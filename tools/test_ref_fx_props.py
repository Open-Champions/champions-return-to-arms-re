#!/usr/bin/env python3
"""Synthetic tests of tools/ref_fx_props.py (no game data)."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_core as C          # noqa: E402
import ref_fx_props as F      # noqa: E402

TABLE = [(i * 37) % 2000 - 1000 for i in range(256)]


def f(p):
    return C.to_float(p)


class Props(unittest.TestCase):
    def test_torch_counts_by_kind(self):
        for kind, flames in ((0, 1), (1, 1), (2, 3), (3, 1), (4, 4), (5, 3)):
            t = F.FireProp(F.TORCH, 0x1000, (0.0, 0.0, 0.0), 77, kind=kind)
            out = F.torch_run(t, 1, TABLE)                      # odd frame: no smoke
            self.assertEqual(sum(s.definition == F.DEF_TORCH_FLAME for s in out.spawns), flames)
            self.assertTrue(all(s.backdate == (C.f32(0.25) if kind == 3 else 0)
                                for s in out.spawns if s.definition == F.DEF_TORCH_FLAME))

    def test_torch_smoke_every_eighth_frame(self):
        t = F.FireProp(F.TORCH, 0x1000, (0.0, 0.0, 0.0), 5, kind=0)
        self.assertEqual([s.definition for s in F.torch_run(t, 8, TABLE).spawns][:2],
                         [F.DEF_TORCH_FLAME, F.DEF_TORCH_SMOKE])
        t4 = F.FireProp(F.TORCH, 0x1000, (0.0, 0.0, 0.0), 5, kind=4)
        self.assertNotIn(F.DEF_TORCH_SMOKE, [s.definition for s in F.torch_run(t4, 8, TABLE).spawns])

    def test_torch_radius_range(self):
        t = F.FireProp(F.TORCH, 0x2000, (0.0, 0.0, 0.0), 1)
        for frame in range(50):
            F.torch_run(t, frame, TABLE)
            self.assertTrue(160 - 21 <= f(t.model_radius) <= 160 + 21)
            self.assertEqual(t.model_radius, t.level_radius)

    def test_candle_radius_every_five(self):
        c = F.FireProp(F.CANDLE, 0x3000, (0.0, 0.0, 10.0), 9)
        radii = []
        for frame in range(10):
            F.candle_run(c, frame)
            radii.append(f(c.model_radius))
        self.assertEqual(radii[:4], [240.0] * 4)
        self.assertTrue(48 <= radii[4] <= 63)
        big = F.FireProp(F.CANDLE, 0x3000, (0.0, 0.0, 10.0), 9, big=True)
        for frame in range(5):
            F.candle_run(big, frame)
        self.assertTrue(84 <= f(big.model_radius) <= 99)

    def test_candle_particle_rises(self):
        c = F.FireProp(F.CANDLE3, 0x3000, (1.0, 2.0, 3.0), 9)
        s = F.candle3_run(c).spawns[0]
        self.assertEqual(s.velocity[:2], [0, 0])
        self.assertTrue(3.2 <= f(s.velocity[2]) <= 3.8)
        self.assertGreaterEqual(f(s.position[2]), 8.0)

    def test_lantern_mine(self):
        a = F.FireProp(F.LANTERN, 0x4000, (0.0, 0.0, 0.0), 1, level_name='d_mine2')
        F.lantern_run(a, 3, TABLE)
        self.assertEqual(a.level_radius, 0)
        b = F.FireProp(F.LANTERN, 0x4000, (0.0, 0.0, 0.0), 1, level_name='castle')
        F.lantern_run(b, 3, TABLE)
        self.assertEqual(b.level_radius, b.model_radius)

    def test_lamp_speed(self):
        lp = F.FireProp(F.LAMP, 0x5000, (0.0, 0.0, 0.0), 3)
        out = F.lamp_run(lp, 0, TABLE)
        self.assertEqual(len(out.spawns), 2)
        for s in out.spawns:
            self.assertAlmostEqual(math.sqrt(sum(f(v) ** 2 for v in s.velocity)), 2.846, places=4)

    def test_stop_after_31_undrawn(self):
        lp = F.FireProp(F.LAMP, 0x5000, (0.0, 0.0, 0.0), 3)
        stops = [F.lamp_run(lp, i, TABLE).stopped for i in range(33)]
        self.assertEqual(stops.index(True), 31)


if __name__ == '__main__':
    unittest.main()
