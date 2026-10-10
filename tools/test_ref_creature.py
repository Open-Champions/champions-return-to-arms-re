#!/usr/bin/env python3
"""Unit tests of tools/ref_creature.py that need no game files (they run in CI).

They check the model's own logic on a synthetic memory image: that it behaves the way
docs/spec/creature-tick.md says.  Whether that is what the game does is the business of
tools/difftest_creature.py, which needs the executable."""
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_creature as RC                       # noqa: E402
from ref_creature import Model, Memory, M32     # noqa: E402


def f32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def fl(raw):
    return struct.unpack('<f', struct.pack('<I', raw & M32))[0]


class Game:
    """A memory image with one base-class creature and a few other objects."""

    def __init__(self):
        self.mem = Memory()
        self.table = 0x00100000
        for slot, (addr, _method) in RC.BASE_BODIES.items():
            self.mem.poke(self.table + 8 * slot + 4, 4, addr)
        self.next = 0x00200000
        self.nodes = {}
        self.calls = []
        self.answers = {}
        self.c = self.creature(100.0, 200.0)
        self.mem.poke(RC.G_NUM_PLAYERS, 4, 1)
        self.mem.poke(RC.G_SIM_FRAME, 4, 1001)

    def creature(self, x, y, flags=0x20, team=0xFF):
        obj = self.next
        self.next += 0x1000
        poke = self.mem.poke
        poke(obj + 0xC, 4, flags)
        for i, v in enumerate((x, y, 0.0)):
            poke(obj + 0x10 + 4 * i, 4, f32(v))
            poke(obj + 0x3B4 + 4 * i, 4, f32(v))
        poke(obj + 0x1C, 4, f32(16.0))
        poke(obj + 0x20, 4, f32(72.0))
        poke(obj + 0x48, 4, self.table)
        poke(obj + 0xB0, 4, f32(1.0))
        poke(obj + 0xB8, 4, f32(120.0))
        poke(obj + 0xDC, 4, f32(1.0))
        poke(obj + 0x228, 4, f32(100.0))
        poke(obj + 0x22C, 4, f32(100.0))
        poke(obj + 0x310, 1, team)
        poke(obj + 0x3C0, 4, f32(1000.0))
        node = self.next
        self.next += 0x100
        poke(node + 0xC, 4, obj)
        self.nodes[obj] = node
        return obj

    def model(self):
        game = self

        class Callbacks:
            def get(self, name):
                def answer(*args):
                    game.calls.append((name, args))
                    if name == 'handle_clear':
                        game.mem.poke(args[0], 4, 0)
                    if name == 'handle_link':
                        game.mem.poke(args[0], 4, game.nodes[args[2]])
                    if name in game.answers:
                        return game.answers[name](*args)
                    return RC.shape_result(name, args)
                return answer
        return Model(self.mem, Callbacks())

    def u(self, addr, size=4):
        return self.mem.load(addr, size)

    def s16(self, addr):
        return RC.s16(self.mem.load(addr, 2))


class RunTests(unittest.TestCase):
    def test_always_returns_zero_and_counts_the_clock(self):
        g = Game()
        self.assertEqual(g.model().run(g.c, 0), 0)
        self.assertEqual(g.u(g.c + 0x300), 1)
        g.mem.poke(g.c + 0x2FC, 1, 60)                       # fully slowed: the clock stands
        g.model().run(g.c, 0)
        self.assertEqual(g.u(g.c + 0x300), 1)
        g.mem.poke(g.c + 0x2FC, 1, 59)
        g.model().run(g.c, 0)
        self.assertEqual(g.u(g.c + 0x300), 2)

    def test_flash_colours_move_two_toward_zero(self):
        g = Game()
        for k, v in enumerate((5, 1, -1, -7, 0, 2, -2, 300)):
            g.mem.poke(g.c + 0x90 + 2 * k, 2, v & 0xFFFF)
        g.model().run(g.c, 0)
        self.assertEqual([g.s16(g.c + 0x90 + 2 * k) for k in range(8)], [3, 0, 0, -5, 0, 0, 0, 298])

    def test_frame_timers(self):
        g = Game()
        for off, value in ((0x314, 0xFFFF), (0x316, 3), (0x318, 1), (0x31A, 7), (0x31C, 2)):
            g.mem.poke(g.c + off, 2, value)
        g.model().run(g.c, 0)
        self.assertEqual([g.s16(g.c + off) for off in (0x314, 0x316, 0x318, 0x31A, 0x31C)], [-1, 2, 0, 6, 1])

    def test_counter_seven_ramps_then_caps(self):
        g = Game()
        g.mem.poke(g.c + 0x388, 4, 300)
        g.mem.poke(g.c + 0xF0, 4, 1001 - 4)                  # started four frames ago
        g.model().run(g.c, 0)
        self.assertEqual(g.u(g.c + 0x2FC, 1), 8)             # two per frame
        g.mem.poke(g.c + 0xF0, 4, 1001 - 31)
        g.model().run(g.c, 0)
        self.assertEqual(g.u(g.c + 0x2FC, 1), 60)            # after the ramp: 60 for a counter above 30
        g.mem.poke(g.c + 0x388, 4, 12)
        g.model().run(g.c, 0)
        self.assertEqual(g.u(g.c + 0x2FC, 1), 12)            # ... and the counter itself at 30 or below
        g.mem.poke(g.c + 0x6C, 4, f32(0.5))                  # lightning resistance caps it
        g.mem.poke(g.c + 0x388, 4, 300)
        g.model().run(g.c, 0)
        self.assertEqual(g.u(g.c + 0x2FC, 1), 30)
        self.assertEqual(g.u(g.c + 0x388), 300)              # Creature_run never decrements the counter

    def test_a_burning_monster_draws_nothing_a_player_one(self):
        for flags, draws in ((0x20, 0), (0x40, 1)):
            g = Game()
            g.mem.poke(g.c + 0xC, 4, flags)
            g.mem.poke(g.c + 0x340, 4, f32(2.0))
            g.mem.poke(RC.G_SIM_FRAME, 4, 0x1000)            # a 32nd frame
            g.answers['net_objOrGhost'] = lambda obj: obj
            m = g.model()
            m.run(g.c, 0)
            self.assertEqual(m.draws, draws)
            hit = [args for name, args in m.calls if name == 'damage_apply']
            self.assertEqual(len(hit), 1)
            self.assertEqual(hit[0][5], 0x1180C040)
            if not draws:
                self.assertEqual(hit[0][6], ('elem', 1, 1))

    def test_boss_meter_follows_the_local_alive_list(self):
        g = Game()
        player = g.creature(110.0, 200.0, flags=0x40)
        g.mem.poke(RC.G_PLAYERS + RC.REC_OBJ, 4, player)
        g.mem.poke(g.c + 0xA8, 8, 0x8000000000000001)        # MiniBoss, active
        g.model().run(g.c, 0)
        self.assertFalse(g.u(g.c + 0xA8, 8) & 0x80000000)    # nobody local and alive: no meter
        g.mem.poke(RC.G_LOCAL_ALIVE_COUNT, 4, 1)
        g.mem.poke(RC.G_LOCAL_ALIVE_LIST, 4, 0)
        g.model().run(g.c, 0)
        self.assertTrue(g.u(g.c + 0xA8, 8) & 0x80000000)
        g.model().run(g.c, 0)
        self.assertEqual(g.u(RC.G_BOSS_METER_MAX), 100)
        g.mem.poke(RC.G_LOCAL_ALIVE_COUNT, 4, 0)
        g.model().run(g.c, 0)
        self.assertFalse(g.u(g.c + 0xA8, 8) & 0x80000000)


class DamageTests(unittest.TestCase):
    def test_take_damage(self):
        g = Game()
        attacker = g.creature(100.0, 150.0)
        g.model().take_damage(g.c, attacker, 0x800, f32(30.0))
        self.assertEqual(fl(g.u(g.c + 0x228)), 70.0)
        self.assertEqual(fl(g.u(g.c + 0xC8)), 30.0)
        self.assertEqual(g.u(g.c + 0x2DC), 0x800)
        self.assertEqual(g.u(g.c + 0x304), 1001)
        self.assertEqual(g.s16(g.c + 0x3B0), 0x7FFF)
        self.assertEqual(g.u(g.c + 0x2E4), g.nodes[attacker])

    def test_inert_and_ignore_damage(self):
        g = Game()
        g.mem.poke(g.c + 0x231, 1, 1)
        g.model().take_damage(g.c, 0, 1, f32(30.0))
        self.assertEqual(fl(g.u(g.c + 0x228)), 100.0)
        self.assertEqual(g.s16(g.c + 0x3B0), 0)
        g.mem.poke(g.c + 0x231, 1, 0)
        g.mem.poke(g.c + 0xA8, 8, 0x1000000000000)
        g.mem.poke(g.c + 0x340, 4, f32(5.0))
        g.model().take_damage(g.c, 0, 1, f32(30.0))
        self.assertEqual(fl(g.u(g.c + 0x228)), 100.0)
        self.assertEqual(g.u(g.c + 0x340), 0)
        self.assertEqual(g.s16(g.c + 0x3B0), 0x7FFF)         # the arc opens all the same

    def test_death_order_of_call_outs(self):
        g = Game()
        player = g.creature(110.0, 200.0, flags=0x40)
        record = RC.G_PLAYERS
        g.mem.poke(record + RC.REC_OBJ, 4, player)
        g.mem.poke(record + 0x59, 1, 5)
        g.mem.poke(record + 0xAC, 4, f32(50.0))
        g.mem.poke(record + 0x50, 4, 1)
        g.mem.poke(RC.G_EXP_TABLE + 20, 4, 1000)
        g.mem.poke(RC.G_EXP_TABLE + 24, 4, 1600)
        g.mem.poke(g.c + 0xD8, 4, f32(5000.0))               # (5000 / level 5) ^ 1.4 x 0.75 is far above the cap
        g.model().take_damage(g.c, player, 0x80001, f32(250.0))
        m = g.model()
        m.process_damage(g.c, 0)
        names = [name for name, _args in m.calls]
        self.assertEqual(names, ['world_notifyObjectsNear', 'obj_getPropInt', 'player_getSkillRank',
                                 'SkillLifeTap_getStat0Fraction', 'player_giveExp'])
        self.assertEqual(g.s16(g.c + 0x232), 0x14)           # the base set-state stored it
        self.assertEqual(g.u(g.c + 0xC) & 0x2009, 0x2009)
        self.assertEqual(g.u(g.c + 0x2E8), 0x43160000)       # 150: flag bit 0x80000 at death
        self.assertEqual(g.u(g.c + 0x2DC), 0)
        self.assertEqual(m.draws, 0)                         # no shared draw in the base class's death
        give = [args for name, args in m.calls if name == 'player_giveExp'][0]
        self.assertEqual(give, (0, 600))                     # capped at one level's worth

    def test_a_corpse_keeps_its_flags(self):
        g = Game()
        g.mem.poke(g.c + 0x232, 2, 0x14)
        g.mem.poke(g.c + 0xC8, 4, f32(5.0))
        g.mem.poke(g.c + 0x2DC, 4, 0x40000)
        g.model().process_damage(g.c, 0)
        self.assertEqual(g.u(g.c + 0xC8), 0)
        self.assertEqual(g.u(g.c + 0x2DC), 0x40000)


class TargetTests(unittest.TestCase):
    def scan(self, g, found, force=0):
        g.answers['world_collectObjectsInBox'] = lambda low, high, cap: list(found)
        g.mem.poke(RC.G_SIM_FRAME, 4, 0x2000)                # a scan frame for serial 0
        g.mem.poke(RC.G_EXCLUDE_MASK, 4, 0x20000)
        m = g.model()
        m.pick_target(g.c, force)
        return m

    def test_nearest_enemy_and_the_mask(self):
        g = Game()
        far = g.creature(400.0, 200.0, team=1)
        near = g.creature(150.0, 200.0, team=1)
        friend = g.creature(101.0, 200.0, team=0xFF)
        m = self.scan(g, [far, friend, near])
        self.assertEqual(g.u(g.c + 0x234), g.nodes[near])
        self.assertEqual(g.u(RC.G_EXCLUDE_MASK), 0x20000)    # restored
        stores = [value for addr, _size, value in m.writes if addr == RC.G_EXCLUDE_MASK]
        self.assertEqual(stores, [8, 0x20000])
        self.assertEqual(m.draws, 0)

    def test_last_attacker_outscores_distance(self):
        g = Game()
        far = g.creature(400.0, 200.0, team=1)
        near = g.creature(150.0, 200.0, team=1)
        g.mem.poke(g.c + 0x2E4, 4, g.nodes[far])
        self.scan(g, [far, near])
        self.assertEqual(g.u(g.c + 0x234), g.nodes[far])

    def test_a_scan_drops_a_target_the_query_does_not_return(self):
        g = Game()
        old = g.creature(150.0, 200.0, team=1)
        g.mem.poke(g.c + 0x234, 4, g.nodes[old])
        self.scan(g, [])
        self.assertEqual(g.u(g.c + 0x234), 0)

    def test_force_changes_target(self):
        g = Game()
        current = g.creature(110.0, 200.0, team=1)
        other = g.creature(900.0, 200.0, team=1)
        g.mem.poke(g.c + 0x234, 4, g.nodes[current])
        self.scan(g, [current, other], force=1)
        self.assertEqual(g.u(g.c + 0x234), g.nodes[other])

    def test_leash(self):
        g = Game()
        g.mem.poke(g.c + 0x3C0, 4, f32(100.0))               # HomeRange 100, home = position
        g.mem.poke(g.c + 0x304, 4, 0)                        # not hit for a long time
        outside = g.creature(195.0, 200.0, team=1)           # 95 away: beyond 60 + radii? no, 60+32 = 92
        self.scan(g, [outside])
        self.assertEqual(g.u(g.c + 0x234), g.nodes[outside]) # inside HomeRange of home: accepted
        g2 = Game()
        g2.mem.poke(g2.c + 0x3C0, 4, f32(90.0))
        outside = g2.creature(195.0, 200.0, team=1)
        self.scan(g2, [outside])
        self.assertEqual(g2.u(g2.c + 0x234), 0)              # outside it, farther than 92: left alone
        g2.mem.poke(g2.c + 0x304, 4, 0x2000 - 100)           # hit 100 frames ago: the leash is off
        g2.mem.poke(g2.c + 0x3C0, 4, f32(96.0))              # (the box and the tie-break still use HomeRange)
        self.scan(g2, [outside])
        self.assertEqual(g2.u(g2.c + 0x234), g2.nodes[outside])

    def test_is_enemy(self):
        g = Game()
        m = g.model()
        self.assertEqual(m.is_enemy(g.c, 0), 0)
        self.assertEqual(m.is_enemy(g.c, g.c), 0)
        self.assertEqual(m.is_enemy(g.c, g.creature(0.0, 0.0, team=1)), 1)
        self.assertEqual(m.is_enemy(g.c, g.creature(0.0, 0.0, team=0xFF)), 0)
        self.assertEqual(m.is_enemy(g.c, g.creature(0.0, 0.0, flags=0x28, team=1)), 0)
        priority = g.creature(0.0, 0.0, team=1)
        g.mem.poke(priority + 0xA8, 8, 0x100000000000)
        self.assertEqual(m.is_enemy(g.c, priority), 4)


class MoveTests(unittest.TestCase):
    def test_turn_returns_the_angle_before_the_turn(self):
        g = Game()
        d = g.model().turn_toward(g.c, 0, (f32(100.0), f32(300.0), 0))     # straight along +y
        self.assertEqual(d, 0x3FFF)                          # a quarter turn, truncated by the angle conversion
        self.assertEqual(g.s16(g.c + 0x110), 453)            # int(16383 x 0.05) = 819, less int(819 x sqrt(0.2))
        self.assertEqual(g.s16(g.c + 0x38), 453)
        g2 = Game()
        self.assertEqual(g2.model().turn_toward(g2.c, 1, (f32(100.0), f32(300.0), 0)), -0x4001)

    def test_slow_removes_the_root_yaw(self):
        g = Game()
        g.mem.poke(g.c + 0xC4, 2, 500)
        g.mem.poke(g.c + 0xBC, 4, f32(2.0))
        g.model().step_anim(g.c, f32(1.0))
        self.assertEqual(g.s16(g.c + 0xC4), 500)
        g.mem.poke(g.c + 0x2FC, 1, 1)
        g.model().step_anim(g.c, f32(1.0))
        self.assertEqual(g.s16(g.c + 0xC4), 0)               # AN1

    def test_move_by_gravity_and_ground(self):
        g = Game()
        g.answers['terrain_heightBelow'] = lambda world, pos, radius: f32(-50.0)
        bits = g.model().move_by(g.c, (0, 0, 0))
        self.assertEqual(bits, 0)
        self.assertAlmostEqual(fl(g.u(g.c + 0x30)), -9.0, places=5)
        g.answers['terrain_heightBelow'] = lambda world, pos, radius: f32(0.0)
        self.assertEqual(g.model().move_by(g.c, (0, 0, 0)), 4)
        self.assertEqual(g.u(g.c + 0x18), 0)
        self.assertEqual(g.u(g.c + 0x30), 0)

    def test_random_point_uses_a_bit_mask(self):
        g = Game()
        g.answers['terrain_heightBelow'] = lambda world, pos, radius: f32(0.0)
        m = g.model()
        offsets = set()
        for _ in range(200):
            x, _y, _z = m.random_point_near_home(g.c, 300)
            offsets.add(int(fl(x) - 100.0))
        self.assertTrue(offsets <= {(v & 600) - 300 for v in range(1024)})
        self.assertLessEqual(len(offsets), 16)               # 600 has four bits set

    def test_filter_state(self):
        g = Game()
        m = g.model()
        self.assertEqual(m.filter_state(g.c, 3), (0, 3))
        g.mem.poke(g.c + 0x314, 2, 10)                       # rooted, no target
        self.assertEqual(m.filter_state(g.c, 3), (0, 0))
        self.assertEqual(m.filter_state(g.c, 7), (0, 7))
        g.mem.poke(g.c + 0x314, 2, 0)
        g.mem.poke(g.c + 0x31C, 2, 10)
        self.assertEqual(m.filter_state(g.c, 3), (0, 0x13))
        self.assertEqual(m.filter_state(g.c, 0x14), (0, 0x14))
        self.assertEqual(g.s16(g.c + 0x31C), 0)

    def test_default_slots(self):
        g = Game()
        m = g.model()
        m.vcall(g.c, 27, 9)
        self.assertEqual(g.s16(g.c + 0x232), 9)
        g.mem.poke(RC.G_LEVEL_MONSTER_LEVEL, 4, f32(30.0))
        self.assertEqual(m.vcall(g.c, 35), 8)                # int(30 x 0.29999998)
        g.answers['creature_bossRank'] = lambda c: 2
        self.assertEqual(g.model().vcall(g.c, 36), 10)

    def test_a_replaced_slot_is_a_callback(self):
        g = Game()
        g.mem.poke(g.table + 8 * 27 + 4, 4, 0x2A91B8)        # some subclass's set-state
        m = g.model()
        m.vcall(g.c, 27, 9)
        self.assertEqual(m.calls, [('Creature.v27', (g.c, 9))])
        self.assertEqual(g.s16(g.c + 0x232), 0)


if __name__ == '__main__':
    unittest.main()
