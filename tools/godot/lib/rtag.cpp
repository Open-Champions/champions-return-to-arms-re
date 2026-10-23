// rtag.cpp - the library behind rtag.h.
//
// The pieces are tools/recomp's, unchanged (a snapshot of them: see ../build.py):
//   rta::run()                the translated game on the runtime's threads (rt/)
//   app::Sink (pipeline.h)    the picture path: the runtime's sink copies on the game's thread,
//                             a decoder thread runs VIF1 / VU1 / the GS model
//   render::Renderer          gives one FrameList per vertical blank
//   render::GlBackend         optional: draws the lists off screen (gl_offscreen.h makes the context)
//   sound_rta.cpp             the sound core; its "device" is the host (audio_host.inc)
// What is new here is only the hand-over: the game's thread stands at every blank until the
// host lets it go (Gate), finished frames wait in a short queue for the host (Outbox), and
// the end of the run stops the machine instead of the process (host_godot.cpp).
#include "rtag.h"
#include <cstddef>

#include "app_rt.h"
#include "backend_gl.h"
#include "fpview.h"
#include "gfx_rt.h"
#include "gl_offscreen.h"
#include "pipeline.h"
#include "png_write.h"
#include "scene_export.h"
#include "skeleton_export.h"
#include "scene_tap.h"
#if __has_include("fpcontrols.h") && !defined(RTAG_NO_CONTROLS)
#include "fpcontrols.h"
#define RTAG_HAVE_CONTROLS 1
#endif
// the souls-style combat mode (tools/recomp/app/soulscombat.h): build.py defines RTAG_HAVE_SOULS when the snapshot has
// app/soulscombat.cpp (it needs the controls: the lock-on)
#if defined(RTAG_HAVE_SOULS) && defined(RTAG_HAVE_CONTROLS)
#include "soulscombat.h"
#ifdef RTAG_HAVE_NET2
#include "../net/netdrv.h"
#include "../net2/hooks.h"
#endif
#else
#undef RTAG_HAVE_SOULS
#endif
// aiming by looking (tools/recomp/app/fpaim.h, docs/issues/native-first-person-aim.md): build.py defines RTAG_HAVE_AIM
// when the snapshot has app/fpaim.cpp (it needs the controls: the look's pitch, set_aim)
#if defined(RTAG_HAVE_AIM) && defined(RTAG_HAVE_CONTROLS)
#include "fpaim.h"
#ifdef RTAG_HAVE_NET2
#include "../net/netdrv.h"
#include "../net2/hooks.h"
#endif
#else
#undef RTAG_HAVE_AIM
#endif
// the world for a camera inside it (tools/recomp/app/fpworld.h): build.py defines RTAG_HAVE_WORLD when the snapshot has
// app/fpworld.cpp and the translation wraps its three functions
#ifdef RTAG_HAVE_WORLD
#include "fpworld.h"
#include "worldfill.h"
#endif

// the tester's kit (tools/recomp/app/testerkit.h): build.py defines RTAG_HAVE_TESTERKIT when the snapshot has it
#ifdef RTAG_HAVE_TESTERKIT
#include "testerkit.h"
#endif

#include <atomic>
#include <cmath>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <dirent.h>
#include <mutex>
#include <string>
#ifdef _WIN32
#include <direct.h>                                     // _mkdir
#include <windows.h>                                    // GetProcessTimes (the library for Windows: build_lib_win.py)
#else
#include <sys/resource.h>
#endif
#include <sys/stat.h>
#include <thread>
#include <vector>

namespace rta { namespace snd { void host_audio_pull(int16_t* stereo, size_t frames, float gain); } }
void rtag_host_set_quit(void (*fn)(int code));          // host_godot.cpp

using app::now_ms;
using render::FrameList;

namespace {

static_assert(sizeof(rtag_vertex) == sizeof(render::Vertex), "rtag_vertex is render::Vertex");
static_assert(offsetof(rtag_vertex, s) == offsetof(render::Vertex, s) && offsetof(rtag_vertex, r) == offsetof(render::Vertex, r) &&
              offsetof(rtag_vertex, fog) == offsetof(render::Vertex, fog), "rtag_vertex is render::Vertex");

const uint32_t G_SIM_FRAME = 0x44FDCC;                  // symbols/engine.tsv: g_simFrame

#ifdef _WIN32
double cpu_ms() {
    FILETIME created, ended, kernel, user;
    if (!GetProcessTimes(GetCurrentProcess(), &created, &ended, &kernel, &user)) return 0;
    auto ms = [](const FILETIME& t) { return (double)(((uint64_t)t.dwHighDateTime << 32) | t.dwLowDateTime) / 10000.0; };
    return ms(kernel) + ms(user);
}
static int make_dir(const char* path) { return _mkdir(path); }
#else
static int make_dir(const char* path) { return mkdir(path, 0755); }
double cpu_ms() {
    rusage u;
    getrusage(RUSAGE_SELF, &u);
    return (u.ru_utime.tv_sec + u.ru_stime.tv_sec) * 1000.0 + (u.ru_utime.tv_usec + u.ru_stime.tv_usec) / 1000.0;
}
#endif
#ifdef _WIN32
// the C library's stat() has a 32-bit size here and fails on a file over 2 GB (the disc image): the 64-bit one
bool file_exists(const std::string& path) { struct _stat64 st; return _stat64(path.c_str(), &st) == 0; }
#else
bool file_exists(const std::string& path) { struct stat st; return stat(path.c_str(), &st) == 0; }
#endif
void say(const std::string& line) { fprintf(stderr, "rtag: %s\n", line.c_str()); fflush(stderr); }

// ---- the gate: the game's thread stands at a blank until it is let go ----------------------
struct Gate {
    std::mutex lock;
    std::condition_variable changed;
    long credits = 0;
    bool open = false;                  // rtag_run(< 0): never waits
    void wait() {
        std::unique_lock<std::mutex> hold(lock);
        changed.wait(hold, [this] { return open || credits > 0; });
        if (!open) credits--;
    }
    void grant(long n) { { std::lock_guard<std::mutex> hold(lock); credits += n; if (credits > 4) credits = 4; } changed.notify_all(); }
    void set_open(bool on) { { std::lock_guard<std::mutex> hold(lock); open = on; } changed.notify_all(); }
};

// One finished frame on its way to the host.
struct OutFrame {
    FrameList list;
    std::vector<uint8_t> picture;
    int picture_w = 0, picture_h = 0;
    std::vector<std::string> shots, commands;
    uint32_t sim_tick = 0, flags = 0;
    rtag_view view;
    scene::Frame scene;
    double ready_ms = 0;                // when the decoder finished it (rtag_frame_age_ms)
    double released_ms = 0;             // when the game was let go into the frame it shows (the controller read then)
};

struct Note { uint64_t number; uint32_t sim_tick, flags; std::vector<std::string> shots, commands; rtag_view view; double released_ms = 0; };

struct Machine;
Machine* g_m;
std::string g_report_told;                              // testerkit::start's words about a crash report of the run before

// The sink of the picture path with the gate behind it, and what travels beside a frame.
struct GateSink : app::Sink {
    Gate gate;
    std::mutex notes_lock;
    std::deque<Note> notes;                             // game's thread -> decoder
    std::mutex shots_lock;
    std::vector<std::string> shots_asked;               // by the script, at this blank
    std::vector<std::string> commands_asked;            // "app ..." lines that are the host's
    void vblank(unsigned field, uint64_t number) override;
    void vif1(const uint32_t* words, size_t count) override;
    std::vector<uint32_t> scene_codes;
    // The view a frame is drawn with (fpview's call-out, when a draw pass has returned), and the view of the list
    // that is being sent: a frame's packets go out at the start of the next frame, after the blank that follows its
    // draw pass, so the view taken at the first transfer after a blank is that of the list the next blank closes.
    rtag_view drawn_view, sent_view;
    bool first_transfer = true;
    double last_release_ms = 0;                         // when the gate last let the game go: the frame being made began then
    bool take(uint64_t number, Note& out) {
        std::lock_guard<std::mutex> hold(notes_lock);
        bool found = false;
        while (!notes.empty() && notes.front().number <= number) {
            for (auto& s : notes.front().shots) out.shots.push_back(s);
            for (auto& s : notes.front().commands) out.commands.push_back(s);
            out.number = notes.front().number; out.sim_tick = notes.front().sim_tick; out.flags = notes.front().flags;
            out.view = notes.front().view;
            out.released_ms = notes.front().released_ms;
            notes.pop_front();
            found = true;
        }
        return found;
    }
};

struct Pads : rta::PadSource {
    std::mutex lock;
    rtag_pad held[2] = {{0, 128, 128, 128, 128}, {0, 128, 128, 128, 128}};
    std::atomic<bool> quit{false};
    std::atomic<uint32_t> rumbles{0};
    std::atomic<bool> controls_on{true};
    std::mutex hud_lock;
    rtag_controls hud;
    bool have_hud = false;
    void read(unsigned port, uint64_t blank, rta::PadState& state) override {
        if (quit) apprt::finish(0);                     // rtag_stop(): end from the game's thread
        state = apprt::script_pad(port);
        if (port > 1) return;
        rtag_pad p;
        { std::lock_guard<std::mutex> hold(lock); p = held[port]; }
        state.buttons |= p.buttons;
        if (state.lx == 128 && state.ly == 128) { state.lx = p.lx; state.ly = p.ly; }
        if (state.rx == 128 && state.ry == 128) { state.rx = p.rx; state.ry = p.ry; }
#ifdef RTAG_HAVE_TESTERKIT
        struct Record { ~Record() { if (port == 0) testerkit::pad(blank, state); } unsigned port; uint64_t blank; rta::PadState& state; } record{port, blank, state};
#endif
#ifdef RTAG_HAVE_CONTROLS
        // The views that look along the ground: stick and pointer are the look (the game camera's yaw word), the
        // character is turned to it; in the overhead views nothing changes (fpcontrols.h; as app_main.cpp does it).
        // Not while another machine's rows are replayed: the input is then given whole.
        if (port == 0) {
            static const bool replayed = apprt::replaying();
            const fpview::View& v = fpview::view();
            fpcontrols::set_view(replayed || !controls_on ? 0 : fpview::mode(), v.active && !v.fallback, v.look_pitch);
            fpcontrols::translate(blank, state);
            if (float pitch = fpcontrols::take_pitch(); pitch != 0) fpview::add_pitch(pitch);
#ifdef RTAG_HAVE_SOULS
            soulscombat::blank(blank);          // the souls-style combat mode (soulscombat.h): off unless asked for; as app_main.cpp
#endif
#ifdef RTAG_HAVE_AIM
            fpaim::blank(blank);                // aiming by looking (fpaim.h): off unless asked for; as app_main.cpp
#endif
            const fpcontrols::Hud& h = fpcontrols::hud();
            rtag_controls o;
            memset(&o, 0, sizeof o);
            o.struct_size = sizeof o; o.tick = h.tick; o.blank = h.blank; o.view = h.view;
            o.look = h.look; o.playing = h.playing; o.ranged = h.ranged; o.aligning = h.aligning; o.reticle = h.reticle; o.usable = h.usable;
            o.wants_pointer = fpcontrols::wants_pointer();
            o.slot = h.slot; o.player = h.player; o.x = h.x; o.y = h.y; o.z = h.z;
            o.look_heading = h.look_heading; o.look_pitch = h.look_pitch; o.facing = h.facing; o.facing_error = h.facing_error;
            o.state = h.state; o.weapon_class = h.weapon_class;
            auto mark = [](rtag_mark& to, const fpcontrols::Mark& from) {
                to.valid = from.valid; to.object = from.object; to.x = from.x; to.y = from.y; to.z = from.z;
                to.distance = from.distance; to.bearing = from.bearing; to.hp = from.hp; to.hp_max = from.hp_max;
            };
            mark(o.melee, h.melee); mark(o.shot, h.shot); mark(o.locked, h.locked);
            o.usable_kind = h.usable_kind; o.usable_fade = h.usable_fade; o.usable_object = h.usable_object;
            o.usable_x = h.usable_x; o.usable_y = h.usable_y; o.usable_z = h.usable_z; o.usable_bearing = h.usable_bearing;
            snprintf(o.usable_text, sizeof o.usable_text, "%s", h.usable_text);
            o.threat_count = h.threat_count < 16 ? h.threat_count : 16; o.behind = h.behind;
            for (int k = 0; k < o.threat_count; k++) {
                const fpcontrols::Threat& t = h.threats[k];
                o.threats[k] = {t.object, t.x, t.y, t.z, t.distance, t.bearing, (uint8_t)t.targets_me, (uint8_t)t.attacking, (uint8_t)t.in_view, 0};
            }
            o.swings = h.swings; o.hits_dealt = h.hits_dealt; o.hits_taken = h.hits_taken; o.deaths = h.deaths; o.respawns = h.respawns;
            o.last_hit_bearing = h.last_hit_bearing; o.last_hit_amount = h.last_hit_amount;
            std::lock_guard<std::mutex> hold(hud_lock);
            hud = o;
            have_hud = true;
        }
#else
        (void)blank;
#endif
    }
    void rumble(unsigned, uint8_t, uint8_t) override { rumbles++; }
};

struct Machine {
    // configuration (copies)
    std::string disc, data, workspace, elf, script;
    int lists = 1, picture_w = 0, picture_h = 0, every_frame = 0, samples = 0, anisotropy = 1, mipmaps = 0, sound = 0, scene3d = 0;
    double aspect = 4.0 / 3.0, gain = 1.0;
    std::vector<std::string> args;
    std::vector<char*> argv;

    render::Renderer renderer;
    GateSink sink;
#ifdef RTAG_HAVE_WORLD
    std::mutex fill_lock;
    std::shared_ptr<const render::FillLevel> fill_held;     // what rtag_fill_get handed out last
#endif
    Pads pads;
    rta::Hooks hooks;
    double waited_downstream_ms = 0;
    // the library's own renderer (decoder's thread)
    render::GlBackend* backend = nullptr;
    bool backend_failed = false;
    // decoder -> host
    enum { DEPTH = 3 };
    std::mutex lock;
    std::condition_variable changed;
    std::deque<OutFrame*> ready;
    std::vector<OutFrame*> spare;
    OutFrame* held = nullptr;                           // the frame the host is looking at
    // the host's view of it
    rtag_frame view;
    rtag_scene scene_view;
    std::vector<rtag_draw> draws;
    std::vector<rtag_texture> textures;
    std::vector<rtag_texture_name> texture_names;      // parallel to textures (rtag_texture_names)
    std::vector<rtag_target> targets;
    std::vector<const char*> shot_names, command_names;
    // the end
    bool hud_text_off = false;
    std::atomic<bool> ended{false};
    std::atomic<int> exit_code{0};
    // the library's own clock (rtag_run)
    std::atomic<double> run_hz{0};
    std::thread clock;
    std::atomic<bool> clock_on{false};
    // figures
    double start_ms = 0, start_cpu = 0;
    std::atomic<uint64_t> frames_out{0}, frames_taken{0}, vertices{0}, commands{0}, shots_written{0};
    double backend_ms = 0;                              // decoder's thread: the library's own OpenGL calls and read-backs
    double take_ms = 0;                                 // ... the scene and the skeletons handed over (scene::take)
    std::string info;
};

void GateSink::vblank(unsigned field, uint64_t number) {
    Note note;
    note.number = number;
    note.released_ms = last_release_ms;
    const uint8_t* ram = rta::memory();
    if (ram) {
        memcpy(&note.sim_tick, ram + G_SIM_FRAME, 4);
        note.flags = 0;
    }
    note.view = sent_view;
    first_transfer = true;
#ifdef RTAG_HAVE_TESTERKIT
    testerkit::blank(number, ram);                      // the tick log of a report (testerkit.h)
#endif
    { std::lock_guard<std::mutex> hold(shots_lock); note.shots.swap(shots_asked); note.commands.swap(commands_asked); }
    { std::lock_guard<std::mutex> hold(notes_lock); notes.push_back(std::move(note)); }
    if (g_m->scene3d) scene::at_blank(rta::memory(), number);
    app::Sink::vblank(field, number);                   // hands the batch to the decoder
    gate.wait();                                        // the host lets the next frame go; the controller is read after this
    last_release_ms = now_ms();
}

void GateSink::vif1(const uint32_t* words, size_t count) {
    if (first_transfer) { first_transfer = false; sent_view = drawn_view; }
    if (g_m->scene3d) {                                 // the camera these packets were made with goes ahead of them
        scene::before_transfer(rta::memory(), scene_codes);
        if (!scene_codes.empty()) app::Sink::vif1(scene_codes.data(), scene_codes.size());
    }
    app::Sink::vif1(words, count);
}

// fpview's call-out, on the game's thread: a draw pass has returned, its camera still in place.
void view_drawn(const fpview::View& v, Ctx* c, void*) {
#ifdef RTAG_HAVE_CONTROLS
    // the strafe mode (the fix set's section, when the game has it), asked for by the controls and sent through the
    // section's own sender from the draw pass - as tools/recomp/app/app_main.cpp does; never while rows are replayed
    {
        static const bool replayed = apprt::replaying();
        int mode = fpcontrols::take_strafe_send();
        if (mode >= 0 && !replayed && g_m->pads.controls_on) apprt::call_game(c, fpcontrols::STRAFE_SENDER, (uint32_t)mode);
#ifdef RTAG_HAVE_AIM
        // aiming by looking: this machine's aim, by game message 4 (fpaim.h), as app_main.cpp
        if (!replayed) fpaim::drawn(c, v.mode, g_m->pads.controls_on && v.active && !v.fallback && v.shown == v.mode, v.look_pitch);
#endif
    }
#else
    (void)c;
#endif
    rtag_view& o = g_m->sink.drawn_view;
    memset(&o, 0, sizeof o);
    o.mode = v.mode; o.shown = v.shown; o.blend = v.blend;
    o.active = v.active; o.fallback = v.fallback; o.hide_player = v.hide_player; o.have_head = v.head_from_pose;
    snprintf(o.fallback_why, sizeof o.fallback_why, "%s", v.fallback_why ? v.fallback_why : "");
    auto put = [](float* to, const fpview::Vec3& from) { to[0] = from.x; to[1] = from.y; to[2] = from.z; };
    put(o.eye, v.eye); put(o.forward, v.forward); put(o.up, v.up); put(o.right, v.right);
    o.fov = v.fov;
    put(o.head, v.head);
    o.yaw = std::atan2(v.forward.y, v.forward.x);
    o.near_plane = v.near_plane; o.far_plane = v.far_plane;
    put(o.player, v.player_pos);
    o.facing = v.facing; o.look_pitch = v.look_pitch;
    o.have_player = v.have_player; o.valid = 1;
    o.tick = v.tick;
    if (!v.active) {
        // No view of fpview's is in place (overhead; a cutscene, a dialogue, a menu): the frame was drawn with the
        // game's own camera, and that is the camera it carries - read where camera_setView left it (g_cameraPos
        // 0x44f038; g_cameraMatrix 0x44f110, whose columns are the camera's right, down, forward in the world;
        // g_projScale 0x44f108 = 477.5 / tan(fov / 2)).
        if (const uint8_t* ram = rta::memory()) {
            float pos[3], m[9], scale;
            memcpy(pos, ram + 0x44F038, 12); memcpy(m, ram + 0x44F110, 36); memcpy(&scale, ram + 0x44F108, 4);
            for (int a = 0; a < 3; a++) { o.eye[a] = pos[a]; o.right[a] = m[a * 3]; o.up[a] = -m[a * 3 + 1]; o.forward[a] = m[a * 3 + 2]; }
            if (scale > 1.0f) o.fov = 2.0f * std::atan(477.5f / scale) * 57.29578f;
            o.yaw = std::atan2(o.forward[1], o.forward[0]);
            o.near_plane = 18.0f; o.far_plane = 1800.0f;
        }
    }
    if (g_m->scene3d) scene::drawn(rta::memory(), v.near_plane, v.far_plane);
}

void app_command(const std::string& text, uint64_t frame) {
    std::vector<std::string> w;
    for (size_t at = 0; at < text.size();) {
        while (at < text.size() && isspace((unsigned char)text[at])) at++;
        size_t end = at;
        while (end < text.size() && !isspace((unsigned char)text[end])) end++;
        if (end > at) w.push_back(text.substr(at, end - at));
        at = end;
    }
    if (w.empty()) return;
    if (w[0] == "shot" && w.size() >= 2) {
        std::lock_guard<std::mutex> hold(g_m->sink.shots_lock);
        g_m->sink.shots_asked.push_back(text.substr(text.find(w[1])));
    } else if (w[0] == "view" && w.size() >= 2) {       // app view NAME | app view set KEY VALUE (as the native application's)
        // the key as the native application takes it ("view.first.pitch"); a bare one ("first.pitch") is given its "view."
        if (w[1] == "set" && w.size() >= 4) {
            std::string key = w[2].compare(0, 5, "view.") == 0 ? w[2] : "view." + w[2];
            if (!rtag_set_option(key.c_str(), w[3].c_str())) say("not a view setting: " + w[2]);
        }
        else if (!rtag_set_option("view", w[1].c_str())) say("no such view: " + w[1]);
    } else if (w[0] == "gamehud" && w.size() >= 2) {
        rtag_set_option("game_hud", w[1].c_str());
    } else if (w[0] == "gamehudtext" && w.size() >= 2) {
        if (!rtag_set_option("game_hud_text", w[1].c_str())) say("this library cannot leave the game's boss meter, message and prompt out");
    } else if (w[0] == "option" && w.size() >= 3) {     // app option KEY VALUE: rtag_set_option from a script
        if (!rtag_set_option(w[1].c_str(), w[2].c_str())) say("option refused: " + w[1] + " " + w[2]);
#ifdef RTAG_HAVE_CONTROLS
    } else if (w[0] == "fpc" && w.size() >= 2) {        // the look controls' own lines (fpcontrols.h), as the native application's
        printf("[frame %llu] fpc: %s\n", (unsigned long long)frame, fpcontrols::command(text.substr(text.find(w[1])), frame).c_str());
        fflush(stdout);
#endif
#ifdef RTAG_HAVE_SOULS
    } else if (w[0] == "souls") {                       // app souls info | on | off | lock | set NAME VALUE (soulscombat.h), as the native application's
        printf("[frame %llu] %s\n", (unsigned long long)frame, soulscombat::command(w.size() >= 2 ? text.substr(text.find(w[1])) : std::string()).c_str());
        fflush(stdout);
#endif
#ifdef RTAG_HAVE_AIM
    } else if (w[0] == "aim") {                         // app aim info | on | off (fpaim.h), as the native application's
        printf("[frame %llu] %s\n", (unsigned long long)frame, fpaim::command(w.size() >= 2 ? text.substr(text.find(w[1])) : std::string()).c_str());
        fflush(stdout);
#endif
#ifdef RTAG_HAVE_WORLD
    } else if (w[0] == "world" && w.size() >= 2) {      // app world info | app world set KEY VALUE (fpworld.h), as the native application's
        if (w[1] == "set" && w.size() >= 4) { if (!fpworld::setting(w[2].c_str(), w[3].c_str())) say("not a world setting: " + w[2]); }
        else printf("[frame %llu] %s\n", (unsigned long long)frame, fpworld::info());
        fflush(stdout);
    } else if (w[0] == "fill") {                        // app fill: what rtag_fill_get hands a host now
        rtag_fill f;
        if (rtag_fill_get(&f)) {
            unsigned ceilings = 0, skirts = 0, rims = 0;
            for (uint32_t k = 0; k < f.mesh_count; k++) (f.meshes[k].kind == RTAG_FILL_CEILING ? ceilings : f.meshes[k].kind == RTAG_FILL_SKIRT ? skirts : rims)++;
            printf("[frame %llu] fill: level %s, serial %llu, %u vertices (%u triangles), %u meshes (%u ceiling, %u skirt, %u rim), bounds %.0f %.0f %.0f .. %.0f %.0f %.0f\n",
                   (unsigned long long)frame, f.level, (unsigned long long)f.serial, f.vertex_count, f.vertex_count / 3, f.mesh_count, ceilings, skirts, rims,
                   f.bounds[0], f.bounds[1], f.bounds[2], f.bounds[3], f.bounds[4], f.bounds[5]);
        } else printf("[frame %llu] fill: none\n", (unsigned long long)frame);
        fflush(stdout);
#endif
    } else if (w[0] == "stats") {
        printf("[frame %llu] rtag: %s\n", (unsigned long long)frame, rtag_info());
        fflush(stdout);
#ifdef RTAG_HAVE_TESTERKIT
    } else if (w[0] == "report" && w.size() >= 2 && w[1] == "crash") {
        testerkit::command(text);                       // the crash handler's test (RTA_TESTERKIT_CRASH=1); the box is the host's
#endif
    } else {                                            // the host's (rtag_frame::host_commands)
        std::lock_guard<std::mutex> hold(g_m->sink.shots_lock);
        g_m->sink.commands_asked.push_back(text);
    }
}

// The decoder's thread: one list per vertical blank.
void on_frame(FrameList& frame) {
    Machine& m = *g_m;
    OutFrame* out = nullptr;
    {
        std::unique_lock<std::mutex> hold(m.lock);
        double w0 = now_ms();
        m.changed.wait(hold, [&] { return (int)m.ready.size() < Machine::DEPTH; });
        m.waited_downstream_ms += now_ms() - w0;
        if (!m.spare.empty()) { out = m.spare.back(); m.spare.pop_back(); }
    }
    if (!out) out = new OutFrame;
    out->shots.clear();
    out->commands.clear();
    out->picture_w = out->picture_h = 0;
    Note note;
    note.sim_tick = 0; note.flags = 0;
    memset(&note.view, 0, sizeof note.view);
    m.sink.take(frame.number, note);
    out->shots.swap(note.shots);
    out->commands.swap(note.commands);
    out->sim_tick = note.sim_tick;
    out->flags = note.flags;
    out->view = note.view;
    out->released_ms = note.released_ms;
    const double take0 = now_ms();
    if (m.scene3d) scene::take(frame, out->scene); else out->scene.clear();
    m.take_ms += now_ms() - take0;
    m.vertices += frame.vertices.size();
    m.commands += frame.commands.size();
    if (m.picture_w > 0 && !m.backend_failed) {
        double t0 = now_ms();
        if (!m.backend) {
            std::string why;
            if (!gl_offscreen::make_current(why)) {
                m.backend_failed = true;
                say("no OpenGL 4.1 context for the library's own renderer (" + why + "): no pictures from it");
            } else {
                m.backend = new render::GlBackend;
                render::PictureOptions picture;
                picture.samples = m.samples;
                picture.anisotropy = m.anisotropy < 1 ? 1 : m.anisotropy;
                picture.mipmaps = m.mipmaps != 0;
                m.backend->configure(picture);
                m.backend->set_output_size(m.picture_w, m.picture_h);
                say("the library's own renderer: " + gl_offscreen::description() + ", picture " + std::to_string(m.picture_w) + " x " + std::to_string(m.picture_h));
            }
        }
        if (m.backend) {
            m.backend->execute(frame);
            if (m.every_frame || !out->shots.empty()) {
                if (!m.backend->read_shown(out->picture, out->picture_w, out->picture_h)) out->picture_w = out->picture_h = 0;
            }
            for (const std::string& path : out->shots) {
                if (!out->picture_w) { say("no picture to write to " + path + " (nothing is shown)"); continue; }
                if (png_write::rgb_from_rgba(path.c_str(), out->picture.data(), out->picture_w, out->picture_h)) {
                    m.shots_written++;
                    say("wrote " + path + " (" + std::to_string(out->picture_w) + " x " + std::to_string(out->picture_h) + ") at vertical blank " + std::to_string(frame.number));
                } else say("cannot write " + path);
            }
        }
        m.backend_ms += now_ms() - t0;
    }
    // the list goes to the host; the renderer gets an older one's vectors back to fill again
    FrameList& slot = out->list;
    if (m.lists) {
        std::swap(slot.vertices, frame.vertices);
        std::swap(slot.commands, frame.commands);
        std::swap(slot.textures, frame.textures);
        std::swap(slot.targets, frame.targets);
        std::swap(slot.dead_textures, frame.dead_textures);
        std::swap(slot.dead_targets, frame.dead_targets);
    } else slot.clear();
    slot.show_target = frame.show_target;
    slot.aspect = frame.aspect;
    memcpy(slot.show_rect, frame.show_rect, sizeof(slot.show_rect));
    slot.number = frame.number;
    out->ready_ms = now_ms();
    {
        std::lock_guard<std::mutex> hold(m.lock);
        m.ready.push_back(out);
        m.frames_out++;
    }
    m.changed.notify_all();
}

void final_report() {                                   // on the game's thread, when the run ends
    Machine& m = *g_m;
    double wall = now_ms() - m.start_ms, cpu = cpu_ms() - m.start_cpu;
    double n = m.sink.blanks ? (double)m.sink.blanks : 1;
    printf("rtag: %llu vertical blanks in %.0f ms: %.1f pictures a second of wall time\n", (unsigned long long)m.sink.blanks, wall, 1000.0 * n / wall);
    printf("rtag: per picture %.2f ms of processor time over all threads of the process (the host's included); game side %.2f ms of wall time; decoder %.2f ms of wall "
           "time, %.2f ms of its own processor time (VIF1, VU1, GS model%s); %.0f vertices, %.0f draw commands\n",
           cpu / n, m.sink.game_ms / n, m.sink.decode_wall_ms / n, m.sink.decode_cpu_ms / n,
           m.picture_w > 0 ? ", and the library's own OpenGL renderer" : "", m.vertices / n, m.commands / n);
    if (m.picture_w > 0) printf("rtag: the library's own renderer: %.2f ms a picture on the decoder's thread (OpenGL calls, read-backs), %llu pictures written\n",
                                m.backend_ms / n, (unsigned long long)m.shots_written.load());
    apprt::films_report();
    const render::GsStats& g = m.renderer.gs.stats;
    printf("rtag: textures made %llu, held %llu (%.1f MB as RGBA), freed %llu; draws without their texture %llu; surface copies %llu; VU1 instructions not implemented %llu\n",
           (unsigned long long)g.textures_made, (unsigned long long)g.textures_held, g.texture_bytes / 1048576.0, (unsigned long long)g.textures_freed,
           (unsigned long long)g.texture_missing, (unsigned long long)g.copies, (unsigned long long)m.renderer.vif.vu.bad);
    {
        uint64_t wide = 0, clamps = 0, marks = 0, active = 0, fallback = 0, hidden = 0;
        gfxrt::figures(wide, clamps, marks);
        fpview::figures(active, fallback, hidden);
        printf("rtag: view modes: %llu draw passes with a view in place, %llu fell back to the game's camera; marks in the stream %llu; the game's own HUD layer %s\n",
               (unsigned long long)active, (unsigned long long)fallback, (unsigned long long)marks, m.renderer.gs.hide_edge ? "off" : "on");
    }
    if (m.scene3d) scene::report();
    fflush(stdout);
}

void on_quit(int code) {                                // host_godot.cpp: the runtime has ended the run
    Machine& m = *g_m;
    m.exit_code = code;
    m.ended = true;
    m.changed.notify_all();
}

void clock_loop() {
    Machine& m = *g_m;
    double next = now_ms();
    while (m.clock_on) {
        double hz = m.run_hz;
        if (hz <= 0) { std::this_thread::sleep_for(std::chrono::milliseconds(5)); next = now_ms(); continue; }
        next += 1000.0 / hz;
        double now = now_ms();
        if (now > next + 100) next = now;               // stood still (a level load, the host): no burst afterwards
        app::sleep_until_ms(next);
        m.sink.gate.grant(1);
    }
}

void fill_view(Machine& m) {
    OutFrame& f = *m.held;
    const FrameList& l = f.list;
    rtag_frame& v = m.view;
    memset(&v, 0, sizeof v);
    v.number = l.number;
    v.sim_tick = f.sim_tick;
    v.flags = f.flags;
    v.view = f.view;
    m.draws.resize(l.commands.size());
    for (size_t k = 0; k < l.commands.size(); k++) {
        const render::DrawCmd& c = l.commands[k];
        rtag_draw& d = m.draws[k];
        memset(&d, 0, sizeof d);
        d.kind = c.kind; d.prim = c.prim; d.made_by = c.made_by; d.scissor_moved = c.scissor_moved;
        d.first = c.first; d.count = c.count; d.target = c.target;
        memcpy(d.scissor, c.scissor, sizeof d.scissor);
        d.scissor_x[0] = c.scissor_x[0]; d.scissor_x[1] = c.scissor_x[1];
        d.texture = c.texture; d.tex_is_target = c.tex_is_target; d.linear = c.linear; d.wrap_s = c.wrap[0]; d.wrap_t = c.wrap[1];
        memcpy(d.tex_size, c.tex_size, sizeof d.tex_size);
        memcpy(d.tex_offset, c.tex_offset, sizeof d.tex_offset);
        memcpy(d.st_scale, c.st_scale, sizeof d.st_scale);
        memcpy(d.region, c.region, sizeof d.region);
        d.tex_missing = c.tex_missing;
        d.texa_mode = c.texa_mode; d.ta0 = c.ta0; d.ta1 = c.ta1; d.aem = c.aem;
        d.tfx = c.tfx; d.tcc = c.tcc;
        d.alpha_test = c.alpha_test; d.atst = c.atst; d.aref = c.aref; d.afail = c.afail;
        d.depth_test = c.depth_test; d.ztst = c.ztst; d.depth_write = c.depth_write;
        d.blend = c.blend; d.ba = c.ba; d.bb = c.bb; d.bc = c.bc; d.bd = c.bd; d.fix = c.fix;
        d.mask_rgb = c.mask_rgb; d.mask_a = c.mask_a;
        d.fog = c.fog; memcpy(d.fog_colour, c.fog_colour, 3);
        d.weave_half = c.weave_half; d.weave_base = c.weave_base;
        memcpy(d.copy_src, c.copy_src, sizeof d.copy_src);
        memcpy(d.copy_dst, c.copy_dst, sizeof d.copy_dst);
        d.scene_first = -1;
        d.scene_kind = 0;
        d.scene_piece_first = d.scene_piece_count = 0;
    }
    m.textures.resize(l.textures.size());
    for (size_t k = 0; k < l.textures.size(); k++) m.textures[k] = {l.textures[k].id, l.textures[k].width, l.textures[k].height, l.textures[k].rgba.data()};
    m.texture_names.resize(l.textures.size());
    for (size_t k = 0; k < l.textures.size(); k++) {
        const render::TextureData& t = l.textures[k];
        m.texture_names[k] = {t.id, t.named ? 1 : 0, t.figure, t.palette_figure, t.format, t.sent_width, t.sent_height, t.named_width, t.named_height};
    }
    m.targets.resize(l.targets.size());
    for (size_t k = 0; k < l.targets.size(); k++) m.targets[k] = {l.targets[k].id, l.targets[k].width, l.targets[k].height, l.targets[k].screen ? 1 : 0};
    m.shot_names.clear();
    for (auto& s : f.shots) m.shot_names.push_back(s.c_str());
    v.vertices = (const rtag_vertex*)l.vertices.data(); v.vertex_count = (uint32_t)l.vertices.size();
    v.draws = m.draws.data(); v.draw_count = (uint32_t)m.draws.size();
    v.textures = m.textures.data(); v.texture_count = (uint32_t)m.textures.size();
    v.targets = m.targets.data(); v.target_count = (uint32_t)m.targets.size();
    v.dead_textures = l.dead_textures.data(); v.dead_texture_count = (uint32_t)l.dead_textures.size();
    v.dead_targets = l.dead_targets.data(); v.dead_target_count = (uint32_t)l.dead_targets.size();
    v.show_target = l.show_target;
    memcpy(v.show_rect, l.show_rect, sizeof v.show_rect);
    v.aspect = l.aspect;
    if (f.picture_w > 0) { v.picture = f.picture.data(); v.picture_width = f.picture_w; v.picture_height = f.picture_h; }
    v.shots = m.shot_names.data(); v.shot_count = (uint32_t)m.shot_names.size();
    m.command_names.clear();
    for (auto& s : f.commands) m.command_names.push_back(s.c_str());
    v.host_commands = m.command_names.data(); v.host_command_count = (uint32_t)m.command_names.size();
    v.scene = nullptr;
    if (m.scene3d) {
        scene::fill(f.scene, m.scene_view, m.draws.data(), m.draws.size());
        v.scene = &m.scene_view;
    }
}

}  // namespace

extern "C" {

int rtag_api_version(void) { return RTAG_API_VERSION; }

// ---- the tester's kit (testerkit.h) ----
const char* rtag_report_begin(const char* host_lines) {
    static std::string folder;
#ifdef RTAG_HAVE_TESTERKIT
    std::string shot;
    folder = testerkit::begin(shot, false, host_lines ? host_lines : "");
#else
    (void)host_lines;
    folder.clear();
#endif
    return folder.c_str();
}
const char* rtag_report_finish(const char* folder, const char* text, int keep) {
    static std::string zip;
#ifdef RTAG_HAVE_TESTERKIT
    zip = folder && *folder ? testerkit::finish(folder, text ? text : "", keep != 0) : "";
#else
    (void)folder; (void)text; (void)keep;
    zip.clear();
#endif
    return zip.c_str();
}
const char* rtag_build_line(void) {
    static std::string line;
#ifdef RTAG_HAVE_TESTERKIT
    line = testerkit::build_line();
#endif
    return line.c_str();
}
const char* rtag_report_told(void) { return g_report_told.c_str(); }

double rtag_frame_since_release_ms(void) {
    if (!g_m) return -1;
    std::lock_guard<std::mutex> hold(g_m->lock);
    return g_m->held && g_m->held->released_ms > 0 ? now_ms() - g_m->held->released_ms : -1;
}

double rtag_frame_age_ms(void) {
    if (!g_m) return -1;
    std::lock_guard<std::mutex> hold(g_m->lock);
    return g_m->held ? now_ms() - g_m->held->ready_ms : -1;
}

int rtag_skeletons_get(rtag_skeletons* out) {
    // a host built before the players were added passes the shorter structure (up to player_count): it is served too
    if (!g_m || !out || out->struct_size < offsetof(rtag_skeletons, player_count) || !g_m->scene3d || !g_m->held) return 0;
    skel::fill(g_m->held->scene.skeletons, *out);
    return 1;
}

uint32_t rtag_texture_names(rtag_texture_name* out, uint32_t max) {
    if (!g_m || !out) return 0;
    uint32_t n = (uint32_t)std::min<size_t>(max, g_m->texture_names.size());
    for (uint32_t k = 0; k < n; k++) out[k] = g_m->texture_names[k];
    return n;
}

int rtag_has(const char* feature) {
    std::string f = feature ? feature : "";
    if (f == "fixes") {
#ifdef RTAG_ORIGINAL
        return 0;
#else
        return 1;
#endif
    }
    if (f == "films") return apprt::films_linked() ? 1 : 0;
    if (f == "picture") return 1;
    if (f == "scene3d") return 1;
    if (f == "texture_names") return 1;
    if (f == "skeletons") return 1;
    if (f == "views") return 1;
    if (f == "world") {
#ifdef RTAG_HAVE_WORLD
        return 1;
#else
        return 0;
#endif
    }
    if (f == "controls") {
#ifdef RTAG_HAVE_CONTROLS
        return 1;
#else
        return 0;
#endif
    }
    if (f == "music_volume") {
#ifdef RTAG_HAVE_MUSIC_GAIN
        return 1;
#else
        return 0;
#endif
    }
    if (f == "game_hud_text") {
#ifdef RTAG_HAVE_HUD_TEXT
        return 1;
#else
        return 0;
#endif
    }
    if (f == "aim") {                                   // aiming by looking (combat.aim, app aim ...)
#ifdef RTAG_HAVE_AIM
        return 1;
#else
        return 0;
#endif
    }
    if (f == "souls") {                                 // the souls-style combat mode (combat.mode, app souls ...)
#ifdef RTAG_HAVE_SOULS
        return 1;
#else
        return 0;
#endif
    }
    if (f == "network" || f == "net2") {                // the network driver and a room of our own (net2_* exported beside rtag_*)
#ifdef RTAG_HAVE_NET2
        return 1;
#else
        return 0;
#endif
    }
    return 0;
}

int rtag_start(const rtag_config* config) {
    if (!config || config->struct_size != sizeof(rtag_config)) return -1;
    if (g_m) return -4;
    if (!config->disc || !file_exists(config->disc)) return -2;
    if (!config->data_dir) return -1;
    Machine* m = new Machine;
    m->disc = config->disc;
    m->data = config->data_dir;
    m->workspace = config->workspace ? config->workspace : "";
    m->elf = config->elf ? config->elf : "";
    m->script = config->script ? config->script : "";
    m->lists = config->lists;
    m->picture_w = config->picture_width; m->picture_h = config->picture_height;
    m->every_frame = config->picture_every_frame;
    m->samples = config->samples; m->anisotropy = config->anisotropy; m->mipmaps = config->mipmaps;
    m->aspect = config->aspect > 0 ? config->aspect : 4.0 / 3.0;
    if (m->aspect < 4.0 / 3.0) m->aspect = 4.0 / 3.0;
    m->scene3d = config->scene3d;
    if (m->scene3d) m->renderer.gs.name_textures = true;    // a host may draw an art pack's pictures (rtag_texture_names)
    m->sound = config->sound;
    m->gain = config->gain;
    make_dir(m->data.c_str());
    std::string mode = "boot";
    std::vector<std::string> pass;
    for (int k = 0; k < config->argc; k++) pass.push_back(config->argv[k]);
    if (!pass.empty() && (pass[0] == "boot" || pass[0] == "resume")) { mode = pass[0]; pass.erase(pass.begin()); }
    if (mode == "boot" && m->elf.empty()) {
        bool given = false;
        for (auto& a : pass) if (a == "--elf") given = true;
        if (!given) {
            if (!m->workspace.empty() && file_exists(m->workspace + "/SLUS_209.73")) m->elf = m->workspace + "/SLUS_209.73";
            else {
                m->elf = m->data + "/SLUS_209.73";
                if (!file_exists(m->elf) && !apprt::extract_from_disc(m->disc, "\\SLUS_209.73;1", m->elf)) { delete m; return -3; }
            }
        }
    }
    g_m = m;

#ifdef RTAG_HAVE_TESTERKIT
    {
        // the tester's kit: the rings and the crash handler here; the host draws the box and the line (testerkit.gd)
        testerkit::Setup kit;
        kit.data_dir = m->data;
        kit.program = "Godot library";
        kit.host_ui = true;
        kit.describe = [] {
            std::string s = std::string("view = ") + fpview::mode_name(fpview::mode()) + "\n";
#ifdef RTAG_HAVE_AIM
            s += std::string("aim = ") + (fpaim::wanted() ? "where you look" : "the game's") + "\n";
#endif
#ifdef RTAG_HAVE_SOULS
            s += std::string("combat = ") + (soulscombat::wanted() ? "Hardcore" : "the game's") + "\n";
#endif
            if (g_m) {
                char text[160];
                snprintf(text, sizeof text, "drawn_by = %s\nlibrary_picture = %dx%d\naspect = %.4f\n", g_m->scene3d ? "Godot (scene)" : "the library (picture)",
                         g_m->picture_w, g_m->picture_h, g_m->aspect);
                s += text;
            }
            return s;
        };
        g_report_told = testerkit::start(kit);
    }
#endif
    m->renderer.gs.layout.enabled = true;
    gfxrt::install();
    gfxrt::set_aspect(m->aspect);
    // the view modes (tools/recomp/app/fpview.h): the game builds, culls and sends each frame for the selected view
    memset(&m->sink.drawn_view, 0, sizeof m->sink.drawn_view);
    memset(&m->sink.sent_view, 0, sizeof m->sink.sent_view);
    fpview::install();
    fpview::on_drawn(view_drawn);
#ifdef RTAG_HAVE_CONTROLS
    // the picture of a look view: its centre on the walking direction, the kick of swings and hits (fpcontrols.h)
    fpview::on_view([](fpview::View& v, Ctx*, void*) {
        if (v.shown != v.mode || !g_m->pads.controls_on) return;
        float forward[3] = {v.forward.x, v.forward.y, v.forward.z}, up[3] = {v.up.x, v.up.y, v.up.z};
        fpcontrols::apply_view(v.mode, forward, up);
        v.forward = {forward[0], forward[1], forward[2]};
        v.up = {up[0], up[1], up[2]};
    });
#endif
#ifdef RTAG_HAVE_WORLD
    // the world for a camera inside it: the fill (ceilings, skirts) is made at a level load and handed out by
    // rtag_fill_get; the cut at the near plane and the textures in perspective are for a host that draws the list.  The
    // scene tap draws the packets' complete geometry and counts their vertices, so with it both are off
    // (tools/recomp/render/fpworld.patch, its notes).
    fpworld::install();
    if (m->scene3d) { fpworld::setting("world.clip", "off"); fpworld::setting("world.persp", "off"); }
#endif
    if (config->view && *config->view) { int mode = fpview::mode_by_name(config->view); if (mode >= 0) fpview::set_mode(mode); }
    if (getenv("RTA_GS_LOG")) m->renderer.gs.log_display = true;
    if (m->scene3d) { scene::install(m->renderer); scene::set_aspect(m->aspect); }
    m->sink.renderer = &m->renderer;
    m->sink.resumed = mode == "resume";
    m->sink.waited_downstream_ms = &m->waited_downstream_ms;
    m->sink.pacer.mode = app::Pacer::OFF;
    m->renderer.on_frame = on_frame;
    m->sink.start();
    apprt::set_command_handler(app_command);
    apprt::set_finish_handler(final_report);
    rtag_host_set_quit(on_quit);
    apprt::interactive_threads();

    std::vector<std::string>& args = m->args;
    args = {"rtag", mode};
    if (mode == "boot" && !m->elf.empty()) { args.push_back("--elf"); args.push_back(m->elf); }
    args.push_back("--disc"); args.push_back(m->disc);
    args.push_back("--card"); args.push_back(m->data + "/card");
    if (config->emulator_timing) args.push_back("--emulator-timing");
    if (apprt::films_linked() && config->films) { args.push_back("--opt"); args.push_back("films=original"); }
    if (m->sound != RTAG_SOUND_NONE) {
        args.push_back("--opt"); args.push_back("sound-out=device");
        args.push_back("--opt"); args.push_back("sound-gain=1");
        bool said = false;
        for (auto& a : pass) if (a.compare(0, 12, "sound-clock=") == 0) said = true;
        if (m->sound == RTAG_SOUND_PULL && !said) { args.push_back("--opt"); args.push_back("sound-clock=real"); }
    }
    if (!m->script.empty() && !m->workspace.empty()) {  // names for the script's expressions
        if (file_exists(m->workspace + "/names.tsv")) { args.push_back("--sym"); args.push_back(m->workspace + "/names.tsv"); }
        std::vector<std::string> found;
        if (DIR* dir = opendir((m->workspace + "/symbols").c_str())) {
            while (dirent* e = readdir(dir)) {
                std::string name = e->d_name;
                if (name.size() > 4 && name.compare(name.size() - 4, 4, ".tsv") == 0) found.push_back(m->workspace + "/symbols/" + name);
            }
            closedir(dir);
        }
        std::sort(found.begin(), found.end());
        for (auto& path : found) { args.push_back("--sym"); args.push_back(path); }
    }
    if (!m->script.empty()) { args.push_back("--script"); args.push_back(m->script); }
    args.insert(args.end(), pass.begin(), pass.end());
    for (auto& a : args) m->argv.push_back(&a[0]);
    m->hooks.video = &m->sink;
    m->hooks.pad = &m->pads;
    m->start_ms = now_ms();
    m->start_cpu = cpu_ms();
    std::thread game([m] { app::interactive_thread(); rta::run((int)m->argv.size(), m->argv.data(), m->hooks); });
    game.detach();
    m->clock_on = true;
    m->clock = std::thread(clock_loop);
    m->clock.detach();
    return 0;
}

void rtag_set_pad(int port, const rtag_pad* pad) {
    if (!g_m || port < 0 || port > 1 || !pad) return;
    std::lock_guard<std::mutex> hold(g_m->pads.lock);
    g_m->pads.held[port] = *pad;
}

int rtag_poll(int wait_ms, const rtag_frame** frame) {
    if (frame) *frame = nullptr;
    if (!g_m) return -1;
    Machine& m = *g_m;
    {
        std::unique_lock<std::mutex> hold(m.lock);
        auto there = [&] { return !m.ready.empty() || m.ended.load(); };
        if (wait_ms < 0) m.changed.wait(hold, there);
        else if (wait_ms > 0) m.changed.wait_for(hold, std::chrono::milliseconds(wait_ms), there);
        if (m.ready.empty()) return m.ended ? -1 : 0;
        if (m.held) m.spare.push_back(m.held);
        m.held = m.ready.front();
        m.ready.pop_front();
        m.frames_taken++;
    }
    m.changed.notify_all();
    fill_view(m);
    if (frame) *frame = &m.view;
    return 1;
}

int rtag_step(const rtag_pad* pads, int wait_ms, const rtag_frame** frame) {
    if (frame) *frame = nullptr;
    if (!g_m) return -1;
    if (pads) { rtag_set_pad(0, &pads[0]); rtag_set_pad(1, &pads[1]); }
    g_m->sink.gate.grant(1);
    return rtag_poll(wait_ms, frame);
}

int rtag_release(void) {
    if (!g_m) return -1;
    g_m->sink.gate.grant(1);
    return 0;
}

void rtag_run(double hz) {
    if (!g_m) return;
    g_m->run_hz = hz > 0 ? hz : 0;
    g_m->sink.gate.set_open(hz < 0);
}

#ifdef RTAG_HAVE_MUSIC_GAIN
extern "C" void rta_sound_set_music_gain(float gain);      // tools/recomp/sound/drivers.cpp (the HUD agent's hunk)
#endif

int rtag_set_option(const char* key, const char* value) {
    if (!g_m || !key || !value) return 0;
    std::string k = key, v = value;
    if (k == "name_textures") {                         // work out every new texture's name (rtag_texture_names)
        g_m->renderer.gs.name_textures = !(v == "off" || v == "0" || v == "no");
        return 1;
    }
    if (k == "music_volume") {                          // 0..1: the game's music alone (stream 2 of the stream driver)
#ifdef RTAG_HAVE_MUSIC_GAIN
        rta_sound_set_music_gain((float)atof(value));
        return 1;
#else
        return 0;
#endif
    }
    if (k == "controls") {
#ifdef RTAG_HAVE_CONTROLS
        g_m->pads.controls_on = !(v == "off" || v == "0" || v == "no");
        return 1;
#else
        return 0;
#endif
    }
#ifdef RTAG_HAVE_CONTROLS
    if (k.compare(0, 9, "controls.") == 0) return fpcontrols::setting(key, value) ? 1 : 0;
#endif
    if (k == "combat.aim") {                            // "combat.aim" = look | off (fpaim.h)
#ifdef RTAG_HAVE_AIM
        return fpaim::setting(key, value) ? 1 : 0;
#else
        return 0;
#endif
    }
    if (k.compare(0, 7, "combat.") == 0) {             // "combat.mode" = souls | off, "combat.<number>" (soulscombat.h)
#ifdef RTAG_HAVE_SOULS
        return soulscombat::setting(key, value) ? 1 : 0;
#else
        return 0;
#endif
    }
    if (k == "game_hud_text") {
#ifdef RTAG_HAVE_HUD_TEXT
        bool off = v == "off" || v == "0" || v == "no";
        g_m->hud_text_off = off;
        gfxrt::set_hud_marks(off || g_m->renderer.gs.hide_edge);    // the marks are needed while either layer is left out
        g_m->renderer.gs.hide_text = off;
        return 1;
#else
        return 0;
#endif
    }
    if (k == "view") {
        int mode = fpview::mode_by_name(value);
        if (mode < 0) return 0;
        fpview::set_mode(mode);
        return 1;
    }
    if (k.compare(0, 5, "view.") == 0) return fpview::setting(key, value) ? 1 : 0;
    if (k == "world" || k.compare(0, 6, "world.") == 0) {
#ifdef RTAG_HAVE_WORLD
        return fpworld::setting(key, value) ? 1 : 0;
#else
        return 0;
#endif
    }
    if (k == "aspect") {                                // the shape of the 3-D view, width / height (4:3 at the least)
        double shape = atof(value);
        if (!(shape > 0)) return 0;
        if (shape < 4.0 / 3.0) shape = 4.0 / 3.0;
        g_m->aspect = shape;
        gfxrt::set_aspect(shape);                       // taken by the game at its next frame
        if (g_m->scene3d) scene::set_aspect(shape);
        return 1;
    }
    if (k == "game_hud") {
        bool off = v == "off" || v == "0" || v == "no";
        gfxrt::set_hud_marks(off || g_m->hud_text_off); // the marks that say what the HUD's draw functions made, also at 4:3
        g_m->renderer.gs.hide_edge = off;               // ... and the GS model leaves those primitives out
        return 1;
    }
    return 0;
}

void rtag_audio_pull(int16_t* stereo, int frames) {
    if (frames <= 0) return;
    if (!g_m || g_m->sound == RTAG_SOUND_NONE || g_m->ended) { memset(stereo, 0, (size_t)frames * 4); return; }
    rta::snd::host_audio_pull(stereo, (size_t)frames, (float)g_m->gain);
}

int rtag_controls_hud(rtag_controls* out) {
    if (!g_m || !out || out->struct_size != sizeof(rtag_controls)) return 0;
    std::lock_guard<std::mutex> hold(g_m->pads.hud_lock);
    if (!g_m->pads.have_hud) return 0;
    *out = g_m->pads.hud;
    return 1;
}

int rtag_fill_get(rtag_fill* out) {
    if (!out) return 0;
    memset(out, 0, sizeof *out);
#ifdef RTAG_HAVE_WORLD
    if (!g_m) return 0;
    static_assert(sizeof(rtag_fill_vertex) == sizeof(render::FillVertex) && sizeof(rtag_fill_mesh) == sizeof(render::FillMesh), "rtag_fill_* = render::Fill*");
    std::shared_ptr<const render::FillLevel> level = render::current_fill();
    std::lock_guard<std::mutex> hold(g_m->fill_lock);
    g_m->fill_held = level;                             // the pointers handed out stay valid until the next call or rtag_stop
    if (!level || level->meshes.empty()) return 0;
    out->serial = level->serial;
    out->level = level->name.c_str();
    out->vertices = (const rtag_fill_vertex*)level->vertices.data();
    out->vertex_count = (uint32_t)level->vertices.size();
    out->meshes = (const rtag_fill_mesh*)level->meshes.data();
    out->mesh_count = (uint32_t)level->meshes.size();
    memcpy(out->bounds, level->bounds, sizeof out->bounds);
    return 1;
#else
    return 0;
#endif
}

void rtag_mouse(float dx, float dy, float wheel) {
#ifdef RTAG_HAVE_CONTROLS
    if (!g_m) return;
    if (dx != 0 || dy != 0) fpcontrols::mouse_motion(dx, dy);
    if (wheel != 0) fpcontrols::mouse_wheel(wheel);
#else
    (void)dx; (void)dy; (void)wheel;
#endif
}

void rtag_mouse_button(int button, int down) {
#ifdef RTAG_HAVE_CONTROLS
    if (g_m) fpcontrols::mouse_button(button, down != 0);
#else
    (void)button; (void)down;
#endif
}

const uint8_t* rtag_memory(void) { return g_m ? rta::memory() : nullptr; }
uint64_t rtag_fields(void) { return g_m ? apprt::fields() : 0; }

const char* rtag_info(void) {
    if (!g_m) return "";
    Machine& m = *g_m;
    char text[768];
    double n = m.sink.blanks ? (double)m.sink.blanks : 1;
    size_t queued;
    { std::lock_guard<std::mutex> hold(m.lock); queued = m.ready.size(); }
    snprintf(text, sizeof text, "blanks=%llu ms=%.0f cpu_ms=%.0f game_ms=%.3f decode_wall_ms=%.3f decode_cpu_ms=%.3f backend_ms=%.3f frames_out=%llu frames_taken=%llu queued=%zu "
             "vertices=%.0f draws=%.0f tex_made=%llu tex_held=%llu tex_missing=%llu ended=%d %s",
             (unsigned long long)m.sink.blanks, now_ms() - m.start_ms, cpu_ms() - m.start_cpu, m.sink.game_ms / n, m.sink.decode_wall_ms / n, m.sink.decode_cpu_ms / n,
             m.backend_ms / n, (unsigned long long)m.frames_out.load(), (unsigned long long)m.frames_taken.load(), queued, m.vertices / n, m.commands / n,
             (unsigned long long)m.renderer.gs.stats.textures_made, (unsigned long long)m.renderer.gs.stats.textures_held,
             (unsigned long long)m.renderer.gs.stats.texture_missing, (int)m.ended.load(), apprt::sound_figures().c_str());
    m.info = text;
    char said[160];
    snprintf(said, sizeof said, " tap_ms=%.3f kick_ms=%.3f take_ms=%.3f skel_ms=%.3f", render::g_tap_ms / n, render::g_tap_kick_ms / n, m.take_ms / n, skel::g_build_ms / n);
    m.info += said;
#ifdef RTAG_HAVE_SOULS
    // the souls mode: wanted (this copy's setting) / active (the running game's)
    snprintf(said, sizeof said, " souls_want=%d souls_on=%d", soulscombat::wanted() ? 1 : 0, soulscombat::active() ? 1 : 0);
    m.info += said;
#endif
#ifdef RTAG_HAVE_AIM
    // aiming by looking, the same way
    snprintf(said, sizeof said, " aim_want=%d aim_on=%d", fpaim::wanted() ? 1 : 0, fpaim::active() ? 1 : 0);
    m.info += said;
#endif
#if (defined(RTAG_HAVE_SOULS) || defined(RTAG_HAVE_AIM)) && defined(RTAG_HAVE_NET2)
    // what this copy says of itself in a room (net2_set "copy"), as tools/recomp/net2/launch.cpp souls_describe makes it
    // (souls bit 0x8000, aim bit 0x4000, each folding its figure in): the portal says it again when it changes
    {
        const rtanet::Info& net = rtanet::info();
        uint32_t set = net.patch_set;
        unsigned words = net.patch_words & 0x3fff;
#ifdef RTAG_HAVE_SOULS
        if (soulscombat::wanted()) { words |= 0x8000; if (net2hook::souls_figure) set ^= net2hook::souls_figure(); }
#endif
#ifdef RTAG_HAVE_AIM
        if (fpaim::wanted()) { words |= 0x4000; if (net2hook::aim_figure) set ^= net2hook::aim_figure(); }
#endif
        if (net.patch_set != 0 || net.patch_words != 0) {
            snprintf(said, sizeof said, " copy=fix=%08x,words=%u", set, words);
            m.info += said;
        }
    }
#endif
    return m.info.c_str();
}

int rtag_ended(void) { return g_m && g_m->ended ? 1 : 0; }
int rtag_exit_code(void) { return g_m ? g_m->exit_code.load() : 0; }

void rtag_stop(void) {
    if (!g_m) return;
    Machine& m = *g_m;
    if (m.ended) return;
    m.pads.quit = true;
    m.run_hz = 0;
    double until = now_ms() + 2000;
    while (!m.ended && now_ms() < until) {
        m.sink.gate.grant(1);
        // frames still on their way are thrown away so that the decoder and the game are not held
        {
            std::lock_guard<std::mutex> hold(m.lock);
            while (!m.ready.empty()) { m.spare.push_back(m.ready.front()); m.ready.pop_front(); }
        }
        m.changed.notify_all();
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    m.clock_on = false;
}

}  // extern "C"
