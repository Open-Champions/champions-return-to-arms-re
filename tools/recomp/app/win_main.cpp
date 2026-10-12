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
//   --volume V          0..1 (default 1); --mute = --volume 0; --no-sound opens no device
//   --emulator-timing   the I/O processor answers as slowly as on a console
//   --no-films          a film ends at its first picture (when app/film.cpp is part of the program the films play)
//   --script FILE, --do "COMMAND"   scripted input on top of keyboard and controller; the
//                       "app ..." lines of app_main.cpp: shot, key, gcpad, pads, stats, record
//   --offscreen         the window is never shown (pictures and timings only)
//   --unpaced           as fast as the machine goes
//   --png PREFIX --at n,n,...   write the shown picture at these vertical blanks
//   --stop-after N      print the figures and end after N vertical blanks
//   --no-log            leave the output on the console (default: when the output is a
//                       console it goes to <data>\rta_app-log.txt, the file to send with a report)
//
// Keyboard: W A S D left stick, arrows direction pad, I J K L triangle square cross circle,
// Q E L1 R1, 1 3 L2 R2, X C L3 R3, Enter Start, Backspace Select, F12 a picture of the
// game into the data directory.
//
// Threads as in app_main.cpp: the game's (rta::run), the decoder (pipeline.h) and this
// one, which owns the window and OpenGL and paces everything: one picture per 1/60 s,
// locked to the display's refresh when that is a multiple of 60 Hz.
#ifdef _WIN32
#include "app_rt.h"
#include "backend_gl.h"
#include "pad_host.h"
#include "pipeline.h"
#include "recorder.h"
#include "win/wgl.h"

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
    double volume = 1.0;
    std::string test, png, disc, data, elf;
    std::set<uint64_t> at;
    uint64_t stop_after = 0;
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
static void sleep_ms(double ms) {
    if (ms <= 0) return;
    static HANDLE timer = CreateWaitableTimerExW(nullptr, nullptr, 0x00000002 /* CREATE_WAITABLE_TIMER_HIGH_RESOLUTION */, TIMER_ALL_ACCESS);
    if (timer) {
        LARGE_INTEGER due;
        due.QuadPart = -(LONGLONG)(ms * 10000.0);
        if (SetWaitableTimer(timer, &due, 0, nullptr, nullptr, FALSE) && WaitForSingleObject(timer, INFINITE) == WAIT_OBJECT_0) return;
    }
    Sleep((DWORD)(ms + 0.5));
}
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
    default: return 0;
    }
}
static WPARAM key_by_name(const std::string& name) {
    static const struct { const char* name; WPARAM key; } names[] = {
        {"w", 'W'}, {"a", 'A'}, {"s", 'S'}, {"d", 'D'}, {"up", VK_UP}, {"down", VK_DOWN}, {"left", VK_LEFT}, {"right", VK_RIGHT},
        {"i", 'I'}, {"j", 'J'}, {"k", 'K'}, {"l", 'L'}, {"q", 'Q'}, {"e", 'E'}, {"1", '1'}, {"3", '3'}, {"x", 'X'}, {"c", 'C'},
        {"return", VK_RETURN}, {"backspace", VK_BACK}, {"escape", VK_ESCAPE}, {"f", 'F'}};
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

// ---- "app shot" requests (game's thread -> sink -> decoder -> this thread) ------------------------
static std::mutex g_shot_lock;
static std::vector<std::string> g_shots_asked;           // picked up by the sink at this blank

// ---- the window and the main-thread side -----------------------------------------------------
enum { TIMER_END = 1, TIMER_MOVE = 2 };

struct Screen {
    Options opt;
    HWND window = nullptr;
    wgl::Context gl;
    GlBackend* backend = nullptr;
    bool follow_window = false;                         // the picture is drawn at the window's pixel size
    bool is_fullscreen = false;
    WINDOWPLACEMENT placement;
    DWORD normal_style = 0;
    HANDLE frame_event = nullptr;
    unsigned shot_number = 0;
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
        UINT dpi = 96;
        if (HMODULE user = GetModuleHandleW(L"user32.dll"))
            if (auto get = (UINT(WINAPI*)())(void*)GetProcAddress(user, "GetDpiForSystem")) dpi = get();
        if (dpi < 96 || dpi > 960) dpi = 96;
        RECT r = {0, 0, MulDiv(opt.window_w, (int)dpi, 96), MulDiv(opt.window_h, (int)dpi, 96)};
        AdjustWindowRectEx(&r, style, FALSE, ex);
        std::string title = test ? "AGENT TEST - " + opt.test : std::string(TITLE);
        window = CreateWindowExW(ex, wc.lpszClassName, wide(title).c_str(), style, CW_USEDEFAULT, CW_USEDEFAULT, r.right - r.left, r.bottom - r.top,
                                 nullptr, nullptr, wc.hInstance, nullptr);
        if (!window) { error = "CreateWindow failed"; return false; }
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
        int w = opt.size_w, h = opt.size_h;
        if (opt.scale) { w = 640 * opt.scale; h = 448 * opt.scale; }
        if (!w || !h) {
            follow_window = !opt.offscreen;
            int cw = 0, ch = 0;
            client_size(cw, ch);
            h = ch >= 224 ? ch : opt.window_h;
            w = h * 4 / 3;
        }
        opt.size_w = w; opt.size_h = h;
        backend->set_output_size(w, h);
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
        SetEvent(frame_event);
    }

    // main thread: the list in the slot is drawn, shown and paced
    void draw() {
        { std::lock_guard<std::mutex> hold(lock); if (!busy) return; }
        FrameList* frame = &slot;                       // ours until busy is cleared
        double t0 = now_ms();
        wgl::Functions* f = wgl::functions();
        int cw = 0, ch = 0;
        client_size(cw, ch);
        if (follow_window && ch >= 224) {               // the window was resized: draw at its new size
            int h = ch, w = h * 4 / 3;
            if (h != opt.size_h || w != opt.size_w) { opt.size_w = w; opt.size_h = h; backend->set_output_size(w, h); }
        }
        backend->execute(*frame);
        vertices += frame->vertices.size();
        commands += frame->commands.size();
        if (!opt.png.empty() && opt.at.count(blanks)) save(opt.png + "-" + std::to_string(blanks) + ".png");
        for (const std::string& path : slot_shots) save(path);
        slot_shots.clear();
        bool shown = !opt.offscreen && IsWindowVisible(window) && !IsIconic(window) && cw > 0 && ch > 0;
        double swap_start = 0, after = 0;
        if (shown) {
            // with more than one refresh per picture the swap is asked for inside the last of
            // them, so that it lands on the refresh the picture is due at
            if (display_locked && refreshes_per_picture > 1 && last_present != 0) {
                double ask_at = last_present + period_ms - 0.5 * refresh_ms;
                double now = now_ms();
                if (ask_at > now) sleep_ms(ask_at - now);
            }
            f->glBindFramebuffer(GL_FRAMEBUFFER, 0);
            backend->present(cw, ch, 4.0 / 3.0);
            swap_start = now_ms();
            SwapBuffers(gl.dc);
            after = now_ms();
            pace.swap_ms += after - swap_start;
            if (after - swap_start > 1.0) pace.swap_waited++;
        } else { f->glFlush(); after = now_ms(); }
        draw_ms += after - t0;
        if (!opt.unpaced) {
            // One picture per period.  A swap that waited for the display returns at the
            // refresh; one that did not (window hidden, no display lock) is held by the clock.
            double due = last_present + period_ms;
            if (last_present == 0 || after - due > 2 * period_ms) { if (last_present != 0) pace.late_starts++; last_present = after; }
            else if (after < due - 1.5) {
                sleep_ms(due - after);
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
            f->glFinish();
            g_pads.quit = true;                         // the game's thread prints the reports and ends the process
            SetTimer(window, TIMER_END, 3000, nullptr);
        }
        { std::lock_guard<std::mutex> hold(lock); busy = false; }
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
        if (lp & (1 << 30)) return 0;                   // the key repeating
        g_key_events++;
        if (message == WM_SYSKEYDOWN) {                 // Alt held: only Alt+Enter means something here
            if (wp == VK_RETURN && s && !test) s->toggle_fullscreen();
            else if (wp == VK_F4) break;                // Alt+F4 closes, as everywhere
            return 0;
        }
        if (uint32_t bit = key_bit(wp)) { g_keys |= bit; return 0; }
        if (!s || test) return 0;
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
        return 0;
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
        if (wp == TIMER_END) end_now(0);
        if (wp == TIMER_MOVE && s && WaitForSingleObject(s->frame_event, 0) == WAIT_OBJECT_0) s->draw();
        return 0;
    case WM_CLOSE:
        // the game's thread ends the run at its next vertical blank (reports, sound device);
        // if it does not come to one, end here
        g_pads.quit = true;
        SetTimer(hwnd, TIMER_END, 1500, nullptr);
        return 0;
    default:
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
    }
    printf("rta_app: input: %llu key events, controller %s, %u rumble commands\n", (unsigned long long)g_key_events.load(),
           hostpad::name().empty() ? "none" : hostpad::name().c_str(), g_pads.rumbles.load());
    apprt::films_report();
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
    "keys: W A S D left stick; arrows direction pad; I J K L triangle square cross circle; Q E L1 R1; 1 3 L2 R2; X C L3 R3;\n"
    "      Enter Start; Backspace Select; F, F11 or Alt+Enter full screen; Escape leaves full screen; F12 writes a picture\n"
    "a controller that speaks XInput (Xbox; PlayStation through Steam or DS4Windows) is port 1 as well\n";

int main(int argc, char** argv) {
    Options opt;
    std::vector<std::string> pass, script_args;
    std::string mode = "boot";
    if (const char* disc = getenv("RTA_DISC")) opt.disc = disc;
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
        else if (a == "--no-log") opt.no_log = true;
        else if (a == "--no-films") opt.no_films = true;
        else if (a == "--help" || a == "-h" || a == "/?") { printf("%s", HELP); return 0; }
        else if (a.compare(0, 2, "--") != 0) opt.disc = a;      // a file dropped on the program: the disc image
        else { fail("unknown option " + a + " (see --help; the runtime's own arguments go after --)", own_console); return 2; }
    }
    for (; k < argc; k++) pass.push_back(argv[k]);
    if (!pass.empty() && (pass[0] == "boot" || pass[0] == "resume")) { mode = pass[0]; pass.erase(pass.begin()); }

    // where things are: everything beside the program
    wchar_t module[MAX_PATH * 4];
    GetModuleFileNameW(nullptr, module, MAX_PATH * 4);
    std::string bin = narrow(module);
    bin = bin.substr(0, bin.find_last_of("\\/"));
    if (opt.data.empty()) opt.data = bin + "\\rta-data";
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

    static Renderer renderer;
    g_renderer = &renderer;
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
        DWORD woke = MsgWaitForMultipleObjects(1, &screen.frame_event, FALSE, INFINITE, QS_ALLINPUT);
        if (woke == WAIT_OBJECT_0) screen.draw();
        MSG msg;
        while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) end_now(0);
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        if (woke == WAIT_FAILED) Sleep(1);
    }
}
#endif  // _WIN32
