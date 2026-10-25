#!/usr/bin/env python3
"""test_ref_phprop_run.py - unit tests of tools/ref_phprop_run.py that need no game files.

Made-up memory: gravity and its option, the water test's frame gate and splash, a ground
contact (impulse, push, damping), the rest conversion (which constructor, its shared draw, the
matrix), the -220 limit, the player-height delete, the burning prop's StaticFire, the rigid
body helpers, the landing sounds, and GutChunk_run's bounce delete, decal counter and resting
decal.  Whether the model matches the game is tools/difftest_phprop_run.py's business (it
needs the executable)."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_phprop_run as PR                     # noqa: E402

f32 = C.f32
OBJ, BLOCK, MODEL, TABLE, PLAYER, DEF = 0x100000, 0x110000, 0x120000, 0x130000, 0x140000, 0x150000
M32 = 0xFFFFFFFF
I3 = [C.ONE, 0, 0, 0, C.ONE, 0, 0, 0, C.ONE]


def lcg(seed):
    return (seed * 0x19660D + 0x3C6EF35F) & M32


def fl(raw):
    return C.to_float(raw)


class Fixture(unittest.TestCase):
    ground = 0.0
    sweep = (C.ONE, 0, 0)
    water = 0
    block = BLOCK

    def setUp(self):
        C.set_fpu('ps2')
        self.mem = RC.Memory()
        self.model = PR.Model(self.mem, self)
        self.poke(RC.G_RAND_SEED, 0x1234)
        self.poke(PR.G_SIM_FRAME, 1)
        self.text(PR.S_SPLASH_FORMAT, b'splash_sound_%d')
        for addr, text in ((PR.SND_WOOD, b'drop_sound_wood'), (PR.SND_METAL, b'drop_sound_metal'),
                           (PR.SND_SHIELD, b'drop_sound_shield'), (PR.SND_CHAIN, b'drop_sound_chain'),
                           (PR.SND_JEWELRY, b'drop_sound_jewelry')):
            self.text(addr, text)
        self.prop(OBJ)

    # ---- the made-up world ---------------------------------------------------------------
    def get(self, name):
        if name in ('terrain_heightBelow', 'terrain_height'):
            return lambda *args: f32(self.ground)
        if name == 'terrain_sweepCircle':
            return lambda *args: self.sweep
        if name == 'water_test':
            return lambda *args: self.water
        if name == 'pool_new':
            return lambda size: self.block
        if name in ('res_find', 'obj_getPropInt', 'sound_playOnObject', 'handle_link'):
            return lambda *args: 0
        return None

    def poke(self, addr, value, size=4):
        self.mem.poke(addr, size, value & ((1 << (8 * size)) - 1))

    def pokef(self, addr, *values):
        for k, v in enumerate(values):
            self.poke(addr + 4 * k, f32(v))

    def text(self, addr, data):
        for j, b in enumerate(data + b'\0'):
            self.mem.poke(addr + j, 1, b)

    def u32(self, addr):
        return self.mem.load(addr, 4)

    def f(self, addr):
        return fl(self.u32(addr))

    def calls(self, name):
        return [args for n, args in self.model.calls if n == name]

    def prop(self, obj, z=50.0):
        """A prop at rest in the air: mass 1, unit inertia, identity orientation, life 180,
        no parts (so no hull points), PhProp table."""
        self.pokef(obj + 0x10, 10.0, 20.0, z)
        self.pokef(obj + 0x1C, 4.0)
        self.poke(obj + 0x48, 0x511BA8)
        self.poke(obj + 0x4C, MODEL)
        self.poke(obj + 0x10E, 180, 2)
        self.pokef(obj + 0x190, 1.0, 1.0, 1.0, 1.0)
        self.pokef(obj + 0x1A0, 10.0, 20.0, z)
        self.pokef(obj + 0x1AC, 0.0, 0.0, 0.0, 1.0)
        for k, v in enumerate(I3):
            self.poke(obj + 0x1D4 + 4 * k, v)
            self.poke(obj + 0x1F8 + 4 * k, v)
        self.pokef(obj + 0x228, -100.0)
        self.pokef(obj + 0x23C, -0.4)
        self.pokef(obj + 0x240, 1.0)
        self.text(obj + 0x54, b'fx.lmp')
        self.text(obj + 0x64, b'gutchunks.vif')
        self.text(obj + 0xA4, b'gutchunks.tex')

    def hull(self, mesh, points):
        self.poke(MODEL + 0x25, 4, 1)                                    # the table at +0x40
        for j, p in enumerate(points):
            for i in range(3):
                self.poke(MODEL + 0x40 + 24 * mesh + 3 * j + i, p[i], 1)
        self.poke(OBJ + 0xE8, 1 << mesh, 8)


class Flight(Fixture):
    def test_gravity(self):
        self.model.phprop_run(OBJ)
        self.assertAlmostEqual(self.f(OBJ + 0x1C4), -0.18, places=6)
        self.assertAlmostEqual(self.f(OBJ + 0x1A8), 50.0 - 0.18, places=4)
        self.assertEqual(self.f(OBJ + 0x18), 50.0)                      # the old body z
        self.assertEqual(self.u32(OBJ + 0x228), f32(0.0))
        self.assertEqual(self.mem.load(OBJ + 0x10E, 2), 179)
        self.assertEqual([n for n, _a in self.model.calls], ['terrain_heightBelow', 'obj_updateGridCell'])

    def test_low_gravity_option(self):
        self.poke(PR.G_PROP_OPTIONS, 0x100)
        self.pokef(OBJ + 0x190, 0.5)
        self.model.phprop_run(OBJ)
        self.assertAlmostEqual(self.f(OBJ + 0x1C4), -0.054 / 0.5, places=6)

    def test_water_gate_and_splash(self):
        self.water = 1
        self.model.phprop_run(OBJ)                                     # frame 1: no test
        self.assertEqual(self.calls('water_test'), [])
        self.poke(PR.G_SIM_FRAME, 16)
        seed = self.u32(OBJ + 0x44)
        self.model.phprop_run(OBJ)
        self.assertEqual(self.mem.load(OBJ + 0x239, 1), 1)
        self.assertEqual(self.u32(OBJ + 0x44), lcg(seed))               # one own draw
        self.assertEqual(self.calls('libc_sprintf'), [(PR.S_SPLASH_FORMAT, 1)])
        self.assertEqual(self.calls('res_find')[0], (PR.S_FX_LUMP, ('buf', b'splash_sound_1')))
        self.assertEqual(self.calls('sound_playOnObject')[0][2], PR.F_SPLASH_VOL)
        self.assertEqual(self.calls('water_disturb')[0][2:], (PR.F_700, PR.F_24))
        self.model.calls[:] = []
        self.model.phprop_run(OBJ)                                     # in water: never again
        self.assertEqual(self.calls('water_test'), [])

    def test_sweep_wall_pushes_back(self):
        self.pokef(OBJ + 0x1BC, 2.0, 0.0)
        self.sweep = (f32(0.5), f32(-1.0), 0)
        self.model.phprop_run(OBJ)
        self.assertAlmostEqual(self.f(OBJ + 0x10), 11.0, places=5)     # half of the move
        self.assertEqual(len(self.calls('obj_updateGridCell')), 2)
        # a = 0.001 - (-1 x 2) = 2.001; momentum x += -1 x a x 1.5
        self.assertAlmostEqual(self.f(OBJ + 0x1BC), 2.0 - 2.001 * 1.5, places=4)

    def test_contact_bounces(self):
        """One hull point 1 under the level: impulse up, +0x230, horizontal damping."""
        self.hull(0, [(0, 0, -60)] * 8)                                 # 10 under the ground
        self.pokef(OBJ + 0x228, 0.0)
        self.pokef(OBJ + 0x1BC, 1.0, 0.0, -3.0)
        self.model.phprop_run(OBJ)
        self.assertEqual(self.u32(OBJ + 0x230), 1)
        self.assertGreater(self.f(OBJ + 0x1C4), 0.0)                   # bounced
        self.assertLess(self.f(OBJ + 0x1BC), 1.0)                      # x 0.95 after contact
        self.assertEqual(self.calls('sound_playOnObject'), [])         # no prop bits 8/0x10

    def test_countdown_skips_points(self):
        self.hull(0, [(0, 0, -60)] * 8)
        self.pokef(OBJ + 0x228, 0.0)
        self.poke(OBJ + 0x234, 3)
        self.model.phprop_run(OBJ)
        self.assertEqual(self.u32(OBJ + 0x234), 0)
        self.assertEqual(self.u32(OBJ + 0x230), 1)                     # points 4..8 still collide

    def test_spin_clamp(self):
        self.poke(OBJ + 0x140, 0x20, 2)
        self.pokef(OBJ + 0x1C8, 3.0, -3.0, 0.01)
        self.pokef(OBJ + 0x194, 0.1, 0.1, 0.1)
        self.model.phprop_run(OBJ)
        self.assertAlmostEqual(self.f(OBJ + 0x1C8), 0.5 * 0.95, places=5)
        self.assertAlmostEqual(self.f(OBJ + 0x1CC), -0.5 * 0.95, places=5)


class Rest(Fixture):
    def still(self, life):
        self.poke(OBJ + 0x10E, life, 2)

    def test_rest_named_prop(self):
        self.still(0)
        self.model.phprop_run(OBJ)
        self.assertEqual(self.calls('pool_new'), [(0x148,)])
        self.assertEqual(self.model.draws, 1)                          # GameObject_ctor
        self.assertEqual(self.u32(BLOCK + 0x48), PR.VT_PROP)
        self.assertEqual(self.u32(BLOCK + 0xC) & 0x1809, 0x1809)
        self.assertEqual(self.mem.load(BLOCK + 0x140, 2), 1)
        self.assertEqual(self.calls('obj_delete'), [(OBJ,)])
        self.assertEqual(self.u32(BLOCK + 0x110), C.ONE)                # identity rotation
        self.assertEqual(self.u32(BLOCK + 0x134), f32(10.0))
        self.assertEqual(self.mem.load(OBJ + 0x10E, 2), 0xFFFF)         # decremented first

    def test_rest_needs_stillness(self):
        self.still(0)
        self.pokef(OBJ + 0x1C8, 0.5)
        self.model.phprop_run(OBJ)
        self.assertEqual(self.calls('pool_new'), [])
        self.assertEqual(self.calls('obj_delete'), [])

    def test_life_limit(self):
        self.pokef(OBJ + 0x1C8, 5.0)
        self.still(-220 & 0xFFFF)
        self.model.phprop_run(OBJ)
        self.assertEqual(self.calls('obj_delete'), [])
        self.assertEqual(self.mem.load(OBJ + 0x10E, 2), -221 & 0xFFFF)
        self.model.phprop_run(OBJ)
        self.assertEqual(self.calls('obj_delete'), [(OBJ,)])
        self.assertEqual(self.mem.load(OBJ + 0x10E, 2), -221 & 0xFFFF)  # not decremented

    def test_rest_res_prop_and_no_block(self):
        self.still(0)
        self.poke(OBJ + 0x54, 0, 1)
        self.poke(OBJ + 0x4C, 0xABC)
        self.model.phprop_run(OBJ)
        self.assertEqual(self.u32(BLOCK + 0x4C), 0xABC)
        self.assertEqual(self.u32(BLOCK + 0xC) & 0x5809, 0x5809)
        self.block = 0
        self.prop(OBJ)
        self.pokef(OBJ + 0x1BC, 0.0, 0.0, 0.0)
        self.still(0)
        self.model.calls[:] = []
        self.model.phprop_run(OBJ)
        self.assertEqual(self.calls('obj_delete'), [(OBJ,)])           # deleted even without a block

    def test_rest_item(self):
        self.still(0)
        self.poke(OBJ + 0x238, 1, 1)
        self.poke(OBJ + 0x148, DEF)
        self.poke(DEF + 0x34, 3, 2)
        self.model.phprop_run(OBJ)
        self.assertEqual(self.calls('pool_new'), [(0x190,)])
        self.assertEqual(self.u32(BLOCK + 0x48), PR.VT_ITEMPROP)
        self.assertEqual(self.u32(BLOCK + 0x148), DEF)
        self.assertEqual(self.mem.load(BLOCK + 0xE8, 8), (1 << 64) - 1)
        self.assertEqual(self.u32(BLOCK + 0xC) & 0x103800, 0x102000)

    def test_player_height_delete(self):
        self.poke(PR.G_NUM_PLAYERS, 1)
        self.poke(PR.G_ALIVE_PLAYERS, 0)
        self.poke(PR.G_PLAYER_OBJ, PLAYER)
        self.pokef(PLAYER + 0x18, 170.0)                               # 50 + 120 is not below 170
        self.model.phprop_run(OBJ)
        self.assertEqual(self.calls('obj_delete'), [])
        self.pokef(PLAYER + 0x18, 171.0)
        self.model.phprop_run(OBJ)
        self.assertEqual(self.calls('obj_delete'), [(OBJ,)])

    def test_static_fire(self):
        self.poke(OBJ + 0x23A, 1, 1)
        self.ground = 45.0
        seed = self.u32(OBJ + 0x44)
        self.model.phprop_run(OBJ)
        self.assertEqual(self.mem.load(OBJ + 0x23A, 1), 2)
        d = lcg(seed) >> 16
        fire = self.calls('StaticFire_ctor')
        self.assertEqual(len(fire), 1)
        self.assertEqual(fire[0][2], (d % 40) * 60 + 480)
        self.assertEqual(fire[0][5:], (PR.F_240, C.HALF))


class Body(Fixture):
    def test_point_velocity(self):
        body = OBJ + 0x190
        self.pokef(body + 0x8C, 0.0, 0.0, 1.0)                          # spin about z
        self.pokef(body + 0x2C, 0.5, 0.0, 0.0)
        v = self.model.rb_point_velocity(body, [f32(11.0), f32(20.0), f32(50.0)])
        self.assertEqual([fl(x) for x in v], [0.5, 1.0, 0.0])

    def test_add_force_torque(self):
        fsum, tsum = [0, 0, 0], [0, 0, 0]
        self.model.rb_add_force(OBJ + 0x190, [f32(11.0), f32(20.0), f32(50.0)], (0, 0, f32(2.0)), fsum, tsum)
        self.assertEqual([fl(x) for x in fsum], [0.0, 0.0, 2.0])
        self.assertEqual([fl(x) for x in tsum], [0.0, -2.0, 0.0])         # (1,0,0) x (0,0,2)

    def test_integrate_still(self):
        body = OBJ + 0x190
        self.model.rb_integrate(C.ONE, body, [0, 0, f32(1.0)], [0, 0, 0])
        self.assertEqual(self.u32(body + 0x34), f32(1.0))
        self.assertEqual([self.u32(body + 0x44 + 4 * k) for k in range(9)], I3)

    def test_landing_sounds(self):
        self.poke(OBJ + 0x140, 8, 2)
        self.assertEqual(self.model.landing_sound(OBJ), PR.SND_WOOD)
        self.poke(OBJ + 0x238, 1, 1)
        self.poke(OBJ + 0x148, DEF)
        self.poke(OBJ + 0x150, 0x40000, 8)
        self.assertEqual(self.model.landing_sound(OBJ), PR.SND_METAL)
        self.poke(DEF + 0x1D, 1, 1)
        self.poke(DEF + 0x1C, 3, 1)
        self.assertEqual(self.model.landing_sound(OBJ), PR.SND_SHIELD)
        self.poke(DEF + 0x1C, 1, 1)
        self.assertEqual(self.model.landing_sound(OBJ), PR.SND_METAL2)
        self.poke(OBJ + 0x150, 0x10000000, 8)
        self.assertEqual(self.model.landing_sound(OBJ), PR.SND_JEWELRY)
        self.poke(OBJ + 0x150, 0, 8)
        self.assertIsNone(self.model.landing_sound(OBJ))


class Gut(Fixture):
    def setUp(self):
        Fixture.setUp(self)
        self.poke(OBJ + 0x48, TABLE)
        self.poke(TABLE + 0xC, PR.GUTCHUNK_DTOR)
        self.poke(OBJ + 0x25C, 2)
        self.ground = 49.0

    def bounce(self, last=-3.0):
        """Falling last frame, rising now (an upward momentum before gravity)."""
        self.pokef(OBJ + 0x24C, last)
        self.pokef(OBJ + 0x1C4, 2.0)

    def test_bit0_destroys_on_bounce(self):
        self.poke(OBJ + 0x248, 1)
        self.bounce()
        self.model.gutchunk_run(OBJ)
        self.assertEqual(self.calls('GutChunk_dtor'), [(OBJ, 3)])
        self.assertEqual(self.calls('res_find'), [(PR.S_FX_LUMP2, PR.S_GUT_SPLAT)])
        self.assertEqual(self.f(OBJ + 0x24C), -3.0)                    # not stored

    def test_bounce_decals_count_down(self):
        self.poke(OBJ + 0x248, 2)
        self.poke(OBJ + 0x260, 1, 1)                                  # resting decal already made
        self.bounce(-0.5)
        seed = self.u32(OBJ + 0x44)
        self.model.gutchunk_run(OBJ)
        self.assertEqual(self.u32(OBJ + 0x25C), 1)
        decal = self.calls('decal_add')
        self.assertEqual(len(decal), 1)
        self.assertEqual(decal[0][2:], (7, 0, PR.F_TWELVE))
        self.assertEqual(self.calls('res_find'), [])                   # -0.5 is no hard bounce
        draws = 0
        while seed != self.u32(OBJ + 0x44):
            seed, draws = lcg(seed), draws + 1
        self.assertEqual(draws, 3)                                     # rising > 1: 1, decal: 2
        self.assertAlmostEqual(self.f(OBJ + 0x24C), 2.0 - 0.18, places=5)

    def test_bit8_counts_without_decal(self):
        self.poke(OBJ + 0x248, 8)
        self.bounce(-0.5)
        self.model.gutchunk_run(OBJ)
        self.assertEqual(self.u32(OBJ + 0x25C), 1)
        self.assertEqual(self.calls('decal_add'), [])

    def test_resting_decal_once(self):
        self.poke(OBJ + 0x248, 4)
        self.model.gutchunk_run(OBJ)
        decal = self.calls('decal_add')
        self.assertEqual([d[2:] for d in decal], [(3, 1, PR.F_TWELVE)])
        self.assertEqual(self.mem.load(OBJ + 0x260, 1), 1)
        self.model.gutchunk_run(OBJ)
        self.assertEqual(len(self.calls('decal_add')), 1)

    def test_falling_decal_crossing(self):
        """Bits & 9 = 1: a decal when the vertical speed crosses -1 this frame."""
        self.poke(OBJ + 0x248, 1)
        self.pokef(OBJ + 0x24C, -0.9)
        self.pokef(OBJ + 0x1C4, -0.9)
        self.model.gutchunk_run(OBJ)                                   # -0.9 - 0.18 = -1.08
        self.assertEqual(len(self.calls('decal_add')), 1)
        self.assertEqual(self.calls('decal_add')[0][3], 0)

    def test_particle_needs_option(self):
        self.poke(OBJ + 0x260, 1, 1)
        self.pokef(OBJ + 0x1C4, 3.0)
        for option in (0, 1):
            self.poke(PR.G_DECAL_DETAIL, option)
            self.model.calls[:] = []
            seed = self.u32(OBJ + 0x44)
            self.model.gutchunk_run(OBJ)
            d = lcg(seed) >> 16
            expect = 1 if option and d % 3 == 0 else 0
            self.assertEqual(len(self.calls('particle_spawn')), expect)
            self.assertEqual(self.u32(OBJ + 0x44), lcg(seed))         # drawn either way


class Contract(unittest.TestCase):
    def test_executed_and_externals(self):
        self.assertEqual(PR.EXECUTED['PhProp_run'], 0x155FCC)
        self.assertEqual(PR.EXECUTED['GutChunk_run'], 0x1EDB18)
        self.assertEqual(PR.CLASS_BODIES[0x50F3B8], ('GutChunk', 0x1EDB18))
        for name in PR.SERVICES + PR.PRESENTATION:
            self.assertIn(name, PR.EXTERNALS)
        self.assertFalse(set(PR.EXECUTED.values()) & {e.addr for e in PR.EXTERNALS.values()})


if __name__ == '__main__':
    unittest.main()
