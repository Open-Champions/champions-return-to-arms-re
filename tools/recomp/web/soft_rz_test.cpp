// soft_rz_test.cpp - soft_rz.h against a processor that really rounds toward zero, without
// and with flush-to-zero.
//
//   clang++ -std=c++17 -O2 -ffp-contract=off -frounding-math soft_rz_test.cpp -o soft_rz_test && ./soft_rz_test
//   em++    -std=c++17 -O2 -ffp-contract=off soft_rz_test.cpp -o soft_rz_test.js && node soft_rz_test.js
//
// On a host with the modes (an ARM64 Mac) every helper is compared with the processor's
// own result, bit for bit, over all pairs of a list of special values and N random operand
// sets of several kinds: the plain family in FE_TOWARDZERO, the _fz family in
// FE_TOWARDZERO with FPCR.FZ set (the state the Mac builds run the game's threads in).
// The number of differences is printed.  On every host a checksum over the helpers'
// results is printed: the WebAssembly build has to print the same checksums as the Mac.
// Exit code 1 when a difference was found.
#include "soft_rz.h"

#include <cfenv>
#include <cstdio>
#include <cstdlib>
#include <vector>

static uint64_t g_state = 0x9E3779B97F4A7C15ull;
static uint64_t next64() { g_state ^= g_state << 13; g_state ^= g_state >> 7; g_state ^= g_state << 17; return g_state; }
static float raw(uint32_t r) { return softrz::from_bits(r); }

// keep the compiler from folding or reordering the reference operations
template <class T> static T opaque(T v) { volatile T x = v; return x; }
static float hw_add(float a, float b) { return opaque(a) + opaque(b); }
static float hw_sub(float a, float b) { return opaque(a) - opaque(b); }
static float hw_mul(float a, float b) { return opaque(a) * opaque(b); }
static float hw_div(float a, float b) { return opaque(a) / opaque(b); }
static float hw_sqrt(float a) { return __builtin_sqrtf(opaque(a)); }
static float hw_int(int32_t v) { return (float)opaque(v); }
static float hw_max(float a, float b) { return __builtin_fmaxf(opaque(a), opaque(b)); }
static float hw_min(float a, float b) { return __builtin_fminf(opaque(a), opaque(b)); }
static uint32_t hw_cmp(float a, float b) { float x = opaque(a), y = opaque(b); return (x == y ? 1u : 0u) | (x < y ? 2u : 0u) | (x <= y ? 4u : 0u); }

// flush-to-zero of the processor (ARM64: FPCR bit 24); false where there is none to set
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

enum { PLAIN = 6, FZ = 10, KINDS = PLAIN + FZ };
static const char* NAMES[KINDS] = {"add", "subtract", "multiply", "divide", "square root", "from integer",
                                   "add, flush", "subtract, flush", "multiply, flush", "divide, flush", "square root, flush",
                                   "maximum, flush", "minimum, flush", "equal, flush", "less, flush", "less or equal, flush"};

int main(int argc, char** argv) {
    long count = argc > 1 ? atol(argv[1]) : 4000000;
    std::vector<uint32_t> special = {
        0x00000000, 0x80000000, 0x00000001, 0x80000001, 0x007FFFFF, 0x807FFFFF, 0x00800000, 0x80800000,
        0x00800001, 0x3F800000, 0xBF800000, 0x3F7FFFFF, 0x3F800001, 0x40000000, 0x40400000, 0x3EAAAAAB,
        0x7F7FFFFF, 0xFF7FFFFF, 0x7F7FFFFE, 0x7F000000, 0x7F800000, 0xFF800000, 0x7FC00000, 0x7FA00001,
        0x4B800000, 0x4B7FFFFF, 0x4B800001, 0x4C000000, 0x33800000, 0x34000000, 0x3F000000, 0x00FFFFFF,
        0x01000000, 0x1E3CE508, 0x5F000000, 0x5F7FFFFF, 0x20000000, 0x1F800000, 0x0D800000, 0x71800000,
        0x00400000, 0x80400000, 0x00C00000, 0x80C00000, 0x20800000, 0x1F000000, 0x20000001, 0x9FFFFFFF,
    };
    bool can_round = fesetround(FE_TOWARDZERO) == 0 && fegetround() == FE_TOWARDZERO;
    // is the mode real? 1 + 0.75 places is 1 toward zero and the next number to nearest
    // (Emscripten's fesetround() answers "done" and changes nothing)
    if (can_round && softrz::bits(hw_add(1.0f, raw(0x33C00000))) != 0x3F800000) can_round = false;
    fesetround(FE_TONEAREST);
    // and flush-to-zero: the smallest normal number halved is zero with it
    bool can_flush = can_round && set_fz(true) && softrz::bits(hw_mul(raw(0x00800000), 0.5f)) == 0;
    set_fz(false);
    printf("this host %s round toward zero and %s flush to zero\n", can_round ? "can" : "cannot", can_flush ? "can" : "cannot");
    if (!can_round) printf("(the checksums below are to be compared with a host that can)\n");

    uint64_t sums[KINDS] = {0}, differ[KINDS] = {0}, cases = 0;
    auto mix = [](uint64_t& sum, uint32_t value) { sum = (sum ^ value) * 0x100000001B3ull + (sum >> 29); };
    auto nan = [](uint32_t r) { return (r & 0x7FFFFFFFu) > 0x7F800000u; };
    auto one = [&](uint32_t ra, uint32_t rb) {
        float a = raw(ra), b = raw(rb);
        bool numbers = !nan(ra) && !nan(rb);            // the game's operands are clamped: never a NaN
        uint32_t soft[KINDS] = {
            softrz::bits(softrz::add(a, b)), softrz::bits(softrz::sub(a, b)), softrz::bits(softrz::mul(a, b)),
            softrz::bits(softrz::div(a, b)), softrz::bits(softrz::sqrt(a)), softrz::bits(softrz::from_int((int32_t)ra)),
            softrz::bits(softrz::add_fz(a, b)), softrz::bits(softrz::sub_fz(a, b)), softrz::bits(softrz::mul_fz(a, b)),
            softrz::bits(softrz::div_fz(a, b)), softrz::bits(softrz::sqrt_fz(a)),
            numbers ? softrz::bits(softrz::max_fz(a, b)) : 0, numbers ? softrz::bits(softrz::min_fz(a, b)) : 0,
            numbers ? (uint32_t)softrz::eq_fz(a, b) : 0, numbers ? (uint32_t)softrz::lt_fz(a, b) : 0, numbers ? (uint32_t)softrz::le_fz(a, b) : 0};
        // the bits of a NaN are the processor's choice and nothing reads them: count any NaN as one value
        for (int k = 0; k < KINDS; k++) { if (nan(soft[k])) soft[k] = 0x7FC00000u; mix(sums[k], soft[k]); }
        cases++;
        if (!can_round) return;
        uint32_t hard[KINDS] = {0};
        fesetround(FE_TOWARDZERO);
        hard[0] = softrz::bits(hw_add(a, b)); hard[1] = softrz::bits(hw_sub(a, b)); hard[2] = softrz::bits(hw_mul(a, b));
        hard[3] = softrz::bits(hw_div(a, b)); hard[4] = softrz::bits(hw_sqrt(a)); hard[5] = softrz::bits(hw_int((int32_t)ra));
        if (can_flush) {
            set_fz(true);
            hard[6] = softrz::bits(hw_add(a, b)); hard[7] = softrz::bits(hw_sub(a, b)); hard[8] = softrz::bits(hw_mul(a, b));
            hard[9] = softrz::bits(hw_div(a, b)); hard[10] = softrz::bits(hw_sqrt(a));
            if (numbers) {
                hard[11] = softrz::bits(hw_max(a, b)); hard[12] = softrz::bits(hw_min(a, b));
                uint32_t c = hw_cmp(a, b);
                hard[13] = c & 1; hard[14] = (c >> 1) & 1; hard[15] = (c >> 2) & 1;
            }
            set_fz(false);
        }
        fesetround(FE_TONEAREST);
        for (int k = 0; k < (can_flush ? KINDS : PLAIN); k++) {
            if (nan(hard[k])) hard[k] = 0x7FC00000u;
            if (hard[k] != soft[k] && differ[k]++ < 5) printf("  %s(%08x, %08x): processor %08x, helper %08x\n", NAMES[k], ra, rb, hard[k], soft[k]);
        }
    };
    for (uint32_t a : special) for (uint32_t b : special) one(a, b);
    for (long n = 0; n < count; n++) {
        uint64_t r = next64(), s = next64();
        uint32_t a = (uint32_t)r, b = (uint32_t)(r >> 32);
        switch (n % 10) {
        case 0: break;                                                                      // any bits
        case 1: a = (a & 0x807FFFFF) | ((100 + (s & 63)) << 23); b = (b & 0x807FFFFF) | ((100 + ((s >> 8) & 63)) << 23); break;   // ordinary magnitudes
        case 2: b = a + (uint32_t)(s & 7) - 3; break;                                       // a few places apart
        case 3: b = (a ^ 0x80000000u) + (uint32_t)(s & 7) - 3; break;                       // nearly cancelling
        case 4: a = softrz::bits((float)(int32_t)(s & 0xFFFF) - 32768.0f); b = softrz::bits((float)(int32_t)((s >> 16) & 0xFFF) + 1.0f); break;   // small whole numbers
        case 5: a = (a & 0x807FFFFF) | ((s & 3) << 23); b = (b & 0x807FFFFF) | ((120 + ((s >> 8) & 15)) << 23); break;     // tiny against ordinary
        case 6: a = (a & 0x807FFFFF) | ((250 + (s & 7)) << 23); if ((a & 0x7F800000u) == 0x7F800000u) a &= 0xFF7FFFFFu; b = (b & 0x807FFFFF) | ((120 + ((s >> 8) & 15)) << 23); break;   // near the largest
        case 7: a = (a & 0x807FFFFF) | ((s & 3) << 23); b = (b & 0x807FFFFF) | (((s >> 8) & 3) << 23); break;              // tiny against tiny
        case 8: a = (a & 0x807FFFFF) | ((1 + (s & 31)) << 23); b = (b & 0x807FFFFF) | ((96 + ((s >> 8) & 63)) << 23); break;   // products and quotients around the smallest number
        case 9: a = (a & 0x807FFFFF) | ((1 + (s & 3)) << 23); b = (a ^ ((s >> 8) & 1 ? 0x80000000u : 0)) + (uint32_t)((s >> 16) & 0xFFFFF) - 0x80000; break;   // sums around the smallest number
        }
        one(a, b);
    }
    uint64_t total = 0;
    for (int k = 0; k < KINDS; k++) {
        printf("%-22s checksum %016llx", NAMES[k], (unsigned long long)sums[k]);
        if (can_round && (k < PLAIN || can_flush)) printf("   differences from the processor: %llu", (unsigned long long)differ[k]);
        printf("\n");
        total += differ[k];
    }
    printf("%llu operand sets\n", (unsigned long long)cases);
    return total ? 1 : 0;
}
