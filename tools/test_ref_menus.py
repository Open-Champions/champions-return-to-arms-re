#!/usr/bin/env python3
"""Unit tests of tools/ref_menus.py. No game files.

tools/dis.py shadows the standard-library dis module, so discover has to load
that module first:

  python3 -c "import dis,sys; sys.path.insert(0,'.'); import unittest; \
r=unittest.TextTestRunner().run(unittest.defaultTestLoader.discover('tools', pattern='test_ref_menus.py')); \
sys.exit(0 if r.wasSuccessful() else 1)"
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_menus as M


class RankCost(unittest.TestCase):
    def test_linear_band(self):
        self.assertEqual(M.rank_cost(0, 10), 0)
        self.assertEqual(M.rank_cost(1, 0), 1)
        self.assertEqual(M.rank_cost(1, 10), 11)
        self.assertEqual(M.rank_cost(4, 10), 44)
        self.assertEqual(M.rank_cost(-1, 10), -11)
        self.assertEqual(M.rank_cost(4, 0), 4)

    def test_power_band_matches_the_executed_points(self):
        # These are the values skills_nextRankCost returned under ee_emu.
        self.assertEqual(M.rank_cost(5, 0), 5)
        self.assertEqual(M.rank_cost(5, 1), 6)
        self.assertEqual(M.rank_cost(5, 2), 8)
        self.assertEqual(M.rank_cost(5, 3), 10)
        self.assertEqual(M.rank_cost(5, 10), 44)
        self.assertEqual(M.rank_cost(8, 2), 11)
        self.assertEqual(M.rank_cost(20, 10), 59)


class SaveIndex(unittest.TestCase):
    def setUp(self):
        self.record = 0x100000
        self.counts = (2, 1, 0)

    def test_round_trip_of_counted_cells(self):
        for bag, index in ((0, 0), (0, 1), (1, 0)):
            cell = (self.record + M.BAG_ITEMS + bag * M.BAG_STRIDE + index * M.ITEM_SIZE)
            got = M.item_ptr_to_index(cell, self.record, self.counts)
            self.assertEqual(got, bag * 1000 + index)
            self.assertEqual(M.item_index_to_ptr(got, self.record, self.counts), cell)

    def test_null_and_past_the_count(self):
        self.assertEqual(M.item_ptr_to_index(0, self.record, self.counts), -1)
        past = self.record + M.BAG_ITEMS + 2 * M.ITEM_SIZE
        self.assertEqual(M.item_ptr_to_index(past, self.record, self.counts), -1)
        self.assertEqual(M.item_index_to_ptr(-1, self.record, self.counts), 0)
        self.assertEqual(M.item_index_to_ptr(2, self.record, self.counts), 0)
        bag1 = self.record + M.BAG_ITEMS + M.BAG_STRIDE
        self.assertEqual(M.item_index_to_ptr(1000, self.record, self.counts), bag1)
        self.assertEqual(M.item_index_to_ptr(1001, self.record, self.counts), 0)
        self.assertEqual(M.item_index_to_ptr(2000, self.record, self.counts), 0)
        empty = self.record + M.BAG_ITEMS + 2 * M.BAG_STRIDE
        self.assertEqual(M.item_ptr_to_index(empty, self.record, self.counts), -1)


class Cursor(unittest.TestCase):
    def test_origin_cell(self):
        self.assertEqual(M.cursor_cell(0, 17, 100, 0, 0), (0, 0))
        self.assertEqual(M.cursor_cell(0, 49, 100, 0, 0), (1, 0))
        self.assertEqual(M.grid_address(0x2000, 1, 0), 0x2000 + M.GRID_COL)
        self.assertEqual(M.grid_address(0x2000, -1, 0), 0)
        self.assertEqual(M.grid_address(0x2000, 9, 0), 0)


class Actions(unittest.TestCase):
    def test_cross_confirm_scheme(self):
        m = M.CROSS_CONFIRM
        self.assertEqual(M.item_action(0, 0x80, masks=m), 'buy')
        self.assertIsNone(M.item_action(0, 0x40, masks=m))
        self.assertEqual(M.item_action(1, 0x80, masks=m), 'sell')
        self.assertEqual(M.item_action(1, 0x80, equipped=True, masks=m), 'confirm')
        self.assertEqual(M.item_action(1, 0x40, masks=m), 'equip')
        self.assertEqual(M.item_action(1, 0x40, equipped=True, masks=m), 'unequip')
        self.assertEqual(M.item_action(2, 0x40, masks=m), 'equip')
        self.assertEqual(M.item_action(2, 0x40, holdable=True, masks=m), 'drag')
        self.assertEqual(M.item_action(2, 0x10, masks=m), 'drop')
        self.assertEqual(M.item_action(2, 0x50, masks=m), 'equip')
        self.assertIsNone(M.item_action(2, 0x80, masks=m))
        self.assertEqual(M.item_action(3, 0, masks=m), 'workshop')

    def test_circle_confirm_scheme(self):
        m = M.CIRCLE_CONFIRM
        self.assertEqual(M.item_action(2, 0x20, masks=m), 'equip')
        self.assertEqual(M.item_action(2, 0x80, masks=m), 'drop')
        self.assertIsNone(M.item_action(2, 0x40, masks=m))
        self.assertIsNone(M.item_action(0, 0x80, masks=m))


class Layout(unittest.TestCase):
    def test_published_positions(self):
        self.assertEqual(M.inventory_strip(80), (95, 413, 385))
        self.assertEqual(M.shop_choice_rows(), (203, 243))
        self.assertEqual(M.stats_header(), (160, 107, 0x4F7104))


if __name__ == '__main__':
    unittest.main()
