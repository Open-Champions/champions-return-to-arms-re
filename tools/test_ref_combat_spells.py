#!/usr/bin/env python3
"""Unit tests of tools/ref_combat_spells.py that need no game files (they run in CI).

Section 1 (the victim finders and the radius damage) is tested on a synthetic memory
image with scripted call-outs; whether it matches the game is tools/difftest_combat_spells.py's
business.  Section 2 (spells in the shared world) is tested on authored fixtures: a flat
floor, hand-placed actors, Skill objects with AUTHORED statistics.  The tests pin the
composition rules of docs/spec/combat-spells.md - when a cast's objects first run, how
victims are found and ordered, how damage, burning and kill credit reach the victims, and
when the effects are destroyed."""
import hashlib
import os
import struct
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_spells as S                   # noqa: E402

f32 = T.f32


def fl(bits):
    return struct.unpack('<f', struct.pack('<I', bits & 0xFFFFFFFF))[0]


# =======================================================================================
# Section 1 on a synthetic image
# =======================================================================================

class Script:
    """Callbacks: the box query returns a fixed list; slot 20 answers from a set; the two
    list functions link real nodes in the image (as tools/ref_core.py HandlePool does)."""

    def __init__(self, mem, found, enemies=()):
        self.mem, self.found, self.enemies = mem, list(found), set(enemies)
        self.next_node = 0x9000
        self.damage = []

    def get(self, name):
        return getattr(self, 'cb_' + name.replace('.', '_'), None)

    def cb_world_collectObjectsInBox(self, low, high, limit):
        self.box = (low, high, limit)
        return list(self.found)

    def cb_Creature_v20(self, this, other):
        return 1 if other in self.enemies else 0

    def _node(self, obj):
        node, self.next_node = self.next_node, self.next_node + 0x20
        self.mem.poke(node + 0xC, 4, obj)
        self.mem.poke(node + 8, 4, 0)
        return node

    def cb_handle_insertNode(self, head, after, obj):
        node = self._node(obj)
        prev = after or head
        nxt = self.mem.load(prev, 4)
        self.mem.poke(node, 4, nxt)
        if nxt:
            self.mem.poke(nxt + 4, 4, node)
        self.mem.poke(node + 4, 4, prev)
        self.mem.poke(prev, 4, node)
        return node

    def cb_handle_addNode(self, head, obj):
        return self.cb_handle_insertNode(head, 0, obj)

    def cb_damage_apply(self, *args):
        self.damage.append(args)
        return 1


def image(objects):
    """objects: [(addr, x, y, flags, radius)] -> (memory, a model with no callbacks yet)."""
    mem = RC.Memory()
    table = 0x7000
    mem.poke(table + 8 * 20 + 4, 4, 0xF00020)           # slot 20: a call-out
    for addr, x, y, flags, radius in objects:
        mem.poke(addr + 0xC, 4, flags)
        mem.poke(addr + 0x10, 4, f32(x))
        mem.poke(addr + 0x14, 4, f32(y))
        mem.poke(addr + 0x1C, 4, f32(radius))
        mem.poke(addr + 0x48, 4, table)
    return mem


def model(mem, script):
    return S.QueryModel(mem, script)


ORIGIN = (f32(0.0), f32(0.0), f32(0.0))
OUT = 0x8000


class ArcQuery(unittest.TestCase):
    def objs(self, *pts, flags=0x20, radius=10.0):
        return [(0x1000 + 0x100 * i, x, y, flags, radius) for i, (x, y) in enumerate(pts)]

    def run_arc(self, objs, arc=-1.0, width=0.0, radius=300.0, filt=0, enemies=(), facing=0):
        mem = image(objs)
        script = Script(mem, [o[0] for o in objs], enemies)
        found = model(mem, script).collect_in_arc(ORIGIN, facing, OUT, filt, f32(radius), f32(arc), f32(width))
        return found, script

    def test_first_entry_is_the_nearest_and_the_rest_reverse_acceptance(self):
        objs = self.objs((50, 0), (20, 0), (80, 0), (30, 0), (90, 0))
        found, _ = self.run_arc(objs)
        a = [o[0] for o in objs]
        # accepted in box order 50, 20, 80, 30, 90: 20 is the nearest; every later one goes
        # right behind the first node
        self.assertEqual(found, [a[1], a[4], a[3], a[2], a[0]])

    def test_box_only_no_circular_range(self):
        objs = self.objs((290, 290))                    # 410 away, inside the 300 box
        found, script = self.run_arc(objs)
        self.assertEqual(found, [objs[0][0]])
        self.assertEqual(script.box[2], 0x200)

    def test_front_half_plane_is_strict_and_creatures_only(self):
        objs = self.objs((-1, 50), (-10, 5)) + [(0x1800, 40, 0, 0x0, 10.0), (0x1900, 40, 0, 0x28, 10.0)]
        found, _ = self.run_arc(objs)
        self.assertEqual(found, [])                     # behind the side line, behind, not a creature, dead

    def test_arc_and_width(self):
        objs = self.objs((100, 30), (100, 10))          # about 16.7 and 5.7 degrees off
        found, _ = self.run_arc(objs, arc=20.0)
        self.assertEqual(found, [objs[1][0]])
        found, _ = self.run_arc(objs, width=20.0)
        self.assertEqual(found, [objs[1][0]])

    def test_filter_is_the_filter_objects_slot_20(self):
        objs = self.objs((50, 0), (60, 0))
        found, _ = self.run_arc(objs, filt=objs[0][0], enemies={objs[1][0]})
        self.assertEqual(found, [objs[1][0]])

    def test_nodes_have_no_partner(self):
        objs = self.objs((50, 0))
        mem = image(objs)
        script = Script(mem, [objs[0][0]])
        model(mem, script).collect_in_arc(ORIGIN, 0, OUT, 0, f32(300.0), f32(-1.0), 0)
        self.assertEqual(mem.load(mem.load(OUT, 4) + 8, 4), 0)


class SphereQuery(unittest.TestCase):
    def test_any_class_reverse_box_order_three_d(self):
        objs = [(0x1000, 50, 0, 0x0, 10.0), (0x1100, 20, 0, 0x20, 10.0), (0x1200, 30, 0, 0x8, 10.0),
                (0x1300, 59.9, 0, 0x4081, 10.0)]
        mem = image(objs)
        mem.poke(0x1000 + 0x18, 4, f32(5.0))
        found = model(mem, Script(mem, [o[0] for o in objs])).collect_in_sphere(ORIGIN, 0, OUT, f32(50.0))
        self.assertEqual(found, [0x1100, 0x1000])       # dead and not-solid left out; front-linked


class RadiusDamage(unittest.TestCase):
    def setUp(self):
        self.objs = [(0x1000, 30, 40, 0x20, 10.0), (0x1100, 0, 90, 0x20, 12.0), (0x1200, 100, 100, 0x20, 0.0),
                     (0x1300, 20, 0, 0x28, 8.0), (0x1400, 10, 0, 0x40 | 0x20, 16.0)]

    def run_radius(self, attacker, most=50, least=5, skip=0, inner=0.0, outer=100.0, enemies=()):
        mem = image(self.objs)
        script = Script(mem, [o[0] for o in self.objs], enemies)
        hit = model(mem, script).damage_in_radius(attacker, ORIGIN, most, 0x40860, least, skip, f32(inner), f32(outer))
        return hit, script

    def test_a_monster_or_no_attacker_damages_everything_but_itself(self):
        hit, script = self.run_radius(0x1000)
        self.assertEqual(hit, [0x1100, 0x1300, 0x1400])  # the corpse too; (100, 100) is too far
        hit, _ = self.run_radius(0)
        self.assertEqual(hit, [0x1000, 0x1100, 0x1300, 0x1400])

    def test_a_player_attacker_asks_its_slot_20(self):
        hit, _ = self.run_radius(0x1400, enemies={0x1100})
        self.assertEqual(hit, [0x1100])

    def test_skip_flags(self):
        hit, _ = self.run_radius(0, skip=0x8)
        self.assertNotIn(0x1300, hit)

    def test_octagon_distance_slope_least_and_most(self):
        hit, script = self.run_radius(0, most=50, least=5, inner=0.0, outer=100.0)
        amounts = {args[0]: fl(args[8]) for args in script.damage}
        # k = 50 / 100.  (30, 40) r 10: 70 - 30 x 0.33299 - 10 = 50.01 -> 24.99 -> 24
        self.assertEqual(amounts[0x1000], 24.0)
        self.assertEqual(amounts[0x1100], 11.0)          # (0, 90) r 12: 78 -> 11
        self.assertEqual(amounts[0x1300], 44.0)          # the corpse (20, 0) r 8: 12 -> 44
        self.assertEqual(amounts[0x1400], 50.0)          # 10 - 16 < 0 -> 53, capped at `most`
        hit, script = self.run_radius(0, most=50, least=30)
        self.assertEqual(fl(script.damage[1][8]), 30.0)  # raised to `least`

    def test_span_of_one_or_less_means_slope_100(self):
        hit, script = self.run_radius(0, most=50, least=0, inner=99.5, outer=100.0)
        self.assertTrue(all(fl(a[8]) == 50.0 for a in script.damage))


# =======================================================================================
# Section 2: spells in the shared world (AUTHORED fixtures)
# =======================================================================================

STATS = {16: {0: (1, 10, 0.0), 1: (1, 20, 0.0), 2: (1, 5, 0.0)},
         57: {0: (1, 10, 0.0), 1: (1, 6, 0.0), 2: (1, 5, 0.0), 3: (1, 300, 0.0)},
         95: {0: (1, 10, 0.0), 1: (1, 20, 0.0)}}


def world():
    rt = S.SpellRuntime()
    p = rt.spawn_player(0, (0.0, 0.0, 0.0))
    for skill_id, stats in STATS.items():
        rt.give_skill(skill_id, stats)
    return rt, p


def effects(rt):
    return sorted(a for a in rt.world.objects if rt.kinds.get(a) == 'effect')


def kinds(rt, start, *names):
    return [e for e in rt.trace[start:] if e[0] in names]


class CastTiming(unittest.TestCase):
    def test_a_projectile_first_runs_in_the_next_tick_and_runs_first(self):
        rt, p = world()
        s = rt.spawn_skelight((120.0, 0.0, 0.0))
        rt.queue_cast(p, 16, level=3)
        mark = len(rt.trace)
        rt.tick()
        runs = [e[1] for e in kinds(rt, mark, 'run')]
        (bolt,) = effects(rt)
        self.assertEqual(runs, [s, p])                  # made in p's run, at the front: not run
        mark = len(rt.trace)
        rt.tick()
        self.assertEqual([e[1] for e in kinds(rt, mark, 'run')][:1], [bolt])

    def test_an_attached_spell_runs_in_the_casters_tail_in_the_same_tick(self):
        rt, p = world()
        rt.spawn_skelight((60.0, 0.0, 0.0))
        rt.queue_cast(p, 95, level=3)
        mark = len(rt.trace)
        rt.tick()
        order = [e[0] for e in kinds(rt, mark, 'cast', 'light', 'sphere', 'player_spells')]
        self.assertEqual(order, ['cast', 'light', 'sphere', 'player_spells'])
        self.assertEqual(len(rt.attached(p)), 1)

    def test_the_constructors_draw_the_shared_seed(self):
        rt, p = world()
        rt.queue_cast(p, 95, level=3)
        before = rt.u32(T.G_RAND_SEED)
        rt.tick()
        s = before
        for _ in range(2):                              # the spell's own seed, the light's GameObject_ctor
            s = (s * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF
        self.assertEqual(rt.u32(T.G_RAND_SEED), s)


class HolyStrike(unittest.TestCase):
    def test_one_hit_from_the_owner_then_destroyed_at_once(self):
        rt, p = world()
        s = rt.spawn_skelight((120.0, 0.0, 0.0), hp=100.0)
        rt.queue_cast(p, 16, level=3)
        rt.tick()
        (bolt,) = effects(rt)
        for _ in range(30):
            mark = len(rt.trace)
            rt.tick()
            hits = kinds(rt, mark, 'damage_apply')
            if hits:
                break
        self.assertEqual(hits, [('damage_apply', s, p, 100000, 0x80000)])   # the owner, knock-back class
        self.assertNotIn(bolt, rt.world.objects)        # slot 1 with 3 inside its own run, no delete list
        destroyed = [e[2] for e in kinds(rt, mark, 'destroy')]
        self.assertEqual(destroyed, ['HolyStrike_dtor'])
        (light,) = effects(rt)                          # the LightEffect of the end (life 1.0: 60 frames)
        self.assertEqual(rt.u32(light + 0xC) & 3, 3)
        for _ in range(60):
            rt.tick()
        self.assertEqual(effects(rt), [])

    def test_the_candidate_list_outlives_its_target(self):
        rt, p = world()
        near = rt.spawn_skelight((100.0, -40.0, 0.0))
        rt.spawn_skelight((250.0, 0.0, 0.0))
        rt.queue_cast(p, 16, level=3)
        rt.tick()
        (bolt,) = effects(rt)
        first = rt.u32(rt.u32(bolt + 0x58) + 0xC)
        self.assertEqual(first, near)                   # nearest enemy first
        rt.svc_obj_delete(near)
        rt.tick()                                       # destroyed in the flush
        self.assertNotIn(near, rt.world.objects)
        self.assertEqual(rt.u32(rt.u32(bolt + 0x58) + 0xC), near)          # the node has no partner
        reborn = rt.spawn_skelight((0.0, 200.0, 0.0))   # the pool hands the block out again
        self.assertEqual(reborn, near)
        for _ in range(30):
            rt.tick()
        self.assertGreater(fl(rt.u32(bolt + 0x14)), 60.0)                  # it turned toward the newcomer


class WaveOfFlame(unittest.TestCase):
    def test_cast_time_candidates_hit_once_burn_and_credit_the_caster(self):
        rt, p = world()
        s = rt.spawn_skelight((60.0, 0.0, 0.0), hp=200.0)
        rt.queue_cast(p, 95, level=3)
        rt.tick()
        late = rt.spawn_skelight((0.0, 60.0, 0.0), hp=200.0)               # inside the ring, after the cast
        direct, burns = [], []
        for _ in range(140):
            mark = len(rt.trace)
            rt.tick()
            for e in kinds(rt, mark, 'damage_apply'):
                (burns if e[2] == e[1] else direct).append((rt.world.frame - 1, e))
        self.assertEqual([e for _, e in direct], [('damage_apply', s, p, 100000, 0x160)])
        self.assertTrue(burns)
        self.assertTrue(all(frame % 32 == 0 and e[4] == 0x1180C040 and e[1] == s for frame, e in burns))
        self.assertEqual(rt.handle_target(s + 0x360), p)                    # status source
        self.assertEqual(rt.handle_target(s + 0x2E4), p)                    # kill credit via 0x10000000
        self.assertEqual(fl(rt.u32(late + 0x228)), 200.0)
        self.assertEqual(rt.attached(p), [])                                 # the spell ended itself

    def test_a_burning_kill_gives_the_experience(self):
        rt, p = world()
        s = rt.spawn_skelight((60.0, 0.0, 0.0), hp=31.0)
        rt.queue_cast(p, 95, level=3)
        for _ in range(140):
            rt.tick()
            if s not in rt.world.objects:
                break
        self.assertNotIn(s, rt.world.objects)
        self.assertTrue(rt.exp_awards)


class ShockOfFire(unittest.TestCase):
    def test_a_players_burst_hits_only_its_enemies(self):
        rt, p = world()
        a = rt.spawn_skelight((120.0, 0.0, 0.0), hp=100.0)
        b = rt.spawn_skelight((140.0, -30.0, 0.0), hp=100.0)
        rt.queue_cast(p, 57, level=3)
        hits = []
        for _ in range(30):
            mark = len(rt.trace)
            rt.tick()
            hits += kinds(rt, mark, 'damage_apply')
        direct = [e for e in hits if e[3] == 10000000]
        burst = [e for e in hits if e[4] == 0x40860]
        self.assertEqual([e[1] for e in direct], [a])                       # the touch: first enemy only
        self.assertEqual(sorted(e[1] for e in burst), sorted([a, b]))
        self.assertTrue(all(e[2] == p for e in direct + burst))

    def test_a_monsters_burst_hits_everything_in_the_box(self):
        rt, p = world()
        rt.mem.poke(p + 0x10, 4, f32(10.0))
        caster = rt.spawn_skelight((0.0, 100.0, 0.0), hp=100.0, facing=0xC000)
        other = rt.spawn_skelight((0.0, 40.0, 0.0), hp=100.0)
        rt.queue_cast(caster, 57, level=3)
        burst = []
        for _ in range(30):
            mark = len(rt.trace)
            rt.tick()
            burst += [e for e in kinds(rt, mark, 'damage_apply') if e[4] == 0x40860]
        victims = [e[1] for e in burst]
        self.assertIn(other, victims)                   # another monster
        self.assertIn(p, victims)
        nonliving = [v for v in victims if v not in (other, p)]
        self.assertEqual(len(nonliving), 2)             # the LightEffect and the Sparks itself
        results = [e for e in rt.trace if e[0] == 'damage_result' and e[1] in nonliving]
        self.assertTrue(all(len(e[3]) == 1 for e in results))               # one shared draw each


class Refusals(unittest.TestCase):
    def test_a_victim_with_a_spell_damage_apply_asks_about(self):
        rt, p = world()
        s = rt.spawn_skelight((60.0, 0.0, 0.0))
        spell = rt.svc_pool_new(0x2C)
        table = 0x00012000
        rt.mem.poke(table + 4, 4, 0x3D0A00)              # the BloodLust getter
        rt.mem.poke(spell + 0x14, 4, table)
        rt.svc_creature_addSpell(s, spell)
        with self.assertRaises(T.Unsupported):
            rt.live(s).spells


class SelfPin(unittest.TestCase):
    """Evidence about the MODEL only (a change detector for whoever ports it): three
    casts at three Skelights over 150 ticks."""

    def test_three_spell_trace_is_stable(self):
        rt, p = world()
        rt.spawn_skelight((60.0, 0.0, 0.0), hp=60.0)
        rt.spawn_skelight((140.0, -20.0, 0.0), hp=60.0)
        rt.spawn_skelight((-80.0, 50.0, 0.0), hp=60.0)
        rt.queue_cast(p, 95, level=3)
        for t in range(150):
            if t == 20:
                rt.queue_cast(p, 16, level=3)
            if t == 40:
                rt.queue_cast(p, 57, level=3)
            rt.tick()
        keep = ('cast', 'pool_new', 'arc', 'sphere', 'damage_apply', 'damage_result', 'destroy', 'destroy_spell',
                'light', 'run')
        text = repr([e for e in rt.trace if e[0] in keep]) + repr(rt.u32(T.G_RAND_SEED))
        self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),
                         'a62693589f31b6c76a15211b17bd20f79442e9106ea78fed3b9bc4a7bf63d3dd')


if __name__ == '__main__':
    unittest.main()
