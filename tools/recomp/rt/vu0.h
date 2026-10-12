// vu0.h - vector unit 0 as the game uses it: register moves from the main CPU (QMTC2,
// QMFC2, CTC2, CFC2, LQC2, SQC2) and VCALLMS, which runs a microprogram to its end.
//
// The game has one VU0 microprogram (g_vu0PoseProgram, 77 instructions, entered at 2 and
// 4 from anim_buildPose).  The interpreter below implements the instructions that program
// uses plus their obvious relatives, and stops with a message on anything else: nothing
// is guessed.  Arithmetic is the host's single-precision IEEE arithmetic in the rounding
// mode the runtime sets (toward zero), which is what the Play! emulator does for the
// vector units; multiply-add is two operations, not a fused one.  The status/MAC/clip
// flags are not kept (the program has no flag instruction).
#pragma once
#include <cstdio>
#include <cstdlib>

struct Vu0 {
    float vf[32][4];        // x y z w
    u16 vi[16];
    float acc[4];
    float q, i;
    u32 control[32];
    u8 micro[0x1000];       // 0x11000000
    u8 mem[0x1000];         // 0x11004000
    u64 instructions;       // executed, for the report
    u64 calls;
};

static inline u32 vu_raw(float f) { u32 r; memcpy(&r, &f, 4); return r; }
static inline float vu_flt(u32 r) { float f; memcpy(&f, &r, 4); return f; }

[[noreturn]] static void vu_die(const char* what, u32 pc, u32 word) {
    fprintf(stderr, "VU0: %s not implemented (micro address 0x%03x, word %08x)\n", what, pc, word);
    exit(3);
}

// arithmetic whose result depends on the processor's state: the host's own (the runtime
// sets toward zero and flush-to-zero), or tools/recomp/web/soft_rz.h on a host that
// cannot (fpu.h says more)
#ifdef RTA_SOFT_RZ
static inline float vu_add(float a, float b) { return softrz::add_fz(a, b); }
static inline float vu_sub(float a, float b) { return softrz::sub_fz(a, b); }
static inline float vu_mul(float a, float b) { return softrz::mul_fz(a, b); }
static inline float vu_itof(s32 v) { return softrz::from_int(v); }
static inline bool vu_gt(float a, float b) { return softrz::flush(a) > softrz::flush(b); }  // the compare reads tiny numbers as zero
#else
static inline float vu_add(float a, float b) { return a + b; }
static inline float vu_sub(float a, float b) { return a - b; }
static inline float vu_mul(float a, float b) { return a * b; }
static inline float vu_itof(s32 v) { return (float)v; }
static inline bool vu_gt(float a, float b) { return a > b; }
#endif

static inline float vu_ftoi(float f, float scale) {
    float v = vu_mul(f, scale);
    s32 r;
    if (v != v) r = 0;
    else if (v >= 2147483648.0f) r = INT32_MAX;
    else if (v <= -2147483648.0f) r = INT32_MIN;
    else r = (s32)v;                 // truncates
    return vu_flt((u32)r);
}

static void vu0_run(Vu0& v, u32 pc) {
    v.calls++;
    bool ending = false, in_delay = false;
    u32 branch_target = 0;
    for (int guard = 0; guard < 100000; guard++) {
        pc &= 0x1FF;
        u32 lower, upper;
        memcpy(&lower, v.micro + pc * 8, 4);
        memcpy(&upper, v.micro + pc * 8 + 4, 4);
        v.instructions++;
        bool last = ending;
        if (upper & 0x40000000u) ending = true;         // E: stop after the next instruction
        float old[32][4];
        memcpy(old, v.vf, sizeof(old));
        u16 old_vi[16];
        memcpy(old_vi, v.vi, sizeof(old_vi));

        // ---- upper instruction ----
        u32 dest = (upper >> 21) & 15;                  // x=8 y=4 z=2 w=1
        u32 ft = (upper >> 16) & 31, fs = (upper >> 11) & 31, fd = (upper >> 6) & 31, bc = upper & 3;
        u32 op = upper & 63;
        auto on = [&](int k) { return (dest >> (3 - k)) & 1; };
        auto put = [&](u32 reg, int k, float value) { if (reg != 0 && on(k)) v.vf[reg][k] = value; };
        if (op >= 0x3C) {
            u32 idx = (((upper >> 6) & 31) << 2) | (upper & 3);
            if (idx <= 0x0F || (idx >= 0x18 && idx <= 0x1B)) {
                // ADDAbc SUBAbc MADDAbc MSUBAbc MULAbc
                float b = old[ft][idx & 3];
                for (int k = 0; k < 4; k++) {
                    if (!on(k)) continue;
                    float a = old[fs][k];
                    if (idx <= 0x03) v.acc[k] = vu_add(a, b);
                    else if (idx <= 0x07) v.acc[k] = vu_sub(a, b);
                    else if (idx <= 0x0B) { float p = vu_mul(a, b); v.acc[k] = vu_add(v.acc[k], p); }
                    else if (idx <= 0x0F) { float p = vu_mul(a, b); v.acc[k] = vu_sub(v.acc[k], p); }
                    else v.acc[k] = vu_mul(a, b);
                }
            } else if (idx >= 0x10 && idx <= 0x13) {    // ITOF0/4/12/15: ft <- fs
                static const float scale[4] = {1.0f, 1.0f / 16.0f, 1.0f / 4096.0f, 1.0f / 32768.0f};
                for (int k = 0; k < 4; k++) {
                    float f = vu_itof((s32)vu_raw(old[fs][k]));
                    put(ft, k, idx == 0x10 ? f : vu_mul(f, scale[idx & 3]));
                }
            } else if (idx >= 0x14 && idx <= 0x17) {    // FTOI0/4/12/15
                static const float scale[4] = {1.0f, 16.0f, 4096.0f, 32768.0f};
                for (int k = 0; k < 4; k++) put(ft, k, vu_ftoi(old[fs][k], scale[idx & 3]));
            } else if (idx == 0x1E) {                   // MULAi
                for (int k = 0; k < 4; k++) if (on(k)) v.acc[k] = vu_mul(old[fs][k], v.i);
            } else if (idx == 0x28 || idx == 0x2A || idx == 0x2C || idx == 0x29 || idx == 0x2D) {
                for (int k = 0; k < 4; k++) {           // ADDA MULA SUBA MADDA MSUBA
                    if (!on(k)) continue;
                    float a = old[fs][k], b = old[ft][k];
                    if (idx == 0x28) v.acc[k] = vu_add(a, b);
                    else if (idx == 0x2C) v.acc[k] = vu_sub(a, b);
                    else if (idx == 0x2A) v.acc[k] = vu_mul(a, b);
                    else if (idx == 0x29) { float p = vu_mul(a, b); v.acc[k] = vu_add(v.acc[k], p); }
                    else { float p = vu_mul(a, b); v.acc[k] = vu_sub(v.acc[k], p); }
                }
            } else if (idx == 0x1D) {                   // ABS
                for (int k = 0; k < 4; k++) put(ft, k, vu_flt(vu_raw(old[fs][k]) & 0x7FFFFFFFu));
            } else if (idx == 0x2F || idx == 0x30) {    // NOP
            } else vu_die("upper special instruction", pc, upper);
        } else if (op <= 0x1B && !(op >= 0x10 && op <= 0x17)) {
            // ADDbc SUBbc MADDbc MSUBbc MULbc
            float b = old[ft][bc];
            for (int k = 0; k < 4; k++) {
                float a = old[fs][k], r;
                if (op <= 0x03) r = vu_add(a, b);
                else if (op <= 0x07) r = vu_sub(a, b);
                else if (op <= 0x0B) { float p = vu_mul(a, b); r = vu_add(v.acc[k], p); }
                else if (op <= 0x0F) { float p = vu_mul(a, b); r = vu_sub(v.acc[k], p); }
                else r = vu_mul(a, b);
                put(fd, k, r);
            }
        } else if (op >= 0x10 && op <= 0x17) {          // MAXbc MINIbc
            float b = old[ft][bc];
            for (int k = 0; k < 4; k++) {
                float a = old[fs][k];
                put(fd, k, op <= 0x13 ? (vu_gt(a, b) ? a : b) : (vu_gt(b, a) ? a : b));
            }
        } else if (op == 0x1E || op == 0x22 || op == 0x26 || op == 0x23 || op == 0x27) {
            for (int k = 0; k < 4; k++) {               // MULi ADDi SUBi MADDi MSUBi
                float a = old[fs][k], r;
                if (op == 0x1E) r = vu_mul(a, v.i);
                else if (op == 0x22) r = vu_add(a, v.i);
                else if (op == 0x26) r = vu_sub(a, v.i);
                else if (op == 0x23) { float p = vu_mul(a, v.i); r = vu_add(v.acc[k], p); }
                else { float p = vu_mul(a, v.i); r = vu_sub(v.acc[k], p); }
                put(fd, k, r);
            }
        } else if (op == 0x28 || op == 0x2A || op == 0x2C || op == 0x29 || op == 0x2D || op == 0x2B || op == 0x2F) {
            for (int k = 0; k < 4; k++) {               // ADD MUL SUB MADD MSUB MAX MINI
                float a = old[fs][k], b = old[ft][k], r;
                if (op == 0x28) r = vu_add(a, b);
                else if (op == 0x2C) r = vu_sub(a, b);
                else if (op == 0x2A) r = vu_mul(a, b);
                else if (op == 0x29) { float p = vu_mul(a, b); r = vu_add(v.acc[k], p); }
                else if (op == 0x2D) { float p = vu_mul(a, b); r = vu_sub(v.acc[k], p); }
                else if (op == 0x2B) r = vu_gt(a, b) ? a : b;
                else r = vu_gt(b, a) ? a : b;
                put(fd, k, r);
            }
        } else vu_die("upper instruction", pc, upper);

        // ---- lower instruction (reads the state from before the upper one) ----
        bool branch = false;
        u32 target = 0;
        if (upper & 0x80000000u) {
            v.i = vu_flt(lower);                        // I bit: the lower word is a constant
        } else if (lower != 0x8000033Cu) {
            u32 lop = lower >> 25;
            u32 lt = (lower >> 16) & 31, ls = (lower >> 11) & 31, ldest = (lower >> 21) & 15;
            s32 imm11 = (s32)(lower << 21) >> 21;
            auto lon = [&](int k) { return (ldest >> (3 - k)) & 1; };
            if (lop == 0x00) {                          // LQ ft, imm(is)
                u32 addr = ((u32)(old_vi[ls & 15] + imm11) * 16) & 0xFF0;
                for (int k = 0; k < 4; k++)
                    if (lt != 0 && lon(k)) memcpy(&v.vf[lt][k], v.mem + addr + k * 4, 4);
            } else if (lop == 0x01) {                   // SQ fs, imm(it)
                u32 addr = ((u32)(old_vi[lt & 15] + imm11) * 16) & 0xFF0;
                for (int k = 0; k < 4; k++)
                    if (lon(k)) memcpy(v.mem + addr + k * 4, &old[ls][k], 4);
            } else if (lop == 0x20) {                   // B
                branch = true;
                target = (pc + 1 + imm11) & 0x1FF;
            } else if (lop == 0x40 && (lower & 63) == 0x3D && ((lower >> 6) & 31) == 0x0C) {
                // MR32 ft, fs: (x, y, z, w) <- (y, z, w, x)
                for (int k = 0; k < 4; k++)
                    if (lt != 0 && lon(k)) v.vf[lt][k] = old[ls][(k + 1) & 3];
            } else if (lop == 0x40 && (lower & 63) == 0x3C && ((lower >> 6) & 31) == 0x0C) {
                for (int k = 0; k < 4; k++)             // MOVE ft, fs
                    if (lt != 0 && lon(k)) v.vf[lt][k] = old[ls][k];
            } else vu_die("lower instruction", pc, lower);
        }
        v.vf[0][0] = v.vf[0][1] = v.vf[0][2] = 0.0f;
        v.vf[0][3] = 1.0f;
        v.vi[0] = 0;

        if (last) return;
        if (in_delay) { pc = branch_target; in_delay = false; }
        else pc = pc + 1;
        if (branch) { in_delay = true; branch_target = target; }
    }
    vu_die("endless microprogram", pc, 0);
}
