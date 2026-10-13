// rta_gamestate.h - RtaGameState: the game's state for a HUD drawn by Godot.
//
// A thin wrapper round the reader of tools/recomp/app/gamestate.h (a plain C struct filled from
// the machine's memory, read only): update() once per displayed frame, then the getters hand the
// struct out as Godot values.  The reader's source is compiled into this extension as it is (it
// has no dependencies and contains no game code or text: addresses and offsets only).
//
// Registered by one line in register.cpp:  GDREGISTER_CLASS(RtaGameState);
#pragma once
#include "gamestate.h"

#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_float32_array.hpp>
#include <godot_cpp/variant/string.hpp>
#include <godot_cpp/variant/vector3.hpp>

namespace godot {

class RtaGameState : public RefCounted {
    GDCLASS(RtaGameState, RefCounted)
  public:
    RtaGameState();
    ~RtaGameState();
    // Reads the state of the machine as it stands now (call it after RtaMachine.step() has returned a frame).
    // `machine` is only looked at for being there; the memory is the one library's of the process.
    // False when there is no machine or no memory yet.
    bool update(Object* machine);
    void set_aspect(double aspect);
    // The frame's camera from a host whose library has the view modes (tools/recomp/app/fpview.h): a Dictionary with
    // mode, shown, blend, active, fallback, why, hide_player, eye, forward, up, right (Vector3), fov, head.  Empty: the
    // game's own camera, read from memory.
    void set_view(const Dictionary& view);
    void set_screen_delay(int frames);
    Dictionary get_frame() const;                   // everything that is not a player, a creature or an event
    Dictionary get_player(int slot) const;
    PackedFloat32Array get_creatures() const;       // CREATURE_STRIDE floats each: see the constants of hud.gd
    String get_creature_name(int index) const;
    PackedFloat32Array get_creature_status(int index) const;    // four floats per status: kind, detail, seconds, seconds_most
    Array get_events() const;
    Vector3 project(const Vector3& world) const;    // x, y: 0..1 in the picture from the top left; z: distance along the view (<= 0 behind)
    double get_cost_usec() const;                   // of the last update: the reader alone
    int get_struct_size() const { return (int)sizeof(rta_gamestate); }

  protected:
    static void _bind_methods();

  private:
    rta_gs_reader* reader = nullptr;
    const rta_gamestate* state = nullptr;
};

}  // namespace godot
