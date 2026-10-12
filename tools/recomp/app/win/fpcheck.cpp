// fpcheck.cpp - the game's floating-point arithmetic on this processor, as one table of
// checksums.  Built by build_win.py for every target (fpcheck.exe for Windows, and for
// macOS arm64 and x86-64); the lines printed must be the same on every machine.  The
// translated game computes with rt/fpu.h (the main processor's FPU, on raw 32-bit
// patterns) and rt/vu0.h (vector unit 0); this runs every operation of both over corner
// values and a fixed pseudo-random set, in the rounding mode the runtime sets.
//
//   fpcheck            the table: one checksum per operation and operand class
//   fpcheck --dump     every result, one per line (to find a differing case with diff)
//
// Operand classes: "numbers" - what the operation can be handed by the game's own
// arithmetic (fpu.h clamps every operand to +/-FLT_MAX; rounding toward zero never makes
// an infinity); "any" - every 32-bit pattern, infinities and NaNs included.  The first
// class must agree everywhere.  The second is printed apart: where an operation makes or
// passes on a NaN, IEEE 754 leaves the NaN's sign and payload to the processor.
#include "recomp.h"
#include "vu0.h"

#include <cfenv>
#include <cstdio>
#include <vector>

static bool g_dump;
static const char* g_name;
static u64 g_hash;
static void begin(const char* name) { g_name = name; g_hash = 0xcbf29ce484222325ull; }
static inline void out(u32 a, u32 b, u32 r) {
    for (int k = 0; k < 4; k++) { g_hash ^= (r >> (k * 8)) & 0xFF; g_hash *= 0x100000001b3ull; }
    if (g_dump) printf("%s %08x %08x = %08x\n", g_name, a, b, r);
}
static u64 g_all = 0xcbf29ce484222325ull;
static void end(const char* cls, size_t count, bool counts) {
    if (!g_dump) printf("%-10s %-8s %9zu cases  %016llx\n", g_name, cls, count, (unsigned long long)g_hash);
    if (counts) { g_all ^= g_hash; g_all *= 0x100000001b3ull; }
}

static bool is_number(u32 v) { return (v & 0x7F800000u) != 0x7F800000u; }

int main(int argc, char** argv) {
    g_dump = argc > 1 && !strcmp(argv[1], "--dump");
    fesetround(FE_TOWARDZERO);                          // what rt/runtime.cpp does on every guest thread
    static const u32 corner[] = {
        0x00000000, 0x80000000, 0x00000001, 0x80000001, 0x007FFFFF, 0x807FFFFF, 0x00800000, 0x80800000,
        0x00800001, 0x3F800000, 0xBF800000, 0x3F7FFFFF, 0x3F800001, 0x40000000, 0xC0000000, 0x40400000,
        0x3F000000, 0x3EAAAAAB, 0x4EFFFFFF, 0x4F000000, 0xCF000000, 0xCF000001, 0x4F000001, 0x5F000000,
        0x7F7FFFFF, 0xFF7FFFFF, 0x7F7FFFFE, 0x7F000000, 0x00FFFFFF, 0x01000000, 0x34000000, 0x33800000,
        0x7F800000, 0xFF800000, 0x7FC00000, 0xFFC00000, 0x7F800001, 0xFF800001, 0x7FFFFFFF, 0xFFFFFFFF,
        0x7FA00000, 0xFFFFF1A3, 0x7FC12345, 0xFFD00001, 0x42F6E979, 0xC2F6E979, 0x3DCCCCCD, 0x461C4000};
    std::vector<u32> values(corner, corner + sizeof corner / sizeof corner[0]);
    u64 seed = 0x9E3779B97F4A7C15ull;
    auto next = [&]() { seed ^= seed << 13; seed ^= seed >> 7; seed ^= seed << 17; return (u32)(seed >> 16); };
    for (int k = 0; k < 400; k++) values.push_back(next());
    for (int k = 0; k < 400; k++) {                     // ordinary sizes: exponents around 1
        u32 v = next();
        values.push_back((v & 0x807FFFFFu) | ((0x70u + (v >> 23) % 0x20u) << 23));
    }
    std::vector<u32> numbers;
    for (u32 v : values) if (is_number(v)) numbers.push_back(v);

    struct Two { const char* name; u32 (*fn)(u32, u32); };
    static const Two two[] = {
        // rt/fpu.h, as the translated game calls it
        {"fp_add", [](u32 a, u32 b) { return fp_add(a, b); }}, {"fp_sub", [](u32 a, u32 b) { return fp_sub(a, b); }},
        {"fp_mul", [](u32 a, u32 b) { return fp_mul(a, b); }}, {"fp_div", [](u32 a, u32 b) { return fp_div(a, b); }},
        {"fp_rsqrt", [](u32 a, u32 b) { return fp_rsqrt(a, b); }},
        {"fp_max", [](u32 a, u32 b) { return fp_max(a, b); }}, {"fp_min", [](u32 a, u32 b) { return fp_min(a, b); }},
        {"fp_cmp", [](u32 a, u32 b) { return (u32)fp_eq(a, b) | (u32)fp_lt(a, b) << 1 | (u32)fp_le(a, b) << 2; }},
        {"fp_madd", [](u32 a, u32 b) { return fp_add(0x3F800000u, fp_mul(a, b)); }},      // MADD.S: two operations
        // rt/vu0.h: the expressions of the interpreter, on unclamped values
        {"vu_add", [](u32 a, u32 b) { return vu_raw(vu_flt(a) + vu_flt(b)); }},
        {"vu_sub", [](u32 a, u32 b) { return vu_raw(vu_flt(a) - vu_flt(b)); }},
        {"vu_mul", [](u32 a, u32 b) { return vu_raw(vu_flt(a) * vu_flt(b)); }},
        {"vu_madd", [](u32 a, u32 b) { float p = vu_flt(a) * vu_flt(b); return vu_raw(vu_flt(0x3F800000u) + p); }},
        {"vu_msub", [](u32 a, u32 b) { float p = vu_flt(a) * vu_flt(b); return vu_raw(vu_flt(0x42F6E979u) - p); }},
        {"vu_max", [](u32 a, u32 b) { float x = vu_flt(a), y = vu_flt(b); return vu_raw(x > y ? x : y); }},
        {"vu_mini", [](u32 a, u32 b) { float x = vu_flt(a), y = vu_flt(b); return vu_raw(x < y ? x : y); }},
    };
    struct One { const char* name; u32 (*fn)(u32); };
    static const One one[] = {
        {"fp_sqrt", [](u32 a) { return fp_sqrt(a); }}, {"fp_to_int", [](u32 a) { return fp_to_int(a); }},
        {"fp_from_i", [](u32 a) { return fp_from_int(a); }},
        {"vu_ftoi0", [](u32 a) { return vu_raw(vu_ftoi(vu_flt(a), 1.0f)); }},
        {"vu_ftoi4", [](u32 a) { return vu_raw(vu_ftoi(vu_flt(a), 16.0f)); }},
        {"vu_ftoi12", [](u32 a) { return vu_raw(vu_ftoi(vu_flt(a), 4096.0f)); }},
        {"vu_ftoi15", [](u32 a) { return vu_raw(vu_ftoi(vu_flt(a), 32768.0f)); }},
        {"vu_itof0", [](u32 a) { return vu_raw((float)(s32)a); }},
        {"vu_itof4", [](u32 a) { return vu_raw((float)(s32)a * (1.0f / 16.0f)); }},
        {"vu_itof12", [](u32 a) { return vu_raw((float)(s32)a * (1.0f / 4096.0f)); }},
        {"vu_itof15", [](u32 a) { return vu_raw((float)(s32)a * (1.0f / 32768.0f)); }},
    };
    for (int cls = 0; cls < 2; cls++) {
        const std::vector<u32>& set = cls == 0 ? numbers : values;
        const char* cname = cls == 0 ? "numbers" : "any";
        for (const Two& op : two) {
            // the fp_ operations clamp what they read, so for them every pattern is a "number"
            bool fp = op.name[0] == 'f';
            begin(op.name);
            for (u32 a : set) for (u32 b : set) out(a, b, op.fn(a, b));
            end(cname, set.size() * set.size(), cls == 0 || fp);
        }
        for (const One& op : one) {
            bool everywhere = op.name[0] == 'f' || !strncmp(op.name, "vu_itof", 7) || !strncmp(op.name, "vu_ftoi", 7);
            begin(op.name);
            for (u32 a : set) out(a, 0, op.fn(a));
            if (cls == 1) for (int k = 0; k < 200000; k++) { u32 a = next(); out(a, 0, op.fn(a)); }
            end(cname, set.size() + (cls == 1 ? 200000 : 0), cls == 0 || everywhere);
        }
    }
    if (!g_dump) {
        printf("must agree everywhere (fpu.h on every pattern; vu0.h on numbers, and its conversions on every pattern): %016llx\n",
               (unsigned long long)g_all);
        printf("rounding mode now %s; sizeof(long) %d, sizeof(void*) %d\n", fegetround() == FE_TOWARDZERO ? "toward zero" : "NOT toward zero",
               (int)sizeof(long), (int)sizeof(void*));
    }
    return 0;
}
