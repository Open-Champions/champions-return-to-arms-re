// recomp.h - what generated code is written against.
//
// The translator (tools/recomp/recomp.py) turns every function of the game's executable
// into one C++ function `void fn_<address>(Ctx*)`.  Everything such a function needs is
// declared here: the register context, guest memory access, the arithmetic helpers whose
// behaviour differs from plain C (R5900 FPU, 128-bit multimedia instructions, unaligned
// loads and stores) and the hooks into the runtime (calls through a pointer, system calls,
// hardware registers).  Two programs link against this: the differential-test driver
// (rt/test_driver.cpp, built with -DRECOMP_TEST) and the headless runtime (rt/runtime.cpp).
//
// Semantics follow tools/ee_emu.py, the project's instruction interpreter, operation for
// operation; tools/recomp/difftest.py checks that function by function.
#pragma once
#include <cstdint>
#include <cstring>
#include <cstddef>

typedef uint8_t u8;
typedef int8_t s8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef int32_t s32;
typedef uint64_t u64;
typedef int64_t s64;

#define LIKELY(x) __builtin_expect(!!(x), 1)
#define UNLIKELY(x) __builtin_expect(!!(x), 0)

// Register context of one guest thread.  A general register is 128 bits wide on this CPU:
// r[n] holds bits 0-63 and rh[n] bits 64-127 (only the multimedia instructions and the
// 128-bit load/store touch rh).  r[0] and rh[0] are never written.
struct Ctx {
    u64 r[32];
    u64 rh[32];
    u64 hi, lo, hi1, lo1;
    u32 sa;
    u32 fcr31;
    u32 f[32];          // raw single-precision patterns
    u32 acc;
    u32 cop0[32];
    s64 budget;         // test build: remaining loop iterations and calls
    void* thread;       // runtime: the guest thread this context belongs to
};

typedef void (*RecompFn)(Ctx*);
struct RecompEntry { u32 addr; RecompFn fn; };
extern const RecompEntry g_recomp_entries[];
extern const unsigned g_recomp_entry_count;

#define RAM_SIZE 0x02000000u
extern u8* g_ram;       // RAM_SIZE bytes plus a guard page

// ---- supplied by whichever program links the generated code --------------------------
u64 rt_load(u32 addr, unsigned size);                 // outside main memory
void rt_store(u32 addr, unsigned size, u64 value);
void rt_load128(u32 addr, u64* lo, u64* hi);
void rt_store128(u32 addr, u64 lo, u64 hi);
void rt_call(Ctx* c, u32 target);                     // call or jump through a pointer
void rt_syscall(Ctx* c, u32 pc);
void rt_break(Ctx* c, u32 pc, u32 code);
void rt_trap(Ctx* c, u32 pc, const char* what);       // integer overflow and the like
void rt_unimpl(Ctx* c, u32 pc, u32 word);
void rt_cop2(Ctx* c, u32 pc, u32 word);               // every COP2 instruction, LQC2, SQC2
u32 rt_mfc0(Ctx* c, u32 pc, unsigned reg);
void rt_mtc0(Ctx* c, u32 pc, unsigned reg, u32 value);
void rt_eret(Ctx* c, u32 pc);
#ifdef RECOMP_TEST
bool rt_test_call(Ctx* c, u32 site, u32 target);      // false: the call was stubbed
void rt_budget(Ctx* c);
extern u8 g_dirty[RAM_SIZE >> 12];
#define DIRTY(a, n) do { g_dirty[(a) >> 12] = 1; g_dirty[((a) + (n) - 1) >> 12] = 1; } while (0)
#define BUDGET() do { if (UNLIKELY(--c->budget < 0)) rt_budget(c); } while (0)
#define CALL(fn, target, site) do { if (rt_test_call(c, site, target)) fn(c); } while (0)
#define CALLR(target, site) do { u32 t_ = (target); if (rt_test_call(c, site, t_)) rt_call(c, t_); } while (0)
#define LOCALCALL(label, target, site) do { if (rt_test_call(c, site, target)) goto label; } while (0)
#else
#define LOCALCALL(label, target, site) goto label
// Runtime build.  Every call and every backward branch counts one "unit" against
// c->budget; when it runs out the runtime gets control (rt_poll) to advance its clock,
// deliver interrupts and let another guest thread run.  g_site is the address of the
// last call instruction executed, for diagnostics.
void rt_poll(Ctx* c);
extern u32 g_site;
#define DIRTY(a, n) ((void)0)
#define BUDGET() do { if (UNLIKELY(--c->budget < 0)) rt_poll(c); } while (0)
#define CALL(fn, target, site) do { g_site = site; BUDGET(); fn(c); } while (0)
#define CALLR(target, site) do { g_site = site; BUDGET(); rt_call(c, target); } while (0)
#endif

#define SX32(x) ((u64)(s64)(s32)(x))

// ---- guest memory ---------------------------------------------------------------------
#ifdef RECOMP_RELOC_CHECK
// A test build of a translation with moved tables (recomp.py --reloc, app/party8.h): every load and store of the
// translated code is checked against the old places of the moved tables while they are moved; a hit is reported
// with the translated function it came from (app/party8.cpp).
#include "moved.h"
__attribute__((weak, noinline)) void reloc_check_hit(u32 address) { (void)address; }   // app/party8.cpp has the one that reports
static inline void RELOC_CHECK(u32 a) {
    if (UNLIKELY(g_party8_delta != nullptr)) {
        u32 p = a & 0x1FFFFFFFu;
        for (int k = 0; k < 32; k++)
            if (p >= g_party8_spans[k][0] && p < g_party8_spans[k][1]) { reloc_check_hit(a); break; }
    }
}
#else
#define RELOC_CHECK(a) ((void)0)
#endif
#ifdef RECOMP_RELOC_DYN
// A translation with moved tables (app/party8.h): every load and store at an old place of a moved table goes to the
// new place, whatever made the address (a pointer made before the move, one the translator could not follow).
#include "moved.h"
#define RELOC_MAP(a) do { if (UNLIKELY(g_party8_page[((a) & 0x1FFFFFFFu) >> 16])) (a) = party8_at(a); } while (0)
#else
#define RELOC_MAP(a) ((void)0)
#endif
static inline u8 LD8(u32 a) {
    RELOC_CHECK(a);
    RELOC_MAP(a);
    if (LIKELY(a < RAM_SIZE)) return g_ram[a];
    return (u8)rt_load(a, 1);
}
static inline u16 LD16(u32 a) {
    RELOC_CHECK(a);
    RELOC_MAP(a);
    if (LIKELY(a <= RAM_SIZE - 2)) { u16 v; memcpy(&v, g_ram + a, 2); return v; }
    return (u16)rt_load(a, 2);
}
static inline u32 LD32(u32 a) {
    RELOC_CHECK(a);
    RELOC_MAP(a);
    if (LIKELY(a <= RAM_SIZE - 4)) { u32 v; memcpy(&v, g_ram + a, 4); return v; }
    return (u32)rt_load(a, 4);
}
static inline u64 LD64(u32 a) {
    RELOC_CHECK(a);
    RELOC_MAP(a);
    if (LIKELY(a <= RAM_SIZE - 8)) { u64 v; memcpy(&v, g_ram + a, 8); return v; }
    return rt_load(a, 8);
}
static inline void ST8(u32 a, u8 v) {
    RELOC_CHECK(a);
    RELOC_MAP(a);
    if (LIKELY(a < RAM_SIZE)) { g_ram[a] = v; DIRTY(a, 1); return; }
    rt_store(a, 1, v);
}
static inline void ST16(u32 a, u16 v) {
    RELOC_CHECK(a);
    RELOC_MAP(a);
    if (LIKELY(a <= RAM_SIZE - 2)) { memcpy(g_ram + a, &v, 2); DIRTY(a, 2); return; }
    rt_store(a, 2, v);
}
static inline void ST32(u32 a, u32 v) {
    RELOC_CHECK(a);
    RELOC_MAP(a);
    if (LIKELY(a <= RAM_SIZE - 4)) { memcpy(g_ram + a, &v, 4); DIRTY(a, 4); return; }
    rt_store(a, 4, v);
}
static inline void ST64(u32 a, u64 v) {
    RELOC_CHECK(a);
    RELOC_MAP(a);
    if (LIKELY(a <= RAM_SIZE - 8)) { memcpy(g_ram + a, &v, 8); DIRTY(a, 8); return; }
    rt_store(a, 8, v);
}
// LQ / SQ: the CPU ignores the low four address bits
static inline void op_lq(Ctx* c, int rt, u32 a) {
    a &= ~15u;
    RELOC_CHECK(a);
    RELOC_MAP(a);
    u64 lo, hi;
    if (LIKELY(a <= RAM_SIZE - 16)) { memcpy(&lo, g_ram + a, 8); memcpy(&hi, g_ram + a + 8, 8); }
    else rt_load128(a, &lo, &hi);
    if (rt) { c->r[rt] = lo; c->rh[rt] = hi; }
}
static inline void op_sq(Ctx* c, int rt, u32 a) {
    a &= ~15u;
    RELOC_CHECK(a);
    RELOC_MAP(a);
    if (LIKELY(a <= RAM_SIZE - 16)) {
        memcpy(g_ram + a, &c->r[rt], 8); memcpy(g_ram + a + 8, &c->rh[rt], 8); DIRTY(a, 16);
    } else rt_store128(a, c->r[rt], c->rh[rt]);
}

// ---- unaligned load/store pairs -------------------------------------------------------
static inline void op_lwl(Ctx* c, int rt, u32 a) {
    u32 sh = (a & 3) * 8, m = LD32(a & ~3u);
    u64 v = SX32(((u32)c->r[rt] & (0x00FFFFFFu >> sh)) | (m << (24 - sh)));
    if (rt) c->r[rt] = v;
}
static inline void op_lwr(Ctx* c, int rt, u32 a) {
    u32 sh = (a & 3) * 8, m = LD32(a & ~3u);
    u64 v;
    if (sh == 0) v = SX32(m);
    else {      // only the low bytes change; bits 32-63 are kept
        u64 keep = 0xFFFFFFFF00000000ull | (u32)(0xFFFFFFFFu << (32 - sh));
        v = (c->r[rt] & keep) | (m >> sh);
    }
    if (rt) c->r[rt] = v;
}
static inline void op_swl(Ctx* c, int rt, u32 a) {
    u32 sh = (a & 3) * 8, base = a & ~3u, m = LD32(base), v = (u32)c->r[rt];
    ST32(base, (v >> (24 - sh)) | (m & (u32)(0xFFFFFF00u << sh)));
}
static inline void op_swr(Ctx* c, int rt, u32 a) {
    u32 sh = (a & 3) * 8, base = a & ~3u, m = LD32(base), v = (u32)c->r[rt];
    ST32(base, (u32)(v << sh) | (m & ((1u << sh) - 1)));
}
static inline void op_ldl(Ctx* c, int rt, u32 a) {
    u32 sh = (a & 7) * 8;
    u64 m = LD64(a & ~7u);
    u64 v = (c->r[rt] & (0x00FFFFFFFFFFFFFFull >> sh)) | (m << (56 - sh));
    if (rt) c->r[rt] = v;
}
static inline void op_ldr(Ctx* c, int rt, u32 a) {
    u32 sh = (a & 7) * 8;
    u64 m = LD64(a & ~7u);
    u64 keep = sh ? (~0ull << (64 - sh)) : 0;
    u64 v = (c->r[rt] & keep) | (m >> sh);
    if (rt) c->r[rt] = v;
}
static inline void op_sdl(Ctx* c, int rt, u32 a) {
    u32 sh = (a & 7) * 8, base = a & ~7u;
    u64 m = LD64(base), v = c->r[rt];
    ST64(base, (v >> (56 - sh)) | (m & (0xFFFFFFFFFFFFFF00ull << sh)));
}
static inline void op_sdr(Ctx* c, int rt, u32 a) {
    u32 sh = (a & 7) * 8, base = a & ~7u;
    u64 m = LD64(base), v = c->r[rt];
    ST64(base, (v << sh) | (m & ((1ull << sh) - 1)));
}

// ---- multiply / divide ----------------------------------------------------------------
static inline void op_mult(Ctx* c, int rd, u64 a, u64 b, bool one) {
    s64 p = (s64)(s32)a * (s64)(s32)b;
    u64 lo = SX32((u32)p), hi = SX32((u32)((u64)p >> 32));
    if (one) { c->lo1 = lo; c->hi1 = hi; } else { c->lo = lo; c->hi = hi; }
    if (rd) c->r[rd] = lo;          // R5900: rd also receives LO
}
static inline void op_multu(Ctx* c, int rd, u64 a, u64 b, bool one) {
    u64 p = (u64)(u32)a * (u64)(u32)b;
    u64 lo = SX32((u32)p), hi = SX32((u32)(p >> 32));
    if (one) { c->lo1 = lo; c->hi1 = hi; } else { c->lo = lo; c->hi = hi; }
    if (rd) c->r[rd] = lo;
}
static inline void op_madd(Ctx* c, int rd, u64 a, u64 b, bool is_unsigned) {
    u64 p = is_unsigned ? (u64)(u32)a * (u64)(u32)b : (u64)((s64)(s32)a * (s64)(s32)b);
    u64 t = (((u64)(u32)c->hi << 32) | (u32)c->lo) + p;
    c->lo = SX32((u32)t);
    c->hi = SX32((u32)(t >> 32));
    if (rd) c->r[rd] = c->lo;
}
// Division by zero does not trap on this CPU; the values are the ones the hardware is
// reported to leave (ee_emu.py, div_zero = 'r5900').
static inline void op_div(Ctx* c, u64 ra, u64 rb, bool one) {
    s32 a = (s32)ra, b = (s32)rb;
    u64 lo, hi;
    if (b == 0) { lo = SX32(a < 0 ? 1 : -1); hi = SX32(a); }
    else if (a == INT32_MIN && b == -1) { lo = SX32(0x80000000u); hi = 0; }
    else { lo = SX32(a / b); hi = SX32(a % b); }
    if (one) { c->lo1 = lo; c->hi1 = hi; } else { c->lo = lo; c->hi = hi; }
}
static inline void op_divu(Ctx* c, u64 ra, u64 rb, bool one) {
    u32 a = (u32)ra, b = (u32)rb;
    u64 lo, hi;
    if (b == 0) { lo = ~0ull; hi = SX32(a); }
    else { lo = SX32(a / b); hi = SX32(a % b); }
    if (one) { c->lo1 = lo; c->hi1 = hi; } else { c->lo = lo; c->hi = hi; }
}

#include "fpu.h"
#include "mmi.h"
