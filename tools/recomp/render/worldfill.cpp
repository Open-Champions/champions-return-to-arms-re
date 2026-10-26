// worldfill.cpp - see worldfill.h.
#include "worldfill.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>
#include <mutex>

namespace render {
namespace {

const int NONE = -32768;
const int STEP = 4;             // units between the terrain's height samples
const int FINE = 16;            // a cell of the ceiling grid: 4 x 4 samples
const int COARSE = 48;          // a cell of the skirt grid: 3 x 3 fine cells
const int NO_GROUND = -2000;    // a sample at or below this is "no floor here"
const int PATH_CELL = 24;

struct Reader {
    const uint8_t* m; size_t size; uint32_t world; bool relocated;
    bool ok = true;
    // an offset the loader turns into a pointer: a place in `m`
    size_t at(uint32_t value) const { return relocated ? (size_t)(value & (uint32_t)(size - 1)) : (size_t)world + value; }   // size: the memory, a power of two
    bool fits(size_t a, size_t n) const { return a <= size && n <= size - a; }
    uint32_t u32(size_t a) { uint32_t v = 0; if (fits(a, 4)) memcpy(&v, m + a, 4); else ok = false; return v; }
    int32_t s32(size_t a) { return (int32_t)u32(a); }
    int16_t s16(size_t a) { int16_t v = 0; if (fits(a, 2)) memcpy(&v, m + a, 2); else ok = false; return v; }
};

struct Grid {
    int x0 = 0, y0 = 0, w = 0, h = 0;      // origin (in cells) and size
    bool inside(int i, int j) const { return i >= 0 && j >= 0 && i < w && j < h; }
};

void normal_of(const float* a, const float* b, const float* c, bool up, float* n) {
    float u[3] = {b[0] - a[0], b[1] - a[1], b[2] - a[2]}, v[3] = {c[0] - a[0], c[1] - a[1], c[2] - a[2]};
    n[0] = u[1] * v[2] - u[2] * v[1]; n[1] = u[2] * v[0] - u[0] * v[2]; n[2] = u[0] * v[1] - u[1] * v[0];
    float l = std::sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]);
    if (l < 1e-6f) { n[0] = n[1] = 0; n[2] = up ? 1.0f : -1.0f; return; }
    if ((n[2] > 0) != up) l = -l;
    n[0] /= l; n[1] /= l; n[2] /= l;
}

// one quad of a grid as two triangles; corner order: (0,0) (1,0) (1,1) (0,1)
void quad(std::vector<FillVertex>& out, const float p[4][3], const uint8_t shade[4], const uint8_t alpha[4], bool up) {
    static const int order[6] = {0, 1, 2, 0, 2, 3};
    for (int t = 0; t < 2; t++) {
        const float* a = p[order[t * 3]];
        const float* b = p[order[t * 3 + 1]];
        const float* c = p[order[t * 3 + 2]];
        float n[3];
        normal_of(a, b, c, up, n);
        for (int k = 0; k < 3; k++) {
            int corner = order[t * 3 + k];
            FillVertex v;
            memcpy(v.position, p[corner], 12);
            memcpy(v.normal, n, 12);
            v.uv[0] = p[corner][0] / 64.0f; v.uv[1] = p[corner][1] / 64.0f;
            v.rgba[0] = v.rgba[1] = v.rgba[2] = shade[corner]; v.rgba[3] = alpha[corner];
            out.push_back(v);
        }
    }
}

void close_mesh(FillLevel& level, uint8_t kind, uint32_t first) {
    uint32_t count = (uint32_t)level.vertices.size() - first;
    if (!count) return;
    FillMesh mesh;
    mesh.kind = kind; mesh.pad[0] = mesh.pad[1] = mesh.pad[2] = 0;
    mesh.first = first; mesh.count = count;
    for (int d = 0; d < 3; d++) { mesh.bounds[d] = 1e30f; mesh.bounds[3 + d] = -1e30f; }
    for (uint32_t k = first; k < first + count; k++)
        for (int d = 0; d < 3; d++) {
            float v = level.vertices[k].position[d];
            mesh.bounds[d] = std::min(mesh.bounds[d], v); mesh.bounds[3 + d] = std::max(mesh.bounds[3 + d], v);
        }
    level.meshes.push_back(mesh);
}

std::mutex g_lock;
std::shared_ptr<const FillLevel> g_current;

}  // namespace

void publish_fill(std::shared_ptr<const FillLevel> level) { std::lock_guard<std::mutex> hold(g_lock); g_current = std::move(level); }
std::shared_ptr<const FillLevel> current_fill() { std::lock_guard<std::mutex> hold(g_lock); return g_current; }

std::shared_ptr<const FillLevel> build_fill(const uint8_t* memory, size_t size, uint32_t world, bool relocated, const char* name, const FillOptions& opt) {
    const auto started = std::chrono::steady_clock::now();
    Reader r{memory, size, world, relocated};
    const size_t base = relocated ? (size_t)(world & (uint32_t)(size - 1)) : (size_t)world;
    if (!r.fits(base, 0x84)) return nullptr;
    const uint32_t chunks = r.u32(base), elements = r.u32(base + 0x1C);
    if (!chunks || chunks > 0xFFFF || !elements || elements > 100000) return nullptr;
    const size_t element_at = r.at(r.u32(base + 0x20));
    if (!r.fits(element_at, (size_t)elements * 0x24)) return nullptr;

    // ---- the terrain's samples as one raster, the highest ground per sample ----
    struct Element { int minx, miny, maxx, maxy; size_t field; uint32_t flags; int x, y, z; float co, si; int fx, fy, fw, fh; };
    std::vector<Element> es;
    int sx0 = INT32_MAX, sy0 = INT32_MAX, sx1 = INT32_MIN, sy1 = INT32_MIN;
    for (uint32_t i = 0; i < elements; i++) {
        size_t o = element_at + (size_t)i * 0x24;
        Element e;
        e.minx = r.s16(o); e.miny = r.s16(o + 2); e.maxx = r.s16(o + 4); e.maxy = r.s16(o + 6);
        e.field = r.at(r.u32(o + 0x0C)); e.flags = r.u32(o + 0x10);
        e.x = r.s32(o + 0x14); e.y = r.s32(o + 0x18); e.z = r.s32(o + 0x1C);
        e.co = (float)r.s16(o + 0x20) / 32767.0f; e.si = (float)r.s16(o + 0x22) / 32767.0f;
        if (!r.fits(e.field, 0x14)) return nullptr;
        e.fx = r.s32(e.field); e.fy = r.s32(e.field + 4); e.fw = (int)r.u32(e.field + 8); e.fh = (int)r.u32(e.field + 0xC);
        if (e.fw <= 0 || e.fh <= 0 || e.fw > 4096 || e.fh > 4096 || !r.fits(e.field + 0x14, (size_t)e.fw * e.fh * 2)) return nullptr;
        es.push_back(e);
        sx0 = std::min(sx0, (int)std::floor((double)e.minx / STEP) - 1); sy0 = std::min(sy0, (int)std::floor((double)e.miny / STEP) - 1);
        sx1 = std::max(sx1, (int)std::floor((double)e.maxx / STEP) + 2); sy1 = std::max(sy1, (int)std::floor((double)e.maxy / STEP) + 2);
    }
    if (!r.ok || sx1 <= sx0 || sy1 <= sy0) return nullptr;
    // whole fine cells: the raster starts and ends on multiples of COARSE
    auto down = [](int v, int m) { return (int)std::floor((double)v / m) * m; };
    const int unit0x = down(sx0 * STEP, COARSE), unit0y = down(sy0 * STEP, COARSE);
    const int unit1x = down(sx1 * STEP + COARSE - 1, COARSE), unit1y = down(sy1 * STEP + COARSE - 1, COARSE);
    const int sw = (unit1x - unit0x) / STEP, sh = (unit1y - unit0y) / STEP;
    if (sw <= 0 || sh <= 0 || (int64_t)sw * sh > 48000000) return nullptr;
    std::vector<int16_t> sample((size_t)sw * sh, (int16_t)NONE);
    for (const Element& e : es) {
        const bool mirror = e.flags & 1;
        const uint8_t* s = r.m + e.field + 0x14;
        for (int j = 0; j < e.fh; j++) {
            const float ly = (float)((e.fy + j) * STEP);
            for (int i = 0; i < e.fw; i++) {
                int16_t v;
                memcpy(&v, s + ((size_t)j * e.fw + i) * 2, 2);
                const int hgt = v >> 4;
                if (hgt <= NO_GROUND) continue;
                const float lx = (float)((e.fx + i) * STEP);
                float wx, wy;
                if (mirror) { wx = lx * e.co + ly * e.si + (float)e.x; wy = lx * e.si - ly * e.co + (float)e.y; }
                else { wx = lx * e.co - ly * e.si + (float)e.x; wy = lx * e.si + ly * e.co + (float)e.y; }
                const int px = (int)std::lround(wx / STEP) - unit0x / STEP, py = (int)std::lround(wy / STEP) - unit0y / STEP;
                if (px < 0 || py < 0 || px >= sw || py >= sh) continue;
                const int h = std::max(-32000, std::min(32000, hgt + e.z));
                int16_t& cell = sample[(size_t)py * sw + px];
                if (cell == NONE || h > cell) cell = (int16_t)h;
            }
        }
    }

    // ---- the fine grid: highest and lowest sample of each cell ----
    Grid g;
    g.x0 = unit0x / FINE; g.y0 = unit0y / FINE; g.w = sw * STEP / FINE; g.h = sh * STEP / FINE;
    const int per = FINE / STEP;
    const size_t cells = (size_t)g.w * g.h;
    std::vector<int16_t> hi(cells, (int16_t)NONE), lo(cells, (int16_t)NONE);
    for (int j = 0; j < g.h; j++)
        for (int i = 0; i < g.w; i++) {
            int a = NONE, b = NONE;
            for (int y = 0; y < per; y++)
                for (int x = 0; x < per; x++) {
                    int v = sample[(size_t)(j * per + y) * sw + i * per + x];
                    if (v == NONE) continue;
                    if (a == NONE || v > a) a = v;
                    if (b == NONE || v < b) b = v;
                }
            hi[(size_t)j * g.w + i] = (int16_t)a; lo[(size_t)j * g.w + i] = (int16_t)b;
        }

    // ---- what is drawn over each cell: the boxes of the geometry and scenery-model chunks.  The terrain is
    // what one collides with; an awning, an arch, the crown of a pillar are drawn and not in it, and a
    // ceiling has to clear them (a chunk's box is a 120-unit tile: coarse, and on the safe side) ----
    std::vector<float> drawn(cells, -1e9f);
    {
        const size_t chunk_at = r.at(r.u32(base + 0x24));
        if (r.fits(chunk_at, (size_t)chunks * 0x3C))
            for (uint32_t k = 0; k < chunks; k++) {
                const size_t o = chunk_at + (size_t)k * 0x3C;
                const uint32_t flags = r.u32(o + 0x24);
                if (flags & 0xC080) continue;                               // water, emitter, light
                if (!(flags & 0x800) && r.s16(o + 0x34) == 0) continue;     // geometry that is never drawn
                float b[6];
                memcpy(b, r.m + o + 8, 24);
                if (!(b[0] <= b[3] && b[1] <= b[4] && b[5] > -30000.0f && b[5] < 30000.0f) || b[3] - b[0] > 2000.0f || b[4] - b[1] > 2000.0f) continue;
                const int i0 = std::max(0, (int)std::floor((b[0] - (float)unit0x) / FINE)), i1 = std::min(g.w - 1, (int)std::floor((b[3] - (float)unit0x) / FINE));
                const int j0 = std::max(0, (int)std::floor((b[1] - (float)unit0y) / FINE)), j1 = std::min(g.h - 1, (int)std::floor((b[4] - (float)unit0y) / FINE));
                for (int j = j0; j <= j1; j++)
                    for (int i = i0; i <= i1; i++) { float& v = drawn[(size_t)j * g.w + i]; if (b[5] > v) v = b[5]; }
            }
    }

    // ---- the floor: flooded from the path grid's nodes over ground that does not step up or down by more than 10 a cell (32 degrees; a steeper stair has nodes of its own) ----
    std::vector<float> floor_z(cells, NAN);
    std::vector<uint32_t> queue;
    {
        const int px0 = r.s32(base + 0x28), py0 = r.s32(base + 0x2C);
        const uint32_t pw = r.u32(base + 0x30), ph = r.u32(base + 0x34);
        const uint32_t poff = r.u32(base + 0x38);
        if (poff && pw && ph && pw <= 8192 && ph <= 8192) {
            const size_t pat = r.at(poff);
            if (r.fits(pat, (size_t)pw * ph * 4))
                for (uint32_t j = 0; j < ph; j++)
                    for (uint32_t i = 0; i < pw; i++) {
                        if (!(r.u32(pat + ((size_t)j * pw + i) * 4) & 0xFF)) continue;
                        const int wx = (px0 + (int)i) * PATH_CELL, wy = (py0 + (int)j) * PATH_CELL;
                        const int spx = (wx - unit0x) / STEP, spy = (wy - unit0y) / STEP;
                        int best = NONE;
                        for (int y = spy - 1; y <= spy + 1 && best == NONE; y++)
                            for (int x = spx - 1; x <= spx + 1; x++)
                                if (x >= 0 && y >= 0 && x < sw && y < sh && sample[(size_t)y * sw + x] != NONE) { best = sample[(size_t)y * sw + x]; break; }
                        if (best == NONE) continue;
                        const int ci = (wx - unit0x) / FINE, cj = (wy - unit0y) / FINE;
                        if (!g.inside(ci, cj)) continue;
                        const size_t c = (size_t)cj * g.w + ci;
                        if (std::isnan(floor_z[c])) { floor_z[c] = (float)best; queue.push_back((uint32_t)c); }
                    }
        }
    }
    for (size_t head = 0; head < queue.size(); head++) {
        const uint32_t c = queue[head];
        const int ci = (int)(c % g.w), cj = (int)(c / g.w);
        static const int dx[4] = {1, -1, 0, 0}, dy[4] = {0, 0, 1, -1};
        for (int k = 0; k < 4; k++) {
            const int ni = ci + dx[k], nj = cj + dy[k];
            if (!g.inside(ni, nj)) continue;
            const size_t n = (size_t)nj * g.w + ni;
            if (!std::isnan(floor_z[n]) || lo[n] == NONE) continue;
            if (std::fabs((float)lo[n] - floor_z[c]) > 10.0f) continue;
            floor_z[n] = (float)lo[n];
            queue.push_back((uint32_t)n);
        }
    }

    auto level = std::make_shared<FillLevel>();
    level->name = name ? name : "";
    level->floor_area = (double)queue.size() * FINE * FINE;
    level->bounds[0] = (float)unit0x; level->bounds[1] = (float)unit0y; level->bounds[3] = (float)unit1x; level->bounds[4] = (float)unit1y;
    {
        int zmin = 32767, zmax = -32767;
        for (size_t c = 0; c < cells; c++) if (hi[c] != NONE) { zmin = std::min(zmin, (int)lo[c]); zmax = std::max(zmax, (int)hi[c]); }
        level->bounds[2] = (float)zmin; level->bounds[5] = (float)zmax;
    }

    // ---- ceilings ----
    if (opt.ceilings && !queue.empty()) {
        // walls that carry a ceiling: cells beside the floor (or floor cells with a wall in them) whose
        // top is wall_min over that floor.  Distance to the nearest one, and its lid, by a chamfer over the floor.
        std::vector<float> dist(cells, 1e9f), lid(cells, 0.0f);
        std::vector<float> rises;
        for (int j = 0; j < g.h; j++)
            for (int i = 0; i < g.w; i++) {
                const size_t c = (size_t)j * g.w + i;
                if (hi[c] == NONE) continue;
                float beside = NAN;
                if (!std::isnan(floor_z[c])) beside = floor_z[c];
                else
                    for (int y = j - 1; y <= j + 1; y++)
                        for (int x = i - 1; x <= i + 1; x++)
                            if (g.inside(x, y) && !std::isnan(floor_z[(size_t)y * g.w + x])) {
                                float f = floor_z[(size_t)y * g.w + x];
                                if (std::isnan(beside) || f < beside) beside = f;
                            }
                if (std::isnan(beside) || (float)hi[c] - beside < opt.wall_min) continue;
                // not a wall when its top is itself walked: the edge of an upper floor over a lower one (a
                // gallery, a walkway over a sunken court) would hang the lower floor's ceiling at the upper floor's feet
                bool upper_floor = false;
                for (int y = j - 2; y <= j + 2 && !upper_floor; y++)
                    for (int x = i - 2; x <= i + 2; x++)
                        if (g.inside(x, y)) { float f = floor_z[(size_t)y * g.w + x]; if (!std::isnan(f) && std::fabs(f - (float)hi[c]) <= 12.0f) { upper_floor = true; break; } }
                if (upper_floor) continue;
                dist[c] = 0; lid[c] = (float)hi[c];
                rises.push_back((float)hi[c] - beside);
            }
        level->walls = (int)rises.size();
        if (!rises.empty()) { std::nth_element(rises.begin(), rises.begin() + rises.size() / 2, rises.end()); level->lid_median = rises[rises.size() / 2]; }
        const float straight = (float)FINE, diagonal = (float)FINE * 1.41421356f;
        auto relax = [&](size_t c, int i, int j, int di, int dj, float cost) {
            const int x = i + di, y = j + dj;
            if (!g.inside(x, y)) return;
            const size_t n = (size_t)y * g.w + x;
            if (dist[n] + cost < dist[c]) { dist[c] = dist[n] + cost; lid[c] = lid[n]; }
        };
        for (int pass = 0; pass < 2; pass++) {
            for (int j = 0; j < g.h; j++)
                for (int i = 0; i < g.w; i++) {
                    const size_t c = (size_t)j * g.w + i;
                    if (std::isnan(floor_z[c]) || dist[c] == 0) continue;
                    relax(c, i, j, -1, 0, straight); relax(c, i, j, 0, -1, straight); relax(c, i, j, -1, -1, diagonal); relax(c, i, j, 1, -1, diagonal);
                }
            for (int j = g.h - 1; j >= 0; j--)
                for (int i = g.w - 1; i >= 0; i--) {
                    const size_t c = (size_t)j * g.w + i;
                    if (std::isnan(floor_z[c]) || dist[c] == 0) continue;
                    relax(c, i, j, 1, 0, straight); relax(c, i, j, 0, 1, straight); relax(c, i, j, 1, 1, diagonal); relax(c, i, j, -1, 1, diagonal);
                }
        }
        // the highest floor within 12 cells: a ceiling keeps its clearance over that one too (a pit beside a
        // gallery is not roofed below the heads of those on the gallery)
        std::vector<float> high(floor_z);
        for (int round = 0; round < 12; round++) {
            std::vector<float> next(high);
            for (int j = 1; j + 1 < g.h; j++)
                for (int i = 1; i + 1 < g.w; i++) {
                    const size_t c = (size_t)j * g.w + i;
                    if (std::isnan(floor_z[c])) continue;
                    float best = high[c];
                    static const int nx[4] = {1, -1, 0, 0}, ny[4] = {0, 0, 1, -1};
                    for (int k = 0; k < 4; k++) { float v = high[(size_t)(j + ny[k]) * g.w + i + nx[k]]; if (!std::isnan(v) && v > best) best = v; }
                    next[c] = best;
                }
            high.swap(next);
        }
        std::vector<float> top(cells, NAN);
        for (size_t c = 0; c < cells; c++) {
            if (std::isnan(floor_z[c]) || dist[c] > opt.reach) continue;
            float z = lid[c] + std::min(dist[c] * opt.vault, opt.vault_most);
            top[c] = std::max(std::max(z, high[c] + opt.clearance), drawn[c] + 2.0f);
        }
        // smoothed where two walls of different height meet over a room; a cell at a wall keeps its own
        for (int pass = 0; pass < 6; pass++) {
            std::vector<float> next(top);
            for (int j = 1; j + 1 < g.h; j++)
                for (int i = 1; i + 1 < g.w; i++) {
                    const size_t c = (size_t)j * g.w + i;
                    if (std::isnan(top[c]) || dist[c] < (float)FINE * 1.5f) continue;
                    float sum = 0; int n = 0;
                    for (int y = j - 1; y <= j + 1; y++)
                        for (int x = i - 1; x <= i + 1; x++) { float v = top[(size_t)y * g.w + x]; if (!std::isnan(v)) { sum += v; n++; } }
                    next[c] = std::max(sum / (float)n, drawn[c] + 2.0f);
                }
            top.swap(next);
        }
        // carried on over the lids and over what is neither floor nor wall (a pit, a gap in the terrain), up
        // to `over` cells from the floor: from the floor nothing of it is seen, but no hole is left at a
        // wall's top, and a camera a little over a lid still has something above it
        for (int round = 0; round < opt.over; round++) {
            std::vector<float> next(top);
            bool any = false;
            for (int j = 0; j < g.h; j++)
                for (int i = 0; i < g.w; i++) {
                    const size_t c = (size_t)j * g.w + i;
                    if (!std::isnan(top[c])) continue;
                    float best = NAN;
                    for (int y = j - 1; y <= j + 1; y++)
                        for (int x = i - 1; x <= i + 1; x++)
                            if (g.inside(x, y)) { float v = top[(size_t)y * g.w + x]; if (!std::isnan(v) && (std::isnan(best) || v > best)) best = v; }
                    if (std::isnan(best)) continue;
                    next[c] = std::max(hi[c] == NONE ? best : std::max(best, (float)hi[c] + 0.5f), drawn[c] + 2.0f);
                    dist[c] = 0;
                    any = true;
                }
            top.swap(next);
            if (!any) break;
        }
        // corners: the mean of the cells round them that have a ceiling
        const int cw = g.w + 1;
        std::vector<float> corner_z((size_t)cw * (g.h + 1), NAN), corner_s((size_t)cw * (g.h + 1), 0.0f);
        for (int j = 0; j <= g.h; j++)
            for (int i = 0; i <= g.w; i++) {
                float sum = 0, shade = 0; int n = 0;
                for (int y = j - 1; y <= j; y++)
                    for (int x = i - 1; x <= i; x++)
                        if (g.inside(x, y)) {
                            const size_t c = (size_t)y * g.w + x;
                            if (std::isnan(top[c])) continue;
                            sum += top[c]; n++;
                            shade += 255.0f - (255.0f - (float)opt.far_shade) * std::min(1.0f, dist[c] / 200.0f);
                        }
                if (n) { corner_z[(size_t)j * cw + i] = sum / (float)n; corner_s[(size_t)j * cw + i] = shade / (float)n; }
            }
        const int block = 8;
        for (int bj = 0; bj < g.h; bj += block)
            for (int bi = 0; bi < g.w; bi += block) {
                const uint32_t first = (uint32_t)level->vertices.size();
                for (int j = bj; j < std::min(bj + block, g.h); j++)
                    for (int i = bi; i < std::min(bi + block, g.w); i++) {
                        if (std::isnan(top[(size_t)j * g.w + i])) continue;
                        float p[4][3];
                        uint8_t shade[4], alpha[4] = {128, 128, 128, 128};
                        static const int ox[4] = {0, 1, 1, 0}, oy[4] = {0, 0, 1, 1};
                        for (int k = 0; k < 4; k++) {
                            const size_t v = (size_t)(j + oy[k]) * cw + i + ox[k];
                            p[k][0] = (float)((g.x0 + i + ox[k]) * FINE); p[k][1] = (float)((g.y0 + j + oy[k]) * FINE); p[k][2] = corner_z[v];
                            shade[k] = (uint8_t)corner_s[v];
                        }
                        quad(level->vertices, p, shade, alpha, false);
                        level->ceiling_area += (double)FINE * FINE;
                    }
                close_mesh(*level, FILL_CEILING, first);
            }
    }

    // ---- skirts ----
    if (opt.skirts) {
        const int ratio = COARSE / FINE;
        const int ring = (int)std::ceil(opt.skirt_width / COARSE) + 1;
        Grid s;
        s.w = g.w / ratio + 2 * ring; s.h = g.h / ratio + 2 * ring;
        s.x0 = unit0x / COARSE - ring; s.y0 = unit0y / COARSE - ring;
        const size_t n = (size_t)s.w * s.h;
        std::vector<int16_t> top(n, (int16_t)NONE);
        std::vector<float> near_floor(n, NAN);
        for (int j = 0; j < g.h; j++)
            for (int i = 0; i < g.w; i++) {
                const size_t c = (size_t)j * g.w + i;
                if (hi[c] == NONE) continue;
                const size_t k = (size_t)(j / ratio + ring) * s.w + i / ratio + ring;
                if (top[k] == NONE || hi[c] > top[k]) top[k] = hi[c];
                if (!std::isnan(floor_z[c]) && (std::isnan(near_floor[k]) || floor_z[c] < near_floor[k])) near_floor[k] = floor_z[c];
            }
        // outside: empty cells reached from the border
        std::vector<uint8_t> outside(n, 0);
        std::vector<uint32_t> q;
        for (int j = 0; j < s.h; j++)
            for (int i = 0; i < s.w; i++)
                if ((i == 0 || j == 0 || i == s.w - 1 || j == s.h - 1) && top[(size_t)j * s.w + i] == NONE) { outside[(size_t)j * s.w + i] = 1; q.push_back((uint32_t)((size_t)j * s.w + i)); }
        static const int dx[4] = {1, -1, 0, 0}, dy[4] = {0, 0, 1, -1};
        for (size_t head = 0; head < q.size(); head++) {
            const int ci = (int)(q[head] % s.w), cj = (int)(q[head] / s.w);
            for (int k = 0; k < 4; k++) {
                const int ni = ci + dx[k], nj = cj + dy[k];
                if (!s.inside(ni, nj)) continue;
                const size_t m = (size_t)nj * s.w + ni;
                if (outside[m] || top[m] != NONE) continue;
                outside[m] = 1; q.push_back((uint32_t)m);
            }
        }
        // rings outward from the rim; a rim cell that is a floor's edge (not rim_min over the floor near it) starts none
        std::vector<float> d(n, 1e9f), z(n, 0.0f);
        std::vector<uint8_t> lidded(n, 0);
        q.clear();
        for (int j = 0; j < s.h; j++)
            for (int i = 0; i < s.w; i++) {
                const size_t c = (size_t)j * s.w + i;
                if (top[c] == NONE) continue;
                bool rim = false;
                for (int k = 0; k < 4; k++) { const int ni = i + dx[k], nj = j + dy[k]; if (s.inside(ni, nj) && outside[(size_t)nj * s.w + ni]) rim = true; }
                if (!rim) continue;
                float f = NAN;
                for (int y = j - 2; y <= j + 2; y++)
                    for (int x = i - 2; x <= i + 2; x++)
                        if (s.inside(x, y)) { float v = near_floor[(size_t)y * s.w + x]; if (!std::isnan(v) && (std::isnan(f) || v < f)) f = v; }
                d[c] = 0; z[c] = (float)top[c];
                lidded[c] = std::isnan(f) || (float)top[c] - f >= opt.rim_min;
                q.push_back((uint32_t)c);
            }
        for (size_t head = 0; head < q.size(); head++) {
            const uint32_t c = q[head];
            const int ci = (int)(c % s.w), cj = (int)(c / s.w);
            for (int k = 0; k < 4; k++) {
                const int ni = ci + dx[k], nj = cj + dy[k];
                if (!s.inside(ni, nj)) continue;
                const size_t m = (size_t)nj * s.w + ni;
                if (!outside[m] || d[m] <= d[c] + (float)COARSE) continue;
                d[m] = d[c] + (float)COARSE; z[m] = z[c]; lidded[m] = lidded[c];
                q.push_back((uint32_t)m);
            }
        }
        auto skirted = [&](int i, int j) { if (!s.inside(i, j)) return false; const size_t c = (size_t)j * s.w + i; return outside[c] && lidded[c] && d[c] <= opt.skirt_width; };
        const int cw = s.w + 1;
        std::vector<float> corner_z((size_t)cw * (s.h + 1), 0.0f), corner_a((size_t)cw * (s.h + 1), 0.0f);
        for (int j = 0; j <= s.h; j++)
            for (int i = 0; i <= s.w; i++) {
                float sum = 0, alpha = 0; int cnt = 0; bool at_rim = false; float rim_z = 0; int rims = 0;
                for (int y = j - 1; y <= j; y++)
                    for (int x = i - 1; x <= i; x++) {
                        if (!s.inside(x, y)) { continue; }
                        const size_t c = (size_t)y * s.w + x;
                        if (skirted(x, y)) { sum += z[c] - opt.skirt_drop * d[c]; alpha += 128.0f * std::max(0.0f, 1.0f - d[c] / opt.skirt_width); cnt++; }
                        else if (top[c] != NONE && d[c] == 0 && lidded[c]) { at_rim = true; rim_z += (float)top[c]; rims++; }
                    }
                const size_t v = (size_t)j * cw + i;
                if (at_rim) { corner_z[v] = rim_z / (float)rims; corner_a[v] = 128.0f; }       // fastened to the lid it continues
                else if (cnt) { corner_z[v] = sum / (float)cnt; corner_a[v] = cnt == 4 ? alpha / 4.0f : 0.0f; }     // a corner on the outer edge fades to nothing
            }
        const int block = 4;
        for (int bj = 0; bj < s.h; bj += block)
            for (int bi = 0; bi < s.w; bi += block) {
                const uint32_t first = (uint32_t)level->vertices.size();
                for (int j = bj; j < std::min(bj + block, s.h); j++)
                    for (int i = bi; i < std::min(bi + block, s.w); i++) {
                        if (!skirted(i, j)) continue;
                        float p[4][3];
                        uint8_t shade[4] = {255, 255, 255, 255}, alpha[4];
                        static const int ox[4] = {0, 1, 1, 0}, oy[4] = {0, 0, 1, 1};
                        for (int k = 0; k < 4; k++) {
                            const size_t v = (size_t)(j + oy[k]) * cw + i + ox[k];
                            p[k][0] = (float)((s.x0 + i + ox[k]) * COARSE); p[k][1] = (float)((s.y0 + j + oy[k]) * COARSE); p[k][2] = corner_z[v];
                            alpha[k] = (uint8_t)std::max(0.0f, std::min(128.0f, corner_a[v]));
                        }
                        quad(level->vertices, p, shade, alpha, true);
                        level->skirt_area += (double)COARSE * COARSE;
                    }
                close_mesh(*level, FILL_SKIRT, first);
            }
    }

    // ---- rims: under a floor that ends over nothing ----
    // On a grid of RIM-unit cells reaching rim_width beyond the level: the cells with no terrain at all that are not water
    // are "empty"; a terrain cell beside one is an edge, which starts a fill when it is a floor's (walked ground within two
    // cells, not rim_min under the top) - or any edge when no skirt is made.  The fill is carried out over the empty cells
    // (chamfer distance), falling with the distance.  The edge cells are filled too, at the floor's height less 4, so
    // that seen over the edge it begins where the ground ends inside a cell that is only partly ground; where there is
    // ground the level's own covers it (it is a background, drawn first, writing no depth).  Corners beside ground that
    // is not an edge are fastened there.
    if (opt.rims && !queue.empty()) {
        const int RIM = 32;
        const int ring = (int)std::ceil(opt.rim_width / RIM) + 2;
        Grid t;
        t.x0 = (int)std::floor((double)unit0x / RIM) - ring; t.y0 = (int)std::floor((double)unit0y / RIM) - ring;
        t.w = (int)std::ceil((double)(unit1x - unit0x) / RIM) + 2 * ring; t.h = (int)std::ceil((double)(unit1y - unit0y) / RIM) + 2 * ring;
        const size_t tn = (size_t)t.w * t.h;
        if (tn > 0 && tn <= 6000000) {
            std::vector<int16_t> ttop(tn, (int16_t)NONE);
            std::vector<float> tfloor(tn, NAN);
            for (int j = 0; j < g.h; j++)
                for (int i = 0; i < g.w; i++) {
                    const size_t c = (size_t)j * g.w + i;
                    if (hi[c] == NONE) continue;
                    const int ti = (int)std::floor((double)((g.x0 + i) * FINE) / RIM) - t.x0, tj = (int)std::floor((double)((g.y0 + j) * FINE) / RIM) - t.y0;
                    if (!t.inside(ti, tj)) continue;
                    const size_t k = (size_t)tj * t.w + ti;
                    if (ttop[k] == NONE || hi[c] > ttop[k]) ttop[k] = hi[c];
                    if (!std::isnan(floor_z[c]) && (std::isnan(tfloor[k]) || floor_z[c] < tfloor[k])) tfloor[k] = floor_z[c];
                }
            // water: the boxes of the water chunks (a beach's sea, a lava lake are the level's own)
            std::vector<uint8_t> water(tn, 0);
            {
                const size_t chunk_at = r.at(r.u32(base + 0x24));
                if (r.fits(chunk_at, (size_t)chunks * 0x3C))
                    for (uint32_t k = 0; k < chunks; k++) {
                        const size_t o = chunk_at + (size_t)k * 0x3C;
                        if (!(r.u32(o + 0x24) & 0x80)) continue;
                        float b[6];
                        memcpy(b, r.m + o + 8, 24);
                        if (!(b[0] <= b[3] && b[1] <= b[4]) || b[3] - b[0] > 20000.0f || b[4] - b[1] > 20000.0f) continue;
                        const int i0 = std::max(0, (int)std::floor(b[0] / RIM) - t.x0 - 1), i1 = std::min(t.w - 1, (int)std::floor(b[3] / RIM) - t.x0 + 1);
                        const int j0 = std::max(0, (int)std::floor(b[1] / RIM) - t.y0 - 1), j1 = std::min(t.h - 1, (int)std::floor(b[4] / RIM) - t.y0 + 1);
                        for (int j = j0; j <= j1; j++)
                            for (int i = i0; i <= i1; i++) water[(size_t)j * t.w + i] = 1;
                    }
            }
            auto empty = [&](int i, int j) { if (!t.inside(i, j)) return false; const size_t c = (size_t)j * t.w + i; return ttop[c] == NONE && !water[c]; };
            // the edges: a terrain cell beside an empty one; its height is that of the floor there
            std::vector<float> edge_z(tn, NAN);
            static const int nx[4] = {1, -1, 0, 0}, ny[4] = {0, 0, 1, -1};
            for (int j = 0; j < t.h; j++)
                for (int i = 0; i < t.w; i++) {
                    const size_t c = (size_t)j * t.w + i;
                    if (ttop[c] == NONE) continue;
                    bool beside = false;
                    for (int k = 0; k < 4; k++) if (empty(i + nx[k], j + ny[k])) beside = true;
                    if (!beside) continue;
                    float f = NAN;
                    for (int y = j - 2; y <= j + 2; y++)
                        for (int x = i - 2; x <= i + 2; x++)
                            if (t.inside(x, y)) { float v = tfloor[(size_t)y * t.w + x]; if (!std::isnan(v) && (std::isnan(f) || v > f)) f = v; }
                    const bool lid = std::isnan(f) || (float)ttop[c] - f >= opt.rim_min;
                    if (lid && opt.skirts) continue;                   // a lid's edge: the skirt's (and nobody looks over it)
                    edge_z[c] = std::isnan(tfloor[c]) ? (std::isnan(f) ? (float)ttop[c] : f) : tfloor[c];
                }
            // out over the empty cells
            std::vector<float> d(tn, 1e9f), z0(tn, 0.0f);
            std::vector<uint32_t> q;
            for (int j = 0; j < t.h; j++)
                for (int i = 0; i < t.w; i++) {
                    if (!empty(i, j)) continue;
                    const size_t c = (size_t)j * t.w + i;
                    float best = NAN;                           // the highest floor edge beside it
                    for (int k = 0; k < 4; k++) {
                        const int x = i + nx[k], y = j + ny[k];
                        if (!t.inside(x, y)) continue;
                        const float e = edge_z[(size_t)y * t.w + x];
                        if (!std::isnan(e) && (std::isnan(best) || e > best)) best = e;
                    }
                    if (std::isnan(best)) continue;
                    d[c] = RIM * 0.5f; z0[c] = best;
                    q.push_back((uint32_t)c);
                }
            for (size_t head = 0; head < q.size(); head++) {
                const uint32_t c = q[head];
                const int ci = (int)(c % t.w), cj = (int)(c / t.w);
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++) {
                        if (!dx && !dy) continue;
                        const int x = ci + dx, y = cj + dy;
                        if (!empty(x, y)) continue;
                        const size_t m = (size_t)y * t.w + x;
                        const float step = (dx && dy) ? RIM * 1.41421356f : (float)RIM, nd = d[c] + step;
                        if (nd >= d[m] || nd > opt.rim_width) continue;
                        d[m] = nd; z0[m] = z0[c];
                        q.push_back((uint32_t)m);
                    }
            }
            for (size_t c = 0; c < tn; c++)
                if (!std::isnan(edge_z[c])) { d[c] = 0; z0[c] = edge_z[c] - 4.0f; }
            auto filled = [&](int i, int j) { return t.inside(i, j) && d[(size_t)j * t.w + i] < 1e8f; };
            auto fall = [&](float at) { return std::min(at, opt.rim_knee) * opt.rim_fall + std::max(0.0f, at - opt.rim_knee) * opt.rim_fall_far; };
            const float fade_from = opt.rim_width * 0.45f;
            const int cw = t.w + 1;
            std::vector<float> corner_z((size_t)cw * (t.h + 1), 0.0f), corner_a((size_t)cw * (t.h + 1), 0.0f), corner_d((size_t)cw * (t.h + 1), 0.0f);
            for (int j = 0; j <= t.h; j++)
                for (int i = 0; i <= t.w; i++) {
                    float sum = 0, dsum = 0, edge = NAN; int cnt = 0, around = 0; bool ground = false;
                    for (int y = j - 1; y <= j; y++)
                        for (int x = i - 1; x <= i; x++) {
                            if (!t.inside(x, y)) continue;
                            around++;
                            const size_t c = (size_t)y * t.w + x;
                            if (filled(x, y)) { sum += z0[c] - fall(d[c]); dsum += d[c]; cnt++; }
                            else if (ttop[c] != NONE) ground = true;
                            if (!std::isnan(edge_z[c])) edge = std::isnan(edge) ? edge_z[c] : std::max(edge, edge_z[c]);
                        }
                    const size_t v = (size_t)j * cw + i;
                    if (ground && !std::isnan(edge)) { corner_z[v] = edge - 4.0f; corner_a[v] = 128.0f; corner_d[v] = 0; }    // fastened under the ground
                    else if (cnt) {
                        const float at = dsum / (float)cnt;
                        corner_z[v] = sum / (float)cnt; corner_d[v] = at;
                        corner_a[v] = cnt == around ? 128.0f * std::max(0.0f, std::min(1.0f, (opt.rim_width - at) / (opt.rim_width - fade_from))) : 0.0f;
                    }
                }
            const int block = 8;
            for (int bj = 0; bj < t.h; bj += block)
                for (int bi = 0; bi < t.w; bi += block) {
                    const uint32_t first = (uint32_t)level->vertices.size();
                    for (int j = bj; j < std::min(bj + block, t.h); j++)
                        for (int i = bi; i < std::min(bi + block, t.w); i++) {
                            if (!filled(i, j)) continue;
                            float p[4][3];
                            uint8_t shade[4], alpha[4];
                            static const int ox[4] = {0, 1, 1, 0}, oy[4] = {0, 0, 1, 1};
                            for (int k = 0; k < 4; k++) {
                                const size_t v = (size_t)(j + oy[k]) * cw + i + ox[k];
                                p[k][0] = (float)((t.x0 + i + ox[k]) * RIM); p[k][1] = (float)((t.y0 + j + oy[k]) * RIM); p[k][2] = corner_z[v];
                                alpha[k] = (uint8_t)std::max(0.0f, std::min(128.0f, corner_a[v]));
                                // grey: 150 at the edge, 90 at the outer edge (the renderer darkens the underside with it)
                                shade[k] = (uint8_t)(150.0f - 60.0f * std::min(1.0f, corner_d[v] / opt.rim_width));
                            }
                            quad(level->vertices, p, shade, alpha, true);
                            level->rim_area += (double)RIM * RIM;
                        }
                    close_mesh(*level, FILL_RIM, first);
                }
        }
    }

    // a number of this build
    uint64_t serial = 1469598103934665603ull;
    auto mix = [&](const void* p, size_t count) { const uint8_t* b = (const uint8_t*)p; for (size_t k = 0; k < count; k++) serial = (serial ^ b[k]) * 1099511628211ull; };
    mix(level->name.data(), level->name.size());
    const float numbers[14] = {(float)opt.over, opt.wall_min, opt.reach, opt.vault, opt.vault_most, opt.clearance, opt.skirt_width, opt.skirt_drop, opt.rim_min,
                               (float)(opt.far_shade + (opt.ceilings ? 256 : 0) + (opt.skirts ? 512 : 0) + (opt.rims ? 1024 : 0)), opt.rim_width, opt.rim_knee, opt.rim_fall,
                               opt.rim_fall_far};
    mix(numbers, sizeof numbers);
    const uint64_t counts[3] = {level->vertices.size(), level->meshes.size(), cells};
    mix(counts, sizeof counts);
    level->serial = serial ? serial : 1;
    level->build_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count();
    return level;
}

}  // namespace render
