#!/usr/bin/env python3
"""Unit tests for the inventory carry-over helpers in ref_quests.

No executable. Preload the standard-library dis module before discover,
because tools/dis.py shadows it:

  python3 -c 'import dis,unittest,sys; sys.path.insert(0,"tools"); \
r=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromName("test_ref_inventory_reset")); \
sys.exit(0 if r.wasSuccessful() else 1)'
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_quests as Q

BIT = 1 << 39


def item(name, flags, stack=1, equip=0, stamp=0):
    return Q.BagItem(name, flags, stack, equip, stamp)


def equip_names(record):
    names = []
    for slot, pointed in enumerate(record.equip):
        if pointed is not None:
            names.append((slot, pointed.name))
    return names


class RemoveFixups(unittest.TestCase):
    def test_slide_repoints_the_tail_and_clears_the_named_slot(self):
        record = Q.ItemRecord()
        first = item('questgem', BIT, equip=0, stamp=0)
        second = item('sword', 0, equip=2, stamp=1)
        record.bags[0] = [first, second]
        record.equip[0] = first
        record.equip[2] = second
        record.weapons[0] = first
        record.weapons[1] = second
        record.second = second
        Q.remove_bag_item(record, 0, 0)
        self.assertEqual([entry.name for entry in record.bags[0]], ['sword'])
        self.assertEqual(second.stamp, 0)
        self.assertEqual(equip_names(record), [(2, 'sword')])
        self.assertIsNone(record.weapons[0])
        self.assertIs(record.weapons[1], second)
        self.assertIs(record.second, second)
        self.assertEqual(record.weapon_class, 5)

    def test_inactive_weapon_word_does_not_change_the_class(self):
        record = Q.ItemRecord()
        held = item('sword', 0, equip=0, stamp=0)
        record.bags[0] = [held]
        record.weapons[0] = held
        record.active = 1
        record.weapon_class = 2
        Q.remove_bag_item(record, 0, 0)
        self.assertEqual(record.weapon_class, 2)
        self.assertIsNone(record.weapons[0])

    def test_ring_pair_clears_only_the_cell_that_names_the_item(self):
        record = Q.ItemRecord()
        left = item('ringa', 0, equip=5, stamp=0)
        right = item('ringb', 0, equip=6, stamp=1)
        record.bags[0] = [left, right]
        record.equip[5] = left
        record.equip[6] = right
        Q.remove_bag_item(record, 0, 0)
        self.assertIsNone(record.equip[5])
        self.assertIs(record.equip[6], right)
        self.assertEqual(right.stamp, 0)

    def test_flag39_walk_matches_the_name_filter_and_fixes_pointers(self):
        record = Q.ItemRecord()
        drop = item('questgem', BIT, equip=0, stamp=0)
        keep = item('pickaxe', BIT, equip=0, stamp=1)
        plain = item('sword', 0, equip=2, stamp=2)
        record.bags[0] = [drop, plain]
        record.bags[2] = [keep]
        record.equip[0] = drop
        record.equip[2] = plain
        record.weapons[1] = plain
        Q.drop_unkept_flag39(record)
        self.assertEqual([entry.name for entry in record.bags[0]], ['sword'])
        self.assertEqual([entry.name for entry in record.bags[2]], ['pickaxe'])
        self.assertEqual(plain.stamp, 1)
        self.assertEqual(equip_names(record), [(2, 'sword')])
        self.assertIs(record.weapons[1], plain)
        self.assertEqual(record.weapon_class, 0)


class ShareAndWipe(unittest.TestCase):
    def test_share_copies_bag2_flag39_and_drops_the_other_slots_copies(self):
        source = Q.ItemRecord()
        other = Q.ItemRecord()
        untouched = Q.ItemRecord()
        source.bags[0] = [item('bag0', BIT)]
        source.bags[2] = [item('sword', 0, stamp=0), item('questgem', BIT, stack=4, stamp=1)]
        other.bags[0] = [item('keepbag0', BIT)]
        other.bags[1] = [item('keepbag1', BIT)]
        other.bags[2] = [item('plain', 0, stamp=0), item('oldquest', BIT, stamp=1)]
        other.equip[0] = other.bags[2][1]
        untouched.bags[2] = [item('canary', BIT)]
        Q.share_bag2_quest_items([source, other, untouched], 0, 2)
        self.assertEqual([entry.name for entry in source.bags[2]], ['sword', 'questgem'])
        self.assertEqual([entry.name for entry in other.bags[0]], ['keepbag0'])
        self.assertEqual([entry.name for entry in other.bags[1]], ['keepbag1'])
        self.assertEqual([(entry.name, entry.stack, entry.stamp) for entry in other.bags[2]],
                         [('plain', 1, 0), ('questgem', 4, 1)])
        self.assertIsNone(other.equip[0])
        self.assertEqual([entry.name for entry in untouched.bags[2]], ['canary'])

    def test_empty_source_still_drops_the_other_bag2_flag(self):
        source = Q.ItemRecord()
        other = Q.ItemRecord()
        other.bags[2] = [item('oldquest', BIT), item('plain', 0)]
        Q.share_bag2_quest_items([source, other], 0, 2)
        self.assertEqual([entry.name for entry in other.bags[2]], ['plain'])

    def test_bit38_is_not_shared(self):
        source = Q.ItemRecord()
        other = Q.ItemRecord()
        source.bags[2] = [item('questgem', 1 << 38)]
        Q.share_bag2_quest_items([source, other], 0, 2)
        self.assertEqual(other.bags[2], [])

    def test_source_slot_sends_to_the_other_slots_only(self):
        records = [Q.ItemRecord(), Q.ItemRecord(), Q.ItemRecord()]
        records[1].bags[2] = [item('pickaxe', BIT, stack=2)]
        Q.share_bag2_quest_items(records, 1, 3)
        self.assertEqual([entry.name for entry in records[0].bags[2]], ['pickaxe'])
        self.assertEqual([entry.stack for entry in records[1].bags[2]], [2])
        self.assertEqual([entry.name for entry in records[2].bags[2]], ['pickaxe'])

    def test_remove_all_takes_the_first_cell_of_each_nonempty_bag(self):
        record = Q.ItemRecord()
        weapon = item('sword', 0, equip=0)
        shield = item('shield', 0, equip=3, stamp=1)
        quest = item('questgem', BIT, equip=5)
        record.bags[0] = [weapon, shield]
        record.bags[1] = [quest]
        record.bags[2] = [item('potion', 0)]
        record.equip[0] = weapon
        record.equip[3] = shield
        record.equip[5] = quest
        record.weapons[0] = weapon
        Q.remove_all_bag_items(record)
        self.assertEqual([entry.name for entry in record.bags[0]], ['shield'])
        self.assertEqual(shield.stamp, 0)
        self.assertEqual(record.bags[1], [])
        self.assertEqual(record.bags[2], [])
        self.assertEqual(equip_names(record), [(3, 'shield')])
        self.assertIsNone(record.weapons[0])
        self.assertEqual(record.weapon_class, 5)

    def test_bag0_count_of_three_keeps_the_second_cell(self):
        record = Q.ItemRecord()
        weapon = item('sword', 0, equip=0)
        shield = item('shield', 0, equip=3, stamp=1)
        gem = item('gem', 0, equip=1, stamp=2)
        record.bags[0] = [weapon, shield, gem]
        record.bags[1] = [item('questgem', BIT, equip=5)]
        record.bags[2] = [item('potion', 0)]
        record.equip[0] = weapon
        record.equip[1] = gem
        record.equip[3] = shield
        record.equip[5] = record.bags[1][0]
        record.weapons[0] = weapon
        Q.remove_all_bag_items(record)
        self.assertEqual([entry.name for entry in record.bags[0]], ['shield'])
        self.assertEqual(shield.stamp, 0)
        self.assertEqual(record.bags[1], [])
        self.assertEqual(record.bags[2], [])
        self.assertEqual(equip_names(record), [(3, 'shield')])
        self.assertIsNone(record.weapons[0])
        self.assertEqual(record.weapon_class, 5)

    def test_later_bags_lose_every_cell_when_each_holds_two(self):
        record = Q.ItemRecord()
        record.bags[0] = [item('a', 0), item('b', 0), item('c', 0)]
        record.bags[1] = [item('d', 0), item('e', 0)]
        record.bags[2] = [item('f', 0), item('g', 0)]
        Q.remove_all_bag_items(record)
        self.assertEqual([entry.name for entry in record.bags[0]], ['b'])
        self.assertEqual(record.bags[1], [])
        self.assertEqual(record.bags[2], [])


class CleanupGate(unittest.TestCase):
    def test_gate(self):
        self.assertTrue(Q.cleanup_runs(1, 0, 0, 0))
        self.assertFalse(Q.cleanup_runs(0, 0, 0, 0))
        self.assertFalse(Q.cleanup_runs(1, 1, 0, 0))
        self.assertFalse(Q.cleanup_runs(1, 0, 1, 0))
        self.assertFalse(Q.cleanup_runs(1, 0, 0, 1))


if __name__ == '__main__':
    unittest.main()
