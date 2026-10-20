// gfx_rt.cpp - see gfx_rt.h.  Compiled with the runtime's flags; supplies the fn_<address>
// of the functions listed under "native graphics" in tools/recomp/hle.txt.
//
// Three groups:
//   the view      mat4_setProjection x 3 (horizontal scale), camera_setProjection (the aspect
//                 of the frustum planes), camera_buildFrustum and game_buildScreenEdgePlanes
//                 (a 4:3 set of world planes kept for the one simulation reader);
//   who drew it   draw functions whose packets the renderer has to tell apart: the address
//                 range each call adds to the display list is noted, and when the runtime
//                 walks the list for VIF1 a NOP code naming the range's kind goes into the
//                 stream in front of it;
//   the frame     gfx_beginFrame (rt_frame_hook): the aspect is taken once per frame.
// With the aspect at 4:3 every hook is the plain call of the original.
//
// Options (after "--" on the command line, "--opt key=value"):
//   wide-cull=off      keep the game's 4:3 frustum planes (to show what the widening adds)
//   wide-clamp=screen  the offline two-player screen clamp follows the wide view (changes the
//                      simulation of an offline game with two players; default: 4:3)
//   wide-tags=off      no marks in the stream
//   wide-menu3d=off    the inventory's 3-D figure is projected wide like the world
#include "gfx_rt.h"

#include "rt.h"
#include "funcs.h"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

namespace {

const u32 G_DL_BASE = 0x44FE0C, G_DL_CURSOR = 0x44FE10, G_DL_UNITS = 0x44FDA4;
const u32 PLANES_CAMERA = 0x7D5BC0, PLANES_CAMERA_SIZE = 0x48;      // six normals, camera space
const u32 PLANES_WORLD = 0x44F0A8, PLANES_WORLD_SIZE = 0x60;        // six planes, world space
const u32 MATRICES[3] = {0x44F140, 0x44F180, 0x44F1C0};             // g_viewProj, g_viewProjWorld, g_viewProjModel
const u32 G_CAMERA_MATRIX = 0x44F110;
const u32 RAM_MASK = 0x01FFFFFF;                    // the display list is addressed through the 0x30000000 mirror of main memory

enum Mode : u16 { M_NONE = 0, M_EDGE = 1, M_WORLD = 2, M_BILLBOARD = 3, M_MENU3D = 4, M_TEXT = 5 };

std::atomic<bool> g_marks_always{false};    // set_hud_marks: the marks also at 4:3
std::atomic<float> g_wanted{1.0f};      // k = (4/3) / aspect the application asks for
float g_k = 1.0f;                       // of the frame being built
int g_menu_view = 0;                    // inside a draw task that puts a 3-D figure into a 4:3 menu
bool g_options_read = false, g_cull_wide = true, g_clamp_wide = false, g_tags = true, g_menu3d = true;
u64 g_wide_frames = 0, g_clamp_calls = 0, g_marks = 0;
u32 g_list_most = 0, g_list_room = 0;   // display-list units (8 bytes) the fullest frame took, and what a frame has

// the 4:3 planes, as the game would hold them
u8 g_camera43[PLANES_CAMERA_SIZE], g_world43[PLANES_WORLD_SIZE];
bool g_have_camera43 = false, g_have_world43 = false;
// camera_setProjection's last arguments (f12..f15); until it is called (a machine resumed
// from a memory image) what the game camera passes: 50 degrees, 1.33, 80 degrees, 1
u32 g_projection_args[4] = {0x42480000, 0x3FAA3D70, 0x42A00000, 0x3F800000};

inline float as_float(u32 bits) { float f; memcpy(&f, &bits, 4); return f; }
inline u32 as_bits(float f) { u32 b; memcpy(&b, &f, 4); return b; }

void read_options() {
    if (g_options_read) return;
    g_options_read = true;
    auto is = [](const char* key, const char* value) { const char* o = rt_option(key); return o && !strcmp(o, value); };
    g_cull_wide = !is("wide-cull", "off");
    g_clamp_wide = is("wide-clamp", "screen");
    g_tags = !is("wide-tags", "off");
    g_menu3d = !is("wide-menu3d", "off");
}

float g_near = 0, g_far = 0;             // fpview: the depth range of a view of its own (0 = the game's 18 and 1800)

inline float view_k() { return (g_menu_view && g_menu3d) ? 1.0f : g_k; }

// ---- the projection -----------------------------------------------------------------------
void scaled(Ctx* c, void (*original)(Ctx*)) {
    float k = view_k();
    if (g_near > 0 && !g_menu_view) {        // (sx, sy, scale, z near, z far, near, far): f17 and f18
        u32 near_asked = c->f[17], far_asked = c->f[18];
        c->f[17] = as_bits(g_near);
        c->f[18] = as_bits(g_far);
        if (k == 1.0f) original(c);
        else {
            u32 asked = c->f[12];
            c->f[12] = as_bits(as_float(asked) * k);
            original(c);
            c->f[12] = asked;
        }
        c->f[17] = near_asked;
        c->f[18] = far_asked;
        return;
    }
    if (k == 1.0f) { original(c); return; }
    u32 asked = c->f[12], wide = as_bits(as_float(asked) * k);
    c->f[12] = wide;
    original(c);
    if (c->f[12] == wide) c->f[12] = asked;     // the caller's register as it was
}

// camera_setProjection with the planes of both shapes: first as the game asks (kept), then wide
void set_projection(Ctx* c) {
    memcpy(g_projection_args, &c->f[12], sizeof g_projection_args);
    read_options();
    float k = g_k;
    if (k == 1.0f || !g_cull_wide) {
        g_have_camera43 = g_have_world43 = false;
        orig_0018619c(c);
        return;
    }
    Ctx in = *c;
    orig_0018619c(c);
    memcpy(g_camera43, g_ram + PLANES_CAMERA, PLANES_CAMERA_SIZE);
    g_have_camera43 = true;
    g_have_world43 = false;
    s64 budget = c->budget;
    *c = in;
    c->budget = budget;
    c->f[13] = as_bits(as_float(in.f[13]) / k);
    orig_0018619c(c);
    c->f[13] = in.f[13];
}

void build_frustum(Ctx* c) {
    if (!g_have_camera43) { orig_001863fc(c); return; }
    // the planes the game would have made, from its own code: its camera-space set goes
    // in, its world-space set comes out and is kept; then the same again with the wide set
    u8 wide[PLANES_CAMERA_SIZE];
    memcpy(wide, g_ram + PLANES_CAMERA, PLANES_CAMERA_SIZE);
    Ctx in = *c;
    memcpy(g_ram + PLANES_CAMERA, g_camera43, PLANES_CAMERA_SIZE);
    orig_001863fc(c);
    memcpy(g_camera43, g_ram + PLANES_CAMERA, PLANES_CAMERA_SIZE);  // it edits two of them in place for the half-screen views
    memcpy(g_world43, g_ram + PLANES_WORLD, PLANES_WORLD_SIZE);
    g_have_world43 = true;
    s64 budget = c->budget;
    *c = in;
    c->budget = budget;
    memcpy(g_ram + PLANES_CAMERA, wide, PLANES_CAMERA_SIZE);
    orig_001863fc(c);
}

// The aspect changed between two frames: the planes are made when a level or a cutscene
// starts, the matrices at the next camera_setView - bring both up to date now.
void apply_change(Ctx* c, float from, float to) {
    for (u32 m : MATRICES)
        for (u32 row = 0; row < 4; row++) {
            u32& word = W(m + row * 16);
            word = as_bits(as_float(word) * (to / from));
        }
    Ctx saved = *c;
    memcpy(&c->f[12], g_projection_args, sizeof g_projection_args);
    set_projection(c);
    c->r[4] = G_CAMERA_MATRIX;
    build_frustum(c);
    s64 budget = c->budget;
    *c = saved;
    c->budget = budget;
}

// ---- who drew it ----------------------------------------------------------------------------
// The display list is filled from low to high addresses, one of two buffers per frame; a
// frame's lists are sent while the next frame fills the other buffer.
struct Segment { u32 lo, hi; u16 mark; };
struct Buffer { u32 base = 0, size = 0; float k = 1.0f; std::vector<Segment> segments; u64 filled_at = 0; };
Buffer g_buffers[2];
int g_fill = 0;
u64 g_frames = 0;
std::vector<u16> g_open;                // marks of the draw functions we are inside of
u32 g_segment_start = 0;
u16 g_sequence = 0;
u16 g_stream_mark = 0xFFFF;             // the last one put into the stream
float g_stream_k = -1.0f;

void close_segment(u32 upto) {
    if (!g_open.empty() && upto > g_segment_start) g_buffers[g_fill].segments.push_back({g_segment_start, upto, g_open.back()});
}
void enter(Mode mode) {
    u32 cursor = W(G_DL_CURSOR) & RAM_MASK;
    close_segment(cursor);
    g_sequence = (u16)((g_sequence + 1) & 0xFFF);
    g_open.push_back((u16)(g_sequence << 4 | mode));
    g_segment_start = cursor;
}
void leave() {
    u32 cursor = W(G_DL_CURSOR) & RAM_MASK;
    close_segment(cursor);
    if (!g_open.empty()) g_open.pop_back();
    g_segment_start = cursor;
}
struct Scope {
    bool on;
    explicit Scope(Mode mode) { read_options(); on = g_tags && (g_k != 1.0f || g_marks_always); if (on) enter(mode); }
    ~Scope() { if (on) leave(); }
};

void dma_tag(u32 tag_address, std::vector<u32>& stream) {
    u32 a = tag_address & RAM_MASK;
    static const bool log = getenv("RTA_GFX_LOG") != nullptr;
    static int left = 60, skip = 400;
    if (log && skip-- < 0 && left > 0) {
        left--;
        fprintf(stderr, "gfx: dma tag at %x; buffers %x+%x (%zu segments) %x+%x (%zu segments), cursor %x base %x units %x\n", a, g_buffers[0].base, g_buffers[0].size,
                g_buffers[0].segments.size(), g_buffers[1].base, g_buffers[1].size, g_buffers[1].segments.size(), W(G_DL_CURSOR), W(G_DL_BASE), W(G_DL_UNITS));
    }
    for (Buffer& b : g_buffers) {
        if (!b.base || a < b.base || a - b.base >= b.size) continue;
        if (b.k != g_stream_k) {
            g_stream_k = b.k;
            u32 bits = as_bits(b.k);
            stream.push_back(0x00A60000u | (bits >> 16));
            stream.push_back(0x00A70000u | (bits & 0xFFFF));
        }
        u16 mark = 0;
        size_t lo = 0, hi = b.segments.size();
        while (lo < hi) {                               // the last segment that starts at or below a
            size_t mid = (lo + hi) / 2;
            if (b.segments[mid].lo <= a) lo = mid + 1; else hi = mid;
        }
        if (lo > 0 && a < b.segments[lo - 1].hi) mark = b.segments[lo - 1].mark;
        if (mark != g_stream_mark) {
            g_stream_mark = mark;
            stream.push_back(0x00A50000u | mark);
            g_marks++;
        }
        return;
    }
    // a tag outside the display list (the present pass, uploads) is nobody's: with the marks sent for the HUD switch
    // it must not go on under the mark of the last thing the list drew
    if (g_marks_always && g_stream_mark != 0 && g_stream_mark != 0xFFFF) {
        g_stream_mark = 0;
        stream.push_back(0x00A50000u);
        g_marks++;
    }
}

void frame_hook(Ctx* c, int phase) {
    read_options();
    if (phase == 0) {
        // the frame that just ended: how full its display list got (the object walk stops
        // drawing when fewer than 3000 units are left, and a wide view draws more)
        u32 used = ((W(G_DL_CURSOR) & RAM_MASK) - (W(G_DL_BASE) & RAM_MASK)) >> 3;
        if (g_frames && used < 0x100000 && used > g_list_most) g_list_most = used;
        g_list_room = W(G_DL_UNITS);
        g_open.clear();
        return;
    }
    // gfx_beginFrame has chosen the buffer this frame is built in
    g_frames++;
    float wanted = g_wanted.load();
    if (wanted != g_k) {
        float from = g_k;
        g_k = wanted;
        apply_change(c, from, wanted);
    }
    if (g_k != 1.0f) g_wide_frames++;
    u32 base = W(G_DL_BASE) & RAM_MASK;
    int slot = g_buffers[0].base == base ? 0 : g_buffers[1].base == base ? 1 : !g_buffers[0].base ? 0 : !g_buffers[1].base ? 1
             : g_buffers[0].filled_at < g_buffers[1].filled_at ? 0 : 1;
    Buffer& b = g_buffers[slot];
    b.base = base;
    b.size = W(G_DL_UNITS) * 8;
    b.k = g_k;
    b.filled_at = g_frames;
    b.segments.clear();
    g_fill = slot;
    g_open.clear();
    // said again with every frame: a recording that starts in the middle (render/stream.h) plays right
    g_stream_k = -1.0f;
    g_stream_mark = 0xFFFF;
    g_segment_start = W(G_DL_CURSOR) & RAM_MASK;
}

}  // namespace

// ---- the functions the translation calls ------------------------------------------------------
void fn_00165950(Ctx* c) { scaled(c, orig_00165950); }
void fn_001659d0(Ctx* c) { scaled(c, orig_001659d0); }
void fn_00165a70(Ctx* c) { scaled(c, orig_00165a70); }
void fn_0018619c(Ctx* c) { set_projection(c); }
void fn_001863fc(Ctx* c) { build_frustum(c); }

void fn_001e71b0(Ctx* c) {
    if (!g_have_world43 || g_clamp_wide) { orig_001e71b0(c); return; }
    u8 wide[PLANES_WORLD_SIZE];
    memcpy(wide, g_ram + PLANES_WORLD, PLANES_WORLD_SIZE);
    memcpy(g_ram + PLANES_WORLD, g_world43, PLANES_WORLD_SIZE);
    orig_001e71b0(c);
    memcpy(g_ram + PLANES_WORLD, wide, PLANES_WORLD_SIZE);
    g_clamp_calls++;
}

static void object_walk_original(void* ctx) { orig_0014b168((Ctx*)ctx); }
void fn_0014b168(Ctx* c) { Scope s(M_WORLD); if (gfxrt::object_walk.run) gfxrt::object_walk.run(c, object_walk_original); else orig_0014b168(c); }
void fn_001d9cd4(Ctx* c) { Scope s(M_EDGE); orig_001d9cd4(c); }
void fn_001dc708(Ctx* c) { Scope s(M_EDGE); orig_001dc708(c); }
void fn_001df720(Ctx* c) { Scope s(M_EDGE); orig_001df720(c); }
void fn_001e42e0(Ctx* c) { Scope s(M_EDGE); orig_001e42e0(c); }
void fn_001dd270(Ctx* c) { Scope s(M_EDGE); orig_001dd270(c); }
#ifndef RTA_NO_HUD_TEXT_HOOKS
// hud_drawBossMeter (the boss meter and the one-line message) and hud_drawPromptBox (the interaction prompt, also
// the spell selector's): marked so that a host that draws its own can leave them out (Gs::hide_text).  Their layout
// is the unmarked one.  Needs 1d93b0 and 1d99f0 in hle.txt; a build whose translation lacks them defines
// RTA_NO_HUD_TEXT_HOOKS (tools/godot/build.py does, by itself).
void fn_001d93b0(Ctx* c) { Scope s(M_TEXT); orig_001d93b0(c); }
void fn_001d99f0(Ctx* c) { Scope s(M_TEXT); orig_001d99f0(c); }
#endif
void fn_001907d0(Ctx* c) { Scope s(M_BILLBOARD); orig_001907d0(c); }
void fn_0018fe18(Ctx* c) { Scope s(M_BILLBOARD); orig_0018fe18(c); }
void fn_001c1108(Ctx* c) { Scope s(M_MENU3D); g_menu_view++; orig_001c1108(c); g_menu_view--; }
void fn_001d1bc0(Ctx* c) { Scope s(M_MENU3D); g_menu_view++; orig_001d1bc0(c); g_menu_view--; }

namespace gfxrt {

void install() {
    rt_frame_hook = frame_hook;
    rt_dma_tag = dma_tag;
}
void set_hud_marks(bool on) { g_marks_always = on; }

void set_aspect(double aspect) {
    if (aspect < 4.0 / 3.0) aspect = 4.0 / 3.0;         // narrower than the game's picture: bars, not a taller view
    if (aspect > 4.0) aspect = 4.0;
    float k = (float)((4.0 / 3.0) / aspect);
    if (k > 0.9995f) k = 1.0f;
    g_wanted = k;
}
void figures(uint64_t& wide_frames, uint64_t& clamp_calls, uint64_t& marks) {
    wide_frames = g_wide_frames; clamp_calls = g_clamp_calls; marks = g_marks;
}
void list_figures(uint32_t& most, uint32_t& room) { most = g_list_most; room = g_list_room; }
void projection_args(uint32_t out[4]) { memcpy(out, g_projection_args, sizeof g_projection_args); }
void set_depth_range(float near_plane, float far_plane) { g_near = near_plane; g_far = far_plane; }
float view_aspect() {
    float a = as_float(g_projection_args[1]);
    if (!(a > 0.5f && a < 4.0f)) a = 4.0f / 3.0f;
    return a / (g_k > 0.1f ? g_k : 1.0f);
}
ObjectWalk object_walk = {nullptr};

}  // namespace gfxrt
