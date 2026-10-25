#!/usr/bin/env python3
"""test_ref_skeleton_run.py - unit tests of tools/ref_skeleton_run.py that need no game files.

Made-up memory only, with the prologue and the base-class bodies replaced by recorders so
each test sees one piece alone: the range test, the bow's second sight in states 0 and 1,
state 3's melee sweep and its timer draw, state 5's re-read kind and the previous-1
sweep, state 6's guard flag, state 8's release (origin, unchanged angle on a far lead,
unit-ball draws, the projectile per element, MissileWeapon's halved stack word), the
count-downs, the line-of-fire sweep's frame test and thresholds, the lead point, and slot
12's arc.  Whether the model matches the game is tools/difftest_skeleton_run.py's
business (it needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skeleton_run as SR                   # noqa: E402

f32 = C.f32
CRE, NODE, TARGET, HOLDER, HTABLE = 0x100000, 0x120000, 0x130000, 0x140000, 0x150000


def lcg(seed):
    return (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF


class Recorder(SR.Model):
    """The switch alone: the prologue's pieces and the base bodies only record."""

    def setup(self, sight=(), ev=0, see=(), ally=None, rooted=False, away=0):
        self.log, self.sight, self.ev, self.see_answers = [], list(sight), ev, list(see)
        self.ally, self.rooted, self.away = ally, rooted, away

    def process_damage(self, c, model):
        pass

    def run(self, c, model):
        return 0

    def update_active(self, c):
        return 1

    def step_anim(self, c, speed):
        return self.ev

    def vcall(self, obj, slot, *args):
        if slot == 25:
            self.log.append(('sight',) + args)
            return self.sight.pop(0) if self.sight else 0
        if slot == 27:
            self.log.append(('state', args[0]))
            self.w16(obj + 0x232, args[0])
            return None
        self.log.append(('slot%d' % slot,) + args)
        return 0

    def holder_call(self, holder, slot, *args):
        self.log.append(('holder%d' % slot,) + args)
        return self.cb.holder_answers.get(slot, 0)

    def can_see_target_in(self, c, facing, arc, ray_mode, near, far, lead):
        self.log.append(('see', arc, ray_mode, far))
        return self.see_answers.pop(0) if self.see_answers else 0

    def ally_in_line_of_fire(self, c, target, previous, reach, distance):
        if self.ally is None:
            return SR.Model.ally_in_line_of_fire(self, c, target, previous, reach, distance)
        self.log.append(('ally', target, previous))
        return self.ally

    def move_to_target(self, c):
        self.log.append(('chase',))

    def move_to_dest(self, c):
        self.log.append(('wander',))

    def turn_to_target(self, c):
        self.log.append(('turn',))

    def is_away_from_home(self, c):
        return self.away

    def is_not_rooted(self, c):
        return 0 if self.rooted else 1


class Fixture(unittest.TestCase):
    answers = {}

    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.model = Recorder(self.mem, self)
        self.model.setup()
        self.answers = dict(self.answers)
        self.holder_answers = {}
        self.mem.poke(NODE + 0xC, 4, TARGET)
        self.mem.poke(CRE + 0x300, 4, 1000)                  # the creature clock
        self.mem.poke(CRE + 0xF4, 4, 5000)
        self.mem.poke(CRE + 0x1C, 4, f32(18.0))
        self.mem.poke(CRE + 0x20, 4, f32(60.0))
        self.mem.poke(TARGET + 0x10, 4, f32(100.0))

    def get(self, name):
        if name in self.answers:
            value = self.answers[name]
            return value if callable(value) else (lambda *args: value)
        return None

    def state(self, n, target=True, kind=0, holder=0, **kw):
        self.mem.poke(CRE + 0x232, 2, n)
        self.mem.poke(CRE + 0x234, 4, NODE if target else 0)
        self.mem.poke(CRE + 0x3D0, 4, kind)
        self.mem.poke(CRE + 0x50, 4, holder)
        self.model.setup(**kw)
        self.model.calls = []
        self.model.skeleton_run(CRE)
        return self.model.log

    def named(self, name):
        return [args for n, args in self.model.calls if n == name]


class Switch(Fixture):
    def test_out_of_range_and_empty_arms(self):
        for n in (0x18, 0x19, 0x40, 0x7FFF, 0xFFFF, 2, 4, 7, 9, 0xF, 0x15, 0x16):
            self.assertEqual(self.state(n), [('slot23', 0)], hex(n))

    def test_idle_second_sight_only_for_the_bow(self):
        self.assertEqual(self.state(0, kind=1)[1:], [('sight', 0)])
        self.assertEqual(self.state(0, kind=4)[1:], [('sight', 0), ('sight', 1)])
        self.assertEqual(self.state(0, kind=4, sight=(0, 1))[-1], ('state', 3))

    def test_idle_and_wander_timers(self):
        self.mem.poke(CRE + 0xF4, 4, 999)
        self.assertEqual(self.state(0)[-1], ('state', 1))
        self.assertEqual(self.state(1)[-1], ('state', 0))
        self.mem.poke(CRE + 0xF4, 4, 1000)                  # not expired: equal is not below
        self.assertEqual(self.state(0, away=1)[-1], ('state', 1))
        self.assertEqual(self.state(0, away=0)[-1], ('sight', 0))
        self.assertEqual(self.state(1)[-1], ('wander',))

    def test_chase_bow(self):
        log = self.state(3, kind=4, see=(1,))
        self.assertEqual(log[1:], [('see', 2000, 1, SR.F_400), ('state', 8)])
        log = self.state(3, kind=4, see=(0, 1))
        self.assertEqual(log[-2:], [('see', 0x7FFF, 1, SR.F_400), ('turn',)])

    def test_chase_melee_sweep_draws_the_timer(self):
        self.mem.poke(CRE + 0x44, 4, 7)
        log = self.state(3, kind=0, ally=1)
        self.assertEqual(log[1:4], [('see', 6000, 0, SR.F_24), ('ally', TARGET, 0), ('state', 5)])
        d = lcg(7) >> 16
        self.assertEqual(self.mem.load(CRE + 0xF4, 4), 1000 + d % 240 + 240)
        log = self.state(3, kind=0, ally=0)
        self.assertEqual(log[-2:], [('see', 0x7FFF, 0, SR.F_20), ('chase',)])
        self.assertEqual(self.state(3, target=False)[-1], ('state', 0))

    def test_guard_state5(self):
        self.assertEqual(self.state(5, kind=4, see=(1,))[-1], ('state', 8))
        log = self.state(5, kind=4, see=(0,), ally=1)
        self.assertNotIn(('see', 6000, 0, SR.F_20), log)          # the bow skips the melee sight
        self.assertEqual(self.state(5, kind=0, see=(1,))[-1], ('state', 6))
        self.assertEqual(self.state(5, rooted=True)[-1], ('see', 6000, 0, SR.F_20))
        self.assertEqual(self.state(5, ally=1)[-1], ('ally', TARGET, 1))
        self.assertEqual(self.state(5, ally=0)[-1], ('state', 3))
        self.mem.poke(CRE + 0xF4, 4, 3)
        self.assertEqual(self.state(5, ally=1)[-1], ('state', 3))

    def test_swing_sets_guard_flag_and_counts_down(self):
        self.mem.poke(CRE + 0xF4, 4, 2)
        self.state(6, ev=1)
        self.assertEqual(self.named('Creature_hitTargetAtReach')[0][4:], (8, 0, SR.F_36))
        self.assertEqual(self.mem.load(CRE + 0xA8, 8) & 0x200, 0x200)
        self.assertEqual(self.mem.load(CRE + 0xF4, 4), 1)
        self.assertEqual(self.state(6)[-1], ('state', 3))
        self.mem.poke(CRE + 0xF4, 4, 2)
        self.mem.poke(CRE + 0x11A, 2, 8)                      # clip playing: turn, no count-down
        self.assertEqual(self.state(6)[-1], ('turn',))
        self.assertEqual(self.mem.load(CRE + 0xF4, 4), 2)

    def test_small_states(self):
        self.mem.poke(CRE + 0x11A, 2, 0x10)
        self.assertEqual(self.state(0x12), [('slot23', 0)])
        self.assertEqual(self.state(0x17)[-1], ('slot23', 0))
        self.mem.poke(CRE + 0x11A, 2, 0)
        self.assertEqual(self.state(0x17)[-1], ('state', 0))
        self.assertEqual(self.state(0x13)[-1], ('state', 0))
        self.mem.poke(CRE + 0x31C, 2, 3)
        self.assertEqual(self.state(0x13), [('slot23', 0)])
        self.state(0x14, ev=5)
        self.assertEqual(self.named('Creature_deadUpdate'), [(CRE, 5, (0, 0, 0), 1, SR.F_20)])
        self.mem.poke(CRE + 0xF4, 4, 999)
        self.assertEqual(self.state(0x11)[-1], ('state', 3))


class Release(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        self.mem.poke(CRE + 0x10, 4, f32(0.0))
        self.mem.poke(CRE + 0x14, 4, f32(0.0))
        self.mem.poke(CRE + 0x18, 4, f32(0.0))
        self.mem.poke(HOLDER, 4, HTABLE)
        self.mem.poke(SR.G_LEVEL_MONSTER_LEVEL, 4, f32(7.9))
        self.answers['pool_new'] = 0x200000

    def test_no_target_still_counts_down(self):
        self.mem.poke(CRE + 0xF4, 4, 1)
        self.assertEqual(self.state(8, target=False)[-2:], [('state', 0), ('state', 3)])

    def test_projectile_per_element(self):
        for element, ctor in ((2, 'ColdArrowProjectile_ctor'), (1, 'FireArrowProjectile_ctor'),
                              (6, 'ExplodeArrowProjectile_ctor'), (0, 'MissileWeapon_ctor'),
                              (3, 'MissileWeapon_ctor'), (0xFFFFFFFF, 'MissileWeapon_ctor')):
            self.holder_answers = {16: element}
            self.state(8, holder=HOLDER, ev=1)
            self.assertEqual(len(self.named(ctor)), 1, element)

    def test_origin_angle_and_missile_words(self):
        self.mem.poke(TARGET + 0x10, 4, f32(0.0))
        self.mem.poke(TARGET + 0x14, 4, f32(200.0))           # 90 degrees off a facing of 0
        self.mem.poke(CRE + 0xD2, 2, 0xFFF9)                  # -7: halved toward zero is -3
        self.state(8, holder=HOLDER, ev=1)
        args = self.named('MissileWeapon_ctor')[0]
        self.assertEqual(args[4], (0, 0, C.add(C.mul(f32(60.0), SR.HALF), SR.F_18)))
        angle = C.atan2_16(f32(200.0), f32(0.0))
        self.assertEqual(args[6], (angle - 0x4000) & 0xFFFFFFFF)
        self.assertEqual(args[8:], (0, 0, 0, (-3) & 0xFFFFFFFF, 0, 0, 0, 4, 0))
        # the far-off-facing lead is replaced by the point 300 ahead (slot 26 sees it)
        self.mem.poke(CRE + 0x11A, 2, 8)
        log = self.state(8, holder=HOLDER, ev=1)
        ahead = (C.mul(C.cos16(0), SR.F_300), C.mul(C.sin16(0), SR.F_300), 0)
        self.assertIn(('slot26', 0, ahead), log)

    def test_release_draws(self):
        self.mem.poke(CRE + 0x44, 4, 1)
        self.state(8, holder=HOLDER, ev=1)
        seed, tries = 1, 0
        while True:
            vals = []
            for _ in range(3):
                seed = lcg(seed)
                vals.append(C.sub(C.add(*(2 * [C.mul(C.from_int(seed >> 16), SR.F_2M16)])), SR.ONE))
            tries += 1
            size = C.add(C.add(C.mul(vals[0], vals[0]), C.mul(vals[1], vals[1])), C.mul(vals[2], vals[2]))
            if not C.lt(SR.ONE, size):
                break
        seed = lcg(seed)
        self.assertEqual(self.named('libc_sprintf'), [(SR.S_SWISH_FORMAT, ((seed >> 16) & 3) + 1)])
        self.assertEqual(self.mem.load(CRE + 0x44, 4), seed)

    def test_hand_two_calls(self):
        log = self.state(8, holder=HOLDER, ev=3)
        self.assertEqual([e for e in log if e[0] == 'holder1'], [('holder1', 2, 0), ('holder1', 2, 0x56)])


class Sweep(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        self.mem.poke(CRE + 0x230, 1, 5)
        self.mem.poke(SR.G_SIM_FRAME, 4, 0x15)               # 0x15 ^ 5 = 0x10: low three bits clear
        self.answers['creature_objInArcRange'] = 1

    def sweep(self, previous, count, t, hit):
        self.answers['world_countLivingNonplayerCreaturesInBox'] = count
        self.answers['world_raycast'] = (t, hit)
        return self.model.ally_in_line_of_fire(CRE, TARGET, previous, SR.F_300, f32(54.0))

    def test_frame_and_target(self):
        self.mem.poke(SR.G_SIM_FRAME, 4, 0x16)
        self.assertEqual(self.sweep(7, 9, f32(0.5), 0), 7)
        self.assertEqual(self.model.ally_in_line_of_fire(CRE, 0, 9, SR.F_300, f32(54.0)), 9)

    def test_thresholds(self):
        self.assertEqual(self.sweep(0, 4, f32(0.5), 0), 1)
        self.assertEqual(self.sweep(0, 3, f32(0.5), 0), 0)
        self.assertEqual(self.sweep(1, 3, f32(0.5), 0), 1)
        self.assertEqual(self.sweep(1, 2, f32(0.5), 0), 0)
        self.assertEqual(self.sweep(0, 9, f32(1.0), 0), 0)
        self.assertEqual(self.sweep(0, 9, 0, 0), 0)
        self.assertEqual(self.sweep(0, 9, f32(0.5), TARGET), 0)

    def test_arc_refusal_is_zero(self):
        self.answers['creature_objInArcRange'] = 0
        self.assertEqual(self.sweep(1, 9, f32(0.5), 0), 0)
        self.assertEqual(self.named('world_raycast'), [])

    def test_ray(self):
        self.sweep(0, 9, f32(0.5), 0)
        args = self.named('world_raycast')[0]
        self.assertEqual(args[1], (0, 0, SR.F_13))
        heading = C.s16(0x4000 - C.atan2_16(f32(100.0), 0))          # the target along +x: heading ~0
        self.assertEqual(args[2], (C.mul(C.cos16(heading), f32(54.0)), C.mul(C.sin16(heading), f32(54.0)), 0))


class LeadAndSlot12(Fixture):
    def test_lead_point(self):
        self.mem.poke(CRE + 0x234, 4, NODE)
        self.mem.poke(TARGET + 0x308, 4, f32(10.0))
        self.mem.poke(TARGET + 0x20, 4, f32(8.0))
        ok, point = self.model.lead_target_point(CRE, None, f32(50.0))
        self.assertEqual(ok, 1)
        self.assertEqual(point, (f32(120.0), 0, f32(4.0)))
        self.mem.poke(CRE + 0x234, 4, 0)
        self.assertEqual(self.model.lead_target_point(CRE, 'kept', f32(50.0)), (0, 'kept'))

    def test_block_only_shielded_in_3_or_5_near_the_facing(self):
        self.mem.poke(CRE + 0x50, 4, HOLDER)
        self.holder_answers = {15: 0x62}
        self.mem.poke(CRE + 0x232, 2, 3)
        self.model.setup()
        self.model.skeleton_on_nearby_event(CRE, 2, (0, 0, 0), TARGET)      # bearing 0, facing 0
        self.assertEqual(self.model.log[-1], ('state', 0x11))
        for code, part, state in ((1, 0x62, 3), (2, 0x61, 3), (2, 0x60, 6)):
            self.holder_answers = {15: part}
            self.mem.poke(CRE + 0x232, 2, state)
            self.model.setup()
            self.model.skeleton_on_nearby_event(CRE, code, (0, 0, 0), TARGET)
            self.assertNotIn(('state', 0x11), self.model.log)
        self.holder_answers = {15: 0x60}
        self.mem.poke(CRE + 0x232, 2, 5)
        self.mem.poke(CRE + 0x38, 2, 10000)                   # 10000 off: outside the 19999 window
        self.model.setup()
        self.model.skeleton_on_nearby_event(CRE, 2, (0, 0, 0), TARGET)
        self.assertNotIn(('state', 0x11), self.model.log)

    def test_has_shield_without_holder(self):
        self.mem.poke(CRE + 0x50, 4, 0)
        self.assertEqual(self.model.skeleton_has_shield(CRE), 0)


if __name__ == '__main__':
    unittest.main()
