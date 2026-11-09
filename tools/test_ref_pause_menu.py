"""Static consistency of tools/ref_pause_menu.py (no executable needed)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import ref_pause_menu as R  # noqa: E402


class PauseMenuReference(unittest.TestCase):
    def test_every_main_row_has_an_action(self):
        self.assertEqual({key for key, _, _ in R.MAIN_ROWS}, set(R.MAIN_ACCEPT))

    def test_actions_name_known_functions_and_globals(self):
        for calls, values in R.MAIN_ACCEPT.values():
            for name in calls:
                self.assertIn(name, R.F)
            for name in values:
                self.assertIn(name, R.G)

    def test_submenu_tables_are_distinct(self):
        tables = list(R.SUBMENU_TABLE.values())
        self.assertEqual(len(tables), len(set(tables)))
        self.assertNotIn(R.SUB_LEAVING_OPTIONS, R.SUBMENU_TABLE)

    def test_no_save_row(self):
        keys = {key for key, _, _ in R.MAIN_ROWS + R.DEBUG_ROWS}
        self.assertNotIn("menu_savegame", keys)

    def test_leave_options_commits(self):
        for queried, edge, commit in R.LEAVE_OPTIONS:
            if commit is not None:
                self.assertEqual(commit[:2], (0, 0))
                self.assertIn(commit[2], (0, 1))

    def test_minimap_modes(self):
        self.assertEqual(set(R.MINIMAP_MODES), {1, 2})
        for modes in R.MINIMAP_MODES.values():
            self.assertEqual(set(modes), {0, 1, 2})
            scale, x, y, width, height = modes[0]
            self.assertEqual((x, y, width, height), (0.0, 0.0, 320.0, 224.0))  # centred
            self.assertEqual(modes[2][0], 0.0)                                  # hidden


if __name__ == "__main__":
    unittest.main()
