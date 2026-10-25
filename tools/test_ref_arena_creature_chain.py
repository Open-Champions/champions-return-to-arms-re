"""Synthetic checks of tools/ref_arena_creature_chain.py (no game files)."""
import unittest

import ref_arena_creature_chain as R
import ref_arena_match_classes as AC
import ref_core as C


class Memory:
    def __init__(self):
        self.words = {}

    def u32(self, addr):
        return self.words.get(addr, 0)

    def w16(self, addr, value):
        word = self.words.get(addr & ~3, 0)
        shift = 8 * (addr & 2)
        self.words[addr & ~3] = (word & ~(0xFFFF << shift)) | ((value & 0xFFFF) << shift)


def hash_by_hand(name):
    """docs/data-tables.md's listing, written out separately."""
    h = 0
    for c in name.lower():
        h = ((h + c) & 0xFFFF) * 0x401 & 0xFFFF
        h ^= h >> 6
    h = h * 9 & 0xFFFF
    return ((h >> 11) ^ h) * 0x8001 & 0xFFFF


class BalanceTests(unittest.TestCase):
    def table(self, records, count=None):
        mem = Memory()
        base = 0x1000
        for k, rec in enumerate(records):
            for j, value in enumerate(rec):
                mem.w16(base + 12 * k + 2 * j, value)
        mem.words[R.BALANCE_RECORDS] = base
        mem.words[R.BALANCE_COUNT] = len(records) if count is None else count
        return mem

    def test_hash_matches_listing_and_ignores_case(self):
        for name in (b'a', b'Goblin', b'orc2', b'snobadge', b'Z_9'):
            self.assertEqual(R.balance_hash(name), hash_by_hand(name))
        self.assertEqual(R.balance_hash(b'ABC'), R.balance_hash(b'abc'))

    def test_first_equal_hash_wins_and_values_are_unsigned_percent(self):
        h = R.balance_hash(b'thing')
        mem = self.table([(h ^ 1, 1, 1, 1, 1, 1), (h, 100, 200, 0xFFFF, 0, 50), (h, 7, 7, 7, 7, 7)])
        found, factors = R.balance_lookup(mem.u32, b'thing')
        self.assertEqual(found, 1)
        self.assertEqual(factors[0], C.mul(C.from_int(100), R.PERCENT))
        self.assertEqual(factors[2], C.mul(C.from_int(0xFFFF), R.PERCENT))
        self.assertEqual(factors[3], 0)

    def test_missing_null_and_empty(self):
        mem = self.table([(1, 2, 3, 4, 5, 6)])
        self.assertEqual(R.balance_lookup(mem.u32, b'absent' if R.balance_hash(b'absent') != 1 else b'other'),
                         (0, (C.ONE,) * 5))
        self.assertEqual(R.balance_lookup(mem.u32, None), (0, (C.ONE,) * 5))
        mem = self.table([(R.balance_hash(b'x'), 2, 3, 4, 5, 6)], count=0xFFFFFFFF)
        self.assertEqual(R.balance_lookup(mem.u32, b'x')[0], 0)


class CreatureInitTests(unittest.TestCase):
    def test_height_floor_and_byte(self):
        self.assertEqual(R.creature_init_height(0, 100), (C.from_int(100), 101))
        self.assertEqual(R.creature_init_height(10, 50), (R.HEIGHT_FLOOR, 85))
        self.assertEqual(R.creature_init_height(0, 84), (R.HEIGHT_FLOOR, 85))

    def test_empty_list_outside_cutscene(self):
        calls, fields = R.creature_init(0, 0x1234, {}, True, 0, (0, 90), 0)
        self.assertEqual(calls, [(R.MODEL_BOUNDS, 0x1234)])
        self.assertEqual(fields[0xA8], (8, 0))
        self.assertNotIn(0xE8, fields)

    def test_every_branch(self):
        props = {b'dead': b'1', b'change0': b'y', b'change31': b'y', b'coldweapons': b'2',
                 b'nomagicweapons': b'0', b'shockweapons': b'abc', b'initscript': b'go'}
        calls, fields = R.creature_init(1, 0x10, props, True, 0, (0, 1), 0xAB)
        self.assertEqual(calls[0], ('slot', 18))
        self.assertIn(('slot', 27, 0x14), calls)
        self.assertIn((R.HIDE_MASK, 0x10, 0x80000001), calls)
        self.assertEqual([c for c in calls if c[0] == 'holder'], [('holder', 4)])
        self.assertEqual(calls[-1], (R.SCRIPT_RUN,))
        self.assertEqual(fields[0xA8], (8, 1 | R.DEAD_FLAG))
        self.assertEqual(fields[0x220], (8, 0xAB))
        calls, _ = R.creature_init(0, 0, props, False, 1, (0, 1), 0)
        self.assertFalse([c for c in calls if c[0] in ('holder', R.SCRIPT_RUN, R.MODEL_BOUNDS)])

    def test_atoi(self):
        self.assertEqual([R.atoi(t) for t in (b'12x', b' -3', b'+4', b'abc', b'')], [12, -3, 4, 0, 0])

    def test_empty_string_is_present_property(self):
        props = {b'dead': b'', b'change0': b'', b'initscript': b''}
        calls, fields = R.creature_init(0, 0, props, False, 0, (0, 90), 0)
        self.assertIn(('slot', 27, 0x14), calls)
        self.assertIn((R.HIDE_MASK, 0, 1), calls)
        self.assertIn((R.SCRIPT_RUN,), calls)
        self.assertEqual(fields[0xE8], (4, 1))


class ChainPieces(unittest.TestCase):
    def test_entry_lookups_only_when_stale(self):
        mem = Memory()
        block = 0x2000
        mem.words.update({block + 8: 1, block + 0x10: 2, R.G_LUMP_GENERATION: 5})
        self.assertEqual(R.entry_lookups(mem.u32, block), [R.RES_FIND] * 2)
        mem.words[block + 4] = 5
        self.assertEqual(R.entry_lookups(mem.u32, block), [])

    def test_rare_roll_boundary(self):
        self.assertTrue(AC.rare_roll(6553))
        self.assertFalse(AC.rare_roll(6554))

    def test_fixture_mode_still_refuses_rare(self):
        # a fixture seed whose second own draw is rare must be refused, not modelled
        for seed in range(2000):
            shared, _ = AC.next_draw(seed)
            own, _ = AC.next_draw(shared)
            _, rare = AC.next_draw(own)
            if AC.rare_roll(rare):
                with self.assertRaises(AssertionError):
                    AC.constructor(AC.MUMMY, seed)
                kinds = AC.constructor(AC.MUMMY, seed, own=shared)
                self.assertIn(AC.RARE_MODIFIER, kinds[2])
                return
        self.fail('no rare seed found in the search range')


class FreeSpotTests(unittest.TestCase):
    CENTER = (C.f32(10.0), C.f32(-20.0), 0)

    def test_open_ground_takes_the_first_sample_inside_the_ball(self):
        seed = 12345
        after, p, draws = R.unit_ball_sample(seed)
        self.assertEqual(draws % 3, 0)
        self.assertEqual(after, R.lcg_n(seed, draws))
        got = R.free_spot(seed, self.CENTER, 36, 24, 0, lambda q: 0, lambda q: 0, lambda lo, hi: [])
        new_seed, spot, ok, tries, n, boxes = got
        self.assertEqual((new_seed, ok, tries, n), (after, 1, 1, draws))
        self.assertEqual(spot[0], C.add(C.mul(p[0], C.from_int(36)), self.CENTER[0]))
        self.assertEqual(len(boxes), 1)

    def test_blocked_everywhere_gives_up_after_fifty_tries(self):
        got = R.free_spot(7, self.CENTER, 36, 24, 0, lambda q: C.ONE, lambda q: 0, lambda lo, hi: [])
        self.assertEqual((got[1], got[2], got[3], got[5]), (self.CENTER, 0, 50, []))
        self.assertEqual(got[4] % 3, 0)

    def test_height_step_and_any_height(self):
        high = lambda q: C.f32(6.0)
        self.assertEqual(R.free_spot(7, self.CENTER, 36, 24, 0, lambda q: 0, high, lambda lo, hi: [])[2], 0)
        self.assertEqual(R.free_spot(7, self.CENTER, 36, 24, 1, lambda q: 0, high, lambda lo, hi: [])[2], 1)

    def test_blocker_rule_and_flag_one(self):
        def box(lo, hi):
            x = C.add(lo[0], C.f32(24.0))
            y = C.add(lo[1], C.f32(24.0))
            return [(x, y, C.f32(1.0), 0x21), (C.add(x, C.f32(24.0)), y, 0, 0x20)]
        # the flag-1 object is skipped; the other stands at exactly sqrt(radius^2): blocked
        got = R.free_spot(99, self.CENTER, 36, 24, 0, lambda q: 0, lambda q: 0, box)
        self.assertEqual((got[2], got[3]), (0, 50))


class OniBallTests(unittest.TestCase):
    def test_one_shared_and_five_own_draws(self):
        shared, own, fields, creature = R.oniball_ctor(20973, (0, 0, 0), 100, C.f32(200.0))
        first, own0 = R.lcg(20973)
        self.assertEqual(shared, first)
        self.assertEqual(own, R.lcg_n(own0, 5))
        self.assertEqual(fields[0x58], (4, 9))      # 200 x 0x3d4ccccc = 9.9999995, truncated
        self.assertEqual(fields[0x54], (4, 700))
        self.assertEqual(creature[0xF0], (4, 100))
        self.assertEqual(fields[0x18], (4, R.F_36))


if __name__ == '__main__':
    unittest.main()
