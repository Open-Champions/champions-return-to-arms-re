// soulscombat.h - an optional "souls-style" combat mode for the native build: stamina, a dodge
// with invulnerable ticks, light and heavy attacks (tap / hold), blocking that costs stamina
// instead of health, enemies that stagger when their poise breaks, and (in app/fpcontrols.h)
// a lock-on for the views that look along the ground.  docs/issues/native-souls-combat.md has
// the design, every number and what was run.
//
// THE RULE (the game is deterministic lockstep online).  Everything that changes the
// simulation is computed on every machine, in the tick, from what every machine has alike:
// the lockstep controller row of each player (g_pads, written by the game's own tick from
// the input record) and the game's own state.  Nothing here reads the local controller, the
// camera, the frame time or the renderer when it decides.  The mode is one switch for the
// whole game: offline it is this program's setting; online it is a room option that every
// copy must hold before the start (a copy that cannot do it, or does not want it, makes the
// room refuse to start: net2 room check), and it never changes during a game.
//
// How the simulation is reached: four functions of the game that it calls through a pointer
// (a virtual slot or a handler table) are given native wrappers in the runtime's table of
// translations (rt_replace_function).  The originals run inside them.  With the mode off
// nothing is replaced and the program is the program without this file.
//   Player_run 0x1a5030 (Player slot 4)          stamina, the tap / hold of attack, dodge, sprint
//   Player_takeDamage 0x1b5330 (Player slot 2)   invulnerable ticks, block cost, guard break
//   Creature_takeDamage 0x116638 (slot 2)        poise and stagger, the heavy attack's weight, criticals
//   Savepoint_run 0x28cdd0 (SavePoint slot 4)    the flasks refilled near a save point
//
// Inputs (the lockstep pad row of each player; nothing is added to the record):
//   attack (the slot's own attack button, the game's table 0x41b980)
//       tap  (released before HEAVY_HOLD ticks) = the game's own swing / combo step (light)
//       hold (HEAVY_HOLD ticks)                  = the game's own heavy attack (Player state 1 with
//                                                  request 2: its animation, its hyper-armour)
//   L3 (bit 0x200 of the row; the game's simulation does not read it: only its camera, which the
//       look views hold at rest)
//       tap  = dodge: the game's own "block move" (state 0xb, a back-hop of about 49 units in 45
//              ticks) toward the stick's direction, or straight back with the stick at rest
//       hold = sprint while moving
//   block (the slot's block button): the game's own block; a blocked hit costs stamina
//   block held + L3 pressed = parry (the L3 press is then neither a dodge nor a sprint)
//   attack pressed within the guard-counter window after a paid block = guard counter (the game's heavy attack at once)
//   potion A (the health potion button, the game's table 0x41ba10) = drink a flask; the game's health potions are not used
//
// State: a block of guest memory at SOULS_BASE (0xE0800, in the first megabyte, where the game
// has nothing: tools/recomp/soak uses 0xE0000-0xE004F) - the per-player numbers, written in the
// tick by every machine alike, readable by tick logs and by the Godot HUD (hud/souls.gd).
// The poise of creatures is kept in this file, keyed by the creature's object (object
// addresses are not the same on every machine; the entries are used only by the object they
// belong to and are never chosen between by address).
#pragma once
#include <cstdint>
#include <string>

struct Ctx;
namespace render { struct FrameList; }

namespace soulscombat {

// ---- the tuning: every number of the mode, in one place (docs/issues/native-souls-combat.md,
// table "Elden Ring reference -> our value").  Stamina is in hundredths of a point; ticks are
// the game's 60 a second.
struct Tuning {
    int32_t stamina_max = 10000;        // 100.0
    int32_t regen_per_tick = 75;        // 0.75 a tick = 45 a second
    int32_t regen_delay = 36;           // ticks after spending before it refills
    int32_t regen_block_percent = 35;   // refill while holding a block
    int32_t cost_light = 1300;          // a swing or a combo step
    int32_t cost_heavy = 2600;          // the heavy attack
    int32_t cost_ranged = 1000;         // a shot or a throw
    int32_t cost_dodge = 1500;
    int32_t cost_sprint_per_tick = 20;  // 12 a second
    int32_t cost_block_base = 800;      // a blocked hit: base + per_hp_percent x (damage / maximum hit points x 100)
    int32_t cost_block_per_hp_percent = 60;
    int32_t heavy_hold = 18;            // ticks the attack button is held for a heavy attack
    int32_t sprint_hold = 14;           // ticks L3 is held before it is a sprint (a shorter press is a dodge)
    int32_t dodge_iframe_first = 1;     // ticks of the dodge (state 0xb) in which no hit lands
    int32_t dodge_iframe_last = 24;
    int32_t dodge_cooldown = 0;         // ticks after a dodge has ended before the next (the hop is the recovery)
    int32_t dodge_stick_ignored = 47;   // the game's own (Player_tryBlockMove)
    int32_t guard_break_ticks = 60;     // no block after a broken guard
    int32_t sprint_speed_percent = 135; // the run speed while sprinting
    int32_t heavy_damage_percent = 130; // a heavy attack's damage against creatures
    int32_t poise_light = 100;          // poise damage of a light hit, a heavy one, a shot
    int32_t poise_heavy = 220;
    int32_t poise_ranged = 60;
    int32_t poise_normal = 300;         // what breaks a creature's poise, by its boss rank 0 / 1 / 2
    int32_t poise_miniboss = 800;
    int32_t poise_boss = 1100;
    int32_t poise_reset_ticks = 300;    // poise damage is forgotten after this long without a hit
    int32_t stagger_ticks = 50;         // the creature's stun (its own slot 30) when its poise breaks
    // ---- parry, criticals, guard counter, flasks, the death drop (2026-10-21; docs/issues/native-souls-combat.md 2.7) ----
    int32_t parry_first = 3;            // ticks after the parry press (block held + L3) in which a melee hit is parried
    int32_t parry_last = 18;
    int32_t parry_recovery = 45;        // up to this tick a missed parry leaves the guard open (hits are not blocked)
    int32_t cost_parry = 1000;
    int32_t parry_reach = 90;           // units between the two centres: farther is not a melee hit
    int32_t parry_stagger_ticks = 100;  // the parried attacker's stun (its own slot 30)
    int32_t riposte_window = 100;       // ticks the parried attacker is open to a riposte
    int32_t crit_riposte_percent = 400; // damage of a critical: a riposte, a stance-break critical, a backstab
    int32_t crit_stance_percent = 400;
    int32_t crit_backstab_percent = 300;
    int32_t crit_stun_ticks = 45;       // the creature's stun after a critical
    int32_t stance_crit_window = 90;    // ticks after a poise break in which a heavy hit is a critical (the stagger, and the recovery from it)
    int32_t backstab_half_angle = 40;   // degrees either side of straight behind the creature
    int32_t backstab_reach = 90;
    int32_t backstab_cooldown = 120;    // ticks before the same creature can be backstabbed again
    int32_t guard_counter_window = 36;  // ticks after a paid block in which an attack press is a guard counter
    int32_t guard_counter_damage_percent = 150;
    int32_t poise_guard_counter = 550;
    int32_t flask_count = 4;            // flasks: refilled at level entry, at a respawn and near a save point
    int32_t flask_heal_percent = 50;    // of the maximum hit points, delivered by the game's own potion healing
    int32_t flask_drink_ticks = 66;     // the drink's committed length
    int32_t flask_heal_tick = 36;       // the tick of the drink at which the flask is spent and the healing starts
    int32_t flask_heal_spread = 30;     // ticks the healing is delivered over
    int32_t flask_refill_radius = 120;  // units from a save point
    int32_t drop_percent = 50;          // of the carried gold, left where the player died
    int32_t drop_radius = 60;           // units from the spot that pick it up again
};
const Tuning& tuning();

// ---- the block in guest memory ----------------------------------------------------------
const uint32_t SOULS_BASE = 0xE0800;
const uint32_t SOULS_MAGIC = 0x4c554f53;        // "SOUL"
// header: +0 magic, +4 version (1), +8 mode (1 on), +0xc updates (real player ticks seen),
//         +0x10 poise breaks, +0x14 sum of the poise held (hundredths), +0x18 hits not landed (dodged), +0x1c blocks paid
// per player at +0x40 + slot x 0x40 (s32 each):
//   +0x00 stamina   +0x04 refill delay   +0x08 flags (FL_*)   +0x0c dodge tick (-1 none)
//   +0x10 dodge cooldown   +0x14 attack held (ticks)   +0x18 L3 held (ticks)   +0x1c guard broken (ticks left)
//   +0x20 last action state   +0x24 last combo step   +0x28 dodges   +0x2c heavy attacks
//   +0x30 light attacks   +0x34 refused (no stamina)   +0x38 hits not landed   +0x3c blocks paid
// header (version 2) +0x20 parries, +0x24 ripostes, +0x28 stance-break criticals, +0x2c backstabs, +0x30 guard counters,
//   +0x34 flask refills, +0x38 gold picked up again, +0x3c gold lost; +0x300 drops left, +0x304 drops picked up, +0x308 flasks drunk,
//   +0x30c + slot x 4 dead (1 from the death to the first tick alive again); +0x31c a test aid (0 outside tests): slot + 1 puts that player on its death drop in its next tick
// per player, kept over a death and a level change, at +0x200 + slot x 0x40 (s32 each):
//   +0x00 flasks left   +0x04 parry tick (-1 none)   +0x08 riposte window (ticks left)   +0x0c guard-counter window
//   +0x10 drink tick (-1 none)   +0x14 gold at the death spot   +0x18 x, +0x1c y, +0x20 z of the spot (f32)
//   +0x24 the spot's level (FNV-1a of the level name)   +0x28 gold to take at the respawn   +0x2c parries
//   +0x30 criticals   +0x34 guard counters   +0x38 flasks drunk   +0x3c gold picked up again
// local, per machine (presentation; not simulation): +0x180 lock on, +0x184 locked object,
//   +0x188 x, +0x18c y, +0x190 z, +0x194 hp, +0x198 hp max (f32), +0x19c this player's drop is on this level
enum : uint32_t { FL_DODGE = 1, FL_IFRAMES = 2, FL_SPRINT = 4, FL_BLOCK = 8, FL_HEAVY = 16, FL_BROKEN = 32, FL_EMPTY = 64,
                  FL_PARRY = 128, FL_RIPOSTE = 256, FL_COUNTER = 512, FL_DRINK = 1024, FL_COUNTER_HEAVY = 2048 };

// ---- from the application -----------------------------------------------------------------
// The setting ("combat.mode = souls|off", "--combat souls"): what this copy wants.  Offline it is what
// the game plays with; online the room decides (room_agreed).
void want(bool on);
bool wanted();
// The room's decision, for the game that is launched now (tools/recomp/net2/launch.cpp at the start):
// every copy of the room had the same mode.  `agreed` false: an online game this file knows nothing of
// (the old lobby): the mode stays off there.
void room_agreed(bool on);
// once per vertical blank on the game's thread (the controller read): puts the wrappers in place when the
// mode becomes active, keeps the local block (lock-on) and tells fpcontrols
void blank(uint64_t number);
bool active();                          // the mode is in force for the game that runs
// The overlay of the native picture: the stamina bar and the lock-on marker, added to the frame's draw list
// before the backend draws it (render thread).  `view_*`: the camera of the frame (fpview::View).
struct Camera { bool valid = false; float eye[3], forward[3], up[3], right[3], fov = 50; };
void set_camera(const Camera& camera);  // game thread, each draw pass
void overlay(render::FrameList& frame);
// "app souls ..." (script / control socket): info | on | off | lock | set NAME VALUE | figures
std::string command(const std::string& text);
bool setting(const char* key, const char* value);   // "combat.mode", "combat.<tuning name>"
std::string settings_text();
std::string figures();
std::string help_text();

}  // namespace soulscombat
