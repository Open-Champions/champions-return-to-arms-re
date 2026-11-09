"""Unit tests of the front-end flow reference (no game file needed)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_frontend_flow as R  # noqa: E402


class FrontendFlowReference(unittest.TestCase):
    def test_max_difficulty_bits(self):
        self.assertEqual([R.max_difficulty(w) for w in (0, 4, 8, 1, 0x10, 0x20, 0x40, 0x7D)],
                         [1, 2, 2, 3, 3, 4, 5, 5])

    def test_difficulty_rows_lock_above_profile(self):
        self.assertEqual([R.difficulty_accept(r, 0) for r in range(4)], [1, None, None, None])
        self.assertEqual([R.difficulty_accept(r, 0x20) for r in range(4)], [1, 2, 3, 4])

    def test_players_and_mode_tables(self):
        self.assertEqual(R.players_accept(0), (1, R.S_MODE, R.T_MODE_ONE))
        self.assertEqual(R.players_accept(3), (4, R.S_MODE, R.T_MODE_MULTI))
        self.assertEqual(R.players_row_kinds(1), (0, 5, 5, 5))
        self.assertEqual(R.players_row_kinds(3), (0, 0, 0, 5))
        self.assertEqual(R.mode_next(0, 0, 0), ('difficulty', R.S_DIFFICULTY, R.T_DIFFICULTY))
        self.assertEqual(R.mode_next(1, 0, 1)[0], 'kill')
        self.assertEqual(R.mode_next(0, 0, 1), ('select', 1))

    def test_import_phase_from_difficulty_two(self):
        self.assertEqual([R.import_first(d) for d in (1, 2, 3, 4)], [0, 1, 1, 1])

    def test_stat_allocation_bounds(self):
        base = list(R.class_base(1))
        stats, points, _ = R.stat_input(base, 20, 0, 1, R.REPEAT_RIGHT)
        self.assertEqual((stats[0], points), (base[0] + 1, 19))
        self.assertEqual(R.stat_input([100] + base[1:], 5, 0, 1, R.REPEAT_RIGHT)[1], 5)
        self.assertEqual(R.stat_input(base, 0, 0, 1, R.REPEAT_LEFT)[0], base)
        self.assertEqual(R.stat_input(base, 0, 3, 1, R.REPEAT_DOWN)[2], 3)
        self.assertEqual(R.stat_accept(1), 'warn')
        self.assertEqual(R.stat_accept(0), R.PHASE_NAME)

    def test_name_rules(self):
        glyphs = 'abc'
        self.assertEqual(R.name_accept('', 1, glyphs), ('b', 0, 0))
        self.assertEqual(R.name_accept('x' * 30, 0, glyphs), ('x' * 30, 0, 0))
        self.assertEqual(R.name_accept('  ', R.CURSOR_DONE, glyphs), ('  ', 0, 1))
        self.assertEqual(R.name_accept('a ', R.CURSOR_DONE, glyphs), ('a ', 1, 0))
        self.assertEqual(R.name_phase_result(1, 0, 1), (R.PHASE_FINISH_FADE, None))
        self.assertEqual(R.name_phase_result(1, 0, 2), (R.PHASE_NAME, R.PHASE_NEXT_PLAYER))
        self.assertEqual(R.name_phase_result(-1, 0, 2), (R.PHASE_NAME, R.PHASE_STATS))

    def test_no_text_in_reference(self):
        for name in dir(R):
            if not name.startswith('_'):
                self.assertNotIsInstance(getattr(R, name), (str, bytes), name)


if __name__ == '__main__':
    unittest.main()
