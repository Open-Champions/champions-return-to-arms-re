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
//   L3 held + attack pressed = the weapon art (the attack press and the L3 press are then spent)
//   L3 held + swap (the other weapon set) pressed = two-handing on / off (the swap is not given to the game)
//   L3 held + use pressed near a save point = upgrade the weapon in hand by one level (the use is not given to the game)
//   L3 held + potion B (L2) pressed near a save point = the character screen: up / down choose a row, right spends a point
//       (Mind, Endurance, Faith) or puts the chosen spell into a slot, left takes it out; block, or L3 + L2 again, closes it.
//       While it is open the character stands and no other button reaches the game.
//   ability A / B (the game's own skill buttons): a spell that is not attuned (in one of the spell slots) is not cast
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
    // ---- weapons (2026-10-21, third round; docs/issues/native-souls-combat.md 2.8 and 3.3) ----
    // equip load: the weight of what is equipped (the game's own item_getWeight of each equipped item) against a
    // capacity from the character's statistics, in hundredths: base + per_stamina x stamina + per_strength x strength
    int32_t load_base = 2000;
    int32_t load_per_endurance = 100;   // (the weapons round had the game's stamina here; Endurance since the stats round)
    int32_t load_per_strength = 25;
    int32_t load_light = 30;            // percent of the capacity: below it light, below load_medium medium,
    int32_t load_medium = 70;           // up to 100 heavy, above 100 overloaded
    // by tier (light, medium, heavy, overloaded), percent: the dodge's movement, its invulnerable ticks, the stamina
    // refill, the sprint's extra speed (0: no dodge / no sprint)
    int32_t tier_dodge_move[4] = {115, 100, 75, 0};
    int32_t tier_iframes[4] = {100, 100, 75, 0};
    int32_t tier_regen[4] = {110, 100, 85, 60};
    int32_t tier_sprint[4] = {100, 100, 70, 0};
    // by weapon class (WC_*: none, dagger, sword, axe, mace, great, spear, staff, bow)
    int32_t wc_stamina[9] = {100, 75, 100, 110, 100, 135, 120, 100, 100};   // percent of cost_light / cost_heavy / cost_ranged
    int32_t wc_poise[9] = {70, 70, 100, 100, 150, 260, 200, 70, 100};       // percent of poise_light / heavy / ranged
    int32_t wc_recovery[9] = {0, 0, 4, 8, 10, 16, 6, 8, 0};                // ticks after a swing before the next swing starts
    int32_t wc_cancel[9] = {18, 16, 20, 24, 26, -1, 22, 24, -1};           // ticks into a swing from which a dodge cancels it (-1 never)
    int32_t wc_str[9] = {0, 30, 35, 44, 50, 48, 36, 12, 19};               // scaling coefficients (the grade letters come from them)
    int32_t wc_dex[9] = {0, 50, 32, 33, 33, 30, 41, 0, 26};
    int32_t wc_int[9] = {0, 0, 0, 0, 0, 0, 0, 90, 0};
    int32_t wc_guard[9] = {300, 300, 175, 165, 175, 120, 145, 300, 300};    // block cost (percent) guarding with the weapon (two-handed or no shield)
    int32_t wc_crit[9] = {100, 110, 100, 100, 100, 100, 100, 100, 100};     // percent on a riposte and a backstab
    int32_t wc_art[9] = {0, 1, 2, 2, 3, 3, 1, 4, 4};                       // the weapon art (ART_*): lunge, spin, slam, bolt
    // stat scaling: the bonus in percent of the hit's damage = sum over strength, dexterity, intelligence of
    // coefficient x (100 + upgrade_correct_percent x level) / 100 x curve(stat) / 100; the curve is linear between
    // these points (statistic -> percent)
    int32_t scale_stat[7] = {0, 20, 40, 80, 120, 160, 200};
    int32_t scale_value[7] = {0, 12, 28, 54, 75, 90, 95};
    int32_t twohand_strength_percent = 150;
    int32_t twohand_poise_percent = 125;
    int32_t heavy_interrupt_hp_percent = 6;  // a heavy without hyper-armour (not a great weapon) is staggered by a hit of this share of the bar
    int32_t spear_chip_percent = 20;         // of a blocked spear hit that still lands (a player's spear against a blocking player)
    // upgrades +1..+10: damage, scaling, cost (gold and the upgrade material)
    int32_t upgrade_max = 10;
    int32_t upgrade_damage_tenths = 145;     // +14.5 % of the damage per level
    int32_t upgrade_correct_percent = 8;     // the scaling coefficients +8 % per level
    int32_t upgrade_gold_base = 300;         // gold for level n: base x (100 + step x (n - 1)) / 100
    int32_t upgrade_gold_step = 50;
    int32_t upgrade_material_every = 3;      // materials for level n: 1 + (n - 1) / every
    int32_t material_drop_normal = 8;        // percent, by the creature's boss rank, decided by the game's shared generator state
    int32_t material_drop_miniboss = 50;
    int32_t material_drop_boss = 100;
    int32_t save_reach = 120;                // units from a save point at which the upgrade can be made
    // weapon arts (the game's own skills cast at the level 1 + upgrade)
    int32_t art_mana_percent = 20;           // of the maximum mana
    int32_t art_stamina_percent = 100;       // of cost_heavy
    int32_t art_cooldown = 60;
    int32_t art_slam_percent = 160;          // a slam's shove: this share of the weapon's top damage
    int32_t art_fixed_percent = 30;          // the lunge's and the bolt's own fixed damage (the skills') is scaled by this
    int32_t art_bolt_ticks = 90;             // how long after a bolt its projectile's hits count as the art's
    // ---- attributes and the spellbook (2026-10-25, fourth round; docs/issues/native-souls-combat.md 2.9 and 3.4) ----
    // Vigor, Strength, Dexterity and Intelligence are the game's own statistics (stamina, strength, dexterity,
    // intelligence: the game's level-up screen spends its own points on them); Mind, Endurance and Faith are the mode's,
    // kept with the character (soulscombat.h, the save spot).  By class (barbarian, cleric, shadow knight, ranger,
    // wizard, berserker, shaman): where the mode's three start; every level gained gives points_per_level of the mode's
    // points, spent on them at a save point (the mode's character screen).
    int32_t points_per_level = 2;
    int32_t start_mind[7] = {20, 36, 28, 26, 44, 20, 38};
    int32_t start_endurance[7] = {40, 30, 36, 34, 24, 42, 28};
    int32_t start_faith[7] = {20, 44, 34, 24, 20, 22, 40};
    int32_t stat_max = 198;                  // the ceiling of Mind, Endurance and Faith (our scale: 2 x the reference's 99)
    int32_t mana_per_mind_permille = 25;     // the maximum mana: the game's own + this many thousandths of it per Mind point spent
    int32_t stamina_per_endurance = 90;      // the stamina bar: stamina_max + this (hundredths) per Endurance point spent
    // spell slots = slot_base + Mind / slot_per_mind + Intelligence / slot_per_int, 1 .. slot_max (at most 9)
    int32_t slot_base = 1;
    int32_t slot_per_mind = 16;
    int32_t slot_per_int = 40;
    int32_t slot_max = 9;
    // spell scaling by class: the bonus in percent of a spell's damage = (sc_int x curve(Intelligence) + sc_faith x
    // curve(Faith)) / 100 (the weapons' curve); grade letters as the weapons'
    int32_t sc_int[7] = {0, 0, 45, 25, 90, 0, 30};
    int32_t sc_faith[7] = {20, 80, 40, 25, 0, 20, 60};
    int32_t spell_hit_ticks = 240;           // how long after a cast the caster's hits (not swings, not weapon arts) count as the spell's
};
enum : int32_t { WC_NONE = 0, WC_DAGGER, WC_SWORD, WC_AXE, WC_MACE, WC_GREAT, WC_SPEAR, WC_STAFF, WC_BOW, WC_COUNT };
enum : int32_t { ART_NONE = 0, ART_LUNGE, ART_SPIN, ART_SLAM, ART_BOLT };
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
// header (version 3, the weapons) +0x320 weapon arts, +0x324 upgrades, +0x328 materials dropped, +0x32c two-hand toggles,
//   +0x330 spear chips, +0x334 heavies interrupted, +0x338 swings cancelled by a dodge, +0x33c a test aid (slot + 1 | count << 8:
//   that player is given `count` upgrade materials in its next tick); +0x340..+0x37f scratch the game is handed (a position,
//   a clip name); +0x380 the level's save points (count, then x, y, z each, at most 8), +0x3fc their level; +0x5a0..+0x5e7 an
//   item record handed to the game (the test aid)
// per player, weapons, at +0x400 + slot x 0x60 (s32 each):
//   +0x00 weapon class (WC_*)   +0x04 equip load   +0x08 capacity (hundredths)   +0x0c tier (0 light .. 3 overloaded)
//   +0x10 upgrade of the weapon in hand   +0x14 grades (letters: strength, dexterity, intelligence in bytes 0..2)
//   +0x18 scaling bonus (percent)   +0x1c two-handed   +0x20 weapon-art tick (-1 none)   +0x24 its kind (ART_*)
//   +0x28 upgrade materials carried   +0x2c near a save point (1)   +0x30 arts   +0x34 upgrades made
//   +0x38 recovery ticks left   +0x3c ticks into the swing (-1 none)   +0x40 art cooldown   +0x44 buffered swing
//   +0x48 damage percent (100 + upgrade + scaling)   +0x4c gold for the next level   +0x50 materials for it   +0x54 refused upgrades
// upgrades are kept on the weapon's own item record, in bytes the game never writes nor reads (+0x06, +0x44): the record
// is on the memory card with the character and goes to every machine at a net game's launch
// local, per machine (presentation; not simulation): +0x180 lock on, +0x184 locked object,
//   +0x188 x, +0x18c y, +0x190 z, +0x194 hp, +0x198 hp max (f32), +0x19c this player's drop is on this level,
//   +0x1a0 the name of this player's weapon (32 bytes), +0x1c0 the character sheet asked for on this machine (1),
//   +0x1d0 this player's hit points, +0x1d4 their maximum, +0x1d8 its mana, +0x1dc the maximum mana (f32), +0x1e0 u8[15] the
//   ability records of its spellbook in order (the open screen's rows after the three attributes; 0xff none), +0xb00 u8[24][15] the names of its
//   ability records (0 none)
// header +0x580 a test aid (slot + 1: that player is put beside the nearest living creature, facing it, in its next tick)
// header (version 4, the attributes and the spellbook) +0x5e8 a test aid (slot + 1 | amount << 8: that player is given
//   `amount` experience by the game's own player_giveExp in its next tick), +0x5ec mode points spent, +0x5f0 attunement
//   changes, +0x5f4 spells cast, +0x5f8 spell hits scaled, +0x5fc casts refused (not attuned)
// per player, attributes and spellbook, at +0x600 + slot x 0x80 (s32 each):
//   +0x00 Vigor  +0x04 Mind  +0x08 Endurance  +0x0c Strength  +0x10 Dexterity  +0x14 Intelligence  +0x18 Faith
//   +0x1c mode points unspent  +0x20 spent  +0x24 the character screen open (1)  +0x28 its selected row  +0x2c spell slots
//   +0x30 spells (bit k: ability record k is in the spellbook)  +0x34 attuned (bit k: castable)  +0x38 stamina maximum
//   +0x3c the game's own maximum mana (f32)  +0x40 the maximum written (f32)  +0x44 the mana at the end of the last tick (f32)
//   +0x48 spell damage percent  +0x4c spell grades (Intelligence, Faith letters in bytes 0, 1)  +0x50 spell window (ticks since
//   the cast, -1 none)  +0x54 casts  +0x58 casts refused  +0x5c points spent  +0x60 attunement changes  +0x64 the save spot
//   was found (1)  +0x68 the level  +0x6c screens opened  +0x70 the class (0-6)  +0x74 spell slots in use
// per player at +0xa00 + slot x 0x40: u16[15] the mana cost of each ability record (tenths), u8[15] at +0x20 its rank
// Mind, Endurance, Faith and the attuned spells are kept with the character, in the last 6 bytes of the player record, which
// the game never reads or writes (+0x4c2a..+0x4c2f, after the marker byte +0x4c29: tools/fieldxref.py finds no access; a
// level change, a death and the reload keep them - docs/issues/native-souls-combat.md 2.9): 48 bits, low first: Mind,
// Endurance, Faith (7 bits each, the points spent), the attuned ability records (15 bits), the tag 0xa (4 bits), a check
// (8 bits, FNV-1a of the 40 below).  Anything else there is "nothing spent, the default slots".
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
// The class (WC_*) of the weapon player `slot` holds, by the mode's own rules (the definition row's animation class, damage
// kind, weight and name), and the item record (guest address, 0 none).  Reads memory only; whether or not the mode is on.
int32_t weapon_class_in_hand(int slot, uint32_t* item = nullptr);
// The overlay of the native picture: the stamina bar and the lock-on marker, added to the frame's draw list
// before the backend draws it (render thread).  `view_*`: the camera of the frame (fpview::View).
struct Camera { bool valid = false; float eye[3], forward[3], up[3], right[3], fov = 50; };
void set_camera(const Camera& camera);  // game thread, each draw pass
void overlay(render::FrameList& frame);
// The attributes of player `slot` as the mode has them (Vigor, Mind, Endurance, Strength, Dexterity, Intelligence, Faith),
// whether or not the mode is on; false without a character.
bool attributes(int slot, int32_t out[7]);
// "app souls ..." (script / control socket): info | on | off | lock | set NAME VALUE | figures | stats | sheet
std::string command(const std::string& text);
bool setting(const char* key, const char* value);   // "combat.mode", "combat.<tuning name>"
std::string settings_text();
std::string figures();
std::string help_text();

}  // namespace soulscombat
