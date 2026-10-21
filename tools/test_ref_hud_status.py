"""Synthetic tests of tools/ref_hud_status.py (no ELF, no game data)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_core as F
import ref_hud_status as R
import ref_ui_layout as L

f = F.f32


def state(**kw):
    base = dict(slot=0, x=12, local=True, obj_flags=0, health=f(50.0), health_max=f(100.0),
                health_pending=f(20.0), mana=f(30.0), mana_max=f(60.0), mana_pending=f(10.0),
                tick=44, flash=0, cooldown=0, ack_level=1, level=1, exp=50, exp_base=0,
                exp_next=100, glow_alpha=0)
    base.update(kw)
    return R.State(**base)


def rects(draws):
    return [d for d in draws if isinstance(d, R.Rect)]


class PendingArithmetic(unittest.TestCase):
    def test_known_rows(self):
        # S = 27; a = trunc((C/M)*99), t = trunc(C+p) lowered to trunc(M), b = trunc(t/M*99)
        self.assertEqual(R.pending_rect(0, 27, f(50.0), f(100.0), f(20.0), R.HEALTH_RECT),
                         R.Rect(76, 47, 96, 51, 6, 0x80000060))
        self.assertEqual(R.pending_rect(0, 27, f(30.0), f(60.0), f(10.0), R.MANA_RECT),
                         R.Rect(76, 66, 92, 70, 6, 0x805A4632))
        self.assertEqual(R.pending_rect(0, 27, f(1.0), f(3.0), f(1.5), R.HEALTH_RECT).x1, 92)
        self.assertEqual(R.pending_rect(0, 27, f(2.0), f(7.0), f(0.25), R.MANA_RECT)[:3:2], (55, 55))

    def test_sum_past_maximum_is_lowered_to_trunc_maximum(self):
        left, right = R.pending_span(27, f(90.0), f(100.0), f(500.0))
        self.assertEqual((left, right), (27 + 89, 27 + 99))
        left, right = R.pending_span(27, f(1.0), f(2.5), f(9.0))    # t = trunc(2.5) = 2
        self.assertEqual(right, 27 + F.to_int(F.mul(F.div(F.from_int(2), f(2.5)), R.BAR_SPAN_F)))

    def test_truncation_before_ratio_can_invert(self):
        left, right = R.pending_span(27, f(5.7), f(10.0), f(0.2))   # t = 5 < 5.7
        self.assertLess(right, left)
        left, right = R.pending_span(27, f(120.0), f(100.0), f(5.0))  # current above maximum
        self.assertLess(right, left)

    def test_caps_by_raw_slot(self):
        self.assertEqual([R.pending_cap(s) for s in range(4)], [180, 605, 333, 447])
        r = R.pending_rect(0, 400, f(0.0), f(100.0), f(100.0), R.HEALTH_RECT)
        self.assertEqual((r.x0, r.x1), (400, 180))
        r = R.pending_rect(3, 27, f(0.0), f(100.0), f(100.0), R.HEALTH_RECT)
        self.assertEqual(r.x1, 126)

    def test_shipped_origins_never_reach_cap(self):
        for network in (False, True):
            for local in ((0,), (1,), (0, 2), (1, 3), (2,), (0, 1, 2, 3)):
                xs = L.hud_origins(network, local, 4)
                for slot in range(4):
                    if network and slot not in local:
                        continue          # remote slot: no rectangle at all
                    self.assertLess(xs[slot] + 15 + 99, R.pending_cap(slot))


class Gates(unittest.TestCase):
    def test_dead_bit_suppresses_both(self):
        d, *_ = R.status_draws(state(obj_flags=R.DEAD_FLAG))
        self.assertEqual(rects(d), [])

    def test_health_not_positive_still_draws_both(self):
        for h in (0.0, -5.0):
            d, *_ = R.status_draws(state(health=f(h)))
            self.assertEqual([r.colour for r in rects(d)], [0x80000060, 0x805A4632])

    def test_each_pending_needs_its_own_positive_value(self):
        d, *_ = R.status_draws(state(health_pending=f(0.0)))
        self.assertEqual([r.colour for r in rects(d)], [0x805A4632])
        d, *_ = R.status_draws(state(mana_pending=f(-1.0)))
        self.assertEqual([r.colour for r in rects(d)], [0x80000060])

    def test_remote_slot(self):
        d, lookups, *_ = R.status_draws(state(local=False))
        self.assertEqual([x.resource for x in d], ['bar_red00.tex', 'hud_multi.tex'])
        self.assertEqual(lookups, ['bar_red00.tex', 'hud_statusbar00.tex', 'hud_multi.tex'])

    def test_local_order(self):
        d, *_ = R.status_draws(state(level=2))
        kinds = [x.resource if isinstance(x, R.ClipSprite) else x.colour for x in d]
        self.assertEqual(kinds, ['bar_red00.tex', 0x80000060, 0x805A4632, 'bar_green00.tex',
                                 'bar_blue00.tex', 'hud_statusbar00glow.tex', 'hud_statusbar00.tex'])

    def test_visible(self):
        self.assertTrue(R.visible())
        for kw in (dict(menu_open=1), dict(hud_suppressed=0x80), dict(shop_open=1),
                   dict(camera_mode=0), dict(camera_mode=2), dict(slot_active=False),
                   dict(has_object=False), dict(vehicle=1), dict(free_units=2999)):
            self.assertFalse(R.visible(**kw), kw)
        self.assertTrue(R.visible(free_units=3000))

    def test_local_flag(self):
        self.assertTrue(R.local_flag(False, False))
        self.assertTrue(R.local_flag(True, True))
        self.assertFalse(R.local_flag(True, False))


class Bars(unittest.TestCase):
    def test_fill_matches_base_layer_reference(self):
        for c, m in ((1.0, 4.0), (3.0, 7.0), (99.0, 100.0), (0.0, 5.0)):
            self.assertEqual(R.fill_right(27, f(c), f(m)), L.bar_clip_right(27, c, m))

    def test_flash_and_cooldown(self):
        d, _l, flash, _g = R.status_draws(state(flash=3, cooldown=1))
        self.assertEqual(flash, 2)
        self.assertEqual(d[0].tint, 0x80FFFFFF)
        mana = [x for x in d if isinstance(x, R.ClipSprite) and x.resource.startswith('bar_blue')]
        self.assertEqual(mana[0].tint, 0x2AACACAC)
        d, _l, flash, _g = R.status_draws(state(flash=2, cooldown=0x8000))
        self.assertEqual((flash, d[0].tint), (2, 0x80808080))
        mana = [x for x in d if isinstance(x, R.ClipSprite) and x.resource.startswith('bar_blue')]
        self.assertEqual(mana[0].tint, 0x80ACACAC)

    def test_bar_records(self):
        d, *_ = R.status_draws(state(health_pending=0, mana_pending=0))
        self.assertEqual(d[0], R.ClipSprite('bar_red00.tex', 27, 46, 6, 0x80808080, 27, 24,
                                            R.fill_right(27, f(50.0), f(100.0)), 124, 0, 0))

    def test_anim_frame_c_semantics(self):
        self.assertEqual(R.anim_frame(44), 0)
        self.assertEqual(R.anim_frame(4 * 23), 1)
        self.assertEqual(R.anim_frame(-4), -1)
        self.assertEqual(R.bar_name('red', -4), 'bar_red-1.tex')

    def test_glow_alpha_steps(self):
        _d, _l, _f, g = R.status_draws(state(level=2, glow_alpha=126))
        self.assertEqual(g, 128)
        _d, _l, _f, g = R.status_draws(state(level=2, glow_alpha=126, health=f(0.0)))
        self.assertEqual(g, 126)


class Packet(unittest.TestCase):
    def test_corners(self):
        r = R.Rect(27, 47, 96, 51, 6, 0x80000060)
        self.assertEqual(R.rect_gs_corners(r, True),
                         ((32 * 27 + 0x5800, 16 * 47 + 0x7200), (32 * 96 + 0x5800, 16 * 51 + 0x7200)))
        self.assertEqual(R.rect_gs_corners(r, False)[0][0], 16 * 27 + 0x6C00)
        w0, _w1 = R.rect_xyz2(r, True)
        self.assertEqual((w0 & 0xFFFF, (w0 >> 16) & 0xFFFF, w0 >> 32),
                         (32 * 27 + 0x5800, 16 * 47 + 0x7200, 0xA))

    def test_negative_x_corrupts_word(self):
        w0, _ = R.rect_xyz2(R.Rect(-800, 47, 0, 51, 6, 0), True)
        self.assertEqual((w0 >> 16) & 0xFFFF, 0xFFFF)

    def test_packets(self):
        self.assertEqual(R.rect_packets(3000, 2), 1)
        self.assertEqual(R.rect_packets(3016, 2), 2)
        self.assertEqual(R.rect_packets(2999, 2), 0)


class Vectors(unittest.TestCase):
    def test_row_shape(self):
        import random
        rng = random.Random(1)
        for _ in range(50):
            st = R.random_state(rng)
            cells = R.vector_row(st).split('\t')
            n = int(cells[len(R.VECTOR_COLUMNS) - 1])
            self.assertEqual(len(cells), len(R.VECTOR_COLUMNS) + n * len(R.DRAW_COLUMNS))


if __name__ == '__main__':
    unittest.main()
