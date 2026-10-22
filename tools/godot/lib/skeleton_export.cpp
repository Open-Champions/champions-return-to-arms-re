// skeleton_export.cpp - see skeleton_export.h.
#include "skeleton_export.h"

#include "rt.h"
#include "scene_tap.h"

#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <memory>
#include <mutex>

namespace skel {

namespace {

// docs/spec/animation.md 2.1, 2.2, 2.4, 2.5
const uint32_t POOL = 0x791EC0, POOL_COUNT = 100, BUFFER = 0x620;
const uint32_t G_DRAW_FRAME = 0x44FDD0;
const uint32_t RAM = 32u << 20;

struct Record {
    uint32_t buffer = 0, state = 0, clip = 0;
    int32_t count = 0;              // the buffer's joint count
    int32_t skeleton = 0;           // the clip's joint count (0: no structure found)
    uint8_t depth[64];
    int16_t bind[64][3];
    int16_t mats[64][12];           // per joint three quadwords (R0[c], R1[c], R2[c], t[c]), c = 0..2
    double inverse0[12];            // of joint 0's matrix (3 x 4, column vectors)
};
struct Batch {
    uint32_t number = 0;
    std::vector<Record> records;
};

std::mutex g_lock;
std::deque<std::shared_ptr<Batch>> g_batches;      // the last few draw passes'
uint32_t g_next = 1;
bool g_off = false;
// figures
std::atomic<uint64_t> g_passes{0}, g_recorded{0}, g_with_structure{0};
uint64_t g_built_frames = 0, g_skeletons = 0, g_objects = 0, g_matched = 0, g_unmatched = 0, g_no_batch = 0;
double g_worst = 0, g_sum = 0;

inline uint32_t rd32(const uint8_t* ram, uint32_t a) { uint32_t v; memcpy(&v, ram + (a & (RAM - 1)), 4); return v; }
inline int16_t rd16(const uint8_t* ram, uint32_t a) { int16_t v; memcpy(&v, ram + (a & (RAM - 1)), 2); return v; }
inline bool in_ram(uint32_t a, uint32_t size) { a &= 0x1FFFFFFF; return a >= 0x100000 && a + size <= RAM; }

// the pose buffer's joint j as 3 x 4 (column vectors): bind-pose model space -> posed model space
// (render-pipeline.md 4.7: qword c of joint j = (R0[c], R1[c], R2[c], t[c]); p'_c = sum_r R_r[c] p_r + t[c], so row c of
// the matrix is qword c)
void pose_matrix(const Record& r, int j, double* out) {
    for (int c = 0; c < 3; c++) {
        for (int k = 0; k < 3; k++) out[c * 4 + k] = r.mats[j][c * 4 + k] / 4096.0;
        out[c * 4 + 3] = r.mats[j][c * 4 + 3] / 64.0;
    }
}

bool invert34(const double* a, double* out) {
    double det = a[0] * (a[5] * a[10] - a[6] * a[9]) - a[1] * (a[4] * a[10] - a[6] * a[8]) + a[2] * (a[4] * a[9] - a[5] * a[8]);
    if (!(std::fabs(det) > 1e-9)) return false;
    double ri[9] = {(a[5] * a[10] - a[6] * a[9]) / det, (a[2] * a[9] - a[1] * a[10]) / det, (a[1] * a[6] - a[2] * a[5]) / det,
                    (a[6] * a[8] - a[4] * a[10]) / det, (a[0] * a[10] - a[2] * a[8]) / det, (a[2] * a[4] - a[0] * a[6]) / det,
                    (a[4] * a[9] - a[5] * a[8]) / det, (a[1] * a[8] - a[0] * a[9]) / det, (a[0] * a[5] - a[1] * a[4]) / det};
    for (int i = 0; i < 3; i++) {
        for (int c = 0; c < 3; c++) out[i * 4 + c] = ri[i * 3 + c];
        out[i * 4 + 3] = -(ri[i * 3] * a[3] + ri[i * 3 + 1] * a[7] + ri[i * 3 + 2] * a[11]);
    }
    return true;
}

void compose34(const double* a, const double* b, double* out) {        // out = a b
    for (int i = 0; i < 3; i++)
        for (int c = 0; c < 4; c++)
            out[i * 4 + c] = a[i * 4] * b[c] + a[i * 4 + 1] * b[4 + c] + a[i * 4 + 2] * b[8 + c] + (c == 3 ? a[i * 4 + 3] : 0.0);
}

const double DEPTH_SCALE = 1.0 / 1125899906842624.0;

// the program's joint matrix (object -> clip, rows as it holds them) taken back into the world: 3 x 4, column vectors
bool to_world(const float* m, const double* inverse, float* out) {
    double x[4][4];
    for (int r = 0; r < 4; r++)
        for (int a = 0; a < 4; a++) {
            double sum = 0;
            for (int c = 0; c < 4; c++) sum += (double)m[r * 4 + c] * (c == 2 ? DEPTH_SCALE : 1.0) * inverse[c * 4 + a];
            x[r][a] = sum;
        }
    const double h = x[3][3];
    if (!(std::fabs(h) > 1e-12)) return false;
    for (int a = 0; a < 3; a++) {
        for (int r = 0; r < 3; r++) out[a * 4 + r] = (float)(x[r][a] / h);
        out[a * 4 + 3] = (float)(x[3][a] / h);
    }
    return true;
}

inline void apply(const float* m, const double* p, double* out) {
    for (int a = 0; a < 3; a++) out[a] = m[a * 4] * p[0] + m[a * 4 + 1] * p[1] + m[a * 4 + 2] * p[2] + m[a * 4 + 3];
}

// How far skin[] is from (one object matrix) x the record's pose, in world units: the object matrix from joint 0, then
// every joint compared at its bind origin and 16 units along each axis from it.
double mismatch(const Record& r, const float (*skin)[12], double stop) {
    double s0[12], X[12];
    for (int k = 0; k < 12; k++) s0[k] = skin[0][k];
    compose34(s0, r.inverse0, X);
    double worst = 0;
    for (int j = 1; j < r.count; j++) {
        double pj[12], wj[12];
        pose_matrix(r, j, pj);
        compose34(X, pj, wj);
        double o[3] = {0, 0, 0};
        if (r.skeleton) for (int a = 0; a < 3; a++) o[a] = -r.bind[j][a] / 64.0;
        for (int t = 0; t < 4; t++) {
            double q[3] = {o[0], o[1], o[2]};
            if (t) q[t - 1] += 16.0;
            double b[3];
            apply(skin[j], q, b);
            for (int a = 0; a < 3; a++) {
                double w = wj[a * 4] * q[0] + wj[a * 4 + 1] * q[1] + wj[a * 4 + 2] * q[2] + wj[a * 4 + 3];
                worst = std::max(worst, std::fabs(w - b[a]));
            }
        }
        if (worst > stop) return worst;
    }
    return worst;
}

}  // namespace

void install() {
    g_off = getenv("RTA_SKEL") && atoi(getenv("RTA_SKEL")) == 0;
}

// The game's thread, when a draw pass has returned: the pose buffers it drew are the ones stamped with this g_drawFrame
// (anim_emitPose stamps every buffer it hands to the draw list; animation.md 8.2).
uint32_t drawn(const uint8_t* ram) {
    if (!ram || g_off) return 0;
    auto batch = std::make_shared<Batch>();
    const uint32_t frame = rd32(ram, G_DRAW_FRAME);
    for (uint32_t i = 0; i < POOL_COUNT; i++) {
        const uint32_t buffer = POOL + i * BUFFER;
        if (rd32(ram, buffer + 0x61C) != frame) continue;
        Record r;
        r.buffer = buffer;
        r.count = rd16(ram, buffer + 8);
        if (r.count < 1 || r.count > 64) continue;
        for (int j = 0; j < r.count; j++)
            for (int k = 0; k < 12; k++) r.mats[j][k] = rd16(ram, buffer + 0x10 + j * 24 + k * 2);
        double p0[12];
        pose_matrix(r, 0, p0);
        if (!invert34(p0, r.inverse0)) continue;
        r.state = rd32(ram, buffer + 0x610);
        if (r.state && in_ram(r.state, 0x108)) {
            const int tracks = (int8_t)ram[(r.state & 0x1FFFFFF) + 4];
            if (tracks >= 1 && tracks <= 8) {
                r.clip = rd32(ram, r.state + 8 + (tracks - 1) * 0x20);       // the top track's clip: its skeleton is the pose's (8.1 step 7)
                if (in_ram(r.clip, 0x50)) {
                    const int32_t joints = (int32_t)rd32(ram, r.clip);
                    const uint32_t bind = rd32(ram, r.clip + 0x0C), depth = rd32(ram, r.clip + 0x10);
                    if (joints >= r.count && joints <= 64 && in_ram(bind, joints * 8) && in_ram(depth, joints)) {
                        r.skeleton = joints;
                        for (int j = 0; j < joints; j++) {
                            r.depth[j] = ram[(depth & 0x1FFFFFF) + j];
                            for (int k = 0; k < 3; k++) r.bind[j][k] = rd16(ram, bind + j * 8 + k * 2);
                        }
                        g_with_structure++;
                    }
                }
            }
        }
        batch->records.push_back(r);
    }
    g_passes++;
    g_recorded += batch->records.size();
    std::lock_guard<std::mutex> hold(g_lock);
    batch->number = g_next++;
    if (!g_next) g_next = 1;
    g_batches.push_back(batch);
    while (g_batches.size() > 16) g_batches.pop_front();
    return batch->number;
}

void build(const render::TapFrame& tap, const std::vector<uint8_t>& kept, Frame& out) {
    out.clear();
    g_built_frames++;
    if (!tap.have_camera) return;
    std::shared_ptr<Batch> batch;
    {
        std::lock_guard<std::mutex> hold(g_lock);
        for (auto& b : g_batches) if (b->number == tap.batch) batch = b;
    }
    if (!batch && tap.batch) g_no_batch++;
    out.sources.resize(tap.sources.size());
    static_assert(sizeof(rtag_skin_source) == sizeof(render::TapSource), "rtag_skin_source is render::TapSource");
    if (!tap.sources.empty()) memcpy(out.sources.data(), tap.sources.data(), tap.sources.size() * sizeof(render::TapSource));
    out.full_source = tap.full_source;
    uint32_t last_object = ~0u, last_joints = ~0u;
    int last_skeleton = -1;
    for (size_t k = 0; k < tap.pieces.size(); k++) {
        if (k < kept.size() && !kept[k]) continue;
        const render::TapPiece& p = tap.pieces[k];
        rtag_skin_piece sp;
        memset(&sp, 0, sizeof sp);
        sp.skeleton = -1;
        sp.source_first = p.source_first;
        sp.source_count = p.source_count;
        const bool model = p.kind == render::TAP_MODEL;
        const size_t room = (size_t)(p.joints + (model ? 64 : 1)) * 16;
        if (room <= tap.joints.size()) to_world(&tap.joints[(size_t)p.joints * 16], tap.clip_to_world, sp.slot0);
        if (model && batch && room <= tap.joints.size()) {
            if (p.object == last_object && p.joints == last_joints) sp.skeleton = last_skeleton;
            else {
                last_object = p.object; last_joints = p.joints; last_skeleton = -1;
                g_objects++;
                rtag_skeleton s;
                memset(&s, 0, sizeof s);
                s.object = p.object;
                bool ok = to_world(&tap.joints[(size_t)p.joints * 16], tap.clip_to_world, s.skin[0]);
                // matrices past the pose's joint count are left-overs or zeros (animation.md 8.1 step 8)
                for (int j = 1; j < 64 && ok; j++)
                    if (!to_world(&tap.joints[(size_t)(p.joints + j) * 16], tap.clip_to_world, s.skin[j])) memset(s.skin[j], 0, sizeof s.skin[j]);
                // which of the poses this draw pass drew: the one that, through a single object matrix, is these joint
                // matrices (the object's own scale is in that matrix)
                int best = -1;
                double best_error = 0.05;
                for (size_t i = 0; ok && i < batch->records.size(); i++) {
                    if (batch->records[i].count < 2) continue;
                    double e = mismatch(batch->records[i], s.skin, best_error);
                    if (e < best_error) { best_error = e; best = (int)i; }
                }
                if (best >= 0) {
                    const Record& r = batch->records[best];
                    s.pose = (uint32_t)best + 1;
                    s.state = r.state; s.clip = r.clip; s.buffer = r.buffer;
                    s.pose_error = (float)best_error;
                    g_sum += best_error; if (best_error > g_worst) g_worst = best_error;
                    if (r.skeleton) {
                        s.joint_count = r.count;
                        int last_at_depth[66];
                        for (int d = 0; d < 66; d++) last_at_depth[d] = -1;
                        for (int j = 0; j < r.count; j++) {
                            const int d = r.depth[j];
                            s.depth[j] = (uint8_t)d;
                            // joint j composes with stack level d (written by the last joint of depth d - 1) and writes level d + 1
                            s.parent[j] = (int8_t)(d >= 1 && d <= 64 ? last_at_depth[d - 1] : -1);
                            if (d < 65) last_at_depth[d] = j;
                            for (int a = 0; a < 3; a++) s.bind[j][a] = -r.bind[j][a] / 64.0f;
                        }
                    }
                    for (int j = 0; j < 64; j++) {
                        memcpy(s.joint[j], s.skin[j], sizeof s.joint[j]);
                        if (j < s.joint_count) {
                            double o[3] = {s.bind[j][0], s.bind[j][1], s.bind[j][2]}, w[3];
                            apply(s.skin[j], o, w);
                            for (int a = 0; a < 3; a++) s.joint[j][a * 4 + 3] = (float)w[a];
                        }
                    }
                    s.scale = std::sqrt(s.skin[0][0] * s.skin[0][0] + s.skin[0][4] * s.skin[0][4] + s.skin[0][8] * s.skin[0][8]);
                    last_skeleton = (int)out.skeletons.size();
                    out.skeletons.push_back(s);
                    out.poses_matched++;
                    g_matched++; g_skeletons++;
                    sp.skeleton = last_skeleton;
                } else {
                    g_unmatched++;
                }
            }
        }
        out.pieces.push_back(sp);
    }
    out.poses_seen = batch ? (uint32_t)batch->records.size() : 0;
}

void fill(const Frame& f, rtag_skeletons& out) {
    const uint32_t size = out.struct_size;
    memset(&out, 0, sizeof out);
    out.struct_size = size;
    out.skeleton_count = (uint32_t)f.skeletons.size();
    out.piece_count = (uint32_t)f.pieces.size();
    out.source_count = (uint32_t)f.sources.size();
    out.full_count = (uint32_t)f.full_source.size();
    out.skeletons = f.skeletons.data();
    out.pieces = f.pieces.data();
    out.sources = f.sources.data();
    out.full_source = f.full_source.data();
    out.poses_seen = f.poses_seen;
    out.poses_matched = f.poses_matched;
}

void report() {
    printf("rtag: skeletons: %llu draw passes, %llu poses drawn in them (%llu with the clip's skeleton); %llu frames built, %llu model objects: %llu tied to one of "
           "their pass's poses (through one object matrix: mean %.5f, largest %.5f world units), %llu not (rigid models, the default pose); %llu frames whose pass "
           "was not found\n",
           (unsigned long long)g_passes.load(), (unsigned long long)g_recorded.load(), (unsigned long long)g_with_structure.load(), (unsigned long long)g_built_frames,
           (unsigned long long)g_objects, (unsigned long long)g_matched, g_matched ? g_sum / g_matched : 0.0, g_worst, (unsigned long long)g_unmatched,
           (unsigned long long)g_no_batch);
}

}  // namespace skel
