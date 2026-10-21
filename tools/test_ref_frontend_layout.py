#!/usr/bin/env python3
"""Unit tests of the front-end layout reference tables; no game file needed.

Whether the tables match the game is the business of tools/difftest_frontend_layout.py
and tools/difftest_frontend_screens.py.

  python3 -m unittest discover -s tools -p 'test_ref_frontend_layout.py'
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_frontend_layout as L                 # noqa: E402
import ref_frontend_screens as S                # noqa: E402
import scan_lookup_sites as scan                # noqa: E402

KINDS = {"text_begin", "centered", "wide", "wrapped", "ascii", "ascii_centered",
         "wrapped_centered", "sprite", "frame", "rect", "clip", "colour", "key",
         "msgbox", "lump", "class_name", "pad_glyph", "name_run", "name_draw",
         "fade_step"}


class ListGeometry(unittest.TestCase):
    def test_first_row_and_spacing(self):
        anchors, frame = L.list_geometry(4)
        self.assertEqual(anchors, [(320, 259), (320, 281), (320, 303), (320, 325)])
        self.assertEqual(frame, (293, 252, 54, 114, 7, 0x80808080))

    def test_value_rows_shift_left(self):
        anchors, _ = L.list_geometry(13, (0, 1, 2), origin=(320, 238))
        self.assertEqual(anchors[0], (297, 89))
        self.assertEqual(anchors[3], (320, 155))

    def test_selected_row_height_follows_parity(self):
        odd_y = L.list_frame_calls(4)[0]    # first row y = 259
        even_y = L.list_frame_calls(3)[0]   # first row y = 270
        self.assertEqual((even_y[3], odd_y[3]), (32, 33))


class ThemeGate(unittest.TestCase):
    def test_gate_and_negative_values(self):
        self.assertTrue(L.first_theme_queues(0x3D4CCCCC))
        self.assertFalse(L.first_theme_queues(0x3D4CCCCB))
        self.assertFalse(L.first_theme_queues(0))
        self.assertFalse(L.first_theme_queues(0xBF800000))   # -1.0
        with self.assertRaises(ValueError):
            L.first_theme_queues(0x7FC00000)                 # NaN


class MenuTables(unittest.TestCase):
    def test_main_accept_rows_cover_four_distinct_outcomes(self):
        self.assertEqual(sorted(L.MAIN_MENU_ACCEPT), [0, 1, 2, 3])
        self.assertEqual([v[0] for v in L.MAIN_MENU_ACCEPT.values()], [1, 0, 11, 15])

    def test_fonts_are_known_names(self):
        for uses in L.FONT_USES.values():
            for _site, font, layer, _colour in uses:
                self.assertIn(font, ("medium", "small"))
                self.assertIn(layer, (6, 7))


class ScreenTables(unittest.TestCase):
    def test_state_counts_match_jump_tables(self):
        self.assertEqual(sorted(S.PLAYERSEL_PHASES), list(range(16)))
        self.assertEqual(sorted(S.SLOTLIST_STATES), list(range(16)))
        self.assertEqual(sorted(S.BROWSER_STATES), list(range(35)))
        self.assertEqual(sorted(S.IMPORT_STATES), list(range(24)))

    def test_records_hold_only_numbers_and_tokens(self):
        for table in (S.PLAYERSEL_PHASES, S.SLOTLIST_STATES, S.BROWSER_STATES,
                      S.IMPORT_STATES):
            for records in table.values():
                for site, kind, *rest in records:
                    self.assertIn(kind, KINDS)
                    self.assertTrue(0x100000 <= site < 0x400000)
                    for value in rest:
                        self.assertTrue(isinstance(value, int) or value in ("medium", "small"))

    def test_lookup_sites_are_ordered_and_in_range(self):
        for sites in S.LOOKUP_SITES.values():
            addresses = [site for site, _name, _strings in sites]
            self.assertEqual(addresses, sorted(addresses))


class DecodeConstant(unittest.TestCase):
    def test_lui_addiu_pair_with_negative_offset(self):
        lui = (0x0F << 26) | (5 << 16) | 0x0054
        addiu = (0x09 << 26) | (5 << 21) | (5 << 16) | (-0x3208 & 0xFFFF)
        self.assertEqual(scan.decode_constant([lui, addiu], 2, 5), 0x540000 - 0x3208)

    def test_unrelated_register_is_not_decoded(self):
        lui = (0x0F << 26) | (4 << 16) | 0x0054
        self.assertIsNone(scan.decode_constant([lui], 1, 5))


if __name__ == "__main__":
    unittest.main()
