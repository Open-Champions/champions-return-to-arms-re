// testerkit.h - what a tester needs from the program: a bug report on a key, a report when the program
// crashes, and a line that says which build this is.  One file for the three programs (app_main.cpp,
// win_main.cpp, linux/linux_main.cpp) and the Godot library (tools/godot/lib/rtag.cpp).
//
//   F8 (or L3 + R3 held together for a second on a controller): a report.  What the last 60 seconds were
//      - a row per vertical blank of the tick log (the rig's columns: lockstep tick, seed, level, players'
//      positions, states, hit points, gold, experience) and of the input record (port 1's buttons and sticks
//      as the game was given them) - is copied out of two rings that are always kept (a fixed array each,
//      written once per blank: nothing is allocated while playing), with a picture of the screen, the build
//      id, the fix set's figure, the platform, the view and mode settings, and, in a room of our own
//      (tools/recomp/net2), the room's code and every member's copy (fix set and word count).  A box on the
//      screen takes a short text (optional): Enter saves, Escape drops the report.  The report is one zip in
//      <data>/reports/; nothing is sent anywhere - the player sends it himself.
//   a crash (an access fault, an illegal instruction, abort ...): the same report without the picture, written
//      from the fault handler into <data>/reports/crash-.../; at the next start it is zipped and the program
//      says where it is.
//   F9: the build line (top right) on and off.
//
// Nothing here reads or writes anything the game's simulation reads: it reads main memory at a blank, and
// while the box is open it hands the game a controller at rest (the keyboard is the box's then).  Nothing of
// it runs in a test (--test, --offscreen: `Setup::person` false) apart from the rings and the crash handler.
#pragma once
#include <cstdint>
#include <functional>
#include <string>

namespace render { struct FrameList; }
namespace rta { struct PadState; }

namespace testerkit {

struct Setup {
    std::string data_dir;                               // reports go to <data_dir>/reports
    std::string program = "rta_app";                   // which program: rta_app, the Godot library
    bool person = true;                                 // somebody plays: the box, the line and the notes are drawn
    bool line = true;                                   // the build line at the start (F9 turns it off and on)
    bool host_ui = false;                               // the host draws the box, the line and the notes itself and reads the chord
                                                        // (Godot: tools/godot/project/testerkit.gd): only the rings and the crash handler here
    // the view and mode settings as "key = value" lines (called on the game's thread every few seconds, and
    // when a report is made); may be empty
    std::function<std::string()> describe;
    // write the next picture shown into this file (PNG); null: the report has no picture
    std::function<void(const std::string& png_path)> ask_shot;
    std::function<void(const std::string& line)> log;   // a line for the program's log
};

// Installs the crash handler, zips a crash report left by the run before and returns what to tell the
// player about it ("" when there was none).  Once, before the game starts.
std::string start(const Setup& setup);

std::string build_id();                                 // e.g. "79dbdc1+ 2026-10-21 18:02" (the source's commit, + for changes)
std::string fix_set();                                  // "9ac29719 (189 words)" or "none"
std::string platform();                                 // "macOS 26.1 arm64"
std::string build_line();                               // what F9 shows

// The game's thread.
void blank(uint64_t number, const uint8_t* ram);        // once per vertical blank: a row of the tick log (ram: rta::memory())
void pad(uint64_t number, rta::PadState& state);        // port 1 as it goes to the game: recorded; the chord; at rest while the box is open

// The window's thread (keys).
void open_box();                                        // F8: the report is taken now, the box asks for the text
bool box_open();
enum Key { KEY_ENTER, KEY_ESCAPE, KEY_BACKSPACE };
void box_key(Key key);
void box_text(const std::string& utf8);                 // typed text (one or more characters)
void toggle_line();                                     // F9
bool line_shown();

// Tests: script and control-socket lines "app report open | type TEXT | enter | escape | line | info | crash"
// (crash only with RTA_TESTERKIT_CRASH=1 in the environment: an access fault on purpose).  True when it was one.
// RTA_TESTERKIT=1 makes a test window behave as a person's (the box, the line, the notes are drawn).
bool command(const std::string& text);

// The drawing thread: the line, the box and the notes, drawn into the shown surface after the game's picture.
void overlay(render::FrameList& frame);

// For a host that draws its own box (Godot): take a report (returns its folder; shot_path is where the
// picture should go, "" for none), then finish it with the text (keep false: drop it).  finish returns the
// zip's path ("" when dropped or when it could not be written).
std::string begin(std::string& shot_path, bool want_shot = true, const std::string& host_lines = "");
std::string finish(const std::string& folder, const std::string& text, bool keep);
std::string last_note();                                // the last thing said to the player ("report saved: ..."), for a host's own label

}  // namespace testerkit
