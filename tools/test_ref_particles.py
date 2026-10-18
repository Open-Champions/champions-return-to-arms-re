"""Tests for ref_particles.py on synthetic values only (no game file).

Run: python3 -m unittest discover -s tools -p test_ref_particles.py

The expected numbers follow from the rules in docs/effects.md; agreement with the original
machine code would need a difftest under tools/ee_emu.py, which does not exist yet.
"""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_particles as P                       # noqa: E402


def make(kind=P.KIND_ADD, life_class=1, tile=0x12, size=(1.0, 3.0), gravity=-2.56,
         start=(0x80, 0x40, 0x20, 0x80), end=(0, 0x40, 0xff, 0)):
    return P.ParticleDef.build(size[0], size[1], gravity, start, end, life_class, kind, tile)


class Definition(unittest.TestCase):
    def test_lifetimes_and_list_index(self):
        self.assertEqual(P.LIFE_TICKS, (11, 30, 60, 90))
        d = make(kind=P.KIND_BLEND, life_class=2)
        self.assertEqual((d.life, d.list_index), (60, 2))
        d = make(kind=P.KIND_LINE, life_class=3)
        self.assertEqual(d.list_index, 11)

    def test_clamps(self):
        d = make(kind=7, life_class=-4)
        self.assertEqual((d.kind, d.life_class, d.life), (3, 0, 11))

    def test_tile_coordinates(self):
        d = make(tile=0x12)                   # column 2, row 1
        self.assertEqual((d.u0, d.v0, d.u1, d.v1), (65 * 16, 33 * 16, 95 * 16, 63 * 16))

    def test_sizes_and_gravity(self):
        d = make(life_class=1, size=(1.0, 3.0), gravity=-2.56)
        self.assertAlmostEqual(d.size0, 100.0)
        self.assertAlmostEqual(d.size_rate, 200.0 / 30, places=4)
        self.assertAlmostEqual(d.gravity, -0.01, places=6)
        self.assertAlmostEqual(d.size_at(30), 300.0, places=3)

    def test_colour_clamp_and_bias(self):
        d = make(life_class=1, start=(0x80, 0x40, 0x20, 0x80), end=(0, 0x40, 0xff, 0))
        self.assertEqual(d.colour_at(0), (0x80, 0x40, 0x20, 0x80))
        # (0xff - 0x20) / 30 is inexact and cut toward zero: the blue ends one short
        self.assertEqual(d.colour_at(30), (0, 0x40, 0xfe, 0))
        self.assertEqual(d.colour_at(60), (0, 0x40, 255, 0))     # clamped, not wrapped
        self.assertEqual(d.c0[0], 0x80 + 2 ** 23)
        hidden = make(kind=P.KIND_HIDDEN)
        self.assertEqual(hidden.c0[0], 0x80)

    def test_callback_rejected(self):
        with self.assertRaises(ValueError):
            P.ParticleDef.build(1, 1, 0, (0,) * 4, (0,) * 4, callback=1)

    def test_line_kind_fields(self):
        d = make(kind=P.KIND_LINE, size=(4.0, 9.0), gravity=2.56)
        self.assertAlmostEqual(d.line_lag, 4.0, places=5)
        self.assertAlmostEqual(d.line_gravity, 0.01, places=6)
        self.assertEqual(len(d.record()), 0x40)

    def test_record_layout(self):
        d = make(tile=0x01)
        r = d.record()
        self.assertEqual(struct.unpack_from('<ii', r, 0), (33 * 16, 16))
        self.assertAlmostEqual(struct.unpack_from('<f', r, 0x1c)[0], 100.0)
        self.assertEqual(struct.unpack_from('<f', r, 0x20)[0], 0x80 + 2 ** 23)

    def test_default_reset(self):
        d = P.ParticleDef.reset_default()
        self.assertEqual((d.kind, d.life_class, d.tile, d.life), (1, 3, 1, 90))


class Spawn(unittest.TestCase):
    def test_plain_record(self):
        d = make()
        p = P.spawn_record(d, (10.7, -3.9, 5.0), (1.0, -0.5, 0.25), clock=100)
        self.assertEqual(p, P.Particle(10, -3, 5, 100, 256, -128, 64, 0))

    def test_backdate_keeps_position_and_velocity_now(self):
        d = make(gravity=-25.6)                # g = -0.1 per tick^2
        p = P.spawn_record(d, (100.0, 200.0, 300.0), (16.0, 0.0, 32.0), clock=50, backdate=0.25)
        self.assertEqual(p.birth, 50 - 15)
        x, y, z = P.position_at(p, d, 15)
        self.assertAlmostEqual(x, 100.0, delta=1.0)
        self.assertAlmostEqual(y, 200.0, delta=1.0)
        self.assertAlmostEqual(z, 300.0, delta=1.0)

    def test_motion(self):
        d = make(gravity=-25.6)
        p = P.spawn_record(d, (0.0, 0.0, 100.0), (16.0, 0.0, 0.0), clock=0)
        x, _, z = P.position_at(p, d, 10)
        self.assertAlmostEqual(x, 10.0)        # 16 units per 16 ticks
        self.assertAlmostEqual(z, 100.0 - 0.1 * 100, places=4)

    def test_line_endpoints(self):
        d = make(kind=P.KIND_LINE, size=(4.0, 4.0), gravity=0.0)
        p = P.spawn_record(d, (0.0, 0.0, 0.0), (16.0, 0.0, 0.0), clock=0)
        tail, head = P.line_endpoints(p, d, 10)
        self.assertAlmostEqual(head[0], 10.0)
        self.assertAlmostEqual(tail[0], 6.0, places=4)

    def test_screen_extent(self):
        self.assertEqual(P.screen_half_extent(100.0, 50.0), (4.0, 2.0))


class Pools(unittest.TestCase):
    def test_lifetime_inclusive(self):
        s = P.ParticleSystem()
        d = make(life_class=0)
        s.spawn(d, (0, 0, 0), (0, 0, 0))
        for _ in range(11):
            s.update()
        self.assertEqual(len(list(s.live())), 1)          # age 11 = life: still drawn
        s.update()
        self.assertEqual(len(list(s.live())), 0)
        self.assertEqual((d.live, d.slot), (0, -1))
        self.assertEqual(len(s.free_pages), P.PAGE_COUNT)

    def test_page_capacity(self):
        s = P.ParticleSystem()
        d = make(life_class=3)
        for _ in range(P.CELLS_PER_PAGE):
            s.spawn(d, (0, 0, 0), (0, 0, 0))
        self.assertEqual(len(s.free_pages), P.PAGE_COUNT - 1)
        s.spawn(d, (0, 0, 0), (0, 0, 0))
        self.assertEqual(len(s.free_pages), P.PAGE_COUNT - 2)

    def test_pool_exhaustion_drops(self):
        s = P.ParticleSystem()
        d = make(life_class=3)
        total = P.PAGE_COUNT * P.CELLS_PER_PAGE
        for _ in range(total + 5):
            s.spawn(d, (0, 0, 0), (0, 0, 0))
        self.assertEqual(d.live, total)
        self.assertEqual(s.dropped, 5)

    def test_slot_exhaustion(self):
        s = P.ParticleSystem()
        defs = [make(tile=i) for i in range(P.SLOT_COUNT + 1)]
        got = [s.spawn(x, (0, 0, 0), (0, 0, 0)) for x in defs]
        # slot 0 belongs to the definition particle_init claims (0x7e1d00): 31 are left
        self.assertTrue(all(got[:P.SLOT_COUNT - 1]))
        self.assertIsNone(got[P.SLOT_COUNT - 1])
        self.assertIsNone(got[-1])
        self.assertEqual([x.slot for x in defs[:3]], [1, 2, 3])
        self.assertEqual(s.slots[0], P.SLOT0_DEFINITION)

    def test_fifo_per_list(self):
        s = P.ParticleSystem()
        d = make(life_class=0)
        s.spawn(d, (1, 0, 0), (0, 0, 0))
        for _ in range(5):
            s.update()
        s.spawn(d, (2, 0, 0), (0, 0, 0))
        for _ in range(7):
            s.update()
        self.assertEqual([p.x for p, _ in s.live()], [2])

    def test_group_idle_free(self):
        s = P.ParticleSystem()
        h = s.group_create()
        self.assertEqual(h & 0xff, 0)
        for _ in range(31):
            s.update()
        self.assertIn(h, s.groups)
        s.update()
        self.assertNotIn(h, s.groups)

    def test_group_cutscene_holds(self):
        s = P.ParticleSystem()
        h = s.group_create()
        for _ in range(100):
            s.update(in_cutscene=True)
        self.assertIn(h, s.groups)

    def test_group_free_keeps_slot(self):
        s = P.ParticleSystem()
        h = s.group_create()
        d = make(life_class=3)
        s.group_begin(h)
        s.spawn(d, (0, 0, 0), (0, 0, 0))
        s.group_end(h)
        s.group_free(h)
        self.assertEqual((d.live, d.slot), (1, 1))
        self.assertEqual(len(s.free_pages), P.PAGE_COUNT)

    def test_freed_group_lists_are_inherited(self):
        # a list set left current after its group is freed keeps receiving particles; the
        # next group created in that slot inherits them (particleGroup_create does not reset)
        s = P.ParticleSystem()
        h = s.group_create()
        d = make(life_class=3)
        s.group_begin(h)
        s.group_free(h)
        s.spawn(d, (5, 0, 0), (0, 0, 0))
        s.group_end(h)                       # stale handle: no effect
        self.assertIs(s.current, s.group_lists[0])
        h2 = s.group_create()
        self.assertEqual(h2 & 0xff, 0)
        self.assertEqual([p.x for p, _ in s.live()], [5])

    def test_group_matrix(self):
        s = P.ParticleSystem()
        h = s.group_create()
        self.assertEqual(s.groups[h][1], P.GROUP_IDENTITY)
        m = ((0, 1, 0), (-1, 0, 0), (0, 0, 1), (10, 20, 30))
        s.group_set_matrix(h, m)
        self.assertEqual(s.groups[h][1][3], (10, 20, 30))
        s.group_set_matrix(h + 0x100, ((0,) * 3,) * 4)    # stale handle: ignored
        self.assertEqual(s.groups[h][1][3], (10, 20, 30))

    def test_rz_rounds_toward_zero(self):
        self.assertEqual(P.rz(1.0 / 3.0), 0.3333333134651184)
        self.assertEqual(P.rz(-1.0 / 3.0), -0.3333333134651184)
        self.assertEqual(P.rz(1e-40), 0.0)
        # 60 * (17 / 60) is just below 17 in single precision: the console back-dates 16 ticks
        d = make(life_class=3)
        p = P.spawn_record(d, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 100, backdate=17 / 60.0)
        self.assertEqual(p.birth, 100 - 16)

    def test_clock_rebase(self):
        s = P.ParticleSystem()
        s.clock = 0x7ffe
        d = make(life_class=3)
        s.spawn(d, (0, 0, 0), (0, 0, 0))
        s.update()
        s.update()
        (p, _), = list(s.live())
        self.assertEqual(s.clock, 0)
        self.assertEqual(s.clock - p.birth, 2)


class Flipbook(unittest.TestCase):
    def test_rows(self):
        still = make(tile=0x05)
        self.assertFalse(P.flipbook_step(still, 0))
        row1 = make(tile=0x1f)                 # row 1, last column
        self.assertFalse(P.flipbook_step(row1, 1))
        self.assertTrue(P.flipbook_step(row1, 2))
        self.assertEqual((row1.u0, row1.u1), (16, 31 * 16))   # wrapped to column 0
        row4 = make(tile=0x40)
        self.assertTrue(P.flipbook_step(row4, 1))
        self.assertEqual(row4.u0, 33 * 16)


class Emitters(unittest.TestCase):
    def test_round_trip_and_definition(self):
        r = P.EmitterRecord.new(start_rgba=(1, 2, 3, 4), end_rgba=(5, 6, 7, 8), size_start=2,
                                size_end=-1, gravity=-5, life_class=2, kind=0, tile=0x33,
                                rate=-4, off_x=10, off_y=-20, off_z=30, vel=(0, 0, 40),
                                yaw=0x4000, pitch=0x100, box=(8, 8, 2), spread=6, cone=0x800,
                                on_time=120, off_time=60, flags=2, name='smoke')
        b = r.pack()
        self.assertEqual(len(b), 0x48)
        self.assertEqual(b[0x11], 0xfc)
        self.assertEqual(struct.unpack_from('<i', b, 0x2c)[0], 120)
        self.assertEqual(b[0x3d:0x42], b'smoke')
        back = P.EmitterRecord.parse(b)
        self.assertEqual((back.tile, back.rate, back.vel, back.name), (0x33, -4, (0, 0, 40), 'smoke'))
        d = P.ParticleDef.from_emitter_record(b)
        self.assertEqual((d.kind, d.life_class, d.tile), (0, 2, 0x33))
        self.assertAlmostEqual(d.size0, 200.0)
        other = P.EmitterRecord.parse(b)
        other.rate = 3
        self.assertTrue(r.same_definition(other))

    def test_rate(self):
        rng = P.CosmeticRng(1)
        r = P.EmitterRecord.new(rate=3)
        self.assertEqual(len(P.emitter_run(r, (0, 0, 0), 10, rng)), 3)
        r = P.EmitterRecord.new(rate=-4)
        self.assertEqual(len(P.emitter_run(r, (0, 0, 0), 10, rng)), 0)
        self.assertEqual(len(P.emitter_run(r, (0, 0, 0), 12, rng)), 1)
        r = P.EmitterRecord.new(rate=0)
        self.assertEqual(P.emitter_run(r, (0, 0, 0), 12, rng), [])

    def test_on_off_cycle(self):
        rng = P.CosmeticRng(7)
        r = P.EmitterRecord.new(rate=1, on_time=100, off_time=50, next=0, on=0)
        out = P.emitter_run(r, (0, 0, 0), 1, rng)
        self.assertEqual((r.on, len(out)), (1, 1))
        self.assertTrue(1 + 50 <= r.next < 1 + 150)
        t = r.next + 1
        self.assertEqual(P.emitter_run(r, (0, 0, 0), t, rng), [])
        self.assertEqual(r.on, 0)
        self.assertTrue(t + 25 <= r.next < t + 75)

    def test_straight_up_without_spread(self):
        rng = P.CosmeticRng(3)
        r = P.EmitterRecord.new(rate=1, vel=(0, 0, 32), off_z=5)
        (p, v), = P.emitter_run(r, (100.0, 50.0, 10.0), 1, rng)
        self.assertEqual(p, (100.0, 50.0, 15.0))
        self.assertAlmostEqual(v[0], 0.0, places=9)
        self.assertAlmostEqual(v[2], 32.0, places=9)

    def test_weather_gate(self):
        rng = P.CosmeticRng(3)
        r = P.EmitterRecord.new(rate=2, vel=(10, 0, 0), flags=1)
        self.assertEqual(P.emitter_run(r, (0, 0, 0), 1, rng, weather_on=False), [])
        self.assertEqual(len(P.emitter_run(r, (0, 0, 0), 2, rng, weather_on=True)), 2)

    def test_first_call_at_tick_zero_stays_off(self):
        r = P.EmitterRecord.new(rate=1)
        self.assertEqual(P.emitter_run(r, (0, 0, 0), 0, P.CosmeticRng(1)), [])
        self.assertEqual(r.on, 0)

    def test_rng(self):
        rng = P.CosmeticRng(0)
        self.assertEqual(rng.step(), 0x3c6ef35f)
        self.assertAlmostEqual(P.CosmeticRng(0).r(), 0x3c6e / 65536)

    def test_rotate_axis_matches_core_rules(self):
        m = P.rotate_axis(P.IDENTITY, 2, 0x4000)   # quarter turn about z
        x, y, z = P.transform(m, (1.0, 0.0, 0.0))
        self.assertAlmostEqual(x, 0.0, places=9)
        self.assertAlmostEqual(y, 1.0, places=9)


if __name__ == '__main__':
    unittest.main()
