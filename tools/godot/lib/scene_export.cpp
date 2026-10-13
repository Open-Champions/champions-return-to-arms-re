// scene_export.cpp - the 3-D scene for the host (rtag_scene of rtag.h): every vertex of the
// scene's draws where it was in the world, with its normal where the game has one.
//
// Two sources, the first wherever it has something:
//
// 1. THE PROGRAMS' INPUTS (core/render/scene_tap.h).  The four mesh programs - level
//    chunks and models: nearly all of the scene - are tapped where they run: the packet's
//    own vertices, normals, joints and weights, through the matrices the program used, back
//    through the inverse of the game's view-projection.  Exact positions, real normals, an
//    identity per packet.  The game's camera travels with the frame's packets: this file's
//    before_transfer() puts the 62 words at 0x44f108 in front of the first VIF1 transfer
//    after each vertical blank, as notes in the stream, so the decoder has the camera the
//    packets were made with whatever thread it runs on.  (Checked by the tap: the depth and
//    translation rows a level chunk is sent with are that camera's, bit for bit.)
//
// 2. THE DEPTH (the first version of this file).  What other programs and the CPU project -
//    the game's ground shadows, water, trails, particles made of triangles - has no tap; its
//    vertices go back along the view ray by their 16-bit depth:
//        sx = F k x / z,  sy = F 0.4666667 y / z,  zb = 16 (A + B / z)
//    Coarser (0.13 units at the usual distance) and without normals.
#include "scene_export.h"

#include "scene_tap.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <unordered_map>

namespace scene {

namespace {

const float NEAR_PLANE = 18.0f, FAR_PLANE = 1800.0f;    // the game's own; a view may bring others
float g_depth_a = 0, g_depth_b = 0, g_near = NEAR_PLANE, g_far = FAR_PLANE;
void depth_range(float near_plane, float far_plane) {
    if (!(near_plane > 0) || !(far_plane > near_plane)) { near_plane = NEAR_PLANE; far_plane = FAR_PLANE; }
    const float k = 4094.94f * far_plane;
    g_depth_a = 4095.94f - k / (far_plane - near_plane);
    g_depth_b = k * near_plane / (far_plane - near_plane);
    g_near = near_plane; g_far = far_plane;
}
const float Y_SCALE = 0.4666667f;

struct Camera {
    bool ok = false;
    float m[12];                // g_cameraMatrix
    float F = 1024.0f;
    float inverse[9];           // of the 3 x 3 part: world = (cam - m3) . inverse
};

render::SceneTap g_tap;
render::TapFrame g_tap_frame;
bool g_diag = false;
bool g_sprites = true;          // RTA_SCENE_SPRITES=0: sprites stay in the 2-D layer, as before
float g_k = 1.0f;               // widescreen factor: (4/3) / aspect
std::unordered_map<uint32_t, int> g_target_width;
// the game's thread
bool g_first_after_blank = true, g_have_drawn = false;
uint32_t g_block[render::SceneTap::CAMERA_WORDS + 2];
// figures
uint64_t g_frames = 0, g_frames_with_camera = 0, g_exact_draws = 0, g_depth_draws = 0, g_exact_vertices = 0, g_depth_vertices = 0;
uint64_t g_grid_n = 0, g_grid_hit = 0;

bool invert3(const float* a, float* out) {
    double det = a[0] * (a[4] * a[8] - a[5] * a[7]) - a[1] * (a[3] * a[8] - a[5] * a[6]) + a[2] * (a[3] * a[7] - a[4] * a[6]);
    if (std::fabs(det) < 1e-12) return false;
    double r = 1.0 / det;
    out[0] = (float)((a[4] * a[8] - a[5] * a[7]) * r); out[1] = (float)((a[2] * a[7] - a[1] * a[8]) * r); out[2] = (float)((a[1] * a[5] - a[2] * a[4]) * r);
    out[3] = (float)((a[5] * a[6] - a[3] * a[8]) * r); out[4] = (float)((a[0] * a[8] - a[2] * a[6]) * r); out[5] = (float)((a[2] * a[3] - a[0] * a[5]) * r);
    out[6] = (float)((a[3] * a[7] - a[4] * a[6]) * r); out[7] = (float)((a[1] * a[6] - a[0] * a[7]) * r); out[8] = (float)((a[0] * a[4] - a[1] * a[3]) * r);
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
    float d = zb * (1.0f / 16.0f) - g_depth_a;
    return d > 1e-3f ? g_depth_b / d : g_far * 4;
}

}  // namespace

void install(render::Renderer& renderer) {
    g_diag = getenv("RTA_SCENE_DIAG") != nullptr;
    if (getenv("RTA_SCENE_SPRITES")) g_sprites = atoi(getenv("RTA_SCENE_SPRITES")) != 0;
    g_tap.install(renderer);
}

void set_aspect(double aspect) { g_k = (float)((4.0 / 3.0) / (aspect > 0 ? aspect : 4.0 / 3.0)); }

void before_transfer(const uint8_t* ram, std::vector<uint32_t>& codes) {
    codes.clear();
    if (!ram || !g_first_after_blank) return;
    g_first_after_blank = false;
    // the camera of the draw pass that built these packets (drawn()), or - a library without the view modes -
    // the game's words as they are now, which is the same camera then
    if (!g_have_drawn) {
        memcpy(g_block, ram + render::SceneTap::CAMERA_ADDRESS, render::SceneTap::CAMERA_WORDS * 4);
        float range[2] = {NEAR_PLANE, FAR_PLANE};
        memcpy(g_block + render::SceneTap::CAMERA_WORDS, range, 8);
    }
    render::SceneTap::camera_notes(g_block, render::SceneTap::CAMERA_WORDS + 2, codes);
}

void drawn(const uint8_t* ram, float near_plane, float far_plane) {
    if (!ram) return;
    memcpy(g_block, ram + render::SceneTap::CAMERA_ADDRESS, render::SceneTap::CAMERA_WORDS * 4);
    float range[2] = {near_plane, far_plane};
    memcpy(g_block + render::SceneTap::CAMERA_WORDS, range, 8);
    g_have_drawn = true;
}

void at_blank(const uint8_t*, uint64_t) { g_first_after_blank = true; }

void take(render::FrameList& list, Frame& out) {
    out.clear();
    g_frames++;
    for (const render::TargetInfo& t : list.targets) g_target_width[t.id] = t.width;
    for (uint32_t id : list.dead_targets) g_target_width.erase(id);
    g_tap.take(g_tap_frame);
    const render::TapFrame& tap = g_tap_frame;
    if (!tap.have_camera) return;
    Camera cam;
    memcpy(cam.m, tap.world_to_view, sizeof cam.m);
    cam.F = tap.proj_scale;
    cam.ok = cam.F > 1.0f && cam.F < 1e6f && invert3(cam.m, cam.inverse);
    if (!cam.ok) return;
    depth_range(tap.near_plane, tap.far_plane);
    const size_t count = list.vertices.size();
    out.vertices.resize(count);
    out.normals.assign(count * 3, 0.0f);
    out.known.assign(list.commands.size(), 0);
    std::vector<uint8_t> exact(count, 0);
    // ---- 1: the programs' inputs ----
    static_assert(sizeof(rtag_scene_full) == sizeof(render::TapFull), "rtag_scene_full is render::TapFull");
    out.full.resize(tap.full.size());
    if (!tap.full.empty()) memcpy(out.full.data(), tap.full.data(), tap.full.size() * sizeof(render::TapFull));
    out.piece_first.assign(list.commands.size(), 0);
    out.piece_count.assign(list.commands.size(), 0);
    size_t command_at = 0;                              // pieces and draws are both in the order they were made
    int last_command = -1;
    uint32_t last_object = ~0u;
    uint8_t last_pass = 0;
    out.pieces.reserve(tap.pieces.size());
    for (const render::TapPiece& p : tap.pieces) {
        if ((size_t)p.list_first + p.list_count > count) continue;
        for (uint32_t k = 0; k < p.list_count; k++) {
            const render::TapVertex& v = tap.vertices[p.first + k];
            const uint32_t i = p.list_first + k;
            out.vertices[i] = {v.world[0], v.world[1], v.world[2], v.clip[3]};
            memcpy(&out.normals[(size_t)i * 3], v.normal, 12);
            exact[i] = 1;
        }
        rtag_scene_piece piece;
        memset(&piece, 0, sizeof piece);
        piece.mesh = p.mesh; piece.occurrence = p.occurrence; piece.object = p.object;
        piece.first = p.list_first; piece.count = p.list_count;
        piece.kind = p.kind; piece.flags = p.flags; piece.entry = p.entry;
        piece.full_first = p.full_first; piece.full_count = p.full_count;
        // whose state: the draw its list vertices are in; a packet with none (all dropped): that of the packet before it
        piece.command = -1;
        if (p.list_count) {
            while (command_at < list.commands.size() &&
                   !(list.commands[command_at].kind == render::CMD_DRAW && p.list_first >= list.commands[command_at].first &&
                     p.list_first < list.commands[command_at].first + list.commands[command_at].count)) command_at++;
            if (command_at < list.commands.size()) piece.command = (int32_t)command_at;
        } else if (last_command >= 0 && last_object == p.object && last_pass == (p.flags & render::TAP_FIRST_PASS)) piece.command = last_command;
        if (piece.command >= 0) {
            last_command = piece.command; last_object = p.object; last_pass = p.flags & render::TAP_FIRST_PASS;
            uint32_t index = (uint32_t)out.pieces.size();
            if (!out.piece_count[piece.command]) out.piece_first[piece.command] = index;
            if (out.piece_first[piece.command] + out.piece_count[piece.command] == index) out.piece_count[piece.command]++;
            else piece.command = -1;                    // not next to the draw's other packets: left to the list's own triangles
        }
        out.pieces.push_back(piece);
        if (g_diag && p.kind == render::TAP_LEVEL && !(p.flags & render::TAP_MIRRORED))
            for (uint32_t k = 0; k < p.list_count; k += 7) {
                const render::TapVertex& v = tap.vertices[p.first + k];
                bool on = true;
                for (int a = 0; a < 3; a++) { float g = v.world[a] * 4.0f; if (std::fabs(g - std::round(g)) > 0.05f) on = false; }
                g_grid_n++; if (on) g_grid_hit++;
            }
    }
    // ---- per draw: from the inputs, or by the depth, or not part of the scene ----
    for (size_t k = 0; k < list.commands.size(); k++) {
        const render::DrawCmd& c = list.commands[k];
        if (c.kind != render::CMD_DRAW || c.prim != render::PK_TRIANGLES || !c.count || c.first + c.count > count) continue;
        auto width = g_target_width.find(c.target);
        if (width == g_target_width.end() || width->second < 1024) continue;        // the 3-D surface only
        uint32_t have = 0;
        for (uint32_t i = c.first; i < c.first + c.count; i++) have += exact[i];
        if (have == c.count) {
            out.known[k] = 2;
            g_exact_draws++; g_exact_vertices += c.count;
            continue;
        }
        // What is drawn without a depth test is the 2-D layer.  A sprite that IS tested against the scene's depth
        // (a particle, a glow, a spark: a camera-facing quad at a place in the world) goes into the world where its
        // depth says it is - the host can then hide it behind what is in front of it under its own depth buffer.
        if (c.ztst != 2 && c.ztst != 3) continue;
        if (c.made_by > 1 && !g_sprites) continue;
        for (uint32_t i = c.first; i < c.first + c.count; i++) {
            if (exact[i]) continue;
            const render::Vertex& v = list.vertices[i];
            float z = depth_to_z(v.z), w[3];
            to_world(cam, v.x, v.y, z, w);
            out.vertices[i] = {w[0], w[1], w[2], z};
        }
        out.known[k] = 1;
        g_depth_draws++; g_depth_vertices += c.count;
    }
    out.valid = true;
    g_frames_with_camera++;
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
    out.view_to_clip[10] = g_depth_a / 4096.0f; out.view_to_clip[11] = g_depth_b / 4096.0f;      // z: the game's depth, 0..1 of 65536
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
    out.near_plane = g_near;
    out.far_plane = g_far;
}

void fill(const Frame& frame, rtag_scene& view, rtag_draw* draws, size_t count) {
    memset(&view, 0, sizeof view);
    if (!frame.valid) return;
    view.valid = 1;
    view.vertices = frame.vertices.data();
    view.vertex_count = (uint32_t)frame.vertices.size();
    view.normals = frame.normals.data();
    view.pieces = frame.pieces.data();
    view.piece_count = (uint32_t)frame.pieces.size();
    view.full = frame.full.data();
    view.full_count = (uint32_t)frame.full.size();
    memcpy(view.world_to_view, frame.world_to_view, sizeof view.world_to_view);
    memcpy(view.view_to_clip, frame.view_to_clip, sizeof view.view_to_clip);
    memcpy(view.world_to_screen, frame.world_to_screen, sizeof view.world_to_screen);
    memcpy(view.camera_position, frame.camera_position, sizeof view.camera_position);
    view.fov_y_degrees = frame.fov_y;
    view.near_plane = frame.near_plane;
    view.far_plane = frame.far_plane;
    for (size_t k = 0; k < count && k < frame.known.size(); k++)
        if (frame.known[k]) {
            draws[k].scene_first = (int32_t)draws[k].first; draws[k].scene_kind = frame.known[k];
            if (frame.known[k] == 2 && k < frame.piece_count.size()) { draws[k].scene_piece_first = frame.piece_first[k]; draws[k].scene_piece_count = frame.piece_count[k]; }
        }
}

void report() {
    double n = g_frames_with_camera ? (double)g_frames_with_camera : 1;
    const render::TapStats& s = g_tap.stats;
    printf("rtag: scene: %llu lists, %llu with a camera; per list %.1f draws and %.0f vertices from the programs' inputs (with normals), %.1f draws and %.0f vertices put back "
           "by their depth\n", (unsigned long long)g_frames, (unsigned long long)g_frames_with_camera, g_exact_draws / n, g_exact_vertices / n, g_depth_draws / n, g_depth_vertices / n);
    printf("rtag: scene tap: %llu mesh packets kicked, %llu handed on (%.2f %%); left out: %llu the list did not take as kicked, %llu not where the program put them, %llu not laid "
           "out as documented; %llu kicks of other programs; checked against the programs' own positions: %llu vertices, %llu off, the largest difference of the rest %.2f of 1/16 "
           "pixel\n", (unsigned long long)s.kicks, (unsigned long long)s.pieces, s.kicks ? 100.0 * s.pieces / s.kicks : 0.0, (unsigned long long)s.rejected_count,
           (unsigned long long)s.rejected_check, (unsigned long long)s.rejected_layout, (unsigned long long)s.other_entries, (unsigned long long)s.checked, (unsigned long long)s.off,
           s.worst);
    printf("rtag: scene tap: complete geometry: %llu triangles the programs' clip pass had dropped are back in it; the strips' own no-draw bits against the replay's "
           "(objects without the clip flag): %llu compared, %llu different\n", (unsigned long long)s.dropped_restored, (unsigned long long)s.stitch_checked,
           (unsigned long long)s.stitch_off);
    printf("rtag: scene tap: the camera came with %llu frames; level set-ups whose depth and translation rows are that camera's, bit for bit: %llu of %llu\n",
           (unsigned long long)s.camera_blocks, (unsigned long long)s.level_rows_equal, (unsigned long long)s.level_setups);
    if (g_diag) printf("rtag: scene: level vertices on the quarter-unit grid the files store them on (within 0.0125 units): %.2f %% of %llu looked at\n",
                       g_grid_n ? 100.0 * g_grid_hit / g_grid_n : 0.0, (unsigned long long)g_grid_n);
}

}  // namespace scene
