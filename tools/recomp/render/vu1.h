// vu1.h - an interpreter for vector unit 1, enough of it to run this game's vertex
// programs (docs/spec/render-pipeline.md section 4) exactly as they are.
//
// What is modelled, because the programs rely on it:
//  - one instruction pair per cycle, the upper and lower halves reading the state from
//    before the pair - the I register too: a pair with the I bit loads its constant after
//    its own upper half has used the old one; branch delay slots; the E bit (stop after
//    the next pair);
//  - the divider: Q changes 7 cycles after DIV and 13 after RSQRT, the old value is read
//    until then (the lighting loops are written around that), WAITQ and a second divide
//    wait for the first;
//  - MAC, status and clip flags as seen 4 cycles after the instruction that made them;
//  - arithmetic rounded toward zero, as the unit rounds: the programs make integers for
//    the GS by adding 2^23 (and similar) to a float and letting the mantissa drop bits.
// What is not: the EFU (P register), random numbers, M/D/T bits, integer-register branch
// hazards (the programs would not work with them: see the loop at instruction 0x117),
// FMAC data stalls.  An instruction outside the 60-odd kinds the three programs use
// stops the run and is reported once.
#pragma once
#include <cstdint>

namespace render {

struct Vu1 {
    union Reg { float f[4]; uint32_t u[4]; int32_t s[4]; };
    Reg vf[32], acc;
    uint16_t vi[16];
    float q = 0, q_next = 0, i_reg = 0;
    uint64_t cyc = 0, q_ready = 0;
    bool q_busy = false;
    // Flags are worked out when an instruction reads them (nine places in the programs),
    // not when one is set: the last results and clip values are kept with their cycle.
    struct FlagEvent { uint64_t cyc; Reg value; uint32_t dest; };
    struct ClipEvent { uint64_t cyc; uint32_t value; };
    FlagEvent flag_ring[8];
    ClipEvent clip_ring[8];
    uint32_t flag_count = 0, clip_count = 0, clip_now = 0;
    uint32_t top = 0, itop = 0;         // VIF1 TOP / ITOP as the last MSCAL left them
    uint32_t pc = 0;                    // instruction index after the last run (MSCNT continues here)
    uint8_t* micro = nullptr;           // 16 KB: 2,048 instruction pairs, lower word first
    uint8_t* data = nullptr;            // 16 KB: 1,024 quadwords
    void (*kick)(void* user, uint32_t qword) = nullptr;    // XGKICK: a GIF packet starts at this quadword
    void* user = nullptr;
    uint64_t instructions = 0, runs = 0, bad = 0;
    int debug_left = 0;                 // print the registers at the next instructions in [debug_lo, debug_hi]
    uint32_t debug_lo = 0, debug_hi = 0;
    bool debug_hit = false;             // a watched store happened in the copy loop (0x314 / 0x318)
    int debug_store = 0;                // report the next stores into qwords debug_store_lo..hi (default 0x3f0-0x3f7)
    uint32_t debug_store_lo = 0x3F0, debug_store_hi = 0x3F7;

    Vu1();
    void run(uint32_t start);
    void micro_changed() { decoded_valid = false; }
    // The main program as C++ source (vu1.cpp); false when the file cannot be written.
    bool write_translation(const char* path, uint32_t pairs);
    bool use_translation = true;        // false: interpret even when a translation is linked
    bool translated = false;            // the linked translation matches what is in `micro`
    uint32_t mac_seen() const;          // MAC flags as an instruction of this cycle reads them
    uint32_t clip_seen() const;

    struct Ins {
        uint8_t uop, ukind, usrc, udst;     // upper: operation, see vu1.cpp
        uint8_t udest, uft, ufs, ufd, ubc;
        uint8_t lop, ldest, lt, ls, ld, fsf, ftf;
        uint8_t ibit, ebit;
        uint32_t umask[4];                  // all ones for the fields the upper half writes
        int16_t imm11;
        uint16_t imm15;
        uint32_t imm24;
        uint32_t lower;
    };
  private:
    Ins decoded[2048];
    bool decoded_valid = false;
    void decode();
};

}  // namespace render
