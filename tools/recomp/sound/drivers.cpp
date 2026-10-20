// drivers.cpp - the two I/O-processor programs the game calls, and the time line
// (rta_sound.h; behaviour and evidence in docs/issues/native-sound.md).
//
//   sd_call()      Sony's sound remote: one libsd function per call
//   stream_call()  the game's stream driver: commands 0x10 .. 0xc0
//   alarm()        the stream driver's 6 ms timer
//   advance_to()   renders, running the timer at its sample positions
#include <atomic>
#include "rta_sound.h"

#include <chrono>
#include <cstring>

namespace rta {
namespace snd {

namespace {

inline uint32_t word(const uint8_t* p, size_t size, unsigned index) {
    uint32_t v = 0;
    if ((index + 1) * 4 <= size) memcpy(&v, p + index * 4, 4);
    return v;
}

// stream s plays on voice 19 + kVoice[s] of core 1 (and the next one when it has two)
const int kVoice[3] = {0, 2, 3};
const int kVoiceStream[5] = {0, 0, 1, 2, 2};
const unsigned kStreamPitch = 0x7FE;          // 48000 * 0x7fe / 0x1000 = 23,976.6 Hz
const int kOrder[3] = {1, 0, 2};              // the timer looks at speech first
const unsigned kAlarmSamples = 288;           // 6 ms

inline unsigned voice_entry(int stream, int second) { return (unsigned)((19 + kVoice[stream] + second) * 2 + 1); }
inline uint32_t stream_base(int stream) { return 0x5010u + (uint32_t)stream * 0x1000u; }

}  // namespace

Engine::Engine() {
    memset(stream_, 0, sizeof stream_);
    memset(effect_, 0, sizeof effect_);
    memset(zero_input_, 0, sizeof zero_input_);
    memset(fake_stereo_, 0, sizeof fake_stereo_);
}

uint8_t* Engine::iop_at(uint32_t address, uint32_t size) {
    address &= 0x1FFFFFFF;
    if (!iop_ || address >= iop_size_ || size > iop_size_ - address) { stats.bad_address++; return nullptr; }
    return iop_ + address;
}

// ---- 0x80000701: libsd through SDRDRV ------------------------------------------------------
//
// The argument block is seven words; word 0 is the caller's own pointer, the libsd
// arguments start at word 1.  The answer is one word.  For the effect calls
// (0x8130 / 0x81a0 / 0x81b0 | core) the block is the effect attribute structure itself:
// { core, mode, depth left, depth right (16 bit each), delay, feedback }.

uint32_t Engine::transfer(uint32_t source, uint32_t spu_address, uint32_t size) {
    // the chip is fed in pieces of 64 bytes
    uint32_t rounded = (size + 63) & ~63u;
    if (uint8_t* p = iop_at(source, rounded)) {
        spu.write(spu_address & ~15u, p, rounded);
        stats.uploaded += rounded;
    }
    return rounded;
}

uint32_t Engine::batch(uint32_t address, uint32_t results, uint32_t count) {
    uint32_t done = 0;
    for (; done < count; done++) {
        uint8_t* p = iop_at(address + done * 8, 8);
        if (!p) break;
        uint16_t function, entry; uint32_t value, result = 0;
        memcpy(&function, p, 2); memcpy(&entry, p + 2, 2); memcpy(&value, p + 4, 4);
        switch (function) {
        case 0x01: spu.set_param(entry, value & 0xFFFF); break;
        case 0x02: spu.set_switch(entry, value); break;
        case 0x03: spu.set_addr(entry, value); break;
        case 0x04: spu.set_core_attr(entry, value & 0xFFFF); break;
        case 0x05: if (uint8_t* q = iop_at(value, 4)) { uint32_t e = entry; memcpy(q, &e, 4); } break;
        case 0x11: result = spu.get_param(entry); break;
        case 0x12: result = spu.get_switch(entry); break;
        case 0x13: result = spu.get_addr(entry); break;
        case 0x14: result = spu.get_core_attr(entry); break;
        default: return ~done;     // as the original: minus the number done, minus one
        }
        if (results)
            if (uint8_t* q = iop_at(results + done * 4, 4)) memcpy(q, &result, 4);
        stats.batch_commands++;
    }
    return done;
}

uint32_t Engine::sd_call(uint32_t function, const uint8_t* a, size_t size, uint8_t* reply, size_t reply_size) {
    uint32_t w1 = word(a, size, 1), w2 = word(a, size, 2), w3 = word(a, size, 3), w4 = word(a, size, 4), w5 = word(a, size, 5);
    unsigned core = function & 1;
    switch (function & 0xFFF0) {
    case 0x8000: spu.sd_init(); memset(effect_, 0, sizeof effect_); return 0;
    case 0x8010: spu.set_param(w1 & 0xFFFF, w2 & 0xFFFF); return 0;
    case 0x8020: return spu.get_param(w1 & 0xFFFF);
    case 0x8030: spu.set_switch(w1 & 0xFFFF, w2); return 0;
    case 0x8040: return spu.get_switch(w1 & 0xFFFF);
    case 0x8050: spu.set_addr(w1 & 0xFFFF, w2); return 0;
    case 0x8060: return spu.get_addr(w1 & 0xFFFF);
    case 0x8070: spu.set_core_attr(w1 & 0xFFFF, w2 & 0xFFFF); return 0;
    case 0x8080: return spu.get_core_attr(w1 & 0xFFFF);
    case 0x80B0: return batch(w1, w2, w3);
    case 0x80D0:                                   // voice transfer: channel, mode, source, SPU address, size
        if (!w5) return (uint32_t)-100;
        if ((w2 & 3) == 0) return transfer(w3, w4, w5);
        return (w5 + 63) & ~63u;                   // a read back from the chip: not needed
    case 0x80F0: return 1;                         // transfer status: finished
    case 0x8100: return 0;
    case 0x8150:                                   // clear / clean the effect work area
    case 0x8190: return 0;
    case 0x8130:                                   // set effect attributes, mode, parameters
    case 0x81A0:
    case 0x81B0: {
        Effect e;
        memset(&e, 0, sizeof e);
        memcpy(&e, a, size < sizeof e ? size : sizeof e);
        unsigned mode = (unsigned)e.mode & 0xFF;
        if (mode > 9) return (uint32_t)-100;
        Effect& now = effect_[core];
        if ((function & 0xFFF0) == 0x81B0) {
            if ((unsigned)now.mode != mode) return (uint32_t)-100;
        } else {
            now.mode = (int32_t)mode; now.delay = now.feedback = 0; now.depth_l = now.depth_r = 0;
            spu.set_param(0x0B80 | core, 0); spu.set_param(0x0C80 | core, 0);
        }
        if ((function & 0xFFF0) != 0x81A0) {
            now.depth_l = e.depth_l; now.depth_r = e.depth_r; now.delay = e.delay; now.feedback = e.feedback;
            spu.set_param(0x0B80 | core, (uint16_t)e.depth_l); spu.set_param(0x0C80 | core, (uint16_t)e.depth_r);
        }
        // Only "off" exists in the game's data.  Another mode would need the effect
        // processor, which is not here: it is counted and stays silent.
        if (mode != 0) stats.effect_modes++;
        return 0;
    }
    case 0x8140: {                                 // get effect attributes: answered as a structure
        Effect e = effect_[core];
        e.core = (int32_t)core;
        memset(reply, 0, reply_size);
        memcpy(reply, &e, reply_size < sizeof e ? reply_size : sizeof e);
        return e.core;
    }
    case 0x8160: case 0x8170: case 0x8180:         // interrupt and transfer handlers: nothing calls back
    case 0xE620: case 0xE630:
        return 0;
    }
    stats.unknown++;
    return 0;
}

// ---- 0x163a5: the stream driver ------------------------------------------------------------
//
// A stream owns a ring buffer in I/O-processor memory that the game fills from the disc
// (command 0x40 says how much was added) and a 0x1000-byte buffer in SPU2 memory at
// 0x5010 + stream * 0x1000 that its voice plays round and round.  The timer copies the
// next 0x800 bytes of the ring into the half of the SPU2 buffer that is not being played.
//   one voice  (stream 1)        0x800 bytes of one channel per half
//   two voices (streams 0, 2)    0x400 bytes left then 0x400 right; each voice plays its
//                                0x400 and is sent to the other half by its loop address;
//                                a one-channel entry is given to both voices
// Silence is copied when the ring holds less than a piece.

void Engine::stream_init() {
    alarm_on_ = false;
    spu.set_switch(0x1601, 0x1Fu << 19);
    for (int i = 0; i < 5; i++) {
        unsigned e = 0x27 + (unsigned)i * 2;
        uint32_t base = stream_base(kVoiceStream[i]);
        spu.set_param(e, 0x3FFF);
        spu.set_param(e | 0x100, 0x3FFF);
        spu.set_param(e | 0x200, kStreamPitch);
        spu.set_addr(e | 0x2040, base);
        spu.set_addr(e | 0x2140, base);
        spu.set_param(e | 0x300, 0xFF);
        spu.set_param(e | 0x400, 0x1FC0);
    }
    for (int s = 0; s < 3; s++) {
        memset(zero_input_, 0, sizeof zero_input_);
        for (int i = 1; i < 0x1000; i += 0x10) zero_input_[i] = 2;
        zero_input_[1] = 6; zero_input_[0xFF1] = 3;
        spu.write(stream_base(s), zero_input_, 0x1000);
        stream_[s].target = 0x3FFF; stream_[s].volume = 0; stream_[s].scale = 0x100;
    }
    stream_[0].flags |= 2; stream_[2].flags |= 2;
    spu.set_switch(0x1501, 0x1Fu << 19);
    force_volume_ = 1;
    set_alarm();
}

void Engine::stream_call(uint32_t function, const uint8_t* a, size_t size) {
    uint32_t w0 = word(a, size, 0), w1 = word(a, size, 1), w2 = word(a, size, 2), w3 = word(a, size, 3);
    Stream* st = w0 < 3 ? &stream_[w0] : nullptr;
    switch (function & 0xFFF0) {
    case 0x10: status_[0] = spu.get_param(0x527) & 0xFFFF; break;
    case 0x20: stream_init(); break;
    case 0x30:                                     // stream, ring address, ring size
        if (!st) break;
        memset(st, 0, sizeof *st);
        st->buffer = w1; st->size = (int32_t)w2;
        break;
    case 0x40:                                     // stream, bytes added, rate, two channels (16 bit) | flags (16 bit)
        if (!st || st->size <= 0) { stats.unknown++; break; }
        st->write = (int32_t)(((int64_t)st->write + (int32_t)w1) % st->size);
        if (st->count >= 32) { stats.unknown++; break; }
        st->que[st->count].rate = (int32_t)w2;
        st->que[st->count].stereo = (int16_t)(w3 & 0xFFFF);
        st->que[st->count].left = (int32_t)w1;
        st->que[st->count].flags = (int16_t)(w3 >> 16);
        st->count++;
        stats.stream_bytes[w0] += w1;
        break;
    case 0x50:                                     // status
        for (int s = 0; s < 3; s++) {
            status_[s * 4] = (uint32_t)stream_[s].write; status_[s * 4 + 1] = (uint32_t)stream_[s].read;
            status_[s * 4 + 2] = (uint32_t)stream_[s].volume; status_[s * 4 + 3] = (uint32_t)stream_[s].played;
        }
        break;
    case 0x60:                                     // drop what is buffered
        if (!st || st->size <= 0) { stats.unknown++; break; }
        st->write = (st->write + 0x7FF) & ~0x7FF;
        st->read = st->write % st->size;
        st->played = 0; st->count = 0;
        break;
    case 0x70: if (st) st->target = (int32_t)w1; break;
    case 0x80:                                     // two-channel output on/off, a volume scale per stream
        stereo_enable_ = (int32_t)w0;
        stream_[0].scale = (int32_t)w1; stream_[1].scale = (int32_t)w2; stream_[2].scale = (int32_t)w3;
        force_volume_ = 1;
        break;
    case 0x90: break;                              // load a module: nothing to load here
    case 0xA0: case 0xB0: alarm_on_ = false; break;   // timer off (around sample uploads)
    case 0xC0: set_alarm(); break;                 // timer on: first after 10 ms
    default: stats.unknown++;
    }
}

// The host's volume for the MUSIC alone: stream 2 of the stream driver carries the music (speech is on streams 0 and
// 1, effects are voices of their own), so a host can turn the game's music down - under music of its own, say - and
// leave speech and effects as they are.  0..1; any thread.
static std::atomic<int> g_music_gain{0x100}, g_music_gain_changed{0};
void set_music_gain(float gain) {
    int g = (int)(gain * 256.0f + 0.5f);
    g = g < 0 ? 0 : g > 0x100 ? 0x100 : g;
    if (g_music_gain.exchange(g) != g) g_music_gain_changed.store(1);
}

void Engine::alarm() {
    stats.alarms++;
    if (g_music_gain_changed.exchange(0)) force_volume_ = 1;
    // volumes move towards their targets: down 0x20 a tick, up 0x40 (stream 0) or 0xc0
    for (int s = 0; s < 3; s++) {
        Stream& st = stream_[s];
        if (st.target == st.volume && !force_volume_) continue;
        if (st.target < st.volume) {
            st.volume -= 0x20;
            if (st.volume < st.target) st.volume = st.target;
        } else if (st.volume < st.target) {
            st.volume += s == 0 ? 0x40 : 0xC0;
            if (st.target < st.volume) st.volume = st.target;
        }
        unsigned v = (unsigned)((st.volume * st.scale) >> 8) & 0xFFFF;
        if (s == 2) v = (v * (unsigned)g_music_gain.load()) >> 8;
        unsigned e = voice_entry(s, 0), e2 = voice_entry(s, 1);
        if (!(st.flags & 2)) {
            spu.set_param(e, v); spu.set_param(e | 0x100, v);
        } else if (!stereo_enable_) {
            spu.set_param(e | 0x100, v); spu.set_param(e, v);
            spu.set_param(e2 | 0x100, v); spu.set_param(e2, v);
        } else {
            spu.set_param(e | 0x100, 0); spu.set_param(e, v);
            spu.set_param(e2 | 0x100, v); spu.set_param(e2, 0);
        }
    }
    force_volume_ = 0;

    // one stream per tick gets its next piece (an upload is in flight for the rest of it)
    for (int k = 0; k < 3; k++) {
        int s = kOrder[k];
        Stream& st = stream_[s];
        if (st.size <= 0) continue;
        int32_t need = 0x800;
        bool fake = false;
        uint32_t base = stream_base(s);
        unsigned e = voice_entry(s, 0), e2 = voice_entry(s, 1);
        int32_t nax = (int32_t)spu.get_addr(e | 0x2240);
        int32_t left = (st.write - st.read + st.size) % st.size;
        if (st.flags & 1) left = 0x100000;
        if ((st.flags & 2) && st.que[0].stereo == 0) { fake = true; need = 0x400; }
        if (!st.started && need <= left) st.started = 1;
        int32_t half = nax - (int32_t)base > 0x800 ? 1 : 0;
        if (half == st.last_half) continue;

        if (left < need) st.started = 0;
        uint8_t* src = st.started ? iop_at(st.buffer + (uint32_t)st.read, 0x800) : zero_input_;
        if (!src) src = zero_input_;
        if (!st.started) stats.starved[s]++;
        if (fake) {
            memcpy(fake_stereo_, src, 0x400); memcpy(fake_stereo_ + 0x400, src, 0x400);
            src = fake_stereo_;
        }
        // the flag byte of every block is replaced: "inside a loop"; the piece's ends
        // carry the jump
        for (int i = 0; i < 0x800; i += 0x10) src[i + 1] = (src[i + 1] & 0xF8) | 2;
        if (!(st.flags & 2)) {
            if (half == 0) src[0x7F1] = (src[0x7F1] & 0xF8) | 3;      // second half: end, back to the loop start
            else src[1] = (src[1] & 0xF8) | 6;                        // first half: loop start
        } else {
            spu.set_addr(e | 0x2140, half == 0 ? base + 0x800 : base);
            spu.set_addr(e2 | 0x2140, half == 0 ? base + 0xC00 : base + 0x400);
            src[0x3F1] = (src[0x3F1] & 0xF8) | 3;
            src[0x7F1] = (src[0x7F1] & 0xF8) | 3;
        }
        spu.write(half == 0 ? base + 0x800 : base, src, 0x800);
        stats.refills[s]++;
        if (st.started) {
            if (st.que[0].flags & 1) { st.played = 0; st.que[0].flags &= ~1; }
            st.played += need;
            st.read = (st.read + need) % st.size;
            st.que[0].left -= need;
            if (st.que[0].left == 0 && st.count > 0) {
                for (int i = 0; i + 1 < st.count; i++) st.que[i] = st.que[i + 1];
                st.count--;
            }
        }
        st.last_half = half;
        break;
    }
}

// ---- remote calls and time ---------------------------------------------------------------

bool Engine::rpc(uint32_t server, uint32_t function, const uint8_t* send, size_t send_size,
                 uint8_t* reply, size_t reply_size) {
    if (server != SERVER_SD && server != SERVER_STREAM) return false;
    uint8_t none[4] = {0};
    if (!send) { send = none; send_size = 0; }
    if (reply_size > 64) reply_size = 64;
    uint8_t answer[64];
    memset(answer, 0, sizeof answer);
    if (server == SERVER_SD) {
        stats.calls[0][function & 0xFFFF]++;
        uint32_t result = sd_call(function, send, send_size, answer, sizeof answer);
        if ((function & 0xFFF0) != 0x8140) memcpy(answer, &result, 4);
    } else {
        stats.calls[1][function & 0xFFFF]++;
        stream_call(function, send, send_size);
        // the driver answers every call with the same block: the last status, then its
        // copy of the arguments
        memcpy(answer, status_, sizeof status_);
        memcpy(answer + 48, send, send_size < 16 ? send_size : 16);
    }
    if (reply && reply_size) memcpy(reply, answer, reply_size);
    return true;
}

// A host's own sound added to the output (app/bossmusic.cpp: the player's music for boss fights): called with every
// block AFTER the chip has made it, before it goes to the WAV file or the device.  Nothing of the chip, the drivers
// or what the game is told depends on it.  Any thread sets it; it runs on whichever thread renders.
static std::atomic<void (*)(int16_t*, size_t)> g_host_mix{nullptr};
void set_host_mix(void (*mix)(int16_t*, size_t)) { g_host_mix.store(mix, std::memory_order_release); }

void Engine::render(uint64_t frames) {
    int16_t buffer[1024 * 2];
    while (frames) {
        size_t n = frames > 1024 ? 1024 : (size_t)frames;
        spu.render(buffer, n);
        if (auto mix = g_host_mix.load(std::memory_order_acquire)) mix(buffer, n);
        if (sink_) sink_->write(buffer, n);
        position_ += n;
        frames -= n;
    }
}

void Engine::advance_to(uint64_t sample) {
    if (sample <= position_) return;
    auto t0 = std::chrono::steady_clock::now();
    if (sample - position_ > max_jump) {
        // the clock jumped (a machine resumed far into its time): do not render the gap
        uint64_t skip = sample - position_;
        stats.skipped += skip;
        if (alarm_on_) alarm_at_ += skip;
        position_ = sample;
        return;
    }
    while (alarm_on_ && alarm_at_ <= sample) {
        if (alarm_at_ > position_) render(alarm_at_ - position_);
        alarm_at_ += kAlarmSamples;
        alarm();
    }
    render(sample - position_);
    stats.render_seconds += std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
}

void Engine::report(FILE* out) const {
    static const char* const kNames[2] = {"sd", "stream"};
    fprintf(out, "sound: %.2f s rendered (%llu samples at 48 kHz) in %.3f s of processor time (%.2f%% of real time)",
            position_ / 48000.0, (unsigned long long)spu.stats.frames, stats.render_seconds,
            position_ ? stats.render_seconds * 100.0 * 48000.0 / (double)position_ : 0.0);
    if (stats.skipped) fprintf(out, ", %llu samples skipped by clock jumps", (unsigned long long)stats.skipped);
    fprintf(out, "\n");
    for (int s = 0; s < 2; s++) {
        fprintf(out, "sound: %s calls:", kNames[s]);
        for (const auto& kv : stats.calls[s]) fprintf(out, " %x x%llu", kv.first, (unsigned long long)kv.second);
        fprintf(out, "\n");
    }
    fprintf(out, "sound: %llu key-ons, %llu key-offs, %llu voices ran to their end; %llu batch commands; %llu bytes uploaded; peak %d, %llu samples at full scale\n",
            (unsigned long long)spu.stats.key_on, (unsigned long long)spu.stats.key_off, (unsigned long long)spu.stats.ended,
            (unsigned long long)stats.batch_commands, (unsigned long long)stats.uploaded, spu.stats.peak,
            (unsigned long long)spu.stats.clipped);
    fprintf(out, "sound: stream timer %llu ticks; pieces copied (of them silence) per stream: %llu (%llu), %llu (%llu), %llu (%llu); bytes queued %llu, %llu, %llu\n",
            (unsigned long long)stats.alarms,
            (unsigned long long)stats.refills[0], (unsigned long long)stats.starved[0],
            (unsigned long long)stats.refills[1], (unsigned long long)stats.starved[1],
            (unsigned long long)stats.refills[2], (unsigned long long)stats.starved[2],
            (unsigned long long)stats.stream_bytes[0], (unsigned long long)stats.stream_bytes[1], (unsigned long long)stats.stream_bytes[2]);
    if (stats.unknown || stats.bad_address || stats.effect_modes || spu.stats.key_on_unwritten || spu.stats.sweep_volumes)
        fprintf(out, "sound: NOT HANDLED: %llu unknown or refused commands, %llu addresses outside I/O-processor memory, %llu effect modes other than off, %llu key-ons at memory never uploaded, %llu sweep volumes\n",
                (unsigned long long)stats.unknown, (unsigned long long)stats.bad_address, (unsigned long long)stats.effect_modes,
                (unsigned long long)spu.stats.key_on_unwritten, (unsigned long long)spu.stats.sweep_volumes);
    if (sink_) sink_->report(out);
}

}  // namespace snd
}  // namespace rta

// for a host outside the runtime (tools/godot/lib/rtag.cpp: option "music_volume")
extern "C" void rta_sound_set_music_gain(float gain) { rta::snd::set_music_gain(gain); }
// a host's own sound mixed into the output (app/bossmusic.cpp); nullptr: none
extern "C" void rta_sound_set_host_mix(void (*mix)(int16_t* stereo, size_t frames)) { rta::snd::set_host_mix(mix); }
