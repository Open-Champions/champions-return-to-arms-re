#!/usr/bin/env python3
"""Synthetic checks for tools/ref_leveldraw.py. No executable and no disc file.

  python3 -m unittest discover -s tools -p 'test_ref_leveldraw.py'
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_leveldraw as R                      # noqa: E402


class TestChunkState(unittest.TestCase):
    def test_default_chunk_darkens_and_depth_tests(self):
        gs = R.chunk_gs(0)
        self.assertEqual(gs['alpha1'], 0x02)
        self.assertIsNone(gs['alpha2'])
        self.assertEqual(gs['test'], 0x587F4)
        self.assertEqual(gs['layer'], 0)
        self.assertEqual(R.chunk_light(0), ('dynamic', None, 0))

    def test_flag_bits_that_were_executed(self):
        self.assertEqual(R.chunk_gs(0x10)['alpha2'], 0x2A)
        self.assertEqual(R.chunk_gs(0x10)['alpha1'], 0x09)
        self.assertEqual(R.chunk_gs(0x200)['layer'], 4)
        self.assertEqual(R.chunk_gs(0x200)['alpha1'], 0x01)
        self.assertEqual(R.chunk_gs(0x400)['test'], 0x582F5)
        self.assertEqual(R.chunk_gs(0x400)['layer'], 0)
        self.assertEqual(R.chunk_gs(0x600)['layer'], 4)
        self.assertEqual(R.chunk_gs(0x600)['test'], 0x582F5)
        self.assertEqual(R.chunk_gs(0x10000)['alpha1'], 0x48)
        self.assertEqual(R.chunk_gs(0x410)['test'], 0x582F5)
        self.assertEqual(R.chunk_gs(0x410)['alpha2'], 0x2A)

    def test_light_precedence_and_the_bit_0x100_clears(self):
        self.assertEqual(R.chunk_light(0x100), ('flash', -230, 0))
        self.assertEqual(R.chunk_light(0x110), ('flash', -230, 0x10))
        self.assertEqual(R.chunk_light(0x2000), ('full', 230, 0x2000))
        self.assertEqual(R.chunk_light(0x2200), ('full', 230, 0x2200))
        self.assertEqual(R.chunk_light(0x2100), ('flash', -230, 0x2000))
        self.assertEqual(R.chunk_light(0x200), ('flat', 0, 0x200))

    def test_other_chunk_kinds_are_refused(self):
        for bit in (0x80, 0x800, 0x4000, 0x8000):
            with self.assertRaises(ValueError):
                R.chunk_gs(bit)


class TestEnvRows(unittest.TestCase):
    def test_axis_xy_skips_each_axis_z(self):
        camera = [float(i + 1) for i in range(9)]
        self.assertEqual(R.axis_xy(camera), (1.0, 2.0, 4.0, 5.0, 7.0, 8.0))

    def test_rows_scale_by_six_and_bias_192(self):
        rows = R.env_rows((1, 2, 4, 5, 7, 8), frame=0, level_options=0)
        self.assertEqual(rows[0], (6.0, 12.0, 24.0, 30.0))
        self.assertEqual(rows[1], (42.0, 48.0, 192.0, 192.0))

    def test_quarter_turns(self):
        axis = (1, 2, 4, 5, 7, 8)
        expect = {
            0: (6, 12, 24, 30),
            1: (-6, -12, 24, 30),
            2: (6, 12, -24, -30),
            3: (-6, -12, -24, -30),
            4: (24, 30, 6, 12),
            5: (-24, -30, 6, 12),
            6: (24, 30, -6, -12),
            7: (-24, -30, -6, -12),
        }
        for code, four in expect.items():
            row4, row5 = R.env_rows(axis, 0, 0, quarter=code)
            self.assertEqual(row4, tuple(float(v) for v in four))
            self.assertEqual(row5[:2], (42.0, 48.0))

    def test_scroll_is_frame_masked_times_a_quarter(self):
        axis = (0, 0, 0, 0, 0, 0)
        self.assertEqual(R.env_rows(axis, 100, 0)[1][2], 192.0)
        self.assertEqual(R.env_rows(axis, 100, 4)[1][2], 217.0)
        self.assertEqual(R.env_rows(axis, 0x400, 4)[1][2], 192.0)
        self.assertEqual(R.env_rows(axis, 0x3FF, 4)[1][2], 447.75)
        self.assertEqual(R.env_rows(axis, 50, 5)[1][2], 204.5)

    def test_uv_formula_uses_normal_over_16(self):
        rows = R.env_rows((1, 0, 0, 0, 0, 0), 0, 0)
        # n' = (1, 0, 0); u = 192 + 1*6 + 0.07*10
        self.assertAlmostEqual(R.env_uv((16, 0, 0), rows, 10, -20)[0], 192 + 6 + 0.7)
        self.assertAlmostEqual(R.env_uv((16, 0, 0), rows, 10, -20)[1], 192 - 1.4)


class TestAutomap(unittest.TestCase):
    def test_bit_fields(self):
        # column 31, orientation 0, row 15, explored 0
        fields = R.automap_fields(0x0F1F)
        self.assertEqual(fields['col'], 31)
        self.assertEqual(fields['row'], 15)
        self.assertEqual(fields['orient'], 0)
        self.assertEqual(fields['explored'], 0)
        self.assertEqual(fields['alpha'], 0x0F)
        fields = R.automap_fields(0xF562)
        self.assertEqual((fields['col'], fields['orient'], fields['row'], fields['explored']),
                         (2, 3, 5, 15))
        self.assertEqual(fields['alpha'], 0xF5)

    def test_orient_0_rectangle(self):
        # one cell's code on every corner: the quad shows that cell
        code = 0xF000 | (2 << 8) | 1          # col 1, orient 0, row 2, explored 15
        quad = R.automap_quad(code, code, code, code)
        self.assertEqual([p[:2] for p in quad],
                         [(160, 320), (160, 478), (318, 320), (318, 478)])
        self.assertTrue(all(p[2] == 0xF2 for p in quad))

    def test_tile_comes_from_the_bottom_right_cell(self):
        plain = 0xF000                          # col 0, row 0, explored 15
        marked = 0xF000 | (5 << 5) | 1 | (2 << 8)
        quad = R.automap_quad(plain, plain, plain, marked)
        # orientation 5 of column 1, row 2
        self.assertEqual([p[:2] for p in quad],
                         [(160, 478), (318, 478), (160, 320), (318, 320)])
        self.assertEqual([p[2] for p in quad], [0xF0, 0xF0, 0xF0, 0xF2])

    def test_all_eight_orientations_are_distinct(self):
        seen = set()
        for orient in range(8):
            code = 0xF000 | (orient << 5) | 1 | (2 << 8)
            seen.add(tuple(p[:2] for p in R.automap_quad(code, code, code, code)))
        self.assertEqual(len(seen), 8)


class TestOrder(unittest.TestCase):
    def test_texture_groups_and_the_front(self):
        items = [
            (0, 'A', 0, 'a0'),
            (0, 'B', 0, 'b'),
            (0, 'A', 0, 'a1'),
            (0, 'C', 1, 'front'),
            (4, 'A', 0, 'later'),
            (0, None, 0, 'notex'),
        ]
        order = R.sorted_draw_order(items)
        self.assertEqual(order[0], ['notex', 'front', 'b', 'a0', 'a1'])
        self.assertEqual(order[4], ['later'])
        self.assertEqual(order[1], [])
