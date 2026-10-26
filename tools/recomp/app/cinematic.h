// cinematic.h - hold to skip a cut scene (Remastered): docs/issues/native-cutscenes.md.
//
// The game skips a cut scene when any player's controller row shows START pressed (cut_runFrame 0x199944,
// names.tsv: the loop over the players' rows at 0x199de4 sets g_cutSkip 0x44fcec on bit 0x800 of the pressed word).
// With this mode a skip needs START HELD for HOLD_TICKS game ticks by EVERY player of the game: alone that is a one
// second hold and the scene ends; in a room the scene ends at the tick in which the last of the players has held it
// for a second.  A tap no longer skips.
//
// THE RULE (deterministic lockstep, as soulscombat.h and fpaim.h).  The decision is made inside the tick, on every
// machine alike, from the lockstep controller rows of all players (g_pads 0x41bfd8, the held word +8) and the game's
// own player count (0x4d8ae0) - nothing local.  The game's own skip test stays the judge: around the original
// cut_runFrame the START bit of every pressed word is taken away, and put on player 1's row only in the tick in which
// every player has held long enough; the words are put back as they were afterwards (nothing else in the tick sees a
// difference).  The game's other conditions are its own and still hold: no skip test at all in the front end (g_inFrontend
// 0x41b510) or while the loading screen is up (0x506094); in a net game the two ending scenes "endgood" / "endbad" (the
// scene name at 0x44fe18, compared at 0x199da0 / 0x199db4) are not skipped before their 301st frame - every other scene
// may be skipped at once (Ran: bossevil's opening scene ended at its frame 62 in a room).  The counts are kept in guest memory
// (CINE_BASE), written in the tick: tick logs and the host's HUD read them.
//
// The mode is a room option like Hardcore and aiming: a copy that wants it says so with bit 0x2000 of its fix-set
// word count (the bit the portal uses for Remastered: a Remastered copy wants it, a Classic copy does not) and the
// mode's figure folded into its fix-set figure; a room whose copies differ is not launched (net2 launch.cpp).
// Offline it is this program's setting.  With the mode off the original runs untouched: the program is the
// program without this file.
//
// The game function is reached through the translation's HLE list (app/hle-app.txt names cut_runFrame: the
// translation of the fix-set build calls fn_00199944 for it, direct calls and calls through a pointer alike, and
// emits the original as orig_00199944).  cinematic_hle.cpp holds that one function and is linked only into the
// fix-set build (the original game's translation, rta_app_orig, has no such entry: it never skips by holding).
#pragma once
#include <cstdint>
#include <string>

struct Ctx;
typedef void (*RecompFn)(Ctx*);

namespace cinematic {

// ---- the block in guest memory (first megabyte, where the game has nothing: tools/recomp/soak 0xE0000-0xE004F,
// Hardcore 0xE0800-0xE147F (soulscombat.h BLOCK_SIZE), aiming 0xE1800 (fpaim.h)) ----
const uint32_t CINE_BASE = 0xE1C00;
const uint32_t CINE_MAGIC = 0x314e4943;     // "CIN1"
// header: +0x00 magic, +0x04 version (2), +0x08 mode (1 hold to skip), +0x0c scenes skipped, +0x10 ticks to hold,
// +0x14 players counted in the last tick, +0x18 the game frame counted last PLUS ONE (0: none yet in this scene),
// +0x1c taps held back (a press of START that the game would have taken as a skip), +0x20 + slot x 4: ticks START has
// been held by that player (-1: held through a skip the game took, counts again from a release).  Only the scene's
// own tick call (cut_runFrame(0)) counts; the load warm-up's cut_runFrame(1), whose number differs per machine, runs
// the original untouched, as do the front end's own scenes (g_inFrontend: per-machine clocks, never skipped by the
// game).  A completed hold whose skip the game refuses (an ending scene before frame 301 online) stays
// complete and the press is offered again each tick until the game takes it.
const uint32_t CINE_HOLD = 0x20;
const int HOLD_TICKS = 60;                  // one second of the game's 60 ticks

// ---- from the application ----
void want(bool on);                         // "cinematic.skip = hold | tap", "--cinematic hold"
bool wanted();
bool active();                              // in force for the game that runs
void blank(uint64_t number);                // once per vertical blank on the game's thread (as fpaim::blank)
bool setting(const char* key, const char* value);
std::string settings_text();
std::string figures();
std::string command(const std::string& text);   // "app cine info | on | off"

// cinematic_hle.cpp: the game's cut_runFrame with the original translation handed in
void run_frame(Ctx* c, RecompFn original);

}  // namespace cinematic
