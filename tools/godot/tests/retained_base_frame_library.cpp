// Authored scene ABI frames only: no game, disc, assets, or translated code.
// Model packets exercise production scene_take -> kept meshes -> place_mesh.
#include "rtag.h"
#include <cstring>

namespace {
enum { SEED, REPEAT, MOVE, RECOLOUR, MATERIAL_HIDE, MATERIAL_RESTORE,
       GROW, SHRINK, FLAT_QUAD, FLAT_TRIANGLE, RETAINED_RETURN, ABSENT,
       REAPPEAR, RESIZE, RESIZE_BACK, RETIRE_TARGET, RECREATE_TARGET,
       ABSENT_BEFORE_FLAT, FLAT_AFTER_EMPTY, RETAINED_AFTER_FLAT, ABSENT_BEFORE_REBIND,
       REBIND_SAME_MATERIAL, RETIRE_MATERIAL_IDLE, MATERIAL_RECREATED, PHASES };
int next_phase = 0;
int emitted = 0;
int retire_idle_left = 193;
bool running = false;
rtag_frame frame{};
rtag_target target{1,1280,1280,1};
uint32_t dead = 1;
rtag_vertex vertices[32]{};
rtag_draw draws[3]{};
rtag_scene scene{};
rtag_scene_vertex scene_vertices[12]{};
rtag_scene_full full[12]{};
float normals[36]{};
rtag_scene_piece piece{};

void pixel_vertex(float x, float y, unsigned char r, unsigned char g, unsigned char b) {
    auto& v = vertices[frame.vertex_count++];
    v = {}; v.x = x * target.width; v.y = y * target.height; v.z = .5f; v.q = 1;
    v.r = r; v.g = g; v.b = b; v.a = 128; v.fog = 255;
}
rtag_draw& command(unsigned first, unsigned count) {
    auto& d = draws[frame.draw_count++]; d = {};
    d.kind = RTAG_DRAW; d.prim = RTAG_TRIANGLES; d.target = 1; d.first = first; d.count = count;
    d.scissor[2] = target.width; d.scissor[3] = target.height; d.ztst = 1; d.scene_first = -1;
    return d;
}
void flat(bool triangle, bool left, unsigned char r, unsigned char g, unsigned char b) {
    const unsigned start = frame.vertex_count;
    const float lo = left ? .25f : .55f, hi = left ? .45f : .75f;
    pixel_vertex(lo,.35f,r,g,b); pixel_vertex(hi,.35f,r,g,b); pixel_vertex(lo,.65f,r,g,b);
    if (!triangle) {
        pixel_vertex(lo,.65f,r,g,b); pixel_vertex(hi,.35f,r,g,b); pixel_vertex(hi,.65f,r,g,b);
    }
    command(start, triangle ? 3 : 6).made_by = 2;
}
void model_quad(bool left, unsigned char r, unsigned char g, unsigned char b) {
    const float lo = left ? -1.5f : .3f, hi = left ? -.3f : 1.5f;
    const float x[6] = {lo,hi,lo,lo,hi,hi}, z[6] = {.9f,.9f,-.9f,-.9f,.9f,-.9f};
    for (int k = 0; k < 6; ++k) {
        const unsigned n = scene.full_count++;
        full[n] = {}; full[n].x = x[k]; full[n].y = 3; full[n].z = z[k];
        full[n].ny = -1; full[n].r = r; full[n].g = g; full[n].b = b; full[n].a = 128;
        scene_vertices[n] = {x[k],3,z[k],3};
        normals[n*3] = 0; normals[n*3+1] = -1; normals[n*3+2] = 0;
        pixel_vertex(.5f + x[k]/6, .5f-z[k]/6, r,g,b);
    }
}
void make_frame(int phase) {
    frame = {}; scene = {}; piece = {};
    frame.number = ++emitted; frame.sim_tick = emitted; frame.aspect = 1;
    frame.vertices = vertices; frame.draws = draws; frame.targets = &target; frame.target_count = 1;
    frame.show_target = 1; frame.show_rect[2] = target.width; frame.show_rect[3] = target.height;
    frame.scene = &scene;
    scene.valid = 1; scene.vertices = scene_vertices; scene.normals = normals;
    scene.pieces = &piece; scene.full = full; scene.fov_y_degrees = 90; scene.near_plane = .1f; scene.far_plane = 30;
    scene.world_to_view[0] = 1; scene.world_to_view[6] = -1; scene.world_to_view[9] = 1; scene.world_to_view[15] = 1;
    if (phase == RETIRE_TARGET) {
        frame.target_count = 0; frame.show_target = 0; frame.dead_targets = &dead; frame.dead_target_count = 1;
        return;
    }
    // First draw is the game's ordinary full-surface clearing rectangle. It also
    // keeps the pass rendering when no model uses the following instance slot.
    pixel_vertex(0,0,0,0,0); pixel_vertex(1,0,0,0,0); pixel_vertex(0,1,0,0,0);
    pixel_vertex(0,1,0,0,0); pixel_vertex(1,0,0,0,0); pixel_vertex(1,1,0,0,0);
    command(0,6).made_by = 2;
    if (phase == ABSENT || phase == ABSENT_BEFORE_FLAT || phase == ABSENT_BEFORE_REBIND || phase == RETIRE_MATERIAL_IDLE) return;
    if (phase == FLAT_QUAD || phase == FLAT_TRIANGLE || phase == FLAT_AFTER_EMPTY) {
        flat(phase == FLAT_TRIANGLE, phase == FLAT_TRIANGLE,
             255, phase == FLAT_TRIANGLE ? 255 : 0, 255);
        return;
    }
    const unsigned start = frame.vertex_count;
    if (phase <= REPEAT) model_quad(true,255,0,0);
    else if (phase == MOVE) model_quad(false,0,255,0);
    else if (phase <= MATERIAL_RESTORE) model_quad(false,0,0,255);
    else if (phase == GROW) { model_quad(true,255,255,0); model_quad(false,255,255,0); }
    else model_quad(true,0,255,255);
    scene.vertex_count = scene.full_count; scene.piece_count = 1;
    piece.mesh = 0xA110CA7E; piece.object = 1; piece.kind = 2;
    piece.first = 0; piece.count = scene.full_count; piece.full_first = 0; piece.full_count = scene.full_count; piece.command = 1;
    auto& d = command(start,scene.full_count);
    d.made_by = 1; d.scene_kind = RTAG_SCENE_EXACT; d.scene_first = 0; d.scene_piece_count = 1;
    d.depth_test = 1; d.depth_write = 1; d.ztst = 2;
    if (phase == MATERIAL_HIDE) { d.alpha_test = 1; d.atst = 0; }
}
}

extern "C" {
int rtag_api_version(void) { return RTAG_API_VERSION; }
int rtag_has(const char*) { return 0; }
int rtag_start(const rtag_config* c) { if (!c || c->struct_size != sizeof(rtag_config)) return -1; next_phase=0; emitted=0; retire_idle_left=193; running=true; return 0; }
void rtag_set_pad(int,const rtag_pad*) {}
int rtag_step(const rtag_pad*,int,const rtag_frame** out) { if (!out || !running || next_phase>=PHASES) return -1; make_frame(next_phase); if (next_phase != RETIRE_MATERIAL_IDLE || --retire_idle_left == 0) ++next_phase; *out=&frame; return 1; }
int rtag_poll(int wait,const rtag_frame** out) { return rtag_step(nullptr,wait,out); }
void rtag_run(double) {}
void rtag_audio_pull(int16_t* out,int n) { if (out && n>0) std::memset(out,0,(size_t)n*2*sizeof(int16_t)); }
const uint8_t* rtag_memory(void) { return nullptr; }
uint64_t rtag_fields(void) { return (uint64_t)emitted; }
const char* rtag_info(void) { return "authored retained/flat/unused/resize/retirement scene; no game data"; }
int rtag_ended(void) { return !running || next_phase>=PHASES; }
int rtag_exit_code(void) { return 0; }
void rtag_stop(void) { running=false; }
int rtag_set_option(const char*,const char*) { return 0; }
}
