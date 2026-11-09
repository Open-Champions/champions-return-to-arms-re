#!/usr/bin/env python3
"""Synthetic tests of tools/ref_dialog_system.py (no game file needed).

  python3 -m unittest tools/test_ref_dialog_system.py   (or run it directly)
"""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_dialog as R  # noqa: E402
import ref_dialog_system as S  # noqa: E402


class PostAction(unittest.TestCase):
    def test_second_post_replaces_first(self):
        s = S.Scripts()
        s.set_post('a')
        s.set_post('b')
        ran = []
        s.run_post(ran.append)
        self.assertEqual(ran, ['b'])
        self.assertEqual(s.post, '')

    def test_empty_runs_nothing(self):
        s = S.Scripts()
        self.assertIsNone(s.run_post(lambda n: self.fail('ran')))

    def test_post_set_inside_post_action_is_kept(self):
        s = S.Scripts()
        s.set_post('a')
        seen = []

        def run(name):
            seen.append((name, s.in_post, s.post))
            s.set_post('b')
        s.run_post(run)
        self.assertEqual(seen, [('a', 1, '')])
        self.assertEqual((s.post, s.in_post), ('b', 0))


class Deferred(unittest.TestCase):
    def test_runs_next_frame_in_order(self):
        s = S.Scripts()
        s.queue('x')
        s.queue('y')
        ran = []
        s.run_deferred(ran.append)          # this frame: nothing was in the front half
        self.assertEqual(ran, [])
        s.run_deferred(ran.append)
        self.assertEqual(ran, ['x', 'y'])

    def test_requeue_from_a_deferred_entry_waits_a_frame(self):
        s = S.Scripts()
        s.queue('loop')
        s.run_deferred(lambda n: None)
        ran = []

        def run(name):
            ran.append(name)
            s.queue(name)
        s.run_deferred(run)
        s.run_deferred(run)
        self.assertEqual(ran, ['loop', 'loop'])

    def test_sixty_fifth_name_dropped(self):
        s = S.Scripts()
        self.assertTrue(all(s.queue('n%d' % i) for i in range(64)))
        self.assertFalse(s.queue('late'))
        self.assertEqual(s.queued, 64)

    def test_clear_inside_the_loop_stops_it(self):
        s = S.Scripts()
        for nm in ('a', 'b', 'c'):
            s.queue(nm)
        s.run_deferred(lambda n: None)
        ran = []

        def run(name):
            ran.append(name)
            if name == 'a':
                s.clear()
        s.run_deferred(run)
        self.assertEqual(ran, ['a'])
        self.assertEqual((s.run_count, s.queued, s.flip), (0, 0, 1))


def one_node(action='act', nxt=-1):
    host = R.Host()
    host.texts.update({'tx': [0x41], 'ch': [0x42], 'Affirmation': [1], 'dialogMore': [1], 'nm': [1]})
    obj = R.Object(0x1000, flags=0x20, npc=True, props={'showname': 'nm'})
    host.objects['npc'] = [obj]
    host.player_obj = {0: R.Object(0x2000)}
    return host, [R.Node('', 'tx', 'v', '', [R.Choice('ch', '', action, nxt)])]


class Chain(unittest.TestCase):
    def open(self, programs, network=False):
        host, nodes = one_node()
        host.network = network
        sess = S.Session(host, nodes, programs)
        sess.outbox = []
        sess.d.mutex = 1
        sess.message(R.start_message('npc', 0, 0, 0, [0, 0, 0], 0, 0))
        d = sess.d
        d.revealing, d.reveal_done, d.at_end, d.more = 0, 1, 1, 0
        sess.message(bytes((R.MSG_CONFIRM,)))
        return sess

    def test_post_action_sees_closed_dialog_and_free_mutex(self):
        sess = self.open({'act': [('post', 'pa')], 'pa': [('running',)]})
        sess.message(bytes((R.MSG_END,)))
        name, sentinel = sess.runs[-1]
        self.assertEqual(name, 'pa')
        self.assertEqual(sentinel[:5], (0, 0, 0, 0, 1))
        self.assertEqual(sentinel[8], '')
        self.assertEqual(sess.observed, [0])

    def test_offline_chained_open_drops_the_pending_shop(self):
        progs = {'act': [('store', 3), ('post', 'pa')], 'pa': [('start', 'npc', 0, 0)]}
        sess = self.open(progs)
        sess.d.log = []
        sess.message(bytes((R.MSG_END,)))
        self.assertTrue(sess.d.is_open)
        self.assertFalse(any(t[0] == 'shop' for t in sess.d.log))
        self.assertEqual(sess.d.mutex, 0)       # the chained dialog runs without the mutex

    def test_net_chained_open_waits_and_shop_opens(self):
        progs = {'act': [('store', 3), ('post', 'pa')], 'pa': [('start', 'npc', 0, 0)]}
        sess = self.open(progs, network=True)
        sess.d.log = []
        sess.message(bytes((R.MSG_END,)))
        self.assertFalse(sess.d.is_open)
        self.assertEqual(len(sess.outbox), 1)
        self.assertTrue(any(t[0] == 'shop' for t in sess.d.log))

    def test_duplicate_end_is_ignored_unless_a_new_dialog_opened(self):
        sess = self.open({'act': []})
        sess.message(bytes((R.MSG_END,)))
        sess.d.log = []
        sess.message(bytes((R.MSG_END,)))
        self.assertEqual(sess.d.log, [])


class InputMap(unittest.TestCase):
    def test_only_up_down_confirm(self):
        self.assertEqual(S.input_map(0x40, 0x40), [bytes((1,))])
        self.assertEqual(S.input_map(0x1000, 0x40), [bytes((2, 0xFF))])
        self.assertEqual(S.input_map(0x200000, 0x40), [bytes((2, 1))])
        for layout in (0, 1):
            confirm, cancel = S.CONFIRM_LAYOUT[layout], S.CANCEL_LAYOUT[layout]
            for bits in (cancel, S.DEFAULT_USE, 0x800, 0x1, 0x10):
                self.assertEqual(S.input_map(bits, confirm), [], hex(bits))
        self.assertEqual(S.input_map(0x40, 0x40, paused=True), [])


if __name__ == '__main__':
    unittest.main()
