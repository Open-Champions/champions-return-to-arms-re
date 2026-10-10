#!/usr/bin/env python3
"""test_ref_skills_c.py - unit tests of tools/ref_skills_c.py that need no game files.

Everything here runs on made-up memory: a Skill object with invented statistic tables on
a table of the base class's function addresses, invented creatures, a threaded handle
pool.  The comparison with the original machine code is tools/difftest_skills_c.py; these
tests pin the model's own logic.

  python3 -m unittest tools/test_ref_skills_c.py
"""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_c as SK                       # noqa: E402


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def fl(raw):
    return struct.unpack('<f', struct.pack('<I', raw & 0xFFFFFFFF))[0]


SKILL, TABLE, SPELL_TABLE = 0x1000, 0x2000, 0x2400
PLAYER, MONSTER, CREATURE_TABLE = 0x3000, 0x3800, 0x2800
SPELL = 0x4000


class Fixture:
    """A Model on an empty memory with one made-up skill: statistic n has tier 1
    {first, base, step} and tier 2 from the lists below."""
    TIER_1 = ((1, 20, 2.5), (5, 3, 0.5), (1, 50, 1.0), (1, -40, -3.0), (1, 30, 13.0))
    TIER_2 = ((1, 10, 2.0), (-1, 0, 0.0), (3, 7, 0.25), (-1, 0, 0.0), (-1, 0, 0.0))

    def __init__(self, callbacks=None):
        self.mem = RC.Memory()
        self.model = SK.Model(self.mem, callbacks or {})
        poke = self.mem.poke
        poke(SKILL + 0x60, 4, TABLE)
        for slot, address in SK.SKILL_BASE.items():
            poke(TABLE + 8 * slot + 4, 4, address)
        for stat, (first, base, step) in enumerate(self.TIER_1):
            poke(SKILL + 0x0E + 2 * stat, 2, first & 0xFFFF)
            poke(SKILL + 0x18 + 2 * stat, 2, base & 0xFFFF)
            poke(SKILL + 0x24 + 4 * stat, 4, f32(step))
        for stat, (first, base, step) in enumerate(self.TIER_2):
            poke(SKILL + 0x38 + 2 * stat, 2, first & 0xFFFF)
            poke(SKILL + 0x42 + 2 * stat, 2, base & 0xFFFF)
            poke(SKILL + 0x4C + 4 * stat, 4, f32(step))
        for obj, flags in ((PLAYER, 0x60), (MONSTER, 0x20)):
            poke(obj + 0xC, 4, flags)
            poke(obj + 0x48, 4, CREATURE_TABLE)
        poke(PLAYER + 0x3C8, 4, 1)
        # a spell of the made-up skill on the player, level 4
        poke(SPELL, 1, 4)
        poke(SPELL + 8, 4, SKILL)
        poke(SPELL + 0xC, 4, PLAYER)
        poke(SPELL + 0x10, 4, 0x1234)
        poke(SPELL + 0x14, 4, SPELL_TABLE)

    def thread_handles(self, count=64):
        base = SK.G_HANDLE_NODES
        for index in range(count):
            self.mem.poke(base + 20 * index, 4, base + 20 * (index + 1) if index + 1 < count else 0)
        self.mem.poke(SK.G_HANDLE_FREE, 4, base)

    def free_nodes(self):
        out, node = [], self.mem.load(SK.G_HANDLE_FREE, 4)
        while node:
            out.append(node)
            node = self.mem.load(node, 4)
        return out


class Statistics(unittest.TestCase):
    def setUp(self):
        self.fx = Fixture()
        self.m = self.fx.model

    def test_level_zero_and_first_level(self):
        m = self.m
        self.assertEqual(m.skill_get_stat(SKILL, 0, 0), 0)
        self.assertEqual(m.skill_get_stat(SKILL, 1, 4), 0)         # below its first level
        self.assertEqual(m.skill_get_stat(SKILL, 1, 5), 3)
        self.assertEqual(m.skill_get_stat_tier2(SKILL, 0, 0, 10), 0)

    def test_rounding_is_half_away_from_zero(self):
        m = self.m
        self.assertEqual(m.skill_get_stat(SKILL, 0, 2), 23)        # 22.5 rounds up
        self.assertEqual(m.skill_get_stat(SKILL, 1, 6), 4)         # 3.5
        self.assertEqual(RC.s32(m.skill_get_stat(SKILL, 3, 2)), -43)

    def test_tier_two_and_the_cap(self):
        m = self.m
        self.assertEqual(m.skill_get_stat_tier2(SKILL, 0, 30, 0), 68)       # no cap
        self.assertEqual(m.skill_get_stat_tier2(SKILL, 0, 30, 10), 28)      # level clamped to 10
        self.assertEqual(m.skill_get_stat_tier2(SKILL, 1, 9, 6), 4)         # no tier 2: tier 1, clamped
        self.assertEqual(m.skill_get_stat_tier2(SKILL, 2, 2, 0), 0)         # below tier 2's first level

    def test_caster_selects_the_tier(self):
        m = self.m
        self.assertEqual(m.skill_stat_for(SKILL, 0, 30, PLAYER, 10), 93)    # tier 1, never clamped
        self.assertEqual(m.skill_stat_for(SKILL, 0, 30, MONSTER, 10), 28)
        self.assertEqual(m.skill_stat_for(SKILL, 0, 30, 0, 10), 28)         # a null caster is "not a player"

    def test_range_has_a_floor_of_one_and_draws_nothing(self):
        m = self.m
        self.assertEqual(m.skill_stat_range(SKILL, 0, 1, 0, SK.F_0_2), (16, 24))
        self.assertEqual(m.skill_stat_range(SKILL, 0, 0, 0, SK.F_0_2), (1, 1))
        self.assertEqual(m.draws, 0)

    def test_randomised_range_draws_twice_per_bound(self):
        m = self.m
        self.fx.mem.poke(SK.G_RAND_SEED, 4, 99)
        low, high = m.skill_stat_range(SKILL, 0, 1, 1, SK.F_0_2)
        self.assertEqual(m.draws, 4)
        self.assertTrue(16 <= low <= 20 <= high <= 24)

    def test_spread_for_non_players_truncates_without_a_floor(self):
        m = self.m
        self.assertEqual(m.statistic_spread(SKILL, 0, 1, PLAYER), (16, 24))
        self.assertEqual(m.statistic_spread(SKILL, 0, 1, MONSTER), (8, 11))     # tier 2: 10 -/+ 1.99..
        self.assertEqual(m.statistic_spread(SKILL, 0, 0, MONSTER), (0, 0))

    def test_mana_is_statistic_four_of_tier_one(self):
        self.assertEqual(fl(self.m.skill_mana_cost(SKILL, 3)), 56.0)


class Handles(unittest.TestCase):
    def test_link_remove_clear_keep_the_pool_whole(self):
        fx = Fixture()
        fx.thread_handles(16)
        m, load = fx.model, fx.mem.load
        head = 0x5000
        objects = [0x6000 + 0x100 * k for k in range(3)]
        nodes = [m.handle_link(head, obj, obj) for obj in objects]
        self.assertEqual([obj for _node, obj in m.handle_items(head)], objects[::-1])   # pushed at the head
        self.assertEqual(len(fx.free_nodes()), 16 - 6)             # two nodes per link
        self.assertEqual(m.handle_remove(nodes[1]), objects[1])
        self.assertEqual([obj for _node, obj in m.handle_items(head)], [objects[2], objects[0]])
        self.assertEqual(load(objects[1], 4), 0)                   # its partner left the object's own list
        self.assertEqual(fx.free_nodes()[0], nodes[1])             # the node itself is reused first
        m.handle_clear(head)
        self.assertEqual(load(head, 4), 0)
        self.assertEqual(sorted(fx.free_nodes()), sorted(SK.G_HANDLE_NODES + 20 * k for k in range(16)))

    def test_a_stack_list_is_a_call_out(self):
        fx = Fixture()
        fx.model.handle_clear('stack')
        self.assertEqual(fx.model.calls, [('handle_clear', ('stack',))])


class Generators(unittest.TestCase):
    def test_ball_points_are_inside_and_cost_three_draws_per_try(self):
        fx = Fixture()
        m = fx.model
        seed, draws = 0x1234, 0
        for _ in range(200):
            x, y, z = m.spell_ball(SPELL)
            self.assertLessEqual(fl(x) ** 2 + fl(y) ** 2 + fl(z) ** 2, 1.0 + 1e-6)
        state = fx.mem.load(SPELL + 0x10, 4)
        while seed != state:
            seed = (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
            draws += 1
        self.assertEqual(draws % 3, 0)
        self.assertGreater(draws, 600)                             # some tries were rejected
        self.assertEqual(m.draws, 0)                               # the shared seed is not touched


class HitHandlers(unittest.TestCase):
    def test_frost_armor_strikes_with_the_damage_minus_the_factor(self):
        calls = {'damage_apply': lambda *args: 1}
        fx = Fixture(calls)
        m = fx.model
        fx.mem.poke(SK.G_RAND_SEED, 4, 0)
        # statistic 1 at level 4 is 0 (first level 5): factor 1.0; statistic 2 is 53 percent
        roll = ((0 * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF) >> 16
        factor = m.frostarmor_on_hit(SPELL, MONSTER, f32(250.0))
        self.assertEqual(factor, C.ONE)
        struck = [args for name, args in m.calls if name == 'damage_apply']
        self.assertEqual(bool(struck), roll % 100 < 53)
        if struck:
            self.assertEqual(struck[0][6], SK.desc((0x16, 249, 249, 0)))      # 250 - 1.0, not 250 x 0
            self.assertEqual(struck[0][5], 0x540)
        self.assertEqual(m.draws, 1)

    def test_frost_armor_without_an_attacker_draws_nothing(self):
        fx = Fixture()
        fx.model.frostarmor_on_hit(SPELL, 0, f32(10.0))
        self.assertEqual(fx.model.draws, 0)

    def test_retribution_heals_up_to_the_maximum(self):
        fx = Fixture()
        m, mem = fx.model, fx.mem
        rec = SK.G_PLAYERS + 1 * SK.REC_SIZE
        mem.poke(rec + 0xAC, 4, f32(100.0))
        mem.poke(rec + 0xB0, 4, f32(120.0))
        mem.poke(SPELL, 1, 6)                                      # statistic 1 at level 6: 3.5 -> 4 percent
        self.assertEqual(fl(m.retribution_heal_owner(SPELL, f32(200.0))), fl(C.mul(f32(4.0), SK.F_0_01)))
        self.assertAlmostEqual(fl(mem.load(rec + 0xAC, 4)), 108.0, places=3)
        m.retribution_heal_owner(SPELL, f32(5000.0))
        self.assertEqual(mem.load(rec + 0xAC, 4), f32(120.0))
        mem.poke(rec + 0xAC, 4, 0)                                 # no hit points: nothing, and 0.0 back
        self.assertEqual(m.retribution_heal_owner(SPELL, f32(50.0)), 0)

    def test_spirit_shield_draws_only_inside_its_duration(self):
        fx = Fixture()
        m, mem = fx.model, fx.mem
        mem.poke(SPELL + 0x1C, 4, f32(500.0))                      # clock far past statistic 0
        self.assertEqual(m.spiritshield_roll_absorb(SPELL), 0)
        self.assertEqual(m.draws, 0)
        mem.poke(SPELL + 0x1C, 4, f32(1.0))
        m.spiritshield_roll_absorb(SPELL)
        self.assertEqual(m.draws, 1)


class DiseaseBlade(unittest.TestCase):
    ITEM = 0x7000

    def item(self, fx, slots):
        for k in range(4):
            ident, values = slots[k] if k < len(slots) else (0xFFFF, (0, 0, 0))
            fx.mem.poke(self.ITEM + 0x24 + 8 * k, 2, ident)
            for j, value in enumerate(values):
                fx.mem.poke(self.ITEM + 0x26 + 8 * k + 2 * j, 2, value)

    def slot(self, fx, k):
        return tuple(fx.mem.load(self.ITEM + 0x24 + 8 * k + 2 * j, 2) for j in range(4))

    def test_a_fresh_weapon_takes_the_modifier(self):
        fx = Fixture()
        self.item(fx, [(0x15, (5, 6, 600))])
        fx.model.write_disease(self.ITEM, 21, 900, 900)
        self.assertEqual(self.slot(fx, 1), (0x26, 21, 25, 900))    # round(21 + 21 x 0.19999999) = 25

    def test_the_limit_is_compared_with_the_old_value(self):
        fx = Fixture()
        self.item(fx, [(0x26, (31, 37, 1))])                      # one frame left, value 31
        fx.model.write_disease(self.ITEM, 34, 31, 31)              # the aura: limit 31
        self.assertEqual(self.slot(fx, 0), (0x26, 31, 37, 1))      # refused: 31 is not below 31
        self.item(fx, [(0x26, (30, 36, 1))])
        fx.model.write_disease(self.ITEM, 34, 31, 31)
        self.assertEqual(self.slot(fx, 0), (0x26, 34, 41, 31))

    def test_a_weaker_value_and_a_thrown_weapon_are_left_alone(self):
        fx = Fixture()
        self.item(fx, [(0x26, (40, 48, 500))])
        fx.model.write_disease(self.ITEM, 21, 900, 900)
        self.assertEqual(self.slot(fx, 0), (0x26, 40, 48, 500))
        self.item(fx, [])
        fx.mem.poke(self.ITEM + 8, 8, 0x1000000)
        fx.model.write_disease(self.ITEM, 21, 900, 900)
        self.assertEqual(self.slot(fx, 0)[0], 0xFFFF)


class Passives(unittest.TestCase):
    def test_berserker_rage_needs_half_health_and_ramps_over_a_second(self):
        fx = Fixture()
        m, mem = fx.model, fx.mem
        rec = 0x9000
        mem.poke(rec + 0xAC, 4, f32(61.0))
        mem.poke(rec + 0xB0, 4, f32(120.0))
        self.assertEqual(m.berserkerrage_damage_factor(SKILL, 6, rec, 30), C.ONE)
        mem.poke(rec + 0xAC, 4, f32(60.0))
        half = m.berserkerrage_damage_factor(SKILL, 6, rec, 30)    # statistic 1 at rank 6: 3.5 -> 4 percent
        full = m.berserkerrage_damage_factor(SKILL, 6, rec, 600)
        self.assertAlmostEqual(fl(full), 1.04, places=5)
        self.assertAlmostEqual(fl(half), 1.02, places=5)           # half a second into the chain
        self.assertEqual(m.berserkerrage_damage_factor(SKILL, 3, rec, 600), C.ONE)     # below its first level: 0
        swing = m.berserkerrage_swing_factor(SKILL, 3, rec, 600)   # statistic 0 at rank 3: 25
        self.assertAlmostEqual(fl(swing), 1.25, places=5)

    def test_fractions_are_zero_at_rank_zero(self):
        m = Fixture().model
        self.assertEqual(m.battlemage_fraction(SKILL, 0), 0)
        self.assertEqual(m.throwing_fraction(SKILL, 0), 0)
        self.assertEqual(m.dodge_fraction(SKILL, 0), 0)
        self.assertEqual(m.passive_complement(SKILL, 0), C.ONE)
        self.assertAlmostEqual(fl(m.battlemage_fraction(SKILL, 1)), 0.2, places=6)


class ConeOfShock(unittest.TestCase):
    def test_the_range_draw_follows_the_decoration_draw(self):
        enemy = 0xA000
        calls = {'world_collectObjectsInArc': lambda *args: [enemy], 'Creature.v20': lambda *args: 1,
                 'damage_apply': lambda *args: 1}
        fx = Fixture(calls)
        m, mem = fx.model, fx.mem
        mem.poke(SK.G_SIM_FRAME, 4, 30)                            # a decoration frame (period 15 at level 4) and a damage frame
        m.coneofshock_spell_run(SPELL, (f32(0.0), f32(0.0), f32(0.0)), 0)
        first = (0x1234 * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
        second = (first * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
        self.assertEqual(mem.load(SPELL + 0x10, 4), second)        # two own draws
        quarter = int(27.5 * 0.25)                                 # statistic 0 at level 4: 27.5 -> 28 -> 7
        quarter = int(28 * 0.25)
        top = quarter + int(quarter * ((second >> 16) / 65536.0) * 0.19999999)
        hit = [args for name, args in m.calls if name == 'damage_apply'][0]
        self.assertEqual(hit[6], SK.desc((0x18, quarter, top, 0)))
        self.assertEqual((hit[8], hit[9]), (0, 0))                 # the base range is 0..0
        self.assertEqual(m.draws, 0)

    def test_no_damage_between_the_fifteenth_frames(self):
        fx = Fixture({'world_collectObjectsInArc': lambda *args: [0xA000]})
        fx.mem.poke(SK.G_SIM_FRAME, 4, 31)
        fx.model.coneofshock_spell_run(SPELL, (0, 0, 0), 0)
        self.assertFalse([name for name, _args in fx.model.calls if name == 'world_collectObjectsInArc'])


class Tables(unittest.TestCase):
    def test_every_body_has_a_method_and_an_address(self):
        for table in (SK.SKILL_BODIES, SK.SPELL_BODIES):
            for address, (slot, method) in table.items():
                self.assertTrue(hasattr(SK.Model, method), method)
                self.assertIn(address, SK.MODELLED.values(), hex(address))
        self.assertEqual(len(set(SK.MODELLED.values())), len(SK.MODELLED))

    def test_externals_are_addressed_once(self):
        seen = {}
        for name, ext in SK.EXTERNALS.items():
            if ext.addr:
                self.assertEqual(seen.setdefault(ext.addr, name), name)


if __name__ == '__main__':
    unittest.main()
