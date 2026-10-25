#!/usr/bin/env python3
"""test_ref_antqueen_run.py - unit tests of tools/ref_antqueen_run.py that need no game files.

Made-up memory only, with the prologue and the base-class bodies replaced by recorders so
each test sees the switch alone: the range test, state 0's two sight calls, the state-3
bite or rear-cone choice, state 7's untested target, state 8's reset draw, the 0x17
stuck counter, the 0x19 wave frame, the poison descriptor, and AntQueen_pickFlyDest's
draws, window and fall-back.  Whether the model matches the game is
tools/difftest_antqueen_run.py's business (it needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_antqueen_run as AQ                   # noqa: E402

f32 = C.f32
CRE, NODE, TARGET, SKILL, TABLE = 0x100000, 0x120000, 0x130000, 0x140000, 0x150000


def lcg(seed):
    return (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF


class Recorder(AQ.Model):
    """The switch alone: the prologue's pieces and the base bodies only record."""

    def setup(self, sight=(), ev=0, see=(), moved=0):
        self.log, self.sight, self.ev, self.see_answers, self.moved = [], list(sight), ev, list(see), moved

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

    def can_see_target_in(self, c, facing, arc, ray_mode, near, far, lead):
        self.log.append(('see', facing, arc, far))
        return self.see_answers.pop(0) if self.see_answers else 0

    def move_to_target(self, c):
        self.log.append(('chase',))

    def move_to_dest(self, c):
        self.log.append(('wander',))

    def move_to(self, c, dest):
        self.log.append(('moveTo', dest))
        return self.moved

    def turn_to_target(self, c):
        self.log.append(('turn',))

    def fade_bank_tracks(self, c):
        self.log.append(('fade',))

    def update_bank(self, c):
        self.log.append(('bank',))


class Fixture(unittest.TestCase):
    answers = {}

    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.model = Recorder(self.mem, self)
        self.model.setup()
        self.answers = dict(self.answers)
        self.mem.poke(NODE + 0xC, 4, TARGET)
        self.mem.poke(CRE + 0x300, 4, 1000)                  # the creature clock
        self.mem.poke(CRE + 0xF4, 4, 5000)
        self.mem.poke(CRE + 0x3D4, 4, 5000)
        self.mem.poke(AQ.G_SKILL_POISONWEAPONS, 4, SKILL)
        self.mem.poke(SKILL + 0x60, 4, TABLE)
        self.mem.poke(AQ.G_LEVEL_MONSTER_LEVEL, 4, f32(7.9))

    def get(self, name):
        if name in self.answers:
            value = self.answers[name]
            return value if callable(value) else (lambda *args: value)
        return None

    def state(self, n, target=True, **kw):
        self.mem.poke(CRE + 0x232, 2, n)
        self.mem.poke(CRE + 0x234, 4, NODE if target else 0)
        self.model.setup(**kw)
        self.model.calls = []
        self.model.antqueen_run(CRE)
        return self.model.log

    def named(self, name):
        return [args for n, args in self.model.calls if n == name]


class Switch(Fixture):
    def test_out_of_range_does_nothing(self):
        for n in (0x1A, 0x40, 0x7FFF, 0xFFFF, 2, 4, 0x11, 0x15, 0x16):
            self.assertEqual(self.state(n), [('slot23', 0)], hex(n))

    def test_state0_second_sight_when_tracks_full(self):
        self.mem.poke(CRE + 0x118, 1, 4)
        log = self.state(0, sight=(1, 1))
        self.assertEqual(log, [('slot23', 0), ('fade',), ('sight', 0), ('sight', 0)])
        self.mem.poke(CRE + 0x118, 1, 2)
        log = self.state(0, sight=(1,))
        self.assertEqual(log[-1], ('state', 3))

    def test_state0_wanders_when_timer_expired(self):
        self.mem.poke(CRE + 0xF4, 4, 999)
        self.assertEqual(self.state(0)[-1], ('state', 1))

    def test_state3_bite_or_rear_cone(self):
        self.mem.poke(CRE + 0x44, 4, 0)
        d = lcg(0) >> 16
        self.mem.poke(CRE + 0x38, 2, 0x1000)
        self.answers['creature_findEnemyInCone'] = 1
        log = self.state(3, see=(1,))
        if d & 3:
            self.assertIn(('see', 0x1000, 6000, AQ.F_20), log)
            self.assertEqual(log[-1], ('state', 6))
        else:
            self.assertEqual(self.named('creature_findEnemyInCone')[0][1], C.s16(0x1000 - 0x7FFF))
            self.assertEqual(log[-1], ('state', 7))

    def test_state3_without_target(self):
        self.assertEqual(self.state(3, target=False)[-1], ('state', 0))

    def test_state7_stings_without_a_target(self):
        self.answers['Skill.v11'] = 0x12345
        self.mem.poke(CRE + 0x38, 2, 0x9000)
        self.state(7, target=False, ev=1)
        (args,) = self.named('Creature_hitTargetOrPlayerInArc')
        self.assertEqual(args[1], C.s16(0x9000 + 0x7FFF) & 0xFFFFFFFF)
        self.assertEqual(args[2], 3000)
        self.assertEqual(args[6], 0x40008)
        self.assertEqual(args[7], ('desc', ((0x17, 0x2345, 0x2345, 0), None, None, None)))
        self.assertEqual(self.named('Skill.v11')[0][1:], (0, 7, 0))      # trunc(7.9)

    def test_state8_reset_draw(self):
        for seed in range(40):
            self.mem.poke(CRE + 0x44, 4, seed)
            self.mem.poke(CRE + 0x3D4, 4, 5000)
            self.mem.poke(CRE + 0x11A, 2, 0)
            log = self.state(8, see=(1,))
            self.assertEqual(log[-1], ('state', 9))
            want = 0 if (lcg(seed) >> 16) % 3 == 0 else 5000
            self.assertEqual(self.mem.load(CRE + 0x3D4, 4), want)

    def test_state8_takes_off_when_timer_expired(self):
        self.mem.poke(CRE + 0x3D4, 4, 999)
        self.assertEqual(self.state(8)[-1], ('state', 0x17))

    def test_state_0x17_stuck_counter(self):
        self.mem.poke(CRE + 0x11A, 2, 0)
        for counter, want in ((30, 5000), (31, 0), (0xFFFFFFFF, 5000)):
            self.mem.poke(CRE + 0x3D4, 4, 5000)
            self.mem.poke(CRE + 0x2C4, 4, counter)
            self.state(0x17)
            self.assertEqual(self.mem.load(CRE + 0x3D4, 4), want, counter)

    def test_state_0x19_wave_frame(self):
        self.answers['pool_new'] = 0x160000
        self.mem.poke(CRE + 0xF4, 4, 1121)
        self.state(0x19)
        self.assertEqual(len(self.named('AntWave_ctor')), 0)
        self.mem.poke(CRE + 0xF4, 4, 1120)
        self.state(0x19)
        (args,) = self.named('AntWave_ctor')
        self.assertEqual(args[0], 0x160000)
        self.assertEqual(args[1], TARGET)
        self.assertEqual(args[4], 600)
        self.answers['pool_new'] = 0
        self.state(0x19)
        self.assertEqual(self.named('AntWave_ctor'), [])

    def test_state_10_and_9_targets(self):
        self.mem.poke(CRE + 0x11A, 2, 0)
        self.assertEqual(self.state(10)[-1], ('state', 0x17))
        self.assertEqual(self.state(9)[-1], ('state', 8))


class PickFlyDest(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        for k, v in enumerate((100.0, 200.0, 10.0)):
            self.mem.poke(CRE + 0x10 + 4 * k, 4, f32(v))
            self.mem.poke(TARGET + 0x10 + 4 * k, 4, f32(v + 500))
        self.mem.poke(CRE + 0x1C, 4, f32(45.0))
        self.mem.poke(CRE + 0x234, 4, NODE)

    def test_no_target_is_home(self):
        self.mem.poke(CRE + 0x234, 4, 0)
        self.assertEqual(self.model.antqueen_pick_fly_dest(CRE), (f32(100.0), f32(200.0), f32(10.0)))
        self.assertEqual(self.model.calls, [])

    def test_ten_misses_fall_back(self):
        self.answers['terrain_height'] = f32(50.0)
        self.mem.poke(CRE + 0x44, 4, 7)
        self.assertEqual(self.model.antqueen_pick_fly_dest(CRE), (f32(100.0), f32(200.0), f32(10.0)))
        self.assertEqual(len(self.named('terrain_height')), 10)
        s = 7
        for _ in range(30):
            s = lcg(s)
        self.assertEqual(self.mem.load(CRE + 0x44, 4), s)

    def test_window_is_strict(self):
        for h, hit in ((22.0, False), (21.9, True), (-1.9, True), (-2.0, False)):
            self.answers['terrain_height'] = f32(h)
            self.model.calls = []
            self.mem.poke(CRE + 0x44, 4, 7)
            got = self.model.antqueen_pick_fly_dest(CRE)
            self.assertEqual(len(self.named('terrain_height')), 1 if hit else 10, h)
            if hit:
                d1 = lcg(7)
                d2 = lcg(d1)
                angle = C.s16(d1 >> 16)
                radius = C.add(C.mul(C.mul(C.from_int(d2 >> 16), RC.F_2M16), AQ.F_300), AQ.F_300)
                self.assertEqual(got[0], C.add(f32(600.0), C.mul(radius, C.cos16(angle))))
                self.assertEqual(got[2], f32(10.0))

    def test_probe_is_behind_the_facing(self):
        self.mem.poke(CRE + 0x38, 2, 0x4000)
        self.answers['terrain_height'] = f32(10.0)
        self.mem.poke(CRE + 0x44, 4, 7)
        x, y, _z = self.model.antqueen_pick_fly_dest(CRE)
        (args,) = self.named('terrain_height')
        px, py, pz = args[1]
        self.assertEqual(px, C.add(x, C.mul(C.cos16(0x4000 - 0x7FFF), AQ.F_150)))
        self.assertEqual(py, C.add(y, C.mul(C.sin16(0x4000 - 0x7FFF), AQ.F_150)))
        self.assertEqual(args[2], f32(45.0))


class Descriptor(unittest.TestCase):
    def test_low_16_bits(self):
        self.assertEqual(AQ.poison_descriptor(0x10007), ('desc', ((0x17, 7, 7, 0), None, None, None)))


if __name__ == '__main__':
    unittest.main()
