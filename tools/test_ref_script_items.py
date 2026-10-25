#!/usr/bin/env python3
"""Synthetic tests of tools/ref_script_items.py.  No game file is needed: every record,
definition and name below is made up here."""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_items as I           # noqa: E402
import ref_natives as N         # noqa: E402
import ref_script_items as R    # noqa: E402

DEFS = 0x01000000               # made-up definition rows of 0x40 bytes
NAMES = 0x01001000


class World:
    def __init__(self):
        self.mem = N.Mem()
        self.names = {}
        self.next_name = NAMES
        self.next_def = DEFS

    def definition(self, name, slot=0, category=0, flags=0):
        at = self.next_name
        self.mem.write(at, name + b'\0')
        self.next_name += len(name) + 1
        d = self.next_def
        self.next_def += 0x40
        self.mem.w32(d, at)
        self.mem.w8(d + 0x1C, slot)
        self.mem.w8(d + 0x1D, category)
        self.mem.w64(d + 0x28, flags)
        return d

    def put(self, slot, bag, definition, count=1):
        at = R.bag_count_at(slot, bag)
        i = self.mem.s32(at)
        entry = R.bag_entry(slot, bag, i)
        self.mem.w32(entry, definition)
        self.mem.w16(entry + 4, count)
        self.mem.w32(at, i + 1)
        return entry


class Counts(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.sword = self.w.definition(b'Sword')
        self.key = self.w.definition(b'Key of Ash', category=2)
        self.empty = self.w.definition(b'')

    def test_count_sums_stacks_in_every_bag(self):
        self.w.put(0, 0, self.sword, 1)
        self.w.put(0, 2, self.sword, 4)
        self.w.put(0, 1, self.key, 3)
        self.assertEqual(R.count_item_by_name(self.w.mem, b'Sword', 0), 5)
        self.assertEqual(R.count_item_by_name(self.w.mem, b'Key of Ash', 0), 3)

    def test_count_is_case_sensitive_and_exact(self):
        self.w.put(1, 0, self.sword, 2)
        self.assertEqual(R.count_item_by_name(self.w.mem, b'sword', 1), 0)
        self.assertEqual(R.count_item_by_name(self.w.mem, b'Swor', 1), 0)
        self.assertEqual(R.count_item_by_name(self.w.mem, b'Sword', 0), 0)

    def test_count_adds_signed_stack_counts(self):
        self.w.put(0, 0, self.sword, -3)
        self.w.put(0, 0, self.sword, 1)
        self.assertEqual(R.count_item_by_name(self.w.mem, b'Sword', 0), -2)

    def test_find_last_match_wins_and_name_inside_text(self):
        self.w.put(0, 0, self.sword)
        self.w.put(0, 0, self.sword)
        self.w.put(0, 2, self.key)
        self.assertEqual(R.find_item_by_substring(self.w.mem, 0, b'give back the Sword now'), (1, 0))
        self.assertEqual(R.find_item_by_substring(self.w.mem, 0, b'Sword, Key of Ash'), (0, 2))
        self.assertEqual(R.find_item_by_substring(self.w.mem, 0, b'Swor'), (-1, None))

    def test_find_empty_name_matches_anything(self):
        self.w.put(0, 1, self.empty)
        self.assertEqual(R.find_item_by_substring(self.w.mem, 0, b'whatever'), (0, 1))


class Ranks(unittest.TestCase):
    def setUp(self):
        self.mem = N.Mem()

    def test_skill_rank_list_ends_at_minus_one(self):
        r = R.rec(0)
        self.mem.w16(r + R.P_SKILL_PAIRS, 0x49)
        self.mem.w16(r + R.P_SKILL_PAIRS + 2, 7)
        self.mem.w16(r + R.P_SKILL_PAIRS + 4, 0xFFFF)
        self.mem.w16(r + R.P_SKILL_PAIRS + 8, 0x4A)
        self.mem.w16(r + R.P_SKILL_PAIRS + 10, 3)
        self.assertEqual(R.skill_rank(self.mem, 0, 0x49), 7)
        self.assertEqual(R.skill_rank(self.mem, 0, 0x4A), 0)

    def test_skill_rank_after_clear_all_skills_is_zero(self):
        r = R.rec(2)
        self.mem.w8(R.G_MEDAL_PLAYER, 2)
        for k in range(48):
            self.mem.w16(r + R.P_SKILL_PAIRS + 4 * k, 0x49)
            self.mem.w16(r + R.P_SKILL_PAIRS + 4 * k + 2, 9)
        R.clear_all_skills(self.mem)
        self.assertEqual(R.skill_rank(self.mem, 2, 0x49), 0)

    def test_passive_level_class_table_and_slot_limit(self):
        r = R.rec(1)
        self.mem.w32(r + R.P_CLASS, 3)
        table = R.G_CLASS_SKILLS + 3 * R.CLASS_SKILLS_SIZE
        self.mem.w64(table + 5 * R.CLASS_SKILL_ROW, 0x40)
        self.mem.w8(r + R.P_PASSIVES + 5, 4)
        self.assertEqual(R.passive_level(self.mem, 1, 0x40), 4)
        self.mem.w8(r + R.P_PASSIVES + 5, 0xF0)
        self.assertEqual(R.passive_level(self.mem, 1, 0x40), 0)
        self.assertEqual(R.passive_level(self.mem, 5, 0x40), 0)
        self.assertEqual(R.passive_level(self.mem, 1, 0x80), 0)


class Limit(unittest.TestCase):
    def test_base_and_passive(self):
        self.assertEqual(R.load_limit(46, 0, 0), I.f_bits(171.0))
        self.assertEqual(R.load_limit(46, 2, 0), I.f_bits(201.0))

    def test_bonus_word_and_cap(self):
        self.assertEqual(R.load_limit(46, 0, 1), I.f_bits(5171.0))
        self.assertEqual(R.load_limit(46, 0, -1), I.f_bits(5171.0))
        self.assertEqual(R.load_limit(9000, 0, 1), R.F_9999)
        self.assertEqual(R.load_limit(9874, 0, 0), I.f_bits(9999.0))

    def test_negative_strength(self):
        self.assertEqual(R.load_limit(-200, 0, 0), I.f_bits(-75.0))


class ClearAllSkills(unittest.TestCase):
    def test_fields(self):
        mem = N.Mem()
        mem.w8(R.G_MEDAL_PLAYER, 1)
        r = R.rec(1)
        mem.w64(r + R.P_ABILITY_MASK, 0x1234)
        mem.w32(r + R.P_SKILL_POINTS, 9)
        mem.w8(r + R.P_QUICK_B, 0)
        mem.w8(r + R.P_QUICK_A, 7)
        mem.w32(r + R.P_PAD_MASK, 0xFF)
        mem.w8(r + 0x4BC8, 0x33)                   # the first countdown byte after the pairs
        self.assertEqual(R.clear_all_skills(mem), 0)
        self.assertEqual(mem.u64(r + R.P_ABILITY_MASK), 0)
        self.assertEqual(mem.u32(r + R.P_SKILL_POINTS), 0)
        self.assertEqual(mem.u8(r + R.P_QUICK_B), 1)
        self.assertEqual(mem.u8(r + R.P_QUICK_A), 0)
        self.assertEqual(mem.u32(r + R.P_PAD_MASK), 0)
        self.assertEqual(mem.u8(r + 0x4BC8), 0x33)
        self.assertEqual(mem.u16(r + R.P_ABILITY_SKILL + 14 * R.ABILITY_SIZE), 0xFFFF)
        self.assertEqual(mem.read(r + 0x4BBF, 9), b'\xff' * 9)
        self.assertEqual(mem.u8(R.rec(0) + R.P_SKILL_POINTS), 0)

    def test_only_difficulty_zero_row_overlaps(self):
        self.assertEqual(R.mission_rows_overlapping_skill_pairs(), [0])
        self.assertEqual(R.MISSION_ROW_SPAN[1], (0x4BCC, 0x4BD9))
        self.assertEqual(R.MISSION_ROW_SPAN[5][1], R.P_MEDALS)


class Cm1(unittest.TestCase):
    def test_cached_word(self):
        self.assertEqual(R.scan_cm1_vars(0, None, 0xFFFFFFFF), -1)
        self.assertEqual(R.scan_cm1_vars(0, None, 4), 4)

    def test_scan_order_and_none(self):
        values = {b'm7cm1': 1, b'm1cm1': 1}
        asked = []

        def get(name):
            asked.append(name)
            return values.get(name, 0)
        self.assertEqual(R.scan_cm1_vars(1, get, 0), 3)
        self.assertEqual(asked, list(R.CM1_NAMES[:4]))
        self.assertEqual(R.scan_cm1_vars(1, lambda n: 0, 0), 9)
        self.assertEqual(R.scan_cm1_vars(1, lambda n: n == b'm1cm1', 0), 8)

    def test_set_word(self):
        mem = N.Mem()
        R.set_cm1_word(mem, 5, None)
        self.assertEqual(mem.s32(R.G_CM1_WORD), 5)
        R.set_cm1_word(mem, -1, lambda n: n == b'm8cm1')
        self.assertEqual(mem.s32(R.G_CM1_WORD), 2)


class Gold(unittest.TestCase):
    def comp(self, players, golds):
        mem = N.Mem()
        mem.w32(R.G_NUM_PLAYERS, players)
        for slot, g in enumerate(golds):
            mem.w32(R.rec(slot) + R.P_GOLD, g)
        return mem, R.Composer(mem, None, R.Host(), 0x01FF0000)

    def test_give_divides_and_caps(self):
        mem, c = self.comp(3, [0, 99999990, 5])
        c.givePlayerGold(31)
        self.assertEqual([mem.s32(R.rec(s) + R.P_GOLD) for s in range(3)], [10, 99999999, 15])

    def test_give_negative_rounds_toward_zero(self):
        mem, c = self.comp(2, [100, 100])
        c.givePlayerGold(-7)
        self.assertEqual(mem.s32(R.rec(0) + R.P_GOLD), 97)

    def test_give_wraps_then_caps_only_positive(self):
        mem, c = self.comp(1, [0x7FFFFFF0])
        c.givePlayerGold(0x20)
        self.assertEqual(mem.s32(R.rec(0) + R.P_GOLD), -0x7FFFFFF0)

    def test_take_floor_and_checks(self):
        mem, c = self.comp(2, [10, 50])
        c.takePlayerGold(40)
        self.assertEqual([mem.s32(R.rec(s) + R.P_GOLD) for s in range(2)], [0, 30])
        self.assertEqual(c.checkPlayerGold(), 30)
        self.assertEqual(c.checkPlayerMinGold(), 0)

    def test_min_gold_with_no_players_reads_slot_zero(self):
        mem, c = self.comp(0, [77])
        self.assertEqual(c.checkPlayerMinGold(), 77)
        self.assertEqual(c.checkPlayerGold(), 0)


class Handlers(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.mem = self.w.mem
        self.sword = self.w.definition(b'Sword')
        self.mem.w32(R.G_NUM_PLAYERS, 2)
        self.log = []

        class Host(R.Host):
            pass
        self.host = Host()
        self.c = R.Composer(self.mem, None, self.host, 0x01FF0000)

    def obj(self, slot, dead=False):
        at = 0x01200000 + slot * 0x100
        self.mem.w32(at + R.OBJ_FLAGS, R.OBJ_DEAD if dead else 0)
        self.mem.w32(R.rec(slot) + R.P_OBJECT, at)

    def test_one_player_needs_a_living_object(self):
        self.w.put(1, 0, self.sword, 2)
        self.assertEqual(self.c.onePlayerHasItem(1, b'Sword'), 0)
        self.obj(1, dead=True)
        self.assertEqual(self.c.onePlayerHasItem(1, b'Sword'), 0)
        self.obj(1)
        self.assertEqual(self.c.onePlayerHasItem(1, b'Sword'), 2)
        self.assertEqual(self.c.onePlayerHasItem(2, b'Sword'), 0)

    def test_has_item_sums_players_quest_items_slot_zero(self):
        self.w.put(0, 2, self.sword, 1)
        self.w.put(1, 2, self.sword, 2)
        self.assertEqual(self.c.playerHasItem(b'Sword'), 3)
        self.assertEqual(self.c.countQuestItems(b'Sword'), 1)

    def test_remove_all_weapons_clears_the_three_pointers(self):
        self.mem.w8(R.G_MEDAL_PLAYER, 1)
        r = R.rec(1)
        for off in (0, 4, 8):
            self.mem.w32(r + R.P_SET_WEAPONS + off, 0x1234)
        self.mem.w32(r + 0x43F0, 0x5678)
        self.c.removeAllWeapons()
        self.assertEqual([self.mem.u32(r + R.P_SET_WEAPONS + o) for o in (0, 4, 8)], [0, 0, 0])
        self.assertEqual(self.mem.u32(r + 0x43F0), 0x5678)

    def test_fits(self):
        r = R.rec(0)
        self.mem.w32(r + R.P_LOAD, I.f_bits(160.0))
        self.mem.w32(r + R.P_LOAD_LIMIT, I.f_bits(171.0))
        self.assertTrue(R.fits(self.mem, 0, I.f_bits(10.0), True))
        self.assertFalse(R.fits(self.mem, 0, I.f_bits(11.0), True))
        self.assertFalse(R.fits(self.mem, 0, I.f_bits(11.0), False))
        self.mem.w32(r + R.P_LOAD, I.f_bits(200.0))
        self.assertTrue(R.fits(self.mem, 0, 0, False))
        self.assertTrue(R.fits(self.mem, 0, 0x80000000, False))
        self.assertFalse(R.fits(self.mem, 0, 0, True))

    def test_null_item_weighs_one(self):
        self.assertEqual(R.item_weight(self.mem, None, self.host, 0, 0), R.F_ONE)
        self.assertEqual(R.item_weight(self.mem, None, self.host, 0, 0x01300000), R.F_ONE)


if __name__ == '__main__':
    unittest.main()
