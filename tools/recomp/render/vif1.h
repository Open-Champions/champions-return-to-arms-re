// vif1.h - the VIF1 decoder: takes the word stream of DMA transfers to VIF1, unpacks data
// into VU1 memory, loads microprograms, runs them (vu1.h) and passes DIRECT data and the
// packets VU1 kicks to the GS model (gs.h).  State is kept from one transfer to the next.
#pragma once
#include "gs.h"
#include "vu1.h"

#include <string>
#include <vector>

namespace render {

struct Vif1Stats { uint64_t codes = 0, unpacks = 0, mscal = 0, direct_qwords = 0, mpg = 0, unknown = 0; double run_ms = 0; };

class Vif1 {
  public:
    Vu1 vu;
    Gs* gs = nullptr;
    Vif1Stats stats;
    bool run_programs = true;
    // The scene tap (scene_tap.h): told before a microprogram runs (entry, or -1 for a continued one), and given
    // the notes from the game side that are its own (NOP codes with 0xA8 / 0xA9 in NUM)
    void (*on_program)(void* user, int entry) = nullptr;
    void (*on_note)(void* user, uint32_t num, uint32_t imm) = nullptr;
    void* tap_user = nullptr;
    bool time_runs = false;             // add the processor time of every program run to stats.run_ms (kicks included)
    int debug_ring = 0;                 // > 0: keep the last codes and print them when vu.debug_hit is raised
    std::vector<std::string> ring;
    int debug_unpack = 0;               // > 0: report unpacks that reach the constants at 0x3f6 and up
    uint32_t debug_unpack_lo = 0, debug_unpack_hi = 0;   // when hi is set: report unpacks into this range instead
    uint64_t entry_counts[128] = {0};   // MSCAL starts by entry (instruction index < 128)

    void feed(const uint32_t* words, size_t count);

  private:
    uint32_t cl = 1, wl = 1, mode = 0, mask = 0, row[4] = {0, 0, 0, 0}, col[4] = {0, 0, 0, 0};
    uint32_t base = 0, ofst = 0, tops = 0, itops = 0;
    bool dbf = false;
    std::vector<uint32_t> pending;
    size_t process(const uint32_t* w, size_t n);       // returns words consumed
    void unpack(uint32_t code, const uint32_t* data);
    bool unpack_fast(uint32_t code, const uint32_t* data);
  public:
    bool fast_unpack = true;            // false: every UNPACK field by field (the reference; RTA_VIF_SLOW)
  private:
    void start_program(uint32_t at, bool from_pc);
    // A started program runs when the VIF comes to a code that would wait for VU1 or that
    // writes where the program may read, not at its MSCAL.  On the machine the VIF goes on
    // unpacking while the program runs, and the mesh packets rely on it: their texture
    // coordinates follow the MSCAL and are unpacked, relative to the double buffer's other
    // half, into the strip the program is building, long before the program kicks it.
    // So: STCYCL and an UNPACK into the output part of the double buffer's other half
    // (+0x80 and up) are carried out first; any other code runs the program before it.
    bool waiting = false, waiting_from_pc = false;
    uint32_t waiting_at = 0;
#ifdef RTA_PROF
    uint32_t prof_entry = 0;            // the entry of the last MSCAL (prof.h: a continued program counts for it)
#endif
    void run_waiting();
};

}  // namespace render
