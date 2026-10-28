// Authored RTAG draw-list fixture: no game, disc, assets, or translated code.
// Loaded through the real RtaMachine API so RtaDrawer::submit sees production ABI frames.
#include "rtag.h"
#include <cstring>

namespace {
enum { NARROW_INITIAL, NARROW_REPEAT, NARROW_IDLE, WIDE_CANCEL, NARROW_CANCEL, WIDE_TRANSITION, WIDE_REPEAT, WIDE_IDLE, NARROW_RETURN, NARROW_FINAL, PHASES };
int next_phase = 0;
bool running = false;
rtag_frame frame{};
rtag_target target{};
rtag_vertex vertices[64]{};
rtag_draw draws[8]{};

void vertex(float x, float y, unsigned char red, unsigned char green, unsigned char blue) {
    auto& v = vertices[frame.vertex_count++];
    v = {};
    v.x = x * target.width / 64.0f;
    v.y = y * target.height / 64.0f;
    v.z = 0.5f;
    v.q = 1.0f;
    v.r = red; v.g = green; v.b = blue; v.a = 128; v.fog = 255;
}
void command(unsigned first, unsigned count) {
    auto& d = draws[frame.draw_count++];
    d = {};
    d.kind = RTAG_DRAW; d.prim = RTAG_TRIANGLES; d.made_by = 2;
    d.target = target.id; d.first = first; d.count = count;
    d.scissor[2] = target.width; d.scissor[3] = target.height;
    d.ztst = 1;                         // colour-only overwrite: depth never obscures the pattern
    d.scene_first = -1;
}
void rectangle(float x0, float y0, float x1, float y1, unsigned char r, unsigned char g, unsigned char b) {
    const unsigned first = frame.vertex_count;
    vertex(x0,y0,r,g,b); vertex(x1,y0,r,g,b); vertex(x0,y1,r,g,b);
    vertex(x0,y1,r,g,b); vertex(x1,y0,r,g,b); vertex(x1,y1,r,g,b);
    command(first,6);
}
void depth_strip(float z, unsigned char r, unsigned char g, unsigned char b) {
    const unsigned first = frame.vertex_count;
    rectangle(0,0,2,64,r,g,b);
    auto& d = draws[frame.draw_count-1];
    d.depth_test = 1; d.depth_write = 1; d.ztst = 2;
    for (unsigned k = first; k < frame.vertex_count; ++k) vertices[k].z = z;
}
void make_frame(int phase) {
    frame = {};
    frame.number = static_cast<uint64_t>(phase + 1);
    frame.sim_tick = phase + 1;
    frame.aspect = 1.0f;
    // A stable id and identical physical 64x64 viewport throughout. Only logical extent changes.
    const bool wide = phase == WIDE_CANCEL || phase == WIDE_TRANSITION || phase == WIDE_REPEAT || phase == WIDE_IDLE;
    target = {1, wide ? 1280 : 640, wide ? 448 : 224, 1};
    frame.vertices = vertices; frame.draws = draws;
    frame.targets = &target; frame.target_count = 1;
    frame.show_target = 1; frame.show_rect[2] = target.width; frame.show_rect[3] = target.height;
    if (phase == NARROW_IDLE || phase == WIDE_IDLE || phase == WIDE_CANCEL) return; // target announced and shown, but not repainted
    if (phase == NARROW_INITIAL) {
        rectangle(36,0,64,32,16,128,40);
        rectangle(36,32,64,64,196,32,16);
    }
    // Later frames never draw the right half: a lost viewport history cannot be hidden by repainting it.
    rectangle(2,0,34,64,0,0,0);
    const unsigned first = frame.vertex_count;
    vertex(4.25f,8.25f,255,255,255);
    vertex(29.25f,10.25f,255,255,255);
    vertex(6.25f,55.25f,255,255,255);
    command(first,3);
    // The wide pass writes a fresh blue bar. Returning to narrow must carry it,
    // rather than reveal that pass's stale original red/green picture.
    if (phase == WIDE_REPEAT) rectangle(44,0,48,64,0,0,255);
    // A strip separate from the AA triangle checks depth. Mode changes must not
    // revive the cached pass's old near depths. Other phases prove actual ordering
    // within this very frame, independently of cross-frame engine clear policy.
    if (phase == NARROW_INITIAL || phase == NARROW_REPEAT || phase == NARROW_CANCEL || phase == NARROW_FINAL) depth_strip(0.8f,255,0,0);
    if (phase == WIDE_REPEAT) depth_strip(0.9f,0,0,255);
    if (phase != NARROW_INITIAL) depth_strip(0.2f,0,255,0);
}
}

extern "C" {
int rtag_api_version(void) { return RTAG_API_VERSION; }
int rtag_has(const char*) { return 0; }
int rtag_start(const rtag_config* config) {
    if (!config || config->struct_size != sizeof(rtag_config)) return -1;
    next_phase = 0; running = true; return 0;
}
void rtag_set_pad(int, const rtag_pad*) {}
int rtag_step(const rtag_pad*, int, const rtag_frame** result) {
    if (!result || !running || next_phase >= PHASES) return -1;
    make_frame(next_phase++); *result = &frame; return 1;
}
int rtag_poll(int wait, const rtag_frame** result) { return rtag_step(nullptr,wait,result); }
void rtag_run(double) {}
void rtag_audio_pull(int16_t* out, int count) {
    if (out && count > 0) std::memset(out,0,static_cast<size_t>(count)*2*sizeof(int16_t));
}
const uint8_t* rtag_memory(void) { return nullptr; }
uint64_t rtag_fields(void) { return static_cast<uint64_t>(next_phase); }
const char* rtag_info(void) { return "authored narrow/wide/narrow target reuse; no game data"; }
int rtag_ended(void) { return !running || next_phase >= PHASES; }
int rtag_exit_code(void) { return 0; }
void rtag_stop(void) { running = false; }
int rtag_set_option(const char*,const char*) { return 0; }
}
