#!/usr/bin/env python3
"""test_ref_antwave.py - unit tests of tools/ref_antwave.py that need no game files.

Made-up memory: the constructor's fields and its handle to the target, the destructor's
double clear, the run's three exits (lost target, damage every 60 ticks inside the radius,
lifetime), the strict radius and the signed remainder, and the draw's period, own draws and
particle.  Creature_run and Creature_moveTo are replaced by recorders here (they are the
creature base's models, executed elsewhere).  Whether the model matches the game is
tools/difftest_antwave.py's business (it needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_antwave as AW                        # noqa: E402

f32, fl = C.f32, C.to_float
M32 = 0xFFFFFFFF
WAVE, TARGET, NODE, TABLE = 0x100000, 0x110000, 0x120000, 0x130000


def lcg(seed):
    return (seed * 0x19660D + 0x3C6EF35F) & M32


class Recorded(AW.Model):
    """The model with the creature base's run and walk recorded instead of run."""

    def run(self, c, model):
        self.calls.append(('Creature_run', (c, model)))
        self.w32(c + 0x300, (self.u32(c + 0x300) + 1) & M32)
        return 0

    def move_to(self, c, dest):
        self.calls.append(('Creature_moveTo', (c, tuple(dest))))
        return 0


class Fixture(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.model = Recorded(self.mem, {})
        for slot, fn in ((1, AW.ANTWAVE_DTOR), (4, AW.ANTWAVE_RUN), (5, AW.ANTWAVE_DRAW)):
            self.mem.poke(AW.VT_ANTWAVE + 8 * slot + 4, 4, fn)
        self.mem.poke(TABLE + 8 * 2 + 4, 4, 0x00DEAD00)          # the target's slot 2: not a base body
        self.mem.poke(TARGET + 0x48, 4, TABLE)
        self.mem.poke(NODE + 0xC, 4, TARGET)

    def place(self, obj, x, y, z):
        for k, v in enumerate((x, y, z)):
            self.mem.poke(obj + 0x10 + 4 * k, 4, f32(v))

    def wave(self, clock, life=600, radius=20.0, handle=True):
        self.mem.poke(WAVE + 0x48, 4, AW.VT_ANTWAVE)
        self.mem.poke(WAVE + 0x300, 4, clock & M32)
        self.mem.poke(WAVE + 0x3CC, 4, life & M32)
        self.mem.poke(WAVE + 0x1C, 4, f32(radius))
        self.mem.poke(WAVE + 0x3D0, 4, NODE if handle else 0)
        self.place(WAVE, 0.0, 0.0, 0.0)

    def names(self):
        return [n for n, _a in self.model.calls]

    def calls(self, name):
        return [a for n, a in self.model.calls if n == name]


class Ctor(Fixture):
    def test_fields_and_handle(self):
        self.mem.poke(TARGET + 0x1C, 4, f32(16.0))
        self.mem.poke(WAVE + 0x300, 4, 1234)                     # Creature_ctor zeroes the clock first
        pos = (f32(1.0), f32(2.0), f32(3.0))
        self.model.antwave_ctor(WAVE, TARGET, pos, 0x12345, 600)
        u32 = self.mem.load
        self.assertEqual(u32(WAVE + 0xB0, 4), AW.F_0_6)
        self.assertEqual(u32(WAVE + 0xB8, 4), AW.F_100)
        self.assertEqual(fl(u32(WAVE + 0x1C, 4)), 26.0)
        self.assertEqual(u32(WAVE + 0x48, 4), AW.VT_ANTWAVE)
        self.assertEqual(u32(WAVE + 0x3C8, 4), 0)
        self.assertEqual(u32(WAVE + 0x3CC, 4), 600)
        self.assertEqual(u32(WAVE + 0xC, 4) & 0x21, 0x21)
        self.assertEqual(self.mem.load(WAVE + 0x38, 2), 0x2345)
        self.assertEqual(self.calls('handle_link'), [(WAVE + 0x3D0, TARGET, TARGET)])
        self.assertEqual(self.names()[-1], 'obj_runEveryFrame')
        self.assertEqual(self.calls('GameObject_ctor')[0][2:], (0, 0))   # no class definition, no properties
        self.assertEqual(self.model.draws, 0)


class Dtor(Fixture):
    def test_double_clear_and_free(self):
        self.wave(5)
        self.model.antwave_dtor(WAVE, 3)
        clears = self.calls('handle_clear')
        self.assertEqual(clears[:2], [(WAVE + 0x3D0,), (WAVE + 0x3D0,)])
        self.assertEqual(self.names()[-1], 'pool_free')

    def test_single_clear_without_handle_no_free(self):
        self.wave(5, handle=False)
        self.model.antwave_dtor(WAVE, 2)
        self.assertEqual(self.calls('handle_clear')[:2], [(WAVE + 0x3D0,), (WAVE + 0x364,)])
        self.assertNotIn('pool_free', self.names())


class Run(Fixture):
    def test_lost_target_deletes_without_walking(self):
        self.wave(10, handle=False)
        self.model.antwave_run(WAVE)
        self.assertEqual(self.names()[0], 'Creature_run')
        self.assertNotIn('Creature_moveTo', self.names())
        self.assertEqual(self.names()[-1], 'pool_free')

    def test_walks_to_the_target(self):
        self.wave(10)
        self.place(TARGET, 100.0, 50.0, 0.0)
        self.model.antwave_run(WAVE)
        self.assertEqual(self.calls('Creature_moveTo'), [(WAVE, (f32(100.0), f32(50.0), 0))])
        self.assertNotIn('Creature.v2', self.names())

    def test_hit_every_60_inside_the_radius(self):
        self.wave(59)                                            # Creature_run makes it 60
        self.place(TARGET, 10.0, 0.0, 0.0)
        self.model.antwave_run(WAVE)
        self.assertEqual(self.calls('Creature.v2'), [(TARGET, WAVE, 0x100, AW.ONE)])

    def test_no_hit_off_the_period(self):
        self.wave(60)
        self.place(TARGET, 10.0, 0.0, 0.0)
        self.model.antwave_run(WAVE)
        self.assertNotIn('Creature.v2', self.names())

    def test_radius_is_strict(self):
        self.wave(119, radius=20.0)
        self.place(TARGET, 12.0, 16.0, 0.0)                     # exactly 20 away
        self.model.antwave_run(WAVE)
        self.assertNotIn('Creature.v2', self.names())

    def test_signed_remainder(self):
        self.wave(-61 & M32)                                     # -60 after the run: remainder 0
        self.place(TARGET, 1.0, 0.0, 0.0)
        self.model.antwave_run(WAVE)
        self.assertEqual(len(self.calls('Creature.v2')), 1)

    def test_lifetime(self):
        self.wave(600, life=600)                                 # 601 after the run: 600 < 601
        self.place(TARGET, 500.0, 0.0, 0.0)
        self.model.antwave_run(WAVE)
        self.assertEqual(self.names()[-1], 'pool_free')
        self.setUp()
        self.wave(599, life=600)
        self.place(TARGET, 500.0, 0.0, 0.0)
        self.model.antwave_run(WAVE)
        self.assertNotIn('pool_free', self.names())


class Draw(Fixture):
    def test_period_and_own_draws(self):
        self.wave(4)
        self.mem.poke(WAVE + 0x44, 4, 0x1234)
        self.model.antwave_draw(WAVE)
        self.assertEqual(self.model.calls, [])
        self.wave(6)
        self.place(WAVE, 100.0, 200.0, 5.0)
        self.model.antwave_draw(WAVE)
        (definition, point, velocity, zero), = self.calls('particle_spawn')
        self.assertEqual((definition, velocity, zero), (AW.P_ANTWAVE, (0, 0, 0), 0))
        for k, base in enumerate((100.0, 200.0, 5.0)):
            self.assertLessEqual(abs(fl(point[k]) - base), 10.0)
        seed, n = 0x1234, 0
        while seed != self.mem.load(WAVE + 0x44, 4):
            seed, n = lcg(seed), n + 1
        self.assertEqual(n % 3, 0)
        self.assertEqual(self.model.draws, 0)


class Tables(unittest.TestCase):
    def test_executed_and_slots(self):
        self.assertEqual(AW.EXECUTED, {'AntWave_ctor': 0x238654, 'AntWave_run': 0x238938, 'AntWave_draw': 0x2387D0,
                                       'AntWave_dtor': 0x238750})
        self.assertEqual(AW.CLASS_BODIES[0x238938], (4, 'antwave_run'))
        self.assertEqual(AW.CLASS_BODIES[0x238750], (1, 'antwave_dtor'))
        self.assertNotIn('AntWave_ctor', AW.EXTERNALS)


if __name__ == '__main__':
    unittest.main()
