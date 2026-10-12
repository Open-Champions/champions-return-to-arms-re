"""softf.py - single-precision arithmetic in exact integer arithmetic, as a reference.

Two things are written down here, both on raw 32-bit patterns:

  IEEE 754 single precision with rounding toward zero (rz_*), with the two treatments of
  denormals a host offers: kept (gradual underflow), or "flush to zero" as an ARM64 CPU
  does it with FPCR.FZ set - a denormal operand counts as zero and a result that would be
  denormal becomes zero.  The Play! emulator runs the game's code with rounding toward
  zero and FZ set (PS2VM.cpp, CPS2VM::EmuThread).

  The 'host' model of tools/recomp/rt/fpu.h (host_*): what the translated game's FPU
  instructions compute in the runtime build - operands clamped to +/-FLT_MAX, then the
  IEEE operation; division and reciprocal square root by a zero exponent give +/-FLT_MAX.

No floating point is used anywhere in this file.  NaN operands exist only where the
models let them through (conversions, the vector unit); a NaN result is 0x7fc00000, the
ARM64 default NaN.
"""
import math

M32 = 0xFFFFFFFF
SIGN = 0x80000000
FLT_MAX = 0x7F7FFFFF
NAN = 0x7FC00000


def is_nan(raw):
    return (raw & 0x7F800000) == 0x7F800000 and (raw & 0x7FFFFF) != 0


def is_inf(raw):
    return (raw & 0x7FFFFFFF) == 0x7F800000


def flush(raw):
    """FZ: a denormal operand is a zero of the same sign."""
    return raw & SIGN if (raw & 0x7F800000) == 0 else raw


def unpack(raw):
    """(sign, N, e) of a finite pattern: value = N * 2**e."""
    exp = (raw >> 23) & 0xFF
    man = raw & 0x7FFFFF
    if exp == 0:
        return raw >> 31, man, -149
    return raw >> 31, man | 0x800000, exp - 150


def pack_rz(sign, n, e, fz):
    """The pattern of (-1)**sign * n * 2**e (n >= 0 exact, or exact up to bits that
    truncation discards), rounded toward zero."""
    if n == 0:
        return sign << 31
    length = n.bit_length()
    top = length - 1 + e                    # the value lies in [2**top, 2**(top+1))
    if top > 127:
        return (sign << 31) | FLT_MAX       # overflow, rounding toward zero: the largest finite
    if top >= -126:
        shift = length - 24
        m = n >> shift if shift > 0 else n << -shift
        return (sign << 31) | ((top + 127) << 23) | (m & 0x7FFFFF)
    if fz:
        return sign << 31
    shift = e + 149
    m = n << shift if shift >= 0 else n >> -shift
    return (sign << 31) | m


def rz_add(a, b, fz):
    if fz:
        a, b = flush(a), flush(b)
    sa, na, ea = unpack(a)
    sb, nb, eb = unpack(b)
    e = min(ea, eb)
    total = (-na if sa else na) * (1 << (ea - e)) + (-nb if sb else nb) * (1 << (eb - e))
    if total == 0:
        return (sa & sb) << 31 if (na == 0 and nb == 0) else 0
    return pack_rz(1 if total < 0 else 0, abs(total), e, fz)


def rz_sub(a, b, fz):
    return rz_add(a, b ^ SIGN, fz)


def rz_mul(a, b, fz):
    if fz:
        a, b = flush(a), flush(b)
    sa, na, ea = unpack(a)
    sb, nb, eb = unpack(b)
    return pack_rz(sa ^ sb, na * nb, ea + eb, fz)


def rz_div(a, b, fz):
    """b must not be zero."""
    if fz:
        a, b = flush(a), flush(b)
    sa, na, ea = unpack(a)
    sb, nb, eb = unpack(b)
    if na == 0:
        return (sa ^ sb) << 31
    k = 64
    return pack_rz(sa ^ sb, (na << k) // nb, ea - eb - k, fz)


def rz_sqrt(a, fz):
    """a must not be negative (minus zero gives minus zero)."""
    if fz:
        a = flush(a)
    sa, na, ea = unpack(a)
    if na == 0:
        return sa << 31
    k = 64
    if (ea - k) & 1:
        k += 1
    return pack_rz(0, math.isqrt(na << k), (ea - k) // 2, fz)


def to_int(raw):
    """FCVTZS: truncate, saturate, NaN gives 0."""
    if is_nan(raw):
        return 0
    sign, n, e = unpack(raw) if not is_inf(raw) else (raw >> 31, 1, 200)
    mag = n << e if e >= 0 else n >> -e
    if sign:
        return 0x80000000 if mag >= 0x80000000 else (-mag) & M32
    return 0x7FFFFFFF if mag >= 0x80000000 else mag


def from_int(word):
    value = word - (1 << 32) if word & SIGN else word
    return pack_rz(1 if value < 0 else 0, abs(value), 0, False)


def order(raw):
    """A key that orders finite patterns by value (+0 and -0 equal)."""
    sign, n, e = unpack(raw)
    value = n << (e + 149)
    return -value if sign else value


# ---- the 'host' model of fpu.h --------------------------------------------------------------

def clamp(a):
    if a < SIGN and a > FLT_MAX:
        return FLT_MAX
    if a > 0xFF7FFFFF:
        return 0xFF7FFFFF
    return a


def host_add(a, b, fz):
    return rz_add(clamp(a), clamp(b), fz)


def host_sub(a, b, fz):
    return rz_sub(clamp(a), clamp(b), fz)


def host_mul(a, b, fz):
    return rz_mul(clamp(a), clamp(b), fz)


def host_div(a, b, fz):
    if (b & 0x7F800000) == 0:
        return ((a ^ b) & SIGN) | FLT_MAX
    return rz_div(clamp(a), clamp(b), fz)


def host_sqrt(a, fz):
    return rz_sqrt(clamp(a) & 0x7FFFFFFF, fz)


def host_rsqrt(a, b, fz):
    if (b & 0x7F800000) == 0:
        return ((a ^ b) & SIGN) | FLT_MAX
    if b & SIGN:
        return NAN
    root = rz_sqrt(clamp(b), fz)
    return rz_mul(clamp(a), rz_div(0x3F800000, root, fz), fz)


def host_to_int(a):
    return to_int(a)


def host_from_int(word):
    return from_int(word)


def host_max(a, b, fz):
    """ARM64 FMAXNM on the clamped operands: of +0 and -0 the maximum is +0."""
    x, y = clamp(a), clamp(b)
    if fz:
        x, y = flush(x), flush(y)
    kx, ky = order(x), order(y)
    if kx != ky:
        return x if kx > ky else y
    return x & y


def host_min(a, b, fz):
    x, y = clamp(a), clamp(b)
    if fz:
        x, y = flush(x), flush(y)
    kx, ky = order(x), order(y)
    if kx != ky:
        return x if kx < ky else y
    return x | y


def host_cmp(a, b, fz):
    x, y = clamp(a), clamp(b)
    if fz:
        x, y = flush(x), flush(y)
    kx, ky = order(x), order(y)
    return (kx > ky) - (kx < ky)
