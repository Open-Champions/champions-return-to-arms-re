#!/usr/bin/env python3
"""Synthetic tests for the round-3 combat bodies.  No game files.

The fixtures are authored.  What is checked is the composed behaviour of the bodies in
tools/ref_combat_round3.py: the disease cloud's damage entry and who it skips, the
disease-effect constructor that entry leads to, GutChunk's gore bit, and the phantom's
timer.
"""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_a as SA                       # noqa: E402
import ref_combat_ranged as RR                  # noqa: E402
import ref_combat_round3 as R3                  # noqa: E402

CLOUD, VICTIM, OWNER, NODE, OTHER = 0x2000, 0x3000, 0x4000, 0x5000, 0x6000
TABLE, SPELL = 0x7000, 0x8000
MISSILE, ARROW_VT, LIGHT = 0x9000, 0x9100, 0x9300


class Callbacks:
    def __init__(self, found=(), pool=0):
        self.found, self.pool, self.calls = found, pool, []

    def get(self, name):
        def answer(*args):
            self.calls.append((name, args))
            if name == 'world_collectObjectsInBox':
                return self.found
            if name == 'pool_new':
                return self.pool
            if name == 'res_find':
                return 0xA10000
            return 0
        return answer


def model(found=(), pool=0, seed=1):
    mem = RC.Memory()
    mem.store(RC.G_RAND_SEED, 4, seed)
    mem.store(SA.G_SIM_FRAME, 4, 60)
    cb = Callbacks(found, pool)
    return R3.Model(mem, cb), mem, cb


def plant_cloud(mem, end=1000, cap=10, radius=10.0, potency=20, owner=OWNER, frame=60):
    mem.store(SA.G_SIM_FRAME, 4, frame)
    mem.store(CLOUD + 0x48, 4, TABLE)
    mem.store(TABLE + 8, 2, 0)
    mem.store(TABLE + 12, 4, 0xABC)
    mem.store(CLOUD + 0x44, 4, 0x12345678)
    mem.store(CLOUD + 0x54, 4, end)
    mem.store(CLOUD + 0x58, 4, cap)
    mem.store(CLOUD + 0x5C, 4, C.f32(radius))
    mem.store(CLOUD + 0x60, 4, potency)
    mem.store(CLOUD + 0x4C, 4, NODE if owner else 0)
    if owner:
        mem.store(NODE + 0xC, 4, owner)
        mem.store(owner + 0xC, 4, 0x20)


class Round3Tests(unittest.TestCase):
    def test_cloud_damages_with_no_attacker(self):
        m, mem, cb = model(found=(VICTIM,))
        plant_cloud(mem)
        mem.store(VICTIM + 0xC, 4, 0x20)
        m.diseasecloud_run(CLOUD)
        hits = [args for name, args in cb.calls if name == 'damage_apply']
        self.assertEqual(len(hits), 1)
        victim, attacker, attack, _a, _b, flags, desc, _tail, lo, hi = hits[0]
        self.assertEqual((victim, attacker, attack, flags), (VICTIM, 0, 100000, 0x1000040))
        self.assertEqual(desc, ('desc', (0x26, 20, 20, 0), None, None, None))
        self.assertEqual((lo, hi), (0, 0))
        self.assertEqual(len([c for c in cb.calls if c[0] == 'particle_spawn']), 3)

    def test_cloud_skips_its_owner_two_players_and_an_empty_handle(self):
        m, mem, cb = model(found=(OWNER, VICTIM))
        plant_cloud(mem)
        mem.store(OWNER + 0xC, 4, 0x40)
        mem.store(VICTIM + 0xC, 4, 0x40)
        m.diseasecloud_run(CLOUD)
        self.assertFalse([c for c in cb.calls if c[0] == 'damage_apply'])

        m, mem, cb = model(found=(VICTIM,))
        plant_cloud(mem, owner=0)
        mem.store(VICTIM + 0xC, 4, 0x20)
        m.diseasecloud_run(CLOUD)
        self.assertFalse([c for c in cb.calls if c[0] == 'damage_apply'])

    def test_cloud_grows_and_expires(self):
        m, mem, cb = model(found=())
        plant_cloud(mem, cap=48, radius=10.0)
        m.diseasecloud_run(CLOUD)
        self.assertEqual(mem.load(CLOUD + 0x5C, 4), C.f32(10.5))

        m, mem, cb = model()
        plant_cloud(mem, end=60, frame=60)
        m.diseasecloud_run(CLOUD)
        self.assertEqual(cb.calls, [('Creature.v1', (CLOUD, 3))])

    def test_disease_attach_builds_the_effect_and_still_adds_a_null_block(self):
        m, mem, cb = model(pool=SPELL)
        mem.store(VICTIM + 0x68, 4, 0)              # no resistance: five seconds
        mem.store(R3.G_SKILL_DISEASE, 4, 0x41B000)
        made = m.disease_attach(VICTIM, 0)
        self.assertEqual(made, SPELL)
        self.assertEqual(mem.load(SPELL + 0x1A4, 4), 5)
        self.assertEqual(mem.load(SPELL + 0x1A8, 4), 0)
        self.assertEqual(mem.load(SPELL + 0x1AC, 4), 0x41B000)
        self.assertEqual(cb.calls[-1], ('creature_addSpell', (VICTIM, SPELL)))

        m, mem, cb = model(pool=0)
        mem.store(VICTIM + 0x68, 4, C.f32(1.0))     # full resistance: zero seconds, no block
        m.disease_attach(VICTIM, 0, 0x111)
        self.assertEqual(cb.calls, [('pool_new', (0x1B0,)), ('creature_addSpell', (VICTIM, 0))])

    def test_gutchunk_gore_bit_and_name_selection(self):
        m, mem, cb = model()
        mem.store(R3.G_GORE, 4, 0)
        m.gutchunk_ctor(CLOUD, (C.f32(1.0), C.f32(2.0), C.f32(3.0)), 2, 0)
        self.assertEqual(mem.load(CLOUD + 0x248, 4), 1)
        self.assertEqual(mem.load(CLOUD + 0x48, 4), R3.GUT_VT)
        self.assertEqual(mem.load(CLOUD + 0x25C, 4), 2)
        self.assertEqual(mem.load(CLOUD + 0x260, 1), 0)
        name = cb.calls[0][1][4]
        self.assertEqual(name, mem.load(R3.GUT_BASE + 0x58, 4))

        m, mem, cb = model()
        mem.store(R3.G_GORE, 4, 2)
        m.gutchunk_ctor(CLOUD, (0, 0, 0), 1, 2)
        self.assertEqual(mem.load(CLOUD + 0x248, 4), 2)
        self.assertEqual(cb.calls[0][1][4], mem.load(R3.GUT_BASE + 0x60, 4))

    def test_phantom_timers_and_deletion(self):
        m, mem, cb = model()
        mem.store(OWNER + 0x10, 4, C.f32(8.0))
        mem.store(OWNER + 0x38, 2, 0x100)
        mem.store(OWNER + 0x24, 4, 0)
        mem.store(OWNER + 0x2E0, 2, 0x20)
        m.strongstance_phantom_ctor(CLOUD, OWNER, 0x550100, 4, 1)
        self.assertEqual(mem.load(CLOUD + 0x3CC, 4), R3.F_240)
        self.assertEqual(mem.load(CLOUD + 0x3D0, 4), R3.F_240)
        self.assertEqual(mem.load(CLOUD + 0x3D4, 4), 1)
        self.assertEqual(mem.load(CLOUD + 0x1C, 4), R3.F_24)
        self.assertEqual(mem.load(CLOUD + 0x48, 4), R3.PHANTOM_VT)
        self.assertEqual(cb.calls[-1][0], 'handle_link')

        m, mem, cb = model()
        m.strongstance_phantom_ctor(CLOUD, OWNER, 0x550100, 0, 0)
        self.assertEqual(mem.load(CLOUD + 0x3CC, 4), R3.F_75)

        m, mem, cb = model()
        mem.store(CLOUD + 0x3CC, 4, C.f32(1.0))
        m.strongstance_phantom_run(CLOUD)
        self.assertEqual(mem.load(CLOUD + 0x3CC, 4), C.f32(0.0))
        self.assertEqual(cb.calls[-1], ('obj_delete', (CLOUD,)))

        m, mem, cb = model()
        mem.store(CLOUD + 0x3CC, 4, C.f32(2.0))
        m.strongstance_phantom_run(CLOUD)
        self.assertEqual(mem.load(CLOUD + 0x3CC, 4), C.f32(1.0))
        self.assertFalse([c for c in cb.calls if c[0] == 'obj_delete'])


class ArrowCallbacks:
    def __init__(self, collide=0, pool=0):
        self.collide, self.pool, self.calls = collide, pool, []

    def get(self, name):
        def answer(*args):
            self.calls.append((name, args))
            if name == 'obj_moveAndCollide':
                return self.collide
            if name == 'pool_new':
                return self.pool
            if name == 'res_find':
                return 0xA10000
            return 0
        return answer


def plant_arrow(mem, end=1000, damage=40, spin=0, impact=0, owner=0, frame=60, kind=2):
    mem.store(RC.G_SIM_FRAME, 4, frame)
    mem.store(MISSILE + 0x48, 4, ARROW_VT)
    mem.store(ARROW_VT + 8, 2, 0)
    mem.store(ARROW_VT + 12, 4, 0x151454)
    mem.store(MISSILE + 0xD0, 4, kind)
    mem.store(MISSILE + 0x44, 4, 0x1234)
    mem.store(MISSILE + 0xD8, 4, damage)
    mem.store(MISSILE + 0xEC, 4, end)
    for i, word in enumerate((C.f32(1.0), C.f32(2.0), C.f32(3.0))):
        mem.store(MISSILE + 0x10 + 4 * i, 4, word)
    mem.store(MISSILE + 0x1B0, 4, C.f32(4.0))
    mem.store(MISSILE + 0xFA, 2, spin)
    mem.store(MISSILE + 0x1BC, 4, impact)
    if owner:
        mem.store(MISSILE + 0x4C, 4, NODE)
        mem.store(NODE + 0xC, 4, owner)


class ArrowTests(unittest.TestCase):
    def arrow(self, collide=0, pool=0):
        mem = RC.Memory()
        cb = ArrowCallbacks(collide, pool)
        return R3.ArrowModel(mem, cb), mem, cb

    def test_miss_follows_the_light_and_does_not_explode(self):
        m, mem, cb = self.arrow()
        plant_arrow(mem)
        m.missile_run(MISSILE)
        names = [name for name, _args in cb.calls]
        self.assertEqual(names, ['obj_moveAndCollide', 'light_relink'])
        self.assertEqual(mem.load(MISSILE + 0x1A4, 4), C.f32(1.0))
        self.assertEqual(mem.load(MISSILE + 0x1AC, 4), C.f32(3.0))
        self.assertEqual(cb.calls[-1][1], (MISSILE + 0x174,))

    def test_hit_damages_in_a_ring_and_ends_the_arrow(self):
        m, mem, cb = self.arrow(collide=1, pool=LIGHT)
        plant_arrow(mem, impact=0)
        m.missile_run(MISSILE)
        names = [name for name, _args in cb.calls]
        self.assertEqual(names, [
            'obj_moveAndCollide', 'res_find', 'sound_playOnObject', 'fx_ringBurst', 'pool_new',
            'LightEffect_ctor', 'world_damageInRadius', 'light_relink', 'Creature.v1'])
        self.assertEqual(cb.calls[1][1], (RR.S_FX_LUMP, R3.S_KIND12_IMPACT))
        ring = cb.calls[3][1]
        self.assertEqual(ring[0], (C.f32(1.0), C.f32(2.0), C.f32(3.0)))
        self.assertEqual(ring[1], R3.F_RING2)
        light = cb.calls[5][1]
        self.assertEqual(light[0], LIGHT)
        self.assertEqual(light[4:12], (R3.F_LIGHT_A, R3.F_LIGHT_B, 0, R3.F_LIGHT_C, 0, 0, 0, 0))
        self.assertEqual(light[12:], (R3.F_LIGHT_D, R3.F_LIGHT_E, C.ONE, C.ONE))
        damage = cb.calls[6][1]
        self.assertEqual(damage[0], 0)
        self.assertEqual(damage[2:6], (40, 0, 0, 0))
        self.assertEqual(damage[6:], (R3.F_24, R3.F_OUTER72))
        self.assertEqual(mem.load(MISSILE + 0xEC, 4), 0)
        self.assertEqual(cb.calls[-1][1], (MISSILE, 3))

    def test_a_failed_light_pool_still_damages_and_the_owner_is_the_attacker(self):
        m, mem, cb = self.arrow(collide=1, pool=0)
        plant_arrow(mem, owner=OWNER, impact=7)
        m.missile_run(MISSILE)
        names = [name for name, _args in cb.calls]
        self.assertNotIn('LightEffect_ctor', names)
        self.assertIn('sound_playSample', names)
        damage = [args for name, args in cb.calls if name == 'world_damageInRadius'][0]
        self.assertEqual(damage[0], OWNER)

    def test_only_a_ground_hit_plays_the_impact_sample(self):
        m, mem, cb = self.arrow(collide=3, pool=0)
        plant_arrow(mem, impact=7)
        m.missile_run(MISSILE)
        self.assertTrue([c for c in cb.calls if c[0] == 'sound_playSample'])

    def test_kind5_spawns_thirty_two_particles_and_a_different_light(self):
        C.set_fpu('ps2')
        m, mem, cb = self.arrow(collide=0)
        plant_arrow(mem, kind=5)
        m.missile_run(MISSILE)
        spawned = [args for name, args in cb.calls if name == 'particle_spawn']
        self.assertEqual(len(spawned), 32)
        self.assertEqual(spawned[0][0], R3.P_KIND5)
        self.assertEqual(spawned[0][3], 0)
        self.assertFalse([c for c in cb.calls if c[0] == 'fx_spawn'])

        m, mem, cb = self.arrow(collide=1, pool=LIGHT)
        plant_arrow(mem, kind=5)
        m.missile_run(MISSILE)
        self.assertEqual([args for name, args in cb.calls if name == 'res_find'][0],
                         (RR.S_FX_LUMP, R3.S_KIND5_IMPACT))
        self.assertEqual([args for name, args in cb.calls if name == 'fx_spawn'][0][0], 10)
        light = [args for name, args in cb.calls if name == 'LightEffect_ctor'][0]
        self.assertEqual(light[4:8], (0, R3.F_LIGHT_B, R3.F_LIGHT_A, R3.F_LIGHT_C))
        self.assertFalse([c for c in cb.calls if c[0] == 'world_damageInRadius'])

    def test_kind1_pairs_particles_and_spawns_effect_five_on_a_ground_hit(self):
        C.set_fpu('ps2')
        m, mem, cb = self.arrow(collide=1, pool=LIGHT)
        plant_arrow(mem, kind=1)
        m.missile_run(MISSILE)
        self.assertEqual([args for name, args in cb.calls if name == 'fx_spawn'][0][0], 5)
        props = [args for name, args in cb.calls if name == 'ParticleProp_ctor']
        self.assertGreaterEqual(len(props), 3)
        self.assertLessEqual(len(props), 6)
        self.assertEqual(props[0][2], 8)
        spawned = [args for name, args in cb.calls if name == 'particle_spawn']
        self.assertEqual(len(spawned), 48)
        self.assertEqual(spawned[0][0], R3.P_KIND1_A)
        self.assertEqual(spawned[1][0], R3.P_KIND1_B)
        self.assertEqual(spawned[0][2], spawned[1][2])

    def test_kind6_bursts_at_the_arrow_and_asks_a_player_owner(self):
        C.set_fpu('ps2')
        m, mem, cb = self.arrow(collide=1, pool=LIGHT)
        plant_arrow(mem, kind=6, owner=OWNER)
        mem.store(OWNER + 0xC, 4, 0x40)
        mem.store(OWNER + 0x3C8, 4, 3)
        m.missile_run(MISSILE)
        spawned = [args for name, args in cb.calls if name == 'particle_spawn']
        self.assertEqual(len(spawned), 100)
        self.assertEqual(spawned[0][0], R3.P_KIND6)
        self.assertEqual(spawned[0][1], (C.f32(1.0), C.f32(2.0), C.f32(3.0)))
        self.assertEqual([args for name, args in cb.calls if name == 'player_getPassiveLevel'], [(3, 0x1000)])
        light = [args for name, args in cb.calls if name == 'LightEffect_ctor'][0]
        self.assertEqual(light[4], 0)


if __name__ == '__main__':
    unittest.main()
