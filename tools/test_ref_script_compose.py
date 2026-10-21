#!/usr/bin/env python3
"""test_ref_script_compose.py - the 191-command composition table is complete."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_natives as N                         # noqa: E402
import ref_script_compose as C                  # noqa: E402


class CompositionContract(unittest.TestCase):
    def test_every_table_name_once(self):
        rows = C.commands()
        self.assertEqual([row['name'] for row in rows], list(N.NATIVE_NAMES))
        self.assertEqual(len(rows), 191)

    def test_published_census(self):
        counts = C.published_counts()
        self.assertEqual(set(counts), set(N.NATIVE_NAMES))
        self.assertEqual(sum(calls for calls, _levels in counts.values()), 5660)
        self.assertEqual(sum(1 for calls, _levels in counts.values() if calls), 122)
        self.assertEqual(sum(1 for calls, _levels in counts.values() if calls == 0), 69)

    def test_rank_puts_unused_last(self):
        order = C.ranked()
        self.assertEqual(order[0][2]['name'], 'getv')
        self.assertGreater(order[0][1], 0)
        self.assertEqual(order[-1][1], 0)
        self.assertEqual(len(order), 191)

    def test_status_and_subsystem_vocabulary(self):
        for row in C.commands():
            self.assertIn(row['status'], C.STATUSES)
            self.assertIn(row['subsystem'], C.SUBSYSTEMS)
            self.assertTrue(row['native'])
            self.assertTrue(row['seam'])

    def test_document_names_every_command(self):
        path = os.path.join(os.path.dirname(__file__), '..', 'docs', 'script-composition.md')
        with open(path, 'r', encoding='utf-8') as source:
            text = source.read()
        for name in N.NATIVE_NAMES:
            self.assertIn('`%s`' % name, text)
        self.assertIn('81 documented (3,883 calls)', text)
        self.assertIn('70 partly documented (1,184 calls)', text)
        self.assertIn('40 unknown (593 calls)', text)


if __name__ == '__main__':
    unittest.main()
