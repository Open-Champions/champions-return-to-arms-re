#!/usr/bin/env python3
"""Synthetic tests of tools/ref_fx_recipes.py (no game files needed).  The bit-for-bit
comparison with the original is tools/difftest_fx_recipes.py."""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ref_core as C                                    # noqa: E402
import ref_fx_recipes as R                              # noqa: E402

F = C.to_float
POS = [C.f32(100.5), C.f32(-200.25), C.f32(30.0)]


def spawns(calls):
    return [c for c in calls if c[0] == 'spawn']


class FxSpawnTest(unittest.TestCase):
    def run_id(self, fx_id, seed=12345, **kw):
        cos, shr = C.Lcg(seed), C.Lcg(seed ^ 0x5555)
        calls = R.fx_spawn(fx_id, POS, cos, shr, **kw)
        return calls, cos, shr

    def test_counts(self):
        counts = {0: 300, 1: 300, 2: 150, 3: 150, 4: 150, 6: 150, 7: 3, 8: 300, 9: 300,
                  10: 105, 0xB: 40, 0xC: 35, 0xD: 1, 0xE: 1, 0xF: 1, 0x10: 1, 0x11: 1,
                  0x12: 1, 0x14: 3, 0x15: 10, 0x16: 2}
        for fx_id, n in counts.items():
            self.assertEqual(len(spawns(self.run_id(fx_id)[0])), n, hex(fx_id))

    def test_camera_gate_and_id5(self):
        calls, cos, _ = self.run_id(2, near=False)
        self.assertEqual(calls, [('near', POS)])
        self.assertEqual(cos.state, 12345)
        calls, cos, shr = self.run_id(5, near=False)
        self.assertNotIn('near', [c[0] for c in calls])
        fires = [c for c in calls if c[0] == 'fire']
        self.assertIn(len(fires), (3, 4))
        self.assertEqual(cos.state, 12345)              # id 5 draws only the shared seed
        self.assertNotEqual(shr.state, 12345 ^ 0x5555)
        for c in fires:
            self.assertTrue(-6 <= F(c[1][0]) - F(POS[0]) <= 5)
            self.assertTrue(0 <= F(c[1][2]) - F(POS[2]) <= 17)

    def test_gore_zero_blocks_red_blood_only(self):
        self.assertEqual(spawns(self.run_id(0, gore=0)[0]), [])
        self.assertEqual(spawns(self.run_id(1, gore=0)[0]), [])
        self.assertEqual(len(spawns(self.run_id(9, gore=0)[0])), 300)

    def test_first_use_constructs_all_definitions_once(self):
        made = set()
        calls = self.run_id(0x11, made=made)[0]
        self.assertEqual([c[1] for c in calls if c[0] == 'ctor'], list(R.FX_SPAWN_DEFS))
        calls = self.run_id(0x11, made=made)[0]
        self.assertEqual([c for c in calls if c[0] == 'ctor'], [])

    def test_backdate_is_zero_and_static_ids_have_no_velocity(self):
        for fx_id in range(0x17):
            for c in spawns(self.run_id(fx_id)[0]):
                self.assertEqual(c[1], 0)
        for fx_id in (0xD, 0xE, 0xF, 0x10, 0x11, 0x12):
            (c,) = spawns(self.run_id(fx_id)[0])
            self.assertEqual(c[4], [0, 0, 0])

    def test_id6_scales_all_axes_by_16(self):
        for c in spawns(self.run_id(6)[0]):
            self.assertLessEqual(sum(F(v) ** 2 for v in c[4]), 16.0 ** 2 * 1.0001)

    def test_upward_ids(self):
        for fx_id in (0x16,):
            for c in spawns(self.run_id(fx_id)[0]):
                self.assertGreaterEqual(F(c[4][2]), 0.0)
        for seed in range(50):
            for c in spawns(self.run_id(7, seed=seed)[0]):
                self.assertGreater(F(c[4][2]), 6.05 - 4.75 * 0.77 - 1e-3)

    def test_id15_vertical_terms_vanish_except_at_minus_one(self):
        for seed in range(30):
            for c in spawns(self.run_id(0x15, seed=seed)[0]):
                self.assertIn(F(c[4][2]), (0.0, 12.0))
                self.assertIn(F(c[3][2]) - F(POS[2]), (0.0, 6.0, 36.0))

    def test_id13_second_particle_one_in_ten(self):
        extra = sum(len(spawns(self.run_id(0x13, seed=s)[0])) - 1 for s in range(400))
        self.assertTrue(10 <= extra <= 80, extra)

    def test_point_within_15(self):
        for seed in range(100):
            (c,) = spawns(self.run_id(0xD, seed=seed)[0])
            dx, dy = F(c[3][0]) - F(POS[0]), F(c[3][1]) - F(POS[1])
            self.assertLessEqual(dx * dx + dy * dy, 15.0 ** 2 * 1.001)
            self.assertTrue(-7.5 <= F(c[3][2]) - F(POS[2]) <= 7.5)


class FakeModel:
    def __init__(self, n=5, size=4000.0):
        self.n = n
        self.size = C.f32(size)
        self.n_samples = n
        self.attach_base = 2

    def sample_count(self):
        return self.n

    def sample_point(self, scale, anim, pos, yaw, index):
        return [C.f32(10.0 * index), C.f32(1.0), C.f32(2.0)], self.size

    def transform_sample_point(self, matrix, index):
        return C.mat34_transform_point(matrix, [C.f32(index), 0, 0]), self.size

    def effect_segment(self):
        return [0, C.f32(4.5), 0], [0, C.f32(38.0), 0]


class DeathRecipeTest(unittest.TestCase):
    def test_disintegrate_volume_rule(self):
        # 4000^3 = 6.4e10 < 8.09e10: one particle per point, the remainder carries over
        model = FakeModel(n=10, size=4000.0)
        calls = R.disintegrate_model(model, POS, 0, C.ONE, 0, 0, 0, C.Lcg(1))
        n = len(spawns(calls))
        self.assertTrue(7 <= n <= 10, n)
        self.assertEqual(calls[0], ('hide',))
        for c in spawns(calls):
            self.assertTrue(0 <= F(c[1]) < 0.4)
            self.assertEqual(c[2], R.DEF_DISINTEGRATE)

    def test_shatter_uses_only_the_shared_seed(self):
        model = FakeModel(n=12)
        shared = C.Lcg(99)
        calls = R.shatter_to_loose_ice(model, POS, 0, C.f32(4.0), C.ONE, 0, 0, shared)
        chunks = [c for c in calls if c[0] == 'phprop']
        self.assertEqual(len(chunks), 4)
        self.assertEqual([c for c in calls if c[0] == 'sample'][0][5], 3)    # step 12 // 4
        self.assertTrue(all(c[6] in (2, 3, 4) for c in chunks))
        draws = C.Lcg(99)
        for _ in range(5):
            draws.draw()
        self.assertEqual(shared.state, draws.state)


class LosePartTest(unittest.TestCase):
    def mask(self, model, variant):
        return (variant * 0x0101010101) & 0xFFFFFFFFFFFFFFFF

    def test_ant_chunk_shows_the_hidden_meshes(self):
        c = R.Creature(variant=0, cls=list(range(8)))
        calls = R.lose_body_part('Ant', c, 3, self.mask)
        self.assertEqual(c.variant, 0x10)
        (gut,) = [x for x in calls if x[0] == 'gut']
        self.assertEqual(gut[9], self.mask(3, 0) & ~self.mask(3, 0x10) & 0xFFFFFFFFFFFFFFFF)
        self.assertEqual((gut[10], gut[11]), (0xE, 2))
        self.assertIn(('lift',), calls)

    def test_firebeetle_constant_masks_and_blackwidow(self):
        c = R.Creature(variant=0, cls=list(range(8)))
        calls = R.lose_body_part('FireBeetle', c, 5, self.mask)
        self.assertEqual([x for x in calls if x[0] == 'gut'][0][9], 0xC00)
        self.assertEqual(calls[-1][0], 'mask')
        c = R.Creature(variant=0, cls=list(range(8)), kind=1)
        self.assertEqual(R.lose_body_part('BlackWidow', c, 2, self.mask), [])
        c = R.Creature(variant=0, cls=list(range(8)))
        calls = R.lose_body_part('BlackWidow', c, 9, self.mask)
        self.assertFalse([x for x in calls if x[0] == 'gut'])
        self.assertEqual(c.variant, 0x200)

    def test_orc_head_mask(self):
        self.assertEqual(R.orc_head_mask(0), 0x20406)
        self.assertEqual(R.orc_head_mask(1), 0x60406)
        self.assertEqual(R.orc_head_mask(0x104), 0x80000000 | (0x20406 ^ 6) | 0x300000)


class ModelRecipeTest(unittest.TestCase):
    def test_emit_from_verts(self):
        calls = R.emit_from_model_verts(FakeModel(), POS, 0, 0, 7, 0x1234, None, None, C.ONE, C.Lcg(5))
        self.assertEqual(len(spawns(calls)), 7)

    def test_sparkle_counts(self):
        model = FakeModel(size=1.0)       # size^2 = 1: one particle per point
        calls = R.model_sparkle(model, POS, 0, 0, C.ONE, 0, C.Lcg(5))
        defs = [c[2] for c in spawns(calls)]
        self.assertEqual(defs.count(0x870728), 17)        # round(16.59)
        self.assertEqual(defs.count(0x870778), 4)         # round(3.76)
        self.assertEqual(R.model_sparkle(model, POS, 0, 0, C.ONE, 0, C.Lcg(5), near=False),
                         [('near', POS)])

    def test_arcs_create_then_update(self):
        state = R.ArcState()
        calls = R.model_arcs(FakeModel(), POS, 0, 0, C.f32(2.0), C.ONE, 0, state, 0, C.Lcg(3),
                             beam_create=lambda a, b: 77)
        self.assertEqual(sum(1 for c in calls if c[0] == 'beam_create'), 3)
        self.assertTrue(all(a[2] == 77 for a in state.arcs))
        updates = 0
        for seed in range(20):
            calls = R.model_arcs(FakeModel(), POS, 0, 0, C.f32(2.0), C.ONE, 0, state, 0,
                                 C.Lcg(seed), beam_create=lambda a, b: 77)
            for c in calls:
                if c[0] == 'beam_update':
                    updates += 1
                    self.assertEqual(c[4], 94)        # alpha clamped to 1
        self.assertGreater(updates, 20)

    def test_glow_ramp_clamps(self):
        ramp = R.GlowRamp()
        for _ in range(200):
            R.model_glow(FakeModel(), 0x20, ramp, POS, 0, 0, C.ONE, 0, C.ONE, [100] * 4,
                         [200] * 4, 0, 0, 0)
        self.assertEqual([F(v) for v in ramp.b], [200.0] * 4)
        for _ in range(200):
            R.model_glow(FakeModel(), 0x20, ramp, POS, 0, 0, C.ONE, 0, C.ONE, [100] * 4,
                         [200] * 4, 2, 0, 0)
        self.assertEqual([F(v) for v in ramp.b], [0.0] * 4)


class WeaponStatusTest(unittest.TestCase):
    def run_fx(self, entries, swinging=0, amount=1.0, **kw):
        item = R.WeaponItem((0, 0, 0, 0), (0, 0, 0, 0), entries)
        prev = C.mat34_set_identity()
        state = R.WeaponFxState(C.mat34_set_pos_rot_z([0, 0, 0], 0x1000))
        calls = R.model_status_effects(C.f32(amount), C.ONE, item, FakeModel(), state, POS, 0,
                                       None, 0, swinging, 0, None, C.Lcg(7), **kw)
        return calls, state, item

    def test_level_flag_and_dialog(self):
        self.assertEqual(self.run_fx([(0x18, 1)], level_flags=0x10000000)[0], [])
        self.assertEqual(self.run_fx([(0x18, 1)], dialog_open=True)[0], [('dialog_open',)])

    def test_lightning_minimum_and_beam(self):
        calls, state, _ = self.run_fx([(0x18, 1)], amount=0.01, answers={'beam_create': 9})
        self.assertGreaterEqual(sum(1 for c in spawns(calls) if c[2] == 0x870958), 8)
        self.assertEqual(state.beam, 9)

    def test_entry_value_only_gates(self):
        a = self.run_fx([(0x16, 1)])[0]
        b = self.run_fx([(0x16, 100)])[0]
        self.assertEqual(a, b)
        self.assertEqual(spawns(self.run_fx([(0x16, 0)])[0]), [])

    def test_poison_ignores_motion(self):
        calls = self.run_fx([(0x17, 1)])[0]
        n = sum(1 for c in spawns(calls) if c[2] == 0x870CC8)
        self.assertEqual(n, int(26 * 0.155997))
        self.assertEqual(spawns(calls)[0][1], 0)                 # backdate starts at 0

    def test_item_colours_fade(self):
        item = R.WeaponItem((5, -5, 1, 0), (3, 0, -1, 0), [])
        R.model_status_effects(C.ONE, C.ONE, item, FakeModel(), R.WeaponFxState(), POS, 0, None,
                               0, 0, 0, None, C.Lcg(7))
        self.assertEqual(item.glow, [3, -3, 0, 0])
        self.assertEqual(item.colour2, [1, 0, 0, 0])


if __name__ == '__main__':
    unittest.main()
