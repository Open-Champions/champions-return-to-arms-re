// audio_out_win.cpp - the Windows sound device behind audio_out.cpp's two functions:
// open_device_sink() (the ring with its reserve) and open_device_puller() (the device asks
// the source).  Included by audio_out.cpp inside #if defined(_WIN32), after its Ring and
// PullCount, so it is part of the same translation unit; it is not compiled by itself.
//
// Written and compiled on a Mac with a cross-compiler; NOT RUN - nobody has heard it
// (docs/issues/native-windows.md).
//
//   WASAPI   shared mode, event driven: the default output device, 48 kHz 16-bit stereo
//            handed over as it is (AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM: Windows converts to
//            the device's own format), a 20 ms buffer filled whenever the device signals.
//            If the device goes away (unplugged, the default changed) it is opened again;
//            meanwhile the sound is asked for on a 10 ms timer and dropped, so that the
//            game's sound side keeps its time.
//   waveOut  the fallback when WASAPI does not open, and what RTA_SOUND_API=waveout asks
//            for: four buffers of 10 ms, refilled by the same thread as each comes back.
//
// The gain is applied to the samples here (no session volume is touched in Windows).
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <mmsystem.h>
#include <mmreg.h>
#include <objbase.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <avrt.h>

#include <condition_variable>

namespace rta {
namespace snd {
namespace {

// The GUIDs spelled out, so that no import library has to carry them.
const GUID kClsidEnumerator = {0xBCDE0395, 0xE52F, 0x467C, {0x8E, 0x3D, 0xC4, 0x57, 0x92, 0x91, 0x69, 0x2E}};
const GUID kIidEnumerator = {0xA95664D2, 0x9614, 0x4F35, {0xA7, 0x46, 0xDE, 0x8D, 0xB6, 0x36, 0x17, 0xE6}};
const GUID kIidAudioClient = {0x1CB9AD4C, 0xDBFA, 0x4C32, {0xB1, 0x78, 0xC2, 0xF5, 0x68, 0xA7, 0x03, 0xB2}};
const GUID kIidRenderClient = {0xF294ACFC, 0x3146, 0x4483, {0xA7, 0xBF, 0xAD, 0xDC, 0xA7, 0xC2, 0x60, 0xE2}};

class WinDevice : public PullDevice {
public:
    WinDevice(unsigned rate, unsigned latency_ms, float gain, AudioSource* source)
        : ring_(rate, latency_ms), source_(source), rate_(rate) {
        gain_ = gain <= 0 ? 0 : gain >= 1 ? 32768 : (int)(gain * 32768.0f + 0.5f);
        const char* api = getenv("RTA_SOUND_API");
        force_waveout_ = api && !strcmp(api, "waveout");
        thread_ = std::thread([this] { run(); });
        std::unique_lock<std::mutex> lock(mutex_);
        ready_.wait(lock, [this] { return state_ != STARTING; });
    }
    ~WinDevice() override { close(); }
    bool ok() const { return state_ == RUNNING; }
    const char* why() const { return why_; }
    long status() const { return status_; }
    void write(const int16_t* stereo, size_t frames) override { if (!source_) ring_.push(stereo, frames); }
    PullFigures figures() override { return count_.figures(); }
    void close() override {
        if (stop_.exchange(true)) return;
        if (thread_.joinable()) thread_.join();
    }
    void report(FILE* out) override {
        char device[96];
        snprintf(device, sizeof device, "%s (opened %u times)", api_, opens_.load());
        if (source_) {
            count_.report(out, device, rate_);
            fprintf(out, "sound: delay from a register write to the device: up to %u ms of device buffer + the device's own\n", buffer_ms_);
            return;
        }
        ring_.report(out, device);
        fprintf(out, "sound: delay from render to the device: the reserve + up to %u ms of device buffer + the device's own\n", buffer_ms_);
    }

private:
    enum State { STARTING, RUNNING, FAILED };

    void fill(int16_t* out, size_t frames) {
        if (source_) count_.pull(source_, out, frames);
        else ring_.pull(out, frames);
        if (gain_ == 0) memset(out, 0, frames * 4);
        else if (gain_ < 32768)
            for (size_t k = 0; k < frames * 2; k++) out[k] = (int16_t)(((int32_t)out[k] * gain_) >> 15);
    }
    void started(State state) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (state_ == STARTING) { state_ = state; ready_.notify_all(); }
    }
    WAVEFORMATEX format() const {
        WAVEFORMATEX f = {};
        f.wFormatTag = WAVE_FORMAT_PCM;
        f.nChannels = 2;
        f.nSamplesPerSec = rate_;
        f.wBitsPerSample = 16;
        f.nBlockAlign = 4;
        f.nAvgBytesPerSec = rate_ * 4;
        return f;
    }

    // ---- WASAPI ----
    struct Wasapi {
        IMMDeviceEnumerator* enumerator = nullptr;
        IMMDevice* device = nullptr;
        IAudioClient* client = nullptr;
        IAudioRenderClient* render = nullptr;
        HANDLE event = nullptr;
        UINT32 frames = 0;
        void release() {
            if (client) client->Stop();
            if (render) render->Release();
            if (client) client->Release();
            if (device) device->Release();
            if (enumerator) enumerator->Release();
            if (event) CloseHandle(event);
            *this = Wasapi();
        }
    };
    bool wasapi_open(Wasapi& w) {
        HRESULT hr;
#define RTA_STEP(what, call) if (FAILED(hr = (call))) { why_ = what; status_ = (long)hr; w.release(); return false; }
        RTA_STEP("CoCreateInstance(MMDeviceEnumerator)",
                 CoCreateInstance(kClsidEnumerator, nullptr, CLSCTX_ALL, kIidEnumerator, (void**)&w.enumerator));
        RTA_STEP("GetDefaultAudioEndpoint", w.enumerator->GetDefaultAudioEndpoint(eRender, eConsole, &w.device));
        RTA_STEP("IMMDevice::Activate", w.device->Activate(kIidAudioClient, CLSCTX_ALL, nullptr, (void**)&w.client));
        WAVEFORMATEX f = format();
        const DWORD flags = AUDCLNT_STREAMFLAGS_EVENTCALLBACK | 0x80000000u /* AUTOCONVERTPCM */ | 0x08000000u /* SRC_DEFAULT_QUALITY */;
        RTA_STEP("IAudioClient::Initialize", w.client->Initialize(AUDCLNT_SHAREMODE_SHARED, flags, 20 * 10000 /* 20 ms in 100 ns */, 0, &f, nullptr));
        w.event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
        RTA_STEP("SetEventHandle", w.client->SetEventHandle(w.event));
        RTA_STEP("GetBufferSize", w.client->GetBufferSize(&w.frames));
        RTA_STEP("GetService(IAudioRenderClient)", w.client->GetService(kIidRenderClient, (void**)&w.render));
        BYTE* data = nullptr;                           // start on a full buffer of silence
        if (SUCCEEDED(w.render->GetBuffer(w.frames, &data))) w.render->ReleaseBuffer(w.frames, AUDCLNT_BUFFERFLAGS_SILENT);
        RTA_STEP("IAudioClient::Start", w.client->Start());
#undef RTA_STEP
        buffer_ms_ = w.frames * 1000 / rate_;
        return true;
    }
    // Plays until asked to stop (true) or until the device fails (false).
    bool wasapi_play(Wasapi& w) {
        while (!stop_) {
            if (WaitForSingleObject(w.event, 200) != WAIT_OBJECT_0) {
                UINT32 probe = 0;                       // no signal for 200 ms: is the device still there?
                if (FAILED(w.client->GetCurrentPadding(&probe))) return false;
                continue;
            }
            UINT32 queued = 0;
            if (FAILED(w.client->GetCurrentPadding(&queued))) return false;
            UINT32 space = w.frames > queued ? w.frames - queued : 0;
            if (!space) continue;
            BYTE* data = nullptr;
            if (FAILED(w.render->GetBuffer(space, &data))) return false;
            fill((int16_t*)data, space);
            if (FAILED(w.render->ReleaseBuffer(space, 0))) return false;
        }
        return true;
    }

    // ---- waveOut ----
    bool waveout_play() {
        enum { kBuffers = 4, kFrames = 480 };
        WAVEFORMATEX f = format();
        HANDLE event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
        HWAVEOUT out = nullptr;
        MMRESULT r = waveOutOpen(&out, WAVE_MAPPER, &f, (DWORD_PTR)event, 0, CALLBACK_EVENT);
        if (r != MMSYSERR_NOERROR) { why_ = "waveOutOpen"; status_ = (long)r; CloseHandle(event); return false; }
        std::vector<int16_t> samples[kBuffers];
        WAVEHDR header[kBuffers];
        memset(header, 0, sizeof header);
        for (int k = 0; k < kBuffers; k++) {
            samples[k].assign(kFrames * 2, 0);
            header[k].lpData = (LPSTR)samples[k].data();
            header[k].dwBufferLength = kFrames * 4;
            waveOutPrepareHeader(out, &header[k], sizeof(WAVEHDR));
            header[k].dwFlags |= WHDR_DONE;             // "came back": filled and written below
        }
        api_ = "waveOut, 4 x 10 ms";
        buffer_ms_ = kBuffers * 10;
        opens_++;
        started(RUNNING);
        while (!stop_) {
            for (int k = 0; k < kBuffers; k++) {
                if (!(header[k].dwFlags & WHDR_DONE)) continue;
                header[k].dwFlags &= ~WHDR_DONE;
                fill(samples[k].data(), kFrames);
                waveOutWrite(out, &header[k], sizeof(WAVEHDR));
            }
            WaitForSingleObject(event, 50);
        }
        waveOutReset(out);
        for (int k = 0; k < kBuffers; k++) waveOutUnprepareHeader(out, &header[k], sizeof(WAVEHDR));
        waveOutClose(out);
        CloseHandle(event);
        return true;
    }

    void run() {
        HRESULT com = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        DWORD task = 0;
        HANDLE mm = AvSetMmThreadCharacteristicsW(L"Pro Audio", &task);
        Wasapi w;
        bool opened = !force_waveout_ && wasapi_open(w);
        if (opened) {
            api_ = "WASAPI shared, event driven";
            opens_++;
            started(RUNNING);
            std::vector<int16_t> scratch(rate_ / 100 * 2);
            while (!stop_) {
                if (opened && wasapi_play(w)) break;    // asked to stop
                if (stop_) break;
                // the device failed or is gone: keep the time on a timer, try again twice a second
                w.release();
                opened = false;
                for (int k = 0; k < 50 && !stop_; k++) {
                    Sleep(10);
                    fill(scratch.data(), scratch.size() / 2);
                }
                if (!stop_ && wasapi_open(w)) { opened = true; opens_++; }
            }
            w.release();
        } else if (!waveout_play()) {
            started(FAILED);                            // neither opened: the caller falls back to its timer
        }
        if (mm) AvRevertMmThreadCharacteristics(mm);
        if (SUCCEEDED(com)) CoUninitialize();
    }

    Ring ring_;
    AudioSource* source_;
    unsigned rate_;
    int gain_ = 32768;
    bool force_waveout_ = false;
    PullCount count_;
    std::mutex mutex_;
    std::condition_variable ready_;
    State state_ = STARTING;
    const char* why_ = "";
    const char* api_ = "none";
    long status_ = 0;
    unsigned buffer_ms_ = 0;
    std::atomic<unsigned> opens_{0};
    std::atomic<bool> stop_{false};
    std::thread thread_;
};

}  // namespace

AudioSink* open_device_sink(unsigned rate, unsigned latency_ms, float gain) {
    WinDevice* device = new WinDevice(rate, latency_ms, gain, nullptr);
    if (device->ok()) return device;
    fprintf(stderr, "sound: device not opened: %s (status 0x%08lx)\n", device->why(), (unsigned long)device->status());
    delete device;
    return nullptr;
}

PullDevice* open_device_puller(unsigned rate, float gain, AudioSource* source) {
    WinDevice* device = new WinDevice(rate, 0, gain, source);
    if (device->ok()) return device;
    fprintf(stderr, "sound: device not opened: %s (status 0x%08lx)\n", device->why(), (unsigned long)device->status());
    delete device;
    return nullptr;
}

}  // namespace snd
}  // namespace rta
