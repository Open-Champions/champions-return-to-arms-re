#!/usr/bin/env python3
"""Synthetic tests for the round-4 combat bodies.  No game files.

The fixtures are authored.  What is checked is the composed behaviour of
tools/ref_combat_round4.py.  Agreement with the original is tools/difftest_combat_round4.py.
"""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_ranged as RR                  # noqa: E402
import ref_combat_round4 as R4                  # noqa: E402
import ref_combat_runtime as T                  # noqa: E402

OBJ, OWNER, NODE, BLOCK = 0x2000, 0x3000, 0x3100, 0x4000


class Callbacks:
    def __init__(self, collide=0, pool=BLOCK, ground=0):
        self.collide, self.pool, self.ground, self.calls = collide, pool, ground, []

    def get(self, name):
        def answer(*args):
            self.calls.append((name, args))
            if name == 'obj_moveAndCollide':
                return self.collide
            if name == 'pool_new':
                return self.pool
            if name == 'terrain_height':
                return self.ground
            if name == 'res_find':
                return 0xA10000
            return 0
        return answer


def plant(mem, kind, frame=100, expiry=None, spin=0, splash=0, owner=OWNER):
    mem.store(RC.G_SIM_FRAME, 4, frame)
    mem.store(RC.G_RAND_SEED, 4, 1)
    mem.store(RR.G_WORLD, 4, 0x1000)
    mem.store(OBJ + 0x48, 4, RR.VT_THROWN)
    mem.store(OBJ + 0x10, 4, C.f32(10.0))
    mem.store(OBJ + 0x14, 4, C.f32(20.0))
    mem.store(OBJ + 0x18, 4, C.f32(30.0))
    mem.store(OBJ + 0x1B0, 4, C.f32(1.0))
    mem.store(OBJ + 0x1B4, 4, C.f32(2.0))
    mem.store(OBJ + 0x1B8, 4, C.f32(40.0))
    mem.store(OBJ + 0x1C, 4, C.f32(12.0))
    mem.store(OBJ + 0xEC, 4, frame + 80 if expiry is None else expiry)
    mem.poke(OBJ + 0x1CC, 2, spin & 0xFFFF)
    mem.poke(OBJ + 0x1CE, 1, kind)
    mem.poke(OBJ + 0xCC, 1, splash)
    if owner:
        mem.store(OBJ + 0x1C8, 4, NODE)
        mem.store(NODE + 0xC, 4, owner)
    # The blast compares this buffer with the name at 0x535ed8.  Tests that care
    # about the name plant it; the default is not that name.
    for i, byte in enumerate(b'town\0'):
        mem.poke(R4.G_LEVEL_TEXT + i, 1, byte)


def model(kind, **kw):
    mem = RC.Memory()
    plant(mem, kind, **{k: kw.pop(k) for k in list(kw) if k in ('frame', 'expiry', 'spin', 'splash', 'owner')})
    cb = Callbacks(**kw)
    return R4.PotionModel(mem, cb), mem, cb


class PotionTests(unittest.TestCase):
    def test_kind1_in_flight_emits_three_particles_and_keeps_flying(self):
        m, mem, cb = model(1, collide=0)
        m.thrown_run(OBJ)
        flames = [c for c in cb.calls if c[0] == 'particle_spawn']
        self.assertEqual(len(flames), 3)
        self.assertEqual(flames[0][1][0], R4.P_FLAME_A)
        self.assertEqual(flames[2][1][0], R4.P_FLAME_B)
        self.assertEqual(flames[0][1][3], 0)
        self.assertNotIn('Creature.v1', [c[0] for c in cb.calls])
        self.assertNotIn('LooseFire_ctor', [c[0] for c in cb.calls])
        self.assertEqual(mem.load(OBJ + 0x1B8, 4), C.sub(C.f32(40.0), RR.F_GRAVITY))

    def test_kind1_hit_lays_five_fires_and_destroys(self):
        m, mem, cb = model(1, collide=1, ground=C.f32(4.0))
        m.thrown_run(OBJ)
        fires = [args for name, args in cb.calls if name == 'LooseFire_ctor']
        decals = [args for name, args in cb.calls if name == 'decal_add']
        self.assertEqual(len(fires), 5)
        self.assertEqual(len(decals), 5)
        self.assertEqual(fires[0][2], OWNER)
        self.assertEqual(fires[0][1][2], C.add(C.f32(4.0), C.ONE))
        self.assertEqual(decals[0][1:], (decals[0][1], 9, 0, R4.F_THIRTY_SIX))
        self.assertEqual(cb.calls[-1], ('Creature.v1', (OBJ, 3)))
        self.assertEqual(mem.load(OBJ + 0xEC, 4), 0)

    def test_a_splash_overlap_skips_the_stone_sound(self):
        plain, _mem, plain_cb = model(1, collide=2, splash=0)
        plain.thrown_run(OBJ)
        splash, _mem2, splash_cb = model(1, collide=2, splash=1)
        splash.thrown_run(OBJ)
        # The stone sample is a res_find before the fire sample.  A splash byte skips it.
        self.assertEqual(len([c for c in plain_cb.calls if c[0] == 'res_find']), 2)
        self.assertEqual(len([c for c in splash_cb.calls if c[0] == 'res_find']), 1)

    def test_kind2_builds_a_gas_cloud_for_the_owner(self):
        m, _mem, cb = model(2, collide=1)
        m.thrown_run(OBJ)
        gas = [args for name, args in cb.calls if name == 'poisonGasSpell_ctor']
        self.assertEqual(len(gas), 1)
        block, _pos, life, radius, zero, owner, damage = gas[0]
        self.assertEqual((block, life, radius, zero, owner, damage), (BLOCK, 0x12C, 0x14, 0, OWNER, 5))
        sounds = [args for name, args in cb.calls if name == 'sound_playOnObject']
        self.assertEqual(sounds[-1][1], BLOCK)

    def test_kind2_with_no_block_still_destroys_the_potion(self):
        m, _mem, cb = model(2, collide=0, expiry=0, pool=0)
        m.thrown_run(OBJ)
        self.assertFalse([c for c in cb.calls if c[0] == 'poisonGasSpell_ctor'])
        self.assertEqual(cb.calls[-1], ('Creature.v1', (OBJ, 3)))

    def test_kind3_damages_unless_the_level_is_innpit(self):
        m, mem, cb = model(3, collide=1, ground=C.f32(30.0))
        m.thrown_run(OBJ)
        hits = [args for name, args in cb.calls if name == 'world_damageInRadius']
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][0], OWNER)
        self.assertEqual(hits[0][2:6], (0x32, 0x40840, 0, 0))
        self.assertEqual(hits[0][6:], (R4.F_FORTY, R4.F_ONE_EIGHTY))
        self.assertTrue([c for c in cb.calls if c[0] == 'decal_add'])
        lights = [args for name, args in cb.calls if name == 'LightEffect_ctor']
        self.assertEqual(len(lights), 1)
        self.assertEqual(lights[0][4], R4.F_ONE_TWENTY_EIGHT)
        self.assertEqual(lights[0][-1], R4.F_THIRD)

        for i, byte in enumerate(b'InNpIt\0'):
            mem.poke(R4.G_LEVEL_TEXT + i, 1, byte)
        for i, byte in enumerate(b'innpit\0'):
            mem.poke(R4.S_INNPIT + i, 1, byte)
        cb.calls.clear()
        m.thrown_run(OBJ)
        self.assertFalse([c for c in cb.calls if c[0] == 'world_damageInRadius'])

    def test_kind3_skips_the_decal_when_the_ground_is_4_away(self):
        m, _mem, cb = model(3, collide=0, expiry=0, ground=C.add(C.f32(30.0), C.f32(4.0)))
        m.thrown_run(OBJ)
        self.assertFalse([c for c in cb.calls if c[0] == 'decal_add'])

        m, _mem, cb = model(3, collide=0, expiry=0, ground=C.add(C.f32(30.0), C.f32(-1.0)))
        m.thrown_run(OBJ)
        self.assertEqual(len([c for c in cb.calls if c[0] == 'decal_add']), 1)

    def test_the_round2_model_still_refuses_a_potion(self):
        mem = RC.Memory()
        plant(mem, 1)
        with self.assertRaises(T.Unsupported):
            RR.RangedModel(mem, Callbacks()).thrown_run(OBJ)


SPELL, CASTER, SKILL, MODEL = 0x5000, 0x6000, 0x7000, 0x8000


class ShieldCallbacks:
    def __init__(self, points=4, stat=100, pool=BLOCK):
        self.points, self.stat, self.pool, self.calls = points, stat, pool, []

    def get(self, name):
        def answer(*args):
            self.calls.append((name, args))
            if name == 'Creature.v16':
                return MODEL
            if name == 'model_getSamplePointCount':
                return self.points
            if name == 'model_getSamplePoint':
                return ((C.f32(1.0), C.f32(2.0), C.f32(3.0)), 0)
            if name == 'pool_new':
                return self.pool
            if name == 'Skill.v10':
                return self.stat
            return 0
        return answer


def shield(cooldown=0, level=1, **kw):
    mem = RC.Memory()
    mem.store(SPELL + 0x8, 4, SKILL)
    mem.store(SPELL + 0xC, 4, CASTER)
    mem.store(SPELL + 0x10, 4, 1)
    mem.store(SPELL + 0x1C, 4, cooldown)
    mem.store(SPELL + 0x24, 4, 0xD0)
    mem.poke(SPELL, 1, level)
    mem.store(CASTER + 0x10, 4, C.f32(10.0))
    mem.store(CASTER + 0x14, 4, C.f32(20.0))
    mem.store(CASTER + 0x18, 4, C.f32(30.0))
    cb = ShieldCallbacks(**kw)
    return R4.ShieldModel(mem, cb), mem, cb


class ShieldTests(unittest.TestCase):
    def test_a_due_shield_lays_241_particles_and_a_light(self):
        m, mem, cb = shield(0, stat=100)
        got = m.holy_shield_absorb(SPELL)
        flames = [c for c in cb.calls if c[0] == 'particle_spawn']
        self.assertEqual(len(flames), 241)
        self.assertEqual(flames[0][1][0], R4.P_HOLY)
        self.assertEqual(flames[0][1][3], 0)
        self.assertTrue([c for c in cb.calls if c[0] == 'LightEffect_ctor'])
        self.assertEqual(mem.load(SPELL + 0x1C, 4), R4.F_COOLDOWN)
        self.assertEqual(got, C.mul(C.from_int(100), R4.F_HUNDREDTH))

    def test_a_live_cooldown_skips_the_light(self):
        m, mem, cb = shield(C.ONE, stat=0)
        got = m.holy_shield_absorb(SPELL)
        self.assertFalse([c for c in cb.calls if c[0] == 'pool_new'])
        self.assertEqual(mem.load(SPELL + 0x1C, 4), C.ONE)
        self.assertEqual(got, 0)

    def test_a_refused_pool_still_starts_the_cooldown(self):
        m, mem, cb = shield(0, pool=0, stat=10)
        m.holy_shield_absorb(SPELL)
        self.assertFalse([c for c in cb.calls if c[0] == 'LightEffect_ctor'])
        self.assertEqual(mem.load(SPELL + 0x1C, 4), R4.F_COOLDOWN)


PLAYER = 0x9000


class SparkCallbacks:
    def __init__(self, points=2):
        self.points, self.calls = points, []

    def get(self, name):
        def answer(*args):
            self.calls.append((name, args))
            if name == 'model_getSamplePointCount':
                return self.points
            if name == 'model_getSamplePoint':
                return ((C.f32(4.0), C.f32(5.0), C.f32(6.0)), 0)
            if name == 'model_getAttachPoint':
                return (C.f32(0.0), C.f32(0.0), C.f32(0.0))
            return 0
        return answer


def sparks(points=2):
    mem = RC.Memory()
    mem.store(PLAYER + 0x544, 4, MODEL)
    mem.store(PLAYER + 0x10, 4, C.f32(1.0))
    mem.store(PLAYER + 0x14, 4, C.f32(2.0))
    mem.store(PLAYER + 0x18, 4, C.f32(3.0))
    mem.store(RC.G_RAND_SEED, 4, 1)
    cb = SparkCallbacks(points)
    return R4.SparkModel(mem, cb), mem, cb


class SparkTests(unittest.TestCase):
    def test_silent_1_spawns_five_per_sample_point(self):
        m, _mem, cb = sparks(2)
        m.block_sparks(PLAYER, 1)
        flames = [c for c in cb.calls if c[0] == 'particle_spawn']
        self.assertEqual(len(flames), 10)
        self.assertTrue(all(c[1][0] == R4.P_BLOCK_A for c in flames))
        self.assertEqual(len([c for c in cb.calls if c[0] == 'model_getAttachPoint']), 2)

    def test_silent_3_draws_the_balls_and_spawns_nothing(self):
        m, _mem, cb = sparks(1)
        m.block_sparks(PLAYER, 3)
        self.assertFalse([c for c in cb.calls if c[0] == 'particle_spawn'])
        self.assertEqual(len([c for c in cb.calls if c[0] == 'model_getSamplePoint']), 1)

    def test_a_count_of_0_returns_after_the_hands(self):
        m, _mem, cb = sparks(0)
        m.block_sparks(PLAYER, 1)
        self.assertFalse([c for c in cb.calls if c[0] == 'model_getSamplePoint'])
        self.assertEqual(len([c for c in cb.calls if c[0] == 'model_getAttachPoint']), 2)

    def test_the_round2_body_still_refuses_a_nonzero_silent(self):
        m, _mem, _cb = sparks(1)
        with self.assertRaises(T.Unsupported):
            m.player_block_sparks(PLAYER, 1)


if __name__ == '__main__':
    unittest.main()
