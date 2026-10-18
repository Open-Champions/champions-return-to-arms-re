"""Invented textures and draw records only; no original game data in fixtures."""
import unittest

import ref_ui_composite as C
import ref_ui_layout as R


def solid(w, h, rgba):
    return C.Texture(w, h, bytes(rgba) * (w * h))


def px(fb, x, y, width=C.WIDTH):
    i = 4 * (y * width + x)
    return tuple(fb[i:i + 4])


TEX = {
    'a.tex': solid(4, 2, (200, 100, 50, 0x80)),
    'b.tex': solid(4, 2, (10, 20, 30, 0x80)),
    'half.tex': solid(2, 2, (255, 255, 255, 0x40)),
    'clear.tex': solid(2, 2, (255, 0, 0, 1)),
    'ramp.tex': C.Texture(3, 1, bytes([1, 0, 0, 0x80, 2, 0, 0, 0x80, 3, 0, 0, 0x80])),
}


class Order(unittest.TestCase):
    def test_later_submission_draws_first_within_layer(self):
        fb = C.composite([R.HudLayer('a.tex', 10, 10, None, C.NEUTRAL, 6),
                          R.HudLayer('b.tex', 10, 10, None, C.NEUTRAL, 6)], TEX)
        self.assertEqual(px(fb, 10, 10)[:3], (200, 100, 50))

    def test_higher_layer_draws_over_lower_regardless_of_submission(self):
        fb = C.composite([R.HudLayer('a.tex', 10, 10, None, C.NEUTRAL, 7),
                          R.HudLayer('b.tex', 10, 10, None, C.NEUTRAL, 6)], TEX)
        self.assertEqual(px(fb, 10, 10)[:3], (200, 100, 50))

    def test_text_batch_is_one_packet_with_forward_glyphs(self):
        g1 = C.Blit('a.tex', 0, 0, (0, 0, 4, 2))
        g2 = C.Blit('b.tex', 2, 0, (0, 0, 4, 2))
        order = C.painter_order([C.TextBatch([g1, g2], 6), C.Rect(0, 0, 1, 1, 6, 0x80ffffff)], TEX)
        self.assertIsInstance(order[0], C.Rect)
        self.assertEqual(order[1].glyphs, (g1, g2))
        fb = C.composite([C.TextBatch([g1, g2], 6)], TEX)
        self.assertEqual(px(fb, 2, 0)[:3], (10, 20, 30))   # later glyph over earlier

    def test_bad_layer_rejected(self):
        with self.assertRaises(ValueError):
            C.painter_order([C.Rect(0, 0, 1, 1, 8, 0)], TEX)


class Geometry(unittest.TestCase):
    def test_plain_sprite_adds_one_to_y_clipped_does_not(self):
        plain = C.normalize(R.Draw('a.tex', 5, 7), TEX)[0]
        clipped = C.normalize(R.Draw('a.tex', 5, 7, (0, 0, 640, 447)), TEX)[0]
        self.assertEqual((plain.y, clipped.y), (8, 7))
        self.assertEqual(plain.src, (0, 0, 4, 2))

    def test_clip_is_half_open_and_cuts_without_stretch(self):
        fb = C.composite([R.HudLayer('ramp.tex', 20, 5, (20, 0, 22, 447), C.NEUTRAL, 6)], TEX)
        self.assertEqual([px(fb, x, 5)[0] for x in (20, 21, 22)], [1, 2, 0])

    def test_clip_clamped_to_screen(self):
        self.assertEqual(C._clamp_clip((-5, -1, 1000, 1000)), (0, 0, 640, 447))
        fb = C.composite([R.HudLayer('a.tex', 0, 446, (0, 0, 1000, 1000), C.NEUTRAL, 6)], TEX)
        self.assertEqual(px(fb, 0, 446)[:3], (200, 100, 50))
        self.assertEqual(px(fb, 0, 447)[:3], (0, 0, 0))     # bottom clamp 447, half-open

    def test_offscreen_parts_dropped(self):
        fb = C.composite([C.Blit('a.tex', 638, -1, (0, 0, 4, 2))], TEX)
        self.assertEqual(px(fb, 639, 0)[:3], (200, 100, 50))

    def test_flip(self):
        fb = C.composite([C.Blit('ramp.tex', 0, 0, (0, 0, 3, 1), flip_x=True)], TEX)
        self.assertEqual([px(fb, x, 0)[0] for x in range(3)], [3, 2, 1])

    def test_rect_is_two_corners_half_open(self):
        fb = C.composite([C.Rect(3, 4, 6, 6, 6, 0x80000060)], TEX)
        self.assertEqual(px(fb, 3, 4)[:3], (0x60, 0, 0))
        self.assertEqual(px(fb, 5, 5)[:3], (0x60, 0, 0))
        self.assertEqual(px(fb, 6, 5)[:3], (0, 0, 0))
        self.assertEqual(px(fb, 5, 6)[:3], (0, 0, 0))


class Colour(unittest.TestCase):
    def test_neutral_tint_is_identity_and_tint_modulates(self):
        fb = C.composite([C.Blit('a.tex', 0, 0, (0, 0, 4, 2), tint=0x80404040)], TEX)
        self.assertEqual(px(fb, 0, 0)[:3], (100, 50, 25))

    def test_tint_brightens_and_clamps(self):
        fb = C.composite([C.Blit('a.tex', 0, 0, (0, 0, 4, 2), tint=0x80ffffff)], TEX)
        self.assertEqual(px(fb, 0, 0)[:3], (255, 199, 99))

    def test_half_alpha_blend_and_alpha_written(self):
        fb = C.composite([C.Blit('half.tex', 0, 0, (0, 0, 2, 2))], TEX, background=(100, 0, 200, 0x80))
        self.assertEqual(px(fb, 0, 0), (177, 127, 227, 0x40))

    def test_tint_alpha_fades_sprite(self):
        fb = C.composite([C.Blit('a.tex', 0, 0, (0, 0, 4, 2), tint=0x40808080)], TEX)
        self.assertEqual(px(fb, 0, 0)[:3], (100, 50, 25))

    def test_alpha_test_rejects_alpha_one_or_less(self):
        fb = C.composite([C.Blit('clear.tex', 0, 0, (0, 0, 2, 2))], TEX, background=(9, 9, 9, 0x80))
        self.assertEqual(px(fb, 0, 0), (9, 9, 9, 0x80))

    def test_negative_difference_floors(self):
        fb = C.composite([C.Rect(0, 0, 1, 1, 6, 0x01000000)], TEX, background=(1, 0, 0, 0x80))
        self.assertEqual(px(fb, 0, 0)[0], 0)   # ((0-1)*1 >> 7) + 1 = 0

    def test_hud_bar_composition_frame_behind_bar(self):
        tex = {'bar_red00.tex': solid(100, 8, (255, 0, 0, 0x80)),
               'hud_multi.tex': solid(158, 46, (0, 0, 255, 0x80))}
        layers = R.hud_base_layers(12, 0, 2, 4, 1, 1, local=False)
        fb = C.composite(layers, tex)
        self.assertEqual(px(fb, 27, 46)[:3], (255, 0, 0))     # bar over the frame
        self.assertEqual(px(fb, 27 + 50, 46)[:3], (0, 0, 255))  # past the fill: frame


class Comparison(unittest.TestCase):
    W, H = 8, 4

    def buf(self, fill=(0, 0, 0, 0x80)):
        return bytearray(bytes(fill) * (self.W * self.H))

    def test_identical(self):
        r = C.compare(self.buf(), self.buf(), self.W, self.H)
        self.assertEqual(r, C.Report(0, 0, 32, None, None))

    def test_tolerance_and_bbox(self):
        a, b = self.buf(), self.buf()
        b[4 * (1 * self.W + 2)] = 5
        b[4 * (2 * self.W + 6) + 2] = 40
        r = C.compare(a, b, self.W, self.H, tolerance=8)
        self.assertEqual((r.max_delta, r.over, r.bbox, r.first), (40, 1, (6, 2, 7, 3), (6, 2)))
        r = C.compare(a, b, self.W, self.H)
        self.assertEqual((r.over, r.bbox), (2, (2, 1, 7, 3)))

    def test_mask_and_alpha_ignored(self):
        a, b = self.buf(), self.buf()
        b[4 * (0 * self.W + 0)] = 99
        b[4 * (3 * self.W + 7) + 3] = 0
        r = C.compare(a, b, self.W, self.H, mask=[(0, 0, 1, 1)])
        self.assertEqual((r.over, r.total), (0, 31))

    def test_slack_forgives_one_row_shift(self):
        a, b = self.buf(), self.buf()
        for x in range(self.W):
            a[4 * (1 * self.W + x)] = 200
            b[4 * (2 * self.W + x)] = 200
        self.assertEqual(C.compare(a, b, self.W, self.H).over, 16)
        self.assertEqual(C.compare(a, b, self.W, self.H, slack=1).over, 0)

    def test_size_mismatch(self):
        with self.assertRaises(ValueError):
            C.compare(self.buf(), bytearray(4), self.W, self.H)


class RecordDiff(unittest.TestCase):
    def test_equal_after_normalisation(self):
        orig = [R.Draw('a.tex', 1, 2), R.Draw('b.tex', 1, 2, (0, 0, 9, 9))]
        native = [C.Blit('a.tex', 1, 3, (0, 0, 4, 2)), C.Blit('b.tex', 1, 2, (0, 0, 4, 2), (0, 0, 9, 9))]
        self.assertEqual(C.diff_records(orig, native, TEX), [])

    def test_order_and_value_differences_reported(self):
        orig = [R.HudLayer('a.tex', 1, 2, None, C.NEUTRAL, 6), R.HudLayer('b.tex', 1, 2, None, C.NEUTRAL, 6)]
        native = [R.HudLayer('a.tex', 1, 2, None, C.NEUTRAL, 6), R.HudLayer('b.tex', 1, 3, None, C.NEUTRAL, 6)]
        d = C.diff_records(orig, native, TEX)
        self.assertEqual(len(d), 1)
        op, a, b = d[0]
        self.assertEqual((op, a[0].y, b[0].y), ('replace', 2, 3))

    def test_unknown_record_rejected(self):
        with self.assertRaises(TypeError):
            C.normalize((1, 2), TEX)


if __name__ == '__main__':
    unittest.main()
