// vu1.cpp - see vu1.h.  Compile with -frounding-math -ffp-contract=off: the rounding mode
// is changed while a program runs and a multiply-add must stay two rounded operations.
#include "vu1_fast.h"
#include "vu1_step.h"

#include <cfenv>
#include <cmath>
#include <cstdio>
#include <cstring>

namespace render {

Vu1::Vu1() {
    memset(vf, 0, sizeof(vf));
    memset(&acc, 0, sizeof(acc));
    memset(vi, 0, sizeof(vi));
    memset(flag_ring, 0, sizeof(flag_ring));
    memset(clip_ring, 0, sizeof(clip_ring));
    vf[0].f[3] = 1.0f;
    cyc = 16;                                           // so that "four cycles ago" never is before the start
}

void Vu1::micro_changed(uint32_t first, uint32_t count) {
    uint32_t end = first + count > 2048 ? 2048 : first + count;
    if (first >= end) return;
    if (decoded_valid) { dirty_first = first; dirty_end = end; }
    else { if (first < dirty_first) dirty_first = first; if (end > dirty_end) dirty_end = end; }
    decoded_valid = false;
    if (fast_checked) { fast_dirty_first = first; fast_dirty_end = end; }
    else { if (first < fast_dirty_first) fast_dirty_first = first; if (end > fast_dirty_end) fast_dirty_end = end; }
    fast_checked = false;
}

void Vu1::decode() {
    for (unsigned n = dirty_first; n < dirty_end; n++) {
        uint32_t lo, up;
        memcpy(&lo, micro + n * 8, 4);
        memcpy(&up, micro + n * 8 + 4, 4);
        Ins d;
        memset(&d, 0, sizeof(d));
        d.ibit = (up >> 31) & 1;
        d.ebit = (up >> 30) & 1;
        d.udest = (up >> 21) & 15;
        d.uft = (up >> 16) & 31;
        d.ufs = (up >> 11) & 31;
        d.ufd = (up >> 6) & 31;
        d.ubc = up & 3;
        for (int k = 0; k < 4; k++) d.umask[k] = (d.udest & (8 >> k)) ? 0xFFFFFFFFu : 0;
        unsigned op = up & 0x3F;
        static const uint8_t group[7] = {U_ADD, U_SUB, U_MADD, U_MSUB, U_MAX, U_MINI, U_MUL};
        d.uop = U_BAD;
        d.udst = 0;
        if (op < 0x1C) { d.uop = group[op >> 2]; d.usrc = S_BC; }
        else if (op < 0x28) {
            static const uint8_t ops[12] = {U_MUL, U_MAX, U_MUL, U_MINI, U_ADD, U_MADD, U_ADD, U_MADD, U_SUB, U_MSUB, U_SUB, U_MSUB};
            static const uint8_t src[12] = {S_Q, S_I, S_I, S_I, S_Q, S_Q, S_I, S_I, S_Q, S_Q, S_I, S_I};
            d.uop = ops[op - 0x1C]; d.usrc = src[op - 0x1C];
        } else if (op < 0x30) {
            static const uint8_t ops[8] = {U_ADD, U_MADD, U_MUL, U_MAX, U_SUB, U_MSUB, U_BAD, U_MINI};
            d.uop = ops[op - 0x28]; d.usrc = S_VEC;
        } else if (op >= 0x3C) {
            unsigned sp = (d.ufd << 2) | (up & 3);
            d.udst = 1;                                 // the accumulator
            if (sp < 0x10) { static const uint8_t g[4] = {U_ADD, U_SUB, U_MADD, U_MSUB}; d.uop = g[sp >> 2]; d.usrc = S_BC; }
            else if (sp >= 0x18 && sp < 0x1C) { d.uop = U_MUL; d.usrc = S_BC; }
            else if (sp >= 0x10 && sp < 0x14) { static const uint8_t s[4] = {0, 4, 12, 15}; d.uop = U_ITOF; d.ubc = s[sp & 3]; }
            else if (sp >= 0x14 && sp < 0x18) { static const uint8_t s[4] = {0, 4, 12, 15}; d.uop = U_FTOI; d.ubc = s[sp & 3]; }
            else if (sp == 0x1C) { d.uop = U_MUL; d.usrc = S_Q; }
            else if (sp == 0x1D) d.uop = U_ABS;
            else if (sp == 0x1E) { d.uop = U_MUL; d.usrc = S_I; }
            else if (sp == 0x1F) d.uop = U_CLIP;
            else if (sp >= 0x20 && sp < 0x28) {
                static const uint8_t ops[8] = {U_ADD, U_MADD, U_ADD, U_MADD, U_SUB, U_MSUB, U_SUB, U_MSUB};
                static const uint8_t src[8] = {S_Q, S_Q, S_I, S_I, S_Q, S_Q, S_I, S_I};
                d.uop = ops[sp - 0x20]; d.usrc = src[sp - 0x20];
            } else if (sp >= 0x28 && sp < 0x2E && sp != 0x2B) {
                static const uint8_t ops[6] = {U_ADD, U_MADD, U_MUL, U_BAD, U_SUB, U_MSUB};
                d.uop = ops[sp - 0x28]; d.usrc = S_VEC;
            } else if (sp == 0x2F) d.uop = U_NOP;
        }
        // lower
        d.lower = lo;
        d.ldest = (lo >> 21) & 15;
        d.lt = (lo >> 16) & 31;
        d.ls = (lo >> 11) & 31;
        d.ld = (lo >> 6) & 31;
        d.fsf = (lo >> 21) & 3;
        d.ftf = (lo >> 23) & 3;
        d.imm11 = (int16_t)((lo & 0x7FF) << 5) >> 5;
        d.imm15 = (uint16_t)(((lo >> 10) & 0x7800) | (lo & 0x7FF));
        d.imm24 = lo & 0xFFFFFF;
        unsigned lop = lo >> 25;
        d.lop = L_BAD;
        if (d.ibit) d.lop = L_NOP;
        else switch (lop) {
        case 0x00: d.lop = L_LQ; break;       case 0x01: d.lop = L_SQ; break;
        case 0x04: d.lop = L_ILW; break;      case 0x05: d.lop = L_ISW; break;
        case 0x08: d.lop = L_IADDIU; break;   case 0x09: d.lop = L_ISUBIU; break;
        case 0x10: d.lop = L_FCEQ; break;     case 0x11: d.lop = L_FCSET; break;
        case 0x12: d.lop = L_FCAND; break;    case 0x13: d.lop = L_FCOR; break;
        case 0x14: d.lop = L_FSEQ; break;     case 0x15: d.lop = L_FSSET; break;
        case 0x16: d.lop = L_FSAND; break;    case 0x17: d.lop = L_FSOR; break;
        case 0x18: d.lop = L_FMEQ; break;     case 0x1A: d.lop = L_FMAND; break;
        case 0x1B: d.lop = L_FMOR; break;     case 0x1C: d.lop = L_FCGET; break;
        case 0x20: d.lop = L_B; break;        case 0x21: d.lop = L_BAL; break;
        case 0x24: d.lop = L_JR; break;       case 0x25: d.lop = L_JALR; break;
        case 0x28: d.lop = L_IBEQ; break;     case 0x29: d.lop = L_IBNE; break;
        case 0x2C: d.lop = L_IBLTZ; break;    case 0x2D: d.lop = L_IBGTZ; break;
        case 0x2E: d.lop = L_IBLEZ; break;    case 0x2F: d.lop = L_IBGEZ; break;
        case 0x40: {
            unsigned f = lo & 0x3F;
            if (f == 0x30) d.lop = L_IADD;
            else if (f == 0x31) d.lop = L_ISUB;
            else if (f == 0x32) d.lop = L_IADDI;
            else if (f == 0x34) d.lop = L_IAND;
            else if (f == 0x35) d.lop = L_IOR;
            else if (f >= 0x3C) {
                unsigned sp = (d.ld << 2) | (lo & 3);
                switch (sp) {
                case 0x30: d.lop = L_MOVE; break;   case 0x31: d.lop = L_MR32; break;
                case 0x34: d.lop = L_LQI; break;    case 0x35: d.lop = L_SQI; break;
                case 0x36: d.lop = L_LQD; break;    case 0x37: d.lop = L_SQD; break;
                case 0x38: d.lop = L_DIV; break;    case 0x39: d.lop = L_SQRT; break;
                case 0x3A: d.lop = L_RSQRT; break;  case 0x3B: d.lop = L_WAITQ; break;
                case 0x3C: d.lop = L_MTIR; break;   case 0x3D: d.lop = L_MFIR; break;
                case 0x3E: d.lop = L_ILWR; break;   case 0x3F: d.lop = L_ISWR; break;
                case 0x68: d.lop = L_XTOP; break;   case 0x69: d.lop = L_XITOP; break;
                case 0x6C: d.lop = L_XGKICK; break;
                }
            }
            if (lo == 0x8000033C) d.lop = L_NOP;        // the canonical lower NOP (MOVE vf0, vf0)
            break;
        }
        }
        decoded[n] = d;
    }
    decoded_valid = true;
    dirty_first = 2048; dirty_end = 0;
}

uint32_t Vu1::mac_seen() const {
    // the newest result that is at least four cycles old
    for (uint32_t back = 1; back <= 8 && back <= flag_count; back++) {
        const FlagEvent& e = flag_ring[(flag_count - back) & 7];
        if (e.cyc + 4 > cyc) continue;
        uint32_t mac = 0;
        for (int k = 0; k < 4; k++) {
            if (!(e.dest & (8 >> k))) continue;
            if ((e.value.u[k] & 0x7FFFFFFF) == 0) mac |= 0x0008 >> k;
            if (e.value.u[k] & 0x80000000) mac |= 0x0080 >> k;
        }
        return mac;
    }
    return 0;
}

uint32_t Vu1::clip_seen() const {
    for (uint32_t back = 1; back <= 8 && back <= clip_count; back++) {
        const ClipEvent& e = clip_ring[(clip_count - back) & 7];
        if (e.cyc + 4 <= cyc) return e.value;
    }
    return 0;
}

// The translation of the main program, when one is linked (vu1_translated.cpp from
// local/recomp-out/gen-vu/, or vu1_none.cpp).  It is used only while the microprogram
// memory holds exactly the program it was made from.
extern const uint64_t vu1_translated_hash;
extern const uint32_t vu1_translated_count;
int vu1_translated_run(Vu1& v, uint32_t at, int old_round);

static uint64_t micro_hash(const uint8_t* micro, uint32_t pairs) {
    uint64_t h = 0xCBF29CE484222325ull;
    for (uint32_t k = 0; k < pairs * 8; k++) { h ^= micro[k]; h *= 0x100000001B3ull; }
    return h;
}

// Which of the translated programs are in the microprogram memory now.  Only those the
// change touched are looked at again: the game loads a small program behind the main one
// every frame, and the main one is 15 KB to hash.
void Vu1::fast_check() {
    for (uint32_t k = 0; k < vu1_fast_program_count && k < 32; k++) {
        const Vu1Program& p = vu1_fast_programs[k];
        if (p.start + p.count > 2048 || p.start >= fast_dirty_end || p.start + p.count <= fast_dirty_first) continue;
        if (micro_hash(micro + p.start * 8, p.count) == p.hash) fast_match |= 1u << k; else fast_match &= ~(1u << k);
    }
    fast_checked = true;
    fast_dirty_first = 2048; fast_dirty_end = 0;
}

void vu1_fast_kick(Vu1& v, uint32_t qword) {
    if (!v.kick) return;
    vu1_flush_off();
    VU1_ROUND_RESTORE(v.round_before);
    v.kick(v.user, qword);
    VU1_ROUND_TOWARD_ZERO();
    vu1_flush_on();
}

// Does the processor's flush-to-zero mode do what the translated programs leave to it
// (vu1_simd.h)?  A few products and sums around the smallest normal number, by the
// processor in that mode and by vu_in / vu_out, in the unit's rounding.
static bool vu1_flush_works() {
#if VU1_HARDWARE_FLUSH
    static const uint32_t cases[][2] = {
        {0x00800000u, 0x3F000000u}, {0x80800000u, 0x3F000000u}, {0x00C00000u, 0x80800000u}, {0x00000001u, 0x7F000000u}, {0x807FFFFFu, 0x40000000u},
        {0x00800001u, 0x3F7FFFFFu}, {0x1E000000u, 0x1E000000u}, {0x00FFFFFFu, 0x80FFFFFEu}, {0x7F7FFFFFu, 0x00000001u}, {0x3F800000u, 0x3F800000u}};
    bool good = true;
    for (const auto& c : cases) {
        volatile uint32_t a = c[0], b = c[1];           // not folded at compile time
        V4 x = v4_splat(a), y = v4_splat(b);
        uint32_t want[3] = {0, 0, 0}, got[3];
        float fa = vu_in(a), fb = vu_in(b), r;
        r = vu_out(vu_mul(fa, fb)); memcpy(&want[0], &r, 4);
        r = vu_out(vu_add(fa, fb)); memcpy(&want[1], &r, 4);
        r = vu_out(vu_sub(fa, fb)); memcpy(&want[2], &r, 4);
        vu1_flush_on();
        got[0] = v4_get(v4_out(v4_mul(v4_in(x), v4_in(y))), 0);
        got[1] = v4_get(v4_out(v4_add(v4_in(x), v4_in(y))), 1);
        got[2] = v4_get(v4_out(v4_sub(v4_in(x), v4_in(y))), 2);
        vu1_flush_off();
        if (memcmp(want, got, sizeof(want))) good = false;
    }
    return good;
#else
    return true;
#endif
}

void Vu1::run(uint32_t start) {
    bool micro_was_changed = !decoded_valid;
    if (!fast_checked) fast_check();
    int old_round = fegetround();
    round_before = old_round;
    VU1_ROUND_TOWARD_ZERO();
    runs++;
    uint32_t at = start & 2047;
    int stop_in = -1;                                   // pairs left after an E bit
    int branch_in = -1;
    uint32_t branch_to = 0;
    const bool debugging = debug_left > 0 || debug_store > 0;
    if (use_fast && fast_match && !debugging) {
        static const bool flush_works = vu1_flush_works();      // (in the unit's rounding, as the programs run)
        if (!flush_works) {
            fprintf(stderr, "vu1: this processor's flush-to-zero mode is not what the translated programs count on - interpreting\n");
            use_fast = false;
        }
        for (uint32_t k = 0; use_fast && k < vu1_fast_program_count && k < 32; k++) {
            const Vu1Program& p = vu1_fast_programs[k];
            if (!(fast_match & (1u << k)) || at < p.start || at >= p.start + p.count) continue;
            vu1_flush_on();
            int left = p.run(*this, at);
            vu1_flush_off();
            if (left < 0) {                             // ran to its end bit
                fast_runs++;
                if (q_busy) { q = q_next; q_busy = false; }
                VU1_ROUND_RESTORE(old_round);
                return;
            }
            if ((uint32_t)left != at) { fast_runs++; fast_left++; at = (uint32_t)left; break; }    // it ran some of it
        }
    }
    if (!decoded_valid) {
        decode();
        micro_was_changed = true;
    }
    if (micro_was_changed) translated = use_translation && vu1_translated_count && micro_hash(micro, vu1_translated_count) == vu1_translated_hash;
    if (translated && !debugging && at < vu1_translated_count) {
        int left = vu1_translated_run(*this, at, old_round);
        if (left < 0) {                                 // ran to its end bit
            if (q_busy) { q = q_next; q_busy = false; }
            VU1_ROUND_RESTORE(old_round);
            return;
        }
        at = (uint32_t)left;                            // a place the translation leaves to the interpreter
    }
    for (uint64_t guard = 0; guard < 4000000; guard++) {
        const Ins& d = decoded[at];
        if (debugging) {
            if (debug_left > 0 && at >= debug_lo && at <= debug_hi) {
                debug_left--;
                fprintf(stderr, "vu %03x (from %03x) cyc %llu Q %g | vi", at, start, (unsigned long long)cyc, q);
                for (int k = 1; k < 16; k++) fprintf(stderr, " %x", vi[k]);
                fprintf(stderr, " | vf1 %g %g %g %g | vf2 %g %g %g %g | vf4 %g %g %g %g | vf14 %g %g %g %g\n", vf[1].f[0], vf[1].f[1], vf[1].f[2], vf[1].f[3],
                        vf[2].f[0], vf[2].f[1], vf[2].f[2], vf[2].f[3], vf[4].f[0], vf[4].f[1], vf[4].f[2], vf[4].f[3], vf[14].f[0], vf[14].f[1], vf[14].f[2], vf[14].f[3]);
            }
            if (debug_store > 0 && (d.lop == L_SQ || d.lop == L_SQI || d.lop == L_SQD || d.lop == L_ISW || d.lop == L_ISWR)) {
                uint32_t a = d.lop == L_SQ ? (uint32_t)vi[d.lt] + d.imm11 : d.lop == L_ISW ? (uint32_t)vi[d.ls] + d.imm11
                           : d.lop == L_SQI ? vi[d.lt] : d.lop == L_SQD ? (uint32_t)vi[d.lt] - 1 : vi[d.ls];
                a &= 0x3FF;
                if (a >= debug_store_lo && a <= debug_store_hi) {
                    debug_store--;
                    if (at == 0x314 || at == 0x318) debug_hit = true;
                    fprintf(stderr, "vu store to %03x at %03x (run from %03x, cycle %llu): top %03x itop %u vi", a, at, start, (unsigned long long)cyc, top, itop);
                    for (int k = 1; k < 16; k++) fprintf(stderr, " %x", vi[k]);
                    if (d.lop != L_ISW && d.lop != L_ISWR) fprintf(stderr, " | %08x %08x %08x %08x", vf[d.ls].u[0], vf[d.ls].u[1], vf[d.ls].u[2], vf[d.ls].u[3]);
                    fprintf(stderr, "\n");
                }
            }
        }
        uint32_t dest = 0;
        bool taken = vu1_step(*this, d, at, dest, old_round);
        // ---- control ----
        at = (at + 1) & 2047;
        if (branch_in == 0) { at = branch_to & 2047; branch_in = -1; }
        else if (branch_in > 0) branch_in--;
        if (taken && branch_in < 0) { branch_in = 0; branch_to = dest; }
        if (stop_in == 0) break;
        if (stop_in > 0) stop_in--;
        if (d.ebit && stop_in < 0) stop_in = 0;
    }
    pc = at;
    // a divide in flight finishes before the next program starts
    if (q_busy) { q = q_next; q_busy = false; }
    VU1_ROUND_RESTORE(old_round);
}

// Write the main program as C++: every pair a constant handed to vu1_step, the branches,
// delay slots and end bits as gotos.  `pairs` is how much of the microprogram memory the
// main program takes (the two small programs loaded behind it each frame are interpreted).
bool Vu1::write_translation(const char* path, uint32_t pairs) {
    if (!decoded_valid) decode();
    FILE* f = fopen(path, "w");
    if (!f) return false;
    auto is_branch = [&](uint32_t n) { return decoded[n].lop >= L_B && decoded[n].lop <= L_IBGEZ; };
    auto is_dynamic = [&](uint32_t n) { return decoded[n].lop == L_JR || decoded[n].lop == L_JALR; };
    fprintf(f, "// GENERATED by Vu1::write_translation from the game's VU1 microprogram: derived from the game,\n"
               "// keep under local/recomp-out/.  %u instruction pairs.\n#include \"vu1_step.h\"\n\nnamespace render {\n\n", pairs);
    fprintf(f, "extern const uint64_t vu1_translated_hash = 0x%llxull;\nextern const uint32_t vu1_translated_count = %u;\n\n",
            (unsigned long long)micro_hash(micro, pairs), pairs);
    fprintf(f, "static constexpr Vu1::Ins K[%u] = {\n", pairs + 1);
    for (uint32_t n = 0; n <= pairs; n++) {
        const Ins& d = decoded[n];
        fprintf(f, "    {%u, %u, %u, %u, %u, %u, %u, %u, %u, %u, %u, %u, %u, %u, %u, %u, %u, %u, {0x%xu, 0x%xu, 0x%xu, 0x%xu}, %d, %u, 0x%xu, 0x%xu},\n", d.uop, d.ukind,
                d.usrc, d.udst, d.udest, d.uft, d.ufs, d.ufd, d.ubc, d.lop, d.ldest, d.lt, d.ls, d.ld, d.fsf, d.ftf, d.ibit, d.ebit, d.umask[0], d.umask[1],
                d.umask[2], d.umask[3], d.imm11, d.imm15, d.imm24, d.lower);
    }
    fprintf(f, "};\n\n// Returns -1 when the program reached its end bit (v.pc is set), or the instruction to go on\n// interpreting at.\n"
               "int vu1_translated_run(Vu1& v, uint32_t at, int old_round) {\n    uint32_t dest = 0;\n    bool taken = false;\n"
               "dispatch:\n    if (at >= %u) return (int)at;\n    switch (at) {\n", pairs);
    for (uint32_t n = 0; n < pairs; n++) fprintf(f, "    case %u: goto L_%03x;\n", n, n);
    fprintf(f, "    }\n");
    for (uint32_t n = 0; n < pairs; n++) {
        const Ins& d = decoded[n];
        fprintf(f, "L_%03x:\n", n);
        bool branch = is_branch(n);
        // a pair after which control is not simply the next pair, with a slot the translation
        // does not follow: leave it to the interpreter
        if ((branch || d.ebit) && (n + 1 >= pairs || decoded[n + 1].ebit || (d.ebit && branch))) { fprintf(f, "    return %u;\n", n); continue; }
        fprintf(f, "    taken = vu1_step(v, K[%u], %u, dest, old_round);\n", n, n);
        if (!branch && !d.ebit) continue;               // falls into the next pair
        if (d.ebit) {                                   // one more pair, then the program ends
            fprintf(f, "    { uint32_t ignored; vu1_step(v, K[%u], %u, ignored, old_round); }\n    v.pc = %u;\n    return -1;\n", n + 1, n + 1, (n + 2) & 2047);
            continue;
        }
        // a branch: its delay slot runs, then it goes; a branch in the slot is not taken
        if (is_dynamic(n)) fprintf(f, "    { uint32_t to = dest, ignored; vu1_step(v, K[%u], %u, ignored, old_round); at = to & 2047; goto dispatch; }\n", n + 1, n + 1);
        else {
            uint32_t to = (n + 1 + d.imm11) & 2047;
            fprintf(f, "    { bool go = taken; uint32_t ignored; vu1_step(v, K[%u], %u, ignored, old_round);\n", n + 1, n + 1);
            char yes[32], no[32];
            if (to < pairs) snprintf(yes, sizeof(yes), "goto L_%03x", to); else snprintf(yes, sizeof(yes), "return %u", to);
            if (n + 2 < pairs) snprintf(no, sizeof(no), "goto L_%03x", n + 2); else snprintf(no, sizeof(no), "return %u", (n + 2) & 2047);
            fprintf(f, "      if (go) %s; else %s; }\n", yes, no);
        }
    }
    fprintf(f, "    return %u;\n}\n\n}  // namespace render\n", pairs);
    fclose(f);
    return true;
}

}  // namespace render
