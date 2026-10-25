#!/usr/bin/env python3
"""Synthetic tests of tools/ref_prop_dtors.py (no game file needed)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_prop_dtors as R                       # noqa: E402


class Recorder:
    def __init__(self, answers=()):
        self.mem, self.calls, self.answers = {}, [], list(answers)

    def w32(self, addr, value):
        self.mem[addr] = value

    def call(self, name, *args, f12=None):
        self.calls.append((name, args, f12))
        return self.answers.pop(0) if self.answers else 0


class PropDtor(unittest.TestCase):
    def test_table_then_base_then_free_on_bit_0(self):
        for flags, frees in ((0, False), (1, True), (2, False), (3, True)):
            r = Recorder()
            R.Model(r.w32, r.call).prop_dtor(0x1000, flags)
            self.assertEqual(r.mem, {0x1048: R.VT_PROP})
            expected = [('GameObject_dtor', (0x1000, 0), None)]
            if frees:
                expected.append(('pool_free', (0x1000,), None))
            self.assertEqual(r.calls, expected)

    def test_four_classes_share_the_body(self):
        for addr in (R.GUTCHUNK_DTOR, R.PROP_DTOR, R.ITEMPROP_DTOR):
            self.assertEqual(R.CLASS_BODIES[addr], R.CLASS_BODIES[R.PHPROP_DTOR])
        self.assertEqual(R.CLASS_BODIES[R.GOLD_DTOR], (1, 'gold_dtor'))
        self.assertEqual(len(R.EXECUTED), 6)

    def test_gold_releases_its_clip_state_first(self):
        for flags, frees in ((0, False), (1, True)):
            r = Recorder()
            R.Model(r.w32, r.call).gold_dtor(0x1000, flags)
            self.assertEqual(r.mem, {0x1048: R.VT_GOLD})
            expected = [('AnimState_dtor', (0x1058, 2), None), ('GameObject_dtor', (0x1000, 0), None)]
            if frees:
                expected.append(('pool_free', (0x1000,), None))
            self.assertEqual(r.calls, expected)


class UnitSpeed(unittest.TestCase):
    def test_speed_one_and_arguments_unchanged(self):
        r = Recorder(answers=[0x81])
        ret = R.Model(r.w32, r.call).anim_advance_unit_speed(0x2000, 0, 0x3000, 0x3004)
        self.assertEqual(ret, 0x81)
        self.assertEqual(r.calls, [('anim_advance', (0x2000, 0, 0x3000, 0x3004), 0x3F800000)])
        self.assertEqual(r.mem, {})


if __name__ == '__main__':
    unittest.main()
