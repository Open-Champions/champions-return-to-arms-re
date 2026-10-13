// soft_rz4_test.cpp - soft_rz4.h (toward zero with flush-to-zero, four at a time) against a
// processor that really has the two modes.
//
//   clang++ -std=c++17 -O2 -ffp-contract=off -frounding-math soft_rz4_test.cpp -o soft_rz4_test && ./soft_rz4_test
//   em++    -std=c++17 -O2 -ffp-contract=off -msimd128 soft_rz4_test.cpp -o soft_rz4_test.js && node soft_rz4_test.js
//
//   soft_rz4_test [operand sets, default 8000000]
//
// On a host with the modes (an ARM64 Mac) every helper is run in the host's ordinary state
// (to nearest, tiny numbers kept: the state WebAssembly code is always in) and compared, bit
// for bit, with the processor's own scalar instruction on the same operands in "toward
// zero" with FPCR.FZ set - the state the Mac application runs a translated vertex program
// in.  The number of differences is printed.  On every host a checksum over the helpers'
// results is printed: the WebAssembly build has to print the same checksums as the Mac.
// Exit code 1 when a difference was found.
//
// Operands: all pairs of a list of special values, then random sets of ten kinds (ordinary
// magnitudes, a few places apart, nearly cancelling, small whole numbers, tiny against
// ordinary, near the largest, tiny against tiny, products and sums around the smallest
// normal number).  The plain helpers get them as "the unit's numbers" (exponent 0 read as
// zero, exponent 255 as the largest number: vu_in); the _fz helpers get every finite bit
// pattern as it is, tiny ones included.
#include "soft_rz4.h"

#include <cfenv>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

using softrz4::U4;

static uint64_t g_state = 0x9E3779B97F4A7C15ull;
static uint64_t next64() { g_state ^= g_state << 13; g_state ^= g_state >> 7; g_state ^= g_state << 17; return g_state; }
static float raw(uint32_t r) { float f; memcpy(&f, &r, 4); return f; }
static uint32_t bits(float f) { uint32_t r; memcpy(&r, &f, 4); return r; }

// keep the compiler from folding or reordering the reference operations
template <class T> static T opaque(T v) { volatile T x = v; return x; }
static float hw_add(float a, float b) { return opaque(a) + opaque(b); }
static float hw_sub(float a, float b) { return opaque(a) - opaque(b); }
static float hw_mul(float a, float b) { return opaque(a) * opaque(b); }
static float hw_int(int32_t v, float scale) { volatile float f = (float)opaque(v); return f * opaque(scale); }

static bool set_fz(bool on) {
#if defined(__aarch64__)
    uint64_t v;
    __asm__ volatile("mrs %0, fpcr" : "=r"(v));
    v = on ? (v | (1ull << 24)) : (v & ~(1ull << 24));
    __asm__ volatile("msr fpcr, %0" : : "r"(v));
    return true;
#else
    (void)on;
    return false;
#endif
}

// the unit's reading of a bit pattern (render/vu1_step.h, vu_in)
static uint32_t unit(uint32_t u) {
    uint32_t e = u & 0x7F800000u;
    return e == 0x7F800000u ? ((u & 0x80000000u) | 0x7F7FFFFFu) : e == 0 ? (u & 0x80000000u) : u;
}
// any finite number: exponent 255 becomes 254
static uint32_t finite(uint32_t u) { return (u & 0x7F800000u) == 0x7F800000u ? (u & 0xFF7FFFFFu) : u; }

enum { KINDS = 10 };
static const char* NAMES[KINDS] = {"add", "subtract", "multiply", "add, any finite", "subtract, any finite", "multiply, any finite",
                                   "from integer", "from integer / 16", "from integer / 4096", "from integer / 32768"};
static const float SCALES[4] = {0x1p0f, 0x1p-4f, 0x1p-12f, 0x1p-15f};

int main(int argc, char** argv) {
    long count = argc > 1 ? atol(argv[1]) : 8000000;
    std::vector<uint32_t> special = {
        0x00000000, 0x80000000, 0x00000001, 0x80000001, 0x007FFFFF, 0x807FFFFF, 0x00800000, 0x80800000,
        0x00800001, 0x3F800000, 0xBF800000, 0x3F7FFFFF, 0x3F800001, 0x40000000, 0x40400000, 0x3EAAAAAB,
        0x7F7FFFFF, 0xFF7FFFFF, 0x7F7FFFFE, 0x7F000000, 0x7F800000, 0xFF800000, 0x7FC00000, 0x7FA00001,
        0x4B800000, 0x4B7FFFFF, 0x4B800001, 0x4C000000, 0x33800000, 0x34000000, 0x3F000000, 0x00FFFFFF,
        0x01000000, 0x1E3CE508, 0x5F000000, 0x5F7FFFFF, 0x20000000, 0x1F800000, 0x0D800000, 0x71800000,
        0x00400000, 0x80400000, 0x00C00000, 0x80C00000, 0x20800000, 0x1F000000, 0x20000001, 0x9FFFFFFF,
        0x7FFFFFFF, 0x80000000, 0x01000001, 0xFEFFFFFF, 0x00FFFFFF, 0xFF000001, 0x4E800000, 0xCF000000,
    };
    bool can_round = fesetround(FE_TOWARDZERO) == 0 && fegetround() == FE_TOWARDZERO;
    // is the mode real? 1 + 0.75 places is 1 toward zero and the next number to nearest
    // (Emscripten's fesetround() answers "done" and changes nothing)
    if (can_round && bits(hw_add(1.0f, raw(0x33C00000))) != 0x3F800000) can_round = false;
    fesetround(FE_TONEAREST);
    bool can_flush = can_round && set_fz(true) && bits(hw_mul(raw(0x00800000), 0.5f)) == 0;
    set_fz(false);
    bool can = can_round && can_flush;
    printf("soft_rz4_test: this host %s round toward zero and %s flush to zero\n", can_round ? "can" : "cannot", can_flush ? "can" : "cannot");
    if (!can) printf("(the checksums below are to be compared with a host that can)\n");

    uint64_t sums[KINDS] = {0}, differ[KINDS] = {0}, cases = 0;
    auto mix = [](uint64_t& sum, uint32_t value) { sum = (sum ^ value) * 0x100000001B3ull + (sum >> 29); };
    uint32_t qa[4], qb[4];
    int queued = 0;
    auto four = [&]() {
        uint32_t ua[4], ub[4], fa[4], fb[4], soft[KINDS][4];
        for (int k = 0; k < 4; k++) { ua[k] = unit(qa[k]); ub[k] = unit(qb[k]); fa[k] = finite(qa[k]); fb[k] = finite(qb[k]); }
        U4 va = {ua[0], ua[1], ua[2], ua[3]}, vb = {ub[0], ub[1], ub[2], ub[3]};
        U4 wa = {fa[0], fa[1], fa[2], fa[3]}, wb = {fb[0], fb[1], fb[2], fb[3]};
        U4 ia = {qa[0], qa[1], qa[2], qa[3]};
        U4 out[KINDS] = {softrz4::add(va, vb), softrz4::sub(va, vb), softrz4::mul(va, vb), softrz4::add_fz(wa, wb), softrz4::sub_fz(wa, wb), softrz4::mul_fz(wa, wb),
                         softrz4::from_int_scaled(ia, SCALES[0]), softrz4::from_int_scaled(ia, SCALES[1]), softrz4::from_int_scaled(ia, SCALES[2]),
                         softrz4::from_int_scaled(ia, SCALES[3])};
        for (int n = 0; n < KINDS; n++) { memcpy(soft[n], &out[n], 16); for (int k = 0; k < 4; k++) mix(sums[n], soft[n][k]); }
        cases += 4;
        if (!can) return;
        uint32_t hard[KINDS][4];
        fesetround(FE_TOWARDZERO);
        set_fz(true);
        for (int k = 0; k < 4; k++) {
            hard[0][k] = bits(hw_add(raw(ua[k]), raw(ub[k]))); hard[1][k] = bits(hw_sub(raw(ua[k]), raw(ub[k]))); hard[2][k] = bits(hw_mul(raw(ua[k]), raw(ub[k])));
            hard[3][k] = bits(hw_add(raw(fa[k]), raw(fb[k]))); hard[4][k] = bits(hw_sub(raw(fa[k]), raw(fb[k]))); hard[5][k] = bits(hw_mul(raw(fa[k]), raw(fb[k])));
            for (int s = 0; s < 4; s++) hard[6 + s][k] = bits(hw_int((int32_t)qa[k], SCALES[s]));
        }
        set_fz(false);
        fesetround(FE_TONEAREST);
        for (int n = 0; n < KINDS; n++) for (int k = 0; k < 4; k++) {
            if (hard[n][k] != soft[n][k] && differ[n]++ < 5)
                printf("  %s(%08x, %08x): processor %08x, helper %08x\n", NAMES[n], n < 3 ? ua[k] : n < 6 ? fa[k] : qa[k], n < 3 ? ub[k] : n < 6 ? fb[k] : 0, hard[n][k], soft[n][k]);
        }
    };
    auto one = [&](uint32_t a, uint32_t b) { qa[queued] = a; qb[queued] = b; if (++queued == 4) { four(); queued = 0; } };
    for (uint32_t a : special) for (uint32_t b : special) one(a, b);
    for (long n = 0; n < count; n++) {
        uint64_t r = next64(), s = next64();
        uint32_t a = (uint32_t)r, b = (uint32_t)(r >> 32);
        switch (n % 10) {
        case 0: break;                                                                      // any bits
        case 1: a = (a & 0x807FFFFF) | ((100 + (s & 63)) << 23); b = (b & 0x807FFFFF) | ((100 + ((s >> 8) & 63)) << 23); break;   // ordinary magnitudes
        case 2: b = a + (uint32_t)(s & 7) - 3; break;                                       // a few places apart
        case 3: b = (a ^ 0x80000000u) + (uint32_t)(s & 7) - 3; break;                       // nearly cancelling
        case 4: a = bits((float)(int32_t)(s & 0xFFFF) - 32768.0f); b = bits((float)(int32_t)((s >> 16) & 0xFFF) + 1.0f); break;   // small whole numbers
        case 5: a = (a & 0x807FFFFF) | ((s & 3) << 23); b = (b & 0x807FFFFF) | ((120 + ((s >> 8) & 15)) << 23); break;     // tiny against ordinary
        case 6: a = (a & 0x807FFFFF) | ((250 + (s & 7)) << 23); b = (b & 0x807FFFFF) | ((120 + ((s >> 8) & 15)) << 23); break;   // near the largest
        case 7: a = (a & 0x807FFFFF) | ((s & 3) << 23); b = (b & 0x807FFFFF) | (((s >> 8) & 3) << 23); break;              // tiny against tiny
        case 8: a = (a & 0x807FFFFF) | ((1 + (s & 31)) << 23); b = (b & 0x807FFFFF) | ((96 + ((s >> 8) & 63)) << 23); break;   // products around the smallest number
        case 9: a = (a & 0x807FFFFF) | ((1 + (s & 3)) << 23); b = (a ^ ((s >> 8) & 1 ? 0x80000000u : 0)) + (uint32_t)((s >> 16) & 0xFFFFF) - 0x80000; break;   // sums around the smallest number
        }
        one(a, b);
        // near the largest against near the largest, and against something a few exponents
        // below: sums that come back into the range, sums that leave it
        if (n % 10 == 6) { one(b | 0x7E000000u, a ^ 0x80000000u); one(a, (a & 0xFF800000u) | (b & 0x007FFFFFu)); one(a ^ 0x80000000u, (b & 0x807FFFFFu) | ((240 + ((s >> 20) & 15)) << 23)); }
    }
    while (queued) one(0x3F800000, 0x3F800000);
    uint64_t total = 0;
    for (int n = 0; n < KINDS; n++) {
        printf("%-22s checksum %016llx", NAMES[n], (unsigned long long)sums[n]);
        if (can) printf("   differences from the processor: %llu", (unsigned long long)differ[n]);
        printf("\n");
        total += differ[n];
    }
    printf("%llu operand sets\n", (unsigned long long)cases);
    return total ? 1 : 0;
}
