// rta_sound.h - the sound side of Champions: Return to Arms, on the host.
//
// On the console the game does not make sound itself.  It talks to two programs on the
// I/O processor through remote calls:
//
//   0x80000701  Sony's "sound remote" (SDRDRV.IRX in front of LIBSD.IRX): every call is one
//               libsd function, that is, reads and writes of the SPU2 sound chip's registers
//               and uploads into its 2 MB of sample memory.  All sound effects go this way.
//   0x000163a5  the game's own stream driver (HELLO.IRX): three streams (movie sound,
//               speech, music) whose data the game reads from the disc into ring buffers in
//               I/O-processor memory; a 6 ms timer copies it piecewise into SPU2 memory
//               under five voices that loop for ever.
//
// This library is those two programs and the chip, written from their behaviour
// (docs/issues/native-sound.md): Spu2 (48 voices, ADPCM, envelopes, pitch, mixing),
// the libsd command set, the stream driver's ten commands and timer.  It has no
// dependency on the recompiled game or its runtime: sound_rta.cpp connects it to the
// runtime's three sound functions, sndtool.cpp drives it from files for tests.
//
// Time is counted in output samples (48,000 a second, the chip's own rate).  Nothing here
// reads a clock: the owner says how far to render (Engine::advance_to).
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <map>

namespace rta {
namespace snd {

// ---- where the samples go ----------------------------------------------------------------
class AudioSink {
public:
    virtual ~AudioSink() {}
    // interleaved left/right, 16 bit, 48 kHz
    virtual void write(const int16_t* stereo, size_t frames) = 0;
    virtual void close() {}
    virtual void report(FILE*) {}
};
AudioSink* open_wav_sink(const char* path, unsigned rate);
// The host's sound device behind a ring buffer (audio_out.cpp; CoreAudio on macOS).
// `gain` 0 plays silence (tests on a computer somebody is using).  nullptr when the host
// has no back end compiled in or the device cannot be opened.
AudioSink* open_device_sink(unsigned rate, unsigned latency_ms, float gain);
// The same ring with a thread in place of a device: takes 10 ms every 10 ms, discards it.
AudioSink* open_timer_sink(unsigned rate, unsigned latency_ms);

// ---- the chip ----------------------------------------------------------------------------
class Spu2 {
public:
    enum { RAM_BYTES = 0x200000, CORES = 2, VOICES = 24, RATE = 48000 };
    enum Interpolation { GAUSS = 0, LINEAR = 1, NEAREST = 2 };

    Spu2();
    void reset();          // power-on: silence, memory cleared
    void sd_init();        // the state libsd's sceSdInit leaves (docs: "Start-up")

    // Register access as libsd numbers it: entry = register << 8 | voice << 1 | core.
    void set_param(unsigned entry, unsigned value);
    unsigned get_param(unsigned entry) const;
    void set_switch(unsigned entry, uint32_t value);
    uint32_t get_switch(unsigned entry) const;
    void set_addr(unsigned entry, uint32_t value);
    uint32_t get_addr(unsigned entry) const;
    void set_core_attr(unsigned entry, unsigned value);
    unsigned get_core_attr(unsigned entry) const;
    // sample memory upload ("voice transfer"); the size is used as given
    void write(uint32_t address, const uint8_t* data, uint32_t size);

    void render(int16_t* stereo, size_t frames);

    void set_interpolation(Interpolation i) { interpolation_ = i; }
    // test aid: leave voices out of the mix (they still run).  One 24-bit mask per core.
    void set_mute(uint32_t core0, uint32_t core1) { mute_[0] = core0; mute_[1] = core1; }
    int voices_sounding() const;

    struct Stats {
        uint64_t frames = 0, key_on = 0, key_off = 0, ended = 0;
        uint64_t clipped = 0;            // output samples that hit full scale
        uint64_t key_on_unwritten = 0;   // key-on at memory nothing was uploaded to
        uint64_t sweep_volumes = 0;      // volume registers written in sweep mode (not modelled)
        int peak = 0;
    } stats;

    uint8_t ram[RAM_BYTES];

private:
    enum Phase { OFF = 0, ATTACK, DECAY, SUSTAIN, RELEASE };
    struct Voice {
        // registers
        uint16_t voll, volr, pitch, adsr1, adsr2;
        uint32_t ssa, lsax;            // byte addresses, 16-byte aligned
        // state
        uint32_t nax;                  // address of the block being played
        uint8_t pos;                   // next sample of the block, 0..28
        uint8_t flags;                 // of the block being played
        uint8_t phase;
        bool lsax_written;             // software set the loop address since key-on
        bool parked;                   // silent on a block that loops to itself
        int32_t envx;                  // 0..0x7fff
        uint32_t env_count;
        uint32_t counter;              // pitch counter, 12 fraction bits
        int32_t hist1, hist2;          // decoder history
        int16_t ring[4];               // the four newest samples, ring[3] newest
        int16_t block[28];
    };
    struct Core {
        Voice v[VOICES];
        uint16_t mmix, mvoll, mvolr, evoll, evolr, avoll, avolr, bvoll, bvolr;
        uint32_t pmon, non, vmixl, vmixel, vmixr, vmixer, endx;
        uint32_t esa, eea, tsa, irqa;
        uint16_t attr;
    };
    Core core_[CORES];
    Interpolation interpolation_;
    int16_t gauss_[256][4];
    uint8_t written_[RAM_BYTES / 64 / 8];   // which 64-byte pieces were ever uploaded
    uint32_t mute_[CORES] = {0, 0};

    void key_on(Core& c, int n);
    void key_off(Core& c, int n);
    void load_block(Core& c, int n);
    void next_sample(Core& c, int n);
    void envelope(Voice& v);
    inline int32_t voice_tick(Core& c, int n);
};

// ---- the two programs and the time line ---------------------------------------------------
class Engine {
public:
    static const uint32_t SERVER_SD = 0x80000701u, SERVER_STREAM = 0x000163A5u;

    Engine();
    // I/O-processor memory: the remote calls name buffers in it (batches, uploads, stream
    // rings).  The owner keeps it; the stream driver marks ADPCM flag bytes in it as the
    // original does.
    void set_iop_memory(uint8_t* base, size_t size) { iop_ = base; iop_size_ = size; }
    void set_sink(AudioSink* sink) { sink_ = sink; }

    // One remote call.  `send` is the caller's argument block, `reply` receives what the
    // server answers (at most `reply_size` bytes, at most 64).  Returns false for a server
    // that is not one of the two.  Call advance_to() first: the answer is the state at
    // the render position.
    bool rpc(uint32_t server, uint32_t function, const uint8_t* send, size_t send_size,
             uint8_t* reply, size_t reply_size);

    // Render up to sample number `sample` (48 kHz, from 0), running the stream driver's
    // timer on the way.  A target more than `max_jump` samples ahead is a jump of the
    // clock: the gap is skipped, not rendered.
    void advance_to(uint64_t sample);
    uint64_t position() const { return position_; }

    void report(FILE* out) const;

    Spu2 spu;
    uint64_t max_jump = 48000 * 5;

    struct Stats {
        std::map<uint32_t, uint64_t> calls[2];   // by server (0 sd, 1 stream) and function
        uint64_t unknown = 0;
        uint64_t batch_commands = 0, uploaded = 0;
        uint64_t alarms = 0, refills[3] = {}, starved[3] = {}, stream_bytes[3] = {};
        uint64_t effect_modes = 0;         // effect modes other than "off" asked for
        uint64_t bad_address = 0;          // I/O-processor addresses outside the memory
        uint64_t skipped = 0;              // samples skipped by clock jumps
        double render_seconds = 0;         // processor time spent in advance_to
    } stats;

private:
    struct Queue { int32_t rate, stereo, left, flags; };
    struct Stream {
        uint32_t buffer; int32_t size, write, read, last_half, played;
        int32_t volume, target, scale; uint32_t flags;
        Queue que[32]; int32_t count, started;
    };

    uint8_t* iop_ = nullptr;
    size_t iop_size_ = 0;
    AudioSink* sink_ = nullptr;
    uint64_t position_ = 0;

    // libsd / SDRDRV
    struct Effect { int32_t core, mode; int16_t depth_l, depth_r; int32_t delay, feedback; } effect_[2];
    uint32_t sd_call(uint32_t function, const uint8_t* a, size_t size, uint8_t* reply, size_t reply_size);
    uint32_t batch(uint32_t address, uint32_t results, uint32_t count);
    uint32_t transfer(uint32_t source, uint32_t spu_address, uint32_t size);

    // HELLO
    Stream stream_[3];
    int32_t stereo_enable_ = 1, force_volume_ = 1;
    uint32_t status_[12] = {};
    bool alarm_on_ = false;
    uint64_t alarm_at_ = 0;
    uint8_t zero_input_[0x1000], fake_stereo_[0x800];
    void stream_call(uint32_t function, const uint8_t* a, size_t size);
    void stream_init();
    void alarm();
    void set_alarm() { alarm_on_ = true; alarm_at_ = position_ + 480; }   // 10 ms

    uint8_t* iop_at(uint32_t address, uint32_t size);
    void render(uint64_t frames);
};

}  // namespace snd
}  // namespace rta
