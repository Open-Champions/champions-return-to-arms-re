// rta_remaster.cpp - see rta_remaster.h.
#include "rta_remaster.h"
#include "rta_library.h"

#include <godot_cpp/classes/mesh.hpp>
#include <godot_cpp/classes/rendering_server.hpp>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/packed_float32_array.hpp>
#include <godot_cpp/variant/packed_int32_array.hpp>
#include <godot_cpp/variant/packed_string_array.hpp>
#include <godot_cpp/variant/packed_vector2_array.hpp>
#include <godot_cpp/variant/packed_vector3_array.hpp>
#include <godot_cpp/variant/packed_vector4_array.hpp>
#include <godot_cpp/variant/transform3d.hpp>
#include <godot_cpp/variant/vector2.hpp>
#include <godot_cpp/variant/vector3.hpp>
#include <godot_cpp/variant/vector3i.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <map>
#include <unordered_set>

using namespace godot;

namespace {

uint64_t fnv(uint64_t h, const void* data, size_t n) {
    const uint8_t* p = (const uint8_t*)data;
    for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ull; }
    return h;
}
const uint64_t FNV0 = 1469598103934665603ull;

// eight bytes at a step (the byte-wise FNV above over every packet's data each frame was most of the scan's time)
uint64_t mix64(uint64_t h, const void* data, size_t n) {
    const uint8_t* p = (const uint8_t*)data;
    while (n >= 8) {
        uint64_t w;
        memcpy(&w, p, 8);
        h = (h ^ w) * 0x9E3779B97F4A7C15ull;
        h ^= h >> 29;
        p += 8;
        n -= 8;
    }
    uint64_t w = 0;
    memcpy(&w, p, n);
    h = (h ^ w ^ (n << 56)) * 0x9E3779B97F4A7C15ull;
    return h ^ (h >> 31);
}

std::string hex(uint64_t v) {
    char b[24];
    snprintf(b, sizeof b, "%016llx", (unsigned long long)v);
    return b;
}

bool frame_skeletons(const Ref<RtaMachine>& machine, rtag_skeletons& k, const rtag_scene*& sc) {
    if (machine.is_null()) return false;
    const rtag_frame* f = machine->current();
    const RtaLibrary& lib = rta_library();
    if (!f || !f->scene || !lib.rtag_skeletons_get) return false;
    memset(&k, 0, sizeof k);
    k.struct_size = sizeof k;
    if (!lib.rtag_skeletons_get(&k) || k.piece_count != f->scene->piece_count) return false;
    sc = f->scene;
    return true;
}

struct Group {
    uint32_t object = 0;
    int skeleton = -2;
    bool bad = false;
    uint32_t rigid = 0, unskinned = 0, other_skeleton = 0, env = 0;
    int first_skeleton = -1;
    std::vector<uint32_t> pieces;
    std::vector<uint64_t> hashes;
    std::vector<char> shiny;
    std::vector<int> under;                 // the first pass of a two-pass packet laid under it (its own texture), -1: none
    std::vector<int> env_pass;              // the first pass of a two-pass packet that is an environment map, -1: none
    uint64_t key = 0;
    uint32_t corners = 0;
};

// A packet's identity: its counts, and every third source and corner (all of them took most of a frame's scan in a
// crowd; a packet of another model that agrees with this one in its counts and a third of its data is not met)
uint64_t piece_hash(const rtag_skeletons& k, const rtag_scene& sc, uint32_t i, uint32_t& corners) {
    const rtag_skin_piece& p = k.pieces[i];
    const rtag_scene_piece& q = sc.pieces[i];
    uint64_t h = FNV0;
    h = mix64(h, &p.source_count, sizeof p.source_count);
    h = mix64(h, &q.full_count, sizeof q.full_count);
    if (p.source_first + p.source_count <= k.source_count)
        for (uint32_t v = 0; v < p.source_count; v += 3) h = mix64(h, k.sources + p.source_first + v, sizeof(rtag_skin_source));
    const uint32_t full = std::min(k.full_count, sc.full_count);
    const uint32_t end = std::min(q.full_first + q.full_count, full);
    corners = end > q.full_first ? end - q.full_first : 0;
    for (uint32_t c = q.full_first; c < end; c += 3) {
        h = mix64(h, &k.full_source[c], 2);
        h = mix64(h, &sc.full[c].u, 4);
        h = mix64(h, &sc.full[c].v, 4);
    }
    return h;
}

// the figures of the frame: per object, its skinned packets (an object posed by two skeletons is left to the game)
void groups(const rtag_skeletons& k, const rtag_scene& sc, std::vector<Group>& out, std::vector<Group>* rejected = nullptr) {
    std::map<uint32_t, Group> by;
    // the first passes of two-pass packets, by object and source: the second pass is the same vertices
    std::map<std::pair<uint32_t, uint32_t>, uint32_t> first_pass;
    for (uint32_t i = 0; i < k.piece_count; i++) {
        const rtag_scene_piece& q = sc.pieces[i];
        if (q.kind == 2 && (q.flags & 4) && (q.flags & 2) && k.pieces[i].skeleton >= 0) first_pass[{q.object, k.pieces[i].source_first}] = i;
    }
    for (uint32_t i = 0; i < k.piece_count; i++) {
        const rtag_scene_piece& q = sc.pieces[i];
        if (q.kind != 2) continue;
        Group& g = by[q.object];
        g.object = q.object;
        const int s = k.pieces[i].skeleton;
        // what is not skinned (a held weapon's rigid packets, a packet on one joint) stays the game's (set_hidden_skinned)
        if (s < 0) { g.rigid++; continue; }
        if (g.first_skeleton < 0) g.first_skeleton = s;
        if (!(q.flags & 4)) { g.unskinned++; continue; }
        if (q.flags & 2) { g.env++; continue; }         // the environment-map pass of a two-pass packet
        if (g.skeleton == -2) g.skeleton = s;
        else if (g.skeleton != s) { g.bad = true; g.other_skeleton++; }
        g.pieces.push_back(i);
    }
    for (auto& e : by) {
        Group& g = e.second;
        if (rejected && (g.bad || g.skeleton < 0) && g.first_skeleton >= 0) rejected->push_back(g);
        if (g.bad || g.skeleton < 0 || g.pieces.empty()) continue;
        std::vector<std::pair<uint64_t, uint32_t>> order;
        for (uint32_t i : g.pieces) {
            uint32_t c = 0;
            order.push_back({piece_hash(k, sc, i, c), i});
            g.corners += c;
        }
        std::sort(order.begin(), order.end());
        g.pieces.clear();
        g.shiny.clear();
        g.under.clear();
        g.env_pass.clear();
        uint64_t key = FNV0;
        for (auto& o : order) {
            g.pieces.push_back(o.second);
            g.hashes.push_back(o.first);
            // the second pass of a two-pass packet: the game lays an environment map over it (chrome, polished armour) in
            // a first pass that is left out with the body - its material is told it shines
            // A two-pass packet: its first pass is either an environment map (chrome: the texture coordinates are made
            // from the view, they differ from the second pass's) or the packet's own colour under a blended second pass
            // (a face under its paint: the same coordinates).  The first: the material shines; the second: drawn under.
            int under = -1, env = -1;
            bool shiny = false;
            if (sc.pieces[o.second].flags & 1) {
                auto fp = first_pass.find({g.object, k.pieces[o.second].source_first});
                uint32_t first = fp != first_pass.end() ? fp->second : UINT32_MAX;
                // (else the packet the list has just before it: the first kick of the two)
                for (uint32_t back = 1; first == UINT32_MAX && back <= 2 && o.second >= back; back++) {
                    const rtag_scene_piece& c = sc.pieces[o.second - back];
                    if (c.kind == 2 && (c.flags & 2) && c.object == g.object && c.full_count == sc.pieces[o.second].full_count) first = o.second - back;
                }
                if (first != UINT32_MAX) {
                    const rtag_scene_piece& a = sc.pieces[first];
                    const rtag_scene_piece& b = sc.pieces[o.second];
                    // (texels of each pass's own texture: the same mapping on textures of two sizes differs by a
                    // factor in u and one in v)
                    bool same = a.full_count == b.full_count && a.full_count > 0;
                    const uint32_t full = std::min(k.full_count, sc.full_count);
                    float ku = 0.0f, kv = 0.0f;
                    for (uint32_t c = 0; same && c < a.full_count && c < 64; c++) {
                        if (a.full_first + c >= full || b.full_first + c >= full) { same = false; break; }
                        const rtag_scene_full& x = sc.full[a.full_first + c];
                        const rtag_scene_full& y = sc.full[b.full_first + c];
                        if (ku == 0.0f && std::fabs(y.u) > 0.5f) ku = x.u / y.u;
                        if (kv == 0.0f && std::fabs(y.v) > 0.5f) kv = x.v / y.v;
                        if (ku != 0.0f && std::fabs(x.u - y.u * ku) > 0.02f * (1.0f + std::fabs(x.u))) same = false;
                        if (kv != 0.0f && std::fabs(x.v - y.v * kv) > 0.02f * (1.0f + std::fabs(x.v))) same = false;
                    }
                    if (ku <= 0.0f || kv <= 0.0f) same = false;
                    if (same) under = (int)first;
                    else { shiny = true; env = (int)first; }
                } else shiny = true;
            }
            g.shiny.push_back(shiny ? 1 : 0);
            g.under.push_back(under);
            g.env_pass.push_back(env);
            key = fnv(key, &o.first, 8);
        }
        g.key = key;
        out.push_back(std::move(g));
    }
}

Transform3D rows34(const float* m) {
    return Transform3D(Basis(m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10]), Vector3(m[3], m[7], m[11]));
}

// ---- subdivision ------------------------------------------------------------------------------------------------------
struct Skin { int j[4]; float w[4]; };
struct Tri { int v[3]; Vector2 uv[3]; Vector3 rn[3]; int piece; bool decal = false; };
struct Row { std::vector<std::pair<int, float>> w; };
struct Level { std::vector<Row> rows; std::vector<std::array<int, 3>> mids; };

inline uint64_t ekey(int a, int b) { return a < b ? ((uint64_t)a << 32) | (uint32_t)b : ((uint64_t)b << 32) | (uint32_t)a; }

struct Edge { int a, b, nf = 0, opp[2] = {-1, -1}, face[2] = {-1, -1}; bool crease = false; };

void build_edges(const std::vector<Tri>& tris, std::vector<Edge>& edges, std::unordered_map<uint64_t, int>& eid) {
    edges.clear();
    eid.clear();
    eid.reserve(tris.size() * 2);
    for (size_t t = 0; t < tris.size(); t++)
        for (int c = 0; c < 3; c++) {
            if (tris[t].decal) break;          // a decal lies on the surface: no part of its shape
            const int a = tris[t].v[c], b = tris[t].v[(c + 1) % 3], o = tris[t].v[(c + 2) % 3];
            auto it = eid.find(ekey(a, b));
            int e;
            if (it == eid.end()) { e = (int)edges.size(); eid[ekey(a, b)] = e; Edge x; x.a = std::min(a, b); x.b = std::max(a, b); edges.push_back(x); }
            else e = it->second;
            Edge& x = edges[e];
            if (x.nf < 2) { x.opp[x.nf] = o; x.face[x.nf] = (int)t; }
            x.nf++;
        }
}

Vector3 corner_rn(const Tri& t, int v) {
    for (int c = 0; c < 3; c++) if (t.v[c] == v) return t.rn[c];
    return Vector3();
}

// one level: the stencils from this level's vertices to the next's, the next level's triangles and creases
void step(int nv, const std::vector<Tri>& tris, std::unordered_set<uint64_t>& crease, Level& L, std::vector<Tri>& out, int& out_nv) {
    std::vector<Edge> edges;
    std::unordered_map<uint64_t, int> eid;
    build_edges(tris, edges, eid);
    std::vector<std::vector<int>> nb(nv), cnb(nv);
    for (Edge& e : edges) {
        e.crease = e.nf != 2 || crease.count(ekey(e.a, e.b));
        nb[e.a].push_back(e.b);
        nb[e.b].push_back(e.a);
        if (e.crease) { cnb[e.a].push_back(e.b); cnb[e.b].push_back(e.a); }
    }
    L.rows.assign(nv + edges.size(), Row());
    for (int i = 0; i < nv; i++) {
        Row& r = L.rows[i];
        const size_t cn = cnb[i].size();
        if (nb[i].empty() || cn >= 3) { r.w.push_back({i, 1.0f}); continue; }
        if (cn == 2) { r.w = {{i, 0.75f}, {cnb[i][0], 0.125f}, {cnb[i][1], 0.125f}}; continue; }
        const int n = (int)nb[i].size();
        const float beta = n == 3 ? 3.0f / 16.0f : 3.0f / (8.0f * n);
        r.w.push_back({i, 1.0f - n * beta});
        for (int j : nb[i]) r.w.push_back({j, beta});
    }
    L.mids.clear();
    for (size_t k = 0; k < edges.size(); k++) {
        const Edge& e = edges[k];
        Row& r = L.rows[nv + k];
        if (e.crease || e.opp[0] < 0 || e.opp[1] < 0) r.w = {{e.a, 0.5f}, {e.b, 0.5f}};
        else r.w = {{e.a, 0.375f}, {e.b, 0.375f}, {e.opp[0], 0.125f}, {e.opp[1], 0.125f}};
        L.mids.push_back({nv + (int)k, e.a, e.b});
    }
    std::unordered_set<uint64_t> next;
    for (size_t k = 0; k < edges.size(); k++)
        if (edges[k].crease) { next.insert(ekey(edges[k].a, nv + (int)k)); next.insert(ekey(nv + (int)k, edges[k].b)); }
    crease.swap(next);
    out.clear();
    out.reserve(tris.size() * 4);
    for (const Tri& t : tris) {
        int m[3];
        Vector2 muv[3];
        Vector3 mrn[3];
        bool lost = false;
        for (int c = 0; c < 3 && !lost; c++) {
            const int d = (c + 1) % 3;
            auto it = eid.find(ekey(t.v[c], t.v[d]));
            if (it == eid.end()) { lost = true; break; }      // (a decal off the surface's own edges: not carried on)
            m[c] = nv + it->second;
            muv[c] = (t.uv[c] + t.uv[d]) * 0.5f;
            Vector3 s = t.rn[c] + t.rn[d];
            mrn[c] = s.length_squared() > 1e-12f ? s.normalized() : t.rn[c];
        }
        if (lost) continue;
        // m[0] = (v0 v1), m[1] = (v1 v2), m[2] = (v2 v0)
        Tri a = t, b = t, c = t, d = t;
        a.v[0] = t.v[0]; a.uv[0] = t.uv[0]; a.rn[0] = t.rn[0]; a.v[1] = m[0]; a.uv[1] = muv[0]; a.rn[1] = mrn[0]; a.v[2] = m[2]; a.uv[2] = muv[2]; a.rn[2] = mrn[2];
        b.v[0] = t.v[1]; b.uv[0] = t.uv[1]; b.rn[0] = t.rn[1]; b.v[1] = m[1]; b.uv[1] = muv[1]; b.rn[1] = mrn[1]; b.v[2] = m[0]; b.uv[2] = muv[0]; b.rn[2] = mrn[0];
        c.v[0] = t.v[2]; c.uv[0] = t.uv[2]; c.rn[0] = t.rn[2]; c.v[1] = m[2]; c.uv[1] = muv[2]; c.rn[1] = mrn[2]; c.v[2] = m[1]; c.uv[2] = muv[1]; c.rn[2] = mrn[1];
        d.v[0] = m[0]; d.uv[0] = muv[0]; d.rn[0] = mrn[0]; d.v[1] = m[1]; d.uv[1] = muv[1]; d.rn[1] = mrn[1]; d.v[2] = m[2]; d.uv[2] = muv[2]; d.rn[2] = mrn[2];
        out.push_back(a); out.push_back(b); out.push_back(c); out.push_back(d);
    }
    out_nv = nv + (int)edges.size();
}

std::vector<Vector3> apply(const std::vector<Level>& levels, size_t upto, std::vector<Vector3> p) {
    for (size_t l = 0; l < upto; l++) {
        std::vector<Vector3> q(levels[l].rows.size());
        for (size_t i = 0; i < q.size(); i++) {
            Vector3 s;
            for (const auto& w : levels[l].rows[i].w) s += p[w.first] * w.second;
            q[i] = s;
        }
        p.swap(q);
    }
    return p;
}

std::vector<Skin> apply_skin(const std::vector<Level>& levels, size_t upto, std::vector<Skin> s) {
    for (size_t l = 0; l < upto; l++) {
        std::vector<Skin> q(levels[l].rows.size());
        for (size_t i = 0; i < q.size(); i++) {
            int js[24];
            float ws[24];
            int n = 0;
            for (const auto& w : levels[l].rows[i].w) {
                const Skin& a = s[w.first];
                for (int c = 0; c < 4; c++) {
                    if (a.w[c] <= 0.0f) continue;
                    int k = 0;
                    while (k < n && js[k] != a.j[c]) k++;
                    if (k == n) { if (n == 24) continue; js[n] = a.j[c]; ws[n] = 0.0f; n++; }
                    ws[k] += a.w[c] * w.second;
                }
            }
            Skin out{{0, 0, 0, 0}, {0, 0, 0, 0}};
            float total = 0.0f;
            for (int c = 0; c < 4; c++) {
                int best = -1;
                for (int k = 0; k < n; k++) if (ws[k] > 0.0f && (best < 0 || ws[k] > ws[best])) best = k;
                if (best < 0) break;
                out.j[c] = js[best]; out.w[c] = ws[best]; total += ws[best]; ws[best] = -1.0f;
            }
            if (total > 0.0f) for (int c = 0; c < 4; c++) out.w[c] /= total;
            else out = s[levels[l].rows[i].w[0].first];
            q[i] = out;
        }
        s.swap(q);
    }
    return s;
}

struct OutSurface {
    std::vector<Vector3> pos, nrm;
    std::vector<float> tan;
    std::vector<Vector2> uv;
    std::vector<int> bones, index;
    std::vector<float> weights;
};
struct OutLevel { std::vector<OutSurface> surfaces; size_t triangles = 0; };

struct CornerKey {
    int v; float u, w; int nx, ny, nz;
    bool operator==(const CornerKey& o) const { return v == o.v && u == o.u && w == o.w && nx == o.nx && ny == o.ny && nz == o.nz; }
};
struct CornerHash {
    size_t operator()(const CornerKey& k) const { return (size_t)fnv(FNV0, &k, sizeof k); }
};

OutLevel emit(const std::vector<Tri>& tris, const std::vector<Vector3>& p, const std::vector<Skin>& skin, int pieces, float crease_cos) {
    OutLevel out;
    out.surfaces.resize(pieces);
    std::vector<Vector3> fn(tris.size());
    std::vector<std::vector<int>> vf(p.size());
    for (size_t t = 0; t < tris.size(); t++) {
        const Tri& x = tris[t];
        fn[t] = (p[x.v[1]] - p[x.v[0]]).cross(p[x.v[2]] - p[x.v[0]]);
        for (int c = 0; c < 3; c++) vf[x.v[c]].push_back((int)t);
    }
    std::vector<std::unordered_map<CornerKey, int, CornerHash>> seen(pieces);
    for (size_t t = 0; t < tris.size(); t++) {
        const Tri& x = tris[t];
        OutSurface& s = out.surfaces[x.piece];
        int ids[3];
        for (int c = 0; c < 3; c++) {
            const int v = x.v[c];
            Vector3 sum;
            for (int f : vf[v]) if (corner_rn(tris[f], v).dot(x.rn[c]) >= crease_cos) sum += fn[f];
            Vector3 n = sum.length_squared() > 1e-20f ? sum.normalized() : (fn[t].length_squared() > 1e-20f ? fn[t].normalized() : x.rn[c]);
            CornerKey key{v, x.uv[c].x, x.uv[c].y, (int)std::lround(n.x * 2000), (int)std::lround(n.y * 2000), (int)std::lround(n.z * 2000)};
            auto it = seen[x.piece].find(key);
            if (it != seen[x.piece].end()) { ids[c] = it->second; continue; }
            const int id = (int)s.pos.size();
            seen[x.piece][key] = id;
            s.pos.push_back(p[v]);
            s.nrm.push_back(n);
            s.uv.push_back(x.uv[c]);
            for (int q = 0; q < 4; q++) { s.bones.push_back(skin[v].j[q]); s.weights.push_back(skin[v].w[q]); }
            ids[c] = id;
        }
        // Godot's front faces are wound clockwise: the triangle (counter-clockwise about its outward normal) turned over
        s.index.push_back(ids[0]); s.index.push_back(ids[2]); s.index.push_back(ids[1]);
        out.triangles++;
    }
    // tangents along +u, the sign so that cross(N, T) * w points up the picture (-v)
    for (OutSurface& s : out.surfaces) {
        std::vector<Vector3> tu(s.pos.size()), tv(s.pos.size());
        for (size_t i = 0; i + 2 < s.index.size(); i += 3) {
            const int a = s.index[i], b = s.index[i + 1], c = s.index[i + 2];
            const Vector3 e1 = s.pos[b] - s.pos[a], e2 = s.pos[c] - s.pos[a];
            const Vector2 d1 = s.uv[b] - s.uv[a], d2 = s.uv[c] - s.uv[a];
            const float det = d1.x * d2.y - d2.x * d1.y;
            if (std::fabs(det) < 1e-12f) continue;
            const float r = 1.0f / det;
            const Vector3 T = (e1 * d2.y - e2 * d1.y) * r, B = (e2 * d1.x - e1 * d2.x) * r;
            for (int v : {a, b, c}) { tu[v] += T; tv[v] += B; }
        }
        s.tan.resize(s.pos.size() * 4);
        for (size_t v = 0; v < s.pos.size(); v++) {
            const Vector3 n = s.nrm[v];
            Vector3 t = tu[v] - n * n.dot(tu[v]);
            if (t.length_squared() < 1e-20f) t = std::fabs(n.x) < 0.9f ? Vector3(1, 0, 0).cross(n) : Vector3(0, 1, 0).cross(n);
            t.normalize();
            const float w = n.cross(t).dot(-tv[v]) < 0.0f ? -1.0f : 1.0f;
            s.tan[v * 4] = t.x; s.tan[v * 4 + 1] = t.y; s.tan[v * 4 + 2] = t.z; s.tan[v * 4 + 3] = w;
        }
    }
    return out;
}

// Layers: where the model has a second surface just outside a vertex (a skirt over the hips, a pauldron over the
// shoulder, a belt over the waist - the game's own layered clothing, a fraction of a unit apart), the vertex is covered.
// A smooth surface leaves its control points by up to a few tenths of a unit between them, which is enough for the inner
// layer to come through the outer one (a hip through a skirt): covered vertices of the finer levels are drawn `gap`
// units inside.  A surface counts only when it is no near neighbour of the vertex in the mesh (its own fold, the thigh
// next to it, is not a layer over it): no corner of the triangle within two edges of the vertex.
std::vector<float> covered_by_layers(const std::vector<Vector3>& p, const std::vector<Tri>& tris, float reach) {
    const size_t nv = p.size();
    std::vector<float> cov(nv, 0.0f);
    if (tris.empty() || reach <= 0.0f) return cov;
    std::vector<Vector3> vn(nv);
    std::vector<std::vector<int>> nb(nv);
    for (const Tri& t : tris) {
        if (t.decal) continue;
        const Vector3 n = (p[t.v[1]] - p[t.v[0]]).cross(p[t.v[2]] - p[t.v[0]]);
        for (int c = 0; c < 3; c++) {
            vn[t.v[c]] += n;
            nb[t.v[c]].push_back(t.v[(c + 1) % 3]);
            nb[t.v[c]].push_back(t.v[(c + 2) % 3]);
        }
    }
    // the triangles in a grid of cells `reach` wide
    const float cell = std::max(reach, 0.5f);
    auto key = [&](int x, int y, int z) { return ((uint64_t)(uint32_t)(x + 100000) << 42) ^ ((uint64_t)(uint32_t)(y + 100000) << 21) ^ (uint64_t)(uint32_t)(z + 100000); };
    std::unordered_map<uint64_t, std::vector<int>> grid;
    for (size_t t = 0; t < tris.size(); t++) {
        if (tris[t].decal) continue;
        Vector3 lo = p[tris[t].v[0]], hi = lo;
        for (int c = 1; c < 3; c++) {
            const Vector3 q = p[tris[t].v[c]];
            lo = Vector3(std::min(lo.x, q.x), std::min(lo.y, q.y), std::min(lo.z, q.z));
            hi = Vector3(std::max(hi.x, q.x), std::max(hi.y, q.y), std::max(hi.z, q.z));
        }
        for (int x = (int)std::floor(lo.x / cell); x <= (int)std::floor(hi.x / cell); x++)
            for (int y = (int)std::floor(lo.y / cell); y <= (int)std::floor(hi.y / cell); y++)
                for (int z = (int)std::floor(lo.z / cell); z <= (int)std::floor(hi.z / cell); z++) grid[key(x, y, z)].push_back((int)t);
    }
    std::vector<int> mark(nv, -1);
    for (size_t v = 0; v < nv; v++) {
        if (vn[v].length_squared() < 1e-12f) continue;
        const Vector3 n = vn[v].normalized(), o = p[v];
        // the vertices within two edges of v
        mark[v] = (int)v;
        for (int a : nb[v]) {
            mark[a] = (int)v;
            for (int b : nb[a]) mark[b] = (int)v;
        }
        bool hit = false;
        std::unordered_set<int> tried;
        for (int step = 0; step <= 2 && !hit; step++) {
            const Vector3 q = o + n * (reach * step * 0.5f);
            const int cx = (int)std::floor(q.x / cell), cy = (int)std::floor(q.y / cell), cz = (int)std::floor(q.z / cell);
            auto it = grid.find(key(cx, cy, cz));
            if (it == grid.end()) continue;
            for (int t : it->second) {
                if (!tried.insert(t).second) continue;
                const Tri& tr = tris[t];
                if (mark[tr.v[0]] == (int)v || mark[tr.v[1]] == (int)v || mark[tr.v[2]] == (int)v) continue;
                // the ray o + n s, 0 < s <= reach, against the triangle (Moller-Trumbore)
                const Vector3 e1 = p[tr.v[1]] - p[tr.v[0]], e2 = p[tr.v[2]] - p[tr.v[0]];
                const Vector3 h = n.cross(e2);
                const float det = e1.dot(h);
                if (std::fabs(det) < 1e-9f) continue;
                const float inv = 1.0f / det;
                const Vector3 sv = o - p[tr.v[0]];
                const float u = sv.dot(h) * inv;
                if (u < 0.0f || u > 1.0f) continue;
                const Vector3 qv = sv.cross(e1);
                const float w = n.dot(qv) * inv;
                if (w < 0.0f || u + w > 1.0f) continue;
                const float s = e2.dot(qv) * inv;
                if (s > 1e-4f && s <= reach) { hit = true; break; }
            }
        }
        if (hit) cov[v] = 1.0f;
    }
    return cov;
}

}  // namespace

// two vertices skinned alike: the same joints with weights within 2/255
bool same_skin(const Skin& k, const rtag_skin_source& s) {
    float w[64] = {};
    bool used[64] = {};
    for (int c = 0; c < 4; c++) if (s.weight[c] && s.joint[c] < 64) { w[s.joint[c]] += s.weight[c] / 255.0f; used[s.joint[c]] = true; }
    for (int c = 0; c < 4; c++) if (k.w[c] > 0.0f && k.j[c] >= 0 && k.j[c] < 64) { w[k.j[c]] -= k.w[c]; used[k.j[c]] = true; }
    for (int j = 0; j < 64; j++) if (used[j] && std::fabs(w[j]) > 2.5f / 255.0f) return false;
    return true;
}

struct RtaRemaster::Job {
    struct Piece { std::vector<rtag_skin_source> sources; std::vector<std::array<float, 3>> corners; /* source, u, v */ };
    std::vector<Piece> pieces;
    std::vector<std::string> piece_keys;
    std::vector<char> decal_piece;          // packets drawn over others' triangles (decals)
    int levels = 2, fit = 4, max_tris = 80000;
    float crease = 0.5f, keep = 0.8f, layer_reach = 2.0f, layer_gap = 0.3f;
    std::atomic<bool> done{false};
    std::string failed, stats;
    std::vector<OutLevel> out;
    bool taken = false;

    void run() {
        const auto t0 = std::chrono::steady_clock::now();
        // weld by position (a packet seam is one edge of the surface): within WELD of each other, whatever grid cell the
        // two fall in (a packet's copy of a seam vertex can differ from its neighbour's in the last bits)
        const float WELD = 0.0025f;
        std::map<std::array<int, 3>, std::vector<int>> weld;
        std::vector<Vector3> p0;
        std::vector<Skin> s0;
        std::vector<Tri> tris;
        size_t dropped = 0;
        for (size_t pi = 0; pi < pieces.size(); pi++) {
            const Piece& pc = pieces[pi];
            std::vector<int> id(pc.sources.size());
            for (size_t v = 0; v < pc.sources.size(); v++) {
                const rtag_skin_source& s = pc.sources[v];
                const Vector3 pos(s.position[0], s.position[1], s.position[2]);
                std::array<int, 3> q{(int)std::floor(pos.x / WELD), (int)std::floor(pos.y / WELD), (int)std::floor(pos.z / WELD)};
                int found = -1;
                for (int dx = -1; dx <= 1 && found < 0; dx++)
                    for (int dy = -1; dy <= 1 && found < 0; dy++)
                        for (int dz = -1; dz <= 1 && found < 0; dz++) {
                            auto it = weld.find({q[0] + dx, q[1] + dy, q[2] + dz});
                            if (it == weld.end()) continue;
                            // (and only one moved the same way: an upper lip and the lower one, an eyelid and the eye,
                            // meet in the bind pose but follow different joints - welded, the mouth was torn open)
                            for (int k : it->second)
                                if (p0[k].distance_to(pos) <= WELD && same_skin(s0[k], s)) { found = k; break; }
                        }
                if (found >= 0) { id[v] = found; continue; }
                id[v] = (int)p0.size();
                weld[q].push_back(id[v]);
                p0.push_back(pos);
                Skin k;
                for (int c = 0; c < 4; c++) { k.j[c] = s.joint[c]; k.w[c] = s.weight[c] / 255.0f; }
                s0.push_back(k);
            }
            for (size_t c = 0; c + 2 < pc.corners.size(); c += 3) {
                Tri t;
                t.piece = (int)pi;
                bool ok = true;
                for (int k = 0; k < 3; k++) {
                    const int src = (int)pc.corners[c + k][0];
                    if (src < 0 || src >= (int)pc.sources.size()) { ok = false; break; }
                    t.v[k] = id[src];
                    t.uv[k] = Vector2(pc.corners[c + k][1], pc.corners[c + k][2]);
                    const rtag_skin_source& s = pc.sources[src];
                    Vector3 n(s.normal[0], s.normal[1], s.normal[2]);
                    t.rn[k] = n.length_squared() > 1e-12f ? n.normalized() : Vector3();
                }
                if (!ok || t.v[0] == t.v[1] || t.v[1] == t.v[2] || t.v[2] == t.v[0]) { dropped++; continue; }
                const Vector3 g = (p0[t.v[1]] - p0[t.v[0]]).cross(p0[t.v[2]] - p0[t.v[0]]);
                if (g.length_squared() < 1e-14f) { dropped++; continue; }
                // wound counter-clockwise about the game's own normals (a strip's triangles alternate)
                if (g.dot(t.rn[0] + t.rn[1] + t.rn[2]) < 0.0f) { std::swap(t.v[1], t.v[2]); std::swap(t.uv[1], t.uv[2]); std::swap(t.rn[1], t.rn[2]); }
                tris.push_back(t);
            }
        }
        if (tris.empty()) { failed = "no triangles"; done = true; return; }
        // the same triangle twice in one packet (its strip's own overlap) once.  The same triangle in a later packet is a
        // DECAL: the game draws a second picture on the same vertices over the first (the eyes, brows and lips on a
        // face, the paint on a shield) - kept, as no part of the surface's shape, and drawn a hair above it
        std::vector<int> decal_tris(pieces.size(), 0), all_tris(pieces.size(), 0);
        {
            std::unordered_map<std::string, int> once;
            std::vector<Tri> kept;
            for (Tri t : tris) {
                int s[3] = {t.v[0], t.v[1], t.v[2]};
                std::sort(s, s + 3);
                std::string k((const char*)s, sizeof s);
                all_tris[t.piece]++;
                auto it = once.find(k);
                if (it == once.end()) { once[k] = t.piece; kept.push_back(t); continue; }
                if (it->second == t.piece) { dropped++; continue; }
                t.decal = true;
                decal_tris[t.piece]++;
                kept.push_back(t);
            }
            tris.swap(kept);
        }
        decal_piece.assign(pieces.size(), 0);
        size_t decals = 0;
        for (size_t pi = 0; pi < pieces.size(); pi++)
            if (all_tris[pi] > 0 && decal_tris[pi] * 2 > all_tris[pi]) { decal_piece[pi] = 1; decals++; }
        // (a packet only partly over another keeps its own shape: only its overlapping triangles are decals)
        // T-junctions: a packet's border edge with a vertex of the neighbouring packet lying on it (the two packets were
        // cut differently along their seam).  Each side would be subdivided as a curve of its own and part: a crack.  The
        // triangle is split at that vertex, so the seam is shared edges, and the surface runs smoothly across it.
        size_t tsplit = 0;
        for (int pass = 0; pass < 4; pass++) {
            std::vector<Edge> edges;
            std::unordered_map<uint64_t, int> eid;
            build_edges(tris, edges, eid);
            std::vector<char> on_border(p0.size(), 0);
            for (const Edge& e : edges) if (e.nf == 1) { on_border[e.a] = 1; on_border[e.b] = 1; }
            std::vector<int> border;
            for (size_t v = 0; v < p0.size(); v++) if (on_border[v]) border.push_back((int)v);
            if (border.empty()) break;
            std::vector<std::pair<int, int>> splits;     // (triangle, vertex)
            std::vector<char> taken(tris.size(), 0);
            for (const Edge& e : edges) {
                if (e.nf != 1 || taken[e.face[0]]) continue;
                const Vector3 A = p0[e.a], B = p0[e.b], AB = B - A;
                const float len2 = AB.length_squared();
                if (len2 < 1e-8f) continue;
                const float tol = std::max(WELD * 2.0f, std::sqrt(len2) * 0.01f);
                int best = -1;
                float best_d = tol;
                for (int v : border) {
                    if (v == e.a || v == e.b) continue;
                    const Vector3 P = p0[v];
                    const float t = (P - A).dot(AB) / len2;
                    if (t <= 0.02f || t >= 0.98f) continue;
                    const float d = (A + AB * t).distance_to(P);
                    if (d < best_d) { best_d = d; best = v; }
                }
                if (best >= 0) { splits.push_back({e.face[0], best}); taken[e.face[0]] = 1; }
            }
            if (splits.empty()) break;
            for (const auto& sp : splits) {
                const Tri t = tris[sp.first];
                const int v = sp.second;
                // which edge of the triangle the vertex lies on: the nearest
                int c = 0;
                float bd = 1e30f;
                for (int k = 0; k < 3; k++) {
                    const Vector3 A = p0[t.v[k]], AB = p0[t.v[(k + 1) % 3]] - A;
                    const float tt = std::clamp((p0[v] - A).dot(AB) / std::max(AB.length_squared(), 1e-12f), 0.0f, 1.0f);
                    const float d = (A + AB * tt).distance_to(p0[v]);
                    if (d < bd) { bd = d; c = k; }
                }
                const int a = c, b = (c + 1) % 3, o = (c + 2) % 3;
                const Vector3 A = p0[t.v[a]], AB = p0[t.v[b]] - A;
                const float u = std::clamp((p0[v] - A).dot(AB) / std::max(AB.length_squared(), 1e-12f), 0.0f, 1.0f);
                Tri t1 = t, t2 = t;
                // t1 = (a, v, o), t2 = (v, b, o)
                t1.v[b] = v; t1.uv[b] = t.uv[a].lerp(t.uv[b], u); t1.rn[b] = t.rn[a].lerp(t.rn[b], u).normalized();
                t2.v[a] = v; t2.uv[a] = t1.uv[b]; t2.rn[a] = t1.rn[b];
                (void)o;
                tris[sp.first] = t1;
                tris.push_back(t2);
                tsplit++;
            }
        }
        // the creases of level 0: the game's normals part across the edge (a hard edge), or the faces fold back on each other
        std::unordered_set<uint64_t> crease0;
        {
            std::vector<Edge> edges;
            std::unordered_map<uint64_t, int> eid;
            build_edges(tris, edges, eid);
            for (const Edge& e : edges) {
                if (e.nf != 2) continue;
                const Tri& f1 = tris[e.face[0]];
                const Tri& f2 = tris[e.face[1]];
                bool hard = corner_rn(f1, e.a).dot(corner_rn(f2, e.a)) < crease || corner_rn(f1, e.b).dot(corner_rn(f2, e.b)) < crease;
                const Vector3 n1 = (p0[f1.v[1]] - p0[f1.v[0]]).cross(p0[f1.v[2]] - p0[f1.v[0]]).normalized();
                const Vector3 n2 = (p0[f2.v[1]] - p0[f2.v[0]]).cross(p0[f2.v[2]] - p0[f2.v[0]]).normalized();
                if (n1.dot(n2) < -0.3f) hard = true;
                if (hard) crease0.insert(ekey(e.a, e.b));
            }
        }
        const size_t creases = crease0.size();
        const std::vector<float> covered0 = covered_by_layers(p0, tris, layer_reach);
        size_t covered_count = 0;
        for (float c : covered0) covered_count += c > 0.0f ? 1 : 0;
        // a dense model is split fewer times (each level is four times the triangles of the one before)
        while (levels > 1 && tris.size() * ((size_t)1 << (2 * levels)) > (size_t)max_tris) levels--;
        std::vector<Level> lv;
        std::vector<std::vector<Tri>> tris_at{tris};
        std::vector<int> nv_at{(int)p0.size()};
        std::unordered_set<uint64_t> cr = crease0;
        for (int l = 0; l < levels; l++) {
            Level L;
            std::vector<Tri> next;
            int nv = 0;
            step(nv_at.back(), tris_at.back(), cr, L, next, nv);
            lv.push_back(std::move(L));
            tris_at.push_back(std::move(next));
            nv_at.push_back(nv);
        }
        std::string fit_text;
        out.push_back(emit(tris, p0, s0, (int)pieces.size(), crease));     // level 0: the game's own mesh (far away)
        for (int l = 1; l <= levels; l++) {
            // fit the control points so that the subdivided surface passes through the game's vertices
            std::vector<Vector3> P = p0;
            float worst = 0.0f;
            for (int it = 0; it < fit; it++) {
                std::vector<Vector3> q = apply(lv, l, P);
                worst = 0.0f;
                for (size_t i = 0; i < p0.size(); i++) {
                    const Vector3 d = p0[i] - q[i];
                    worst = std::max(worst, d.length());
                    P[i] += d * keep;
                }
            }
            std::vector<Vector3> p = apply(lv, l, P);
            float after = 0.0f;
            for (size_t i = 0; i < p0.size(); i++) after = std::max(after, (p0[i] - p[i]).length());
            if (covered_count > 0 && layer_gap > 0.0f) {
                // the covered vertices drawn `gap` inside (the covered share subdivided as the positions are)
                std::vector<Vector3> c3(covered0.size());
                for (size_t i = 0; i < covered0.size(); i++) c3[i] = Vector3(covered0[i], 0, 0);
                c3 = apply(lv, l, c3);
                std::vector<Vector3> vn(p.size());
                for (const Tri& t : tris_at[l]) {
                    const Vector3 fn = (p[t.v[1]] - p[t.v[0]]).cross(p[t.v[2]] - p[t.v[0]]);
                    for (int c = 0; c < 3; c++) vn[t.v[c]] += fn;
                }
                for (size_t i = 0; i < p.size(); i++)
                    if (c3[i].x > 0.0f && vn[i].length_squared() > 1e-12f) p[i] -= vn[i].normalized() * (layer_gap * std::min(1.0f, c3[i].x));
            }
            std::vector<Skin> s = apply_skin(lv, l, s0);
            out.push_back(emit(tris_at[l], p, s, (int)pieces.size(), crease));
            char b[96];
            snprintf(b, sizeof b, " L%d %zu tris (fit: %.3f off at most)", l, out.back().triangles, after);
            fit_text += b;
        }
        const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        char b[512];
        snprintf(b, sizeof b, "%zu packets, %zu vertices welded, %zu triangles (%zu dropped, %zu split at T-junctions), %zu crease edges, %zu vertices under a layer, %zu decal packets;%s; %.0f ms",
                 pieces.size(), p0.size(), tris.size(), dropped, tsplit, creases, covered_count, decals, fit_text.c_str(), ms);
        stats = b;
        done = true;
    }
};

RtaRemaster::~RtaRemaster() {
    for (std::thread& t : threads) if (t.joinable()) t.join();
}

Dictionary RtaRemaster::scan(const Ref<RtaMachine>& machine) {
    Dictionary d;
    rtag_skeletons k;
    const rtag_scene* sc = nullptr;
    if (!frame_skeletons(machine, k, sc)) return d;
    std::vector<Group> gs, rej;
    groups(k, *sc, gs, &rej);
    Array rejected;
    for (const Group& g : rej) {
        Dictionary e;
        e["object"] = (int64_t)g.object;
        const int sk = g.skeleton >= 0 ? g.skeleton : g.first_skeleton;
        e["state"] = sk >= 0 && sk < (int)k.skeleton_count ? (int64_t)k.skeletons[sk].state : (int64_t)0;
        e["skinned"] = (int64_t)g.pieces.size();
        e["rigid"] = (int64_t)g.rigid;
        e["unskinned"] = (int64_t)g.unskinned;
        e["other_skeleton"] = (int64_t)g.other_skeleton;
        rejected.push_back(e);
    }
    d["rejected"] = rejected;
    Array figures;
    for (const Group& g : gs) {
        const rtag_skeleton& s = k.skeletons[g.skeleton];
        Dictionary e;
        e["object"] = (int64_t)g.object;
        e["skeleton"] = g.skeleton;
        e["state"] = (int64_t)s.state;
        e["joints"] = s.joint_count;
        e["key"] = String(hex(g.key).c_str());
        PackedInt32Array pieces;
        PackedStringArray keys;
        for (size_t i = 0; i < g.pieces.size(); i++) {
            pieces.push_back((int32_t)g.pieces[i]);
            auto it = hex_cache.find(g.hashes[i]);
            if (it == hex_cache.end()) {
                if (hex_cache.size() > 200000) hex_cache.clear();
                it = hex_cache.emplace(g.hashes[i], String(hex(g.hashes[i]).c_str())).first;
            }
            keys.push_back(it->second);
        }
        e["pieces"] = pieces;
        e["piece_keys"] = keys;
        PackedInt32Array shiny, under;
        for (size_t i = 0; i < g.shiny.size(); i++) if (g.shiny[i]) shiny.push_back((int32_t)i);
        for (size_t i = 0; i < g.under.size(); i++) under.push_back((int32_t)g.under[i]);
        PackedInt32Array env;
        for (size_t i = 0; i < g.env_pass.size(); i++) env.push_back((int32_t)g.env_pass[i]);
        e["env"] = env;
        e["shiny"] = shiny;
        e["under"] = under;
        e["passes"] = Vector3i((int32_t)g.rigid, (int32_t)g.unskinned, (int32_t)g.env);     // (debugging) left to the game
        e["root"] = Vector3(s.joint[0][3], s.joint[0][7], s.joint[0][11]);
        // the box of its joints (the camera of the tests aims at its middle)
        Vector3 lo(s.joint[0][3], s.joint[0][7], s.joint[0][11]), hi = lo;
        for (int j = 1; j < (int)s.joint_count && j < 64; j++) {
            const Vector3 v(s.joint[j][3], s.joint[j][7], s.joint[j][11]);
            lo = Vector3(std::min(lo.x, v.x), std::min(lo.y, v.y), std::min(lo.z, v.z));
            hi = Vector3(std::max(hi.x, v.x), std::max(hi.y, v.y), std::max(hi.z, v.z));
        }
        e["low"] = lo;
        e["high"] = hi;
        e["corners"] = (int64_t)g.corners;
        figures.push_back(e);
    }
    d["figures"] = figures;
    Array players;
    for (uint32_t i = 0; i < std::min<uint32_t>(k.player_count, 4); i++) {
        Dictionary e;
        e["slot"] = k.players[i].slot;
        e["state"] = (int64_t)k.players[i].state;
        e["object"] = (int64_t)k.players[i].object;
        e["character_class"] = k.players[i].character_class;
        players.push_back(e);
    }
    d["players"] = players;
    return d;
}

String RtaRemaster::bake_start(const Ref<RtaMachine>& machine, int64_t object, const Dictionary& options) {
    rtag_skeletons k;
    const rtag_scene* sc = nullptr;
    if (!frame_skeletons(machine, k, sc)) return "";
    std::vector<Group> gs;
    groups(k, *sc, gs);
    for (const Group& g : gs) {
        if ((int64_t)g.object != object) continue;
        const std::string key = hex(g.key);
        if (jobs.count(key)) return String(key.c_str());
        auto job = std::make_shared<Job>();
        job->levels = std::clamp((int)options.get("levels", 2), 1, 3);
        job->fit = std::clamp((int)options.get("fit", 4), 0, 12);
        job->crease = (float)(double)options.get("crease", 0.5);
        job->keep = (float)(double)options.get("keep", 0.8);
        job->max_tris = std::max(1000, (int)options.get("max_tris", 80000));
        job->layer_reach = (float)(double)options.get("layer_reach", 2.0);
        job->layer_gap = (float)(double)options.get("layer_gap", 0.3);
        const uint32_t full = std::min(k.full_count, sc->full_count);
        for (size_t n = 0; n < g.pieces.size(); n++) {
            const uint32_t i = g.pieces[n];
            const rtag_skin_piece& p = k.pieces[i];
            const rtag_scene_piece& q = sc->pieces[i];
            Job::Piece pc;
            if (p.source_first + p.source_count <= k.source_count) pc.sources.assign(k.sources + p.source_first, k.sources + p.source_first + p.source_count);
            for (uint32_t c = q.full_first; c < q.full_first + q.full_count && c < full; c++)
                pc.corners.push_back({(float)k.full_source[c], sc->full[c].u, sc->full[c].v});
            job->pieces.push_back(std::move(pc));
            job->piece_keys.push_back(hex(g.hashes[n]));
        }
        jobs[key] = job;
        threads.emplace_back([job]() { job->run(); });
        return String(key.c_str());
    }
    return "";
}

int64_t RtaRemaster::bakes_running() const {
    int64_t n = 0;
    for (const auto& e : jobs) n += e.second->done ? 0 : 1;
    return n;
}

Dictionary RtaRemaster::bake_take(const String& key) {
    Dictionary d;
    auto it = jobs.find(std::string(key.utf8().get_data()));
    if (it == jobs.end()) { d["failed"] = "unknown"; return d; }
    Job& j = *it->second;
    if (!j.done) return d;
    if (!j.failed.empty()) { d["failed"] = String(j.failed.c_str()); return d; }
    Array levels;
    for (const OutLevel& L : j.out) {
        Array surfaces;
        for (const OutSurface& s : L.surfaces) {
            Array a;
            a.resize(Mesh::ARRAY_MAX);
            PackedVector3Array pos, nrm;
            PackedFloat32Array tan, wts;
            PackedVector2Array uv;
            PackedInt32Array bones, index;
            pos.resize(s.pos.size()); nrm.resize(s.nrm.size()); tan.resize(s.tan.size()); uv.resize(s.uv.size());
            bones.resize(s.bones.size()); wts.resize(s.weights.size()); index.resize(s.index.size());
            if (!s.pos.empty()) {
                memcpy(pos.ptrw(), s.pos.data(), sizeof(Vector3) * s.pos.size());
                memcpy(nrm.ptrw(), s.nrm.data(), sizeof(Vector3) * s.nrm.size());
                memcpy(tan.ptrw(), s.tan.data(), sizeof(float) * s.tan.size());
                memcpy(uv.ptrw(), s.uv.data(), sizeof(Vector2) * s.uv.size());
                memcpy(bones.ptrw(), s.bones.data(), sizeof(int) * s.bones.size());
                memcpy(wts.ptrw(), s.weights.data(), sizeof(float) * s.weights.size());
                memcpy(index.ptrw(), s.index.data(), sizeof(int) * s.index.size());
                a[Mesh::ARRAY_VERTEX] = pos;
                a[Mesh::ARRAY_NORMAL] = nrm;
                a[Mesh::ARRAY_TANGENT] = tan;
                a[Mesh::ARRAY_TEX_UV] = uv;
                a[Mesh::ARRAY_BONES] = bones;
                a[Mesh::ARRAY_WEIGHTS] = wts;
                a[Mesh::ARRAY_INDEX] = index;
            }
            surfaces.push_back(a);
        }
        Dictionary e;
        e["surfaces"] = surfaces;
        e["triangles"] = (int64_t)L.triangles;
        levels.push_back(e);
    }
    d["levels"] = levels;
    PackedStringArray keys;
    for (const std::string& s : j.piece_keys) keys.push_back(String(s.c_str()));
    d["piece_keys"] = keys;
    PackedInt32Array decals;
    for (size_t i = 0; i < j.decal_piece.size(); i++) if (j.decal_piece[i]) decals.push_back((int32_t)i);
    d["decals"] = decals;
    d["stats"] = String(j.stats.c_str());
    j.out.clear();                      // handed over: the job stays as the record that this key was baked
    j.out.shrink_to_fit();
    return d;
}

Array RtaRemaster::merge(const Array& surfaces, const PackedInt32Array& groups, int64_t count) const {
    Array out;
    out.resize(count);
    struct Acc { PackedVector3Array pos, nrm; PackedFloat32Array tan, wts; PackedVector2Array uv; PackedInt32Array bones, index; };
    std::vector<Acc> acc(count);
    for (int64_t i = 0; i < surfaces.size() && i < groups.size(); i++) {
        const int g = groups[i];
        if (g < 0 || g >= count || surfaces[i].get_type() != Variant::ARRAY) continue;
        const Array a = surfaces[i];
        if (a.size() < Mesh::ARRAY_MAX || a[Mesh::ARRAY_VERTEX].get_type() != Variant::PACKED_VECTOR3_ARRAY) continue;
        Acc& c = acc[g];
        const int base = (int)c.pos.size();
        c.pos.append_array(a[Mesh::ARRAY_VERTEX]);
        c.nrm.append_array(a[Mesh::ARRAY_NORMAL]);
        c.tan.append_array(a[Mesh::ARRAY_TANGENT]);
        c.uv.append_array(a[Mesh::ARRAY_TEX_UV]);
        c.bones.append_array(a[Mesh::ARRAY_BONES]);
        c.wts.append_array(a[Mesh::ARRAY_WEIGHTS]);
        const PackedInt32Array idx = a[Mesh::ARRAY_INDEX];
        const int64_t at = c.index.size();
        c.index.resize(at + idx.size());
        int32_t* w = c.index.ptrw();
        const int32_t* r = idx.ptr();
        for (int64_t k = 0; k < idx.size(); k++) w[at + k] = r[k] + base;
    }
    for (int64_t g = 0; g < count; g++) {
        Array a;
        a.resize(Mesh::ARRAY_MAX);
        if (!acc[g].pos.is_empty()) {
            a[Mesh::ARRAY_VERTEX] = acc[g].pos;
            a[Mesh::ARRAY_NORMAL] = acc[g].nrm;
            a[Mesh::ARRAY_TANGENT] = acc[g].tan;
            a[Mesh::ARRAY_TEX_UV] = acc[g].uv;
            a[Mesh::ARRAY_BONES] = acc[g].bones;
            a[Mesh::ARRAY_WEIGHTS] = acc[g].wts;
            a[Mesh::ARRAY_INDEX] = acc[g].index;
        }
        out[g] = a;
    }
    return out;
}

bool RtaRemaster::pose(const Ref<RtaMachine>& machine, int64_t skeleton, const RID& rid) {
    rtag_skeletons k;
    const rtag_scene* sc = nullptr;
    if (!frame_skeletons(machine, k, sc) || skeleton < 0 || skeleton >= (int64_t)k.skeleton_count) return false;
    const rtag_skeleton& s = k.skeletons[skeleton];
    const int n = s.joint_count > 0 ? s.joint_count : 64;
    RenderingServer* rs = RenderingServer::get_singleton();
    Pose& P = poses[rid.get_id()];
    if (P.n != n) {
        rs->skeleton_allocate_data(rid, n);
        P.n = n;
        P.now.clear();
    }
    P.before = P.now.empty() ? std::vector<float>(&s.skin[0][0], &s.skin[0][0] + n * 12) : P.now;
    P.now.assign(&s.skin[0][0], &s.skin[0][0] + n * 12);
    for (int j = 0; j < n; j++) rs->skeleton_bone_set_transform(rid, j, rows34(s.skin[j]));
    return true;
}

bool RtaRemaster::skin_palette(const RID& rid, const PackedInt32Array& binds, const Array& globals, const Array& inverse_bind) const {
    if (!rid.is_valid() || binds.size() != inverse_bind.size()) return false;
    // Validate before changing any bone. Missing global bones keep the script's
    // identity transform; malformed palettes are refused as a whole.
    for (int64_t q = 0; q < binds.size(); ++q) {
        const int bone = binds[q];
        if (bone >= globals.size() || inverse_bind[q].get_type() != Variant::TRANSFORM3D) return false;
        if (bone >= 0 && globals[bone].get_type() != Variant::NIL && globals[bone].get_type() != Variant::TRANSFORM3D) return false;
    }
    RenderingServer* rs = RenderingServer::get_singleton();
    for (int64_t q = 0; q < binds.size(); ++q) {
        const int bone = binds[q];
        Transform3D value;
        if (bone >= 0 && globals[bone].get_type() != Variant::NIL) {
            // Use the engine's operator, just as GDScript does. The extension's
            // compiled matrix multiply can differ in its final floating-point bit.
            Variant product;
            bool valid = false;
            Variant::evaluate(Variant::OP_MULTIPLY, globals[bone], inverse_bind[q], product, valid);
            if (!valid) return false; // types were checked above
            value = product;
        }
        rs->skeleton_bone_set_transform(rid, q, value);
    }
    return true;
}

void RtaRemaster::tween(const RID& rid, double t) {
    auto it = poses.find(rid.get_id());
    if (it == poses.end() || it->second.now.empty()) return;
    const Pose& P = it->second;
    const float w = (float)(1.0 + t);
    RenderingServer* rs = RenderingServer::get_singleton();
    float m[12];
    for (int j = 0; j < P.n; j++) {
        for (int c = 0; c < 12; c++) m[c] = P.before[j * 12 + c] + (P.now[j * 12 + c] - P.before[j * 12 + c]) * w;
        rs->skeleton_bone_set_transform(rid, j, rows34(m));
    }
}

void RtaRemaster::forget(const RID& rid) { poses.erase(rid.get_id()); }

// The game's own light on a figure this frame, as a function of the surface's direction: its vertex program's colour at
// every corner of the figure's packets (rtag_scene_full r, g, b: ambient + sun + fill + two point lights, the poison's and
// the hit flash's tints, clamped at 255 - all of it) against the corner's normal, fitted by second-order spherical
// harmonics (nine coefficients a channel; a sum of Lambert lobes is within a few percent of its fit).  The remastered
// surface takes its light from this at its own normal: exactly as bright as the game's figure, from every light the game
// has, without modelling any of them.  [] when the figure has too few corners this frame.
PackedVector4Array RtaRemaster::light_sh(const Ref<RtaMachine>& machine, const PackedInt32Array& pieces) {
    PackedVector4Array out;
    rtag_skeletons k;
    const rtag_scene* sc = nullptr;
    if (!frame_skeletons(machine, k, sc) || !sc->full) return out;
    double A[9][9] = {}, B[9][3] = {};
    size_t n = 0;
    for (int64_t pi = 0; pi < pieces.size(); pi++) {
        const uint32_t i = (uint32_t)pieces[pi];
        if (i >= sc->piece_count) continue;
        const rtag_scene_piece& q = sc->pieces[i];
        const uint32_t end = std::min(q.full_first + q.full_count, sc->full_count);
        for (uint32_t c = q.full_first; c < end; c += 2) {
            const rtag_scene_full& f = sc->full[c];
            const float l = std::sqrt(f.nx * f.nx + f.ny * f.ny + f.nz * f.nz);
            if (l < 0.5f) continue;
            const double x = f.nx / l, y = f.ny / l, z = f.nz / l;
            const double Y[9] = {1.0, y, z, x, x * y, y * z, 3.0 * z * z - 1.0, x * z, x * x - y * y};
            const double col[3] = {f.r / 128.0, f.g / 128.0, f.b / 128.0};
            for (int a = 0; a < 9; a++) {
                // The normal matrix is symmetric. Accumulate each product once,
                // in the original corner order, then mirror it before solving.
                for (int b = a; b < 9; b++) A[a][b] += Y[a] * Y[b];
                for (int ch = 0; ch < 3; ch++) B[a][ch] += Y[a] * col[ch];
            }
            n++;
        }
    }
    if (n < 24) return out;
    for (int a = 0; a < 9; a++)
        for (int b = 0; b < a; b++) A[a][b] = A[b][a];
    // ridge (the bands of directions a figure's normals do not cover stay near the mean) and Gauss-Jordan
    for (int a = 0; a < 9; a++) A[a][a] += (a == 0 ? 1e-6 : 0.02) * (double)n;
    for (int col = 0; col < 9; col++) {
        int piv = col;
        for (int r = col + 1; r < 9; r++) if (std::fabs(A[r][col]) > std::fabs(A[piv][col])) piv = r;
        if (std::fabs(A[piv][col]) < 1e-12) return out;
        if (piv != col) { for (int c2 = 0; c2 < 9; c2++) std::swap(A[col][c2], A[piv][c2]); for (int ch = 0; ch < 3; ch++) std::swap(B[col][ch], B[piv][ch]); }
        const double d = A[col][col];
        for (int c2 = 0; c2 < 9; c2++) A[col][c2] /= d;
        for (int ch = 0; ch < 3; ch++) B[col][ch] /= d;
        for (int r = 0; r < 9; r++) {
            if (r == col) continue;
            const double f = A[r][col];
            if (f == 0.0) continue;
            for (int c2 = 0; c2 < 9; c2++) A[r][c2] -= f * A[col][c2];
            for (int ch = 0; ch < 3; ch++) B[r][ch] -= f * B[col][ch];
        }
    }
    out.resize(9);
    for (int a = 0; a < 9; a++) out.set(a, Vector4((real_t)B[a][0], (real_t)B[a][1], (real_t)B[a][2], 0));
    return out;
}

// ---- maps ---------------------------------------------------------------------------------------------------------------
// RM_TEXELS_BEGIN - plain C++ (no Godot types): the texel analysis and classes, also built by the local tuning tool
// (local/model-remaster/texels: the same code run over the pictures a session dumped, RTA_REMASTER_DUMP)
namespace rmt {

enum Cls { SKIN = 0, LEATHER, METAL, CLOTH, HAIR, FUR, STONE, NCLS };
static const char* const NAMES[NCLS] = {"skin", "leather", "metal", "cloth", "hair", "fur", "stone"};

inline void box_blur(std::vector<float>& a, int w, int h, int r) {
    if (r <= 0) return;
    std::vector<float> t(a.size());
    for (int y = 0; y < h; y++) {
        double s = 0;
        int n = 0;
        for (int x = -r; x <= r; x++) { const int xx = std::clamp(x, 0, w - 1); s += a[y * w + xx]; n++; }
        for (int x = 0; x < w; x++) {
            t[y * w + x] = (float)(s / n);
            const int out = std::clamp(x - r, 0, w - 1), in = std::clamp(x + r + 1, 0, w - 1);
            s += a[y * w + in] - a[y * w + out];
        }
    }
    for (int x = 0; x < w; x++) {
        double s = 0;
        int n = 0;
        for (int y = -r; y <= r; y++) { const int yy = std::clamp(y, 0, h - 1); s += t[yy * w + x]; n++; }
        for (int y = 0; y < h; y++) {
            a[y * w + x] = (float)(s / n);
            const int out = std::clamp(y - r, 0, h - 1), in = std::clamp(y + r + 1, 0, h - 1);
            s += t[in * w + x] - t[out * w + x];
        }
    }
}

struct Settings {
    float scale = 1.0f;         // picture pixels per game texel (the art pack's pictures are 4x)
    int forced = -1;            // every texel this class
    int strands = HAIR;         // what streaked texels are: HAIR (a person's) or FUR (a beast's)
    bool grey_metal = true;     // grey, worked, shaded texels may be metal (off: a figure in grey cloth)
    bool gold = true;           // ochre and yellow texels may be gold (off: a beast with an ochre hide)
    int prefer = -1;            // what would be leather, cloth or strands is this instead (a picture of a body: skin)
    struct Rule { int cls; float h0, h1, s0, s1, v0, v1; };
    std::vector<Rule> rules;    // a figure's own: texels of this hue (h0 > h1: wraps past red), saturation, value are this class
    bool stone = false;         // grey grainy texels may be stone (a creature's)
    float skin_hue_lo = -0.03f, skin_hue_hi = 0.105f;   // the hue band of skin (0..1; red at 0); a green or blue people's own
    float skin_v_lo = 0.42f, skin_s_hi = 0.7f;         // skin is at least this bright and at most this saturated (a dark people's own)
};

struct Texels {
    int w = 0, h = 0;
    std::vector<float> lum, hue, sat, val, lb, broad, height, contrast, grain, coh, energy, dir_c, dir_s, stripes, density, spread;
    std::vector<uint8_t> cls;
    double share[NCLS] = {};
};

inline float hue_in(float h, float lo, float hi) {        // inside the band [lo, hi] (lo may be below 0: wraps)
    if (lo < 0.0f) return (h >= 1.0f + lo || h <= hi) ? 1.0f : 0.0f;
    return (h >= lo && h <= hi) ? 1.0f : 0.0f;
}

// rgba: w*h*4 bytes
inline void analyse(const uint8_t* src, int w, int h, const Settings& st, Texels& t) {
    const size_t n = (size_t)w * h;
    t.w = w; t.h = h;
    t.lum.assign(n, 0); t.hue.assign(n, 0); t.sat.assign(n, 0); t.val.assign(n, 0);
    for (size_t i = 0; i < n; i++) {
        const float r = src[i * 4] / 255.0f, g = src[i * 4 + 1] / 255.0f, b = src[i * 4 + 2] / 255.0f;
        t.lum[i] = 0.299f * r + 0.587f * g + 0.114f * b;
        const float mx = std::max(r, std::max(g, b)), mn = std::min(r, std::min(g, b)), c = mx - mn;
        t.val[i] = mx;
        t.sat[i] = mx > 1e-4f ? c / mx : 0.0f;
        float hh = 0.0f;
        if (c > 1e-4f) {
            if (mx == r) hh = std::fmod((g - b) / c + 6.0f, 6.0f);
            else if (mx == g) hh = (b - r) / c + 2.0f;
            else hh = (r - g) / c + 4.0f;
        }
        t.hue[i] = hh / 6.0f;
    }
    const float scale = st.scale;
    // edge-aware: a bilateral filter of the luminance (a painted edge stays, the noise of the upscale goes)
    const int R = std::max(1, (int)std::lround(scale * 0.6f));
    t.lb.assign(n, 0);
    {
        const float ss = 2.0f * (R * 0.75f) * (R * 0.75f), sr = 2.0f * 0.1f * 0.1f;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++) {
                const float c = t.lum[y * w + x];
                float s = 0, ws = 0;
                for (int dy = -R; dy <= R; dy++) {
                    const int yy = std::clamp(y + dy, 0, h - 1);
                    for (int dx = -R; dx <= R; dx++) {
                        const int xx = std::clamp(x + dx, 0, w - 1);
                        const float v = t.lum[yy * w + xx], dv = v - c;
                        const float k = std::exp(-(dx * dx + dy * dy) / ss - dv * dv / sr);
                        s += v * k;
                        ws += k;
                    }
                }
                t.lb[y * w + x] = s / ws;
            }
    }
    // the broad shading painted into the texture taken off: what is left is the relief
    t.broad = t.lb;
    box_blur(t.broad, w, h, std::max(2, (int)std::lround(scale * 3.0f)));
    t.height.assign(n, 0);
    for (size_t i = 0; i < n; i++) t.height[i] = t.lb[i] - 0.75f * t.broad[i];
    // local contrast at the texel's own size (metal: worn bright edges; skin: smooth) and the grain under it (stone, cloth weave)
    t.contrast.assign(n, 0);
    t.grain.assign(n, 0);
    {
        std::vector<float> m = t.lum;
        box_blur(m, w, h, std::max(1, (int)std::lround(scale)));
        for (size_t i = 0; i < n; i++) t.contrast[i] = std::fabs(t.lum[i] - m[i]);
        t.grain = t.contrast;
        box_blur(t.contrast, w, h, std::max(1, (int)std::lround(scale * 1.5f)));
        std::vector<float> m2 = t.lum;
        box_blur(m2, w, h, std::max(1, (int)std::lround(scale * 0.5f)));
        for (size_t i = 0; i < n; i++) t.grain[i] = std::fabs(t.lum[i] - m2[i]);
        box_blur(t.grain, w, h, std::max(1, (int)std::lround(scale * 2.0f)));
    }
    // streaks (hair, fur): the structure tensor of the luminance - how much of its change runs across one direction
    // (coherence) and which; a strand runs across its gradient
    t.coh.assign(n, 0); t.energy.assign(n, 0); t.dir_c.assign(n, 1); t.dir_s.assign(n, 0); t.stripes.assign(n, 0);
    {
        // stripes: many parallel lines, not one edge - the gradients across a run of strands point both ways and cancel
        // (|mean gradient| small against the mean of |gradient|); across a single edge they all point one way
        std::vector<float> jxx(n), jxy(n), jyy(n), sgx(n), sgy(n), mag(n);
        auto L = [&](int xx, int yy) { return t.lum[std::clamp(yy, 0, h - 1) * w + std::clamp(xx, 0, w - 1)]; };
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++) {
                const float gx = (L(x + 1, y - 1) + 2 * L(x + 1, y) + L(x + 1, y + 1) - L(x - 1, y - 1) - 2 * L(x - 1, y) - L(x - 1, y + 1)) / 8.0f;
                const float gy = (L(x - 1, y + 1) + 2 * L(x, y + 1) + L(x + 1, y + 1) - L(x - 1, y - 1) - 2 * L(x, y - 1) - L(x + 1, y - 1)) / 8.0f;
                const size_t i = (size_t)y * w + x;
                jxx[i] = gx * gx; jxy[i] = gx * gy; jyy[i] = gy * gy;
                sgx[i] = gx; sgy[i] = gy; mag[i] = std::sqrt(gx * gx + gy * gy);
            }
        const int r = std::max(1, (int)std::lround(scale * 2.0f));
        box_blur(jxx, w, h, r); box_blur(jxy, w, h, r); box_blur(jyy, w, h, r);
        box_blur(sgx, w, h, r); box_blur(sgy, w, h, r); box_blur(mag, w, h, r);
        for (size_t i = 0; i < n; i++) t.stripes[i] = mag[i] > 1e-6f ? 1.0f - std::sqrt(sgx[i] * sgx[i] + sgy[i] * sgy[i]) / mag[i] : 0.0f;
        // density: the share of a wider window (4 game texels round) that is edge - a run of strands fills it, one painted
        // line or ridge (whose two sides cancel as strands do) does not
        t.density.assign(n, 0.0f);
        std::vector<float> raw(n);
        {
            auto L2 = [&](int xx, int yy) { return t.lb[std::clamp(yy, 0, h - 1) * w + std::clamp(xx, 0, w - 1)]; };
            const int d = std::max(1, (int)std::lround(scale * 0.5f));
            for (int y = 0; y < h; y++)
                for (int x = 0; x < w; x++) {
                    const float gx = L2(x + d, y) - L2(x - d, y), gy = L2(x, y + d) - L2(x, y - d);
                    raw[(size_t)y * w + x] = std::sqrt(gx * gx + gy * gy) > 0.045f ? 1.0f : 0.0f;
                }
        }
        t.density = raw;
        box_blur(t.density, w, h, std::max(2, (int)std::lround(scale * 4.0f)));
        // spread: the luminance's spread over the same window (skin and plain leather: small; trims, studs, mail: large)
        t.spread.assign(n, 0.0f);
        {
            // over the painted texels only: the empty (near black) space between a picture's islands is no part of it
            std::vector<float> m(n), m2(n), mk(n);
            for (size_t i = 0; i < n; i++) {
                mk[i] = t.val[i] > 0.06f ? 1.0f : 0.0f;
                m[i] = t.lum[i] * mk[i];
                m2[i] = t.lum[i] * t.lum[i] * mk[i];
            }
            const int r2 = std::max(2, (int)std::lround(scale * 3.0f));
            box_blur(m, w, h, r2);
            box_blur(m2, w, h, r2);
            box_blur(mk, w, h, r2);
            for (size_t i = 0; i < n; i++) {
                const float a = m[i] / std::max(mk[i], 1e-4f), b = m2[i] / std::max(mk[i], 1e-4f);
                t.spread[i] = mk[i] > 1e-4f ? std::sqrt(std::max(0.0f, b - a * a)) : 0.0f;
            }
        }
        for (size_t i = 0; i < n; i++) {
            const float a = jxx[i] - jyy[i], b = 2.0f * jxy[i], e = jxx[i] + jyy[i];
            const float d = std::sqrt(a * a + b * b);
            t.coh[i] = e > 1e-7f ? d / e : 0.0f;
            t.energy[i] = std::sqrt(std::max(e, 0.0f)) * scale;      // per game texel
            // the gradient's doubled angle is (a, b) / d; the strand's is opposite
            if (d > 1e-9f) { t.dir_c[i] = -a / d; t.dir_s[i] = -b / d; }
        }
    }
    // classes per texel, then the majority round each
    std::vector<float> share[NCLS];
    for (int c = 0; c < NCLS; c++) share[c].assign(n, 0.0f);
    for (size_t i = 0; i < n; i++) {
        int c = CLOTH;
        const float hh = t.hue[i], s = t.sat[i], v = t.val[i], k = t.contrast[i], gr = t.grain[i], co = t.coh[i], en = t.energy[i];
        const bool skin_hue = hue_in(hh, st.skin_hue_lo, st.skin_hue_hi) > 0.5f;
        const bool streaked = co > 0.5f && t.stripes[i] > 0.55f && t.density[i] > 0.45f && en > 0.03f;
        const float sp = t.spread[i];
        // gold: a saturated ochre (dark, as the painters shade it) or a bright yellow; silver, iron, mail: grey and shaded
        const bool gold = st.gold && hh > 0.098f && hh < 0.16f && ((s > 0.68f && v > 0.14f) || (s > 0.52f && v > 0.55f));     // (gold before strands)
        // (a single painted edge in grey cloth is no metal: worked metal - mail, engraving - is edges all over, bright
        // silver is shaded and light)
        const bool grey_metal = st.grey_metal && st.prefer != SKIN && s < 0.32f && v > 0.18f && sp > 0.045f && (t.density[i] > 0.33f || (s < 0.26f && v > 0.42f && sp > 0.05f));
        (void)k;
        int ruled = -1;
        for (const Settings::Rule& r : st.rules) {
            const bool hue_ok = r.h0 <= r.h1 ? (hh >= r.h0 && hh <= r.h1) : (hh >= r.h0 || hh <= r.h1);
            if (hue_ok && s >= r.s0 && s <= r.s1 && v >= r.v0 && v <= r.v1) { ruled = r.cls; break; }
        }
        if (st.forced >= 0) c = st.forced;
        else if (ruled >= 0) c = ruled;
        else if (gold && s > 0.6f) c = METAL;           // (a gold trim's edges look like strands)
        else if (streaked && skin_hue && s > 0.14f && s < st.skin_s_hi && v > st.skin_v_lo) c = SKIN;   // brows, lashes, lips painted on a face
        else if (streaked && v > 0.08f) c = st.strands;
        else if (gold || grey_metal) c = METAL;
        else if (skin_hue && s > 0.14f && s < st.skin_s_hi && v > st.skin_v_lo && sp < 0.09f) c = SKIN;
        else if (st.stone && s < 0.14f && v > 0.15f && v < 0.7f && gr > 0.02f) c = STONE;
        else if (hh > 0.02f && hh < 0.15f && s > 0.3f && v > 0.05f && v <= 0.62f) c = LEATHER;
        // a picture declared of one stuff (auto:<class>): what would be leather, cloth or strands is that stuff (its gold,
        // its grey metal, its skin stay what they are)
        if (st.prefer >= 0 && st.forced < 0 && ruled < 0 && (c == LEATHER || c == CLOTH || c == HAIR || c == FUR) && v > 0.1f) c = st.prefer;
        share[c][i] = 1.0f;
    }
    t.cls.assign(n, 0);
    for (int c = 0; c < NCLS; c++) { box_blur(share[c], w, h, std::max(1, (int)std::lround(scale * 1.5f))); t.share[c] = 0; }
    for (size_t i = 0; i < n; i++) {
        int best = 0;
        for (int c = 1; c < NCLS; c++) if (share[c][i] > share[best][i]) best = c;
        t.cls[i] = (uint8_t)best;
        t.share[best] += 1.0 / (double)n;
    }
}

// the maps of the analysed texels: normal (rgb), ORM (r cavity, g roughness, b metal, a fur), and AUX (r skin, g hair,
// b/a the strand's doubled angle in the picture, cos and sin * 0.5 + 0.5), each w*h*4 bytes (normal: rgb + 255)
inline void maps(const Texels& t, float strength, float scale, float metal_amt, float rough_mul, uint8_t* np, uint8_t* op, uint8_t* ap) {
    const int w = t.w, h = t.h;
    const float bump = strength * scale;
    //                                        skin   leather metal  cloth  hair   fur    stone
    static const float CLS_ROUGH[NCLS] =     {0.48f, 0.58f,  0.26f, 0.88f, 0.55f, 0.78f, 0.92f};
    static const float CLS_BUMP[NCLS] =      {0.35f, 0.9f,   0.6f,  1.0f,  0.5f,  0.8f,  1.25f};
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++) {
            auto H = [&](int xx, int yy) { return t.height[std::clamp(yy, 0, h - 1) * w + std::clamp(xx, 0, w - 1)]; };
            const float gx = (H(x + 1, y - 1) + 2 * H(x + 1, y) + H(x + 1, y + 1) - H(x - 1, y - 1) - 2 * H(x - 1, y) - H(x - 1, y + 1)) / 8.0f;
            const float gy = (H(x - 1, y + 1) + 2 * H(x, y + 1) + H(x + 1, y + 1) - H(x - 1, y - 1) - 2 * H(x, y - 1) - H(x + 1, y - 1)) / 8.0f;
            const size_t i = (size_t)y * w + x;
            const int c = t.cls[i];
            const float b = bump * CLS_BUMP[c];
            float nx = -gx * b, ny = gy * b, nz = 1.0f;     // +v is down the picture: up (green) is -v, so the slope along up is -gy
            const float nl = std::sqrt(nx * nx + ny * ny + nz * nz);
            nx /= nl; ny /= nl; nz /= nl;
            np[i * 4] = (uint8_t)std::clamp((int)std::lround((nx * 0.5f + 0.5f) * 255.0f), 0, 255);
            np[i * 4 + 1] = (uint8_t)std::clamp((int)std::lround((ny * 0.5f + 0.5f) * 255.0f), 0, 255);
            np[i * 4 + 2] = (uint8_t)std::clamp((int)std::lround((nz * 0.5f + 0.5f) * 255.0f), 0, 255);
            np[i * 4 + 3] = 255;
            // a cavity where the relief is below its surroundings (stone deeper); roughness by class, worn spots rougher
            const float cav_k = c == STONE ? 4.5f : (c == SKIN ? 1.5f : 3.0f);
            const float cav = std::clamp(1.0f - std::max(0.0f, t.broad[i] * 0.25f - t.height[i]) * cav_k, 0.5f, 1.0f);
            float rough = CLS_ROUGH[c] + (0.5f - t.lb[i]) * 0.1f + t.contrast[i] * 0.35f;
            if (c == METAL) rough = CLS_ROUGH[c] + (1.0f - t.val[i]) * 0.3f + t.grain[i] * 1.5f;   // polished where bright
            if (c == SKIN) rough = CLS_ROUGH[c] + t.grain[i] * 0.8f;
            rough = std::clamp(rough * rough_mul, 0.1f, 1.0f);
            const float metal = c == METAL ? metal_amt * std::clamp(0.55f + t.val[i] * 0.55f, 0.0f, 1.0f) : 0.0f;
            op[i * 4] = (uint8_t)std::lround(cav * 255.0f);
            op[i * 4 + 1] = (uint8_t)std::lround(rough * 255.0f);
            op[i * 4 + 2] = (uint8_t)std::lround(std::clamp(metal, 0.0f, 1.0f) * 255.0f);
            op[i * 4 + 3] = c == FUR ? 255 : 0;
            ap[i * 4] = c == SKIN ? 255 : 0;
            ap[i * 4 + 1] = c == HAIR ? 255 : 0;
            ap[i * 4 + 2] = (uint8_t)std::clamp((int)std::lround((t.dir_c[i] * 0.5f + 0.5f) * 255.0f), 0, 255);
            ap[i * 4 + 3] = (uint8_t)std::clamp((int)std::lround((t.dir_s[i] * 0.5f + 0.5f) * 255.0f), 0, 255);
        }
}

// a picture of the classes (for looking at them): one colour a class
inline void class_picture(const Texels& t, uint8_t* out /* w*h*3 */) {
    static const uint8_t C[NCLS][3] = {{240, 170, 140}, {130, 80, 40}, {80, 200, 255}, {120, 120, 120}, {250, 230, 60}, {230, 120, 20}, {170, 170, 200}};
    for (size_t i = 0; i < (size_t)t.w * t.h; i++) for (int k = 0; k < 3; k++) out[i * 3 + k] = C[t.cls[i]][k];
}

}  // namespace rmt
// RM_TEXELS_END

Dictionary RtaRemaster::derive_maps(const Ref<Image>& albedo, const Dictionary& options) const {
    Dictionary d;
    if (albedo.is_null() || albedo->is_empty()) return d;
    Ref<Image> img = albedo->duplicate();
    if (img->is_compressed()) img->decompress();
    if (img->has_mipmaps()) img->clear_mipmaps();
    img->convert(Image::FORMAT_RGBA8);
    const int w = img->get_width(), h = img->get_height();
    if (w < 2 || h < 2) return d;
    const PackedByteArray px = img->get_data();
    rmt::Settings st;
    st.scale = std::max(1.0f, (float)(double)options.get("scale", 1.0));
    const String force = options.get("class", "");
    for (int c = 0; c < rmt::NCLS; c++) if (force == String(rmt::NAMES[c])) st.forced = c;
    st.strands = String(options.get("strands", "hair")) == "fur" ? rmt::FUR : rmt::HAIR;
    st.stone = (bool)options.get("stone", false);
    st.grey_metal = (bool)options.get("grey_metal", true);
    st.gold = (bool)options.get("gold", true);
    st.skin_hue_lo = (float)(double)options.get("skin_hue_lo", -0.03);
    st.skin_hue_hi = (float)(double)options.get("skin_hue_hi", 0.105);
    st.skin_v_lo = (float)(double)options.get("skin_v_lo", 0.42);
    st.skin_s_hi = (float)(double)options.get("skin_s_hi", 0.7);
    // rules: ["fur 0.08 0.16 0.15 0.45 0.4 0.95", ...] (class, hue from-to, saturation from-to, value from-to)
    const Array rules = options.get("rules", Array());
    for (int64_t k = 0; k < rules.size(); k++) {
        const PackedStringArray w = String(rules[k]).split(" ", false);
        if (w.size() < 7) continue;
        rmt::Settings::Rule r{-1, (float)w[1].to_float(), (float)w[2].to_float(), (float)w[3].to_float(), (float)w[4].to_float(), (float)w[5].to_float(), (float)w[6].to_float()};
        for (int c = 0; c < rmt::NCLS; c++) if (w[0] == String(rmt::NAMES[c])) r.cls = c;
        if (r.cls >= 0) st.rules.push_back(r);
    }
    const String prefer = options.get("prefer", "");
    for (int c = 0; c < rmt::NCLS; c++) if (prefer == String(rmt::NAMES[c])) st.prefer = c;
    rmt::Texels t;
    rmt::analyse(px.ptr(), w, h, st, t);
    const size_t n = (size_t)w * h;
    PackedByteArray nb, ob, ab;
    nb.resize(n * 4);
    ob.resize(n * 4);
    ab.resize(n * 4);
    rmt::maps(t, (float)(double)options.get("strength", 1.6), st.scale, (float)(double)options.get("metal", 0.85), (float)(double)options.get("rough", 1.0),
              nb.ptrw(), ob.ptrw(), ab.ptrw());
    Ref<Image> ni = Image::create_from_data(w, h, false, Image::FORMAT_RGBA8, nb);
    Ref<Image> oi = Image::create_from_data(w, h, false, Image::FORMAT_RGBA8, ob);
    Ref<Image> ai = Image::create_from_data(w, h, false, Image::FORMAT_RGBA8, ab);
    ni->generate_mipmaps();
    oi->generate_mipmaps();
    ai->generate_mipmaps();
    d["normal"] = ni;
    d["orm"] = oi;
    d["aux"] = ai;
    if ((bool)options.get("class_picture", false)) {
        PackedByteArray cb;
        cb.resize(n * 3);
        rmt::class_picture(t, cb.ptrw());
        d["class_picture"] = Image::create_from_data(w, h, false, Image::FORMAT_RGB8, cb);
    }
    Dictionary shares;
    for (int c = 0; c < rmt::NCLS; c++) if (t.share[c] > 0.0) shares[rmt::NAMES[c]] = std::round(t.share[c] * 1000.0) / 1000.0;
    d["classes"] = shares;
    return d;
}

void RtaRemaster::_bind_methods() {
    ClassDB::bind_method(D_METHOD("scan", "machine"), &RtaRemaster::scan);
    ClassDB::bind_method(D_METHOD("bake_start", "machine", "object", "options"), &RtaRemaster::bake_start);
    ClassDB::bind_method(D_METHOD("bake_take", "key"), &RtaRemaster::bake_take);
    ClassDB::bind_method(D_METHOD("bakes_running"), &RtaRemaster::bakes_running);
    ClassDB::bind_method(D_METHOD("merge", "surfaces", "groups", "count"), &RtaRemaster::merge);
    ClassDB::bind_method(D_METHOD("pose", "machine", "skeleton", "rid"), &RtaRemaster::pose);
    ClassDB::bind_method(D_METHOD("skin_palette", "rid", "binds", "globals", "inverse_bind"), &RtaRemaster::skin_palette);
    ClassDB::bind_method(D_METHOD("tween", "rid", "t"), &RtaRemaster::tween);
    ClassDB::bind_method(D_METHOD("forget", "rid"), &RtaRemaster::forget);
    ClassDB::bind_method(D_METHOD("light_sh", "machine", "pieces"), &RtaRemaster::light_sh);
    ClassDB::bind_method(D_METHOD("derive_maps", "albedo", "options"), &RtaRemaster::derive_maps);
}
