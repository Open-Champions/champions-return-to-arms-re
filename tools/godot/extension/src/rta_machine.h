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
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/vector3.hpp>

namespace godot {

class RtaMachine : public RefCounted {
    GDCLASS(RtaMachine, RefCounted)
  public:
    bool load_library(const String& path);
    // Godot moves the process into the project's directory; a run that was given relative paths (a script, a log)
    // goes back to where it was started from before the machine starts
    bool change_directory(const String& path);
    String get_error() const { return error; }
    bool has(const String& feature) const;
    int start(const Dictionary& config);
    void set_pad(int port, int buttons, int lx, int ly, int rx, int ry);
    // Latest local-port motors: supported/valid, weak (small != 0), strong (large / 255), raw small/large, generation.
    // Neutral before start, after stop/exit or with an old library. The host applies/releases physical devices.
    Dictionary get_rumble(int port) const;
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
    // The camera the frame was drawn with (rtag_view): mode, mode_name, shown, blend, active, fallback, fallback_why,
    // eye, forward, up, right (Vector3, the game's world: z up), fov, head, hide_player, yaw, near, far, player, facing,
    // look_pitch, tick, valid.  Empty before the first frame.
    Dictionary get_view() const;
    // "view" = overhead|action|chase|shoulder|first, "view.<mode>.<name>" = a view's setting, "game_hud" = on|off
    bool set_option(const String& key, const String& value);
    // The controls of the look views (tools/recomp/app/fpcontrols.h, inside the library): what they know, with the field
    // names of fpcontrols::Hud - blank, tick, view, look, playing, slot, player, x, y, z, look_heading, look_pitch, facing,
    // facing_error, state, weapon_class, ranged, aligning, reticle, melee / shot / locked ({valid, object, x, y, z,
    // distance, bearing, hp, hp_max}), usable, usable_kind, usable_fade, usable_object, usable_x/y/z, usable_bearing,
    // usable_text, threat_count, threats (Array of {object, x, y, z, distance, bearing, targets_me, attacking, in_view}),
    // behind, swings, hits_dealt, hits_taken, deaths, respawns, last_hit_bearing, last_hit_amount, wants_pointer.
    // Empty when the library has no controls.
    Dictionary get_controls_hud() const;
    Dictionary get_film() const;       // the film playing now (rtag_film_now): {key (16 hex digits), picture, width, height}; {} none
    // The pointer as the look: motion since the last call (right and down positive), wheel steps; a button (0 left,
    // 1 right, 2 middle, 3 and 4 the side buttons).  wants_pointer(): a look view is active and the player is playing -
    // the host hides and holds the pointer while this is true and it has the keyboard.
    void mouse(double dx, double dy, double wheel);
    void mouse_button(int button, bool down);
    bool wants_pointer() const;
    PackedStringArray get_shots() const;
    PackedStringArray get_host_commands() const;
    Ref<Image> get_picture() const;         // null when the frame carries none
    // the machine's memory (read only): for a script that wants to show a figure of the game
    int64_t peek_u32(int64_t address) const;
    double peek_f32(int64_t address) const;
    String peek_string(int64_t address, int max_bytes) const;
    PackedByteArray peek_bytes(int64_t address, int64_t length) const;   // test aid (main.gd --control)
    bool poke_bytes(int64_t address, const PackedByteArray& bytes);     // test aid (main.gd --control): a write into the game's memory
    // The game's point lights (docs/spec/render-pipeline.md 5.2): the light nodes of its 90 x 90 grid of 256-unit cells
    // (g_lightGrid 0x5d34d8, origin -11520) and of its overflow list, of the current layer, within `radius` of `at` (the
    // game's world: z up).  Each {address, position, colour (the level's, 0x80 = 1), model_colour, radius (+0x1c: what the
    // game's own search reaches with), radius_2 (+0x20), falloff (+0x28: 1 / radius^2 for the level's lights), floor, layer}.  The level's light chunks (torches, braziers: 16 slots, their flicker
    // included), LightEffect objects and spell effects are all such nodes.
    Array get_lights(const Vector3& at, double radius, int max_count) const;

    const rtag_frame* current() const { return frame; }
    // The level's generated ceilings and skirts (rtag_fill_get, tools/recomp/render/worldfill.h): false when the library
    // has none for the level that is loaded.  The pointers in `out` stay valid until the next call.
    bool fill(rtag_fill& out) const;
    // the same as figures: level, serial, vertices, meshes, ceilings, skirts ({} when there is none)
    Dictionary get_fill_info() const;
    // The frame's skeletons (rtag_skeletons_get): a pose stream a Skeleton3D takes as it is - per skeleton its parents,
    // the bind-pose joint origins (rest = T(bind[j] - bind[parent])), the posed joint frames in the world (global poses)
    // and the skin matrices; per scene piece its skeleton, object and sources.  with_mesh: also the bind-pose sources and
    // the drawn corners (to re-skin and compare, or to draw the game's own mesh re-posed).
    Dictionary get_skeletons(bool with_mesh) const;
    // the tester's kit (tools/recomp/app/testerkit.h, rtag.h): "" when the library has none
    String report_begin(const String& host_lines);
    String report_finish(const String& folder, const String& text, bool keep);
    String build_line() const;
    String report_told() const;
    int release();                          // let one blank go without taking a frame (-2: the library cannot; use step)
    double frame_age_ms() const;
    double frame_since_release_ms() const;  // ... and since the game was let go into it (its controller read); -1 unknown            // how long ago the frame taken last was finished (-1: none, or a library without it)

  protected:
    static void _bind_methods();

  private:
    String error;
    const rtag_frame* frame = nullptr;
    bool started = false;
};

}  // namespace godot
