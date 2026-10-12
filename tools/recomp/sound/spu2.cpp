// spu2.cpp - the SPU2 sound chip as far as this game uses it (rta_sound.h).
//
// Two cores of 24 voices each over 2 MB of sample memory.  A voice plays 16-byte ADPCM
// blocks (28 samples each) at a rate set by its pitch register (0x1000 = 48,000 Hz),
// through a four-tap interpolation filter, an ADSR envelope and a left/right volume.
// Core 0's mix enters core 1 as its external input; core 1's output is what is heard.
//
// Not modelled, because the game never asks for it (docs/issues/native-sound.md,
// "What is not there"): the effect (reverb) processor - every level sets effect mode
// "off" with depth 0 -, pitch modulation, noise, volume sweeps, the block-transfer input,
// interrupts on a memory address.
//
// The chip's interpolation table lives in its ROM.  It is replaced here by the function it
// follows closely, a Gaussian of sigma 0.567 samples sampled at the four taps and scaled to
// unit gain; the result is the chip's soft treble, not its exact numbers.
#include "rta_sound.h"

#include <cmath>
#include <cstring>

namespace rta {
namespace snd {

namespace {

inline int32_t clamp16(int32_t x) { return x < -32768 ? -32768 : x > 32767 ? 32767 : x; }

// A volume register in direct mode holds 15 bits, signed: value * 2 is the gain in 1/32768.
inline int32_t volume(uint16_t reg) { return (int16_t)(reg << 1); }

const int kFilter[5][2] = {{0, 0}, {60, 0}, {115, -52}, {98, -55}, {122, -60}};

// ADPCM block flags
enum { F_END = 1, F_REPEAT = 2, F_START = 4 };

}  // namespace

Spu2::Spu2() : interpolation_(GAUSS) {
    for (int i = 0; i < 256; i++) {
        double f = i / 256.0, d[4] = {1.0 + f, f, 1.0 - f, 2.0 - f}, w[4], sum = 0;
        for (int k = 0; k < 4; k++) { w[k] = exp(-d[k] * d[k] / (2 * 0.567 * 0.567)); sum += w[k]; }
        for (int k = 0; k < 4; k++) gauss_[i][k] = (int16_t)lrint(w[k] / sum * 32767.0);
    }
    reset();
}

void Spu2::reset() {
    memset(ram, 0, sizeof ram);
    memset(written_, 0, sizeof written_);
    memset(core_, 0, sizeof core_);
    for (Core& c : core_)
        for (Voice& v : c.v) v.parked = true;
    stats = Stats();
}

// What sceSdInit(cold) does to the chip: a 16-byte block of silence that loops to itself
// (flags 7) at 0x5000, every voice pointed at it with zero volume and full pitch, keyed on
// and off again (so every "ended" flag is set), all voices routed to the dry and the
// effect mix, master and effect volumes 0, core 1 taking core 0 at full volume.
void Spu2::sd_init() {
    uint8_t silent[16] = {0x00, 0x07};
    write(0x5000, silent, 16);
    for (int ci = 0; ci < CORES; ci++) {
        Core& c = core_[ci];
        for (int n = 0; n < VOICES; n++) {
            Voice& v = c.v[n];
            v.voll = v.volr = 0; v.pitch = 0x3FFF; v.adsr1 = v.adsr2 = 0;
            v.ssa = 0x5000; v.phase = OFF; v.envx = 0;
        }
        c.attr = 0xC000 | ci;
        c.vmixl = c.vmixr = c.vmixel = c.vmixer = 0xFFFFFF;
        c.mmix = ci ? 0xFFC : 0xFF0;
        c.mvoll = c.mvolr = c.evoll = c.evolr = 0;
        c.eea = ci ? 0x1FFFFF : 0x1DFFFF;
        c.esa = c.eea - 0xF;
        c.avoll = c.avolr = ci ? 0x7FFF : 0;
        c.bvoll = c.bvolr = 0;
        c.pmon = c.non = 0;
        set_switch(0x1500 | ci, 0xFFFFFF);
        set_switch(0x1600 | ci, 0xFFFFFF);
        // the silent block ends at once: the voices sit on it, ended
        for (int n = 0; n < VOICES; n++) { c.v[n].phase = OFF; c.v[n].envx = 0; c.v[n].parked = true; }
        c.endx = 0xFFFFFF;
    }
}

void Spu2::write(uint32_t address, const uint8_t* data, uint32_t size) {
    address &= RAM_BYTES - 1;
    if (size > RAM_BYTES - address) size = RAM_BYTES - address;
    memcpy(ram + address, data, size);
    for (uint32_t p = address >> 6; p <= (address + size - 1) >> 6 && size; p++) written_[p >> 3] |= 1 << (p & 7);
    // a silent voice parked on a block that has now changed plays on from there
    for (Core& c : core_)
        for (Voice& v : c.v)
            if (v.parked && v.nax + 16 > address && v.nax < address + size) v.parked = false;
}

// ---- registers ---------------------------------------------------------------------------

void Spu2::set_param(unsigned entry, unsigned value) {
    Core& c = core_[entry & 1];
    Voice& v = c.v[(entry >> 1) & 0x1F];
    unsigned reg = entry >> 8;
    if (reg < 8 && ((entry >> 1) & 0x1F) >= VOICES) return;
    switch (reg) {
    case 0x00: v.voll = value; if (value & 0x8000) stats.sweep_volumes++; break;
    case 0x01: v.volr = value; if (value & 0x8000) stats.sweep_volumes++; break;
    case 0x02: v.pitch = value; break;
    case 0x03: v.adsr1 = value; break;
    case 0x04: v.adsr2 = value; break;
    case 0x08: c.mmix = value; break;
    case 0x09: c.mvoll = value; break;
    case 0x0A: c.mvolr = value; break;
    case 0x0B: c.evoll = value; break;
    case 0x0C: c.evolr = value; break;
    case 0x0D: c.avoll = value; break;
    case 0x0E: c.avolr = value; break;
    case 0x0F: c.bvoll = value; break;
    case 0x10: c.bvolr = value; break;
    }
}

unsigned Spu2::get_param(unsigned entry) const {
    const Core& c = core_[entry & 1];
    const Voice& v = c.v[(entry >> 1) & 0x1F];
    unsigned reg = entry >> 8;
    if (reg < 8 && ((entry >> 1) & 0x1F) >= VOICES) return 0;
    switch (reg) {
    case 0x00: return v.voll;
    case 0x01: return v.volr;
    case 0x02: return v.pitch;
    case 0x03: return v.adsr1;
    case 0x04: return v.adsr2;
    case 0x05: return (unsigned)v.envx;
    case 0x06: return (uint16_t)volume(v.voll);
    case 0x07: return (uint16_t)volume(v.volr);
    case 0x08: return c.mmix;
    case 0x09: return c.mvoll;
    case 0x0A: return c.mvolr;
    case 0x0B: return c.evoll;
    case 0x0C: return c.evolr;
    case 0x0D: return c.avoll;
    case 0x0E: return c.avolr;
    case 0x0F: return c.bvoll;
    case 0x10: return c.bvolr;
    case 0x11: return (uint16_t)volume(c.mvoll);
    case 0x12: return (uint16_t)volume(c.mvolr);
    }
    return 0;
}

void Spu2::set_switch(unsigned entry, uint32_t value) {
    Core& c = core_[entry & 1];
    value &= 0xFFFFFF;
    switch (entry >> 8) {
    case 0x13: c.pmon = value; break;
    case 0x14: c.non = value; break;
    case 0x15: for (int n = 0; n < VOICES; n++) if (value >> n & 1) key_on(c, n); break;
    case 0x16: for (int n = 0; n < VOICES; n++) if (value >> n & 1) key_off(c, n); break;
    case 0x17: c.endx = 0; break;        // any write clears the flags
    case 0x18: c.vmixl = value; break;
    case 0x19: c.vmixel = value; break;
    case 0x1A: c.vmixr = value; break;
    case 0x1B: c.vmixer = value; break;
    }
}

uint32_t Spu2::get_switch(unsigned entry) const {
    const Core& c = core_[entry & 1];
    switch (entry >> 8) {
    case 0x13: return c.pmon;
    case 0x14: return c.non;
    case 0x17: return c.endx;
    case 0x18: return c.vmixl;
    case 0x19: return c.vmixel;
    case 0x1A: return c.vmixr;
    case 0x1B: return c.vmixer;
    }
    return 0;
}

// libsd halves the byte address and drops the low three bits of the word address: sample
// addresses are multiples of 16 bytes.
void Spu2::set_addr(unsigned entry, uint32_t value) {
    Core& c = core_[entry & 1];
    Voice& v = c.v[(entry >> 1) & 0x1F];
    uint32_t a = value & (RAM_BYTES - 1) & ~15u;
    switch (entry >> 8) {
    case 0x1C: c.esa = a; break;
    case 0x1D: c.eea = value | 0x1FFFF; break;      // only the top bits exist
    case 0x1E: c.tsa = a; break;
    case 0x1F: c.irqa = a; break;
    case 0x20: v.ssa = a; break;
    case 0x21: v.lsax = a; v.lsax_written = true; if (v.parked && a != v.nax) v.parked = false; break;
    }
}

uint32_t Spu2::get_addr(unsigned entry) const {
    const Core& c = core_[entry & 1];
    const Voice& v = c.v[(entry >> 1) & 0x1F];
    switch (entry >> 8) {
    case 0x1C: return c.esa;
    case 0x1D: return c.eea;
    case 0x1E: return c.tsa;
    case 0x1F: return c.irqa;
    case 0x20: return v.ssa;
    case 0x21: return v.lsax;
    // the chip's read pointer: past the header, two bytes for every four samples taken
    case 0x22: return v.nax + 2 + (v.pos >= 28 ? 12 : (v.pos >> 2) * 2);
    }
    return 0;
}

void Spu2::set_core_attr(unsigned entry, unsigned value) {
    Core& c = core_[entry & 1];
    switch (entry & 0xE) {
    case 0x2: c.attr = (c.attr & ~0x80) | (value ? 0x80 : 0); break;     // effect enable
    case 0x4: c.attr = (c.attr & ~0x40) | (value ? 0x40 : 0); break;     // interrupt enable
    case 0x6: c.attr = (c.attr & ~0x4000) | (value ? 0x4000 : 0); break; // "mute enable": 1 = sound on
    case 0x8: c.attr = (c.attr & ~0x3F00) | ((value & 0x3F) << 8); break;
    }
}

unsigned Spu2::get_core_attr(unsigned entry) const {
    const Core& c = core_[entry & 1];
    switch (entry & 0xE) {
    case 0x2: return c.attr >> 7 & 1;
    case 0x4: return c.attr >> 6 & 1;
    case 0x6: return c.attr >> 14 & 1;
    case 0x8: return c.attr >> 8 & 0x3F;
    }
    return 0;
}

// ---- voices ------------------------------------------------------------------------------

void Spu2::load_block(Core& c, int n) {
    Voice& v = c.v[n];
    const uint8_t* b = ram + (v.nax & (RAM_BYTES - 1) & ~15u);
    int shift = b[0] & 15, filter = b[0] >> 4;
    v.flags = b[1];
    if (shift > 12) shift = 9;
    int f0 = filter < 5 ? kFilter[filter][0] : 0, f1 = filter < 5 ? kFilter[filter][1] : 0;
    // a block marked "loop start" becomes the loop address, unless software has set one
    // since the key-on
    if ((v.flags & F_START) && !v.lsax_written) v.lsax = v.nax;
    int32_t h1 = v.hist1, h2 = v.hist2;
    for (int i = 0; i < 28; i++) {
        int nibble = (b[2 + (i >> 1)] >> ((i & 1) * 4)) & 15;
        int32_t s = (int16_t)(nibble << 12) >> shift;
        s = clamp16(s + ((h1 * f0 + h2 * f1 + 32) >> 6));
        v.block[i] = (int16_t)s;
        h2 = h1; h1 = s;
    }
    v.hist1 = h1; v.hist2 = h2;
    v.pos = 0;
}

void Spu2::next_sample(Core& c, int n) {
    Voice& v = c.v[n];
    if (v.pos >= 28) {
        // the block is finished: act on its flags, then fetch the next one
        if (v.flags & F_END) {
            if (!(c.endx >> n & 1)) stats.ended++;
            c.endx |= 1u << n;
            v.nax = v.lsax;
            if (!(v.flags & F_REPEAT)) { v.phase = OFF; v.envx = 0; }
        } else {
            v.nax = (v.nax + 16) & (RAM_BYTES - 1);
        }
        load_block(c, n);
        // silent, and on a block that leads back to itself: nothing more can happen
        // until a key-on, an upload over the block or a new loop address
        if (v.phase == OFF && (v.flags & F_END) && v.lsax == v.nax) { c.endx |= 1u << n; v.parked = true; }
    }
    v.ring[0] = v.ring[1]; v.ring[1] = v.ring[2]; v.ring[2] = v.ring[3];
    v.ring[3] = v.block[v.pos++];
}

void Spu2::key_on(Core& c, int n) {
    Voice& v = c.v[n];
    stats.key_on++;
    c.endx &= ~(1u << n);
    v.nax = v.ssa;
    v.hist1 = v.hist2 = 0;
    v.ring[0] = v.ring[1] = v.ring[2] = v.ring[3] = 0;
    v.counter = 0;
    v.envx = 0; v.env_count = 0;
    v.phase = ATTACK;
    v.lsax_written = false;
    v.parked = false;
    if (!(written_[(v.nax >> 6) >> 3] >> ((v.nax >> 6) & 7) & 1)) {
        // nothing was ever uploaded here (a machine resumed from a memory image has an
        // empty sample memory): the chip would play zeros for ever and never report the
        // end; say "ended" so that the game's voice table keeps turning over
        stats.key_on_unwritten++;
        v.phase = OFF; v.parked = true;
        c.endx |= 1u << n;
        return;
    }
    load_block(c, n);
}

void Spu2::key_off(Core& c, int n) {
    Voice& v = c.v[n];
    stats.key_off++;
    if (v.phase != OFF) v.phase = RELEASE, v.env_count = 0;
}

// The envelope generator: per phase a 5-bit shift and a small step; the level moves by
// step << (11 - shift) every 1 << (shift - 11) samples, the falling exponential forms
// scaled by the level, the rising one four times slower above 0x6000.
void Spu2::envelope(Voice& v) {
    int shift, step;
    bool expo, down;
    switch (v.phase) {
    case ATTACK:
        expo = v.adsr1 >> 15; down = false;
        shift = v.adsr1 >> 10 & 0x1F; step = 7 - (v.adsr1 >> 8 & 3);
        break;
    case DECAY:
        if (v.envx <= ((v.adsr1 & 0xF) + 1) * 0x800) { v.phase = SUSTAIN; v.env_count = 0; return envelope(v); }
        expo = true; down = true; shift = v.adsr1 >> 4 & 0xF; step = -8;
        break;
    case SUSTAIN:
        expo = v.adsr2 >> 15; down = v.adsr2 >> 14 & 1;
        shift = v.adsr2 >> 8 & 0x1F;
        step = down ? -8 + (v.adsr2 >> 6 & 3) : 7 - (v.adsr2 >> 6 & 3);
        break;
    case RELEASE:
        expo = v.adsr2 >> 5 & 1; down = true; shift = v.adsr2 & 0x1F; step = -8;
        break;
    default:
        return;
    }
    uint32_t cycles = 1u << (shift > 11 ? shift - 11 : 0);
    int32_t delta = step << (shift < 11 ? 11 - shift : 0);
    if (expo && !down && v.envx > 0x6000) cycles *= 4;
    if (expo && down) delta = (delta * v.envx) >> 15;
    if (++v.env_count < cycles) return;
    v.env_count = 0;
    int32_t level = v.envx + delta;
    v.envx = level < 0 ? 0 : level > 0x7FFF ? 0x7FFF : level;
    if (v.phase == ATTACK && v.envx >= 0x7FFF) v.phase = DECAY;
    else if (v.phase == RELEASE && v.envx == 0) v.phase = OFF;
}

inline int32_t Spu2::voice_tick(Core& c, int n) {
    Voice& v = c.v[n];
    int32_t s = 0;
    if (v.phase != OFF) {
        unsigned i = v.counter >> 4 & 0xFF;
        switch (interpolation_) {
        case GAUSS: {
            const int16_t* g = gauss_[i];
            s = (g[0] * v.ring[0] + g[1] * v.ring[1] + g[2] * v.ring[2] + g[3] * v.ring[3]) >> 15;
            break;
        }
        case LINEAR:
            s = v.ring[2] + (((v.ring[3] - v.ring[2]) * (int32_t)(v.counter & 0xFFF)) >> 12);
            break;
        default:
            s = v.ring[3];
        }
        envelope(v);
        s = (s * v.envx) >> 15;
    }
    unsigned step = v.pitch > 0x3FFF ? 0x3FFF : v.pitch;
    v.counter += step;
    while (v.counter >= 0x1000) {
        v.counter -= 0x1000;
        next_sample(c, n);
        if (v.parked) { v.counter = 0; break; }
    }
    return s;
}

int Spu2::voices_sounding() const {
    int count = 0;
    for (const Core& c : core_)
        for (const Voice& v : c.v) count += v.phase != OFF;
    return count;
}

// Per output sample: each core sums its voices (left and right volumes, the VMIX switches
// choosing who takes part) and saturates; core 0 times its master volume is core 1's
// external input, scaled by core 1's AVOL; MMIX gates what reaches the output; core 1's
// master volume and a last saturation follow.
void Spu2::render(int16_t* out, size_t frames) {
    stats.frames += frames;
    for (size_t f = 0; f < frames; f++) {
        int32_t ext_l = 0, ext_r = 0, out_l = 0, out_r = 0;
        for (int ci = 0; ci < CORES; ci++) {
            Core& c = core_[ci];
            int32_t l = 0, r = 0;
            for (int n = 0; n < VOICES; n++) {
                Voice& v = c.v[n];
                if (v.parked) continue;
                int32_t s = voice_tick(c, n);
                if (!s || (mute_[ci] >> n & 1)) continue;
                if (c.vmixl >> n & 1) l += (s * volume(v.voll)) >> 15;
                if (c.vmixr >> n & 1) r += (s * volume(v.volr)) >> 15;
            }
            l = (c.mmix & 0x800) ? clamp16(l) : 0;
            r = (c.mmix & 0x400) ? clamp16(r) : 0;
            if (ci == 0) {
                ext_l = (l * volume(c.mvoll)) >> 15;
                ext_r = (r * volume(c.mvolr)) >> 15;
            } else {
                if (c.mmix & 0x008) l += (ext_l * (int16_t)c.avoll) >> 15;
                if (c.mmix & 0x004) r += (ext_r * (int16_t)c.avolr) >> 15;
                out_l = (clamp16(l) * volume(c.mvoll)) >> 15;
                out_r = (clamp16(r) * volume(c.mvolr)) >> 15;
                if (!(c.attr & 0x4000)) out_l = out_r = 0;
            }
        }
        if (out_l <= -32768 || out_l >= 32767 || out_r <= -32768 || out_r >= 32767) stats.clipped++;
        out_l = clamp16(out_l); out_r = clamp16(out_r);
        int a = out_l < 0 ? -out_l : out_l, b = out_r < 0 ? -out_r : out_r;
        if (a > stats.peak) stats.peak = a;
        if (b > stats.peak) stats.peak = b;
        out[f * 2] = (int16_t)out_l; out[f * 2 + 1] = (int16_t)out_r;
    }
}

}  // namespace snd
}  // namespace rta
