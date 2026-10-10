#!/usr/bin/env python3
"""Unit tests for tools/ref_combat.py that need no game file (they run in CI).

They check the model's own logic on made-up tables and records.  Whether the model matches
the game is the business of tools/difftest_combat.py, which needs the executable.  The few
bit patterns asserted here are results that the differential test saw the original code
produce (they are arithmetic facts about the C library and the FPU model, not game data).
"""
import math
import os
import random
import sys
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_combat as R                          # noqa: E402

F, T = R.f32, R.to_float


def tables():
    t = R.Tables()
    t.exp_table = [0] + [1000 * level * level for level in range(1, 80)] + [99999999]
    t.class_formulas = [(F(13.0), F(1.5), F(6.0), F(14.5), F(2.5), F(65.0))] * 7
    t.passive_masks = [[0x40, 0x40000] + [0] * 46 for _ in range(7)]
    t.figurine_stats = ('str', 'int', 'dex', 'sta')
    t.figurine_tiers = ('tiny', 'small', 'large', 'huge')
    t.boss_names = ('bigboss',)
    t.boss_gate = 'gate'
    t.boss_pairs = (('twin', 'left'),)
    t.boss_last = ('last1', 'last2')
    t.no_scale_name = 'exempt'
    t.fixed_levels = ('fixed1', 'fixed2')
    return t


class Arithmetic(unittest.TestCase):
    def setUp(self):
        R.set_fpu()

    def test_fpu_truncates_and_saturates(self):
        self.assertEqual(R.fdiv(R.ONE, R.THREE), 0x3EAAAAAA)
        self.assertEqual(R.fdiv(R.ONE, R.ZERO), 0x7FFFFFFF)
        self.assertEqual(R.fdiv(R.ZERO, R.ZERO), 0x7FFFFFFF)
        self.assertEqual(R.ftoi(0x7FFFFFFF), 0x7FFFFFFF)
        self.assertEqual(R.ftoi(F(-2.9)), -2)
        self.assertEqual(R.fsqrt(F(-4.0)), F(2.0))
        self.assertEqual(R.fmin(F(0.5), R.ONE), F(0.5))
        self.assertEqual(R.round_half_away(F(-2.5)), -3)

    def test_soft_double_is_not_ieee(self):
        self.assertEqual(R.dbl_to_single(Fraction(1, 10)), 0x3DCCCCCC)         # truncated, not 0x3dcccccd
        self.assertEqual(R.dbl_to_single(Fraction(2) ** 129), 0x7F800000)
        self.assertEqual(R.dbl_to_single(-Fraction(2) ** 140), 0xFF800000)
        self.assertEqual(R.dbl_to_single(Fraction(1, 2 ** 127)), 0)
        self.assertEqual(R.dbl_from_single(0x7FFFFFFF), Fraction(0xFFFFFF) * Fraction(2) ** 105)
        self.assertEqual(R.dbl_from_single(0x007FFFFF), 0)
        self.assertEqual(R.dbl_add(Fraction(1), Fraction(3, 2 ** 53)), 1 + Fraction(1, 2 ** 52))
        self.assertIs(R.dbl_fmod(Fraction(5), Fraction(0)), R.NAN)
        self.assertEqual(R.dbl_fmod(Fraction(5), Fraction(-3)), 2)

    def test_powf_shortcuts_and_known_patterns(self):
        x = F(37.25)
        self.assertEqual(R.powf(x, R.ONE), x)
        self.assertEqual(R.powf(x, R.TWO), R.fmul(x, x))
        self.assertEqual(R.powf(x, R.ZERO), R.ONE)
        self.assertEqual(R.powf(F(4.0), R.HALF), F(2.0))
        self.assertEqual(R.powf(F(2.0), F(0.85)), 0x3FE6B85A)
        self.assertEqual(R.powf(F(1234.5), 0x3FB33333), 0x46A64B59)

    def test_powf_is_close_to_the_real_power(self):
        rng = random.Random(5)
        for _ in range(300):
            x, y = rng.uniform(0.01, 5000), rng.choice((0.85, 1.322, 1.4, rng.uniform(-3, 3)))
            want = math.pow(T(F(x)), T(F(y)))
            self.assertLess(abs(T(R.powf(F(x), F(y))) - want), 2e-5 * max(want, 1e-30))

    def test_generator(self):
        seed = R.Seed(0)
        state, want = 0, []
        for _ in range(3):
            state = (state * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
            want.append(state >> 16)
        self.assertEqual([seed.draw() for _ in range(3)], want)
        self.assertEqual(want[0], 0x3C6E)
        self.assertEqual((seed.state, seed.draws), (state, want))

    def test_adder_models_are_selectable(self):
        a, b = F(1.0), F(-3e-8)
        R.set_fpu('chop')
        chop = R.fadd(a, b)
        R.set_fpu('ps2')
        self.assertEqual(R.fadd(a, b), a)
        self.assertEqual(chop, 0x3F7FFFFF)


class Damage(unittest.TestCase):
    def setUp(self):
        R.set_fpu()

    def world(self, seed=0x1234):
        w = R.World(seed=seed)
        w.players = [R.PlayerRec() for _ in range(4)]
        return w

    def test_base_roll(self):
        self.assertEqual(R.base_roll(F(20.5), F(30.25), 40000), F(30.5))       # 40000 mod 10.75 = 10
        self.assertEqual(R.base_roll(F(5.0), F(5.0), 12345), F(5.0))
        self.assertEqual(R.base_roll(F(0.7), F(5.7), 3), 0x406CCCCC)           # truncated
        self.assertEqual(R.base_roll(F(5.0), F(4.0), 7), 0x7F800000)           # span of zero

    def test_range_with_upper_end_below_lower(self):
        w = R.World(seed=1)
        values = {R.ftoi(R._proc_amount(w, 10, 5)) for _ in range(200)}
        self.assertEqual(values, {10, 11, 12, 13})
        w = R.World(seed=1)
        draw_then = R.ftoi(R._proc_amount(w, 10, 9))
        self.assertEqual(draw_then, 10 + w.seed.draws[0])                      # zero divisor: reported behaviour

    def test_prediction_copy_attacker_does_nothing(self):
        w = self.world()
        ret = R.damage_apply(w, R.Obj(flags=0x20), R.Obj(flags=0x20020), F(1.0), F(2.0), 100000, 0)
        self.assertEqual((ret, w.seed.draws, w.events), (0, [], []))

    def test_non_creature_takes_one_draw(self):
        w = self.world()
        ret = R.damage_apply(w, R.Obj(tag='box'), None, F(10.0), F(19.0), 0, 0x10)
        self.assertEqual((ret, len(w.seed.draws)), (1, 1))
        (event,) = w.events
        self.assertEqual(event[:2] + event[3:], ('take_damage', 'box', None, 0x10))
        self.assertEqual(T(event[2]), 10.0 + w.seed.draws[0] % 10)

    def test_plain_hit_between_monsters(self):
        w = self.world()
        victim, attacker = R.Obj(tag='v', flags=0x20, armor=100), R.Obj(tag='a', flags=0x20)
        ret = R.damage_apply(w, victim, attacker, F(10.0), F(19.0), 100000, 1)
        self.assertEqual(ret, 1)
        self.assertEqual(len(w.seed.draws), 7)      # roll, first hit, four chance rolls, second hit
        kinds = [e[0] for e in w.events]
        self.assertEqual(kinds, ['hit_sound', 'take_damage'])                  # no number: neither is a player
        self.assertEqual(w.events[1][4], 1 | 0x1000000)

    def test_zero_attack_misses(self):
        w = self.world()
        victim = R.Obj(tag='v', flags=0x20, armor=50)
        ret = R.damage_apply(w, victim, R.Obj(tag='a', flags=0x20), F(10.0), F(10.0), 0, 0x8000)
        self.assertEqual(ret, 0)
        self.assertEqual(w.events, [('take_damage', 'v', R.ZERO, 'a', 0x42000)])
        self.assertEqual(len(w.seed.draws), 2)

    def test_player_mitigation_and_number(self):
        w = self.world()
        hero = R.Obj(tag='hero', flags=0x60, slot=0, armor=150)
        w.players[0].obj = hero
        R.damage_apply(w, hero, R.Obj(tag='a', flags=0x20), F(20.0), F(20.0), 100000, 0)
        amount = [e for e in w.events if e[0] == 'take_damage'][0][2]
        self.assertEqual(amount, R.fsub(F(20.0), R.fmul(R.itof(150), R.K_1_30)))
        self.assertFalse([e for e in w.events if e[0] == 'text'])              # no number over a player

    def test_certain_critical_triples_and_skips_second_roll(self):
        w = self.world()
        victim = R.Obj(tag='v', flags=0x20)
        desc = [(0x1D, 200, 0, 0)] + [(-1, 0, 0, 0)] * 3
        R.damage_apply(w, victim, R.Obj(tag='a', flags=0x20), F(7.0), F(7.0), 100000, 0, desc)
        self.assertEqual(len(w.seed.draws), 6)      # first hit, critical, four chance rolls; no second roll
        self.assertEqual([e for e in w.events if e[0] == 'take_damage'][0][2], F(21.0))

    def test_damage_over_time_collects(self):
        w = self.world()
        w.frame = 33
        victim = R.Obj(tag='v', flags=0x20, dot=F(2.0))
        R.damage_apply(w, victim, None, F(3.0), F(3.0), 100000, 0x800000)
        self.assertEqual(victim.dot, F(5.0))
        self.assertEqual([e[2] for e in w.events if e[0] == 'take_damage'], [R.ZERO])
        w.frame = 64
        R.damage_apply(w, victim, None, F(3.0), F(3.0), 100000, 0x800000)
        self.assertEqual(victim.dot, R.ZERO)
        self.assertEqual([e[2] for e in w.events if e[0] == 'take_damage'][1:], [F(8.0), R.ZERO])

    def test_colour_class(self):
        victim = R.Obj(res=[R.ZERO, F(0.3), R.ZERO, R.ZERO, R.ZERO])
        self.assertEqual(R.colour_class(victim, 1), 1)                          # any resistance colours it
        victim.cflags = 0x100
        self.assertEqual(R.colour_class(victim, 0), 2)
        self.assertEqual(R.colour_class(R.Obj(), 0xD), 0)


class Statistics(unittest.TestCase):
    def setUp(self):
        R.set_fpu()
        self.t = tables()

    def test_boss_rank(self):
        t = self.t
        self.assertEqual(R.boss_rank(t, True, 'BigBoss', '', 0), 2)
        self.assertEqual(R.boss_rank(t, True, 'twin', 'LEFT', 0), 2)
        self.assertEqual(R.boss_rank(t, True, 'twin', 'right', 1), 1)
        self.assertEqual(R.boss_rank(t, True, None, '', 3), 1)
        self.assertEqual(R.boss_rank(t, False, 'bigboss', '', 1), 0)

    def test_monster_stats(self):
        w = R.World()
        w.monster_level, w.num_players = F(12.0), 1
        out = R.monster_stats(self.t, w, (R.ONE,) * 5, 0, 'rat', True, own_draw=3)
        self.assertEqual((out['armor'], out['dmg_low'], out['dmg_high'], out['attack']), (168, 18, 36, 168))
        self.assertEqual(T(out['exp_value']), 213.0)
        self.assertAlmostEqual(T(out['hp']), 18.5 * 12 ** 0.85, places=3)
        self.assertEqual(out['hp'], out['max_hp'])
        w.num_players = 3
        more = R.monster_stats(self.t, w, (R.ONE,) * 5, 0, 'exempt', True, own_draw=3)
        self.assertEqual(more['dmg_low'], 18)                                   # the exempt name is not scaled
        self.assertGreater(T(more['hp']), T(out['hp']))
        scaled = R.monster_stats(self.t, w, (R.ONE,) * 5, 0, 'rat', False, dead=True)
        self.assertEqual((scaled['dmg_low'], scaled['hp'], scaled['max_hp']), (24, R.ZERO, None))

    def make_world(self, levels, alive=(True, True)):
        w = R.World()
        w.num_players = len(levels)
        w.players = []
        for slot, level in enumerate(levels):
            obj = R.Obj(tag='p%d' % slot, flags=0x60, slot=slot)
            w.players.append(R.PlayerRec(obj=obj, cls=1, level59=level, level58=level, base=[20, 20, 20, 20],
                                         exp=self.t.exp_table[level - 1],
                                         hp=F(50.0) if alive[slot] else R.ZERO, max_hp=F(50.0)))
        return w

    def test_kill_experience_split(self):
        w = self.make_world((10, 10), alive=(True, False))
        monster = R.Obj(tag='m', exp_value=F(4000.0), max_hp=F(300.0))
        raw = R.ftoi(R.powf(R.fdiv(F(4000.0), R.itof(20)), 0x3FB33333))
        xp = int(raw * 0.75)
        awards = R.kill_experience(self.t, w, monster, 0)
        self.assertEqual(awards, [(0, R.ftoi(R.fmul(R.itof(xp), 0x3F199999))),
                                  (1, R.ftoi(R.fmul(R.itof(xp), 0x3ECCCCCC)) // 2)])
        w = self.make_world((10, 10))
        self.assertEqual({a for _s, a in R.kill_experience(self.t, w, monster, -1)}, {xp // 2})

    def test_kill_experience_is_capped_by_the_level_width(self):
        w = self.make_world((2,))
        monster = R.Obj(tag='m', exp_value=F(4000000.0), max_hp=F(300.0))
        (award,) = R.kill_experience(self.t, w, monster, -1)
        self.assertEqual(award, (0, self.t.exp_table[3] - self.t.exp_table[2]))

    def test_give_exp_levels(self):
        w = self.make_world((5,))
        rec = w.players[0]
        rec.exp = self.t.exp_table[5] - 1
        gained = R.give_exp(self.t, w, 0, 1)
        self.assertEqual((gained, rec.level59, rec.skill_points, rec.stat_points), (1, 6, 1, 3))
        self.assertEqual(rec.hp, rec.max_hp)
        R.give_exp(self.t, w, 0, 10 ** 9)
        self.assertEqual((rec.level59, rec.exp), (80, self.t.exp_table[80] - 1))

    def test_recalc_stats_and_the_overwritten_modifiers(self):
        w = self.make_world((10,))
        rec = w.players[0]
        rec.base = [30, 12, 21, 30]
        R.recalc_stats(self.t, w)
        bare = (rec.max_hp, rec.max_mana, rec.obj.armor)
        self.assertEqual(T(rec.max_hp), 10 * 14.5 + 30 * 2.5 - 65.0)
        self.assertEqual(rec.obj.armor, 10)                                     # dexterity / 2
        rec.equip[0] = R.Item(defn=R.ItemDef(armor=40, category=1),
                              mods=[(0x0D, 25, 0, 0), (5, 50, 0, 0), (6, 50, 0, 0), (0, 15, 0, 0)])
        rec.bag2 = [R.Item(defn=R.ItemDef(name='idol_sta_small', flags=1 << 45), count=2)]
        R.recalc_stats(self.t, w)
        self.assertEqual(rec.obj.armor, 10 + 40 + 9)                            # 25 % of 40 is 9.99..., truncated
        self.assertEqual(rec.eff[3], 30 + 2 * 10)
        self.assertEqual(T(rec.max_hp), T(bare[0]) + 20 * 2.5)                  # figurines count, modifier 5 does not
        self.assertEqual(rec.max_mana, bare[1])                                 # modifier 6 does not either
        self.assertAlmostEqual(T(rec.obj.res[0]), 0.15, places=6)

    def test_recalc_damage(self):
        w = self.make_world((10,))
        w.alive = [0]
        rec, obj = w.players[0], w.players[0].obj
        rec.eff = [40, 12, 0, 30]
        self.assertEqual(R.recalc_damage(self.t, w, obj, None, 1), (210, 11, 12))
        sword = R.Item(defn=R.ItemDef(dmg_min=10, dmg_max=20, attack=30, dmg_type=1), mods=[(0x23, 20, 0, 0)] + [(-1, 0, 0, 0)] * 3)
        self.assertEqual(R.item_damage_range(sword, 0), (12, 24))
        self.assertEqual(R.recalc_damage(self.t, w, obj, sword, 0), (200 + 35 + 10, 22, 34))
        w.stat_fn = lambda skill, stat, level: 50 if skill == 0x4F else 0
        rec.skills = [(0x4F, 5)]
        axe = R.Item(defn=R.ItemDef(dmg_min=10, dmg_max=20, dmg_type=4, subtype=6))
        self.assertEqual(R.recalc_damage(self.t, w, obj, axe, 0), (200, 15, 27))   # the thrown-weapon quirk


if __name__ == '__main__':
    unittest.main()
