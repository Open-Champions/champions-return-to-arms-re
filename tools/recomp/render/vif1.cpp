// vif1.cpp - see vif1.h.
#include "vif1.h"

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
        case 0x00: break;                               // NOP
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
            vu.micro_changed();
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

void Vif1::unpack(uint32_t code, const uint32_t* data) {
    uint32_t cmd = (code >> 24) & 0x7F, num = (code >> 16) & 0xFF, imm = code & 0xFFFF;
    uint32_t vn = (cmd >> 2) & 3, vl = cmd & 3;
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
            if ((address & 0x3FF) >= 0x3F6 && debug_unpack > 0) {
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
