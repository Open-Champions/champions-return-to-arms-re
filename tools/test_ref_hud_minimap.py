#!/usr/bin/env python3
"""Synthetic tests for tools/ref_hud_minimap.py (no ELF needed)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_core as F
import ref_hud_minimap as R


def state(**kw):
    s = {'world_tex': 0x100000, 'dl_cursor': 0x1000000, 'dl_base': 0x1000000,
         'dl_capacity': 0x40000, 'yaw': 0, 'centre': (F.f32(1200.0), F.f32(1200.0)),
         'offx': 0, 'offy': 0, 'zoom': F.ONE, 'half_w': F.f32(30.0), 'half_h': F.f32(30.0),
         'blip_size': F.f32(6.0), 'icon_size': F.f32(16.0), 'origin': (0, 0),
         'width': 40, 'height': 40, 'grid': bytes(216 * 216 * 2), 'blips': [], 'icons': [],
         'full_scissor': (0, 447), 'zbuf': 0, 'timer': (10, 25), 'counters': (100, 3)}
    s.update(kw)
    return s


def packets(out):
    return [c for c in out['calls'] if c[0] == 'gfx_addSortedPacket']


class Gate(unittest.TestCase):
    def test_needs_texture_space_and_width(self):
        self.assertEqual(R.gate(0, 0, 0, 0x40000, F.f32(320.0)), 0)
        self.assertEqual(R.gate(1, 8 * 100, 0, 12099, F.f32(320.0)), 0)
        self.assertEqual(R.gate(1, 8 * 100, 0, 12100, F.f32(320.0)), 1)
        self.assertEqual(R.gate(1, 0, 0, 0x40000, F.f32(1.99)), 0)
        self.assertEqual(R.gate(1, 0, 0, 0x40000, F.f32(2.0)), 1)


class Cells(unittest.TestCase):
    def test_world_to_cell_is_one_per_120_units(self):
        u, v = R.world_to_cell(F.f32(1200.0), F.f32(-240.0), (F.f32(5.0), 0))
        self.assertAlmostEqual(F.to_float(u), 15.0, places=4)
        self.assertAlmostEqual(F.to_float(v), -2.0, places=4)

    def test_floor_ceil(self):
        self.assertEqual(R.r5900_floor(F.f32(-0.5)), -1)
        self.assertEqual(R.r5900_ceil(F.f32(2.25)), 3)
        self.assertEqual(R.r5900_floor(0x80000000), 0)


class Draw(unittest.TestCase):
    def test_hidden_mode_draws_nothing(self):
        out = R.draw(state(half_w=0, half_h=0))
        self.assertFalse(out['drawn'])
        self.assertEqual(out['calls'], [])
        self.assertEqual(out['counters'], (100, 3))

    def test_strips_and_counters(self):
        out = R.draw(state())
        self.assertTrue(out['drawn'])
        # radius = 30 * 1.333 / 1 * 0.1333 = 5.33 cells around cell (10, 10)
        rng = [c for c in out['calls'] if c[0] == 'ranges'][0]
        self.assertEqual(rng[1:], (3, 3, 16, 16))
        pk = packets(out)
        self.assertEqual(len(pk), 2)               # blip packet + one 13-column strip
        self.assertEqual(pk[0][2:], (5, 0, 0, 0))
        self.assertEqual(pk[1][2:], (5, 0x100000, 0, 0))
        self.assertEqual(len([c for c in out['calls'] if c[0] == 'memcpy']), 13)
        self.assertEqual(out['counters'], (115, 4))

    def test_no_blip_packet_at_low_zoom(self):
        out = R.draw(state(zoom=F.f32(0.125), half_w=F.f32(4.0)))
        self.assertTrue(all(c[3] != 0 for c in packets(out)))

    def test_blip_triangle_points_up_at_yaw_zero(self):
        blip = {'x': F.f32(1200.0), 'y': F.f32(1200.0), 'angle': 0x3FFF, 'r': 1, 'g': 2,
                'b': 3, 'scale': F.ONE}
        out = R.draw(state(blips=[blip]))
        b = out['bytes']
        start = 0x1000000 + 0x80

        def q(a):
            return sum(b[a + i] << (8 * i) for i in range(8))
        self.assertEqual(q(start), R.PRIM_BLIP_SHADOW)
        self.assertEqual(q(start + 0x10), R.SHADOW_RGBA)
        colour = q(start + 0x60)
        self.assertEqual(colour, 0x80030201)
        # first vertex of the coloured triangle: (0, -6) from the blip, 12.4 with x doubled
        xyz = q(start + 0x70)
        x, y = xyz & 0xFFFF, (xyz >> 16) & 0xFFFF
        self.assertEqual((x - 32768) / 32.0, 0.0)
        self.assertAlmostEqual((y - 32768) / 16.0, -6.0, delta=0.1)

    def test_icon_alpha_from_explored_nibble(self):
        grid = bytearray(216 * 216 * 2)
        grid[(10 * 216 + 10) * 2 + 1] = 0x5F
        icon = {'x': F.f32(1210.0), 'y': F.f32(1210.0), 'tex': 0, 'tex_w': 0, 'tex_h': 0,
                'rotate': 0, 'var': 0, 'var_ok': 1, 'script': 0, 'script_ok': 1}
        out = R.draw(state(grid=bytes(grid), icons=[icon]))
        b = out['bytes']
        pk = packets(out)
        p = pk[1][1]
        rgba = sum(b[p + 0x90 + i] << (8 * i) for i in range(4))
        self.assertEqual(rgba, 0x50808080)

    def test_icon_gated_by_variable(self):
        icon = {'x': 0, 'y': 0, 'tex': 0, 'tex_w': 0, 'tex_h': 0, 'rotate': 0,
                'var': 0x500, 'var_ok': 0, 'script': 0x600, 'script_ok': 1}
        out = R.draw(state(icons=[icon]))
        names = [c[0] for c in out['calls']]
        self.assertIn('vars_get', names)
        self.assertNotIn('script_runByName', names)

    def test_orientation_table(self):
        out = R.draw(state())
        p = packets(out)[1][1]
        b = out['bytes']
        words = []
        # constant block: tag qword at p+0xb0, UNPACK at +0xb8, 7 qwords, then 8 orders
        base = p + 0xB0 + 0x18 + 4 + 7 * 16
        for k in range(8):
            words.append(tuple(sum(b[base + 16 * k + 4 * j + i] << (8 * i) for i in range(4))
                               for j in range(4)))
        self.assertEqual(words[0], (0, 3, 6, 9))
        self.assertEqual(words[1], (6, 9, 0, 3))
        self.assertEqual(sorted(set(words)), sorted(words))


if __name__ == '__main__':
    unittest.main()
