#!/usr/bin/env python3
"""ref_core.py - reference model of the engine's small core: the math library, the random
generators, the object pool and the handle lists of Champions: Return to Arms (SLUS_209.73).

A research tool, not game code.  Every function here was written from the instruction
sequence at the address given in its docstring and is compared with that code, executed
under tools/ee_emu.py, by tools/difftest_core.py.  docs/spec/core.md is the prose version.
Standard library only; no game data is embedded.

Floats are raw 32-bit patterns
    Online play is lockstep, so the last bit matters, and the console's FPU is not IEEE 754.
    Every float in this module is therefore an int holding the 32-bit pattern, and all
    arithmetic goes through the Fpu class below, which follows the same rules as the
    interpreter in tools/ee_emu.py (and offers the same four adder models).  f32() turns a
    Python float into a pattern, to_float() turns one back for printing.  Vectors, matrices
    and quaternions are Python lists of patterns:

        vec3    [x, y, z]
        quat    [x, y, z, w]
        mat3    9 patterns, three rows of three; a point is transformed as  v * M  (row vector)
        mat34   12 patterns: a mat3 followed by the translation row
        mat4    16 patterns, four rows of four
        bbox    [min x, min y, min z, max x, max y, max z]

    Functions return new lists; where the original writes through an output pointer while it
    is still reading its inputs, the docstring says so ("not alias-safe").

Angles are 16-bit: 0x10000 is a full turn; arguments are reduced with s16() as the code does.

Sections: 1 arithmetic, 2 angles, 3 scalars and colours, 4 vectors and boxes, 5 matrices,
6 quaternions, 7 noise, 8 C-library routines, 8b software double precision, 9 random
generators, 10 object pool, 11 handle lists.
"""
import struct
from fractions import Fraction

M32 = 0xFFFFFFFF
M64 = 0xFFFFFFFFFFFFFFFF
SIGN = 0x80000000
FMAX = 0x7FFFFFFF          # what the R5900 produces on overflow and on division by zero


# =======================================================================================
# 1. Arithmetic
# =======================================================================================

def s16(x):
    """Low 16 bits as a signed number (the sll 16 / sra 16 pair)."""
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def s32(x):
    """Low 32 bits as a signed number."""
    x &= M32
    return x - 0x100000000 if x & SIGN else x


def f32(value):
    """Pattern of the IEEE single nearest to a Python float (for test input, not for
    constants of the game: those are given as patterns, see const())."""
    try:
        return struct.unpack('<I', struct.pack('<f', value))[0]
    except OverflowError:
        return 0xFF800000 if value < 0 else 0x7F800000


def to_float(raw):
    """IEEE reading of a pattern (an R5900 value with exponent field 255 shows as inf/nan)."""
    return struct.unpack('<f', struct.pack('<I', raw & M32))[0]


def const(text):
    """Pattern the game's compiler produced for a decimal literal: the exact decimal value
    TRUNCATED toward zero to 24 significant bits, not rounded to nearest.  const('0.1') is
    0x3dcccccc where IEEE rounding gives 0x3dcccccd.  (Shown by the C library's tables, all
    of which come out of this rule - difftest_core.py property "libm tables".)"""
    q = Fraction(text)
    sign = SIGN if q < 0 else 0
    q = abs(q)
    if q == 0:
        return sign
    e2 = q.numerator.bit_length() - q.denominator.bit_length() - 24
    while q >= Fraction(2) ** (e2 + 24):
        e2 += 1
    while q < Fraction(2) ** (e2 + 23):
        e2 -= 1
    mant = int(q / Fraction(2) ** e2)                   # floor: truncation
    return sign | ((e2 + 150) << 23) | (mant & 0x7FFFFF)


class Fpu:
    """R5900 single precision on raw patterns.

    No NaN, infinity or denormal: exponent field 0 is zero, exponent field 255 is an
    ordinary large number, overflow gives +/-0x7fffffff, underflow gives a signed zero,
    division by zero gives +/-0x7fffffff, results are truncated toward zero.

    model selects how a sum is formed (the one place where descriptions of the hardware
    differ; see tools/ee_emu.py):
      'ps2'     the smaller operand is aligned keeping six extra bits, the rest floored
                away; ignored altogether when the exponents differ by 25 or more
      'ps2g1'   the smaller operand keeps one extra bit; then the sum is truncated
      'chop'    the exact sum truncated toward zero
      'nearest' IEEE round to nearest even, for sensitivity tests only
    mul_bias takes one unit off every inexact product; div_nearest rounds quotients and
    square roots to nearest.  Both exist to measure sensitivity, as in ee_emu.
    """
    MODELS = ('ps2', 'ps2g1', 'chop', 'nearest')

    def __init__(self, model='ps2', mul_bias=False, div_nearest=False):
        if model not in self.MODELS:
            raise ValueError('model must be one of %s' % (self.MODELS,))
        self.model = model
        self.mul_bias = mul_bias
        self.div_nearest = div_nearest

    @staticmethod
    def _split(raw):
        """(sign, 24-bit significand or 0, exponent field)."""
        exp = (raw >> 23) & 0xFF
        if exp == 0:
            return raw >> 31, 0, 0
        return raw >> 31, (raw & 0x7FFFFF) | 0x800000, exp

    @staticmethod
    def _round(sign, mag, e2, nearest):
        """Pattern for (-1)**sign * mag * 2**e2, mag a positive integer of any size."""
        drop = mag.bit_length() - 24
        if drop > 0:
            kept = mag >> drop
            if nearest:
                rest = mag - (kept << drop)
                half = 1 << (drop - 1)
                if rest > half or (rest == half and kept & 1):
                    kept += 1
                    if kept == 1 << 24:
                        kept >>= 1
                        drop += 1
        else:
            kept = mag << -drop
        exp = e2 + drop + 150
        if exp > 255:
            return (sign << 31) | FMAX
        if exp < 1:
            return sign << 31
        return (sign << 31) | (exp << 23) | (kept & 0x7FFFFF)

    def add(self, a, b):
        sa, ma, ea = self._split(a)
        sb, mb, eb = self._split(b)
        if ma == 0 and mb == 0:
            return (sa & sb) << 31
        if ma == 0:
            return b & M32
        if mb == 0:
            return a & M32
        if self.model == 'ps2':
            if ea < eb:
                a, sa, ma, ea, sb, mb, eb = b, sb, mb, eb, sa, ma, ea
            gap = ea - eb
            if gap >= 25:
                return a & M32
            big = -ma if sa else ma
            small = -mb if sb else mb
            total = (big << 6) + ((small << 6) >> gap)      # >> floors
            if total == 0:
                return 0
            return self._round(1 if total < 0 else 0, abs(total), ea - 156, False)
        if self.model == 'ps2g1':
            gap = ea - eb
            if gap >= 25:
                return a & M32
            if gap <= -25:
                return b & M32
            if gap > 1:
                mb &= -1 << (gap - 1)
            elif gap < -1:
                ma &= -1 << (-gap - 1)
        low = min(ea, eb)
        total = ((-ma if sa else ma) << (ea - low)) + ((-mb if sb else mb) << (eb - low))
        if total == 0:
            return 0
        return self._round(1 if total < 0 else 0, abs(total), low - 150, self.model == 'nearest')

    def sub(self, a, b):
        return self.add(a, (b ^ SIGN) & M32)

    def mul(self, a, b):
        sa, ma, ea = self._split(a)
        sb, mb, eb = self._split(b)
        sign = sa ^ sb
        if ma == 0 or mb == 0:
            return sign << 31
        product = ma * mb
        raw = self._round(sign, product, ea + eb - 300, self.model == 'nearest')
        if self.mul_bias:
            drop = product.bit_length() - 24
            exp = ea + eb - 300 + drop + 150
            inexact = drop > 0 and product & ((1 << drop) - 1)
            if inexact and 1 <= exp <= 255 and (raw & FMAX) > 0x00800000:
                raw -= 1
        return raw

    def div(self, a, b):
        sa, ma, ea = self._split(a)
        sb, mb, eb = self._split(b)
        sign = sa ^ sb
        if mb == 0:
            return (sign << 31) | FMAX
        if ma == 0:
            return sign << 31
        quotient, rest = divmod(ma << 40, mb)
        quotient = (quotient << 1) | (1 if rest else 0)         # sticky bit
        return self._round(sign, quotient, ea - eb - 41, self.div_nearest or self.model == 'nearest')

    def sqrt(self, a):
        """Square root of the magnitude (the sign of a non-zero operand is ignored)."""
        sa, ma, ea = self._split(a)
        if ma == 0:
            return sa << 31
        e2 = ea - 150
        if e2 & 1:
            ma <<= 1
            e2 -= 1
        wide = ma << 48
        root = _isqrt(wide)
        root = (root << 1) | (1 if root * root != wide else 0)   # sticky bit
        return self._round(0, root, e2 // 2 - 25, self.div_nearest or self.model == 'nearest')

    def rsqrt(self, a, b):
        """The rsqrt.s instruction: a / sqrt(b), as a square root followed by a division."""
        return self.div(a, self.sqrt(b))

    def from_int(self, value):
        """cvt.s.w: signed 32-bit integer to float (truncated above 24 bits)."""
        value = s32(value)
        if value == 0:
            return 0
        return self._round(1 if value < 0 else 0, abs(value), 0, self.model == 'nearest')

    @staticmethod
    def to_int(a):
        """cvt.w.s: toward zero, saturating at -0x80000000 / 0x7fffffff.  Returns a signed int."""
        sign, mant, exp = Fpu._split(a)
        if mant == 0:
            return 0
        if exp >= 158:
            return -0x80000000 if sign else 0x7FFFFFFF
        mag = mant << (exp - 150) if exp >= 150 else mant >> (150 - exp)
        return -mag if sign else mag

    @staticmethod
    def compare(a, b):
        """-1, 0 or 1.  Sign and magnitude of the raw patterns; +0 equals -0."""
        x = -(a & FMAX) if a & SIGN else a & FMAX
        y = -(b & FMAX) if b & SIGN else b & FMAX
        return (x > y) - (x < y)


def _isqrt(n):
    """Integer square root (math.isqrt needs Python 3.8)."""
    if n < 2:
        return n
    x = 1 << ((n.bit_length() + 1) // 2)
    while True:
        y = (x + n // x) >> 1
        if y >= x:
            return x
        x = y


_fpu = Fpu()


def set_fpu(model='ps2', mul_bias=False, div_nearest=False):
    """Choose the arithmetic every function of this module uses; returns the Fpu."""
    global _fpu
    _fpu = Fpu(model, mul_bias, div_nearest)
    return _fpu


def add(a, b):
    return _fpu.add(a, b)


def sub(a, b):
    return _fpu.sub(a, b)


def mul(a, b):
    return _fpu.mul(a, b)


def div(a, b):
    return _fpu.div(a, b)


def sqrt(a):
    return _fpu.sqrt(a)


def rsqrt(a, b):
    return _fpu.rsqrt(a, b)


def neg(a):
    """neg.s: flips the sign bit, nothing else (so 0 becomes -0)."""
    return (a ^ SIGN) & M32


def fabs(a):
    """abs.s: clears the sign bit."""
    return a & FMAX


def fmax(a, b):
    """max.s: the first operand unless the second compares greater (so max(+0, -0) is the
    first one given)."""
    return a & M32 if Fpu.compare(a, b) >= 0 else b & M32


def fmin(a, b):
    """min.s: the first operand unless the second compares smaller."""
    return a & M32 if Fpu.compare(a, b) <= 0 else b & M32


def from_int(value):
    return _fpu.from_int(value)


def to_int(a):
    return Fpu.to_int(a)


def lt(a, b):
    """c.olt.s / c.lt.s"""
    return Fpu.compare(a, b) < 0


def le(a, b):
    """c.ole.s / c.le.s"""
    return Fpu.compare(a, b) <= 0


def eq(a, b):
    """c.eq.s"""
    return Fpu.compare(a, b) == 0


ZERO = 0x00000000
HALF = 0x3F000000
ONE = 0x3F800000
TWO = 0x40000000
MINUS_ONE = 0xBF800000
TWO_M16 = 0x37800000            # 1/65536: turns a 16-bit random draw into [0, 1)


def to_uint(a):
    """The compiler's float -> unsigned idiom (77 sites compare with 0x4f000000 = 2**31):
    below 2**31 a plain cvt.w.s, otherwise cvt.w.s(a - 2**31) with bit 31 set."""
    if le(0x4F000000, a):
        return (to_int(sub(a, 0x4F000000)) | SIGN) & M32
    return to_int(a) & M32


def round_half_away(a):
    """The inline rounding idiom (e.g. 0x161628): add 0.5 when 0 <= a, subtract 0.5
    otherwise, then cvt.w.s."""
    return to_int(add(a, HALF) if le(ZERO, a) else sub(a, HALF))


# =======================================================================================
# 2. Angles
# =======================================================================================

K_PI_65536 = 0x38490FDA         # pi / 65536: angle units to HALF the angle in radians
K_SIN3 = 0x3E2AAA57             # 0.16666542   (not 1/6 = 0x3e2aaaab)
K_SIN5 = 0x3C086B24             # 0.008326326
K_SIN7 = 0x39458017             # 0.00018835101
K_RAD_TO_ANGLE = 0x4622F983     # 10430.378 = 65536 / 2 pi
K_DEG_TO_ANGLE = 0x43360B60     # 182.04443 = 65536 / 360, truncated


def cos16(angle):
    """math_cos16 0x166630: cosine of a 16-bit angle.

    The angle is folded into [-0x4000, 0x3fff] (adding or subtracting half a turn flips the
    sign), halved by the constant, the sine of the half angle comes from a degree-7
    polynomial, and the result is  sign * (1 - (s + s) * s)."""
    a = s16(angle)
    sign = ONE
    if (a ^ (a << 1)) & 0x8000:             # bits 15 and 14 differ
        sign = MINUS_ONE
        a = (a & 0x7FFF) - (0x8000 if a & 0x4000 else 0)     # sign-extend from bit 14
    x = mul(from_int(a), K_PI_65536)
    x2 = mul(x, x)
    x3 = mul(x, x2)
    s = sub(x, mul(x3, K_SIN3))
    x5 = mul(x3, x2)
    s = add(s, mul(x5, K_SIN5))
    x7 = mul(x5, x2)
    s = sub(s, mul(x7, K_SIN7))
    return mul(sign, sub(ONE, mul(add(s, s), s)))


def sin16(angle):
    """math_sin16 0x1666e0: cos16(angle - 0x4000); the same code with one subtraction."""
    return cos16(angle - 0x4000)


def angle_from_radians(radians):
    """The conversion at the end of math_atan2_16 (0x1667a8): multiply by 10430.378,
    truncate toward zero, keep 16 bits."""
    return s16(to_int(mul(radians, K_RAD_TO_ANGLE)))


def angle_from_degrees(degrees):
    """Inline at 0x1985b0 and others: multiply by 182.04443, truncate, keep 16 bits.
    (Some sites round with round_half_away instead; see docs/spec/core.md.)"""
    return s16(to_int(mul(degrees, K_DEG_TO_ANGLE)))


def atan2_16(y, x):
    """math_atan2_16 0x166798 (f12 = y, f13 = x): the C library's atan2f, then
    angle_from_radians."""
    return angle_from_radians(atan2f(y, x))


def angle_turn_dir(a, b):
    """angle_turnDir 0x166bc8 -> (direction, absolute difference).

    direction is -1 when the 16-bit difference a - b is positive, +1 otherwise (so +1 for
    equal angles and for a difference of exactly -0x8000).  The absolute difference is
    what the code stores through its third argument when that is not null; -0x8000 gives
    0x8000."""
    diff = s16(s16(a) - s16(b))
    return (-1 if diff > 0 else 1), (-diff if diff < 0 else diff)


def angle_approach(rate, min_step, max_step, current, target):
    """angle_approach 0x166c18 (f12 rate, f13 min, f14 max, a0 current, a1 target).

    step = |current - target| * rate, raised to min_step, lowered to max_step (a limit of
    exactly -1.0 is disabled), truncated; the result is current -/+ step, 16 bits.  The
    step is NOT limited to the remaining difference: min_step can carry the angle past the
    target."""
    cur = s16(current)
    diff = s16(cur - s16(target))
    direction = -1 if diff > 0 else 1
    step = mul(from_int(-diff if diff < 0 else diff), rate)
    if not eq(min_step, MINUS_ONE) and lt(step, min_step):
        step = min_step
    if not eq(max_step, MINUS_ONE) and lt(max_step, step):
        step = max_step
    return s16(s32(to_int(step) * direction) + cur)


# =======================================================================================
# 3. Scalars and colours
# =======================================================================================

THREE = 0x40400000
MINUS_TWO = 0xC0000000


def _hermite_basis(t):
    """The four weights as vec3_hermite forms them: (2t3 - 3t2 + 1, -2t3 + 3t2,
    t3 - 2t2 + t, t3 - t2) with these exact groupings."""
    t2 = mul(t, t)
    t3 = mul(t2, t)
    three_t2 = mul(t2, THREE)
    h00 = add(sub(add(t3, t3), three_t2), ONE)
    h01 = add(mul(t3, MINUS_TWO), three_t2)
    h10 = add(sub(t3, add(t2, t2)), t)
    h11 = sub(t3, t2)
    return h00, h01, h10, h11


def hermite(t, p0, p1, m0, m1):
    """math_hermite 0x1658f0 (five floats): scalar cubic Hermite.  Unlike the vector
    version the first term is  (2t3 - 3t2) * p0 + p0.  hermite(t, 0, 1, 0, 0) is the
    smoothstep used by the camera and the animation blend."""
    t2 = mul(t, t)
    t3 = mul(t2, t)
    three_t2 = mul(t2, THREE)
    value = add(mul(sub(add(t3, t3), three_t2), p0), p0)
    value = add(value, mul(add(mul(t3, MINUS_TWO), three_t2), p1))
    value = add(value, mul(add(sub(t3, add(t2, t2)), t), m0))
    return add(value, mul(sub(t3, t2), m1))


def log2_floor(x):
    """math_log2Floor 0x1665f0: floor(log2(x)) for x >= 1; 0 for x <= 1, negative x
    included (the argument is tested as a 64-bit register)."""
    if x < 0:
        return 0
    return (x >> 1).bit_length()


def color_scale_clamped(factor, rgba):
    """color_scaleClamped 0x165428 (f12 factor, a0 colour) -> colour: each of the four bytes
    becomes trunc(byte * factor) limited to 0..255."""
    out = 0
    for shift in (0, 8, 16, 24):
        value = to_int(mul(from_int((rgba >> shift) & 0xFF), factor))
        value = 255 if value > 255 else value
        value = 0 if value < 0 else value
        out |= value << shift
    return out


K_255 = 0x437F0000
SIX = 0x40C00000


def color_from_hsv(h, s, v):
    """0x164f10 (three floats, each clamped to 0..1) -> 0xff000000 | B << 16 | G << 8 | R.
    The sector is trunc(h * 6); h = 1.0 gives sector 6, which returns opaque black."""
    def clamp(x):
        if lt(x, ZERO):
            x = ZERO
        if lt(ONE, x):
            x = ONE
        return x

    def byte(x):
        return to_uint(mul(x, K_255))

    h, s, v = clamp(h), clamp(s), clamp(v)
    if eq(s, ZERO):
        return (0xFF000000 | byte(v) | (byte(v) << 16) | (byte(v) << 8)) & M32
    h6 = mul(h, SIX)
    sector = to_int(h6)
    frac = sub(h6, from_int(sector))
    p = mul(v, sub(ONE, s))
    q = mul(v, sub(ONE, mul(s, frac)))
    t = mul(v, sub(ONE, mul(s, sub(ONE, frac))))
    table = {0: (v, t, p), 1: (q, v, p), 2: (p, v, t), 3: (p, q, v), 4: (t, p, v), 5: (v, p, q)}
    if sector not in table:
        return 0xFF000000
    red, green, blue = table[sector]
    return (0xFF000000 | byte(red) | (byte(blue) << 16) | (byte(green) << 8)) & M32


# =======================================================================================
# 4. Vectors and boxes
# =======================================================================================

def _dot3(a0, b0, a1, b1, a2, b2):
    """(a0*b0 + a1*b1) + a2*b2 - the grouping every product in this library uses."""
    return add(add(mul(a0, b0), mul(a1, b1)), mul(a2, b2))


def vec3_hermite(t, p0, p1, m0, m1):
    """vec3_hermite 0x162310 (f12 t, a0..a3 the four vectors, t0 out): cubic Hermite on
    three components,  ((p0*h00 + p1*h01) + m0*h10) + m1*h11."""
    h00, h01, h10, h11 = _hermite_basis(t)
    return [add(add(add(mul(p0[i], h00), mul(p1[i], h01)), mul(m0[i], h10)), mul(m1[i], h11))
            for i in range(3)]


def vec3_hermite_derivative(t, p0, p1, m0, m1):
    """0x162440 (same arguments as vec3_hermite; no caller found): the derivative,
    weights 6t2 - 6t, -6t2 + 6t, 3t2 - 4t + 1, 3t2 - 2t."""
    t2 = mul(t, t)
    six_t = mul(t, SIX)
    three_t2 = mul(t2, THREE)
    d00 = sub(mul(t2, SIX), six_t)
    d01 = add(mul(t2, 0xC0C00000), six_t)
    d10 = add(sub(three_t2, mul(t, 0x40800000)), ONE)
    d11 = sub(three_t2, add(t, t))
    return [add(add(add(mul(p0[i], d00), mul(p1[i], d01)), mul(m0[i], d10)), mul(m1[i], d11))
            for i in range(3)]


def vec3_dot_delta(a, n, b):
    """vec3_dotDelta 0x1667d8 (a0 a, a1 n, a2 b) -> dot(n, b - a)."""
    return _dot3(n[0], sub(b[0], a[0]), n[1], sub(b[1], a[1]), n[2], sub(b[2], a[2]))


def vec2_dot_delta(a, n, b):
    """vec2_dotDelta 0x166820: the two-component version."""
    return add(mul(n[0], sub(b[0], a[0])), mul(n[1], sub(b[1], a[1])))


K_1000 = 0x447A0001             # 1000.00006: 1 / const('0.001')
K_0_001 = 0x3A83126E


def ray_plane_distance(point, direction, plane_point, normal):
    """0x163658 (a0 point, a1 direction, a2 a point on the plane, a3 normal) -> float.

    Returns -1.0 when the direction does not face the plane (0 <= direction . normal) or
    the point is behind it; otherwise  h * (h / d)  with h = normal . (point - plane_point)
    and d = -(direction . (normal * h)), or  h * (h * 1000.00006)  when |d| <= 0.001."""
    facing = _dot3(direction[0], normal[0], direction[1], normal[1], direction[2], normal[2])
    height = _dot3(normal[0], sub(point[0], plane_point[0]),
                   normal[1], sub(point[1], plane_point[1]),
                   normal[2], sub(point[2], plane_point[2]))
    if le(ZERO, facing) or lt(height, ZERO):
        return MINUS_ONE
    scaled = [mul(normal[0], height), mul(normal[1], height), mul(normal[2], height)]
    denom = neg(_dot3(scaled[0], direction[0], scaled[1], direction[1], scaled[2], direction[2]))
    if lt(K_0_001, fabs(denom)):
        return mul(height, div(height, denom))
    return mul(height, mul(height, K_1000))


K_0_01 = 0x3C23D70A
QUARTER = 0x3E800000


def segment_hits_plane_near_edge(a, b, normal, p1, p0):
    """0x163790 (a0 a, a1 b, a2 normal, a3 p1, t0 p0, t1 out) -> (hit flag, point or None).

    The segment p0 -> p1 must run against the normal; it is cut by the plane through a at
    t = normal . (a - p0) / normal . (p1 - p0)  (the divisor pushed out to +/-0.01), 0 <= t
    <= 1.  The point p0 + (p1 - p0) * t is stored; the function returns 1 when its
    projection on the edge b -> a lies within [-0.25, |a - b| + 0.25].  The point is
    written even when that last test fails."""
    d = [sub(p1[i], p0[i]) for i in range(3)]
    if le(ZERO, _dot3(d[0], normal[0], d[1], normal[1], d[2], normal[2])):
        return 0, None
    e = [sub(a[i], p0[i]) for i in range(3)]
    num = _dot3(e[0], normal[0], e[1], normal[1], e[2], normal[2])
    den = _dot3(d[0], normal[0], d[1], normal[1], d[2], normal[2])
    if lt(ZERO, den) and lt(den, K_0_01):
        den = K_0_01
    if lt(den, ZERO) and lt(neg(K_0_01), den):
        den = neg(K_0_01)
    t = div(num, den)
    if lt(t, ZERO) or lt(ONE, t):
        return 0, None
    point = [add(p0[i], mul(d[i], t)) for i in range(3)]
    edge = [sub(a[i], b[i]) for i in range(3)]
    length = sqrt(add(add(mul(edge[0], edge[0]), mul(edge[1], edge[1])), mul(edge[2], edge[2])))
    inv = div(ONE, length)
    unit = [mul(edge[i], inv) for i in range(3)]
    along = _dot3(unit[0], sub(point[0], b[0]), unit[1], sub(point[1], b[1]),
                  unit[2], sub(point[2], b[2]))
    if lt(along, neg(QUARTER)):
        return 0, point
    if lt(add(length, QUARTER), along):
        return 0, point
    return 1, point


K_BIG = 0x4B189680              # 10,000,000.0


def bbox_set_empty():
    """bbox_setEmpty 0x166ec0: min = +10,000,000, max = -10,000,000."""
    return [K_BIG] * 3 + [neg(K_BIG)] * 3


def bbox_union(a, b):
    """bbox_union 0x166cc0 (a0 a, a1 b): a grows to hold b; returns the new a."""
    out = list(a)
    for i in range(3):
        if lt(b[i], out[i]):
            out[i] = b[i]
    for i in range(3, 6):
        if lt(out[i], b[i]):
            out[i] = b[i]
    return out


def bbox_add_point(box, point):
    """0x166d40 (no caller found): grow the box to hold a point."""
    out = list(box)
    for i in range(3):
        if lt(point[i], out[i]):
            out[i] = point[i]
    for i in range(3):
        if lt(out[3 + i], point[i]):
            out[3 + i] = point[i]
    return out


def bbox_contains_point(box, point):
    """0x166dc0 (no caller found): 1 when min <= point <= max on all three axes."""
    for i in range(3):
        if not le(box[i], point[i]) or not le(point[i], box[3 + i]):
            return 0
    return 1


def bbox_overlaps(a, b):
    """0x166e38 (no caller found): 1 unless the boxes are separated on some axis
    (touching counts as overlapping)."""
    for i in range(3):
        if lt(a[3 + i], b[i]):
            return 0
    for i in range(3):
        if lt(b[3 + i], a[i]):
            return 0
    return 1


# =======================================================================================
# 5. Matrices
# =======================================================================================

def mat3_set_identity():
    """mat3_setIdentity 0x165650."""
    return [ONE, 0, 0, 0, ONE, 0, 0, 0, ONE]


def mat34_set_identity():
    """mat34_setIdentity 0x165680."""
    return mat3_set_identity() + [0, 0, 0]


def mat34_set_translation(pos):
    """mat34_setTranslation 0x166850 (a0 m, a1 pos)."""
    return mat3_set_identity() + list(pos[:3])


def mat3_mul(a, b):
    """mat3_mul 0x165710 (a0 out, a1 a, a2 b): out[r][c] = (a[r][0]*b[0][c] + a[r][1]*b[1][c])
    + a[r][2]*b[2][c].  Built in a temporary: out may be a or b."""
    return [_dot3(a[3 * r], b[c], a[3 * r + 1], b[3 + c], a[3 * r + 2], b[6 + c])
            for r in range(3) for c in range(3)]


def mat34_mul_mat3(a, b):
    """mat34_mulMat3 0x162580 (a0 out, a1 mat3 a, a2 mat34 b): rotation a * b, translation
    copied from b."""
    return mat3_mul(a, b) + list(b[9:12])


def mat34_mul(a, b):
    """mat34_mul 0x162808 (a0 out, a1 a, a2 b): rotation as mat3_mul; translation row
    ((a[9]*b[0][c] + a[10]*b[1][c]) + a[11]*b[2][c]) + b[9 + c]."""
    return mat3_mul(a, b) + [add(_dot3(a[9], b[c], a[10], b[3 + c], a[11], b[6 + c]), b[9 + c])
                             for c in range(3)]


def mat4_mul_mat34(a, b):
    """mat4_mulMat34 0x162698 (a0 out mat4, a1 mat34 a, a2 mat4 b): a taken as a 4x4 whose
    last column is 0, 0, 0, 1."""
    out = [_dot3(a[3 * r], b[c], a[3 * r + 1], b[4 + c], a[3 * r + 2], b[8 + c])
           for r in range(3) for c in range(4)]
    return out + [add(_dot3(a[9], b[c], a[10], b[4 + c], a[11], b[8 + c]), b[12 + c])
                  for c in range(4)]


def mat4_mul(a, b):
    """mat4_mul 0x1657e0 (no caller found): ((a0*b0 + a1*b1) + a2*b2) + a3*b3 per element."""
    return [add(_dot3(a[4 * r], b[c], a[4 * r + 1], b[4 + c], a[4 * r + 2], b[8 + c]),
                mul(a[4 * r + 3], b[12 + c]))
            for r in range(4) for c in range(4)]


def _rotate_rows(m, width, axis, angle):
    """Rotate two rows of a matrix with rows of `width` floats (pre-multiplication)."""
    c, s = cos16(angle), sin16(angle)
    out = list(m)
    if axis == 0:
        first, second, sign = 1, 2, 1
    elif axis == 1:
        first, second, sign = 0, 2, -1
    elif axis == 2:
        first, second, sign = 0, 1, 1
    else:
        return out
    for k in range(width):
        p, q = m[first * width + k], m[second * width + k]
        if sign > 0:        # first' = c*first + s*second ; second' = (-s)*first + c*second
            out[first * width + k] = add(mul(c, p), mul(s, q))
            out[second * width + k] = add(mul(neg(s), p), mul(c, q))
        else:               # axis 1: first' = c*first - s*second ; second' = s*first + c*second
            out[first * width + k] = sub(mul(c, p), mul(s, q))
            out[second * width + k] = add(mul(s, p), mul(c, q))
    return out


def mat3_rotate_axis(m, axis, angle):
    """mat3_rotateAxis 0x162960 and mat34_rotateAxis 0x163000 (a0 m, a1 axis 0/1/2 = X/Y/Z,
    a2 angle), in place; identical bodies that touch only the first nine floats.  Any other
    axis value leaves the matrix alone."""
    return _rotate_rows(m[:9], 3, axis, angle) + list(m[9:])


mat34_rotate_axis = mat3_rotate_axis


def mat4_rotate_axis(m, axis, angle):
    """0x163208 (no caller found): the same on the rows of a mat4."""
    return _rotate_rows(m, 4, axis, angle)


def _rotate_columns(m, rows, axis, angle):
    """Rotate two columns of a 3-column matrix with `rows` rows (post-multiplication)."""
    c, s = cos16(angle), sin16(angle)
    out = list(m)
    if axis == 0:
        first, second, sign = 1, 2, 1
    elif axis == 1:
        first, second, sign = 0, 2, -1
    elif axis == 2:
        first, second, sign = 0, 1, 1
    else:
        return out
    for r in range(rows):
        p, q = m[3 * r + first], m[3 * r + second]
        if sign > 0:        # first' = c*first - s*second ; second' = s*first + c*second
            out[3 * r + first] = sub(mul(c, p), mul(s, q))
            out[3 * r + second] = add(mul(s, p), mul(c, q))
        else:               # axis 1: first' = c*first + s*second ; second' = (-s)*first + c*second
            out[3 * r + first] = add(mul(c, p), mul(s, q))
            out[3 * r + second] = add(mul(neg(s), p), mul(c, q))
    return out


def mat3_rotate_axis_post(m, axis, angle):
    """0x162df0 (a0 m, a1 axis, a2 angle; one caller, 0x179030): rotates two COLUMNS of the
    3x3 part, i.e. applies the rotation before the matrix instead of after it."""
    return _rotate_columns(m[:9], 3, axis, angle) + list(m[9:])


def mat34_rotate_axis_post(m, axis, angle):
    """0x162b68 (no caller found): as mat3_rotate_axis_post on all four rows of a mat34."""
    return _rotate_columns(m[:12], 4, axis, angle) + list(m[12:])


def mat3_set_rot_z(angle):
    """mat3_setRotZ 0x1639d8 (a0 m, a1 angle): the cosine and sine code is inlined, with the
    same operations as cos16 and sin16."""
    c, s = cos16(angle), sin16(angle)
    return [c, s, 0, neg(s), c, 0, 0, 0, ONE]


def mat34_set_pos_rot_z(pos, angle):
    """mat34_setPosRotZ 0x163b30 (a0 m, a1 pos, a2 angle): the usual object matrix."""
    return mat3_set_rot_z(angle) + list(pos[:3])


def mat34_set_pos_rot_z_scale(scale, pos, angle):
    """mat34_setPosRotZScale 0x163cb8 (f12 scale, a0 m, a1 pos, a2 angle).  m[3] is the
    negation of the product sin * scale, not (-sin) * scale."""
    c, s = mul(cos16(angle), scale), mul(sin16(angle), scale)
    return [c, s, 0, neg(s), c, 0, 0, 0, scale] + list(pos[:3])


def mat34_set_pos_euler_scale(scale, pos, yaw, pitch, roll):
    """mat34_setPosEulerScale 0x163e48 (f12 scale, a0 m, a1 pos, a2 yaw, a3 pitch, t0 roll):
    identity, then rotate about Z by yaw + 0x4000, about Y by pitch, about X by roll (three
    mat34_rotateAxis calls), then the nine rotation floats times scale."""
    m = mat34_set_translation(pos)
    m = mat34_rotate_axis(m, 2, s16(yaw + 0x4000))
    m = mat34_rotate_axis(m, 1, s16(pitch))
    m = mat34_rotate_axis(m, 0, s16(roll))
    return [mul(x, scale) for x in m[:9]] + m[9:]


K_SINGULAR = 0x38D1B717         # 0.0001 (truncated)


def mat4_invert(m):
    """mat4_invert 0x163f98 (a0 out, a1 in): Gauss-Jordan on a copy of the input.

    For each index c = 0..3: look along row c (elements 4c+c .. 4c+3) for the entry of
    largest magnitude (a later entry wins only when strictly larger), swap that column
    with column c in both matrices, stop with the IDENTITY as the answer when the
    magnitude is <= 0.0001, multiply column c by 1/pivot, and subtract column c times
    element [c][j] from every other column j.  Because the input is copied first, out may
    be the input."""
    work = list(m)
    out = [ONE, 0, 0, 0, 0, ONE, 0, 0, 0, 0, ONE, 0, 0, 0, 0, ONE]
    for c in range(4):
        pivot = work[5 * c]
        best = fabs(pivot)
        pick = c
        for j in range(c + 1, 4):
            candidate = work[4 * c + j]
            if lt(best, fabs(candidate)):
                pivot, best, pick = candidate, fabs(candidate), j
        if pick != c:
            for k in range(4):
                out[4 * k + c], out[4 * k + pick] = out[4 * k + pick], out[4 * k + c]
                work[4 * k + c], work[4 * k + pick] = work[4 * k + pick], work[4 * k + c]
        if le(best, K_SINGULAR):
            return [ONE, 0, 0, 0, 0, ONE, 0, 0, 0, 0, ONE, 0, 0, 0, 0, ONE]
        inverse = div(ONE, pivot)
        for k in range(4):
            work[4 * k + c] = mul(work[4 * k + c], inverse)
            out[4 * k + c] = mul(out[4 * k + c], inverse)
        for j in range(4):
            if j == c:
                continue
            factor = work[4 * c + j]
            for k in range(4):
                work[4 * k + j] = sub(work[4 * k + j], mul(work[4 * k + c], factor))
                out[4 * k + j] = sub(out[4 * k + j], mul(out[4 * k + c], factor))
    return out


def mat34_invert(m):
    """mat34_invert 0x164288 (a0 out, a1 in): widen to 4x4 with last column 0, 0, 0, 1,
    mat4_invert in place, keep the first three columns."""
    wide = []
    for r in range(4):
        wide += [m[3 * r], m[3 * r + 1], m[3 * r + 2], ONE if r == 3 else 0]
    inverse = mat4_invert(wide)
    return [inverse[4 * r + c] for r in range(4) for c in range(3)]


def mat3_transpose(m):
    """mat3_transpose 0x166298 (a0 out, a1 m).  Built in a temporary."""
    return [m[0], m[3], m[6], m[1], m[4], m[7], m[2], m[5], m[8]]


def mat3_scale(s, m):
    """mat3_scale 0x165cc0 (f12 s, a0 m), in place."""
    return [mul(x, s) for x in m[:9]] + list(m[9:])


def mat3_scale_xyz(sx, sy, sz, m):
    """mat3_scaleXYZ 0x165d30 (f12 f13 f14, a0 m): row 0 by sx, row 1 by sy, row 2 by sz."""
    return ([mul(x, sx) for x in m[0:3]] + [mul(x, sy) for x in m[3:6]]
            + [mul(x, sz) for x in m[6:9]] + list(m[9:]))


def mat4_scale_rotation(s, m):
    """mat4_scaleRotation 0x165b98 (f12 s, a0 mat4): the 3x3 part of a mat4 times s."""
    out = list(m)
    for r in range(3):
        for c in range(3):
            out[4 * r + c] = mul(m[4 * r + c], s)
    return out


def mat34_translate_local(x, y, z, m):
    """mat34_translateLocal 0x165b10 (f12 f13 f14, a0 m): translation += (x, y, z) * rotation,
    as  t[c] + ((m[0][c]*x + m[1][c]*y) + m[2][c]*z)."""
    out = list(m)
    for c in range(3):
        out[9 + c] = add(m[9 + c], _dot3(m[c], x, m[3 + c], y, m[6 + c], z))
    return out


def mat4_translate_local(x, y, z, m):
    """mat4_translateLocal 0x165c08 (f12 f13 f14, a0 mat4): the same on all four columns of
    the last row."""
    out = list(m)
    for c in range(4):
        out[12 + c] = add(m[12 + c], _dot3(m[c], x, m[4 + c], y, m[8 + c], z))
    return out


def mat3_mul_vec(m, v):
    """mat3_mulVec 0x165e40 and mat34_rotateVec 0x166158 (a0 out, a1 m, a2 v):
    out[c] = (v.x*m[0][c] + v.y*m[1][c]) + v.z*m[2][c].  The vector is copied first: out may
    be v."""
    return [_dot3(m[c], v[0], m[3 + c], v[1], m[6 + c], v[2]) for c in range(3)]


mat34_rotate_vec = mat3_mul_vec


def mat3_mul_vec_transposed(m, v):
    """mat3_mulVecTransposed 0x165da0 and its duplicate 0x1661f8 (a0 out, a1 m, a2 v):
    out[r] = dot(row r, v), the inverse rotation of an orthonormal matrix."""
    return [_dot3(m[3 * r], v[0], m[3 * r + 1], v[1], m[3 * r + 2], v[2]) for r in range(3)]


def mat34_transform_point(m, v):
    """mat34_transformPoint 0x1660a0 (a0 out, a1 m, a2 v): rotate, then add the translation
    as the LAST term:  ((v.x*m[0][c] + v.y*m[1][c]) + v.z*m[2][c]) + m[3][c]."""
    return [add(_dot3(m[c], v[0], m[3 + c], v[1], m[6 + c], v[2]), m[9 + c]) for c in range(3)]


def mat4_transform_point(m, v):
    """mat4_transformPoint 0x165ee0 (a0 out, a1 mat4, a2 v) -> (point, w).  The three
    coordinates are stored undivided; w is returned in f0."""
    out = [add(_dot3(m[c], v[0], m[4 + c], v[1], m[8 + c], v[2]), m[12 + c]) for c in range(4)]
    return out[:3], out[3]


def mat4_transform_point_transposed(m, v):
    """0x165fc0 (a0 out, a1 mat4, a2 v; one caller) -> (point, w): the same with the matrix
    read by columns, out[r] = ((m[r][0]*v.x + m[r][1]*v.y) + m[r][2]*v.z) + m[r][3]; w is
    built from elements 3, 7, 11 and 15."""
    out = [add(_dot3(m[4 * r], v[0], m[4 * r + 1], v[1], m[4 * r + 2], v[2]), m[4 * r + 3])
           for r in range(3)]
    return out, add(_dot3(m[3], v[0], m[7], v[1], m[11], v[2]), m[15])


def mat4_set_projection(sx, sy, scale, z_a, z_b, near, far):
    """mat4_setProjection 0x165950 (f12..f18 in this order, a0 out)."""
    k = div(mul(sub(z_b, z_a), far), sub(far, near))
    out = [0] * 16
    out[0] = mul(scale, sx)
    out[5] = mul(scale, sy)
    out[10] = sub(z_b, k)
    out[11] = ONE
    out[14] = div(mul(mul(sub(z_b, z_a), far), near), sub(far, near))
    return out


def mat4_set_projection_fixed(sx, sy, scale, z_a, z_b, near, far):
    """0x1659d0 and its duplicate 0x165a70 (same arguments): as mat4_setProjection with the
    two depth terms multiplied by 16.0 and then by 2**46 (0x56800000)."""
    out = mat4_set_projection(sx, sy, scale, z_a, z_b, near, far)
    out[10] = mul(mul(out[10], 0x41800000), 0x56800000)
    out[14] = mul(mul(out[14], 0x41800000), 0x56800000)
    return out


def mat4_from_mat3_pos(m, pos):
    """0x166340 (a0 out mat4, a1 mat3, a2 pos; no caller found): the TRANSPOSE of the 3x3
    goes into the upper left, the position into the last row, last column 0, 0, 0, 1."""
    return [m[0], m[3], m[6], 0, m[1], m[4], m[7], 0, m[2], m[5], m[8], 0,
            pos[0], pos[1], pos[2], ONE]


# =======================================================================================
# 6. Quaternions (x, y, z, w)
# =======================================================================================

def quat_from_axis_angle(x, y, z, angle):
    """quat_fromAxisAngle 0x1663c0 (f12 f13 f14 axis, a0 out, a1 angle): the half angle is
    s16(angle) >> 1; the axis is normalised with rsqrt.s(1.0, (x*x + y*y) + z*z), and each
    component is  (sin * 1/length) * axis."""
    half = s16(angle) >> 1
    inverse = rsqrt(ONE, add(add(mul(x, x), mul(y, y)), mul(z, z)))
    s = mul(sin16(half), inverse)
    return [mul(s, x), mul(s, y), mul(s, z), cos16(half)]


def quat_mul(a, b):
    """quat_mul 0x166480 (a0 out, a1 a, a2 b)."""
    return [
        add(add(mul(a[3], b[0]), mul(b[3], a[0])), sub(mul(a[1], b[2]), mul(a[2], b[1]))),
        add(add(mul(a[3], b[1]), mul(b[3], a[1])), sub(mul(a[2], b[0]), mul(a[0], b[2]))),
        add(add(mul(a[3], b[2]), mul(b[3], a[2])), sub(mul(a[0], b[1]), mul(a[1], b[0]))),
        sub(mul(a[3], b[3]), _dot3(a[0], b[0], a[1], b[1], a[2], b[2])),
    ]


def quat_normalize(q):
    """quat_normalize 0x166550 (a0 q), in place: each component times
    rsqrt.s(1.0, ((w*w + x*x) + y*y) + z*z)."""
    n = add(add(add(mul(q[3], q[3]), mul(q[0], q[0])), mul(q[1], q[1])), mul(q[2], q[2]))
    inverse = rsqrt(ONE, n)
    return [mul(c, inverse) for c in q[:4]]


def quat_rotate_vec(q, v):
    """quat_rotateVec 0x163490 (a0 out, a1 q, a2 v): q * (v, 0) * conj(q), not divided by
    the norm.  Built in a temporary."""
    x, y, z, w = q[0], q[1], q[2], q[3]
    tw = neg(_dot3(x, v[0], y, v[1], z, v[2]))
    tx = add(mul(w, v[0]), sub(mul(y, v[2]), mul(z, v[1])))
    ty = add(mul(w, v[1]), sub(mul(z, v[0]), mul(x, v[2])))
    tz = add(mul(w, v[2]), sub(mul(x, v[1]), mul(y, v[0])))
    nx, ny, nz = neg(x), neg(y), neg(z)
    return [
        add(add(mul(tw, nx), mul(w, tx)), sub(mul(ty, nz), mul(tz, ny))),
        add(add(mul(tw, ny), mul(w, ty)), sub(mul(tz, nx), mul(tx, nz))),
        add(add(mul(tw, nz), mul(w, tz)), sub(mul(tx, ny), mul(ty, nx))),
    ]


def quat_from_mat3(m):
    """quat_fromMat3 0x164330 (a0 out, a1 m).

    With trace = (m[0] + m[4]) + m[8] > 0:  r = sqrt(trace + 1), w = r * 0.5, and x, y, z =
    (m[5]-m[7], m[6]-m[2], m[1]-m[3]) * (0.5 / r).  Otherwise the largest diagonal element
    i is chosen (1 if m[0] < m[4]; then 2 if that one < m[8]), j and k follow cyclically,
    r = sqrt((m[ii] - (m[jj] + m[kk])) + 1), q[i] = r * 0.5, and with s = 0.5 / r (s stays r
    when r is 0):  w = (m[jk] - m[kj]) * s,  q[j] = (m[ij] + m[ji]) * s,
    q[k] = (m[ik] + m[ki]) * s."""
    trace = add(add(m[0], m[4]), m[8])
    if lt(ZERO, trace):
        r = sqrt(add(trace, ONE))
        s = div(HALF, r)
        return [mul(sub(m[5], m[7]), s), mul(sub(m[6], m[2]), s), mul(sub(m[1], m[3]), s),
                mul(r, HALF)]
    i = 1 if lt(m[0], m[4]) else 0
    if lt(m[4 * i], m[8]):
        i = 2
    j = (1, 2, 0)[i]
    k = (1, 2, 0)[j]
    r = sqrt(add(sub(m[4 * i], add(m[4 * j], m[4 * k])), ONE))
    q = [0, 0, 0, 0]
    q[i] = mul(r, HALF)
    s = r if eq(r, ZERO) else div(HALF, r)
    q[3] = mul(sub(m[3 * j + k], m[3 * k + j]), s)
    q[j] = mul(add(m[3 * i + j], m[3 * j + i]), s)
    q[k] = mul(add(m[3 * i + k], m[3 * k + i]), s)
    return q


def mat3_from_quat(q):
    """mat3_fromQuat 0x1668b8 (a0 m, a1 q).  s = 2.0 / (((x*x + y*y) + z*z) + w*w), then
    xs, ys, zs = x*s, y*s, z*s and every product is  component * (other * s)."""
    x, y, z, w = q[0], q[1], q[2], q[3]
    s = div(TWO, add(add(add(mul(x, x), mul(y, y)), mul(z, z)), mul(w, w)))
    xs, ys, zs = mul(x, s), mul(y, s), mul(z, s)
    xx, yy, zz = mul(x, xs), mul(y, ys), mul(z, zs)
    xy, xz, yz = mul(x, ys), mul(x, zs), mul(y, zs)
    wx, wy, wz = mul(w, xs), mul(w, ys), mul(w, zs)
    return [sub(ONE, add(yy, zz)), add(xy, wz), sub(xz, wy),
            sub(xy, wz), sub(ONE, add(xx, zz)), add(yz, wx),
            add(xz, wy), sub(yz, wx), sub(ONE, add(xx, yy))]


def mat34_from_quat(q):
    """mat34_fromQuat 0x166988 (a0 m, a1 q): mat3_fromQuat with a zero translation."""
    return mat3_from_quat(q) + [0, 0, 0]


def mat4_from_quat(q, old):
    """0x166a68 (a0 out mat4, a1 q; no caller found): the transpose of mat3_fromQuat in the
    upper left, elements 3, 7 and 11 zero; the last row is NOT written (old supplies it)."""
    r = mat3_from_quat(q)
    return [r[0], r[3], r[6], 0, r[1], r[4], r[7], 0, r[2], r[5], r[8], 0] + list(old[12:16])


# =======================================================================================
# 7. Noise
# =======================================================================================

K_1_16 = 0x3D800000
K_1_32768 = 0x38000000
K_40000 = 0x471C4000


def noise(table, index):
    """math_noise 0x166b48 (a0 index) -> float.  table is the 256 signed 16-bit entries of
    g_noiseTable 0x6e0d90.  Linear interpolation between entries (index >> 4) & 255 and the
    next one, weight (index & 15) / 16, scaled by 1/32768.  The period is 4096."""
    index = s32(index)
    frac = mul(from_int(index & 0xF), K_1_16)
    low = table[(index >> 4) & 0xFF]
    high = table[((index >> 4) + 1) & 0xFF]
    value = add(mul(from_int(low), sub(ONE, frac)), mul(from_int(high), frac))
    return mul(value, K_1_32768)


def noise3(table, index, step):
    """0x164578 (a0 out, a1 index, a2 step; no caller found): three samples at index,
    index + step and index + 2 * step."""
    return [noise(table, index), noise(table, index + step), noise(table, index + 2 * step)]


def build_noise_table(seed, stale=(0, 0, 0), weights=None):
    """math_buildNoiseTable 0x1646c8 -> (256 signed 16-bit entries, seed afterwards).

    seed is g_cosmeticSeed 0x404460, which at this point holds the CPU cycle counter: the
    table is different on every boot.  Four octaves: octave k draws a new target every
    2**k entries (value - 0.5 from the cosmetic generator; 0 for entries 241 and up so the
    table closes on itself) and walks toward it in 2**k equal steps; the entry is the sum
    of the four accumulators weighted 1/8, 1/4, 1/2, 1 (computed with powf(2**(3-k), -1.0)),
    times 40000, truncated.

    Only accumulator 0 is cleared by the code.  Accumulators 1..3 start from whatever the
    three stack words at sp+4, sp+8 and sp+0xc held (sp after the function's own 0x60-byte
    frame); stale gives those three patterns."""
    if weights is None:
        weights = [powf(from_int(1 << (3 - k)), MINUS_ONE) for k in range(4)]
    rng = Lcg(seed)
    acc = [ZERO, stale[0], stale[1], stale[2]]
    slope = [ZERO, ZERO, ZERO, ZERO]
    table = []
    for n in range(256):
        for k in range(4):
            if n & ((1 << k) - 1) == 0:
                target = sub(mul(from_int(rng.draw()), TWO_M16), HALF)
                if n >= 0xF1:
                    target = ZERO
                slope[k] = mul(sub(target, acc[k]), div(ONE, from_int(1 << k)))
            acc[k] = add(acc[k], slope[k])
        total = ZERO
        for k in range(4):
            total = add(total, mul(acc[k], weights[k]))
        table.append(s16(to_int(mul(total, K_40000))))
    return table, rng.state


# =======================================================================================
# 8. C-library routines the engine reaches (newlib, compiled for the console's FPU)
# =======================================================================================
# The coefficients are fdlibm's published decimal constants; const() applies the
# compiler's truncation, which changes the last bit of 6 of the 19 table entries.
# difftest_core.py checks every table against the executable (property "libm tables").

K_HUGE = 0x7149F2C9             # 1.0e30
K_TINY = 0x0DA2425F             # 1.0e-30
K_PI = 0x40490FDA
K_PI_2 = 0x3FC90FDA
K_PI_LO = 0x34222168

LIBM_DECIMALS = []              # every decimal literal the tables below were made from
LIBM_TABLES = []                # (address, patterns, name) of tables beyond the three of atanf


def _table(*texts):
    LIBM_DECIMALS.extend(texts)
    return [const(text) for text in texts]


ATAN_HI = _table('4.6364760399e-01', '7.8539812565e-01', '9.8279368877e-01',
                 '1.5707962513e+00')                            # 0x562058
ATAN_LO = _table('5.0121582440e-09', '3.7748947079e-08', '3.4473217170e-08',
                 '7.5497894159e-08')                            # 0x562068
ATAN_T = _table('3.3333334327e-01', '-2.0000000298e-01', '1.4285714924e-01',
                '-1.1111110449e-01', '9.0908870101e-02', '-7.6918758452e-02',
                '6.6610731184e-02', '-5.8335702866e-02', '4.9768779427e-02',
                '-3.6531571299e-02', '1.6285819933e-02')        # 0x562078


def atanf(x):
    """libm_atanf 0x3aa558.  Range tests are on the bit pattern; the NaN and infinity
    branches of the C source are absent."""
    hx = s32(x)
    ix = x & FMAX
    if ix > 0x507FFFFF:                             # |x| >= 2**34
        if hx > 0:
            return add(ATAN_HI[3], ATAN_LO[3])
        return sub(neg(ATAN_HI[3]), ATAN_LO[3])
    if ix <= 0x3EDFFFFF:                            # |x| < 0.4375
        if ix <= 0x30FFFFFF and lt(ONE, add(x, K_HUGE)):       # |x| < 2**-29
            return x
        index = -1
    else:
        x = fabs(x)
        if ix <= 0x3F97FFFF:                        # |x| < 1.1875
            if ix <= 0x3F2FFFFF:                    # 7/16 <= |x| < 11/16
                index = 0
                x = div(sub(add(x, x), ONE), add(x, TWO))
            else:
                index = 1
                x = div(sub(x, ONE), add(x, ONE))
        elif ix <= 0x401BFFFF:                      # |x| < 2.4375
            index = 2
            x = div(sub(x, 0x3FC00000), add(mul(x, 0x3FC00000), ONE))
        else:
            index = 3
            x = div(MINUS_ONE, x)
    z = mul(x, x)
    w = mul(z, z)
    t = ATAN_T
    even = mul(w, t[10])
    odd = mul(w, t[9])
    for n in (8, 6, 4, 2):
        even = mul(w, add(t[n], even))
        odd = mul(w, add(t[n - 1], odd))
    s1 = mul(z, add(t[0], even))
    s2 = odd
    if index < 0:
        return sub(x, mul(x, add(s1, s2)))
    z = sub(ATAN_HI[index], sub(sub(mul(x, add(s1, s2)), ATAN_LO[index]), x))
    return neg(z) if hx < 0 else z


def atan2f(y, x):
    """libm_atan2f 0x3a5a80 -> libm_ieee754_atan2f 0x3a7328 (f12 = y, f13 = x).

    x = 1.0 exactly goes straight to atanf(y).  y "zero" means its bits are <= 0x007fffff
    (zero or a denormal pattern): the answer is then y itself for x >= 0, +pi for x < 0 and
    y >= +0, -pi for both negative - WITHOUT the usual tiny addend.  x "zero" gives +/-pi/2.
    The quotient is |y / x| and the exponent difference decides the shortcuts."""
    hx, hy = s32(x), s32(y)
    ix, iy = x & FMAX, y & FMAX
    if (x & M32) == ONE:
        return atanf(y)
    quadrant = ((y >> 31) & 1) | ((x >> 30) & 2)
    if iy <= 0x007FFFFF:
        if quadrant == 2:
            return K_PI
        if quadrant == 3:
            return neg(K_PI)
        return y
    if ix <= 0x007FFFFF:
        return neg(K_PI_2) if hy < 0 else K_PI_2
    k = (iy - ix) >> 23
    if k > 60:
        z = K_PI_2
    elif hx < 0 and k < -60:
        z = ZERO
    else:
        z = atanf(fabs(div(y, x)))
    if quadrant == 0:
        return z
    if quadrant == 1:
        return neg(z)
    if quadrant == 2:
        return sub(K_PI, sub(z, K_PI_LO))
    return sub(sub(z, K_PI_LO), K_PI)


def floorf(x):
    """libm_floorf 0x3a57e8.  Works on the bits; the only FPU operation is the
    "huge + x > 0" test of the C source, which is true for every value that reaches it."""
    i0 = s32(x)
    ix = x & FMAX
    j0 = (ix >> 23) - 0x7F
    if j0 >= 23:
        return x & M32
    if j0 < 0:
        if lt(ZERO, add(x, K_HUGE)):
            if i0 >= 0:
                i0 = 0
            elif ix > 0x007FFFFF:
                i0 = MINUS_ONE
        return i0 & M32
    mask = 0x007FFFFF >> j0
    if i0 & mask == 0:
        return x & M32
    if lt(ZERO, add(x, K_HUGE)):
        if i0 < 0:
            i0 += 0x00800000 >> j0
        i0 &= ~mask
    return i0 & M32


def ceilf(x):
    """libm_ceilf 0x3a5710."""
    i0 = s32(x)
    ix = x & FMAX
    j0 = (ix >> 23) - 0x7F
    if j0 >= 23:
        return x & M32
    if j0 < 0:
        if lt(ZERO, add(x, K_HUGE)):
            if i0 < 0:
                i0 = SIGN
            elif ix > 0x007FFFFF:
                i0 = ONE
        return i0 & M32
    mask = 0x007FFFFF >> j0
    if i0 & mask == 0:
        return x & M32
    if lt(ZERO, add(x, K_HUGE)):
        if i0 > 0:
            i0 += 0x00800000 >> j0
        i0 &= ~mask
    return i0 & M32


def copysignf(x, y):
    """0x3aa920: magnitude of x, sign of y, on the bits."""
    return (x & FMAX) | (y & SIGN)


def scalbnf(x, n):
    """libm_scalbnf 0x3aa810 (f12 x, a0 n): x * 2**n by adding to the exponent field.
    A zero pattern (bits <= 0x007fffff) comes back unchanged; an exponent that would
    reach 256 gives copysign(1e30, x) * 1e30 (0x7fffffff with the sign of x on this FPU);
    one that would drop to 0 or below gives copysign(1e-30, x) * 1e-30 (a signed zero),
    or the overflow value when n > 50000."""
    hx = x & FMAX
    if hx <= 0x007FFFFF:
        return x & M32
    k = (hx >> 23) + s32(n)
    if k >= 0x100:
        return mul(copysignf(K_HUGE, x), K_HUGE)
    if k > 0:
        return (x & 0x807FFFFF) | (k << 23)
    if s32(n) > 50000:
        return mul(copysignf(K_HUGE, x), K_HUGE)
    return mul(copysignf(K_TINY, x), K_TINY)


def sqrtf(x):
    """0x3a84c0, the C library's square root (reached from powf(x, 0.5)); the engine's own
    code uses the sqrt.s instruction instead.  Integer arithmetic, one result bit per
    step, ROUNDED TO NEAREST - unlike sqrt.s, which truncates.  A zero pattern returns
    itself, a negative argument returns (x - x) / (x - x), which is 0x7fffffff here."""
    ix = s32(x)
    if (x & FMAX) <= 0x007FFFFF:
        return x & M32
    if ix < 0:
        zero = sub(x, x)
        return div(zero, zero)
    m = (ix >> 23) - 0x7F
    ix = (ix & 0x007FFFFF) | 0x00800000
    if m & 1:
        ix <<= 1
    m >>= 1
    ix <<= 1
    q = s = 0
    r = 0x01000000
    while r:
        t = s + r
        if t <= ix:
            s = t + r
            ix -= t
            q += r
        ix <<= 1
        r >>= 1
    if ix:
        q += q & 1
    return (0x3F000000 + (q >> 1) + (m << 23)) & M32


LIBM_IMMEDIATES = []            # (address of the lui, pattern, name): constants held in code


def _imm(address, text, name):
    LIBM_DECIMALS.append(text)
    LIBM_IMMEDIATES.append((address, const(text), name))
    return const(text)


POW_BP = [ONE, 0x3FC00000]                              # 0x5619c0: 1.0, 1.5
POW_DP_H = [ZERO] + _table('5.84960938e-01')            # 0x5619c8
POW_DP_L = [ZERO] + _table('1.56322085e-06')            # 0x5619d0
POW_OVERFLOW = _table('3.4028234664e+38')[0]            # 0x561a44: "huge * huge", folded by the compiler
LIBM_TABLES += [(0x5619C0, POW_BP, 'bp'), (0x5619C8, POW_DP_H, 'dp_h'), (0x5619D0, POW_DP_L, 'dp_l'),
                (0x561A44, [POW_OVERFLOW], 'huge*huge'), (0x5619B8, [ZERO, SIGN], 'fmodf Zero')]
_imm(0x3A7EB8, '1.0e30', 'huge')
_imm(0x3A7F38, '1.0e-30', 'tiny')
POW_THIRD = _imm(0x3A7B8C, '0.333333333333', '1/3')
POW_IVLN2 = _imm(0x3A7BA4, '1.4426950216e+00', 'ivln2')
POW_IVLN2_H = _imm(0x3A7BB4, '1.4426879883e+00', 'ivln2_h')
POW_IVLN2_L = _imm(0x3A7B98, '7.0526075433e-06', 'ivln2_l')
POW_L = [None,
         _imm(0x3A7D00, '6.0000002384e-01', 'L1'), _imm(0x3A7CF0, '4.2857143283e-01', 'L2'),
         _imm(0x3A7CE0, '3.3333334327e-01', 'L3'), _imm(0x3A7CD4, '2.7272811532e-01', 'L4'),
         _imm(0x3A7CC8, '2.3066075146e-01', 'L5'), _imm(0x3A7CBC, '2.0697501302e-01', 'L6')]
POW_P = [None,
         _imm(0x3A7FEC, '1.6666667163e-01', 'P1'), _imm(0x3A8028, '-2.7777778450e-03', 'P2'),
         _imm(0x3A8034, '6.6137559770e-05', 'P3'), _imm(0x3A8018, '-1.6533901999e-06', 'P4'),
         _imm(0x3A8008, '4.1381369442e-08', 'P5')]
POW_CP = _imm(0x3A7DCC, '9.6179670095e-01', 'cp')
POW_CP_H = _imm(0x3A7DB4, '9.6179199219e-01', 'cp_h')
POW_CP_L = _imm(0x3A7DC0, '4.7017383622e-06', 'cp_l')
POW_LG2 = _imm(0x3A7FDC, '6.9314718246e-01', 'lg2')
POW_LG2_H = _imm(0x3A7FD0, '6.93145752e-01', 'lg2_h')
POW_LG2_L = _imm(0x3A7FF8, '1.42860654e-06', 'lg2_l')
POW_OVT = _imm(0x3A7ED8, '4.2995665694e-08', 'ovt')
HEAD = 0xFFFFF000               # "the high part": clear the low 12 bits of a pattern


def powf(x, y):
    """libm_powf 0x3a5ac8 -> libm_ieee754_powf 0x3a7930 (f12 x, f13 y): fdlibm's e_powf.c as
    the console compiler built it - no NaN or infinity cases, no denormal scaling, the
    FPU's truncating arithmetic throughout.

    Shortcuts taken on the bit patterns, in this order: y "zero" (bits <= 0x007fffff)
    gives 1; y = +/-1 gives x or 1/x; y = 2 gives x*x; y = 0.5 with x >= +0 gives the C
    library sqrtf(x); x "zero" or |x| = 1 gives |x| or 1/|x| with the sign rule below; a
    negative x with a non-integer y gives (x - x) / (x - x), which is 0x7fffffff here.
    Otherwise 2**(y * log2|x|) from the usual split into high and low parts, negated when
    x < 0 and y is an odd integer.  An exactly representable case need not be exact:
    powf(10, 2) takes the x*x shortcut, powf(10, 3) does not."""
    hx, hy = s32(x), s32(y)
    ix, iy = x & FMAX, y & FMAX
    if iy <= 0x007FFFFF:
        return ONE
    # is y an integer?  0 no, 1 odd, 2 even - only looked at for negative x
    yisint = 0
    if hx < 0:
        if iy > 0x4B7FFFFF:
            yisint = 2
        elif iy > 0x3F7FFFFF:
            shift = 0x96 - (iy >> 23)
            j = iy >> shift
            if (j << shift) == iy:
                yisint = 2 - (j & 1)
    if iy == ONE:
        return (x & M32) if hy >= 0 else div(ONE, x)
    if (y & M32) == TWO:
        return mul(x, x)
    if (y & M32) == HALF and hx >= 0:
        return sqrtf(x)
    ax = fabs(x)
    if ix <= 0x007FFFFF or ix == ONE:
        z = ax
        if hy < 0:
            z = div(ONE, z)
        if hx < 0:
            if ix == ONE and yisint == 0:
                zero = sub(z, z)
                z = div(zero, zero)
            elif yisint == 1:
                z = neg(z)
        return z
    negative = (x >> 31) & 1
    if negative and yisint == 0:
        zero = sub(x, x)
        return div(zero, zero)

    if iy > 0x4D000000:                             # |y| > 2**27
        if ix <= 0x3F7FFFF7:
            return POW_OVERFLOW if hy < 0 else ZERO
        if ix > 0x3F800007:
            return POW_OVERFLOW if hy > 0 else ZERO
        t = sub(x, ONE)                             # x is within 8 units of 1.0
        w = mul(mul(t, t), sub(HALF, mul(t, sub(POW_THIRD, mul(t, QUARTER)))))
        u = mul(t, POW_IVLN2_H)
        v = sub(mul(t, POW_IVLN2_L), mul(w, POW_IVLN2))
        t1 = add(u, v) & HEAD
        t2 = sub(v, sub(t1, u))
    else:
        j = ix & 0x007FFFFF
        n = (ix >> 23) - 0x7F
        ix = j | 0x3F800000
        if j <= 0x1CC471:
            k = 0
        elif j <= 0x5DB3D6:
            k = 1
        else:
            k = 0
            n += 1
            ix -= 0x00800000
        ax = ix
        u = sub(ax, POW_BP[k])
        v = div(ONE, add(ax, POW_BP[k]))
        s = mul(u, v)
        s_h = s & HEAD
        t_h = (((ix >> 1) | 0x20000000) + (k << 21) + 0x00040000) & M32
        t_l = sub(ax, sub(t_h, POW_BP[k]))
        s_l = mul(v, sub(sub(u, mul(s_h, t_h)), mul(s_h, t_l)))
        s2 = mul(s, s)
        r = mul(s2, POW_L[6])
        for index in (5, 4, 3, 2, 1):
            r = add(r, POW_L[index])
            if index > 1:
                r = mul(s2, r)
        r = mul(mul(s2, s2), r)
        r = add(r, mul(s_l, add(s_h, s)))
        s2 = mul(s_h, s_h)
        t_h = add(add(s2, THREE), r) & HEAD
        t_l = sub(r, sub(sub(t_h, THREE), s2))
        u = mul(s_h, t_h)
        v = add(mul(s_l, t_h), mul(t_l, s))
        p_h = add(u, v) & HEAD
        p_l = sub(v, sub(p_h, u))
        z_h = mul(p_h, POW_CP_H)
        z_l = add(add(mul(p_h, POW_CP_L), mul(p_l, POW_CP)), POW_DP_L[k])
        t = from_int(n)
        t1 = add(add(add(z_h, z_l), POW_DP_H[k]), t) & HEAD
        t2 = sub(z_l, sub(sub(sub(t1, t), POW_DP_H[k]), z_h))

    sign = MINUS_ONE if negative and yisint == 1 else ONE
    y1 = y & HEAD
    p_l = add(mul(sub(y, y1), t1), mul(y, t2))
    p_h = mul(y1, t1)
    z = add(p_l, p_h)
    j = s32(z)
    i = z & FMAX
    if j > 0:
        if i > 0x43010000 or (i == 0x43010000 and lt(sub(z, p_h), add(p_l, POW_OVT))):
            return mul(mul(sign, K_HUGE), K_HUGE)
    else:
        if i > 0x42FC0000 or (i == 0x42FC0000 and le(p_l, sub(z, p_h))):
            return mul(mul(sign, K_TINY), K_TINY)
    n = 0
    bits = z
    if i > 0x3F000000:                              # |z| > 0.5: take the integer part out
        n = (j + (0x00800000 >> ((i >> 23) - 0x7E))) & M32
        k = ((n >> 23) & 0xFF) - 0x7F
        t = n & ~(0x007FFFFF >> k) & M32
        n = ((n & 0x007FFFFF) | 0x00800000) >> (23 - k)
        if j < 0:
            n = -n
        p_h = sub(p_h, t)
        bits = add(p_l, p_h)
    t = bits & HEAD
    u = mul(t, POW_LG2_H)
    v = add(mul(sub(p_l, sub(t, p_h)), POW_LG2), mul(t, POW_LG2_L))
    z = add(u, v)
    w = sub(v, sub(z, u))
    t = mul(z, z)
    poly = mul(t, POW_P[5])
    for index in (4, 3, 2, 1):
        poly = mul(t, add(poly, POW_P[index]))
    t1 = sub(z, poly)
    r = sub(div(mul(z, t1), sub(t1, TWO)), add(w, mul(z, w)))
    z = sub(ONE, sub(r, z))
    j = s32(z + (n << 23))
    if (j >> 23) <= 0:
        z = scalbnf(z, n)
    else:
        z = j & M32
    return mul(sign, z)


def fmodf(x, y):
    """libm_fmodf 0x3a5ab0 -> libm_ieee754_fmodf 0x3a7760 (f12 x, f13 y): the remainder
    with the sign of x, by shift and subtract on the significands - exact, no FPU
    operation involved except for a "zero" divisor (bits <= 0x007fffff), which returns
    (x * y) / (x * y): 0x7fffffff on this FPU."""
    hx, hy = x & M32, y & FMAX
    sign = hx & SIGN
    hx ^= sign
    if hy <= 0x007FFFFF:
        product = mul(x, y)
        return div(product, product)
    if hx < hy:
        return x & M32
    if hx == hy:
        return sign
    ix = (hx >> 23) - 127
    iy = (hy >> 23) - 127
    hx = 0x00800000 | (hx & 0x007FFFFF)
    hy = 0x00800000 | (hy & 0x007FFFFF)
    for _ in range(ix - iy):
        hz = hx - hy
        if hz < 0:
            hx = hx + hx
        elif hz == 0:
            return sign
        else:
            hx = hz + hz
    hz = hx - hy
    if hz >= 0:
        hx = hz
    if hx == 0:
        return sign
    while hx < 0x00800000:
        hx <<= 1
        iy -= 1
    if iy >= -126:
        return ((hx - 0x00800000) | ((iy + 127) << 23) | sign) & M32
    return ((hx >> (-126 - iy)) | sign) & M32


# ---------------------------------------------------------------------------------------
# 8b. Double precision, which this console does in software
# ---------------------------------------------------------------------------------------
# The EE has no double-precision FPU; every `double` operation of the game is a call into
# the compiler's support library (GCC fp-bit.c, 0x3ae688-0x3afc80).  Game code reaches it
# all the time: any float multiplied by an unsuffixed literal such as 1.5 is converted to
# double, multiplied and converted back.  This build of the library is NOT IEEE 754
# either:
#   * results are TRUNCATED toward zero, never rounded (the rounding step is compiled out);
#   * there are no denormals: an exponent field of 0 is zero, a result below the normal
#     range is zero;
#   * infinities and NaNs do exist in double, but the float side has neither: a float
#     with exponent field 255 converts to an ordinary double (2**128 and up), and a double
#     that is too large, infinite or NaN converts to the float pattern 0x7f800000.
# A double is an int holding the 64-bit pattern.

D_SIGN = 1 << 63
D_NAN = 0x7FF8000000000000      # what an invalid operation returns
_D_SNAN, _D_QNAN, _D_ZERO, _D_NUMBER, _D_INF = range(5)
_D_ONE = 1 << 60                # the leading 1 of an unpacked significand (8 guard bits below 52)


def d64(value):
    """Pattern of a Python float (IEEE; for test input)."""
    return struct.unpack('<Q', struct.pack('<d', value))[0]


def to_double(bits):
    return struct.unpack('<d', struct.pack('<Q', bits & M64))[0]


def dconst(text):
    """Pattern the game's compiler produced for a double literal: the decimal value
    truncated to 53 bits (0.9 is 0x3feccccccccccccc, not ...cd)."""
    q = Fraction(text)
    sign = D_SIGN if q < 0 else 0
    q = abs(q)
    if q == 0:
        return sign
    e2 = q.numerator.bit_length() - q.denominator.bit_length() - 53
    while q >= Fraction(2) ** (e2 + 53):
        e2 += 1
    while q < Fraction(2) ** (e2 + 52):
        e2 -= 1
    mant = int(q / Fraction(2) ** e2)
    return sign | ((e2 + 1075) << 52) | (mant & 0xFFFFFFFFFFFFF)


def _d_unpack(bits):
    """unpack_d 0x3af0f0 -> (class, sign, exponent, significand)."""
    bits &= M64
    sign = bits >> 63
    exp = (bits >> 52) & 0x7FF
    frac = bits & 0xFFFFFFFFFFFFF
    if exp == 0:
        return _D_ZERO, sign, 0, 0
    if exp == 0x7FF:
        if frac == 0:
            return _D_INF, sign, 1023, _D_ONE
        return (_D_QNAN if frac & (1 << 51) else _D_SNAN), sign, 1023, frac
    return _D_NUMBER, sign, exp - 1023, (frac << 8) | _D_ONE


def _d_pack(cls, sign, exp, frac):
    """pack_d 0x3af018: no rounding - the eight guard bits are shifted out."""
    if cls < _D_ZERO:
        field, frac = 0x7FF, frac | (1 << 51)
    elif cls == _D_INF:
        field, frac = 0x7FF, 0
    elif cls == _D_ZERO or frac == 0 or exp < -1022:
        field, frac = 0, 0
    elif exp >= 1024:
        field, frac = 0x7FF, 0
    else:
        field, frac = exp + 1023, frac >> 8
    return ((sign & 1) << 63) | (field << 52) | (frac & 0xFFFFFFFFFFFFF)


def _d_add_parts(a, b):
    """_fpadd_parts 0x3af1b0 on two unpacked values."""
    (ca, sa, ea, fa), (cb, sb, eb, fb) = a, b
    if ca < _D_ZERO:
        return a
    if cb < _D_ZERO:
        return b
    if ca == _D_INF:
        if cb == _D_INF and sa != sb:
            return _D_SNAN, 0, 0, 0                 # the library's NaN: packs to D_NAN
        return a
    if cb == _D_INF:
        return b
    if cb == _D_ZERO:
        if ca == _D_ZERO:
            return ca, sa & sb, ea, fa
        return a
    if ca == _D_ZERO:
        return b
    gap = ea - eb
    if abs(gap) < 64:
        # the smaller operand is shifted down one bit at a time; a 1 that falls off the
        # end sticks in the lowest bit
        for _ in range(abs(gap)):
            if gap > 0:
                fb = (fb >> 1) | (fb & 1)
            else:
                fa = (fa >> 1) | (fa & 1)
        exp = max(ea, eb)
    elif gap > 0:
        fb, exp = 0, ea                             # 64 or more apart: dropped altogether
    else:
        fa, exp = 0, eb
    if sa != sb:
        frac = fb - fa if sa else fa - fb
        sign = 0
        if frac < 0:
            sign, frac = 1, -frac
        while 0 < frac < _D_ONE:
            frac <<= 1
            exp -= 1
    else:
        sign, frac = sa, fa + fb
    if frac >= _D_ONE << 1:
        frac = (frac >> 1) | (frac & 1)
        exp += 1
    return _D_NUMBER, sign, exp, frac


def dadd(a, b):
    """0x3af410: a + b.  The exact sum truncated toward zero - except that an operand 2**64
    times smaller than the other is ignored even when subtracting it should have taken
    the last bit down.  x - x is +0; (-0) + (-0) is -0."""
    return _d_pack(*_d_add_parts(_d_unpack(a), _d_unpack(b)))


def dsub(a, b):
    """0x3af468: a - b, as dadd with the sign of b flipped after unpacking."""
    cb, sb, eb, fb = _d_unpack(b)
    return _d_pack(*_d_add_parts(_d_unpack(a), (cb, sb ^ 1, eb, fb)))


def dmul(a, b):
    """0x3af4d0: a * b, the exact product truncated toward zero."""
    ca, sa, ea, fa = _d_unpack(a)
    cb, sb, eb, fb = _d_unpack(b)
    sign = sa ^ sb
    if ca < _D_ZERO:
        return _d_pack(ca, sign, ea, fa)
    if cb < _D_ZERO:
        return _d_pack(cb, sign, eb, fb)
    if ca == _D_INF:
        return D_NAN if cb == _D_ZERO else _d_pack(ca, sign, ea, fa)
    if cb == _D_INF:
        return D_NAN if ca == _D_ZERO else _d_pack(cb, sign, eb, fb)
    if ca == _D_ZERO or cb == _D_ZERO:
        return sign << 63
    product = fa * fb                               # 121 or 122 bits
    exp = ea + eb
    frac = product >> 60
    if frac >= _D_ONE << 1:
        frac >>= 1
        exp += 1
    return _d_pack(_D_NUMBER, sign, exp, frac)


def ddiv(a, b):
    """0x3af758: a / b, the exact quotient truncated toward zero.  x / 0 is an infinity,
    0 / 0 and inf / inf are D_NAN, x / inf is a signed zero."""
    ca, sa, ea, fa = _d_unpack(a)
    cb, sb, eb, fb = _d_unpack(b)
    if ca < _D_ZERO:
        return _d_pack(ca, sa, ea, fa)
    if cb < _D_ZERO:
        return _d_pack(cb, sb, eb, fb)
    sign = sa ^ sb
    if ca in (_D_INF, _D_ZERO):
        return D_NAN if ca == cb else _d_pack(ca, sign, ea, fa)
    if cb == _D_INF:
        return sign << 63
    if cb == _D_ZERO:
        return _d_pack(_D_INF, sign, 0, 0)
    exp = ea - eb
    if fa < fb:
        fa <<= 1
        exp -= 1
    return _d_pack(_D_NUMBER, sign, exp, (fa << 60) // fb)


def dcmp(a, b):
    """0x3af9b8, the one comparison routine all 110 call sites use: -1, 0 or +1 for a < b,
    a == b, a > b; +1 when either is a NaN.  +0 equals -0 and every denormal pattern."""
    ca, sa, ea, fa = _d_unpack(a)
    cb, sb, eb, fb = _d_unpack(b)
    if ca < _D_ZERO or cb < _D_ZERO:
        return 1
    if ca == _D_INF and cb == _D_INF:
        return sb - sa
    if ca == _D_INF:
        return -1 if sa else 1
    if cb == _D_INF:
        return 1 if sb else -1
    if ca == _D_ZERO and cb == _D_ZERO:
        return 0
    if ca == _D_ZERO:
        return 1 if sb else -1
    if cb == _D_ZERO:
        return -1 if sa else 1
    if sa != sb:
        return -1 if sa else 1
    if (ea, fa) == (eb, fb):
        return 0
    return (1 if (ea, fa) > (eb, fb) else -1) * (-1 if sa else 1)


def i2d(value):
    """0x3afa08: signed 32-bit integer to double (always exact)."""
    value = s32(value)
    if value == 0:
        return 0
    frac, exp = abs(value), 60
    while frac < _D_ONE:
        frac <<= 1
        exp -= 1
    return _d_pack(_D_NUMBER, 1 if value < 0 else 0, exp, frac)


def d2i(bits):
    """0x3afac0: double to signed 32-bit integer, toward zero; saturates at 0x7fffffff /
    -0x80000000 (an infinity too); a NaN gives 0."""
    cls, sign, exp, frac = _d_unpack(bits)
    if cls == _D_ZERO or cls < _D_ZERO:
        return 0
    if cls == _D_INF or exp >= 31:
        return -0x80000000 if sign else 0x7FFFFFFF
    if exp < 0:
        return 0
    value = frac >> (60 - exp)
    return -value if sign else value


def f2d(raw):
    """0x3aef58: float to double, exact.  Exponent field 0 is zero (sign kept); exponent
    field 255 is an ordinary number, so 0x7f800000 becomes 2**128, not infinity."""
    raw &= M32
    field = (raw >> 23) & 0xFF
    if field == 0:
        return (raw >> 31) << 63
    frac = ((raw & 0x007FFFFF) << 7) | 0x40000000
    return _d_pack(_D_NUMBER, raw >> 31, field - 127, frac << 30)


def d2f(bits):
    """0x3afb90: double to float, TRUNCATED toward zero.  Below 2**-126 the result is a
    signed zero; from 2**129 up, and for an infinity or a NaN, it is 0x7f800000 with the
    sign; in between 2**128 and 2**129 it is a float with exponent field 255."""
    cls, sign, exp, frac = _d_unpack(bits)
    if cls == _D_ZERO or exp < -126:
        return sign << 31
    if exp >= 129:                                  # an infinity or a NaN arrives with 1023
        return (sign << 31) | 0x7F800000
    return (sign << 31) | ((exp + 127) << 23) | ((frac >> 37) & 0x007FFFFF)


def fmod(x, y):
    """libm_fmod 0x3a5a38 -> libm_ieee754_fmod 0x3a6208 (two doubles): fdlibm's e_fmod.c
    on the two 32-bit halves of each operand - exact, sign of x, and the one routine here
    that still honours denormals.  y = 0, x infinite or NaN, or y NaN returns
    (x * y) / (x * y) through dmul and ddiv."""
    hx, lx = (x >> 32) & M32, x & M32
    hy, ly = (y >> 32) & 0x7FFFFFFF, y & M32
    sx = hx & SIGN
    hx ^= sx
    if (hy | ly) == 0 or hx >= 0x7FF00000 or (hy | ((ly | (-ly & M32)) >> 31)) > 0x7FF00000:
        product = dmul(x, y)
        return ddiv(product, product)
    if hx <= hy:
        if hx < hy or lx < ly:
            return x & M64
        if lx == ly:
            return sx << 32
    if hx < 0x00100000:                             # ilogb of a denormal x
        if hx == 0:
            ix, i = -1043, s32(lx)
        else:
            ix, i = -1022, s32(hx << 11)
        while i > 0:
            i = s32(i << 1)
            ix -= 1
    else:
        ix = (hx >> 20) - 1023
    if hy < 0x00100000:
        if hy == 0:
            iy, i = -1043, s32(ly)
        else:
            iy, i = -1022, s32(hy << 11)
        while i > 0:
            i = s32(i << 1)
            iy -= 1
    else:
        iy = (hy >> 20) - 1023

    def align(high, low, exponent):
        if exponent >= -1022:
            return 0x00100000 | (high & 0x000FFFFF), low
        n = -1022 - exponent
        if n <= 31:
            return ((high << n) | (low >> (32 - n))) & M32, (low << n) & M32
        return (low << (n - 32)) & M32, 0

    hx, lx = align(hx, lx, ix)
    hy, ly = align(hy, ly, iy)
    wide_x, wide_y = (hx << 32) | lx, (hy << 32) | ly      # the 64-bit fixed-point values
    for _ in range(ix - iy):
        rest = wide_x - wide_y
        if rest < 0:
            wide_x <<= 1
        elif rest == 0:
            return sx << 32
        else:
            wide_x = rest << 1
    rest = wide_x - wide_y
    if rest >= 0:
        wide_x = rest
    if wide_x == 0:
        return sx << 32
    while wide_x < 1 << 52:
        wide_x <<= 1
        iy -= 1
    if iy >= -1022:
        return ((sx << 32) | (wide_x - (1 << 52)) | ((iy + 1023) << 52)) & M64
    return (sx << 32) | (wide_x >> (-1022 - iy))


# Constants of the engine's own code, with the address of the instruction pair (lui, ori)
# that loads each: difftest_core.py reads them back from the executable (property
# "code.constants"), which checks the ones too small to show in any result.
CODE_CONSTANTS = [
    (0x166668, K_PI_65536, 'cos16 pi/65536'), (0x166674, K_SIN3, 'cos16 s3'),
    (0x166680, K_SIN5, 'cos16 s5'), (0x16668C, K_SIN7, 'cos16 s7'),
    (0x16671C, K_PI_65536, 'sin16 pi/65536'), (0x166728, K_SIN3, 'sin16 s3'),
    (0x166734, K_SIN5, 'sin16 s5'), (0x166740, K_SIN7, 'sin16 s7'),
    (0x1667A8, K_RAD_TO_ANGLE, 'atan2_16 scale'), (0x161618, K_DEG_TO_ANGLE, 'degrees to angle'),
    (0x164038, K_SINGULAR, 'mat4_invert limit'), (0x164764, K_40000, 'noise table scale'),
    (0x166B5C, K_1_16, 'noise 1/16'), (0x166BA8, K_1_32768, 'noise 1/32768'),
    (0x1636F0, K_0_001, 'ray/plane limit'), (0x163770, K_1000, 'ray/plane 1000.00006'),
    (0x163858, K_0_01, 'segment divisor limit'), (0x166EC0, K_BIG, 'empty box'),
    (0x164F70, K_255, 'colour 255'), (0x3A738C, K_PI, 'atan2f pi'), (0x3A73F4, K_PI_2, 'atan2f pi/2'),
    (0x3A74B0, K_PI_LO, 'atan2f pi_lo'), (0x3AA5E4, K_HUGE, 'atanf huge'),
]


# =======================================================================================
# 9. Random generators
# =======================================================================================

class Lcg:
    """The engine's one generator, used with several seeds:

        state = state * 0x0019660D + 0x3C6EF35F   (mod 2**32)
        draw  = state >> 16                        (the upper 16 bits of the NEW state)

    GameObject_rand 0x1509d0 (state at object +0x44) and Spell_rand 0x16a964 (spell +0x10)
    are this function; the shared seed 0x404464, the cosmetic seed 0x404460 and the third
    seed 0x404468 are updated by the same three instructions inlined at every use (the
    script built-in getRand 0x146570 is the shared one as a function)."""
    MULTIPLIER = 0x0019660D
    INCREMENT = 0x3C6EF35F

    def __init__(self, state=0):
        self.state = state & M32

    def draw(self):
        self.state = (self.state * self.MULTIPLIER + self.INCREMENT) & M32
        return self.state >> 16

    def unit(self):
        """float(draw) * 2**-16: the usual [0, 1) value (685 inline sites; 0x3c7f30)."""
        return mul(from_int(self.draw()), TWO_M16)

    def signed_unit(self):
        """(u + u) - 1.0 with u = unit(): the usual [-1, 1) value."""
        u = self.unit()
        return sub(add(u, u), ONE)

    def in_unit_sphere(self):
        """0x3c7f60 / 0x3c8030: three signed_unit() draws, repeated while
        1.0 < (x*x + y*y) + z*z."""
        while True:
            x = self.signed_unit()
            y = self.signed_unit()
            z = self.signed_unit()
            if not lt(ONE, add(add(mul(x, x), mul(y, y)), mul(z, z))):
                return [x, y, z]


class SharedRandom(Lcg):
    """g_randSeed 0x404464: part of the sync hash; 0 in the executable and set to 0 again
    by net_startSync 0x13dce0.  Must be drawn identically on every machine."""


class CosmeticRandom(Lcg):
    """g_cosmeticSeed 0x404460: seeded from the CPU cycle counter at boot (0x19d1e0),
    overwritten with g_randSeed during game_loadLevel.  Per machine."""


class EffectRandom(Lcg):
    """The third seed 0x404468 (effects and decals).  Per machine."""


class ObjectRandom(Lcg):
    """The per-object generator.  GameObject_ctor (0x14cd50-0x14cd80) advances the shared
    seed once and stores the DRAW, a 16-bit number, as the object's state at +0x44."""

    def __init__(self, shared):
        Lcg.__init__(self, shared.draw())


class SpellRandom(Lcg):
    """The per-spell generator at spell +0x10, seeded exactly like ObjectRandom by every
    Spell constructor (out-of-line copy 0x3d0bc4)."""

    def __init__(self, shared):
        Lcg.__init__(self, shared.draw())


class LibcRand:
    """libc_rand 0x3b70f0 / libc_srand 0x3b70d8 (newlib): a 64-bit state at the C library's
    re-entrancy structure +0xa8, 1 in the executable.

        state = state * 6364136223846793005 + 1   (mod 2**64)
        rand  = (state >> 32) & 0x7fffffff

    Per machine: its only seeding is the lobby clock value."""
    MULTIPLIER = 6364136223846793005

    def __init__(self, state=1):
        self.state = state & M64

    def seed(self, value):
        self.state = value & M32

    def rand(self):
        self.state = (self.state * self.MULTIPLIER + 1) & M64
        return (self.state >> 32) & 0x7FFFFFFF


# =======================================================================================
# 10. Object pool
# =======================================================================================

class PoolError(Exception):
    """The original has no defined behaviour here (it would read or write stray memory)."""


class Pool:
    """pool_init 0x14fcd8, pool_new 0x14fdb8, pool_free 0x150470, pool_countFree 0x150410.

    Three size classes laid out back to back from 0x5f88c0; each has a singly linked free
    list whose link is the first word of the free block.  self.head[c] is the list head of
    class c, self.link[address] the link word of a block that is on a list."""
    BASE = 0x5F88C0
    CLASSES = ((0x180, 512), (0x500, 512), (3000, 32))      # g_poolClasses 0x403a10

    def __init__(self):
        self.init()

    def init(self):
        """pool_init: every list holds its blocks in ascending address order."""
        self.base = []
        self.head = []
        self.link = {}
        self.last = 0                   # 0x4d8a24: the block handed out last
        address = self.BASE
        for size, count in self.CLASSES:
            self.base.append(address)
            self.head.append(address)
            for n in range(count):
                self.link[address + n * size] = address + (n + 1) * size if n + 1 < count else 0
            address += size * count
        self.end = address              # 0x6dffc0

    def new(self, size):
        """pool_new(size) -> address, or 0 when no class that is big enough has a free block
        (the original then prints the heap).  The first class whose block size is >= size
        AND whose list is not empty serves the request: a full class spills into the next
        larger one.  The block comes off the head of the list and is zero-filled over the
        whole block size of its class.  size is compared as a signed number, so 0 and
        negative sizes are served from class 0."""
        size = s32(size)
        for index, (block, _count) in enumerate(self.CLASSES):
            if block >= size and self.head[index]:
                address = self.head[index]
                if address not in self.link:
                    raise PoolError('free list of class %d is corrupt at 0x%x' % (index, address))
                self.head[index] = self.link.pop(address)
                self.last = address
                return address
        return 0

    def class_of(self, address):
        """The class pool_free files an address under: the first class whose successor
        starts above it.  There is no lower bound, so anything below the pool lands in
        class 0; at or above the end of the pool the original walks off its table."""
        if address >= self.end:
            raise PoolError('0x%x is past the pool: pool_free would read beyond its table' % address)
        for index in (0, 1):
            if address < self.base[index + 1]:
                return index
        return 2

    def free(self, address):
        """pool_free(address): push on the head of its class's list.  No check of any kind:
        the class is that of the ADDRESS (a spilled block goes back where it came from),
        and freeing a block twice makes the list loop."""
        index = self.class_of(address)
        self.link[address] = self.head[index]
        self.head[index] = address

    def free_list(self, index):
        """Addresses on the free list of one class, head first."""
        out, address = [], self.head[index]
        while address:
            if len(out) > 4096:
                raise PoolError('free list of class %d loops' % index)
            out.append(address)
            address = self.link[address]
        return out

    def count_free(self):
        """pool_countFree: the lengths of the three lists added up."""
        return sum(len(self.free_list(index)) for index in range(3))


# =======================================================================================
# 11. Handle lists
# =======================================================================================

class HandleError(Exception):
    """The original has no defined behaviour here (it would write through a null or stale
    pointer)."""


class Cell:
    """A list head: one pointer.  A global list, a grid cell, a single object reference (a
    "handle"), or one of the three heads at the start of every object."""
    __slots__ = ('next', 'name')

    def __init__(self, name=None):
        self.next = None
        self.name = name


class Node:
    """One 20-byte node of the pool at 0x847268: +0 next, +4 prev, +8 partner, +0xc object,
    +0x10 a 16-bit field that is cleared whenever the node is taken from the free list.
    prev refers to the previous node OR to the Cell that heads the list: both start with
    the 'next' pointer, which is all the code touches through prev."""
    __slots__ = ('index', 'next', 'prev', 'partner', 'obj', 'tag')

    def __init__(self, index):
        self.index = index
        self.next = self.prev = self.partner = self.obj = None
        self.tag = 0


class HandlePool:
    """handle_initPool 0x1a17d0, handle_link 0x1a1738, handle_linkBoth 0x1a18f0,
    handle_addNode 0x1a1980, handle_insertNode 0x1a19d0, handle_removeNode 0x1a1868,
    handle_clear 0x1a1698.  6,096 nodes; the free list (head 0x864ea8) is last in, first
    out.  Fields of a freed node other than 'next' keep their old values, as in the
    original."""
    NODE_COUNT = 6096
    NODE_BASE = 0x847268
    NODE_SIZE = 20

    def __init__(self, count=NODE_COUNT):
        self.nodes = [Node(index) for index in range(count)]
        self.init()

    def init(self):
        """handle_initPool: node i links to node i + 1; node 0 is handed out first."""
        for index, node in enumerate(self.nodes):
            node.next = self.nodes[index + 1] if index + 1 < len(self.nodes) else None
        self.free = self.nodes[0] if self.nodes else None

    # -- the three primitive steps every function is made of
    def _take(self):
        node = self.free
        if node is None:
            raise HandleError('node pool exhausted: the original would store through a null node')
        self.free = node.next
        node.tag = 0
        return node

    def _release(self, node):
        node.next = self.free
        self.free = node

    @staticmethod
    def _push(head, node):
        """Insert node directly after head (a Cell or a Node)."""
        node.next = head.next
        if head.next is not None:
            head.next.prev = node
        node.prev = head
        head.next = node

    @staticmethod
    def _unlink(node):
        if node.prev is not None:
            node.prev.next = node.next
        if node.next is not None:
            node.next.prev = node.prev

    # -- the functions
    def link(self, head, back, obj):
        """handle_link(head, back, obj) -> the list node.  Two nodes: A at the front of the
        list `head` carrying obj, B at the front of `back` (one of the object's own three
        heads) carrying nothing; each is the other's partner.  A is taken first."""
        a = self._take()
        b = self._take()
        self._push(head, a)
        self._push(back, b)
        a.obj, a.partner = obj, b
        b.obj, b.partner = None, a
        return a

    def link_both(self, head_a, obj_b, head_b, obj_a):
        """handle_linkBoth 0x1a18f0 (a0 head_a, a1 obj_b, a2 head_b, a3 obj_a): as link, but
        the second node carries an object too, so each list refers to the other side.  The
        original returns nothing.  The two heads must be different lists (see clear)."""
        a = self._take()
        b = self._take()
        self._push(head_a, a)
        self._push(head_b, b)
        a.obj, b.obj = obj_a, obj_b
        a.partner, b.partner = b, a

    def add(self, head, obj):
        """handle_addNode(head, obj) -> node: one node without a partner at the front."""
        node = self._take()
        self._push(head, node)
        node.obj, node.partner = obj, None
        return node

    def insert(self, head, after, obj):
        """handle_insertNode(head, after, obj) -> node: behind `after` when it is given, at
        the front of head otherwise."""
        node = self._take()
        node.obj, node.partner = obj, None
        self._push(after if after is not None else head, node)
        return node

    def remove(self, node):
        """handle_removeNode(node) -> its object.  Unlinks the node and its partner; the
        partner returns to the free list first, so the node itself is reused first."""
        obj = node.obj
        self._unlink(node)
        partner = node.partner
        if partner is not None:
            self._unlink(partner)
            self._release(partner)
        self._release(node)
        return obj

    def clear(self, head):
        """handle_clear(head): remove every node of the list, front to back, each with its
        partner.  This is what an object's destructor does to its three heads, and why
        every list that referred to the object forgets it at that moment.

        The successor is read before the node's partner is released, so a list must not
        hold both nodes of one link: the walk would continue through a freed node into
        the free list."""
        node = head.next
        while node is not None:
            if isinstance(node, Iterator):
                raise HandleError('list cleared while an iterator stands in it: the original '
                                  'would treat the iterator as a node and free stack memory')
            following = node.next
            if following is not None and following is node.partner:
                raise HandleError('both nodes of a link are in the list being cleared')
            self._unlink(node)
            partner = node.partner
            if partner is not None:
                self._unlink(partner)
                self._release(partner)
            self._release(node)
            node = following

    def count_free(self):
        count, node = 0, self.free
        while node is not None:
            count += 1
            node = node.next
        return count

    @staticmethod
    def items(head):
        """The objects a plain walk of the list sees (partner-side nodes and iterators
        carry none and are left out)."""
        out, node = [], head.next
        while node is not None:
            if node.obj is not None:
                out.append(node.obj)
            node = node.next
        return out


class Iterator:
    """iter_begin 0x1a1a48, iter_next 0x1a1b38, iter_end 0x1a1ae8.

    The iterator is a 24-byte record laid out like a node (+0 next, +4 prev, +0xc object =
    0, +0x14 the skip mask) and it is spliced INTO the list, directly behind the node it is
    on.  The current object is  prev.obj;  the walk is over when prev is null.  A node is
    skipped when it carries no object or when  object.flags & mask  is not zero (flags is
    the word at object +0xc).

    Because the iterator is a member of the list, the list may change during the walk:
      * removing the current node, or any other, keeps the walk correct: iter_next looks
        from its own 'next', which unlinking maintains;
      * a node added at the front of the list is behind the iterator and is not visited;
      * a node inserted directly after the current one lands BEFORE the iterator and is
        not visited either;
      * other iterators in the same list are skipped like partner nodes;
      * after the current node is removed, prev refers to the node before it (or to the
        list head, which is not a node): `current` is only meaningful until then."""
    __slots__ = ('next', 'prev', 'partner', 'obj', 'mask')

    def __init__(self, head, mask=0):
        self.partner = None
        self.mask = mask & M32
        node = self._find(head.next)
        self._stand_behind(node)
        self.obj = None

    def _find(self, node):
        while node is not None:
            if node.obj is not None and not (node.obj.flags & self.mask):
                return node
            node = node.next
        return None

    def _stand_behind(self, node):
        if node is None:
            self.next = self.prev = None
            return
        self.prev = node
        self.next = node.next
        if node.next is not None:
            node.next.prev = self
        node.next = self

    @property
    def done(self):
        return self.prev is None

    @property
    def current(self):
        """The object the caller reads right after iter_begin / iter_next: prev.obj.  When a
        second iterator has since come to stand behind the same node, prev is that
        iterator and this reads its empty object field: None."""
        if self.prev is None:
            return None
        if isinstance(self.prev, Cell):
            raise HandleError('prev is the list head: the original would read stray memory')
        return self.prev.obj

    def advance(self):
        """iter_next: find the next wanted node from 'next', leave the list, stand behind
        the found node (or end with prev = next = null)."""
        if self.prev is None:
            raise HandleError('iter_next after the end: the original stores to address 0')
        node = self._find(self.next)
        if self.next is not None:
            self.next.prev = self.prev
        self.prev.next = self.next
        self._stand_behind(node)

    def end(self):
        """iter_end: leave the list (the fields are not cleared)."""
        if self.next is not None:
            self.next.prev = self.prev
        if self.prev is not None:
            self.prev.next = self.next


def walk(head, mask=0):
    """The loop every caller writes: the objects in the order iter_begin / iter_next yield
    them when nothing changes the list meanwhile."""
    out = []
    it = Iterator(head, mask)
    while not it.done:
        out.append(it.current)
        it.advance()
    it.end()
    return out
