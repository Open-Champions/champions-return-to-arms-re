// soft_rz4.h - soft_rz.h four at a time: single-precision add, subtract, multiply and
// integer conversion rounded toward zero with flush-to-zero, on a host that can only round
// to nearest and keeps tiny numbers (WebAssembly), as vector code.
//
// What it is for: the vertex programs (VU1) of the native build's page.  The unit rounds
// toward zero; the Mac application puts the processor in that mode (and, for translated
// programs, in flush-to-zero) while a program runs, and its vertices are what a picture
// is compared with.  render/vu1_step.h has the software form field by field
// (RTA_SOFT_RZ_VU1), which made the exact page 2.7 times dearer than the one that rounds
// to nearest; this is the same arithmetic on whole registers.
//
// Written with the compiler's own vector types (clang / GCC `vector_size`), not with one
// machine's intrinsics, so that the one source is WebAssembly SIMD under Emscripten
// (-msimd128) and NEON on an ARM64 Mac - where soft_rz4_test.cpp compares every helper
// with the processor's own toward-zero, flush-to-zero mode, and prints checksums that the
// WebAssembly build has to print too.
//
// The result of each helper is, bit for bit, what an ARM64 processor gives with
// FPCR.RMode = toward zero and FPCR.FZ = 1:
//
//   add, sub   the nearest sum and its error, which is itself a float and is computed
//              without error (the fast two-sum, larger operand first): the sum lies beyond
//              the true one when the error has the other sign, and is then stepped one
//              place back
//   mul        the product of two floats is exact in a double; cut to 24 places there
//              (the low 29 bits cleared) it is the toward-zero float
//   from_int   a 32-bit integer times a power of two is exact in a double: the same cut
//
// and then: a result too small to be a normal number is zero with its sign, one beyond
// the largest number is the largest.
//
// Operands.  The plain helpers (add, sub, mul) take "the unit's numbers": finite, and zero
// or normal - what vu_in / v4_in make of any bit pattern, and what every result here is.
// The _fz helpers take any finite operands and read a tiny one as zero first, as the
// processor's mode does.  Infinities and NaNs are not handled: the unit has none.
#pragma once
#include <cstdint>

namespace softrz4 {

typedef float F4 __attribute__((vector_size(16)));
typedef uint32_t U4 __attribute__((vector_size(16)));
typedef int32_t I4 __attribute__((vector_size(16)));
typedef double D2 __attribute__((vector_size(16)));
typedef uint64_t Q2 __attribute__((vector_size(16)));
typedef float F2 __attribute__((vector_size(8)));
typedef int32_t I2 __attribute__((vector_size(8)));

#define SOFTRZ4_INLINE inline __attribute__((always_inline))

static SOFTRZ4_INLINE U4 splat(uint32_t x) { U4 v = {x, x, x, x}; return v; }

// a tiny number (exponent field 0) is zero with its sign
static SOFTRZ4_INLINE U4 flush(U4 r) {
    U4 number = (U4)((I4)(r & splat(0x7F800000u)) != (I4)splat(0));
    return r & (number | splat(0x80000000u));
}
// what every helper ends with: infinity (a finite operation went beyond the range) is the
// largest number - one place back - and a tiny result is zero
static SOFTRZ4_INLINE U4 finish(U4 r) {
    r += (U4)((I4)(r & splat(0x7FFFFFFFu)) > (I4)splat(0x7F7FFFFFu));
    return flush(r);
}

static SOFTRZ4_INLINE U4 add(U4 a, U4 b) {
#pragma clang fp contract(off)
    // the operand of the larger magnitude first: then the error of the nearest sum comes out
    // of two subtractions, exactly, and neither can leave the range (Dekker's fast two-sum;
    // the symmetric form, Knuth's, goes to infinity on the way when the operands have
    // opposite signs and one is near the largest number)
    U4 swap = (U4)((I4)(a & splat(0x7FFFFFFFu)) < (I4)(b & splat(0x7FFFFFFFu)));
    U4 first = (a & ~swap) | (b & swap);
    F4 x = (F4)first, y = (F4)(a ^ b ^ first);
    F4 s = x + y;
    F4 e = y - (s - x);                                 // x + y == s + e, exactly
    const F4 zero = {0, 0, 0, 0};
    // beyond the truth: the error is not zero and has the other sign.  (When the sum went
    // to infinity the error is the opposite infinity: one place back is the largest number.)
    I4 beyond = (e != zero) & ((I4)((U4)e ^ (U4)s) >> 31);
    return finish((U4)s + (U4)beyond);                  // one place back where beyond
}
static SOFTRZ4_INLINE U4 sub(U4 a, U4 b) { return add(a, b ^ splat(0x80000000u)); }

// a pair of exact doubles cut to 24 places each, as two floats; `top` gets the doubles'
// high words (sign and exponent: is the value too small for a float?)
static SOFTRZ4_INLINE U4 cut(D2 low, D2 high, U4* top) {
    const Q2 keep = {~0x1FFFFFFFull, ~0x1FFFFFFFull};  // 53 - 24 places
    Q2 l = (Q2)low & keep, h = (Q2)high & keep;
    F2 rl = __builtin_convertvector((D2)l, F2), rh = __builtin_convertvector((D2)h, F2);       // exact where the value is a normal float
    *top = __builtin_shufflevector((U4)l, (U4)h, 1, 3, 5, 7);
    return (U4)__builtin_shufflevector(rl, rh, 0, 1, 2, 3);
}

static SOFTRZ4_INLINE U4 mul(U4 a, U4 b) {
#pragma clang fp contract(off)
    F4 x = (F4)a, y = (F4)b;
    D2 low = __builtin_convertvector(__builtin_shufflevector(x, x, 0, 1), D2) * __builtin_convertvector(__builtin_shufflevector(y, y, 0, 1), D2);
    D2 high = __builtin_convertvector(__builtin_shufflevector(x, x, 2, 3), D2) * __builtin_convertvector(__builtin_shufflevector(y, y, 2, 3), D2);
    U4 top;
    U4 r = cut(low, high, &top);
    // below 2^-126 the conversion to float rounded (it may even have reached the smallest
    // normal number): zero, with the product's sign.  2^128 and up became infinity.
    U4 tiny = (U4)((I4)(top & splat(0x7FFFFFFFu)) < (I4)splat(0x38100000u));
    r &= ~tiny | splat(0x80000000u);
    return r + (U4)((I4)(r & splat(0x7FFFFFFFu)) > (I4)splat(0x7F7FFFFFu));
}

// (float)v * scale, both steps toward zero, for a scale that is a power of two no smaller
// than 2^-64 (VU1's ITOF0, 4, 12, 15): one cut, since the scaling loses nothing
static SOFTRZ4_INLINE U4 from_int_scaled(U4 v, float scale) {
#pragma clang fp contract(off)
    I4 i = (I4)v;
    const D2 s = {scale, scale};
    D2 low = __builtin_convertvector(__builtin_shufflevector(i, i, 0, 1), D2) * s;
    D2 high = __builtin_convertvector(__builtin_shufflevector(i, i, 2, 3), D2) * s;
    U4 top;
    return cut(low, high, &top);
}

// any finite operands: a tiny one is zero
static SOFTRZ4_INLINE U4 add_fz(U4 a, U4 b) { return add(flush(a), flush(b)); }
static SOFTRZ4_INLINE U4 sub_fz(U4 a, U4 b) { return sub(flush(a), flush(b)); }
static SOFTRZ4_INLINE U4 mul_fz(U4 a, U4 b) { return mul(flush(a), flush(b)); }

}  // namespace softrz4
