// fpview.h - the views of the native build: the classic overhead camera, a closer "action"
// overhead, a chase camera behind the character, over the shoulder, and first person.
// docs/issues/native-first-person.md says what was run and what each view looks like.
//
// HOW.  The game's own camera is never touched.  It runs as it always did (follow, rotate,
// zoom, collide, shake; cutscene, dialogue and menu cameras), so every word the simulation
// reads from it - the yaw that makes "up on the stick" a direction, the camera mode, the
// camera focus - is what it is in the overhead view.  Only for the length of the DRAW PASS
// of a displayed frame (tasks_call(0, 1), 0x19e798) is another camera put in place, by the
// game's own functions: camera_setProjection (field of view -> g_projScale and the two sets
// of frustum planes) and camera_setView (position and orientation -> the camera matrix, the
// three view-projection matrices, the planes in world space).  The game then culls level
// chunks, objects, lights and decals for that camera and builds its draw list for it; when
// the pass returns, the words those two functions wrote are put back.  The simulation ticks
// that follow see the game's own camera.
//
// This header is the whole interface: the view of the frame for whoever needs it, and two
// call-outs.  It includes nothing of the runtime; fpview.cpp is compiled with the runtime's
// flags and supplies the fn_<address> of the functions listed under "view modes" in
// tools/recomp/hle.txt.
//
// THREADS.  set_mode / mode / setting may be called from any thread.  Everything else -
// view(), the call-outs - belongs to the game's thread; a call-out runs on it.
#pragma once
#include <cstdint>

struct Ctx;     // the translated code's registers (rt/recomp.h); call-outs may call game functions with it

namespace fpview {

enum Mode : int {
    OVERHEAD = 0,   // the game's camera, untouched: nothing of this file runs
    ACTION = 1,     // overhead, closer and lower
    CHASE = 2,      // third person, behind the character at the game camera's yaw
    SHOULDER = 3,   // over the right shoulder
    FIRST = 4,      // from the character's eyes
    MODE_COUNT = 5
};

struct Vec3 { float x, y, z; };     // world space: z is up, units are the game's (a character is about 60 high)

// The camera of the frame being drawn and what it was made from.  Angles in degrees.
struct View {
    // ---- which view ----
    int mode = OVERHEAD;        // the view selected
    int shown = OVERHEAD;       // the view this frame is closest to (differs from `mode` during a transition or a fallback)
    float blend = 0;            // 0 = the game's own camera ... 1 = the selected view (eased)
    bool active = false;        // this frame is drawn with a camera of this file (blend > 0)
    bool fallback = false;      // a view is selected but the game's camera has the frame (cutscene, dialogue, menu, death, load, two local players)
    const char* fallback_why = "";

    // ---- the camera the frame is drawn with: a call-out of on_view may change these ----
    Vec3 eye{};                 // position
    Vec3 forward{};             // unit vectors; right = forward x world up, down completes the frame
    Vec3 up{};
    Vec3 right{};
    float fov = 50;             // vertical field of view (the game's own camera: 50)
    float near_plane = 18;      // the game's own: 18
    float far_plane = 1800;     // of the projection's depth range (the game's own: 1800); see cull_far
    float cull_far = 0;         // the far plane everything is culled by (g_farClip; the game caps it at 1800).  0 = leave the level's own
    Vec3 stream_focus{};        // the point the level's texture cells are kept loaded around (worldtex_stream)
    bool hide_player = false;   // the local player's model is left out of the picture (first person)

    // ---- the game's own camera of this frame (never changed) ----
    Vec3 game_eye{}, game_forward{}, game_up{}, game_right{};
    float game_fov = 50;
    float game_yaw = 0;         // heading of the game camera in the ground plane: atan2(forward.y, forward.x)
    int game_zoom = 1;          // the game camera's zoom index 0..2 (camera stick up / down steps it)
    uint16_t game_yaw_word = 0; // camera +0x68: the word Player_move steers by

    // ---- the local player ----
    bool have_player = false;
    int slot = -1;              // player slot the view follows
    uint32_t player_object = 0; // guest address of its GameObject in the player record (0 = none)
    uint32_t drawn_object = 0;  // the object that is on screen for it: in a net game the prediction copy (g_ghost
                                // 0x4027bc, through net_objOrGhost 0x13e180) when there is one, else player_object.
                                // Position and facing below are this object's
    Vec3 player_pos{};          // the object's position (its feet)
    float player_height = 72;   // its height extent (object +0x20; 72 for a human-sized character): the views scale by it
    Vec3 head{};                // the eye point: head joint when the pose gives one, else feet + eye height
    bool head_from_pose = false;
    float facing = 0;           // heading of the character in the ground plane, degrees, same convention as game_yaw
    Vec3 facing_dir{};          // unit vector of it
    float look_yaw = 0;         // heading the view looks along (the game camera's yaw, plus what a view adds)
    float look_pitch = 0;       // up (+) / down (-) of a view that lets the stick look

    // ---- when ----
    uint32_t tick = 0;          // g_simFrame
    uint64_t frame = 0;         // draw passes so far
};

// The view of the draw pass that is running or last ran.
const View& view();

// Selecting a view (any thread; takes effect at the next draw pass, eased over a third of a second).
void set_mode(int mode);
int mode();
const char* mode_name(int mode);                // "overhead", "action", "chase", "shoulder", "first"
int mode_by_name(const char* name);             // -1 when it is not one
void cycle(int step = 1);                       // the key: next view

// Looking up (+) and down (-) by other means than the camera stick (a mouse: fpcontrols.h):
// degrees added to the selected view's pitch at the next draw pass, inside its limits.
void add_pitch(float degrees);

// A per-view setting, as a line of the settings file gives it: key "view" (value = a mode
// name), or "view.<mode>.<name>" with <name> one of fov, near, distance, height, side,
// pitch, pitch_min, pitch_max, eye_height, eye_forward, look_speed, head (pose|fixed),
// hide_player (yes|no), collide (yes|no), far, ease.  False when the key is not one.
bool setting(const char* key, const char* value);
// The settings as lines for the settings file.
const char* settings_text();

// Call-outs.  on_view: after this file has made the frame's camera and before the game is
// asked to build its projection and planes for it - change the View (eye, forward, up, fov,
// near_plane, far_plane, cull_far, stream_focus, hide_player) and it is what gets built.
// Called only for frames with active == true.  on_drawn: when the draw pass has returned and
// the frame's draw list is complete, the view still in place (the game's words are put back
// right after); called for every draw pass, active or not.
typedef void (*ViewFn)(View& view, Ctx* c, void* user);
typedef void (*DrawnFn)(const View& view, Ctx* c, void* user);
void on_view(ViewFn fn, void* user = nullptr);
void on_drawn(DrawnFn fn, void* user = nullptr);

// Helpers for call-outs (game thread only).  The game's own queries, called the way its camera
// calls them; they do not touch simulation state beyond the terrain visit stamp its own
// camera also advances.
// First terrain hit on the way from `from` to `to`: 0..1 along it, or -1 when the way is clear.
float ray(Ctx* c, Vec3 from, Vec3 to);
// Height of the ground under a point (highest sample under it); -1e6 when there is none.
float ground(Ctx* c, Vec3 at);

// Set the hook points.  Before rta::run().
void install();
// Figures for the report: draw passes with a view in place, passes that fell back, guest calls made.
void figures(uint64_t& active_frames, uint64_t& fallback_frames, uint64_t& hidden_packets);

}  // namespace fpview
