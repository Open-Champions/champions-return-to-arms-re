"""Synthetic locks for skill-driven player animation. No ELF."""
import unittest
import ref_skill_anim as S


class SkillAnimTest(unittest.TestCase):
    def test_state6_starts_one_clip_and_stores_6(self):
        names = [row['name'] for row in S.STATE6]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(S.STATE6), 7)
        for row in S.STATE6:
            self.assertEqual(row['state'], 6)
            self.assertEqual(len(row['anim']), 5)
            self.assertIn(row['anim'][1], row['names'])

    def test_ancestral_does_set_state_6(self):
        row = S.state6_by_name('SpellAncestralCall_ctor')
        self.assertEqual(row['state'], 6)
        self.assertEqual(row['anim'][1], 'ohw_warcry.anm')
        self.assertEqual(row['anim'][2], 0x22)

    def test_charge_needs_object_flag(self):
        self.assertEqual(S.charge_state(0x40), 9)
        self.assertEqual(S.charge_state(0), 0)
        self.assertEqual(S.charge_state(0x41), 9)
        self.assertEqual(S.charge_state(0x20), 0)

    def test_shadow_step_flags_and_end(self):
        self.assertEqual(S.SHADOW_STATE, 0xe)
        self.assertEqual(S.SHADOW_FLAGS_AFTER_CTOR, 0x45)
        self.assertEqual(S.SHADOW_END_STATE, 2)
        self.assertEqual(S.SHADOW_FLAGS_AFTER_DTOR, 0x40)
        self.assertEqual(S.SHADOW_ANIM[2], 0x4)

    def test_no_skill_here_stores_state_7(self):
        states = [row['state'] for row in S.STATE6]
        states += [S.charge_state(0x40), S.SHADOW_STATE, S.SHADOW_END_STATE]
        self.assertNotIn(7, states)


if __name__ == '__main__':
    unittest.main()
