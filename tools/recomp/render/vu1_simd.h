// vu1_simd.h - a VU1 float register as a vector of four, for the translated programs
// (vu1_translate.py writes code against this; vu1_fast.h is the rest of what it uses).
//
// Every operation here is the four-wide form of what vu1_step.h does field by field, and
// has to give the same bits: v4_in is vu_in, v4_out is vu_out, v4_max / v4_min compare bit
// patterns as sign and magnitude, v4_add / v4_sub / v4_mul are the processor's own
// instructions in whatever rounding mode the thread is in (Vu1::run puts it in "toward
// zero", and NEON and SSE vector arithmetic follow that mode as scalar arithmetic does).
// test_vu1_simd() in vu1_fast_test.cpp compares each with the scalar functions.
//
//   NEON                    AArch64
//   SSE2                    x86-64 (and 32-bit x86 built with SSE2)
//   WebAssembly SIMD        Emscripten with -msimd128
//   plain C++               everything else, -DVU1_SIMD_NONE, and RTA_SOFT_RZ_VU1 (the
//                           WebAssembly build that rounds toward zero in software: its
//                           arithmetic is vu_add / vu_sub / vu_mul of vu1_step.h per field)
#pragma once
#include "vu1_step.h"

#if defined(RTA_SOFT_RZ_VU1) || defined(VU1_SIMD_NONE)
#define VU1_SIMD_KIND 0
#elif defined(__aarch64__) || defined(_M_ARM64)
#define VU1_SIMD_KIND 1
#include <arm_neon.h>
#elif defined(__SSE2__) || defined(_M_X64)
#define VU1_SIMD_KIND 2
#include <emmintrin.h>
#elif defined(__wasm_simd128__)
#define VU1_SIMD_KIND 3
#include <wasm_simd128.h>
#else
#define VU1_SIMD_KIND 0
#endif

namespace render {

// A value the translator has proved to be the result of an arithmetic instruction (or
// vf0, or a copy of such a value) needs no vu_in: it is a finite number that is zero or
// normal, and vu_in leaves such a number as it is.  That holds only while results cannot
// overflow to infinity, which is the case when the arithmetic rounds toward zero - on a
// host put in that mode and in the software family.  A WebAssembly build that computes to
// nearest (the page's default) can make an infinity; there the proof is not used.
#if defined(__EMSCRIPTEN__) && !defined(RTA_SOFT_RZ_VU1)
#define VU1_RESULTS_STAY_FINITE 0
#else
#define VU1_RESULTS_STAY_FINITE 1
#endif

#if VU1_SIMD_KIND == 1
// ---------------------------------------------------------------------------------- NEON
typedef uint32x4_t V4;
static VU1_INLINE V4 v4_load(const uint8_t* p) { return vreinterpretq_u32_u8(vld1q_u8(p)); }
static VU1_INLINE void v4_store(uint8_t* p, V4 v) { vst1q_u8(p, vreinterpretq_u8_u32(v)); }
static VU1_INLINE V4 v4_splat(uint32_t x) { return vdupq_n_u32(x); }
static VU1_INLINE V4 v4_set(uint32_t x, uint32_t y, uint32_t z, uint32_t w) { const uint32_t a[4] = {x, y, z, w}; return vld1q_u32(a); }
#define v4_get(v, k) vgetq_lane_u32((v), (k))
#define v4_bc(v, k) vdupq_laneq_u32((v), (k))
static VU1_INLINE V4 v4_select(V4 mask, V4 a, V4 b) { return vbslq_u32(mask, a, b); }
static VU1_INLINE V4 v4_in(V4 u) {
    V4 sign = vandq_u32(u, vdupq_n_u32(0x80000000u));
    V4 magnitude = vminq_u32(vbicq_u32(u, vdupq_n_u32(0x80000000u)), vdupq_n_u32(0x7F7FFFFFu));    // exponent 255: the largest number
    V4 number = vtstq_u32(u, vdupq_n_u32(0x7F800000u));                                             // exponent 0: zero
    return vorrq_u32(vandq_u32(magnitude, number), sign);
}
static VU1_INLINE V4 v4_out(V4 r) {
    V4 number = vtstq_u32(r, vdupq_n_u32(0x7F800000u));
    return vandq_u32(r, vorrq_u32(number, vdupq_n_u32(0x80000000u)));
}
static VU1_INLINE V4 v4_add(V4 a, V4 b) { return vreinterpretq_u32_f32(vaddq_f32(vreinterpretq_f32_u32(a), vreinterpretq_f32_u32(b))); }
static VU1_INLINE V4 v4_sub(V4 a, V4 b) { return vreinterpretq_u32_f32(vsubq_f32(vreinterpretq_f32_u32(a), vreinterpretq_f32_u32(b))); }
static VU1_INLINE V4 v4_mul(V4 a, V4 b) { return vreinterpretq_u32_f32(vmulq_f32(vreinterpretq_f32_u32(a), vreinterpretq_f32_u32(b))); }
static VU1_INLINE int32x4_t v4_key(V4 u) {              // vu_key: -(magnitude) for a set sign bit
    int32x4_t s = vshrq_n_s32(vreinterpretq_s32_u32(u), 31);
    return vsubq_s32(veorq_s32(vreinterpretq_s32_u32(vbicq_u32(u, vdupq_n_u32(0x80000000u))), s), s);
}
static VU1_INLINE V4 v4_max(V4 a, V4 b) { return vbslq_u32(vcgtq_s32(v4_key(a), v4_key(b)), a, b); }
static VU1_INLINE V4 v4_min(V4 a, V4 b) { return vbslq_u32(vcltq_s32(v4_key(a), v4_key(b)), a, b); }
static VU1_INLINE V4 v4_itof(V4 a, float scale) { return vreinterpretq_u32_f32(vmulq_f32(vcvtq_f32_s32(vreinterpretq_s32_u32(a)), vdupq_n_f32(scale))); }
// (a is already brought into range.)  The conversion cuts toward zero and stops at the
// largest and smallest integers, which is what the interpreter's three-way test does.
static VU1_INLINE V4 v4_ftoi(V4 a, float scale) { return vreinterpretq_u32_s32(vcvtq_s32_f32(vmulq_f32(vreinterpretq_f32_u32(a), vdupq_n_f32(scale)))); }
static VU1_INLINE V4 v4_abs(V4 a) { return vbicq_u32(a, vdupq_n_u32(0x80000000u)); }
static VU1_INLINE V4 v4_mr32(V4 a) { return vextq_u32(a, a, 1); }

#elif VU1_SIMD_KIND == 2
// ---------------------------------------------------------------------------------- SSE2
typedef __m128i V4;
static VU1_INLINE V4 v4_load(const uint8_t* p) { return _mm_loadu_si128((const __m128i*)p); }
static VU1_INLINE void v4_store(uint8_t* p, V4 v) { _mm_storeu_si128((__m128i*)p, v); }
static VU1_INLINE V4 v4_splat(uint32_t x) { return _mm_set1_epi32((int)x); }
static VU1_INLINE V4 v4_set(uint32_t x, uint32_t y, uint32_t z, uint32_t w) { return _mm_set_epi32((int)w, (int)z, (int)y, (int)x); }
#define v4_get(v, k) ((uint32_t)_mm_cvtsi128_si32(_mm_shuffle_epi32((v), (k))))
#define v4_bc(v, k) _mm_shuffle_epi32((v), (k) * 0x55)
static VU1_INLINE V4 v4_select(V4 mask, V4 a, V4 b) { return _mm_or_si128(_mm_and_si128(mask, a), _mm_andnot_si128(mask, b)); }
static VU1_INLINE V4 v4_in(V4 u) {
    const V4 sign_bit = _mm_set1_epi32((int)0x80000000u), exponent = _mm_set1_epi32(0x7F800000);
    V4 sign = _mm_and_si128(u, sign_bit), magnitude = _mm_andnot_si128(sign_bit, u), e = _mm_and_si128(u, exponent);
    V4 is_top = _mm_cmpeq_epi32(e, exponent), is_zero = _mm_cmpeq_epi32(e, _mm_setzero_si128());
    magnitude = v4_select(is_top, _mm_set1_epi32(0x7F7FFFFF), magnitude);
    return _mm_or_si128(_mm_andnot_si128(is_zero, magnitude), sign);
}
static VU1_INLINE V4 v4_out(V4 r) {
    V4 is_zero = _mm_cmpeq_epi32(_mm_and_si128(r, _mm_set1_epi32(0x7F800000)), _mm_setzero_si128());
    return _mm_andnot_si128(_mm_andnot_si128(_mm_set1_epi32((int)0x80000000u), is_zero), r);
}
static VU1_INLINE V4 v4_add(V4 a, V4 b) { return _mm_castps_si128(_mm_add_ps(_mm_castsi128_ps(a), _mm_castsi128_ps(b))); }
static VU1_INLINE V4 v4_sub(V4 a, V4 b) { return _mm_castps_si128(_mm_sub_ps(_mm_castsi128_ps(a), _mm_castsi128_ps(b))); }
static VU1_INLINE V4 v4_mul(V4 a, V4 b) { return _mm_castps_si128(_mm_mul_ps(_mm_castsi128_ps(a), _mm_castsi128_ps(b))); }
static VU1_INLINE V4 v4_key(V4 u) {
    V4 s = _mm_srai_epi32(u, 31);
    return _mm_sub_epi32(_mm_xor_si128(_mm_andnot_si128(_mm_set1_epi32((int)0x80000000u), u), s), s);
}
static VU1_INLINE V4 v4_max(V4 a, V4 b) { return v4_select(_mm_cmpgt_epi32(v4_key(a), v4_key(b)), a, b); }
static VU1_INLINE V4 v4_min(V4 a, V4 b) { return v4_select(_mm_cmplt_epi32(v4_key(a), v4_key(b)), a, b); }
static VU1_INLINE V4 v4_itof(V4 a, float scale) { return _mm_castps_si128(_mm_mul_ps(_mm_cvtepi32_ps(a), _mm_set1_ps(scale))); }
static VU1_INLINE V4 v4_ftoi(V4 a, float scale) {
    // the conversion gives 0x80000000 for everything out of range: the interpreter gives the
    // largest integer for 2^31 and up
    __m128 scaled = _mm_mul_ps(_mm_castsi128_ps(a), _mm_set1_ps(scale));
    V4 high = _mm_castps_si128(_mm_cmpge_ps(scaled, _mm_set1_ps(2147483648.0f)));
    return _mm_xor_si128(_mm_cvttps_epi32(scaled), high);     // 0x80000000 ^ 0xFFFFFFFF = 0x7FFFFFFF
}
static VU1_INLINE V4 v4_abs(V4 a) { return _mm_andnot_si128(_mm_set1_epi32((int)0x80000000u), a); }
static VU1_INLINE V4 v4_mr32(V4 a) { return _mm_shuffle_epi32(a, 0x39); }

#elif VU1_SIMD_KIND == 3
// ---------------------------------------------------------------------- WebAssembly SIMD
typedef v128_t V4;
static VU1_INLINE V4 v4_load(const uint8_t* p) { return wasm_v128_load(p); }
static VU1_INLINE void v4_store(uint8_t* p, V4 v) { wasm_v128_store(p, v); }
static VU1_INLINE V4 v4_splat(uint32_t x) { return wasm_u32x4_splat(x); }
static VU1_INLINE V4 v4_set(uint32_t x, uint32_t y, uint32_t z, uint32_t w) { return wasm_u32x4_make(x, y, z, w); }
#define v4_get(v, k) wasm_u32x4_extract_lane((v), (k))
#define v4_bc(v, k) wasm_i32x4_shuffle((v), (v), (k), (k), (k), (k))
static VU1_INLINE V4 v4_select(V4 mask, V4 a, V4 b) { return wasm_v128_bitselect(a, b, mask); }
static VU1_INLINE V4 v4_in(V4 u) {
    const V4 sign_bit = wasm_u32x4_splat(0x80000000u), exponent = wasm_u32x4_splat(0x7F800000u);
    V4 sign = wasm_v128_and(u, sign_bit);
    V4 magnitude = wasm_u32x4_min(wasm_v128_andnot(u, sign_bit), wasm_u32x4_splat(0x7F7FFFFFu));
    V4 is_zero = wasm_i32x4_eq(wasm_v128_and(u, exponent), wasm_u32x4_splat(0));
    return wasm_v128_or(wasm_v128_andnot(magnitude, is_zero), sign);
}
static VU1_INLINE V4 v4_out(V4 r) {
    V4 is_zero = wasm_i32x4_eq(wasm_v128_and(r, wasm_u32x4_splat(0x7F800000u)), wasm_u32x4_splat(0));
    return wasm_v128_andnot(r, wasm_v128_andnot(is_zero, wasm_u32x4_splat(0x80000000u)));
}
static VU1_INLINE V4 v4_add(V4 a, V4 b) { return wasm_f32x4_add(a, b); }
static VU1_INLINE V4 v4_sub(V4 a, V4 b) { return wasm_f32x4_sub(a, b); }
static VU1_INLINE V4 v4_mul(V4 a, V4 b) { return wasm_f32x4_mul(a, b); }
static VU1_INLINE V4 v4_key(V4 u) {
    V4 s = wasm_i32x4_shr(u, 31);
    return wasm_i32x4_sub(wasm_v128_xor(wasm_v128_andnot(u, wasm_u32x4_splat(0x80000000u)), s), s);
}
static VU1_INLINE V4 v4_max(V4 a, V4 b) { return wasm_v128_bitselect(a, b, wasm_i32x4_gt(v4_key(a), v4_key(b))); }
static VU1_INLINE V4 v4_min(V4 a, V4 b) { return wasm_v128_bitselect(a, b, wasm_i32x4_lt(v4_key(a), v4_key(b))); }
static VU1_INLINE V4 v4_itof(V4 a, float scale) { return wasm_f32x4_mul(wasm_f32x4_convert_i32x4(a), wasm_f32x4_splat(scale)); }
static VU1_INLINE V4 v4_ftoi(V4 a, float scale) { return wasm_i32x4_trunc_sat_f32x4(wasm_f32x4_mul(a, wasm_f32x4_splat(scale))); }
static VU1_INLINE V4 v4_abs(V4 a) { return wasm_v128_andnot(a, wasm_u32x4_splat(0x80000000u)); }
static VU1_INLINE V4 v4_mr32(V4 a) { return wasm_i32x4_shuffle(a, a, 1, 2, 3, 0); }

#else
// ---------------------------------------------------------------------------- plain C++
struct V4 { uint32_t u[4]; };
static VU1_INLINE float v4_f(uint32_t u) { float f; memcpy(&f, &u, 4); return f; }
static VU1_INLINE uint32_t v4_u(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
static VU1_INLINE V4 v4_load(const uint8_t* p) { V4 v; memcpy(v.u, p, 16); return v; }
static VU1_INLINE void v4_store(uint8_t* p, V4 v) { memcpy(p, v.u, 16); }
static VU1_INLINE V4 v4_splat(uint32_t x) { V4 v = {{x, x, x, x}}; return v; }
static VU1_INLINE V4 v4_set(uint32_t x, uint32_t y, uint32_t z, uint32_t w) { V4 v = {{x, y, z, w}}; return v; }
#define v4_get(v, k) ((v).u[(k)])
#define v4_bc(v, k) v4_splat((v).u[(k)])
static VU1_INLINE V4 v4_select(V4 mask, V4 a, V4 b) { V4 r; for (int k = 0; k < 4; k++) r.u[k] = (a.u[k] & mask.u[k]) | (b.u[k] & ~mask.u[k]); return r; }
static VU1_INLINE V4 v4_in(V4 u) { V4 r; for (int k = 0; k < 4; k++) r.u[k] = v4_u(vu_in(u.u[k])); return r; }
static VU1_INLINE V4 v4_out(V4 a) { V4 r; for (int k = 0; k < 4; k++) r.u[k] = v4_u(vu_out(v4_f(a.u[k]))); return r; }
static VU1_INLINE V4 v4_add(V4 a, V4 b) { V4 r; for (int k = 0; k < 4; k++) r.u[k] = v4_u(vu_add(v4_f(a.u[k]), v4_f(b.u[k]))); return r; }
static VU1_INLINE V4 v4_sub(V4 a, V4 b) { V4 r; for (int k = 0; k < 4; k++) r.u[k] = v4_u(vu_sub(v4_f(a.u[k]), v4_f(b.u[k]))); return r; }
static VU1_INLINE V4 v4_mul(V4 a, V4 b) { V4 r; for (int k = 0; k < 4; k++) r.u[k] = v4_u(vu_mul(v4_f(a.u[k]), v4_f(b.u[k]))); return r; }
static VU1_INLINE V4 v4_max(V4 a, V4 b) { V4 r; for (int k = 0; k < 4; k++) r.u[k] = vu_key(a.u[k]) > vu_key(b.u[k]) ? a.u[k] : b.u[k]; return r; }
static VU1_INLINE V4 v4_min(V4 a, V4 b) { V4 r; for (int k = 0; k < 4; k++) r.u[k] = vu_key(a.u[k]) < vu_key(b.u[k]) ? a.u[k] : b.u[k]; return r; }
static VU1_INLINE V4 v4_itof(V4 a, float scale) { V4 r; for (int k = 0; k < 4; k++) r.u[k] = v4_u(vu_mul(vu_itof((int32_t)a.u[k]), scale)); return r; }
static VU1_INLINE V4 v4_ftoi(V4 a, float scale) {
    V4 r;
    for (int k = 0; k < 4; k++) {
        float scaled = vu_mul(v4_f(a.u[k]), scale);
        r.u[k] = scaled >= 2147483648.0f ? 0x7FFFFFFFu : scaled <= -2147483648.0f ? 0x80000000u : (uint32_t)(int32_t)scaled;
    }
    return r;
}
static VU1_INLINE V4 v4_abs(V4 a) { V4 r; for (int k = 0; k < 4; k++) r.u[k] = a.u[k] & 0x7FFFFFFFu; return r; }
static VU1_INLINE V4 v4_mr32(V4 a) { V4 r = {{a.u[1], a.u[2], a.u[3], a.u[0]}}; return r; }
#endif

// ---- the same for every kind ---------------------------------------------------------------
// fields of `a` where the instruction's destination mask has them (bit 8 = x ... 1 = w), else of `b`
static VU1_INLINE V4 v4_blend(unsigned dest, V4 a, V4 b) {
    return v4_select(v4_set(dest & 8 ? ~0u : 0, dest & 4 ? ~0u : 0, dest & 2 ? ~0u : 0, dest & 1 ? ~0u : 0), a, b);
}
// a value the translator proved clean (see VU1_RESULTS_STAY_FINITE)
static VU1_INLINE V4 v4_in_clean(V4 u) { return VU1_RESULTS_STAY_FINITE ? u : v4_in(u); }
static VU1_INLINE V4 v4_splat_f(float f) { uint32_t u; memcpy(&u, &f, 4); return v4_splat(u); }

}  // namespace render
