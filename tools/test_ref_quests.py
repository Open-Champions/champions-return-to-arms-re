#!/usr/bin/env python3
"""Unit tests of tools/ref_quests.py. No game files.

tools/dis.py shadows the standard-library dis module, so discover has to load
that module first:

  python3 -c "import dis,sys; sys.path.append('tools'); import unittest; \
r=unittest.TextTestRunner().run(unittest.defaultTestLoader.discover('tools', pattern='test_ref_quests.py')); \
sys.exit(0 if r.wasSuccessful() else 1)"
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_quests as Q


def _table():
    # Leave level n once experience reaches 100*n. The last entry is the cap plus one.
    table = [100 * i for i in range(80)]
    table.append(10000)
    return table


def _rows():
    rows = []
    for i in range(13):
        rows.append(Q.MissionRow('s%d' % i, '', 'm%d' % i, 'b%d' % i, 1, 1, 1))
    rows[2] = Q.MissionRow('s2', '', '', '', 0, 0, 0)
    rows[5] = Q.MissionRow('s5', 'e5', 'm5', 'b5', 1, 1, 1)
    return rows


class Experience(unittest.TestCase):
    def test_bands_and_the_cap(self):
        table = _table()
        level, exp, skill, stat, hp, mana, n = Q.give_exp(1, 0, 0, 0, 4.0, 9.0, 1.0, 3.0, 10, table)
        self.assertEqual((level, exp, skill, stat, n), (1, 10, 0, 0, 0))
        self.assertEqual(hp, 4.0)
        level, exp, skill, stat, hp, mana, n = Q.give_exp(5, 499, 0, 0, 4.0, 9.0, 1.0, 3.0, 1, table)
        self.assertEqual((level, skill, stat, n), (6, 1, 3, 1))
        self.assertEqual((hp, mana), (9.0, 3.0))
        level, exp, skill, stat, hp, mana, n = Q.give_exp(15, 1499, 0, 0, 4.0, 9.0, 1.0, 3.0, 1, table)
        self.assertEqual((level, skill), (16, 2))
        level, exp, skill, stat, hp, mana, n = Q.give_exp(35, 3499, 0, 0, 0.0, 9.0, 1.0, 3.0, 1, table)
        self.assertEqual((level, skill, hp, mana), (36, 4, 0.0, 1.0))
        level, exp, skill, stat, hp, mana, n = Q.give_exp(36, 3599, 0, 0, 4.0, 9.0, 1.0, 3.0, 1, table)
        self.assertEqual(skill, 5)
        level, exp, skill, stat, hp, mana, n = Q.give_exp(79, 7900, 0, 250, 4.0, 9.0, 1.0, 3.0, 10 ** 9, table)
        self.assertEqual(exp, 9999)
        self.assertEqual(stat, (250 + 3) & 0xFF)
        level, exp, skill, stat, hp, mana, n = Q.give_exp(80, 9999, 7, 4, 4.0, 9.0, 1.0, 3.0, 100, table)
        self.assertEqual((level, exp, skill, stat, n), (80, 9999, 7, 4, 0))


class HubAndActs(unittest.TestCase):
    def test_hub_needs_both_bits_and_a_completed_mission(self):
        self.assertEqual(Q.hub_name(0, 0, 0, 1), 'hub')
        self.assertEqual(Q.hub_name(2, 0, 2, 1), 'hub')
        self.assertEqual(Q.hub_name(2, 2, 1, 1), 'hub')
        self.assertEqual(Q.hub_name(2, 2, 2, 1), 'hub2')
        self.assertEqual(Q.hub_name(2, 2, 3, 1), 'hub2')
        self.assertEqual(Q.hub_name(1, 1, 2, 1), 'hub')
        self.assertEqual(Q.hub_name(4, 4, 2, 2), 'hub2')

    def test_prefix_and_the_current_act(self):
        acts = [['hub', 'blood1'], ['hub', 'innovat1'], ['hub'], ['hub', 'fire1']]
        self.assertEqual(Q.find_act('blood1', 0, acts), 0)
        self.assertEqual(Q.find_act('blood1_x', 0, acts), 0)
        self.assertEqual(Q.find_act('blood', 0, acts), -1)
        self.assertEqual(Q.find_act('fire1', 0, acts), 3)
        self.assertEqual(Q.find_act('fire', 0, acts), -1)
        self.assertEqual(Q.find_act('hub2', 0, acts), 0)
        self.assertEqual(Q.find_act('hub2', 3, acts), 3)
        self.assertEqual(Q.find_act('fire1', -1, acts), 3)
        self.assertEqual(Q.find_act('HUB', 0, acts), -1)
        self.assertEqual(Q.act_changed('fire1', 0, acts), (1, 3))
        self.assertEqual(Q.act_changed('fire1', 3, acts), (0, 3))
        self.assertEqual(Q.act_changed('nope', 3, acts), (0, 3))
        self.assertEqual(Q.act_changed('fire1', -1, acts), (1, 3))


class QuestItems(unittest.TestCase):
    def test_keep_list_and_the_placeholder(self):
        self.assertTrue(Q.quest_item_kept('bloodstonefay'))
        self.assertTrue(Q.quest_item_kept('xxshardofyy'))
        self.assertTrue(Q.quest_item_kept('pickaxe'))
        self.assertFalse(Q.quest_item_kept('pickaxe2'))
        self.assertFalse(Q.quest_item_kept('Bloodstone'))
        self.assertFalse(Q.quest_item_kept('zzzz'))
        bit = 1 << 39
        items = [('zzzz', bit), ('pickaxe', bit), ('zzzz', 0), ('sword', 1 << 38)]
        self.assertEqual([n for n, _f in Q.flag39_remaining(items)], ['pickaxe', 'zzzz', 'sword'])
        title = b'ABCDEFGHIJKLMNOPQRSTUV' + bytes(10)
        entries = [(title, b'body' + bytes(28))] + [(b'later' + bytes(27), bytes(32))] * 7
        cleared, count = Q.clear_quest_list(entries, 1)
        self.assertEqual(count, 0)
        self.assertTrue(cleared[0][0].startswith(b'NoQuests\0'))
        self.assertEqual(cleared[0][0][9:14], b'JKLMN')
        self.assertTrue(cleared[1][0].startswith(b'later'))


class Menu(unittest.TestCase):
    def setUp(self):
        self.world = Q.CampaignView(_rows(), available={1, 5}, complete={5}, medals={5: 3})
        self.state = Q.new_menu()

    def test_intro_lands_on_the_highest_row(self):
        for _ in range(17):
            Q.menu_tick(self.state, 0, self.world)
        self.assertEqual(self.state['state'], 2)
        self.assertEqual(self.state['row'], 4)
        self.assertEqual(self.state['counter'], 127)
        self.assertEqual(self.state['mark'], 0)
        self.assertEqual(self.state['paused'], 1)
        Q.menu_tick(self.state, 0, self.world)
        self.assertEqual(self.state['mark'], 8)
        self.assertEqual(Q.initial_row({0}), 0)
        self.assertEqual(Q.initial_row(set()), 0)
        self.assertEqual(Q.initial_row({2, 3, 11}), 10)

    def test_movement_and_launch(self):
        for _ in range(18):
            Q.menu_tick(self.state, 0, self.world)
        # Row 4 is even, so the left button walks toward the side columns.
        self.state['row'] = 4
        self.state['col'] = 0
        Q.menu_tick(self.state, Q.BTN_LEFT, self.world)
        self.assertEqual(self.state['col'], 1)
        Q.menu_tick(self.state, Q.BTN_LEFT, self.world)
        self.assertEqual(self.state['col'], 2)
        Q.menu_tick(self.state, Q.BTN_RIGHT, self.world)
        self.assertEqual(self.state['col'], 1)
        self.state['col'] = 2
        self.world.complete_set.clear()
        Q.menu_tick(self.state, Q.BTN_RIGHT, self.world)
        self.assertEqual(self.state['col'], 0)
        self.state['row'] = 5
        self.state['col'] = 0
        self.world.available_set.add(6)
        self.world.complete_set.add(6)
        Q.menu_tick(self.state, Q.BTN_RIGHT, self.world)
        self.assertEqual(self.state['col'], 1)
        self.state['row'] = 2
        Q.menu_tick(self.state, Q.BTN_UP, self.world)
        self.assertEqual(self.state['row'], 1)
        Q.menu_tick(self.state, Q.BTN_DOWN, self.world)
        self.assertEqual(self.state['row'], 1)
        self.state['row'] = 0
        self.state['col'] = 0
        Q.menu_tick(self.state, Q.BTN_CROSS, self.world)
        self.assertEqual(self.state['state'], 5)
        Q.menu_tick(self.state, 0, self.world)
        self.assertEqual(self.state['state'], 6)
        Q.menu_tick(self.state, 0, self.world)
        Q.menu_tick(self.state, 0, self.world)
        self.assertEqual(self.state['state'], 6)
        self.world.fade = 128
        Q.menu_tick(self.state, 0, self.world)
        self.assertEqual(self.state['state'], 7)
        Q.menu_tick(self.state, 0, self.world)
        self.assertEqual(self.state['state'], 8)
        self.assertEqual(self.state['pending'], '')
        Q.menu_tick(self.state, 0, self.world)
        self.assertEqual(self.state['pending'], 's0')
        self.assertEqual(self.state['orient'], 0xFF)

    def test_helpers_follow_the_flag_words(self):
        row = Q.MissionRow('s', 'e', 'm', 'b', 1, 1, 1)
        self.assertEqual([Q.helper_value(i, row, True, True, 3) for i in range(12)], [1] * 12)
        row.flag24 = 0
        self.assertEqual(Q.helper_value(6, row, True, True, 3), 0)
        self.assertEqual(Q.helper_value(7, row, True, True, 3), 1)
        self.assertEqual(Q.helper_value(3, row, True, True, 3), 0)
        row.medal = ''
        self.assertEqual(Q.helper_value(7, row, True, True, 3), 0)
        self.assertEqual(Q.helper_value(8, row, True, True, 3), 1)
        row.flag28 = 0
        self.assertEqual(Q.helper_value(11, row, True, True, 3), 0)


if __name__ == '__main__':
    unittest.main()
