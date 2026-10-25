#!/usr/bin/env python3
"""Synthetic tests for the round-5 combat bodies.  No game files.

The fixtures are authored.  What is checked is the composed behaviour of
tools/ref_combat_round5.py.  Agreement with the original is tools/difftest_combat_round5.py.
"""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_round4 as R4                  # noqa: E402
import ref_combat_round5 as R5                  # noqa: E402
import ref_combat_runtime as T                  # noqa: E402

CREATURE, CLASSDEF, SPELL, CASTER, SKILL, MODEL = (
    0x1000, 0x2000, 0x3000, 0x3200, 0x3400, 0x3600)
OBJ = 0x4000


class TestAngles(unittest.TestCase):
    def test_hit_offset_is_the_full_register(self):
        self.assertEqual(R5.hit_effect_angle(0), 0x7FFF)
        self.assertEqual(R5.hit_effect_angle(1), 0x8000)
        self.assertEqual(R5.hit_effect_angle(0x8000), 0xFFFFFFFF)
        self.assertEqual(R5.hit_effect_angle(0x7FFF), 0xFFFE)

    def test_facing_is_the_sign_extended_halfword(self):
        self.assertEqual(R5.facing_angle(0x1234), 0x1234)
        self.assertEqual(R5.facing_angle(0xC000), 0xFFFFC000)
        self.assertEqual(R5.facing_angle(0x8000), 0xFFFF8000)

    def test_gib_heading_sign_extends_the_bias_sum(self):
        self.assertEqual(R5.gib_heading(0, 0, 16000, 0xE0C0), 0xFFFFE0C0)
        angles, seed = R5.gib_angles(0x12345678, 0x100)
        self.assertEqual(len(angles), 12)
        self.assertEqual(angles[0::2], angles[1::2])
        self.assertEqual(seed, 0xE27C553A)
        again, _seed = R5.gib_angles(0x12345678, 0x100)
        self.assertEqual(again, angles)


class TestSightContract(unittest.TestCase):
    def test_skeleton_bow_passes_one_on_the_second_call(self):
        self.assertEqual(R5.skeleton_sight_forces(0, False), (0,))
        self.assertEqual(R5.skeleton_sight_forces(4, False), (0, 1))
        self.assertEqual(R5.skeleton_sight_forces(4, True), (0,))

    def test_antqueen_passes_zero_and_can_skip_the_second(self):
        self.assertEqual(R5.antqueen_sight_forces(0, False, 0), (0, 0))
        self.assertEqual(R5.antqueen_sight_forces(0, True, 0), (0,))
        self.assertEqual(R5.antqueen_sight_forces(0, True, 4), (0, 0))
        self.assertEqual(R5.antqueen_sight_forces(1, False, 0), (0,))

    def test_soul_phase_is_the_low_nibble(self):
        self.assertTrue(R5.soul_demon_due(9, 9))
        self.assertTrue(R5.soul_demon_due(0, 0))
        self.assertTrue(R5.soul_demon_due(16, 0))
        self.assertFalse(R5.soul_demon_due(1, 0))
        self.assertFalse(R5.soul_demon_due(16, 1))
        self.assertFalse(R5.soul_demon_due(9, 0))


def _queen(count, half, clips):
    mem = RC.Memory()
    mem.poke(CREATURE + 0x24, 4, CLASSDEF)
    for off, word in zip(R5.BANK_CLIPS, (0x11, 0x22, 0x33, 0x44)):
        mem.poke(CLASSDEF + off, 4, word)
    mem.poke(CREATURE + 0x110, 2, half & 0xFFFF)
    mem.poke(CREATURE + 0x118, 1, count & 0xFF)
    for index, clip in enumerate(clips):
        mem.poke(CREATURE + 0x11C + 32 * index, 4, clip)
    return mem, R5.QueenModel(mem, {})


class TestBank(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')

    def test_zero_spring_writes_minus_zero_on_the_second_pair(self):
        mem, model = _queen(2, 0, (0x11, 0x33))
        model.update_bank(CREATURE)
        self.assertEqual(mem.load(CREATURE + 0x124, 4), 0)
        self.assertEqual(mem.load(CREATURE + 0x144, 4), 0x80000000)
        self.assertEqual(mem.load(CREATURE + 0x3E0, 4), 0)
        self.assertEqual(mem.load(CREATURE + 0x3DC, 4), 0)
        self.assertEqual(mem.load(CREATURE + 0x3E4, 2), 0)
        self.assertEqual(model.calls, [])

    def test_a_positive_rate_fills_the_first_pair_only(self):
        mem, model = _queen(2, 100, (0x11, 0x33))
        model.update_bank(CREATURE)
        self.assertNotEqual(mem.load(CREATURE + 0x124, 4), 0)
        self.assertEqual(mem.load(CREATURE + 0x144, 4), 0)

    def test_a_negative_rate_fills_the_second_pair_only(self):
        mem, model = _queen(2, -100 & 0xFFFF, (0x11, 0x33))
        model.update_bank(CREATURE)
        self.assertEqual(mem.load(CREATURE + 0x124, 4), 0)
        self.assertNotEqual(mem.load(CREATURE + 0x144, 4), 0)
        self.assertNotEqual(mem.load(CREATURE + 0x144, 4), 0x80000000)

    def test_a_non_positive_count_leaves_the_tracks(self):
        for count in (0, 0xFF):
            mem, model = _queen(count, 100, (0x11,))
            mem.poke(CREATURE + 0x124, 4, 0x111)
            model.update_bank(CREATURE)
            self.assertEqual(mem.load(CREATURE + 0x124, 4), 0x111)
            self.assertNotEqual(mem.load(CREATURE + 0x3E0, 4), 0)

    def test_fade_writes_the_rate_of_a_matching_clip(self):
        mem, model = _queen(2, 0, (0x11, 0x99))
        model.fade_bank_tracks(CREATURE)
        self.assertEqual(mem.load(CREATURE + 0x128, 4), R5.FADE_RATE)
        self.assertEqual(mem.load(CREATURE + 0x148, 4), 0)
        self.assertEqual(mem.load(CREATURE + 0x124, 4), 0)

    def test_fade_skips_a_non_positive_count(self):
        for count in (0, 0xFF):
            mem, model = _queen(count, 0, (0x11,))
            model.fade_bank_tracks(CREATURE)
            self.assertEqual(mem.load(CREATURE + 0x128, 4), 0)


class _Demon:
    def __init__(self, tokens, demons):
        self.tokens, self.demons = tokens, demons

    def get(self, name):
        def answer(*args):
            if name == 'Creature.v0':
                return self.tokens[args[0]]
            if name == 'Demon_typeinfo':
                return 0xD000
            if name == 'rtti_typeInfoEquals':
                return 1 if args[0] in self.demons and args[1] == 0xD000 else 0
            return 0
        return answer


class TestDemon(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')

    def _run(self, objects, tokens, demons, pos=(0x41000000, 0x41800000, 0x41C00000)):
        mem = RC.Memory()
        for i, word in enumerate(pos):
            mem.poke(CREATURE + 0x10 + 4 * i, 4, word)
        for obj, flags in objects:
            mem.poke(obj + 0xC, 4, flags)
        model = R5.SoulModel(mem, _Demon(tokens, demons))
        result = model.is_demon_near(CREATURE, [obj for obj, _flags in objects])
        return result, model.calls

    def test_empty_box_returns_zero(self):
        result, calls = self._run((), {}, set())
        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 1)
        _low, _high, limit = calls[0][1]
        self.assertEqual(limit, 128)

    def test_a_living_demon_returns_one_and_a_dead_one_does_not(self):
        objects = ((0x5000, 0), (0x5100, 8), (0x5200, 0))
        tokens = {0x5000: 0xA1, 0x5100: 0xA2, 0x5200: 0xA3}
        result, calls = self._run(objects, tokens, {0xA2, 0xA3})
        self.assertEqual(result, 1)
        names = [name for name, _args in calls]
        self.assertEqual(names, [
            'world_collectObjectsInBox',
            'Creature.v0', 'Demon_typeinfo', 'rtti_typeInfoEquals',
            'Creature.v0', 'Demon_typeinfo', 'rtti_typeInfoEquals',
            'Creature.v0', 'Demon_typeinfo', 'rtti_typeInfoEquals'])

    def test_the_box_is_three_hundred_on_each_axis(self):
        pos = (0x41000000, 0x41800000, 0x41C00000)
        _result, calls = self._run((), {}, set(), pos)
        low, high, limit = calls[0][1]
        self.assertEqual(limit, R5.DEMON_LIMIT)
        self.assertEqual(low, tuple(C.sub(p, R5.DEMON_REACH) for p in pos))
        self.assertEqual(high, tuple(C.add(p, R5.DEMON_REACH) for p in pos))


class _Volley:
    def __init__(self, collide):
        self.collide = collide

    def get(self, name):
        def answer(*_args):
            if name == 'obj_moveAndCollide':
                return self.collide
            return 0
        return answer


class TestVolley(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')

    def _obj(self, ended=0, age=0, seed=1):
        mem = RC.Memory()
        mem.poke(OBJ + 0x60, 4, ended)
        mem.poke(OBJ + 0x6C, 4, age)
        mem.poke(OBJ + 0x44, 4, seed)
        mem.poke(OBJ + 0x74, 4, 0xAB)
        for i, word in enumerate((0x41000000, 0x41800000, 0x41C00000)):
            mem.poke(OBJ + 0x10 + 4 * i, 4, word)
            mem.poke(OBJ + 0x54 + 4 * i, 4, 0x3F800000)
        return mem

    def test_an_ended_bolt_does_nothing(self):
        mem = self._obj(ended=1, age=5)
        model = R5.VolleyModel(mem, _Volley(0))
        model.multifire_run(OBJ)
        self.assertEqual(model.calls, [])
        self.assertEqual(mem.load(OBJ + 0x6C, 4), 5)

    def test_age_601_ends_with_reason_zero(self):
        mem = self._obj(age=600)
        model = R5.VolleyModel(mem, _Volley(0))
        model.multifire_run(OBJ)
        self.assertEqual(mem.load(OBJ + 0x6C, 4), 601)
        self.assertEqual([name for name, _a in model.calls],
                         ['trail_addPoint', 'obj_moveAndCollide', 'MultiFireProjectile_end'])
        self.assertEqual(model.calls[-1][1], (OBJ, 0))

    def test_a_terrain_bit_ends_with_reason_one(self):
        for collide in (1, 3):
            mem = self._obj(age=0, seed=collide + 9)
            model = R5.VolleyModel(mem, _Volley(collide))
            model.multifire_run(OBJ)
            names = [name for name, _a in model.calls]
            self.assertEqual(names, ['trail_addPoint', 'obj_moveAndCollide', 'MultiFireProjectile_end'])
            self.assertEqual(model.calls[-1][1], (OBJ, 1))
            self.assertNotIn('particle_spawn', names)

    def test_a_clear_flight_spawns_ten(self):
        mem = self._obj(age=0, seed=0x1234)
        model = R5.VolleyModel(mem, _Volley(2))
        model.multifire_run(OBJ)
        spawned = [args for name, args in model.calls if name == 'particle_spawn']
        self.assertEqual(len(spawned), 10)
        for args in spawned:
            self.assertEqual(args[0], R5.P_VOLLEY)
            self.assertEqual(args[3], C.ZERO)
        self.assertEqual(mem.load(OBJ + 0x6C, 4), 1)


class _Shield:
    def get(self, name):
        def answer(*_args):
            if name == 'Creature.v16':
                return MODEL
            if name == 'Skill.v10':
                return 100
            if name == 'pool_new':
                return 0
            return 0
        return answer


class TestShield(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')

    def test_a_count_of_zero_is_refused(self):
        mem = RC.Memory()
        mem.poke(SPELL + 0xC, 4, CASTER)
        mem.poke(CASTER + 0x48, 4, 0x3800)
        mem.poke(MODEL + 0x24, 1, 6)
        mem.poke(MODEL + 0x64, 4, 0)
        model = R5.ShieldPoints(mem, _Shield())
        with self.assertRaises(T.Unsupported):
            model.holy_shield_sample(SPELL)

    def test_two_hundred_forty_one_particles_and_the_skill_result(self):
        mem = RC.Memory()
        mem.poke(SPELL + 0x8, 4, SKILL)
        mem.poke(SPELL + 0xC, 4, CASTER)
        mem.poke(SPELL + 0x10, 4, 1)
        mem.poke(SPELL + 0x1C, 4, C.ONE)
        mem.poke(SPELL + 0x24, 4, 7)
        mem.poke(CASTER + 0x48, 4, 0x3800)
        mem.poke(CASTER + 0x114, 4, 0x3900)
        mem.poke(SKILL + 0x60, 4, 0x3A00)
        mem.poke(0x3900 + 8, 2, 1)
        mem.poke(0x3900 + 0x10, 2, 0x1000)
        mem.poke(0x3900 + 0x18, 2, 0x1000)
        mem.poke(0x3900 + 0x20, 2, 0x1000)
        mem.poke(MODEL + 0x24, 1, 6)
        mem.poke(MODEL + 0x64, 4, 1)
        model = R5.ShieldPoints(mem, _Shield())
        result = model.holy_shield_sample(SPELL)
        spawned = [args for name, args in model.calls if name == 'particle_spawn']
        self.assertEqual(len(spawned), 0xF1)
        self.assertEqual(spawned[0][0], R4.P_HOLY)
        self.assertEqual(result, C.mul(C.from_int(100), R4.F_HUNDREDTH))
        self.assertEqual(model.calls[0][0], 'Creature.v16')
        self.assertEqual(model.calls[2][0], 'particleGroup_begin')


if __name__ == '__main__':
    unittest.main()
