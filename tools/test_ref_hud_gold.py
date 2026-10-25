"""Synthetic tests for tools/ref_hud_gold.py (no game data; no ELF needed)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_core as F
import ref_hud_gold as G


def sep(text, language=0):
    buf = bytearray(text + b'\0' + b'\xaa' * 8)
    G.insert_separators(buf, language)
    return bytes(buf[:buf.index(0)])


class Separators(unittest.TestCase):
    def test_up_to_eight_digits_match_grouping(self):
        for v in (0, 7, 42, 999, 1000, 12345, 999999, 1000000, 1234567, 99999999):
            self.assertEqual(G.format_gold(v, 0), '{:,}'.format(v).encode())

    def test_language_byte(self):
        self.assertEqual(G.format_gold(1234567, 0), b'1,234,567')
        for lang in (1, 2, 0x7f, 0x80, 0xff):
            self.assertEqual(G.format_gold(1234567, lang), b'1.234.567')

    def test_nine_digits_double_separator(self):
        self.assertEqual(sep(b'123456789'), b'1234,,56789')

    def test_negative_quirk(self):
        self.assertEqual(G.format_gold(-123, 0), b'-,123')
        self.assertEqual(G.format_gold(-1234, 0), b'-1,234')

    def test_overrun_byte_written(self):
        buf = bytearray(b'1234\0\xaa\xaa\xaa')
        G.insert_separators(buf, 0)
        self.assertEqual(bytes(buf[:7]), b'1,234\0\xaa')     # byte n+g+1 = old byte n+g

    def test_short_strings_untouched(self):
        for t in (b'', b'1', b'12', b'123'):
            self.assertEqual(sep(t), t)


class Credit(unittest.TestCase):
    def test_cap_and_wrap(self):
        self.assertEqual(G.credit(G.GOLD_CAP - 5, 10), G.GOLD_CAP)
        self.assertEqual(G.credit(0xFFFFFFF0, 4), 0xFFFFFFF4)

    def test_tick_delay_and_eighths(self):
        st = G.GoldState()
        st.floaters[2].amount, st.floaters[2].slot, st.floaters[2].start = 120, 1, 100
        st.frame = 142
        G.tick_gold(st)
        self.assertEqual((st.gold[1], st.floaters[2].amount), (0, 120))
        st.frame = 143
        G.tick_gold(st)
        self.assertEqual((st.gold[1], st.pending[1], st.floaters[2].amount), (15, 105, 0))
        paid = [15]
        while st.pending[1]:
            G.tick_gold(st)
            paid.append(st.gold[1] - sum(paid))
        self.assertEqual(sum(paid), 120)
        self.assertEqual(paid[:4], [15, 14, 12, 10])

    def test_all_busy_direct_credit_no_draw(self):
        st = G.GoldState()
        for f in st.floaters:
            f.amount = 1
        seed = st.cosmetic
        self.assertEqual(G.add_gold_floater(st, 3, [0, 0, 0], 50, [0] * 16), -1)
        self.assertEqual((st.gold[3], st.cosmetic, st.cosmetic_draws), (50, seed, 0))

    def test_first_free_floater_and_one_cosmetic_draw(self):
        st = G.GoldState()
        st.floaters[0].amount = 9
        st.frame, st.cosmetic = 77, 1
        m = [0] * 16
        m[0] = m[5] = m[10] = F.f32(1.0)
        m[15] = F.f32(100.0)
        self.assertEqual(G.add_gold_floater(st, 0, [0, 0, 0], 5, m), 1)
        f = st.floaters[1]
        self.assertEqual((f.amount, f.slot, f.start, f.offscreen), (5, 0, 77, 0))
        self.assertEqual(f.pos, [F.f32(320.0), F.f32(240.0), 0])
        self.assertEqual((st.cosmetic, st.cosmetic_draws), (G.lcg(1), 1))

    def test_flush_zeroes_counter(self):
        st = G.GoldState()
        st.floaters[0].amount, st.pending[2], st.hold, st.alpha = 7, 9, [5] * 4, [64] * 4
        G.flush_gold(st)
        self.assertEqual((st.gold[0], st.gold[2], st.hold, st.alpha), (7, 9, [0] * 4, [0] * 4))


class Draw(unittest.TestCase):
    def test_floater_alpha(self):
        self.assertEqual([G.floater_alpha(10 + d, 10) for d in (-5, 0, 1, 42, 43)], [128, 128, 125, 2, 0])

    def test_right_aligned_slot_and_coin(self):
        st = G.GoldState()
        st.gold[1], st.alpha[1] = 1500, 128
        calls = G.draw_gold(st, lambda s: True, lambda t: 10 * len(t), 0)
        draw = [c for c in calls if c[0] == 'text_drawAscii']
        self.assertEqual(draw, [('text_drawAscii', 590 - 50, 200, b'1,500', G.TEXT_LIMIT)])
        self.assertEqual(calls[-1], ('ui_drawSprite', 'coin', 593, 190, 6, 0x7C808080))
        self.assertEqual(st.alpha[1], 124)

    def test_non_local_slot_not_stepped(self):
        st = G.GoldState()
        st.alpha = [40] * 4
        G.draw_gold(st, lambda s: s == 0, len, 0)
        self.assertEqual(st.alpha, [36, 40, 40, 40])

    def test_hud_off_freezes(self):
        st = G.GoldState()
        st.alpha = [40] * 4
        self.assertEqual(G.draw_gold(st, lambda s: True, len, 0, hud_off=True), [])
        self.assertEqual(st.alpha, [40] * 4)

    def test_bonus_life_fade(self):
        st = G.GoldState()
        G.arena_bonus_life(st, 2)
        n = 0
        while st.alpha[2] > 0:
            G.draw_gold(st, lambda s: True, len, 0)
            n += 1
        self.assertEqual(n, 32)

    def test_single_pickup_timeline(self):
        tl = G.counter_timeline(120)
        shown = [t for t, _g, _p, _h, a in tl if a > 0]
        self.assertEqual((shown[0], shown[-1]), (0, 132))
        self.assertEqual(tl[31][4], 128)
        self.assertEqual(tl[42][1], 0)
        self.assertEqual(tl[43][1], 15)
        self.assertEqual((tl[101][3], tl[101][4], tl[102][4]), (0, 128, 124))


if __name__ == '__main__':
    unittest.main()
