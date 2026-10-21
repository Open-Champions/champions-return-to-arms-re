#!/usr/bin/env python3
"""test_ref_sweep.py - unit tests of tools/ref_sweep.py that need no game files.

Made-up memory: the box count's flag test (0x68 == 0x20) and box, the arc test's bearing,
signed arc compare, radius-reduced range and terrain-ray answers.  Whether the model
matches the game is tools/difftest_sweep.py's business (it needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_sweep as SW                          # noqa: E402

f32 = C.f32
CRE, OBJ = 0x100000, 0x110000
OTHERS = (0x120000, 0x121000, 0x122000, 0x123000, 0x124000)


class Fixture(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.model = SW.Model(self.mem, self)
        self.found, self.ray = [], f32(-1.0)
        self.boxes, self.rays = [], []

    def get(self, name):
        if name == 'world_collectObjectsInBox':
            def collect(low, high, cap):
                self.boxes.append((low, high, cap))
                return list(self.found)
            return collect
        if name == 'terrain_raycast':
            def ray(world, origin, direction, mask, length):
                self.rays.append((origin, direction, mask, length))
                return self.ray
            return ray
        return None

    def place(self, obj, x, y, z=0.0, height=72.0, radius=12.0, facing=0):
        for off, v in ((0x10, x), (0x14, y), (0x18, z), (0x20, height), (0x1C, radius)):
            self.mem.poke(obj + off, 4, f32(v))
        self.mem.poke(obj + 0x38, 2, facing & 0xFFFF)


class Count(Fixture):
    def test_counts_living_non_players_only(self):
        for obj, flags in zip(OTHERS, (0x20, 0x60, 0x28, 0x20 | 0x1000, 0x30)):
            self.mem.poke(obj + 0xC, 4, flags)
        self.found = list(OTHERS)
        n = self.model.count_living((f32(10.0), f32(20.0), f32(0.0)), f32(21.0))
        self.assertEqual(n, 3)                   # 0x20, 0x1020 and 0x30 pass; 0x60 and 0x28 do not
        low, high, cap = self.boxes[0]
        self.assertEqual(low, (f32(-11.0), f32(-1.0), f32(-21.0)))
        self.assertEqual(high, (f32(31.0), f32(41.0), f32(21.0)))
        self.assertEqual(cap, 0x80)


class Arc(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        self.place(CRE, 0.0, 0.0, facing=0)
        self.place(OBJ, 100.0, 0.0)

    def test_no_object(self):
        self.assertEqual(self.model.obj_in_arc_range(CRE, 0, 0x4000, f32(300.0)), 0)

    def test_ahead_in_range_ray_misses(self):
        self.assertEqual(self.model.obj_in_arc_range(CRE, OBJ, 0x4000, f32(300.0)), 1)
        origin, direction, mask, length = self.rays[0]
        self.assertEqual(origin[2], f32(72.0))          # the full height, not half
        self.assertEqual(direction, (f32(100.0), f32(0.0), f32(0.0)))
        self.assertEqual((mask, length), (3, SW.F_RAY_LENGTH))

    def test_ray_blocked(self):
        self.ray = f32(0.5)
        self.assertEqual(self.model.obj_in_arc_range(CRE, OBJ, 0x4000, f32(300.0)), 0)
        self.ray = f32(1.0)
        self.assertEqual(self.model.obj_in_arc_range(CRE, OBJ, 0x4000, f32(300.0)), 0)
        self.ray = f32(1.01)
        self.assertEqual(self.model.obj_in_arc_range(CRE, OBJ, 0x4000, f32(300.0)), 1)

    def test_range_less_radius(self):
        # 100^2 - 12 < r^2: 99.94 passes, 99.9 does not
        self.assertEqual(self.model.obj_in_arc_range(CRE, OBJ, 0x4000, f32(99.95)), 1)
        self.assertEqual(self.model.obj_in_arc_range(CRE, OBJ, 0x4000, f32(99.9)), 0)
        self.assertEqual(self.rays and len(self.rays), 1)

    def test_arc_signed(self):
        self.place(OBJ, -100.0, 0.0)                # behind: |diff| = 0x8000
        self.assertEqual(self.model.obj_in_arc_range(CRE, OBJ, 0x7FFF, f32(300.0)), 0)
        self.assertEqual(self.model.obj_in_arc_range(CRE, OBJ, 0x8000, f32(300.0)), 0)   # s16: -0x8000
        self.place(OBJ, 0.0, 100.0)                 # a quarter turn: 0x4000 is not below 0x4000
        self.assertEqual(self.model.obj_in_arc_range(CRE, OBJ, 0x4000, f32(300.0)), 0)
        self.assertEqual(self.model.obj_in_arc_range(CRE, OBJ, 0x4001, f32(300.0)), 1)


if __name__ == '__main__':
    unittest.main()
