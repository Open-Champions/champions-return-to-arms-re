#!/usr/bin/env python3
"""Unit tests of tools/ref_combat_melee.py that need no game files (they run in CI).

Every fixture is synthetic: actors placed by hand, weapons written into fixture memory,
callbacks answered by the test.  The tests pin what docs/spec/combat-player-melee.md
states - the attack-animation choice and its one shared draw, the branches of the armed
melee hit, the 200 draws of the hit sparks, the combo timing - and that round 1's
contract is unchanged where this module adds to it.  Whether the bodies match the game is
the business of tools/difftest_combat_melee.py."""
import hashlib
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                            # noqa: E402
import ref_creature as RC                       # noqa: E402
import ref_combat_runtime as T                  # noqa: E402
import ref_combat_melee as M                    # noqa: E402
import test_ref_combat_runtime as R1            # noqa: E402

f32 = T.f32
P_ADDR, T_ADDR, TABLE = 0x00100000, 0x00101000, 0x00102000


class Script:
    """Callbacks answered by a fixed script; every call is recorded by the model."""

    def __init__(self, answers=None):
        self.answers = answers or {}

    def get(self, name):
        def answer(*args):
            value = self.answers.get(name, 0)
            return value(*args) if callable(value) else value
        return answer


def bare_model(answers=None, slot=0):
    mem = RC.Memory()
    model = M.MeleeModel(mem, Script(answers))
    mem.poke(P_ADDR + 0x3C8, 4, slot)
    mem.poke(T_ADDR + 0x48, 4, TABLE)
    mem.poke(TABLE + 8 * 16 + 4, 4, 0x3C2738)              # Creature slot 16
    mem.poke(T_ADDR + 0x24, 4, TABLE + 0x100)
    mem.poke(TABLE + 0x10C, 4, 0x00A20000)                  # the target's model
    mem.poke(P_ADDR + 0x544, 4, 0x00A10000)
    return model, mem


def rec(slot=0):
    return T.G_PLAYERS + slot * T.REC_SIZE


class PickAttackAnim(unittest.TestCase):
    def test_table_of_the_animation_document(self):
        """Spot checks against docs/spec/player-animation-dispatch.md 3.4 (Executed there
        by an ad-hoc run) and this module's reading."""
        V = M.pick_attack_variant
        self.assertEqual(V(0, 0, 1, 0x7FFE), [2])
        self.assertEqual(V(0, 0, 1, 0x7FFF), [4])
        self.assertEqual(V(0, 0, 0, 0xBB7F), [2])
        self.assertEqual(V(0, 0, 0, 0xBB80), [4])
        self.assertEqual(V(9, 0, 5, 0x1000), [4])
        self.assertEqual(V(9, 0, 5, 0xAAAA), [4, 1])         # two stores on this path
        self.assertEqual(V(9, 5, 3, 0), [1])
        self.assertEqual(V(11, 0, 4, 0x53EC), [5])
        self.assertEqual(V(11, 2, 3, 0xBB80), [4])
        self.assertEqual(V(11, 5, 2, 0xDAC0), [4])
        self.assertEqual(V(3, 7, 1, 0), [2])
        self.assertEqual(V(3, 7, 6, 0), [1])
        for cls in (4, 6):
            self.assertEqual(V(0, cls, 1, 0x1234), [])

    def test_one_shared_draw_whose_value_is_unused(self):
        for seed in (0, 0x12345678, 0xFFFFFFFF):
            model, mem = bare_model()
            mem.poke(T.G_RAND_SEED, 4, seed)
            mem.poke(T.G_SIM_FRAME, 4, 1000)
            mem.poke(P_ADDR + 0x461, 1, 1)
            model.pick_attack_anim(P_ADDR, 0)
            self.assertEqual(model.draws, 1)
            self.assertEqual(mem.load(P_ADDR + 0x461, 1), M.pick_attack_variant(0, 0, 1, M.frame_hash(1000))[-1])
            self.assertEqual(model.calls, [('net_isLocalSlot', (0,))])
            self.assertEqual({a for a, _s, _v in model.writes}, {T.G_RAND_SEED, P_ADDR + 0x461})


class MeleeHitFull(unittest.TestCase):
    def setUp(self):
        self.answers = {'terrain_raycast': f32(-1.0), 'damage_apply': 1, 'item_getModifiedField1a': 7}

    def armed(self, cls=0, subtype=0, both=False, step=0, heavy=False, passive=0):
        model, mem = bare_model(self.answers)
        R = rec()
        d, item, second = 0x00104000, 0x00104100, 0x00104200
        mem.poke(d + 0x20, 4, 8)
        mem.poke(d + 0x1E, 1, subtype)
        for it in (item, second):
            mem.poke(it, 4, d)
            mem.poke(it + 8, 4, 0x55)
        mem.poke(R + 0x4434, 4, item)
        mem.poke(R + 0x43F0, 4, item)
        if both:
            mem.poke(R + 0x43F4, 4, second)
            mem.poke(R + 0x443C, 4, second)
        mem.poke(R + 0x4A86, 1, cls)
        mem.poke(P_ADDR + 0x460, 1, step)
        mem.poke(R + 0xD0, 4, 10)
        mem.poke(R + 0xD4, 4, 20)
        if heavy:
            mem.poke(P_ADDR + 0x44C, 4, 2)
        if passive:
            mem.poke(M.G_CLASS_SKILLS + 3 * 0x38, 8, passive)
            mem.poke(R + 0xEF + 3, 1, 2)
        return model, mem, item, second

    def damage_call(self, model):
        return [c for c in model.calls if c[0] == 'damage_apply'][0][1]

    def test_weapon_flags_and_descriptor(self):
        model, mem, item, _ = self.armed()
        model.player_melee_hit_full(P_ADDR, T_ADDR, 0, 0x40000000, M.ZERO)
        args = self.damage_call(model)
        self.assertEqual(args[3], 7)                       # item_getModifiedField1a
        self.assertEqual(args[4], 0x55)                    # low word of item +8
        self.assertEqual(args[5], 8 | 0x40000 | 0x40000000)
        self.assertEqual(args[6], item)
        self.assertEqual(args[8:], (C.from_int(10), C.from_int(20)))

    def test_bow_and_thrown_hit_as_a_fist(self):
        for cls, subtype in ((4, 0), (0, 6)):
            model, mem, item, _ = self.armed(cls=cls, subtype=subtype)
            model.player_melee_hit_full(P_ADDR, T_ADDR, 0, 0, M.ZERO)
            recalcs = [c[1] for c in model.calls if c[0] == 'Player_recalcDamage']
            self.assertEqual(recalcs, [(P_ADDR, item, 0), (P_ADDR, 0, 0)])
            self.assertTrue(self.damage_call(model)[5] & 0x200000)

    def test_second_hand_on_odd_steps_with_the_passive(self):
        for step, passive, expect_second in ((1, M.PASSIVE_DUAL_WIELD, True), (2, M.PASSIVE_DUAL_WIELD, False),
                                             (1, 0, False)):
            model, mem, item, second = self.armed(both=True, step=step, passive=passive)
            model.player_melee_hit_full(P_ADDR, T_ADDR, 0, 0, M.ZERO)
            self.assertEqual(self.damage_call(model)[6], second if expect_second else item)
            mem.poke(T_ADDR + 0xC, 4, 0x20)

    def test_trail_material_of_the_second_hand(self):
        model, mem, item, second = self.armed(both=True, step=1, passive=M.PASSIVE_DUAL_WIELD)
        mem.poke(T_ADDR + 0xC, 4, 0x20)
        mem.poke(T_ADDR + 0xA8, 8, 0x1000)
        model.player_melee_hit_full(P_ADDR, T_ADDR, 0, 0, M.ZERO)
        self.assertEqual(mem.load(rec() + 0x4AC5 + 0x40, 1), 2)
        self.assertEqual(mem.load(rec() + 0x4AC6 + 0x40, 1), 5)

    def test_heavy_attack_raises_the_record_range_in_place(self):
        model, mem, _, _ = self.armed(heavy=True)
        model.player_melee_hit_full(P_ADDR, T_ADDR, 0, 0, M.ZERO)
        # skill_rankScale(0) = 0.9: 10 + round(9.0) = 19, 20 + round(18.0) = 38
        self.assertEqual((mem.load(rec() + 0xD0, 4), mem.load(rec() + 0xD4, 4)), (19, 38))
        self.assertEqual(self.damage_call(model)[8:], (C.from_int(19), C.from_int(38)))
        self.assertTrue(self.damage_call(model)[5] & 0x200000)
        self.assertFalse([c for c in model.calls if c[0] == 'model_getSamplePointCount'])  # not a creature

    def test_scale_multiplies_the_range_and_skips_the_ray(self):
        model, mem, _, _ = self.armed()
        model.player_melee_hit_full(P_ADDR, T_ADDR, 0, 0, f32(1.5))
        self.assertNotIn('terrain_raycast', [c[0] for c in model.calls])
        self.assertEqual((mem.load(rec() + 0xD0, 4), mem.load(rec() + 0xD4, 4)), (15, 30))
        self.assertTrue(self.damage_call(model)[5] & 0x80000)

    def test_blocked_line_of_sight_and_the_autoprop_exception(self):
        self.answers['terrain_raycast'] = f32(0.5)
        model, mem, _, _ = self.armed()
        self.answers['Creature.v0'] = 0x00105000
        self.answers['AutoProp_typeinfo'] = M.AUTOPROP_DESC
        mem.poke(0x00105000, 4, 0x00105100)
        mem.poke(M.AUTOPROP_DESC, 4, 0x00105200)
        for addr, text in ((0x00105100, b'Creature\0'), (0x00105200, b'AutoProp\0')):
            for i, b in enumerate(text):
                mem.poke(addr + i, 1, b)
        model.player_melee_hit_full(P_ADDR, T_ADDR, 0, 0, M.ZERO)
        self.assertNotIn('damage_apply', [c[0] for c in model.calls])
        model2, mem2, _, _ = self.armed()
        self.answers['Creature.v0'] = M.AUTOPROP_DESC
        model2.player_melee_hit_full(P_ADDR, T_ADDR, 0, 0, M.ZERO)
        self.assertIn('damage_apply', [c[0] for c in model2.calls])

    def test_prediction_copy_does_nothing(self):
        model, mem, _, _ = self.armed()
        mem.poke(P_ADDR + 0xC, 4, T.F_PREDICTION_COPY)
        model.player_melee_hit_full(P_ADDR, T_ADDR, 0, 0, M.ZERO)
        self.assertEqual(model.calls, [])


class HitSparks(unittest.TestCase):
    def test_two_hundred_shared_draws(self):
        answers = {'model_getSamplePointCount': 7,
                   'model_getSamplePoint': lambda *a: ((f32(1.0), f32(2.0), f32(3.0 + a[4])), (0, 0, 0))}
        model, mem = bare_model(answers)
        mem.poke(T_ADDR + 0xC, 4, 0x20)
        model.player_hit_sparks(P_ADDR, T_ADDR)
        self.assertEqual(model.draws, 200)
        names = [c[0] for c in model.calls]
        self.assertEqual(names.count('particle_spawn'), 100)
        self.assertEqual(names.count('model_getSamplePoint'), 200)
        spawn = [c[1] for c in model.calls if c[0] == 'particle_spawn'][0]
        self.assertEqual(spawn[0], M.HIT_SPARK_DEF)

    def test_a_model_without_points_is_refused(self):
        model, mem = bare_model({'model_getSamplePointCount': 0})
        with self.assertRaises(T.Unsupported):
            model.player_hit_sparks(P_ADDR, T_ADDR)


class ComboTimeline(unittest.TestCase):
    def test_speed_one(self):
        t = M.combo_timeline(0)
        self.assertEqual((t['hit'], t['steps'], t['sweep_from']), (16, 7, None))
        self.assertEqual(t['next_after'], 0x41B028F5)      # 22.02
        self.assertEqual(t['ends_at'], C.mul(0x3FCCCCCC, M.F_60))
        self.assertEqual(M.combo_timeline(0, net=True)['hit'], 1)

    def test_class_two_sweep_needs_speed(self):
        """The class-2 sweep starts at trunc(127 / speed) but a swing ends by itself at
        96 frames (1.6 x 60, not divided by the speed): at speed 1.0 the sweep can only
        come after the swing ended (Inferred from the executed ref_player model)."""
        slow = M.combo_timeline(2)
        self.assertEqual(slow['sweep_from'], 127)
        self.assertTrue(C.lt(slow['ends_at'], C.from_int(slow['sweep_from'])))
        fast = M.combo_timeline(2, speed=f32(1.4))
        self.assertTrue(C.le(C.from_int(fast['sweep_from']), fast['ends_at']))
        self.assertEqual(M.combo_timeline(2, heavy=True)['sweep_from'], 0x5E)

    def test_haste_trims_the_window(self):
        t = M.combo_timeline(7, speed=f32(1.25), haste=f32(0.25))
        self.assertEqual(t['next_after'], C.div(C.sub(0x418CED91, C.mul(C.mul(f32(0.25), M.F_60), M.HALF)), f32(1.25)))


class Composition(unittest.TestCase):
    def test_round_one_duel_unchanged(self):
        """MeleeRuntime on round 1's pinned duel (unarmed, scale 0): the same trace, seed
        and memory as ref_combat_runtime.Runtime - the superset method changes nothing in
        round 1's domain."""
        rt = M.MeleeRuntime()
        rt.spawn_player(0, (0.0, 0.0, 0.0), strength=40)
        s = rt.spawn_skelight((30.0, 0.0, 0.0), facing=0x8000, hp=40.0)
        R1.swing_clips(rt, s)
        for t in range(80):
            if t == 30:
                rt.press_attack(0)
            rt.tick()
        digest = hashlib.sha256(repr(rt.trace).encode() + repr(sorted(rt.mem.bytes.items())).encode()).hexdigest()
        self.assertEqual(rt.u32(T.G_RAND_SEED), R1.DUEL_SEED)
        self.assertEqual(digest, R1.DUEL_DIGEST)

    def combo(self, rt, taps):
        rt.spawn_player(0, (0.0, 0.0, 0.0))
        rt.spawn_skelight((300.0, 0.0, 0.0))
        for _ in range(25):
            rt.tick()
        starts, draws = [], []
        for t in range(taps * 30):
            if t % 30 in (0, 24):
                rt.press_attack(0)
            before = rt.model.draws
            rt.tick()
            if rt.model.u32(rt.players[0] + 0x448) == (rt.world.frame - 1) & T.M32:
                starts.append(t)
                draws.append(rt.model.draws - before)
        return starts, draws

    def test_a_combo_runs_with_the_attack_animation_choice(self):
        """Round 1 refused the second swing (Player_pickAttackAnim); here it runs, each
        next swing after the window (22.02 frames at speed 1)."""
        rt = M.MeleeRuntime()
        starts, _draws = self.combo(rt, 3)
        self.assertEqual(starts[0], 0)
        self.assertGreaterEqual(len(starts), 3)
        self.assertTrue(all(b - a > 22 for a, b in zip(starts, starts[1:])))
        variants = rt.model.s8(rt.players[0] + 0x461)
        self.assertIn(variants, (1, 2))                     # unarmed (class 5): 1 -> 2 -> 1 ...

    def test_an_armed_hit_uses_the_weapon(self):
        rt = M.MeleeRuntime()
        P = rt.spawn_player(0, (0.0, 0.0, 0.0), strength=40)
        item = rt.give_weapon(0, dmg=(30, 40), attack=50, dmg_type=8)
        s = rt.spawn_skelight((30.0, 0.0, 0.0), facing=0x8000, hp=400.0)
        R1.swing_clips(rt, s)
        for t in range(60):
            if t == 30:
                rt.press_attack(0)
            rt.tick()
        hits = [e for e in rt.trace if e[0] == 'damage_apply' and e[2] == P]
        self.assertTrue(hits)
        R = rec()
        self.assertEqual(rt.model.s32(R + 0xD0), 30 + 10)    # range + strength / 4
        self.assertEqual(rt.model.u32(R + 0x4434), item)
        self.assertTrue(hits[0][4] & 8)                       # the definition's damage bits

    def test_bow_damage_is_refused(self):
        rt = M.MeleeRuntime()
        rt.spawn_player(0, (0.0, 0.0, 0.0))
        rt.give_weapon(0, subtype=4, cls=0)
        rt.spawn_skelight((30.0, 0.0, 0.0), facing=0x8000)
        with self.assertRaises(T.Unsupported):
            for t in range(60):
                if t == 30:
                    rt.press_attack(0)
                rt.tick()


if __name__ == '__main__':
    unittest.main()
