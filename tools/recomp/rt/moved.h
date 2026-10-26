// moved.h - where a game address is while the tables sized for four are moved (party8.h).  The native modules
// that read or write the game's memory at fixed addresses (the player records, the pads, ...) pass the address
// through party8_at() first: the same address while nothing is moved (every game of one to four players, and every
// program whose translation has no relocations), the moved table's address otherwise.  Header only: a program
// without party8.cpp links and never moves anything.
#pragma once
#include <cstdint>

// set by party8.cpp while the tables are moved (null otherwise): the added words and the ranges, as the translation
// has them (g_reloc, g_reloc_spans of recomp.py --reloc)
inline const uint32_t* g_party8_delta = nullptr;
inline const uint32_t (*g_party8_spans)[2] = nullptr;

// one byte per 64 KB of the address space (main memory and its mirrors folded): 1 where an old place lies (rt/recomp.h
// RECOMP_RELOC_DYN looks here before it looks at the ranges)
inline uint8_t g_party8_page[0x2000] = {};

inline uint32_t party8_at(uint32_t address) {
    if (!g_party8_delta) return address;
    const uint32_t a = address & 0x1FFFFFFFu;
    for (int k = 0; k < 32; k++)
        if (a >= g_party8_spans[k][0] && a < g_party8_spans[k][1]) return address + g_party8_delta[k];
    return address;
}
