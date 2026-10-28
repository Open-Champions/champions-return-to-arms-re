// party8.cpp - the tables sized for four moved to where they have room for eight (party8.h).
#include "party8.h"
#include "guestmap.h"
#include "moved.h"
#include "rt.h"
#include "../net2/hooks.h"
#include "testerkit.h"
#include "backend.h"

#include <atomic>
#include <mutex>
#include <unordered_map>
#include <vector>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <cmath>
#include <string>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <dlfcn.h>
#include <execinfo.h>
#include <sys/mman.h>
#include <unistd.h>
#endif

// What the translation made with --reloc defines (tools/recomp/recomp.py: table.cpp); the weak ones here are taken
// in a program whose translation has no relocations (then nothing can be moved).
__attribute__((weak)) u32 g_reloc[PARTY8_TABLES];
__attribute__((weak)) u32 g_reloc_spans[PARTY8_TABLES][2];
__attribute__((weak)) unsigned g_reloc_count;
__attribute__((weak)) u32 g_party8_slots;    // the hard-coded fours (recomp.py --reloc-sites): 4, or 8 in a game of five to eight

namespace party8 {
namespace {

// Where the moved tables go: guest memory the game leaves alone (below its executable at 0x100000, above the
// runtime's kernel at 0x30000), without the two pieces seen in use (0x74000-0x77fff, 0x82000-0x83fff: written while the
// game starts) and the other modes' blocks from 0xE0000.  Checked to be empty at every move.
struct Area { u32 lo, hi; };
const Area AREAS[] = {{0x30000, 0x74000}, {0x88000, 0xE0000}};
const u32 SAVED_PLAYERS = 0x879ec0;      // g_savedPlayers
const u32 SEND_CYCLE_TABLE = 0x4027e8;   // g_netSendCycleTable
const u32 EQCACHE = 0x8659e8, EQCACHE_ROW = 0x160;      // the equipment cache: 10 rows of 4 x 0x58
static_assert(guestmap::at(0x30000).hi == 0x74000 && guestmap::at(0x88000).hi == 0xE0000, "party8.cpp: the areas are not those of guestmap.h");
std::atomic<int> g_want{-1};            // -1 nothing asked, 0 move back, 1 move, 2 move and poison, 3 move, poison and trap
bool g_moved = false;
u32 g_new[PARTY8_TABLES];                          // where each table is while moved
u32 g_moves = 0, g_backs = 0;

u32 size_of(int k) { return g_reloc_spans[k][1] - g_reloc_spans[k][0]; }

bool areas_free() {
    bool free = true;
    for (const Area& r : AREAS)
        for (u32 b = r.lo; b < r.hi; b += 0x4000) {
            u32 used = 0, first = 0;
            for (u32 a = b; a < b + 0x4000 && a < r.hi; a += 4) { u32 v; memcpy(&v, g_ram + a, 4); if (v) { if (!used) first = a; used++; } }
            if (used) { fprintf(stderr, "party8: guest memory 0x%x is in use (%u words from 0x%x)\n", b, used, first); free = false; }
        }
    return free;
}

// The trap (a test aid): the whole pages inside the old places made unreadable, so that an access the translator
// missed stops the program with the host's call stack (the translated function's name, fn_<address>).
// The Windows trace names the module and offset (the private link map resolves it); POSIX keeps dladdr's symbol.
uintptr_t describe_site(void* site, char* name, size_t size) {
#ifdef _WIN32
    HMODULE module = nullptr;
    char path[MAX_PATH] = {};
    if (GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           reinterpret_cast<LPCSTR>(site), &module) && GetModuleFileNameA(module, path, sizeof path - 1)) {
        const char* base = strrchr(path, '\\');
        snprintf(name, size, "%s", base ? base + 1 : path);
        return reinterpret_cast<uintptr_t>(site) - reinterpret_cast<uintptr_t>(module);
    }
    snprintf(name, size, "?");
    return 0;
#else
    Dl_info info{};
    if (dladdr(site, &info) && info.dli_sname) {
        snprintf(name, size, "%s", info.dli_sname);
        return reinterpret_cast<uintptr_t>(site) - reinterpret_cast<uintptr_t>(info.dli_saddr);
    }
    snprintf(name, size, "?");
    return 0;
#endif
}

#ifdef _WIN32
uintptr_t g_trap_page = 0;
bool trapped_address(uintptr_t address) {
    if (!g_trap_page || !g_ram) return false;
    for (int k = 0; k < PARTY8_TABLES; ++k) {
        if (!size_of(k)) continue;
        const uintptr_t lo = (reinterpret_cast<uintptr_t>(g_ram + g_reloc_spans[k][0]) + g_trap_page - 1) & ~(g_trap_page - 1);
        const uintptr_t hi = reinterpret_cast<uintptr_t>(g_ram + g_reloc_spans[k][1]) & ~(g_trap_page - 1);
        if (address >= lo && address < hi) return true;
    }
    return false;
}
void trap_line(const char* text) {
    DWORD written;
    WriteFile(GetStdHandle(STD_ERROR_HANDLE), text, (DWORD)strlen(text), &written, nullptr);
}
LONG CALLBACK on_fault(EXCEPTION_POINTERS* fault) {
    const auto* record = fault->ExceptionRecord;
    if (record->ExceptionCode != EXCEPTION_ACCESS_VIOLATION || record->NumberParameters < 2 ||
        !trapped_address((uintptr_t)record->ExceptionInformation[1])) return EXCEPTION_CONTINUE_SEARCH;
    char line[512];
    snprintf(line, sizeof line, "party8: TRAP: an access to the old place of a moved table, guest address 0x%x; the call stack:\n",
             (u32)((uintptr_t)record->ExceptionInformation[1] - reinterpret_cast<uintptr_t>(g_ram)));
    trap_line(line);
    void* frames[24];
    USHORT count = CaptureStackBackTrace(0, 24, frames, nullptr);
    for (USHORT k = 0; k < count; ++k) {
        char name[MAX_PATH];
        const uintptr_t offset = describe_site(frames[k], name, sizeof name);
        snprintf(line, sizeof line, "  %s+0x%llx\n", name, (unsigned long long)offset);
        trap_line(line);
    }
    TerminateProcess(GetCurrentProcess(), 70);
    return EXCEPTION_CONTINUE_SEARCH;
}
void trap_old_places() {
    SYSTEM_INFO system;
    GetSystemInfo(&system);
    g_trap_page = system.dwPageSize;
    if (!AddVectoredExceptionHandler(1, on_fault)) {
        fprintf(stderr, "party8: cannot install the old-place trap (error %lu)\n", GetLastError());
        fflush(stderr);
        TerminateProcess(GetCurrentProcess(), 70);
    }
    for (int k = 0; k < PARTY8_TABLES; ++k) {
        if (!size_of(k)) continue;
        const uintptr_t lo = (reinterpret_cast<uintptr_t>(g_ram + g_reloc_spans[k][0]) + g_trap_page - 1) & ~(g_trap_page - 1);
        const uintptr_t hi = reinterpret_cast<uintptr_t>(g_ram + g_reloc_spans[k][1]) & ~(g_trap_page - 1);
        DWORD old;
        if (hi > lo && !VirtualProtect(reinterpret_cast<void*>(lo), hi - lo, PAGE_NOACCESS, &old)) {
            fprintf(stderr, "party8: cannot protect an old place (error %lu)\n", GetLastError());
            fflush(stderr);
            TerminateProcess(GetCurrentProcess(), 70);
        }
    }
}
#else
void on_fault(int sig, siginfo_t* info, void*) {
    char line[160];
    u32 guest = (u32)((u8*)info->si_addr - g_ram);
    int n = snprintf(line, sizeof line, "party8: TRAP: an access to the old place of a moved table, guest address 0x%x; the call stack:\n", guest);
    write(2, line, (size_t)n);
    void* frames[24];
    int count = backtrace(frames, 24);
    backtrace_symbols_fd(frames, count, 2);
    signal(sig, SIG_DFL);
    _exit(70);
}
void trap_old_places() {
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_fault;
    sa.sa_flags = SA_SIGINFO;
    sigaction(SIGSEGV, &sa, nullptr);
    sigaction(SIGBUS, &sa, nullptr);
    const uintptr_t page = (uintptr_t)getpagesize();
    for (int k = 0; k < PARTY8_TABLES; k++) {
        if (!size_of(k)) continue;
        uintptr_t lo = ((uintptr_t)(g_ram + g_reloc_spans[k][0]) + page - 1) & ~(page - 1);
        uintptr_t hi = (uintptr_t)(g_ram + g_reloc_spans[k][1]) & ~(page - 1);
        if (hi > lo) mprotect((void*)lo, hi - lo, PROT_NONE);
    }
}
#endif

void move(bool poison, bool trap) {
    if (!available() || g_moved) return;
    if (!areas_free()) { fprintf(stderr, "party8: the tables are not moved\n"); return; }
    // the largest first, each with room for twice its size (eight players): into the upper area first - the native
    // modules' readers take nothing below 0x80000 for the game's memory - and the snapshot of the records
    // (g_savedPlayers, read by the game's code only) into the lower one
    u32 at[2] = {AREAS[0].lo, AREAS[1].lo};
    bool placed[PARTY8_TABLES] = {false};
    for (int round = 0; round < PARTY8_TABLES; round++) {
        int best = -1;
        for (int k = 0; k < PARTY8_TABLES; k++) if (size_of(k) && !placed[k] && (best < 0 || size_of(k) > size_of(best))) best = k;
        if (best < 0) break;
        u32 n = 2 * size_of(best);
        const bool low = g_reloc_spans[best][0] == SAVED_PLAYERS;
        int a = low ? 0 : 1;
        // the new place keeps the old one's address modulo 16: the game reads the unaligned address tables (0x402b3b)
        // with lwl/lwr pairs, whose halves depend on the address's low bits
        const u32 low4 = g_reloc_spans[best][0] & 15u;
        // (right where the last one ended when that already has the low bits: rows of one table, each its own range,
        // stay exactly twice their size apart - the equipment cache, party8-ranges.txt)
        auto place = [&](u32 from) { return (from & 15u) == low4 ? from : ((from + 15) & ~15u) + low4; };
        if (place(at[a]) + n > AREAS[a].hi) a = 1 - a;
        if (place(at[a]) + n > AREAS[a].hi) { fprintf(stderr, "party8: no room for table %d (0x%x bytes)\n", best, n); return; }
        g_new[best] = place(at[a]);
        at[a] = g_new[best] + n;
        placed[best] = true;
    }
    // the equipment cache's rows must lie 2 x 0x160 apart, in order (the translation's rows:0x160 sites count on it)
    for (u32 r = 1; r < 10; r++) {
        int prev = -1, cur = -1;
        for (int k = 0; k < PARTY8_TABLES; k++) {
            if (size_of(k) && g_reloc_spans[k][0] == EQCACHE + (r - 1) * EQCACHE_ROW) prev = k;
            if (size_of(k) && g_reloc_spans[k][0] == EQCACHE + r * EQCACHE_ROW) cur = k;
        }
        if (prev >= 0 && cur >= 0 && g_new[cur] != g_new[prev] + 2 * EQCACHE_ROW) {
            fprintf(stderr, "party8: the equipment cache's rows %u and %u are not 0x%x apart (0x%x, 0x%x): the tables are not moved\n", r - 1, r,
                    2 * EQCACHE_ROW, g_new[prev], g_new[cur]);
            return;
        }
    }
    // words in memory that point into an old place (pointers the game made before the move): listed (a test aid)
    if (getenv("PARTY8_SCAN")) {
        u32 found = 0;
        for (u32 a = 0x3e9c00; a + 4 <= RAM_SIZE; a += 4) {   // from the data segment (below it: code)
            u32 v; memcpy(&v, g_ram + a, 4);
            u32 p = v & 0x1FFFFFFF;
            for (int k = 0; k < PARTY8_TABLES; k++) {
                if (!size_of(k) || p < g_reloc_spans[k][0] || p >= g_reloc_spans[k][1]) continue;
                bool inside = false;
                for (int q = 0; q < PARTY8_TABLES; q++) inside |= size_of(q) && a >= g_reloc_spans[q][0] && a < g_reloc_spans[q][1];
                if (!inside && found++ < 200) fprintf(stderr, "party8: SCAN: the word at 0x%x holds 0x%x (table of 0x%x)\n", a, v, g_reloc_spans[k][0]);
                break;
            }
        }
        fprintf(stderr, "party8: SCAN: %u words point into the old places\n", found);
    }
    for (int k = 0; k < PARTY8_TABLES; k++) {
        u32 n = size_of(k);
        if (!n) continue;
        u32 old = g_reloc_spans[k][0];
        memcpy(g_ram + g_new[k], g_ram + old, n);
        if (poison) memset(g_ram + old, 0xA5, n);
        g_reloc[k] = g_new[k] - old;
    }
    // g_netSendCycleTable (s32 by the number of remote peers: 6, 2, 4, 6) gets the entries for four to seven remote
    // peers: one packet every second call, as for the others (docs/issues/native-8-players.md A.3)
    for (int k = 0; k < PARTY8_TABLES; k++)
        if (size_of(k) && g_reloc_spans[k][0] == SEND_CYCLE_TABLE)
            for (u32 n = 4; n < 8; n++) { u32 v = 2 * n; memcpy(g_ram + g_new[k] + 4 * n, &v, 4); }
    g_party8_spans = g_reloc_spans;
    g_party8_delta = g_reloc;               // the native modules' reads follow from here on (moved.h)
    for (int k = 0; k < PARTY8_TABLES; k++)
        if (size_of(k)) for (u32 p = g_reloc_spans[k][0] >> 16; p <= (g_reloc_spans[k][1] - 1) >> 16; p++) g_party8_page[p] = 1;
    g_moved = true;
    g_moves++;
    fprintf(stderr, "party8: %u tables moved (0x%x-0x%x, 0x%x-0x%x)%s%s\n", g_reloc_count, AREAS[0].lo, at[0], AREAS[1].lo, at[1],
            poison ? "; the old places poisoned" : "", trap ? "; their whole pages trapped" : "");
    if (trap) trap_old_places();
}

void set_wide(int count) {
    const bool on = count > 4 && g_moved;
    if (&g_party8_slots) g_party8_slots = on ? 8 : 4;
    g_party8_wide = on ? 1 : 0;
    g_party8_rx_mask = 0x100;
    fprintf(stderr, "party8: %s\n", on ? "a game of five to eight: the player-slot fours are eight" : "the player-slot fours are four");
}

bool asked() {
    const char* o = rt_option("party8");
    return o && strcmp(o, "0") != 0;
}

// net2 (net2/hooks.h): the copy can play a game of five to eight when it was started for it (--opt party8=1) and its
// translation has the relocations; the launch tells the game's count
struct Hooks {
    Hooks() {
        // five to eight players need the bigger heap too (party8=8: rt/moved.h g_party8_memtop)
        net2hook::party8_capable = [] { return available() && (g_moved || asked()) && g_party8_memtop > 0x02000000u ? 1 : 0; };
        net2hook::party8_game = [](int count) { if (count == 0 || count > 4) set_wide(count); };
    }
} g_hooks;

// ---- the inventory's item lists (inventory_pollResources 0x1bfbc8) --------------------------------------------------
// The inventory resource holds one item-list block per local player: 0x23988 bytes each from the pointer at 0x4ebbb0
// (resource + 0x300000), four of them (the function clears four), and the inventory's textures at resource + 0x400000.
// A player 5..8 indexes past the four: player 8's block would run 0x1cc40 bytes into the textures.  Every reader takes
// the block as pointer + slot x 0x23988 and only for a local player (net_isLocalPlayer 0x13e150 first), and in a room
// a machine has one local player.  So in a game of five to eight a machine whose player is 5..8 is given the pointer
// four blocks lower: its block is then the one player slot - 4 would have used - inside the cleared four, on a machine
// where that player is not local.  Nothing in any other game (the wrapper only calls the game's function).
const u32 INV_POLL = 0x1bfbc8, INV_LISTS = 0x4ebbb0, INV_BLOCK = 0x23988;
const u32 SETTINGS_MY_SLOT = 0x402a30 + 9;      // the launch's settings block +9: this machine's player slot (net2/launch.cpp)
RecompFn g_inv_orig = nullptr;
u32 g_inv_given = 0, g_inv_shifts = 0;
u32 rd_u32(u32 a) { u32 v = 0; a &= 0x1FFFFFFF; if (g_ram && a <= RAM_SIZE - 4) memcpy(&v, g_ram + a, 4); return v; }
void w_inventory_poll(Ctx* c) {
    g_inv_orig(c);
    if (!g_party8_wide || !g_ram) return;
    const u32 at = party8_at(SETTINGS_MY_SLOT) & 0x1FFFFFFF;
    const int mine = at < RAM_SIZE ? g_ram[at] : 0;
    const u32 lists = rd_u32(INV_LISTS);
    if (mine < 4 || mine > 7 || lists == 0 || lists == g_inv_given) return;
    g_inv_given = lists - 4 * INV_BLOCK;
    memcpy(g_ram + INV_LISTS, &g_inv_given, 4);
    g_inv_shifts++;
    fprintf(stderr, "party8: the inventory's item lists of player %d at %08x (the block of player %d, cleared, not local here)\n", mine + 1,
            g_inv_given + (u32)mine * INV_BLOCK, mine - 3);
}
void install_inventory() {
    static bool done = false;
    if (done || !available()) return;
    done = true;
    g_inv_orig = rt_replace_function(INV_POLL, w_inventory_poll);
    if (!g_inv_orig) fprintf(stderr, "party8: inventory_pollResources not found: players 5..8 keep the game's item-list blocks\n");
}

void move_back() {
    if (!g_moved) return;
    if (g_party8_wide) set_wide(0);
    memset(g_party8_page, 0, sizeof g_party8_page);
    g_party8_delta = nullptr;
    for (int k = 0; k < PARTY8_TABLES; k++) {
        u32 n = size_of(k);
        if (!n) continue;
        memcpy(g_ram + g_reloc_spans[k][0], g_ram + g_new[k], n);
        memset(g_ram + g_new[k], 0, 2 * n);
        g_reloc[k] = 0;
    }
    g_moved = false;
    g_backs++;
    fprintf(stderr, "party8: the tables are back where the game has them\n");
}

}  // namespace

// The check build (RECOMP_RELOC_CHECK, rt/recomp.h): a load or store of the translated code at an old place, reported
// once per site with the function it is in.
void report_hit(u32 address, void* site) {
    static std::mutex lock;
    static std::unordered_map<void*, u32> seen;
    std::lock_guard<std::mutex> hold(lock);
    u32& n = seen[site];
    if (n++ || seen.size() > 400) return;
    char site_name[512];
    const uintptr_t offset = describe_site(site, site_name, sizeof site_name);
    const char* name = site_name;
    const u32 p = address & 0x1FFFFFFF;
    u32 table = 0;
    bool past = false;
    for (int k = 0; k < PARTY8_TABLES && !table; k++) {
        const u32 lo = g_reloc_spans[k][0], hi = g_reloc_spans[k][1];
        if (p >= lo && p < hi) table = lo;
        else if (lo < hi && p >= hi && p < hi + (hi - lo)) { table = lo; past = true; }
    }
    if (!table && g_party8_heapwatch && !(p >= g_party8_watch_lo && p < g_party8_watch_hi)) {
        // a heap header: the allocator's own functions (mem.cc, 0x14fcd8-0x150948) are expected
        unsigned long fn = 0;
        if (sscanf(name, "_Z11fn_%8lxP3Ctx", &fn) == 1 || sscanf(name, "_ZL13body_%8lxP3Ctxj", &fn) == 1 || sscanf(name, "_Z13orig_%8lxP3Ctx", &fn) == 1)
            if (fn >= 0x14fcd8 && fn < 0x150948) return;
        fprintf(stderr, "party8: HEAPWATCH: a heap block's header 0x%x reached from %s+0x%lx\n", address, name, (unsigned long)offset);
        return;
    }
    if (!table && p >= g_party8_watch_lo && p < g_party8_watch_hi) {
        fprintf(stderr, "party8: WATCH: 0x%x reached from %s+0x%lx\n", address, name, (unsigned long)offset);
        return;
    }
    fprintf(stderr, "party8: CHECK: the translated code reached %s 0x%x (table of 0x%x) from %s+0x%lx\n", past ? "PAST the old place, at" : "the old place",
            address, table, name, (unsigned long)offset);
}

}  // namespace party8

__attribute__((noinline)) void reloc_check_hit(u32 address) { party8::report_hit(address, __builtin_return_address(0)); }

// PARTY8_HEAPWATCH=1 (the check build): the heap blocks' headers as the last heap walk found them (sorted), so that an
// access to one from outside the allocator is reported (party8::report_hit filters the allocator's own functions)
static std::vector<u32> g_headers;
static std::mutex g_headers_lock;
__attribute__((noinline)) bool reloc_check_header(u32 p) {
    std::lock_guard<std::mutex> hold(g_headers_lock);
    auto it = std::upper_bound(g_headers.begin(), g_headers.end(), p);
    return it != g_headers.begin() && p - *(it - 1) < 0x14;
}

namespace party8 {

bool available() { return g_reloc_count > 0; }
bool moved() { return g_moved; }
void want(bool on, bool poison) { g_want = on ? (poison ? 2 : 1) : 0; }

// the equipment cache's records (a test aid: which slot's record holds which buffer); PARTY8_EQDUMP=N prints them at blank N
void eq_dump() {
    auto rd = [](u32 a) { u32 v = 0; a &= 0x1FFFFFFF; if (a + 4 <= RAM_SIZE) memcpy(&v, g_ram + a, 4); return v; };
    const u32 stride = g_party8_wide ? 2 * EQCACHE_ROW : EQCACHE_ROW;
    for (u32 r = 0; r < 10; r++)
        for (u32 k = 0; k < 8; k++) {
            const u32 rec = (party8_at(EQCACHE) & 0x1FFFFFFF) + r * stride + k * 0x58;
            if (k >= 4 && !g_party8_wide) break;
            if (!rd(rec)) continue;
            char name[24] = {};
            for (u32 i = 0; i < 23 && g_ram[rec + 0xc + i]; i++) name[i] = (char)g_ram[rec + 0xc + i];
            fprintf(stderr, "party8: EQ: row %u slot %u: buffer 0x%x size 0x%x off 0x%x flags %02x %02x %02x loaded %d '%s'\n", r, k, rd(rec), rd(rec + 4),
                    rd(rec + 0x4c), g_ram[rec + 0x54], g_ram[rec + 0x55], g_ram[rec + 0x56], (int)(int16_t)rd(rec + 8), name);
        }
}

// A test aid (PARTY8_HEAPCHECK=1, or always in a game of five to eight with PARTY8_HEAPCHECK unset to 0): the game's
// heap is a circular list of blocks from g_heapFirstBlock (+0xc next, +4 size, +8 tag); walked every 30 blanks, the
// first time it does not come round is reported with the blocks before the break.
void heap_check(uint64_t number) {
    static bool told = false;
    if (told || (number % 30 && !g_party8_heapwatch)) return;
    auto rd = [](u32 a) { u32 v = 0; a &= 0x1FFFFFFF; if (a + 4 <= RAM_SIZE) memcpy(&v, g_ram + a, 4); return v; };
    const u32 first = rd(0x6dffc8);
    if (!first) return;
    u32 b = first, prev = 0, prev2 = 0, prev3 = 0, prev4 = 0;
    static std::unordered_map<u32, int> seen;
    seen.clear();
    for (int n = 0; n < 200000; n++) {
        u32 next = rd(b + 0xc);
        if ((next & 0x1FFFFFFF) == 0 || (next & 0x1FFFFFFF) >= RAM_SIZE || !seen.emplace(b, n).second) {
            told = true;
            auto tag = [&](u32 block) {
                std::string t;
                u32 a = rd(block + 8) & 0x1FFFFFFF;
                for (u32 i = 0; i < 40 && a && a + i < RAM_SIZE && g_ram[a + i]; i++) t += (char)g_ram[a + i];
                return t;
            };
            fprintf(stderr, "party8: HEAP: at blank %llu the block list breaks after %d blocks: 0x%x (size 0x%x, tag 0x%x) -> next 0x%x; before it 0x%x (size 0x%x) "
                    "and 0x%x (size 0x%x, flags 0x%x, tag '%s')\n", (unsigned long long)number, n, b, rd(b + 4), rd(b + 8), next, prev, rd(prev + 4), prev2,
                    rd(prev2 + 4), rd(prev2), tag(prev2).c_str());
            for (u32 q : {prev3, prev4})
                fprintf(stderr, "party8: HEAP:   earlier 0x%x: size 0x%x, flags 0x%x, tag '%s', next 0x%x\n", q, rd(q + 4), rd(q), tag(q).c_str(), rd(q + 0xc));
            eq_dump();
            return;
        }
        if (next == first) {
            if (g_party8_heapwatch) {
                std::vector<u32> h;
                h.reserve(seen.size());
                for (auto& kv : seen) h.push_back(kv.first & 0x1FFFFFFF);
                std::sort(h.begin(), h.end());
                std::lock_guard<std::mutex> hold(g_headers_lock);
                g_headers.swap(h);
            }
            return;
        }
        prev4 = prev3; prev3 = prev2; prev2 = prev; prev = b; b = next;
    }
    told = true;
    fprintf(stderr, "party8: HEAP: at blank %llu the block list does not come round in 200000 blocks\n", (unsigned long long)number);
}

void blank(uint64_t number) {
    static bool first = true;
    if (first) {
        g_party8_heapwatch = getenv("PARTY8_HEAPWATCH") && !strcmp(getenv("PARTY8_HEAPWATCH"), "1");
        if (const char* w = getenv("PARTY8_WATCH")) {
            unsigned long lo = strtoul(w, nullptr, 16), n = 4;
            if (const char* c = strchr(w, ':')) n = strtoul(c + 1, nullptr, 0);
            g_party8_watch_lo = (u32)lo; g_party8_watch_hi = (u32)(lo + n);
        }
        // "--opt party8=1" (or =poison): the tables are moved at the first blank, before the game has made a pointer into them
        first = false;
        if (asked()) want(true, strstr(rt_option("party8"), "poison") != nullptr);
        if (asked()) install_inventory();       // a copy started for rooms of up to eight (the wrapper does nothing in four)
    }
    if (g_ram && getenv("PARTY8_EQDUMP") && number == strtoull(getenv("PARTY8_EQDUMP"), nullptr, 0)) eq_dump();
    if (g_ram && ((g_party8_wide && !(getenv("PARTY8_HEAPCHECK") && !strcmp(getenv("PARTY8_HEAPCHECK"), "0"))) ||
                  (getenv("PARTY8_HEAPCHECK") && !strcmp(getenv("PARTY8_HEAPCHECK"), "1"))))
        heap_check(number);
    int w = g_want.exchange(-1);
    if (w < 0 || !g_ram) return;
    if (w == 0) move_back();
    else move(w >= 2, w == 3);
}

std::string command(const std::string& text) {
    std::string w = text;
    while (!w.empty() && w[0] == ' ') w.erase(0, 1);
    if (w == "on" || w == "on poison" || w == "on trap") {
        if (!available()) return "party8: this translation has no relocations (app/build.py --party8)";
        if (w == "on trap") g_want = 3;
        else want(true, w == "on poison");
        return "party8: the tables move at the next frame";
    }
    if (w == "off") { want(false); return "party8: the tables move back at the next frame"; }
    char out[256];
    snprintf(out, sizeof out, "party8: %s, %u tables, %s; moved %u times, back %u times; inventory lists moved down %u times", available() ? "relocations present" : "no relocations",
             g_reloc_count, g_moved ? "moved" : "where the game has them", g_moves, g_backs, g_inv_shifts);
    return out;
}

}  // namespace party8

namespace party8 {

void overlay(render::FrameList& frame) {
    if (!g_party8_wide || !g_ram || !frame.show_target || frame.show_rect[2] <= 0 || frame.show_rect[3] <= 0) return;
    auto rd = [](u32 a) { u32 v = 0; memcpy(&v, g_ram + (a & 0x1FFFFFFF), 4); return v; };
    if (g_ram[0x41b510] != 0) return;                           // g_inFrontend
    const int count = (int)rd(0x4d8ae0);                        // g_numPlayers
    if (count <= 4 || count > 8) return;
    const u32 players = party8_at(0x4d8af0) & 0x1FFFFFFF;       // g_players, moved (slots 4..7 past the old end)
    const u32 peers = party8_at(0x5bf838) & 0x1FFFFFFF;
    const float X = (float)frame.show_rect[0], Y = (float)frame.show_rect[1], W = (float)frame.show_rect[2], H = (float)frame.show_rect[3];
    const float px = std::max(1.0f, std::floor(H / 448.0f + 0.25f)), lh = 22 * px, bw = 96 * px;
    size_t first = frame.vertices.size();
    auto quad = [&](float x0, float y0, float x1, float y1, uint8_t r, uint8_t g, uint8_t b, uint8_t a) {
        render::Vertex v{};
        v.z = 1; v.q = 1; v.r = r; v.g = g; v.b = b; v.a = a;
        auto put = [&](float x, float y) { v.x = x; v.y = y; frame.vertices.push_back(v); };
        put(x0, y0); put(x1, y0); put(x0, y1); put(x1, y0); put(x1, y1); put(x0, y1);
    };
    float y = Y + H * 0.22f;
    const float x = X + W - bw - 10 * px;
    for (int slot = 4; slot < count; slot++, y += lh) {
        const u32 rec = players + (u32)slot * 0x4c30;
        char name[24] = {};
        memcpy(name, g_ram + rec, sizeof name - 1);
        for (char& c : name) if (c && (c < 32 || c > 126)) c = '?';
        float hp, most;
        { u32 a = rd(rec + 0xac), b = rd(rec + 0xb0); memcpy(&hp, &a, 4); memcpy(&most, &b, 4); }
        const bool gone = g_ram[peers + (u32)slot * 0x44e0 + 0x44d5] != 0;
        const float share = most > 0 ? std::max(0.0f, std::min(1.0f, hp / most)) : 0;
        char line[48];
        snprintf(line, sizeof line, "P%d %s%s", slot + 1, name[0] ? name : "-", gone ? " (LEFT)" : "");
        testerkit::text(frame, x, y, px, line, 0xf0, 0xe8, 0xd0, gone ? 0x50 : 0x80);
        const float by = y + 10 * px, bh = 4 * px;
        quad(x - 1, by - 1, x + bw + 1, by + bh + 1, 0, 0, 0, 0x60);
        if (share > 0) quad(x, by, x + bw * share, by + bh, 0xd0, 0x30, 0x28, gone ? 0x30 : 0x70);
    }
    if (frame.vertices.size() == first) return;
    render::DrawCmd cmd;
    cmd.kind = render::CMD_DRAW;
    cmd.prim = render::PK_TRIANGLES;
    cmd.first = (uint32_t)first;
    cmd.count = (uint32_t)(frame.vertices.size() - first);
    cmd.target = frame.show_target;
    cmd.scissor[0] = frame.show_rect[0]; cmd.scissor[1] = frame.show_rect[1];
    cmd.scissor[2] = frame.show_rect[0] + frame.show_rect[2]; cmd.scissor[3] = frame.show_rect[1] + frame.show_rect[3];
    cmd.blend = true; cmd.ba = 0; cmd.bb = 1; cmd.bc = 0; cmd.bd = 1;
    cmd.made_by = 2;
    frame.commands.push_back(cmd);
}

}  // namespace party8
