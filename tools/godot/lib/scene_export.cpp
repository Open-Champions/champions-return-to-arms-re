// scene_tap.cpp - the 3-D scene before the game's projection (rtag_scene of rtag.h).
//
// The draw list is what the vertex programs made: positions already projected to the
// 1280 x 448 buffer.  A host that wants the scene in 3-D - to light it, to throw a shadow
// on it, to look at it from somewhere else - needs every vertex where it was in the world.
// The vertex programs (docs/spec/render-pipeline.md, section 3 and 4) compute, for a
// camera-space point (x right, y down, z forward):
//     sx = F k x / z      sy = F 0.4666667 y / z       in buffer pixels from the centre (640, 224)
//     Q  = 1 / z          (the texture coordinates are sent as S/z, T/z, 1/z)
//     zb = 16 (A + B / z)                              16-bit depth, larger = nearer
// with F = g_projScale (0x44f108), k the widescreen factor of tools/recomp/app/gfx_rt.cpp,
// and the world -> camera matrix g_cameraMatrix (0x44f110, four rows of three:
// cam = p.x m0 + p.y m1 + p.z m2 + m3).  All of it can be turned round per vertex: z comes
// from Q where a draw carries one, else from the depth (16 bits: coarser the farther
// away); x and y from the pixel position (1/16 pixel); the world position from the
// inverse of the camera matrix.  (Ran: this game sends texel coordinates, not S, T, Q -
// its texturing is not perspective-correct - so every vertex goes by its depth.  The step
// of the depth is 1/16 in A + B/z: 0.005 units at z = 78, 0.2 units at z = 500.)
//
// That is the route taken here: one rule for every vertex program - level chunks, skinned
// models, shells, trails, decals - and for what the CPU projects itself, instead of one
// decoder per program's input format.  What comes out for a model is its posed vertices in
// the world (after skinning), which is what a renderer wants.  What this cannot give: the
// programs' other inputs (normals, joint weights, the light slots) - see
// docs/issues/native-godot.md, stage 4, for what a tap at the programs' inputs would add.
//
// The camera has to be the one the vertices were projected with.  A list closed at blank N
// holds what the game queued during the frame before (it sends a frame's packets at the
// start of the next), so the camera sampled at blank N - 1 is used; RTA_SCENE_DELAY=n
// tries another, and RTA_SCENE_DIAG=1 counts, for each candidate - and for the depth's
// constant A moved either way - how many of the programs' vertices land on the quarter-unit
// grid level geometry is stored on (the right camera and the right constant put them there).
#include "scene_tap.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <unordered_map>

namespace scene {

namespace {

const uint32_t G_PROJ_SCALE = 0x44F108, G_CAMERA_MATRIX = 0x44F110;
const float NEAR_PLANE = 18.0f, FAR_PLANE = 1800.0f;
const float DEPTH_K = 4094.94f * FAR_PLANE;
const float DEPTH_A = 4095.94f - DEPTH_K / (FAR_PLANE - NEAR_PLANE), DEPTH_B = DEPTH_K * NEAR_PLANE / (FAR_PLANE - NEAR_PLANE);
const float Y_SCALE = 0.4666667f;

struct Camera {
    uint64_t number = 0;
    bool ok = false;
    float m[12];                // g_cameraMatrix
    float F = 1024.0f;
    float inverse[9];           // of the 3 x 3 part: world = (cam - m3) . inverse
};

std::mutex g_lock;
Camera g_ring[8];
unsigned g_ring_at = 0;
int g_delay = 1;
bool g_diag = false;
float g_k = 1.0f;               // widescreen factor: (4/3) / aspect
std::unordered_map<uint32_t, int> g_target_width;
// figures
uint64_t g_frames = 0, g_frames_with_camera = 0, g_world_draws = 0, g_world_vertices = 0, g_by_q = 0, g_by_depth = 0;
double g_ratio_sum = 0, g_ratio_sq = 0;
uint64_t g_ratio_n = 0;
uint64_t g_grid_n[3] = {0, 0, 0}, g_grid_hit[3] = {0, 0, 0};
enum { OFFSETS = 49 };                  // diagnostic: the depth's constant A moved by -12 .. +12 in steps of 0.5
uint64_t g_offset_n = 0, g_offset_hit[OFFSETS] = {0};

bool invert3(const float* a, float* out) {
    double det = a[0] * (a[4] * a[8] - a[5] * a[7]) - a[1] * (a[3] * a[8] - a[5] * a[6]) + a[2] * (a[3] * a[7] - a[4] * a[6]);
    if (std::fabs(det) < 1e-12) return false;
    double r = 1.0 / det;
    out[0] = (float)((a[4] * a[8] - a[5] * a[7]) * r); out[1] = (float)((a[2] * a[7] - a[1] * a[8]) * r); out[2] = (float)((a[1] * a[5] - a[2] * a[4]) * r);
    out[3] = (float)((a[5] * a[6] - a[3] * a[8]) * r); out[4] = (float)((a[0] * a[8] - a[2] * a[6]) * r); out[5] = (float)((a[2] * a[3] - a[0] * a[5]) * r);
    out[6] = (float)((a[3] * a[7] - a[4] * a[6]) * r); out[7] = (float)((a[1] * a[6] - a[0] * a[7]) * r); out[8] = (float)((a[0] * a[4] - a[1] * a[3]) * r);
    return true;
}

bool camera_for(uint64_t number, Camera& out) {
    std::lock_guard<std::mutex> hold(g_lock);
    const Camera* best = nullptr;
    for (const Camera& c : g_ring)
        if (c.ok && c.number <= number && (!best || c.number > best->number)) best = &c;
    if (!best) return false;
    out = *best;
    return true;
}

inline void to_world(const Camera& c, float px, float py, float z, float* w) {
    float cx = (px - 640.0f) * z / (c.F * g_k), cy = (py - 224.0f) * z / (c.F * Y_SCALE);
    float dx = cx - c.m[9], dy = cy - c.m[10], dz = z - c.m[11];
    w[0] = dx * c.inverse[0] + dy * c.inverse[3] + dz * c.inverse[6];
    w[1] = dx * c.inverse[1] + dy * c.inverse[4] + dz * c.inverse[7];
    w[2] = dx * c.inverse[2] + dy * c.inverse[5] + dz * c.inverse[8];
}

inline float depth_to_z(float list_z) {
    float zb = list_z * 65536.0f;
    float d = zb * (1.0f / 16.0f) - DEPTH_A;
    return d > 1e-3f ? DEPTH_B / d : FAR_PLANE * 4;
}

}  // namespace

void install(render::Renderer&) {
    if (const char* text = getenv("RTA_SCENE_DELAY")) g_delay = atoi(text);
    g_diag = getenv("RTA_SCENE_DIAG") != nullptr;
}

void set_aspect(double aspect) { g_k = (float)((4.0 / 3.0) / (aspect > 0 ? aspect : 4.0 / 3.0)); }

void at_blank(const uint8_t* ram, uint64_t number) {
    if (!ram) return;
    Camera c;
    c.number = number;
    memcpy(c.m, ram + G_CAMERA_MATRIX, sizeof c.m);
    memcpy(&c.F, ram + G_PROJ_SCALE, 4);
    c.ok = c.F > 1.0f && c.F < 1e6f && invert3(c.m, c.inverse);
    for (float v : c.m) if (!(std::fabs(v) < 1e7f)) c.ok = false;
    std::lock_guard<std::mutex> hold(g_lock);
    g_ring[g_ring_at++ & 7] = c;
}

void take(render::FrameList& list, Frame& out) {
    out.clear();
    g_frames++;
    for (const render::TargetInfo& t : list.targets) g_target_width[t.id] = t.width;
    for (uint32_t id : list.dead_targets) g_target_width.erase(id);
    Camera cam;
    uint64_t wanted = list.number >= (uint64_t)g_delay ? list.number - (uint64_t)g_delay : 0;
    if (!camera_for(wanted, cam)) return;
    out.vertices.resize(list.vertices.size());
    out.known.assign(list.commands.size(), 0);
    Camera candidates[3];
    bool have[3] = {false, false, false};
    if (g_diag) for (int d = 0; d < 3; d++) have[d] = list.number >= (uint64_t)d && camera_for(list.number - d, candidates[d]) && candidates[d].number == list.number - d;
    bool any = false;
    for (size_t k = 0; k < list.commands.size(); k++) {
        const render::DrawCmd& c = list.commands[k];
        if (c.kind != render::CMD_DRAW || c.prim != render::PK_TRIANGLES || c.made_by > 1 || c.ztst != 2 || !c.count) continue;
        auto width = g_target_width.find(c.target);
        if (width == g_target_width.end() || width->second < 1024) continue;        // the 3-D surface only
        if (c.first + c.count > list.vertices.size()) continue;
        // a program gives every vertex its own Q; what the CPU builds with texel coordinates carries 1
        bool by_q = c.made_by == 0 && c.texture != 0;
        if (by_q) {
            const render::Vertex& v0 = list.vertices[c.first];
            if (!(v0.q > 0) || v0.q == 1.0f) by_q = false;
        }
        for (uint32_t i = c.first; i < c.first + c.count; i++) {
            const render::Vertex& v = list.vertices[i];
            float z = by_q && v.q > 1e-9f ? 1.0f / v.q : depth_to_z(v.z);
            float w[3];
            to_world(cam, v.x, v.y, z, w);
            out.vertices[i] = {w[0], w[1], w[2], z};
            if (g_diag) {
                float zd = depth_to_z(v.z);
                if (by_q && zd > 20 && zd < 600) { double r = (double)zd * v.q; g_ratio_sum += r; g_ratio_sq += r * r; g_ratio_n++; }
                if (c.made_by == 0 && z < 150)
                    for (int d = 0; d < 3; d++) {
                        if (!have[d]) continue;
                        float p[3];
                        to_world(candidates[d], v.x, v.y, z, p);
                        bool on = true;
                        for (int a = 0; a < 3; a++) { float g = p[a] * 4.0f; if (std::fabs(g - std::round(g)) > 0.12f) on = false; }
                        g_grid_n[d]++; if (on) g_grid_hit[d]++;
                    }
                if (c.made_by == 0 && z < 150 && (i & 15) == 0) {
                    g_offset_n++;
                    for (int o = 0; o < OFFSETS; o++) {
                        float dd = v.z * 65536.0f * (1.0f / 16.0f) - (DEPTH_A + (o - OFFSETS / 2) * 0.5f);
                        if (dd < 1e-3f) continue;
                        float p[3];
                        to_world(cam, v.x, v.y, DEPTH_B / dd, p);
                        bool on = true;
                        for (int a = 0; a < 3; a++) { float g = p[a] * 4.0f; if (std::fabs(g - std::round(g)) > 0.12f) on = false; }
                        if (on) g_offset_hit[o]++;
                    }
                }
            }
        }
        out.known[k] = 1;
        any = true;
        g_world_draws++;
        g_world_vertices += c.count;
        if (by_q) g_by_q += c.count; else g_by_depth += c.count;
    }
    out.valid = true;
    g_frames_with_camera++;
    (void)any;
    // the camera, for the host: world -> view as a 4 x 4 (row-major, column vectors), view -> clip, and both together
    memset(out.world_to_view, 0, sizeof out.world_to_view);
    for (int r = 0; r < 3; r++) {
        for (int col = 0; col < 3; col++) out.world_to_view[r * 4 + col] = cam.m[col * 3 + r];
        out.world_to_view[r * 4 + 3] = cam.m[9 + r];
    }
    out.world_to_view[15] = 1;
    memset(out.view_to_clip, 0, sizeof out.view_to_clip);
    out.view_to_clip[0] = cam.F * g_k / 640.0f;             // x: -1..1 over the 1280 pixels
    out.view_to_clip[5] = cam.F * Y_SCALE / 224.0f;         // y: -1..1 over the 448 lines (down)
    out.view_to_clip[10] = DEPTH_A / 4096.0f; out.view_to_clip[11] = DEPTH_B / 4096.0f;      // z: the game's depth, 0..1 of 65536
    out.view_to_clip[14] = 1;                               // w = z
    for (int r = 0; r < 4; r++)
        for (int col = 0; col < 4; col++) {
            float sum = 0;
            for (int n = 0; n < 4; n++) sum += out.view_to_clip[r * 4 + n] * out.world_to_view[n * 4 + col];
            out.world_to_screen[r * 4 + col] = sum;
        }
    float origin[3] = {-cam.m[9], -cam.m[10], -cam.m[11]};
    for (int a = 0; a < 3; a++) out.camera_position[a] = origin[0] * cam.inverse[a] + origin[1] * cam.inverse[3 + a] + origin[2] * cam.inverse[6 + a];
    out.fov_y = 2.0f * std::atan(224.0f / (cam.F * Y_SCALE)) * 57.29578f;
    out.near_plane = NEAR_PLANE;
    out.far_plane = FAR_PLANE;
}

void fill(const Frame& frame, rtag_scene& view, rtag_draw* draws, size_t count) {
    memset(&view, 0, sizeof view);
    if (!frame.valid) return;
    view.valid = 1;
    view.vertices = frame.vertices.data();
    view.vertex_count = (uint32_t)frame.vertices.size();
    memcpy(view.world_to_view, frame.world_to_view, sizeof view.world_to_view);
    memcpy(view.view_to_clip, frame.view_to_clip, sizeof view.view_to_clip);
    memcpy(view.world_to_screen, frame.world_to_screen, sizeof view.world_to_screen);
    memcpy(view.camera_position, frame.camera_position, sizeof view.camera_position);
    view.fov_y_degrees = frame.fov_y;
    view.near_plane = frame.near_plane;
    view.far_plane = frame.far_plane;
    for (size_t k = 0; k < count && k < frame.known.size(); k++)
        if (frame.known[k]) draws[k].scene_first = (int32_t)draws[k].first;
}

void report() {
    double n = g_frames_with_camera ? (double)g_frames_with_camera : 1;
    printf("rtag: scene: %llu lists, %llu with a camera; per list %.1f draws and %.0f vertices put back into the world (%.0f %% by the program's own 1/z, the rest by the 16-bit depth)\n",
           (unsigned long long)g_frames, (unsigned long long)g_frames_with_camera, g_world_draws / n, g_world_vertices / n,
           g_world_vertices ? 100.0 * g_by_q / g_world_vertices : 0.0);
    if (g_diag) {
        double mean = g_ratio_n ? g_ratio_sum / g_ratio_n : 0, var = g_ratio_n ? g_ratio_sq / g_ratio_n - mean * mean : 0;
        printf("rtag: scene: depth-derived z times Q over %llu vertices: mean %.5f, standard deviation %.5f (1 = Q is 1 / camera z)\n", (unsigned long long)g_ratio_n, mean,
               var > 0 ? std::sqrt(var) : 0.0);
        printf("rtag: scene: on the grid with the depth's constant A moved by:");
        for (int o = 0; o < OFFSETS; o++) printf(" %+.1f: %.1f %%;", (o - OFFSETS / 2) * 0.5, g_offset_n ? 100.0 * g_offset_hit[o] / g_offset_n : 0.0);
        printf("\n");
        for (int d = 0; d < 3; d++)
            printf("rtag: scene: with the camera of %d blank(s) before the list's: %.1f %% of %llu program-made vertices on the quarter-unit grid\n", d,
                   g_grid_n[d] ? 100.0 * g_grid_hit[d] / g_grid_n[d] : 0.0, (unsigned long long)g_grid_n[d]);
    }
}

}  // namespace scene
