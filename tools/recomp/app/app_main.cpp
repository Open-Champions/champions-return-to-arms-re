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
//                         app stats [reset]        print the pacing figures so far
//                         app window W H           give the window this size (the view follows with --aspect auto)
//                         app fullscreen           what the F key does
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
// owns the window and OpenGL.  The window paces everything: one picture per 1/60 s, locked
// to the display's refresh when that is a multiple of 60 Hz, and the wait travels back
// through the two hand-overs to the game.
#include "app_rt.h"
#include "backend_gl.h"
#include "control.h"
#include "gfx_rt.h"
#include "pad_host.h"
#include "pipeline.h"
#include "recorder.h"
#include "settings.h"

#include <QCoreApplication>
#include <QEvent>
#include <QGuiApplication>
#include <QImage>
#include <QKeyEvent>
#include <QOffscreenSurface>
#include <QOpenGLContext>
#include <QOpenGLExtraFunctions>
#include <QScreen>
#include <QSurfaceFormat>
#include <QTimer>
#include <QWindow>

#include <atomic>
#include <cmath>
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

static const char* TITLE = "Champions: Return to Arms - native build (experimental)";
static render::Renderer* g_renderer;
static double memory_mb();

static double cpu_ms() {                                // processor time of the whole process
    rusage u;
    getrusage(RUSAGE_SELF, &u);
    return (u.ru_utime.tv_sec + u.ru_stime.tv_sec) * 1000.0 + (u.ru_utime.tv_usec + u.ru_stime.tv_usec) / 1000.0;
}

struct Options {
    int window_w = 960, window_h = 720, size_w = 0, size_h = 0, scale = 0;
    bool offscreen = false, unpaced = false, fullscreen = false, no_sound = false, emulator_timing = false, no_films = false;
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
    default: return 0;
    }
}
static int key_by_name(const std::string& name) {
    static const struct { const char* name; int key; } names[] = {
        {"w", Qt::Key_W}, {"a", Qt::Key_A}, {"s", Qt::Key_S}, {"d", Qt::Key_D}, {"up", Qt::Key_Up}, {"down", Qt::Key_Down},
        {"left", Qt::Key_Left}, {"right", Qt::Key_Right}, {"i", Qt::Key_I}, {"j", Qt::Key_J}, {"k", Qt::Key_K}, {"l", Qt::Key_L},
        {"q", Qt::Key_Q}, {"e", Qt::Key_E}, {"1", Qt::Key_1}, {"3", Qt::Key_3}, {"x", Qt::Key_X}, {"c", Qt::Key_C},
        {"return", Qt::Key_Return}, {"backspace", Qt::Key_Backspace}, {"escape", Qt::Key_Escape}, {"f", Qt::Key_F}};
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
        if (port == 0) control().on_blank(frame);
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
    void toggle_fullscreen() { if (visibility() == QWindow::FullScreen) showNormal(); else showFullScreen(); }

  protected:
    void keyPressEvent(QKeyEvent* e) override {
        if (e->isAutoRepeat()) return;
        g_key_events++;
        if (uint32_t bit = key_bit(e->key())) { g_keys |= bit; return; }
        if (test) return;
        if (e->key() == Qt::Key_F11 || (e->key() == Qt::Key_F && !(e->modifiers() & ~Qt::KeyboardModifiers(Qt::ControlModifier | Qt::MetaModifier)))) toggle_fullscreen();
        else if (e->key() == Qt::Key_Escape && visibility() == QWindow::FullScreen) showNormal();
    }
    void keyReleaseEvent(QKeyEvent* e) override {
        if (e->isAutoRepeat()) return;
        g_key_events++;
        if (uint32_t bit = key_bit(e->key())) g_keys &= ~bit;
    }
    void focusOutEvent(QFocusEvent*) override { g_keys = 0; }       // nothing stays held when the window is left
    bool event(QEvent* e) override {
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

// The main-thread side: owns the context, the backend and the window; draws and paces.
class Screen : public QObject {
  public:
    Options opt;
    GameWindow* window = nullptr;
    QOffscreenSurface* offscreen = nullptr;
    QOpenGLContext* context = nullptr;
    GlBackend* backend = nullptr;
    bool follow_window = false;                         // the picture is drawn at the window's pixel size
    double view_aspect = 4.0 / 3.0;                     // what the game is asked to make its view for
    // hand-over
    std::mutex lock;
    std::condition_variable done;
    FrameList slot;
    std::vector<std::string> slot_shots;
    bool busy = false;
    double submit_wait_ms = 0;                          // time the decoder waited for this thread
    // pacing
    double refresh_hz = 60, refresh_ms = 1000.0 / 60, period_ms = 1000.0 / 60;
    int refreshes_per_picture = 1;
    bool display_locked = false;
    double last_present = 0;
    // figures
    uint64_t blanks = 0;
    double draw_ms = 0, start_ms = 0, start_cpu = 0;
    size_t vertices = 0, commands = 0;
    struct Pace {
        uint64_t presents = 0, swap_waited = 0, timer_waited = 0, late_starts = 0;
        uint64_t by_refreshes[8] = {0, 0, 0, 0, 0, 0, 0, 0};    // pictures that stood for k refreshes (7 = more)
        double first = 0, last = 0, swap_ms = 0, worst_ms = 0;
    } pace;

    QSurface* surface() { return window ? (QSurface*)window : (QSurface*)offscreen; }

    void create() {
        QSurfaceFormat format = QSurfaceFormat::defaultFormat();
        format.setSwapInterval(opt.unpaced ? 0 : 1);
        if (opt.offscreen) {
            offscreen = new QOffscreenSurface;
            offscreen->setFormat(format);
            offscreen->create();
        } else {
            window = new GameWindow;
            window->setSurfaceType(QSurface::OpenGLSurface);
            window->setFormat(format);
            if (!opt.test.empty()) {
                window->test = true;
                window->setTitle(QString("AGENT TEST - ") + QString::fromStdString(opt.test));
                window->setFlags(window->flags() | Qt::WindowDoesNotAcceptFocus | Qt::WindowStaysOnBottomHint);
            } else window->setTitle(TITLE);
            window->resize(opt.window_w, opt.window_h);
            window->setMinimumSize(QSize(320, 240));
            if (opt.fullscreen && opt.test.empty()) window->showFullScreen(); else window->show();
            if (!opt.test.empty()) window->lower();
        }
        context = new QOpenGLContext;
        context->setFormat(format);
        if (!context->create() || !context->makeCurrent(surface())) { log_line("no OpenGL 4.1 context"); _exit(1); }
        QOpenGLExtraFunctions* gl = context->extraFunctions();
        log_line(std::string("OpenGL ") + (const char*)gl->glGetString(GL_VERSION) + " on " + (const char*)gl->glGetString(GL_RENDERER));
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
        start_ms = now_ms();
        start_cpu = cpu_ms();
    }

    // called on the decoder's thread: take this list to be drawn.  Returns as soon as the
    // list before it has been drawn; the caller gets that one's vectors back to fill again.
    void submit(FrameList& frame, std::vector<std::string>& shots) {
        std::unique_lock<std::mutex> hold(lock);
        double w0 = now_ms();
        done.wait(hold, [this] { return !busy; });
        submit_wait_ms += now_ms() - w0;
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
        slot_shots.swap(shots);
        shots.clear();
        busy = true;
        QCoreApplication::postEvent(this, new QEvent(FrameEvent));
    }

    bool event(QEvent* e) override {
        if (e->type() == CallEvent) { static_cast<CallQEvent*>(e)->fn(); return true; }
        if (e->type() != FrameEvent) return QObject::event(e);
        FrameList* frame = &slot;                       // ours until busy is cleared
        double t0 = now_ms();
        context->makeCurrent(surface());
        QOpenGLExtraFunctions* gl = context->extraFunctions();
        if (window && opt.aspect == 0) {                // the view takes the window's shape
            double shape = (double)window->width() / window->height();
            if (shape < 4.0 / 3.0) shape = 4.0 / 3.0;
            if (std::fabs(shape - view_aspect) > 0.002) { view_aspect = shape; gfxrt::set_aspect(shape); }
        }
        // The picture is sized for the shape THIS list was built for (it says so itself): while
        // a new shape is on its way through the game and the decoder, the lists still in
        // flight are drawn as what they are, with bars for a frame or two, never stretched.
        if (follow_window && window) {                  // the window was resized: draw at its new size
            double ratio = window->devicePixelRatio(), shape = frame->aspect;
            int h = (int)(window->height() * ratio), w = (int)std::lround(h * shape);
            if (w > (int)(window->width() * ratio)) { w = (int)(window->width() * ratio); h = (int)std::lround(w / shape); }
            if (h >= 224 && (h != opt.size_h || w != opt.size_w)) { opt.size_w = w; opt.size_h = h; backend->set_output_size(w, h); }
        } else if (opt.scale) {
            int h = 448 * opt.scale, w = (int)std::lround(640 * opt.scale * frame->aspect / (4.0 / 3.0));
            if (h != opt.size_h || w != opt.size_w) { opt.size_w = w; opt.size_h = h; backend->set_output_size(w, h); }
        }
        backend->execute(*frame);
        vertices += frame->vertices.size();
        commands += frame->commands.size();
        if (!opt.png.empty() && opt.at.count(blanks)) save(opt.png + "-" + std::to_string(blanks) + ".png");
        for (const std::string& path : slot_shots) save(path);
        slot_shots.clear();
        bool shown = window && window->isExposed();
        if (opt.set.frame_cap > 0 && opt.set.frame_cap <= 30 && (blanks & 1)) shown = false;        // every other picture
        double swap_start = 0, after = 0;
        if (shown) {
            // with more than one refresh per picture the swap is asked for inside the last of
            // them, so that it lands on the refresh the picture is due at
            if (display_locked && refreshes_per_picture > 1 && last_present != 0) {
                double ask_at = last_present + period_ms - 0.5 * refresh_ms;
                double now = now_ms();
                if (ask_at > now) std::this_thread::sleep_for(std::chrono::duration<double, std::milli>(ask_at - now));
            }
            double ratio = window->devicePixelRatio();
            gl->glBindFramebuffer(GL_FRAMEBUFFER, context->defaultFramebufferObject());
            backend->present((int)(window->width() * ratio), (int)(window->height() * ratio), frame->aspect);
            swap_start = now_ms();
            context->swapBuffers(window);
            after = now_ms();
            pace.swap_ms += after - swap_start;
            if (after - swap_start > 1.0) pace.swap_waited++;
        } else { gl->glFlush(); after = now_ms(); }
        draw_ms += after - t0;
        if (!opt.unpaced) {
            // One picture per period.  A swap that waited for the display returns at the
            // refresh; one that did not (window hidden, no display lock) is held by the clock.
            double due = last_present + period_ms;
            if (last_present == 0 || after - due > 2 * period_ms) { if (last_present != 0) pace.late_starts++; last_present = after; }
            else if (after < due - 1.5) {
                std::this_thread::sleep_for(std::chrono::duration<double, std::milli>(due - after));
                pace.timer_waited++;
                last_present = due;
            } else last_present = after;
        } else last_present = after;
        // figures: how long the picture before this one stood, in refreshes of the display
        {
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
        latency_sample(frame->number, after);
        blanks++;
        if (opt.stop_after && blanks >= opt.stop_after) {
            gl->glFinish();
            g_pads.quit = true;                         // the game's thread prints the reports and ends the process
            QTimer::singleShot(3000, [] { fflush(stdout); _exit(0); });
        }
        { std::lock_guard<std::mutex> hold(lock); busy = false; }
        done.notify_all();
        return true;
    }

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

    void report_pace(bool reset) {
        Pace p;
        { std::lock_guard<std::mutex> hold(lock); p = pace; if (reset) pace = Pace(); }
        double load[3] = {0, 0, 0};
        getloadavg(load, 3);
        double span = p.last - p.first, n = p.presents > 1 ? (double)(p.presents - 1) : 1;
        printf("rta_app: pacing: %llu pictures in %.0f ms: %.3f a second (display %.2f Hz, %s); a picture stood for",
               (unsigned long long)p.presents, span, span > 0 ? 1000.0 * n / span : 0.0, refresh_hz,
               opt.unpaced ? "not paced" : display_locked ? "locked to the display" : "clock");
        for (int k = 0; k < 8; k++) if (p.by_refreshes[k]) printf(" %d%s refreshes: %llu;", k, k == 7 ? "+" : "", (unsigned long long)p.by_refreshes[k]);
        printf(" longest %.1f ms; the swap waited for the display %llu times (%.2f ms on average), the clock held %llu, %llu restarts after a stall; load average %.0f\n",
               p.worst_ms, (unsigned long long)p.swap_waited, p.presents ? p.swap_ms / p.presents : 0.0, (unsigned long long)p.timer_waited,
               (unsigned long long)p.late_starts, load[0]);
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
    printf("rta_app: per picture %.2f ms of processor time over all threads; main thread %.2f ms in OpenGL and the swap; %.0f vertices, %.0f draw commands\n",
           cpu / n, s.draw_ms / n, s.vertices / n, s.commands / n);
    if (g_sink && g_sink->blanks) {
        double b = (double)g_sink->blanks;
        printf("rta_app: per picture, by stage: game side %.2f ms of wall time (translated game, runtime, sound, the sink's copying); decoder %.2f ms of wall time, "
               "%.2f ms of its own processor time (VIF1, VU1, GS model)\n", g_sink->game_ms / b, g_sink->decode_wall_ms / b, g_sink->decode_cpu_ms / b);
    }
    s.report_pace(false);
    apprt::films_report();
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
    char text[1024];
    int n = snprintf(text, sizeof text, "ms=%.0f cpu_ms=%.0f pictures=%llu memory_mb=%.1f tex_made=%llu tex_held=%llu tex_freed=%llu tex_mb=%.1f tex_missing=%llu "
                     "copies=%llu copies_skipped=%llu vu_bad=%llu gs_unknown=%llu draws=%llu fields=%llu machine_s=%.3f",
                     now_ms() - s.start_ms, cpu_ms() - s.start_cpu, (unsigned long long)s.blanks, memory_mb(), (unsigned long long)g.textures_made,
                     (unsigned long long)g.textures_held, (unsigned long long)g.textures_freed, g.texture_bytes / 1048576.0, (unsigned long long)g.texture_missing,
                     (unsigned long long)g.copies, (unsigned long long)g.copies_skipped, (unsigned long long)g_renderer->vif.vu.bad,
                     (unsigned long long)g.unknown_regs, (unsigned long long)s.backend->draw_calls(), (unsigned long long)apprt::fields(), apprt::machine_seconds());
    n += snprintf(text + n, sizeof text - n, " fogged=%llu targets_held=%llu targets_freed=%llu", (unsigned long long)g.fogged, (unsigned long long)g.targets_held,
                  (unsigned long long)g.targets_freed);
    for (int k = 0; k < render::AP_COUNT && n < (int)sizeof text - 40; k++)
        if (g.approx[k]) n += snprintf(text + n, sizeof text - n, " approx%d=%llu", k, (unsigned long long)g.approx[k]);
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
    } else if (w[0] == "fullscreen") {
        // app fullscreen: what F does (a test window stays as it is: it must not cover the screen)
        QCoreApplication::postEvent(g_screen, new CallQEvent([] {
            if (g_screen->window && !g_screen->window->test) g_screen->window->toggle_fullscreen();
            else log_line("app fullscreen: not in a test window");
        }));
    } else if (w[0] == "art" && w.size() >= 2) {
        // the same frame with and without the pack's pictures (and the mip-mapped parts): app art off|on
        bool on = w[1] != "off";
        QCoreApplication::postEvent(g_screen, new CallQEvent([on] { g_screen->backend->set_replacements(on); }));
    } else if (w[0] == "stats") {
        g_screen->report_pace(w.size() >= 2 && w[1] == "reset");
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
            double limit = std::max(2 * noise, noise + 6);
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
        else if (a == "--test") opt.test = next();
        else if (a == "--png") opt.png = next();
        else if (a == "--at") { std::string s = next(); for (char* p = &s[0]; *p;) { opt.at.insert(strtoull(p, &p, 10)); if (*p) p++; } }
        else if (a == "--stop-after") opt.stop_after = strtoull(next().c_str(), nullptr, 10);
        else if (a == "--control") opt.control = next();
        else if (a == "--help" || a == "-h") {
            printf("picture (each also a line of <data>/settings.txt, see tools/recomp/app/settings.h):\n"
                   "        [--aspect auto|4:3|16:9|16:10|21:9|W:H] [--resolution window|WxH|Nx] [--antialiasing off|2|4|8] [--anisotropy 1..16]\n"
                   "        [--mipmaps yes|no] [--art-pack DIR] [--art-memory MB] [--frame-cap 60|30|0] [--plain] [--settings FILE] [--no-settings]\n");
            printf("rta_app --disc IMAGE [--data DIR] [--window WxH] [--fullscreen] [--scale N | --size WxH] [--volume V | --mute | --no-sound]\n"
                   "        [--emulator-timing] [--script FILE] [--do COMMAND] [--test TEXT] [--offscreen] [--unpaced] [--png PREFIX --at n,..]\n"
                   "        [--stop-after N] [-- runtime arguments]\n"
                   "keys: W A S D left stick; arrows direction pad; I J K L triangle square cross circle; Q E L1 R1; 1 3 L2 R2; X C L3 R3;\n"
                   "      Return Start; Backspace Select; F or F11 full screen; Escape leaves full screen\n"
                   "(the head of tools/recomp/app/app_main.cpp describes every option)\n");
            return 0;
        }
        else { fprintf(stderr, "rta_app: unknown option %s (see --help; the runtime's own arguments go after --)\n", a.c_str()); return 2; }
    }
    for (; k < argc; k++) pass.push_back(argv[k]);
    if (!pass.empty() && (pass[0] == "boot" || pass[0] == "resume")) { mode = pass[0]; pass.erase(pass.begin()); }
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
        if (!there && opt.test.empty() && !opt.offscreen) app::Settings().save(file);
    }
    if (mode == "boot") {
        if (opt.disc.empty() || !file_exists(opt.disc)) {
            fprintf(stderr, "rta_app: give your disc image of Champions: Return to Arms (SLUS-20973 v2.00): --disc \"/path/to/image.iso\" (or set RTA_DISC)\n");
            return 1;
        }
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

    static Screen screen;
    screen.opt = opt;
    screen.create();
    g_screen = &screen;
    hostpad::start(log_line);

    static Renderer renderer;
    g_renderer = &renderer;
    renderer.gs.layout.enabled = opt.layout;
    renderer.gs.name_textures = !opt.set.art_pack.empty();
    gfxrt::install();
    if (getenv("RTA_GS_LOG")) renderer.gs.log_display = true;
    if (const char* keep = getenv("RTA_TEX_KEEP")) renderer.gs.texture_keep_frames = (uint32_t)atoi(keep);    // frames an unused texture is kept; 0 = for ever
    static AppSink sink;
    g_sink = &sink;
    sink.renderer = &renderer;
    sink.resumed = mode == "resume";
    sink.waited_downstream_ms = &screen.submit_wait_ms;
    renderer.on_frame = [](FrameList& frame) {
        static std::vector<std::string> shots;
        sink.take(frame.number, shots);
        g_screen->submit(frame, shots);
    };
    sink.start();

    apprt::set_command_handler(app_command);
    apprt::set_finish_handler(final_report);
    if (!opt.control.empty()) {
        g_control.buttons_of = parse_buttons;
        g_control.app_command = app_command;
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
    std::thread game([] { rta::run((int)run_args.size(), run_args.data(), hooks); });
    game.detach();
    return qapp.exec();
}
