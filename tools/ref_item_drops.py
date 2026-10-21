#!/usr/bin/env python3
"""ref_item_drops.py - the ground item (ItemProp_ctor2 and the prop chain under it) and
givePlayerRandom composed with its real callees.

Reference contract, executed against the original by tools/difftest_item_drops.py
(docs/spec/item-drops.md is the prose).

    ItemProp_ctor2          0x1590ec  (block, position, item record, launch flags)
    Prop_ctorNamedLaunch    0x153e54  (obj, position, lump, model, texture, part mask, launch)
    Prop_launch             0x1541a0  (obj, launch flags)
    GameObject_ctor         0x14cb10  (obj, position, class definition 0, properties 0)
    GameObject_rand         0x1509d0  (obj): the object's own generator at +0x44
    item_getResourceIndex   0x1083f8  (item): ref_items.resource_index
    mat34_setPosRotZ        0x163b30  ref_core.mat34_set_pos_rot_z
    givePlayerRandom        0x145f18  (script handler, no arguments)

The Prop_ctorNamedLaunch / Prop_launch / GameObject_ctor bodies are those of
tools/ref_phprop.py and tools/ref_skills_a.py on t3/research-combat-ctors-3 (9ff6ae0),
rewritten here for a plain memory with load/store; difftest_item_drops runs the originals.

Draws.  ItemProp_ctor2 makes ONE draw from the shared seed 0x404464 (GameObject_ctor seeds
the object's own generator +0x44 with it), then OWN draws from +0x44: one for the facing
and, by launch flag, 0-3 velocity draws.  Every caller passes launch 0, so a ground item
costs exactly one shared draw.
"""
import ref_core as C
import ref_items as I
import ref_script_items as R
from ref_script_items import M32, s32, s8, rec, ITEM_SIZE

M64 = (1 << 64) - 1

# ---- addresses (each Observed at the instruction named) -----------------------------------
ITEMPROP_CTOR2 = 0x1590EC
PROP_CTOR_NAMED_LAUNCH, PROP_LAUNCH, GAMEOBJECT_CTOR, GAMEOBJECT_RAND = 0x153E54, 0x1541A0, 0x14CB10, 0x1509D0
RESOURCE_INDEX, MAT34_SET_POS_ROT_Z = 0x1083F8, 0x163B30
GIVE_PLAYER_RANDOM = 0x145F18
LEVEL_TIMES_DIFFICULTY, GENERATE_WITH_AFFIXES = 0x1EBF70, 0x104CA4
ITEM_PARSE, INVENTORY_GIVE, PLAYER_ITEM_WEIGHT, RECALC_LOAD = 0x1069B8, 0x1C1868, 0x1B6338, 0x1BEC10
POOL_NEW, LIBC_STRSTR = 0x14FDB8, 0x3B96A8

VT_ITEMPROP = 0x511C38          # 0x159178/0x15917c
VT_PROP = 0x511D58              # 0x153ebc/0x153ec0 (ref_phprop)
VT_GAMEOBJECT = 0x5122A8        # ref_skills_a
MODEL_TABLE = 0x3E9CE0          # 0x1590f8/0x15911c: 16-byte rows, +0 model name, +4 texture name
S_ITEM_LUMP = 0x5326B0          # 0x159148/0x159160: the lump name handed to Prop_ctorNamedLaunch
ITEM_BLOCK = 0x190              # pool_new(0x190) at every caller
G_PROP_OPTIONS = 0x44FE08       # bit 0x100 damps every launch (ref_phprop)
G_LUMP_GENERATION = 0x41BF78
G_GRID_A, G_OFF_GRID = 0x5DB4F0, 0x5F76F0
S_HIDE = 0x5321A8
G_LEVEL_NAME = 0x41B721         # 0x145fe0/0x145fe8
S_SPECIAL_LEVEL = 0x5312A8      # 0x145fe4/0x146000
G_DIFFICULTY = 0x4F719C
G_PVP_A, G_PVP_B, G_LEVEL = 0x4F711C, 0x4F7120, 0x4F714C
# difficulty -> (descriptor text, byte +0x20, byte +0x21): 0x14601c-0x146098
SPECIAL_ITEMS = {1: (0x5312B8, 0x12, 0x33), 2: (0x531308, 0x33, 0x34), 3: (0x531358, 0x24, 0x35)}
F_0_015 = 0x3C75C28F            # 0x145fd4/0x145fd8
TRIES = 10                      # 0x146194

F_2M16, HALF, ONE = 0x37800000, 0x3F000000, 0x3F800000
F_QUARTER, F_FOUR, F_24, F_72 = 0x3E800000, 0x40800000, 0x41C00000, 0x42900000
F_30, F_60, F_124, F_130 = 0x41F00000, 0x42700000, 0x42F80000, 0x43020000
F_224, F_260, F_324, F_400, F_480 = 0x43600000, 0x43820000, 0x43A20000, 0x43C80000, 0x43F00000

# Leaf call-outs that stay with the host: name -> (address, number of argument words)
EXTERNALS = {
    'handle_link': (0x1A1738, 3), 'obj_getPropInt': (0x14C880, 3), 'res_find': (0x17365C, 2),
    'model_getBounds': (0x179400, 2), 'obj_updateGridCell': (0x14F028, 1),
    'obj_runEveryFrame': (0x14F248, 1), 'obj_stopRunning': (0x14F290, 1),
}


class Fault(Exception):
    """The original reads or writes an address nobody mapped (a null object)."""


def draw(mem):
    """One draw from the shared seed 0x404464."""
    seed = (mem.load(R.G_RAND_SEED, 4) * 0x19660D + 0x3C6EF35F) & M32
    mem.store(R.G_RAND_SEED, 4, seed)
    return seed >> 16


def obj_rand(mem, obj):
    """GameObject_rand 0x1509d0: the object's own generator at +0x44."""
    seed = (mem.load(obj + 0x44, 4) * 0x19660D + 0x3C6EF35F) & M32
    mem.store(obj + 0x44, 4, seed)
    return seed >> 16


def cstr(mem, addr, limit=4096):
    out = bytearray()
    while len(out) < limit:
        b = mem.load((addr + len(out)) & M32, 1)
        if not b:
            break
        out.append(b)
    return bytes(out)


class Ground:
    """ItemProp_ctor2 and its chain on a memory with load/store/read/write.  host.call(name,
    *args) answers the EXTERNALS; model_getBounds returns six signed integers."""

    def __init__(self, mem, tables, host):
        self.mem, self.tables, self.host = mem, tables, host
        self.own_draws = 0

    # ---- helpers ----------------------------------------------------------------------
    def u32(self, a):
        return self.mem.load(a & M32, 4)

    def w32(self, a, v):
        self.mem.store(a & M32, 4, v & M32)

    def w16(self, a, v):
        self.mem.store(a & M32, 2, v & 0xFFFF)

    def u16(self, a):
        return self.mem.load(a & M32, 2)

    def w8(self, a, v):
        self.mem.store(a & M32, 1, v & 0xFF)

    def rand(self, obj):
        self.own_draws += 1
        return obj_rand(self.mem, obj)

    def frac(self, d):
        return C.mul(C.from_int(d), F_2M16)

    def strcpy(self, dst, src):
        data = cstr(self.mem, src) + b'\0'
        self.mem.write(dst, data)

    # ---- item_getResourceIndex -----------------------------------------------------------
    def resource_index(self, item):
        """item_getResourceIndex 0x1083f8: definition +0x34, plus the variant (flag bits
        11-15) when flag bit 36 is set."""
        definition = self.u32(item)
        if definition == 0:
            raise Fault('item_getResourceIndex with definition 0 reads address 0x34')
        row = s32(self.u32(definition + 0x34))
        flags = self.mem.load(item + 8, 8)
        if flags & 0x1000000000:
            row += (flags >> 11) & 0x1F
        return row & M32

    # ---- GameObject_ctor (no definition, no properties) ------------------------------------
    def gameobject_ctor(self, obj, pos):
        """GameObject_ctor 0x14cb10 (obj, position, 0, 0): heads +0, +4, +8, flags +0xc,
        +0x34 = 0; table 0x5122a8; radius 24, height 72; bytes +0x28 = 0x19, +0x29 = 0x49;
        position; +0x24 = 0; the grid link handle_link(cell, obj + 8, obj) with the cell of
        the truncated position ((int)x + 0x3c00) >> 8 (row major, 120 x 120) or the off-grid
        list; obj_getPropInt(obj, 'hide', 0); +0x2c = 0; +0x44 = ONE SHARED DRAW."""
        for off in (0, 4, 8, 0xC, 0x34):
            self.w32(obj + off, 0)
        self.w32(obj + 0x48, VT_GAMEOBJECT)
        self.w32(obj + 0x1C, F_24)
        self.w32(obj + 0x20, F_72)
        self.w8(obj + 0x28, 0x19)
        self.w8(obj + 0x29, 0x49)
        for k in range(3):
            self.w32(obj + 0x10 + 4 * k, pos[k])
        self.w32(obj + 0x24, 0)
        col = (s32(C.to_int(self.u32(obj + 0x10))) + 0x3C00) >> 8
        row = (s32(C.to_int(self.u32(obj + 0x14))) + 0x3C00) >> 8
        cell = G_GRID_A + 4 * (row * 0x78 + col) if 0 <= col < 0x78 and 0 <= row < 0x78 else G_OFF_GRID
        self.host.call('handle_link', cell & M32, (obj + 8) & M32, obj)
        if self.host.call('obj_getPropInt', obj, S_HIDE, 0):
            raise NotImplementedError('a hidden object: the grid node is moved by hand (0x14cc90)')
        self.w32(obj + 0x2C, 0)
        self.w32(obj + 0x44, draw(self.mem))

    # ---- Prop_ctorNamedLaunch ------------------------------------------------------------
    def prop_ctor_named_launch(self, obj, pos, lump, model, texture, part_mask, launch):
        """Prop_ctorNamedLaunch 0x153e54: GameObject_ctor (ONE SHARED DRAW); table
        0x511d58; the three names copied to +0x54, +0x64, +0xa4; +0x4c / +0x50 =
        res_find(lump copy, model copy / texture copy); +0xe8 = 64-bit part mask; ONE OWN
        DRAW: facing +0x38; +0x10c = 0; +0x30 = +0x100 = +0xfc = 0; the bounds centre at
        +0xf0..+0xf8, +0x108 = centre z - min z; launch bit 4 moves the position by the
        centre and relinks the cell; then Prop_launch."""
        self.gameobject_ctor(obj, pos)
        self.w32(obj + 0x48, VT_PROP)
        self.strcpy(obj + 0x54, lump)
        self.strcpy(obj + 0x64, model)
        self.strcpy(obj + 0xA4, texture)
        self.w32(obj + 0x4C, self.host.call('res_find', (obj + 0x54) & M32, (obj + 0x64) & M32))
        texture_entry = self.host.call('res_find', (obj + 0x54) & M32, (obj + 0xA4) & M32)
        self.mem.store(obj + 0xE8, 8, part_mask & M64)
        self.w32(obj + 0x50, texture_entry)
        d = self.rand(obj)
        self.w16(obj + 0x10C, 0)
        self.w16(obj + 0x38, d)
        for off in (0x30, 0x100, 0xFC):
            self.w32(obj + off, 0)
        b = self.host.call('model_getBounds', self.u32(obj + 0x4C), self.mem.load(obj + 0xE8, 8))
        lo_x, lo_y, lo_z, hi_x, hi_y, hi_z = (s32(v) for v in b)
        cz = C.from_int(s32((lo_z + hi_z) & M32) >> 1)
        cx = C.from_int(s32((lo_x + hi_x) & M32) >> 1)
        cy = C.from_int(s32((lo_y + hi_y) & M32) >> 1)
        self.w32(obj + 0xF8, cz)
        self.w32(obj + 0xF0, cx)
        self.w32(obj + 0xF4, cy)
        self.w32(obj + 0x108, C.sub(cz, C.from_int(lo_z)))
        if launch & 4:
            self.w32(obj + 0x10, C.add(self.u32(obj + 0x10), cx))
            self.w32(obj + 0x14, C.add(self.u32(obj + 0x14), cy))
            self.w32(obj + 0x18, C.add(self.u32(obj + 0x18), cz))
            self.host.call('obj_updateGridCell', obj)
        self.prop_launch(obj, launch)

    # ---- Prop_launch ---------------------------------------------------------------------
    def prop_launch(self, obj, launch):
        """Prop_launch 0x1541a0 (obj, launch flags); see docs/spec/item-drops.md 1.3."""
        u32, w32, w16, u16 = self.u32, self.w32, self.w16, self.u16
        w32(obj + 0xC, u32(obj + 0xC) | 0x1809)
        self.host.call('obj_updateGridCell', obj)
        w32(obj + 0x1C, F_FOUR)
        if launch & 0x100:
            w16(obj + 0x140, u16(obj + 0x140) | 2)
            w32(obj + 0xC, u32(obj + 0xC) | 0x4000)
        if launch & 0x200:
            w16(obj + 0x140, u16(obj + 0x140) | 4)
        for bit, span in ((1, F_124), (8, F_224), (0x10, F_324)):
            if launch & bit:
                w32(obj + 0xFC, C.mul(C.sub(self.frac(self.rand(obj)), HALF), span))
                w32(obj + 0x100, C.mul(C.sub(self.frac(self.rand(obj)), HALF), span))
                if bit == 0x10:
                    w32(obj + 0x30, C.mul(self.frac(self.rand(obj)), F_480))
        if launch & 0x20:
            w32(obj + 0x30, C.add(C.mul(self.frac(self.rand(obj)), F_30), F_130))
        if launch & 0x40:
            w32(obj + 0x30, C.add(C.mul(self.frac(self.rand(obj)), F_60), F_260))
        if launch & 2:
            w16(obj + 0x10C, 2000)
        self.host.call('obj_runEveryFrame', obj)
        w16(obj + 0x10E, 0x7FFF if launch & 0x8000 else 0xB4)
        if launch & 0x2000:
            w16(obj + 0x140, u16(obj + 0x140) | 8)
        elif launch & 0x4000:
            w16(obj + 0x140, u16(obj + 0x140) | 0x10)
        if launch & 0x10000:
            w16(obj + 0x140, u16(obj + 0x140) | 0x20)
        if launch & 0x80:
            bits = u16(obj + 0x140)
            w16(obj + 0x10E, 0)
            w16(obj + 0x140, bits | 1)
            if not bits & 2:
                self.host.call('obj_stopRunning', obj)
        if u32(G_PROP_OPTIONS) & 0x100:
            if C.lt(F_400, u32(obj + 0x30)):
                w32(obj + 0x30, F_400)
            w32(obj + 0x30, C.mul(u32(obj + 0x30), F_QUARTER))
            w32(obj + 0xFC, C.mul(u32(obj + 0xFC), HALF))
            w32(obj + 0x100, C.mul(u32(obj + 0x100), HALF))

    # ---- ItemProp_ctor2 ------------------------------------------------------------------
    def itemprop_ctor2(self, obj, pos, item, launch):
        """ItemProp_ctor2 0x1590ec (block, position (12 bytes, copied), item record, launch).

        row = item_getResourceIndex(item) (asked twice); Prop_ctorNamedLaunch(obj, copy of
        the position, lump 0x5326b0, model name = word +0 of row `row` of 0x3e9ce0, texture
        name = word +4 of that row, part mask -1 (all 64 bits), launch).  Table 0x511c38.
        The empty record at +0x148 (halfwords +0x16c, +0x174, +0x17c, +0x184 = 0xffff,
        bytes +0x169, +0x168 = 0xff, halfwords +0x158..+0x166 = 0), then the 0x48 bytes of
        the item copied over it (with ld/sd: the item and obj + 0x148 must be 8-aligned).
        Flags +0xc = (flags | 0x102000) & ~0x1800, and & ~0x3000 as well when bit 39 of the
        item's flags (+0x150) is set.  obj_updateGridCell(obj).  The matrix +0x110 =
        mat34_setPosRotZ(position, s16(facing + 0x4000))."""
        pos = tuple(pos)
        row = self.resource_index(item)
        row2 = self.resource_index(item)
        model = self.u32(MODEL_TABLE + (row << 4))
        texture = self.u32(MODEL_TABLE + (row2 << 4) + 4)
        self.prop_ctor_named_launch(obj, pos, S_ITEM_LUMP, model, texture, M64, launch)
        self.w32(obj + 0x48, VT_ITEMPROP)
        for k in range(4):
            self.w16(obj + 0x16C + 8 * k, 0xFFFF)
        self.w8(obj + 0x169, 0xFF)
        self.w8(obj + 0x168, 0xFF)
        for k in range(4):
            self.w16(obj + 0x158 + 2 * k, 0)
            self.w16(obj + 0x160 + 2 * k, 0)
        if item & 7 or (obj + 0x148) & 7:
            raise Fault('ItemProp_ctor2: ld/sd copy of an item record that is not 8-aligned')
        self.mem.write(obj + 0x148, self.mem.read(item, ITEM_SIZE))
        flags = ((self.u32(obj + 0xC) | 0x102000) & ~0x1800) & M32
        if self.mem.load(obj + 0x150, 8) & (0x8000 << 24):
            flags &= ~0x3000 & M32
        self.w32(obj + 0xC, flags)
        self.host.call('obj_updateGridCell', obj)
        here = tuple(self.u32(obj + 0x10 + 4 * k) for k in range(3))
        angle = C.s16((self.u16(obj + 0x38) + 0x4000) & 0xFFFF)
        for k, v in enumerate(C.mat34_set_pos_rot_z(here, angle)):
            self.w32(obj + 0x110 + 4 * k, v)


# =========================================================================================
# givePlayerRandom
# =========================================================================================
def game_from(mem):
    """The globals item_generateWithAffixes and level_monsterLevelTimesDifficulty read."""
    n = s32(mem.load(R.G_NUM_PLAYERS, 4))
    classes = [s32(mem.load(rec(k) + R.P_CLASS, 4)) for k in range(4)]
    return I.Game(n, classes, s32(mem.load(G_DIFFICULTY, 4)), s32(mem.load(G_PVP_A, 4)),
                  s32(mem.load(G_PVP_B, 4)), level_raw=mem.load(G_LEVEL, 4))


def blank_record(mem, at):
    """The handler's pre-set of its stack record (0x145f4c-0x145f98): halfwords +0x24,
    +0x2c, +0x34, +0x3c = 0xffff, bytes +0x21, +0x20 = 0xff, halfwords +0x10..+0x1e = 0.
    +0x00..+0x0f, +0x22, +0x23, the slot values and +0x44.. keep what the stack held."""
    for k in range(4):
        mem.store(at + 0x24 + 8 * k, 2, 0xFFFF)
    mem.store(at + 0x21, 1, 0xFF)
    mem.store(at + 0x20, 1, 0xFF)
    for k in range(4):
        mem.store(at + 0x10 + 2 * k, 2, 0)
        mem.store(at + 0x18 + 2 * k, 2, 0)


class RandomGiver(R.Composer):
    """givePlayerRandom with its callees.  The host answers pool_new (and the call-outs
    R.Composer sends it); the ground item is Ground.itemprop_ctor2 on the same memory.
    self.scratch is the handler's stack record."""

    def __init__(self, mem, tables, host, scratch):
        R.Composer.__init__(self, mem, tables, host, scratch)
        self.ground = Ground(mem, tables, host)
        self.tries = []                 # per player: generator calls made
        self.generated = []             # per player: did the last call succeed

    def _give_or_drop(self, slot):
        """player_itemWeight(slot, record); load + w < limit (C.OLT.S only, no zero clause):
        inventory_giveItem(slot, record, 1), player_recalcLoad(slot).  Otherwise
        pool_new(0x190); with a block, ItemProp_ctor2(block, copy of the position of the
        record's object (no null test), record, 0)."""
        mem = self.mem
        weight = R.item_weight(mem, self.tables, self.host, slot, self.scratch)
        if R.fits(mem, slot, weight, True):
            if mem.load(self.scratch, 4) == 0:
                raise Fault('inventory_giveItem with definition 0 reads the category byte at address 0x1d')
            self.machine.give_item(slot, self.scratch, 1)
            R.recalc_load(mem, self.tables, self.host, slot)
            return 'give'
        block = self.host.call('pool_new', ITEM_BLOCK) & M32
        if block == 0:
            return 'lost'
        obj = mem.load(rec(slot) + R.P_OBJECT, 4)
        if obj == 0:
            raise Fault('givePlayerRandom: drop for a player without an object (reads address 0x10)')
        pos = tuple(mem.load(obj + 0x10 + 4 * k, 4) for k in range(3))
        self.ground.itemprop_ctor2(block, pos, self.scratch, 0)
        return 'drop'

    def _generate(self, budget, category, level):
        """item_generateWithAffixes(record, budget, category, -1, level) -> 0 / 1.  On
        success the record is the generated item (bytes the generator never defines keep
        the record's old bytes); on failure the record is not written."""
        rng = I.Rng(self.seed)
        item = I.generate_with_affixes(self.tables, game_from(self.mem), rng, s32(budget), category, -1, s32(level))
        self.mem.store(R.G_RAND_SEED, 4, rng.seed)
        if item is None:
            return 0
        old = self.mem.read(self.scratch, ITEM_SIZE)
        self.mem.write(self.scratch, item.pack(old))
        return 1

    def givePlayerRandom(self):
        """0x145f18.  For slot 0 .. g_numPlayers - 1 (re-read after each player):
          blank the record; d = ONE SHARED DRAW; s = level_monsterLevelTimesDifficulty();
          budget = (int)((float)d * s * 0.015)  (0x3c75c28f; two single multiplies, cvt.w.s)
          if strstr(level name 0x41b721, 0x5312a8): for difficulty 1, 2, 3 parse the fixed
            descriptor (variant 0, usePresets 0: no draw) and overwrite bytes +0x20/+0x21;
            then give or drop the record (any difficulty);
          up to 10 times: r = ONE SHARED DRAW; item_generateWithAffixes(record, budget,
            r & 1, -1, (int)g_levelMonsterLevel); stop on non-zero;
          give or drop the record."""
        mem = self.mem
        self.outcomes = []
        slot = 0
        while slot < self.num_players:
            blank_record(mem, self.scratch)
            d = draw(mem)
            s = game_from(mem).level_times_difficulty()
            budget = C.to_int(C.mul(C.mul(C.from_int(d), s), F_0_015))
            if cstr(mem, S_SPECIAL_LEVEL) in cstr(mem, G_LEVEL_NAME):
                special = SPECIAL_ITEMS.get(s32(mem.load(G_DIFFICULTY, 4)))
                if special is not None:
                    text, b20, b21 = special
                    rng = I.Rng(self.seed)
                    item = I.parse_descriptor(self.tables, cstr(mem, text), 0, False, rng)
                    mem.store(R.G_RAND_SEED, 4, rng.seed)
                    mem.write(self.scratch, item.pack(mem.read(self.scratch, ITEM_SIZE)))
                    mem.store(self.scratch + 0x20, 1, b20)
                    mem.store(self.scratch + 0x21, 1, b21)
                self.outcomes.append(('special', slot, self._give_or_drop(slot)))
            made, tries = 0, 0
            while tries < TRIES:
                r = draw(mem)
                level = C.to_int(mem.load(G_LEVEL, 4))
                tries += 1
                made = self._generate(budget, r & 1, level)
                if made:
                    break
            self.tries.append(tries)
            self.generated.append(made)
            self.outcomes.append(('random', slot, self._give_or_drop(slot)))
            slot += 1
        return 0

