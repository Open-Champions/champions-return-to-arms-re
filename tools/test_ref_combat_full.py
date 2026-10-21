#!/usr/bin/env python3
"""Unit tests of tools/ref_combat_full.py that need no game files (they run in CI).

Every fixture is synthetic: actors placed by hand on an authored flat floor with authored
animation timelines.  The tests pin what the round-2 section of docs/combat-runtime.md
states about the composition of all round-2 bodies in one world: the merged tables have
no conflict, round 1's duel differs only where the real player tick adds work (the idle
fidget draw and regeneration), a walk touches in the mover's order, an armed combo, an
arrow and a burn each kill with round 1's delete-then-destroy timing, and every shared draw
of a tick belongs to one actor's run for a reason docs/spec/player-tick.md section 10
names.  Whether the bodies match the game is the business of the area difftests."""
import hashlib
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_ptick as PT                   # noqa: E402
import ref_combat_full as F                     # noqa: E402
import test_ref_combat_runtime as R1            # noqa: E402

f32 = T.f32
LCG = lambda s: (s * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF          # noqa: E731
PLANES = [((0.0, 0.0, -1000.0), (0.0, 0.0, 1.0))] * 4             # AUTHORED: everyone inside
WAVE = {0: (1, 10, 0.0), 1: (1, 20, 0.0)}                          # AUTHORED Wave of Flame statistics


def fl(bits):
    return C.to_float(bits)


def digest(rt):
    return hashlib.sha256(repr(rt.trace).encode() + repr(sorted(rt.mem.bytes.items())).encode()).hexdigest()


def duel(rt):
    """Round 1's duel set-up (test_ref_combat_runtime.test_duel_trace_is_stable)."""
    p = rt.spawn_player(0, (0.0, 0.0, 0.0), strength=40)
    s = rt.spawn_skelight((30.0, 0.0, 0.0), facing=0x8000, hp=40.0)
    R1.swing_clips(rt, s)
    return p, s


def run_duel(rt, hook=None):
    p, s = duel(rt)
    for t in range(80):
        if t == 30:
            rt.press_attack(0)
        rt.tick()
        if hook:
            hook(rt, p, s)
    return p, s


def player_draws(rt):
    """Shared draws of each player's slot 4, by frame (wraps round 1's driver)."""
    per = {}
    inner = rt.player_run

    def counted(P):
        before = rt.u32(T.G_RAND_SEED)
        inner(P)
        per[rt.u32(T.G_SIM_FRAME)] = PT.lcg_steps(before, rt.u32(T.G_RAND_SEED))
    rt.player_run = counted
    return per


def events(rt, start, *names):
    return [e for e in rt.trace[start:] if e[0] in names]


class Tables(unittest.TestCase):
    def test_every_area_reaches_the_one_model(self):
        owners = set(F.INTERNAL_OWNER.values()) | set(F.MODELLED_OWNER.values())
        self.assertEqual(owners, {'move', 'melee', 'defence', 'ranged', 'monsters', 'spells'})
        for name in ('Player_meleeHit', 'Player_pickAttackAnim', 'Player_processDamage', 'Player_takeDamage',
                     'Player_animStep', 'obj_moveAndCollide', 'creature_findPlayerInCone',
                     'world_collectObjectsInArc', 'Creature_dropLoot'):
            self.assertTrue(hasattr(F.FullModel, F.FULL_INTERNAL[name]), name)
        self.assertEqual(F.FULL_COMBAT_BODIES[0x1B5330], (2, 'player_take_damage_full'))

    def test_destructor_steps_stay_call_outs_of_the_shared_world(self):
        for name in F.KEPT_AS_CALL_OUTS:
            self.assertNotIn(name, F.FULL_INTERNAL)
        self.assertIsInstance(F.FullModel.DTORS, dict)
        self.assertEqual(F.FullModel.RANGED_DTORS, (0x151454, 0x3C6468))

    def test_the_two_water_helpers_are_told_apart(self):
        rt = F.FullRuntime()
        c = rt.spawn_skelight((0.0, 0.0, 0.0))
        rt.mem.poke(c + 0x2E8, 4, f32(100.0))               # a knock-back: Creature_moveBy -> _water(c)
        rt.model.apply_knockback(c, T.ONE)
        self.assertNotEqual(rt.u32(c + 0x10), f32(0.0))

    def test_type_names_are_one_form(self):
        rt = F.FullRuntime()
        for desc, name in F.TYPE_NAME.items():
            self.assertEqual(rt.model._cstr(rt.u32(desc), 64), name)
            self.assertTrue(name[:1].isdigit())

    def test_refuses_rather_than_invents(self):
        rt = F.FullRuntime()                                # no screen planes
        rt.spawn_player(0, (0.0, 0.0, 0.0))
        rt.spawn_player(1, (100.0, 0.0, 0.0))
        rt.stick(0, 1.0, 0.0)
        with self.assertRaises(T.Unsupported):              # the offline screen clamp needs the frustum
            rt.tick()


class RoundOneDuel(unittest.TestCase):
    """(a) Round 1's 80-tick duel in the full world."""

    def setUp(self):
        self.rt = F.FullRuntime()
        self.p, self.s = run_duel(self.rt)
        self.full = {f: d for f, d in self.rt.draws_by_player[self.p]}

    def test_extra_draws_are_the_idle_fidget_only(self):
        r1 = T.Runtime()
        per1 = player_draws(r1)
        run_duel(r1)
        extra = {f: self.full[f] - per1[f] for f in per1}
        self.assertEqual(set(extra.values()), {0, 1})
        # no fidget while the swing's fifth track plays (the swing starts at 30, its clip
        # lasts 20 ticks): docs/spec/player-tick.md 10 row 2
        self.assertEqual(sorted(f for f in extra if extra[f] == 0), list(range(31, 51)))

    def test_with_the_fidget_draws_round_one_rolls_the_same_hits(self):
        r1 = T.Runtime()
        per1 = player_draws(r1)
        run_duel(r1)
        fidget = {f for f in per1 if self.full[f] - per1[f] == 1}

        class WithFidget(T.Runtime):
            def player_run(self, P):                        # the fidget comes before Player_processDamage
                if self.u32(T.G_SIM_FRAME) in fidget:
                    self.mem.poke(T.G_RAND_SEED, 4, LCG(self.u32(T.G_RAND_SEED)))
                T.Runtime.player_run(self, P)
        r2 = WithFidget()
        p2, s2 = run_duel(r2)
        results = lambda rt: [e for e in rt.trace if e[0] in ('damage_apply', 'damage_result')]   # noqa: E731
        self.assertEqual(results(r2), results(self.rt))
        self.assertEqual(r2.u32(T.G_RAND_SEED), self.rt.u32(T.G_RAND_SEED))
        self.assertEqual(r2.u32(s2 + 0x228), self.rt.u32(self.s + 0x228))
        # the record differs by Player_regenHealth only (real tick, hp below the maximum:
        # 100 x 0.0001 = 0.01 per tick; docs/spec/player-tick.md 9.4)
        gap = fl(self.rt.u32(T.G_PLAYERS + 0xAC)) - fl(r2.u32(T.G_PLAYERS + 0xAC))
        self.assertAlmostEqual(gap, 0.01 * (80 - 12), delta=0.005)

    def test_differs_from_round_one_pin_and_equals_the_tick_runtime(self):
        self.assertNotEqual(self.rt.u32(T.G_RAND_SEED), R1.DUEL_SEED)
        tick = PT.TickRuntime()
        run_duel(tick)
        self.assertEqual(self.rt.u32(T.G_RAND_SEED), tick.u32(T.G_RAND_SEED))
        self.assertEqual([e for e in self.rt.trace if e[0] == 'damage_result'],
                         [e for e in tick.trace if e[0] == 'damage_result'])
        self.assertEqual(self.rt.u32(T.G_RAND_SEED), FULL_DUEL_SEED)
        self.assertEqual(digest(self.rt), FULL_DUEL_DIGEST)


class WalkAndCombo(unittest.TestCase):
    """(b) A player walks into a Skelight, then an armed combo kills it."""

    def test_touch_order_then_combo_kill_and_removal(self):
        rt = F.FullRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0), strength=40)
        rt.give_weapon(0, dmg=(30, 40), attack=50, dmg_type=8)
        s = rt.spawn_skelight((80.0, 0.0, 0.0), facing=0x8000, hp=120.0)
        R1.swing_clips(rt, s)
        rt.stick(0, 1.0, 0.0)
        touch = None
        for _ in range(40):
            mark = len(rt.model.vcalls)
            rt.tick()
            six = [c[1][:2] for c in rt.model.vcalls[mark:] if c[0] == 'Creature.v6']
            if six:
                touch = six
                break
        # obj_moveWithCollision: the other's slot 6 with the mover, then the mover's own
        self.assertEqual(touch[:2], [(s, p), (p, s)])
        self.assertTrue(rt.model.u64(s + 0xA8) & (1 << 59))           # Creature_onTouch: a player
        self.assertLessEqual(fl(rt.u32(p + 0x10)), 80.0 - 28.0 + 0.5)  # held off by the two radii
        rt.stick(0, 0.0, 0.0)
        variants, hit_tick, tick = set(), None, 0
        while s in rt.world.objects and tick < 200:
            if tick % 12 == 0:
                rt.press_attack(0)
            mark = len(rt.trace)
            rt.tick()
            variants.add(rt.model.s8(p + 0x461))
            hits = [e for e in events(rt, mark, 'damage_apply') if e[1] == s and e[2] == p]
            if hits:
                self.assertTrue(hits[0][4] & 8)                       # the weapon's damage bits
            if hits and fl(rt.u32(s + 0x228)) <= 0.0 and hit_tick is None:
                hit_tick = tick
            if events(rt, mark, 'obj_delete'):
                self.assertEqual(tick, hit_tick + 1)                  # its own run, the next tick
                self.assertIn(s, rt.world.objects)
            if events(rt, mark, 'destroy'):
                self.assertEqual(tick, hit_tick + 2)                  # the next flush
            tick += 1
        self.assertNotIn(s, rt.world.objects)
        self.assertGreaterEqual(len(variants - {0}), 2)               # Player_pickAttackAnim chose swings
        self.assertEqual(rt.u32(p + T.H_TARGET), 0)


class ArrowKill(unittest.TestCase):
    """(c) A player's arrow kills a creature."""

    def test_projectile_ends_in_its_own_run_creature_by_delete_then_flush(self):
        rt = F.FullRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        s = rt.spawn_skelight((150.0, 0.0, 0.0), facing=0x8000, hp=3.0)
        for _ in range(3):
            rt.tick()
        a = rt.spawn_missile(p, (20.0, 0.0, 36.0), (1000.0, 0.0, 0.0), dmin=4, dmax=8, attack=100000)
        seq = []
        for _ in range(12):
            mark = len(rt.trace)
            rt.tick()
            seq.append([e[:3] for e in events(rt, mark, 'run', 'damage_apply', 'obj_delete', 'destroy')
                        if e[1] in (a, s)])
            if a not in rt.world.objects:
                break
        hit = next(i for i, ev in enumerate(seq) if ('damage_apply', s, p) in ev)
        self.assertEqual(seq[hit][:4], [('run', a, 'missile'), ('damage_apply', s, p), ('run', s, 'skelight'),
                                        ('obj_delete', s)])
        self.assertEqual(seq[hit + 1], [('destroy', s, 'creature'), ('run', a, 'missile'),
                                        ('destroy', a, 'missile')])
        self.assertNotIn(s, rt.world.objects)
        self.assertEqual(rt.exp_awards, [(0, 0)])


class BurnKill(unittest.TestCase):
    """(d) A burn from Wave of Flame kills and credits the caster."""

    def test_burn_kill_credits_the_caster(self):
        rt = F.FullRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        rt.give_skill(95, WAVE)
        s = rt.spawn_skelight((60.0, 0.0, 0.0), hp=31.0)
        rt.queue_cast(p, 95, level=3)
        burns, credit = [], None
        for _ in range(160):
            mark = len(rt.trace)
            rt.tick()
            burns += [(rt.world.frame - 1, e) for e in events(rt, mark, 'damage_apply') if e[1] == e[2] == s]
            if events(rt, mark, 'obj_delete'):
                credit = rt.handle_target(s + T.H_LAST_ATTACKER)
            if s not in rt.world.objects:
                break
        self.assertNotIn(s, rt.world.objects)
        self.assertTrue(burns)
        self.assertTrue(all(frame % 32 == 0 and e[4] == 0x1180C040 for frame, e in burns))
        self.assertEqual(credit, p)                                   # 0x10000000: the status source
        self.assertEqual(rt.exp_awards, [(0, 0)])
        self.assertEqual(rt.attached(p), [])


class DrawAccounting(unittest.TestCase):
    """(e) Two players and two monsters: every shared draw of a tick is one actor's, and a
    player's are the reasons of docs/spec/player-tick.md section 10."""

    def test_every_draw_has_an_owner_and_a_reason(self):
        rt = F.FullRuntime(screen_planes=PLANES)
        p0 = rt.spawn_player(0, (0.0, 0.0, 0.0), strength=40)
        p1 = rt.spawn_player(1, (0.0, 120.0, 0.0), strength=40, idle_voice_limit=40)
        a = rt.spawn_skelight((30.0, 0.0, 0.0), facing=0x8000, hp=60.0)
        b = rt.spawn_skelight((30.0, 120.0, 0.0), facing=0x8000, hp=60.0)
        R1.swing_clips(rt, a)
        R1.swing_clips(rt, b)
        picks = []
        rt.plug('Player_pickAttackAnim', lambda P, cls: picks.append((P, rt.u32(T.G_SIM_FRAME)))
                or rt.model.pick_attack_anim(P, cls))
        log, inner = [], rt._slot4

        def slot4(obj):
            P = obj.addr
            before, mark = rt.u32(T.G_RAND_SEED), len(rt.trace)
            state = (rt.model.s8(P + 0x118), rt.u32(P + 0xC8), rt.model.s16(P + 0x4B2), rt.u32(T.G_SIM_FRAME))
            inner(obj)
            dmg = sum(len(e[3]) for e in rt.trace[mark:] if e[0] == 'damage_result')
            log.append((P, PT.lcg_steps(before, rt.u32(T.G_RAND_SEED), 10000), dmg, state,
                        rt.model.s16(P + 0x4B2)))
        rt.world.on_run = slot4
        reasons = {'fidget': 0, 'stagger': 0, 'voice': 0, 'pick': 0}
        for t in range(90):
            if t in (30, 55):
                rt.press_attack(0)
            before, n = rt.u32(T.G_RAND_SEED), len(log)
            rt.tick()
            self.assertEqual(PT.lcg_steps(before, rt.u32(T.G_RAND_SEED), 10000), sum(x[1] for x in log[n:]))
        for P, draws, dmg, (tracks, pending, limit, frame), limit_after in log:
            if P in (a, b):
                self.assertEqual(draws, dmg)                          # a monster's: its damage_apply only
                continue
            fid, stag, voice, pick = (tracks == 4), (pending != 0), (limit_after != limit), ((P, frame) in picks)
            self.assertEqual(draws - dmg, fid + stag + voice + pick, (P, frame))
            for key, on in (('fidget', fid), ('stagger', stag), ('voice', voice), ('pick', pick)):
                reasons[key] += on
        self.assertTrue(all(reasons.values()), reasons)


class MixedPin(unittest.TestCase):
    """(f) Self-pin of a 200-tick mixed scenario: two players (one walking and swinging an
    armed combo, one shooting and casting), two Skelights.  The digest was made by this
    model; it is evidence about the model only, not about the game."""

    def scenario(self):
        rt = F.FullRuntime(screen_planes=PLANES)
        p0 = rt.spawn_player(0, (0.0, 0.0, 0.0), strength=40)
        p1 = rt.spawn_player(1, (0.0, 150.0, 0.0), strength=30, idle_voice_limit=90)
        rt.give_weapon(0, dmg=(20, 30), attack=50, dmg_type=8)
        rt.give_skill(95, WAVE)
        a = rt.spawn_skelight((90.0, 0.0, 0.0), facing=0x8000, hp=90.0)
        b = rt.spawn_skelight((60.0, 150.0, 0.0), facing=0x8000, hp=40.0)
        R1.swing_clips(rt, a)
        R1.swing_clips(rt, b)
        for t in range(200):
            rt.stick(0, 1.0 if t < 25 else 0.0, 0.0)
            if t >= 30 and t % 12 == 0:
                rt.press_attack(0)
            if t == 10:
                rt.spawn_missile(p1, (20.0, 150.0, 36.0), (1000.0, 0.0, 0.0), dmin=4, dmax=8, attack=100000)
            if t == 60:
                rt.queue_cast(p1, 95, level=3)
            rt.tick()
        return rt, (p0, p1, a, b)

    def test_mixed_trace_is_stable(self):
        rt, (p0, p1, a, b) = self.scenario()
        self.assertNotIn(a, rt.world.objects)
        self.assertNotIn(b, rt.world.objects)
        self.assertIn(p0, rt.world.objects)
        self.assertEqual(rt.u32(T.G_RAND_SEED), MIXED_SEED)
        self.assertEqual(digest(rt), MIXED_DIGEST)


FULL_DUEL_SEED = 0xA2E1C5FE
FULL_DUEL_DIGEST = '73f3f49047e158f8975fed3afd27fa6ef361438357a19e98c619a64de02d5013'
MIXED_SEED = 0x7D6B07D5
MIXED_DIGEST = 'f3f95a27b2291796216f993d94b74205c4bb5639f514f87c327226369335dcb6'


if __name__ == '__main__':
    unittest.main()
