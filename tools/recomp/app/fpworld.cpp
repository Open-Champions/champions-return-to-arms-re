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
// world-skirts=auto|on|off; world-log=1; world-nocull=1 (a test aid: every box passes the
// frustum test).
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
#include <mutex>
#include <string>
#include <vector>

namespace fpworld {
namespace {

const u32 G_DL_BASE = 0x44FE0C, G_DL_CURSOR = 0x44FE10, G_DL_UNITS = 0x44FDA4;
const u32 RAM_MASK = 0x01FFFFFF;

enum { WHEN_VIEWS = 0, WHEN_OFF = 1, WHEN_ALWAYS = 2 };
std::atomic<int> g_when{WHEN_VIEWS};
std::atomic<bool> g_clip{true}, g_persp{true}, g_objects{true};
enum { AUTO = 0, ON = 1, OFF = 2 };
std::atomic<int> g_ceilings{AUTO}, g_skirts{AUTO};
bool g_options_read = false, g_log = false;

inline float as_float(u32 bits) { float f; memcpy(&f, &bits, 4); return f; }
inline u32 as_bits(float f) { u32 b; memcpy(&b, &f, 4); return b; }
inline u32 at(u32 address) { return address & RAM_MASK; }     // a guest address as an offset into main memory

bool is_on(const char* v) { return !strcmp(v, "on") || !strcmp(v, "yes") || !strcmp(v, "1"); }
bool is_off(const char* v) { return !strcmp(v, "off") || !strcmp(v, "no") || !strcmp(v, "0"); }

void read_options() {
    if (g_options_read) return;
    g_options_read = true;
    if (const char* o = rt_option("world")) setting("world", o);
    if (const char* o = rt_option("world-clip")) setting("world.clip", o);
    if (const char* o = rt_option("world-persp")) setting("world.persp", o);
    if (const char* o = rt_option("world-objects")) setting("world.objects", o);
    if (const char* o = rt_option("world-ceilings")) setting("world.ceilings", o);
    if (const char* o = rt_option("world-skirts")) setting("world.skirts", o);
    if (const char* o = rt_option("world-log")) g_log = atoi(o) != 0;
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
bool g_in_object_walk = false;

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
    g_active_passes++;
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
void object_walk(void* ctx, void (*original)(void*)) {
    bool mine = g_pass.active && g_objects.load();
    if (mine) g_in_object_walk = true;
    original(ctx);
    g_in_object_walk = false;
}

// ---- figures of a pass --------------------------------------------------------------------------------
struct Counts { u32 chunks = 0, no_cell = 0, cell_loading = 0, tests = 0; } g_counts, g_last;
int g_nocull = 0;       // a test aid: 1 = every box passes the frustum test (what is missing then is not culled, it is not there)

// ---- the level's fill -----------------------------------------------------------------------------------
// Built when a level is first drawn (the .world is fixed up in main memory by then), from the
// structure at g_world; what is built depends on the level:
//   ceilings  auto = the level clears to black, has no sky dome, and is walled: the cells of wall
//             that would carry a ceiling make up a tenth of the walked floor's area or more
//             (dungeon 0.26, cave 0.23, hall 0.34, arena 0.17, scrap-yard 0.13; a night swamp 0.06
//             and a night forest 0.01 clear to black too and get none);
//   skirts    auto = the level has no sky dome (a dome is a bowl of cloud under a floating level,
//             or a painted horizon: the rim is the design there).
const u32 G_WORLD = 0x44FDC8, G_LEVEL_NAME = 0x41B721, G_BACKGROUND = 0x506044, G_DOME_LUMP = 0x86AF54, G_LIGHT_LEVEL = 0x5D347C;
const u32 G_VIEW_PROJ = 0x44F140;
struct LevelFill {
    u32 world = 0;
    char name[16] = {0};
    u8 header[0x84] = {0};                  // the .world's header as it lay there: another level at the same address is another level
    int ceilings = -1, skirts = -1;         // the settings it was built with
    u32 kinds = 0;                          // what there is to draw: bit 0 ceilings, bit 1 skirts
    std::shared_ptr<const render::FillLevel> level;
    std::string why;
} g_level;
u64 g_fill_builds = 0;

void level_fill(u32 world) {
    char name[16] = {0};
    memcpy(name, g_ram + at(G_LEVEL_NAME), 15);
    int ceilings = g_ceilings.load(), skirts = g_skirts.load();
    if (world == g_level.world && !strcmp(name, g_level.name) && ceilings == g_level.ceilings && skirts == g_level.skirts &&
        !memcmp(g_level.header, g_ram + at(world), sizeof g_level.header)) return;
    memcpy(g_level.header, g_ram + at(world), sizeof g_level.header);
    g_level.world = world; memcpy(g_level.name, name, 16); g_level.ceilings = ceilings; g_level.skirts = skirts;
    g_level.kinds = 0; g_level.level.reset(); g_level.why.clear();
    const bool dome = W(G_DOME_LUMP) != 0, black = (W(G_BACKGROUND) & 0xFFFFFF) == 0;
    render::FillOptions opt;
    opt.skirts = skirts == ON || (skirts == AUTO && !dome);
    opt.ceilings = ceilings == ON || (ceilings == AUTO && !dome && black);
    if (opt.ceilings || opt.skirts) {
        std::shared_ptr<const render::FillLevel> level = render::build_fill(g_ram, 0x02000000, world, true, name, opt);
        g_fill_builds++;
        if (level) {
            bool walled = level->floor_area > 0 && (double)level->walls * 256.0 >= 0.10 * level->floor_area;
            bool keep_ceiling = opt.ceilings && (ceilings == ON || walled);
            if (opt.ceilings && !keep_ceiling) {            // not an interior after all: built again without
                opt.ceilings = false;
                level = opt.skirts ? render::build_fill(g_ram, 0x02000000, world, true, name, opt) : nullptr;
            }
            if (level) {
                g_level.kinds = (level->ceiling_area > 0 ? 1u : 0u) | (level->skirt_area > 0 ? 2u : 0u);
                g_level.level = level;
            }
        } else g_level.why = "the level's terrain was not read";
    }
    render::publish_fill(g_level.level);
    if (g_log) {
        const render::FillLevel* l = g_level.level.get();
        fprintf(stderr, "world: level %s: sky dome %s, clears to %06x; fill: ceiling %.0f, skirt %.0f square units, %zu triangles, walls %d cells (lid %.0f over the floor), floor %.0f, %.1f ms %s\n",
                name, dome ? "yes" : "no", W(G_BACKGROUND) & 0xFFFFFF, l ? l->ceiling_area : 0.0, l ? l->skirt_area : 0.0, l ? l->vertices.size() / 3 : (size_t)0,
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
    if (k == "world.ceilings" || k == "world.skirts") {
        int mode = v == "auto" ? AUTO : is_on(value) ? ON : is_off(value) ? OFF : -1;
        if (mode < 0) return false;
        (k == "world.ceilings" ? g_ceilings : g_skirts) = mode;
        return true;
    }
    std::atomic<bool>* part = k == "world.clip" ? &g_clip : k == "world.persp" ? &g_persp : k == "world.objects" ? &g_objects : nullptr;
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
        "\nworld.objects = " + (g_objects.load() ? "on" : "off") + "\n";
    static const char* const modes[3] = {"auto", "on", "off"};
    g_settings_text += std::string("world.ceilings = ") + modes[g_ceilings.load()] + "\nworld.skirts = " + modes[g_skirts.load()] + "\n";
    return g_settings_text.c_str();
}

const char* info() {
    std::lock_guard<std::mutex> hold(g_text_lock);
    char line[900];
    const Buffer& b = g_buffers[g_fill];
    snprintf(line, sizeof line, "world: %s; this pass %s (near %.1f far %.0f, switches %x); passes with it %llu; object cells widened %llu; "
             "last pass: %u chunks drawn, %u not (texture cell not loaded), %u not (its texture still loading), %u box tests; list %u of %u units",
             g_when.load() == WHEN_VIEWS ? "views" : g_when.load() == WHEN_OFF ? "off" : "always", b.on ? "on" : "off", b.near_plane, b.far_plane, b.switches,
             (unsigned long long)g_active_passes, (unsigned long long)g_cells_widened, g_last.chunks, g_last.no_cell, g_last.cell_loading, g_last.tests,
             ((W(G_DL_CURSOR) & RAM_MASK) - (W(G_DL_BASE) & RAM_MASK)) >> 3, W(G_DL_UNITS));
    {
        const render::FillLevel* l = g_level.level.get();
        char more[240];
        snprintf(more, sizeof more, "; fill of %s: ceiling %.0f, skirt %.0f square units in %zu triangles (walls %d cells, lid %.0f; floor %.0f; %.1f ms), said %llu times",
                 g_level.name, l ? l->ceiling_area : 0.0, l ? l->skirt_area : 0.0, l ? l->vertices.size() / 3 : (size_t)0, l ? l->walls : 0, l ? l->lid_median : 0.0f,
                 l ? l->floor_area : 0.0, l ? l->build_ms : 0.0, (unsigned long long)g_fill_notes);
        strncat(line, more, sizeof line - strlen(line) - 1);
    }
    g_info_text = line;
    return g_info_text.c_str();
}

void install() {
    read_options();
    g_prev_frame_hook = rt_frame_hook; rt_frame_hook = frame_hook;
    g_prev_dma_tag = rt_dma_tag; rt_dma_tag = dma_tag;
    fpview::on_view(on_view, nullptr);
    gfxrt::object_walk.run = object_walk;
    if (const char* o = rt_option("world-nocull")) g_nocull = atoi(o);
}

}  // namespace fpworld

// ---- the functions the translation calls ------------------------------------------------------------
using namespace fpworld;

// frustum_testBox(box, mask): box = min x, max x, min y, max y, min z, max z; 0 = outside
void fn_001868a4(Ctx* c) {
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
    if (g_nocull && g_pass.active) { c->r[2] = (u64)(s64)(s32)((u32)c->r[5] | 0x3F); return; }
    orig_001868a4(c);
}

// world_draw(world)
void fn_00189870(Ctx* c) {
    g_counts = Counts();
    u32 world = (u32)c->r[4];
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
    orig_00189870(c);
    g_last = g_counts;
}

// world_drawChunk(world, chunk, clip flag): a geometry chunk whose texture cell is not loaded, or
// whose texture is still on its way to the GS, is left out (0x1887b8)
void fn_001887b8(Ctx* c) {
    u32 chunk = (u32)c->r[5];
    u32 flags = W(at(chunk) + 0x24);
    if (!(flags & 0xC880)) {
        s16 cell = (s16)(W(at(chunk) + 0x34) & 0xFFFF);
        if (cell != 0) {
            s8 slot = (s8)g_ram[at(0x41C1B8 + cell)];
            if (slot == -1) g_counts.no_cell++;
            else {
                u32 header = W(at(0x425DF8 + slot * 4)) + W(at(chunk) + 0x20);
                if (!header || W(at(header) + 0x14) == 0) g_counts.cell_loading++; else g_counts.chunks++;
            }
        }
    }
    // the first geometry chunk of the pass that is put into the list: the fill is drawn in front of its packet
    Buffer& b = g_buffers[g_fill];
    bool first = g_pass.active && b.fill_kinds && !b.fill_hi && !(flags & 0xC880);
    u32 before = W(G_DL_CURSOR) & RAM_MASK;
    orig_001887b8(c);
    if (first) {
        u32 after = W(G_DL_CURSOR) & RAM_MASK;
        if (after > before) { b.fill_lo = before; b.fill_hi = after; }
    }
}
