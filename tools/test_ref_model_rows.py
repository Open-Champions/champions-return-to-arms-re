#!/usr/bin/env python3
"""Unit tests of tools/ref_model_rows.py: the VIF row-register contract of program 0x46
in a model file.  Synthetic vectors only.

  python3 -m unittest discover -s tools -p 'test_ref_model_rows.py'
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_model_rows as R                      # noqa: E402


class TestStmodAdd(unittest.TestCase):
    def test_zero_rows_leave_positions(self):
        self.assertEqual(R.stmod_add((16, -32, 48), (0, 0, 0, 0)), (16, -32, 48))
        self.assertEqual(R.world_units((16, -32, 48), (0, 0, 0, 0)), (1.0, -2.0, 3.0))

    def test_nonzero_rows_are_added_per_component_before_the_divide(self):
        rows = R.rows_for_level_chunk(160, -1600, 32)
        self.assertEqual(rows, (160, -1600, 32, 0))
        self.assertEqual(R.stmod_add((16, 16, 16), rows), (176, -1584, 48))
        self.assertEqual(R.world_units((16, 16, 16), rows), (11.0, -99.0, 3.0))
        self.assertEqual(R.packet_positions([(0, 0, 0), (-16, 32, -48)], rows),
                         [(10.0, -100.0, 2.0), (9.0, -98.0, -1.0)])

    def test_add_is_32_bit_and_wraps(self):
        self.assertEqual(R.stmod_add((0x7fffffff, -0x80000000, 0), (1, -1, 0, 0)),
                         (-0x80000000, 0x7fffffff, 0))

    def test_signed_16_bit_inputs_are_sign_extended(self):
        # a V3-16 signed unpack delivers -1 as 0xffffffff before the add
        self.assertEqual(R.stmod_add((-1, -32768, 32767), (1, 0, 1, 0)), (0, -32768, 32768))


class TestProvenance(unittest.TestCase):
    def test_uncalled_setup_rows_are_zero(self):
        self.assertEqual(R.rows_for_model(R.ROWS_MODEL_SETUP_0x175950), (0, 0, 0, 0))
        self.assertEqual(R.SETUP_0x175950_ROWS, (0, 0, 0, 0))
        regs = dict((a, v) for a, v in R.SETUP_0x175950_GS)
        self.assertEqual(regs[0x47], 0x507f5)
        self.assertEqual(regs[0x3f], 0)
        self.assertEqual(regs[0x42], 'model+0x18')

    def test_inherited_rows_need_the_preceding_chunk(self):
        with self.assertRaises(ValueError):
            R.rows_for_model(R.ROWS_INHERITED)
        self.assertEqual(R.rows_for_model(R.ROWS_INHERITED, (160, -1600, 32, 0)), (160, -1600, 32, 0))

    def test_a_model_is_not_a_level_chunk(self):
        with self.assertRaises(ValueError):
            R.rows_for_model(R.ROWS_LEVEL_CHUNK)
        with self.assertRaises(ValueError):
            R.rows_for_model('guess')

    def test_constants(self):
        self.assertEqual(R.STROW_CODE, 0x30000000)
        self.assertEqual(R.PROGRAM_LEVEL_ONE_PASS, 0x46)
        self.assertEqual(R.POSITION_SCALE, 16)


if __name__ == '__main__':
    unittest.main()
