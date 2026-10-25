#!/usr/bin/env python3
"""Unit tests of tools/ref_combat_ptick.py that need no game files (they run in CI).

Every fixture is synthetic: actors placed by hand on an authored flat floor with an
authored animation timeline (ref_combat_ptick.PlayerAnim for players).  The tests pin
what docs/spec/combat-player-defence.md states about the composition: the defence bodies
keep round 1's behaviour on round 1's domain, a block from the front zeroes or halves the
hit and walks the player's own seed, the knock-down picks its clip by bearing, and the
real player tick makes the shared-seed draws of docs/spec/player-tick.md section 10 that
round 1's authored driver left out.  Whether the bodies match the game is the business of
tools/difftest_combat_ptick.py (and tools/difftest_player.py for the tick)."""
import hashlib
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_ptick as PT                   # noqa: E402

K1, K2 = PT.KNOCKDOWN_PREFIX[False], PT.KNOCKDOWN_PREFIX[True]
import test_ref_combat_runtime as R1            # noqa: E402

f32 = T.f32
LCG = lambda s: (s * 0x19660D + 0x3C6EF35F) & 0xFFFFFFFF          # noqa: E731


def duel(rt, voice=0x7FFF):
    p = rt.spawn_player(0, (0.0, 0.0, 0.0), strength=40, idle_voice_limit=voice) \
        if isinstance(rt, PT.TickRuntime) else rt.spawn_player(0, (0.0, 0.0, 0.0), strength=40)
    s = rt.spawn_skelight((30.0, 0.0, 0.0), facing=0x8000, hp=40.0)
    R1.swing_clips(rt, s)
    return p, s


def presentation(rt, start, name):
    return [e for e in rt.trace[start:] if e == ('presentation', name)]


class DefenceKeepsRoundOne(unittest.TestCase):
    def test_round_one_duel_pin_with_the_defence_model(self):
        """Round 1's Runtime with DefenceModel in place of CombatModel reproduces round 1's
        80-tick self-pin: the _full bodies agree with round 1's on its domain."""
        rt = T.Runtime()
        rt.model = PT.DefenceModel(rt.mem, rt.services)
        p, s = duel(rt)
        for t in range(80):
            if t == 30:
                rt.press_attack(0)
            rt.tick()
        digest = hashlib.sha256(repr(rt.trace).encode() + repr(sorted(rt.mem.bytes.items())).encode()).hexdigest()
        self.assertEqual(rt.u32(T.G_RAND_SEED), R1.DUEL_SEED)
        self.assertEqual(digest, R1.DUEL_DIGEST)

    def test_round_one_runtime_is_unchanged(self):
        rt = T.Runtime()
        self.assertIs(type(rt.model), T.CombatModel)
        self.assertEqual(rt.model.COMBAT_BODIES[0x1B5330], (2, 'player_take_damage'))


class Blocking(unittest.TestCase):
    def setUp(self):
        self.rt = rt = PT.TickRuntime()
        self.p = rt.spawn_player(0, (0.0, 0.0, 0.0), facing=0)
        self.s = rt.spawn_skelight((30.0, 0.0, 0.0), facing=0x8000)
        rt.mem.poke(self.p + 0x58C, 4, 8)                     # blocking

    def hit(self, flags=8, amount=10.0):
        rt = self.rt
        mark, seed, own = len(rt.trace), rt.u32(T.G_RAND_SEED), rt.u32(self.p + 0x44)
        rt.model.vcall(self.p, 2, self.s, flags, f32(amount))
        return mark, seed, own

    def test_a_block_from_the_front_zeroes_the_hit_and_walks_the_own_seed(self):
        mark, seed, own = self.hit()
        rt = self.rt
        self.assertEqual(rt.u32(self.p + 0xC8), 0)               # pending + 0
        self.assertEqual(rt.u32(T.G_RAND_SEED), LCG(seed))       # one shared draw: the clip choice
        self.assertEqual(len(presentation(rt, mark, 'particle_spawn')), 50)
        self.assertGreaterEqual(PT.lcg_steps(own, rt.u32(self.p + 0x44)), 150)
        self.assertEqual(len([e for e in rt.trace[mark:] if e[:2] == ('anim', 'blend')]), 1)
        self.assertEqual(rt.handle_target(self.p + T.H_LAST_ATTACKER), self.s)      # still the attacker

    def test_flag_0x20000_halves_a_blocked_hit(self):
        self.hit(flags=0x20008, amount=10.0)
        self.assertEqual(self.rt.u32(self.p + 0xC8), f32(5.0))

    def test_a_block_from_behind_changes_nothing_but_the_clip(self):
        self.rt.mem.poke(self.p + 0x38, 2, 0x8000)
        mark, seed, own = self.hit()
        rt = self.rt
        self.assertEqual(rt.u32(self.p + 0xC8), f32(10.0))
        self.assertEqual(rt.u32(T.G_RAND_SEED), LCG(seed))
        self.assertEqual(rt.u32(self.p + 0x44), own)
        self.assertFalse(presentation(rt, mark, 'particle_spawn'))

    def test_the_block_move_makes_no_shared_draw(self):
        self.rt.mem.poke(self.p + 0x58C, 4, 0xB)
        mark, seed, own = self.hit()
        self.assertEqual(self.rt.u32(T.G_RAND_SEED), seed)
        self.assertEqual(self.rt.u32(self.p + 0xC8), 0)

    def test_flag_0x40_is_not_blocked(self):
        self.hit(flags=0x48)
        self.assertEqual(self.rt.u32(self.p + 0xC8), f32(10.0))

    def test_holy_shield_pays_from_mana(self):
        rt, p = self.rt, self.p
        rt.mem.poke(p + 0x58C, 4, 2)
        R = T.G_PLAYERS
        rt.mem.poke(R + 0xC0, 4, f32(3.0))
        rt.plug('creature_findSpellByType', lambda c, t: 0x5000 if t == 0x3CF124 else 0)
        rt.plug('SpellHolyShield_absorb', lambda spell: f32(0.5))
        rt.model.vcall(p, 2, self.s, 8, f32(10.0))
        self.assertEqual(rt.u32(p + 0xC8), f32(5.0))
        self.assertEqual(rt.u32(R + 0xC0), 0)                    # 3 - 5, floored at 0


class KnockDown(unittest.TestCase):
    def test_clip_names_by_bearing(self):
        self.assertEqual(PT.knockdown_name(5, 0), K1 + b'b.anm')
        self.assertEqual(PT.knockdown_name(2, 0x7000), K2 + b'a.anm')
        self.assertEqual(PT.knockdown_name(3, -0x6000), K2 + b'a.anm')
        self.assertEqual(PT.knockdown_name(1, -0x5FFF), K1 + b'c.anm')
        self.assertEqual(PT.knockdown_name(0, -0x2000), K1 + b'c.anm')
        self.assertEqual(PT.knockdown_name(4, -0x1FFF), K1 + b'b.anm')
        self.assertEqual(PT.knockdown_name(7, 0x2000), K1 + b'b.anm')
        self.assertEqual(PT.knockdown_name(6, 0x2001), K1 + b'd.anm')
        self.assertEqual(PT.knockdown_name(5, 0x5FFF), K1 + b'd.anm')

    def setUp(self):
        self.rt = rt = PT.TickRuntime(skill_stat=lambda name, *a: 0)
        self.p = rt.spawn_player(0, (0.0, 0.0, 0.0), facing=0)
        self.s = rt.spawn_skelight((-30.0, 0.0, 0.0))

    def test_a_heavy_knock_back_class_knocks_down(self):
        rt, p = self.rt, self.p
        rt.model.vcall(p, 2, self.s, 0x80008, f32(5.0))          # attacker behind: bearing 'b'
        mark, seed = len(rt.trace), rt.u32(T.G_RAND_SEED)
        rt.model.player_process_damage_full(p)
        self.assertEqual(rt.model.s32(p + 0x58C), 3)
        self.assertEqual(rt.u32(p + 0x2E8), f32(150.0))
        token = rt.svc_res_find(0, K1 + b'b.anm')
        self.assertIn(('anim', 'blend', p + 0x114, token, 0x80A), rt.trace[mark:])
        # the Strong Stance roll only: the knock-down set action state 3, so no stagger roll (E)
        self.assertEqual(PT.lcg_steps(seed, rt.u32(T.G_RAND_SEED)), 1)

    def test_a_knock_down_already_playing_is_not_restarted(self):
        rt, p = self.rt, self.p
        token = rt.svc_res_find(0, K1 + b'b.anm')
        rt.anim.start(rt.mem, p + 0x114, token, 0)
        rt.model.vcall(p, 2, self.s, 0x80008, f32(5.0))
        mark = len(rt.trace)
        rt.model.player_process_damage_full(p)
        self.assertFalse([e for e in rt.trace[mark:] if e[:2] == ('anim', 'blend')])

    def test_a_resisted_knock_down_calls_strong_stance(self):
        rt = PT.TickRuntime(skill_stat=lambda name, *a: 100)     # always resists
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        s = rt.spawn_skelight((-30.0, 0.0, 0.0))
        rt.model.vcall(p, 2, s, 0x100008, f32(5.0))
        with self.assertRaises(T.Unsupported):                  # SkillStrongStance_trigger: objects
            rt.model.player_process_damage_full(p)
        calls = []
        rt.plug('SkillStrongStance_trigger', lambda *a: calls.append(a))
        rt.model.vcall(p, 2, s, 0x100008, f32(5.0))
        rt.model.player_process_damage_full(p)
        self.assertEqual(calls[0][2], K1 + b'b.anm')
        self.assertEqual(calls[0][3], 200)
        self.assertEqual(rt.u32(p + 0x2E8), 0)

    def test_blood_draws_once_and_a_gut_chunk_is_refused(self):
        rt, p = self.rt, self.p
        rt.mem.poke(T.G_DECAL_DETAIL, 4, 1)
        refused = 0
        for k in range(64):
            rt.mem.poke(p + 0x58C, 4, 2)
            rt.model.vcall(p, 2, self.s, 8, f32(1.0))
            seed = rt.u32(T.G_RAND_SEED)
            try:
                rt.model.player_process_damage_full(p)
            except T.Unsupported:
                refused += 1
                self.assertEqual(LCG(seed) >> 16 & 7, 0)
                rt.mem.poke(p + 0xC8, 4, 0)
                rt.mem.poke(p + 0x2DC, 4, 0)
                continue
            self.assertEqual(PT.lcg_steps(seed, rt.u32(T.G_RAND_SEED)), 2)    # blood roll, stagger roll
        self.assertGreater(refused, 0)


class RealTick(unittest.TestCase):
    def test_a_standing_player_draws_once_per_tick_for_the_fidget(self):
        rt = PT.TickRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        for _ in range(20):
            rt.tick()
        self.assertEqual([d for _f, d in rt.draws_by_player[p]], [1] * 20)
        self.assertEqual(rt.model.s8(p + 0x118), 4)

    def test_the_idle_voice_draws_when_its_counter_passes_the_limit(self):
        rt = PT.TickRuntime()
        p = rt.spawn_player(1, (0.0, 0.0, 0.0), idle_voice_limit=5)    # slot 1 alone (no screen clamp)
        for _ in range(8):
            rt.tick()
        draws = [d for _f, d in rt.draws_by_player[p]]
        self.assertEqual(draws, [1, 1, 1, 1, 1, 2, 1, 1])
        limit = rt.model.s16(p + 0x4B2)
        self.assertEqual((limit - 0xE10) % 60, 0)
        self.assertEqual((limit - 0xE10) // 60 - 45, ((limit - 0xE10) // 60 - 45) % 30)    # (d % 30) + slot x 45

    def test_a_swing_track_stops_the_fidget_draw(self):
        rt = PT.TickRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        for t in range(32):
            if t == 25:                                        # 20 frames (+0x48c x 60) since spawning
                rt.press_attack(0)
            rt.tick()
        draws = [d for _f, d in rt.draws_by_player[p]]
        self.assertEqual(draws[:25], [1] * 25)
        self.assertEqual(draws[26:], [0] * 6)                  # five tracks while the swing plays
        self.assertEqual(rt.model.s8(p + 0x118), 5)

    def test_plugged_call_outs_answer_the_tick(self):
        rt = PT.TickRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        seen = []
        original = rt.model.player_move
        rt.plug('Player_move', lambda P, mode, pad, ext: seen.append(mode) or original(P, mode, pad, ext))
        rt.tick()
        self.assertEqual(seen, [0])

    def test_the_combo_choice_is_refused_until_plugged(self):
        rt = PT.TickRuntime()
        p, s = duel(rt)
        for _ in range(25):
            rt.tick()
        with self.assertRaises(T.Unsupported):
            for _ in range(40):
                rt.press_attack(0)
                rt.tick()
        rt = PT.TickRuntime()
        p, s = duel(rt)
        picks = []

        def pick(P, cls):
            picks.append(cls)
            rt.model.draw()                                    # its one shared draw (difftest_player 9.10)
        rt.plug('Player_pickAttackAnim', pick)
        for _ in range(25):
            rt.tick()
        for _ in range(40):
            rt.press_attack(0)
            rt.tick()
        self.assertTrue(picks)

    def test_the_interaction_prompt_decays_by_seven(self):
        rt = PT.TickRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        rt.mem.poke(PT.G_PROMPT_TIMER, 4, 20)
        rt.mem.poke(PT.G_PROMPT_OWNER, 4, 0x1234)
        rt.tick()
        self.assertEqual(rt.u32(PT.G_PROMPT_TIMER), 13)
        rt.tick()
        rt.tick()
        self.assertEqual(rt.u32(PT.G_PROMPT_TIMER), 0)
        self.assertEqual(rt.u32(PT.G_PROMPT_OWNER), 0)

    def test_an_interactable_object_is_refused(self):
        rt = PT.TickRuntime()
        p = rt.spawn_player(0, (0.0, 0.0, 0.0))
        s = rt.spawn_skelight((20.0, 0.0, 0.0))
        rt.mem.poke(s + 0xC, 4, rt.u32(s + 0xC) | 0x100000)
        with self.assertRaises(T.Unsupported):
            rt.tick()

    def test_tick_duel_trace_is_stable(self):
        """Self-pin of the composed duel on the real tick (player against a Skelight, 80
        ticks).  The digest was made by this model; it is not evidence about the game."""
        rt = PT.TickRuntime()
        p, s = duel(rt, voice=10)
        for t in range(80):
            if t == 30:
                rt.press_attack(0)
            rt.tick()
        digest = hashlib.sha256(repr(rt.trace).encode() + repr(sorted(rt.mem.bytes.items())).encode()).hexdigest()
        self.assertEqual(sum(d for _f, d in rt.draws_by_player[p]), TICK_DUEL_PLAYER_DRAWS)
        self.assertEqual(rt.u32(T.G_RAND_SEED), TICK_DUEL_SEED)
        self.assertEqual(digest, TICK_DUEL_DIGEST)


TICK_DUEL_PLAYER_DRAWS = 72
TICK_DUEL_SEED = 0xCC973545
TICK_DUEL_DIGEST = 'e61799d0353733de642be7f5a16e8150ef51383ee90805c37c719fbf3082d6dc'


if __name__ == '__main__':
    unittest.main()
