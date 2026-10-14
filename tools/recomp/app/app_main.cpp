// app_main.cpp - rta_app: Champions: Return to Arms as a native application.
//
// One window in which the game - its own code translated to C++ (tools/recomp), no
// emulator - boots from power-on, shows its picture (tools/recomp/render), plays its sound
// (tools/recomp/sound) and takes the keyboard and a game controller.
//
//   rta_app --disc IMAGE [options] [-- <more arguments for the runtime>]
//
//   --disc IMAGE        your disc image of SLUS-20973 v2.00, read in place (or $RTA_DISC)
//   --data DIR          settings and memory cards (default: app-data beside the program's bin/)
//   --elf FILE          the game's executable (default: SLUS_209.73 of the workspace, else
//                       copied out of the disc image into the data directory)
//   --window WxH        window size in points (default 960x720); the picture keeps 4:3
//   --fullscreen        start full screen (F or F11 toggles, Escape leaves)
//   --scale N           draw the picture at N times the console's 640 x 448 (1..8)
//   --size WxH          or at exactly this size (default: the window's own pixels)
//   the picture (docs/issues/native-graphics.md; each is also a line of <data>/settings.txt,
//   see settings.h - the file is read first, then these):
//   --aspect A          the shape of the 3-D view: auto (the window's own, the default), 4:3
//                       (the console's), 16:9, 16:10, 21:9, W:H.  The game itself makes the wide
//                       view (gfx_rt.h); the HUD keeps to its edge, menus stay centred
//   --resolution R      the size the picture is drawn at: window, WxH, or Nx (as --size / --scale)
//   --antialiasing N    samples per pixel of the 3-D scene: off, 2, 4 (default), 8
//   --anisotropy N      1 (off) to 16 (default);  --mipmaps yes|no  mip maps for the game's textures
//   --art-pack DIR      replacement pictures named as the emulator build names textures
//                       (tools/play-net/README.md, "Upscaled art");  --art-memory MB (3072)
//   --frame-cap N       60 (default), 30, or 0 = --unpaced
//   --view V            the camera: overhead (the game's own, the default), action, chase,
//                       shoulder, first (fpview.h; docs/issues/native-first-person.md).  V switches
//                       while the game runs; --view-set NAME=VALUE is a "view.<mode>.<name>" line
//   --game-hud on|off, --game-hud-text on|off   the game's own HUD layer (status, gold, compass, minimap,
//                       spell selector) and its second group (boss meter, one-line message, prompt
//                       box) left out of the picture; --music-volume 0..1 the game's music alone
//                       (speech and effects stay).  Lines of the settings file too; while running:
//                       "app option game_hud|game_hud_text on|off", "app option music_volume V"
//   --present metal|opengl   how a picture gets into the window (present_host.h): through a Metal
//                       layer, drawn and handed over by a thread of its own that nothing AppKit
//                       does to the window can hold up (the default), or by an OpenGL swap on the
//                       window's own thread as it was until 2026-10-13 (if the picture looks wrong)
//   --pacing ahead|queued   how the game is held to one frame per picture (pipeline.h): let go
//                       by a clock just ahead of each picture's moment (the default), or held
//                       back through the picture path's hand-overs as it was until 2026-10-12
//   --plain             all of that off: 4:3, no multisampling, no mip maps, no pack
//   --settings FILE, --no-settings;  tests: --no-layout, --art-whole, --art-wait
//   --volume V          0..1 (default 1); --mute = --volume 0 (the device still runs);
//                       --no-sound opens no device at all
//   --emulator-timing   the I/O processor answers as slowly as on a console (default: fast loading)
//   --no-films          a film ends at its first picture (as the headless runtime does it)
//   --script FILE, --do "COMMAND"   scripted input (the rig's script language) on top of
//                       keyboard and controller; "app ..." lines are for this program:
//                         app shot FILE.png        the picture of this vertical blank, at its drawn size
//                         app key down|up NAME     a key event sent to the window (w a s d up down left right
//                                                  i j k l q e 1 3 x c return backspace)
//                         app gcpad connect|disconnect|set BUTTONS|none [lx ly rx ry [l2 r2]]
//                                                  a controller made by the program, to test the map
//                         app pads                 print the controller and what port 1 holds
//                         app stats [reset]        print the pacing figures so far: how long pictures stood, and
//                                                  what each part of the path from the game to the swap took
//                         app window W H           give the window this size (the view follows with --aspect auto)
//                         app fullscreen           what the F key does
//                         app view NAME|next       the camera: overhead action chase shoulder first
//                         app view set KEY VALUE   a view setting, e.g. app view set view.first.fov 75
//                         app view info            print the view of the last frame
//                         app art off|on           draw with the game's own textures / with the art pack and mip maps again
//                         app latency BUTTONS [pictures [before]]   a press given to the controller read after
//                                                  `before` (12) more pictures; app latency report, `pictures`
//                                                  (40) later, says which picture first showed a change
//                         app record FILE | app record stop
//                                                  write the picture stream from here on (render/stream.h;
//                                                  played back by rta_replay: draw lists, texture sheets)
//   --test "TEXT"       a test run on a computer somebody is using: the window is titled
//                       "AGENT TEST - TEXT", small, behind the others, takes no keyboard,
//                       and the sound is silent whatever --volume says
//   --offscreen         no window (pictures and timings only)
//   --unpaced           as fast as the machine goes
//   --png PREFIX --at n,n,...   write the shown picture at these vertical blanks
//   --stop-after N      print the figures and end after N vertical blanks
//   --control PATH      a control socket for test runs (control.h): the protocol of the emulator
//                       build's, so that one driver walks both builds through the same places
//
// Keyboard: W A S D left stick, arrows direction pad, I J K L triangle square cross circle,
// Q E L1 R1, 1 3 L2 R2, X C L3 R3, Return Start, Backspace Select.  The first game
// controller macOS knows is port 1 as well (pad_mac.mm).
//
// Threads: the game's (the runtime, rta::run), a decoder (pipeline.h) and this one, which
// owns the window and OpenGL.  One picture per 1/60 s: the game is let go by a clock just
// ahead of the moment each picture is due on screen, and that clock is held to the
// display's refreshes when the display's rate is a multiple of 60 Hz and its swaps wait
// for them (pipeline.h, Pacer).  No thread waits for another across a swap: the decoder
// hands its lists to a short queue, and a picture that is overtaken is drawn and not shown.
#include "app_rt.h"
#include "backend_gl.h"
#include "control.h"
#include "fpcontrols.h"
#include "fpview.h"
#include "gfx_rt.h"
#include "help_host.h"
#include "look_host.h"
#include "pad_host.h"
#include "pipeline.h"
#include "present_host.h"
#include "recorder.h"
#include "settings.h"

#include <QCoreApplication>
#include <QEvent>
#include <QGuiApplication>
#include <QImage>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QWheelEvent>
#include <QOffscreenSurface>
#include <QOpenGLContext>
#include <QOpenGLExtraFunctions>
#include <QScreen>
#include <QSurfaceFormat>
#include <QThread>
#include <QTimer>
#include <QWindow>

#include <atomic>
#include <cmath>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <mutex>
#include <set>
#include <string>
#include <sys/resource.h>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>
#include <vector>

using namespace render;
using app::now_ms;

// ---- the display's own refreshes ------------------------------------------------------------
// On this system a swap does not wait for the display (Ran: 0.25 ms, display lit or not), so
// the times swaps return at say nothing about where the refreshes lie.  The display link
// does: its callback is handed, about 11 ms ahead, the time of the refresh the frame then
// being made will be shown at.  The window's thread asks here for the refresh nearest to a
// picture's moment; the pacer moves its grid onto them (pipeline.h).  It runs on a thread
// of its own and stops ticking when the display sleeps: an answer older than a tenth of a
// second is no answer.
#ifdef __APPLE__
#include <CoreGraphics/CoreGraphics.h>
#include <CoreVideo/CVDisplayLink.h>
#include <mach/mach_time.h>
struct DisplayClock {
    std::atomic<double> refresh_at{0}, period{0}, seen{0};      // a refresh (ms of now_ms()), the time between two, when that was learnt
    std::atomic<uint64_t> ticks{0};
    CVDisplayLinkRef link = nullptr;
    static CVReturn tick(CVDisplayLinkRef, const CVTimeStamp* now, const CVTimeStamp* out, CVOptionFlags, CVOptionFlags*, void* user) {
        DisplayClock& d = *(DisplayClock*)user;
        static mach_timebase_info_data_t base;
        if (!base.denom) mach_timebase_info(&base);
        (void)now;
        // host time to this program's clock: both read now
        double host_now = (double)mach_absolute_time() * base.numer / base.denom / 1e6, mine = now_ms();
        if (out->videoTimeScale && out->videoRefreshPeriod) d.period = 1000.0 * (double)out->videoRefreshPeriod / (double)out->videoTimeScale;
        d.refresh_at = (double)out->hostTime * base.numer / base.denom / 1e6 + (mine - host_now);
        d.seen = mine;
        d.ticks++;
        return kCVReturnSuccess;
    }
    bool start() {
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
        if (CVDisplayLinkCreateWithCGDisplay(CGMainDisplayID(), &link) != kCVReturnSuccess || !link) return false;
        CVDisplayLinkSetOutputCallback(link, tick, this);
        return CVDisplayLinkStart(link) == kCVReturnSuccess;
#pragma clang diagnostic pop
    }
    // The refresh nearest to `moment`; false when the display says nothing now, or its
    // refreshes are not `refresh_ms` apart (another display's rate).
    bool nearest(double moment, double refresh_ms, double& refresh) const {
        double at = refresh_at, p = period, when = seen;
        if (p <= 0 || now_ms() - when > 100.0 || std::fabs(p - refresh_ms) > 0.02 * refresh_ms) return false;
        refresh = at + std::round((moment - at) / p) * p;
        return true;
    }
};
#else
struct DisplayClock {
    std::atomic<uint64_t> ticks{0};
    bool start() { return false; }
    bool nearest(double, double, double&) const { return false; }
};
#endif
static DisplayClock g_display;

// ---- what holds the window's thread ("RTA_STALL_LOG=1", a debugging aid) ---------------------
// A list that is ready to be drawn is normally taken by the window's thread within a
// millisecond.  When it is not taken for `after_ms`, a thread of its own takes the window
// thread's call stack every few milliseconds until the list is taken, and prints the
// stacks with the names the dynamic loader knows (image and nearest exported name, and
// the offsets, so that `atos -o IMAGE -l BASE ADDRESS` gives the rest afterwards).  The
// window's thread is stopped for the microseconds it takes to copy the addresses; nothing
// that may wait for a lock is called while it is stopped.
#ifdef __APPLE__
#include <dlfcn.h>
#include <mach/mach.h>
#include <pthread.h>
struct StallWatch {
    const char* what;                           // what stood: said in every line
    explicit StallWatch(const char* text) : what(text) {}
    std::atomic<double> waiting_since{0};       // the watched thread has had something to do since then (0: nothing, or it is at it)
    std::atomic<bool> on{false};
    std::atomic<uint64_t> stalls{0};
    std::atomic<double> longest_ms{0}, total_ms{0};
    double after_ms = 25.0;
    thread_act_t port = 0;
    uintptr_t stack_low = 0, stack_high = 0;
    enum { DEPTH = 48, MOST = 12 };
    struct Stack { double at_ms; int count; uintptr_t pc[DEPTH]; };
    void start() {                              // on the thread to be watched
        if (!getenv("RTA_STALL_LOG")) return;
        if (const char* ms = getenv("RTA_STALL_MS")) after_ms = std::max(2.0, atof(ms));
        port = mach_thread_self();
        stack_high = (uintptr_t)pthread_get_stackaddr_np(pthread_self());
        stack_low = stack_high - pthread_get_stacksize_np(pthread_self());
        on = true;
        std::thread([this] { app::interactive_thread(); loop(); }).detach();
    }
    void ready() { if (on) { double zero = 0; waiting_since.compare_exchange_strong(zero, now_ms()); } }
    void taken() { if (on) waiting_since = 0; }
    void beat() { if (on) waiting_since = now_ms(); }           // a thread that should come by every few milliseconds
    bool take(Stack& out) {
#if defined(__arm64__) || defined(__aarch64__)
        if (thread_suspend(port) != KERN_SUCCESS) return false;
        arm_thread_state64_t state;
        mach_msg_type_number_t n = ARM_THREAD_STATE64_COUNT;
        out.count = 0;
        if (thread_get_state(port, ARM_THREAD_STATE64, (thread_state_t)&state, &n) == KERN_SUCCESS) {
            out.pc[out.count++] = (uintptr_t)arm_thread_state64_get_pc(state);
            out.pc[out.count++] = (uintptr_t)arm_thread_state64_get_lr(state);
            uintptr_t fp = (uintptr_t)arm_thread_state64_get_fp(state);
            while (out.count < DEPTH && fp >= stack_low && fp + 16 <= stack_high && !(fp & 7)) {
                uintptr_t next = ((uintptr_t*)fp)[0], ret = ((uintptr_t*)fp)[1];
                if (!ret) break;
                out.pc[out.count++] = ret;
                if (next <= fp) break;
                fp = next;
            }
        }
        thread_resume(port);
        return out.count > 0;
#else
        (void)out;
        return false;
#endif
    }
    void loop() {
        std::vector<Stack> stacks;
        for (;;) {
            std::this_thread::sleep_for(std::chrono::milliseconds(3));
            double since = waiting_since;
            if (since == 0 || now_ms() - since < after_ms) continue;
            stacks.clear();
            while (waiting_since.load() == since && stacks.size() < MOST) {
                Stack one;
                one.at_ms = now_ms() - since;
                if (take(one)) stacks.push_back(one);
                std::this_thread::sleep_for(std::chrono::milliseconds(stacks.size() < 4 ? 6 : 25));
            }
            while (waiting_since.load() == since) std::this_thread::sleep_for(std::chrono::milliseconds(2));
            double held = now_ms() - since;
            stalls++;
            total_ms = total_ms + held;
            if (held > longest_ms) longest_ms = held;
            std::string text;
            char line[640];
            snprintf(line, sizeof line, "rta_app: stall: %s for %.1f ms; its call stack meanwhile (%zu taken):\n", what, held, stacks.size());
            text += line;
            for (size_t k = 0; k < stacks.size(); k++) {
                bool same = k > 0 && stacks[k].count == stacks[k - 1].count && !memcmp(stacks[k].pc + 2, stacks[k - 1].pc + 2, (stacks[k].count - 2) * sizeof(uintptr_t));
                snprintf(line, sizeof line, "rta_app: stall:  at %.1f ms%s\n", stacks[k].at_ms, same ? ": as before (but for the innermost frames)" : ":");
                text += line;
                for (int f = 0; f < stacks[k].count && (!same || f < 2); f++) {
                    uintptr_t pc = stacks[k].pc[f] & 0x0000FFFFFFFFFFFFull;
                    Dl_info info;
                    if (dladdr((void*)pc, &info) && info.dli_fname) {
                        const char* image = strrchr(info.dli_fname, '/');
                        snprintf(line, sizeof line, "rta_app: stall:    %-28s %s + %lu   [%s base 0x%lx address 0x%lx]\n", image ? image + 1 : info.dli_fname,
                                 info.dli_sname ? info.dli_sname : "?", info.dli_saddr ? (unsigned long)(pc - (uintptr_t)info.dli_saddr) : 0ul,
                                 info.dli_fname, (unsigned long)(uintptr_t)info.dli_fbase, (unsigned long)pc);
                    } else snprintf(line, sizeof line, "rta_app: stall:    0x%lx\n", (unsigned long)pc);
                    text += line;
                }
            }
            fputs(text.c_str(), stderr);
            fflush(stderr);
        }
    }
};
#else
struct StallWatch {
    explicit StallWatch(const char*) {}
    double after_ms = 0;
    std::atomic<bool> on{false};
    std::atomic<uint64_t> stalls{0};
    std::atomic<double> longest_ms{0}, total_ms{0};
    void start() {}
    void ready() {}
    void taken() {}
    void beat() {}
};
#endif
static StallWatch g_stall("a list that was ready to be drawn waited for the thread that draws");
static StallWatch g_main_stall("the window's own thread (the main one: events, AppKit) did not come back to its event loop");

static const char* TITLE = "Champions: Return to Arms - native build (experimental)";
static render::Renderer* g_renderer;
static double memory_mb();

static double cpu_ms() {                                // processor time of the whole process
    rusage u;
    getrusage(RUSAGE_SELF, &u);
    return (u.ru_utime.tv_sec + u.ru_stime.tv_sec) * 1000.0 + (u.ru_utime.tv_usec + u.ru_stime.tv_usec) / 1000.0;
}

// How a picture gets into the window when nothing is said (--present, RTA_PRESENT):
// through a Metal layer from a drawing thread of its own (macOS: ten minutes of a fight in
// a window somebody was moving another window over had 27 of 36,000 pictures late that way
// and 769 the other way, native-app.md 12.3), or by an OpenGL swap on the window's own thread.
#ifdef __APPLE__
static const bool PRESENT_METAL_DEFAULT = true;
#else
static const bool PRESENT_METAL_DEFAULT = false;
#endif

struct Options {
    int window_w = 960, window_h = 720, size_w = 0, size_h = 0, scale = 0;
    bool offscreen = false, unpaced = false, fullscreen = false, no_sound = false, emulator_timing = false, no_films = false;
    bool queued = false;                // --pacing queued: the picture path's hand-overs hold the game back
    bool metal = PRESENT_METAL_DEFAULT; // --present metal|opengl: how the picture gets into the window (present_host.h)
    double volume = 1.0;
    std::string test, png, disc, data, elf, control;
    std::set<uint64_t> at;
    uint64_t stop_after = 0;
    // the picture (settings.h): the settings file, then the command line
    app::Settings set;
    double aspect = 0;                  // of the 3-D view; 0 = the window's own shape
    bool layout = true;                 // false: the wide picture without the 2-D layer put back into shape
    bool art_parts = true;              // false: whole replacement pictures on the graphics card
    bool art_wait = false;              // tests: every frame waits for the replacement pictures it asks for
    std::string settings_file;
};

static void log_line(const std::string& line) {
    fprintf(stderr, "rta_app: %s\n", line.c_str());
    fflush(stderr);
}

// ---- input --------------------------------------------------------------------------------
// The keyboard as a pad: bits of rta::PadButton plus four bits for the stick keys.
enum { KEY_STICK_UP = 1 << 16, KEY_STICK_DOWN = 1 << 17, KEY_STICK_LEFT = 1 << 18, KEY_STICK_RIGHT = 1 << 19 };
static std::atomic<uint32_t> g_keys{0};
static std::atomic<uint64_t> g_key_events{0};

static uint32_t key_bit(int key) {
    switch (key) {
    case Qt::Key_W: return KEY_STICK_UP;
    case Qt::Key_S: return KEY_STICK_DOWN;
    case Qt::Key_A: return KEY_STICK_LEFT;
    case Qt::Key_D: return KEY_STICK_RIGHT;
    case Qt::Key_Up: return rta::PAD_UP;
    case Qt::Key_Down: return rta::PAD_DOWN;
    case Qt::Key_Left: return rta::PAD_LEFT;
    case Qt::Key_Right: return rta::PAD_RIGHT;
    case Qt::Key_I: return rta::PAD_TRIANGLE;
    case Qt::Key_J: return rta::PAD_SQUARE;
    case Qt::Key_K: return rta::PAD_CROSS;
    case Qt::Key_L: return rta::PAD_CIRCLE;
    case Qt::Key_Q: return rta::PAD_L1;
    case Qt::Key_E: return rta::PAD_R1;
    case Qt::Key_1: return rta::PAD_L2;
    case Qt::Key_3: return rta::PAD_R2;
    case Qt::Key_X: return rta::PAD_L3;
    case Qt::Key_C: return rta::PAD_R3;
    case Qt::Key_Return: case Qt::Key_Enter: return rta::PAD_START;
    case Qt::Key_Backspace: return rta::PAD_SELECT;
    // second names for three buttons, where a hand on W A S D and a mouse finds them (fpcontrols.h)
    case Qt::Key_Space: return rta::PAD_SQUARE;
    case Qt::Key_Shift: return rta::PAD_R1;
    case Qt::Key_Tab: return rta::PAD_R3;
    default: return 0;
    }
}
static int key_by_name(const std::string& name) {
    static const struct { const char* name; int key; } names[] = {
        {"w", Qt::Key_W}, {"a", Qt::Key_A}, {"s", Qt::Key_S}, {"d", Qt::Key_D}, {"up", Qt::Key_Up}, {"down", Qt::Key_Down},
        {"left", Qt::Key_Left}, {"right", Qt::Key_Right}, {"i", Qt::Key_I}, {"j", Qt::Key_J}, {"k", Qt::Key_K}, {"l", Qt::Key_L},
        {"q", Qt::Key_Q}, {"e", Qt::Key_E}, {"1", Qt::Key_1}, {"3", Qt::Key_3}, {"x", Qt::Key_X}, {"c", Qt::Key_C},
        {"return", Qt::Key_Return}, {"backspace", Qt::Key_Backspace}, {"escape", Qt::Key_Escape}, {"f", Qt::Key_F}, {"v", Qt::Key_V},
        {"space", Qt::Key_Space}, {"shift", Qt::Key_Shift}, {"tab", Qt::Key_Tab}};
    for (auto& n : names) if (name == n.name) return n.key;
    return 0;
}

// ---- press to picture ("app latency BUTTONS [pictures [before]]") ---------------------------
// A press is put on port 1 at one controller read; every picture presented from `before`
// pictures earlier on is reduced to a coarse grid of brightness, and the first one that
// differs from its predecessor by clearly more than the pictures before the press differed
// among themselves is the answer to the press.
struct Latency {
    std::mutex lock;
    int state = 0;                      // 0 off, 1 armed (counting pictures before the press), 2 pressed, 3 done
    uint16_t buttons = 0;
    int before = 12, after = 40, hold = 4;
    uint64_t arm_blank = 0, press_blank = 0;
    double press_ms = 0;
    struct Sample { uint64_t number; double presented_ms; std::vector<uint8_t> grid; };
    std::vector<Sample> samples;
} g_latency;

static app::Control& control();

// Port 1 is the script, the control socket, the controller and the keyboard together:
// buttons of all, each stick from the first of them that is not at rest.
struct Pads : rta::PadSource {
    std::atomic<uint32_t> last_buttons{0};
    std::atomic<uint32_t> last_sticks{0x80808080};
    std::atomic<uint32_t> rumbles{0};
    std::atomic<bool> quit{false};
    void read(unsigned port, uint64_t frame, rta::PadState& state) override {
        if (quit) apprt::finish(0);                     // the window was closed: end from the game's thread
        state = apprt::script_pad(port);
        if (port != 0) return;
        {
            std::lock_guard<std::mutex> hold(g_latency.lock);
            Latency& t = g_latency;
            if (t.state == 1 && !t.arm_blank) t.arm_blank = frame;
            if (t.state == 1 && frame >= t.arm_blank + (uint64_t)t.before) { t.state = 2; t.press_blank = frame; t.press_ms = now_ms(); }
            if (t.state == 2 && frame < t.press_blank + (uint64_t)t.hold) state.buttons |= t.buttons;
        }
        {
            app::Control& c = control();
            state.buttons |= c.held;
            if (state.lx == 128 && state.ly == 128) { state.lx = c.sticks[0]; state.ly = c.sticks[1]; }
            if (state.rx == 128 && state.ry == 128) { state.rx = c.sticks[2]; state.ry = c.sticks[3]; }
        }
        rta::PadState pad;
        bool have_pad = hostpad::read(pad);
        uint32_t keys = g_keys;
        rta::PadState kb;
        kb.buttons = (uint16_t)keys;
        kb.lx = (keys & KEY_STICK_LEFT) ? ((keys & KEY_STICK_RIGHT) ? 128 : 0) : (keys & KEY_STICK_RIGHT) ? 255 : 128;
        kb.ly = (keys & KEY_STICK_UP) ? ((keys & KEY_STICK_DOWN) ? 128 : 0) : (keys & KEY_STICK_DOWN) ? 255 : 128;
        state.buttons |= kb.buttons;
        if (have_pad) state.buttons |= pad.buttons;
        auto rest = [](uint8_t x, uint8_t y) { return x == 128 && y == 128; };
        if (rest(state.lx, state.ly)) {
            if (have_pad && !rest(pad.lx, pad.ly)) { state.lx = pad.lx; state.ly = pad.ly; }
            else { state.lx = kb.lx; state.ly = kb.ly; }
        }
        if (rest(state.rx, state.ry) && have_pad) { state.rx = pad.rx; state.ry = pad.ry; }
        // the views that look along the ground: mouse and right stick are the look (the game
        // camera's yaw word), the character is turned to it; in the overhead views nothing
        // changes (fpcontrols.h).  The view is the one of the last draw pass.
        // (Not while another machine's controller rows are replayed: the input is then given
        // whole - the rows, and the yaw word the game turns from them - and the controls, which
        // drive the yaw word themselves in shoulder and first person, stand aside.  The view is
        // still drawn; it is the camera's own claim that is checked that way: 12.10.)
        {
            static const bool replayed = apprt::replaying();
            const fpview::View& v = fpview::view();
            fpcontrols::set_view(replayed ? 0 : fpview::mode(), v.active && !v.fallback, v.look_pitch);
            fpcontrols::translate(frame, state);
            if (float pitch = fpcontrols::take_pitch(); pitch != 0) fpview::add_pitch(pitch);
        }
        last_buttons = state.buttons;
        last_sticks = state.lx | state.ly << 8 | state.rx << 16 | (uint32_t)state.ry << 24;
    }
    void rumble(unsigned, uint8_t, uint8_t) override { rumbles++; }
};
static Pads g_pads;
static app::Control g_control;
static app::Control& control() { return g_control; }

// ---- the window ---------------------------------------------------------------------------
static const QEvent::Type FrameEvent = (QEvent::Type)(QEvent::User + 1);
static const QEvent::Type CallEvent = (QEvent::Type)(QEvent::User + 2);

class GameWindow : public QWindow {
  public:
    bool test = false;
    bool pointer_let_go = false;        // Escape gave the pointer back; a click in the window takes it again
    void toggle_fullscreen() { if (visibility() == QWindow::FullScreen) showNormal(); else showFullScreen(); }
    // What the thread that draws needs to know of the window, kept here by this (the main)
    // thread whenever it changes: size in points, device pixels per point, whether any of
    // it can be seen.
    std::atomic<int> points_w{0}, points_h{0};
    std::atomic<double> pixel_ratio{1.0};
    std::atomic<bool> exposed{false};
    std::atomic<uint64_t> changes{0};
    void mirror() {
        points_w = width(); points_h = height();
        pixel_ratio = devicePixelRatio();
        exposed = isExposed();
        changes++;
    }

  protected:
    void keyPressEvent(QKeyEvent* e) override {
        if (e->isAutoRepeat()) return;
        g_key_events++;
        if (uint32_t bit = key_bit(e->key())) { g_keys |= bit; return; }
        if (test) return;
        if (e->key() == Qt::Key_F1 || e->key() == Qt::Key_Help) { hosthelp::toggle(); return; }
        if (e->key() == Qt::Key_V) { fpview::cycle(e->modifiers() & Qt::ShiftModifier ? -1 : 1); log_line(std::string("view: ") + fpview::mode_name(fpview::mode())); return; }
        if (e->key() == Qt::Key_Escape && hostlook::captured()) { pointer_let_go = true; hostlook::capture(false); return; }
        if (e->key() == Qt::Key_F11 || (e->key() == Qt::Key_F && !(e->modifiers() & ~Qt::KeyboardModifiers(Qt::ControlModifier | Qt::MetaModifier)))) toggle_fullscreen();
        else if (e->key() == Qt::Key_Escape && visibility() == QWindow::FullScreen) showNormal();
    }
    void keyReleaseEvent(QKeyEvent* e) override {
        if (e->isAutoRepeat()) return;
        g_key_events++;
        if (uint32_t bit = key_bit(e->key())) g_keys &= ~bit;
    }
    void focusOutEvent(QFocusEvent*) override { g_keys = 0; fpcontrols::release_all(); hostlook::capture(false); }       // nothing stays held when the window is left
    // the mouse (fpcontrols.h): its buttons are pad buttons in the look views.  Not in a test window: a test
    // moves and presses through the control socket ("app fpc ..."), and a person's click on it must do nothing
    static int mouse_index(Qt::MouseButton b) { return b == Qt::LeftButton ? 0 : b == Qt::RightButton ? 1 : b == Qt::MiddleButton ? 2 : b == Qt::BackButton ? 3 : 4; }
    void mousePressEvent(QMouseEvent* e) override { if (test) return; pointer_let_go = false; fpcontrols::mouse_button(mouse_index(e->button()), true); }
    void mouseReleaseEvent(QMouseEvent* e) override { if (test) return; fpcontrols::mouse_button(mouse_index(e->button()), false); }
    void wheelEvent(QWheelEvent* e) override { if (!test) fpcontrols::mouse_wheel((float)e->angleDelta().y() / 120.0f); }
    void resizeEvent(QResizeEvent*) override { mirror(); }
    void exposeEvent(QExposeEvent*) override { mirror(); }
    bool event(QEvent* e) override {
        if (e->type() == QEvent::DevicePixelRatioChange || e->type() == QEvent::WindowStateChange) {
            bool r = QWindow::event(e);
            mirror();
            if (e->type() == QEvent::WindowStateChange)
                log_line(std::string("window: ") + (visibility() == QWindow::FullScreen ? "full screen" : visibility() == QWindow::Minimized ? "minimised" : "a window") +
                         ", " + std::to_string(width()) + " x " + std::to_string(height()) + " points");
            return r;
        }
        if (e->type() == QEvent::Close) {
            // the game's thread ends the run at its next vertical blank (reports, sound device);
            // if it does not come to one, end here
            g_pads.quit = true;
            QTimer::singleShot(1500, [] { fflush(stdout); _exit(0); });
            e->ignore();
            return true;
        }
        return QWindow::event(e);
    }
};

struct CallQEvent : QEvent {
    std::function<void()> fn;
    explicit CallQEvent(std::function<void()> f) : QEvent(CallEvent), fn(std::move(f)) {}
};

// The window and the picture.  The window is the main thread's (Qt, AppKit: events, the
// title bar, everything the system does to a window).  The picture - the OpenGL context,
// the backend, drawing, the swap and its timing - belongs to a thread of its own, the
// "drawing thread": while the main thread is inside one of AppKit's own jobs for the
// window (its display cycle makes calls to the window server that take 100 ms and more
// when a person is moving other windows about: seen with RTA_STALL_LOG, native-app.md
// 12.3), pictures go on being drawn and shown.  RTA_PICTURE_THREAD=main: the main thread
// draws as well, as it did until 2026-10-13 (for comparing).
class Screen : public QObject {
  public:
    Options opt;
    bool own_thread = true;                             // a thread of its own draws (see above)
    QThread* painter = nullptr;
    std::condition_variable work;                       // a list or a call waits for the drawing thread
    std::vector<std::function<void()>> calls;           // to be carried out by the drawing thread, with its context current (under `lock`)
    GameWindow* window = nullptr;
    QOffscreenSurface* offscreen = nullptr;
    QOpenGLContext* context = nullptr;
    GlBackend* backend = nullptr;
    bool follow_window = false;                         // the picture is drawn at the window's pixel size
    double view_aspect = 4.0 / 3.0;                     // what the game is asked to make its view for
    // hand-over: lists wait here in order.  The decoder waits only when all places are
    // taken (`limit`: 1 in the queued way - it then waits until the picture before is shown).
    enum { DEPTH = 3 };
    struct Item { FrameList frame; std::vector<std::string> shots; app::Timing timing; };
    std::mutex lock;
    std::mutex pace_lock;                               // the figures (written here, read by whoever reports)
    std::condition_variable done;
    Item items[DEPTH];
    int head = 0, count = 0, limit = DEPTH;
    double submit_wait_ms = 0;                          // time the decoder waited for this thread
    app::Pacer* pacer = nullptr;
    // pacing
    double refresh_hz = 60, refresh_ms = 1000.0 / 60, period_ms = 1000.0 / 60;
    int refreshes_per_picture = 1;
    bool display_locked = false;
    double last_present = 0;
    // Does the swap wait for the display?  It does for a window on a lit display, and
    // returns at once for a hidden one or when the display is asleep.  A swap asked for
    // well before the picture's moment that took 2.5 ms or more is taken as one that
    // waited (one that does not wait takes a third of a millisecond; one that waits for a
    // refresh it knows nothing of takes 2.5 ms or more seven times out of ten).  Six more
    // of those than of the others, and the times the swaps return at are taken as the
    // display's refreshes (`swap_waits`); as many of the others again, and they are not.
    int swap_evidence = 0;
    bool swap_waits = false;
    // The display's refreshes as the display link tells them (DisplayClock), used where the
    // swaps do not wait: the picture is then handed over nine tenths of a refresh before
    // its moment - shortly after the refresh before it, which is when the system expects a
    // frame for the next one (the display link itself calls 11 ms ahead).
    bool display_link = false;
    uint64_t link_timed = 0;                            // pictures whose moment was set against the display link
    double ask_ahead() const {                          // how long before its moment a picture's swap is asked for
        if (!display_locked) return 0;
        if (display_link && !swap_waits) return 0.9 * refresh_ms;
        return refreshes_per_picture > 1 ? 0.5 * refresh_ms : 0;
    }
    bool pace_log = getenv("RTA_PACE_LOG") != nullptr;  // debugging: one line per picture
    // a test aid (RTA_FAKE_DISPLAY=HZ[,PPM[,PHASE_MS]]): a display that is not there - every
    // swap waits until the next refresh of a display of that rate, PPM millionths fast
    // against this computer's clock - to see the grid find a display's refreshes when the
    // real display is asleep or the window hidden
    double fake_refresh_ms = 0, fake_phase_ms = 0;
    // figures
    uint64_t blanks = 0;
    double draw_ms = 0, start_ms = 0, start_cpu = 0, main_cpu_ms = 0;
    size_t vertices = 0, commands = 0;
    struct Pace {
        uint64_t presents = 0, swap_waited = 0, timer_waited = 0, late_starts = 0, overtaken = 0, late = 0;
        uint64_t by_refreshes[8] = {0, 0, 0, 0, 0, 0, 0, 0};    // pictures that stood for k refreshes (7 = more)
        uint64_t late_by[5] = {0, 0, 0, 0, 0};                  // of the late ones: the part that took longest (game, decoder, OpenGL, swap, a wait)
        double first = 0, last = 0, swap_ms = 0, worst_ms = 0;
        // the path, per picture (milliseconds of wall time)
        app::Figure game, slot_wait, decoder_idle, decode, queue, gl, to_swap, swap, pipe;
        std::vector<float> slack;                               // the moment minus the time it was drawn at (negative: drawn late)
        // through Metal the system says when each picture really was on the glass (present_host.h)
        uint64_t glass = 0, glass_never = 0, glass_by_refreshes[8] = {0, 0, 0, 0, 0, 0, 0, 0};
        double glass_last = 0, glass_worst_ms = 0;
        app::Figure glass_after_due;                            // on the glass, minus the moment it was meant for (+1000 ms, see where it is added)
        double slack_mean = 0, slack_low = 0;                   // filled in by report_pace
        // processor time at the reset, to say what a picture cost since
        double cpu0 = 0, main_cpu0 = 0, decode_cpu0 = 0;
        uint64_t blanks0 = 0;
    } pace;

    // Through a Metal layer (present_host.h): the window has no OpenGL in it, the context is
    // made current on a surface without a window, and the drawing thread hands each picture
    // to the layer itself.
    bool metal = false;
    hostpresent::Surface* presenter = nullptr;
    QSurface* surface() { return window && !metal ? (QSurface*)window : (QSurface*)offscreen; }     // what the context is made current on

    void create() {
        QSurfaceFormat format = QSurfaceFormat::defaultFormat();
        format.setSwapInterval(opt.unpaced ? 0 : 1);
#ifdef __APPLE__
        metal = !opt.offscreen && opt.metal;
#endif
        if (opt.offscreen || metal) {
            offscreen = new QOffscreenSurface;
            offscreen->setFormat(format);
            offscreen->create();
        }
        if (!opt.offscreen) {
            // (a plain CAMetalLayer, not Qt's own kind that presents with the main thread's transaction while a window is resized)
            if (metal) qputenv("QT_MTL_NO_TRANSACTION", "1");
            window = new GameWindow;
            window->setSurfaceType(metal ? QSurface::MetalSurface : QSurface::OpenGLSurface);
            if (!metal) window->setFormat(format);
            if (!opt.test.empty()) {
                window->test = true;
                window->setTitle(QString("AGENT TEST - ") + QString::fromStdString(opt.test));
                // (tests of what is on the glass need the window to be seen: RTA_TEST_WINDOW_FRONT=1 keeps a test
                // window above the others instead of below them; it still takes no keyboard)
                bool front = getenv("RTA_TEST_WINDOW_FRONT") != nullptr;
                window->setFlags(window->flags() | Qt::WindowDoesNotAcceptFocus | (front ? Qt::WindowStaysOnTopHint : Qt::WindowStaysOnBottomHint));
            } else window->setTitle(TITLE);
            window->resize(opt.window_w, opt.window_h);
            window->setMinimumSize(QSize(320, 240));
            // tests: RTA_TEST_WINDOW_AT=X,Y puts a test window where the test wants it (to move another window over it)
            // (a negative figure counts from the screen's right or lower edge)
            if (const char* at = getenv("RTA_TEST_WINDOW_AT")) {
                int x = 0, y = 0;
                if (!opt.test.empty() && sscanf(at, "%d,%d", &x, &y) == 2) {
                    QRect screen = QGuiApplication::primaryScreen() ? QGuiApplication::primaryScreen()->availableGeometry() : QRect(0, 0, 1440, 900);
                    if (x < 0) x = screen.right() + x - opt.window_w;
                    if (y < 0) y = screen.bottom() + y - opt.window_h;
                    window->setPosition(x, y);
                }
            }
            if (opt.fullscreen && opt.test.empty()) window->showFullScreen(); else window->show();
            if (!opt.test.empty() && !getenv("RTA_TEST_WINDOW_FRONT")) window->lower();
            window->mirror();
        }
        context = new QOpenGLContext;
        context->setFormat(format);
        if (!context->create() || !context->makeCurrent(surface())) { log_line("no OpenGL 4.1 context"); _exit(1); }
        QOpenGLExtraFunctions* gl = context->extraFunctions();
        log_line(std::string("OpenGL ") + (const char*)gl->glGetString(GL_VERSION) + " on " + (const char*)gl->glGetString(GL_RENDERER));
        if (metal) {
            presenter = hostpresent::create((void*)window->winId(), log_line);
            if (!presenter) { log_line("the window cannot be given its pictures through Metal; start again with --present opengl"); _exit(1); }
        }
        backend = new GlBackend;
        {
            PictureOptions picture;
            picture.samples = opt.set.samples;
            picture.anisotropy = opt.set.anisotropy;
            picture.mipmaps = opt.set.mipmaps;
            picture.pack = opt.set.art_pack;
            picture.pack_memory_mb = opt.set.art_memory;
            picture.pack_parts = opt.art_parts;
            picture.pack_wait = opt.art_wait;
            backend->configure(picture);
            PictureFigures fig = backend->figures();
            char line[512];
            snprintf(line, sizeof line, "picture: %d samples per pixel, anisotropy %d, mip maps for the game's textures %s; art pack %s (%llu pictures), %d MB",
                     fig.samples, fig.anisotropy, opt.set.mipmaps ? "on" : "off", opt.set.art_pack.empty() ? "none" : opt.set.art_pack.c_str(),
                     (unsigned long long)fig.pack_files, opt.set.art_memory);
            log_line(line);
        }
        // The shape of the view: what was asked for, else the window's own (without a window:
        // the shape of the size asked for; a size of 640 x 448 and its multiples is the
        // console's picture, which is 4:3).
        int w = opt.size_w, h = opt.size_h;
        double shape = opt.aspect;
        if (shape <= 0) {
            if (window) shape = (double)window->width() / window->height();
            else if (w && h) shape = (w * 448 == h * 640) ? 4.0 / 3.0 : (double)w / h;
            else shape = (double)opt.window_w / opt.window_h;
        }
        if (shape < 4.0 / 3.0) shape = 4.0 / 3.0;
        view_aspect = shape;
        if (opt.scale) { h = 448 * opt.scale; w = (int)std::lround(640 * opt.scale * shape / (4.0 / 3.0)); }
        if (!w || !h) {
            follow_window = window != nullptr;
            double ratio = window ? window->devicePixelRatio() : 1.0;
            h = (int)((window ? window->height() : opt.window_h) * ratio);
            w = (int)std::lround(h * shape);
            if (window && w > (int)(window->width() * ratio)) { w = (int)(window->width() * ratio); h = (int)std::lround(w / shape); }
        }
        opt.size_w = w; opt.size_h = h;
        backend->set_output_size(w, h);
        gfxrt::set_aspect(shape);
        if (window && window->screen()) refresh_hz = window->screen()->refreshRate();
        if (refresh_hz < 20 || refresh_hz > 1000) refresh_hz = 60;
        refresh_ms = 1000.0 / refresh_hz;
        refreshes_per_picture = (int)std::lround(refresh_hz / 60.0);
        if (refreshes_per_picture < 1) refreshes_per_picture = 1;
        // locked to the display when its rate is a multiple of the console's within 1.5 %
        display_locked = window && !opt.unpaced && std::fabs(refresh_hz / refreshes_per_picture - 60.0) < 0.9;
        period_ms = display_locked ? refresh_ms * refreshes_per_picture : 1000.0 / 59.94;
        char text[256];
        snprintf(text, sizeof text, "picture drawn at %d x %d; display %.2f Hz; %s", w, h, refresh_hz,
                 opt.unpaced ? "not paced" : display_locked ? "one picture per display refresh interval(s) below" : "paced by the clock at 59.94 pictures a second");
        log_line(text);
        if (display_locked) { snprintf(text, sizeof text, "pacing: one picture every %d refresh(es) = %.3f ms", refreshes_per_picture, period_ms); log_line(text); }
        if (const char* fake = getenv("RTA_FAKE_DISPLAY")) {
            double hz = 0, ppm = 0, phase = 0;
            sscanf(fake, "%lf,%lf,%lf", &hz, &ppm, &phase);
            if (hz >= 20 && window && !opt.unpaced) {
                fake_refresh_ms = 1000.0 / (hz * (1.0 + ppm * 1e-6));
                fake_phase_ms = phase;
                refresh_hz = hz;
                refresh_ms = 1000.0 / hz;
                refreshes_per_picture = std::max(1, (int)std::lround(hz / 60.0));
                display_locked = std::fabs(hz / refreshes_per_picture - 60.0) < 0.9;
                period_ms = display_locked ? refresh_ms * refreshes_per_picture : 1000.0 / 59.94;
                snprintf(text, sizeof text, "TEST: a display of %.3f Hz that is not there (RTA_FAKE_DISPLAY): every swap waits for its next refresh", 1000.0 / fake_refresh_ms);
                log_line(text);
            }
        }
        limit = opt.queued ? 1 : DEPTH;
        if (pacer) {
            pacer->mode = opt.unpaced ? app::Pacer::OFF : opt.queued ? app::Pacer::QUEUED : app::Pacer::AHEAD;
            pacer->period_ms = period_ms;
            pacer->most_lead_ms = 2.5 * period_ms;
            // a drawn picture is to be there before the swap is asked for: half a refresh before
            // its moment where the swaps are asked for inside the last refresh, 4 ms otherwise
            // on a display, and a millisecond more; 2 ms where nothing is shown
            pacer->margin_ms = !window ? 2.0 : 1.0 + (display_locked && refreshes_per_picture > 1 ? 0.5 * refresh_ms : 4.0);
            // the real display's refreshes (not with the display that is not there, and not when told not to)
            if (window && display_locked && fake_refresh_ms == 0 && !opt.queued && !getenv("RTA_NO_DISPLAY_LINK")) {
                display_link = g_display.start();
                log_line(display_link ? "pacing: the display link is asked where the display's refreshes lie" : "pacing: no display link");
            }
            if (!opt.unpaced) log_line(opt.queued ? "pacing: the picture path's hand-overs hold the game back (--pacing queued)"
                                                  : "pacing: the game is let go by the clock, just ahead of each picture's moment");
        }
        start_ms = now_ms();
        start_cpu = cpu_ms();
        pace.cpu0 = start_cpu;
        // Who draws.  Without a window: a thread of its own.  With the window as an OpenGL
        // view: the main thread - AppKit ends the program when a context that has a view is
        // updated from any other ("-[NSOpenGLContext update] must be called from the main
        // thread if the context has a view", met at the first resize: Ran, 12.3), and Qt
        // says of itself that it cannot draw OpenGL from another thread on macOS.
        const char* who = getenv("RTA_PICTURE_THREAD");
        own_thread = !window || metal;
        if (who && !strcmp(who, "main")) own_thread = false;
        if (own_thread) {
            // the context goes to the drawing thread for good (Qt: a context is made current
            // only on the thread its object lives on)
            context->doneCurrent();
            painter = QThread::create([this] { painter_loop(); });
            context->moveToThread(painter);
            painter->start();
        } else {
            log_line(metal ? "picture: drawn by the window's own (main) thread (RTA_PICTURE_THREAD=main)"
                           : "picture: drawn and swapped by the window's own (main) thread (--present opengl: an OpenGL view cannot be drawn from another)");
            g_stall.start();
        }
    }

    // Something for the drawing thread to do with its context current (an "app art" line).
    void on_drawing_thread(std::function<void()> fn) {
        if (!own_thread) { QCoreApplication::postEvent(this, new CallQEvent(std::move(fn))); return; }
        { std::lock_guard<std::mutex> hold(lock); calls.push_back(std::move(fn)); }
        work.notify_one();
    }
    void painter_loop() {
        app::interactive_thread();
        g_stall.start();
        for (;;) {
            std::vector<std::function<void()>> todo;
            bool have;
            {
                std::unique_lock<std::mutex> hold(lock);
                work.wait(hold, [this] { return count > 0 || !calls.empty(); });
                todo.swap(calls);
                have = count > 0;
            }
            if (!todo.empty()) {
                context->makeCurrent(surface());
                for (auto& fn : todo) fn();
            }
            if (have) draw_one();
        }
    }

    // called on the decoder's thread: take this list to be drawn.  Returns as soon as there
    // is a place for it; the caller gets the vectors of an earlier list back to fill again.
    void submit(FrameList& frame, std::vector<std::string>& shots, app::Timing timing) {
        std::unique_lock<std::mutex> hold(lock);
        double w0 = now_ms();
        timing.decode_end = w0;
        done.wait(hold, [this] { return count < limit; });
        timing.queue_wait = now_ms() - w0;
        submit_wait_ms += timing.queue_wait;
        Item& item = items[(head + count) % DEPTH];
        FrameList& slot = item.frame;
        std::swap(slot.vertices, frame.vertices);
        std::swap(slot.commands, frame.commands);
        std::swap(slot.textures, frame.textures);
        std::swap(slot.targets, frame.targets);
        std::swap(slot.dead_textures, frame.dead_textures);
        std::swap(slot.dead_targets, frame.dead_targets);
        slot.show_target = frame.show_target;
        slot.aspect = frame.aspect;
        memcpy(slot.show_rect, frame.show_rect, sizeof(slot.show_rect));
        slot.number = frame.number;
        item.shots.swap(shots);
        shots.clear();
        item.timing = timing;
        count++;
        if (count == 1) g_stall.ready();                // nothing was before it: the drawing thread is free to take it
        if (own_thread) work.notify_one(); else QCoreApplication::postEvent(this, new QEvent(FrameEvent));
    }

    bool event(QEvent* e) override {                    // the main thread
        if (e->type() == CallEvent) { static_cast<CallQEvent*>(e)->fn(); return true; }
        if (e->type() != FrameEvent) return QObject::event(e);
        draw_one();
        return true;
    }

    // The drawing thread: the oldest list waiting is drawn, shown at its moment, counted.
    void draw_one() {
        Item* item;
        double newer_due = -1;                          // the moment of the list behind this one, when there is one
        g_stall.taken();
        {
            std::lock_guard<std::mutex> hold(lock);
            item = &items[head];                        // ours until it is counted off below
            if (count > 1) newer_due = items[(head + 1) % DEPTH].timing.due;
        }
        FrameList* frame = &item->frame;
        app::Timing& timing = item->timing;
        double t0 = now_ms(), cpu0 = app::thread_cpu_ms();
        timing.draw_start = t0;
        if (window_free > timing.decode_end) timing.blocked += std::min(t0, window_free) - timing.decode_end;
        context->makeCurrent(surface());
        QOpenGLExtraFunctions* gl = context->extraFunctions();
        // the window as its own thread last saw it (GameWindow::mirror)
        int win_w = window ? window->points_w.load() : 0, win_h = window ? window->points_h.load() : 0;
        double win_ratio = window ? window->pixel_ratio.load() : 1.0;
        if (win_w < 1 || win_h < 1) { win_w = opt.window_w; win_h = opt.window_h; }
        if (window && opt.aspect == 0) {                // the view takes the window's shape
            double shape = (double)win_w / win_h;
            if (shape < 4.0 / 3.0) shape = 4.0 / 3.0;
            if (std::fabs(shape - view_aspect) > 0.002) { view_aspect = shape; gfxrt::set_aspect(shape); }
        }
        // The picture is sized for the shape THIS list was built for (it says so itself): while
        // a new shape is on its way through the game and the decoder, the lists still in
        // flight are drawn as what they are, with bars for a frame or two, never stretched.
        if (follow_window && window) {                  // the window was resized: draw at its new size
            double ratio = win_ratio, shape = frame->aspect;
            int h = (int)(win_h * ratio), w = (int)std::lround(h * shape);
            if (w > (int)(win_w * ratio)) { w = (int)(win_w * ratio); h = (int)std::lround(w / shape); }
            if (h >= 224 && (h != opt.size_h || w != opt.size_w)) { opt.size_w = w; opt.size_h = h; backend->set_output_size(w, h); }
        } else if (opt.scale) {
            int h = 448 * opt.scale, w = (int)std::lround(640 * opt.scale * frame->aspect / (4.0 / 3.0));
            if (h != opt.size_h || w != opt.size_w) { opt.size_w = w; opt.size_h = h; backend->set_output_size(w, h); }
        }
        backend->execute(*frame);
        vertices += frame->vertices.size();
        commands += frame->commands.size();
        if (!opt.png.empty() && opt.at.count(blanks)) save(opt.png + "-" + std::to_string(blanks) + ".png");
        for (const std::string& path : item->shots) save(path);
        item->shots.clear();
        bool ahead = pacer && pacer->mode == app::Pacer::AHEAD && timing.due > 0;
        // The moment this picture is due: the game's grid, or (queued, or before there is a
        // grid) one period after the picture before.
        double due = ahead ? timing.due : last_present + period_ms;
        // Overtaken: the list behind this one is due as well (this thread was held up, by
        // a swap that waited long or by anything else).  This one was drawn - the surfaces
        // and textures the next list builds on are as they have to be - and is not shown.
        bool overtaken = ahead && newer_due > 0 && newer_due <= now_ms() + 0.5 * refresh_ms;
        bool shown = window && window->exposed.load() && !overtaken;
        if (opt.set.frame_cap > 0 && opt.set.frame_cap <= 30 && (blanks & 1)) shown = false;        // every other picture
        double after = 0;
        bool timed = false;                             // the swap returned at a refresh of the display
        bool for_window = false;                        // the window's picture is drawn (through Metal: there was a surface for it)
        auto to_window = [&] {
            int pw = (int)(win_w * win_ratio), ph = (int)(win_h * win_ratio);
            if (metal) {
                unsigned target = hostpresent::begin(presenter, pw, ph);
                if (!target) return;
                gl->glBindFramebuffer(GL_FRAMEBUFFER, target);
                backend->present_top_down(pw, ph, frame->aspect);
            } else {
                gl->glBindFramebuffer(GL_FRAMEBUFFER, context->defaultFramebufferObject());
                backend->present(pw, ph, frame->aspect);
            }
            for_window = true;
        };
        // Let go ahead of its moment, a picture is "drawn" when the graphics card has
        // finished it, the window's copy included: what is left for the swap is to hand it
        // over, and how long the path takes is known to the millisecond (the lead is made of
        // it).  The queued way draws the window's copy after its wait, as it always did.
        if (ahead) {
            if (shown) to_window();
            gl->glFinish();
        }
        timing.ready = now_ms();
        if (shown) {
            // with more than one refresh per picture the swap is asked for inside the last of
            // them, so that it lands on the refresh the picture is due at
            if (display_locked && last_present != 0 && (ahead ? ask_ahead() > 0 : refreshes_per_picture > 1))
                app::sleep_until_ms(due - (ahead ? ask_ahead() : 0.5 * refresh_ms));
            if (!ahead) to_window();
            timing.swap_start = now_ms();
            if (metal) {
                if (!ahead) gl->glFinish();             // (let go ahead, the picture was finished above)
                if (for_window) hostpresent::show(presenter, now_ms(), opt.unpaced ? 0.0 : due);
            } else context->swapBuffers(window);
            if (fake_refresh_ms > 0) {                  // the display that is not there: wait for its next refresh
                double now = now_ms();
                app::sleep_until_ms((std::floor((now - fake_phase_ms) / fake_refresh_ms) + 1) * fake_refresh_ms + fake_phase_ms);
            }
            after = now_ms();
            if (!opt.unpaced && due - timing.swap_start >= 3.0) {
                swap_evidence = after - timing.swap_start >= 2.5 ? std::min(swap_evidence + 1, 12) : std::max(swap_evidence - 1, 0);
                if (swap_evidence >= 6) swap_waits = true; else if (swap_evidence == 0) swap_waits = false;
            }
        } else { gl->glFlush(); after = now_ms(); timing.swap_start = after; }
        draw_ms += after - t0;
        bool clock_held = false, restarted = false;
        if (overtaken) {}
        else if (!opt.unpaced) {
            // One picture per period.  A swap that waited for the display returns at the
            // refresh; one that did not (window hidden, display asleep, no display lock) is
            // held by the clock.
            // (`timed`: this swap's return is a refresh of the display, early or late; the grid learns from it)
            timed = shown && display_locked && swap_waits && last_present != 0 && after - due <= 2 * period_ms;
            if (last_present == 0 || after - due > 2 * period_ms) { restarted = last_present != 0; last_present = after; }
            else if (after < due - 1.5 && !timed) {
                app::sleep_until_ms(due);
                clock_held = true;
                last_present = due;
            } else last_present = after;
        } else last_present = after;
        timing.shown = overtaken ? 0 : timed ? after : last_present;
        // Where the swaps do not wait, the display link says where the refresh nearest to this
        // picture's moment lay: the grid learns from that (a picture that came late learns nothing).
        double refresh = 0;
        if (ahead && shown && !timed && display_link && !swap_waits && !restarted && after <= due + 1.5 && g_display.nearest(due, refresh_ms, refresh)) {
            timed = true;
            timing.shown = refresh;
            link_timed++;
        }
        if (pacer && ahead) pacer->margin_ms = !window ? 2.0 : 1.0 + (display_locked ? std::max(ask_ahead(), refreshes_per_picture > 1 ? 0.0 : 4.0) : 4.0);
        if (pace_log && !overtaken) fprintf(stderr, "pace %llu due %.2f ready %.2f ask %.2f after %.2f shown-due %.2f timed %d evidence %d lead %.2f\n", (unsigned long long)frame->number,
                                            fmod(due, 1000.0), timing.ready - due, timing.swap_start - due, after - due, timing.shown - due, (int)timed, swap_evidence,
                                            pacer ? pacer->lead_ms.load() : 0.0);
        timing.due = overtaken || opt.unpaced ? 0 : due;
        main_cpu_ms += app::thread_cpu_ms() - cpu0;
        if (pacer && !overtaken) pacer->presented(timing, timed);
        // figures: how long the picture before this one stood, in refreshes of the display,
        // and what each part of this one's way took
        std::vector<hostpresent::Glass> told;
        if (presenter) hostpresent::glass(presenter, told);
        std::unique_lock<std::mutex> figures(pace_lock);
        for (const hostpresent::Glass& g : told) {
            if (g.on_glass_ms <= 0) { pace.glass_never++; continue; }
            if (pace.glass_last > 0) {
                double stood = g.on_glass_ms - pace.glass_last;
                long k = std::lround(stood / refresh_ms);
                pace.glass_by_refreshes[k < 0 ? 0 : k > 7 ? 7 : k]++;
                if (stood > pace.glass_worst_ms) pace.glass_worst_ms = stood;
            }
            pace.glass_last = g.on_glass_ms;
            pace.glass++;
            if (g.due_ms > 0) {
                double off = g.on_glass_ms - g.due_ms;
                pace.glass_after_due.add(off + 1000.0);         // (kept positive for the figure: 1000 is taken off again when it is printed)
            }
        }
        if (shown) { pace.swap_ms += after - timing.swap_start; if (after - timing.swap_start > 1.0) pace.swap_waited++; }
        if (overtaken) pace.overtaken++;
        if (clock_held) pace.timer_waited++;
        if (restarted) pace.late_starts++;
        if (!overtaken) {
            double t = opt.unpaced ? after : last_present;
            if (pace.presents) {
                double stood = t - pace.last;
                long k = std::lround(stood / refresh_ms);
                pace.by_refreshes[k < 0 ? 0 : k > 7 ? 7 : k]++;
                if (stood > pace.worst_ms) pace.worst_ms = stood;
            } else pace.first = t;
            pace.last = t;
            pace.presents++;
        }
        if (timing.released > 0 && timing.handed > 0) {
            double parts[5] = {timing.handed - timing.released, timing.decode_end - timing.decode_start, timing.ready - timing.draw_start,
                               after - timing.swap_start, (timing.decode_start - timing.handed) + (timing.draw_start - timing.decode_end)};
            pace.game.add(parts[0]);
            pace.slot_wait.add(timing.slot_wait);
            pace.decoder_idle.add(timing.decode_start - timing.handed - timing.slot_wait);
            pace.decode.add(parts[1]);
            pace.queue.add(timing.draw_start - timing.decode_end);
            pace.gl.add(parts[2]);
            pace.to_swap.add(timing.swap_start - timing.ready);
            pace.swap.add(parts[3]);
            pace.pipe.add(timing.ready - timing.released - timing.blocked);
            if (timing.due > 0) {
                if (pace.slack.size() < 400000) pace.slack.push_back((float)(timing.due - timing.ready));
                // late: on screen more than half a refresh after its moment
                if (timing.shown > timing.due + 0.5 * refresh_ms) {
                    pace.late++;
                    int longest = 0;
                    for (int k = 1; k < 5; k++) if (parts[k] > parts[longest]) longest = k;
                    pace.late_by[longest]++;
                }
            }
        }
        figures.unlock();
        latency_sample(frame->number, after);
        blanks++;
        if (opt.stop_after && blanks >= opt.stop_after) {
            gl->glFinish();
            g_pads.quit = true;                         // the game's thread prints the reports and ends the process
            QCoreApplication::postEvent(this, new CallQEvent([] { QTimer::singleShot(3000, [] { fflush(stdout); _exit(0); }); }));
        }
        window_free = now_ms();
        bool more;
        { std::lock_guard<std::mutex> hold(lock); head = (head + 1) % DEPTH; count--; more = count > 0; if (more) g_stall.ready(); }
        done.notify_all();
        // (the main thread drawing: every list posted its own event; the drawing thread comes round by itself)
    }
    double window_free = 0;                             // when this thread was done with the picture before

    // the shown picture as a 40 x 28 grid of brightness, while a latency test runs
    void latency_sample(uint64_t number, double presented) {
        Latency& t = g_latency;
        { std::lock_guard<std::mutex> hold(t.lock); if (t.state != 1 && t.state != 2) return; }
        std::vector<uint8_t> rgba;
        int w = 0, h = 0;
        if (!backend->read_shown(rgba, w, h) || w < 40 || h < 28) return;
        Latency::Sample s;
        s.number = number; s.presented_ms = presented;
        s.grid.resize(40 * 28);
        for (int gy = 0; gy < 28; gy++)
            for (int gx = 0; gx < 40; gx++) {
                unsigned sum = 0, n = 0;
                for (int y = gy * h / 28; y < (gy + 1) * h / 28; y += 2)
                    for (int x = gx * w / 40; x < (gx + 1) * w / 40; x += 2) {
                        const uint8_t* p = &rgba[((size_t)y * w + x) * 4];
                        sum += p[0] + 2 * p[1] + p[2]; n++;
                    }
                s.grid[gy * 40 + gx] = (uint8_t)(n ? sum / (4 * n) : 0);
            }
        std::lock_guard<std::mutex> hold(t.lock);
        t.samples.push_back(std::move(s));
        if (t.state == 2 && number >= t.press_blank + (uint64_t)t.after) t.state = 3;
    }

    void save(const std::string& name) {
        std::vector<uint8_t> rgba;
        int w = 0, h = 0;
        if (!backend->read_shown(rgba, w, h)) { log_line("no picture to write to " + name + " (nothing is shown)"); g_control.shots_written++; return; }
        QImage image(rgba.data(), w, h, w * 4, QImage::Format_RGBA8888);
        image.convertToFormat(QImage::Format_RGB888).save(QString::fromStdString(name));
        g_control.shots_written++;
        log_line("wrote " + name + " (" + std::to_string(w) + " x " + std::to_string(h) + ") at vertical blank " + std::to_string(blanks));
    }

    // decode_cpu: the decoder's processor time so far (the sink's figure), for "since the reset"
    void report_pace(bool reset, double decode_cpu) {
        Pace p;
        uint64_t blanks_now = blanks;
        double cpu_now = cpu_ms(), main_cpu_now = main_cpu_ms;
        {
            std::lock_guard<std::mutex> hold(pace_lock);
            p = pace;
            if (reset) { pace = Pace(); pace.cpu0 = cpu_now; pace.main_cpu0 = main_cpu_now; pace.decode_cpu0 = decode_cpu; pace.blanks0 = blanks_now; }
        }
        double load[3] = {0, 0, 0};
        getloadavg(load, 3);
        if (!p.slack.empty()) {
            double sum = 0;
            for (float v : p.slack) sum += v;
            p.slack_mean = sum / p.slack.size();
            size_t at = (size_t)(0.05 * (p.slack.size() - 1) + 0.5);
            std::nth_element(p.slack.begin(), p.slack.begin() + at, p.slack.end());
            p.slack_low = p.slack[at];
        }
        double span = p.last - p.first, n = p.presents > 1 ? (double)(p.presents - 1) : 1;
        printf("rta_app: pacing: %llu pictures in %.0f ms: %.3f a second (display %.2f Hz, %s); a picture stood for",
               (unsigned long long)p.presents, span, span > 0 ? 1000.0 * n / span : 0.0, refresh_hz,
               opt.unpaced ? "not paced" : display_locked ? "locked to the display" : "clock");
        for (int k = 0; k < 8; k++) if (p.by_refreshes[k]) printf(" %d%s refreshes: %llu;", k, k == 7 ? "+" : "", (unsigned long long)p.by_refreshes[k]);
        printf(" longest %.1f ms; the swap waited for the display %llu times (%.2f ms on average), the clock held %llu, %llu restarts after a stall; load average %.0f\n",
               p.worst_ms, (unsigned long long)p.swap_waited, p.presents ? p.swap_ms / p.presents : 0.0, (unsigned long long)p.timer_waited,
               (unsigned long long)p.late_starts, load[0]);
        if (!p.pipe.values.empty()) {
            auto f = [](const app::Figure& g) {
                static char text[8][64];
                static int at = 0;
                char* out = text[at++ & 7];
                snprintf(out, 64, "%.2f / %.2f / %.1f", g.mean(), g.percentile(0.95), g.most);
                return out;
            };
            printf("rta_app: path: per picture, ms of wall time (average / 95th percentile / longest): game side %s; waiting for the decoder to take it %s;",
                   f(p.game), f(p.slot_wait));
            printf(" in the decoder's place %s; decoder %s; to the window's thread %s; OpenGL %s; drawn, until the swap is asked for %s; in the swap %s\n",
                   f(p.decoder_idle), f(p.decode), f(p.queue), f(p.gl), f(p.to_swap), f(p.swap));
            printf("rta_app: path: from letting the game go to the drawn picture, without what it stood behind the picture before, %s ms", f(p.pipe));
            if (pacer && pacer->mode == app::Pacer::AHEAD)
                printf("; the game is let go %.2f ms ahead of the picture's moment now; a drawn picture was there %.2f ms before its moment on average "
                       "(5th percentile %.2f); %llu of %zu were on screen more than half a refresh late - the longest part then: game %llu, decoder %llu, OpenGL %llu, "
                       "swap %llu, a wait between them %llu; %llu drawn and not shown (overtaken); the grid was started again %llu times and moved %.1f ms toward the display in all; "
                       "the game's thread woke %.2f ms after the time it asked for on average; %llu pictures' moments were set against the display link (%llu refreshes told by it)",
                       pacer->lead_ms.load(), p.slack_mean, p.slack_low, (unsigned long long)p.late, p.pipe.values.size(),
                       (unsigned long long)p.late_by[0], (unsigned long long)p.late_by[1], (unsigned long long)p.late_by[2], (unsigned long long)p.late_by[3],
                       (unsigned long long)p.late_by[4], (unsigned long long)p.overtaken, (unsigned long long)pacer->resyncs.load(), pacer->slewed_ms.load(),
                       pacer->wakes.load() ? pacer->woke_late_ms.load() / pacer->wakes.load() : 0.0, (unsigned long long)link_timed,
                       (unsigned long long)g_display.ticks.load());
            printf("\n");
        }
        if (p.glass || p.glass_never) {
            printf("rta_app: on the glass (told by the system for every picture handed to the Metal layer): %llu shown, %llu never (window hidden, or dropped); a picture stood for",
                   (unsigned long long)p.glass, (unsigned long long)p.glass_never);
            for (int k = 0; k < 8; k++) if (p.glass_by_refreshes[k]) printf(" %d%s refreshes: %llu;", k, k == 7 ? "+" : "", (unsigned long long)p.glass_by_refreshes[k]);
            // The system's compositor puts a window's picture on the glass a fixed number of refreshes after
            // it is handed over: "the usual" is the median, and a picture is early or late against that.
            double usual = p.glass_after_due.percentile(0.5) - 1000.0;
            uint64_t early = 0, late = 0;
            for (float v : p.glass_after_due.values) { double off = v - 1000.0 - usual; if (off > 0.5 * refresh_ms) late++; else if (off < -0.5 * refresh_ms) early++; }
            printf(" longest %.1f ms; on the glass %.2f ms after the moment the program meant (the median: %.2f refreshes, the compositor's own delay); "
                   "against that %llu came a refresh or more early and %llu late (the latest %.1f ms)\n",
                   p.glass_worst_ms, usual, usual / refresh_ms, (unsigned long long)early, (unsigned long long)late, p.glass_after_due.most - 1000.0 - usual);
        }
        double pictures = blanks_now > p.blanks0 ? (double)(blanks_now - p.blanks0) : 1;
        printf("rta_app: processor time per picture since the figures were last reset (%.0f pictures): %.2f ms over all threads; of it the decoder %.2f ms, "
               "the window's thread (OpenGL) %.2f ms, everything else (the game, the runtime, sound, art readers) %.2f ms\n", pictures,
               (cpu_now - p.cpu0) / pictures, (decode_cpu - p.decode_cpu0) / pictures, (main_cpu_now - p.main_cpu0) / pictures,
               ((cpu_now - p.cpu0) - (decode_cpu - p.decode_cpu0) - (main_cpu_now - p.main_cpu0)) / pictures);
        fflush(stdout);
    }
};

static Screen* g_screen;
static app::Sink* g_sink;
static Recorder g_recorder;                             // between the runtime and the sink; writes only while a file is open

static void final_report() {                            // on the game's thread, when the run ends
    Screen& s = *g_screen;
    double wall = now_ms() - s.start_ms, cpu = cpu_ms() - s.start_cpu, n = s.blanks ? (double)s.blanks : 1;
    printf("rta_app: %llu vertical blanks in %.0f ms: %.1f pictures a second of wall time at %d x %d (%s)\n", (unsigned long long)s.blanks, wall,
           1000.0 * n / wall, s.opt.size_w, s.opt.size_h, s.opt.offscreen ? "no window" : "window");
    printf("rta_app: per picture %.2f ms of processor time over all threads; the thread that draws %.2f ms in OpenGL and the swap; %.0f vertices, %.0f draw commands "
           "sent as %.0f draw calls\n", cpu / n, s.draw_ms / n, s.vertices / n, s.commands / n, (double)s.backend->draw_calls() / n);
    if (g_sink && g_sink->blanks) {
        double b = (double)g_sink->blanks;
        printf("rta_app: per picture, by stage: game side %.2f ms of wall time (translated game, runtime, sound, the sink's copying); decoder %.2f ms of wall time, "
               "%.2f ms of its own processor time (VIF1, VU1, GS model)\n", g_sink->game_ms / b, g_sink->decode_wall_ms / b, g_sink->decode_cpu_ms / b);
    }
    s.report_pace(false, g_sink ? g_sink->decode_cpu_ms : 0.0);
    apprt::films_report();
    printf("rta_app: %s\n", fpcontrols::figures().c_str());
    {
        const render::GsStats& g = g_renderer->gs.stats;
        printf("rta_app: memory %.1f MB; textures made %llu, held %llu (%.1f MB as RGBA), freed %llu; draws without their texture %llu; surface copies %llu, "
               "transfers inside GS memory not carried out %llu; VU1 instructions not implemented %llu; GS registers unknown %llu\n", memory_mb(),
               (unsigned long long)g.textures_made, (unsigned long long)g.textures_held, g.texture_bytes / 1048576.0, (unsigned long long)g.textures_freed,
               (unsigned long long)g.texture_missing, (unsigned long long)g.copies, (unsigned long long)g.copies_skipped,
               (unsigned long long)g_renderer->vif.vu.bad, (unsigned long long)g.unknown_regs);
        printf("rta_app: primitives drawn with GS state the model approximates (of %llu):", (unsigned long long)g.prims);
        bool any = false;
        for (int k = 0; k < render::AP_COUNT; k++) if (g.approx[k]) { printf(" %s %llu;", render::Gs::APPROX_NAMES[k], (unsigned long long)g.approx[k]); any = true; }
        printf("%s; with fogging (applied): %llu\n", any ? "" : " none", (unsigned long long)g.fogged);
    }
    {
        PictureFigures fig = s.backend->figures();
        const render::Layout& l = g_renderer->gs.layout;
        uint64_t wide = 0, clamps = 0, marks = 0;
        gfxrt::figures(wide, clamps, marks);
        uint32_t list_most = 0, list_room = 0;
        gfxrt::list_figures(list_most, list_room);
        printf("rta_app: picture: the game's display list: the fullest frame took %u of %u units (objects are no longer drawn when fewer than 3000 are left)\n",
               list_most, list_room);
        printf("rta_app: picture: view %.4f (k %.4f), %llu frames built wide, %llu marks in the stream; 2-D primitives moved %llu in %llu clusters, sprites narrowed %llu, "
               "left across the width %llu; the screen clamp was handed the 4:3 planes %llu times\n", s.view_aspect, l.k, (unsigned long long)wide,
               (unsigned long long)marks, (unsigned long long)l.moved_2d, (unsigned long long)l.clusters, (unsigned long long)l.moved_sprites,
               (unsigned long long)l.kept_full, (unsigned long long)clamps);
        printf("rta_app: picture: %d samples, anisotropy %d; art pack %llu files: textures named %llu, found in the pack %llu, pictures read %llu (%llu as parts), "
               "read again for a larger part %llu, given up unread %llu, dropped for memory %llu; mip-mapped parts of the game's own textures made %llu; "
               "held now %llu pictures, %.1f MB (most %.1f MB), %llu waiting\n", fig.samples, fig.anisotropy, (unsigned long long)fig.pack_files,
               (unsigned long long)fig.named, (unsigned long long)fig.named_found, (unsigned long long)fig.replaced, (unsigned long long)fig.parts,
               (unsigned long long)fig.regrown, (unsigned long long)fig.abandoned, (unsigned long long)fig.dropped, (unsigned long long)fig.own_made,
               (unsigned long long)fig.held, fig.held_bytes / 1048576.0, fig.most_bytes / 1048576.0, (unsigned long long)fig.pending);
    }
    printf("rta_app: input: %llu key events, controller %s, %u rumble commands\n", (unsigned long long)g_key_events.load(),
           hostpad::name().empty() ? "none" : hostpad::name().c_str(), g_pads.rumbles.load());
    {
        unsigned threads_now = 0, threads_made = 0, threads_ended = 0;
        apprt::thread_figures(threads_now, threads_made, threads_ended);
        printf("rta_app: the game's threads: %u now, %u started in all, %u ended by the game from outside (TerminateThread)\n", threads_now, threads_made, threads_ended);
    }
    if (s.presenter) {
        unsigned long long presented = 0, refused = 0, skipped = 0;
        double longest = 0;
        hostpresent::figures(s.presenter, presented, refused, skipped, longest);
        printf("rta_app: present: %llu pictures handed to the window's Metal layer; %llu times it had no drawable of the right size (a resize under way); "
               "%llu pictures not shown because the ones before were still on their way; the layer's longest wait for a drawable %.1f ms (the drawing thread does not wait for it)\n",
               presented, refused, skipped, longest);
    }
    if (g_stall.on)
        printf("rta_app: stalls (RTA_STALL_LOG): a list waited more than %.0f ms for the thread that draws (%s) %llu times, longest %.1f ms, %.0f ms in all; "
               "the window's own thread stayed away from its event loop for more than %.0f ms %llu times, longest %.1f ms, %.0f ms in all\n",
               g_stall.after_ms, s.own_thread ? "a thread of its own" : "the window's own thread", (unsigned long long)g_stall.stalls.load(), g_stall.longest_ms.load(),
               g_stall.total_ms.load(), g_main_stall.after_ms, (unsigned long long)g_main_stall.stalls.load(), g_main_stall.longest_ms.load(), g_main_stall.total_ms.load());
    fflush(stdout);
}

// What the process holds in memory now (macOS: the footprint Activity Monitor shows).
#ifdef __APPLE__
#include <mach/mach.h>
static double memory_mb() {
    task_vm_info_data_t vm;
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&vm, &count) != KERN_SUCCESS) return 0;
    return (double)vm.phys_footprint / 1048576.0;
}
#else
static double memory_mb() { rusage u; getrusage(RUSAGE_SELF, &u); return (double)u.ru_maxrss / 1024.0; }
#endif

// One line of key=value figures for the control socket's `info` (read on the game's
// thread while the other threads count: figures, not a consistent snapshot).
static std::string info_line() {
    Screen& s = *g_screen;
    const render::GsStats& g = g_renderer->gs.stats;
    char text[1536];
    int n = snprintf(text, sizeof text, "ms=%.0f cpu_ms=%.0f pictures=%llu memory_mb=%.1f tex_made=%llu tex_held=%llu tex_freed=%llu tex_mb=%.1f tex_missing=%llu "
                     "copies=%llu copies_skipped=%llu vu_bad=%llu gs_unknown=%llu draws=%llu fields=%llu machine_s=%.3f",
                     now_ms() - s.start_ms, cpu_ms() - s.start_cpu, (unsigned long long)s.blanks, memory_mb(), (unsigned long long)g.textures_made,
                     (unsigned long long)g.textures_held, (unsigned long long)g.textures_freed, g.texture_bytes / 1048576.0, (unsigned long long)g.texture_missing,
                     (unsigned long long)g.copies, (unsigned long long)g.copies_skipped, (unsigned long long)g_renderer->vif.vu.bad,
                     (unsigned long long)g.unknown_regs, (unsigned long long)s.backend->draw_calls(), (unsigned long long)apprt::fields(), apprt::machine_seconds());
    n += snprintf(text + n, sizeof text - n, " fogged=%llu targets_held=%llu targets_freed=%llu", (unsigned long long)g.fogged, (unsigned long long)g.targets_held,
                  (unsigned long long)g.targets_freed);
    for (int k = 0; k < render::AP_COUNT && n < (int)sizeof text - 120; k++)
        if (g.approx[k]) n += snprintf(text + n, sizeof text - n, " approx%d=%llu", k, (unsigned long long)g.approx[k]);
    unsigned threads_now = 0, threads_made = 0, threads_ended = 0;
    apprt::thread_figures(threads_now, threads_made, threads_ended);
    n += snprintf(text + n, sizeof text - n, " game_threads=%u game_threads_made=%u game_threads_ended=%u", threads_now, threads_made, threads_ended);
    {
        PictureFigures fig = s.backend->figures();     // (counters of the drawing thread, read as they stand)
        n += snprintf(text + n, sizeof text - n, " art_named=%llu art_found=%llu art_read=%llu art_held=%llu art_waiting=%llu", (unsigned long long)fig.named,
                      (unsigned long long)fig.named_found, (unsigned long long)fig.replaced, (unsigned long long)fig.held, (unsigned long long)fig.pending);
    }
    return std::string(text) + " " + apprt::sound_figures();
}

// ---- "app ..." script lines (game's thread) -------------------------------------------------
static std::mutex g_shot_lock;
static std::vector<std::string> g_shots_asked;           // picked up by the sink at this blank

static uint16_t parse_buttons(const std::string& text) {
    static const struct { const char* name; uint16_t bit; } names[] = {
        {"up", rta::PAD_UP}, {"down", rta::PAD_DOWN}, {"left", rta::PAD_LEFT}, {"right", rta::PAD_RIGHT}, {"cross", rta::PAD_CROSS},
        {"circle", rta::PAD_CIRCLE}, {"square", rta::PAD_SQUARE}, {"triangle", rta::PAD_TRIANGLE}, {"l1", rta::PAD_L1}, {"l2", rta::PAD_L2},
        {"l3", rta::PAD_L3}, {"r1", rta::PAD_R1}, {"r2", rta::PAD_R2}, {"r3", rta::PAD_R3}, {"start", rta::PAD_START}, {"select", rta::PAD_SELECT}};
    uint16_t bits = 0;
    size_t at = 0;
    while (at <= text.size()) {
        size_t plus = text.find('+', at);
        std::string one = text.substr(at, plus == std::string::npos ? std::string::npos : plus - at);
        for (auto& n : names) if (one == n.name) bits |= n.bit;
        if (plus == std::string::npos) break;
        at = plus + 1;
    }
    return bits;
}

static void app_command(const std::string& text, uint64_t frame) {
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
        std::lock_guard<std::mutex> hold(g_shot_lock);
        g_shots_asked.push_back(text.substr(text.find(w[1])));
    } else if (w[0] == "key" && w.size() >= 3) {
        int key = key_by_name(w[2]);
        bool down = w[1] == "down";
        if (!key || !g_screen->window) { log_line("app key: unknown key or no window: " + text); return; }
        QCoreApplication::postEvent(g_screen->window, new QKeyEvent(down ? QEvent::KeyPress : QEvent::KeyRelease, key, Qt::NoModifier));
    } else if (w[0] == "gcpad" && w.size() >= 2) {
        float v[6] = {0, 0, 0, 0, 0, 0};
        for (size_t k = 3; k < w.size() && k < 9; k++) v[k - 3] = (float)atof(w[k].c_str());
        hostpad::test(w[1], w.size() >= 3 ? parse_buttons(w[2]) : 0, v);
    } else if (w[0] == "pads") {
        uint32_t sticks = g_pads.last_sticks;
        printf("[frame %llu] rta_app: controller %s (generation %u); port 1 holds buttons %04x, sticks %u %u %u %u; keyboard bits %05x\n",
               (unsigned long long)frame, hostpad::name().empty() ? "none" : hostpad::name().c_str(), hostpad::generation(), g_pads.last_buttons.load(),
               sticks & 255, (sticks >> 8) & 255, (sticks >> 16) & 255, sticks >> 24, g_keys.load());
        fflush(stdout);
    } else if (w[0] == "record" && w.size() >= 2) {
        g_recorder.out.close();
        g_recorder.first_frame = ~0ull;                 // not active: everything passes straight through
        if (w[1] != "stop") {
            g_recorder.started = false;
            g_recorder.vu_data.clear();
            if (g_recorder.out.open(text.substr(text.find(w[1])).c_str())) g_recorder.first_frame = 0;
            else log_line("cannot write " + w[1]);
        }
    } else if (w[0] == "window" && w.size() >= 3) {
        // app window W H: the window takes this size (points), as a person dragging its corner would make it
        int ww = atoi(w[1].c_str()), wh = atoi(w[2].c_str());
        if (g_screen->window && ww >= 160 && wh >= 120)
            QCoreApplication::postEvent(g_screen, new CallQEvent([ww, wh] { g_screen->window->resize(ww, wh); }));
    } else if (w[0] == "fpc" && w.size() >= 2) {
        // app fpc mouse DX DY | button left|right|middle down|up | wheel N | set KEY VALUE | hud | log on|off | figures  (fpcontrols.h)
        printf("[frame %llu] fpc: %s\n", (unsigned long long)frame, fpcontrols::command(text.substr(text.find(w[1])), frame).c_str());
        fflush(stdout);
    } else if (w[0] == "option" && w.size() >= 3) {
        // app option game_hud on|off | game_hud_text on|off | music_volume 0..1: the names the Godot library's
        // rtag_set_option knows them by (settings.h has the same three as lines of the settings file)
        bool off = w[2] == "off" || w[2] == "no" || w[2] == "0";
        render::Gs& gs = g_renderer->gs;
        if (w[1] == "game_hud") gs.hide_edge = off;
        else if (w[1] == "game_hud_text") gs.hide_text = off;
        else if (w[1] == "music_volume") { if (!apprt::set_music_volume(atof(w[2].c_str()))) log_line("app option music_volume: this program has no sound library"); }
        else { log_line("app option: game_hud on|off, game_hud_text on|off, music_volume 0..1"); return; }
        gfxrt::set_hud_marks(gs.hide_edge || gs.hide_text);        // the marks that say who drew what are needed at 4:3 too while either is left out
        printf("[frame %llu] option: game_hud %s, game_hud_text %s%s\n", (unsigned long long)frame, gs.hide_edge ? "off" : "on", gs.hide_text ? "off" : "on",
               w[1] == "music_volume" ? (", music_volume " + w[2]).c_str() : "");
        fflush(stdout);
    } else if (w[0] == "view" && w.size() >= 2) {
        if (w[1] == "next") fpview::cycle(1);
        else if (w[1] == "set" && w.size() >= 4) { if (!fpview::setting(w[2].c_str(), w[3].c_str())) log_line("app view set: not a view setting: " + w[2]); }
        else if (w[1] == "info") {
            const fpview::View& v = fpview::view();
            printf("[frame %llu] view: selected %s, shown %s, blend %.2f%s%s; tick %u; eye %.1f %.1f %.1f forward %.3f %.3f %.3f fov %.1f near %.1f; "
                   "game eye %.1f %.1f %.1f yaw %.1f zoom %d; player %.1f %.1f %.1f facing %.1f pitch %.1f\n",
                   (unsigned long long)frame, fpview::mode_name(v.mode), fpview::mode_name(v.shown), v.blend, v.fallback ? "; the game's camera: " : "",
                   v.fallback_why, v.tick, v.eye.x, v.eye.y, v.eye.z, v.forward.x, v.forward.y, v.forward.z, v.fov, v.near_plane, v.game_eye.x, v.game_eye.y,
                   v.game_eye.z, v.game_yaw, v.game_zoom, v.player_pos.x, v.player_pos.y, v.player_pos.z, v.facing, v.look_pitch);
            fflush(stdout);
        } else if (fpview::mode_by_name(w[1].c_str()) >= 0) fpview::set_mode(fpview::mode_by_name(w[1].c_str()));
        else log_line("app view: overhead, action, chase, shoulder, first, next, info, or set KEY VALUE");
    } else if (w[0] == "fullscreen") {
        // app fullscreen: what F does (a test window stays as it is: it must not cover the screen)
        // (RTA_TEST_FULLSCREEN_OK=1: a test that has to see full screen work asks for it, for seconds)
        QCoreApplication::postEvent(g_screen, new CallQEvent([] {
            if (g_screen->window && (!g_screen->window->test || getenv("RTA_TEST_FULLSCREEN_OK"))) g_screen->window->toggle_fullscreen();
            else log_line("app fullscreen: not in a test window");
        }));
    } else if (w[0] == "art" && w.size() >= 2) {
        // the same frame with and without the pack's pictures (and the mip-mapped parts): app art off|on
        bool on = w[1] != "off";
        g_screen->on_drawing_thread([on] { g_screen->backend->set_replacements(on); });
    } else if (w[0] == "presented" && w.size() >= 2) {
        // app presented FILE.png: what the window's Metal layer was last handed, as it was handed (a test of the way into the window)
        std::string path = text.substr(text.find(w[1]));
        g_screen->on_drawing_thread([path] {
            std::vector<unsigned char> bgra;
            int pw = 0, ph = 0;
            if (!g_screen->presenter || !hostpresent::read(g_screen->presenter, bgra, pw, ph)) { log_line("app presented: nothing is presented through Metal"); return; }
            QImage image(bgra.data(), pw, ph, pw * 4, QImage::Format_ARGB32);
            image.convertToFormat(QImage::Format_RGB888).save(QString::fromStdString(path));
            log_line("wrote " + path + " (" + std::to_string(pw) + " x " + std::to_string(ph) + "), the window's picture as the Metal layer was handed it");
        });
    } else if (w[0] == "pointer") {
        // app pointer: is the pointer held as the look (look_host.h)?  app pointer click: a click of the left button in the window
        bool click = w.size() >= 2 && w[1] == "click";
        QCoreApplication::postEvent(g_screen, new CallQEvent([click] {
            GameWindow* win = g_screen->window;
            if (click && win) {
                QPointF at(win->width() / 2.0, win->height() / 2.0);
                QMouseEvent down(QEvent::MouseButtonPress, at, win->mapToGlobal(at), Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
                QMouseEvent up(QEvent::MouseButtonRelease, at, win->mapToGlobal(at), Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
                QCoreApplication::sendEvent(win, &down);
                QCoreApplication::sendEvent(win, &up);
            }
            log_line(hostlook::state() + "; the view wants it=" + (fpcontrols::wants_pointer() ? "1" : "0") + ", given back by Escape=" +
                     (win && win->pointer_let_go ? "1" : "0") + ", view " + fpview::mode_name(fpview::mode()));
        }));
    } else if (w[0] == "close") {
        // app close: what a click on the window's close button does (and Command-Q: the application asks its window to close)
        if (g_screen->window) QCoreApplication::postEvent(g_screen->window, new QEvent(QEvent::Close));
    } else if (w[0] == "help") {
        // app help [show|hide|info]: the keys panel (help_host.h), for tests
        log_line(hosthelp::test(w.size() >= 2 ? w[1] : "info"));
    } else if (w[0] == "stats") {
        g_screen->report_pace(w.size() >= 2 && w[1] == "reset", g_sink ? g_sink->decode_cpu_ms : 0.0);
    } else if (w[0] == "latency" && w.size() >= 2) {
        Latency& t = g_latency;
        std::lock_guard<std::mutex> hold(t.lock);
        if (w[1] == "report") {
            // differences between consecutive pictures: the largest before the press is the
            // noise (an idle animation); the first after it above three times that, and
            // above 1, is the answer
            // (the largest difference of one cell, not the mean over the picture: a moved
            // menu highlight changes a few cells much and the mean hardly at all, while a
            // moving backdrop changes every cell a little)
            auto diff = [&](size_t k) {
                int d = 0;
                for (size_t i = 0; i < t.samples[k].grid.size(); i++) d = std::max(d, abs((int)t.samples[k].grid[i] - (int)t.samples[k - 1].grid[i]));
                return (double)d;
            };
            double noise = 0;
            for (size_t k = 1; k < t.samples.size(); k++) if (t.samples[k].number <= t.press_blank) noise = std::max(noise, diff(k));
            double limit = std::max(2 * noise, noise + 2);
            bool found = false;
            for (size_t k = 1; k < t.samples.size() && !found; k++)
                if (t.samples[k].number > t.press_blank && diff(k) > limit) {
                    found = true;
                    printf("[frame %llu] rta_app: latency: buttons %04x given to the game's controller read at vertical blank %llu; the first changed picture is that of blank %llu: "
                           "%llu pictures after the press, presented %.1f ms after it (difference %.2f against %.2f before the press; state %d, %zu pictures looked at)\n",
                           (unsigned long long)frame, t.buttons, (unsigned long long)t.press_blank, (unsigned long long)t.samples[k].number,
                           (unsigned long long)(t.samples[k].number - t.press_blank), t.samples[k].presented_ms - t.press_ms, diff(k), noise, t.state, t.samples.size());
                }
            if (!found) printf("[frame %llu] rta_app: latency: no picture changed after the press at blank %llu (noise %.2f, state %d, %zu pictures)\n", (unsigned long long)frame,
                               (unsigned long long)t.press_blank, noise, t.state, t.samples.size());
            fflush(stdout);
            t.state = 0;
        } else {
            t.buttons = parse_buttons(w[1]);
            t.after = w.size() >= 3 ? atoi(w[2].c_str()) : 40;
            t.before = w.size() >= 4 ? atoi(w[3].c_str()) : 12;
            t.samples.clear();
            t.arm_blank = 0; t.press_blank = 0;
            t.state = 1;
        }
    } else log_line("unknown app command: " + text);
}

// The sink with the pictures a script asked for travelling along with their frame.
struct AppSink : app::Sink {
    std::mutex notes_lock;
    std::vector<std::pair<uint64_t, std::string>> notes;     // (blank number, path), game thread -> decoder
    void vblank(unsigned field, uint64_t number) override {
        // the control socket's commands of this blank: a picture it asks for is this blank's,
        // what it presses is read by the controller read that follows
        control().on_blank(number);
        {
            std::lock_guard<std::mutex> hold(g_shot_lock);
            if (!g_shots_asked.empty()) {
                std::lock_guard<std::mutex> hold2(notes_lock);
                for (auto& path : g_shots_asked) notes.push_back({number, path});
                g_shots_asked.clear();
            }
        }
        app::Sink::vblank(field, number);
    }
    void take(uint64_t number, std::vector<std::string>& out) {
        std::lock_guard<std::mutex> hold(notes_lock);
        for (size_t k = 0; k < notes.size();)
            if (notes[k].first <= number) { out.push_back(notes[k].second); notes.erase(notes.begin() + k); } else k++;
    }
};

static bool file_exists(const std::string& path) { struct stat st; return stat(path.c_str(), &st) == 0; }

int main(int argc, char** argv) {
    Options opt;
    std::vector<std::pair<std::string, std::string>> overrides;     // picture settings given on the command line
    bool plain = false, no_settings = false;
    std::vector<std::string> pass, script_args;
    std::string mode = "boot";
    if (const char* disc = getenv("RTA_DISC")) opt.disc = disc;
    if (const char* way = getenv("RTA_PRESENT")) opt.metal = !strcmp(way, "metal");
    int k = 1;
    for (; k < argc; k++) {
        std::string a = argv[k];
        auto next = [&]() -> std::string { return k + 1 < argc ? argv[++k] : ""; };
        if (a == "--") { k++; break; }
        else if (a == "--disc") opt.disc = next();
        else if (a == "--data") opt.data = next();
        else if (a == "--elf") opt.elf = next();
        else if (a == "--window") overrides.push_back({"window", next()});
        else if (a == "--size") overrides.push_back({"resolution", next()});
        else if (a == "--scale") overrides.push_back({"resolution", next() + "x"});
        else if (a == "--fullscreen") overrides.push_back({"fullscreen", "yes"});
        else if (a == "--aspect") overrides.push_back({"aspect", next()});
        else if (a == "--resolution") overrides.push_back({"resolution", next()});
        else if (a == "--antialiasing" || a == "--aa") overrides.push_back({"antialiasing", next()});
        else if (a == "--anisotropy") overrides.push_back({"anisotropy", next()});
        else if (a == "--mipmaps") overrides.push_back({"mipmaps", next()});
        else if (a == "--art-pack") overrides.push_back({"art_pack", next()});
        else if (a == "--art-memory") overrides.push_back({"art_memory", next()});
        else if (a == "--frame-cap") overrides.push_back({"frame_cap", next()});
        else if (a == "--view") overrides.push_back({"view", next()});
        else if (a == "--game-hud") overrides.push_back({"game_hud", next()});
        else if (a == "--game-hud-text") overrides.push_back({"game_hud_text", next()});
        else if (a == "--music-volume") overrides.push_back({"music_volume", next()});
        else if (a == "--view-set") { std::string kv = next(); size_t eq = kv.find('='); if (eq != std::string::npos) overrides.push_back({kv.substr(0, eq), kv.substr(eq + 1)}); }
        else if (a == "--plain") plain = true;
        else if (a == "--settings") opt.settings_file = next();
        else if (a == "--no-settings") no_settings = true;
        else if (a == "--no-layout") opt.layout = false;
        else if (a == "--art-whole") opt.art_parts = false;
        else if (a == "--art-wait") opt.art_wait = true;
        else if (a == "--volume") opt.volume = atof(next().c_str());
        else if (a == "--mute") opt.volume = 0;
        else if (a == "--no-sound") opt.no_sound = true;
        else if (a == "--emulator-timing") opt.emulator_timing = true;
        else if (a == "--no-films") opt.no_films = true;
        else if (a == "--script" || a == "--do") { script_args.push_back(a); script_args.push_back(next()); }
        else if (a == "--offscreen") opt.offscreen = true;
        else if (a == "--unpaced") overrides.push_back({"frame_cap", "0"});
        else if (a == "--present") { std::string way = next(); opt.metal = way == "metal"; if (way != "metal" && way != "opengl") { fprintf(stderr, "rta_app: --present metal|opengl\n"); return 2; } }
        else if (a == "--pacing") { std::string way = next(); opt.queued = way == "queued"; if (way != "queued" && way != "ahead") { fprintf(stderr, "rta_app: --pacing ahead|queued\n"); return 2; } }
        else if (a == "--test") opt.test = next();
        else if (a == "--png") opt.png = next();
        else if (a == "--at") { std::string s = next(); for (char* p = &s[0]; *p;) { opt.at.insert(strtoull(p, &p, 10)); if (*p) p++; } }
        else if (a == "--stop-after") opt.stop_after = strtoull(next().c_str(), nullptr, 10);
        else if (a == "--control") opt.control = next();
        else if (a == "--help" || a == "-h") {
            printf("picture (each also a line of <data>/settings.txt, see tools/recomp/app/settings.h):\n"
                   "        [--aspect auto|4:3|16:9|16:10|21:9|W:H] [--resolution window|WxH|Nx] [--antialiasing off|2|4|8] [--anisotropy 1..16]\n"
                   "        [--mipmaps yes|no] [--art-pack DIR] [--art-memory MB] [--frame-cap 60|30|0] [--plain] [--settings FILE] [--no-settings]\n"
                   "        [--view overhead|action|chase|shoulder|first] [--view-set view.<mode>.<name>=VALUE]   (V switches while the game runs)\n"
                   "        [--game-hud on|off] [--game-hud-text on|off] [--music-volume 0..1]   (the game's own HUD layer; its boss meter, message and prompt box; the music alone)\n"
                   "        [--pacing ahead|queued] [--present metal|opengl]   (opengl: the way into the window used until 2026-10-13 - if the picture looks wrong)\n");
            printf("rta_app --disc IMAGE [--data DIR] [--window WxH] [--fullscreen] [--scale N | --size WxH] [--volume V | --mute | --no-sound]\n"
                   "        [--emulator-timing] [--script FILE] [--do COMMAND] [--test TEXT] [--offscreen] [--unpaced] [--png PREFIX --at n,..]\n"
                   "        [--stop-after N] [-- runtime arguments]\n"
                   "keys: W A S D left stick; arrows direction pad; I J K L triangle square cross circle; Q E L1 R1; 1 3 L2 R2; X C L3 R3;\n"
                   "      Return Start; Backspace Select; F or F11 full screen; Escape leaves full screen; V the next camera view; F1 shows this list beside the window\n"
                   "(the head of tools/recomp/app/app_main.cpp describes every option)\n");
            return 0;
        }
        else { fprintf(stderr, "rta_app: unknown option %s (see --help; the runtime's own arguments go after --)\n", a.c_str()); return 2; }
    }
    for (; k < argc; k++) pass.push_back(argv[k]);
    if (!pass.empty() && (pass[0] == "boot" || pass[0] == "resume")) { mode = pass[0]; pass.erase(pass.begin()); }
    bool first_start = false;                                               // nobody has played from this data directory before
    bool settings_later = opt.settings_file.empty() && !no_settings;       // <data>/settings.txt, once the data directory is known
    auto apply_settings = [&](const std::string& file) {
        if (!file.empty() && !opt.set.load(file, log_line) && file == opt.settings_file) log_line("cannot read the settings file " + file);
        if (plain) opt.set.plain();
        for (auto& kv : overrides) opt.set.set(kv.first, kv.second);
        opt.window_w = opt.set.window_w; opt.window_h = opt.set.window_h;
        opt.fullscreen = opt.set.fullscreen;
        opt.size_w = opt.set.size_w; opt.size_h = opt.set.size_h; opt.scale = opt.set.scale;
        opt.aspect = opt.set.aspect;
        opt.unpaced = opt.set.frame_cap <= 0;
        for (auto& kv : opt.set.view)
            if (!fpview::setting(kv.first.c_str(), kv.second.c_str()) && !fpcontrols::setting(kv.first.c_str(), kv.second.c_str())) log_line("settings: not a view setting: " + kv.first + " = " + kv.second);
        opt.set.view.clear();
    };
    if (!settings_later) apply_settings(opt.settings_file);

    if (opt.offscreen || !opt.test.empty()) qputenv("QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM", "1");   // no Dock icon, never in front
    QSurfaceFormat format;
    format.setVersion(4, 1);
    format.setProfile(QSurfaceFormat::CoreProfile);
    format.setDepthBufferSize(0);
    format.setSwapInterval(opt.unpaced ? 0 : 1);
    QSurfaceFormat::setDefaultFormat(format);
    int qt_argc = 1;
    QGuiApplication qapp(qt_argc, argv);
    QGuiApplication::setApplicationDisplayName(opt.test.empty() ? TITLE : "AGENT TEST");

    // where things are: <root>/local/recomp-out/bin/rta_app
    std::string bin = QCoreApplication::applicationDirPath().toStdString();
    std::string out = bin + "/..", root = bin + "/../../..";
    if (opt.data.empty()) opt.data = out + "/app-data";
    mkdir(opt.data.c_str(), 0755);
    if (settings_later) {
        // the file beside the memory cards; a first run that somebody plays writes one to edit
        std::string file = opt.data + "/settings.txt";
        bool there = file_exists(file);
        apply_settings(there ? file : std::string());
        if (!there && opt.test.empty() && !opt.offscreen) { app::Settings().save(file, (std::string(fpview::settings_text()) + "\n" + fpcontrols::settings_text()).c_str()); first_start = true; }
    }
    if (mode == "boot") {
        // Something is wrong with what was given as the disc: said on the terminal, and to a
        // person (not a test, not a run without a window) in a box as well.
        bool person = opt.test.empty() && !opt.offscreen;
        auto refuse = [&](const std::string& headline, const std::string& text) {
            fprintf(stderr, "rta_app: %s. %s\n", headline.c_str(), text.c_str());
            if (person) hosthelp::box(headline, text);
        };
        const std::string how = "Start the program with your own disc image of Champions: Return to Arms (the US disc, SLUS-20973, version 2.00):\n"
                                "rta_app --disc \"/path/to/image.iso\"\n(or set RTA_DISC to that path; a launcher names the path it expects inside itself).";
        if (opt.disc.empty()) { refuse("No disc image was given", how); return 1; }
        if (!file_exists(opt.disc)) { refuse("The disc image was not found", "There is no file at\n" + opt.disc + "\n(if that is a link, what it points to is gone).\n\n" + how); return 1; }
        uint32_t figure = 0;
        int disc_kind = apprt::disc_check(opt.disc, figure);
        if (disc_kind == 0) { refuse("This file is not a disc image the program can read", opt.disc + "\n\nAn .iso file of the game's DVD is expected.\n\n" + how); return 1; }
        if (disc_kind == 1) { refuse("This disc image is another game", opt.disc + "\nhas no file SLUS_209.73.\n\n" + how); return 1; }
        char found[32];
        snprintf(found, sizeof found, "%08X", figure);
        if (figure != 0x4028A55Fu) {
            // not refused: the levels and pictures may still fit - but said plainly
            std::string text = opt.disc + "\nis another version of the game than the one this program is made from (its executable has the figure " + found +
                               "; version 2.00 of SLUS-20973 has 4028A55F). The program runs its own copy of the game's code and reads everything else "
                               "from this image: it may stop or look wrong.";
            fprintf(stderr, "rta_app: WARNING: %s\n", text.c_str());
            if (person) hosthelp::box("This disc image is another version of the game", text);
        } else log_line("disc: Champions: Return to Arms, SLUS-20973 version 2.00 (figure " + std::string(found) + "): " + opt.disc);
        if (opt.elf.empty()) {
            opt.elf = root + "/SLUS_209.73";
            if (!file_exists(opt.elf)) {
                opt.elf = opt.data + "/SLUS_209.73";
                if (!file_exists(opt.elf) && !apprt::extract_from_disc(opt.disc, "\\SLUS_209.73;1", opt.elf)) {
                    fprintf(stderr, "rta_app: SLUS_209.73 is not on this disc image: %s\n", opt.disc.c_str());
                    return 1;
                }
            }
        }
    }

    static AppSink sink;
    static Screen screen;
    screen.opt = opt;
    screen.pacer = &sink.pacer;
    screen.create();
    g_screen = &screen;
    // RTA_STALL_LOG: the main thread's event loop is watched as well - a timer that should
    // come by every 8 ms
    g_main_stall.start();
    // the pointer belongs to the look while a look view is played in the window that has the keyboard
    static QTimer pointer_watch;
    if (opt.test.empty() && !opt.offscreen) {
        hostlook::start();
        QObject::connect(&pointer_watch, &QTimer::timeout, [] {
            GameWindow* w = g_screen ? g_screen->window : nullptr;
            hostlook::capture(w && !w->test && w->isActive() && !w->pointer_let_go && fpcontrols::wants_pointer());
        });
        pointer_watch.start(50);
    }
    static QTimer heartbeat;
    if (g_main_stall.on) {
        g_main_stall.after_ms += 8;
        heartbeat.setTimerType(Qt::PreciseTimer);
        QObject::connect(&heartbeat, &QTimer::timeout, [] { g_main_stall.beat(); });
        heartbeat.start(8);
    }
    hostpad::start(log_line);
    // what a person has to be told (help_host.h): the keys on the terminal at every start
    // somebody plays, in a panel beside the window at the first one, and under F1 and Help
    if (!opt.offscreen) {
        hosthelp::start();
        if (opt.test.empty()) {
            fprintf(stderr, "\n%s\n\n", hosthelp::keys_text().c_str());
            fflush(stderr);
            if (first_start) {
                log_line("first start with this data directory: settings are in " + opt.data + "/settings.txt (a text file you can edit), memory cards in " +
                         opt.data + "/card");
                hosthelp::show();
            }
        }
    }
    // the picture's threads and the game's are the player's own work, not background work
    app::interactive_thread();
    apprt::interactive_threads();
    hostpad::keep_timers();

    static Renderer renderer;
    g_renderer = &renderer;
    renderer.gs.layout.enabled = opt.layout;
    renderer.gs.name_textures = !opt.set.art_pack.empty();
    gfxrt::install();
    fpview::install();
    // the game's own HUD layer and its second group left out, the music's own volume (settings.h; "app option ...")
    renderer.gs.hide_edge = !opt.set.game_hud;
    renderer.gs.hide_text = !opt.set.game_hud_text;
    gfxrt::set_hud_marks(renderer.gs.hide_edge || renderer.gs.hide_text);
    if (opt.set.music_volume < 1.0) apprt::set_music_volume(opt.set.music_volume);
    // the picture of a look view: its centre on the walking direction, the kick of swings and hits (fpcontrols.h)
    fpview::on_view([](fpview::View& v, Ctx*, void*) {
        if (v.shown != v.mode) return;
        float forward[3] = {v.forward.x, v.forward.y, v.forward.z}, up[3] = {v.up.x, v.up.y, v.up.z};
        fpcontrols::apply_view(v.mode, forward, up);
        v.forward = {forward[0], forward[1], forward[2]};
        v.up = {up[0], up[1], up[2]};
    });
    // the strafe mode (the fix set's section, when the game has it): asked for by game message 4 through the
    // section's own sender, from the draw pass - where the game's own HUD code sends its messages from
    // (Not while another machine's controller rows are replayed - the replay rule of Pads::read: a game message is
    // input like a row, and a replay is given its input whole.  A script may then set the mode itself: 13.2.)
    fpview::on_drawn([](const fpview::View&, Ctx* c, void*) {
        static const bool replayed = apprt::replaying();
        int mode = fpcontrols::take_strafe_send();
        if (mode >= 0 && !replayed) apprt::call_game(c, fpcontrols::STRAFE_SENDER, (uint32_t)mode);
    });
    if (getenv("RTA_GS_LOG")) renderer.gs.log_display = true;
    if (const char* keep = getenv("RTA_TEX_KEEP")) renderer.gs.texture_keep_frames = (uint32_t)atoi(keep);    // frames an unused texture is kept; 0 = for ever
    g_sink = &sink;
    sink.renderer = &renderer;
    sink.resumed = mode == "resume";
    sink.waited_downstream_ms = &screen.submit_wait_ms;
    renderer.on_frame = [](FrameList& frame) {
        static std::vector<std::string> shots;
        sink.take(frame.number, shots);
        g_screen->submit(frame, shots, sink.current);
    };
    sink.start();

    apprt::set_command_handler(app_command);
    apprt::set_finish_handler(final_report);
    if (!opt.control.empty()) {
        g_control.buttons_of = parse_buttons;
        // as a script's "app" line: through the network's commands (online ..., net ...) when the
        // network is linked, then to this program's own
        g_control.app_command = [](const std::string& text, uint64_t frame) { apprt::command(text, frame); fflush(stdout); };
        g_control.shot = [](const std::string& path) { std::lock_guard<std::mutex> hold(g_shot_lock); g_shots_asked.push_back(path); };
        g_control.quit = [] { apprt::finish(0); };
        g_control.info = info_line;
        if (!g_control.start(opt.control)) { fprintf(stderr, "rta_app: cannot listen on %s\n", opt.control.c_str()); return 1; }
    }

    // the runtime's arguments
    static std::vector<std::string> args = {argv[0], mode};
    if (mode == "boot") { args.push_back("--elf"); args.push_back(opt.elf); }
    if (!opt.disc.empty()) { args.push_back("--disc"); args.push_back(opt.disc); }
    args.push_back("--card"); args.push_back(opt.data + "/card");
    if (opt.emulator_timing) args.push_back("--emulator-timing");
    // the films: the game's own player runs when the decoder behind it is linked (film.cpp)
    if (apprt::films_linked() && !opt.no_films) { args.push_back("--opt"); args.push_back("films=original"); }
    if (!opt.no_sound) {
        bool silent = !opt.test.empty() || opt.offscreen;       // a test makes no sound, whatever was asked
        char gain[32];
        snprintf(gain, sizeof gain, "sound-gain=%.3f", silent ? 0.0 : opt.volume < 0 ? 0.0 : opt.volume > 1 ? 1.0 : opt.volume);
        args.push_back("--opt"); args.push_back("sound-out=device");
        args.push_back("--opt"); args.push_back(gain);
        // Paced, the sound side runs by itself on the device's clock, as the console's does
        // (it goes on through a level load).  A run that goes as fast as it can, or without a
        // window, keeps the sound on the machine's clock: the same run, the same answers.
        bool own_clock = !opt.unpaced && !opt.offscreen;
        for (auto& a : pass) if (a.compare(0, 12, "sound-clock=") == 0) own_clock = false;      // said by hand after "--"
        if (own_clock) { args.push_back("--opt"); args.push_back("sound-clock=real"); }
    }
    if (!script_args.empty()) {                         // names for the script's expressions
        if (file_exists(root + "/names.tsv")) { args.push_back("--sym"); args.push_back(root + "/names.tsv"); }
        std::vector<std::string> found;
        if (DIR* dir = opendir((root + "/symbols").c_str())) {
            while (dirent* e = readdir(dir)) {
                std::string name = e->d_name;
                if (name.size() > 4 && name.compare(name.size() - 4, 4, ".tsv") == 0) found.push_back(root + "/symbols/" + name);
            }
            closedir(dir);
        }
        std::sort(found.begin(), found.end());
        for (auto& path : found) { args.push_back("--sym"); args.push_back(path); }
    }
    args.insert(args.end(), script_args.begin(), script_args.end());
    args.insert(args.end(), pass.begin(), pass.end());
    static std::vector<char*> run_args;
    for (auto& a : args) run_args.push_back(&a[0]);
    static rta::Hooks hooks;
    g_recorder.next = &sink;
    g_recorder.first_frame = ~0ull;
    hooks.video = &g_recorder;
    hooks.pad = &g_pads;
    std::thread game([] { app::interactive_thread(); rta::run((int)run_args.size(), run_args.data(), hooks); });
    game.detach();
    return qapp.exec();
}
