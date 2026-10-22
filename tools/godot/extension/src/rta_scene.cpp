// rta_scene.cpp - RtaDrawer's scene mode: the game's 3-D scene in world space under a Godot camera.
//
// In the plain mode every vertex is a point of the screen and Godot is a rasteriser.  Here
// the draws that make up the 3-D scene (rtag_draw::scene_first: what the vertex programs
// kicked, and what the CPU projected, into the 3-D surface with a depth test) are given to
// Godot where they were in the world before the game projected them (rtag_scene: the library
// turns the projection round per vertex, tools/godot/lib/scene_tap.cpp), and the viewport of
// the 3-D surface gets a perspective camera placed where the game's camera is.  Everything
// else of that surface - the 2-D layer - is drawn as before, in the list's order.
//
//   - the same meshes and the same shader (variant GS_WORLD: Godot's MODELVIEW / PROJECTION
//     instead of a position written by the shader), still in the list's order with each
//     draw's own depth test and write, the depth being Godot's own now;
//   - the game's colours - texture times its vertex light - are the surface's colour: baked
//     light.  With `lit` on (variant GS_LIT) Godot's ambient light and lights decide how much
//     of that colour arrives: a sun with a shadow map darkens what it does not reach, a
//     point light adds to what is near it;
//   - `shadows`: every opaque draw of the scene has a twin that is only drawn into Godot's
//     shadow maps (the ordered draws themselves are in the transparent pass, which does not
//     cast);
//   - the camera follows the game's (world -> view from g_cameraMatrix, field of view from
//     g_projScale), and can be pulled back along its axis, turned round the point it looks
//     at, or set free - which shows what the game never drew for its own view.
//
// Options (set_scene_option): lit 0|1, shadows 0|1, ambient E (energy of the ambient light
// with lit on), packets 0|1 (1: the packets' complete geometry, with the triangles the game's
// programs drop near the eye; 0: the draw list's own triangles), pull_back F (distance to the looked-at point times F), orbit DEGREES (round
// the vertical through that point), raise DEGREES (tilt), focus D (distance of that point
// along the view axis; default: where the player stands in the game's own view, 390).
#include "rta_drawer.h"
#include "rta_variant.h"

#include <godot_cpp/classes/rendering_server.hpp>
#include <godot_cpp/variant/basis.hpp>
#include <godot_cpp/variant/color.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>

#include <cmath>
#include <cstring>
#include <unordered_map>
#include <unordered_set>

namespace godot {

using namespace rta_variant;

// ---- the sky ---------------------------------------------------------------------------------
// What the game draws of a sky (docs/issues/native-first-person-world.md): the picture is cleared to one colour by a
// rectangle over all of it - the first draw into the 3-D surface - and 19 of the 111 levels then draw a painted dome
// round the camera: model packets without a depth write, before the first piece of the level.  The dome was made for
// a camera that looks down: it ends 18 degrees above the horizon (or is a hemisphere down to the horizon only).
// The drawer finds both in every frame, and learns the dome's edges: the colour the game's own draws give the
// upper edge and the lower edge in each of 256 directions (the packet's own texture at the edge's vertices, through
// the draw's texture function and blend over the clear colour).  project/scene_view.gd makes the sky that continues
// the dome from there (shaders/atmosphere.gdshaderinc), or a whole one from the clear colour where there is no dome.
// With the option `sky` on, the game's clearing rectangle is left out (the sky is behind everything instead) and
// the dome's draws are not hazed.
struct SkyTexture { int w = 0, h = 0; std::vector<uint8_t> rgba; };
enum { RING = 256 };

struct RtaDrawer::Scene {
    bool lit = false, shadows = false;
    bool near_fade = false;             // cut-out cards of the level thin out near the eye (a view along the ground)
    bool sky = false;                   // asked for: Godot draws the sky
    bool sky_active = false;            // ... and does in this frame (the camera is known and the game cleared the picture)
    int fill_draw = -1;                 // this frame: the game's clearing rectangle
    std::vector<uint8_t> is_dome;       // this frame, per draw
    bool have_clear = false, dome = false;
    float clear[3] = {0, 0, 0};
    float top = -10.0f, bottom = 10.0f; // radians: the dome's upper and lower edge as seen so far
    double ring_sum[2][RING][3];
    double ring_n[2][RING];
    uint8_t ring[2][RING][3];
    uint32_t ring_version = 0;
    double bright_sum[4] = {0, 0, 0, 0};    // direction of the dome's light part, weighted
    std::unordered_map<uint32_t, SkyTexture> sky_textures;
    std::unordered_set<uint64_t> ring_done;
    // Where the level's light comes from.  The game's levels are lit in their textures (every placed chunk has its own
    // pre-lit texture: docs/formats/world.md), so the direction is in the picture, not in the data: per texture, how the
    // brightness of its texels goes with the normals of the vertices that carry them (their covariance); summed over the
    // textures of the level it points to the light.  Learnt while the level is walked, kept once there is enough of it.
    double sun_sum[3] = {0, 0, 0};
    double sun_weight = 0;
    uint64_t sun_samples = 0;
    uint64_t fills_dropped = 0, dome_draws = 0, near_faded = 0;
    Scene() { memset(ring_sum, 0, sizeof ring_sum); memset(ring_n, 0, sizeof ring_n); memset(ring, 0, sizeof ring); }
    bool packets = true;                // draw the packets' complete geometry where the tap has it (false: the list's own triangles)
    std::unordered_set<uint32_t> hidden;    // objects left out (set_hidden_objects)
    uint64_t hidden_draws = 0;
    float hidden_order = -1;            // this frame: the place in the world's pass of the first draw left out (-1: none)
    std::unordered_map<uint32_t, float> hidden_orders;      // this frame: per object left out, the place of its first draw
    // Meshes kept between frames: a draw whose packets are, byte for byte, those of a mesh made before (the level's chunks
    // where nothing moved and no light changed: most of a frame) takes that mesh instead of being built and sent again.
    // Kept by the draw's identity (its packets' figures, kinds and corner counts, and how many draws of that identity came
    // before it in the frame): a draw whose content changed (a character that moved, a light that flickered) has its
    // mesh's buffers written again in place (mesh_surface_update_*_region) instead of a mesh made and another one freed -
    // what cost the most of a fight's frame in Forward+ (mesh_add_surface: buffers made and freed on the card).
    struct Kept { RID mesh; AABB box; uint64_t used = 0; uint64_t content = 0; int corners = 0; bool normals = false; };
    std::unordered_map<uint64_t, Kept> kept;
    std::unordered_map<uint64_t, uint32_t> kept_seen;  // this frame: draws of each identity so far
    bool keep = true;
    uint64_t kept_hits = 0, kept_misses = 0, kept_corners = 0, kept_updates = 0;
    uint64_t kept_ident = 0;            // this draw's identity (0: not kept)
    uint64_t kept_key = 0;              // this draw's figure (0: not kept)
    RID kept_mesh;                      // ... and the kept mesh it found
    AABB kept_box;
    double ambient = 1.0, pull_back = 1.0, orbit = 0.0, raise = 0.0, focus = 390.0;
    // Cleaner models (the owner: "cleaner models"): what Godot does to the game's models without changing a thing the
    // game computes.  model_look: solid model draws take the variant GS_MODEL (per-pixel form light by the game's own
    // normals, a rim light, a sharper texture: shaders/gs_draw.gdshaderinc); model_smooth N: every triangle of a
    // skinned model (a character, a creature) is made N x N curved triangles (PN triangles, Vlachos et al. 2001: a
    // cubic patch through the corners that follows the normals there), on the CPU as the mesh is built; the normals the
    // curve follows are welded over the frame (all skinned packets' corners at one point share one normal: no cracks
    // between triangles or between a body's packets), and an edge whose two normals part by more than model_crease
    // (cosine) is left straight (a hard edge stays hard).  contacts: the frame's standing figures (skinned models'
    // feet), handed to scene_view.gd for the contact shadows on the level (GS_CONTACT).
    bool model_look = true;
    int model_smooth = 2;
    double model_crease = 0.35;
    double model_near = 520.0;          // curved only within this distance of the eye (units; a character is about 65 high)
    bool contacts_on = true;
    std::unordered_map<uint64_t, Vector3> weld;     // this frame: quantised position -> sum of the skinned packets' normals there
    std::vector<float> contacts;                    // this frame: x, y, z (feet), radius per standing figure
    uint64_t smoothed_draws = 0, smoothed_corners = 0, model_draws = 0;
    int level_draws = 0, level_draws_last = 0;      // this frame / the last whole frame: draws of the level's own chunks
    int ground_near = 0, ground_near_last = 0;      // ... of them, those whose box reaches under the player's feet
    Vector3 feet;                                   // where the player stands (scene_view.gd: options feet_x, feet_y, feet_z)
    // this frame
    bool valid = false;
    const rtag_scene* tap = nullptr;
    Transform3D game_camera, camera;
    double fov_y = 50.0;
    std::vector<RID> casters;           // shadow-only instances, in the world's scenario
    size_t casters_used = 0;
    RID caster_scenario;
    // figures
    uint64_t packet_draws = 0;
    int64_t packet_extra = 0;           // corners drawn beyond the list's (the triangles the programs had dropped)
    uint64_t world_draws = 0, world_vertices = 0, flat_draws = 0, frames = 0, frames_without_camera = 0, exact_draws = 0, blob_shadows_dropped = 0;
};

void RtaDrawer::set_scene_mode(bool on) {
    scene_mode = on;
    if (on && !scene) scene = new Scene;
}

void RtaDrawer::set_hidden_objects(const PackedInt64Array& objects) {
    if (!scene) scene = new Scene;
    scene->hidden.clear();
    for (int64_t k = 0; k < objects.size(); k++) scene->hidden.insert((uint32_t)objects[k]);
}

void RtaDrawer::set_scene_option(const String& name, double value) {
    if (!scene) scene = new Scene;
    if (name.begins_with("fill")) { fill_option(name, value); return; }
    if (name == "lit") scene->lit = value != 0;
    else if (name == "shadows") scene->shadows = value != 0;
    else if (name == "ambient") scene->ambient = value;
    else if (name == "pull_back") scene->pull_back = value;
    else if (name == "orbit") scene->orbit = value;
    else if (name == "raise") scene->raise = value;
    else if (name == "focus") scene->focus = value;
    else if (name == "packets") scene->packets = value != 0;
    else if (name == "sky") scene->sky = value != 0;
    else if (name == "near_fade") scene->near_fade = value != 0;
    else if (name == "keep") scene->keep = value != 0;
    else if (name == "model_look") scene->model_look = value != 0;
    else if (name == "model_smooth") scene->model_smooth = std::max(1, std::min(4, (int)value));
    else if (name == "model_crease") scene->model_crease = value;
    else if (name == "model_near") scene->model_near = value;
    else if (name == "contacts") scene->contacts_on = value != 0;
    else if (name == "feet_x") scene->feet.x = (real_t)value;
    else if (name == "feet_y") scene->feet.y = (real_t)value;
    else if (name == "feet_z") scene->feet.z = (real_t)value;
}

// ---- cleaner models ---------------------------------------------------------------------------------------------------
static inline uint64_t weld_key(float x, float y, float z) {
    uint64_t a = (uint32_t)(int32_t)lrintf(x * 8.0f), b = (uint32_t)(int32_t)lrintf(y * 8.0f), c = (uint32_t)(int32_t)lrintf(z * 8.0f);
    uint64_t h = a * 0x9E3779B97F4A7C15ull;
    h = (h ^ (h >> 31) ^ b) * 0xBF58476D1CE4E5B9ull;
    h = (h ^ (h >> 29) ^ c) * 0x94D049BB133111EBull;
    return h ^ (h >> 32);
}

// The welded normals and the standing figures of this frame: one pass over the skinned packets of the tap.
static void scene_models_scan(const rtag_scene* tap, std::unordered_map<uint64_t, Vector3>& weld, std::vector<float>& contacts, bool want_weld) {
    weld.clear();
    if (want_weld) weld.reserve(1 << 15);
    contacts.clear();
    struct Box { float lo[3], hi[3]; uint32_t object; };
    std::vector<Box> boxes;
    for (uint32_t k = 0; k < tap->piece_count; k++) {
        const rtag_scene_piece& piece = tap->pieces[k];
        if (piece.kind != 2 || !(piece.flags & 4) || !piece.full_count || piece.full_first + piece.full_count > tap->full_count) continue;
        const rtag_scene_full* v = tap->full + piece.full_first;
        Box b = {{v->x, v->y, v->z}, {v->x, v->y, v->z}, piece.object};
        for (uint32_t n = 0; n < piece.full_count; n++, v++) {
            if (want_weld) weld[weld_key(v->x, v->y, v->z)] += Vector3(v->nx, v->ny, v->nz);
            b.lo[0] = std::min(b.lo[0], v->x); b.lo[1] = std::min(b.lo[1], v->y); b.lo[2] = std::min(b.lo[2], v->z);
            b.hi[0] = std::max(b.hi[0], v->x); b.hi[1] = std::max(b.hi[1], v->y); b.hi[2] = std::max(b.hi[2], v->z);
        }
        if (!boxes.empty() && boxes.back().object == piece.object) {
            Box& o = boxes.back();
            for (int a = 0; a < 3; a++) { o.lo[a] = std::min(o.lo[a], b.lo[a]); o.hi[a] = std::max(o.hi[a], b.hi[a]); }
        } else boxes.push_back(b);
    }
    // the pieces of one figure (body, head, what it wears) are objects of their own: boxes whose middles are near merge
    std::vector<Box> figures;
    for (const Box& b : boxes) {
        float cx = (b.lo[0] + b.hi[0]) * 0.5f, cy = (b.lo[1] + b.hi[1]) * 0.5f;
        bool merged = false;
        for (Box& f : figures) {
            float fx = (f.lo[0] + f.hi[0]) * 0.5f, fy = (f.lo[1] + f.hi[1]) * 0.5f;
            if (std::fabs(fx - cx) < 24.0f && std::fabs(fy - cy) < 24.0f && b.lo[2] < f.hi[2] + 8.0f && b.hi[2] > f.lo[2] - 8.0f) {
                for (int a = 0; a < 3; a++) { f.lo[a] = std::min(f.lo[a], b.lo[a]); f.hi[a] = std::max(f.hi[a], b.hi[a]); }
                merged = true;
                break;
            }
        }
        if (!merged) figures.push_back(b);
    }
    for (const Box& f : figures) {
        float h = f.hi[2] - f.lo[2], wx = f.hi[0] - f.lo[0], wy = f.hi[1] - f.lo[1];
        if (h < 6.0f || wx > 400.0f || wy > 400.0f) continue;        // a flat thing, or something as large as a room
        float r = std::max(10.0f, std::min(60.0f, 0.5f * std::max(wx, wy) * 0.8f + 4.0f));
        contacts.push_back((f.lo[0] + f.hi[0]) * 0.5f);
        contacts.push_back((f.lo[1] + f.hi[1]) * 0.5f);
        contacts.push_back(f.lo[2]);
        contacts.push_back(r);
        if (contacts.size() >= 16 * 4) break;
    }
}

// One triangle of a skinned model as n x n PN triangles: corners c[0..2], welded normals wn[0..2] (unit or zero).
// Writes n*n*3 corners: positions (12 bytes each) and attributes (stride 32: colour, s, t, 1, 1, normal).
static void pn_triangle(const rtag_scene_full* c[3], const Vector3 wn[3], int n, double crease, uint8_t*& p, uint8_t*& a) {
    Vector3 P[3], N[3];
    for (int i = 0; i < 3; i++) { P[i] = Vector3(c[i]->x, c[i]->y, c[i]->z); N[i] = wn[i]; }
    // the edge's two inner control points; straight where the normals part (a hard edge) or one is missing
    auto inner = [&](int i, int j) {
        bool curved = N[i].length_squared() > 0.25f && N[j].length_squared() > 0.25f && N[i].dot(N[j]) >= (real_t)crease;
        if (!curved) return (P[i] * 2 + P[j]) / 3;
        real_t w = (P[j] - P[i]).dot(N[i]);
        return (P[i] * 2 + P[j] - N[i] * w) / 3;
    };
    Vector3 b210 = inner(0, 1), b120 = inner(1, 0), b021 = inner(1, 2), b012 = inner(2, 1), b102 = inner(2, 0), b201 = inner(0, 2);
    Vector3 E = (b210 + b120 + b021 + b012 + b102 + b201) / 6, V = (P[0] + P[1] + P[2]) / 3;
    Vector3 b111 = E + (E - V) / 2;
    // the patch's points once each ((n + 1)(n + 2) / 2 of them), then the triangles from them
    struct Point { float pos[3]; uint8_t rgba[4]; float st[4]; float nf[3]; };
    Point grid[15];                     // n <= 4
    auto at = [n](int i, int j) { return i * (n + 1) - i * (i - 1) / 2 + j; };
    const uint8_t* c0 = &c[0]->r; const uint8_t* c1 = &c[1]->r; const uint8_t* c2 = &c[2]->r;
    for (int i = 0; i <= n; i++)
        for (int j = 0; j <= n - i; j++) {
            // barycentric: u toward c[1], v toward c[2], w toward c[0]
            float u = (float)i / n, v = (float)j / n, w = 1.0f - u - v;
            Point& g = grid[at(i, j)];
            Vector3 q = P[0] * (w * w * w) + P[1] * (u * u * u) + P[2] * (v * v * v) + b210 * (3 * w * w * u) + b120 * (3 * w * u * u) +
                        b201 * (3 * w * w * v) + b021 * (3 * u * u * v) + b102 * (3 * w * v * v) + b012 * (3 * u * v * v) + b111 * (6 * w * u * v);
            g.pos[0] = (float)q.x; g.pos[1] = (float)q.y; g.pos[2] = (float)q.z;
            for (int k = 0; k < 4; k++) g.rgba[k] = (uint8_t)std::min(255.0f, std::max(0.0f, c0[k] * w + c1[k] * u + c2[k] * v + 0.5f));
            g.st[0] = c[0]->u * w + c[1]->u * u + c[2]->u * v; g.st[1] = c[0]->v * w + c[1]->v * u + c[2]->v * v; g.st[2] = 1.0f; g.st[3] = 1.0f;
            Vector3 nn = Vector3(c[0]->nx, c[0]->ny, c[0]->nz) * w + Vector3(c[1]->nx, c[1]->ny, c[1]->nz) * u + Vector3(c[2]->nx, c[2]->ny, c[2]->nz) * v;
            if (nn.length_squared() > 1e-12f) nn.normalize();
            g.nf[0] = (float)nn.x; g.nf[1] = (float)nn.y; g.nf[2] = (float)nn.z;
        }
    auto corner = [&](int i, int j) {
        const Point& g = grid[at(i, j)];
        memcpy(p, g.pos, 12);
        memcpy(a, g.rgba, 4);
        memcpy(a + 4, g.st, 16);
        memcpy(a + 20, g.nf, 12);
        p += 12;
        a += 32;
    };
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n - i; j++) {
            corner(i, j); corner(i + 1, j); corner(i, j + 1);
            if (i + j < n - 1) { corner(i + 1, j); corner(i + 1, j + 1); corner(i, j + 1); }
        }
}


void RtaDrawer::sky_reset() {
    if (!scene) return;
    Scene& sc = *scene;
    sc.dome = false; sc.have_clear = false;
    sc.top = -10.0f; sc.bottom = 10.0f;
    memset(sc.ring_sum, 0, sizeof sc.ring_sum); memset(sc.ring_n, 0, sizeof sc.ring_n);
    memset(sc.bright_sum, 0, sizeof sc.bright_sum);
    sc.sky_textures.clear();
    sc.ring_done.clear();
    sc.ring_version++;
    sc.sun_sum[0] = sc.sun_sum[1] = sc.sun_sum[2] = 0;
    sc.sun_weight = 0;
    sc.sun_samples = 0;
}

Dictionary RtaDrawer::get_sky_info() const {
    Dictionary info;
    if (!scene) return info;
    const Scene& sc = *scene;
    info["active"] = sc.sky_active;
    PackedFloat32Array contacts;
    contacts.resize((int64_t)sc.contacts.size());
    for (size_t k = 0; k < sc.contacts.size(); k++) contacts.set((int64_t)k, sc.contacts[k]);
    info["contacts"] = contacts;
    info["level_draws"] = sc.level_draws_last;
    info["ground_near"] = sc.ground_near_last;
    info["have_clear"] = sc.have_clear;
    info["clear"] = Color(sc.clear[0], sc.clear[1], sc.clear[2]);
    info["dome"] = sc.dome;
    info["top"] = sc.top;
    info["bottom"] = sc.bottom;
    info["version"] = (int64_t)sc.ring_version;
    PackedByteArray bytes;
    bytes.resize(RING * 2 * 3);
    memcpy(bytes.ptrw(), sc.ring, RING * 2 * 3);
    info["ring"] = bytes;
    info["ring_width"] = (int64_t)RING;
    double n = sc.bright_sum[3] > 0 ? sc.bright_sum[3] : 1;
    info["bright"] = Vector3((real_t)(sc.bright_sum[0] / n), (real_t)(sc.bright_sum[1] / n), (real_t)(sc.bright_sum[2] / n));
    // the painted light: a vector toward it (its length says how clearly the textures agree: brightness, 0..1, per unit
    // of normal), and how many vertices it rests on
    double w = sc.sun_weight > 0 ? sc.sun_weight : 1;
    info["sun"] = Vector3((real_t)(sc.sun_sum[0] / w), (real_t)(sc.sun_sum[1] / w), (real_t)(sc.sun_sum[2] / w));
    info["sun_samples"] = (int64_t)sc.sun_samples;
    return info;
}

// The game's clearing rectangle and its dome in this frame's list; the dome's edges are learnt.
void RtaDrawer::scene_scan_sky(const rtag_frame& f, const Target& world) {
    Scene& sc = *scene;
    const rtag_scene* tap = sc.tap;
    sc.fill_draw = -1;
    sc.is_dome.assign(f.draw_count, 0);
    std::vector<uint32_t> found;
    float frame_top = -10.0f, frame_bottom = 10.0f;
    const float* eye = tap->camera_position;
    for (uint32_t i = 0; i < f.draw_count; i++) {
        const rtag_draw& d = f.draws[i];
        if (d.target != world.id || d.kind != RTAG_DRAW || !d.count || d.first + d.count > f.vertex_count) continue;
        bool in_scene = d.scene_first >= 0 && (uint32_t)d.scene_first + d.count <= tap->vertex_count;
        if (!in_scene) {
            if (sc.fill_draw < 0 && found.empty() && !d.texture && d.prim == RTAG_TRIANGLES && d.count >= 6) {
                float x0 = 1e9f, y0 = 1e9f, x1 = -1e9f, y1 = -1e9f;
                for (uint32_t k = 0; k < d.count; k++) {
                    const rtag_vertex& v = f.vertices[d.first + k];
                    x0 = std::min(x0, v.x); x1 = std::max(x1, v.x); y0 = std::min(y0, v.y); y1 = std::max(y1, v.y);
                }
                if (x0 <= 2 && y0 <= 2 && x1 >= world.lw - 2 && y1 >= world.lh - 2) {
                    sc.fill_draw = (int)i;
                    const rtag_vertex& v = f.vertices[d.first];
                    sc.clear[0] = v.r / 255.0f; sc.clear[1] = v.g / 255.0f; sc.clear[2] = v.b / 255.0f;
                    sc.have_clear = true;
                }
            }
            continue;
        }
        if (d.depth_write) break;                       // the level begins
        if (d.scene_kind != RTAG_SCENE_EXACT || !d.scene_piece_count || d.scene_piece_first + d.scene_piece_count > tap->piece_count) continue;
        if (tap->pieces[d.scene_piece_first].kind != 2) continue;
        sc.is_dome[i] = 1;
        found.push_back(i);
        const rtag_scene_piece* pieces = tap->pieces + d.scene_piece_first;
        for (uint32_t k = 0; k < d.scene_piece_count; k++) {
            const rtag_scene_full* v = tap->full + pieces[k].full_first;
            for (uint32_t n = 0; n < pieces[k].full_count; n++, v++) {
                float dx = v->x - eye[0], dy = v->y - eye[1], dz = v->z - eye[2];
                float r = std::sqrt(dx * dx + dy * dy + dz * dz);
                if (r < 1.0f) continue;
                float e = std::asin(dz / r);
                frame_top = std::max(frame_top, e); frame_bottom = std::min(frame_bottom, e);
            }
        }
    }
    sc.dome_draws += found.size();
    if (found.empty() || !sc.have_clear) return;
    sc.dome = true;
    bool changed = false;
    if (frame_top > sc.top + 0.02f) {                   // a higher ring came into view: the edge is there
        sc.top = frame_top;
        memset(sc.ring_sum[0], 0, sizeof sc.ring_sum[0]); memset(sc.ring_n[0], 0, sizeof sc.ring_n[0]);
        sc.ring_done.clear();
        changed = true;
    }
    if (frame_bottom < sc.bottom - 0.02f) {
        sc.bottom = frame_bottom;
        memset(sc.ring_sum[1], 0, sizeof sc.ring_sum[1]); memset(sc.ring_n[1], 0, sizeof sc.ring_n[1]);
        sc.ring_done.clear();
        changed = true;
    }
    const float edge = 0.012f;
    for (uint32_t i : found) {
        const rtag_draw& d = f.draws[i];
        const rtag_scene_piece* pieces = tap->pieces + d.scene_piece_first;
        const SkyTexture* texture = nullptr;
        bool looked = false;
        // the draw's blend over the clear colour (as material_for sets it up)
        float bsc = 0, bsk = 1, bdc = 0, bdk = 0;
        if (d.blend) {
            bsc = (d.ba == 0 ? 1.0f : 0.0f) - (d.bb == 0 ? 1.0f : 0.0f); bsk = d.bd == 0 ? 1.0f : 0.0f;
            bdc = (d.ba == 1 ? 1.0f : 0.0f) - (d.bb == 1 ? 1.0f : 0.0f); bdk = d.bd == 1 ? 1.0f : 0.0f;
        }
        for (uint32_t k = 0; k < d.scene_piece_count; k++) {
            const rtag_scene_piece& piece = pieces[k];
            if (piece.full_count < 3) continue;
            const rtag_scene_full* v = tap->full + piece.full_first;
            float first_az = std::atan2(v->y - eye[1], v->x - eye[0]);
            uint64_t key = piece.mesh ^ ((uint64_t)d.texture * 0x9E3779B97F4A7C15ull) ^ ((uint64_t)(int64_t)std::lround(first_az * 40.0f) << 48);
            if (sc.ring_done.count(key)) continue;
            if (!looked && d.texture) {
                looked = true;
                auto have = sc.sky_textures.find(d.texture);
                if (have == sc.sky_textures.end()) {
                    SkyTexture copy;
                    for (uint32_t t = 0; t < f.texture_count; t++)
                        if (f.textures[t].id == d.texture) {
                            copy.w = f.textures[t].width; copy.h = f.textures[t].height;
                            copy.rgba.assign(f.textures[t].rgba, f.textures[t].rgba + (size_t)copy.w * copy.h * 4);
                        }
                    if (!copy.w) {                      // made by an earlier list: read it back once
                        auto gpu = textures.find(d.texture);
                        if (gpu != textures.end()) {
                            Ref<Image> image = RenderingServer::get_singleton()->texture_2d_get(gpu->second);
                            if (image.is_valid()) {
                                if (image->get_format() != Image::FORMAT_RGBA8) image->convert(Image::FORMAT_RGBA8);
                                copy.w = image->get_width(); copy.h = image->get_height();
                                PackedByteArray data = image->get_data();
                                if (data.size() >= (int64_t)copy.w * copy.h * 4) copy.rgba.assign(data.ptr(), data.ptr() + (size_t)copy.w * copy.h * 4);
                                else copy.w = copy.h = 0;
                            }
                        }
                    }
                    have = sc.sky_textures.emplace(d.texture, std::move(copy)).first;
                }
                if (have->second.w) texture = &have->second;
            }
            if (d.texture && !texture) continue;        // not yet: looked at again when the texture is there
            sc.ring_done.insert(key);
            for (uint32_t n = 0; n + 2 < piece.full_count; n += 3) {
                for (int a = 0; a < 3; a++) {
                    const rtag_scene_full& p = v[n + a];
                    const rtag_scene_full& q = v[n + (a + 1) % 3];
                    float pd[3] = {p.x - eye[0], p.y - eye[1], p.z - eye[2]}, qd[3] = {q.x - eye[0], q.y - eye[1], q.z - eye[2]};
                    float pr = std::sqrt(pd[0] * pd[0] + pd[1] * pd[1] + pd[2] * pd[2]), qr = std::sqrt(qd[0] * qd[0] + qd[1] * qd[1] + qd[2] * qd[2]);
                    if (pr < 1.0f || qr < 1.0f) continue;
                    float pe = std::asin(pd[2] / pr), qe = std::asin(qd[2] / qr);
                    int row = -1;
                    if (pe >= sc.top - edge && qe >= sc.top - edge) row = 0;
                    else if (pe <= sc.bottom + edge && qe <= sc.bottom + edge) row = 1;
                    if (row < 0) continue;
                    const int steps = 24;
                    for (int st = 0; st <= steps; st++) {
                        float t = (float)st / steps;
                        float dx = pd[0] + (qd[0] - pd[0]) * t, dy = pd[1] + (qd[1] - pd[1]) * t;
                        float u = p.u + (q.u - p.u) * t, w = p.v + (q.v - p.v) * t;
                        float vc[4] = {p.r + (q.r - p.r) * t, p.g + (q.g - p.g) * t, p.b + (q.b - p.b) * t, p.a + (q.a - p.a) * t};
                        float c[4] = {vc[0], vc[1], vc[2], vc[3]};
                        if (texture) {
                            float x = u * d.st_scale[0], y = w * d.st_scale[1];
                            if (d.wrap_s == RTAG_WRAP_REGION_CLAMP) x = std::min(std::max(x, d.region[0]), d.region[1]);
                            if (d.wrap_t == RTAG_WRAP_REGION_CLAMP) y = std::min(std::max(y, d.region[2]), d.region[3]);
                            int tx = std::min(std::max((int)std::floor(x + d.tex_offset[0]), 0), texture->w - 1);
                            int ty = std::min(std::max((int)std::floor(y + d.tex_offset[1]), 0), texture->h - 1);
                            const uint8_t* tp = &texture->rgba[((size_t)ty * texture->w + tx) * 4];
                            if (d.tfx == 1) { c[0] = tp[0]; c[1] = tp[1]; c[2] = tp[2]; c[3] = d.tcc ? tp[3] : vc[3]; }
                            else {
                                float add = d.tfx >= 2 ? vc[3] : 0.0f;
                                for (int ch = 0; ch < 3; ch++) c[ch] = std::min(tp[ch] * vc[ch] / 128.0f + add, 255.0f);
                                c[3] = !d.tcc ? vc[3] : d.tfx == 0 ? std::min(tp[3] * vc[3] / 128.0f, 255.0f) : d.tfx == 2 ? std::min(tp[3] + vc[3], 255.0f) : (float)tp[3];
                            }
                        }
                        float factor = d.bc == 0 ? c[3] / 128.0f : d.bc == 1 ? 1.0f : d.fix / 128.0f;
                        float source = d.blend ? std::fabs(bsc * factor + bsk) : 1.0f;
                        float destination = d.blend ? std::min(std::max(std::fabs(bdc * factor + bdk), 0.0f), 1.0f) : 0.0f;
                        int bin = (int)std::floor((std::atan2(dy, dx) / 6.2831853f + 0.5f) * RING);
                        bin = ((bin % RING) + RING) % RING;
                        float lum = 0;
                        for (int ch = 0; ch < 3; ch++) {
                            float out = std::min(c[ch] / 255.0f * source, 1.0f) + sc.clear[ch] * destination;
                            out = std::min(out, 1.0f);
                            sc.ring_sum[row][bin][ch] += out;
                            lum += out;
                        }
                        sc.ring_n[row][bin] += 1;
                        if (row == 0) {
                            double weight = (double)lum * lum * lum;
                            float len = std::sqrt(dx * dx + dy * dy);
                            if (len > 1e-3f) { sc.bright_sum[0] += dx / len * weight; sc.bright_sum[1] += dy / len * weight; sc.bright_sum[3] += weight; }
                        }
                    }
                    changed = true;
                }
            }
        }
    }
    if (!changed) return;
    // the ring as it is shown: what was seen, the nearest seen for what was not, and a little smoothing
    for (int row = 0; row < 2; row++) {
        float colour[RING][3];
        int known = 0;
        for (int b = 0; b < RING; b++) if (sc.ring_n[row][b] > 0) known++;
        for (int b = 0; b < RING; b++) {
            int from = -1;
            for (int step = 0; step < RING / 2 + 1 && from < 0 && known; step++) {
                if (sc.ring_n[row][(b + step) % RING] > 0) from = (b + step) % RING;
                else if (sc.ring_n[row][(b - step + RING) % RING] > 0) from = (b - step + RING) % RING;
            }
            for (int ch = 0; ch < 3; ch++) colour[b][ch] = from >= 0 ? (float)(sc.ring_sum[row][from][ch] / sc.ring_n[row][from]) : sc.clear[ch];
        }
        for (int b = 0; b < RING; b++)
            for (int ch = 0; ch < 3; ch++) {
                float sum = 0;
                for (int o = -3; o <= 3; o++) sum += colour[(b + o + RING) % RING][ch];
                sc.ring[row][b][ch] = (uint8_t)std::lround(std::min(std::max(sum / 7.0f, 0.0f), 1.0f) * 255.0f);
            }
    }
    sc.ring_version++;
}

RID RtaDrawer::get_world_scenario() const {
    const Target* world = const_cast<RtaDrawer*>(this)->world_target();
    return world ? world->passes[0]->scenario : RID();
}

RID RtaDrawer::get_world_camera() const {
    const Target* world = const_cast<RtaDrawer*>(this)->world_target();
    return world ? world->passes[0]->camera : RID();
}

RID RtaDrawer::get_world_viewport() const {
    const Target* world = const_cast<RtaDrawer*>(this)->world_target();
    return world ? world->passes[0]->viewport : RID();
}

RID RtaDrawer::get_world_environment() const {
    const Target* world = const_cast<RtaDrawer*>(this)->world_target();
    return world ? world->passes[0]->environment : RID();
}

String RtaDrawer::describe_frame(int max_lines) const {
    String text;
    if (machine.is_null() || !machine->current()) return text;
    const rtag_frame& f = *machine->current();
    const Target* world = const_cast<RtaDrawer*>(this)->world_target();
    const rtag_scene* tap = f.scene && f.scene->valid ? f.scene : nullptr;
    int lines = 0;
    for (uint32_t i = 0; i < f.draw_count && lines < max_lines; i++) {
        const rtag_draw& d = f.draws[i];
        if (!world || d.target != world->id) continue;
        float x0 = 1e9f, y0 = 1e9f, x1 = -1e9f, y1 = -1e9f;
        int ar = 0, ag = 0, ab = 0, aa = 0;
        for (uint32_t k = 0; k < d.count && d.first + k < f.vertex_count; k++) {
            const rtag_vertex& v = f.vertices[d.first + k];
            x0 = std::min(x0, v.x); x1 = std::max(x1, v.x); y0 = std::min(y0, v.y); y1 = std::max(y1, v.y);
            ar += v.r; ag += v.g; ab += v.b; aa += v.a;
        }
        int n = d.count ? (int)d.count : 1;
        String line = vformat("%4d %s by%d n%-5d tex %-5d%s tfx%d blend%d(%d%d%d%d fix%d) atst%d/%d z%d%s box %.0f,%.0f-%.0f,%.0f rgba %d,%d,%d,%d", (int64_t)i,
                              d.kind == RTAG_COPY ? "copy" : d.prim == RTAG_TRIANGLES ? "tri " : "oth ", (int)d.made_by, (int64_t)d.count, (int64_t)d.texture, d.tex_is_target ? "T" : " ",
                              (int)d.tfx, (int)d.blend, (int)d.ba, (int)d.bb, (int)d.bc, (int)d.bd, (int)d.fix, (int)d.alpha_test, (int)d.aref, (int)d.ztst, d.depth_write ? "w" : "-",
                              x0, y0, x1, y1, ar / n, ag / n, ab / n, aa / n);
        if (tap && d.scene_first >= 0 && (uint32_t)d.scene_first + d.count <= tap->vertex_count) {
            float r0 = 1e9f, r1 = 0, e0 = 90, e1 = -90;
            for (uint32_t k = 0; k < d.count; k++) {
                const rtag_scene_vertex& w = tap->vertices[d.scene_first + k];
                float dx = w.x - tap->camera_position[0], dy = w.y - tap->camera_position[1], dz = w.z - tap->camera_position[2];
                float r = std::sqrt(dx * dx + dy * dy + dz * dz);
                float e = r > 1e-3f ? std::asin(dz / r) * 57.29578f : 0;
                r0 = std::min(r0, r); r1 = std::max(r1, r); e0 = std::min(e0, e); e1 = std::max(e1, e);
            }
            int kind = 0, entry = 0, flags = 0;
            if (d.scene_piece_count && d.scene_piece_first < tap->piece_count) { kind = tap->pieces[d.scene_piece_first].kind; entry = tap->pieces[d.scene_piece_first].entry; flags = tap->pieces[d.scene_piece_first].flags; }
            line += vformat("  WORLD %s pieces %d kind %d entry %x flags %x  r %.0f..%.0f elev %.0f..%.0f", d.scene_kind == RTAG_SCENE_EXACT ? "exact" : "depth", (int64_t)d.scene_piece_count,
                            kind, entry, flags, r0, r1, e0, e1);
        }
        text += line + "\n";
        lines++;
    }
    return text;
}

Dictionary RtaDrawer::get_scene_info() const {
    Dictionary info;
    if (!scene) return info;
    info["valid"] = scene->valid;
    info["game_camera"] = scene->game_camera;
    info["camera"] = scene->camera;
    info["fov_y"] = scene->fov_y;
    // where the host's own figure goes among the world's draws (set_hidden_objects): the transparent pass draws by this
    // sorting offset, as the drawer places every draw (RtaDrawer::place)
    info["hidden_order"] = scene->hidden_order;
    {
        Dictionary per;                 // per object left out: the place of its first draw (a figure of the host's goes there)
        for (const auto& e : scene->hidden_orders) per[(int64_t)e.first] = e.second;
        info["hidden_orders"] = per;
    }
    info["hidden_draws"] = (int64_t)scene->hidden_draws;
    info["focus"] = scene->game_camera.origin - scene->game_camera.basis.get_column(2) * (real_t)scene->focus;
    double n = scene->frames ? (double)scene->frames : 1;
    info["figures"] = vformat("scene: %d lists (%d without a camera); per list %.1f draws and %.0f vertices in the world (%.1f of the draws from the vertex programs' inputs, "
                              "with normals; %.1f of them as whole packets, %.0f corners a list more than the list has: the triangles the game drops near the eye and off "
                              "screen), %.1f draws of the 2-D layer, %.2f of the game's own ground shadows left out; sky: %.2f of the game's clearing rectangles left out, %.1f dome "
                              "draws, %.1f sprite draws placed by their depth; kept meshes: %.1f draws a list taken as they were (%.0f corners), %.1f made, %.1f written again in place, %d held", (int64_t)scene->frames,
                              (int64_t)scene->frames_without_camera, scene->world_draws / n, scene->world_vertices / n, scene->exact_draws / n, scene->packet_draws / n,
                              (double)scene->packet_extra / n, scene->flat_draws / n, scene->blob_shadows_dropped / n, scene->fills_dropped / n, scene->dome_draws / n,
                              scene->near_faded / n, scene->kept_hits / n, scene->kept_corners / n, scene->kept_misses / n, scene->kept_updates / n, (int64_t)scene->kept.size());
    info["figures"] = String(info["figures"]) + vformat("; models: %.1f solid model draws a list in the cleaner look, %.1f of them curved (%d x %d), %.0f curved corners a list",
                              scene->model_draws / n, scene->smoothed_draws / n, (int64_t)scene->model_smooth, (int64_t)scene->model_smooth, scene->smoothed_corners / n);
    return info;
}

void RtaDrawer::scene_begin(const rtag_frame& f) {
    Scene& sc = *scene;
    RenderingServer* s = RenderingServer::get_singleton();
    sc.frames++;
    sc.tap = f.scene;
    sc.valid = f.scene && f.scene->valid;
    sc.casters_used = 0;
    sc.kept_seen.clear();
    sc.sky_active = false;
    sc.fill_draw = -1;
    sc.is_dome.clear();
    sc.contacts.clear();
    sc.level_draws_last = sc.level_draws;
    sc.level_draws = 0;
    sc.ground_near_last = sc.ground_near;
    sc.ground_near = 0;
    sc.hidden_order = -1;
    sc.hidden_orders.clear();
    Target* world = world_target();
    if (!sc.valid || !world) { if (!sc.valid) sc.frames_without_camera++; return; }
    scene_scan_sky(f, *world);
    sc.sky_active = sc.sky && sc.fill_draw >= 0;
    if (sc.packets && f.scene->full && (sc.model_smooth > 1 || sc.contacts_on)) scene_models_scan(f.scene, sc.weld, sc.contacts, sc.model_look && sc.model_smooth > 1);
    else { sc.weld.clear(); sc.contacts.clear(); }
    Pass* pass = world->passes[0];
    // The game's camera space is x right, y down, z forward; Godot's is x right, y up, z back.  world_to_view's
    // rows are the camera's axes in the world.
    const float* m = f.scene->world_to_view;
    Vector3 right(m[0], m[1], m[2]), down(m[4], m[5], m[6]), forward(m[8], m[9], m[10]);
    Vector3 position(f.scene->camera_position[0], f.scene->camera_position[1], f.scene->camera_position[2]);
    sc.game_camera = Transform3D(Basis(right, -down, -forward), position);
    sc.fov_y = f.scene->fov_y_degrees;
    Transform3D camera = sc.game_camera;
    if (sc.pull_back != 1.0 || sc.orbit != 0.0 || sc.raise != 0.0) {
        Vector3 focus = position + forward * (real_t)sc.focus;
        Vector3 offset = position - focus;
        Vector3 up(0, 0, 1);                                // the game's world is z up
        offset = offset.rotated(up, (real_t)Math::deg_to_rad(sc.orbit));
        Vector3 side = up.cross(offset).normalized();
        if (side.length() > 0.5f) offset = offset.rotated(side, (real_t)Math::deg_to_rad(-sc.raise));
        offset *= (real_t)sc.pull_back;
        Vector3 eye = focus + offset;
        camera = Transform3D(Basis(), eye).looking_at(focus, up);
    }
    sc.camera = camera;
    s->camera_set_transform(pass->camera, camera);
    double far_plane = f.scene->far_plane * std::max(1.0, sc.pull_back) * 1.5;
    s->camera_set_perspective(pass->camera, (float)sc.fov_y, f.scene->near_plane, (float)far_plane);
    fill_frame(f, camera.origin, pass->scenario);           // the level's generated ceilings and skirts (rta_fill.cpp)
    if (sc.lit) s->environment_set_ambient_light(pass->environment, Color(1, 1, 1), RenderingServer::ENV_AMBIENT_SOURCE_COLOR, (float)sc.ambient);
    // a camera that is not the game's sees past what the game drew: black there, not last frame's picture
    s->environment_set_background(pass->environment, sc.pull_back != 1.0 || sc.orbit != 0.0 || sc.raise != 0.0 ? RenderingServer::ENV_BG_CLEAR_COLOR : RenderingServer::ENV_BG_KEEP);
}

bool RtaDrawer::scene_take(Pass& pass, const rtag_frame& f, const rtag_draw& d, const Target& target, RID texture, float order) {
    Scene& sc = *scene;
    const size_t index = (size_t)(&d - f.draws);
    if (sc.sky_active && (int)index == sc.fill_draw) { sc.fills_dropped++; return true; }     // the sky is behind everything instead
    if (!sc.valid || d.scene_first < 0 || !d.count || (uint32_t)d.scene_first + d.count > sc.tap->vertex_count || d.first + d.count > f.vertex_count) {
        sc.flat_draws++;
        return false;
    }
    RenderingServer* s = RenderingServer::get_singleton();
    if (fill_drops(f, d)) return true;                      // the library's plain fill: drawn here by rta_fill.cpp instead
    if (!sc.hidden.empty() && d.scene_piece_count && d.scene_piece_first + d.scene_piece_count <= sc.tap->piece_count) {
        // an object the host draws itself (set_hidden_objects): a draw all of whose packets are its goes
        uint32_t hidden = 0;
        for (uint32_t k = 0; k < d.scene_piece_count; k++) hidden += sc.hidden.count(sc.tap->pieces[d.scene_piece_first + k].object) ? 1 : 0;
        if (hidden == d.scene_piece_count) {
            sc.hidden_draws++;
            if (sc.hidden_order < 0 || order < sc.hidden_order) sc.hidden_order = order;
            for (uint32_t k = 0; k < d.scene_piece_count; k++) {
                auto it = sc.hidden_orders.find(sc.tap->pieces[d.scene_piece_first + k].object);
                if (it == sc.hidden_orders.end()) sc.hidden_orders[sc.tap->pieces[d.scene_piece_first + k].object] = order;
                else if (order < it->second) it->second = order;
            }
            return true;
        }
    }
    // the game's own ground shadows (a silhouette drawn into a small surface, then subtracted from the ground through a
    // quad the CPU projects) go when Godot throws real ones
    if (sc.shadows && d.tex_is_target && d.scene_kind == RTAG_SCENE_DEPTH && d.blend) { sc.blob_shadows_dropped++; return true; }
    const bool normals = d.scene_kind == RTAG_SCENE_EXACT && sc.tap->normals != nullptr;
    const int stride = normals ? 32 : 20;
    bool model = false;
    sc.kept_key = 0;
    sc.kept_mesh = RID();
    PackedByteArray positions, attributes;
    int corners = 0;
    if (normals && sc.packets && d.scene_piece_count && d.scene_piece_first + d.scene_piece_count <= sc.tap->piece_count) {
        // The packets' own geometry: every triangle of every strip drawn with this state - the list's triangles and the
        // ones the game's vertex programs dropped whole near the eye (Godot clips them as triangles should be clipped).
        const rtag_scene_piece* pieces = sc.tap->pieces + d.scene_piece_first;
        // a solid model: the cleaner look, and its skinned packets curved (PN triangles, see Scene::model_smooth)
        const bool dome_draw = index < sc.is_dome.size() && sc.is_dome[index];
        // the curve is the packet's, whatever the draw's state: a two-pass model's second pass (blended, no depth write)
        // must lie exactly on its first, or the two fight in the depth buffer (seen: a face in specks)
        const bool any_model = sc.model_look && pieces[0].kind == 2 && !dome_draw;
        model = any_model && d.depth_write && (!d.blend || d.alpha_test);
        int smooth = any_model && !sc.weld.empty() ? sc.model_smooth : 1;
        if (smooth > 1 && pieces[0].full_count && pieces[0].full_first < sc.tap->full_count) {
            // only near the eye: far away a figure is a few dozen pixels high and its curve costs what it does near
            const rtag_scene_full& v0 = sc.tap->full[pieces[0].full_first];
            if (Vector3(v0.x, v0.y, v0.z).distance_to(sc.camera.origin) > (real_t)sc.model_near) smooth = 1;
        }
        auto curved = [&](const rtag_scene_piece& piece) { return smooth > 1 && (piece.flags & 4) && piece.full_count % 3 == 0; };
        for (uint32_t k = 0; k < d.scene_piece_count; k++) corners += (int)pieces[k].full_count * (curved(pieces[k]) ? smooth * smooth : 1);
        if (model) sc.model_draws++;
        if (sc.keep) {
            // a figure over the packets as they are this frame: their identity, the colours the game lit them with and their
            // texels exactly, their positions to 1/16 unit (the tap takes them back through the camera of the frame, so they
            // differ in the last bits from frame to frame while the camera moves)
            uint64_t h[4] = {0x9E3779B97F4A7C15ull, 0xC2B2AE3D27D4EB4Full, 0x165667B19E3779F9ull, 0x27D4EB2F165667C5ull};
            auto mix = [](uint64_t& x, uint64_t w) { x = (x ^ w) * 0x100000001B3ull; x ^= x >> 29; };
            for (uint32_t k = 0; k < d.scene_piece_count; k++) {
                mix(h[0], pieces[k].mesh);
                mix(h[1], ((uint64_t)pieces[k].full_count << 32) | pieces[k].kind);
                const rtag_scene_full* v = sc.tap->full + pieces[k].full_first;
                for (uint32_t n = 0; n < pieces[k].full_count; n++, v++) {
                    uint32_t rgba, u, w;
                    memcpy(&rgba, &v->r, 4); memcpy(&u, &v->u, 4); memcpy(&w, &v->v, 4);
                    mix(h[0], ((uint64_t)u << 32) | rgba);
                    mix(h[1], ((uint64_t)w << 32) | (uint32_t)lrintf(v->z * 16.0f));
                    mix(h[2], ((uint64_t)(uint32_t)lrintf(v->x * 16.0f) << 32) | (uint32_t)lrintf(v->y * 16.0f));
                }
            }
            mix(h[3], (uint64_t)smooth * 0x51ED27u + (any_model ? 7 : 0));
            sc.kept_key = (h[0] ^ (h[1] * 3) ^ (h[2] * 5) ^ (h[3] * 7) ^ ((uint64_t)corners << 40)) | 1;
            uint64_t id = 0xA24BAED4963EE407ull ^ ((uint64_t)corners << 32) ^ (normals ? 1 : 0);
            for (uint32_t k = 0; k < d.scene_piece_count; k++) {
                mix(id, pieces[k].mesh);
                mix(id, ((uint64_t)pieces[k].full_count << 32) | pieces[k].kind);
            }
            uint32_t& seen = sc.kept_seen[id];
            mix(id, seen++);
            sc.kept_ident = id | 1;
            auto found = sc.kept.find(sc.kept_ident);
            if (found != sc.kept.end() && found->second.content == sc.kept_key && found->second.used != frames) {
                found->second.used = frames;
                sc.kept_hits++;
                sc.kept_corners += corners;
                sc.kept_mesh = found->second.mesh;
                sc.kept_box = found->second.box;
            }
        }
        if (!sc.kept_mesh.is_valid()) {
        positions.resize((int64_t)corners * 12);
        attributes.resize((int64_t)corners * stride);
        uint8_t* p = positions.ptrw();
        uint8_t* a = attributes.ptrw();
        for (uint32_t k = 0; k < d.scene_piece_count; k++) {
            const rtag_scene_full* v = sc.tap->full + pieces[k].full_first;
            if (curved(pieces[k])) {
                for (uint32_t n = 0; n < pieces[k].full_count; n += 3) {
                    const rtag_scene_full* c[3] = {v + n, v + n + 1, v + n + 2};
                    Vector3 wn[3];
                    for (int i = 0; i < 3; i++) {
                        auto w = sc.weld.find(weld_key(c[i]->x, c[i]->y, c[i]->z));
                        wn[i] = w != sc.weld.end() && w->second.length_squared() > 1e-8f ? w->second.normalized() : Vector3(c[i]->nx, c[i]->ny, c[i]->nz);
                    }
                    pn_triangle(c, wn, smooth, sc.model_crease, p, a);
                }
                sc.smoothed_corners += pieces[k].full_count * smooth * smooth;
                continue;
            }
            for (uint32_t n = 0; n < pieces[k].full_count; n++, v++, p += 12, a += stride) {
                memcpy(p, &v->x, 12);
                memcpy(a, &v->r, 4);
                float st[4] = {v->u, v->v, 1.0f, 1.0f};
                memcpy(a + 4, st, 16);
                memcpy(a + 20, &v->nx, 12);
            }
        }
        }
        if (smooth > 1) sc.smoothed_draws++;
        sc.packet_draws++;
        sc.packet_extra += corners - (int)d.count;
        if (pieces[0].kind == 1) sc.level_draws++;
        if (pieces[0].kind == 1) fill_learn(sc.tap, d, pieces, d.scene_piece_count, sc.camera.origin);
        else card_take(sc.tap, d, pieces, d.scene_piece_count);   // the character card (rta_card.cpp)
        // the painted light (see Scene::sun_sum): level chunks with a texture whose brightness is known
        if (pieces[0].kind == 1 && d.texture && d.depth_write && sc.sun_samples < 400000) {
            auto thumb = thumbs.find(d.texture);
            if (thumb != thumbs.end() && d.tex_size[0] > 0 && d.tex_size[1] > 0) {
                double sn[3] = {0, 0, 0}, sl = 0, sln[3] = {0, 0, 0};
                int count = 0;
                for (uint32_t k = 0; k < d.scene_piece_count; k++) {
                    const rtag_scene_full* v = sc.tap->full + pieces[k].full_first;
                    for (uint32_t n = 0; n < pieces[k].full_count; n += 5) {
                        const rtag_scene_full& q = v[n];
                        float tx = (q.u * d.st_scale[0] + d.tex_offset[0]) / d.tex_size[0], ty = (q.v * d.st_scale[1] + d.tex_offset[1]) / d.tex_size[1];
                        tx -= std::floor(tx); ty -= std::floor(ty);
                        float l = thumb->second.lum[std::min((int)(ty * THUMB), THUMB - 1) * THUMB + std::min((int)(tx * THUMB), THUMB - 1)] / 255.0f;
                        sn[0] += q.nx; sn[1] += q.ny; sn[2] += q.nz; sl += l;
                        sln[0] += l * q.nx; sln[1] += l * q.ny; sln[2] += l * q.nz;
                        count++;
                    }
                }
                if (count >= 24) {
                    for (int a = 0; a < 3; a++) sc.sun_sum[a] += sln[a] - sl * sn[a] / count;
                    sc.sun_weight += count;
                    sc.sun_samples += count;
                }
            }
        }
    } else {
        corners = (int)d.count;
        positions.resize((int64_t)d.count * 12);
        attributes.resize((int64_t)d.count * stride);
        uint8_t* p = positions.ptrw();
        uint8_t* a = attributes.ptrw();
        const rtag_vertex* v = f.vertices + d.first;
        const rtag_scene_vertex* w = sc.tap->vertices + d.scene_first;
        const float* n = normals ? sc.tap->normals + (size_t)d.scene_first * 3 : nullptr;
        for (uint32_t k = 0; k < d.count; k++, v++, w++, p += 12, a += stride) {
            memcpy(p, &w->x, 12);
            memcpy(a, &v->r, 4);
            float st[4] = {v->s, v->t, v->q, (float)v->fog / 255.0f};
            memcpy(a + 4, st, 16);
            if (normals) memcpy(a + 20, n + (size_t)k * 3, 12);
        }
    }
    if (!corners) return true;
    if (d.depth_write) fill_note_level(order);              // the level begins: the fill is drawn right before it
    // the mesh's real box: Godot pairs its lights with what they reach, and culls the shadow casters by it
    AABB box;
    RID mesh;
    if (sc.kept_mesh.is_valid()) {
        box = sc.kept_box;
        mesh = sc.kept_mesh;
    } else {
        const float* q = (const float*)positions.ptr();
        float lo[3] = {q[0], q[1], q[2]}, hi[3] = {q[0], q[1], q[2]};
        for (int k = 1; k < corners; k++)
            for (int a = 0; a < 3; a++) { float v = q[k * 3 + a]; lo[a] = std::min(lo[a], v); hi[a] = std::max(hi[a], v); }
        box = AABB(Vector3(lo[0], lo[1], lo[2]), Vector3(hi[0] - lo[0] + 0.01f, hi[1] - lo[1] + 0.01f, hi[2] - lo[2] + 0.01f));
        if (sc.kept_key) {
            auto slot = sc.kept.find(sc.kept_ident);
            if (slot != sc.kept.end() && slot->second.corners == corners && slot->second.normals == normals && slot->second.used != frames) {
                // the same draw, changed: its buffers are written again where they are
                mesh = slot->second.mesh;
                s->mesh_surface_update_vertex_region(mesh, 0, 0, positions);
                s->mesh_surface_update_attribute_region(mesh, 0, 0, attributes);
                s->mesh_set_custom_aabb(mesh, box);
                slot->second.box = box; slot->second.used = frames; slot->second.content = sc.kept_key;
                sc.kept_updates++;
            } else {
                if (slot != sc.kept.end()) s->free_rid(slot->second.mesh);
                mesh = s->mesh_create();
                add_surface_bytes(mesh, RenderingServer::PRIMITIVE_TRIANGLES, positions, attributes, corners, normals, &box);
                sc.kept[sc.kept_ident] = {mesh, box, frames, sc.kept_key, corners, normals};
                sc.kept_misses++;
            }
        } else {
            mesh = mesh_for(pass);
            add_surface_bytes(mesh, RenderingServer::PRIMITIVE_TRIANGLES, positions, attributes, corners, normals, &box);
        }
    }
    // the level under the player's feet (scene_view.gd's backdrop, for a level that has none there)
    // (any solid draw that is not a model's: the level is drawn in packets, and in places through the CPU's own projection)
    if (d.depth_write && !(d.scene_piece_count && sc.tap->pieces[d.scene_piece_first].kind == 2)) {
        const Vector3 lo = box.position, hi = box.position + box.size;
        if (sc.feet.x > lo.x - 60 && sc.feet.x < hi.x + 60 && sc.feet.y > lo.y - 60 && sc.feet.y < hi.y + 60 && sc.feet.z > lo.z - 80 && sc.feet.z < hi.z + 400)
            sc.ground_near++;
    }
    // Godot's light falls on what is solid (writes depth); glows, the dome, decals and what else is laid over the scene
    // keep the game's colours.  The dome is not hazed; camera-facing sprites fade as they come up to the eye.
    const bool is_dome = index < sc.is_dome.size() && sc.is_dome[index];
    const bool sprite = (d.made_by == 2 && d.scene_kind == RTAG_SCENE_DEPTH) ||
                        // ... and the level's cut-out cards (foliage): alpha-tested chunks, thinned out near the eye
                        (sc.near_fade && normals && d.alpha_test && d.depth_write && d.scene_piece_count && sc.tap->pieces[d.scene_piece_first].kind == 1);
    if (sprite) sc.near_faded++;
    // the level's solid pieces take the contact shadows of the figures standing on them
    const bool ground = sc.contacts_on && normals && d.depth_write && !is_dome && d.scene_piece_count && sc.tap->pieces[d.scene_piece_first].kind == 1;
    uint32_t extra = V_WORLD | (sc.lit && d.depth_write ? V_LIT : 0) | (normals ? V_NORMALS : 0) | (is_dome ? V_NOFOG : 0) | (sprite ? V_NEARFADE : 0) |
                     (model ? V_MODEL : 0) | (ground ? V_CONTACT : 0);
    if (normals) sc.exact_draws++;
    if (sc.kept_key) place_mesh(pass, mesh, material_for(d, target, false, texture, false, extra), order);
    else place(pass, material_for(d, target, false, texture, false, extra), order);
    // what is opaque also throws a shadow: a twin of the same mesh that Godot only draws into its shadow maps
    if (sc.shadows && d.depth_write && (!d.blend || d.alpha_test)) {
        RID caster;
        if (sc.caster_scenario != pass.scenario) {          // the surface was made again: instances of the old scenario are gone with it
            for (RID old : sc.casters) s->free_rid(old);
            sc.casters.clear();
            sc.caster_scenario = pass.scenario;
        }
        if (sc.casters_used < sc.casters.size()) caster = sc.casters[sc.casters_used];
        else {
            caster = s->instance_create();
            s->instance_set_scenario(caster, pass.scenario);
            s->instance_geometry_set_cast_shadows_setting(caster, RenderingServer::SHADOW_CASTING_SETTING_SHADOWS_ONLY);
            sc.casters.push_back(caster);
        }
        sc.casters_used++;
        s->instance_set_base(caster, mesh);
        s->instance_geometry_set_material_override(caster, material_for(d, target, false, texture, false, V_WORLD | V_CASTER | (normals ? V_NORMALS : 0)));
    }
    sc.world_draws++;
    sc.world_vertices += d.count;
    draws_submitted++;
    vertices_submitted += d.count;
    return true;
}

void RtaDrawer::scene_end(const rtag_frame&) {
    Scene& sc = *scene;
    RenderingServer* s = RenderingServer::get_singleton();
    for (size_t k = sc.casters_used; k < sc.casters.size(); k++) s->instance_set_base(sc.casters[k], RID());
    fill_order();
    if (Target* world = world_target()) card_end(*world);
    // kept meshes nothing drew for half a second go
    if ((frames & 15) == 0)
        for (auto k = sc.kept.begin(); k != sc.kept.end();) {
            if (frames - k->second.used > 30) { s->free_rid(k->second.mesh); k = sc.kept.erase(k); }
            else ++k;
        }
}

void RtaDrawer::scene_release() {
    if (!scene) return;
    RenderingServer* s = RenderingServer::get_singleton();
    if (s) for (RID caster : scene->casters) s->free_rid(caster);
    if (s) for (auto& k : scene->kept) s->free_rid(k.second.mesh);
    delete scene;
    scene = nullptr;
}

}  // namespace godot
