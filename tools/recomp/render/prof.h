// prof.h - where the renderer's processor side spends its instructions: a counter per
// part, read from the thread's own instruction and cycle counters at every change of part.
//
// Compiled in only with -DRTA_PROF (tools/recomp/render/speedbench.py --prof); otherwise
// every call below is empty.  Instructions and cycles, not times: the machine this is
// developed on is never free, and those two do not move with its load the way times do
// (docs/issues/native-render-speed.md).  Reading the counters costs a system call (about
// 2,000 instructions on the Mac this was written on); prof::calibrate() measures it and
// the report takes it off again, per change of part.
#pragma once
#include <cstdint>
#include <cstdio>

namespace render {
namespace prof {

enum Part {
    P_HOST,             // outside the renderer: the bench's own reading and checksums
    P_VIF,              // VIF1 codes other than UNPACK
    P_UNPACK,           // VIF1 UNPACK
    P_VU,               // VU1 programs: by entry, below
    P_KICK_COPY,        // XGKICK: the packet taken out of VU1 memory
    P_GS_VU,            // GIF data of path 1 that VU1 kicked: registers, vertices, primitives
    P_GS_DIRECT,        // the same for DIRECT data and the GIF channel
    P_GS_STATE,         // a draw command's state worked out (rebuild_state)
    P_GS_TEXID,         // which texture a draw means (texture_for when it is known already)
    P_GS_TEXMAKE,       // a texture decoded for the first time
    P_GS_UPLOAD,        // transfers to the GS: the copy and the hash of what was sent
    P_GS_FRAME,         // end of frame, begin of frame
    P_FIXED,
    P_VU_FIRST = P_FIXED, P_VU_SLOTS = 48,
    P_COUNT = P_VU_FIRST + P_VU_SLOTS
};

#if defined(RTA_PROF) && defined(__APPLE__)
extern "C" int thread_selfcounts(int type, void* buf, size_t nbytes);

struct State {
    uint64_t instructions[P_COUNT] = {0}, cycles[P_COUNT] = {0}, entered[P_COUNT] = {0};
    uint64_t pairs[P_VU_SLOTS] = {0}, runs[P_VU_SLOTS] = {0};
    uint32_t vu_entry[P_VU_SLOTS] = {0};
    int vu_slots = 0;
    int now = P_HOST;
    uint64_t last[2] = {0, 0};
    double cost_instructions = 0, cost_cycles = 0;      // of one change of part
    bool on = false;
};
inline State& state() { static State s; return s; }

inline void change(int part) {
    State& s = state();
    if (!s.on) { s.now = part; return; }
    uint64_t c[2];
    thread_selfcounts(1, c, sizeof(c));
    s.instructions[s.now] += c[0] - s.last[0];
    s.cycles[s.now] += c[1] - s.last[1];
    s.last[0] = c[0]; s.last[1] = c[1];
    s.now = part;
    s.entered[part]++;
}
inline void start() { State& s = state(); thread_selfcounts(1, s.last, sizeof(s.last)); s.on = true; }
inline void stop() { change(state().now); state().on = false; }
inline void calibrate() {
    State saved = state();
    State& s = state();
    s = State();
    start();
    for (int k = 0; k < 2000; k++) change(k & 1 ? P_VIF : P_UNPACK);
    stop();
    double ci = (double)(s.instructions[P_VIF] + s.instructions[P_UNPACK]) / 2000.0, cc = (double)(s.cycles[P_VIF] + s.cycles[P_UNPACK]) / 2000.0;
    s = saved;
    s.cost_instructions = ci; s.cost_cycles = cc;
}
// the part of a VU1 program started at `entry` (an instruction index)
inline int vu_part(uint32_t entry) {
    State& s = state();
    for (int k = 0; k < s.vu_slots; k++) if (s.vu_entry[k] == entry) return P_VU_FIRST + k;
    if (s.vu_slots < P_VU_SLOTS - 1) { s.vu_entry[s.vu_slots] = entry; return P_VU_FIRST + s.vu_slots++; }
    s.vu_entry[P_VU_SLOTS - 1] = 0xFFFF;
    return P_VU_FIRST + P_VU_SLOTS - 1;
}
struct Scope {
    int before;
    explicit Scope(int part) : before(state().now) { change(part); }
    ~Scope() { change(before); }
};
// One line per part: instructions and cycles per frame with the cost of reading the
// counters taken off (a change of part is charged half to the part left, half to the one
// entered: each part is charged one whole change per time it was entered).
inline void report(FILE* f, double frames) {
    State& s = state();
    static const char* const names[P_FIXED] = {"outside (bench)", "VIF1 codes", "VIF1 UNPACK", "VU1", "XGKICK copy", "GS: VU1's packets", "GS: DIRECT + GIF channel",
                                               "GS: draw state", "GS: texture lookup", "GS: texture made", "GS: uploads (copy, hash)", "GS: frame ends"};
    double total_i = 0, total_c = 0;
    double net_i[P_COUNT], net_c[P_COUNT];
    for (int p = 0; p < P_COUNT; p++) {
        net_i[p] = (double)s.instructions[p] - (double)s.entered[p] * s.cost_instructions;
        net_c[p] = (double)s.cycles[p] - (double)s.entered[p] * s.cost_cycles;
        if (p != P_HOST) { total_i += net_i[p]; total_c += net_c[p]; }
    }
    fprintf(f, "profile per frame (%.0f frames; a change of part costs %.0f instructions, %.0f cycles, taken off):\n", frames, s.cost_instructions, s.cost_cycles);
    fprintf(f, "  %-28s %12s %7s %12s %7s %10s\n", "part", "instructions", "share", "cycles", "share", "entered");
    double vu_i = 0, vu_c = 0;
    for (int k = 0; k < s.vu_slots || k == P_VU_SLOTS - 1; k++) { vu_i += net_i[P_VU_FIRST + k]; vu_c += net_c[P_VU_FIRST + k]; if (k >= s.vu_slots) break; }
    for (int p = 0; p < P_FIXED; p++) {
        double i = p == P_VU ? vu_i : net_i[p], c = p == P_VU ? vu_c : net_c[p];
        if (p == P_HOST) { fprintf(f, "  %-28s %12.0f %7s %12.0f\n", names[p], i / frames, "", c / frames); continue; }
        fprintf(f, "  %-28s %12.0f %6.1f%% %12.0f %6.1f%% %10.0f\n", names[p], i / frames, 100.0 * i / total_i, c / frames, 100.0 * c / total_c, s.entered[p] / frames);
    }
    fprintf(f, "  %-28s %12.0f %7s %12.0f\n", "all of the renderer", total_i / frames, "", total_c / frames);
    fprintf(f, "  VU1 by program entry (instruction index): runs, instruction pairs, instructions and cycles per frame, instructions per pair\n");
    for (int k = 0; k < P_VU_SLOTS; k++) {
        int p = P_VU_FIRST + k;
        if (!s.entered[p]) continue;
        fprintf(f, "    entry %04x %8.1f runs %10.0f pairs %12.0f %6.1f%% %12.0f %6.1f%%   %6.1f\n", s.vu_entry[k], s.runs[k] / frames, s.pairs[k] / frames, net_i[p] / frames,
                100.0 * net_i[p] / total_i, net_c[p] / frames, 100.0 * net_c[p] / total_c, s.pairs[k] ? net_i[p] / (double)s.pairs[k] : 0.0);
    }
}
#define RTA_PROF_NAME2(a, b) a##b
#define RTA_PROF_NAME(a, b) RTA_PROF_NAME2(a, b)
#define RTA_PROF_SCOPE(part) ::render::prof::Scope RTA_PROF_NAME(rta_prof_scope_, __LINE__)(part)
#define RTA_PROF_ON 1
#else
inline void change(int) {}
inline void start() {}
inline void stop() {}
inline void calibrate() {}
inline int vu_part(uint32_t) { return P_VU; }
inline void report(FILE*, double) {}
#define RTA_PROF_SCOPE(part) ((void)0)
#define RTA_PROF_ON 0
#endif

}  // namespace prof
}  // namespace render
