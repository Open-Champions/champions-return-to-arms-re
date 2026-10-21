#!/usr/bin/env python3
"""ref_combat_runtime.py - reference contract of how Champions: Return to Arms (SLUS_209.73,
US v2.00) keeps SEVERAL live actors in one world while they fight: one memory, one identity
scheme, one grid, one contact loop, one damage path, and the order in which the original
calls each service.  docs/combat-runtime.md is the prose version and says, statement by
statement, what is Observed, Executed elsewhere, Inferred or authored here.

A research tool, not game code.  Standard library only; no game data is embedded.

Why a composition module
    The pieces were modelled one at a time, each with its own representation:

        tools/ref_objects.py    lists, grid, box query, run order, deferred deletion
                                (Python objects; executed against the original)
        tools/ref_creature.py   the creature base class on a memory image: take-damage,
                                pending damage and death, target choice, the contact
                                loop of Creature_moveBy (executed)
        tools/ref_combat.py     damage_apply on Python records (executed)
        tools/ref_player.py     Player_run on a memory image; the melee target scan is
                                part of it (executed)

    A rebuild with more than one fighting actor needs them to agree about the same
    objects.  This module binds them to ONE authority, a SharedMemory image:

      * object fields (+0xc flags, +0x10 position, +0x1c radius, +0x20 height, +0x38
        facing, +0x44 own seed, +0x48 table, and every creature/player field) live in the
        image and nowhere else.  ref_objects' GameObject is re-bound so that its
        attributes read and write the image (BoundObject); ref_combat's Obj is replaced by
        a live view (LiveObj) over the same bytes;
      * every handle word (an object's three heads, the target +0x234, the last attacker
        +0x2e4, the ally +0x238, the status source +0x360, the player's sweep list +0x4b8)
        is a ref_core Cell of the ONE HandlePool of the world, and node words read from
        that pool.  Destroying an object therefore nulls every handle to it at the moment
        GameObject_dtor clears head +0, exactly as in the original;
      * the shared seed 0x404464, g_simFrame, g_excludeMask and the other globals the
        models read are words of the image; ref_objects' SharedRandom and ref_combat's
        Seed are views of the same word, so object construction, damage rolls and the
        creature code draw from one sequence.

    No value is copied between models, so there is nothing to import or publish and no
    window in which two copies disagree.

What the module adds: CombatModel (ref_arena_monsters.Model plus the bodies below)
    Executed - tools/difftest_combat_runtime.py runs the original under tools/ee_emu.py and
    compares calls, stored bytes, the shared seed and the result:
        can_see_obj             creature_canSeeObj 0x10c810
        hit_target_in_arc       Creature_hitTargetInArc 0x119938
        hit_all_enemies_in_arc  Creature_hitAllEnemiesInArc 0x119b58
        find_enemy_in_cone      creature_findEnemyInCone 0x10cf78
        apply_knockback         Creature_applyKnockback 0x115eb8
        dead_update             Creature_deadUpdate 0x1108a0 (no blood decal)
        player_is_enemy         Player_isEnemy 0x1b5ea8 (Player slot 20)
        player_take_damage      Player_takeDamage 0x1b5330 (Player slot 2)
        player_find_target      Player_findTarget 0x1bb3c8
        player_process_damage   Player_processDamage 0x1b2cc0 (restricted)
        player_melee_hit        Player_meleeHit 0x1b6a98 (unarmed)
    Observed only (read, not executed):
        move_with_collision     obj_moveWithCollision 0x14d4b8 (docs/spec/movement-camera.md 5.5)
        move_simple             creature_moveSimple 0x1186d8
        player_move             Player_move 0x1b4020, still stick, modes 0, 3, 4
        player_on_touch, player_team, player_skill_rank   Player slots 6, 37, 39
        the destructor chain    Creature_dtor 0x117128 (Runtime._slot1)
    Runtime: the composition of one tick - runObjects order, slot 4 of each actor (the
    Skelight run of ref_arena_monsters; an AUTHORED player driver around ref_player's
    executed state switch), deferred deletion and destruction, the service table each
    call-out and virtual slot reaches.

Restricted domain (everything else raises Unsupported rather than inventing behaviour)
    offline (g_networkMode 0), no cutscene, damage-number option 0, decal option 0, no
    spells, weapons or projectiles, no effect objects created by the damage function (a
    pool request from inside damage_apply is refused), no water, an authored flat floor
    and an authored animation timeline supplied by the caller, players standing still
    (melee only).  Inside that domain every call the models make is answered by a model
    or by a labelled fixture, in the order the original makes it.
"""
import os
import struct as _struct
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_objects as O                         # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat as RB                         # noqa: E402
import ref_arena_monsters as AM                 # noqa: E402
import ref_player as RP                         # noqa: E402

M32 = 0xFFFFFFFF
M64 = 0xFFFFFFFFFFFFFFFF
s8, s16, s32 = RC.s8, RC.s16, RC.s32
f32 = C.f32

ZERO, HALF, ONE = 0, 0x3F000000, 0x3F800000


class CompositionError(Exception):
    """The original has no defined behaviour here (a stale or foreign pointer, a store
    into a handle word, an iterator read as a node); the contract refuses."""


class Unsupported(Exception):
    """Outside the restricted domain of this contract: the original does something here
    that no executed model covers.  Refused instead of guessed."""


# =======================================================================================
# 1. Addresses
# =======================================================================================

G_RAND_SEED = 0x404464          # shared seed (sync hash)
G_COSMETIC_SEED = 0x404460      # per machine
G_SIM_FRAME = 0x44FDCC
G_EXCLUDE_MASK = 0x4039B8
G_NETWORK_MODE = 0x402791       # s8
G_CULL_BY_CAMERA = 0x4039C1     # s8
G_CUTSCENE_ACTIVE = 0x44FCD0    # s8
G_NUMBERS_OPTION = 0x44FCF8     # damage-number option (per machine; matters offline only)
G_NUM_PLAYERS = RC.G_NUM_PLAYERS
G_PLAYERS, REC_SIZE, REC_OBJ = RC.G_PLAYERS, RC.REC_SIZE, RC.REC_OBJ
G_PVP_MODE_A = 0x4F711C
G_WORLD = RC.G_WORLD
G_LEVEL_NAME = 0x41B721

# object flags (+0xc)
F_NOT_SOLID = 0x1
F_DEAD = 0x8
F_CREATURE = 0x20
F_PLAYER = 0x40
F_OWNED = 0x80                  # has an owner handle at +0x4c (projectiles)
F_HIT_THIS_TICK = 0x100         # set by Creature_processDamage on pending damage
F_NOT_RUN = 0x8000
F_PREDICTION_COPY = 0x20000

# creature AI states (+0x232)
ST_IDLE, ST_DEAD = 0, 0x14

# handle words of a creature / player that the combat path links or clears
H_TARGET = 0x234
H_ALLY = 0x238
H_LAST_ATTACKER = 0x2E4
H_STATUS_SOURCE = 0x360
H_SWEEP = 0x4B8                 # player: targets of a sweeping swing
H_OWNER = 0x4C                  # projectile owner (not used in the domain)
HANDLE_FIELDS = (H_TARGET, H_ALLY, H_LAST_ATTACKER, H_STATUS_SOURCE)

POOL_BLOCK = {0: 0x180, 1: 0x500, 2: 3000}
CREATURE_SIZE = 0x3C8
PLAYER_SIZE = 0x590


# =======================================================================================
# 2. One memory: object bytes, globals, handle words and the node pool
# =======================================================================================

class SharedMemory(RC.Memory):
    """The single authority.  Plain bytes for object fields and globals; handle words and
    node fields are views of the world's HandlePool.

      * A registered head address (an object's +0, +4, +8, or a handle field) reads as the
        address of the first node of its Cell, or 0.  Storing into it is refused, except
        a 4-byte store of 0 into an empty head - the `handle_clear(h); h = 0` the original
        writes after clearing (Creature_pickTarget, Creature_filterState).
      * The node region (HandlePool.NODE_BASE, 20 bytes per node) reads +0 next, +4 prev,
        +8 partner, +0xc object, +0x10 the 16-bit tag.  Stores are refused: only the
        handle functions write nodes.
    """

    NODE_BASE = C.HandlePool.NODE_BASE
    NODE_SIZE = C.HandlePool.NODE_SIZE

    def __init__(self, handles):
        RC.Memory.__init__(self)
        self.handles = handles
        self.heads = {}                         # address -> ref_core Cell
        self.node_end = self.NODE_BASE + self.NODE_SIZE * len(handles.nodes)

    # ---- heads ---------------------------------------------------------------------
    def register_head(self, addr, cell):
        if addr & 3:
            raise CompositionError('head 0x%x is not word aligned' % addr)
        old = self.heads.get(addr)
        if old is not None and old is not cell and old.next is not None:
            raise CompositionError('head 0x%x re-registered while it still holds a node' % addr)
        self.heads[addr] = cell

    def head(self, addr):
        """The Cell of a handle word, created on first use (a zero word is an empty head)."""
        addr &= M32
        cell = self.heads.get(addr)
        if cell is None:
            if RC.Memory.load(self, addr, 4) != 0:
                raise CompositionError('handle word 0x%x holds a raw value' % addr)
            cell = C.Cell(addr)
            self.register_head(addr, cell)
        return cell

    def forget_heads(self, lo, hi):
        """A freed block: its handle words are dead memory (their Cells are empty)."""
        for addr in [a for a in self.heads if lo <= a < hi]:
            if self.heads[addr].next is not None:
                raise CompositionError('freed block still has a linked head at 0x%x' % addr)
            del self.heads[addr]

    def node_addr(self, node):
        if node is None:
            return 0
        if isinstance(node, C.Cell):
            return node.name & M32
        if isinstance(node, C.Node):
            return self.NODE_BASE + self.NODE_SIZE * node.index
        raise CompositionError('an iterator was read as a node')

    def _node_field(self, addr, size):
        index, off = divmod(addr - self.NODE_BASE, self.NODE_SIZE)
        node = self.handles.nodes[index]
        if off == 0x10 and size <= 2:
            return node.tag & ((1 << (8 * size)) - 1)
        if off & 3 or size != 4:
            raise CompositionError('unaligned read of node field 0x%x' % addr)
        if off == 0:
            return self.node_addr(node.next)
        if off == 4:
            return self.node_addr(node.prev)
        if off == 8:
            return self.node_addr(node.partner)
        if off == 0xC:
            return node.obj.addr if node.obj is not None else 0
        raise CompositionError('read of node padding 0x%x' % addr)

    def _touches_head(self, addr, size):
        a = addr & ~3
        while a < addr + size:
            if a in self.heads:
                return a
            a += 4
        return None

    # ---- the Memory interface ---------------------------------------------------------
    def load(self, addr, size):
        addr &= M32
        if self.NODE_BASE <= addr < self.node_end:
            return self._node_field(addr, size)
        head = self._touches_head(addr, size)
        if head is not None:
            if head != addr or size != 4:
                raise CompositionError('partial read of handle word 0x%x' % head)
            return self.node_addr(self.heads[head].next)
        return RC.Memory.load(self, addr, size)

    def _check_store(self, addr, size, value):
        if self.NODE_BASE <= addr < self.node_end:
            raise CompositionError('store into the node pool at 0x%x' % addr)
        head = self._touches_head(addr, size)
        if head is not None:
            if head != addr or size != 4 or value & M32 or self.heads[head].next is not None:
                raise CompositionError('store into handle word 0x%x' % head)
            return False
        return True

    def store(self, addr, size, value):
        addr &= M32
        value &= (1 << (8 * size)) - 1
        if self._check_store(addr, size, value):
            RC.Memory.store(self, addr, size, value)
        else:
            self.log.append((addr, size, value))

    def poke(self, addr, size, value):
        addr &= M32
        if self._check_store(addr, size, value & ((1 << (8 * size)) - 1)):
            RC.Memory.poke(self, addr, size, value)

    def zero(self, lo, hi):
        """pool_new's zero fill of a whole block."""
        for a in range(lo, hi):
            self.bytes.pop(a, None)

    # ---- typed helpers --------------------------------------------------------------
    def u32(self, a):
        return self.load(a, 4)

    def w32(self, a, v):
        self.poke(a, 4, v & M32)


def _mem_prop(off, size, signed=False):
    mask = (1 << (8 * size)) - 1

    def get(self):
        v = self._mem.load(self.addr + off, size)
        if signed and v >> (8 * size - 1):
            v -= 1 << (8 * size)
        return v

    def put(self, value):
        self._mem.poke(self.addr + off, size, value & mask)
    return property(get, put)


class _MemVec(list):
    """A list of 32-bit words that writes item assignments through to the image."""

    def __init__(self, mem, base, count, stride=4, size=4, signed=False):
        self._mem, self._base, self._stride, self._size, self._signed = mem, base, stride, size, signed
        list.__init__(self, [self._read(i) for i in range(count)])

    def _read(self, i):
        v = self._mem.load(self._base + i * self._stride, self._size)
        if self._signed and v >> (8 * self._size - 1):
            v -= 1 << (8 * self._size)
        return v

    def __setitem__(self, i, value):
        list.__setitem__(self, i, value)
        self._mem.poke(self._base + i * self._stride, self._size, value & ((1 << (8 * self._size)) - 1))


class BoundObject(O.GameObject):
    """ref_objects' GameObject whose fields are the bytes of the shared image.  The three
    heads stay the Cells the object model links through; they are registered in the image
    so that the creature code reads them as words."""
    flags = _mem_prop(0x0C, 4)
    radius = _mem_prop(0x1C, 4)
    height = _mem_prop(0x20, 4)
    vz = _mem_prop(0x30, 4)
    angle = _mem_prop(0x38, 2)
    seed = _mem_prop(0x44, 4)
    vtable = _mem_prop(0x48, 4)

    @property
    def pos(self):
        return _MemVec(self._mem, self.addr + 0x10, 3)

    @pos.setter
    def pos(self, value):
        for i in range(3):
            self._mem.poke(self.addr + 0x10 + 4 * i, 4, value[i] & M32)


_BOUND_FIELDS = ('flags', 'radius', 'height', 'vz', 'angle', 'seed', 'vtable', 'pos')


class MemSharedRandom(C.SharedRandom):
    """ref_objects' g_randSeed as the word 0x404464 of the image."""

    def __init__(self, mem):
        self._mem = mem

    @property
    def state(self):
        return self._mem.u32(G_RAND_SEED)

    @state.setter
    def state(self, value):
        self._mem.w32(G_RAND_SEED, value)


class MemSeed(RB.Seed):
    """ref_combat's shared seed as the same word; .draws keeps what damage_apply drew."""

    def __init__(self, mem, addr=G_RAND_SEED):
        self._mem, self._addr, self.draws = mem, addr, []

    @property
    def state(self):
        return self._mem.u32(self._addr)

    @state.setter
    def state(self, value):
        self._mem.w32(self._addr, value)


def _global(addr, size, signed=False):
    mask = (1 << (8 * size)) - 1

    def get(self):
        v = self.mem.load(addr, size)
        if signed and v >> (8 * size - 1):
            v -= 1 << (8 * size)
        return v

    def put(self, value):
        self.mem.poke(addr, size, value & mask)
    return property(get, put)


class SharedWorld(O.World):
    """ref_objects.World over the shared image: the frame number, exclude mask, network
    flag and camera switch are the globals of the image, the shared seed is its word,
    every created object is a BoundObject, and a freed block is zeroed again on reuse."""
    frame = _global(G_SIM_FRAME, 4)
    exclude_mask = _global(G_EXCLUDE_MASK, 4)
    network_mode = _global(G_NETWORK_MODE, 1, True)
    cull_by_camera = _global(G_CULL_BY_CAMERA, 1, True)
    cursor60 = _global(O.G_CURSOR_60, 4, True)
    cursor15 = _global(O.G_CURSOR_15, 4, True)

    @property
    def camera_focus(self):
        return _MemVec(self.mem, O.G_CAMERA_FOCUS, 3)

    @camera_focus.setter
    def camera_focus(self, value):
        for i in range(3):
            self.mem.poke(O.G_CAMERA_FOCUS + 4 * i, 4, value[i] & M32)

    @property
    def centres(self):
        """g_activityCenters 0x4039c8 (four Vec3) and their count 0x403a08 (s8)."""
        count = s8(self.mem.load(O.G_ACTIVITY_COUNT, 1))
        return [list(_MemVec(self.mem, O.G_ACTIVITY_CENTERS + 12 * i, 3)) for i in range(max(count, 0))]

    @centres.setter
    def centres(self, value):
        if len(value) > 4:
            raise CompositionError('more than four activity centres')
        for i, centre in enumerate(value):
            for k in range(3):
                self.mem.poke(O.G_ACTIVITY_CENTERS + 12 * i + 4 * k, 4, centre[k] & M32)
        self.mem.poke(O.G_ACTIVITY_COUNT, 1, len(value))

    def __init__(self):
        handles = C.HandlePool()
        self.mem = SharedMemory(handles)
        O.World.__init__(self)
        self.handles = handles
        self.mem.handles = handles
        self.shared = MemSharedRandom(self.mem)
        for cell in [self.run_active, self.delete_list, self.always_draw, self.off_grid] \
                + self.run15 + self.run60 + self.grid + self.grid_b:
            self.mem.register_head(cell.name, cell)

    def construct(self, addr, pos, class_def=None, props=None, stale_props=None):
        block = self._block_size(addr)
        self.mem.zero(addr, addr + block)
        self.mem.forget_heads(addr, addr + block)
        for i, cell in enumerate((C.Cell(addr), C.Cell(addr + 4), C.Cell(addr + 8))):
            self.mem.register_head(addr + 4 * i, cell)
        obj = O.World.construct(self, addr, pos, class_def, props, stale_props)
        # the base constructor linked heads[2] already; adopt the object's own Cells
        for i, cell in enumerate(obj.heads):
            self.mem.heads[addr + 4 * i] = cell
        values = {name: obj.__dict__.pop(name) for name in _BOUND_FIELDS}
        obj.__class__ = BoundObject
        obj._mem = self.mem
        for name, value in values.items():
            setattr(obj, name, value)
        return obj

    def _block_size(self, addr):
        index = self.pool.class_of(addr)
        return self.pool.CLASSES[index][0]

    def obj(self, addr):
        """The live object at an address, or a CompositionError: a pointer that is not a
        live object is what the original would follow into freed or foreign memory."""
        obj = self.objects.get(addr & M32)
        if obj is None:
            raise CompositionError('0x%x is not a live object' % addr)
        return obj

    def destroy(self, obj, flags=3):
        """GameObject_dtor 0x14cf90 on the shared image (the derived destructors that run
        before it are the runtime's, section 6)."""
        O.World.destroy(self, obj, flags)
        if flags & 1:
            block = self._block_size(obj.addr)
            for addr in [a for a in self.mem.heads if obj.addr <= a < obj.addr + block]:
                if self.mem.heads[addr].next is not None:
                    raise CompositionError('destroyed object still holds a link at 0x%x' % addr)


# =======================================================================================
# 3. ref_combat's records as live views of the same bytes
# =======================================================================================

class LiveObj(RB.Obj):
    """ref_combat.Obj whose fields are the bytes of the image (no copy).  Fields the
    restricted domain excludes are fixed: no owner link, no spells, never Innoruuk."""
    flags = _mem_prop(0x0C, 4)
    facing = _mem_prop(0x38, 2, True)
    own_seed = _mem_prop(0x44, 4)
    cflags = _mem_prop(0xA8, 8)
    kind = _mem_prop(0xB4, 1)
    dot = _mem_prop(0xCC, 4)
    exp_value = _mem_prop(0xD8, 4)
    field_dc = _mem_prop(0xDC, 4)
    armor = _mem_prop(0xE4, 2)
    stamp_f0 = _mem_prop(0xF0, 4)
    hp = _mem_prop(0x228, 4)
    max_hp = _mem_prop(0x22C, 4)
    poison_a = _mem_prop(0x358, 2)
    poison_b = _mem_prop(0x35A, 2)
    counter2 = _mem_prop(0x374, 4)
    counter4 = _mem_prop(0x37C, 4)
    counter11 = _mem_prop(0x398, 4)
    counter12 = _mem_prop(0x39C, 4)
    slot = _mem_prop(0x3C8, 4)
    state = _mem_prop(0x58C, 4)                 # players only (the action state)
    attack_start = _mem_prop(0x458, 4)
    attack_chain = _mem_prop(0x45C, 4)

    def __init__(self, rt, addr, cls):          # noqa: no Record.__init__: nothing is copied
        d = self.__dict__
        d.update(_rt=rt, _mem=rt.mem, addr=addr, tag=addr, cls=cls, innoruuk_immune=0,
                 owner_link=False, owner=None, model_points=1, boss_rank=0)

    def __setattr__(self, name, value):
        if name in ('owner_link', 'owner', 'innoruuk_immune'):
            raise Unsupported('ref_combat would change %s, which the domain keeps fixed' % name)
        object.__setattr__(self, name, value)

    @property
    def pos(self):
        return _MemVec(self._mem, self.addr + 0x10, 3)

    @property
    def res(self):
        return _MemVec(self._mem, self.addr + 0x5C, 5)

    @property
    def flash(self):
        return _MemVec(self._mem, self.addr + 0x90, 8, 2, 2, True)

    @flash.setter
    def flash(self, values):
        for i, v in enumerate(values):
            self._mem.poke(self.addr + 0x90 + 2 * i, 2, v & 0xFFFF)

    @property
    def status(self):
        return _MemVec(self._mem, self.addr + 0x340, 5)

    @status.setter
    def status(self, values):
        for i, v in enumerate(values):
            self._mem.poke(self.addr + 0x340 + 4 * i, 4, v & M32)

    @property
    def bonus(self):
        return _MemVec(self._mem, self.addr + 0x474, 4, 1, 1, True)

    @property
    def spells(self):
        node = self._mem.heads.get(self.addr + 0x364)
        if node is not None and node.next is not None:
            raise Unsupported('attached spells are outside the domain')
        return []

    @spells.setter
    def spells(self, value):
        raise Unsupported('damage_apply would attach a spell (disease): outside the domain')

    @property
    def status_source(self):
        obj = self._rt.handle_target(self.addr + H_STATUS_SOURCE)
        return self._rt.live(obj) if obj else None

    @status_source.setter
    def status_source(self, source):
        """The status setter 0x118950 re-links +0x360 (handle_clear, then handle_link)."""
        self._rt.relink(self.addr + H_STATUS_SOURCE, source.addr if source is not None else 0)

    @property
    def last_attacker(self):
        obj = self._rt.handle_target(self.addr + H_LAST_ATTACKER)
        return self._rt.live(obj) if obj else None


class LiveRec:
    """The parts of a player record (g_players + slot * 0x4c30) that damage_apply reads:
    the skill ranks (+0x4b08, (s16 id, s16 rank) pairs up to id -1), hit points and the
    object pointer."""

    def __init__(self, rt, slot):
        self._rt, self.slot = rt, slot
        self.base = G_PLAYERS + slot * REC_SIZE

    def rank(self, skill):
        """player_getSkillRank 0x1bf330."""
        a = self.base + 0x4B08
        while True:
            ident = s16(self._rt.mem.load(a, 2))
            if ident == -1:
                return 0
            if ident == skill:
                return s16(self._rt.mem.load(a + 2, 2))
            a += 4

    @property
    def hp(self):
        return self._rt.mem.u32(self.base + 0xAC)

    @hp.setter
    def hp(self, value):
        self._rt.mem.w32(self.base + 0xAC, value)

    @property
    def max_hp(self):
        return self._rt.mem.u32(self.base + 0xB0)

    @property
    def obj(self):
        addr = self._rt.mem.u32(self.base + REC_OBJ)
        return self._rt.live(addr) if addr else None


# =======================================================================================
# 4. Dispatch tables (Observed: the function words of the tables in SLUS_209.73)
# =======================================================================================
# slot -> function.  Only addresses; CombatModel.knows() says which have a model.

VT_CREATURE, VT_PLAYER, VT_SKELIGHT = 0x50CC58, 0x511308, 0x5174B0

CREATURE_SLOTS = {
    0: 0x3C2608, 1: 0x117128, 2: 0x116638, 3: 0x11A5F0, 4: 0x3C7E98, 5: 0x3C7EA0, 6: 0x11A418,
    7: 0x11A260, 8: 0x116920, 9: 0x116780, 10: 0x11A3F0, 11: 0x11A448, 12: 0x11A290,
    13: 0x116D50, 14: 0x116BD8, 15: 0x11C298, 16: 0x3C2738, 17: 0x11A868, 18: 0x118410,
    19: 0x118418, 20: 0x119328, 21: 0x119400, 22: 0x10DE10, 23: 0x10DED0, 24: 0x10E2C0,
    25: 0x10E658, 26: 0x10BB08, 27: 0x3C2688, 28: 0x10BEB8, 29: 0x11A668, 30: 0x118A58,
    31: 0x118AF8, 32: 0x10BFC8, 33: 0x3C2700, 34: 0x3C2708, 35: 0x118C50, 36: 0x118C78,
    37: 0x3C2730, 38: 0x3C2748,
}
PLAYER_SLOTS = dict(CREATURE_SLOTS)
PLAYER_SLOTS.update({0: 0x3C3AB8, 1: 0x1A1BB8, 2: 0x1B5330, 4: 0x1A5030, 5: 0x1A46C0, 6: 0x1BEAF0,
                     15: 0x11E870, 16: 0x3C3B38, 20: 0x1B5EA8, 27: 0x1B5D68, 29: 0x3C3B08,
                     30: 0x3C3B10, 37: 0x3C3B18})
SKELIGHT_SLOTS = dict(CREATURE_SLOTS)
SKELIGHT_SLOTS.update({0: 0x3CC6DC, 1: 0x3CC67C, 4: 0x2A8B84, 5: 0x2A8A64, 8: 0x2A90B0, 9: 0x2A8FDC,
                       15: 0x126B58, 27: 0x2A91B8})
TABLES = {VT_CREATURE: CREATURE_SLOTS, VT_PLAYER: PLAYER_SLOTS, VT_SKELIGHT: SKELIGHT_SLOTS}

# functions with an empty body (Observed: a bare return)
EMPTY_BODIES = {0x11A290: 'Creature_slot12', 0x3C7EF8: 'GameObject_default_slot12',
                0x3C3B10: 'Player_slot30', 0x3C3B08: 'Player_slot29'}


# =======================================================================================
# 5. Fixtures: what the caller authors (labelled so in every trace)
# =======================================================================================

MISS = 0xBF800000                       # -1.0: what a ray that hits nothing returns


class FlatTerrain:
    """An open floor at height z with no walls and no water.  AUTHORED: it stands in for
    tools/ref_world.py's terrain kernels, which need a level file.  Every answer is
    recorded as ('terrain', ...) so a trace never passes it off as the original's."""

    def __init__(self, z=0):
        self.z = z

    def height_below(self, pos, radius):
        return self.z

    def slide(self, pos, delta, mask, radius):
        return [C.add(pos[i], delta[i]) for i in range(3)], 0, (0, 0, 0)

    def raycast(self, origin, direction, mask, factor):
        return MISS

    def water_test(self, pos, radius):
        return 0


class AnimTimeline:
    """AUTHORED animation: tools/ref_anim.py owns the real clips.  A clip is a token (the
    word the class definition holds); `clips` maps a token to (length in ticks, {tick: event
    bits}).  anim_start* begins a clip: track count +0x118 = 1, flags +0x11a = 0x8 (playing).
    anim_advance on an active creature counts one tick, returns the bits scheduled for that
    tick and, at the end, clears 0x8 and sets 0x80 (ended).  No root motion."""

    def __init__(self, clips=None, default=(20, {})):
        self.clips = dict(clips or {})
        self.default = default
        self.state = {}                 # anim state address -> [clip, tick]

    def start(self, mem, anim, clip):
        self.state[anim] = [clip, 0]
        mem.poke(anim + 4, 1, 1)
        mem.poke(anim + 6, 2, 0x8)

    def advance(self, mem, anim):
        entry = self.state.get(anim)
        if entry is None:
            return 0
        length, events = self.clips.get(entry[0], self.default)
        entry[1] += 1
        bits = events.get(entry[1], 0)
        if entry[1] >= length:
            mem.poke(anim + 6, 2, (mem.load(anim + 6, 2) & ~0x8 & 0xFFFF) | 0x80)
        return bits


# =======================================================================================
# 6. Services: every name the executed models call out to, and nothing else
# =======================================================================================

class Services:
    """The callbacks dict of the models.  A name that is not listed here raises Unsupported:
    no callback silently answers zero.  Each entry is one of
        - an executed model's method (ref_objects, ref_creature, ref_arena_monsters,
          ref_combat) or a method of this module (Observed bodies, section 7),
        - a fixture answer (terrain, animation, skill statistics), traced as such,
        - presentation (sound, particles, effects, decals, music), traced and ignored."""

    PRESENTATION = ('fx_spawn', 'particle_spawn', 'sound_playOnObject', 'sound_playAtPos', 'decal_add',
                    'anim_releaseCaches', 'anim_snapTopToEnd', 'anim_jumpTopToEnd', 'anim_syncToSimFrame',
                    'creature_stopBossMusic', 'fx_burnModel', 'fx_shockModel', 'player_voice',
                    'gfx_setColorOffset', 'pad_rumble')

    def __init__(self, rt):
        self.rt = rt
        self.table = {}
        for name in self.PRESENTATION:
            self.table[name] = self._presentation(name)

    def _presentation(self, name):
        def fn(*args):
            self.rt.trace.append(('presentation', name))
            return 0
        return fn

    def _virtual(self, slot):
        """A virtual call-out (from ref_player.Tick, or a model meeting a function it has
        no body for): it runs when some model has the body, else it is refused."""
        def fn(this, *args):
            model = self.rt.model
            target = model.u32(model.u32(this + 0x48) + 8 * slot + 4)
            if not model.knows(target):
                raise Unsupported('virtual slot %d of 0x%x reaches 0x%x, which has no model' % (slot, this, target))
            return model.vcall(this, slot, *args)
        return fn

    def get(self, name):
        fn = self.table.get(name)
        if fn is None and name.startswith(('Creature.v', 'Player.v')):
            return self._virtual(int(name.split('.v')[1]))
        if fn is None:
            fn = getattr(self.rt, 'svc_' + name.replace('.', '_'), None)
        if fn is None:
            def refuse(*args):
                raise Unsupported('call-out %s is outside the contract' % name)
            return refuse
        return fn


# =======================================================================================
# 7. The model: ref_arena_monsters on the shared image, plus the bodies read for this
#    contract (Observed, docs/combat-runtime.md sections 5 and 6)
# =======================================================================================



class CombatModel(AM.Model):
    """ref_arena_monsters.Model (itself ref_creature.Model) whose callbacks are the
    runtime's services, extended with the base-class and player bodies that model leaves
    as call-outs."""

    # functions whose bodies this class has: function -> (slot, method), for virtual calls
    COMBAT_BODIES = {
        0x1B5330: (2, 'player_take_damage'), 0x1BEAF0: (6, 'player_on_touch'),
        0x1B5EA8: (20, 'player_is_enemy'), 0x3C3B18: (37, 'player_team'), 0x3C3B40: (39, 'player_skill_rank'),
    }
    # direct calls to functions this class has: name -> method.  They run here, as the
    # original's run inside the caller; naming one in `external` turns it into a call-out.
    INTERNAL = {
        'creature_canSeeObj': 'can_see_obj', 'Creature_hitTargetInArc': 'hit_target_in_arc',
        'Creature_hitAllEnemiesInArc': 'hit_all_enemies_in_arc', 'creature_findEnemyInCone': 'find_enemy_in_cone',
        'Creature_applyKnockback': 'apply_knockback', 'Creature_deadUpdate': 'dead_update',
        'Player_findTarget': 'player_find_target', 'Player_meleeHit': 'player_melee_hit',
        'Player_processDamage': 'player_process_damage', 'Player_move': 'player_move',
        'creature_moveSimple': 'move_simple', 'obj_moveWithCollision': 'move_with_collision',
    }
    MODELLED = {
        'creature_canSeeObj': 0x10C810, 'Creature_hitTargetInArc': 0x119938, 'Creature_hitAllEnemiesInArc': 0x119B58,
        'creature_findEnemyInCone': 0x10CF78, 'Creature_applyKnockback': 0x115EB8, 'Creature_deadUpdate': 0x1108A0,
        'Player_findTarget': 0x1BB3C8, 'Player_meleeHit': 0x1B6A98, 'Player_processDamage': 0x1B2CC0,
        'Player_move': 0x1B4020, 'creature_moveSimple': 0x1186D8, 'obj_moveWithCollision': 0x14D4B8,
        'Player_takeDamage': 0x1B5330, 'Player_onTouch': 0x1BEAF0, 'Player_isEnemy': 0x1B5EA8,
        'Player_slot37': 0x3C3B18, 'Player_slot39': 0x3C3B40,
    }

    def __init__(self, mem, callbacks=None, external=()):
        AM.Model.__init__(self, mem, callbacks, external)
        self.vcalls = []                # every virtual call, as ('Creature.v<slot>', (this, args...))

    def call(self, name, *args):
        method = self.INTERNAL.get(name)
        if method is not None and name not in self.external:
            return getattr(self, method)(*args)
        return AM.Model.call(self, name, *args)

    def knows(self, fn):
        """Whether a virtual call to `fn` runs a body of some model rather than a call-out."""
        return fn in AM.CLASS_BODIES or fn in self.COMBAT_BODIES or fn in EMPTY_BODIES or \
            any(base[0] == fn for base in RC.BASE_BODIES.values())

    def vcall(self, obj, slot, *args):
        """A virtual call through object +0x48: a body of ref_arena_monsters or
        ref_creature runs there, a body of COMBAT_BODIES here, an empty body does nothing;
        anything else is the call-out 'Creature.v<slot>'."""
        table = self.u32(obj + 0x48)
        fn = self.u32(table + 8 * slot + 4)
        this = (obj + self.s16(table + 8 * slot)) & M32
        self.vcalls.append(('Creature.v%d' % slot, (this,) + tuple(args)))
        body = self.COMBAT_BODIES.get(fn)
        if body is not None and ('Creature.v%d' % slot) not in self.external:
            return getattr(self, body[1])(this, *args)
        if fn in EMPTY_BODIES:
            return 0
        return AM.Model.vcall(self, obj, slot, *args)

    # ---- creature_canSeeObj 0x10c810 ---------------------------------------------------
    def can_see_obj(self, c, obj, facing, arc, ray_mode, near, far, lead):
        """creature_canSeeObj 0x10c810 (c, obj, facing, arc, rayMode; near, far, lead).

        Arc: |s16(atan2_16(v.y, v.x) - facing)| < arc, strict.  Range in 2-D with both
        radii: (d - obj.r) - c.r < far and near <= (d + obj.r) - c.r.  Line of sight: one
        terrain ray from half the creature's height along v (to the object's feet), mask 3
        when rayMode is 0 else 0, length factor 1.0999999; clear when t < 0 or 1.0 < t."""
        u32 = self.u32
        if not obj:
            return 0
        facing, arc = s16(facing), s16(arc)
        p = list(self.vec(obj + 0x10))
        if not C.eq(lead, ZERO) and u32(obj + 0xC) & 0x20:
            p[0] = C.add(p[0], C.mul(u32(obj + 0x308), lead))
            p[1] = C.add(p[1], C.mul(u32(obj + 0x30C), lead))
        cx, cy, cz = self.vec(c + 0x10)
        v = (C.sub(p[0], cx), C.sub(p[1], cy), C.sub(p[2], cz))
        delta = s16(C.atan2_16(v[1], v[0]) - facing)
        if not abs(delta) < arc:
            return 0
        ex, ey = C.sub(cx, p[0]), C.sub(cy, p[1])
        d = C.sqrt(C.add(C.mul(ex, ex), C.mul(ey, ey)))
        orad, crad = u32(obj + 0x1C), u32(c + 0x1C)
        if not C.lt(C.sub(C.sub(d, orad), crad), far):
            return 0
        if not C.le(near, C.sub(C.add(d, orad), crad)):
            return 0
        origin = (cx, cy, C.add(cz, C.mul(u32(c + 0x20), HALF)))
        t = self.call('terrain_raycast', u32(G_WORLD), origin, v, 0 if ray_mode else 3, 0x3F8CCCCC)
        return 1 if C.lt(t, ZERO) or C.lt(ONE, t) else 0

    # ---- the hit helpers -----------------------------------------------------------------
    def hit_target_in_arc(self, c, facing, arc, lo, hi, attack, flags, desc, near, far):
        """Creature_hitTargetInArc 0x119938 (near, far; c, facing, arc, min, max, attack,
        flags, desc) -> what damage_apply returns, or 0.  No target: 0.  The target must
        pass creature_canSeeObj (lead 0, ray mode 0); there is no enemy test and no dead
        test here.  damage_apply(f32(min), f32(max); target, c, attack, 0, 0, flags, desc,
        noCrit 0)."""
        node = self.u32(c + H_TARGET)
        if not node:
            return 0
        seen = self.call('creature_canSeeObj', c, self.u32(node + 0xC), s16(facing), s16(arc), 0,
                         near, far, ZERO)
        if not seen:
            return 0
        target = self.u32(self.u32(c + H_TARGET) + 0xC)
        return self.call('damage_apply', target, c, attack, 0, 0, flags, desc, 0,
                         C.from_int(s32(lo)), C.from_int(s32(hi)))

    def hit_all_enemies_in_arc(self, c, facing, arc, lo, hi, attack, flags, desc, near, far):
        """Creature_hitAllEnemiesInArc 0x119b58 (same arguments) -> 1 when any damage_apply
        returned non-zero.  ONE box query of +-1.4 far (0x3fb33333, single precision) on
        all three axes, limit 0x80, the exclude mask as it stands; then for each object in
        list order: slot 20 non-zero, creature_canSeeObj, damage_apply.  Damage is applied
        per candidate at once; the list is not re-queried."""
        h = C.mul(far, 0x3FB33333)
        x, y, z = self.vec(c + 0x10)
        low, high = (C.sub(x, h), C.sub(y, h), C.sub(z, h)), (C.add(x, h), C.add(y, h), C.add(z, h))
        found = self.call('world_collectObjectsInBox', low, high, 0x80)
        hit_any = 0
        for o in found:
            hit = 0
            if self.vcall(c, 20, o):
                if self.call('creature_canSeeObj', c, o, s16(facing), s16(arc), 0, near, far, ZERO):
                    hit = 1 if self.call('damage_apply', o, c, attack, 0, 0, flags, desc, 0,
                                         C.from_int(s32(lo)), C.from_int(s32(hi))) else 0
            if hit:
                hit_any = 1
        return hit_any

    def find_enemy_in_cone(self, c, facing, arc, near, far):
        """creature_findEnemyInCone 0x10cf78 (near, far; c, facing, arc) -> object or 0.

        bestD = far*far; h = single(double(far) * 1.4) through the soft doubles; one box
        query of +-h on all axes, limit 0x80.  Per object: score = slot 20; skip at 0; skip
        when the 3-D squared distance is below near*near; skip when |s16(s16(0x4000 -
        atan2_16(v.x, v.y)) - facing)| > arc (inclusive); skip when a terrain ray (mask 3,
        from the creature's full height along v, which ends at the object's half height
        plus the creature's) gives 0 <= t <= 1.  Score +1 when nearer than the best so far,
        +1 for the last attacker, +1 for the current target; taken on a higher score or an
        equal score and a smaller distance.  far bounds only the start of bestD: an object
        beyond it is taken when its score is higher."""
        u32 = self.u32
        facing, arc = s16(facing), s16(arc)
        best_d = C.mul(far, far)
        h = RB.dbl_to_single(RB.dbl_mul(RB.dbl_from_single(far), _DOUBLE_1_4))
        x, y, z = self.vec(c + 0x10)
        found = self.call('world_collectObjectsInBox', (C.sub(x, h), C.sub(y, h), C.sub(z, h)),
                          (C.add(x, h), C.add(y, h), C.add(z, h)), 0x80)
        best, best_score = 0, 0
        near2 = C.mul(near, near)
        for o in found:
            score = s32(self.vcall(c, 20, o))
            if not score:
                continue
            ox, oy, oz = self.vec(o + 0x10)
            cx, cy, cz = self.vec(c + 0x10)
            dx, dy, dz = C.sub(cx, ox), C.sub(cy, oy), C.sub(cz, oz)
            d2 = C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz))
            if C.lt(d2, near2):
                continue
            ctop = C.add(cz, C.mul(u32(c + 0x20), HALF))
            v = (C.sub(ox, cx), C.sub(oy, cy), C.sub(C.add(oz, C.mul(u32(o + 0x20), HALF)), ctop))
            delta = s16(s16(0x4000 - C.atan2_16(v[0], v[1])) - facing)
            if arc < abs(delta):
                continue
            origin = (cx, cy, C.add(cz, u32(c + 0x20)))
            t = self.call('terrain_raycast', u32(G_WORLD), origin, v, 3, 0x3F8CCCCC)
            if C.le(ZERO, t) and C.le(t, ONE):
                continue
            if C.lt(d2, best_d):
                score += 1
            if u32(c + H_LAST_ATTACKER) and self.handle_obj(c + H_LAST_ATTACKER) == o:
                score += 1
            if u32(c + H_TARGET) and self.handle_obj(c + H_TARGET) == o:
                score += 1
            if best_score < score or (score == best_score and C.lt(d2, best_d)):
                best, best_d, best_score = o, d2, score
        return best

    # ---- Creature_applyKnockback 0x115eb8 ---------------------------------------------
    def apply_knockback(self, c, scale):
        """Creature_applyKnockback 0x115eb8 (c; scale).

        A player in a net game or in PvP mode B: speed +0x2e8 = 0 and nothing else.
        Otherwise, with 0 < scale, speed != 0 and object flag 2 clear: velocity =
        (cos16(+0x2e0) x speed x scale, sin16(+0x2e0) x speed x scale, 0); the root motion
        (+0xbc, 8 bytes) and root yaw (+0xc4) are saved, zeroed, Creature_moveBy runs - its
        contact loop and slot-6 calls included - and both are put back; speed -= 2 while
        positive, floored at 0.  When the move neither slid nor touched (bits & 3 == 0)
        and creature flags 0x2000000000100000 (in water, or bit 20) are clear: two dust
        puffs, each made of OWN-generator draws (three for a spot, triples until a point of
        the unit ball, three for a jitter) and one presentation call."""
        u32, w32 = self.u32, self.w32
        flags = u32(c + 0xC)
        if flags & 0x40 and (self.s8(G_NETWORK_MODE) or u32(0x4F7120)):
            w32(c + 0x2E8, 0)
            return
        if not C.lt(ZERO, scale) or C.eq(u32(c + 0x2E8), ZERO) or flags & 2:
            return
        speed = u32(c + 0x2E8)
        vx = C.mul(C.mul(C.cos16(self.s16(c + 0x2E0)), speed), scale)
        vy = C.mul(C.mul(C.sin16(self.s16(c + 0x2E0)), speed), scale)
        saved_root = self.u64(c + 0xBC)
        self._w(c + 0xBC, 8, 0)
        saved_yaw = self.u16(c + 0xC4)
        self.w16(c + 0xC4, 0)
        bits = self.move_by(c, (vx, vy, ZERO))
        self._w(c + 0xBC, 8, saved_root)
        self.w16(c + 0xC4, saved_yaw)
        speed = u32(c + 0x2E8)
        if C.lt(ZERO, speed):
            speed = C.sub(speed, 0x40000000)
            w32(c + 0x2E8, speed)
        if C.lt(speed, ZERO):
            w32(c + 0x2E8, ZERO)
        if self.u64(c + 0xA8) & 0x2000000000100000 or bits & 3:
            return
        radius_unit = 0x37800000
        for _puff in range(2):
            r = u32(c + 0x1C)
            spot = [ZERO, ZERO, ZERO]
            d = self.obj_rand(c)
            spot[0] = C.add(C.sub(u32(c + 0x10), C.mul(r, HALF)), C.from_int(_c_rem(d, C.to_int(r))))
            d = self.obj_rand(c)
            r = u32(c + 0x1C)
            spot[1] = C.add(C.sub(u32(c + 0x14), C.mul(r, HALF)), C.from_int(_c_rem(d, C.to_int(r))))
            d = self.obj_rand(c)
            spot[2] = C.add(u32(c + 0x18), C.from_int(d % 10))
            while True:
                ball = []
                for _axis in range(3):
                    u = C.mul(C.from_int(self.obj_rand(c)), radius_unit)
                    ball.append(C.sub(C.add(u, u), ONE))
                size = C.add(C.add(C.mul(ball[0], ball[0]), C.mul(ball[1], ball[1])), C.mul(ball[2], ball[2]))
                if not C.lt(ONE, size):
                    break
            ball = [C.mul(b, 0x41273333) for b in ball]
            at = [C.add(C.from_int(self.obj_rand(c) % 12 - 6), spot[i]) for i in range(3)]
            if u32(RC.G_LEVEL_FLAGS) & 0x100:
                self.call('fx_spawn', 0x11, tuple(at))
            else:
                self.call('particle_spawn', 0x4F8710, tuple(at), tuple(ball), ZERO)

    # ---- Creature_deadUpdate 0x1108a0 --------------------------------------------------
    def dead_update(self, c, events, offset, hold, size):
        """Creature_deadUpdate 0x1108a0 (size; c, events, &offset, hold).

        Creature flag 0x1000000 (sinking corpse): object flag 0x4000 every call; until the
        death clip has ended (+0x11a & 0x80) only +0x2f4 is reset (when hold is 0); with
        hold 0 it then sinks 0.35 a call (+0x2f4, drawn height +0x3c) and is obj_delete'd
        once the sink exceeds the height.  Otherwise: a blood decal (two own draws, only
        when one of four creature-flag blood types is set, events & 0x80, object flag 2
        clear, size > 0 and hold 0), and with hold set obj_delete once the clip has ended
        with one track left."""
        u32 = self.u32
        cf = self.u64(c + 0xA8)
        if cf & 0x1000000:
            self.w32(c + 0xC, u32(c + 0xC) | 0x4000)
            if not self.u16(c + 0x11A) & 0x80:
                if not hold:
                    self.w32(c + 0x2F4, ZERO)
                return
            if hold:
                return
            sink = C.add(u32(c + 0x2F4), 0x3EB33333)
            self.w32(c + 0x2F4, sink)
            self.w32(c + 0x3C, C.sub(u32(c + 0x18), sink))
            if C.lt(u32(c + 0x20), u32(c + 0x2F4)):
                self.w32(c + 0xC, u32(c + 0xC) | 0x4002)
                self.call('obj_delete', c)
            return
        if events & 0x80 and not u32(c + 0xC) & 2 and C.lt(ZERO, size) and not hold:
            for bit, kind in ((0x1000, 6), (0x2000, 3), (0x4000, 0xA), (0x40000, 0)):
                if cf & bit:
                    raise Unsupported('blood decal of a corpse (two own draws): not in the domain')
        if self.u64(c + 0x118) & 0x8000FF == 0x800001 and hold:
            self.call('obj_delete', c)

    # =====================================================================================
    # Player bodies (Observed; docs/combat-runtime.md section 6).  Every callee by name.
    # =====================================================================================
    def _rec(self, P):
        return (G_PLAYERS + self.s32(P + 0x3C8) * REC_SIZE) & M32

    def _cstr(self, addr, limit=32):
        out = bytearray()
        while len(out) < limit:
            b = self.u8(addr + len(out))
            if not b:
                break
            out.append(b)
        return bytes(out)

    def player_team(self, P):
        """Player_slot37 0x3c3b18: the record's team byte +0x4c24 (signed)."""
        return self.s8(self._rec(P) + 0x4C24) & M32

    def player_skill_rank(self, P, skill):
        """Player slot 39, 0x3c3b40: player_getSkillRank(P+0x3c8, id) (a tail call)."""
        return self.call('player_getSkillRank', self.u32(P + 0x3C8), skill)

    def player_is_enemy(self, P, o):
        """Player_isEnemy 0x1b5ea8 (P, o) -> 0 or 1.  0 for itself, for an object without
        flag 0x20, with flag 8 or 0x1000000, or with creature flag 0x4000000 or 0x800.
        Another player: only in PvP mode A, when the record team bytes differ.  A creature:
        1 when its charm timer +0x312 is 0; a charmed one only in PvP mode A with a team
        byte >= 0 that differs from the player's."""
        if o == P:
            return 0
        flags = self.u32(o + 0xC)
        if not flags & 0x20 or flags & 8 or flags & 0x1000000:
            return 0
        if self.u64(o + 0xA8) & 0x4000800:
            return 0
        pvp = self.u32(G_PVP_MODE_A)
        if flags & 0x40:
            if not pvp:
                return 0
            return 1 if self.s8(self._rec(o) + 0x4C24) != self.s8(self._rec(P) + 0x4C24) else 0
        if self.s16(o + 0x312) == 0:
            return 1
        if not pvp:
            return 0
        team = self.s8(o + 0x310)
        if team < 0:
            return 0
        return 1 if team != self.s8(self._rec(P) + 0x4C24) else 0

    def player_on_touch(self, P, other):
        """Player_onTouch 0x1beaf0: nothing for the prediction copy or outside action state
        9 (the rush, SpellCharge, not in the domain)."""
        if self.u32(P + 0xC) & F_PREDICTION_COPY or self.s32(P + 0x58C) != 9:
            return
        raise Unsupported('Player_onTouch in state 9 (SpellCharge_onContact)')

    def player_take_damage(self, P, attacker, flags, amount):
        """Player_takeDamage 0x1b5330, slot 2 (P, attacker, flags; amount).

        Early returns, in order: g_recallCountdown, spawn protection +0x4b4, a vehicle
        +0x540, the level 'actintro', jumpgate_getTravelState(), g_menuInputLockout,
        g_exitCountdown.  With g_localMenuOpen and a local slot: gfx_setColorOffset (the
        tint).  Hit immunity R+0x4c27 > 0: the HUD flash bit and nothing else.  Block
        (attacker, action state 8 or 0xb, flag 0x40 clear) is outside the domain (state 8:
        one shared draw for the clip; an attacker in front: Player_blockSparks, not read).
        A Holy Shield (looked up on every hit) is outside the domain.  Then pending +0xc8
        += amount and +0x2dc |= flags - hit points are NOT changed here (record +0xac, in
        Player_processDamage).  With an attacker: unless the new flags have 0x800000 the
        hit angle +0x2e0 = 0x4000 - atan2_16(P.x - A.x, P.y - A.y); the last-attacker
        handle +0x2e4 is relinked on EVERY hit (no hit-point guard).  Pending > 0: the HUD
        flash bit.  No prediction-copy test."""
        u32 = self.u32
        if self.s8(G_RECALL_COUNTDOWN) or self.s16(P + 0x4B4) or u32(P + 0x540):
            return
        if self._cstr(G_LEVEL_NAME) == b'actintro':
            return
        if self.call('jumpgate_getTravelState'):
            return
        if u32(G_MENU_LOCKOUT) or self.s16(G_EXIT_COUNTDOWN):
            return
        slot = self.s32(P + 0x3C8)
        if self.s8(0x41B69D) and self.call('net_isLocalSlot', slot):
            self.call('gfx_setColorOffset', 0x40, 0, 0, 0)
        R = self._rec(P)
        flash = (G_HUD_HIT_FLASH + 4 * slot) & M32
        if self.s8(R + 0x4C27) > 0:
            self.w32(flash, u32(flash) | 1)
            return
        state = self.s32(P + 0x58C)
        if attacker and state in (8, 0xB) and not flags & 0x40:
            raise Unsupported('a blocking player (block clip choice, Player_blockSparks)')
        if self.call('creature_findSpellByType', P, self.call('SpellHolyShield_typeinfo')):
            raise Unsupported('a Holy Shield')
        self.w32(P + 0xC8, C.add(u32(P + 0xC8), amount))
        df = u32(P + 0x2DC) | flags
        self.w32(P + 0x2DC, df)
        if attacker:
            if not df & 0x800000:
                angle = C.atan2_16(C.sub(u32(P + 0x10), u32(attacker + 0x10)),
                                   C.sub(u32(P + 0x14), u32(attacker + 0x14)))
                self.w16(P + 0x2E0, 0x4000 - angle)
            self.call('handle_clear', P + H_LAST_ATTACKER)
            src = attacker
            if u32(attacker + 0xC) & F_OWNED:
                node = u32(attacker + H_OWNER)
                if node:
                    src = u32(node + 0xC)
            elif flags & 0x10000000:
                node = u32(P + H_STATUS_SOURCE)
                if node:
                    src = u32(node + 0xC)
            if src:
                self.call('handle_link', P + H_LAST_ATTACKER, src, src)
        if C.lt(ZERO, u32(P + 0xC8)):
            self.w32(flash, u32(flash) | 1)

    def _track_fixup(self, P):
        """Before a reaction clip (e.g. 0x1b3834-0x1b3884): with five or more tracks the top
        track's life rate becomes -1/12 and its life is capped at 1.0."""
        n = self.s8(P + 0x118)
        if n >= 5:
            self.w32(P + 0x110 + 32 * n, 0xBDAAAAAA)
            a = P + 0x10C + 32 * n
            if C.lt(ONE, self.u32(a)):
                self.w32(a, ONE)

    def _reaction_clip(self, P):
        cls = self.s8(self._rec(P) + 0x4A86)
        self.call('anim_startBlendInOut', P + 0x114, self.u32(self.u32(P + 0x24) + 0x68 * cls + 0x7C), 0xA,
                  0x3DCCCCCC, 0x3DCCCCCC)

    def _set_state3(self, P):
        self.w32(P + 0x58C, 3)
        self.w32(P + 0x448, self.u32(G_SIM_FRAME))
        if self.call('net_isLocalSlot', self.u32(P + 0x3C8)):
            self.w8(G_FORCE_GHOST_REBASE, 1)
        self.call('player_voice', self.u32(P + 0x3C8), 0xC)

    def player_process_damage(self, P):
        """Player_processDamage 0x1b2cc0 (P), restricted.  In order:

        A  unless +0x2dc has 0x20000000: in a cutscene or with a dialog open, pending and
           flags are dropped.
        B  flags & 0x3c0000 and action state not 6 or 10: rank of skill 0x3e (slot 39),
           SkillStrongStance stat 0, ONE SHARED DRAW, resist = draw % 100 < stat; knock-back
           speed +0x2e8 100 / 150 / 200 / 250 and level 1 / 2 / 3 / 3 for the first of
           0x40000, 0x80000, 0x100000, 0x200000.  Level <= 0: on to C.  Blocking with the
           attacker in front: level - 1.  level < 2 or not resist: action state 3.  level < 2:
           unless 0x400000, the small reaction clip.  The knock-down (level >= 2) is outside
           the domain.
        C  pending <= 0 or action state 4: flags dropped, pending KEPT.  Record hit points
           -= pending.  (Blood and gibs need g_decalDetail or a net game: outside.)  pending
           = 0, object flag 0x100.
        D  hit points <= 0 (no Resurrect spell): hit points = 0, flag 8; a held spell is
           outside the domain; the death clip; action state 4, +0x448 = frame, flag 1;
           game_rebuildAlivePlayers AT ONCE; local: net_closeLocalMenus, ghost rebase; with
           two or more players the other of slots 0 / 1 shouts when alive.  The object stays
           in the world (never deleted).  Flags dropped.
        E  survived, unless 0x400000, action state 3 or 7, or a heavy attack (+0x44c == 2):
           ONE SHARED DRAW; stagger when draw < (max(0.04 - R+0xdc x 0.04, 0)) x 65536 or
           flags & 0x4000000; then (not in action state 6 or 10) action state 3 and the
           reaction clip.  Flags dropped."""
        u32 = self.u32
        R = self._rec(P)
        if not u32(P + 0x2DC) & 0x20000000 and (self.s8(G_CUTSCENE_ACTIVE) or self.call('dialog_isOpen')):
            self.w32(P + 0x2DC, 0)
            self.w32(P + 0xC8, 0)
            return
        df = u32(P + 0x2DC)
        rel = s16(self.u16(P + 0x2E0) - self.u16(P + 0x38))
        level = resist = 0
        state = self.s32(P + 0x58C)
        if df & 0x3C0000 and state not in (6, 10):
            rank = self.vcall(P, 39, 0x3E)
            pct = s32(self.call('SkillStrongStance_getStat0', u32(G_SKILL_STRONGSTANCE), rank))
            df = u32(P + 0x2DC)
            resist = 1 if (self.draw() % 100) < pct else 0
            for bit, speed, lv in ((0x40000, 0x42C80000, 1), (0x80000, 0x43160000, 2),
                                   (0x100000, 0x43480000, 3), (0x200000, 0x437A0000, 3)):
                if df & bit:
                    self.w32(P + 0x2E8, speed)
                    level = lv
                    break
        if u32(G_PVP_MODE_A):
            raise Unsupported('PvP mode A')
        if level > 0:
            if state == 8 and not -0x5FFF <= rel < 0x6000:
                level -= 1
            small = level < 2
            if small or not resist:
                self._set_state3(P)
            if not small:
                raise Unsupported('the knock-down reaction (Player_hasAnim, SkillStrongStance_trigger)')
            if not u32(P + 0x2DC) & 0x400000:
                self._track_fixup(P)
                self._reaction_clip(P)
        # C
        if not C.lt(ZERO, u32(P + 0xC8)) or self.s32(P + 0x58C) == 4:
            self.w32(P + 0x2DC, 0)
            return
        df = u32(P + 0x2DC)
        if u32(G_DEBUG_INVULNERABLE) and not df & 0x20000000:
            self.w32(P + 0xC8, ZERO)
        self.w32(R + 0xAC, C.sub(u32(R + 0xAC), u32(P + 0xC8)))
        if (self.s32(G_DECAL_DETAIL) > 0 or self.s8(G_NETWORK_MODE)) and df & 0xD:
            raise Unsupported('player blood and gibs (decal option or net game: one shared draw)')
        if df & 0x10 and C.le(u32(R + 0xAC), ZERO):
            raise Unsupported('disintegration')
        self.w32(P + 0xC8, 0)
        self.w32(P + 0xC, u32(P + 0xC) | 0x100)
        if C.le(u32(R + 0xAC), ZERO):
            # D
            if self.call('creature_findSpellByType', P, self.call('SpellResurrect_typeinfo')):
                raise Unsupported('a Resurrect spell')
            self.w32(R + 0xAC, ZERO)
            self.w32(P + 0xC, u32(P + 0xC) | 8)
            node = u32(P + 0x588)
            if node and u32(node + 0xC):
                raise Unsupported('a held spell is destroyed on death')
            model = self.s32(R + 0x54)
            offset = 0x14 if (model in (0, 1, 4, 5, 8, 9, 10, 11) and self.s8(R + 0x4A86) == 2) else 0xC
            self.call('anim_start', P + 0x114, u32(u32(P + 0x24) + offset), 0x206, HALF)
            self.w32(P + 0x58C, 4)
            self.w32(P + 0x448, u32(G_SIM_FRAME))
            self.w32(P + 0xC, u32(P + 0xC) | 1)
            self.call('game_rebuildAlivePlayers')
            if self.call('net_isLocalSlot', u32(P + 0x3C8)):
                self.call('net_closeLocalMenus', 1)
                self.w8(G_FORCE_GHOST_REBASE, 1)
            if self.s32(G_NUM_PLAYERS) >= 2:
                other = 1 if self.u32(P + 0x3C8) == 0 else 0
                if C.lt(ZERO, u32(G_PLAYERS + other * REC_SIZE + 0xAC)) and not u32(G_PVP_MODE_A):
                    self.call('player_voice', other, 3)
            if u32(G_PVP_MODE_B):
                raise Unsupported('PvP mode B (arena lives)')
            self.w32(P + 0x2DC, 0)
            return
        # E
        df = u32(P + 0x2DC)
        state = self.s32(P + 0x58C)
        if df & 0x400000 or state in (3, 7) or self.s32(P + 0x44C) == 2:
            self.w32(P + 0x2DC, 0)
            return
        chance = C.sub(0x3D23D70A, C.mul(u32(R + 0xDC), 0x3D23D70A))
        if C.lt(chance, ZERO):
            chance = ZERO
        if C.lt(C.from_int(self.draw()), C.mul(chance, 0x47800000)) or u32(P + 0x2DC) & 0x4000000:
            if self.s32(P + 0x58C) not in (6, 10):
                self._set_state3(P)
                self._track_fixup(P)
                self._reaction_clip(P)
        self.w32(P + 0x2DC, 0)

    def player_find_target(self, P, reach):
        """Player_findTarget 0x1bb3c8 (reach; P): the target handle +0x234 of a bow or
        thrown-weapon player.  A level whose name contains 'stomedal': nothing at all.
        Box (+-reach, +-reach, +-72) limit 0x100; +0x4b8 cleared.  Candidates: not P, flags
        & 0x49 clear, flag 0x20 set (so never another player), charm timer 0; n = the 2-D
        unit vector to it, dot = n . (cos16, sin16)(facing); skip dot < 0.5; edge = dist -
        o.radius, skip reach <= edge; skip when a terrain ray (mask 0, length 1.0) from 36
        above P along the 3-D difference gives t >= 0; score = edge - dot x 32; the lowest
        score wins, ties to the later.  +0x234 is cleared even when nothing is found.

        (The cone and range rejects branch to the loop test past the address computation
        at 0x1bb690; the pointer is already right because the delay slot of the branch at
        0x1bb52c, which is not a branch-likely, computed it.  Executed.)"""
        u32 = self.u32
        if b'stomedal' in self._cstr(G_LEVEL_NAME):
            return
        fx, fy = C.cos16(self.s16(P + 0x38)), C.sin16(self.s16(P + 0x38))
        px, py, pz = self.vec(P + 0x10)
        found = self.call('world_collectObjectsInBox', (C.sub(px, reach), C.sub(py, reach), C.sub(pz, 0x42900000)),
                          (C.add(px, reach), C.add(py, reach), C.add(pz, 0x42900000)), 0x100)
        self.call('handle_clear', P + H_SWEEP)
        best, best_score = 0, 0x551184E7
        for o in found:
            if o == P:
                continue
            flags = u32(o + 0xC)
            if flags & 0x49 or not flags & 0x20 or self.s16(o + 0x312):
                continue
            px, py, pz = self.vec(P + 0x10)
            dx, dy = C.sub(u32(o + 0x10), px), C.sub(u32(o + 0x14), py)
            dist = C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy)))
            inv = C.div(ONE, dist)
            dot = C.add(C.mul(C.mul(dx, inv), fx), C.mul(C.mul(dy, inv), fy))
            if C.lt(dot, HALF):
                continue
            edge = C.sub(dist, u32(o + 0x1C))
            if C.le(reach, edge):
                continue
            score = C.sub(edge, C.mul(dot, 0x42000000))
            ox, oy, oz = self.vec(o + 0x10)
            t = self.call('terrain_raycast', u32(G_WORLD), (C.add(px, ZERO), py, C.add(pz, 0x42100000)),
                          (C.sub(ox, px), C.sub(oy, py), C.sub(oz, pz)), 0, ONE)
            if C.le(ZERO, t) or C.lt(best_score, score):
                continue
            best, best_score = o, score
        self.call('handle_clear', P + H_TARGET)
        if best:
            self.call('handle_link', P + H_TARGET, best, best)

    def player_melee_hit(self, P, target, a2, extra, scale):
        """Player_meleeHit 0x1b6a98 (scale; P, target, unused, extra flags), restricted to
        an unarmed player without spells and scale 0.

        Nothing for the prediction copy.  Line of sight (scale 0 only): a terrain ray
        (mask 0, length 1.0) from 36 above P along the 3-D difference; t >= 0 refuses the
        hit unless the target is an AutoProp (outside the domain).  No weapon: flags 1,
        Player_recalcDamage(P, 0, 0); flag 0x1000 for weapon class 1 after 60 frames;
        knock-back class 0x40000 (0x80000 with a scale, or a long weapon after 60 frames).
        A heavy attack (+0x44c == 2) is outside the domain (the record's range raised in
        place, Player_hitSparks).  SpellHarmTouch is looked up.  Then ONE damage_apply(
        f32(R+0xd0), f32(R+0xd4); target, P, R+0xcc, 0, 0, flags | extra, weapon (0),
        noCrit 0); the record's values are left as written.  A hit on a creature sets the
        trail's hit material and its 5-frame timer (R+0x4ac5 / +0x4ac6)."""
        u32 = self.u32
        if u32(P + 0xC) & F_PREDICTION_COPY:
            return
        R = self._rec(P)
        if C.eq(scale, ZERO):
            px, py, pz = self.vec(P + 0x10)
            tx, ty, tz = self.vec(target + 0x10)
            t = self.call('terrain_raycast', u32(G_WORLD), (px, py, C.add(pz, 0x42100000)),
                          (C.sub(tx, px), C.sub(ty, py), C.sub(tz, pz)), 0, ONE)
            if C.le(ZERO, t):
                raise Unsupported('a blocked melee line of sight (the AutoProp exception)')
        else:
            raise Unsupported('a scaled melee hit (SpellCyclone)')
        if u32(R + 0x43F0) and u32(R + 0x43F4):
            raise Unsupported('two hands (dual wield)')
        weapon = u32(R + 0x4434 + 4 * self.s8(R + 0x4A7C))
        self.call('Player_recalcDamage', P, weapon, 0)
        if weapon:
            raise Unsupported('an armed player (weapon items are outside the domain)')
        flags = 1
        since = C.from_int(s32(u32(G_SIM_FRAME) - u32(P + 0x448)))
        cls = self.s8(R + 0x4A86)
        if cls == 1 and C.le(0x42700000, since):
            flags |= 0x1000
        knock = 0x40000
        if cls == 3 and C.le(0x42700000, since):
            knock = 0x80000
        flags |= knock
        if self.s32(P + 0x44C) == 2:
            raise Unsupported('the heavy attack (Player_hitSparks)')
        dmin, dmax = self.s32(R + 0xD0), self.s32(R + 0xD4)
        if self.call('creature_findSpellByType', P, self.call('SpellHarmTouch_typeinfo')):
            raise Unsupported('SpellHarmTouch')
        result = self.call('damage_apply', target, P, u32(R + 0xCC), 0, 0, (flags | extra) & M32, 0, 0,
                           C.from_int(dmin), C.from_int(dmax))
        if result and u32(target + 0xC) & 0x20:
            cf = self.u64(target + 0xA8)
            m = 3 if cf & 0x2000 else 2 if cf & 0x1000 else 1 if cf & 0x40000 else 0
            self.w8(R + 0x4AC5, m)
            self.w8(R + 0x4AC6, 5)

    def player_move(self, P, mode, pad, ext=0):
        """Player_move 0x1b4020 (P, mode, pad, vec), restricted to a STILL stick (pad +0x14,
        +0x18 zero) and the modes Player_run uses for a standing or swinging player: 0
        (state 2), 3 and 4 (state 1).  docs/spec/movement-camera.md 4.1, re-read at
        0x1b4794-0x1b4b88 for mode 0:

          s = 0, so no turn and cs = cc = 0; the water test on frames with frame & 3 == 0.
          mode 0: rate 0; the blend weight +0x46c falls by 0.1 (floored at 0); with it below
            0.05 Player_animStep(1.0) and no event bits, else Player_animStep(rate) & 1
            (s < 0.6; the soft-double comparison made there is discarded); the ramp +0x468;
            track weights 1..3 (+0x144/+0x14c = w, +0x164/+0x16c and +0x184/+0x18c from the
            soft doubles with 0.45 and 0.7 as the executable holds them); the camera yaw
            round trip V = A x (cc x -180) + B x (cs x 180), x1.25 airborne; +0x4bc, +0x4c0.
          modes 3, 4: V = 0; mode 4 also zeroes +0x46c and the six blend fields.
          then: +0x490 = 0 unless a heavy attack; the slow factor; the move proper W = V +
            root x 60 through creature_moveSimple -> obj_moveWithCollision(P, W, 0, 0);
            root = 0; the bookkeeping of 4.1(m).
        Returns the event bits (mode 0 only)."""
        u32 = self.u32
        if mode not in (0, 3, 4):
            raise Unsupported('Player_move mode %d is not in this contract' % mode)
        if u32(pad + 0x14) or u32(pad + 0x18) or self.u8(P + 0x481):
            raise Unsupported('a moving stick (turning and walking are not in this contract)')
        if self.s16(P + 0x31A) > 0:
            if self.call('creature_findSpellByType', P, self.call('SpellDrowsy_typeinfo')):
                raise Unsupported('SpellDrowsy')
        s = ZERO
        ev = 0
        if not self.u64(P + 0xA8) & (1 << 61) and not u32(G_SIM_FRAME) & 3:
            if self.call('water_test', u32(G_WORLD), self.vec(P + 0x10), 0, 0x41400000):
                raise Unsupported('a player entering water')
        v = [ZERO, ZERO, ZERO]
        if mode == 0:
            rate = C.mul(s, 0x4014D653)
            w = C.sub(u32(P + 0x46C), 0x3DCCCCCC)
            self.w32(P + 0x46C, w)
            if C.lt(w, ZERO):
                self.w32(P + 0x46C, ZERO)
            if C.lt(rate, 0x3C23D70A) and C.lt(u32(P + 0x46C), 0x3D4CCCCC):
                self.call('Player_animStep', P, ONE)
            else:
                ev = s8(self.call('Player_animStep', P, rate)) & 1
            prev = u32(P + 0x468)
            if C.lt(C.sub(prev, s), 0xBD4CCCCC):
                s = C.add(prev, 0x3D4CCCCC)
            w = u32(P + 0x46C)
            self.w32(P + 0x14C, w)
            self.w32(P + 0x144, w)
            wd, sd = RB.dbl_from_single(w), RB.dbl_from_single(s)
            t2 = RB.dbl_to_single(RB.dbl_mul(RB.dbl_mul(wd, RB.dbl_add(sd, -D_045)), D_3))
            self.w32(P + 0x164, t2)
            self.w32(P + 0x16C, t2)
            t3 = RB.dbl_to_single(RB.dbl_mul(RB.dbl_mul(wd, RB.dbl_add(sd, -D_07)), D_3))
            self.w32(P + 0x468, s)
            self.w32(P + 0x184, t3)
            self.w32(P + 0x18C, t3)
            yaw = s32(self.call('net_getCamYaw', u32(P + 0x3C8)))
            a1, a2 = -yaw - 0x4000, -yaw - 0x8000
            A = (C.neg(C.cos16(a1)), C.neg(C.sin16(a1)), ZERO)
            B = (C.neg(C.cos16(a2)), C.neg(C.sin16(a2)), ZERO)
            p, q = C.mul(ZERO, 0xC3340000), C.mul(ZERO, 0x43340000)          # cc x -180, cs x 180
            v = [C.add(C.mul(A[i], p), C.mul(B[i], q)) for i in range(3)]
            if self.u8(P + 0x47E) and self.u8(P + 0x47C):
                v = [C.mul(x, 0x3FA00000) for x in v]
            self.w32(P + 0x4BC, v[0])
            self.w32(P + 0x4C0, v[1])
        elif mode == 4:
            for off in (0x46C, 0x144, 0x14C, 0x164, 0x16C, 0x184, 0x18C):
                self.w32(P + off, 0)
        if self.s32(P + 0x44C) != 2:
            self.w8(P + 0x490, 0)
        slow = self.u8(P + 0x2FC)
        k = C.mul(C.from_int(60 - s8(slow)), RC.DT) if 1 <= slow <= 60 else None
        if k is not None:
            v = [C.mul(x, k) for x in v]
        if self.s32(G_NUM_PLAYERS) >= 2 and self.s32(G_ALIVE_COUNT) >= 2 and not self.s8(G_NETWORK_MODE):
            raise Unsupported('the offline screen clamp (two or more players alive)')
        w3 = (C.add(v[0], C.mul(u32(P + 0xBC), 0x42700000)), C.add(v[1], C.mul(u32(P + 0xC0), 0x42700000)), v[2])
        bits = self.call('creature_moveSimple', P, w3)
        self.w32(P + 0xBC, 0)
        self.w32(P + 0xC0, 0)
        if bits & 3:
            self.w8(P + 0x490, bits)
        if bits & 2 and self.call('net_isLocalSlot', u32(P + 0x3C8)) and not u32(P + 0xC) & F_PREDICTION_COPY:
            self.w8(G_FORCE_GHOST_REBASE, 1)
        if bits & 3 == 0:
            vx, vy = u32(P + 0x4BC), u32(P + 0x4C0)
            if k is not None:
                vx, vy = C.mul(vx, k), C.mul(vy, k)
            self.w32(P + 0x308, vx)
            self.w32(P + 0x30C, vy)
        else:
            self.w32(P + 0x308, 0)
            self.w32(P + 0x30C, 0)
        if bits & 4:
            self.w8(P + 0x482, 15)
            if self.u8(P + 0x47D):
                raise Unsupported('a landing (footstep, state 2)')
        elif self.u8(P + 0x482):
            self.w8(P + 0x482, self.u8(P + 0x482) - 1)
        return ev

    def move_simple(self, obj, vel):
        """creature_moveSimple 0x1186d8 (obj, vel): obj_moveWithCollision(obj, copy, 0, 0)."""
        return self.move_with_collision(obj, vel, 0, 0)

    def move_with_collision(self, obj, vel, ignore, skip_creatures):
        """obj_moveWithCollision 0x14d4b8 (obj, vel, ignore, skipCreatures) -> bits (1 slid,
        2 pushed out, 4 landed).  d = vel x DT; above 0.001 (3-D) a slide with mask 5
        (player), 3 (creature) or 1, then an inline copy of obj_updateGridCell.  ONE box
        query (+-r, +-r, +-1000), limit 0x40.  Per object in list order: skip flag 1,
        itself, `ignore`, a creature with skipCreatures; overlap in 2-D (dist + 0.001 < r +
        o.r); the stand-on rule when either has flag 0x10; a push-out (mask 1, relink, bit 2)
        unless o has 0x200, the mover 0x400 or dist <= 0.001; then TOUCH: the other's slot
        6 with the mover (skipped when the MOVER is the prediction copy), then the mover's
        own slot 6 with the other.  No break.  Then ground and gravity."""
        u32 = self.u32
        DT = RC.DT
        d = (C.mul(vel[0], DT), C.mul(vel[1], DT), C.mul(vel[2], DT))
        bits = 0
        flags = u32(obj + 0xC)
        if C.lt(0x3A83126E, C.add(C.add(C.mul(d[0], d[0]), C.mul(d[1], d[1])), C.mul(d[2], d[2]))):
            mask = 1
            if flags & 0x20:
                mask = 3
            if flags & 0x40:
                mask = (mask | 4) & 5
            bits = 1 if self.call('world_slideMove', obj + 0x10, d, mask, 0, u32(obj + 0x1C)) else 0
            self.call('obj_updateGridCell', obj)
        r = u32(obj + 0x1C)
        x, y, z = self.vec(obj + 0x10)
        found = self.call('world_collectObjectsInBox', (C.sub(x, r), C.sub(y, r), C.sub(z, 0x447A0000)),
                          (C.add(x, r), C.add(y, r), C.add(z, 0x447A0000)), 0x40)
        top = C.add(u32(obj + 0x18), u32(obj + 0x20))
        stand = 0xC7C35000
        for o in found:
            oflags = u32(o + 0xC)
            if oflags & 1 or o == obj or o == ignore or (skip_creatures and oflags & 0x20):
                continue
            dx, dy = C.sub(u32(obj + 0x10), u32(o + 0x10)), C.sub(u32(obj + 0x14), u32(o + 0x14))
            dist = C.sqrt(C.add(C.mul(dx, dx), C.mul(dy, dy)))
            if not C.lt(C.add(dist, 0x3A83126E), C.add(r, u32(o + 0x1C))):
                continue
            mf = u32(obj + 0xC)
            touch_only = False
            if (oflags | mf) & 0x10:
                if C.lt(top, C.add(u32(o + 0x18), 0x40400000)):
                    continue
                otop = C.add(u32(o + 0x18), u32(o + 0x20))
                if C.lt(otop, u32(obj + 0x18)):
                    continue
                if C.lt(C.sub(otop, u32(obj + 0x18)), 0x40A00000):
                    if oflags & 0x200 or mf & 0x400:
                        touch_only = True
                    else:
                        if C.lt(stand, otop):
                            stand = otop
                        continue
            if not touch_only and not (oflags & 0x200 or mf & 0x400) and C.lt(0x3A83126E, C.fabs(dist)):
                k = C.div(C.sub(C.add(r, u32(o + 0x1C)), dist), dist)
                self.call('world_slideMove', obj + 0x10, (C.mul(dx, k), C.mul(dy, k), ZERO), 1, 0, r)
                self.call('obj_updateGridCell', obj)
                bits |= 2
            if not mf & F_PREDICTION_COPY:
                self.vcall(o, 6, obj)
            self.vcall(obj, 6, o)
            r = u32(obj + 0x1C)
        ground = self.call('terrain_heightBelow', u32(G_WORLD), self.vec(obj + 0x10), r)
        if C.lt(ground, stand):
            ground = stand
        vz = C.sub(u32(obj + 0x30), 0x410FFFFF)
        self.w32(obj + 0x30, vz)
        nz = C.add(u32(obj + 0x18), C.mul(vz, DT))
        self.w32(obj + 0x18, nz)
        if C.le(C.sub(nz, 0x3C23D70A), ground):
            self.w32(obj + 0x18, ground)
            if C.lt(vz, ZERO):
                self.w32(obj + 0x30, ZERO)
                bits |= 4
        return bits

_DOUBLE_1_4 = RB.Fraction(1.4)                  # the double at 0x52fc80 (0x3ff6666666666666) exactly


def _c_rem(a, b):
    """The R5900's signed remainder (div): the sign of the dividend; a zero divisor is
    refused (the console's result is not established, docs/spec/combat.md 3.1)."""
    a, b = s32(a), s32(b)
    if b == 0:
        raise CompositionError('remainder by zero (a radius below 1)')
    q = abs(a) // abs(b)
    r = abs(a) - q * abs(b)
    return -r if a < 0 else r


# =======================================================================================
# 8. The runtime: one world, its actors, the service table, one tick
# =======================================================================================


PLAYER_SLOTS[39] = 0x3C3B40                     # tail call of player_getSkillRank(P+0x3c8, id)

G_PADS, PAD_SIZE = RP.G_PADS, RP.PAD_SIZE
G_ALIVE_COUNT, G_ALIVE_LIST = 0x4F8420, 0x4F8440
G_LOCAL_ALIVE_COUNT, G_LOCAL_ALIVE_LIST, G_LOCAL_ALIVE_FIRST = 0x4F8424, 0x4F8430, 0x4F841C
G_FORCE_GHOST_REBASE = 0x402797
G_HUD_HIT_FLASH = 0x41B930
G_RECALL_COUNTDOWN, G_MENU_LOCKOUT, G_EXIT_COUNTDOWN = 0x41B51D, 0x41B4FC, 0x4F694A
G_DEBUG_INVULNERABLE, G_DECAL_DETAIL, G_PVP_MODE_B = 0x44F20C, 0x44FDC0, 0x4F7120
G_SKILL_STRONGSTANCE = 0x41B268
G_RUN_SPEED = 0x4F8418                         # float; 1.0 after game_clearLevel (0x1e4ff0)
WORLD_TOKEN = 0x00000F00                        # authored: the word g_world holds (never dereferenced)
FIXTURE_BASE = 0x00010000                       # authored: class definitions and animation tables

S_ACTINTRO, S_STOMEDAL = 0x5376C0, 0x537BE8     # strings the player code compares with (addresses)


def _dbl(bits):
    """A double constant of the executable, exactly (it is read as bits, not decimals)."""
    return RB.Fraction(_struct.unpack('<d', _struct.pack('<Q', bits))[0])


D_045, D_07, D_3 = _dbl(0x3FDCCCCCCCCCCCCC), _dbl(0x3FE6666666666666), _dbl(0x4008000000000000)


class Runtime:
    """One shared world and the order of service calls in it.  See the module docstring
    and docs/combat-runtime.md.  Typical use:

        rt = Runtime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        s = rt.spawn_skelight((40.0, 0.0, 0.0), clips={...})
        rt.press_attack(0)               # the pad of slot 0 (lockstep input)
        rt.tick()                        # gameSetObjectVis, runObjects, end of tick
        rt.trace                         # every service call, in order
    """

    RUN_BODIES = {0x2A8B84: 'skelight', 0x1A5030: 'player', 0x3C7E98: 'empty'}
    DTOR_BODIES = {0x117128: 'creature', 0x3CC67C: 'creature', 0x1A1BB8: 'player'}

    def __init__(self, terrain=None, anim=None, skill_stat=None, camera_mode=1):
        self.world = SharedWorld()
        self.world.init()
        self.mem = self.world.mem
        self.terrain = terrain or FlatTerrain()
        self.anim = anim or AnimTimeline()
        self.skill_stat = skill_stat or (lambda name, *args: ZERO)
        self.camera_mode = camera_mode
        self.trace, self.exp_awards = [], []
        self.services = Services(self)
        self.model = CombatModel(self.mem, self.services)
        self.rb = RB.World()
        self.rb.seed = MemSeed(self.mem)
        self.rb.cosmetic = MemSeed(self.mem, G_COSMETIC_SEED)
        self.rb.take_damage_fn = self._rb_take_damage
        self.rb.pool_fn = self._rb_pool
        self.rb.enemy_fn = lambda obj, other: self.model.vcall(obj.addr, 22, other.addr)
        self.world.on_run = self._slot4
        self.world.on_destroy = self._slot1
        self.players = {}                       # slot -> player object address
        self.kinds = {}                         # address -> 'creature' | 'player'
        for addr, size, value in ((G_WORLD, 4, WORLD_TOKEN), (G_NUM_PLAYERS, 4, 0), (G_NUMBERS_OPTION, 4, 0),
                                  (G_DECAL_DETAIL, 4, 0), (RC.G_LEVEL_MONSTER_LEVEL, 4, ONE),
                                  (G_RUN_SPEED, 4, ONE)):
            self.mem.poke(addr, size, value)
        for slot in range(4):
            self.mem.poke(G_PLAYERS + slot * REC_SIZE + 0x4B08, 2, 0xFFFF)     # empty skill lists
        self._fixture_next = FIXTURE_BASE

    # ---- small helpers --------------------------------------------------------------------
    def u32(self, a):
        return self.mem.u32(a)

    def live(self, addr):
        self.world.obj(addr)
        return LiveObj(self, addr, 'Player' if self.kinds.get(addr) == 'player' else 'Creature')

    def handle_target(self, head):
        cell = self.mem.heads.get(head)
        node = cell.next if cell is not None else None
        return node.obj.addr if node is not None and node.obj is not None else 0

    def relink(self, head, target):
        self.world.handles.clear(self.mem.head(head))
        if target:
            obj = self.world.obj(target)
            self.world.handles.link(self.mem.head(head), obj.heads[0], obj)

    def _alloc_fixture(self, size):
        addr = self._fixture_next
        self._fixture_next += (size + 0xF) & ~0xF
        return addr

    def note(self, *event):
        self.trace.append(event)

    # ---- spawning (AUTHORED set-up; not the original constructors) ------------------------
    def _spawn(self, size, pos, table, kind):
        obj = self.world.new_object(size, [f32(v) for v in pos])         # pool_new + GameObject_ctor
        if obj is None:
            raise Unsupported('the pool refused the block')
        addr = obj.addr
        self.kinds[addr] = kind
        self.mem.poke(addr + 0x48, 4, table)
        for slot, fn in TABLES[table].items():
            self.mem.poke(table + 8 * slot, 2, 0)
            self.mem.poke(table + 8 * slot + 4, 4, fn)
        for off in HANDLE_FIELDS + (0x364,) + ((0x588, H_SWEEP) if kind == 'player' else ()):
            self.mem.head(addr + off)
        return obj

    def spawn_skelight(self, pos, facing=0, hp=100.0, armor=0, damage=(4, 8), attack=100, team=0xFF,
                       home_range=600.0, visual=(48, 200, 0x2000), clips=None, cflags=0x100000):
        """A Skelight-class creature placed by hand (Skelight_ctor 0x2a8770 is modelled in
        ref_arena_monsters; this set-up is AUTHORED): table 0x5174b0, on the every-frame
        list and marked active as the constructor does, state 0 instead of the rising 0x17,
        no weapon holder, an authored class definition whose clip words are tokens."""
        obj = self._spawn(0x3C8, pos, VT_SKELIGHT, 'creature')
        c, poke = obj.addr, self.mem.poke
        definition = self._alloc_fixture(0x80)
        for k in range(1, 0x10):
            poke(definition + 8 * k + 4, 4, 0xC1100000 + 8 * k)           # clip tokens
        poke(definition + 0xC, 4, 0)                                      # no model
        poke(c + 0x24, 4, definition)
        poke(c + 0xC, 4, F_CREATURE)
        poke(c + 0x1C, 4, f32(12.0))
        poke(c + 0x38, 2, facing & 0xFFFF)
        poke(c + 0xA8, 8, cflags | (1 << 63))
        poke(c + 0xB0, 4, f32(1.5))                                       # turn rate
        poke(c + 0xB4, 1, 0x10)
        poke(c + 0xD0, 2, damage[0] & 0xFFFF)
        poke(c + 0xD2, 2, damage[1] & 0xFFFF)
        poke(c + 0xD4, 2, attack & 0xFFFF)
        poke(c + 0xDC, 4, ONE)
        poke(c + 0xE4, 2, armor & 0xFFFF)
        poke(c + 0x228, 4, f32(hp))
        poke(c + 0x22C, 4, f32(hp))
        poke(c + 0x310, 1, team & 0xFF)
        poke(c + 0x3AC, 2, visual[0])
        poke(c + 0x3AE, 2, visual[1])
        poke(c + 0x3B0, 2, visual[2])
        for i, v in enumerate(pos):
            poke(c + 0x3B4 + 4 * i, 4, f32(v))                            # home
        poke(c + 0x3C0, 4, f32(home_range))
        self.world.run_every_frame(obj)
        if clips:
            for token, timeline in clips.items():
                self.anim.clips[definition + token if token < 0x100 else token] = timeline
        return c

    def clip_token(self, c, offset):
        return self.u32(self.u32(c + 0x24) + offset)

    def spawn_player(self, slot, pos, facing=0, hp=100.0, level=1, strength=20, armor=0, team=0):
        """A player object placed by hand (Player_ctor 0x1a1d28 is not modelled; AUTHORED):
        table 0x511308, record slot `slot`, unarmed (weapon class 5), linked to the
        every-frame list as Player_ctor does (0x1a2340), action state 2."""
        obj = self._spawn(PLAYER_SIZE, pos, VT_PLAYER, 'player')
        P, poke = obj.addr, self.mem.poke
        R = G_PLAYERS + slot * REC_SIZE
        anims = self._alloc_fixture(0x68 * 8)
        for k in range(0, 0x68 * 8, 4):
            poke(anims + k, 4, 0xA0000000 + k)                            # animation tokens
        poke(P + 0x24, 4, anims)
        poke(P + 0xC, 4, F_CREATURE | F_PLAYER)
        poke(P + 0x1C, 4, f32(16.0))
        poke(P + 0x38, 2, facing & 0xFFFF)
        poke(P + 0xB0, 4, 0x3FB33333)
        poke(P + 0xDC, 4, ONE)
        poke(P + 0xE4, 2, armor & 0xFFFF)
        poke(P + 0x3C8, 4, slot)
        poke(P + 0x58C, 4, 2)
        poke(P + 0x4B2, 2, 0x7FFF)                                       # idle-voice limit: authored
        poke(R + 0x43D8, 4, P)
        poke(R + 0x50, 4, 1)                                             # class 1 (no class-0 mana rules)
        poke(R + 0x58, 1, level)
        poke(R + 0x59, 1, level)
        poke(R + 0x90, 4, strength)
        poke(R + 0xAC, 4, f32(hp))
        poke(R + 0xB0, 4, f32(hp))
        poke(R + 0x4A86, 1, 5)                                           # unarmed
        poke(R + 0x4C24, 1, team & 0xFF)
        poke(P + 0x228, 4, f32(hp))
        self.players[slot] = P
        self.mem.poke(G_NUM_PLAYERS, 4, max(self.players) + 1)
        self.world.run_every_frame(obj)
        self._rebuild_alive()
        return P

    # ---- input ---------------------------------------------------------------------------
    def press_attack(self, slot, held=True):
        """The slot's lockstep pad: the attack button in `pressed` (and `held`) for the next
        tick; tasks_run clears the edge word after the tick."""
        mask = 0x10
        self.mem.poke(RP.G_BTN_ATTACK + 4 * slot, 4, mask)
        pad = G_PADS + slot * PAD_SIZE
        self.mem.poke(pad + 0xC, 4, mask)
        self.mem.poke(pad + 8, 4, mask if held else 0)

    # ---- the tick ------------------------------------------------------------------------
    def tick(self):
        """One run pass, offline (docs/spec/object-system.md 6.2, 6.3), in the contract's
        domain: gameSetObjectVis (priority 0), runObjects (10); then g_simFrame += 1, the
        pads' edge words zeroed, game_rebuildAlivePlayers.  The other run tasks of
        docs/mainloop.md section 2 are not in this composition."""
        if self.world.network_mode or s8(self.mem.load(G_CUTSCENE_ACTIVE, 1)):
            raise Unsupported('net games and cutscenes are outside the domain')
        self.note('task', 'gameSetObjectVis')
        players = [self.world.objects.get(self.players.get(slot, 0)) for slot in range(self.num_players())]
        self.world.set_object_vis(None, self.camera_mode, 0, players)
        self.note('task', 'runObjects', self.world.frame)
        self.world.run_objects()
        self.world.frame = (self.world.frame + 1) & M32
        for slot in range(4):
            self.mem.poke(G_PADS + slot * PAD_SIZE + 0xC, 4, 0)
            self.mem.poke(G_PADS + slot * PAD_SIZE + 0x10, 4, 0)
        self._rebuild_alive()
        alive = s32(self.u32(G_ALIVE_COUNT))
        if self.players and alive == 0:
            raise Unsupported('every player is dead: game_checkAllDead schedules deathTask')

    def num_players(self):
        return s32(self.u32(G_NUM_PLAYERS))

    def _rebuild_alive(self):
        """game_rebuildAlivePlayers 0x1e72f8 (ref_objects.World.alive_players); offline
        every slot is local."""
        objs = [self.world.objects.get(self.players.get(slot, 0)) for slot in range(self.num_players())]
        alive, local, first = O.World.alive_players(objs, lambda slot: True)
        self.mem.poke(G_ALIVE_COUNT, 4, len(alive))
        self.mem.poke(G_LOCAL_ALIVE_COUNT, 4, len(local))
        self.mem.poke(G_LOCAL_ALIVE_FIRST, 4, first & M32)
        for i, slot in enumerate(alive):
            self.mem.poke(G_ALIVE_LIST + 4 * i, 4, slot)
        for i, slot in enumerate(local):
            self.mem.poke(G_LOCAL_ALIVE_LIST + 4 * i, 4, slot)

    # ---- slot 4 and slot 1 ---------------------------------------------------------------
    def _fn(self, addr, slot):
        return self.u32(self.u32(addr + 0x48) + 8 * slot + 4)

    def _slot4(self, obj):
        fn = self._fn(obj.addr, 4)
        kind = self.RUN_BODIES.get(fn)
        self.note('run', obj.addr, kind)
        if kind == 'skelight':
            self.model.skelight_run(obj.addr)
        elif kind == 'player':
            self.player_run(obj.addr)
        elif kind != 'empty':
            raise Unsupported('slot 4 of 0x%x reaches 0x%x' % (obj.addr, fn))

    def _slot1(self, obj, flags):
        """The destructor chain (slot 1 with argument 3).  Creature_dtor 0x117128: the
        attached spells (slot 1 of each, none in the domain), then handle_clear of +0x364,
        +0x360, the attachment state (0x202500, not modelled: presentation), +0x2e4, +0x238,
        +0x234, the animation state, then GameObject_dtor (+8, +4, +0) and pool_free.
        Player_dtor 0x1a1bb8 adds, before that: the record's object pointer is cleared
        (when +0x462 is 0), game_rebuildAlivePlayers, handle_clear of +0x588, two lights,
        +0x4b8, five heads +0x438 down to +0x3d8 - refused here (a player is never destroyed in
        the domain)."""
        fn = self._fn(obj.addr, 1)
        kind = self.DTOR_BODIES.get(fn)
        self.note('destroy', obj.addr, kind)
        if kind == 'creature':
            addr, mem, handles = obj.addr, self.mem, self.world.handles
            if mem.heads[addr + 0x364].next is not None:
                raise Unsupported('destroying a creature with attached spells')
            for off in (0x364, 0x360, 0x2E4, 0x238, 0x234):
                handles.clear(mem.head(addr + off))
            block = self.world._block_size(addr)
            self.world.destroy(obj, flags)
            self.kinds.pop(addr, None)
            if flags & 1:
                mem.forget_heads(addr, addr + block)
        elif kind == 'player':
            raise Unsupported('Player_dtor: a player object is not destroyed in the domain')
        else:
            self.world.destroy(obj, flags)

    # ---- the damage path ------------------------------------------------------------------
    def _sync_rb(self):
        w, mem = self.rb, self.mem
        w.frame = mem.u32(G_SIM_FRAME)
        w.network_mode = s8(mem.load(G_NETWORK_MODE, 1))
        w.cutscene = s8(mem.load(G_CUTSCENE_ACTIVE, 1))
        w.numbers_option = mem.u32(G_NUMBERS_OPTION)
        w.pvp_a = mem.u32(G_PVP_MODE_A)
        w.focus = [mem.u32(O.G_CAMERA_FOCUS), mem.u32(O.G_CAMERA_FOCUS + 4)]
        w.num_players = self.num_players()
        w.players = [LiveRec(self, slot) for slot in range(max(w.num_players, 0))]
        w.alive = [s32(mem.u32(G_ALIVE_LIST + 4 * i)) for i in range(s32(mem.u32(G_ALIVE_COUNT)))]
        w.monster_level = mem.u32(RC.G_LEVEL_MONSTER_LEVEL)

    def _rb_take_damage(self, victim, amount, attacker, flags):
        """damage_apply's take-damage: the victim's virtual slot 2 (amount, attacker, flags)."""
        self.model.vcall(victim.addr, 2, attacker.addr if attacker is not None else 0, flags, amount)

    def _rb_pool(self, size):
        raise Unsupported('damage_apply asks for a pool block of 0x%x (an effect object): outside the domain'
                          % size)

    def svc_damage_apply(self, victim, attacker, attack, a3, t0, flags, desc, no_crit, dmin, dmax):
        """damage_apply 0x1e8230 (ref_combat, executed) on live views of the image."""
        if desc and not (isinstance(desc, tuple) and desc[0] == 'elem'):
            raise Unsupported('a damage descriptor (weapon item) is outside the domain')
        slots = None
        if isinstance(desc, tuple):
            slots = [(0x15, s16(desc[1]), s16(desc[2]), 0)] + [(-1, 0, 0, 0)] * 3
        self._sync_rb()
        before = len(self.rb.seed.draws)
        self.note('damage_apply', victim, attacker, s32(attack), flags & M32)
        result = RB.damage_apply(self.rb, self.live(victim), self.live(attacker) if attacker else None,
                                 dmin, dmax, attack, flags, slots, no_crit)
        self.note('damage_result', victim, result, tuple(self.rb.seed.draws[before:]))
        return result

    # ---- the world services the models call out to ------------------------------------------
    def svc_world_collectObjectsInBox(self, low, high, limit):
        found = [o.addr for o in self.world.collect_in_box(list(low), list(high), limit)]
        self.note('box', tuple(found))
        return found

    def svc_obj_updateGridCell(self, c):
        self.world.update_grid_cell(self.world.obj(c))

    def svc_obj_runEveryFrame(self, c):
        self.world.run_every_frame(self.world.obj(c))

    def svc_obj_runEvery60(self, c):
        self.world.run_every_60(self.world.obj(c))

    def svc_obj_delete(self, c):
        self.note('obj_delete', c)
        self.world.delete(self.world.obj(c))

    def svc_handle_clear(self, head):
        self.world.handles.clear(self.mem.head(head))

    def svc_handle_link(self, head, back, obj):
        """handle_link(head, back, obj): `back` is an object (its head +0) or one of an
        object's heads (+4 for the run lists).  A pointer that is not a live object is
        refused: the original would link it anyway (FINDINGS ST3)."""
        target = self.world.obj(obj)
        back_cell = self.mem.heads.get(back)
        if back_cell is None:
            raise CompositionError('handle_link back list 0x%x is not a head' % back)
        self.world.handles.link(self.mem.head(head), back_cell, target)

    def svc_handle_removeNode(self, node):
        index, rest = divmod(node - SharedMemory.NODE_BASE, SharedMemory.NODE_SIZE)
        if rest or not 0 <= index < len(self.world.handles.nodes):
            raise CompositionError('0x%x is not a node' % node)
        n = self.world.handles.nodes[index]
        obj = self.world.handles.remove(n)
        return obj.addr if obj is not None else 0

    def svc_iter_begin(self, head, mask):
        cell = self.mem.heads.get(head)
        if cell is not None and cell.next is not None:
            raise Unsupported('iterating a non-empty list at 0x%x (attached spells)' % head)
        return 0

    def svc_iter_next(self):
        return 0

    def svc_iter_end(self, flags):
        return None

    def svc_terrain_raycast(self, world, origin, direction, mask, factor):
        t = self.terrain.raycast(origin, direction, mask, factor)
        self.note('terrain', 'raycast', t)
        return t

    def svc_world_raycast(self, world, origin, direction, ignore, hit_out, mask, flag, factor):
        self.note('terrain', 'world_raycast')
        t = self.terrain.raycast(origin, direction, mask, factor)
        return (t, 0) if hit_out else t

    def svc_world_slideMove(self, pos_addr, delta, mask, normal_out, radius):
        pos = self.model.vec(pos_addr)
        new, hit, normal = self.terrain.slide(pos, delta, mask, radius)
        self.note('terrain', 'slide', mask)
        for i in range(3):
            self.mem.poke(pos_addr + 4 * i, 4, new[i])
        return (hit, normal) if normal_out else hit

    def svc_terrain_heightBelow(self, world, pos, radius):
        return self.terrain.height_below(pos, radius)

    def svc_water_test(self, world, pos, flag, radius):
        r = self.terrain.water_test(pos, radius)
        self.note('terrain', 'water_test', r)
        if r:
            raise Unsupported('water: the creature water services are not in this contract')
        return 0

    def svc_obj_getPropStr(self, obj, key, default):
        o = self.world.obj(obj)
        if o.props:
            raise Unsupported('objects with properties are outside the domain')
        return 0

    def svc_obj_getPropInt(self, obj, key, default):
        o = self.world.obj(obj)
        if o.props:
            raise Unsupported('objects with properties are outside the domain')
        return default

    def svc_net_objOrGhost(self, c):
        return c

    def svc_net_isLocalSlot(self, slot):
        return 1                                    # offline: every slot is this machine's

    def svc_net_getCamFlag(self, slot):
        return 0

    def svc_player_speedScale(self, slot):
        """player_speedScale 0x1bea10 (slot): Player_move's speed scale (4.1(b)) without the
        Drowsy line - base 0x3f5ca86d offline (also on the level 'watmedal'), times the
        record's speed multiplier +0x4c20 unless slot is -1, times g_runSpeed 0x4f8418,
        capped at 0x3f999999."""
        if s8(self.mem.load(G_NETWORK_MODE, 1)):
            raise Unsupported('player_speedScale in a net game')
        S = 0x3F5CA86D
        if s32(slot) != -1:
            S = C.mul(S, self.u32(G_PLAYERS + s32(slot) * REC_SIZE + 0x4C20))
        S = C.mul(S, self.u32(G_RUN_SPEED))
        return 0x3F999999 if C.lt(0x3F999999, S) else S

    def svc_net_getCamYaw(self, slot):
        """The slot's camera yaw of the input record (lockstep input): AUTHORED 0."""
        return 0

    def svc_creature_bossRank(self, c):
        """creature_bossRank 0x10d940 for an object without a type name: bit 0 of the
        creature flags (docs/spec/combat.md 4.3).  The domain's creatures have none."""
        return self.model.u64(c + 0xA8) & 1

    def svc_creature_findSpellByType(self, c, type_info):
        cell = self.mem.heads.get(c + 0x364)
        if cell is not None and cell.next is not None:
            raise Unsupported('attached spells are outside the domain')
        return 0

    def svc_SpellDrowsy_typeinfo(self):
        return 0x3D1234

    def svc_SpellAncestralCall_typeinfo(self):
        return 0x3D0001

    def svc_SpellBattleCry_typeinfo(self):
        return 0x3D0002

    def svc_player_getSkillRank(self, slot, skill):
        return LiveRec(self, s32(slot)).rank(s32(skill)) & M32

    def svc_SkillLifeTap_getStat0Fraction(self, skill, rank):
        return self.skill_stat('SkillLifeTap_getStat0Fraction', skill, rank)

    def svc_player_giveExp(self, slot, amount):
        """Delivered, not applied: experience is ref_combat.give_exp's (executed there)."""
        self.exp_awards.append((slot, amount))
        self.note('player_giveExp', slot, amount)

    def svc_world_notifyObjectsNear(self, a, pos, b, radius):
        """world_notifyObjectsNear 0x11a2b8 (a, &pos, b; R): a box of +-R on all three axes,
        limit 0x80; slot 12 of every object in list order with (a, &pos, b; R).  The bodies
        of the domain's tables (Creature_slot12, GameObject_default_slot12) are empty."""
        x, y, z = pos
        found = self.svc_world_collectObjectsInBox((C.sub(x, radius), C.sub(y, radius), C.sub(z, radius)),
                                                   (C.add(x, radius), C.add(y, radius), C.add(z, radius)), 0x80)
        for o in found:
            self.model.vcall(o, 12, a, pos, b, radius)

    def svc_model_getBounds(self, model, index):
        return (0, 0, 0, 0, 0, 0)

    def svc_model_getSamplePointCount(self, model):
        return 0

    def svc_dialog_isOpen(self):
        return 0

    def svc_game_isFrozen(self):
        return 0

    def svc_task_isRunning(self, name):
        return 0

    def svc_net_isSlotActive(self, slot):
        return 1

    def svc_libc_sprintf(self, fmt, *args):
        return ('buf', b'')

    def svc_res_find(self, lump, entry):
        return 0

    def svc_text_lookup(self, ident):
        return 0

    # animation (AUTHORED timeline)
    def svc_anim_start(self, state, clip, flags, blend):
        self.note('anim', 'start', state, clip, flags)
        self.anim.start(self.mem, state, clip)

    def svc_anim_startBlendInOut(self, state, clip, flags, blend_in, blend_out):
        self.note('anim', 'blend', state, clip, flags)
        self.anim.start(self.mem, state, clip)

    def svc_anim_advance(self, state, sound_pos, root_out, yaw_out, speed):
        return self.anim.advance(self.mem, state)

    def svc_Player_animStep(self, P, speed):
        return self.anim.advance(self.mem, P + 0x114)

    # call-outs of ref_player.Tick that the combat model has bodies for
    def svc_Creature_run(self, c, model):
        return self.model.run(c, model)

    def svc_Player_meleeHit(self, P, target, a2, extra, scale):
        return self.model.player_melee_hit(P, target, a2, extra, scale)

    def svc_Player_findTarget(self, P, reach):
        return self.model.player_find_target(P, reach)

    def svc_Player_move(self, P, mode, pad, ext):
        return self.model.player_move(P, mode, pad, ext)

    def svc_Player_processDamage(self, P):
        return self.model.player_process_damage(P)

    def svc_Player_recalcDamage(self, P, weapon, flag):
        """Player_recalcDamage 0x1b7158 (P, weapon, flag): ref_combat.recalc_damage
        (executed) on a live view of the record.  Unarmed only."""
        if weapon:
            raise Unsupported('Player_recalcDamage with a weapon item')
        self._sync_rb()
        rec = _LivePlayerRec(self, s32(self.u32(P + 0x3C8)))
        self.rb.players[rec.slot] = rec
        RB.recalc_damage(None, self.rb, self.live(P), None, flag)

    def svc_game_rebuildAlivePlayers(self):
        self._rebuild_alive()

    def svc_jumpgate_getTravelState(self):
        return 0

    def svc_SkillStrongStance_getStat0(self, skill, rank):
        return self.skill_stat('SkillStrongStance_getStat0', skill, rank)

    def svc_SpellHolyShield_typeinfo(self):
        return 0x3CF124

    def svc_SpellResurrect_typeinfo(self):
        return 0x3D162C

    def svc_SpellHarmTouch_typeinfo(self):
        return 0x3D0003

    def svc_net_closeLocalMenus(self, flag):
        self.note('presentation', 'net_closeLocalMenus')

    def svc_Player_tryBlockMove(self, P, pad):
        raise Unsupported('Player_tryBlockMove as a call-out')

    def svc_Player_footstep(self, P):
        self.note('presentation', 'Player_footstep')

    def svc_Player_weaponTrails(self, P):
        self.note('presentation', 'Player_weaponTrails')

    # ---- the player's slot 4: an AUTHORED driver around executed pieces --------------------
    def player_run(self, P):
        """Slot 4 of a player in this contract.  NOT Player_run 0x1a5030: it runs, in
        Player_run's order, the steps the contract has models for and refuses the rest:

          Creature_run(P, P+0x544)            ref_creature (executed)        0x1a5248
          Creature_applyKnockback(P; 1.0)     this module (Observed)
          P+0x228 = record hit points                                        0x1a527c
          hit-immunity and spawn-protection countdowns (as ref_player.top)
          Player_processDamage(P) unless dead this module (Observed)         0x1a5b90
          the action-state switch             ref_player.Tick, executed: states 1 (melee),
                                              2 (neutral, standing), 3 (staggered)

        Left out, each of which ref_player models and the original runs every tick: the
        breath puff (own draws, cold levels), the white light, the idle voice (a shared draw
        when it fires; its limit +0x4b2 is set high by the fixture), the rumble, the pad
        choice (the slot's lockstep pad is used as is), Player_idleFidget (a shared draw
        with four tracks), the aura globals, regeneration, the kill plane, the swap /
        interact gate, instant abilities, the tail (casts, record countdowns)."""
        mem, u32 = self.mem, self.u32
        R = self.model._rec(P)
        self.model.run(P, P + 0x544)
        self.model.apply_knockback(P, ONE)
        mem.poke(P + 0x228, 4, u32(R + 0xAC))
        if not u32(P + 0xC) & F_PREDICTION_COPY:
            v = s8(mem.load(R + 0x4C27, 1)) - 1
            mem.poke(R + 0x4C27, 1, max(v, 0))
        if self.model.s16(P + 0x4B4):
            v = (mem.load(P + 0x4B4, 2) - 1) & 0xFFFF
            mem.poke(P + 0x4B4, 2, v)
            if s16(v) < 0x14:
                mem.poke(P + 0xC, 4, u32(P + 0xC) & ~2 & M32)
        if s8(mem.load(P + 0x231, 1)):
            raise Unsupported('scripted control (+0x231)')
        mem.poke(P + 0x4C0, 4, 0)                                         # 3.4 last velocity
        mem.poke(P + 0x4BC, 4, 0)
        weapon = u32(R + 0x4434 + 4 * s8(mem.load(R + 0x4A7C, 1)))           # 3.5 time between attacks
        mem.poke(P + 0x48C, 4, 0x3EA8F5C2 if not weapon or mem.load(u32(weapon) + 0x1E, 1) == 4 else 0x3E199999)
        if not u32(P + 0xC) & F_DEAD:
            self.model.player_process_damage(P)
        state = s32(u32(P + 0x58C))
        if state == 4:
            self.note('player_dead_state', P)
            return
        if state not in (1, 2, 3):
            raise Unsupported('player action state %d' % state)
        tick = RP.Tick(mem, P, self.services)
        tick.pad = G_PADS + s32(u32(P + 0x3C8)) * PAD_SIZE
        tick.instant = 0
        tick.R0 = R
        try:
            tick.switch()
        except RP.Leave:
            pass
        self.note('player_state', P, state, s32(u32(P + 0x58C)))


class _LivePlayerRec(LiveRec):
    """The record fields ref_combat.recalc_damage reads and writes, as live views."""

    @property
    def eff(self):
        return _MemVec(self._rt.mem, self.base + 0x90, 4, 4, 4, True)

    @property
    def level58(self):
        return s8(self._rt.mem.load(self.base + 0x58, 1))

    @property
    def cls(self):
        return s32(self._rt.mem.u32(self.base + 0x50))

    @property
    def second_weapon(self):
        if self._rt.mem.u32(self.base + 0x443C):
            raise Unsupported('a second weapon')
        return None

    def _set(self, off, value):
        self._rt.mem.poke(self.base + off, 4, value & M32)

    attack = property(lambda self: s32(self._rt.mem.u32(self.base + 0xCC)), lambda self, v: self._set(0xCC, v))
    dmg_min = property(lambda self: s32(self._rt.mem.u32(self.base + 0xD0)), lambda self, v: self._set(0xD0, v))
    dmg_max = property(lambda self: s32(self._rt.mem.u32(self.base + 0xD4)), lambda self, v: self._set(0xD4, v))
