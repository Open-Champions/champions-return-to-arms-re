// fpcontrols.h - controls for the views that look along the ground (chase, shoulder, first
// person; app/fpview.h): mouse and right-stick look, movement relative to the look, the
// character turned to where the player looks, and what a HUD needs to know about aim,
// things in reach and attackers out of sight.  docs/issues/native-first-person-controls.md
// says how the original moves and aims (part 1) and what was run (part 2).
//
// THE RULE.  The simulation is not touched and is told nothing it does not already
// understand: everything here ends in an ordinary controller row (buttons, two sticks) and
// in the game camera's yaw word (camera +0x68) - the word the game itself turns with the
// camera stick, reads live offline and sends with every input record in a net game.  So a
// machine in first person and a machine in the overhead view compute the same game from the
// same rows.  What this file reads from the game's memory it only reads.
//
//  - Look: the yaw word is driven here (mouse, right stick x) instead of by the game's own
//    camera stick code, which is held at rest in these views (it turns at 82 degrees a
//    second at most, and its y would step the hidden zoom).  Pitch is the picture's only:
//    it is handed to the view (take_pitch).
//  - Move: the left stick is passed on as it is.  Player_move turns the character toward
//    "stick angle - yaw word" and runs it along its facing, so with the yaw word following
//    the look, forward is where the player looks and left / right / back are relative to it.
//  - Face: the original has no strafe and no turn button; a character faces where it last
//    ran.  But a push just past the stick's dead zone turns it (40 % of the angle a tick)
//    and moves it by nothing: the step it asks for is below the 0.0316 units under which the
//    move routine does not move.  That push, pointed where the player looks, is what turns
//    the character with the view: while it stands, before a strike (the press is held back
//    for the few ticks the turn takes) and through the states in which the stick only turns
//    (drawing a bow, casting, blocking, the wind-up of a swing).
//
// This file includes nothing of the runtime but iface.h and nothing of fpview: the
// application tells it the view (set_view) and carries the pitch and the view kick across.
//
// THREADS.  translate(), hud(), apply_view(), command() belong to the game's thread (the
// controller read at a vertical blank; the view's call-out).  mouse_motion(), mouse_button(),
// set_view(), setting() may be called from any thread.
#pragma once
#include "iface.h"

#include <cstdint>
#include <string>

namespace fpcontrols {

// The views, numbered as fpview::Mode numbers them.
enum View : int { OVERHEAD = 0, ACTION = 1, CHASE = 2, SHOULDER = 3, FIRST = 4, VIEW_COUNT = 5 };

// ---- from the application ---------------------------------------------------------------
// The view selected, and whether this frame is drawn with it (false: the game's own camera
// has the frame - a cutscene, a dialogue, a menu, death, a load).  Without a call the view
// is OVERHEAD and nothing of this file changes a row.  `look_pitch`: the view's pitch now,
// degrees (for the HUD's figures only).
void set_view(int view, bool active, float look_pitch = 0);

// Pointer motion since the last call, in the pointer's own counts: right and down positive.
void mouse_motion(float dx, float dy);
// A mouse button: 0 left, 1 right, 2 middle, 3 and 4 the side buttons.
void mouse_button(int button, bool down);
void mouse_wheel(float steps);                  // up positive
void release_all();                             // the window lost the keyboard: nothing stays held

// The last step of the application's controller read (port 0 only; game's thread): `state`
// holds what script, control socket, controller and keyboard hold; what the game is to be
// given is put in its place.  `blank` counts vertical blanks.
void translate(uint64_t blank, rta::PadState& state);

// The "strafe mode" section of the fix set (app/fp-proposed.pnach; docs/issues/native-first-person-controls.md
// part 3): a player can run one way and face another.  strafe_wanted(): -1 when the game does not have the
// section, else the mode this machine's player should have now (0 or 1).  take_strafe_send(): -1, or a mode the
// application is to send NOW by calling the section's sender (STRAFE_SENDER, mode in a0) on the game's thread -
// asked for when the view changes and again while the simulation's byte is not what is wanted (a new character
// after a level change or a respawn starts with the mode off on every machine).
int strafe_wanted();
int take_strafe_send();
const uint32_t STRAFE_SENDER = 0x215c98;
// Degrees of pitch (up positive) the look has gained since the last call: for the view.
float take_pitch();
// The view about to be built (the view's on_view call-out): the picture's centre is turned
// onto the heading a pushed-up stick walks along (2.5 degrees from the game camera's own,
// the 0x41c2 of Player_move), and the kick of a swing or a hit is added.  All vectors are
// unit vectors in world space (z up).
void apply_view(int view, float forward[3], float up[3]);

// Should the pointer be the look's now: a look view is active and the player is playing
// (the application hides and holds the pointer while this is true and it has the keyboard).
bool wants_pointer();

// ---- for a HUD --------------------------------------------------------------------------
struct Mark {
    bool valid = false;
    uint32_t object = 0;        // guest address of the creature
    float x = 0, y = 0, z = 0;  // its middle (feet + half its height), world space
    float distance = 0;         // from the player's feet to its rim, in the ground plane
    float bearing = 0;          // degrees to the right (+) or left (-) of the look
    float hp = 0, hp_max = 0;
};
struct Threat {
    uint32_t object = 0;
    float x = 0, y = 0, z = 0;
    float distance = 0;         // centre to centre
    float bearing = 0;          // degrees right (+) / left (-) of the look; beyond +-90 it is behind
    bool targets_me = false;    // its target handle is the local player
    bool attacking = false;     // ... and it is within its reach and turned toward the player
    bool in_view = false;       // inside the horizontal field of the view
};
struct Hud {
    uint64_t blank = 0;
    uint32_t tick = 0;
    int view = OVERHEAD;
    bool look = false;                  // a look view is active and this file is steering
    bool playing = false;               // a local player object exists, alive, and the pad reaches it
    int slot = -1;
    uint32_t player = 0;                // the object the player sees (the prediction copy in a net game)
    float x = 0, y = 0, z = 0;
    float look_heading = 0;             // degrees, 0 = +x, 90 = +y: where a pushed-up stick walks
    float look_pitch = 0;               // degrees, what this file has handed to the view in all
    float facing = 0;                   // the character's heading, same convention
    float facing_error = 0;             // look - facing, degrees (-180..180)
    int state = -1;                     // the player's action state (docs/player.md): 2 neutral, 1 melee, 0 ranged, 5 casting, 8 blocking ...
    int weapon_class = 0;               // 0..7 (4 bow, 6 thrown)
    bool ranged = false;
    bool aligning = false;              // a press is being held back while the character turns
    // what the simulation would pick if the player struck / shot now, by its own rules
    Mark melee;                         // nearest by the melee score inside 60 degrees and reach
    Mark shot;                          // the first enemy in the 20-degree arc ahead within 340: arrows and spells fly at it
    Mark locked;                        // the target the simulation holds now (during a swing or a shot)
    bool reticle = false;               // a reticle means something: a look view, playing, a ranged weapon or a cast in hand
    // something usable in reach (the game's own prompt: fade 0..128, kind 1 the use button, 2 triangle)
    bool usable = false;
    int usable_kind = 0, usable_fade = 0;
    uint32_t usable_object = 0;
    float usable_x = 0, usable_y = 0, usable_z = 0, usable_bearing = 0;
    char usable_text[96] = "";          // the game's prompt text, ASCII
    // attackers
    int threat_count = 0;
    Threat threats[16];                 // nearest first
    int behind = 0;                     // of them: targeting the player and outside the view
    // events, as counters that only grow (a HUD or the view compares with what it saw last)
    uint32_t swings = 0, hits_dealt = 0, hits_taken = 0, deaths = 0, respawns = 0;
    float last_hit_bearing = 0;         // where the last hit taken came from, degrees right (+) / left (-) of the look
    float last_hit_amount = 0;
};
const Hud& hud();
std::string hud_text();                 // the same as "key=value" words on one line (tests, logs)

// ---- settings, help, tests ----------------------------------------------------------------
// A line of the settings file: "controls.<name> = value" (list in settings_text()).  False
// when the key is not one of them.
bool setting(const char* key, const char* value);
std::string settings_text();
std::string help_text();                // the keys and buttons of the look views, for the help panel
// "app fpc ..." (script / control socket): mouse DX DY | button left|right|middle down|up |
// wheel N | set KEY VALUE | info | hud | log on|off.  The answer is one line.
std::string command(const std::string& text, uint64_t blank);
std::string figures();                  // counters for the report at the end of a run

// Mouse buttons and extra keys as controller buttons (rta::PadButton bits), given the view.
uint16_t mouse_buttons_as_pad();

}  // namespace fpcontrols
