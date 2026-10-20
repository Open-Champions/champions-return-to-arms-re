// fpaim.cpp - aiming by looking (fpaim.h; docs/issues/native-first-person-aim.md).
#include "fpaim.h"
#include "fpcontrols.h"
#include "rt.h"
#include "../net2/hooks.h"

#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>

namespace fpaim {
namespace {

// ---- the game (docs/spec/player-tick.md state 0, docs/netcode.md "Game messages", docs/spec/object-system.md 1) ----
const u32 PLAYER_RUN = 0x1a5030, NULL_HANDLER = 0x1e01b0, NET_SEND_GAME_MSG = 0x13db38, NULL_CHANNEL_ID = 0x86aa60;
const u32 MATH_COS16 = 0x166630, MATH_SIN16 = 0x1666e0, MATH_ATAN2_16 = 0x166798, NET_GET_CAM_YAW = 0x13e0c8;
const u32 G_RUN_LIST = 0x5db3a8, G_NETWORK_MODE = 0x402791, G_SIM_FRAME = 0x44fdcc;
const u32 O_FLAGS = 0x0c, O_FACING = 0x38, O_VTABLE = 0x48, O_OWNER = 0x4c, P_SLOT = 0x3c8;
const u32 FLAG_COPY = 0x20000, FLAG_OWNED = 0x80;
const int T_UP = 0x3e3d;                // the heading a pushed-up stick walks along is T_UP - the yaw word (Player_move)
const s32 PITCH_MAX = 0x3800;           // 78.75 degrees
const u8 SUBTYPE = 3;                   // message 4: 0 / 1 the game's (ignored), 2 the strafe section's, 3 this

// Projectile classes whose run moves them by a velocity they keep (obj_moveAndCollide 0x1509f8 with that vector):
// the vector is turned onto the look.  Read in each class's run (slot 4); homing bolts (DiseaseBolt, HolyBolt,
// HolyStrike, PoisonBolt: they rebuild their velocity from a heading turned toward their target every tick) are
// not in the list - the game keeps steering them.
struct Class { u32 vtable; u32 velocity; const char* name; };
const Class CLASSES[] = {
    {0x50e5a0, 0x1b0, "MissileWeapon"},          // bow arrows, Multi Fire (run 0x15153c)
    {0x50e470, 0x1b0, "playerProjectile"},       // thrown weapons, Fire / Cold Axe (run 0x1ba940; falls by 9 a tick)
    {0x518de0, 0x54, "FireArrowProjectile"},     // run 0x2d66ac
    {0x518ef8, 0x54, "ColdArrowProjectile"},     // 0x2d73c8
    {0x519010, 0x54, "PoisonArrowProjectile"},   // 0x2d8e80
    {0x519240, 0x54, "ExplodeArrowProjectile"},  // 0x2db17c
    {0x50e998, 0x58, "Sparks"},                  // Shock of Fire (0x28fa3c)
    {0x51a838, 0x9c, "ShockOfFrost"},            // 0x2f77c0
};
const int CLASS_COUNT = (int)(sizeof CLASSES / sizeof CLASSES[0]);

bool ok(u32 a, u32 size = 4) { a &= 0x1FFFFFFF; return a >= 0x80000 && a <= RAM_SIZE - size; }
u32 RD(u32 a) { u32 v = 0; if (ok(a)) memcpy(&v, g_ram + (a & 0x1FFFFFFF), 4); return v; }
u16 RH(u32 a) { u16 v = 0; if (ok(a, 2)) memcpy(&v, g_ram + (a & 0x1FFFFFFF), 2); return v; }
u8 RB(u32 a) { return ok(a, 1) ? g_ram[a & 0x1FFFFFFF] : 0; }
float RF(u32 a) { float v = 0; if (ok(a)) memcpy(&v, g_ram + (a & 0x1FFFFFFF), 4); return v; }
void WR(u32 a, u32 v) { if (ok(a)) memcpy(g_ram + (a & 0x1FFFFFFF), &v, 4); }
void WH(u32 a, u16 v) { if (ok(a, 2)) memcpy(g_ram + (a & 0x1FFFFFFF), &v, 2); }
void WB(u32 a, u8 v) { if (ok(a, 1)) g_ram[a & 0x1FFFFFFF] = v; }
void WF(u32 a, float v) { u32 b; memcpy(&b, &v, 4); WR(a, b); }
u32 bits(float v) { u32 b; memcpy(&b, &v, 4); return b; }
float flt(u32 b) { float v; memcpy(&v, &b, 4); return v; }
s32 BR(u32 off) { return (s32)RD(AIM_BASE + off); }
void BW(u32 off, s32 v) { WR(AIM_BASE + off, (u32)v); }
u32 slot_off(int slot, u32 field) { return AIM_SLOT + (u32)slot * AIM_SLOT_SIZE + field; }
enum : u32 { H_MAGIC = 0, H_VERSION = 4, H_MODE = 8, H_MESSAGES = 0xc, H_AIMED = 0x10, L_MESSAGE = 0x100 };
enum : u32 { S_ON = 0, S_PITCH = 4, S_MESSAGES = 8, S_AIMED = 0xc, S_HEADING = 0x10, S_LAST_PITCH = 0x14, S_CLASS = 0x18, S_SPEED = 0x1c };

// ---- state ----
std::atomic<bool> g_want{false};
std::atomic<int> g_room{-1};            // -1 no room game; 0 / 1 the launched game's mode
int g_last_room = -1;
bool g_on = false, g_installed = false;
RecompFn g_orig_run = nullptr, g_orig_handler = nullptr;
uint64_t g_blank = 0;
// the sender (this machine)
int g_sent_on = -1, g_sent_pitch = 0;
uint64_t g_sent_blank = 0;
// counters (per machine)
uint64_t g_runs = 0, g_handled = 0, g_sent = 0, g_aimed = 0, g_foreign = 0;

// A game function called the way its own code calls it, on the context that is running (registers put back
// afterwards); v0 and f0 out.
struct Out { u32 v0; u32 f0; };
Out call(Ctx* c, u32 address, u32 a0, u32 a1 = 0, u32 a2 = 0, u32 f12 = 0, u32 f13 = 0) {
    Ctx saved = *c;
    c->r[29] = (u64)(s64)(s32)((((u32)saved.r[29]) - 0x600) & ~15u);
    c->r[4] = (u64)(s64)(s32)a0; c->r[5] = (u64)(s64)(s32)a1; c->r[6] = (u64)(s64)(s32)a2;
    c->f[12] = f12; c->f[13] = f13;
    rt_call(c, address);
    Out out{(u32)c->r[2], c->f[0]};
    s64 budget = c->budget;
    *c = saved;
    c->budget = budget;
    return out;
}
float cos16(Ctx* c, s32 a) { return flt(call(c, MATH_COS16, (u32)a).f0); }
float sin16(Ctx* c, s32 a) { return flt(call(c, MATH_SIN16, (u32)a).f0); }

void reset_all() {
    for (u32 a = 0; a < 0x100; a += 4) WR(AIM_BASE + a, 0);
    BW(H_MAGIC, (s32)AIM_MAGIC);
    BW(H_VERSION, 1);
}

int class_of(u32 vtable) {
    for (int k = 0; k < CLASS_COUNT; k++) if (CLASSES[k].vtable == vtable) return k;
    return -1;
}

// One projectile just launched by player P (slot): its velocity turned onto the look, its speed kept; its facing
// (the angle its model is drawn at, and nothing else of the kept-velocity classes) turned by as much.
void aim_object(Ctx* c, u32 P, int slot, u32 O) {
    if (!ok(O, 0x60)) return;
    int k = class_of(RD(O + O_VTABLE));
    if (k < 0) return;
    u32 head = RD(O + O_OWNER), owner = (head && ok(head, 16)) ? RD(head + 12) : 0;
    if (!(RD(O + O_FLAGS) & FLAG_OWNED) || owner != P) { g_foreign++; return; }
    u32 V = O + CLASSES[k].velocity;
    if (!ok(V, 12)) return;
    float vx = RF(V), vy = RF(V + 4), vz = RF(V + 8);
    float speed = std::sqrt(vx * vx + vy * vy + vz * vz);
    if (!(speed > 0.0f) || !(speed < 1.0e6f)) return;
    s32 heading = (s16)(T_UP - (s16)call(c, NET_GET_CAM_YAW, (u32)slot).v0);
    s32 pitch = BR(slot_off(slot, S_PITCH));
    float ch = cos16(c, heading), sh = sin16(c, heading), cp = cos16(c, pitch), sp = sin16(c, pitch);
    float level = speed * cp;
    float nx = level * ch, ny = level * sh, nz = speed * sp;
    s32 before = (s16)call(c, MATH_ATAN2_16, 0, 0, 0, bits(vy), bits(vx)).v0;   // atan2f(y, x) in 16-bit units
    WF(V, nx); WF(V + 4, ny); WF(V + 8, nz);
    WH(O + O_FACING, (u16)(s16)((s16)RH(O + O_FACING) + (s16)(heading - before)));
    g_aimed++;
    BW(H_AIMED, BR(H_AIMED) + 1);
    BW(slot_off(slot, S_AIMED), BR(slot_off(slot, S_AIMED)) + 1);
    BW(slot_off(slot, S_HEADING), heading);
    BW(slot_off(slot, S_LAST_PITCH), pitch);
    BW(slot_off(slot, S_CLASS), k + 1);
    WF(AIM_BASE + slot_off(slot, S_SPEED), speed);
    static const bool log = getenv("AIM_LOG") != nullptr;
    if (log)
        fprintf(stderr, "aim: tick %u: player %d %s %08x: (%.2f %.2f %.2f) -> (%.2f %.2f %.2f), heading %d (was %d), pitch %d\n", RD(G_SIM_FRAME), slot,
                CLASSES[k].name, O, vx, vy, vz, nx, ny, nz, heading, before, pitch);
}

// ---- Player_run (slot 4) ----------------------------------------------------------------------
// A new object is linked to the FRONT of its run list (docs/spec/object-system.md 1, 2.2): what stands in front of
// the objects that were first before the original ran was linked during it.  The run list is the same on every
// machine; only objects owned by this player and of a known class are touched.
void w_player_run(Ctx* c) {
    u32 P = (u32)c->r[4];
    if (!g_on || !ok(P, 0x590) || (RD(P + O_FLAGS) & FLAG_COPY)) { g_orig_run(c); return; }
    s32 slot = (s32)RD(P + P_SLOT);
    if (slot < 0 || slot > 3 || BR(slot_off(slot, S_ON)) == 0) { g_orig_run(c); return; }
    g_runs++;
    u32 front[8];
    int n = 0;
    for (u32 node = RD(G_RUN_LIST), steps = 0; node && ok(node, 16) && n < 8 && steps < 64; node = RD(node), steps++)
        if (u32 o = RD(node + 12)) front[n++] = o;
    g_orig_run(c);
    for (u32 node = RD(G_RUN_LIST), steps = 0; node && ok(node, 16) && steps < 64; node = RD(node), steps++) {
        u32 o = RD(node + 12);
        if (!o) continue;
        bool old = false;
        for (int k = 0; k < n && !old; k++) old = front[k] == o;
        if (old) break;
        aim_object(c, P, slot, o);
    }
}

// ---- message 4's handler: a0 the bytes, a1 their count ----------------------------------------
void w_handler(Ctx* c) {
    u32 bytes = (u32)c->r[4];
    s32 count = (s32)c->r[5];
    if (!g_on || count < 5 || RB(bytes) != SUBTYPE) { g_orig_handler(c); return; }
    int slot = RB(bytes + 1);
    if (slot > 3) return;
    s32 pitch = (s16)(RB(bytes + 3) | RB(bytes + 4) << 8);
    if (pitch > PITCH_MAX) pitch = PITCH_MAX;
    if (pitch < -PITCH_MAX) pitch = -PITCH_MAX;
    BW(slot_off(slot, S_ON), (RB(bytes + 2) & 1) ? 1 : 0);
    BW(slot_off(slot, S_PITCH), pitch);
    BW(slot_off(slot, S_MESSAGES), BR(slot_off(slot, S_MESSAGES)) + 1);
    BW(H_MESSAGES, BR(H_MESSAGES) + 1);
    g_handled++;
}

void install() {
    if (g_installed) return;
    g_orig_run = rt_replace_function(PLAYER_RUN, w_player_run);
    g_orig_handler = rt_replace_function(NULL_HANDLER, w_handler);
    if (!g_orig_run || !g_orig_handler) {
        if (g_orig_run) rt_replace_function(PLAYER_RUN, g_orig_run);
        if (g_orig_handler) rt_replace_function(NULL_HANDLER, g_orig_handler);
        fprintf(stderr, "aim: the game's functions are not all there; the mode stays off\n");
        g_want = false;
        return;
    }
    g_installed = true;
    fprintf(stderr, "aim: the look-aim wrappers are in place\n");
}

// what the room is told: the mode's version (a change of how it aims must not meet an older copy in a game)
u32 aim_figure() {
    u32 h = 2166136261u;
    const char* text = "fpaim 1: MissileWeapon playerProjectile Fire Cold Poison Explode arrows Sparks ShockOfFrost; message 4/3";
    for (const char* p = text; *p; p++) h = (h ^ (u8)*p) * 16777619u;
    return h;
}

struct Hooks {
    Hooks() {
        net2hook::aim_wanted = [] { return g_want.load() ? 1 : 0; };
        net2hook::aim_want = [](bool on) { g_want = on; };
        net2hook::aim_figure = [] { return aim_figure(); };
        net2hook::aim_room = [](int on) { g_room = on; };
    }
} g_hooks_installed;

}  // namespace

void want(bool on) { g_want = on; }
bool wanted() { return g_want.load(); }
bool active() { return g_on; }

void blank(uint64_t number) {
    g_blank = number;
    bool net = RB(G_NETWORK_MODE) != 0;
    int room = g_room.load();
    bool on = room >= 0 ? room == 1 : !net && g_want.load();
    if (on && !g_installed) install();
    if (on && !g_installed) on = false;
    if (on != g_on || room != g_last_room) {
        g_last_room = room;
        reset_all();
        g_on = on;
        BW(H_MODE, on ? 1 : 0);
        if (!on) BW(H_MAGIC, 0);
        g_sent_on = -1;
        fprintf(stderr, "aim: aiming by looking is %s (%s)\n", on ? "ON" : "off", room >= 0 ? "a room's game" : net ? "an online game without a room: off" : "offline");
    }
    fpcontrols::set_aim(on);
}

void drawn(Ctx* c, int view, bool steering, float pitch_degrees) {
    if (!g_on || !c) return;
    const fpcontrols::Hud& h = fpcontrols::hud();
    if (h.slot < 0 || h.slot > 3) return;
    bool on = steering && h.playing && (view == fpcontrols::FIRST || view == fpcontrols::SHOULDER);
    s32 pitch = 0;
    if (on) {
        float units = pitch_degrees * (65536.0f / 360.0f);
        pitch = (s32)std::lround(units);
        if (pitch > PITCH_MAX) pitch = PITCH_MAX;
        if (pitch < -PITCH_MAX) pitch = -PITCH_MAX;
    }
    // what the simulation holds for this player, and what was sent last: a message when they differ
    bool held_on = BR(slot_off(h.slot, S_ON)) != 0;
    s32 held_pitch = BR(slot_off(h.slot, S_PITCH));
    if (!on && !held_on) { if (g_sent_on != 1) g_sent_on = 0; return; }       // off, and the simulation knows: nothing to say
    bool differs = on != held_on || (on && std::abs(pitch - held_pitch) >= 46);           // a quarter of a degree
    bool changed = (int)on != g_sent_on || (on && std::abs(pitch - g_sent_pitch) >= 46);
    if (!differs && !changed) return;
    // at most one message every two blanks (every blank when it turns on or off); again after a second if the
    // simulation still holds something else (a level change, a mode change reset the block)
    uint64_t since = g_blank - g_sent_blank;
    if ((int)on == g_sent_on && since < 2) return;
    if (!changed && since < 60) return;
    u32 m = AIM_BASE + L_MESSAGE;
    WB(m, SUBTYPE); WB(m + 1, (u8)h.slot); WB(m + 2, on ? 1 : 0); WB(m + 3, (u8)(pitch & 0xff)); WB(m + 4, (u8)((pitch >> 8) & 0xff));
    call(c, NET_SEND_GAME_MSG, RD(NULL_CHANNEL_ID), m, 5);
    g_sent_on = on ? 1 : 0;
    g_sent_pitch = pitch;
    g_sent_blank = g_blank;
    g_sent++;
}

bool setting(const char* key, const char* value) {
    if (strcmp(key, "combat.aim") != 0) return false;
    std::string text = value ? value : "";
    g_want = text == "look" || text == "on" || text == "yes";
    return true;
}

std::string settings_text() {
    return std::string("combat.aim = ") + (g_want.load() ? "look" : "off") +
           "        # look: in first person and over the shoulder arrows, thrown weapons and spell bolts go where you look (docs/issues/native-first-person-aim.md)\n";
}

std::string figures() {
    char text[256];
    snprintf(text, sizeof text, "aim: %s, wrappers %s; player ticks aimed for %llu, messages sent %llu, applied %llu, projectiles aimed %llu (others' %llu)",
             g_on ? "on" : "off", g_installed ? "in place" : "not installed", (unsigned long long)g_runs, (unsigned long long)g_sent,
             (unsigned long long)g_handled, (unsigned long long)g_aimed, (unsigned long long)g_foreign);
    return text;
}

std::string command(const std::string& text) {
    std::string w = text;
    while (!w.empty() && w[0] == ' ') w.erase(0, 1);
    if (w.empty() || w == "info") {
        std::string out = figures();
        for (int k = 0; k < 4; k++) {
            char one[160];
            snprintf(one, sizeof one, " | p%d on=%d pitch=%d msgs=%d aimed=%d last=%d/%d class=%d speed=%.1f", k, BR(slot_off(k, S_ON)), BR(slot_off(k, S_PITCH)),
                     BR(slot_off(k, S_MESSAGES)), BR(slot_off(k, S_AIMED)), BR(slot_off(k, S_HEADING)), BR(slot_off(k, S_LAST_PITCH)), BR(slot_off(k, S_CLASS)),
                     RF(AIM_BASE + slot_off(k, S_SPEED)));
            out += one;
        }
        return out;
    }
    if (w == "on" || w == "off") { if (RB(G_NETWORK_MODE)) return "aim: not during an online game"; g_want = w == "on"; return "aim: wanted " + w; }
    return "aim: info | on | off";
}

}  // namespace fpaim
