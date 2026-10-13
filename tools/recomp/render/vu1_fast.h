// vu1_fast.h - what the ahead-of-time translation of the VU1 microprograms is written
// against (vu1_translate.py writes the code, into local/recomp-out/gen-vu/vu1_fast.cpp:
// it is derived from the game and lives there; vu1_fast_none.cpp is linked when there is
// none).  The interpreter (vu1.cpp, vu1_step.h) stays the description of the machine: the
// helpers below are its lower-half operations as functions over the same Vu1 object, and
// a translated program run from any state must leave the object exactly as the
// interpreter would - registers, VU1 data memory, Q and its pipeline, the cycle counter,
// the flag history as far as anything can still read it, the instruction count.
#pragma once
#include "vu1_simd.h"

namespace render {

// One translated program: the pairs [start, start + count) of microprogram memory, used
// only while that memory holds the bytes it was made from (FNV-1a of them, as micro_hash
// in vu1.cpp).  run() starts at pair `at` and returns -1 when the program reached its end
// bit (v.pc is set), or the pair at which the interpreter has to go on: a place the
// translation does not follow, or an entry it was not made for.
struct Vu1Program {
    uint32_t start, count;
    uint64_t hash;
    int (*run)(Vu1& v, uint32_t at);
};
extern const Vu1Program vu1_fast_programs[];
extern const uint32_t vu1_fast_program_count;

// ---- flags ---------------------------------------------------------------------------------
static VU1_INLINE void vu1_flag_push(Vu1& v, uint64_t cyc, V4 value, uint32_t dest) {
    Vu1::FlagEvent& e = v.flag_ring[v.flag_count++ & 7];
    e.cyc = cyc;
    v4_store((uint8_t*)&e.value, value);
    e.dest = dest;
}
static VU1_INLINE uint32_t vu1_mac_of(const uint32_t* value, uint32_t dest) {
    uint32_t mac = 0;
    for (int k = 0; k < 4; k++) {
        if (!(dest & (8 >> k))) continue;
        if ((value[k] & 0x7FFFFFFF) == 0) mac |= 0x0008 >> k;
        if (value[k] & 0x80000000) mac |= 0x0080 >> k;
    }
    return mac;
}
// MAC flags as an instruction at cycle `cyc` reads them (Vu1::mac_seen)
static VU1_INLINE uint32_t vu1_mac_seen(const Vu1& v, uint64_t cyc) {
    for (uint32_t back = 1; back <= 8 && back <= v.flag_count; back++) {
        const Vu1::FlagEvent& e = v.flag_ring[(v.flag_count - back) & 7];
        if (e.cyc + 4 > cyc) continue;
        return vu1_mac_of(e.value.u, e.dest);
    }
    return 0;
}
// the same when the translator knows which instruction's result it is
static VU1_INLINE uint32_t vu1_mac_direct(V4 value, uint32_t dest) {
    uint32_t u[4];
    v4_store((uint8_t*)u, value);
    return vu1_mac_of(u, dest);
}
static VU1_INLINE uint32_t vu1_status(uint32_t mac) { return (mac & 0x000F ? 1u : 0u) | (mac & 0x00F0 ? 2u : 0u); }
static VU1_INLINE uint32_t vu1_clip_seen(const Vu1& v, uint64_t cyc) {
    for (uint32_t back = 1; back <= 8 && back <= v.clip_count; back++) {
        const Vu1::ClipEvent& e = v.clip_ring[(v.clip_count - back) & 7];
        if (e.cyc + 4 <= cyc) return e.value;
    }
    return 0;
}
static VU1_INLINE void vu1_clip_push(Vu1& v, uint64_t cyc, uint32_t value) {
    Vu1::ClipEvent& e = v.clip_ring[v.clip_count++ & 7];
    e.cyc = cyc;
    e.value = value;
}
// CLIP: fs against the fourth field of ft (the registers as they are); the clip register after it
static VU1_INLINE uint32_t vu1_clip_value(uint32_t clip_now, V4 fs, V4 ft) {
    float w = fabsf(vu_in(v4_get(ft, 3))), x = vu_in(v4_get(fs, 0)), y = vu_in(v4_get(fs, 1)), z = vu_in(v4_get(fs, 2));
    uint32_t c = 0;
    if (x > w) c |= 1;
    if (x < -w) c |= 2;
    if (y > w) c |= 4;
    if (y < -w) c |= 8;
    if (z > w) c |= 16;
    if (z < -w) c |= 32;
    return ((clip_now << 6) | c) & 0xFFFFFF;
}

// XGKICK from translated code (vu1.cpp): as the interpreter does it - the thread's own
// floating-point mode is put back while the GS model takes the packet.
void vu1_fast_kick(Vu1& v, uint32_t qword);

// ---- the divider (the result; the pipeline is in the generated code) -----------------------
static VU1_INLINE float vu1_div(uint32_t fs, uint32_t ft) {
    float a = vu_in(fs), b = vu_in(ft);
    const float big = 3.4028235e38f;
    return vu_out(b == 0 ? ((std::signbit(a) != std::signbit(b)) ? -big : big) : vu_div(a, b));
}
static VU1_INLINE float vu1_sqrt(uint32_t ft) { return vu_out(vu_sqrt(fabsf(vu_in(ft)))); }
static VU1_INLINE float vu1_rsqrt(uint32_t fs, uint32_t ft) {
    float a = vu_in(fs), b = vu_in(ft);
    const float big = 3.4028235e38f;
    return vu_out(b == 0 ? (std::signbit(a) ? -big : big) : vu_div(a, vu_sqrt(fabsf(b))));
}

// ---- memory --------------------------------------------------------------------------------
static VU1_INLINE uint8_t* vu1_at(uint8_t* data, uint32_t qword) { return data + (qword & 0x3FF) * 16; }
static VU1_INLINE uint32_t vu1_ilw(const uint8_t* m, int field) { uint16_t value; memcpy(&value, m + field * 4, 2); return value; }
static VU1_INLINE void vu1_isw(uint8_t* m, unsigned dest, uint32_t value) {
    for (int k = 0; k < 4; k++) if (dest & (8 >> k)) memcpy(m + k * 4, &value, 4);
}

}  // namespace render
