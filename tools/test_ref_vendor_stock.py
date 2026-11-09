#!/usr/bin/env python3
"""Arithmetic checks for the vendor price and gold-restock helpers. No game files."""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_vendor_stock as S


class Prices(unittest.TestCase):
    def test_buy_factors(self):
        self.assertEqual(S.buy_price(100, 0, 0, 0), 59)
        self.assertEqual(S.buy_price(100, 1, 0, 0), 44)
        self.assertEqual(S.buy_price(100, 0, S.BUY_FULL_FLAGS, 0), 100)
        self.assertEqual(S.buy_price(100, 1, 0, 8), 100)

    def test_sell_credit_and_cap(self):
        self.assertEqual(S.sell_credit(100, 1, 0, False, 0), 4)
        self.assertEqual(S.sell_credit(100, 1, 8, False, 0), 0)
        self.assertEqual(S.sell_credit(100, 1, 0, False, S.SELL_ZERO_FLAGS), 0)
        self.assertEqual(S.sell_gold(S.GOLD_CAP - 1, 4), S.GOLD_CAP)
        self.assertEqual(S.buy_gold(10, 59), (10, False))
        self.assertEqual(S.buy_gold(59, 59), (0, True))

    def test_restock_budgets_wrap(self):
        self.assertEqual(S.signed_half(0), 0)
        self.assertEqual(S.signed_half(-1), 0)
        self.assertEqual(S.signed_half(-3), -1)
        self.assertEqual(S.signed_double(0x7FFFFFFF), -2)
        calls = list(S.restock_calls(100))
        self.assertEqual(len(calls), 45)
        self.assertEqual(calls[0], (S.RESTOCK_LISTS[0], 50, 0, 0))
        self.assertEqual(calls[5], (S.RESTOCK_LISTS[0], 100, 0, 0))
        self.assertEqual(calls[10], (S.RESTOCK_LISTS[0], 200, 0, 0))
        self.assertEqual(calls[-1][0], S.RESTOCK_LISTS[2])
        self.assertEqual(calls[-1][3], 2)


class Round3(unittest.TestCase):
    def test_hub_store_level(self):
        self.assertEqual(S.hub_store_level(0), 0)
        self.assertEqual([S.hub_store_level(n) for n in range(1, 7)], [0, 1, 2, 3, 4, 5])
        self.assertEqual(S.hub_store_level(7), 5)
        self.assertEqual(S.hub_store_level(7, {8: 1}), 6)
        self.assertEqual(S.hub_store_level(7, {8: 1, 9: 1}), 7)
        self.assertEqual(S.hub_store_level(7, {9: 2}), 8)
        self.assertEqual(S.hub_store_level(7, {8: 2}), 5)
        self.assertEqual([S.hub_store_level(n) for n in (8, 9, 10, 11, 12)], [6, 7, 9, 10, 11])

    def test_menu_steps(self):
        self.assertEqual(S.choice_step(3, 0, 0x40, 0x40, 0x20), (0, 0))
        self.assertEqual(S.choice_step(3, 1, 0x40, 0x40, 0x20), (1, 1))
        self.assertEqual(S.choice_step(3, 1, 0x40, 0x40, 0x20, animating=True), (3, 1))
        self.assertEqual(S.choice_step(3, 0, 0x20, 0x40, 0x20), (2, 0))
        self.assertEqual(S.choice_step(3, 0, 0x20, 0x40, 0x20, blocked=True), (3, 0))
        self.assertEqual(S.list_cancel(1, 1, 0x20, 0x20), (3, 1))
        self.assertEqual(S.list_cancel(0, 0, 0x40, 0x20), (0, None))

    def test_buy_allowed(self):
        one, ten = 0x3F800000, 0x41200000
        self.assertEqual(S.buy_allowed(100, 59, 0, 0, one, ten), 'send')
        self.assertEqual(S.buy_allowed(58, 59, 0, 0, one, ten), 'gold')
        self.assertEqual(S.buy_allowed(100, 59, 64, 0, one, ten), 'full')
        self.assertEqual(S.buy_allowed(100, 59, 0, ten, one, ten), 'weight')


if __name__ == '__main__':
    unittest.main()
