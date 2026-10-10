#!/usr/bin/env python3
"""Unit tests of tools/ref_items.py that need no game files.

The tables used here are INVENTED: a small fake executable image is built in memory with
made-up rows at the addresses the model reads.  Nothing in this file comes from the game.
These tests check the model's own logic (the rules written in docs/spec/items.md); whether
the rules are the game's is the job of tools/difftest_items.py, which needs the executable.

  python3 -m unittest discover -s tools -p 'test_ref_items.py'
"""
import math
import os
import struct
import sys
import unittest
from fractions import Fraction

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.append(_HERE)
import ref_items as R

F = R.f_bits


class FakeExe(R.Exe):
    """Sparse memory standing in for the executable."""

    def __init__(self):
        self.mem = {}
        self.pool = 0x600000

    def poke(self, addr, data):
        for index, byte in enumerate(data):
            self.mem[addr + index] = byte

    def text(self, value):
        addr = self.pool
        self.poke(addr, value + b'\0')
        self.pool += len(value) + 1
        return addr

    def read(self, addr, size):
        return bytes(self.mem.get(addr + index, 0) for index in range(size))

    def cstr(self, addr):
        out = bytearray()
        while self.mem.get(addr, 0):
            out.append(self.mem[addr])
            addr += 1
        return bytes(out)


CLOTH, NO_RANDOM, REAGENT, FIGURINE = 0x80000, 0x10000, 0x800000000, 0x200000000000

# name, level, weight, count, dmin, dmax, price, armor, attack, slot, category, subtype,
# damage bits, flags, picture
DEFS = [
    (b'blade', 1, 4.0, 1, 4, 9, 0, 0, 6, 0, 0, 0, 8, 2 << 11, None),
    (b'maul', 3, 28.0, 1, 10, 20, 0, 0, 14, 2, 0, 3, 1, 0, None),
    (b'greataxe', 2, 20.0, 1, 9, 19, 0, 0, 13, 2, 0, 3, 8, 3 << 11, None),
    (b'dart', 1, 0.5, 40, 2, 5, 0, 0, 3, 0, 0, 6, 4, 0, None),
    (b'cap', 1, 2.0, 1, 0, 0, 0, 5, 0, 11, 1, 0, 0, 0x100000, None),
    (b'robe', 1, 3.0, 1, 0, 0, 0, 4, 0, 4, 1, 0, 0, CLOTH, None),
    (b'vest', 4, 9.0, 1, 0, 0, 0, 12, 0, 4, 1, 0, 0, 0x100000 | (2 << 11), None),
    (b'buckler', 2, 6.0, 1, 0, 0, 0, 8, 0, 3, 1, 0, 0, 0x200000, None),
    (b'redvial', 1, 0.2, 1, 0, 0, 25, 0, 0, 16, 2, 0, 0, NO_RANDOM, None),
    (b'bluevial', 1, 0.2, 1, 0, 0, 30, 0, 0, 16, 2, 0, 0, NO_RANDOM, None),
    (b'homevial', 1, 0.2, 1, 0, 0, 50, 0, 0, 16, 2, 0, 0, NO_RANDOM, None),
    (b'bolts', 1, 0.1, 20, 0, 0, 2, 0, 0, 8, 2, 0, 0, NO_RANDOM, None),
    (b'ring', 2, 0.1, 1, 0, 0, 0, 0, 0, 5, 2, 0, 0, 0, None),
    (b'trinket', 1, 0.3, 1, 0, 0, 0, 0, 0, 16, 2, 0, 0, 0, None),
    (b'dust', 3, 0.1, 1, 0, 0, 12, 0, 0, 16, 2, 0, 0, REAGENT, b'dustpic'),
    (b'shard', 20, 0.1, 1, 0, 0, 90, 0, 0, 16, 2, 0, 0, REAGENT, b'shardpic'),
    (b'idol', 3, 1.0, 1, 0, 0, 500, 0, 0, 16, 2, 0, 0, FIGURINE, b'idolpic'),
]
PRESETS = [(b'blade+tokaa7', 1, 0), (b'cap+tokae3', 2, 0), (b'robe+tokae9', 1, CLOTH), (b'ring+tokai4', 3, 0)]
PREFIXES = [   # key, level, texts by category, flag mask, damage mask
    (b'dull', 1, (b'+tokaa-20', b'+tokae-20', None), 0x380000, 0),
    (b'fine', 2, (b'+tokaa15', b'+tokae15', None), 0x380000, 0),
    (b'keen', 9, (b'+tokaa30', None, None), 0x100000, 8),
    (b'odd', 1, (b'+tokaa5', b'+tokae5', None), 0x100000, 0),
]
SUFFIXES = [(b'ash', 1, (b'+tokai4', b'+tokam6', b'+tokam2')),
            (b'ice', 2, (b'+tokai9', None, b'+tokam8')),
            (b'sky', 30, (b'+tokai40', b'+tokam40', b'+tokam40'))]


def fake_tables():
    exe = FakeExe()
    patterns = ('%d', '%d-%d', '%d,%d', '%d,%d-%d')
    for index, (addr, code) in enumerate(R.TOKEN_FORMATS):
        word = 'tok' + chr(97 + index // 26) + chr(97 + index % 26)
        exe.poke(addr, (word + ('%d' if code is None else patterns[index % 4])).encode() + b'\0')

    def rows(base, entries, preset):
        for index, entry in enumerate(entries):
            addr = base + index * 0x40
            if preset:
                name, level, flags = entry
                base_def = next(d for d in DEFS if d[0] == name.split(b'+')[0])
                entry = (name, level) + base_def[2:13] + (base_def[13] | flags, base_def[14])
            (name, level, weight, count, dmin, dmax, price, armor, attack, slot, category, subtype,
             bits, flags, picture) = entry
            exe.poke(addr, struct.pack('<Ih2xfhhh2xihhbbb1xI4xQI', exe.text(name), level, weight, count, dmin,
                                       dmax, price, armor, attack, slot, category, subtype, bits, flags,
                                       exe.text(picture) if picture else 0))
            exe.poke(addr + 0x34, struct.pack('<h', index))

    rows(R.A_DEFS, DEFS, False)
    rows(R.A_PRESETS, PRESETS, True)
    for index, (key, level, texts, mask, damage) in enumerate(PREFIXES):
        addr = R.A_PREFIXES + index * 0x28
        exe.poke(addr, struct.pack('<Ih', exe.text(key), level))
        exe.poke(addr + 0xC, struct.pack('<3I', *[exe.text(t) if t else 0 for t in texts]))
        exe.poke(addr + 0x18, struct.pack('<QI', mask, damage))
    for index, (key, level, texts) in enumerate(SUFFIXES):
        addr = R.A_SUFFIXES + index * 0x14
        exe.poke(addr, struct.pack('<Ih', exe.text(key), level))
        exe.poke(addr + 8, struct.pack('<3I', *[exe.text(t) if t else 0 for t in texts]))
    for row in range(12):
        exe.poke(R.A_QUALITY + 12 * row, struct.pack('<3f', max(0.6 - 0.07 * row, 0.0), 0.3, 0.1))
    exe.poke(R.A_WEAPON_MULT, struct.pack('<7f', 1.0, 0.8, 0.8, 0.9, 1.0, 1.0, 1.0))
    exe.poke(R.A_MANA_POTIONS, struct.pack('<9I', *[exe.text(b'bluevial')] * 9))
    exe.poke(R.A_HEAL_POTIONS, struct.pack('<9I', *[exe.text(b'redvial')] * 9))
    exe.poke(R.A_GOLD_SCALE_MP, struct.pack('<d', 2.0))
    for addr, value in ((R.S_ARROWS, b'bolts'), (R.S_NAME_SUFFIX, b'%s.txt'), (R.S_SPACE, b' '),
                        (R.S_OF_KEY, b'link'), (R.S_THROWN_STEM, b'dart'), (R.S_POTION_STEM, b'vial'),
                        (R.S_CIRCLET_STEM, b'band'), (R.S_RECALL, b'homevial'),
                        (R.S_CIRCLET_STEM_EQUIP, b'band')):
        exe.poke(addr, value + b'\0')
    return R.Tables(exe)


T = fake_tables()


def item_of(text, seed=1, variant=-1):
    return R.parse_descriptor(T, text, variant, False, R.Rng(seed))


def seeds(count):
    """Start seeds that are far apart (neighbouring seeds give neighbouring first draws)."""
    return [(index * 0x9E3779B1 + 0x1234567) & 0xFFFFFFFF for index in range(count)]


class FloatKernel(unittest.TestCase):
    def test_exact_cases(self):
        self.assertEqual(R.fmul(F(1.5), F(2.0)), F(3.0))
        self.assertEqual(R.fadd(F(0.25), F(0.5)), F(0.75))
        self.assertEqual(R.fsub(F(1.0), F(1.0)), 0)
        self.assertEqual(R.fint(-7), F(-7.0))
        self.assertEqual(R.ftrunc(F(-2.9)), -2)
        self.assertEqual(R.ftrunc(F(2.9)), 2)

    def test_results_are_truncated_not_rounded(self):
        self.assertEqual(R.fdiv(F(1.0), F(3.0)), 0x3EAAAAAA)       # IEEE rounding gives ...AB
        self.assertEqual(R.fint(16777217), 0x4B800000)
        self.assertEqual(R.fmul(0x3F7FFFFF, 0x3F7FFFFF), 0x3F7FFFFE)

    def test_no_infinity(self):
        self.assertEqual(R.fmul(F(1e30), F(1e30)), 0x7FFFFFFF)
        self.assertEqual(R.fdiv(F(1.0), 0), 0x7FFFFFFF)
        self.assertEqual(R.fdiv(F(-1.0), 0), 0xFFFFFFFF)
        self.assertEqual(R.fmul(F(1e-30), F(1e-30)), 0)
        self.assertEqual(R.ftrunc(0x7FFFFFFF), 0x7FFFFFFF)

    def test_small_addend_is_dropped(self):
        self.assertEqual(R.fadd(F(2.0 ** 30), F(1.0)), F(2.0 ** 30))

    def test_compare(self):
        self.assertTrue(R.flt(F(-1.0), 0))
        self.assertFalse(R.flt(0, 0x80000000))
        self.assertTrue(R.fle(0, 0x80000000))

    def test_float_times_double_truncates_the_exact_product(self):
        self.assertEqual(R.float_times_double(F(0.5), 1.5), F(0.75))
        for value in (0.1, 0.6, 1.8, 3.0, 123.456):
            raw = F(value)
            exact = Fraction(R.f_value(raw)) * Fraction(2.4)
            got = Fraction(R.f_value(R.float_times_double(raw, 2.4)))
            self.assertLessEqual(got, exact)
            self.assertGreater(Fraction(R.f_value(R.float_times_double(raw, 2.4) + 1)), exact)


class Power(unittest.TestCase):
    def test_shortcuts(self):
        self.assertEqual(R.powf(F(4.0), F(2.0)), F(16.0))
        self.assertEqual(R.powf(F(7.25), F(1.0)), F(7.25))
        self.assertEqual(R.powf(F(7.25), 0), F(1.0))
        self.assertEqual(R.powf(0, 0x3FF99999), 0)
        with self.assertRaises(NotImplementedError):
            R.powf(F(4.0), F(0.5))

    def test_close_to_the_true_power(self):
        exponents = sorted(set(R._VALUE_EXPONENT.values()) | {0x3FF99999, 0x3F28F5C2})
        for step in range(1, 400):
            x = step * 0.37
            for y in exponents:
                want = math.pow(R.f_value(F(x)), R.f_value(y))
                got = R.f_value(R.powf(F(x), y))
                self.assertLess(abs(got - want), 2e-6 * want, (x, y))

    def test_negative_base_gives_the_largest_number(self):
        # 0/0 on this FPU is the largest magnitude, not a NaN
        self.assertEqual(R.powf(F(-2.0), 0x3FF99999), 0x7FFFFFFF)


class Generator(unittest.TestCase):
    def test_sequence(self):
        rng, seed = R.Rng(0), 0
        for _ in range(5):
            seed = (seed * 1664525 + 1013904223) % 2 ** 32
            self.assertEqual(rng.next(), seed >> 16)
        self.assertEqual((rng.seed, rng.draws), (seed, 5))


class Scanner(unittest.TestCase):
    def test_conversions(self):
        self.assertEqual(R.scan(b'ab%d', b'ab12'), (1, [12]))
        self.assertEqual(R.scan(b'ab%d', b'ab -7x'), (1, [-7]))
        self.assertEqual(R.scan(b'ab%d', b'ab+7'), (1, [7]))
        self.assertEqual(R.scan(b'ab%d-%d', b'ab3-4'), (2, [3, 4]))
        self.assertEqual(R.scan(b'ab%d-%d', b'ab3-'), (1, [3]))
        self.assertEqual(R.scan(b'ab%d-%d', b'ab3,4'), (1, [3]))
        self.assertEqual(R.scan(b'ab%d,%d-%d', b'ab3,4-5'), (3, [3, 4, 5]))

    def test_end_of_text_before_a_value_is_minus_one(self):
        for text in (b'', b'a', b'ab', b'ab '):
            self.assertEqual(R.scan(b'ab%d', text)[0], -1, text)

    def test_mismatch_is_zero(self):
        for text in (b'ac1', b'b', b'ab-', b'abx', b'ab-x', b'AB1'):
            self.assertEqual(R.scan(b'ab%d', text)[0], 0, text)

    def test_huge_numbers_saturate_a_64_bit_long_then_lose_their_top(self):
        self.assertEqual(R.scan(b'ab%d', b'ab99999999999999999999'), (1, [-1]))
        self.assertEqual(R.scan(b'ab%d', b'ab-99999999999999999999'), (1, [0]))
        self.assertEqual(R.scan(b'ab%d', b'ab4294967298'), (1, [2]))


class Parser(unittest.TestCase):
    def test_defaults(self):
        item = item_of(b'dart')
        self.assertIs(item.definition, T.defs[3])
        self.assertEqual((item.count, item.flags, item.prefix, item.suffix), (40, 0, 0xFF, 0xFF))
        self.assertEqual(item.mods, [None] * 4)
        self.assertEqual(item.a + item.b, [0] * 8)

    def test_unknown_name_is_row_zero(self):
        self.assertIs(item_of(b'nothing').definition, T.defs[0])
        self.assertIs(R.parse_descriptor(T, b'nothing', 0, True).definition, T.presets[0])

    def test_tokens_fill_slots_in_order(self):
        item = item_of(b'dart+tokaa5+tokab3-4+tokad1,2-3')
        self.assertEqual(item.mods[:3], [[R.TOKEN_FORMATS[0][1], 5, 0, 0], [R.TOKEN_FORMATS[1][1], 3, 4, 0],
                                         [R.TOKEN_FORMATS[3][1], 1, 2, 3]])
        self.assertIsNone(item.mods[3])

    def test_repeat_overwrites_and_fifth_is_dropped(self):
        item = item_of(b'dart+tokaa5+tokae1+tokai2+tokam3+tokaq4+tokaa9')
        self.assertEqual([m[0] for m in item.mods], [R.TOKEN_FORMATS[i][1] for i in (0, 4, 8, 12)])
        self.assertEqual(item.mods[0][1], 9)

    def test_values_are_stored_as_16_bits(self):
        self.assertEqual(item_of(b'dart+tokaa65537').mods[0][1], 1)
        self.assertEqual(item_of(b'dart+tokaa-3').mods[0][1], -3)

    def test_empty_and_truncated_tokens_match_the_first_format_that_runs_out_of_text(self):
        for text in (b'dart+', b'dart++tokae1', b'dart+t', b'dart+tok', b'dart+tokaa'):
            self.assertEqual(item_of(text).mods[0], [R.TOKEN_FORMATS[0][1], 0, 0, 0], text)
        self.assertEqual(item_of(b'dart+tokae').mods[0], [R.TOKEN_FORMATS[4][1], 0, 0, 0])
        self.assertEqual(item_of(b'dart+zzz').mods, [None] * 4)

    def test_variant(self):
        self.assertEqual(item_of(b'blade', variant=1).variant, 1)
        self.assertEqual(item_of(b'blade+tokbp1', variant=0).variant, 1)           # the mesh format
        self.assertEqual(item_of(b'blade+tokbp33', variant=0).flags, 33 << 11)      # not masked to five bits
        rng = R.Rng(5)
        item = R.parse_descriptor(T, b'blade', -1, False, rng)
        self.assertEqual((rng.draws, item.variant), (1, R.Rng(5).next() % 2))
        rng = R.Rng(5)
        R.parse_descriptor(T, b'dart', -1, False, rng)
        self.assertEqual(rng.draws, 0)                                               # no variants: no draw

    def test_preset_lookup_uses_the_whole_text(self):
        item = R.parse_descriptor(T, b'cap+tokae3', 0, True)
        self.assertIs(item.definition, T.presets[1])
        self.assertEqual(item.mods[0], [R.TOKEN_FORMATS[4][1], 3, 0, 0])
        self.assertEqual(R.encode_definition_index(T, item), (R.A_PRESETS + 0x40 - R.A_DEFS) >> 6)

    def test_too_long(self):
        with self.assertRaises(ValueError):
            item_of(b'dart+' + b'x' * 300)


class Record(unittest.TestCase):
    def test_pack_round_trip_and_unwritten_bytes(self):
        item = item_of(b'blade+tokaa5+tokab3-4', variant=1)
        item.prefix = 2
        stale = bytes(range(0x48))
        raw = item.pack(stale)
        self.assertEqual(len(raw), 0x48)
        for offset in item.undefined_offsets():
            self.assertEqual(raw[offset], stale[offset])
        self.assertEqual(sorted(item.undefined_offsets()),
                         [6, 7, 0x22, 0x23] + list(range(0x36, 0x3C)) + list(range(0x3E, 0x48)))
        back = R.Item.unpack(T, raw)
        self.assertEqual(back.pack(stale), raw)
        self.assertIs(back.definition, item.definition)

    def test_identity_and_copy(self):
        a, b = item_of(b'blade+tokaa5', variant=1), item_of(b'blade+tokae9', variant=1)
        self.assertTrue(R.same_identity(a, b))
        b.suffix = 1
        self.assertFalse(R.same_identity(a, b))
        target = item_of(b'dart')
        R.copy_mutable(target, a)
        self.assertIs(target.definition, T.defs[3])
        self.assertEqual((target.flags, target.mods), (a.flags, a.mods))

    def test_definition_index(self):
        for d in T.defs + T.presets:
            item = R.Item(d)
            self.assertIs(R.decode_definition_index(T, R.encode_definition_index(T, item)), d)
        self.assertLess(R.encode_definition_index(T, R.Item(T.presets[0])), 0)


class Statistics(unittest.TestCase):
    def test_weight(self):
        self.assertEqual(R.item_weight(item_of(b'blade')), F(4.0))
        self.assertEqual(R.item_weight(item_of(b'dart')), F(20.0))                 # 0.5 x 40
        heavy = R.f_value(R.item_weight(item_of(b'maul')))                          # above 15: compressed
        self.assertAlmostEqual(heavy, 28 - 13 * 0.7692308, places=4)
        armour = R.f_value(R.item_weight(item_of(b'vest')))                         # armour: above 5
        self.assertAlmostEqual(armour, 9 - 4 * 0.7692308, places=4)
        item = item_of(b'blade')
        item.set_modifier(0x24, -50)
        self.assertAlmostEqual(R.f_value(R.item_weight(item)), 2.0, places=5)

    def test_armor_attack_damage(self):
        # 0.01 is not exact and every product is truncated, so a percentage whose exact
        # result is a whole number comes out one short: +50% of 12 is 17.
        item = item_of(b'vest')
        self.assertEqual(R.item_armor(item), 12)
        item.set_modifier(0x0D, 50)
        self.assertEqual(R.item_armor(item), 17)
        item.set_modifier(0x0D, -75)
        self.assertEqual(R.item_armor(item), 4)
        item.set_modifier(0x0D, 51)
        self.assertEqual(R.item_armor(item), 18)
        blade = item_of(b'blade')
        self.assertEqual((R.item_damage_range(blade), R.item_attack_rating(blade)), ((4, 9), 6))
        blade.set_modifier(0x23, 50)
        self.assertEqual((R.item_damage_range(blade), R.item_attack_rating(blade)), ((6, 13), 8))
        blade.set_modifier(0x15, 3, 7)
        self.assertEqual(R.item_damage_range(blade), (9, 20))
        self.assertEqual(R.item_damage_range(blade, False), (6, 13))

    def test_value(self):
        self.assertEqual(R.item_value(T, item_of(b'bolts')), 2 * 20)               # fixed price x count
        plain = R.item_value(T, item_of(b'trinket'))
        self.assertLess(abs(plain - 40 * 5 ** 1.95), 1.0)
        ring = R.item_value(T, item_of(b'ring'))
        self.assertLess(abs(ring - 40 * 5 ** 1.95 * 8.009912), 1.0)
        thrown = item_of(b'dart')
        base = R.item_value(T, thrown) / 40
        self.assertGreater(base, 0)
        blade, better = item_of(b'blade'), item_of(b'blade')
        better.set_modifier(0x23, 50)
        self.assertGreater(R.item_value(T, better), R.item_value(T, blade))
        cheaper = item_of(b'blade')
        cheaper.set_modifier(0x25, -50)
        self.assertLess(abs(R.item_value(T, cheaper) * 2 - R.item_value(T, blade)), 2)

    def test_negative_modifier_value_saturates(self):
        item = item_of(b'trinket')
        item.set_modifier(0x05, -4)
        self.assertEqual(R.item_value(T, item), 0x7FFFFFFF)

    def test_required_level(self):
        self.assertEqual(R.required_level_for_value(0), 1)
        self.assertEqual(R.required_level_for_value(6199), 1)
        self.assertEqual(R.required_level_for_value(6200), 3)
        levels = [R.required_level_for_value(v) for v in range(0, 30000000, 50000)]
        self.assertEqual(levels, sorted(levels))
        self.assertEqual(levels[-1], 80)
        self.assertTrue(all(level % 2 == 1 or level == 80 for level in levels))


class Generators(unittest.TestCase):
    def test_groups(self):
        self.assertEqual([R.weapon_group(d) for d in T.defs[:5]], [2, 2, 1, 0, -1])
        self.assertEqual([R.armor_group(d) for d in T.defs[3:8]], [-1, 0, 1, 1, 4])

    def test_with_affixes_is_deterministic_and_within_limits(self):
        made = 0
        for index, start in enumerate(seeds(60)):
            seed = index
            game = R.Game(1, (seed % 7, 0, 0, 0), 1, level=5.0)
            args = (T, game, None, 4000, seed % 3, -1, 2 + seed % 9)
            first_rng, second_rng = R.Rng(start), R.Rng(start)
            first = R.generate_with_affixes(args[0], args[1], first_rng, *args[3:])
            second = R.generate_with_affixes(args[0], args[1], second_rng, *args[3:])
            self.assertEqual(first_rng.seed, second_rng.seed)
            if first is None:
                self.assertIsNone(second)
                continue
            made += 1
            self.assertEqual(first.pack(), second.pack())
            self.assertEqual(first.definition.category, seed % 3)
            self.assertLessEqual(first.definition.level, 2 + seed % 9)
            self.assertFalse(first.definition.flags & (NO_RANDOM | REAGENT | FIGURINE))
            if first.prefix != 0xFF:
                self.assertLessEqual(T.prefixes[first.prefix].level, 2 + seed % 9)
            if first.suffix != 0xFF:
                self.assertLessEqual(T.suffixes[first.suffix].level, 2 + seed % 9)
            if b'vial' not in first.definition.name:
                self.assertGreaterEqual(first.get(0x0E), 1)
        self.assertGreater(made, 30)

    def test_budget(self):
        self.assertIsNone(R.generate_with_affixes(T, R.Game(), R.Rng(3), 0, 1, -1, 9))
        for seed in seeds(30):
            item = R.generate_with_affixes(T, R.Game(), R.Rng(seed), 600, 1, 1, 9)
            if item is not None:
                check = item.copy()
                self.assertLessEqual(R.item_value(T, check), 600)

    def test_cloth_steering(self):
        def cloth_kinds(game):
            made = [R.generate_with_affixes(T, game, R.Rng(seed), 10 ** 6, 1, -1, 9) for seed in seeds(150)]
            return {bool(item.definition.flags & CLOTH) for item in made if item is not None}
        self.assertEqual(cloth_kinds(R.Game(1, (0, 0, 0, 0))), {False})      # nobody of class 4: no cloth
        self.assertEqual(cloth_kinds(R.Game(2, (4, 0, 0, 0))), {True, False})
        self.assertEqual(cloth_kinds(R.Game(1, (4, 0, 0, 0))), {True, False})

    def test_preset(self):
        seen = set()
        for seed in seeds(80):
            rng = R.Rng(seed)
            item = R.generate_preset(T, R.Game(1, (4, 0, 0, 0)), rng, 10 ** 6, -1, 3)
            self.assertIsNotNone(item)
            self.assertTrue(item.definition.preset)
            seen.add(item.definition.index)
        self.assertTrue(seen)
        self.assertIsNone(R.generate_preset(T, R.Game(), R.Rng(1), 10 ** 6, 2, 2))   # the ring is level 3
        rng = R.Rng(1)
        self.assertIsNone(R.generate_preset(T, R.Game(), rng, -5, 0, 9))
        self.assertEqual(rng.draws, 10 + 10)                    # ten picks, each parse draws a variant

    def test_reagent_and_figurine(self):
        game = R.Game(difficulty=1)
        self.assertEqual(R.generate_reagent(T, game, R.Rng(1), 5).definition.name, b'dust')
        self.assertIsNone(R.generate_reagent(T, game, R.Rng(1), 2))
        self.assertEqual({R.generate_reagent(T, game, R.Rng(s), 25).definition.name for s in seeds(40)},
                         {b'dust', b'shard'})
        self.assertEqual(R.generate_reagent(T, game, R.Rng(1), 25, b'shardpic').definition.name, b'shard')
        self.assertIsNone(R.generate_reagent(T, game, R.Rng(1), 25, b'nopic'))
        hard = R.Game(difficulty=2)                              # floor 17: the level-3 rows drop out
        self.assertEqual(R.generate_reagent(T, hard, R.Rng(1), 25).definition.name, b'shard')
        self.assertIsNone(R.generate_figurine(T, hard, R.Rng(1), 25))
        self.assertEqual(R.generate_figurine(T, game, R.Rng(1), 25).definition.name, b'idol')
        self.assertEqual(R.generate_figurine(T, game, R.Rng(1), 0x10003).definition.name, b'idol')

    def test_consumable(self):
        names = {R.generate_consumable(T, R.Game(level=3.0), R.Rng(s)).definition.name for s in seeds(200)}
        self.assertEqual(names, {b'redvial', b'bluevial', b'homevial'})
        names = {R.generate_consumable(T, R.Game(level=3.0, pvp_b=1), R.Rng(s)).definition.name for s in seeds(200)}
        self.assertEqual(names, {b'redvial', b'bluevial'})

    def test_shop(self):
        stock, rng = [], R.Rng(11)
        for _ in range(12):
            try:
                R.shop_append_unique(T, R.Game(), rng, stock, 10 ** 6, 1)
            except NotImplementedError:
                pass
        pairs = [(e.definition.index, e.flags) for e in stock]
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertTrue(stock)

    def test_load_resources(self):
        rng = R.Rng(9)
        self.assertEqual(R.load_resources(T, rng), sum(1 for d in T.defs if (d.flags >> 11) & 0x1F))


class Loot(unittest.TestCase):
    ARGS = (F(1.0), F(0.5), F(2.0), F(0.5))

    def run_loot(self, seed, game=None, **kw):
        world, rng = R.World(), R.Rng(seed)
        ending = R.loot_generate_drops(T, game or R.Game(level=8.0), rng, world, *self.ARGS, **kw)
        return ending, world.drops, rng

    def test_deterministic_and_ordered(self):
        order = {'gold': 0, 'consumable': 1, 'reagent': 2, 'figurine': 3, 'equipment': 4, 'throw': 5}
        kinds = set()
        for seed in seeds(400):
            ending, drops, rng = self.run_loot(seed)
            again = self.run_loot(seed)
            self.assertEqual((ending, rng.seed, [k for k, _ in drops]), (again[0], again[2].seed, [k for k, _ in again[1]]))
            ranks = [order[kind] for kind, _ in drops]
            self.assertEqual(ranks, sorted(ranks))
            self.assertGreaterEqual(rng.draws, 6)
            kinds.update(kind for kind, _ in drops)
            if ending == 'done':
                self.assertEqual(drops[-1][0], 'throw')
                self.assertLessEqual(abs(drops[-1][1]), 0x2000)
        self.assertLessEqual({'gold', 'consumable', 'equipment', 'throw'}, kinds)

    def test_no_gold_in_pvp_mode_a_and_fixed_chance_in_mode_b(self):
        for seed in seeds(100):
            self.assertNotIn('gold', [k for k, _ in self.run_loot(seed, R.Game(level=8.0, pvp_a=1))[1]])

    def test_minimum_draws_when_nothing_drops(self):
        world, rng = R.World(), R.Rng(77)
        ending = R.loot_generate_drops(T, R.Game(level=8.0), rng, world, F(1.0), 0, 0, 0)
        if not world.drops:
            # quality, gold count, 1-3 gold chances, consumable, reagent, figurine, equipment
            self.assertIn(rng.draws, (7, 8, 9))
            self.assertEqual(ending, 'no equipment roll')

    def test_early_return_when_a_reagent_roll_has_nothing_to_give(self):
        low = R.Game(level=2.0)                                  # half level 1: no reagent row fits
        endings = {self.run_loot(seed, low)[0] for seed in seeds(3000)}
        self.assertIn('no reagent', endings)
        self.assertEqual(R.half_level(R.Game(level=7.9)), 3)

    def test_refused_allocation_skips_the_throw(self):
        class Full(R.World):
            def spawn_item(self, kind, item, rng):
                return False
        for seed in seeds(300):
            world, rng = Full(), R.Rng(seed)
            ending = R.loot_generate_drops(T, R.Game(level=8.0), rng, world, *self.ARGS)
            self.assertNotIn('throw', [k for k, _ in world.drops])
            if ending == 'done':
                plain, plain_rng = R.World(), R.Rng(seed)
                R.loot_generate_drops(T, R.Game(level=8.0), plain_rng, plain, *self.ARGS)
                self.assertEqual(plain_rng.draws, rng.draws + 1)

    def test_gold_scatter(self):
        rng = R.Rng(4)
        x, y, z = R.gold_scatter(rng, lambda px, py, pz: pz, F(100.0), F(200.0), F(5.0))
        self.assertEqual(rng.draws % 3, 0)
        self.assertEqual(z, F(5.0))
        self.assertLessEqual(math.hypot(R.f_value(x) - 100, R.f_value(y) - 200), 36.001)
        rng = R.Rng(4)
        self.assertEqual(R.gold_scatter(rng, lambda px, py, pz: F(500.0), F(1.0), F(2.0), F(3.0)),
                         (F(1.0), F(2.0), F(3.0)))
        self.assertGreaterEqual(rng.draws, 30)

    def test_named_drop(self):
        world, rng = R.World(), R.Rng(2)
        item = R.spawn_named_item(T, rng, world, b'blade+tokaa5')
        self.assertEqual(world.drops, [('named', item)])
        self.assertEqual(rng.draws, 1)


class Names(unittest.TestCase):
    TEXT = {'blade.txt': 'Sabre_fs', 'dull': 'mat_ms|matte_fs|mats_mp|mattes_fp', 'fine': 'fin', 'ash': 'Asche',
            'link': 'von', 'cap.txt': 'Hut_m', 'ring.txt': 'Reif'}

    def name(self, text, language, prefix=0xFF, suffix=0xFF, decorated=True, table=None):
        item = item_of(text, variant=0)
        item.prefix, item.suffix = prefix, suffix
        return R.build_name(T, item, decorated, (table or self.TEXT).__getitem__, language)

    def test_default_order(self):
        self.assertEqual(self.name(b'ring', 0), 'Reif')
        self.assertEqual(self.name(b'ring', 0, prefix=1, suffix=0), 'fin Reif von Asche')
        self.assertEqual(self.name(b'ring', 0, prefix=0), 'mat_ms Reif')          # first alternative, tag kept
        self.assertEqual(self.name(b'blade', 0), 'Sabre_fs')                       # no tags in this language

    def test_two_letter_tags(self):
        for language in (1, 3):
            self.assertEqual(self.name(b'blade', language), 'Sabre')
            self.assertEqual(self.name(b'blade', language, prefix=0, suffix=0), 'Sabre matte Asche')
            self.assertEqual(self.name(b'ring', language, prefix=1), 'Reif fin')

    def test_one_letter_tags(self):
        table = dict(self.TEXT, dull='matter|matte|mattes|matten')
        self.assertEqual(self.name(b'cap', 4, table=table), 'Hut')
        self.assertEqual(self.name(b'cap', 4, prefix=0, suffix=0, table=table), 'matter Hut Asche')
        self.assertEqual(self.name(b'ring', 4, prefix=0, table=table), 'mattes Reif')

    def test_plain(self):
        self.assertEqual(self.name(b'ring', 0, prefix=1, suffix=0, decorated=False), 'Reif')
        item = item_of(b'ring', variant=0)
        item.flags |= 0x200
        item.prefix = 1
        self.assertEqual(R.build_name(T, item, True, self.TEXT.__getitem__, 0), 'Reif')

    def test_uncovered_input_is_refused(self):
        with self.assertRaises(ValueError):
            self.name(b'ring', 0, prefix=1, table=dict(self.TEXT, fine='50% fin'))

    def test_strip(self):
        self.assertEqual(R.strip_grammar_suffix('Hut_m', 4), ('Hut', 1))
        self.assertEqual(R.strip_grammar_suffix('Hut_q', 4), ('Hut', 0))
        self.assertEqual(R.strip_grammar_suffix('Hut', 4), ('Hut', 0))
        self.assertEqual(R.strip_grammar_suffix('Sabre_FP', 1), ('Sabre', 4))
        self.assertEqual(R.strip_grammar_suffix('Sabre_f', 3), ('Sabre', 2))
        self.assertEqual(R.strip_grammar_suffix('Sabre', 3), ('Sabre', 1))
        self.assertEqual(R.strip_grammar_suffix('Sabre_fs', 0), ('Sabre_fs', 0))


class Requirements(unittest.TestCase):
    def test_reasons(self):
        blade = item_of(b'blade')
        ok = R.Player(0, 20, 20, 20, 20, 20)
        self.assertEqual(R.equip_restriction(T, ok, blade), R.EQUIP_OK)
        for code, reason, field in ((0x0E, R.EQUIP_LEVEL, 'level'), (0x0F, R.EQUIP_STRENGTH, 'strength'),
                                    (0x10, R.EQUIP_INTELLIGENCE, 'intelligence'),
                                    (0x11, R.EQUIP_DEXTERITY, 'dexterity'), (0x12, R.EQUIP_STAMINA, 'stamina')):
            item = item_of(b'blade')
            item.set_modifier(code, 15)
            self.assertEqual(R.equip_restriction(T, ok, item), R.EQUIP_OK)
            low = R.Player(0, 20, 20, 20, 20, 20)
            setattr(low, field, 14)
            self.assertEqual(R.equip_restriction(T, low, item), reason)

    def test_class_rules(self):
        self.assertEqual(R.equip_restriction(T, R.Player(1), item_of(b'blade')), R.EQUIP_CLASS)   # slashing
        self.assertEqual(R.equip_restriction(T, R.Player(1), item_of(b'maul')), R.EQUIP_CLASS)    # subtype 3
        self.assertEqual(R.equip_restriction(T, R.Player(0), item_of(b'robe')), R.EQUIP_CLASS)    # cloth
        self.assertEqual(R.equip_restriction(T, R.Player(4), item_of(b'robe')), R.EQUIP_OK)
        self.assertEqual(R.equip_restriction(T, R.Player(4), item_of(b'vest')), R.EQUIP_CLASS)
        item = item_of(b'dart')
        item.set_modifier(0x13, 3)                              # requiredclass holds class + 1
        self.assertEqual(R.equip_restriction(T, R.Player(2), item), R.EQUIP_OK)
        self.assertEqual(R.equip_restriction(T, R.Player(3), item), R.EQUIP_CLASS)

    def test_skill_requirements(self):
        item = item_of(b'dart')
        item.set_modifier(0x27, 2)
        self.assertEqual(R.equip_restriction(T, R.Player(0), item), R.EQUIP_BLUNT)
        self.assertEqual(R.equip_restriction(T, R.Player(0, skills={0x3C: 2}), item), R.EQUIP_OK)


if __name__ == '__main__':
    unittest.main()
