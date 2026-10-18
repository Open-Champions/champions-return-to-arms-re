#!/usr/bin/env python3
"""Synthetic tests of tools/ref_fx_recipes.py (no game files needed).  The bit-for-bit
comparison with the original is tools/difftest_fx_recipes.py."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                                    # noqa: E402
import ref_fx_recipes as R                              # noqa: E402

F = C.to_float
POS = [C.f32(100.5), C.f32(-200.25), C.f32(30.0)]


def spawns(calls):
    return [c for c in calls if c[0] == 'spawn']


class FxSpawnTest(unittest.TestCase):
    def run_id(self, fx_id, seed=12345, **kw):
        cos, shr = C.Lcg(seed), C.Lcg(seed ^ 0x5555)
        calls = R.fx_spawn(fx_id, POS, cos, shr, **kw)
        return calls, cos, shr

    def test_counts(self):
        counts = {0: 300, 1: 300, 2: 150, 3: 150, 4: 150, 6: 150, 7: 3, 8: 300, 9: 300,
                  10: 105, 0xB: 40, 0xC: 35, 0xD: 1, 0xE: 1, 0xF: 1, 0x10: 1, 0x11: 1,
                  0x12: 1, 0x14: 3, 0x15: 10, 0x16: 2}
        for fx_id, n in counts.items():
            self.assertEqual(len(spawns(self.run_id(fx_id)[0])), n, hex(fx_id))

    def test_camera_gate_and_id5(self):
        calls, cos, _ = self.run_id(2, near=False)
        self.assertEqual(calls, [('near', POS)])
        self.assertEqual(cos.state, 12345)
        calls, cos, shr = self.run_id(5, near=False)
        self.assertNotIn('near', [c[0] for c in calls])
        fires = [c for c in calls if c[0] == 'fire']
        self.assertIn(len(fires), (3, 4))
        self.assertEqual(cos.state, 12345)              # id 5 draws only the shared seed
        self.assertNotEqual(shr.state, 12345 ^ 0x5555)
        for c in fires:
            self.assertTrue(-6 <= F(c[1][0]) - F(POS[0]) <= 5)
            self.assertTrue(0 <= F(c[1][2]) - F(POS[2]) <= 17)

    def test_gore_zero_blocks_red_blood_only(self):
        self.assertEqual(spawns(self.run_id(0, gore=0)[0]), [])
        self.assertEqual(spawns(self.run_id(1, gore=0)[0]), [])
        self.assertEqual(len(spawns(self.run_id(9, gore=0)[0])), 300)

    def test_first_use_constructs_all_definitions_once(self):
        made = set()
        calls = self.run_id(0x11, made=made)[0]
        self.assertEqual([c[1] for c in calls if c[0] == 'ctor'], list(R.FX_SPAWN_DEFS))
        calls = self.run_id(0x11, made=made)[0]
        self.assertEqual([c for c in calls if c[0] == 'ctor'], [])

    def test_backdate_is_zero_and_static_ids_have_no_velocity(self):
        for fx_id in range(0x17):
            for c in spawns(self.run_id(fx_id)[0]):
                self.assertEqual(c[1], 0)
        for fx_id in (0xD, 0xE, 0xF, 0x10, 0x11, 0x12):
            (c,) = spawns(self.run_id(fx_id)[0])
            self.assertEqual(c[4], [0, 0, 0])

    def test_id6_scales_all_axes_by_16(self):
        for c in spawns(self.run_id(6)[0]):
            self.assertLessEqual(sum(F(v) ** 2 for v in c[4]), 16.0 ** 2 * 1.0001)

    def test_upward_ids(self):
        for fx_id in (0x16,):
            for c in spawns(self.run_id(fx_id)[0]):
                self.assertGreaterEqual(F(c[4][2]), 0.0)
        for seed in range(50):
            for c in spawns(self.run_id(7, seed=seed)[0]):
                self.assertGreater(F(c[4][2]), 6.05 - 4.75 * 0.77 - 1e-3)

    def test_id15_vertical_terms_vanish_except_at_minus_one(self):
        for seed in range(30):
            for c in spawns(self.run_id(0x15, seed=seed)[0]):
                self.assertIn(F(c[4][2]), (0.0, 12.0))
                self.assertIn(F(c[3][2]) - F(POS[2]), (0.0, 6.0, 36.0))

    def test_id13_second_particle_one_in_ten(self):
        extra = sum(len(spawns(self.run_id(0x13, seed=s)[0])) - 1 for s in range(400))
        self.assertTrue(10 <= extra <= 80, extra)

    def test_point_within_15(self):
        for seed in range(100):
            (c,) = spawns(self.run_id(0xD, seed=seed)[0])
            dx, dy = F(c[3][0]) - F(POS[0]), F(c[3][1]) - F(POS[1])
            self.assertLessEqual(dx * dx + dy * dy, 15.0 ** 2 * 1.001)
            self.assertTrue(-7.5 <= F(c[3][2]) - F(POS[2]) <= 7.5)


if __name__ == '__main__':
    unittest.main()
