"""Synthetic tests for ref_hud_xp; no game files needed."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_core as F
import ref_hud_xp as X


class XpBar(unittest.TestCase):
    def test_frame_and_name(self):
        self.assertEqual(X.xp_frame(0), 0)
        self.assertEqual(X.xp_frame(44), 0)
        self.assertEqual(X.xp_frame(43), 10)
        self.assertEqual(X.xp_resource(4 * 13), 'bar_green02.tex')
        self.assertEqual(X.xp_frame(-4), -1)          # C remainder keeps the sign

    def test_threshold_addresses(self):
        self.assertEqual(X.xp_threshold_addresses(1), (0x41B558, 0x41B55C))
        self.assertEqual(X.xp_threshold_addresses(80), (0x41B694, 0x41B698))
        self.assertEqual(X.xp_threshold_addresses(0x81), (0x41B554 - 4 * 127, 0x41B558 - 4 * 127))

    def test_not_drawn(self):
        self.assertIsNone(X.xp_layer(12, 0, 0, 0, 0, 100))
        self.assertIsNone(X.xp_layer(12, 0, -3, 0, 0, 100))
        self.assertIsNone(X.xp_layer(12, 0, 1, 0, 0, 100, local=False))

    def test_fill(self):
        layer = X.xp_layer(12, 44, 1, 50, 0, 100)
        self.assertEqual(layer, X.XpLayer('bar_green00.tex', 27, 56, (27, 24, 76, 124), 0x80808080, 6))
        self.assertEqual(X.xp_fill_right(27, 0, 0, 1100), 27)
        self.assertEqual(X.xp_fill_right(27, 1100, 0, 1100), 27 + 99)

    def test_out_of_range_xp_is_not_clamped(self):
        self.assertLess(X.xp_fill_right(27, -100, 0, 100), 27)
        self.assertEqual(X.xp_fill_right(27, 300, 0, 100), 27 + 297)

    def test_equal_thresholds_saturate(self):
        self.assertEqual(X.xp_fill_right(27, 5, 5, 5), 0x7FFFFFFF)     # 0/0 -> +max
        self.assertEqual(X.xp_fill_right(27, 9, 5, 5), 0x7FFFFFFF)
        self.assertEqual(X.xp_fill_right(27, 1, 5, 5), -0x80000000)

    def test_integer_differences_wrap(self):
        self.assertEqual(X.xp_fill_right(27, 0x7FFFFFFF, -1, 0x7FFFFFFF),
                         X.xp_fill_right(27, -0x80000000, 0, -0x80000000))


class Scissor(unittest.TestCase):
    def test_progressive_and_interlaced(self):
        self.assertEqual(X.scissor(27, 24, 126, 124, interlaced=False),
                         27 | 126 << 16 | 24 << 32 | 124 << 48)
        self.assertEqual(X.scissor(27, 24, 126, 124, both_fields=True),
                         54 | 251 << 16 | 24 << 32 | 123 << 48)
        self.assertEqual(X.scissor(27, 24, 126, 125, parity=0), 54 | 251 << 16 | 24 << 32 | 123 << 48)
        self.assertEqual(X.scissor(27, 24, 126, 125, parity=1), 54 | 251 << 16 | 24 << 32 | 125 << 48)

    def test_clamps(self):
        got = X.scissor(-5, -9, 5000, 900, interlaced=False)
        self.assertEqual(got, 0 | 640 << 16 | 0 << 32 | 447 << 48)
        self.assertEqual(X.scissor(0, 10, 10, 20, interlaced=False, letterbox=4),
                         10 << 16 | 6 << 32 | 16 << 48)

    def test_negative_right_spills(self):
        value = X.scissor(27, 24, -1, 124, interlaced=False)
        self.assertEqual(value & 0xFFFF, 27)
        self.assertEqual(value >> 16, 0xFFFFFFFFFFFF)

    def test_visible_columns(self):
        self.assertEqual(X.visible_columns(27, 27 + 99), 99)
        self.assertEqual(X.visible_columns(27, 27), 0)
        self.assertEqual(X.visible_columns(27, 27 + 500), 100)
        self.assertEqual(X.visible_columns(27, 20), 0)


class Shapes(unittest.TestCase):
    def test_bar_green(self):
        shapes = X.bar_green_shapes()
        self.assertEqual(len(shapes), 11)
        self.assertEqual(shapes[0].offset, 0x4D80)
        self.assertEqual(shapes[10].offset, 0x4D80 + 10 * 0x680)
        self.assertEqual({X.source_rect(s) for s in shapes}, {(0, 0, 100, 6)})
        self.assertTrue(all(s.upload[0] >= s.used[0] and s.upload[1] >= s.used[1] for s in shapes))


class NewCharacter(unittest.TestCase):
    FORMULA = (F.f32(10.0), F.f32(1.5), F.f32(2.0), F.f32(3.0), F.f32(1.0), F.f32(5.0))

    def test_after_init(self):
        state = X.after_init()
        self.assertEqual(state['hp'], state['mana'])
        self.assertEqual(F.to_float(state['hp']), 999999936.0)
        self.assertEqual(state['hp_max'], 0)
        self.assertEqual(F.to_float(state['mana_max']), 10.0)

    def test_first_level_current_equals_max(self):
        hp, hp_max, mana, mana_max = X.first_level_current(self.FORMULA, 1, (20, 30, 20, 30))
        self.assertEqual(F.to_float(hp_max), 3.0 + 30.0 - 5.0)
        self.assertEqual(F.to_float(mana_max), (30 - 10.0) * 1.5 + 2.0)
        self.assertEqual((hp, mana), (hp_max, mana_max))

    def test_clamp_only_lowers(self):
        self.assertEqual(X.clamp(F.f32(5.0), F.f32(9.0)), F.f32(5.0))
        self.assertEqual(X.clamp(F.f32(9.0), F.f32(5.0)), F.f32(5.0))

    def test_recalc_reach(self):
        self.assertFalse(X.recalc_clamps(0, 1, False))
        self.assertFalse(X.recalc_clamps(2, 2, True))
        self.assertTrue(X.recalc_clamps(1, 2, True))

    def test_respawn(self):
        self.assertEqual(X.respawn_hp(F.f32(40.0), 1), F.f32(40.0))
        self.assertEqual(X.respawn_hp(F.f32(40.0), 0), F.f32(20.0))


if __name__ == '__main__':
    unittest.main()
