#!/usr/bin/env python3
"""Synthetic tests of tools/ref_strings.py (no game files needed).

  python3 -m unittest tools/test_ref_strings.py

The cases are built by hand from docs/strings.md; tools/difftest_strings.py compares the
same model with the original functions.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_core as RC          # noqa: E402
import ref_strings as R        # noqa: E402


def w(text):
    return [ord(c) for c in text]


def colliding(count, target=None):
    import random
    rng = random.Random(1)
    target = R.text_hash(b'seed') if target is None else target
    out = []
    while len(out) < count:
        key = bytes(rng.choice(b'abcdefghij') for _ in range(rng.randint(3, 6)))
        if R.text_hash(key) == target and key not in out:
            out.append(key)
    return out


class HashAndTable(unittest.TestCase):
    def test_hash_is_13_bits_and_signed(self):
        self.assertEqual(R.text_hash(b''), 0)
        for key in (b'a', b'abc', b'\xff\x80', b'menu_mis0'):
            self.assertLess(R.text_hash(key), 0x2000)
        # a byte >= 0x80 is added as a negative number
        self.assertNotEqual(R.text_hash(b'\x80'), R.text_hash(b'\x00\x80'[1:2].replace(b'\x80', b'\x7f')))

    def test_uni_walk(self):
        data = R.build_uni([(b'ab', 'x'), (b'abc', ''), (b'k', 'hello')])
        got = [(key, units) for _ko, key, _to, units, _n in R.uni_entries(data)]
        self.assertEqual(got, [(b'ab', w('x')), (b'abc', []), (b'k', w('hello'))])
        # every text starts on an even offset
        for _ko, _key, toff, _u, _n in R.uni_entries(data):
            self.assertEqual(toff & 1, 0)

    def test_duplicate_key_keeps_first(self):
        data = R.build_uni([(b'dup', 'first'), (b'dup', 'second')])
        table = R.TextTable()
        table.register(data, 0x100000)
        _addr, units, hit = table.lookup(b'dup')
        self.assertTrue(hit)
        self.assertEqual(units, w('first'))

    def test_quotes_dropped_from_request_only(self):
        data = R.build_uni([(b'key', 'plain'), (b'k"q', 'quoted')])
        table = R.TextTable()
        table.register(data, 0x100000)
        self.assertEqual(table.lookup(b'"key"')[1], w('plain'))
        self.assertFalse(table.lookup(b'k"q')[2])        # the request loses its quote
        self.assertEqual(table.find(b'k"q'), 0)

    def test_miss_ring(self):
        table = R.TextTable()
        seen = []
        for i in range(18):
            addr, units, hit = table.lookup(b'missing_key_number_%02d' % i)
            self.assertFalse(hit)
            self.assertEqual(units, R.nf_text(b'missing_key_number_%02d' % i))
            self.assertEqual(len(units), 3 + 16)        # NF: + 16 bytes of the key
            seen.append(addr)
        self.assertEqual(seen[0], R.G_NF_RING + 40)     # the index is advanced first
        self.assertEqual(seen[15], R.G_NF_RING)         # 16th miss wraps to entry 0
        self.assertEqual(seen[16], seen[0])
        # a short key: the copy terminator ends the visible text
        _a, units, _h = table.lookup(b'ab')
        self.assertEqual(units, w('NF:ab'))
        self.assertEqual(table.nf_ring[table.nf_index][19], 0)

    def test_unregister_shadows_later_collider(self):
        a, b, c = colliding(3)
        first = R.build_uni([(a, 'A'), (b, 'B')])
        second = R.build_uni([(c, 'C')])
        table = R.TextTable()
        table.register(first, 0x100000)
        table.register(second, 0x200000)
        self.assertTrue(table.lookup(c)[2])
        table.unregister(first, 0x100000)
        # c sat two slots past its hash; the emptied slot now ends the probe
        self.assertFalse(table.lookup(c)[2])
        self.assertEqual(table.find(c), 0)

    def test_long_key_refused(self):
        with self.assertRaises(R.TableError):
            R.TextTable().lookup(b'x' * 0x200)


class Formatter(unittest.TestCase):
    def fmt(self, text, args=(), tail=(0,), **kw):
        out, _used = R.wstr_format(w(text) + [0] + list(tail), list(args), **kw)
        return out

    def test_plain_and_percent(self):
        self.assertEqual(self.fmt('ab'), w('ab') + [0])
        self.assertEqual(self.fmt('100%% '), w('100% ') + [0])
        # '%%' is a conversion too: at the very end it copies the terminator and
        # then looks at the unit after it
        self.assertEqual(self.fmt('100%%'), w('100%') + [0, 0])

    def test_empty_format_writes_two_zeros(self):
        self.assertEqual(self.fmt(''), [0, 0])

    def test_integer_and_char(self):
        self.assertEqual(self.fmt('n=%d.', [R.cvt_s_w(-42)]), w('n=-42.') + [0])
        self.assertEqual(self.fmt('[%c]', [R.cvt_s_w(0x263A)]), [0x5B, 0x263A, 0x5D, 0])
        # the integer arrives as a float and is truncated
        self.assertEqual(self.fmt('%d!', [RC.f32(-2.9)]), w('-2!') + [0])

    def test_float_two_places_only(self):
        self.assertEqual(self.fmt('%f!', [RC.f32(1.5)]), w('1.50!') + [0])
        self.assertEqual(self.fmt('%.2f!', [RC.f32(1.5)]), w('2f!') + [0])

    def test_float_widening(self):
        self.assertEqual(R.widen(0x00000001), 0.0)            # denormal pattern -> 0
        self.assertEqual(R.widen(0x7F800000), 2.0 ** 128)      # exponent 255 is a number
        self.assertEqual(self.fmt('%f!', [0x80000001]), w('-0.00!') + [0])

    def test_strings(self):
        mem8 = {0x1000: b'abc\0'}
        mem16 = {0x2000: [0x3042, 0x3044, 0]}
        out = self.fmt('%s-%u!', [R.cvt_s_w(0x1000), R.cvt_s_w(0x2000)],
                       cstr=mem8.get, wstr=mem16.get)
        self.assertEqual(out, w('abc-') + [0x3042, 0x3044, 0x21, 0])

    def test_unknown_conversion(self):
        self.assertEqual(self.fmt('a%xb'), w('ab') + [0])
        self.assertEqual(self.fmt('%x%d!', [R.cvt_s_w(7)]), w('7!') + [0])  # %x took nothing

    def test_conversion_at_end_reads_past_terminator(self):
        # the terminator is copied, then the units after it, until a copied unit is
        # followed by 0
        out = self.fmt('v%d', [R.cvt_s_w(5)], tail=w('KEY') + [0])
        self.assertEqual(out, w('v5') + [0] + w('KEY') + [0])
        self.assertEqual(R.visible(out), w('v5'))
        # a lone '%' skips the terminator itself as its conversion unit
        out = self.fmt('v%', tail=[0, 0])
        self.assertEqual(out, w('v') + [0, 0])

    def test_ninth_conversion_refused(self):
        with self.assertRaises(R.FormatError):
            self.fmt('%d' * 9 + '.', [0] * 8)


class HudCommands(unittest.TestCase):
    def setUp(self):
        self.table = R.TextTable()
        pairs = [(b'msg', 'Hello'), (b'title', 'T'), (b'body', 'B'),
                 (b'cnt', 'Count %d'), (b'long', 'x' * 40), (b'lbl', 'Go here')]
        self.table.register(R.build_uni(pairs), 0x300000)
        self.hud = R.Hud()
        self.cmd = R.Commands(self.table, self.hud, find_object=lambda n: (1, 2, 3) if n == b'obj' else None)

    def test_set_info(self):
        self.cmd.set_info(b'msg')
        self.assertEqual(self.hud.read_units(R.MESSAGE_TEXT), w('Hello'))
        self.assertEqual(self.hud.msg_frames, 180)
        for _ in range(180):
            self.hud.tick_message()
        self.assertEqual(self.hud.msg_frames, 0)

    def test_set_info_blocked_by_local_menu(self):
        self.hud.local_menu = 1
        self.cmd.set_info(b'msg')
        self.assertEqual(self.hud.msg_frames, 0)

    def test_help_has_no_queue(self):
        self.cmd.add_help_message(b'title', b'body')
        first = (self.hud.help_title, self.hud.help_body)
        self.cmd.add_help_message(b'body', b'title')
        self.assertEqual((self.hud.help_title, self.hud.help_body), first[::-1])
        self.assertEqual(sum(1 for e in self.hud.events if e[0] == 'sound_playOnObject'), 2)
        self.assertEqual(self.hud.help_close_delay, 90)

    def test_help_net_needs_local_alive(self):
        self.hud.network = 1
        self.hud.alive = [2, 3]
        self.hud.local = lambda slot: slot == 3
        self.cmd.add_help_message(b'title', b'body')
        self.assertEqual(self.hud.help_open, 1)
        self.assertIn(('hudmsg_sendMenuState', 3, 1, 0), self.hud.events)
        hud = R.Hud()
        hud.network, hud.alive, hud.local = 1, [1], (lambda slot: slot == -1)
        R.Commands(self.table, hud).add_help_message(b'title', b'body')
        self.assertEqual(hud.help_open, 0)

    def test_help_f_formats_and_overflows_title(self):
        self.cmd.add_help_message_f(b'cnt', 12, b'cnt', -3)
        self.assertEqual(self.hud.read_units(R.HELP_F_TITLE), w('Count 12'))
        self.assertEqual(self.hud.read_units(R.HELP_F_BODY), w('Count -3'))
        # a title of more than 31 units runs into the body buffer, which the body
        # copy then overwrites: the box shows 32 title units followed by the body
        self.cmd.add_help_message_f(b'long', 0, b'msg', 0)
        self.assertEqual(self.hud.read_units(R.HELP_F_TITLE), w('x' * 32 + 'Hello'))

    def test_bust_countdown(self):
        self.cmd.show_bust(b'portrait', b'lbl', 3, 10)
        self.assertEqual(self.hud.bust_shown, 5)
        for _ in range(5):
            self.hud.tick_widgets()
        self.assertEqual(self.hud.bust_shown, 0)

    def test_bust_text_overruns_compass_label(self):
        self.cmd.show_compass(b'obj', b'lbl')
        self.cmd.show_bust(b'p', b'long', 1, -1)
        self.assertEqual(self.hud.read_units(R.COMPASS_LABEL), w('x' * 8))

    def test_widget_gate(self):
        self.hud.suppressed = 1
        self.cmd.show_bust(b'p', b'lbl', 0, 0)
        self.assertEqual(self.hud.bust_shown, 0)
        self.hud.suppressed = 0
        self.hud.camera_mode = None
        with self.assertRaises(R.FormatError):
            self.cmd.show_compass(b'obj', b'lbl')

    def test_compass_missing_object(self):
        with self.assertRaises(R.FormatError):
            self.cmd.show_compass(b'none', b'lbl')

    def test_latch_four_players_offline(self):
        self.hud.num_players = 4
        self.cmd.set_info(b'msg')
        self.hud.tick_message()
        self.assertEqual(self.hud.latch, 1)


class SoundAndCharm(unittest.TestCase):
    def obj(self, pool, addr, flags=0x20):
        o = R.Creature(addr, flags)
        o.position = (0x3F800000, 0x40000000, 0x40400000)
        return o

    def test_last_free_slot_and_handle(self):
        pool = RC.HandlePool()
        seqs = R.SoundSeqs(pool)
        seqs.groups = {0x5000: 0}
        handle, slot = seqs.play_on_object(0x5000)
        self.assertEqual(slot, 31)
        self.assertEqual(handle, 31 | 0x8000)
        handle, slot = seqs.play_on_object(0x5000)
        self.assertEqual((slot, handle), (30, 30 | (1 << 8) | 0x8000))

    def test_category_cap(self):
        pool = RC.HandlePool()
        seqs = R.SoundSeqs(pool)
        seqs.groups = {0x5000: 3}
        seqs.limits[3] = 2
        self.assertIsNotNone(seqs.play_on_object(0x5000)[1])
        self.assertIsNotNone(seqs.play_on_object(0x5000)[1])
        self.assertEqual(seqs.play_on_object(0x5000), (0xFFFFFFFF, None))

    def test_follow_object_and_reuse(self):
        pool = RC.HandlePool()
        seqs = R.SoundSeqs(pool)
        a, b = self.obj(pool, 0x100000), self.obj(pool, 0x200000)
        _h, slot = seqs.play_on_object(0x5000, a)
        self.assertEqual(R.RC.HandlePool.items(seqs.slots[slot].handle_head), [a])
        # the slot finishes without clearing its handle; a new sound reuses it
        seqs.slots[slot].tracks = 0
        _h, again = seqs.play_on_object(0x5000, b)
        self.assertEqual(again, slot)
        self.assertEqual(R.RC.HandlePool.items(seqs.slots[slot].handle_head), [b])
        self.assertIsNone(a.heads[0].next)                 # a's back node went too
        self.assertEqual(pool.count_free(), RC.HandlePool.NODE_COUNT - 2)

    def test_charm_live_target(self):
        pool = RC.HandlePool()
        c = self.obj(pool, 0x100000)
        other = self.obj(pool, 0x200000)
        target = self.obj(pool, 0x300000)
        pool.link(c.target, target.heads[0], target)
        pool.link(other.target, target.heads[0], target)
        self.assertTrue(R.set_charm(pool, c, 0xFFFF, 0))
        self.assertIsNone(c.target.next)
        self.assertEqual(RC.HandlePool.items(other.target), [target])
        self.assertEqual(pool.count_free(), RC.HandlePool.NODE_COUNT - 2)
        self.assertEqual((c.team, c.charm), (0, 0xFFFF))
        # charmed creatures keep their target: -1 refuses
        pool.link(c.target, target.heads[0], target)
        self.assertFalse(R.set_charm(pool, c, 0xFFFF, 0))
        self.assertEqual(RC.HandlePool.items(c.target), [target])


if __name__ == '__main__':
    unittest.main()
