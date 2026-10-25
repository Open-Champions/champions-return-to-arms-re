#!/usr/bin/env python3
"""Unit tests for tools/ref_music_volume.py that need no game file (they run in CI).

They pin the model's own logic with values worked out by hand from the patterns and the
R5900 rules of tools/ref_core.py.  Whether the model agrees with the game is the business
of tools/difftest_music_volume.py.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_core as R                    # noqa: E402
import ref_music_volume as M            # noqa: E402


class GateTest(unittest.TestCase):
    def setUp(self):
        R.set_fpu('ps2')

    def test_equal_pattern_passes(self):
        self.assertTrue(M.music_gate_passes(M.MUSIC_GATE))
        self.assertTrue(M.music_gate_passes(M.MUSIC_GATE + 1))
        self.assertFalse(M.music_gate_passes(M.MUSIC_GATE - 1))

    def test_zero_and_negative_fail(self):
        for pattern in (0, 0x80000000, 0xBF800000, 0xBD4CCCCC):
            self.assertFalse(M.music_gate_passes(pattern))

    def test_defaults_pass(self):
        self.assertTrue(M.music_gate_passes(M.DEFAULT_MUSIC))
        self.assertTrue(M.music_gate_passes(M.STATIC_MUSIC))

    def test_play_level_calls(self):
        self.assertEqual(M.music_play_level(0, R.ONE, 0x1000, 0x102), [])
        calls = M.music_play_level(M.DEFAULT_MUSIC, R.ONE, 0x1000, 0x102)
        self.assertEqual(calls[0], (M.AUDIO_SET_CHANNEL_VOLUME, 2, 0x3EC80000))  # 0.5 * 0.78125
        self.assertEqual(calls[1], (M.STREAM_QUEUE, 2, (0x1000, 0x122)))


class ApplyTest(unittest.TestCase):
    def setUp(self):
        R.set_fpu('ps2')

    def test_status_bit(self):
        self.assertEqual(M.music_apply_volume(R.ONE, R.ONE, 0),
                         [(M.AUDIO_STREAM_STATUS, 2, None)])
        self.assertEqual(M.music_apply_volume(R.ONE, R.ONE, 0x1F),
                         [(M.AUDIO_STREAM_STATUS, 2, None)])
        calls = M.music_apply_volume(R.ONE, R.ONE, 0x20)
        self.assertEqual(calls[1], (M.AUDIO_SET_CHANNEL_VOLUME, 2, M.CHANNEL_SCALE))

    def test_channel_volume_product(self):
        # 0.5 * 0.5 = 0.25, * 0.78125 = 0.1953125 = 0x3e480000 exactly
        self.assertEqual(M.channel_volume(M.DEFAULT_MUSIC, M.DEFAULT_MUSIC), 0x3E480000)
        self.assertEqual(M.channel_volume(0, R.ONE), 0)


class DefaultsTest(unittest.TestCase):
    def test_all(self):
        writes, calls = M.config_set_defaults(-1, 1, R.ONE, 0x20)
        self.assertEqual(writes[M.G_MUSIC_VOLUME], 0x3F000000)
        self.assertEqual(writes[M.G_SAVED_CONFIG + 8], 0x3F000000)
        self.assertEqual(writes[M.G_SAVED_CONFIG], 0)
        self.assertEqual(writes[M.G_SAVED_CONFIG + 0x34], 0x40)
        self.assertEqual(writes[M.G_SAVED_CONFIG + 0x34 + 3 * 0x24 + 0x20], 4)
        self.assertEqual(len(writes), 2 * 17 + 1 + 4 * 9)
        self.assertEqual(calls[1][2], R.mul(M.DEFAULT_MUSIC, M.CHANNEL_SCALE))

    def test_one_row_leaves_music(self):
        writes, calls = M.config_set_defaults(2, 0)
        self.assertNotIn(M.G_MUSIC_VOLUME, writes)
        self.assertEqual(calls, [])
        self.assertEqual(sorted(writes), [M.G_SAVED_CONFIG + 0x34 + 2 * 0x24 + 4 * k for k in range(9)])
        self.assertEqual(writes[M.G_SAVED_CONFIG + 0x34 + 2 * 0x24], 0x20)

    def test_other_scheme_and_slot(self):
        self.assertEqual(M.config_set_defaults(1, 2)[0], {})
        self.assertEqual(M.config_set_defaults(4, 1)[0], {})
        writes, _ = M.config_set_defaults(-1, 2)
        self.assertEqual(len(writes), 2 * 17 + 1)


class CopyTest(unittest.TestCase):
    def test_core_tasks_copies_verbatim(self):
        for pattern in (0, 0x3FC00000, 0xBF800000, 0x7FFFFFFF):
            writes, _ = M.game_add_core_tasks({0x08: pattern}, R.ONE, 0)
            self.assertEqual(writes[M.G_MUSIC_VOLUME], pattern)
        writes, _ = M.game_add_core_tasks({0x34 + 0x24 + 7 * 4: 0x1234}, R.ONE, 0)
        self.assertEqual(writes[0x41B9E0 + 4], 0x1234)

    def test_options_screen_states(self):
        buffer = {0x08: 0x3E800000, 0x0C: 0x3F400000}
        writes, calls = M.options_screen(2, buffer, 0, 0, R.ONE, 0)
        self.assertEqual(writes[M.G_MUSIC_VOLUME], 0x3E800000)
        self.assertEqual(writes[M.G_SAVED_CONFIG + 8], 0x3E800000)
        self.assertEqual(writes[M.G_OPTIONS_STATE], 3)
        self.assertNotIn(M.G_SAVED_CONFIG + 0x34, writes)
        self.assertEqual(calls[-1], (M.MEMCARD_SET_STATE, (-1, 0)))
        self.assertEqual(M.options_screen(0, {}, 2, 0, 0, 0)[0], {M.G_OPTIONS_STATE: 1})
        self.assertEqual(M.options_screen(0, {}, 1, 0, 0, 0)[1][-1], (M.MEMCARD_SET_STATE, (-1, 0)))
        self.assertEqual(M.options_screen(1, {}, 0, 1, 0, 0)[0], {M.G_OPTIONS_STATE: 2})
        self.assertEqual(M.options_screen(1, {}, 0, 2, 0, 0)[0], {})
        self.assertEqual(M.options_screen(-1, {}, 0, 0, 0, 0), ({}, []))
        self.assertEqual(M.options_screen(4, {}, 0, 0, 0, 0), ({}, []))

    def test_browser_copy(self):
        image, buffer = bytes(M.CONFIG_SIZE), bytes([0x11]) * M.CONFIG_SIZE
        self.assertEqual(M.browser_config_copy(0, image, buffer, -1), image)
        self.assertEqual(M.browser_config_copy(1, image, buffer, -1), buffer)
        out = M.browser_config_copy(0, image, buffer, 0x10)
        self.assertEqual(out[:4], bytes([0x14, 0, 0, 0]))


class SliderTest(unittest.TestCase):
    def setUp(self):
        R.set_fpu('ps2')

    def test_clamps(self):
        self.assertEqual(M.slider_step(0, 0x400000), 0)
        self.assertEqual(M.slider_step(R.ONE, 0x800000), R.ONE)
        self.assertEqual(M.slider_step(M.DEFAULT_MUSIC, 0), M.DEFAULT_MUSIC)
        self.assertEqual(M.slider_step(M.DEFAULT_MUSIC, M.LEFT_MASK | M.RIGHT_MASK),
                         R.add(R.sub(M.DEFAULT_MUSIC, M.SLIDER_STEP), M.SLIDER_STEP))

    def test_out_of_range_file_value_is_pulled_in_by_one_press(self):
        self.assertEqual(M.slider_step(0x3FC00000, 0x2000), R.ONE)          # 1.5 + step
        self.assertEqual(M.slider_step(0xBE800000, 0x8000), 0)              # -0.25 - step

    def test_timer(self):
        value, timer, active = M.menu_slider_call(M.DEFAULT_MUSIC, 0x400000, 0)
        self.assertFalse(active)
        self.assertEqual((value, timer), (M.DEFAULT_MUSIC, M.TIMER_STEP))
        calls, timer = 0, 0
        while True:
            calls += 1
            _v, timer, active = M.menu_slider_call(M.DEFAULT_MUSIC, 0x400000, timer)
            if active:
                break
        self.assertEqual(calls, 5)
        self.assertEqual(timer, R.ONE)

    def test_walk_from_default(self):
        down = M.slider_walk(M.DEFAULT_MUSIC, 0x400000)
        self.assertEqual(down[-1], 0)
        self.assertEqual(len(down) - 1, 60)
        first_below = next(i + 1 for i, v in enumerate(down) if not M.music_gate_passes(v))
        self.assertEqual(first_below, 54)
        self.assertEqual(down[53], 0x3D4CCC08)
        up = M.slider_walk(M.DEFAULT_MUSIC, 0x800000)
        self.assertEqual(up[-1], R.ONE)
        self.assertEqual(len(up) - 1, 61)


class CommitTest(unittest.TestCase):
    def test_commit(self):
        self.assertEqual(M.config_commit_music(0x3F000000, 0x3F000000, 0, 0), (0, 0x3F000000, False))
        self.assertEqual(M.config_commit_music(0x3E800000, 0x3F000000, 1, 0), (1, 0x3F000000, False))
        self.assertEqual(M.config_commit_music(0x3E800000, 0x3F000000, 0, 0), (1, 0x3E800000, True))
        self.assertEqual(M.config_commit_music(0x3E800000, 0x3F000000, 0, 1), (1, 0x3E800000, False))
        self.assertEqual(M.config_commit_music(0x3F000000, 0x3F000000, 0, 0, force=1),
                         (0, 0x3F000000, True))


class BootTest(unittest.TestCase):
    def setUp(self):
        R.set_fpu('ps2')

    def test_no_file(self):
        steps = M.boot_music_volume(None)
        self.assertEqual(steps[0][1], 0x3F800000)
        self.assertEqual(steps[-1][1], 0x3F000000)
        self.assertIn('passes', steps[-1][0])

    def test_file_values(self):
        self.assertEqual(M.boot_music_volume(0x3E800000)[-1][1], 0x3E800000)
        self.assertEqual(M.boot_music_volume(0x3FC00000)[-1][1], 0x3FC00000)   # no clamp on load
        self.assertIn('fails', M.boot_music_volume(0)[-1][0])
        # the defaults are still what 0x4f8944 holds while the card is read
        self.assertEqual(M.boot_music_volume(0)[2][1], 0x3F000000)

    def test_front_end_slider(self):
        steps = M.boot_music_volume(None, slider_held=[0x400000] * 54)
        self.assertIn('fails', steps[-1][0])
        steps = M.boot_music_volume(None, slider_held=[0x400000] * 53)
        self.assertIn('passes', steps[-1][0])


if __name__ == '__main__':
    unittest.main()
