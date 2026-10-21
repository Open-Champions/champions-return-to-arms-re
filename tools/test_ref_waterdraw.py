#!/usr/bin/env python3
"""Synthetic checks for tools/ref_waterdraw.py. No executable and no disc file.

  python3 -m unittest discover -s tools -p 'test_ref_waterdraw.py'
"""
import os
import struct
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_waterdraw as R                      # noqa: E402


def _raw(value):
    return struct.unpack('<I', struct.pack('<f', float(value)))[0]


def _blank():
    return [[0] * 32 for _ in range(33)], [[0] * 32 for _ in range(32)], [0] * 32


class TestAppearance(unittest.TestCase):
    def test_two_constant_sets(self):
        ordinary = R.gs_state(0)
        other = R.gs_state(1)
        self.assertEqual(ordinary['alpha_low'], 0x64)
        self.assertEqual(ordinary['alpha_high'], 102)
        self.assertEqual(ordinary['colour'], 0x006D6B5F)
        self.assertEqual(R.colour_channels(ordinary['colour']), (95, 107, 109, 0))
        self.assertEqual(ordinary['scale'], 0x3B999999)
        self.assertEqual(other['alpha_low'], 0x64)
        self.assertEqual(other['alpha_high'], 98)
        self.assertEqual(other['colour'], 0x00808080)
        self.assertEqual(other['scale'], 0x3CC00000)
        self.assertEqual(ordinary['test'], 0x71001)
        self.assertEqual(ordinary['tex1'], 0x61)
        self.assertEqual(ordinary['prim'], 0x15C)
        self.assertEqual(ordinary['layer'], 3)

    def test_negative_fix_is_additive(self):
        self.assertEqual(R.alpha_words(-100), (0x68, 100))
        self.assertEqual(R.alpha_words(0), (0x64, 0))

    def test_width_and_origin_use_floor_of_half(self):
        self.assertEqual(R.floor_half(0.4), 0.0)
        self.assertEqual(R.floor_half(-1.2), -1.0)
        self.assertEqual(R.floor_half(120.5), 121.0)
        self.assertEqual(R.floor_half(10.6), 11.0)
        self.assertEqual(R.tile_step_bits(0.0, 120.0), 0x407FFFFF)
        self.assertEqual(R.tile_step_bits(0.4, 100.2), 0x40555554)
        self.assertEqual(R.origin(0.4, -1.2, 8), (0.0, -1.0, 2.0))

    def test_uploaded_matrix_puts_height_on_the_third_view_row(self):
        view = [(2, 0, 0, 0), (0, 3, 0, 0), (0, 0, 4, 0), (5, 6, 7, 8)]
        out0, out1, out2, out3 = R.upload_matrix(view, (0.0, 0.0, 40.0), R.SET0_SCALE)
        self.assertEqual(out0[2], 0x3C999999)
        self.assertEqual(out1[1], _raw(3))
        self.assertEqual(out2[0], _raw(2))
        self.assertEqual(tuple(round(struct.unpack('<f', struct.pack('<I', b))[0], 5) for b in out3),
                         (5.0, 6.0, 167.0, 8.0))


class TestGrid(unittest.TestCase):
    def test_a_spike_is_damped_and_added_one_row_later(self):
        heights, disturb, gap = _blank()
        disturb[4][5] = 1000
        field, velocity, spare = R.step_grid(heights, disturb, gap, bytes([0xFF]) * 128)
        self.assertEqual(field[5][5], 993)
        self.assertEqual(velocity[4][5], 993)
        self.assertEqual(field[4][5], 0)
        self.assertEqual(disturb[31], velocity[31])

    def test_row_zero_is_replaced_and_a_clear_mask_bit_freezes(self):
        heights, disturb, gap = _blank()
        heights[0][0] = 500
        heights[10][10] = 100
        field, velocity, spare = R.step_grid(heights, disturb, gap, bytes(128))
        self.assertEqual(field[0][0], 0)
        self.assertEqual(field[10][10], 100)
        self.assertTrue(all(v == 0 for row in velocity for v in row))

    def test_flat_water_does_not_move(self):
        heights = [[100] * 32 for _ in range(33)]
        disturb = [[0] * 32 for _ in range(32)]
        field, velocity, spare = R.step_grid(heights, disturb, [0] * 32, bytes([0xFF]) * 128)
        self.assertEqual(field[10][10], 100)
        self.assertEqual(velocity[10][10], 0)

    def test_mask_bit_15_is_the_first_row_of_the_bank(self):
        self.assertTrue(R.mask_allows(struct.pack('<H', 0x8000) + bytes(126), 0, 0))
        self.assertFalse(R.mask_allows(struct.pack('<H', 0x8000) + bytes(126), 0, 1))
        self.assertTrue(R.mask_allows(bytes(64) + struct.pack('<H', 1) + bytes(62), 0, 31))

    def test_column_and_row_seams(self):
        this_h = [[row * 40 + col for col in range(32)] for row in range(33)]
        other_h = [[1000 + row * 40 + col for col in range(32)] for row in range(33)]
        this_d = [[7] * 32 for _ in range(32)]
        other_d = [[3000 + row * 40 + col for col in range(32)] for row in range(32)]
        h, d, oh, od = R.seam_columns(this_h, this_d, other_h, other_d)
        self.assertEqual(h[4][0], other_h[4][30])
        self.assertEqual(oh[4][31], this_h[4][1])
        self.assertEqual(d[4][0], other_d[4][30])
        self.assertEqual(od[4][31], this_d[4][1])
        h, d, oh, od = R.seam_rows(this_h, this_d, other_h, other_d)
        self.assertEqual(h[1], other_h[31])
        self.assertEqual(oh[32], this_h[2])
        self.assertEqual(d[0], other_d[30])
        self.assertEqual(od[31], this_d[1])

    def test_a_block_lasts_199_frames(self):
        self.assertFalse(R.block_expired(199, 0))
        self.assertTrue(R.block_expired(200, 0))
        self.assertFalse(R.block_expired(10, 11))


class TestVertices(unittest.TestCase):
    def _ident(self):
        return [tuple(_raw(v) for v in row) for row in (
            (0, 1, 0, 0), (0, 0, 1, 0), (1, 0, 0, 0), (0, 0, 0, 1))]

    def test_flat_sample_and_a_slope(self):
        rows = [[0] * 32 for _ in range(3)]
        rows[2][2] = 160
        strips = R.project_strips(rows, self._ident(), _raw(4))
        self.assertEqual(len(strips), 1)
        self.assertEqual(len(strips[0]), 62)
        current = strips[0][0]
        self.assertEqual(current[:4], (32896, 32768, 512, 512))
        self.assertEqual(current[4], 0)
        sloped = strips[0][2]
        self.assertEqual(sloped[2], 504)

    def test_clip_sticks_for_the_rest_of_the_strip(self):
        matrix = [tuple(_raw(v) for v in row) for row in (
            (0, 0, 0, 0), (0, 0, 0, 0), (0, 100, 0, 0), (0, -2000, 0, 1))]
        strips = R.project_strips([[0] * 32 for _ in range(4)], matrix, _raw(4), clip=1)
        self.assertEqual([v[4] for v in strips[1][:4]], [0, 1, 1, 1])
        held = [tuple(_raw(v) for v in row) for row in (
            (0, 0, 0, 0), (0, 250, 0, 0), (0, 0, 0, 0), (0, 0, 0, 1))]
        edge = R.project_strips([[0] * 32 for _ in range(3)], held, _raw(4), clip=1)
        self.assertEqual(edge[0][2][4], 0)

    def test_splash_gate(self):
        seed, splash = R.splash_seed(0)
        self.assertEqual(seed, R.LCG_ADD)
        self.assertIs(splash, (seed >> 16) % 300 == 0)

    def test_splash_point_shares_one_interval_and_keeps_minimum_z(self):
        bounds = tuple(_raw(v) for v in (0.4, -1.2, 3.5, 120.6, 10.0, 40.0))
        self.assertTrue(R.splash_seed(324)[1])
        seed, point = R.splash_point(324, bounds)
        self.assertEqual(seed, 0xAA3E5B7D)
        self.assertEqual(point, (0x42A10BBD, 0x40C88098, 0x40600000))
        self.assertEqual(R.second_particle_z(0x42F70000, seed), 0x4348B360)
        missed, quiet = R.splash_point(325, bounds)
        self.assertIsNone(quiet)
        self.assertEqual(missed, R.splash_seed(325)[0])


class TestDisturb(unittest.TestCase):
    def _splash(self, grid, strength=1500.0, radius=6.0, origin=(0, 0),
                span=(-60.0, 60.0), pos=(0.0, 0.0)):
        return R.disturb_cells(
            grid, _raw(strength), _raw(radius), origin,
            tuple(_raw(v) for v in span), tuple(_raw(v) for v in pos))

    def test_a_centre_splash_is_a_three_by_three(self):
        out = self._splash([[0] * 32 for _ in range(32)])
        self.assertEqual([row[15:18] for row in out[15:18]], [
            [328, 914, 328],
            [914, 1500, 914],
            [328, 914, 328],
        ])
        self.assertEqual(sum(sum(row) for row in out), 328 * 4 + 914 * 4 + 1500)
        shifted = self._splash([[0] * 32 for _ in range(32)], pos=(30.0, 0.0))
        rows = [r for r in range(32) if any(shifted[r])]
        cols = [c for c in range(32) if any(shifted[r][c] for r in range(32))]
        self.assertEqual((min(rows), max(rows), min(cols), max(cols)), (23, 25, 15, 17))

    def test_only_a_sum_above_32767_is_clamped(self):
        grid = [[-100] * 32 for _ in range(32)]
        grid[16][16] = 32000
        out = self._splash(grid)
        self.assertEqual(out[16][16], 32767)
        self.assertGreater(out[16][15], -100)
        self.assertEqual(out[0][0], -100)
        negative = self._splash([[0] * 32 for _ in range(32)], strength=-100.0)
        self.assertEqual(negative[16][16], -100)


class TestLevel(unittest.TestCase):
    def test_colour_packs_three_bytes_and_wavyness_scales(self):
        self.assertEqual(R.colour_word(10, 20, 30), 0x001E140A)
        self.assertEqual(R.wavyness_scale(0x3F800000), R.SET1_SCALE)
        half = R.wavyness_scale(0x3F000000)
        self.assertEqual(half, R._cpu_mul(0x3F000000, R.SET1_SCALE))
        self.assertLess(R.ee_emu.fp_cmp(half, R.SET1_SCALE), 0)


class TestClaim(unittest.TestCase):
    def test_one_edge_is_truncated_against_one(self):
        ten = R._cpu_mul(R.ee_emu.fp_from_int(10, 'ps2'), R.EDGE_WEIGHT)
        self.assertEqual(ten, 0x3F7FFFFF)
        self.assertLess(R.ee_emu.fp_cmp(ten, R.CLAIM_ONE), 0)
        neighbour = [[0] * 32 for _ in range(33)]
        neighbour[1][31] = 1001
        heights, disturb = R.claim_grid((neighbour, None, None, None))
        self.assertEqual(heights[0], [0] * 32)
        self.assertEqual(heights[1][:10], [1000, 900, 800, 700, 600, 500, 400, 300, 200, 100])
        self.assertEqual(heights[1][10:], [0] * 22)
        self.assertEqual(heights[2], [0] * 32)
        self.assertEqual(disturb, [[0] * 32 for _ in range(32)])

    def test_a_negative_sample_stays_signed(self):
        neighbour = [[0] * 32 for _ in range(33)]
        neighbour[1][31] = -30000
        heights, _disturb = R.claim_grid((neighbour, None, None, None))
        self.assertEqual(heights[1][0], -29999)
        self.assertEqual(heights[1][9], -2999)

    def test_two_edges_normalise_only_once_the_sum_reaches_one(self):
        left = [[0] * 32 for _ in range(33)]
        far = [[0] * 32 for _ in range(33)]
        left[1][31] = 30000
        left[10][31] = 30000
        far[32][9] = 30000
        both, _disturb = R.claim_grid((left, None, far, None))
        left_only, _disturb = R.claim_grid((left, None, None, None))
        self.assertEqual(left_only[1][0], 29999)
        self.assertEqual(both[1][0], 14999)
        self.assertEqual(both[10][9], 5999)


if __name__ == '__main__':
    unittest.main()
