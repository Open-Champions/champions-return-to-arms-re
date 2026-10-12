// sound_rta.cpp - sound for the native build: drop-in for rt/sound_null.cpp.
//
//   python3 tools/recomp/build.py run --sound tools/recomp/sound/sound_rta.cpp
//
// Defines the three functions rt.h declares and nothing else of the runtime's.  Uses
// g_ram, iop_ram(), rt_cycles() and rt_option() only.  The work is in the library next to
// this file (rta_sound.h: the SPU2 chip, Sony's sound remote, the game's stream driver),
// compiled into this one object.
//
// Time, two ways (sound-clock):
//   machine  the mixer follows the machine's virtual clock.  One output sample (48 kHz) is
//            6,144 cycles of the 294,912,000 Hz clock; at every remote call and every
//            vertical blank the sound is rendered up to "now" before anything else happens,
//            so a register write or a status read lands on the sample it would have landed
//            on.  The same run gives the same sound and the same answers every time: for
//            files, comparisons and runs that go faster than time.
//   real     the sound side runs by itself, as the console's does: the device asks for
//            its sound and the chip, the stream driver and its 6 ms timer run on the
//            device's thread and clock.  The game's calls are carried out when they are
//            made.  Voices keep playing and streams keep being fed out of their rings
//            while the main side loads a level and makes no call for a third of a second.
//            What the game is told (voice end flags, stream positions) then depends on
//            when it asks, as on a console.
//
// Options (--opt key=value):
//   sound-wav=FILE        write everything rendered to a WAV file (48 kHz, 16 bit, stereo)
//   sound-out=device      play on the host's sound device (default: no device)
//   sound-out=timer       a stand-in device that only keeps time and discards the sound:
//                         measures the buffering where no sound may be made
//   sound-gain=0..1       device volume (0: the device runs, silent - for tests)
//   sound-clock=machine|real   see above (default machine; the application asks for real
//                         when it runs paced with a device)
//   sound-latency=MS      reserve held in front of the device (default 40; machine clock only)
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

#include <chrono>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>

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

// ---- the sound side on its own clock -----------------------------------------------------
bool g_real;                        // sound-clock=real
// The engine, between the game's thread and the device's.  The device's thread is the
// system's real-time sound thread: the lock has to hand its priority to whoever holds it
// (the game's thread, which a busy machine may not let run for a long time otherwise).
#if defined(__APPLE__)
}  // namespace
#include <os/lock.h>
namespace {
struct EngineLock {
    os_unfair_lock l = OS_UNFAIR_LOCK_INIT;
    void lock() { os_unfair_lock_lock(&l); }
    void unlock() { os_unfair_lock_unlock(&l); }
    bool try_lock() { return os_unfair_lock_trylock(&l); }
};
#else
typedef std::mutex EngineLock;
#endif
EngineLock g_lock;
rta::snd::PullDevice* g_puller;
u64 g_calls_waited;                 // remote calls that had to wait for the device's thread
double g_longest_wait_ms;

// What the engine renders while the device asks goes straight into the device's buffer
// (and into the WAV file when one is written).
class Capture : public AudioSink {
public:
    int16_t* out = nullptr;
    size_t left = 0;
    void write(const int16_t* s, size_t n) override {
        if (g_tee.a) g_tee.a->write(s, n);
        size_t take = n < left ? n : left;
        if (take) { memcpy(out, s, take * 4); out += take * 2; left -= take; }
    }
} g_capture;

class Puller : public rta::snd::AudioSource {
public:
    void pull(int16_t* stereo, size_t frames) override {
        std::lock_guard<EngineLock> hold(g_lock);
        g_capture.out = stereo; g_capture.left = frames;
        if (g_engine && !g_off) g_engine->advance_to(g_engine->position() + frames);
        if (g_capture.left) memset(g_capture.out, 0, g_capture.left * 4);
        g_capture.out = nullptr; g_capture.left = 0;
    }
} g_source;

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
    const char* clock = rt_option("sound-clock");
    const char* out = rt_option("sound-out");
    if (clock && !strcmp(clock, "real") && out && !g_off) {
        // the sound side by itself: the device (or, where none may be used or none opens, a
        // thread that keeps its time) asks for every 10 ms
        const char* gain = rt_option("sound-gain");
        g_real = true;
        g_engine->set_sink(&g_capture);
        if (!strcmp(out, "device")) g_puller = rta::snd::open_device_puller(48000, gain ? (float)atof(gain) : 1.0f, &g_source);
        if (!g_puller) {
            if (!strcmp(out, "device")) fprintf(stderr, "sound: no sound device; the sound side runs on a timer and is not heard\n");
            g_puller = rta::snd::open_timer_puller(48000, &g_source);
        }
        return *g_engine;
    }
    if (out) {
        const char* gain = rt_option("sound-gain");
        const char* latency = rt_option("sound-latency");
        unsigned reserve = latency ? (unsigned)atoi(latency) : 40;
        if (!strcmp(out, "device")) g_tee.b = rta::snd::open_device_sink(48000, reserve, gain ? (float)atof(gain) : 1.0f);
        else if (!strcmp(out, "timer")) g_tee.b = rta::snd::open_timer_sink(48000, reserve);
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
    if (!g_off && !g_real) e.advance_to(rt_cycles() / CYCLES_PER_SAMPLE);
}

// The game's thread takes the engine for one call.  On its own clock the device's thread
// may be rendering: the call waits for it (counted; a request is rendered in well under a
// millisecond).
struct Hold {
    std::unique_lock<EngineLock> lock;
    Hold() : lock(g_lock, std::defer_lock) {
        if (!g_real) return;
        if (lock.try_lock()) return;
        auto t0 = std::chrono::steady_clock::now();
        lock.lock();
        double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        g_calls_waited++;
        if (ms > g_longest_wait_ms) g_longest_wait_ms = ms;
    }
};

}  // namespace

bool sound_rpc(u32 server, u32 function, u32 send, u32 send_size, u32 recv, u32 recv_size) {
    if (server != Engine::SERVER_SD && server != Engine::SERVER_STREAM) return false;
    Engine& e = engine();
    Hold hold;
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
    if (g_engine && !g_real) catch_up(*g_engine);
}

void sound_report() {
    if (!g_engine) return;
    if (g_real) {
        if (g_puller) g_puller->close();                // the device's thread is gone before the engine is read
        g_engine->report(stdout);
        printf("sound: on its own clock (sound-clock=real): %llu of the game's calls waited for the device's thread, %.2f ms at most\n",
               (unsigned long long)g_calls_waited, g_longest_wait_ms);
        if (g_puller) g_puller->report(stdout);
        if (g_tee.a) g_tee.a->close();
    } else {
        catch_up(*g_engine);
        g_engine->report(stdout);
        g_tee.close();
    }
    if (g_log) fclose(g_log), g_log = nullptr;
}

// Figures for whoever asks while the run goes on (the application's control socket): one
// line of key=value.  Not part of rt.h.
std::string rta_sound_figures() {
    if (!g_engine) return "sound=none";
    char text[256];
    if (g_real && g_puller) {
        rta::snd::PullFigures f = g_puller->figures();
        snprintf(text, sizeof text, "sound=real sound_requests=%llu sound_late=%llu sound_longest_gap_ms=%.1f sound_s=%.2f sound_calls_waited=%llu",
                 (unsigned long long)f.pulls, (unsigned long long)f.late, f.longest_gap_ms, (double)f.frames / 48000.0, (unsigned long long)g_calls_waited);
    } else snprintf(text, sizeof text, "sound=machine sound_s=%.2f", (double)g_engine->position() / 48000.0);
    return text;
}
