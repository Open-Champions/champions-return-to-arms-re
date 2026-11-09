"""Vectors for tools/ref_player_anim_states.py that need no game executable.

Every value here is also an input/output pair the difftest
tools/difftest_player_anim_states.py compared with the original code on seed 20973
(docs/player-anim-states.md), except the combo-step table, which is Observed only."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                      # noqa: E402
import ref_player_anim_states as M        # noqa: E402


class Timing(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')

    def test_melee_frames(self):
        speed, haste = M.swing_speed()
        self.assertEqual(M.hit_frame(speed), 16)
        self.assertEqual(M.hit_frame(speed, network=True), 1)
        self.assertEqual(M.first_combo_frame(0, haste, speed), 23)
        self.assertEqual(M.first_combo_frame(7, haste, speed), 18)
        self.assertEqual(M.swing_end_frame(), 96)
        self.assertEqual(M.stick_end_frame(), 40)
        self.assertEqual([M.move_mode(e) for e in (25, 26)], [4, 3])
        speed, haste = M.swing_speed(status2=True)
        self.assertEqual(M.hit_frame(speed), 12)
        self.assertEqual(M.first_combo_frame(0, haste, speed), 12)
        self.assertEqual(M.first_combo_frame(7, haste, speed), 9)

    def test_knockdown_names(self):
        cases = {-0x8000: 'a', -0x6000: 'a', -0x5FFF: 'c', -0x2000: 'c', -0x1FFF: 'b', 0: 'b',
                 0x2000: 'b', 0x2001: 'd', 0x5FFF: 'd', 0x6000: 'a', 0x7FFF: 'a'}
        for rel, suffix in cases.items():
            self.assertEqual(M.knockdown_name(0, rel), 'knockdown1_%s.anm' % suffix)
        self.assertTrue(M.knockdown_name(2, 0).startswith('knockdown2_'))
        self.assertTrue(M.knockdown_name(3, 0).startswith('knockdown2_'))
        self.assertTrue(M.knockdown_name(7, 0).startswith('knockdown1_'))

    def test_death_clip(self):
        self.assertEqual([M.death_offset(m, 2) for m in range(12)],
                         [0x14, 0x14, 0xC, 0xC, 0x14, 0x14, 0xC, 0xC, 0x14, 0x14, 0x14, 0x14])
        self.assertEqual({M.death_offset(m, c) for m in range(12) for c in (0, 1, 3, 4, 5, 6, 7)}, {0xC})

    def test_locomotion(self):
        self.assertEqual(M.playback_rate(C.ZERO), C.ZERO)
        self.assertEqual(M.playback_rate(0x3F333333), 0x3FACCCCC)
        first = M.locomotion_step(C.ZERO, C.ZERO, 0x3F400000, 4)
        self.assertEqual((first['blend'], first['previous'], first['event']),
                         (0x3DCCCCCC, 0x3D4CCCCC, 4))
        rest = M.locomotion_step(0x3D4CCCCC, C.ZERO, C.ZERO, 5)
        self.assertEqual((rest['rate'], rest['blend'], rest['event']), (C.ONE, C.ZERO, 0))
        # First moving tick (blend 0.1, held speed 0.05), reached by the difftest's stick
        # script: truncation gives ...8e / ...13, IEEE rounding would give ...8f / ...14.
        self.assertEqual((first['run1'], first['run2']), (0xBDF5C28E, 0xBE47AE13))
        self.assertEqual(M.run_weight(0x3DCCCCCC, 0x3D4CCCCC, M.D_045_BITS), 0xBDF5C28E)
        self.assertEqual(M.run_weight(0x3DCCCCCC, 0x3D4CCCCC, M.D_07_BITS), 0xBE47AE13)

    def test_combo_steps(self):
        self.assertEqual([M.COMBO_STEPS[c] for c in range(8)], [7, 7, 4, 9, 7, 2, 7, 7])


if __name__ == '__main__':
    unittest.main()
