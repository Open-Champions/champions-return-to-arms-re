"""Synthetic checks of tools/ref_audio_session.py. No executable and no disc data.

tools/difftest_audio_session.py compares the same functions with the original code;
this file only keeps the model on the patterns that comparison established.
"""

import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_audio_session as S  # noqa: E402


class LevelEntry(unittest.TestCase):
    def test_recall_skips_everything_but_the_reseed(self):
        self.assertEqual(S.level_entry(1, 0, ["x_enttag"], 0x1234), ([], 0x1234))
        self.assertEqual(S.level_entry(0, 1, None, 0x99), ([], 0x99))

    def test_no_tag_queues_a_stop(self):
        self.assertEqual(S.level_entry(0, 0, ["mx_env_a_l.vag", "amb_b_l.vag"], 5),
                         ([("stream_queueStop", 2)], 5))
        self.assertEqual(S.level_entry(0, 0, None, 5), ([("stream_queueStop", 2)], 5))
        self.assertEqual(S.level_entry(0, 0, ["", "x_enttag"], 5), ([("stream_queueStop", 2)], 5))

    def test_tag_plays_and_sets_the_timer(self):
        calls, seed = S.level_entry(0, 0, ["a", "b_enttag_c"], 0)
        self.assertEqual(seed, S.lcg(0))
        self.assertEqual(calls[0], ("music_playLevel", 1, 2))
        self.assertEqual(calls[1], ("timer", (S.lcg(0) >> 16) % 1200 + 1800))

    def test_countdown(self):
        self.assertEqual(S.session_countdown(0, 0, 999), 60)
        self.assertEqual(S.session_countdown(1, 0, 999), 999)
        self.assertEqual(S.session_countdown(0, 0xFF, 7), 7)


class Music(unittest.TestCase):
    def test_pvp(self):
        self.assertEqual(S.pvp_music(0, 3), ([], 3))
        calls, seed = S.pvp_music(1, 3)
        self.assertEqual(calls, [("music_playGlobal", S.PVP_TRACKS[(S.lcg(3) >> 16) % 11], 1)])

    def test_pause_preview_and_fade(self):
        calls, timer = S.slider_preview("pause", 0, 0, 0x3F000000, 0x3F800000, 0, 77, 1)
        self.assertEqual(calls, [("status", 2), ("music_playGlobal", "mx_main_l.vag", 0x41)])
        self.assertEqual(timer, 1)
        calls, timer = S.slider_preview("pause", 0, 0, 0, 0, 0x41, 240, 1)
        self.assertEqual((calls, timer), ([("status", 2), ("stream_queueStop", 2)], 241))
        calls, timer = S.slider_preview("pause", 0, 0, 0, 0, 0x41, 239, 1)
        self.assertEqual((calls, timer), ([], 240))

    def test_front_preview(self):
        calls, timer = S.slider_preview("front", 0, 0x3F000000, 0, 0x80000000, 0x20, 120, 4)
        self.assertEqual(calls, [("lump_get",), ("sound_playOnObject", S.FLOAT_ONE, 0),
                                 ("music_applyVolume",), ("audio_sendVolumes",),
                                 ("status", 2)])
        self.assertEqual(timer, 121)


class Voice(unittest.TestCase):
    def test_got_item_line(self):
        calls, seed = S.player_voice(0, 9, 1, 0, 0, 0, 0, S.FLOAT_ONE, 0)
        n = 35 + (S.lcg(0) >> 16) % 2
        self.assertEqual(calls[-1], ("playGlobalRandom", 1, "bwm%03d" % n, 0x24))

    def test_gates(self):
        self.assertEqual(S.player_voice(0, 9, 0, 0, 0, 0, 0, S.FLOAT_ONE, 0)[0], [("isLocal",)])
        self.assertEqual(S.player_voice(0, 9, 1, 1, 0, 0, 0, S.FLOAT_ONE, 0)[0], [("isLocal",)])
        self.assertEqual(S.player_voice(0, 9, 1, 0, 0, 1, 0, S.FLOAT_ONE, 0)[0], [("isLocal",)])
        self.assertEqual(S.player_voice(0, 9, 1, 0, 0, 0, 0x20, S.FLOAT_ONE, 0)[0],
                         [("isLocal",), ("status", 1)])
        self.assertEqual(S.player_voice(0, 9, 1, 0, 0, 0, 0, 0x80000000, 0)[0],
                         [("isLocal",), ("status", 1)])

    def test_silent_kinds(self):
        for kind in (2, 6, 10, 17):
            self.assertEqual(len(S.player_voice(3, kind, 1, 0, 1, 0, 0, S.FLOAT_ONE, 0)[0]),
                             1 if kind >= 10 else 2)
        self.assertEqual(len(S.player_voice(10, 3, 1, 0, 1, 0, 0, S.FLOAT_ONE, 0)[0]), 2)


class FoleyAndHits(unittest.TestCase):
    def test_foley(self):
        self.assertEqual(S.foley(0, 0, 9), (None, 9))
        self.assertEqual(S.foley(0, 0x800000, 9), (None, 9))
        self.assertTrue(S.foley(1, 0, 9)[0].startswith("fs_water"))
        self.assertTrue(S.foley(0, 0x480000, 9)[0].startswith("foly_plate"))
        self.assertTrue(S.foley(0, 0x180000, 9)[0].startswith("foly_leather"))
        self.assertTrue(S.foley(0, 0x80000, 9)[0].startswith("foly_cloth"))

    def test_hit(self):
        one, hundred = 0x3F800000, 0x42C80000
        self.assertIsNone(S.hit_name(0, 0, None, 0x4000, 1, one, hundred))
        self.assertEqual(S.hit_name(0, 1 << 38, None, 8, 1, one, hundred), "hit_stone_slsh_lt.anm")
        self.assertEqual(S.hit_name(0, (1 << 38) | (1 << 35), None, 4, 0, one, hundred),
                         "hit_lthr_pierce_miss.anm")
        self.assertEqual(S.hit_name(1, 0, 0x480000, 0, 1, 0x41C80000, hundred),
                         "hit_cloth_bludg_med.anm")
        self.assertEqual(S.hit_name(1, 0, None, 0, 1, 0x42700000, hundred), "hit_flesh_bludg_hvy.anm")


class Volumes(unittest.TestCase):
    def test_order(self):
        self.assertEqual(S.update_order(0, False)[0], "music_updateDucking")
        self.assertIn("stream_serviceQueues", S.update_order(4, True))
        self.assertNotIn("audio_setChannelVolume", S.update_order(1, True))
        self.assertEqual(S.update_order(15, False)[-1], "audio_sendVolumes")

    def test_channels(self):
        self.assertEqual(S.channel0_volume(0x3F000000), 0x3F160000)
        self.assertEqual(S.channel0_volume(0), 0)
        self.assertEqual(S.set_channel_volume(0x3F800000, 0x3FC00000), (0x3F800000, False))
        self.assertEqual(S.set_channel_volume(0x3F800000, 0xBF800000), (0, True))
        self.assertEqual(S.send_volumes_payload(1, (0x3F800000, 0x3F000000, 0)), (1, 256, 128, 0))


if __name__ == "__main__":
    unittest.main()
