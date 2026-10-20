// soulscombat.cpp - the souls-style combat mode (soulscombat.h; docs/issues/native-souls-combat.md).
#include "soulscombat.h"
#include "fpcontrols.h"
#include "rt.h"
#include "backend.h"
#include "../net2/hooks.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iterator>
#include <mutex>
#include <unordered_map>

namespace soulscombat {
namespace {

// ---- the game (addresses and offsets: docs/player.md, docs/spec/player-tick.md, docs/creatures.md) ----
const u32 PLAYER_RUN = 0x1a5030, PLAYER_TAKE_DAMAGE = 0x1b5330, CREATURE_TAKE_DAMAGE = 0x116638;
const u32 MATH_ATAN2_16 = 0x166798, NET_GET_CAM_YAW = 0x13e0c8, ANIM_START_BLEND_IN_OUT = 0x16ceb0, CREATURE_BOSS_RANK = 0x10d940;
const u32 G_PLAYERS = 0x4d8af0, REC = 0x4c30, REC_OBJECT = 0x43d8, REC_HP = 0xac, REC_HP_MAX = 0xb0, REC_SPEED = 0x4c20, REC_WEAPON_CLASS = 0x4a86;
const u32 G_PADS = 0x41bfd8, PAD = 0x58, PAD_HELD = 8, PAD_PRESSED = 0xc, PAD_LX = 0x14, PAD_LY = 0x18;
const u32 G_BTN_ATTACK = 0x41b980, G_BTN_BLOCK = 0x41b9d0;
const u32 G_SIM_FRAME = 0x44fdcc, G_NETWORK_MODE = 0x402791, G_LEVEL_FLAGS = 0x44fe08, G_LEVEL_NAME = 0x41b721;
const u32 VT_PLAYER = 0x511308;
const u32 O_FLAGS = 0x0c, O_FACING = 0x38, O_VTABLE = 0x48, O_ANIM = 0x114, O_TRACKS = 0x118, O_TRACKS2 = 0x119, O_ANIM_TABLE = 0x24;
const u32 C_HP = 0x228, C_INERT = 0x231, C_PENDING = 0xc8, C_PENDING_FLAGS = 0x2dc, C_TURN_RATE = 0xb0;
const u32 P_SLOT = 0x3c8, P_ACTION_START = 0x448, P_ATTACK_REQUEST = 0x44c, P_COMBO = 0x460, P_ATTACK_LENGTH = 0x470, P_BLEND = 0x46c;
const u32 P_BLOCKING = 0x47f, P_STICK_IGNORED = 0x481, P_ON_GROUND = 0x482, P_STATE = 0x58c;
const u32 FLAG_COPY = 0x20000;          // the prediction copy
const u32 PEND_STAGGER = 0x4000000;     // pending-damage flag that makes Player_processDamage stagger
const u32 HIT_UNBLOCKABLE = 0x40;       // damage flag: Player_takeDamage does not block it
const u32 L3 = 0x200;                   // the row's L3 bit (the held word of g_pads)
const u32 F_ONE_TENTH = 0x3dcccccc, F_POINT_3 = 0x3e999999, F_2_8 = 0x40333333, F_HEAVY_LENGTH = 0x3f5b645a;

bool ok(u32 a, u32 size = 4) { a &= 0x1FFFFFFF; return a >= 0x80000 && a <= RAM_SIZE - size; }
u32 W(u32 a) { u32 v = 0; if (ok(a)) memcpy(&v, g_ram + (a & 0x1FFFFFFF), 4); return v; }
u16 H(u32 a) { u16 v = 0; if (ok(a, 2)) memcpy(&v, g_ram + (a & 0x1FFFFFFF), 2); return v; }
u8 B(u32 a) { return ok(a, 1) ? g_ram[a & 0x1FFFFFFF] : 0; }
float F(u32 a) { float v = 0; if (ok(a)) memcpy(&v, g_ram + (a & 0x1FFFFFFF), 4); return v; }
void PW(u32 a, u32 v) { if (ok(a)) memcpy(g_ram + (a & 0x1FFFFFFF), &v, 4); }
void PH(u32 a, u16 v) { if (ok(a, 2)) memcpy(g_ram + (a & 0x1FFFFFFF), &v, 2); }
void PB(u32 a, u8 v) { if (ok(a, 1)) g_ram[a & 0x1FFFFFFF] = v; }
void PF(u32 a, float v) { u32 b; memcpy(&b, &v, 4); PW(a, b); }
u32 bits(float v) { u32 b; memcpy(&b, &v, 4); return b; }
float flt(u32 b) { float v; memcpy(&v, &b, 4); return v; }
// the block (soulscombat.h)
s32 SR(u32 off) { return (s32)W(SOULS_BASE + off); }
void SW(u32 off, s32 v) { PW(SOULS_BASE + off, (u32)v); }
u32 slot_off(int slot, u32 field) { return 0x40 + (u32)slot * 0x40 + field; }
enum : u32 { S_STAMINA = 0, S_DELAY = 4, S_FLAGS = 8, S_DODGE = 0xc, S_COOL = 0x10, S_ATK = 0x14, S_L3 = 0x18, S_BROKEN = 0x1c,
             S_LAST_STATE = 0x20, S_LAST_COMBO = 0x24, S_DODGES = 0x28, S_HEAVIES = 0x2c, S_LIGHTS = 0x30, S_REFUSED = 0x34,
             S_AVOIDED = 0x38, S_BLOCKS = 0x3c };
enum : u32 { H_MAGIC = 0, H_VERSION = 4, H_MODE = 8, H_UPDATES = 0xc, H_BREAKS = 0x10, H_POISE = 0x14, H_AVOIDED = 0x18, H_BLOCKS = 0x1c,
             L_LOCK = 0x180, L_OBJECT = 0x184, L_X = 0x188, L_Y = 0x18c, L_Z = 0x190, L_HP = 0x194, L_HP_MAX = 0x198 };

// ---- state ----
Tuning g_tuning;
std::mutex g_lock;                      // the tuning and the camera against other threads
std::atomic<bool> g_want{false};
std::atomic<int> g_room{-1};            // -1 no room game; 0 / 1 the launched game's mode
int g_last_room = -1;
bool g_on = false;                      // in force (game thread)
bool g_installed = false;
RecompFn g_orig_run = nullptr, g_orig_ptd = nullptr, g_orig_ctd = nullptr;
u32 g_last_object[4] = {0, 0, 0, 0};    // per machine: which object the slot's numbers belong to
char g_level[16] = "";
struct Ghost { s32 atk = 0, l3 = 0, dodge = -1; u32 object = 0; } g_ghost;   // the prediction copy's own presses (picture only)
struct Poise { s32 poise = 0; u32 last = 0; };
std::unordered_map<u32, Poise> g_poise; // by creature object (soulscombat.h)
// presentation
Camera g_camera;
struct Shown { bool valid = false; int slot = -1; float stamina = 1, max = 1; u32 flags = 0; bool lock = false; float x = 0, y = 0, z = 0, hp = 0, hp_max = 0; } g_shown;
// counters (per machine)
uint64_t g_runs = 0, g_ptd_calls = 0, g_ctd_calls = 0, g_staggers = 0, g_iframe_skips = 0;

u32 frame_now() { return W(G_SIM_FRAME); }

// A game function called the way its own code calls it, on the context that is running (its registers put
// back afterwards); returns v0.
u32 call(Ctx* c, u32 address, u32 a0, u32 a1 = 0, u32 a2 = 0, u32 f12 = 0, u32 f13 = 0) {
    Ctx saved = *c;
    c->r[29] = (u64)(s64)(s32)((((u32)saved.r[29]) - 0x600) & ~15u);
    c->r[4] = (u64)(s64)(s32)a0; c->r[5] = (u64)(s64)(s32)a1; c->r[6] = (u64)(s64)(s32)a2;
    c->f[12] = f12; c->f[13] = f13;
    rt_call(c, address);
    u32 v = (u32)c->r[2];
    s64 budget = c->budget;
    *c = saved;
    c->budget = budget;
    return v;
}

void charge(int slot, s32 amount) {
    s32 st = SR(slot_off(slot, S_STAMINA)) - amount;
    SW(slot_off(slot, S_STAMINA), st < 0 ? 0 : st);
    SW(slot_off(slot, S_DELAY), g_tuning.regen_delay);
}

void reset_slot(int slot) {
    for (u32 f = 0; f < 0x28; f += 4) SW(slot_off(slot, f), 0);
    SW(slot_off(slot, S_STAMINA), g_tuning.stamina_max);
    SW(slot_off(slot, S_DODGE), -1);
    SW(slot_off(slot, S_LAST_STATE), -1);
}

void reset_all() {
    for (u32 a = 0; a < 0x200; a += 4) PW(SOULS_BASE + a, 0);
    SW(H_MAGIC, (s32)SOULS_MAGIC);
    SW(H_VERSION, 1);
    for (int k = 0; k < 4; k++) { reset_slot(k); g_last_object[k] = 0; }
    g_poise.clear();
    g_ghost = Ghost();
}

bool level_changed() {
    char now[16];
    memcpy(now, g_ram + G_LEVEL_NAME, 15);
    now[15] = 0;
    if (strncmp(now, g_level, 15) == 0) return false;
    memcpy(g_level, now, 16);
    return true;
}

// The game's heavy attack (Player_run state 2, older ability 0x25 at 0x1a71f8-0x1a7310) started for a player,
// as the game starts it - without the ability, its mana and its light effect: state 1 with request 2, which is
// also the game's own hyper-armour (Player_processDamage does not stagger a player whose request is 2).
bool start_heavy(Ctx* c, u32 P, int cls) {
    u32 table = W(P + O_ANIM_TABLE);
    u32 clip = table ? W(table + (u32)cls * 0x68 + 0x64) : 0;
    if (!clip) return false;
    PW(P + C_TURN_RATE, F_2_8);
    PW(P + P_ATTACK_LENGTH, F_HEAVY_LENGTH);
    PB(P + P_COMBO, 0);
    PW(P + P_BLEND, 0);
    PW(P + P_ACTION_START, frame_now());
    PW(P + P_ATTACK_REQUEST, 2);
    int tracks = (int8_t)B(P + O_TRACKS2);
    for (int k = 1; k < tracks; k++) { PW(P + 0x144 + (u32)(k - 1) * 0x20, 0); PW(P + 0x14c + (u32)(k - 1) * 0x20, 0); }
    call(c, ANIM_START_BLEND_IN_OUT, P + O_ANIM, clip, 0x812, F_ONE_TENTH, F_ONE_TENTH);
    PW(P + P_STATE, 1);
    return true;
}

// The dodge: the game's own block move (Player_tryBlockMove 0x1bf150: state 0xb, its back-hop clip, the stick
// ignored for 47 ticks) with the character turned so that the hop goes where the stick points.
bool start_dodge(Ctx* c, u32 P, int slot, int cls) {
    u32 table = W(P + O_ANIM_TABLE);
    u32 clip = table ? W(table + (u32)cls * 0x68 + 0xa4) : 0;
    if (!clip) return false;
    u32 pad = G_PADS + (u32)slot * PAD;
    float lx = F(pad + PAD_LX), ly = F(pad + PAD_LY);
    if (lx * lx + ly * ly > 0.09f) {
        s16 stick = (s16)call(c, MATH_ATAN2_16, 0, 0, 0, bits(lx), bits(ly));
        s16 yaw = (s16)call(c, NET_GET_CAM_YAW, (u32)slot);
        s16 heading = (s16)(stick - yaw - 0x41c2);      // where the stick walks (Player_move's target facing)
        PH(P + O_FACING, (u16)(s16)(heading + 0x8000)); // the hop goes backwards
    }
    PW(P + P_STATE, 0xb);
    PB(P + P_STICK_IGNORED, (u8)g_tuning.dodge_stick_ignored);
    PB(P + P_BLOCKING, 1);
    call(c, ANIM_START_BLEND_IN_OUT, P + O_ANIM, clip, 0x808, F_ONE_TENTH, F_POINT_3);
    return true;
}

// ---- Player_run (slot 4) ----------------------------------------------------------------------
void w_player_run(Ctx* c) {
    u32 P = (u32)c->r[4];
    if (!g_on || !ok(P, 0x590)) { g_orig_run(c); return; }
    s32 slot = (s32)W(P + P_SLOT);
    if (slot < 0 || slot > 3) { g_orig_run(c); return; }
    const Tuning& t = g_tuning;
    bool copy = (W(P + O_FLAGS) & FLAG_COPY) != 0;
    u32 record = G_PLAYERS + (u32)slot * REC;
    if (!copy) {
        g_runs++;
        if (level_changed()) g_poise.clear();
        if (g_last_object[slot] != P) { g_last_object[slot] = P; reset_slot(slot); }
        SW(H_UPDATES, SR(H_UPDATES) + 1);
    } else if (g_ghost.object != P) { g_ghost = Ghost(); g_ghost.object = P; }
    s32 stamina = SR(slot_off(slot, S_STAMINA));
    s32 state = (s32)W(P + P_STATE);
    int cls = (int8_t)B(record + REC_WEAPON_CLASS);
    bool ranged = cls == 4 || cls == 6;
    u32 pad = G_PADS + (u32)slot * PAD;
    u32 held = W(pad + PAD_HELD), pressed = W(pad + PAD_PRESSED), nh = held, np = pressed;
    u32 attack = W(G_BTN_ATTACK + (u32)slot * 4) & 0xffff, block = W(G_BTN_BLOCK + (u32)slot * 4) & 0xffff;
    s32 atk = copy ? g_ghost.atk : SR(slot_off(slot, S_ATK)), l3 = copy ? g_ghost.l3 : SR(slot_off(slot, S_L3));
    bool light = false, heavy = false, dodge = false, refused = false;
    // attack: a tap is the game's swing, a hold its heavy attack
    if (attack && !ranged) {
        if (held & attack) {
            atk++;
            nh &= ~attack; np &= ~attack;
            if (atk == t.heavy_hold) heavy = true;
        } else {
            if (atk > 0 && atk < t.heavy_hold) light = true;
            atk = 0;
        }
        if (light) { if (stamina > 0) { nh |= attack; np |= attack; } else { light = false; refused = true; } }
        if (heavy && stamina <= 0) { heavy = false; refused = true; }
    } else if (attack && ranged && state == 2 && stamina <= 0 && (held & attack)) {
        nh &= ~attack; np &= ~attack;
        if (pressed & attack) refused = true;
    }
    // L3: a tap is a dodge, a hold a sprint
    if (held & L3) l3++;
    else { if (l3 > 0 && l3 < t.sprint_hold) dodge = true; l3 = 0; }
    float lx = F(pad + PAD_LX), ly = F(pad + PAD_LY);
    bool sprint = (held & L3) && l3 >= t.sprint_hold && state == 2 && stamina > 0 && lx * lx + ly * ly > 0.25f;
    if (SR(slot_off(slot, S_BROKEN)) > 0 && block) { nh &= ~block; np &= ~block; }
    if (nh != held) PW(pad + PAD_HELD, nh);
    if (np != pressed) PW(pad + PAD_PRESSED, np);
    u32 speed_bits = W(record + REC_SPEED);
    if (sprint) PF(record + REC_SPEED, flt(speed_bits) * ((float)t.sprint_speed_percent / 100.0f));
    bool heavy_started = false;
    if (heavy && state == 2 && B(P + P_ON_GROUND) && W(P + P_ATTACK_REQUEST) == 0 && (int8_t)B(P + O_TRACKS) < 6 && !B(P + C_INERT) && F(record + REC_HP) > 0)
        heavy_started = start_heavy(c, P, cls);

    g_orig_run(c);

    PW(pad + PAD_HELD, held);
    PW(pad + PAD_PRESSED, pressed);
    if (sprint) PW(record + REC_SPEED, speed_bits);
    s32 now = (s32)W(P + P_STATE);
    bool dodged = false;
    s32 dodge_t = copy ? g_ghost.dodge : SR(slot_off(slot, S_DODGE));
    if (dodge) {
        bool can = (now == 2 || now == 8) && B(P + P_ON_GROUND) && !B(P + C_INERT) && F(record + REC_HP) > 0 && dodge_t < 0 &&
                   (copy || SR(slot_off(slot, S_COOL)) == 0) && !(W(G_LEVEL_FLAGS) & 0x10000000);
        if (can && stamina > 0) dodged = start_dodge(c, P, slot, cls);
        else if (can) refused = true;
    }
    if (copy) {
        g_ghost.atk = atk; g_ghost.l3 = l3;
        g_ghost.dodge = dodged ? 0 : (g_ghost.dodge >= 0 && now == 0xb ? g_ghost.dodge + 1 : -1);
        return;
    }
    // ---- the numbers, real players only: the same on every machine ----
    SW(slot_off(slot, S_ATK), atk);
    SW(slot_off(slot, S_L3), l3);
    u32 flags = (u32)SR(slot_off(slot, S_FLAGS)) & (FL_HEAVY);
    s32 last = SR(slot_off(slot, S_LAST_STATE)), combo = (int8_t)B(P + P_COMBO);
    bool spent = false;
    if (refused) SW(slot_off(slot, S_REFUSED), SR(slot_off(slot, S_REFUSED)) + 1);
    if (dodged) {
        charge(slot, t.cost_dodge); spent = true;
        dodge_t = 0;
        SW(slot_off(slot, S_DODGES), SR(slot_off(slot, S_DODGES)) + 1);
    } else if (dodge_t >= 0) {
        dodge_t++;
        if (now != 0xb || dodge_t > 120) { dodge_t = -1; SW(slot_off(slot, S_COOL), t.dodge_cooldown); }
    } else if (SR(slot_off(slot, S_COOL)) > 0) SW(slot_off(slot, S_COOL), SR(slot_off(slot, S_COOL)) - 1);
    SW(slot_off(slot, S_DODGE), dodge_t);
    if (dodge_t >= 0) flags |= FL_DODGE;
    if (dodge_t >= t.dodge_iframe_first && dodge_t <= t.dodge_iframe_last) flags |= FL_IFRAMES;
    if (heavy_started) {
        charge(slot, t.cost_heavy); spent = true; flags |= FL_HEAVY;
        SW(slot_off(slot, S_HEAVIES), SR(slot_off(slot, S_HEAVIES)) + 1);
    } else if (now == 1 && W(P + P_ATTACK_REQUEST) != 2 && (last != 1 || combo != SR(slot_off(slot, S_LAST_COMBO)))) {
        charge(slot, t.cost_light); spent = true; flags &= ~FL_HEAVY;
        SW(slot_off(slot, S_LIGHTS), SR(slot_off(slot, S_LIGHTS)) + 1);
    } else if (now == 0 && last != 0) { charge(slot, t.cost_ranged); spent = true; }
    if (now != 1) flags &= ~FL_HEAVY;
    if (sprint) { charge(slot, t.cost_sprint_per_tick); spent = true; flags |= FL_SPRINT; }
    if (now == 8) flags |= FL_BLOCK;
    s32 broken = SR(slot_off(slot, S_BROKEN));
    if (broken > 0) { SW(slot_off(slot, S_BROKEN), broken - 1); flags |= FL_BROKEN; }
    if (!spent) {
        s32 delay = SR(slot_off(slot, S_DELAY));
        if (delay > 0) SW(slot_off(slot, S_DELAY), delay - 1);
        else {
            s32 add = now == 8 ? t.regen_per_tick * t.regen_block_percent / 100 : t.regen_per_tick;
            SW(slot_off(slot, S_STAMINA), std::min(t.stamina_max, SR(slot_off(slot, S_STAMINA)) + add));
        }
    }
    if (SR(slot_off(slot, S_STAMINA)) <= 0) flags |= FL_EMPTY;
    SW(slot_off(slot, S_FLAGS), (s32)flags);
    SW(slot_off(slot, S_LAST_STATE), now);
    SW(slot_off(slot, S_LAST_COMBO), combo);
    // the poise held, summed (the order of the entries does not matter to a sum)
    u32 tick = frame_now();
    s32 held_poise = 0;
    for (const auto& e : g_poise) if (tick - e.second.last <= (u32)t.poise_reset_ticks) held_poise += e.second.poise;
    SW(H_POISE, held_poise);
}

// ---- Player_takeDamage (slot 2): a0 the player, a1 the attacker, a2 the flags, f12 the amount ---------------------
void w_player_take_damage(Ctx* c) {
    u32 P = (u32)c->r[4];
    if (!g_on || !ok(P, 0x590) || (W(P + O_FLAGS) & FLAG_COPY)) { g_orig_ptd(c); return; }
    s32 slot = (s32)W(P + P_SLOT);
    if (slot < 0 || slot > 3 || g_last_object[slot] != P) { g_orig_ptd(c); return; }
    g_ptd_calls++;
    const Tuning& t = g_tuning;
    u32 attacker = (u32)c->r[5], flags = (u32)c->r[6];
    float amount = flt(c->f[12]);
    s32 dodge_t = SR(slot_off(slot, S_DODGE));
    if (amount > 0 && amount < 100000.0f && dodge_t >= t.dodge_iframe_first && dodge_t <= t.dodge_iframe_last) {
        // the dodge's invulnerable ticks: the hit does not land
        g_iframe_skips++;
        SW(slot_off(slot, S_AVOIDED), SR(slot_off(slot, S_AVOIDED)) + 1);
        SW(H_AVOIDED, SR(H_AVOIDED) + 1);
        return;
    }
    s32 state = (s32)W(P + P_STATE);
    if (dodge_t >= 0 && state == 0xb) { flags |= HIT_UNBLOCKABLE; c->r[6] = (u64)(s64)(s32)flags; }   // the dodge's recovery is no block
    bool blocking = (state == 8 || state == 0xb) && !(flags & HIT_UNBLOCKABLE) && attacker && amount > 0 && amount < 100000.0f;
    float before = F(P + C_PENDING);
    g_orig_ptd(c);
    if (!blocking) return;
    float added = F(P + C_PENDING) - before;
    if (added >= amount * 0.25f) return;            // from behind: the game did not block it
    u32 record = G_PLAYERS + (u32)slot * REC;
    float most = F(record + REC_HP_MAX);
    if (!(most > 1.0f)) most = 1.0f;
    float share = amount * 100.0f / most;
    if (share > 1000.0f) share = 1000.0f;
    s32 cost = t.cost_block_base + (s32)(share * (float)t.cost_block_per_hp_percent);
    s32 stamina = SR(slot_off(slot, S_STAMINA));
    SW(slot_off(slot, S_BLOCKS), SR(slot_off(slot, S_BLOCKS)) + 1);
    SW(H_BLOCKS, SR(H_BLOCKS) + 1);
    if (stamina >= cost) { charge(slot, cost); return; }
    // the guard breaks: no stamina left, the hit lands whole and the player staggers (the game's own forced stagger)
    charge(slot, stamina);
    SW(slot_off(slot, S_BROKEN), t.guard_break_ticks);
    PF(P + C_PENDING, F(P + C_PENDING) + (amount - added));
    PW(P + C_PENDING_FLAGS, W(P + C_PENDING_FLAGS) | PEND_STAGGER);
}

// ---- Creature_takeDamage (slot 2 of most creatures) -------------------------------------------------------------
void w_creature_take_damage(Ctx* c) {
    u32 V = (u32)c->r[4], A = (u32)c->r[5];
    if (!g_on || !ok(V, 0x3c8) || !ok(A, 0x590) || W(A + O_VTABLE) != VT_PLAYER || (W(A + O_FLAGS) & FLAG_COPY)) { g_orig_ctd(c); return; }
    s32 slot = (s32)W(A + P_SLOT);
    if (slot < 0 || slot > 3) { g_orig_ctd(c); return; }
    g_ctd_calls++;
    const Tuning& t = g_tuning;
    float amount = flt(c->f[12]);
    s32 state = (s32)W(A + P_STATE);
    bool heavy = state == 1 && W(A + P_ATTACK_REQUEST) == 2 && (SR(slot_off(slot, S_FLAGS)) & FL_HEAVY);
    if (heavy && amount > 0) c->f[12] = bits(amount * ((float)t.heavy_damage_percent / 100.0f));
    g_orig_ctd(c);
    if (!(amount > 0)) return;
    if (!(F(V + C_HP) > 0)) { g_poise.erase(V); return; }
    if (B(V + C_INERT)) return;
    u32 tick = frame_now();
    Poise& p = g_poise[V];
    if (tick - p.last > (u32)t.poise_reset_ticks) p.poise = 0;
    p.poise += heavy ? t.poise_heavy : state == 0 ? t.poise_ranged : t.poise_light;
    p.last = tick;
    u32 rank = call(c, CREATURE_BOSS_RANK, V) & 0xff;
    s32 limit = rank >= 2 ? t.poise_boss : rank == 1 ? t.poise_miniboss : t.poise_normal;
    if (p.poise >= limit) {
        p.poise = 0;
        u32 vtable = W(V + O_VTABLE);
        u32 stun = vtable ? W(vtable + 30 * 8 + 4) : 0;
        if (stun) {
            call(c, stun, V, (u32)t.stagger_ticks, 1);
            g_staggers++;
            SW(H_BREAKS, SR(H_BREAKS) + 1);
            static const bool log = getenv("SOULS_LOG") != nullptr;
            if (log) fprintf(stderr, "souls: tick %u: poise broken (rank %u): stun slot %08x, the creature's stun timer is now %d\n", tick, rank, stun, (int)(s16)H(V + 0x31c));
        }
    }
    if (g_poise.size() > 256)
        for (auto it = g_poise.begin(); it != g_poise.end();) it = tick - it->second.last > (u32)t.poise_reset_ticks ? g_poise.erase(it) : std::next(it);
}

void install() {
    if (g_installed) return;
    g_orig_run = rt_replace_function(PLAYER_RUN, w_player_run);
    g_orig_ptd = rt_replace_function(PLAYER_TAKE_DAMAGE, w_player_take_damage);
    g_orig_ctd = rt_replace_function(CREATURE_TAKE_DAMAGE, w_creature_take_damage);
    if (!g_orig_run || !g_orig_ptd || !g_orig_ctd) {
        // a translation without one of them: put back what was replaced and stay off
        if (g_orig_run) rt_replace_function(PLAYER_RUN, g_orig_run);
        if (g_orig_ptd) rt_replace_function(PLAYER_TAKE_DAMAGE, g_orig_ptd);
        if (g_orig_ctd) rt_replace_function(CREATURE_TAKE_DAMAGE, g_orig_ctd);
        fprintf(stderr, "souls: the game's functions are not all there; the mode stays off\n");
        g_want = false;
        return;
    }
    g_installed = true;
    fprintf(stderr, "souls: the combat mode's wrappers are in place\n");
}

u32 tuning_figure() {
    std::lock_guard<std::mutex> hold(g_lock);
    u32 h = 2166136261u;
    const unsigned char* p = (const unsigned char*)&g_tuning;
    for (size_t k = 0; k < sizeof g_tuning; k++) h = (h ^ p[k]) * 16777619u;
    return h;
}

struct Hooks {
    Hooks() {
        net2hook::souls_wanted = [] { return g_want.load() ? 1 : 0; };
        net2hook::souls_want = [](bool on) { g_want = on; };
        net2hook::souls_figure = [] { return tuning_figure(); };
        net2hook::souls_room = [](int on) { g_room = on; };
    }
} g_hooks_installed;

struct Named { const char* name; int32_t Tuning::*field; };
const Named NAMES[] = {
    {"stamina_max", &Tuning::stamina_max}, {"regen_per_tick", &Tuning::regen_per_tick}, {"regen_delay", &Tuning::regen_delay},
    {"regen_block_percent", &Tuning::regen_block_percent}, {"cost_light", &Tuning::cost_light}, {"cost_heavy", &Tuning::cost_heavy},
    {"cost_ranged", &Tuning::cost_ranged}, {"cost_dodge", &Tuning::cost_dodge}, {"cost_sprint_per_tick", &Tuning::cost_sprint_per_tick},
    {"cost_block_base", &Tuning::cost_block_base}, {"cost_block_per_hp_percent", &Tuning::cost_block_per_hp_percent},
    {"heavy_hold", &Tuning::heavy_hold}, {"sprint_hold", &Tuning::sprint_hold}, {"dodge_iframe_first", &Tuning::dodge_iframe_first},
    {"dodge_iframe_last", &Tuning::dodge_iframe_last}, {"dodge_cooldown", &Tuning::dodge_cooldown}, {"dodge_stick_ignored", &Tuning::dodge_stick_ignored},
    {"guard_break_ticks", &Tuning::guard_break_ticks}, {"sprint_speed_percent", &Tuning::sprint_speed_percent},
    {"heavy_damage_percent", &Tuning::heavy_damage_percent}, {"poise_light", &Tuning::poise_light}, {"poise_heavy", &Tuning::poise_heavy},
    {"poise_ranged", &Tuning::poise_ranged}, {"poise_normal", &Tuning::poise_normal}, {"poise_miniboss", &Tuning::poise_miniboss},
    {"poise_boss", &Tuning::poise_boss}, {"poise_reset_ticks", &Tuning::poise_reset_ticks}, {"stagger_ticks", &Tuning::stagger_ticks}};

}  // namespace

const Tuning& tuning() { return g_tuning; }
void want(bool on) { g_want = on; }
bool wanted() { return g_want.load(); }
void room_agreed(bool on) { g_room = on ? 1 : 0; }
bool active() { return g_on; }

void blank(uint64_t number) {
    (void)number;
    bool net = B(G_NETWORK_MODE) != 0;
    int room = g_room.load();
    // offline: this copy's setting; online: only a game of a room that agreed (an old-lobby game: off)
    bool on = room >= 0 ? room == 1 : !net && g_want.load();
    if (on && !g_installed) install();
    if (on && !g_installed) on = false;
    if (on != g_on || room != g_last_room) {
        g_last_room = room;
        reset_all();
        g_on = on;
        SW(H_MODE, on ? 1 : 0);
        if (!on) SW(H_MAGIC, 0);
        fprintf(stderr, "souls: the combat mode is %s (%s)\n", on ? "ON" : "off", room >= 0 ? "a room's game" : net ? "an online game without a room: off" : "offline");
    }
    fpcontrols::set_souls(on);
    // the local part of the block, and what the overlay shows
    const fpcontrols::Hud& h = fpcontrols::hud();
    Shown s;
    if (on && h.slot >= 0 && h.slot < 4) {
        s.valid = h.playing;
        s.slot = h.slot;
        s.stamina = (float)SR(slot_off(h.slot, S_STAMINA));
        s.max = (float)g_tuning.stamina_max;
        s.flags = (u32)SR(slot_off(h.slot, S_FLAGS));
        s.lock = h.lock.valid;
        s.x = h.lock.x; s.y = h.lock.y; s.z = h.lock.z; s.hp = h.lock.hp; s.hp_max = h.lock.hp_max;
        SW(L_LOCK, s.lock ? 1 : 0);
        SW(L_OBJECT, (s32)(s.lock ? h.lock.object : 0));
        PF(SOULS_BASE + L_X, s.x); PF(SOULS_BASE + L_Y, s.y); PF(SOULS_BASE + L_Z, s.z);
        PF(SOULS_BASE + L_HP, s.hp); PF(SOULS_BASE + L_HP_MAX, s.hp_max);
    }
    std::lock_guard<std::mutex> hold(g_lock);
    g_shown = s;
}

void set_camera(const Camera& camera) { std::lock_guard<std::mutex> hold(g_lock); g_camera = camera; }

// ---- the overlay: plain blended rectangles in the shown surface ----
void overlay(render::FrameList& frame) {
    Shown s;
    Camera cam;
    { std::lock_guard<std::mutex> hold(g_lock); s = g_shown; cam = g_camera; }
    if (!s.valid || !frame.show_target || frame.show_rect[2] <= 0 || frame.show_rect[3] <= 0) return;
    float X = (float)frame.show_rect[0], Y = (float)frame.show_rect[1], Wd = (float)frame.show_rect[2], Ht = (float)frame.show_rect[3];
    size_t first = frame.vertices.size();
    auto quad = [&](float x0, float y0, float x1, float y1, uint8_t r, uint8_t g, uint8_t b, uint8_t a) {
        render::Vertex v{};
        v.z = 1; v.q = 1; v.r = r; v.g = g; v.b = b; v.a = a;
        auto put = [&](float x, float y) { v.x = x; v.y = y; frame.vertices.push_back(v); };
        put(x0, y0); put(x1, y0); put(x0, y1); put(x1, y0); put(x1, y1); put(x0, y1);
    };
    // stamina: a bar under the middle of the picture (the game's own bars are top left)
    float bw = Wd * 0.26f, bh = std::max(3.0f, Ht * 0.014f), bx = X + (Wd - bw) * 0.5f, by = Y + Ht * 0.905f;
    float share = s.max > 0 ? std::max(0.0f, std::min(1.0f, s.stamina / s.max)) : 0;
    bool empty = (s.flags & FL_EMPTY) != 0, broken = (s.flags & FL_BROKEN) != 0;
    quad(bx - 2, by - 2, bx + bw + 2, by + bh + 2, 0, 0, 0, 0x60);
    quad(bx, by, bx + bw, by + bh, 0x30, 0x30, 0x30, 0x50);
    if (share > 0) quad(bx, by, bx + bw * share, by + bh, broken ? 0xd0 : 0x58, broken ? 0x50 : 0xc8, broken ? 0x30 : 0x50, 0x70);
    if (empty) quad(bx, by, bx + bw, by + bh, 0xe0, 0x20, 0x20, 0x40);
    if (s.flags & FL_IFRAMES) {         // the dodge's invulnerable ticks: a white frame round the bar
        float e = std::max(1.5f, bh * 0.35f);
        quad(bx - 2 - e, by - 2 - e, bx + bw + 2 + e, by - 2, 0xf0, 0xf0, 0xf0, 0x78);
        quad(bx - 2 - e, by + bh + 2, bx + bw + 2 + e, by + bh + 2 + e, 0xf0, 0xf0, 0xf0, 0x78);
        quad(bx - 2 - e, by - 2, bx - 2, by + bh + 2, 0xf0, 0xf0, 0xf0, 0x78);
        quad(bx + bw + 2, by - 2, bx + bw + 2 + e, by + bh + 2, 0xf0, 0xf0, 0xf0, 0x78);
    }
    // the lock-on: a diamond on the target, its health under it
    if (s.lock && cam.valid) {
        float v[3] = {s.x - cam.eye[0], s.y - cam.eye[1], s.z - cam.eye[2]};
        float z = v[0] * cam.forward[0] + v[1] * cam.forward[1] + v[2] * cam.forward[2];
        if (z > 1.0f) {
            float th = std::tan(cam.fov * 0.5f * 3.14159265f / 180.0f), aspect = frame.aspect > 0.1f ? frame.aspect : 4.0f / 3.0f;
            float px = (v[0] * cam.right[0] + v[1] * cam.right[1] + v[2] * cam.right[2]) / (z * th * aspect);
            float py = (v[0] * cam.up[0] + v[1] * cam.up[1] + v[2] * cam.up[2]) / (z * th);
            if (std::fabs(px) < 1.2f && std::fabs(py) < 1.2f) {
                float cx = X + (0.5f + 0.5f * px) * Wd, cy = Y + (0.5f - 0.5f * py) * Ht, r = Ht * 0.018f;
                render::Vertex d{};
                d.z = 1; d.q = 1; d.r = 0xf0; d.g = 0xe0; d.b = 0x90; d.a = 0x78;
                auto tri = [&](float ax, float ay, float bx2, float by2, float qx, float qy) {
                    d.x = ax; d.y = ay; frame.vertices.push_back(d); d.x = bx2; d.y = by2; frame.vertices.push_back(d); d.x = qx; d.y = qy; frame.vertices.push_back(d);
                };
                tri(cx, cy - r, cx + r, cy, cx, cy + r);
                tri(cx, cy - r, cx, cy + r, cx - r, cy);
                d.r = d.g = d.b = 0x10; d.a = 0x70;
                float k = r * 0.45f;
                tri(cx, cy - k, cx + k, cy, cx, cy + k);
                tri(cx, cy - k, cx, cy + k, cx - k, cy);
                if (s.hp_max > 0) {
                    float hw = r * 5, hy = cy + r * 2.2f, hh = std::max(2.0f, r * 0.35f), part = std::max(0.0f, std::min(1.0f, s.hp / s.hp_max));
                    quad(cx - hw * 0.5f, hy, cx + hw * 0.5f, hy + hh, 0, 0, 0, 0x60);
                    quad(cx - hw * 0.5f, hy, cx - hw * 0.5f + hw * part, hy + hh, 0xc8, 0x30, 0x28, 0x70);
                }
            }
        }
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

bool setting(const char* key, const char* value) {
    if (strncmp(key, "combat.", 7) != 0) return false;
    std::string name = key + 7, text = value ? value : "";
    if (name == "mode") { g_want = text == "souls" || text == "on" || text == "yes"; return true; }
    std::lock_guard<std::mutex> hold(g_lock);
    for (const Named& n : NAMES)
        if (name == n.name) { g_tuning.*(n.field) = (int32_t)atol(text.c_str()); return true; }
    return false;
}

std::string settings_text() {
    std::string out = std::string("combat.mode = ") + (g_want.load() ? "souls" : "off") +
                      "      # souls: stamina, dodge, light / heavy attacks, blocking with stamina, poise, lock-on (docs/issues/native-souls-combat.md)\n";
    return out;
}

std::string figures() {
    char text[320];
    snprintf(text, sizeof text, "souls: %s, wrappers %s; player ticks %llu, player hits %llu (dodged %llu), creature hits by players %llu, staggers %llu, tuning %08x",
             g_on ? "on" : "off", g_installed ? "in place" : "not installed", (unsigned long long)g_runs, (unsigned long long)g_ptd_calls,
             (unsigned long long)g_iframe_skips, (unsigned long long)g_ctd_calls, (unsigned long long)g_staggers, tuning_figure());
    return text;
}

std::string help_text() {
    return "Souls-style combat (combat.mode = souls; online the room's host decides):\n"
           "  Light attack          tap the attack button (K, left mouse button)\n"
           "  Heavy attack          hold it\n"
           "  Dodge                 tap L3 (X, mouse button 4) - toward the move stick, or back\n"
           "  Sprint                hold L3 while moving\n"
           "  Block                 R1 (E, Shift, right mouse button): costs stamina instead of health\n"
           "  Lock on               R3 (Tab, mouse button 5); flick the mouse or the right stick to change target\n";
}

std::string command(const std::string& text) {
    std::string w = text;
    while (!w.empty() && w[0] == ' ') w.erase(0, 1);
    if (w.empty() || w == "info") {
        std::string out = figures();
        for (int k = 0; k < 4; k++) {
            char one[200];
            snprintf(one, sizeof one, " | p%d st=%d fl=%x dodge=%d atk=%d l3=%d dodges=%d heavy=%d light=%d refused=%d avoided=%d blocks=%d", k,
                     SR(slot_off(k, S_STAMINA)), SR(slot_off(k, S_FLAGS)), SR(slot_off(k, S_DODGE)), SR(slot_off(k, S_ATK)), SR(slot_off(k, S_L3)),
                     SR(slot_off(k, S_DODGES)), SR(slot_off(k, S_HEAVIES)), SR(slot_off(k, S_LIGHTS)), SR(slot_off(k, S_REFUSED)),
                     SR(slot_off(k, S_AVOIDED)), SR(slot_off(k, S_BLOCKS)));
            out += one;
        }
        char tail[96];
        snprintf(tail, sizeof tail, " | breaks=%d poise=%d lock=%d", SR(H_BREAKS), SR(H_POISE), SR(L_LOCK));
        return out + tail;
    }
    if (w == "on" || w == "off") { if (B(G_NETWORK_MODE)) return "souls: not during an online game"; g_want = w == "on"; return "souls: wanted " + w; }
    if (w == "lock") { fpcontrols::lock_toggle(); return "souls: lock toggled"; }
    if (w.compare(0, 4, "set ") == 0) {
        if (B(G_NETWORK_MODE)) return "souls: not during an online game";
        size_t sp = w.find(' ', 4);
        if (sp == std::string::npos) return "souls: set NAME VALUE";
        std::string key = "combat." + w.substr(4, sp - 4);
        return setting(key.c_str(), w.substr(sp + 1).c_str()) ? "souls: set" : "souls: no such number";
    }
    return "souls: info | on | off | lock | set NAME VALUE";
}

}  // namespace soulscombat
