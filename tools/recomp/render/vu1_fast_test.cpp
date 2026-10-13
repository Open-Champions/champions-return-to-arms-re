// vu1_fast_test.cpp - the four-wide operations of vu1_simd.h against the interpreter's own
// field-by-field arithmetic (vu1_step.h): every operation the translated VU1 programs are
// written with has to give the same bits.
//
//   clang++ -std=c++17 -O2 -ffp-contract=off -frounding-math -I tools/recomp/render tools/recomp/render/vu1_fast_test.cpp -o vu1_fast_test
//       (the machine's own kind: NEON with the processor's flush-to-zero mode on a Mac)
//   ... -DVU1_NO_HARDWARE_FLUSH     NEON doing the masking itself
//   ... -DVU1_SIMD_NONE             plain C++
//   ... -arch x86_64                SSE2 (runs under Rosetta on an Apple Silicon Mac)
//   em++ ... -msimd128 [-DRTA_SOFT_RZ_VU1 -I tools/recomp/web]     WebAssembly SIMD, for node
//
//   vu1_fast_test [millions of operand sets, default 4]
//
// Operands are drawn so that the cases the unit treats differently from the host come up
// all the time: exponent 0 (zero to the unit), exponent 255 (an ordinary number), results
// that fall below the smallest normal number or beyond the largest, both signs of zero.
// The reference is computed with the processor's flush-to-zero mode off, the four-wide
// form as the translated programs run it (on, where vu1_simd.h uses it).
#include "vu1_simd.h"

#include <cstdio>
#include <cstdlib>

using namespace render;

static uint64_t g_state = 0x9E3779B97F4A7C15ull;
static uint32_t rnd() {
    g_state ^= g_state << 13; g_state ^= g_state >> 7; g_state ^= g_state << 17;
    return (uint32_t)(g_state >> 16);
}
// a bit pattern of a kind chosen at random
static uint32_t operand() {
    uint32_t sign = rnd() & 0x80000000u, fraction = rnd() & 0x007FFFFFu;
    switch (rnd() % 12) {
    case 0: return sign;                                            // zero
    case 1: return sign | fraction;                                 // exponent 0
    case 2: return sign | 0x7F800000u | fraction;                   // exponent 255
    case 3: return sign | (1u << 23) | fraction;                    // the smallest exponent
    case 4: return sign | (254u << 23) | fraction;                  // the largest
    case 5: return sign | ((1 + rnd() % 30) << 23) | fraction;      // small: products fall below the range
    case 6: return sign | ((225 + rnd() % 30) << 23) | fraction;    // large: products go beyond it
    case 7: return sign | ((100 + rnd() % 56) << 23) | fraction;    // around one
    case 8: return sign | (127u << 23) | (rnd() % 3 ? 0 : fraction);
    case 9: return rnd() % 65536;                                   // a small integer kept in a float register
    case 10: return (uint32_t)-(int32_t)(rnd() % 65536);
    default: return rnd();
    }
}

static uint32_t bits(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
static float number(uint32_t u) { float f; memcpy(&f, &u, 4); return f; }

int main(int argc, char** argv) {
    const uint64_t sets = (uint64_t)(argc > 1 ? atof(argv[1]) : 4.0) * 1000000ull / 4;
    const char* kind = VU1_SIMD_KIND == 1 ? (VU1_HARDWARE_FLUSH ? "NEON with the processor's flush-to-zero mode" : "NEON, masking itself")
                     : VU1_SIMD_KIND == 2 ? "SSE2" : VU1_SIMD_KIND == 3 ? "WebAssembly SIMD" : "plain C++";
#if defined(RTA_SOFT_RZ_VU1)
    const char* arithmetic = "toward zero in software";
#elif defined(__EMSCRIPTEN__)
    const char* arithmetic = "to nearest (WebAssembly's only mode)";
#else
    const char* arithmetic = "the processor's, toward zero";
#endif
    printf("vu1_fast_test: %s; arithmetic %s\n", kind, arithmetic);
    VU1_ROUND_TOWARD_ZERO();
    static const char* const names[] = {"add", "sub", "mul", "madd", "msub", "max", "min", "itof0", "itof4", "itof12", "itof15", "ftoi0", "ftoi4", "ftoi12", "ftoi15",
                                        "abs", "mr32", "blend", "add of clean", "mul by a field", "in", "out"};
    enum { N = sizeof(names) / sizeof(names[0]) };
    uint64_t wrong[N] = {0}, checksum = 0;
    uint32_t first_bad[N][4] = {{0}};
    for (uint64_t set = 0; set < sets; set++) {
        uint32_t a[4], b[4], c[4];
        for (int k = 0; k < 4; k++) { a[k] = operand(); b[k] = operand(); c[k] = bits(vu_out(vu_mul(vu_in(operand()), vu_in(operand())))); }     // c: a clean value (an accumulator)
        const unsigned dest = rnd() & 15, field = rnd() & 3;
        uint32_t want[N][4], got[N][4];
        // ---- the interpreter's way ----
        for (int k = 0; k < 4; k++) {
            float fa = vu_in(a[k]), fb = vu_in(b[k]), fc = number(c[k]);
            want[0][k] = bits(vu_out(vu_add(fa, fb)));
            want[1][k] = bits(vu_out(vu_sub(fa, fb)));
            want[2][k] = bits(vu_out(vu_mul(fa, fb)));
            float p = vu_out(vu_mul(fa, fb));
            want[3][k] = bits(vu_out(vu_add(fc, p)));
            want[4][k] = bits(vu_out(vu_sub(fc, p)));
            want[5][k] = vu_key(a[k]) > vu_key(b[k]) ? a[k] : b[k];
            want[6][k] = vu_key(a[k]) < vu_key(b[k]) ? a[k] : b[k];
            static const unsigned shifts[4] = {0, 4, 12, 15};
            for (int s = 0; s < 4; s++) {
                want[7 + s][k] = bits(vu_mul(vu_itof((int32_t)a[k]), 1.0f / (float)(1u << shifts[s])));
                float scaled = vu_mul(fa, (float)(1u << shifts[s]));
                want[11 + s][k] = scaled >= 2147483648.0f ? 0x7FFFFFFFu : scaled <= -2147483648.0f ? 0x80000000u : (uint32_t)(int32_t)scaled;
            }
            want[15][k] = a[k] & 0x7FFFFFFFu;
            want[16][k] = a[(k + 1) & 3];
            want[17][k] = (dest & (8 >> k)) ? a[k] : b[k];
            // operands that are results already: taken as they are
            want[18][k] = bits(vu_out(vu_add(vu_in(c[k]), vu_in(want[2][k]))));
            want[19][k] = bits(vu_out(vu_mul(fa, vu_in(b[field]))));
            want[20][k] = bits(fa);
            want[21][k] = bits(vu_out(number(a[k])));
        }
        // ---- four at a time, as the translated programs run ----
        V4 va = v4_set(a[0], a[1], a[2], a[3]), vb = v4_set(b[0], b[1], b[2], b[3]), vc = v4_set(c[0], c[1], c[2], c[3]);
        V4 out[N];
        vu1_flush_on();
        out[0] = v4_out(v4_add(v4_in(va), v4_in(vb)));
        out[1] = v4_out(v4_sub(v4_in(va), v4_in(vb)));
        out[2] = v4_out(v4_mul(v4_in(va), v4_in(vb)));
        out[3] = v4_out(v4_add(vc, v4_out(v4_mul(v4_in(va), v4_in(vb)))));
        out[4] = v4_out(v4_sub(vc, v4_out(v4_mul(v4_in(va), v4_in(vb)))));
        out[5] = v4_max(va, vb);
        out[6] = v4_min(va, vb);
        out[7] = v4_itof(va, 0x1p0f); out[8] = v4_itof(va, 0x1p-4f); out[9] = v4_itof(va, 0x1p-12f); out[10] = v4_itof(va, 0x1p-15f);
        out[11] = v4_ftoi(v4_in(va), 0x1p0f); out[12] = v4_ftoi(v4_in(va), 0x1p4f); out[13] = v4_ftoi(v4_in(va), 0x1p12f); out[14] = v4_ftoi(v4_in(va), 0x1p15f);
        out[15] = v4_abs(va);
        out[16] = v4_mr32(va);
        out[17] = v4_blend(dest, va, vb);
        out[18] = v4_out(v4_add(v4_in_clean(vc), v4_in_clean(out[2])));
        out[19] = v4_out(v4_mul(v4_in(va), v4_in(field == 0 ? v4_bc(vb, 0) : field == 1 ? v4_bc(vb, 1) : field == 2 ? v4_bc(vb, 2) : v4_bc(vb, 3))));
#if VU1_HARDWARE_FLUSH
        // (With the mode, "in" is finished by the instruction that reads the value - seen
        // here through a multiplication by one - and "out" is that instruction's own
        // result: there is nothing to look at by itself.)
        out[20] = v4_out(v4_mul(v4_in(va), v4_splat_f(1.0f)));
        out[21] = v4_set(want[21][0], want[21][1], want[21][2], want[21][3]);
#else
        out[20] = v4_in(va);
        out[21] = v4_out(va);
#endif
        vu1_flush_off();
        for (int n = 0; n < (int)N; n++) {
            v4_store((uint8_t*)got[n], out[n]);
            for (int k = 0; k < 4; k++) checksum = (checksum ^ want[n][k]) * 0x100000001B3ull;
            if (memcmp(want[n], got[n], 16)) {
                if (!wrong[n]) for (int k = 0; k < 4; k++) first_bad[n][k] = got[n][k] ^ want[n][k];
                wrong[n]++;
            }
        }
    }
    uint64_t total = 0;
    for (int n = 0; n < (int)N; n++) {
        total += wrong[n];
        if (wrong[n]) printf("  %-16s %llu of %llu sets differ (first difference, as xor of the four fields: %08x %08x %08x %08x)\n", names[n], (unsigned long long)wrong[n],
                             (unsigned long long)sets, first_bad[n][0], first_bad[n][1], first_bad[n][2], first_bad[n][3]);
    }
    printf("%llu sets of four operands, %d kinds of operation: %llu differences; checksum of the reference %016llx\n", (unsigned long long)sets, (int)N,
           (unsigned long long)total, (unsigned long long)checksum);
    return total ? 1 : 0;
}
