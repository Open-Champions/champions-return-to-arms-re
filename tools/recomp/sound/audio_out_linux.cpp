// audio_out_linux.cpp - the Linux sound device behind audio_out.cpp's two functions:
// open_device_sink() (the ring with its reserve) and open_device_puller() (the device asks
// the source).  Included by audio_out.cpp inside #elif defined(__linux__), after its Ring and
// PullCount, so it is part of the same translation unit; it is not compiled by itself.
//
// SDL2's audio device (PipeWire, PulseAudio, ALSA - whatever SDL finds; SDL_AUDIODRIVER
// chooses): 48 kHz 16-bit stereo, a buffer of 512 frames (10.7 ms), SDL converts to the
// device's own format.  Its callback runs on SDL's own audio thread.  When no device opens
// (a machine without sound, a container) the caller falls back to its timer, as on the
// other systems.  The gain is applied to the samples here.
#include <SDL.h>

namespace rta {
namespace snd {
namespace {

class SdlDevice : public PullDevice {
public:
    SdlDevice(unsigned rate, unsigned latency_ms, float gain, AudioSource* source)
        : ring_(rate, latency_ms), source_(source), rate_(rate) {
        gain_ = gain <= 0 ? 0 : gain >= 1 ? 32768 : (int)(gain * 32768.0f + 0.5f);
        if (SDL_InitSubSystem(SDL_INIT_AUDIO) != 0) { why_ = SDL_GetError(); return; }
        SDL_AudioSpec want, have;
        SDL_zero(want);
        want.freq = (int)rate;
        want.format = AUDIO_S16SYS;
        want.channels = 2;
        want.samples = 512;
        want.callback = [](void* self, Uint8* stream, int bytes) { ((SdlDevice*)self)->fill((int16_t*)stream, (size_t)bytes / 4); };
        want.userdata = this;
        device_ = SDL_OpenAudioDevice(nullptr, 0, &want, &have, 0);
        if (!device_) { why_ = SDL_GetError(); return; }
        frames_ = have.samples;
        driver_ = SDL_GetCurrentAudioDriver() ? SDL_GetCurrentAudioDriver() : "?";
        SDL_PauseAudioDevice(device_, 0);
    }
    ~SdlDevice() override { close(); }
    bool ok() const { return device_ != 0; }
    std::string why() const { return why_; }
    void write(const int16_t* stereo, size_t frames) override { if (!source_) ring_.push(stereo, frames); }
    PullFigures figures() override { return count_.figures(); }
    void close() override {
        if (device_) { SDL_CloseAudioDevice(device_); device_ = 0; }
    }
    void report(FILE* out) override {
        char device[96];
        snprintf(device, sizeof device, "SDL2 %s, %u frames", driver_.c_str(), frames_);
        if (source_) { count_.report(out, device, rate_); return; }
        ring_.report(out, device);
    }

private:
    void fill(int16_t* out, size_t frames) {
        if (source_) count_.pull(source_, out, frames);
        else ring_.pull(out, frames);
        if (gain_ != 32768)
            for (size_t i = 0; i < frames * 2; i++) out[i] = (int16_t)(((int)out[i] * gain_) >> 15);
    }
    Ring ring_;
    AudioSource* source_;
    unsigned rate_;
    int gain_ = 32768;
    PullCount count_;
    SDL_AudioDeviceID device_ = 0;
    unsigned frames_ = 0;
    std::string why_, driver_;
};

}  // namespace

AudioSink* open_device_sink(unsigned rate, unsigned latency_ms, float gain) {
    SdlDevice* device = new SdlDevice(rate, latency_ms, gain, nullptr);
    if (device->ok()) return device;
    fprintf(stderr, "sound: device not opened: %s\n", device->why().c_str());
    delete device;
    return nullptr;
}

PullDevice* open_device_puller(unsigned rate, float gain, AudioSource* source) {
    SdlDevice* device = new SdlDevice(rate, 0, gain, source);
    if (device->ok()) return device;
    fprintf(stderr, "sound: device not opened: %s\n", device->why().c_str());
    delete device;
    return nullptr;
}

}  // namespace snd
}  // namespace rta
