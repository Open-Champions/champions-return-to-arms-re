"""Synthetic tests for tools/ref_wading.py (authored fixtures; no game data).

The format strings and lump name the original reads from its image are replaced here by
authored placeholders written into the synthetic memory.
"""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as R                        # noqa: E402
import ref_combat_move as MV                    # noqa: E402
import ref_water_services as W                  # noqa: E402
import ref_wading as WD                         # noqa: E402

WORLD, TREE, CHUNKS, PAYLOAD, GRID = 0x10000, 0x10100, 0x10200, 0x10400, 0x11000
P = 0x20000
F = C.f32


def world(mem, surface, x0=-192.0, width=384.0, flags=0x80, grid=GRID):
    mem.poke(MV.G_WORLD, 4, WORLD)
    mem.poke(WORLD + 4, 4, TREE)
    mem.poke(WORLD + 0x24, 4, CHUNKS)
    mem.poke(TREE, 2, 1)
    mem.poke(TREE + 2, 2, 0)
    mem.poke(CHUNKS, 4, PAYLOAD)
    mem.poke(CHUNKS + 0x24, 4, flags)
    for k, v in enumerate((x0, -192.0, surface)):
        mem.poke(CHUNKS + 8 + 4 * k, 4, F(v))
    for k, v in enumerate((x0 + width, 192.0, surface)):
        mem.poke(CHUNKS + 0x14 + 4 * k, 4, F(v))
    mem.poke(CHUNKS + 0x28, 4, 0)
    mem.poke(CHUNKS + 0x2C, 4, 0)
    mem.poke(PAYLOAD + 8, 4, grid)


def cell(mem, x, y):
    return R.s16(mem.load(GRID + 0xA90 + 2 * (32 * x + y), 2))


class Recorder(dict):
    def __init__(self):
        dict.__init__(self)
        self.log = []
        for name in ('res_find', 'sound_playOnObject', 'fx_burst_1fbdf0', 'damage_apply', 'sound_playAtPos'):
            self[name] = (lambda n: lambda *a: self.log.append((n, a)) or 0x777)(name)


def player(mem, z=0.0, wet=False, frame=0, airborne=0):
    for k, v in enumerate((0.0, 0.0, z)):
        mem.poke(P + 0x10 + 4 * k, 4, F(v))
    mem.poke(P + 0xA8, 8, WD.WATER_BIT if wet else 0)
    mem.poke(P + 0x47C, 1, airborne)
    mem.poke(MV.G_SIM_FRAME, 4, frame)
    mem.poke(MV.S_SPLASH_FMT, 6, int.from_bytes(b'sp%d\0\0', 'little'))


class Boxes(unittest.TestCase):
    def test_entry_box_pads_xy_by_one_and_spans_z_minus1_to_plus60(self):
        lo, hi = WD.entry_box((0, 0, 0))
        self.assertEqual(lo, (F(-13), F(-13), F(-1)))
        self.assertEqual(hi, (F(13), F(13), F(60)))

    def test_wade_box_is_twelve_lower_and_unpadded(self):
        lo, hi = WD.wade_box((0, 0, F(100)))
        self.assertEqual(lo, (F(-12), F(-12), F(87)))
        self.assertEqual(hi, (F(12), F(12), F(148)))

    def test_wade_box_with_negative_zero_x(self):
        lo, hi = WD.wade_box((0x80000000, 0, 0))
        self.assertEqual(lo[0], F(-12))
        self.assertEqual(hi[0], F(12))


class Band(unittest.TestCase):
    def setUp(self):
        self.mem = R.Memory()
        self.model = WD.WadeModel(self.mem, Recorder())

    def hit_test(self, surface):
        world(self.mem, surface)
        return self.model.wade_water_test(WORLD, (0, 0, 0), 1, 0x41400000)

    def test_entry_hits_from_one_below_to_sixty_above(self):
        for dz, want in ((-1.25, 0), (-1.0, 1), (0.0, 1), (60.0, 1), (60.25, 0)):
            self.assertEqual(self.hit_test(dz)[0], want, dz)

    def test_entry_returns_the_chunk_minimum_z(self):
        self.assertEqual(self.hit_test(7.5), (1, F(7.5)))

    def test_wading_disturb_hits_from_thirteen_below_to_forty_eight_above(self):
        for dz, want in ((-13.25, 0), (-13.0, 1), (48.0, 1), (48.25, 0)):
            world(self.mem, dz)
            point = (0, 0, F(-12.0))
            self.assertEqual(self.model.wade_water_disturb(WORLD, point, F(300), F(12)), want, dz)

    def test_cut_skip_stops_the_ripple(self):
        world(self.mem, 0.0)
        self.mem.poke(W.G_CUT_SKIP, 1, 1)
        self.assertEqual(self.model.wade_water_disturb(WORLD, (0, 0, F(-12)), F(300), F(12)), 0)
        self.assertEqual(cell(self.mem, 16, 16), 0)


class PlayerWater(unittest.TestCase):
    def setUp(self):
        self.mem = R.Memory()
        self.cb = Recorder()
        self.model = WD.WadeModel(self.mem, self.cb)

    def test_entry_on_foot_sets_bit_draws_once_and_writes_1000_at_the_centre(self):
        world(self.mem, 10.0)
        player(self.mem, frame=8)
        self.model._player_water(P, F(0.5))
        self.assertTrue(self.mem.load(P + 0xA8, 8) & WD.WATER_BIT)
        self.assertEqual(self.model.draws, 1)
        self.assertEqual([n for n, _a in self.cb.log], ['res_find', 'sound_playOnObject'])
        self.assertEqual(self.cb.log[1][1][2], 0x3ECCCCCC)
        self.assertEqual(cell(self.mem, 16, 16), 1000)

    def test_airborne_entry_is_3000_louder_and_bursts_at_the_surface(self):
        world(self.mem, 10.0)
        player(self.mem, frame=4, airborne=1)
        self.model._player_water(P, F(0.5))
        self.assertEqual(cell(self.mem, 16, 16), 3000)
        self.assertEqual(self.cb.log[1][1][2], WD.ONE)
        self.assertEqual(self.cb.log[2], ('fx_burst_1fbdf0', ((0, 0, F(10.0)), WD.ONE)))

    def test_no_test_on_frames_not_multiple_of_four(self):
        world(self.mem, 10.0)
        player(self.mem, frame=5)
        self.model._player_water(P, F(0.5))
        self.assertFalse(self.mem.load(P + 0xA8, 8) & WD.WATER_BIT)
        self.assertEqual(self.model.draws, 0)

    def test_deep_water_entry_ripple_writes_nothing(self):
        world(self.mem, 55.0)
        player(self.mem, frame=0)
        self.model._player_water(P, F(0.5))
        self.assertTrue(self.mem.load(P + 0xA8, 8) & WD.WATER_BIT)
        self.assertEqual(cell(self.mem, 16, 16), 0)

    def test_wading_ripple_300_every_frame_when_moving(self):
        world(self.mem, 10.0)
        player(self.mem, wet=True, frame=5)
        self.model._player_water(P, F(0.5))
        self.assertEqual(cell(self.mem, 16, 16), 300)
        self.assertEqual(self.model.draws, 0)

    def test_still_wader_ripples_only_on_sixteenth_frames(self):
        world(self.mem, 10.0)
        player(self.mem, wet=True, frame=5)
        self.model._player_water(P, 0)
        self.assertEqual(cell(self.mem, 16, 16), 0)
        player(self.mem, wet=True, frame=32)
        self.model._player_water(P, 0)
        self.assertEqual(cell(self.mem, 16, 16), 300)

    def test_wader_leaves_when_the_ripple_finds_no_water(self):
        world(self.mem, 50.0)
        player(self.mem, wet=True, frame=5)
        self.model._player_water(P, F(0.5))
        self.assertFalse(self.mem.load(P + 0xA8, 8) & WD.WATER_BIT)

    def test_hurting_level_damages_on_sixteenth_frames(self):
        world(self.mem, 10.0)
        player(self.mem, wet=True, frame=16)
        self.mem.poke(MV.G_LEVEL_FLAGS, 4, 0x1000)
        self.model._player_water(P, F(0.5))
        self.assertEqual(self.cb.log[0][0], 'damage_apply')


class Footstep(unittest.TestCase):
    def setUp(self):
        self.mem = R.Memory()
        self.cb = Recorder()
        self.model = WD.WadeModel(self.mem, self.cb)
        for addr, text in ((WD.S_FOLEY_WATER, b'w%d'), (WD.S_FOLEY_PLAIN, b'p%d'),
                           (WD.S_FOLEY_BY_FLAG[0][1], b'a%d'), (WD.S_FOLEY_BY_FLAG[1][1], b'b%d'),
                           (WD.S_FOLEY_BY_FLAG[2][1], b'c%d'), (WD.S_FOLEY_LUMP, b'L')):
            for i, b in enumerate(text + b'\0'):
                self.mem.poke(addr + i, 1, b)
        self.mem.poke(P + 0x3C8, 4, 1)
        self.rec = WD.G_PLAYERS + WD.REC_SIZE

    def step(self, flags=None, wet=False, seed=0x12345678):
        if flags is not None:
            self.mem.poke(self.rec + WD.REC_BOOTS_A, 4, 0x30000)
            self.mem.poke(0x30008, 4, flags)
        self.mem.poke(P + 0xA8, 8, WD.WATER_BIT if wet else 0)
        self.mem.poke(WD.G_COSMETIC_SEED, 4, seed)
        return self.model.player_footstep(P)

    def test_in_water_picks_the_water_variant_from_the_cosmetic_seed(self):
        self.step(0x400000, wet=True, seed=0)
        seed = 0x3C6EF35F
        self.assertEqual(self.mem.load(WD.G_COSMETIC_SEED, 4), seed)
        self.assertEqual(self.cb.log[0][1][1], b'w%d' % ((seed >> 16 & 1) + 1))
        self.assertEqual(self.model.draws, 0)

    def test_dry_without_foley_bits_is_silent_and_returns_the_delay_slot_value(self):
        self.assertEqual(self.step(0x40000), WD.FOLEY_SILENT)
        self.assertEqual(self.cb.log, [])
        self.assertEqual(self.mem.load(WD.G_COSMETIC_SEED, 4), 0x12345678)

    def test_flag_precedence_and_variant_counts(self):
        self.step(0x600000, seed=0)
        self.assertEqual(self.cb.log[0][1][1], b'a%d' % ((0x3C6EF35F >> 16) % 5 + 1))
        self.step(None, seed=0)
        self.mem.poke(0x30008, 4, 0x80000)
        self.cb.log[:] = []
        self.step(None, seed=0)
        self.assertEqual(self.cb.log[0][1][1], b'p%d' % (((0x3C6EF35F >> 16) & 3) + 1))

    def test_no_boot_item_uses_0x80000(self):
        self.step(None, seed=0)
        self.assertEqual(self.cb.log[0][1][1][:1], b'p')
        self.assertEqual(self.cb.log[1][1][2], WD.ONE)


class Constants(unittest.TestCase):
    def test_addresses_are_inside_player_move_or_player_run(self):
        for value, addr, _what in WD.player_wade_constants:
            self.assertTrue(0x1B4020 <= addr < 0x1B5330 or 0x1A5030 <= addr < 0x1AC7A4, hex(addr))

    def test_strengths_and_radii(self):
        values = {v for v, _a, _w in WD.player_wade_constants}
        for v in (0x447A0000, 0x453B8000, 0x43960000, 0x41C00000, 0x41400000):
            self.assertIn(v, values)
        self.assertEqual(C.to_float(0x43960000), 300.0)
        self.assertEqual(C.to_float(0x453B8000), 3000.0)


if __name__ == '__main__':
    unittest.main()
