// partyscale.cpp - Hardcore mode's party scaling (partyscale.h; docs/issues/native-8-players.md part B).
#include "partyscale.h"
#include "soulscombat.h"
#include "fpaim.h"
#include "cinematic.h"
#include "guestmap.h"
#include "rt.h"
#include "moved.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <unordered_map>

// the modules' blocks where guestmap.h has them (a header that moves its block without the map does not build)
static_assert(guestmap::at(partyscale::PARTY_BASE).hi >= partyscale::PARTY_BASE + 0x80, "partyscale.h: PARTY_BASE is not in guestmap.h");
static_assert(guestmap::at(soulscombat::SOULS_BASE).hi == soulscombat::SOULS_BASE + 0xC80, "soulscombat.h: SOULS_BASE is not in guestmap.h");
static_assert(guestmap::at(fpaim::AIM_BASE).hi != 0 && fpaim::AIM_SLOT + 4 * fpaim::AIM_SLOT_SIZE <= 0x100, "fpaim.h: AIM_BASE is not in guestmap.h");
static_assert(guestmap::at(cinematic::CINE_BASE).hi >= cinematic::CINE_BASE + cinematic::CINE_HOLD + 8 * 4, "cinematic.h: CINE_BASE is not in guestmap.h");

namespace partyscale {
namespace {

// ---- the game (docs/data-tables.md 3.2, docs/objects.md, docs/creatures.md) ----
const u32 SET_STATS = 0x10a620, FACTORY = 0x159c94, BOSS_RANK = 0x10d940, FIND_FREE_SPOT = 0x14acf8;
const u32 LOAD_RECORDS_FACTORY_RETURN = 0x14e9a8;   // world_loadRecords' call of g_objectFactory returns here
const u32 G_NUM_PLAYERS = 0x4d8ae0, G_NO_PARTY_SCALING = 0x4f713c, G_LEVEL_NAME = 0x41b721, G_POOL = 0x403a10;
const u32 O_FLAGS = 0x0c, O_POS = 0x10, O_RADIUS = 0x1c, O_TYPE = 0x34, O_VTABLE = 0x48, C_HP = 0x228, C_HP_MAX = 0x22c;
const u32 F_CREATURE = 0x20, F_PLAYER = 0x40, F_TRANSIENT = 0x4000;
const u32 POOL_CREATURES = 1;                       // the pool's class of 0x500-byte blocks (creatures)
// the block (partyscale.h)
enum : u32 { H_MAGIC = 0, H_VERSION = 4, H_ON = 8, H_PARTY = 0xc, H_SCALED = 0x10, H_ELITES = 0x14, H_EXTRAS = 0x18, H_EXTRAS_REFUSED = 0x1c,
             H_BOSSES = 0x20, H_HP_SUM = 0x24, H_LEVEL = 0x28, H_SCRATCH = 0x40, BLOCK_SIZE = 0x80 };

bool ok(u32 a, u32 size = 4) { a &= 0x1FFFFFFF; return a >= 0x80000 && a <= RAM_SIZE - size; }
u32 W(u32 a) { u32 v = 0; if (ok(a)) memcpy(&v, g_ram + (party8_at(a) & 0x1FFFFFFF), 4); return v; }
u8 B(u32 a) { return ok(a, 1) ? g_ram[party8_at(a) & 0x1FFFFFFF] : 0; }
float F(u32 a) { float v = 0; if (ok(a)) memcpy(&v, g_ram + (party8_at(a) & 0x1FFFFFFF), 4); return v; }
void PW(u32 a, u32 v) { if (ok(a)) memcpy(g_ram + (party8_at(a) & 0x1FFFFFFF), &v, 4); }
u32 bits(float v) { u32 b; memcpy(&b, &v, 4); return b; }
float flt(u32 b) { float v; memcpy(&v, &b, 4); return v; }
s32 PR(u32 off) { return (s32)W(PARTY_BASE + off); }
void PS(u32 off, s32 v) { PW(PARTY_BASE + off, (u32)v); }
void bump(u32 off, s32 by = 1) { PS(off, PR(off) + by); }

Tuning g_tuning;
std::mutex g_lock;                      // the tuning against the threads that set it
RecompFn g_orig_factory = nullptr;
bool g_installed = false;
bool g_level_load = false;              // inside world_loadRecords' factory call of a level file (game thread)
bool g_log = false;                     // PARTY_LOG: a line per creature scaled, per extra one made
// elites, by creature object, with the maximum hit points they were given (an object of this machine: the entry is only
// used by the object itself, and only while its maximum is still that one)
std::unordered_map<u32, u32> g_elites;
uint64_t g_calls = 0, g_passed = 0;     // per machine: set_stats calls, of them handed to the game unchanged

// A game function called on the context that is running, its registers put back afterwards; returns v0.
u32 call_fn(Ctx* c, RecompFn fn, u32 address, u32 a0, u32 a1 = 0, u32 a2 = 0, u32 a3 = 0, u32 t0 = 0, u32 t1 = 0) {
    Ctx saved = *c;
    c->r[29] = (u64)(s64)(s32)((((u32)saved.r[29]) - 0x400) & ~15u);
    c->r[4] = (u64)(s64)(s32)a0; c->r[5] = (u64)(s64)(s32)a1; c->r[6] = (u64)(s64)(s32)a2;
    c->r[7] = (u64)(s64)(s32)a3; c->r[8] = (u64)(s64)(s32)t0; c->r[9] = (u64)(s64)(s32)t1;
    c->r[31] = 0;                       // not the caller's return address: the factory wrapper tests it
    if (fn) fn(c); else rt_call(c, address);
    u32 v = (u32)c->r[2];
    s64 budget = c->budget;
    *c = saved;
    c->budget = budget;
    return v;
}

u32 fnv(u32 h, const void* data, size_t n) {
    const unsigned char* p = (const unsigned char*)data;
    for (size_t k = 0; k < n; k++) h = (h ^ p[k]) * 16777619u;
    return h;
}
u32 level_figure() {
    u32 h = 2166136261u;
    for (u32 k = 0; k < 15 && g_ram[G_LEVEL_NAME + k]; k++) h = (h ^ g_ram[G_LEVEL_NAME + k]) * 16777619u;
    return h;
}
// a creature's figure: the level, its place, its kind (the type name when it has one, else its class's table)
u32 creature_figure(u32 obj, u32 salt) {
    u32 h = fnv(level_figure(), &salt, 4);
    for (u32 k = 0; k < 3; k++) { u32 v = W(obj + O_POS + 4 * k); h = fnv(h, &v, 4); }
    u32 type = W(obj + O_TYPE);
    if (type && ok(type, 1)) {
        for (u32 k = 0; k < 32; k++) { u8 ch = B(type + k); if (!ch) break; if (ch >= 'A' && ch <= 'Z') ch += 32; h = fnv(h, &ch, 1); }
    } else {
        u32 vt = W(obj + O_VTABLE);
        h = fnv(h, &vt, 4);
    }
    h ^= h >> 15; h *= 0x2c1b3c6du; h ^= h >> 12; h *= 0x297a2d39u; h ^= h >> 15;
    return h;
}
bool name_is(u32 s, const char* word) {
    if (!s || !ok(s, 1)) return false;
    for (u32 k = 0;; k++) {
        u8 a = B(s + k), b = (u8)word[k];
        if (a >= 'A' && a <= 'Z') a += 32;
        if (a != b) return false;
        if (!a) return true;
    }
}
// a property list (null-terminated "key=value" strings) has a key starting with one of the words
bool has_prop(u32 props, const char* const* words) {
    for (u32 k = 0; props && ok(props + 4 * k) && k < 64; k++) {
        u32 s = W(props + 4 * k);
        if (!s) break;
        for (const char* const* w = words; *w; w++) {
            bool same = true;
            for (u32 q = 0; (*w)[q]; q++) { u8 ch = B(s + q); if (ch >= 'A' && ch <= 'Z') ch += 32; if (ch != (u8)(*w)[q]) { same = false; break; } }
            if (same) return true;
        }
    }
    return false;
}
// entries in use in the game's table of object names (objNames_add 0x14bce0: 512 objects at 0x5f7ef8)
const u32 G_NAME_OBJECTS = 0x5f7ef8, NAME_SLOTS = 512, NAMES_KEEP = 384;
u32 names_used() {
    u32 n = 0;
    for (u32 k = 0; k < NAME_SLOTS; k++) n += W(G_NAME_OBJECTS + 4 * k) != 0;
    return n;
}
// free blocks in one class of the object pool (docs/objects.md "Object pool": {size, count, base, free head} x 3)
u32 pool_free(u32 cls) {
    u32 size = W(G_POOL + cls * 16), count = W(G_POOL + cls * 16 + 4), base = W(G_POOL + cls * 16 + 8) & 0x1FFFFFFFu;
    u32 p = W(G_POOL + cls * 16 + 12) & 0x1FFFFFFFu, n = 0;
    while (p >= base && size && p < base + size * count && n < count) { n++; p = W(p) & 0x1FFFFFFFu; }
    return n;
}

int clamp_party(int n) { return n < 1 ? 1 : n > 8 ? 8 : n; }
void ensure_block() {
    if ((u32)PR(H_MAGIC) != PARTY_MAGIC) {
        for (u32 a = 0; a < BLOCK_SIZE; a += 4) PS(a, 0);
        PS(H_MAGIC, (s32)PARTY_MAGIC);
        PS(H_VERSION, 1);
    }
    PS(H_ON, 1);
}

// ---- world_objectFactory, called through g_objectFactory: the extra creatures of a level file ----------------------
void w_factory(Ctx* c) {
    const bool from_level = (u32)c->r[31] == LOAD_RECORDS_FACTORY_RETURN && !(c->r[30] & 1);   // r30: the blob's "saved state" bit
    const u32 cls = (u32)c->r[4], pos = (u32)c->r[5], angle = (u32)c->r[6], props = (u32)c->r[7];
    const bool on = from_level && soulscombat::active() && g_tuning.on;
    g_level_load = on;
    g_orig_factory(c);
    g_level_load = false;
    const u32 obj = (u32)c->r[2];
    if (!on || !obj || !ok(obj, 0x3c8)) return;
    const u32 flags = W(obj + O_FLAGS);
    if (!(flags & F_CREATURE) || (flags & F_PLAYER)) return;
    const int n = party();
    const s32 pct = g_tuning.extra[n - 1];
    if (pct <= 0) return;
    // not a creature that is someone (talks, sells, runs a script of its own, is hidden or dead, a boss); a creature of a
    // named group is copied (the group's scripts then count and wake the extra one too) while the game's table of names
    // has room
    static const char* const SKIP[] = {"action", "hide", "dead", "miniboss", "boss", "dialog", "shop", "showname", "script", nullptr};
    static const char* const NAMED[] = {"name", nullptr};
    if (has_prop(props, SKIP) || (has_prop(props, NAMED) && names_used() > NAMES_KEEP)) {
        if (g_log) {
            fprintf(stderr, "party: no extra %s: its properties", ok(cls, 1) ? (const char*)(g_ram + (cls & 0x1FFFFFFF)) : "?");
            for (u32 k = 0; props && ok(props + 4 * k) && W(props + 4 * k) && k < 16; k++) fprintf(stderr, " %s", (const char*)(g_ram + (W(props + 4 * k) & 0x1FFFFFFF)));
            fprintf(stderr, "\n");
        }
        return;
    }
    PW(obj + O_TYPE, cls);              // world_loadRecords stores the same right after; the rank needs it
    if ((call_fn(c, nullptr, BOSS_RANK, obj) & 0xff) != 0) { if (g_log) fprintf(stderr, "party: no extra: a boss or mini-boss\n"); return; }
    const u32 h = creature_figure(obj, 0x45585452u);    // "EXTR"
    int count = pct / 100 + ((s32)(h % 100u) < pct % 100 ? 1 : 0);
    ensure_block();
    for (int k = 0; k < count; k++) {
        if (pool_free(POOL_CREATURES) <= (u32)g_tuning.pool_keep) { bump(H_EXTRAS_REFUSED); continue; }
        // a free spot near the creature (the game's own search; it draws on the shared generator, as every machine does)
        const u32 out = PARTY_BASE + H_SCRATCH, centre = out + 0x10, okflag = out + 0x1c;
        for (u32 q = 0; q < 3; q++) PW(centre + 4 * q, W(obj + O_POS + 4 * q));
        PW(okflag, 0);
        s32 radius = (s32)F(obj + O_RADIUS);
        if (radius < 4 || radius > 200) radius = 12;
        call_fn(c, nullptr, FIND_FREE_SPOT, out, centre, (u32)g_tuning.extra_range, (u32)radius, okflag, 0);
        if (!B(okflag)) { bump(H_EXTRAS_REFUSED); continue; }
        u32 more = call_fn(c, g_orig_factory, FACTORY, cls, out, angle, props);
        if (!more || !ok(more, 0x3c8)) { bump(H_EXTRAS_REFUSED); continue; }
        PW(more + O_TYPE, cls);
        PW(more + O_FLAGS, W(more + O_FLAGS) | F_TRANSIENT);   // never written into a saved level state
        bump(H_EXTRAS);
        if (g_log) fprintf(stderr, "party: an extra %s at %.1f %.1f %.1f (beside %08x)\n", ok(cls, 1) ? (const char*)(g_ram + (cls & 0x1FFFFFFF)) : "?",
                           F(more + O_POS), F(more + O_POS + 4), F(more + O_POS + 8), obj);
    }
    (void)pos;
}

void install() {
    if (g_installed) return;
    g_orig_factory = rt_replace_function(FACTORY, w_factory);
    g_installed = true;
    g_log = getenv("PARTY_LOG") != nullptr;
    fprintf(stderr, "party: %s\n", g_orig_factory ? "the factory wrapper is in place" : "no factory in this translation: no extra creatures");
}

int32_t poise_limit(uint32_t creature, uint32_t rank, int32_t limit, int32_t miniboss_limit) {
    if (!g_tuning.on) return limit;
    if (rank == 0 && elite(creature)) limit = miniboss_limit;
    return (int32_t)((int64_t)limit * g_tuning.poise[party() - 1] / 100);
}

uint32_t figure() {
    std::lock_guard<std::mutex> hold(g_lock);
    return fnv(0x50525459u, &g_tuning, sizeof g_tuning);
}

struct Named { const char* name; int32_t* field; int count; };
bool setting(const char* key, const char* value) {
    if (strncmp(key, "combat.party.", 13) != 0) return false;
    std::string name = key + 13;
    int32_t v = (int32_t)atol(value ? value : "0");
    std::lock_guard<std::mutex> hold(g_lock);
    Tuning& t = g_tuning;
    const Named names[] = {{"on", &t.on, 1}, {"players", &t.players, 1}, {"hp", t.hp, 8}, {"boss_hp", t.boss_hp, 8},
                           {"damage", t.damage, 8}, {"exp", t.exp, 8}, {"poise", t.poise, 8}, {"elite", t.elite, 8}, {"extra", t.extra, 8},
                           {"elite_hp", &t.elite_hp, 1}, {"elite_damage", &t.elite_damage, 1}, {"elite_exp", &t.elite_exp, 1},
                           {"extra_range", &t.extra_range, 1}, {"pool_keep", &t.pool_keep, 1}};
    for (const Named& n : names) {
        if (n.count == 1 && name == n.name) { *n.field = v; return true; }
        for (int k = 0; n.count > 1 && k < n.count; k++)
            if (name == std::string(n.name) + "." + std::to_string(k + 1)) { n.field[k] = v; return true; }
    }
    return false;
}

void reset() {
    for (u32 a = 0; a < BLOCK_SIZE; a += 4) PS(a, 0);
    g_elites.clear();
}

struct Hooks {
    Hooks() {
        partyscale_hook::install = install;
        partyscale_hook::reset = reset;
        partyscale_hook::poise_limit = poise_limit;
        partyscale_hook::figure = figure;
        partyscale_hook::setting = setting;
        partyscale_hook::figures = partyscale::figures;
    }
} g_hooks_installed;

}  // namespace

const Tuning& tuning() { return g_tuning; }

int party() {
    int forced = g_tuning.players;
    if (forced >= 1 && forced <= 8) return forced;
    return clamp_party((s32)W(G_NUM_PLAYERS));
}

bool elite(uint32_t creature) {
    auto it = g_elites.find(creature);
    return it != g_elites.end() && W(creature + C_HP_MAX) == it->second;
}

// ---- Creature_setStats(hp%, armour%, damage%, attack%, exp%, this, rollHp): f12..f16, a0, a1 ------------------------
void set_stats(Ctx* c, RecompFn original) {
    if (!soulscombat::active() || !g_tuning.on) { original(c); return; }
    g_calls++;
    const Tuning& t = g_tuning;
    const u32 obj = (u32)c->r[4];
    const int n = party();
    // what the game would do with this party (its own test: two or more players and the word 0x4f713c clear)
    const bool game_scales = n >= 2 && W(G_NO_PARTY_SCALING) == 0;
    const u32 rank = call_fn(c, nullptr, BOSS_RANK, obj) & 0xff;
    const u32 type = W(obj + O_TYPE);
    const bool damage_rule = rank != 2 && type != 0 && !name_is(type, "droid");   // the game's own condition for damage
    // an elite: an ordinary creature, chosen by its figure (level-file creatures by their place; others also by the tick)
    const u32 salt = g_level_load ? 0x454c4954u : 0x454c4954u ^ W(0x44fdcc);      // "ELIT", g_simFrame
    const bool is_elite = rank == 0 && (s32)(creature_figure(obj, salt) % 100u) < t.elite[n - 1];
    const int k = n - 1;
    const s32 hp_row = rank >= 2 ? t.boss_hp[k] : t.hp[k];
    const bool games_numbers = hp_row == 100 + 60 * k && t.damage[k] == 100 + 15 * k && t.exp[k] == 100 * n && n <= 4 &&
                               n == clamp_party((s32)W(G_NUM_PLAYERS));   // and the count the game reads is that party
    ensure_block();
    u32 level = level_figure();
    if ((u32)PR(H_LEVEL) != level) PS(H_LEVEL, (s32)level);
    if (games_numbers && !is_elite) {
        // the game's own numbers: the original as it is
        g_passed++;
        original(c);
    } else {
        // the game's player-count step done here (the multipliers), the original run with a count of one
        float fh = game_scales ? (float)hp_row / 100.0f : 1.0f;
        float fd = game_scales && damage_rule ? (float)t.damage[k] / 100.0f : 1.0f;
        float fe = game_scales ? (float)t.exp[k] / 100.0f : 1.0f;
        if (is_elite) {
            fh *= (float)t.elite_hp / 100.0f;
            fd *= (float)t.elite_damage / 100.0f;
            fe *= (float)t.elite_exp / 100.0f;
        }
        c->f[12] = bits(flt(c->f[12]) * fh);
        c->f[14] = bits(flt(c->f[14]) * fd);
        c->f[16] = bits(flt(c->f[16]) * fe);
        const u32 count = W(G_NUM_PLAYERS);
        PW(G_NUM_PLAYERS, 1);
        original(c);
        PW(G_NUM_PLAYERS, count);
    }
    if (is_elite) { g_elites[obj] = W(obj + C_HP_MAX); bump(H_ELITES); }
    else g_elites.erase(obj);
    if (g_elites.size() > 4096) g_elites.clear();
    PS(H_PARTY, n);
    bump(H_SCALED);
    if (rank >= 2) bump(H_BOSSES);
    bump(H_HP_SUM, (s32)F(obj + C_HP_MAX));
    if (g_log)
        fprintf(stderr, "party: n=%d %s rank %u%s%s: hit points %.1f, damage %d-%d, experience %.0f%s\n", n,
                type && ok(type, 1) ? (const char*)(g_ram + (type & 0x1FFFFFFF)) : "(no type name)", rank, is_elite ? " ELITE" : "",
                g_level_load ? " (level file)" : "", F(obj + C_HP_MAX), (int)(s16)(W(obj + 0xd0) & 0xffff), (int)(s16)(W(obj + 0xd0) >> 16),
                F(obj + 0xd8), games_numbers && !is_elite ? " (the game's own)" : "");
}

std::string figures() {
    char text[512];
    snprintf(text, sizeof text, "party: %s, party of %d, creatures scaled %d (%llu calls here, %llu as the game's own), elites %d, bosses %d, "
             "extra creatures %d (%d not made), tuning %08x",
             soulscombat::active() && g_tuning.on ? "on" : "off", party(), PR(H_SCALED), (unsigned long long)g_calls, (unsigned long long)g_passed,
             PR(H_ELITES), PR(H_BOSSES), PR(H_EXTRAS), PR(H_EXTRAS_REFUSED), figure());
    return text;
}

}  // namespace partyscale
