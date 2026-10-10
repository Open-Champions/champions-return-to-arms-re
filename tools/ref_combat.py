#!/usr/bin/env python3
"""ref_combat.py - reference model of the combat and statistics rules of Champions: Return
to Arms (SLUS_209.73, US v2.00): the numbers that decide a fight.

A research tool, not game code.  Every function here was written from the instruction
sequence at the address given in its docstring and is compared with that code, executed
under tools/ee_emu.py, by tools/difftest_combat.py.  docs/spec/combat.md is the prose
version.  Standard library only.  No game data is embedded: tables (experience curve, class
constants, passive masks, name fragments) are read from your own executable by
Tables.load(); the functions take them as arguments, so everything can also be run on
made-up tables (tools/test_ref_combat.py does).

What is modelled
    damage_apply        0x1e8230   one hit: mitigation, the base roll, block, both to-hit
                                   rolls, critical hits, the item-effect slots, resistances,
                                   reflection, damage over time, the floating number - with
                                   every draw from the shared seed in order
    spell and skill helpers it calls: BloodLust 0x3047b0, Spirit Shield 0x315888, Frost
                        Armor 0x318264, thorns 0x2ddccc, critical-hit bonus 0x2e76c4,
                        stunning strike 0x308c10 / 0x308cb4, Retribution 0x314790
    boss_rank           0x10d940   0 / 1 (MiniBoss) / 2 (named boss)
    level_scale         0x1e55c0   (0x1e5b70-0x1e5c94) the level's monster level per difficulty
    monster_stats       0x10a620   hit points, armour, damage, attack, experience value
    kill_experience     0x110d30   (0x111e3c-0x112248) experience for a kill and its split
    give_exp            0x1d3150   experience, level-ups, points
    recalc_stats        0x1b6458   effective statistics, max hit points and mana, load limit
    recalc_armor        0x1b5790   player armour and resistances, figurine bonuses
    recalc_damage       0x1b7158   player attack rating and weapon damage
    item_damage_range / item_attack_rating / item_armor_value   0x104100 / 0x103f88 / 0x103ec8
    powf, sqrtf, scalbnf           the C library's single-precision power function
                                   (0x3a7930, 0x3a84c0, 0x3aa810), needed bit for bit
    the soft-float double routines the damage roll and the hit-point roll go through

Floats are raw 32-bit patterns
    Online play is lockstep, so the last bit matters, and the console's FPU is not IEEE 754.
    Every float in this module is an int holding the 32-bit pattern and all arithmetic goes
    through the Fpu class, which follows the rules of the interpreter in tools/ee_emu.py
    (and offers the same adder models).  f32() turns a Python float into a pattern,
    to_float() turns one back for printing.

Virtual calls are callbacks
    The original reaches skill statistics, the victim's take-damage function, skill casts
    and a few effects through virtual tables.  The model takes them as callbacks on the
    World object (stat, stat_for, adjust_level, ...) and logs them; what the callbacks
    return is an input of the model, not something it knows.
"""
import math
import struct
from fractions import Fraction

M32 = 0xFFFFFFFF
M64 = 0xFFFFFFFFFFFFFFFF
SIGN = 0x80000000
FMAX = 0x7FFFFFFF           # what the R5900 produces on overflow and on division by zero


# =======================================================================================
# 1. Integers and R5900 single precision
# =======================================================================================

def s8(x):
    x &= 0xFF
    return x - 0x100 if x & 0x80 else x


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def s32(x):
    x &= M32
    return x - 0x100000000 if x & SIGN else x


def f32(value):
    """Pattern of the IEEE single nearest to a Python float (for inputs and examples; the
    game's own constants are given as patterns)."""
    try:
        return struct.unpack('<I', struct.pack('<f', value))[0]
    except OverflowError:
        return 0xFF800000 if value < 0 else 0x7F800000


def to_float(raw):
    """IEEE reading of a pattern (an R5900 value with exponent field 255 shows as inf/nan)."""
    return struct.unpack('<f', struct.pack('<I', raw & M32))[0]


def c_rem(a, b):
    """Remainder of the MIPS `div` instruction on signed 32-bit operands: the sign follows
    the dividend.  A zero divisor leaves the dividend in HI on the R5900 (as reported; the
    interpreter needs div_zero='r5900' to continue there)."""
    if b == 0:
        return a
    q = abs(a) // abs(b)
    if (a < 0) != (b < 0):
        q = -q
    return a - q * b


class Fpu:
    """R5900 single precision on raw patterns: no NaN, infinity or denormal; exponent field
    0 is zero and 255 is an ordinary large number; overflow and division by zero give
    +/-0x7fffffff; results are truncated toward zero.  model, mul_bias and div_nearest are
    the same switches as in tools/ee_emu.py (they exist to measure sensitivity)."""
    MODELS = ('ps2', 'ps2g1', 'chop', 'nearest')

    def __init__(self, model='ps2', mul_bias=False, div_nearest=False):
        if model not in self.MODELS:
            raise ValueError('model must be one of %s' % (self.MODELS,))
        self.model, self.mul_bias, self.div_nearest = model, mul_bias, div_nearest

    @staticmethod
    def _split(raw):
        exp = (raw >> 23) & 0xFF
        if exp == 0:
            return raw >> 31, 0, 0
        return raw >> 31, (raw & 0x7FFFFF) | 0x800000, exp

    @staticmethod
    def _pack(sign, mag, e2, nearest):
        """(pattern, out of range) for (-1)**sign * mag * 2**e2, mag a positive integer."""
        drop = mag.bit_length() - 24
        if drop > 0:
            kept = mag >> drop
            if nearest:
                rest = mag & ((1 << drop) - 1)
                half = 1 << (drop - 1)
                if rest > half or (rest == half and kept & 1):
                    kept += 1
                    if kept == 0x1000000:
                        kept >>= 1
                        drop += 1
        else:
            kept = mag << -drop
        exp = e2 + drop + 150
        if exp > 255:
            return (sign << 31) | FMAX, True
        if exp < 1:
            return sign << 31, True
        return (sign << 31) | (exp << 23) | (kept & 0x7FFFFF), False

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
            total = ((-ma if sa else ma) << 6) + (((-mb if sb else mb) << 6) >> gap)
            if total == 0:
                return 0
            return self._pack(1 if total < 0 else 0, abs(total), ea - 156, False)[0]
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
        return self._pack(1 if total < 0 else 0, abs(total), low - 150, self.model == 'nearest')[0]

    def sub(self, a, b):
        return self.add(a, (b ^ SIGN) & M32)

    def mul(self, a, b):
        sa, ma, ea = self._split(a)
        sb, mb, eb = self._split(b)
        sign = sa ^ sb
        if ma == 0 or mb == 0:
            return sign << 31
        product = ma * mb
        raw, out = self._pack(sign, product, ea + eb - 300, self.model == 'nearest')
        if self.mul_bias and not out:
            drop = product.bit_length() - 24
            if drop > 0 and product & ((1 << drop) - 1) and (raw & FMAX) > 0x00800000:
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
        quotient, remainder = divmod(ma << 40, mb)
        quotient = (quotient << 1) | (1 if remainder else 0)
        return self._pack(sign, quotient, ea - eb - 41, self.div_nearest or self.model == 'nearest')[0]

    def sqrt(self, a):
        """Square root of |a| (the instruction ignores the sign; -0 stays -0)."""
        sa, ma, ea = self._split(a)
        if ma == 0:
            return sa << 31
        e = ea - 150
        if e & 1:
            ma <<= 1
            e -= 1
        wide = ma << 48
        root = math.isqrt(wide)
        root = (root << 1) | (1 if root * root != wide else 0)
        return self._pack(0, root, e // 2 - 25, self.div_nearest or self.model == 'nearest')[0]

    def from_int(self, value):
        value = s32(value)
        if value == 0:
            return 0
        return self._pack(1 if value < 0 else 0, abs(value), 0, self.model == 'nearest')[0]

    @staticmethod
    def to_int(a):
        """cvt.w.s: truncate toward zero, saturate; returns a signed int."""
        exp = (a >> 23) & 0xFF
        if exp == 0:
            return 0
        if exp >= 158:
            return -0x80000000 if a & SIGN else 0x7FFFFFFF
        man = (a & 0x7FFFFF) | 0x800000
        shift = exp - 150
        mag = man << shift if shift >= 0 else man >> -shift
        return -mag if a & SIGN else mag

    @staticmethod
    def compare(a, b):
        """-1, 0 or 1 by sign and magnitude of the patterns; +0 equals -0."""
        x = -(a & FMAX) if a & SIGN else a & FMAX
        y = -(b & FMAX) if b & SIGN else b & FMAX
        return (x > y) - (x < y)


_fpu = Fpu()


def set_fpu(model='ps2', mul_bias=False, div_nearest=False):
    """Choose the arithmetic every function of this module uses; returns the Fpu."""
    global _fpu
    _fpu = Fpu(model, mul_bias, div_nearest)
    return _fpu


def fadd(a, b):
    return _fpu.add(a, b)


def fsub(a, b):
    return _fpu.sub(a, b)


def fmul(a, b):
    return _fpu.mul(a, b)


def fdiv(a, b):
    return _fpu.div(a, b)


def fsqrt(a):
    return _fpu.sqrt(a)


def itof(value):
    """cvt.s.w of a signed 32-bit integer."""
    return _fpu.from_int(value)


def ftoi(a):
    return Fpu.to_int(a)


def flt(a, b):
    return Fpu.compare(a, b) < 0


def fle(a, b):
    return Fpu.compare(a, b) <= 0


def feq(a, b):
    return Fpu.compare(a, b) == 0


def fmin(a, b):
    """min.s: the first operand unless the second is smaller."""
    return a if Fpu.compare(a, b) <= 0 else b


def fmax(a, b):
    """max.s: the first operand unless the second is larger."""
    return a if Fpu.compare(a, b) >= 0 else b


def round_half_away(a):
    """The inline rounding idiom: add 0.5 when 0 <= a, subtract 0.5 otherwise, cvt.w.s."""
    return ftoi(fadd(a, HALF) if fle(ZERO, a) else fsub(a, HALF))


ZERO = 0x00000000
HALF = 0x3F000000
ONE = 0x3F800000
TWO = 0x40000000
THREE = 0x40400000
FIVE = 0x40A00000
SIXTY = 0x42700000
MINUS_ONE = 0xBF800000
K_001 = 0x3C23D70A          # 0.01 (this one is the nearest single, not the truncated one)
K_65536 = 0x47800000        # turns a probability into a threshold for a 16-bit draw
K_1_65536 = 0x37800000      # turns a 16-bit draw into [0, 1)
K_1_30 = 0x3D088888         # 1/30, truncated


# =======================================================================================
# 2. The soft-float double routines
# =======================================================================================
# The executable has no double-precision FPU; doubles go through library routines
# (int -> double 0x3afa08, single -> double 0x3aef58, add 0x3af410, multiply 0x3af4d0,
# double -> single 0x3afb90, fmod 0x3a5a38 -> 0x3a6208).  Executed under the interpreter
# they turned out NOT to be IEEE: single -> double reads exponent field 255 as an ordinary
# number and a denormal as zero, add and multiply truncate toward zero, and double -> single
# truncates toward zero, gives a zero below 2**-126 and the pattern 0x7f800000 (which the
# FPU then treats as 2**128) from 2**129 up.  fmod is exact.  Doubles are Fractions here;
# NAN stands for the one not-a-number the damage roll can produce (fmod by zero).

NAN = 'nan'


def _chop(q, bits):
    """q truncated toward zero to `bits` significant bits (a Fraction)."""
    if q == 0:
        return q
    mag = abs(q)
    e = mag.numerator.bit_length() - mag.denominator.bit_length() - bits
    while mag >= Fraction(2) ** (e + bits):
        e += 1
    while mag < Fraction(2) ** (e + bits - 1):
        e -= 1
    kept = Fraction(int(mag / Fraction(2) ** e)) * Fraction(2) ** e
    return -kept if q < 0 else kept


def dbl_from_int(value):
    """__floatsidf 0x3afa08: exact."""
    return Fraction(s32(value))


def dbl_from_single(raw):
    """__extendsfdf2 0x3aef58: exact; exponent field 0 is zero, 255 an ordinary number."""
    exp = (raw >> 23) & 0xFF
    if exp == 0:
        return Fraction(0)
    q = Fraction((raw & 0x7FFFFF) | 0x800000) * Fraction(2) ** (exp - 150)
    return -q if raw & SIGN else q


def dbl_add(a, b):
    """__adddf3 0x3af410: the exact sum truncated toward zero to 53 bits."""
    if a is NAN or b is NAN:
        return NAN
    return _chop(a + b, 53)


def dbl_mul(a, b):
    """__muldf3 0x3af4d0: the exact product truncated toward zero to 53 bits."""
    if a is NAN or b is NAN:
        return NAN
    return _chop(a * b, 53)


def dbl_fmod(a, b):
    """fmod 0x3a6208: exact remainder with the sign of a; a zero divisor gives a NaN."""
    if a is NAN or b is NAN or b == 0:
        return NAN
    mag = abs(a) - abs(b) * (abs(a) // abs(b))
    return -mag if a < 0 else mag


def dbl_to_single(q):
    """__truncdfsf2 0x3afb90: truncated toward zero to 24 bits; below 2**-126 a zero; from
    2**129 up, and for a NaN, the pattern 0x7f800000 (with the sign for a number)."""
    if q is NAN:
        return 0x7F800000
    if q == 0:
        return 0
    sign = SIGN if q < 0 else 0
    mag = abs(q)
    e = mag.numerator.bit_length() - mag.denominator.bit_length() - 24
    while mag >= Fraction(2) ** (e + 24):
        e += 1
    while mag < Fraction(2) ** (e + 23):
        e -= 1
    exp = e + 150
    if exp < 1:
        return sign
    if exp > 255:
        return sign | 0x7F800000
    return sign | (exp << 23) | (int(mag / Fraction(2) ** e) & 0x7FFFFF)


# =======================================================================================
# 3. The C library's powf
# =======================================================================================
# libm_powf 0x3a5ac8 jumps to 0x3a7930, a build of the usual single-precision power kernel
# with the NaN and infinity tests removed and "zero" widened to "exponent field 0".  All
# its arithmetic is FPU arithmetic, so its last bits follow the console's truncation; the
# constants below are the kernel's (they are the library's, not the game's).

_BP = (0x3F800000, 0x3FC00000)                  # table 0x5619c0
_DP_H = (0x00000000, 0x3F15C000)                # table 0x5619c8
_DP_L = (0x00000000, 0x35D1CFDC)                # table 0x5619d0
_HUGE = 0x7149F2C9                              # 1e30
_TINY = 0x0DA2425F                              # 1e-30
_HUGE_SQUARED = 0x7F7FFFFF                      # folded constant at 0x561a44


def sqrtf(x):
    """0x3a84c0: bit-by-bit square root; rounds up when the remainder is not zero and the
    last bit is set.  A negative argument gives (x - x) / (x - x), which is 0x7fffffff."""
    ix = s32(x)
    if not (x & FMAX) > 0x007FFFFF:
        return x & M32
    if ix < 0:
        d = fsub(x, x)
        return fdiv(d, d)
    m = (ix >> 23) - 0x7F
    ix = ((ix & 0x007FFFFF) | 0x00800000) << (m & 1)
    m >>= 1
    ix = (ix << 1) & M32
    q = s = 0
    r = 0x01000000
    while r:
        t = s + r
        if not s32(ix) < s32(t):
            ix = (ix - t) & M32
            s = t + r
            q += r
        r >>= 1
        ix = (ix << 1) & M32
    if ix:
        q += q & 1
    return (0x3F000000 + (q >> 1) + (m << 23)) & M32


def scalbnf(x, n):
    """0x3aa810: multiply by 2**n by adjusting the exponent field; anything that would
    leave the field's range becomes huge*huge or tiny*tiny with the sign of x."""
    ix = x & FMAX
    if not ix > 0x007FFFFF:
        return x & M32
    k = (ix >> 23) + n
    if k >= 0x100:
        big = True
    elif k > 0:
        return (x & 0x807FFFFF) | (k << 23)
    else:
        big = n > 50000
    c = _HUGE if big else _TINY
    return fmul(c | (x & SIGN), c)


def powf(x, y):
    """libm_powf 0x3a5ac8 -> 0x3a7930, operation for operation."""
    hx, hy = s32(x), s32(y)
    ix, iy = x & FMAX, y & FMAX
    if not iy > 0x007FFFFF:
        return ONE
    yisint = 0
    if hx < 0:
        if iy > 0x4B7FFFFF:
            yisint = 2
        elif iy > 0x3F7FFFFF:
            j = (0x96 - (iy >> 23)) & 31
            t = iy >> j
            if (t << j) & M32 == iy:
                yisint = 2 - (t & 1)
    if iy == 0x3F800000:
        return x & M32 if hy >= 0 else fdiv(ONE, x)
    if hy == 0x40000000:
        return fmul(x, x)
    if hy == 0x3F000000 and hx >= 0:
        return sqrtf(x)
    ax = x & FMAX
    if not ix > 0x007FFFFF or ix == 0x3F800000:
        z = ax
        if hy < 0:
            z = fdiv(ONE, z)
        if hx >= 0:
            return z
        if ((ix - 0x3F800000) & M32) | yisint == 0:
            d = fsub(z, z)
            return fdiv(d, d)
        return z ^ SIGN if yisint == 1 else z
    negative = (x >> 31) & 1
    if (negative - 1) | yisint == 0:
        d = fsub(x, x)
        return fdiv(d, d)
    if iy > 0x4D000000:
        if not ix > 0x3F7FFFF7:
            return _HUGE_SQUARED if hy < 0 else ZERO
        if ix > 0x3F800007:
            return _HUGE_SQUARED if hy > 0 else ZERO
        t = fsub(x, ONE)
        w = fmul(fmul(t, t), fsub(HALF, fmul(t, fsub(0x3EAAAAAA, fmul(t, 0x3E800000)))))
        u = fmul(t, 0x3FB8AA00)
        v = fsub(fmul(t, 0x36ECA56F), fmul(w, 0x3FB8AA3A))
        t1 = fadd(u, v) & 0xFFFFF000
        t2 = fsub(v, fsub(t1, u))
    else:
        j = ix & 0x007FFFFF
        n = (ix >> 23) - 0x7F
        ix2 = j | 0x3F800000
        k = 0
        if j > 0x1CC471:
            if j > 0x5DB3D6:
                n += 1
                ix2 = (ix2 - 0x00800000) & M32
            else:
                k = 1
        ax = ix2
        bp = _BP[k]
        u = fsub(ax, bp)
        v = fdiv(ONE, fadd(ax, bp))
        s = fmul(u, v)
        s_h = s & 0xFFFFF000
        t_h = (((ix2 >> 1) | 0x20000000) + (k << 21) + 0x00040000) & M32
        t_l = fsub(ax, fsub(t_h, bp))
        s2 = fmul(s, s)
        r = fmul(s2, 0x3E53F142)
        s_l = fmul(v, fsub(fsub(u, fmul(s_h, t_h)), fmul(s_h, t_l)))
        r = fmul(s2, fadd(r, 0x3E6C3254))
        r = fmul(s2, fadd(r, 0x3E8BA304))
        r = fmul(s2, fadd(r, 0x3EAAAAAB))
        r = fmul(s2, fadd(r, 0x3EDB6DB7))
        r = fmul(fmul(s2, s2), fadd(r, 0x3F199999))
        r = fadd(r, fmul(s_l, fadd(s_h, s)))
        s2 = fmul(s_h, s_h)
        t_h = fadd(fadd(s2, THREE), r) & 0xFFFFF000
        t_l = fsub(r, fsub(fsub(t_h, THREE), s2))
        u = fmul(s_h, t_h)
        v = fadd(fmul(s_l, t_h), fmul(t_l, s))
        p_h = fadd(u, v) & 0xFFFFF000
        p_l = fsub(v, fsub(p_h, u))
        z_h = fmul(p_h, 0x3F763800)
        z_l = fadd(fadd(fmul(p_h, 0x369DC39F), fmul(p_l, 0x3F76384E)), _DP_L[k])
        t = itof(n)
        t1 = fadd(fadd(fadd(z_h, z_l), _DP_H[k]), t) & 0xFFFFF000
        t2 = fsub(z_l, fsub(fsub(fsub(t1, t), _DP_H[k]), z_h))
    sn = MINUS_ONE if (negative - 1) | (yisint - 1) == 0 else ONE
    y1 = y & 0xFFFFF000
    p_l = fadd(fmul(fsub(y, y1), t1), fmul(y, t2))
    p_h = fmul(y1, t1)
    z = fadd(p_l, p_h)
    j = s32(z)
    i = j & FMAX
    if j > 0:
        if i > 0x43010000 or (i == 0x43010000 and flt(fsub(z, p_h), fadd(p_l, 0x3338AA3B))):
            return fmul(fmul(sn, _HUGE), _HUGE)
    else:
        if i > 0x42FC0000 or (i == 0x42FC0000 and fle(p_l, fsub(z, p_h))):
            return fmul(fmul(sn, _TINY), _TINY)
    n = 0
    zbits = z
    if i > 0x3F000000:
        n = (j + (0x00800000 >> (((i >> 23) - 0x7E) & 31))) & M32
        k = ((n >> 23) & 0xFF) - 0x7F
        t = n & ~(0x007FFFFF >> (k & 31)) & M32
        n = ((n & 0x007FFFFF) | 0x00800000) >> ((23 - k) & 31)
        if j < 0:
            n = -n
        p_h = fsub(p_h, t)
        zbits = fadd(p_l, p_h)
    t = zbits & 0xFFFFF000
    u = fmul(t, 0x3F317200)
    v = fadd(fmul(fsub(p_l, fsub(t, p_h)), 0x3F317217), fmul(t, 0x35BFBE8C))
    z = fadd(u, v)
    w = fsub(v, fsub(z, u))
    t = fmul(z, z)
    c = fmul(t, 0x3331BB4B)
    c = fmul(t, fadd(c, 0xB5DDEA0E))
    c = fmul(t, fadd(c, 0x388AB354))
    c = fmul(t, fadd(c, 0xBB360B60))
    c = fmul(t, fadd(c, 0x3E2AAAAA))
    t1 = fsub(z, c)
    r = fsub(fdiv(fmul(z, t1), fsub(t1, TWO)), fadd(w, fmul(z, w)))
    z = fsub(ONE, fsub(r, z))
    j = (z + (n << 23)) & M32
    if s32(j) >> 23 <= 0:
        z = scalbnf(z, n)
    else:
        z = j
    return fmul(sn, z)


# =======================================================================================
# 4. Angles and the random generator
# =======================================================================================

def cos16(angle):
    """math_cos16 0x166630: cosine of a 16-bit angle (0x10000 is a full turn)."""
    a = s16(angle)
    sign = ONE
    if (a ^ (a << 1)) & 0x8000:
        sign = MINUS_ONE
        a = (a & 0x7FFF) - (0x8000 if a & 0x4000 else 0)
    x = fmul(itof(a), 0x38490FDA)
    x2 = fmul(x, x)
    x3 = fmul(x, x2)
    s = fsub(x, fmul(x3, 0x3E2AAA57))
    x5 = fmul(x3, x2)
    s = fadd(s, fmul(x5, 0x3C086B24))
    x7 = fmul(x5, x2)
    s = fsub(s, fmul(x7, 0x39458017))
    return fmul(sign, fsub(ONE, fmul(fadd(s, s), s)))


def sin16(angle):
    """math_sin16 0x1666e0: cos16(angle - 0x4000)."""
    return cos16(angle - 0x4000)


class Seed:
    """The engine's generator:  state = state * 0x19660d + 0x3c6ef35f (mod 2**32); a draw
    is the upper 16 bits of the new state.  Used for the shared seed 0x404464 (part of the
    sync hash), the cosmetic seed 0x404460 and each object's own seed at +0x44.  draws
    keeps every value drawn, in order."""

    def __init__(self, state=0):
        self.state = state & M32
        self.draws = []

    def draw(self):
        self.state = (self.state * 0x0019660D + 0x3C6EF35F) & M32
        value = self.state >> 16
        self.draws.append(value)
        return value

    def in_unit_sphere(self):
        """Three draws mapped to [-1, 1), repeated while the point is outside the unit
        sphere (the inline loop at 0x1e88f8)."""
        while True:
            p = []
            for _ in range(3):
                u = fmul(itof(self.draw()), K_1_65536)
                p.append(fsub(fadd(u, u), ONE))
            if not flt(ONE, fadd(fadd(fmul(p[0], p[0]), fmul(p[1], p[1])), fmul(p[2], p[2]))):
                return p


# =======================================================================================
# 5. Records
# =======================================================================================

class Record:
    """A bag of named fields with defaults; unknown names are refused."""
    FIELDS = {}

    def __init__(self, **values):
        for name, default in self.FIELDS.items():
            setattr(self, name, list(default) if isinstance(default, list) else default)
        for name, value in values.items():
            if name not in self.FIELDS:
                raise TypeError('%s has no field %r' % (type(self).__name__, name))
            setattr(self, name, value)

    def copy(self):
        return type(self)(**{name: (list(getattr(self, name)) if isinstance(getattr(self, name), list)
                                    else getattr(self, name)) for name in self.FIELDS})


class Spell(Record):
    """An attached spell.  kind is the class the original tests with typeid; skill is the
    id of the Skill it belongs to (spell +8), level its level byte (spell +0), owner the
    creature at spell +0xc."""
    FIELDS = {'kind': '', 'skill': 0, 'level': 1, 'owner': None,
              'f18': 0,             # +0x18 s32   Spirit Shield: "hit effect started"
              'f1c': ZERO,          # +0x1c float Spirit Shield: counter compared with its limit
              'f20': ZERO,          # +0x20 float Spirit Shield: end of the hit effect
              'f2c': 0}             # +0x2c s32   BloodLust: active


class Obj(Record):
    """The fields of a game object that the combat code reads or writes."""
    FIELDS = {
        'tag': 'obj',
        'flags': 0,                 # +0x0c  0x8 dead, 0x20 creature, 0x40 player, 0x80 has owner link, 0x20000 prediction copy
        'pos': [ZERO, ZERO, ZERO],  # +0x10 x, y, height
        'facing': 0,                # +0x38 s16
        'owner_link': False,        # +0x4c non-null (objects with flag 0x80)
        'owner': None,              #        the object behind the link
        'cls': 'Creature',          # C++ class, compared with typeid
        'innoruuk_immune': 0,       # +0x3e0 (class Innoruuk only)
        'res': [ZERO] * 5,          # +0x5c fire, +0x60 cold, +0x64 poison, +0x68 disease, +0x6c lightning
        'flash': [0] * 8,           # +0x90 s16[8]
        'cflags': 0,                # +0xa8 u64 creature flags
        'kind': 0,                  # +0xb4 s8
        'dot': ZERO,                # +0xcc float, damage-over-time accumulator
        'field_dc': ZERO,           # +0xdc float (read through a GiantGrowth spell)
        'armor': 0,                 # +0xe4 s16
        'stamp_f0': 0,              # +0xf0 s32
        'hp': ZERO,                 # +0x228 float
        'max_hp': ZERO,             # +0x22c float
        'status': [ZERO] * 5,       # +0x340 burn, cold, shock, poison, +0x350
        'poison_a': 0,              # +0x358 s16
        'poison_b': 0,              # +0x35a s16
        'status_source': None,      # +0x360 handle: who caused the last status
        'spells': [],               # +0x364 list, in list order
        'counter2': 0,              # +0x374 status counter 2
        'counter4': 0,              # +0x37c status counter 4
        'counter11': 0,             # +0x398
        'counter12': 0,             # +0x39c
        'slot': 0,                  # +0x3c8 (players)
        'state': 0,                 # +0x58c (players)
        'attack_start': 0,          # +0x458 frame stamp (players)
        'attack_chain': 0,          # +0x45c frame stamp (players)
        'bonus': [0] * 4,           # +0x474 s8[4] (players)
        'model_points': 1,          # sample points of the drawn model (thorns needs one)
        'boss_rank': 0,             # what creature_bossRank returns for it
        'exp_value': ZERO,          # +0xd8 float
        'own_seed': 0,              # +0x44 the object's own generator
        'last_attacker': None,      # +0x2e4 handle
    }

    def spell(self, kind):
        """creature_findSpellByType 0x11a710: the first attached spell of that class."""
        for spell in self.spells:
            if spell.kind == kind:
                return spell
        return None


EMPTY_DESC = [(-1, 0, 0, 0)] * 4


def desc_get(desc, kind, field):
    """First effect slot whose type is `kind`: its value 1, 2 or 3; 0 when there is none."""
    for slot in desc:
        if s16(slot[0]) == kind:
            return s16(slot[field])
    return 0


class ItemDef(Record):
    """An item definition row (0x40 bytes)."""
    FIELDS = {'name': '', 'dmg_min': 0, 'dmg_max': 0, 'armor': 0, 'attack': 0,
              'category': 0,        # +0x1d  0 weapon, 1 armour, 2 other
              'subtype': 0,         # +0x1e  4 bow, 6 thrown
              'dmg_type': 0,        # +0x20  damage-type bits 1, 4, 8
              'flags': 0}           # +0x28  u64


class Item(Record):
    """An item record (0x48 bytes): definition, count, flags and four modifier slots, each
    (code, value 1, value 2, value 3).  The modifier slots are what damage_apply reads as
    the damage descriptor when the item is the weapon."""
    FIELDS = {'defn': None, 'count': 1, 'flags': 0, 'mods': [(-1, 0, 0, 0)] * 4}

    def mod(self, code, field=1):
        return desc_get(self.mods, code, field)


class PlayerRec(Record):
    """The per-player record (0x4c30 bytes), as far as these rules use it."""
    FIELDS = {
        'cls': 0,                   # +0x50
        'level58': 1,               # +0x58 s8, acknowledged level (attack rating)
        'level59': 1,               # +0x59 s8, level earned (hit points, mana, experience)
        'exp': 0,                   # +0x5c
        'base': [0] * 4,            # +0x78 strength, intelligence, dexterity, stamina
        'eff': [0] * 4,             # +0x90
        'hp': ZERO,                 # +0xac
        'max_hp': ZERO,             # +0xb0
        'mana': ZERO,               # +0xc0
        'max_mana': ZERO,           # +0xc4
        'attack': 0,                # +0xcc
        'dmg_min': 0,               # +0xd0
        'dmg_max': 0,               # +0xd4
        'stagger': ZERO,            # +0xdc
        'skill_points': 0,          # +0xe8
        'stat_points': 0,           # +0xec s8
        'passives': [0] * 48,       # +0xef s8[48]
        'load_limit': ZERO,         # +0x124
        'bag2': [],                 # +0x2540 up to 64 items (figurines are counted here)
        'obj': None,                # +0x43d8
        'equip': [None] * 17,       # +0x43f0
        'weapon_sets': [None, None],  # +0x4434
        'second_weapon': None,      # +0x443c
        'active_set': 0,            # +0x4a7c s8
        'skills': [],               # +0x4b08 (id, rank) pairs up to the first id -1
    }

    def rank(self, skill):
        """player_getSkillRank 0x1bf330."""
        for ident, rank in self.skills:
            if s16(ident) == -1:
                break
            if s16(ident) == skill:
                return s16(rank)
        return 0


class World:
    """Globals the rules read, the callbacks that stand for virtual calls, and the log."""

    def __init__(self, seed=0, cosmetic=0):
        self.seed = Seed(seed)              # g_randSeed 0x404464
        self.cosmetic = Seed(cosmetic)      # g_cosmeticSeed 0x404460
        self.frame = 0                      # g_simFrame 0x44fdcc
        self.pvp_a = 0                      # g_pvpModeA 0x4f711c
        self.cutscene = 0                   # g_cutsceneActive 0x44fcd0
        self.numbers_option = 1             # damage-number option 0x44fcf8
        self.network_mode = 0               # g_networkMode 0x402791
        self.monster_level = ONE            # g_levelMonsterLevel 0x4f714c (float)
        self.focus = [ZERO, ZERO]           # g_cameraFocus 0x44f048 x, y
        self.music = [0] * 32               # byte array 0x4f7158
        self.music_index = 0                # s16 0x4f717a
        self.players = []                   # g_players, by slot
        self.num_players = 0                # g_numPlayers 0x4d8ae0
        self.alive = []                     # g_alivePlayers 0x4f8440 (slots)
        self.medal_mission = 0              # word 0x4f713c
        self.difficulty = 1                 # g_difficultyIdx 0x4f719c
        self.level_name = ''                # g_levelTexName 0x44fe18
        self.load_cheat = 0                 # word 0x4d8ae8 (+5000 load limit)
        self.events = []
        # callbacks
        self.stat_fn = lambda skill, stat, level: 0                     # Skill slot 10
        self.stat_for_fn = lambda skill, stat, level, caster, cap: 0    # Skill slot 12
        self.adjust_fn = lambda skill, level, n: level                  # Skill slot 14
        self.pool_fn = lambda size: True                                # pool_new succeeded?
        self.enemy_fn = lambda obj, other: 1                            # creature slot 22
        self.take_damage_fn = None                                      # creature slot 2

    def log(self, *event):
        self.events.append(event)

    def stat(self, skill, stat, level):
        return s32(self.stat_fn(skill, stat, level))

    def stat_for(self, skill, stat, level, caster, cap):
        return s32(self.stat_for_fn(skill, stat, level, caster, cap))

    def adjust(self, skill, level, n):
        return s32(self.adjust_fn(skill, level, n))

    def pool(self, size):
        ok = bool(self.pool_fn(size))
        self.log('pool', size, ok)
        return ok

    def take_damage(self, victim, amount, attacker, flags):
        self.log('take_damage', victim.tag, amount, attacker.tag if attacker else None, flags & M32)
        if self.take_damage_fn:
            self.take_damage_fn(victim, amount, attacker, flags)


# Sound names are given by the address of the name string; the strings stay in the game.
FX_BLOCK = 0x53DF18
FX_FIRE = 0x53DF38
FX_COLD_PROC = 0x53DF50
FX_POISON = 0x53DF70
FX_LIGHTNING = 0x53DF90
FX_COLD = 0x53DFB0
FX_DISEASE = 0x53DFC8
FX_UNDEAD_KILL = 0x53DFE0
FX_SPIRIT_SHIELD = 0x552DA0
FX_FROST_ARMOR = 0x553040
FX_STUN = 0x5520F8

CF_BLOCKING = 0x200
CF_INVULNERABLE = 0x800
CF_ABSOLUTE = 0x100000
CF_THORNS = 1 << 45

SKILL_RIPOSTE, SKILL_DISEASE, SKILL_CRIT_A, SKILL_CRIT_B = 9, 0x1D, 0x21, 0x35
SKILL_STUN, SKILL_CRIT_C, SKILL_RIPOSTE_B = 0x40, 0x51, 0x52


# =======================================================================================
# 6. The damage function
# =======================================================================================

def base_roll(dmin, dmax, draw):
    """min + fmod(draw, max - min + 1): the span is formed in single precision, the rest in
    the soft-float doubles, and the result is truncated back to a single (0x1e8414-0x1e8484
    and 0x1e8714-0x1e8788).  A span of exactly zero gives the pattern 0x7f800000."""
    span = dbl_from_single(fadd(fsub(dmax, dmin), ONE))
    return dbl_to_single(dbl_add(dbl_from_single(dmin), dbl_fmod(Fraction(draw), span)))


def set_status(w, obj, which, value, source):
    """Creature_setEffectTimer 0x118950: store a status value; a value above zero also
    re-links the status-source handle (+0x360) to `source` (or leaves it empty)."""
    obj.status[which] = value
    if flt(ZERO, value):
        obj.status_source = source
        w.log('status_source', obj.tag, source.tag if source else None)


def _proc_amount(w, lo, hi):
    """lo + draw % (hi - lo + 1) as a float."""
    return itof(lo + c_rem(w.seed.draw(), s32(hi - lo + 1)))


def _fx(w, name, target):
    w.log('fx', name, target.tag)


def bloodlust_armor_factor(w, spell):
    """SpellBloodLust_getStat2Complement 0x3047b0: 1 - statistic 2 / 100 while active."""
    if spell.f2c == 0:
        return ONE
    return fsub(ONE, fmul(itof(w.stat(spell.skill, 2, s8(spell.level))), K_001))


def spirit_shield_absorbs(w, spell):
    """SpellSpiritShield_playHitEffect 0x315888: statistic 0 is a limit for the spell's
    counter, statistic 1 a percent chance.  One shared draw unless the counter is above the
    limit."""
    limit = w.stat_for(spell.skill, 0, s8(spell.level), spell.owner, 10)
    chance = w.stat_for(spell.skill, 1, s8(spell.level), spell.owner, 10)
    if flt(itof(limit), spell.f1c):
        return False
    if not w.seed.draw() % 100 < chance:
        return False
    if spell.f18 == 0:
        spell.f18 = 1
        spell.f20 = fadd(spell.f1c, 0x3E449B62)
    w.log('fx_at', FX_SPIRIT_SHIELD)
    return True


def frost_armor_on_hit(w, spell, dmg, attacker):
    """SpellFrostArmor_onHit 0x318264: returns the factor 1 - statistic 1 / 100 (not below
    0).  With an attacker: one shared draw against statistic 2 percent; on success the
    attacker takes a cold hit of trunc(dmg - factor) through a nested damage_apply."""
    level = s8(spell.level)
    factor = fsub(ONE, fmul(itof(w.stat_for(spell.skill, 1, level, spell.owner, 0)), K_001))
    if flt(factor, ZERO):
        factor = ZERO
    if attacker is None:
        return factor
    roll = w.seed.draw() % 100
    if not roll < w.stat_for(spell.skill, 2, level, spell.owner, 0):
        return factor
    amount = s16(ftoi(fsub(dmg, factor)))
    desc = [(0x16, amount, amount, 0)] + [(-1, 0, 0, 0)] * 3
    damage_apply(w, attacker, spell.owner, ZERO, ZERO, 100000, 0x540, desc, 0)
    w.log('fx_at', FX_FROST_ARMOR)
    w.log('fx_spawn', 10)
    return factor


def thorns(w, skill, victim, attacker, level):
    """SkillRiposte_counterAttack 0x2ddccc: statistic 0 is the damage, statistic 1 a percent
    chance.  One shared draw; on success, and only if the victim's model has sample points,
    a second draw and a nested damage_apply against the attacker (flags 0x40, no critical)."""
    if level == 0:
        return
    damage = w.stat_for(skill, 0, level, victim, 10)
    chance = w.stat_for(skill, 1, level, victim, 10)
    if not ftoi(fmul(fmul(itof(w.seed.draw()), K_1_65536), 0x42C80000)) < chance:
        return
    victim.flash = [0x82, 0x82, 0x83, 0x55, 0x82, 0x82, 0x83, 0x55]
    if victim.model_points == 0:
        return
    w.log('thorns', skill, victim.tag)
    for _ in range(200):                # particles: cosmetic seed only
        w.cosmetic.draw()
        w.cosmetic.in_unit_sphere()
    low = itof(damage)
    high = fadd(low, fmul(fmul(low, fmul(itof(w.seed.draw()), K_1_65536)), 0x3E4CCCCC))
    damage_apply(w, attacker, victim, low, high, 100000, 0x40, None, 1)


def crit_bonus(w, skill, attacker, rank):
    """SkillCriticalHit_critBonusFor 0x2e76c4: the attacker's own rank counts only while a
    CriticalHit spell is attached to it; otherwise the best rank of another alive player
    that carries the spell and stands within 12 x statistic 1 (x, y) is used.  The bonus is
    statistic 0 / 100 at that rank."""
    use = rank if rank != 0 and attacker.spell('CriticalHit') else None
    if use is None:
        use = 0
        for slot in w.alive:
            if slot == attacker.slot:
                continue
            other = w.players[slot].obj
            d = [fsub(other.pos[i], attacker.pos[i]) for i in range(3)]
            if not flt(fadd(fadd(fmul(d[0], d[0]), fmul(d[1], d[1])), fmul(d[2], d[2])), 0x49742400):
                continue
            if w.pvp_a and not w.enemy_fn(other, attacker):
                continue
            if not other.spell('CriticalHit'):
                continue
            rec = w.players[slot]
            best = rec.rank(SKILL_CRIT_B)
            best = max(best, rec.rank(SKILL_CRIT_C))
            best = max(best, rec.rank(SKILL_CRIT_A))
            if best == 0:
                continue
            reach = itof(s32(w.stat(skill, 1, best) * 12))
            dx = fsub(other.pos[0], attacker.pos[0])
            dy = fsub(other.pos[1], attacker.pos[1])
            if flt(fadd(fmul(dx, dx), fmul(dy, dy)), fmul(reach, reach)):
                if best > 0:
                    use = best
                break
    level = w.adjust(skill, use, 0x14)
    if level == 0:
        return ZERO
    return fmul(itof(w.stat(skill, 0, level)), K_001)


def stun_chance(w, victim, rank):
    """SkillStunningStrike_getStat0ForTarget 0x308c10: statistic 0 percent; 0 against
    non-creatures, in PvP mode A and against rank-2 bosses; at most 5 against rank 1."""
    if not victim.flags & 0x20 or w.pvp_a:
        return 0
    chance = w.stat(SKILL_STUN, 0, rank)
    if victim.boss_rank >= 2:
        return 0
    if victim.boss_rank <= 0:
        return chance
    return chance if chance < 6 else 5


def stun_effect(w, victim):
    """SkillStunningStrike_spawnEffect 0x308cb4: a LightEffect (its constructor draws the
    shared seed), then one draw for a duration of 1.5 to 2.5 seconds in frames, handed to
    the victim's virtual slot 30."""
    if not victim.flags & 0x20:
        return
    w.log('fx_at', FX_STUN)
    if w.pool(0xBC):
        w.seed.draw()
        w.log('light')
    frames = ftoi(fmul(fadd(fmul(itof(w.seed.draw()), K_1_65536), 0x3FC00000), SIXTY))
    w.log('stun', victim.tag, frames)


def retribution(w, spell, dmg):
    """SpellRetribution_healOwner 0x314790: returns statistic 1 / 100; a player owner with
    hit points above zero is healed by dmg times that (up to the maximum); a player owner
    at zero gets 0 back."""
    owner = spell.owner
    owner.flash = [0x46, 0x80, 0x4B, 0x3F, owner.flash[4], 0x80, 0x4B, 0x3F]
    fraction = fmul(itof(w.stat(spell.skill, 1, s8(spell.level))), K_001)
    if owner.flags & 0x40:
        rec = w.players[owner.slot]
        if not flt(ZERO, rec.hp):
            return ZERO
        rec.hp = fadd(rec.hp, fmul(dmg, fraction))
        if flt(rec.max_hp, rec.hp):
            rec.hp = rec.max_hp
    return fraction


def colour_class(victim, flags):
    """0x1ea350-0x1ea510: 0 normal, 1 resisted, 2 immune.  Chooses the colour of the
    floating number only; it never changes the amount."""
    immune = resisted = False

    def grade(value):
        nonlocal immune, resisted
        if fle(ONE, value):
            immune = True
        elif flt(ZERO, value):
            resisted = True

    cf = victim.cflags
    if flags & 0x100:
        grade(victim.res[4])
    if flags & 4:
        resisted |= bool(cf & 2)
        immune |= bool(cf & 4)
    if flags & 8:
        immune |= bool(cf & 0x10)
        resisted |= bool(cf & 8)
    if flags & 1:
        immune |= bool(cf & 0x40)
        resisted |= bool(cf & 0x20)
    grade(victim.res[1])
    grade(victim.res[0])
    resisted |= bool(cf & 0x80)
    immune |= bool(cf & 0x100)
    grade(victim.res[4])
    grade(victim.res[2])
    grade(victim.res[3])
    return 2 if immune else int(resisted)


def _facing_front(victim, attacker):
    """True when the attacker is in front of the victim's facing (x, y only)."""
    c = cos16(victim.facing)
    s = sin16(victim.facing)
    dx = fsub(attacker.pos[0], victim.pos[0])
    dy = fsub(attacker.pos[1], victim.pos[1])
    return flt(ZERO, fadd(fmul(c, dx), fmul(s, dy)))


def damage_apply(w, victim, attacker, dmin, dmax, attack, flags, desc=None, no_crit=0):
    """damage_apply 0x1e8230.

    w        World: seeds, globals, callbacks, log
    victim   Obj (never None); attacker Obj or None
    dmin, dmax   base damage range, float patterns
    attack   attack rating, compared with the victim's armour (100000 = "always hits")
    flags    the flag word (docs/spec/combat.md lists the bits)
    desc     four effect slots (type, v1, v2, v3), or None for an empty descriptor
    no_crit  non-zero: no critical-hit bonus and no critical roll

    Returns 0 when nothing landed, 1 otherwise, as the original does.  Everything else is
    in w: every shared draw in w.seed.draws, the amounts handed to the victim's take-damage
    function and every effect in w.events, and the changed fields on the objects."""
    flags &= M32
    if attacker is not None and attacker.flags & 0x20000:
        return 0
    if desc is None:
        desc = EMPTY_DESC
    if not w.cutscene:
        dy = fsub(w.focus[1], victim.pos[1])
        dx = fsub(w.focus[0], victim.pos[0])
        if flt(fsqrt(fadd(fmul(dx, dx), fmul(dy, dy))), 0x43AA0000):
            w.music[w.music_index] = (w.music[w.music_index] + 1) & 0xFF
    if victim.cls == 'Innoruuk' and victim.innoruuk_immune != 0:
        return 0
    if not victim.flags & 0x20:
        w.take_damage(victim, base_roll(dmin, dmax, w.seed.draw()), attacker, flags)
        return 1
    cf = victim.cflags
    if cf & CF_INVULNERABLE:
        return 0
    if cf & CF_ABSOLUTE and cf & 0x50 and flags & 9:
        return 0
    if flags & 0x8000000 and s8(victim.kind) != 0x10:
        return 0
    if (attacker is not None and attacker.flags & 0x80 and not victim.flags & 0x40
            and attacker.owner_link and victim.cls == attacker.owner.cls):
        return 1
    if attacker is not None and not victim.flags & 0x40 and not attacker.flags & 0x40:
        flags |= 0x1000000
    armor = s16(victim.armor)
    spell = victim.spell('BloodLust')
    if spell:
        armor = ftoi(fmul(itof(armor), bloodlust_armor_factor(w, spell)))
        if not armor > 0:
            armor = 1
    attacker_is_player = attacker is not None and bool(attacker.flags & 0x40)
    sound_a0 = 0 if attacker_is_player else 1
    sound_slot = attacker.slot if attacker_is_player else 0

    # mitigation by armour: player victims, and everybody in PvP mode A
    if victim.flags & 0x40 or w.pvp_a:
        cut = fmul(itof(s16(victim.armor)), K_1_30)
        low = fsub(dmin, cut)
        if flt(low, fmul(dmin, HALF)):
            low = fmul(dmin, HALF)
        high = fsub(dmax, cut)
        if flt(high, fmul(dmax, HALF)):
            high = fmul(dmax, HALF)
        if flt(low, ZERO):
            low = ZERO
        if flt(high, ZERO):
            high = ZERO
        dmin, dmax = low, high

    dmg = dmin
    if not fle(dmax, dmin):
        dmg = base_roll(dmin, dmax, w.seed.draw())

    # block, then Spirit Shield
    unblockable = flags & 0x40
    if not unblockable:
        if victim.cflags & CF_BLOCKING and attacker is not None and _facing_front(victim, attacker):
            _fx(w, FX_BLOCK, victim)
            for _ in range(50):
                w.cosmetic.in_unit_sphere()
            w.log('sparks', 50)
            if not flags & 0x20000:
                return 0
            dmg = fmul(dmg, HALF)
        spell = victim.spell('SpiritShield')
        if spell and spirit_shield_absorbs(w, spell):
            if not flags & 0x20000:
                return 0
            dmg = fmul(dmg, HALF)

    # hit probability and the first hit roll
    p = fsqrt(fdiv(itof(attack), itof(armor))) if armor > 0 else ONE
    crit_chance = fmul(itof(desc_get(desc, 0x1D, 1)), K_001)
    threshold = fmul(p, K_65536)
    hit = flt(itof(w.seed.draw()), threshold)

    # reflection
    if (s32(victim.counter12) > 0 and hit and attacker is not None and attacker.flags & 0x20
            and flt(ZERO, dmg) and attacker is not victim and s8(attacker.kind) == 0x10):
        damage_apply(w, attacker, victim, dmg, dmg, 100000000, 0x100, desc, 0)
        attacker.counter11 = 0x11
        attacker.stamp_f0 = w.frame

    spell = victim.spell('FrostArmor')
    if spell:
        dmg = fmul(dmg, frost_armor_on_hit(w, spell, dmg, attacker))

    if armor > 0:
        dmg = fmul(dmg, fmin(fdiv(itof(attack), fmul(itof(armor), HALF)), ONE))

    if not flags & 0x40000000 and attacker_is_player and no_crit == 0:
        rec = w.players[attacker.slot]
        b1 = crit_bonus(w, SKILL_CRIT_A, attacker, rec.rank(SKILL_CRIT_A))
        b2 = crit_bonus(w, SKILL_CRIT_B, attacker, rec.rank(SKILL_CRIT_B))
        b3 = crit_bonus(w, SKILL_CRIT_C, attacker, rec.rank(SKILL_CRIT_C))
        crit_chance = fadd(crit_chance, fmax(b3, fmax(b1, b2)))

    crit = 0
    if flt(ZERO, crit_chance) and hit and no_crit == 0:
        if flt(itof(w.seed.draw()), fmul(crit_chance, K_65536)):
            crit = 1
            if attacker_is_player:
                w.log('voice', attacker.slot, 10)
            dmg = fmul(dmg, itof(3))

    source = attacker if attacker is not None and attacker.flags & 0x20 else None

    def chance_roll(kind):
        return flt(itof(w.seed.draw()), fmul(fmul(itof(desc_get(desc, kind, 1)), K_001), K_65536))

    def reduced(amount, resistance):
        return fsub(amount, fmul(amount, resistance))

    def cold_time(amount):
        t = victim.status[1]
        t = fadd(t, SIXTY) if feq(victim.hp, ZERO) else fadd(t, fdiv(fmul(amount, SIXTY), victim.hp))
        return SIXTY if flt(SIXTY, t) else t

    if hit:
        # 0x29: cast a skill
        if source is not None:
            chance = desc_get(desc, 0x29, 2)
            if chance != 0 and w.seed.draw() < s32(chance * 0x28F):
                w.log('cast', desc_get(desc, 0x29, 1), desc_get(desc, 0x29, 3), source.tag,
                      s16(source.facing))
        # 0x1f: chance of fire
        if chance_roll(0x1F):
            before = victim.status[0]
            set_status(w, victim, 0, fsub(ONE, victim.res[0]), source)
            if fle(before, ZERO) and flt(ZERO, victim.status[0]):
                _fx(w, FX_FIRE, victim)
            amount = _proc_amount(w, desc_get(desc, 0x1F, 2), desc_get(desc, 0x1F, 3))
            dmg = fadd(dmg, reduced(amount, victim.res[0]))
        # 0x20: chance of cold
        if chance_roll(0x20):
            _fx(w, FX_COLD_PROC, victim)
            amount = _proc_amount(w, desc_get(desc, 0x20, 2), desc_get(desc, 0x20, 3))
            dmg = fadd(dmg, reduced(amount, victim.res[1]))
            set_status(w, victim, 1, cold_time(dmg), source)
        # 0x21: chance of a poison cloud
        if chance_roll(0x21):
            _fx(w, FX_POISON, victim)
            strength = desc_get(desc, 0x21, 2)
            if w.pool(0x70):
                w.seed.draw()               # GameObject_ctor
                w.log('gas', strength * 30 + 30, strength * 25 + 25, attacker.tag if attacker else None)
        # 0x22: chance of lightning
        if chance_roll(0x22):
            set_status(w, victim, 2, TWO, source)
            _fx(w, FX_LIGHTNING, victim)
            amount = _proc_amount(w, desc_get(desc, 0x22, 2), desc_get(desc, 0x22, 3))
            dmg = fadd(dmg, reduced(amount, victim.res[4]))

    # the slots that do not need the first hit roll
    percent = desc_get(desc, 0x1B, 1)
    if percent != 0 and s8(victim.kind) == 0x10:
        dmg = fadd(fmul(fmul(itof(percent), K_001), dmg), dmg)
    if desc_get(desc, 0x15, 1) != 0:
        resistance, before = victim.res[0], victim.status[0]
        amount = _proc_amount(w, desc_get(desc, 0x15, 1), desc_get(desc, 0x15, 2))
        dmg = fadd(dmg, reduced(amount, resistance))
        if not flags & 0x10000000:
            set_status(w, victim, 0, fsub(TWO, fadd(resistance, resistance)), source)
        if fle(before, ZERO) and flt(ZERO, victim.status[0]):
            _fx(w, FX_FIRE, victim)
    if desc_get(desc, 0x16, 1) != 0:
        amount = _proc_amount(w, desc_get(desc, 0x16, 1), desc_get(desc, 0x16, 2))
        amount = reduced(amount, victim.res[1])
        w.log('fx_at', FX_COLD)
        dmg = fadd(dmg, amount)
        set_status(w, victim, 1, cold_time(amount), source)
    if desc_get(desc, 0x17, 1) != 0:
        _fx(w, FX_POISON, victim)
        set_status(w, victim, 3, fsub(FIVE, fmul(victim.res[2], FIVE)), source)
        victim.poison_a = desc_get(desc, 0x17, 1)
        victim.poison_b = desc_get(desc, 0x17, 2)
    if desc_get(desc, 0x26, 1) != 0:
        late = flags & 0xC000
        if not late:
            _fx(w, FX_DISEASE, victim)
        if not victim.spell('DiseaseEffect'):
            if late:
                _fx(w, FX_DISEASE, victim)
            made = w.pool(0x1B0)
            if made:
                w.seed.draw()               # the Spell constructor seeds its own generator
                strength = ftoi(fsub(FIVE, fmul(victim.res[3], FIVE)))
                victim.spells = victim.spells + [Spell(kind='DiseaseEffect', skill=SKILL_DISEASE,
                                                       level=0, owner=victim)]
                w.log('disease', strength, victim.tag, attacker.tag if attacker else None)
            w.log('add_spell', victim.tag, made)
    if desc_get(desc, 0x18, 1) != 0:
        amount = _proc_amount(w, desc_get(desc, 0x18, 1), desc_get(desc, 0x18, 2))
        dmg = fadd(dmg, reduced(amount, victim.res[4]))
        _fx(w, FX_LIGHTNING, victim)
        set_status(w, victim, 2, fsub(TWO, fadd(victim.res[4], victim.res[4])), source)
    if desc_get(desc, 0x19, 1) != 0 and s8(victim.kind) == 0x12:
        set_status(w, victim, 2, TWO, source)
        _fx(w, FX_LIGHTNING, victim)
        amount = _proc_amount(w, desc_get(desc, 0x19, 1), desc_get(desc, 0x19, 2))
        dmg = fadd(dmg, reduced(amount, victim.res[4]))
    if desc_get(desc, 0x1A, 1) != 0 and s8(victim.kind) == 0x12:
        if not desc_get(desc, 0x1A, 1) < w.seed.draw() % 100:
            flags |= 0x800
            _fx(w, FX_LIGHTNING, victim)
            dmg = fadd(dmg, victim.hp)
    if desc_get(desc, 0x1C, 1) != 0 and s8(victim.kind) == 0x10:
        if not desc_get(desc, 0x1C, 1) < w.seed.draw() % 100:
            flags |= 0x2000000
            _fx(w, FX_UNDEAD_KILL, victim)
            dmg = fadd(dmg, victim.hp)

    # second hit roll: a miss discards the amount, not what already happened
    if not crit and not flt(itof(w.seed.draw()), threshold):
        if not flags & 0x8000:
            w.log('hit_sound', dmg, sound_a0, sound_slot, flags, 0)
        w.take_damage(victim, ZERO, attacker, 0x2000 if victim.flags & 0x40 else 0x42000)
        return 0

    colour = colour_class(victim, flags)

    if attacker is not None and flags & 0xD:
        if victim.flags & 0x20 and attacker.flags & 0x20:
            if victim.flags & 0x40:
                rec = w.players[victim.slot]
                if rec.rank(SKILL_RIPOSTE):
                    thorns(w, SKILL_RIPOSTE, victim, attacker, rec.rank(SKILL_RIPOSTE))
                if rec.rank(SKILL_RIPOSTE_B):
                    thorns(w, SKILL_RIPOSTE_B, victim, attacker, rec.rank(SKILL_RIPOSTE_B))
            elif victim.cflags & CF_THORNS:
                thorns(w, SKILL_RIPOSTE, victim, attacker, ftoi(w.monster_level))
        if victim.flags & 0x40 and attacker.flags & 0x20 and s8(attacker.kind) == 0x10:
            first = victim.spell('UndeadShield')
            second = victim.spell('SecondaryUndeadShield')
            if first:
                w.log('undead_shield', 1, victim.tag, attacker.tag, ftoi(dmg))
            elif second:
                w.log('undead_shield', 2, victim.tag, attacker.tag, ftoi(dmg))

    victim_is_player = 1 if victim.flags & 0x40 else 0
    if w.pvp_a and victim_is_player:
        dmg = fmul(dmg, HALF)
    number = ftoi(fadd(dmg, HALF))

    if flags & 0x800000:                # damage over time: collect, deliver every 32nd frame
        total = fadd(victim.dot, dmg)
        dmg = ZERO
        victim.dot = total
        if w.frame & 0x1F == 0:
            if fle(total, ONE):
                victim.dot = ONE
            number = ftoi(fadd(victim.dot, HALF))
            w.take_damage(victim, itof(ftoi(victim.dot)), attacker, flags)
            victim.dot = ZERO

    if not flags & 0x4000:
        w.log('hit_sound', dmg, victim_is_player, sound_slot, flags, 1)
    w.take_damage(victim, dmg, attacker, flags)

    share = ZERO
    if attacker_is_player:
        rank = w.players[attacker.slot].rank(SKILL_STUN)
        chance = stun_chance(w, victim, rank)
        if w.seed.draw() % 100 < chance:
            stun_effect(w, victim)
        spell = attacker.spell('Retribution')
        if spell:
            share = retribution(w, spell, dmg)

    blocked_text = (w.pvp_a and attacker is not None and victim.flags & 0x40
                    and victim.state in (8, 0xB) and not flags & 0x20040
                    and _facing_front(victim, attacker))

    # the floating number
    if victim_is_player and not (w.pvp_a and attacker_is_player and attacker is not victim):
        return 1
    if not w.numbers_option and not w.network_mode:
        return 1
    if victim.flags & 8:
        return 1
    if flags & 0x200 and victim.cflags & 0x100:
        return 1
    if w.cutscene or blocked_text:
        return 1
    if flags & 0x800000:
        if w.frame & 0x1F:
            return 1
    elif flags & 0x1000000:
        return 1
    if w.pool(0x98):
        w.seed.draw()                   # GameObject_ctor
        w.log('text', number, crit, victim_is_player, colour, 0)
    if feq(share, ZERO):
        return 1
    number = ftoi(fadd(fmul(dmg, share), HALF))
    if w.pool(0x98):
        w.seed.draw()
        w.log('text', number, crit, victim_is_player, colour, 2)
    return 1


# =======================================================================================
# 7. Tables read from the executable
# =======================================================================================

class Exe:
    """Just enough of an ELF reader to fetch words, bytes and strings by address."""

    def __init__(self, path):
        with open(path, 'rb') as source:
            self.data = source.read()
        data = self.data
        if data[:4] != b'\x7fELF' or data[4] != 1 or data[5] != 1:
            raise ValueError('%s: not a 32-bit little-endian ELF' % path)
        phoff, = struct.unpack_from('<I', data, 28)
        phentsize, phnum = struct.unpack_from('<HH', data, 42)
        self.segments = []
        for index in range(phnum):
            kind, offset, vaddr, _p, filesz, _m = struct.unpack_from('<6I', data, phoff + index * phentsize)
            if kind == 1:
                self.segments.append((vaddr, offset, filesz))

    def _offset(self, addr):
        for vaddr, offset, size in self.segments:
            if vaddr <= addr < vaddr + size:
                return offset + addr - vaddr
        raise ValueError('address 0x%08x is not in the file' % addr)

    def u8(self, addr):
        return self.data[self._offset(addr)]

    def u32(self, addr):
        return struct.unpack_from('<I', self.data, self._offset(addr))[0]

    def s32(self, addr):
        return struct.unpack_from('<i', self.data, self._offset(addr))[0]

    def u64(self, addr):
        return struct.unpack_from('<Q', self.data, self._offset(addr))[0]

    def cstr(self, addr):
        start = self._offset(addr)
        return self.data[start:self.data.index(b'\0', start)].decode('latin1')


A_EXP_TABLE = 0x41B558              # g_expTable: 81 s32, index = level
A_CLASS_CHAIN = (0x1B6740, 0x1B694C)    # the class-constant chain in player_recalcStats
A_PASSIVE_LISTS = (0x4EBBE8, 0x4EBEC0, 0x4EC400, 0x4EC2B0, 0x4EC0B8, 0x4EC748, 0x4EC5C0)
A_FIGURINE_STATS = (0x5376F0, 0x5365E8, 0x536650, 0x5366B8)
A_FIGURINE_TIERS = (0x537700, 0x537708, 0x537710, 0x537718)
A_BOSS_NAMES = (0x52FD48, 0x52FD58, 0x52FD68, 0x52FD78, 0x52FD88, 0x52FD90, 0x52FDA0, 0x52FDB0,
                0x52FDC0, 0x52FDD0, 0x52FDE0, 0x52FDF0, 0x52FE00)
A_BOSS_GATE = 0x52FE10              # a 14th name; the pairs and the last two only matter when it differs
A_BOSS_PAIRS = ((0x52FE20, 0x52FE30), (0x52FE20, 0x52FE38), (0x52FE40, 0x52FE48))
A_BOSS_LAST = (0x52FE50, 0x52FE60)
A_NO_SCALE_NAME = 0x52FB68          # type name exempt from the player-count damage scaling
A_FIXED_LEVELS = (0x52FB70, 0x52FB80)   # level names exempt from the difficulty hit-point factor


class Tables:
    """Rules data that lives in the executable.  Build one with Tables.load(path), or fill
    the attributes yourself.

    exp_table        81 ints: a character leaves level L when its experience reaches [L]
    class_formulas   per class: (mana_int_offset, mana_per_int, mana_per_level,
                     hp_per_level, hp_per_stamina, hp_offset), float patterns;
                     class_default is the row for a class index outside 0-6
    passive_masks    per class: the masks of its 48 passive rows (0 = unused row)
    figurine_stats   four name fragments that pick the statistic a figurine raises
    figurine_tiers   four name fragments that pick the amount per figurine: 5, 10, 20, 25
                     (15 when none matches)
    boss_names, boss_gate, boss_pairs, boss_last    see boss_rank()
    no_scale_name, fixed_levels                     see monster_stats()"""

    def __init__(self):
        self.exp_table = [0] * 81
        self.class_formulas = [(ZERO,) * 6] * 7
        self.class_default = (ZERO,) * 6
        self.passive_masks = [[0] * 48 for _ in range(7)]
        self.figurine_stats = ('', '', '', '')
        self.figurine_tiers = ('', '', '', '')
        self.boss_names = ()
        self.boss_gate = ''
        self.boss_pairs = ()
        self.boss_last = ()
        self.no_scale_name = ''
        self.fixed_levels = ()

    @classmethod
    def load(cls, path):
        exe = path if isinstance(path, Exe) else Exe(path)
        t = cls()
        t.exp_table = [exe.s32(A_EXP_TABLE + 4 * i) for i in range(81)]
        t.class_formulas = [read_class_formula(exe, c) for c in range(7)]
        t.class_default = read_class_formula(exe, -1)
        t.passive_masks = [read_passive_masks(exe, addr) for addr in A_PASSIVE_LISTS]
        t.figurine_stats = tuple(exe.cstr(a) for a in A_FIGURINE_STATS)
        t.figurine_tiers = tuple(exe.cstr(a) for a in A_FIGURINE_TIERS)
        t.boss_names = tuple(exe.cstr(a) for a in A_BOSS_NAMES)
        t.boss_gate = exe.cstr(A_BOSS_GATE)
        t.boss_pairs = tuple((exe.cstr(a), exe.cstr(b)) for a, b in A_BOSS_PAIRS)
        t.boss_last = tuple(exe.cstr(a) for a in A_BOSS_LAST)
        t.no_scale_name = exe.cstr(A_NO_SCALE_NAME)
        t.fixed_levels = tuple(exe.cstr(a) for a in A_FIXED_LEVELS)
        return t


def read_class_formula(exe, cls):
    """Walk the class-test chain of player_recalcStats (0x1b6740-0x1b694c) for one class and
    return the six float immediates it leaves in $f23, $f24, $f25, $f22, $f20, $f21.  Only
    the instruction kinds that occur in the chain are understood; a class outside 0-6
    yields the defaults the chain starts with."""
    start, end = A_CLASS_CHAIN
    reg = [0] * 32
    freg = [0] * 32
    pc, npc = start, start + 4
    for _ in range(400):
        if pc == end:
            return tuple(freg[i] for i in (23, 24, 25, 22, 20, 21))
        word = exe.u32(pc)
        op, rs, rt, imm = word >> 26, (word >> 21) & 31, (word >> 16) & 31, word & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        target = npc + 4
        if word == 0:
            pass
        elif op == 0x23 and imm == 0x50:                # lw rt, 0x50(record): the class
            reg[rt] = cls & M32
        elif op == 0x0F:                                # lui
            reg[rt] = (imm << 16) & M32
        elif op == 0x0D:                                # ori
            reg[rt] = reg[rs] | imm
        elif op == 0x09:                                # addiu
            reg[rt] = (reg[rs] + simm) & M32
        elif op == 0x11 and rs == 4:                    # mtc1 rt, fs
            freg[(word >> 11) & 31] = reg[rt]
        elif op in (0x04, 0x05):                        # beq / bne
            if (reg[rs] == reg[rt]) == (op == 0x04):
                target = pc + 4 + (simm << 2)
        else:
            raise ValueError('unexpected instruction 0x%08x at 0x%08x in the class chain' % (word, pc))
        reg[0] = 0
        pc, npc = npc, target
    raise ValueError('the class chain did not end')


def read_passive_masks(exe, addr):
    """One class's passive source list: rows of 0x38 bytes, name first, ended by the row
    named END; the mask is the u64 at +0x28.  classSkills_init 0x1ac7a8 copies the rows in
    order into the run-time table, so the row index is the index of the level byte."""
    masks = []
    while len(masks) < 48 and exe.cstr(addr) != 'END':
        masks.append(exe.u64(addr + 0x28))
        addr += 0x38
    return masks + [0] * (48 - len(masks))


def passive_level(tables, rec, slot, mask):
    """player_getPassiveLevel 0x1bed48: the level byte of the first row whose mask is `mask`
    (0 when negative, when there is no such row, or when the slot is above 4)."""
    if not 0 <= slot <= 4:
        return 0
    for index, row_mask in enumerate(tables.passive_masks[rec.cls]):
        if row_mask == mask:
            level = s8(rec.passives[index])
            return level if level >= 0 else 0
    return 0


# =======================================================================================
# 8. Monsters
# =======================================================================================

def boss_rank(tables, is_creature, type_name, name_prop, cflags):
    """creature_bossRank 0x10d940.  2 for a named boss, else bit 0 of the creature flags
    (the MiniBoss property), 0 for a non-creature.  Names compare without regard to case.
    type_name is the level record's class string (None when absent), name_prop the object's
    `name` property ('' when absent)."""
    if not is_creature:
        return 0
    if type_name is None:
        return cflags & 1
    name = type_name.lower()
    if name in [n.lower() for n in tables.boss_names]:
        return 2
    if name == tables.boss_gate.lower():
        return 2
    for boss, wanted in tables.boss_pairs:
        if name == boss.lower() and (name_prop or '').lower() == wanted.lower():
            return 2
    if name == tables.boss_last[0].lower() or name == tables.boss_last[1].lower():
        return 2
    return cflags & 1


def level_scale(tables, level_byte, difficulty, pvp_b, level_name):
    """The monster level of a level, g_levelMonsterLevel 0x4f714c, as game_loadLevel sets it
    (0x1e5b70-0x1e5c94).  level_byte is the signed byte at +4 of the level's table row.
    Difficulty 1: byte + 2; difficulties 2-5: (byte + 2) x 0.75 + 34, 61, 88, 115.  PvP
    mode B makes it 3.0 - but the difficulty formula is applied after that store and from
    the unchanged byte, so the 3.0 survives only on difficulty 1.  Two level names (compared
    exactly, with case) then force 1.0 and 2.0."""
    base = itof(s8(level_byte) + 2)
    value = THREE if pvp_b else base
    if difficulty in (2, 3, 4, 5):
        value = fadd(fmul(base, 0x3F400000), (0x42080000, 0x42740000, 0x42B00000, 0x42E60000)[difficulty - 2])
    if level_name == tables.fixed_levels[0]:
        value = ONE
    elif level_name == tables.fixed_levels[1]:
        value = TWO
    return value


def monster_stats(tables, w, pct, rank, type_name, roll_hp, own_draw=0, dead=False):
    """Creature_setStats 0x10a620.

    pct        the five factors from monsters.bal (hp, armour, damage, attack, experience),
               float patterns (100 % = 1.0)
    rank       boss_rank() of the creature
    type_name  its type name or None (one name is exempt from the damage scaling)
    roll_hp    the function's last argument: compute hit points
    own_draw   the value GameObject_rand returns for the hit-point roll (the creature's own
               generator, not the shared seed)
    dead       the object has the Dead property
    Uses w.monster_level, w.num_players, w.medal_mission, w.difficulty, w.level_name.

    Returns a dict: hp and max_hp (float patterns; None = left as they were), armor,
    dmg_low, dmg_high, attack (s16) and exp_value (float pattern)."""
    hp, armor, damage, attack, exp = pct
    level = w.monster_level
    damage = fmul(damage, 0x3FC51EB8)                       # 1.54
    if rank == 1:
        hp = fmul(hp, 0x41199999)                           # 9.6
        damage = fmul(damage, 0x3FA66666)                   # 1.3
        attack = fmul(attack, THREE)
        exp = fmul(exp, 0x40800000)                         # 4
    n = s32(w.num_players)
    if n >= 2 and w.medal_mission == 0:
        extra = itof(n - 1)
        exp = fmul(exp, fadd(extra, ONE))
        hp = fmul(hp, fadd(fmul(extra, 0x3F199999), ONE))   # 1 + 0.6 (n - 1)
        if rank != 2 and type_name is not None and type_name.lower() != tables.no_scale_name.lower():
            damage = fmul(damage, fadd(fmul(extra, 0x3E199999), ONE))   # 1 + 0.15 (n - 1)
    out = {'hp': None, 'max_hp': None}
    if roll_hp:
        power = powf(fmul(hp, level), 0x3F599999)           # ** 0.85
        factor = dbl_add(dbl_from_int((own_draw & M32) % 5), Fraction(31, 2))
        value = dbl_to_single(dbl_mul(factor, dbl_from_single(power)))
        if w.level_name.lower() not in [name.lower() for name in tables.fixed_levels]:
            if w.difficulty == 2:
                value = fmul(value, 0x3FC00000)
            elif w.difficulty == 3:
                value = fadd(value, value)
            elif w.difficulty == 4:
                value = fmul(value, 0x40200000)
            elif w.difficulty == 5:
                value = fmul(value, THREE)
        out['hp'] = out['max_hp'] = value
    out['armor'] = s16(ftoi(fmul(fmul(armor, 0x41600000), level)))
    out['dmg_low'] = s16(ftoi(fmul(damage, powf(level, ONE))))
    high = s16(ftoi(fmul(fadd(damage, damage), powf(level, ONE))))
    if high < out['dmg_low'] + 1:
        high = s16(out['dmg_low'] + 1)
    out['dmg_high'] = high
    out['attack'] = s16(ftoi(fmul(fmul(level, 0x41600000), attack)))
    out['exp_value'] = itof(ftoi(fmul(powf(fmul(exp, level), 0x3FA9374B), 0x41000000)))
    if dead:                            # also when the hit points were not rolled
        out['hp'] = ZERO
    return out


# =======================================================================================
# 9. Experience
# =======================================================================================

def exp_cap(tables, level):
    """The most experience one kill can give at `level`: the width of the level
    (table[level + 1] - table[level]) below level 80, table[level] from 80 on."""
    level = s8(level)
    if level < 80:
        return s32(tables.exp_table[level + 1] - tables.exp_table[level])
    return tables.exp_table[level]


def give_exp(tables, w, slot, amount, on_level_up=None):
    """player_giveExp 0x1d3150: add experience (never above table[80] - 1) and take every
    level it pays for.  Per level: skill points +1 below level 6, +2 below 16, +3 below 26,
    +4 below 36, else +5; stat points +3; level +1; recalc_stats; hit points and mana
    refilled when alive.  Returns the number of levels gained."""
    rec = w.players[slot]
    rec.exp = s32(rec.exp + amount)
    ceiling = s32(tables.exp_table[80] - 1)
    if ceiling < rec.exp:
        rec.exp = ceiling
    gained = 0
    while tables.exp_table[s8(rec.level59)] <= rec.exp:
        level = s8(rec.level59)
        rec.skill_points += 1 if level < 6 else 2 if level < 16 else 3 if level < 26 else 4 if level < 36 else 5
        rec.stat_points = s8(rec.stat_points + 3)
        rec.level59 = s8(level + 1)
        recalc_stats(tables, w)
        if flt(ZERO, rec.hp):
            rec.hp = rec.max_hp
            rec.mana = rec.max_mana
        w.log('level_up', slot, rec.level59)
        if on_level_up:
            on_level_up(slot)
        gained += 1
    return gained


def kill_experience(tables, w, creature, killer_slot, orb_draw=0):
    """The experience part of Creature_processDamage 0x110d30 (0x111e3c-0x112248).

    creature     Obj: exp_value (+0xd8), max_hp (+0x22c) are read
    killer_slot  slot of the player behind the last-attacker handle, -1 when no player
    orb_draw     the value the creature's own generator returns for the kill-orb roll
                 (made only when a player made the kill)

    Returns the list of (slot, amount) handed to give_exp, in order."""
    n = s32(w.num_players)
    total = 0
    for slot in range(max(n, 0)):
        total += s8(w.players[slot].level59)
    raw = ftoi(powf(fdiv(creature.exp_value, itof(total)), 0x3FB33333))     # ** 1.4
    if killer_slot != -1:
        rank = w.players[killer_slot].rank(0x3B)
        chance = fmul(itof(w.stat(0x3B, 0, w.adjust(0x3B, rank, 1))), K_001)
        low = c_rem(s32(orb_draw), 0x10000)
        if flt(itof(low), fmul(chance, K_65536)):
            if w.pool(0xB8):
                w.seed.draw()               # OniBall constructor
                w.log('orb', creature.tag)
    xp = ftoi(fmul(itof(raw), 0x3F400000))                                  # x 0.75
    awards = []

    def mana_bonus(rec):
        rec.mana = fadd(rec.mana, fmul(creature.max_hp, K_1_30))
        if flt(rec.max_mana, rec.mana):
            rec.mana = rec.max_mana

    if n < 2:
        for slot in range(max(n, 0)):
            rec = w.players[slot]
            if not flt(ZERO, rec.hp):
                continue
            cap = exp_cap(tables, rec.level59)
            if cap < xp:
                xp = cap
            awards.append((slot, xp))
            give_exp(tables, w, slot, xp)
            if rec.cls == 0:
                mana_bonus(rec)
        return awards
    whole = itof(xp)
    for slot in range(n):
        rec = w.players[slot]
        share = HALF if killer_slot == -1 else 0x3F199999 if killer_slot == slot else 0x3ECCCCCC
        amount = ftoi(fmul(whole, share))
        if fle(rec.hp, ZERO):
            amount = ftoi(fmul(itof(amount), HALF))
        cap = exp_cap(tables, rec.level59)
        if cap < amount:
            amount = cap
        awards.append((slot, amount))
        give_exp(tables, w, slot, amount)
        if rec.cls == 0 and killer_slot == slot:
            mana_bonus(rec)
    return awards


# =======================================================================================
# 10. Player statistics
# =======================================================================================

def item_armor_value(item):
    """item_getArmorValue 0x103ec8: definition armour, plus modifier 0x0d percent of it."""
    base = s16(item.defn.armor)
    percent = item.mod(0x0D)
    if percent != 0:
        base += ftoi(fmul(itof(base), fmul(itof(percent), K_001)))
    return base


def item_attack_rating(item):
    """item_getModifiedField1a 0x103f88: definition attack rating scaled by modifier 0x23."""
    base = itof(s16(item.defn.attack))
    percent = item.mod(0x23)
    if percent != 0:
        base = fadd(fmul(fmul(itof(percent), K_001), base), base)
    return ftoi(base)


def item_damage_range(item, with_elements):
    """item_getDamageRange 0x104100 -> (min, max).  The definition's range scaled by
    modifier 0x23 percent; with_elements adds the ranges of modifiers 0x15, 0x16, 0x18,
    0x17 and 0x26; each end is rounded by adding 0.5 and truncating."""
    high = itof(s16(item.defn.dmg_max))
    low = itof(s16(item.defn.dmg_min))
    percent = item.mod(0x23)
    if percent != 0:
        factor = fadd(fmul(itof(percent), K_001), ONE)
        high = fmul(high, factor)
        low = fmul(low, factor)
    if with_elements:
        for code in (0x15, 0x16, 0x18, 0x17, 0x26):
            if item.mod(code) != 0:
                low = fadd(low, itof(item.mod(code, 1)))
                high = fadd(high, itof(item.mod(code, 2)))
    return ftoi(fadd(fmul(low, ONE), HALF)), ftoi(fadd(fmul(high, ONE), HALF))


def recalc_armor(tables, w, slot):
    """player_recalcArmor 0x1b5790: returns the armour value; rewrites the object's five
    resistances; adds figurine bonuses to the effective statistics; adds modifiers 5 and 6
    to the record's maximum hit points and mana (recalc_stats overwrites both right after,
    so those two modifiers have no lasting effect through this path)."""
    rec = w.players[slot]
    obj = rec.obj
    if obj is None:
        return 0
    obj.res = [ZERO] * 5
    armor = 0
    weapon = rec.weapon_sets[s8(rec.active_set)]
    for item in rec.bag2[:64]:
        if item is None or item.defn is None or not item.defn.flags & (1 << 45):
            continue
        name = item.defn.name
        stat = next((i for i, part in enumerate(tables.figurine_stats) if part in name), -1)
        if stat < 0:
            continue
        tier = next((i for i, part in enumerate(tables.figurine_tiers) if part in name), -1)
        rec.eff[stat] = s32(rec.eff[stat] + s16(item.count) * (5, 10, 20, 25, 15)[tier])
    for index in range(17):
        if weapon is not None and index == 3 and s8(weapon.defn.subtype) == 4:
            continue                    # the shield slot does not count while a bow is out
        item = rec.equip[index]
        if item is None:
            continue
        if s8(item.defn.category) == 1:
            armor += item_armor_value(item)
        for code in range(5):
            obj.res[code] = fadd(obj.res[code], fmul(itof(item.mod(code)), K_001))
        every = fmul(itof(item.mod(0x2A)), K_001)
        for code in range(5):
            obj.res[code] = fadd(obj.res[code], every)
        if s8(item.defn.category) != 1:
            armor += item.mod(0x0D)
        rec.max_hp = fadd(rec.max_hp, itof(item.mod(5)))
        rec.max_mana = fadd(rec.max_mana, itof(item.mod(6)))
    bonus = fmul(itof(w.stat(0x3F, 0, w.adjust(0x3F, rec.rank(0x3F), 1))), K_001)
    for code in range(5):
        obj.res[code] = fadd(obj.res[code], bonus)
        if flt(ONE, obj.res[code]):
            obj.res[code] = ONE
    dex = s32(rec.eff[2])
    return s32(armor + ((dex + (1 if dex < 0 else 0)) >> 1))


def recalc_stats(tables, w):
    """player_recalcStats 0x1b6458, for every slot below w.num_players: effective statistics
    (base + modifiers 7-10 of the 17 equipped items), stagger resistance (modifier 0x1e),
    the four bonus bytes on the object, armour and resistances (recalc_armor), load limit,
    maximum mana and hit points from the class constants, and the clamps of mana and hit
    points to the new maxima.  A slot without an object only gets its effective statistics
    reset to the base ones."""
    for slot in range(max(s32(w.num_players), 0)):
        rec = w.players[slot]
        rec.eff = [s32(v) for v in rec.base]
        obj = rec.obj
        if obj is None:
            continue
        rec.stagger = ZERO
        for item in rec.equip:
            if item is None:
                continue
            for stat, code in enumerate((7, 8, 9, 10)):
                rec.eff[stat] = s32(rec.eff[stat] + item.mod(code))
            rec.stagger = fadd(rec.stagger, fmul(itof(item.mod(0x1E)), K_001))
        for stat in range(4):
            value = (rec.eff[stat] - (0x1E if stat in (0, 2) else 5)) & 0xFF
            obj.bonus[stat] = 0 if s8(value) < 0 else value
        mana_int_offset, mana_per_int, mana_per_level, hp_per_level, hp_per_stamina, hp_offset = \
            tables.class_formulas[rec.cls] if 0 <= rec.cls < len(tables.class_formulas) else tables.class_default
        obj.armor = s16(recalc_armor(tables, w, slot))
        level = itof(s8(rec.level59))
        rec.load_limit = itof(rec.eff[0] + 0x7D)
        rec.max_mana = fadd(fmul(fsub(itof(rec.eff[1]), mana_int_offset), mana_per_int),
                            fmul(level, mana_per_level))
        rec.max_hp = fsub(fadd(fmul(level, hp_per_level), fmul(itof(rec.eff[3]), hp_per_stamina)),
                          hp_offset)
        rec.load_limit = fadd(rec.load_limit, fmul(itof(passive_level(tables, rec, obj.slot, 0x40)),
                                                   0x41700000))
        if w.load_cheat:
            rec.load_limit = fadd(rec.load_limit, 0x459C4000)
        if flt(0x461C3C00, rec.load_limit):
            rec.load_limit = 0x461C3C00
        if flt(rec.max_mana, rec.mana):
            rec.mana = rec.max_mana
        if flt(rec.max_hp, rec.hp):
            rec.hp = rec.max_hp


def recalc_damage(tables, w, player, weapon, with_elements):
    """Player_recalcDamage 0x1b7158(player object, weapon item or None, flag): writes the
    record's attack rating (+0xcc) and weapon damage range (+0xd0, +0xd4) and returns them
    as (attack, min, max)."""
    rec = w.players[player.slot]
    strength, dexterity = s32(rec.eff[0]), s32(rec.eff[2])
    by_strength = (strength + (3 if strength < 0 else 0)) >> 2
    by_dexterity = (dexterity + (3 if dexterity < 0 else 0)) >> 2
    attack = s8(rec.level58) * 20
    if weapon is None:
        low, high, attack = by_strength + 1, by_strength + 2, attack + by_strength
    else:
        defn = weapon.defn
        low, high = item_damage_range(weapon, with_elements)
        attack += item_attack_rating(weapon)
        bonus = by_dexterity if s8(defn.subtype) in (4, 6) else by_strength
        low, high, attack = low + bonus, high + bonus, attack + bonus
        factor_1 = factor_8 = ONE
        if rec.rank(0x3C) != 0:
            factor_1 = fadd(fmul(itof(rec.rank(0x3C)), 0x3D4CCCCC), 0x3F933333)
        if rec.rank(0x3D) != 0:
            factor_8 = fadd(fmul(itof(rec.rank(0x3D)), 0x3D4CCCCC), 0x3F933333)
        if s8(defn.subtype) == 4:       # bows: skill 0x30
            f = fmul(itof(w.stat(0x30, 0, w.adjust(0x30, rec.rank(0x30), 0x14))), K_001)
            low = s32(low + round_half_away(fmul(itof(low), f)))
            high = s32(high + round_half_away(fmul(itof(high), f)))
        if s8(defn.subtype) == 6:       # thrown: skill 0x4f; the maximum grows by the NEW minimum's share
            f = fmul(itof(w.stat(0x4F, 0, w.adjust(0x4F, rec.rank(0x4F), 2))), K_001)
            low = s32(low + round_half_away(fmul(itof(low), f)))
            high = s32(high + round_half_away(fmul(itof(low), f)))
        if rec.second_weapon is not None and s8(defn.subtype) != 6 and defn.dmg_type in (1, 8):
            dual = fmul(fadd(fmul(itof(passive_level(tables, rec, player.slot, 0x40000)), 0x40200000),
                             0x42C80000), K_001)
            if defn.dmg_type == 1:
                factor_1 = fmul(factor_1, dual)
            else:
                factor_8 = fmul(factor_8, dual)
        if defn.dmg_type in (1, 8):
            f = factor_1 if defn.dmg_type == 1 else factor_8
            low = ftoi(fadd(fmul(itof(low), f), HALF))
            high = ftoi(fadd(fmul(itof(high), f), HALF))
        if rec.cls == 4:
            wanted = (s8(defn.subtype) == 0 and not weapon.flags & (1 << 36)
                      and defn.dmg_type in (8, 4)) or bool(weapon.flags & (1 << 43))
            if wanted:
                f = fmul(itof(w.stat(0x5C, 0, w.adjust(0x5C, rec.rank(0x5C), 1))), K_001)
                low = round_half_away(fmul(itof(low), f))
                high = round_half_away(fmul(itof(high), f))
    # AncestralCall: the best factor among the alive players whose spell reaches this one
    best = ZERO
    for slot in w.alive:
        spell = w.players[slot].obj.spell('AncestralCall')
        if spell is None:
            continue
        level = s8(spell.level)
        reach = w.stat(spell.skill, 3, level)
        factor = fmul(itof(w.stat(spell.skill, 0, level)), K_001)
        owner = spell.owner
        if player is not owner:
            if w.pvp_a and not w.enemy_fn(owner, player):
                continue
            dx = fsub(player.pos[0], owner.pos[0])
            dy = fsub(player.pos[1], owner.pos[1])
            if flt(itof(s32(reach * 12 * reach * 12)), fadd(fmul(dx, dx), fmul(dy, dy))):
                continue
        if flt(best, factor):
            best = factor
    if not feq(best, ZERO):
        low = round_half_away(fmul(itof(low), best))
        high = round_half_away(fmul(itof(high), best))
        attack = round_half_away(fmul(itof(attack), best))
    factor = ONE
    if rec.cls == 5 and player.state == 1:
        if s32(w.frame - player.attack_chain) < 0x1B:
            rank = rec.rank(0x47)
            if rank > 0:
                level = w.adjust(0x47, rank, 0x14)
                rage = ONE
                if fle(fdiv(rec.hp, rec.max_hp), HALF):
                    t = fmul(itof(s32(w.frame - player.attack_start)), 0x3C888888)
                    if flt(ONE, t):
                        t = ONE
                    rage = fadd(fmul(fmul(itof(w.stat(0x47, 1, level)), K_001), t), ONE)
                if flt(factor, rage):
                    factor = rage
        spell = player.spell('BloodLust')
        if spell is not None:
            lust = ONE
            if spell.f2c != 0:
                lust = fadd(fmul(itof(w.stat(spell.skill, 1, s8(spell.level))), K_001), ONE)
            if flt(factor, lust):
                factor = lust
    if rec.cls == 6 and player.state == 1:
        spell = player.spell('GiantGrowth')
        if spell is not None and flt(factor, spell.owner.field_dc):
            factor = spell.owner.field_dc
    low = ftoi(fmul(itof(low), factor))
    high = ftoi(fmul(itof(high), factor))
    attack = ftoi(fmul(itof(attack), factor))
    if player.counter2 != 0:
        low, high, attack = (ftoi(fmul(itof(v), 0x3FC00000)) for v in (low, high, attack))
    if player.counter4 != 0:
        low, high, attack = (ftoi(fmul(itof(v), 0x3F999999)) for v in (low, high, attack))
    rec.attack, rec.dmg_min, rec.dmg_max = attack, low, high
    return attack, low, high


def level_for_exp(tables, exp):
    """The level a new character reaches with `exp` experience (levels are 1 to 80)."""
    level = 1
    while level < 80 and tables.exp_table[level] <= exp:
        level += 1
    return level


# =======================================================================================
# 11. Command line: worked examples
# =======================================================================================

def _examples(path):
    tables = Tables.load(path)
    w = World(seed=0x1234)
    w.monster_level = f32(12.0)
    w.num_players = 1
    stats = monster_stats(tables, w, (ONE,) * 5, 0, 'example', True, own_draw=3)
    print('monster, all factors 1.0, level scale 12, one player, roll 3:')
    print('  ', {k: (to_float(v) if k in ('hp', 'max_hp', 'exp_value') else v) for k, v in stats.items()})
    victim = Obj(tag='monster', flags=0x20, armor=stats['armor'], hp=stats['hp'])
    attacker = Obj(tag='hero', flags=0x60)
    w.players = [PlayerRec(obj=attacker)]
    ret = damage_apply(w, victim, attacker, f32(20.0), f32(30.0), 400, 1)
    print('hit for 20-30 with attack 400: returned %d, draws %s' % (ret, w.seed.draws))
    for event in w.events:
        print('  ', event)


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        sys.exit('usage: ref_combat.py path/to/SLUS_209.73   (prints worked examples)')
    _examples(sys.argv[1])
