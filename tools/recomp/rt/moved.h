// moved.h - where a game address is while the tables sized for four are moved (party8.h).  The native modules
// that read or write the game's memory at fixed addresses (the player records, the pads, ...) pass the address
// through party8_at() first: the same address while nothing is moved (every game of one to four players, and every
// program whose translation has no relocations), the moved table's address otherwise.  Header only: a program
// without party8.cpp links and never moves anything.
#pragma once
#include <cstdint>
#include "ramsize.h"

// set by party8.cpp while the tables are moved (null otherwise): the added words and the ranges, as the translation
// has them (g_reloc, g_reloc_spans of recomp.py --reloc)
constexpr int PARTY8_TABLES = 96;       // the slots of g_reloc (recomp.py --reloc, reloc.py TABLES)
inline const uint32_t* g_party8_delta = nullptr;
inline const uint32_t (*g_party8_spans)[2] = nullptr;

// one byte per 64 KB of the address space (main memory and its mirrors folded): 1 where an old place lies (rt/recomp.h
// RECOMP_RELOC_DYN looks here before it looks at the ranges)
inline uint8_t g_party8_page[0x2000] = {};

// a test aid of the check build (RECOMP_RELOC_CHECK): every load and store of the translated code in [lo, hi) is
// reported with its function as well (party8.cpp: PARTY8_WATCH=address:length)
inline uint32_t g_party8_watch_lo = 0, g_party8_watch_hi = 0;
// ... and, with PARTY8_HEAPWATCH=1, every access to a heap block's header (the list party8.cpp keeps of them) from code
// outside the allocator
inline bool g_party8_heapwatch = false;

inline uint32_t party8_at(uint32_t address) {
    if (!g_party8_delta) return address;
    const uint32_t a = address & 0x1FFFFFFFu;
    for (int k = 0; k < PARTY8_TABLES; k++)
        if (a >= g_party8_spans[k][0] && a < g_party8_spans[k][1]) return address + g_party8_delta[k];
    return address;
}

// ---- a game of five to eight (docs/issues/native-8-players.md A.3, C) --------------------------------------------
// The top of memory the game is told of (GetMemorySize, the main thread's stack, and the game's own heap size at
// 0x19d59c - site `memtop` of app/party8-sites.txt): 32 MB, as on the console.  A copy started for rooms of five to
// eight (--opt party8=8) in a program built with more memory (RAM_SIZE 64 MB: app/build.py --party8) is told all of it:
// eight players' models and equipment caches do not fit the game's 23 MB heap (Ran: out of memory at the sixth player).
// Its main thread's stack then goes to the new top as well.  (party8=1 moves the tables only and keeps 32 MB: a room of
// one to four is then the same game, value for value - Ran; the bigger heap is not: other addresses, other choices.)
inline uint32_t g_party8_memtop = 0x02000000u;
// Set by party8.cpp at the launch of a room of five to eight (the tables moved, g_party8_slots 8); 0 in every other
// game, and then nothing below changes a byte.
inline uint32_t g_party8_wide = 0;

// The input packet's byte 8 carries the sender's slot (low nibble) and its active mask (high nibble): four bits of
// mask.  In a game of five to eight the sender's network layer appends a trailer word 0xB8000000 | mask (eight bits)
// to every input packet (0xbd3f) and raw relay (0xbd42); the receiving layer takes it off again and leaves the mask
// here, where the translation's site 0x13b694 (net_receivePackets: `sra $10, $10, 4`, app/party8-sites.txt) reads
// it in place of the nibble.  net_main hands each datagram to net_receivePackets right after sceInetRecvFrom, so
// the word always belongs to the packet being read.  0x100 (no mask matches): a packet without the trailer.
inline uint32_t g_party8_rx_mask = 0x100;
constexpr uint32_t PARTY8_TRAILER = 0xB8000000u;

// the sender's active mask as net_sendInputPacket 0x137d60 computes it (0x137de4-0x137e18): bit k for every peer
// k < g_numPeers whose word at +0x44d4 has its three upper bytes clear (not dropped, not being kicked, not out of step)
inline uint32_t party8_active_mask(const uint8_t* ram) {
    uint32_t peers = 0, mask = 0;
    __builtin_memcpy(&peers, ram + 0x4027c4, 4);                          // g_numPeers
    const uint32_t base = party8_at(0x5bf838) & 0x1FFFFFFFu;              // g_peers, wherever it is
    for (uint32_t k = 0; k < peers && k < 8; k++) {
        uint32_t w;
        __builtin_memcpy(&w, ram + base + k * 0x44e0 + 0x44d4, 4);
        if ((w & 0xFFFFFF00u) == 0) mask |= 1u << k;
    }
    return mask;
}
