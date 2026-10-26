// partyscale.h - Hardcore mode's party scaling: how the enemies grow with the number of players, for parties of
// one to eight (docs/issues/native-8-players.md, part B, has the curve, the reasons and what was run).
//
// What the game does by itself (Creature_setStats 0x10a620, docs/data-tables.md 3.2): with n players (g_numPlayers
// 0x4d8ae0, n >= 2, word 0x4f713c clear) a creature's hit-point multiplier is x (1 + 0.6 (n - 1)) before the
// power 0.85 of the hit-point formula, its damage x (1 + 0.15 (n - 1)) (not for a boss, a droid or a creature
// without a type name), its experience x n.  Nothing else: no extra creatures, no tougher kinds.
//
// What this adds, with Hardcore mode on (soulscombat.h) and nothing at all with it off:
//   - the three multipliers taken from a table for n = 1..8 (the game's own values for 1..4, so that a Hardcore
//     room of up to four has the game's numbers), and a separate hit-point row for bosses;
//   - elites: a share of the ordinary creatures (rank 0) by party size gets more hit points, damage and
//     experience, and the mini-boss poise limit (chosen by a figure of the level, the creature's place and kind:
//     the same creature is an elite on every machine and at every visit);
//   - more creatures: for a share of the ordinary creatures of a level file, one (or two) more of the same kind is
//     made beside it when the level is loaded (not from a saved level state: the extra ones are never saved);
//   - the poise limit (Hardcore's stagger) grows with the party.
// The party size is the game's own player count; `combat.party.players` (1..8, 0 = the game's) makes a copy count
// another number - for tests now, and for the game of five to eight players the design describes.
//
// THE RULE of soulscombat.h holds: everything is decided from what every machine has alike (the player count, the
// level's name, the creature's kind and place, the game's shared generator through its own world_findFreeSpot);
// the numbers are folded into the Hardcore tuning figure, so a room whose copies differ refuses to start.
//
// Where the game is reached:
//   Creature_setStats 0x10a620   app/hle-app.txt hands it to partyscale_hle.cpp (the fix-set translation only);
//                                the original runs inside, with its multipliers changed and the player count it reads
//                                held at 1 while it runs when the table is not the game's
//   world_objectFactory 0x159c94 called through g_objectFactory: rt_replace_function; the original runs first, the
//                                extra creatures are made by the original too (only for calls from world_loadRecords
//                                0x14e808 loading a level file)
//
// State in guest memory at PARTY_BASE (first megabyte; every module's block is listed in guestmap.h), written in the
// simulation by every machine alike:
//   +0x00 magic "PRTY"  +0x04 version (1)  +0x08 on (1)  +0x0c the party size used last  +0x10 creatures scaled
//   +0x14 elites made  +0x18 extra creatures made  +0x1c extra creatures not made (the creature pool nearly full)
//   +0x20 bosses scaled  +0x24 the sum of the maximum hit points given (integer part)  +0x28 the last level's figure
//   +0x40..+0x5f scratch handed to the game (two positions and a flag)
#pragma once
#include <cstdint>
#include <string>

struct Ctx;
typedef void (*RecompFn)(Ctx*);

namespace partyscale {

// Every number in percent; index = party size - 1.
struct Tuning {
    int32_t on = 1;                     // 0: the game's own scaling in Hardcore too
    int32_t players = 0;                // 0: the game's player count; 1..8: count this many (tests; the 8-player game)
    int32_t hp[8] = {100, 160, 220, 280, 340, 400, 460, 530};          // hit-point multiplier (before the power 0.85)
    int32_t boss_hp[8] = {100, 160, 220, 280, 450, 600, 790, 990};     // the same for a boss (rank 2)
    int32_t damage[8] = {100, 115, 130, 145, 155, 165, 175, 185};      // not for a boss, a droid, a creature without a type name
    int32_t exp[8] = {100, 200, 300, 400, 500, 600, 700, 800};
    int32_t poise[8] = {100, 110, 120, 135, 150, 170, 190, 210};       // Hardcore's poise limit
    int32_t elite[8] = {2, 4, 7, 10, 13, 16, 20, 24};                  // chance an ordinary creature is an elite
    int32_t extra[8] = {0, 0, 0, 10, 35, 60, 80, 100};                 // chance of one more (above 100: of a second)
    int32_t elite_hp = 220;             // an elite's multipliers on top of the row's
    int32_t elite_damage = 125;
    int32_t elite_exp = 300;
    int32_t extra_range = 48;           // units around the creature where world_findFreeSpot looks for the extra one
    int32_t pool_keep = 96;             // creature blocks (the pool's 0x500 class) left free: no extra creature below that
};
const Tuning& tuning();

const uint32_t PARTY_BASE = 0xE2000;
const uint32_t PARTY_MAGIC = 0x59545250;       // "PRTY"

// partyscale_hle.cpp: the game's Creature_setStats with the original translation handed in
void set_stats(Ctx* c, RecompFn original);
bool elite(uint32_t creature);                  // made an elite by set_stats (the object of this machine)
int party();                                    // the party size the numbers are taken for (1..8)
std::string figures();

}  // namespace partyscale

// What soulscombat.cpp calls; null in a program without partyscale.cpp (then nothing of this happens).
namespace partyscale_hook {
inline void (*install)() = nullptr;                                          // soulscombat::install: the factory wrapper
inline void (*reset)() = nullptr;                                            // Hardcore switched on or off, a room's game begins or ends
inline int32_t (*poise_limit)(uint32_t creature, uint32_t rank, int32_t limit, int32_t miniboss_limit) = nullptr;
inline uint32_t (*figure)() = nullptr;                                       // folded into the Hardcore tuning figure
inline bool (*setting)(const char* key, const char* value) = nullptr;        // "combat.party.*"
inline std::string (*figures)() = nullptr;
}  // namespace partyscale_hook
