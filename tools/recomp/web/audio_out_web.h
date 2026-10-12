// audio_out_web.h - the sound device of a page, for tools/recomp/sound/audio_out.cpp (which
// includes this file when it is compiled with Emscripten).
//
// The renderer hands samples over on the machine's clock; the page's AudioWorklet
// (rta-sound-worklet.js) takes them on the sound device's clock, straight out of this
// ring in the shared memory - the page's main thread is not on the path.  The reserve
// and the slow rate correction that keep two clocks together are the worklet's (the
// same scheme as the Ring above, and as the emulator's page).  A ring nobody reads
// (sound switched off on the page) fills up and what follows is dropped.
//
// Layout the worklet reads: four 32-bit words - write position, read position (both
// count 16-bit samples and run on; the worklet owns `read`), size in samples (a power of
// two), sample rate - then the samples, left and right interleaved.
#pragma once
#include <atomic>
#include <cstdint>

namespace rta {
namespace snd {
namespace web {
enum { RING_SAMPLES = 1 << 16 };                        // 32,768 stereo frames: 0.68 s at 48 kHz
struct Ring {
    std::atomic<uint32_t> write{0}, read{0};
    uint32_t size = RING_SAMPLES, rate = 48000;
    int16_t samples[RING_SAMPLES];
};
inline Ring& ring() { static Ring r; return r; }
inline std::atomic<uint64_t>& dropped() { static std::atomic<uint64_t> d{0}; return d; }
}  // namespace web

namespace {
class WebSink : public AudioSink {
public:
    explicit WebSink(unsigned rate) { web::ring().rate = rate; }
    void write(const int16_t* stereo, size_t frames) override {
        web::Ring& r = web::ring();
        uint32_t write = r.write.load(std::memory_order_relaxed), read = r.read.load(std::memory_order_acquire);
        size_t room = (r.size - (write - read)) / 2;
        if (frames > room) { web::dropped() += frames - room; frames = room; }
        for (size_t i = 0; i < frames * 2; i++) r.samples[(write + i) & (r.size - 1)] = stereo[i];
        r.write.store(write + (uint32_t)(frames * 2), std::memory_order_release);
        frames_ += frames;
    }
    void report(FILE* out) override {
        fprintf(out, "sound: page: %.2f s handed to the ring, %.2f s dropped because nothing took it\n",
                (double)frames_ / web::ring().rate, (double)web::dropped().load() / web::ring().rate);
    }
private:
    uint64_t frames_ = 0;
};
}  // namespace

AudioSink* open_device_sink(unsigned rate, unsigned, float) { return new WebSink(rate); }
// the sound side on the device's own clock would need the engine run from the worklet's
// thread; not built: the caller falls back to a timer
PullDevice* open_device_puller(unsigned, float, AudioSource*) { return nullptr; }

}  // namespace snd
}  // namespace rta

extern "C" __attribute__((used)) void* rta_web_sound_ring() { return &rta::snd::web::ring(); }
