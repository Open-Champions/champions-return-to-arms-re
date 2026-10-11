#!/usr/bin/env python3
"""Unit tests for tools/ref_skills_b.py that need no game files: the Skill base on a made-up
Skill object, the handle lists, the spell walk and the projectile step, and for the second pass the Shock
chain, the Charge contact, AncestralCall's constructor for the prediction copy and its query.
The comparison with
the game's own code is tools/difftest_skills_b.py."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_skills_b as SB                       # noqa: E402

SKILL, TABLE, NODES, HEAD, OBJ = 0x1000, 0x2000, 0x3000, 0x5000, 0x6000
BASE_SLOTS = {1: 0x3C8218, 2: 0x3C8220, 5: 0x3C82A8, 8: 0x3C82E4, 10: 0x3C85FC, 11: 0x3C8690, 12: 0x3C87F0,
              13: 0x3C8864, 14: 0x3C88DC, 15: 0x3C88E4}


def make(callbacks=None, nodes=40):
    """A model on an empty memory with a Skill object whose table holds the base slots, and
    a pool of free handle nodes."""
    mem = RC.Memory()
    for slot, fn in BASE_SLOTS.items():
        mem.poke(TABLE + 8 * slot + 4, 4, fn)
    mem.poke(SKILL + 0x60, 4, TABLE)
    for i in range(nodes):
        mem.poke(NODES + 0x14 * i, 4, NODES + 0x14 * (i + 1) if i + 1 < nodes else 0)
    mem.poke(SB.G_HANDLE_FREE, 4, NODES)
    return SB.Model(mem, callbacks or {}), mem


def set_stat(mem, stat, first, base, step, first2=0xFFFF, base2=0, step2=0.0):
    mem.poke(SKILL + 0x0E + 2 * stat, 2, first)
    mem.poke(SKILL + 0x18 + 2 * stat, 2, base)
    mem.poke(SKILL + 0x24 + 4 * stat, 4, C.f32(step))
    mem.poke(SKILL + 0x38 + 2 * stat, 2, first2)
    mem.poke(SKILL + 0x42 + 2 * stat, 2, base2)
    mem.poke(SKILL + 0x4C + 4 * stat, 4, C.f32(step2))


class SkillBase(unittest.TestCase):
    def test_tier1(self):
        model, mem = make()
        set_stat(mem, 0, 1, 30, 3.0)
        set_stat(mem, 1, 5, 10, -2.5)
        self.assertEqual(model.skill_get_stat(SKILL, 0, 0), 0)                # level 0
        self.assertEqual(model.skill_get_stat(SKILL, 0, 1), 30)
        self.assertEqual(model.skill_get_stat(SKILL, 0, 20), 87)
        self.assertEqual(model.skill_get_stat(SKILL, 1, 4), 0)                # below the first level
        self.assertEqual(RC.s32(model.skill_get_stat(SKILL, 1, 10)), -3)      # 10 - 12.5 = -2.5, half away from zero

    def test_tier2_and_cap(self):
        model, mem = make()
        set_stat(mem, 0, 1, 30, 3.0, first2=1, base2=5, step2=1.0)
        set_stat(mem, 1, 1, 30, 3.0)                                          # no tier 2: falls back to tier 1
        self.assertEqual(model.skill_get_stat_tier2(SKILL, 0, 40, 0), 44)
        self.assertEqual(model.skill_get_stat_tier2(SKILL, 0, 40, 10), 14)     # level limited by the cap
        self.assertEqual(model.skill_get_stat_tier2(SKILL, 1, 40, 10), 57)
        self.assertEqual(model.skill_get_stat_tier2(SKILL, 0, 0, 10), 0)

    def test_for_caster(self):
        model, mem = make()
        set_stat(mem, 0, 1, 30, 3.0, first2=1, base2=5, step2=1.0)
        player, monster = OBJ, OBJ + 0x100
        mem.poke(player + 0xC, 4, 0x40)
        mem.poke(monster + 0xC, 4, 0x20)
        self.assertEqual(model.skill_get_stat_for(SKILL, 0, 20, player, 10), 87)    # tier 1, cap ignored
        self.assertEqual(model.skill_get_stat_for(SKILL, 0, 20, monster, 10), 14)
        self.assertEqual(model.skill_get_stat_for(SKILL, 0, 20, 0, 0), 24)
        self.assertEqual(model.skill_mana_from_stat4(SKILL, 3, 20), C.f32(0.0))
        self.assertEqual(model.skill_adjust_level(SKILL, 7, 20), 7)

    def test_range(self):
        model, mem = make()
        set_stat(mem, 0, 1, 100, 0.0)
        out = 0x7000
        model.skill_stat_range(SKILL, 0, 1, 0, out, out + 4, C.f32(0.2))
        self.assertEqual((mem.load(out, 4), mem.load(out + 4, 4), model.draws), (80, 120, 0))
        mem.poke(SB.G_RAND_SEED, 4, 12345)
        model.skill_stat_range(SKILL, 0, 1, 1, out, out + 4, C.f32(0.2))
        self.assertEqual(model.draws, 4)                                       # two draws per bound
        self.assertTrue(80 <= mem.load(out, 4) <= 100 <= mem.load(out + 4, 4) <= 120)
        set_stat(mem, 0, 1, 0, 0.0)
        model.skill_stat_range(SKILL, 0, 1, 0, out, out + 4, C.f32(0.2))
        self.assertEqual((mem.load(out, 4), mem.load(out + 4, 4)), (1, 1))     # never below 1


class Lists(unittest.TestCase):
    def test_newest_first_and_clear(self):
        model, mem = make()
        a, b = OBJ, OBJ + 0x100
        model.handle_link(HEAD, a, a)
        model.handle_link(HEAD, b, b)
        self.assertEqual(model.list_objects(HEAD), [b, a])
        model.handle_clear(a)                           # the object is destroyed: its handles go empty
        self.assertEqual(model.list_objects(HEAD), [b])
        model.handle_clear(HEAD)
        self.assertEqual(mem.load(HEAD, 4), 0)
        self.assertEqual(mem.load(b, 4), 0)             # the back list is empty again
        count, node = 0, mem.load(SB.G_HANDLE_FREE, 4)
        while node:
            count, node = count + 1, mem.load(node, 4)
        self.assertEqual(count, 40)                     # every node is back on the free list

    def test_iterator_skips_and_ignores_new_heads(self):
        model, mem = make()
        objs = [OBJ + 0x100 * i for i in range(4)]
        mem.poke(objs[1] + 0xC, 4, 8)                   # masked out
        for obj in objs:
            model.handle_link(HEAD, obj, obj)
        it, seen = 0x7100, []
        model.iter_begin(it, HEAD, 8)
        while mem.load(it + 4, 4):
            seen.append(mem.load(mem.load(it + 4, 4) + 0xC, 4))
            if len(seen) == 1:
                model.handle_link(HEAD, OBJ + 0x900, OBJ + 0x900)      # linked during the walk: not visited
            model.iter_next(it)
        model.iter_end(it, 2)
        self.assertEqual(seen, [objs[3], objs[2], objs[0]])
        self.assertEqual(model.list_objects(HEAD)[0], OBJ + 0x900)

    def test_list_fill_order(self):
        model, mem = make()
        SB.list_fill(mem.load, mem.poke, HEAD, [11, 22, 33])
        self.assertEqual(model.list_objects(HEAD), [11, 22, 33])


class Spells(unittest.TestCase):
    def test_walk_runs_the_newest_spell_first(self):
        ran = []
        model, mem = make({'Spell.v2': lambda spell, pos, facing: ran.append((spell, pos, facing))})
        creature, table = OBJ, 0x7200
        mem.poke(creature + 0x38, 2, 0xF11C)
        spells = [0x7300, 0x7340]
        for spell in spells:
            mem.poke(spell + 0x14, 4, table)            # a table this module has no body for: a callback
            model.creature_add_spell(creature, spell)
        pos = 0x7400
        for i, value in enumerate((1.0, 2.0, 3.0)):
            mem.poke(pos + 4 * i, 4, C.f32(value))
        model.creature_update_spells(creature, pos)
        self.assertEqual([r[0] for r in ran], [spells[1], spells[0]])
        self.assertEqual(ran[0][1], (C.f32(1.0), C.f32(2.0), C.f32(3.0)))
        self.assertEqual(ran[0][2], 0xFFFFF11C)         # the facing is sign-extended

    def test_base_ctor_draws_once(self):
        model, mem = make()
        mem.poke(SB.G_RAND_SEED, 4, 1)
        model.spell_base_ctor(0x7500, 7, OBJ, SKILL, 0x518A98)
        self.assertEqual(model.draws, 1)
        self.assertEqual(mem.load(0x7500 + 0x10, 4), ((1 * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF) >> 16)
        self.assertEqual(mem.load(0x7500, 1), 7)


class Projectiles(unittest.TestCase):
    def test_step_and_touch(self):
        touched = []
        other = OBJ + 0x200

        def box(low, high, capacity):
            return [other]
        callbacks = {'world_collectObjectsInBox': box,
                     'terrain_height': lambda world, pos, radius: C.f32(-100.0),
                     'Creature.v6': lambda this, by: touched.append((this, by))}
        model, mem = make(callbacks)
        obj, vel, table = OBJ, 0x7600, 0x7700
        for target in (obj, other):
            mem.poke(target + 0x48, 4, table)
            mem.poke(target + 0x1C, 4, C.f32(12.0))
            mem.poke(target + 0x20, 4, C.f32(72.0))
        mem.poke(vel, 4, C.f32(600.0))
        mem.poke(other + 0x10, 4, C.f32(15.0))
        result = model.obj_move_and_collide(obj, vel)
        self.assertEqual(result, 2)
        self.assertEqual(touched, [(other, obj), (obj, other)])        # the other object's handler first
        self.assertAlmostEqual(C.to_float(mem.load(obj + 0x10, 4)), 10.0, places=4)


class Registry(unittest.TestCase):
    def test_every_id_has_a_row(self):
        self.assertEqual(sorted(SB.SKILLS), list(range(35, 69)))
        for name, (start, end) in SB.FUNCTIONS.items():
            self.assertTrue(0x100000 <= start < end < 0x400000, name)
        for table in (SB.SKILL_BODIES, SB.SPELL_BODIES, SB.OBJECT_BODIES):
            for address, method in table.items():
                self.assertTrue(hasattr(SB.Model, method), method)
        for sid, (start, _end, slot, _n) in SB.MANA_COST.items():
            self.assertIn(slot, (14, 15))
            self.assertEqual(SB.SKILL_BODIES[start], 'mana_cost_%d' % sid)

    def test_mana_cost_forwards(self):
        model, mem = make()
        set_stat(mem, 4, 1, 35, 3.0)
        self.assertEqual(model.mana_cost_35(SKILL, 2), C.f32(38.0))    # slot 15: statistic 4 as a float
        self.assertEqual(model.mana_cost_59(SKILL, 2), C.f32(0.0))     # LifeTap costs nothing


class SecondPass(unittest.TestCase):
    """The casts and effects added by the second pass, on made-up memory."""

    def creature(self, mem, addr, x, y, flags=0x20):
        mem.poke(addr + 0xC, 4, flags)
        mem.poke(addr + 0x10, 4, C.f32(x))
        mem.poke(addr + 0x14, 4, C.f32(y))
        return addr

    def test_helpers(self):
        self.assertEqual(SB.from_uint(46), C.f32(46.0))
        self.assertTrue(C.lt(C.f32(4.0e9), SB.from_uint(0xFFFFFFFF)))       # a clock behind the cast: a huge difference
        self.assertEqual(SB.c_rem(-7, 3), -1)
        self.assertEqual(SB.c_rem(7, 0), 7)

    def test_shock_chain_is_depth_first_nearest_first(self):
        model, mem = make()
        bolt = OBJ
        a, b, c, far = (self.creature(mem, 0x7000 + 0x400 * i, x, 0.0) for i, x in enumerate((0.0, 100.0, 190.0, 500.0)))
        for obj in (far, c, b, a):                          # a ends up at the head, as the target does
            model.handle_link(bolt + 0x50, obj, obj)
        mem.poke(bolt + 0x18C, 4, 0x472DE900)               # 211 squared
        mem.poke(bolt + 0x18A, 1, 3)
        model.shock_build_chain(bolt, a + 0x10)
        self.assertEqual(model.list_objects(bolt + 0x54), [c, b, a])       # newest first; `far` is out of range of all
        self.assertEqual(model.u8(bolt + 0x18B), 3)
        self.assertEqual(model.shock_in_chain(bolt, b), 1)
        self.assertEqual(model.shock_in_chain(bolt, far), 0)
        # the limit is a count of links
        model.handle_clear(bolt + 0x54)
        mem.poke(bolt + 0x18B, 1, 0)
        mem.poke(bolt + 0x18A, 1, 2)
        model.shock_build_chain(bolt, a + 0x10)
        self.assertEqual(model.list_objects(bolt + 0x54), [b, a])

    def test_charge_contact_happens_once(self):
        calls = []

        class Callbacks:
            def get(self, name):
                def answer(*args):
                    calls.append((name, args))
                    return {'Creature.v20': 1}.get(name, 0)
                return answer
        model, mem = make(Callbacks())
        set_stat(mem, 0, 1, 120, 10.0)
        spell, owner, target = OBJ, 0x7000, 0x7400
        self.creature(mem, owner, 0.0, 0.0, 0x60)
        self.creature(mem, target, 10.0, 0.0)
        mem.poke(spell, 1, 1)
        mem.poke(spell + 8, 4, SKILL)
        mem.poke(spell + 0xC, 4, owner)
        mem.poke(spell + 0x10, 4, 0x1234)
        model.charge_on_contact(spell, target)
        hits = [args for name, args in calls if name == 'damage_apply']
        self.assertEqual(len(hits), 1)
        self.assertEqual((hits[0][0], hits[0][1], hits[0][5], hits[0][8]), (target, owner, 0x8C040, C.f32(120.0)))
        self.assertEqual(model.u32(spell + 0x48), 1)
        model.charge_on_contact(spell, target)               # the second contact does nothing
        self.assertEqual(len([1 for name, _a in calls if name == 'damage_apply']), 1)

    def test_ancestral_call_copy_stops_before_the_state_change(self):
        calls = []

        class Callbacks:
            def get(self, name):
                def answer(*args):
                    calls.append(name)
                    return ('buf', b'clip') if name == 'libc_sprintf' else 0
                return answer
        model, mem = make(Callbacks())
        spell, copy, class_def = OBJ, 0x7000, 0x7800
        mem.poke(copy + 0xC, 4, 0x20060)                    # the prediction copy
        mem.poke(copy + 0x24, 4, class_def)
        mem.poke(copy + 0x58C, 4, 2)
        model.ancestralcall_spell_ctor(spell, 5, copy, SKILL)
        self.assertEqual(model.u32(copy + 0x58C), 2)        # not put into the casting state
        self.assertEqual(calls, ['res_find', 'sound_playOnObject', 'libc_sprintf', 'res_find', 'anim_startBlendInOut'])
        self.assertEqual(model.draws, 1)                    # the spell's seed, which prediction restores

    def test_query_for_is_inclusive_and_owner_is_always_in(self):
        model, mem = make()
        set_stat(mem, 3, 1, 5, 0.0)                         # radius 5 x 12 = 60
        set_stat(mem, 0, 1, 125, 0.0)
        spell, owner, other = OBJ, 0x7000, 0x7400
        self.creature(mem, owner, 0.0, 0.0, 0x60)
        self.creature(mem, other, 60.0, 0.0, 0x60)
        mem.poke(spell, 1, 1)
        mem.poke(spell + 8, 4, SKILL)
        mem.poke(spell + 0xC, 4, owner)
        out = 0x7C00
        self.assertEqual(model.ancestralcall_query_for(spell, other, out, 0), 1)       # exactly at the radius
        self.assertEqual(mem.load(out, 4), C.mul(C.f32(125.0), 0x3C23D70A))            # 1.2499999 under truncation
        mem.poke(other + 0x10, 4, C.f32(60.5))
        self.assertEqual(model.ancestralcall_query_for(spell, other, 0, 0), 0)
        self.assertEqual(model.ancestralcall_query_for(spell, owner, 0, 0), 1)
        self.assertEqual(model.ancestralcall_query_for(spell, 0, 0, 0), 0)


if __name__ == '__main__':
    unittest.main()
