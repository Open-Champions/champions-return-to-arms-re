// rta_world.cpp - the Elden Ring world layer of the drawer (look.er_world; project/er_world.gd): what each piece of the level
// is made of, read from its texture, and where grass grows on it.
//
// The game's levels are lit in their textures: every placed chunk has its own pre-lit texture (docs/formats/world.md), so a
// texture is a piece of ground, a wall, a floor as it looks under the level's light.  What it is made of is read from its
// texels (world_classify, when the texture first arrives): each texel's colour is given a membership of the material
// families (grass, dirt, sand, snow, stone) by its hue, saturation and brightness - the shader computes the same per pixel
// (shaders/er_world.gdshaderinc, er_member) - and the texture as a whole adds what only a whole texture shows: an even
// mesh of strong edges reads as cobbles or flagstones, edges all along one direction as boards (wood).  The texture's class
// is its strongest family (er_class); a second one that covers enough of it (a path through grass) is er_class_b, and the
// shader decides between the two per pixel.  The host's table (set_world_layer: by texture name, or a whole class remapped
// for the level) is put over what was read.
//
// Classes: 1 grass, 2 dirt, 3 stone, 4 cobble, 5 wood, 6 metal, 7 sand, 8 snow (0: none - the texture stays as it is).
//
// Grass (get_grass): the level's pieces whose texture reads as grass are scattered with points, once per piece (the level's
// chunks are in world coordinates and do not move): on triangles that face up, as many as their area asks for, each kept
// only where the texel under it reads as grass itself (a path painted through the grass stays bare); and every piece's
// walls are written into a grid of cells, so that no grass grows against a wall.  The host draws the points (MultiMesh).
// Nothing here changes what the game computes.
#include "rta_drawer.h"
#include "rta_variant.h"

#include <godot_cpp/variant/utility_functions.hpp>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>

using namespace godot;
using namespace rta_variant;

namespace {

enum { C_NONE = 0, C_GRASS = 1, C_DIRT = 2, C_STONE = 3, C_COBBLE = 4, C_WOOD = 5, C_METAL = 6, C_SAND = 7, C_SNOW = 8, C_COUNT = 9 };
const char* const CLASS_NAMES[C_COUNT] = {"none", "grass", "dirt", "stone", "cobble", "wood", "metal", "sand", "snow"};

float smooth(float a, float b, float x) {
    float t = std::min(1.0f, std::max(0.0f, (x - a) / (b - a)));
    return t * t * (3.0f - 2.0f * t);
}

// inside the hue band [lo, hi] (degrees), with soft edges `soft` wide
float band(float h, float lo, float hi, float soft) {
    return smooth(lo - soft, lo, h) * (1.0f - smooth(hi, hi + soft, h));
}

// where grass's band of hues starts (degrees; the host's table: "grass_hue", per level)
float grass_hue = 64.0f;

// the membership of one colour (0..1, stored values) in the five families - as er_member in shaders/er_world.gdshaderinc
void member(float r, float g, float b, float m[C_COUNT]) {
    const float mx = std::max(r, std::max(g, b)), mn = std::min(r, std::min(g, b));
    const float lum = 0.3f * r + 0.59f * g + 0.11f * b;
    const float sat = (mx - mn) / std::max(mx, 0.04f);
    float h = 0;
    if (mx - mn > 1e-4f) {
        if (mx == r) h = 60.0f * std::fmod((g - b) / (mx - mn) + 6.0f, 6.0f);
        else if (mx == g) h = 60.0f * ((b - r) / (mx - mn) + 2.0f);
        else h = 60.0f * ((r - g) / (mx - mn) + 4.0f);
    }
    for (int k = 0; k < C_COUNT; k++) m[k] = 0;
    const float coloured = smooth(0.06f, 0.16f, sat);
    m[C_GRASS] = band(h, grass_hue, 170, 16) * smooth(0.08f, 0.18f, sat);
    m[C_SAND] = band(h, 26, 58, 10) * coloured * (1.0f - smooth(0.55f, 0.75f, sat)) * smooth(0.42f, 0.56f, lum);
    m[C_DIRT] = band(h, 6, 56, 10) * coloured * (1.0f - m[C_SAND]);
    m[C_SNOW] = smooth(0.62f, 0.78f, lum) * (1.0f - smooth(0.10f, 0.22f, sat));
    m[C_STONE] = (1.0f - coloured) * (1.0f - m[C_SNOW]);
}

int class_of_name(const String& s) {
    for (int k = 0; k < C_COUNT; k++)
        if (s == CLASS_NAMES[k]) return k;
    return -1;
}

uint64_t mix64(uint64_t x) {
    x ^= x >> 33; x *= 0xff51afd7ed558ccdull; x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53ull; x ^= x >> 33;
    return x;
}

}  // namespace

// a texture as it arrives (scene mode): what it is made of
void RtaDrawer::world_classify(const rtag_texture& t, const rtag_texture_name* name) {
    WorldTex& w = world_tex[t.id];
    w = WorldTex();
    if (name && name->named) {
        char buf[48];
        snprintf(buf, sizeof buf, "%016llx-%016llx", (unsigned long long)name->figure, (unsigned long long)name->palette_figure);
        w.name = buf;
    }
    w.pending = true;           // read at its first draw of the level (world_scan): with the draw's own vertex light
}

// what a texture is made of: its texels as the draw shows them (times the mean colour of the game's vertex light on it:
// a level's chunks take much of their colour from it)
void RtaDrawer::world_read(uint32_t id, const float tint[3]) {
    auto wt = world_tex.find(id);
    if (wt == world_tex.end()) return;
    WorldTex& w = wt->second;
    w.pending = false;
    for (int k = 0; k < 3; k++) w.tint[k] = tint[k];
    auto ct = cpu_textures.find(id);
    if (ct == cpu_textures.end()) return;
    struct { int width, height; const uint8_t* rgba; } t = {ct->second.w, ct->second.h, ct->second.rgba.data()};
    if (t.width < 8 || t.height < 8 || !t.rgba) return;
    // at most 64 x 64 texels looked at
    const int step_x = std::max(1, t.width / 64), step_y = std::max(1, t.height / 64);
    double sum[C_COUNT] = {0}, rgb[3] = {0, 0, 0}, edge = 0, edge_x = 0, edge_y = 0, lum_sum = 0;
    int n = 0, opaque = 0, high = 0, total = 0;
    // alpha: a texture whose texels all have a low alpha does not use it (a 24-bit texture, its alpha from TEXA, or a draw
    // that does not take the texture's alpha); one with some texels high and some low is cut out
    for (int y = 0; y + step_y < t.height; y += step_y)
        for (int x = 0; x + step_x < t.width; x += step_x) {
            total++;
            if (t.rgba[((size_t)y * t.width + x) * 4 + 3] >= 0x70) high++;
        }
    const bool alpha_used = high > 0;
    for (int y = 0; y + step_y < t.height; y += step_y)
        for (int x = 0; x + step_x < t.width; x += step_x) {
            const uint8_t* p = t.rgba + ((size_t)y * t.width + x) * 4;
            n++;
            if (alpha_used && p[3] < 0x70) continue;
            opaque++;
            const float r = std::min(1.0f, p[0] / 255.0f * tint[0]), g = std::min(1.0f, p[1] / 255.0f * tint[1]), b = std::min(1.0f, p[2] / 255.0f * tint[2]);
            float m[C_COUNT];
            member(r, g, b, m);
            for (int k = 0; k < C_COUNT; k++) sum[k] += m[k];
            rgb[0] += r; rgb[1] += g; rgb[2] += b;
            const float l = (0.3f * p[0] + 0.59f * p[1] + 0.11f * p[2]) / 255.0f;
            const uint8_t* px = p + 4 * step_x;
            const uint8_t* py = p + (size_t)t.width * 4 * step_y;
            const float lx = (0.3f * px[0] + 0.59f * px[1] + 0.11f * px[2]) / 255.0f, ly = (0.3f * py[0] + 0.59f * py[1] + 0.11f * py[2]) / 255.0f;
            edge_x += std::fabs(lx - l); edge_y += std::fabs(ly - l);
            lum_sum += l;
        }
    if (!n) return;
    w.opaque = (float)opaque / n;
    if (!opaque) return;
    for (int k = 0; k < 3; k++) w.mean[k] = (float)(rgb[k] / opaque);
    for (int k = 0; k < C_COUNT; k++) w.frac[k] = (float)(sum[k] / opaque);
    const double lum = std::max(lum_sum / opaque, 0.02);
    edge = (edge_x + edge_y) / opaque;
    w.edge = (float)(edge / lum);                                  // strong edges for its brightness: cobbles, blocks, boards
    w.aniso = (float)(std::max(edge_x, edge_y) / std::max(std::min(edge_x, edge_y), 1e-6));
    // its strongest family, and a second one that covers enough of it
    int a = C_NONE, b = C_NONE;
    for (int k = 1; k < C_COUNT; k++) {
        if (w.frac[k] <= 0.0f) continue;
        if (a == C_NONE || w.frac[k] > w.frac[a]) { b = a; a = k; }
        else if (b == C_NONE || w.frac[k] > w.frac[b]) b = k;
    }
    if (w.opaque < 0.8f) a = b = C_NONE;                           // a cut-out (foliage, railings): left as it is
    if (b != C_NONE && w.frac[b] < 0.14f) b = C_NONE;
    // what only the whole texture shows
    if (a == C_STONE && w.edge > world_cobble_edge) a = C_COBBLE;
    if (a == C_DIRT && w.aniso > world_wood_aniso && w.edge > world_wood_edge) a = C_WOOD;
    if (b == C_STONE && w.edge > world_cobble_edge) b = C_COBBLE;
    w.guess = (uint8_t)a;
    w.guess_b = (uint8_t)b;
    world_apply(w);
}

// the host's table over what was read: by the texture's name, else the class remapped for the level
void RtaDrawer::world_apply(WorldTex& w) {
    w.cls = w.guess;
    w.cls_b = w.guess_b;
    w.from_table = 0;
    auto o = world_overrides.find(w.name);
    if (!w.name.empty() && o != world_overrides.end()) {
        w.cls = (uint8_t)(o->second & 15);
        w.cls_b = (uint8_t)((o->second >> 4) & 15);
        w.from_table = 1;
        return;
    }
    if (w.cls < 16 && world_remap[w.cls] >= 0) { w.cls = (uint8_t)world_remap[w.cls]; w.from_table = 2; }
    if (w.cls_b < 16 && world_remap[w.cls_b] >= 0) w.cls_b = (uint8_t)world_remap[w.cls_b];
    if (w.cls_b == w.cls) w.cls_b = 0;
    if (w.cls == 0) w.cls_b = 0;
}

uint32_t RtaDrawer::world_code(uint32_t game_texture) {
    if (!world_on || !game_texture) return 0;
    auto it = world_tex.find(game_texture);
    if (it == world_tex.end() || it->second.pending) return 0;
    it->second.draws++;
    world_seen_frame[game_texture] = frames;
    return (uint32_t)it->second.cls | ((uint32_t)it->second.cls_b << 8);
}

// set_world_layer(on, table): table = {"<texture name>": "class" or "class/class_b", "remap.<class>": "class",
// "cobble_edge": x, "wood_aniso": x, "wood_edge": x, "grass": density (points per 1000 square units, 0 = none)}
void RtaDrawer::set_world_layer(bool on, const Dictionary& table) {
    world_on = on;
    world_overrides.clear();
    grass_hue = 64.0f;
    for (int k = 0; k < 16; k++) world_remap[k] = -1;
    Array keys = table.keys();
    for (int64_t i = 0; i < keys.size(); i++) {
        const String key = keys[i];
        const Variant value = table[keys[i]];
        if (key == "cobble_edge") { world_cobble_edge = (float)(double)value; continue; }
        if (key == "wood_aniso") { world_wood_aniso = (float)(double)value; continue; }
        if (key == "wood_edge") { world_wood_edge = (float)(double)value; continue; }
        if (key == "grass") { world_grass_density = (float)(double)value; continue; }
        if (key == "grass_hue") { grass_hue = (float)(double)value; continue; }
        const String v = value;
        if (key.begins_with("remap.")) {
            const int from = class_of_name(key.substr(6)), to = class_of_name(v);
            if (from >= 0 && to >= 0) world_remap[from] = to;
            continue;
        }
        const PackedStringArray parts = v.split("/");
        const int a = class_of_name(parts[0]), b = parts.size() > 1 ? class_of_name(parts[1]) : 0;
        if (a >= 0) world_overrides[key.utf8().get_data()] = a | (std::max(b, 0) << 4);
    }
    for (auto& e : world_tex) {
        // a texture whose pixels were read already: read again only from what was kept (the guess stays)
        world_apply(e.second);
    }
}

// what was read: per texture drawn within the last `frames_back` frames
Dictionary RtaDrawer::get_world_info(int64_t frames_back) const {
    Dictionary out;
    out["on"] = world_on;
    out["textures"] = (int64_t)world_tex.size();
    out["grass_pieces"] = (int64_t)grass_pieces.size();
    out["grass_points"] = (int64_t)grass_total;
    out["wall_cells"] = (int64_t)wall_cells.size();
    Array list;
    int64_t per_class[C_COUNT] = {0};
    for (const auto& e : world_tex) {
        auto seen = world_seen_frame.find(e.first);
        if (seen == world_seen_frame.end() || frames - seen->second > (uint64_t)std::max<int64_t>(frames_back, 0)) continue;
        const WorldTex& w = e.second;
        per_class[w.cls < C_COUNT ? w.cls : 0]++;
        Dictionary d;
        d["id"] = (int64_t)e.first;
        d["name"] = String(w.name.c_str());
        d["class"] = String(CLASS_NAMES[w.cls < C_COUNT ? w.cls : 0]);
        d["class_b"] = String(CLASS_NAMES[w.cls_b < C_COUNT ? w.cls_b : 0]);
        d["guess"] = String(CLASS_NAMES[w.guess < C_COUNT ? w.guess : 0]);
        d["table"] = (int64_t)w.from_table;
        d["mean"] = Color(w.mean[0], w.mean[1], w.mean[2]);
        PackedFloat32Array fr;
        for (int k = 1; k < C_COUNT; k++) fr.push_back(w.frac[k]);
        d["frac"] = fr;
        d["edge"] = w.edge;
        d["aniso"] = w.aniso;
        d["opaque"] = w.opaque;
        d["draws"] = (int64_t)w.draws;
        list.push_back(d);
    }
    out["seen"] = list;
    Dictionary pc;
    for (int k = 0; k < C_COUNT; k++) pc[CLASS_NAMES[k]] = per_class[k];
    out["per_class"] = pc;
    return out;
}

// ---- grass ------------------------------------------------------------------------------------------------------------

// a draw of the level's chunks (scene_take, before it is batched): its pieces' walls into the grid, and - where its
// texture reads as grass - points scattered on it, once per piece
void RtaDrawer::world_scan(const rtag_draw& d, const rtag_scene* tap) {
    if (!world_on || !tap) return;
    if (!d.scene_piece_count || d.scene_piece_first + d.scene_piece_count > tap->piece_count || !tap->full) return;
    auto wt = world_tex.find(d.texture);
    if (wt != world_tex.end() && wt->second.pending) {
        // its first draw: the mean of the game's vertex light over its pieces (128 = 1), then its texels read with it
        double sum[3] = {0, 0, 0};
        int n = 0;
        for (uint32_t k = 0; k < d.scene_piece_count && n < 600; k++) {
            const rtag_scene_piece& pc = tap->pieces[d.scene_piece_first + k];
            if (pc.full_first + pc.full_count > tap->full_count) continue;
            for (uint32_t i = 0; i < pc.full_count && n < 600; i += 3, n++) {
                const rtag_scene_full& v = tap->full[pc.full_first + i];
                sum[0] += v.r; sum[1] += v.g; sum[2] += v.b;
            }
        }
        float tint[3] = {1, 1, 1};
        if (n) for (int k = 0; k < 3; k++) tint[k] = (float)(sum[k] / n / 128.0);
        world_read(d.texture, tint);
    }
    if (world_grass_density <= 0.0f || (d.alpha_test && d.atst != 1)) return;     // (no grass on a cut-out card: a tree's crown)
    const bool grassy = wt != world_tex.end() && (wt->second.cls == C_GRASS || wt->second.cls_b == C_GRASS);
    const CpuTexture* cpu = nullptr;
    if (grassy) {
        auto c = cpu_textures.find(d.texture);
        if (c != cpu_textures.end() && c->second.w >= 8 && c->second.h >= 8) cpu = &c->second;
    }
    for (uint32_t k = 0; k < d.scene_piece_count; k++) {
        const rtag_scene_piece& pc = tap->pieces[d.scene_piece_first + k];
        if (pc.kind != 1 || !pc.full_count || pc.full_first + pc.full_count > tap->full_count) continue;
        const rtag_scene_full* v = tap->full + pc.full_first;
        // the piece's identity: its packet's figure and where it lies (the same packet may be placed twice)
        uint64_t id = mix64(pc.mesh ^ ((uint64_t)(int64_t)std::lround(v[0].x * 4) << 1) ^ ((uint64_t)(int64_t)std::lround(v[0].y * 4) << 23) ^
                            ((uint64_t)(int64_t)std::lround(v[0].z * 4) << 45));
        if (!grass_pieces.insert(id).second) continue;
        for (uint32_t i = 0; i + 2 < pc.full_count; i += 3) {
            const rtag_scene_full &a = v[i], &b = v[i + 1], &c = v[i + 2];
            const float ux = b.x - a.x, uy = b.y - a.y, uz = b.z - a.z, wx = c.x - a.x, wy = c.y - a.y, wz = c.z - a.z;
            float nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx;
            const float len = std::sqrt(nx * nx + ny * ny + nz * nz);
            if (len < 1e-4f) continue;
            nx /= len; ny /= len; nz /= len;
            if (std::fabs(nz) < 0.5f) {
                // a wall: the cells it stands in (every 6 units along it), with the height it spans
                const float lo = std::min(a.z, std::min(b.z, c.z)), hi = std::max(a.z, std::max(b.z, c.z));
                const float span = std::max(std::sqrt(ux * ux + uy * uy), std::sqrt(wx * wx + wy * wy));
                const int steps = std::min(64, (int)(span / 6.0f) + 1);
                for (int s = 0; s <= steps; s++)
                    for (int r = 0; r <= steps - s; r++) {
                        const float fs = (float)s / steps, fr = (float)r / steps;
                        const float px = a.x + ux * fs + wx * fr, py = a.y + uy * fs + wy * fr;
                        const int64_t cx = (int64_t)std::floor(px / WALL_CELL), cy = (int64_t)std::floor(py / WALL_CELL);
                        WallCell& wc = wall_cells[(uint64_t)(cx & 0xffffffff) | ((uint64_t)cy << 32)];
                        wc.lo = std::min(wc.lo, lo); wc.hi = std::max(wc.hi, hi);
                    }
                continue;
            }
            if (!grassy || !cpu || nz < 0.8f) continue;        // grass on what faces up (slopes up to about 37 degrees)
            const float area = 0.5f * len;
            const float want = area * world_grass_density / 1000.0f;
            const uint64_t seed = mix64(id + i * 0x9E3779B97F4A7C15ull);
            int count = (int)want;
            if ((float)((seed >> 11) & 0xffff) / 65536.0f < want - count) count++;
            for (int j = 0; j < count; j++) {
                const uint64_t h = mix64(seed + (uint64_t)j * 0xBF58476D1CE4E5B9ull);
                float s = (float)(h & 0xffff) / 65536.0f, r = (float)((h >> 16) & 0xffff) / 65536.0f;
                if (s + r > 1.0f) { s = 1.0f - s; r = 1.0f - r; }
                const float px = a.x + ux * s + wx * r, py = a.y + uy * s + wy * r, pz = a.z + uz * s + wz * r;
                // the texel under it: grass, or a path / a stone painted into the grass?
                const float tu = a.u + (b.u - a.u) * s + (c.u - a.u) * r, tv = a.v + (b.v - a.v) * s + (c.v - a.v) * r;
                float fx = tu * d.st_scale[0] + d.tex_offset[0], fy = tv * d.st_scale[1] + d.tex_offset[1];
                int tx = (int)std::floor(fx), ty = (int)std::floor(fy);
                tx = ((tx % cpu->w) + cpu->w) % cpu->w;
                ty = ((ty % cpu->h) + cpu->h) % cpu->h;
                const uint8_t* texel = &cpu->rgba[((size_t)ty * cpu->w + tx) * 4];
                // the ground colour there (with the game's vertex light), for the grass to take - and to be grass at all
                const float lr = (a.r + (b.r - a.r) * s + (c.r - a.r) * r) / 128.0f, lg = (a.g + (b.g - a.g) * s + (c.g - a.g) * r) / 128.0f,
                            lb = (a.b + (b.b - a.b) * s + (c.b - a.b) * r) / 128.0f;
                float m[C_COUNT];
                member(std::min(1.0f, texel[0] / 255.0f * lr), std::min(1.0f, texel[1] / 255.0f * lg), std::min(1.0f, texel[2] / 255.0f * lb), m);
                if (m[C_GRASS] < 0.45f) continue;
                GrassPoint g;
                g.x = px; g.y = py; g.z = pz;
                g.r = std::min(1.0f, texel[0] / 255.0f * lr); g.g = std::min(1.0f, texel[1] / 255.0f * lg); g.b = std::min(1.0f, texel[2] / 255.0f * lb);
                g.seed = (float)((h >> 32) & 0xffff) / 65536.0f;
                g.nx = nx; g.ny = ny; g.nz = nz;
                const int64_t gx = (int64_t)std::floor(px / GRASS_CELL), gy = (int64_t)std::floor(py / GRASS_CELL);
                grass_cells[(uint64_t)(gx & 0xffffffff) | ((uint64_t)gy << 32)].push_back(g);
                grass_total++;
            }
        }
    }
}

bool RtaDrawer::grass_near_wall(float x, float y, float z) const {
    const int64_t cx = (int64_t)std::floor(x / WALL_CELL), cy = (int64_t)std::floor(y / WALL_CELL);
    for (int64_t dy = -1; dy <= 1; dy++)
        for (int64_t dx = -1; dx <= 1; dx++) {
            auto it = wall_cells.find((uint64_t)((cx + dx) & 0xffffffff) | ((uint64_t)(cy + dy) << 32));
            if (it == wall_cells.end()) continue;
            if (it->second.lo < z + 30.0f && it->second.hi > z + 4.0f) return true;
        }
    return false;
}

// the points within `radius` of `eye` (on the ground plane), thinned out with distance: 9 floats each -
// x, y, z, r, g, b, seed, distance share (0 near .. 1 at the radius), facing (the normal's z)
PackedFloat32Array RtaDrawer::get_grass(const Vector3& eye, double radius, int64_t max_points) {
    PackedFloat32Array out;
    if (!world_on || grass_cells.empty()) return out;
    const int64_t r = (int64_t)std::ceil(radius / GRASS_CELL);
    const int64_t ex = (int64_t)std::floor(eye.x / GRASS_CELL), ey = (int64_t)std::floor(eye.y / GRASS_CELL);
    std::vector<float> v;
    v.reserve(std::min<int64_t>(max_points, 200000) * 9);
    const float r2 = (float)(radius * radius);
    int64_t n = 0;
    for (int64_t dy = -r; dy <= r && n < max_points; dy++)
        for (int64_t dx = -r; dx <= r && n < max_points; dx++) {
            auto it = grass_cells.find((uint64_t)((ex + dx) & 0xffffffff) | ((uint64_t)(ey + dy) << 32));
            if (it == grass_cells.end()) continue;
            for (const GrassPoint& g : it->second) {
                const float ddx = g.x - (float)eye.x, ddy = g.y - (float)eye.y;
                const float d2 = ddx * ddx + ddy * ddy;
                if (d2 > r2) continue;
                const float share = std::sqrt(d2 / r2);
                // fewer, by distance: all of them out to a third of the radius, then thinning to a quarter at the edge
                const float keep = share < 0.33f ? 1.0f : 1.0f - 0.75f * smooth(0.33f, 1.0f, share);
                if (g.seed > keep) continue;
                if (std::fabs(g.z - (float)eye.z) > 900.0f) continue;
                if (grass_near_wall(g.x, g.y, g.z)) continue;
                v.insert(v.end(), {g.x, g.y, g.z, g.r, g.g, g.b, g.seed, share, g.nz});
                if (++n >= max_points) break;
            }
        }
    out.resize((int64_t)v.size());
    if (!v.empty()) memcpy(out.ptrw(), v.data(), v.size() * sizeof(float));
    return out;
}

// a new level: what was scattered and walled is forgotten (the textures' classes stay with the textures)
void RtaDrawer::world_reset() {
    grass_pieces.clear();
    grass_cells.clear();
    wall_cells.clear();
    grass_total = 0;
}
