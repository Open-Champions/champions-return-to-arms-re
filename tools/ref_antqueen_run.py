"""ref_antqueen_run.py - the whole of AntQueen_run, every state of its switch, and
AntQueen_pickFlyDest, the helper AntQueen_setState state 0x17 calls.

Reference contract, executed against the original by tools/difftest_antqueen_run.py
(docs/spec/antqueen-run.md is the prose).  Everything here is Observed by that difftest
unless a docstring says otherwise.

    AntQueen_run            0x236f78 (slot 4; switch table 0x541b80, 26 entries)
    AntQueen_pickFlyDest    0x238150 (out position, queen) -> out
    AntQueen_fadeBankTracks 0x2385dc and AntQueen_updateBank 0x238448: the bodies of
                            tools/ref_combat_round5.py (QueenModel), run here inline

The prologue (damage, Creature_run, activity not tested, stepAnim(1.0) whose event bits
the attack states read, applyKnockback(0.5), slot 23) is tools/ref_combat_ctors.py's.
"""
import ref_core as C
import ref_creature as RC
import ref_combat_ctors as CT
import ref_combat_round5 as R5
from ref_creature import Ext, M32, s8, s16, s32

ANTQUEEN_RUN, PICK_FLY_DEST = 0x236F78, 0x238150
FADE_BANK, UPDATE_BANK = 0x2385DC, 0x238448
RUN_SWITCH = 0x541B80                           # 26 words; 2, 4, 0xb-0x11, 0x15, 0x16 go to the exit
STATE_COUNT = 0x1A
G_SKILL_TABLE = 0x41B170                        # pointers to the Skill objects, by id
G_SKILL_POISONWEAPONS = G_SKILL_TABLE + 4 * 26  # 0x41b1d8: skill 26, SkillPoisonWeapons (object 0x6e1f00)
G_WORLD = RC.G_WORLD                            # 0x44fdc8
G_LEVEL_MONSTER_LEVEL = RC.G_LEVEL_MONSTER_LEVEL

ZERO, ONE = RC.ZERO, RC.ONE
F_2M16 = RC.F_2M16                              # 0x37800000, pickFlyDest 0x2381b0
F_10 = 0x41200000                               # state 0x19 wave offset, 0x237638
F_12 = 0x41400000                               # pickFlyDest height window, 0x2382c0
F_20 = 0x41A00000                               # bite reach, 0x237134 / 0x2371f0 / 0x237380
F_30 = 0x41F00000                               # Creature_deadUpdate size, 0x2378b0
F_36 = 0x42100000                               # state 6 reach, 0x237460
F_40 = 0x42200000                               # cone / sting reach, 0x237170 / 0x237240 / 0x2375cc / 0x2377d8
F_150 = 0x43160000                              # pickFlyDest probe behind the facing, 0x2381cc
F_300 = 0x43960000                              # pickFlyDest distance base and span, 0x2381c0
F_500 = 0x43FA0000                              # state 0x17 landing sight, 0x2372b8
POISON = 0x17                                   # descriptor entry id the stings build
WAVE_SIZE, WAVE_LIFE = 0x3D8, 600               # pool_new size and the last AntWave_ctor argument

# bodies executed by tools/difftest_antqueen_run.py (name -> entry)
EXECUTED = {'AntQueen_run': 0x236F78, 'AntQueen_pickFlyDest': 0x238150}

EXTERNALS = dict(CT.EXTERNALS)
EXTERNALS.update({
    'Creature_hitTargetOrPlayerInArc': Ext(0x119A20, 'piiiiiiE', 2, 'i',
                                           '(creature, facing, arc, min, max, attack rating, damage flags, '
                                           'descriptor; near, far) -> hit'),
    'AntWave_ctor': Ext(0x238654, 'ppvii', 0, 'n', '(block, target, position, facing, 600)'),
})


def shape_result(name, args, ret=0, fret=0, outs=None):
    """CT.shape_result for this module's rows."""
    saved = CT.M1.EXTERNALS
    CT.M1.EXTERNALS = EXTERNALS
    try:
        return CT.M1.shape_result(name, args, ret, fret, outs)
    finally:
        CT.M1.EXTERNALS = saved


def poison_descriptor(value):
    """The stack descriptor states 7, 9 and 10 build: eight zero halfwords, two 0xff
    bytes, four free slots; the search for a free slot or one of id 0x17 always takes
    slot 0, which gets (0x17, value, value, 0) with the low 16 bits of the value."""
    v = value & 0xFFFF
    return ('desc', ((POISON, v, v, 0), None, None, None))


class Model(CT.Model):
    """AntQueen_run in full on a memory image."""

    fade_bank_tracks = R5.QueenModel.fade_bank_tracks
    update_bank = R5.QueenModel.update_bank
    _clips = R5.QueenModel._clips

    def call(self, name, *args):
        if name == 'AntQueen_pickFlyDest':      # executed here: not a callback
            return self.antqueen_pick_fly_dest(args[0] & M32)
        args = tuple(a & M32 if isinstance(a, int) else a for a in args)
        self.calls.append((name, args))
        function = self.cb.get(name)
        if function is not None:
            return function(*args)
        return shape_result(name, args)

    # ---- helpers --------------------------------------------------------------------------
    def tracks_below_4(self, c):
        return s8(self.u8(c + 0x118)) < 4

    def expired(self, c, offset):
        """The signed word at offset strictly below the creature clock +0x300."""
        return self.s32(c + offset) < self.s32(c + 0x300)

    def poison_value(self):
        """Slot 11 (getStatTier2) of the SkillPoisonWeapons object at g_skillTable[26]:
        (statistic 0, level = trunc(g_levelMonsterLevel), cap 0)."""
        return self.table_call('Skill', self.u32(G_SKILL_POISONWEAPONS), 0x60, 11, 0,
                               C.to_int(self.u32(G_LEVEL_MONSTER_LEVEL)), 0)

    def back_facing(self, c, sign):
        """The facing halfword read unsigned, plus or minus 0x7fff, narrowed to s16."""
        return s16(self.u16(c + 0x38) + sign * 0x7FFF)

    # ---- the run --------------------------------------------------------------------------
    def antqueen_run(self, c):
        """AntQueen_run 0x236f78 (creature): one tick.

        Prologue (ref_combat_ctors.antqueen_run_prologue), keeping stepAnim's event bits
        ev.  The state is the s16 at +0x232, compared unsigned with 0x1a: anything
        outside 0..0x19 returns.  Then, with st = slot 27, see(arc, far) = canSeeTargetIn
        (own facing, arc, ray 0; near 0, far, lead 0), T = a target handle +0x234:

          0     fade; slot 25 (0) and tracks < 4 -> 3; again slot 25 (0) and tracks < 4
                -> 3; +0xf4 < clock -> 1
          1     bank; slot 25 (0) -> 3; else Creature_moveToDest
          3     bank; no T -> 0; ONE OWN DRAW d: d & 3 != 0: see(6000, 20) -> 6;
                d & 3 == 0: findEnemyInCone(facing - 0x7fff, 6000; 0, 40) -> 7; then
                Creature_moveToTarget; +0x3d4 < clock and tracks < 4 -> 8
          5     ONE OWN DRAW d: as state 3's tests (each only with T), then not rooted -> 3
          6     fade; with T: on ev bit 0 hitTargetAtReach(+0xd0, +0xd2, +0xd4, 0x40008, no
                descriptor; 36) and +0x3cc = 1; +0x3cc == 0 -> turn; clip flag 8 clear -> 3
          7     fade; on ev bit 0 (no target test): poison descriptor, then
                hitTargetOrPlayerInArc(facing + 0x7fff, 3000, +0xd0, +0xd2, +0xd4, 0x40008,
                descriptor; 0, 40); clip flag 8 clear -> 3
          8     bank; no T -> 0; +0x3d4 < clock -> 0x17; clip flag 8 -> stay; see(6000,
                20) -> 9 and ONE OWN DRAW, d % 3 == 0 -> +0x3d4 = 0; else canSeeTargetIn
                (facing 0, arc 0x7fff; 0, 20) -> turn, else Creature_moveToTarget
          9, 10 fade; with T: on ev bit 0 poison descriptor and hitTargetAtReach(+0xd0,
                +0xd2, +0xd4, 0x10004, descriptor; 40); turn; clip flag 8 clear -> 0x17
                from 10, 8 from 9
          0x12  fade; clip flag 0x10 clear and tracks < 4 -> 3
          0x13  not stunned -> 0
          0x14  fade; Creature_deadUpdate(ev, (0, 0, 0), 0; 30)
          0x17  bank; no T -> 0; +0x3d4 < clock: turn, see(3000, 500) -> 0x18; else clip
                flag 8 -> stay; Creature_moveTo(+0x104): arrived, or +0x2c4 >= 31 ->
                +0x3d4 = 0
          0x18  fade; clip flag 8 clear and tracks < 4 -> 3
          0x19  fade; with T and clock == +0xf4 - 120: pool_new(0x3d8) and AntWave_ctor(
                block, target, the point radius + 10 ahead, facing, 600); +0xf4 < clock
                and tracks < 4 -> 3
          2, 4, 0xb-0x11, 0x15, 0x16: nothing."""
        u32 = self.u32
        st = self.set_state
        self.process_damage(c, self.class_model(c))
        if self.run(c, self.class_model(c)):
            return
        self.update_active(c)
        ev = self.step_anim(c, ONE)
        self.call('Creature_applyKnockback', c, CT.HALF)
        self.vcall(c, 23, 0)
        state = self.s16(c + 0x232)
        if not 0 <= state < STATE_COUNT:
            return
        target = lambda: u32(c + 0x234)       # noqa: E731
        if state == 0:
            self.fade_bank_tracks(c)
            if self.vcall(c, 25, 0) and self.tracks_below_4(c):
                return st(c, 3)
            if self.vcall(c, 25, 0) and self.tracks_below_4(c):
                return st(c, 3)
            if self.expired(c, 0xF4):
                return st(c, 1)
        elif state == 1:
            self.update_bank(c)
            if self.vcall(c, 25, 0):
                return st(c, 3)
            self.move_to_dest(c)
        elif state == 3:
            self.update_bank(c)
            if not target():
                return st(c, 0)
            if self.obj_rand(c) & 3:
                if self.see(c, 6000, F_20):
                    return st(c, 6)
            elif self.call('creature_findEnemyInCone', c, self.back_facing(c, -1), 6000, ZERO, F_40):
                return st(c, 7)
            self.move_to_target(c)
            if self.expired(c, 0x3D4) and self.tracks_below_4(c):
                return st(c, 8)
        elif state == 5:
            roll = self.obj_rand(c) & 3
            if roll:
                if target() and self.see(c, 6000, F_20):
                    return st(c, 6)
            elif target() and self.call('creature_findEnemyInCone', c, self.back_facing(c, -1), 6000, ZERO, F_40):
                return st(c, 7)
            if self.is_not_rooted(c):
                return st(c, 3)
        elif state == 6:
            self.fade_bank_tracks(c)
            if target():
                if ev & 1:
                    self.call('Creature_hitTargetAtReach', c, self.s16(c + 0xD0), self.s16(c + 0xD2),
                              self.s16(c + 0xD4), 0x40008, 0, F_36)
                    self.w32(c + 0x3CC, 1)
                if not u32(c + 0x3CC):
                    self.turn_to_target(c)
            if not self.anim_flags(c, 8):
                return st(c, 3)
        elif state == 7:
            self.fade_bank_tracks(c)
            if ev & 1:
                descriptor = poison_descriptor(self.poison_value())
                self.call('Creature_hitTargetOrPlayerInArc', c, self.back_facing(c, 1), 3000, self.s16(c + 0xD0),
                          self.s16(c + 0xD2), self.s16(c + 0xD4), 0x40008, descriptor, ZERO, F_40)
            if not self.anim_flags(c, 8):
                return st(c, 3)
        elif state == 8:
            self.update_bank(c)
            if not target():
                return st(c, 0)
            if self.expired(c, 0x3D4):
                return st(c, 0x17)
            if self.anim_flags(c, 8):
                return
            if self.see(c, 6000, F_20):
                st(c, 9)
                if self.obj_rand(c) % 3 == 0:
                    self.w32(c + 0x3D4, 0)
                return
            if self.can_see_target_in(c, 0, 0x7FFF, 0, ZERO, F_20, ZERO):
                self.turn_to_target(c)
            else:
                self.move_to_target(c)
        elif state in (9, 10):
            self.fade_bank_tracks(c)
            if target():
                if ev & 1:
                    descriptor = poison_descriptor(self.poison_value())
                    self.call('Creature_hitTargetAtReach', c, self.s16(c + 0xD0), self.s16(c + 0xD2),
                              self.s16(c + 0xD4), 0x10004, descriptor, F_40)
                self.turn_to_target(c)
            if self.anim_flags(c, 8):
                return
            return st(c, 0x17 if self.s16(c + 0x232) == 10 else 8)
        elif state == 0x12:
            self.fade_bank_tracks(c)
            if not self.anim_flags(c, 0x10) and self.tracks_below_4(c):
                return st(c, 3)
        elif state == 0x13:
            if self.is_not_stunned(c):
                return st(c, 0)
        elif state == 0x14:
            self.fade_bank_tracks(c)
            self.dead_update(c, ev, 0, F_30)
        elif state == 0x17:
            self.update_bank(c)
            if not target():
                return st(c, 0)
            if self.expired(c, 0x3D4):
                self.turn_to_target(c)
                if self.see(c, 3000, F_500):
                    return st(c, 0x18)
                return
            if self.anim_flags(c, 8):
                return
            if self.move_to(c, self.vec(c + 0x104)) or self.s32(c + 0x2C4) >= 31:
                self.w32(c + 0x3D4, 0)
        elif state == 0x18:
            self.fade_bank_tracks(c)
            if not self.anim_flags(c, 8) and self.tracks_below_4(c):
                return st(c, 3)
        elif state == 0x19:
            self.fade_bank_tracks(c)
            if target() and self.s32(c + 0x300) == s32(u32(c + 0xF4) - 120):
                facing = self.s16(c + 0x38)
                x = C.add(u32(c + 0x10), C.mul(C.cos16(facing), C.add(u32(c + 0x1C), F_10)))
                y = C.add(u32(c + 0x14), C.mul(C.sin16(facing), C.add(u32(c + 0x1C), F_10)))
                point = (x, y, u32(c + 0x18))
                block = self.call('pool_new', WAVE_SIZE)
                if block:
                    self.call('AntWave_ctor', block, u32(u32(c + 0x234) + 0xC), point, self.s16(c + 0x38),
                              WAVE_LIFE)
            if self.expired(c, 0xF4) and self.tracks_below_4(c):
                return st(c, 3)

    # ---- the flight destination -------------------------------------------------------------
    def pick_fly_dest_entry(self, out, q):
        """AntQueen_pickFlyDest as an entry point: returns out (as the original's v0) and
        keeps the position the original writes there in self.dest."""
        self.dest = self.antqueen_pick_fly_dest(q)
        return out

    def antqueen_pick_fly_dest(self, q):
        """AntQueen_pickFlyDest 0x238150 (out, queen) -> the position written to out.

        No target: the queen's position.  Otherwise up to ten tries, each THREE OWN DRAWS:
        an angle a = s16(d1); the point (target.x + (d2 * 2^-16 * 300 + 300) * cos a,
        target.y + (d3 * 2^-16 * 300 + 300) * sin a, the queen's z); a probe 150 behind
        the queen's FACING from that point (cos16/sin16 of s16 facing - 0x7fff, not
        narrowed); terrain_height(g_world, probe; the queen's radius +0x1c).  The first
        try whose height h has z - 12 < h < z + 12 (both strict, z re-read) is the answer;
        after ten misses, the queen's position again."""
        u32 = self.u32
        if not u32(q + 0x234):
            return self.vec(q + 0x10)
        for _ in range(10):
            angle = s16(self.obj_rand(q))
            cos_a = C.cos16(angle)
            t = u32(u32(q + 0x234) + 0xC)
            d = self.obj_rand(q)
            x = C.add(u32(t + 0x10), C.mul(C.add(C.mul(C.mul(C.from_int(d), F_2M16), F_300), F_300), cos_a))
            sin_a = C.sin16(angle)
            t = u32(u32(q + 0x234) + 0xC)
            d = self.obj_rand(q)
            y = C.add(u32(t + 0x14), C.mul(C.add(C.mul(C.mul(C.from_int(d), F_2M16), F_300), F_300), sin_a))
            z = u32(q + 0x18)
            behind = self.s16(q + 0x38) - 0x7FFF
            px = C.add(x, C.mul(C.cos16(behind), F_150))
            py = C.add(y, C.mul(C.sin16(behind), F_150))
            h = self.call('terrain_height', u32(G_WORLD), (px, py, z), u32(q + 0x1C))
            qz = u32(q + 0x18)
            if C.lt(C.sub(qz, F_12), h) and C.lt(h, C.add(qz, F_12)):
                return (x, y, z)
        return self.vec(q + 0x10)
