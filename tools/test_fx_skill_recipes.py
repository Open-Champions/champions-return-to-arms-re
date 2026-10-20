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


def sh(rt, off, base):
    return T.i_type(0x29, base, rt, off)


def sw(rt, off, base):
    return T.i_type(0x2b, base, rt, off)


def sb(rt, off, base):
    return T.i_type(0x28, base, rt, off)


def swc1(ft, off, base):
    return T.i_type(0x39, base, ft, off)


def beq(rs, rt, here, target):
    """beq at instruction index `here` to instruction index `target`."""
    return T.i_type(4, rs, rt, target - (here + 1))


def fill_light_record(light_off=0x80, colours=(0x11, 0x22, 0x33, 0x44), radius=16.0, extra=0.5,
                      falloff=0.125):
    """Minimal ctor body: a0 at BASE; light at a0+light_off; constant fields only."""
    w = [T.addiu(2, 4, light_off)]
    for k, value in enumerate(colours):
        w.append(T.addiu(3, 0, value & 0xFFFF))
        w.append(sh(3, 0x0A + 2 * k, 2))
        w.append(sh(3, 0x12 + 2 * k, 2))
    w += T.load_float(12, radius)
    w.append(swc1(12, 0x1C, 2))
    w.append(swc1(12, 0x24, 2))
    w += T.load_float(12, falloff)
    w.append(swc1(12, 0x20, 2))
    w.append(swc1(12, 0x28, 2))
    w += T.load_float(12, extra)
    w.append(swc1(12, 0x2C, 2))
    w.append(sb(0, 8, 2))
    w.append(sb(0, 9, 2))
    return w


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


class LightRecords(unittest.TestCase):
    def test_decode_and_scan(self):
        words = fill_light_record()
        mem = R._walk_function(words, BASE, BASE, BASE + len(words) * 4, None)
        rec = R.decode_light_record(mem, 0x80, True)
        self.assertEqual(rec['colour'], [0x11, 0x22, 0x33, 0x44] * 2)
        self.assertEqual(rec['radius'], 16.0)
        self.assertEqual(rec['falloff'], 0.125)
        self.assertEqual(rec['extra'], 0.5)
        out = R.scan_light_records(words, BASE, None,
                                   (('Synth_ctor', BASE, BASE + len(words) * 4, 0x80, True),))
        self.assertIn('Synth_ctor', out)
        json.dumps(out)                         # serialisable floats


class PathFill(unittest.TestCase):
    """A branch around an earlier call keeps constants the straight-line walk drops.

    Shape of SpellArena_run's two particle calls (0x305e08–0x305e28): the fall-through
    call uses one a0, an unconditional branch skips the next call, and that next call's
    a0 is an addiu from a register set before the first call.  f12 is set before both.
    Immediates here are synthetic.
    """

    def test_second_call_keeps_a0_and_f12(self):
        w = [T.lui(8, 0x12), T.addiu(4, 8, 100), T.mtc1(0, 12), beq(0, 0, 3, 9), T.NOP,
             T.jal(0x18F3F8), T.NOP, beq(0, 0, 7, 12), T.NOP, T.addiu(4, 8, 200),
             T.jal(0x18F3F8), T.NOP, T.NOP]
        rows = R.scan(w, BASE, [BASE], {BASE: 'Synth_run'}, lo=BASE, hi=BASE + 0x100)
        self.assertEqual([row[3] for row in rows], ['particle', 'particle'])
        self.assertEqual(rows[0][4]['a0'], 0x120000 + 100)
        self.assertEqual(rows[0][4]['f12'], 0.0)
        self.assertEqual(rows[1][4]['a0'], 0x120000 + 200)
        self.assertEqual(rows[1][4]['f12'], 0.0)

    def test_straight_line_value_wins_over_the_other_path(self):
        # Fall-through sets a0 to 5.  The always-taken branch would leave the lui value.
        w = [T.lui(4, 1), beq(0, 0, 1, 4), T.NOP, T.addiu(4, 0, 5), T.jal(0x18F3F8), T.NOP]
        rows = R.scan(w, BASE, [BASE], {BASE: 'Synth_run'}, lo=BASE, hi=BASE + 0x100)
        self.assertEqual(rows[0][4]['a0'], 5)

    def test_no_bounds_drops_every_call(self):
        words = [T.addiu(29, 29, -32), T.jal(0x18F3F8), T.NOP, 0x03E00008, T.NOP]
        self.assertEqual(R.scan(words, BASE, [], {BASE: 'Foo_run'}, lo=BASE, hi=BASE + 64), [])

    def test_inferred_prologue_keeps_the_call(self):
        # The prologue is the instruction after the previous function's jr ra.
        words = [0x03E00008, T.NOP, T.addiu(29, 29, -32), T.jal(0x18F3F8), T.NOP,
                 0x03E00008, T.NOP]
        start = BASE + 8
        starts = R.function_starts(words, BASE, [], BASE, BASE + 64, extra=())
        self.assertIn(start, starts)
        rows = R.scan(words, BASE, starts, {start: 'Foo_run'}, lo=BASE, hi=BASE + 64)
        self.assertEqual([(row[0], row[3]) for row in rows], [(start, 'particle')])

    def test_listed_bounds_are_not_replaced(self):
        words = [T.addiu(29, 29, -32), T.jal(0x18F3F8), T.NOP]
        listed = [BASE + 4]
        self.assertEqual(R.function_starts(words, BASE, listed, BASE, BASE + 64), listed)

    def test_extra_outside_the_image_is_ignored(self):
        words = [T.jal(BASE + 8), T.NOP, T.NOP, T.NOP]
        starts = R.function_starts(words, BASE, [], BASE, BASE + 32, extra=(BASE + 0x10000,))
        self.assertIn(BASE + 8, starts)
        self.assertNotIn(BASE + 0x10000, starts)


if __name__ == '__main__':
    unittest.main()
