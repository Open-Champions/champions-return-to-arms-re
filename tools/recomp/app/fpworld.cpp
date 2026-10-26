// fpworld.cpp - see fpworld.h.  Compiled with the runtime's flags.
//
// How a switch reaches the renderer: like the widescreen factor of gfx_rt.cpp, as NOP codes
// in the VIF1 stream (NUM 0xB0: sixteen bits of a payload; NUM 0xB1: a command that takes
// it - render/gs.h, WorldView): the view's near and far plane and the switches in front of
// the first tag of the display list a frame filled, and "draw the level's fill here" with
// the frame's view-projection in front of the frame's first level chunk.  So a frame's list
// and the way it is to be read always agree, also in a recorded stream (which has no fill:
// the meshes are not in the stream).
//
// Options (after "--" on the command line, "--opt key=value"): world=views|off|always,
// world-clip=on|off, world-persp=on|off, world-objects=on|off, world-ceilings=auto|on|off,
// world-skirts=auto|on|off, world-rims=auto|on|off, world-cells=on|off, world-sweep=on|off, world-box-xy=N (default 256),
// world-box-z=N (default 0); world-log=1; world-nocull=1 (a
// test aid: every box passes the frustum test).  Test aids also as "app world set": world.nocull on|off,
// world.box-xy N, world.box-z N, world.dump N (every chunk of the next N level walks to the output: its box
// test, cell, slot, texture header and what it put into the list).  They are read at the first frame (before that
// rt_option has nothing: until 2026-10-19 they were read at install() and none of them took).
#include "fpworld.h"
#include "fpview.h"
#include "gfx_rt.h"
#include "worldfill.h"

#include "rt.h"
#include "funcs.h"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <cmath>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace fpworld {
namespace {

const u32 G_DL_BASE = 0x44FE0C, G_DL_CURSOR = 0x44FE10, G_DL_UNITS = 0x44FDA4;
const u32 RAM_MASK = RAM_SIZE - 1;     // ramsize.h

enum { WHEN_VIEWS = 0, WHEN_OFF = 1, WHEN_ALWAYS = 2 };
std::atomic<int> g_when{WHEN_VIEWS};
std::atomic<bool> g_clip{true}, g_persp{true}, g_objects{true}, g_cells{true}, g_sweep_on{false};
enum { AUTO = 0, ON = 1, OFF = 2 };
std::atomic<int> g_ceilings{AUTO}, g_skirts{AUTO}, g_rims{AUTO};
bool g_options_read = false, g_log = false;

inline float as_float(u32 bits) { float f; memcpy(&f, &bits, 4); return f; }
inline u32 as_bits(float f) { u32 b; memcpy(&b, &f, 4); return b; }
inline u32 at(u32 address) { return address & RAM_MASK; }     // a guest address as an offset into main memory

float g_box_margin = 0, g_box_xy = 256;   // world-box-z=N, world-box-xy=N: what a level box is widened by in a view (fn_001868a4)
int g_dump = 0, g_dumping = 0;     // world.dump N: the chunks of the next N level walks to the output (a test aid)
int g_nocull = 0;       // a test aid: 1 = every box passes the frustum test (what is missing then is not culled, it is not there)
bool is_on(const char* v) { return !strcmp(v, "on") || !strcmp(v, "yes") || !strcmp(v, "1"); }
bool is_off(const char* v) { return !strcmp(v, "off") || !strcmp(v, "no") || !strcmp(v, "0"); }

void read_options() {
    if (g_options_read) return;
    g_options_read = true;
    if (const char* o = rt_option("world")) setting("world", o);
    if (const char* o = rt_option("world-clip")) setting("world.clip", o);
    if (const char* o = rt_option("world-persp")) setting("world.persp", o);
    if (const char* o = rt_option("world-objects")) setting("world.objects", o);
    if (const char* o = rt_option("world-cells")) setting("world.cells", o);
    if (const char* o = rt_option("world-sweep")) setting("world.sweep", o);
    if (const char* o = rt_option("world-ceilings")) setting("world.ceilings", o);
    if (const char* o = rt_option("world-skirts")) setting("world.skirts", o);
    if (const char* o = rt_option("world-rims")) setting("world.rims", o);
    if (const char* o = rt_option("world-log")) g_log = atoi(o) != 0;
    if (const char* o = rt_option("world-nocull")) g_nocull = atoi(o);
    if (const char* o = rt_option("world-box-z")) g_box_margin = (float)atof(o);
    if (const char* o = rt_option("world-box-xy")) g_box_xy = (float)atof(o);
}

// ---- the frame's switches, carried with its display list ---------------------------------------
// The display list is filled from low to high addresses, one of two buffers per frame; a
// frame's list is sent while the next frame fills the other buffer (gfx_rt.cpp).
struct Buffer {
    u32 base = 0, size = 0; u64 filled_at = 0; bool on = false; float near_plane = 18, far_plane = 1800; u32 switches = 0;
    // the fill: the packet of the frame's first level chunk, and what to draw in front of it
    u32 fill_lo = 0, fill_hi = 0, fill_kinds = 0, clear_colour = 0, light_level = 128;
    u32 matrix[16] = {0}, eye[3] = {0, 0, 0};
    bool fill_said = false;
};
Buffer g_buffers[2];
int g_fill = 0;
u64 g_frames = 0, g_said = ~0ull;
void (*g_prev_frame_hook)(Ctx*, int) = nullptr;
void (*g_prev_dma_tag)(u32, std::vector<u32>&) = nullptr;

// the pass that is being drawn, or was last
struct Pass { bool active = false; float eye[3] = {0, 0, 0}; u64 frame = 0; } g_pass;
u64 g_active_passes = 0, g_cells_tested = 0, g_cells_widened = 0, g_fill_notes = 0;
bool g_in_object_walk = false, g_in_world_draw = false;
u64 g_boxes_widened = 0;
float g_player_xy[2] = {0, 0};      // the local player's feet in the pass (the decoder-slot guard)

void frame_hook(Ctx* c, int phase) {
    if (g_prev_frame_hook) g_prev_frame_hook(c, phase);
    if (phase != 1) return;
    read_options();
    g_frames++;
    u32 base = W(G_DL_BASE) & RAM_MASK;
    int slot = g_buffers[0].base == base ? 0 : g_buffers[1].base == base ? 1 : !g_buffers[0].base ? 0 : !g_buffers[1].base ? 1
             : g_buffers[0].filled_at < g_buffers[1].filled_at ? 0 : 1;
    Buffer& b = g_buffers[slot];
    b.base = base;
    b.size = W(G_DL_UNITS) * 8;
    b.filled_at = g_frames;
    b.on = false;
    b.switches = 0;
    b.fill_lo = b.fill_hi = b.fill_kinds = 0;
    b.fill_said = false;
    g_fill = slot;
    g_said = ~0ull;                         // said again with every frame (a recording may start anywhere)
    g_pass.active = false;
    if (g_when.load() == WHEN_ALWAYS) {     // the game's own camera: its near and far plane
        b.on = true; b.near_plane = 18.0f; b.far_plane = 1800.0f;
        b.switches = 1u | (g_persp.load() ? 2u : 0u) | (g_clip.load() ? 4u : 0u);
    }
}

void put_words(std::vector<u32>& stream, const u32* words, size_t count, u32 command) {
    for (size_t k = 0; k < count; k++) {
        stream.push_back(0x00B00000u | (words[k] >> 16));
        stream.push_back(0x00B00000u | (words[k] & 0xFFFF));
    }
    stream.push_back(0x00B10000u | command);
}

void dma_tag(u32 tag_address, std::vector<u32>& stream) {
    if (g_prev_dma_tag) g_prev_dma_tag(tag_address, stream);
    u32 a = tag_address & RAM_MASK;
    for (Buffer& b : g_buffers) {
        if (!b.base || a < b.base || a - b.base >= b.size) continue;
        if (g_said != b.filled_at) {
            g_said = b.filled_at;
            const u32 words[2] = {as_bits(b.near_plane), as_bits(b.far_plane)};
            put_words(stream, words, 2, 0x100u | (b.on ? b.switches : 0));
        }
        if (b.fill_kinds && !b.fill_said && a >= b.fill_lo && a < b.fill_hi) {
            b.fill_said = true;
            u32 words[21];
            memcpy(words, b.matrix, 64);
            words[16] = b.clear_colour; words[17] = b.light_level;
            memcpy(&words[18], b.eye, 12);
            put_words(stream, words, 21, 0x200u | b.fill_kinds);
            g_fill_notes++;
        }
        return;
    }
}

void sweep(fpview::View& v);      // the second stream focus (below, with the shelf)

// fpview's call-out: the frame's camera is made, the game has not built its projection yet
void on_view(fpview::View& v, Ctx*, void*) {
    read_options();
    if (g_when.load() == WHEN_OFF) return;
    Buffer& b = g_buffers[g_fill];
    b.on = true;
    b.near_plane = v.near_plane;
    b.far_plane = v.far_plane;
    b.switches = 1u | (g_persp.load() ? 2u : 0u) | (g_clip.load() ? 4u : 0u);
    g_pass.active = true;
    g_pass.eye[0] = v.eye.x; g_pass.eye[1] = v.eye.y; g_pass.eye[2] = v.eye.z;
    g_pass.frame = v.frame;
    g_player_xy[0] = v.player_pos.x; g_player_xy[1] = v.player_pos.y;
    g_active_passes++;
    if (g_cells.load() && g_sweep_on.load()) sweep(v);
}

// ---- the object walk -------------------------------------------------------------------------------
// world_drawObjects walks the object grid by halving a rectangle of cells (256 units each) and
// tests every rectangle as a box from the camera's height to 840 below it: under the camera
// overhead everything that can be seen lies below the camera.  A camera in the world sees
// objects above its own height - on a ledge, up a stair, a creature's upper half when the
// view looks up - and a view that looks up by more than half its field of view has its whole
// frustum above that box: no cell passes and every object of the level is gone.  For the
// length of the walk the cell boxes are taken from 840 below the eye to OBJECTS_ABOVE over it.
// (An object's own box, tested next, is its own: position, draw radius, draw height.)
const u32 G_CAMERA_POS = 0x44F038;
const float OBJECTS_BELOW = 840.0f, OBJECTS_ABOVE = 600.0f;

// ---- the decoder slots and the far objects ------------------------------------------------------------
// Drawing an animated object decodes its tracks into the animation decoder's slots (165 of them at
// 0x6f6180, 0xf1c bytes, docs/spec/animation.md 2.3).  animcache_alloc 0x16e388 hands out the least
// recently used slot and never one whose owner track carries root motion or yaw (flags 0x0800 / 0x4000):
// with all 165 so held it loops for ever.  Overhead, a level full of creatures holds about a hundred;
// a view along the ground draws creatures out to 1,800 units that the overhead camera never shows (they
// stand still beyond 600 units, A8) and each of them pins one or two more: `dismedal` reached 143 and
// then, at one heading, all of them - the game hung inside the draw pass (Ran, 2026-10-19; one walk
// took the count from 76 to 161).  While a view's object walk runs, every box it tests first counts
// the slots held: from SLOTS_SOFT on, a box farther than GUARD_RADIUS from the player is outside the
// frustum (the overhead camera would not have drawn it either); from SLOTS_HARD on no box passes.  Drawing only: what is not
// drawn is not decoded, and nothing the simulation computes changes.
const u32 ANIM_SLOTS = 0x6F6180, ANIM_SLOT_SIZE = 0xF1C, ANIM_SLOT_COUNT = 165;
const u32 SLOTS_SOFT = 140, SLOTS_HARD = 158;
const float GUARD_RADIUS = 650.0f;
u32 g_slots_held = 0, g_slots_most = 0;
u64 g_guard_walks = 0, g_guard_rejected = 0, g_guard_hard = 0;
bool g_guard_on = false, g_guard_counted = false;
u32 slots_held() {
    u32 held = 0;
    for (u32 k = 0; k < ANIM_SLOT_COUNT; k++) {
        u32 owner = W(ANIM_SLOTS + k * ANIM_SLOT_SIZE + 0x14) & RAM_MASK;
        if (owner && owner < RAM_MASK - 0x20 && (g_ram[owner + 0x1c] | g_ram[owner + 0x1d] << 8) & 0x4800) held++;
    }
    return held;
}

void object_walk(void* ctx, void (*original)(void*)) {
    bool mine = g_pass.active && g_objects.load();
    if (mine) g_in_object_walk = true;
    g_guard_on = g_pass.active;           // every box of the walk asks how many slots are held now
    g_guard_counted = false;
    if (g_pass.active) {
        g_slots_held = slots_held();
        if (g_slots_held > g_slots_most) g_slots_most = g_slots_held;
    }
    original(ctx);
    if (g_log && g_pass.active) {
        u32 after = slots_held();
        if (after >= 100 || g_slots_held >= 100) fprintf(stderr, "world: object walk, decoder slots held %u before, %u after%s\n", g_slots_held, after, g_guard_counted ? " (guarded)" : "");
    }
    g_guard_on = false;
    g_in_object_walk = false;
}

// ---- figures of a pass --------------------------------------------------------------------------------
struct Counts { u32 chunks = 0, no_cell = 0, cell_loading = 0, tests = 0, shelved = 0, unprepared_shelved = 0; } g_counts, g_last;

// ---- texture cells kept on the shelf (A4) -------------------------------------------------------------
// The game keeps the level's textures of nine cells of 720 x 720 units (the 3 x 3 round g_cameraFocus,
// worldtex_stream 0x17d830) and draws no chunk of any other cell (world_drawChunk 0x1887b8: the cell's
// slot byte at 0x41c1b8 + cell is -1).  A view along the ground sees 1,800 units: 100 to 300 chunks a
// frame of a big level have no cell.  A texture of a resident cell, once the game's texture thread has
// prepared it (header +0x14: its upload chain - NEXT tags page to page, a RET at the end - in the 5 MB
// page pool), is copied here to the runtime's shelf (rt_shelf: host memory at guest addresses the console
// does not have), header and chain, the chain's tags pointed at the copy.  A chunk of a cell that is not
// resident whose texture is on the shelf is then drawn by the game's own world_drawChunk with, for the
// length of that call, the cell's slot byte and a tenth slot pointer (0x425e1c) showing the shelf's copy
// of the cell's header table; both words are put back when it returns.  The game uploads the texture from
// the shelf like any other (gfx_dmaHandler patches the copy's destination words, its texture cache marks
// the copy's header resident or not).  Only in a view's pass; the run pass and the overhead view never
// see the shelf; nothing the simulation reads is written.  A new level empties it.
const u32 G_CELL_SLOT = 0x41C1B8, G_SLOT_BASE = 0x425DF8, G_SLOT_CELL = 0x7D2FD0, SHELF_SLOT = 9, G_WORLD_PTR = 0x44FDC8;
const u32 SHELF_BYTES = 120u << 20;        // below 0x10000000, where the hardware registers start
struct ShelfCell { u32 guest = 0, count = 0, prepared = 0; std::vector<u8> have; std::vector<u32> asked; };
std::unordered_map<int, ShelfCell> g_shelf;
u8* g_shelf_mem = nullptr;
u32 g_shelf_used = 0, g_shelf_world = 0, g_shelf_textures = 0;
char g_shelf_level[16] = {0};
u64 g_shelf_refused = 0, g_shelf_full = 0, g_shelf_drawn = 0;

u32 shelf_alloc(u32 bytes) {
    bytes = (bytes + 15) & ~15u;
    if (!g_shelf_mem) g_shelf_mem = rt_shelf(SHELF_BYTES);
    if (!g_shelf_mem || g_shelf_used + bytes > SHELF_BYTES) { g_shelf_full++; return 0; }
    u32 at_ = g_shelf_used;
    g_shelf_used += bytes;
    return at_;
}
inline u8* shelf_ptr(u32 offset) { return g_shelf_mem + offset; }

// the upload chain of a prepared texture onto the shelf; the guest address of the copy, or 0
u32 shelve_chain(u32 start, u32 qwords) {
    struct Seg { u32 from, bytes, id; };
    std::vector<Seg> segs;
    u32 a = start & RAM_MASK, total = 0;
    for (int n = 0; n < 4096; n++) {
        if (a > RAM_MASK - 16) return 0;
        u64 tag; memcpy(&tag, g_ram + a, 8);
        u32 id = (u32)(tag >> 28) & 7, q = (u32)tag & 0xFFFF;
        if (id != 1 && id != 2 && id != 6) return 0;            // cnt, next, ret: nothing else was seen
        u32 bytes = 16 + q * 16;
        if (a + bytes > RAM_MASK) return 0;
        segs.push_back({a, bytes, id});
        total += bytes;
        if (total > (qwords + 64) * 16 + 4096 * 8) return 0;       // longer than the header says
        if (id == 6) break;
        a = id == 2 ? ((u32)(tag >> 32) & RAM_MASK) : a + bytes;
        if (n == 4095) return 0;
    }
    u32 off = shelf_alloc(std::max(total, 0x500u));
    if (!off) return 0;
    u32 put = off;
    for (size_t k = 0; k < segs.size(); k++) {
        u8* to = shelf_ptr(put);
        memcpy(to, g_ram + segs[k].from, segs[k].bytes);
        put += segs[k].bytes;
        if (segs[k].id == 2) {                                   // the next segment follows this one here
            u32 next = RT_SHELF_BASE + put;
            memcpy(to + 4, &next, 4);
        }
    }
    return RT_SHELF_BASE + off;
}

// A texture is prepared only when a chunk that uses it is drawn: what lies behind the view never is, and
// when the view turns after its cell has gone, nothing of it is on the shelf.  So the textures of the
// resident cells that are neither prepared nor asked for are put into the texture thread's queue (64
// entries {header, cell} at 0x7d3340, write index 0x7d3540, read index 0x7d3544; world_drawChunk adds a
// texture to it the same way, 0x17fc78), a few at a time and only while the queue is nearly empty, so the
// game's own requests come first.  The thread prepares them into its page pool; the next pass shelves them.
const u32 G_TEXQ = 0x7D3340, G_TEXQ_WRITE = 0x7D3540, G_TEXQ_READ = 0x7D3544;
const u32 ASK_PER_PASS = 4, ASK_WHEN_BELOW = 8, ASK_AGAIN = 120;
u64 g_shelf_asked = 0;
void ask_for_the_rest() {
    u32 asked = 0;
    for (u32 slot = 0; slot < 9 && asked < ASK_PER_PASS; slot++) {
        u32 base = W(G_SLOT_BASE + slot * 4) & RAM_MASK;
        s32 cell = (s32)W(G_SLOT_CELL + slot * 4);
        if (!base || cell <= 0 || cell >= 10000 || (s8)g_ram[G_CELL_SLOT + cell] != (s8)slot) continue;
        auto it = g_shelf.find(cell);
        if (it == g_shelf.end() || !it->second.guest || it->second.count != W(base)) continue;
        ShelfCell& sc = it->second;
        if (sc.prepared == sc.count) continue;
        for (u32 k = 0; k < sc.count && asked < ASK_PER_PASS; k++) {
            if (sc.have[k] || (sc.asked[k] && g_frames - sc.asked[k] < ASK_AGAIN)) continue;
            u32 h = base + 0x40 + k * 0x40;
            if (W(h + 0x14)) continue;                           // prepared: shelved at the next pass
            u32 write = W(G_TEXQ_WRITE) & 63, read = W(G_TEXQ_READ) & 63;
            if (((write - read) & 63) >= ASK_WHEN_BELOW) return;
            W(G_TEXQ + write * 8) = h;
            W(G_TEXQ + write * 8 + 4) = (u32)cell;
            W(G_TEXQ_WRITE) = (write + 1) & 63;
            sc.asked[k] = (u32)g_frames | 1;
            asked++;
            g_shelf_asked++;
        }
    }
}

// every view pass, before the level is drawn: what the nine resident cells have prepared that is not
// on the shelf yet
void shelve_cells(u32 world) {
    char name[16] = {0};
    memcpy(name, g_ram + 0x41B721, 15);         // g_levelName
    if (world != g_shelf_world || strcmp(name, g_shelf_level)) {
        g_shelf.clear();
        g_shelf_used = 0; g_shelf_textures = 0;
        g_shelf_world = world; memcpy(g_shelf_level, name, 16);
    }
    for (u32 slot = 0; slot < 9; slot++) {
        u32 base = W(G_SLOT_BASE + slot * 4) & RAM_MASK;
        s32 cell = (s32)W(G_SLOT_CELL + slot * 4);
        if (!base || cell <= 0 || cell >= 10000 || (s8)g_ram[G_CELL_SLOT + cell] != (s8)slot) continue;
        u32 count = W(base);
        if (count == 0 || count > 2000 || base + (count + 1) * 0x40 > RAM_MASK) continue;
        ShelfCell& sc = g_shelf[cell];
        if (!sc.guest) {
            u32 off = shelf_alloc((count + 1) * 0x40);
            if (!off) continue;
            memcpy(shelf_ptr(off), g_ram + base, (count + 1) * 0x40);
            for (u32 k = 0; k < count; k++) {                    // as the loader leaves a header: not in the page pool, not in the GS
                u8* h = shelf_ptr(off + 0x40 + k * 0x40);
                memset(h + 0x14, 0, 0x2C);
                memset(h + 0x1C, 0xFF, 4);
            }
            sc.guest = RT_SHELF_BASE + off;
            sc.count = count;
            sc.have.assign(count, 0);
            sc.asked.assign(count, 0);
        }
        if (sc.count != count) continue;
        for (u32 k = 0; k < count; k++) {
            if (sc.have[k]) continue;
            u32 h = base + 0x40 + k * 0x40;
            u32 chain = W(h + 0x14);
            if (!chain) continue;
            u32 qwords = g_ram[h + 6] | g_ram[h + 7] << 8;
            u32 copy = shelve_chain(chain, qwords);
            if (!copy) { if (!g_shelf_full) g_shelf_refused++; sc.have[k] = 2; sc.prepared++; continue; }
            memcpy(shelf_ptr(sc.guest - RT_SHELF_BASE + 0x40 + k * 0x40 + 0x14), &copy, 4);
            sc.have[k] = 1;
            sc.prepared++;
            g_shelf_textures++;
        }
    }
    ask_for_the_rest();
}

// ---- a second stream focus (world.sweep, off by default: a turn right after a sweep showed holes near
// the feet, docs/issues/native-first-person-world.md 8.3) ------------------------------------------------
// The shelf keeps what was once resident; the cells far ahead of a view along the ground never are (the
// nine round a point 300 ahead of the eye: fpview, view-stream-ahead).  While the view is still - the
// look turned by less than SWEEP_TURN degrees and the player moved less than SWEEP_MOVE units over the last
// SWEEP_STILL frames - the nine cells round the near point are resident, every texture of the cells round
// the eye and round the near point is on the shelf (ask_for_the_rest has the ones nothing drew prepared),
// and the last pass still had SWEEP_WANT chunks or more without a cell, the stream is pointed
// SWEEP_AHEAD units ahead instead.  It goes back to the near point when the far cells have been resident
// for SWEEP_DWELL frames (they are drawn meanwhile, so the game's texture thread prepares their textures
// and the shelf takes them), after SWEEP_LIMIT frames, or as soon as the view turns or the player moves.
// What the player stands on stays drawn throughout: from the shelf while its cell is away.  Drawing only:
// which cells are loaded is per machine and read by no simulation code (docs/formats/world.md).
const int SWEEP_STILL = 45, SWEEP_DWELL = 40, SWEEP_LIMIT = 300, SWEEP_REST = 60;
const u32 SWEEP_WANT = 16;
const float SWEEP_AHEAD = 1300.0f, SWEEP_TURN = 12.0f, SWEEP_MOVE = 60.0f;
struct Sweep {
    bool far_ = false;
    u64 since = 0, settled = 0;
    fpview::Vec3 focus{}, eye_ref{};
    float yaw_ref = 0;
    u64 still_since = 0;
    u64 sweeps = 0, cut_short = 0;
} g_sw;

float cell_size() {
    u32 world = W(G_WORLD_PTR) & RAM_MASK;
    float size = world ? as_float(W(world + 0x68)) : 0;
    return size > 1 ? size : 960.0f;
}
int cell_of(float x, float y) {
    float size = cell_size();
    return ((int)std::floor(y / size) + 50) * 100 + (int)std::floor(x / size) + 50;
}
// the level has texture data for this cell (its entry in the world's cell table is not the file's placeholder)
bool cell_exists(int cell) {
    u32 world = W(G_WORLD_PTR) & RAM_MASK;
    if (!world) return false;
    s32 lo = (s32)W(world + 0x58), hi = (s32)W(world + 0x5c);
    if (cell < lo || cell > hi) return false;
    u32 table = W(world + 0x64) & RAM_MASK;
    if (!table || table + (u32)(cell - lo) * 8 + 8 > RAM_MASK) return false;
    return W(table + (cell - lo) * 8 + 4) > 0x40;
}
// the 3 x 3 cells round a point: all resident (those the level has), or all on the shelf
bool window_resident(float x, float y) {
    int c = cell_of(x, y);
    for (int dy = -1; dy <= 1; dy++)
        for (int dx = -1; dx <= 1; dx++) {
            int id = c + dy * 100 + dx;
            if (id > 0 && id < 10000 && cell_exists(id) && (s8)g_ram[G_CELL_SLOT + id] == -1) return false;
        }
    return true;
}
bool window_shelved(float x, float y) {
    int c = cell_of(x, y);
    for (int dy = -1; dy <= 1; dy++)
        for (int dx = -1; dx <= 1; dx++) {
            int id = c + dy * 100 + dx;
            if (id <= 0 || id >= 10000 || !cell_exists(id)) continue;
            auto it = g_shelf.find(id);
            if (it == g_shelf.end() || !it->second.guest || it->second.prepared < it->second.count) return false;
        }
    return true;
}

void sweep(fpview::View& v) {
    u64 now = g_frames;
    float yaw = std::atan2(v.forward.y, v.forward.x) * 57.29578f;
    float turned = std::fabs(yaw - g_sw.yaw_ref); if (turned > 180) turned = 360 - turned;
    float moved = std::hypot(v.eye.x - g_sw.eye_ref.x, v.eye.y - g_sw.eye_ref.y);
    if (turned > SWEEP_TURN || moved > SWEEP_MOVE) {             // the view is not still: measured again from here
        g_sw.yaw_ref = yaw; g_sw.eye_ref = v.eye; g_sw.still_since = now;
        if (g_sw.far_) { g_sw.far_ = false; g_sw.since = now; g_sw.cut_short++; }
    }
    if (!g_sw.far_) {
        if (now - g_sw.since < (u64)SWEEP_REST || now - g_sw.still_since < (u64)SWEEP_STILL || g_last.no_cell < SWEEP_WANT) return;
        if (!window_resident(v.stream_focus.x, v.stream_focus.y) || !window_shelved(v.eye.x, v.eye.y) ||
            !window_shelved(v.stream_focus.x, v.stream_focus.y)) return;
        float fl = std::hypot(v.forward.x, v.forward.y);
        if (fl < 0.3f) return;
        fpview::Vec3 far_point{v.eye.x + v.forward.x / fl * SWEEP_AHEAD, v.eye.y + v.forward.y / fl * SWEEP_AHEAD, v.eye.z};
        if (cell_of(far_point.x, far_point.y) == cell_of(v.stream_focus.x, v.stream_focus.y)) return;
        g_sw.far_ = true; g_sw.since = now; g_sw.settled = 0; g_sw.focus = far_point; g_sw.sweeps++;
    }
    if (g_sw.far_) {
        if (window_resident(g_sw.focus.x, g_sw.focus.y)) { if (!g_sw.settled) g_sw.settled = now; }
        if ((g_sw.settled && now - g_sw.settled >= (u64)SWEEP_DWELL) || now - g_sw.since >= (u64)SWEEP_LIMIT) {
            g_sw.far_ = false; g_sw.since = now;
            return;
        }
        v.stream_focus = g_sw.focus;
    }
}

// the shelf's header of a chunk of a cell that is not resident, prepared; 0 = none
u32 shelved_header(s16 cell, u32 offset, u32& table) {
    auto it = g_shelf.find(cell);
    if (it == g_shelf.end() || !it->second.guest || offset < 0x40 || (offset & 0x3F)) return 0;
    u32 k = offset / 0x40 - 1;
    if (k >= it->second.count || it->second.have[k] != 1) return 0;
    table = it->second.guest;
    return table + offset;
}

// ---- the level's fill -----------------------------------------------------------------------------------
// Built when a level is first drawn (the .world is fixed up in main memory by then), from the
// structure at g_world; what is built depends on the level:
//   ceilings  auto = the level clears to black, has no sky dome, and is walled: the cells of wall
//             that would carry a ceiling make up a tenth of the walked floor's area or more
//             (dungeon 0.26, cave 0.23, hall 0.34, arena 0.17, scrap-yard 0.13; a night swamp 0.06
//             and a night forest 0.01 clear to black too and get none);
//   skirts    auto = the level has no sky dome (a dome is a bowl of cloud under a floating level,
//             or a painted horizon: the rim is the design there).
//   rims      auto = the level HAS a sky dome: floating ground, where a floor's edge stands over nothing
//             and the eye looks down past it (storm2, torment2, fay2, pvpfire2: native-first-person-world.md
//             8.8, cause 4); a surface falls away under the edge, a background like the skirt.
const u32 G_WORLD = 0x44FDC8, G_LEVEL_NAME = 0x41B721, G_BACKGROUND = 0x506044, G_DOME_LUMP = 0x86AF54, G_LIGHT_LEVEL = 0x5D347C;
const u32 G_VIEW_PROJ = 0x44F140;
struct LevelFill {
    u32 world = 0;
    char name[16] = {0};
    u8 header[0x84] = {0};                  // the .world's header as it lay there: another level at the same address is another level
    int ceilings = -1, skirts = -1, rims = -1;      // the settings it was built with
    u32 kinds = 0;                          // what there is to draw: bit 0 ceilings, bit 1 skirts, bit 2 rims
    std::shared_ptr<const render::FillLevel> level;
    std::string why;
} g_level;
u64 g_fill_builds = 0;

void level_fill(u32 world) {
    char name[16] = {0};
    memcpy(name, g_ram + at(G_LEVEL_NAME), 15);
    int ceilings = g_ceilings.load(), skirts = g_skirts.load(), rims = g_rims.load();
    if (world == g_level.world && !strcmp(name, g_level.name) && ceilings == g_level.ceilings && skirts == g_level.skirts && rims == g_level.rims &&
        !memcmp(g_level.header, g_ram + at(world), sizeof g_level.header)) return;
    memcpy(g_level.header, g_ram + at(world), sizeof g_level.header);
    g_level.world = world; memcpy(g_level.name, name, 16); g_level.ceilings = ceilings; g_level.skirts = skirts; g_level.rims = rims;
    g_level.kinds = 0; g_level.level.reset(); g_level.why.clear();
    const bool dome = W(G_DOME_LUMP) != 0, black = (W(G_BACKGROUND) & 0xFFFFFF) == 0;
    render::FillOptions opt;
    opt.skirts = skirts == ON || (skirts == AUTO && !dome);
    opt.ceilings = ceilings == ON || (ceilings == AUTO && !dome && black);
    opt.rims = rims == ON || (rims == AUTO && dome);
    if (opt.ceilings || opt.skirts || opt.rims) {
        std::shared_ptr<const render::FillLevel> level = render::build_fill(g_ram, RAM_SIZE, world, true, name, opt);
        g_fill_builds++;
        if (level) {
            bool walled = level->floor_area > 0 && (double)level->walls * 256.0 >= 0.10 * level->floor_area;
            bool keep_ceiling = opt.ceilings && (ceilings == ON || walled);
            if (opt.ceilings && !keep_ceiling) {            // not an interior after all: built again without
                opt.ceilings = false;
                level = opt.skirts || opt.rims ? render::build_fill(g_ram, RAM_SIZE, world, true, name, opt) : nullptr;
            }
            if (level) {
                g_level.kinds = (level->ceiling_area > 0 ? 1u : 0u) | (level->skirt_area > 0 ? 2u : 0u) | (level->rim_area > 0 ? 4u : 0u);
                g_level.level = level;
            }
        } else g_level.why = "the level's terrain was not read";
    }
    render::publish_fill(g_level.level);
    if (g_log) {
        const render::FillLevel* l = g_level.level.get();
        fprintf(stderr, "world: level %s: sky dome %s, clears to %06x; fill: ceiling %.0f, skirt %.0f, rim %.0f square units, %zu triangles, walls %d cells (lid %.0f over the floor), floor %.0f, %.1f ms %s\n",
                name, dome ? "yes" : "no", W(G_BACKGROUND) & 0xFFFFFF, l ? l->ceiling_area : 0.0, l ? l->skirt_area : 0.0, l ? l->rim_area : 0.0, l ? l->vertices.size() / 3 : (size_t)0,
                l ? l->walls : 0, l ? l->lid_median : 0.0f, l ? l->floor_area : 0.0, l ? l->build_ms : 0.0, g_level.why.c_str());
    }
}

std::mutex g_text_lock;
std::string g_settings_text, g_info_text;

}  // namespace

bool setting(const char* key, const char* value) {
    std::string k = key, v = value;
    if (k == "world") {
        if (v == "views") g_when = WHEN_VIEWS; else if (v == "always") g_when = WHEN_ALWAYS; else if (is_off(value)) g_when = WHEN_OFF; else return false;
        return true;
    }
    if (k == "world.ceilings" || k == "world.skirts" || k == "world.rims") {
        int mode = v == "auto" ? AUTO : is_on(value) ? ON : is_off(value) ? OFF : -1;
        if (mode < 0) return false;
        (k == "world.ceilings" ? g_ceilings : k == "world.skirts" ? g_skirts : g_rims) = mode;
        return true;
    }
    if (k == "world.dump") { g_dump = atoi(value); return true; }
    if (k == "world.nocull") { g_nocull = is_on(value) ? 1 : 0; return true; }      // test aids, not in the settings file
    if (k == "world.box-xy") { g_box_xy = (float)atof(value); return true; }
    if (k == "world.box-z") { g_box_margin = (float)atof(value); return true; }
    std::atomic<bool>* part = k == "world.clip" ? &g_clip : k == "world.persp" ? &g_persp : k == "world.objects" ? &g_objects
                            : k == "world.cells" ? &g_cells : k == "world.sweep" ? &g_sweep_on : nullptr;
    if (!part) return false;
    if (is_on(value)) *part = true; else if (is_off(value)) *part = false; else return false;
    return true;
}

const char* settings_text() {
    std::lock_guard<std::mutex> hold(g_text_lock);
    int when = g_when.load();
    g_settings_text = std::string("world = ") + (when == WHEN_VIEWS ? "views" : when == WHEN_OFF ? "off" : "always") +
        "        # the world for a camera inside it: views (while a view other than overhead is drawn), off, always\n";
    g_settings_text += std::string("world.clip = ") + (g_clip.load() ? "on" : "off") + "\nworld.persp = " + (g_persp.load() ? "on" : "off") +
        "\nworld.objects = " + (g_objects.load() ? "on" : "off") + "\nworld.cells = " + (g_cells.load() ? "on" : "off") +
        "\nworld.sweep = " + (g_sweep_on.load() ? "on" : "off") + "\n";
    static const char* const modes[3] = {"auto", "on", "off"};
    g_settings_text += std::string("world.ceilings = ") + modes[g_ceilings.load()] + "\nworld.skirts = " + modes[g_skirts.load()] +
        "\nworld.rims = " + modes[g_rims.load()] + "\n";
    return g_settings_text.c_str();
}

const char* info() {
    std::lock_guard<std::mutex> hold(g_text_lock);
    char line[1600];
    const Buffer& b = g_buffers[g_fill];
    snprintf(line, sizeof line, "world: %s; this pass %s (near %.1f far %.0f, switches %x); passes with it %llu; object cells widened %llu; "
             "last pass: %u chunks drawn, %u not (texture cell not loaded), %u not (its texture still loading), %u box tests; list %u of %u units",
             g_when.load() == WHEN_VIEWS ? "views" : g_when.load() == WHEN_OFF ? "off" : "always", b.on ? "on" : "off", b.near_plane, b.far_plane, b.switches,
             (unsigned long long)g_active_passes, (unsigned long long)g_cells_widened, g_last.chunks, g_last.no_cell, g_last.cell_loading, g_last.tests,
             ((W(G_DL_CURSOR) & RAM_MASK) - (W(G_DL_BASE) & RAM_MASK)) >> 3, W(G_DL_UNITS));
    {
        const render::FillLevel* l = g_level.level.get();
        char more[260];
        snprintf(more, sizeof more, "; fill of %s: ceiling %.0f, skirt %.0f, rim %.0f square units in %zu triangles (walls %d cells, lid %.0f; floor %.0f; %.1f ms), said %llu times",
                 g_level.name, l ? l->ceiling_area : 0.0, l ? l->skirt_area : 0.0, l ? l->rim_area : 0.0, l ? l->vertices.size() / 3 : (size_t)0, l ? l->walls : 0, l ? l->lid_median : 0.0f,
                 l ? l->floor_area : 0.0, l ? l->build_ms : 0.0, (unsigned long long)g_fill_notes);
        strncat(line, more, sizeof line - strlen(line) - 1);
    }
    {
        char more[360];
        snprintf(more, sizeof more, "; shelf: %u textures of %zu cells, %.1f of %u MB%s, %u chunks drawn from it last pass (%u of a resident cell; %llu in all), %llu refused; "
                 "%llu asked for; far focus %s, %llu times (%llu cut short); level boxes widened %llu",
                 g_shelf_textures, g_shelf.size(), g_shelf_used / 1048576.0, SHELF_BYTES >> 20, g_shelf_full ? " (full)" : "", g_last.shelved, g_last.unprepared_shelved,
                 (unsigned long long)g_shelf_drawn, (unsigned long long)g_shelf_refused, (unsigned long long)g_shelf_asked, g_sw.far_ ? "now" : "not now",
                 (unsigned long long)g_sw.sweeps, (unsigned long long)g_sw.cut_short, (unsigned long long)g_boxes_widened);
        strncat(line, more, sizeof line - strlen(line) - 1);
    }
    {
        char more[200];
        snprintf(more, sizeof more, "; decoder slots held %u (most %u of %u), walks guarded %llu, boxes left out %llu (%llu at the hard limit)",
                 g_slots_held, g_slots_most, ANIM_SLOT_COUNT, (unsigned long long)g_guard_walks, (unsigned long long)g_guard_rejected,
                 (unsigned long long)g_guard_hard);
        strncat(line, more, sizeof line - strlen(line) - 1);
    }
    g_info_text = line;
    return g_info_text.c_str();
}

void install() {
    // the options are read at the first frame (read_options): rt_option has nothing before rta::run
    // has parsed the command line, and install() runs before that
    g_prev_frame_hook = rt_frame_hook; rt_frame_hook = frame_hook;
    g_prev_dma_tag = rt_dma_tag; rt_dma_tag = dma_tag;
    fpview::on_view(on_view, nullptr);
    gfxrt::object_walk.run = object_walk;
}

}  // namespace fpworld

// ---- the functions the translation calls ------------------------------------------------------------
using namespace fpworld;

// frustum_testBox(box, mask): box = min x, max x, min y, max y, min z, max z; 0 = outside
static void test_box(Ctx* c);
void fn_001868a4(Ctx* c) {
    u32 ra = (u32)c->r[31], chunk = (u32)c->r[16];
    test_box(c);
    if (g_dumping && ra == 0x189CAC)
        fprintf(stderr, "world dump: test %x %s\n", chunk, c->r[2] ? "in" : "out");
}
static void test_box(Ctx* c) {
    g_counts.tests++;
    if (g_in_object_walk) {
        u32 box = (u32)c->r[4];
        float cam_z = as_float(W(G_CAMERA_POS + 8));
        // a cell box of the object walk: exactly the camera's height on top and 840 below it
        if (W(at(box) + 0x14) == as_bits(cam_z) && W(at(box) + 0x10) == as_bits(cam_z - OBJECTS_BELOW)) {
            W(at(box) + 0x14) = as_bits(cam_z + OBJECTS_ABOVE);
            g_cells_widened++;
        }
    }
    if (g_guard_on) {
        u32 box = (u32)c->r[4];
        float lo_x = as_float(W(at(box))), hi_x = as_float(W(at(box) + 4)), lo_y = as_float(W(at(box) + 8)), hi_y = as_float(W(at(box) + 12));
        float dx = g_player_xy[0] < lo_x ? lo_x - g_player_xy[0] : g_player_xy[0] > hi_x ? g_player_xy[0] - hi_x : 0;
        float dy = g_player_xy[1] < lo_y ? lo_y - g_player_xy[1] : g_player_xy[1] > hi_y ? g_player_xy[1] - hi_y : 0;
        u32 held = slots_held();
        if (held > g_slots_most) g_slots_most = held;
        if (held >= SLOTS_SOFT && !g_guard_counted) { g_guard_counted = true; g_guard_walks++; }
        if (held >= SLOTS_HARD || (held >= SLOTS_SOFT && dx * dx + dy * dy > GUARD_RADIUS * GUARD_RADIUS)) {
            if (held >= SLOTS_HARD) g_guard_hard++;
            g_guard_rejected++;
            c->r[2] = 0;
            return;
        }
    }
    if (g_nocull && g_pass.active) { c->r[2] = (u64)(s64)(s32)((u32)c->r[5] | 0x3F); return; }
    // the test world_draw makes of one chunk's own box (call 0x189ca4: the chunk in s0), for a chunk of plain
    // level geometry - the kinds that draw water, lights or emitters (flags 0xC880), which take numbers from
    // the cosmetic generator, are tested as the game tests them
    bool chunk_test = g_in_world_draw && (u32)c->r[31] == 0x189CAC && !(W(at((u32)c->r[16]) + 0x24) & 0xC880);
    if (chunk_test && (g_box_margin > 0 || g_box_xy > 0)) {
        // A chunk's box, for the length of the test, wider by g_box_xy on every side (and
        // taller by g_box_z).  Some boxes do not cover their chunk's ground: from overhead the frustum is
        // hundreds of units wide where the ground is and such a box still passes; a camera at eye height
        // has a frustum a few units wide just in front of it, and the box falls outside a side plane while
        // the ground it stands for is in the picture - a hole of a chunk's size in the ground near the
        // feet (Ran: obsidian at 324,-86, 2026-10-19: gone with every box passing (world-nocull), gone with
        // 300 more on every side, nearly gone with 120, not changed by any height).  Drawing only: the box
        // is put back when the test returns.
        u32 box = at((u32)c->r[4]);
        if (box <= RAM_MASK - 24) {
            orig_001868a4(c);                                  // as the game tests it first
            if (c->r[2] != 0) return;
            u32 saved[6];
            memcpy(saved, g_ram + box, 24);
            W(box + 0x10) = as_bits(as_float(saved[4]) - g_box_margin);
            W(box + 0x14) = as_bits(as_float(saved[5]) + g_box_margin);
            if (g_box_xy > 0) {
                W(box) = as_bits(as_float(saved[0]) - g_box_xy); W(box + 4) = as_bits(as_float(saved[1]) + g_box_xy);
                W(box + 8) = as_bits(as_float(saved[2]) - g_box_xy); W(box + 12) = as_bits(as_float(saved[3]) + g_box_xy);
            }
            orig_001868a4(c);
            memcpy(g_ram + box, saved, 24);
            if (c->r[2] != 0) g_boxes_widened++;
            return;
        }
    }
    orig_001868a4(c);
}

// world_draw(world)
void fn_00189870(Ctx* c) {
    g_counts = Counts();
    g_dumping = 0;
    if (g_dump > 0) {
        g_dump--; g_dumping = 1;
        fprintf(stderr, "world dump: pass %s eye %.0f %.0f %.0f\n", g_pass.active ? "view" : "game", g_pass.eye[0], g_pass.eye[1], g_pass.eye[2]);
    }
    u32 world = (u32)c->r[4];
    if (g_pass.active && world && world == W(G_WORLD) && g_cells.load()) shelve_cells(world);
    if (g_pass.active && world && world == W(G_WORLD) && g_ram[at(0x44F054)] != 0) {      // g_worldPiecesDrawn: the level is whole
        level_fill(world);
        Buffer& b = g_buffers[g_fill];
        b.fill_kinds = g_level.kinds;
        b.fill_lo = b.fill_hi = 0;
        memcpy(b.matrix, g_ram + G_VIEW_PROJ, 64);
        b.clear_colour = W(G_BACKGROUND);
        b.light_level = W(G_LIGHT_LEVEL);
        memcpy(b.eye, g_pass.eye, 12);
    }
    g_in_world_draw = g_pass.active;
    orig_00189870(c);
    g_in_world_draw = false;
    g_last = g_counts;
    if (g_dumping) fprintf(stderr, "world dump: end\n");
    g_dumping = 0;
}

// world_drawChunk(world, chunk, clip flag): a geometry chunk whose texture cell is not loaded, or
// whose texture is still on its way to the GS, is left out (0x1887b8)
void fn_001887b8(Ctx* c) {
    u32 chunk = (u32)c->r[5];
    u32 flags = W(at(chunk) + 0x24);
    u32 shelf_table = 0;
    s16 shelf_cell = 0;
    if (!(flags & 0xC880)) {
        s16 cell = (s16)(W(at(chunk) + 0x34) & 0xFFFF);
        if (cell > 0) {
            s8 slot = (s8)g_ram[at(G_CELL_SLOT + cell)];
            if (slot == -1 && g_pass.active && g_cells.load() && shelved_header(cell, W(at(chunk) + 0x20), shelf_table)) {
                g_counts.shelved++;
                shelf_cell = cell;
            } else if (slot == -1) g_counts.no_cell++;
            else {
                u32 header = W(at(0x425DF8 + slot * 4)) + W(at(chunk) + 0x20);
                if (header && W(at(header) + 0x14) != 0) g_counts.chunks++;
                // The cell is resident but this texture is not prepared (or no longer: the texture thread's page
                // pool holds what the last frames drew, and a view along the ground draws far more than the
                // overhead camera: 43 chunks of storm1a's pit floor stayed unprepared for 400 frames and more,
                // with the textures on the shelf, 2026-10-20).  The game leaves such a chunk out until it is.  When the shelf has the
                // texture it is drawn from there, the same way as a chunk of a cell that is not resident.
                else if (g_pass.active && g_cells.load() && shelved_header(cell, W(at(chunk) + 0x20), shelf_table)) {
                    g_counts.shelved++; g_counts.unprepared_shelved++;
                    shelf_cell = cell;
                } else g_counts.cell_loading++;
            }
        }
    }
    // the first geometry chunk of the pass that is put into the list: the fill is drawn in front of its packet
    Buffer& b = g_buffers[g_fill];
    bool first = g_pass.active && b.fill_kinds && !b.fill_hi && !(flags & 0xC880);
    u32 before = W(G_DL_CURSOR) & RAM_MASK;
    if (shelf_cell) {
        // the chunk's cell shown as resident in a tenth slot whose header table is the shelf's, for this call only
        u8 slot_was = g_ram[G_CELL_SLOT + shelf_cell];
        u32 pointer_was = W(G_SLOT_BASE + SHELF_SLOT * 4);
        g_ram[G_CELL_SLOT + shelf_cell] = (u8)SHELF_SLOT;
        W(G_SLOT_BASE + SHELF_SLOT * 4) = shelf_table;
        orig_001887b8(c);
        W(G_SLOT_BASE + SHELF_SLOT * 4) = pointer_was;
        g_ram[G_CELL_SLOT + shelf_cell] = slot_was;
        g_shelf_drawn++;
    } else orig_001887b8(c);
    if (g_dumping) {
        s16 cell = (s16)(W(at(chunk) + 0x34) & 0xFFFF);
        s8 sl = cell > 0 ? (s8)g_ram[at(G_CELL_SLOT + cell)] : -1;
        u32 off = W(at(chunk) + 0x20), hdr = sl >= 0 && sl < 9 ? (W(at(0x425DF8 + sl * 4)) & RAM_MASK) + off : 0;
        auto it = g_shelf.find(cell);
        int have = it == g_shelf.end() || off < 0x40 || off / 0x40 - 1 >= it->second.count ? -1 : it->second.have[off / 0x40 - 1];
        fprintf(stderr, "world dump: tex %x hdr %x prep %x have %d q %u/%u\n", chunk, hdr, hdr ? W(hdr + 0x14) : 0, have, W(G_TEXQ_WRITE), W(G_TEXQ_READ));
        fprintf(stderr, "world dump: draw %x flags %x cell %d slot %d shelf %d box %.0f %.0f %.0f  %.0f %.0f %.0f list +%u\n", chunk, flags, cell,
                cell > 0 ? (int)(s8)g_ram[at(G_CELL_SLOT + cell)] : -9, shelf_cell ? 1 : 0, as_float(W(at(chunk) + 8)), as_float(W(at(chunk) + 12)),
                as_float(W(at(chunk) + 16)), as_float(W(at(chunk) + 20)), as_float(W(at(chunk) + 24)), as_float(W(at(chunk) + 28)),
                ((W(G_DL_CURSOR) & RAM_MASK) - before) >> 3);
    }
    if (first) {
        u32 after = W(G_DL_CURSOR) & RAM_MASK;
        if (after > before) { b.fill_lo = before; b.fill_hi = after; }
    }
}
