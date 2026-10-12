// vu1_step.h - one instruction pair of VU1, as a function that is always inlined.
//
// The interpreter (vu1.cpp) calls it with the pair it decoded.  The translation of the
// main program (written by Vu1::write_translation, compiled from local/recomp-out/) calls
// it with every pair as a compile-time constant, so the compiler folds the decoding away
// and what is left is the pair's arithmetic: one description of the machine for both.
// It does everything of a cycle except deciding where to go next: returns whether the
// lower half is a taken branch, and to where.
#pragma once
#include "vu1.h"

#include <cfenv>
#include <cmath>
#include <cstdio>
#include <cstring>

namespace render {

enum { U_NOP, U_ADD, U_SUB, U_MUL, U_MADD, U_MSUB, U_MAX, U_MINI, U_ITOF, U_FTOI, U_CLIP, U_ABS, U_BAD };
enum { S_VEC, S_BC, S_Q, S_I };
enum { L_NOP, L_LQ, L_SQ, L_ILW, L_ISW, L_IADDIU, L_ISUBIU, L_FCEQ, L_FCSET, L_FCAND, L_FCOR, L_FSEQ, L_FSSET,
       L_FSAND, L_FSOR, L_FMEQ, L_FMAND, L_FMOR, L_FCGET, L_B, L_BAL, L_JR, L_JALR, L_IBEQ, L_IBNE, L_IBLTZ,
       L_IBGTZ, L_IBLEZ, L_IBGEZ, L_IADD, L_ISUB, L_IADDI, L_IAND, L_IOR, L_MOVE, L_MR32, L_LQI, L_SQI, L_LQD,
       L_SQD, L_DIV, L_SQRT, L_RSQRT, L_WAITQ, L_MTIR, L_MFIR, L_ILWR, L_ISWR, L_XTOP, L_XITOP, L_XGKICK, L_BAD };

#if defined(__GNUC__) || defined(__clang__)
#define VU1_INLINE inline __attribute__((always_inline))
#else
#define VU1_INLINE inline
#endif

// The unit's numbers.  An exponent of 255 is an ordinary exponent - there are no
// infinities and no NaNs - and an exponent of 0 is zero whatever the fraction says.  The
// game relies on it: registers and data memory hold integers and stale data of other
// drawers (a pose is blended as `new * 1 + old * 0` over whatever the slot held before,
// 16-bit trail points for instance, whose bit patterns are NaNs to the host; with host
// arithmetic the joint matrix became NaN and its vertices went to a far corner).  So what
// an arithmetic instruction reads is brought into the host's range first (the largest
// number for exponent 255, as other emulators do), and a result too small to be a number
// is zero.  Results cannot overflow: the unit rounds toward zero, and so does the host
// while a program runs.
static VU1_INLINE float vu_in(uint32_t u) {
#ifdef VU1_HOST_NUMBERS
    { float h; memcpy(&h, &u, 4); return h; }
#endif
    uint32_t e = u & 0x7F800000u;
    u = e == 0x7F800000u ? ((u & 0x80000000u) | 0x7F7FFFFFu) : e == 0 ? (u & 0x80000000u) : u;
    float f;
    memcpy(&f, &u, 4);
    return f;
}
static VU1_INLINE float vu_out(float f) {
#ifdef VU1_HOST_NUMBERS
    return f;
#endif
    uint32_t u;
    memcpy(&u, &f, 4);
    if ((u & 0x7F800000u) == 0) { u &= 0x80000000u; memcpy(&f, &u, 4); }
    return f;
}
// MAX and MINI compare the bit patterns as sign and magnitude and hand one of them on
// unchanged (integers kept in float registers go through them)
static VU1_INLINE int32_t vu_key(uint32_t u) { return (u & 0x80000000u) ? -(int32_t)(u & 0x7FFFFFFFu) : (int32_t)u; }

// The operations whose result depends on the rounding mode.  The unit rounds toward zero
// and the programs count on it (integers made by adding 2^23 to a float).  A host with
// rounding modes is put in that mode while a program runs (Vu1::run) and these are its own
// instructions.  WebAssembly has one mode, to nearest: built with RTA_SOFT_RZ_VU1 the same
// results are worked out in double precision and cut to 24 bits (tools/recomp/web/soft_rz.h
// has the reasoning; here the unit's own rules shorten it: operands are never infinite, a
// result too small to be a number is zero, one too large is the largest).
#if defined(RTA_SOFT_RZ_VU1)
#include "soft_rz.h"
static VU1_INLINE float vu_cut(double d) {              // a double as a float, toward zero
    uint64_t u;
    memcpy(&u, &d, 8);
    uint64_t magnitude = u & 0x7FFFFFFFFFFFFFFFull;
    if (magnitude < 0x3810000000000000ull) u &= 0x8000000000000000ull;             // below 2^-126: zero
    else if (magnitude >= 0x47F0000000000000ull) u = (u & 0x8000000000000000ull) | 0x47EFFFFFE0000000ull;    // 2^128 and up: the largest
    else u &= ~0x1FFFFFFFull;                           // 53 - 24 places
    memcpy(&d, &u, 8);
    return (float)d;                                    // exact now
}
static VU1_INLINE float vu_add(float a, float b) {
    double x = a, y = b, d = x + y;
    // exact unless one operand vanished in the other (more than 29 places apart): then the
    // sum is that operand, or - with opposite signs - the number just below it
    if (d == x && b != 0) { if ((a < 0) != (b < 0)) { uint32_t u; memcpy(&u, &a, 4); u--; memcpy(&a, &u, 4); } return a; }
    if (d == y && a != 0) { if ((a < 0) != (b < 0)) { uint32_t u; memcpy(&u, &b, 4); u--; memcpy(&b, &u, 4); } return b; }
    return vu_cut(d);
}
static VU1_INLINE float vu_sub(float a, float b) { return vu_add(a, -b); }
static VU1_INLINE float vu_mul(float a, float b) { return vu_cut((double)a * (double)b); }      // the product is exact in a double
static VU1_INLINE float vu_div(float a, float b) { return softrz::div(a, b); }
static VU1_INLINE float vu_sqrt(float a) { return softrz::sqrt(a); }
static VU1_INLINE float vu_itof(int32_t v) { return softrz::from_int(v); }
#define VU1_ROUND_TOWARD_ZERO() ((void)0)
#define VU1_ROUND_RESTORE(mode) ((void)(mode))
#else
static VU1_INLINE float vu_add(float a, float b) { return a + b; }
static VU1_INLINE float vu_sub(float a, float b) { return a - b; }
static VU1_INLINE float vu_mul(float a, float b) { return a * b; }
static VU1_INLINE float vu_div(float a, float b) { return a / b; }
static VU1_INLINE float vu_sqrt(float a) { return sqrtf(a); }
static VU1_INLINE float vu_itof(int32_t v) { return (float)v; }
#define VU1_ROUND_TOWARD_ZERO() fesetround(FE_TOWARDZERO)
#define VU1_ROUND_RESTORE(mode) fesetround(mode)
#endif

static VU1_INLINE bool vu1_step(Vu1& v, const Vu1::Ins& d, uint32_t at, uint32_t& dest, int old_round) {
    if (v.q_busy && v.cyc >= v.q_ready) { v.q = v.q_next; v.q_busy = false; }
    // ---- upper half, computed from the state before the pair ----
    // (that includes I: a pair with the I bit loads its constant after its own upper
    // half has read the old one - the programs use `ADDi ... | LOI next` on purpose)
    Vu1::Reg result;
    int write = 0;                                  // 1: a register, 2: the accumulator
    unsigned target = 0;
    if (d.uop != U_NOP) {
        const Vu1::Reg& fs = v.vf[d.ufs];
        const Vu1::Reg& ft = v.vf[d.uft];
        Vu1::Reg bb;                                    // the second operand as it is
        switch (d.usrc) {
        case S_VEC: bb = ft; break;
        case S_BC: bb.u[0] = bb.u[1] = bb.u[2] = bb.u[3] = ft.u[d.ubc]; break;
        case S_Q: bb.f[0] = bb.f[1] = bb.f[2] = bb.f[3] = v.q; break;
        default: bb.f[0] = bb.f[1] = bb.f[2] = bb.f[3] = v.i_reg; break;
        }
        float a[4], b[4];                               // both as the numbers the unit computes with
        if (d.uop <= U_MSUB) for (int k = 0; k < 4; k++) { a[k] = vu_in(fs.u[k]); b[k] = vu_in(bb.u[k]); }
        Vu1::Reg r;
        bool arithmetic = false;
        switch (d.uop) {
        case U_ADD: for (int k = 0; k < 4; k++) r.f[k] = vu_out(vu_add(a[k], b[k])); arithmetic = true; break;
        case U_SUB: for (int k = 0; k < 4; k++) r.f[k] = vu_out(vu_sub(a[k], b[k])); arithmetic = true; break;
        case U_MUL: for (int k = 0; k < 4; k++) r.f[k] = vu_out(vu_mul(a[k], b[k])); arithmetic = true; break;
        case U_MADD: { float p[4]; for (int k = 0; k < 4; k++) p[k] = vu_out(vu_mul(a[k], b[k])); for (int k = 0; k < 4; k++) r.f[k] = vu_out(vu_add(v.acc.f[k], p[k])); arithmetic = true; break; }
        case U_MSUB: { float p[4]; for (int k = 0; k < 4; k++) p[k] = vu_out(vu_mul(a[k], b[k])); for (int k = 0; k < 4; k++) r.f[k] = vu_out(vu_sub(v.acc.f[k], p[k])); arithmetic = true; break; }
        case U_MAX: for (int k = 0; k < 4; k++) r.u[k] = vu_key(fs.u[k]) > vu_key(bb.u[k]) ? fs.u[k] : bb.u[k]; break;
        case U_MINI: for (int k = 0; k < 4; k++) r.u[k] = vu_key(fs.u[k]) < vu_key(bb.u[k]) ? fs.u[k] : bb.u[k]; break;
        case U_ITOF: { float scale = 1.0f / (float)(1u << d.ubc); for (int k = 0; k < 4; k++) r.f[k] = vu_mul(vu_itof(fs.s[k]), scale); break; }
        case U_FTOI: {
            float scale = (float)(1u << d.ubc);
            for (int k = 0; k < 4; k++) {
                float scaled = vu_mul(vu_in(fs.u[k]), scale);
                r.s[k] = scaled >= 2147483648.0f ? 0x7FFFFFFF : scaled <= -2147483648.0f ? (int32_t)0x80000000 : (int32_t)scaled;
            }
            break;
        }
        case U_ABS: for (int k = 0; k < 4; k++) r.u[k] = fs.u[k] & 0x7FFFFFFF; break;
        case U_CLIP: {
            float w = fabsf(vu_in(ft.u[3])), x = vu_in(fs.u[0]), y = vu_in(fs.u[1]), z = vu_in(fs.u[2]);
            uint32_t c = 0;
            if (x > w) c |= 1;  if (x < -w) c |= 2;
            if (y > w) c |= 4;  if (y < -w) c |= 8;
            if (z > w) c |= 16; if (z < -w) c |= 32;
            v.clip_now = ((v.clip_now << 6) | c) & 0xFFFFFF;
            v.clip_ring[v.clip_count++ & 7] = {v.cyc, v.clip_now};
            break;
        }
        default:
            if (!v.bad++) fprintf(stderr, "vu1: upper instruction not implemented at 0x%x\n", at);
            break;
        }
        if (d.uop <= U_ABS && d.uop != U_CLIP) {
            bool to_acc = d.udst && d.uop <= U_MSUB;
            target = (d.uop == U_ITOF || d.uop == U_FTOI || d.uop == U_ABS) ? d.uft : d.ufd;
            const Vu1::Reg& old = to_acc ? v.acc : v.vf[target];
            for (int k = 0; k < 4; k++) result.u[k] = (r.u[k] & d.umask[k]) | (old.u[k] & ~d.umask[k]);
            write = to_acc ? 2 : 1;
            if (arithmetic) v.flag_ring[v.flag_count++ & 7] = {v.cyc, r, d.udest};
        }
    }
    // ---- lower half ----
    bool taken = false;
    switch (d.lop) {
    case L_NOP: break;
    case L_LQ: { const uint8_t* m = v.data + (((uint32_t)v.vi[d.ls] + d.imm11) & 0x3FF) * 16; if (d.lt) { if (d.ldest == 15) memcpy(&v.vf[d.lt], m, 16); else for (int k = 0; k < 4; k++) if (d.ldest & (8 >> k)) memcpy(&v.vf[d.lt].u[k], m + k * 4, 4); } break; }
    case L_SQ: { uint8_t* m = v.data + (((uint32_t)v.vi[d.lt] + d.imm11) & 0x3FF) * 16; if (d.ldest == 15) memcpy(m, &v.vf[d.ls], 16); else for (int k = 0; k < 4; k++) if (d.ldest & (8 >> k)) memcpy(m + k * 4, &v.vf[d.ls].u[k], 4); break; }
    case L_LQI: { const uint8_t* m = v.data + (v.vi[d.ls] & 0x3FF) * 16; if (d.lt) { if (d.ldest == 15) memcpy(&v.vf[d.lt], m, 16); else for (int k = 0; k < 4; k++) if (d.ldest & (8 >> k)) memcpy(&v.vf[d.lt].u[k], m + k * 4, 4); } if (d.ls) v.vi[d.ls]++; break; }
    case L_SQI: { uint8_t* m = v.data + (v.vi[d.lt] & 0x3FF) * 16; if (d.ldest == 15) memcpy(m, &v.vf[d.ls], 16); else for (int k = 0; k < 4; k++) if (d.ldest & (8 >> k)) memcpy(m + k * 4, &v.vf[d.ls].u[k], 4); if (d.lt) v.vi[d.lt]++; break; }
    case L_LQD: { if (d.ls) v.vi[d.ls]--; const uint8_t* m = v.data + (v.vi[d.ls] & 0x3FF) * 16; if (d.lt) for (int k = 0; k < 4; k++) if (d.ldest & (8 >> k)) memcpy(&v.vf[d.lt].u[k], m + k * 4, 4); break; }
    case L_SQD: { if (d.lt) v.vi[d.lt]--; uint8_t* m = v.data + (v.vi[d.lt] & 0x3FF) * 16; for (int k = 0; k < 4; k++) if (d.ldest & (8 >> k)) memcpy(m + k * 4, &v.vf[d.ls].u[k], 4); break; }
    case L_ILW: { const uint8_t* m = v.data + (((uint32_t)v.vi[d.ls] + d.imm11) & 0x3FF) * 16; for (int k = 0; k < 4; k++) if (d.ldest & (8 >> k)) { uint16_t value; memcpy(&value, m + k * 4, 2); if (d.lt) v.vi[d.lt] = value; break; } break; }
    case L_ISW: { uint8_t* m = v.data + (((uint32_t)v.vi[d.ls] + d.imm11) & 0x3FF) * 16; uint32_t value = v.vi[d.lt]; for (int k = 0; k < 4; k++) if (d.ldest & (8 >> k)) memcpy(m + k * 4, &value, 4); break; }
    case L_ILWR: { const uint8_t* m = v.data + (v.vi[d.ls] & 0x3FF) * 16; for (int k = 0; k < 4; k++) if (d.ldest & (8 >> k)) { uint16_t value; memcpy(&value, m + k * 4, 2); if (d.lt) v.vi[d.lt] = value; break; } break; }
    case L_ISWR: { uint8_t* m = v.data + (v.vi[d.ls] & 0x3FF) * 16; uint32_t value = v.vi[d.lt]; for (int k = 0; k < 4; k++) if (d.ldest & (8 >> k)) memcpy(m + k * 4, &value, 4); break; }
    case L_IADDIU: if (d.lt) v.vi[d.lt] = (uint16_t)(v.vi[d.ls] + d.imm15); break;
    case L_ISUBIU: if (d.lt) v.vi[d.lt] = (uint16_t)(v.vi[d.ls] - d.imm15); break;
    case L_IADD: if (d.ld) v.vi[d.ld] = (uint16_t)(v.vi[d.ls] + v.vi[d.lt]); break;
    case L_ISUB: if (d.ld) v.vi[d.ld] = (uint16_t)(v.vi[d.ls] - v.vi[d.lt]); break;
    case L_IAND: if (d.ld) v.vi[d.ld] = v.vi[d.ls] & v.vi[d.lt]; break;
    case L_IOR: if (d.ld) v.vi[d.ld] = v.vi[d.ls] | v.vi[d.lt]; break;
    case L_IADDI: { int imm5 = d.ld & 16 ? (int)d.ld - 32 : d.ld; if (d.lt) v.vi[d.lt] = (uint16_t)(v.vi[d.ls] + imm5); break; }
    case L_FCSET: v.clip_now = d.imm24; v.clip_ring[v.clip_count++ & 7] = {v.cyc, v.clip_now}; break;
    case L_FCAND: v.vi[1] = (v.clip_seen() & d.imm24) ? 1 : 0; break;
    case L_FCOR: v.vi[1] = ((v.clip_seen() | d.imm24) & 0xFFFFFF) == 0xFFFFFF ? 1 : 0; break;
    case L_FCEQ: v.vi[1] = (v.clip_seen() & 0xFFFFFF) == d.imm24 ? 1 : 0; break;
    case L_FCGET: if (d.lt) v.vi[d.lt] = v.clip_seen() & 0xFFF; break;
    // status flag: zero and sign of the same result; the sticky bits are not kept (the
    // programs test 0x001 and 0x002 only)
    case L_FSAND: case L_FSOR: case L_FSEQ: {
        uint32_t mac = v.mac_seen(), status = (mac & 0x000F ? 1u : 0u) | (mac & 0x00F0 ? 2u : 0u);
        uint32_t imm = ((d.lower >> 10) & 0x800) | (d.lower & 0x7FF);
        if (d.lt) v.vi[d.lt] = d.lop == L_FSAND ? (status & imm) : d.lop == L_FSOR ? ((status | imm) & 0xFFF) : ((status == imm) ? 1 : 0);
        break;
    }
    case L_FSSET: break;
    case L_FMAND: if (d.lt) v.vi[d.lt] = v.mac_seen() & v.vi[d.ls]; break;
    case L_FMOR: if (d.lt) v.vi[d.lt] = (v.mac_seen() | v.vi[d.ls]) & 0xFFFF; break;
    case L_FMEQ: if (d.lt) v.vi[d.lt] = (v.mac_seen() & 0xFFFF) == v.vi[d.ls] ? 1 : 0; break;
    case L_B: taken = true; dest = at + 1 + d.imm11; break;
    case L_BAL: taken = true; dest = at + 1 + d.imm11; if (d.lt) v.vi[d.lt] = (uint16_t)(at + 2); break;
    case L_JR: taken = true; dest = v.vi[d.ls]; break;
    case L_JALR: taken = true; dest = v.vi[d.ls]; if (d.lt) v.vi[d.lt] = (uint16_t)(at + 2); break;
    case L_IBEQ: taken = v.vi[d.lt] == v.vi[d.ls]; dest = at + 1 + d.imm11; break;
    case L_IBNE: taken = v.vi[d.lt] != v.vi[d.ls]; dest = at + 1 + d.imm11; break;
    case L_IBLTZ: taken = (int16_t)v.vi[d.ls] < 0; dest = at + 1 + d.imm11; break;
    case L_IBGTZ: taken = (int16_t)v.vi[d.ls] > 0; dest = at + 1 + d.imm11; break;
    case L_IBLEZ: taken = (int16_t)v.vi[d.ls] <= 0; dest = at + 1 + d.imm11; break;
    case L_IBGEZ: taken = (int16_t)v.vi[d.ls] >= 0; dest = at + 1 + d.imm11; break;
    case L_MOVE: if (d.lt) for (int k = 0; k < 4; k++) if (d.ldest & (8 >> k)) v.vf[d.lt].u[k] = v.vf[d.ls].u[k]; break;
    case L_MR32: if (d.lt) { Vu1::Reg s = v.vf[d.ls]; for (int k = 0; k < 4; k++) if (d.ldest & (8 >> k)) v.vf[d.lt].u[k] = s.u[(k + 1) & 3]; } break;
    case L_MTIR: if (d.lt) v.vi[d.lt] = (uint16_t)v.vf[d.ls].u[d.fsf]; break;
    case L_MFIR: if (d.lt) for (int k = 0; k < 4; k++) if (d.ldest & (8 >> k)) v.vf[d.lt].s[k] = (int16_t)v.vi[d.ls]; break;
    case L_XTOP: if (d.lt) v.vi[d.lt] = (uint16_t)v.top; break;
    case L_XITOP: if (d.lt) v.vi[d.lt] = (uint16_t)(v.itop & 0x3FF); break;
    case L_DIV: case L_SQRT: case L_RSQRT: {
        // a divide still in flight is waited for
        if (v.q_busy) { if (v.q_ready > v.cyc) v.cyc = v.q_ready; v.q = v.q_next; v.q_busy = false; }
        float a = vu_in(v.vf[d.ls].u[d.fsf]), b = vu_in(v.vf[d.lt].u[d.ftf]), r;
        const float big = 3.4028235e38f;
        if (d.lop == L_DIV) r = b == 0 ? ((std::signbit(a) != std::signbit(b)) ? -big : big) : vu_div(a, b);
        else if (d.lop == L_SQRT) r = vu_sqrt(fabsf(b));
        else r = b == 0 ? (std::signbit(a) ? -big : big) : vu_div(a, vu_sqrt(fabsf(b)));
        v.q_next = vu_out(r);
        v.q_ready = v.cyc + (d.lop == L_RSQRT ? 13 : 7);
        v.q_busy = true;
        break;
    }
    case L_WAITQ: if (v.q_busy) { if (v.q_ready > v.cyc) v.cyc = v.q_ready; v.q = v.q_next; v.q_busy = false; } break;
    case L_XGKICK: if (v.kick) { VU1_ROUND_RESTORE(old_round); v.kick(v.user, v.vi[d.ls] & 0x3FF); VU1_ROUND_TOWARD_ZERO(); } break;
    default:
        if (!v.bad++) fprintf(stderr, "vu1: lower instruction %08x not implemented at 0x%x\n", d.lower, at);
        break;
    }
    if (d.ibit) memcpy(&v.i_reg, &d.lower, 4);
    // ---- commit the upper half ----
    if (write == 2) v.acc = result;
    else if (write == 1 && target) v.vf[target] = result;
    v.cyc++;
    v.instructions++;
    return taken;
}

}  // namespace render
