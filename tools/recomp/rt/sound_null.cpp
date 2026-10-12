// sound_null.cpp - the two sound servers of the I/O processor, without sound.
//
// The game reaches sound through two RPC servers: Sony's sound remote 0x80000701
// (SDRDRV.IRX in front of LIBSD.IRX: SPU2 registers, sample uploads, effects) and its own
// stream driver 0x000163a5 (HELLO.IRX).  Nothing is mixed here.  What is modelled is what
// the game reads back and acts on:
//   - the stream driver's 0x40-byte status block (per stream: write position, read
//     position, current volume, bytes played), with the read position advancing on the
//     virtual clock at the stream's byte rate - the game feeds a stream from the disc as
//     the driver consumes it and treats "read position == write position" as finished;
//   - the answers of the sound remote that have a value: the size of a sample upload, the
//     transfer status, the batch count, and the voice end flags (all voices ended, which
//     is what the reference emulator's sound library answered in the captured boot).
// A file that makes sound replaces this one (build.py --sound FILE); the three functions
// declared in rt.h are the whole interface.
//
// Observed traffic (reference boot in the emulator rig, 3,200 fields), function numbers
// as the game passes them: 0x80000701: 0x8000 init, 0x8010 set parameter, 0x8030 set
// switch, 0x8040 get switch, 0x8050 set address, 0x8070 set core attribute, 0x80b0
// batch, 0x80d0 voice transfer, 0x80f0 transfer status, 0x8190 / 0x81a1 / 0x81b1
// effects.  0x163a5: 0x20 init, 0x30 stream buffer (stream, I/O-processor address,
// size), 0x40 data written (stream, write position, sample rate, flags), 0x50 status,
// 0x60 stop, 0x70 volume target, 0x80 volumes, 0xb0 / 0xc0 sample upload.
#include "rt.h"

#include <cstdio>
#include <map>

namespace {

struct Stream {
    u32 buffer = 0, size = 0;       // ring in I/O-processor memory
    u32 write = 0, read = 0, played = 0;
    u32 rate = 0;                   // bytes per second while playing
    bool playing = false;
    u32 volume = 0, target = 0;
    u64 byte_clock = 0;             // cycles not yet turned into bytes
};
Stream g_stream[3];
// the sizes the game gives its three stream buffers; in force until it says otherwise
// (a resumed image never repeats function 0x30)
struct Defaults { Defaults() { g_stream[0].size = 0x19000; g_stream[1].size = 0x1E000; g_stream[2].size = 0x40000; } } g_defaults;
u64 g_last_cycles, g_volume_clock;
std::map<u32, u64> g_calls;
u64 g_uploaded;

void advance() {
    u64 t = rt_cycles();
    u64 elapsed = t - g_last_cycles;
    g_last_cycles = t;
    // the driver's volume ramp: one step per 256 output samples (48 kHz)
    g_volume_clock += elapsed;
    u64 steps = g_volume_clock / (6144ull * 256);
    g_volume_clock -= steps * 6144ull * 256;
    for (int i = 0; i < 3; i++) {
        Stream& s = g_stream[i];
        u32 step = (i == 0 ? 0x40u : 0xC0u) * (u32)(steps > 1000 ? 1000 : steps);
        if (s.volume < s.target) s.volume = s.target - s.volume < step ? s.target : s.volume + step;
        else if (s.volume > s.target) s.volume = s.volume - s.target < step ? s.target : s.volume - step;
        if (!s.playing || !s.rate || !s.size) { s.byte_clock = 0; continue; }
        // consumed in blocks of 0x800 bytes, never past what has been written
        s.byte_clock += elapsed * s.rate;
        while (s.byte_clock >= 0x800ull * CYCLES_PER_SECOND) {
            if (s.read == s.write) { s.byte_clock = 0; break; }
            s.byte_clock -= 0x800ull * CYCLES_PER_SECOND;
            s.read = (s.read + 0x800) % s.size;
            s.played += 0x800;
        }
    }
}

void status(u32 recv, u32 recv_size) {
    u32 words[16] = {0};
    for (int i = 0; i < 3; i++) {
        words[i * 4] = g_stream[i].write; words[i * 4 + 1] = g_stream[i].read;
        words[i * 4 + 2] = g_stream[i].volume; words[i * 4 + 3] = g_stream[i].played;
    }
    if (recv != ~0u) memcpy(g_ram + recv, words, recv_size < 64 ? recv_size : 64);
}

}  // namespace

bool sound_rpc(u32 server, u32 function, u32 send, u32 send_size, u32 recv, u32 recv_size) {
    if (server != 0x80000701u && server != 0x000163A5u) return false;
    g_calls[(server == 0x80000701u ? 0x10000u : 0) | (function & 0xFFFF)]++;
    u32 a[8] = {0};
    if (send != ~0u) memcpy(a, g_ram + send, send_size < 32 ? send_size : 32);
    if (server == 0x80000701u) {
        u32 result = 0;
        switch (function & 0xFFF0) {
        case 0x8040: result = 0x00FFFFFF; break;        // get switch: every voice has ended
        case 0x80B0: result = a[3]; break;              // batch: commands carried out
        case 0x80D0: result = a[5]; g_uploaded += a[5]; break;   // voice transfer: bytes
        case 0x80F0: result = 1; break;                 // transfer status: done
        }
        if (recv != ~0u && recv_size >= 4) { memset(g_ram + recv, 0, recv_size); memcpy(g_ram + recv, &result, 4); }
        return true;
    }
    advance();
    u32 n = a[0] < 3 ? a[0] : 0;
    Stream& s = g_stream[n];
    switch (function) {
    case 0x20: for (auto& st : g_stream) { u32 size = st.size; st = Stream(); st.size = size; } break;
    case 0x30: s.buffer = a[1]; s.size = a[2]; s.write = s.read = s.played = 0; s.playing = false; break;
    case 0x40:                                          // data written up to a[1]; rate; flags: 1 play, 0x10000 two channels
        s.write = s.size ? a[1] % s.size : a[1];
        s.rate = (u32)((u64)a[2] * 16 / 28) * ((a[3] & 0x10000) ? 2 : 1);
        if (a[3] & 1) s.playing = true;
        break;
    case 0x60: s.playing = false; s.write = s.read = s.played = 0; s.byte_clock = 0; break;
    case 0x70: s.target = a[1] & 0x3FFF; break;
    }
    status(recv, recv_size);
    return true;
}

void sound_vblank() {}

void sound_report() {
    if (g_calls.empty()) return;
    printf("sound (no output): calls by function:");
    for (auto& kv : g_calls) printf(" %s%x x%llu", (kv.first & 0x10000) ? "sd:" : "stream:", kv.first & 0xFFFF, (unsigned long long)kv.second);
    printf("; %llu bytes of samples uploaded\n", (unsigned long long)g_uploaded);
}
