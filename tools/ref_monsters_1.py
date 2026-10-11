#!/usr/bin/env python3
"""ref_monsters_1.py - reference model of five ordinary monster classes of Champions: Return
to Arms (SLUS_209.73, US v2.00): the small common enemies, batch 1 (SmallSpider, Gnaw,
Mosquito, Scorpion, Badger).

A research tool, not game code.  It sits on tools/ref_arena_monsters.py (which adds
Creature_ctor and the small target helpers to the creature base class of
tools/ref_creature.py) and adds, as methods of Model:

    SmallSpider   smallspider_ctor 0x2ab450   smallspider_run 0x2ab5d8
                  smallspider_set_state 0x2ab704   smallspider_on_touch 0x2ab8e0 (slot 6)
    Gnaw          gnaw_ctor 0x26741c   gnaw_run 0x267654   gnaw_set_state 0x267a0c
    Mosquito      mosquito_ctor 0x297788   mosquito_run 0x297b30
                  mosquito_set_state 0x297f54   mosquito_lose_part 0x2982cc
    Scorpion      scorpion_ctor 0x2a4d68   scorpion_run 0x2a5068
                  scorpion_set_state 0x2a55ec   scorpion_sever_part 0x2a59f0
    Badger        badger_ctor 0x244018   badger_run 0x244380   badger_set_state 0x244aa4
                  (slot 11, 0x244a9c, is an empty body)
    and the one helper they share that no other model has
                  str_prefix_differs 0x159c20

Every method was written from the instructions at the address in its docstring and is
compared with that code, executed under tools/ee_emu.py, by tools/difftest_monsters_1.py.
docs/spec/monsters-1.md is the prose version and says what the comparison covers.
Standard library only; no game data is embedded: strings, tables, class definitions and
the two double constants a constructor uses are named by address and read through the
memory the caller supplies.  The software doubles two constructors use are
tools/ref_core.py's (they truncate).

How it sees the game: exactly as tools/ref_arena_monsters.py does - a memory image, callbacks
for everything outside the models (EXTERNALS below extends that module's list), canonical
arguments (integers as unsigned 32-bit, floats as patterns, a vector as a tuple of three
patterns).  A virtual call through object +0x48 runs a body of CLASS_BODIES here, a body
the two models underneath have there, and is the callback 'Creature.v<slot>' otherwise.

Call-outs to what other models own: the animation functions (tools/ref_anim.py),
Creature_setStats and damage_apply behind the hit helpers (tools/ref_combat.py),
GameObject_ctor, pool_new and the run lists (tools/ref_core.py, tools/ref_objects.py).

No function here draws from the shared seed 0x404464 itself (Model.draws stays what the
base class made of it); every random choice is the object's own generator (+0x44).
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_arena_monsters as AM                 # noqa: E402
from ref_creature import Ext, M32, M64, s8, s16, s32      # noqa: E402,F401

# ---------------------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------------------
G_SIM_FRAME = RC.G_SIM_FRAME
G_DIFFICULTY = 0x4F719C                         # g_difficultyIdx (shared game state)
G_CTYPE = 0x5628E1                              # the C library's character-class table (+1); bit 0 = upper case
D_GNAW_SCALE_MUL, D_GNAW_SCALE_ADD = 0x545EA0, 0x545EA8        # two double constants (0.3, 0.45)

VT_SMALLSPIDER, VT_GNAW, VT_MOSQUITO = 0x50FD40, 0x515038, 0x516A08
VT_SCORPION, VT_BADGER = 0x50FE88, 0x510F30
DEF_SMALLSPIDER, DEF_GNAW, DEF_MOSQUITO = 0x502818, 0x5000A0, 0x5017A0     # class definitions
DEF_SCORPION = 0x502238
DEF_BADGER, DEF_BADGER_STEP = 0x4FECF8, 0xA0    # one definition per variant
S_MOSQUITO_LARGE = 0x549AF0                     # type-name prefix of the full-size mosquito
S_SCORPION_ITEM = 0x54B648                      # the named item a scorpion's loot call is given
D_0_75 = 0x3FE8000000000000                     # the double 0.75 (an immediate in Scorpion_ctor)

# float patterns
ZERO, HALF, ONE = RC.ZERO, RC.HALF, RC.ONE
F_2M16 = RC.F_2M16
F_0_05, F_0_1, F_0_2, F_0_3, F_0_4 = 0x3D4CCCCC, 0x3DCCCCCC, 0x3E4CCCCC, 0x3E999999, 0x3ECCCCCC
F_0_25, F_0_5, F_0_6, F_0_7, F_0_8, F_0_9 = 0x3E800000, 0x3F000000, 0x3F199999, 0x3F333333, 0x3F4CCCCC, 0x3F666666
F_1_2, F_1_4, F_1_5, F_1_6, F_2, F_2_8, F_3 = 0x3F999999, 0x3FB33333, 0x3FC00000, 0x3FCCCCCC, 0x40000000, 0x40333333, 0x40400000
F_5, F_6, F_10, F_15, F_20, F_24, F_25 = 0x40A00000, 0x40C00000, 0x41200000, 0x41700000, 0x41A00000, 0x41C00000, 0x41C80000
F_30, F_35, F_36, F_40, F_50, F_60, F_100 = 0x41F00000, 0x420C0000, 0x42100000, 0x42200000, 0x42480000, 0x42700000, 0x42C80000

# The original functions this module implements (name -> address);
# tools/difftest_monsters_1.py runs exactly these (and the two models underneath) for real.
MODELLED = {
    'SmallSpider_ctor': 0x2AB450, 'SmallSpider_run': 0x2AB5D8, 'SmallSpider_setState': 0x2AB704,
    'SmallSpider_onTouch': 0x2AB8E0,
    'Gnaw_ctor': 0x26741C, 'Gnaw_run': 0x267654, 'Gnaw_setState': 0x267A0C,
    'Mosquito_ctor': 0x297788, 'Mosquito_run': 0x297B30, 'Mosquito_setState': 0x297F54,
    'Mosquito_losePart': 0x2982CC,
    'Scorpion_ctor': 0x2A4D68, 'Scorpion_run': 0x2A5068, 'Scorpion_setState': 0x2A55EC,
    'Scorpion_severPart': 0x2A59F0,
    'Badger_ctor': 0x244018, 'Badger_run': 0x244380, 'Badger_setState': 0x244AA4, 'Badger_slot11': 0x244A9C,
    'str_prefixDiffers': 0x159C20,
}

# virtual bodies of Creature-derived objects this module has: function -> (slot, method)
CLASS_BODIES = {
    0x2AB5D8: (4, 'smallspider_run'), 0x2AB704: (27, 'smallspider_set_state'), 0x2AB8E0: (6, 'smallspider_on_touch'),
    0x267654: (4, 'gnaw_run'), 0x267A0C: (27, 'gnaw_set_state'),
    0x297B30: (4, 'mosquito_run'), 0x297F54: (27, 'mosquito_set_state'),
    0x2A5068: (4, 'scorpion_run'), 0x2A55EC: (27, 'scorpion_set_state'),
    0x244380: (4, 'badger_run'), 0x244AA4: (27, 'badger_set_state'), 0x244A9C: (11, 'slot_empty'),
}

EXTERNALS = dict(AM.EXTERNALS)
EXTERNALS.update({
    'anim_randomizeTopTime': Ext(0x16D0B8, 'p', 0, 'n', '(anim state): start phase of the top clip from the cosmetic seed'),
    'Creature_hitTargetInArcEdge': Ext(0x119850, 'piiiiiii', 2, 'i', 'as Creature_hitTargetInArc, with the edge sight test'),
    'Creature_hitTargetAtReach': Ext(0x1196E8, 'piiiiE', 1, 'i', '(creature, min, max, attack rating, damage flags, '
                                     'descriptor or 0; reach) -> hit'),
    'GutChunk_ctorFromProp': Ext(0x201AD0, 'pviipiii', 1, 'n', '(block, position, facing, model, anim state, three words '
                                 'of the class definition; scale)'),
})


def shape_result(name, args, ret=0, fret=0, outs=None):
    """What a callback hands back, built from its EXTERNALS row (ref_arena_monsters.shape_result
    for this module's rows).  One more argument kind: 'E', a damage descriptor a caller built
    on its stack, passed as ('desc', four slots) where a slot is (effect id, v1, v2, v3) or
    None for a free one - or 0 for no descriptor."""
    ext = EXTERNALS[name]
    values, position, given = [], 0, list(outs) if outs is not None else None
    for kind in ext.ints:
        if kind in 'oOwWbnL':
            if given:
                value = given.pop(0)
            else:
                value = (0, 0, 0) if kind in 'oO' else ([] if kind in 'nL' else 0)
            if kind not in 'OW' or args[position]:
                values.append(value)
        if kind in 'ipvelsSOWE':
            position += 1
    if ext.ret == 's':
        return ('buf', given[0] if given else b'')
    head = [] if ext.ret == 'n' else [fret if ext.ret == 'f' else ret]
    result = head + values
    if not result:
        return None
    return result[0] if len(result) == 1 else tuple(result)


class Model(AM.Model):
    """Batch 1 of the ordinary monster classes on a memory image.  See the module docstring."""

    # ---- plumbing ----------------------------------------------------------------------
    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    def vcall(self, obj, slot, *args):
        """A virtual call through object +0x48: a body of CLASS_BODIES runs here, otherwise
        as ref_arena_monsters does it."""
        table = self.u32(obj + 0x48)
        body = CLASS_BODIES.get(self.u32(table + 8 * slot + 4))
        if body is not None and ('Creature.v%d' % slot) not in self.external:
            this = (obj + self.s16(table + 8 * slot)) & M32
            return getattr(self, body[1])(this, *args)
        return AM.Model.vcall(self, obj, slot, *args)

    def anim_flags(self, c, mask):
        return self.u16(c + 0x11A) & mask

    def see(self, c, arc, far, near=ZERO, facing=None):
        """Creature_canSeeTargetIn around the creature's own facing (or the one given), ray
        mode 0, lead 0."""
        if facing is None:
            facing = self.s16(c + 0x38)
        return self.can_see_target_in(c, facing, arc, 0, near, far, ZERO)

    def start(self, c, offset, flags, blend=F_0_1):
        self.call('anim_start', c + 0x114, self.clip(c, offset), flags, blend)

    def swing(self, c, offset, flags):
        self.call('anim_startBlendInOut', c + 0x114, self.clip(c, offset), flags, F_0_1, F_0_1)

    def dead_update(self, c, ev, flag, size, push=(0, 0, 0)):
        self.call('Creature_deadUpdate', c, ev, push, flag, size)

    def drop_loot(self, c, item, f3, f4, f5):
        """Creature_dropLoot with the position, the facing and the six floats every class of
        this batch passes (36, 2, a, b, c, 0.25) and a named extra item or 0."""
        self.call('Creature_dropLoot', c, self.vec(c + 0x10), self.s16(c + 0x38), item,
                  F_36, F_2, f3, f4, f5, F_0_25)

    def events(self, c, table):
        for entry, masks, times in table:
            self.set_def_entry_params(c, entry, masks, times)

    # =====================================================================================
    # A helper of the object factory two constructors use
    # =====================================================================================
    def str_prefix_differs(self, text, prefix):
        """str_prefixDiffers 0x159c20 (text, prefix) -> 0 when the text starts with the
        prefix, compared without case (an upper-case letter of either side, by the C
        library's class table, is lowered by adding 0x20), else 1."""
        index = 0
        while True:
            want = self.s8(prefix + index)
            if want == 0:
                return 0
            have = self.s8(text + index)
            index += 1
            if self.u8((G_CTYPE + want) & M32) & 1:
                want += 0x20
            if self.u8((G_CTYPE + have) & M32) & 1:
                have += 0x20
            if have != want:
                return 1

    # =====================================================================================
    # SmallSpider
    # =====================================================================================
    def smallspider_ctor(self, c, type_name, pos, facing, props):
        """SmallSpider_ctor 0x2ab450 (object, type name, position, facing, property list).

        Creature_ctor with class definition 0x502818 and 1.0 placeholder hit points; move
        speed 50, radius 5 (10 is stored first), turn rate 0.7, kind 0x12, scale 0.2,
        +0x64 = 1.0, creature flags |= 0x8004001000 (0x4000000 = nobody's enemy and picks
        no target).  The facing is stored a second time, as it was passed.  The idle clip (+0x3c) is pushed and its phase randomised from the
        cosmetic seed; a 60-frame run list; Creature_init.  No own draw, no event table."""
        w32 = self.w32
        self.creature_ctor(c, type_name, pos, s16(facing), DEF_SMALLSPIDER, props, ONE)
        w32(c + 0xB8, F_50)
        w32(c + 0x1C, F_10)
        w32(c + 0x48, VT_SMALLSPIDER)
        self.w16(c + 0x38, facing)
        w32(c + 0xB0, F_0_7)
        self.w16(c + 0x232, 0)
        self.w8(c + 0xB4, 0x12)
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x8004001000)
        w32(c + 0xEC, self.u32(G_SIM_FRAME))
        w32(c + 0x1C, F_5)
        w32(c + 0xDC, F_0_2)
        w32(c + 0x64, ONE)
        self.call('anim_push', c + 0x114, self.clip(c, 0x3C), 1)
        self.call('anim_randomizeTopTime', c + 0x114)
        self.w16(c + 0x232, 0)
        self.call('obj_runEvery60', c)
        self.call('Creature_init', c)

    def smallspider_run(self, c):
        """SmallSpider_run 0x2ab5d8 (creature): one tick.

        Creature_processDamage, Creature_run, Creature_updateActive - an inactive spider
        stops here - Creature_stepAnim(1.0), Creature_applyKnockback(1.0).  No target pick
        and no attack.  State 0: set-state 1 once the clock has passed +0xf4.  State 1:
        Creature_moveToDest.  State 0x14: Creature_deadUpdate(10.0).  Any other state:
        nothing."""
        self.process_damage(c, self.class_model(c))
        if self.run(c, self.class_model(c)):
            return
        if not self.update_active(c):
            return
        ev = self.step_anim(c, ONE)
        self.call('Creature_applyKnockback', c, ONE)
        state = self.s16(c + 0x232)
        if state == 1:
            self.move_to_dest(c)
        elif state == 0:
            if self.s32(c + 0xF4) < self.s32(c + 0x300):
                self.set_state(c, 1)
        elif state == 0x14:
            self.dead_update(c, ev, 0, F_10)

    def smallspider_set_state(self, c, state):
        """SmallSpider_setState 0x2ab704 (creature, state): slot 27.

        After Creature_filterState:
          0     ONE OWN DRAW d: +0xf4 = clock + 120 + d % 300; the idle clip
          1     path cleared, wander destination, the walk clip
          5, 0x10, 0x12, 0x13   ignored: the state stays what it was
          0x14  object flags |= 9; THREE OWN DRAWS: a decal (angle = draw 1, size 10 +
                draw 2 % 10, kind 6), one of four death clips (draw 3 & 3) - jumped to its
                end for a hidden spider - then slot 28 (on death).  No loot.
          anything else: the number is stored and nothing is done."""
        refused, state = self.filter_state(c, state)
        if refused:
            return
        if state == 0:
            draw = self.obj_rand(c)
            self.w32(c + 0xF4, self.u32(c + 0x300) + draw % 300 + 120)
            self.start(c, 0x3C, 3, F_0_3)
        elif state == 1:
            self.clear_path(c)
            self.pick_wander_dest(c)
            self.start(c, 0x4C, 3, F_0_3)
        elif state in (5, 0x10, 0x12, 0x13):
            state = self.s16(c + 0x232)
        elif state == 0x14:
            self.w32(c + 0xC, self.u32(c + 0xC) | 9)
            angle = self.obj_rand(c)
            size = self.obj_rand(c) % 10 + 10
            self.call('decal_add', self.vec(c + 0x10), s16(angle), 6, 1, C.from_int(size))
            self.start(c, 0x1C + 8 * (self.obj_rand(c) & 3), 6, F_0_3)
            if self.u32(c + 0xC) & 2:
                self.call('anim_jumpTopToEnd', c + 0x114)
            self.vcall(c, 28, 0)
        self.w16(c + 0x232, state)

    def smallspider_on_touch(self, c, other):
        """SmallSpider_onTouch 0x2ab8e0 (creature, toucher): slot 6.  Touched by an object
        with flag 0x40 (a player) while not in state 0x14: slot 27 (0x14) - it is squashed.
        Then the base body (0x11a418)."""
        if other and self.s16(c + 0x232) != 0x14 and self.u32(other + 0xC) & 0x40:
            self.set_state(c, 0x14)
        self.slot6_touched(c, other)

    # =====================================================================================
    # Gnaw
    # =====================================================================================
    GNAW_EVENTS = tuple((entry, (1, 0, 0, 0), (F_0_2, 0, 0, 0)) for entry in (3, 4, 5))

    def gnaw_ctor(self, c, type_name, pos, facing, props):
        """Gnaw_ctor 0x26741c (object, type name, position, facing, property list).

        Creature_ctor with class definition 0x5000a0; kind 1, turn rate 1.2, radius 6, move
        speed 0, creature flags |= 0x200001000, +0xf4 = frame + 300.  ONE OWN DRAW d sets
        the scale: (float)((double)(d x 2^-16) x 0.3 + 0.45), in the software doubles
        (truncating).  State 0 through its own set-state, the EVERY-FRAME run list, the
        three bite clips' event (0.2 s -> bit 0), Creature_init."""
        w32 = self.w32
        self.creature_ctor(c, type_name, pos, s16(facing), DEF_GNAW, props, F_10)
        frame = self.u32(G_SIM_FRAME)
        self.w8(c + 0xB4, 1)
        w32(c + 0xB0, F_1_2)
        w32(c + 0xEC, frame)
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x200001000)
        w32(c + 0x48, VT_GNAW)
        w32(c + 0x1C, F_6)
        w32(c + 0xF4, frame + 300)
        w32(c + 0xB8, 0)
        self.w16(c + 0x232, 0)
        unit = C.f2d(C.mul(C.from_int(self.obj_rand(c)), F_2M16))
        w32(c + 0xDC, C.d2f(C.dadd(C.dmul(unit, self.u64(D_GNAW_SCALE_MUL)), self.u64(D_GNAW_SCALE_ADD))))
        self.call('anim_clear', c + 0x114)
        self.gnaw_set_state(c, 0)
        self.call('obj_runEveryFrame', c)
        self.events(c, self.GNAW_EVENTS)
        self.call('Creature_init', c)

    def gnaw_run(self, c):
        """Gnaw_run 0x267654 (creature): one tick.

        Creature_processDamage and Creature_run with the model from slot 16;
        Creature_updateActive - inactive ends the tick - Creature_stepAnim(1.0),
        Creature_applyKnockback(1.0), slot 23, then the switch on the state (read as an
        unsigned 16-bit number; 0x15 and up go to the last row):

          0     slot 25 (0) -> 3; else away from home -> 1
          1     slot 25 (0) -> 3; else Creature_moveToDest
          3     no target -> 0; target within 6 in arc 8000 -> 5; within 6 any direction ->
                turn; else Creature_moveToTarget
          5     within 6 in arc 8000 -> 6; within 6 any direction -> turn; else not rooted -> 3
          6     turn; on event bit 0 the hit (0-6, arc 8000, flags 8, no descriptor);
                clip no longer playing -> 5
          0x10  attack ready -> 0, else flee        0x12  reaction clip over -> 5
          0x13  not stunned -> 3
          0x14  Creature_deadUpdate(flag 1; 20.0) and obj_delete, every tick
          else  -> 0"""
        st = self.set_state
        self.process_damage(c, self.vcall(c, 16))
        if self.run(c, self.vcall(c, 16)):
            return
        if not self.update_active(c):
            return
        ev = self.step_anim(c, ONE)
        self.call('Creature_applyKnockback', c, ONE)
        self.vcall(c, 23, 0)
        state = self.u16(c + 0x232)
        if state == 0:
            if self.vcall(c, 25, 0):
                return st(c, 3)
            if self.is_away_from_home(c):
                return st(c, 1)
        elif state == 1:
            if self.vcall(c, 25, 0):
                return st(c, 3)
            self.move_to_dest(c)
        elif state == 3:
            if not self.u32(c + 0x234):
                return st(c, 0)
            if self.see(c, 8000, F_6):
                return st(c, 5)
            if self.see(c, 0x7FFF, F_6):
                self.turn_to_target(c)
            else:
                self.move_to_target(c)
        elif state == 5:
            if self.see(c, 8000, F_6):
                return st(c, 6)
            if self.see(c, 0x7FFF, F_6):
                self.turn_to_target(c)
            elif self.is_not_rooted(c):
                return st(c, 3)
        elif state == 6:
            self.turn_to_target(c)
            if ev & 1:
                self.call('Creature_hitTargetInArc', c, self.s16(c + 0x38), 8000, self.s16(c + 0xD0),
                          self.s16(c + 0xD2), self.s16(c + 0xD4), 8, 0, ZERO, F_6)
            if not self.anim_flags(c, 8):
                return st(c, 5)
        elif state == 0x10:
            if self.is_attack_ready(c):
                return st(c, 0)
            self.flee_from_target(c, 0)
        elif state == 0x12:
            if not self.anim_flags(c, 0x10):
                return st(c, 5)
        elif state == 0x13:
            if self.is_not_stunned(c):
                return st(c, 3)
        elif state == 0x14:
            self.dead_update(c, ev, 1, F_20)
            self.call('obj_delete', c)
        else:
            return st(c, 0)

    def gnaw_set_state(self, c, state):
        """Gnaw_setState 0x267a0c (creature, state): slot 27.

        After Creature_filterState:
          0     the first bite clip (+0x1c) looping - the class has no idle clip
          1     path cleared, wander destination, the move clip (+0x3c), frame sync
          3     path cleared, the move clip (no sync)
          5     ONE OWN DRAW d: bite clip d % 3 looping, frame sync
          6     ONE OWN DRAW d: bite clip d % 3 as a swing
          0x10  cooldown +0x318 = 60, path cleared, the second move clip (+0x34), frame sync
          0x12  ignored: the state stays what it was
          0x13  the first bite clip, blend 0.3
          0x14  six times effect 9 at 24 above the position; for the first two a GutChunk
                (pool 0x268, variant = OWN DRAW % 3, kind 2) with physics kind 0x12 - the
                draw is made only when the pool gave a block; the first bite clip with
                flags 0x803; slot 28 (on death).  No loot.
          anything else: state 0 is stored and nothing is done."""
        refused, state = self.filter_state(c, state)
        if refused:
            return
        anim = c + 0x114
        if state == 0:
            self.start(c, 0x1C, 3)
        elif state == 1:
            self.clear_path(c)
            self.pick_wander_dest(c)
            self.start(c, 0x3C, 0x803)
            self.call('anim_syncToSimFrame', anim)
        elif state == 3:
            self.clear_path(c)
            self.start(c, 0x3C, 0x803)
        elif state == 5:
            self.start(c, 0x1C + 8 * (self.obj_rand(c) % 3), 3)
            self.call('anim_syncToSimFrame', anim)
        elif state == 6:
            self.swing(c, 0x1C + 8 * (self.obj_rand(c) % 3), 0x808)
        elif state == 0x10:
            self.w16(c + 0x318, 60)
            self.clear_path(c)
            self.start(c, 0x34, 0x803)
            self.call('anim_syncToSimFrame', anim)
        elif state == 0x12:
            state = self.s16(c + 0x232)
        elif state == 0x13:
            self.start(c, 0x1C, 3, F_0_3)
        elif state == 0x14:
            for index in range(6):
                spot = (self.u32(c + 0x10), self.u32(c + 0x14), C.add(self.u32(c + 0x18), F_24))
                if index < 2:
                    block = self.call('pool_new', 0x268)
                    if block:
                        self.call('GutChunk_ctor', block, spot, self.obj_rand(c) % 3, 2, ONE)
                        self.call('PhProp_initPhysics', block, 0x12)
                self.call('fx_spawn', 9, spot)
            self.start(c, 0x1C, 0x803)
            self.vcall(c, 28, 0)
        else:
            state = 0
        self.w16(c + 0x232, state)

    # =====================================================================================
    # Mosquito
    # =====================================================================================
    MOSQUITO_EVENTS = (
        (3, (1, 0, 0, 0), (F_0_2, 0, 0, 0)), (4, (1, 0, 0, 0), (F_0_2, 0, 0, 0)),       # the two bites
        (5, (0x80, 0, 0, 0), (ONE, 0, 0, 0)), (6, (0x80, 0, 0, 0), (F_1_5, 0, 0, 0)),   # the four death clips
        (7, (0x80, 0, 0, 0), (F_1_5, 0, 0, 0)), (8, (0x80, 0, 0, 0), (F_0_5, 0, 0, 0)),
    )
    MOSQUITO_PART_BITS = {1: 0x10, 2: 0x10, 3: 0x40, 4: 2, 5: 1, 6: 4, 7: 8}

    def mosquito_ctor(self, c, pos, facing, props, type_name):
        """Mosquito_ctor 0x297788 (object, position, facing, property list, type name).

        Creature_ctor with class definition 0x5017a0; +0x28 = 0x1e, kind 0x12, turn rate
        1.2, radius 10, move speed 0, +0xf4 = frame + 300, creature flags |= 0x8000001000,
        resistances +0x5c = -0.2, +0x64 = +0x68 = 1.0.  Scale 0.7 unless the type name
        starts with the text at 0x549af0 (the large kind keeps 1.0).  State 0 through its
        own set-state (ONE OWN DRAW), a 60-frame run list, six clips' event times,
        Creature_init."""
        w32 = self.w32
        self.creature_ctor(c, type_name, pos, s16(facing), DEF_MOSQUITO, props, F_10)
        frame = self.u32(G_SIM_FRAME)
        self.w8(c + 0x28, 0x1E)
        self.w8(c + 0xB4, 0x12)
        w32(c + 0x48, VT_MOSQUITO)
        w32(c + 0xB0, F_1_2)
        w32(c + 0x1C, F_10)
        w32(c + 0xEC, frame)
        w32(c + 0xF4, frame + 300)
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x8000001000)
        w32(c + 0x5C, 0xBE4CCCCC)
        w32(c + 0xB8, 0)
        self.w16(c + 0x232, 0)
        w32(c + 0x64, ONE)
        w32(c + 0x68, ONE)
        if self.str_prefix_differs(type_name, S_MOSQUITO_LARGE):
            w32(c + 0xDC, F_0_7)
        self.call('anim_clear', c + 0x114)
        self.mosquito_set_state(c, 0)
        self.call('obj_runEvery60', c)
        self.events(c, self.MOSQUITO_EVENTS)
        self.call('Creature_init', c)

    def mosquito_run(self, c):
        """Mosquito_run 0x297b30 (creature): one tick.

        Creature_processDamage, Creature_run, Creature_updateActive - inactive ends the
        tick - Creature_stepAnim(1.0), Creature_applyKnockback(1.5), slot 23, then:

          0     slot 25 (0) -> 3; else away from home -> 1
          1     slot 25 (0) -> 0; else Creature_moveToDest unless animation flag 0x20
          3     no target -> 0; nothing while animation flag 0x10; target within 40 in
                arc 6000 -> 6; within 40 any direction -> turn; else Creature_moveToTarget
          5     no target -> 0; turn; within 40 in arc 6000 -> 6; else not rooted -> 3
          6     Creature_moveBy(0); with a target: on event bit 0 the hit
                (Creature_hitTargetInArcEdge 0-40, arc 6000, flags 4), then turn; clip no
                longer playing -> 3
          0x10  attack ready -> 0, else flee
          0x12, 0x17   Creature_moveBy(0); reaction flag 0x10 clear -> 3
          0x13  not stunned -> 3
          0x14  Creature_moveBy(0), Creature_deadUpdate(flag 0; 15.0)
          else  -> 0"""
        st = self.set_state
        self.process_damage(c, self.class_model(c))
        if self.run(c, self.class_model(c)):
            return
        if not self.update_active(c):
            return
        ev = self.step_anim(c, ONE)
        self.call('Creature_applyKnockback', c, F_1_5)
        self.vcall(c, 23, 0)
        state = self.u16(c + 0x232)
        zero = (0, 0, 0)
        if state == 0:
            if self.vcall(c, 25, 0):
                return st(c, 3)
            if self.is_away_from_home(c):
                return st(c, 1)
        elif state == 1:
            if self.vcall(c, 25, 0):
                return st(c, 0)
            if not self.anim_flags(c, 0x20):
                self.move_to_dest(c)
        elif state == 3:
            if not self.u32(c + 0x234):
                return st(c, 0)
            if self.anim_flags(c, 0x10):
                return
            if self.see(c, 6000, F_40):
                return st(c, 6)
            if self.see(c, 0x7FFF, F_40):
                self.turn_to_target(c)
            else:
                self.move_to_target(c)
        elif state == 5:
            if not self.u32(c + 0x234):
                return st(c, 0)
            self.turn_to_target(c)
            if self.see(c, 6000, F_40):
                return st(c, 6)
            if self.is_not_rooted(c):
                return st(c, 3)
        elif state == 6:
            self.move_by(c, zero)
            if self.u32(c + 0x234):
                if ev & 1:
                    self.call('Creature_hitTargetInArcEdge', c, self.s16(c + 0x38), 6000, self.s16(c + 0xD0),
                              self.s16(c + 0xD2), self.s16(c + 0xD4), 4, 0, ZERO, F_40)
                self.turn_to_target(c)
            if not self.anim_flags(c, 8):
                return st(c, 3)
        elif state == 0x10:
            if self.is_attack_ready(c):
                return st(c, 0)
            self.flee_from_target(c, 0)
        elif state in (0x12, 0x17):
            self.move_by(c, zero)
            if not self.anim_flags(c, 0x10):
                return st(c, 3)
        elif state == 0x13:
            if self.is_not_stunned(c):
                return st(c, 3)
        elif state == 0x14:
            self.move_by(c, zero)
            self.dead_update(c, ev, 0, F_15)
        else:
            return st(c, 0)

    def mosquito_set_state(self, c, state):
        """Mosquito_setState 0x297f54 (creature, state): slot 27.

        After Creature_filterState:
          0     the hover clip (+0x84); ONE OWN DRAW d: +0xf4 = clock + d % 120
          1     path cleared, wander destination, the flying clip (+0x64), blend 0.5
          3     path cleared, the flying clip
          5     the hover clip; ONE OWN DRAW d: +0xf4 = clock + 60 + d % 120
          6     ONE OWN DRAW: one of the two bite clips
          0x10  cooldown +0x318 = 60, then as 3
          0x12  TWO OWN DRAWS: one of two reaction clips (& 1), then a part is shed:
                mosquito_lose_part(d % 3 + 1)
          0x13  the hover clip
          0x14  Creature_dropLoot (36, 2, 1.6, 0.6, 1.4, 0.25; no named item); TWO OWN
                DRAWS: one of four death clips (& 3), mosquito_lose_part((d & 3) + 4);
                slot 28 (on death)
          0x17  ONE OWN DRAW: one of the three dodge clips (% 3)
          anything else: state 0 is stored and nothing is done.
        Last, creature flag 0x100000 (no water test) is cleared for a stored state of 0 or
        0x14 and set for every other."""
        refused, state = self.filter_state(c, state)
        if refused:
            return
        if state == 0:
            self.start(c, 0x84, 3)
            self.w32(c + 0xF4, self.u32(c + 0x300) + self.obj_rand(c) % 120)
        elif state == 1:
            self.clear_path(c)
            self.pick_wander_dest(c)
            self.start(c, 0x64, 0x803, F_0_5)
        elif state == 3:
            self.clear_path(c)
            self.start(c, 0x64, 0x803)
        elif state == 5:
            self.start(c, 0x84, 3)
            self.w32(c + 0xF4, self.u32(c + 0x300) + self.obj_rand(c) % 120 + 60)
        elif state == 6:
            self.swing(c, 0x1C + 8 * (self.obj_rand(c) & 1), 0x808)
        elif state == 0x10:
            self.w16(c + 0x318, 60)
            self.clear_path(c)
            self.start(c, 0x64, 0x803)
        elif state == 0x12:
            self.swing(c, 0x6C + 8 * (self.obj_rand(c) & 1), 0x810)
            self.mosquito_lose_part(c, self.obj_rand(c) % 3 + 1)
        elif state == 0x13:
            self.start(c, 0x84, 3)
        elif state == 0x14:
            self.drop_loot(c, 0, F_1_6, F_0_6, F_1_4)
            self.start(c, 0x2C + 8 * (self.obj_rand(c) & 3), 0x806, F_0_2)
            self.mosquito_lose_part(c, (self.obj_rand(c) & 3) + 4)
            self.vcall(c, 28, 0)
        elif state == 0x17:
            self.swing(c, 0x4C + 8 * (self.obj_rand(c) % 3), 0x810)
        else:
            state = 0
        self.w16(c + 0x232, state)
        flags = self.u64(c + 0xA8)
        if s16(state) in (0, 0x14):
            self.w64(c + 0xA8, flags & ~0x100000 & M64)
        else:
            self.w64(c + 0xA8, flags | 0x100000)

    def mosquito_lose_part(self, c, part):
        """Mosquito_losePart 0x2982cc (creature, part 1-7).

        The model-variant word +0xe8 gets the part's bit (1, 2 -> 0x10; 3 -> 0x40; 4 -> 2;
        5 -> 1; 6 -> 4; 7 -> 8; any other number: none) and the show mask +0x220 is
        rebuilt (model_buildHideMask is called once before, its result dropped, and once
        after).  Then, ALWAYS - also when the bit was already set - a GutChunk copy of the
        creature (pool 0x268, GutChunk_ctorFromProp at the creature's position and facing,
        scale 1.0) whose +0x1c4 is raised by 2.0."""
        self.call('model_buildHideMask', self.class_model(c), self.u32(c + 0xE8))
        bit = self.MOSQUITO_PART_BITS.get(part & M32)
        if bit is not None:
            self.w32(c + 0xE8, self.u32(c + 0xE8) | bit)
        self.w64(c + 0x220, self.call('model_buildHideMask', self.class_model(c), self.u32(c + 0xE8)))
        self._shed_chunk(c)

    def _shed_chunk(self, c):
        """The tail two classes share (from the pool_new calls at 0x298378 and 0x2a5a50): a GutChunk copy of the creature
        (pool 0x268; GutChunk_ctorFromProp at the creature's position and facing with the
        model, the animation state and words 0, 2 and 4 of the class definition; scale
        1.0) whose +0x1c4 is raised by 2.0.  Nothing without a block."""
        block = self.call('pool_new', 0x268)
        if block:
            definition = self.u32(c + 0x24)
            self.call('GutChunk_ctorFromProp', block, self.vec(c + 0x10), self.s16(c + 0x38),
                      self.u32(definition + 0xC), c + 0x114, self.u32(definition), self.u32(definition + 8),
                      self.u32(definition + 0x10), ONE)
            self.w32(block + 0x1C4, C.add(self.u32(block + 0x1C4), F_2))

    # =====================================================================================
    # Scorpion
    # =====================================================================================
    SCORPION_EVENTS = tuple((entry, (1, 0, 0, 0), (F_0_3, 0, 0, 0)) for entry in (5, 6, 7, 8)) + \
        tuple((entry, (0x80, 0, 0, 0), (F_0_5, 0, 0, 0)) for entry in (0xB, 0xC))

    def scorpion_ctor(self, c, type_name, pos, facing, props):
        """Scorpion_ctor 0x2a4d68 (object, type name, position, facing, property list).

        Creature_ctor with class definition 0x502238; +0x28 = 0x46, kind 0x12, turn rate
        1.2, move speed 0, resistance +0x64 = 0.4, creature flags |= 0x8000001000.  TWO OWN
        DRAWS: the scale +0xdc = (float)((double)(float(d1 % 6) x 0.05) + 0.75) - 0.75 to
        1.0 in steps of 0.05, through the software doubles - with the radius 30 x scale;
        and the skin byte +0x3c8 = d2 & 1 (which of two textures the draw function uses).
        Variant word 0 and its show mask, the idle clip (+0x84) pushed, a 60-frame run
        list, six clips' event times, Creature_init."""
        w32 = self.w32
        self.creature_ctor(c, type_name, pos, s16(facing), DEF_SCORPION, props, F_10)
        w32(c + 0x1C, F_30)
        w32(c + 0x48, VT_SCORPION)
        w32(c + 0xB0, F_1_2)
        self.w8(c + 0x28, 0x46)
        w32(c + 0xB8, 0)
        self.w16(c + 0x232, 0)
        self.w8(c + 0xB4, 0x12)
        w32(c + 0xEC, self.u32(G_SIM_FRAME))
        w32(c + 0x64, F_0_4)
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x8000001000)
        w32(c + 0xE8, 0)
        step = C.mul(C.from_int(self.obj_rand(c) % 6), F_0_05)
        scale = C.d2f(C.dadd(C.f2d(step), D_0_75))
        w32(c + 0xDC, scale)
        w32(c + 0x1C, C.mul(self.u32(c + 0x1C), scale))
        self.w8(c + 0x3C8, self.obj_rand(c) & 1)
        self.w64(c + 0x220, self.call('model_buildHideMask', self.class_model(c), self.u32(c + 0xE8)))
        self.call('anim_clear', c + 0x114)
        self.call('anim_push', c + 0x114, self.clip(c, 0x84), 1)
        self.call('obj_runEvery60', c)
        self.events(c, self.SCORPION_EVENTS)
        self.call('Creature_init', c)

    def scorpion_run(self, c):
        """Scorpion_run 0x2a5068 (creature): one tick.

        Creature_processDamage, Creature_run, Creature_updateActive - inactive ends the
        tick - Creature_stepAnim(1.0), Creature_applyKnockback(0.5), slot 23, then:

          0     slot 25 (0) -> 3; else away from home -> 1; else clock past +0xf4 -> 1
          1     slot 25 (0) -> 0 (not 3); else Creature_moveToDest
          3     no target -> 0; target within 20 in arc 6000 -> 6; within 20 any direction ->
                turn; else Creature_moveToTarget
          5     within 20 in arc 6000 -> 6; else not rooted -> 3
          6 claw, 7 sting   see scorpion_attack
          0x10  attack ready -> 0, else flee        0x12  reaction clip over -> 3
          0x13  not stunned -> 0
          0x14  Creature_deadUpdate(flag 0; 25.0)
          0x17, 0x18   Creature_moveBy(0); clip no longer playing -> 3
          anything else (2, 4, 8-0xf, 0x11, 0x15, 0x16, 0x19 and up): nothing at all"""
        st = self.set_state
        self.process_damage(c, self.class_model(c))
        if self.run(c, self.class_model(c)):
            return
        if not self.update_active(c):
            return
        ev = self.step_anim(c, ONE)
        self.call('Creature_applyKnockback', c, HALF)
        self.vcall(c, 23, 0)
        state = self.u16(c + 0x232)
        if state == 0:
            if self.vcall(c, 25, 0):
                return st(c, 3)
            if self.is_away_from_home(c):
                return st(c, 1)
            if self.s32(c + 0xF4) < self.s32(c + 0x300):
                return st(c, 1)
        elif state == 1:
            if self.vcall(c, 25, 0):
                return st(c, 0)
            self.move_to_dest(c)
        elif state == 3:
            if not self.u32(c + 0x234):
                return st(c, 0)
            if self.see(c, 6000, F_20):
                return st(c, 6)
            if self.see(c, 0x7FFF, F_20):
                self.turn_to_target(c)
            else:
                self.move_to_target(c)
        elif state == 5:
            if self.see(c, 6000, F_20):
                return st(c, 6)
            if self.is_not_rooted(c):
                return st(c, 3)
        elif state in (6, 7):
            self._scorpion_attack(c, ev)
        elif state == 0x10:
            if self.is_attack_ready(c):
                return st(c, 0)
            self.flee_from_target(c, 0)
        elif state == 0x12:
            if not self.anim_flags(c, 0x10):
                return st(c, 3)
        elif state == 0x13:
            if self.is_not_stunned(c):
                return st(c, 0)
        elif state == 0x14:
            self.dead_update(c, ev, 0, F_25)
        elif state in (0x17, 0x18):
            self.move_by(c, (0, 0, 0))
            if not self.anim_flags(c, 8):
                return st(c, 3)

    def _scorpion_attack(self, c, ev):
        """States 6 (claw) and 7 (sting), 0x2a529c.

        With a target, on event bit 0:
          6   Creature_hitTargetAtReach(reach 36; +0xd0, +0xd2, +0xd4, flags 8, no descriptor)
          7   first, when g_difficultyIdx is 2 the damage range +0xd0, +0xd2 is divided by
              4, when it is 3 by 8 (toward zero), AND WRITTEN BACK to the creature; then
              a descriptor with one effect (id 0x17 poison, the new +0xd0, the new +0xd2,
              0) and the hit with flags 0x10004 and that descriptor.
        While the clip plays (flag 8, read after the hit) and there is a target: turn to
        it.  Once the clip is not playing (read again after the turn), +0xf4 counts down;
        at 0 or below ONE OWN DRAW d: bit 0 -> state 0x17, else bit 1 -> 0x18, else 3."""
        count_down = True
        if self.u32(c + 0x234):
            if ev & 1:
                if self.s16(c + 0x232) != 7:
                    self.call('Creature_hitTargetAtReach', c, self.s16(c + 0xD0), self.s16(c + 0xD2),
                              self.s16(c + 0xD4), 8, 0, F_36)
                else:
                    level = self.u32(G_DIFFICULTY)
                    if level in (2, 3):
                        shift = 2 if level == 2 else 3
                        for off in (0xD0, 0xD2):
                            value = self.s16(c + off)
                            if value < 0:
                                value += (1 << shift) - 1
                            self.w16(c + off, value >> shift)
                    low, high = self.u16(c + 0xD0), self.u16(c + 0xD2)
                    descriptor = ('desc', ((0x17, low, high, 0), None, None, None))
                    self.call('Creature_hitTargetAtReach', c, self.s16(c + 0xD0), self.s16(c + 0xD2),
                              self.s16(c + 0xD4), 0x10004, descriptor, F_36)
            if self.anim_flags(c, 8):
                self.turn_to_target(c)
                count_down = not self.anim_flags(c, 8)
        else:
            count_down = not self.anim_flags(c, 8)
        if count_down:
            self.w32(c + 0xF4, self.u32(c + 0xF4) - 1)
        if self.s32(c + 0xF4) > 0:
            return
        draw = self.obj_rand(c)
        self.set_state(c, 0x17 if draw & 1 else 0x18 if draw & 2 else 3)

    def scorpion_set_state(self, c, state):
        """Scorpion_setState 0x2a55ec (creature, state): slot 27.

        After Creature_filterState:
          0     ONE OWN DRAW d: +0xf4 = clock + 120 + d % 60; the idle clip (+0x84), blend 0.3
          1     path cleared, wander destination, walk clip +0x94
          3, 0x10   path cleared, walk clip +0x9c
          5     the second idle clip (+0x8c)
          6     the second idle clip underneath; OWN DRAW d1: d1 % 6 == 0 -> the state
                becomes 7 and the sting clip (+0x44) starts; else OWN DRAW d2: claw clip
                d2 % 3 (+0x2c ...).  Then OWN DRAW d3: +0xf4 = d3 % 20
          0x12  ignored (the state stays) while stunned (state 0x13) and while a claw clip
                of state 6 is still playing; else the reaction clip (+0x7c)
          0x13  the idle clip, blend 0.3
          0x14  OWN DRAW % 3 == 0 -> scorpion_sever_part(OWN DRAW % 6); Creature_dropLoot
                (36, 2, 1.6, 0.6, 1.4, 0.25) with the named item at 0x54b648; one of two
                death clips (OWN DRAW & 1); slot 28 (on death)
          0x17, 0x18   the second idle clip underneath and a flank clip (+0x6c / +0x74)
          anything else: the number is stored and nothing is done."""
        refused, state = self.filter_state(c, state)
        if refused:
            return
        if state == 0:
            self.w32(c + 0xF4, self.u32(c + 0x300) + self.obj_rand(c) % 60 + 120)
            self.start(c, 0x84, 3, F_0_3)
        elif state == 1:
            self.clear_path(c)
            self.pick_wander_dest(c)
            self.start(c, 0x94, 0x803, F_0_3)
        elif state in (3, 0x10):
            self.clear_path(c)
            self.start(c, 0x9C, 0x803, F_0_3)
        elif state == 5:
            self.start(c, 0x8C, 3)
        elif state == 6:
            self.start(c, 0x8C, 3)
            if self.obj_rand(c) % 6 == 0:
                state = 7
                self.swing(c, 0x44, 8)
            else:
                self.swing(c, 0x2C + 8 * (self.obj_rand(c) % 3), 8)
            self.w32(c + 0xF4, self.obj_rand(c) % 20)
        elif state == 0x12:
            current = self.s16(c + 0x232)
            if current == 0x13 or (current == 6 and self.anim_flags(c, 8)):
                state = current
            else:
                self.swing(c, 0x7C, 0x10)
        elif state == 0x13:
            self.start(c, 0x84, 3, F_0_3)
        elif state == 0x14:
            if self.obj_rand(c) % 3 == 0:
                self.scorpion_sever_part(c, self.obj_rand(c) % 6)
            self.drop_loot(c, S_SCORPION_ITEM, F_1_6, F_0_6, F_1_4)
            self.start(c, 0x5C + 8 * (self.obj_rand(c) & 1), 0x806, F_0_3)
            self.vcall(c, 28, 0)
        elif state in (0x17, 0x18):
            self.start(c, 0x8C, 3)
            self.swing(c, 0x6C if state == 0x17 else 0x74, 0x808)
        self.w16(c + 0x232, state)

    def scorpion_sever_part(self, c, part):
        """Scorpion_severPart 0x2a59f0 (creature, part): the model-variant word +0xe8 gets
        bit `part` (the shift uses its low five bits), the show mask +0x220 is rebuilt
        (model_buildHideMask once before with the old word, result dropped), and a
        GutChunk copy is made (_shed_chunk)."""
        self.call('model_buildHideMask', self.class_model(c), self.u32(c + 0xE8))
        bits = self.u32(c + 0xE8) | (1 << (part & 31))
        model = self.class_model(c)
        self.w32(c + 0xE8, bits)
        self.w64(c + 0x220, self.call('model_buildHideMask', model, bits))
        self._shed_chunk(c)

    # =====================================================================================
    # Badger
    # =====================================================================================
    BADGER_EVENTS = tuple((entry, (1, 2, 0, 0), (F_0_3, F_0_8, 0, 0)) for entry in (4, 5, 6, 7)) + (
        (10, (1, 2, 0, 0), (F_0_5, F_0_9, 0, 0)),
        (0xB, (0x84, 0, 0, 0), (ONE, 0, 0, 0)), (0xC, (0x84, 0, 0, 0), (ONE, 0, 0, 0)),
    )

    def badger_ctor(self, c, type_name, pos, facing, props, variant):
        """Badger_ctor 0x244018 (object, type name, position, facing, property list, variant).

        Creature_ctor with class definition 0x4fecf8 + 0xa0 x variant; kind 3, turn rate
        1.0, move speed 0, creature flags |= 0x200000000, variant byte +0x3cc.
        Variant 1 (the snow kind): radius 25, +0x28 = 0x28, scale 0.8, +0xe0 = -10,
        resistances +0x5c = -0.3, +0x60 = 1.0.  Any other variant: radius 35, +0x28 = 0x2d,
        +0xe0 = -15.  Variant word 0 and its show mask, the idle clip (+0x7c) pushed, a
        60-frame run list, seven clips' event times, Creature_init.  No own draw."""
        w32 = self.w32
        self.creature_ctor(c, type_name, pos, s16(facing), (DEF_BADGER + DEF_BADGER_STEP * s32(variant)) & M32,
                           props, F_10)
        w32(c + 0x48, VT_BADGER)
        w32(c + 0x1C, F_35)
        self.w8(c + 0x28, 0x28)
        w32(c + 0xB8, 0)
        w32(c + 0xB0, ONE)
        self.w16(c + 0x232, 0)
        self.w8(c + 0xB4, 3)
        w32(c + 0xEC, self.u32(G_SIM_FRAME))
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x200000000)
        self.w8(c + 0x3CC, variant)
        if s8(variant) == 1:
            w32(c + 0x60, ONE)
            w32(c + 0x5C, 0xBE999999)
            w32(c + 0xDC, F_0_8)
            w32(c + 0xE0, 0xC1200000)
            w32(c + 0x1C, F_25)
        else:
            self.w8(c + 0x28, 0x2D)
            w32(c + 0xE0, 0xC1700000)
        w32(c + 0xE8, 0)
        self.w64(c + 0x220, self.call('model_buildHideMask', self.class_model(c), 0))
        self.call('anim_clear', c + 0x114)
        self.call('anim_push', c + 0x114, self.clip(c, 0x7C), 1)
        self.call('obj_runEvery60', c)
        self.events(c, self.BADGER_EVENTS)
        self.call('Creature_init', c)

    def badger_run(self, c):
        """Badger_run 0x244380 (creature): one tick.

        Creature_processDamage, Creature_run, Creature_updateActive - inactive ends the
        tick - Creature_stepAnim(1.0), Creature_applyKnockback(0.2), slot 23, then:

          0     slot 25 (0) -> 3; else away from home -> 1
          1     slot 25 (0) -> 0; else Creature_moveToDest
          3     the chase: _badger_chase
          5     no target: not rooted -> 3.  With one: target within 25 in arc 7000, or
                any enemy in that cone -> 6; else not rooted -> 3
          6-10  the attacks: _badger_attack
          0x10  attack ready -> 0, else flee        0x12  reaction clip over -> 3
          0x13  not stunned -> 0
          0x14  Creature_deadUpdate(flag 0; 35.0); on event bit 2 object flag 1 is set
          anything else: nothing at all"""
        st = self.set_state
        self.process_damage(c, self.class_model(c))
        if self.run(c, self.class_model(c)):
            return
        if not self.update_active(c):
            return
        ev = self.step_anim(c, ONE)
        self.call('Creature_applyKnockback', c, F_0_2)
        self.vcall(c, 23, 0)
        state = self.u16(c + 0x232)
        if state == 0:
            if self.vcall(c, 25, 0):
                return st(c, 3)
            if self.is_away_from_home(c):
                return st(c, 1)
        elif state == 1:
            if self.vcall(c, 25, 0):
                return st(c, 0)
            self.move_to_dest(c)
        elif state == 3:
            self._badger_chase(c)
        elif state == 5:
            if not self.u32(c + 0x234):
                if self.is_not_rooted(c):
                    return st(c, 3)
                return
            if self.see(c, 7000, F_25):
                return st(c, 6)
            if self.call('creature_findEnemyInCone', c, self.s16(c + 0x38), 7000, ZERO, F_25):
                return st(c, 6)
            if self.is_not_rooted(c):
                return st(c, 3)
        elif 6 <= state <= 10:
            self._badger_attack(c, ev)
        elif state == 0x10:
            if self.is_attack_ready(c):
                return st(c, 0)
            self.flee_from_target(c, 0)
        elif state == 0x12:
            if not self.anim_flags(c, 0x10):
                return st(c, 3)
        elif state == 0x13:
            if self.is_not_stunned(c):
                return st(c, 0)
        elif state == 0x14:
            self.dead_update(c, ev, 0, F_35)
            if ev & 4:
                self.w32(c + 0xC, self.u32(c + 0xC) | 1)

    def _badger_pick(self, c):
        """ONE OWN DRAW d: d % 5 == 0 -> state 8 (left), 1 -> 9 (right), else 6 (front)."""
        pick = self.obj_rand(c) % 5
        return 8 if pick == 0 else 9 if pick == 1 else 6

    def _badger_chase(self, c):
        """State 3, first match wins; T is the target seen in a range and arc,
        E any enemy in a cone (creature_findEnemyInCone):
            no target                               -> 0
            T 0-60, facing, arc 7000                -> own draw: 8, 9 or 6
            T 25-100, facing, arc 7000              -> 10
            T 0-60, facing + 8000, arc 3000         -> 8
            T 0-60, facing - 8000, arc 3000         -> 9
            E 0-25, facing, arc 7000                -> own draw: 8, 9 or 6
            E 0-25, facing + 8000, arc 3000         -> 8
            E 0-25, facing - 8000, arc 3000         -> 9
            T 0-20, any direction (facing 0, arc 0x7fff)   turn only
            otherwise                               Creature_moveToTarget"""
        st = self.set_state
        if not self.u32(c + 0x234):
            return st(c, 0)
        facing = lambda delta=0: s16(self.u16(c + 0x38) + delta)      # noqa: E731
        cone = lambda delta, arc: self.call('creature_findEnemyInCone', c, facing(delta), arc, ZERO, F_25)   # noqa: E731
        if self.see(c, 7000, F_60):
            return st(c, self._badger_pick(c))
        if self.see(c, 7000, F_100, near=F_25):
            return st(c, 10)
        if self.see(c, 3000, F_60, facing=facing(8000)):
            return st(c, 8)
        if self.see(c, 3000, F_60, facing=facing(-8000)):
            return st(c, 9)
        if cone(0, 7000):
            return st(c, self._badger_pick(c))
        if cone(8000, 3000):
            return st(c, 8)
        if cone(-8000, 3000):
            return st(c, 9)
        if self.can_see_target_in(c, 0, 0x7FFF, 0, ZERO, F_20, ZERO):
            self.turn_to_target(c)
        else:
            self.move_to_target(c)

    def _badger_attack(self, c, ev):
        """States 6 (front), 7, 8 (left), 9 (right), 10 (0x2447c4).

        Creature_settle every tick.  On event bit 0: Creature_hitAllEnemiesInArc (0 to
        radius + 25, facing, arc 7000, +0xd0, +0xd2, +0xd4, no descriptor) and +0x3c8 = 1.
        The damage flags are 8 for variant 1 and for states 8 and 9; for variant 0 in
        states 6, 7 and 10 ONE OWN DRAW d decides: d % 3 == 0 -> 0x80008, else 0x40008.
        With a target, while the clip plays (flag 8) and the target is within 10 in arc
        7000: turn to it - in state 6 only before the hit (+0x3c8 == 0), in 7 and 10
        throughout.  On event bit 1, in any state but 6, with the target within 60 in arc
        7000: set-state 6 (the chain into a front attack).  Then, clip not playing ->
        set-state 3 - also on the tick the chain just started."""
        self.settle(c)
        if ev & 1:
            flags = 8
            if self.s8(c + 0x3CC) != 1 and self.s16(c + 0x232) in (6, 7, 10):
                flags = 0x80008 if self.obj_rand(c) % 3 == 0 else 0x40008
            self.call('Creature_hitAllEnemiesInArc', c, self.s16(c + 0x38), 7000, self.s16(c + 0xD0),
                      self.s16(c + 0xD2), self.s16(c + 0xD4), flags, 0, ZERO, C.add(self.u32(c + 0x1C), F_25))
            self.w32(c + 0x3C8, 1)
        if self.u32(c + 0x234):
            state = self.s16(c + 0x232)
            if state == 6 and not self.u32(c + 0x3C8) and self.anim_flags(c, 8):
                if self.see(c, 7000, F_10):
                    self.turn_to_target(c)
                state = self.s16(c + 0x232)
            if state == 10:
                if self.anim_flags(c, 8) and self.see(c, 7000, F_10):
                    self.turn_to_target(c)
                state = self.s16(c + 0x232)
            if state == 7 and self.anim_flags(c, 8) and self.see(c, 7000, F_10):
                self.turn_to_target(c)
        if ev & 2 and self.s16(c + 0x232) != 6 and self.see(c, 7000, F_60):
            self.set_state(c, 6)
        if not self.anim_flags(c, 8):
            self.set_state(c, 3)

    def badger_set_state(self, c, state):
        """Badger_setState 0x244aa4 (creature, state): slot 27.

        After Creature_filterState:
          0     the idle clip (+0x7c); +0xf4 = clock + 180 (nothing reads it)
          1     path cleared, wander destination; the walk clip (+0x8c), or the charge clip
                (+0x4c) while the charm timer +0x312 is non-zero; frame sync
          3     path cleared; the charge clip (blend 0.2) unless the current state is 3 or
                an attack (6-10); frame sync either way
          5, 0x13   the idle clip
          6, 7, 10  swing clip +0x24 / +0x54 / +0x34 with flags 0x808; +0x3c8 = 0
          8, 9      swing clip +0x2c / +0x3c with flags 0x4808; +0x3c8 = 0
          0x10  path cleared, the back-up clip (+0x44), frame sync
          0x12  ignored (the state stays 6) while a state-6 clip is still playing; else
                one of two reaction clips (OWN DRAW & 1)
          0x14  object flag 1 cleared unless the creature is hidden (flag 2);
                Creature_dropLoot (36, 2, 2.8, 3, 3, 0.25; no named item); one of two death
                clips (OWN DRAW & 1); slot 28 (on death)
          anything else: the number is stored and nothing is done."""
        refused, state = self.filter_state(c, state)
        if refused:
            return
        anim = c + 0x114
        swings = {6: (0x24, 0x808), 7: (0x54, 0x808), 8: (0x2C, 0x4808), 9: (0x3C, 0x4808), 10: (0x34, 0x808)}
        if state == 0:
            self.start(c, 0x7C, 3)
            self.w32(c + 0xF4, self.u32(c + 0x300) + 180)
        elif state == 1:
            self.clear_path(c)
            self.pick_wander_dest(c)
            self.start(c, 0x8C if self.s16(c + 0x312) == 0 else 0x4C, 0x803)
            self.call('anim_syncToSimFrame', anim)
        elif state == 3:
            self.clear_path(c)
            if self.s16(c + 0x232) not in (3, 6, 7, 8, 9, 10):
                self.start(c, 0x4C, 0x803, F_0_2)
            self.call('anim_syncToSimFrame', anim)
        elif state in (5, 0x13):
            self.start(c, 0x7C, 3)
        elif state in swings:
            self.swing(c, *swings[state])
            self.w32(c + 0x3C8, 0)
        elif state == 0x10:
            self.clear_path(c)
            self.start(c, 0x44, 0x803)
            self.call('anim_syncToSimFrame', anim)
        elif state == 0x12:
            if self.s16(c + 0x232) == 6 and self.anim_flags(c, 8):
                state = 6
            else:
                self.swing(c, 0x6C + 8 * (self.obj_rand(c) & 1), 0x10)
        elif state == 0x14:
            flags = self.u32(c + 0xC)
            if not flags & 2:
                self.w32(c + 0xC, flags & ~1 & M32)
            self.drop_loot(c, 0, F_2_8, F_3, F_3)
            self.start(c, 0x5C + 8 * (self.obj_rand(c) & 1), 6)
            self.vcall(c, 28, 0)
        self.w16(c + 0x232, state)
