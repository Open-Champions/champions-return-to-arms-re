// fpview.cpp - see fpview.h.  Compiled with the runtime's flags; supplies the fn_<address> of
// the functions listed under "view modes" in tools/recomp/hle.txt.
//
// What happens in a displayed frame with a view other than overhead selected:
//
//   the run pass      nothing of this file.  The game's camera object and the engine camera
//                     are the game's own.
//   tasks_call(0, 1)  begin_pass: the camera of the selected view is made from the game
//                     camera's yaw, the local player's position and facing, and the camera
//                     stick (look up / down; host-side state, never written to the game);
//                     the words camera_setProjection and camera_setView write are saved;
//                     both are called (the game's own code, through gfx_rt's widescreen
//                     hooks) with the view's field of view, position and orientation.
//                     Then the game's draw tasks run: they cull and draw for that camera.
//                     camera_updateFocus, which drawWorld calls, is handed the game's own
//                     camera for the length of the call: g_cameraFocus stays what it is in
//                     the overhead view (the simulation reads it).
//   end_pass          the saved words are put back; gfx_rt's host-side copies are brought
//                     back by running the game's own projection and view once more.
//   worldtex_stream   (after the pass) keeps texture cells loaded round g_cameraFocus; for
//                     the length of that call the focus is the drawn view's.
//
// Options (after "--" on the command line, "--opt key=value"):
//   view=NAME            the view at start (the application's --view sets the same thing)
//   view-zoom=off        the game camera's zoom steps (camera stick fully up / down) are held off
//                        while a view that looks with the stick is selected.  This changes what the
//                        game camera does with a pad row (its zoom index, and through it the speed
//                        its yaw turns at): not presentation-only, off by default
//   view-log=1           one line per second with the view's figures
//   view-clock=counted   the draw pass of a view costs the virtual console its time like any other code
//                        (default: it costs none, see begin_pass)
//   tests: view-stream=off (the texture stream keeps to the game's focus), view-collide=off,
//          view-light=off
#include "fpview.h"
#include "gfx_rt.h"

#include "rt.h"
#include "funcs.h"

#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

namespace fpview {
namespace {

// ---- the game's words ------------------------------------------------------------------------
const u32 G_LOCAL_CAMERA = 0x4F8450;        // pointer to this machine's camera object
const u32 CAM_MODE = 0x34, CAM_TRANSITION = 0x48, CAM_ZOOM = 0x54, CAM_YAW = 0x68, CAM_PAD_SLOT = 0x40;
const u32 G_CAMERA_POS = 0x44F038, G_CAMERA_FOCUS = 0x44F048, G_CAMERA_MATRIX = 0x44F110, G_PROJ_SCALE = 0x44F108;
const u32 G_FAR_CLIP = 0x7D8A04;
const u32 PLANE_NEAR_D = 0x44F104, PLANE80_NEAR_D = 0x7D5C64;   // d of the near plane in the two world-space sets (the game: -18)
const u32 G_WORLD = 0x44FDC8, G_SIM_FRAME = 0x44FDCC, G_DRAW_FRAME = 0x44FDD0;
const u32 G_CUTSCENE_ACTIVE = 0x44FCD0, G_LOADSCREEN_ACTIVE = 0x506094, G_WARMUP_FRAMES = 0x506048;
const u32 G_LOCAL_ALIVE_COUNT = 0x4F8424, G_LOCAL_ALIVE = 0x4F8430;
const u32 G_PLAYER_OBJECT = 0x4DCEC8, PLAYER_STRIDE = 0x4C30;   // g_players[slot] + 0x43d8
const u32 OBJ_POS = 0x10, OBJ_FACING = 0x38;
const u32 G_PADS = 0x41BFD8, PAD_STRIDE = 0x58, PAD_RX = 0x1C, PAD_RY = 0x20;
const u32 G_DL_CURSOR = 0x44FE10, G_DL_BASE = 0x44FE0C, G_DL_UNITS = 0x44FDA4;
const u32 RAM_MASK = 0x01FFFFFF;

// what camera_setProjection (0x18619c) and camera_setView (0x18a2b0, with camera_buildFrustum
// 0x1863fc) write, and g_farClip: saved before a view is put in place, put back after the pass
struct Region { u32 addr, size; };
const Region SAVED[] = {
    {0x44F038, 12},     // g_cameraPos
    {0x44F0A8, 0x60},   // the view's six planes, world space
    {0x44F108, 4},      // g_projScale
    {0x44F110, 0x30},   // g_cameraMatrix
    {0x44F140, 0xC0},   // g_viewProj, g_viewProjWorld, g_viewProjModel
    {0x7D5BC0, 0x48},   // the view's planes, camera space
    {0x7D5C08, 0x60},   // the 80-degree set, world space
    {0x7D5C68, 0x48},   // the 80-degree set, camera space
    {0x7D89D8, 18},     // sign bytes of the two world-space sets
    {0x7D89F0, 18},
    {0x7D8A04, 4},      // g_farClip
};
const size_t SAVED_BYTES = 12 + 0x60 + 4 + 0x30 + 0xC0 + 0x48 + 0x60 + 0x48 + 18 + 18 + 4;

inline float as_float(u32 bits) { float f; memcpy(&f, &bits, 4); return f; }
inline u32 as_bits(float f) { u32 b; memcpy(&b, &f, 4); return b; }
inline float F(u32 addr) { return as_float(W(addr)); }
inline bool in_ram(u32 pointer, u32 size) { return pointer != 0 && guest_addr(pointer, size) != ~0u; }
inline u32 at(u32 pointer) { return pointer & 0x1FFFFFFF; }

const float PI = 3.14159265358979f, DEG = PI / 180.0f;

// ---- small vector arithmetic (the host's floats: nothing of this is simulation) --------------------
inline Vec3 v3(float x, float y, float z) { return Vec3{x, y, z}; }
inline Vec3 operator+(Vec3 a, Vec3 b) { return v3(a.x + b.x, a.y + b.y, a.z + b.z); }
inline Vec3 operator-(Vec3 a, Vec3 b) { return v3(a.x - b.x, a.y - b.y, a.z - b.z); }
inline Vec3 operator*(Vec3 a, float s) { return v3(a.x * s, a.y * s, a.z * s); }
inline float dot(Vec3 a, Vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
inline Vec3 cross(Vec3 a, Vec3 b) { return v3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x); }
inline float length(Vec3 a) { return std::sqrt(dot(a, a)); }
inline Vec3 normal(Vec3 a, Vec3 or_else) { float l = length(a); return l > 1e-6f ? a * (1.0f / l) : or_else; }
inline Vec3 mix(Vec3 a, Vec3 b, float t) { return a + (b - a) * t; }
inline float mixf(float a, float b, float t) { return a + (b - a) * t; }
inline float clampf(float v, float lo, float hi) { return v < lo ? lo : v > hi ? hi : v; }
inline float smooth(float t) { t = clampf(t, 0, 1); return t * t * (3 - 2 * t); }
inline float wrap_deg(float a) { while (a > 180) a -= 360; while (a < -180) a += 360; return a; }

struct Quat { float w, x, y, z; };
// from the frame (right, down, forward) as the columns of a rotation
Quat quat_of(Vec3 r, Vec3 d, Vec3 f) {
    float m00 = r.x, m01 = d.x, m02 = f.x, m10 = r.y, m11 = d.y, m12 = f.y, m20 = r.z, m21 = d.z, m22 = f.z;
    float trace = m00 + m11 + m22;
    Quat q;
    if (trace > 0) {
        float s = std::sqrt(trace + 1.0f) * 2;
        q = {0.25f * s, (m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s};
    } else if (m00 > m11 && m00 > m22) {
        float s = std::sqrt(1.0f + m00 - m11 - m22) * 2;
        q = {(m21 - m12) / s, 0.25f * s, (m01 + m10) / s, (m02 + m20) / s};
    } else if (m11 > m22) {
        float s = std::sqrt(1.0f + m11 - m00 - m22) * 2;
        q = {(m02 - m20) / s, (m01 + m10) / s, 0.25f * s, (m12 + m21) / s};
    } else {
        float s = std::sqrt(1.0f + m22 - m00 - m11) * 2;
        q = {(m10 - m01) / s, (m02 + m20) / s, (m12 + m21) / s, 0.25f * s};
    }
    return q;
}
Quat slerp(Quat a, Quat b, float t) {
    float d = a.w * b.w + a.x * b.x + a.y * b.y + a.z * b.z;
    if (d < 0) { b = {-b.w, -b.x, -b.y, -b.z}; d = -d; }
    float ka, kb;
    if (d > 0.9995f) { ka = 1 - t; kb = t; }
    else {
        float angle = std::acos(d), s = std::sin(angle);
        ka = std::sin((1 - t) * angle) / s;
        kb = std::sin(t * angle) / s;
    }
    Quat q = {a.w * ka + b.w * kb, a.x * ka + b.x * kb, a.y * ka + b.y * kb, a.z * ka + b.z * kb};
    float n = std::sqrt(q.w * q.w + q.x * q.x + q.y * q.y + q.z * q.z);
    return {q.w / n, q.x / n, q.y / n, q.z / n};
}
void frame_of(Quat q, Vec3& r, Vec3& d, Vec3& f) {
    float xx = q.x * q.x, yy = q.y * q.y, zz = q.z * q.z, xy = q.x * q.y, xz = q.x * q.z, yz = q.y * q.z, wx = q.w * q.x, wy = q.w * q.y, wz = q.w * q.z;
    r = v3(1 - 2 * (yy + zz), 2 * (xy + wz), 2 * (xz - wy));
    d = v3(2 * (xy - wz), 1 - 2 * (xx + zz), 2 * (yz + wx));
    f = v3(2 * (xz + wy), 2 * (yz - wx), 1 - 2 * (xx + yy));
}

// A camera: where, which way, how wide.
struct Pose {
    Vec3 eye{}, right{1, 0, 0}, down{0, 0, -1}, forward{0, 1, 0};
    float fov = 50, near_plane = 18;
};
// forward (unit) and no roll: the frame the game's own look-at makes (Camera_apply 0x2035c8)
void aim(Pose& p, Vec3 forward) {
    p.forward = normal(forward, v3(0, 1, 0));
    p.right = normal(v3(p.forward.y, -p.forward.x, 0), v3(1, 0, 0));
    p.down = normal(cross(p.forward, p.right), v3(0, 0, -1));
}
Pose blend(const Pose& a, const Pose& b, float t) {
    Pose p;
    p.eye = mix(a.eye, b.eye, t);
    p.fov = mixf(a.fov, b.fov, t);
    p.near_plane = mixf(a.near_plane, b.near_plane, t);
    frame_of(slerp(quat_of(a.right, a.down, a.forward), quat_of(b.right, b.down, b.forward), t), p.right, p.down, p.forward);
    return p;
}

// ---- settings ----------------------------------------------------------------------------------
struct ModeSettings {
    float fov, near_plane;
    float distance;         // from the pivot back along the view
    float height;           // of the pivot above the character's feet
    float side;             // of the pivot to the character's right
    float pitch;            // at rest: up (+) / down (-), degrees
    float pitch_min, pitch_max;     // what the camera stick can reach (equal: the stick does not look)
    float eye_forward;      // first person: the eye this far in front of the head
    float look_speed;       // degrees a second at full stick
    float far;              // cull distance, 0 = the level's own
    bool head_pose;         // first person: the eye follows the head joint (else a fixed height)
    bool hide_player;
    bool collide;           // pull in when the level is between pivot and camera
    float follow = 0;       // 0..1: how far the view turns from the game camera's heading to the character's facing
};
ModeSettings g_set[MODE_COUNT] = {
    //  fov near dist height side pitch  min   max  fwd  speed far  head   hide   collide
    {50, 18, 0, 0, 0, 0, 0, 0, 0, 0, 0, false, false, false},                 // overhead: the game's
    {50, 18, 215, 55, 0, -33, -33, -33, 0, 0, 0, false, false, true},         // action
    {58, 12, 150, 62, 0, -14, -45, 25, 0, 90, 0, false, false, true},         // chase
    {60, 8, 88, 66, 20, -8, -55, 45, 0, 100, 0, false, false, true},          // shoulder
    {70, 4, 0, 60, 0, 0, -65, 65, 7, 110, 0, false, true, false},             // first
};
float g_ease_seconds = 0.35f;
const char* const NAMES[MODE_COUNT] = {"overhead", "action", "chase", "shoulder", "first"};
std::mutex g_settings_lock;         // settings arrive from the application's thread
std::string g_settings_text;

std::atomic<int> g_wanted{OVERHEAD};
bool g_options_read = false, g_zoom_off = false, g_log = false;
bool g_stream_follows = true, g_collide = true, g_light = true, g_free_pass = true, g_hold_rate = true;      // tests: --opt view-stream=off, view-collide=off, view-light=off

// ---- state of the view (host side; the game never reads it) --------------------------------------
View g_view;
int g_mode = OVERHEAD;              // the view being shown or eased to
float g_t = 1;                      // 0..1 through the transition into g_mode
bool g_have_from = false;           // the pose the transition starts from, kept relative to the character
Vec3 g_from_offset{};               // eye - anchor, in the heading frame (ahead, left, up)
Quat g_from_turn{1, 0, 0, 0};       // orientation relative to the heading
float g_from_fov = 50, g_from_near = 18;
Pose g_shown;                       // the pose of the last active frame
bool g_shown_valid = false;
bool g_was_fallback = true;
float g_pitch[MODE_COUNT];          // what the stick has added, per view
std::atomic<float> g_pitch_add{0};  // add_pitch(): taken at the next draw pass
float g_anchor_z = 0;               // the character's height, smoothed over steps
bool g_anchor_valid = false;
float g_pull[MODE_COUNT];           // distance in use after pulling in for the level
float g_raise[MODE_COUNT];          // degrees the camera has swung up over what stood in the way
float g_turn = 0;                   // degrees the view is turned from the game camera's heading toward the facing (follow)
u32 g_last_tick = 0;
bool g_in_pass = false;             // a view is in place: between begin_pass and end_pass
u8 g_saved[SAVED_BYTES];
u32 g_game_args[4];                 // camera_setProjection as the game last asked
u32 g_stream_frame = ~0u;           // g_drawFrame of the pass whose view the texture stream follows
u64 g_time_pass_end = 0, g_time_stream_in = 0, g_time_stream_out = 0, g_time_begin_in = 0, g_time_begin_out = 0;     // view-timing
void (*g_next_frame_hook)(Ctx*, int) = nullptr;
void timing_frame_hook(Ctx* c, int phase) {
    (phase == 0 ? g_time_begin_in : g_time_begin_out) = rt_cycles();
    if (g_next_frame_hook) g_next_frame_hook(c, phase);
}
u64 g_active_frames = 0, g_fallback_frames = 0, g_hidden_packets = 0, g_passes = 0, g_restore_differs = 0;

struct Callout { void* fn; void* user; };
std::vector<Callout> g_on_view, g_on_drawn;

// the local player's packets of the frame, by display-list buffer
// (a buffer's ranges are good for the frame they were noted in and the one after, in which the list is
// sent: the same addresses hold other packets in every later frame)
struct Hidden { u32 base = 0, size = 0; u64 filled_at = 0; u32 draw_frame = 0; std::vector<std::pair<u32, u32>> ranges; };
Hidden g_hidden[2];
int g_hidden_fill = -1;

void read_options() {
    if (g_options_read) return;
    g_options_read = true;
    if (const char* o = rt_option("view")) { int m = mode_by_name(o); if (m >= 0) g_wanted = m; }
    if (const char* o = rt_option("view-zoom")) g_zoom_off = !strcmp(o, "off");
    g_log = rt_option("view-log") != nullptr;
    if (const char* o = rt_option("view-stream")) g_stream_follows = strcmp(o, "off") != 0;
    if (const char* o = rt_option("view-collide")) g_collide = strcmp(o, "off") != 0;
    if (const char* o = rt_option("view-light")) g_light = strcmp(o, "off") != 0;
    if (const char* o = rt_option("view-clock")) g_free_pass = g_hold_rate = strcmp(o, "counted") != 0;    // the pass at the console's price, the game's own half rate
    for (int m = 0; m < MODE_COUNT; m++) { g_pitch[m] = 0; g_pull[m] = -1; g_raise[m] = -1; }
}

// ---- calling the game ----------------------------------------------------------------------------
// A guest call from inside a hook: the registers are put back afterwards (the loop budget of a
// test build is kept), the callee gets a stack below a scratch area of ours.
struct GuestCall {
    Ctx* c;
    Ctx saved;
    u32 scratch;        // 0x400 bytes of guest memory below the caller's stack pointer
    explicit GuestCall(Ctx* ctx) : c(ctx), saved(*ctx) {
        u32 sp = (u32)saved.r[29];
        scratch = (sp - 0x400) & ~15u;
        c->r[29] = (u64)(s64)(s32)(scratch - 0x200);
    }
    ~GuestCall() { s64 budget = c->budget; *c = saved; c->budget = budget; }
    u32 put(u32 offset, Vec3 v) {
        u32 a = scratch + offset;
        W(at(a)) = as_bits(v.x); W(at(a) + 4) = as_bits(v.y); W(at(a) + 8) = as_bits(v.z); W(at(a) + 12) = 0;
        return a;
    }
    void arg(int n, u32 value) { c->r[4 + n] = (u64)(s64)(s32)value; }
    void farg(int n, float value) { c->f[12 + n] = as_bits(value); }
    float fret() const { return as_float(c->f[0]); }
};

void game_set_projection(Ctx* c, const u32 args[4]) {
    GuestCall call(c);
    memcpy(&c->f[12], args, 16);
    fn_0018619c(c);                 // camera_setProjection, through gfx_rt (widescreen)
}
void game_set_view(Ctx* c, Vec3 eye, Vec3 right, Vec3 down, Vec3 forward) {
    GuestCall call(c);
    u32 pos = call.put(0, eye), m = call.scratch + 0x20;
    const float rows[12] = {right.x, down.x, forward.x, right.y, down.y, forward.y, right.z, down.z, forward.z, 0, 0, 0};
    for (int k = 0; k < 12; k++) W(at(m) + 4 * k) = as_bits(rows[k]);
    call.arg(0, pos);
    call.arg(1, m);
    fn_0018a2b0(c);                 // camera_setView: matrix, three view-projections, planes
}
// net_objOrGhost 0x13e180: the object that is on screen for a player - this machine's own player in a
// net game is shown as its prediction copy when there is one.  Reads only.
u32 game_drawn_object(Ctx* c, u32 object) {
    GuestCall call(c);
    call.arg(0, object);
    fn_0013e180(c);
    u32 shown = (u32)c->r[2];
    return in_ram(shown, 0x600) ? shown : object;
}
void game_scene_light(Ctx* c) {
    if (!g_light) return;
    GuestCall call(c);
    fn_00148018(c);                 // transformSceneLight: the sun and fill directions in camera space
}

void save_words() {
    size_t n = 0;
    for (const Region& r : SAVED) { memcpy(g_saved + n, g_ram + r.addr, r.size); n += r.size; }
}
size_t restore_words() {
    size_t n = 0, differed = 0;
    for (const Region& r : SAVED) {
        if (memcmp(g_ram + r.addr, g_saved + n, r.size)) { differed++; memcpy(g_ram + r.addr, g_saved + n, r.size); }
        n += r.size;
    }
    return differed;
}
const u8* saved_region(u32 addr) {
    size_t n = 0;
    for (const Region& r : SAVED) { if (r.addr == addr) return g_saved + n; n += r.size; }
    return nullptr;
}

// ---- the camera of a view --------------------------------------------------------------------------
struct Inputs {
    Pose game;                      // the game's own camera
    Vec3 heading{}, left{};         // unit vectors in the ground plane: where the game camera looks, and its left
    float yaw = 0;                  // degrees
    Vec3 feet{}, anchor{};          // the character: its position, and the same with the height smoothed
    Vec3 facing_dir{};
    float facing = 0;
    float size = 1;                 // the character's height extent (object +0x20) / 72
    float stick_x = 0, stick_y = 0;
    float dt = 0;                   // seconds of simulation since the last pass
};

float ray_between(Ctx* c, Vec3 from, Vec3 to) {
    u32 world = W(G_WORLD);
    if (!world || !g_collide) return -1;
    Vec3 d = to - from;
    float l = length(d);
    if (l < 0.5f) return -1;
    GuestCall call(c);
    u32 o = call.put(0, from), dir = call.put(0x10, d * (1.0f / l));
    call.farg(0, l);
    call.arg(0, world);
    call.arg(1, o);
    call.arg(2, dir);
    call.arg(3, 0);
    fn_0018a5c0(c);                 // terrain_raycast(maxT, world, origin, dir, flags)
    float t = call.fret();
    if (!(t >= 0)) return -1;
    return clampf(t / l, 0, 1);
}
float ground_under(Ctx* c, Vec3 p) {
    u32 world = W(G_WORLD);
    if (!world || !g_collide) return -1e6f;
    GuestCall call(c);
    u32 pos = call.put(0, p);
    call.farg(0, 6.0f);
    call.arg(0, world);
    call.arg(1, pos);
    fn_00183820(c);                 // terrain_height(radius, world, pos)
    return call.fret();
}

// Is the character seen from `eye`?  Two rays of the game's own terrain query, from the head and from knee
// height: the level's walls are blocks of its height field, so a ray that is clear means nothing of the
// level stands between (objects - crates, pillars that are models - are not asked: they are small).
bool sees(Ctx* c, Vec3 eye, Vec3 head, Vec3 knee) {
    if (ray_between(c, head, eye) >= 0) return false;
    return ray_between(c, knee, eye) < 0;
}

Pose pose_of(Ctx* c, int mode, const Inputs& in) {
    if (mode == OVERHEAD) return in.game;
    const ModeSettings& s = g_set[mode];
    Pose p;
    p.fov = s.fov;
    p.near_plane = s.near_plane;
    float size = in.size;                           // the character's height against the 72 the numbers were chosen for
    float pitch = clampf(s.pitch + g_pitch[mode], std::min(s.pitch_min, s.pitch), std::max(s.pitch_max, s.pitch));
    Vec3 up = v3(0, 0, 1);
    auto forward_at = [&](float degrees) { return in.heading * std::cos(degrees * DEG) + v3(0, 0, std::sin(degrees * DEG)); };
    if (mode == FIRST) {
        aim(p, forward_at(pitch));
        p.eye = in.anchor + up * (s.height * size) + in.heading * (s.eye_forward * size);
        return p;
    }
    Vec3 head = in.anchor + up * (s.height * size);
    Vec3 knee = in.anchor + up * (22.0f * size);
    Vec3 pivot = head - in.left * (s.side * size);
    float want = s.distance * size;
    if (!s.collide || !g_collide) {
        aim(p, forward_at(pitch));
        p.eye = pivot - p.forward * want;
        return p;
    }
    if (s.side != 0) {                              // the shoulder itself must not be behind a wall
        float t = ray_between(c, head, pivot);
        if (t >= 0) pivot = mix(head, pivot, std::max(0.0f, t - 0.25f));
    }
    // 1. The level between camera and character: the camera first swings up over what is in the way (what
    //    the game's own camera does: it raises its pitch and never comes closer), in steps, eased.
    static const float RAISE[] = {0, 9, 18, 28, 40, 52};
    float raise = RAISE[5];
    for (float r : RAISE) {
        float down = std::max(pitch - r, -80.0f);
        if (sees(c, pivot - forward_at(down) * want, head, knee) || down <= -80.0f) { raise = pitch - down; break; }
    }
    float& held = g_raise[mode];
    if (held < 0) held = raise;
    else if (raise > held) held = std::min(raise, held + 150.0f * in.dt);
    else held = std::max(raise, held - 35.0f * in.dt);
    aim(p, forward_at(std::max(pitch - held, -80.0f)));
    // 2. What is still in the way of the head (a wall behind the character, a narrow corridor): come closer,
    //    at once; go back out slowly, so that a pillar passing between does not make the picture jump.
    float use = want;
    float t = ray_between(c, pivot, pivot - p.forward * want);
    if (t >= 0) use = std::max(10.0f * size, t * want - 7.0f);
    float& pull = g_pull[mode];
    if (pull < 0 || use < pull) pull = use;
    else pull = std::min(use, pull + 240.0f * in.dt);
    use = pull;
    p.eye = pivot - p.forward * use;
    // 3. Never under the floor.  The ground query gives the top of whatever is under the point - over a wall
    //    its lid - so only a floor near the character's own counts: the camera is not lifted onto walls.
    float floor = ground_under(c, p.eye);
    if (floor > -1e5f && floor < in.anchor.z + 45.0f * size && p.eye.z < floor + 7.0f) p.eye.z = floor + 7.0f;
    return p;
}

// the transition's starting pose, kept relative to the character so that it moves along with it
void capture_from(const Pose& p, const Inputs& in) {
    Vec3 d = p.eye - in.anchor;
    g_from_offset = v3(dot(d, in.heading), dot(d, in.left), d.z);
    Pose h;
    aim(h, in.heading);
    Quat qh = quat_of(h.right, h.down, h.forward), qp = quat_of(p.right, p.down, p.forward);
    // relative = inverse(heading) * pose
    Quat inv = {qh.w, -qh.x, -qh.y, -qh.z};
    g_from_turn = {inv.w * qp.w - inv.x * qp.x - inv.y * qp.y - inv.z * qp.z, inv.w * qp.x + inv.x * qp.w + inv.y * qp.z - inv.z * qp.y,
                   inv.w * qp.y - inv.x * qp.z + inv.y * qp.w + inv.z * qp.x, inv.w * qp.z + inv.x * qp.y - inv.y * qp.x + inv.z * qp.w};
    g_from_fov = p.fov;
    g_from_near = p.near_plane;
    g_have_from = true;
}
Pose from_pose(const Inputs& in) {
    Pose p;
    p.eye = in.anchor + in.heading * g_from_offset.x + in.left * g_from_offset.y + v3(0, 0, g_from_offset.z);
    Pose h;
    aim(h, in.heading);
    Quat a = quat_of(h.right, h.down, h.forward), b = g_from_turn;
    Quat q = {a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z, a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
              a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x, a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w};
    frame_of(q, p.right, p.down, p.forward);
    p.fov = g_from_fov;
    p.near_plane = g_from_near;
    return p;
}

const char* const WARMUP = "warm-up (the picture is blanked)";
const char* g_last_fallback = "";

const char* fallback_reason(u32& camera, u32& object, int& slot) {
    camera = W(G_LOCAL_CAMERA);
    object = 0;
    slot = -1;
    if (!in_ram(camera, 0x180)) return "no camera";
    if (!W(G_WORLD)) return "no level";
    if (g_ram[G_LOADSCREEN_ACTIVE]) return "loading";
    if (g_ram[G_CUTSCENE_ACTIVE]) return "cutscene";
    // The warm-up after a load, a cutscene or a menu: the picture is blanked and its draw lists thrown
    // away while the level's textures stream in, and the count starts again while the stream is busy.
    // Offline the simulation tick stands still for its length while parts of the run pass go on, so its
    // length is simulation timing: it must be what it is in the overhead view.  The game's camera draws
    // (unseen) through it, asks for the textures it always asked for, and the view cuts in when the
    // picture comes back.
    if (W(G_WARMUP_FRAMES) != 0) return WARMUP;
    if (W(at(camera) + CAM_MODE) != 1) return "the game holds the camera (menu, dialogue, cutscene)";
    if (W(at(camera) + CAM_TRANSITION) != 0) return "camera reset";
    s32 alive = (s32)W(G_LOCAL_ALIVE_COUNT);
    if (alive < 1) return "no local player alive";
    if (alive > 1) return "more than one local player";
    slot = (s32)W(G_LOCAL_ALIVE);
    if (slot < 0 || slot > 3) return "no local player";
    object = W(G_PLAYER_OBJECT + (u32)slot * PLAYER_STRIDE);
    if (!in_ram(object, 0x600)) return "no player object";
    return nullptr;
}

// Returns true when a view is put in place for this pass.
bool begin_pass(Ctx* c) {
    read_options();
    g_passes++;
    View& v = g_view;
    int wanted = g_wanted.load();
    v.mode = wanted;
    v.frame = g_passes;
    v.tick = W(G_SIM_FRAME);
    v.active = false;
    v.fallback = false;
    v.fallback_why = "";
    v.hide_player = false;
    if (wanted == OVERHEAD && g_mode == OVERHEAD && g_t >= 1) {     // the game as it is: nothing is read, nothing is written
        v.shown = OVERHEAD;
        v.blend = 0;
        g_shown_valid = false;
        g_was_fallback = true;
        g_anchor_valid = false;
        return false;
    }
    u32 camera, object;
    int slot;
    const char* why = fallback_reason(camera, object, slot);
    if (why) {
        v.fallback = true;
        v.fallback_why = why;
        v.shown = OVERHEAD;
        v.blend = 0;
        v.have_player = false;
        g_fallback_frames++;
        g_last_fallback = why;
        g_was_fallback = true;
        g_shown_valid = false;
        g_anchor_valid = false;
        for (float& p : g_pull) p = -1;
        for (float& r : g_raise) r = -1;
        return false;
    }

    // ---- what the view is made from ----
    Inputs in;
    const u32 gm = G_CAMERA_MATRIX;
    in.game.right = v3(F(gm), F(gm + 12), F(gm + 24));
    in.game.down = v3(F(gm + 4), F(gm + 16), F(gm + 28));
    in.game.forward = v3(F(gm + 8), F(gm + 20), F(gm + 32));
    in.game.eye = v3(F(G_CAMERA_POS), F(G_CAMERA_POS + 4), F(G_CAMERA_POS + 8));
    float scale = F(G_PROJ_SCALE);
    in.game.fov = scale > 1 ? 2 * std::atan(477.5f / scale) / DEG : 50;
    in.game.near_plane = 18;
    // the heading comes from the camera's right vector, which lies in the ground plane whatever the pitch
    in.heading = normal(v3(-in.game.right.y, in.game.right.x, 0), v3(0, 1, 0));
    in.left = v3(-in.heading.y, in.heading.x, 0);
    in.yaw = std::atan2(in.heading.y, in.heading.x) / DEG;
    u32 drawn = game_drawn_object(c, object);
    u32 obj = at(drawn);
    in.feet = v3(F(obj + OBJ_POS), F(obj + OBJ_POS + 4), F(obj + OBJ_POS + 8));
    // facing: the camera is "behind the character" at yaw word 0x4000 - facing (Camera_followRecenter), and a
    // growing yaw word turns the camera clockwise seen from above (Ran: stick right, heading falls).  So the
    // character's heading is the camera's heading minus ((0x4000 - facing) - yaw word)
    float extent = F(obj + 0x20);
    in.size = extent > 20 && extent < 400 ? clampf(extent / 72.0f, 0.6f, 2.5f) : 1.0f;
    u16 yaw_word = (u16)W(at(camera) + CAM_YAW), facing_word = (u16)W(obj + OBJ_FACING);
    float turn = (float)(s16)(u16)(0x4000 - facing_word - yaw_word) * (360.0f / 65536.0f);
    in.facing = wrap_deg(in.yaw - turn);
    in.facing_dir = v3(std::cos(in.facing * DEG), std::sin(in.facing * DEG), 0);
    u32 pad_slot = W(at(camera) + CAM_PAD_SLOT);
    if (pad_slot > 3) pad_slot = (u32)slot;
    in.stick_x = F(G_PADS + pad_slot * PAD_STRIDE + PAD_RX);
    in.stick_y = F(G_PADS + pad_slot * PAD_STRIDE + PAD_RY);
    u32 ticks = v.tick - g_last_tick;
    if (g_was_fallback || ticks > 8) ticks = ticks ? 1 : 0;     // a level start, a long stall: no jump
    g_last_tick = v.tick;
    in.dt = (float)ticks / 60.0f;

    // "follow": the view turned from the game camera's heading toward where the character faces, eased.
    // Picture only - the stick still means what it means to the game's camera (fpview.h)
    {
        float want = g_set[wanted].follow > 0 ? wrap_deg(in.facing - in.yaw) * clampf(g_set[wanted].follow, 0, 1) : 0;
        if (g_was_fallback) g_turn = want;
        else g_turn += wrap_deg(want - g_turn) * (1 - std::exp(-in.dt * 5.0f));
        g_turn = wrap_deg(g_turn);
        if (g_turn != 0) {
            float a = (in.yaw + g_turn) * DEG;
            in.heading = v3(std::cos(a), std::sin(a), 0);
            in.left = v3(-in.heading.y, in.heading.x, 0);
        }
    }

    // the character's height, eased over steps and stairs (the game eases its look-at point the same way)
    if (!g_anchor_valid || std::fabs(in.feet.z - g_anchor_z) > 90) g_anchor_z = in.feet.z;
    else g_anchor_z += (in.feet.z - g_anchor_z) * (1 - std::exp(-in.dt * 14.0f));
    g_anchor_valid = true;
    in.anchor = v3(in.feet.x, in.feet.y, g_anchor_z);

    // ---- which view, and how far into it ----
    if (wanted != g_mode || g_was_fallback) {
        // start a transition from what is on screen now (the game's camera after a fallback)
        if (g_shown_valid && !g_was_fallback) capture_from(g_shown, in);
        else capture_from(in.game, in);
        // after a warm-up the picture comes back from black: the view is simply there
        bool cut = g_was_fallback && g_last_fallback == WARMUP;
        g_mode = wanted;
        g_t = g_ease_seconds > 0.001f && !cut ? 0 : 1;
        g_last_fallback = "";
        g_pull[g_mode] = -1;
        g_raise[g_mode] = -1;
    } else if (g_t < 1) {
        g_t = g_ease_seconds > 0.001f ? std::min(1.0f, g_t + in.dt / g_ease_seconds) : 1;
    }
    g_was_fallback = false;
    if (g_mode == OVERHEAD && g_t >= 1) {           // arrived back at the game's camera
        v.shown = OVERHEAD;
        v.blend = 0;
        g_shown_valid = false;
        return false;
    }

    // the stick looks up and down in views that allow it
    const ModeSettings& s = g_set[g_mode];
    if (g_mode != OVERHEAD && s.pitch_max > s.pitch_min && std::fabs(in.stick_y) > 0.05f) {
        // pad.ry is negative when the stick is pushed up (a byte of 0 is -1.0): up looks up
        g_pitch[g_mode] = clampf(g_pitch[g_mode] - in.stick_y * s.look_speed * in.dt, s.pitch_min - s.pitch, s.pitch_max - s.pitch);
    }

    if (float more = g_pitch_add.exchange(0); more != 0 && g_mode != OVERHEAD && s.pitch_max > s.pitch_min)
        g_pitch[g_mode] = clampf(g_pitch[g_mode] + more, s.pitch_min - s.pitch, s.pitch_max - s.pitch);

    Pose target = pose_of(c, g_mode, in);
    Pose shown = g_t >= 1 ? target : blend(from_pose(in), target, smooth(g_t));
    g_shown = shown;
    g_shown_valid = true;

    // ---- the View for whoever asks, and the call-outs ----
    v.shown = g_t >= 0.5f ? g_mode : OVERHEAD;
    v.blend = g_mode == OVERHEAD ? 1 - smooth(g_t) : smooth(g_t);
    v.active = true;
    v.eye = shown.eye;
    v.forward = shown.forward;
    v.right = shown.right;
    v.up = shown.down * -1.0f;
    v.fov = shown.fov;
    v.near_plane = shown.near_plane;
    v.far_plane = 1800;
    v.cull_far = s.far;
    v.stream_focus = shown.eye + shown.forward * 600.0f;
    v.hide_player = s.hide_player && g_t >= 0.5f;
    v.game_eye = in.game.eye; v.game_forward = in.game.forward; v.game_right = in.game.right; v.game_up = in.game.down * -1.0f;
    v.game_fov = in.game.fov;
    v.game_yaw = in.yaw;
    v.game_zoom = (int)W(at(camera) + CAM_ZOOM);
    v.game_yaw_word = yaw_word;
    v.have_player = true;
    v.slot = slot;
    v.player_object = object;
    v.drawn_object = drawn;
    v.player_pos = in.feet;
    v.head = in.anchor + v3(0, 0, g_set[FIRST].height * in.size);
    v.player_height = extent;
    v.head_from_pose = false;
    v.facing = in.facing;
    v.facing_dir = in.facing_dir;
    v.look_yaw = wrap_deg(in.yaw + g_turn);
    v.look_pitch = std::asin(clampf(shown.forward.z, -1, 1)) / DEG;
    for (const Callout& call : g_on_view) ((ViewFn)call.fn)(v, c, call.user);

    // ---- put it in place: the game's own functions build everything from it ----
    Pose put;
    put.eye = v.eye;
    put.forward = normal(v.forward, shown.forward);
    put.right = normal(cross(put.forward, v.up), shown.right);
    put.down = normal(cross(put.forward, put.right), shown.down);
    float fov = clampf(v.fov, 10, 120), near_plane = clampf(v.near_plane, 0.5f, 400);

    save_words();
    gfxrt::projection_args(g_game_args);
    // the second set of planes ("is this mesh wholly inside what the vertex program can draw without
    // its clip test") keeps its size in pixels: the game has 80 degrees there for a view of 50
    float second = 2 * std::atan(std::tan(40 * DEG) / std::tan(25 * DEG) * std::tan(fov * DEG / 2)) / DEG;
    u32 args[4] = {as_bits(fov), g_game_args[1], as_bits(std::min(second, 150.0f)), g_game_args[3]};
    gfxrt::set_depth_range(near_plane, v.far_plane);
    if (v.cull_far > 0) W(G_FAR_CLIP) = as_bits(v.cull_far);
    game_set_projection(c, args);
    game_set_view(c, put.eye, put.right, put.down, put.forward);
    // camera_buildFrustum moved the near plane by the game's 18
    W(PLANE_NEAR_D) = as_bits(F(PLANE_NEAR_D) + 18.0f - near_plane);
    W(PLANE80_NEAR_D) = as_bits(F(PLANE80_NEAR_D) + 18.0f - near_plane);
    game_scene_light(c);
    // the pass costs the virtual console no time: it draws more than the console's camera ever asked
    // for, and a frame that runs past its field makes the game step two ticks in the next
    if (g_free_pass) rt_unit_cost(c, 0);
    g_in_pass = true;
    g_active_frames++;

    // the local player's packets of this frame: which display-list buffer they go into
    u32 base = W(G_DL_BASE) & RAM_MASK;
    int fill = g_hidden[0].base == base ? 0 : g_hidden[1].base == base ? 1 : g_hidden[0].filled_at <= g_hidden[1].filled_at ? 0 : 1;
    g_hidden[fill].base = base;
    g_hidden[fill].size = W(G_DL_UNITS) * 8;
    g_hidden[fill].filled_at = g_passes;
    g_hidden[fill].draw_frame = W(G_DRAW_FRAME);
    g_hidden[fill].ranges.clear();
    g_hidden_fill = fill;

    if (g_log && g_passes % 60 == 0)
        fprintf(stderr, "view: %s t=%.2f tick %u eye %.1f %.1f %.1f fwd %.2f %.2f %.2f fov %.0f near %.0f | game eye %.1f %.1f %.1f yaw %.1f zoom %d | feet %.1f %.1f %.1f facing %.1f stick %.2f %.2f\n",
                NAMES[g_mode], g_t, v.tick, v.eye.x, v.eye.y, v.eye.z, v.forward.x, v.forward.y, v.forward.z, v.fov, v.near_plane, v.game_eye.x, v.game_eye.y,
                v.game_eye.z, v.game_yaw, v.game_zoom, v.player_pos.x, v.player_pos.y, v.player_pos.z, v.facing, in.stick_x, in.stick_y);
    return true;
}

void end_pass(Ctx* c) {
    rt_unit_cost(c, 4);
    g_in_pass = false;
    g_hidden_fill = -1;
    g_stream_frame = W(G_DRAW_FRAME);
    // gfx_rt's host-side copies (the 4:3 planes it keeps for the simulation's one reader, the
    // arguments it rebuilds from when the window changes shape) are brought back by the game's own
    // two functions; then the words themselves, byte for byte as they were
    gfxrt::set_depth_range(0, 0);
    Vec3 eye, right, down, forward;
    const u8* pos = saved_region(G_CAMERA_POS);
    const u8* m = saved_region(G_CAMERA_MATRIX);
    float f[12];
    memcpy(&eye, pos, 12);
    memcpy(f, m, 48);
    right = v3(f[0], f[3], f[6]); down = v3(f[1], f[4], f[7]); forward = v3(f[2], f[5], f[8]);
    memcpy(g_ram + G_FAR_CLIP, saved_region(G_FAR_CLIP), 4);
    game_set_projection(c, g_game_args);
    game_set_view(c, eye, right, down, forward);
    g_restore_differs += restore_words();
    game_scene_light(c);
}

void record_hidden(u32 lo, u32 hi) {
    if (g_hidden_fill < 0 || hi <= lo) return;
    g_hidden[g_hidden_fill].ranges.push_back({lo, hi});
}

bool dma_skip(u32 tag_address) {
    u32 a = tag_address & RAM_MASK;
    for (const Hidden& h : g_hidden) {
        if (!h.base || h.ranges.empty() || a < h.base || a - h.base >= h.size) continue;
        if (W(G_DRAW_FRAME) - h.draw_frame > 1) continue;
        for (const auto& r : h.ranges)
            if (a >= r.first && a < r.second) { g_hidden_packets++; return true; }
    }
    return false;
}

}  // namespace

// ---- the interface -----------------------------------------------------------------------------------
const View& view() { return g_view; }
void set_mode(int mode) { if (mode >= 0 && mode < MODE_COUNT) g_wanted = mode; }
int mode() { return g_wanted.load(); }
const char* mode_name(int mode) { return mode >= 0 && mode < MODE_COUNT ? NAMES[mode] : "?"; }
int mode_by_name(const char* name) {
    if (!name) return -1;
    for (int m = 0; m < MODE_COUNT; m++) if (!strcmp(name, NAMES[m])) return m;
    if (!strcmp(name, "fp") || !strcmp(name, "firstperson") || !strcmp(name, "first-person")) return FIRST;
    if (!strcmp(name, "third") || !strcmp(name, "behind")) return CHASE;
    if (!strcmp(name, "game") || !strcmp(name, "classic")) return OVERHEAD;
    return -1;
}
void cycle(int step) { g_wanted = ((g_wanted.load() + step) % MODE_COUNT + MODE_COUNT) % MODE_COUNT; }

bool setting(const char* key, const char* value) {
    if (!key || !value) return false;
    std::lock_guard<std::mutex> hold(g_settings_lock);
    if (!strcmp(key, "view")) { int m = mode_by_name(value); if (m < 0) return false; g_wanted = m; return true; }
    if (!strcmp(key, "view.ease")) { g_ease_seconds = clampf((float)atof(value), 0, 3); return true; }
    if (strncmp(key, "view.", 5)) return false;
    const char* dot2 = strchr(key + 5, '.');
    if (!dot2) return false;
    int m = mode_by_name(std::string(key + 5, dot2 - key - 5).c_str());
    if (m <= OVERHEAD) return false;            // the overhead view is the game's: it has no settings
    ModeSettings& s = g_set[m];
    std::string name = dot2 + 1;
    float number = (float)atof(value);
    bool yes = !strcmp(value, "yes") || !strcmp(value, "on") || !strcmp(value, "1") || !strcmp(value, "true");
    if (name == "fov") s.fov = clampf(number, 20, 110);
    else if (name == "near") s.near_plane = clampf(number, 1, 100);
    else if (name == "distance") s.distance = clampf(number, 0, 900);
    else if (name == "height") s.height = clampf(number, 0, 400);
    else if (name == "eye_height") s.height = clampf(number, 0, 400);
    else if (name == "side") s.side = clampf(number, -200, 200);
    else if (name == "pitch") s.pitch = clampf(number, -89, 89);
    else if (name == "pitch_min") s.pitch_min = clampf(number, -89, 89);
    else if (name == "pitch_max") s.pitch_max = clampf(number, -89, 89);
    else if (name == "eye_forward") s.eye_forward = clampf(number, -50, 50);
    else if (name == "look_speed") s.look_speed = clampf(number, 0, 720);
    else if (name == "far") s.far = clampf(number, 0, 1800);
    else if (name == "follow") s.follow = clampf(number, 0, 1);
    else if (name == "head") s.head_pose = !strcmp(value, "pose");
    else if (name == "hide_player") s.hide_player = yes;
    else if (name == "collide") s.collide = yes;
    else return false;
    return true;
}
const char* settings_text() {
    std::lock_guard<std::mutex> hold(g_settings_lock);
    char line[512];
    g_settings_text.clear();
    snprintf(line, sizeof line, "view = %s          # the camera: overhead (the game's own), action, chase, shoulder, first.  V switches while the game runs\n",
             NAMES[g_wanted.load()]);
    g_settings_text += line;
    snprintf(line, sizeof line, "view.ease = %.2f       # seconds a change of view takes\n", g_ease_seconds);
    g_settings_text += line;
    for (int m = 1; m < MODE_COUNT; m++) {
        const ModeSettings& s = g_set[m];
        snprintf(line, sizeof line, "view.%s.fov = %g\nview.%s.near = %g\nview.%s.far = %g\nview.%s.height = %g\n", NAMES[m], s.fov, NAMES[m], s.near_plane,
                 NAMES[m], s.far, NAMES[m], s.height);
        g_settings_text += line;
        if (m != FIRST) {
            snprintf(line, sizeof line, "view.%s.distance = %g\nview.%s.side = %g\nview.%s.collide = %s\n", NAMES[m], s.distance, NAMES[m], s.side, NAMES[m],
                     s.collide ? "yes" : "no");
            g_settings_text += line;
        } else {
            snprintf(line, sizeof line, "view.%s.eye_forward = %g\nview.%s.hide_player = %s\n", NAMES[m], s.eye_forward, NAMES[m], s.hide_player ? "yes" : "no");
            g_settings_text += line;
        }
        snprintf(line, sizeof line, "view.%s.pitch = %g\nview.%s.pitch_min = %g\nview.%s.pitch_max = %g\nview.%s.look_speed = %g\nview.%s.follow = %g\n", NAMES[m],
                 s.pitch, NAMES[m], s.pitch_min, NAMES[m], s.pitch_max, NAMES[m], s.look_speed, NAMES[m], s.follow);
        g_settings_text += line;
    }
    return g_settings_text.c_str();
}

void add_pitch(float degrees) {
    float old = g_pitch_add.load();
    while (!g_pitch_add.compare_exchange_weak(old, old + degrees)) {}
}

void on_view(ViewFn fn, void* user) { g_on_view.push_back({(void*)fn, user}); }
void on_drawn(DrawnFn fn, void* user) { g_on_drawn.push_back({(void*)fn, user}); }
float ray(Ctx* c, Vec3 from, Vec3 to) { return ray_between(c, from, to); }
float ground(Ctx* c, Vec3 p) { return ground_under(c, p); }

void install() {
    rt_dma_skip = dma_skip;
    g_next_frame_hook = rt_frame_hook;      // gfx_rt's; ours only notes the time (view-timing) and hands on
    rt_frame_hook = timing_frame_hook;
}
void figures(uint64_t& active_frames, uint64_t& fallback_frames, uint64_t& hidden_packets) {
    active_frames = g_active_frames; fallback_frames = g_fallback_frames; hidden_packets = g_hidden_packets;
}

}  // namespace fpview

// ---- the functions the translation calls ------------------------------------------------------------
using namespace fpview;

// tasks_call(excludeMask, includeMask): (0, 1) is the draw pass of a displayed frame
void fn_0019e798(Ctx* c) {
    bool draw_pass = (s32)c->r[4] == 0 && (s32)c->r[5] == 1;
    if (!draw_pass || g_in_pass) { orig_0019e798(c); return; }
    static u64 last_begin = 0;
    static const bool timing = rt_option("view-timing") != nullptr;    // a line for every frame longer than 1.2 fields of the virtual clock
    u64 t0 = rt_cycles();
    bool active = begin_pass(c);
    u64 t1 = rt_cycles();
    orig_0019e798(c);
    if (timing) {
        u64 t2 = rt_cycles();
        const double field = 4920115.0;
        if (last_begin && t0 - last_begin > 5900000ull)
            fprintf(stderr, "view-timing: tick %u frame %llu: %.2f fields since the last pass began: that pass %.3f, to the texture stream %.3f, in it %.3f, "
                    "end of frame up to gfx_beginFrame %.3f, in gfx_beginFrame %.3f, frame step + pads + run pass %.3f; view %s\n",
                    W(G_SIM_FRAME), (unsigned long long)g_passes, (double)(t0 - last_begin) / field, (double)(g_time_pass_end - last_begin) / field,
                    (double)(g_time_stream_in - g_time_pass_end) / field, (double)(g_time_stream_out - g_time_stream_in) / field,
                    (double)(g_time_begin_in - g_time_stream_out) / field, (double)(g_time_begin_out - g_time_begin_in) / field,
                    (double)(t0 - g_time_begin_out) / field, active ? NAMES[g_mode] : "game");
        last_begin = t0;
        g_time_pass_end = t2;
        (void)t1;
    }
    for (const Callout& call : g_on_drawn) ((DrawnFn)call.fn)(g_view, c, call.user);
    if (active) end_pass(c);
}

// camera_updateFocus: g_cameraFocus = camera position + forward x 600, from the game's own camera
void fn_0018a520(Ctx* c) {
    if (!g_in_pass) { orig_0018a520(c); return; }
    u8 pos[12], m[0x30];
    memcpy(pos, g_ram + G_CAMERA_POS, 12);
    memcpy(m, g_ram + G_CAMERA_MATRIX, 0x30);
    memcpy(g_ram + G_CAMERA_POS, saved_region(G_CAMERA_POS), 12);
    memcpy(g_ram + G_CAMERA_MATRIX, saved_region(G_CAMERA_MATRIX), 0x30);
    orig_0018a520(c);
    memcpy(g_ram + G_CAMERA_POS, pos, 12);
    memcpy(g_ram + G_CAMERA_MATRIX, m, 0x30);
}

// worldtex_stream: the cells round the focus are kept loaded; the picture needs those round the drawn view's
void fn_0017d830(Ctx* c) {
    struct Timed { Timed() { g_time_stream_in = rt_cycles(); } ~Timed() { g_time_stream_out = rt_cycles(); } } timed;
    bool mine = g_stream_frame == W(G_DRAW_FRAME) && g_view.active;
    // The main loop counts displayed frames in a row with the "terrain late" flag up (g_terrainLateFrames
    // 0x5060a8) and after 21 asks for half the display rate, to give the stream time.  A view along the
    // ground has chunks in sight whose texture cell is outside the 3 x 3 the game keeps loaded: the flag
    // never drops and the game would run at two ticks a picture for as long as they are in sight.  The
    // count is held at nothing while a view is drawn (it is read by the main loop only).
    if (mine && g_hold_rate) W(0x5060A8) = 0;
    if (!g_stream_follows || !mine) { orig_0017d830(c); return; }
    u8 focus[12];
    memcpy(focus, g_ram + G_CAMERA_FOCUS, 12);
    W(G_CAMERA_FOCUS) = as_bits(g_view.stream_focus.x);
    W(G_CAMERA_FOCUS + 4) = as_bits(g_view.stream_focus.y);
    W(G_CAMERA_FOCUS + 8) = as_bits(g_view.stream_focus.z);
    orig_0017d830(c);
    memcpy(g_ram + G_CAMERA_FOCUS, focus, 12);
}

// Player_draw: everything it does, it does; in first person its packets are left out of the stream
void fn_001a46c0(Ctx* c) {
    u32 self = (u32)c->r[4];
    if (!g_in_pass || !g_view.hide_player || (self != g_view.player_object && self != g_view.drawn_object)) { orig_001a46c0(c); return; }
    u32 before = W(G_DL_CURSOR) & RAM_MASK;
    orig_001a46c0(c);
    record_hidden(before, W(G_DL_CURSOR) & RAM_MASK);
}

// Camera_followZoomInput: held off only when asked (--opt view-zoom=off) and a view looks with the stick
void fn_00205880(Ctx* c) {
    int m = g_wanted.load();
    if (g_zoom_off && m != OVERHEAD && g_set[m].pitch_max > g_set[m].pitch_min) return;
    orig_00205880(c);
}
