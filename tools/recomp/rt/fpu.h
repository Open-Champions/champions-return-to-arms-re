// fpu.h - single-precision arithmetic of the R5900 FPU on raw 32-bit patterns.
//
// Two models, chosen at compile time:
//
//   -DFPU_PS2   the 'ps2' model of tools/ee_emu.py, in integer arithmetic: no NaN,
//               infinity or denormal; exponent field 255 is an ordinary number, 0 is zero;
//               overflow gives +/-0x7fffffff, underflow zero; add/subtract align the
//               smaller operand keeping six extra bits; multiply, divide and square root
//               truncate the exact result.  This is what the differential test compares
//               against the interpreter, bit for bit.
//
//   (default)   'host': the arithmetic the Play! emulator performs on an ARM64 host, which
//               is what the headless rig (tools/rig) runs the original game with: operands
//               clamped to +/-FLT_MAX, then the host's IEEE operation with the rounding
//               mode set to toward-zero by the runtime; divide by a zero-exponent divisor
//               gives +/-FLT_MAX.  Fast, and the model to use when comparing with the rig.
//
// The FPU status flags are not kept: the game has no instruction that reads them (no
// CFC1 in the executable); only the compare bit (FCR31 bit 23) is.
#pragma once

#define FCR31_C 0x00800000u

static inline void fp_setc(Ctx* c, bool cond) {
    c->fcr31 = cond ? (c->fcr31 | FCR31_C) : (c->fcr31 & ~FCR31_C);
}

// CVT.W.S: truncate toward zero, saturate (same in both models for ordinary numbers)
static inline u32 fp_to_int_ps2(u32 a) {
    u32 exp = (a >> 23) & 0xFF;
    if (exp == 0) return 0;
    u32 sign = a >> 31, man = (a & 0x7FFFFF) | 0x800000;
    if (exp >= 158) return sign ? 0x80000000u : 0x7FFFFFFFu;
    int shift = (int)exp - 150;
    u32 mag = shift >= 0 ? man << shift : (shift <= -32 ? 0 : man >> -shift);
    return sign ? (u32)(0 - mag) : mag;
}

#ifdef FPU_PS2

#define FP_MAXRAW 0x7FFFFFFFu

static inline int fp_bitlen(u64 v) { return v ? 64 - __builtin_clzll(v) : 0; }

// raw single for (-1)^sign * mag * 2^e2, truncated; mag fits in 127 bits
static inline u32 fp_pack(u32 sign, unsigned __int128 mag, int e2) {
    if (mag == 0) return sign << 31;
    u64 top = (u64)(mag >> 64);
    int len = top ? 64 + fp_bitlen(top) : fp_bitlen((u64)mag);
    int shift = len - 24;
    u32 m = shift > 0 ? (u32)(mag >> shift) : (u32)((u64)mag << -shift);
    int exp = e2 + shift + 150;
    if (exp > 255) return (sign << 31) | FP_MAXRAW;
    if (exp < 1) return sign << 31;
    return (sign << 31) | ((u32)exp << 23) | (m & 0x7FFFFF);
}

static inline u32 fp_add(u32 a, u32 b) {
    u32 sa = a >> 31, ea = (a >> 23) & 0xFF, sb = b >> 31, eb = (b >> 23) & 0xFF;
    u32 ma = ea ? ((a & 0x7FFFFF) | 0x800000) : 0, mb = eb ? ((b & 0x7FFFFF) | 0x800000) : 0;
    if (ma == 0 && mb == 0) return (sa & sb) << 31;
    if (ma == 0) return b;
    if (mb == 0) return a;
    if (ea < eb) {
        u32 t;
        t = a; a = b; b = t;  t = sa; sa = sb; sb = t;
        t = ma; ma = mb; mb = t;  t = ea; ea = eb; eb = t;
    }
    u32 diff = ea - eb;
    if (diff >= 25) return a;
    s64 big = sa ? -(s64)ma : (s64)ma, small = sb ? -(s64)mb : (s64)mb;
    s64 man = big * 64 + ((small * 64) >> diff);        // the shift floors
    if (man == 0) return 0;
    u64 mag = man < 0 ? (u64)(-man) : (u64)man;
    int exp = (int)ea - 6;
    int shift = fp_bitlen(mag) - 24;
    if (shift > 0) mag >>= shift; else mag <<= -shift;
    exp += shift;
    u32 sign = man < 0 ? 1u : 0u;
    if (exp > 255) return (sign << 31) | FP_MAXRAW;
    if (exp < 1) return sign << 31;
    return (sign << 31) | ((u32)exp << 23) | ((u32)mag & 0x7FFFFF);
}
static inline u32 fp_sub(u32 a, u32 b) { return fp_add(a, b ^ 0x80000000u); }
static inline u32 fp_mul(u32 a, u32 b) {
    u32 ea = (a >> 23) & 0xFF, eb = (b >> 23) & 0xFF, sign = (a ^ b) >> 31;
    if (ea == 0 || eb == 0) return sign << 31;
    u64 product = (u64)((a & 0x7FFFFF) | 0x800000) * (u64)((b & 0x7FFFFF) | 0x800000);
    return fp_pack(sign, product, (int)ea + (int)eb - 300);
}
static inline u32 fp_div(u32 a, u32 b) {
    u32 ea = (a >> 23) & 0xFF, eb = (b >> 23) & 0xFF, sign = (a ^ b) >> 31;
    if (eb == 0) return (sign << 31) | FP_MAXRAW;
    if (ea == 0) return sign << 31;
    u64 ma = (a & 0x7FFFFF) | 0x800000, mb = (b & 0x7FFFFF) | 0x800000;
    u64 num = ma << 40;
    u64 q = num / mb;
    q = (q << 1) | (num % mb ? 1 : 0);                  // sticky bit
    return fp_pack(sign, q, (int)ea - (int)eb - 41);
}
static inline u32 fp_sqrt(u32 a) {
    u32 ea = (a >> 23) & 0xFF;
    if (ea == 0) return a & 0x80000000u;
    u64 ma = (a & 0x7FFFFF) | 0x800000;
    int e = (int)ea - 150;
    if (e & 1) { ma <<= 1; e -= 1; }
    unsigned __int128 wide = (unsigned __int128)ma << 48;
    // integer square root of a value below 2^73
    unsigned __int128 root = 0, bit = (unsigned __int128)1 << 72, rem = wide;
    while (bit > rem) bit >>= 2;
    while (bit != 0) {
        if (rem >= root + bit) { rem -= root + bit; root = (root >> 1) + bit; }
        else root >>= 1;
        bit >>= 2;
    }
    u64 r = (u64)root;
    r = (r << 1) | (rem != 0 ? 1 : 0);                  // sticky bit
    return fp_pack(0, r, e / 2 - 25);
}
static inline u32 fp_rsqrt(u32 a, u32 b) { return fp_div(a, fp_sqrt(b)); }
static inline u32 fp_to_int(u32 a) { return fp_to_int_ps2(a); }
static inline u32 fp_from_int(u32 w) {
    s32 v = (s32)w;
    if (v == 0) return 0;
    if (v < 0) return fp_pack(1, (u64)(-(s64)v), 0);
    return fp_pack(0, (u64)v, 0);
}
// -1, 0 or 1; +0 equals -0; ordered by sign and magnitude of the raw pattern
static inline int fp_cmp(u32 a, u32 b) {
    s64 x = (a & 0x80000000u) ? -(s64)(a & 0x7FFFFFFF) : (s64)(a & 0x7FFFFFFF);
    s64 y = (b & 0x80000000u) ? -(s64)(b & 0x7FFFFFFF) : (s64)(b & 0x7FFFFFFF);
    return (x > y) - (x < y);
}
static inline u32 fp_max(u32 a, u32 b) { return fp_cmp(a, b) >= 0 ? a : b; }
static inline u32 fp_min(u32 a, u32 b) { return fp_cmp(a, b) <= 0 ? a : b; }
static inline bool fp_eq(u32 a, u32 b) { return fp_cmp(a, b) == 0; }
static inline bool fp_lt(u32 a, u32 b) { return fp_cmp(a, b) < 0; }
static inline bool fp_le(u32 a, u32 b) { return fp_cmp(a, b) <= 0; }

#else   // host model

static inline float fp_f(u32 raw) { float f; memcpy(&f, &raw, 4); return f; }
static inline u32 fp_r(float f) { u32 raw; memcpy(&raw, &f, 4); return raw; }
// signed minimum with 0x7f7fffff, then unsigned minimum with 0xff7fffff
static inline u32 fp_clamp(u32 a) {
    if ((s32)a > (s32)0x7F7FFFFF) a = 0x7F7FFFFFu;
    if (a > 0xFF7FFFFFu) a = 0xFF7FFFFFu;
    return a;
}
static inline float fp_cf(u32 raw) { return fp_f(fp_clamp(raw)); }
static inline u32 fp_add(u32 a, u32 b) { float x = fp_cf(a), y = fp_cf(b); return fp_r(x + y); }
static inline u32 fp_sub(u32 a, u32 b) { float x = fp_cf(a), y = fp_cf(b); return fp_r(x - y); }
static inline u32 fp_mul(u32 a, u32 b) { float x = fp_cf(a), y = fp_cf(b); return fp_r(x * y); }
static inline u32 fp_div(u32 a, u32 b) {
    if ((b & 0x7F800000u) == 0) return ((a ^ b) & 0x80000000u) | 0x7F7FFFFFu;
    float x = fp_cf(a), y = fp_cf(b);
    return fp_r(x / y);
}
static inline u32 fp_sqrt(u32 a) { float x = fp_f(fp_clamp(a) & 0x7FFFFFFFu); return fp_r(__builtin_sqrtf(x)); }
static inline u32 fp_rsqrt(u32 a, u32 b) {
    if ((b & 0x7F800000u) == 0) return ((a ^ b) & 0x80000000u) | 0x7F7FFFFFu;
    float x = fp_cf(a), y = fp_cf(b);
    float s = __builtin_sqrtf(y);
    float r = 1.0f / s;
    return fp_r(x * r);
}
// FCVTZS: saturating, NaN gives 0
static inline u32 fp_to_int(u32 a) {
    float x = fp_f(a);
    if (x != x) return 0;
    if (x >= 2147483648.0f) return 0x7FFFFFFFu;
    if (x <= -2147483648.0f) return 0x80000000u;
    return (u32)(s32)x;
}
static inline u32 fp_from_int(u32 w) { s32 v = (s32)w; return fp_r((float)v); }
static inline u32 fp_max(u32 a, u32 b) { float x = fp_cf(a), y = fp_cf(b); return fp_r(__builtin_fmaxf(x, y)); }
static inline u32 fp_min(u32 a, u32 b) { float x = fp_cf(a), y = fp_cf(b); return fp_r(__builtin_fminf(x, y)); }
static inline bool fp_eq(u32 a, u32 b) { return fp_cf(a) == fp_cf(b); }
static inline bool fp_lt(u32 a, u32 b) { return fp_cf(a) < fp_cf(b); }
static inline bool fp_le(u32 a, u32 b) { return fp_cf(a) <= fp_cf(b); }

#endif
