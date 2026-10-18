"""Invented font and strings only; no original game data in fixtures."""
import struct
import unittest

import ref_ui_layout as L
import ref_ui_text as T


def font_fixture():
    """Glyph 0 = space-like (advance 3); A=1 (7), B=2 (8), dash=3 (5), 4..0x5f
    filler with wide codes 0x1000+i; '{' -> 0x5b (icon range). Kerning: A then B -3."""
    count = 0x60
    go = 0x214
    ko = go + count * 16
    to = ko + 2 * 6
    data = bytearray(to + 0x40)
    struct.pack_into('<HHIIII', data, 0, count, 8, 2, go, ko, to)
    charmap = [-1] * 256
    charmap[0x20], charmap[ord('A')], charmap[ord('B')], charmap[45], charmap[0x7b] = 0, 1, 2, 3, 0x5b
    struct.pack_into('<256h', data, 0x14, *charmap)
    glyphs = [(0x20, 0, 0, 0, 0, 0, 3, -1), (65, 0, 6, 0, 10, 2, 7, -1), (66, 6, 13, 0, 12, 0, 8, 0),
              (45, 13, 18, 0, 4, 5, 5, -1)]
    glyphs += [(0x1000 + i, 0, 9, 16, 26, 1, 9, -1) for i in range(4, count)]
    glyphs[0x5b] = (0x7b, 20, 30, 0, 10, 0, 10, -1)
    for i, g in enumerate(glyphs):
        struct.pack_into('<H7h', data, go + 16 * i, *g)
    struct.pack_into('<HHhHHh', data, ko, 1, 2, -3, 0xffff, 0xffff, 0)
    return L.parse_font(bytes(data))


def w(text):
    return [ord(c) for c in text]


class Measure(unittest.TestCase):
    def setUp(self):
        self.f = font_fixture()

    def test_kerning_scale_depends_on_interlace_when_measuring(self):
        self.assertEqual(T.measure_wide(self.f, w('AB'), True), 12)
        self.assertEqual(T.measure_wide(self.f, w('AB'), False), 13)
        self.assertEqual(T.measure_wide(self.f, w('AB'), True, 1), 7)
        self.assertEqual(T.measure_wide(self.f, w('AB'), True, 0), 0)

    def test_newline_is_invisible_to_measure_and_keeps_previous(self):
        self.assertEqual(T.measure_wide(self.f, w('A\nB')), 12)

    def test_fallbacks(self):
        self.assertEqual(T.glyph_index_wide(self.f, ord('Z')), 3)        # map 45 glyph
        self.assertEqual(T.glyph_index_wide(self.f, 0x1004), 4)
        self.assertEqual(T.glyph_index_wide(self.f, 0x2222), 0)
        self.assertEqual(T.measure_wide(self.f, [ord('Z'), 0x2222]), 5 + 3)
        self.assertEqual(self.f.width_ascii(b'Z'), 3)                   # ASCII path differs

    def test_centring_wrappers_use_their_own_measure(self):
        self.assertEqual(T.centered_x_wide(self.f, 100, w('ZZ')), 95)
        self.assertEqual(T.centered_x_ascii(self.f, 100, b'ZZ'), 97)
        self.assertEqual(T.centered_x_wide(self.f, 100, w('A')), 97)   # arithmetic >> 1


class Glyphs(unittest.TestCase):
    def setUp(self):
        self.f = font_fixture()

    def test_half_pixel_kerning_offsets_and_sources(self):
        draws, end = T.glyph_run(self.f, 10, 40, w('AB'))
        self.assertEqual([(g.index, g.x_half, g.y, g.source) for g in draws],
                         [(1, 20, 42, (0, 0, 6, 10)), (2, 31, 40, (6, 0, 7, 12))])
        self.assertEqual(end, 47)

    def test_newline_breaks_kerning_in_draw_and_missing_advances(self):
        draws, end = T.glyph_run(self.f, 0, 0, w('A\nB') + [0x2222])
        self.assertEqual([g.x_half for g in draws], [0, 14])
        self.assertEqual(end, 14 + 16 + 6)

    def test_vertical_reject_and_count(self):
        self.assertEqual(T.glyph_run(self.f, 0, 801, w('A'))[0], [])
        self.assertEqual(len(T.glyph_run(self.f, 0, -100, w('A'))[0]), 1)
        self.assertEqual(T.glyph_run(self.f, 0, 0, w('AB'), 0)[0], [])
        self.assertEqual(len(T.glyph_run(self.f, 0, 0, w('AB\0A'))[0]), 2)

    def test_icon_tint_and_alpha_restore(self):
        state = T.TextState(0x40ffcc10, icon_alpha=0x1234, stored_alpha=-1)
        draws, _ = T.glyph_run(self.f, 0, 0, w('{A{'), state=state)
        self.assertEqual([g.tint for g in draws], [0x34606060, 0x40ffcc10, 0x40606060])
        self.assertEqual(state.icon_alpha, -1)
        self.assertEqual(T.TextState(0x7f000000).icon_tint(), 0x7f606060)


class Wrap(unittest.TestCase):
    def setUp(self):
        self.f = font_fixture()

    def test_left_wrap_counts_trailing_space(self):
        r = T.draw_wrapped(self.f, 5, 100, w('AB AB AB'), 32, 0, 448, 17)
        self.assertEqual(r.runs, [T.Run(5, 100, 0, 6), T.Run(5, 117, 6, 2)])
        self.assertEqual((r.height, r.shown), (34, 8))

    def test_centred_wrap_includes_trailing_space_in_centre(self):
        r = T.draw_wrapped_centered(self.f, 200, 0, w('AB AB AB'), 32, -1, 448, 21)
        self.assertEqual(r.runs, [T.Run(185, 0, 0, 6), T.Run(194, 21, 6, 2)])
        self.assertEqual((r.height, r.shown), (42, None))

    def test_left_splits_long_words_centred_does_not(self):
        left = T.draw_wrapped(self.f, 0, 0, w('AAAAAA'), 20, -1, 448, 10)
        self.assertEqual([(r.start, r.count) for r in left.runs], [(0, 2), (2, 2), (4, 2)])
        centred = T.draw_wrapped_centered(self.f, 50, 0, w('AAAAAA'), 20, -1, 448, 10)
        self.assertEqual(centred.runs, [T.Run(50, 0, 0, 0), T.Run(29, 10, 0, 6)])
        self.assertEqual(centred.height, 20)

    def test_newline_forces_break_and_stays_in_run(self):
        r = T.draw_wrapped(self.f, 0, 0, w('A\nB'), 100, -1, 448, 10)
        self.assertEqual([(x.start, x.count) for x in r.runs], [(0, 2), (2, 1)])

    def test_budget_and_clip_are_per_line(self):
        r = T.draw_wrapped(self.f, 0, 50, w('AB AB AB'), 32, -1, 448, 10, budget=4)
        self.assertEqual((r.runs, r.shown), ([T.Run(0, 50, 0, 4)], 4))
        r = T.draw_wrapped(self.f, 0, 50, w('AB AB AB'), 32, 50, 448, 10)
        self.assertEqual((r.runs, r.shown, r.height), ([T.Run(0, 60, 6, 2)], 8, 20))

    def test_per_character_language(self):
        r = T.draw_wrapped(self.f, 0, 0, w('ABAB'), 16, -1, 448, 10, language=5)
        self.assertEqual([(x.start, x.count) for x in r.runs], [(0, 2), (2, 2)])

    def test_unbreakable_unit_is_refused(self):
        with self.assertRaises(ValueError):
            T.draw_wrapped(self.f, 0, 0, w('AA'), 5, -1, 448, 10)
        with self.assertRaises(ValueError):
            T.draw_wrapped(self.f, 0, 0, w('A'), 0, -1, 448, 10)


class FitAndClip(unittest.TestCase):
    def test_fit_by_pixels_and_by_characters(self):
        f = font_fixture()
        self.assertEqual(f.width_ascii(b'ABAB'), 24)
        self.assertEqual(T.fit_ascii(f, b'ABAB', 20), b'ABA...')
        self.assertEqual(T.fit_ascii(f, b'ABAB', 24), b'ABAB')
        self.assertEqual(T.fit_ascii(None, b'ABCDEFGH', 6), b'ABC...')
        self.assertEqual(T.fit_ascii(None, b'ABCDEFGH', 8), b'ABCDEFGH')

    def test_text_scissor(self):
        self.assertEqual(T.text_scissor(-5, -5, 700, 500), ((0, 1279, 0, 447), (0, 0, 640, 448)))
        self.assertEqual(T.text_scissor(10, 20, 30, 40), ((20, 59, 20, 40), (10, 20, 30, 41)))


if __name__ == '__main__':
    unittest.main()
