"""Tests for ref_fx_skills.py on synthetic memory (no game file).

Run: python3 -m unittest discover -s tools -p test_ref_fx_skills.py
"""
import importlib
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_fx_skills as FS                      # noqa: E402

M32 = 0xFFFFFFFF


def f32(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


def fl(raw):
    return struct.unpack('<f', struct.pack('<I', raw & M32))[0]


class Rec:
    """Callbacks that record nothing themselves (the model keeps .calls) and answer with
    scripted values."""

    def __init__(self, answers=None):
        self.answers = answers or {}

    def get(self, name):
        if name in self.answers:
            value = self.answers[name]
            return value if callable(value) else (lambda *a: value)
        return None


def model(answers=None):
    mem = RC.Memory()
    return FS.Model(mem, Rec(answers)), mem


def put_vec(m, addr, values):
    for i, v in enumerate(values):
        m.mem.poke(addr + 4 * i, 4, f32(v))


def calls_named(m, name):
    return [args for n, args in m.calls if n == name]


class Callouts(unittest.TestCase):
    def test_particle(self):
        fx = FS.to_primitive('particle_spawn', (0x8E5910, (f32(1.0), f32(2.0), f32(3.0)),
                                                (f32(0.5), 0, f32(-8.0)), 0))
        self.assertEqual(fx.primitive, 'particle')
        self.assertEqual(fx.fields['definition'], 0x8E5910)
        self.assertEqual(fx.fields['pos'], (1.0, 2.0, 3.0))
        self.assertEqual(fx.fields['vel'], (0.5, 0.0, -8.0))
        self.assertEqual(fx.fields['backdate'], 0.0)

    def test_glow_light_trail_decal(self):
        glow = FS.to_primitive('glow_add', ((0, 0, f32(5.0)), 1, 2, 3, 4, 0xD30000, 0x100, 6, f32(10.0), f32(1408.0)))
        self.assertEqual((glow.fields['r'], glow.fields['flags'], glow.fields['size']), (1, 6, 1408.0))
        self.assertEqual(glow.fields['bias'], 10.0)
        light = FS.to_primitive('LightEffect_ctor', (0x1000, (0, 0, 0), 0, 1) + tuple(f32(v) for v in range(12)))
        self.assertEqual(light.primitive, 'light_effect')
        self.assertEqual((light.fields['c1'], light.fields['seconds']), (1.0, 11.0))
        trail = FS.to_primitive('trail_create', (1, 0x7A, 0, 0x80, 0x80, 0x80, 0x20, f32(0.25)))
        self.assertEqual((trail.fields['row'], trail.fields['width'], trail.fields['lifetime']), (1, 0x7A, 0.25))
        decal = FS.to_primitive('decal_add', ((0, 0, 0), 0x1234, 9, 0, f32(2.0)))
        self.assertEqual((decal.fields['type'], decal.fields['size']), (9, 2.0))

    def test_effects_of_skips_other_calls(self):
        calls = [('sound_playAtPos', (1, (0, 0, 0), 0)), ('fx_spawn', (8, (0, 0, 0))), ('obj_delete', (5,))]
        self.assertEqual([fx.primitive for fx in FS.effects_of(calls)], ['fx_spawn'])
        self.assertIsNone(FS.to_primitive('damage_apply', ()))

    def test_every_callout_is_a_model_callout(self):
        names = {}
        for module in ('ref_skills_a', 'ref_skills_b', 'ref_skills_c', 'ref_arena_monsters', 'ref_fx_skills'):
            for name, ext in importlib.import_module(module).EXTERNALS.items():
                names.setdefault(name, set()).add(ext.addr)
        for name, out in FS.CALLOUTS.items():
            self.assertIn(name, names, name)
            self.assertEqual(names[name], {out.addr}, name)


class Recipes(unittest.TestCase):
    def test_table(self):
        rows = [r for rs in FS.RECIPES.values() for r in rs]
        self.assertEqual(len(rows), 161)
        self.assertEqual(len({r.addr for r in rows}), 161)
        for r in rows:
            self.assertIn(r.phase, FS.PHASES)
            self.assertEqual(r.cls, r.function.split('_', 1)[0])
            module, method = FS.model_method(r)
            self.assertTrue(hasattr(importlib.import_module(module).Model, method), r.model)
            for g in r.generators.split():
                self.assertIn(g, ('own', 'spell', 'SHARED', 'SHARED(LightEffect)', 'cosmetic', 'seed3'))
        self.assertEqual(set(r.addr for r in rows if r.model.startswith('ref_fx_skills.')) - set(FS.DRAW_MODELLED.values()),
                         set())

    def test_recipe_lookup(self):
        phases = [p.phase for p in FS.recipe('MultiFireProjectile')]
        self.assertEqual(phases, ['cast', 'run', 'event'])
        self.assertIn('StaticFire', FS.classes())
        self.assertEqual(FS.recipe('NoSuchClass'), [])


class Draws(unittest.TestCase):
    def test_firearrow_glow(self):
        m, mem = model()
        put_vec(m, 0x1010, (1.0, 2.0, 3.0))
        mem.poke(0x101C, 4, f32(2.0))
        mem.poke(FS.G_GLOW_TEX_B, 4, 0xABC)
        m.firearrow_draw(0x1000)
        (args,) = calls_named(m, 'glow_add')
        self.assertEqual(args[1:8], (0x93, 0x62, 0x49, 0x49, 0xABC, 0, 6))
        self.assertEqual(fl(args[9]), 2816.0)

    def test_holystrike_point_is_beside_and_above(self):
        m, mem = model()
        put_vec(m, 0x1010, (10.0, 20.0, 30.0))
        mem.poke(0x106C, 4, f32(1.0))           # direction (1, 0): the glow sits at -y
        m.holystrike_draw(0x1000)
        (args,) = calls_named(m, 'glow_add')
        self.assertEqual(tuple(fl(v) for v in args[0]), (10.0, 19.0, 31.0))
        self.assertEqual(args[7], 3)

    def test_resurrect_ring_only_offline(self):
        m, mem = model()
        mem.poke(0x2000 + 0x18, 4, 0x3000)
        put_vec(m, 0x3010, (0.0, 0.0, 0.0))
        mem.poke(RC.G_NUM_PLAYERS, 4, 2)
        m.resurrect_draw(0x2000)
        self.assertEqual(calls_named(m, 'glow_add'), [])
        mem.poke(RC.G_NUM_PLAYERS, 4, 1)
        m.resurrect_draw(0x2000)
        glows = calls_named(m, 'glow_add')
        self.assertEqual(len(glows), 13)
        for args in glows:                      # +0x20 = 0: radius 15, full alpha
            x, y, z = (fl(v) for v in args[0])
            self.assertAlmostEqual(x * x + y * y, 225.0, delta=0.5)
            self.assertEqual(z, 116.0)
            self.assertEqual(args[4], 128)

    def test_smoke_ring_wraps_at_100(self):
        m, mem = model({'isNearView': 1})
        obj = 0x4000
        mem.poke(obj + 0x438, 2, 98)
        mem.poke(obj + 0x43A, 2, 2)
        mem.poke(obj + 0x464, 4, 1)
        mem.poke(obj + 0x474, 4, f32(1.0))
        m.smokegen_draw(obj)
        self.assertEqual(len(calls_named(m, 'glow_add')), 4)        # 98, 99, 0, 1


class Objects(unittest.TestCase):
    def test_multifire_end_burst_by_level_flag(self):
        for flags, burst in ((0, 2), (0x40000, 8)):
            m, mem = model({'libc_sprintf': ('buf', b'x'), 'res_find': 1})
            mem.poke(FS.MultiFire.LEVEL_FLAGS, 4, flags)
            m.multifire_end(0x5000, 1)
            self.assertEqual(calls_named(m, 'fx_spawn')[0][0], burst)
            self.assertEqual(mem.load(0x5060, 4), 1)
            m.calls = []
            m.multifire_end(0x5000, 1)          # once only
            self.assertEqual(m.calls, [])

    def test_multifire_run_ten_particles_from_own_generator(self):
        m, mem = model({'obj_moveAndCollide': 0})
        mem.poke(0x5044, 4, 12345)
        m.multifire_run(0x5000)
        spawns = calls_named(m, 'particle_spawn')
        self.assertEqual(len(spawns), 10)
        self.assertNotEqual(mem.load(0x5044, 4), 12345)
        self.assertEqual(mem.load(0x506C, 4), 1)
        for args in spawns:
            self.assertEqual(args[0], FS.MultiFire.MF_PARTICLE)
            self.assertLessEqual(sum(fl(v) ** 2 for v in args[2]), 64.0001)

    def test_pustule_falls_with_still_particles(self):
        m, mem = model()
        obj = 0x6000
        put_vec(m, obj + 0x10, (0.0, 0.0, 100.0))
        mem.poke(obj + 0x54, 4, f32(-50.0))
        m.pustule_run(obj)
        spawns = calls_named(m, 'particle_spawn')
        self.assertEqual(len(spawns), 3)
        self.assertTrue(all(args[2] == (0, 0, 0) for args in spawns))
        self.assertEqual(mem.load(obj + 0x64, 4), 1)

    def test_disease_cloud_hurts_without_attacker(self):
        victim = 0x7100
        m, mem = model({'world_collectObjectsInBox': [victim]})
        obj = 0x7000
        node = 0x7200
        mem.poke(obj + 0x54, 4, 1000)
        mem.poke(obj + 0x58, 4, 0)
        mem.poke(obj + 0x60, 4, 7)
        mem.poke(obj + 0x4C, 4, node)
        mem.poke(node + 0xC, 4, 0x7300)
        mem.poke(RC.G_SIM_FRAME, 4, 60)
        m.diseasecloud_run(obj)
        (args,) = calls_named(m, 'damage_apply')
        self.assertEqual(args[:2], (victim, 0))
        self.assertEqual(args[6][2], (0x26, 7, 7, 0))

    def test_staticfire_flame_ring(self):
        m, mem = model()
        obj, ring = 0x8000, 0x9000
        mem.poke(obj + 0x4A4, 4, ring)
        mem.poke(obj + 0x76, 2, 3)               # a ring of three points: holds two
        mem.poke(obj + 0x1C, 4, f32(16.0))
        mem.poke(obj + 0x64, 4, f32(1.0))
        mem.poke(obj + 0x58, 4, f32(20.0))
        for _ in range(3):
            m.staticfire_add_flame(obj)
        self.assertEqual(mem.load(obj + 0x78, 2), 2)                # the third did not fit
        self.assertEqual(mem.load(obj + 0x7A, 2), 0)
        for _ in range(3):
            m.staticfire_move_flames(obj)
        self.assertGreaterEqual(C.s16(mem.load(ring + 4, 2)), 21)    # risen by 21 in 1/16 units

    def test_from_uint(self):
        self.assertEqual(fl(FS._from_uint(5)), 5.0)
        self.assertEqual(fl(FS._from_uint(0xFFFFFFFF)), 4294967040.0)          # toward zero


if __name__ == '__main__':
    unittest.main()
