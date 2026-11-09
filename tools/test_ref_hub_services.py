"""Synthetic checks of tools/ref_hub_services.py (no game data needed)."""
import unittest

import ref_hub_services as R


def state(complete_through=0, k=None, raw_k=0, started_k=0):
    raw = [3] + [3 if n <= complete_through else 0 for n in R.MISSIONS]
    started = [0] * 13
    if k is not None:
        raw[k] = raw_k
        started[k] = started_k
    return raw, started


class TableShape(unittest.TestCase):
    def test_node_and_choice_counts(self):
        self.assertEqual(len(R.NODES[R.HUB]), 31)
        self.assertEqual(len(R.NODES[R.HUB2]), 26)
        self.assertEqual(sum(len(n[3]) for n in R.NODES[R.HUB]), 54)
        self.assertEqual(sum(len(n[3]) for n in R.NODES[R.HUB2]), 48)

    def test_every_dialog_action_has_an_effect(self):
        for hub in (R.HUB, R.HUB2):
            used = {c[4] for node in R.NODES[hub] for c in node[3] if c[4] is not None}
            self.assertEqual(used, set(R.ACTIONS[hub]))
            self.assertFalse(used & set(R.UNREFERENCED_WRITERS[hub]))

    def test_next_nodes_in_range(self):
        for hub in (R.HUB, R.HUB2):
            for node in R.NODES[hub]:
                for choice in node[3]:
                    self.assertTrue(choice[5] == -1 or 0 <= choice[5] < len(R.NODES[hub]))


class StartNodes(unittest.TestCase):
    def test_fresh_hub_offers_mission_one(self):
        raw, started = state()
        self.assertEqual(R.start_node(R.HUB, raw, started), 1)

    def test_pending_then_started(self):
        raw, started = state(0, 1, 1, 0)
        self.assertEqual(R.start_node(R.HUB, raw, started), 3)
        raw, started = state(0, 1, 1, 1)
        self.assertEqual(R.start_node(R.HUB, raw, started), 0)

    def test_hub2_intro_then_offer(self):
        raw, started = state(1)
        self.assertEqual(R.start_node(R.HUB2, raw, started, intro=0), 1)
        self.assertEqual(R.start_node(R.HUB2, raw, started, intro=1), 3)

    def test_hub2_intro_choice_depends_on_mission_one(self):
        raw, started = state(1)
        self.assertEqual(R.visible(R.HUB2, 1, raw, started), [1])
        raw[1] = 1
        self.assertEqual(R.visible(R.HUB2, 1, raw, started), [0])

    def test_missions_eight_and_nine_have_status_nodes_only(self):
        raw, started = state(7)
        self.assertEqual(R.start_node(R.HUB, raw, started), 21)
        for node in (21, 22):
            self.assertTrue(all(c[4] in (None, 0x1DF8) for c in R.NODES[R.HUB][node][3]))

    def test_all_complete_falls_back_to_node_zero(self):
        self.assertEqual(R.start_node(R.HUB, [3] * 13, [0] * 13), 0)


class EntryAndTravel(unittest.TestCase):
    def test_store_level(self):
        raw = [0] * 13
        self.assertEqual([R.store_level(c, raw) for c in (0, 1, 2, 8, 9, 12)], [0, 0, 1, 6, 7, 11])
        self.assertEqual(R.store_level(7, raw), 5)
        raw[8] = 1
        self.assertEqual(R.store_level(7, raw), 6)
        raw[9] = 1
        self.assertEqual(R.store_level(7, raw), 7)
        raw[9] = 3
        self.assertEqual(R.store_level(7, raw), 8)

    def test_key_reads_only_availability_for_mission_twelve(self):
        self.assertEqual(R.key_usable([3] * 13), 1)
        self.assertEqual(R.key_usable([3] * 12 + [0]), 0)
        raw = [3, 1] + [0] * 11
        self.assertEqual(R.key_usable(raw), 1)

    def test_use_trigger_warns_on_started_mission(self):
        raw, started = state(0, 1, 1, 1)
        self.assertTrue(R.use_trigger(raw, started)['warn'])
        raw, started = state(0, 1, 1, 0)
        self.assertEqual(R.use_trigger(raw, started, dialog_open=1),
                         {'warn': False, 'entrance': True, 'menu': False})

    def test_walk_in_once(self):
        raw, started = state(0, 1, 1, 0)
        self.assertEqual(R.walk_in(raw, started, fired=0), 1)
        self.assertEqual(R.walk_in(raw, started, fired=1), 0)

    def test_mana_and_first_mission(self):
        self.assertEqual(R.entry_mana(1, 3, 9), (0, 9))
        self.assertEqual(R.entry_mana(2, 3, 9), (2, 3))
        self.assertEqual(R.entry_first_mission(1, [1, 1], 2), (False, 1, False))
        self.assertEqual(R.entry_first_mission(1, [0, 1], 2), (True, 0, True))

    def test_dedupe(self):
        self.assertEqual(R.dedupe_removals([[0, 1, 2, 5]]), 2)


if __name__ == '__main__':
    unittest.main()
