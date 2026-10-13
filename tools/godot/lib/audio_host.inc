// audio_host.inc - the "sound device" of a machine that lives inside another program: the
// host asks for the sound (rtag_audio_pull) and plays it itself.
//
// Included by tools/recomp/sound/audio_out.cpp in place of its own devices when
// RTA_AUDIO_HOST names this file (../recomp.patch), after the ring (Ring) and the request
// counter (PullCount) of that file:
//   open_device_puller   sound-clock=real: every request of the host is rendered when it
//                        is made, on the host's sound thread (the console's sound side
//                        runs by itself in the same way);
//   open_device_sink     sound-clock=machine: what is rendered on the machine's clock
//                        waits in the ring for the host's requests.
// The gain is the host's business (rtag.cpp scales what it hands out).

namespace rta {
namespace snd {

namespace {

std::mutex g_host_lock;                 // against the device being closed while the host asks
class HostPuller;
class HostSink;
HostPuller* g_host_puller = nullptr;
HostSink* g_host_sink = nullptr;

class HostPuller : public PullDevice {
public:
    HostPuller(unsigned rate, AudioSource* source) : source_(source), rate_(rate) {}
    void pull(int16_t* out, size_t frames) { count_.pull(source_, out, frames); }
    PullFigures figures() override { return count_.figures(); }
    void close() override { std::lock_guard<std::mutex> hold(g_host_lock); if (g_host_puller == this) g_host_puller = nullptr; }
    void report(FILE* out) override { count_.report(out, "the host program (it asks for its sound)", rate_); }

private:
    AudioSource* source_;
    unsigned rate_;
    PullCount count_;
};

class HostSink : public AudioSink {
public:
    HostSink(unsigned rate, unsigned latency_ms) : ring_(rate, latency_ms) {}
    void write(const int16_t* stereo, size_t frames) override { ring_.push(stereo, frames); }
    void pull(int16_t* out, size_t frames) { ring_.pull(out, frames); }
    void close() override { std::lock_guard<std::mutex> hold(g_host_lock); if (g_host_sink == this) g_host_sink = nullptr; }
    void report(FILE* out) override { ring_.report(out, "the host program, through a ring"); }

private:
    Ring ring_;
};

}  // namespace

AudioSink* open_device_sink(unsigned rate, unsigned latency_ms, float) {
    std::lock_guard<std::mutex> hold(g_host_lock);
    g_host_sink = new HostSink(rate, latency_ms);
    return g_host_sink;
}

PullDevice* open_device_puller(unsigned rate, float, AudioSource* source) {
    std::lock_guard<std::mutex> hold(g_host_lock);
    g_host_puller = new HostPuller(rate, source);
    return g_host_puller;
}

// What rtag_audio_pull() calls: exactly `frames` frames, silence while no device is open.
void host_audio_pull(int16_t* stereo, size_t frames, float gain) {
    {
        std::lock_guard<std::mutex> hold(g_host_lock);
        if (g_host_puller) g_host_puller->pull(stereo, frames);
        else if (g_host_sink) g_host_sink->pull(stereo, frames);
        else { memset(stereo, 0, frames * 4); return; }
    }
    if (gain <= 0.0f) memset(stereo, 0, frames * 4);
    else if (gain < 0.999f)
        for (size_t k = 0; k < frames * 2; k++) stereo[k] = (int16_t)(stereo[k] * gain);
}

}  // namespace snd
}  // namespace rta
