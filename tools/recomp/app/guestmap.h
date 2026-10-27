// guestmap.h - every block the native modules keep in guest memory the game leaves alone (below its executable at
// 0x100000, above the runtime's kernel at 0x30000), in one list, checked at compile time not to overlap.  A module
// that adds or grows a block adds or changes its line here; partyscale.cpp checks the modules' own constants
// against this list (static_assert), so a header that moves its block without this file does not build.
//
// Sizes are for the layouts of today (four players).  The game of five to eight (docs/issues/native-8-players.md
// A.8) needs bigger per-player parts in the Hardcore, aiming and cut-scene blocks: they get new places here then,
// never a grown block in place (Hardcore's per-player parts at +0x40/+0x200/+0x400/+0x600 x slot are already back to
// back; aiming's slots at +0x40 + slot x 0x20 would reach its local bytes at +0x100 with eight).  Done for Hardcore
// (SOULS_HIGH) and aiming (AIM_HIGH); the cut-scene block has eight slots in place.
#pragma once
#include <cstdint>

namespace guestmap {

struct Block { uint32_t lo, hi; const char* what; };    // [lo, hi)

constexpr Block BLOCKS[] = {
    {0x30000, 0x74000, "party8.h: moved tables, lower area (g_savedPlayers and the small ones)"},
    {0x88000, 0xE0000, "party8.h: moved tables, upper area (each table with room for eight players)"},
    {0xE0000, 0xE0058, "tools/recomp/soak/soakhooks.cpp: pool figures and control"},
    {0xE0800, 0xE1480, "soulscombat.h: Hardcore mode (SOULS_BASE, BLOCK_SIZE 0xC80)"},
    {0xE1800, 0xE1940, "fpaim.h: aiming by looking (AIM_BASE)"},
    {0xE1A00, 0xE1A80, "fpaim.h: aiming by looking, players 5..8 of a game of five to eight (AIM_HIGH)"},
    {0xE1C00, 0xE1C40, "cinematic.h: hold to skip (CINE_BASE; +0x20 + slot x 4, eight slots)"},
    {0xE2000, 0xE2080, "partyscale.h: Hardcore's party scaling (PARTY_BASE)"},
    {0xE2100, 0xE2D80, "soulscombat.cpp: Hardcore's per-player parts of players 5..8 (SOULS_HIGH, the block's layout)"},
    {0xFF000, 0x100000, "tools/recomp/rt/iop.cpp: RPC packets (PACKETS)"},
};
constexpr int COUNT = (int)(sizeof BLOCKS / sizeof BLOCKS[0]);

constexpr bool disjoint() {
    for (int a = 0; a < COUNT; a++) {
        if (BLOCKS[a].lo >= BLOCKS[a].hi || BLOCKS[a].lo < 0x30000 || BLOCKS[a].hi > 0x100000) return false;
        for (int b = a + 1; b < COUNT; b++)
            if (BLOCKS[a].lo < BLOCKS[b].hi && BLOCKS[b].lo < BLOCKS[a].hi) return false;
    }
    return true;
}
static_assert(disjoint(), "two guest-memory blocks of the native modules overlap (guestmap.h)");

// the block that starts at `lo`, for the modules' own checks
constexpr Block at(uint32_t lo) {
    for (int k = 0; k < COUNT; k++) if (BLOCKS[k].lo == lo) return BLOCKS[k];
    return Block{0, 0, nullptr};
}

}  // namespace guestmap
