// arith_main.cpp - runs single translated instructions, and single vector-unit
// instructions, on files of operand sets.  The other half is tools/recomp/proof/arith.py,
// which writes the operands, generates arith_gen.cpp (one C++ function per instruction,
// its body being exactly what tools/recomp/recomp.py emits for that instruction word) and
// compares the results with the interpreter and with softf.py.
//
//   arith_bin F <op> <in> <out> [fz]   FPU instruction <op> of the generated table
//                                      in: f1 f2 acc (u32)      out: f3 acc compare-bit (u32)
//   arith_bin M <op> <in> <out>        integer / multimedia instruction
//                                      in: r1 lo,hi r2 lo,hi hi lo hi1 lo1 sa (u64)
//                                      out: r3 lo,hi hi lo hi1 lo1 (u64)
//   arith_bin V <upper word, hex> <in> <out> [fz]
//                                      one upper instruction of vector unit 0 (vu0.h), with
//                                      fs = vf1, ft = vf2, fd = vf3 as the word names them
//                                      in: vf1 vf2 acc (4 x u32 each) i   out: vf3 acc
//
// Built twice: with -DFPU_PS2 (the model the differential test uses) and without (the
// model the runtime uses).  "fz" sets the CPU's flush-to-zero mode (ARM64 FPCR.FZ; on
// x86-64 the two MXCSR bits), which the Play! emulator runs the game with; the rounding
// mode is toward zero, as the runtime sets it.
#include "recomp.h"
#include "vu0.h"

#include <cfenv>
#include <cstdio>
#include <cstdlib>
#include <vector>
#if defined(__x86_64__)
#include <xmmintrin.h>
#include <pmmintrin.h>
#endif

u8* g_ram;
u32 g_site;
u64 rt_load(u32, unsigned) { return 0; }
void rt_store(u32, unsigned, u64) {}
void rt_load128(u32, u64*, u64*) {}
void rt_store128(u32, u64, u64) {}
void rt_call(Ctx*, u32) {}
void rt_syscall(Ctx*, u32) {}
void rt_break(Ctx*, u32, u32) {}
void rt_trap(Ctx*, u32, const char*) {}
void rt_unimpl(Ctx*, u32, u32) {}
void rt_cop2(Ctx*, u32, u32) {}
u32 rt_mfc0(Ctx*, u32, unsigned) { return 0; }
void rt_mtc0(Ctx*, u32, unsigned, u32) {}
void rt_eret(Ctx*, u32) {}
void rt_poll(Ctx*) {}

extern void (*const g_arith_ops[])(Ctx*);
extern const unsigned g_arith_count;

static std::vector<u8> slurp(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "cannot read %s\n", path); exit(2); }
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    std::vector<u8> d(size);
    if (fread(d.data(), 1, size, f) != (size_t)size) exit(2);
    fclose(f);
    return d;
}

int main(int argc, char** argv) {
    if (argc < 5) { fprintf(stderr, "usage: arith_bin F|M|V <op> <in> <out> [fz]\n"); return 2; }
    fesetround(FE_TOWARDZERO);
    if (argc > 5 && !strcmp(argv[5], "fz")) {
#if defined(__aarch64__)
        u64 fpcr;
        __asm__ __volatile__("mrs %0, fpcr" : "=r"(fpcr));
        fpcr |= 1ull << 24;
        __asm__ __volatile__("msr fpcr, %0" : : "r"(fpcr));
#elif defined(__x86_64__)
        _MM_SET_DENORMALS_ZERO_MODE(_MM_DENORMALS_ZERO_ON);
        _MM_SET_FLUSH_ZERO_MODE(_MM_FLUSH_ZERO_ON);
#endif
    }
    char kind = argv[1][0];
    std::vector<u8> in = slurp(argv[3]);
    FILE* out = fopen(argv[4], "wb");
    if (!out) { fprintf(stderr, "cannot write %s\n", argv[4]); return 2; }
    static Ctx ctx;
    Ctx* c = &ctx;
    if (kind == 'F') {
        unsigned op = (unsigned)atoi(argv[2]);
        if (op >= g_arith_count) return 2;
        size_t n = in.size() / 12;
        std::vector<u32> res(n * 3);
        const u32* p = (const u32*)in.data();
        for (size_t i = 0; i < n; i++) {
            c->f[1] = p[i * 3]; c->f[2] = p[i * 3 + 1]; c->acc = p[i * 3 + 2];
            c->f[3] = 0xDEADBEEFu;
            c->fcr31 = 0x01000001u;
            g_arith_ops[op](c);
            res[i * 3] = c->f[3]; res[i * 3 + 1] = c->acc; res[i * 3 + 2] = (c->fcr31 >> 23) & 1;
        }
        fwrite(res.data(), 4, res.size(), out);
    } else if (kind == 'M') {
        unsigned op = (unsigned)atoi(argv[2]);
        if (op >= g_arith_count) return 2;
        size_t n = in.size() / 72;
        std::vector<u64> res(n * 6);
        const u64* p = (const u64*)in.data();
        for (size_t i = 0; i < n; i++) {
            const u64* q = p + i * 9;
            c->r[1] = q[0]; c->rh[1] = q[1]; c->r[2] = q[2]; c->rh[2] = q[3];
            c->hi = q[4]; c->lo = q[5]; c->hi1 = q[6]; c->lo1 = q[7]; c->sa = (u32)q[8];
            c->r[3] = 0x0123456789ABCDEFull; c->rh[3] = 0xFEDCBA9876543210ull;
            g_arith_ops[op](c);
            u64* r = res.data() + i * 6;
            r[0] = c->r[3]; r[1] = c->rh[3]; r[2] = c->hi; r[3] = c->lo; r[4] = c->hi1; r[5] = c->lo1;
        }
        fwrite(res.data(), 8, res.size(), out);
    } else if (kind == 'V') {
        u32 upper = (u32)strtoul(argv[2], nullptr, 16);
        static Vu0 v;
        size_t n = in.size() / 52;
        std::vector<u32> res(n * 8);
        const u32* p = (const u32*)in.data();
        u32 nop_lower = 0x8000033Cu, nop_upper = 0x000002FFu, first = upper | 0x40000000u;
        memcpy(v.micro, &nop_lower, 4); memcpy(v.micro + 4, &first, 4);
        memcpy(v.micro + 8, &nop_lower, 4); memcpy(v.micro + 12, &nop_upper, 4);
        for (size_t i = 0; i < n; i++) {
            const u32* q = p + i * 13;
            for (int k = 0; k < 4; k++) {
                v.vf[1][k] = vu_flt(q[k]); v.vf[2][k] = vu_flt(q[4 + k]); v.acc[k] = vu_flt(q[8 + k]);
                v.vf[3][k] = vu_flt(0xDEADBEEFu);
            }
            v.i = vu_flt(q[12]);
            vu0_run(v, 0);
            for (int k = 0; k < 4; k++) { res[i * 8 + k] = vu_raw(v.vf[3][k]); res[i * 8 + 4 + k] = vu_raw(v.acc[k]); }
        }
        fwrite(res.data(), 4, res.size(), out);
    } else return 2;
    fclose(out);
    return 0;
}
