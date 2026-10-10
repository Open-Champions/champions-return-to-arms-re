#!/usr/bin/env python3
"""Unit tests for tools/ref_core.py that need no game file (they run in CI).

They pin down the model's own logic with values worked out independently: by hand, from
the published description of the generators, or from the definition of the operation.
Whether the model agrees with the game is the business of tools/difftest_core.py.
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_core as R            # noqa: E402

F = R.f32


class Flagged:
    """Stand-in for a game object: the handle iterators only read .flags."""

    def __init__(self, name, flags=0):
        self.name, self.flags = name, flags

    def __repr__(self):
        return self.name


class FpuTest(unittest.TestCase):
    def setUp(self):
        R.set_fpu()

    def test_truncation(self):
        self.assertEqual(R.div(R.ONE, F(3.0)), 0x3EAAAAAA)          # IEEE nearest is ...ab
        self.assertEqual(R.mul(F(1.1), F(1.1)), 0x3F9AE148)          # exact 1.2100000524...; nearest would be ...49
        self.assertEqual(R.from_int(16777217), 0x4B800000)           # 2**24 + 1 loses the 1
        self.assertEqual(R.from_int(0x7FFFFFFF), 0x4EFFFFFF)         # not rounded up to 2**31

    def test_no_infinity_no_denormal(self):
        self.assertEqual(R.div(R.ONE, 0), R.FMAX)
        self.assertEqual(R.div(R.MINUS_ONE, 0), 0xFFFFFFFF)
        self.assertEqual(R.div(0, 0), R.FMAX)
        self.assertEqual(R.mul(0x7F000000, 0x7F000000), R.FMAX)      # overflow clamps
        self.assertEqual(R.mul(0x00800000, R.HALF), 0)               # underflow is zero
        self.assertEqual(R.add(0x00000001, R.ONE), R.ONE)            # a denormal pattern is zero
        self.assertEqual(R.add(0x7F800000, 0x7F800000), R.FMAX)      # "infinity" is just a number

    def test_adder_models_differ_only_far_apart(self):
        a, b = R.ONE, 0xB3000000                                     # 1.0 - 2**-25: half a unit down
        results = {model: R.Fpu(model).add(a, b) for model in R.Fpu.MODELS}
        self.assertEqual(results['nearest'], R.ONE)                  # tie, to even
        self.assertEqual(results['chop'], 0x3F7FFFFF)                # the exact sum cut off
        self.assertEqual(results['ps2'], R.ONE)                      # 25 exponents apart: ignored
        self.assertEqual(results['ps2g1'], R.ONE)
        for model in R.Fpu.MODELS:                                   # equal exponents: all agree
            self.assertEqual(R.Fpu(model).add(F(1.5), F(1.25)), F(2.75))

    def test_ps2_adder_ignores_small_operand(self):
        self.assertEqual(R.Fpu('ps2').add(R.ONE, 0xB2000000), R.ONE)       # 26 exponents apart
        self.assertEqual(R.Fpu('chop').add(R.ONE, 0xB2000000), 0x3F7FFFFF)

    def test_conversions(self):
        self.assertEqual(R.to_int(F(-2.7)), -2)
        self.assertEqual(R.to_int(F(3.0e9)), 0x7FFFFFFF)
        self.assertEqual(R.to_int(F(-3.0e9)), -0x80000000)
        self.assertEqual(R.to_int(0x7FC00000), 0x7FFFFFFF)           # a NaN pattern is a big number
        self.assertEqual(R.to_uint(F(3.0e9)), 3000000000)
        self.assertEqual(R.round_half_away(F(2.5)), 3)
        self.assertEqual(R.round_half_away(F(-2.5)), -3)

    def test_compare(self):
        self.assertTrue(R.eq(0, R.SIGN))                             # +0 == -0
        self.assertTrue(R.lt(R.MINUS_ONE, 0))
        self.assertFalse(R.lt(0, R.SIGN))
        self.assertTrue(R.le(0x7F800000, 0x7FC00000))                # ordered like any numbers

    def test_const_truncates(self):
        self.assertEqual(R.const('0.1'), 0x3DCCCCCC)
        self.assertEqual(R.const('0.3'), 0x3E999999)
        self.assertEqual(R.const('-0.2'), 0xBE4CCCCC)
        self.assertEqual(R.const('1.5'), 0x3FC00000)
        self.assertEqual(R.const('1.0e30'), 0x7149F2C9)
        self.assertEqual(R.dconst('0.9'), 0x3FECCCCCCCCCCCCC)
        self.assertEqual(R.dconst('2.4'), 0x4003333333333333)
        self.assertEqual(R.dconst('1.5'), 0x3FF8000000000000)


class AngleTest(unittest.TestCase):
    def setUp(self):
        R.set_fpu()

    def test_cardinal_values(self):
        self.assertEqual(R.cos16(0), R.ONE)
        self.assertEqual(R.cos16(0x8000), R.MINUS_ONE)
        self.assertEqual(R.sin16(0x4000), R.ONE)
        self.assertEqual(R.sin16(0xC000), R.MINUS_ONE)
        # the quarter turns are not zero: 2**-22, with a sign that depends on the side
        self.assertEqual(R.sin16(0), 0x34800000)
        self.assertEqual(R.sin16(0x8000), 0xB4800000)
        self.assertEqual(R.cos16(0x4000), 0xB4800000)
        self.assertEqual(R.cos16(0xC000), 0x34800000)

    def test_close_to_the_real_cosine(self):
        worst = max(abs(R.to_float(R.cos16(a)) - math.cos(a * math.pi / 32768)) for a in range(0, 65536, 5))
        self.assertLess(worst, 1.0e-6)

    def test_only_sixteen_bits_count(self):
        for angle in (0x1234, 0x7FFF, 0x8000, 0xFFFF):
            self.assertEqual(R.cos16(angle), R.cos16(angle | 0x7FFF0000))
            self.assertEqual(R.cos16(angle), R.cos16(R.s16(angle)))

    def test_atan2_quirks(self):
        self.assertEqual(R.atan2_16(F(0.0), F(1.0)), 0)
        self.assertEqual(R.atan2_16(F(1.0), F(1.0)), 8191)           # one short of an eighth turn
        self.assertEqual(R.atan2_16(F(1.0), F(0.0)), 16383)
        self.assertEqual(R.atan2_16(F(0.0), F(-1.0)), 32767)
        self.assertEqual(R.atan2_16(F(-0.0), F(-1.0)), -32767)
        self.assertEqual(R.atan2_16(F(-1.0), F(0.0)), -16383)
        self.assertEqual(R.atan2_16(F(0.0), F(0.0)), 0)

    def test_turn_dir(self):
        self.assertEqual(R.angle_turn_dir(100, 50), (-1, 50))
        self.assertEqual(R.angle_turn_dir(50, 100), (1, 50))
        self.assertEqual(R.angle_turn_dir(7, 7), (1, 0))
        self.assertEqual(R.angle_turn_dir(0x8000, 0), (1, 0x8000))
        self.assertEqual(R.angle_turn_dir(0x7FFF, 0x8001), (1, 2))   # across the wrap

    def test_approach(self):
        no = R.MINUS_ONE
        self.assertEqual(R.angle_approach(F(0.5), no, no, 1000, 0), 500)
        self.assertEqual(R.angle_approach(F(0.5), no, no, 0, 1000), 500)
        self.assertEqual(R.angle_approach(F(0.5), no, F(100.0), 1000, 0), 900)
        self.assertEqual(R.angle_approach(F(0.5), F(700.0), no, 1000, 0), 300)
        self.assertEqual(R.angle_approach(F(0.1), F(700.0), no, 100, 0), -600)   # overshoots the target
        self.assertEqual(R.angle_approach(F(1.0), no, no, 0x7000, 0x9000), -0x7000)


class MathTest(unittest.TestCase):
    def setUp(self):
        R.set_fpu()

    def test_hermite_ends(self):
        self.assertEqual(R.hermite(0, 0, R.ONE, 0, 0), 0)
        self.assertEqual(R.hermite(R.ONE, 0, R.ONE, 0, 0), R.ONE)
        self.assertEqual(R.hermite(R.HALF, 0, R.ONE, 0, 0), R.HALF)
        p0, p1 = [F(1.0), F(2.0), F(3.0)], [F(5.0), F(7.0), F(9.0)]
        zero = [0, 0, 0]
        self.assertEqual(R.vec3_hermite(0, p0, p1, zero, zero), p0)
        self.assertEqual(R.vec3_hermite(R.ONE, p0, p1, zero, zero), p1)

    def test_identity_products(self):
        ident = R.mat34_set_identity()
        m = [F(v) for v in (0.5, -1.0, 2.0, 3.0, 0.25, -4.0, 1.5, 8.0, -0.125, 10.0, 20.0, 30.0)]
        self.assertEqual(R.mat34_mul(m, ident), m)
        self.assertEqual(R.mat34_mul(ident, m), m)
        self.assertEqual(R.mat3_transpose(R.mat3_transpose(m[:9])), m[:9])

    def test_rotation_by_zero_is_not_identity(self):
        rotated = R.mat3_rotate_axis(R.mat3_set_identity(), 2, 0)
        self.assertEqual(rotated, [R.ONE, 0x34800000, 0, 0xB4800000, R.ONE, 0, 0, 0, R.ONE])
        self.assertEqual(R.mat3_set_rot_z(0), rotated)
        self.assertEqual(R.mat3_rotate_axis(R.mat3_set_identity(), 5, 0x1234), R.mat3_set_identity())

    def test_quarter_turn_matrix(self):
        m = R.mat34_set_pos_rot_z([F(1.0), F(2.0), F(3.0)], 0x4000)
        self.assertEqual(m[1], R.ONE)                                # sin
        self.assertEqual(m[3], R.MINUS_ONE)                          # -sin
        self.assertEqual(m[9:], [F(1.0), F(2.0), F(3.0)])
        point = R.mat34_transform_point(m, [F(10.0), 0, 0])
        self.assertAlmostEqual(R.to_float(point[0]), 1.0, places=4)
        self.assertAlmostEqual(R.to_float(point[1]), 12.0, places=4)

    def test_invert(self):
        ident = [R.ONE if i % 5 == 0 else 0 for i in range(16)]
        self.assertEqual(R.mat4_invert(ident), ident)
        self.assertEqual(R.mat4_invert([0] * 16), ident)              # singular: identity
        scale = list(ident)
        scale[0], scale[5], scale[10] = F(2.0), F(4.0), F(8.0)
        inverse = R.mat4_invert(scale)
        self.assertEqual((inverse[0], inverse[5], inverse[10]), (F(0.5), F(0.25), F(0.125)))
        swap = [0, R.ONE, 0, 0, R.ONE, 0, 0, 0, 0, 0, R.ONE, 0, 0, 0, 0, R.ONE]
        self.assertEqual(R.mat4_invert(swap), swap)                   # needs the column exchange
        m34 = R.mat34_set_translation([F(3.0), F(-4.0), F(5.0)])
        self.assertEqual(R.mat34_invert(m34)[9:], [F(-3.0), F(4.0), F(-5.0)])

    def test_quaternions(self):
        self.assertEqual(R.quat_normalize([0, 0, 0, F(2.0)]), [0, 0, 0, R.ONE])
        ident = [0, 0, 0, R.ONE]
        q = [F(0.5), F(0.5), F(0.5), F(0.5)]
        self.assertEqual(R.quat_mul(ident, q), q)
        self.assertEqual(R.mat3_from_quat(ident), R.mat3_set_identity())
        self.assertEqual(R.quat_from_mat3(R.mat3_set_identity()), ident)
        self.assertEqual(R.quat_rotate_vec(ident, [F(1.0), F(2.0), F(3.0)]), [F(1.0), F(2.0), F(3.0)])
        # trace <= 0: a half turn about X
        self.assertEqual(R.quat_from_mat3([R.ONE, 0, 0, 0, R.MINUS_ONE, 0, 0, 0, R.MINUS_ONE]), [R.ONE, 0, 0, 0])

    def test_boxes(self):
        empty = R.bbox_set_empty()
        box = R.bbox_add_point(empty, [F(1.0), F(2.0), F(3.0)])
        self.assertEqual(box, [F(1.0), F(2.0), F(3.0)] * 2)
        box = R.bbox_union(box, [F(-1.0), 0, 0, F(0.5), F(5.0), F(1.0)])
        self.assertEqual(box, [F(-1.0), 0, 0, F(1.0), F(5.0), F(3.0)])
        self.assertEqual(R.bbox_contains_point(box, [F(1.0), F(5.0), 0]), 1)      # on the boundary
        self.assertEqual(R.bbox_contains_point(box, [F(1.5), F(5.0), 0]), 0)
        self.assertEqual(R.bbox_overlaps(box, [F(1.0)] * 3 + [F(9.0)] * 3), 1)   # touching
        self.assertEqual(R.bbox_overlaps(box, [F(1.5)] * 3 + [F(9.0)] * 3), 0)

    def test_colours(self):
        self.assertEqual(R.color_scale_clamped(F(0.5), 0x80FF4020), 0x407F2010)
        self.assertEqual(R.color_scale_clamped(F(2.0), 0x80FF4020), 0xFFFF8040)
        self.assertEqual(R.color_scale_clamped(F(-1.0), 0x80FF4020), 0)
        self.assertEqual(R.color_from_hsv(0, R.ONE, R.ONE), 0xFF0000FF)           # red in the low byte
        self.assertEqual(R.color_from_hsv(0, 0, R.HALF), 0xFF7F7F7F)
        self.assertEqual(R.color_from_hsv(R.ONE, R.ONE, R.ONE), 0xFF000000)       # hue 1.0: black

    def test_log2(self):
        self.assertEqual([R.log2_floor(x) for x in (-7, 0, 1, 2, 3, 4, 1023, 1024)], [0, 0, 0, 1, 1, 2, 9, 10])

    def test_noise(self):
        flat = [16384] * 256
        self.assertEqual({R.noise(flat, i) for i in range(0, 5000, 7)}, {R.HALF})
        ramp = list(range(256))
        self.assertEqual(R.noise(ramp, 16 * 10), R.mul(R.from_int(10), 0x38000000))
        self.assertEqual(R.noise(ramp, 16 * 10 + 8), R.mul(F(10.5), 0x38000000))
        self.assertEqual(R.noise(ramp, 4096 + 5), R.noise(ramp, 5))               # period
        self.assertEqual(R.noise(ramp, -1), R.noise(ramp, 4095))
        table, seed = R.build_noise_table(12345)
        self.assertEqual(len(table), 256)
        self.assertTrue(all(-0x8000 <= v < 0x8000 for v in table))
        self.assertEqual(R.build_noise_table(12345), (table, seed))
        self.assertNotEqual(R.build_noise_table(12346)[0], table)
        self.assertNotEqual(R.build_noise_table(12345, stale=(R.HALF, 0, 0))[0], table)


class LibmTest(unittest.TestCase):
    def setUp(self):
        R.set_fpu()

    def test_floor_ceil(self):
        cases = ((2.5, 2.0, 3.0), (-2.5, -3.0, -2.0), (7.0, 7.0, 7.0), (0.25, 0.0, 1.0), (-0.25, -1.0, -0.0))
        for value, down, up in cases:
            self.assertEqual(R.floorf(F(value)), F(down))
            self.assertEqual(R.ceilf(F(value)), F(up))
        self.assertEqual(R.ceilf(F(-0.25)), R.SIGN)                  # minus zero
        self.assertEqual(R.floorf(R.SIGN), R.SIGN)

    def test_fmodf(self):
        self.assertEqual(R.fmodf(F(5.5), F(2.0)), F(1.5))
        self.assertEqual(R.fmodf(F(-5.5), F(2.0)), F(-1.5))
        self.assertEqual(R.fmodf(F(6.0), F(-2.0)), 0)
        self.assertEqual(R.fmodf(F(-6.0), F(2.0)), R.SIGN)
        self.assertEqual(R.fmodf(F(1.0), F(2.0)), F(1.0))
        self.assertEqual(R.fmodf(F(1.0), 0), R.FMAX)                 # 0/0 on this FPU

    def test_sqrtf_rounds_where_the_instruction_truncates(self):
        self.assertEqual(R.sqrtf(F(4.0)), F(2.0))
        self.assertEqual(R.sqrtf(F(-4.0)), R.FMAX)
        differ = [n for n in range(2, 200) if R.sqrtf(F(float(n))) != R.sqrt(F(float(n)))]
        self.assertTrue(differ)                                       # e.g. 3: 0x3fddb3d7 against ...d6
        self.assertTrue(all(R.sqrtf(F(float(n))) - R.sqrt(F(float(n))) == 1 for n in differ))

    def test_powf(self):
        self.assertEqual(R.powf(F(2.0), F(-1.0)), R.HALF)
        self.assertEqual(R.powf(F(8.0), F(-1.0)), F(0.125))
        self.assertEqual(R.powf(F(10.0), F(2.0)), F(100.0))          # the x*x shortcut
        self.assertEqual(R.powf(F(9.0), R.HALF), F(3.0))             # the sqrtf shortcut
        self.assertEqual(R.powf(F(123.0), 0), R.ONE)
        self.assertEqual(R.powf(F(-2.0), F(3.0)), F(-8.0))
        self.assertEqual(R.powf(F(-2.0), F(0.5)), R.FMAX)            # no NaN to return
        self.assertAlmostEqual(R.to_float(R.powf(F(1.1), F(10.0))), 1.1 ** 10, places=5)

    def test_atan(self):
        self.assertEqual(R.atanf(0), 0)
        self.assertEqual(R.atanf(R.ONE), 0x3F490FDA)
        self.assertAlmostEqual(R.to_float(R.atanf(F(0.5))), math.atan(0.5), places=6)
        self.assertEqual(R.atan2f(F(1.0), F(-1.0)), 0x4016CBE4)
        self.assertEqual(R.atan2f(0, F(-1.0)), 0x40490FDA)


class SoftDoubleTest(unittest.TestCase):
    def test_truncating(self):
        self.assertEqual(R.dmul(R.d64(0.1), R.d64(3.0)), 0x3FD3333333333333)     # IEEE gives ...34
        self.assertEqual(R.ddiv(R.d64(1.0), R.d64(3.0)), 0x3FD5555555555555)
        self.assertEqual(R.ddiv(R.d64(2.0), R.d64(3.0)), 0x3FE5555555555555)     # IEEE rounds up
        self.assertEqual(R.d2f(R.d64(0.1)), 0x3DCCCCCC)                          # IEEE nearest is ...cd
        self.assertEqual(R.dadd(R.d64(1.0), R.d64(2.0)), R.d64(3.0))
        self.assertEqual(R.dsub(R.d64(1.0), R.d64(1.0)), 0)

    def test_no_denormals_but_infinities(self):
        self.assertEqual(R.dadd(1, 1), 0)
        self.assertEqual(R.dmul(0x0010000000000000, R.d64(0.5)), 0)
        self.assertEqual(R.ddiv(R.d64(1.0), 0), 0x7FF0000000000000)
        self.assertEqual(R.ddiv(0, 0), R.D_NAN)
        self.assertEqual(R.dsub(0x7FF0000000000000, 0x7FF0000000000000), R.D_NAN)
        self.assertEqual(R.dcmp(R.D_NAN, R.d64(1.0)), 1)
        self.assertEqual(R.dcmp(R.d64(1.0), R.d64(2.0)), -1)
        self.assertEqual(R.dcmp(0, R.D_SIGN), 0)

    def test_conversions(self):
        self.assertEqual(R.i2d(-3), R.d64(-3.0))
        self.assertEqual(R.i2d(-0x80000000), R.d64(-2147483648.0))
        self.assertEqual(R.d2i(R.d64(-2.9)), -2)
        self.assertEqual(R.d2i(R.d64(1e12)), 0x7FFFFFFF)
        self.assertEqual(R.d2i(R.D_NAN), 0)
        self.assertEqual(R.f2d(F(1.5)), R.d64(1.5))
        self.assertEqual(R.f2d(0x7F800000), R.d64(2.0 ** 128))       # not an infinity
        self.assertEqual(R.d2f(R.d64(1e300)), 0x7F800000)
        self.assertEqual(R.d2f(0xFFF0000000000000), 0xFF800000)
        self.assertEqual(R.d2f(R.d64(1e-300)), 0)

    def test_the_literal_idiom(self):
        # f * 1.5 as the game computes it: widen, multiply, truncate back
        value = F(0.7)
        self.assertEqual(R.d2f(R.dmul(R.f2d(value), R.dconst('1.5'))), 0x3F866666)
        self.assertEqual(R.f32(R.to_float(value) * 1.5), 0x3F866666)
        value = F(0.3)                                               # here truncation shows
        self.assertEqual(R.d2f(R.dmul(R.f2d(value), R.dconst('0.9'))), 0x3E8A3D70)
        self.assertEqual(R.f32(R.to_float(value) * 0.9), 0x3E8A3D71)

    def test_fmod(self):
        self.assertEqual(R.fmod(R.d64(5.5), R.d64(2.0)), R.d64(1.5))
        self.assertEqual(R.fmod(R.d64(-7.0), R.d64(4.0)), R.d64(-3.0))
        self.assertEqual(R.fmod(R.d64(8.0), R.d64(4.0)), 0)
        self.assertEqual(R.fmod(R.d64(1.0), 0), R.D_NAN)
        for a, b in ((123456.789, 0.37), (1e20, 7.0), (5e-324, 3e-324), (-9.25, 0.5)):
            self.assertEqual(R.fmod(R.d64(a), R.d64(b)), R.d64(math.fmod(a, b)))


class GeneratorTest(unittest.TestCase):
    def test_lcg_is_the_textbook_one(self):
        # "ranqd1" of Numerical Recipes in C, 2nd edition, section 7.1: starting from 0 the
        # states are 3C6EF35F, 47502932, D1CCF6E9, AAF95334, 6252E503, 9F2EC686, ...
        rng = R.Lcg(0)
        draws = [rng.draw() for _ in range(6)]
        self.assertEqual(draws, [0x3C6E, 0x4750, 0xD1CC, 0xAAF9, 0x6252, 0x9F2E])
        self.assertEqual(rng.state, 0x9F2EC686)

    def test_object_seed_is_a_draw(self):
        shared = R.SharedRandom(0)
        first = R.ObjectRandom(shared)
        second = R.SpellRandom(shared)
        self.assertEqual((first.state, second.state), (0x3C6E, 0x4750))
        self.assertEqual(shared.state, 0x47502932)

    def test_float_draws(self):
        R.set_fpu()
        rng = R.Lcg(0)
        self.assertEqual(rng.unit(), R.mul(R.from_int(0x3C6E), R.TWO_M16))
        self.assertEqual(R.to_float(R.Lcg(0).unit()), 0x3C6E / 65536.0)
        point = R.Lcg(1234).in_unit_sphere()
        self.assertLessEqual(sum(R.to_float(c) ** 2 for c in point), 1.0)

    def test_libc_rand(self):
        rng = R.LibcRand()
        self.assertEqual(rng.rand(), 1481765933)                     # newlib's first rand() from seed 1
        rng.seed(1)
        self.assertEqual(rng.rand(), 1481765933)
        self.assertTrue(all(0 <= rng.rand() <= 0x7FFFFFFF for _ in range(100)))


class PoolTest(unittest.TestCase):
    def test_layout(self):
        pool = R.Pool()
        self.assertEqual(pool.count_free(), 1056)
        self.assertEqual(pool.base, [0x5F88C0, 0x5F88C0 + 0x180 * 512, 0x5F88C0 + (0x180 + 0x500) * 512])
        self.assertEqual(pool.end, 0x5F88C0 + 0xE7700)

    def test_order_and_reuse(self):
        pool = R.Pool()
        a, b, c = pool.new(0x100), pool.new(0x100), pool.new(0x100)
        self.assertEqual((a, b, c), (0x5F88C0, 0x5F88C0 + 0x180, 0x5F88C0 + 0x300))   # ascending at first
        pool.free(a)
        pool.free(c)
        self.assertEqual(pool.new(0x10), c)                          # last freed, first reused
        self.assertEqual(pool.new(0x10), a)
        self.assertEqual(pool.last, a)

    def test_class_choice(self):
        pool = R.Pool()
        self.assertEqual(pool.class_of(pool.new(0x180)), 0)
        self.assertEqual(pool.class_of(pool.new(0x181)), 1)
        self.assertEqual(pool.class_of(pool.new(0x500)), 1)
        self.assertEqual(pool.class_of(pool.new(0x501)), 2)
        self.assertEqual(pool.class_of(pool.new(3000)), 2)
        self.assertEqual(pool.new(3001), 0)
        self.assertEqual(pool.class_of(pool.new(0)), 0)
        self.assertEqual(pool.class_of(pool.new(-5)), 0)

    def test_spill_and_failure(self):
        pool = R.Pool()
        small = [pool.new(0x148) for _ in range(512)]
        self.assertTrue(all(pool.class_of(a) == 0 for a in small))
        spilled = pool.new(0x148)
        self.assertEqual(pool.class_of(spilled), 1)
        pool.free(spilled)                                           # back to the class of its address
        self.assertEqual(pool.new(0x400), spilled)
        for _ in range(511 + 32):
            self.assertNotEqual(pool.new(0x10), 0)
        self.assertEqual(pool.count_free(), 0)
        self.assertEqual(pool.new(0x10), 0)
        pool.free(small[7])
        self.assertEqual(pool.new(0x200), 0)                         # the free block is too small
        self.assertEqual(pool.new(0x10), small[7])

    def test_out_of_range(self):
        pool = R.Pool()
        self.assertEqual(pool.class_of(0x100000), 0)                 # no lower bound in the original
        self.assertRaises(R.PoolError, pool.class_of, pool.end)


class HandleTest(unittest.TestCase):
    def setUp(self):
        self.pool = R.HandlePool(64)
        self.objects = [Flagged('o%d' % n) for n in range(6)]
        self.backs = [R.Cell() for _ in self.objects]
        self.head = R.Cell()

    def link_all(self):
        return [self.pool.link(self.head, back, obj) for obj, back in zip(self.objects, self.backs)]

    def test_link_is_two_nodes_and_lifo(self):
        nodes = self.link_all()
        self.assertEqual([n.index for n in nodes], [0, 2, 4, 6, 8, 10])
        self.assertEqual(self.pool.count_free(), 64 - 12)
        self.assertEqual(R.HandlePool.items(self.head), self.objects[::-1])     # newest first
        self.assertIs(nodes[0].partner.partner, nodes[0])
        self.assertIs(self.backs[0].next, nodes[0].partner)
        self.assertIsNone(nodes[0].partner.obj)

    def test_clearing_an_object_empties_every_handle_to_it(self):
        other = R.Cell()
        self.link_all()
        self.pool.link(other, self.backs[2], self.objects[2])
        self.pool.clear(self.backs[2])                               # the object is destroyed
        self.assertNotIn(self.objects[2], R.HandlePool.items(self.head))
        self.assertEqual(R.HandlePool.items(other), [])
        self.assertIsNone(self.backs[2].next)
        self.assertEqual(self.pool.count_free(), 64 - 10)

    def test_clearing_a_list_frees_the_back_nodes(self):
        self.link_all()
        self.pool.clear(self.head)
        self.assertTrue(all(back.next is None for back in self.backs))
        self.assertEqual(self.pool.count_free(), 64)

    def test_remove_and_reuse_order(self):
        nodes = self.link_all()
        self.assertIs(self.pool.remove(nodes[3]), self.objects[3])
        fresh = self.pool.link(self.head, self.backs[3], self.objects[3])
        self.assertIs(fresh, nodes[3])                               # the node itself comes back first
        self.assertEqual(fresh.partner.index, 7)

    def test_single_nodes(self):
        a = self.pool.add(self.head, self.objects[0])
        b = self.pool.add(self.head, self.objects[1])
        c = self.pool.insert(self.head, b, self.objects[2])          # behind b
        d = self.pool.insert(self.head, None, self.objects[3])       # at the front
        self.assertEqual(R.HandlePool.items(self.head), [self.objects[i] for i in (3, 1, 2, 0)])
        self.assertTrue(all(n.partner is None for n in (a, b, c, d)))

    def test_exhaustion(self):
        pool = R.HandlePool(4)
        pool.link(self.head, self.backs[0], self.objects[0])
        pool.link(self.head, self.backs[1], self.objects[1])
        self.assertRaises(R.HandleError, pool.link, self.head, self.backs[2], self.objects[2])

    def test_walk_and_mask(self):
        self.link_all()
        self.objects[1].flags = 0x20000
        self.objects[4].flags = 0x200000
        self.assertEqual(R.walk(self.head), self.objects[::-1])
        self.assertEqual(R.walk(self.head, 0x20000), [o for o in self.objects[::-1] if o is not self.objects[1]])
        self.assertEqual(R.walk(self.head, 0x220000),
                         [o for o in self.objects[::-1] if o not in (self.objects[1], self.objects[4])])
        self.assertEqual(R.walk(R.Cell()), [])
        self.assertEqual(R.walk(self.backs[0]), [])                  # partner-side nodes carry no object

    def test_iterator_stands_in_the_list(self):
        nodes = self.link_all()
        it = R.Iterator(self.head)
        self.assertIs(it.prev, nodes[5])
        self.assertIs(nodes[5].next, it)
        self.assertIs(it.next, nodes[4])
        self.assertIs(nodes[4].prev, it)
        it.end()
        self.assertIs(nodes[5].next, nodes[4])
        self.assertIs(nodes[4].prev, nodes[5])

    def test_removing_the_current_node(self):
        self.link_all()
        seen = []
        it = R.Iterator(self.head)
        while not it.done:
            seen.append(it.current)
            self.pool.remove(it.prev)                                # the body deletes what it is on
            it.advance()
        it.end()
        self.assertEqual(seen, self.objects[::-1])
        self.assertIsNone(self.head.next)

    def test_destroying_objects_ahead(self):
        self.link_all()
        seen = []
        it = R.Iterator(self.head)
        while not it.done:
            seen.append(it.current)
            if it.current is self.objects[4]:
                self.pool.clear(self.backs[3])                       # the next two objects die
                self.pool.clear(self.backs[2])
            it.advance()
        it.end()
        self.assertEqual(seen, [self.objects[i] for i in (5, 4, 1, 0)])

    def test_additions_are_not_visited(self):
        self.link_all()
        late, back = Flagged('late'), R.Cell()
        seen = []
        it = R.Iterator(self.head)
        first = True
        while not it.done:
            seen.append(it.current)
            if first:
                self.pool.link(self.head, back, late)                # at the front: already passed
                self.pool.insert(self.head, it.prev, late)           # behind the current node: before the iterator
                first = False
            it.advance()
        it.end()
        self.assertEqual(seen, self.objects[::-1])
        self.assertEqual(R.HandlePool.items(self.head).count(late), 2)

    def test_two_iterators(self):
        self.link_all()
        outer = R.Iterator(self.head)
        inner = R.Iterator(self.head)                                # comes to stand behind the same node
        self.assertIs(outer.prev, inner)
        self.assertIsNone(outer.current)                             # reads the other iterator's empty field
        inner.end()
        self.assertIs(outer.current, self.objects[5])
        pairs = 0
        while not outer.done:
            inner = R.Iterator(self.head)
            while not inner.done:
                pairs += 1
                inner.advance()
            inner.end()
            outer.advance()
        outer.end()
        self.assertEqual(pairs, 36)

    def test_undefined_cases_raise(self):
        self.link_all()
        it = R.Iterator(self.head)
        self.assertRaises(R.HandleError, self.pool.clear, self.head)        # an iterator stands in it
        it.end()
        done = R.Iterator(R.Cell())
        self.assertRaises(R.HandleError, done.advance)
        same = R.Cell()
        self.pool.link(same, same, self.objects[0])                  # both nodes in one list
        self.assertRaises(R.HandleError, self.pool.clear, same)


if __name__ == '__main__':
    unittest.main()
