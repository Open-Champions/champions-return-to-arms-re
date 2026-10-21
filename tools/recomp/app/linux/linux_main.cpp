// linux_main.cpp - rta_app for Linux: Champions: Return to Arms as a native Linux program.
//
// The Linux counterpart of app_main.cpp (Qt, macOS) and win_main.cpp (Win32): the same
// translated game, runtime, picture path (pipeline.h), renderer and sound library in one
// process; this file is the window, the OpenGL context and the keyboard and mouse, all
// through SDL2 (X11 or Wayland, whatever SDL finds).  Controllers: linux/pad_linux.cpp (SDL2
// game controllers).  Sound device: sound/audio_out_linux.cpp (SDL2 audio).  OpenGL
// functions: linux/glsdl.h.  Sockets: net/sock.h's BSD body; TLS: net2/tls_openssl.cpp.
//
// The routines are win_main.cpp's (which are app_main.cpp's with other names): the options,
// the hand-over queue, the pacing, the reports, the "app ..." script lines.  What differs is
// the window system's calls, and: no compositor clock is asked (the display link of the
// other two), and the log stays on the terminal unless --log FILE is given.
//
//   rta_app IMAGE.iso
//   rta_app --disc IMAGE [options] [-- <more arguments for the runtime>]
//
//   --disc IMAGE        your disc image of SLUS-20973 v2.00, read in place (or $RTA_DISC)
//   --data DIR          memory cards, pictures (default: rta-data beside the program)
//   --elf FILE          the game's executable (default: SLUS_209.73 beside the program, else
//                       copied out of the disc image into the data directory)
//   --window WxH, --fullscreen, --scale N, --size WxH, and the picture options of
//   win_main.cpp (--aspect, --resolution, --antialiasing, --anisotropy, --mipmaps, --art-pack,
//   --art-memory, --frame-cap, --plain, --settings, --no-settings, --view, --view-set, --world)
//   online (only in a build with the network, RTA_NET): --server, --server-public, --online,
//   --host [CODE], --join CODE, --choose-character, --player N, --name NAME; a room of our own:
//   --play-host, --play-join CODE, --service HOST:PORT (else $RTA_NET2_SERVICE)
//   --volume V, --mute, --no-sound, --emulator-timing, --no-films, --script FILE, --do "COMMAND",
//   --offscreen, --unpaced, --png PREFIX --at n,n,..., --stop-after N, --test NAME, --log FILE,
//   --pacing ahead|queued
//
// Keyboard: as win_main.cpp: W A S D left stick, arrows direction pad, I J K L triangle
// square cross circle, Q E L1 R1, 1 3 L2 R2, X C L3 R3, Enter Start, Backspace Select, F or
// F11 or Alt+Enter full screen, Escape leaves it, F12 a picture into the data directory,
// V the next camera view.
#if defined(__linux__)
#include "app_rt.h"
#include "backend_gl.h"
#include "gfx_rt.h"
#include "pad_host.h"
#include "fpcontrols.h"
#include "soulscombat.h"
#include "fpaim.h"                  // aiming by looking (docs/issues/native-first-person-aim.md)
#include "bossmusic.h"
#include "fpview.h"
#include "fpworld.h"
#include "pipeline.h"
#include "recorder.h"
#include "settings.h"
#include "glsdl.h"
#ifdef RTA_NET
#include "netdrv.h"                                     // tools/recomp/net: the hooks for the notes on this window
#endif

#include <SDL.h>

#include <sys/resource.h>
#include <sys/utsname.h>
#include <unistd.h>

#include <algorithm>
#include <atomic>
#include <cctype>
#include <cmath>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <filesystem>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>

using namespace render;
using app::now_ms;

namespace hostpad { void poll(bool in_front); }        // pad_linux.cpp

static const char* TITLE = "Champions: Return to Arms - native build (experimental)";
static render::Renderer* g_renderer;

struct Options {
    int window_w = 960, window_h = 720, size_w = 0, size_h = 0, scale = 0;
    bool offscreen = false, unpaced = false, fullscreen = false, no_sound = false, emulator_timing = false, no_films = false;
    bool queued = false;
    double volume = 1.0;
    std::string test, png, disc, data, elf, log;
    std::set<uint64_t> at;
    uint64_t stop_after = 0;
    app::Settings set;
    double aspect = 0;
    bool layout = true, art_parts = true, art_wait = false;
    std::string settings_file;
    std::string server, server_public, online, name;
    bool choose_character = false;
    int player = 1;
};

static void log_line(const std::string& line) {
    fprintf(stderr, "rta_app: %s\n", line.c_str());
    fflush(stderr);
}

static double cpu_ms() {
    rusage u;
    if (getrusage(RUSAGE_SELF, &u) != 0) return 0;
    return (u.ru_utime.tv_sec + u.ru_stime.tv_sec) * 1000.0 + (u.ru_utime.tv_usec + u.ru_stime.tv_usec) / 1000.0;
}
static double memory_mb() {                             // resident set, from /proc
    long pages = 0, resident = 0;
    if (FILE* f = fopen("/proc/self/statm", "r")) {
        if (fscanf(f, "%ld %ld", &pages, &resident) != 2) resident = 0;
        fclose(f);
    }
    return (double)resident * (double)sysconf(_SC_PAGESIZE) / 1048576.0;
}
static void sleep_ms(double ms) {
    if (ms <= 0) return;
    timespec t;
    t.tv_sec = (time_t)(ms / 1000.0);
    t.tv_nsec = (long)((ms - t.tv_sec * 1000.0) * 1e6);
    while (nanosleep(&t, &t) != 0 && errno == EINTR) {}
}
static void sleep_until(double when_ms) {
    double now = now_ms();
    if (when_ms > now) sleep_ms(when_ms - now);
}
[[noreturn]] static void end_now(int code) {
    fflush(stdout);
    fflush(stderr);
    _exit(code);
}

// ---- a picture as a PNG file (no compression: stored blocks; win_main.cpp's) -------------------
static bool write_png(const std::string& path, const uint8_t* rgba, int w, int h) {
    static uint32_t table[256];
    if (!table[1]) for (uint32_t n = 0; n < 256; n++) { uint32_t c = n; for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1; table[n] = c; }
    FILE* f = fopen(path.c_str(), "wb");
    if (!f) return false;
    auto chunk = [&](const char* type, const std::vector<uint8_t>& data) {
        uint8_t head[8] = {(uint8_t)(data.size() >> 24), (uint8_t)(data.size() >> 16), (uint8_t)(data.size() >> 8), (uint8_t)data.size(),
                           (uint8_t)type[0], (uint8_t)type[1], (uint8_t)type[2], (uint8_t)type[3]};
        uint32_t crc = 0xFFFFFFFFu;
        for (int k = 4; k < 8; k++) crc = table[(crc ^ head[k]) & 255] ^ (crc >> 8);
        for (uint8_t b : data) crc = table[(crc ^ b) & 255] ^ (crc >> 8);
        crc = ~crc;
        uint8_t tail[4] = {(uint8_t)(crc >> 24), (uint8_t)(crc >> 16), (uint8_t)(crc >> 8), (uint8_t)crc};
        fwrite(head, 1, 8, f);
        if (!data.empty()) fwrite(data.data(), 1, data.size(), f);
        fwrite(tail, 1, 4, f);
    };
    static const uint8_t signature[8] = {0x89, 'P', 'N', 'G', 13, 10, 26, 10};
    fwrite(signature, 1, 8, f);
    std::vector<uint8_t> ihdr = {(uint8_t)(w >> 24), (uint8_t)(w >> 16), (uint8_t)(w >> 8), (uint8_t)w,
                                 (uint8_t)(h >> 24), (uint8_t)(h >> 16), (uint8_t)(h >> 8), (uint8_t)h, 8, 2, 0, 0, 0};
    chunk("IHDR", ihdr);
    std::vector<uint8_t> raw;
    raw.reserve((size_t)h * ((size_t)w * 3 + 1));
    for (int y = 0; y < h; y++) {
        raw.push_back(0);
        const uint8_t* row = rgba + (size_t)y * w * 4;
        for (int x = 0; x < w; x++) { raw.push_back(row[x * 4]); raw.push_back(row[x * 4 + 1]); raw.push_back(row[x * 4 + 2]); }
    }
    std::vector<uint8_t> z = {0x78, 0x01};
    uint32_t a = 1, b = 0;
    for (size_t at = 0; at < raw.size() || at == 0;) {
        size_t n = raw.size() - at > 65535 ? 65535 : raw.size() - at;
        bool last = at + n >= raw.size();
        z.push_back(last ? 1 : 0);
        z.push_back((uint8_t)n); z.push_back((uint8_t)(n >> 8));
        z.push_back((uint8_t)~n); z.push_back((uint8_t)(~n >> 8));
        for (size_t k = 0; k < n; k++) { a = (a + raw[at + k]) % 65521; b = (b + a) % 65521; }
        z.insert(z.end(), raw.begin() + at, raw.begin() + at + n);
        at += n;
        if (last) break;
    }
    z.push_back((uint8_t)(b >> 8)); z.push_back((uint8_t)b); z.push_back((uint8_t)(a >> 8)); z.push_back((uint8_t)a);
    chunk("IDAT", z);
    chunk("IEND", {});
    return fclose(f) == 0;
}

// ---- input --------------------------------------------------------------------------------
enum { KEY_STICK_UP = 1 << 16, KEY_STICK_DOWN = 1 << 17, KEY_STICK_LEFT = 1 << 18, KEY_STICK_RIGHT = 1 << 19 };
static std::atomic<uint32_t> g_keys{0};
static std::atomic<uint64_t> g_key_events{0};

static uint32_t key_bit(SDL_Scancode key) {
    switch (key) {
    case SDL_SCANCODE_W: return KEY_STICK_UP;
    case SDL_SCANCODE_S: return KEY_STICK_DOWN;
    case SDL_SCANCODE_A: return KEY_STICK_LEFT;
    case SDL_SCANCODE_D: return KEY_STICK_RIGHT;
    case SDL_SCANCODE_UP: return rta::PAD_UP;
    case SDL_SCANCODE_DOWN: return rta::PAD_DOWN;
    case SDL_SCANCODE_LEFT: return rta::PAD_LEFT;
    case SDL_SCANCODE_RIGHT: return rta::PAD_RIGHT;
    case SDL_SCANCODE_I: return rta::PAD_TRIANGLE;
    case SDL_SCANCODE_J: return rta::PAD_SQUARE;
    case SDL_SCANCODE_K: return rta::PAD_CROSS;
    case SDL_SCANCODE_L: return rta::PAD_CIRCLE;
    case SDL_SCANCODE_Q: return rta::PAD_L1;
    case SDL_SCANCODE_E: return rta::PAD_R1;
    case SDL_SCANCODE_1: case SDL_SCANCODE_KP_1: return rta::PAD_L2;
    case SDL_SCANCODE_3: case SDL_SCANCODE_KP_3: return rta::PAD_R2;
    case SDL_SCANCODE_X: return rta::PAD_L3;
    case SDL_SCANCODE_C: return rta::PAD_R3;
    case SDL_SCANCODE_RETURN: case SDL_SCANCODE_KP_ENTER: return rta::PAD_START;
    case SDL_SCANCODE_BACKSPACE: return rta::PAD_SELECT;
    case SDL_SCANCODE_SPACE: return rta::PAD_SQUARE;     // second names, for a hand on W A S D and a mouse (fpcontrols.h)
    case SDL_SCANCODE_LSHIFT: case SDL_SCANCODE_RSHIFT: return rta::PAD_R1;
    case SDL_SCANCODE_TAB: return rta::PAD_R3;
    default: return 0;
    }
}
static SDL_Scancode key_by_name(const std::string& name) {
    static const struct { const char* name; SDL_Scancode key; } names[] = {
        {"w", SDL_SCANCODE_W}, {"a", SDL_SCANCODE_A}, {"s", SDL_SCANCODE_S}, {"d", SDL_SCANCODE_D}, {"up", SDL_SCANCODE_UP},
        {"down", SDL_SCANCODE_DOWN}, {"left", SDL_SCANCODE_LEFT}, {"right", SDL_SCANCODE_RIGHT}, {"i", SDL_SCANCODE_I}, {"j", SDL_SCANCODE_J},
        {"k", SDL_SCANCODE_K}, {"l", SDL_SCANCODE_L}, {"q", SDL_SCANCODE_Q}, {"e", SDL_SCANCODE_E}, {"1", SDL_SCANCODE_1},
        {"3", SDL_SCANCODE_3}, {"x", SDL_SCANCODE_X}, {"c", SDL_SCANCODE_C}, {"return", SDL_SCANCODE_RETURN},
        {"backspace", SDL_SCANCODE_BACKSPACE}, {"escape", SDL_SCANCODE_ESCAPE}, {"f", SDL_SCANCODE_F}, {"v", SDL_SCANCODE_V}};
    for (auto& n : names) if (name == n.name) return n.key;
    return SDL_SCANCODE_UNKNOWN;
}

struct Pads : rta::PadSource {
    std::atomic<uint32_t> last_buttons{0};
    std::atomic<uint32_t> last_sticks{0x80808080};
    std::atomic<uint32_t> rumbles{0};
    std::atomic<bool> quit{false};
    void read(unsigned port, uint64_t blank, rta::PadState& state) override {
        if (quit) apprt::finish(0);
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
        {
            static const bool replayed = apprt::replaying();
            const fpview::View& v = fpview::view();
            fpcontrols::set_view(replayed ? 0 : fpview::mode(), v.active && !v.fallback, v.look_pitch);
            fpcontrols::translate(blank, state);
            if (float pitch = fpcontrols::take_pitch(); pitch != 0) fpview::add_pitch(pitch);
            soulscombat::blank(blank);          // the souls-style combat mode (soulscombat.h): off unless asked for
            bossmusic::blank(blank);            // the player's own boss music (bossmusic.h): reads the game's state, plays nothing without files
            fpaim::blank(blank);                // aiming by looking (fpaim.h): off unless asked for; as app_main.cpp
        }
        last_buttons = state.buttons;
        last_sticks = state.lx | state.ly << 8 | state.rx << 16 | (uint32_t)state.ry << 24;
    }
    void rumble(unsigned, uint8_t, uint8_t) override { rumbles++; }
};
static Pads g_pads;

static std::mutex g_shot_lock;
static std::vector<std::string> g_shots_asked;

// Events from other threads to the window's (SDL_PushEvent is safe from any thread).
enum { EV_FRAME, EV_RESIZE, EV_FULLSCREEN, EV_ART, EV_KEY, EV_TITLE };
static Uint32 g_event_base = (Uint32)-1;
static void post(int code, int a = 0, int b = 0, void* data = nullptr) {
    if (g_event_base == (Uint32)-1) return;
    SDL_Event e;
    SDL_zero(e);
    e.type = g_event_base;
    e.user.code = code;
    e.user.data1 = (void*)(intptr_t)a;
    e.user.data2 = data ? data : (void*)(intptr_t)b;
    SDL_PushEvent(&e);
}

static bool g_pointer_held = false, g_pointer_let_go = false;
static void hold_pointer(bool on) {
    if (on == g_pointer_held) return;
    SDL_SetRelativeMouseMode(on ? SDL_TRUE : SDL_FALSE);
    g_pointer_held = on;
}

struct Screen {
    Options opt;
    SDL_Window* window = nullptr;
    SDL_GLContext gl = nullptr;
    GlBackend* backend = nullptr;
    bool follow_window = false;
    double view_aspect = 4.0 / 3.0;
    bool is_fullscreen = false;
    unsigned shot_number = 0;
    enum { DEPTH = 3 };
    struct Item { FrameList frame; std::vector<std::string> shots; app::Timing timing; };
    std::mutex lock;
    std::condition_variable done;
    Item items[DEPTH];
    int head = 0, count = 0, limit = DEPTH;
    double submit_wait_ms = 0;
    app::Pacer* pacer = nullptr;
    double refresh_hz = 60, refresh_ms = 1000.0 / 60, period_ms = 1000.0 / 60;
    int refreshes_per_picture = 1;
    bool display_locked = false;
    double last_present = 0, window_free = 0;
    int swap_evidence = 0;
    bool swap_waits = false;
    double ask_ahead() const {
        if (!display_locked) return 0;
        return refreshes_per_picture > 1 ? 0.5 * refresh_ms : 0;
    }
    uint64_t blanks = 0;
    double draw_ms = 0, start_ms = 0, start_cpu = 0;
    size_t vertices = 0, commands = 0;
    struct Pace {
        uint64_t presents = 0, swap_waited = 0, timer_waited = 0, late_starts = 0, overtaken = 0, late = 0;
        uint64_t by_refreshes[8] = {0, 0, 0, 0, 0, 0, 0, 0};
        double first = 0, last = 0, swap_ms = 0, worst_ms = 0;
        uint64_t timed = 0;
        double game = 0, decode = 0, queue = 0, gl = 0, to_swap = 0, pipe = 0, slack = 0, pipe_most = 0;
    } pace;

    void client_size(int& w, int& h) { SDL_GL_GetDrawableSize(window, &w, &h); }
    bool visible() {
        Uint32 f = SDL_GetWindowFlags(window);
        return (f & SDL_WINDOW_SHOWN) && !(f & SDL_WINDOW_HIDDEN) && !(f & SDL_WINDOW_MINIMIZED);
    }

    void toggle_fullscreen() {
        is_fullscreen = !is_fullscreen;
        SDL_SetWindowFullscreen(window, is_fullscreen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0);
    }

    double display_rate() {
        SDL_DisplayMode mode;
        if (SDL_GetWindowDisplayMode(window, &mode) != 0 || mode.refresh_rate < 20) return 60;
        double hz = mode.refresh_rate;
        if (mode.refresh_rate % 60 == 59) hz = (mode.refresh_rate + 1) * (59.94 / 60.0);     // whole numbers: 59 is 59.94
        return hz;
    }

    bool create(std::string& error) {
        bool test = !opt.test.empty();
        SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_CORE);
        SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
        SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE, 0);          // the backend draws into its own targets
        SDL_GL_SetAttribute(SDL_GL_RED_SIZE, 8);
        SDL_GL_SetAttribute(SDL_GL_GREEN_SIZE, 8);
        SDL_GL_SetAttribute(SDL_GL_BLUE_SIZE, 8);
        Uint32 flags = SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI | SDL_WINDOW_HIDDEN;
        std::string title = test ? "AGENT TEST - " + opt.test : std::string(TITLE);
        static const int versions[][2] = {{4, 1}, {3, 3}};
        for (auto& v : versions) {
            SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, v[0]);
            SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, v[1]);
            window = SDL_CreateWindow(title.c_str(), SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED, opt.window_w, opt.window_h, flags);
            if (!window) { error = std::string("no window: ") + SDL_GetError(); return false; }
            if ((gl = SDL_GL_CreateContext(window))) break;
            error = std::string("no OpenGL ") + std::to_string(v[0]) + "." + std::to_string(v[1]) + " core context: " + SDL_GetError();
            SDL_DestroyWindow(window);
            window = nullptr;
        }
        if (!gl) return false;
        SDL_SetWindowMinimumSize(window, 320, 240);
        std::string missing;
        glsdl::load(missing);
        glsdl::Functions* f = glsdl::functions();
        int major = 0, minor = 0;
        f->glGetIntegerv(GL_MAJOR_VERSION, &major);
        f->glGetIntegerv(GL_MINOR_VERSION, &minor);
        const char* v = (const char*)f->glGetString(GL_VERSION);
        const char* r = (const char*)f->glGetString(GL_RENDERER);
        log_line(std::string("OpenGL ") + (v ? v : "?") + " on " + (r ? r : "?") + " (SDL " + SDL_GetCurrentVideoDriver() + ")");
        if (!missing.empty()) log_line("OpenGL functions this driver does not have: " + missing);
        if (major < 4 || (major == 4 && minor < 1)) log_line("warning: the renderer is written for OpenGL 4.1; this context is older and may fail");
        bool waits = SDL_GL_SetSwapInterval(opt.unpaced ? 0 : 1) == 0;
        if (!waits && !opt.unpaced) log_line("the driver cannot be told to wait for the display; the clock paces");
        if (!opt.offscreen) {
            SDL_ShowWindow(window);
            if (opt.fullscreen && !test) toggle_fullscreen();
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
            if (!opt.set.art_pack.empty() && fig.pack_files == 0) log_line("the art pack folder holds no pictures (or cannot be read): " + opt.set.art_pack);
        }
        int w = opt.size_w, h = opt.size_h;
        int cw = 0, ch = 0;
        client_size(cw, ch);
        double shape = opt.aspect;
        if (shape <= 0) {
            if (!opt.offscreen && cw > 0 && ch > 0) shape = (double)cw / ch;
            else if (w && h) shape = (w * 448 == h * 640) ? 4.0 / 3.0 : (double)w / h;
            else shape = (double)opt.window_w / opt.window_h;
        }
        if (shape < 4.0 / 3.0) shape = 4.0 / 3.0;
        view_aspect = shape;
        if (opt.scale) { h = 448 * opt.scale; w = (int)std::lround(640 * opt.scale * shape / (4.0 / 3.0)); }
        if (!w || !h) {
            follow_window = !opt.offscreen;
            h = ch >= 224 ? ch : opt.window_h;
            w = (int)std::lround(h * shape);
            if (follow_window && cw > 0 && w > cw) { w = cw; h = (int)std::lround(w / shape); }
        }
        opt.size_w = w; opt.size_h = h;
        backend->set_output_size(w, h);
        gfxrt::set_aspect(shape);
        refresh_hz = display_rate();
        if (refresh_hz < 20 || refresh_hz > 1000) refresh_hz = 60;
        refresh_ms = 1000.0 / refresh_hz;
        refreshes_per_picture = (int)std::lround(refresh_hz / 60.0);
        if (refreshes_per_picture < 1) refreshes_per_picture = 1;
        display_locked = !opt.offscreen && !opt.unpaced && waits && std::fabs(refresh_hz / refreshes_per_picture - 60.0) < 0.9;
        period_ms = display_locked ? refresh_ms * refreshes_per_picture : 1000.0 / 59.94;
        char text[256];
        snprintf(text, sizeof text, "picture drawn at %d x %d; display %.2f Hz; %s", w, h, refresh_hz,
                 opt.unpaced ? "not paced" : display_locked ? "one picture per display refresh interval(s) below" : "paced by the clock at 59.94 pictures a second");
        log_line(text);
        if (display_locked) { snprintf(text, sizeof text, "pacing: one picture every %d refresh(es) = %.3f ms", refreshes_per_picture, period_ms); log_line(text); }
        start_ms = now_ms();
        start_cpu = cpu_ms();
        return true;
    }

    void setup_pacer(app::Pacer* p) {
        pacer = p;
        limit = opt.queued ? 1 : DEPTH;
        pacer->mode = opt.unpaced ? app::Pacer::OFF : opt.queued ? app::Pacer::QUEUED : app::Pacer::AHEAD;
        pacer->period_ms = period_ms;
        pacer->most_lead_ms = 2.5 * period_ms;
        pacer->sleep_until = sleep_until;
        pacer->margin_ms = opt.offscreen ? 2.0 : 1.0 + (display_locked && refreshes_per_picture > 1 ? 0.5 * refresh_ms : 4.0);
        if (!opt.unpaced) log_line(opt.queued ? "pacing: the picture path's hand-overs hold the game back (--pacing queued)"
                                              : "pacing: the game is let go by the clock, just ahead of each picture's moment");
    }

    bool pending() { std::lock_guard<std::mutex> hold(lock); return count > 0; }

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
        hold.unlock();
        post(EV_FRAME);
    }

    // the window's thread: win_main.cpp's Screen::draw (app_main.cpp's draw_one) without the compositor clock
    void draw() {
        Item* item;
        double newer_due = -1;
        {
            std::lock_guard<std::mutex> hold(lock);
            if (count == 0) return;
            item = &items[head];
            if (count > 1) newer_due = items[(head + 1) % DEPTH].timing.due;
        }
        FrameList* frame = &item->frame;
        app::Timing& timing = item->timing;
        double t0 = now_ms();
        timing.draw_start = t0;
        if (window_free > timing.decode_end) timing.blocked += std::min(t0, window_free) - timing.decode_end;
        glsdl::Functions* f = glsdl::functions();
        int cw = 0, ch = 0;
        client_size(cw, ch);
        if (!opt.offscreen && opt.aspect == 0 && cw > 0 && ch > 0) {
            double shape = (double)cw / ch;
            if (shape < 4.0 / 3.0) shape = 4.0 / 3.0;
            if (std::fabs(shape - view_aspect) > 0.002) { view_aspect = shape; gfxrt::set_aspect(shape); }
        }
        if (follow_window && cw > 0 && ch > 0) {
            double shape = frame->aspect;
            int h = ch, w = (int)std::lround(h * shape);
            if (w > cw) { w = cw; h = (int)std::lround(w / shape); }
            if (h >= 224 && (h != opt.size_h || w != opt.size_w)) { opt.size_w = w; opt.size_h = h; backend->set_output_size(w, h); }
        } else if (opt.scale) {
            int h = 448 * opt.scale, w = (int)std::lround(640 * opt.scale * frame->aspect / (4.0 / 3.0));
            if (h != opt.size_h || w != opt.size_w) { opt.size_w = w; opt.size_h = h; backend->set_output_size(w, h); }
        }
        soulscombat::overlay(*frame);           // the souls mode's stamina bar and lock-on marker (nothing when it is off)
        backend->execute(*frame);
        vertices += frame->vertices.size();
        commands += frame->commands.size();
        if (!opt.png.empty() && opt.at.count(blanks)) save(opt.png + "-" + std::to_string(blanks) + ".png");
        for (const std::string& path : item->shots) save(path);
        item->shots.clear();
        bool ahead = pacer && pacer->mode == app::Pacer::AHEAD && timing.due > 0;
        double due = ahead ? timing.due : last_present + period_ms;
        bool overtaken = ahead && newer_due > 0 && newer_due <= now_ms() + 0.5 * refresh_ms;
        bool shown = !opt.offscreen && visible() && cw > 0 && ch > 0 && !overtaken;
        if (opt.set.frame_cap > 0 && opt.set.frame_cap <= 30 && (blanks & 1)) shown = false;
        double after = 0;
        bool timed = false;
        auto to_window = [&] {
            f->glBindFramebuffer(GL_FRAMEBUFFER, 0);
            backend->present(cw, ch, frame->aspect);
        };
        if (ahead) {
            if (shown) to_window();
            f->glFinish();
        }
        timing.ready = now_ms();
        if (shown) {
            if (display_locked && last_present != 0 && (ahead ? ask_ahead() > 0 : refreshes_per_picture > 1))
                sleep_until(due - (ahead ? ask_ahead() : 0.5 * refresh_ms));
            if (!ahead) to_window();
            timing.swap_start = now_ms();
            SDL_GL_SwapWindow(window);
            after = now_ms();
            if (!opt.unpaced && due - timing.swap_start >= 3.0) {
                swap_evidence = after - timing.swap_start >= 2.5 ? std::min(swap_evidence + 1, 12) : std::max(swap_evidence - 1, 0);
                if (swap_evidence >= 6) swap_waits = true; else if (swap_evidence == 0) swap_waits = false;
            }
        } else { f->glFlush(); after = now_ms(); timing.swap_start = after; }
        draw_ms += after - t0;
        bool clock_held = false, restarted = false;
        if (overtaken) {}
        else if (!opt.unpaced) {
            timed = shown && display_locked && swap_waits && last_present != 0 && after - due <= 2 * period_ms;
            if (last_present == 0 || after - due > 2 * period_ms) { restarted = last_present != 0; last_present = after; }
            else if (after < due - 1.5 && !timed) {
                sleep_until(due);
                clock_held = true;
                last_present = due;
            } else last_present = after;
        } else last_present = after;
        timing.shown = overtaken ? 0 : timed ? after : last_present;
        if (pacer && ahead) pacer->margin_ms = opt.offscreen ? 2.0 : 1.0 + (display_locked ? std::max(ask_ahead(), refreshes_per_picture > 1 ? 0.0 : 4.0) : 4.0);
        timing.due = overtaken || opt.unpaced ? 0 : due;
        if (pacer && !overtaken) pacer->presented(timing, timed);
        {
            std::lock_guard<std::mutex> hold(lock);
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
                double pipe = timing.ready - timing.released - timing.blocked;
                pace.timed++;
                pace.game += timing.handed - timing.released;
                pace.decode += timing.decode_end - timing.decode_start;
                pace.queue += timing.draw_start - timing.decode_end;
                pace.gl += timing.ready - timing.draw_start;
                pace.to_swap += timing.swap_start - timing.ready;
                pace.pipe += pipe;
                if (pipe > pace.pipe_most) pace.pipe_most = pipe;
                if (timing.due > 0) {
                    pace.slack += timing.due - timing.ready;
                    if (timing.shown > timing.due + 0.5 * refresh_ms) pace.late++;
                }
            }
        }
        blanks++;
        if (opt.stop_after && blanks >= opt.stop_after && !end_at) {
            f->glFinish();
            g_pads.quit = true;                         // the game's thread prints the reports and ends the process
            end_at = now_ms() + 3000;
        }
        window_free = now_ms();
        { std::lock_guard<std::mutex> hold(lock); head = (head + 1) % DEPTH; count--; }
        done.notify_all();
    }
    double end_at = 0;                                  // the window's thread ends the process here if the game's has not

    void save(const std::string& name) {
        std::vector<uint8_t> rgba;
        int w = 0, h = 0;
        if (!backend->read_shown(rgba, w, h)) { log_line("no picture to write to " + name + " (nothing is shown)"); return; }
        if (!write_png(name, rgba.data(), w, h)) { log_line("cannot write " + name); return; }
        log_line("wrote " + name + " (" + std::to_string(w) + " x " + std::to_string(h) + ") at vertical blank " + std::to_string(blanks));
    }

    void report_pace(bool reset) {
        Pace p;
        { std::lock_guard<std::mutex> hold(lock); p = pace; if (reset) pace = Pace(); }
        double span = p.last - p.first, n = p.presents > 1 ? (double)(p.presents - 1) : 1;
        printf("rta_app: pacing: %llu pictures in %.0f ms: %.3f a second (display %.2f Hz, %s); a picture stood for",
               (unsigned long long)p.presents, span, span > 0 ? 1000.0 * n / span : 0.0, refresh_hz,
               opt.unpaced ? "not paced" : display_locked ? "locked to the display" : "clock");
        for (int k = 0; k < 8; k++) if (p.by_refreshes[k]) printf(" %d%s refreshes: %llu;", k, k == 7 ? "+" : "", (unsigned long long)p.by_refreshes[k]);
        printf(" longest %.1f ms; the swap waited for the display %llu times (%.2f ms on average), the clock held %llu, %llu restarts after a stall\n",
               p.worst_ms, (unsigned long long)p.swap_waited, p.presents ? p.swap_ms / p.presents : 0.0, (unsigned long long)p.timer_waited,
               (unsigned long long)p.late_starts);
        if (p.timed) {
            double n2 = (double)p.timed;
            printf("rta_app: path: per picture, ms of wall time on average: game side %.2f; decoder %.2f; to the window's thread %.2f; OpenGL (to glFinish) %.2f; "
                   "drawn, until the swap is asked for %.2f; in the swap %.2f; from letting the game go to the drawn picture %.2f (longest %.1f)\n",
                   p.game / n2, p.decode / n2, p.queue / n2, p.gl / n2, p.to_swap / n2, p.presents ? p.swap_ms / p.presents : 0.0, p.pipe / n2, p.pipe_most);
            if (pacer && pacer->mode == app::Pacer::AHEAD)
                printf("rta_app: path: the game is let go %.2f ms ahead of the picture's moment now; a drawn picture was there %.2f ms before its moment on average; "
                       "%llu of %llu were on screen more than half a refresh late; %llu drawn and not shown (overtaken); the grid was started again %llu times and "
                       "moved %.1f ms toward the display in all; the swaps %s; the game's thread woke %.2f ms after the time it asked for on average\n",
                       pacer->lead_ms.load(), p.slack / n2, (unsigned long long)p.late, (unsigned long long)p.timed, (unsigned long long)p.overtaken,
                       (unsigned long long)pacer->resyncs.load(), pacer->slewed_ms.load(), swap_waits ? "wait for the display" : "do not wait for the display",
                       pacer->wakes.load() ? pacer->woke_late_ms.load() / pacer->wakes.load() : 0.0);
        }
        fflush(stdout);
    }
};

static Screen* g_screen;
static app::Sink* g_sink;
static Recorder g_recorder;

static void final_report() {
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
    apprt::films_report();
    printf("rta_app: %s\n", fpcontrols::figures().c_str());
    if (soulscombat::wanted() || soulscombat::active()) printf("rta_app: %s\n", soulscombat::figures().c_str());
    if (fpaim::wanted() || fpaim::active()) printf("rta_app: %s\n", fpaim::figures().c_str());
    printf("rta_app: %s\n", bossmusic::figures().c_str());
    fflush(stdout);
}

// ---- "app ..." script lines (game's thread; win_main.cpp's) --------------------------------------
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
        SDL_Scancode key = key_by_name(w[2]);
        if (key == SDL_SCANCODE_UNKNOWN || !g_screen->window) { log_line("app key: unknown key or no window: " + text); return; }
        post(EV_KEY, (int)key, w[1] == "down" ? 1 : 0);
    } else if (w[0] == "gcpad" && w.size() >= 2) {
        float v[6] = {0, 0, 0, 0, 0, 0};
        for (size_t k = 3; k < w.size() && k < 9; k++) v[k - 3] = (float)atof(w[k].c_str());
        hostpad::test(w[1], w.size() >= 3 ? parse_buttons(w[2]) : 0, v);
    } else if (w[0] == "music") {
        // app music info | on | off | volume V | dir PATH | rescan | engage on|off|auto  (bossmusic.h)
        printf("[frame %llu] %s\n", (unsigned long long)frame, bossmusic::command(w.size() >= 2 ? text.substr(text.find(w[1])) : std::string()).c_str());
        fflush(stdout);
    } else if (w[0] == "aim") {
        // app aim info | on | off  (fpaim.h)
        printf("[frame %llu] %s\n", (unsigned long long)frame, fpaim::command(w.size() >= 2 ? text.substr(text.find(w[1])) : std::string()).c_str());
    } else if (w[0] == "souls") {
        // app souls info | on | off | lock | set NAME VALUE  (soulscombat.h)
        printf("[frame %llu] %s\n", (unsigned long long)frame, soulscombat::command(w.size() >= 2 ? text.substr(text.find(w[1])) : std::string()).c_str());
        fflush(stdout);
    } else if (w[0] == "fpc" && w.size() >= 2) {
        printf("[frame %llu] fpc: %s\n", (unsigned long long)frame, fpcontrols::command(text.substr(text.find(w[1])), frame).c_str());
        fflush(stdout);
    } else if (w[0] == "pads") {
        uint32_t sticks = g_pads.last_sticks;
        printf("[frame %llu] rta_app: controller %s (generation %u); port 1 holds buttons %04x, sticks %u %u %u %u; keyboard bits %05x\n",
               (unsigned long long)frame, hostpad::name().empty() ? "none" : hostpad::name().c_str(), hostpad::generation(), g_pads.last_buttons.load(),
               sticks & 255, (sticks >> 8) & 255, (sticks >> 16) & 255, sticks >> 24, g_keys.load());
        fflush(stdout);
    } else if (w[0] == "record" && w.size() >= 2) {
        g_recorder.out.close();
        g_recorder.first_frame = ~0ull;
        if (w[1] != "stop") {
            g_recorder.started = false;
            g_recorder.vu_data.clear();
            if (g_recorder.out.open(text.substr(text.find(w[1])).c_str())) g_recorder.first_frame = 0;
            else log_line("cannot write " + w[1]);
        }
    } else if (w[0] == "option" && w.size() >= 3) {
        bool off = w[2] == "off" || w[2] == "no" || w[2] == "0";
        render::Gs& gs = g_renderer->gs;
        if (w[1] == "game_hud") gs.hide_edge = off;
        else if (w[1] == "game_hud_text") gs.hide_text = off;
        else if (w[1] == "music_volume") { if (!bossmusic::game_music_volume(atof(w[2].c_str()))) log_line("app option music_volume: this program has no sound library"); }
        else { log_line("app option: game_hud on|off, game_hud_text on|off, music_volume 0..1"); return; }
        gfxrt::set_hud_marks(gs.hide_edge || gs.hide_text);
        printf("[frame %llu] option: game_hud %s, game_hud_text %s%s\n", (unsigned long long)frame, gs.hide_edge ? "off" : "on", gs.hide_text ? "off" : "on",
               w[1] == "music_volume" ? (", music_volume " + w[2]).c_str() : "");
        fflush(stdout);
    } else if (w[0] == "world" && w.size() >= 2) {
        if (w[1] == "set" && w.size() >= 4) { if (!fpworld::setting(w[2].c_str(), w[3].c_str())) log_line("app world set: not a world setting: " + w[2]); }
        else if (w[1] == "info") {
            const render::Gs::WorldView& wv = g_renderer->gs.world;
            printf("[frame %llu] %s; renderer: %llu strips, %llu triangles, %llu cut at the near plane, %llu behind it, %llu left out; fill drawn %llu times, "
                   "%llu blocks, %llu triangles, %llu times left out\n", (unsigned long long)frame,
                   fpworld::info(), (unsigned long long)wv.runs, (unsigned long long)wv.triangles, (unsigned long long)wv.cut, (unsigned long long)wv.behind,
                   (unsigned long long)wv.odd, (unsigned long long)wv.fill_draws, (unsigned long long)wv.fill_blocks, (unsigned long long)wv.fill_triangles,
                   (unsigned long long)wv.fill_skipped);
            fflush(stdout);
        } else log_line("app world: info, or set KEY VALUE");
    } else if (w[0] == "view" && w.size() >= 2) {
        if (w[1] == "next") fpview::cycle(1);
        else if (w[1] == "set" && w.size() >= 4) { if (!fpview::setting(w[2].c_str(), w[3].c_str())) log_line("app view set: not a view setting: " + w[2]); }
        else if (w[1] == "info") {
            const fpview::View& v = fpview::view();
            printf("[frame %llu] view: selected %s, shown %s, blend %.2f%s%s; tick %u; eye %.1f %.1f %.1f forward %.3f %.3f %.3f fov %.1f near %.1f\n",
                   (unsigned long long)frame, fpview::mode_name(v.mode), fpview::mode_name(v.shown), v.blend, v.fallback ? "; the game's camera: " : "",
                   v.fallback_why, v.tick, v.eye.x, v.eye.y, v.eye.z, v.forward.x, v.forward.y, v.forward.z, v.fov, v.near_plane);
            fflush(stdout);
        } else if (fpview::mode_by_name(w[1].c_str()) >= 0) fpview::set_mode(fpview::mode_by_name(w[1].c_str()));
        else log_line("app view: overhead, action, chase, shoulder, first, next, info, or set KEY VALUE");
    } else if (w[0] == "window" && w.size() >= 3) {
        int ww = atoi(w[1].c_str()), wh = atoi(w[2].c_str());
        if (g_screen->window && ww >= 160 && wh >= 120) post(EV_RESIZE, ww, wh);
    } else if (w[0] == "fullscreen") {
        if (g_screen->window) post(EV_FULLSCREEN);
    } else if (w[0] == "art" && w.size() >= 2) {
        if (g_screen->window) post(EV_ART, w[1] != "off" ? 1 : 0);
    } else if (w[0] == "stats") {
        g_screen->report_pace(w.size() >= 2 && w[1] == "reset");
    } else log_line("unknown app command: " + text);
}

struct AppSink : app::Sink {
    std::mutex notes_lock;
    std::vector<std::pair<uint64_t, std::string>> notes;
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

static bool file_exists(const std::string& path) { return access(path.c_str(), F_OK) == 0; }

static void fail(const std::string& text) {
    fprintf(stderr, "rta_app: %s\n", text.c_str());
    fflush(stderr);
    // started from a file manager there is no terminal to read: a box as well, when a display is there
    if (!isatty(2)) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_INFORMATION, "Champions: Return to Arms - native build", text.c_str(), nullptr);
}

#ifdef RTA_NET
// the driver's notes go into the window's title (the window's thread sets it)
static void online_note(const std::string& text) { post(EV_TITLE, 0, 0, new std::string(text)); }
static void online_warning(const std::string& text) { fprintf(stderr, "rta_app: online: %s\n", text.c_str()); fflush(stderr); }
#endif

static const char* HELP =
    "rta_app IMAGE.iso\n"
    "rta_app --disc IMAGE [--data DIR] [--window WxH] [--fullscreen] [--scale N | --size WxH] [--volume V | --mute | --no-sound]\n"
    "        [--emulator-timing] [--no-films] [--script FILE] [--do COMMAND] [--offscreen] [--unpaced] [--png PREFIX --at n,..]\n"
    "        [--stop-after N] [--log FILE] [-- runtime arguments]\n"
    "picture (each also a line of rta-data/settings.txt, which is written with its defaults at the first start):\n"
    "        [--aspect auto|4:3|16:9|16:10|21:9|W:H] [--resolution window|WxH|Nx] [--antialiasing off|2|4|8] [--anisotropy 1..16]\n"
    "        [--mipmaps yes|no] [--art-pack FOLDER] [--art-memory MB] [--frame-cap 60|30|0] [--plain] [--settings FILE] [--no-settings]\n"
    "        [--pacing ahead|queued] [--view overhead|action|chase|shoulder|first] [--view-set view.<mode>.<name>=VALUE] [--combat souls|off] [--aim look|off]\n"
#ifdef RTA_NET
    "online: [--server ADDRESS] (or the first line of server.txt beside the program) [--online | --host [CODE] | --join CODE]\n"
    "        [--choose-character] [--player N] [--server-public ADDRESS] [--name NAME]\n"
    "a room of our own: [--play-host | --play-join CODE] [--name NAME] [--service HOST:PORT] (else $RTA_NET2_SERVICE)\n"
#else
    "(this build has no network)\n"
#endif
    "keys: W A S D left stick; arrows direction pad; I J K L triangle square cross circle; Q E L1 R1; 1 3 L2 R2; X C L3 R3;\n"
    "      Enter Start; Backspace Select; F, F11 or Alt+Enter full screen; Escape leaves full screen; F12 writes a picture; V the view\n"
    "a game controller SDL2 knows (Xbox, PlayStation, Switch, most others) is port 1 as well\n";

int main(int argc, char** argv) {
    Options opt;
    std::vector<std::pair<std::string, std::string>> overrides;
    bool plain = false, no_settings = false;
    std::vector<std::string> pass, script_args, net2_args;
    std::string mode = "boot";
    if (const char* disc = getenv("RTA_DISC")) opt.disc = disc;
    auto code_like = [](const std::string& text) {
        if (text.size() < 4 || text.size() > 8) return false;
        for (char ch : text) if (!isalnum((unsigned char)ch)) return false;
        return true;
    };
    int k = 1;
    for (; k < argc; k++) {
        std::string a = argv[k];
        auto next = [&]() -> std::string { return k + 1 < argc ? argv[++k] : ""; };
        if (a == "--") { k++; break; }
        else if (a == "--disc") opt.disc = next();
        else if (a == "--data") opt.data = next();
        else if (a == "--elf") opt.elf = next();
        else if (a == "--combat") overrides.push_back({"combat.mode", next()});        // souls | off (soulscombat.h)
        else if (a == "--aim") overrides.push_back({"combat.aim", next()});           // look | off (fpaim.h)
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
        else if (a == "--world") {
            std::string kv = next(); size_t eq = kv.find('=');
            std::string key = eq == std::string::npos ? std::string() : kv.substr(0, eq), value = eq == std::string::npos ? std::string() : kv.substr(eq + 1);
            if (key != "world" && key.compare(0, 6, "world.") != 0) { fprintf(stderr, "rta_app: --world world=views|off|always, world.clip|persp|objects=on|off, world.ceilings|skirts=auto|on|off\n"); return 2; }
            overrides.push_back({key, value});
        }
        else if (a == "--game-hud") overrides.push_back({"game_hud", next()});
        else if (a == "--game-hud-text") overrides.push_back({"game_hud_text", next()});
        else if (a == "--music-volume") overrides.push_back({"music_volume", next()});
        else if (a == "--boss-music") overrides.push_back({"music.boss", next()});                 // on | off (bossmusic.h)
        else if (a == "--boss-music-dir") overrides.push_back({"music.boss_dir", next()});
        else if (a == "--boss-music-volume") overrides.push_back({"music.boss_volume", next()});
        else if (a == "--view-set") { std::string kv = next(); size_t eq = kv.find('='); if (eq != std::string::npos) overrides.push_back({kv.substr(0, eq), kv.substr(eq + 1)}); }
        else if (a == "--pacing") { std::string way = next(); opt.queued = way == "queued"; if (way != "queued" && way != "ahead") { fail("--pacing ahead|queued"); return 2; } }
        else if (a == "--plain") plain = true;
        else if (a == "--settings") opt.settings_file = next();
        else if (a == "--no-settings") no_settings = true;
        else if (a == "--no-layout") opt.layout = false;
        else if (a == "--art-whole") opt.art_parts = false;
        else if (a == "--art-wait") opt.art_wait = true;
#ifdef RTA_NET
        else if (a == "--server") opt.server = next();
        else if (a == "--server-public") opt.server_public = next();
        else if (a == "--online") opt.online = "lobby";
        else if (a == "--host") { opt.online = "host"; if (k + 1 < argc && code_like(argv[k + 1])) opt.online += std::string(":") + argv[++k]; }
        else if (a == "--join") opt.online = "join:" + next();
        else if (a == "--choose-character") opt.choose_character = true;
        else if (a == "--player") { opt.player = atoi(next().c_str()); if (opt.player < 1) opt.player = 1; }
        else if (a == "--name") { opt.name = next(); net2_args.push_back("--opt"); net2_args.push_back("net2-name=" + opt.name); }
        else if (a == "--play-host") { net2_args.push_back("--opt"); net2_args.push_back("net2=host"); }
        else if (a == "--play-join") { net2_args.push_back("--opt"); net2_args.push_back("net2=join:" + next()); }
        else if (a == "--service") { net2_args.push_back("--opt"); net2_args.push_back("net2-service=" + next()); }
#endif
        else if (a == "--volume") opt.volume = atof(next().c_str());
        else if (a == "--mute") opt.volume = 0;
        else if (a == "--no-sound") opt.no_sound = true;
        else if (a == "--emulator-timing") opt.emulator_timing = true;
        else if (a == "--script" || a == "--do") { script_args.push_back(a); script_args.push_back(next()); }
        else if (a == "--offscreen") opt.offscreen = true;
        else if (a == "--unpaced") overrides.push_back({"frame_cap", "0"});
        else if (a == "--test") opt.test = next();
        else if (a == "--png") opt.png = next();
        else if (a == "--at") { std::string s = next(); for (char* p = &s[0]; *p;) { opt.at.insert(strtoull(p, &p, 10)); if (*p) p++; } }
        else if (a == "--stop-after") opt.stop_after = strtoull(next().c_str(), nullptr, 10);
        else if (a == "--log") opt.log = next();
        else if (a == "--no-log") {}                    // (win_main.cpp's; the log is on the terminal here unless --log)
        else if (a == "--no-films") opt.no_films = true;
        else if (a == "--help" || a == "-h") { printf("%s", HELP); return 0; }
        else if (a.compare(0, 2, "--") != 0) opt.disc = a;      // a file given by itself: the disc image
        else { fail("unknown option " + a + " (see --help; the runtime's own arguments go after --)"); return 2; }
    }
    for (; k < argc; k++) pass.push_back(argv[k]);
    if (!pass.empty() && (pass[0] == "boot" || pass[0] == "resume")) { mode = pass[0]; pass.erase(pass.begin()); }
    (void)code_like;
    bool settings_later = opt.settings_file.empty() && !no_settings;
    auto apply_settings = [&](const std::string& file) {
        if (!file.empty() && !opt.set.load(file, log_line) && file == opt.settings_file) log_line("cannot read the settings file " + file);
        if (plain) opt.set.plain();
        for (auto& kv : overrides) opt.set.set(kv.first, kv.second);
        while (opt.set.art_pack.size() > 1 && opt.set.art_pack.back() == '/') opt.set.art_pack.pop_back();
        opt.window_w = opt.set.window_w; opt.window_h = opt.set.window_h;
        opt.fullscreen = opt.set.fullscreen;
        opt.size_w = opt.set.size_w; opt.size_h = opt.set.size_h; opt.scale = opt.set.scale;
        opt.aspect = opt.set.aspect;
        opt.unpaced = opt.set.frame_cap <= 0;
        for (auto& kv : opt.set.view)
            if (!fpview::setting(kv.first.c_str(), kv.second.c_str()) && !fpcontrols::setting(kv.first.c_str(), kv.second.c_str()) && !fpworld::setting(kv.first.c_str(), kv.second.c_str()) &&
                !fpaim::setting(kv.first.c_str(), kv.second.c_str()) && !soulscombat::setting(kv.first.c_str(), kv.second.c_str()) &&
                !bossmusic::setting(kv.first.c_str(), kv.second.c_str()))
                log_line("settings: not a view, controls or world setting: " + kv.first + " = " + kv.second);
        opt.set.view.clear();
    };
    if (!settings_later) apply_settings(opt.settings_file);

    // where things are: beside the program
    std::string bin = ".";
    {
        char path[4096];
        ssize_t n = readlink("/proc/self/exe", path, sizeof path - 1);
        if (n > 0) { bin.assign(path, (size_t)n); bin = bin.substr(0, bin.find_last_of('/')); }
    }
    std::error_code ec;
    if (opt.data.empty()) {
        opt.data = bin + (opt.player > 1 ? "/rta-data-player" + std::to_string(opt.player) : std::string("/rta-data"));
        // a folder that cannot be written (installed for every user): the user's own data folder instead
        std::filesystem::create_directories(opt.data, ec);
        if (ec || access(opt.data.c_str(), W_OK) != 0) {
            const char* xdg = getenv("XDG_DATA_HOME");
            const char* home = getenv("HOME");
            std::string base = xdg && *xdg ? std::string(xdg) : std::string(home ? home : ".") + "/.local/share";
            opt.data = base + "/rta-native" + (opt.player > 1 ? "/player" + std::to_string(opt.player) : std::string());
        }
    }
    std::filesystem::create_directories(opt.data, ec);

    if (!opt.log.empty()) {
        printf("rta_app: the log of this run is written to %s\n", opt.log.c_str());
        fflush(stdout);
        if (freopen(opt.log.c_str(), "w", stdout)) {
            dup2(fileno(stdout), fileno(stderr));
            setvbuf(stdout, nullptr, _IONBF, 0);
            setvbuf(stderr, nullptr, _IONBF, 0);
        }
    }
    {
        utsname u;
        if (uname(&u) == 0) log_line(std::string(u.sysname) + " " + u.release + " " + u.machine + ", " + std::to_string(sysconf(_SC_NPROCESSORS_ONLN)) + " processors");
    }

    if (settings_later) {
        std::string file = opt.data + "/settings.txt";
        bool there = file_exists(file);
        apply_settings(there ? file : std::string());
        if (!there && opt.test.empty() && !opt.offscreen) app::Settings().save(file, (std::string(fpview::settings_text()) + "\n" + fpcontrols::settings_text() + "\n" + fpworld::settings_text() + "\n" + bossmusic::settings_text()).c_str());
    }
#ifdef RTA_NET
    if (opt.server.empty()) {
        if (FILE* f = fopen((bin + "/server.txt").c_str(), "r")) {
            char line[512];
            while (fgets(line, sizeof line, f)) {
                std::string text = line;
                size_t hash = text.find('#');
                if (hash != std::string::npos) text.erase(hash);
                size_t a = text.find_first_not_of(" \t\r\n"), b = text.find_last_not_of(" \t\r\n");
                if (a == std::string::npos) continue;
                text = text.substr(a, b - a + 1);
                size_t eq = text.find('=');
                if (eq != std::string::npos) {
                    std::string key = text.substr(0, eq), value = text.substr(eq + 1);
                    while (!key.empty() && (key.back() == ' ' || key.back() == '\t')) key.pop_back();
                    size_t v = value.find_first_not_of(" \t");
                    value = v == std::string::npos ? "" : value.substr(v);
                    if (key == "public" && opt.server_public.empty()) opt.server_public = value;
                    else if (key == "server" && opt.server.empty()) opt.server = value;
                    else if (key == "service") { net2_args.push_back("--opt"); net2_args.push_back("net2-service=" + value); }
                } else if (opt.server.empty()) opt.server = text;
            }
            fclose(f);
            if (!opt.server.empty()) log_line("the lobby server is taken from server.txt: " + opt.server);
        }
    }
#endif
    if (mode == "boot") {
        if (opt.disc.empty() || !file_exists(opt.disc)) {
            fail(opt.disc.empty() ? "Give your disc image of Champions: Return to Arms (SLUS-20973 v2.00):  ./rta_app \"/path/to/image.iso\"  (or ./play.sh \"/path/to/image.iso\")"
                                  : "The disc image was not found: " + opt.disc);
            return 1;
        }
        if (opt.elf.empty()) {
            opt.elf = bin + "/SLUS_209.73";
            if (!file_exists(opt.elf)) {
                opt.elf = opt.data + "/SLUS_209.73";
                if (!file_exists(opt.elf) && !apprt::extract_from_disc(opt.disc, "\\SLUS_209.73;1", opt.elf)) {
                    fail("SLUS_209.73 is not on this disc image (is it Champions: Return to Arms, SLUS-20973?): " + opt.disc);
                    return 1;
                }
            }
        }
    }

    // SDL: video and events here; the sound device opens its own subsystem from the game's thread
    SDL_SetHint(SDL_HINT_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR, "0");
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS) != 0) {
        fail(std::string("No display to open a window on (") + SDL_GetError() + "). Under X11 or Wayland this starts by itself; without one, run it under Xvfb (xvfb-run).");
        return 1;
    }
    g_event_base = SDL_RegisterEvents(1);

    static Screen screen;
    screen.opt = opt;
    g_screen = &screen;
    std::string error;
    if (!screen.create(error)) {
        fail("The window or its OpenGL 4.1 context could not be made: " + error + ". The graphics driver (Mesa, or the maker's) must offer OpenGL 4.1 or 3.3 core.");
        return 1;
    }
    hostpad::start(log_line);
#ifdef RTA_NET
    if (opt.test.empty() && !opt.offscreen) rtanet::show_note = online_note;
    rtanet::show_warning = online_warning;
#endif

    static Renderer renderer;
    g_renderer = &renderer;
    renderer.gs.layout.enabled = opt.layout;
    renderer.gs.name_textures = !opt.set.art_pack.empty();
    gfxrt::install();
    fpview::install();
    renderer.gs.hide_edge = !opt.set.game_hud;
    renderer.gs.hide_text = !opt.set.game_hud_text;
    gfxrt::set_hud_marks(renderer.gs.hide_edge || renderer.gs.hide_text);
    if (opt.set.music_volume < 1.0) bossmusic::game_music_volume(opt.set.music_volume);
    bossmusic::set_data_folder(opt.data);              // the player's boss music: <data>/music/boss/ unless music.boss_dir says otherwise
    fpview::on_view([](fpview::View& v, Ctx*, void*) {
        if (v.shown != v.mode) return;
        float forward[3] = {v.forward.x, v.forward.y, v.forward.z}, up[3] = {v.up.x, v.up.y, v.up.z};
        fpcontrols::apply_view(v.mode, forward, up);
        v.forward = {forward[0], forward[1], forward[2]};
        v.up = {up[0], up[1], up[2]};
    });
    fpview::on_drawn([](const fpview::View& v, Ctx* c, void*) {
        static const bool replayed = apprt::replaying();
        {
            soulscombat::Camera cam;            // the souls mode's lock-on marker is placed with the camera the frame was drawn with
            cam.valid = true;
            const fpview::Vec3* vs[4] = {&v.eye, &v.forward, &v.up, &v.right};
            float* outs[4] = {cam.eye, cam.forward, cam.up, cam.right};
            for (int k = 0; k < 4; k++) { outs[k][0] = vs[k]->x; outs[k][1] = vs[k]->y; outs[k][2] = vs[k]->z; }
            cam.fov = v.fov;
            soulscombat::set_camera(cam);
        }
        int mode = fpcontrols::take_strafe_send();
        if (mode >= 0 && !replayed) apprt::call_game(c, fpcontrols::STRAFE_SENDER, (uint32_t)mode);
        if (!replayed) fpaim::drawn(c, v.mode, v.active && !v.fallback && v.shown == v.mode, v.look_pitch);   // aiming by looking: this machine's aim, by game message 4
    });
    fpworld::install();
    if (getenv("RTA_GS_LOG")) renderer.gs.log_display = true;
    if (const char* keep = getenv("RTA_TEX_KEEP")) renderer.gs.texture_keep_frames = (uint32_t)atoi(keep);
    static AppSink sink;
    g_sink = &sink;
    sink.renderer = &renderer;
    sink.resumed = mode == "resume";
    sink.waited_downstream_ms = &screen.submit_wait_ms;
    renderer.on_frame = [](FrameList& frame) {
        static std::vector<std::string> shots;
        sink.take(frame.number, shots);
        g_screen->submit(frame, shots, sink.current);
    };
    screen.setup_pacer(&sink.pacer);
    sink.start();

    apprt::set_command_handler(app_command);
    apprt::set_finish_handler(final_report);

    static std::vector<std::string> args = {argv[0], mode};
    if (mode == "boot") { args.push_back("--elf"); args.push_back(opt.elf); }
    if (!opt.disc.empty()) { args.push_back("--disc"); args.push_back(opt.disc); }
    args.push_back("--card"); args.push_back(opt.data + "/card");
    if (opt.emulator_timing) args.push_back("--emulator-timing");
    if (apprt::films_linked() && !opt.no_films) { args.push_back("--opt"); args.push_back("films=original"); }
    if (!opt.no_sound) {
        bool silent = !opt.test.empty() || opt.offscreen;
        char gain[32];
        snprintf(gain, sizeof gain, "sound-gain=%.3f", silent ? 0.0 : opt.volume < 0 ? 0.0 : opt.volume > 1 ? 1.0 : opt.volume);
        args.push_back("--opt"); args.push_back("sound-out=device");
        args.push_back("--opt"); args.push_back(gain);
        bool own_clock = !opt.unpaced && !opt.offscreen;
        for (auto& a : pass) if (a.compare(0, 12, "sound-clock=") == 0) own_clock = false;
        if (own_clock) { args.push_back("--opt"); args.push_back("sound-clock=real"); }
    }
    if (!script_args.empty()) {
        if (file_exists(bin + "/names.tsv")) { args.push_back("--sym"); args.push_back(bin + "/names.tsv"); }
        std::vector<std::string> found;
        for (std::filesystem::directory_iterator it(std::filesystem::path(bin + "/symbols"), ec), end; !ec && it != end; it.increment(ec)) {
            std::string name = it->path().filename().string();
            if (name.size() > 4 && name.compare(name.size() - 4, 4, ".tsv") == 0) found.push_back(bin + "/symbols/" + name);
        }
        std::sort(found.begin(), found.end());
        for (auto& path : found) { args.push_back("--sym"); args.push_back(path); }
    }
#ifdef RTA_NET
    args.push_back("--opt"); args.push_back("net-data=" + opt.data);
    args.push_back("--opt"); args.push_back("net-card=" + opt.data + "/card");
    if (!opt.server.empty()) { args.push_back("--opt"); args.push_back("net-server=" + opt.server); }
    if (!opt.server_public.empty()) { args.push_back("--opt"); args.push_back("net-server-public=" + opt.server_public); }
    if (!opt.online.empty()) {
        args.push_back("--opt");
        args.push_back("online=" + opt.online + ((opt.choose_character && opt.online != "lobby") ? "+choose" : ""));
    }
    if (!opt.name.empty()) { args.push_back("--opt"); args.push_back("online-name=" + opt.name); }
    args.insert(args.end(), net2_args.begin(), net2_args.end());
#endif
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

    // the window's loop: a frame from the decoder, or whatever SDL has for the window
    bool test = !opt.test.empty();
    double next_pointer_check = 0;
    for (;;) {
        SDL_Event e;
        bool got = screen.pending() ? SDL_PollEvent(&e) : SDL_WaitEventTimeout(&e, 50);
        while (got) {
            switch (e.type) {
            case SDL_QUIT:
                g_pads.quit = true;                     // the game's thread ends the run at its next vertical blank
                if (!screen.end_at) screen.end_at = now_ms() + 1500;
                break;
            case SDL_KEYDOWN:
            case SDL_KEYUP: {
                g_key_events++;
                if (e.key.repeat) break;
                SDL_Scancode key = e.key.keysym.scancode;
                bool down = e.type == SDL_KEYDOWN;
                if (down && (e.key.keysym.mod & KMOD_ALT)) {
                    if ((key == SDL_SCANCODE_RETURN) && !test) screen.toggle_fullscreen();
                    break;
                }
                if (uint32_t bit = key_bit(key)) { if (down) g_keys |= bit; else g_keys &= ~bit; break; }
                if (!down || test) break;
                if (key == SDL_SCANCODE_ESCAPE && g_pointer_held) { g_pointer_let_go = true; hold_pointer(false); break; }
                if (key == SDL_SCANCODE_V) {
                    fpview::cycle((e.key.keysym.mod & KMOD_SHIFT) ? -1 : 1);
                    log_line(std::string("view: ") + fpview::mode_name(fpview::mode()));
                } else if (key == SDL_SCANCODE_F11 || key == SDL_SCANCODE_F) screen.toggle_fullscreen();
                else if (key == SDL_SCANCODE_ESCAPE && screen.is_fullscreen) screen.toggle_fullscreen();
                else if (key == SDL_SCANCODE_F12) {
                    std::lock_guard<std::mutex> hold(g_shot_lock);
                    g_shots_asked.push_back(opt.data + "/picture-" + std::to_string(++screen.shot_number) + ".png");
                }
                break;
            }
            case SDL_WINDOWEVENT:
                if (e.window.event == SDL_WINDOWEVENT_FOCUS_LOST) { g_keys = 0; fpcontrols::release_all(); hold_pointer(false); }
                break;
            case SDL_MOUSEBUTTONDOWN:
            case SDL_MOUSEBUTTONUP:
                if (!test) {
                    bool down = e.type == SDL_MOUSEBUTTONDOWN;
                    if (down) g_pointer_let_go = false;
                    int b = e.button.button == SDL_BUTTON_LEFT ? 0 : e.button.button == SDL_BUTTON_RIGHT ? 1 : 2;
                    fpcontrols::mouse_button(b, down);
                }
                break;
            case SDL_MOUSEWHEEL:
                if (!test) fpcontrols::mouse_wheel((float)e.wheel.y);
                break;
            case SDL_MOUSEMOTION:
                if (g_pointer_held) fpcontrols::mouse_motion((float)e.motion.xrel, (float)e.motion.yrel);
                break;
            default:
                if (e.type == g_event_base) {
                    int a = (int)(intptr_t)e.user.data1, b = (int)(intptr_t)e.user.data2;
                    switch (e.user.code) {
                    case EV_FRAME: break;               // only to wake the loop
                    case EV_RESIZE: if (!screen.is_fullscreen) SDL_SetWindowSize(screen.window, a, b); break;
                    case EV_FULLSCREEN: if (!test) screen.toggle_fullscreen(); else log_line("app fullscreen: not in a test window"); break;
                    case EV_ART: if (screen.backend) screen.backend->set_replacements(a != 0); break;
                    case EV_KEY: {
                        uint32_t bit = key_bit((SDL_Scancode)a);
                        g_key_events++;
                        if (bit) { if (b) g_keys |= bit; else g_keys &= ~bit; }
                        else if (b && (SDL_Scancode)a == SDL_SCANCODE_F && !test) screen.toggle_fullscreen();
                        else if (b && (SDL_Scancode)a == SDL_SCANCODE_V) fpview::cycle(1);
                        break;
                    }
                    case EV_TITLE: {
                        std::string* text = (std::string*)e.user.data2;
                        SDL_SetWindowTitle(screen.window, (std::string(TITLE) + (text->empty() ? "" : " - " + *text)).c_str());
                        delete text;
                        break;
                    }
                    }
                }
                break;
            }
            got = SDL_PollEvent(&e);
        }
        if (screen.pending()) screen.draw();
        double now = now_ms();
        if (now >= next_pointer_check) {                // the pointer is the look's while a look view is played
            next_pointer_check = now + 50;
            bool focus = (SDL_GetWindowFlags(screen.window) & SDL_WINDOW_INPUT_FOCUS) != 0;
            if (!test) hold_pointer(focus && !g_pointer_let_go && fpcontrols::wants_pointer());
        }
        hostpad::poll((SDL_GetWindowFlags(screen.window) & SDL_WINDOW_INPUT_FOCUS) != 0);
        if (screen.end_at && now >= screen.end_at) end_now(0);
    }
}
#endif  // __linux__
