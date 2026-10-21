#!/usr/bin/env python3
"""Synthetic tests of tools/ref_rigidbody.py (no game file needed)."""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                             # noqa: E402
import ref_rigidbody as RB                       # noqa: E402


def f(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def g(raw):
    return struct.unpack('<f', struct.pack('<I', raw))[0]


class Mem(RB.RigidMixin):
    def __init__(self):
        self.w = {}
        self.log = []

    def u32(self, a):
        return self.w.get(a, 0)

    def w32(self, a, v):
        self.log.append(a)
        self.w[a] = v & 0xFFFFFFFF


BODY = 0x1000


class Init(unittest.TestCase):
    def build(self, seed, mass=f(1.0), factor=f(1.0), size=(2.0, 3.0, 4.0)):
        m = Mem()
        m.w[RB.G_COSMETIC_SEED] = seed
        for off in range(0, RB.BODY_SIZE, 4):
            m.w[BODY + off] = 0xDEADBEEF               # a dirty block: the clear must show
        m.rb_init(BODY, mass, factor, *[f(s) for s in size])
        return m

    def test_one_cosmetic_draw_and_no_other_seed(self):
        m = self.build(12345)
        self.assertEqual(m.w[RB.G_COSMETIC_SEED], (12345 * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF)
        self.assertEqual(sum(1 for a in m.log if a == RB.G_COSMETIC_SEED), 1)
        self.assertNotIn(0x404464, m.log)

    def test_clears_the_whole_body_and_writes_nothing_beyond(self):
        m = self.build(1)
        self.assertEqual(min(a for a in m.log if a != RB.G_COSMETIC_SEED), BODY)
        self.assertLess(max(a for a in m.log if a != RB.G_COSMETIC_SEED), BODY + RB.BODY_SIZE)
        for off in (0x10, 0x14, 0x18, 0x2C, 0x30, 0x34, 0x38, 0x3C, 0x40, 0x68, 0x6C, 0x88):
            self.assertEqual(m.w[BODY + off], 0, hex(off))      # position, momenta, world inertia

    def test_inverse_mass_and_box_inertia(self):
        m = self.build(0, mass=f(2.0), size=(2.0, 3.0, 4.0))
        self.assertEqual(g(m.w[BODY]), 0.5)
        # M = 2; about x: 12 / (2 (9 + 16)) ; about y: 12 / (2 (4 + 16)); about z: 12 / (2 (4 + 9))
        self.assertAlmostEqual(g(m.w[BODY + 4]), 12 / 50, places=6)
        self.assertAlmostEqual(g(m.w[BODY + 8]), 12 / 40, places=6)
        self.assertAlmostEqual(g(m.w[BODY + 0xC]), 12 / 26, places=6)

    def test_orientation_is_a_turn_about_the_vertical_axis(self):
        for seed in (0, 0x10000, 0x80000000, 0xFFFFFFFF, 0x12345678):
            m = self.build(seed)
            new = (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
            u = (new >> 16) / 65536.0
            q = [g(m.w[BODY + 0x1C + 4 * k]) for k in range(4)]
            self.assertEqual(q[0], 0.0)
            self.assertEqual(q[1], 0.0)
            self.assertAlmostEqual(q[3] / q[2], u, places=5)
            self.assertAlmostEqual(sum(c * c for c in q), 1.0, places=5)

    def test_matrix_is_a_rotation_about_z(self):
        m = self.build(99)
        r = [g(m.w[BODY + 0x44 + 4 * k]) for k in range(9)]
        self.assertAlmostEqual(r[8], 1.0, places=5)
        self.assertAlmostEqual(r[0] * r[0] + r[1] * r[1], 1.0, places=5)
        self.assertAlmostEqual(r[0], r[4], places=5)

    def test_update_derived_matches_integrate_tail_for_identity(self):
        m = Mem()
        for k, v in enumerate((0, 0, 0, C.ONE)):
            m.w[BODY + 0x1C + 4 * k] = v
        for off, v in ((4, 2.0), (8, 3.0), (0xC, 5.0)):
            m.w[BODY + off] = f(v)
        m.w[BODY + 0x38] = f(1.0)
        m.rb_update_derived(BODY)
        iw = [g(m.w[BODY + 0x68 + 4 * k]) for k in range(9)]
        self.assertEqual([iw[0], iw[4], iw[8]], [2.0, 3.0, 5.0])
        self.assertEqual([g(m.w[BODY + 0x8C + 4 * k]) for k in range(3)], [2.0, 0.0, 0.0])

    def test_rigid_call_dispatch(self):
        m = Mem()
        self.assertEqual(m.rigid_call('obj_delete', (1,)), (False, None))
        self.assertEqual(sorted(RB.NAMES.values()), [0x164330, 0x166550, 0x167A58, 0x1682F0])


if __name__ == '__main__':
    unittest.main()
