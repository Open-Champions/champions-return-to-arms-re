#!/usr/bin/env python3
"""Synthetic tests for the round-6 combat handlers.  No game files.

The fixtures are authored.  What is checked is the branch structure of
tools/ref_combat_round6.py: who is damaged, who is skipped, and which calls that
choice makes.  The byte-for-byte comparison with the original is
tools/difftest_combat_round6.py.
"""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_a as SA                       # noqa: E402
import ref_combat_round6 as R6                  # noqa: E402

OBJ, OWNER, NODE, SKILL, OTHER = 0x2000, 0x3000, 0x4000, 0x5000, 0x6000
VT, OVT, SVT, BLOCK, VICTIM = 0x7000, 0x7100, 0x7200, 0x8000, 0x9000
FN_DTOR, FN_ENEMY, FN_STAT10, FN_STAT13 = 0x3E0100, 0x3E0120, 0x3E0140, 0x3E0160


class Callbacks:
    def __init__(self, found=(), enemies=(), block=BLOCK, stat0=10, stat2=4, near=1):
        self.found, self.enemies, self.block = found, set(enemies), block
        self.stat0, self.stat2, self.near = stat0, stat2, near

    def get(self, name):
        def answer(*args):
            if name == 'world_collectObjectsInBox':
                return self.found
            if name == 'pool_new':
                return self.block
            if name == 'Skill.v13':
                return self.stat0
            if name == 'Skill.v10':
                return self.stat2
            if name == 'Creature.v20':
                return 1 if args[1] in self.enemies else 0
            if name == 'isNearView':
                return self.near
            if name == 'libc_sprintf':
                return ('buf', b'name')
            if name == 'res_find':
                return 0xA10000
            return 0
        return answer


def memory():
    mem = RC.Memory()
    mem.poke(VT + 8, 2, 0)
    mem.poke(VT + 12, 4, FN_DTOR)
    mem.poke(OVT + 0xA0, 2, 0)
    mem.poke(OVT + 0xA4, 4, FN_ENEMY)
    mem.poke(SVT + 0x50, 2, 0)
    mem.poke(SVT + 0x54, 4, FN_STAT10)
    mem.poke(SVT + 0x68, 2, 0)
    mem.poke(SVT + 0x6C, 4, FN_STAT13)
    mem.poke(SKILL + 0x60, 4, SVT)
    mem.poke(NODE + 0xC, 4, OWNER)
    mem.poke(OWNER + 0x48, 4, OVT)
    return mem


def plant(mem, addr, flags=0):
    mem.poke(addr + 0xC, 4, flags)
    mem.poke(addr + 0x48, 4, VT)


def names(model):
    return [call[0] for call in model.calls]


class Round6Test(unittest.TestCase):
    def setUp(self):
        C.set_fpu('ps2')

    def test_gas_expires_without_a_tick(self):
        mem = memory()
        plant(mem, OBJ)
        mem.poke(OBJ + 0x5C, 4, 10)
        mem.poke(SA.G_SIM_FRAME, 4, 10)
        model = R6.Model(mem, Callbacks())
        model.poison_gas_run(OBJ)
        self.assertEqual(names(model), ['Creature.v1'])
        self.assertEqual(model.calls[0][1], (OBJ, 3))

    def test_gas_damages_only_the_owner_enemy(self):
        mem = memory()
        plant(mem, OBJ)
        plant(mem, OWNER)
        mem.poke(OBJ + 0x4C, 4, NODE)
        mem.poke(OBJ + 0x5C, 4, 90)
        mem.poke(OBJ + 0x60, 4, 0)
        mem.poke(OBJ + 0x64, 4, C.from_int(4))
        mem.poke(OBJ + 0x6C, 4, 0x10005)
        mem.poke(SA.G_SIM_FRAME, 4, 30)
        friend, foe = VICTIM, VICTIM + 0x40
        model = R6.Model(mem, Callbacks(found=(friend, foe), enemies=(foe,)))
        model.poison_gas_run(OBJ)
        self.assertEqual(names(model), ['world_collectObjectsInBox', 'Creature.v20', 'Creature.v20',
                                        'damage_apply'])
        damage = model.calls[-1][1]
        self.assertEqual(damage[0], foe)
        self.assertEqual(damage[1], OWNER)
        self.assertEqual(damage[5], R6.GAS_FLAGS)
        self.assertEqual(damage[6], SA.descriptor((0x17, 5, 5, 0)))
        self.assertEqual(damage[-2:], (C.ZERO, C.ZERO))

    def test_corpse_stops_after_half_the_word(self):
        mem = memory()
        plant(mem, OBJ)
        mem.poke(OBJ + 0x4C, 4, NODE)
        mem.poke(OBJ + 0x50, 4, 2)
        mem.poke(OBJ + 0x54, 4, 16)
        first, second = VICTIM, VICTIM + 0x40
        plant(mem, first, 0x28)
        plant(mem, second, 0x28)
        mem.poke(first + 0x10, 4, 0x3F800000)
        model = R6.Model(mem, Callbacks(found=(first, second)))
        model.disease_corpse_run(OBJ)
        self.assertEqual(names(model), ['world_collectObjectsInBox', 'pool_new', 'DiseaseCloud_ctor',
                                        'Creature.v1'])
        ctor = model.calls[2][1]
        self.assertEqual(ctor[0], BLOCK)
        self.assertEqual(ctor[1][0], 0x3F800000)
        self.assertEqual(ctor[2], 2)
        self.assertEqual(ctor[3], OWNER)

    def test_corpse_counts_a_failed_pool(self):
        mem = memory()
        plant(mem, OBJ)
        mem.poke(OBJ + 0x4C, 4, NODE)
        mem.poke(OBJ + 0x50, 4, 4)
        plant(mem, VICTIM, 0x28)
        model = R6.Model(mem, Callbacks(found=(VICTIM,), block=0))
        model.disease_corpse_run(OBJ)
        self.assertEqual(names(model), ['world_collectObjectsInBox', 'pool_new', 'Creature.v1'])

    def test_hit_ignores_a_player_marked_target(self):
        mem = memory()
        plant(mem, OBJ)
        plant(mem, OWNER, 0x40)
        mem.poke(OBJ + 0x4C, 4, NODE)
        mem.poke(OTHER + 0xC, 4, 0x40)
        model = R6.Model(mem, Callbacks())
        model.multifire_on_hit(OBJ, OTHER)
        self.assertEqual(model.calls, [])

    def test_hit_still_damages_when_the_bolt_already_ended(self):
        mem = memory()
        plant(mem, OBJ)
        plant(mem, OWNER)
        mem.poke(OBJ + 0x4C, 4, NODE)
        mem.poke(OBJ + 0x60, 4, 1)
        mem.poke(OBJ + 0x70, 4, SKILL)
        mem.poke(OBJ + 0x68, 4, 1)
        mem.poke(OBJ + 0x44, 4, 1)
        model = R6.Model(mem, Callbacks(enemies=(OTHER,), stat0=8))
        model.multifire_on_hit(OBJ, OTHER)
        self.assertEqual(names(model), ['Creature.v20', 'Skill.v13', 'damage_apply'])
        self.assertEqual(model.calls[-1][1][5], R6.HIT_FLAGS)
        self.assertEqual(mem.load(OBJ + 0x60, 4), 1)

    def test_end_reason_zero_skips_the_impact(self):
        mem = memory()
        plant(mem, OBJ)
        mem.poke(OBJ + 0x74, 4, 0x1110)
        model = R6.Model(mem, Callbacks())
        model.multifire_end(OBJ, 0)
        self.assertEqual(names(model), ['trail_release', 'obj_delete'])
        self.assertEqual(mem.load(OBJ + 0x60, 4), 1)

    def test_end_ice_flag_picks_the_ice_format(self):
        mem = memory()
        plant(mem, OBJ)
        mem.poke(OBJ + 0x44, 4, 1)
        mem.poke(RC.G_LEVEL_FLAGS, 4, R6.LEVEL_ICE)
        model = R6.Model(mem, Callbacks())
        model.multifire_end(OBJ, 2)
        self.assertEqual(model.calls[1][0], 'libc_sprintf')
        self.assertEqual(model.calls[1][1][0], R6.FMT_ICE)
        self.assertEqual(model.calls[2][1][0], 8)

    def test_pustule_at_the_launch_limit_destroys_itself(self):
        mem = memory()
        plant(mem, OBJ)
        mem.poke(OBJ + 0x64, 4, 301)
        model = R6.Model(mem, Callbacks())
        model.pustule_run(OBJ)
        self.assertEqual(names(model), ['Creature.v1'])

    def test_smoke_far_from_the_view_does_not_step(self):
        mem = memory()
        model = R6.Model(mem, Callbacks(near=0))
        model.smoke_gen_run(OBJ)
        self.assertEqual(names(model), ['isNearView'])
        self.assertEqual(model.calls[0][1], ((OBJ + 0x10) & 0xFFFFFFFF, R6.F_1000))

    def test_smoke_damages_creatures_other_than_itself(self):
        mem = memory()
        mem.poke(SA.G_SIM_FRAME, 4, 8)
        mem.poke(OBJ + 0x478, 4, C.from_int(4))
        mem.poke(OBJ + 0x48C, 4, 5)
        plain, marked, creature = VICTIM, VICTIM + 0x40, VICTIM + 0x80
        plant(mem, plain, 0)
        plant(mem, marked, 0x21)
        plant(mem, creature, 0x20)
        model = R6.Model(mem, Callbacks(found=(OBJ, plain, marked, creature)))
        model.smoke_gen_run(OBJ)
        self.assertEqual(names(model), ['isNearView', 'SmokeGen_stepParticles',
                                        'world_collectObjectsInBox', 'damage_apply'])
        damage = model.calls[-1][1]
        self.assertEqual(damage[0], creature)
        self.assertEqual(damage[1], OBJ)
        self.assertEqual(damage[5], R6.SMOKE_FLAGS)
        self.assertEqual(damage[6], SA.descriptor((0x26, 1, 1, 0)))
        self.assertEqual(damage[-2:], (C.from_int(5), C.from_int(5)))

    def test_arena_below_thirty_clears_the_mark(self):
        mem = memory()
        plant(mem, OWNER, 2)
        mem.poke(OBJ + 0xC, 4, OWNER)
        mem.poke(R6.G_ARENA_COUNTER, 2, 0)
        model = R6.Model(mem, Callbacks())
        model.arena_run(OBJ, (C.ZERO, C.ZERO, C.ZERO))
        self.assertEqual(names(model), [])
        self.assertEqual(mem.load(OWNER + 0xC, 4), 0)

    def test_horn_at_its_end_destroys_the_spell(self):
        mem = memory()
        mem.poke(SA.G_SIM_FRAME, 4, 10)
        mem.poke(OBJ + 0x18, 4, 10)
        mem.poke(OBJ + 0x14, 4, VT)
        model = R6.Model(mem, Callbacks())
        model.hornomen_run(OBJ, (C.ZERO, C.ZERO, C.ZERO))
        self.assertEqual(names(model), ['Spell.v1'])
        self.assertEqual(model.calls[0][1], (OBJ, 3))

    def test_horn_ctor_ends_six_hundred_frames_later(self):
        mem = memory()
        mem.poke(SA.G_SIM_FRAME, 4, 12)
        mem.poke(RC.G_RAND_SEED, 4, 1)
        model = R6.Model(mem, Callbacks())
        model.hornomen_ctor(OBJ, 1, OWNER, 9)
        self.assertEqual(names(model), ['particleGroup_create'])
        self.assertEqual(mem.load(OBJ + 0x18, 4), 612)
        self.assertEqual(mem.load(OBJ + 0x14, 4), R6.HO_VT)
        self.assertEqual(mem.load(OBJ + 0xC, 4), OWNER)


if __name__ == '__main__':
    unittest.main()
