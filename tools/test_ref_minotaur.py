"""Synthetic tests for the authored Minotaur call-out contract (no game input)."""
import unittest

import ref_minotaur as contract


class MinotaurContractTests(unittest.TestCase):
    def test_invalid_state_falls_back(self):
        for state in (-1, 2, 4, 13, 14, 15, 17, 21, 22, 24, 0x10000):
            self.assertEqual(contract.stored_state(state), 0)
            self.assertEqual(contract.state_animation(state), [])

    def test_charge_overlay_once(self):
        self.assertEqual(len(contract.state_animation(12, first_charge=True)), 2)
        self.assertEqual(len(contract.state_animation(12, first_charge=False)), 1)

    def test_health_band_changes_locomotion(self):
        self.assertEqual(contract.state_animation(3, health_band=1)[0][1], 19)
        self.assertEqual(contract.state_animation(3, health_band=0)[0][1], 16)
        self.assertEqual(contract.state_animation(3, health_band=2)[0][1], 16)

    def test_back_attack_not_unused_180_clip(self):
        self.assertEqual(contract.ATTACK_CLIPS[11], 3)
        self.assertNotIn(2, contract.ATTACK_CLIPS.values())

    def test_death_uses_own_draw_low_bit(self):
        self.assertEqual(contract.state_animation(20, draw=0)[0][1], 10)
        self.assertEqual(contract.state_animation(20, draw=3)[0][1], 11)


if __name__ == '__main__':
    unittest.main()
