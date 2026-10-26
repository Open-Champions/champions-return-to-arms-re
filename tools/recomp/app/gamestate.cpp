// gamestate.cpp - see gamestate.h.  Reads the game's state out of its memory; never writes there,
// never calls the game.  Everything is bounds-checked: a pointer that does not lie in main memory
// reads as nothing, so a frame taken in the middle of a level change gives an empty state, not a fault.
//
// Sources (each use below names its own): docs/player.md (the player record), docs/objects.md and
// docs/creatures.md (objects, creatures, the pool, handle lists), docs/ui.md (the HUD's own code and
// globals), FINDINGS.md rows as cited, symbols/*.tsv for names.  What was found for this file by
// reading the HUD's functions is written up in docs/issues/native-hud.md, "Where the numbers come
// from", with what was checked on the running game.
#include "gamestate.h"
#include "../rt/moved.h"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;

// (RAM_SIZE: ../rt/ramsize.h, through moved.h)

// ---- addresses ------------------------------------------------------------------------------------
const u32 G_PLAYERS = 0x4D8AF0, PLAYER_SIZE = 0x4C30;   // docs/player.md
// (a per-slot table is reached as party8_at(table) + slot x size: in a game of five to eight the tables are moved with
// room for eight, and slots 4..7 lie past the old end, where party8_at alone would not follow - rt/moved.h)
const u32 G_NUM_PLAYERS = 0x4D8AE0;                     // names.tsv g_numPlayers (s32)
const u32 G_NETWORK_MODE = 0x402791;                    // names.tsv g_networkMode (s8)
const u32 G_NUM_PEERS = 0x4027C4;                       // names.tsv g_numPeers (s32)
const u32 G_PEER_LOCAL = 0x5C3D0C, PEER_SIZE = 0x44E0;  // net_isLocalSlot 0x13e150: slot >= g_numPeers ? 1 : u8 here + slot x 0x44e0 (g_peers 0x5bf838 + 0x44d4)
const u32 G_PEER_GONE = 0x5C3D0D;                       // net_isSlotActive 0x13dd40: +0x44d5 = disconnected
const u32 G_PEER_DESYNC = 0x5C3D0F;                     // +0x44d7: "... IS OUT OF SYNC!" (hud draw task 0x1dbc48; FINDINGS D1)
const u32 G_SIM_FRAME = 0x44FDCC;                       // g_simFrame (FINDINGS V28)
const u32 G_LEVEL_NAME = 0x41B721;                      // g_levelName (FINDINGS V2; Ran)
const u32 G_PENDING_LEVEL = 0x41B6D0;                   // pending level name: non-empty = a level change was asked for (docs/ui.md message 7)
const u32 G_PAUSED = 0x41B4F4;                          // g_paused s32 (docs/ui.md P3)
const u32 G_PAUSE_MENU_OPEN = 0x44F208;                 // u8: 1 at 0x18e3f4 (pause menu open 0x18e334), 0 at 0x18dfb8
const u32 G_LOCAL_MENU_OPEN = 0x41B69D;                 // g_localMenuOpen u8 (names.tsv): inventory / character sheet of this machine
const u32 G_MENU_OPEN_FLAG = 0x41B4F8;                  // s32: any full-screen menu of this machine (first test of hud_drawPlayerStatus 0x1d9cd4)
const u32 G_HUD_SUPPRESSED = 0x4F66A8;                  // s8: cutscene, dialogue, mission menu, jump gate (second test there)
const u32 G_SHOP_OPEN = 0x41B50C;                       // s32 (third test there)
const u32 G_LOCAL_CAMERA = 0x4F8450;                    // pointer; +0x34 mode: 1 follow, 0 held, 3..5 free (docs/issues/native-first-person.md 2)
const u32 G_CUTSCENE_ACTIVE = 0x44FCD0;                 // g_cutsceneActive s8 (names.tsv)
const u32 G_DIALOG_DATA = 0x8E2D60;                     // != 0: a conversation is open (dialog_isOpen 0x22fbc0)
const u32 G_HELP_OPEN = 0x41B928;                       // u8: the modal help box (hud_showHelpMessage 0x1d9830, help_task 0x1dcc78)
const u32 G_NOTICE_OPEN = 0x41B518;                     // u8[4]: per-player notice box (hud_showPlayerNotice 0x1d9954; docs/ui.md P2)
const u32 G_IN_FRONTEND = 0x41B510;                     // s32 (rig symbol g_inFrontend; Ran: 1 before a game, 0 in a level)
const u32 G_LEVEL_LOADED = 0x4F85B0;                    // s32: 0 in the title level, 1 in every other
const u32 G_LOADSCREEN = 0x506094;                      // s8: the loading screen is up
const u32 G_WARMUP_FRAMES = 0x506048;                   // s32: the wait loop after a load (session loop 0x322998; docs/ui.md P1)
const u32 G_WORLD_PIECES_DRAWN = 0x44F054;              // u8: 0 from a level change until the new level draws (docs/ui.md P1)
const u32 G_HUD_FADE = 0x4F66AC;                        // s32 0..0x80 (hud_setFade 0x1df5d0)
const u32 G_TASK_COUNT = 0x44FDB8, G_TASKS = 0x840100;  // task table: 16 bytes {fn, priority, name, flags} (task_add 0x19e4a0)
const u32 FN_HUD_RUN = 0x1DB870, FN_JUMP_GATE = 0x27DD74, FN_MISSION_RUN = 0x2316FC, FN_MISSION_DRAW = 0x232300, FN_DEATH = 0x1E75E8,
          FN_PAUSE_MENU = 0x18CC08, FN_INVENTORY = 0x1C1108, FN_SHOP = 0x1C6068;        // docs/ui.md "Tasks registered here"
const u32 G_EXP_TABLE = 0x41B558;                       // s32[]: experience at which level n ends; [n - 1] where it starts (0x1d9cd4)
const u32 G_GOLD_FLOATERS = 0x86A900, GOLD_FLOATER_SIZE = 0x24, GOLD_FLOATERS = 8;     // +0x1c amount (0 free), +0x20 slot (hud_addGoldFloater 0x1dc268)
const u32 G_GOLD_PENDING = 0x86ACE8;                    // s32[4] (hud_tickGold 0x1dcb80)
const u32 G_POTION_NAMES = 0x4EF4C8;                    // char*[18]: 0..8 the mana potions, 9..17 the health potions (player_countPotions 0x1ba5f8)
const u32 G_BTN_USE = 0x41B9C0;                         // u32[4] (symbols/player.tsv)
const u32 G_SKILL_MARKER = 0x535E30;                    // the fixed name an ability record carries when it is a Skill object (docs/player.md, ability record +0x00)
const u32 G_SKILL_TABLE = 0x41B170, SKILLS = 102;       // Skill*[102] by id; skill +0 char* name, +8 kind, +0xc s16 recast frames
const u32 G_CLASS_KEYS[7] = {0x53E018, 0x53E048, 0x53E030, 0x53E058, 0x53E068, 0x53E078, 0x53E090};    // text keys by class index (text_getClassName 0x1eb0f8)
const u32 G_ITEM_PREFIX = 0x400E50, ITEM_PREFIX_SIZE = 0x28, G_ITEM_SUFFIX = 0x4019E0, ITEM_SUFFIX_SIZE = 0x14;   // item name parts (0x101e48)
const u32 G_TEXT_HASH = 0x7C2EA0, TEXT_SLOTS = 0x2000;  // text_lookup 0x173c84: 8192 pointers to keys; the text follows its key as UTF-16
const u32 G_POOLS = 0x403A10;                           // {size, count, base, free head} x 3 (docs/objects.md allocator; pool_new 0x14fdb8)
const u32 VT_GAMEOBJECT = 0x5122A8;                     // what a destroyed object's block is left with at +0x48
const u32 G_GRID = 0x5DB4F0;                            // 120 x 120 handle-list heads, cell = ((int)coord + 0x3c00) >> 8 (docs/objects.md)
const u32 G_HANDLE_NODES = 0x847268, G_HANDLE_NODES_END = 0x864EA8;   // the node pool (handle_link 0x1a1738)
const u32 G_PROMPT_TEXT = 0x864F50, PROMPT_TEXT_SIZE = 0x200;         // UTF-16 per slot (Player_interact 0x1b2640, display mode)
const u32 G_PROMPT_ALPHA = 0x4D8AC0;                    // s32[4]: > 0 while the prompt shows (+7 a tick with something in reach, -7 without)
const u32 G_SPELL_SELECT_HELD = 0x41B818;               // s32[4]: the quick-cast selector is open (FINDINGS K1)
const u32 G_SPELL_SELECT_ALPHA = 0x86A8D8;              // s32[4] 0..0x80
const u32 G_SPELL_SELECT_DIR = 0x4F66B8;                // s32[4]: highlighted position 0..7 clockwise from up, -1 none
const u32 G_MENU_INPUT_LOCKOUT = 0x41B4FC;              // FINDINGS D26
const u32 G_HUD_MESSAGE = 0x86AB78;                     // UTF-16 (hud_showMessage 0x1d92a0)
const u32 G_HUD_MESSAGE_FRAMES = 0x4F66E0;              // s16; +2 s8 "force": shown although the HUD is suppressed
const u32 G_COMPASS_ON = 0x4F66D5;                      // s8 countdown: script showCompass sets 5 each call, hud_run takes 1 a tick
const u32 G_COMPASS_TARGET = 0x86A8F0;                  // float[3]
const u32 G_CAMERA_POS = 0x44F038, G_CAMERA_MATRIX = 0x44F110, G_PROJ_SCALE = 0x44F108;    // camera_setView 0x18a2b0
const u32 G_BOSS_MAX = 0x41B6A4, G_BOSS_NAME = 0x41BA40;   // the boss meter: s32 hp 0x41b6a0, s32 max 0x41b6a4, the name's key (Creature_run 0x113960-0x113adc; FINDINGS E11)
const u32 G_BOSS_NAMES[16] = {0x52FD48, 0x52FD58, 0x52FD68, 0x52FD78, 0x52FD88, 0x52FD90, 0x52FDA0, 0x52FDB0, 0x52FDC0, 0x52FDD0,
                              0x52FDE0, 0x52FDF0, 0x52FE00, 0x52FE10, 0x52FE50, 0x52FE60};     // type names of rank 2 (creature_bossRank 0x10d940)
const u32 G_PVP_MODE_A = 0x4F711C;                      // s32 (Player_isEnemy 0x1b5ea8)
const u32 G_CHECKSUM_FAILED = 0x4F7144;                 // s32: "Net Checksum Failure" (0x1dbc48)
const u32 G_NET_STALL = 0x40279C;                       // s32: displayed frames without a tick (docs/ui.md HUD; FINDINGS L19)
const u32 G_NET_KICKED = 0x4027A0;                      // u8
const u32 G_NET_EXIT = 0x4F6948;                        // s16 g_netExitCountdown (FINDINGS V65)
const u32 G_CHAT_LOG = 0x8E8AC8, CHAT_LINE = 0x7E, CHAT_LINES = 8;    // +2 s8 sender slot (0xfe empty), +3 text (textMessageDraw 0x31deec)
const u32 G_CHAT_AGE = 0x8E8EB8;                        // s32[8] ticks; shown while < 601
// vtables of what can be used (vtables.txt; slot 13 = the prompt)
struct Usable { u32 vtable; u8 kind; };
const Usable USABLES[] = {
    {0x50E100, RTA_GS_USE_DOOR}, {0x50E068, RTA_GS_USE_DOOR}, {0x50DFD8, RTA_GS_USE_DOOR}, {0x5138C8, RTA_GS_USE_DOOR}, {0x513B68, RTA_GS_USE_DOOR},
    {0x5136D8, RTA_GS_USE_PORTAL}, {0x5133C0, RTA_GS_USE_OTHER}, {0x5130C0, RTA_GS_USE_OTHER},
    {0x5118D8, RTA_GS_USE_CHEST}, {0x513468, RTA_GS_USE_CHEST}, {0x513168, RTA_GS_USE_CHEST}, {0x5119F8, RTA_GS_USE_CHEST}, {0x513330, RTA_GS_USE_CHEST},
    {0x513030, RTA_GS_USE_CHEST}, {0x50DC78, RTA_GS_USE_SAVEPOINT}, {0x50DBE8, RTA_GS_USE_GATE}, {0x50D918, RTA_GS_USE_LEVER}, {0x50DF48, RTA_GS_USE_LEVER},
    {0x511450, RTA_GS_USE_LEVER}, {0x511BA8, RTA_GS_USE_ITEM}, {0x511C38, RTA_GS_USE_ITEM}, {0x50D590, RTA_GS_USE_PORTAL},
};

double now_usec() {
    return std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

// ---- reading -------------------------------------------------------------------------------------
struct Mem {
    const u8* ram = nullptr;
    bool ok(u32 a, u32 n = 4) const { return a >= 0x10000 && a < RAM_SIZE && n <= RAM_SIZE - a; }
    template <class T> T get(u32 a) const { T v{}; a = party8_at(a); if (ok(a, sizeof(T))) memcpy(&v, ram + a, sizeof(T)); return v; }   // moved.h
    u32 w(u32 a) const { return get<u32>(a); }
    int32_t i(u32 a) const { return get<int32_t>(a); }
    u16 h(u32 a) const { return get<u16>(a); }
    int16_t sh(u32 a) const { return get<int16_t>(a); }
    u8 b(u32 a) const { return get<u8>(a); }
    int8_t sb(u32 a) const { return get<int8_t>(a); }
    float f(u32 a) const { float v = get<float>(a); return std::isfinite(v) ? v : 0.0f; }
    u64 q(u32 a) const { return get<u64>(a); }
    // a zero-terminated string of the game, printable characters only
    void str(u32 a, char* out, size_t size) const {
        size_t n = 0;
        if (ok(a, 1)) {
            while (n + 1 < size && a + n < RAM_SIZE) {
                u8 c = ram[a + n];
                if (!c) break;
                out[n++] = (c >= 0x20 && c < 0x7F) ? (char)c : '?';
            }
        }
        out[n] = 0;
    }
    bool same(u32 a, const char* text) const {      // strcmp == 0
        if (!ok(a, 1)) return false;
        size_t n = strlen(text);
        return a + n < RAM_SIZE && !memcmp(ram + a, text, n + 1);
    }
    bool same_at(u32 a, u32 b) const {             // two strings of the game, equal
        if (!ok(a, 1) || !ok(b, 1)) return false;
        for (u32 k = 0; k < 64; k++) {
            if (ram[a + k] != ram[b + k]) return false;
            if (!ram[a + k]) return true;
        }
        return false;
    }
    bool same_nocase(u32 a, u32 b) const {
        if (!ok(a, 1) || !ok(b, 1)) return false;
        for (u32 k = 0; k < 64; k++) {
            u8 x = ram[a + k], y = ram[b + k];
            if (x >= 'A' && x <= 'Z') x += 32;
            if (y >= 'A' && y <= 'Z') y += 32;
            if (x != y) return false;
            if (!x) return true;
        }
        return false;
    }
    // UTF-16 of the game -> UTF-8.  Characters 0x7b..0x86 at the start are the game's button glyphs (pad_buttonMaskToGlyph 0x1eacb8): left out.
    void wide(u32 a, char* out, size_t size, u32 max_chars = 256) const {
        size_t n = 0;
        for (u32 k = 0; k < max_chars && ok(a + k * 2, 2); k++) {
            u32 c = h(a + k * 2);
            if (!c) break;
            if (k == 0 && c >= 0x7B && c <= 0x86) continue;
            if (c == '|') break;                    // alternatives of a text: the first one
            if (c < 0x20) c = ' ';
            if (c < 0x80) { if (n + 2 > size) break; out[n++] = (char)c; }
            else if (c < 0x800) { if (n + 3 > size) break; out[n++] = (char)(0xC0 | c >> 6); out[n++] = (char)(0x80 | (c & 0x3F)); }
            else { if (n + 4 > size) break; out[n++] = (char)(0xE0 | c >> 12); out[n++] = (char)(0x80 | ((c >> 6) & 0x3F)); out[n++] = (char)(0x80 | (c & 0x3F)); }
        }
        while (n > 0 && out[n - 1] == ' ') n--;
        size_t start = 0;
        while (start < n && out[start] == ' ') start++;
        if (start) memmove(out, out + start, n - start);
        out[n - start] = 0;
    }
    // The game's text table (text_lookup 0x173c84, hash 0x173a74): the address of the UTF-16 text for a key, 0 when there is none.
    u32 text(const char* key) const {
        u32 hash = 0;
        size_t len = 0;
        for (const char* p = key; *p; p++, len++) {
            hash = (hash + (u8)*p) * 0x401u;
            hash ^= (u32)((int32_t)hash >> 6);
        }
        hash *= 9u;
        u32 slot = (hash ^ (u32)((int32_t)hash >> 11)) & (TEXT_SLOTS - 1);
        for (u32 tries = 0; tries < 64; tries++) {
            u32 k = w(G_TEXT_HASH + slot * 4);
            if (!k) return 0;
            if (same(k, key)) return (k + (u32)len + 2) & ~1u;
            slot = (slot + 1) & (TEXT_SLOTS - 1);
        }
        return 0;
    }
    bool text_to(const char* key_in, char* out, size_t size) const {
        char key[96];                               // the game drops quotation marks from a key (a ShowName property carries them)
        size_t n = 0;
        for (const char* p = key_in; *p && n + 1 < sizeof key; p++) if (*p != '"') key[n++] = *p;
        key[n] = 0;
        u32 a = text(key);
        if (!a) { out[0] = 0; return false; }
        wide(a, out, size);
        return out[0] != 0;
    }
    // handle: a cell holding at most one node; node +0xc is the object (docs/objects.md "Handle lists"; accessor 0x3c2668)
    u32 handle(u32 cell) const {
        u32 node = w(cell);
        if (node < G_HANDLE_NODES || node >= G_HANDLE_NODES_END) return 0;
        u32 o = w(node + 0xC);
        return ok(o, 0x50) ? o : 0;
    }
};

float facing_radians(u16 word) { return (float)word * (6.2831853f / 65536.0f); }

void copy_text(char* to, size_t size, const char* from) {
    size_t n = strlen(from);
    if (n >= size) n = size - 1;
    memcpy(to, from, n);
    to[n] = 0;
}

// A kind of creature has a name in the level data ("FooBarSmall" style); there is no display name for ordinary
// monsters anywhere in memory (the game never shows one), so the type name itself is what is handed out.

struct Track {                  // a creature seen before
    u32 object = 0;
    u32 uid = 0;
    u32 type = 0;               // object +0x34 (type name pointer) when the uid was given
    int8_t serial = 0;          // object +0x230
    bool dead = false;
    bool named = false;
    bool metered = false;       // the name came from the boss meter's own key: kept, so the bar does not flip to the kind's name
    float health = 0, health_max = 0;
    float screen[3] = {0, 0, 0};    // of the frame before
    float head[3] = {0, 0, 0};      // the point above the head, in the world, of the frame before
    bool have_screen = false;
    u64 seen = 0;
    char name[RTA_GS_TEXT] = "";
    rta_gs_status status[4];
    u32 status_count = 0;
};

struct PlayerTrack {
    bool valid = false;
    u32 object = 0;
    bool alive = false;
    float health = 0, health_max = 0, health_coming = 0, mana = 0;
    int32_t experience = 0, gold_total = 0, level = 0;
    u32 bag_sum = 0;
    int bag_n = 0;
    int bag_n_defs = 0;
    u32 bag_def[192];
    int32_t bag_qty[192];
    float screen[3] = {0, 0, 0};
    float head[3] = {0, 0, 0};
    bool have_screen = false;
    rta_gs_status status[RTA_GS_STATUS];
    u32 status_count = 0;
    char name[RTA_GS_TEXT] = "";
};

const int TRACKS = 256;

}  // namespace

struct rta_gs_reader {
    rta_gamestate s;
    Mem m;
    Track track[TRACKS];
    PlayerTrack ptrack[RTA_GS_PLAYERS];
    u32 next_uid = 1;
    char level_seen[16] = "";
    u32 tick_seen = 0;
    bool baseline = false;      // the trackers hold the frame before of the same level
    float aspect = 4.0f / 3.0f;
    bool have_host_view = false;
    bool host_camera = false;   // ... and it carries a camera (a host may hand in the mode alone: its overhead view has no camera of its own)
    rta_gs_view host_view;
    int screen_delay = 1;
    double cost = 0;
    u32 tasks[64];
    int task_count = 0;
};

namespace {

typedef rta_gs_reader R;

bool has_task(const R& r, u32 fn) {
    for (int k = 0; k < r.task_count; k++) if (r.tasks[k] == fn) return true;
    return false;
}

void add_event(R& r, u8 kind, int slot, u32 uid, float amount, const float* position, const char* text, bool heavy = false) {
    rta_gamestate& s = r.s;
    if (s.event_count >= RTA_GS_EVENTS) { s.events_dropped++; return; }
    rta_gs_event& e = s.event[s.event_count++];
    memset(&e, 0, sizeof e);
    e.kind = kind;
    e.slot = (int8_t)slot;
    e.uid = uid;
    e.amount = amount;
    e.heavy = heavy;
    if (position) memcpy(e.position, position, sizeof e.position);
    if (text) copy_text(e.text, sizeof e.text, text);
}

// ---- the camera ----------------------------------------------------------------------------------
void game_view(const Mem& m, rta_gs_view& v) {
    // g_cameraMatrix: four rows of three; rows are world x, y, z, columns the camera's right, down, forward (camera_setView 0x18a2b0)
    float mat[12];
    for (int k = 0; k < 12; k++) mat[k] = m.f(G_CAMERA_MATRIX + k * 4);
    memset(&v, 0, sizeof v);
    for (int k = 0; k < 3; k++) {
        v.right[k] = mat[k * 3 + 0];
        v.up[k] = -mat[k * 3 + 1];
        v.forward[k] = mat[k * 3 + 2];
        v.eye[k] = m.f(G_CAMERA_POS + k * 4);
    }
    float F = m.f(G_PROJ_SCALE);                // 477.5 / tan(fov / 2) (camera_setProjection 0x18619c)
    v.fov = F > 1.0f ? 2.0f * atanf(477.5f / F) * 57.29578f : 50.0f;
    v.yaw = atan2f(v.forward[1], v.forward[0]);
}

bool project(const R& r, const float p[3], float out[3]) {
    const rta_gs_view& v = r.s.view;
    float d[3] = {p[0] - v.eye[0], p[1] - v.eye[1], p[2] - v.eye[2]};
    float x = d[0] * v.right[0] + d[1] * v.right[1] + d[2] * v.right[2];
    float y = -(d[0] * v.up[0] + d[1] * v.up[1] + d[2] * v.up[2]);
    float z = d[0] * v.forward[0] + d[1] * v.forward[1] + d[2] * v.forward[2];
    out[2] = z;
    if (z < 1.0f) { out[0] = out[1] = -1; return false; }
    // the vertex programs: sx = F k x / z, sy = F 0.4666667 y / z in pixels of the 1280 x 448 buffer from its centre
    // (docs/spec/render-pipeline.md 3; k = (4/3) / aspect, tools/recomp/app/gfx_rt.cpp)
    float F = 477.5f / tanf(v.fov * 0.5f * 0.01745329f);
    float k = (4.0f / 3.0f) / (r.aspect > 0.1f ? r.aspect : 4.0f / 3.0f);
    out[0] = 0.5f + F * k * x / z / 1280.0f;
    out[1] = 0.5f + F * 0.4666667f * y / z / 448.0f;
    return true;
}

// Where a point is in the picture that is SHOWN.  The picture of a blank was drawn one simulation tick before the memory
// read at that blank (the game sends a frame's packets at the start of the next; Ran: the game's own bars in the picture
// are one tick behind the fields, docs/issues/native-hud.md).  So the place that belongs to the picture is where the
// thing was one update ago: with a camera handed in by the host - which is the shown frame's own - the old place under
// that camera; with the camera read from memory - which is as new as the places - the projection made one update ago.
void delayed(const R& r, bool have_before, const float* head_before, const float* screen_before, const float* now, float* out) {
    if (r.screen_delay <= 0 || !have_before) { memcpy(out, now, 3 * sizeof(float)); return; }
    if (r.host_camera) project(r, head_before, out);
    else memcpy(out, screen_before, 3 * sizeof(float));
}

// ---- status effects ------------------------------------------------------------------------------
void add_status(rta_gs_status* list, u32& count, u32 room, u8 kind, u8 detail, float seconds) {
    if (count >= room) return;
    rta_gs_status& st = list[count++];
    st.kind = kind;
    st.detail = detail;
    st.pad = 0;
    st.seconds = seconds;
    st.seconds_most = seconds;
}

// the timers every creature has (docs/creatures.md "Status effects")
void creature_status(const Mem& m, u32 o, rta_gs_status* list, u32& count, u32 room) {
    static const struct { u32 offset; u8 kind; } SECONDS[] = {{0x340, RTA_GS_ST_BURN}, {0x344, RTA_GS_ST_CHILL}, {0x348, RTA_GS_ST_SHOCK},
                                                               {0x34C, RTA_GS_ST_POISON}, {0x350, RTA_GS_ST_DOT2}};
    for (const auto& t : SECONDS) {
        float v = m.f(o + t.offset);
        if (v > 0.0f && v < 100000.0f) add_status(list, count, room, t.kind, 0, v);
    }
    static const struct { u32 offset; u8 kind; } FRAMES[] = {{0x31C, RTA_GS_ST_STUN}, {0x314, RTA_GS_ST_ROOT}, {0x312, RTA_GS_ST_CHARM}};
    for (const auto& t : FRAMES) {
        int v = m.sh(o + t.offset);
        if (v != 0) add_status(list, count, room, t.kind, 0, v < 0 ? -1.0f : (float)v / 60.0f);
    }
    int slow = m.sb(o + 0x2FC);
    bool chilled = m.f(o + 0x344) > 0.0f;
    if (slow > 0 && !chilled) add_status(list, count, room, RTA_GS_ST_SLOW, (u8)slow, -1.0f);
}

// keep the largest value seen while a status runs, so that a ring can empty
void carry_most(rta_gs_status* list, u32 count, const rta_gs_status* before, u32 before_count) {
    for (u32 k = 0; k < count; k++) {
        for (u32 j = 0; j < before_count; j++) {
            if (before[j].kind == list[k].kind && before[j].detail == list[k].detail && before[j].seconds_most >= list[k].seconds) {
                list[k].seconds_most = before[j].seconds_most;
                break;
            }
        }
    }
}

// ---- creatures -----------------------------------------------------------------------------------
int boss_rank(const Mem& m, u32 o) {
    // creature_bossRank 0x10d940: the type name against sixteen names, three by their name property (left out), else the MiniBoss bit
    u32 type = m.w(o + 0x34);
    if (m.ok(type, 1)) for (u32 a : G_BOSS_NAMES) if (m.same_nocase(type, a)) return 2;
    return (m.q(o + 0xA8) & 1) ? 1 : 0;
}

// Player_isEnemy 0x1b5ea8 as data: is creature `o` an enemy of the player in `slot` (record `rec`)
bool hostile(const Mem& m, u32 o, u32 rec) {
    u32 f = m.w(o + 0xC);
    u64 cf = m.q(o + 0xA8);
    if (!(f & 0x20) || (f & 0x8) || (f & 0x1000000)) return false;     // 0x1b5eb8-0x1b5ed0
    if (cf & (0x4000000ull | 0x800ull)) return false;                   // 0x1b5ed8-0x1b5ee8
    if (m.sh(o + 0x312) == 0) return true;                              // not charmed: 0x1b5f48
    int team = m.sb(o + 0x310);
    return m.i(G_PVP_MODE_A) && team >= 0 && team != m.sb(rec + 0x4C24);    // 0x1b5f54-0x1b5f90
}

Track* find_track(R& r, u32 object) {
    for (Track& t : r.track) if (t.object == object) return &t;
    return nullptr;
}

Track* new_track(R& r) {
    Track* oldest = &r.track[0];
    for (Track& t : r.track) {
        if (!t.object) return &t;
        if (t.seen < oldest->seen) oldest = &t;
    }
    return oldest;
}

void creature_name(const Mem& m, u32 o, bool meter, char* out, size_t size, bool& named) {
    named = false;
    out[0] = 0;
    // a creature that can be talked to: ShowName (object +0x368) is a key of the text table (Creature_interactPrompt 0x116d50)
    u32 show = m.w(o + 0x368);
    if (m.ok(show, 1)) {
        char key[64];
        m.str(show, key, sizeof key);
        named = true;
        if (key[0] && m.text_to(key, out, size)) return;
    }
    // the creature the game's boss meter is about: the meter's own key (0x41ba40, written by Creature_getName 0x118418)
    if (meter) {
        char key[64];
        m.str(G_BOSS_NAME, key, sizeof key);
        if (key[0] && m.text_to(key, out, size)) return;
    }
    m.str(m.w(o + 0x34), out, size);            // the kind's own name in the level data
}

struct Found { u32 object; float distance; };

void read_creatures(R& r) {
    const Mem& m = r.m;
    rta_gamestate& s = r.s;
    // every creature lives in one of the object pools (docs/objects.md; pool table 0x403a10).  A block is a live creature
    // when it has the creature flag, a grid link whose node points back at it, and is not the husk a destructor leaves.
    static Found found[1024];
    int count = 0;
    float px[RTA_GS_PLAYERS], py[RTA_GS_PLAYERS];
    u32 pobj[RTA_GS_PLAYERS];
    int np = 0;
    for (int k = 0; k < RTA_GS_PLAYERS; k++) {
        if (s.player[k].present && s.player[k].object) { px[np] = s.player[k].position[0]; py[np] = s.player[k].position[1]; pobj[np] = s.player[k].object; np++; }
    }
    if (!np) return;
    const float REACH = 1150.0f;                // a little more than the widest view shows (the far corners at 21:9 are about 900 away)
    for (int pool = 1; pool < 3; pool++) {
        u32 size = m.w(G_POOLS + pool * 16), n = m.w(G_POOLS + pool * 16 + 4), base = m.w(G_POOLS + pool * 16 + 8);
        if (size < 0x3C8 || size > 0x4000 || n > 2048 || !m.ok(base, size) || (u64)base + (u64)size * n > RAM_SIZE) continue;
        for (u32 k = 0; k < n; k++) {
            u32 o = base + k * size;
            u32 f = m.w(o + 0xC);
            if ((f & 0x20060) != 0x20) continue;                // a creature, not a player, not the prediction copy
            if (f & 0x8000) continue;                           // hidden: not run (docs/objects.md flag 0x8000)
            u32 link = m.w(o + 8);
            if (!link || m.w(o + 0x48) == VT_GAMEOBJECT) continue;
            if (link < G_HANDLE_NODES || link >= G_HANDLE_NODES_END) continue;
            u32 partner = m.w(link + 8);
            if (partner < G_HANDLE_NODES || partner >= G_HANDLE_NODES_END || m.w(partner + 0xC) != o) continue;
            float x = m.f(o + 0x10), y = m.f(o + 0x14);
            float best = 1e30f;
            for (int p = 0; p < np; p++) {
                float d = (x - px[p]) * (x - px[p]) + (y - py[p]) * (y - py[p]);
                if (d < best) best = d;
            }
            bool marked = (m.q(o + 0xA8) & 0x80000000000ull) != 0;      // script showOnMap: the game's own map shows it (minimap_blipColor 0x1e40a8)
            if (best > REACH * REACH && !(marked && best < 3840.0f * 3840.0f)) continue;
            if (count < 1024) found[count++] = {o, best};
        }
    }
    if (count > RTA_GS_CREATURES) {
        // the nearest: a partial selection sort is enough for 64 of a few hundred
        for (int a = 0; a < RTA_GS_CREATURES; a++) {
            int least = a;
            for (int b = a + 1; b < count; b++) if (found[b].distance < found[least].distance) least = b;
            Found t = found[a]; found[a] = found[least]; found[least] = t;
        }
        s.creatures_dropped = count - RTA_GS_CREATURES;
        count = RTA_GS_CREATURES;
    }
    u32 first_rec = party8_at(G_PLAYERS) + (u32)(s.local_slot >= 0 ? s.local_slot : 0) * PLAYER_SIZE;
    bool meter_on = m.i(G_BOSS_MAX) > 0;
    for (int k = 0; k < count; k++) {
        u32 o = found[k].object;
        u32 f = m.w(o + 0xC);
        u64 cf = m.q(o + 0xA8);
        int state = m.sh(o + 0x232);
        // someone to talk to (ShowName, object +0x368) carries flag 0x8 as scenery does, and is not dead for that
        bool talker = m.ok(m.w(o + 0x368), 1) && (f & 0x100000) && state != 0x14;
        bool dead = ((f & 0x8) != 0 && !talker) || state == 0x14;   // flag 0x8 set with hp <= 0 (0x11149c); state 0x14 for the ones loaded dead
        Track* t = find_track(r, o);
        u32 type = m.w(o + 0x34);
        int8_t serial = m.sb(o + 0x230);
        if (t && (t->type != type || t->serial != serial)) t = nullptr;        // the block was given to another creature
        bool fresh = !t;
        if (fresh) {
            if (dead) continue;                                 // scenery that is "dead" from the start (flag 0x8: butterflies, corpses of a save)
            t = new_track(r);
            *t = Track();
            t->object = o;
            t->uid = r.next_uid++;
            t->type = type;
            t->serial = serial;
        }
        t->seen = s.updates;
        rta_gs_creature& c = s.creature[s.creature_count++];
        memset(&c, 0, sizeof c);
        c.uid = t->uid;
        c.object = o;
        c.ai_state = (int16_t)state;
        c.health = m.f(o + 0x228);
        c.health_max = m.f(o + 0x22C);
        if (c.health < 0) c.health = 0;
        c.position[0] = m.f(o + 0x10);
        c.position[1] = m.f(o + 0x14);
        c.position[2] = m.f(o + 0x18);
        c.height = m.f(o + 0x20);
        c.radius = m.f(o + 0x1C);
        c.facing = facing_radians(m.h(o + 0x38));
        c.target_slot = -1;
        int rank = boss_rank(m, o);
        c.boss_rank = (u8)rank;
        bool meter = meter_on && (cf & 1) && (cf & 0x80000000ull);     // the creature the boss meter is about: cflags bit 0 and bit 31 (0x113960)
        u32 flags = 0;
        if (dead) flags |= RTA_GS_CF_DEAD;
        if (!dead && hostile(m, o, first_rec)) flags |= RTA_GS_CF_HOSTILE;
        if (rank == 2 || meter) flags |= RTA_GS_CF_BOSS;
        if (cf & 1) flags |= RTA_GS_CF_MINIBOSS;
        if ((f & 0x1000000) || (cf & 0x4000000ull) || talker) flags |= RTA_GS_CF_FRIENDLY;
        if (m.b(o + 0x231)) flags |= RTA_GS_CF_INERT;
        if (cf & 0x80000000000ull) flags |= RTA_GS_CF_MARKED;
        if (state >= 6 && state <= 15) flags |= RTA_GS_CF_ATTACKING;
        u32 target = m.handle(o + 0x234);
        if (target && !dead) {
            for (int p = 0; p < RTA_GS_PLAYERS; p++) {
                if (s.player[p].present && s.player[p].object == target) { c.target_slot = (int8_t)p; if (flags & RTA_GS_CF_HOSTILE) flags |= RTA_GS_CF_AGGRO; }
            }
        }
        for (int p = 0; p < np; p++) {
            // a player's attack is aimed at it: the player's own target handle, while he attacks (state 0 ranged, 1 melee; docs/player.md)
            int action = m.i(pobj[p] + 0x58C);
            if ((action == 0 || action == 1) && m.handle(pobj[p] + 0x234) == o) flags |= RTA_GS_CF_TARGETED;
        }
        if (meter && !dead) s.boss_uid = c.uid;
        if (fresh || (meter && !t->metered) || (!t->metered && (s.updates & 63) == (c.uid & 63))) {
            creature_name(m, o, meter, t->name, sizeof t->name, t->named);
            t->metered = meter && t->name[0];
        }
        if (t->named) flags |= RTA_GS_CF_NAMED;
        memcpy(c.name, t->name, sizeof c.name);
        creature_status(m, o, c.status, c.status_count, 4);
        carry_most(c.status, c.status_count, t->status, t->status_count);
        memcpy(t->status, c.status, sizeof t->status);
        t->status_count = c.status_count;
        // a point just above the head: the game's own overhead effects use feet + height (0x112c9c); the drawn model is scaled by +0xdc
        float scale = m.f(o + 0xDC);
        if (!(scale > 0.2f && scale < 4.0f)) scale = 1.0f;
        float head[3] = {c.position[0], c.position[1], c.position[2] + c.height * (scale < 1.0f ? scale : 1.0f) + 6.0f};
        float now[3];
        bool on = project(r, head, now);
        delayed(r, t->have_screen, t->head, t->screen, now, c.screen);
        on = c.screen[2] >= 1.0f;
        memcpy(t->screen, now, sizeof t->screen);
        memcpy(t->head, head, sizeof t->head);
        t->have_screen = true;
        if (on && c.screen[0] >= 0 && c.screen[0] <= 1 && c.screen[1] >= 0 && c.screen[1] <= 1 && c.screen[2] >= 1) flags |= RTA_GS_CF_ONSCREEN;
        c.flags = flags;
        // what happened to it since the last frame
        if (!fresh && r.baseline && !(flags & RTA_GS_CF_INERT)) {
            float lost = t->health - c.health;
            if (lost > 0.05f && !t->dead) {
                bool heavy = c.health_max > 0 && lost >= 0.25f * c.health_max;
                u32 by = m.handle(o + 0x2E4);       // the last attacker (docs/creatures.md +0x2e4)
                int slot = -1;
                for (int p = 0; p < RTA_GS_PLAYERS; p++) if (by && s.player[p].present && s.player[p].object == by) slot = p;
                add_event(r, RTA_GS_EV_DAMAGE_DEALT, slot, c.uid, lost, head, nullptr, heavy);
            } else if (-lost > 0.01f * c.health_max && -lost > 0.5f && !dead) {
                add_event(r, RTA_GS_EV_HEAL, -1, c.uid, -lost, head, nullptr);
            }
            if (dead && !t->dead) add_event(r, RTA_GS_EV_KILL, -1, c.uid, 0, head, c.name);
        }
        t->health = c.health;
        t->health_max = c.health_max;
        t->dead = dead;
    }
    // forget what has not been in reach for two seconds
    for (Track& t : r.track) if (t.object && s.updates - t.seen > 120) t = Track();
}

// ---- players -------------------------------------------------------------------------------------
bool is_local(const Mem& m, int slot) {
    if (!m.sb(G_NETWORK_MODE)) return true;
    if (slot >= m.i(G_NUM_PEERS)) return true;                      // net_isLocalSlot 0x13e150
    return m.b(party8_at(G_PEER_LOCAL) + (u32)slot * PEER_SIZE) != 0;
}

bool is_active(const Mem& m, int slot) {
    if (!m.sb(G_NETWORK_MODE)) return true;                         // net_isSlotActive 0x13dd40
    return slot < m.i(G_NUM_PEERS) && m.b(party8_at(G_PEER_GONE) + (u32)slot * PEER_SIZE) == 0;
}

// An item's name as the game builds it (0x101e48, first language): [prefix] noun [of suffix]
void item_name(const Mem& m, u32 item, char* out, size_t size) {
    out[0] = 0;
    u32 def = m.w(item);
    u32 name = m.w(def);
    if (!m.ok(def, 0x40) || !m.ok(name, 1)) return;
    char raw[64], key[80];
    m.str(name, raw, sizeof raw);
    char* plus = strchr(raw, '+');
    bool whole = (m.q(item + 8) & 0x200) != 0;                     // item flag 0x200: the full descriptor is its own key
    if (plus && !whole) *plus = 0;
    snprintf(key, sizeof key, "%s_name", raw);
    char noun[48];
    if (!m.text_to(key, noun, sizeof noun)) copy_text(noun, sizeof noun, raw);
    char prefix[32] = "", suffix[32] = "", of[8] = "";
    u8 p = m.b(item + 0x20), sfx = m.b(item + 0x21);
    if (!whole && p != 0xFF && p < 200) {
        char pk[48];
        m.str(m.w(G_ITEM_PREFIX + p * ITEM_PREFIX_SIZE), pk, sizeof pk);
        if (pk[0]) m.text_to(pk, prefix, sizeof prefix);
    }
    if (!whole && sfx != 0xFF && sfx < 200) {
        char sk[48];
        m.str(m.w(G_ITEM_SUFFIX + sfx * ITEM_SUFFIX_SIZE), sk, sizeof sk);
        if (sk[0] && m.text_to(sk, suffix, sizeof suffix)) m.text_to("of", of, sizeof of);
    }
    char full[160];
    snprintf(full, sizeof full, "%s%s%s%s%s%s%s", prefix, prefix[0] ? " " : "", noun, suffix[0] ? " " : "", suffix[0] ? of : "", suffix[0] && of[0] ? " " : "", suffix);
    copy_text(out, size, full);
}

int potion_kind(const Mem& m, u32 name) {      // 0 mana, 1 health, -1 neither (player_countPotions 0x1ba5f8: by the definition's name)
    char text[40];
    m.str(name, text, sizeof text);
    if (!text[0]) return -1;
    for (int k = 0; k < 18; k++) if (m.same(m.w(G_POTION_NAMES + k * 4), text)) return k < 9 ? 0 : 1;
    return -1;
}

void read_slot(const Mem& m, u32 rec, u32 o, int which, rta_gs_player& p) {
    rta_gs_slot& q = p.slot[which];
    int index = m.sb(rec + 0x4A84 + which);                         // docs/player.md +0x4a84 / +0x4a85
    q.index = (int16_t)index;
    q.skill_id = -1;
    q.mana_cost = -1.0f;
    q.enough_mana = 1;
    if (index < 0 || index >= 15) return;
    u32 a = rec + 0x4440 + (u32)index * 0x68;
    int id = m.sh(a + 0x20);
    if (id < 0) return;
    q.filled = 1;
    q.skill_id = (int16_t)id;
    q.kind = m.b(a + 0x25);
    for (int k = 0; k < 48; k++) {                                   // +0x4b08 {id, rank}[48], ended by id -1 (player_getSkillRank 0x1bf330)
        int sid = m.sh(rec + 0x4B08 + k * 4);
        if (sid < 0) break;
        if (sid == id) { q.rank = m.sh(rec + 0x4B08 + k * 4 + 2); break; }
    }
    char name[40], key[56];
    bool new_style = m.same_at(a, G_SKILL_MARKER);                  // the marker name of abilities that are Skill objects, compared in memory
    u32 skill = (id > 0 && id < (int)SKILLS) ? m.w(G_SKILL_TABLE + (u32)id * 4) : 0;
    float most = 0;
    if (new_style && m.ok(skill, 0x68)) {
        m.str(m.w(skill), name, sizeof name);
        most = (float)m.sh(skill + 0xC) / 60.0f;                    // the recast time Player_castSkill 0x1a42b8 puts into object +0x4ae
    } else {
        m.str(a, name, sizeof name);
        most = (float)m.sh(a + 0x22) / 60.0f;
        float cost = m.f(a + 0x2C);
        if (cost > 0.0f && cost < 900.0f) { q.mana_cost = cost; q.enough_mana = p.mana >= cost; }
    }
    snprintf(key, sizeof key, "%s_name", name);                     // the selector's own lookup (hud_spellSelect 0x1ddd18)
    if (!m.text_to(key, q.name, sizeof q.name)) copy_text(q.name, sizeof q.name, name);
    q.cooldown = o ? (float)m.sh(o + 0x4AE) / 60.0f : 0.0f;         // one countdown for all abilities of the player
    if (q.cooldown < 0) q.cooldown = 0;
    q.cooldown_most = most > q.cooldown ? most : q.cooldown;
    q.active = o && m.i(o + 0x58C) == 5 && m.sh(rec + 0x4A60) == which;
}

void read_player(R& r, int slot) {
    const Mem& m = r.m;
    rta_gamestate& s = r.s;
    rta_gs_player& p = s.player[slot];
    PlayerTrack& t = r.ptrack[slot];
    u32 rec = party8_at(G_PLAYERS) + (u32)slot * PLAYER_SIZE;
    memset(&p, 0, sizeof p);
    if (slot >= s.player_count || !m.b(rec) || !is_active(m, slot)) { t.valid = false; return; }
    p.present = 1;
    p.local = is_local(m, slot);
    m.str(rec, p.name, sizeof p.name);
    p.class_index = m.i(rec + 0x50);
    {
        char key[40];
        int c = p.class_index;
        m.str(G_CLASS_KEYS[(c >= 0 && c < 7) ? c : 3], key, sizeof key);    // text_getClassName 0x1eb0f8: other values take the fourth key
        m.text_to(key, p.class_name, sizeof p.class_name);
    }
    p.level_acknowledged = (u8)m.sb(rec + 0x58);
    p.level = (u8)m.sb(rec + 0x59);
    p.experience = m.i(rec + 0x5C);
    int L = p.level_acknowledged;
    if (L >= 1 && L < 80) {
        p.experience_base = m.i(G_EXP_TABLE + (u32)(L - 1) * 4);
        p.experience_next = m.i(G_EXP_TABLE + (u32)L * 4);
    }
    p.health = m.f(rec + 0xAC);
    p.health_max = m.f(rec + 0xB0);
    p.health_coming = m.f(rec + 0xB4);
    p.mana = m.f(rec + 0xC0);
    p.mana_max = m.f(rec + 0xC4);
    p.mana_coming = m.f(rec + 0xC8);
    if (p.health < 0) p.health = 0;
    if (p.mana < 0) p.mana = 0;
    p.gold = m.i(rec + 0xE4);
    p.gold_coming = m.i(party8_at(G_GOLD_PENDING) + (u32)slot * 4);
    for (u32 k = 0; k < GOLD_FLOATERS; k++) {
        u32 a = G_GOLD_FLOATERS + k * GOLD_FLOATER_SIZE;
        if (m.i(a + 0x1C) > 0 && m.sb(a + 0x20) == slot) p.gold_coming += m.i(a + 0x1C);
    }
    p.skill_points = m.i(rec + 0xE8);
    p.stat_points = (u8)m.sb(rec + 0xEC);
    p.weapon_class = m.b(rec + 0x4A86);
    u32 o = m.w(rec + 0x43D8);
    if (!m.ok(o, 0x590) || !(m.w(o + 0xC) & 0x40)) o = 0;
    p.object = o;
    if (o) {
        u32 f = m.w(o + 0xC);
        p.alive = !(f & 0x8) && p.health > 0.0f;
        p.in_menu = (f & 0x400000) != 0;
        p.position[0] = m.f(o + 0x10);
        p.position[1] = m.f(o + 0x14);
        p.position[2] = m.f(o + 0x18);
        p.height = m.f(o + 0x20);
        p.facing = facing_radians(m.h(o + 0x38));
        p.action_state = m.i(o + 0x58C);
    }
    // the weapon in hand: +0x4434[active set +0x4a7c] (docs/player.md); ammunition: equipment slot 8 at +0x4410
    {
        int set = m.sb(rec + 0x4A7C) ? 1 : 0;
        u32 item = m.w(rec + 0x4434 + (u32)set * 4);
        if (item >= rec && item < rec + PLAYER_SIZE) item_name(m, item, p.weapon, sizeof p.weapon);
        u32 ammo = m.w(rec + 0x4410);
        if (ammo >= rec && ammo < rec + PLAYER_SIZE) p.ammunition = m.sh(ammo + 4);
    }
    // potions: bag 2 by the definitions' names; and the bags as a whole for "what was picked up"
    static const u32 BAG[3] = {0x130, 0x1338, 0x2540}, BAG_COUNT[3] = {0x1330, 0x2538, 0x3740};
    u32 sum = 0;
    int total = 0;
    for (int b = 0; b < 3; b++) {
        int n = m.i(rec + BAG_COUNT[b]);
        if (n < 0 || n > 64) n = 0;
        for (int k = 0; k < n; k++) {
            u32 item = rec + BAG[b] + (u32)k * 0x48;
            u32 def = m.w(item);
            int qty = m.sh(item + 4);
            sum = sum * 31u + def + (u32)qty * 7u + m.h(item + 0x20);
            total++;
            if (b == 2) {
                int kind = potion_kind(m, m.w(def));
                if (kind == 1) p.health_potions += qty;
                else if (kind == 0) p.mana_potions += qty;
            }
        }
    }
    if (o) {
        read_slot(m, rec, o, 0, p);
        read_slot(m, rec, o, 1, p);
        // the quick-cast selector (hud_spellSelect 0x1dd270): the eight positions it offers
        p.selector_open = (u8)(m.i(party8_at(G_SPELL_SELECT_ALPHA) + (u32)slot * 4) > 0 ? 1 : 0);
        p.selector_position = (int8_t)m.i(party8_at(G_SPELL_SELECT_DIR) + (u32)slot * 4);
        // status: the creature timers, then what only players have
        creature_status(m, o, p.status, p.status_count, RTA_GS_STATUS);
        int protect = m.sh(o + 0x4B4);                              // spawn protection (docs/player.md)
        int immune = m.sb(rec + 0x4C27);                            // hit immunity countdown
        if (protect > 0 || immune > 0) add_status(p.status, p.status_count, RTA_GS_STATUS, RTA_GS_ST_PROTECTED, 0, (float)(protect > immune ? protect : immune) / 60.0f);
        float per_tick = m.f(rec + 0xB8);
        if (p.health_coming > 0.01f) add_status(p.status, p.status_count, RTA_GS_STATUS, RTA_GS_ST_HEALING, 0, per_tick > 0.0001f ? p.health_coming / per_tick / 60.0f : -1.0f);
        per_tick = m.f(rec + 0xBC);
        if (p.mana_coming > 0.01f) add_status(p.status, p.status_count, RTA_GS_STATUS, RTA_GS_ST_MANA, 0, per_tick > 0.0001f ? p.mana_coming / per_tick / 60.0f : -1.0f);
        // timed modifiers of what is worn: item +0x24 {id, value, ?, frames}[4] (docs/player.md item record; Player_tickEnchantTimers 0x1bc560)
        for (int e = 0; e < 17; e++) {
            u32 item = m.w(rec + 0x43F0 + (u32)e * 4);
            if (item < rec || item >= rec + PLAYER_SIZE) continue;
            for (int k = 0; k < 4; k++) {
                int id = m.sh(item + 0x24 + k * 8), frames = m.sh(item + 0x24 + k * 8 + 6);
                if (id > 0 && frames > 0) add_status(p.status, p.status_count, RTA_GS_STATUS, RTA_GS_ST_ENCHANT, (u8)id, (float)frames / 60.0f);
            }
        }
        // the sixteen status counters (FINDINGS D12-D15; docs/creatures.md): what they stand for differs by counter, so they are handed out by index
        for (int k = 0; k < 16; k++) {
            int v = m.i(o + 0x36C + (u32)k * 4);
            if (v > 0 && v < 100000) add_status(p.status, p.status_count, RTA_GS_STATUS, RTA_GS_ST_COUNTER, (u8)k, k == 12 ? -1.0f : (float)v / 60.0f);
        }
        if (t.valid) carry_most(p.status, p.status_count, t.status, t.status_count);
        // the creature his attack is aimed at
        if (p.action_state == 0 || p.action_state == 1) {
            u32 target = m.handle(o + 0x234);
            if (target) if (Track* tr = find_track(r, target)) p.target_uid = tr->uid;
        }
        float head[3] = {p.position[0], p.position[1], p.position[2] + p.height + 6.0f};
        float now[3];
        project(r, head, now);
        delayed(r, t.valid && t.have_screen, t.head, t.screen, now, p.screen);
        memcpy(t.screen, now, sizeof t.screen);
        memcpy(t.head, head, sizeof t.head);
        t.have_screen = true;
    } else {
        t.have_screen = false;
    }
    // ---- what happened since the last frame ----
    int32_t gold_total = p.gold + p.gold_coming;
    bool same_object = t.valid && t.object == o;
    if (t.valid && r.baseline && !strcmp(t.name, p.name)) {
        float head[3] = {p.position[0], p.position[1], p.position[2] + p.height};
        bool leveled = p.level > t.level;
        if (p.experience > t.experience) add_event(r, RTA_GS_EV_EXPERIENCE, slot, 0, (float)(p.experience - t.experience), head, nullptr);
        if (leveled) add_event(r, RTA_GS_EV_LEVEL_UP, slot, 0, (float)p.level, head, nullptr);
        if (gold_total != t.gold_total) add_event(r, RTA_GS_EV_GOLD, slot, 0, (float)(gold_total - t.gold_total), head, nullptr);
        if (same_object && o) {
            float lost = t.health - p.health;
            bool resized = fabsf(t.health_max - p.health_max) > 0.01f;     // the maximum changed (a level, an item): not a hit
            if (resized || leveled) lost = 0;
            if (lost > 0.05f) {
                // who did it: the player object's last attacker (docs/creatures.md +0x2e4); its place, for a mark of where the hit came from
                u32 by = m.handle(o + 0x2E4), uid = 0;
                float from[3] = {head[0], head[1], head[2]};
                if (by) {
                    from[0] = m.f(by + 0x10); from[1] = m.f(by + 0x14); from[2] = m.f(by + 0x18);
                    if (Track* tr = find_track(r, by)) uid = tr->uid;
                }
                add_event(r, RTA_GS_EV_DAMAGE_TAKEN, slot, uid, lost, from, nullptr, p.health_max > 0 && lost >= 0.2f * p.health_max);
            }
            // healing: a potion starts (the amount it will deliver), or health jumps (a spell); slow regeneration and the
            // refill of a level-up are not events
            float coming = p.health_coming - t.health_coming;
            if (coming > 0.5f) add_event(r, RTA_GS_EV_HEAL, slot, 0, coming, head, nullptr);
            else if (-lost > 1.0f && -lost > 0.02f * p.health_max && !leveled && p.health_coming <= 0.01f && t.health > 0.0f)
                add_event(r, RTA_GS_EV_HEAL, slot, 0, -lost, head, nullptr);
            if (t.alive && !p.alive) add_event(r, RTA_GS_EV_PLAYER_DIED, slot, 0, 0, head, nullptr);
        }
        // the bags: which definitions have more or fewer pieces than before
        if (sum != t.bag_sum || total != t.bag_n) {
            u32 defs[192];
            int32_t qty[192];
            int n = 0;
            for (int b = 0; b < 3; b++) {
                int cnt = m.i(rec + BAG_COUNT[b]);
                if (cnt < 0 || cnt > 64) cnt = 0;
                for (int k = 0; k < cnt; k++) {
                    u32 item = rec + BAG[b] + (u32)k * 0x48;
                    u32 def = m.w(item);
                    int q = m.sh(item + 4);
                    if (q < 1) q = 1;
                    int at = 0;
                    while (at < n && defs[at] != def) at++;
                    if (at == n) { defs[n] = def; qty[n] = 0; n++; }
                    qty[at] += q;
                }
            }
            for (int k = 0; k < n; k++) {
                int before = 0;
                for (int j = 0; j < t.bag_n_defs; j++) if (t.bag_def[j] == defs[k]) before = t.bag_qty[j];
                if (qty[k] != before) {
                    // name it by any record of that definition
                    char name[RTA_GS_TEXT] = "";
                    for (int b = 0; b < 3 && !name[0]; b++) {
                        int cnt = m.i(rec + BAG_COUNT[b]);
                        if (cnt < 0 || cnt > 64) cnt = 0;
                        for (int j = 0; j < cnt; j++) {
                            u32 item = rec + BAG[b] + (u32)j * 0x48;
                            if (m.w(item) == defs[k]) { item_name(m, item, name, sizeof name); break; }
                        }
                    }
                    add_event(r, qty[k] > before ? RTA_GS_EV_ITEM : RTA_GS_EV_ITEM_LOST, slot, 0, (float)abs(qty[k] - before), head, name);
                }
            }
            for (int j = 0; j < t.bag_n_defs; j++) {
                bool still = false;
                for (int k = 0; k < n; k++) if (defs[k] == t.bag_def[j]) still = true;
                if (!still) {
                    char raw[40], key[56], name[RTA_GS_TEXT];
                    m.str(m.w(t.bag_def[j]), raw, sizeof raw);
                    if (char* plus = strchr(raw, '+')) *plus = 0;
                    snprintf(key, sizeof key, "%s_name", raw);
                    if (!m.text_to(key, name, sizeof name)) copy_text(name, sizeof name, raw);
                    add_event(r, RTA_GS_EV_ITEM_LOST, slot, 0, (float)t.bag_qty[j], head, name);
                }
            }
            memcpy(t.bag_def, defs, sizeof(u32) * (size_t)n);
            memcpy(t.bag_qty, qty, sizeof(int32_t) * (size_t)n);
            t.bag_n_defs = n;
        }
    } else {
        // first sight of this character: take the bags as they are
        int n = 0;
        for (int b = 0; b < 3; b++) {
            int cnt = m.i(rec + BAG_COUNT[b]);
            if (cnt < 0 || cnt > 64) cnt = 0;
            for (int k = 0; k < cnt; k++) {
                u32 item = rec + BAG[b] + (u32)k * 0x48;
                u32 def = m.w(item);
                int q = m.sh(item + 4);
                if (q < 1) q = 1;
                int at = 0;
                while (at < n && t.bag_def[at] != def) at++;
                if (at == n) { t.bag_def[n] = def; t.bag_qty[n] = 0; n++; }
                t.bag_qty[at] += q;
            }
        }
        t.bag_n_defs = n;
    }
    t.valid = true;
    t.object = o;
    t.alive = p.alive;
    t.health = p.health;
    t.health_max = p.health_max;
    t.health_coming = p.health_coming;
    t.mana = p.mana;
    t.experience = p.experience;
    t.gold_total = gold_total;
    t.level = p.level;
    t.bag_sum = sum;
    t.bag_n = total;
    memcpy(t.status, p.status, sizeof t.status);
    t.status_count = p.status_count;
    copy_text(t.name, sizeof t.name, p.name);
}

// ---- the prompt ----------------------------------------------------------------------------------
void read_prompt(R& r) {
    const Mem& m = r.m;
    rta_gamestate& s = r.s;
    rta_gs_prompt& q = s.prompt;
    memset(&q, 0, sizeof q);
    q.slot = -1;
    int slot = s.local_slot;
    if (slot < 0) return;
    const rta_gs_player& p = s.player[slot];
    // the tests Player_draw makes before it draws the prompt (0x1a47a0-0x1a4800)
    if (m.i(party8_at(G_PROMPT_ALPHA) + (u32)slot * 4) <= 0 || !p.alive || m.i(G_PAUSED) || m.i(G_MENU_INPUT_LOCKOUT) || m.i(party8_at(G_SPELL_SELECT_HELD) + (u32)slot * 4) || m.w(G_DIALOG_DATA))
        return;
    m.wide(party8_at(G_PROMPT_TEXT) + (u32)slot * PROMPT_TEXT_SIZE, q.text, sizeof q.text);
    if (!q.text[0]) return;
    q.active = 1;
    q.slot = (int8_t)slot;
    u32 first = m.h(party8_at(G_PROMPT_TEXT) + (u32)slot * PROMPT_TEXT_SIZE);
    q.button = (first >= 0x7B && first <= 0x86) ? m.w(party8_at(G_BTN_USE) + (u32)slot * 4) : 0;      // a glyph in front = a button does it
    q.kind = RTA_GS_USE_OTHER;
    // what it is about is not kept anywhere: ask as Player_interact 0x1b2640 asks - the nearest usable object (flag 0x100000)
    // in the box x, y +-48, z .. z + 60 round the player, through the grid (world_collectObjectsInBox 0x14a928)
    float x = p.position[0], y = p.position[1], z = p.position[2];
    int gx0 = ((int)(x - 48.0f) + 0x3BA0) >> 8, gx1 = ((int)(x + 48.0f) + 0x3C60) >> 8;
    int gy0 = ((int)(y - 48.0f) + 0x3BA0) >> 8, gy1 = ((int)(y + 48.0f) + 0x3C60) >> 8;
    float best = 1e30f;
    for (int gy = gy0 < 0 ? 0 : gy0; gy <= gy1 && gy < 120; gy++) {
        for (int gx = gx0 < 0 ? 0 : gx0; gx <= gx1 && gx < 120; gx++) {
            u32 node = m.w(G_GRID + (u32)(gy * 120 + gx) * 4);
            for (int guard = 0; guard < 512 && node >= G_HANDLE_NODES && node < G_HANDLE_NODES_END; guard++, node = m.w(node)) {
                u32 o = m.w(node + 0xC);
                if (!m.ok(o, 0x50)) continue;
                u32 f = m.w(o + 0xC);
                if (!(f & 0x100000) || (f & 0x20000)) continue;
                float ox = m.f(o + 0x10), oy = m.f(o + 0x14), oz = m.f(o + 0x18), rad = m.f(o + 0x1C);
                if (fabsf(ox - x) > 48.0f + rad || fabsf(oy - y) > 48.0f + rad || oz > z + 60.0f || z > oz + m.f(o + 0x20)) continue;
                float d = (ox - x) * (ox - x) + (oy - y) * (oy - y) + (oz - z) * (oz - z);
                if (d < best) { best = d; q.object = o; q.position[0] = ox; q.position[1] = oy; q.position[2] = oz; }
            }
        }
    }
    if (q.object) {
        u32 vt = m.w(q.object + 0x48);
        u32 f = m.w(q.object + 0xC);
        for (const Usable& u : USABLES) if (u.vtable == vt) q.kind = u.kind;
        if (q.kind == RTA_GS_USE_OTHER && (f & 0x20)) {
            // a creature with a ShowName: someone to talk to; a shop when its property list has "shop=" (Creature_interactPrompt 0x116d50)
            q.kind = RTA_GS_USE_TALK;
            u32 props = m.w(q.object + 0x2C);
            for (int k = 0; k < 32 && m.ok(props + (u32)k * 4); k++) {
                u32 text = m.w(props + (u32)k * 4);
                if (!text) break;
                if (m.ok(text, 5) && !memcmp(m.ram + text, "shop=", 5)) q.kind = RTA_GS_USE_SHOP;
            }
        }
    }
}

}  // namespace

// ---- the interface ---------------------------------------------------------------------------------
extern "C" {

rta_gs_reader* rta_gs_create(void) {
    rta_gs_reader* r = new rta_gs_reader();
    memset(&r->s, 0, sizeof r->s);
    r->s.version = RTA_GS_VERSION;
    r->s.struct_size = sizeof(rta_gamestate);
    r->s.local_slot = -1;
    r->s.aspect = r->aspect;
    return r;
}

void rta_gs_destroy(rta_gs_reader* reader) { delete reader; }
const rta_gamestate* rta_gs_state(const rta_gs_reader* reader) { return &reader->s; }
void rta_gs_set_aspect(rta_gs_reader* reader, float aspect) { reader->aspect = aspect > 0.1f ? aspect : 4.0f / 3.0f; }
void rta_gs_set_screen_delay(rta_gs_reader* reader, int frames) { reader->screen_delay = frames > 0 ? 1 : 0; }
double rta_gs_cost_usec(const rta_gs_reader* reader) { return reader->cost; }

void rta_gs_set_view(rta_gs_reader* reader, const rta_gs_view* view) {
    reader->have_host_view = view != nullptr;
    if (view) reader->host_view = *view;
}

int rta_gs_project(const rta_gs_reader* reader, const float world[3], float out[3]) { return project(*reader, world, out) ? 1 : 0; }

const rta_gamestate* rta_gs_update(rta_gs_reader* reader, const uint8_t* ram) {
    R& r = *reader;
    rta_gamestate& s = r.s;
    double t0 = now_usec();
    r.m.ram = ram;
    const Mem& m = r.m;
    u64 updates = s.updates + 1;
    // everything of a frame is made anew; what carries over is in the reader
    s.version = RTA_GS_VERSION;
    s.struct_size = sizeof(rta_gamestate);
    s.updates = updates;
    s.phase = 0;
    s.hud_hidden = 0;
    s.player_count = 0;
    s.local_slot = -1;
    s.creature_count = 0;
    s.creatures_dropped = 0;
    s.boss_uid = 0;
    s.event_count = 0;
    s.events_dropped = 0;
    s.message[0] = 0;
    s.message_frames = 0;
    s.compass_on = 0;
    s.online = 0;
    s.net_notice = RTA_GS_NET_OK;
    s.net_notice_slot = -1;
    s.net_stall_frames = 0;
    s.net_exit_frames = 0;
    s.chat_count = 0;
    s.aspect = r.aspect;
    memset(&s.prompt, 0, sizeof s.prompt);
    s.prompt.slot = -1;
    if (!ram) { r.baseline = false; r.cost = now_usec() - t0; return &s; }

    s.sim_tick = m.w(G_SIM_FRAME);
    m.str(G_LEVEL_NAME, s.level, sizeof s.level);
    // the tasks registered now say which screens are up (docs/ui.md)
    r.task_count = 0;
    int tasks = m.i(G_TASK_COUNT);
    if (tasks < 0 || tasks > 64) tasks = 0;
    for (int k = 0; k < tasks; k++) r.tasks[r.task_count++] = m.w(G_TASKS + (u32)k * 16);

    // ---- the phase ----
    u32 phase = 0;
    bool frontend = m.i(G_IN_FRONTEND) != 0 || m.i(G_LEVEL_LOADED) == 0;
    if (frontend) phase |= RTA_GS_PH_FRONTEND;
    char pending[8];
    m.str(G_PENDING_LEVEL, pending, sizeof pending);
    if (pending[0] || m.sb(G_LOADSCREEN) || m.i(G_WARMUP_FRAMES) || !m.b(G_WORLD_PIECES_DRAWN)) phase |= RTA_GS_PH_LOADING;
    if (m.i(G_PAUSED)) phase |= RTA_GS_PH_PAUSED;
    if (m.b(G_PAUSE_MENU_OPEN) || has_task(r, FN_PAUSE_MENU)) phase |= RTA_GS_PH_PAUSE_MENU;
    if (m.b(G_LOCAL_MENU_OPEN) || m.i(G_SHOP_OPEN) || has_task(r, FN_INVENTORY) || has_task(r, FN_SHOP) || (m.i(G_MENU_OPEN_FLAG) && !(phase & RTA_GS_PH_PAUSE_MENU)))
        phase |= RTA_GS_PH_MENU;
    if (m.sb(G_CUTSCENE_ACTIVE)) phase |= RTA_GS_PH_CUTSCENE;
    if (m.w(G_DIALOG_DATA) || m.b(G_HELP_OPEN)) phase |= RTA_GS_PH_DIALOGUE;
    if (has_task(r, FN_JUMP_GATE) || has_task(r, FN_MISSION_RUN) || has_task(r, FN_MISSION_DRAW)) phase |= RTA_GS_PH_GATE_MENU;
    if (m.i(G_HUD_FADE) > 0x40) phase |= RTA_GS_PH_FADE;
    u32 camera = m.w(G_LOCAL_CAMERA);
    if (m.ok(camera, 0x70) && m.i(camera + 0x34) != 1) phase |= RTA_GS_PH_CAMERA_HELD;
    s.hud_hidden = (m.i(G_MENU_OPEN_FLAG) || m.sb(G_HUD_SUPPRESSED) || m.i(G_SHOP_OPEN) || (phase & RTA_GS_PH_CAMERA_HELD)) ? 1 : 0;

    // ---- the camera ----
    r.host_camera = false;
    if (r.have_host_view) {
        const rta_gs_view& h = r.host_view;
        float len = h.forward[0] * h.forward[0] + h.forward[1] * h.forward[1] + h.forward[2] * h.forward[2];
        if (len > 0.25f) {
            s.view = h;
            r.host_camera = true;
        } else {
            // no camera in it (the overhead view is the game's own camera, untouched): which view it is from the host, the camera from memory
            game_view(m, s.view);
            s.view.mode = h.mode;
            s.view.shown = h.shown;
            s.view.blend = h.blend;
            s.view.fallback = h.fallback;
            s.view.hide_player = h.hide_player;
            memcpy(s.view.fallback_why, h.fallback_why, sizeof s.view.fallback_why);
        }
    } else {
        game_view(m, s.view);
    }

    // ---- a new level, or time went back: nothing to compare with ----
    if (strcmp(r.level_seen, s.level) || s.sim_tick < r.tick_seen || (phase & (RTA_GS_PH_FRONTEND | RTA_GS_PH_LOADING))) {
        r.baseline = false;
        for (Track& t : r.track) t = Track();
        copy_text(r.level_seen, sizeof r.level_seen, s.level);
    }
    r.tick_seen = s.sim_tick;

    // ---- players ----
    s.online = m.sb(G_NETWORK_MODE) != 0;
    bool level = !frontend && has_task(r, FN_HUD_RUN);
    int count = level ? m.i(G_NUM_PLAYERS) : 0;
    if (count < 0 || count > RTA_GS_PLAYERS) count = 0;
    s.player_count = count;
    bool any_object = false, any_local_alive = false, any_local = false;
    for (int slot = 0; slot < RTA_GS_PLAYERS; slot++) {
        read_player(r, slot);
        const rta_gs_player& p = s.player[slot];
        if (!p.present) continue;
        if (p.object) any_object = true;
        if (p.local) { any_local = true; if (s.local_slot < 0) s.local_slot = slot; if (p.alive) any_local_alive = true; }
        if (p.local && m.b(party8_at(G_NOTICE_OPEN) + (u32)slot)) phase |= RTA_GS_PH_DIALOGUE;
    }
    if (level && any_object) phase |= RTA_GS_PH_LEVEL;
    if ((phase & RTA_GS_PH_LEVEL) && any_local && !any_local_alive) phase |= RTA_GS_PH_DEAD;
    if (has_task(r, FN_DEATH)) phase |= RTA_GS_PH_DEAD;
    s.phase = phase;

    if (phase & RTA_GS_PH_LEVEL) {
        if (!s.level_title[0] || !r.baseline) {
            // a readable title: the text table by the level's name, shortened from the end until something is found (save_levelDisplayName 0x22233c)
            char key[16];
            copy_text(key, sizeof key, s.level);
            s.level_title[0] = 0;
            for (size_t n = strlen(key); n >= 1; n--) {
                key[n] = 0;
                if (m.text_to(key, s.level_title, sizeof s.level_title)) break;
            }
        }
        read_creatures(r);
        // a player's target needs the creatures' numbers, which are given while the creatures are read
        for (int slot = 0; slot < RTA_GS_PLAYERS; slot++) {
            rta_gs_player& p = s.player[slot];
            if (p.present && p.object && (p.action_state == 0 || p.action_state == 1) && !p.target_uid) {
                u32 target = m.handle(p.object + 0x234);
                if (target) if (Track* tr = find_track(r, target)) p.target_uid = tr->uid;
            }
        }
        read_prompt(r);
        // the game's own one-line message
        int frames = m.sh(G_HUD_MESSAGE_FRAMES);
        if (frames > 0 && (!m.sb(G_HUD_SUPPRESSED) || m.sb(G_HUD_MESSAGE_FRAMES + 2))) {
            m.wide(G_HUD_MESSAGE, s.message, sizeof s.message);
            s.message_frames = s.message[0] ? frames : 0;
        }
        if (m.sb(G_COMPASS_ON)) {
            s.compass_on = 1;
            for (int k = 0; k < 3; k++) s.compass_target[k] = m.f(G_COMPASS_TARGET + (u32)k * 4);
        }
        r.baseline = true;
    } else {
        s.level_title[0] = 0;
        r.baseline = false;
    }

    // ---- online ----
    if (s.online) {
        s.net_stall_frames = m.i(G_NET_STALL);
        s.net_exit_frames = m.sh(G_NET_EXIT);
        if (m.i(G_CHECKSUM_FAILED)) s.net_notice = RTA_GS_NET_CHECKSUM;
        for (int slot = 0; slot < RTA_GS_PLAYERS && slot < m.i(G_NUM_PEERS); slot++) {
            if (m.b(party8_at(G_PEER_DESYNC) + (u32)slot * PEER_SIZE)) { s.net_notice = RTA_GS_NET_DESYNC; s.net_notice_slot = (int8_t)slot; }
        }
        if (s.net_stall_frames > 1200 || m.b(G_NET_KICKED)) s.net_notice = RTA_GS_NET_LOST;
        else if (s.net_stall_frames > 30 && s.net_notice == RTA_GS_NET_OK) s.net_notice = RTA_GS_NET_STALLED;
        if (s.net_exit_frames > 0 && s.net_notice == RTA_GS_NET_OK) s.net_notice = RTA_GS_NET_LEAVING;
        // chat: eight lines, the newest first; shown by the game while younger than 601 ticks
        for (int k = CHAT_LINES - 1; k >= 0; k--) {
            u32 a = G_CHAT_LOG + (u32)k * CHAT_LINE;
            int sender = m.sb(a + 2);
            if (sender < 0 || sender >= RTA_GS_PLAYERS || m.i(G_CHAT_AGE + (u32)k * 4) >= 601 || s.chat_count >= RTA_GS_CHAT_LINES) continue;
            char text[80], name[RTA_GS_TEXT];
            m.str(a + 3, text, sizeof text);
            m.str(party8_at(G_PLAYERS) + (u32)sender * PLAYER_SIZE, name, sizeof name);
            if (!text[0]) continue;
            snprintf(s.chat[s.chat_count], sizeof s.chat[0], "%s: %s", name, text);
            s.chat_slot[s.chat_count] = (int8_t)sender;
            s.chat_count++;
        }
    }
    r.cost = now_usec() - t0;
    return &s;
}

}  // extern "C"
