// cinematic.cpp - hold to skip a cut scene (cinematic.h; docs/issues/native-cutscenes.md).
#include "cinematic.h"
#include "rt.h"
#include "../net2/hooks.h"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace cinematic {
namespace {

// ---- the game (names.tsv; the disassembly of cut_runFrame 0x199944) ----
const u32 G_PADS = 0x41bfd8, PAD = 0x58, PAD_HELD = 8, PAD_PRESSED = 0xc;
const u32 G_PLAYER_COUNT = 0x4d8ae0;        // the count cut_runFrame's skip loop runs over (0x199dd8)
const u32 G_CUT_ACTIVE = 0x44fcd0, G_CUT_FRAME = 0x44fce0, G_CUT_SKIP = 0x44fcec;
const u32 G_SIM_FRAME = 0x44fdcc, G_NETWORK_MODE = 0x402791;
const u32 START = 0x800;

enum : u32 { H_MAGIC = 0, H_VERSION = 4, H_MODE = 8, H_SKIPS = 0xc, H_NEED = 0x10, H_PLAYERS = 0x14, H_FRAME = 0x18, H_HELD_BACK = 0x1c };

bool ok(u32 a, u32 size = 4) { a &= 0x1FFFFFFF; return a >= 0x80000 && a <= RAM_SIZE - size; }
u32 RD(u32 a) { u32 v = 0; if (ok(a)) memcpy(&v, g_ram + (a & 0x1FFFFFFF), 4); return v; }
u8 RB(u32 a) { return ok(a, 1) ? g_ram[a & 0x1FFFFFFF] : 0; }
void WR(u32 a, u32 v) { if (ok(a)) memcpy(g_ram + (a & 0x1FFFFFFF), &v, 4); }
s32 BR(u32 off) { return (s32)RD(CINE_BASE + off); }
void BW(u32 off, s32 v) { WR(CINE_BASE + off, (u32)v); }

std::atomic<bool> g_want{false};
std::atomic<int> g_room{-1};            // -1 no room game; 0 / 1 the launched game's mode
int g_last_room = -1;
bool g_on = false;
// counters (per machine)
uint64_t g_calls = 0, g_counted = 0, g_skips = 0, g_held_back = 0;

void reset_all() {
    for (u32 a = 0; a < 0x40; a += 4) WR(CINE_BASE + a, 0);
    BW(H_MAGIC, (s32)CINE_MAGIC);
    BW(H_VERSION, 1);
    BW(H_NEED, HOLD_TICKS);
}

// what the room is told: the mode's version (a copy that skips otherwise must not meet this one in a game)
u32 cine_figure() {
    u32 h = 2166136261u;
    const char* text = "cinematic 1: START held 60 ticks by every player; cut_runFrame 0x199944 pressed bit 0x800";
    for (const char* p = text; *p; p++) h = (h ^ (u8)*p) * 16777619u;
    return h;
}

struct Hooks {
    Hooks() {
        net2hook::cine_wanted = [] { return g_want.load() ? 1 : 0; };
        net2hook::cine_figure = [] { return cine_figure(); };
        net2hook::cine_room = [](int on) { g_room = on; };
    }
} g_hooks_installed;

}  // namespace

void want(bool on) { g_want = on; }
bool wanted() { return g_want.load(); }
bool active() { return g_on; }

void blank(uint64_t) {
    bool net = RB(G_NETWORK_MODE) != 0;
    int room = g_room.load();
    bool on = room >= 0 ? room == 1 : !net && g_want.load();
    if (on != g_on || room != g_last_room) {
        g_last_room = room;
        reset_all();
        g_on = on;
        BW(H_MODE, on ? 1 : 0);
        if (!on) BW(H_MAGIC, 0);
        fprintf(stderr, "cinematic: hold to skip is %s (%s)\n", on ? "ON" : "off", room >= 0 ? "a room's game" : net ? "an online game without a room: off" : "offline");
    }
}

void run_frame(Ctx* c, RecompFn original) {
    if (!g_on) { original(c); return; }
    g_calls++;
    s32 n = (s32)RD(G_PLAYER_COUNT);
    if (n < 0) n = 0;
    if (n > 4) n = 4;
    BW(H_PLAYERS, n);
    // once a game frame (the function may be reached twice in one: from its task and from the frame loop)
    s32 frame = (s32)RD(G_SIM_FRAME);
    bool count = BR(H_FRAME) != frame || BR(H_FRAME) == 0;
    bool fresh = BR(H_FRAME) != frame - 1 && BR(H_FRAME) != frame;     // a scene that just began: counts start again
    BW(H_FRAME, frame);
    if (count) g_counted++;
    bool all = n > 0;
    for (s32 k = 0; k < n; k++) {
        u32 row = G_PADS + (u32)k * PAD;
        bool held = (RD(row + PAD_HELD) & START) != 0;
        s32 t = BR(CINE_HOLD + (u32)k * 4);
        if (fresh && t > 0) t = 0;
        if (count) {
            if (!held) t = 0;
            else if (t >= 0 && t < 0x7fff) t++;
            BW(CINE_HOLD + (u32)k * 4, t);
        }
        all = all && t >= HOLD_TICKS;
    }
    // the game's own skip test sees START pressed only in the tick in which every player has held it long enough
    u32 saved[4] = {0, 0, 0, 0};
    for (s32 k = 0; k < n; k++) {
        u32 row = G_PADS + (u32)k * PAD;
        saved[k] = RD(row + PAD_PRESSED);
        if ((saved[k] & START) && !all) { g_held_back++; BW(H_HELD_BACK, BR(H_HELD_BACK) + 1); }
        WR(row + PAD_PRESSED, saved[k] & ~START);
    }
    if (all) WR(G_PADS + PAD_PRESSED, RD(G_PADS + PAD_PRESSED) | START);
    u8 skip_before = RB(G_CUT_SKIP);
    original(c);
    for (s32 k = 0; k < n; k++) WR(G_PADS + (u32)k * PAD + PAD_PRESSED, saved[k]);
    if (all) {
        // held through: each player counts again only after letting go (a next scene is not skipped by the same hold)
        for (s32 k = 0; k < n; k++) BW(CINE_HOLD + (u32)k * 4, -1);
        if (!skip_before && (RB(G_CUT_SKIP) || !RB(G_CUT_ACTIVE))) { g_skips++; BW(H_SKIPS, BR(H_SKIPS) + 1); }
    }
}

bool setting(const char* key, const char* value) {
    if (strcmp(key, "cinematic.skip") != 0) return false;
    std::string text = value ? value : "";
    g_want = text == "hold" || text == "on" || text == "yes";
    return true;
}

std::string settings_text() {
    return std::string("cinematic.skip = ") + (g_want.load() ? "hold" : "tap") +
           "        # hold: a cut scene is skipped by holding START for a second (every player of a room); tap: the game's own (docs/issues/native-cutscenes.md)\n";
}

std::string figures() {
    char text[200];
    snprintf(text, sizeof text, "cinematic: hold to skip %s; scene ticks %llu, counted %llu, scenes skipped %llu, taps held back %llu",
             g_on ? "on" : "off", (unsigned long long)g_calls, (unsigned long long)g_counted, (unsigned long long)g_skips, (unsigned long long)g_held_back);
    return text;
}

std::string command(const std::string& text) {
    std::string w = text;
    while (!w.empty() && w[0] == ' ') w.erase(0, 1);
    if (w.empty() || w == "info") {
        char one[200];
        snprintf(one, sizeof one, "%s | block mode=%d skips=%d need=%d players=%d frame=%d held_back=%d hold=%d,%d,%d,%d cut=%d cut_frame=%d", figures().c_str(),
                 BR(H_MODE), BR(H_SKIPS), BR(H_NEED), BR(H_PLAYERS), BR(H_FRAME), BR(H_HELD_BACK), BR(CINE_HOLD), BR(CINE_HOLD + 4), BR(CINE_HOLD + 8),
                 BR(CINE_HOLD + 12), (int)RB(G_CUT_ACTIVE), (int)RD(G_CUT_FRAME));
        return one;
    }
    if (w == "on" || w == "off") { if (RB(G_NETWORK_MODE)) return "cinematic: not during an online game"; g_want = w == "on"; return "cinematic: wanted " + w; }
    return "cinematic: info | on | off";
}

}  // namespace cinematic
