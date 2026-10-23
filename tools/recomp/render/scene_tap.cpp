// scene_tap.cpp - see scene_tap.h.
//
// What is read where (docs/formats/model-texture.md, "Packet layout"; N = ITOP, `in` = the
// half of the double buffer the packet was unpacked into, both as the MSCAL left them):
//   in + 0      N positions      signed 16 bit as integers (level: the caller's STROW added)
//   in + N      N normals        signed 8 bit
//   in + 2N     N + 2 slot rows  (a, src, dst): where a vertex goes in the strip, and one copy
//   in + 3N + 2 weight entries   (j1, w1, j2, w2), models only; then
//               (c, 0, 0, 0) and c copy rows (s1, d1, s2, d2)
//   the strip   the GIF tag at the kicked quadword, nloop vertices of nreg quadwords after it;
//               the last quadword of a vertex is its position, bit 15 of its fourth word "do not draw"
#include "scene_tap.h"
#include "xxh3_64.h"
#include <chrono>
#ifdef __APPLE__
#include <pthread/qos.h>
#endif

#include "renderer.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>

namespace render {

namespace {

const double DEPTH_SCALE = 1.0 / 1125899906842624.0;        // 2^-50: the programs' depth terms carry 2^50

inline uint64_t fnv(const uint8_t* bytes, size_t count, uint64_t h) {
    for (size_t k = 0; k < count; k++) { h ^= bytes[k]; h *= 0x100000001B3ull; }
    return h;
}

bool invert4(const double* m, double* out) {
    double inv[16];
    inv[0] = m[5] * m[10] * m[15] - m[5] * m[11] * m[14] - m[9] * m[6] * m[15] + m[9] * m[7] * m[14] + m[13] * m[6] * m[11] - m[13] * m[7] * m[10];
    inv[4] = -m[4] * m[10] * m[15] + m[4] * m[11] * m[14] + m[8] * m[6] * m[15] - m[8] * m[7] * m[14] - m[12] * m[6] * m[11] + m[12] * m[7] * m[10];
    inv[8] = m[4] * m[9] * m[15] - m[4] * m[11] * m[13] - m[8] * m[5] * m[15] + m[8] * m[7] * m[13] + m[12] * m[5] * m[11] - m[12] * m[7] * m[9];
    inv[12] = -m[4] * m[9] * m[14] + m[4] * m[10] * m[13] + m[8] * m[5] * m[14] - m[8] * m[6] * m[13] - m[12] * m[5] * m[10] + m[12] * m[6] * m[9];
    inv[1] = -m[1] * m[10] * m[15] + m[1] * m[11] * m[14] + m[9] * m[2] * m[15] - m[9] * m[3] * m[14] - m[13] * m[2] * m[11] + m[13] * m[3] * m[10];
    inv[5] = m[0] * m[10] * m[15] - m[0] * m[11] * m[14] - m[8] * m[2] * m[15] + m[8] * m[3] * m[14] + m[12] * m[2] * m[11] - m[12] * m[3] * m[10];
    inv[9] = -m[0] * m[9] * m[15] + m[0] * m[11] * m[13] + m[8] * m[1] * m[15] - m[8] * m[3] * m[13] - m[12] * m[1] * m[11] + m[12] * m[3] * m[9];
    inv[13] = m[0] * m[9] * m[14] - m[0] * m[10] * m[13] - m[8] * m[1] * m[14] + m[8] * m[2] * m[13] + m[12] * m[1] * m[10] - m[12] * m[2] * m[9];
    inv[2] = m[1] * m[6] * m[15] - m[1] * m[7] * m[14] - m[5] * m[2] * m[15] + m[5] * m[3] * m[14] + m[13] * m[2] * m[7] - m[13] * m[3] * m[6];
    inv[6] = -m[0] * m[6] * m[15] + m[0] * m[7] * m[14] + m[4] * m[2] * m[15] - m[4] * m[3] * m[14] - m[12] * m[2] * m[7] + m[12] * m[3] * m[6];
    inv[10] = m[0] * m[5] * m[15] - m[0] * m[7] * m[13] - m[4] * m[1] * m[15] + m[4] * m[3] * m[13] + m[12] * m[1] * m[7] - m[12] * m[3] * m[5];
    inv[14] = -m[0] * m[5] * m[14] + m[0] * m[6] * m[13] + m[4] * m[1] * m[14] - m[4] * m[2] * m[13] - m[12] * m[1] * m[6] + m[12] * m[2] * m[5];
    inv[3] = -m[1] * m[6] * m[11] + m[1] * m[7] * m[10] + m[5] * m[2] * m[11] - m[5] * m[3] * m[10] - m[9] * m[2] * m[7] + m[9] * m[3] * m[6];
    inv[7] = m[0] * m[6] * m[11] - m[0] * m[7] * m[10] - m[4] * m[2] * m[11] + m[4] * m[3] * m[10] + m[8] * m[2] * m[7] - m[8] * m[3] * m[6];
    inv[11] = -m[0] * m[5] * m[11] + m[0] * m[7] * m[9] + m[4] * m[1] * m[11] - m[4] * m[3] * m[9] - m[8] * m[1] * m[7] + m[8] * m[3] * m[5];
    inv[15] = m[0] * m[5] * m[10] - m[0] * m[6] * m[9] - m[4] * m[1] * m[10] + m[4] * m[2] * m[9] + m[8] * m[1] * m[6] - m[8] * m[2] * m[5];
    double det = m[0] * inv[0] + m[1] * inv[4] + m[2] * inv[8] + m[3] * inv[12];
    if (!(std::fabs(det) > 1e-300)) return false;
    for (int k = 0; k < 16; k++) out[k] = inv[k] / det;
    return true;
}

}  // namespace

void SceneTap::install(Renderer& renderer) {
    r = &renderer;
    if (const char* e = getenv("RTA_TAP_ASYNC")) async = atoi(e) != 0;
    renderer.vif.vu.user = this;
    renderer.vif.vu.kick = kick;
    renderer.vif.tap_user = this;
    renderer.vif.on_program = [](void* user, int entry) { ((SceneTap*)user)->program(entry); };
    renderer.vif.on_note = [](void* user, uint32_t num, uint32_t imm) { ((SceneTap*)user)->note(num, imm); };
}

void SceneTap::camera_notes(const uint32_t* words, size_t count, std::vector<uint32_t>& codes) {
    codes.push_back(0x00A80000u | (uint32_t)(count & 0xFFFF));           // NOP, NUM 0xA8: so many words follow
    for (size_t k = 0; k < count; k++) {
        codes.push_back(0x00A90000u | (words[k] & 0xFFFF));
        codes.push_back(0x00A90000u | (words[k] >> 16));
    }
}

void SceneTap::note(uint32_t num, uint32_t imm) {
    if (num == 0xA8) { note_words.clear(); note_expect = imm & 0xFFFF; note_half = 0; return; }
    if (num != 0xA9 || note_words.size() >= note_expect) return;
    if (!note_half) { note_low = imm & 0xFFFF; note_half = 1; return; }
    note_half = 0;
    note_words.push_back(note_low | (imm & 0xFFFF) << 16);
    if (note_words.size() == note_expect) camera(note_words.data(), note_words.size());
}

void SceneTap::camera(const uint32_t* words, size_t count) {
    if (count < CAMERA_WORDS) return;
    {   // the decoder's own view of it (program()'s figures), as apply_camera() will make it
        float f[CAMERA_WORDS];
        memcpy(f, words, sizeof f);
        double vp[16], vpw[16], a[16], b[16];
        for (int k = 0; k < 16; k++) { vp[k] = k % 4 == 2 ? f[46 + k] * DEPTH_SCALE : f[46 + k]; vpw[k] = k % 4 == 2 ? f[30 + k] * DEPTH_SCALE : f[30 + k]; }
        memcpy(dec_camera_world, f + 30, sizeof dec_camera_world);
        dec_have_camera = invert4(vp, a) && invert4(vpw, b);
    }
    if (!async) { apply_camera(words, count); return; }
    // into the worker's queue after the kicks so far (the frame's camera: the kicks before it are made with the one before)
    Job job;
    memset(&job, 0, sizeof job);
    job.kind = JOB_CAMERA;
    job.own = buffer();
    job.vu = job.own;
    job.qword = (uint32_t)std::min<size_t>(count, 0x4000 / 4);
    memcpy(job.own, words, (size_t)job.qword * 4);
    pending.push_back(job);
}

void SceneTap::apply_camera(const uint32_t* words, size_t count) {
    float f[CAMERA_WORDS];
    memcpy(f, words, sizeof f);
    frame.proj_scale = f[0];
    frame.near_plane = frame.far_plane = 0;
    if (count >= CAMERA_WORDS + 2) { memcpy(&frame.near_plane, words + CAMERA_WORDS, 4); memcpy(&frame.far_plane, words + CAMERA_WORDS + 1, 4); }
    memcpy(frame.world_to_view, f + 2, sizeof frame.world_to_view);
    // g_viewProjModel (words 46..61): world -> clip, rows as the programs hold them
    double vp[16];
    for (int row = 0; row < 4; row++)
        for (int col = 0; col < 4; col++) {
            double v = f[46 + row * 4 + col];
            if (col == 2) v *= DEPTH_SCALE;
            vp[row * 4 + col] = v;
            frame.view_projection[row * 4 + col] = (float)v;
        }
    // g_viewProjWorld (words 30..45): the same for the level, whose vertices are in world / 4
    double vpw[16];
    memcpy(camera_world, f + 30, sizeof camera_world);
    for (int k = 0; k < 16; k++) vpw[k] = k % 4 == 2 ? f[30 + k] * DEPTH_SCALE : f[30 + k];
    frame.have_camera = invert4(vp, inverse) && invert4(vpw, inverse_world);
    memcpy(frame.clip_to_world, inverse, sizeof frame.clip_to_world);
    frame.batch = count >= CAMERA_WORDS + 3 ? words[CAMERA_WORDS + 2] : 0;
    stats.camera_blocks++;
}

void SceneTap::program(int entry) {
    if (!r) return;
    const Vu1& vu = r->vif.vu;
    auto Q = [&](uint32_t q) { return (const float*)(vu.data + (q & 0x3FF) * 16); };
    if (entry == 0x16 || entry == 0x02) {       // level chunk / model: the four rows of the transform were just unpacked
        for (int row = 0; row < 4; row++) memcpy(rows + row * 4, Q(vu.top + row), 16);
        have_rows = true;
        mirrored = false;
        clip_flag = vu.itop != 0;
        rows_kind = entry == 0x16 ? TAP_LEVEL : TAP_MODEL;
        object++;
        joint_epoch++;
        if (entry == 0x16) {
            // the depth row and the translation row of a chunk are the camera's own (its turn is in rows 0 and 1):
            // if they are, the camera block that came with the frame is the one these packets were made with
            stats.level_setups++;
            if (dec_have_camera && !memcmp(rows + 8, dec_camera_world + 8, 32)) stats.level_rows_equal++;
        }
    } else if (entry == 0x3c) {                 // the chunk again, mirrored in z
        for (int k = 8; k < 12; k++) rows[k] = -rows[k];
        mirrored = true;
        object++;
    } else if (entry == 0x0c || entry == 0x1e || entry == 0x1a) {
        joint_epoch++;                          // the joint matrices are made again
    }
}

double g_tap_kick_ms = 0, g_tap_ms = 0;        // decoder thread: in the GS model's xgkick, and in the tap (figures)
double g_tap_copy_ms = 0, g_tap_worker_ms = 0; // async: the decoder's copies for the worker, and the worker's own time (figures)

static inline double tap_now_ms() { return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count(); }

SceneTap::~SceneTap() {
    if (worker.joinable()) {
        { std::lock_guard<std::mutex> g(lock); stop = true; }
        wake.notify_all();
        worker.join();
    }
    for (uint8_t* b : spare) delete[] b;
    for (uint8_t* b : mine) delete[] b;
    for (const Job& j : pending) delete[] j.own;
    for (const Job& j : queue) delete[] j.own;
}

void SceneTap::drain() {
    hand_over();
    if (!worker.joinable()) return;
    std::unique_lock<std::mutex> g(lock);
    done.wait(g, [&] { return queue.empty() && !busy; });
}

void SceneTap::work() {
#ifdef __APPLE__
    pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);     // a picture passes through here: as the decoder's thread
#endif
    std::deque<Job> jobs;
    std::vector<uint8_t*> used;
    double cut_ms = 0;
    for (;;) {
        {
            std::unique_lock<std::mutex> g(lock);
            for (uint8_t* b : used) spare.push_back(b);
            used.clear();
            if (queue.empty()) { busy = false; done.notify_all(); }
            wake.wait(g, [&] { return stop || !queue.empty(); });
            if (queue.empty()) return;
            std::swap(jobs, queue);
            busy = true;
        }
        const double t0 = tap_now_ms();
        for (const Job& job : jobs) {
            if (job.kind == JOB_KICK) kicked(job);
            else if (job.kind == JOB_CAMERA) apply_camera((const uint32_t*)job.own, job.qword);
            else {
                std::function<void(TapFrame&)> then;
                { std::lock_guard<std::mutex> g(lock); then = std::move(cuts.front()); cuts.pop_front(); }
                take_now(cut_frame);
                const double t1 = tap_now_ms();
                then(cut_frame);
                cut_ms += tap_now_ms() - t1;        // (what the cut's receiver does is its own: left out of g_tap_ms)
                continue;
            }
            if (job.own) used.push_back(job.own);
        }
        jobs.clear();
        g_tap_ms += tap_now_ms() - t0 - cut_ms;
        g_tap_worker_ms += tap_now_ms() - t0 - cut_ms;
        cut_ms = 0;
    }
}

void SceneTap::kick(void* user, uint32_t qword) {
    SceneTap* tap = (SceneTap*)user;
    Renderer* r = tap->r;
    size_t before = r->gs.frame.vertices.size();
    // (the clock is read for one kick in eight, and that counted eight times: reading it was 5 % of the decoder's thread)
    const bool timed = !tap->async || (++tap->kick_count & 7) == 0;
    const double t0 = timed ? tap_now_ms() : 0;
    r->gs.xgkick(r->vif.vu.data, qword);
    const double t1 = timed ? tap_now_ms() : 0;
    const size_t after = r->gs.frame.vertices.size();
    const int entry = r->gs.debug_entry;
    if (timed) g_tap_kick_ms += (t1 - t0) * (tap->async ? 8 : 1);
    if (entry != 0x42 && entry != 0x44 && entry != 0x46 && entry != 0x48) {
        if (after > before) tap->stats.other_entries++;
        return;
    }
    const Vu1& vu = r->vif.vu;
    Job job;
    job.vu = vu.data; job.own = nullptr;
    job.qword = qword; job.entry = (uint32_t)entry; job.itop = vu.itop; job.top = vu.top;
    job.before = before; job.after = after;
    memcpy(job.rows, tap->rows, sizeof job.rows);
    job.have_rows = tap->have_rows; job.mirrored = tap->mirrored; job.clip_flag = tap->clip_flag; job.rows_kind = tap->rows_kind;
    job.object = tap->object; job.joint_epoch = tap->joint_epoch;
    job.kind = JOB_KICK;
    if (!tap->async) {
        tap->kicked(job);
        g_tap_ms += tap_now_ms() - t1;
        return;
    }
    // what kicked() reads of VU1 memory, into a copy of its own (at the same addresses)
    uint8_t* copy = tap->buffer();
    auto grab = [&](uint32_t from, uint32_t count) {    // quadwords from..from + count, round the end of the memory
        count = std::min<uint32_t>(count, 0x400);
        from &= 0x3FF;
        const uint32_t first = std::min<uint32_t>(count, 0x400 - from);
        memcpy(copy + from * 16, vu.data + from * 16, (size_t)first * 16);
        if (count > first) memcpy(copy, vu.data, (size_t)(count - first) * 16);
    };
    auto U = [&](uint32_t q) { return (const uint32_t*)(vu.data + (q & 0x3FF) * 16); };
    const uint32_t q = qword & 0x3FF;
    const uint32_t* tag = U(q);
    const uint32_t nloop = tag[0] & 0x7FFF, nreg = (tag[1] >> 28) & 15;
    grab(q, 1 + (nloop <= 96 && nreg <= 4 ? nloop * nreg : 0));
    const uint32_t N = vu.itop;
    if (N >= 1 && N <= 64) {
        // positions, normals, slot rows; the weight entries (models), walked as kicked() walks them; the copy rows
        uint32_t at = vu.top + 3 * N + 2;
        if (entry == 0x42 || entry == 0x44) {
            uint32_t v = 0, guard = 0;
            while (v < N && guard++ < 200) {
                const uint32_t* e = U(at++);
                if ((e[2] & 0xFF) == 0xFF) { v += e[3] & 0xFF; continue; }
                if ((e[1] & 0xFF) + (e[3] & 0xFF) != 255) at++;
                v++;
            }
            const uint32_t* pad = U(at);
            if ((pad[0] & 0xFFFF) == 0 && (pad[1] & 0xFF) == 255 && (pad[2] & 0xFF) == 255 && (pad[3] & 0xFF) == 255) at++;     // the unused entry
            grab(0, 260);                               // the joint matrices (the weight entries' joint bytes are their addresses)
        }
        const uint32_t copies = std::min<uint32_t>(U(at)[0] & 0xFFFF, 96);
        grab(vu.top, std::min<uint32_t>(at + 1 + copies - vu.top, 0x400));
    }
    job.vu = copy; job.own = copy;
    tap->pending.push_back(job);
    if (tap->pending.size() >= 32) tap->hand_over();
    if (timed) { const double ms = (tap_now_ms() - t1) * 8; g_tap_ms += ms; g_tap_copy_ms += ms; }
}

uint8_t* SceneTap::buffer() {
    if (mine.empty()) {
        std::unique_lock<std::mutex> g(lock);
        if (spare.empty() && buffers >= 4096) done.wait(g, [&] { return !spare.empty(); });
        while (!spare.empty() && mine.size() < 64) { mine.push_back(spare.back()); spare.pop_back(); }
    }
    if (!mine.empty()) { uint8_t* b = mine.back(); mine.pop_back(); return b; }
    buffers++;
    return new uint8_t[0x4000];
}

void SceneTap::cut(std::function<void(TapFrame&)> then) {
    if (!async) { take_now(cut_frame); then(cut_frame); return; }
    { std::lock_guard<std::mutex> g(lock); cuts.push_back(std::move(then)); }
    Job job;
    memset(&job, 0, sizeof job);
    job.kind = JOB_CUT;
    pending.push_back(job);
    hand_over();
}

// the kicks gathered so far, to the worker
void SceneTap::hand_over() {
    if (pending.empty()) return;
    {
        std::lock_guard<std::mutex> g(lock);
        if (!worker.joinable()) worker = std::thread([this] { work(); });
        for (const Job& j : pending) queue.push_back(j);
    }
    pending.clear();
    wake.notify_one();
}

void SceneTap::kicked(const Job& job) {
    const int entry = (int)job.entry;
    const size_t before = job.before, after = job.after;
    const float* rows = job.rows;
    const bool have_rows = job.have_rows, mirrored = job.mirrored, clip_flag = job.clip_flag;
    const uint8_t rows_kind = job.rows_kind;
    const uint32_t object = job.object;
    if (job.joint_epoch != joints_epoch_seen) { joints_at = -1; joints_epoch_seen = job.joint_epoch; }
    const uint8_t* data = job.vu;
    auto U = [&](uint32_t q) { return (const uint32_t*)(data + (q & 0x3FF) * 16); };
    auto S = [&](uint32_t q) { return (const int32_t*)(data + (q & 0x3FF) * 16); };
    auto F = [&](uint32_t q) { return (const float*)(data + (q & 0x3FF) * 16); };
    uint32_t qword = job.qword & 0x3FF;
    const uint32_t* tag = U(qword);
    const uint32_t nloop = tag[0] & 0x7FFF, nreg = (tag[1] >> 28) & 15;
    if (!nloop || qword == 0x3F6) return;           // the empty packet between two passes
    stats.kicks++;
    const uint32_t N = job.itop, in = job.top & 0x3FF;
    if ((nreg != 3 && nreg != 4) || N < 1 || N > 64 || nloop > 96) { stats.rejected_layout++; return; }
    const uint32_t strip = qword + 1;
    uint32_t drawn = 0;
    for (uint32_t p = 2; p < nloop; p++) if (!(U(strip + p * nreg + nreg - 1)[3] & 0x8000)) drawn++;
    if (after - before != (size_t)drawn * 3) { stats.rejected_count++; return; }

    // ---- the strip, replayed from the slot rows ----
    int slot[96];
    bool hidden[96];                                // the strip's own no-draw bit (bit 15 of the address written to)
    for (uint32_t p = 0; p < nloop; p++) { slot[p] = -1; hidden[p] = true; }
    auto pos = [&](uint32_t address) -> int {
        address &= 0x7FFF;
        uint32_t p = nreg == 3 ? address / 3 : (address - 1) / 4;
        if (nreg == 3 ? address % 3 != 0 : (address < 1 || (address - 1) % 4 != 0)) return -1;
        return p < nloop ? (int)p : -1;
    };
    for (uint32_t j = 0; j < N + 2; j++) {
        const uint32_t* row = U(in + 2 * N + j);
        int from = pos(row[1] & 0xFFFF), copy = from >= 0 ? slot[from] : -1;
        if (j >= 2) { int to = pos(row[0] & 0xFFFF); if (to >= 0) { slot[to] = (int)j - 2; hidden[to] = (row[0] & 0x8000) != 0; } }
        if (copy >= 0) { int to = pos(row[2] & 0xFFFF); if (to >= 0) { slot[to] = copy; hidden[to] = (row[2] & 0x8000) != 0; } }
    }
    // ---- joints and weights (models), and where the copy rows are ----
    const bool model = entry == 0x42 || entry == 0x44;
    uint8_t joint[64][4], weight[64][4];
    uint32_t at = in + 3 * N + 2;
    bool skinned = false;
    if (model) {
        uint32_t v = 0, guard = 0;
        while (v < N && guard++ < 200) {
            const uint32_t* e = U(at++);
            uint32_t j1 = e[0] & 0xFF, w1 = e[1] & 0xFF, j2 = e[2] & 0xFF, w2 = e[3] & 0xFF;
            if (j2 == 0xFF) {                           // a run on one joint
                for (uint32_t k = 0; k < w2 && v < N; k++, v++) {
                    joint[v][0] = (uint8_t)j1; weight[v][0] = 255;
                    joint[v][1] = joint[v][2] = joint[v][3] = 0; weight[v][1] = weight[v][2] = weight[v][3] = 0;
                }
                if (j1) skinned = true;
                continue;
            }
            joint[v][0] = (uint8_t)j1; weight[v][0] = (uint8_t)w1; joint[v][1] = (uint8_t)j2; weight[v][1] = (uint8_t)w2;
            joint[v][2] = joint[v][3] = 0; weight[v][2] = weight[v][3] = 0;
            if (w1 + w2 != 255) {
                const uint32_t* e2 = U(at++);
                joint[v][2] = (uint8_t)(e2[0] & 0xFF); weight[v][2] = (uint8_t)(e2[1] & 0xFF);
                if ((e2[2] & 0xFF) != 0xFF) { joint[v][3] = (uint8_t)(e2[2] & 0xFF); weight[v][3] = (uint8_t)(e2[3] & 0xFF); }
            }
            skinned = true;
            v++;
        }
        if (v < N) { stats.rejected_layout++; return; }
        const uint32_t* pad = U(at);
        if ((pad[0] & 0xFFFF) == 0 && (pad[1] & 0xFF) == 255 && (pad[2] & 0xFF) == 255 && (pad[3] & 0xFF) == 255) at++;     // the unused entry
    }
    {
        const uint32_t* head = U(at);
        uint32_t copies = head[0] & 0xFFFF;
        if (copies > 96 || (head[1] & 0xFFFF) || (head[2] & 0xFFFF) || (head[3] & 0xFFFF)) { stats.rejected_layout++; return; }
        for (uint32_t k = 0; k < copies; k++) {
            const uint32_t* row = U(at + 1 + k);
            int s1 = pos(row[0] & 0xFFFF), d1 = pos(row[1] & 0xFFFF), s2 = pos(row[2] & 0xFFFF), d2 = pos(row[3] & 0xFFFF);
            int a = s1 >= 0 ? slot[s1] : -1, b = s2 >= 0 ? slot[s2] : -1;
            if (d1 >= 0 && a >= 0) { slot[d1] = a; hidden[d1] = (row[1] & 0x8000) != 0; }
            if (d2 >= 0 && b >= 0) { slot[d2] = b; hidden[d2] = (row[3] & 0x8000) != 0; }
        }
        at += 1 + copies;
    }
    for (uint32_t p = 2; p < nloop; p++)
        if (!(U(strip + p * nreg + nreg - 1)[3] & 0x8000) && (slot[p] < 0 || slot[p - 1] < 0 || slot[p - 2] < 0)) { stats.rejected_layout++; return; }
    if (!model && !have_rows) { stats.rejected_layout++; return; }
    // the replay's no-draw bits against the program's: the same wherever the clip pass did not run
    uint32_t complete = 0;
    for (uint32_t p = 2; p < nloop; p++) {
        if (slot[p] < 0) continue;
        const bool adc = (U(strip + p * nreg + nreg - 1)[3] & 0x8000) != 0;
        if (!clip_flag) { stats.stitch_checked++; if (adc != hidden[p]) stats.stitch_off++; }
        if (!hidden[p] && slot[p - 1] >= 0 && slot[p - 2] >= 0) { complete++; if (adc) stats.dropped_restored++; }
    }
    if (!drawn && !complete) return;

    // (XXH3 over the packet's words: a byte-at-a-time figure over a few kilobytes a kick was most of the tap's time in a
    // fight; the identity is only compared within a run, never kept)
    uint64_t h = 0xCBF29CE484222325ull ^ (uint64_t)entry;
    const uint32_t body = 3 * N + 2;                                          // positions, normals, slot rows
    if ((in & 0x3FF) + body <= 0x400) h = (h * 0x100000001B3ull) ^ xxh3::hash64(U(in), (size_t)body * 16);
    else h = fnv((const uint8_t*)U(in), (size_t)body * 16, h);              // (round the end of VU1 memory: as before)
    if (model) {
        const uint32_t extra = (uint32_t)((at - (in + 3 * N + 2)) & 0xFF);
        if (((in + body) & 0x3FF) + extra <= 0x400) h = (h * 0x100000001B3ull) ^ xxh3::hash64(U(in + body), (size_t)extra * 16);
        else h = fnv((const uint8_t*)U(in + body), (size_t)extra * 16, h);
    }
    // The second kick of a two-pass packet (the same words, the same set-up, right after the first): its vertices are the
    // first's - taken from it, not computed again (the same computation on the same inputs: the same bytes)
    const bool reuse = nreg == 4 && reuse_ok && !frame.pieces.empty() && frame.pieces.back().mesh == h && frame.pieces.back().object == object &&
                       (frame.pieces.back().flags & TAP_FIRST_PASS) && reuse_n == N && reuse_in == in && reuse_epoch == job.joint_epoch && reuse_model == model;
    // ---- the vertices, through the matrices the program used ----
    struct Made { double clip[4], normal[4]; };
    static_assert(sizeof(Made) * 64 == sizeof(reuse_made), "the kept vertices");
    Made made[64];
    TapSource source[64];
    if (reuse) { memcpy(made, reuse_made, sizeof(Made) * N); memcpy(source, reuse_source, sizeof(TapSource) * N); }
    for (uint32_t v = 0; v < (reuse ? 0 : N); v++) {
        const int32_t* ps = S(in + v);
        const int32_t* ns = S(in + N + v);
        double p[3] = {ps[0] / 16.0, ps[1] / 16.0, ps[2] / 16.0};
        double n[3] = {(double)ns[0], (double)ns[1], (double)ns[2]};
        double length = std::sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]);
        if (length > 0) { n[0] /= length; n[1] /= length; n[2] /= length; }
        TapSource& s = source[v];
        for (int a = 0; a < 3; a++) { s.position[a] = (float)p[a]; s.normal[a] = (float)n[a]; }
        Made& m = made[v];
        for (int c = 0; c < 4; c++) m.clip[c] = m.normal[c] = 0;
        if (model) {
            for (int k = 0; k < 4; k++) {
                s.joint[k] = (uint8_t)(joint[v][k] >> 2); s.weight[k] = weight[v][k];
                if (!weight[v][k]) continue;
                const double w = weight[v][k] / 255.0;
                const float* j0 = F(joint[v][k]);       // the joint byte is the matrix's address
                const float* j1 = F(joint[v][k] + 1u);
                const float* j2 = F(joint[v][k] + 2u);
                const float* j3 = F(joint[v][k] + 3u);
                for (int c = 0; c < 4; c++) {
                    m.clip[c] += w * (p[0] * j0[c] + p[1] * j1[c] + p[2] * j2[c] + j3[c]);
                    m.normal[c] += w * (n[0] * j0[c] + n[1] * j1[c] + n[2] * j2[c]);
                }
            }
        } else {
            memset(s.joint, 0, 4); s.weight[0] = 255; s.weight[1] = s.weight[2] = s.weight[3] = 0;
            for (int c = 0; c < 4; c++) {
                m.clip[c] = p[0] * rows[c] + p[1] * rows[4 + c] + p[2] * rows[8 + c] + rows[12 + c];
                m.normal[c] = n[0] * rows[c] + n[1] * rows[4 + c] + n[2] * rows[8 + c];
            }
        }
    }
    // ---- the check: is that where the program put them? ----
    if (check) {
        uint32_t off = 0, compared = 0;
        double worst = 0;
        for (uint32_t p = 0; p < nloop; p++) {
            if (slot[p] < 0) continue;
            const Made& m = made[slot[p]];
            if (!(m.clip[3] > 1e-6)) continue;
            double sx = m.clip[0] / m.clip[3], sy = m.clip[1] / m.clip[3];
            if (std::fabs(sx) > 1900 || std::fabs(sy) > 1900) continue;         // would wrap in 16 bits
            const uint32_t* xyz = U(strip + p * nreg + nreg - 1);
            double dx = (2048.0 + sx) * 16.0 - (double)(xyz[0] & 0xFFFF), dy = (2048.0 + sy) * 16.0 - (double)(xyz[1] & 0xFFFF);
            double d = std::max(std::fabs(dx), std::fabs(dy));
            compared++;
            if (d > 4.0) off++; else if (d > worst) worst = d;
        }
        stats.checked += compared;
        stats.off += off;
        if (off) { stats.rejected_check++; return; }
        if (worst > stats.worst) stats.worst = worst;
    }

    // ---- the piece ----
    TapPiece piece;
    memset(&piece, 0, sizeof piece);
    piece.kind = model ? TAP_MODEL : rows_kind;
    piece.entry = (uint8_t)entry;
    piece.flags = (uint8_t)((nreg == 4 ? TAP_TWO_PASS : 0) | (skinned ? TAP_SKINNED : 0) | (mirrored ? TAP_MIRRORED : 0) | (clip_flag ? TAP_CLIP_FLAG : 0));
    piece.object = object;
    piece.mesh = h;
    bool second = false;
    if (nreg == 4) {
        // the first of the two kicks of a packet is the environment-map layer
        second = !frame.pieces.empty() && frame.pieces.back().mesh == h && frame.pieces.back().object == object && (frame.pieces.back().flags & TAP_FIRST_PASS);
        if (!second) piece.flags |= TAP_FIRST_PASS;
    }
    uint32_t& count = seen[h];
    piece.occurrence = second ? count - 1 : count++;
    piece.list_first = (uint32_t)before;
    piece.list_count = (uint32_t)(after - before);
    piece.first = (uint32_t)frame.vertices.size();
    piece.source_first = (uint32_t)frame.sources.size();
    piece.source_count = N;
    frame.sources.insert(frame.sources.end(), source, source + N);
    if (model) {
        if (joints_at < 0) {                            // this object's 64 joint matrices, once
            joints_at = (int)(frame.joints.size() / 16);
            frame.joints.insert(frame.joints.end(), F(0), F(0) + 64 * 16);
        }
        piece.joints = (uint32_t)joints_at;
    } else {
        piece.joints = (uint32_t)(frame.joints.size() / 16);
        frame.joints.insert(frame.joints.end(), rows, rows + 16);
    }
    // the level's matrices are g_viewProjWorld's (in world / 4); the models' are g_viewProjModel's
    const double scale = piece.kind == TAP_LEVEL ? 4.0 : 1.0;
    const double* const inverse = piece.kind == TAP_LEVEL ? inverse_world : this->inverse;
    // Each source vertex is taken back to the world once (it stands at up to six corners of the list and the complete
    // geometry: the same computation, done once, gives the same bytes)
    TapVertex world_of[64];
    bool world_done[64];
    if (reuse) { memcpy(world_of, reuse_world, sizeof(TapVertex) * N); memcpy(world_done, reuse_done, N); }
    else for (uint32_t v = 0; v < N; v++) world_done[v] = false;
    // (the list's vertices and the corners are written in place: the counts are known - drawn, complete)
    auto make = [&](int sv) -> const TapVertex& {
        if (world_done[sv]) return world_of[sv];
        const Made& m = made[sv];
        TapVertex out;
        memset(&out, 0, sizeof out);
        out.source = (uint16_t)sv;
        out.clip[0] = (float)m.clip[0]; out.clip[1] = (float)m.clip[1]; out.clip[2] = (float)(m.clip[2] * DEPTH_SCALE); out.clip[3] = (float)m.clip[3];
        if (frame.have_camera) {
            const double c[4] = {m.clip[0], m.clip[1], m.clip[2] * DEPTH_SCALE, m.clip[3]};
            const double d[4] = {m.normal[0], m.normal[1], m.normal[2] * DEPTH_SCALE, m.normal[3]};
            double w[4], n[3];
            for (int a = 0; a < 4; a++) w[a] = c[0] * inverse[a] + c[1] * inverse[4 + a] + c[2] * inverse[8 + a] + c[3] * inverse[12 + a];
            for (int a = 0; a < 3; a++) n[a] = d[0] * inverse[a] + d[1] * inverse[4 + a] + d[2] * inverse[8 + a] + d[3] * inverse[12 + a];
            const double hw = std::fabs(w[3]) > 1e-12 ? w[3] : 1.0;
            for (int a = 0; a < 3; a++) out.world[a] = (float)(w[a] / hw * scale);
            double length = std::sqrt(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]);
            if (length > 0) for (int a = 0; a < 3; a++) out.normal[a] = (float)(n[a] / length);
        }
        world_of[sv] = out;
        world_done[sv] = true;
        return world_of[sv];
    };
    {
        const size_t first = frame.vertices.size();
        frame.vertices.resize(first + (size_t)drawn * 3);
        TapVertex* o = frame.vertices.data() + first;
        for (uint32_t p = 2; p < nloop; p++)
            if (!(U(strip + p * nreg + nreg - 1)[3] & 0x8000)) { *o++ = make(slot[p - 2]); *o++ = make(slot[p - 1]); *o++ = make(slot[p]); }
    }
    // ---- the complete geometry: every triangle of the strip, with what the program wrote beside each position ----
    piece.full_first = (uint32_t)frame.full.size();
    if (frame.have_camera) {
        const uint64_t regs = (uint64_t)tag[2] | (uint64_t)tag[3] << 32;
        uint32_t uv_at = 0, rgba_at = nreg - 2;
        for (uint32_t k = 0; k < nreg; k++) { uint32_t d = (uint32_t)(regs >> (4 * k)) & 15; if (d == 3) uv_at = k; else if (d == 1) rgba_at = k; }
        const size_t first = frame.full.size();
        frame.full.resize(first + (size_t)complete * 3);
        frame.full_source.resize(first + (size_t)complete * 3);
        TapFull* fo = frame.full.data() + first;
        uint16_t* so = frame.full_source.data() + first;
        auto corner = [&](uint32_t p) {
            const TapVertex& made_vertex = make(slot[p]);
            TapFull& out = *fo++;
            memcpy(out.world, made_vertex.world, 12);
            memcpy(out.normal, made_vertex.normal, 12);
            const uint32_t* uv = U(strip + p * nreg + uv_at);
            const uint32_t* colour = U(strip + p * nreg + rgba_at);
            out.uv[0] = (float)(uv[0] & 0x3FFF) * (1.0f / 16.0f); out.uv[1] = (float)(uv[1] & 0x3FFF) * (1.0f / 16.0f);
            out.rgba[0] = (uint8_t)colour[0]; out.rgba[1] = (uint8_t)colour[1]; out.rgba[2] = (uint8_t)colour[2]; out.rgba[3] = (uint8_t)colour[3];
            *so++ = (uint16_t)slot[p];
        };
        for (uint32_t p = 2; p < nloop; p++)
            if (!hidden[p] && slot[p] >= 0 && slot[p - 1] >= 0 && slot[p - 2] >= 0) { corner(p - 2); corner(p - 1); corner(p); }
    }
    piece.full_count = (uint32_t)frame.full.size() - piece.full_first;
    frame.pieces.push_back(piece);
    // a first pass: its vertices kept for its second
    reuse_ok = (piece.flags & TAP_FIRST_PASS) != 0;
    if (reuse_ok) {
        memcpy(reuse_made, made, sizeof(Made) * N); memcpy(reuse_source, source, sizeof(TapSource) * N);
        memcpy(reuse_world, world_of, sizeof(TapVertex) * N); memcpy(reuse_done, world_done, N);
        reuse_n = N; reuse_in = in; reuse_epoch = job.joint_epoch; reuse_model = model;
    }
    stats.pieces++;
    stats.vertices += piece.list_count;
}

void SceneTap::take(TapFrame& out) {
    drain();
    take_now(out);
}

void SceneTap::take_now(TapFrame& out) {
    std::swap(out.pieces, frame.pieces);
    std::swap(out.vertices, frame.vertices);
    std::swap(out.sources, frame.sources);
    std::swap(out.full, frame.full);
    std::swap(out.joints, frame.joints);
    std::swap(out.full_source, frame.full_source);
    out.have_camera = frame.have_camera;
    memcpy(out.clip_to_world, frame.clip_to_world, sizeof out.clip_to_world);
    out.batch = frame.batch;
    memcpy(out.world_to_view, frame.world_to_view, sizeof out.world_to_view);
    memcpy(out.view_projection, frame.view_projection, sizeof out.view_projection);
    out.proj_scale = frame.proj_scale;
    out.near_plane = frame.near_plane; out.far_plane = frame.far_plane;
    frame.clear();
    seen.clear();
    joints_at = -1;
    reuse_ok = false;
}

}  // namespace render
