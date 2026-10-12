// sound_rta.cpp - sound for the native build: drop-in for rt/sound_null.cpp.
//
//   python3 tools/recomp/build.py run --sound tools/recomp/sound/sound_rta.cpp
//
// Defines the three functions rt.h declares and nothing else of the runtime's.  Uses
// g_ram, iop_ram(), rt_cycles() and rt_option() only.  The work is in the library next to
// this file (rta_sound.h: the SPU2 chip, Sony's sound remote, the game's stream driver),
// compiled into this one object.
//
// Time: the mixer follows the machine's virtual clock.  One output sample (48 kHz) is
// 6,144 cycles of the 294,912,000 Hz clock; at every remote call and every vertical blank
// the sound is rendered up to "now" before anything else happens, so a register write or
// a status read lands on the sample it would have landed on.
//
// Options (--opt key=value):
//   sound-wav=FILE        write everything rendered to a WAV file (48 kHz, 16 bit, stereo)
//   sound-out=device      play on the host's sound device (default: no device)
//   sound-out=timer       a stand-in device that only keeps time and discards the sound:
//                         measures the buffering where no sound may be made
//   sound-gain=0..1       device volume (0: the device runs, silent - for tests)
//   sound-latency=MS      reserve held in front of the device (default 40)
//   sound-interp=gauss|linear|nearest   the voices' interpolation (default gauss)
//   sound-off=1           answer the calls, render nothing
//   sound-log=FILE        one line per remote call: machine time, server, function,
//                         argument words, answer words (status calls only when they change)
//   sound-solo=effects|streams|stream0|stream1|stream2   test aid: only the 43 effect
//                         voices, only the five stream voices, or one stream's, in the mix
// Without sound-wav and sound-out the calls are answered and the chip runs (voices end,
// streams advance, the game is told the truth); nothing is kept.
#include "rt.h"

#include "rta_sound.h"

#include "spu2.cpp"
#include "drivers.cpp"
#include "audio_out.cpp"

#include <cstdlib>
#include <cstring>

namespace {

using rta::snd::AudioSink;
using rta::snd::Engine;

const u64 CYCLES_PER_SAMPLE = CYCLES_PER_SECOND / 48000;      // 6144
const u32 IOP_RAM_SIZE = 0x200000;

class Tee : public AudioSink {
public:
    AudioSink* a = nullptr;
    AudioSink* b = nullptr;
    void write(const int16_t* s, size_t n) override { if (a) a->write(s, n); if (b) b->write(s, n); }
    void close() override { if (a) a->close(); if (b) b->close(); }
    void report(FILE* out) override { if (a) a->report(out); if (b) b->report(out); }
};

Engine* g_engine;
Tee g_tee;
bool g_off;
FILE* g_log;
u32 g_last_status[12];

Engine& engine() {
    if (g_engine) return *g_engine;
    g_engine = new Engine();
    g_engine->set_iop_memory(iop_ram(), IOP_RAM_SIZE);
    const char* text;
    if ((text = rt_option("sound-off")) && atoi(text)) g_off = true;
    if ((text = rt_option("sound-interp"))) {
        if (!strcmp(text, "linear")) g_engine->spu.set_interpolation(rta::snd::Spu2::LINEAR);
        else if (!strcmp(text, "nearest")) g_engine->spu.set_interpolation(rta::snd::Spu2::NEAREST);
    }
    if ((text = rt_option("sound-log"))) g_log = fopen(text, "w");
    if ((text = rt_option("sound-solo"))) {
        if (!strcmp(text, "effects")) g_engine->spu.set_mute(0, 0xF80000);
        else if (!strcmp(text, "streams")) g_engine->spu.set_mute(0xFFFFFF, 0x07FFFF);
        else if (!strcmp(text, "stream0")) g_engine->spu.set_mute(0xFFFFFF, 0xFFFFFF & ~(3u << 19));
        else if (!strcmp(text, "stream1")) g_engine->spu.set_mute(0xFFFFFF, 0xFFFFFF & ~(1u << 21));
        else if (!strcmp(text, "stream2")) g_engine->spu.set_mute(0xFFFFFF, 0xFFFFFF & ~(3u << 22));
    }
    if ((text = rt_option("sound-wav"))) {
        g_tee.a = rta::snd::open_wav_sink(text, 48000);
        if (!g_tee.a) fprintf(stderr, "sound: cannot write %s\n", text);
    }
    if ((text = rt_option("sound-out"))) {
        const char* gain = rt_option("sound-gain");
        const char* latency = rt_option("sound-latency");
        unsigned reserve = latency ? (unsigned)atoi(latency) : 40;
        if (!strcmp(text, "device")) g_tee.b = rta::snd::open_device_sink(48000, reserve, gain ? (float)atof(gain) : 1.0f);
        else if (!strcmp(text, "timer")) g_tee.b = rta::snd::open_timer_sink(48000, reserve);
        if (!g_tee.b) fprintf(stderr, "sound: no sound device\n");
    }
    if (g_tee.a || g_tee.b) g_engine->set_sink(&g_tee);
    // The time line starts with the machine's: a boot from power-on reaches its first
    // sound call after a few seconds, which are rendered as the silence they are; a
    // machine resumed far into its time starts at "now".
    g_engine->max_jump = 48000 * 60;
    g_engine->advance_to(rt_cycles() / CYCLES_PER_SAMPLE);
    g_engine->max_jump = 48000 * 5;
    return *g_engine;
}

void catch_up(Engine& e) {
    if (!g_off) e.advance_to(rt_cycles() / CYCLES_PER_SAMPLE);
}

}  // namespace

bool sound_rpc(u32 server, u32 function, u32 send, u32 send_size, u32 recv, u32 recv_size) {
    if (server != Engine::SERVER_SD && server != Engine::SERVER_STREAM) return false;
    Engine& e = engine();
    catch_up(e);
    u8 reply[64];
    const u8* args = send != ~0u && send < RAM_SIZE && send_size <= RAM_SIZE - send ? g_ram + send : nullptr;
    e.rpc(server, function, args, args ? send_size : 0, reply, sizeof reply);
    if (recv != ~0u && recv < RAM_SIZE && recv_size <= RAM_SIZE - recv)
        memcpy(g_ram + recv, reply, recv_size < sizeof reply ? recv_size : sizeof reply);
    if (g_log) {
        u32 a[7] = {0}, r[12];
        if (args) memcpy(a, args, send_size < sizeof a ? send_size : sizeof a);
        memcpy(r, reply, sizeof r);
        bool status = server == Engine::SERVER_STREAM && function == 0x50;
        if (!status || memcmp(r, g_last_status, sizeof r)) {
            fprintf(g_log, "%.4f\t%s\t%x\t%x %x %x %x %x %x\t", (double)rt_cycles() / CYCLES_PER_SECOND, server == Engine::SERVER_SD ? "sd" : "stream",
                    function, a[0], a[1], a[2], a[3], a[4], a[5]);
            if (server == Engine::SERVER_SD) fprintf(g_log, "%x\n", r[0]);
            else fprintf(g_log, "%x %x %x %x | %x %x %x %x | %x %x %x %x\n", r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11]);
        }
        if (status) memcpy(g_last_status, r, sizeof r);
    }
    return true;
}

void sound_vblank() {
    if (g_engine) catch_up(*g_engine);
}

void sound_report() {
    if (!g_engine) return;
    catch_up(*g_engine);
    g_engine->report(stdout);
    g_tee.close();
    if (g_log) fclose(g_log), g_log = nullptr;
}
