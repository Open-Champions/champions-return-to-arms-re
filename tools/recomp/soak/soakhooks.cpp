// soakhooks.cpp - what the soak farm adds to the native lockstep build
// (tools/recomp/soak/build_soak.py; docs/issues/native-soak.md).
//
// 1. After every lockstep tick, before the shim writes the tick log's row, checksums of
//    the object pool are put into a block of main memory the game does not use
//    (0xE0000, in the kernel's megabyte), where tick-log columns can read them:
//
//      0xE0000 u32  "pool"     the sum over live objects of a hash of: virtual table,
//                              position, facing, the object's own random state
//      0xE0004 u32  "poolraw"  the sum over live objects of a hash of every word of the
//                              block, less the words of the mask (below); a word that is
//                              an address counts as what it points at, not as a number
//      0xE0008 u32  live objects (the prediction copy not counted)
//      0xE000C u32  "poolfree" the three free lists in order (where the next object goes)
//      0xE0010 u32 x 3  live objects per block class (0x180, 0x500, 3000 bytes)
//
//    The pool is g_poolClasses 0x403a10 ({block size, count, base, free head} x 3); a free
//    block is one on a free list (link in its first word).  The prediction copy of this
//    machine's own player (g_ghost 0x4027bc) is left out: it is per machine by design.
//    Both sums are independent of the order and the addresses of the objects.
//
//    The mask: words that differ between two machines in step by design.  Built in: the
//    three handle heads (+0x00, +0x04, +0x08) of every object and, in a Player, the flag
//    bits 0x200000 and 0x100 (set on the real local player and on the copy:
//    docs/netcode.md).  SOAK_MASK=<file> adds lines
//      <virtual table, hex, or *> <offset, hex> [<bits to ignore, hex>]
//      <virtual table> nohard      the class is left out of "pool" (its position or random
//                                  state is presentation)
//      <virtual table> skip        the class is left out of both
//    SOAK_MACHINES=2: the run ends 60 ticks after one machine holds the other dropped.
//    SOAK_RAW_EVERY=N: "poolraw" is computed in ticks divisible by N only (it is the costly one).
//
// 2. --instrument count: g_soak_calls, one counter per call target, written at the end of
//    the run to SOAK_CALLS=<file> as "address count" lines.
// 3. --instrument trace: SOAK_WATCH=<address>:<length>[,...] (hex), SOAK_WATCH_TICKS=<lo>:<hi>,
//    SOAK_WATCH_LOG=<file>: at every call and return the watched bytes are compared with a
//    shadow; a change is logged with the tick, the old and new bytes and the chain of
//    functions that were running (innermost first).  The writer is the innermost function,
//    or the runtime if the store was a service's.
#include "recomp.h"
#include "funcs.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <unordered_map>
#include <vector>

extern void (*rt_at_finish)();
[[noreturn]] void rt_finish(int code);

namespace {

enum : u32 { POOL_TABLE = 0x403a10, G_GHOST = 0x4027bc, G_NETFRAME = 0x4027ac, SCRATCH = 0xE0000, TICK_RETURN = 0x13aee8,
             VT_PLAYER = 0x511308, VT_LO = 0x500000u, VT_HI = 0x520000u, POOL_BASE = 0x5f88c0, POOL_END = 0x6dffc0,
             G_PEERS = 0x5bf838, PEER_SIZE = 0x44e0, PEER_DROPPED = 0x44d5 };

u32 rd(u32 a) { u32 v = 0; a &= 0x1FFFFFFFu; if (a <= RAM_SIZE - 4) memcpy(&v, g_ram + a, 4); return v; }
void wr(u32 a, u32 v) { memcpy(g_ram + a, &v, 4); }
inline u64 mix(u64 h, u64 v) { h ^= v; h *= 0x9E3779B97F4A7C15ull; return h ^ (h >> 29); }

struct MaskLine { u32 vtable, offset, bits; };
std::vector<MaskLine> g_mask;
std::unordered_map<u32, int> g_class_rule;          // virtual table -> 1 "nohard", 2 "skip"
std::unordered_map<u64, std::vector<u32>> g_keep;   // (virtual table, block size) -> bits kept per word
bool g_started = false;
int g_raw_every = 1;      // SOAK_RAW_EVERY=N: "poolraw" is computed in ticks divisible by N only
void (*g_prev_finish)() = nullptr;

void at_finish();
void start() {
    if (g_started) return;
    g_started = true;
    g_mask = {{0, 0x0, ~0u}, {0, 0x4, ~0u}, {0, 0x8, ~0u}, {VT_PLAYER, 0xc, 0x200100u}};
    if (const char* path = getenv("SOAK_MASK")) {
        FILE* f = fopen(path, "r");
        if (!f) { fprintf(stderr, "soak: cannot read %s\n", path); _Exit(2); }
        char line[256];
        while (fgets(line, sizeof(line), f)) {
            char who[64], what[64];
            unsigned bits = ~0u;
            if (line[0] == '#') continue;
            int n = sscanf(line, "%63s %63s %x", who, what, &bits);
            if (n < 2) continue;
            u32 vtable = strcmp(who, "*") == 0 ? 0 : (u32)strtoul(who, nullptr, 16);
            if (strcmp(what, "nohard") == 0) g_class_rule[vtable] |= 1;
            else if (strcmp(what, "skip") == 0) g_class_rule[vtable] |= 2;
            else g_mask.push_back({vtable, (u32)strtoul(what, nullptr, 16), n >= 3 ? bits : ~0u});
        }
        fclose(f);
    }
    if (const char* every = getenv("SOAK_RAW_EVERY")) g_raw_every = atoi(every);
    for (u32 a = SCRATCH; a < SCRATCH + 0x40; a += 4)
        if (rd(a)) { fprintf(stderr, "soak: the scratch block at 0x%x is in use\n", SCRATCH); _Exit(2); }
    g_prev_finish = rt_at_finish;
    rt_at_finish = at_finish;
}

struct PoolClass { u32 size, count, base; };

// A word that is an address is not compared as a number: an address in the heap (pose
// buffers, handle nodes, lists - their placement differs between machines in step) counts
// as "a heap address"; an address in the object pool counts as the class of the object it
// points into and the offset inside it.
inline u32 canon(u32 v, const PoolClass* classes) {
    if (v < POOL_BASE || v >= RAM_SIZE) return v;
    if (v >= POOL_END) return 0xA0000002u;
    for (int k = 0; k < 3; k++) {
        const PoolClass& c = classes[k];
        if (c.size && v >= c.base && v < c.base + c.size * c.count) {
            u32 block = c.base + (v - c.base) / c.size * c.size;
            return 0xB0000000u ^ (rd(block + 0x48) * 31u) ^ (v - block);
        }
    }
    return 0xA0000001u;
}

void pool_checksums() {
    static u8 is_free[2048];
    bool want_raw = g_raw_every <= 1 || rd(G_NETFRAME) % (u32)g_raw_every == 0;
    u64 hard = 0, raw = 0, order = 0xA4093822299F31D0ull;
    u32 live = 0, per_class[3] = {};
    u32 ghost = rd(G_GHOST) & 0x1FFFFFFFu;
    PoolClass classes[3] = {};
    for (int k = 0; k < 3; k++) {
        u32 size = rd(POOL_TABLE + k * 16), count = rd(POOL_TABLE + k * 16 + 4), base = rd(POOL_TABLE + k * 16 + 8) & 0x1FFFFFFFu;
        if (size < 0x4c || size > 0x4000 || count == 0 || count > sizeof(is_free) || (u64)base + (u64)size * count > RAM_SIZE) continue;
        classes[k] = {size, count, base};
    }
    for (int k = 0; k < 3; k++) {
        u32 size = classes[k].size, count = classes[k].count, base = classes[k].base;
        if (!size) continue;
        memset(is_free, 0, count);
        u32 p = rd(POOL_TABLE + k * 16 + 12) & 0x1FFFFFFFu;
        for (u32 n = 0; p >= base && p < base + size * count && n < count; n++) {
            is_free[(p - base) / size] = 1;
            order = mix(order, p);
            p = rd(p) & 0x1FFFFFFFu;
        }
        order = mix(order, 0xFFFFFFFFull);
        u32 words = size / 4;
        for (u32 i = 0; i < count; i++) {
            u32 block = base + i * size;
            if (is_free[i] || block == ghost) continue;
            live++;
            per_class[k]++;
            u32 vtable = rd(block + 0x48);
            int rule = 0;
            if (!g_class_rule.empty()) { auto found = g_class_rule.find(vtable); if (found != g_class_rule.end()) rule = found->second; }
            // a block whose word at +0x48 is not a virtual table is not a game object (the pool
            // also serves a few small records): left out of both sums
            if ((rule & 2) || vtable < VT_LO || vtable >= VT_HI) continue;
            std::vector<u32>& keep = g_keep[((u64)vtable << 16) | size];
            if (keep.empty()) {
                keep.assign(words, ~0u);
                for (const MaskLine& m : g_mask)
                    if ((m.vtable == 0 || m.vtable == vtable) && m.offset / 4 < words) keep[m.offset / 4] &= ~m.bits;
            }
            if (!(rule & 1)) {
                u64 h = mix(0x243F6A8885A308D3ull, vtable);
                h = mix(h, ((u64)(rd(block + 0x10) & keep[4]) << 32) | (rd(block + 0x14) & keep[5]));
                h = mix(h, ((u64)(rd(block + 0x18) & keep[6]) << 32) | (rd(block + 0x38) & keep[14] & 0xFFFFu));
                hard += mix(h, rd(block + 0x44) & keep[17]);
            }
            if (!want_raw) continue;
            u64 h = mix(0x13198A2E03707344ull, vtable);
            const u8* at = g_ram + block;
            for (u32 w = 0; w < words; w++) {
                u32 v;
                memcpy(&v, at + w * 4, 4);
                if (keep[w] == 0) continue;
                // the flag word (+0x0c) is a bit set and can look like an address: taken as it is
                h = mix(h, (w == 3 ? v : canon(v, classes)) & keep[w]);
            }
            raw += h;
        }
    }
    wr(SCRATCH, (u32)(hard ^ (hard >> 32)));
    if (want_raw) wr(SCRATCH + 4, (u32)(raw ^ (raw >> 32)));
    wr(SCRATCH + 8, live);
    wr(SCRATCH + 12, (u32)(order ^ (order >> 32)));
    wr(SCRATCH + 16, per_class[0]);
    wr(SCRATCH + 20, per_class[1]);
    wr(SCRATCH + 24, per_class[2]);
}

}  // namespace

#ifdef SOAK_INSTRUMENT_COUNT
u32 g_soak_calls[1u << 20];
#endif

#ifdef SOAK_INSTRUMENT_TRACE
namespace {
struct Range { u32 lo, length; std::vector<u8> shadow; };
std::vector<Range> g_ranges;
u32 g_tick_lo = 0, g_tick_hi = 0xFFFFFFFFu;
FILE* g_watch_log = nullptr;
bool g_watch_ready = false, g_watch_armed = false;
thread_local u32 t_stack[1024];
thread_local unsigned t_sp = 0;

void watch_setup() {
    g_watch_ready = true;
    const char* spec = getenv("SOAK_WATCH");
    if (!spec) return;
    std::string text = spec;
    size_t at = 0;
    while (at < text.size()) {
        size_t comma = text.find(',', at);
        std::string part = text.substr(at, comma == std::string::npos ? std::string::npos : comma - at);
        unsigned lo = 0, length = 4;
        if (sscanf(part.c_str(), "%x:%x", &lo, &length) >= 1 && lo < RAM_SIZE && length <= 0x1000 && lo + length <= RAM_SIZE)
            g_ranges.push_back({lo, length, std::vector<u8>(g_ram + lo, g_ram + lo + length)});
        if (comma == std::string::npos) break;
        at = comma + 1;
    }
    if (const char* ticks = getenv("SOAK_WATCH_TICKS")) sscanf(ticks, "%u:%u", &g_tick_lo, &g_tick_hi);
    const char* path = getenv("SOAK_WATCH_LOG");
    g_watch_log = path ? fopen(path, "w") : stderr;
}
void watch_check(const char* when) {
    if (!g_watch_ready) watch_setup();
    if (g_ranges.empty()) return;
    u32 tick = rd(G_NETFRAME);
    bool inside = tick >= g_tick_lo && tick <= g_tick_hi;
    if (!inside && !g_watch_armed) return;
    for (Range& r : g_ranges) {
        if (memcmp(g_ram + r.lo, r.shadow.data(), r.length) == 0) continue;
        if (inside && g_watch_armed) {
            for (u32 i = 0; i < r.length; i += 4) {
                u32 n = r.length - i < 4 ? r.length - i : 4, was = 0, now = 0;
                memcpy(&was, r.shadow.data() + i, n);
                memcpy(&now, g_ram + r.lo + i, n);
                if (was == now) continue;
                fprintf(g_watch_log, "tick %u %s addr %08x was %08x now %08x site %x chain", tick, when, r.lo + i, was, now, g_site);
                for (unsigned k = 0; k < 14 && k < t_sp; k++) fprintf(g_watch_log, " %x", t_stack[(t_sp - 1 - k) & 1023]);
                fprintf(g_watch_log, "\n");
            }
            fflush(g_watch_log);
        }
        memcpy(r.shadow.data(), g_ram + r.lo, r.length);
    }
    g_watch_armed = inside;
}
}  // namespace
void soak_enter(u32 target) { watch_check("call"); t_stack[t_sp++ & 1023] = target; }
void soak_leave() { watch_check("return"); if (t_sp) t_sp--; }
#endif

namespace {
void at_finish() {
#ifdef SOAK_INSTRUMENT_COUNT
    if (const char* path = getenv("SOAK_CALLS")) {
        if (FILE* f = fopen(path, "w")) {
            for (u32 i = 0; i < (1u << 20); i++)
                if (g_soak_calls[i]) fprintf(f, "%x %u\n", i << 2, g_soak_calls[i]);
            fclose(f);
        }
    }
#endif
    if (g_prev_finish) g_prev_finish();
}
}  // namespace

// tasks_run, called by the shim's hook in place of the translation: the game's task pass,
// then - if this was a lockstep tick - the checksums, which the shim's tick log then reads
void soak_tasks_run(Ctx* c) {
    u32 ra = (u32)c->r[31];
    orig_003226e4(c);
    if (ra != TICK_RETURN) return;
    start();
    pool_checksums();
    // SOAK_MACHINES=2: a pair in which one machine holds the other dropped (a kick, a leave,
    // a time-out) has nothing left to compare; it ends 60 ticks later
    static int machines = -1, countdown = -1;
    if (machines < 0) { const char* v = getenv("SOAK_MACHINES"); machines = v ? atoi(v) : 0; }
    if (machines == 2) {
        if (countdown < 0 && (g_ram[G_PEERS + PEER_DROPPED] || g_ram[G_PEERS + PEER_SIZE + PEER_DROPPED])) {
            countdown = 60;
            printf("soak: tick %u: a peer is held dropped; the run ends in 60 ticks\n", rd(G_NETFRAME));
        }
        if (countdown > 0 && --countdown == 0) { fflush(nullptr); rt_finish(0); }
    }
}

// gfx_vblankHandler, likewise: nothing is added per frame yet
void soak_vblank(Ctx* c) { orig_0019b6e4(c); }
