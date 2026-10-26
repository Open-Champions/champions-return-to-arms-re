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
#include <godot_cpp/variant/transform3d.hpp>
#include <godot_cpp/variant/vector2.hpp>
#include <godot_cpp/variant/vector3.hpp>

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
    uint64_t key = 0;
    uint32_t corners = 0;
};

uint64_t piece_hash(const rtag_skeletons& k, const rtag_scene& sc, uint32_t i, uint32_t& corners) {
    const rtag_skin_piece& p = k.pieces[i];
    const rtag_scene_piece& q = sc.pieces[i];
    uint64_t h = FNV0;
    if (p.source_first + p.source_count <= k.source_count) h = fnv(h, k.sources + p.source_first, sizeof(rtag_skin_source) * p.source_count);
    const uint32_t full = std::min(k.full_count, sc.full_count);
    corners = 0;
    for (uint32_t c = q.full_first; c < q.full_first + q.full_count && c < full; c++) {
        h = fnv(h, &k.full_source[c], 2);
        h = fnv(h, &sc.full[c].u, 4);
        h = fnv(h, &sc.full[c].v, 4);
        corners++;
    }
    return h;
}

// the figures of the frame: per object, its skinned packets (an object posed by two skeletons is left to the game)
void groups(const rtag_skeletons& k, const rtag_scene& sc, std::vector<Group>& out, std::vector<Group>* rejected = nullptr) {
    std::map<uint32_t, Group> by;
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
        uint64_t key = FNV0;
        for (auto& o : order) { g.pieces.push_back(o.second); g.hashes.push_back(o.first); key = fnv(key, &o.first, 8); }
        g.key = key;
        out.push_back(std::move(g));
    }
}

Transform3D rows34(const float* m) {
    return Transform3D(Basis(m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10]), Vector3(m[3], m[7], m[11]));
}

// ---- subdivision ------------------------------------------------------------------------------------------------------
struct Skin { int j[4]; float w[4]; };
struct Tri { int v[3]; Vector2 uv[3]; Vector3 rn[3]; int piece; };
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
        for (int c = 0; c < 3; c++) {
            const int d = (c + 1) % 3;
            m[c] = nv + eid[ekey(t.v[c], t.v[d])];
            muv[c] = (t.uv[c] + t.uv[d]) * 0.5f;
            Vector3 s = t.rn[c] + t.rn[d];
            mrn[c] = s.length_squared() > 1e-12f ? s.normalized() : t.rn[c];
        }
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

}  // namespace

struct RtaRemaster::Job {
    struct Piece { std::vector<rtag_skin_source> sources; std::vector<std::array<float, 3>> corners; /* source, u, v */ };
    std::vector<Piece> pieces;
    std::vector<std::string> piece_keys;
    int levels = 2, fit = 4, max_tris = 80000;
    float crease = 0.5f, keep = 0.8f;
    std::atomic<bool> done{false};
    std::string failed, stats;
    std::vector<OutLevel> out;
    bool taken = false;

    void run() {
        const auto t0 = std::chrono::steady_clock::now();
        // weld by position (a packet seam is one edge of the surface)
        std::map<std::array<int, 3>, int> weld;
        std::vector<Vector3> p0;
        std::vector<Skin> s0;
        std::vector<Tri> tris;
        size_t dropped = 0;
        for (size_t pi = 0; pi < pieces.size(); pi++) {
            const Piece& pc = pieces[pi];
            std::vector<int> id(pc.sources.size());
            for (size_t v = 0; v < pc.sources.size(); v++) {
                const rtag_skin_source& s = pc.sources[v];
                std::array<int, 3> q{(int)std::lround(s.position[0] * 1000.0f), (int)std::lround(s.position[1] * 1000.0f), (int)std::lround(s.position[2] * 1000.0f)};
                auto it = weld.find(q);
                if (it != weld.end()) { id[v] = it->second; continue; }
                id[v] = (int)p0.size();
                weld[q] = id[v];
                p0.push_back(Vector3(s.position[0], s.position[1], s.position[2]));
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
        // the same triangle twice (a packet's strip and its neighbour's) once
        {
            std::unordered_set<std::string> once;
            std::vector<Tri> kept;
            for (const Tri& t : tris) {
                int s[3] = {t.v[0], t.v[1], t.v[2]};
                std::sort(s, s + 3);
                std::string k((const char*)s, sizeof s);
                if (once.insert(k).second) kept.push_back(t); else dropped++;
            }
            tris.swap(kept);
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
            std::vector<Skin> s = apply_skin(lv, l, s0);
            out.push_back(emit(tris_at[l], p, s, (int)pieces.size(), crease));
            char b[96];
            snprintf(b, sizeof b, " L%d %zu tris (fit: %.3f off at most)", l, out.back().triangles, after);
            fit_text += b;
        }
        const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        char b[256];
        snprintf(b, sizeof b, "%zu packets, %zu vertices welded, %zu triangles (%zu dropped), %zu crease edges;%s; %.0f ms", pieces.size(), p0.size(),
                 tris.size(), dropped, creases, fit_text.c_str(), ms);
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
        for (size_t i = 0; i < g.pieces.size(); i++) { pieces.push_back((int32_t)g.pieces[i]); keys.push_back(String(hex(g.hashes[i]).c_str())); }
        e["pieces"] = pieces;
        e["piece_keys"] = keys;
        e["root"] = Vector3(s.joint[0][3], s.joint[0][7], s.joint[0][11]);
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

// ---- maps ---------------------------------------------------------------------------------------------------------------
namespace {

void box_blur(std::vector<float>& a, int w, int h, int r) {
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

enum Cls { SKIN = 0, LEATHER = 1, METAL = 2, CLOTH = 3 };
const char* CLS_NAMES[4] = {"skin", "leather", "metal", "cloth"};

}  // namespace

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
    const uint8_t* src = px.ptr();
    const float strength = (float)(double)options.get("strength", 1.6);
    const float scale = std::max(1.0f, (float)(double)options.get("scale", 1.0));
    const String force = options.get("class", "");
    const float metal_amt = (float)(double)options.get("metal", 0.85);
    const float rough_mul = (float)(double)options.get("rough", 1.0);
    const size_t n = (size_t)w * h;
    std::vector<float> lum(n), hue(n), sat(n), val(n);
    for (size_t i = 0; i < n; i++) {
        const float r = src[i * 4] / 255.0f, g = src[i * 4 + 1] / 255.0f, b = src[i * 4 + 2] / 255.0f;
        lum[i] = 0.299f * r + 0.587f * g + 0.114f * b;
        const float mx = std::max(r, std::max(g, b)), mn = std::min(r, std::min(g, b)), c = mx - mn;
        val[i] = mx;
        sat[i] = mx > 1e-4f ? c / mx : 0.0f;
        float hh = 0.0f;
        if (c > 1e-4f) {
            if (mx == r) hh = std::fmod((g - b) / c + 6.0f, 6.0f);
            else if (mx == g) hh = (b - r) / c + 2.0f;
            else hh = (r - g) / c + 4.0f;
        }
        hue[i] = hh / 6.0f;
    }
    // edge-aware: a bilateral filter of the luminance (a painted edge stays, the noise of the upscale goes)
    const int R = std::max(1, (int)std::lround(scale * 0.6f));
    std::vector<float> lb(n);
    {
        const float ss = 2.0f * (R * 0.75f) * (R * 0.75f), sr = 2.0f * 0.1f * 0.1f;
        for (int y = 0; y < h; y++)
            for (int x = 0; x < w; x++) {
                const float c = lum[y * w + x];
                float s = 0, ws = 0;
                for (int dy = -R; dy <= R; dy++) {
                    const int yy = std::clamp(y + dy, 0, h - 1);
                    for (int dx = -R; dx <= R; dx++) {
                        const int xx = std::clamp(x + dx, 0, w - 1);
                        const float v = lum[yy * w + xx], dv = v - c;
                        const float k = std::exp(-(dx * dx + dy * dy) / ss - dv * dv / sr);
                        s += v * k;
                        ws += k;
                    }
                }
                lb[y * w + x] = s / ws;
            }
    }
    // the broad shading painted into the texture taken off: what is left is the relief
    std::vector<float> broad = lb;
    box_blur(broad, w, h, std::max(2, (int)std::lround(scale * 3.0f)));
    std::vector<float> height(n);
    for (size_t i = 0; i < n; i++) height[i] = lb[i] - 0.75f * broad[i];
    // local contrast (metal: worn, bright edges; cloth: even)
    std::vector<float> contrast(n);
    {
        std::vector<float> m = lum;
        box_blur(m, w, h, std::max(1, (int)std::lround(scale)));
        for (size_t i = 0; i < n; i++) contrast[i] = std::fabs(lum[i] - m[i]);
        box_blur(contrast, w, h, std::max(1, (int)std::lround(scale * 1.5f)));
    }
    // classes per texel, then the majority round each
    int forced = -1;
    for (int c = 0; c < 4; c++) if (force == String(CLS_NAMES[c])) forced = c;
    std::vector<float> share[4];
    for (int c = 0; c < 4; c++) share[c].assign(n, 0.0f);
    for (size_t i = 0; i < n; i++) {
        int c = CLOTH;
        const float hh = hue[i], s = sat[i], v = val[i], k = contrast[i];
        const bool warm = hh < 0.115f || hh > 0.97f;
        if (forced >= 0) c = forced;
        else if ((s < 0.17f && v > 0.38f && k > 0.035f) || (hh > 0.105f && hh < 0.17f && s > 0.5f && v > 0.62f && k > 0.04f)) c = METAL;
        else if (warm && s > 0.16f && s < 0.62f && v > 0.34f) c = SKIN;
        else if (hh > 0.02f && hh < 0.15f && s > 0.3f && v > 0.06f && v <= 0.42f) c = LEATHER;
        share[c][i] = 1.0f;
    }
    double counts[4] = {0, 0, 0, 0};
    std::vector<uint8_t> cls(n);
    for (int c = 0; c < 4; c++) box_blur(share[c], w, h, std::max(1, (int)std::lround(scale)));
    for (size_t i = 0; i < n; i++) {
        int best = 0;
        for (int c = 1; c < 4; c++) if (share[c][i] > share[best][i]) best = c;
        cls[i] = (uint8_t)best;
        counts[best] += 1;
    }
    // normal map from the height (Sobel); green up the picture (-v)
    PackedByteArray nb, ob;
    nb.resize(n * 3);
    ob.resize(n * 3);
    uint8_t* np = nb.ptrw();
    uint8_t* op = ob.ptrw();
    const float bump = strength * scale;
    static const float CLS_ROUGH[4] = {0.55f, 0.62f, 0.34f, 0.86f};
    static const float CLS_BUMP[4] = {0.45f, 0.9f, 0.7f, 1.0f};
    for (int y = 0; y < h; y++)
        for (int x = 0; x < w; x++) {
            auto H = [&](int xx, int yy) { return height[std::clamp(yy, 0, h - 1) * w + std::clamp(xx, 0, w - 1)]; };
            const float gx = (H(x + 1, y - 1) + 2 * H(x + 1, y) + H(x + 1, y + 1) - H(x - 1, y - 1) - 2 * H(x - 1, y) - H(x - 1, y + 1)) / 8.0f;
            const float gy = (H(x - 1, y + 1) + 2 * H(x, y + 1) + H(x + 1, y + 1) - H(x - 1, y - 1) - 2 * H(x, y - 1) - H(x + 1, y - 1)) / 8.0f;
            const size_t i = (size_t)y * w + x;
            const float b = bump * CLS_BUMP[cls[i]];
            Vector3 nv(-gx * b, gy * b, 1.0f);      // +v is down the picture: up (green) is -v, so the slope along up is -gy
            nv.normalize();
            np[i * 3] = (uint8_t)std::clamp((int)std::lround((nv.x * 0.5f + 0.5f) * 255.0f), 0, 255);
            np[i * 3 + 1] = (uint8_t)std::clamp((int)std::lround((nv.y * 0.5f + 0.5f) * 255.0f), 0, 255);
            np[i * 3 + 2] = (uint8_t)std::clamp((int)std::lround((nv.z * 0.5f + 0.5f) * 255.0f), 0, 255);
            // ORM: a cavity where the relief is below its surroundings; roughness by class (worn spots rougher); metal
            const float cav = std::clamp(1.0f - std::max(0.0f, broad[i] * 0.25f - height[i]) * 3.0f, 0.55f, 1.0f);
            float rough = CLS_ROUGH[cls[i]] + (0.5f - lb[i]) * 0.12f + contrast[i] * 0.4f;
            if (cls[i] == METAL) rough += (1.0f - val[i]) * 0.25f;
            rough = std::clamp(rough * rough_mul, 0.12f, 1.0f);
            const float metal = cls[i] == METAL ? metal_amt * std::clamp(0.5f + val[i] * 0.6f, 0.0f, 1.0f) : 0.0f;
            op[i * 3] = (uint8_t)std::lround(cav * 255.0f);
            op[i * 3 + 1] = (uint8_t)std::lround(rough * 255.0f);
            op[i * 3 + 2] = (uint8_t)std::lround(std::clamp(metal, 0.0f, 1.0f) * 255.0f);
        }
    Ref<Image> ni = Image::create_from_data(w, h, false, Image::FORMAT_RGB8, nb);
    Ref<Image> oi = Image::create_from_data(w, h, false, Image::FORMAT_RGB8, ob);
    ni->generate_mipmaps();
    oi->generate_mipmaps();
    d["normal"] = ni;
    d["orm"] = oi;
    Dictionary shares;
    for (int c = 0; c < 4; c++) shares[CLS_NAMES[c]] = counts[c] / (double)n;
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
    ClassDB::bind_method(D_METHOD("tween", "rid", "t"), &RtaRemaster::tween);
    ClassDB::bind_method(D_METHOD("forget", "rid"), &RtaRemaster::forget);
    ClassDB::bind_method(D_METHOD("derive_maps", "albedo", "options"), &RtaRemaster::derive_maps);
}
