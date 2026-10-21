#!/usr/bin/env python3
"""Unit tests of tools/ref_combat_runtime.py that need no game files (they run in CI).

Every fixture is synthetic: actors placed by hand on an authored flat floor with an
authored animation timeline.  The tests pin the composition rules of
docs/combat-runtime.md - one memory, one handle pool, one shared seed, the run order,
when damage is applied and when it is reacted to, deferred deletion, the contact order -
and that anything outside the contract's domain is refused rather than guessed.  Whether
the bodies match the game is the business of the per-area differential tests and, for
the bodies first read for this contract, of a differential test still to be written."""
import hashlib
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_combat_runtime as T                  # noqa: E402

f32 = T.f32


def swing_clips(rt, c, length=30, hit=10):
    """Both Skelight swing clips (class definition +0x1c, +0x24): `length` ticks, the hit
    event (bit 1) on tick `hit`."""
    definition = rt.u32(c + 0x24)
    for off in (0x1C, 0x24):
        rt.anim.clips[rt.u32(definition + off)] = (length, {hit: 1})


def events(rt, start, kind):
    return [e for e in rt.trace[start:] if e[0] == kind]


def run_until(rt, predicate, limit=200):
    for _ in range(limit):
        mark = len(rt.trace)
        rt.tick()
        if predicate(rt, mark):
            return mark
    raise AssertionError('condition not reached in %d ticks' % limit)


class SharedImage(unittest.TestCase):
    def test_object_fields_are_the_bytes_of_the_image(self):
        rt = T.Runtime()
        c = rt.spawn_skelight((100.0, 50.0, 0.0))
        obj = rt.world.obj(c)
        self.assertEqual(obj.pos, [f32(100.0), f32(50.0), 0])
        rt.mem.poke(c + 0x10, 4, f32(700.0))
        self.assertEqual(obj.pos[0], f32(700.0))           # the object model sees the store
        rt.world.update_grid_cell(obj)
        lo, hi = [f32(600.0), f32(0.0), f32(-10.0)], [f32(800.0), f32(100.0), f32(10.0)]
        self.assertEqual(rt.world.collect_in_box(lo, hi, 16), [obj])

    def test_handle_words_read_the_node_pool_and_refuse_raw_stores(self):
        rt = T.Runtime()
        a = rt.spawn_skelight((0.0, 0.0, 0.0), team=1)
        b = rt.spawn_skelight((40.0, 0.0, 0.0), team=2)
        rt.svc_handle_link(a + T.H_TARGET, b, b)
        node = rt.u32(a + T.H_TARGET)
        self.assertTrue(T.SharedMemory.NODE_BASE <= node < rt.mem.node_end)
        self.assertEqual(rt.u32(node + 0xC), b)            # node +0xc is the object
        with self.assertRaises(T.CompositionError):
            rt.mem.poke(a + T.H_TARGET, 4, 0x1234)
        with self.assertRaises(T.CompositionError):
            rt.mem.poke(node + 0xC, 4, 0)

    def test_destroying_an_object_nulls_every_handle_to_it(self):
        rt = T.Runtime()
        a = rt.spawn_skelight((0.0, 0.0, 0.0), team=1)
        b = rt.spawn_skelight((40.0, 0.0, 0.0), team=2)
        rt.svc_handle_link(a + T.H_TARGET, b, b)
        rt.svc_handle_link(a + T.H_LAST_ATTACKER, b, b)
        rt.world.on_destroy(rt.world.obj(b), 3)
        self.assertEqual(rt.u32(a + T.H_TARGET), 0)
        self.assertEqual(rt.u32(a + T.H_LAST_ATTACKER), 0)
        with self.assertRaises(T.CompositionError):
            rt.world.obj(b)
        c = rt.spawn_skelight((80.0, 0.0, 0.0))
        self.assertEqual(c, b)                             # the freed block is handed out next

    def test_one_shared_seed_for_construction_and_damage(self):
        rt = T.Runtime()
        seed = C.Lcg(0)
        rt.spawn_player(0, (0.0, 0.0, 0.0))
        rt.spawn_skelight((30.0, 0.0, 0.0))
        seed.draw()
        seed.draw()                                        # one GameObject_ctor draw each
        self.assertEqual(rt.u32(T.G_RAND_SEED), seed.state)
        self.assertEqual(rt.rb.seed.state, seed.state)     # ref_combat's seed is the same word
        self.assertEqual(rt.world.shared.state, seed.state)


class RunOrder(unittest.TestCase):
    def test_the_last_linked_actor_runs_first(self):
        rt = T.Runtime()
        a = rt.spawn_skelight((0.0, 0.0, 0.0))
        b = rt.spawn_skelight((500.0, 0.0, 0.0))
        p = rt.spawn_player(0, (-500.0, 0.0, 0.0))
        rt.tick()
        order = [e[1] for e in rt.trace if e[0] == 'run']
        self.assertEqual(order, [p, b, a])

    def test_the_player_record_and_alive_list(self):
        rt = T.Runtime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0), hp=50.0)
        self.assertEqual(rt.u32(T.G_PLAYERS + T.REC_OBJ), p)
        self.assertEqual(rt.u32(T.G_ALIVE_COUNT), 1)
        rt.tick()
        self.assertEqual(rt.u32(p + 0x228), f32(50.0))      # object hit points mirror the record


class DamageTiming(unittest.TestCase):
    def duel(self, camera_mode=0):
        rt = T.Runtime(camera_mode=camera_mode)          # active by the camera focus (0, 0, 0)
        a = rt.spawn_skelight((0.0, 0.0, 0.0), facing=0, team=1, hp=60.0)
        b = rt.spawn_skelight((30.0, 0.0, 0.0), facing=0x8000, team=2, hp=60.0)
        swing_clips(rt, a)
        swing_clips(rt, b)
        return rt, a, b

    def test_hits_land_at_once_and_wait_for_the_victims_own_run(self):
        rt, a, b = self.duel()
        seen = {a: False, b: False}
        for _ in range(120):
            mark = len(rt.trace)
            rt.tick()
            for e in events(rt, mark, 'damage_result'):
                victim = e[1]
                if seen[victim] or not e[2]:
                    continue
                seen[victim] = True
                order = [x[1] for x in events(rt, mark, 'run')]
                victim_ran_before_hit = order.index(victim) < order.index(a if victim == b else b)
                pending = rt.u32(victim + 0xC8)
                if victim_ran_before_hit:
                    self.assertNotEqual(pending, 0)            # reacted to in the next tick
                    rt.tick()
                    self.assertEqual(rt.u32(victim + 0xC8), 0)
                else:
                    self.assertEqual(pending, 0)               # reacted to in this tick
                    self.assertTrue(rt.u32(victim + 0xC) & 0x100)
            if all(seen.values()):
                break
        self.assertTrue(all(seen.values()))

    def test_an_inactive_swing_never_lands(self):
        rt, a, b = self.duel(camera_mode=1)                # no player: no activity centre
        for _ in range(60):
            rt.tick()
        self.assertFalse([e for e in rt.trace if e[0] == 'damage_apply'])
        self.assertEqual(rt.model.s16(a + 0x232), 6)       # stuck in the swing: the clip never ends
        self.assertFalse(rt.model.u64(a + 0xA8) >> 63)

    def test_target_choice_follows_the_enemy_test(self):
        rt, a, b = self.duel()
        rt.tick()
        self.assertEqual(rt.handle_target(a + T.H_TARGET), b)
        self.assertEqual(rt.handle_target(b + T.H_TARGET), a)
        rt2 = T.Runtime()
        c = rt2.spawn_skelight((0.0, 0.0, 0.0), team=1)
        d = rt2.spawn_skelight((30.0, 0.0, 0.0), team=1)
        rt2.tick()
        self.assertEqual(rt2.handle_target(c + T.H_TARGET), 0)   # same team: no enemy
        self.assertEqual(rt2.handle_target(d + T.H_TARGET), 0)


class DeathAndRemoval(unittest.TestCase):
    def test_kill_delete_destroy_in_three_ticks(self):
        rt = T.Runtime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0), strength=40)
        s = rt.spawn_skelight((30.0, 0.0, 0.0), facing=0x8000, hp=1.0)
        swing_clips(rt, s)
        for _ in range(30):
            rt.tick()
        rt.press_attack(0)
        hit = run_until(rt, lambda r, m: any(e[1] == s and e[2] for e in events(r, m, 'damage_result')))
        self.assertTrue([e for e in events(rt, hit, 'damage_apply') if e[1] == s and e[2] == p])
        self.assertIn(s, rt.world.objects)
        mark = len(rt.trace)
        rt.tick()                                          # the Skelight's own run: death, obj_delete
        self.assertEqual(events(rt, mark, 'obj_delete'), [('obj_delete', s)])
        self.assertEqual(rt.u32(s + 0xC) & 9, 9)
        self.assertEqual(rt.model.s16(s + 0x232), 0x14)
        self.assertEqual(rt.exp_awards, [(0, 0)])
        found = rt.world.collect_in_box([f32(0.0), f32(-50.0), f32(-10.0)], [f32(60.0), f32(50.0), f32(10.0)], 16)
        self.assertIn(s, [o.addr for o in found])          # still in the grid until destroyed
        self.assertEqual(rt.handle_target(p + T.H_TARGET), s)
        mark = len(rt.trace)
        rt.tick()                                          # flushed at the start of runObjects
        self.assertEqual(events(rt, mark, 'destroy'), [('destroy', s, 'creature')])
        self.assertNotIn(s, rt.world.objects)
        self.assertEqual(rt.u32(p + T.H_TARGET), 0)

    def test_a_dead_player_stays_and_monsters_let_go(self):
        rt = T.Runtime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0), hp=1.0)
        s = rt.spawn_skelight((30.0, 0.0, 0.0), facing=0x8000, damage=(50, 60), attack=100000)
        swing_clips(rt, s)
        with self.assertRaises(T.Unsupported):             # every player dead: deathTask
            run_until(rt, lambda r, m: bool(events(r, m, 'player_dead')))
        self.assertIn(p, rt.world.objects)                 # never deleted
        self.assertEqual(rt.u32(p + 0x58C), 4)
        self.assertEqual(rt.u32(p + 0xC) & 9, 9)
        self.assertEqual(rt.u32(T.G_PLAYERS + 0xAC), 0)
        self.assertEqual(rt.u32(T.G_ALIVE_COUNT), 0)       # rebuilt at once, inside the tick


class PlayerServices(unittest.TestCase):
    def test_take_damage_only_accumulates(self):
        rt = T.Runtime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0), hp=100.0)
        s = rt.spawn_skelight((30.0, 0.0, 0.0))
        rt.model.player_take_damage(p, s, 8, f32(10.0))
        self.assertEqual(rt.u32(T.G_PLAYERS + 0xAC), f32(100.0))
        self.assertEqual(rt.u32(p + 0xC8), f32(10.0))
        self.assertEqual(rt.handle_target(p + T.H_LAST_ATTACKER), s)
        rt.model.player_take_damage(p, s, 8, f32(5.0))           # relinked on every hit
        self.assertEqual(rt.handle_target(p + T.H_LAST_ATTACKER), s)
        rt.mem.poke(T.G_PLAYERS + 0x4C27, 1, 3)              # hit immunity
        rt.model.player_take_damage(p, s, 8, f32(5.0))
        self.assertEqual(rt.u32(p + 0xC8), f32(15.0))

    def test_process_damage_draws_once_for_a_surviving_hit(self):
        rt = T.Runtime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0), hp=100.0)
        rt.model.player_take_damage(p, 0, 8, f32(10.0))
        before = rt.model.draws
        rt.model.player_process_damage(p)
        self.assertEqual(rt.model.draws - before, 1)       # the stagger roll (section E)
        self.assertEqual(rt.u32(T.G_PLAYERS + 0xAC), f32(90.0))
        self.assertEqual(rt.u32(p + 0xC8), 0)

    def test_find_target_skips_a_reject_and_keeps_walking(self):
        rt = T.Runtime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0), facing=0)
        ahead = rt.spawn_skelight((40.0, 0.0, 0.0))
        behind = rt.spawn_skelight((-40.0, 10.0, 0.0))
        order = rt.svc_world_collectObjectsInBox((f32(-60.0), f32(-60.0), f32(-72.0)),
                                                 (f32(60.0), f32(60.0), f32(72.0)), 0x100)
        self.assertLess(order.index(behind), order.index(ahead))       # the reject comes first
        rt.model.player_find_target(p, f32(60.0))
        self.assertEqual(rt.handle_target(p + T.H_TARGET), ahead)

    def test_find_target_lowest_score_and_cleared_when_nothing(self):
        rt = T.Runtime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0), facing=0)
        near = rt.spawn_skelight((20.0, 0.0, 0.0))
        rt.spawn_skelight((55.0, 0.0, 0.0))
        rt.model.player_find_target(p, f32(72.0))
        self.assertEqual(rt.handle_target(p + T.H_TARGET), near)
        rt.mem.poke(p + 0x38, 2, 0x8000)                                 # turn away: nothing in the cone
        rt.model.player_find_target(p, f32(72.0))
        self.assertEqual(rt.u32(p + T.H_TARGET), 0)


class Contacts(unittest.TestCase):
    def test_mover_contact_order(self):
        rt = T.Runtime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        s = rt.spawn_skelight((20.0, 0.0, 0.0))
        rt.model.vcalls[:] = []
        bits = rt.model.move_with_collision(p, (0, 0, 0), 0, 0)
        touches = [c for c in rt.model.vcalls if c[0] == 'Creature.v6']
        self.assertEqual(touches, [('Creature.v6', (s, p)), ('Creature.v6', (p, s))])
        self.assertTrue(bits & 2)                          # pushed out
        self.assertTrue(rt.model.u64(s + 0xA8) & (1 << 59))  # Creature_onTouch: touched by a player

    def test_prediction_copy_skips_the_other_handler(self):
        rt = T.Runtime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        s = rt.spawn_skelight((20.0, 0.0, 0.0))
        rt.mem.poke(p + 0xC, 4, rt.u32(p + 0xC) | T.F_PREDICTION_COPY)
        rt.model.vcalls[:] = []
        rt.model.move_with_collision(p, (0, 0, 0), 0, 0)
        touches = [c for c in rt.model.vcalls if c[0] == 'Creature.v6']
        self.assertEqual(touches, [('Creature.v6', (p, s))])
        self.assertFalse(rt.model.u64(s + 0xA8) & (1 << 59))

    def test_creature_touches_the_player(self):
        rt = T.Runtime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        s = rt.spawn_skelight((20.0, 0.0, 0.0))
        rt.model.vcalls[:] = []
        bits = rt.model.move_by(s, (0, 0, 0))
        self.assertTrue(bits & 2)
        self.assertIn(('Creature.v6', (p, s)), rt.model.vcalls)   # Player_onTouch: nothing outside state 9


class HitHelpers(unittest.TestCase):
    def test_hit_all_enemies_in_box_query_order(self):
        rt = T.Runtime()
        c = rt.spawn_skelight((0.0, 0.0, 0.0), facing=0, team=1)
        e1 = rt.spawn_skelight((30.0, 5.0, 0.0), team=2)
        e2 = rt.spawn_skelight((30.0, -5.0, 0.0), team=2)
        friend = rt.spawn_skelight((25.0, 0.0, 0.0), team=1)
        mark = len(rt.trace)
        hit = rt.model.hit_all_enemies_in_arc(c, 0, 0x2000, 4, 8, 100000, 8, 0, 0, f32(48.0))
        victims = [e[1] for e in events(rt, mark, 'damage_apply')]
        self.assertEqual(hit, 1)
        self.assertNotIn(friend, victims)
        box = [x for x in events(rt, mark, 'box')[0][1] if x in (e1, e2)]
        self.assertEqual(victims, box)

    def test_cone_search_has_no_hard_range(self):
        rt = T.Runtime()
        c = rt.spawn_skelight((0.0, 0.0, 0.0), facing=0, team=1)
        far = rt.spawn_skelight((60.0, 0.0, 0.0), team=2)
        found = rt.model.find_enemy_in_cone(c, 0, 0x2000, 0, f32(48.0))
        self.assertEqual(found, far)                       # beyond 48, inside the 1.4 x 48 box

    def test_can_see_obj_ray_modes(self):
        rt = T.Runtime()
        c = rt.spawn_skelight((0.0, 0.0, 0.0), facing=0)
        o = rt.spawn_skelight((30.0, 0.0, 0.0))
        masks = []
        rt.terrain.raycast = lambda origin, direction, mask, factor: masks.append(mask) or T.MISS
        self.assertEqual(rt.model.can_see_obj(c, o, 0, 0x2000, 0, 0, f32(48.0), 0), 1)
        self.assertEqual(rt.model.can_see_obj(c, o, 0, 0x2000, 1, 0, f32(48.0), 0), 1)
        self.assertEqual(masks, [3, 0])
        self.assertEqual(rt.model.can_see_obj(c, o, 0x8000, 0x2000, 0, 0, f32(48.0), 0), 0)   # behind


class Knockback(unittest.TestCase):
    def test_dust_uses_the_own_generator_only(self):
        rt = T.Runtime()
        c = rt.spawn_skelight((0.0, 0.0, 0.0), cflags=0)
        rt.mem.poke(c + 0x2E8, 4, f32(100.0))
        own, shared = rt.u32(c + 0x44), rt.u32(T.G_RAND_SEED)
        rt.model.apply_knockback(c, f32(0.7))
        self.assertNotEqual(rt.u32(c + 0x44), own)
        self.assertEqual(rt.u32(T.G_RAND_SEED), shared)
        self.assertEqual(rt.u32(c + 0x2E8), f32(98.0))
        self.assertGreater(rt.u32(c + 0x10), 0)            # pushed along +0x2e0 = 0 (+x)

    def test_a_dry_creature_raises_no_dust(self):
        rt = T.Runtime()
        c = rt.spawn_skelight((0.0, 0.0, 0.0))             # creature flag 0x100000
        rt.mem.poke(c + 0x2E8, 4, f32(100.0))
        own = rt.u32(c + 0x44)
        rt.model.apply_knockback(c, f32(0.7))
        self.assertEqual(rt.u32(c + 0x44), own)


class Refusals(unittest.TestCase):
    def test_outside_the_domain(self):
        rt = T.Runtime()
        rt.world.network_mode = 1
        with self.assertRaises(T.Unsupported):
            rt.tick()
        rt = T.Runtime()
        c = rt.spawn_skelight((0.0, 0.0, 0.0))
        with self.assertRaises(T.Unsupported):
            rt.svc_damage_apply(c, 0, 100000, 0, 0, 1, 0x4000, 0, f32(1.0), f32(2.0))   # a weapon item
        with self.assertRaises(T.Unsupported):
            rt.services.get('Holder.v17')(0, 1)
        with self.assertRaises(T.Unsupported):
            rt.rb.pool(0x98)                               # FlyingText

    def test_handle_link_to_a_non_object_is_refused(self):
        rt = T.Runtime()
        c = rt.spawn_skelight((0.0, 0.0, 0.0))
        with self.assertRaises(T.CompositionError):
            rt.svc_handle_link(c + T.H_LAST_ATTACKER, 0x123450, 0x123450)


class Regression(unittest.TestCase):
    def test_a_combo_needs_the_unread_attack_animation_choice(self):
        rt = T.Runtime()
        rt.spawn_player(0, (0.0, 0.0, 0.0))
        rt.spawn_skelight((300.0, 0.0, 0.0))
        for _ in range(25):
            rt.tick()
        rt.press_attack(0)
        rt.tick()
        with self.assertRaises(T.Unsupported):               # Player_pickAttackAnim: one shared draw
            for _ in range(30):
                rt.press_attack(0)
                rt.tick()

    def test_duel_trace_is_stable(self):
        """Self-pin of the composed duel (player against a Skelight, 80 ticks): any change
        to an executed model or to this module's bodies shows up here.  The digest was made
        by this model; it is not evidence about the game."""
        rt = T.Runtime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0), strength=40)
        s = rt.spawn_skelight((30.0, 0.0, 0.0), facing=0x8000, hp=40.0)
        swing_clips(rt, s)
        for t in range(80):
            if t == 30:
                rt.press_attack(0)
            rt.tick()
        digest = hashlib.sha256(repr(rt.trace).encode() + repr(sorted(rt.mem.bytes.items())).encode()).hexdigest()
        self.assertEqual(rt.u32(T.G_RAND_SEED), DUEL_SEED)
        self.assertEqual(digest, DUEL_DIGEST)
        self.assertIn(p, rt.world.objects)


DUEL_SEED = 0x60792ED2
DUEL_DIGEST = '82969d2a86f9313c01cf32b84c25eb6da17050993da0798502f523aed42d3d8d'


if __name__ == '__main__':
    unittest.main()
