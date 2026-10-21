"""ref_combat_ctors.py - the AntQueen, Skeleton and Soul constructors, their set-state
functions, and the part of their run functions that comes before the state switch.

Reference contract, executed against the original by tools/difftest_combat_ctors.py
(docs/spec/combat-ctors.md is the prose).  Everything here is Observed by that
difftest unless a docstring says otherwise.

    AntQueen_ctor       0x236c70      AntQueen_setState     0x237918
    AntQueen_run        0x236f78 (up to the switch at 0x237000)
    Skeleton_ctor       0x2a5af4      Skeleton_setState     0x2a7768
    Skeleton_run        0x2a6864 (up to the switch at 0x2a6950)
    Soul_ctor           0x2a9478      Soul_setState         0x2aac38
    Soul_run            0x2a9870 (up to the switch at 0x2a9978)
    Soul_getModel       0x2ab298 (slot 16)
    anm_setEventSlots   0x1183d0

What a creature of each class runs before it can fight:
  1. the constructor (Creature_ctor underneath, the class's own fields, its first clip,
     its run list, the event times of its attack clips, Creature_init);
  2. on every tick, the run prologue before the switch: Creature_processDamage,
     Creature_run, Creature_updateActive, Creature_stepAnim(1.0),
     Creature_applyKnockback, slot 23 (Creature_pickTarget, the base body in all three
     tables).  AntQueen does not test the activity result; Skeleton and Soul return when
     it is 0.  Skeleton updates its weapon holder (slot 21) between activity and the
     animation step.  Soul takes its model from its own slot 16 and, unless held or
     thrown, makes one zero-vector Creature_moveBy;
  3. the set-state entries that lead into a fight (Creature_filterState first; the
     clips and timers of each state are below).

The states the switches then select are tools/ref_combat_round5.py on t3/research-combat
(states 0 and 1) and the prose of docs/monsters-2.md (the rest).
"""
import ref_core as C
import ref_creature as RC
import ref_arena_monsters as AM
import ref_monsters_1 as M1
from ref_creature import Ext, M32, M64, s16, s32

# class definitions, tables, data
DEF_ANTQUEEN, VT_ANTQUEEN = 0x4FEB10, 0x511078
DEF_SKELETON, DEF_SKELETON_STEP, VT_SKELETON = 0x5022E0, 0x40, 0x5175F8   # model set n: 0x5022e0 + 0x40 n
SKEL_COMMON, SKEL_ROW = 0x5023E0, 0x70          # skelcom block: per weapon kind a row of 14 entries
DEF_SOUL, VT_SOUL = 0x502778, 0x517740
G_LEVEL_NAME = 0x41B721                         # g_levelName (Soul compares it with "airhub")
G_LUMP_GENERATION = 0x41BF78
S_AIRHUB = 0x54C2B8
S_BONECHIP = 0x54BF60                           # the item a Skeleton's loot call names
P_SOUL = 0x8E4600                               # the particle definition of the Soul class

# The Skeleton type-name prefixes, in the order Skeleton_ctor tests them, with what a match
# sets: (prefix address, weapon kind or None to keep the drawn one, side or None).
SKEL_PREFIXES = (
    (0x54BD70, None, 2), (0x54BD80, None, 1),   # skeletonred, skeletonblue
    (0x54BD90, 0, 2), (0x54BDA8, 0, 1),         # skeletonswordohw red / blue
    (0x54BDC0, 1, 2), (0x54BDD8, 1, 1),         # skeletonsworddhw red / blue
    (0x54BDF0, 2, 2), (0x54BE00, 2, 1),         # skeletonaxe red / blue
    (0x54BE10, 3, 2), (0x54BE28, 3, 1),         # skeletonspear red / blue
    (0x54BE40, 4, 2), (0x54BE50, 4, 2),         # skeletonbow red AND blue: side 2 for both
    (0x54BE60, 0, None), (0x54BE78, 1, None), (0x54BE90, 2, None),   # sword ohw, sword dhw, axe
    (0x54BEA0, 3, None), (0x54BEB0, 4, None),   # spear, bow
)

# float patterns
ZERO, HALF, ONE = RC.ZERO, RC.HALF, RC.ONE
F_2M16 = RC.F_2M16
F_0_1, F_0_2, F_0_3, F_0_4, F_0_5 = 0x3DCCCCCC, 0x3E4CCCCC, 0x3E999999, 0x3ECCCCCC, 0x3F000000
F_THIRD, F_0_6, F_0_7, F_0_9 = 0x3EAAAAAB, 0x3F199999, 0x3F333333, 0x3F666666
F_1_2, F_1_3, F_1_6, F_2, F_5 = 0x3F999999, 0x3FA66666, 0x3FCCCCCC, 0x40000000, 0x40A00000
F_10, F_15, F_18, F_36, F_40, F_45 = 0x41200000, 0x41700000, 0x41900000, 0x42100000, 0x42200000, 0x42340000
F_140, F_200, F_240, F_1000 = 0x430C0000, 0x43480000, 0x43700000, 0x447A0000
# the element chance of each Skeleton weapon kind: (float)draw x 2^-16 below this
SKEL_ELEMENT_CHANCE = (0x3DCCCA2D, 0x3DCCCA2D, 0x3DCCCAB3, 0x3DCCCCCC, 0x3DCCCBC0)

MODELLED = {
    'AntQueen_ctor': 0x236C70, 'AntQueen_setState': 0x237918,
    'Skeleton_ctor': 0x2A5AF4, 'Skeleton_setState': 0x2A7768,
    'Soul_ctor': 0x2A9478, 'Soul_setState': 0x2AAC38, 'Soul_getModel': 0x2AB298,
    'anm_setEventSlots': 0x1183D0,
}
# The run functions: entry, the address of the state switch's range test, and the
# address the original goes to when that test fails (the epilogue).
RUN_PROLOGUES = {
    'AntQueen_run': (0x236F78, 0x237004, 'antqueen_run_prologue'),
    'Skeleton_run': (0x2A6864, 0x2A6954, 'skeleton_run_prologue'),
    'Soul_run': (0x2A9870, 0x2A997C, 'soul_run_prologue'),
}

# virtual bodies this module has: function -> (slot, method)
CLASS_BODIES = dict(M1.CLASS_BODIES)
CLASS_BODIES.update({
    0x237918: (27, 'antqueen_set_state'), 0x2A7768: (27, 'skeleton_set_state'),
    0x2AAC38: (27, 'soul_set_state'), 0x2AB298: (16, 'soul_get_model'),
})

EXTERNALS = dict(M1.EXTERNALS)
EXTERNALS.update({
    'anim_pushChained': Ext(0x170938, 'ppi', 0, 'n', '(state, clip, flags): starts where the previous track ends'),
    'anim_findTrack': Ext(0x170D88, 'pp', 0, 'i', '(state, clip) -> track or 0'),
    'anim_pushWithWeights': Ext(0x1708C0, 'ppi', 5, 'n', '(state, clip, flags; 0, weight, rate, life, life rate)'),
    'AntQueen_pickFlyDest': Ext(0x238150, 'op', 0, 'n', '(out position, queen)'),
    'Skeleton_shatter': Ext(0x2A7EF0, 'pi', 0, 'n', '(skeleton, group 8): bone props from the show mask'),
    'Holder.v3': Ext(0, 'pi', 0, 'n', 'fire-burst weapon (1)'),
})


def shape_result(name, args, ret=0, fret=0, outs=None):
    """M1.shape_result for this module's rows."""
    saved = M1.EXTERNALS
    M1.EXTERNALS = EXTERNALS
    try:
        return M1.shape_result(name, args, ret, fret, outs)
    finally:
        M1.EXTERNALS = saved


class Model(M1.Model):
    """The three classes on a memory image."""

    def call(self, name, *args):
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    def vcall(self, obj, slot, *args):
        table = self.u32(obj + 0x48)
        body = CLASS_BODIES.get(self.u32(table + 8 * slot + 4))
        if body is not None and ('Creature.v%d' % slot) not in self.external:
            this = (obj + self.s16(table + 8 * slot)) & M32
            return getattr(self, body[1])(this, *args)
        return AM.Model.vcall(self, obj, slot, *args)

    # ---- helpers --------------------------------------------------------------------------
    def anm_set_event_slots(self, block, entry, masks, times):
        """anm_setEventSlots 0x1183d0 (creature, unused; block, entry, four masks; four
        times): creature_setDefEntryParams with the resource block given instead of the
        creature's class definition.  Entry k's record is the word at block + 8k + 4."""
        for k in range(4):
            record = self.u32(block + 8 * entry + 4)
            self.w8(record + 0x18 + 8 * k, masks[k])
            self.w32(record + 0x14 + 8 * k, times[k])

    def own_chance(self, c, threshold):
        """(float)GameObject_rand(c) x 2^-16 < threshold."""
        return C.lt(C.mul(C.from_int(self.obj_rand(c)), F_2M16), threshold)

    def skel_clip(self, c, offset):
        """A word of the creature's weapon-kind row of the skelcom block."""
        return self.u32((SKEL_COMMON + SKEL_ROW * self.u32(c + 0x3D0) + offset) & M32)

    def blend(self, c, clip, flags, time=F_0_1):
        self.call('anim_startBlendInOut', c + 0x114, clip, flags, time, time)

    def weights(self, c, clip, flags, rate):
        """anim_pushWithWeights with f12 = weight 0, rate given, life 1.0, life rate 0."""
        self.call('anim_pushWithWeights', c + 0x114, clip, flags, ZERO, ZERO, rate, ONE, ZERO)

    def fly_clips(self, c):
        """The three flight tracks (+0x3c weighted 1/3, +0x44, +0x4c) AntQueen layers."""
        self.weights(c, self.clip(c, 0x3C), 0x203, F_THIRD)
        self.weights(c, self.clip(c, 0x44), 0x201, ZERO)
        self.weights(c, self.clip(c, 0x4C), 0x201, ZERO)

    # =====================================================================================
    # AntQueen
    # =====================================================================================
    def antqueen_ctor(self, c, type_name, pos, facing, props):
        """AntQueen_ctor 0x236c70 (object, type name, position, facing, property list).

        ONE OWN DRAW before Creature_ctor, from the generator word +0x44 the block holds
        before GameObject_ctor seeds it: hit points (float)(d % 14 + 4), which the type
        name's Creature_setStats then replaces.  Turn rate 1.2, radius 45, speed 140, byte
        +0x28 = 0x37, kind +0xb4 = 0x13, +0x5c = 0.4, creature flags |= 0x8020001000,
        +0x3d4 = 180, state 0 stored directly (no set-state: +0xf4 stays 0 from
        Creature_ctor).  ONE OWN DRAW: +0x3d8 = clock + 180 + d % 180.  +0xe8 = 0, the
        show mask for variant 0, clip idle_a (+0x7c), the every-60 run list, the event
        times of attack1 (entry 3) and sting (0x13) at 0.2 and attack2 x3 (4-6) at 0.3,
        Creature_init."""
        w32 = self.w32
        hp = C.from_int(self.obj_rand(c) % 14 + 4)
        self.creature_ctor(c, type_name, pos, s16(facing), DEF_ANTQUEEN, props, hp)
        w32(c + 0xB0, F_1_2)
        w32(c + 0x1C, F_45)
        w32(c + 0x48, VT_ANTQUEEN)
        w32(c + 0xB8, F_140)
        self.w8(c + 0x28, 0x37)
        self.w16(c + 0x232, 0)
        w32(c + 0x5C, F_0_4)
        self.w8(c + 0xB4, 0x13)
        w32(c + 0xEC, self.u32(RC.G_SIM_FRAME))
        w32(c + 0x3D4, 180)
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x8020001000)
        d = self.obj_rand(c)
        w32(c + 0xE8, 0)
        w32(c + 0x3D8, self.u32(c + 0x300) + d % 180 + 180)
        self.w64(c + 0x220, self.call('model_buildHideMask', self.class_model(c), 0))
        self.call('anim_clear', c + 0x114)
        self.call('anim_push', c + 0x114, self.clip(c, 0x7C), 1)
        self.call('obj_runEvery60', c)
        self.set_def_entry_params(c, 3, (1, 0, 0, 0), (F_0_2, ZERO, ZERO, ZERO))
        for entry in (4, 5, 6):
            self.set_def_entry_params(c, entry, (1, 0, 0, 0), (F_0_3, ZERO, ZERO, ZERO))
        self.set_def_entry_params(c, 0x13, (1, 0, 0, 0), (F_0_2, ZERO, ZERO, ZERO))
        self.call('Creature_init', c)

    def antqueen_run_prologue(self, c):
        """AntQueen_run 0x236f78 up to its switch: processDamage and Creature_run with the
        class model, Creature_updateActive (result NOT tested), stepAnim(1.0),
        applyKnockback(0.5), slot 23 (0)."""
        self.process_damage(c, self.class_model(c))
        if self.run(c, self.class_model(c)):
            return
        self.update_active(c)
        self.step_anim(c, ONE)
        self.call('Creature_applyKnockback', c, HALF)
        self.vcall(c, 23, 0)

    def antqueen_set_state(self, c, state):
        """AntQueen_setState 0x237918 (creature, state): slot 27.  After
        Creature_filterState (a refusal stores nothing):
          0     ONE OWN DRAW: +0xf4 = clock + d % 120; idle_a (+0x7c) blend 0.3
          1     clear path, wander destination, speed 140, walk (+0xac) blend 0.3
          3     from 0x12, 6 or 7 only +0x3c4 = 0xabe0; otherwise also clear path, speed
                140 and the three walk tracks (+0xac 1/3, +0xb4, +0xbc) by weights
          5     attack2_center (+0x84) blend 0.1
          6     attack1 (+0x1c) as a swing, +0x3cc = 0
          7     with a target: creature_findEnemyInCone(0, 40, this, facing - 0x7fff,
                6000); found: the bearing to it less the facing, plus 0x7fff, as s16:
                above 2000 -> attack2_right, below -2000 -> attack2_left, else centre;
                not found: centre.  As a swing.  No target: only the store.
          8     speed 240, clear path; from 0x17 or 9 nothing else; otherwise ONE OWN
                DRAW +0x3d4 = clock + 300 + d % 180, the fly tracks, takeoff (+0xa4)
          9, 10 sting (+0x9c) as a swing, +0x3cc = 0
          0x12  in 8, 0x17 or 9, or in 6 with clip flag 8: the old state stays.
                Otherwise the hit direction +0x2e0 picks hit_back (+0x54), hit_right
                (+0x6c), hit_left (+0x64) or hit_front (+0x5c), flags 0x10
          0x13  idle_a blend 0.3
          0x14  Creature_dropLoot(position, facing, no item; 36, 2, 5, 1, 5, 1), death
                (+0xc4) flags 0x16 blend 0.4; takeoff as a swing unless a +0x3c track is
                playing; slot 28 (0)
          0x17  ONE OWN DRAW: speed 240, +0x3d4 = clock + 180 + d % 120, clear path,
                AntQueen_pickFlyDest -> +0x104; from 8 or 9 nothing else; otherwise the
                fly tracks and takeoff
          0x18  ONE OWN DRAW: +0x3d4 = clock + 180 + d % 180, attack2_center blend 0.1,
                landing (+0x94) as a swing
          0x19  ONE OWN DRAW: +0x3d8 = clock + 180 + d % 180, attack2_center, +0x8c as a
                swing; ONE OWN DRAW: +0xf4 = clock + 120 + d % 60
          anything else: the request is stored, nothing is done."""
        refused, state = self.filter_state(c, state)
        if refused:
            return
        u32, w32 = self.u32, self.w32
        anim, old = c + 0x114, self.s16(c + 0x232)
        clock = lambda: u32(c + 0x300)              # noqa: E731
        if state == 0:
            d = self.obj_rand(c)
            w32(c + 0xF4, clock() + d % 120)
            self.start(c, 0x7C, 3, F_0_3)
        elif state == 1:
            self.clear_path(c)
            self.pick_wander_dest(c)
            w32(c + 0xB8, F_140)
            self.start(c, 0xAC, 3, F_0_3)
        elif state == 3:
            if old not in (0x12, 6, 7):
                self.clear_path(c)
                w32(c + 0xB8, F_140)
                self.weights(c, self.clip(c, 0xAC), 0x203, F_THIRD)
                self.weights(c, self.clip(c, 0xB4), 0x201, ZERO)
                self.weights(c, self.clip(c, 0xBC), 0x201, ZERO)
            self.w16(c + 0x3C4, 0xABE0)
        elif state == 5:
            self.start(c, 0x84, 3, F_0_1)
        elif state == 6:
            self.blend(c, self.clip(c, 0x1C), 8)
            w32(c + 0x3CC, 0)
        elif state == 7:
            if u32(c + 0x234):
                entry = 4
                found = self.call('creature_findEnemyInCone', c, s16(self.u16(c + 0x38) - 0x7FFF), 6000, ZERO, F_40)
                if found:
                    bearing = C.atan2_16(C.sub(u32(found + 0x14), u32(c + 0x14)), C.sub(u32(found + 0x10), u32(c + 0x10)))
                    diff = s16(bearing - self.u16(c + 0x38) + 0x7FFF)
                    entry = 6 if diff > 2000 else 5 if diff < -2000 else 4
                self.blend(c, self.clip(c, 8 * entry + 4), 8)
        elif state == 8:
            w32(c + 0xB8, F_240)
            self.clear_path(c)
            if old not in (0x17, 9):
                d = self.obj_rand(c)
                w32(c + 0x3D4, clock() + d % 180 + 300)
                self.fly_clips(c)
                self.blend(c, self.clip(c, 0xA4), 8)
        elif state in (9, 10):
            self.blend(c, self.clip(c, 0x9C), 8)
            w32(c + 0x3CC, 0)
        elif state == 0x12:
            if old in (8, 0x17, 9) or (old == 6 and self.u16(c + 0x11A) & 8):
                state = old
            else:
                hit = self.u16(c + 0x2E0)
                if (hit + 0x1FFF) & 0xFFFF < 0x3FFF:
                    offset = 0x54
                elif (hit - 0x2001) & 0xFFFF < 0x3FFF:
                    offset = 0x6C
                elif -0x5FFF <= s16(hit) < -0x2000:
                    offset = 0x64
                else:
                    offset = 0x5C
                self.blend(c, self.clip(c, offset), 0x10)
        elif state == 0x13:
            self.start(c, 0x7C, 3, F_0_3)
        elif state == 0x14:
            self.call('Creature_dropLoot', c, self.vec(c + 0x10), self.s16(c + 0x38), 0,
                      F_36, F_2, F_5, ONE, F_5, ONE)
            self.start(c, 0xC4, 0x16, F_0_4)
            if not self.call('anim_findTrack', anim, self.clip(c, 0x3C)):
                self.blend(c, self.clip(c, 0xA4), 8)
            self.vcall(c, 28, 0)
        elif state == 0x17:
            d = self.obj_rand(c)
            w32(c + 0xB8, F_240)
            w32(c + 0x3D4, clock() + d % 120 + 180)
            self.clear_path(c)
            dest = self.call('AntQueen_pickFlyDest', c)
            self.wvec(c + 0x104, dest)
            if (self.u16(c + 0x232) - 8) & 0xFFFF >= 2:
                self.fly_clips(c)
                self.blend(c, self.clip(c, 0xA4), 8)
        elif state == 0x18:
            d = self.obj_rand(c)
            w32(c + 0x3D4, clock() + d % 180 + 180)
            self.start(c, 0x84, 3, F_0_1)
            self.blend(c, self.clip(c, 0x94), 8)
        elif state == 0x19:
            d = self.obj_rand(c)
            w32(c + 0x3D8, clock() + d % 180 + 180)
            self.start(c, 0x84, 3, F_0_1)
            self.blend(c, self.clip(c, 0x8C), 8)
            w32(c + 0xF4, clock() + self.obj_rand(c) % 60 + 120)
        self.w16(c + 0x232, state)

    # =====================================================================================
    # Skeleton
    # =====================================================================================
    SKEL_EVENTS = (
        ((1, 2, 3, 0xF, 0x10, 0x11, 0x1F, 0x2B, 0x2C, 0x2D), (1, 0, 0, 0), (F_0_3, ZERO, ZERO, ZERO)),
        ((0x1D, 0x1E), (1, 1, 0, 0), (F_0_3, F_0_9, ZERO, ZERO)),
        ((0x39, 0x3A, 0x3B), (2, 1, 0, 0), (F_0_2, F_1_3, ZERO, ZERO)),     # the bow row: bit 1, then bit 0
    )
    SKEL_EVENT_ORDER = (1, 2, 3, 0xF, 0x10, 0x11, 0x1D, 0x1E, 0x1F, 0x2B, 0x2C, 0x2D, 0x39, 0x3A, 0x3B)

    def skeleton_ctor(self, c, pos, facing, props, type_name, model_set):
        """Skeleton_ctor 0x2a5af4 (object, position, facing, property list, type name,
        model set).

        Creature_ctor with the type name and class definition 0x5022e0 + 0x40 x set, hit
        points 10.  The WeaponShield holder embedded at +0x3d8 (+0x50 points at it),
        +0x3c8 = +0x3cc = 0.  The skelcom block 0x5023e0 is resolved (res_find of each
        name) when its generation word is not the current one.  Byte +0x28 = 0x14, turn
        rate 1.2, radius 18, speed 0, state 0 stored, creature flags |= 0x10000, kind 0x10,
        +0x64 = +0x68 = 1.0.

        ONE OWN DRAW: weapon kind +0x3d0 = d % 5, side byte +0x3d4 = 0; then the prefix
        table SKEL_PREFIXES (first match wins).  Per kind, with the holder (each draw is
        made even when +0x50 is 0):
          0  OWN DRAW element chance; on success OWN DRAW (d & 1) + 1; OWN DRAW hand 1 =
             0x52 (odd) or 0x54; OWN DRAW hand 2 = 0x60 + 2 (d & 1)
          1  element as 0; hand 1 = 0x5e
          2  element as 0 (its own threshold); OWN DRAW hand 1 = 0x5a (odd) or 0x5c
          3  element as 0; OWN DRAW hand 1 = 0x64 (odd) or 0x66
          4  element chance; on success OWN DRAW d % 3 + 1; hand 1 = 0x58
        Variant bits +0xe8 (from 0): OWN DRAW d; odd -> OWN DRAW bit d % 3; bow -> 0x80,
        else d & 2 -> OWN DRAW bit 9 + d % 12; bit 14 clear -> OWN DRAW bit 21 + d % 5;
        OWN DRAW bit 5 + (d & 1).  Show mask from those bits.  Element 1 -> holder slot 4,
        2 -> slot 2, 3 -> slot 3 (argument 1).  Creature flags |= 0x800000000 when a bit
        of 0x21e00 is set, else 0x2000000000 for 0x1de000, else 0x10000000000.  HomeRange
        +0x3c0 = 200 with a side, 1000 without.  The kind's idle clip pushed (row +0x44,
        flags 1), Skeleton_setState(0) called directly, the every-60 run list, fifteen
        anm_setEventSlots on the skelcom block (SKEL_EVENTS), Creature_init."""
        u32, w32, w8 = self.u32, self.w32, self.w8
        holder = c + 0x3D8
        self.creature_ctor(c, type_name, pos, s16(facing), (DEF_SKELETON + (model_set << 6)) & M32, props, F_10)
        w32(c + 0x48, VT_SKELETON)
        w32(c + 0x3C8, 0)
        w32(c + 0x3CC, 0)
        self._init_holder(c, holder, AM.VT_WEAPONSHIELD)
        if u32(SKEL_COMMON + 4) != u32(G_LUMP_GENERATION):
            k = 8
            while u32(SKEL_COMMON + k):
                w32(SKEL_COMMON + k + 4, self.call('res_find', u32(SKEL_COMMON), u32(SKEL_COMMON + k)))
                k += 8
            w32(SKEL_COMMON + 4, u32(G_LUMP_GENERATION))
        w8(c + 0x28, 0x14)
        w32(c + 0xB0, F_1_2)
        w32(c + 0x1C, F_18)
        w32(c + 0xB8, 0)
        self.w16(c + 0x232, 0)
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x10000)
        w8(c + 0xB4, 0x10)
        w32(c + 0xEC, u32(RC.G_SIM_FRAME))
        w32(c + 0x64, ONE)
        w32(c + 0x50, holder)
        w32(c + 0x68, ONE)
        w32(c + 0x3D0, self.obj_rand(c) % 5)
        w8(c + 0x3D4, 0)
        for prefix, kind, side in SKEL_PREFIXES:
            if not self.str_prefix_differs(type_name, prefix):
                if kind is not None:
                    w32(c + 0x3D0, kind)
                if side is not None:
                    w8(c + 0x3D4, side)
                break
        kind = u32(c + 0x3D0)
        element = 0

        def hand(which, part):
            if u32(c + 0x50):
                self.holder_call(u32(c + 0x50), 1, which, part)

        if kind < 5:
            if self.own_chance(c, SKEL_ELEMENT_CHANCE[kind]):
                element = (self.obj_rand(c) % 3 if kind == 4 else self.obj_rand(c) & 1) + 1
            if kind == 0:
                hand(1, 0x52 if self.obj_rand(c) & 1 else 0x54)
                hand(2, 0x60 + 2 * (self.obj_rand(c) & 1))
            elif kind == 1:
                hand(1, 0x5E)
            elif kind == 2:
                hand(1, 0x5A if self.obj_rand(c) & 1 else 0x5C)
            elif kind == 3:
                hand(1, 0x64 if self.obj_rand(c) & 1 else 0x66)
            else:
                hand(1, 0x58)
        w32(c + 0xE8, 0)
        d = self.obj_rand(c)
        if d & 1:
            w32(c + 0xE8, u32(c + 0xE8) | 1 << (self.obj_rand(c) % 3))
        if kind == 4:
            w32(c + 0xE8, u32(c + 0xE8) | 0x80)
        elif d & 2:
            w32(c + 0xE8, u32(c + 0xE8) | 1 << (self.obj_rand(c) % 12 + 9))
        if not u32(c + 0xE8) & 0x4000:
            w32(c + 0xE8, u32(c + 0xE8) | 1 << (self.obj_rand(c) % 5 + 21))
        w32(c + 0xE8, u32(c + 0xE8) | 1 << ((self.obj_rand(c) & 1) + 5))
        self.w64(c + 0x220, self.call('model_buildHideMask', self.class_model(c), u32(c + 0xE8)))
        slot = {1: 4, 2: 2, 3: 3}.get(element)
        if slot and u32(c + 0x50):
            self.holder_call(u32(c + 0x50), slot, 1)
        bits = u32(c + 0xE8)
        flag = 0x800000000 if bits & 0x21E00 else 0x2000000000 if bits & 0x1DE000 else 0x10000000000
        self.w64(c + 0xA8, self.u64(c + 0xA8) | flag)
        w32(c + 0x3C0, F_200 if self.u8(c + 0x3D4) else F_1000)
        self.call('anim_clear', c + 0x114)
        self.call('anim_push', c + 0x114, self.skel_clip(c, 0x44), 1)
        self.skeleton_set_state(c, 0)
        self.call('obj_runEvery60', c)
        for entry in self.SKEL_EVENT_ORDER:
            for entries, masks, times in self.SKEL_EVENTS:
                if entry in entries:
                    self.anm_set_event_slots(SKEL_COMMON, entry, masks, times)
        self.call('Creature_init', c)

    def skeleton_run_prologue(self, c):
        """Skeleton_run 0x2a6864 up to its switch: processDamage and Creature_run with the
        class model; Creature_updateActive, and an inactive skeleton RETURNS; the holder's
        slot 21 (skelcom block, this; 0.5); stepAnim(1.0); applyKnockback(0.7); slot 23."""
        self.process_damage(c, self.class_model(c))
        if self.run(c, self.class_model(c)):
            return
        if not self.update_active(c):
            return
        if self.u32(c + 0x50):
            self.holder_call(self.u32(c + 0x50), 21, SKEL_COMMON, c, HALF)
        self.step_anim(c, ONE)
        self.call('Creature_applyKnockback', c, F_0_7)
        self.vcall(c, 23, 0)

    def skeleton_set_state(self, c, state):
        """Skeleton_setState 0x2a7768 (creature, state): slot 27.  After
        Creature_filterState (a refusal stores nothing) creature flag 0x200 (blocking) is
        cleared, and 0x200800 too unless the request is 0x17.  Clips are words of the
        weapon kind's row of the skelcom block (row + offset):
          0     +0x44 blend 0.1; +0xf4 = clock + 120
          1     clear path (no wander destination), +0xf4 = clock + 300, +0x54 flags 0x803,
                frame sync
          3, 0x10  +0x6c flags 0x803, frame sync
          5     +0x2c blend 0.1
          6     +0x2c; OWN DRAW: +0x0c or +0x14 (d & 1) as a swing; OWN DRAW +0xf4 = 20 + d % 20
          7     +0x2c; +0x1c as a swing; OWN DRAW +0xf4 = 20 + d % 20
          8     +0x3c; OWN DRAW: +0x0c or +0x14 as a swing; +0xf4 = 1
          0x11  +0x2c; +0xf4 = clock + 120; creature flag 0x200 set
          0x12  in 0x17: the old state stays.  Otherwise +0x34 flags 0x10 as a swing.
                (The +0x24 branch for a blocking skeleton tests flag 0x200 after the
                clear above, so it is never taken.)
          0x13  +0x44 blend 0.1
          0x14  holder slot 11 for hands 1 and 2 (this, skelcom, 0); object flags |=
                0x4002; creature flag 0x20000000000; Skeleton_shatter(8); unless creature
                flag 0x1000000, Creature_dropLoot(position, facing, "bonechip"; 36, 2,
                1.6, 0.6, 1.6, 0.25); obj_delete; slot 28 (0)
          0x17  creature flags |= 0x200800; +0x74 pushed flags 0x10, +0x44 chained flags 3
          anything else: the request is stored, nothing is done."""
        refused, state = self.filter_state(c, state)
        if refused:
            return
        u32, w32, anim = self.u32, self.w32, c + 0x114
        cf = self.u64(c + 0xA8) & ~0x200 & M64
        self.w64(c + 0xA8, cf)
        if state != 0x17:
            self.w64(c + 0xA8, cf & 0xFFFFFFFFFFDFF7FF)
        clip = lambda off: self.skel_clip(c, off)           # noqa: E731
        start = lambda off, flags: self.call('anim_start', anim, clip(off), flags, F_0_1)   # noqa: E731
        if state == 0:
            start(0x44, 3)
            w32(c + 0xF4, u32(c + 0x300) + 120)
        elif state == 1:
            self.clear_path(c)
            w32(c + 0xF4, u32(c + 0x300) + 300)
            start(0x54, 0x803)
            self.call('anim_syncToSimFrame', anim)
        elif state in (3, 0x10):
            start(0x6C, 0x803)
            self.call('anim_syncToSimFrame', anim)
        elif state == 5:
            start(0x2C, 3)
        elif state in (6, 8):
            start(0x2C if state == 6 else 0x3C, 3)
            self.blend(c, clip(0xC + 8 * (self.obj_rand(c) & 1)), 0x808)
            w32(c + 0xF4, self.obj_rand(c) % 20 + 20 if state == 6 else 1)
        elif state == 7:
            start(0x2C, 3)
            self.blend(c, clip(0x1C), 0x808)
            w32(c + 0xF4, self.obj_rand(c) % 20 + 20)
        elif state == 0x11:
            start(0x2C, 3)
            w32(c + 0xF4, u32(c + 0x300) + 120)
            self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x200)
        elif state == 0x12:
            old = self.s16(c + 0x232)
            if old == 0x17:
                state = old
            elif self.u64(c + 0xA8) & 0x200:
                self.blend(c, clip(0x24), 0x10)
            else:
                self.blend(c, clip(0x34), 0x10)
        elif state == 0x13:
            start(0x44, 3)
        elif state == 0x14:
            for which in (1, 2):
                if u32(c + 0x50):
                    self.holder_call(u32(c + 0x50), 11, which, c, SKEL_COMMON, 0)
            w32(c + 0xC, u32(c + 0xC) | 0x4002)
            self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x20000000000)
            self.call('Skeleton_shatter', c, 8)
            if not self.u64(c + 0xA8) & 0x1000000:
                self.call('Creature_dropLoot', c, self.vec(c + 0x10), self.s16(c + 0x38), S_BONECHIP,
                          F_36, F_2, F_1_6, F_0_6, F_1_6, 0x3E800000)
            self.call('obj_delete', c)
            self.vcall(c, 28, 0)
        elif state == 0x17:
            self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x200800)
            self.call('anim_push', anim, clip(0x74), 0x10)
            self.call('anim_pushChained', anim, clip(0x44), 3)
        self.w16(c + 0x232, state)

    # =====================================================================================
    # Soul
    # =====================================================================================
    def soul_ctor(self, c, type_name, pos, facing, props, owner):
        """Soul_ctor 0x2a9478 (object, type name, position, facing, property list, owner).

        Creature_ctor with class definition 0x502778, hit points 10.  +0x3c8 = 0, turn rate
        1.2, radius 15, byte +0x28 = 0x1e, +0x3cc = 0, speed 0, state 0 stored directly,
        creature flags |= 0x200080000, +0xf4 = 0 (the state-0 entry draw is NOT made),
        Creature_setCharm(-1, team 0), the five resistances +0x5c..+0x6c = 1.0.
        With an owner: object flags |= 9, handle_link(+0x3c8, owner, owner), the held
        clip (+0x6c).  Without: g_levelName compared with "airhub" without case; equal ->
        clip +0x34 and Soul_setState(0x22) called directly; otherwise clip +0x3c.  Then
        creature flag bit 63, the every-frame run list, entry 0xb's event at 0.7,
        Creature_init."""
        w32 = self.w32
        self.creature_ctor(c, type_name, pos, s16(facing), DEF_SOUL, props, F_10)
        w32(c + 0x3C8, 0)
        w32(c + 0x48, VT_SOUL)
        w32(c + 0xB0, F_1_2)
        w32(c + 0x1C, F_15)
        self.w8(c + 0x28, 0x1E)
        w32(c + 0x3CC, 0)
        w32(c + 0xB8, 0)
        self.w16(c + 0x232, 0)
        w32(c + 0xF4, 0)
        w32(c + 0xEC, self.u32(RC.G_SIM_FRAME))
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x200080000)
        self.call('Creature_setCharm', c, M32, 0)
        for off in (0x5C, 0x60, 0x64, 0x68, 0x6C):
            w32(c + off, ONE)
        self.call('anim_clear', c + 0x114)
        if owner:
            w32(c + 0xC, self.u32(c + 0xC) | 9)
            self.call('handle_link', c + 0x3C8, owner, owner)
            self.call('anim_push', c + 0x114, self.clip(c, 0x6C), 1)
        elif self.on_airhub():
            self.call('anim_push', c + 0x114, self.clip(c, 0x34), 1)
            self.soul_set_state(c, 0x22)
        else:
            self.call('anim_push', c + 0x114, self.clip(c, 0x3C), 1)
        self.w64(c + 0xA8, self.u64(c + 0xA8) | 0x8000000000000000)
        self.call('obj_runEveryFrame', c)
        self.set_def_entry_params(c, 0xB, (1, 0, 0, 0), (F_0_7, ZERO, ZERO, ZERO))
        self.call('Creature_init', c)

    def on_airhub(self):
        return self.cstr(G_LEVEL_NAME).lower() == self.cstr(S_AIRHUB).lower()

    def soul_get_model(self, c):
        """Soul_getModel 0x2ab298 (slot 16): the class block's +0x1c while owned, else +0xc."""
        return self.u32(self.u32(c + 0x24) + (0x1C if self.u32(c + 0x3C8) else 0xC))

    def soul_run_prologue(self, c):
        """Soul_run 0x2a9870 up to its switch: processDamage and Creature_run with the
        slot-16 model, Creature_updateActive (inactive RETURNS), stepAnim(1.0),
        applyKnockback(0.0), slot 23; then, when not owned and not in 0x1b, Creature_moveBy
        with a zero vector."""
        self.process_damage(c, self.vcall(c, 16))
        if self.run(c, self.vcall(c, 16)):
            return
        if not self.update_active(c):
            return
        self.step_anim(c, ONE)
        self.call('Creature_applyKnockback', c, ZERO)
        self.vcall(c, 23, 0)
        if not self.u32(c + 0x3C8) and self.s16(c + 0x232) != 0x1B:
            self.move_by(c, (ZERO, ZERO, ZERO))

    def soul_set_state(self, c, state):
        """Soul_setState 0x2aac38 (creature, state): slot 27.

        On "airhub" (g_levelName, without case) every request becomes 0x22 BEFORE
        Creature_filterState.  A refusal stores nothing.  While owned (+0x3c8) only
        0x1a-0x20 are accepted; anything else stores nothing.  In 0x1b nothing is accepted.
          0     OWN DRAW: +0xf4 = clock + 60 + d % 120; +0x3c blend 0.3
          1     clear path, wander destination, +0x4c flags 0x803 blend 0.3, frame sync;
                OWN DRAW: +0xf4 = clock + 300 + d % 120
          5, 0x17  +0x34 blend 0.3
          0x10, 0x13  the old state stays
          0x12  slot 27 again with 0x19 when in 0x18, else 0x18; then 0x12 is stored
          0x14  +0x94 flags 6 blend 0.1; +0xf4 = clock + 180; object flag 0x4000; slot 28 (0)
          0x18  +0x44 blend 0.3; OWN DRAW +0xf4 = clock + d % 120
          0x19  only from 0x18: +0x2c flags 0x10 as a swing; otherwise the old state stays
          0x1a  +0x54 as a swing (flags 8)
          0x1b  handle cleared, +0x3c8 = 0, +0xf4 = clock + 240
          0x1c  +0x74 as a swing (flags 0xc);  0x1d  +0x5c as a swing (flags 8, blend 0.5)
          0x1e  +0x6c flags 3 blend 0.1;  0x1f  +0x7c flags 3 blend 0.3
          0x20  +0x84 as a swing (flags 8)
          0x21  for each sample point of the slot-16 model: the point (scale +0xdc), then
                twice a velocity by OWN DRAW rejection in the unit ball (three draws a
                try), x and y times 15 and z zeroed, a particle;
                object flags |= 0x4002, obj_delete.  (The owner's attach-matrix branch in
                it cannot run: an owned soul never gets here.)
          0x22  +0x94 flags 6 blend 0.1; +0xf4 = clock + 300; object flags |= 9
          anything else: the request is stored, nothing is done."""
        if self.on_airhub():
            state = 0x22
        refused, state = self.filter_state(c, state)
        if refused:
            return
        u32, w32 = self.u32, self.w32
        old = self.s16(c + 0x232)
        if u32(c + 0x3C8) and not 0x1A <= state <= 0x20:
            return
        if old == 0x1B:
            return
        anim = c + 0x114
        clock = lambda: u32(c + 0x300)          # noqa: E731
        if state == 0:
            d = self.obj_rand(c)
            w32(c + 0xF4, clock() + d % 120 + 60)
            self.start(c, 0x3C, 3, F_0_3)
        elif state == 1:
            self.clear_path(c)
            self.pick_wander_dest(c)
            self.start(c, 0x4C, 0x803, F_0_3)
            self.call('anim_syncToSimFrame', anim)
            w32(c + 0xF4, clock() + self.obj_rand(c) % 120 + 300)
        elif state in (5, 0x17):
            self.start(c, 0x34, 3, F_0_3)
        elif state in (0x10, 0x13):
            state = old
        elif state == 0x12:
            self.vcall(c, 27, 0x19 if old == 0x18 else 0x18)
        elif state == 0x14:
            self.start(c, 0x94, 6, F_0_1)
            w32(c + 0xF4, clock() + 180)
            w32(c + 0xC, u32(c + 0xC) | 0x4000)
            self.vcall(c, 28, 0)
        elif state == 0x18:
            self.start(c, 0x44, 3, F_0_3)
            w32(c + 0xF4, clock() + self.obj_rand(c) % 120)
        elif state == 0x19:
            if old == 0x18:
                self.blend(c, self.clip(c, 0x2C), 0x10)
            else:
                state = old
        elif state == 0x1A:
            self.blend(c, self.clip(c, 0x54), 8)
        elif state == 0x1B:
            self.call('handle_clear', c + 0x3C8)
            w32(c + 0x3C8, 0)
            w32(c + 0xF4, clock() + 240)
        elif state == 0x1C:
            self.blend(c, self.clip(c, 0x74), 0xC)
        elif state == 0x1D:
            self.blend(c, self.clip(c, 0x5C), 8, F_0_5)
        elif state == 0x1E:
            self.start(c, 0x6C, 3, F_0_1)
        elif state == 0x1F:
            self.start(c, 0x7C, 3, F_0_3)
        elif state == 0x20:
            self.blend(c, self.clip(c, 0x84), 8)
        elif state == 0x21:
            self.soul_burst(c)
        elif state == 0x22:
            self.start(c, 0x94, 6, F_0_1)
            w32(c + 0xF4, clock() + 300)
            w32(c + 0xC, u32(c + 0xC) | 9)
        self.w16(c + 0x232, state)

    def soul_burst(self, c):
        """Soul_setState 0x21's particles (0x2ab03c-0x2ab258)."""
        count = s32(self.call('model_getSamplePointCount', self.vcall(c, 16)))
        for index in range(max(count, 0)):
            model = self.vcall(c, 16)
            point, _second = self.call('model_getSamplePoint', model, c + 0x114, (ZERO, ZERO, ZERO), 0xFFFFC000,
                                       index, 1, 0, self.u32(c + 0xDC))
            if self.u32(c + 0x3C8):
                raise NotImplementedError('Soul_setState 0x21 with an owner: not reachable, not modelled')
            for _ in range(2):
                while True:
                    v = [C.sub(C.add(f, f), ONE) for f in
                         (C.mul(C.from_int(self.obj_rand(c)), F_2M16) for _k in range(3))]
                    size = C.add(C.add(C.mul(v[0], v[0]), C.mul(v[1], v[1])), C.mul(v[2], v[2]))
                    if not C.lt(ONE, size):
                        break
                # the copy's z word is zeroed before the scale (0x2ab1f0): the burst is flat
                self.call('particle_spawn', P_SOUL, tuple(point), (C.mul(v[0], F_15), C.mul(v[1], F_15),
                                                                   C.mul(ZERO, F_15)), ZERO)
        self.w32(c + 0xC, self.u32(c + 0xC) | 0x4002)
        self.call('obj_delete', c)
