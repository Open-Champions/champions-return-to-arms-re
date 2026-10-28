// Authored RTAG packets only. No game, disc, assets, or translated code.
// One model identity/count: changed positions take the retained in-place path.
#include "rtag.h"
#include <cstring>

namespace {
constexpr int PHASES = 8;
const float CENTRE_X[PHASES] = {1000.f,-1.f,-1.f,-1.f,1.f,1.f,1000.f,-1.f};
int emitted = 0;
bool running = false;
rtag_frame frame{};
rtag_target target{1,1280,1280,1};
rtag_vertex vertices[6]{};
rtag_draw draw{};
rtag_scene scene{};
rtag_scene_vertex scene_vertices[6]{};
rtag_scene_full full[6]{};
float normals[18]{};
rtag_scene_piece piece{};

void make_frame(int phase) {
    frame = {}; scene = {}; draw = {}; piece = {};
    frame.number = ++emitted; frame.sim_tick = emitted; frame.aspect = 1;
    frame.vertices = vertices; frame.vertex_count = 6;
    frame.draws = &draw; frame.draw_count = 1;
    frame.targets = &target; frame.target_count = 1;
    frame.show_target = 1; frame.show_rect[2] = target.width; frame.show_rect[3] = target.height;
    frame.scene = &scene;
    scene.valid = 1; scene.vertices = scene_vertices; scene.vertex_count = 6;
    scene.normals = normals; scene.pieces = &piece; scene.piece_count = 1;
    scene.full = full; scene.full_count = 6;
    scene.fov_y_degrees = 60; scene.near_plane = .1f; scene.far_plane = 30;
    scene.camera_position[1] = 6;
    // Proper camera basis: screen-right+X, screen-up NEGATIVE-Z, forward-Y.
    // scene_begin reads rows right/down/forward, then builds(right,-down,-forward).
    scene.world_to_view[0] = 1;
    scene.world_to_view[6] = 1;
    scene.world_to_view[9] = -1;
    scene.world_to_view[15] = 1;
    const float dx[6] = {-.3f,-.3f,.3f,.3f,-.3f,.3f};
    const float z[6] = {-.3f,.3f,-.3f,-.3f,.3f,.3f};
    constexpr float project_denominator = 6.928203230275509f; // 2*6*tan(30deg)
    for (int k = 0; k < 6; ++k) {
        const float x = CENTRE_X[phase] + dx[k];
        full[k] = {}; full[k].x = x; full[k].y = 0; full[k].z = z[k];
        full[k].ny = 1; full[k].g = full[k].b = 255; full[k].a = 128;
        scene_vertices[k] = {x,0,z[k],6};
        normals[k*3] = 0; normals[k*3+1] = 1; normals[k*3+2] = 0;
        auto& v = vertices[k]; v = {};
        v.x = (.5f + x/project_denominator)*target.width;
        v.y = (.5f + z[k]/project_denominator)*target.height;
        v.z = .5f; v.q = 1; v.g = v.b = 255; v.a = 128; v.fog = 255;
    }
    piece.mesh = 0x5A0D0CA5; piece.object = 1; piece.kind = 2;
    piece.first = 0; piece.count = 6; piece.full_first = 0; piece.full_count = 6; piece.command = 0;
    draw.kind = RTAG_DRAW; draw.prim = RTAG_TRIANGLES; draw.target = 1;
    draw.first = 0; draw.count = 6; draw.made_by = 1;
    draw.scissor[2] = target.width; draw.scissor[3] = target.height;
    draw.scene_kind = RTAG_SCENE_EXACT; draw.scene_first = 0; draw.scene_piece_count = 1;
    draw.depth_test = 1; draw.depth_write = 1; draw.ztst = 2;
    // Deliberately no black flat clearing rectangle: an externally added lit
    // receiver must remain visible. The harness explicitly clears the environment.
}
}

extern "C" {
int rtag_api_version(void) { return RTAG_API_VERSION; }
int rtag_has(const char*) { return 0; }
int rtag_start(const rtag_config* c) {
    if (!c || c->struct_size != sizeof(rtag_config)) return -1;
    emitted = 0; running = true; return 0;
}
void rtag_set_pad(int,const rtag_pad*) {}
int rtag_step(const rtag_pad*,int,const rtag_frame** out) {
    if (!out || !running || emitted >= PHASES) return -1;
    make_frame(emitted); *out = &frame; return 1;
}
int rtag_poll(int wait,const rtag_frame** out) { return rtag_step(nullptr,wait,out); }
void rtag_run(double) {}
void rtag_audio_pull(int16_t* out,int n) { if (out && n>0) std::memset(out,0,(size_t)n*2*sizeof(int16_t)); }
const uint8_t* rtag_memory(void) { return nullptr; }
uint64_t rtag_fields(void) { return (uint64_t)emitted; }
const char* rtag_info(void) { return "authored retained shadow caster; external receiver/light; no game data"; }
int rtag_ended(void) { return !running || emitted >= PHASES; }
int rtag_exit_code(void) { return 0; }
void rtag_stop(void) { running = false; }
int rtag_set_option(const char*,const char*) { return 0; }
}
