// vif1.cpp - see vif1.h.
#include "vif1.h"
#include "prof.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <ctime>

namespace render {

static uint32_t unpack_words(uint32_t code, uint32_t cl, uint32_t wl) {
    uint32_t cmd = (code >> 24) & 0x7F, num = (code >> 16) & 0xFF;
    uint32_t vn = (cmd >> 2) & 3, vl = cmd & 3;
    uint32_t vectors = num ? num : 256;
    if (wl > cl && wl) vectors = cl * (vectors / wl) + ((vectors % wl) < cl ? (vectors % wl) : cl);
    uint32_t bytes = (vn == 3 && vl == 3) ? vectors * 2 : vectors * (vn + 1) * (4 >> vl);
    return (bytes + 3) / 4;
}

void Vif1::feed(const uint32_t* words, size_t count) {
    if (!pending.empty()) {
        pending.insert(pending.end(), words, words + count);
        size_t used = process(pending.data(), pending.size());
        pending.erase(pending.begin(), pending.begin() + used);
        return;
    }
    size_t used = process(words, count);
    if (used < count) pending.assign(words + used, words + count);
}

void Vif1::run_waiting() {
    if (!waiting) return;
    waiting = false;
    if (gs) gs->debug_entry = waiting_from_pc ? -1 : (int)waiting_at;
#if RTA_PROF_ON
    if (!waiting_from_pc) prof_entry = waiting_at;
    prof::Scope prof_scope(prof::vu_part(prof_entry));
    uint64_t prof_pairs = vu.instructions;
    struct ProfCount { Vif1& v; uint64_t before; int slot; ~ProfCount() { if (!prof::state().on) return; prof::state().pairs[slot] += v.vu.instructions - before; prof::state().runs[slot]++; } }
        prof_count{*this, prof_pairs, prof::vu_part(prof_entry) - prof::P_VU_FIRST};
#endif
    if (run_programs && time_runs) {
        timespec a, b;
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &a);
        vu.run(waiting_from_pc ? vu.pc : waiting_at);
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &b);
        stats.run_ms += (b.tv_sec - a.tv_sec) * 1000.0 + (b.tv_nsec - a.tv_nsec) / 1e6;
    } else if (run_programs) vu.run(waiting_from_pc ? vu.pc : waiting_at);
    if (debug_ring > 0) {
        char line[96];
        snprintf(line, sizeof(line), "    -> ran %03x with top %03x itop %u", waiting_at, vu.top, vu.itop);
        ring.push_back(line);
        if (vu.debug_hit) {
            vu.debug_hit = false;
            debug_ring--;
            fprintf(stderr, "---- the codes before a run that stored into the constants ----\n");
            for (size_t k = ring.size() > 70 ? ring.size() - 70 : 0; k < ring.size(); k++) fprintf(stderr, "%s\n", ring[k].c_str());
        }
        if (ring.size() > 400) ring.erase(ring.begin(), ring.begin() + 200);
    }
}

void Vif1::start_program(uint32_t at, bool from_pc) {
    run_waiting();
    stats.mscal++;
    // the double buffer: what was unpacked becomes the program's input, the other half
    // receives the next packet
    vu.top = tops & 0x3FF;
    if (dbf) { tops = base; dbf = false; } else { tops = base + ofst; dbf = true; }
    vu.itop = itops;
    if (!from_pc && at < 128) entry_counts[at]++;
    waiting = true; waiting_at = at; waiting_from_pc = from_pc;
}

size_t Vif1::process(const uint32_t* w, size_t n) {
    RTA_PROF_SCOPE(prof::P_VIF);
    size_t i = 0;
    while (i < n) {
        uint32_t code = w[i];
        uint32_t cmd = (code >> 24) & 0x7F, num = (code >> 16) & 0xFF, imm = code & 0xFFFF;
        size_t need = 0;
        if (cmd == 0x20) need = 1;
        else if (cmd == 0x30 || cmd == 0x31) need = 4;
        else if (cmd == 0x4A) need = (size_t)(num ? num : 256) * 2;
        else if (cmd == 0x50 || cmd == 0x51) need = (size_t)(imm ? imm : 65536) * 4;
        else if (cmd >= 0x60) need = unpack_words(code, cl, wl);
        if (i + 1 + need > n) break;                    // the rest arrives with the next transfer
        const uint32_t* data = w + i + 1;
        stats.codes++;
        if (debug_ring > 0 && cmd != 0) {
            char line[96];
            snprintf(line, sizeof(line), "%s%02x num %u imm %04x (tops %03x%s)", cmd >= 0x60 ? "unpack " : "code ", cmd, num, imm, tops, waiting ? ", a program waits" : "");
            ring.push_back(line);
        }
        if (waiting) {
            // only what belongs to the strip under construction goes ahead of the program:
            // STCYCL and an UNPACK into the output part (+0x80 and up) of the buffer half
            bool harmless = cmd == 0x00 || cmd == 0x01 || (cmd >= 0x60 && (imm & 0x8000) && (imm & 0x3FF) >= 0x80);
            if (!harmless) run_waiting();
        }
        switch (cmd) {
        case 0x00:                                      // NOP; with 0xA5..0xA7 in NUM a note from the game side (gs.h)
            if (num >= 0xA5 && num <= 0xA7 && gs) { run_waiting(); gs->note(num, imm); }
            break;
        case 0x01: cl = imm & 0xFF; wl = (imm >> 8) & 0xFF; break;
        case 0x02: ofst = imm & 0x3FF; dbf = false; tops = base; break;
        case 0x03: base = imm & 0x3FF; break;
        case 0x04: itops = imm & 0x3FF; break;
        case 0x05: mode = imm & 3; break;
        case 0x06: case 0x07: break;                    // MSKPATH3, MARK
        case 0x10: case 0x11: case 0x13: break;         // FLUSHE, FLUSH, FLUSHA
        case 0x14: case 0x15: start_program(imm, false); break;
        case 0x17: start_program(0, true); break;
        case 0x20: mask = data[0]; break;
        case 0x30: memcpy(row, data, 16); break;
        case 0x31: memcpy(col, data, 16); break;
        case 0x4A:
            memcpy(vu.micro + ((imm * 8) & 0x3FFF), data, std::min<size_t>(need * 4, 0x4000 - ((imm * 8) & 0x3FFF)));
            vu.micro_changed(imm & 0x7FF, (uint32_t)(need / 2));
            stats.mpg++;
            break;
        case 0x50: case 0x51:
            stats.direct_qwords += need / 4;
            if (gs) gs->gif(1, data, need / 4);
            break;
        default:
            if (cmd >= 0x60) { unpack(code, data); stats.unpacks++; }
            else stats.unknown++;
            break;
        }
        i += 1 + need;
    }
    if (i >= n) run_waiting();
    return i;
}

// UNPACK without a mask and with a write cycle that skips (WL <= CL; in this game every
// one: S, V2, V3 and V4 of 8, 16 and 32 bits, with the offset and the difference mode):
// one loop per format instead of one decision per field.  What it writes is what unpack()
// below writes - that function is the description, and RTA_VIF_SLOW=1 uses it for all.
namespace {
#if defined(__GNUC__) || defined(__clang__)
#define VIF_INLINE inline __attribute__((always_inline))
#else
#define VIF_INLINE inline
#endif
// FIELDS elements of SIZE bytes per vector; MODE 0 as it is, 1 with the row added, 2 added and kept
template <unsigned FIELDS, unsigned SIZE, bool USN, unsigned MODE>
VIF_INLINE void unpack_run(const uint8_t* src, uint8_t* memory, uint32_t address, uint32_t total, uint32_t wcl, uint32_t wwl, uint32_t* row) {
    uint32_t r[4] = {row[0], row[1], row[2], row[3]};
    uint32_t cycle = 0;
    for (uint32_t written = 0; written < total; address++) {
        if (cycle < wwl) {
            uint32_t in[4] = {0, 0, 0, 0};
            for (unsigned f = 0; f < FIELDS; f++) {
                if (SIZE == 4) memcpy(&in[f], src + f * 4, 4);
                else if (SIZE == 2) { uint16_t e; memcpy(&e, src + f * 2, 2); in[f] = USN ? (uint32_t)e : (uint32_t)(int32_t)(int16_t)e; }
                else in[f] = USN ? (uint32_t)src[f] : (uint32_t)(int32_t)(int8_t)src[f];
            }
            if (FIELDS == 1) in[1] = in[2] = in[3] = in[0];
            src += FIELDS * SIZE;
            if (MODE == 1) for (int f = 0; f < 4; f++) in[f] += r[f];
            else if (MODE == 2) for (int f = 0; f < 4; f++) { in[f] += r[f]; r[f] = in[f]; }
            memcpy(memory + (address & 0x3FF) * 16, in, 16);
            written++;
        }
        if (++cycle >= wcl) cycle = 0;
    }
    if (MODE == 2) memcpy(row, r, 16);
}
template <unsigned FIELDS, unsigned SIZE>
VIF_INLINE void unpack_format(bool usn, uint32_t mode, const uint8_t* src, uint8_t* memory, uint32_t address, uint32_t total, uint32_t wcl, uint32_t wwl, uint32_t* row) {
    if (mode == 1) { if (usn) unpack_run<FIELDS, SIZE, true, 1>(src, memory, address, total, wcl, wwl, row); else unpack_run<FIELDS, SIZE, false, 1>(src, memory, address, total, wcl, wwl, row); }
    else if (mode == 2) { if (usn) unpack_run<FIELDS, SIZE, true, 2>(src, memory, address, total, wcl, wwl, row); else unpack_run<FIELDS, SIZE, false, 2>(src, memory, address, total, wcl, wwl, row); }
    else { if (usn) unpack_run<FIELDS, SIZE, true, 0>(src, memory, address, total, wcl, wwl, row); else unpack_run<FIELDS, SIZE, false, 0>(src, memory, address, total, wcl, wwl, row); }
}
}  // namespace

bool Vif1::unpack_fast(uint32_t code, const uint32_t* data) {
    uint32_t cmd = (code >> 24) & 0x7F, num = (code >> 16) & 0xFF, imm = code & 0xFFFF;
    uint32_t vn = (cmd >> 2) & 3, vl = cmd & 3;
    if ((cmd & 0x10) || vl == 3 || debug_unpack > 0) return false;
    uint32_t wcl = cl ? cl : 1, wwl = wl ? wl : 1;
    if (wwl > wcl) return false;
    const bool usn = imm & 0x4000, flg = imm & 0x8000;
    const uint32_t address = (imm & 0x3FF) + (flg ? tops : 0), total = num ? num : 256;
    const uint8_t* src = (const uint8_t*)data;
    switch (vn * 4 + vl) {
    case 0: unpack_format<1, 4>(usn, mode, src, vu.data, address, total, wcl, wwl, row); break;
    case 1: unpack_format<1, 2>(usn, mode, src, vu.data, address, total, wcl, wwl, row); break;
    case 2: unpack_format<1, 1>(usn, mode, src, vu.data, address, total, wcl, wwl, row); break;
    case 4: unpack_format<2, 4>(usn, mode, src, vu.data, address, total, wcl, wwl, row); break;
    case 5: unpack_format<2, 2>(usn, mode, src, vu.data, address, total, wcl, wwl, row); break;
    case 6: unpack_format<2, 1>(usn, mode, src, vu.data, address, total, wcl, wwl, row); break;
    case 8: unpack_format<3, 4>(usn, mode, src, vu.data, address, total, wcl, wwl, row); break;
    case 9: unpack_format<3, 2>(usn, mode, src, vu.data, address, total, wcl, wwl, row); break;
    case 10: unpack_format<3, 1>(usn, mode, src, vu.data, address, total, wcl, wwl, row); break;
    case 12: unpack_format<4, 4>(usn, mode, src, vu.data, address, total, wcl, wwl, row); break;
    case 13: unpack_format<4, 2>(usn, mode, src, vu.data, address, total, wcl, wwl, row); break;
    default: unpack_format<4, 1>(usn, mode, src, vu.data, address, total, wcl, wwl, row); break;
    }
    return true;
}

void Vif1::unpack(uint32_t code, const uint32_t* data) {
    uint32_t cmd = (code >> 24) & 0x7F, num = (code >> 16) & 0xFF, imm = code & 0xFFFF;
    uint32_t vn = (cmd >> 2) & 3, vl = cmd & 3;
    RTA_PROF_SCOPE(prof::P_UNPACK);
    if (fast_unpack && unpack_fast(code, data)) return;
    bool masked = cmd & 0x10, usn = imm & 0x4000, flg = imm & 0x8000;
    uint32_t address = (imm & 0x3FF) + (flg ? tops : 0);
    uint32_t total = num ? num : 256;
    const uint8_t* src = (const uint8_t*)data;
    const uint8_t* limit = src + (size_t)unpack_words(code, cl, wl) * 4;
    uint32_t wcl = cl ? cl : 1, wwl = wl ? wl : 1;
    uint32_t cycle = 0;                                 // position inside the write cycle
    auto element = [&](unsigned index) -> uint32_t {    // element `index` of the vector at src
        if (src + (index + 1) * (4 >> vl) > limit) return 0;    // the fourth element of the last three-element vector
        switch (vl) {
        case 0: { uint32_t v; memcpy(&v, src + index * 4, 4); return v; }
        case 1: { uint16_t v; memcpy(&v, src + index * 2, 2); return usn ? v : (uint32_t)(int32_t)(int16_t)v; }
        default: { uint8_t v = src[index]; return usn ? v : (uint32_t)(int32_t)(int8_t)v; }
        }
    };
    for (uint32_t written = 0; written < total;) {
        bool has_data = wwl <= wcl ? true : cycle < wcl;
        bool writes = wwl <= wcl ? cycle < wwl : true;
        if (writes) {
            uint32_t in[4] = {0, 0, 0, 0};
            if (has_data) {
                if (vn == 3 && vl == 3) {
                    uint16_t v; memcpy(&v, src, 2);
                    in[0] = (v & 31) << 3; in[1] = ((v >> 5) & 31) << 3; in[2] = ((v >> 10) & 31) << 3; in[3] = (v >> 15) << 7;
                    src += 2;
                } else {
                    switch (vn) {
                    case 0: in[0] = in[1] = in[2] = in[3] = element(0); break;
                    // Fields a format does not carry are written as zero.  (What the machine puts
                    // there is not defined by its manual; the game's strip programs read the
                    // fourth field of three-element rows, and with zero there the reference
                    // emulator draws the game right.)
                    case 1: in[0] = element(0); in[1] = element(1); break;
                    case 2: in[0] = element(0); in[1] = element(1); in[2] = element(2); break;
                    default: in[0] = element(0); in[1] = element(1); in[2] = element(2); in[3] = element(3); break;
                    }
                    src += (vn + 1) * (4 >> vl);
                }
            }
            if (debug_unpack > 0 && debug_unpack_hi && (address & 0x3FF) >= debug_unpack_lo && (address & 0x3FF) <= debug_unpack_hi) {
                debug_unpack--;
                fprintf(stderr, "unpack to %03x: code %08x tops %03x cl %u wl %u written %u/%u waiting %d entry %x | in %08x %08x %08x %08x mask %08x mode %u\n", address & 0x3FF, code,
                        tops, cl, wl, written, total, (int)waiting, waiting_at, in[0], in[1], in[2], in[3], masked ? mask : 0, mode);
            } else if (!debug_unpack_hi && (address & 0x3FF) >= 0x3F6 && debug_unpack > 0) {
                debug_unpack--;
                fprintf(stderr, "unpack to %03x: code %08x tops %03x base %03x ofst %03x dbf %d cl %u wl %u total %u written %u waiting %d entry %x\n", address & 0x3FF, code,
                        tops, base, ofst, (int)dbf, cl, wl, total, written, (int)waiting, waiting_at);
            }
            uint8_t* out = vu.data + ((address & 0x3FF) * 16);
            unsigned mrow = cycle < 3 ? cycle : 3;
            for (unsigned f = 0; f < 4; f++) {
                unsigned m = masked ? (mask >> (mrow * 8 + f * 2)) & 3 : 0;
                uint32_t v;
                if (m == 0) {
                    v = in[f];
                    if (!(vn == 3 && vl == 3)) {
                        if (mode == 1) v += row[f];
                        else if (mode == 2) { v += row[f]; row[f] = v; }
                    }
                } else if (m == 1) v = row[f];
                else if (m == 2) v = col[mrow];
                else continue;
                memcpy(out + f * 4, &v, 4);
            }
            written++;
        }
        address++;
        cycle++;
        if (wwl <= wcl ? cycle >= wcl : cycle >= wwl) cycle = 0;
    }
}

}  // namespace render
