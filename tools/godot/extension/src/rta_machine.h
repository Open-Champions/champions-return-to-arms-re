// rta_machine.h - RtaMachine: the translated game as a Godot object.
//
// A script loads the game library (a file on the user's machine), starts the machine with a
// disc image and a data directory, and then, once per picture, sets the controllers and
// calls step(): the machine runs to its next vertical blank and the frame it finished is
// there to be looked at - as the picture the library's own renderer drew (get_picture), or
// as the draw list (RtaDrawer takes it from here).
#pragma once
#include "rta_library.h"

#include <godot_cpp/classes/image.hpp>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>

namespace godot {

class RtaMachine : public RefCounted {
    GDCLASS(RtaMachine, RefCounted)
  public:
    bool load_library(const String& path);
    String get_error() const { return error; }
    bool has(const String& feature) const;
    int start(const Dictionary& config);
    void set_pad(int port, int buttons, int lx, int ly, int rx, int ry);
    int step(int wait_ms);
    int poll(int wait_ms);
    void run(double hz);
    void stop();
    bool ended() const;
    int exit_code() const;
    String info() const;
    int64_t fields() const;
    // the frame last taken
    bool has_frame() const { return frame != nullptr; }
    int64_t get_frame_number() const { return frame ? (int64_t)frame->number : -1; }
    int64_t get_sim_tick() const { return frame ? (int64_t)frame->sim_tick : 0; }
    double get_frame_aspect() const { return frame ? frame->aspect : 4.0 / 3.0; }
    int get_draw_count() const { return frame ? (int)frame->draw_count : 0; }
    int get_vertex_count() const { return frame ? (int)frame->vertex_count : 0; }
    PackedStringArray get_shots() const;
    PackedStringArray get_host_commands() const;
    Ref<Image> get_picture() const;         // null when the frame carries none
    // the machine's memory (read only): for a script that wants to show a figure of the game
    int64_t peek_u32(int64_t address) const;
    double peek_f32(int64_t address) const;
    String peek_string(int64_t address, int max_bytes) const;

    const rtag_frame* current() const { return frame; }

  protected:
    static void _bind_methods();

  private:
    String error;
    const rtag_frame* frame = nullptr;
    bool started = false;
};

}  // namespace godot
