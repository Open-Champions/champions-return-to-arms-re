// fpcontrols.cpp - see fpcontrols.h.  Plain C++: no window system, nothing of the runtime
// but its memory (iface.h), so the Mac and the Windows program compile the same file.
//
// Addresses and rules of the game used here (docs/issues/native-first-person-controls.md
// part 1 has each with where it was read and what was run):
//   Player_move 0x1b4020   target facing T = atan2_16(lx, ly) - yaw word - 0x41c2; with the
//                          stick straight up that is 0x3e3d - yaw word.  It turns (40 % of the
//                          angle a tick in the neutral state) when s = S x |stick| > 0.01 and
//                          asks for a step of 180 x s / 60 along the facing.
//   obj_moveWithCollision  does not move for a step whose square is not above 0.001.
//   pad_decodeStick        |stick| = 1.4705882 x (m - 0.32), m the raw length in 1/128ths.
#include "fpcontrols.h"
#include "moved.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>

namespace fpcontrols {
namespace {

typedef uint8_t u8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef int32_t s32;

// ---- the game's memory ----------------------------------------------------------------------
const u32 RAM = 0x2000000;
bool ok(u32 a, u32 size = 4) { a &= 0x1FFFFFFF; return a >= 0x80000 && a <= RAM - size; }
u8* at(u32 a) { return rta::memory() + (party8_at(a) & 0x1FFFFFFF); }   // moved.h: a table moved for eight players
u32 W(u32 a) { u32 v = 0; if (ok(a)) memcpy(&v, at(a), 4); return v; }
u16 H(u32 a) { u16 v = 0; if (ok(a, 2)) memcpy(&v, at(a), 2); return v; }
u8 B(u32 a) { return ok(a, 1) ? *at(a) : 0; }
float F(u32 a) { float v = 0; if (ok(a)) memcpy(&v, at(a), 4); return v; }
void put16(u32 a, u16 v) { if (ok(a, 2)) memcpy(at(a), &v, 2); }
void put32(u32 a, u32 v) { if (ok(a)) memcpy(at(a), &v, 4); }

const u32 G_CAMERA = 0x4f8450, CAM_MODE = 0x34, CAM_YAW_VELOCITY = 0x3c, CAM_YAW = 0x68;
const u32 G_PLAYERS = 0x4d8af0, PLAYER_STRIDE = 0x4c30, REC_OBJECT = 0x43d8, REC_HP = 0xac, REC_SPEED = 0x4c20, REC_WEAPON_CLASS = 0x4a86;
const u32 G_LOCAL_ALIVE_COUNT = 0x4f8424, G_LOCAL_ALIVE = 0x4f8430;
const u32 OBJ_FLAGS = 0x0c, OBJ_POS = 0x10, OBJ_RADIUS = 0x1c, OBJ_HEIGHT = 0x20, OBJ_FACING = 0x38, OBJ_FLAGS64 = 0xa8;
const u32 CRE_HP = 0x228, CRE_HP_MAX = 0x22c, CRE_TARGET = 0x234, CRE_CHARM = 0x312;
const u32 P_ACTION_START = 0x448, P_ATTACK_REQUEST = 0x44c, P_STATE = 0x58c;
const u32 G_NET_CAM_YAW = 0x5d0bc0;
// the proposed strafe mode (app/fp-proposed.pnach): its hook in Player_move, and the mode byte of a player object
const u32 STRAFE_HOOK = 0x1b4210, STRAFE_HOOK_WORD = 0x08084A32, P_STRAFE = 0x47e;
const u32 G_SIM_FRAME = 0x44fdcc, G_NETWORK_MODE = 0x402791, G_GHOST = 0x4027bc, G_RUN_SPEED = 0x4f8418, G_GRID = 0x5db4f0, G_LEVEL_NAME = 0x41b721;
const u32 G_BTN_ATTACK = 0x41b980, G_BTN_ABILITY_A = 0x41b990, G_BTN_ABILITY_B = 0x41b9a0, G_BTN_USE = 0x41b9c0, G_BTN_BLOCK = 0x41b9d0, G_BTN_SWAP = 0x41ba30;
const u32 G_PROMPT_FADE = 0x4d8ac0, G_PROMPT_KIND = 0x4d8ad0, G_PROMPT_TEXT = 0x864f50;
const u32 FLAG_CREATURE = 0x20, FLAG_PLAYER = 0x40, FLAG_USABLE = 0x100000, FLAG_FRIENDLY = 0x1000000;

const float UNITS = 65536.0f / 360.0f;          // angle units per degree
const int T_UP = 0x3e3d;                         // facing a pushed-up stick asks for, plus the yaw word
const int VIEW_OFFSET = 0x4000 - T_UP;           // the game camera's own heading is this much to the left of it (0x1c3)
const float STICK_GAIN = 1.4705882f, STICK_DEAD = 0.32f;

s16 wrap16(int v) { return (s16)(u16)v; }
float clampf(float v, float lo, float hi) { return v < lo ? lo : v > hi ? hi : v; }
float deg_of(int units) { return (float)wrap16(units) / UNITS; }
float wrap_deg(float d) { while (d > 180) d -= 360; while (d <= -180) d += 360; return d; }
// the controller's bits (libpad order) <-> the game's held word (the two bytes the other way round)
u16 swap_bytes(u32 v) { return (u16)(((v & 0xff) << 8) | ((v >> 8) & 0xff)); }

// ---- settings -----------------------------------------------------------------------------
struct Settings {
    float mouse_sensitivity = 0.12f;    // degrees a count
    float mouse_pitch_scale = 1.0f;     // up and down against left and right
    float mouse_smoothing = 0.0f;       // 0 = none ... 0.9: share of the last motion carried over
    bool invert_y = false;              // mouse: pushing away looks down
    bool invert_stick_y = false;        // stick: up looks down
    float stick_yaw = 220.0f;           // degrees a second at full push
    float stick_pitch = 130.0f;
    float stick_deadzone = 0.14f;       // of the look stick, radial
    float stick_curve = 1.8f;           // exponent: fine near the centre, fast at the rim
    float stick_ease = 0.07f;           // seconds over which the turn takes up a new stick position
    float move_deadzone = 0.14f;        // of the move stick in the look views (the game's own is 0.32 of the raw stick)
    bool face[VIEW_COUNT] = {false, false, false, true, true};      // the character turns to the look
    bool turn_before_strike = true;     // a strike / cast press is held back while the character turns to the look
    int strike_wait = 6;                // at most this many ticks
    float strike_within = 12.0f;        // degrees: turned enough
    float idle_within = 0.5f;           // degrees: a standing character is turned when it is further off than this
    bool mouse_buttons = true;          // left attack, right block, middle use, wheel weapon set
    bool capture = true;                // the pointer is hidden and held in a look view
    float kick = 1.0f;                  // the view kick of swings and hits, 0 = none
    bool centre = true;                 // first person: the picture's centre is the walking direction
    int strafe = 1;                     // the "strafe mode" section, when the game has it: 0 off, 1 auto (the views that face the look), 2 on (every look view)
    float swing_turn = 5.0f;            // during a swing or shot the look comes round to the simulation's target: at most this many degrees a tick (0 = never)
    float swing_turn_within = 6.0f;     // ... until the target is this near the middle of the picture
    bool swing_tilt = true;             // first person: during a swing the view tips toward a target that is above or below the picture's middle
    // the lock-on of the souls-style combat mode (soulscombat.h)
    float lock_range = 600.0f;          // units: a target further than this (or dead, or no enemy any more) lets go
    float lock_turn = 0.30f;            // share of the bearing to the target the look turns a blank
    float lock_turn_max = 9.0f;         // degrees a blank at most
    float lock_flick = 7.0f;            // degrees of mouse turn in one blank (or the right stick past 0.85 from rest) that change target
};
Settings g_set;
std::mutex g_settings_lock;

// ---- what comes in from other threads --------------------------------------------------------
std::atomic<int> g_view{OVERHEAD};
std::atomic<bool> g_view_active{false};
std::atomic<float> g_view_pitch{0};
std::atomic<float> g_mouse_dx{0}, g_mouse_dy{0}, g_wheel{0};
std::atomic<u32> g_mouse_held{0};
std::atomic<float> g_pitch_out{0};
std::atomic<bool> g_pointer{false};
std::atomic<bool> g_souls{false};
std::atomic<bool> g_aim{false};       // aiming by looking (fpaim.h): a shot is not turned to the game's own target
std::atomic<int> g_lock_toggle{0};

void add(std::atomic<float>& a, float v) {
    float old = a.load();
    while (!a.compare_exchange_weak(old, old + v)) {}
}

// ---- state (the game's thread) ----------------------------------------------------------------
Hud g_hud;
u32 g_lock_object = 0;              // the souls mode's lock-on target (0: none)
int g_lock_flick_side = 0;          // the right stick's flick: -1 / 1 while held past the edge
bool g_lock_r3 = false;
bool g_look_on = false;
double g_look_units = 0;            // the yaw word, kept with its fraction
float g_stick_yaw_now = 0, g_stick_pitch_now = 0;   // degrees a second, eased
float g_mouse_carry_x = 0, g_mouse_carry_y = 0;
u16 g_prev_in = 0;                  // what the player held at the last blank
std::atomic<int> g_strafe_wanted{-1};  // what the mode byte should be; -1: the game has no such section
std::atomic<int> g_strafe_send{-1};    // a mode the application is to send now (take_strafe_send)
int g_strafe_asked_for = -1;
uint64_t g_strafe_asked_at = 0, g_strafe_sends = 0;
bool g_strafing = false;            // the character on screen has the mode on
bool g_idle_turning = false;        // the standing character is being turned to the look
int g_align_left = 0;               // ticks a press may still be held back
u16 g_align_buttons = 0;
int g_inject_left = 0;
u16 g_inject_buttons = 0;
int g_prev_state = -1;
u32 g_prev_start = 0;
u32 g_prev_object = 0;
float g_prev_hp = -1;
u32 g_locked_object = 0;
float g_locked_hp = 0;
float g_kick_pitch = 0, g_kick_roll = 0;    // degrees, decaying
bool g_log = false;
// counters
uint64_t g_assist_blanks = 0;
uint64_t g_blanks_steered = 0, g_nudges = 0, g_held_back = 0, g_held_ticks = 0, g_turn_states = 0, g_released_late = 0;

// ---- helpers ----------------------------------------------------------------------------------
struct Body {
    bool have = false;
    int slot = -1;
    u32 real = 0, object = 0;       // the simulated player, and the one on screen (the prediction copy in a net game)
    bool net = false;
    float hp = 0;
    int state = -1;
    s16 facing = 0;
    u32 since = 0;
    float x = 0, y = 0, z = 0;
};

Body find_body() {
    Body b;
    b.net = (int8_t)B(G_NETWORK_MODE) != 0;
    s32 alive = (s32)W(G_LOCAL_ALIVE_COUNT);
    b.slot = alive >= 1 ? (s32)W(G_LOCAL_ALIVE) : 0;
    if (b.slot < 0 || b.slot > 3) return b;
    u32 record = G_PLAYERS + (u32)b.slot * PLAYER_STRIDE;
    b.real = W(record + REC_OBJECT);
    if (!ok(b.real, 0x590)) return b;
    b.object = b.real;
    if (b.net) {
        u32 ghost = W(G_GHOST);
        if (ok(ghost, 0x590) && (W(ghost + OBJ_FLAGS) & FLAG_PLAYER)) b.object = ghost;
    }
    b.hp = F(record + REC_HP);
    b.state = (int)W(b.object + P_STATE);
    b.facing = (s16)H(b.object + OBJ_FACING);
    b.since = W(G_SIM_FRAME) - W(b.object + P_ACTION_START);
    b.x = F(b.object + OBJ_POS); b.y = F(b.object + OBJ_POS + 4); b.z = F(b.object + OBJ_POS + 8);
    b.have = alive == 1;
    return b;
}

// The speed scale S of Player_move (0x1b40d8): what a stick's length is multiplied by.
float speed_scale(const Body& b) {
    float base = 0.861945f;
    if (b.net && strncmp((const char*)at(G_LEVEL_NAME), "watmedal", 8) != 0) base = 0.75f;
    float s = base * F(G_PLAYERS + (u32)b.slot * PLAYER_STRIDE + REC_SPEED) * F(G_RUN_SPEED);
    if (!(s > 0.05f)) s = base;
    return s > 1.2f ? 1.2f : s;
}

// The smallest push straight up that turns the character: s just above 0.01.  Offline with
// the ordinary scale that is 42/128, whose step (0.0312 a tick) the move routine drops.
int nudge_length(const Body& b) {
    float s = speed_scale(b);
    for (int n = 41; n < 64; n++)
        if (s * STICK_GAIN * ((float)n / 128.0f - STICK_DEAD) > 0.01004f) return n + (b.net ? 2 : 0);   // a net game's stick codec is within 4 of what is asked
    return 46;
}

// ---- the world round the player, by the simulation's own rules ---------------------------------
struct Seen { u32 object; u32 flags; float x, y, z, r, h; };
int collect(float cx, float cy, float reach, Seen* out, int max) {
    int count = 0;
    int x0 = (((int)(cx - reach) + 0x3c00) >> 8), x1 = (((int)(cx + reach) + 0x3c00) >> 8);
    int y0 = (((int)(cy - reach) + 0x3c00) >> 8), y1 = (((int)(cy + reach) + 0x3c00) >> 8);
    for (int gy = std::max(0, y0); gy <= std::min(119, y1); gy++)
        for (int gx = std::max(0, x0); gx <= std::min(119, x1); gx++) {
            u32 node = W(G_GRID + (u32)(gy * 120 + gx) * 4);
            for (int guard = 0; node && ok(node, 16) && guard < 256; guard++) {
                u32 object = W(node + 12);
                if (object && ok(object, 0x60) && count < max) {
                    Seen s;
                    s.object = object;
                    s.flags = W(object + OBJ_FLAGS);
                    s.x = F(object + OBJ_POS); s.y = F(object + OBJ_POS + 4); s.z = F(object + OBJ_POS + 8);
                    s.r = F(object + OBJ_RADIUS); s.h = F(object + OBJ_HEIGHT);
                    out[count++] = s;
                }
                node = W(node);
            }
        }
    return count;
}

// Player_isEnemy 0x1b5ea8 outside the player-against-player modes.
bool is_enemy(const Seen& s) {
    if (!(s.flags & FLAG_CREATURE) || (s.flags & (8 | FLAG_FRIENDLY | FLAG_PLAYER))) return false;
    if (!ok(s.object, 0x320)) return false;
    u32 low = W(s.object + OBJ_FLAGS64);
    if (low & (0x4000000 | 0x800)) return false;
    return (s16)H(s.object + CRE_CHARM) == 0;
}

void mark(Mark& m, const Seen& s, const Body& b, float bearing, float rim) {
    m.valid = true;
    m.object = s.object;
    m.x = s.x; m.y = s.y; m.z = s.z + s.h * 0.5f;
    m.distance = rim;
    m.bearing = bearing;
    m.hp = F(s.object + CRE_HP);
    m.hp_max = F(s.object + CRE_HP_MAX);
    (void)b;
}

void update_hud(uint64_t blank, const Body& b, bool steer, int heading_units, float fov_half) {
    Hud& h = g_hud;
    h.blank = blank;
    h.tick = W(G_SIM_FRAME);
    h.view = g_view.load();
    h.look = steer;
    h.slot = b.slot;
    h.player = b.object;
    h.playing = b.have && b.hp > 0;
    h.x = b.x; h.y = b.y; h.z = b.z;
    h.state = b.state;
    h.facing = deg_of(b.facing);
    h.look_heading = deg_of(heading_units);
    h.facing_error = deg_of(heading_units - b.facing);
    h.look_pitch = g_view_pitch.load();
    // a hit taken (also the one that kills: the lists below are not made for a dead player, so the bearing is that
    // of the nearest attacker of the blank before)
    if (b.real && b.real == g_prev_object && g_prev_hp > 0 && b.hp < g_prev_hp - 0.01f) {
        h.hits_taken++;
        h.last_hit_amount = g_prev_hp - b.hp;
        h.last_hit_bearing = 0;
        for (int k = 0; k < h.threat_count; k++) if (h.threats[k].targets_me) { h.last_hit_bearing = h.threats[k].bearing; break; }
        float full = std::max(1.0f, F(G_PLAYERS + (u32)std::max(0, b.slot) * PLAYER_STRIDE + REC_HP + 4));
        float size = clampf(h.last_hit_amount / full * 12.0f, 0.5f, 3.0f);
        g_kick_pitch += size;
        g_kick_roll += (h.last_hit_bearing >= 0 ? -1.0f : 1.0f) * size * 0.8f;
    }
    h.melee = Mark(); h.shot = Mark(); h.locked = Mark(); h.lock = Mark();
    h.threat_count = 0; h.behind = 0; h.foe_count = 0;
    h.souls = g_souls.load();
    h.usable = false; h.usable_text[0] = 0; h.usable_object = 0;
    // events that do not need a living player: death and coming back
    u32 record = G_PLAYERS + (u32)std::max(0, b.slot) * PLAYER_STRIDE;
    // (the simulated object names the character: the prediction copy of a net game is made anew every half second)
    if (b.real && b.real != g_prev_object) {
        if (g_prev_object && g_prev_hp <= 0 && b.hp > 0) h.respawns++;
        g_prev_object = b.real; g_prev_hp = b.hp; g_prev_state = b.state; g_prev_start = 0;
    }
    if (b.real && g_prev_hp > 0 && b.hp <= 0) h.deaths++;
    if (!b.have) { h.reticle = false; g_lock_object = 0; if (b.real) g_prev_hp = b.hp; return; }
    h.weapon_class = (int8_t)B(record + REC_WEAPON_CLASS);
    h.ranged = h.weapon_class == 4 || h.weapon_class == 6;
    h.reticle = steer && h.playing && (h.ranged || b.state == 0 || b.state == 5);
    // a swing or a shot begins: the action state is 1 or 0 and its start frame is a new one
    u32 start = W(b.object + P_ACTION_START);
    if ((b.state == 1 || b.state == 0) && (g_prev_state != b.state || start != g_prev_start)) { h.swings++; g_kick_pitch -= 0.9f; }
    g_prev_state = b.state;
    g_prev_start = start;

    static Seen seen[256];
    int count = collect(b.x, b.y, 420.0f, seen, 256);
    float hx = std::cos(h.look_heading * 3.14159265f / 180.0f), hy = std::sin(h.look_heading * 3.14159265f / 180.0f);
    float reach = (h.weapon_class == 1 || h.weapon_class == 3) ? 58.0f : 48.0f;
    float best_melee = 1e13f, best_shot = 1e13f;
    u32 locked = 0;
    u32 handle = W(b.object + CRE_TARGET);
    if (handle && ok(handle, 16)) locked = W(handle + 12);
    static Threat near_threat[96], near_foe[96];
    int threats = 0, foes = 0;
    bool lock_seen = false;
    for (int k = 0; k < count; k++) {
        const Seen& s = seen[k];
        if (s.object == b.object || s.object == b.real) continue;
        float dx = s.x - b.x, dy = s.y - b.y;
        float d = std::sqrt(dx * dx + dy * dy);
        // right of the look is a smaller heading: bearing positive to the right
        float bearing = d > 0.01f ? wrap_deg(h.look_heading - std::atan2(dy, dx) * 180.0f / 3.14159265f) : 0;
        if (s.object == locked && (s.flags & FLAG_CREATURE)) mark(h.locked, s, b, bearing, d - s.r);
        if (!is_enemy(s)) continue;
        if (F(s.object + CRE_HP) > 0 && d <= g_set.lock_range && foes < 96) {
            Threat t;
            t.object = s.object; t.x = s.x; t.y = s.y; t.z = s.z + s.h * 0.5f;
            t.distance = d; t.bearing = bearing; t.in_view = std::fabs(bearing) <= fov_half;
            near_foe[foes++] = t;
            if (s.object == g_lock_object) { mark(h.lock, s, b, bearing, d - s.r); lock_seen = true; }
        }
        float along = d > 0.01f ? (dx * hx + dy * hy) / d : 1;
        float rim = d - s.r;
        // melee (Player_run state 1, 0x1a9678 on): a box of the reach and +-72 in height, inside 60 degrees of the
        // facing, rim nearer than the reach; the lowest "rim - 32 x cosine" wins, the later one on a tie
        if (std::fabs(s.z - b.z) <= 72.0f + s.h && along >= 0.5f && rim < reach) {
            float score = rim - along * 32.0f;
            if (score <= best_melee) { best_melee = score; mark(h.melee, s, b, bearing, rim); }
        }
        // shots and casts (world_collectObjectsInArc 0x1614f0 with 340 and 20 degrees): a box of 340 each way, in
        // front, inside 10 degrees either side; the nearest is taken
        if (std::fabs(dx) <= 340.0f + s.r && std::fabs(dy) <= 340.0f + s.r && std::fabs(s.z - b.z) <= 340.0f && along > 0 && std::fabs(bearing) <= 10.0f) {
            if (d < best_shot) { best_shot = d; mark(h.shot, s, b, bearing, rim); }
        }
        // attackers
        u32 its = W(s.object + CRE_TARGET);
        u32 its_target = (its && ok(its, 16)) ? W(its + 12) : 0;
        bool me = its_target == b.real || its_target == b.object;
        if (d <= 400.0f && (me || d <= 160.0f)) {
            Threat t;
            t.object = s.object; t.x = s.x; t.y = s.y; t.z = s.z + s.h * 0.5f;
            t.distance = d; t.bearing = bearing; t.targets_me = me;
            s16 its_facing = (s16)H(s.object + OBJ_FACING);
            float to_me = std::atan2(-dy, -dx) * 180.0f / 3.14159265f;
            t.attacking = me && rim - 12.0f < 60.0f && std::fabs(wrap_deg(deg_of(its_facing) - to_me)) < 45.0f;
            t.in_view = std::fabs(bearing) <= fov_half;
            if (threats < 96) near_threat[threats++] = t;
        }
    }
    std::sort(near_threat, near_threat + threats, [](const Threat& l, const Threat& r) { return l.distance < r.distance; });
    for (int k = 0; k < threats; k++) if (near_threat[k].targets_me && !near_threat[k].in_view) h.behind++;
    if (threats > 16) threats = 16;
    h.threat_count = threats;
    for (int k = 0; k < threats; k++) h.threats[k] = near_threat[k];
    std::sort(near_foe, near_foe + foes, [](const Threat& l, const Threat& r) { return l.distance < r.distance; });
    h.foe_count = std::min(foes, 16);
    for (int k = 0; k < h.foe_count; k++) h.foes[k] = near_foe[k];
    if (g_lock_object && !lock_seen) g_lock_object = 0;     // dead, gone, out of range: the lock lets go

    // a hit landed: the creature the simulation holds as the target lost hit points
    if (h.locked.valid) {
        if (h.locked.object == g_locked_object && h.locked.hp < g_locked_hp - 0.01f) { h.hits_dealt++; g_kick_roll += (h.hits_dealt & 1) ? 0.7f : -0.7f; }
        g_locked_object = h.locked.object; g_locked_hp = h.locked.hp;
    } else g_locked_object = 0;
    g_prev_hp = b.hp;

    // something usable in reach: the game's own prompt (Player_interact 0x1b2640 fills it from the nearest usable
    // object in a box of 48 round the player, whatever way the player faces), and that object found again here
    s32 fade = (s32)W(G_PROMPT_FADE + (u32)b.slot * 4);
    h.usable_fade = fade;
    h.usable_kind = (int)W(G_PROMPT_KIND + (u32)b.slot * 4);
    float best = 1e7f;
    for (int k = 0; k < count; k++) {
        const Seen& s = seen[k];
        if (!(s.flags & FLAG_USABLE) || s.object == b.object || s.object == b.real) continue;
        if (std::fabs(s.x - b.x) > 48.0f + s.r || std::fabs(s.y - b.y) > 48.0f + s.r || s.z + s.h < b.z || s.z > b.z + 60.0f) continue;
        float dx = s.x - b.x, dy = s.y - b.y, dz = s.z - b.z, d2 = dx * dx + dy * dy + dz * dz;
        if (d2 < best) {
            best = d2;
            h.usable_object = s.object; h.usable_x = s.x; h.usable_y = s.y; h.usable_z = s.z;
            h.usable_bearing = d2 > 0.01f ? wrap_deg(h.look_heading - std::atan2(dy, dx) * 180.0f / 3.14159265f) : 0;
        }
    }
    h.usable = fade > 0 && H(G_PROMPT_TEXT + (u32)b.slot * 0x200) != 0;
    if (h.usable) {
        int n = 0;
        for (u32 k = 0; k < 95; k++) {
            u16 ch = H(G_PROMPT_TEXT + (u32)b.slot * 0x200 + k * 2);
            if (!ch) break;
            h.usable_text[n++] = (ch >= 0x20 && ch < 0x7f) ? (char)ch : '?';
        }
        h.usable_text[n] = 0;
    }
}

u8 stick_byte(float v) {            // -1..1 to a stick byte: 0 is -1.0, 255 is +0.992
    int b = 128 + (int)std::lround(v * (v < 0 ? 128.0f : 127.0f));
    return (u8)(b < 0 ? 0 : b > 255 ? 255 : b);
}

}  // namespace

// ---- from the application ---------------------------------------------------------------------
void set_view(int view, bool active, float look_pitch) {
    if (view < 0 || view >= VIEW_COUNT) view = OVERHEAD;
    g_view = view;
    g_view_active = active;
    g_view_pitch = look_pitch;
}
void mouse_motion(float dx, float dy) { add(g_mouse_dx, dx); add(g_mouse_dy, dy); }
void mouse_button(int button, bool down) {
    if (button < 0 || button > 4) return;
    if (down) g_mouse_held |= 1u << button; else g_mouse_held &= ~(1u << button);
}
void mouse_wheel(float steps) { add(g_wheel, steps); }
void release_all() { g_mouse_held = 0; }
float take_pitch() { return g_pitch_out.exchange(0); }
int strafe_wanted() { return g_strafe_wanted.load(); }
int take_strafe_send() { return g_strafe_send.exchange(-1); }
bool wants_pointer() { return g_pointer.load(); }
const Hud& hud() { return g_hud; }

void translate(uint64_t blank, rta::PadState& state) {
    Settings set;
    { std::lock_guard<std::mutex> hold(g_settings_lock); set = g_set; }
    int view = g_view.load();
    bool look_view = view == CHASE || view == SHOULDER || view == FIRST;
    Body b = find_body();
    u32 camera = W(G_CAMERA);
    bool steer = look_view && g_view_active.load() && b.have && b.hp > 0 && ok(camera, 0x180) && W(camera + CAM_MODE) == 1;

    // the mouse's buttons are buttons of the pad in a look view (the masks are the game's own table)
    u32 mouse = set.mouse_buttons && look_view ? g_mouse_held.load() : 0;
    u16 attack = swap_bytes(W(G_BTN_ATTACK + (u32)std::max(0, b.slot) * 4)), block = swap_bytes(W(G_BTN_BLOCK + (u32)std::max(0, b.slot) * 4));
    u16 use = swap_bytes(W(G_BTN_USE + (u32)std::max(0, b.slot) * 4)), swap_set = swap_bytes(W(G_BTN_SWAP + (u32)std::max(0, b.slot) * 4));
    u16 ability = swap_bytes(W(G_BTN_ABILITY_A + (u32)std::max(0, b.slot) * 4)) | swap_bytes(W(G_BTN_ABILITY_B + (u32)std::max(0, b.slot) * 4));
    if (!attack) attack = rta::PAD_CROSS;
    if (!block) block = rta::PAD_R1;
    if (!use) use = rta::PAD_SQUARE;
    if (!swap_set) swap_set = rta::PAD_L1;
    if (mouse & 1) state.buttons |= attack;
    if (mouse & 2) state.buttons |= block;
    if (mouse & 4) state.buttons |= use;
    // the souls-style combat mode: mouse button 4 is the dodge (L3), button 5 and R3 (Tab) the lock-on
    bool souls = g_souls.load();
    bool lock_asked = g_lock_toggle.exchange(0) != 0;
    if (souls) {
        if (mouse & 8) state.buttons |= rta::PAD_L3;
        bool r3 = (state.buttons & rta::PAD_R3) || (mouse & 16);
        if (r3 && !g_lock_r3) lock_asked = true;
        g_lock_r3 = r3;
        if (look_view) state.buttons &= (u16)~rta::PAD_R3;     // the map stays shut: R3 is the lock
    } else g_lock_object = 0;
    if (lock_asked && souls && look_view) {
        if (g_lock_object) g_lock_object = 0;
        else {
            // the enemy nearest the middle of the picture, distance counting a little
            float best = 1e9f;
            for (int k = 0; k < g_hud.foe_count; k++) {
                const Threat& t = g_hud.foes[k];
                float score = std::fabs(t.bearing) + t.distance / 20.0f + (std::fabs(t.bearing) > 70.0f ? 400.0f : 0.0f);
                if (score < best) { best = score; g_lock_object = t.object; }
            }
        }
    }
    if (!look_view) g_lock_object = 0;
    float wheel = g_wheel.exchange(0);
    if (look_view && set.mouse_buttons && std::fabs(wheel) >= 0.5f && g_inject_left == 0) { g_inject_buttons = swap_set; g_inject_left = 3; }

    // The strafe mode, when the game has the section (app/fp-proposed.pnach): on while a view that faces the look is
    // steered, off otherwise - also while the game's own camera has the frame (cutscene, dialogue, menu, death).  The
    // byte itself is simulation state: it is set on every machine by game message 4, which the application sends
    // through the section's sender when take_strafe_send() says so (offline the same call runs the handler at once).
    // Asked again after half a second while the byte is not what is wanted: a new character (level change, respawn)
    // starts with it clear on every machine.  Only the prediction copy of a net game, which no other machine has,
    // is given the simulated player's byte here.
    bool have_strafe = set.strafe != 0 && W(STRAFE_HOOK) == STRAFE_HOOK_WORD;
    bool strafe_view = set.strafe == 2 ? look_view : look_view && set.face[view];
    int strafe_wanted = have_strafe && steer && (strafe_view || (souls && g_lock_object)) ? 1 : 0;
    g_strafe_wanted = W(STRAFE_HOOK) == STRAFE_HOOK_WORD ? strafe_wanted : -1;
    g_strafing = false;
    if (W(STRAFE_HOOK) == STRAFE_HOOK_WORD && b.real && ok(b.real + P_STRAFE, 1)) {
        int actual = B(b.real + P_STRAFE) != 0;
        if (actual != strafe_wanted && (g_strafe_asked_for != strafe_wanted || blank >= g_strafe_asked_at + 30)) {
            g_strafe_send = strafe_wanted;
            g_strafe_asked_for = strafe_wanted;
            g_strafe_asked_at = blank;
            g_strafe_sends++;
        } else if (actual == strafe_wanted) g_strafe_asked_for = -1;
        if (b.net && b.object != b.real && ok(b.object + P_STRAFE, 1)) *at(b.object + P_STRAFE) = B(b.real + P_STRAFE);
        g_strafing = B(b.object + P_STRAFE) != 0;
    }
    if (!steer) {
        if (g_look_on) { g_look_on = false; g_align_left = 0; g_stick_yaw_now = g_stick_pitch_now = 0; }
        g_pointer = false;
        g_mouse_dx = 0; g_mouse_dy = 0;
        if (g_inject_left > 0) { state.buttons |= g_inject_buttons; g_inject_left--; }
        g_prev_in = state.buttons;
        update_hud(blank, b, false, T_UP - (s16)H(camera + CAM_YAW), 35.0f);
        return;
    }
    g_blanks_steered++;
    g_pointer = set.capture;
    if (!g_look_on) {
        g_look_on = true;
        g_look_units = (double)(s16)H(camera + CAM_YAW);
        g_stick_yaw_now = g_stick_pitch_now = 0;
        g_mouse_carry_x = g_mouse_carry_y = 0;
        g_mouse_dx = 0; g_mouse_dy = 0;
    }

    // ---- look ----
    const float dt = 1.0f / 60.0f;
    float mx = g_mouse_dx.exchange(0), my = g_mouse_dy.exchange(0);
    if (set.mouse_smoothing > 0) {
        float k = clampf(set.mouse_smoothing, 0, 0.95f);
        mx = g_mouse_carry_x = g_mouse_carry_x * k + mx * (1 - k);
        my = g_mouse_carry_y = g_mouse_carry_y * k + my * (1 - k);
    }
    float turn = mx * set.mouse_sensitivity;                                                // degrees to the right
    float pitch = -my * set.mouse_sensitivity * set.mouse_pitch_scale * (set.invert_y ? -1.0f : 1.0f);    // degrees up
    float rx = clampf(((float)state.rx - 128.0f) / 127.0f, -1, 1), ry = clampf(((float)state.ry - 128.0f) / 127.0f, -1, 1);
    float rm = std::sqrt(rx * rx + ry * ry);
    float want_yaw = 0, want_pitch = 0;
    if (rm > set.stick_deadzone) {
        float m = clampf((rm - set.stick_deadzone) / (1.0f - set.stick_deadzone), 0, 1);
        float gain = std::pow(m, set.stick_curve) / rm;
        want_yaw = rx * gain * set.stick_yaw;
        want_pitch = -ry * gain * set.stick_pitch * (set.invert_stick_y ? -1.0f : 1.0f);    // a byte below 128 is "up"
    }
    float ease = set.stick_ease > dt ? dt / set.stick_ease : 1.0f;
    g_stick_yaw_now += (want_yaw - g_stick_yaw_now) * ease;
    g_stick_pitch_now += (want_pitch - g_stick_pitch_now) * ease;
    if (std::fabs(g_stick_yaw_now) < 0.01f && want_yaw == 0) g_stick_yaw_now = 0;
    if (std::fabs(g_stick_pitch_now) < 0.01f && want_pitch == 0) g_stick_pitch_now = 0;
    turn += g_stick_yaw_now * dt;
    pitch += g_stick_pitch_now * dt;
    if (pitch != 0) add(g_pitch_out, pitch);
    // The simulation picks its own target for a swing or a shot (inside 60 degrees of the facing) and turns the
    // character to it; a view that kept looking where it looked would have the fight beside the picture.  While
    // a swing or shot holds a target, the look comes round to it: a quarter of what is left a tick, bounded, and
    // only as far as `swing_turn_within` of the middle.  It is the yaw word that turns - input like any other.
    if (set.swing_turn > 0 && set.face[view] && (b.state == 1 || (b.state == 0 && !g_aim.load())) && g_hud.locked.valid && g_hud.blank + 1 == blank) {
        float off = g_hud.locked.bearing, excess = std::fabs(off) - set.swing_turn_within;
        if (excess > 0) { turn += (off > 0 ? 1.0f : -1.0f) * std::min(excess * 0.25f, set.swing_turn); g_assist_blanks++; }
    }
    // the souls mode's lock-on: the look comes round to the target by itself; a flick changes target
    if (souls && g_lock_object && g_hud.lock.valid && g_hud.lock.object == g_lock_object) {
        int side = 0;
        if (std::fabs(mx * set.mouse_sensitivity) >= set.lock_flick) side = mx > 0 ? 1 : -1;
        int stick_side = rx > 0.85f ? 1 : rx < -0.85f ? -1 : 0;
        if (stick_side != 0 && g_lock_flick_side == 0) side = stick_side;
        g_lock_flick_side = std::fabs(rx) > 0.5f ? (stick_side ? stick_side : g_lock_flick_side) : 0;
        if (side != 0) {
            // the next enemy on that side: the smallest bearing beyond the target's own
            float now = g_hud.lock.bearing, best = 1e9f;
            u32 pick = 0;
            for (int k = 0; k < g_hud.foe_count; k++) {
                const Threat& t = g_hud.foes[k];
                if (t.object == g_lock_object) continue;
                float rel = wrap_deg(t.bearing - now) * (float)side;
                if (rel > 0.5f && rel < best) { best = rel; pick = t.object; }
            }
            if (pick) { g_lock_object = pick; g_hud.lock_switches++; }
        }
        float off = g_hud.lock.bearing;
        turn = clampf(off * set.lock_turn, -set.lock_turn_max, set.lock_turn_max);
    }
    // a growing yaw word turns the camera clockwise seen from above: to the right
    g_look_units += (double)turn * UNITS;
    while (g_look_units >= 32768.0) g_look_units -= 65536.0;
    while (g_look_units < -32768.0) g_look_units += 65536.0;
    // bit 0 of the word is the "camera is not following" flag on the wire: the angle is kept even
    s16 yaw_word = (s16)(((int)std::lround(g_look_units)) & ~1);
    put16(camera + CAM_YAW, (u16)yaw_word);
    put32(camera + CAM_YAW_VELOCITY, 0);
    // the game's own camera stick code is held at rest: it would turn the same word (slowly) and step the zoom
    state.rx = state.ry = 128;
    if (!souls) state.buttons &= (u16)~rta::PAD_L3;         // "camera behind the character" would turn the word as well (the souls mode: L3 is the dodge, and the camera stick code is held at rest anyway)

    // ---- move ----
    u16 in_buttons = state.buttons;
    u16 pressed = (u16)(in_buttons & ~g_prev_in);
    g_prev_in = in_buttons;
    float ux = clampf(((float)state.lx - 128.0f) / 127.0f, -1, 1), uy = clampf(((float)state.ly - 128.0f) / 127.0f, -1, 1);
    float um = std::sqrt(ux * ux + uy * uy);
    auto digital = [](u8 v) { return v == 0 || v == 128 || v == 255; };
    if (!(digital(state.lx) && digital(state.ly))) {
        // an analog stick: its own small dead zone, then the whole of the game's range past the game's dead zone,
        // so that a light push walks instead of doing nothing until a third of the way out
        if (um <= set.move_deadzone) { um = 0; state.lx = state.ly = 128; }
        else {
            float m = 0.345f + clampf((um - set.move_deadzone) / (1.0f - set.move_deadzone), 0, 1) * (1.0f - 0.345f);
            state.lx = stick_byte(ux / um * m);
            state.ly = stick_byte(uy / um * m);
            um = m;
        }
    }
    bool moving = um > 0.33f;

    // ---- face ----
    int heading = T_UP - yaw_word;                       // what a pushed-up stick turns the character to
    // In a net game the simulation steers by the yaw word as the wire's codec approximates it (within about a
    // degree; g_netCamYaw holds this machine's own after the prediction of the last blank): the character is
    // turned to that, or the turning push would never be satisfied.  The picture keeps the exact word.
    int steered = b.net ? T_UP - (s16)H(G_NET_CAM_YAW + (u32)b.slot * 2) : heading;
    if (b.net && std::abs((int)wrap16(steered - heading)) > 0x300) steered = heading;        // the look is turning fast: the word in the table is an old one
    int error = wrap16(steered - b.facing);
    float error_deg = std::fabs((float)error / UNITS);
    bool aligning = false;
    if (set.face[view]) {
        u16 strike = attack | ability;
        int nudge = nudge_length(b);
        enum { PASS, NUDGE, UP_HALF, UP_FULL, REST } stick = PASS;
        float up_length = 0.5f;
        if (g_strafing) {
            // the simulation itself keeps the character on the look in the neutral state: nothing to turn, nothing to hold back
            g_align_left = 0;
            g_idle_turning = false;
        } else if (g_align_left > 0) {
            if (b.state != 2 || error_deg <= set.strike_within || --g_align_left == 0) {
                // turned (or out of time, or the game has put the character into another state): the press goes through
                g_align_left = 0;
                if (!(in_buttons & g_align_buttons)) { g_inject_buttons = g_align_buttons; g_inject_left = 2; g_released_late++; }
            } else aligning = true;
        } else if (b.state == 2 && set.turn_before_strike && (pressed & strike) && error_deg > set.strike_within) {
            g_align_buttons = pressed & strike;
            g_align_left = std::max(1, set.strike_wait);
            g_held_back++;
            aligning = true;
        }
        switch (b.state) {
        case 2:
            if (g_strafing) stick = PASS;
            else if (aligning) stick = NUDGE;
            else if (moving) { stick = PASS; g_idle_turning = false; }
            else {
                // standing: turned once it is `idle_within` off, until it is there.  In a net game "there" moves: the
                // wire's yaw wanders up to 1.1 degrees round the true one even while the camera stands still (the codec
                // keeps a small delta until it is 200 units off), so the turn starts later and ends sooner
                float start = b.net ? std::max(3.0f, set.idle_within) : set.idle_within, stop = b.net ? 1.0f : std::min(0.1f, set.idle_within);
                if (!g_idle_turning && error_deg > start) g_idle_turning = true;
                else if (g_idle_turning && error_deg <= stop) g_idle_turning = false;
                stick = g_idle_turning ? NUDGE : REST;
            }
            break;
        case 1: {
            // the wind-up turns 5 % of the angle a tick toward the stick, whatever its length; afterwards the stick
            // does nothing but end the swing early when it is pushed past 0.8, which is left to the player
            bool heavy = W(b.object + P_ATTACK_REQUEST) == 2;
            if ((float)b.since <= (heavy ? 0.567f : 0.433f) * 60.0f) {
                if (moving) { stick = UP_HALF; up_length = um; }
                else stick = error_deg > set.idle_within ? UP_HALF : REST;
            }
            break;
        }
        case 0: case 5: case 8: case 0xb:
            // drawing a bow, casting, blocking: the stick only turns the character; it turns to the look
            stick = error_deg > set.idle_within ? UP_FULL : REST;
            g_turn_states++;
            break;
        default: break;
        }
        if (aligning) { state.buttons &= (u16)~g_align_buttons; g_held_ticks++; }
        switch (stick) {
        case NUDGE: state.lx = 128; state.ly = (u8)(128 - nudge); g_nudges++; break;
        case UP_HALF: state.lx = 128; state.ly = stick_byte(-clampf(up_length, 0.4f, 1.0f)); break;
        case UP_FULL: state.lx = 128; state.ly = 0; break;
        case REST: state.lx = state.ly = 128; break;
        case PASS: break;
        }
    }
    if (g_inject_left > 0 && !aligning) { state.buttons |= g_inject_buttons; g_inject_left--; }

    // the kick decays (a tenth of it is left after 12 blanks)
    g_kick_pitch *= 0.825f; g_kick_roll *= 0.825f;
    if (std::fabs(g_kick_pitch) < 0.01f) g_kick_pitch = 0;
    if (std::fabs(g_kick_roll) < 0.01f) g_kick_roll = 0;

    update_hud(blank, b, true, heading, view == FIRST ? 46.0f : 40.0f);
    g_hud.aligning = aligning;
    // What is struck in first person is often at the player's feet, under the picture: while a swing has a target,
    // the view tips until the target's middle is within 12 degrees of the picture's (the picture's only; pitch is
    // not part of any row)
    if (set.swing_tilt && view == FIRST && b.state == 1 && g_hud.locked.valid) {
        float dx = g_hud.locked.x - b.x, dy = g_hud.locked.y - b.y;
        float want = std::atan2(g_hud.locked.z - (b.z + 60.0f), std::max(8.0f, std::sqrt(dx * dx + dy * dy))) * 180.0f / 3.14159265f;
        float off = want - g_view_pitch.load();
        if (std::fabs(off) > 12.0f) add(g_pitch_out, (off - (off > 0 ? 12.0f : -12.0f)) * 0.12f);
    }
    if (g_log && (blank % 30 == 0 || aligning))
        fprintf(stderr, "fpc: blank %llu tick %u view %d yaw word %d heading %.1f facing %.1f error %.1f state %d stick %u %u buttons %04x%s\n", (unsigned long long)blank,
                g_hud.tick, view, yaw_word, g_hud.look_heading, g_hud.facing, g_hud.facing_error, b.state, state.lx, state.ly, state.buttons, aligning ? " (press held back)" : "");
}

void apply_view(int view, float forward[3], float up[3]) {
    Settings set;
    { std::lock_guard<std::mutex> hold(g_settings_lock); set = g_set; }
    auto turn_z = [](float v[3], float degrees) {
        float c = std::cos(degrees * 3.14159265f / 180.0f), s = std::sin(degrees * 3.14159265f / 180.0f);
        float x = v[0] * c - v[1] * s, y = v[0] * s + v[1] * c;
        v[0] = x; v[1] = y;
    };
    auto turn_about = [](float v[3], const float axis[3], float degrees) {      // Rodrigues
        float c = std::cos(degrees * 3.14159265f / 180.0f), s = std::sin(degrees * 3.14159265f / 180.0f);
        float d = axis[0] * v[0] + axis[1] * v[1] + axis[2] * v[2];
        float cx = axis[1] * v[2] - axis[2] * v[1], cy = axis[2] * v[0] - axis[0] * v[2], cz = axis[0] * v[1] - axis[1] * v[0];
        v[0] = v[0] * c + cx * s + axis[0] * d * (1 - c);
        v[1] = v[1] * c + cy * s + axis[1] * d * (1 - c);
        v[2] = v[2] * c + cz * s + axis[2] * d * (1 - c);
    };
    if (view == FIRST && set.centre) {
        // the game camera looks 0x1c3 angle units to the left of where a pushed-up stick walks
        float degrees = -(float)VIEW_OFFSET / UNITS;
        turn_z(forward, degrees);
        turn_z(up, degrees);
    }
    if ((view == FIRST || view == SHOULDER) && set.kick > 0 && (g_kick_pitch != 0 || g_kick_roll != 0)) {
        float scale = set.kick * (view == FIRST ? 1.0f : 0.5f);
        float right[3] = {forward[1] * up[2] - forward[2] * up[1], forward[2] * up[0] - forward[0] * up[2], forward[0] * up[1] - forward[1] * up[0]};
        float length = std::sqrt(right[0] * right[0] + right[1] * right[1] + right[2] * right[2]);
        if (length > 0.001f) {
            for (float& r : right) r /= length;
            float f0[3] = {forward[0], forward[1], forward[2]};
            turn_about(forward, right, g_kick_pitch * scale);
            turn_about(up, right, g_kick_pitch * scale);
            turn_about(up, f0, g_kick_roll * scale);
        }
    }
}

// ---- settings -----------------------------------------------------------------------------------
bool setting(const char* key, const char* value) {
    if (strncmp(key, "controls.", 9) != 0) return false;
    std::string name = key + 9, text = value;
    float number = (float)atof(value);
    bool yes = text == "yes" || text == "on" || text == "1" || text == "true";
    std::lock_guard<std::mutex> hold(g_settings_lock);
    Settings& s = g_set;
    static const char* const views[VIEW_COUNT] = {"overhead", "action", "chase", "shoulder", "first"};
    if (name == "mouse_sensitivity") s.mouse_sensitivity = clampf(number, 0.005f, 2.0f);
    else if (name == "mouse_pitch_scale") s.mouse_pitch_scale = clampf(number, 0.1f, 4.0f);
    else if (name == "mouse_smoothing") s.mouse_smoothing = clampf(number, 0, 0.95f);
    else if (name == "invert_y") s.invert_y = yes;
    else if (name == "invert_stick_y") s.invert_stick_y = yes;
    else if (name == "stick_yaw") s.stick_yaw = clampf(number, 20, 720);
    else if (name == "stick_pitch") s.stick_pitch = clampf(number, 10, 720);
    else if (name == "stick_deadzone") s.stick_deadzone = clampf(number, 0, 0.6f);
    else if (name == "stick_curve") s.stick_curve = clampf(number, 1, 4);
    else if (name == "stick_ease") s.stick_ease = clampf(number, 0, 0.5f);
    else if (name == "move_deadzone") s.move_deadzone = clampf(number, 0, 0.6f);
    else if (name == "turn_before_strike") s.turn_before_strike = yes;
    else if (name == "strike_wait") s.strike_wait = (int)clampf(number, 1, 30);
    else if (name == "strike_within") s.strike_within = clampf(number, 1, 90);
    else if (name == "idle_within") s.idle_within = clampf(number, 0.2f, 45);
    else if (name == "mouse_buttons") s.mouse_buttons = yes;
    else if (name == "capture_pointer") s.capture = yes;
    else if (name == "kick") s.kick = clampf(number, 0, 4);
    else if (name == "centre") s.centre = yes;
    else if (name == "swing_tilt") s.swing_tilt = yes;
    else if (name == "swing_turn") s.swing_turn = clampf(number, 0, 30);
    else if (name == "swing_turn_within") s.swing_turn_within = clampf(number, 0, 45);
    else if (name == "lock_range") s.lock_range = clampf(number, 100, 2000);
    else if (name == "lock_turn") s.lock_turn = clampf(number, 0.02f, 1.0f);
    else if (name == "lock_turn_max") s.lock_turn_max = clampf(number, 0.5f, 45);
    else if (name == "lock_flick") s.lock_flick = clampf(number, 1, 60);
    else if (name == "strafe") s.strafe = text == "on" ? 2 : (text == "auto" || yes) ? 1 : 0;
    else if (name.compare(0, 5, "face.") == 0) {
        for (int v = 0; v < VIEW_COUNT; v++) if (name.substr(5) == views[v]) { s.face[v] = yes && v >= CHASE; return true; }
        return false;
    } else return false;
    return true;
}

std::string settings_text() {
    Settings s;
    { std::lock_guard<std::mutex> hold(g_settings_lock); s = g_set; }
    auto yes = [](bool b) { return b ? "yes" : "no"; };
    char text[3600];
    snprintf(text, sizeof text,
             "# controls of the views that look along the ground (chase, shoulder, first person)\n"
             "controls.mouse_sensitivity = %g     # degrees of turn for one count of the mouse\n"
             "controls.mouse_pitch_scale = %g       # up and down against left and right\n"
             "controls.mouse_smoothing = %g         # 0 (none) to 0.9\n"
             "controls.invert_y = %s               # mouse: pushing away looks down\n"
             "controls.invert_stick_y = %s         # right stick: up looks down\n"
             "controls.stick_yaw = %g             # right stick: degrees a second at full push, left and right\n"
             "controls.stick_pitch = %g           # ... up and down\n"
             "controls.stick_deadzone = %g       # right stick: nothing happens inside this\n"
             "controls.stick_curve = %g           # right stick: 1 = even, higher = finer near the centre\n"
             "controls.stick_ease = %g           # right stick: seconds over which a new position takes hold\n"
             "controls.move_deadzone = %g        # left stick in these views: a push beyond this walks\n"
             "controls.face.chase = %s             # the character turns to where the view looks (else it faces where it runs)\n"
             "controls.face.shoulder = %s\n"
             "controls.face.first = %s\n"
             "controls.turn_before_strike = %s    # a strike or cast pressed while the character faces away waits until it has turned\n"
             "controls.strike_wait = %d            # ... for at most this many ticks (60 a second)\n"
             "controls.strike_within = %g         # ... or until it is within this many degrees\n"
             "controls.idle_within = %g            # a standing character is turned once it is this many degrees off the look\n"
             "controls.mouse_buttons = %s         # left: attack, right: block, middle: use, wheel: other weapon set\n"
             "controls.capture_pointer = %s       # the pointer is hidden and held while one of these views is played\n"
             "controls.kick = %g                   # how much a swing or a hit moves the view (0 = not at all)\n"
             "controls.centre = %s                # first person: the middle of the picture is where forward walks and arrows fly\n"
             "controls.swing_tilt = %s            # first person: during a swing the view tips toward a target under or over the picture\n"
             "controls.swing_turn = %g             # during a swing or shot the look comes round to the target the game took: degrees a tick at most (0 = never)\n"
             "controls.swing_turn_within = %g      # ... until the target is this many degrees from the middle of the picture\n"
             "controls.strafe = %s                # needs the strafe section in the game: auto (first person and shoulder run sideways and backwards facing the look), on (chase too), off\n",
             s.mouse_sensitivity, s.mouse_pitch_scale, s.mouse_smoothing, yes(s.invert_y), yes(s.invert_stick_y), s.stick_yaw, s.stick_pitch, s.stick_deadzone,
             s.stick_curve, s.stick_ease, s.move_deadzone, yes(s.face[CHASE]), yes(s.face[SHOULDER]), yes(s.face[FIRST]), yes(s.turn_before_strike), s.strike_wait,
             s.strike_within, s.idle_within, yes(s.mouse_buttons), yes(s.capture), s.kick, yes(s.centre), yes(s.swing_tilt), s.swing_turn, s.swing_turn_within, s.strafe == 2 ? "on" : s.strafe == 1 ? "auto" : "off");
    return text;
}

std::string help_text() {
    return "In the chase, shoulder and first-person views (V changes the view):\n"
           "\n"
           "  Look                  the mouse, or the right stick\n"
           "  Move                  W A S D, or the left stick: forward is where you look\n"
           "  Attack / shoot        left mouse button (Cross, K)\n"
           "  Block                 right mouse button (R1, E, Shift)\n"
           "  Use, talk, pick up    middle mouse button (Square, J, Space)\n"
           "  Other weapon set      mouse wheel (L1, Q)\n"
           "  Map                   Tab (R3, C)\n"
           "  Give the pointer back Escape (a click in the window takes it again)\n"
           "\n"
           "The character turns to where you look when it stands, strikes, shoots, casts\n"
           "or blocks; running sideways or backwards it runs that way, as it always did.\n"
           "Sensitivity, inverted look and the rest: the controls.* lines of settings.txt.";
}

std::string hud_text() {
    const Hud& h = g_hud;
    char text[2400];
    int n = snprintf(text, sizeof text,
                     "tick=%u view=%d look=%d playing=%d slot=%d pos=%.1f,%.1f,%.1f heading=%.2f facing=%.2f error=%.2f pitch=%.1f state=%d weapon=%d aligning=%d reticle=%d "
                     "melee=%x@%.0f/%.0f shot=%x@%.0f/%.0f locked=%x usable=%d kind=%d fade=%d usable_obj=%x usable_bearing=%.0f text=\"%s\" threats=%d behind=%d "
                     "swings=%u hits_dealt=%u hits_taken=%u deaths=%u respawns=%u strafing=%d",
                     h.tick, h.view, h.look, h.playing, h.slot, h.x, h.y, h.z, h.look_heading, h.facing, h.facing_error, h.look_pitch, h.state, h.weapon_class, h.aligning,
                     h.reticle, h.melee.valid ? h.melee.object : 0, h.melee.distance, h.melee.bearing, h.shot.valid ? h.shot.object : 0, h.shot.distance, h.shot.bearing,
                     h.locked.valid ? h.locked.object : 0, h.usable, h.usable_kind, h.usable_fade, h.usable_object, h.usable_bearing, h.usable_text, h.threat_count, h.behind,
                     h.swings, h.hits_dealt, h.hits_taken, h.deaths, h.respawns, (int)g_strafing);
    for (int k = 0; k < h.threat_count && k < 6 && n < (int)sizeof text - 80; k++)
        n += snprintf(text + n, sizeof text - (size_t)n, " threat%d=%x,%.0f,%.0f,%s%s%s", k, h.threats[k].object, h.threats[k].distance, h.threats[k].bearing,
                      h.threats[k].targets_me ? "T" : "-", h.threats[k].attacking ? "A" : "-", h.threats[k].in_view ? "V" : "-");
    return text;
}

std::string command(const std::string& text, uint64_t blank) {
    (void)blank;
    char a[64] = "", b[64] = "", c[64] = "";
    int n = sscanf(text.c_str(), "%63s %63s %63s", a, b, c);
    std::string what = a;
    if (what == "mouse" && n >= 3) { mouse_motion((float)atof(b), (float)atof(c)); return "ok"; }
    if (what == "button" && n >= 3) {
        std::string name = b;
        int button = name == "left" ? 0 : name == "right" ? 1 : name == "middle" ? 2 : atoi(b);
        mouse_button(button, std::string(c) == "down");
        return "ok";
    }
    if (what == "wheel" && n >= 2) { mouse_wheel((float)atof(b)); return "ok"; }
    if (what == "set" && n >= 3) return setting((std::string("controls.") + b).c_str(), c) ? "ok" : "not a controls setting: " + std::string(b);
    if (what == "log" && n >= 2) { g_log = std::string(b) == "on"; return "ok"; }
    if (what == "hud" || what == "info") return hud_text();
    if (what == "figures") return figures();
    return "unknown: " + text;
}

std::string figures() {
    char text[640];
    snprintf(text, sizeof text, "controls: %llu blanks steered in a look view, the turning push given at %llu, %llu presses held back for %llu ticks in all (%llu let through after "
             "the button was up again), %llu blanks in a state where the stick only turns, the look brought round to a target in %llu, the strafe mode asked for %llu times",
             (unsigned long long)g_blanks_steered, (unsigned long long)g_nudges, (unsigned long long)g_held_back, (unsigned long long)g_held_ticks, (unsigned long long)g_released_late,
             (unsigned long long)g_turn_states, (unsigned long long)g_assist_blanks, (unsigned long long)g_strafe_sends);
    return text;
}

void set_souls(bool on) { g_souls = on; }
void set_aim(bool on) { g_aim = on; }
void lock_toggle() { g_lock_toggle = 1; }

uint16_t mouse_buttons_as_pad() {
    u32 mouse = g_mouse_held.load();
    return (uint16_t)((mouse & 1 ? rta::PAD_CROSS : 0) | (mouse & 2 ? rta::PAD_R1 : 0) | (mouse & 4 ? rta::PAD_SQUARE : 0));
}

}  // namespace fpcontrols
