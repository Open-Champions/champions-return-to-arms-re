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
// Classes: 1 grass, 2 dirt, 3 stone, 4 cobble, 5 wood, 6 metal, 7 sand, 8 snow, 9 water, 10 lava, 11 ice (0: none - the texture
// stays as it is).  Water, lava, ice and snow never grow grass.
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
#include <string>
#include <vector>

using namespace godot;
using namespace rta_variant;

namespace {

enum { C_NONE = 0, C_GRASS = 1, C_DIRT = 2, C_STONE = 3, C_COBBLE = 4, C_WOOD = 5, C_METAL = 6, C_SAND = 7, C_SNOW = 8, C_WATER = 9, C_LAVA = 10,
       C_ICE = 11, C_COUNT = 12 };
const char* const CLASS_NAMES[C_COUNT] = {"none", "grass", "dirt", "stone", "cobble", "wood", "metal", "sand", "snow", "water", "lava", "ice"};

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

// the membership of one colour (0..1, stored values) in the families - as er_member in shaders/er_world.gdshaderinc:
// grass, dirt, sand, snow, stone, and the liquids and ice (measured on the sweep of every level, docs/issues/native-er-world.md):
//  - lava: a saturated red to orange that glows (bright); a dark rock under an orange light is not lava
//  - water: a saturated cyan to blue
//  - ice: a pale, faintly blue white (a snow is colourless; a blue-grey rock is darker or rougher: world_read)
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
    m[C_LAVA] = 0.0f;           // (lava glows whatever the light: lava_member, from the texel itself)
    m[C_WATER] = band(h, 172, 250, 12) * smooth(0.25f, 0.4f, sat);
    m[C_ICE] = band(h, 172, 245, 12) * smooth(0.05f, 0.1f, sat) * (1.0f - smooth(0.24f, 0.34f, sat)) * smooth(0.58f, 0.72f, lum);
    m[C_GRASS] = band(h, grass_hue, 160, 12) * smooth(0.08f, 0.18f, sat);
    m[C_SAND] = band(h, 26, 58, 10) * coloured * (1.0f - smooth(0.55f, 0.75f, sat)) * smooth(0.42f, 0.56f, lum) * (1.0f - m[C_LAVA]);
    m[C_DIRT] = band(h, 6, 56, 10) * coloured * (1.0f - m[C_SAND]) * (1.0f - m[C_LAVA]);
    m[C_SNOW] = smooth(0.62f, 0.78f, lum) * (1.0f - smooth(0.10f, 0.22f, sat)) * (1.0f - m[C_ICE]);
    m[C_STONE] = (1.0f - coloured) * (1.0f - m[C_SNOW]) * (1.0f - m[C_ICE]);
}

// lava: a saturated red to orange that is bright in the texture itself (0..1 texel values; the game's textures are stored
// at about half their drawn brightness) - as er_lava in shaders/er_world.gdshaderinc
float lava_member(float r, float g, float b) {
    const float mx = std::max(r, std::max(g, b)), mn = std::min(r, std::min(g, b));
    const float sat = (mx - mn) / std::max(mx, 0.04f);
    float h = 0;
    if (mx - mn > 1e-4f) {
        if (mx == r) h = 60.0f * std::fmod((g - b) / (mx - mn) + 6.0f, 6.0f);
        else if (mx == g) h = 60.0f * ((b - r) / (mx - mn) + 2.0f);
        else h = 60.0f * ((r - g) / (mx - mn) + 4.0f);
    }
    return (h < 180.0f ? band(h, -20, 40, 10) : band(h, 340, 400, 10)) * smooth(0.5f, 0.65f, sat) * smooth(0.38f, 0.52f, mx);
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
    double sum[C_COUNT] = {0}, sum_grey[C_COUNT] = {0}, rgb[3] = {0, 0, 0}, edge = 0, edge_x = 0, edge_y = 0, lum_sum = 0, lum_sq = 0;
    double jxx = 0, jyy = 0, jxy = 0, sat_sum = 0;      // the structure tensor of its brightness (which way its edges run)
    int n = 0, opaque = 0, high = 0, total = 0, coloured = 0, cool = 0, hot = 0;
    std::vector<float> lums;
    lums.reserve(4096);
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
            {
                // lava, from the texel itself: what it takes is taken from the others
                // (only where the level's section says it has lava: a lamp-lit red wall glows in its texture too)
                const float lava = world_lava_read ? lava_member(p[0] / 255.0f, p[1] / 255.0f, p[2] / 255.0f) : 0.0f;
                if (lava > 0.0f) {
                    for (int k = 1; k < C_COUNT; k++) m[k] *= 1.0f - lava;
                    m[C_LAVA] = lava;
                }
            }
            for (int k = 0; k < C_COUNT; k++) sum[k] += m[k];
            {
                // a glowing texel (lava's: bright orange to yellow in the texture itself, whatever the light)
                const int mx8 = std::max(p[0], std::max(p[1], p[2])), mn8 = std::min(p[0], std::min(p[1], p[2]));
                if (mx8 > 120 && p[0] == mx8 && (mx8 - mn8) > 0.45f * mx8 && p[1] > 0.3f * p[0]) hot++;
            }
            // ... and the texel as it is, without the level's light: what the surface is, whatever colour and strength the
            // light has (a snowfield under a deep blue night light reads as nothing - or as water - under its own)
            {
                float mg[C_COUNT];
                member(p[0] / 255.0f, p[1] / 255.0f, p[2] / 255.0f, mg);
                for (int k = 0; k < C_COUNT; k++) sum_grey[k] += mg[k];
            }
            rgb[0] += r; rgb[1] += g; rgb[2] += b;
            const float l = (0.3f * p[0] + 0.59f * p[1] + 0.11f * p[2]) / 255.0f;
            const uint8_t* px = p + 4 * step_x;
            const uint8_t* py = p + (size_t)t.width * 4 * step_y;
            const float lx = (0.3f * px[0] + 0.59f * px[1] + 0.11f * px[2]) / 255.0f, ly = (0.3f * py[0] + 0.59f * py[1] + 0.11f * py[2]) / 255.0f;
            edge_x += std::fabs(lx - l); edge_y += std::fabs(ly - l);
            jxx += (lx - l) * (lx - l); jyy += (ly - l) * (ly - l); jxy += (lx - l) * (ly - l);
            lum_sum += l; lum_sq += l * l;
            lums.push_back(l);
            const float mx = std::max(r, std::max(g, b)), mn = std::min(r, std::min(g, b));
            const float sat = (mx - mn) / std::max(mx, 0.04f);
            sat_sum += sat;
            if (sat > 0.06f && mx - mn > 1e-4f) {
                coloured++;
                float hue = mx == r ? 60.0f * std::fmod((g - b) / (mx - mn) + 6.0f, 6.0f) : mx == g ? 60.0f * ((b - r) / (mx - mn) + 2.0f) : 60.0f * ((r - g) / (mx - mn) + 4.0f);
                if (hue >= 180.0f && hue <= 260.0f) cool++;
            }
        }
    if (!n) return;
    w.opaque = (float)opaque / n;
    if (!opaque) return;
    for (int k = 0; k < 3; k++) w.mean[k] = (float)(rgb[k] / opaque);
    for (int k = 0; k < C_COUNT; k++) w.frac[k] = (float)(sum[k] / opaque);
    {
        // water and ice are blue in themselves, not only under a blue light; where the level's light leaves the texture
        // in no family at all (a deep, coloured light), it is read by its texels alone
        float grey[C_COUNT], families = 0;
        for (int k = 0; k < C_COUNT; k++) grey[k] = (float)(sum_grey[k] / opaque);
        for (int k = 1; k < C_COUNT; k++) families += k == C_WATER || k == C_ICE ? std::min(w.frac[k], grey[k]) : w.frac[k];
        // (water is read only where the level's section says so: a blue light, a blue painted stone or a pale marble reads
        // as water as often as a lake does - the sweep found it on 30 levels with no water in their solid pieces; the game's
        // water surfaces are see-through sheets, which keep the grass off without a class: world_decal)
        w.frac[C_WATER] = world_water_read ? std::min(w.frac[C_WATER], grey[C_WATER]) : 0.0f;
        w.frac[C_ICE] = std::min(w.frac[C_ICE], grey[C_ICE]);
        if (families < 0.35f) {
            for (int k = 0; k < C_COUNT; k++) w.frac[k] = grey[k];
            w.lit_grey = true;
        }
        if (!world_water_read) w.frac[C_WATER] = 0.0f;
    }
    const double lum = std::max(lum_sum / opaque, 0.02);
    edge = (edge_x + edge_y) / opaque;
    w.edge = (float)(edge / lum);                                  // strong edges for its brightness: cobbles, blocks, boards
    w.aniso = (float)(std::max(edge_x, edge_y) / std::max(std::min(edge_x, edge_y), 1e-6));
    w.coherence = (float)(std::sqrt((jxx - jyy) * (jxx - jyy) + 4.0 * jxy * jxy) / std::max(jxx + jyy, 1e-9));
    w.sat = (float)(sat_sum / opaque);
    w.contrast = (float)(std::sqrt(std::max(lum_sq / opaque - (lum_sum / opaque) * (lum_sum / opaque), 0.0)) / lum);
    w.cool = coloured ? (float)cool / coloured : 0.0f;
    w.hot = (float)hot / opaque;
    {
        // glints: texels far brighter than the texture's middle (a metal's painted highlights)
        std::vector<float> sorted(lums);
        std::nth_element(sorted.begin(), sorted.begin() + sorted.size() / 2, sorted.end());
        const float median = std::max(sorted[sorted.size() / 2], 0.02f);
        int glints = 0;
        for (float l : lums) glints += l > median * 1.8f && l > 0.35f ? 1 : 0;
        w.glint = (float)glints / (float)lums.size();
    }
    // its strongest family, and a second one that covers enough of it
    int a = C_NONE, b = C_NONE;
    for (int k = 1; k < C_COUNT; k++) {
        if (w.frac[k] <= 0.0f) continue;
        if (a == C_NONE || w.frac[k] > w.frac[a]) { b = a; a = k; }
        else if (b == C_NONE || w.frac[k] > w.frac[b]) b = k;
    }
    // lava glows: a red that does not (a carpet, a banner, a dark rock under a red light) is earth
    // (as a share of what reads as lava: a texture page with a lava flow in a corner)
    const bool glows = w.frac[C_LAVA] > 0.0f && w.hot / w.frac[C_LAVA] >= world_lava_hot;
    if (a == C_LAVA && !glows) a = C_DIRT;
    if (b == C_LAVA && !glows) b = C_NONE;
    // a lava flow on part of a texture (a page of the level's pieces): the second class, decided per pixel, whatever else
    // is second
    if (glows && a != C_LAVA && w.frac[C_LAVA] >= 0.03f) b = C_LAVA;
    // a cut-out (foliage, railings) is left as it is - but not a liquid whose alpha makes it see-through (a lava flow's edge)
    if (w.opaque < 0.8f && !(a == C_LAVA || (a == C_WATER && w.opaque > 0.3f))) a = b = C_NONE;
    if (b != C_NONE && w.frac[b] < 0.14f) b = C_NONE;
    // what only the whole texture shows
    //  - wood: warm (earth or sand colours, or a warm grey) with edges running one way - its grain, its boards - at any
    //    turn (the structure tensor's coherence; the old test took only edges along the texture's own axes)
    //  - metal: grey or blue-grey, smooth between bright glints (painted highlights), with a strong spread of brightness
    //  - cobble: grey with strong, even edges (setts, flagstones)
    // (measured on class pictures: a mine's beams have edges 1.5..1.9 times stronger along one axis; rock, lava swirls and
    // painted floors 1.0..1.2 - the coherence, whichever way the edges run, is 0.2..0.5 for all of them, so it only
    // counts when it is far over that; valor's cliffs are cool and have glints too, but few and with a coloured cast)
    const bool warm = a == C_DIRT || a == C_SAND || (a == C_STONE && w.mean[0] > w.mean[2] * 1.12f && w.sat > 0.08f);
    const bool grained = w.aniso > world_wood_aniso || w.coherence > world_wood_coherence;
    if (warm && grained && w.edge > world_wood_edge) a = C_WOOD;
    else if (a == C_STONE && w.sat < 0.1f && w.glint > world_metal_glint && w.contrast > world_metal_contrast && w.edge < 0.5f) a = C_METAL;
    else if (a == C_STONE && w.edge > world_cobble_edge) a = C_COBBLE;
    // ice is smooth: a rough, pale blue-white is snow
    if (a == C_ICE && w.edge > world_ice_edge) a = C_SNOW;
    if (b == C_ICE && w.edge > world_ice_edge) b = C_SNOW;
    if (b == a) b = C_NONE;
    // a liquid or ice is the whole surface: no second class decided per pixel over it, and none of them under another
    if (a == C_WATER || a == C_LAVA) b = C_NONE;
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
    world_lava_read = false;
    world_water_read = false;
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
        if (key == "wood_coherence") { world_wood_coherence = (float)(double)value; continue; }
        if (key == "metal_glint") { world_metal_glint = (float)(double)value; continue; }
        if (key == "metal_contrast") { world_metal_contrast = (float)(double)value; continue; }
        if (key == "grass") { world_grass_density = (float)(double)value; continue; }
        if (key == "grass_hue") { grass_hue = (float)(double)value; continue; }
        if (key == "grass_ground") { world_grass_ground = (float)(double)value; continue; }
        if (key == "grass_clear") { world_grass_clear = (float)(double)value; continue; }
        if (key == "ice_edge") { world_ice_edge = (float)(double)value; continue; }
        if (key == "lava_hot") { world_lava_hot = (float)(double)value; continue; }
        if (key == "lava") { world_lava_read = (double)value > 0.5; continue; }
        if (key == "water") { world_water_read = (double)value > 0.5; continue; }
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
        d["coherence"] = w.coherence;
        d["sat"] = w.sat;
        d["contrast"] = w.contrast;
        d["glint"] = w.glint;
        d["cool"] = w.cool;
        d["opaque"] = w.opaque;
        d["tint"] = Color(w.tint[0], w.tint[1], w.tint[2]);
        d["lit_grey"] = w.lit_grey;
        d["hot"] = w.hot;
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
    // a surface that is not grass (read, solid): what faces up on it keeps the tufts off (a path laid on the ground, a kerb)
    const bool other = wt != world_tex.end() && !wt->second.pending && !grassy && wt->second.opaque >= 0.8f &&
                       !(d.blend && !(d.ba == 0 && d.bb == 1 && d.bc == 0 && d.bd == 1));     // (not a glow)
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
        if (grassy) {
            // when the piece was last drawn: the game leaves pieces out by distance and brings them back (valor's grass
            // carpets over its flagstone floor), and their tufts must go and come with them
            uint64_t& last = grass_seen[id];
            if (frames - last > GRASS_GONE) grass_epoch++;
            last = frames;
        }
        if (!grass_pieces.insert(id).second) continue;
        // a piece that is mostly not ground (a bush's mound, a rock, a tree's crown: little of its area faces up) grows no
        // grass on the little that does - the tufts stood on such tops like slabs in the air
        bool ground_piece = true;
        if (grassy && cpu) {
            double up = 0, all = 0;
            for (uint32_t i = 0; i + 2 < pc.full_count; i += 3) {
                const rtag_scene_full &a = v[i], &b = v[i + 1], &c = v[i + 2];
                const float ux = b.x - a.x, uy = b.y - a.y, uz = b.z - a.z, wx = c.x - a.x, wy = c.y - a.y, wz = c.z - a.z;
                const float nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx;
                const float len = std::sqrt(nx * nx + ny * ny + nz * nz);
                all += len;
                if (len > 1e-6f && std::fabs(nz) / len >= 0.8f) up += len;
            }
            ground_piece = all <= 0 || up / all >= world_grass_ground;
        }
        for (uint32_t i = 0; i + 2 < pc.full_count; i += 3) {
            const rtag_scene_full &a = v[i], &b = v[i + 1], &c = v[i + 2];
            const float ux = b.x - a.x, uy = b.y - a.y, uz = b.z - a.z, wx = c.x - a.x, wy = c.y - a.y, wz = c.z - a.z;
            float nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx;
            const float len = std::sqrt(nx * nx + ny * ny + nz * nz);
            if (len < 1e-4f) continue;
            nx /= len; ny /= len; nz /= len;
            // the triangle's side by the game's own normals (the strips' winding alternates)
            if (nx * (a.nx + b.nx + c.nx) + ny * (a.ny + b.ny + c.ny) + nz * (a.nz + b.nz + c.nz) < 0) { nx = -nx; ny = -ny; nz = -nz; }
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
            if (other && nz >= 0.5f) { world_mark(ground_cells, a, b, c); ground_gen++; }
            if (grassy && nz >= 0.5f) { world_mark(cover_cells, a, b, c); ground_gen++; }
            if (!grassy || !cpu || !ground_piece || nz < 0.8f) continue;     // grass on what faces up (slopes up to about 37 degrees)
            const float area = 0.5f * len;
            const float want = area * world_grass_density / 1000.0f;
            // texels a world unit here (the triangle's area in texels over its area in units): the ground's painted
            // features (a flower patch, a path's edge) are looked for around each point, not only under it
            const float tax = (b.u - a.u) * d.st_scale[0], tay = (b.v - a.v) * d.st_scale[1], tbx = (c.u - a.u) * d.st_scale[0], tby = (c.v - a.v) * d.st_scale[1];
            const float texel_area = 0.5f * std::fabs(tax * tby - tay * tbx);
            const float per_unit = area > 1e-4f ? std::sqrt(texel_area / area) : 0.0f;
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
                if (d.tcc && wt->second.opaque < 0.999f && texel[3] < 0x40) continue;      // a see-through texel: nothing grows on it
                // the ground colour there (with the game's vertex light), for the grass to take - and to be grass at all
                const float lr = (a.r + (b.r - a.r) * s + (c.r - a.r) * r) / 128.0f, lg = (a.g + (b.g - a.g) * s + (c.g - a.g) * r) / 128.0f,
                            lb = (a.b + (b.b - a.b) * s + (c.b - a.b) * r) / 128.0f;
                float m[C_COUNT];
                member(std::min(1.0f, texel[0] / 255.0f * lr), std::min(1.0f, texel[1] / 255.0f * lg), std::min(1.0f, texel[2] / 255.0f * lb), m);
                if (m[C_GRASS] < 0.45f) continue;
                // room: how far (units) the nearest painted feature lies that is not grass (a flagstone, a path's edge, a flower
                // patch: texels not grass, or far brighter than the grass here - white and yellow petals read as pale grass).
                // Looked at on rings round the point; the tuft is made no wider than its room (er_world.gd), and none is put
                // where the room is under `grass_clear` units
                float room = 40.0f;
                if (per_unit > 0.0f && world_grass_clear > 0.0f) {
                    static const float RINGS[] = {4.0f, 8.0f, 13.0f, 19.0f, 26.0f, 34.0f};
                    static const float DIRS[8][2] = {{1, 0}, {0.7071f, 0.7071f}, {0, 1}, {-0.7071f, 0.7071f}, {-1, 0}, {-0.7071f, -0.7071f}, {0, -1}, {0.7071f, -0.7071f}};
                    const float lum_here = (0.3f * texel[0] + 0.59f * texel[1] + 0.11f * texel[2]) / 255.0f;
                    for (float ring : RINGS) {
                        const float rad = ring * per_unit;
                        int features = 0;
                        for (const auto& dir : DIRS) {
                            int qx = (int)std::floor(fx + dir[0] * rad), qy = (int)std::floor(fy + dir[1] * rad);
                            qx = ((qx % cpu->w) + cpu->w) % cpu->w;
                            qy = ((qy % cpu->h) + cpu->h) % cpu->h;
                            const uint8_t* q = &cpu->rgba[((size_t)qy * cpu->w + qx) * 4];
                            float mq[C_COUNT];
                            member(std::min(1.0f, q[0] / 255.0f * lr), std::min(1.0f, q[1] / 255.0f * lg), std::min(1.0f, q[2] / 255.0f * lb), mq);
                            const float lum = (0.3f * q[0] + 0.59f * q[1] + 0.11f * q[2]) / 255.0f;
                            if (mq[C_GRASS] < 0.3f || lum > lum_here * 1.8f + 0.08f) features++;
                        }
                        // (a ring only counts once two of its eight points are a feature: one may be a speck)
                        if (features >= 2) { room = ring; break; }
                    }
                    if (room < world_grass_clear) continue;
                }
                GrassPoint g;
                g.x = px; g.y = py; g.z = pz;
                g.r = std::min(1.0f, texel[0] / 255.0f * lr); g.g = std::min(1.0f, texel[1] / 255.0f * lg); g.b = std::min(1.0f, texel[2] / 255.0f * lb);
                g.seed = (float)((h >> 32) & 0xffff) / 65536.0f;
                g.nx = nx; g.ny = ny; g.nz = nz;
                g.room = room;
                g.piece = id;
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

// a triangle's cells (GROUND_CELL) with the height span it covers them at
void RtaDrawer::world_mark(std::unordered_map<uint64_t, WallCell>& cells, const rtag_scene_full& a, const rtag_scene_full& b, const rtag_scene_full& c) {
    const float ux = b.x - a.x, uy = b.y - a.y, wx = c.x - a.x, wy = c.y - a.y;
    const float span = std::max(std::sqrt(ux * ux + uy * uy), std::sqrt(wx * wx + wy * wy));
    const int steps = std::min(200, (int)(span / (GROUND_CELL * 0.5f)) + 1);
    for (int s = 0; s <= steps; s++)
        for (int r = 0; r <= steps - s; r++) {
            const float fs = (float)s / steps, fr = (float)r / steps;
            const float px = a.x + ux * fs + wx * fr, py = a.y + uy * fs + wy * fr, pz = a.z + (b.z - a.z) * fs + (c.z - a.z) * fr;
            const int64_t cx = (int64_t)std::floor(px / GROUND_CELL), cy = (int64_t)std::floor(py / GROUND_CELL);
            WallCell& wc = cells[(uint64_t)(cx & 0xffffffff) | ((uint64_t)cy << 32)];
            wc.lo = std::min(wc.lo, pz); wc.hi = std::max(wc.hi, pz);
        }
}

// units (up to 40) to the nearest surface that is not grass and lies at or over the point's height (up to 40 over it), or
// that lies a little under it where no grass covers it: the edge of a grass carpet laid over a flagstone floor (valor)
float RtaDrawer::grass_cell_room(float x, float y, float z) const {
    if (ground_cells.empty()) return 40.0f;
    static const float DIRS[8][2] = {{1, 0}, {0.7071f, 0.7071f}, {0, 1}, {-0.7071f, 0.7071f}, {-1, 0}, {-0.7071f, -0.7071f}, {0, -1}, {0.7071f, -0.7071f}};
    auto hit = [&](float px, float py) {
        const int64_t cx = (int64_t)std::floor(px / GROUND_CELL), cy = (int64_t)std::floor(py / GROUND_CELL);
        const uint64_t key = (uint64_t)(cx & 0xffffffff) | ((uint64_t)cy << 32);
        auto it = ground_cells.find(key);
        if (it == ground_cells.end() || it->second.lo >= z + 40.0f) return false;
        if (it->second.hi > z + 1.5f) return true;
        if (it->second.hi < z - 8.0f) return false;
        auto cv = cover_cells.find(key);
        return cv == cover_cells.end() || cv->second.hi < it->second.hi - 0.5f;
    };
    if (hit(x, y)) return 0.0f;
    for (float ring = 6.0f; ring <= 36.0f; ring += 6.0f)
        for (const auto& dir : DIRS)
            if (hit(x + dir[0] * ring, y + dir[1] * ring)) return ring - 3.0f;
    return 40.0f;
}

// under a see-through sheet of the level (a lake's surface, ice) that lies over the point
bool RtaDrawer::grass_under_sheet(float x, float y, float z) const {
    if (sheet_cells.empty()) return false;
    const int64_t cx = (int64_t)std::floor(x / GROUND_CELL), cy = (int64_t)std::floor(y / GROUND_CELL);
    for (int64_t dy = -1; dy <= 1; dy++)
        for (int64_t dx = -1; dx <= 1; dx++) {
            auto it = sheet_cells.find((uint64_t)((cx + dx) & 0xffffffff) | ((uint64_t)(cy + dy) << 32));
            if (it != sheet_cells.end() && it->second.hi > z + 3.0f && it->second.lo < z + 600.0f) return true;
        }
    return false;
}

// the points within `radius` of `eye` (on the ground plane), thinned out with distance: 10 floats each -
// x, y, z, r, g, b, seed, distance share (0 near .. 1 at the radius), facing (the normal's z), room (units to the nearest
// thing that is not grass: the tuft is made no wider)
PackedFloat32Array RtaDrawer::get_grass(const Vector3& eye, double radius, int64_t max_points) {
    constexpr int F = 10;
    PackedFloat32Array out;
    if (!world_on || grass_cells.empty()) return out;
    const int64_t r = (int64_t)std::ceil(radius / GRASS_CELL);
    const int64_t ex = (int64_t)std::floor(eye.x / GRASS_CELL), ey = (int64_t)std::floor(eye.y / GRASS_CELL);
    std::vector<float> v;
    v.reserve(std::min<int64_t>(max_points, 200000) * F);
    const float r2 = (float)(radius * radius);
    int64_t n = 0;
    for (int64_t dy = -r; dy <= r && n < max_points; dy++)
        for (int64_t dx = -r; dx <= r && n < max_points; dx++) {
            auto it = grass_cells.find((uint64_t)((ex + dx) & 0xffffffff) | ((uint64_t)(ey + dy) << 32));
            if (it == grass_cells.end()) continue;
            for (GrassPoint& g : it->second) {
                const float ddx = g.x - (float)eye.x, ddy = g.y - (float)eye.y;
                const float d2 = ddx * ddx + ddy * ddy;
                if (d2 > r2) continue;
                const float share = std::sqrt(d2 / r2);
                // fewer, by distance: all of them out to a third of the radius, then thinning to a quarter at the edge
                const float keep = share < 0.33f ? 1.0f : 1.0f - 0.75f * smooth(0.33f, 1.0f, share);
                if (g.seed > keep) continue;
                if (std::fabs(g.z - (float)eye.z) > 900.0f) continue;
                {
                    // (its piece is not drawn now: the game has left it out)
                    auto seen = grass_seen.find(g.piece);
                    if (seen == grass_seen.end() || frames - seen->second > GRASS_GONE) continue;
                }
                if (grass_near_wall(g.x, g.y, g.z) || grass_under_decal(g.x, g.y, g.z) || grass_under_sheet(g.x, g.y, g.z)) continue;
                if (g.cell_gen != ground_gen) { g.cell_room = grass_cell_room(g.x, g.y, g.z); g.cell_gen = ground_gen; }
                const float room = std::min(g.room, g.cell_room);
                if (room < world_grass_clear) continue;
                v.insert(v.end(), {g.x, g.y, g.z, g.r, g.g, g.b, g.seed, share, g.nz, room});
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
    grass_seen.clear();
    grass_epoch++;
    grass_cells.clear();
    wall_cells.clear();
    grass_total = 0;
    decal_pieces.clear();
    decal_cells.clear();
    decal_textures.clear();
    ground_cells.clear();
    cover_cells.clear();
    sheet_cells.clear();
    ground_gen++;
    world_hide_cache.clear();
    world_watch_cache.clear();
}

// ---- decals ------------------------------------------------------------------------------------------------------------

// an alpha-blended draw of the level's chunks whose texture is partly see-through: a decal painted over the ground - a flower
// patch, a path, moss (the game draws them with depth written, like the ground).  Where it covers the ground (its texel's
// alpha times the game's vertex alpha) with something that is not grass itself, no grass grows: the cells it covers are
// kept with the height they are covered at.  Once per piece.
void RtaDrawer::world_decal(const rtag_draw& d, const rtag_scene* tap) {
    if (!tap || !d.scene_piece_count || d.scene_piece_first + d.scene_piece_count > tap->piece_count || !tap->full) return;
    if (world_grass_density <= 0.0f) return;
    // an alpha blend (Cs - Cd) * As + Cd: what it paints covers the ground; an additive one (a glow) does not
    if (!(d.ba == 0 && d.bb == 1 && d.bc == 0 && d.bd == 1)) return;
    auto c = cpu_textures.find(d.texture);
    if (c == cpu_textures.end() || c->second.w < 4 || c->second.h < 4) return;
    const CpuTexture& cpu = c->second;
    {
        // a see-through sheet: blended and not written into depth (a lake's, a river's surface), or one whose texture reads
        // as water, lava or ice - nothing grows under it.  Once per piece
        auto wt = world_tex.find(d.texture);
        const bool liquid = wt != world_tex.end() && !wt->second.pending &&
                            (wt->second.cls == C_WATER || wt->second.cls == C_LAVA || wt->second.cls == C_ICE);
        if (!d.depth_write || liquid) {
            for (uint32_t k = 0; k < d.scene_piece_count; k++) {
                const rtag_scene_piece& pc = tap->pieces[d.scene_piece_first + k];
                if (pc.kind != 1 || !pc.full_count || pc.full_first + pc.full_count > tap->full_count) continue;
                const rtag_scene_full* v = tap->full + pc.full_first;
                const uint64_t id = mix64(pc.mesh ^ 0x3C6EF372FE94F82Bull ^ ((uint64_t)(int64_t)std::lround(v[0].x * 4) << 1) ^
                                          ((uint64_t)(int64_t)std::lround(v[0].y * 4) << 23) ^ ((uint64_t)(int64_t)std::lround(v[0].z * 4) << 45));
                if (!decal_pieces.insert(id).second) continue;
                for (uint32_t i = 0; i + 2 < pc.full_count; i += 3) {
                    const rtag_scene_full &a = v[i], &b = v[i + 1], &cc = v[i + 2];
                    const float ux = b.x - a.x, uy = b.y - a.y, uz = b.z - a.z, wx = cc.x - a.x, wy = cc.y - a.y, wz = cc.z - a.z;
                    const float nz = ux * wy - uy * wx;
                    const float len = std::sqrt((uy * wz - uz * wy) * (uy * wz - uz * wy) + (uz * wx - ux * wz) * (uz * wx - ux * wz) + nz * nz);
                    if (len > 1e-4f && std::fabs(nz) / len >= 0.7f) world_mark(sheet_cells, a, b, cc);
                }
            }
            if (!d.depth_write) return;
        }
    }
    if (!d.tcc) return;                                         // its alpha is the vertices' alone: not a painted shape
    {
        // see-through somewhere (a ground texture is opaque all over): looked at once per texture
        auto known = decal_textures.find(d.texture);
        if (known == decal_textures.end()) {
            int low = 0, n = 0;
            const int sx = std::max(1, cpu.w / 32), sy = std::max(1, cpu.h / 32);
            for (int y = 0; y < cpu.h; y += sy)
                for (int x = 0; x < cpu.w; x += sx, n++) low += cpu.rgba[((size_t)y * cpu.w + x) * 4 + 3] < 0x40 ? 1 : 0;
            known = decal_textures.emplace(d.texture, n && low * 50 >= n).first;       // at least 2% of it see-through
        }
        if (!known->second) return;
    }
    for (uint32_t k = 0; k < d.scene_piece_count; k++) {
        const rtag_scene_piece& pc = tap->pieces[d.scene_piece_first + k];
        if (pc.kind != 1 || !pc.full_count || pc.full_first + pc.full_count > tap->full_count) continue;
        const rtag_scene_full* v = tap->full + pc.full_first;
        const uint64_t id = mix64(pc.mesh ^ 0x5DEECE66Dull ^ ((uint64_t)(int64_t)std::lround(v[0].x * 4) << 1) ^
                                  ((uint64_t)(int64_t)std::lround(v[0].y * 4) << 23) ^ ((uint64_t)(int64_t)std::lround(v[0].z * 4) << 45));
        if (!decal_pieces.insert(id).second) continue;
        for (uint32_t i = 0; i + 2 < pc.full_count; i += 3) {
            const rtag_scene_full &a = v[i], &b = v[i + 1], &cc = v[i + 2];
            const float ux = b.x - a.x, uy = b.y - a.y, uz = b.z - a.z, wx = cc.x - a.x, wy = cc.y - a.y, wz = cc.z - a.z;
            const float nz = ux * wy - uy * wx;
            const float len = std::sqrt((uy * wz - uz * wy) * (uy * wz - uz * wy) + (uz * wx - ux * wz) * (uz * wx - ux * wz) + nz * nz);
            if (len < 1e-4f || std::fabs(nz) / len < 0.5f) continue;          // (a decal on a wall: no grass there anyway)
            // samples every 2 units or so over the triangle
            const float span = std::max(std::sqrt(ux * ux + uy * uy), std::sqrt(wx * wx + wy * wy));
            const int steps = std::min(160, (int)(span / 2.0f) + 1);
            for (int si = 0; si <= steps; si++)
                for (int ri = 0; ri <= steps - si; ri++) {
                    const float fs = (float)si / steps, fr = (float)ri / steps;
                    const float tu = a.u + (b.u - a.u) * fs + (cc.u - a.u) * fr, tv = a.v + (b.v - a.v) * fs + (cc.v - a.v) * fr;
                    int tx = (int)std::floor(tu * d.st_scale[0] + d.tex_offset[0]), ty = (int)std::floor(tv * d.st_scale[1] + d.tex_offset[1]);
                    tx = ((tx % cpu.w) + cpu.w) % cpu.w;
                    ty = ((ty % cpu.h) + cpu.h) % cpu.h;
                    const uint8_t* texel = &cpu.rgba[((size_t)ty * cpu.w + tx) * 4];
                    const float va = (a.a + (b.a - a.a) * fs + (cc.a - a.a) * fr) / 128.0f;
                    const float ta = d.tcc ? texel[3] / 128.0f : 1.0f;
                    if (ta * va < 0.35f) continue;
                    const float lr = (a.r + (b.r - a.r) * fs + (cc.r - a.r) * fr) / 128.0f, lg = (a.g + (b.g - a.g) * fs + (cc.g - a.g) * fr) / 128.0f,
                                lb = (a.b + (b.b - a.b) * fs + (cc.b - a.b) * fr) / 128.0f;
                    float m[C_COUNT];
                    member(std::min(1.0f, texel[0] / 255.0f * lr), std::min(1.0f, texel[1] / 255.0f * lg), std::min(1.0f, texel[2] / 255.0f * lb), m);
                    if (m[C_GRASS] > 0.6f) continue;                              // a decal of grass itself: grass may grow there
                    const float px = a.x + ux * fs + wx * fr, py = a.y + uy * fs + wy * fr, pz = a.z + uz * fs + wz * fr;
                    const int64_t cx = (int64_t)std::floor(px / DECAL_CELL), cy = (int64_t)std::floor(py / DECAL_CELL);
                    WallCell& dc = decal_cells[(uint64_t)(cx & 0xffffffff) | ((uint64_t)cy << 32)];
                    dc.lo = std::min(dc.lo, pz); dc.hi = std::max(dc.hi, pz);
                }
        }
    }
}

// under a decal, or within a cell of one (a tuft leans over its neighbours: a flower patch must stay clear)
bool RtaDrawer::grass_under_decal(float x, float y, float z) const {
    if (decal_cells.empty()) return false;
    const int64_t cx = (int64_t)std::floor(x / DECAL_CELL), cy = (int64_t)std::floor(y / DECAL_CELL);
    for (int64_t dy = -1; dy <= 1; dy++)
        for (int64_t dx = -1; dx <= 1; dx++) {
            auto it = decal_cells.find((uint64_t)((cx + dx) & 0xffffffff) | ((uint64_t)(cy + dy) << 32));
            if (it != decal_cells.end() && it->second.lo < z + 12.0f && it->second.hi > z - 12.0f) return true;
        }
    return false;
}

// ---- the rebuild: shapes drawn by fitted Elden Ring pieces instead ---------------------------------------------------------

void RtaDrawer::set_world_hide(const Array& volumes) {
    world_hide.clear();
    world_hide_cache.clear();
    world_watch_cache.clear();
    world_watch_any = false;
    world_hide_models = false;
    world_hide_gen++;
    for (int64_t i = 0; i < volumes.size(); i++) {
        const Array v = volumes[i];
        if (v.size() < 9) continue;
        WorldHide h;
        for (int k = 0; k < 3; k++) { h.c[k] = (float)(double)v[k]; h.h[k] = (float)(double)v[3 + k]; }
        const double yaw = (double)v[6] * 3.14159265358979323846 / 180.0;
        h.cos_yaw = (float)std::cos(yaw); h.sin_yaw = (float)std::sin(yaw);
        h.cylinder = (int64_t)v[7] != 0;
        h.kinds = (int)(int64_t)v[8];
        // watch-only (kinds 4): the game's packets inside are noted, never left out; [9] the packets' figures (hex)
        h.watch = (h.kinds & 4) != 0;
        if (h.watch && v.size() >= 10 && v[9].get_type() == Variant::ARRAY) {
            const Array figs = v[9];
            for (int64_t k = 0; k < figs.size(); k++) h.figures.push_back(strtoull(String(figs[k]).utf8().get_data(), nullptr, 16));
            std::sort(h.figures.begin(), h.figures.end());
        }
        world_hide.push_back(h);
        if (h.watch) world_watch_any = true;
        else if (h.kinds & 2) world_hide_models = true;
    }
}

// a model draw the rebuild takes: the middle of its packets' box lies inside a volume for models (a figure walking past is
// not: its middle is never inside the shape it walks around)
bool RtaDrawer::world_model_taken(const rtag_draw& d, const rtag_scene* tap) {
    if (!tap || !d.scene_piece_count || d.scene_piece_first + d.scene_piece_count > tap->piece_count || !tap->full) return false;
    float lo[3] = {1e30f, 1e30f, 1e30f}, hi[3] = {-1e30f, -1e30f, -1e30f};
    for (uint32_t k = 0; k < d.scene_piece_count; k++) {
        const rtag_scene_piece& pc = tap->pieces[d.scene_piece_first + k];
        if (pc.full_first + pc.full_count > tap->full_count) return false;
        const rtag_scene_full* v = tap->full + pc.full_first;
        for (uint32_t n = 0; n < pc.full_count; n++) {
            lo[0] = std::min(lo[0], v[n].x); lo[1] = std::min(lo[1], v[n].y); lo[2] = std::min(lo[2], v[n].z);
            hi[0] = std::max(hi[0], v[n].x); hi[1] = std::max(hi[1], v[n].y); hi[2] = std::max(hi[2], v[n].z);
        }
    }
    const float m[3] = {(lo[0] + hi[0]) * 0.5f, (lo[1] + hi[1]) * 0.5f, (lo[2] + hi[2]) * 0.5f};
    for (const WorldHide& h : world_hide) {
        if (!(h.kinds & 2) || h.watch) continue;
        const float dx = m[0] - h.c[0], dy = m[1] - h.c[1], dz = m[2] - h.c[2];
        if (std::fabs(dz) > h.h[2]) continue;
        if (h.cylinder ? dx * dx + dy * dy <= h.h[0] * h.h[0]
                       : std::fabs(dx * h.cos_yaw + dy * h.sin_yaw) <= h.h[0] && std::fabs(-dx * h.sin_yaw + dy * h.cos_yaw) <= h.h[1])
            return true;
    }
    return false;
}

// a model's triangle all of whose corners lie in a volume that takes models (its place in the list noted)
int RtaDrawer::world_tri_hidden(const rtag_scene_full* c, float order) {
    for (size_t vi = 0; vi < world_hide.size(); vi++) {
        WorldHide& h = world_hide[vi];
        if (!(h.kinds & 2) || h.watch) continue;
        bool all = true;
        for (int i = 0; i < 3 && all; i++) {
            const float dx = c[i].x - h.c[0], dy = c[i].y - h.c[1], dz = c[i].z - h.c[2];
            if (std::fabs(dz) > h.h[2]) all = false;
            else if (h.cylinder) all = dx * dx + dy * dy <= h.h[0] * h.h[0];
            else {
                const float lx = dx * h.cos_yaw + dy * h.sin_yaw, ly = -dx * h.sin_yaw + dy * h.cos_yaw;
                all = std::fabs(lx) <= h.h[0] && std::fabs(ly) <= h.h[1];
            }
        }
        if (all) {
            if (world_hide_frame != frames) {
                world_hide_frame = frames;
                for (WorldHide& o : world_hide) o.order = -1;
            }
            if (h.order < 0 || order < h.order) h.order = order;
            return (int)vi;
        }
    }
    return -1;
}

Array RtaDrawer::get_world_hide() const {
    Array out;
    for (const WorldHide& h : world_hide) {
        Array a;
        a.push_back(world_hide_frame == frames ? h.order : -1.0f);
        a.push_back((int64_t)h.draws);
        a.push_back(h.weight > 0 ? Color((float)(h.rgb[0] / h.weight), (float)(h.rgb[1] / h.weight), (float)(h.rgb[2] / h.weight)) : Color(0, 0, 0, 0));
        a.push_back(h.weight);
        a.push_back(h.watch && frames != 0 && h.seen == frames);
        out.push_back(a);
    }
    return out;
}

// the volume that holds every corner of the draw's packets (-1 none); its place in the list and colour are noted
int RtaDrawer::world_hidden(const rtag_draw& d, const rtag_scene* tap, float order) {
    if (world_hide_frame != frames) {
        world_hide_frame = frames;
        for (WorldHide& h : world_hide) h.order = -1;
    }
    if (!tap || !d.scene_piece_count || d.scene_piece_first + d.scene_piece_count > tap->piece_count || !tap->full) return -1;
    const rtag_scene_piece* pieces = tap->pieces + d.scene_piece_first;
    // the draw's identity: its packets and where the first lies (the level's chunks do not move; a model's draw that moves
    // is looked at again)
    uint64_t key = 0x2545F4914F6CDD1Dull ^ d.scene_piece_count;
    for (uint32_t k = 0; k < d.scene_piece_count; k++) {
        key = mix64(key ^ pieces[k].mesh ^ ((uint64_t)pieces[k].full_count << 40) ^ ((uint64_t)pieces[k].kind << 60));
        if (pieces[k].full_count && pieces[k].full_first < tap->full_count) {
            const rtag_scene_full& v = tap->full[pieces[k].full_first];
            key = mix64(key ^ (uint64_t)(int64_t)std::lround(v.x * 2) ^ ((uint64_t)(int64_t)std::lround(v.y * 2) << 21) ^
                        ((uint64_t)(int64_t)std::lround(v.z * 2) << 42));
        }
    }
    if (world_watch_any) world_watch(key, d, tap);
    int found = -1;
    auto cached = world_hide_cache.find(key);
    if (cached != world_hide_cache.end()) found = cached->second;
    else {
        for (size_t vi = 0; vi < world_hide.size() && found < 0; vi++) {
            const WorldHide& h = world_hide[vi];
            if (h.watch) continue;
            bool all = true, any = false;
            for (uint32_t k = 0; k < d.scene_piece_count && all; k++) {
                const rtag_scene_piece& pc = pieces[k];
                if (!((pc.kind == 1 && (h.kinds & 1)) || (pc.kind == 2 && (h.kinds & 2)))) { all = false; break; }
                if (pc.full_first + pc.full_count > tap->full_count) { all = false; break; }
                const rtag_scene_full* v = tap->full + pc.full_first;
                for (uint32_t n = 0; n < pc.full_count; n++) {
                    const float dx = v[n].x - h.c[0], dy = v[n].y - h.c[1], dz = v[n].z - h.c[2];
                    if (std::fabs(dz) > h.h[2]) { all = false; break; }
                    if (h.cylinder) {
                        if (dx * dx + dy * dy > h.h[0] * h.h[0]) { all = false; break; }
                    } else {
                        const float lx = dx * h.cos_yaw + dy * h.sin_yaw, ly = -dx * h.sin_yaw + dy * h.cos_yaw;
                        if (std::fabs(lx) > h.h[0] || std::fabs(ly) > h.h[1]) { all = false; break; }
                    }
                    any = true;
                }
            }
            if (all && any) found = (int)vi;
        }
        world_hide_cache[key] = found;
    }
    if (found < 0) return -1;
    WorldHide& h = world_hide[found];
    if (h.order < 0 || order < h.order) h.order = order;
    h.draws++;
    world_hide_colour(found, d);
    return found;
}

// the watch-only volumes a draw is seen in: one of its level packets is a figure the volume watches (or, with none named,
// the middle of the packet's box lies inside it); they are marked drawn this frame.  The game culls far chunks itself, so a
// piece laid over the game's own surface (an overlay) is drawn only on the frames the game drew what it lies on.
void RtaDrawer::world_watch(uint64_t key, const rtag_draw& d, const rtag_scene* tap) {
    auto cached = world_watch_cache.find(key);
    if (cached == world_watch_cache.end()) {
        std::vector<int> in;
        const rtag_scene_piece* pieces = tap->pieces + d.scene_piece_first;
        for (size_t vi = 0; vi < world_hide.size(); vi++) {
            const WorldHide& h = world_hide[vi];
            if (!h.watch) continue;
            bool hit = false;
            for (uint32_t k = 0; k < d.scene_piece_count && !hit; k++) {
                const rtag_scene_piece& pc = pieces[k];
                if (pc.kind != 1 || !pc.full_count || pc.full_first + pc.full_count > tap->full_count) continue;
                if (!h.figures.empty()) {
                    hit = std::binary_search(h.figures.begin(), h.figures.end(), (uint64_t)pc.mesh);
                    continue;
                }
                float lo[3] = {1e30f, 1e30f, 1e30f}, hi[3] = {-1e30f, -1e30f, -1e30f};
                const rtag_scene_full* v = tap->full + pc.full_first;
                for (uint32_t n = 0; n < pc.full_count; n++) {
                    lo[0] = std::min(lo[0], v[n].x); lo[1] = std::min(lo[1], v[n].y); lo[2] = std::min(lo[2], v[n].z);
                    hi[0] = std::max(hi[0], v[n].x); hi[1] = std::max(hi[1], v[n].y); hi[2] = std::max(hi[2], v[n].z);
                }
                const float dx = (lo[0] + hi[0]) * 0.5f - h.c[0], dy = (lo[1] + hi[1]) * 0.5f - h.c[1], dz = (lo[2] + hi[2]) * 0.5f - h.c[2];
                if (std::fabs(dz) > h.h[2]) continue;
                hit = h.cylinder ? dx * dx + dy * dy <= h.h[0] * h.h[0]
                                 : std::fabs(dx * h.cos_yaw + dy * h.sin_yaw) <= h.h[0] && std::fabs(-dx * h.sin_yaw + dy * h.cos_yaw) <= h.h[1];
            }
            if (hit) in.push_back((int)vi);
        }
        cached = world_watch_cache.emplace(key, std::move(in)).first;
    }
    for (int vi : cached->second) {
        world_hide[vi].seen = frames;
        world_hide[vi].draws++;
    }
}

// the colour a draw left out was drawn with (its texture's mean, with the game's vertex light): the piece over it takes it on
void RtaDrawer::world_hide_colour(int vi, const rtag_draw& d) {
    if (vi < 0 || vi >= (int)world_hide.size()) return;
    WorldHide& h = world_hide[vi];
    auto wt = world_tex.find(d.texture);
    if (wt != world_tex.end() && !wt->second.pending && wt->second.opaque > 0.5f && d.depth_write && h.weight < 1e6) {
        for (int k = 0; k < 3; k++) h.rgb[k] += wt->second.mean[k];
        h.weight += 1;
    }
}

// ---- dump: the next list's packets, world space, as an OBJ file (app er world dump FILE) ------------------------------------

void RtaDrawer::world_dump(const String& path) {
    if (world_dump_file) { fclose((FILE*)world_dump_file); world_dump_file = nullptr; }
    world_dump_path = path.utf8().get_data();
    world_dump_frame = 0;
}

void RtaDrawer::world_dump_take(const rtag_draw& d, const rtag_scene* tap, size_t index) {
    if (!world_dump_file) {
        world_dump_file = fopen(world_dump_path.c_str(), "w");
        if (!world_dump_file) { world_dump_path.clear(); return; }
        world_dump_frame = frames;
        world_dump_vertices = 0;
        fprintf((FILE*)world_dump_file, "# the scene tap's packets of one list, world space (z up); g d<draw>_k<kind>_o<object>_m<packet>_t<texture>_z<depth write>_b<blend>\n");
    } else if (frames != world_dump_frame) {
        fclose((FILE*)world_dump_file);
        world_dump_file = nullptr;
        UtilityFunctions::print(vformat("rta_godot: er world: dump written to %s", String(world_dump_path.c_str())));
        world_dump_path.clear();
        return;
    }
    if (!tap || !d.scene_piece_count || d.scene_piece_first + d.scene_piece_count > tap->piece_count || !tap->full) return;
    FILE* f = (FILE*)world_dump_file;
    for (uint32_t k = 0; k < d.scene_piece_count; k++) {
        const rtag_scene_piece& pc = tap->pieces[d.scene_piece_first + k];
        if (!pc.full_count || pc.full_first + pc.full_count > tap->full_count) continue;
        auto wt = world_tex.find(d.texture);
        fprintf(f, "g d%zu_k%d_o%u_m%016llx_t%s_z%d_b%d\n", index, (int)pc.kind, pc.object, (unsigned long long)pc.mesh,
                wt != world_tex.end() && !wt->second.name.empty() ? wt->second.name.c_str() : std::to_string(d.texture).c_str(), (int)d.depth_write, (int)d.blend);
        const rtag_scene_full* v = tap->full + pc.full_first;
        for (uint32_t n = 0; n < pc.full_count; n++) fprintf(f, "v %.3f %.3f %.3f %d %d %d\n", v[n].x, v[n].y, v[n].z, v[n].r, v[n].g, v[n].b);
        for (uint32_t n = 0; n + 2 < pc.full_count; n += 3)
            fprintf(f, "f %llu %llu %llu\n", (unsigned long long)(world_dump_vertices + n + 1), (unsigned long long)(world_dump_vertices + n + 2),
                    (unsigned long long)(world_dump_vertices + n + 3));
        world_dump_vertices += pc.full_count;
    }
}
