#!/usr/bin/env python3
"""Synthetic-fixture tests of tools/ref_combat_ranged.py (no game files needed).

The fixtures (positions, hit points, damage ranges, flat floor) are authored; what the
tests check is the composed behaviour of the executed bodies: flight, lifetime, touch
order, the hit-once rule, damage timing, self-destruction and identity reuse."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_ranged as R                   # noqa: E402

f32 = C.f32


def fl(bits):
    return C.to_float(bits)


class StepTerrain(T.FlatTerrain):
    """A floor at z = 0 and a wall-high block (z = 500) for x beyond `wall`."""

    def __init__(self, wall):
        T.FlatTerrain.__init__(self)
        self.wall = wall

    def height_below(self, pos, radius):
        return f32(500.0) if C.lt(f32(self.wall), pos[0]) else 0


def events(rt, start, kinds):
    return [e for e in rt.trace[start:] if e[0] in kinds]


class Flight(unittest.TestCase):
    def test_arrow_moves_one_sixtieth_of_its_velocity_per_tick(self):
        rt = R.RangedRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        a = rt.spawn_missile(p, (0.0, 0.0, 36.0), (1200.0, 0.0, 0.0))
        rt.tick()
        x1 = fl(rt.mem.u32(a + 0x10))
        rt.tick()
        x2 = fl(rt.mem.u32(a + 0x10))
        self.assertAlmostEqual(x1, 20.0, places=3)
        self.assertAlmostEqual(x2 - x1, 20.0, places=3)
        self.assertEqual(rt.mem.u32(a + 0x18), f32(36.0))           # a MissileWeapon has no gravity

    def test_a_missile_that_hits_nothing_lives_300_frames(self):
        rt = R.RangedRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        start = rt.world.frame
        a = rt.spawn_missile(p, (0.0, 0.0, 36.0), (0.0, 100.0, 0.0))
        self.assertEqual(rt.mem.u32(a + 0xEC), start + 300)
        for _ in range(299):
            rt.tick()
        self.assertIn(a, rt.world.objects)
        rt.tick()                                                    # frame start + 299 -> not yet
        self.assertIn(a, rt.world.objects)
        n = len(rt.trace)
        rt.tick()                                                    # the run at frame start + 300 ends it
        self.assertNotIn(a, rt.world.objects)
        self.assertEqual(events(rt, n, ('destroy',))[0][1:], (a, 'missile'))

    def test_thrown_weapon_falls_and_is_destroyed_by_the_floor(self):
        rt = R.RangedRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        a = rt.spawn_thrown(p, (0.0, 0.0, 40.0), (600.0, 0.0, 0.0))
        rt.tick()
        self.assertEqual(rt.mem.u32(a + 0x1B8), C.sub(0, R.F_GRAVITY))     # vz -= 8.999999 before the move
        self.assertEqual(rt.model.u16(a + 0x1CC), (2000 + 3000) & 0xFFFF)   # kind 4 spins 3000 per frame
        ticks = 1
        while a in rt.world.objects and ticks < 200:
            rt.tick()
            ticks += 1
        self.assertNotIn(a, rt.world.objects)
        self.assertLess(ticks, 200)

    def test_terrain_hit_backs_off_and_destroys_in_the_same_run(self):
        rt = R.RangedRuntime(terrain=StepTerrain(100.0))
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        a = rt.spawn_missile(p, (95.0, 0.0, 36.0), (600.0, 0.0, 0.0))
        bits = []
        orig = rt.model.move_and_collide

        def spy(obj, vel):
            bits.append(orig(obj, vel))
            bits.append(fl(rt.mem.u32(obj + 0x10)))
            return bits[-2]
        rt.model.move_and_collide = spy
        rt.tick()
        self.assertEqual(bits[0] & 1, 1)
        self.assertLessEqual(bits[1], 100.0)                        # backed off in tenths of the step
        self.assertNotIn(a, rt.world.objects)


class Hits(unittest.TestCase):
    def setUp(self):
        self.rt = R.RangedRuntime()
        self.p = self.rt.spawn_player(0, (0.0, 0.0, 0.0))

    def test_player_arrow_damages_at_once_and_is_destroyed_next_tick(self):
        rt = self.rt
        s = rt.spawn_skelight((60.0, 0.0, 0.0), hp=100.0)
        a = rt.spawn_missile(self.p, (20.0, 0.0, 36.0), (1000.0, 0.0, 0.0), dmin=4, dmax=8, attack=100000)
        hit_tick = None
        for t in range(10):
            n = len(rt.trace)
            rt.tick()
            if events(rt, n, ('damage_apply',)):
                hit_tick = t
                self.assertLess(fl(rt.mem.u32(s + 0x228)), 100.0)    # creature hit points fall in the hit
                self.assertIn(a, rt.world.objects)                   # +0xec = frame + 1: alive this tick
                self.assertEqual(rt.model.u8(a + 0xCC), 1)
                break
        self.assertIsNotNone(hit_tick)
        n = len(rt.trace)
        rt.tick()
        self.assertNotIn(a, rt.world.objects)
        first = events(rt, n, ('run', 'destroy'))[:2]
        self.assertEqual(first, [('run', a, 'missile'), ('destroy', a, 'missile')])

    def test_monster_arrow_on_a_player_is_destroyed_in_the_same_run(self):
        rt = self.rt
        s = rt.spawn_skelight((200.0, 0.0, 0.0), damage=(3, 3), attack=100000)
        a = rt.spawn_missile(s, (40.0, 0.0, 36.0), (-1000.0, 0.0, 0.0), dmin=3, dmax=3, attack=100000)
        for _ in range(5):
            n = len(rt.trace)
            rt.tick()
            if events(rt, n, ('damage_apply',)):
                break
        seq = events(rt, n, ('run', 'damage_apply', 'destroy'))
        self.assertEqual(seq[0], ('run', a, 'missile'))
        self.assertEqual(seq[1][0], 'damage_apply')
        self.assertEqual(seq[2], ('destroy', a, 'missile'))
        self.assertNotIn(a, rt.world.objects)
        # the player took it as pending damage in the missile's run and, running after the
        # missile in the same tick, applied it to the record in its own Player_processDamage
        self.assertLess(fl(rt.mem.u32(T.G_PLAYERS + 0xAC)), 100.0)

    def test_touch_order_victim_first_then_the_missile(self):
        rt = self.rt
        s = rt.spawn_skelight((40.0, 0.0, 0.0))
        a = rt.spawn_missile(self.p, (30.0, 0.0, 36.0), (60.0, 0.0, 0.0))
        rt.model.vcalls = []
        rt.tick()
        touches = [v for v in rt.model.vcalls if v[0] == 'Creature.v6']
        self.assertEqual(touches[:2], [('Creature.v6', (s, a)), ('Creature.v6', (a, s))])

    def test_one_hit_per_missile_when_two_enemies_overlap(self):
        rt = self.rt
        s1 = rt.spawn_skelight((40.0, 0.0, 0.0))
        s2 = rt.spawn_skelight((40.0, 4.0, 0.0))
        a = rt.spawn_missile(self.p, (30.0, 0.0, 36.0), (60.0, 0.0, 0.0))
        n = len(rt.trace)
        rt.tick()
        hits = events(rt, n, ('damage_apply',))
        self.assertEqual(len(hits), 1)
        self.assertIn(hits[0][1], (s1, s2))
        del a

    def test_monster_arrow_passes_through_a_non_enemy(self):
        rt = self.rt
        shooter = rt.spawn_skelight((300.0, 0.0, 0.0))
        friend = rt.spawn_skelight((40.0, 0.0, 0.0))
        a = rt.spawn_missile(shooter, (50.0, 0.0, 36.0), (-60.0, 0.0, 0.0))
        n = len(rt.trace)
        rt.tick()
        self.assertEqual(events(rt, n, ('damage_apply',)), [])
        self.assertEqual(rt.model.u8(a + 0xCC), 0)
        self.assertIn(a, rt.world.objects)
        del friend

    def test_shared_draws_of_a_player_arrow_hit(self):
        rt = self.rt
        rt.spawn_skelight((40.0, 0.0, 0.0))
        before = rt.mem.u32(T.G_RAND_SEED)
        a = rt.spawn_missile(self.p, (30.0, 0.0, 36.0), (60.0, 0.0, 0.0), dmin=4, dmax=8, attack=100000)
        ctor = 1                                                     # GameObject_ctor
        mid = rt.mem.u32(T.G_RAND_SEED)
        self.assertEqual(mid, _advance(before, ctor))
        draws0 = rt.model.draws
        n = len(rt.trace)
        rt.tick()
        self.assertEqual(len(events(rt, n, ('damage_result',))), 1)
        missile_draws = rt.model.draws - draws0                      # Penetrating Arrows twice, deflection once
        self.assertEqual(missile_draws, 3)
        del a

    def test_destroyed_missile_block_is_reused_by_the_next_large_object(self):
        rt = self.rt
        rt.spawn_skelight((40.0, 0.0, 0.0))
        a = rt.spawn_missile(self.p, (30.0, 0.0, 36.0), (60.0, 0.0, 0.0))
        rt.tick()
        rt.tick()
        self.assertNotIn(a, rt.world.objects)
        s = rt.spawn_skelight((500.0, 0.0, 0.0))                     # a creature: same size class (0x500)
        self.assertEqual(s, a)

    def test_owner_handle_reads_zero_once_the_owner_is_destroyed(self):
        rt = self.rt
        shooter = rt.spawn_skelight((300.0, 300.0, 0.0))
        a = rt.spawn_missile(shooter, (0.0, 300.0, 36.0), (0.0, 10.0, 0.0))
        self.assertEqual(rt.model.handle_obj(a + 0x4C), shooter)
        rt._slot1(rt.world.obj(shooter), 3)
        self.assertEqual(rt.model.handle_obj(a + 0x4C), 0)
        s = rt.spawn_skelight((0.0, 310.0, 0.0))
        with self.assertRaises(T.Unsupported):                     # the missile would be its own attacker
            for _ in range(3):
                rt.tick()
        del s


def _advance(seed, n):
    for _ in range(n):
        seed = (seed * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
    return seed


class Bodies(unittest.TestCase):
    """The bodies on a bare memory image with recorded call-outs."""

    class Calls:
        def __init__(self, answers=None):
            self.log, self.answers = [], answers or {}

        def get(self, name):
            def fn(*args):
                self.log.append((name, args))
                a = self.answers.get(name)
                return a(*args) if callable(a) else (a if a is not None else 0)
            return fn

    def model(self, answers=None):
        cb = self.Calls(answers)
        return R.RangedModel(RC.Memory(), cb), cb

    def test_hit_state_stops_further_touches(self):
        m, cb = self.model()
        m.w8(0x1000 + 0xCC, 1)
        m.missile_on_touch(0x1000, 0x2000)
        self.assertEqual(cb.log, [])

    def test_pierced_list_skips_a_creature_already_hit(self):
        m, cb = self.model({'Creature.v20': 1})
        this, other, owner, node = 0x1000, 0x2000, 0x3000, 0x4000
        m.w32(other + 0xC, 0x20)
        m.w32(owner + 0xC, 0x20)
        m.w32(0x5000 + 0xC, owner)
        m.w32(this + 0x4C, 0x5000)
        m.w32(node + 0xC, other)
        m.w32(this + 0x124, node)
        m.w32(owner + 0x48, 0x6000)
        m.w32(0x6000 + 8 * 20 + 4, 0xDEAD)
        m.missile_on_touch(this, other)
        self.assertEqual([c[0] for c in cb.log], ['Creature.v20'])
        self.assertEqual(m.u8(this + 0xCC), 0)

    def test_non_creature_stops_the_missile_without_damage(self):
        m, cb = self.model({'Creature.v0': R.FAKE_DESC if hasattr(R, 'FAKE_DESC') else 0x7000})
        this, other = 0x1000, 0x2000
        m.w32(other + 0xC, 0x0)
        m.w32(other + 0x48, 0x6000)
        m.missile_on_touch(this, other)
        self.assertEqual(m.u8(this + 0xCC), 2)
        self.assertNotIn('damage_apply', [c[0] for c in cb.log])

    def test_move_and_collide_skips_owner_and_not_solid(self):
        m, cb = self.model()
        this, owner, ghost = 0x1000, 0x3000, 0x7000
        for o in (owner, ghost):
            m.w32(o + 0x1C, f32(12.0))
            m.w32(o + 0x20, f32(72.0))
        m.w32(ghost + 0xC, 0x201)
        m.w32(this + 0x1C, f32(12.0))
        m.w32(this + 0x20, f32(72.0))
        m.w32(0x5000 + 0xC, owner)
        m.w32(this + 0x4C, 0x5000)
        cb.answers['world_collectObjectsInBox'] = [owner, ghost, this]
        cb.answers['terrain_height'] = f32(-1000000.0)
        r = m.move_and_collide(this, (0, 0, 0))
        self.assertEqual(r, 0)
        self.assertEqual(m.vcalls, [])

    def test_nearest_sample_of_a_model_free_creature_is_zero(self):
        m, cb = self.model()
        other = 0x2000
        m.w32(other + 0x48, 0x6000)
        m.w32(0x6000 + 8 * 16 + 4, 0x3C2738)                         # Creature slot 16: class definition +0xc
        m.w32(other + 0x24, 0x8000)
        self.assertEqual(m.missile_nearest_sample(0x1000, other), 0)
        self.assertEqual(cb.log, [])

    def test_ctor_fields(self):
        m, cb = self.model({'trail_create': 0x82CD00})
        obj = 0x10000
        m.missile_ctor(obj, 0, 0xA, 0xB, (f32(1.0), f32(2.0), f32(3.0)), (f32(1000.0), 0, 0), 0x1234, 0, 0, 0,
                       4, 8, 0, 0, 100, 4, 0)
        self.assertEqual(m.u32(obj + 0x48), R.VT_MISSILE)
        self.assertEqual(m.u32(obj + 0xC) & 0x4081, 0x4081)
        self.assertEqual(m.u32(obj + 0x1C), f32(12.0))
        self.assertEqual(m.u32(obj + 0xEC), 300)
        self.assertEqual(m.u32(obj + 0x170), 0x82CD00)
        self.assertEqual([c[0] for c in cb.log][:2], ['GameObject_ctor', 'light_link'])
        self.assertIn(('obj_runEveryFrame', (obj,)), cb.log)


if __name__ == '__main__':
    unittest.main()
