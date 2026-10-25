"""Synthetic playback decisions. No executable and no disc samples.

The patterns below are the ones tools/difftest_audio.py also compares with the
original functions. This file only checks that the model stays on those patterns.
"""

import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_audio_playback as P  # noqa: E402


class LoopRestart(unittest.TestCase):
    def test_span_drops_the_low_ten_bits(self):
        self.assertEqual(
            [P.loop_restart_bytes(v) for v in
             (0, 1, 0x3FF, 0x400, 0x401, 0x800, 0x123456, 0x7FFFFC00, 0x80000000, 0x40000000)],
            [0, 0, 0, 0x800, 0x800, 0x1000, 0x246800, 0xFFFFF800, 0, 0x80000000])

    def test_rewind_replaces_position_and_remaining(self):
        self.assertEqual(P.after_completed_read("t", 1, 0, 0, 0x2000, 0x9000, 0x400, 0),
                         (0x2800, 0x8800))
        self.assertEqual(P.after_completed_read("t", 1, 0, 0, 0x2000, 0x9000, 0, 0),
                         (0x2000, 0x9000))
        self.assertEqual(P.after_completed_read("t", 1, 0, 0, 0x2000, 0x9000, 0x123456, 0),
                         (0x248800, 0xFFDC2800))
        # The read itself has to exhaust the remaining count.
        self.assertEqual(P.after_completed_read("t", 1, 0x111, 0x20, 0x2000, 0x9000, 0x400, 0x20),
                         (0x2800, 0x8800))
        self.assertEqual(P.after_completed_read("t", 1, 0x111, 0x20, 0x2000, 0x9000, 0x400, 0),
                         (0x111, 0x20))
        self.assertEqual(P.after_completed_read("t", 0, 0x111, 0, 0x2000, 0x9000, 0x400, 0),
                         (0x111, 0))
        self.assertEqual(P.after_completed_read("", 1, 0x111, 0x10, 0x2000, 0x9000, 0x400, 0x10),
                         (0x121, 0))


class MusicAndBoss(unittest.TestCase):
    def test_gate_is_closed_only_below_the_constant(self):
        self.assertFalse(P.music_gate_open(P.MUSIC_VOLUME_GATE - 1))
        self.assertTrue(P.music_gate_open(P.MUSIC_VOLUME_GATE))
        self.assertTrue(P.music_gate_open(0x3F800000))
        self.assertFalse(P.music_gate_open(0))

    def test_music_or_and_queue_words(self):
        self.assertEqual(P.music_flags(0x41), 0x63)
        self.assertEqual(P.music_flags(P.GLOBAL_BOSS_FLAGS), 0x123)
        self.assertEqual(P.music_flags(P.LEVEL_POLL_FLAGS), 0x122)
        words = P.queued_music(0x103, 0x333000, 0x222000, 0x2222, 0, 0x800)
        self.assertEqual(words[0x2C], 0x123)
        self.assertEqual((words[0x10], words[0x14], words[0x28]), (0x333000, 0x222000, 0x800))
        self.assertIsNone(P.queued_music(0x103, 0x1000, 0, 24000, 1, 0))

    def test_second_boss_replaces_and_a_closed_gate_silences(self):
        self.assertEqual(P.boss_action(False, 0x3F800000, 0x1000), "noop")
        self.assertEqual(P.boss_action(True, 0x3F800000, 0x1000), "replace")
        self.assertEqual(P.boss_action(True, P.MUSIC_VOLUME_GATE - 1, 0x1000), "silence")
        self.assertEqual(P.boss_action(True, 0x3F800000, 0), "silence")


class Flags(unittest.TestCase):
    def test_status_surfaces_caller_bits_and_hides_a_held_queue_entry(self):
        self.assertEqual(P.stream_status_bits(1, 2, 0, 0x140, 0, 0), 0x141)
        self.assertEqual(P.stream_status_bits(0, 0, 1, 0x40, 0, 0), 0x41)
        self.assertEqual(P.stream_status_bits(0, 0, 0, 0, 1, 0x100), 0x101)
        self.assertEqual(P.stream_status_bits(0, 0, 0, 0, 1, 0x108), 0)
        self.assertEqual(P.stream_status_bits(0, 0, 0, 0x40, 0, 0), 0)
        self.assertEqual(P.stream_status_bits(0, 0, 0x80000000, 0x40, 1, 0x100), 0x101)

    def test_recall_and_cutscene_policies(self):
        self.assertTrue(P.recall_stops_music(0x41))
        self.assertFalse(P.recall_stops_music(0x21))
        self.assertIsNone(P.cut_run_stream2(0, 0x80))
        self.assertEqual(P.cut_run_stream2(1, 0x80), "stop")
        self.assertIsNone(P.cut_run_stream2(1, 0x180))
        self.assertIsNone(P.cut_run_stream2(1, 0x20))
        self.assertIsNone(P.cut_end_stream2(0, 0x80))
        self.assertIsNone(P.cut_end_stream2(1, 0x180))
        self.assertEqual(P.cut_end_stream2(1, 0x80), "stop")
        self.assertEqual(P.cut_end_stream2(1, 0x20), "clear")
        self.assertEqual(P.cut_end_stream2(1, 0), "clear")


class Ducking(unittest.TestCase):
    def test_voice_target_is_the_constant_plus_one_creep(self):
        current, target = P.duck_update(0x3F800000, 0, 0x21, "", 0)
        self.assertEqual((current, target), (0x3F7D70A3, 0x3E5DDDE1))
        self.assertEqual(P.ducked_volume(current, 0x3F800000), 0x3F45FFFF)
        self.assertTrue(P.duck_sends_volume(0x3F800000, current, 0x21))
        self.assertFalse(P.duck_sends_volume(0x3F800000, current, 0))
        self.assertFalse(P.duck_sends_volume(current, current, 0x21))

    def test_without_voice_the_target_keeps_creeping(self):
        current, target = P.duck_update(0x3F800000, 0, 0, "", 0)
        self.assertEqual(target, P.DUCK_CREEP)
        self.assertEqual(current, 0x3F7D70A3)

    def test_actintro_in_another_language_zeros_the_scalar(self):
        current, target = P.duck_update(0x3F800000, 0, 0x21, "actintro", 1)
        self.assertEqual(current, 0)
        self.assertEqual(target, 0x3E5DDDE1)
        current, _target = P.duck_update(0x3F800000, 0, 0x21, "actintro", 0)
        self.assertNotEqual(current, 0)

    def test_set_duck_is_one_minus_the_argument(self):
        self.assertEqual(P.set_duck_target(0), 0x3F800000)
        self.assertEqual(P.set_duck_target(0x3F800000), 0)
        self.assertEqual(P.set_duck_target(0x3E4CCCCD), 0x3F4CCCCC)


class Cadence(unittest.TestCase):
    def test_sound_frame_phases_and_image_values(self):
        self.assertEqual(P.SOUND_FRAME_IMAGE, 0)
        self.assertEqual(P.DRAW_FRAME_IMAGE, 0x400)
        self.assertEqual(P.sound_cadence(0),
                         {"queues": True, "end_flags": True, "send_volumes": False, "next": 1})
        self.assertEqual(P.sound_cadence(4)["queues"], True)
        self.assertEqual(P.sound_cadence(4)["end_flags"], False)
        self.assertEqual(P.sound_cadence(8)["end_flags"], True)
        self.assertTrue(P.sound_cadence(0xF)["send_volumes"])
        self.assertFalse(P.sound_cadence(0x10)["send_volumes"])
        self.assertTrue(P.draw_cadence(0x400))
        self.assertFalse(P.draw_cadence(0x401))
        self.assertTrue(P.draw_cadence(0))
        self.assertFalse(P.draw_cadence(15))
        self.assertTrue(P.draw_cadence(16))


class Movie(unittest.TestCase):
    def test_gate_off_always_advances_and_ignores_position(self):
        self.assertEqual(P.movie_sync(0, 10, 0x400, 0), (False, 11, 0))

    def test_hold_only_when_the_picture_is_ahead_of_stream_2(self):
        self.assertEqual(P.movie_sync(1, 10, 0x400, 0), (True, 10, 0x400))
        self.assertEqual(P.movie_sync(1, 100, 0x10000, 0), (True, 100, 0x10000))
        self.assertEqual(P.movie_sync(1, 10, 0x8000, 0), (False, 11, 0x8000))
        self.assertEqual(P.movie_sync(1, 10, 0x800, 0x800), (False, 11, 0x800))
        self.assertEqual(P.movie_sync(1, 0, 0, 1), (False, 1, 0))


if __name__ == "__main__":
    unittest.main()
