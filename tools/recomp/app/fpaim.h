// fpaim.h - aiming by looking, for the views that look along the ground (first person and over
// the shoulder, app/fpview.h, app/fpcontrols.h): an arrow, a thrown weapon or a spell bolt
// leaves along the line the player looks along - heading AND pitch - instead of the game's own
// automatic aim (the nearest enemy inside 10 degrees of the facing, with an automatic vertical
// part; level otherwise).  docs/issues/native-first-person-aim.md has what the game does, the
// design and what was run.
//
// THE RULE (the game is deterministic lockstep online).  What changes the simulation is
// computed in the tick on every machine from what every machine has alike:
//   - the heading: the yaw word of the player's input record (the game's own per-slot word,
//     net_getCamYaw 0x13e0c8; "0x3e3d - yaw word" is where a pushed-up stick walks and where the
//     first-person picture looks), and
//   - the pitch, and whether the player aims by looking at all: carried by GAME MESSAGE 4 (the
//     game's "null" channel, executed in lockstep by every machine in the tick of the frame it
//     travels with - the channel the strafe section of the fix set already uses, sub-type 2)
//     as sub-type 3 {3, slot, flags, pitch low, pitch high}; the handler stores it in a block
//     of guest memory (AIM_BASE).  Offline net_sendGameMsg runs the handler at once.
// Nothing here reads the local camera, controller or clock in the tick.  The sender (draw pass,
// app_main's fpview::on_drawn, where the strafe sender is called from) is the only part that
// reads this machine's view.
//
// How the simulation is reached (rt_replace_function; nothing is replaced while the mode is off,
// and the program is then the program without this file):
//   Player_run 0x1a5030 (Player slot 4)   after the original: the projectiles the player has just
//                                         launched (new at the front of the every-frame run list,
//                                         owned by the player, of a known class) are turned onto
//                                         the look, keeping their speed
//   0x1e01b0 (message 4's handler)        sub-type 3 is the aim; anything else goes to the
//                                         original (the shipped empty function, or the fix set's
//                                         strafe handler behind it)
//
// One switch for the whole game, like the souls-style combat mode: offline this program's
// setting ("combat.aim = look"), online a room option every copy must have (net2 room check,
// fix_words bit 0x4000), never changed during a game; through the old lobby it is off.
#pragma once
#include <cstdint>
#include <string>

struct Ctx;

namespace fpaim {

// ---- the block in guest memory (first megabyte: tools/recomp/soak 0xE0000-0xE004F, Hardcore mode
// 0xE0800-0xE147F: soulscombat.h BLOCK_SIZE; aiming 0xE1800-0xE193F and 0xE1A00-0xE1A7F (players 5..8); cutscenes 0xE1C00: cinematic.h; party scaling 0xE2000: partyscale.h) ----
const uint32_t AIM_BASE = 0xE1800;
const uint32_t AIM_MAGIC = 0x314d4941;      // "AIM1"
// header: +0 magic, +4 version (1), +8 mode (1 on), +0xc aim messages applied, +0x10 projectiles aimed
// per player at +0x40 + slot x 0x20 (s32 each; written in the tick by every machine alike):
//   +0x00 aims (1: this player's projectiles go where it looks)   +0x04 pitch (16-bit angle units, up positive)
//   +0x08 messages applied   +0x0c projectiles aimed   +0x10 heading of the last one (16-bit units)
//   +0x14 its pitch          +0x18 its class (index of CLASSES + 1)   +0x1c its speed (f32)
// local (per machine; not simulation): +0x100 the bytes of the message being sent
const uint32_t AIM_SLOT = 0x40, AIM_SLOT_SIZE = 0x20;
// players 5..8 of a game of five to eight (docs/issues/native-8-players.md): the same per-player parts in a second
// block (guestmap.h), slot - 4 x 0x20 from AIM_HIGH; never touched in a game of one to four
const uint32_t AIM_HIGH = 0xE1A00, AIM_HIGH_SIZE = 4 * AIM_SLOT_SIZE;

// ---- from the application ----
void want(bool on);                     // "combat.aim = look | off", "--aim look"
bool wanted();
bool active();                          // in force for the game that runs
// once per vertical blank on the game's thread (after fpcontrols::translate): the mode, the wrappers
void blank(uint64_t number);
// the draw pass (app_main's fpview::on_drawn, the game's thread with its context): sends this machine's aim
// when it has changed.  `view` as fpcontrols numbers it, `steering`: that view has the frame and the
// controls steer; `pitch`: the look's pitch, degrees up.
void drawn(Ctx* c, int view, bool steering, float pitch);
bool setting(const char* key, const char* value);   // "combat.aim"
std::string settings_text();
std::string figures();
std::string command(const std::string& text);       // "app aim info | on | off"

}  // namespace fpaim
