#!/usr/bin/env python3
"""The script-effect contract stays aligned with the published call counts."""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                         # noqa: E402
import ref_creature                         # noqa: E402
import ref_natives as N                      # noqa: E402
import ref_script_compose as compose        # noqa: E402
import ref_script_effects as E               # noqa: E402


def f32(value):
    return struct.unpack('<I', struct.pack('<f', float(value)))[0]


class EffectContract(unittest.TestCase):
    def test_counts_match_the_published_census(self):
        counts = compose.published_counts()
        for name, calls, status, _native, _note in E.COMMANDS:
            self.assertIn(name, N.NATIVE_NAMES)
            self.assertEqual(counts[name][0], calls)
            self.assertIn(status, ('executed', 'partial'))

    def test_rank_is_disc_order(self):
        order = E.ranked()
        calls = [row[1] for row in order]
        self.assertEqual(calls, sorted(calls, reverse=True))
        self.assertEqual(order[0][0], 'generateMonster')
        self.assertGreater(order[0][1], 0)

    def test_scale_matches_the_executed_patterns(self):
        mem = N.Mem()
        creature = 0x1000
        mem.w32(creature + 0x228, f32(100))
        mem.w32(creature + 0x22C, f32(200))
        mem.w16(creature + 0xE4, 10)
        mem.w16(creature + 0xD0, 4)
        mem.w16(creature + 0xD2, 6)
        mem.w16(creature + 0xD4, 8)
        mem.w32(creature + 0xD8, f32(3.5))
        self.assertEqual(E.scale_stats(mem, creature, (f32(0.5), f32(2), f32(0.25), f32(1.5), f32(0))), 0)
        self.assertEqual(mem.u32(creature + 0x228), 0x42480000)
        self.assertEqual(mem.u32(creature + 0x22C), 0x42C80000)
        self.assertEqual(mem.u16(creature + 0xE4), 20)
        self.assertEqual(mem.u16(creature + 0xD0), 1)
        self.assertEqual(mem.u16(creature + 0xD2), 1)
        self.assertEqual(mem.u16(creature + 0xD4), 12)
        self.assertEqual(mem.u32(creature + 0xD8), 0)

        mem.w32(creature + 0x228, f32(100.5))
        mem.w32(creature + 0x22C, f32(1))
        mem.w16(creature + 0xE4, 1)
        mem.w16(creature + 0xD0, 1)
        mem.w16(creature + 0xD2, 3)
        mem.w16(creature + 0xD4, 1)
        mem.w32(creature + 0xD8, f32(2))
        E.scale_stats(mem, creature, (f32(0.5), f32(0.1), f32(0.1), f32(-1), f32(0.25)))
        self.assertEqual(mem.u32(creature + 0x228), 0x42480000)   # 50.25 truncated
        self.assertEqual(mem.u32(creature + 0x22C), 0)
        self.assertEqual(mem.u16(creature + 0xE4), 1)
        self.assertEqual(mem.s16(creature + 0xD4), -1)

    def test_home_range_and_state_stores(self):
        mem = N.Mem()
        E.slot34_set_home_range(mem, 0x2000, 0x1ABCD)
        self.assertEqual(mem.u32(0x2000 + 0x3C0), 0x472BCD00)
        E.slot27_set_state(mem, 0x2000, 0x12345)
        self.assertEqual(mem.u16(0x2000 + 0x232), 0x2345)

    def test_spawn_angle_and_failure_return(self):
        mem = N.Mem()
        gen = 0x3000
        mem.w32(gen + 0x10, 0x3FA00000)
        mem.w32(gen + 0x14, 0x40200000)
        mem.w32(gen + 0x18, 0x40700000)
        mem.w32(gen + 0x1C, 0x99)
        mem.w16(gen + 0x38, 0x100)
        mem.w32(gen + 0x2C, 0x11)
        fx = E.Trace({'world_createObject': 0})
        before = len(mem.writes)
        self.assertEqual(E.generator_spawn(mem, fx, gen, 0x3100), 0x01000000)
        _name, pos, angle, props = fx.calls[0][1]
        self.assertEqual(pos, (0x3FA00000, 0x40200000, 0x40700000, 0))
        self.assertEqual(angle, 0xFFFFC100)
        self.assertEqual(props, 0x11)
        self.assertEqual(mem.writes[before:], [])

    def test_queue_stop_and_frozen_flag(self):
        mem = N.Mem()
        self.assertEqual(E.queue_stop(mem, 2), 1)
        self.assertEqual(mem.u32(0x877158), 1)
        self.assertEqual(mem.u32(0x877004), 2)
        self.assertEqual(mem.u8(0x876FD8), 0)
        full = N.Mem()
        full.w32(E.stream_count_addr(2)[0], 8)
        before = len(full.writes)
        self.assertEqual(E.queue_stop(full, 2), 24)
        self.assertEqual(full.writes[before:], [])
        flagged = N.Mem()
        self.assertEqual(E.set_plays_while_frozen(flagged, 0x8003), 0xE4)
        self.assertEqual(flagged.u8(0x871B87), 1)
        self.assertEqual(E.set_plays_while_frozen(N.Mem(), -1), -1)

    def test_music_gate(self):
        shut = N.Mem()
        shut.w32(E.G_MUSIC_VOLUME, 0)
        shut.w32(E.G_MUSIC_SCALAR, f32(1))
        quiet = E.Trace()
        self.assertEqual(E.music_play_level(shut, quiet, 0x100, 3), 0x500000)
        self.assertEqual(quiet.calls, [])
        open_ = N.Mem()
        open_.w32(E.G_MUSIC_VOLUME, E.MUSIC_GATE)
        open_.w32(E.G_MUSIC_SCALAR, f32(1))
        fx = E.Trace()
        self.assertEqual(E.music_play_level(open_, fx, 0x100, 3), 0)
        self.assertEqual(fx.calls[0][0], 'audio_setChannelVolume')
        self.assertEqual(fx.calls[0][2][0], C.mul(C.mul(f32(1), E.MUSIC_GATE), E.MUSIC_SCALE))
        self.assertEqual(fx.calls[1][1], (2, 0x100, 0x23))

    def test_filter_keeps_a_root_and_clears_it_on_death(self):
        """rootMonster asks for state 0. killMonster asks for 0x14. The filter
        is what a derived set-state runs; the base slot 27 does not."""
        mem = ref_creature.Memory()
        model = ref_creature.Model(mem)
        creature = 0x4000
        mem.poke(creature + 0x314, 2, 0xFFFF)
        mem.poke(creature + 0x234, 4, 0x10)
        self.assertEqual(model.filter_state(creature, 0), (0, 0))
        self.assertEqual(mem.load(creature + 0x314, 2), 0xFFFF)
        self.assertEqual(mem.load(creature + 0x234, 4), 0)
        mem.poke(creature + 0x234, 4, 0x10)
        self.assertEqual(model.filter_state(creature, 4), (0, 5))
        mem.poke(creature + 0x234, 4, 0)
        self.assertEqual(model.filter_state(creature, 4), (0, 0))
        for off, value in ((0x314, 9), (0x318, 4), (0x31C, 6), (0x31A, 2)):
            mem.poke(creature + off, 2, value)
        self.assertEqual(model.filter_state(creature, 0x14), (0, 0x14))
        for off in (0x314, 0x318, 0x31C, 0x31A):
            self.assertEqual(mem.load(creature + off, 2), 0)

    def test_boss_table_has_the_eleven_rows(self):
        self.assertEqual(len(E.BOSS_ROWS), 11)
        self.assertEqual(len({row[2] for row in E.BOSS_ROWS}), 11)


if __name__ == '__main__':
    unittest.main()
