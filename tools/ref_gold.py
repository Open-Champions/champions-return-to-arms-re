"""ref_gold.py - the gold pile's frame and pickup down to the credit, and the item props'
pickup (the use button), on top of tools/ref_phprop.py (which built the pile).

Reference contract, executed against the original by tools/difftest_gold.py
(docs/spec/gold-run.md is the prose).  Everything here is Observed by that difftest unless a
docstring says otherwise.

    Gold_run                0x157b58  slot 4 of Gold (table 0x511a88): the spawn countdown
    Gold_onTouch            0x157a9c  slot 6 of Gold: the pickup
    hud_addGoldFloater      0x1dc268  (slot, world position, amount): a floater, or the credit
                                      at once when all eight floaters are busy
    hud_tickGold            0x1dcb80  (inside hud_run, a run task): floaters -> pending -> gold
    hud_flushGold           0x1dc5f4  (game_clearLevel): everything pending, at once
    itemprop_tryPickup      0x154dbc  (slot, item record) -> 1 taken / 0 refused
    PhProp_interact         0x155020  slot 14 of PhProp: an item in flight, the use button
    ItemProp_interact       0x159b38  slot 14 of ItemProp: an item at rest (same code)
    PhProp_interactPrompt   0x154d10  slot 13 of PhProp: the prompt text, +0x104 = frame
    ItemProp_interactPrompt 0x159870  slot 13 of ItemProp (same code)
    ItemProp_ctor3          0x1592bc  (obj, pos, item, matrix): the item at rest; no run
    ItemProp_ctor2          0x1590ec  (obj, pos, item, launch): a dropped/given item; runs
    Prop_ctorNamed          0x153ac0  the Prop constructor under ItemProp_ctor3
    item_getResourceIndex   0x1083f8  the item's row of the model table 0x3e9ce0
    Prop_run                0x154514  slot 4 of Prop and ItemProp: fall, slide, life, sink

Where the gold goes: player record (g_players 0x4d8af0, stride 0x4c30) +0xe4, a signed word
capped at 99,999,999 (0x5f5e0ff) by a store-then-overwrite.  The WHOLE amount goes to the
toucher's slot (object +0x3c8): nothing on this path reads g_numPlayers or splits.

Draws: none from the shared seed 0x404464 anywhere here.  hud_addGoldFloater makes ONE
COSMETIC draw (0x404460) per floater it fills (none on the direct credit).
"""
import ref_core as C
import ref_creature as RC
import ref_phprop as PP
from ref_creature import Ext, M32, M64, s16, s32

GOLD_RUN, GOLD_ON_TOUCH = 0x157B58, 0x157A9C
HUD_ADD_GOLD_FLOATER, HUD_TICK_GOLD, HUD_FLUSH_GOLD = 0x1DC268, 0x1DCB80, 0x1DC5F4
TRY_PICKUP, PHPROP_INTERACT, ITEMPROP_INTERACT = 0x154DBC, 0x155020, 0x159B38
PHPROP_PROMPT, ITEMPROP_PROMPT = 0x154D10, 0x159870
MAT4_TRANSFORM_POINT = 0x165EE0                     # tools/ref_core.py, executed by difftest_core
MAT34_SET_POS_ROT_Z = 0x163B30                      # tools/ref_core.py, executed by difftest_core
ITEMPROP_CTOR2, ITEMPROP_CTOR3, PROP_CTOR_NAMED = 0x1590EC, 0x1592BC, 0x153AC0
PROP_RUN = 0x154514                                 # slot 4 of Prop and of ItemProp
G_WORLD, G_ALIVE_PLAYERS = 0x44FDC8, 0x4F8440
F_DT, F_MILLI, F_ONE_HALF = 0x3C888888, 0x3A83126E, 0x3FC00000     # 1/60, 0.001, 1.5
F_GRAVITY, F_ROLL, F_BOUNCE_MIN, F_BOUNCE = 0x41D7FFFF, 0x3F7AE147, 0xBDCCCCCC, 0x3ECCCCCC
F_SINK, F_120 = 0x3DCCCCCC, 0x42F00000
ITEM_RESOURCE_INDEX = 0x1083F8                      # item_getResourceIndex (difftest_items stats-random)
ITEM_MODELS = 0x3E9CE0                              # 16-byte rows: +0 model name, +4 texture name
S_ITEMS_LUMP = 0x5326B0                             # "equipmnt.lmp" (0x159148/0x159160, 0x159318/0x159330)
VT_GOLD, VT_PHPROP, VT_ITEMPROP = PP.VT_GOLD, PP.VT_PHPROP, 0x511C38
PHPROP_DTOR, ITEMPROP_DTOR = 0x3C2FC8, 0x3C2ED8      # slot 1 of the two tables

G_SIM_FRAME = RC.G_SIM_FRAME                        # 0x44fdcc
G_NUM_PLAYERS = RC.G_NUM_PLAYERS                    # 0x4d8ae0
G_COSMETIC_SEED = 0x404460
G_VIEW_PROJ = 0x44F140                              # this machine's camera x projection
G_PLAYERS, REC_SIZE = 0x4D8AF0, 0x4C30
REC_GOLD, REC_LOAD, REC_LIMIT, REC_OBJ = 0xE4, 0x120, 0x124, 0x43D8
REC_BAG_COUNT, BAG_SIZE = 0x1330, 0x1208           # count word of bag k: +0x130 + k x 0x1208 + 0x1200
GOLD_CAP = 99999999                                 # 0x5f5e0ff, built at 0x1dc2f4/0x1dc2fc and 0x1dcc30
FLOATERS, FLOATER_SIZE, FLOATER_COUNT = 0x86A900, 0x24, 8
G_GOLD_PENDING = 0x86ACE8                           # int[4]
FLUSH_CLEARED = (0x4F6950, 0x86ACD8)                # two int[4] hud_flushGold zeroes; readers unknown
HUD_GOLD_Y, HUD_GOLD_X = 0x4F6710, 0x4F6730         # int[4] each: the counter's screen place per slot
CREDIT_DELAY = 0x80                                 # (frame - start) x 3 must reach 128: 43 frames

S_FX_LUMP = PP.S_FX_LUMP                            # 0x532478 "fx.lmp"
S_COIN_PICKUP = 0x532820                            # the coin pick-up sound (0x157ae4/0x157af4)
S_COIN_DROP = 0x532838                              # the coin drop sound (0x157b8c/0x157b98)
S_CANTDO = 0x5325B8                                 # the can't-do button sound (0x154e28/0x154e2c)
S_GOT_ITEM = 0x532678                               # "*gotItemNotify" (0x154fd0/0x154fd8)
S_PICKUP_KEY, S_SPACE, S_TIMES = 0x5325A0, 0x5325A8, 0x5325B0   # "PickUp", " ", " x %d"
S_JEWELRY = 0x532660
# itemprop_tryPickup's sound by the item's flag word +8, first match wins (0x154e74-0x154f94)
EQUIP_SOUNDS = ((0x800000, 0x5325D0), (0x200000, 0x5325E8), (0x40000, 0x532600),
                (0x100000, 0x532618), (0x80000, 0x532630), (0x1000000, 0x532648))
ITEM_ALL_PLAYERS = 1 << 39                          # item flag: given to every player (0x155024/0x155028)

GOLD_COUNTDOWN = 0x29                               # Gold_ctor2's byte +0x4c (tools/ref_phprop.py)
COIN_SOUND_AT = 0x12                                # Gold_run: the drop sound 18 frames after the ctor

F_20, F_700, F_300 = 0x41A00000, 0x442F0000, 0x43960000
F_320, F_240, F_9 = 0x43A00000, 0x43700000, 0x41100000
F_2M16, HALF, ONE, ZERO = PP.F_2M16, PP.HALF, PP.ONE, PP.ZERO

EXECUTED = {
    'Gold_run': GOLD_RUN, 'Gold_onTouch': GOLD_ON_TOUCH,
    'hud_addGoldFloater': HUD_ADD_GOLD_FLOATER, 'hud_tickGold': HUD_TICK_GOLD,
    'hud_flushGold': HUD_FLUSH_GOLD,
    'itemprop_tryPickup': TRY_PICKUP, 'PhProp_interact': PHPROP_INTERACT,
    'ItemProp_interact': ITEMPROP_INTERACT, 'PhProp_interactPrompt': PHPROP_PROMPT,
    'ItemProp_interactPrompt': ITEMPROP_PROMPT,
    'ItemProp_ctor2': ITEMPROP_CTOR2, 'ItemProp_ctor3': ITEMPROP_CTOR3, 'Prop_ctorNamed': PROP_CTOR_NAMED,
    'Prop_run': PROP_RUN,
}
MODELLED = dict(PP.MODELLED)
MODELLED.update(EXECUTED)
MODELLED.update({'mat4_transformPoint': MAT4_TRANSFORM_POINT, 'mat34_setPosRotZ': MAT34_SET_POS_ROT_Z,
                 'item_getResourceIndex': ITEM_RESOURCE_INDEX})

# virtual bodies: function -> (slot, method)
CLASS_BODIES = {
    GOLD_RUN: (4, 'gold_run'), GOLD_ON_TOUCH: (6, 'gold_on_touch'),
    PHPROP_INTERACT: (14, 'prop_interact'), ITEMPROP_INTERACT: (14, 'prop_interact'),
    PHPROP_PROMPT: (13, 'prop_interact_prompt'), ITEMPROP_PROMPT: (13, 'prop_interact_prompt'),
    PROP_RUN: (4, 'prop_run'),
}

# Callees that stay recording callbacks (kinds as tools/ref_phprop.py: S a text pointer, a
# stack buffer compared by its text).
EXTERNALS = dict(PP.EXTERNALS)
EXTERNALS.update({
    'anim_advanceUnitSpeed': Ext(0x1709D8, 'ppii', 0, 'n', '(anim state, root position, 0, 0)'),
    'obj_delete': Ext(0x14F200, 'p', 0, 'n', '(object): deferred delete (tools/ref_objects.py)'),
    'res_find': Ext(0x17365C, 'pS', 0, 'i', '(lump name, entry name) -> entry or 0'),
    'player_itemWeight': Ext(0x1B6338, 'ip', 0, 'f', '(slot, item record) -> weight'),
    'player_voice': Ext(0x1B7BA8, 'ii', 0, 'n', '(slot, kind): the "cannot carry" line'),
    'script_runByName': Ext(0x1ED694, 'p', 0, 'i', '(hook name)'),
    'inventory_giveItem': Ext(0x1C1868, 'ipi', 0, 'i', '(slot, item record, 1) -> bag index or -1'),
    'player_recalcLoad': Ext(0x1BEC10, 'i', 0, 'n', '(slot)'),
    'text_lookup': Ext(0x173C84, 'p', 0, 'i', '(key) -> wide text'),
    'wstr_cat': Ext(0x19E8E4, 'pp', 0, 'n', '(wide out, wide text)'),
    'wstr_catAscii': Ext(0x19E93C, 'pS', 0, 'n', '(wide out, ascii text)'),
    'itemName_buildLocalizedName': Ext(0x101E48, 'pi', 0, 'i', '(item record, 1) -> wide text'),
    'PhProp_dtor': Ext(PHPROP_DTOR, 'pi', 0, 'n', '(prop, 3): slot 1, delete'),
    'ItemProp_dtor': Ext(ITEMPROP_DTOR, 'pi', 0, 'n', '(prop, 3): slot 1, delete'),
    'Prop_dtor': Ext(0x3C2D30, 'pi', 0, 'n', '(prop, 3): slot 1 of Prop, delete'),
    'terrain_sweepCircle': Ext(0x185A40, 'pvvpN', 1, 'f', '(world, position, step, 1, normal out; radius) '
                               '-> the fraction of the step that is free'),
    'terrain_heightBelow': Ext(0x1834A8, 'pv', 1, 'f', '(world, position; radius) -> ground height'),
})
DTORS = {PHPROP_DTOR: 'PhProp_dtor', ITEMPROP_DTOR: 'ItemProp_dtor', 0x3C2D30: 'Prop_dtor'}


def floater(k):
    """Floater k: +0 screen x, +4 screen y, +8 z (always 0), +0xc/+0x10/+0x14 drift,
    +0x18 start frame, +0x1c amount (0 = free), byte +0x20 slot, byte +0x21 off-screen."""
    return FLOATERS + FLOATER_SIZE * k


def record(slot):
    return (G_PLAYERS + (s32(slot) * REC_SIZE)) & M32


class Model(PP.Model):
    """The gold pile and the item pickup, on a memory image.  .cosmetic counts the draws
    of the cosmetic seed 0x404460 (.draws, as everywhere, the shared seed's)."""

    def __init__(self, mem, callbacks=None, external=()):
        PP.Model.__init__(self, mem, callbacks, external)
        self.cosmetic = 0

    def call(self, name, *args):
        if name == 'libc_sprintf' and len(args) == 1:      # a format without a value
            self.calls.append((name, args))
            return self.cstr(args[0])
        if name == 'terrain_sweepCircle':              # -> (fraction, normal written to the stack)
            args = tuple(a & M32 if isinstance(a, int) else a for a in args)
            self.calls.append((name, args))
            function = self.cb.get(name)
            return function(*args) if function is not None else (ONE, (ZERO, ZERO, ZERO))
        if name in ('player_itemWeight', 'terrain_heightBelow'):
            args = tuple(a & M32 if isinstance(a, int) else a for a in args)
            self.calls.append((name, args))
            function = self.cb.get(name)
            return function(*args) if function is not None else ZERO
        if name in EXTERNALS and name not in PP.EXTERNALS and self.cb.get(name) is None:
            self.calls.append((name, tuple(a & M32 if isinstance(a, int) else a for a in args)))
            return None if EXTERNALS[name].ret == 'n' else 0
        return PP.Model.call(self, name, *args)

    def cstr(self, addr):
        out = bytearray()
        while True:
            b = self.u8(addr + len(out))
            if not b:
                return bytes(out)
            out.append(b)

    def vcall_slot(self, obj, slot, *args):
        """A virtual call through +0x48 to one of this module's bodies, else a callback named
        by the table's function (the destructors) or '<table>.v<slot>'."""
        table = self.u32(obj + 0x48)
        this = (obj + self.s16(table + 8 * slot)) & M32
        function = self.u32(table + 8 * slot + 4)
        body = CLASS_BODIES.get(function)
        if body is not None and body[0] == slot:
            return getattr(self, body[1])(this, *args)
        return self.call(DTORS.get(function, '%x.v%d' % (table, slot)), this, *args)

    # ---- Gold_run --------------------------------------------------------------------------
    def gold_run(self, gold):
        """Gold_run 0x157b58 (gold), slot 4.

        Nothing once the countdown byte +0x4c is 0.  Otherwise: when +0x50 (Gold_ctor2's
        frame) equals g_simFrame - 18, the coin drop sound (0x532838 of fx.lmp on the pile,
        volume 1); then anim_advanceUnitSpeed(+0x58, +0x10, 0, 0); the countdown (re-read)
        loses one when non-zero; and when the anim state's halfword +0x5e has 0x80 (the clip
        has ended) the countdown becomes 0 and obj_stopRunning.  No draws."""
        if not self.s8(gold + 0x4C):
            return
        if self.u32(gold + 0x50) == (self.u32(G_SIM_FRAME) - COIN_SOUND_AT) & M32:
            entry = self.call('res_find', S_FX_LUMP, S_COIN_DROP)
            self.call('sound_playOnObject', entry, gold, ONE)
        self.call('anim_advanceUnitSpeed', gold + 0x58, gold + 0x10, 0, 0)
        if self.s8(gold + 0x4C):
            self.w8(gold + 0x4C, self.u8(gold + 0x4C) - 1)
        if self.u16(gold + 0x5E) & 0x80:
            self.w8(gold + 0x4C, 0)
            self.call('obj_stopRunning', gold)

    # ---- Gold_onTouch ----------------------------------------------------------------------
    def gold_on_touch(self, gold, other):
        """Gold_onTouch 0x157a9c (gold, toucher), slot 6.

        Taken only when, in this order: the toucher's flags +0xc lack 0x20000 (not the
        prediction copy), the countdown +0x4c is 0, the toucher's flags (the same read) have
        0x40 (a player), and the amount +0x80 is not 0.  Then: the coin sound
        ('inv_equip_coin' of fx.lmp on the pile, volume 1), hud_addGoldFloater(toucher +0x3c8,
        a copy of the pile's position, the amount), amount = 0, obj_delete(pile).  No draws,
        no game message, no g_numPlayers."""
        flags = self.u32(other + 0xC)
        if flags & 0x20000 or self.s8(gold + 0x4C) or not flags & 0x40:
            return
        if not self.u32(gold + 0x80):
            return
        entry = self.call('res_find', S_FX_LUMP, S_COIN_PICKUP)
        self.call('sound_playOnObject', entry, gold, ONE)
        slot = self.u32(other + 0x3C8)
        self.hud_add_gold_floater(slot, self.vec(gold + 0x10), self.u32(gold + 0x80))
        self.w32(gold + 0x80, 0)
        self.call('obj_delete', gold)

    # ---- hud_addGoldFloater ----------------------------------------------------------------
    def hud_add_gold_floater(self, slot, pos, amount):
        """hud_addGoldFloater 0x1dc268 (slot, world position, amount).

        The first floater whose amount +0x1c is 0.  None free: record(slot) +0xe4 += amount
        (32-bit), then 99,999,999 when that is (signed) above it; nothing else.  Otherwise
        the floater gets amount, slot byte, start frame g_simFrame, off-screen byte 0; the
        rest is presentation from this machine's camera g_viewProj 0x44f140: (p, w) =
        mat4_transformPoint(viewProj, pos); off-screen byte 1 when w < 20, or w x 700 <
        |p.x|, or w x 300 < |p.y|; screen x = p.x / w x 0.5 + 320, y = p.y / w + 240 (z = p.z
        / w, then overwritten with 0); the drift is the unit direction to the counter (the
        ints at 0x4f6730 / 0x4f6710 by slot) turned a quarter, times (c x 2^-16 - 0.5) x 9
        with c ONE COSMETIC DRAW of 0x404460.  No shared draw."""
        slot &= M32
        k = 0
        while k < FLOATER_COUNT and self.u32(floater(k) + 0x1C):
            k += 1
        if k == FLOATER_COUNT:
            self.credit(record(slot), amount)
            return
        e = floater(k)
        frame = self.u32(G_SIM_FRAME)
        self.w32(e + 0x1C, amount)
        self.w8(e + 0x20, slot)
        self.w32(e + 0x18, frame)
        self.w8(e + 0x21, 0)
        m = [self.u32(G_VIEW_PROJ + 4 * j) for j in range(16)]
        p, w = C.mat4_transform_point(m, list(pos))
        if C.lt(w, F_20) or C.lt(C.mul(w, F_700), C.fabs(p[0])) or C.lt(C.mul(w, F_300), C.fabs(p[1])):
            self.w8(e + 0x21, 1)
        inv = C.div(ONE, w)
        sx = C.add(C.mul(C.mul(p[0], inv), HALF), F_320)
        sy = C.add(C.mul(p[1], inv), F_240)
        sz = C.mul(p[2], inv)
        self.wvec(e, (sx, sy, sz))
        self.w32(e + 8, ZERO)
        tx = C.from_int(self.u32((HUD_GOLD_X + 4 * slot) & M32))
        ty = C.from_int(self.u32((HUD_GOLD_Y + 4 * slot) & M32))
        dx, dy, dz = C.sub(tx, sx), C.sub(ty, sy), C.neg(ZERO)
        r = C.rsqrt(ONE, C.add(C.add(C.mul(dx, dx), C.mul(dy, dy)), C.mul(dz, dz)))
        dx, dy = C.mul(dx, r), C.mul(dy, r)
        seed = (self.u32(G_COSMETIC_SEED) * 0x19660D + 0x3C6EF35F) & M32
        self.w32(G_COSMETIC_SEED, seed)
        self.cosmetic += 1
        spread = C.mul(C.sub(C.mul(C.from_int(seed >> 16), F_2M16), HALF), F_9)
        self.w32(e + 0xC, C.mul(dy, spread))
        self.w32(e + 0x10, C.mul(C.neg(dx), spread))
        self.w32(e + 0x14, ZERO)

    def credit(self, at, amount):
        """The credit idiom of all three bodies: +amount (32-bit), stored, then the cap stored
        over it when the signed sum is above 99,999,999.  A wrapped negative sum stays."""
        total = (self.u32(at + REC_GOLD) + amount) & M32
        self.w32(at + REC_GOLD, total)
        if s32(total) > GOLD_CAP:
            self.w32(at + REC_GOLD, GOLD_CAP)

    # ---- hud_tickGold ----------------------------------------------------------------------
    def hud_tick_gold(self):
        """hud_tickGold 0x1dcb80, every tick from hud_run (a run task).

        Each busy floater (amount != 0) whose (g_simFrame - start) x 3, as a signed 32-bit
        value, is at least 128 (43 frames) moves its amount into g_goldPending[s8 slot byte]
        and is freed.  Then for each slot 0..3 with pending p > 0: step = (p + 7) >> 3
        (arithmetic), the record's gold += step (capped as hud_addGoldFloater), pending =
        p - step.  The position, drift and off-screen byte are never read: the timing is
        the frame counter's alone."""
        frame = self.u32(G_SIM_FRAME)
        for k in range(FLOATER_COUNT):
            e = floater(k)
            amount = self.u32(e + 0x1C)
            if not amount:
                continue
            d = (frame - self.u32(e + 0x18)) & M32
            if s32((3 * d) & M32) < CREDIT_DELAY:
                continue
            pending = (G_GOLD_PENDING + 4 * self.s8(e + 0x20)) & M32
            self.w32(e + 0x1C, 0)
            self.w32(pending, self.u32(pending) + amount)
        for slot in range(4):
            at = G_GOLD_PENDING + 4 * slot
            p = self.s32(at)
            if p <= 0:
                continue
            step = s32((p + 7) & M32) >> 3
            self.credit(record(slot), step & M32)
            self.w32(at, p - step)

    # ---- hud_flushGold ---------------------------------------------------------------------
    def hud_flush_gold(self):
        """hud_flushGold 0x1dc5f4 (game_clearLevel): every busy floater's amount straight
        into record(s8 slot byte) +0xe4 (capped) and freed; then every positive pending sum
        of slots 0..3 likewise, pending = 0; then the words 0x4f6950 + 4s and 0x86acd8 + 4s
        (s 0..3) = 0."""
        for k in range(FLOATER_COUNT):
            e = floater(k)
            amount = self.u32(e + 0x1C)
            if not amount:
                continue
            self.credit(record(self.s8(e + 0x20)), amount)
            self.w32(e + 0x1C, 0)
        for slot in range(4):
            at = G_GOLD_PENDING + 4 * slot
            p = self.s32(at)
            if p <= 0:
                continue
            self.credit(record(slot), p & M32)
            self.w32(at, 0)
        for slot in range(4):
            for base in FLUSH_CLEARED:
                self.w32(base + 4 * slot, 0)

    # ---- itemprop_tryPickup ----------------------------------------------------------------
    def try_pickup(self, slot, item):
        """itemprop_tryPickup 0x154dbc (slot, item record) -> 1 taken, 0 refused.

        w = player_itemWeight(slot, item).  Refused with the 'game_butn_cantdo' sound (no
        object, volume 1) when the count of the bag of the item's category (definition +0x1d,
        s8) plus one is not below 64; refused with player_voice(slot, 0) unless load +0x120 +
        w <= limit +0x124 (c.ole.s).  Taken: the equip sound chosen by the item's flags
        (EQUIP_SOUNDS, jewelry otherwise) on the player's object, the '*gotItemNotify' hook,
        inventory_giveItem(slot, item, 1) (its result ignored), player_recalcLoad(slot)."""
        weight = self.call('player_itemWeight', slot, item)
        rec = record(slot)
        category = self.s8(self.u32(item) + 0x1D)
        count = self.s32((rec + REC_BAG_COUNT + category * BAG_SIZE) & M32)
        if not s32(count + 1) < 0x40:
            entry = self.call('res_find', S_FX_LUMP, S_CANTDO)
            self.call('sound_playOnObject', entry, 0, ONE)
            return 0
        if not C.le(C.add(self.u32(rec + REC_LOAD), weight), self.u32(rec + REC_LIMIT)):
            self.call('player_voice', slot, 0)
            return 0
        flags = self.u64(item + 8)
        fmt = S_JEWELRY
        for bit, name in EQUIP_SOUNDS:
            if flags & bit:
                fmt = name
                break
        text = self.call('libc_sprintf', fmt)
        entry = self.call('res_find', S_FX_LUMP, ('buf', text))
        self.call('sound_playOnObject', entry, self.u32(rec + REC_OBJ), ONE)
        self.call('script_runByName', S_GOT_ITEM)
        self.call('inventory_giveItem', slot, item, 1)
        self.call('player_recalcLoad', slot)
        return 1

    # ---- PhProp_interact / ItemProp_interact -----------------------------------------------
    def prop_interact(self, prop, slot):
        """PhProp_interact 0x155020 and ItemProp_interact 0x159b38 (prop, slot), slot 14; the
        same instructions.  The record is at +0x148.  With item flag bit 39 (+0x150): every
        slot 0 .. g_numPlayers - 1 (re-read each time) tries to take it, each gets a copy;
        otherwise only `slot`.  When any took it and the prop is not null: slot 1 (prop, 3),
        the destructor that deletes it."""
        if self.u64(prop + 0x150) & ITEM_ALL_PLAYERS:
            taken, k = 0, 0
            while k < self.s32(G_NUM_PLAYERS):
                if self.try_pickup(k, prop + 0x148):
                    taken = 1
                k += 1
        else:
            taken = self.try_pickup(slot, prop + 0x148)
        if taken and prop:
            self.vcall_slot(prop, 1, 3)

    # ---- PhProp_interactPrompt / ItemProp_interactPrompt -----------------------------------
    def prop_interact_prompt(self, prop, out):
        """PhProp_interactPrompt 0x154d10 and ItemProp_interactPrompt 0x159870 (prop, wide
        out) -> 1, slot 13; the same instructions.  +0x104 = g_simFrame (only draw code reads
        it), then the text 'PickUp' + ' ' + the item's name, and ' x <n>' when the stack count
        (s16 +0x14c, record +4) is 2 or more."""
        self.w32(prop + 0x104, self.u32(G_SIM_FRAME))
        self.call('wstr_cat', out, self.call('text_lookup', S_PICKUP_KEY))
        self.call('wstr_catAscii', out, S_SPACE)
        self.call('wstr_cat', out, self.call('itemName_buildLocalizedName', prop + 0x148, 1))
        count = self.s16(prop + 0x14C)
        if count >= 2:
            text = self.call('libc_sprintf', S_TIMES, count & M32)
            self.call('wstr_catAscii', out, ('buf', text))
        return 1

    # ---- the item props' constructors -------------------------------------------------------
    def resource_index(self, item):
        """item_getResourceIndex 0x1083f8 (item): s16 definition +0x34, plus bits 11..15 of
        the flag word +8 when its bit 36 is set (a visual variant)."""
        flags = self.u64(item + 8)
        row = self.s16(self.u32(item) + 0x34)
        if flags & (1 << 36):
            row += (flags >> 11) & 0x1F
        return row & M32

    def item_names(self, item):
        """The model and texture names of the item's row of 0x3e9ce0 (the index asked twice)."""
        a = self.resource_index(item)
        b = self.resource_index(item)
        return self.u32((ITEM_MODELS + 16 * a) & M32), self.u32((ITEM_MODELS + 16 * b + 4) & M32)

    def item_record(self, obj, item):
        """What ItemProp_ctor2 and ItemProp_ctor3 share after the Prop constructor: table
        0x511c38; the empty record at +0x148 (as PhProp_ctor) and the item's 0x48 bytes over
        it; flags |= 0x102000 and lose 0x1800, and with item flag bit 39 lose 0x3000 too;
        obj_updateGridCell."""
        w8, w16, w32 = self.w8, self.w16, self.w32
        w32(obj + 0x48, VT_ITEMPROP)
        for k in range(4):
            w16(obj + 0x16C + 8 * k, 0xFFFF)
        w8(obj + 0x169, 0xFF)
        w8(obj + 0x168, 0xFF)
        for k in range(4):
            w16(obj + 0x158 + 2 * k, 0)
            w16(obj + 0x160 + 2 * k, 0)
        for k in range(0, 0x48, 8):
            self.w64(obj + 0x148 + k, self.u64(item + k))
        flags = (self.u32(obj + 0xC) | 0x102000) & 0xFFFFE7FF
        w32(obj + 0xC, flags)
        if self.u64(obj + 0x150) & ITEM_ALL_PLAYERS:
            w32(obj + 0xC, flags & 0xFFFFCFFF)
        self.call('obj_updateGridCell', obj)

    def item_prop_ctor3(self, obj, pos, item, matrix):
        """ItemProp_ctor3 0x1592bc (obj, position, item record, matrix): the item at REST,
        made by PhProp_run when a flying item settles.  Prop_ctorNamed(obj, copy of the
        position, 'equipmnt.lmp', the row's model and texture, part mask -1, prop flags 0,
        matrix), then item_record.  Prop flags 0 means no obj_runEveryFrame: a resting item
        has no per-frame body.  ONE SHARED DRAW (GameObject_ctor), no own draw."""
        model, texture = self.item_names(item)
        self.prop_ctor_named(obj, tuple(pos), S_ITEMS_LUMP, model, texture, M64, 0, matrix)
        self.item_record(obj, item)

    def item_prop_ctor2(self, obj, pos, item, launch):
        """ItemProp_ctor2 0x1590ec (obj, position, item record, launch flags): Prop_ctor-
        NamedLaunch(obj, copy of the position, 'equipmnt.lmp', the row's names, part mask -1,
        launch) - ONE SHARED DRAW, the facing's own draw and the launch's (tools/ref_phprop.py)
        - then item_record, then +0x110 = mat34_setPosRotZ(the position now, s16(facing +
        0x4000))."""
        model, texture = self.item_names(item)
        self.prop_ctor_named_launch(obj, tuple(pos), S_ITEMS_LUMP, model, texture, M64, launch)
        self.item_record(obj, item)
        angle = s16((self.u16(obj + 0x38) + 0x4000) & 0xFFFF)
        m = C.mat34_set_pos_rot_z(self.vec(obj + 0x10), angle)
        for k, word in enumerate(m):
            self.w32(obj + 0x110 + 4 * k, word)

    def prop_ctor_named(self, obj, pos, lump, model, texture, mask, prop_flags, matrix):
        """Prop_ctorNamed 0x153ac0 (obj, position, lump, model, texture, 64-bit part mask, prop
        flags, matrix).  GameObject_ctor(obj, copy, 0, 0) - ONE SHARED DRAW; flags |= 0x1809,
        table 0x511d58, obj_updateGridCell; +0x140 = prop flags | 1; radius +0x1c = 4; the
        matrix's 0x30 bytes to +0x110; the three names copied to +0x54/+0x64/+0xa4, +0x4c and
        +0x50 = res_find of model and texture; +0xe8 = the mask.  Prop flag 2: obj_run-
        EveryFrame and flags |= 0x4000; prop flag 4: flags |= 0x1000."""
        self.gameobject_ctor(obj, pos, 0, 0)
        flags = self.u32(obj + 0xC) | 0x1809
        self.w32(obj + 0x48, PP.VT_PROP)
        self.w32(obj + 0xC, flags)
        self.call('obj_updateGridCell', obj)
        self.w16(obj + 0x140, prop_flags | 1)
        self.w32(obj + 0x1C, PP.F_FOUR)
        for k in range(0, 0x30, 8):
            self.w64(obj + 0x110 + k, self.u64(matrix + k))
        self.strcpy(obj + 0x54, lump)
        self.strcpy(obj + 0x64, model)
        self.strcpy(obj + 0xA4, texture)
        self.w32(obj + 0x4C, self.call('res_find', obj + 0x54, obj + 0x64))
        texture_entry = self.call('res_find', obj + 0x54, obj + 0xA4)
        self.w32(obj + 0x50, texture_entry)
        self.w64(obj + 0xE8, mask)
        if self.u16(obj + 0x140) & 2:
            self.call('obj_runEveryFrame', obj)
            self.w32(obj + 0xC, self.u32(obj + 0xC) | 0x4000)
        if self.u16(obj + 0x140) & 4:
            self.w32(obj + 0xC, self.u32(obj + 0xC) | 0x1000)

    # ---- Prop_run ----------------------------------------------------------------------------
    def prop_run(self, prop):
        """Prop_run 0x154514 (prop), slot 4 of Prop and ItemProp: a launched prop's frame.

        While prop flag 1 (+0x140) is clear (moving):
          the step (vx, vy, 0) x 1/60 from +0xfc, +0x100; when 0.001 < vx^2 + vy^2 (scaled):
            t = terrain_sweepCircle(g_world, position, step, 1, normal; radius +0x1c);
            the position gains step x t, obj_updateGridCell; when t < 1 and d = 0.001 -
            (n.x vx + n.y vy) > 0: vx += n.x d 1.5, vy += n.y d 1.5 (slide off the wall);
          ground = terrain_heightBelow(g_world, position; radius); vz +0x30 -= 26.999998;
          z += vz / 60; at or below ground + +0x108 with vz <= 0: z = that, vx, vy x 0.98,
          vz = -vz x 0.4 when vz < -0.1, else 0; then the spin: facing +0x38 += +0x10c,
          +0x10c -= 10 (not below 0).
        Every tick: the life +0x10e loses one; at <= 0 a moving prop gets flag 1 and, unless
        +0x140 has 2, obj_stopRunning (and nothing more this tick).  Below -60 it sinks
        (+0x18 and the matrix z +0x13c lose 0.1); below -300 slot 1 (prop, 3) deletes it.
        Otherwise, with players: obj_delete when its z + 120 is below the z of the object of
        g_players[g_alivePlayers[0]].  No draws."""
        u16, u32, w16, w32 = self.u16, self.u32, self.w16, self.w32
        if not u16(prop + 0x140) & 1:
            vx, vy = C.mul(u32(prop + 0xFC), F_DT), C.mul(u32(prop + 0x100), F_DT)
            step = [vx, vy, ZERO]
            vxx = C.mul(vx, vx)
            if C.lt(F_MILLI, C.add(vxx, C.mul(vy, vy))):
                t, normal = self.call('terrain_sweepCircle', u32(G_WORLD), self.vec(prop + 0x10), tuple(step), 1,
                                      u32(prop + 0x1C))
                step = [C.mul(v, t) for v in step]
                x, y, z = self.vec(prop + 0x10)
                w32(prop + 0x14, C.add(y, step[1]))
                w32(prop + 0x18, C.add(z, step[2]))
                w32(prop + 0x10, C.add(x, step[0]))
                self.call('obj_updateGridCell', prop)
                if C.lt(t, ONE):
                    vx, vy = u32(prop + 0xFC), u32(prop + 0x100)
                    d = C.sub(F_MILLI, C.add(C.mul(normal[0], vx), C.mul(normal[1], vy)))
                    if C.lt(ZERO, d):
                        ny = C.mul(C.mul(normal[1], d), F_ONE_HALF)
                        nx = C.mul(C.mul(normal[0], d), F_ONE_HALF)
                        w32(prop + 0x100, C.add(vy, ny))
                        w32(prop + 0xFC, C.add(vx, nx))
            ground = self.call('terrain_heightBelow', u32(G_WORLD), self.vec(prop + 0x10), u32(prop + 0x1C))
            floor = C.add(u32(prop + 0x108), ground)
            vz = C.sub(u32(prop + 0x30), F_GRAVITY)
            z = C.add(u32(prop + 0x18), C.mul(vz, F_DT))
            w32(prop + 0x30, vz)
            w32(prop + 0x18, z)
            if C.le(z, floor) and C.le(vz, ZERO):
                w32(prop + 0x18, floor)
                w32(prop + 0xFC, C.mul(u32(prop + 0xFC), F_ROLL))
                w32(prop + 0x100, C.mul(u32(prop + 0x100), F_ROLL))
                w32(prop + 0x30, C.mul(C.neg(vz), F_BOUNCE) if C.lt(vz, F_BOUNCE_MIN) else ZERO)
            spin = u16(prop + 0x10C)
            w16(prop + 0x38, u16(prop + 0x38) + spin)
            w16(prop + 0x10C, spin - 10)
            if s16((spin - 10) & 0xFFFF) < 0:
                w16(prop + 0x10C, 0)
        life = (u16(prop + 0x10E) - 1) & 0xFFFF
        w16(prop + 0x10E, life)
        if s16(life) <= 0:
            bits = u16(prop + 0x140)
            if not bits & 1:
                w16(prop + 0x140, bits | 1)
                if not (bits | 1) & 2:
                    self.call('obj_stopRunning', prop)
                    return
        life = self.s16(prop + 0x10E)
        if life < -60:
            w32(prop + 0x18, C.sub(u32(prop + 0x18), F_SINK))
            w32(prop + 0x13C, C.sub(u32(prop + 0x13C), F_SINK))
            if life < -300:
                if prop:
                    self.vcall_slot(prop, 1, 3)
                return
        if self.s32(G_NUM_PLAYERS) <= 0:
            return
        alive = self.s32(G_ALIVE_PLAYERS)
        if alive < 0:
            return
        obj = u32(record(alive) + REC_OBJ)
        if not obj:
            return
        if C.lt(C.add(u32(prop + 0x18), F_120), u32(obj + 0x18)):
            self.call('obj_delete', prop)


__all__ = ['Model', 'EXECUTED', 'EXTERNALS', 'CLASS_BODIES', 'MODELLED']
