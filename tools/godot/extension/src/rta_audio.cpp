// rta_audio.cpp - see rta_audio.h.
#include "rta_audio.h"

#include "rta_library.h"

#include <godot_cpp/core/class_db.hpp>

namespace godot {

std::atomic<uint64_t> RtaAudioStream::frames_mixed{0};
std::atomic<uint64_t> RtaAudioStream::requests{0};

void RtaAudioPlayback::_start(double) {
    playing = true;
    frames = 0;
    begin_resample();
}
void RtaAudioPlayback::_stop() { playing = false; }
bool RtaAudioPlayback::_is_playing() const { return playing; }
double RtaAudioPlayback::_get_playback_position() const { return (double)frames / 48000.0; }

int32_t RtaAudioPlayback::_mix_resampled(AudioFrame* p_dst_buffer, int32_t p_frame_count) {
    RtaLibrary& lib = rta_library();
    if (p_frame_count <= 0) return 0;
    if (!lib.loaded) {
        for (int32_t k = 0; k < p_frame_count; k++) { p_dst_buffer[k].left = 0; p_dst_buffer[k].right = 0; }
        return p_frame_count;
    }
    if (buffer.size() < (size_t)p_frame_count * 2) buffer.resize((size_t)p_frame_count * 2);
    lib.rtag_audio_pull(buffer.data(), p_frame_count);
    const float scale = 1.0f / 32768.0f;
    for (int32_t k = 0; k < p_frame_count; k++) {
        p_dst_buffer[k].left = buffer[(size_t)k * 2] * scale;
        p_dst_buffer[k].right = buffer[(size_t)k * 2 + 1] * scale;
    }
    frames += (uint64_t)p_frame_count;
    RtaAudioStream::frames_mixed += (uint64_t)p_frame_count;
    RtaAudioStream::requests++;
    return p_frame_count;
}

Ref<AudioStreamPlayback> RtaAudioStream::_instantiate_playback() const {
    Ref<RtaAudioPlayback> playback;
    playback.instantiate();
    return playback;
}

static int64_t rta_audio_frames_mixed() { return (int64_t)RtaAudioStream::frames_mixed.load(); }
static int64_t rta_audio_requests() { return (int64_t)RtaAudioStream::requests.load(); }

void RtaAudioStream::_bind_methods() {
    ClassDB::bind_static_method("RtaAudioStream", D_METHOD("get_frames_mixed"), &rta_audio_frames_mixed);
    ClassDB::bind_static_method("RtaAudioStream", D_METHOD("get_requests"), &rta_audio_requests);
}

}  // namespace godot
