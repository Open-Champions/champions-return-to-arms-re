"""Pure route-list vectors. Original calls live in difftest_mission2_compose."""
import unittest

import ref_mission2 as M
import ref_mission2_compose as C


class RouteList(unittest.TestCase):
    def test_resolver_requires_every_bit(self):
        for evil, decision, complete in (
                (0, 0, 0), (1, 0, 1), (1, 1, 0), (0, 1, 1), (1, 1, 1)):
            hub = 'hub2' if evil and decision and complete else 'hub'
            self.assertEqual(C.resolver_hub(evil, decision, complete), hub)

    def test_latch_keeps_the_previous_list(self):
        previous = ['keep', 'also']
        self.assertEqual(C.reset_destinations(1, previous, 'hub2'), previous)
        self.assertEqual(C.reset_destinations(0, previous, 'hub'), ['hub'])

    def test_a_registered_task_blocks_script_entry_at_counter_zero(self):
        self.assertFalse(C.scripts_admitted(True))
        self.assertTrue(C.scripts_admitted(False))

    def test_route_keeps_the_resolver_hub_ahead_of_the_four_levels(self):
        for hub in C.HUBS:
            self.assertEqual(C.route_list(hub, M.LEVELS), [hub, *M.LEVELS])

    def test_already_present_is_not_rewritten(self):
        self.assertEqual(C.add_current(['hub2', 'innovat1'], 'innovat1', 'hub'),
                         ['hub2', 'innovat1'])
        self.assertEqual(C.add_current(['hub2'], 'hub2', 'hub'), ['hub2'])

    def test_hub2_cold_dialog_follows_mission_2(self):
        self.assertEqual(C.hub2_cold_dialog(0), (1, 1))
        self.assertEqual(C.hub2_cold_dialog(2), (1, 1))
        self.assertEqual(C.hub2_cold_dialog(1), (4, 2))
        self.assertEqual(C.hub2_cold_dialog(3), (5, 2))

    def test_hub2_action_gate_is_an_open_incomplete_variable(self):
        clear = [0] * 12
        row = [3, 0, 1] + [0] * 10
        self.assertEqual(C.hub2_action_gate(row, clear), 0)
        set_second = clear[:]
        set_second[1] = 1
        self.assertEqual(C.hub2_action_gate(row, set_second), 1)
        complete = row[:]
        complete[2] = 3
        self.assertEqual(C.hub2_action_gate(complete, set_second), 0)
        last = [3] + [0] * 12
        last[12] = 1
        values = [0] * 12
        values[11] = 1
        self.assertEqual(C.hub2_action_gate(last, values), 1)

    def test_hub2_key_is_an_open_mission_or_mission_12(self):
        row = [3] + [0] * 12
        self.assertEqual(C.hub2_trigger_key(row), 0)
        row[2] = 1
        self.assertEqual(C.hub2_trigger_key(row), 1)
        row[2] = 3
        self.assertEqual(C.hub2_trigger_key(row), 0)
        row[2] = 2
        self.assertEqual(C.hub2_trigger_key(row), 0)
        row[12] = 3
        self.assertEqual(C.hub2_trigger_key(row), 1)
        self.assertEqual(C.hub2_trigger_key([3] * 13), 1)

    def test_new_arrival_drops_the_other_hub_and_appends(self):
        cases = (
            ('hub', [], 'hub2', []),
            ('hub', [], 'innovat1', ['innovat1']),
            ('hub', ['hub', 'hub2'], 'innovat1', ['hub', 'innovat1']),
            ('hub', ['hub2', 'hub'], 'inmine1', ['hub', 'inmine1']),
            ('hub', ['innovat1', 'hub2', 'hub'], 'innovat2', ['innovat1', 'hub', 'innovat2']),
            ('hub', ['hub2'], 'hub', ['hub']),
            ('hub2', [], 'hub', []),
            ('hub2', ['hub', 'hub2'], 'innovat1', ['hub2', 'innovat1']),
            ('hub2', ['hub2', 'hub'], 'inmine1', ['hub2', 'inmine1']),
            ('hub2', ['innovat2', 'hub'], 'hub2', ['innovat2', 'hub2']),
        )
        for hub, start, current, expected in cases:
            self.assertEqual(C.add_current(start, current, hub), expected, (hub, start, current))


if __name__ == '__main__':
    unittest.main()
