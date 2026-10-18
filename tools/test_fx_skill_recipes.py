"""Tests for fx_skill_recipes.py on hand-assembled instruction words (no game file).

Run: python3 -m unittest discover -s tools -p test_fx_skill_recipes.py
"""
import json
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import fx_skill_recipes as R                    # noqa: E402
import ref_fx_skills as FS                      # noqa: E402
import test_fx_particle_defs as T               # noqa: E402  (instruction encoders)

BASE = 0x2D0000


def glow_call():
    """glow_add(bias 10, size ?, position ?, 0x93, 0x62, 0x49, alpha 0x49, texture ?, 0, 6)."""
    w = T.load_float(12, 10.0)
    w += [T.addiu(5, 0, 0x93), T.addiu(6, 0, 0x62), T.addiu(7, 0, 0x49), T.addiu(8, 0, 0x49),
          T.addiu(10, 0, 0), T.addiu(11, 0, 6), T.jal(0x18FC78), T.NOP]
    return w


def particle_call(definition):
    return [T.lui(4, definition >> 16), T.addiu(4, 4, definition & 0xFFFF), T.mtc1(0, 12),
            T.jal(0x18F3F8), T.NOP]


class Scan(unittest.TestCase):
    def setUp(self):
        self.words = glow_call() + particle_call(0x8E5910) + particle_call(0x8E5910) + particle_call(0x8E5960)
        self.names = {BASE: 'Foo_draw'}
        self.rows = R.scan(self.words, BASE, [BASE], self.names, lo=BASE, hi=BASE + 0x1000)

    def test_rows_and_arguments(self):
        self.assertEqual([r[3] for r in self.rows], ['glow', 'particle', 'particle', 'particle'])
        glow = self.rows[0][4]
        self.assertEqual(glow['f12'], 10.0)
        self.assertIsNone(glow['f13'])
        self.assertEqual((glow['a1'], glow['a2'], glow['a3'], glow['t0'], glow['t3']), (0x93, 0x62, 0x49, 0x49, 6))
        self.assertEqual(self.rows[1][4]['a0'], 0x8E5910)
        self.assertEqual(self.rows[1][4]['f12'], 0.0)

    def test_outside_the_range_is_skipped(self):
        self.assertEqual(R.scan(self.words, BASE, [BASE], self.names, lo=0, hi=BASE), [])

    def test_build_definitions_and_text(self):
        recipes = {'Foo': [FS.Phase('Foo', 'draw', 'Foo_draw', BASE, 'ref_fx_skills.x', 'glow:1', '')]}
        classes = R.build(self.rows, recipes)
        self.assertEqual(sorted(classes), ['Foo'])
        self.assertEqual(classes['Foo']['phases'][0]['phase'], 'draw')
        self.assertEqual(classes['Foo']['calls'][0]['meaning']['t0'], 'alpha')
        self.assertEqual(R.definitions(classes), [0x8E5910, 0x8E5960])
        text = R.text({'classes': classes})
        self.assertIn('alpha=0x49', text)
        self.assertIn('size=?', text)
        json.dumps(classes)                     # serialisable

    def test_class_of(self):
        self.assertEqual(R.class_of('SpellHealing_run'), 'SpellHealing')
        self.assertEqual(R.class_of(''), '')


if __name__ == '__main__':
    unittest.main()
