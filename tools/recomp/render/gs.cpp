// gs.cpp - see gs.h.
#include "gs.h"
#include "worldfill.h"
#include "prof.h"
#include "xxh3_64.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>

namespace render {

// ---------------------------------------------------------------------------------------
// GS memory order, used only to turn "what was sent" into "what is sampled": a transfer
// writes pixels in the order of its own format, a texture is read in the order of its
// format, and the game sends 8-bit textures as 32-bit pixels (docs/formats/
// model-texture.md, "Why sent as 32-bit matters").  Addresses are bytes from the base.
// ---------------------------------------------------------------------------------------
static const uint8_t BLOCK32[4][8] = {{0, 1, 4, 5, 16, 17, 20, 21}, {2, 3, 6, 7, 18, 19, 22, 23},
                                      {8, 9, 12, 13, 24, 25, 28, 29}, {10, 11, 14, 15, 26, 27, 30, 31}};
static const uint8_t BLOCK4[8][4] = {{0, 2, 8, 10}, {1, 3, 9, 11}, {4, 6, 12, 14}, {5, 7, 13, 15},
                                     {16, 18, 24, 26}, {17, 19, 25, 27}, {20, 22, 28, 30}, {21, 23, 29, 31}};
static const uint8_t COL8[8] = {0, 1, 4, 5, 8, 9, 12, 13};
static const uint8_t COL16[16] = {0, 2, 8, 10, 16, 18, 24, 26, 1, 3, 9, 11, 17, 19, 25, 27};

static inline size_t addr32(int x, int y, int bw) {
    size_t page = (size_t)(y >> 5) * bw + (x >> 6);
    unsigned block = BLOCK32[(y >> 3) & 3][(x >> 3) & 7];
    int by = y & 7;
    return page * 8192 + block * 256 + ((by >> 1) * 16 + (by & 1) * 2 + COL8[x & 7]) * 4;
}
static inline size_t addr16(int x, int y, int bw) {
    size_t page = (size_t)(y >> 6) * bw + (x >> 6);
    unsigned block = BLOCK4[(y >> 3) & 7][(x >> 4) & 3];
    int by = y & 7;
    return page * 8192 + block * 256 + ((by >> 1) * 32 + (by & 1) * 4 + COL16[x & 15]) * 2;
}
static inline size_t word48(int bx, int by) {             // the word of an 8- or 4-bit texel in its block
    int r = by & 3, s = (((by + 2) >> 2) & 1) ? 4 : 0;
    return (size_t)((by >> 2) * 16 + (r & 1) * 2 + COL8[(bx & 7) ^ s]) * 4;
}
static inline size_t addr8(int x, int y, int bw) {
    size_t page = (size_t)(y >> 6) * std::max(bw >> 1, 1) + (x >> 7);
    unsigned block = BLOCK32[(y >> 4) & 3][(x >> 4) & 7];
    int bx = x & 15, by = y & 15;
    return page * 8192 + block * 256 + word48(bx, by) + ((by & 3) >> 1) + 2 * ((bx >> 3) & 1);
}
static inline size_t nibble4(int x, int y, int bw) {       // address in nibbles
    size_t page = (size_t)(y >> 7) * std::max(bw >> 1, 1) + (x >> 7);
    unsigned block = BLOCK4[(y >> 4) & 7][(x >> 5) & 3];
    int bx = x & 31, by = y & 15;
    return (page * 8192 + block * 256 + word48(bx, by)) * 2 + ((by & 3) >> 1) + 2 * ((bx >> 3) & 3);
}

enum { PSMCT32 = 0, PSMCT24 = 1, PSMCT16 = 2, PSMCT16S = 10, PSMT8 = 0x13, PSMT4 = 0x14, PSMT8H = 0x1B,
       PSMT4HL = 0x24, PSMT4HH = 0x2C };

static inline uint64_t mix64(uint64_t a, uint64_t b) {
    a ^= b;
    a *= 0x9E3779B97F4A7C15ull;
    return a ^ (a >> 29);
}
static uint64_t hash_bytes(const uint8_t* p, size_t n, uint64_t seed) {
    uint64_t h[4] = {seed ^ 0x243F6A8885A308D3ull, seed ^ 0x13198A2E03707344ull, seed ^ 0xA4093822299F31D0ull,
                     seed ^ 0x082EFA98EC4E6C89ull};
    while (n >= 32) {
        uint64_t v[4];
        memcpy(v, p, 32);
        for (int k = 0; k < 4; k++) { h[k] = (h[k] ^ v[k]) * 0x9FB21C651E98DF25ull; h[k] ^= h[k] >> 32; }
        p += 32; n -= 32;
    }
    uint64_t tail[4] = {0, 0, 0, 0};
    memcpy(tail, p, n);
    uint64_t r = n;
    for (int k = 0; k < 4; k++) r = mix64(r, h[k] ^ tail[k]);
    return r;
}

// A scratch piece of GS memory holding the rectangles of one upload set, and which of its
// 256-byte blocks were written.
struct Scratch {
    std::vector<uint8_t> mem;
    std::vector<uint8_t> written;
    void reserve(size_t bytes) {
        bytes = (bytes + 8191) & ~(size_t)8191;
        if (mem.size() < bytes) { mem.resize(bytes, 0); written.resize(bytes >> 8, 0); }
    }
    inline void put(size_t a, const uint8_t* src, size_t n) {
        if (a + n > mem.size()) reserve(a + n);
        memcpy(&mem[a], src, n);
        written[a >> 8] = 1;
    }
    inline uint8_t byte(size_t a) const { return a < mem.size() ? mem[a] : 0; }
    inline uint32_t word(size_t a) const { uint32_t v = 0; if (a + 4 <= mem.size()) memcpy(&v, &mem[a], 4); return v; }
    inline bool block_written(size_t a) const { return (a >> 8) < written.size() && written[a >> 8]; }
};

template <class Set> static void replay(const Set& set, Scratch& s) {
    for (const auto& r : set.rects) {
        const uint8_t* src = set.data.data() + r.offset;
        if (r.bytes < (size_t)r.w * r.h * (r.psm == PSMT4 ? 1 : r.psm == PSMT8 ? 2 : r.psm == PSMCT16 || r.psm == PSMCT16S ? 4 : r.psm == PSMCT24 ? 6 : 8) / 2) continue;
        switch (r.psm) {
        case PSMCT32:
            for (int y = 0; y < r.h; y++) for (int x = 0; x < r.w; x++) s.put(addr32(r.x + x, r.y + y, r.bw), src + ((size_t)y * r.w + x) * 4, 4);
            break;
        case PSMCT24:
            for (int y = 0; y < r.h; y++) for (int x = 0; x < r.w; x++) { uint8_t px[4] = {0, 0, 0, 0x80}; memcpy(px, src + ((size_t)y * r.w + x) * 3, 3); s.put(addr32(r.x + x, r.y + y, r.bw), px, 4); }
            break;
        case PSMCT16: case PSMCT16S:
            for (int y = 0; y < r.h; y++) for (int x = 0; x < r.w; x++) s.put(addr16(r.x + x, r.y + y, r.bw), src + ((size_t)y * r.w + x) * 2, 2);
            break;
        case PSMT8:
            for (int y = 0; y < r.h; y++) for (int x = 0; x < r.w; x++) s.put(addr8(r.x + x, r.y + y, r.bw), src + (size_t)y * r.w + x, 1);
            break;
        case PSMT4:
            for (int y = 0; y < r.h; y++) for (int x = 0; x < r.w; x++) {
                size_t k = (size_t)y * r.w + x, a = nibble4(r.x + x, r.y + y, r.bw);
                uint8_t v = (src[k >> 1] >> ((k & 1) * 4)) & 15;
                if ((a >> 1) >= s.mem.size()) s.reserve((a >> 1) + 1);
                uint8_t& b = s.mem[a >> 1];
                b = (a & 1) ? (uint8_t)((b & 0x0F) | (v << 4)) : (uint8_t)((b & 0xF0) | v);
                s.written[a >> 9] = 1;
            }
            break;
        default: break;
        }
    }
}

// ---------------------------------------------------------------------------------------
Gs::Gs() {
    memset(reg, 0, sizeof(reg));
    memset(vq, 0, sizeof(vq));
    reg[0x1a] = 1;                                      // PRMODECONT: attributes from PRIM
}

const char* const Gs::APPROX_NAMES[AP_COUNT] = {"alpha-test fail rule", "destination-alpha test", "destination-alpha blend", "FBA", "PABE", "(fog: applied)",
                                                 "AA1", "partial FBMSK", "COLCLAMP off", "region repeat", "texture is its own target"};

void Gs::begin_frame() {
    RTA_PROF_SCOPE(prof::P_GS_FRAME);
    frame.clear(); have_cmd = false; state_dirty = true;
    // the pictures made for the uploads of the frame before
    frame.dead_textures.insert(frame.dead_textures.end(), transient_textures.begin(), transient_textures.end());
    transient_textures.clear();
}

// ---- uploads straight into a surface ------------------------------------------------------
void Gs::upload_to_surface(uint32_t block, const Rect& r, const uint8_t* bytes) {
    if (r.w <= 0 || r.h <= 0 || r.x + r.w > 2048 || r.y + r.h > 2048) return;
    Canvas& c = canvases[block];
    int need_w = std::max(c.width, r.x + r.w), need_h = std::max(c.height, r.y + r.h);
    if (need_w != c.width || need_h != c.height) {
        std::vector<uint32_t> grown((size_t)need_w * need_h, 0);
        for (int y = 0; y < c.height; y++) memcpy(&grown[(size_t)y * need_w], &c.pixels[(size_t)y * c.width], (size_t)c.width * 4);
        c.pixels.swap(grown);
        c.width = need_w; c.height = need_h;
    }
    if (c.x1 <= c.x0) { c.x0 = r.x; c.y0 = r.y; c.x1 = r.x + r.w; c.y1 = r.y + r.h; }
    else { c.x0 = std::min(c.x0, r.x); c.y0 = std::min(c.y0, r.y); c.x1 = std::max(c.x1, r.x + r.w); c.y1 = std::max(c.y1, r.y + r.h); }
    for (int y = 0; y < r.h; y++) {
        uint32_t* to = &c.pixels[(size_t)(r.y + y) * c.width + r.x];
        const uint8_t* from = bytes + (size_t)y * r.w * (r.psm == PSMCT24 ? 3 : r.psm == PSMCT16 || r.psm == PSMCT16S ? 2 : 4);
        if (r.psm == PSMCT32) memcpy(to, from, (size_t)r.w * 4);
        else if (r.psm == PSMCT24) for (int x = 0; x < r.w; x++) to[x] = from[x * 3] | (uint32_t)from[x * 3 + 1] << 8 | (uint32_t)from[x * 3 + 2] << 16 | 0x80000000u;
        else for (int x = 0; x < r.w; x++) {
            uint32_t v = from[x * 2] | (uint32_t)from[x * 2 + 1] << 8;
            to[x] = ((v & 31) << 3) | (((v >> 5) & 31) << 11) | (((v >> 10) & 31) << 19) | ((v & 0x8000) ? 0x80000000u : 0);
        }
    }
    stats.surface_uploads++;
}

void Gs::flush_uploads() {
    if (canvases.empty()) return;
    for (auto& entry : canvases) {
        Canvas& c = entry.second;
        if (c.x1 <= c.x0) continue;
        if (have_cmd && cur.count) frame.commands.push_back(cur);
        have_cmd = false;
        state_dirty = true;
        int w = c.x1 - c.x0, h = c.y1 - c.y0;
        Target& target = target_at(entry.first, c.x1, c.y1);
        target.serial = serial++;
        from_view[target.id] = false;
        if (!target.fbw) target.fbw = (uint32_t)(c.width + 63) / 64;
        TextureData data;
        data.id = next_texture++;
        data.width = w; data.height = h;
        data.rgba.resize((size_t)w * h * 4);
        for (int y = 0; y < h; y++) memcpy(&data.rgba[(size_t)y * w * 4], &c.pixels[(size_t)(c.y0 + y) * c.width + c.x0], (size_t)w * 4);
        transient_textures.push_back(data.id);
        DrawCmd d;
        d.prim = PK_TRIANGLES;
        d.target = target.id;
        d.scissor[0] = 0; d.scissor[1] = 0; d.scissor[2] = std::max(target.width, c.x1); d.scissor[3] = std::max(target.height, c.y1);
        d.texture = data.id;
        d.tex_size[0] = (float)w; d.tex_size[1] = (float)h;
        d.tfx = 1; d.tcc = true;                        // the pixels as they are, alpha too
        d.ztst = 1; d.depth_test = true; d.depth_write = false;
        d.first = (uint32_t)frame.vertices.size();
        d.count = 6;
        static const int corner[6][2] = {{0, 0}, {1, 0}, {0, 1}, {1, 0}, {1, 1}, {0, 1}};
        for (int k = 0; k < 6; k++) {
            Vertex v;
            v.x = (float)(corner[k][0] ? c.x1 : c.x0); v.y = (float)(corner[k][1] ? c.y1 : c.y0); v.z = 0;
            v.s = (float)(corner[k][0] ? w : 0); v.t = (float)(corner[k][1] ? h : 0); v.q = 1;
            v.r = v.g = v.b = v.a = 0x80;
            frame.vertices.push_back(v);
        }
        frame.textures.push_back(std::move(data));
        frame.commands.push_back(d);
        c.x0 = c.y0 = c.x1 = c.y1 = 0;
    }
}

// Textures are known by content and the game sends its resident ones again every frame,
// so nothing says when one is gone for good: one that no draw has named for
// texture_keep_frames is given back (the backend deletes it), and made again from what the
// game sends if it comes back.
void Gs::free_unused_textures() {
    if (!texture_keep_frames) return;
    for (auto it = textures.begin(); it != textures.end();) {
        if (frames_ended - it->second.last_used > texture_keep_frames) {
            frame.dead_textures.push_back(it->second.id);
            stats.texture_bytes -= (uint64_t)it->second.width * it->second.height * 4;
            stats.textures_freed++;
            it = textures.erase(it);
        } else ++it;
    }
    // A film is a new 640 x 448 texture with every picture (the player sends it to texture
    // memory and draws it with one sprite): 300 of them would be held before the first is
    // 600 frames old, half a gigabyte.  Above the budget the textures not used in this
    // frame or the one before go first, oldest first.
    if (stats.texture_bytes > texture_budget) {
        std::vector<std::pair<uint64_t, uint64_t>> idle;    // (last used, key)
        for (auto& entry : textures) if (entry.second.last_used + 2 <= frames_ended) idle.push_back({entry.second.last_used, entry.first});
        std::sort(idle.begin(), idle.end());
        for (auto& candidate : idle) {
            if (stats.texture_bytes <= texture_budget) break;
            auto it = textures.find(candidate.second);
            frame.dead_textures.push_back(it->second.id);
            stats.texture_bytes -= (uint64_t)it->second.width * it->second.height * 4;
            stats.textures_freed++;
            textures.erase(it);
        }
    }
    stats.textures_held = textures.size();
}

void Gs::note(uint32_t kind, uint32_t value) {
    if (kind == 0xA5) { layout.set_mark(frame.vertices, (uint16_t)value); state_dirty = true; }
    else if (kind == 0xA6) note_high = value & 0xFFFF;
    else if (kind == 0xA7) {
        uint32_t bits = note_high << 16 | (value & 0xFFFF);
        float k;
        memcpy(&k, &bits, 4);
        layout.set_k(frame.vertices, k);
        state_dirty = true;
    }
    else if (kind == 0xB0) { if (world.payload.size() < 256) world.payload.push_back((uint16_t)value); }
    else if (kind == 0xB1) {
        std::vector<uint32_t> words;
        for (size_t k = 0; k + 1 < world.payload.size(); k += 2) words.push_back((uint32_t)world.payload[k] << 16 | world.payload[k + 1]);
        world.payload.clear();
        const uint32_t command = (value >> 8) & 0xFF, low = value & 0xFF;
        if (command == 1 && words.size() >= 2) {
            float n, f;
            memcpy(&n, &words[0], 4); memcpy(&f, &words[1], 4);
            world.on = (low & 1) && n > 0 && f > n;
            world.persp = world.on && (low & 2);
            world.clip = world.on && (low & 4);
            if (n > 0 && f > n) {
                // mat4_setProjection 0x165950: depth = A + B / w, 1 at the far plane and 4095.94 at the near one
                world.near_plane = n; world.far_plane = f;
                const double k = 4094.94 * f;
                world.a16 = (float)(16.0 * (4095.94 - k / (f - n)));
                world.b16 = (float)(16.0 * (k * n / (f - n)));
            }
        } else if (command == 2 && words.size() >= 21) {
            float m[16], eye[3];
            memcpy(m, words.data(), 64);
            memcpy(eye, &words[18], 12);
            draw_fill(m, eye, words[16], words[17], low);
        }
    }
}

static bool g_skip_draw = false;

// The level's fill (worldfill.h) into the list: plain triangles, depth tested like the level's
// own (a ceiling also writes depth, a skirt does not: it is the background).  A ceiling is dark,
// lighter by the wall it meets; a skirt has the clear colour, darkened, and fades out with its alpha.
void Gs::draw_fill(const float* m, const float* eye, uint32_t clear_colour, uint32_t light_level, uint32_t kinds) {
    std::shared_ptr<const FillLevel> level = current_fill();
    if (!level || level->vertices.empty()) return;
    if (state_dirty) rebuild_state();
    if (!have_cmd || !cur_wide || g_skip_draw) { world.fill_skipped++; return; }
    const float wn = world.near_plane > 0 ? world.near_plane : 18.0f, far_w = world.far_plane > 0 ? world.far_plane : 1800.0f;
    const float cx = 2048.0f - ofx * (1.0f / 16.0f), cy = 2048.0f - ofy * (1.0f / 16.0f);
    const float light = (float)(light_level ? light_level : 128) / 128.0f;
    const float clear[3] = {(float)(clear_colour & 0xFF), (float)((clear_colour >> 8) & 0xFF), (float)((clear_colour >> 16) & 0xFF)};
    struct P { float x, y, z, w, c[4]; };
    auto to_clip = [&](const float* p, P& o) {
        o.x = p[0] * m[0] + p[1] * m[4] + p[2] * m[8] + m[12];
        o.y = p[0] * m[1] + p[1] * m[5] + p[2] * m[9] + m[13];
        o.z = p[0] * m[2] + p[1] * m[6] + p[2] * m[10] + m[14];
        o.w = p[0] * m[3] + p[1] * m[7] + p[2] * m[11] + m[15];
    };
    if (cur.count) frame.commands.push_back(cur);
    world.fill_draws++;
    for (int kind = FILL_SKIRT; kind >= FILL_CEILING; kind--) {     // the skirt first: it lies behind everything
        if (!(kinds & (1u << (kind - 1)))) continue;
        DrawCmd c = cur;
        c.texture = 0; c.tex_is_target = false; c.tex_missing = 0; c.weave_half = 0; c.texa_mode = 0;
        // A skirt is a background: ground where the level has none, fading to nothing at its outer edge.  It
        // is drawn at the farthest depth and writes none, so it shows only where nothing of the level is drawn,
        // before it or after.  Until 2026-10-20 it had its own depth and wrote it: a sheet hanging over level
        // geometry the terrain it is made from does not have (firbonus's lava sea below the cliffs) hid that
        // geometry, and where its alpha was low the clear colour showed through - a band of nothing.
        c.alpha_test = false; c.depth_test = true; c.ztst = 2; c.depth_write = kind != FILL_SKIRT;
        c.blend = kind == FILL_SKIRT; c.ba = 0; c.bb = 1; c.bc = 0; c.bd = 1;
        c.mask_rgb = c.mask_a = false; c.fog = false; c.made_by = 0; c.scissor_moved = false;
        c.first = (uint32_t)frame.vertices.size();
        c.count = 0;
        for (const FillMesh& mesh : level->meshes) {
            if (mesh.kind != kind) continue;
            // the block against the view: behind the eye, beyond the far plane, or off one side
            int behind = 0, beyond = 0, left = 0, right = 0, above = 0, below = 0;
            for (int k = 0; k < 8; k++) {
                const float p[3] = {mesh.bounds[k & 1 ? 3 : 0], mesh.bounds[k & 2 ? 4 : 1], mesh.bounds[k & 4 ? 5 : 2]};
                P q;
                to_clip(p, q);
                behind += q.w < wn; beyond += q.w > far_w;
                left += q.x < -640.0f * q.w; right += q.x > 640.0f * q.w; above += q.y < -224.0f * q.w; below += q.y > 224.0f * q.w;
            }
            if (behind == 8 || beyond == 8 || left == 8 || right == 8 || above == 8 || below == 8) continue;
            if (kind == FILL_CEILING && eye[2] > mesh.bounds[5]) continue;     // the eye is over all of it
            world.fill_blocks++;
            for (uint32_t t = 0; t < mesh.count; t += 3) {
                P v[3];
                if (kind == FILL_CEILING) {     // seen from below only (its normal looks down)
                    const FillVertex& f = level->vertices[mesh.first + t];
                    if ((eye[0] - f.position[0]) * f.normal[0] + (eye[1] - f.position[1]) * f.normal[1] + (eye[2] - f.position[2]) * f.normal[2] <= 0) continue;
                }
                for (int k = 0; k < 3; k++) {
                    const FillVertex& f = level->vertices[mesh.first + t + k];
                    to_clip(f.position, v[k]);
                    if (kind == FILL_CEILING) {
                        const float g = (float)f.rgba[0] * 0.10f * light;
                        v[k].c[0] = g; v[k].c[1] = g * 0.92f; v[k].c[2] = g * 0.85f; v[k].c[3] = 128.0f;
                    } else {
                        v[k].c[0] = clear[0] * 0.6f; v[k].c[1] = clear[1] * 0.6f; v[k].c[2] = clear[2] * 0.6f; v[k].c[3] = (float)f.rgba[3];
                    }
                }
                const int in = (v[0].w >= wn) + (v[1].w >= wn) + (v[2].w >= wn);
                if (!in) continue;
                P poly[4];
                int count = 0;
                if (in == 3) { poly[0] = v[0]; poly[1] = v[1]; poly[2] = v[2]; count = 3; }
                else
                    for (int e = 0; e < 3; e++) {
                        const P& a = v[e];
                        const P& b = v[(e + 1) % 3];
                        const bool ain = a.w >= wn, bin = b.w >= wn;
                        if (ain) poly[count++] = a;
                        if (ain != bin) {
                            const float u = (wn - a.w) / (b.w - a.w);
                            P n;
                            n.x = a.x + (b.x - a.x) * u; n.y = a.y + (b.y - a.y) * u; n.z = a.z + (b.z - a.z) * u; n.w = wn;
                            for (int ch = 0; ch < 4; ch++) n.c[ch] = a.c[ch] + (b.c[ch] - a.c[ch]) * u;
                            poly[count++] = n;
                        }
                    }
                for (int f = 1; f + 1 < count; f++) {
                    const P* tri[3] = {&poly[0], &poly[f], &poly[f + 1]};
                    for (int k = 0; k < 3; k++) {
                        const P& a = *tri[k];
                        Vertex o;
                        o.x = a.x / a.w + cx; o.y = a.y / a.w + cy;
                        const float zf = a.z / a.w * (1.0f / 4096.0f);
                        o.z = kind == FILL_SKIRT ? 0.0f : zf > 0.99999994f ? 0.99999994f : zf < 0 ? 0 : zf;     // a skirt: the farthest depth
                        o.s = o.t = 0; o.q = 1;
                        o.r = (uint8_t)std::min(255.0f, a.c[0]); o.g = (uint8_t)std::min(255.0f, a.c[1]); o.b = (uint8_t)std::min(255.0f, a.c[2]); o.a = (uint8_t)std::min(255.0f, a.c[3]);
                        o.fog = 255;
                        frame.vertices.push_back(o);
                    }
                    c.count += 3;
                }
            }
        }
        if (c.count) { frame.commands.push_back(c); world.fill_triangles += c.count / 3; stats.prims += c.count / 3; }
    }
    cur.first = (uint32_t)frame.vertices.size();
    cur.count = 0;
}

// A strip of one of the mesh programs for a camera inside the world: see gs.h, WorldView.
// The programs do not convert to integers; they add 2^19 + 2^11 to X and Y and 2^65 to the
// depth and let the GS take the low bits (docs/spec/render-pipeline.md 4.3), so what lies in
// VU1 memory is the whole number: a position 3,000 pixels off the centre, a depth beyond the
// near plane, a point behind the eye (where x / w is the right projective coordinate still).
bool Gs::world_run(const uint32_t* data, uint32_t nloop, uint32_t nreg, uint64_t regs) {
    if ((prim & 7) != 4 || nloop < 3 || trace) return false;
    int uv_at = -1, rgba_at = -1;
    for (uint32_t r = 0; r + 1 < nreg; r++) {
        const unsigned d = (unsigned)((regs >> (4 * r)) & 15);
        if (d == 0x3 && uv_at < 0) uv_at = (int)r;
        else if (d == 0x1 && rgba_at < 0) rgba_at = (int)r;
        else if (d != 0xF) return false;
    }
    if (((regs >> (4 * (nreg - 1))) & 15) != 0x4 || uv_at < 0 || rgba_at < 0) return false;
    if (state_dirty) rebuild_state();
    if (!cur_wide || !cmd_tme || !cmd_fst || !cmd_iip || g_skip_draw) return false;
    if (layout.active() && layout.mode() == Layout::M_MENU3D) return false;    // a figure inside a menu has the game's own projection
    if (cur.made_by != 0 || cur.weave_half != 0) {
        DrawCmd c = cur;
        c.made_by = 0; c.weave_half = 0;
        if (cur.count) frame.commands.push_back(cur);
        c.first = (uint32_t)frame.vertices.size();
        c.count = 0;
        cur = c;
    }
    struct W { float x, y, w, zb, u, v, c[4], fog; uint32_t raw[4]; bool skip, bad; };
    const float BIAS_XY = 526336.0f, BIAS_Z = 36893488147419103232.0f, Z_UNIT = 1.0f / 70368744177664.0f;
    const float cx = 2048.0f - ofx * (1.0f / 16.0f), cy = 2048.0f - ofy * (1.0f / 16.0f);
    const float wn = world.near_plane, a16 = world.a16, b16 = world.b16, zs = zscale;
    const bool persp = world.persp, clip = world.clip;
    const size_t most = (size_t)nloop * 6;
    if (run_vertices.size() < most) run_vertices.resize(most);
    Vertex* const out = run_vertices.data();
    Vertex* o = out;
    auto put = [&](const W& a) {
        o->x = a.x + cx; o->y = a.y + cy;
        const float zf = a.zb * zs;
        o->z = zf > 0.99999994f ? 0.99999994f : zf < 0 ? 0 : zf;
        const float q = persp ? wn / a.w : 1.0f;
        o->s = a.u * q; o->t = a.v * q; o->q = q;
        o->r = (uint8_t)a.c[0]; o->g = (uint8_t)a.c[1]; o->b = (uint8_t)a.c[2]; o->a = (uint8_t)a.c[3];
        o->fog = (uint8_t)a.fog; o->pad[0] = o->pad[1] = o->pad[2] = 0;
        o++;
    };
    W v[3];
    uint64_t cut = 0, behind = 0, odd = 0;
    const size_t step = (size_t)nreg * 4;
    const uint32_t* q = data;
    for (uint32_t k = 0; k < nloop; k++, q += step) {
        W n;
        const uint32_t* uv = q + uv_at * 4;
        const uint32_t* col = q + rgba_at * 4;
        const uint32_t* p = q + step - 4;
        n.u = (float)(uv[0] & 0x3FFF) * (1.0f / 16.0f); n.v = (float)(uv[1] & 0x3FFF) * (1.0f / 16.0f);
        n.c[0] = (float)(uint8_t)col[0]; n.c[1] = (float)(uint8_t)col[1]; n.c[2] = (float)(uint8_t)col[2]; n.c[3] = (float)(uint8_t)col[3];
        n.fog = (float)(uint8_t)(p[3] >> 4);
        n.skip = (p[3] & 0x8000) != 0;
        memcpy(n.raw, p, 16);
        float fx, fy, fz;
        memcpy(&fx, &p[0], 4); memcpy(&fy, &p[1], 4); memcpy(&fz, &p[2], 4);
        n.bad = false;
        if (clip) {
            n.x = fx - BIAS_XY; n.y = fy - BIAS_XY;
            n.zb = (fz - BIAS_Z) * Z_UNIT;
            n.bad = !(fx == fx && fy == fy && fz == fz);
        } else {                                        // as the GS takes them
            n.x = (float)(p[0] & 0xFFFF) * (1.0f / 16.0f) - 2048.0f; n.y = (float)(p[1] & 0xFFFF) * (1.0f / 16.0f) - 2048.0f;
            n.zb = (float)((p[2] >> 4) & 0xFFFFFF);
        }
        const float d = n.zb - a16;
        if (d > 1e-3f || d < -1e-3f) n.w = b16 / d; else { n.w = 0; n.bad = true; }
        if (!clip && n.w < wn) n.w = wn;                // nothing comes nearer when the program has dropped what did
        v[0] = v[1]; v[1] = v[2]; v[2] = n;
        if (k < 2 || n.skip) continue;
        if (v[0].bad || v[1].bad || v[2].bad) { odd++; continue; }
        const int in = (v[0].w >= wn) + (v[1].w >= wn) + (v[2].w >= wn);
        if (in == 3) { put(v[0]); put(v[1]); put(v[2]); continue; }
        if (in == 0) { behind++; continue; }
        // cut at the near plane, in the space before the division: (x w, y w, w)
        W poly[4];
        int count = 0;
        for (int e = 0; e < 3; e++) {
            const W& a = v[e];
            const W& b = v[(e + 1) % 3];
            const bool ain = a.w >= wn, bin = b.w >= wn;
            if (ain) poly[count++] = a;
            if (ain != bin) {
                const float t = (wn - a.w) / (b.w - a.w);
                W m;
                const float X = a.x * a.w + (b.x * b.w - a.x * a.w) * t, Y = a.y * a.w + (b.y * b.w - a.y * a.w) * t;
                m.w = wn; m.x = X / wn; m.y = Y / wn; m.zb = a16 + b16 / wn;
                m.u = a.u + (b.u - a.u) * t; m.v = a.v + (b.v - a.v) * t;
                for (int ch = 0; ch < 4; ch++) m.c[ch] = a.c[ch] + (b.c[ch] - a.c[ch]) * t;
                m.fog = a.fog + (b.fog - a.fog) * t;
                m.skip = m.bad = false;
                poly[count++] = m;
            }
        }
        cut++;
        for (int f = 1; f + 1 < count; f++) { put(poly[0]); put(poly[f]); put(poly[f + 1]); }
    }
    // the registers and the queue as the run leaves them
    {
        const uint32_t* last = data + (size_t)(nloop - 1) * step;
        cur_u = last[uv_at * 4] & 0x3FFF; cur_v = last[uv_at * 4 + 1] & 0x3FFF;
        const uint32_t* col = last + rgba_at * 4;
        cur_rgba[0] = (uint8_t)col[0]; cur_rgba[1] = (uint8_t)col[1]; cur_rgba[2] = (uint8_t)col[2]; cur_rgba[3] = (uint8_t)col[3];
        cur_q = st_q;
        for (int k = 0; k < 2; k++) {
            Queued& t = vq[k];
            const W& a = v[k + 1];
            t.x = a.raw[0] & 0xFFFF; t.y = a.raw[1] & 0xFFFF; t.z = (a.raw[2] >> 4) & 0xFFFFFF; t.fog = (uint8_t)(a.raw[3] >> 4);
            t.s = cur_s; t.t = cur_t; t.q = cur_q; t.u = (uint32_t)(a.u * 16.0f); t.v = (uint32_t)(a.v * 16.0f);
            for (int ch = 0; ch < 4; ch++) t.rgba[ch] = (uint8_t)a.c[ch];
        }
        vcount = 2;
    }
    const size_t emitted = (size_t)(o - out);
    if (emitted) frame.vertices.insert(frame.vertices.end(), out, o);
    stats.reg_writes += (uint64_t)nloop * 2;
    stats.vertices += nloop;
    world.runs++; world.triangles += emitted / 3; world.cut += cut; world.behind += behind; world.odd += odd;
    if (emitted) {
        cur.count += (uint32_t)emitted;
        stats.prims += emitted / 3;
        if (cur.fog) stats.fogged += emitted / 3;
        if (cur_approx) for (int k = 0; k < AP_COUNT; k++) if (cur_approx & (1u << k)) stats.approx[k] += emitted / 3;
    }
    return true;
}

// The same for surfaces.  The shadow surface and the heat haze's piece of the picture are
// textures of the game's ring of resident textures: every time the ring hands them other
// blocks a surface is made at the new place, and the ones at the old places would stay
// for ever (dozens within minutes; at four times the console's resolution 2 MB each).
void Gs::free_unused_targets() {
    if (!texture_keep_frames) return;
    for (auto it = targets.begin(); it != targets.end();) {
        if (frames_ended - it->second.last_used > texture_keep_frames) {
            frame.dead_targets.push_back(it->second.id);
            canvases.erase(it->first);
            stats.targets_freed++;
            it = targets.erase(it);
        } else ++it;
    }
    stats.targets_held = targets.size();
}

void Gs::end_frame(uint64_t number) {
    RTA_PROF_SCOPE(prof::P_GS_FRAME);
    layout.flush(frame.vertices);
    flush_uploads();
    if (have_cmd && cur.count) frame.commands.push_back(cur);
    have_cmd = false;
    state_dirty = true;
    frame.number = number;
    frames_ended++;
    if ((frames_ended & 63) == 0) { free_unused_textures(); free_unused_targets(); }
    else if (stats.texture_bytes > texture_budget + (16u << 20)) free_unused_textures();
    int circuit = (pmode & 2) ? 1 : 0;
    uint64_t fb = dispfb[circuit];
    auto it = targets.find(((uint32_t)fb & 0x1FF) << 5);
    if (it != targets.end()) {
        it->second.last_used = frames_ended;
        frame.show_target = it->second.id;
        frame.show_rect[0] = 0; frame.show_rect[1] = 0;
        frame.show_rect[2] = it->second.width; frame.show_rect[3] = it->second.height;
    }
    stats.commands += frame.commands.size();
    // the shape the picture is meant to be seen in: the view's, or 4:3 for a film
    auto shown = from_view.find(frame.show_target);
    frame.aspect = shown == from_view.end() || shown->second ? (4.0f / 3.0f) / layout.k : 4.0f / 3.0f;
}

void Gs::privileged(uint32_t address, uint64_t value) {
    if (log_display) {
        static uint64_t last[16];
        unsigned slot = (address >> 4) & 15;
        if (address >= 0x12000000 && address < 0x12000100 && last[slot] != value && address != 0x12000090 && address != 0x12000070) {
            last[slot] = value;
            fprintf(stderr, "gs: privileged %08x = %016llx\n", address, (unsigned long long)value);
        }
    }
    switch (address) {
    case 0x12000000: pmode = value; circuits_on |= (unsigned)value & 3; break;
    case 0x12000020: smode2 = value; break;
    case 0x12000070: dispfb[0] = value; display_fbps[0][(uint32_t)value & 0x1FF] = frames_ended; break;
    case 0x12000080: display[0] = value; break;
    case 0x12000090: dispfb[1] = value; display_fbps[1][(uint32_t)value & 0x1FF] = frames_ended; break;
    case 0x120000A0: display[1] = value; break;
    default: break;
    }
}

// What the display circuit reads out of a buffer: DISPLAY's width over its magnification,
// and its height in lines of the buffer.  This game shows 640 x 224 buffers, one per
// field (SMODE2 interlaced, frame mode: 448 lines of DISPLAY are two fields of 224), and
// for a film one 640 x 448 buffer (field mode).
bool Gs::display_size(uint32_t fbp, int& width, int& height) const {
    // of a circuit that was ever switched on, and named for it within the last two seconds
    // (the start-up code names buffer 0, which is the 3-D surface, and never shows it)
    int circuit = -1;
    for (int c = 1; c >= 0 && circuit < 0; c--) {
        auto named = display_fbps[c].find(fbp);
        if ((circuits_on & (1u << c)) && named != display_fbps[c].end() && frames_ended - named->second <= 120) circuit = c;
    }
    if (circuit < 0) return false;
    uint64_t d = display[circuit];
    if (!d) return false;
    width = (int)(((d >> 32) & 0xFFF) + 1) / (int)(((d >> 23) & 15) + 1);
    height = (((int)((d >> 44) & 0x7FF) + 2) & ~1) / (int)(((d >> 27) & 3) + 1);
    if ((smode2 & 1) && (smode2 & 2)) height /= 2;
    return width > 0 && height > 0;
}

// Surfaces are known by the block they start at: a frame buffer's FBP x 32, or wherever a
// copy out of a surface was put (the heat haze's piece of the picture lies in the middle
// of texture memory, not at the start of a page).
Gs::Target& Gs::target_at(uint32_t block, int width, int height) {
    Target& t = targets[block];
    uint32_t fbp = block >> 5;
    if (!t.id) t.id = next_target++;
    t.last_used = frames_ended;
    // A buffer the display reads is as large as the display says, whatever was drawn into
    // it before: the film player shows one buffer of 448 lines, everything else two of 224,
    // at the same place.  (Other surfaces only grow.)
    int dw = 0, dh = 0;
    if (!(block & 31) && display_size(fbp, dw, dh)) {
        if (t.width != dw || t.height != dh || !t.announced) {
            t.width = dw; t.height = dh;
            t.announced = true;
            if (log_display) fprintf(stderr, "gs: target %u at block %u is %d x %d (the display's size)\n", t.id, block, t.width, t.height);
            TargetInfo info;
            info.id = t.id; info.width = t.width; info.height = t.height;
            info.screen = true;
            frame.targets.push_back(info);
        }
        return t;
    }
    if (width > t.width || height > t.height || !t.announced) {
        t.width = std::max(t.width, width);
        t.height = std::max(t.height, height);
        t.announced = true;
        if (log_display) fprintf(stderr, "gs: target %u at block %u is %d x %d\n", t.id, block, t.width, t.height);
        TargetInfo info;
        info.id = t.id; info.width = t.width; info.height = t.height;
        info.screen = t.width >= 512;
        frame.targets.push_back(info);
    }
    return t;
}

// ---- GIF ------------------------------------------------------------------------------
void Gs::gif(int path, const uint32_t* words, size_t quadwords) {
    RTA_PROF_SCOPE(path == 0 ? prof::P_GS_VU : prof::P_GS_DIRECT);
    Path& p = paths[path];
    cur_path = path;
    size_t q = 0;
    while (q < quadwords) {
        const uint32_t* w = words + q * 4;
        if (!p.nloop) {
            uint64_t lo = w[0] | (uint64_t)w[1] << 32, hi = w[2] | (uint64_t)w[3] << 32;
            p.nloop = (uint32_t)lo & 0x7FFF;
            p.eop = (lo >> 15) & 1;
            p.flg = (uint32_t)(lo >> 58) & 3;
            p.nreg = (uint32_t)(lo >> 60) & 15;
            if (!p.nreg) p.nreg = 16;
            p.regs = hi;
            p.at = 0;
            if (((lo >> 46) & 1) && p.flg == 0) write(0x00, (lo >> 47) & 0x7FF);
            stats.packets++;
            q++;
            // all of a PACKED run of triangles is here: one loop for it
            // a strip of a mesh program, for a camera inside the world (gs.h, WorldView)
            if (p.flg == 0 && world.on && path == 0 && (debug_entry == 0x42 || debug_entry == 0x44 || debug_entry == 0x46 || debug_entry == 0x48) &&
                (size_t)p.nloop * p.nreg <= quadwords - q && world_run(words + q * 4, p.nloop, p.nreg, p.regs)) {
                q += (size_t)p.nloop * p.nreg;
                p.nloop = 0;
                continue;
            }
            if (p.flg == 0 && p.nloop && fast_runs && (size_t)p.nloop * p.nreg <= quadwords - q && triangle_run(words + q * 4, p.nloop, p.nreg, p.regs)) {
                q += (size_t)p.nloop * p.nreg;
                p.nloop = 0;
            }
            continue;
        }
        if (p.flg == 0) {
            packed((uint32_t)(p.regs >> (4 * (p.at % p.nreg))) & 15, w);
            q++;
            if (++p.at >= p.nloop * p.nreg) p.nloop = 0;
        } else if (p.flg == 1) {
            uint32_t total = p.nloop * p.nreg;
            for (int half = 0; half < 2 && p.at < total; half++, p.at++)
                reglist((uint32_t)(p.regs >> (4 * (p.at % p.nreg))) & 15, w[half * 2] | (uint64_t)w[half * 2 + 1] << 32);
            q++;
            if (p.at >= total) p.nloop = 0;
        } else {
            size_t n = std::min<size_t>(p.nloop, quadwords - q);
            image_data((const uint8_t*)w, n * 16);
            p.nloop -= (uint32_t)n;
            q += n;
        }
    }
}

void Gs::xgkick(const uint8_t* vu_data, uint32_t qword) {
    RTA_PROF_SCOPE(prof::P_KICK_COPY);
    // how long the packet is, and whether it runs round the end of VU1 memory
    uint32_t at = qword & 0x3FF, used = 0;
    const uint32_t first = at;
    bool round = false;
    for (int guard = 0; guard < 64 && used < 1024; guard++) {
        uint32_t tag[4];
        memcpy(tag, vu_data + at * 16, 16);
        uint32_t nloop = tag[0] & 0x7FFF, flg = (tag[1] >> 26) & 3, nreg = (tag[1] >> 28) & 15;
        if (!nreg) nreg = 16;
        uint32_t body = flg == 0 ? nloop * nreg : flg == 1 ? (nloop * nreg + 1) / 2 : nloop;
        if (used + 1 + body > 1024) break;
        if (at + 1 + body > 0x400) round = true;
        used += 1 + body;
        at = (at + 1 + body) & 0x3FF;
        if (tag[0] & 0x8000) break;
    }
    // It is read where it lies (nothing writes VU1 memory while the GS model works: the
    // program that kicked it waits in its XGKICK), unless it runs round the end or the
    // memory is not laid out for reading words.
    if (!round && !((uintptr_t)vu_data & 3) && !copy_kicks) { xgkick_draw((const uint32_t*)(vu_data + first * 16), used, qword); return; }
    uint32_t buffer[1024 * 4];
    for (uint32_t k = 0; k < used; k++) memcpy(buffer + k * 4, vu_data + ((first + k) & 0x3FF) * 16, 16);
    xgkick_draw(buffer, used, qword);
}

void Gs::xgkick_draw(const uint32_t* buffer, uint32_t used, uint32_t qword) {
    paths[0].nloop = 0;
    if (trace > 0) {
        trace--;
        fprintf(stderr, "entry %x ", debug_entry);
        fprintf(stderr, "xgkick %03x: tag %08x %08x regs %08x %08x, %u qwords\n", qword, buffer[0], buffer[1], buffer[2], buffer[3], used);
        for (uint32_t k = 1; k < used && k < 13; k++) {
            float f[4];
            memcpy(f, buffer + k * 4, 16);
            fprintf(stderr, "   %08x %08x %08x %08x   %g %g %g %g\n", buffer[k * 4], buffer[k * 4 + 1], buffer[k * 4 + 2], buffer[k * 4 + 3], f[0], f[1], f[2], f[3]);
        }
    }
    if (time_paths) {
        timespec a, b;
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &a);
        gif(0, buffer, used);
        clock_gettime(CLOCK_THREAD_CPUTIME_ID, &b);
        stats.kick_ms += (b.tv_sec - a.tv_sec) * 1000.0 + (b.tv_nsec - a.tv_nsec) / 1e6;
    } else gif(0, buffer, used);
}

void Gs::packed(uint32_t d, const uint32_t* q) {
    switch (d) {
    case 0x0: write(0x00, q[0] & 0x7FF); break;
    case 0x1:
        cur_rgba[0] = (uint8_t)q[0]; cur_rgba[1] = (uint8_t)q[1]; cur_rgba[2] = (uint8_t)q[2]; cur_rgba[3] = (uint8_t)q[3];
        cur_q = st_q;
        stats.reg_writes++;
        break;
    case 0x2: memcpy(&cur_s, &q[0], 4); memcpy(&cur_t, &q[1], 4); memcpy(&st_q, &q[2], 4); stats.reg_writes++; break;
    case 0x3: cur_u = q[0] & 0x3FFF; cur_v = q[1] & 0x3FFF; stats.reg_writes++; break;
    case 0x4: case 0xC: {
        Queued& v = vq[vcount < 3 ? vcount : 2];
        v.x = q[0] & 0xFFFF; v.y = q[1] & 0xFFFF; v.z = (q[2] >> 4) & 0xFFFFFF;
        v.fog = (uint8_t)(q[3] >> 4);
        kick(d == 0x4 && !(q[3] & 0x8000));
        break;
    }
    case 0x5: case 0xD: {
        Queued& v = vq[vcount < 3 ? vcount : 2];
        v.x = q[0] & 0xFFFF; v.y = q[1] & 0xFFFF; v.z = q[2];
        v.fog = cur_fog;
        kick(d == 0x5 && !(q[3] & 0x8000));
        break;
    }
    case 0xE: write(q[2] & 0xFF, q[0] | (uint64_t)q[1] << 32); break;
    case 0xF: break;
    case 0xA: cur_fog = (uint8_t)(q[3] >> 4); stats.reg_writes++; break;       // FOG: the coefficient in bits 100 to 107
    default: write(d, q[0] | (uint64_t)q[1] << 32); break;      // TEX0_1/2, CLAMP_1/2
    }
}

void Gs::reglist(uint32_t d, uint64_t value) {
    if (d == 0xE || d == 0xF) return;
    write(d, value);
}

void Gs::write(uint32_t address, uint64_t value) {
    stats.reg_writes++;
    switch (address) {
    case 0x00:
        prim = (uint32_t)value & 0x7FF;
        vcount = 0;
        state_dirty = true;
        prim_serial++;
        return;
    case 0x01:
        cur_rgba[0] = (uint8_t)value; cur_rgba[1] = (uint8_t)(value >> 8); cur_rgba[2] = (uint8_t)(value >> 16); cur_rgba[3] = (uint8_t)(value >> 24);
        { uint32_t qb = (uint32_t)(value >> 32); memcpy(&cur_q, &qb, 4); }
        return;
    case 0x02: { uint32_t a = (uint32_t)value, b = (uint32_t)(value >> 32); memcpy(&cur_s, &a, 4); memcpy(&cur_t, &b, 4); return; }
    case 0x03: cur_u = (uint32_t)value & 0x3FFF; cur_v = (uint32_t)(value >> 16) & 0x3FFF; return;
    case 0x04: case 0x0C: {
        Queued& v = vq[vcount < 3 ? vcount : 2];
        v.x = (uint32_t)value & 0xFFFF; v.y = (uint32_t)(value >> 16) & 0xFFFF; v.z = (uint32_t)(value >> 32) & 0xFFFFFF;
        v.fog = (uint8_t)(value >> 56);
        kick(address == 0x04);
        return;
    }
    case 0x05: case 0x0D: {
        Queued& v = vq[vcount < 3 ? vcount : 2];
        v.x = (uint32_t)value & 0xFFFF; v.y = (uint32_t)(value >> 16) & 0xFFFF; v.z = (uint32_t)(value >> 32);
        v.fog = cur_fog;
        kick(address == 0x05);
        return;
    }
    case 0x0A: cur_fog = (uint8_t)(value >> 56); return;       // FOG
    case 0x3F: return;                                  // TEXFLUSH
    case 0x50: case 0x51: case 0x52: reg[address] = value; return;
    case 0x53:
        reg[address] = value;
        if ((value & 3) == 0) start_transfer();
        else if ((value & 3) == 2) {
            // local to local: a copy out of a surface means something here (the heat haze
            // takes a piece of the picture into a texture and draws it back displaced); what
            // it is put into becomes a surface of its own at that block
            uint64_t bb = reg[0x50], pos = reg[0x51], size = reg[0x52];
            uint32_t sbp = (uint32_t)bb & 0x3FFF, dbp = (uint32_t)(bb >> 32) & 0x3FFF;
            int w = (int)(size & 0xFFF), h = (int)((size >> 32) & 0xFFF);
            if (!canvases.empty()) flush_uploads();
            auto src = targets.find(sbp);
            if (src != targets.end() && sbp != dbp && w && h) {
                if (have_cmd && cur.count) frame.commands.push_back(cur);
                have_cmd = false;
                state_dirty = true;
                int sx = (int)(pos & 0x7FF), sy = (int)((pos >> 16) & 0x7FF), dx = (int)((pos >> 32) & 0x7FF), dy = (int)((pos >> 48) & 0x7FF);
                uint32_t source_id = src->second.id;
                src->second.last_used = frames_ended;
                Target& dst = target_at(dbp, dx + w, dy + h);
                dst.serial = serial++;
                dst.fbw = (uint32_t)(bb >> 48) & 0x3F;
                dst.psm = (uint32_t)(bb >> 56) & 0x3F;
                sets.erase(dbp);
                set_at[dbp] = 0;
                DrawCmd c;
                c.kind = CMD_COPY;
                c.texture = source_id; c.target = dst.id;
                c.copy_src[0] = sx; c.copy_src[1] = sy; c.copy_src[2] = w; c.copy_src[3] = h;
                c.copy_dst[0] = dx; c.copy_dst[1] = dy; c.copy_dst[2] = w; c.copy_dst[3] = h;
                frame.commands.push_back(c);
                stats.copies++;
            } else stats.copies_skipped++;
        }
        return;
    case 0x61: stats.finish++; return;
    case 0x60: case 0x62: return;
    default:
        if (address < 0x64) {
            if (log_display && address == 0x22 && reg[address] != value) fprintf(stderr, "gs: SCANMSK = %llu at frame %llu\n", (unsigned long long)value, (unsigned long long)frames_ended);
            if (reg[address] != value) { reg[address] = value; state_dirty = true; }
        } else stats.unknown_regs++;
        return;
    }
}

// ---- transfers ------------------------------------------------------------------------
static inline size_t bits_per_pixel(uint32_t psm) {
    switch (psm) {
    case PSMCT32: return 32; case PSMCT24: return 24; case PSMCT16: case PSMCT16S: return 16;
    case PSMT8: return 8; case PSMT4: return 4; case PSMT8H: return 8; default: return 32;
    }
}

void Gs::start_transfer() {
    RTA_PROF_SCOPE(prof::P_GS_UPLOAD);
    uint64_t bb = reg[0x50], pos = reg[0x51], size = reg[0x52];
    uint32_t dbp = (uint32_t)(bb >> 32) & 0x3FFF;
    UploadSet& set = sets[dbp];
    set_at[dbp] = 1;
    if (set.used) { set.rects.clear(); set.data.clear(); set.hash = 0; set.used = false; }
    Rect r;
    r.bw_raw = (uint32_t)(bb >> 48) & 0x3F;
    r.bw = std::max<uint32_t>(r.bw_raw, 1);
    r.psm = (uint32_t)(bb >> 56) & 0x3F;
    r.x = (int)((pos >> 32) & 0x7FF); r.y = (int)((pos >> 48) & 0x7FF);
    r.w = (int)(size & 0xFFF); r.h = (int)((size >> 32) & 0xFFF);
    r.offset = set.data.size();
    r.bytes = 0;
    set.rects.push_back(r);
    xfer.active = true; xfer.dbp = dbp; xfer.rect = set.rects.size() - 1; xfer.got = 0;
    stats.uploads++;
    // pixels for a buffer of display size (the film player's pictures) are not a texture
    {
        auto surface = targets.find(dbp);
        xfer.to_surface = surface != targets.end() && surface->second.width >= 512 && r.bw * 64 >= 512
                          && (r.psm == PSMCT32 || r.psm == PSMCT24 || r.psm == PSMCT16 || r.psm == PSMCT16S);
        if (xfer.to_surface) return;
    }
    // a texture that starts inside the blocks this one takes is gone (the game's ring of
    // sixteen resident textures hands the same blocks to one texture after another)
    int bwid = r.psm == PSMT4 ? 32 : r.psm == PSMT8 || r.psm == PSMCT16 || r.psm == PSMCT16S ? 16 : 8;
    int bhei = r.psm == PSMT4 || r.psm == PSMT8 ? 16 : 8;
    // (only the blocks the rectangle really writes: GS memory is not laid out row after
    // row, a narrow rectangle skips blocks, and the game puts other textures into the
    // blocks between - taking the whole span away lost their pictures: "image never
    // sent" for 400 to 600 draws a visit in two levels)
    if (r.w <= 0 || r.h <= 0) return;
    // (Which blocks a rectangle writes depends on its place, size and format alone, and
    // the game sends the same few hundred rectangles every frame: the sorted list is made
    // once per kind of rectangle and kept.)
    if (written_blocks.size() > 4096) written_blocks.clear();
    auto kept = written_blocks.try_emplace(std::make_pair((uint64_t)r.psm | (uint64_t)r.bw << 8 | (uint64_t)(uint32_t)r.x << 16 | (uint64_t)(uint32_t)r.y << 40,
                                                          (uint64_t)(uint32_t)r.w | (uint64_t)(uint32_t)r.h << 32));
    std::vector<uint32_t>& written = kept.first->second;
    if (kept.second) {
        for (int by = r.y / bhei; by <= (r.y + r.h - 1) / bhei; by++)
            for (int bx = r.x / bwid; bx <= (r.x + r.w - 1) / bwid; bx++) {
                int x = bx * bwid, y = by * bhei;
                size_t a = r.psm == PSMT4 ? nibble4(x, y, r.bw) >> 1 : r.psm == PSMT8 ? addr8(x, y, r.bw)
                         : r.psm == PSMCT16 || r.psm == PSMCT16S ? addr16(x, y, r.bw) : addr32(x, y, r.bw);
                written.push_back((uint32_t)(a >> 8));
            }
        std::sort(written.begin(), written.end());
    }
    if (written.empty()) return;
    // (Every set that starts behind this one in a block the rectangle writes.  Asked of a
    // table of the blocks sets start at: walking the map over the rectangle's span and
    // searching the list for each set found there cost, with making the list, about
    // 7,000 instructions an upload - as much as hashing it.)
    for (uint32_t block : written) {
        const uint32_t at = dbp + block;
        if (!block || at >= 0x4000 || !set_at[at]) continue;
        sets.erase(at);
        set_at[at] = 0;
    }
}

void Gs::image_data(const uint8_t* bytes, size_t count) {
    RTA_PROF_SCOPE(prof::P_GS_UPLOAD);
    if (!xfer.active) return;
    auto it = sets.find(xfer.dbp);
    if (it == sets.end()) { xfer.active = false; return; }
    UploadSet& set = it->second;
    Rect& r = set.rects[xfer.rect];
    size_t want = ((size_t)r.w * r.h * bits_per_pixel(r.psm) + 7) / 8;
    size_t take = std::min(count, want - xfer.got);
    set.data.insert(set.data.end(), bytes, bytes + take);
    xfer.got += take;
    stats.upload_bytes += take;
    if (xfer.got >= want && xfer.to_surface) {
        Rect done = r;
        std::vector<uint8_t> bytes(set.data.begin() + (std::ptrdiff_t)r.offset, set.data.end());
        set_at[xfer.dbp & 0x3FFF] = 0;
        sets.erase(it);                                 // nothing of it is kept as a texture
        xfer.active = false;
        if (bytes.size() >= want) upload_to_surface(xfer.dbp, done, bytes.data());
        return;
    }
    if (xfer.got >= want) {
        r.bytes = want;
        uint64_t head[2] = {(uint64_t)r.psm | (uint64_t)r.bw << 8 | (uint64_t)r.x << 16 | (uint64_t)r.y << 32,
                            (uint64_t)r.w | (uint64_t)r.h << 32};
        set.hash = mix64(mix64(set.hash, head[0]), mix64(head[1], hash_bytes(set.data.data() + r.offset, want, set.rects.size())));
        set.serial = serial++;
        xfer.active = false;
    }
}

bool Gs::palette_of(const UploadSet& set, uint32_t cpsm, uint32_t* out, int entries) {
    Scratch s;
    s.reserve(8192);
    replay(set, s);
    int bw = set.rects.empty() ? 1 : (int)set.rects[0].bw;
    for (int i = 0; i < entries; i++) {
        int px, py;
        if (entries == 256) { int p = (i & 0xE7) | ((i & 8) << 1) | ((i & 16) >> 1); px = p & 15; py = p >> 4; }
        else { px = i & 7; py = i >> 3; }
        if (cpsm == PSMCT32 || cpsm == PSMCT24) out[i] = s.word(addr32(px, py, bw));
        else {
            size_t a = addr16(px, py, bw);
            uint32_t v = s.byte(a) | (uint32_t)s.byte(a + 1) << 8;
            out[i] = ((v & 31) << 3) | (((v >> 5) & 31) << 11) | (((v >> 10) & 31) << 19) | ((v & 0x8000) ? 0x80000000u : 0);
        }
    }
    return true;
}

// The name the emulator-based build knows this texture by (its CGSH_OpenGL::RecordUpload
// and PrepareTextureByUpload, tools/play-net/play-net.patch), from what was sent:
//   figure   chained over the pieces of the upload, each XXH3 of (figure so far, where the
//            piece went, its size, XXH3 of its bytes, buffer width and format it was sent
//            in); once more with the texture's buffer width and format when the bytes are
//            read as another format than they were sent in (8-bit texels sent as 32-bit
//            pixels of half the buffer width count as their own format);
//   palette  XXH3 of the 16 or 256 colours in index order;
//   size     one piece from the corner in the texture's own format: that piece (inside
//            the named size); anything else: the smallest rectangle from the corner that
//            holds every texel the pieces cover, read in the texture's format.
void Gs::name_texture(TextureData& out, const UploadSet& set, const uint32_t* palette, int entries, uint32_t psm, uint32_t tbw_raw, uint32_t cpsm,
                      int named_w, int named_h) {
    const std::vector<Rect>& r = set.rects;
    if (r.empty() || (psm != PSMCT32 && psm != PSMT8 && psm != PSMT4)) return;
    // the pieces that build counts as one upload: a piece sent in another format or buffer
    // width, or one that lies over an earlier piece, starts a new one
    size_t start = 0;
    for (size_t i = 1; i < r.size(); i++) {
        bool further = r[i].psm == r[start].psm && r[i].bw_raw == r[start].bw_raw && i - start < 256;
        for (size_t j = start; j < i && further; j++)
            if (!(r[i].x + r[i].w <= r[j].x || r[j].x + r[j].w <= r[i].x || r[i].y + r[i].h <= r[j].y || r[j].y + r[j].h <= r[i].y)) further = false;
        if (!further) start = i;
    }
    uint64_t figure = 0;
    for (size_t i = start; i < r.size(); i++) {
        if (!r[i].bytes) return;
        uint64_t words[5] = {figure, (uint64_t)(uint32_t)r[i].y << 32 | (uint32_t)r[i].x, (uint64_t)(uint32_t)r[i].h << 32 | (uint32_t)r[i].w,
                             xxh3::hash64(set.data.data() + r[i].offset, r[i].bytes), (uint64_t)r[i].bw_raw << 32 | r[i].psm};
        figure = xxh3::hash64(words, sizeof(words));
    }
    const Rect& first = r[start];
    bool plain = r.size() - start == 1 && first.psm == psm && first.bw_raw == tbw_raw && first.x == 0 && first.y == 0;
    int w = 0, h = 0;
    if (plain) { w = std::min(first.w, named_w); h = std::min(first.h, named_h); }
    else {
        bool natural = (first.psm == psm && first.bw_raw == tbw_raw) || (psm == PSMT8 && first.psm == PSMCT32 && first.bw_raw * 2 == tbw_raw);
        if (!natural) {
            uint64_t words[2] = {figure, (uint64_t)tbw_raw << 32 | psm};
            figure = xxh3::hash64(words, sizeof(words));
        }
        // which texels the pieces cover: written, all ones, in the format they were sent in
        // and read back in the texture's
        struct { std::vector<Rect> rects; std::vector<uint8_t> data; } ones;
        size_t most = 0;
        for (size_t i = start; i < r.size(); i++) { Rect c = r[i]; c.offset = 0; ones.rects.push_back(c); most = std::max(most, c.bytes); }
        ones.data.assign(most, 0xFF);
        Scratch cover;
        cover.reserve(8192);
        replay(ones, cover);
        uint32_t tbw = std::max<uint32_t>(tbw_raw, 1);
        int bwid = psm == PSMT4 ? 32 : psm == PSMT8 ? 16 : 8, bhei = psm == PSMT4 || psm == PSMT8 ? 16 : 8;
        for (int by = 0; by < named_h; by += bhei)
            for (int bx = 0; bx < named_w; bx += bwid) {
                size_t a = psm == PSMT4 ? nibble4(bx, by, tbw) >> 1 : psm == PSMT8 ? addr8(bx, by, tbw) : addr32(bx, by, tbw);
                if (!cover.block_written(a)) continue;
                for (int y = by; y < std::min(by + bhei, named_h); y++)
                    for (int x = bx; x < std::min(bx + bwid, named_w); x++) {
                        bool covered;
                        if (psm == PSMT8) covered = cover.byte(addr8(x, y, tbw)) != 0;
                        else if (psm == PSMT4) { size_t n = nibble4(x, y, tbw); covered = ((cover.byte(n >> 1) >> ((n & 1) * 4)) & 15) != 0; }
                        else covered = cover.word(addr32(x, y, tbw)) != 0;
                        if (covered) { w = std::max(w, x + 1); h = std::max(h, y + 1); }
                    }
            }
    }
    if (w <= 0 || h <= 0) return;
    out.named = true;
    out.figure = figure;
    out.palette_figure = 0;
    if (palette && entries > 0) {
        uint32_t colours[256];
        for (int i = 0; i < entries; i++) {
            uint32_t c = palette[i];
            // a 16-bit palette: that build turns the alpha bit into 0xff
            if (cpsm == PSMCT16 || cpsm == PSMCT16S) c = (c & 0x00FFFFFF) | ((c & 0x80000000u) ? 0xFF000000u : 0);
            colours[i] = c;
        }
        out.palette_figure = xxh3::hash64(colours, (size_t)entries * 4);
    }
    out.format = psm;
    out.sent_width = w; out.sent_height = h;
    out.named_width = named_w; out.named_height = named_h;
}

Gs::Texture* Gs::texture_for(uint64_t tex0, uint64_t texa) {
    RTA_PROF_SCOPE(prof::P_GS_TEXID);
    uint32_t tbp = (uint32_t)tex0 & 0x3FFF, tbw = std::max<uint32_t>((uint32_t)(tex0 >> 14) & 0x3F, 1), psm = (uint32_t)(tex0 >> 20) & 0x3F;
    uint32_t tw = (uint32_t)(tex0 >> 26) & 15, th = (uint32_t)(tex0 >> 30) & 15;
    uint32_t cbp = (uint32_t)(tex0 >> 37) & 0x3FFF, cpsm = (uint32_t)(tex0 >> 51) & 15, csa = (uint32_t)(tex0 >> 56) & 31;
    auto image = sets.find(tbp);
    if (image == sets.end() || image->second.rects.empty() || !image->second.rects.back().bytes) return nullptr;
    bool paletted = psm == PSMT8 || psm == PSMT4 || psm == PSMT8H || psm == PSMT4HL || psm == PSMT4HH;
    const UploadSet* pal = nullptr;
    if (paletted) {
        auto p = sets.find(cbp);
        if (p == sets.end() || p->second.rects.empty()) return nullptr;
        pal = &p->second;
        p->second.used = true;
    }
    image->second.used = true;
    uint64_t key = mix64(image->second.hash, pal ? pal->hash : 0x5555);
    key = mix64(key, (uint64_t)psm | (uint64_t)tbw << 8 | (uint64_t)tw << 16 | (uint64_t)th << 20 | (uint64_t)cpsm << 24 | (uint64_t)csa << 28);
    if (psm == PSMCT24 || psm == PSMCT16 || psm == PSMCT16S) key = mix64(key, texa);
    auto found = textures.find(key);
    if (found != textures.end()) {
        stats.texture_hits++;
        // made before the game's header for it was known here (a machine that boots sends a
        // texture in the frame it loads it): ask again until there is an answer
        Texture& known = found->second;
        known.last_used = frames_ended;
        if (!known.height_known && picture_size) {
            int pw = 0, ph = 0;
            if (picture_size(tbp, pw, ph)) {
                known.height_known = true;
                if (ph > 0 && ph <= known.height) known.picture_height = ph;
            }
        }
        return &known;
    }

    // ---- make it ----
    RTA_PROF_SCOPE(prof::P_GS_TEXMAKE);
    const UploadSet& set = image->second;
    Scratch s;
    s.reserve(8192);
    replay(set, s);
    int named_w = 1 << tw, named_h = 1 << th;
    // how much of the named size was sent
    int ext_w = 0, ext_h = 0;
    bool same = true, as32 = true;
    for (const Rect& r : set.rects) {
        if (r.psm != psm && !((r.psm == PSMCT32 || r.psm == PSMCT24) && (psm == PSMCT32 || psm == PSMCT24))) same = false;
        if (r.psm != PSMCT32) as32 = false;
    }
    if (same) for (const Rect& r : set.rects) { ext_w = std::max(ext_w, r.x + r.w); ext_h = std::max(ext_h, r.y + r.h); }
    else if (psm == PSMT8 && as32) for (const Rect& r : set.rects) { ext_w = std::max(ext_w, 2 * (r.x + r.w)); ext_h = std::max(ext_h, 2 * (r.y + r.h)); }
    else {
        int bwid = psm == PSMT4 ? 32 : psm == PSMT8 || psm == PSMCT16 || psm == PSMCT16S ? 16 : 8;
        int bhei = psm == PSMT4 || psm == PSMT8 ? 16 : 8;
        for (int by = 0; by * bhei < named_h; by++)
            for (int bx = 0; bx * bwid < named_w; bx++) {
                int x = bx * bwid, y = by * bhei;
                size_t a = psm == PSMT4 ? nibble4(x, y, tbw) >> 1 : psm == PSMT8 ? addr8(x, y, tbw)
                         : psm == PSMCT16 || psm == PSMCT16S ? addr16(x, y, tbw) : addr32(x, y, tbw);
                if (s.block_written(a)) { ext_w = std::max(ext_w, x + bwid); ext_h = std::max(ext_h, y + bhei); }
            }
    }
    int width = ext_w * 2 > named_w ? named_w : std::max(ext_w, 1);
    int height = ext_h * 2 > named_h ? named_h : std::max(ext_h, 1);
    uint32_t palette[256];
    if (paletted) palette_of(*pal, cpsm, palette, psm == PSMT8 || psm == PSMT8H ? 256 : 16);
    uint8_t ta0 = (uint8_t)texa, ta1 = (uint8_t)(texa >> 32);
    bool aem = (texa >> 15) & 1;
    TextureData data;
    data.id = next_texture++;
    data.width = width; data.height = height;
    data.rgba.resize((size_t)width * height * 4);
    uint32_t* out = (uint32_t*)data.rgba.data();
    for (int y = 0; y < height; y++)
        for (int x = 0; x < width; x++) {
            uint32_t c;
            switch (psm) {
            case PSMCT32: c = s.word(addr32(x, y, tbw)); break;
            case PSMCT24: c = s.word(addr32(x, y, tbw)) & 0xFFFFFF; c |= (aem && !c) ? 0 : (uint32_t)ta0 << 24; break;
            case PSMCT16: case PSMCT16S: {
                size_t a = addr16(x, y, tbw);
                uint32_t v = s.byte(a) | (uint32_t)s.byte(a + 1) << 8;
                c = ((v & 31) << 3) | (((v >> 5) & 31) << 11) | (((v >> 10) & 31) << 19);
                c |= (v & 0x8000) ? (uint32_t)ta1 << 24 : (aem && !v) ? 0 : (uint32_t)ta0 << 24;
                break;
            }
            case PSMT8: c = palette[s.byte(addr8(x, y, tbw))]; break;
            case PSMT4: { size_t a = nibble4(x, y, tbw); c = palette[((s.byte(a >> 1) >> ((a & 1) * 4)) & 15)]; break; }
            case PSMT8H: c = palette[s.byte(addr32(x, y, tbw) + 3)]; break;
            case PSMT4HL: c = palette[s.byte(addr32(x, y, tbw) + 3) & 15]; break;
            case PSMT4HH: c = palette[s.byte(addr32(x, y, tbw) + 3) >> 4]; break;
            default: c = 0xFFFF00FF; break;
            }
            out[(size_t)y * width + x] = c;
        }
    if (trace < 0) {
        size_t a0 = 0, a80 = 0, other = 0;
        for (size_t k = 0; k < (size_t)width * height; k++) { uint8_t a = out[k] >> 24; if (a == 0) a0++; else if (a == 0x80) a80++; else other++; }
        fprintf(stderr, "texture %u: %dx%d psm %x tbw %u named %dx%d rects %zu (first %dx%d psm %x bw %u) alpha 0:%zu 80:%zu other:%zu tex0 %016llx\n", data.id, width, height, psm, tbw,
                named_w, named_h, set.rects.size(), set.rects[0].w, set.rects[0].h, set.rects[0].psm, set.rects[0].bw, a0, a80, other, (unsigned long long)tex0);
    }
    if (name_textures) name_texture(data, set, paletted ? palette : nullptr, psm == PSMT8 ? 256 : 16, psm, (uint32_t)(tex0 >> 14) & 0x3F, cpsm, named_w, named_h);
    Texture t = {data.id, width, height, 0, false, frames_ended};
    stats.texture_bytes += (uint64_t)width * height * 4;
    stats.textures_held = textures.size() + 1;
    int pw = 0, ph = 0;
    if (picture_size && picture_size(tbp, pw, ph)) {
        t.height_known = true;
        if (ph > 0 && ph <= height) t.picture_height = ph;
    }
    if (trace < 0) fprintf(stderr, "   texture %u at tbp %u: picture %d x %d by the game's header\n", t.id, tbp, pw, ph);
    frame.textures.push_back(std::move(data));
    stats.textures_made++;
    return &textures.emplace(key, t).first->second;
}

// ---- drawing --------------------------------------------------------------------------
static bool same_state(const DrawCmd& a, const DrawCmd& b) {
    return a.prim == b.prim && a.target == b.target && !memcmp(a.scissor, b.scissor, sizeof(a.scissor)) && a.texture == b.texture
        && a.tex_is_target == b.tex_is_target && a.tex_offset[0] == b.tex_offset[0] && a.tex_offset[1] == b.tex_offset[1]
        && a.tex_missing == b.tex_missing && a.tex_size[0] == b.tex_size[0] && a.tex_size[1] == b.tex_size[1]
        && a.st_scale[0] == b.st_scale[0] && a.st_scale[1] == b.st_scale[1] && a.linear == b.linear && a.wrap[0] == b.wrap[0]
        && a.wrap[1] == b.wrap[1] && !memcmp(a.region, b.region, sizeof(a.region)) && a.tfx == b.tfx && a.tcc == b.tcc
        && a.texa_mode == b.texa_mode && a.ta0 == b.ta0 && a.ta1 == b.ta1 && a.aem == b.aem
        && a.weave_half == b.weave_half && a.alpha_test == b.alpha_test && a.atst == b.atst && a.aref == b.aref && a.afail == b.afail
        && a.depth_test == b.depth_test && a.ztst == b.ztst && a.depth_write == b.depth_write && a.blend == b.blend && a.ba == b.ba
        && a.bb == b.bb && a.bc == b.bc && a.bd == b.bd && a.fix == b.fix && a.mask_rgb == b.mask_rgb && a.mask_a == b.mask_a
        && a.scissor_moved == b.scissor_moved && a.scissor_x[0] == b.scissor_x[0] && a.scissor_x[1] == b.scissor_x[1]
        && a.fog == b.fog && !memcmp(a.fog_colour, b.fog_colour, 3);
}


void Gs::rebuild_state() {
    RTA_PROF_SCOPE(prof::P_GS_STATE);
    if (!canvases.empty()) flush_uploads();             // what was sent into a surface is there before anything is drawn
    state_dirty = false;
    uint32_t attr = (reg[0x1a] & 1) ? prim : ((prim & 7) | ((uint32_t)reg[0x1b] & 0x7F8));
    unsigned ctxt = (attr >> 9) & 1;
    uint64_t frame_reg = reg[0x4c + ctxt], zbuf = reg[0x4e + ctxt], scissor = reg[0x40 + ctxt], offset = reg[0x18 + ctxt];
    uint64_t test = reg[0x47 + ctxt], alpha = reg[0x42 + ctxt], tex0 = reg[0x06 + ctxt], tex1 = reg[0x14 + ctxt], clamp = reg[0x08 + ctxt];
    DrawCmd c;
    unsigned type = prim & 7;
    c.prim = type == 0 ? PK_POINTS : type <= 2 ? PK_LINES : PK_TRIANGLES;
    cmd_iip = (attr >> 3) & 1;
    cmd_tme = (attr >> 4) & 1;
    cmd_fst = (attr >> 8) & 1;
    c.scissor[0] = (int)(scissor & 0x7FF); c.scissor[2] = (int)((scissor >> 16) & 0x7FF) + 1;
    c.scissor[1] = (int)((scissor >> 32) & 0x7FF); c.scissor[3] = (int)((scissor >> 48) & 0x7FF) + 1;
    // a surface is as wide as its buffer width says and as high as the scissor allows
    int buffer_width = (int)((frame_reg >> 16) & 0x3F) * 64;
    // (no higher than 512 lines: the GS's reset scissor is 2048 lines, a draw under it into
    // the 3-D surface during a dialogue made that surface 1280 x 2048, and from then on the
    // whole picture was drawn at a quarter of its lines - blurred, text unreadable)
    uint32_t frame_block = ((uint32_t)frame_reg & 0x1FF) << 5;
    int scissor_height = c.scissor[3];
    if (scissor_height > 512) {                         // not a surface's height: leave the surface as it is
        auto known = targets.find(frame_block);
        scissor_height = known != targets.end() && known->second.height ? known->second.height : 448;
    }
    Target& target = target_at(frame_block, buffer_width ? std::min(c.scissor[2], buffer_width) : std::min(c.scissor[2], 1280), scissor_height);
    target.fbw = (uint32_t)(frame_reg >> 16) & 0x3F;
    target.psm = (uint32_t)(frame_reg >> 24) & 0x3F;
    target.serial = serial++;
    c.target = target.id;
    ofx = (float)(offset & 0xFFFF);
    uint32_t oy = (uint32_t)(offset >> 32) & 0xFFFF;
    if (no_interlace) oy &= ~15u;
    ofy = (float)oy;
    unsigned zpsm = (unsigned)(zbuf >> 24) & 15;
    zscale = zpsm == 0 ? 1.0f / 4294967296.0f : zpsm == 1 ? 1.0f / 16777216.0f : 1.0f / 65536.0f;
    bool zmsk = (zbuf >> 32) & 1;
    // tests
    bool ate = test & 1;
    unsigned atst = (test >> 1) & 7, afail = (test >> 12) & 3;
    c.aref = (uint8_t)(test >> 4);
    c.depth_test = true;
    c.ztst = (test >> 16) & 1 ? (uint8_t)((test >> 17) & 3) : 1;
    c.depth_write = !zmsk;
    uint32_t fbmsk = (uint32_t)(frame_reg >> 32);
    c.mask_rgb = (fbmsk & 0xFFFFFF) == 0xFFFFFF;
    c.mask_a = (fbmsk >> 24) == 0xFF;
    g_skip_draw = false;
    if (ate && atst == 0) {                             // never passes: what the fail rule leaves
        if (afail == 0) g_skip_draw = true;
        else if (afail == 1) c.depth_write = false;
        else if (afail == 2) { c.mask_rgb = true; c.mask_a = true; }
        else { c.depth_write = false; c.mask_a = true; }
    } else if (ate && atst != 1) {
        c.alpha_test = true; c.atst = (uint8_t)atst; c.afail = (uint8_t)afail;
    }
    if (c.ztst == 0) g_skip_draw = true;
    // a wide picture: the scissor of 2-D things (a text box) moves with them
    cur_wide = buffer_width == 1280;
    // the game's own HUD layer switched off: what its draw functions put into the 3-D buffer without a depth test
    if (hide_edge && cur_wide && c.ztst == 1 && layout.mode() == Layout::M_EDGE) g_skip_draw = true;
    if (hide_text && cur_wide && c.ztst == 1 && layout.mode() == Layout::M_TEXT) g_skip_draw = true;
    if (cur_wide && layout.active() && ((cur_path != 0 && c.ztst == 1) || layout.mode() == Layout::M_MENU3D)) {
        float x0 = (float)c.scissor[0], x1 = (float)c.scissor[2];
        if (layout.scissor(x0, x1)) { c.scissor_moved = true; c.scissor_x[0] = x0; c.scissor_x[1] = x1; }
    }
    cur_approx = 0;
    if (c.alpha_test && afail != 0) cur_approx |= 1u << AP_AFAIL;
    if ((test >> 14) & 1) cur_approx |= 1u << AP_DATE;
    if (reg[0x4a + ctxt] & 1) cur_approx |= 1u << AP_FBA;
    if (reg[0x49] & 1) cur_approx |= 1u << AP_PABE;
    if ((attr >> 5) & 1) {
        c.fog = true;
        uint32_t fogcol = (uint32_t)reg[0x3d];
        c.fog_colour[0] = (uint8_t)fogcol; c.fog_colour[1] = (uint8_t)(fogcol >> 8); c.fog_colour[2] = (uint8_t)(fogcol >> 16);
    }
    if ((attr >> 7) & 1) cur_approx |= 1u << AP_AA1;
    if (!c.mask_rgb && (fbmsk & 0xFFFFFF)) cur_approx |= 1u << AP_FBMSK;
    if (!c.mask_a && (fbmsk >> 24)) cur_approx |= 1u << AP_FBMSK;
    if (!(reg[0x46] & 1)) cur_approx |= 1u << AP_COLCLAMP;
    // blend
    if ((attr >> 6) & 1) {
        c.blend = true;
        c.ba = alpha & 3; c.bb = (alpha >> 2) & 3; c.bc = (alpha >> 4) & 3; c.bd = (alpha >> 6) & 3;
        c.fix = (uint8_t)(alpha >> 32);
        if (c.bc == 1 && c.ba != c.bb) cur_approx |= 1u << AP_DST_ALPHA;
    }
    // texture
    if (cmd_tme) {
        uint32_t tbp = (uint32_t)tex0 & 0x3FFF;
        const Texture* t = nullptr;
        // a surface the game drew into, or a part of one: the GS cannot name a texture
        // wider than 1024, so the present pass reads the 1280-wide 3-D surface as two
        // textures, the second starting at its 640th column
        auto surface = targets.end();
        int offset_x = 0, offset_y = 0;
        if (!targets.empty()) {
            auto it = targets.upper_bound(tbp);
            if (it != targets.begin()) {
                --it;
                const Target& s = it->second;
                uint32_t blocks = tbp - it->first;
                if (!(blocks & 31)) {                   // at the surface's start or a whole number of pages into it
                    uint32_t page = blocks >> 5, fbw = s.fbw ? s.fbw : 1;
                    int page_height = s.psm == PSMCT16 || s.psm == PSMCT16S ? 64 : 32;
                    int px = (int)(page % fbw) * 64, py = (int)(page / fbw) * page_height;
                    if (px < s.width && py < s.height) { surface = it; offset_x = px; offset_y = py; }
                }
            }
        }
        auto set = sets.find(tbp);
        bool surface_newer = surface != targets.end() && (set == sets.end() || set->second.serial < surface->second.serial);
        if (!surface_newer) t = texture_for(tex0, reg[0x3b]);
        if (!t && !surface_newer && restore_texture && restore_tried.insert(tbp).second) {
            // The texture is sent again as GIF data of path 3, in the middle of whatever
            // packet is being read: that packet's path is put back afterwards.  (It was not:
            // the rest of a VU1 packet was then taken for triangles built on the CPU -
            // DrawCmd::made_by 1 - and, in a wide picture, laid out as part of the 2-D layer
            // for that frame.  The whole-run path, triangle_run, reads cur_path after the
            // state is made, so this one place corrects both.)
            int reading = cur_path;
            bool restored = restore_texture(tbp);
            cur_path = reading;
            if (restored) t = texture_for(tex0, reg[0x3b]);
        }
        cur_picture_height = t ? t->picture_height : 0;
        if (t) { c.texture = t->id; c.tex_size[0] = (float)t->width; c.tex_size[1] = (float)t->height; }
        else if (surface != targets.end() && surface->second.id != c.target) {
            surface->second.last_used = frames_ended;
            c.texture = surface->second.id; c.tex_is_target = true;
            c.tex_size[0] = (float)surface->second.width; c.tex_size[1] = (float)surface->second.height;
            c.tex_offset[0] = (float)offset_x; c.tex_offset[1] = (float)offset_y;
            // a surface read in a format without eight bits of alpha gets its alpha from
            // TEXA, as a texture of that format does
            uint32_t tpsm = (uint32_t)(tex0 >> 20) & 0x3F;
            uint64_t texa = reg[0x3b];
            c.texa_mode = tpsm == PSMCT24 ? 1 : tpsm == PSMCT16 || tpsm == PSMCT16S ? 2 : 0;
            c.ta0 = (uint8_t)texa; c.ta1 = (uint8_t)(texa >> 32); c.aem = (texa >> 15) & 1;
        } else {
            stats.texture_missing++; c.tex_missing = tbp + 1;
            if (surface != targets.end()) cur_approx |= 1u << AP_SELF_TEXTURE;
            static const bool log_missing = getenv("RTA_GS_MISSING") != nullptr;
            static std::set<uint64_t> seen;             // each texture and target once
            if (log_missing && seen.size() < 200 && seen.insert(tex0 ^ ((uint64_t)frame_reg << 40)).second) {
                uint32_t cbp = (uint32_t)(tex0 >> 37) & 0x3FFF, psm = (uint32_t)(tex0 >> 20) & 0x3F;
                auto image = sets.find(tbp);
                auto pal = sets.find(cbp);
                fprintf(stderr, "gs: frame %llu: no texture for TEX0 %016llx (tbp %u psm %x cbp %u) ctxt %u prim %x target block %u: image %s, palette %s, %s\n",
                        (unsigned long long)frames_ended, (unsigned long long)tex0, tbp, psm, cbp, ctxt, prim, ((uint32_t)frame_reg & 0x1FF) << 5,
                        image == sets.end() ? "never sent" : image->second.rects.empty() || !image->second.rects.back().bytes ? "incomplete" : "there",
                        pal == sets.end() ? "never sent" : "there",
                        surface != targets.end() ? (surface->second.id == c.target ? "it is the surface being drawn into" : "a surface is there") : "no surface there");
            }
        }
        if (c.texture) {
            c.tfx = (uint8_t)((tex0 >> 35) & 3);
            c.tcc = (tex0 >> 34) & 1;
            c.linear = (tex1 >> 5) & 1;
            c.wrap[0] = (WrapMode)(clamp & 3); c.wrap[1] = (WrapMode)((clamp >> 2) & 3);
            c.region[0] = (float)((clamp >> 4) & 0x3FF); c.region[1] = (float)((clamp >> 14) & 0x3FF);
            c.region[2] = (float)((clamp >> 24) & 0x3FF); c.region[3] = (float)((clamp >> 34) & 0x3FF);
            if (!cmd_fst) { c.st_scale[0] = (float)(1 << ((tex0 >> 26) & 15)); c.st_scale[1] = (float)(1 << ((tex0 >> 30) & 15)); }
            if (c.wrap[0] == WRAP_REGION_REPEAT || c.wrap[1] == WRAP_REGION_REPEAT) cur_approx |= 1u << AP_REGION_REPEAT;
        } else cmd_tme = false;
        if (c.texture && !cur_wide && target.width >= 512) from_view[c.target] = c.tex_is_target && c.tex_size[0] == 1280.0f;
    }
    if (have_cmd && same_state(cur, c) ) return;
    if (have_cmd && cur.count) frame.commands.push_back(cur);
    c.first = (uint32_t)frame.vertices.size();
    c.count = 0;
    cur = c;
    have_cmd = true;
}

static const bool log_far = getenv("RTA_GS_FAR") != nullptr;    // debugging: far vertices are reported (and every vertex goes the long way)

#if defined(__GNUC__) || defined(__clang__)
#define GS_ALWAYS_INLINE __attribute__((always_inline))
#else
#define GS_ALWAYS_INLINE
#endif

// The vertex a queued one becomes (what emit_vertex() makes of it, with the texture
// coordinates kick() picks), for a state that is settled.
#define GS_MAKE_VERTEX(o, vx, vy, vz, vu_, vv_, vs_, vt_, vq_, rgba_, fog_) do { \
        (o).x = ((float)(vx) - ofx) * (1.0f / 16.0f); \
        (o).y = ((float)(vy) - ofy) * (1.0f / 16.0f); \
        float zf_ = (float)(vz) * zscale; \
        (o).z = zf_ > 0.99999994f ? 0.99999994f : zf_; \
        if (!tme) { (o).s = (o).t = 0; (o).q = 1; } \
        else if (fst) { (o).s = (float)(vu_) * (1.0f / 16.0f); (o).t = (float)(vv_) * (1.0f / 16.0f); (o).q = 1; } \
        else { (o).s = (vs_); (o).t = (vt_); (o).q = (vq_); } \
        (o).r = (rgba_)[0]; (o).g = (rgba_)[1]; (o).b = (rgba_)[2]; (o).a = (rgba_)[3]; \
        (o).fog = (fog_); \
    } while (0)

bool Gs::triangle_run(const uint32_t* data, uint32_t nloop, uint32_t nreg, uint64_t regs) {
    const unsigned type = prim & 7;
    if (type < 3 || type > 5 || log_far || trace) return false;
    uint8_t desc[16];
    uint32_t vertex_regs = 0;
    for (uint32_t r = 0; r < nreg; r++) {
        desc[r] = (uint8_t)((regs >> (4 * r)) & 15);
        if (desc[r] != 0x1 && desc[r] != 0x2 && desc[r] != 0x3 && desc[r] != 0x4 && desc[r] != 0x5 && desc[r] != 0xF) return false;
        if (desc[r] == 0x4 || desc[r] == 0x5) vertex_regs++;
    }
    // Vertices are written to a piece of memory of the run's own and added to the list in
    // one piece: at most three for every vertex register of the run.
    const size_t most = (size_t)nloop * vertex_regs * 3;
    if (run_vertices.size() < most) run_vertices.resize(most);
    Vertex* const out = run_vertices.data();
    size_t out_count = 0, emitted = 0;
    // The vertices of the queue as they will be emitted, made when first needed: what they
    // are made with (offsets, depth scale, which texture coordinates) is settled by the
    // first primitive of the run that draws and does not change inside the run.
    Vertex made[3];
    bool have[3] = {false, false, false};
    bool started = false, layout_each = false;
    bool tme = false, fst = false, iip = false;
    const uint32_t* q = data;
    const uint32_t* const end = data + (size_t)nloop * nreg * 4;
    uint64_t reg_writes = 0, vertices = 0, prims = 0;
    uint32_t r = 0;
    // ---- any run, a register at a time (and every run up to its first primitive) ----
    for (; q < end; q += 4, r = r + 1 == nreg ? 0 : r + 1) {
        switch (desc[r]) {
        case 0x1:
            cur_rgba[0] = (uint8_t)q[0]; cur_rgba[1] = (uint8_t)q[1]; cur_rgba[2] = (uint8_t)q[2]; cur_rgba[3] = (uint8_t)q[3];
            cur_q = st_q;
            reg_writes++;
            continue;
        case 0x2: memcpy(&cur_s, &q[0], 4); memcpy(&cur_t, &q[1], 4); memcpy(&st_q, &q[2], 4); reg_writes++; continue;
        case 0x3: cur_u = q[0] & 0x3FFF; cur_v = q[1] & 0x3FFF; reg_writes++; continue;
        case 0xF: continue;
        default: break;                                 // XYZF2, XYZ2: a vertex
        }
        const int slot = vcount < 3 ? vcount : 2;
        Queued& v = vq[slot];
        v.x = q[0] & 0xFFFF; v.y = q[1] & 0xFFFF;
        if (desc[r] == 0x4) { v.z = (q[2] >> 4) & 0xFFFFFF; v.fog = (uint8_t)(q[3] >> 4); }
        else { v.z = q[2]; v.fog = cur_fog; }
        v.s = cur_s; v.t = cur_t; v.q = cur_q; v.u = cur_u; v.v = cur_v;
        memcpy(v.rgba, cur_rgba, 4);
        have[slot] = false;
        vcount++;
        vertices++;
        if (vcount < 3) continue;
        if (!(q[3] & 0x8000)) {                         // drawn
            if (!started) {
                started = true;
                if (state_dirty) rebuild_state();
                // (the path is read after the state is made, as kick() reads it: making
                // the state can send a texture again, which is GIF data of its own path)
                const uint8_t made_by = cur_path == 0 ? 0 : 1;
                if (!g_skip_draw && cur.made_by != made_by) {
                    DrawCmd c = cur;
                    c.made_by = made_by;
                    if (cur.count) frame.commands.push_back(cur);
                    c.first = (uint32_t)frame.vertices.size();
                    c.count = 0;
                    cur = c;
                }
                if (!g_skip_draw && cur.weave_half != 0) {
                    DrawCmd c = cur;
                    c.weave_half = 0;
                    if (cur.count) frame.commands.push_back(cur);
                    c.first = (uint32_t)frame.vertices.size();
                    c.count = 0;
                    cur = c;
                }
                // In a wide picture the 2-D layer is put back into shape primitive by
                // primitive (layout.h): everything built on the CPU, and a 3-D figure
                // inside a menu.  Triangles VU1 kicks otherwise are left as they are.
                layout_each = cur_wide && layout.active() && (cur_path != 0 || layout.mode() == Layout::M_MENU3D);
                tme = cmd_tme; fst = cmd_fst; iip = cmd_iip;
            }
            if (!g_skip_draw) {
                prims++;
                for (int k = 0; k < 3; k++) {
                    if (have[k]) continue;
                    const Queued& a = vq[k];
                    GS_MAKE_VERTEX(made[k], a.x, a.y, a.z, a.u, a.v, a.s, a.t, a.q, a.rgba, a.fog);
                    have[k] = true;
                }
                Vertex* o = out + out_count;
                o[0] = made[0]; o[1] = made[1]; o[2] = made[2];
                if (!iip) {                             // flat: the colour of the last vertex
                    o[0].r = o[1].r = made[2].r; o[0].g = o[1].g = made[2].g; o[0].b = o[1].b = made[2].b; o[0].a = o[1].a = made[2].a;
                }
                out_count += 3;
                if (layout_each) {
                    frame.vertices.insert(frame.vertices.end(), out, out + 3);
                    out_count = 0; emitted += 3;
                    layout.primitive(frame.vertices, (uint32_t)frame.vertices.size() - 3, 3, cur_path, false, cur.ztst == 1, cur.texture != 0, cur.tex_is_target, prim_serial);
                }
            }
        }
        if (type == 4) { vq[0] = vq[1]; vq[1] = vq[2]; made[0] = made[1]; made[1] = made[2]; have[0] = have[1]; have[1] = have[2]; vcount = 2; }
        else if (type == 5) { vq[1] = vq[2]; made[1] = made[2]; have[1] = have[2]; vcount = 2; }
        else vcount = 0;
        // A strip whose state is settled goes on below: there the queue is kept as made
        // vertices only, and its last two are put back into the queue when the run ends.
        if (type == 4 && started && !g_skip_draw && !layout_each && have[0] && have[1]) { q += 4; r = r + 1 == nreg ? 0 : r + 1; goto strip; }
    }
    goto done;
strip:
    {
        // The new vertex is made where it goes, and the two before it are copied from where
        // they lie - in the output, or beside it when the triangle they ended was not drawn:
        // three vertices of 32 bytes per triangle, moved as blocks.  (By address on purpose:
        // held as values the compiler kept forty separate fields in registers and shuffled
        // them around the loop.)
        Vertex beside[2];
        const Vertex* p0 = &made[0];
        const Vertex* p1 = &made[1];
        // the last two vertices of the run, as the queue holds them
        uint64_t left = (uint64_t)nloop * vertex_regs - vertices;       // vertices still to come
        Queued tail[2];
        int tails = 0;
        const float ofx = this->ofx, ofy = this->ofy, zscale = this->zscale;
        uint32_t u = cur_u, vv = cur_v;
        float s = cur_s, t = cur_t, cq = cur_q, sq = st_q;
        uint32_t rgba;                                  // the four bytes as they lie in a vertex
        memcpy(&rgba, cur_rgba, 4);
        const uint8_t reg_fog = cur_fog;
        Vertex* o = out + out_count;
        Vertex* const first_out = o;
        const uint64_t before = vertices;
        auto vertex = [&](const uint32_t* w, bool with_fog) GS_ALWAYS_INLINE {
            const uint32_t x = w[0] & 0xFFFF, y = w[1] & 0xFFFF;
            const uint32_t z = with_fog ? (w[2] >> 4) & 0xFFFFFF : w[2];
            const uint8_t fog = with_fog ? (uint8_t)(w[3] >> 4) : reg_fog;
            Vertex* n = o + 2;
            const Vertex* const p0_before = p0;
            n->x = ((float)x - ofx) * (1.0f / 16.0f);
            n->y = ((float)y - ofy) * (1.0f / 16.0f);
            float zf = (float)z * zscale;
            n->z = zf > 0.99999994f ? 0.99999994f : zf;
            if (!tme) { n->s = n->t = 0; n->q = 1; }
            else if (fst) { n->s = (float)u * (1.0f / 16.0f); n->t = (float)vv * (1.0f / 16.0f); n->q = 1; }
            else { n->s = s; n->t = t; n->q = cq; }
            memcpy(&n->r, &rgba, 4);
            const uint8_t last[4] = {fog, 0, 0, 0};
            memcpy(&n->fog, last, 4);
            p0 = p1;
            if (!(w[3] & 0x8000)) {                     // drawn
                memcpy((void*)o, (const void*)p0_before, sizeof(Vertex));
                memcpy((void*)(o + 1), (const void*)p1, sizeof(Vertex));
                if (!iip) { memcpy(&o[0].r, &rgba, 4); memcpy(&o[1].r, &rgba, 4); }      // flat: the colour of the last vertex
                p1 = n;
                o += 3;
            } else {                                    // not drawn: out of the way of the next one
                Vertex* keep = p1 == &beside[0] ? &beside[1] : &beside[0];
                memcpy((void*)keep, (const void*)n, sizeof(Vertex));
                p1 = keep;
            }
            if (left-- <= 2) {
                Queued& k = tail[tails++];
                k.x = x; k.y = y; k.z = z; k.fog = fog; k.s = s; k.t = t; k.q = cq; k.u = u; k.v = vv;
                memcpy(k.rgba, &rgba, 4);
            }
        };
        // The usual shape of a loop: texel coordinates and a colour (or only one of them, or
        // neither), unused registers, and the vertex last.  Then a loop is read as a whole.
        int uv_at = -1, rgba_at = -1;
        bool usual = r == 0 && vertex_regs == 1 && (desc[nreg - 1] == 0x4 || desc[nreg - 1] == 0x5);
        uint32_t writes_per_loop = 0;
        for (uint32_t k = 0; usual && k + 1 < nreg; k++) {
            if (desc[k] == 0x3) { uv_at = (int)k; writes_per_loop++; }
            else if (desc[k] == 0x1) { rgba_at = (int)k; writes_per_loop++; }
            else if (desc[k] != 0xF) usual = false;
        }
        if (usual) {
            const bool with_fog = desc[nreg - 1] == 0x4;
            const size_t step = (size_t)nreg * 4;
            for (; q < end; q += step) {
                if (uv_at >= 0) { u = q[uv_at * 4] & 0x3FFF; vv = q[uv_at * 4 + 1] & 0x3FFF; }
                if (rgba_at >= 0) {
                    const uint32_t* c = q + rgba_at * 4;
                    const uint8_t bytes[4] = {(uint8_t)c[0], (uint8_t)c[1], (uint8_t)c[2], (uint8_t)c[3]};
                    memcpy(&rgba, bytes, 4);
                    cq = sq;
                }
                vertex(q + step - 4, with_fog);
            }
        } else {
            for (; q < end; q += 4, r = r + 1 == nreg ? 0 : r + 1) {
                switch (desc[r]) {
                case 0x1: {
                    const uint8_t bytes[4] = {(uint8_t)q[0], (uint8_t)q[1], (uint8_t)q[2], (uint8_t)q[3]};
                    memcpy(&rgba, bytes, 4);
                    cq = sq;
                    reg_writes++;
                    break;
                }
                case 0x2: memcpy(&s, &q[0], 4); memcpy(&t, &q[1], 4); memcpy(&sq, &q[2], 4); reg_writes++; break;
                case 0x3: u = q[0] & 0x3FFF; vv = q[1] & 0x3FFF; reg_writes++; break;
                case 0xF: break;
                default: vertex(q, desc[r] == 0x4); break;
                }
            }
        }
        vertices = (uint64_t)nloop * vertex_regs - left;
        if (usual) reg_writes += (vertices - before) * writes_per_loop;
        prims += (size_t)(o - first_out) / 3;
        out_count = (size_t)(o - out);
        cur_u = u; cur_v = vv; cur_s = s; cur_t = t; cur_q = cq; st_q = sq;
        memcpy(cur_rgba, &rgba, 4);
        if (tails == 2) { vq[0] = tail[0]; vq[1] = tail[1]; }
        else if (tails == 1) { vq[0] = vq[1]; vq[1] = tail[0]; }
    }
done:
    if (out_count) { frame.vertices.insert(frame.vertices.end(), out, out + out_count); emitted += out_count; }
    stats.reg_writes += reg_writes;
    stats.vertices += vertices;
    if (emitted) {
        cur.count += (uint32_t)emitted;
        stats.prims += prims;
        if (cur.fog) stats.fogged += prims;
        if (cur_approx) for (int k = 0; k < AP_COUNT; k++) if (cur_approx & (1u << k)) stats.approx[k] += prims;
    }
    return true;
}
#undef GS_MAKE_VERTEX

void Gs::emit_vertex(const Queued& v, const DrawCmd&, float s, float t, float q, const uint8_t* rgba, uint32_t z, uint8_t fog) {
    Vertex o;
    o.x = ((float)v.x - ofx) * (1.0f / 16.0f);
    o.y = ((float)v.y - ofy) * (1.0f / 16.0f);
    {
        static int left = 40;
        if (log_far && left > 0 && (o.x > 2400 || o.y > 2000)) {
            left--;
            fprintf(stderr, "gs: far vertex %04x %04x z %08x from VU1 entry %x prim %x\n", v.x, v.y, z, debug_entry, prim);
            if (on_far_vertex) on_far_vertex();
        }
    }
    float zf = (float)z * zscale;
    o.z = zf > 0.99999994f ? 0.99999994f : zf;
    o.s = s; o.t = t; o.q = q;
    o.r = rgba[0]; o.g = rgba[1]; o.b = rgba[2]; o.a = rgba[3];
    o.fog = fog;
    frame.vertices.push_back(o);
}

void Gs::kick(bool draw) {
    Queued& v = vq[vcount < 3 ? vcount : 2];
    v.s = cur_s; v.t = cur_t; v.q = cur_q; v.u = cur_u; v.v = cur_v;
    memcpy(v.rgba, cur_rgba, 4);
    vcount++;
    stats.vertices++;
    unsigned type = prim & 7;
    static const int need[8] = {1, 2, 2, 3, 3, 3, 2, 1};
    if (vcount < need[type]) return;
    if (draw && type != 7) {
        if (state_dirty) rebuild_state();
        uint8_t made_by = type == 6 ? 2 : cur_path == 0 ? 0 : 1;
        if (!g_skip_draw && cur.made_by != made_by) {
            DrawCmd c = cur;
            c.made_by = made_by;
            if (cur.count) frame.commands.push_back(cur);
            c.first = (uint32_t)frame.vertices.size();
            c.count = 0;
            cur = c;
        }
        if (!g_skip_draw) {
            auto coords = [&](const Queued& a, float& s, float& t, float& q) {
                if (!cmd_tme) { s = t = 0; q = 1; }
                else if (cmd_fst) { s = (float)a.u * (1.0f / 16.0f); t = (float)a.v * (1.0f / 16.0f); q = 1; }
                else { s = a.s; t = a.t; q = a.q; }
            };
            stats.prims++;
            if (cur.fog) stats.fogged++;
            if (cur_approx) for (int k = 0; k < AP_COUNT; k++) if (cur_approx & (1u << k)) stats.approx[k]++;
            if (type == 6) {
                const Queued& a = vq[0];
                const Queued& b = vq[1];
                float s0, t0, q0, s1, t1, q1;
                coords(a, s0, t0, q0); coords(b, s1, t1, q1);
                if (cmd_tme && !cmd_fst) { float qq = b.q != 0 ? b.q : 1; s0 /= qq; t0 /= qq; s1 /= qq; t1 /= qq; q0 = q1 = 1; }
                float dx = ((float)b.x - (float)a.x) * (1.0f / 16.0f), dy = ((float)b.y - (float)a.y) * (1.0f / 16.0f);
                float half = 0;
                int field_shift = 0;                    // lines the woven picture lies above (-) or below (+) the sprite
                if (cmd_tme) {
                    // interface art as two stacked field pictures: half a texture row per line,
                    // all of it inside the upper or the lower half of what was sent
                    float th = cur_picture_height ? (float)cur_picture_height : cur.tex_size[1];
                    // A picture whose height the game's records did not give (the bag's item
                    // pictures: a 94 x 98 picture in a texture named 128 x 128, whose header
                    // carries no block number): a sprite that draws rows 0 to n or n to 2n at
                    // half a row a line is taken to draw one whole field of a picture 2n rows
                    // high.  (By the size that was sent the second field was looked for 15
                    // rows too low, and the item showed twice, one copy between the lines of
                    // the other.)
                    if (!cur_picture_height && cmd_fst && !cur.tex_is_target && dy != 0 && fabsf(t1 - t0) * 2 == fabsf(dy)) {
                        float rows = fabsf(t1 - t0), first = floorf(std::min(t0, t1) + 0.01f);
                        if ((first == 0 || first == rows) && rows >= 2 && 2 * rows <= cur.tex_size[1]) th = 2 * rows;
                    }
                    bool field = weave && cmd_fst && !cur.tex_is_target && dy != 0 && fabsf(t1 - t0) * 2 == fabsf(dy) && th >= 4
                                 && fmodf(th, 2) == 0 && std::max(t0, t1) <= th + 0.5f;
                    if (field) {
                        static const bool log_fields = getenv("RTA_GS_FIELDS") != nullptr;
                        if (log_fields) fprintf(stderr, "gs: field sprite y %g..%g t %g..%g picture height %d sent %g x %g tex %u TEX0 %016llx\n", (float)a.y / 16 - ofy / 16, (float)b.y / 16 - ofy / 16,
                                                t0, t1, cur_picture_height, cur.tex_size[0], cur.tex_size[1], cur.texture,
                                                (unsigned long long)reg[0x06 + (((reg[0x1a] & 1) ? prim : (uint32_t)reg[0x1b]) >> 9 & 1)]);
                        half = th * 0.5f;
                        float base = (t0 + t1) * 0.5f >= half ? half : 0;
                        float line0 = floorf(2 * (std::min(t0, t1) - base) + 0.01f);
                        // Where the picture stands.  The game draws one field per frame: in
                        // the frames of the display's even lines it reads a quarter texel in
                        // (V = 0.25 + line / 2), in those of the odd lines from the row itself.
                        // A picture whose top is on an even line of the 448 is drawn from its
                        // first field in the one and its second in the other, at the same
                        // place; one whose top is on an odd line (the HUD's name, one of its
                        // bars) is drawn from its SECOND field two lines lower in the even
                        // frames and from its first field in the odd frames.  Woven, the whole
                        // picture is drawn every frame, so it has to stand where it is on the
                        // screen, not where the field's sprite is: a line up or down in those
                        // two cases, or it hops by two lines 60 times a second.
                        static const bool hop = getenv("RTA_GS_FIELD_HOP") != nullptr;      // debugging: as it was before
                        if (no_interlace && !hop) {
                            float low = std::min(t0, t1);
                            bool quarter = fabsf(low - floorf(low) - 0.25f) < 0.05f;
                            field_shift = quarter ? (base != 0 ? -1 : 0) : (base != 0 ? 0 : 1);
                        }
                        if (t1 >= t0) { t0 = line0; t1 = line0 + fabsf(dy); } else { t1 = line0; t0 = line0 + fabsf(dy); }
                    } else if (dy != 0) { float dv = (t1 - t0) / dy * 0.5f; t0 -= dv; t1 -= dv; }
                    if (dx != 0) { float du = (s1 - s0) / dx * 0.5f; s0 -= du; s1 -= du; }
                }
                if (half != cur.weave_half) {
                    DrawCmd c = cur;
                    c.weave_half = half;
                    if (cur.count) frame.commands.push_back(cur);
                    c.first = (uint32_t)frame.vertices.size();
                    c.count = 0;
                    cur = c;
                }
                Queued c0 = a, c1 = b, c2 = a, c3 = b;
                c1.y = a.y; c2.y = b.y;                 // c0 = (ax, ay), c1 = (bx, ay), c2 = (ax, by), c3 = (bx, by)
                if (field_shift) { c0.y += field_shift * 16; c1.y += field_shift * 16; c2.y += field_shift * 16; c3.y += field_shift * 16; }
                emit_vertex(c0, cur, s0, t0, 1, b.rgba, b.z, b.fog); emit_vertex(c1, cur, s1, t0, 1, b.rgba, b.z, b.fog); emit_vertex(c2, cur, s0, t1, 1, b.rgba, b.z, b.fog);
                emit_vertex(c1, cur, s1, t0, 1, b.rgba, b.z, b.fog); emit_vertex(c3, cur, s1, t1, 1, b.rgba, b.z, b.fog); emit_vertex(c2, cur, s0, t1, 1, b.rgba, b.z, b.fog);
                cur.count += 6;
                if (cur_wide && layout.active())
                    layout.primitive(frame.vertices, (uint32_t)frame.vertices.size() - 6, 6, cur_path, true, cur.ztst == 1, cur.texture != 0, cur.tex_is_target, prim_serial);
            } else {
                if (cur.weave_half != 0) {
                    DrawCmd c = cur;
                    c.weave_half = 0;
                    if (cur.count) frame.commands.push_back(cur);
                    c.first = (uint32_t)frame.vertices.size();
                    c.count = 0;
                    cur = c;
                }
                int n = need[type];
                const uint8_t* flat = vq[n - 1].rgba;
                for (int k = 0; k < n; k++) {
                    float s, t, q;
                    coords(vq[k], s, t, q);
                    emit_vertex(vq[k], cur, s, t, q, cmd_iip ? vq[k].rgba : flat, vq[k].z, vq[k].fog);
                }
                cur.count += n;
                if (cur_wide && layout.active())
                    layout.primitive(frame.vertices, (uint32_t)frame.vertices.size() - n, n, cur_path, false, cur.ztst == 1, cur.texture != 0, cur.tex_is_target, prim_serial);
            }
        }
    }
    switch (type) {
    case 2: vq[0] = vq[1]; vcount = 1; break;                       // line strip
    case 4: vq[0] = vq[1]; vq[1] = vq[2]; vcount = 2; break;        // triangle strip
    case 5: vq[1] = vq[2]; vcount = 2; break;                       // fan
    default: vcount = 0; break;
    }
}

}  // namespace render
