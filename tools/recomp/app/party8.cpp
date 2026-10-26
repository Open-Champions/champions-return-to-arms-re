// party8.cpp - the tables sized for four moved to where they have room for eight (party8.h).
#include "party8.h"
#include "guestmap.h"
#include "moved.h"
#include "rt.h"

#include <atomic>
#include <dlfcn.h>
#include <mutex>
#include <unordered_map>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <execinfo.h>
#include <sys/mman.h>
#include <unistd.h>
#include <cstring>
#include <string>

// What the translation made with --reloc defines (tools/recomp/recomp.py: table.cpp); the weak ones here are taken
// in a program whose translation has no relocations (then nothing can be moved).
__attribute__((weak)) u32 g_reloc[32];
__attribute__((weak)) u32 g_reloc_spans[32][2];
__attribute__((weak)) unsigned g_reloc_count;

namespace party8 {
namespace {

// Where the moved tables go: guest memory the game leaves alone (below its executable at 0x100000, above the
// runtime's kernel at 0x30000), without the two pieces seen in use (0x74000-0x77fff, 0x82000-0x83fff: written while the
// game starts) and the other modes' blocks from 0xE0000.  Checked to be empty at every move.
struct Area { u32 lo, hi; };
const Area AREAS[] = {{0x30000, 0x74000}, {0x88000, 0xE0000}};
const u32 SAVED_PLAYERS = 0x879ec0;      // g_savedPlayers
static_assert(guestmap::at(0x30000).hi == 0x74000 && guestmap::at(0x88000).hi == 0xE0000, "party8.cpp: the areas are not those of guestmap.h");
std::atomic<int> g_want{-1};            // -1 nothing asked, 0 move back, 1 move, 2 move and poison, 3 move, poison and trap
bool g_moved = false;
u32 g_new[32];                          // where each table is while moved
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
    for (int k = 0; k < 32; k++) {
        if (!size_of(k)) continue;
        uintptr_t lo = ((uintptr_t)(g_ram + g_reloc_spans[k][0]) + page - 1) & ~(page - 1);
        uintptr_t hi = (uintptr_t)(g_ram + g_reloc_spans[k][1]) & ~(page - 1);
        if (hi > lo) mprotect((void*)lo, hi - lo, PROT_NONE);
    }
}

void move(bool poison, bool trap) {
    if (!available() || g_moved) return;
    if (!areas_free()) { fprintf(stderr, "party8: the tables are not moved\n"); return; }
    // the largest first, each with room for twice its size (eight players): into the upper area first - the native
    // modules' readers take nothing below 0x80000 for the game's memory - and the snapshot of the records
    // (g_savedPlayers, read by the game's code only) into the lower one
    u32 at[2] = {AREAS[0].lo, AREAS[1].lo};
    bool placed[32] = {false};
    for (int round = 0; round < 32; round++) {
        int best = -1;
        for (int k = 0; k < 32; k++) if (size_of(k) && !placed[k] && (best < 0 || size_of(k) > size_of(best))) best = k;
        if (best < 0) break;
        u32 n = 2 * size_of(best);
        const bool low = g_reloc_spans[best][0] == SAVED_PLAYERS;
        int a = low ? 0 : 1;
        if (((at[a] + 15) & ~15u) + n > AREAS[a].hi) a = 1 - a;
        if (((at[a] + 15) & ~15u) + n > AREAS[a].hi) { fprintf(stderr, "party8: no room for table %d (0x%x bytes)\n", best, n); return; }
        g_new[best] = (at[a] + 15) & ~15u;
        at[a] = g_new[best] + n;
        placed[best] = true;
    }
    // words in memory that point into an old place (pointers the game made before the move): listed (a test aid)
    if (getenv("PARTY8_SCAN")) {
        u32 found = 0;
        for (u32 a = 0x3e9c00; a + 4 <= RAM_SIZE; a += 4) {   // from the data segment (below it: code)
            u32 v; memcpy(&v, g_ram + a, 4);
            u32 p = v & 0x1FFFFFFF;
            for (int k = 0; k < 32; k++) {
                if (!size_of(k) || p < g_reloc_spans[k][0] || p >= g_reloc_spans[k][1]) continue;
                bool inside = false;
                for (int q = 0; q < 32; q++) inside |= size_of(q) && a >= g_reloc_spans[q][0] && a < g_reloc_spans[q][1];
                if (!inside && found++ < 200) fprintf(stderr, "party8: SCAN: the word at 0x%x holds 0x%x (table of 0x%x)\n", a, v, g_reloc_spans[k][0]);
                break;
            }
        }
        fprintf(stderr, "party8: SCAN: %u words point into the old places\n", found);
    }
    for (int k = 0; k < 32; k++) {
        u32 n = size_of(k);
        if (!n) continue;
        u32 old = g_reloc_spans[k][0];
        memcpy(g_ram + g_new[k], g_ram + old, n);
        if (poison) memset(g_ram + old, 0xA5, n);
        g_reloc[k] = g_new[k] - old;
    }
    g_party8_spans = g_reloc_spans;
    g_party8_delta = g_reloc;               // the native modules' reads follow from here on (moved.h)
    for (int k = 0; k < 32; k++)
        if (size_of(k)) for (u32 p = g_reloc_spans[k][0] >> 16; p <= (g_reloc_spans[k][1] - 1) >> 16; p++) g_party8_page[p] = 1;
    g_moved = true;
    g_moves++;
    fprintf(stderr, "party8: %u tables moved (0x%x-0x%x, 0x%x-0x%x)%s%s\n", g_reloc_count, AREAS[0].lo, at[0], AREAS[1].lo, at[1],
            poison ? "; the old places poisoned" : "", trap ? "; their whole pages trapped" : "");
    if (trap) trap_old_places();
}

void move_back() {
    if (!g_moved) return;
    memset(g_party8_page, 0, sizeof g_party8_page);
    g_party8_delta = nullptr;
    for (int k = 0; k < 32; k++) {
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
    Dl_info info;
    const char* name = dladdr(site, &info) && info.dli_sname ? info.dli_sname : "?";
    fprintf(stderr, "party8: CHECK: the translated code reached the old place 0x%x (table of 0x%x) from %s+0x%lx\n", address,
            [&] { for (int k = 0; k < 32; k++) if ((address & 0x1FFFFFFF) >= g_reloc_spans[k][0] && (address & 0x1FFFFFFF) < g_reloc_spans[k][1]) return g_reloc_spans[k][0]; return 0u; }(),
            name, (unsigned long)((char*)site - (char*)info.dli_saddr));
}

}  // namespace party8

__attribute__((noinline)) void reloc_check_hit(u32 address) { party8::report_hit(address, __builtin_return_address(0)); }

namespace party8 {

bool available() { return g_reloc_count > 0; }
bool moved() { return g_moved; }
void want(bool on, bool poison) { g_want = on ? (poison ? 2 : 1) : 0; }

void blank(uint64_t number) {
    (void)number;
    static bool first = true;
    if (first) {
        // "--opt party8=1" (or =poison): the tables are moved at the first blank, before the game has made a pointer into them
        first = false;
        if (const char* o = rt_option("party8")) if (strcmp(o, "0") != 0) want(true, strcmp(o, "poison") == 0);
    }
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
    snprintf(out, sizeof out, "party8: %s, %u tables, %s; moved %u times, back %u times", available() ? "relocations present" : "no relocations",
             g_reloc_count, g_moved ? "moved" : "where the game has them", g_moves, g_backs);
    return out;
}

}  // namespace party8
