#!/usr/bin/env python3
"""Unit tests for tools/ref_trig.py.  No game file: agreement with the executable is
tools/difftest_trig.py.  These tests pin the polynomial against ref_core (the existing
API, left unchanged) and the places a host libm cosine is not that polynomial.
"""
import math
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref_combat as C           # noqa: E402
import ref_core as R            # noqa: E402
import ref_particles as P       # noqa: E402
import ref_trig as T            # noqa: E402


def fbits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def host_pair(angle):
    """What ref_particles._cs returns: host math.cos/math.sin of the 16-bit angle."""
    turned = R.s16(angle) * (2.0 * math.pi / 65536.0)
    return math.cos(turned), math.sin(turned)


class TrigTest(unittest.TestCase):
    def setUp(self):
        R.set_fpu()
        C.set_fpu()

    def tearDown(self):
        R.set_fpu()
        C.set_fpu()

    def test_matches_ref_core_on_every_angle(self):
        for angle in range(0x10000):
            self.assertEqual(T.cos16(angle), R.cos16(angle))
            self.assertEqual(T.sin16(angle), R.sin16(angle))
            self.assertEqual(T.cos16(angle), C.cos16(angle))
            self.assertEqual(T.sin16(angle), C.sin16(angle))

    def test_sine_is_cosine_of_the_shifted_angle(self):
        for angle in range(0x10000):
            self.assertEqual(T.sin16(angle), T.cos16(angle - 0x4000))

    def test_high_bits_are_ignored(self):
        for angle in range(0, 0x10000, 64):
            self.assertEqual(T.cos16(angle), T.cos16(angle | 0xABCD0000))
            self.assertEqual(T.sin16(angle), T.sin16(angle - 0x10000))

    def test_quarter_turns(self):
        self.assertEqual(T.cos16(0), R.ONE)
        self.assertEqual(T.cos16(0x8000), R.MINUS_ONE)
        self.assertEqual(T.sin16(0x4000), R.ONE)
        self.assertEqual(T.sin16(0), 0x34800000)          # +2^-22, not zero
        self.assertEqual(T.cos16(0x4000), 0xB4800000)
        self.assertEqual(T.cos16(0xC000), 0x34800000)

    def test_adder_models_disagree(self):
        """The polynomial's adds are close enough in magnitude that the adder model
        changes the result.  Counts are pairs (cosine angles, sine angles) against the
        default ps2 model, over all 65,536 inputs."""
        base_c = [T.cos16(a) for a in range(0x10000)]
        base_s = [T.sin16(a) for a in range(0x10000)]
        counts = {}
        for model in ('ps2g1', 'chop', 'nearest'):
            R.set_fpu(model)
            counts[model] = (
                sum(T.cos16(a) != base_c[a] for a in range(0x10000)),
                sum(T.sin16(a) != base_s[a] for a in range(0x10000)),
            )
        self.assertEqual(counts['ps2g1'], (45278, 45278))
        self.assertEqual(counts['chop'], (2830, 2830))
        self.assertEqual(counts['nearest'], (46206, 46206))

    def test_host_libm_is_not_the_polynomial(self):
        # Portable: every IEEE libm returns sin(0) == +0.  The polynomial does not.
        cosine, sine = host_pair(0)
        self.assertEqual(cosine, 1.0)
        self.assertEqual(sine, 0.0)
        self.assertEqual(fbits(cosine), T.cos16(0))
        self.assertNotEqual(fbits(sine), T.sin16(0))
        # The count itself follows the host libm and is not pinned.
        changed = 0
        for angle in range(0x10000):
            hc, hs = host_pair(angle)
            if fbits(hc) != T.cos16(angle) or fbits(hs) != T.sin16(angle):
                changed += 1
        self.assertGreater(changed, 0)

    def test_emitter_yaw_zero_moves_only_the_offset(self):
        """ref_particles.emitter_run uses host sine.  At yaw 0 that sine is +0, so an
        x offset stays on the x axis.  math_sin16(0) is 2^-22, so the original offset
        gains a y component and the x component is unchanged (cosine of 0 is 1 either way).
        The on/off schedule does not read the angle."""
        rec = P.EmitterRecord.new(rate=1, on=1, next=0, on_time=0, off_x=100.0, off_y=0.0,
                                  off_z=0.0, yaw=0, pitch=0, box=(0.0, 0.0, 0.0),
                                  vel=(0.0, 0.0, 0.0), spread=0.0, cone=0.0, flags=0)
        out = P.emitter_run(rec, (0.0, 0.0, 0.0), now=0, rng=P.CosmeticRng(1), yaw=0)
        self.assertEqual(len(out), 1)
        (x, y, z), velocity = out[0]
        self.assertEqual((x, y, z), (100.0, 0.0, 0.0))
        self.assertEqual(velocity, (0.0, 0.0, 0.0))
        sine = T.as_float(T.sin16(0))
        self.assertEqual(sine, 2.0 ** -22)
        self.assertNotEqual(y, -100.0 * sine)
        turned = P.rotate_axis(P.IDENTITY, 2, 0)
        self.assertEqual(turned[0], [1.0, 0.0, 0.0])
        self.assertNotEqual(sine, 0.0)

    def test_haze_circle_truncates_and_has_no_lerp_term(self):
        sine0, cosine0 = T.haze_circle(0)
        self.assertEqual(sine0, 0)                # 5 * 2^-22 truncates to 0
        self.assertEqual(cosine0, 5)
        sine, cosine = T.haze_circle(16)          # angle 16<<10 = 0x4000, a quarter turn
        self.assertEqual(cosine, 0)               # 5 * -2^-22 truncates to 0
        self.assertEqual(sine, 5)
        # Index bits above 6 wrap.  Truncation to a whole number collapses the 64
        # slots onto 28 distinct pairs; the reader still picks one slot, not a blend.
        self.assertEqual(T.haze_circle(0), T.haze_circle(64))
        self.assertEqual(len({T.haze_circle(i) for i in range(64)}), 28)


if __name__ == '__main__':
    unittest.main()
