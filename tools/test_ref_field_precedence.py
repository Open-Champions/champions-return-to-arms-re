"""Synthetic locks for two-field setState precedence. No ELF.

Also checks that round 3's select() still answers the one-word Agony probes
the same way. Combined values are not fed to select(); it is specified to
raise on a condition it did not record.
"""
import unittest
import ref_creature_dispatch as D
import ref_creature_dispatch_data as T
import ref_field_precedence as P


class FieldPrecedenceTest(unittest.TestCase):
    def test_agony_knockback_wins_over_hit(self):
        self.assertEqual(P.agony_hit_entry(0), 0xa)
        self.assertEqual(P.agony_hit_entry(1), 0xa)
        self.assertEqual(P.agony_hit_entry(0x40000), 9)
        self.assertEqual(P.agony_hit_entry(0x40001), 9)
        for bit in (0x80000, 0x100000, 0x200000, 0x380000):
            self.assertEqual(P.agony_hit_entry(bit), 0xd)
            self.assertEqual(P.agony_hit_entry(bit | 0x40000), 0xd)
        self.assertEqual(P.agony_hit_entry(0xffffffff), 0xd)

    def test_select_one_word_rows_unchanged(self):
        case = D.case_for(T.DISPATCH['Agony'], 0x12)
        ops, stored = D.select(case, field=(0x2dc, 0x40000))
        self.assertEqual(ops[0][1], 9)
        self.assertEqual(stored, 0x12)
        ops, stored = D.select(case, field=(0x2dc, 0x80000))
        self.assertEqual(ops[0][1], 0xd)
        with self.assertRaises(KeyError):
            D.select(case, field=(0x2dc, 0x40000 | 0x80000))

    def test_clockwork_or_is_a_third_index(self):
        self.assertEqual(P.clockwork_idle_entry(0), 0xa)
        self.assertEqual(P.clockwork_idle_entry(1 | 2), 40)
        self.assertEqual(P.clockwork_idle_entry(3), 40)
        self.assertEqual(P.clockwork_idle_entry(4), 50)
        self.assertEqual(P.clockwork_idle_entry(1 | 4), 60)
        self.assertIsNone(P.clockwork_idle_entry(2 | 4))

    def test_combined_winners(self):
        ops, stored = P.combined('FemaleDarkElf', 0x12,
                                 ((0x2dc, 0x80000), (0x3c8, 1)))
        self.assertEqual(ops[0][:2], ('anim_start', 4))
        self.assertEqual(stored, 0x12)
        ops, stored = P.combined('Horsemen', 0x14, ((0x3c8, 1), (0x470, 3)))
        self.assertEqual(ops, ())
        self.assertEqual(stored, 0)
        ops, stored = P.combined('VampireLord', 0x11, ((0x3c8, 1), (0x3cc, 1)))
        self.assertEqual(ops[0][1], 11)
        ops, stored = P.combined('Clockwork', 0x14, ((0xc, 2), (0x3c8, 4)))
        self.assertEqual(ops[0][1], 46)
        self.assertEqual(len(P.COMBINED), 7)


if __name__ == '__main__':
    unittest.main()
