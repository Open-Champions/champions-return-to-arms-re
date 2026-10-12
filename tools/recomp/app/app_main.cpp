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
//   --volume V          0..1 (default 1); --mute = --volume 0 (the device still runs);
//                       --no-sound opens no device at all
//   --emulator-timing   the I/O processor answers as slowly as on a console (default: fast loading)
//   --script FILE, --do "COMMAND"   scripted input (the rig's script language) on top of
//                       keyboard and controller; "app ..." lines are for this program:
//                         app shot FILE.png        the picture of this vertical blank, at its drawn size
//                         app key down|up NAME     a key event sent to the window (w a s d up down left right
//                                                  i j k l q e 1 3 x c return backspace)
//                         app gcpad connect|disconnect|set BUTTONS|none [lx ly rx ry [l2 r2]]
//                                                  a controller made by the program, to test the map
//                         app pads                 print the controller and what port 1 holds
//                         app stats [reset]        print the pacing figures so far
//   --test "TEXT"       a test run on a computer somebody is using: the window is titled
//                       "AGENT TEST - TEXT", small, behind the others, takes no keyboard,
//                       and the sound is silent whatever --volume says
//   --offscreen         no window (pictures and timings only)
//   --unpaced           as fast as the machine goes
//   --png PREFIX --at n,n,...   write the shown picture at these vertical blanks
//   --stop-after N      print the figures and end after N vertical blanks
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
#include "pad_host.h"
#include "pipeline.h"

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

static double cpu_ms() {                                // processor time of the whole process
    rusage u;
    getrusage(RUSAGE_SELF, &u);
    return (u.ru_utime.tv_sec + u.ru_stime.tv_sec) * 1000.0 + (u.ru_utime.tv_usec + u.ru_stime.tv_usec) / 1000.0;
}

struct Options {
    int window_w = 960, window_h = 720, size_w = 0, size_h = 0, scale = 0;
    bool offscreen = false, unpaced = false, fullscreen = false, no_sound = false, emulator_timing = false;
    double volume = 1.0;
    std::string test, png, disc, data, elf;
    std::set<uint64_t> at;
    uint64_t stop_after = 0;
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

// Port 1 is the script, the controller and the keyboard together: buttons of all three,
// each stick from the first of them that is not at rest.
struct Pads : rta::PadSource {
    std::atomic<uint32_t> last_buttons{0};
    std::atomic<uint32_t> last_sticks{0x80808080};
    std::atomic<uint32_t> rumbles{0};
    std::atomic<bool> quit{false};
    void read(unsigned port, uint64_t, rta::PadState& state) override {
        if (quit) apprt::finish(0);                     // the window was closed: end from the game's thread
        state = apprt::script_pad(port);
        if (port != 0) return;
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
        int w = opt.size_w, h = opt.size_h;
        if (opt.scale) { w = 640 * opt.scale; h = 448 * opt.scale; }
        if (!w || !h) {
            follow_window = window != nullptr;
            double ratio = window ? window->devicePixelRatio() : 1.0;
            h = (int)((window ? window->height() : opt.window_h) * ratio);
            w = h * 4 / 3;
        }
        opt.size_w = w; opt.size_h = h;
        backend->set_output_size(w, h);
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
        slot.show_target = frame.show_target;
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
        if (follow_window && window) {                  // the window was resized: draw at its new size
            int h = (int)(window->height() * window->devicePixelRatio()), w = h * 4 / 3;
            if (h >= 224 && (h != opt.size_h || w != opt.size_w)) { opt.size_w = w; opt.size_h = h; backend->set_output_size(w, h); }
        }
        backend->execute(*frame);
        vertices += frame->vertices.size();
        commands += frame->commands.size();
        if (!opt.png.empty() && opt.at.count(blanks)) save(opt.png + "-" + std::to_string(blanks) + ".png");
        for (const std::string& path : slot_shots) save(path);
        slot_shots.clear();
        bool shown = window && window->isExposed();
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
            backend->present((int)(window->width() * ratio), (int)(window->height() * ratio), 4.0 / 3.0);
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

    void save(const std::string& name) {
        std::vector<uint8_t> rgba;
        int w = 0, h = 0;
        if (!backend->read_shown(rgba, w, h)) { log_line("no picture to write to " + name + " (nothing is shown)"); return; }
        QImage image(rgba.data(), w, h, w * 4, QImage::Format_RGBA8888);
        image.convertToFormat(QImage::Format_RGB888).save(QString::fromStdString(name));
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
    printf("rta_app: input: %llu key events, controller %s, %u rumble commands\n", (unsigned long long)g_key_events.load(),
           hostpad::name().empty() ? "none" : hostpad::name().c_str(), g_pads.rumbles.load());
    fflush(stdout);
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
    } else if (w[0] == "stats") {
        g_screen->report_pace(w.size() >= 2 && w[1] == "reset");
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
        else if (a == "--window") { std::string s = next(); sscanf(s.c_str(), "%dx%d", &opt.window_w, &opt.window_h); }
        else if (a == "--size") { std::string s = next(); sscanf(s.c_str(), "%dx%d", &opt.size_w, &opt.size_h); }
        else if (a == "--scale") { opt.scale = atoi(next().c_str()); if (opt.scale < 1) opt.scale = 1; if (opt.scale > 8) opt.scale = 8; }
        else if (a == "--fullscreen") opt.fullscreen = true;
        else if (a == "--volume") opt.volume = atof(next().c_str());
        else if (a == "--mute") opt.volume = 0;
        else if (a == "--no-sound") opt.no_sound = true;
        else if (a == "--emulator-timing") opt.emulator_timing = true;
        else if (a == "--script" || a == "--do") { script_args.push_back(a); script_args.push_back(next()); }
        else if (a == "--offscreen") opt.offscreen = true;
        else if (a == "--unpaced") opt.unpaced = true;
        else if (a == "--test") opt.test = next();
        else if (a == "--png") opt.png = next();
        else if (a == "--at") { std::string s = next(); for (char* p = &s[0]; *p;) { opt.at.insert(strtoull(p, &p, 10)); if (*p) p++; } }
        else if (a == "--stop-after") opt.stop_after = strtoull(next().c_str(), nullptr, 10);
        else if (a == "--help" || a == "-h") {
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

    // the runtime's arguments
    static std::vector<std::string> args = {argv[0], mode};
    if (mode == "boot") { args.push_back("--elf"); args.push_back(opt.elf); }
    if (!opt.disc.empty()) { args.push_back("--disc"); args.push_back(opt.disc); }
    args.push_back("--card"); args.push_back(opt.data + "/card");
    if (opt.emulator_timing) args.push_back("--emulator-timing");
    if (!opt.no_sound) {
        bool silent = !opt.test.empty() || opt.offscreen;       // a test makes no sound, whatever was asked
        char gain[32];
        snprintf(gain, sizeof gain, "sound-gain=%.3f", silent ? 0.0 : opt.volume < 0 ? 0.0 : opt.volume > 1 ? 1.0 : opt.volume);
        args.push_back("--opt"); args.push_back("sound-out=device");
        args.push_back("--opt"); args.push_back(gain);
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
    hooks.video = &sink;
    hooks.pad = &g_pads;
    std::thread game([] { rta::run((int)run_args.size(), run_args.data(), hooks); });
    game.detach();
    return qapp.exec();
}
