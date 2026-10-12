// audio_out.cpp - where rendered sound goes: a WAV file, or the host's sound device.
//
// The device sink is the only host-specific part of the library.  The renderer hands it
// samples on the machine's (virtual) clock; the device takes samples on its own clock.
// Between them is a ring buffer with a held reserve: playing starts when `latency_ms` of
// sound is queued, and a slow correction of the read rate (at most 0.5 %, four-point
// interpolation) keeps that much queued, so that two clocks that differ by a fraction of
// a percent neither run the buffer dry nor fill it up.  A burst of more than 200 ms above the
// reserve is given up at once instead.
//
//   macOS    AudioQueue (AudioToolbox), found at run time with dlopen so that the
//            program needs no extra link flag; three buffers of 10 ms.  A device that asks
//            for its sound (open_device_puller) is the default output unit instead: its
//            render callback runs on the system's real-time sound thread, which a loaded
//            machine does not hold up (an AudioQueue's callback thread is an ordinary
//            one: with the computer very busy it once came 0.9 s late)
//   Windows  not written.  It needs the same three calls on WASAPI in shared mode
//            (IAudioClient::Initialize with an event handle, a thread that waits for the
//            event and copies from pull() into IAudioRenderClient::GetBuffer) or, with
//            less code and about 30 ms more delay, waveOutOpen / waveOutWrite with three
//            buffers.  pull() is all either needs from this file.
#include "rta_sound.h"

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <thread>
#include <vector>

namespace rta {
namespace snd {

// ---- WAV ---------------------------------------------------------------------------------

namespace {

class WavSink : public AudioSink {
public:
    WavSink(FILE* f, unsigned rate) : file_(f), rate_(rate) { header(); }
    ~WavSink() override { close(); }
    void write(const int16_t* stereo, size_t frames) override {
        if (!file_) return;
        fwrite(stereo, 4, frames, file_);
        frames_ += frames;
        since_header_ += frames;
        // keep the header true about once a second, so that a run that is killed leaves
        // a file that opens
        if (since_header_ >= rate_) { header(); since_header_ = 0; }
    }
    void close() override {
        if (!file_) return;
        header();
        fclose(file_);
        file_ = nullptr;
    }
    void report(FILE* out) override { fprintf(out, "sound: %.2f s written as WAV\n", (double)frames_ / rate_); }

private:
    void header() {
        uint32_t data = (uint32_t)(frames_ * 4);
        uint8_t h[44] = {'R', 'I', 'F', 'F', 0, 0, 0, 0, 'W', 'A', 'V', 'E', 'f', 'm', 't', ' ', 16, 0, 0, 0, 1, 0, 2, 0};
        uint32_t riff = data + 36, byte_rate = rate_ * 4;
        memcpy(h + 4, &riff, 4); memcpy(h + 24, &rate_, 4); memcpy(h + 28, &byte_rate, 4);
        h[32] = 4; h[34] = 16;
        memcpy(h + 36, "data", 4); memcpy(h + 40, &data, 4);
        long at = ftell(file_);
        fseek(file_, 0, SEEK_SET);
        fwrite(h, 1, 44, file_);
        if (frames_) fseek(file_, at, SEEK_SET);
        fflush(file_);
    }
    FILE* file_;
    uint32_t rate_;
    uint64_t frames_ = 0, since_header_ = 0;
};

// ---- the ring between the renderer and a device ---------------------------------------------

class Ring {
public:
    Ring(unsigned rate, unsigned latency_ms)
        : rate_(rate), reserve_(rate * latency_ms / 1000), data_((size_t)rate * 2) /* one second */ {}

    void push(const int16_t* stereo, size_t frames) {
        std::lock_guard<std::mutex> lock(mutex_);
        size_t capacity = data_.size() / 2;
        if (frames > capacity - count_) {            // the device is not taking it: drop the oldest
            size_t drop = frames - (capacity - count_);
            if (drop > count_) drop = count_;
            read_ = (read_ + drop) % capacity; count_ -= drop;
            dropped_ += drop;
        }
        for (size_t i = 0; i < frames && count_ < capacity; i++) {
            size_t at = (read_ + count_) % capacity;
            data_[at * 2] = stereo[i * 2]; data_[at * 2 + 1] = stereo[i * 2 + 1];
            count_++;
        }
        pushed_ += frames;
        // More than 200 ms above the reserve is not a clock difference but a burst (the
        // machine caught up after standing still): the rate correction would take minutes
        // to play it down, so the oldest sound is given up and the delay is back at once.
        if (count_ > reserve_ + rate_ / 5) {
            size_t drop = count_ - reserve_;
            read_ = (read_ + drop) % capacity; count_ -= drop;
            dropped_ += drop; resyncs_++;
        }
    }

    // The device's side: exactly `frames` frames, silence where there is nothing.
    void pull(int16_t* out, size_t frames) {
        std::lock_guard<std::mutex> lock(mutex_);
        size_t capacity = data_.size() / 2;
        pulled_ += frames;
        if (!running_) {
            if (count_ < reserve_ + frames) { memset(out, 0, frames * 4); return; }
            running_ = true;
        }
        // read rate: 1 when the reserve is as wanted, up to 0.5 % either way
        double error = ((double)count_ - (double)reserve_) / (double)(reserve_ ? reserve_ : 1);
        double rate = 1.0 + 0.005 * (error > 1 ? 1 : error < -1 ? -1 : error);
        fill_sum_ += count_; fill_n_++;
        if (count_ < fill_min_) fill_min_ = count_;
        for (size_t i = 0; i < frames; i++) {
            if (count_ < 4) {                           // ran dry: silence until the reserve is back
                memset(out + i * 2, 0, (frames - i) * 4);
                dry_++; dry_frames_ += frames - i;
                running_ = false; phase_ = 0;
                return;
            }
            for (int ch = 0; ch < 2; ch++) {
                double p0 = data_[((read_ + 0) % capacity) * 2 + ch], p1 = data_[((read_ + 1) % capacity) * 2 + ch];
                double p2 = data_[((read_ + 2) % capacity) * 2 + ch], p3 = data_[((read_ + 3) % capacity) * 2 + ch];
                double t = phase_;
                double v = p1 + 0.5 * t * (p2 - p0 + t * (2 * p0 - 5 * p1 + 4 * p2 - p3 + t * (3 * (p1 - p2) + p3 - p0)));
                out[i * 2 + ch] = (int16_t)(v < -32768 ? -32768 : v > 32767 ? 32767 : v);
            }
            phase_ += rate;
            while (phase_ >= 1.0 && count_ > 0) { phase_ -= 1.0; read_ = (read_ + 1) % capacity; count_--; }
        }
    }

    void report(FILE* out, const char* device) {
        std::lock_guard<std::mutex> lock(mutex_);
        fprintf(out, "sound: device %s: %.2f s handed over, %.2f s taken; reserve asked %u ms, held %.1f ms on average, least %.1f ms; ran dry %llu times (%.1f ms of silence); %llu samples given up in %llu bursts\n",
                device, (double)pushed_ / rate_, (double)pulled_ / rate_, (unsigned)(reserve_ * 1000 / rate_),
                fill_n_ ? fill_sum_ / fill_n_ * 1000.0 / rate_ : 0.0,
                fill_min_ == (size_t)-1 ? 0.0 : fill_min_ * 1000.0 / rate_,
                (unsigned long long)dry_, dry_frames_ * 1000.0 / rate_, (unsigned long long)dropped_, (unsigned long long)resyncs_);
    }

private:
    std::mutex mutex_;
    unsigned rate_;
    size_t reserve_;
    std::vector<int16_t> data_;
    size_t read_ = 0, count_ = 0, fill_min_ = (size_t)-1;
    double phase_ = 0, fill_sum_ = 0;
    uint64_t fill_n_ = 0, pushed_ = 0, pulled_ = 0, dry_ = 0, dry_frames_ = 0, dropped_ = 0, resyncs_ = 0;
    bool running_ = false;
};

}  // namespace

AudioSink* open_wav_sink(const char* path, unsigned rate) {
    FILE* f = fopen(path, "wb");
    return f ? new WavSink(f, rate) : nullptr;
}

// A device that is only a clock: a thread takes 10 ms of sound every 10 ms of wall time
// and throws it away.  It exercises the ring (reserve, rate correction, running dry)
// exactly as a real device does, on a computer where no sound may be made.
namespace {
class TimerSink : public AudioSink {
public:
    TimerSink(unsigned rate, unsigned latency_ms) : ring_(rate, latency_ms), rate_(rate), thread_([this] { run(); }) {}
    ~TimerSink() override { close(); }
    void write(const int16_t* stereo, size_t frames) override { ring_.push(stereo, frames); }
    void close() override {
        if (stop_.exchange(true)) return;
        thread_.join();
    }
    void report(FILE* out) override { ring_.report(out, "timer (no output), 10 ms"); }

private:
    void run() {
        std::vector<int16_t> buffer(rate_ / 100 * 2);
        auto next = std::chrono::steady_clock::now();
        while (!stop_) {
            next += std::chrono::milliseconds(10);
            std::this_thread::sleep_until(next);
            ring_.pull(buffer.data(), buffer.size() / 2);
        }
    }
    Ring ring_;
    unsigned rate_;
    std::atomic<bool> stop_{false};
    std::thread thread_;
};
}  // namespace

AudioSink* open_timer_sink(unsigned rate, unsigned latency_ms) { return new TimerSink(rate, latency_ms); }

// ---- a device that asks ---------------------------------------------------------------------
namespace {
// What is counted about the asking: how often, how long between two requests (the device
// holds 20 ms besides the buffer it hands back; a request more than 30 ms after the one
// before means it may have had nothing to play), how long rendering took.
class PullCount {
public:
    void pull(AudioSource* source, int16_t* out, size_t frames) {
        auto now = std::chrono::steady_clock::now();
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (f_.pulls > 4) {                         // the first requests fill the device's buffers before it starts
                double gap = std::chrono::duration<double, std::milli>(now - last_).count();
                if (gap > f_.longest_gap_ms) f_.longest_gap_ms = gap;
                if (gap > 30.0) f_.late++;
            }
            last_ = now;
        }
        source->pull(out, frames);
        double took = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - now).count();
        std::lock_guard<std::mutex> lock(mutex_);
        f_.pulls++; f_.frames += frames; f_.render_ms += took;
        if (took > f_.longest_render_ms) f_.longest_render_ms = took;
    }
    PullFigures figures() { std::lock_guard<std::mutex> lock(mutex_); return f_; }
    void report(FILE* out, const char* device, unsigned rate) {
        PullFigures f = figures();
        fprintf(out, "sound: device %s, asking for its sound: %.2f s taken in %llu requests; longest time between two %.1f ms, %llu more than 30 ms apart "
                     "(the device may have had nothing to play); rendering a request took %.3f ms on average, %.2f ms at most\n",
                device, (double)f.frames / rate, (unsigned long long)f.pulls, f.longest_gap_ms, (unsigned long long)f.late,
                f.pulls ? f.render_ms / f.pulls : 0.0, f.longest_render_ms);
    }
private:
    std::mutex mutex_;
    PullFigures f_;
    std::chrono::steady_clock::time_point last_;
};

class TimerPuller : public PullDevice {
public:
    TimerPuller(unsigned rate, AudioSource* source) : rate_(rate), source_(source), thread_([this] { run(); }) {}
    ~TimerPuller() override { close(); }
    void close() override {
        if (stop_.exchange(true)) return;
        thread_.join();
    }
    void report(FILE* out) override { count_.report(out, "timer (no output), 10 ms", rate_); }
    PullFigures figures() override { return count_.figures(); }
private:
    void run() {
        std::vector<int16_t> buffer(rate_ / 100 * 2);
        auto next = std::chrono::steady_clock::now();
        while (!stop_) {
            next += std::chrono::milliseconds(10);
            std::this_thread::sleep_until(next);
            count_.pull(source_, buffer.data(), buffer.size() / 2);
        }
    }
    unsigned rate_;
    AudioSource* source_;
    PullCount count_;
    std::atomic<bool> stop_{false};
    std::thread thread_;
};
}  // namespace

PullDevice* open_timer_puller(unsigned rate, AudioSource* source) { return new TimerPuller(rate, source); }

}  // namespace snd
}  // namespace rta

// ---- macOS: AudioQueue -------------------------------------------------------------------
#if defined(__APPLE__)
#include <AudioToolbox/AudioToolbox.h>
#include <dlfcn.h>

namespace rta {
namespace snd {
namespace {

class QueueSink : public PullDevice {
public:
    // with a source the device asks it for every buffer; without, it reads the ring
    QueueSink(unsigned rate, unsigned latency_ms, float gain, AudioSource* source = nullptr)
        : ring_(rate, latency_ms), silent_(gain <= 0), source_(source), rate_(rate) {
        void* lib = dlopen("/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox", RTLD_LAZY);
        if (!lib) { why_ = "AudioToolbox could not be loaded"; return; }
#define RTA_SYM(name) name##_ = (decltype(name##_))dlsym(lib, #name)
        RTA_SYM(AudioQueueNewOutput); RTA_SYM(AudioQueueAllocateBuffer); RTA_SYM(AudioQueueEnqueueBuffer);
        RTA_SYM(AudioQueueStart); RTA_SYM(AudioQueueStop); RTA_SYM(AudioQueueDispose); RTA_SYM(AudioQueueSetParameter);
#undef RTA_SYM
        if (!AudioQueueNewOutput_ || !AudioQueueAllocateBuffer_ || !AudioQueueEnqueueBuffer_ || !AudioQueueStart_) { why_ = "AudioQueue functions not found"; return; }
        AudioStreamBasicDescription format;
        memset(&format, 0, sizeof format);
        format.mSampleRate = rate;
        format.mFormatID = kAudioFormatLinearPCM;
        format.mFormatFlags = kLinearPCMFormatFlagIsSignedInteger | kLinearPCMFormatFlagIsPacked;
        format.mBytesPerPacket = 4; format.mFramesPerPacket = 1; format.mBytesPerFrame = 4;
        format.mChannelsPerFrame = 2; format.mBitsPerChannel = 16;
        if ((status_ = AudioQueueNewOutput_(&format, callback, this, nullptr, nullptr, 0, &queue_)) != 0) { queue_ = nullptr; why_ = "AudioQueueNewOutput"; return; }
        if (AudioQueueSetParameter_) AudioQueueSetParameter_(queue_, kAudioQueueParam_Volume, gain);
        for (int i = 0; i < kBuffers; i++) {
            AudioQueueBufferRef buffer;
            if (AudioQueueAllocateBuffer_(queue_, kFrames * 4, &buffer) != 0) continue;
            callback(this, queue_, buffer);
        }
        if ((status_ = AudioQueueStart_(queue_, nullptr)) != 0) { why_ = "AudioQueueStart"; close(); return; }
        ok_ = true;
    }
    ~QueueSink() override { close(); }
    bool ok() const { return ok_; }
    const char* why() const { return why_; }
    int status() const { return (int)status_; }
    void write(const int16_t* stereo, size_t frames) override { if (!source_) ring_.push(stereo, frames); }
    PullFigures figures() override { return count_.figures(); }
    void close() override {
        if (!queue_) return;
        if (AudioQueueStop_) AudioQueueStop_(queue_, true);
        if (AudioQueueDispose_) AudioQueueDispose_(queue_, true);
        queue_ = nullptr;
    }
    void report(FILE* out) override {
        if (source_) {
            count_.report(out, "AudioQueue, 3 x 10 ms", rate_);
            fprintf(out, "sound: delay from a register write to the device: 20 to 30 ms of queue buffers + the device's own\n");
            return;
        }
        ring_.report(out, "AudioQueue, 3 x 10 ms");
        fprintf(out, "sound: delay from render to the device: the reserve + 20 to 30 ms of queue buffers + the device's own\n");
    }

private:
    enum { kBuffers = 3, kFrames = 480 };
    static void callback(void* self, AudioQueueRef queue, AudioQueueBufferRef buffer) {
        QueueSink* sink = (QueueSink*)self;
        if (sink->source_) sink->count_.pull(sink->source_, (int16_t*)buffer->mAudioData, kFrames);
        else sink->ring_.pull((int16_t*)buffer->mAudioData, kFrames);
        if (sink->silent_) memset(buffer->mAudioData, 0, kFrames * 4);     // gain 0: nothing can be heard
        buffer->mAudioDataByteSize = kFrames * 4;
        sink->AudioQueueEnqueueBuffer_(queue, buffer, 0, nullptr);
    }
    Ring ring_;
    bool silent_;
    AudioSource* source_;
    unsigned rate_;
    PullCount count_;
    bool ok_ = false;
    const char* why_ = "";
    OSStatus status_ = 0;
    AudioQueueRef queue_ = nullptr;
    OSStatus (*AudioQueueNewOutput_)(const AudioStreamBasicDescription*, AudioQueueOutputCallback, void*, CFRunLoopRef, CFStringRef, UInt32, AudioQueueRef*) = nullptr;
    OSStatus (*AudioQueueAllocateBuffer_)(AudioQueueRef, UInt32, AudioQueueBufferRef*) = nullptr;
    OSStatus (*AudioQueueEnqueueBuffer_)(AudioQueueRef, AudioQueueBufferRef, UInt32, const AudioStreamPacketDescription*) = nullptr;
    OSStatus (*AudioQueueStart_)(AudioQueueRef, const AudioTimeStamp*) = nullptr;
    OSStatus (*AudioQueueStop_)(AudioQueueRef, Boolean) = nullptr;
    OSStatus (*AudioQueueDispose_)(AudioQueueRef, Boolean) = nullptr;
    OSStatus (*AudioQueueSetParameter_)(AudioQueueRef, AudioQueueParameterID, AudioQueueParameterValue) = nullptr;
};

}  // namespace

// The default output unit, asking a source for every buffer on the real-time sound thread.
class UnitPuller : public PullDevice {
public:
    UnitPuller(unsigned rate, float gain, AudioSource* source) : source_(source), rate_(rate), gain_(gain) {
        void* lib = dlopen("/System/Library/Frameworks/AudioToolbox.framework/AudioToolbox", RTLD_LAZY);
        if (!lib) { why_ = "AudioToolbox could not be loaded"; return; }
#define RTA_SYM(name) name##_ = (decltype(name##_))dlsym(lib, #name)
        RTA_SYM(AudioComponentFindNext); RTA_SYM(AudioComponentInstanceNew); RTA_SYM(AudioComponentInstanceDispose);
        RTA_SYM(AudioUnitSetProperty); RTA_SYM(AudioUnitInitialize); RTA_SYM(AudioUnitUninitialize);
        RTA_SYM(AudioOutputUnitStart); RTA_SYM(AudioOutputUnitStop);
#undef RTA_SYM
        if (!AudioComponentFindNext_ || !AudioComponentInstanceNew_ || !AudioUnitSetProperty_ || !AudioUnitInitialize_ || !AudioOutputUnitStart_) { why_ = "output unit functions not found"; return; }
        AudioComponentDescription description;
        memset(&description, 0, sizeof description);
        description.componentType = kAudioUnitType_Output;
        description.componentSubType = kAudioUnitSubType_DefaultOutput;
        description.componentManufacturer = kAudioUnitManufacturer_Apple;
        AudioComponent component = AudioComponentFindNext_(nullptr, &description);
        if (!component) { why_ = "no default output unit"; return; }
        if ((status_ = AudioComponentInstanceNew_(component, &unit_)) != 0) { unit_ = nullptr; why_ = "AudioComponentInstanceNew"; return; }
        AudioStreamBasicDescription format;
        memset(&format, 0, sizeof format);
        format.mSampleRate = rate;
        format.mFormatID = kAudioFormatLinearPCM;
        format.mFormatFlags = kLinearPCMFormatFlagIsSignedInteger | kLinearPCMFormatFlagIsPacked;
        format.mBytesPerPacket = 4; format.mFramesPerPacket = 1; format.mBytesPerFrame = 4;
        format.mChannelsPerFrame = 2; format.mBitsPerChannel = 16;
        if ((status_ = AudioUnitSetProperty_(unit_, kAudioUnitProperty_StreamFormat, kAudioUnitScope_Input, 0, &format, sizeof format)) != 0) { why_ = "stream format"; close(); return; }
        AURenderCallbackStruct callback = {render, this};
        if ((status_ = AudioUnitSetProperty_(unit_, kAudioUnitProperty_SetRenderCallback, kAudioUnitScope_Input, 0, &callback, sizeof callback)) != 0) { why_ = "render callback"; close(); return; }
        if ((status_ = AudioUnitInitialize_(unit_)) != 0) { why_ = "AudioUnitInitialize"; close(); return; }
        if ((status_ = AudioOutputUnitStart_(unit_)) != 0) { why_ = "AudioOutputUnitStart"; close(); return; }
        ok_ = true;
    }
    ~UnitPuller() override { close(); }
    bool ok() const { return ok_; }
    const char* why() const { return why_; }
    int status() const { return (int)status_; }
    PullFigures figures() override { return count_.figures(); }
    void close() override {
        if (!unit_) return;
        if (AudioOutputUnitStop_) AudioOutputUnitStop_(unit_);
        if (AudioUnitUninitialize_) AudioUnitUninitialize_(unit_);
        if (AudioComponentInstanceDispose_) AudioComponentInstanceDispose_(unit_);
        unit_ = nullptr;
    }
    void report(FILE* out) override {
        count_.report(out, "default output unit (real-time thread)", rate_);
        fprintf(out, "sound: delay from a register write to the device: one request of the device (about 10 ms) + the device's own\n");
    }

private:
    static OSStatus render(void* self, AudioUnitRenderActionFlags*, const AudioTimeStamp*, UInt32, UInt32 frames, AudioBufferList* data) {
        UnitPuller* unit = (UnitPuller*)self;
        if (!data || !data->mNumberBuffers || !data->mBuffers[0].mData) return 0;
        int16_t* out = (int16_t*)data->mBuffers[0].mData;
        UInt32 room = data->mBuffers[0].mDataByteSize / 4;
        if (frames > room) frames = room;
        unit->count_.pull(unit->source_, out, frames);
        if (unit->gain_ <= 0) memset(out, 0, (size_t)frames * 4);      // gain 0: nothing can be heard
        else if (unit->gain_ < 1) for (UInt32 k = 0; k < frames * 2; k++) out[k] = (int16_t)(out[k] * unit->gain_);
        return 0;
    }
    AudioSource* source_;
    unsigned rate_;
    float gain_;
    PullCount count_;
    bool ok_ = false;
    const char* why_ = "";
    OSStatus status_ = 0;
    AudioComponentInstance unit_ = nullptr;
    AudioComponent (*AudioComponentFindNext_)(AudioComponent, const AudioComponentDescription*) = nullptr;
    OSStatus (*AudioComponentInstanceNew_)(AudioComponent, AudioComponentInstance*) = nullptr;
    OSStatus (*AudioComponentInstanceDispose_)(AudioComponentInstance) = nullptr;
    OSStatus (*AudioUnitSetProperty_)(AudioUnit, AudioUnitPropertyID, AudioUnitScope, AudioUnitElement, const void*, UInt32) = nullptr;
    OSStatus (*AudioUnitInitialize_)(AudioUnit) = nullptr;
    OSStatus (*AudioUnitUninitialize_)(AudioUnit) = nullptr;
    OSStatus (*AudioOutputUnitStart_)(AudioUnit) = nullptr;
    OSStatus (*AudioOutputUnitStop_)(AudioUnit) = nullptr;
};

AudioSink* open_device_sink(unsigned rate, unsigned latency_ms, float gain) {
    QueueSink* sink = new QueueSink(rate, latency_ms, gain);
    if (sink->ok()) return sink;
    fprintf(stderr, "sound: device not opened: %s (status %d)\n", sink->why(), sink->status());
    delete sink;
    return nullptr;
}

PullDevice* open_device_puller(unsigned rate, float gain, AudioSource* source) {
    UnitPuller* unit = new UnitPuller(rate, gain, source);
    if (unit->ok()) return unit;
    fprintf(stderr, "sound: output unit not opened: %s (status %d); trying an AudioQueue\n", unit->why(), unit->status());
    delete unit;
    QueueSink* sink = new QueueSink(rate, 0, gain, source);
    if (sink->ok()) return sink;
    fprintf(stderr, "sound: device not opened: %s (status %d)\n", sink->why(), sink->status());
    delete sink;
    return nullptr;
}

}  // namespace snd
}  // namespace rta

#elif defined(_WIN32)
#include "audio_out_win.cpp"        // WASAPI, waveOut as the fallback: the same two functions

#else

namespace rta {
namespace snd {
AudioSink* open_device_sink(unsigned, unsigned, float) { return nullptr; }
PullDevice* open_device_puller(unsigned, float, AudioSource*) { return nullptr; }
}  // namespace snd
}  // namespace rta

#endif
