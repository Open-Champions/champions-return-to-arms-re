// rta_audio.h - the game's sound as a Godot audio stream.
//
// RtaAudioStream is a stream an AudioStreamPlayer plays; its playback asks the game library
// for sound whenever Godot's mixer asks it (rtag_audio_pull on the audio thread), so the
// game's sound side runs on Godot's audio clock - by itself, as the console's sound
// processor does - and Godot's buses, volume and effects apply to it like to any stream.
// 48 kHz; the resampled playback base class converts when the mixer runs at another rate.
#pragma once
#include <godot_cpp/classes/audio_frame.hpp>
#include <godot_cpp/classes/audio_stream.hpp>
#include <godot_cpp/classes/audio_stream_playback.hpp>
#include <godot_cpp/classes/audio_stream_playback_resampled.hpp>

#include <atomic>
#include <cstdint>
#include <vector>

namespace godot {

class RtaAudioPlayback : public AudioStreamPlaybackResampled {
    GDCLASS(RtaAudioPlayback, AudioStreamPlaybackResampled)
  public:
    void _start(double p_from_pos) override;
    void _stop() override;
    bool _is_playing() const override;
    int32_t _get_loop_count() const override { return 0; }
    double _get_playback_position() const override;
    void _seek(double p_position) override {}
    int32_t _mix_resampled(AudioFrame* p_dst_buffer, int32_t p_frame_count) override;
    float _get_stream_sampling_rate() const override { return 48000.0f; }

  protected:
    static void _bind_methods() {}

  private:
    bool playing = false;
    uint64_t frames = 0;
    std::vector<int16_t> buffer;
};

class RtaAudioStream : public AudioStream {
    GDCLASS(RtaAudioStream, AudioStream)
  public:
    Ref<AudioStreamPlayback> _instantiate_playback() const override;
    String _get_stream_name() const override { return "Champions: Return to Arms (translated game)"; }
    double _get_length() const override { return 0.0; }
    bool _is_monophonic() const override { return true; }
    // figures: frames asked for by the mixer so far, and the largest request
    static std::atomic<uint64_t> frames_mixed, requests;

  protected:
    static void _bind_methods();
};

}  // namespace godot
