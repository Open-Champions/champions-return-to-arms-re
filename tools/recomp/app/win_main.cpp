// win_main.cpp - rta_app.exe: Champions: Return to Arms as a native Windows application.
//
// The Windows counterpart of app_main.cpp (which is Qt and stays the macOS program): the
// same translated game, runtime, picture path (pipeline.h), renderer and sound library in
// one process; this file is the window (Win32), the OpenGL context (WGL, win/wgl.h), the
// pacing and the keyboard.  Controllers: pad_win.cpp (XInput).  Sound device:
// sound/audio_out_win.cpp (WASAPI).
//
// Written and compiled on a Mac with a cross-compiler; NOT RUN: nobody has seen this
// window (docs/issues/native-windows.md has what was proven without it and the test plan).
//
//   rta_app.exe IMAGE.iso                (or drag the disc image onto rta_app.exe or play.bat)
//   rta_app.exe --disc IMAGE [options] [-- <more arguments for the runtime>]
//
//   --disc IMAGE        your disc image of SLUS-20973 v2.00, read in place (or %RTA_DISC%)
//   --data DIR          memory cards, log, pictures (default: rta-data beside the program)
//   --elf FILE          the game's executable (default: SLUS_209.73 beside the program, else
//                       copied out of the disc image into the data directory)
//   --window WxH        window size (default 960x720, scaled by the display's scaling)
//   --fullscreen        start full screen (F, F11 or Alt+Enter toggles, Escape leaves)
//   --scale N           draw the picture at N times the console's 640 x 448 (1..8)
//   --size WxH          or at exactly this size (default: the window's own pixels)
//   the picture (docs/issues/native-graphics.md; each is also a line of <data>\settings.txt,
//   see settings.h - the file is read first, then these):
//   --aspect A          the shape of the 3-D view: auto (the window's own, the default), 4:3
//                       (the console's), 16:9, 16:10, 21:9, W:H
//   --resolution R      the size the picture is drawn at: window, WxH, or Nx (as --size / --scale)
//   --antialiasing N    samples per pixel of the 3-D scene: off, 2, 4 (default), 8
//   --anisotropy N      1 (off) to 16 (default);  --mipmaps yes|no  mip maps for the game's textures
//   --art-pack DIR      replacement pictures (PNG, read by render/png_read.h: no Qt here);
//                       --art-memory MB (3072)
//   --frame-cap N       60 (default), 30, or 0 = --unpaced
//   --plain             all of that off: 4:3, no multisampling, no mip maps, no pack
//   --settings FILE, --no-settings;  tests: --no-layout, --art-whole, --art-wait
//   online (docs/issues/native-online.md; only in a build with the network, RTA_NET):
//   --server ADDRESS    the lobby server, an IPv4 address or a host name.  Left out: the first
//                       line of server.txt beside the program; neither: a server on this computer
//   --server-public A   the server's public address, when it hands that out and you are on
//                       its own network (normally found by itself)
//   --online            go online by itself: title, Internet Game, network setting, log-in,
//                       and stop at the lobby's game list.  The first time a player name is
//                       asked for (a small dialogue); the account is the program's business
//   --host [CODE]       as --online, and on: opens a game named with a code for your friends
//                       (made up when none is given; shown in the window's title)
//   --join CODE         as --online, and on: joins the game with that code
//   --choose-character  with --host or --join: stop on the game's character screens
//   --player N          a second player on the same PC: data in rta-data-player<N>
//   --name NAME         the player name for a new account, instead of the dialogue (for a PC
//                       on which the dialogue does not appear)
//   --volume V          0..1 (default 1); --mute = --volume 0; --no-sound opens no device
//   --emulator-timing   the I/O processor answers as slowly as on a console
//   --no-films          a film ends at its first picture (when app/film.cpp is part of the program the films play)
//   --script FILE, --do "COMMAND"   scripted input on top of keyboard and controller; the
//                       "app ..." lines of app_main.cpp: shot, key, gcpad, pads, stats, record,
//                       window W H, fullscreen, art off|on
//   --offscreen         the window is never shown (pictures and timings only)
//   --unpaced           as fast as the machine goes
//   --png PREFIX --at n,n,...   write the shown picture at these vertical blanks
//   --stop-after N      print the figures and end after N vertical blanks
//   --no-log            leave the output on the console (default: when the output is a
//                       console it goes to <data>\rta_app-log.txt, the file to send with a report)
//
// Keyboard: W A S D left stick, arrows direction pad, I J K L triangle square cross circle,
// Q E L1 R1, 1 3 L2 R2, X C L3 R3, Enter Start, Backspace Select, F12 a picture of the
// game into the data directory, F8 (or L3 + R3 held on a controller) a bug report into its reports
// folder, F9 the build line (testerkit.h).
//
//   --pacing ahead|queued   how the game is held to one frame per picture (pipeline.h): let go
//                       by a clock just ahead of each picture's moment (the default, as in the
//                       macOS program since 2026-10-13), or held back through the picture path's
//                       hand-overs as this program did until then - to compare when the picture
//                       stutters
//
// Threads as in app_main.cpp: the game's (rta::run), the decoder (pipeline.h) and this
// one, which owns the window and OpenGL.  One picture per 1/60 s: the game is let go by a
// clock just ahead of the moment each picture is due on screen (pipeline.h, Pacer); those
// moments are a grid that is moved onto the display's refreshes - learnt from the times the
// swaps return at where the swap waits for the display (the usual case under Windows),
// and from the compositor's own figures (DwmGetCompositionTimingInfo) where it does not.
// No thread waits for another across a swap: the decoder hands its lists to a queue of
// three, and a picture that is overtaken is drawn and not shown.
//
// NOT RUN.  The pacing is the macOS program's (app_main.cpp, Screen::draw_one), which was
// run; what stands in for the Mac's display link here was written by reading.
#ifdef _WIN32
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
#include "testerkit.h"                  // the bug report (F8), the crash report, the build line (F9)
#include "testerkit_app.h"
#include "win/wgl.h"
#ifdef RTA_NET
#include "online_win.h"                                 // tools/recomp/net: the name question and the notes on this window
#endif

#include <dwmapi.h>
#include <mmsystem.h>
#include <psapi.h>

#include <algorithm>
#include <atomic>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <io.h>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <vector>

using namespace render;
using app::now_ms;

namespace hostpad { void set_window(void* hwnd); }      // pad_win.cpp

static const char* TITLE = "Champions: Return to Arms - native build (experimental)";
static render::Renderer* g_renderer;

struct Options {
    int window_w = 960, window_h = 720, size_w = 0, size_h = 0, scale = 0;
    bool offscreen = false, unpaced = false, fullscreen = false, no_sound = false, emulator_timing = false, no_log = false, no_films = false;
    bool queued = false;                // --pacing queued: the picture path's hand-overs hold the game back
    double volume = 1.0;
    std::string test, png, disc, data, elf;
    std::set<uint64_t> at;
    uint64_t stop_after = 0;
    // the picture (settings.h): the settings file, then the command line
    app::Settings set;
    double aspect = 0;                  // of the 3-D view; 0 = the window's own shape
    bool layout = true;                 // false: the wide picture without the 2-D layer put back into shape
    bool art_parts = true;              // false: whole replacement pictures on the graphics card
    bool art_wait = false;              // tests: every frame waits for the replacement pictures it asks for
    std::string settings_file;
    // online
    std::string server, server_public, online, name;    // online: "", lobby, host, host:CODE, join:CODE
    bool choose_character = false;
    int player = 1;
};

static void log_line(const std::string& line) {
    fprintf(stderr, "rta_app: %s\n", line.c_str());
    fflush(stderr);
}

static std::wstring wide(const std::string& text) {
    int n = MultiByteToWideChar(CP_ACP, 0, text.c_str(), -1, nullptr, 0);
    std::wstring out(n > 0 ? n : 1, L'\0');
    if (n > 0) MultiByteToWideChar(CP_ACP, 0, text.c_str(), -1, &out[0], n);
    out.resize(wcslen(out.c_str()));
    return out;
}
static std::string narrow(const wchar_t* text) {
    int n = WideCharToMultiByte(CP_ACP, 0, text, -1, nullptr, 0, nullptr, nullptr);
    std::string out(n > 0 ? n : 1, '\0');
    if (n > 0) WideCharToMultiByte(CP_ACP, 0, text, -1, &out[0], n, nullptr, nullptr);
    out.resize(strlen(out.c_str()));
    return out;
}

static double cpu_ms() {                                // processor time of the whole process
    FILETIME made, ended, kernel, user;
    if (!GetProcessTimes(GetCurrentProcess(), &made, &ended, &kernel, &user)) return 0;
    auto ms = [](const FILETIME& t) { return (double)(((uint64_t)t.dwHighDateTime << 32) | t.dwLowDateTime) / 10000.0; };
    return ms(kernel) + ms(user);
}
static double memory_mb() {
    PROCESS_MEMORY_COUNTERS pmc;
    memset(&pmc, 0, sizeof pmc);
    pmc.cb = sizeof pmc;
    if (!GetProcessMemoryInfo(GetCurrentProcess(), &pmc, sizeof pmc)) return 0;
    return (double)pmc.WorkingSetSize / 1048576.0;
}
// (a timer per thread: the game's thread waits for its moment while this one waits for a swap's)
static void sleep_ms(double ms) {
    if (ms <= 0) return;
    static thread_local HANDLE timer = CreateWaitableTimerExW(nullptr, nullptr, 0x00000002 /* CREATE_WAITABLE_TIMER_HIGH_RESOLUTION */, TIMER_ALL_ACCESS);
    if (timer) {
        LARGE_INTEGER due;
        due.QuadPart = -(LONGLONG)(ms * 10000.0);
        if (SetWaitableTimer(timer, &due, 0, nullptr, nullptr, FALSE) && WaitForSingleObject(timer, INFINITE) == WAIT_OBJECT_0) return;
    }
    Sleep((DWORD)(ms + 0.5));
}
static void sleep_until(double when_ms) {
    double now = now_ms();
    if (when_ms > now) sleep_ms(when_ms - now);
}

// ---- the display's own refreshes ------------------------------------------------------------
// What the display link is to the macOS program: where the refreshes lie on this
// program's clock.  The desktop compositor says it (DwmGetCompositionTimingInfo: the
// performance-counter time of a vertical blank and the time between two); asked only
// where the swaps do not wait for the display, and believed only when its refreshes are
// the window's rate apart and the answer is fresh.
struct DisplayClock {
    uint64_t asked = 0, told = 0;
    bool there() {
        BOOL on = FALSE;
        return SUCCEEDED(DwmIsCompositionEnabled(&on)) && on;
    }
    bool nearest(double moment, double refresh_ms, double& refresh) {
        asked++;
        DWM_TIMING_INFO info;
        memset(&info, 0, sizeof info);
        info.cbSize = sizeof info;
        LARGE_INTEGER frequency, counter;
        if (FAILED(DwmGetCompositionTimingInfo(nullptr, &info)) || !info.qpcRefreshPeriod || !QueryPerformanceFrequency(&frequency) ||
            !QueryPerformanceCounter(&counter)) return false;
        double mine = now_ms(), to_ms = 1000.0 / (double)frequency.QuadPart;
        double period = (double)info.qpcRefreshPeriod * to_ms;
        double at = mine - (double)((LONGLONG)counter.QuadPart - (LONGLONG)info.qpcVBlank) * to_ms;     // that blank on this program's clock
        if (std::fabs(period - refresh_ms) > 0.02 * refresh_ms || std::fabs(mine - at) > 100.0) return false;
        refresh = at + std::round((moment - at) / period) * period;
        told++;
        return true;
    }
};
static DisplayClock g_display;
[[noreturn]] static void end_now(int code) {
    fflush(stdout);
    fflush(stderr);
    TerminateProcess(GetCurrentProcess(), (UINT)code);
    ExitProcess((UINT)code);
}

// ---- a picture as a PNG file (no compression: stored blocks) -----------------------------------
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
    std::vector<uint8_t> raw;                           // a filter byte and RGB for every row
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
// The keyboard as a pad: bits of rta::PadButton plus four bits for the stick keys.
enum { KEY_STICK_UP = 1 << 16, KEY_STICK_DOWN = 1 << 17, KEY_STICK_LEFT = 1 << 18, KEY_STICK_RIGHT = 1 << 19 };
static std::atomic<uint32_t> g_keys{0};
static std::atomic<uint64_t> g_key_events{0};

static uint32_t key_bit(WPARAM key) {
    switch (key) {
    case 'W': return KEY_STICK_UP;
    case 'S': return KEY_STICK_DOWN;
    case 'A': return KEY_STICK_LEFT;
    case 'D': return KEY_STICK_RIGHT;
    case VK_UP: return rta::PAD_UP;
    case VK_DOWN: return rta::PAD_DOWN;
    case VK_LEFT: return rta::PAD_LEFT;
    case VK_RIGHT: return rta::PAD_RIGHT;
    case 'I': return rta::PAD_TRIANGLE;
    case 'J': return rta::PAD_SQUARE;
    case 'K': return rta::PAD_CROSS;
    case 'L': return rta::PAD_CIRCLE;
    case 'Q': return rta::PAD_L1;
    case 'E': return rta::PAD_R1;
    case '1': case VK_NUMPAD1: return rta::PAD_L2;
    case '3': case VK_NUMPAD3: return rta::PAD_R2;
    case 'X': return rta::PAD_L3;
    case 'C': return rta::PAD_R3;
    case VK_RETURN: return rta::PAD_START;
    case VK_BACK: return rta::PAD_SELECT;
    // second names for three buttons, where a hand on W A S D and a mouse finds them (fpcontrols.h)
    case VK_SPACE: return rta::PAD_SQUARE;
    case VK_SHIFT: return rta::PAD_R1;
    case VK_TAB: return rta::PAD_R3;
    default: return 0;
    }
}
static WPARAM key_by_name(const std::string& name) {
    static const struct { const char* name; WPARAM key; } names[] = {
        {"w", 'W'}, {"a", 'A'}, {"s", 'S'}, {"d", 'D'}, {"up", VK_UP}, {"down", VK_DOWN}, {"left", VK_LEFT}, {"right", VK_RIGHT},
        {"i", 'I'}, {"j", 'J'}, {"k", 'K'}, {"l", 'L'}, {"q", 'Q'}, {"e", 'E'}, {"1", '1'}, {"3", '3'}, {"x", 'X'}, {"c", 'C'},
        {"return", VK_RETURN}, {"backspace", VK_BACK}, {"escape", VK_ESCAPE}, {"f", 'F'}, {"v", 'V'}};
    for (auto& n : names) if (name == n.name) return n.key;
    return 0;
}

// Port 1 is the script, the controller and the keyboard together: buttons of all, each
// stick from the first of them that is not at rest.
struct Pads : rta::PadSource {
    std::atomic<uint32_t> last_buttons{0};
    std::atomic<uint32_t> last_sticks{0x80808080};
    std::atomic<uint32_t> rumbles{0};
    std::atomic<bool> quit{false};
    void read(unsigned port, uint64_t blank, rta::PadState& state) override {
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
        // the views that look along the ground: mouse and right stick are the look, the character
        // is turned to it; in the overhead views nothing changes (fpcontrols.h; app_main.cpp has
        // the same lines).  Not while another machine's controller rows are replayed.
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
        testerkit::pad(blank, state);           // the input record of a report; L3 + R3 held: the report box; at rest while it is open
        last_buttons = state.buttons;
        last_sticks = state.lx | state.ly << 8 | state.rx << 16 | (uint32_t)state.ry << 24;
    }
    void rumble(unsigned, uint8_t, uint8_t) override { rumbles++; }
};
static Pads g_pads;

// ---- "app shot" requests (game's thread -> sink -> decoder -> this thread) ------------------------
static std::mutex g_shot_lock;
static std::vector<std::string> g_shots_asked;           // picked up by the sink at this blank

// ---- the window and the main-thread side -----------------------------------------------------
enum { TIMER_END = 1, TIMER_MOVE = 2, TIMER_POINTER = 3 };

// The pointer as the look of a view (fpcontrols.h; the Mac's look_mac.mm): hidden, kept inside
// the window, the mouse's own motion read as raw input.  Never in a test window.
static bool g_pointer_held = false, g_pointer_let_go = false, g_raw_mouse = false;
static void hold_pointer(HWND hwnd, bool on) {
    if (on == g_pointer_held) return;
    if (on) {
        if (!g_raw_mouse) {
            RAWINPUTDEVICE device = {0x01, 0x02, 0, hwnd};         // generic desktop, mouse
            g_raw_mouse = RegisterRawInputDevices(&device, 1, sizeof device) != 0;
        }
        RECT r;
        GetClientRect(hwnd, &r);
        MapWindowPoints(hwnd, nullptr, (POINT*)&r, 2);
        SetCursorPos((r.left + r.right) / 2, (r.top + r.bottom) / 2);
        ClipCursor(&r);
        ShowCursor(FALSE);
    } else {
        ClipCursor(nullptr);
        ShowCursor(TRUE);
    }
    g_pointer_held = on;
}
// asked for by a script line on the game's thread, done by the window's thread
enum { MSG_RESIZE = WM_APP + 1, MSG_FULLSCREEN, MSG_ART };

struct Screen {
    Options opt;
    HWND window = nullptr;
    wgl::Context gl;
    GlBackend* backend = nullptr;
    bool follow_window = false;                         // the picture is drawn at the window's pixel size
    double view_aspect = 4.0 / 3.0;                     // what the game is asked to make its view for
    UINT dpi = 96;
    bool is_fullscreen = false;
    WINDOWPLACEMENT placement;
    DWORD normal_style = 0;
    HANDLE frame_event = nullptr;
    unsigned shot_number = 0;
    // hand-over: lists wait here in order.  The decoder waits only when all places are
    // taken (`limit`: 1 in the queued way - it then waits until the picture before is shown).
    enum { DEPTH = 3 };
    struct Item { FrameList frame; std::vector<std::string> shots; app::Timing timing; };
    std::mutex lock;
    std::condition_variable done;
    Item items[DEPTH];
    int head = 0, count = 0, limit = DEPTH;
    double submit_wait_ms = 0;                          // time the decoder waited for this thread
    app::Pacer* pacer = nullptr;
    // pacing (as app_main.cpp's Screen; the words there apply)
    double refresh_hz = 60, refresh_ms = 1000.0 / 60, period_ms = 1000.0 / 60;
    int refreshes_per_picture = 1;
    bool display_locked = false;
    double last_present = 0, window_free = 0;
    // Does the swap wait for the display?  Found out from how long swaps take that were asked
    // for well before the picture's moment: six more of those that took 2.5 ms or more than
    // of the others, and the times the swaps return at are taken as the display's refreshes.
    int swap_evidence = 0;
    bool swap_waits = false;
    bool display_link = false;                          // the compositor tells where the refreshes lie (DisplayClock)
    uint64_t link_timed = 0;
    double ask_ahead() const {                          // how long before its moment a picture's swap is asked for
        if (!display_locked) return 0;
        if (display_link && !swap_waits) return 0.9 * refresh_ms;
        return refreshes_per_picture > 1 ? 0.5 * refresh_ms : 0;
    }
    // figures
    uint64_t blanks = 0;
    double draw_ms = 0, start_ms = 0, start_cpu = 0;
    size_t vertices = 0, commands = 0;
    struct Pace {
        uint64_t presents = 0, swap_waited = 0, timer_waited = 0, late_starts = 0, overtaken = 0, late = 0;
        uint64_t by_refreshes[8] = {0, 0, 0, 0, 0, 0, 0, 0};    // pictures that stood for k refreshes (7 = more)
        double first = 0, last = 0, swap_ms = 0, worst_ms = 0;
        // the path, per picture (milliseconds of wall time): sums over `timed` pictures
        uint64_t timed = 0;
        double game = 0, decode = 0, queue = 0, gl = 0, to_swap = 0, pipe = 0, slack = 0, pipe_most = 0;
    } pace;

    static LRESULT CALLBACK proc(HWND hwnd, UINT message, WPARAM wp, LPARAM lp);

    void client_size(int& w, int& h) {
        RECT r = {0, 0, 0, 0};
        GetClientRect(window, &r);
        w = r.right - r.left;
        h = r.bottom - r.top;
    }

    void toggle_fullscreen() {
        if (!is_fullscreen) {
            placement.length = sizeof placement;
            GetWindowPlacement(window, &placement);
            normal_style = (DWORD)GetWindowLongPtrW(window, GWL_STYLE);
            MONITORINFO mi;
            mi.cbSize = sizeof mi;
            if (!GetMonitorInfoW(MonitorFromWindow(window, MONITOR_DEFAULTTONEAREST), &mi)) return;
            SetWindowLongPtrW(window, GWL_STYLE, (normal_style & ~(DWORD)WS_OVERLAPPEDWINDOW) | WS_POPUP);
            SetWindowPos(window, HWND_TOP, mi.rcMonitor.left, mi.rcMonitor.top, mi.rcMonitor.right - mi.rcMonitor.left,
                         mi.rcMonitor.bottom - mi.rcMonitor.top, SWP_FRAMECHANGED | SWP_NOOWNERZORDER);
            is_fullscreen = true;
        } else {
            SetWindowLongPtrW(window, GWL_STYLE, normal_style);
            SetWindowPlacement(window, &placement);
            SetWindowPos(window, nullptr, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOOWNERZORDER | SWP_FRAMECHANGED);
            is_fullscreen = false;
        }
    }

    double display_rate() {
        MONITORINFOEXW mi;
        mi.cbSize = sizeof mi;
        DEVMODEW mode;
        memset(&mode, 0, sizeof mode);
        mode.dmSize = sizeof mode;
        const wchar_t* device = GetMonitorInfoW(MonitorFromWindow(window, MONITOR_DEFAULTTOPRIMARY), &mi) ? mi.szDevice : nullptr;
        if (!EnumDisplaySettingsW(device, ENUM_CURRENT_SETTINGS, &mode) || mode.dmDisplayFrequency < 20) return 60;
        double hz = (double)mode.dmDisplayFrequency;
        // Windows gives whole numbers: 59 is 59.94, 119 is 119.88, 239 is 239.76
        if (mode.dmDisplayFrequency % 60 == 59) hz = (mode.dmDisplayFrequency + 1) * (59.94 / 60.0);
        return hz;
    }

    bool create(std::string& error) {
        WNDCLASSW wc;
        memset(&wc, 0, sizeof wc);
        wc.style = CS_OWNDC | CS_HREDRAW | CS_VREDRAW;
        wc.lpfnWndProc = proc;
        wc.hInstance = GetModuleHandleW(nullptr);
        wc.hCursor = LoadCursorW(nullptr, (LPCWSTR)IDC_ARROW);
        wc.hIcon = LoadIconW(nullptr, (LPCWSTR)IDI_APPLICATION);
        wc.hbrBackground = (HBRUSH)GetStockObject(BLACK_BRUSH);
        wc.lpszClassName = L"RtaNativeWindow";
        if (!RegisterClassW(&wc)) { error = "RegisterClass failed"; return false; }
        bool test = !opt.test.empty();
        DWORD style = WS_OVERLAPPEDWINDOW, ex = test ? WS_EX_NOACTIVATE : 0;
        if (HMODULE user = GetModuleHandleW(L"user32.dll"))
            if (auto get = (UINT(WINAPI*)())(void*)GetProcAddress(user, "GetDpiForSystem")) dpi = get();
        if (dpi < 96 || dpi > 960) dpi = 96;
        RECT r = {0, 0, MulDiv(opt.window_w, (int)dpi, 96), MulDiv(opt.window_h, (int)dpi, 96)};
        AdjustWindowRectEx(&r, style, FALSE, ex);
        std::string title = test ? "AGENT TEST - " + opt.test : std::string(TITLE);
        window = CreateWindowExW(ex, wc.lpszClassName, wide(title).c_str(), style, CW_USEDEFAULT, CW_USEDEFAULT, r.right - r.left, r.bottom - r.top,
                                 nullptr, nullptr, wc.hInstance, nullptr);
        if (!window) { error = "CreateWindow failed"; return false; }
        if (opt.test.empty()) SetTimer(window, TIMER_POINTER, 50, nullptr);        // the pointer is the look's while a look view is played
        if (!wgl::create(window, gl, error)) return false;
        log_line("OpenGL " + gl.version + " on " + gl.renderer);
        if (!gl.missing.empty()) log_line("OpenGL functions this driver does not have: " + gl.missing);
        if (gl.major < 4 || (gl.major == 4 && gl.minor < 1)) log_line("warning: the renderer is written for OpenGL 4.1; this context is older and may fail");
        bool waits = wgl::swap_interval(opt.unpaced ? 0 : 1);
        if (!waits && !opt.unpaced) log_line("the driver cannot be told to wait for the display (no WGL_EXT_swap_control); the clock paces");
        frame_event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
        if (!opt.offscreen) {
            if (opt.fullscreen && !test) { ShowWindow(window, SW_SHOWNORMAL); toggle_fullscreen(); }
            else ShowWindow(window, test ? SW_SHOWNOACTIVATE : SW_SHOWNORMAL);
            if (test) SetWindowPos(window, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
            UpdateWindow(window);
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
        // The shape of the view: what was asked for, else the window's own (a window that is
        // never shown: the shape of the size asked for; a size of 640 x 448 and its multiples
        // is the console's picture, which is 4:3).
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
        // locked to the display when its rate is a multiple of the console's within 1.5 %
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

    // Once the sink (and with it the pacer) exists, before the game starts.
    void setup_pacer(app::Pacer* p) {
        pacer = p;
        limit = opt.queued ? 1 : DEPTH;
        pacer->mode = opt.unpaced ? app::Pacer::OFF : opt.queued ? app::Pacer::QUEUED : app::Pacer::AHEAD;
        pacer->period_ms = period_ms;
        pacer->most_lead_ms = 2.5 * period_ms;
        pacer->sleep_until = sleep_until;
        // a drawn picture is to be there before the swap is asked for: half a refresh before
        // its moment where the swaps are asked for inside the last refresh, 4 ms otherwise
        // on a display, and a millisecond more; 2 ms where nothing is shown
        pacer->margin_ms = opt.offscreen ? 2.0 : 1.0 + (display_locked && refreshes_per_picture > 1 ? 0.5 * refresh_ms : 4.0);
        if (!opt.offscreen && display_locked && !opt.queued && !getenv("RTA_NO_DISPLAY_LINK")) {
            display_link = g_display.there();
            log_line(display_link ? "pacing: the desktop compositor is asked where the display's refreshes lie, where the swaps do not say"
                                  : "pacing: no desktop compositor to ask for the display's refreshes");
        }
        if (!opt.unpaced) log_line(opt.queued ? "pacing: the picture path's hand-overs hold the game back (--pacing queued)"
                                              : "pacing: the game is let go by the clock, just ahead of each picture's moment");
    }

    bool pending() { std::lock_guard<std::mutex> hold(lock); return count > 0; }

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
        SetEvent(frame_event);
    }

    // main thread: the oldest list waiting is drawn, shown at its moment, counted.
    // (app_main.cpp, Screen::draw_one, is the same routine with Qt's names.)
    void draw() {
        Item* item;
        double newer_due = -1;                          // the moment of the list behind this one, when there is one
        {
            std::lock_guard<std::mutex> hold(lock);
            if (count == 0) return;
            item = &items[head];                        // ours until it is counted off below
            if (count > 1) newer_due = items[(head + 1) % DEPTH].timing.due;
        }
        FrameList* frame = &item->frame;
        app::Timing& timing = item->timing;
        double t0 = now_ms();
        timing.draw_start = t0;
        if (window_free > timing.decode_end) timing.blocked += std::min(t0, window_free) - timing.decode_end;
        wgl::Functions* f = wgl::functions();
        int cw = 0, ch = 0;
        client_size(cw, ch);
        if (!opt.offscreen && opt.aspect == 0 && cw > 0 && ch > 0) {     // the view takes the window's shape
            double shape = (double)cw / ch;
            if (shape < 4.0 / 3.0) shape = 4.0 / 3.0;
            if (std::fabs(shape - view_aspect) > 0.002) { view_aspect = shape; gfxrt::set_aspect(shape); }
        }
        // The picture is sized for the shape THIS list was built for (it says so itself): while
        // a new shape is on its way through the game and the decoder, the lists still in
        // flight are drawn as what they are, with bars for a frame or two, never stretched.
        if (follow_window && cw > 0 && ch > 0) {        // the window was resized: draw at its new size
            double shape = frame->aspect;
            int h = ch, w = (int)std::lround(h * shape);
            if (w > cw) { w = cw; h = (int)std::lround(w / shape); }
            if (h >= 224 && (h != opt.size_h || w != opt.size_w)) { opt.size_w = w; opt.size_h = h; backend->set_output_size(w, h); }
        } else if (opt.scale) {
            int h = 448 * opt.scale, w = (int)std::lround(640 * opt.scale * frame->aspect / (4.0 / 3.0));
            if (h != opt.size_h || w != opt.size_w) { opt.size_w = w; opt.size_h = h; backend->set_output_size(w, h); }
        }
        soulscombat::overlay(*frame);           // the souls mode's stamina bar and lock-on marker (nothing when it is off)
        testerkit::overlay(*frame);             // the build line, the report box, its notes (testerkit.h; nothing in a test)
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
        // Overtaken: the list behind this one is due as well (this thread was held up, by a
        // swap that waited long, by Windows' own loop while the window is dragged, or by
        // anything else).  This one was drawn - the surfaces and textures the next list
        // builds on are as they have to be - and is not shown.
        bool overtaken = ahead && newer_due > 0 && newer_due <= now_ms() + 0.5 * refresh_ms;
        bool shown = !opt.offscreen && IsWindowVisible(window) && !IsIconic(window) && cw > 0 && ch > 0 && !overtaken;
        if (opt.set.frame_cap > 0 && opt.set.frame_cap <= 30 && (blanks & 1)) shown = false;        // every other picture
        double after = 0;
        bool timed = false;                             // the swap returned at a refresh of the display
        auto to_window = [&] {
            f->glBindFramebuffer(GL_FRAMEBUFFER, 0);
            backend->present(cw, ch, frame->aspect);
        };
        // Let go ahead of its moment, a picture is "drawn" when the graphics card has
        // finished it, the window's copy included: what is left for the swap is to hand it
        // over, and how long the path takes is known (the lead is made of it).  The queued
        // way draws the window's copy after its wait, as it always did.
        if (ahead) {
            if (shown) to_window();
            f->glFinish();
        }
        timing.ready = now_ms();
        if (shown) {
            // with more than one refresh per picture the swap is asked for inside the last of
            // them, so that it lands on the refresh the picture is due at
            if (display_locked && last_present != 0 && (ahead ? ask_ahead() > 0 : refreshes_per_picture > 1))
                sleep_until(due - (ahead ? ask_ahead() : 0.5 * refresh_ms));
            if (!ahead) to_window();
            timing.swap_start = now_ms();
            SwapBuffers(gl.dc);
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
            // One picture per period.  A swap that waited for the display returns at the
            // refresh; one that did not (window hidden, no display lock) is held by the clock.
            // (`timed`: this swap's return is a refresh of the display, early or late; the grid learns from it)
            timed = shown && display_locked && swap_waits && last_present != 0 && after - due <= 2 * period_ms;
            if (last_present == 0 || after - due > 2 * period_ms) { restarted = last_present != 0; last_present = after; }
            else if (after < due - 1.5 && !timed) {
                sleep_until(due);
                clock_held = true;
                last_present = due;
            } else last_present = after;
        } else last_present = after;
        timing.shown = overtaken ? 0 : timed ? after : last_present;
        // Where the swaps do not wait, the compositor says where the refresh nearest to this
        // picture's moment lay: the grid learns from that (a picture that came late learns nothing).
        double refresh = 0;
        if (ahead && shown && !timed && display_link && !swap_waits && !restarted && after <= due + 1.5 && g_display.nearest(due, refresh_ms, refresh)) {
            timed = true;
            timing.shown = refresh;
            link_timed++;
        }
        if (pacer && ahead) pacer->margin_ms = opt.offscreen ? 2.0 : 1.0 + (display_locked ? std::max(ask_ahead(), refreshes_per_picture > 1 ? 0.0 : 4.0) : 4.0);
        timing.due = overtaken || opt.unpaced ? 0 : due;
        if (pacer && !overtaken) pacer->presented(timing, timed);
        // figures: how long the picture before this one stood, in refreshes of the display,
        // and what each part of this one's way took
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
                    if (timing.shown > timing.due + 0.5 * refresh_ms) pace.late++;       // on screen more than half a refresh after its moment
                }
            }
        }
        blanks++;
        if (opt.stop_after && blanks >= opt.stop_after) {
            f->glFinish();
            g_pads.quit = true;                         // the game's thread prints the reports and ends the process
            SetTimer(window, TIMER_END, 3000, nullptr);
        }
        window_free = now_ms();
        { std::lock_guard<std::mutex> hold(lock); head = (head + 1) % DEPTH; count--; }
        done.notify_all();
    }

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
                       "moved %.1f ms toward the display in all; the swaps %s; %llu pictures' moments were set against the compositor's refreshes (asked %llu times, "
                       "answered %llu); the game's thread woke %.2f ms after the time it asked for on average\n",
                       pacer->lead_ms.load(), p.slack / n2, (unsigned long long)p.late, (unsigned long long)p.timed, (unsigned long long)p.overtaken,
                       (unsigned long long)pacer->resyncs.load(), pacer->slewed_ms.load(), swap_waits ? "wait for the display" : "do not wait for the display",
                       (unsigned long long)link_timed, (unsigned long long)g_display.asked, (unsigned long long)g_display.told,
                       pacer->wakes.load() ? pacer->woke_late_ms.load() / pacer->wakes.load() : 0.0);
        }
        fflush(stdout);
    }
};

static Screen* g_screen;
static app::Sink* g_sink;
static Recorder g_recorder;                             // between the runtime and the sink; writes only while a file is open

LRESULT CALLBACK Screen::proc(HWND hwnd, UINT message, WPARAM wp, LPARAM lp) {
    Screen* s = g_screen;
    bool test = s && !s->opt.test.empty();
    switch (message) {
    case WM_KEYDOWN:
    case WM_SYSKEYDOWN:
        // the report box (testerkit.h) has the keyboard while it is open; its letters come as WM_CHAR
        if (s && !test && testerkit::box_open()) {
            if (wp == VK_RETURN) testerkit::box_key(testerkit::KEY_ENTER);
            else if (wp == VK_ESCAPE) testerkit::box_key(testerkit::KEY_ESCAPE);
            else if (wp == VK_BACK) testerkit::box_key(testerkit::KEY_BACKSPACE);
            return 0;
        }
        if (lp & (1 << 30)) return 0;                   // the key repeating
        g_key_events++;
        if (s && !test && message == WM_KEYDOWN && wp == VK_F8) { g_keys = 0; fpcontrols::release_all(); testerkit::open_box(); return 0; }   // report a bug
        if (s && !test && message == WM_KEYDOWN && wp == VK_F9) { testerkit::toggle_line(); return 0; }                                // the build line
        if (message == WM_SYSKEYDOWN) {                 // Alt held: only Alt+Enter means something here
            if (wp == VK_RETURN && s && !test) s->toggle_fullscreen();
            else if (wp == VK_F4) break;                // Alt+F4 closes, as everywhere
            return 0;
        }
        if (uint32_t bit = key_bit(wp)) { g_keys |= bit; return 0; }
        if (!s || test) return 0;
        if (wp == VK_ESCAPE && g_pointer_held) { g_pointer_let_go = true; hold_pointer(hwnd, false); return 0; }
        if (wp == 'V') {                                // the next camera view (Shift: the one before)
            fpview::cycle(GetKeyState(VK_SHIFT) < 0 ? -1 : 1);
            log_line(std::string("view: ") + fpview::mode_name(fpview::mode()));
            return 0;
        }
        if (wp == VK_F11 || wp == 'F') s->toggle_fullscreen();
        else if (wp == VK_ESCAPE && s->is_fullscreen) s->toggle_fullscreen();
        else if (wp == VK_F12) {
            std::lock_guard<std::mutex> hold(g_shot_lock);
            g_shots_asked.push_back(s->opt.data + "\\picture-" + std::to_string(++s->shot_number) + ".png");
        }
        return 0;
    case WM_KEYUP:
    case WM_SYSKEYUP:
        g_key_events++;
        if (uint32_t bit = key_bit(wp)) g_keys &= ~bit;
        return 0;
    case WM_KILLFOCUS:
        g_keys = 0;                                     // nothing stays held when the window is left
        fpcontrols::release_all();
        hold_pointer(hwnd, false);
        return 0;
    // the mouse (fpcontrols.h): its buttons are pad buttons in the look views, its motion the look
    case WM_LBUTTONDOWN: case WM_RBUTTONDOWN: case WM_MBUTTONDOWN:
        if (!test) { g_pointer_let_go = false; fpcontrols::mouse_button(message == WM_LBUTTONDOWN ? 0 : message == WM_RBUTTONDOWN ? 1 : 2, true); }
        return 0;
    case WM_LBUTTONUP: case WM_RBUTTONUP: case WM_MBUTTONUP:
        if (!test) fpcontrols::mouse_button(message == WM_LBUTTONUP ? 0 : message == WM_RBUTTONUP ? 1 : 2, false);
        return 0;
    case WM_MOUSEWHEEL:
        if (!test) fpcontrols::mouse_wheel((float)GET_WHEEL_DELTA_WPARAM(wp) / (float)WHEEL_DELTA);
        return 0;
    case WM_CHAR:
        if (s && !test && testerkit::box_open() && wp >= 32 && (wp < 0xD800 || wp > 0xDFFF)) {
            char text[4];
            int n = WideCharToMultiByte(CP_UTF8, 0, (const wchar_t*)&wp, 1, text, sizeof text, nullptr, nullptr);
            if (n > 0) testerkit::box_text(std::string(text, (size_t)n));
            return 0;
        }
        break;
    case WM_INPUT:
        if (g_pointer_held) {
            RAWINPUT raw;
            UINT size = sizeof raw;
            if (GetRawInputData((HRAWINPUT)lp, RID_INPUT, &raw, &size, sizeof(RAWINPUTHEADER)) != (UINT)-1 && raw.header.dwType == RIM_TYPEMOUSE
                && !(raw.data.mouse.usFlags & MOUSE_MOVE_ABSOLUTE))
                fpcontrols::mouse_motion((float)raw.data.mouse.lLastX, (float)raw.data.mouse.lLastY);     // right and down positive
        }
        break;
    case WM_SYSCOMMAND:
        if ((wp & 0xFFF0) == SC_KEYMENU) return 0;      // Alt or F10 alone would stop the loop in a menu that is not there
        break;
    case WM_ERASEBKGND:
        return 1;
    case WM_ENTERSIZEMOVE:                              // Windows runs its own loop while the window is dragged: keep drawing from a timer
        SetTimer(hwnd, TIMER_MOVE, 2, nullptr);
        return 0;
    case WM_EXITSIZEMOVE:
        KillTimer(hwnd, TIMER_MOVE);
        return 0;
    case WM_TIMER:
        if (wp == TIMER_POINTER) { hold_pointer(hwnd, !test && GetForegroundWindow() == hwnd && !g_pointer_let_go && fpcontrols::wants_pointer()); return 0; }
        if (wp == TIMER_END) end_now(0);
        if (wp == TIMER_MOVE && s) { WaitForSingleObject(s->frame_event, 0); while (s->pending()) s->draw(); }
        return 0;
    case WM_CLOSE:
        // the game's thread ends the run at its next vertical blank (reports, sound device);
        // if it does not come to one, end here
        g_pads.quit = true;
        SetTimer(hwnd, TIMER_END, 1500, nullptr);
        return 0;
    case WM_GETMINMAXINFO:
        if (lp) { ((MINMAXINFO*)lp)->ptMinTrackSize.x = 320; ((MINMAXINFO*)lp)->ptMinTrackSize.y = 240; }
        return 0;
    case MSG_RESIZE:                                    // app window W H: the client area, in points
        if (s && !s->is_fullscreen) {
            RECT r = {0, 0, MulDiv((int)wp, (int)s->dpi, 96), MulDiv((int)lp, (int)s->dpi, 96)};
            AdjustWindowRectEx(&r, (DWORD)GetWindowLongPtrW(hwnd, GWL_STYLE), FALSE, (DWORD)GetWindowLongPtrW(hwnd, GWL_EXSTYLE));
            SetWindowPos(hwnd, nullptr, 0, 0, r.right - r.left, r.bottom - r.top, SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE);
        }
        return 0;
    case MSG_FULLSCREEN:
        if (s && !test) s->toggle_fullscreen(); else log_line("app fullscreen: not in a test window");
        return 0;
    case MSG_ART:
        if (s && s->backend) s->backend->set_replacements(wp != 0);
        return 0;
    default:
#ifdef RTA_NET
        if (message >= WM_APP && onlinewin::window_message(hwnd, message, wp, lp)) return 0;
#endif
        break;
    }
    return DefWindowProcW(hwnd, message, wp, lp);
}

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

// ---- "app ..." script lines (game's thread) -------------------------------------------------
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
    if (testerkit::command(text)) return;           // app report ... (testerkit.h)
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
        WPARAM key = key_by_name(w[2]);
        bool down = w[1] == "down";
        if (!key || !g_screen->window) { log_line("app key: unknown key or no window: " + text); return; }
        PostMessageW(g_screen->window, down ? WM_KEYDOWN : WM_KEYUP, key, down ? 0 : (LPARAM)0xC0000001);
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
        g_recorder.first_frame = ~0ull;                 // not active: everything passes straight through
        if (w[1] != "stop") {
            g_recorder.started = false;
            g_recorder.vu_data.clear();
            if (g_recorder.out.open(text.substr(text.find(w[1])).c_str())) g_recorder.first_frame = 0;
            else log_line("cannot write " + w[1]);
        }
    } else if (w[0] == "option" && w.size() >= 3) {
        // app option game_hud on|off | game_hud_text on|off | music_volume 0..1 (the Mac program's; settings.h)
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
        // app world info | app world set KEY VALUE (fpworld.h: the world for a camera inside it)
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
        // app view NAME|next | set KEY VALUE | info   (fpview.h; as in app_main.cpp)
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
        // app window W H: the window takes this size (points), as a person dragging its corner would make it
        int ww = atoi(w[1].c_str()), wh = atoi(w[2].c_str());
        if (g_screen->window && ww >= 160 && wh >= 120) PostMessageW(g_screen->window, MSG_RESIZE, (WPARAM)ww, (LPARAM)wh);
    } else if (w[0] == "fullscreen") {
        // app fullscreen: what F does (a test window stays as it is: it must not cover the screen)
        if (g_screen->window) PostMessageW(g_screen->window, MSG_FULLSCREEN, 0, 0);
    } else if (w[0] == "art" && w.size() >= 2) {
        // the same frame with and without the pack's pictures (and the mip-mapped parts): app art off|on
        if (g_screen->window) PostMessageW(g_screen->window, MSG_ART, w[1] != "off" ? 1 : 0, 0);
    } else if (w[0] == "stats") {
        g_screen->report_pace(w.size() >= 2 && w[1] == "reset");
    } else log_line("unknown app command: " + text);
}

// The sink with the pictures a script asked for travelling along with their frame.
struct AppSink : app::Sink {
    std::mutex notes_lock;
    std::vector<std::pair<uint64_t, std::string>> notes;     // (blank number, path), game thread -> decoder
    void vblank(unsigned field, uint64_t number) override {
        testerkit::blank(number, rta::memory());        // the tick log of a report (testerkit.h)
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

// The picture's and the game's threads are the player's own work (what the macOS program
// asks for with its user-interactive class and its latency-critical activity): a step ahead
// of ordinary programs, and not slowed down or given coarse timers when the window is not
// in front - Windows 11 does both to a process whose windows are covered unless it says
// otherwise.  Not for test runs and runs without a window.
static void keep_pace() {
    SetPriorityClass(GetCurrentProcess(), ABOVE_NORMAL_PRIORITY_CLASS);
    struct Throttling { ULONG version, control, state; };
    HMODULE kernel = GetModuleHandleW(L"kernel32.dll");
    auto set = kernel ? (BOOL(WINAPI*)(HANDLE, int, LPVOID, DWORD))(void*)GetProcAddress(kernel, "SetProcessInformation") : nullptr;
    if (!set) return;
    // ProcessPowerThrottling (4): "execution speed" (1) and "ignore timer resolution" (4, Windows 11) both switched off
    Throttling both = {1, 0x1 | 0x4, 0}, speed = {1, 0x1, 0};
    if (!set(GetCurrentProcess(), 4, &both, sizeof both)) set(GetCurrentProcess(), 4, &speed, sizeof speed);
}

static bool file_exists(const std::string& path) {
    DWORD a = GetFileAttributesW(wide(path).c_str());
    return a != INVALID_FILE_ATTRIBUTES;
}

// Something the person has to read: on the console or in the log, and in a box when the
// program was started by a double click or a drop (nobody watches a console that closes).
static void fail(const std::string& text, bool box) {
    fprintf(stderr, "rta_app: %s\n", text.c_str());
    fflush(stderr);
    if (box) MessageBoxW(nullptr, wide(text).c_str(), L"Champions: Return to Arms - native build", MB_OK | MB_ICONINFORMATION);
}

static const char* HELP =
    "rta_app.exe IMAGE.iso      (or drag your disc image onto rta_app.exe or play.bat)\n"
    "rta_app.exe --disc IMAGE [--data DIR] [--window WxH] [--fullscreen] [--scale N | --size WxH] [--volume V | --mute | --no-sound]\n"
    "        [--emulator-timing] [--no-films] [--script FILE] [--do COMMAND] [--offscreen] [--unpaced] [--png PREFIX --at n,..]\n"
    "        [--stop-after N] [--no-log] [-- runtime arguments]\n"
    "picture (each also a line of rta-data\\settings.txt, which is written with its defaults at the first start):\n"
    "        [--aspect auto|4:3|16:9|16:10|21:9|W:H] [--resolution window|WxH|Nx] [--antialiasing off|2|4|8] [--anisotropy 1..16]\n"
    "        [--mipmaps yes|no] [--art-pack FOLDER] [--art-memory MB] [--frame-cap 60|30|0] [--plain] [--settings FILE] [--no-settings]\n"
    "        [--pacing ahead|queued]   (queued: the pacing of the first builds - try it when the picture stutters, and say so)\n"
    "        [--view overhead|action|chase|shoulder|first] [--view-set view.<mode>.<name>=VALUE] [--combat souls|off] [--aim look|off]   (V switches while the game runs)\n"
#ifdef RTA_NET
    "online: [--server ADDRESS] (or the first line of server.txt beside the program) [--online | --host [CODE] | --join CODE]\n"
    "        [--choose-character] [--player N] [--server-public ADDRESS] [--name NAME]\n"
    "a room of our own: [--play-host | --play-join CODE] [--name NAME] [--service HOST:PORT] (else service= in server.txt, or %RTA_NET2_SERVICE%)\n"
#else
    "(this build has no network)\n"
#endif
    "keys: W A S D left stick; arrows direction pad; I J K L triangle square cross circle; Q E L1 R1; 1 3 L2 R2; X C L3 R3;\n"
    "      Enter Start; Backspace Select; F, F11 or Alt+Enter full screen; Escape leaves full screen; F12 writes a picture\n"
    "      F8 (or L3 + R3 held) reports a bug: a zip in <data>\\reports; F9 the build line\n"
    "a controller that speaks XInput (Xbox; PlayStation through Steam or DS4Windows) is port 1 as well\n";

int main(int argc, char** argv) {
    Options opt;
    std::vector<std::pair<std::string, std::string>> overrides;     // picture settings given on the command line
    bool plain = false, no_settings = false;
    std::vector<std::string> pass, script_args, net2_args;
    std::string mode = "boot";
    if (const char* disc = getenv("RTA_DISC")) opt.disc = disc;
    // a game code: 4 to 8 letters and digits (what --host may be followed by)
    auto code_like = [](const std::string& text) {
        if (text.size() < 4 || text.size() > 8) return false;
        for (char ch : text) if (!isalnum((unsigned char)ch)) return false;
        return true;
    };
    // started by a double click or a drop: the console is ours alone and closes with us
    DWORD console_processes[2];
    bool own_console = GetConsoleProcessList(console_processes, 2) <= 1;
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
        else if (a == "--pacing") { std::string way = next(); opt.queued = way == "queued"; if (way != "queued" && way != "ahead") { fail("--pacing ahead|queued", own_console); return 2; } }
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
        // a room of our own (tools/recomp/net2/launch.cpp), as the macOS and Linux programs
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
        else if (a == "--no-log") opt.no_log = true;
        else if (a == "--no-films") opt.no_films = true;
        else if (a == "--help" || a == "-h" || a == "/?") { printf("%s", HELP); return 0; }
        else if (a.compare(0, 2, "--") != 0) opt.disc = a;      // a file dropped on the program: the disc image
        else { fail("unknown option " + a + " (see --help; the runtime's own arguments go after --)", own_console); return 2; }
    }
    for (; k < argc; k++) pass.push_back(argv[k]);
    if (!pass.empty() && (pass[0] == "boot" || pass[0] == "resume")) { mode = pass[0]; pass.erase(pass.begin()); }
    (void)code_like;
    bool settings_later = opt.settings_file.empty() && !no_settings;       // <data>\settings.txt, once the data directory is known
    auto apply_settings = [&](const std::string& file) {
        if (!file.empty() && !opt.set.load(file, log_line) && file == opt.settings_file) log_line("cannot read the settings file " + file);
        if (plain) opt.set.plain();
        for (auto& kv : overrides) opt.set.set(kv.first, kv.second);
        // a folder given with a slash at its end is the same folder
        while (opt.set.art_pack.size() > 3 && (opt.set.art_pack.back() == '\\' || opt.set.art_pack.back() == '/')) opt.set.art_pack.pop_back();
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

    // where things are: everything beside the program
    wchar_t module[MAX_PATH * 4];
    GetModuleFileNameW(nullptr, module, MAX_PATH * 4);
    std::string bin = narrow(module);
    bin = bin.substr(0, bin.find_last_of("\\/"));
    if (opt.data.empty()) opt.data = bin + (opt.player > 1 ? "\\rta-data-player" + std::to_string(opt.player) : std::string("\\rta-data"));
    std::error_code ec;
    std::filesystem::create_directories(std::filesystem::path(wide(opt.data)), ec);

    // The output of a program started by a double click is lost with its console: write it
    // where it can be sent from.  Unbuffered, so that the last line before a crash is there.
    if (!opt.no_log && _isatty(_fileno(stdout))) {
        std::string log = opt.data + "\\rta_app-log.txt";
        printf("rta_app: the log of this run is written to %s (send that file with a report; --no-log keeps it here)\n", log.c_str());
        fflush(stdout);
        if (freopen(log.c_str(), "w", stdout)) {
            _dup2(_fileno(stdout), _fileno(stderr));
            setvbuf(stdout, nullptr, _IONBF, 0);
            setvbuf(stderr, nullptr, _IONBF, 0);
        }
    }
    {
        OSVERSIONINFOW version;                         // for the report: which Windows (the manifest makes this true)
        memset(&version, 0, sizeof version);
        version.dwOSVersionInfoSize = sizeof version;
        typedef LONG(WINAPI* RtlGetVersion)(OSVERSIONINFOW*);
        HMODULE ntdll = GetModuleHandleW(L"ntdll.dll");
        if (auto get = ntdll ? (RtlGetVersion)(void*)GetProcAddress(ntdll, "RtlGetVersion") : nullptr) get(&version);
        SYSTEM_INFO si;
        GetSystemInfo(&si);
        char text[200];
        snprintf(text, sizeof text, "Windows %lu.%lu build %lu, %lu processors, code page %u", version.dwMajorVersion, version.dwMinorVersion,
                 version.dwBuildNumber, si.dwNumberOfProcessors, GetACP());
        log_line(text);
    }

    if (settings_later) {
        // the file beside the memory cards; a first run that somebody plays writes one to edit
        std::string file = opt.data + "\\settings.txt";
        bool there = file_exists(file);
        apply_settings(there ? file : std::string());
        if (!there && opt.test.empty() && !opt.offscreen) app::Settings().save(file, (std::string(fpview::settings_text()) + "\n" + fpcontrols::settings_text() + "\n" + fpworld::settings_text() + "\n" + bossmusic::settings_text()).c_str());
    }
#ifdef RTA_NET
    // the lobby server: --server, else server.txt beside the program - its first line that is
    // not empty and not a remark (#) is the address; a line "public = ADDRESS" is --server-public
    if (opt.server.empty()) {
        if (FILE* f = fopen((bin + "\\server.txt").c_str(), "r")) {
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
                    std::string key = text.substr(0, text.find_last_not_of(" \t", eq - 1 < text.size() ? eq - 1 : 0) + 1), value = text.substr(eq + 1);
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
            fail(opt.disc.empty() ? "Give your disc image of Champions: Return to Arms (SLUS-20973 v2.00): drag the .iso file onto rta_app.exe "
                                    "(or onto play.bat), or start it as  rta_app.exe --disc \"C:\\path\\to\\image.iso\""
                                  : "The disc image was not found: " + opt.disc, own_console);
            return 1;
        }
        if (opt.elf.empty()) {
            opt.elf = bin + "\\SLUS_209.73";
            if (!file_exists(opt.elf)) {
                opt.elf = opt.data + "\\SLUS_209.73";
                if (!file_exists(opt.elf) && !apprt::extract_from_disc(opt.disc, "\\SLUS_209.73;1", opt.elf)) {
                    fail("SLUS_209.73 is not on this disc image (is it Champions: Return to Arms, SLUS-20973?): " + opt.disc, own_console);
                    return 1;
                }
            }
        }
    }

    static Screen screen;
    screen.opt = opt;
    g_screen = &screen;
    std::string error;
    if (!screen.create(error)) {
        fail("The window or its OpenGL 4.1 context could not be made: " + error + ". A graphics driver from the maker of the graphics chip "
             "(Intel, AMD, NVIDIA) is needed; the one Windows installs by itself may have no OpenGL.", own_console);
        return 1;
    }
    hostpad::set_window(screen.window);
    hostpad::start(log_line);
    // the tester's kit (testerkit.h): the bug report (F8, L3 + R3), the crash handler, the build line (F9)
    {
        testerkit::Setup kit;
        kit.data_dir = opt.data;
        kit.program = "rta_app.exe (Windows)";
        kit.person = opt.test.empty() && !opt.offscreen;
        static app::Settings kit_settings;
        kit_settings = opt.set;
        static std::string kit_extra;
        kit_extra = std::string("pacing = ") + (opt.queued ? "queued" : "ahead") + "\nfullscreen = " + (opt.set.fullscreen || opt.fullscreen ? "yes" : "no") + "\n";
        kit.describe = [] { return testerkit::describe_app(kit_settings, kit_extra); };
        kit.ask_shot = [](const std::string& path) { std::lock_guard<std::mutex> hold(g_shot_lock); g_shots_asked.push_back(path); };
        kit.log = log_line;
        std::string told = testerkit::start(kit);
        if (!told.empty() && kit.person) MessageBoxW(screen.window, wide(told).c_str(), L"Champions: Return to Arms - the program stopped last time", MB_OK | MB_ICONINFORMATION);
        log_line("build " + testerkit::build_line() + "; F8 reports a bug into " + opt.data + "\\reports");
    }
#ifdef RTA_NET
    onlinewin::attach(screen.window, !opt.test.empty() || opt.offscreen);
#endif

    static Renderer renderer;
    g_renderer = &renderer;
    renderer.gs.layout.enabled = opt.layout;
    renderer.gs.name_textures = !opt.set.art_pack.empty();
    gfxrt::install();
    fpview::install();                                  // (after gfx_rt's: it chains itself in front of the frame hook)
    // the game's own HUD layer and its second group left out, the music's own volume (settings.h; "app option ...")
    renderer.gs.hide_edge = !opt.set.game_hud;
    renderer.gs.hide_text = !opt.set.game_hud_text;
    gfxrt::set_hud_marks(renderer.gs.hide_edge || renderer.gs.hide_text);
    if (opt.set.music_volume < 1.0) bossmusic::game_music_volume(opt.set.music_volume);
    bossmusic::set_data_folder(opt.data);              // the player's boss music: <data>/music/boss/ unless music.boss_dir says otherwise
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
    fpworld::install();     // the world for a camera inside it (the Mac's file; NOT RUN on Windows); after the controls' call-out
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
        g_screen->submit(frame, shots, sink.current);
    };
    screen.setup_pacer(&sink.pacer);
    if (!opt.offscreen && !opt.unpaced && opt.test.empty()) keep_pace();
    sink.start();

    apprt::set_command_handler(app_command);
    apprt::set_finish_handler(final_report);

    // the runtime's arguments
    static std::vector<std::string> args = {argv[0], mode};
    if (mode == "boot") { args.push_back("--elf"); args.push_back(opt.elf); }
    if (!opt.disc.empty()) { args.push_back("--disc"); args.push_back(opt.disc); }
    args.push_back("--card"); args.push_back(opt.data + "\\card");
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
    if (!script_args.empty()) {                         // names for the script's expressions, when they lie beside the program
        if (file_exists(bin + "\\names.tsv")) { args.push_back("--sym"); args.push_back(bin + "\\names.tsv"); }
        std::vector<std::string> found;
        for (std::filesystem::directory_iterator it(std::filesystem::path(wide(bin + "\\symbols")), ec), end; !ec && it != end; it.increment(ec)) {
            std::string name = narrow(it->path().filename().c_str());
            if (name.size() > 4 && name.compare(name.size() - 4, 4, ".tsv") == 0) found.push_back(bin + "\\symbols\\" + name);
        }
        std::sort(found.begin(), found.end());
        for (auto& path : found) { args.push_back("--sym"); args.push_back(path); }
    }
#ifdef RTA_NET
    // the network driver (tools/recomp/net/netdrv.h): where its files are, the server, and
    // what the one-step online is to do.  What follows "--" on the command line comes later
    // and wins.
    args.push_back("--opt"); args.push_back("net-data=" + opt.data);
    args.push_back("--opt"); args.push_back("net-card=" + opt.data + "\\card");
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

    // the window's loop: a frame from the decoder, or whatever Windows has for the window
    for (;;) {
        // (one event may stand for several lists: while one waits, this does not; between two of
        // them Windows' messages get their turn below)
        DWORD woke = MsgWaitForMultipleObjects(1, &screen.frame_event, FALSE, screen.pending() ? 0 : INFINITE, QS_ALLINPUT);
        if (screen.pending()) screen.draw();
        MSG msg;
        while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) end_now(0);
#ifdef RTA_NET
            if (onlinewin::dialog_message(&msg)) continue;      // a key or click for the name question
#endif
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        if (woke == WAIT_FAILED) Sleep(1);
    }
}
#endif  // _WIN32
