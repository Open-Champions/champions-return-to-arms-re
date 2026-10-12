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
        float b[4];
        switch (d.usrc) {
        case S_VEC: b[0] = ft.f[0]; b[1] = ft.f[1]; b[2] = ft.f[2]; b[3] = ft.f[3]; break;
        case S_BC: b[0] = b[1] = b[2] = b[3] = ft.f[d.ubc]; break;
        case S_Q: b[0] = b[1] = b[2] = b[3] = v.q; break;
        default: b[0] = b[1] = b[2] = b[3] = v.i_reg; break;
        }
        Vu1::Reg r;
        bool arithmetic = false;
        switch (d.uop) {
        case U_ADD: for (int k = 0; k < 4; k++) r.f[k] = fs.f[k] + b[k]; arithmetic = true; break;
        case U_SUB: for (int k = 0; k < 4; k++) r.f[k] = fs.f[k] - b[k]; arithmetic = true; break;
        case U_MUL: for (int k = 0; k < 4; k++) r.f[k] = fs.f[k] * b[k]; arithmetic = true; break;
        case U_MADD: { float p[4]; for (int k = 0; k < 4; k++) p[k] = fs.f[k] * b[k]; for (int k = 0; k < 4; k++) r.f[k] = v.acc.f[k] + p[k]; arithmetic = true; break; }
        case U_MSUB: { float p[4]; for (int k = 0; k < 4; k++) p[k] = fs.f[k] * b[k]; for (int k = 0; k < 4; k++) r.f[k] = v.acc.f[k] - p[k]; arithmetic = true; break; }
        case U_MAX: for (int k = 0; k < 4; k++) r.f[k] = fs.f[k] > b[k] ? fs.f[k] : b[k]; break;
        case U_MINI: for (int k = 0; k < 4; k++) r.f[k] = fs.f[k] < b[k] ? fs.f[k] : b[k]; break;
        case U_ITOF: { float scale = 1.0f / (float)(1u << d.ubc); for (int k = 0; k < 4; k++) r.f[k] = (float)fs.s[k] * scale; break; }
        case U_FTOI: {
            float scale = (float)(1u << d.ubc);
            for (int k = 0; k < 4; k++) {
                float scaled = fs.f[k] * scale;
                r.s[k] = scaled >= 2147483648.0f ? 0x7FFFFFFF : scaled <= -2147483648.0f ? (int32_t)0x80000000 : (int32_t)scaled;
            }
            break;
        }
        case U_ABS: for (int k = 0; k < 4; k++) r.u[k] = fs.u[k] & 0x7FFFFFFF; break;
        case U_CLIP: {
            float w = fabsf(ft.f[3]);
            uint32_t c = 0;
            if (fs.f[0] > w) c |= 1;  if (fs.f[0] < -w) c |= 2;
            if (fs.f[1] > w) c |= 4;  if (fs.f[1] < -w) c |= 8;
            if (fs.f[2] > w) c |= 16; if (fs.f[2] < -w) c |= 32;
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
        float a = v.vf[d.ls].f[d.fsf], b = v.vf[d.lt].f[d.ftf], r;
        const float big = 3.4028235e38f;
        if (d.lop == L_DIV) r = b == 0 ? (((a < 0) != std::signbit(b)) ? -big : big) : a / b;
        else if (d.lop == L_SQRT) r = sqrtf(fabsf(b));
        else r = b == 0 ? (a < 0 ? -big : big) : a / sqrtf(fabsf(b));
        v.q_next = r;
        v.q_ready = v.cyc + (d.lop == L_RSQRT ? 13 : 7);
        v.q_busy = true;
        break;
    }
    case L_WAITQ: if (v.q_busy) { if (v.q_ready > v.cyc) v.cyc = v.q_ready; v.q = v.q_next; v.q_busy = false; } break;
    case L_XGKICK: if (v.kick) { fesetround(old_round); v.kick(v.user, v.vi[d.ls] & 0x3FF); fesetround(FE_TOWARDZERO); } break;
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
