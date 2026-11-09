"""Pure tests for tools/ref_arena_acceptance.py (no executable needed).

Needles and identifiers below are synthetic stand-ins; the real ones are read from the
private executable by tools/difftest_arena_acceptance.py.
"""
import unittest

import ref_arena_acceptance as R
from ref_core import from_int


class FrontEnd(unittest.TestCase):
    NA, NS, NB = b'qq', b'zzzz', b'rrrr'

    def test_players(self):
        self.assertEqual(R.players_choice(0), (1, R.STATE_MODE, R.MENU_MODE_SOLO))
        self.assertEqual(R.players_choice(3), (4, R.STATE_MODE, R.MENU_MODE_MULTI))
        self.assertEqual(R.players_choice(4), (None, None, None))
        self.assertEqual(R.players_choice(-1), (None, None, None))

    def test_modes(self):
        coop = R.mode_choice(b'm_rrrr_x', self.NA, self.NS, self.NB, 3)
        self.assertEqual((coop['mode_a'], coop['mode_b'], coop['scramble']), (0, 1, 0))
        self.assertEqual((coop['difficulty'], coop['player_select'], coop['state']), (1, 1, None))
        vs = R.mode_choice(b'm_rrrr_qq', self.NA, self.NS, self.NB, 3)
        self.assertEqual((vs['mode_a'], vs['mode_b'], vs['state'], vs['menu']),
                         (1, 1, R.STATE_KILL_LIMIT, R.MENU_KILL_LIMIT))
        story = R.mode_choice(b'm_other', self.NA, self.NS, self.NB, 2)
        self.assertEqual((story['mode_b'], story['state'], story['players']), (0, R.STATE_DIFFICULTY, 2))
        scr = R.mode_choice(b'zzzz', self.NA, self.NS, self.NB, 4)
        self.assertEqual((scr['mode_b'], scr['scramble'], scr['players']), (1, 1, 1))

    def test_kill_limit(self):
        self.assertEqual([R.kill_limit_offline(i) for i in range(4)], [5, 10, 25, 25])


class NetLaunch(unittest.TestCase):
    def test_modes(self):
        got = [(r['mode_a'], r['mode_b'], r['scramble'])
               for r in (R.net_launch(m, 1, 5, 0, 0) for m in range(5))]
        self.assertEqual(got, [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 0, 0)])

    def test_word(self):
        self.assertEqual(R.net_launch(2, 0xFE, 25, 0xFFFFFFFF, 6)['w7110'], 6)
        self.assertEqual(R.net_launch(2, 0xFE, 25, 7, 6)['w7110'], 7)
        self.assertIsNone(R.net_launch(1, 0xFE, 25, 7, 6)['w7110'])
        self.assertEqual(R.net_launch(1, 0xFE, 25, 7, 6)['difficulty'], 0xFFFFFFFE)


class Items(unittest.TestCase):
    def test_remove_all(self):
        bags = [['a', 'b', 'c'], ['d', 'e'], ['f']]
        calls = R.remove_all(bags)
        self.assertEqual(bags, [['b'], [], []])
        self.assertEqual(calls, [(0, 0), (1, 0), (0, 1), (0, 1), (0, 2)])
        one = [['a'], [], ['x', 'y']]
        self.assertEqual(R.remove_all(one), [(0, 0), (0, 2), (0, 2)])
        self.assertEqual(one, [[], [], []])

    def test_team(self):
        self.assertEqual([R.import_team(1, s) for s in range(4)], [0, 1, 2, 3])
        self.assertEqual([R.import_team(0, s) for s in range(4)], [0, 0, 0, 0])


class Init(unittest.TestCase):
    A, B = [b'a1', b'a2', b'b1'], [b'b1']

    def test_branch(self):
        self.assertTrue(R.arena_init_fresh(b'x', 0, 0, self.A, self.B))
        self.assertFalse(R.arena_init_fresh(b'b1', 0, 0, self.A, self.B))
        self.assertTrue(R.arena_init_fresh(b'b1', 0, 1, self.A, self.B))
        self.assertTrue(R.arena_init_fresh(b'a1', 0, 0, self.A, self.B))
        self.assertFalse(R.arena_init_fresh(b'a1', 1, 0, self.A, self.B))
        self.assertEqual((R.minimap_mode(1), R.minimap_mode(0)), (1, 2))


class Results(unittest.TestCase):
    def test_rows(self):
        rows = R.result_rows([1, 0], [3, 0xFFFF], ['p', 'q'], 2)
        self.assertEqual(rows[:6], [(0x7B, '1.'), (0xA0, 'q'), (0x205, '-1'),
                                    (0x77, '1.'), (0x9C, 'q'), (0x201, '-1')])
        self.assertEqual(rows[6][1], '2.')

    def test_header(self):
        self.assertEqual(R.result_header(0, 1, 4), ('defeat', from_int(5)))
        self.assertEqual(R.result_header(0, 0, 0x8000), ('interval', from_int(-32767)))
        self.assertEqual(R.result_header(1, 0, 3), ('winner', None))


class Knock(unittest.TestCase):
    def test_gate(self):
        self.assertFalse(R.player_push_suppressed(0x40, 0, 0))
        self.assertTrue(R.player_push_suppressed(0x40, 1, 0))
        self.assertTrue(R.player_push_suppressed(0x60, 0, 1))
        self.assertFalse(R.player_push_suppressed(0x20, 1, 1))


class Overflow(unittest.TestCase):
    def test_wrap(self):
        self.assertEqual(R.overflow_wave(0x7FFF), 0x8000)
        self.assertEqual(R.overflow_wave(0xFFFF), 0)

    def test_negative_remainders_spawn_nothing(self):
        def byte_at(_addr):
            return 0x30
        for wave in (-32768, -32767):
            classes, _seed, steps, index = R.overflow_plan(wave, 1, 5, byte_at, 0x1000, 1)
            self.assertEqual((classes, steps), ([], []))
            self.assertLess(index, 0)
        classes, _seed, steps, _index = R.overflow_plan(-32766, 1, 5, byte_at, 0x1000, 1)
        self.assertEqual(classes, [])
        self.assertEqual(len(steps), 1)
        self.assertLess(steps[0][0], 0)


if __name__ == '__main__':
    unittest.main()
