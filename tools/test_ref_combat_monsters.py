#!/usr/bin/env python3
"""Unit tests of tools/ref_combat_monsters.py that need no game files (they run in CI).

Every fixture is synthetic: a sparse memory image with hand-placed objects, or the round-1
shared world (ref_combat_runtime.Runtime) with an authored floor.  The tests pin the rules
docs/spec/combat-monster-death.md states for the round-2 bodies; whether the bodies match
the game is the business of tools/difftest_combat_monsters.py."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_creature as RC                       # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_monsters as M                 # noqa: E402

f32 = T.f32
C_TABLE = 0x00700000                            # authored creature table: every slot a callback
OBJ_A, OBJ_B, OBJ_C = 0x00100000, 0x00101000, 0x00102000


class Rec(dict):
    """Callbacks that record every call and answer from `answers` (name -> value or
    function), else 0."""

    def __init__(self, answers=None):
        dict.__init__(self)
        self.log, self.answers = [], dict(answers or {})

    def get(self, name, default=None):
        def answer(*args):
            self.log.append((name, args))
            a = self.answers.get(name, 0)
            return a(*args) if callable(a) else a
        return answer


def plain(answers=None):
    mem = RC.Memory()
    rec = Rec(answers)
    m = M.MonsterCombatModel(mem, rec)
    for slot in range(48):
        mem.poke(C_TABLE + 8 * slot + 4, 4, 0x00F00000 + slot)
    for obj in (OBJ_A, OBJ_B, OBJ_C):
        mem.poke(obj + 0x48, 4, C_TABLE)
        mem.poke(obj + 0xC, 4, 0x20)
    return m, mem, rec


def place(mem, obj, x, y, z=0.0, r=12.0, h=40.0):
    for i, v in enumerate((x, y, z)):
        mem.poke(obj + 0x10 + 4 * i, 4, f32(v))
    mem.poke(obj + 0x1C, 4, f32(r))
    mem.poke(obj + 0x20, 4, f32(h))


def names(rec):
    return [n for n, _a in rec.log]


class HitHelpers(unittest.TestCase):
    def test_reach_hit_needs_the_target_within_60_of_the_point(self):
        rt = M.MonsterRuntime()
        a = rt.spawn_skelight((0.0, 0.0, 0.0), facing=0, team=1)
        b = rt.spawn_skelight((90.0, 0.0, 0.0), team=2)
        rt.svc_handle_link(a + T.H_TARGET, b, b)
        mark = len(rt.trace)
        rt.model.hit_target_at_reach(a, 4, 8, 100000, 8, 0, f32(36.0))       # point (36, 0, 0): 54 away
        self.assertTrue([e for e in rt.trace[mark:] if e[0] == 'damage_apply'])
        rt.mem.poke(b + 0x10, 4, f32(97.0))                                  # 61 away
        mark = len(rt.trace)
        self.assertEqual(rt.model.hit_target_at_reach(a, 4, 8, 100000, 8, 0, f32(36.0)), 0)
        self.assertFalse([e for e in rt.trace[mark:] if e[0] == 'damage_apply'])

    def test_reach_hit_skips_a_dead_target_and_ignores_facing_of_the_target(self):
        m, mem, rec = plain({'damage_apply': 1})
        place(mem, OBJ_A, 0.0, 0.0)
        place(mem, OBJ_B, 30.0, 0.0)
        node = 0x00200000
        mem.poke(node + 0xC, 4, OBJ_B)
        mem.poke(OBJ_A + T.H_TARGET, 4, node)
        self.assertEqual(m.hit_target_at_reach(OBJ_A, 1, 2, 100, 8, 0, f32(10.0)), 1)
        mem.poke(OBJ_B + 0xC, 4, 0x28)
        self.assertEqual(m.hit_target_at_reach(OBJ_A, 1, 2, 100, 8, 0, f32(10.0)), 0)

    def test_player_cone_strict_arc_far_cap_and_no_team_test(self):
        rt = M.MonsterRuntime()
        c = rt.spawn_skelight((0.0, 0.0, 0.0), facing=0, team=0)
        P = rt.spawn_player(0, (40.0, 0.0, 0.0), team=0)                     # same team: still found
        self.assertEqual(rt.model.find_player_in_cone(c, 0, 0x2000, 0, f32(48.0)), P)
        rt.mem.poke(P + 0x10, 4, f32(60.0))                                  # beyond far: a cap here
        self.assertEqual(rt.model.find_player_in_cone(c, 0, 0x2000, 0, f32(48.0)), 0)
        rt.mem.poke(P + 0x10, 4, f32(40.0))
        self.assertEqual(rt.model.find_player_in_cone(c, 0x8000, 0x2000, 0, f32(48.0)), 0)   # behind

    def test_or_player_falls_back_to_the_cone(self):
        m, mem, rec = plain({'damage_apply': 1, 'terrain_raycast': T.MISS})
        place(mem, OBJ_A, 0.0, 0.0)
        place(mem, OBJ_B, 30.0, 0.0)
        mem.poke(T.G_NUM_PLAYERS, 4, 1)
        mem.poke(T.G_PLAYERS + T.REC_OBJ, 4, OBJ_B)
        self.assertEqual(m.hit_target_or_player_in_arc(OBJ_A, 0, 0x2000, 1, 2, 100, 8, 0, 0, f32(48.0)), 1)
        self.assertEqual([a[0] for n, a in rec.log if n == 'damage_apply'], [OBJ_B])

    def test_knockback_target_writes_the_victim(self):
        m, mem, rec = plain()
        place(mem, OBJ_A, 0.0, 0.0)
        place(mem, OBJ_B, 0.0, 30.0)
        mem.poke(0x00200000 + 0xC, 4, OBJ_B)
        mem.poke(OBJ_A + T.H_TARGET, 4, 0x00200000)
        m.knockback_target(OBJ_A, f32(150.0))
        self.assertEqual(m.u32(OBJ_B + 0x2E8), f32(150.0))
        self.assertIn(m.u16(OBJ_B + 0x2E0), (0x3FFF, 0x4000))               # bearing +y (math_atan2_16 truncates)

    def test_cooldown_setters(self):
        m, mem, rec = plain({'creature_bossRank': 0})
        m.set_cooldown(OBJ_A, 30)                                            # no target: nothing
        self.assertEqual((rec.log, m.u16(OBJ_A + 0x318)), ([], 0))
        mem.poke(OBJ_A + T.H_TARGET, 4, 0x00200000)
        mem.poke(OBJ_A + 0x232, 2, 0x14)
        m.set_cooldown(OBJ_A, 30)                                            # dead: no set-state, cooldown stored
        self.assertEqual((names(rec), m.u16(OBJ_A + 0x318)), ([], 30))
        mem.poke(OBJ_A + 0x232, 2, 3)
        m.set_cooldown_on(OBJ_A, 45, OBJ_B)
        self.assertEqual(names(rec), ['creature_bossRank', 'handle_clear', 'handle_link', 'Creature.v27'])
        self.assertEqual(rec.log[-1][1], (OBJ_A, 0x10))
        rec.answers['creature_bossRank'] = 2
        del rec.log[:]
        m.set_cooldown_on(OBJ_A, 90, OBJ_B)
        self.assertEqual((names(rec), m.u16(OBJ_A + 0x318)), (['creature_bossRank'], 45))

    def test_notify_reaches_every_object_in_box_order(self):
        m, mem, rec = plain({'world_collectObjectsInBox': [OBJ_C, OBJ_A, OBJ_B]})
        m.notify_objects_near(0, (0, 0, 0), OBJ_A, f32(600.0))
        self.assertEqual([a[0] for n, a in rec.log if n == 'Creature.v12'], [OBJ_C, OBJ_A, OBJ_B])


class Destructors(unittest.TestCase):
    def test_creature_chain_order(self):
        nodes = [0x00300000, 0]
        m, mem, rec = plain({'iter_begin': lambda *a: nodes[0], 'iter_next': lambda *a: nodes.pop()})
        spell, table = 0x00310000, 0x00320000
        mem.poke(0x00300000 + 0xC, 4, spell)
        mem.poke(spell + 0x14, 4, table)
        m.creature_dtor(OBJ_A, 3)
        self.assertEqual(m.u32(OBJ_A + 0x48), M.VT_GAMEOBJECT)           # GameObject_dtor last
        self.assertEqual(names(rec)[:4], ['iter_begin', 'Spell.v1', 'iter_next', 'iter_end'])
        cleared = [a[0] - OBJ_A for n, a in rec.log if n == 'handle_clear']
        self.assertEqual(cleared, [0x364, 0x360, 0x2E4, 0x238, 0x234, 8, 4, 0])
        self.assertEqual(names(rec)[-1], 'pool_free')
        self.assertLess(names(rec).index('AnimState_dtor'), names(rec).index('pool_free'))

    def test_player_chain_and_the_ghost_operation(self):
        m, mem, rec = plain()
        mem.poke(OBJ_A + 0x3C8, 4, 1)
        R = T.G_PLAYERS + T.REC_SIZE
        mem.poke(R + T.REC_OBJ, 4, OBJ_A)
        mem.poke(R + 0x43DC, 4, 7)
        mem.poke(M.G_IN_GHOST_OP, 1, 1)
        m.player_dtor(OBJ_A, 2)
        self.assertEqual((m.u32(R + T.REC_OBJ), m.u32(R + 0x43DC)), (OBJ_A, 7))    # kept during a ghost op
        self.assertEqual(names(rec)[0], 'game_rebuildAlivePlayers')            # but still called
        mem.poke(M.G_IN_GHOST_OP, 1, 0)
        m.player_dtor(OBJ_A, 2)
        self.assertEqual((m.u32(R + T.REC_OBJ), m.u32(R + 0x43DC)), (0, 0))
        heads = [a[0] - OBJ_A for n, a in rec.log if n == 'handle_clear']
        self.assertEqual(heads[1:8], [0x4B8, 0x438, 0x420, 0x408, 0x3F0, 0x3D8, 0x364])
        self.assertNotIn('pool_free', names(rec))

    def test_name_properties_are_unregistered_in_order(self):
        m, mem, rec = plain()
        texts = {0x00400000: b'name=a\0', 0x00400010: b'Name=b\0', 0x00400020: b'name=c\0', 0x00400030: b'namex\0'}
        for a, t in texts.items():
            for i, ch in enumerate(t):
                mem.poke(a + i, 1, ch)
        for i, ch in enumerate(b'name\0'):                                   # the key string (authored)
            mem.poke(M.S_NAME_KEY + i, 1, ch)
        props = 0x00410000
        for i, a in enumerate(sorted(texts) + [0]):
            mem.poke(props + 4 * i, 4, a)
        mem.poke(OBJ_A + 0x2C, 4, props)
        m.gameobject_dtor(OBJ_A, 0)
        self.assertEqual([a[0] for n, a in rec.log if n == 'objNames_remove'], [0x00400005, 0x00400025])
        self.assertTrue(any(a == M.S_NAME_KEY for a, _s, _v in mem.log))     # the key is rewritten in place


class Death(unittest.TestCase):
    def test_blood_decal_takes_two_own_draws(self):
        m, mem, rec = plain()
        mem.poke(OBJ_A + 0xA8, 8, 0x2000)
        mem.poke(OBJ_A + 0x44, 4, 12345)
        m.dead_update(OBJ_A, 0x80, (0, 0, 0), 0, f32(20.0))
        decals = [a for n, a in rec.log if n == 'decal_add']
        self.assertEqual(len(decals), 1)
        self.assertEqual(decals[0][2], 3)                                    # kind of bit 0x2000
        s = 12345
        for _ in range(2):
            s = (s * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
        self.assertEqual(m.u32(OBJ_A + 0x44), s)
        self.assertEqual(m.draws, 0)                                         # no shared draw

    def test_drop_loot_ordinary_tint_and_miniboss(self):
        m, mem, rec = plain({'Creature.v0': 1, 'rtti_typeInfoEquals': 0, 'creature_bossRank': 0})
        floats = (f32(36.0), f32(2.0), f32(1.0), f32(0.6), f32(2.0), f32(0.25))
        m.drop_loot(OBJ_A, (0, 0, 0), 0, 7, *floats)
        loot = [a for n, a in rec.log if n == 'loot_generateDrops']
        self.assertEqual(loot, [((0, 0, 0), 0, 7, 0) + floats])
        del rec.log[:]
        mem.poke(OBJ_A + 0xA0, 1, 6)
        m.drop_loot(OBJ_A, (0, 0, 0), 0, 7, *floats)
        loot = [a for n, a in rec.log if n == 'loot_generateDrops']
        self.assertEqual((loot[0][6], loot[0][8]), (f32(3.0), f32(8.0)))
        del rec.log[:]
        mem.poke(OBJ_A + 0xA8, 8, 1)
        m.drop_loot(OBJ_A, (0, 0, 0), 0, 7, *floats)
        self.assertNotIn('loot_generateDrops', names(rec))

    def test_drop_loot_boss_class_coin_per_player_uses_own_draws(self):
        zek = {'Creature.v0': 'Z', 'Zek_typeinfo': 'Z', 'rtti_typeInfoEquals': lambda a, b: int(a == b)}
        m, mem, rec = plain(zek)
        mem.poke(T.G_NUM_PLAYERS, 4, 3)
        mem.poke(OBJ_A + 0x44, 4, 99)
        m.drop_loot(OBJ_A, (0, 0, 0), 0, 7, *(f32(v) for v in (36.0, 2.0, 1.0, 0.6, 2.0, 0.25)))
        loot = [a for n, a in rec.log if n == 'loot_generateDrops']
        self.assertEqual(len(loot), 3 + 3)                                   # no ordinary call for Zek
        self.assertTrue(all(a[2] == 0 for a in loot))
        self.assertNotEqual(m.u32(OBJ_A + 0x44), 99)
        self.assertEqual(m.draws, 0)

    def test_goblin_corpse_sinks_in_a_crowd(self):
        dead = [OBJ_B, OBJ_C, OBJ_B]
        m, mem, rec = plain({'world_collectObjectsInBox': dead, 'Creature.v0': 0, 'rtti_typeInfoEquals': 0})
        for o in (OBJ_B, OBJ_C):
            mem.poke(o + 0xC, 4, 0x29)
        holder, htable = 0x00500000, 0x00510000
        mem.poke(holder, 4, htable)
        mem.poke(OBJ_A + 0x50, 4, holder)
        mem.poke(OBJ_A + 0xC, 4, 0x29)
        m.goblin_set_state(OBJ_A, 0x14)
        self.assertEqual(m.u32(OBJ_A + 0x488), 1)
        self.assertEqual(m.u32(OBJ_A + 0xC) & 1, 0)                          # flag 1 cleared again
        self.assertEqual([a[1] for n, a in rec.log if n == 'Holder.v11'], [1, 2])
        self.assertIn('loot_generateDrops', names(rec))
        self.assertEqual(names(rec)[-1], 'Creature.v28')
        self.assertEqual(m.u16(OBJ_A + 0x232), 0x14)
        with self.assertRaises(T.Unsupported):
            m.goblin_set_state(OBJ_A, 3)


if __name__ == '__main__':
    unittest.main()
