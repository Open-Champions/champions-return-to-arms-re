#!/usr/bin/env python3
"""Synthetic tests of tools/ref_decals.py (no game data)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_core as C          # noqa: E402
import ref_decals as D        # noqa: E402


class Gate(unittest.TestCase):
    def test_detail(self):
        self.assertEqual([D.allowed(k, 0) for k in (0, 1, 2, 3, 9)], [False, False, False, True, True])
        self.assertEqual([D.allowed(k, 1) for k in (0, 1, 2, 3)], [False, True, True, True])
        self.assertTrue(all(D.allowed(k, 2) for k in range(11)))
        self.assertTrue(D.allowed(-1, 0))           # unsigned comparison

    def test_grid(self):
        self.assertEqual(D.cell_of(-3840.0, -3840.0), (0, 0))
        self.assertEqual(D.cell_of(3839.0, 0.0), (29, 15))
        self.assertIsNone(D.cell_of(3840.0, 0.0))
        self.assertIsNone(D.cell_of(0.0, -3841.0))


class Store(unittest.TestCase):
    def test_record(self):
        s = D.DecalStore(2)
        d = s.add(12.0, (10.25, -3.0, 5.0), 0, 9, tint=(1, 2, 3))
        self.assertEqual((d.rgb, d.x4, d.y4, d.z4, d.counted, d.tex), ((1, 2, 3), 41, -12, 32, 0, 0x3D3 + 18))
        self.assertEqual((d.c4, d.s4), (48, 0))
        self.assertEqual(len(d.record()), 0x18)
        self.assertEqual(s.add(1.0, (0.0, 0.0, 0.0), 0, 1).counted, 1)

    def test_cell_limit_and_blocks(self):
        s = D.DecalStore(2)
        made = [s.add(4.0, (1.0, 1.0, 0.0), 0, 9) for _ in range(16)]
        self.assertEqual(sum(d is not None for d in made), D.PER_BLOCK)
        for i in range(D.BLOCKS):                       # one decal in 64 distinct cells
            s.add(4.0, (-3800.0 + 256 * (i % 29), -3800.0 + 256 * (i // 29 + 1), 0.0), 0, 9)
        self.assertEqual(len(s.free), 0)
        self.assertIsNone(s.add(4.0, (3800.0, 3800.0, 0.0), 0, 9))

    def test_z_range_starts_at_zero(self):
        s = D.DecalStore(2)
        s.add(4.0, (0.0, 0.0, 40.0), 0, 9)
        blk = next(iter(s.cells.values()))
        self.assertEqual((blk.zmin, blk.zmax), (0, 40))

    def test_growth_overshoots_by_less_than_a_step(self):
        s = D.DecalStore(2)
        d = s.add(1.0, (0.0, 0.0, 0.0), 0, 10, grow=1)
        self.assertEqual(d.c4, 4)                       # full size until the first step
        steps = 0
        while s.growers[0] is not None:
            s.grow_step()
            steps += 1
        self.assertEqual(steps, 6)                      # 0.2 is cut to 0.19999999: 6 steps
        self.assertEqual(d.c4, 4)                       # trunc(4 x 1.1999999)
        s2 = D.DecalStore(2)
        s2.add(1.0, (0.0, 0.0, 0.0), 0, 10, grow=2)
        n = 0
        while s2.growers[0] is not None:
            s2.grow_step()
            n += 1
        self.assertEqual(n, 21)

    def test_frozen_does_not_grow(self):
        s = D.DecalStore(2)
        s.add(5.0, (0.0, 0.0, 0.0), 0x4000, 10, grow=1)
        s.grow_step(frozen=True)
        self.assertEqual(s.growers[0].size, 0)


if __name__ == '__main__':
    unittest.main()
