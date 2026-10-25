"""Tests for fx_callsites.py on hand-assembled instruction words (no game file).

Run: python3 -m unittest discover -s tools -p test_fx_callsites.py
"""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import fx_callsites as C                        # noqa: E402
import test_fx_particle_defs as T               # noqa: E402  (instruction encoders)


class CallSites(unittest.TestCase):
    def test_light_effect_arguments(self):
        w = []
        for fr, x in zip(range(12, 20), (255, 128, 0, 100, 0, 0, 0, 0)):
            w += T.load_float(fr, float(x))
        w += T.load_float(2, 120.0, tmp=3)[:-1] + [T.sw(3, 0x00)]          # radius0 bits on the stack
        w += [T.addiu(6, 0, 0), T.addiu(7, 0, 1), T.jal(0x201bd8), T.NOP]
        (site, target, t), = list(C.scan_calls(w, 0x2d4480, {0x201bd8}))
        self.assertEqual(target, 0x201bd8)
        text = C.describe_args('LightEffect', t)
        self.assertIn('f12=255', text)
        self.assertIn('f15=100', text)
        self.assertIn('a3=0x1', text)
        self.assertIn('sp+0x0=120', text)
        self.assertIn('sp+0x8=?', text)

    def test_owner_and_summary(self):
        starts = [0x100, 0x200]
        self.assertEqual(C.owner(starts, 0x1fc), 0x100)
        self.assertEqual(C.owner(starts, 0x200), 0x200)
        self.assertIsNone(C.owner(starts, 0x10))
        rows = [(0x100, 'A_run', 0x110, 'particle', ''), (0x100, 'A_run', 0x120, 'particle', ''),
                (0x100, 'A_run', 0x130, 'glow', '')]
        self.assertEqual(C.summarise(rows), {(0x100, 'A_run'): {'particle': 2, 'glow': 1}})

    def test_every_primitive_has_a_name(self):
        self.assertEqual(len(C.PRIMITIVES), len(C.BY_NAME))
        for prim in C.SIGNATURES:
            self.assertIn(prim, C.BY_NAME)


if __name__ == '__main__':
    unittest.main()
