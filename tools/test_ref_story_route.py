#!/usr/bin/env python3
"""Model checks for the ordered story menu. No executable."""
import unittest

import ref_story_route as R


class StoryBeatModel(unittest.TestCase):
    def test_opening_row_ignores_mission_zero(self):
        self.assertEqual(R.opening_row(set()), 0)
        self.assertEqual(R.opening_row({0}), 0)
        self.assertEqual(R.opening_row({0, 1}), 0)
        self.assertEqual(R.opening_row({1, 5}), 4)
        self.assertEqual(R.opening_row({1, 3}), 2)
        self.assertEqual(R.opening_row({12}), 11)

    def test_mission_bits_keep_the_other_bit(self):
        self.assertEqual(R.available_byte(0xA0, 1), 0xA1)
        self.assertEqual(R.available_byte(0xA3, 0), 0xA2)
        self.assertEqual(R.complete_byte(0xA0, -1), 0xA2)
        self.assertEqual(R.complete_byte(0xA1, -1), 0xA3)
        self.assertEqual(R.complete_byte(0xA3, 0), 0xA1)

    def test_story_level_uses_evil_only_when_named(self):
        self.assertEqual(R.story_level('story', 'evil', False), 'story')
        self.assertEqual(R.story_level('story', 'evil', True), 'evil')
        self.assertEqual(R.story_level('story', '', True), 'story')

    def test_hub_needs_completion_and_both_bits(self):
        self.assertEqual(R.hub_name(0, 0, 0, 0), 'hub')
        self.assertEqual(R.hub_name(1, 1, 1, 0), 'hub')
        self.assertEqual(R.hub_name(1, 0, 3, 0), 'hub')
        self.assertEqual(R.hub_name(0, 1, 3, 0), 'hub')
        self.assertEqual(R.hub_name(1, 1, 3, 0), 'hub2')
        self.assertEqual(R.hub_name(1, 1, 2, 0), 'hub2')
        self.assertEqual(R.hub_name(2, 2, 3, 0), 'hub')
        self.assertEqual(R.hub_name(2, 2, 3, 1), 'hub2')

    def test_find_act_is_current_first_prefix(self):
        acts = [['hub', 'blood1'], ['hub', 'later']]
        self.assertEqual(R.find_act('blood1', -1, acts), 0)
        self.assertEqual(R.find_act('blood1_extra', 0, acts), 0)
        self.assertEqual(R.find_act('later', 0, acts), 1)
        self.assertEqual(R.find_act('hub2', -1, acts), 0)
        self.assertEqual(R.find_act('hub2', 1, acts), 1)
        self.assertEqual(R.find_act('missing', 0, acts), -1)
        self.assertEqual(R.act_changed('later', 0, acts), (1, 1))
        self.assertEqual(R.act_changed('blood1', 0, acts), (0, 0))
        self.assertEqual(R.act_changed('missing', 0, acts), (0, 0))

    def test_campaign_tick_down_does_not_skip_a_locked_mission(self):
        rows = [('s%d' % i, '') for i in range(12)]
        state = R.new_menu()
        for _ in range(17):
            R.campaign_tick(state, 0, {1, 3}, rows, False)
        self.assertEqual((state['phase'], state['row']), (2, 2))
        R.campaign_tick(state, R.BTN_UP, {1, 3}, rows, False)
        self.assertEqual(state['row'], 1)
        R.campaign_tick(state, R.BTN_UP, {1, 3}, rows, False)
        self.assertEqual(state['row'], 0)
        R.campaign_tick(state, R.BTN_DOWN, {1, 3}, rows, False)
        self.assertEqual(state['row'], 0)
        state['row'] = 1
        R.campaign_tick(state, R.BTN_DOWN, {1, 3}, rows, False)
        self.assertEqual(state['row'], 2)

    def test_offering_the_next_mission_moves_only_on_down_or_reopen(self):
        rows = [('s%d' % i, 'e%d' % i) for i in range(12)]
        state = R.new_menu()
        available = {1}
        for _ in range(17):
            R.campaign_tick(state, 0, available, rows, False)
        self.assertEqual(state['row'], 0)
        available.add(2)
        R.campaign_tick(state, 0, available, rows, False)
        self.assertEqual(state['row'], 0)
        R.campaign_tick(state, R.BTN_DOWN, available, rows, False)
        self.assertEqual(state['row'], 1)
        R.campaign_tick(state, R.BTN_CROSS, available, rows, True, 0)
        R.campaign_tick(state, 0, available, rows, True, 0)
        R.campaign_tick(state, 0, available, rows, True, 128)
        R.campaign_tick(state, 0, available, rows, True, 128)
        R.campaign_tick(state, 0, available, rows, True, 128)
        self.assertEqual(state['pending'], 'e1')
        self.assertEqual(state['orient'], 0xff)

    def test_completion_does_not_block_the_story_column(self):
        rows = [('first', '')] + [('', '')] * 11
        state = R.new_menu()
        for _ in range(17):
            R.campaign_tick(state, 0, {1}, rows, False)
        R.campaign_tick(state, R.BTN_CROSS, {1}, rows, False)
        for fade in (0, 0, 128, 128, 128):
            R.campaign_tick(state, 0, {1}, rows, False, fade)
        self.assertEqual(state['pending'], 'first')

    def test_row_zero_story_confirm_does_not_read_the_available_bit(self):
        rows = [('first', '')] + [('', '')] * 11
        state = R.new_menu()
        for _ in range(17):
            R.campaign_tick(state, 0, set(), rows, False)
        R.campaign_tick(state, R.BTN_CROSS, set(), rows, False)
        self.assertEqual(state['phase'], 5)
        self.assertFalse(R.story_column_open(1, set()))
        self.assertTrue(R.story_column_open(1, {2}))

    def test_fresh_menu_tick_is_unchanged(self):
        state = R.new_menu()
        R.menu_tick(state, 0, True, 'blood1', 0)
        self.assertEqual(state['row'], 0)
        self.assertEqual(state['phase'], 1)


if __name__ == '__main__':
    unittest.main()
