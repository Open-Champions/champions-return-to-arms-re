// rta_fill.cpp - RtaDrawer's fill: the ceilings and skirts the library generates for a level (rtag_fill_get,
// tools/recomp/render/worldfill.h), drawn in the world of scene mode as if they were part of the level.
//
// What the library hands over is plain geometry: blocks of 128 x 128 units, a ceiling over the walked floor of a walled
// level (it meets each wall at the height of its lid and rises away from the walls), a skirt of ground beyond the outer
// rim; per vertex a position, a normal, world x, y / 64 for a tiling texture, and a grey level (ceilings: 255 at a wall,
// 150 at 200 units from it; skirts: alpha 128 at the rim, 0 at the outer edge).  None of it is the game's art.  Here:
//
//   material   each block takes a SWATCH: a small square cut out of the level's own texture where its wall meets the
//              ceiling (for a ceiling) or of the lid at the rim (for a skirt) - found in the scene tap's level chunks as
//              they are drawn (wall triangles whose top is within reach of the ceiling's lid; ground facing up beside the
//              rim), resampled to 64 x 64 with the vertex light of the triangles it was cut from.  A block takes the
//              swatch cut nearest to it; until the first one is cut, a plain dark stone made in the shader.  Swatches
//              are brought to one brightness so that neighbouring blocks with different swatches do not show as patches.
//   shading    shaders/fill.gdshader: the swatch tiled (mirrored, so it has no seams), darkened, a crease where the
//              ceiling meets the wall, darker toward the middle of a hall; the haze; Godot's point lights (the lamp,
//              the torches) on top.  The sun does not reach a ceiling (light layer 2: scene_view.gd keeps the sun off
//              it); a skirt is lit like the ground.  Neither throws a shadow (they are drawn in the transparent pass
//              with the list's draws, which does not cast).
//   order      in the list's order, right before the first piece of the level (after the game's sky, its dome and the
//              clearing rectangle; a skirt before a ceiling), depth tested and written like the level.
//   visibility as the OpenGL program has it (render/gs.cpp, Gs::draw_fill): a ceiling block only when the eye is under
//              its top, and a ceiling seen from below only - a camera that has got above a lid looks through it.
//
// Options (set_scene_option): fill 0|1 (drawn at all: scene_view.gd's look switch), fill_ceilings, fill_skirts 0|1,
// fill_light (how much of the swatch's brightness a ceiling keeps, default 0.42), fill_scale (swatch repeats per 64
// units, default 0.75).
#include "rta_drawer.h"

#include <godot_cpp/classes/image.hpp>
#include <godot_cpp/classes/rendering_server.hpp>
#include <godot_cpp/variant/aabb.hpp>
#include <godot_cpp/variant/color.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/utility_functions.hpp>

#include <algorithm>
#include <cmath>
#include <cstring>

namespace godot {

namespace {
RenderingServer* rs() { return RenderingServer::get_singleton(); }
enum { SWATCH = 64, GRID = 32, MAX_SWATCHES = 40 };
const uint32_t CEILING_LAYER = 2;       // scene_view.gd keeps the sun off this layer
}  // namespace

struct RtaDrawer::Fill {
    struct Block {
        RID mesh, instance;
        uint8_t kind = 0;
        float bounds[6];
        float cx = 0, cy = 0;
        int swatch = -1;                // index into swatches, -1: the shader's own stone
        bool visible = false;
    };
    struct Swatch {
        uint8_t kind = 0;
        float x = 0, y = 0, z = 0;
        float lum = 0;                  // its mean brightness, 0..1
        RID texture, material;
    };
    struct Cell { float ceiling = 1e9f; bool skirt = false; };
    // the level's fill as built
    uint64_t serial = 0;
    std::string level;
    std::vector<Block> blocks;
    std::vector<Swatch> swatches;
    std::vector<Cell> grid;
    int gx0 = 0, gy0 = 0, gw = 0, gh = 0;
    bool any_ceiling = false, any_skirt = false;
    RID stone[3];                       // the materials without a swatch, by kind
    RID blocks_scenario;
    float level_order = -1, order_set = -1e9f;
    size_t next_assign = 0;
    bool assign_all = false;
    int learn_budget = 0;
    // switches
    bool on = false, ceilings = true, skirts = true;
    double light = 0.42, scale = 0.75;
    bool params_dirty = true;
    Ref<Shader> shader;
    // figures
    uint64_t frames = 0, blocks_drawn = 0, tried = 0, cut = 0, builds = 0, library_dropped = 0;

    Cell* cell(float x, float y) {
        int cx = (int)std::floor(x / GRID) - gx0, cy = (int)std::floor(y / GRID) - gy0;
        if (cx < 0 || cy < 0 || cx >= gw || cy >= gh) return nullptr;
        return &grid[(size_t)cy * gw + cx];
    }
};

void RtaDrawer::set_fill_shader(const Ref<Shader>& shader) {
    if (!fill) fill = new Fill;
    fill->shader = shader;
}

Dictionary RtaDrawer::get_fill_info() const {
    Dictionary d;
    if (!fill) return d;
    const Fill& fl = *fill;
    int ceilings = 0, skirts = 0, sc = 0, ss = 0;
    for (const auto& b : fl.blocks) (b.kind == RTAG_FILL_CEILING ? ceilings : skirts)++;
    for (const auto& s : fl.swatches) (s.kind == RTAG_FILL_CEILING ? sc : ss)++;
    d["level"] = String(fl.level.c_str());
    d["on"] = fl.on;
    d["blocks"] = (int64_t)fl.blocks.size();
    d["ceiling_blocks"] = ceilings;
    d["skirt_blocks"] = skirts;
    d["ceiling_swatches"] = sc;
    d["skirt_swatches"] = ss;
    double n = fl.frames ? (double)fl.frames : 1;
    d["figures"] = vformat("fill: level %s, %d blocks (%d ceiling, %d skirt), %.1f drawn a frame over %d frames; swatches cut %d (%d for ceilings, %d for skirts) of %d "
                           "looked at; %d builds; the library's own fill draws left out: %.2f a frame",
                           String(fl.level.c_str()), (int64_t)fl.blocks.size(), ceilings, skirts, fl.blocks_drawn / n, (int64_t)fl.frames, (int64_t)fl.cut, sc, ss,
                           (int64_t)fl.tried, (int64_t)fl.builds, fl.library_dropped / n);
    return d;
}

void RtaDrawer::fill_release() {
    if (!fill) return;
    RenderingServer* s = rs();
    if (s) {
        for (auto& b : fill->blocks) { s->free_rid(b.instance); s->free_rid(b.mesh); }
        for (auto& w : fill->swatches) { s->free_rid(w.material); s->free_rid(w.texture); }
        for (RID& m : fill->stone) if (m.is_valid()) s->free_rid(m);
    }
    fill->blocks.clear();
    fill->swatches.clear();
    for (RID& m : fill->stone) m = RID();
}

// A material of the fill shader: for a swatch, or (swatch < 0) the plain stone.
RID RtaDrawer::fill_material(Fill& fl, uint8_t kind, RID texture) {
    RenderingServer* s = rs();
    RID m = s->material_create();
    s->material_set_shader(m, fl.shader->get_rid());
    s->material_set_param(m, "kind", (int)kind);
    s->material_set_param(m, "has_swatch", texture.is_valid() ? 1 : 0);
    if (texture.is_valid()) s->material_set_param(m, "swatch", texture);
    return m;
}

void RtaDrawer::fill_params(Fill& fl) {
    // every swatch is brought to the mean brightness of those of its kind, so that a block next to one with another
    // swatch does not stand out
    RenderingServer* s = rs();
    double sum[3] = {0, 0, 0};
    int n[3] = {0, 0, 0};
    for (const auto& w : fl.swatches) { sum[w.kind] += w.lum; n[w.kind]++; }
    for (const auto& w : fl.swatches) {
        float target = (float)(sum[w.kind] / std::max(n[w.kind], 1));
        float gain = w.lum > 0.01f ? std::min(target / w.lum, 2.5f) : 1.0f;
        s->material_set_param(w.material, "gain", gain);
        s->material_set_param(w.material, "light", (float)fl.light);
        s->material_set_param(w.material, "scale", (float)fl.scale);
    }
    for (RID m : fl.stone)
        if (m.is_valid()) { s->material_set_param(m, "light", (float)fl.light); s->material_set_param(m, "scale", (float)fl.scale); }
    fl.params_dirty = false;
}

// The level's fill, made into Godot meshes: one mesh and one instance a block, in the world's scenario.
void RtaDrawer::fill_build(const rtag_fill& f, RID scenario) {
    Fill& fl = *fill;
    RenderingServer* s = rs();
    const std::string level = f.level ? f.level : "";
    for (auto& b : fl.blocks) { s->free_rid(b.instance); s->free_rid(b.mesh); }
    fl.blocks.clear();
    if (level != fl.level) {            // another level: what was cut of the last one goes
        for (auto& w : fl.swatches) { s->free_rid(w.material); s->free_rid(w.texture); }
        fl.swatches.clear();
    }
    fl.level = level;
    fl.serial = f.serial;
    fl.builds++;
    for (int k = 1; k <= 2; k++)
        if (!fl.stone[k].is_valid()) fl.stone[k] = fill_material(fl, (uint8_t)k, RID());
    // the grid: where a ceiling is and how low, where a skirt begins (to know which of the level's triangles a swatch
    // may be cut from)
    float x0 = f.bounds[0], y0 = f.bounds[1], x1 = f.bounds[3], y1 = f.bounds[4];
    fl.gx0 = (int)std::floor(x0 / GRID) - 1; fl.gy0 = (int)std::floor(y0 / GRID) - 1;
    fl.gw = std::max(1, (int)std::floor(x1 / GRID) - fl.gx0 + 2); fl.gh = std::max(1, (int)std::floor(y1 / GRID) - fl.gy0 + 2);
    if ((size_t)fl.gw * fl.gh > 4000000) { fl.gw = fl.gh = 0; }
    fl.grid.assign((size_t)fl.gw * fl.gh, Fill::Cell());
    fl.any_ceiling = fl.any_skirt = false;
    for (uint32_t k = 0; k < f.mesh_count; k++) {
        const rtag_fill_mesh& m = f.meshes[k];
        if (!m.count || m.first + m.count > f.vertex_count) continue;
        Fill::Block b;
        b.kind = m.kind;
        memcpy(b.bounds, m.bounds, sizeof b.bounds);
        b.cx = (m.bounds[0] + m.bounds[3]) * 0.5f; b.cy = (m.bounds[1] + m.bounds[4]) * 0.5f;
        PackedByteArray positions, attributes;
        positions.resize((int64_t)m.count * 12);
        attributes.resize((int64_t)m.count * 32);
        uint8_t* p = positions.ptrw();
        uint8_t* a = attributes.ptrw();
        for (uint32_t n = 0; n < m.count; n++, p += 12, a += 32) {
            const rtag_fill_vertex& v = f.vertices[m.first + n];
            memcpy(p, v.position, 12);
            memcpy(a, v.rgba, 4);
            float custom[4] = {v.uv[0], v.uv[1], v.rgba[0] / 255.0f, std::min(v.rgba[3] / 128.0f, 1.0f)};
            memcpy(a + 4, custom, 16);
            memcpy(a + 20, v.normal, 12);
            if (Fill::Cell* c = fl.cell(v.position[0], v.position[1])) {
                if (m.kind == RTAG_FILL_CEILING) c->ceiling = std::min(c->ceiling, v.position[2]);
                else if (v.rgba[3] >= 96) c->skirt = true;
            }
        }
        (m.kind == RTAG_FILL_CEILING ? fl.any_ceiling : fl.any_skirt) = true;
        Dictionary surface;
        surface["primitive"] = RenderingServer::PRIMITIVE_TRIANGLES;
        surface["format"] = (int64_t)(RenderingServer::ARRAY_FORMAT_VERTEX | RenderingServer::ARRAY_FORMAT_COLOR | RenderingServer::ARRAY_FORMAT_CUSTOM0 |
                                      ((int64_t)RenderingServer::ARRAY_CUSTOM_RGBA_FLOAT << RenderingServer::ARRAY_FORMAT_CUSTOM0_SHIFT) |
                                      RenderingServer::ARRAY_FORMAT_CUSTOM1 | ((int64_t)RenderingServer::ARRAY_CUSTOM_RGB_FLOAT << RenderingServer::ARRAY_FORMAT_CUSTOM1_SHIFT) |
                                      RenderingServer::ARRAY_FLAG_FORMAT_CURRENT_VERSION);
        surface["vertex_data"] = positions;
        surface["attribute_data"] = attributes;
        surface["vertex_count"] = (int64_t)m.count;
        AABB box(Vector3(m.bounds[0], m.bounds[1], m.bounds[2]), Vector3(m.bounds[3] - m.bounds[0], m.bounds[4] - m.bounds[1], m.bounds[5] - m.bounds[2] + 1.0f));
        surface["aabb"] = box;
        b.mesh = s->mesh_create();
        s->mesh_add_surface(b.mesh, surface);
        b.instance = s->instance_create2(b.mesh, scenario);
        s->instance_geometry_set_cast_shadows_setting(b.instance, RenderingServer::SHADOW_CASTING_SETTING_OFF);
        if (m.kind == RTAG_FILL_CEILING) s->instance_set_layer_mask(b.instance, CEILING_LAYER);
        s->instance_geometry_set_material_override(b.instance, fl.stone[m.kind == RTAG_FILL_CEILING ? 1 : 2]);
        s->instance_set_visible(b.instance, false);
        fl.blocks.push_back(b);
    }
    fl.order_set = -1e9f;
    fl.assign_all = true;
    fl.params_dirty = true;
}

// Once a frame, with the camera known: the level's fill (made again when it changed), which blocks are drawn, which
// swatch each takes.
void RtaDrawer::fill_frame(const rtag_frame& f, const Vector3& eye, RID scenario) {
    if (!fill || fill->shader.is_null()) return;
    Fill& fl = *fill;
    RenderingServer* s = rs();
    fl.level_order = -1;
    fl.learn_budget = fl.on ? 1 : 0;    // one swatch at most a frame
    rtag_fill info;
    bool have = machine.is_valid() && machine->fill(info);
    if (!have) {
        if (!fl.blocks.empty()) { for (auto& b : fl.blocks) { s->free_rid(b.instance); s->free_rid(b.mesh); } fl.blocks.clear(); fl.serial = 0; }
        return;
    }
    if (info.serial != fl.serial || fl.blocks.empty() || (!fl.blocks.empty() && fl.blocks_scenario != scenario)) {
        fill_build(info, scenario);
        fl.blocks_scenario = scenario;
    }
    if (fl.params_dirty) fill_params(fl);
    fl.frames++;
    // which blocks are drawn
    for (auto& b : fl.blocks) {
        bool want = fl.on && (b.kind == RTAG_FILL_CEILING ? fl.ceilings && eye.z <= b.bounds[5] + 2.0f : fl.skirts);
        if (want != b.visible) { s->instance_set_visible(b.instance, want); b.visible = want; }
        if (want) fl.blocks_drawn++;
    }
    // which swatch each takes: the nearest of its kind (a few blocks a frame; all of them when a level's first swatch is cut)
    if (fl.swatches.empty() || fl.blocks.empty()) return;
    size_t count = fl.assign_all ? fl.blocks.size() : std::min<size_t>(fl.blocks.size(), 48);
    fl.assign_all = false;
    for (size_t n = 0; n < count; n++) {
        Fill::Block& b = fl.blocks[fl.next_assign++ % fl.blocks.size()];
        int best = -1;
        float best_d = 1e30f;
        for (size_t k = 0; k < fl.swatches.size(); k++) {
            const Fill::Swatch& w = fl.swatches[k];
            if (w.kind != b.kind) continue;
            float dx = w.x - b.cx, dy = w.y - b.cy, d = dx * dx + dy * dy;
            if (d < best_d) { best_d = d; best = (int)k; }
        }
        if (best >= 0 && best != b.swatch) {
            b.swatch = best;
            s->instance_geometry_set_material_override(b.instance, fl.swatches[best].material);
        }
    }
}

// A level chunk drawn this frame (scene_take): perhaps a swatch is cut from it.
void RtaDrawer::fill_learn(const rtag_scene* tap, const rtag_draw& d, const rtag_scene_piece* pieces, uint32_t piece_count, const Vector3& eye) {
    if (!fill || fill->learn_budget <= 0 || fill->blocks.empty() || fill->gw == 0) return;
    Fill& fl = *fill;
    if ((int)fl.swatches.size() >= MAX_SWATCHES) return;
    if (!d.texture || d.alpha_test || d.blend || !d.depth_write || d.tex_size[0] <= 0 || d.tex_size[1] <= 0) return;
    auto cpu = cpu_textures.find(d.texture);
    if (cpu == cpu_textures.end() || cpu->second.w < 8 || cpu->second.h < 8) return;
    const rtag_scene_full* first = tap->full + pieces[0].full_first;
    if (!pieces[0].full_count) return;
    // cheap tests first: near the eye (its texture is the one the chunk has now), and no swatch of that kind near it
    float fx = first->x - eye.x, fy = first->y - eye.y;
    if (fx * fx + fy * fy > 700.0f * 700.0f) return;
    bool want_ceiling = fl.any_ceiling && fl.ceilings, want_skirt = fl.any_skirt && fl.skirts;
    for (const auto& w : fl.swatches) {
        float dx = w.x - first->x, dy = w.y - first->y, dd = dx * dx + dy * dy;
        if (w.kind == RTAG_FILL_CEILING && dd < 300.0f * 300.0f) want_ceiling = false;
        if (w.kind == RTAG_FILL_SKIRT && dd < 420.0f * 420.0f) want_skirt = false;
    }
    if (!want_ceiling && !want_skirt) return;
    fl.learn_budget--;
    fl.tried++;
    // the triangles: walls (normal level with the ground) whose top is the ceiling's lid, and ground (normal up) at the rim
    std::vector<const rtag_scene_full*> walls, ground;
    float wall_top = -1e9f;
    for (uint32_t k = 0; k < piece_count; k++) {
        const rtag_scene_full* v = tap->full + pieces[k].full_first;
        for (uint32_t n = 0; n + 2 < pieces[k].full_count; n += 3) {
            float nz = (v[n].nz + v[n + 1].nz + v[n + 2].nz) / 3.0f;
            float cx = (v[n].x + v[n + 1].x + v[n + 2].x) / 3.0f, cy = (v[n].y + v[n + 1].y + v[n + 2].y) / 3.0f;
            float top = std::max(v[n].z, std::max(v[n + 1].z, v[n + 2].z));
            if (want_ceiling && std::fabs(nz) < 0.35f) {
                float ceiling = 1e9f;
                for (int oy = -1; oy <= 1; oy++)
                    for (int ox = -1; ox <= 1; ox++)
                        if (Fill::Cell* o = fl.cell(cx + ox * GRID, cy + oy * GRID)) ceiling = std::min(ceiling, o->ceiling);
                if (ceiling < 1e8f && top > ceiling - 70.0f && top < ceiling + 30.0f) { walls.push_back(v + n); wall_top = std::max(wall_top, top); }
            } else if (want_skirt && nz > 0.85f) {
                bool rim = false;
                for (int oy = -2; oy <= 2 && !rim; oy++)
                    for (int ox = -2; ox <= 2 && !rim; ox++)
                        if (Fill::Cell* o = fl.cell(cx + ox * GRID, cy + oy * GRID)) rim = o->skirt;
                if (rim) ground.push_back(v + n);
            }
        }
    }
    uint8_t kind = 0;
    std::vector<const rtag_scene_full*>* tris = nullptr;
    if (walls.size() >= 2) {
        // the upper part of the wall: what meets the ceiling
        std::vector<const rtag_scene_full*> upper;
        for (auto t : walls) if ((t[0].z + t[1].z + t[2].z) / 3.0f > wall_top - 56.0f) upper.push_back(t);
        walls.swap(upper);
        if (walls.size() >= 2) { kind = RTAG_FILL_CEILING; tris = &walls; }
    }
    if (!kind && ground.size() >= 2) { kind = RTAG_FILL_SKIRT; tris = &ground; }
    if (!kind) return;
    // where they lie in the texture (as gs_draw.gdshaderinc maps it: (uv x st_scale + tex_offset) / tex_size)
    double u0 = 1e9, v0 = 1e9, u1 = -1e9, v1 = -1e9, sx = 0, sy = 0, sz = 0, col[3] = {0, 0, 0};
    int corners = 0;
    for (auto t : *tris)
        for (int c = 0; c < 3; c++) {
            const rtag_scene_full& q = t[c];
            double u = (q.u * d.st_scale[0] + d.tex_offset[0]) / d.tex_size[0], v = (q.v * d.st_scale[1] + d.tex_offset[1]) / d.tex_size[1];
            u0 = std::min(u0, u); u1 = std::max(u1, u); v0 = std::min(v0, v); v1 = std::max(v1, v);
            sx += q.x; sy += q.y; sz += q.z;
            col[0] += q.r; col[1] += q.g; col[2] += q.b;
            corners++;
        }
    if (u1 - u0 >= 1.0) { u0 = 0; u1 = 1; } else { double k = std::floor(u0); u0 -= k; u1 = std::min(u1 - k, 1.0); }
    if (v1 - v0 >= 1.0) { v0 = 0; v1 = 1; } else { double k = std::floor(v0); v0 -= k; v1 = std::min(v1 - k, 1.0); }
    const CpuTexture& tex = cpu->second;
    if ((u1 - u0) * tex.w < 6 || (v1 - v0) * tex.h < 6) return;
    // the vertex light the triangles were drawn with (modulate: 0x80 = 1.0)
    float light[3] = {1, 1, 1};
    if (d.tfx != 1)
        for (int ch = 0; ch < 3; ch++) light[ch] = (float)std::min(col[ch] / corners / 128.0, 2.0);
    PackedByteArray bytes;
    bytes.resize(SWATCH * SWATCH * 4);
    uint8_t* out = bytes.ptrw();
    double lum = 0;
    for (int y = 0; y < SWATCH; y++)
        for (int x = 0; x < SWATCH; x++) {
            double tx = (u0 + (u1 - u0) * (x + 0.5) / SWATCH) * tex.w - 0.5, ty = (v0 + (v1 - v0) * (y + 0.5) / SWATCH) * tex.h - 0.5;
            int ix = (int)std::floor(tx), iy = (int)std::floor(ty);
            double ax = tx - ix, ay = ty - iy;
            float c[3] = {0, 0, 0};
            for (int k = 0; k < 4; k++) {
                int px = std::min(std::max(ix + (k & 1), 0), tex.w - 1), py = std::min(std::max(iy + (k >> 1), 0), tex.h - 1);
                double wgt = ((k & 1) ? ax : 1 - ax) * ((k >> 1) ? ay : 1 - ay);
                const uint8_t* p = &tex.rgba[((size_t)py * tex.w + px) * 4];
                for (int ch = 0; ch < 3; ch++) c[ch] += (float)(p[ch] * wgt);
            }
            uint8_t* o = out + ((size_t)y * SWATCH + x) * 4;
            for (int ch = 0; ch < 3; ch++) o[ch] = (uint8_t)std::min(std::max(c[ch] * light[ch], 0.0f), 255.0f);
            o[3] = 255;
            lum += (o[0] * 0.30 + o[1] * 0.59 + o[2] * 0.11) / 255.0;
        }
    lum /= SWATCH * SWATCH;
    if (lum < 0.015) return;            // black: nothing to learn from
    Ref<Image> image = Image::create_from_data(SWATCH, SWATCH, false, Image::FORMAT_RGBA8, bytes);
    image->generate_mipmaps();
    Fill::Swatch w;
    w.kind = kind;
    w.x = (float)(sx / corners); w.y = (float)(sy / corners); w.z = (float)(sz / corners);
    w.lum = (float)lum;
    w.texture = rs()->texture_2d_create(image);
    w.material = fill_material(fl, kind, w.texture);
    fl.swatches.push_back(w);
    fl.cut++;
    fl.params_dirty = true;
    bool first_of_kind = true;
    for (size_t k = 0; k + 1 < fl.swatches.size(); k++) if (fl.swatches[k].kind == kind) first_of_kind = false;
    if (first_of_kind) fl.assign_all = true;
    fl.order_set = -1e9f;
}

// After the list's draws: the fill goes right before the first piece of the level.
void RtaDrawer::fill_order() {
    if (!fill || fill->blocks.empty()) return;
    Fill& fl = *fill;
    float at = fl.level_order >= 0 ? fl.level_order : 0.0f;
    if (at == fl.order_set) return;
    fl.order_set = at;
    RenderingServer* s = rs();
    for (auto& b : fl.blocks) s->instance_set_pivot_data(b.instance, at - (b.kind == RTAG_FILL_SKIRT ? 0.7f : 0.5f), false);
}

void RtaDrawer::fill_option(const String& name, double value) {
    if (!fill) fill = new Fill;
    Fill& fl = *fill;
    if (name == "fill") fl.on = value != 0;
    else if (name == "fill_ceilings") fl.ceilings = value != 0;
    else if (name == "fill_skirts") fl.skirts = value != 0;
    else if (name == "fill_light") { fl.light = value; fl.params_dirty = true; }
    else if (name == "fill_scale") { fl.scale = value; fl.params_dirty = true; }
}

// The library's own fill in the list: with the world work on, the game side has the GS draw the fill plainly into the
// list as well (render/gs.cpp, Gs::draw_fill: untextured, depth written, a ceiling grey x 0.10 slightly warm - g = 0.92 r,
// b = 0.85 r - and a skirt in one colour with a falling alpha), which the scene receives by its depth.  While this
// drawer draws the fill itself, those draws are left out.
bool RtaDrawer::fill_drops(const rtag_frame& f, const rtag_draw& d) {
    if (!fill || !fill->on || fill->blocks.empty()) return false;
    if (d.texture || d.made_by != 0 || d.scene_kind != RTAG_SCENE_DEPTH || !d.depth_write || d.prim != RTAG_TRIANGLES || d.count < 3) return false;
    if (d.first + d.count > f.vertex_count) return false;
    const rtag_vertex* v = f.vertices + d.first;
    const uint32_t step = std::max<uint32_t>(1, d.count / 16);
    bool ceiling = !d.blend, skirt = d.blend && d.ba == 0 && d.bb == 1 && d.bc == 0 && d.bd == 1;
    for (uint32_t k = 0; k < d.count && (ceiling || skirt); k += step) {
        const rtag_vertex& q = v[k];
        if (ceiling && (q.r > 70 || q.a != 128 || std::fabs(q.g - q.r * 0.92f) > 1.6f || std::fabs(q.b - q.r * 0.85f) > 1.6f)) ceiling = false;
        if (skirt && (q.r != v[0].r || q.g != v[0].g || q.b != v[0].b || q.a > 128)) skirt = false;
    }
    if (!ceiling && !skirt) return false;
    fill->library_dropped++;
    return true;
}

void RtaDrawer::fill_note_level(float order) {
    if (fill && fill->level_order < 0) fill->level_order = order;
}

void RtaDrawer::fill_free() {
    fill_release();
    delete fill;
    fill = nullptr;
}

}  // namespace godot
