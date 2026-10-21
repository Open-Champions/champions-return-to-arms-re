#!/usr/bin/env python3
"""Synthetic tests of tools/probe_full_placement.py: its tables and its bookkeeping.
No game file is needed; the probe itself is run by hand (docs/spec/full-placement.md)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import probe_full_placement as P                # noqa: E402


class Tables(unittest.TestCase):
    def test_placements_are_the_native_fixture(self):
        self.assertEqual(P.PLACEMENTS['round5'], {'antqueen': (0, 140), 'skeleton': (70, 140),
                                                  'soul': (-70, 140)})
        self.assertEqual(P.PLACEMENTS['native']['soul'], (-60, 100))
        self.assertEqual(P.SKELIGHTS, (((80, 0), 0x8000), ((-40, 0), 0)))
        self.assertEqual((P.FACING, P.HP), (0xC000, 120.0))

    def test_service_recorded_and_unexecuted_are_disjoint(self):
        self.assertFalse(P.SERVICES & P.RECORDED)
        for name in ('Creature.v20', 'Creature.v0', 'Skeleton_shatter', 'AntQueen_pickFlyDest',
                     'GutChunk_ctor', 'Creature_setCharm', 'Holder.v2', 'Holder.v3', 'Holder.v4'):
            self.assertNotIn(name, P.SERVICES)
            self.assertNotIn(name, P.RECORDED)

    def test_executed_bodies_hold_the_known_entries(self):
        ex = P.executed_bodies()
        for addr in (0x119328, 0x10DED0, 0x236C70, 0x237918, 0x2A5AF4, 0x2A7768, 0x2A9478, 0x1E8230):
            self.assertTrue(addr in ex, hex(addr))
        for addr in RC_RUNS:
            self.assertIn(addr, P.RUN_SWITCHES_ENTRIES)

    def test_run_states_executed_before_this_round(self):
        self.assertTrue({0, 1} <= P.RUN_STATES_EXECUTED['Skeleton_run'])
        self.assertEqual(P.RUN_STATES_EXECUTED['AntQueen_run'], set(range(0x1A)))
        self.assertEqual(P.RUN_STATES_EXECUTED['Soul_run'], set())


RC_RUNS = (0x236F78, 0x2A6864, 0x2A9870)
P.RUN_SWITCHES_ENTRIES = {entry for entry, _test in P.RUN_SWITCHES.values()}


class Bookkeeping(unittest.TestCase):
    def _probe(self, stop_first):
        probe = P.Probe.__new__(P.Probe)
        probe.stop_first, probe.first_seen, probe.events, probe.tick = stop_first, {}, [], 5
        return probe

    def test_first_unexecuted_stops(self):
        probe = self._probe(True)
        probe.note_stub('anim_push', probe.classify_name('anim_push'), ())
        probe.note_stub('Holder.v21', probe.classify_name('Holder.v21'), ())
        with self.assertRaises(P.Stop):
            probe.note_stub('Skeleton_shatter', probe.classify_name('Skeleton_shatter'), ())
        self.assertEqual(probe.first_seen['anim_push'], (5, 'service'))
        self.assertEqual(probe.first_seen['Holder.v21'], (5, 'recorded'))
        self.assertEqual(probe.events, [(5, 'Skeleton_shatter')])

    def test_all_mode_keeps_going_and_keeps_the_first_tick(self):
        probe = self._probe(False)
        probe.note_stub('Creature.v20', 'unexecuted', ())
        probe.tick = 9
        probe.note_stub('Creature.v20', 'unexecuted', ())
        self.assertEqual(probe.first_seen['Creature.v20'], (5, 'unexecuted'))
        self.assertEqual(len(probe.events), 2)

    def test_pcs_map_to_their_function(self):
        probe = self._probe(False)
        probe.starts = [0x100000, 0x100100, 0x100200]
        self.assertEqual(probe._functions_run({0x100004, 0x1000FC, 0x100100, 0x100250}),
                         {0x100000, 0x100100, 0x100200})


if __name__ == '__main__':
    unittest.main()
