// soulscombat.cpp - the souls-style combat mode (soulscombat.h; docs/issues/native-souls-combat.md).
#include "soulscombat.h"
#include "partyscale.h"
#include "fpcontrols.h"
#include "testerkit.h"
#include "rt.h"
#include "moved.h"
#include "backend.h"
#include "../net2/hooks.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstddef>
#include <cstring>
#include <iterator>
#include <mutex>
#include <unordered_map>
#include <vector>

namespace soulscombat {
namespace {

// ---- the game (addresses and offsets: docs/player.md, docs/spec/player-tick.md, docs/creatures.md) ----
const u32 PLAYER_RUN = 0x1a5030, PLAYER_TAKE_DAMAGE = 0x1b5330, CREATURE_TAKE_DAMAGE = 0x116638, SAVEPOINT_RUN = 0x28cdd0;
const u32 MATH_COS16 = 0x166630, MATH_SIN16 = 0x1666e0;
const u32 MATH_ATAN2_16 = 0x166798, NET_GET_CAM_YAW = 0x13e0c8, ANIM_START_BLEND_IN_OUT = 0x16ceb0, CREATURE_BOSS_RANK = 0x10d940;
const u32 G_PLAYERS = 0x4d8af0, REC = 0x4c30, REC_OBJECT = 0x43d8, REC_HP = 0xac, REC_HP_MAX = 0xb0, REC_SPEED = 0x4c20, REC_WEAPON_CLASS = 0x4a86;
const u32 G_PADS = 0x41bfd8, PAD = 0x58, PAD_HELD = 8, PAD_PRESSED = 0xc, PAD_LX = 0x14, PAD_LY = 0x18;
const u32 G_BTN_ATTACK = 0x41b980, G_BTN_BLOCK = 0x41b9d0, G_BTN_POTION_A = 0x41ba10;
const u32 REC_GOLD = 0xe4, REC_HEAL_PENDING = 0xb4, REC_HEAL_RATE = 0xb8, REC_BLOCK_TIMER = 0x4a5c, O_POS = 0x10, O_ANIM_FLAGS = 0x11a;
const u32 G_SIM_FRAME = 0x44fdcc, G_NETWORK_MODE = 0x402791, G_LEVEL_FLAGS = 0x44fe08, G_LEVEL_NAME = 0x41b721, G_GRID = 0x5db4f0;
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
// the weapons round (docs/issues/native-souls-combat.md 2.8): items (docs/spec/items.md, docs/player.md), skills (docs/spec/skills-35-68.md)
const u32 G_BTN_USE = 0x41b9c0, G_BTN_SWAP = 0x41ba30;
const u32 ITEM_GET_WEIGHT = 0x103e08, G_ITEM_DEFS = 0x3f7650, G_SKILL_TABLE = 0x41b170, CREATURE_ADD_SPELL = 0x11a838;
const u32 LOOT_SPAWN_NAMED = 0x100ba0, INVENTORY_REMOVE = 0x1c1cb0, INVENTORY_GIVE = 0x1c1868, RES_FIND = 0x17365c, G_RAND_SEED = 0x404464;
const u32 REC_STR = 0x90, REC_INT = 0x94, REC_DEX = 0x98, REC_STA = 0x9c, REC_MANA = 0xc0, REC_MANA_MAX = 0xc4, REC_DMG_MAX = 0xd4;
const u32 REC_EQUIP = 0x43f0, REC_SETS = 0x4434, REC_SET = 0x4a7c, REC_BAGS = 0x130, BAG_STRIDE = 0x1208, BAG_COUNT = 0x1200, ITEM = 0x48;
const u32 FLAG_KNOCK_LIGHT = 0x40000;   // the lightest knock bit: the ground pound's shoves carry it
const s32 SKILL_OF_ART[5] = {0, 35, 41, 38, 37};   // charge (a lunge), cyclone (a spin), ground pound (a slam), shock (a bolt)
// the stats round (docs/issues/native-souls-combat.md 2.9): the class (docs/player.md), the level, the ability records and the
// skill buttons (docs/spec/player-tick.md), the skills (docs/skills.md), the save spot (soulscombat.h)
const u32 REC_CLASS = 0x50, REC_LEVEL = 0x59, REC_ABILITIES = 0x4440, ABILITY = 0x68, REC_BUTTON_A = 0x4a84, REC_SELECTED = 0x4a60;
const u32 REC_RANKS = 0x4b08, REC_SPOT = 0x4c2a, P_RECAST = 0x4ae, G_BTN_ABILITY_A = 0x41b990, G_BTN_ABILITY_B = 0x41b9a0;
const u32 G_BTN_POTION_B = 0x41ba20, SKILL_RECORD_NAME = 0x535e30, PLAYER_GIVE_EXP = 0x1d3150;
const u32 PLAYER_RECALC_STATS = 0x1b6458;
const u32 PAD_UP = 0x1000, PAD_RIGHT = 0x2000, PAD_DOWN = 0x4000, PAD_LEFT = 0x8000;
const s32 ID_HEAVY = 0x25;

bool ok(u32 a, u32 size = 4) { a &= 0x1FFFFFFF; return a >= 0x80000 && a <= RAM_SIZE - size; }
u32 W(u32 a) { u32 v = 0; if (ok(a)) memcpy(&v, g_ram + (party8_at(a) & 0x1FFFFFFF), 4); return v; }
u16 H(u32 a) { u16 v = 0; if (ok(a, 2)) memcpy(&v, g_ram + (party8_at(a) & 0x1FFFFFFF), 2); return v; }
u8 B(u32 a) { return ok(a, 1) ? g_ram[party8_at(a) & 0x1FFFFFFF] : 0; }
float F(u32 a) { float v = 0; if (ok(a)) memcpy(&v, g_ram + (party8_at(a) & 0x1FFFFFFF), 4); return v; }
void PW(u32 a, u32 v) { if (ok(a)) memcpy(g_ram + (party8_at(a) & 0x1FFFFFFF), &v, 4); }
void PH(u32 a, u16 v) { if (ok(a, 2)) memcpy(g_ram + (party8_at(a) & 0x1FFFFFFF), &v, 2); }
void PB(u32 a, u8 v) { if (ok(a, 1)) g_ram[party8_at(a) & 0x1FFFFFFF] = v; }
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
             H_PARRIES = 0x20, H_RIPOSTES = 0x24, H_STANCE = 0x28, H_BACKSTABS = 0x2c, H_COUNTERS = 0x30, H_REFILLS = 0x34,
             H_GOLD_BACK = 0x38, H_GOLD_LOST = 0x3c, H_DROPS = 0x300, H_PICKUPS = 0x304, H_DRUNK = 0x308, H_DEAD = 0x30c, H_TEST_GO = 0x31c, BLOCK_SIZE = 0xc80,
             L_LOCK = 0x180, L_OBJECT = 0x184, L_X = 0x188, L_Y = 0x18c, L_Z = 0x190, L_HP = 0x194, L_HP_MAX = 0x198, L_DROP = 0x19c };
// the second per-player part (soulscombat.h): kept over a death and a level change
u32 ext_off(int slot, u32 field) { return 0x200 + (u32)slot * 0x40 + field; }
enum : u32 { E_FLASKS = 0, E_PARRY = 4, E_RIPOSTE = 8, E_COUNTER = 0xc, E_DRINK = 0x10, E_DROP = 0x14, E_DROP_X = 0x18, E_DROP_Y = 0x1c,
             E_DROP_Z = 0x20, E_DROP_LEVEL = 0x24, E_PENDING = 0x28, E_PARRIES = 0x2c, E_CRITS = 0x30, E_COUNTERS = 0x34, E_DRUNK = 0x38,
             E_GOLD_BACK = 0x3c };
s32 ER(int slot, u32 f) { return SR(ext_off(slot, f)); }
void EW(int slot, u32 f, s32 v) { SW(ext_off(slot, f), v); }
// the weapons part (soulscombat.h, version 3)
u32 wpn_off(int slot, u32 field) { return 0x400 + (u32)slot * 0x60 + field; }
enum : u32 { W_CLASS = 0, W_LOAD = 4, W_CAP = 8, W_TIER = 0xc, W_UPG = 0x10, W_GRADES = 0x14, W_SCALE = 0x18, W_TWOHAND = 0x1c,
             W_ART_T = 0x20, W_ART_KIND = 0x24, W_MATS = 0x28, W_NEAR = 0x2c, W_ARTS = 0x30, W_UPGRADES = 0x34, W_RECOVER = 0x38,
             W_SWING = 0x3c, W_ART_CD = 0x40, W_BUFFER = 0x44, W_DMG = 0x48, W_GOLD_NEXT = 0x4c, W_MATS_NEXT = 0x50, W_UP_REFUSED = 0x54 };
enum : u32 { H_ARTS = 0x320, H_UPGRADES = 0x324, H_MAT_DROPS = 0x328, H_TWOHANDS = 0x32c, H_CHIPS = 0x330, H_INTERRUPTS = 0x334,
             H_CANCELS = 0x338, H_TEST_MAT = 0x33c, H_SCRATCH = 0x340, H_SAVES = 0x380, H_SAVES_LEVEL = 0x3fc, H_ITEM_SCRATCH = 0x5a0, H_TEST_POSE = 0x580, L_NAME = 0x1a0 };
s32 WR(int slot, u32 f) { return SR(wpn_off(slot, f)); }
void WW(int slot, u32 f, s32 v) { SW(wpn_off(slot, f), v); }
// the attributes and spellbook part (soulscombat.h, version 4)
u32 st_off(int slot, u32 field) { return 0x600 + (u32)slot * 0x80 + field; }
enum : u32 { A_VIG = 0, A_MND = 4, A_END = 8, A_STR = 0xc, A_DEX = 0x10, A_INT = 0x14, A_FTH = 0x18, A_UNSPENT = 0x1c, A_SPENT = 0x20,
             A_OPEN = 0x24, A_ROW = 0x28, A_SLOTS = 0x2c, A_BOOK = 0x30, A_ATTUNED = 0x34, A_STAMINA_MAX = 0x38, A_MANA_BASE = 0x3c,
             A_MANA_WRITTEN = 0x40, A_MANA_LAST = 0x44, A_SPELL_PCT = 0x48, A_SPELL_GRADES = 0x4c, A_SPELL_T = 0x50, A_CASTS = 0x54,
             A_CAST_REFUSED = 0x58, A_POINTS = 0x5c, A_SWAPS = 0x60, A_SPOT = 0x64, A_LEVEL = 0x68, A_OPENED = 0x6c, A_CLASS = 0x70, A_USED = 0x74 };
enum : u32 { H_TEST_XP = 0x5e8, H_POINTS = 0x5ec, H_SWAPS = 0x5f0, H_CASTS = 0x5f4, H_SPELL_HITS = 0x5f8, H_CAST_REFUSED = 0x5fc,
             COST_BASE = 0xa00, L_SHEET = 0x1c0, L_SLOT_REC = 0x1e0, L_SPELL_NAMES = 0xb00 };
s32 AR(int slot, u32 f) { return SR(st_off(slot, f)); }
void AW(int slot, u32 f, s32 v) { SW(st_off(slot, f), v); }
void bump(u32 off, s32 by = 1) { SW(off, SR(off) + by); }

// ---- state ----
Tuning g_tuning;
std::mutex g_lock;                      // the tuning and the camera against other threads
std::atomic<bool> g_want{false};
std::atomic<int> g_room{-1};            // -1 no room game; 0 / 1 the launched game's mode
int g_last_room = -1;
bool g_on = false;                      // in force (game thread)
bool g_installed = false;
RecompFn g_orig_run = nullptr, g_orig_ptd = nullptr, g_orig_ctd = nullptr, g_orig_save = nullptr;
u32 g_riposte_target[4] = {0, 0, 0, 0}; // per slot: the creature a parry opened (an object of this machine, see Poise)
u32 g_last_object[4] = {0, 0, 0, 0};    // per machine: which object the slot's numbers belong to
char g_level[16] = "";
struct Ghost { s32 atk = 0, l3 = 0, dodge = -1; u32 object = 0; } g_ghost;   // the prediction copy's own presses (picture only)
struct Poise { s32 poise = 0; u32 last = 0, broken = 0, crit = 0; };   // broken / crit: the tick + 1 of the last poise break / critical
std::unordered_map<u32, Poise> g_poise; // by creature object (soulscombat.h)
// presentation
Camera g_camera;
struct Shown { bool valid = false; int slot = -1; float stamina = 1, max = 1; u32 flags = 0; bool lock = false; float x = 0, y = 0, z = 0, hp = 0, hp_max = 0;
               int flasks = 0, flask_max = 0; bool drop = false; float dx = 0, dy = 0, dz = 0;
               int cls = 0, level = 0, tier = 0, load = 0, cap = 1, mats = 0, gold_next = 0, mats_next = 0, art_cd = 0, damage = 100;
               u32 grades = 0; bool two = false, near = false; char name[32] = "";
               // the character sheet (the attributes and the spellbook of this machine's player)
               struct Spell { char name[24] = ""; int cost10 = 0, rank = 0; bool attuned = false; };
               bool sheet = false, open = false; int row = 0, unspent = 0, char_level = 0, cls_of = 0, slots = 0, v[7] = {0, 0, 0, 0, 0, 0, 0};
               int spell_pct = 100, stamina_most = 10000; u32 spell_grades = 0; float hp_now = 0, hp_most = 0, mana = 0, mana_most = 0;
               Spell book[15]; int rows[15] = {0}, books = 0, used = 0; } g_shown;
std::atomic<bool> g_sheet_view{false};  // the sheet asked for on this machine (app souls sheet); presentation only
// counters (per machine)
uint64_t g_runs = 0, g_ptd_calls = 0, g_ctd_calls = 0, g_staggers = 0, g_iframe_skips = 0, g_save_calls = 0;
bool g_log = false;                     // SOULS_LOG: a line for each parry, critical, guard counter, drink, drop

u32 frame_now() { return W(G_SIM_FRAME); }

// A game function called the way its own code calls it, on the context that is running (its registers put
// back afterwards); returns v0.
u32 g_f0 = 0;                           // f0 of the last call()
u32 call(Ctx* c, u32 address, u32 a0, u32 a1 = 0, u32 a2 = 0, u32 f12 = 0, u32 f13 = 0, u32 a3 = 0, u32 t0 = 0) {
    Ctx saved = *c;
    c->r[29] = (u64)(s64)(s32)((((u32)saved.r[29]) - 0x600) & ~15u);
    c->r[4] = (u64)(s64)(s32)a0; c->r[5] = (u64)(s64)(s32)a1; c->r[6] = (u64)(s64)(s32)a2;
    c->r[7] = (u64)(s64)(s32)a3; c->r[8] = (u64)(s64)(s32)t0;
    c->f[12] = f12; c->f[13] = f13;
    rt_call(c, address);
    u32 v = (u32)c->r[2];
    g_f0 = (u32)c->f[0];
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

s32 stamina_most(int slot);
void reset_slot(int slot) {
    for (u32 f = 0; f < 0x28; f += 4) SW(slot_off(slot, f), 0);
    SW(slot_off(slot, S_STAMINA), stamina_most(slot));
    SW(slot_off(slot, S_DODGE), -1);
    SW(slot_off(slot, S_LAST_STATE), -1);
}

void reset_ext(int slot) {
    for (u32 f = 0; f < 0x40; f += 4) EW(slot, f, 0);
    EW(slot, E_FLASKS, g_tuning.flask_count);
    EW(slot, E_PARRY, -1);
    EW(slot, E_DRINK, -1);
}

void reset_all() {
    for (u32 a = 0; a < BLOCK_SIZE; a += 4) PW(SOULS_BASE + a, 0);
    SW(H_MAGIC, (s32)SOULS_MAGIC);
    SW(H_VERSION, 4);
    for (int k = 0; k < 4; k++) {
        reset_slot(k); reset_ext(k); g_last_object[k] = 0; g_riposte_target[k] = 0;
        WW(k, W_ART_T, -1); WW(k, W_SWING, -1);
        AW(k, A_SPELL_T, -1);
    }
    g_poise.clear();
    g_ghost = Ghost();
}

u32 level_figure() {
    u32 h = 2166136261u;
    for (u32 k = 0; k < 15 && g_ram[G_LEVEL_NAME + k]; k++) h = (h ^ g_ram[G_LEVEL_NAME + k]) * 16777619u;
    return h;
}

// A creature that a player's hit goes through Creature_takeDamage for (its slot 2), alive: what a parry staggers and a
// critical lands on.  Its stun is its own slot 30 (the stun skill's effect).
bool creature(u32 A) {
    if (!ok(A, 0x3c8)) return false;
    u32 vt = W(A + O_VTABLE);
    return vt && vt != VT_PLAYER && ok(vt, 0x100) && W(vt + 2 * 8 + 4) == CREATURE_TAKE_DAMAGE && F(A + C_HP) > 0;
}
bool stun(Ctx* c, u32 V, s32 ticks) {
    u32 vtable = W(V + O_VTABLE);
    u32 fn = vtable ? W(vtable + 30 * 8 + 4) : 0;
    if (!fn) return false;
    call(c, fn, V, (u32)ticks, 1);
    return true;
}
// squared distance in the ground plane (x, y) and in all three; single float operations
float ground2(u32 a, u32 b) { float dx = F(a + O_POS) - F(b + O_POS), dy = F(a + O_POS + 4) - F(b + O_POS + 4); return dx * dx + dy * dy; }

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

// The drink: the game's cast clip (anim(0x6c)) played once in the game's hit-reaction state 3, which steps the
// animation, does not move the character and returns to state 2 when the clip ends (flag 8) - a committed action.
bool start_drink(Ctx* c, u32 P, int cls) {
    u32 table = W(P + O_ANIM_TABLE);
    u32 clip = table ? W(table + (u32)cls * 0x68 + 0x6c) : 0;
    if (!clip) return false;
    PB(P + P_BLOCKING, 0);
    PW(P + P_ACTION_START, frame_now());
    PW(P + P_STATE, 3);
    call(c, ANIM_START_BLEND_IN_OUT, P + O_ANIM, clip, 0x808, F_ONE_TENTH, F_POINT_3);
    return true;
}

// ---- the weapons (docs/issues/native-souls-combat.md 2.8) ------------------------------------------------------
// The name of an item definition contains `word` (lower case; the game's names are lower case).
bool name_has(u32 def, const char* word) {
    u32 name = W(def);
    char text[40];
    size_t n = 0;
    for (; n < sizeof text - 1 && ok(name + (u32)n, 1); n++) { text[n] = (char)B(name + (u32)n); if (!text[n]) break; }
    text[n] = 0;
    return strstr(text, word) != nullptr;
}
// The class of a weapon, from its definition row: the weapon animation class (+0x1e), the damage kind (+0x20), the weight
// (+0x08) and, for the one-handed edged weapons, the name's own word.
s32 weapon_class(u32 def) {
    if (!ok(def, 0x40) || B(def + 0x1d) != 0) return WC_NONE;
    u32 sub = B(def + 0x1e), kind = W(def + 0x20);
    if (sub == 4 || sub == 6) return WC_BOW;            // bows and thrown weapons
    if (sub == 1 || sub == 2) return WC_GREAT;          // the two-handed swords, axes, hammers and maces
    if (sub == 3) return (kind & 1) ? WC_STAFF : WC_SPEAR;   // long weapons: blunt ones are the staves, edged ones the polearms
    if (kind & 1) return WC_MACE;                       // one-handed blunt: clubs, maces, morning stars, hammers, rods
    if (F(def + 8) <= 1.0f) return WC_DAGGER;           // the lightest edged weapons
    if (name_has(def, "axe") || name_has(def, "pick") || name_has(def, "cleaver") || name_has(def, "hatchet")) return WC_AXE;
    return WC_SWORD;
}
const char* class_name(s32 cls) {
    static const char* const NAMES_OF[WC_COUNT] = {"unarmed", "dagger", "sword", "axe", "mace", "great weapon", "spear", "staff", "bow"};
    return cls >= 0 && cls < WC_COUNT ? NAMES_OF[cls] : "?";
}
// the weapon in hand: the active set's primary, else the one-hand or two-hand equipment slot
u32 weapon_item(u32 record) {
    u32 it = W(record + REC_SETS + 4 * (u32)(B(record + REC_SET) & 1));
    if (!ok(it, ITEM)) it = W(record + REC_EQUIP);
    if (!ok(it, ITEM)) it = W(record + REC_EQUIP + 8);
    return ok(it, ITEM) && ok(W(it), 0x40) ? it : 0;
}
// The upgrade level kept on the item record, in two places the game never writes or reads (docs/spec/items.md 2: +0x06 and
// +0x44 are left as they lay in the parser's frame): +0x06 = 0x4800 | level, +0x44 = "HC" | level << 8 | a check of the
// definition and the level.  Anything else there (the parser's leftovers) is level 0.
u32 tag_check(u32 it, s32 level) {
    u32 h = 2166136261u, d = W(it);
    for (int k = 0; k < 4; k++) h = (h ^ ((d >> (8 * k)) & 0xff)) * 16777619u;
    h = (h ^ (u32)level) * 16777619u;
    return h & 0xff;
}
s32 upgrade_of(u32 it) {
    if (!it) return 0;
    u32 t = W(it + 0x44);
    s32 level = (s32)((t >> 8) & 0xff);
    if ((t >> 16) != 0x4843 || level < 1 || level > 20 || (t & 0xff) != tag_check(it, level) || H(it + 6) != (u16)(0x4800 | level)) return 0;
    return level;
}
void set_upgrade(u32 it, s32 level) {
    PH(it + 6, (u16)(0x4800 | level));
    PW(it + 0x44, 0x48430000u | ((u32)level << 8) | tag_check(it, level));
}
// the statistic curve (percent), linear between the tuning's points
s32 curve(s32 stat) {
    const Tuning& t = g_tuning;
    if (stat <= t.scale_stat[0]) return t.scale_value[0];
    for (int k = 1; k < 7; k++)
        if (stat <= t.scale_stat[k]) {
            s32 span = std::max(1, t.scale_stat[k] - t.scale_stat[k - 1]);
            return t.scale_value[k - 1] + (t.scale_value[k] - t.scale_value[k - 1]) * (stat - t.scale_stat[k - 1]) / span;
        }
    return t.scale_value[6];
}
char grade(s32 coefficient) {
    return coefficient >= 175 ? 'S' : coefficient >= 140 ? 'A' : coefficient >= 90 ? 'B' : coefficient >= 60 ? 'C' : coefficient >= 25 ? 'D' : coefficient > 0 ? 'E' : '-';
}
bool can_two_hand(s32 cls, u32 record) { return cls != WC_NONE && cls != WC_BOW && (int8_t)B(record + REC_WEAPON_CLASS) != 7; }
// The upgrade material: the lowest-level reagent of the game's item table whose name says it is a whetstone (a per-machine
// cache of a static table: the same row on every machine).
u32 g_material = 1;                     // 1: not looked for yet
u32 material_def() {
    if (g_material != 1) return g_material;
    g_material = 0;
    s32 best = 1 << 30;
    for (u32 row = G_ITEM_DEFS; ok(row, 0x40) && W(row); row += 0x40) {
        bool reagent = (W(row + 0x28 + 4) & 0x8) != 0;       // definition flag bit 35: the reagent group
        s32 level = (s16)H(row + 4);
        if (reagent && name_has(row, "whetstone") && level < best) { best = level; g_material = row; }
        if (row > G_ITEM_DEFS + 0x40 * 2000) break;
    }
    return g_material;
}
s32 materials(u32 record) {
    u32 m = material_def();
    if (!m) return 0;
    s32 n = 0;
    for (u32 b = 0; b < 3; b++) {
        u32 bag = record + REC_BAGS + b * BAG_STRIDE;
        s32 count = std::min<s32>(64, (s32)W(bag + BAG_COUNT));
        for (s32 i = 0; i < count; i++) if (W(bag + (u32)i * ITEM) == m) n += std::max<s32>(1, (s16)H(bag + (u32)i * ITEM + 4));
    }
    return n;
}
// spends `n` of the material, from the last stacks first; a stack used up leaves the bag through the game's own removal
void spend_materials(Ctx* c, int slot, u32 record, s32 n) {
    u32 m = material_def();
    for (s32 b = 2; b >= 0 && n > 0; b--) {
        u32 bag = record + REC_BAGS + (u32)b * BAG_STRIDE;
        for (s32 i = std::min<s32>(64, (s32)W(bag + BAG_COUNT)) - 1; i >= 0 && n > 0; i--) {
            u32 it = bag + (u32)i * ITEM;
            if (W(it) != m) continue;
            s32 have = std::max<s32>(1, (s16)H(it + 4));
            s32 take = std::min(have, n);
            n -= take;
            if (have > take) PH(it + 4, (u16)(s16)(have - take));
            else call(c, INVENTORY_REMOVE, (u32)slot, (u32)i, (u32)b, 0);
        }
    }
}
// within save_reach of one of this level's save points (the block's list, filled by Savepoint_run)
bool near_save(u32 P) {
    if ((u32)SR(H_SAVES_LEVEL) != level_figure()) return false;
    float r = (float)g_tuning.save_reach;
    for (s32 k = 0, n = std::max(0, std::min(8, SR(H_SAVES))); k < n; k++) {
        float dx = F(P + O_POS) - F(SOULS_BASE + H_SAVES + 4 + 12 * (u32)k), dy = F(P + O_POS + 4) - F(SOULS_BASE + H_SAVES + 8 + 12 * (u32)k);
        if (dx * dx + dy * dy <= r * r) return true;
    }
    return false;
}
s32 upgrade_gold(s32 level) { return g_tuning.upgrade_gold_base * (100 + g_tuning.upgrade_gold_step * (level - 1)) / 100; }
s32 upgrade_materials(s32 level) { return 1 + (level - 1) / std::max(1, g_tuning.upgrade_material_every); }
// the equip load, in hundredths: the game's item_getWeight of each equipped item, once each (per unit for a stack;
// the ammunition slot is not counted)
s32 equip_load(Ctx* c, u32 record) {
    u32 seen[17];
    int n = 0;
    float sum = 0;
    for (u32 k = 0; k < 17; k++) {
        u32 it = W(record + REC_EQUIP + 4 * k);
        if (k == 8 || !ok(it, ITEM) || !ok(W(it), 0x40)) continue;
        bool again = false;
        for (int j = 0; j < n; j++) again |= seen[j] == it;
        if (again) continue;
        seen[n++] = it;
        call(c, ITEM_GET_WEIGHT, it);
        float w = flt(g_f0);
        s32 count = (s16)H(it + 4);
        if (count > 1) w = w / (float)count;
        if (w > 0 && w < 10000.0f) sum = sum + w;
    }
    return (s32)(sum * 100.0f);
}
// Everything about the weapon in hand, written to the weapons part of the block (each player tick, every machine alike).
struct Weapon { u32 item = 0; s32 cls = WC_NONE, level = 0, damage = 100, scale = 0; bool two = false; };
Weapon weapon_now(int slot) {
    Weapon w;
    u32 record = G_PLAYERS + (u32)slot * REC;
    w.item = weapon_item(record);
    w.cls = w.item ? weapon_class(W(w.item)) : WC_NONE;
    w.level = upgrade_of(w.item);
    w.two = WR(slot, W_TWOHAND) != 0 && can_two_hand(w.cls, record);
    const Tuning& t = g_tuning;
    s32 corr = 100 + t.upgrade_correct_percent * w.level;
    s32 str = (s32)W(record + REC_STR), dex = (s32)W(record + REC_DEX), in = (s32)W(record + REC_INT);
    if (w.two) str = str * t.twohand_strength_percent / 100;
    w.scale = (t.wc_str[w.cls] * corr / 100 * curve(str) + t.wc_dex[w.cls] * corr / 100 * curve(dex) + t.wc_int[w.cls] * corr / 100 * curve(in)) / 100;
    w.damage = 100 + w.level * t.upgrade_damage_tenths / 10 + w.scale;
    return w;
}
void weapon_numbers(Ctx* c, int slot, u32 record) {
    const Tuning& t = g_tuning;
    Weapon w = weapon_now(slot);
    s32 load = equip_load(c, record);
    s32 cap = t.load_base + t.load_per_endurance * AR(slot, A_END) + t.load_per_strength * (s32)W(record + REC_STR);
    if (cap < 100) cap = 100;
    s32 share = (s32)((int64_t)load * 100 / cap);
    s32 tier = share < t.load_light ? 0 : share < t.load_medium ? 1 : share <= 100 ? 2 : 3;
    s32 corr = 100 + t.upgrade_correct_percent * w.level;
    u32 grades = (u32)(u8)grade(t.wc_str[w.cls] * corr / 100) | (u32)(u8)grade(t.wc_dex[w.cls] * corr / 100) << 8 | (u32)(u8)grade(t.wc_int[w.cls] * corr / 100) << 16;
    WW(slot, W_CLASS, w.cls); WW(slot, W_LOAD, load); WW(slot, W_CAP, cap); WW(slot, W_TIER, tier); WW(slot, W_UPG, w.level);
    WW(slot, W_GRADES, (s32)grades); WW(slot, W_SCALE, w.scale); WW(slot, W_DMG, w.damage);
    WW(slot, W_MATS, materials(record));
    s32 next = std::min(w.level + 1, t.upgrade_max);
    WW(slot, W_GOLD_NEXT, w.level < t.upgrade_max ? upgrade_gold(next) : 0);
    WW(slot, W_MATS_NEXT, w.level < t.upgrade_max ? upgrade_materials(next) : 0);
}
// The weapon art: the game's own skill of the art's kind cast at the level 1 + upgrade, as Player_castSkill casts it
// (the skill's slot 2, then creature_addSpell) - without the player's rank of it and without its mana price (the mode's
// own cost is taken).  The spin and the slam play clips that a character's animation lump may not have: then the lunge.
bool has_clip(Ctx* c, u32 P, const char* name) {
    u32 table = W(P + O_ANIM_TABLE), lump = table ? W(table) : 0;
    if (!lump) return false;
    u32 at = SOULS_BASE + H_SCRATCH + 0x10;
    size_t n = strlen(name);
    for (size_t k = 0; k <= n && k < 0x2f; k++) PB(at + (u32)k, (u8)name[k]);
    return call(c, RES_FIND, lump, at) != 0;
}
s32 cast_art(Ctx* c, u32 P, s32 kind, s32 level) {
    if ((kind == ART_SPIN && !has_clip(c, P, "cyclone1.anm")) || (kind == ART_SLAM && !has_clip(c, P, "dha_quake.anm"))) kind = ART_LUNGE;
    u32 skill = W(G_SKILL_TABLE + 4 * (u32)SKILL_OF_ART[kind]);
    u32 vt = ok(skill, 0x68) ? W(skill + 0x60) : 0;
    u32 fn = ok(vt, 0x20) ? W(vt + 2 * 8 + 4) : 0;
    if (!fn) return ART_NONE;
    u32 pos = SOULS_BASE + H_SCRATCH;
    PW(pos, W(P + O_POS)); PW(pos + 4, W(P + O_POS + 4)); PF(pos + 8, F(P + O_POS + 8) + 40.0f);
    u32 spell = call(c, fn, skill, (u32)level, P, 0, 0, pos, (u32)(s32)(s16)H(P + O_FACING));
    if (spell && ok(spell, 0x18)) call(c, CREATURE_ADD_SPELL, P, spell);
    return kind;
}

// ---- the attributes and the spellbook (docs/issues/native-souls-combat.md 2.9) -------------------------------------------
s32 class_of(u32 record) { s32 c = (s32)W(record + REC_CLASS); return c < 0 || c > 6 ? 0 : c; }
// The save spot: 16 bytes of the player record that the game never reads or writes (soulscombat.h).  It is on the memory card
// with the character and goes to every machine at a net game's launch with the whole record.
struct Spot { bool valid = false; s32 mind = 0, end = 0, faith = 0; u32 attuned = 0; };
// 48 bits, low first: Mind, Endurance, Faith (7 bits each: the points spent), the attuned ability records (15 bits), the tag
// 0xa (4 bits), a check of the 40 bits below it (8 bits)
u64 spot_bits(u32 record) { u64 v = 0; for (u32 k = 0; k < 6; k++) v |= (u64)B(record + REC_SPOT + k) << (8 * k); return v; }
u8 spot_check(u64 low40) {
    u32 h = 2166136261u;
    for (u32 k = 0; k < 5; k++) h = (h ^ (u32)((low40 >> (8 * k)) & 0xff)) * 16777619u;
    return (u8)(h & 0xff);
}
Spot spot_read(u32 record) {
    Spot sp;
    u64 v = spot_bits(record), low = v & 0xffffffffffull;
    if (((v >> 36) & 0xf) != 0xa || (u8)(v >> 40) != spot_check(low)) return sp;
    sp.valid = true;
    sp.mind = (s32)(v & 0x7f); sp.end = (s32)((v >> 7) & 0x7f); sp.faith = (s32)((v >> 14) & 0x7f);
    sp.attuned = (u32)((v >> 21) & 0x7fff);
    return sp;
}
void spot_write(u32 record, const Spot& sp) {
    auto f = [](s32 x) { return (u64)std::max(0, std::min(127, x)); };
    u64 low = f(sp.mind) | f(sp.end) << 7 | f(sp.faith) << 14 | (u64)(sp.attuned & 0x7fff) << 21 | (u64)0xa << 36;
    u64 v = low | (u64)spot_check(low) << 40;
    for (u32 k = 0; k < 6; k++) PB(record + REC_SPOT + k, (u8)(v >> (8 * k)));
}
// The ability records (the game's own skill bindings: docs/player.md): the spellbook is every record with a skill (not the
// older heavy attack, which the mode's hold of the attack button is)
u32 ability(u32 record, int k) { return record + REC_ABILITIES + (u32)k * ABILITY; }
s32 ability_id(u32 record, int k) { return (s16)H(ability(record, k) + 0x20); }
bool in_book(u32 record, int k) { s32 id = ability_id(record, k); return id >= 1 && id <= 101 && id != ID_HEAVY; }
bool skill_record(u32 rec) {
    for (u32 k = 0; k < 0x20; k++) {
        u8 a = B(rec + k), b = B(SKILL_RECORD_NAME + k);
        if (a != b) return false;
        if (!a) return true;
    }
    return true;
}
u32 skill_of(s32 id) { u32 sk = id >= 1 && id <= 101 ? W(G_SKILL_TABLE + 4 * (u32)id) : 0; return ok(sk, 0x68) ? sk : 0; }
s32 rank_of(u32 record, s32 id) {
    for (u32 k = 0; k < 48; k++) {
        s32 i = (s16)H(record + REC_RANKS + 4 * k);
        if (i == -1) break;
        if (i == id) return (s16)H(record + REC_RANKS + 4 * k + 2);
    }
    return 0;
}
// a record whose hits are a spell's (scaled by Intelligence and Faith): a skill cast as a spell - not a passive, not the bow
// and axe skills (kind 8, they fire through the shot); of the older records not the arrows
bool scaled_spell(u32 record, int k) {
    if (k < 0 || k > 14 || !in_book(record, k)) return false;
    s32 id = ability_id(record, k);
    if (skill_record(ability(record, k))) { u32 sk = skill_of(id); s32 kind = sk ? (s32)W(sk + 8) : 3; return kind != 3 && kind != 8; }
    return id != 4 && id != 5 && id != 6 && id != 0x12 && id != 0x13;
}
// The seven attributes: Vigor, Strength, Dexterity, Intelligence the game's own (effective) statistics; Mind, Endurance, Faith
// the class's start in the mode plus the points spent on them
struct Attr { s32 v[7] = {0, 0, 0, 0, 0, 0, 0}; s32 cls = 0, level = 1, unspent = 0, spent = 0, slots = 1; Spot sp; };
Attr attributes_of(u32 record) {
    const Tuning& t = g_tuning;
    Attr a;
    a.cls = class_of(record);
    a.sp = spot_read(record);
    a.v[0] = (s32)W(record + REC_STA);
    a.v[1] = t.start_mind[a.cls] + a.sp.mind;
    a.v[2] = t.start_endurance[a.cls] + a.sp.end;
    a.v[3] = (s32)W(record + REC_STR);
    a.v[4] = (s32)W(record + REC_DEX);
    a.v[5] = (s32)W(record + REC_INT);
    a.v[6] = t.start_faith[a.cls] + a.sp.faith;
    a.level = (int8_t)B(record + REC_LEVEL);
    a.spent = a.sp.mind + a.sp.end + a.sp.faith;
    a.unspent = std::max(0, std::max(0, a.level - 1) * t.points_per_level - a.spent);
    s32 most = std::max(1, std::min(9, t.slot_max));
    a.slots = std::max(1, std::min(most, t.slot_base + a.v[1] / std::max(1, t.slot_per_mind) + a.v[5] / std::max(1, t.slot_per_int)));
    return a;
}
// the attuned ability records (castable): kept with the character once the screen changed anything, else the first spells of
// the book; never more than the slots (the first ones in record order)
u32 attuned_of(u32 record, const Attr& a) {
    u32 want = a.sp.valid ? a.sp.attuned : 0x7fff, out = 0;
    s32 n = 0;
    for (int k = 0; k < 15 && n < a.slots; k++)
        if (in_book(record, k) && ((want >> k) & 1)) { out |= 1u << k; n++; }
    return out;
}
s32 stamina_most(int slot) { s32 m = AR(slot, A_STAMINA_MAX); return m > 0 ? m : g_tuning.stamina_max; }
// Everything of the attributes and the spellbook, written to the block (each player tick, every machine alike).  With `costs`
// the mana cost of each ability record too (the skill's own price at its rank: its virtual slot 5).
void stats_numbers(Ctx* c, int slot, u32 record, bool costs) {
    const Tuning& t = g_tuning;
    Attr a = attributes_of(record);
    for (u32 k = 0; k < 7; k++) AW(slot, A_VIG + 4 * k, a.v[k]);
    AW(slot, A_UNSPENT, a.unspent); AW(slot, A_SPENT, a.spent); AW(slot, A_SLOTS, a.slots); AW(slot, A_SPOT, a.sp.valid ? 1 : 0);
    AW(slot, A_LEVEL, a.level); AW(slot, A_CLASS, a.cls);
    u32 book = 0, attuned = attuned_of(record, a);
    s32 used = 0;
    for (int k = 0; k < 15; k++) if (in_book(record, k)) book |= 1u << k;
    for (int k = 0; k < 15; k++) used += (attuned >> k) & 1;
    AW(slot, A_BOOK, (s32)book); AW(slot, A_ATTUNED, (s32)attuned); AW(slot, A_USED, used);
    AW(slot, A_STAMINA_MAX, std::max(100, t.stamina_max + a.sp.end * t.stamina_per_endurance));
    AW(slot, A_SPELL_PCT, 100 + (t.sc_int[a.cls] * curve(a.v[5]) + t.sc_faith[a.cls] * curve(a.v[6])) / 100);
    AW(slot, A_SPELL_GRADES, (s32)((u32)(u8)grade(t.sc_int[a.cls]) | (u32)(u8)grade(t.sc_faith[a.cls]) << 8));
    if (!costs) return;
    u32 at = SOULS_BASE + COST_BASE + (u32)slot * 0x40;
    for (int k = 0; k < 15; k++) {
        float cost = 0;
        s32 rank = 0;
        if (in_book(record, k)) {
            u32 rec = ability(record, k);
            s32 id = ability_id(record, k);
            rank = rank_of(record, id);
            if (skill_record(rec)) {
                u32 sk = skill_of(id), vt = sk ? W(sk + 0x60) : 0, fn = ok(vt, 0x30) ? W(vt + 5 * 8 + 4) : 0;
                if (fn) { call(c, fn, sk, (u32)std::max(1, rank)); cost = flt(g_f0); }
            } else cost = F(rec + 0x2c);
        }
        s32 tenths = cost > 0 && cost < 6000.0f ? (s32)(cost * 10.0f + 0.5f) : 0;
        PH(at + 2 * (u32)k, (u16)tenths);
        PB(at + 0x20 + (u32)k, (u8)std::max(0, std::min(255, rank)));
    }
}
// The maximum mana with Mind: the game's own maximum (it rewrites it whenever it recalculates the character: a level gained,
// an item put on, a new object) plus mana_per_mind_permille of it per Mind point spent.  The game's recalculation also puts
// the mana down to its own maximum: what was over it is given back.
void apply_mana(int slot, u32 record) {
    const Tuning& t = g_tuning;
    s32 mind = spot_read(record).mind;
    u32 m = W(record + REC_MANA_MAX), written = (u32)AR(slot, A_MANA_WRITTEN);
    if (m != written) {
        float last = flt((u32)AR(slot, A_MANA_LAST));
        if (written != 0 && W(record + REC_MANA) == m && last > flt(m)) PF(record + REC_MANA, last);
        AW(slot, A_MANA_BASE, (s32)m);
    }
    float base = flt((u32)AR(slot, A_MANA_BASE));
    float most = base + base * ((float)(mind * t.mana_per_mind_permille) / 1000.0f);
    if (!(most >= 0.0f) || most > 1000000.0f) most = base;
    PF(record + REC_MANA_MAX, most);
    AW(slot, A_MANA_WRITTEN, (s32)bits(most));
    if (F(record + REC_MANA) > most) PF(record + REC_MANA, most);
}
// The character screen at a save point, one press of the lockstep row a tick: up / down a row (Mind, Endurance, Faith, then
// each spell of the book), right a point on the attribute or the spell put in a slot, left the spell taken out of its slot.
// Returns false when the press was refused.
bool screen_press(int slot, u32 record, u32 nav) {
    const Tuning& t = g_tuning;
    Attr a = attributes_of(record);
    int rec_of_row[15], books = 0;
    for (int k = 0; k < 15; k++) if (in_book(record, k)) rec_of_row[books++] = k;
    s32 rows = 3 + books, row = std::max(0, std::min(rows - 1, AR(slot, A_ROW)));
    bool done = true;
    if (nav & PAD_UP) row = (row + rows - 1) % rows;
    else if (nav & PAD_DOWN) row = (row + 1) % rows;
    else if (nav & (PAD_RIGHT | PAD_LEFT)) {
        Spot sp = a.sp;
        u32 attuned = attuned_of(record, a);
        if (!sp.valid) { sp.valid = true; sp.attuned = attuned; }
        if (row < 3) {
            s32* f = row == 0 ? &sp.mind : row == 1 ? &sp.end : &sp.faith;
            s32 start = row == 0 ? t.start_mind[a.cls] : row == 1 ? t.start_endurance[a.cls] : t.start_faith[a.cls];
            if ((nav & PAD_RIGHT) && a.unspent > 0 && start + *f < t.stat_max && *f < 127) {
                (*f)++;
                spot_write(record, sp);
                AW(slot, A_POINTS, AR(slot, A_POINTS) + 1);
                bump(H_POINTS);
                if (g_log) fprintf(stderr, "souls: tick %u: p%d spends a point on %s: %d (%d left)\n", frame_now(), slot, row == 0 ? "Mind" : row == 1 ? "Endurance" : "Faith",
                                   start + *f, a.unspent - 1);
            } else done = false;
        } else {
            int k = rec_of_row[row - 3];
            s32 used = 0;
            for (int q = 0; q < 15; q++) used += (attuned >> q) & 1;
            bool in = ((attuned >> k) & 1) != 0;
            if ((nav & PAD_RIGHT) && !in && used < a.slots) sp.attuned = attuned | 1u << k;
            else if ((nav & PAD_LEFT) && in) sp.attuned = attuned & ~(1u << k);
            else done = false;
            if (done) {
                spot_write(record, sp);
                AW(slot, A_SWAPS, AR(slot, A_SWAPS) + 1);
                bump(H_SWAPS);
                if (g_log) fprintf(stderr, "souls: tick %u: p%d spell %d (record %d) %s a slot\n", frame_now(), slot, ability_id(record, k), k, in ? "out of" : "into");
            }
        }
    }
    AW(slot, A_ROW, row);
    return done;
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
        bool fresh = g_last_object[slot] != P;
        // the attributes and the spellbook first: the stamina bar's length comes from Endurance
        stats_numbers(c, slot, record, fresh || frame_now() % 30 == 0 || AR(slot, A_OPEN) != 0);
        if (fresh) {
            // a new object: the game's own figures of the character made anew (so that the maximum mana the mode adds Mind to
            // is the game's own, whatever the record was saved with)
            call(c, PLAYER_RECALC_STATS, 0);
            AW(slot, A_OPEN, 0); AW(slot, A_SPELL_T, -1);
        }
        if (fresh) {
            // a new object: the level's entry or a respawn - the flasks are full again (the second part is kept)
            g_last_object[slot] = P; reset_slot(slot);
            if (ER(slot, E_FLASKS) < t.flask_count) { EW(slot, E_FLASKS, t.flask_count); bump(H_REFILLS); }
            EW(slot, E_PARRY, -1); EW(slot, E_DRINK, -1); EW(slot, E_RIPOSTE, 0); EW(slot, E_COUNTER, 0);
            g_riposte_target[slot] = 0;
            WW(slot, W_ART_T, -1); WW(slot, W_ART_KIND, 0); WW(slot, W_RECOVER, 0); WW(slot, W_SWING, -1); WW(slot, W_ART_CD, 0); WW(slot, W_BUFFER, 0);
        }
        SW(H_UPDATES, SR(H_UPDATES) + 1);
        // a test aid for the runs (0 outside a test): the word H_TEST_MAT = slot + 1 | count << 8, written by every copy in
        // the same lockstep tick (a room's tick-do; a poke offline), gives that player `count` upgrade materials through
        // the game's own inventory_giveItem, as a pick-up would
        u32 aid = (u32)SR(H_TEST_MAT);
        if ((aid & 0xff) == (u32)slot + 1 && material_def()) {
            u32 m = material_def(), it = SOULS_BASE + H_ITEM_SCRATCH;
            for (u32 k = 0; k < ITEM; k += 4) PW(it + k, 0);
            PW(it, m); PH(it + 4, (u16)std::max<u32>(1, (aid >> 8) & 0xff)); PW(it + 8, W(m + 0x28)); PW(it + 12, W(m + 0x2c) );
            PH(it + 0x20, 0xffff);
            for (u32 k = 0; k < 4; k++) PH(it + 0x24 + 8 * k, 0xffff);
            s32 got = (s32)call(c, INVENTORY_GIVE, (u32)slot, it, 0);
            SW(H_TEST_MAT, 0);
            if (g_log) fprintf(stderr, "souls: tick %u: p%d given %u upgrade materials (bag index %d)\n", frame_now(), slot, (aid >> 8) & 0xff, got);
        }
        // a test aid for the runs (0 outside a test): the word H_TEST_XP = slot + 1 | amount << 8 gives that player `amount`
        // experience through the game's own player_giveExp (its levels, points and refill), written by every copy in the same
        // lockstep tick
        u32 xp = (u32)SR(H_TEST_XP);
        if ((xp & 0xff) == (u32)slot + 1) {
            SW(H_TEST_XP, 0);
            call(c, PLAYER_GIVE_EXP, (u32)slot, xp >> 8);
            if (g_log) fprintf(stderr, "souls: tick %u: p%d given %u experience: level %d\n", frame_now(), slot, xp >> 8, (int)(int8_t)B(record + REC_LEVEL));
            stats_numbers(c, slot, record, false);
        }
        // a test aid for the room runs (0 outside a test): the word H_TEST_POSE = slot + 1, written by every copy in the same
        // lockstep tick, puts that player 40 units on the +x side of the nearest living creature (the collision grid in its
        // order, the first of equal distances), level with it and facing it (no trigonometry: every build alike); its grid
        // cell is left as it was, as the drop spot's aid does
        if (SR(H_TEST_POSE) == slot + 1) {
            SW(H_TEST_POSE, 0);
            u32 best = 0;
            float best_d = 0;
            for (u32 cell = 0; cell < 120 * 120; cell++) {
                u32 node = W(G_GRID + cell * 4);
                for (int guard = 0; node && ok(node, 16) && guard < 256; guard++, node = W(node)) {
                    u32 V = W(node + 12);
                    if (!creature(V)) continue;
                    float d = ground2(V, P);
                    if (!best || d < best_d) { best = V; best_d = d; }
                }
            }
            if (best) {
                PF(P + O_POS, F(best + O_POS) + 40.0f);
                PW(P + O_POS + 4, W(best + O_POS + 4));
                PW(P + O_POS + 8, W(best + O_POS + 8));
                PH(P + O_FACING, 0x8000);
            }
            if (g_log) fprintf(stderr, "souls: tick %u: p%d posed by %s\n", frame_now(), slot, best ? "a creature" : "nothing (no creature)");
        }
        weapon_numbers(c, slot, record);    // the weapon in hand, the equip load and its tier (every machine alike)
        WW(slot, W_NEAR, near_save(P) ? 1 : 0);
        apply_mana(slot, record);           // the maximum mana with Mind
    } else if (g_ghost.object != P) { g_ghost = Ghost(); g_ghost.object = P; }
    s32 stamina = SR(slot_off(slot, S_STAMINA));
    s32 state = (s32)W(P + P_STATE);
    int cls = (int8_t)B(record + REC_WEAPON_CLASS);
    bool ranged = cls == 4 || cls == 6;
    s32 wc = WR(slot, W_CLASS);
    if (wc < 0 || wc >= WC_COUNT) wc = WC_NONE;
    s32 tier = std::max(0, std::min(3, WR(slot, W_TIER)));
    u32 pad = G_PADS + (u32)slot * PAD;
    u32 held = W(pad + PAD_HELD), pressed = W(pad + PAD_PRESSED), nh = held, np = pressed;
    u32 attack = W(G_BTN_ATTACK + (u32)slot * 4) & 0xffff, block = W(G_BTN_BLOCK + (u32)slot * 4) & 0xffff;
    u32 potion = W(G_BTN_POTION_A + (u32)slot * 4) & 0xffff;
    u32 swap = W(G_BTN_SWAP + (u32)slot * 4) & 0xffff, use = W(G_BTN_USE + (u32)slot * 4) & 0xffff;
    u32 potion_b = W(G_BTN_POTION_B + (u32)slot * 4) & 0xffff;
    u32 ability_a = W(G_BTN_ABILITY_A + (u32)slot * 4) & 0xffff, ability_b = W(G_BTN_ABILITY_B + (u32)slot * 4) & 0xffff;
    bool open = AR(slot, A_OPEN) != 0, screen_toggle = false, cast_refused = false;
    u32 nav = 0;
    s16 recast0 = (s16)H(P + P_RECAST);
    s32 atk = copy ? g_ghost.atk : SR(slot_off(slot, S_ATK)), l3 = copy ? g_ghost.l3 : SR(slot_off(slot, S_L3));
    bool light = false, heavy = false, dodge = false, refused = false, counter = false, parry = false, drink = false;
    bool art = false, toggle_two = false, upgrade = false;
    bool broken_guard = SR(slot_off(slot, S_BROKEN)) > 0;
    // the health potion button drinks a flask; the game's own potions are not used in the mode
    if (potion) {
        if (pressed & potion) drink = true;
        nh &= ~potion; np &= ~potion;
    }
    // L3 held and another button pressed: the weapon art (attack), two-handing (swap), an upgrade (use); the presses are
    // spent (L3 is then neither a dodge nor a sprint, and the button is not given to the game)
    if ((held & L3) && l3 >= 0) {
        if (attack && (pressed & attack)) { art = true; atk = -100000; nh &= ~attack; np &= ~attack; }
        else if (swap && (pressed & swap)) { toggle_two = true; nh &= ~swap; np &= ~swap; }
        else if (use && (pressed & use)) { upgrade = true; nh &= ~use; np &= ~use; }
        else if (potion_b && (pressed & potion_b)) { screen_toggle = true; nh &= ~potion_b; np &= ~potion_b; }
        if (art || toggle_two || upgrade || screen_toggle) l3 = -100000;
    }
    if (l3 < 0 && (held & L3) && swap) { nh &= ~swap; np &= ~swap; }   // the swap stays the game's only without L3 spent
    // attack: a tap is the game's swing, a hold its heavy attack; pressed in the guard-counter window it is a guard counter
    if (attack && !ranged) {
        if ((held & attack) && atk == 0 && ER(slot, E_COUNTER) > 0 && (state == 2 || state == 8)) {
            counter = true;
            atk = -100000;                          // the press is spent: neither a tap nor a hold follows from it
            nh &= ~attack; np &= ~attack;
        } else if (held & attack) {
            atk++;
            nh &= ~attack; np &= ~attack;
            if (atk >= t.heavy_hold) heavy = true;     // held long enough: the heavy starts as soon as the character can (a swing ending)
        } else {
            if (atk > 0 && atk < t.heavy_hold) light = true;
            atk = 0;
        }
        // the class's recovery after a swing: a tap in it waits (buffered) until the recovery is over
        if (!copy) {
            s32 recover = WR(slot, W_RECOVER), buffered = WR(slot, W_BUFFER);
            if (light && recover > 0 && state == 2) { light = false; WW(slot, W_BUFFER, 1); }
            else if (!light && buffered > 0 && recover == 0 && state == 2 && !(held & attack)) { light = true; WW(slot, W_BUFFER, 0); }
        }
        if (light) { if (stamina > 0) { nh |= attack; np |= attack; } else { light = false; refused = true; } }
        if (heavy && stamina <= 0) { heavy = false; refused = atk == t.heavy_hold; }
        if (counter && stamina <= 0) { counter = false; refused = true; }
    } else if (attack && ranged && state == 2 && stamina <= 0 && (held & attack)) {
        nh &= ~attack; np &= ~attack;
        if (pressed & attack) refused = true;
    }
    // L3: a tap is a dodge, a hold a sprint; pressed while the block is held, a parry (the press is then spent)
    if ((held & L3) && l3 == 0 && block && (held & block) && !broken_guard && (state == 2 || state == 8)) {
        l3 = -100000;
        parry = true;
    } else if (held & L3) { if (l3 >= 0) l3++; }
    else { if (l3 > 0 && l3 < t.sprint_hold) dodge = true; l3 = 0; }
    float lx = F(pad + PAD_LX), ly = F(pad + PAD_LY);
    bool sprint = (held & L3) && l3 >= t.sprint_hold && state == 2 && stamina > 0 && lx * lx + ly * ly > 0.25f && t.tier_sprint[tier] > 0;
    if (broken_guard && block) { nh &= ~block; np &= ~block; }
    // the character screen: the character stands, nothing of the row reaches the game, the presses are the screen's
    bool stick_held = false;
    if (open) {
        nav = pressed & (PAD_UP | PAD_DOWN | PAD_LEFT | PAD_RIGHT | block);
        light = heavy = dodge = counter = parry = drink = art = toggle_two = upgrade = sprint = false;
        refused = false;
        atk = 0;
        if (held & L3) l3 = -100000;
        nh = 0; np = 0;
        if (lx != 0.0f || ly != 0.0f) { stick_held = true; PF(pad + PAD_LX, 0.0f); PF(pad + PAD_LY, 0.0f); }
    } else {
        // the spellbook: a spell that is in no spell slot is not cast from the game's skill buttons
        u32 book = (u32)AR(slot, A_BOOK), attuned = (u32)AR(slot, A_ATTUNED);
        for (u32 b = 0; b < 2; b++) {
            u32 mask = b ? ability_b : ability_a;
            if (!mask || !((held | pressed) & mask)) continue;
            s32 k = (int8_t)B(record + REC_BUTTON_A + b);
            if (k < 0 || k > 14 || !((book >> k) & 1) || ((attuned >> k) & 1)) continue;
            nh &= ~mask; np &= ~mask;
            if (pressed & mask) cast_refused = true;
        }
    }
    if (nh != held) PW(pad + PAD_HELD, nh);
    if (np != pressed) PW(pad + PAD_PRESSED, np);
    u32 speed_bits = W(record + REC_SPEED);
    if (sprint) PF(record + REC_SPEED, flt(speed_bits) * ((float)(100 + (t.sprint_speed_percent - 100) * t.tier_sprint[tier] / 100) / 100.0f));
    bool heavy_started = false, counter_started = false, parry_started = false;
    bool can_attack = B(P + P_ON_GROUND) && W(P + P_ATTACK_REQUEST) == 0 && (int8_t)B(P + O_TRACKS) < 6 && !B(P + C_INERT) && F(record + REC_HP) > 0;
    if (heavy && state == 2 && can_attack)
        heavy_started = start_heavy(c, P, cls);
    if (heavy_started) atk = -100000;           // the hold is spent: neither another heavy nor a tap at its release
    // the guard counter starts from the block, whose clips fill the tracks: anim_start replaces the top track when the
    // state is full (docs/spec/animation.md 4), so the track count is not a condition here
    bool can_counter = B(P + P_ON_GROUND) && W(P + P_ATTACK_REQUEST) == 0 && !B(P + C_INERT) && F(record + REC_HP) > 0;
    if (counter && !copy && can_counter) {
        if (state == 8) { PB(P + P_BLOCKING, 0); PW(record + REC_BLOCK_TIMER, 0); }   // the block let go, as the game lets go of it
        counter_started = start_heavy(c, P, cls);
    }
    if (counter && !copy && !counter_started && g_log)
        fprintf(stderr, "souls: tick %u: p%d guard counter press not taken: state %d on ground %d request %u tracks %d\n", frame_now(), slot, state,
                B(P + P_ON_GROUND), W(P + P_ATTACK_REQUEST), (int)(int8_t)B(P + O_TRACKS));
    if (parry && !copy) {
        if (ER(slot, E_PARRY) < 0 && stamina > 0 && F(record + REC_HP) > 0) {
            parry_started = true;
            PB(P + P_BLOCKING, 0);              // the game raises the guard again (state 8: its own clip anim(0x84))
        } else refused = true;
    }
    float x0 = F(P + O_POS), y0 = F(P + O_POS + 4);

    g_orig_run(c);

    PW(pad + PAD_HELD, held);
    PW(pad + PAD_PRESSED, pressed);
    if (stick_held) { PF(pad + PAD_LX, lx); PF(pad + PAD_LY, ly); }
    if (sprint) PW(record + REC_SPEED, speed_bits);
    s32 now = (s32)W(P + P_STATE);
    bool dodged = false;
    s32 dodge_t = copy ? g_ghost.dodge : SR(slot_off(slot, S_DODGE));
    // a dodge may cancel a light swing of the class once it is `wc_cancel` ticks in (after its hit)
    s32 swing_t = WR(slot, W_SWING);
    bool cancel = now == 1 && t.wc_cancel[wc] >= 0 && swing_t >= t.wc_cancel[wc] && W(P + P_ATTACK_REQUEST) != 2 && !copy;
    if (dodge) {
        bool can = (now == 2 || now == 8 || cancel) && B(P + P_ON_GROUND) && !B(P + C_INERT) && F(record + REC_HP) > 0 && dodge_t < 0 &&
                   (copy || SR(slot_off(slot, S_COOL)) == 0) && !(W(G_LEVEL_FLAGS) & 0x10000000);
        if (can && t.tier_dodge_move[tier] <= 0) { can = false; refused = true; }   // overloaded: no dodge
        if (can && stamina > 0) {
            if (now == 1) { PW(P + P_ATTACK_REQUEST, 0); bump(H_CANCELS); }
            dodged = start_dodge(c, P, slot, cls);
        } else if (can) refused = true;
    }
    // the equip load's tier scales the dodge's movement (the hop's own steps this tick, made longer or shorter)
    if ((dodged || (dodge_t >= 0 && now == 0xb)) && t.tier_dodge_move[tier] != 100) {
        float k = (float)(t.tier_dodge_move[tier] - 100) / 100.0f;
        float dx = F(P + O_POS) - x0, dy = F(P + O_POS + 4) - y0;
        PF(P + O_POS, F(P + O_POS) + dx * k);
        PF(P + O_POS + 4, F(P + O_POS + 4) + dy * k);
    }
    if (copy) {
        g_ghost.atk = atk; g_ghost.l3 = l3;
        g_ghost.dodge = dodged ? 0 : (g_ghost.dodge >= 0 && now == 0xb ? g_ghost.dodge + 1 : -1);
        return;
    }
    // ---- the numbers, real players only: the same on every machine ----
    bool alive = F(record + REC_HP) > 0 && now != 4;
    s32 drink_t = ER(slot, E_DRINK);
    bool drank = false;
    if (drink && drink_t < 0 && !dodged) {
        bool can = now == 2 && B(P + P_ON_GROUND) && !B(P + C_INERT) && alive && W(P + P_ATTACK_REQUEST) == 0;
        if (can && ER(slot, E_FLASKS) > 0) drank = start_drink(c, P, cls);
        else if (can) refused = true;
        if (drank) { now = 3; drink_t = 0; if (g_log) fprintf(stderr, "souls: tick %u: p%d drinks (%d flasks)\n", frame_now(), slot, ER(slot, E_FLASKS)); }
    }
    // the weapons: two-handing, an upgrade at a save point, the weapon art
    bool art_started = false;
    if (toggle_two) {
        Weapon w = weapon_now(slot);
        if (can_two_hand(w.cls, record)) {
            WW(slot, W_TWOHAND, WR(slot, W_TWOHAND) ? 0 : 1);
            bump(H_TWOHANDS);
            if (g_log) fprintf(stderr, "souls: tick %u: p%d two-handing %s (%s)\n", frame_now(), slot, WR(slot, W_TWOHAND) ? "on" : "off", class_name(w.cls));
        } else refused = true;
    }
    if (upgrade) {
        Weapon w = weapon_now(slot);
        bool near = near_save(P);
        s32 next = w.level + 1, gold = upgrade_gold(next), need = upgrade_materials(next), have = materials(record);
        s32 money = (s32)W(record + REC_GOLD);
        if (w.item && w.cls != WC_NONE && near && alive && next <= t.upgrade_max && money >= gold && have >= need) {
            spend_materials(c, slot, record, need);
            PW(record + REC_GOLD, (u32)(money - gold));
            set_upgrade(w.item, next);
            WW(slot, W_UPGRADES, WR(slot, W_UPGRADES) + 1);
            bump(H_UPGRADES);
            if (g_log) fprintf(stderr, "souls: tick %u: p%d upgraded its %s to +%d: %d gold, %d materials (%d left), damage %d %% -> %d %%\n", frame_now(), slot,
                               class_name(w.cls), next, gold, need, materials(record), w.damage, weapon_now(slot).damage);
        } else {
            WW(slot, W_UP_REFUSED, WR(slot, W_UP_REFUSED) + 1);
            if (g_log) fprintf(stderr, "souls: tick %u: p%d upgrade refused: near a save point %d, level %d, gold %d of %d, materials %d of %d\n", frame_now(), slot,
                               near, w.level, money, gold, have, need);
        }
    }
    if (art) {
        Weapon w = weapon_now(slot);
        s32 kind = t.wc_art[w.cls];
        float mana = F(record + REC_MANA), cost = F(record + REC_MANA_MAX) * ((float)t.art_mana_percent / 100.0f);
        if (cost < 1.0f) cost = 1.0f;
        bool can = kind != ART_NONE && (now == 2 || now == 8) && B(P + P_ON_GROUND) && !B(P + C_INERT) && alive && W(P + P_ATTACK_REQUEST) == 0 &&
                   WR(slot, W_ART_CD) == 0 && WR(slot, W_ART_T) < 0 && !dodged && !drank;
        if (can && stamina > 0 && mana >= cost) {
            if (now == 8) { PB(P + P_BLOCKING, 0); PW(record + REC_BLOCK_TIMER, 0); }
            s32 done = cast_art(c, P, kind, 1 + w.level);
            if (done != ART_NONE) {
                art_started = true;
                PF(record + REC_MANA, mana - cost);
                WW(slot, W_ART_T, 0); WW(slot, W_ART_KIND, done); WW(slot, W_ART_CD, t.art_cooldown);
                WW(slot, W_ARTS, WR(slot, W_ARTS) + 1);
                bump(H_ARTS);
                now = (s32)W(P + P_STATE);
                if (g_log) fprintf(stderr, "souls: tick %u: p%d weapon art %d (%s, level %d): %.1f mana, state %d\n", frame_now(), slot, done, class_name(w.cls), 1 + w.level, cost, now);
            } else refused = true;
        } else if (can || kind == ART_NONE) refused = true;
        else if (g_log) fprintf(stderr, "souls: tick %u: p%d weapon art not taken: state %d mana %.1f of %.1f cooldown %d\n", frame_now(), slot, now, mana, cost, WR(slot, W_ART_CD));
    }
    // the attributes and the spellbook: a refused cast, a cast seen (the game's recast counter started from 0), the screen
    if (cast_refused) {
        AW(slot, A_CAST_REFUSED, AR(slot, A_CAST_REFUSED) + 1);
        bump(H_CAST_REFUSED);
        refused = true;
        if (g_log) fprintf(stderr, "souls: tick %u: p%d cast refused: the spell is in no spell slot\n", frame_now(), slot);
    }
    s32 spell_t = AR(slot, A_SPELL_T);
    if (recast0 <= 0 && (s16)H(P + P_RECAST) > 0) {
        s32 k = (int8_t)B(record + REC_BUTTON_A + (H(record + REC_SELECTED) == 1 ? 1u : 0u));
        if (scaled_spell(record, k)) {
            spell_t = 0;
            AW(slot, A_CASTS, AR(slot, A_CASTS) + 1);
            bump(H_CASTS);
            if (g_log) fprintf(stderr, "souls: tick %u: p%d casts skill %d (record %d): its hits x %d %%\n", frame_now(), slot, ability_id(record, k), k, AR(slot, A_SPELL_PCT));
        }
    } else if (spell_t >= 0) {
        spell_t++;
        if (spell_t > t.spell_hit_ticks || !alive || (now == 0 && SR(slot_off(slot, S_LAST_STATE)) != 0)) spell_t = -1;
    }
    AW(slot, A_SPELL_T, spell_t);
    if (screen_toggle) {
        if (open) AW(slot, A_OPEN, 0);
        else if (alive && now == 2 && B(P + P_ON_GROUND) && near_save(P)) {
            AW(slot, A_OPEN, 1); AW(slot, A_ROW, 0); AW(slot, A_OPENED, AR(slot, A_OPENED) + 1);
        } else refused = true;
        if (g_log) fprintf(stderr, "souls: tick %u: p%d character screen %s\n", frame_now(), slot, AR(slot, A_OPEN) ? "open" : open ? "closed" : "refused");
    } else if (open) {
        if (!alive || now != 2 || !near_save(P) || (nav & block)) {
            AW(slot, A_OPEN, 0);
            if (g_log) fprintf(stderr, "souls: tick %u: p%d character screen closed\n", frame_now(), slot);
        } else if (nav && !screen_press(slot, record, nav)) refused = true;
    }
    apply_mana(slot, record);
    AW(slot, A_MANA_LAST, (s32)W(record + REC_MANA));
    SW(slot_off(slot, S_ATK), atk);
    SW(slot_off(slot, S_L3), l3);
    u32 flags = (u32)SR(slot_off(slot, S_FLAGS)) & (FL_HEAVY | FL_COUNTER_HEAVY);
    // a heavy attack of the mode that was left before its hit frame (the block taken in its combo window, a stagger)
    // leaves no heavy request behind: the game would otherwise keep request 2 in state 2 and 8 and start no swing
    if (((flags & FL_HEAVY) || heavy_started || counter_started) && now != 1 && W(P + P_ATTACK_REQUEST) == 2) {
        PW(P + P_ATTACK_REQUEST, 0);
        if (g_log) fprintf(stderr, "souls: tick %u: p%d heavy left in state %d: its request cleared\n", frame_now(), slot, now);
    }
    s32 last = SR(slot_off(slot, S_LAST_STATE)), combo = (int8_t)B(P + P_COMBO);
    bool spent = false;
    s32 per = t.wc_stamina[wc];
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
    s32 iframe_last = t.dodge_iframe_last * t.tier_iframes[tier] / 100;
    if (dodge_t >= 0) flags |= FL_DODGE;
    if (dodge_t >= t.dodge_iframe_first && dodge_t <= iframe_last) flags |= FL_IFRAMES;
    if (art_started) { charge(slot, t.cost_heavy * t.art_stamina_percent / 100 * per / 100); spent = true; }
    if (heavy_started || counter_started) {
        charge(slot, t.cost_heavy * per / 100); spent = true; flags |= FL_HEAVY;
        SW(slot_off(slot, S_HEAVIES), SR(slot_off(slot, S_HEAVIES)) + 1);
        if (counter_started) {
            flags |= FL_COUNTER_HEAVY;
            EW(slot, E_COUNTER, 0);
            EW(slot, E_COUNTERS, ER(slot, E_COUNTERS) + 1);
            bump(H_COUNTERS);
            if (g_log) fprintf(stderr, "souls: tick %u: p%d guard counter\n", frame_now(), slot);
        }
    } else if (now == 1 && W(P + P_ATTACK_REQUEST) != 2 && (last != 1 || combo != SR(slot_off(slot, S_LAST_COMBO)))) {
        charge(slot, t.cost_light * per / 100); spent = true; flags &= ~(FL_HEAVY | FL_COUNTER_HEAVY);
        SW(slot_off(slot, S_LIGHTS), SR(slot_off(slot, S_LIGHTS)) + 1);
    } else if (now == 0 && last != 0) { charge(slot, t.cost_ranged * per / 100); spent = true; }
    if (now != 1) flags &= ~(FL_HEAVY | FL_COUNTER_HEAVY);
    // the swing's own clock (for the dodge cancel) and the class's recovery after it
    if (now == 1) swing_t = (last != 1 || combo != SR(slot_off(slot, S_LAST_COMBO))) ? 0 : swing_t + 1;
    else swing_t = -1;
    WW(slot, W_SWING, swing_t);
    s32 recover = WR(slot, W_RECOVER);
    if (last == 1 && now != 1 && now != 0xb) recover = t.wc_recovery[wc];
    else if (recover > 0) recover--;
    WW(slot, W_RECOVER, recover);
    if (WR(slot, W_BUFFER) > 0) WW(slot, W_BUFFER, WR(slot, W_BUFFER) >= 30 ? 0 : WR(slot, W_BUFFER) + 1);   // a buffered tap waits at most half a second
    // the weapon art's own clock: it ends when the character leaves the art's state
    s32 art_t = WR(slot, W_ART_T);
    if (art_t >= 0 && !art_started) {
        art_t++;
        bool over = WR(slot, W_ART_KIND) == ART_BOLT ? art_t > t.art_bolt_ticks : (now != 6 && now != 9 && now != 10 && art_t > 2);
        if (over || art_t > 600 || !alive) { art_t = -1; WW(slot, W_ART_KIND, 0); }
    }
    WW(slot, W_ART_T, art_t);
    if (WR(slot, W_ART_CD) > 0 && art_t < 0) WW(slot, W_ART_CD, WR(slot, W_ART_CD) - 1);
    if (sprint) { charge(slot, t.cost_sprint_per_tick); spent = true; flags |= FL_SPRINT; }
    if (now == 8) flags |= FL_BLOCK;
    s32 broken = SR(slot_off(slot, S_BROKEN));
    if (broken > 0) { SW(slot_off(slot, S_BROKEN), broken - 1); flags |= FL_BROKEN; }
    // the parry: its tick counts up from the press to the end of its recovery
    s32 parry_t = ER(slot, E_PARRY);
    if (parry_started) {
        charge(slot, t.cost_parry); spent = true;
        parry_t = 0;
        if (g_log) fprintf(stderr, "souls: tick %u: p%d parry pressed\n", frame_now(), slot);
    } else if (parry_t >= 0 && ++parry_t > t.parry_recovery) parry_t = -1;
    if (!alive) parry_t = -1;
    EW(slot, E_PARRY, parry_t);
    if (parry_t >= t.parry_first && parry_t <= t.parry_last) flags |= FL_PARRY;
    s32 riposte = ER(slot, E_RIPOSTE), window = ER(slot, E_COUNTER);
    if (riposte > 0) { flags |= FL_RIPOSTE; if (--riposte == 0) g_riposte_target[slot] = 0; EW(slot, E_RIPOSTE, riposte); }
    if (window > 0) { flags |= FL_COUNTER; EW(slot, E_COUNTER, window - 1); }
    // the drink: the flask is spent and the healing starts at its heal tick; the drink ends with the clip, or here
    if (drink_t >= 0 && !drank) {
        drink_t++;
        if (now == 2 && alive && last == 3 && drink_t < t.flask_drink_ticks) {
            // the clip ended before the drink's time (in a net game the game steps it faster): the character stays in
            // the committed state until the drink's end
            PW(P + P_STATE, 3);
            now = 3;
        }
        if (drink_t == t.flask_heal_tick && now == 3 && alive && ER(slot, E_FLASKS) > 0) {
            float most = F(record + REC_HP_MAX);
            float heal = most * ((float)t.flask_heal_percent / 100.0f);
            PF(record + REC_HEAL_PENDING, F(record + REC_HEAL_PENDING) + heal);
            PF(record + REC_HEAL_RATE, heal / (float)std::max(1, t.flask_heal_spread));
            EW(slot, E_FLASKS, ER(slot, E_FLASKS) - 1);
            EW(slot, E_DRUNK, ER(slot, E_DRUNK) + 1);
            bump(H_DRUNK);
            if (g_log) fprintf(stderr, "souls: tick %u: p%d flask drunk: %.1f of %.1f hit points to come, %d left\n", frame_now(), slot, heal, most, ER(slot, E_FLASKS));
        }
        if (now != 3 || !alive) drink_t = -1;
        else if (drink_t >= t.flask_drink_ticks) {
            PW(P + P_STATE, 2); PW(P + P_ATTACK_REQUEST, 0); PW(P + P_ACTION_START, frame_now());
            now = 2; drink_t = -1;
        }
    }
    EW(slot, E_DRINK, drink_t);
    if (drink_t >= 0) flags |= FL_DRINK;
    // the death drop: on the death a share of the gold is marked at the spot; it is taken from the gold when the player
    // is back (a game that restores the record on everybody's death has done so by then); walking over the spot gives it back
    if (now == 4 && last != 4 && last != -1) {
        if (ER(slot, E_DROP) > 0) { bump(H_GOLD_LOST, ER(slot, E_DROP)); if (g_log) fprintf(stderr, "souls: tick %u: p%d died again: %d gold lost\n", frame_now(), slot, ER(slot, E_DROP)); }
        s64 gold = (s32)W(record + REC_GOLD);
        s32 share = gold > 0 ? (s32)(gold * t.drop_percent / 100) : 0;
        EW(slot, E_DROP, 0);
        EW(slot, E_PENDING, share);
        SW(H_DEAD + 4 * (u32)slot, 1);
        PW(SOULS_BASE + ext_off(slot, E_DROP_X), W(P + O_POS));
        PW(SOULS_BASE + ext_off(slot, E_DROP_Y), W(P + O_POS + 4));
        PW(SOULS_BASE + ext_off(slot, E_DROP_Z), W(P + O_POS + 8));
        EW(slot, E_DROP_LEVEL, (s32)level_figure());
        if (g_log) fprintf(stderr, "souls: tick %u: p%d died with %lld gold: %d to be left at %.1f %.1f %.1f\n", frame_now(), slot, (long long)gold, share, F(P + O_POS), F(P + O_POS + 4), F(P + O_POS + 8));
    }
    if (alive && SR(H_DEAD + 4 * (u32)slot)) {
        // back after a death (a respawn or the reload after everybody died; the object can be the same one): the flasks
        // are full again
        SW(H_DEAD + 4 * (u32)slot, 0);
        if (ER(slot, E_FLASKS) < t.flask_count) { EW(slot, E_FLASKS, t.flask_count); bump(H_REFILLS); }
    }
    if (alive && ER(slot, E_PENDING) > 0) {
        s32 gold = (s32)W(record + REC_GOLD);
        s32 take = std::min(ER(slot, E_PENDING), std::max(0, gold));
        PW(record + REC_GOLD, (u32)(gold - take));
        EW(slot, E_DROP, take);
        EW(slot, E_PENDING, 0);
        if (take > 0) bump(H_DROPS);
        if (g_log) fprintf(stderr, "souls: tick %u: p%d back: %d gold taken, left at the spot\n", frame_now(), slot, take);
    } else if (alive && ER(slot, E_DROP) > 0 && (u32)ER(slot, E_DROP_LEVEL) == level_figure()) {
        // a test aid for the room runs: the word H_TEST_GO, written by every copy in the same lockstep tick (n2party's
        // tick-do), puts player (word - 1) on its drop spot here; 0 (always, outside such a test) does nothing
        if (SR(H_TEST_GO) == slot + 1) {
            for (u32 k = 0; k < 3; k++) PW(P + O_POS + 4 * k, W(SOULS_BASE + ext_off(slot, E_DROP_X) + 4 * k));
            SW(H_TEST_GO, 0);
        }
        float dx = F(P + O_POS) - F(SOULS_BASE + ext_off(slot, E_DROP_X)), dy = F(P + O_POS + 4) - F(SOULS_BASE + ext_off(slot, E_DROP_Y));
        float dz = F(P + O_POS + 8) - F(SOULS_BASE + ext_off(slot, E_DROP_Z));
        float r = (float)t.drop_radius;
        if (dx * dx + dy * dy <= r * r && dz * dz <= 4.0f * r * r) {
            s32 back = ER(slot, E_DROP);
            PW(record + REC_GOLD, W(record + REC_GOLD) + (u32)back);
            EW(slot, E_DROP, 0);
            EW(slot, E_GOLD_BACK, ER(slot, E_GOLD_BACK) + back);
            bump(H_GOLD_BACK, back);
            bump(H_PICKUPS);
            if (g_log) fprintf(stderr, "souls: tick %u: p%d picked up the %d gold at the death spot\n", frame_now(), slot, back);
        }
    }
    if (!spent) {
        s32 delay = SR(slot_off(slot, S_DELAY));
        if (delay > 0) SW(slot_off(slot, S_DELAY), delay - 1);
        else {
            s32 add = now == 8 ? t.regen_per_tick * t.regen_block_percent / 100 : t.regen_per_tick;
            add = add * t.tier_regen[tier] / 100;
            SW(slot_off(slot, S_STAMINA), std::min(stamina_most(slot), SR(slot_off(slot, S_STAMINA)) + add));
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
    s32 tier = std::max(0, std::min(3, WR(slot, W_TIER)));
    s32 iframe_last = t.dodge_iframe_last * t.tier_iframes[tier] / 100;      // the equip load's tier shortens them
    if (amount > 0 && amount < 100000.0f && dodge_t >= t.dodge_iframe_first && dodge_t <= iframe_last) {
        // the dodge's invulnerable ticks: the hit does not land
        g_iframe_skips++;
        SW(slot_off(slot, S_AVOIDED), SR(slot_off(slot, S_AVOIDED)) + 1);
        SW(H_AVOIDED, SR(H_AVOIDED) + 1);
        return;
    }
    s32 parry_t = ER(slot, E_PARRY);
    if (parry_t >= t.parry_first && parry_t <= t.parry_last && amount > 0 && amount < 100000.0f && creature(attacker) &&
        ground2(P, attacker) <= (float)t.parry_reach * (float)t.parry_reach) {
        // parried: the hit does not land, the attacker staggers (its own stun) and is open to a riposte
        stun(c, attacker, t.parry_stagger_ticks);
        g_riposte_target[slot] = attacker;
        EW(slot, E_RIPOSTE, t.riposte_window);
        EW(slot, E_PARRY, t.parry_last + 1);        // one parry per press
        EW(slot, E_PARRIES, ER(slot, E_PARRIES) + 1);
        bump(H_PARRIES);
        if (g_log) fprintf(stderr, "souls: tick %u: p%d parried a hit of %.1f (parry tick %d); the attacker is stunned for %d ticks\n", frame_now(), slot, amount, parry_t, t.parry_stagger_ticks);
        return;
    }
    s32 state = (s32)W(P + P_STATE);
    if (dodge_t >= 0 && state == 0xb) { flags |= HIT_UNBLOCKABLE; c->r[6] = (u64)(s64)(s32)flags; }   // the dodge's recovery is no block
    if (parry_t > t.parry_last && parry_t <= t.parry_recovery && !(flags & HIT_UNBLOCKABLE)) {
        flags |= HIT_UNBLOCKABLE; c->r[6] = (u64)(s64)(s32)flags;  // a missed parry leaves the guard open until its recovery ends
    }
    bool blocking = (state == 8 || state == 0xb) && !(flags & HIT_UNBLOCKABLE) && attacker && amount > 0 && amount < 100000.0f;
    float before = F(P + C_PENDING);
    g_orig_ptd(c);
    u32 record = G_PLAYERS + (u32)slot * REC;
    float most = F(record + REC_HP_MAX);
    if (!(most > 1.0f)) most = 1.0f;
    float added = F(P + C_PENDING) - before;
    // a heavy without hyper-armour: only a great weapon's heavy keeps the game's own; any other class's heavy is
    // staggered (the game's forced stagger) by a hit of heavy_interrupt_hp_percent of the bar or more
    s32 wc = std::max(0, std::min(WC_COUNT - 1, WR(slot, W_CLASS)));
    if (state == 1 && W(P + P_ATTACK_REQUEST) == 2 && (SR(slot_off(slot, S_FLAGS)) & FL_HEAVY) && wc != WC_GREAT && amount > 0 && amount < 100000.0f &&
        added * 100.0f >= most * (float)t.heavy_interrupt_hp_percent) {
        PW(P + C_PENDING_FLAGS, W(P + C_PENDING_FLAGS) | PEND_STAGGER);
        bump(H_INTERRUPTS);
        if (g_log) fprintf(stderr, "souls: tick %u: p%d heavy (%s) interrupted by a hit of %.1f\n", frame_now(), slot, class_name(wc), added);
    }
    if (!blocking) return;
    if (added >= amount * 0.25f) return;            // from behind: the game did not block it
    // a player's spear thrust partly goes through a block
    if (ok(attacker, 0x590) && W(attacker + O_VTABLE) == VT_PLAYER && !(W(attacker + O_FLAGS) & FLAG_COPY)) {
        s32 aslot = (s32)W(attacker + P_SLOT);
        if (aslot >= 0 && aslot < 4 && WR(aslot, W_CLASS) == WC_SPEAR) {
            float chip = amount * ((float)t.spear_chip_percent / 100.0f);
            PF(P + C_PENDING, F(P + C_PENDING) + chip);
            bump(H_CHIPS);
            if (g_log) fprintf(stderr, "souls: tick %u: p%d blocked a spear: %.1f of %.1f goes through\n", frame_now(), slot, chip, amount);
        }
    }
    float share = amount * 100.0f / most;
    if (share > 1000.0f) share = 1000.0f;
    s32 cost = t.cost_block_base + (s32)(share * (float)t.cost_block_per_hp_percent);
    // guarding with the weapon (two-handed, or no shield in the shield slot) costs the class's own share
    bool shield = ok(W(record + REC_EQUIP + 12), ITEM);
    if (weapon_now(slot).two || !shield) cost = cost * t.wc_guard[wc] / 100;
    s32 stamina = SR(slot_off(slot, S_STAMINA));
    SW(slot_off(slot, S_BLOCKS), SR(slot_off(slot, S_BLOCKS)) + 1);
    SW(H_BLOCKS, SR(H_BLOCKS) + 1);
    if (stamina >= cost) { charge(slot, cost); EW(slot, E_COUNTER, t.guard_counter_window); return; }
    // the guard breaks: no stamina left, the hit lands whole and the player staggers (the game's own forced stagger)
    charge(slot, stamina);
    SW(slot_off(slot, S_BROKEN), t.guard_break_ticks);
    PF(P + C_PENDING, F(P + C_PENDING) + (amount - added));
    PW(P + C_PENDING_FLAGS, W(P + C_PENDING_FLAGS) | PEND_STAGGER);
}

// A light hit from behind the creature: the attacker inside backstab_half_angle of straight behind its facing, within
// reach.  The facing's direction is the game's own cos16 / sin16 of the facing word (docs/spec/core.md).
bool from_behind(Ctx* c, u32 V, u32 A) {
    const Tuning& t = g_tuning;
    float dx = F(A + O_POS) - F(V + O_POS), dy = F(A + O_POS + 4) - F(V + O_POS + 4);
    float d2 = dx * dx + dy * dy, reach = (float)t.backstab_reach;
    if (!(d2 <= reach * reach) || d2 < 1.0f) return false;
    s32 facing = (s16)H(V + O_FACING);
    call(c, MATH_COS16, (u32)facing); float fx = flt(g_f0);
    call(c, MATH_SIN16, (u32)facing); float fy = flt(g_f0);
    call(c, MATH_COS16, (u32)(t.backstab_half_angle * 65536 / 360)); float limit = flt(g_f0);
    float along = fx * dx + fy * dy;            // < 0: the attacker is behind
    if (g_log) fprintf(stderr, "souls: tick %u: backstab test: facing %d (%.3f %.3f) to the attacker %.1f %.1f, along %.1f, limit %.3f\n", frame_now(), facing, fx, fy, dx, dy, along, limit);
    return along < 0 && along * along >= d2 * (limit * limit);
}

// A creature killed by a player may leave the upgrade material, by its boss rank: the chance is decided by the game's
// shared generator state as it is at the kill (read, not drawn), the item made by the game's own loot_spawnNamedItem.
void drop_material(Ctx* c, u32 V, int slot) {
    const Tuning& t = g_tuning;
    u32 m = material_def();
    if (!m || !ok(V, 0x3c8)) return;
    u32 rank = call(c, CREATURE_BOSS_RANK, V) & 0xff;
    s32 chance = rank >= 2 ? t.material_drop_boss : rank == 1 ? t.material_drop_miniboss : t.material_drop_normal;
    s32 roll = (s32)((W(G_RAND_SEED) >> 16) % 100);
    if (roll >= chance) return;
    u32 pos = SOULS_BASE + H_SCRATCH;
    PW(pos, W(V + O_POS)); PW(pos + 4, W(V + O_POS + 4)); PW(pos + 8, W(V + O_POS + 8));
    call(c, LOOT_SPAWN_NAMED, pos, W(m));
    bump(H_MAT_DROPS);
    if (g_log) fprintf(stderr, "souls: tick %u: p%d's kill (rank %u, roll %d of %d) left an upgrade material\n", frame_now(), slot, rank, roll, chance);
}

// ---- Creature_takeDamage (slot 2 of most creatures) -------------------------------------------------------------
void w_creature_take_damage(Ctx* c) {
    u32 V = (u32)c->r[4], A = (u32)c->r[5];
    if (!g_on || !ok(V, 0x3c8) || !ok(A, 0x590) || W(A + O_VTABLE) != VT_PLAYER || (W(A + O_FLAGS) & FLAG_COPY)) { g_orig_ctd(c); return; }
    s32 slot = (s32)W(A + P_SLOT);
    if (slot < 0 || slot > 3) { g_orig_ctd(c); return; }
    g_ctd_calls++;
    const Tuning& t = g_tuning;
    float amount = flt(c->f[12]), raw = amount;
    s32 state = (s32)W(A + P_STATE);
    u32 pflags = (u32)SR(slot_off(slot, S_FLAGS));
    bool heavy = state == 1 && W(A + P_ATTACK_REQUEST) == 2 && (pflags & FL_HEAVY);
    bool counter = heavy && (pflags & FL_COUNTER_HEAVY);
    u32 tick = frame_now();
    // a critical: a riposte on the creature a parry opened, a heavy hit on a creature whose poise just broke, a light
    // hit from behind
    int kind = 0;
    if (state == 1 && amount > 0 && amount < 100000.0f && F(V + C_HP) > 0 && !B(V + C_INERT)) {
        auto it = g_poise.find(V);
        if (ER(slot, E_RIPOSTE) > 0 && g_riposte_target[slot] == V) kind = 1;
        else if (heavy && it != g_poise.end() && it->second.broken && tick + 1 - it->second.broken <= (u32)t.stance_crit_window) kind = 2;
        else if (!heavy && (it == g_poise.end() || !it->second.crit || tick + 1 - it->second.crit > (u32)t.backstab_cooldown) && from_behind(c, V, A)) kind = 3;
    }
    s32 wc = std::max(0, std::min(WC_COUNT - 1, WR(slot, W_CLASS)));
    s32 percent = kind == 1 ? t.crit_riposte_percent : kind == 2 ? t.crit_stance_percent : kind == 3 ? t.crit_backstab_percent : 0;
    if (kind == 1 || kind == 3) percent = percent * t.wc_crit[wc] / 100;   // daggers: better ripostes and backstabs
    // a slam (the ground pound's shoves, one point each with the lightest knock bit): the weapon's own top damage instead
    bool slam = WR(slot, W_ART_T) >= 0 && WR(slot, W_ART_KIND) == ART_SLAM && state == 10 && (((u32)c->r[6]) & FLAG_KNOCK_LIGHT) && amount >= 0 && amount <= 2.0f;
    s32 art_kind = WR(slot, W_ART_KIND);
    bool art_hit = WR(slot, W_ART_T) >= 0 && (art_kind == ART_BOLT ? state != 1 && state != 0 : (state == 6 || state == 9 || state == 10));
    // the lunge's and the bolt's hits are the skills' own fixed damage (made for characters of a higher level): scaled down
    if (art_hit && (art_kind == ART_LUNGE || art_kind == ART_BOLT) && amount > 0 && amount < 100000.0f) amount = amount * ((float)t.art_fixed_percent / 100.0f);
    if (slam) amount = F(G_PLAYERS + (u32)slot * REC + REC_DMG_MAX) * ((float)t.art_slam_percent / 100.0f);
    if (kind && amount > 0) amount = amount * ((float)percent / 100.0f);
    else if (counter && amount > 0) amount = amount * ((float)t.guard_counter_damage_percent / 100.0f);
    else if (heavy && amount > 0) amount = amount * ((float)t.heavy_damage_percent / 100.0f);
    // a spell's hit (the caster's hits in the spell window that are not a swing or a weapon art): Intelligence and Faith; every
    // other hit of the player: the weapon's upgrade and the character's statistics (the scaling of its class)
    bool spell_hit = !art_hit && !slam && state != 1 && AR(slot, A_SPELL_T) >= 0;
    s32 dmg = spell_hit ? AR(slot, A_SPELL_PCT) : WR(slot, W_DMG);
    if (spell_hit && amount > 0 && amount < 100000.0f) bump(H_SPELL_HITS);
    if (amount > 0 && amount < 100000.0f && dmg > 0 && dmg != 100) amount = amount * ((float)dmg / 100.0f);
    if (amount > 0 && amount < 100000.0f) c->f[12] = bits(amount);
    float hp_before = F(V + C_HP);
    g_orig_ctd(c);
    if (hp_before > 0 && !(F(V + C_HP) > 0)) drop_material(c, V, slot);
    if (g_log) fprintf(stderr, "souls: tick %u: p%d hits %08x: %.1f -> %.1f (%s, %s %d %%)%s%s, its hit points %.1f -> %.1f\n", tick, slot, V, raw, amount,
                       class_name(wc), spell_hit ? "spell" : "weapon", dmg, heavy ? " (heavy)" : "", slam ? " (slam)" : art_hit ? " (weapon art)" : "", hp_before, F(V + C_HP));
    if (!(amount > 0)) return;
    if (kind) {
        if (kind == 1) { EW(slot, E_RIPOSTE, 0); g_riposte_target[slot] = 0; bump(H_RIPOSTES); }
        else if (kind == 2) bump(H_STANCE);
        else bump(H_BACKSTABS);
        EW(slot, E_CRITS, ER(slot, E_CRITS) + 1);
        if (g_log) fprintf(stderr, "souls: tick %u: p%d %s: %.1f x %d %% -> the creature's hit points %.1f -> %.1f\n", tick, slot,
                           kind == 1 ? "riposte" : kind == 2 ? "stance-break critical" : "backstab", amount, (int)percent, hp_before, F(V + C_HP));
    } else if (counter && g_log)
        fprintf(stderr, "souls: tick %u: p%d guard counter hit: %.1f x %d %% -> %.1f -> %.1f\n", tick, slot, amount, (int)t.guard_counter_damage_percent, hp_before, F(V + C_HP));
    if (!(F(V + C_HP) > 0)) { g_poise.erase(V); return; }
    if (B(V + C_INERT)) return;
    Poise& p = g_poise[V];
    if (kind) {
        p.crit = tick + 1;
        if (kind == 2) p.broken = 0;            // one critical per poise break
        stun(c, V, t.crit_stun_ticks);
    }
    if (tick - p.last > (u32)t.poise_reset_ticks) p.poise = 0;
    s32 poise = counter ? t.poise_guard_counter : (heavy || art_hit) ? t.poise_heavy : state == 0 ? t.poise_ranged : t.poise_light;
    poise = poise * t.wc_poise[wc] / 100;
    if (weapon_now(slot).two) poise = poise * t.twohand_poise_percent / 100;
    p.poise += poise;
    p.last = tick;
    u32 rank = call(c, CREATURE_BOSS_RANK, V) & 0xff;
    s32 limit = rank >= 2 ? t.poise_boss : rank == 1 ? t.poise_miniboss : t.poise_normal;
    if (partyscale_hook::poise_limit) limit = partyscale_hook::poise_limit(V, rank, limit, t.poise_miniboss);   // the party's size, elites
    if (p.poise >= limit) {
        p.poise = 0;
        if (stun(c, V, t.stagger_ticks)) {
            p.broken = tick + 1;
            g_staggers++;
            SW(H_BREAKS, SR(H_BREAKS) + 1);
            if (g_log) fprintf(stderr, "souls: tick %u: poise broken (rank %u): the creature's stun timer is now %d\n", tick, rank, (int)(s16)H(V + 0x31c));
        }
    }
    if (g_poise.size() > 256)
        for (auto it = g_poise.begin(); it != g_poise.end();) it = tick - it->second.last > (u32)t.poise_reset_ticks ? g_poise.erase(it) : std::next(it);
}

// ---- Savepoint_run (SavePoint slot 4): a living player near a save point has the flasks full again ----------------
void w_savepoint_run(Ctx* c) {
    u32 S = (u32)c->r[4];
    g_orig_save(c);
    if (!g_on || !ok(S, 0x118)) return;
    g_save_calls++;
    const Tuning& t = g_tuning;
    // the level's save points, kept in the block (each machine runs them alike): where an upgrade can be made
    u32 level = level_figure();
    if ((u32)SR(H_SAVES_LEVEL) != level) { for (u32 a = H_SAVES; a < H_SAVES + 4 + 12 * 8; a += 4) SW(a, 0); SW(H_SAVES_LEVEL, (s32)level); }
    s32 n = std::max(0, std::min(8, SR(H_SAVES)));
    bool known = false;
    for (s32 k = 0; k < n; k++)
        known |= W(SOULS_BASE + H_SAVES + 4 + 12 * (u32)k) == W(S + O_POS) && W(SOULS_BASE + H_SAVES + 8 + 12 * (u32)k) == W(S + O_POS + 4);
    if (!known && n < 8) {
        for (u32 k = 0; k < 3; k++) PW(SOULS_BASE + H_SAVES + 4 + 12 * (u32)n + 4 * k, W(S + O_POS + 4 * k));
        SW(H_SAVES, n + 1);
        if (g_log) fprintf(stderr, "souls: tick %u: a save point at %.1f %.1f %.1f\n", frame_now(), F(S + O_POS), F(S + O_POS + 4), F(S + O_POS + 8));
    }
    float r = (float)t.flask_refill_radius;
    for (int slot = 0; slot < 4; slot++) {
        u32 record = G_PLAYERS + (u32)slot * REC, P = W(record + REC_OBJECT);
        if (!P || P != g_last_object[slot] || !ok(P, 0x590) || !(F(record + REC_HP) > 0)) continue;
        if (ER(slot, E_FLASKS) >= t.flask_count || !(ground2(P, S) <= r * r)) continue;
        EW(slot, E_FLASKS, t.flask_count);
        bump(H_REFILLS);
        if (g_log) fprintf(stderr, "souls: tick %u: p%d at a save point: flasks full (%d)\n", frame_now(), slot, t.flask_count);
    }
}

void install() {
    if (g_installed) return;
    g_orig_run = rt_replace_function(PLAYER_RUN, w_player_run);
    g_orig_ptd = rt_replace_function(PLAYER_TAKE_DAMAGE, w_player_take_damage);
    g_orig_ctd = rt_replace_function(CREATURE_TAKE_DAMAGE, w_creature_take_damage);
    g_orig_save = rt_replace_function(SAVEPOINT_RUN, w_savepoint_run);   // optional: without it no refill at save points
    if (!g_orig_run || !g_orig_ptd || !g_orig_ctd) {
        // a translation without one of them: put back what was replaced and stay off
        if (g_orig_run) rt_replace_function(PLAYER_RUN, g_orig_run);
        if (g_orig_ptd) rt_replace_function(PLAYER_TAKE_DAMAGE, g_orig_ptd);
        if (g_orig_ctd) rt_replace_function(CREATURE_TAKE_DAMAGE, g_orig_ctd);
        if (g_orig_save) rt_replace_function(SAVEPOINT_RUN, g_orig_save);
        fprintf(stderr, "souls: the game's functions are not all there; the mode stays off\n");
        g_want = false;
        return;
    }
    g_installed = true;
    g_log = getenv("SOULS_LOG") != nullptr;
    if (partyscale_hook::install) partyscale_hook::install();      // the party scaling's factory wrapper (partyscale.h)
    fprintf(stderr, "souls: the combat mode's wrappers are in place%s\n", g_orig_save ? "" : " (no save point refill: Savepoint_run not found)");
}

u32 tuning_figure() {
    std::lock_guard<std::mutex> hold(g_lock);
    u32 h = 2166136261u;
    const unsigned char* p = (const unsigned char*)&g_tuning;
    for (size_t k = 0; k < sizeof g_tuning; k++) h = (h ^ p[k]) * 16777619u;
    if (partyscale_hook::figure) h = (h ^ partyscale_hook::figure()) * 16777619u;   // the party scaling's numbers (partyscale.h)
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
    {"poise_boss", &Tuning::poise_boss}, {"poise_reset_ticks", &Tuning::poise_reset_ticks}, {"stagger_ticks", &Tuning::stagger_ticks},
    {"parry_first", &Tuning::parry_first}, {"parry_last", &Tuning::parry_last},
    {"parry_recovery", &Tuning::parry_recovery},
    {"cost_parry", &Tuning::cost_parry},
    {"parry_reach", &Tuning::parry_reach},
    {"parry_stagger_ticks", &Tuning::parry_stagger_ticks},
    {"riposte_window", &Tuning::riposte_window},
    {"crit_riposte_percent", &Tuning::crit_riposte_percent},
    {"crit_stance_percent", &Tuning::crit_stance_percent},
    {"crit_backstab_percent", &Tuning::crit_backstab_percent},
    {"crit_stun_ticks", &Tuning::crit_stun_ticks},
    {"stance_crit_window", &Tuning::stance_crit_window},
    {"backstab_half_angle", &Tuning::backstab_half_angle},
    {"backstab_reach", &Tuning::backstab_reach},
    {"backstab_cooldown", &Tuning::backstab_cooldown},
    {"guard_counter_window", &Tuning::guard_counter_window},
    {"guard_counter_damage_percent", &Tuning::guard_counter_damage_percent},
    {"poise_guard_counter", &Tuning::poise_guard_counter},
    {"flask_count", &Tuning::flask_count},
    {"flask_heal_percent", &Tuning::flask_heal_percent},
    {"flask_drink_ticks", &Tuning::flask_drink_ticks},
    {"flask_heal_tick", &Tuning::flask_heal_tick},
    {"flask_heal_spread", &Tuning::flask_heal_spread},
    {"flask_refill_radius", &Tuning::flask_refill_radius},
    {"drop_percent", &Tuning::drop_percent},
    {"drop_radius", &Tuning::drop_radius},
    {"load_base", &Tuning::load_base}, {"load_per_endurance", &Tuning::load_per_endurance}, {"load_per_stamina", &Tuning::load_per_endurance},
    {"load_per_strength", &Tuning::load_per_strength},
    {"load_light", &Tuning::load_light}, {"load_medium", &Tuning::load_medium}, {"twohand_strength_percent", &Tuning::twohand_strength_percent},
    {"twohand_poise_percent", &Tuning::twohand_poise_percent}, {"heavy_interrupt_hp_percent", &Tuning::heavy_interrupt_hp_percent},
    {"spear_chip_percent", &Tuning::spear_chip_percent}, {"upgrade_max", &Tuning::upgrade_max}, {"upgrade_damage_tenths", &Tuning::upgrade_damage_tenths},
    {"upgrade_correct_percent", &Tuning::upgrade_correct_percent}, {"upgrade_gold_base", &Tuning::upgrade_gold_base},
    {"upgrade_gold_step", &Tuning::upgrade_gold_step}, {"upgrade_material_every", &Tuning::upgrade_material_every},
    {"material_drop_normal", &Tuning::material_drop_normal}, {"material_drop_miniboss", &Tuning::material_drop_miniboss},
    {"material_drop_boss", &Tuning::material_drop_boss}, {"save_reach", &Tuning::save_reach}, {"art_mana_percent", &Tuning::art_mana_percent},
    {"art_stamina_percent", &Tuning::art_stamina_percent}, {"art_cooldown", &Tuning::art_cooldown}, {"art_slam_percent", &Tuning::art_slam_percent},
    {"art_fixed_percent", &Tuning::art_fixed_percent}, {"art_bolt_ticks", &Tuning::art_bolt_ticks},
    {"points_per_level", &Tuning::points_per_level}, {"stat_max", &Tuning::stat_max}, {"mana_per_mind_permille", &Tuning::mana_per_mind_permille},
    {"stamina_per_endurance", &Tuning::stamina_per_endurance}, {"slot_base", &Tuning::slot_base}, {"slot_per_mind", &Tuning::slot_per_mind},
    {"slot_per_int", &Tuning::slot_per_int}, {"slot_max", &Tuning::slot_max}, {"spell_hit_ticks", &Tuning::spell_hit_ticks}};
// the tuning's arrays: combat.<name>.<label> (a tier, a weapon class or a curve point's index)
const char* const TIER_LABELS[] = {"light", "medium", "heavy", "over"};
const char* const CLASS_LABELS[] = {"none", "dagger", "sword", "axe", "mace", "great", "spear", "staff", "bow"};
const char* const POINT_LABELS[] = {"0", "1", "2", "3", "4", "5", "6"};
const char* const CHAR_LABELS[] = {"barbarian", "cleric", "shadowknight", "ranger", "wizard", "berserker", "shaman"};
struct NamedArray { const char* name; size_t offset; int count; const char* const* labels; };
const NamedArray ARRAYS[] = {
    {"tier_dodge_move", offsetof(Tuning, tier_dodge_move), 4, TIER_LABELS}, {"tier_iframes", offsetof(Tuning, tier_iframes), 4, TIER_LABELS},
    {"tier_regen", offsetof(Tuning, tier_regen), 4, TIER_LABELS}, {"tier_sprint", offsetof(Tuning, tier_sprint), 4, TIER_LABELS},
    {"wc_stamina", offsetof(Tuning, wc_stamina), 9, CLASS_LABELS}, {"wc_poise", offsetof(Tuning, wc_poise), 9, CLASS_LABELS},
    {"wc_recovery", offsetof(Tuning, wc_recovery), 9, CLASS_LABELS}, {"wc_cancel", offsetof(Tuning, wc_cancel), 9, CLASS_LABELS},
    {"wc_str", offsetof(Tuning, wc_str), 9, CLASS_LABELS}, {"wc_dex", offsetof(Tuning, wc_dex), 9, CLASS_LABELS},
    {"wc_int", offsetof(Tuning, wc_int), 9, CLASS_LABELS}, {"wc_guard", offsetof(Tuning, wc_guard), 9, CLASS_LABELS},
    {"wc_crit", offsetof(Tuning, wc_crit), 9, CLASS_LABELS}, {"wc_art", offsetof(Tuning, wc_art), 9, CLASS_LABELS},
    {"scale_stat", offsetof(Tuning, scale_stat), 7, POINT_LABELS}, {"scale_value", offsetof(Tuning, scale_value), 7, POINT_LABELS},
    {"start_mind", offsetof(Tuning, start_mind), 7, CHAR_LABELS}, {"start_endurance", offsetof(Tuning, start_endurance), 7, CHAR_LABELS},
    {"start_faith", offsetof(Tuning, start_faith), 7, CHAR_LABELS}, {"sc_int", offsetof(Tuning, sc_int), 7, CHAR_LABELS},
    {"sc_faith", offsetof(Tuning, sc_faith), 7, CHAR_LABELS}};

}  // namespace

const Tuning& tuning() { return g_tuning; }
void want(bool on) { g_want = on; }
bool wanted() { return g_want.load(); }
void room_agreed(bool on) { g_room = on ? 1 : 0; }
bool active() { return g_on; }

bool attributes(int slot, int32_t out[7]) {
    if (!g_ram || slot < 0 || slot > 3) return false;
    u32 record = G_PLAYERS + (u32)slot * REC;
    if (!W(record + REC_OBJECT)) return false;
    Attr a = attributes_of(record);
    for (int k = 0; k < 7; k++) out[k] = a.v[k];
    return true;
}

int32_t weapon_class_in_hand(int slot, uint32_t* item) {
    if (item) *item = 0;
    if (!g_ram || slot < 0 || slot > 3) return WC_NONE;
    const u32 it = weapon_item(G_PLAYERS + (u32)slot * REC);
    if (item) *item = it;
    return it ? weapon_class(W(it)) : WC_NONE;
}

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
        if (partyscale_hook::reset) partyscale_hook::reset();       // the party scaling's counters and elites (partyscale.h)
        g_on = on;
        SW(H_MODE, on ? 1 : 0);
        if (!on) SW(H_MAGIC, 0);
        fprintf(stderr, "souls: Hardcore mode is %s (%s)\n", on ? "ON" : "off", room >= 0 ? "a room's game" : net ? "an online game without a room: off" : "offline");
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
        s.flasks = ER(h.slot, E_FLASKS);
        s.flask_max = g_tuning.flask_count;
        s.drop = ER(h.slot, E_DROP) > 0 && (u32)ER(h.slot, E_DROP_LEVEL) == level_figure();
        s.dx = F(SOULS_BASE + ext_off(h.slot, E_DROP_X)); s.dy = F(SOULS_BASE + ext_off(h.slot, E_DROP_Y)); s.dz = F(SOULS_BASE + ext_off(h.slot, E_DROP_Z));
        SW(L_DROP, s.drop ? 1 : 0);
        // the weapon card (the weapons part of the block, and the name of the weapon in hand for the HUDs)
        s.cls = WR(h.slot, W_CLASS); s.level = WR(h.slot, W_UPG); s.tier = WR(h.slot, W_TIER); s.load = WR(h.slot, W_LOAD);
        s.cap = std::max(1, WR(h.slot, W_CAP)); s.mats = WR(h.slot, W_MATS); s.gold_next = WR(h.slot, W_GOLD_NEXT);
        s.mats_next = WR(h.slot, W_MATS_NEXT); s.art_cd = WR(h.slot, W_ART_CD); s.damage = WR(h.slot, W_DMG);
        s.grades = (u32)WR(h.slot, W_GRADES); s.two = WR(h.slot, W_TWOHAND) != 0 && s.cls != WC_BOW && s.cls != WC_NONE;
        s.near = WR(h.slot, W_NEAR) != 0;
        u32 it = weapon_item(G_PLAYERS + (u32)h.slot * REC), name = it ? W(W(it)) : 0;
        for (u32 k = 0; k < 31; k++) { char ch = name && ok(name + k, 1) ? (char)B(name + k) : 0; s.name[k] = ch; if (!ch) break; }
        s.name[31] = 0;
        for (u32 k = 0; k < 32; k += 4) { u32 v = 0; memcpy(&v, s.name + k, 4); PW(SOULS_BASE + L_NAME + k, v); }
        // the character sheet: the block's attributes part, and from the record the names of the spells (the skills' own
        // internal names) for the HUDs
        u32 record = G_PLAYERS + (u32)h.slot * REC;
        s.open = AR(h.slot, A_OPEN) != 0;
        s.sheet = s.open || g_sheet_view.load();
        s.row = AR(h.slot, A_ROW); s.unspent = AR(h.slot, A_UNSPENT); s.char_level = AR(h.slot, A_LEVEL); s.slots = AR(h.slot, A_SLOTS);
        s.cls_of = class_of(record);
        for (u32 k = 0; k < 7; k++) s.v[k] = AR(h.slot, A_VIG + 4 * k);
        s.spell_pct = AR(h.slot, A_SPELL_PCT); s.spell_grades = (u32)AR(h.slot, A_SPELL_GRADES); s.stamina_most = stamina_most(h.slot);
        s.hp_now = F(record + REC_HP); s.hp_most = F(record + REC_HP_MAX); s.mana = F(record + REC_MANA); s.mana_most = F(record + REC_MANA_MAX);
        u32 attuned = (u32)AR(h.slot, A_ATTUNED);
        for (int k = 0; k < 15; k++) {
            Shown::Spell& sp = s.book[k];
            if (in_book(record, k)) {
                s32 id = ability_id(record, k);
                u32 sk = skill_of(id), name = skill_record(ability(record, k)) && sk ? W(sk) : ability(record, k);
                for (u32 q = 0; q < 23; q++) { char ch = ok(name + q, 1) ? (char)B(name + q) : 0; sp.name[q] = ch; if (!ch) break; }
                sp.name[23] = 0;
                if (!sp.name[0]) snprintf(sp.name, sizeof sp.name, "skill %d", id);
                sp.cost10 = H(SOULS_BASE + COST_BASE + (u32)h.slot * 0x40 + 2 * (u32)k);
                sp.rank = B(SOULS_BASE + COST_BASE + (u32)h.slot * 0x40 + 0x20 + (u32)k);
                sp.attuned = ((attuned >> k) & 1) != 0;
            }
            for (u32 q = 0; q < 24; q += 4) { u32 v = 0; memcpy(&v, sp.name + q, 4); PW(SOULS_BASE + L_SPELL_NAMES + 24 * (u32)k + q, v); }
        }
        // the book's spells in record order (the rows of the open screen after the three attributes)
        int n = 0;
        for (int k = 0; k < 15; k++) if (in_book(record, k) && n < 15) s.rows[n++] = k;
        s.books = n;
        for (int j = 0; j < 15; j++) PB(SOULS_BASE + L_SLOT_REC + (u32)j, (u8)(j < n ? s.rows[j] : 0xff));
        s.used = AR(h.slot, A_USED);
        SW(L_SHEET, g_sheet_view.load() ? 1 : 0);
        PF(SOULS_BASE + L_SHEET + 0x10, s.hp_now); PF(SOULS_BASE + L_SHEET + 0x14, s.hp_most);
        PF(SOULS_BASE + L_SHEET + 0x18, s.mana); PF(SOULS_BASE + L_SHEET + 0x1c, s.mana_most);
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
    // the flasks: one upright pip for each, full ones amber, spent ones dark, left of the bar
    for (int k = 0; k < s.flask_max && k < 16; k++) {
        float pw = std::max(3.0f, bh * 0.9f), ph = bh * 2.6f, px = bx - 8 - (float)(s.flask_max - k) * (pw + 3), py = by + bh - ph;
        quad(px - 1, py - 1, px + pw + 1, py + ph + 1, 0, 0, 0, 0x60);
        bool full = k < s.flasks;
        quad(px, py, px + pw, py + ph, full ? 0xe8 : 0x38, full ? 0x8c : 0x30, full ? 0x28 : 0x30, (s.flags & FL_DRINK) && k == s.flasks ? 0x40 : 0x70);
    }
    if (s.flags & FL_PARRY) quad(bx, by - bh * 0.8f, bx + bw, by - bh * 0.4f, 0xf0, 0xe8, 0x80, 0x78);   // the parry's window: a gold line over the bar
    if (s.flags & (FL_RIPOSTE | FL_COUNTER)) quad(bx, by + bh * 1.4f, bx + bw, by + bh * 1.8f, 0xf0, 0x60, 0x40, 0x70);   // a riposte or guard counter is open
    // the weapon card: our own text over the bar - the weapon, its upgrade, class and grades, the equip load and its tier;
    // near a save point what the next upgrade costs
    if (s.cls != WC_NONE || s.load > 0) {
        static const char* const TIERS[4] = {"LIGHT", "MEDIUM", "HEAVY", "OVERLOADED"};
        char line[160];
        float px = std::max(1.0f, std::floor(Ht / 448.0f + 0.25f));
        char g[3] = {(char)(s.grades & 0xff), (char)((s.grades >> 8) & 0xff), (char)((s.grades >> 16) & 0xff)};
        snprintf(line, sizeof line, "%s +%d  %s  STR %c DEX %c%s%c  %d%%%s", s.name[0] ? s.name : "-", s.level, class_name(s.cls), g[0] ? g[0] : '-', g[1] ? g[1] : '-',
                 s.cls == WC_STAFF ? " INT " : "", s.cls == WC_STAFF ? (g[2] ? g[2] : '-') : ' ', s.damage, s.two ? "  2H" : "");
        float ty = by - bh - 2 - 9 * px * 2;
        testerkit::text(frame, bx, ty, px, line, 0xf0, 0xe8, 0xd0, 0x80);
        int tier = std::max(0, std::min(3, s.tier));
        snprintf(line, sizeof line, "LOAD %.1f/%.1f %s  WHETSTONES %d%s", s.load / 100.0, s.cap / 100.0, TIERS[tier], s.mats, s.art_cd > 0 ? "  ART ..." : "");
        uint8_t lr = tier == 3 ? 0xf0 : tier == 2 ? 0xf0 : 0xc0, lg = tier == 3 ? 0x50 : tier == 2 ? 0xb0 : 0xe0, lb = tier >= 2 ? 0x50 : 0xc0;
        testerkit::text(frame, bx, ty + 9 * px, px, line, lr, lg, lb, 0x80);
        if (s.near) {
            if (s.gold_next > 0) snprintf(line, sizeof line, "UPGRADE TO +%d: %d GOLD, %d WHETSTONE%s  (HOLD L3 + USE)", s.level + 1, s.gold_next, s.mats_next, s.mats_next == 1 ? "" : "S");
            else snprintf(line, sizeof line, "FULLY UPGRADED");
            testerkit::text(frame, bx, ty - 9 * px, px, line, 0xa0, 0xe8, 0xff, 0x80);
        }
    }
    // the level-up's points and the character screen's way in
    if (s.unspent > 0 || (s.near && !s.open)) {
        char line[160];
        float px = std::max(1.0f, std::floor(Ht / 448.0f + 0.25f));
        if (s.near) snprintf(line, sizeof line, "CHARACTER: HOLD L3 + L2%s", s.unspent > 0 ? "  (POINTS TO SPEND)" : "");
        else snprintf(line, sizeof line, "LEVEL UP: %d POINT%s - SPEND THEM AT A SAVE POINT", s.unspent, s.unspent == 1 ? "" : "S");
        testerkit::text(frame, bx, by + bh + 4 + 3 * px, px, line, 0xf0, 0xd8, 0x80, 0x80);
    }
    // the character sheet: the attributes, what they make, and the spellbook (our own text)
    if (s.sheet) {
        static const char* const CLASS_WORD[7] = {"BARBARIAN", "CLERIC", "SHADOW KNIGHT", "RANGER", "WIZARD", "BERSERKER", "SHAMAN"};
        static const char* const TIERS2[4] = {"LIGHT", "MEDIUM", "HEAVY", "OVERLOADED"};
        float px = std::max(1.0f, std::floor(Ht / 360.0f + 0.25f)), lh = 10 * px;
        struct Line { std::string text; uint8_t r, g, b; };
        std::vector<Line> lines;
        auto add = [&](int row, const char* fmt, auto... args) {
            char t[200];
            snprintf(t, sizeof t, fmt, args...);
            bool chosen = s.open && row >= 0 && row == s.row;
            lines.push_back({std::string(chosen ? "> " : "  ") + t, (uint8_t)(chosen ? 0xff : 0xe8), (uint8_t)(chosen ? 0xd8 : 0xe4), (uint8_t)(chosen ? 0x70 : 0xd8)});
        };
        int cls = std::max(0, std::min(6, s.cls_of)), tier = std::max(0, std::min(3, s.tier));
        add(-1, "%s  LEVEL %d  POINTS %d", CLASS_WORD[cls], s.char_level, s.unspent);
        add(-1, "VIGOR         %3d   HP %.0f/%.0f", s.v[0], s.hp_now, s.hp_most);
        add(0, "MIND          %3d   MANA %.0f/%.0f", s.v[1], s.mana, s.mana_most);
        add(1, "ENDURANCE     %3d   STAMINA %.0f  LOAD %.1f/%.1f %s", s.v[2], s.stamina_most / 100.0, s.load / 100.0, s.cap / 100.0, TIERS2[tier]);
        add(-1, "STRENGTH      %3d", s.v[3]);
        add(-1, "DEXTERITY     %3d", s.v[4]);
        add(-1, "INTELLIGENCE  %3d", s.v[5]);
        add(2, "FAITH         %3d", s.v[6]);
        char g[3] = {(char)(s.grades & 0xff), (char)((s.grades >> 8) & 0xff), (char)((s.grades >> 16) & 0xff)};
        add(-1, "WEAPON  %s +%d  STR %c DEX %c INT %c  %d%%", s.name[0] ? s.name : "-", s.level, g[0] ? g[0] : '-', g[1] ? g[1] : '-', g[2] ? g[2] : '-', s.damage);
        char sg[2] = {(char)(s.spell_grades & 0xff), (char)((s.spell_grades >> 8) & 0xff)};
        add(-1, "SPELLS  INT %c  FTH %c  %d%%   SLOTS %d OF %d (*)", sg[0] ? sg[0] : '-', sg[1] ? sg[1] : '-', s.spell_pct, s.used, s.slots);
        for (int j = 0; j < s.books; j++) {
            const Shown::Spell& b = s.book[s.rows[j]];
            add(3 + j, "%s %-22s RANK %d  %.1f MANA", b.attuned ? "*" : " ", b.name, b.rank, b.cost10 / 10.0);
        }
        if (s.books == 0) add(-1, "  (NO SPELLS)");
        if (s.open) add(-1, "UP/DOWN CHOOSE  RIGHT SPEND / INTO A SLOT  LEFT OUT OF ITS SLOT  BLOCK CLOSES");
        else if (s.unspent > 0) add(-1, "SPEND THE POINTS AT A SAVE POINT: HOLD L3 + L2");
        size_t widest = 0;
        for (const Line& l : lines) widest = std::max(widest, l.text.size());
        float x0 = X + Wd * 0.04f, y0 = Y + Ht * 0.12f, w = (float)widest * 6 * px;
        quad(x0 - 5 * px, y0 - 5 * px, x0 + w + 4 * px, y0 + (float)lines.size() * lh + 3 * px, 0x0c, 0x0c, 0x10, 0x68);
        quad(x0 - 5 * px, y0 - 5 * px, x0 + w + 4 * px, y0 - 4 * px, 0xf0, 0xd8, 0x80, 0x80);
        for (size_t k = 0; k < lines.size(); k++) testerkit::text(frame, x0, y0 + (float)k * lh, px, lines[k].text, lines[k].r, lines[k].g, lines[k].b, 0x80);
    }
    auto project = [&](float wx, float wy, float wz, float& cx, float& cy) {
        if (!cam.valid) return false;
        float v[3] = {wx - cam.eye[0], wy - cam.eye[1], wz - cam.eye[2]};
        float z = v[0] * cam.forward[0] + v[1] * cam.forward[1] + v[2] * cam.forward[2];
        if (z <= 1.0f) return false;
        float th = std::tan(cam.fov * 0.5f * 3.14159265f / 180.0f), aspect = frame.aspect > 0.1f ? frame.aspect : 4.0f / 3.0f;
        float px = (v[0] * cam.right[0] + v[1] * cam.right[1] + v[2] * cam.right[2]) / (z * th * aspect);
        float py = (v[0] * cam.up[0] + v[1] * cam.up[1] + v[2] * cam.up[2]) / (z * th);
        if (std::fabs(px) >= 1.2f || std::fabs(py) >= 1.2f) return false;
        cx = X + (0.5f + 0.5f * px) * Wd; cy = Y + (0.5f - 0.5f * py) * Ht;
        return true;
    };
    // the death drop: a pale green upright diamond over the spot
    float mx, my;
    if (s.drop && project(s.dx, s.dy, s.dz + 20.0f, mx, my)) {
        float r = Ht * 0.022f;
        render::Vertex d{};
        d.z = 1; d.q = 1; d.r = 0x90; d.g = 0xf0; d.b = 0xb0; d.a = 0x70;
        auto put = [&](float x, float y) { d.x = x; d.y = y; frame.vertices.push_back(d); };
        put(mx, my - r * 1.6f); put(mx + r * 0.6f, my); put(mx - r * 0.6f, my);
        put(mx - r * 0.6f, my); put(mx + r * 0.6f, my); put(mx, my + r * 1.6f);
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
    if (partyscale_hook::setting && partyscale_hook::setting(key, value)) return true;   // combat.party.* (partyscale.h)
    std::string name = key + 7, text = value ? value : "";
    if (name == "mode") { g_want = text == "hardcore" || text == "souls" || text == "on" || text == "yes"; return true; }   // "souls": the earlier name
    std::lock_guard<std::mutex> hold(g_lock);
    for (const Named& n : NAMES)
        if (name == n.name) { g_tuning.*(n.field) = (int32_t)atol(text.c_str()); return true; }
    for (const NamedArray& a : ARRAYS)
        for (int k = 0; k < a.count; k++)
            if (name == std::string(a.name) + "." + a.labels[k]) {
                int32_t* field = (int32_t*)((char*)&g_tuning + a.offset) + k;
                *field = (int32_t)atol(text.c_str());
                return true;
            }
    return false;
}

std::string settings_text() {
    std::string out = std::string("combat.mode = ") + (g_want.load() ? "hardcore" : "off") +
                      "      # hardcore (or souls): stamina, dodge, light / heavy attacks, blocking with stamina, poise, lock-on, parry, criticals, flasks, the death drop (docs/issues/native-souls-combat.md)\n";
    return out;
}

std::string figures() {
    char text[1024];
    snprintf(text, sizeof text, "souls: %s, wrappers %s; player ticks %llu, player hits %llu (dodged %llu), creature hits by players %llu, staggers %llu, "
             "parries %d, ripostes %d, stance criticals %d, backstabs %d, guard counters %d, flasks drunk %d, refills %d, save point runs %llu, "
             "drops %d, picked up %d (gold %d), gold lost %d, weapon arts %d, upgrades %d, materials dropped %d, two-hand toggles %d, "
             "spear chips %d, heavies interrupted %d, swings cancelled %d, mode points spent %d, slot changes %d, spells cast %d, spell hits %d, "
             "casts refused %d, tuning %08x",
             g_on ? "on" : "off", g_installed ? "in place" : "not installed", (unsigned long long)g_runs, (unsigned long long)g_ptd_calls,
             (unsigned long long)g_iframe_skips, (unsigned long long)g_ctd_calls, (unsigned long long)g_staggers,
             SR(H_PARRIES), SR(H_RIPOSTES), SR(H_STANCE), SR(H_BACKSTABS), SR(H_COUNTERS), SR(H_DRUNK), SR(H_REFILLS), (unsigned long long)g_save_calls,
             SR(H_DROPS), SR(H_PICKUPS), SR(H_GOLD_BACK), SR(H_GOLD_LOST), SR(H_ARTS), SR(H_UPGRADES), SR(H_MAT_DROPS), SR(H_TWOHANDS),
             SR(H_CHIPS), SR(H_INTERRUPTS), SR(H_CANCELS), SR(H_POINTS), SR(H_SWAPS), SR(H_CASTS), SR(H_SPELL_HITS), SR(H_CAST_REFUSED), tuning_figure());
    if (partyscale_hook::figures) return std::string(text) + "; " + partyscale_hook::figures();   // partyscale.h
    return text;
}

std::string help_text() {
    return "Hardcore mode (combat.mode = hardcore; online the room's host decides):\n"
           "  Light attack          tap the attack button (K, left mouse button)\n"
           "  Heavy attack          hold it\n"
           "  Dodge                 tap L3 (X, mouse button 4) - toward the move stick, or back\n"
           "  Sprint                hold L3 while moving\n"
           "  Block                 R1 (E, Shift, right mouse button): costs stamina instead of health\n"
           "  Parry                 dodge button while blocking: a melee attacker caught in the window staggers\n"
           "  Riposte               attack a parried enemy while it staggers: a critical\n"
           "  Guard counter         attack just after a blocked hit\n"
           "  Backstab              light attack from behind; a heavy attack on a staggered enemy is a critical\n"
           "  Flask                 the health potion button (R2): heals, refilled at save points and on a new level\n"
           "  Weapon art            hold L3 and press attack: a lunge, a spin, a slam or a bolt by the weapon's class (mana)\n"
           "  Two-handing           hold L3 and press the other-weapon-set button (L1, Q, mouse wheel)\n"
           "  Upgrade               near a save point hold L3 and press use (Square, J, Space): gold and whetstones\n"
           "  Equip load            what is equipped against strength and stamina: light, medium, heavy dodge; overloaded, none\n"
           "  Lock on               R3 (Tab, mouse button 5); flick the mouse or the right stick to change target\n"
           "  Character             near a save point hold L3 and press L2 (1): spend the level-ups' points on Mind, Endurance,\n"
           "                        Faith, put spells in the spell slots (arrow keys / d-pad; block closes). Vigor, Strength,\n"
           "                        Dexterity and Intelligence are the game's own level-up screen's\n"
           "  Spells                the game's skill buttons; only the spells in a slot are cast; Intelligence and Faith scale them\n";
}

std::string command(const std::string& text) {
    std::string w = text;
    while (!w.empty() && w[0] == ' ') w.erase(0, 1);
    if (w.empty() || w == "info") {
        std::string out = figures();
        for (int k = 0; k < 4; k++) {
            char one[256];
            snprintf(one, sizeof one, " | p%d st=%d fl=%x dodge=%d atk=%d l3=%d dodges=%d heavy=%d light=%d refused=%d avoided=%d blocks=%d", k,
                     SR(slot_off(k, S_STAMINA)), SR(slot_off(k, S_FLAGS)), SR(slot_off(k, S_DODGE)), SR(slot_off(k, S_ATK)), SR(slot_off(k, S_L3)),
                     SR(slot_off(k, S_DODGES)), SR(slot_off(k, S_HEAVIES)), SR(slot_off(k, S_LIGHTS)), SR(slot_off(k, S_REFUSED)),
                     SR(slot_off(k, S_AVOIDED)), SR(slot_off(k, S_BLOCKS)));
            out += one;
            snprintf(one, sizeof one, " flasks=%d parry=%d riposte=%d counter=%d drink=%d drop=%d pending=%d crits=%d counters=%d drunk=%d back=%d gold=%d",
                     ER(k, E_FLASKS), ER(k, E_PARRY), ER(k, E_RIPOSTE), ER(k, E_COUNTER), ER(k, E_DRINK), ER(k, E_DROP), ER(k, E_PENDING),
                     ER(k, E_CRITS), ER(k, E_COUNTERS), ER(k, E_DRUNK), ER(k, E_GOLD_BACK), (s32)W(G_PLAYERS + (u32)k * REC + REC_GOLD));
            out += one;
            snprintf(one, sizeof one, " class=%s upg=%d grades=%c%c%c scale=%d dmg=%d load=%d/%d tier=%d 2h=%d mats=%d art=%d/%d arts=%d upgrades=%d recover=%d swing=%d",
                     class_name(WR(k, W_CLASS)), WR(k, W_UPG), (char)(WR(k, W_GRADES) & 0xff) ? (char)(WR(k, W_GRADES) & 0xff) : '.',
                     (char)((WR(k, W_GRADES) >> 8) & 0xff) ? (char)((WR(k, W_GRADES) >> 8) & 0xff) : '.', (char)((WR(k, W_GRADES) >> 16) & 0xff) ? (char)((WR(k, W_GRADES) >> 16) & 0xff) : '.',
                     WR(k, W_SCALE), WR(k, W_DMG), WR(k, W_LOAD), WR(k, W_CAP), WR(k, W_TIER), WR(k, W_TWOHAND), WR(k, W_MATS), WR(k, W_ART_KIND), WR(k, W_ART_T),
                     WR(k, W_ARTS), WR(k, W_UPGRADES), WR(k, W_RECOVER), WR(k, W_SWING));
            out += one;
        }
        for (int k = 0; k < 4; k++) {
            char one[320];
            snprintf(one, sizeof one, " | p%d vig=%d mnd=%d end=%d str=%d dex=%d int=%d fth=%d unspent=%d spent=%d slots=%d book=%x attuned=%x open=%d row=%d "
                     "stmax=%d mana=%.1f/%.1f spell=%d%% spellt=%d casts=%d refused=%d spot=%d level=%d", k,
                     AR(k, A_VIG), AR(k, A_MND), AR(k, A_END), AR(k, A_STR), AR(k, A_DEX), AR(k, A_INT), AR(k, A_FTH), AR(k, A_UNSPENT), AR(k, A_SPENT),
                     AR(k, A_SLOTS), AR(k, A_BOOK), AR(k, A_ATTUNED), AR(k, A_OPEN), AR(k, A_ROW), AR(k, A_STAMINA_MAX),
                     F(G_PLAYERS + (u32)k * REC + REC_MANA), F(G_PLAYERS + (u32)k * REC + REC_MANA_MAX), AR(k, A_SPELL_PCT), AR(k, A_SPELL_T),
                     AR(k, A_CASTS), AR(k, A_CAST_REFUSED), AR(k, A_SPOT), AR(k, A_LEVEL));
            out += one;
        }
        char tail[96];
        snprintf(tail, sizeof tail, " | breaks=%d poise=%d lock=%d", SR(H_BREAKS), SR(H_POISE), SR(L_LOCK));
        return out + tail;
    }
    if (w == "on" || w == "off") { if (B(G_NETWORK_MODE)) return "souls: not during an online game"; g_want = w == "on"; return "souls: wanted " + w; }
    if (w == "lock") { fpcontrols::lock_toggle(); return "souls: lock toggled"; }
    if (w == "sheet") { g_sheet_view = !g_sheet_view.load(); return std::string("souls: character sheet ") + (g_sheet_view.load() ? "shown" : "hidden"); }
    // test aids, offline only (they change the simulation): turn the locked creature's back to this player; put this
    // player on its death drop
    if (w == "turn" || w == "go-drop" || w == "pose front" || w == "pose back") {
        if (B(G_NETWORK_MODE)) return "souls: not during an online game";
        const fpcontrols::Hud& h = fpcontrols::hud();
        if (h.slot < 0 || h.slot > 3) return "souls: no player";
        u32 P = W(G_PLAYERS + (u32)h.slot * REC + REC_OBJECT);
        if (!ok(P, 0x590)) return "souls: no player object";
        if (w == "go-drop") {
            for (u32 k = 0; k < 3; k++) PW(P + O_POS + 4 * k, W(SOULS_BASE + ext_off(h.slot, E_DROP_X) + 4 * k));
            return "souls: on the drop spot";
        }
        u32 V = h.lock.valid ? h.lock.object : 0;
        if (!ok(V, 0x3c8)) return "souls: nothing locked";
        if (w.compare(0, 5, "pose ") == 0) {
            // this player 40 units in front of the locked creature (front) or behind it (back), facing it; the creature
            // is not moved (its grid cell stays right)
            double f = (s16)H(V + O_FACING) * 3.141592653589793 / 32768.0, side = w == "pose front" ? 40.0 : -40.0;
            PF(P + O_POS, F(V + O_POS) + (float)(side * std::cos(f)));
            PF(P + O_POS + 4, F(V + O_POS + 4) + (float)(side * std::sin(f)));
            PH(P + O_FACING, (u16)(s16)(H(V + O_FACING) + (w == "pose front" ? 0x8000 : 0)));
            return "souls: posed";
        }
        double a = std::atan2((double)(F(V + O_POS + 4) - F(P + O_POS + 4)), (double)(F(V + O_POS) - F(P + O_POS)));
        PH(V + O_FACING, (u16)(s16)(int)std::lround(a * 32768.0 / 3.141592653589793));
        return "souls: turned";
    }
    if (w.compare(0, 4, "set ") == 0) {
        if (B(G_NETWORK_MODE)) return "souls: not during an online game";
        size_t sp = w.find(' ', 4);
        if (sp == std::string::npos) return "souls: set NAME VALUE";
        std::string key = "combat." + w.substr(4, sp - 4);
        return setting(key.c_str(), w.substr(sp + 1).c_str()) ? "souls: set" : "souls: no such number";
    }
    return "souls: info | on | off | lock | sheet | set NAME VALUE";
}

}  // namespace soulscombat
