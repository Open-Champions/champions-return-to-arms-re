"""Synthetic tests for tools/ref_hud_quickslots.py (no ELF needed)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ref_core as F                  # noqa: E402
import ref_hud_quickslots as Q        # noqa: E402


def potion_state(**kw):
    st = dict(copy=False, hp=F.f32(50.0), maxhp=F.f32(100.0), hp_pending=F.ZERO,
              mana=F.f32(10.0), maxmana=F.f32(100.0), mana_pending=F.ZERO, bag=[],
              local=1, menu_open=0, grid=0, kind=0, timers=[0] * 8, rows=[0] * 8)
    st.update(kw)
    return st


class Notices(unittest.TestCase):
    def test_start_notice_row_counts_others(self):
        t, r = Q.start_notice([5, 0, 0, 0, 0, 0, 0, 0], [0] * 8, 4, Q.NOTICE_LONG)
        self.assertEqual(t[4], 240)
        self.assertEqual(r[4], 1)           # line 0 runs; line 4 itself not counted

    def test_count_line_hidden_by_no_line(self):
        t, r = Q.start_notice([0, 9, 0, 0, 0, 0, 0, 0], [0] * 8, 1, Q.NOTICE_SHORT)
        self.assertEqual(r[1], 0)

    def test_starter_table(self):
        lines = sorted(set(l for l, *_ in Q.NOTICE_STARTERS))
        self.assertEqual(lines, list(range(8)))
        for line, frames, *_ in Q.NOTICE_STARTERS:
            self.assertEqual(frames, Q.NOTICE_LONG if line >= 4 else Q.NOTICE_SHORT)


class Potions(unittest.TestCase):
    def test_count_kinds(self):
        bag = [(('h', 0), 2), (('m', 3), 4), ('other', 9), (('h', 8), 1)]
        self.assertEqual(Q.count_potions(bag, 0), (3, Q.COUNT_HEALTH))
        self.assertEqual(Q.count_potions(bag, 1), (4, Q.COUNT_MANA))
        self.assertEqual(Q.count_potions(bag, 2), (4, Q.COUNT_HEALTH))   # mana names, health store

    def test_size_choice(self):
        found = [-1] * 9
        found[2] = 0
        self.assertEqual(Q.potion_size(F.f32(200.5), found), 2)      # wanted 3, largest present 2
        found[8] = 1
        self.assertEqual(Q.potion_size(F.f32(200.5), found), 8)      # size 8 preferred
        self.assertEqual(Q.potion_size(F.f32(61.0), [-1] * 9), -1)

    def test_no_potion_notice(self):
        out = Q.use_potion(potion_state())
        self.assertEqual(out['notices'], [(1, 120)])
        self.assertEqual(out['timers'][1], 120)

    def test_full_health_no_notice(self):
        out = Q.use_potion(potion_state(hp=F.f32(100.0)))
        self.assertTrue(out['returned_early'])
        self.assertEqual(out['notices'], [])

    def test_use_and_low_count(self):
        bag = [(('h', 0), 3)]
        out = Q.use_potion(potion_state(bag=bag))
        self.assertEqual(out['count'], 2)
        self.assertEqual(out['notices'], [(4, 240)])
        self.assertEqual(out['pending'], F.f32(50.0))                 # 60 capped at missing 50
        self.assertEqual(out['sound'], 'potion_health.anm')

    def test_menu_path_keeps_stack(self):
        bag = [(('m', 0), 1)]
        out = Q.use_potion(potion_state(kind=1, bag=bag, menu_open=1, grid=1))
        self.assertTrue(out['sent_drop'])
        self.assertIsNone(out['removed'])
        self.assertEqual(out['count'], 1)
        self.assertEqual(out['notices'], [(5, 240)])

    def test_last_potion_removed_no_count_notice(self):
        out = Q.use_potion(potion_state(bag=[(('h', 1), 1)]))
        self.assertEqual(out['removed'], 0)
        self.assertEqual(out['count'], 0)
        self.assertEqual(out['notices'], [])


class Selector(unittest.TestCase):
    def base(self, **kw):
        recs = [dict(id=-1, newstyle=False, name='x')] * 8
        st = dict(slot=0, page=0, menu=0, kind=0, value=0, players=1, network=0, local=1,
                  hp=F.f32(10.0), gates={}, local_menu_open=0, held_bits=0, pressed_bits=0,
                  masks=dict(a=0x20, b=0x10, use=0x40, accept=0x40), alpha=0, timer=F.ZERO,
                  speed=-1, prev_dir=-1, tick=0, quick=(0, 2), records=recs,
                  glyphs={1: 0x7b, 2: 0x7c, 3: 0x7d}, mask_entry=(0, 0, 0), font=1)
        st.update(kw)
        return st

    def test_glyph(self):
        self.assertEqual(Q.button_glyph(0x20), 0x7b)
        self.assertEqual(Q.button_glyph(0x2), 0x7b + 11)
        self.assertEqual(Q.button_glyph(0x100), 0)

    def test_gates(self):
        self.assertTrue(Q.pad_readable({}, 0))
        for name, _ in Q.GATES:
            self.assertFalse(Q.pad_readable({name: 1}, 0))
            self.assertTrue(Q.pad_readable({name: 1}, 1))

    def test_pad_axes_later_wins(self):
        self.assertEqual(Q.pad_axes(0xa000), (-1, 0, True))
        self.assertEqual(Q.pad_axes(0x5000), (0, 1, True))

    def test_closed_draws_nothing(self):
        ev, s = Q.selector_frame(self.base())
        self.assertEqual(ev, [])
        self.assertEqual(s['alpha'], 0)

    def test_up_opens_and_masks(self):
        ev, s = Q.selector_frame(self.base(held_bits=0x1000))
        self.assertEqual(s['alpha'], 16)
        self.assertEqual(s['dir'], 0)
        self.assertEqual(s['mask_entry'], (3, 0x70, 0))
        self.assertEqual(ev[0], ('sound', 'fx.lmp', 'menu_spell_high.anm'))
        self.assertIn(('prompt', 0x80, 0, 0), ev)

    def test_gate_blocks(self):
        ev, s = Q.selector_frame(self.base(held_bits=0x1000, gates={'paused': 1}))
        self.assertEqual((ev, s['alpha'], s['mask_entry']), ([], 0, (0, 0, 0)))

    def test_buttons_send(self):
        ev, _ = Q.selector_frame(self.base(held_bits=0x2000, pressed_bits=0x20))
        self.assertIn(('msg', Q.MSG_QUICKSLOT, (0, 0, 2)), ev)
        ev, _ = Q.selector_frame(self.base(held_bits=0x2000, pressed_bits=0x40))
        self.assertIn(('msg', Q.MSG_QUICKCAST, (0, 2)), ev)

    def test_icons(self):
        self.assertEqual(Q.record_icon(dict(id=-1, newstyle=True)), ('blank',))
        self.assertEqual(Q.record_icon(dict(id=7, newstyle=True)), ('skill', 7))
        self.assertEqual(Q.record_icon(dict(id=25, newstyle=False)), ('table', 25))
        self.assertEqual(Q.ICON_TABLE_INDEX[37], 'icslam.tex')

    def test_menu_mode(self):
        ev, s = Q.selector_frame(self.base(menu=1, page=1, kind=1, value=5))
        self.assertEqual(s['alpha'], 16)
        self.assertEqual(ev[-1][1], ('res', 'inventry.lmp', 'spellbookparch.tex'))
        self.assertEqual(ev[-1][2:4], (320 + 0x39, 0xa5))
        self.assertEqual(ev[-2][1], ('icon_or_none', ('skill', 5)))


if __name__ == '__main__':
    unittest.main()
