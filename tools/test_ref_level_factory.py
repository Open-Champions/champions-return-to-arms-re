#!/usr/bin/env python3
"""test_ref_level_factory.py - checks of tools/ref_level_factory.py and
tools/ref_creature_init.py that need no game files.

They pin the models' own rules with authored strings at the real addresses.  That the
models match the game is the job of tools/difftest_level_factory.py and
tools/difftest_creature_init.py, which need the executable.

    python3 -m unittest discover -s tools -p 'test_ref_level_factory.py'
"""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_creature_init as C                   # noqa: E402
import ref_level_factory as F                   # noqa: E402


class Strings:
    """Authored text at a few addresses; an ASCII class table (upper 1, space 8)."""

    def __init__(self, table):
        self.table = table

    def string(self, addr):
        return self.table.get(addr, b'\xff\xfe')     # no authored name matches these

    def ctype(self, index):
        return (1 if 65 <= index <= 90 else 0) | (8 if index in (9, 10, 11, 12, 13, 32) else 0)


def authored():
    t = {}
    for row in F.TESTS:
        t[row[1]] = b'unused%x' % row[1]
    t[F.TESTS[0][1]] = b'First'
    t[F.LINE] = b'Line'
    t[F.LINE_NAME_KEY] = b'name'
    t[F.LINE_WAVE] = b'wave'
    keys = [b'CreatureContainer', b'AutoContainer', b'AutoChest', b'AutoProp', b'AutoEmitter',
            b'AutoDoor', b'AutoSwitch', b'Critter', b'Generator', b'SmokeGen']
    for (_g, addr, _o), key in zip(F.FALLBACKS, keys):
        t[addr] = key
    for addr, key in zip(F.LIGHT_KEYS, (b'ParticleEmitter', b'DynamicLight', b'Halo')):
        t[addr] = key
    for addr, key in zip(F.LIGHT_FORMATS, (b'ParticleEmitter%d', b'DynamicLight%d', b'Halo%d')):
        t[addr] = key
    return Strings(t)


class FactoryRules(unittest.TestCase):
    def setUp(self):
        self.s = authored()

    def test_equality_is_case_insensitive_and_full(self):
        self.assertTrue(F.classify(b'first', [], self.s).creates)
        self.assertTrue(F.classify(b'FIRST', None, self.s).creates)
        self.assertFalse(F.classify(b'Firstx', [], self.s).creates)
        self.assertEqual(F.classify(b'First', [], self.s).sizes, (F.TESTS[0][2],))

    def test_line_builds_a_wave_maker_only_when_named_wave(self):
        self.assertFalse(F.classify(b'Line', [b'name=other'], self.s).creates)
        self.assertEqual(F.classify(b'Line', [], self.s).calls, (0x20F844,))
        wave = F.classify(b'line', [b'name=WAVE'], self.s)
        self.assertTrue(wave.creates)
        self.assertEqual(wave.constructor, 0x15ECF8)

    def test_property_keys_are_lowered_and_matched_case_sensitively(self):
        self.assertTrue(F.classify(b'Nothing', [b'autoemitter=1'], self.s).creates)
        self.assertFalse(F.classify(b'Nothing', [b'AutoEmitter=1'], self.s).creates)
        self.assertFalse(F.classify(b'Nothing', [b'autoemitter=0'], self.s).creates)
        self.assertFalse(F.classify(b'Nothing', [b'autoemitter'], self.s).creates)
        self.assertFalse(F.classify(b'Nothing', [], self.s).creates)

    def test_the_light_test_picks_the_size(self):
        plain = F.classify(b'Nothing', [b'autoprop=1'], self.s)
        lit = F.classify(b'Nothing', [b'autoprop=1', b'halo2=1'], self.s)
        self.assertEqual(plain.sizes, (0x198,))
        self.assertEqual(lit.sizes, (0x448,))

    def test_get_str_needs_only_the_entry(self):
        self.assertTrue(F.classify(b'Nothing', [b'smokegen='], self.s).creates)

    def test_atoi_is_strtol_low_bits(self):
        self.assertEqual(F.atoi(b'\t-3', self.s), (-3) & F.M32)
        self.assertEqual(F.atoi(b'4294967296', self.s), 0)
        self.assertEqual(F.atoi(b'99999999999999999999', self.s), 0xFFFFFFFF)


class CreatureInitRules(unittest.TestCase):
    class Obj:
        def __init__(self, props, flags=0, weapon=0):
            self.props, self.flags, self.weapon_ptr, self.writes = props, flags, weapon, []

        def flags64(self):
            return self.flags

        def set_flags64(self, v):
            self.flags = v
            self.writes.append((0xA8, 8, v))

        def weapon(self):
            return self.weapon_ptr

        def prop_str(self, addr, text=None):
            key = (text if text is not None else {C.KEY_DEAD: b'dead', C.KEY_INIT_SCRIPT: b'initscript'}
                   .get(addr, b'?')).lower()
            for p in self.props:
                if p.startswith(key + b'='):
                    return p[len(key) + 1:]
            return None

        def prop_int(self, addr):
            return 0

        def store(self, off, size, value):
            self.writes.append((off, size, value))

        def store_global(self, addr, size, value):
            self.writes.append(('g', size, value))

    class Host:
        def __init__(self, model=0, bounds=(0,) * 6, cutscene=0):
            self.model, self.b, self.cut, self.events = model, bounds, cutscene, []

        def vcall(self, slot, args):
            self.events.append(('vcall', slot) + tuple(args))
            return self.model if slot == C.SLOT_MODEL else 0

        def weapon_vcall(self, slot, args):
            self.events.append(('weapon', slot))

        def bounds(self, model):
            return list(self.b)

        def hide_mask(self, model, mask):
            return 0x1234

        def call(self, name, args):
            self.events.append((name,) + tuple(args))

        def cutscene(self):
            return self.cut

        def change_key(self, n):
            return b'change%d' % n

    def test_height_floor_and_draw_byte(self):
        obj, host = self.Obj([]), self.Host(model=1, bounds=(0, 0, 10, 0, 0, 30))
        C.run(obj, host)
        self.assertEqual(obj.writes, [(0x20, 4, 0x41A00000), (0x20, 4, C.HEIGHT_FLOOR), (0x29, 1, 85)])

    def test_dead_sets_bit_32_and_the_death_state(self):
        obj, host = self.Obj([b'dead=1'], flags=1), self.Host()
        C.run(obj, host)
        self.assertEqual(obj.writes, [(0xA8, 8, 1 | C.DEAD_BIT)])
        self.assertEqual(host.events[0], ('vcall', C.SLOT_MINIBOSS))
        self.assertIn(('vcall', C.SLOT_SET_STATE, C.DEAD_STATE), host.events)

    def test_change_bits_and_no_flag_word(self):
        obj, host = self.Obj([b'change3=0', b'change0=1']), self.Host()
        C.run(obj, host)
        self.assertEqual(obj.writes, [(0xE8, 4, 9), (0x220, 8, 0x1234)])
        for off, _size, _v in obj.writes:
            self.assertNotIn(off, (0x0C, 0x228, 0x231))

    def test_init_script_skipped_in_a_cutscene(self):
        obj, host = self.Obj([b'initscript=go']), self.Host(cutscene=1)
        C.run(obj, host)
        self.assertEqual(obj.writes, [])
        obj, host = self.Obj([b'initscript=go']), self.Host()
        C.run(obj, host)
        self.assertEqual(obj.writes, [('g', 4, 'this'), ('g', 4, 0)])
        self.assertIn(('script_runByName', b'go'), host.events)


if __name__ == '__main__':
    unittest.main()
