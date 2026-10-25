#!/usr/bin/env python3
"""ref_trig.py - math_cos16 (0x166630) and math_sin16 (0x1666e0).

A research model, not game code.  The bodies were read at those addresses and are
compared with the executable by tools/difftest_trig.py.  docs/spec/trig16.md is the
prose.  The same polynomial already lives in ref_core.cos16; this module is the
effect-and-combat view of it (callers, the haze circle, the host-libm gap).  It uses
ref_core's FPU, so set_fpu changes both.  No game bytes are embedded.

There is no lookup table inside either routine.  The four coefficients are immediate
operands.  particle_init builds a 64-entry circle from the results; haze_circle is
that circle.  Its words are computed, not stored in the executable, and are not
kept here.
"""
import ref_core as R

# Immediates in the function (lui/ori), not loads.
K_HALF_ANGLE = 0x38490FDA     # pi/65536: the folded angle is half the original, in radians
K_S3 = 0x3E2AAA57             # 0.16666542
K_S5 = 0x3C086B24             # 0.008326326
K_S7 = 0x39458017             # 0.00018835101
K_FIVE = 0x40A00000           # 5.0, the haze circle's scale (particle_init)

HAZE_CIRCLE = 0x007EC0E0      # 64 pairs, written by particle_init, read by particle_drawHaze
HAZE_COUNT = 64
HAZE_ANGLE_STEP = 0x400       # index << 10


def cos16(angle):
    """math_cos16 0x166630.  Returns the f0 bit pattern.

    Each multiply, add and subtract is its own R5900 operation (toward zero, no fused
    multiply-add).  cvt.s.w of the folded angle is exact: the angle is at most 16384.
    The active adder is ref_core's current model.  The default 'ps2' model is the one
    difftest_trig compares with the interpreter.
    """
    a = R.s16(angle)                          # sll 16; sra 16
    sign = R.ONE
    if (a ^ (a << 1)) & 0x8000:               # bit 15 of a differs from bit 14
        sign = R.MINUS_ONE
        a = (a & 0x7FFF) - (0x8000 if a & 0x4000 else 0)   # sll 17; sra 17
    x = R.mul(R.from_int(a), K_HALF_ANGLE)    # cvt.s.w, then mul.s
    x2 = R.mul(x, x)
    x3 = R.mul(x, x2)
    s = R.sub(x, R.mul(x3, K_S3))
    x5 = R.mul(x3, x2)
    s = R.add(s, R.mul(x5, K_S5))
    x7 = R.mul(x5, x2)
    s = R.sub(s, R.mul(x7, K_S7))
    two_s = R.add(s, s)
    return R.mul(sign, R.sub(R.ONE, R.mul(two_s, s)))


def sin16(angle):
    """math_sin16 0x1666e0.  The body is a copy of math_cos16, not a call.

    It starts with addiu v1, a0, -0x4000 on the full 32-bit argument, then the same
    sign-extend and polynomial, using v1.  Keeping 16 bits of (angle - 0x4000) is
    that reduction.
    """
    return cos16(angle - 0x4000)


def as_float(pattern):
    """IEEE reading of a result pattern, for the host-libm comparison only."""
    return R.to_float(pattern)


def haze_circle(index):
    """The pair particle_init stores at HAZE_CIRCLE + (index & 63) * 8.

    Returns (sine word, cosine word).  Each is cvt.w.s of the polynomial times 5,
    so the word is the truncated integer.  Index 0's sine truncates to 0 even though
    sin16(0) is not 0.  No second sample and no fraction: the reader uses one pair.
    """
    angle = (index & 63) << 10
    sine = R.to_int(R.mul(sin16(angle), K_FIVE)) & R.M32
    cosine = R.to_int(R.mul(cos16(angle), K_FIVE)) & R.M32
    return sine, cosine
