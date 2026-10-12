// soft_rz.h - single-precision arithmetic rounded toward zero on a host that can only
// round to nearest.
//
// The console rounds toward zero, and so do the Mac builds of this project (the runtime
// and the Play! emulator both put the processor in that mode).  WebAssembly has one
// rounding mode, to nearest, and no way to change it (Emscripten's fesetround() answers
// "done" and changes nothing).  These
// helpers give the toward-zero result anyway, bit for bit what an IEEE processor in that
// mode gives, tiny (denormal) results included: each computes the nearest result, finds
// out *exactly* whether that lies beyond the true one, and if it does steps one place
// back toward zero.
//
//   add, subtract  the error of the nearest sum is itself a float and is computed without
//                  error (Knuth's two-sum); the sum is beyond the truth when the error
//                  has the other sign
//   multiply       the product of two floats is exact in a double
//   divide         quotient * divisor is exact in a double: compare it with the dividend
//   square root    root * root is exact in a double: compare it with the operand
//   from integer   every 32-bit integer is exact in a double
//
// Flush-to-zero.  The Mac builds also run the game's threads with tiny (denormal) numbers
// switched off, as the Play! emulator does (FPCR.FZ on ARM64): a tiny operand is read as
// zero and a result too small to be a normal number is zero, with its sign.  WebAssembly
// has no such switch either.  The second family below (add_fz ...) is the first with that
// rule applied: operands through flush(), the toward-zero result through flush().  (With
// rounding toward zero a result is tiny after rounding exactly when it was before, so the
// order does not matter.)  Compares and minimum / maximum read tiny operands as zero too:
// fpu.h does that with flush() on the bit patterns.
//
// Used by tools/recomp/rt/fpu.h and vu0.h when RTA_SOFT_RZ is defined (web/build.py
// --arith zero).  soft_rz_test.cpp checks every helper against the processor's own
// toward-zero mode on a Mac, without and with flush-to-zero, and prints checksums a
// WebAssembly build has to reproduce.
#pragma once
#include <cstdint>
#include <cstring>

namespace softrz {

static inline uint32_t bits(float f) { uint32_t r; memcpy(&r, &f, 4); return r; }
static inline float from_bits(uint32_t r) { float f; memcpy(&f, &r, 4); return f; }
static inline bool finite(float f) { return (bits(f) & 0x7F800000u) != 0x7F800000u; }
static inline bool finite(double d) { uint64_t r; memcpy(&r, &d, 8); return (r & 0x7FF0000000000000ull) != 0x7FF0000000000000ull; }
static inline double magnitude(double d) { return d < 0 ? -d : d; }
// one place toward zero; never called with a zero
static inline float back(float r) { return from_bits(bits(r) - 1); }
// a finite operation overflowed: toward zero stops at the largest number
static inline float largest(float r) { return from_bits((bits(r) & 0x80000000u) | 0x7F7FFFFFu); }

static inline float add(float a, float b) {
    float s = a + b;
    if (!finite(s)) return (finite(a) && finite(b)) ? largest(s) : s;
    float bv = s - a, av = s - bv;
    float e = (a - av) + (b - bv);                      // a + b == s + e, exactly
    if (e != 0 && ((e < 0) != (s < 0))) s = back(s);
    return s;
}
static inline float sub(float a, float b) { return add(a, -b); }

static inline float mul(float a, float b) {
    double p = (double)a * (double)b;                   // exact
    float r = (float)p;
    if (!finite(r)) return finite(p) ? largest(r) : r;
    if (magnitude((double)r) > magnitude(p)) r = back(r);
    return r;
}

static inline float div(float a, float b) {
    float q = a / b;
    if (!finite(q)) return (finite(a) && finite(b) && b != 0) ? largest(q) : q;
    double p = (double)q * (double)b;                   // exact
    if (magnitude(p) > magnitude((double)a)) q = back(q);
    return q;
}

static inline float sqrt(float x) {
    float r = __builtin_sqrtf(x);
    if (!finite(r) || r != r) return r;
    if ((double)r * (double)r > (double)x) r = back(r);
    return r;
}

static inline float from_int(int32_t v) {
    float r = (float)v;
    if (magnitude((double)r) > magnitude((double)v)) r = back(r);
    return r;
}

// ---- with flush-to-zero ---------------------------------------------------------------
// a tiny number (exponent field 0, fraction not 0) is zero with its sign
static inline uint32_t flush_bits(uint32_t r) { return (r & 0x7F800000u) ? r : (r & 0x80000000u); }
static inline float flush(float f) { return from_bits(flush_bits(bits(f))); }
static inline float add_fz(float a, float b) { return flush(add(flush(a), flush(b))); }
static inline float sub_fz(float a, float b) { return flush(add(flush(a), -flush(b))); }
static inline float mul_fz(float a, float b) { return flush(mul(flush(a), flush(b))); }
static inline float div_fz(float a, float b) { return flush(div(flush(a), flush(b))); }
static inline float sqrt_fz(float x) { return sqrt(flush(x)); }
// Compares, maximum and minimum as an ARM64 processor in that mode gives them (FCMP,
// FMAXNM, FMINNM) for operands that are numbers: tiny ones are zero, and of +0 and -0 the
// maximum is +0 and the minimum -0.
static inline bool eq_fz(float a, float b) { return flush(a) == flush(b); }
static inline bool lt_fz(float a, float b) { return flush(a) < flush(b); }
static inline bool le_fz(float a, float b) { return flush(a) <= flush(b); }
static inline float max_fz(float a, float b) { float x = flush(a), y = flush(b); return x > y ? x : x < y ? y : from_bits(bits(x) & bits(y)); }
static inline float min_fz(float a, float b) { float x = flush(a), y = flush(b); return x < y ? x : x > y ? y : from_bits(bits(x) | bits(y)); }

}  // namespace softrz
