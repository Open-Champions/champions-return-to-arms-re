// web_main.cpp - the native build as a page: the translated game (tools/recomp), its
// runtime, the renderer on WebGL 2 and the sound library in one WebAssembly program.
// The page (index.html, rta-native.js) is the window; this is what app/app_main.cpp is for
// the Mac application, without Qt.
//
// Threads (each a worker on the one shared memory):
//
//   the page's main thread   the page: keyboard, the disc image's reader, the memory
//                            card's store (IndexedDB), the sound device (AudioWorklet).
//                            Runs none of this program except rta_web_* below.
//   main()                   owns the canvas (the page hands it over: OffscreenCanvas) and
//                            WebGL: draws the lists the decoder hands it, one per turn of
//                            its event loop - a browser shows what a worker drew when the
//                            worker's task ends, so this thread never blocks for long
//   the game                 rta::run(): the runtime and the guest threads (pthreads)
//   the decoder              app/pipeline.h: VIF1, VU1, the GS model
//
// Pacing: one picture per 1/59.94 s by the clock, on the drawing thread; the wait travels
// back through the two hand-overs to the game, as in the application.  `--unpaced` (or the
// page's switch) draws as fast as pictures arrive.
//
//   arguments (the page passes them to main): --scale N | --size WxH, --unpaced,
//   --emulator-timing, --no-sound, --script FILE, --do COMMAND, --sym FILE, --stop-after N,
//   --basic-blend, --times, --interpret-vu, and after "--" anything for the runtime.
#include "app_rt.h"
#include "backend_gl.h"
#include "pipeline.h"

#include <emscripten.h>
#include <emscripten/html5.h>
#include <emscripten/threading.h>
#include <GLES3/gl3.h>

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <vector>

using namespace render;
using app::now_ms;

namespace render {
extern uint64_t g_webgl_calls, g_webgl_skipped, g_webgl_feedback_copies;
extern int g_webgl_dual, g_webgl_want_dual;
}
namespace host {
extern std::atomic<uint64_t> g_disc_reads, g_disc_bytes, g_disc_us;
}
std::string rta_sound_figures() __attribute__((weak));

// ---- what the page and the program share ---------------------------------------------------
// 32-bit words the page reads and writes with Atomics (rta-native.js, SHARED_*).
enum { KEY_STICK_UP = 1 << 16, KEY_STICK_DOWN = 1 << 17, KEY_STICK_LEFT = 1 << 18, KEY_STICK_RIGHT = 1 << 19 };
struct Shared {
    std::atomic<uint32_t> keys{0};          // 0  rta::PadButton bits | the four stick keys; the page writes
    std::atomic<uint32_t> unpaced{0};       // 1  1: as fast as it goes
    std::atomic<uint32_t> shot{0};          // 2  the page stores 1 to ask for a picture; 2 = ready below; the page stores 0
    std::atomic<uint32_t> shot_w{0}, shot_h{0}, shot_ptr{0};    // 3 4 5
    std::atomic<uint32_t> canvas_w{0}, canvas_h{0};             // 6 7  the canvas in pixels; the page writes
    std::atomic<uint32_t> quit{0};          // 8
    std::atomic<uint32_t> held{0};          // 9  buttons a test holds (rta.tap), on top of the keys
    std::atomic<uint32_t> sticks{0x80808080};   // 10 lx | ly << 8 | rx << 16 | ry << 24 from a test
    std::atomic<uint32_t> hidden{0};        // 11 the page is not visible (written by the page)
};
static Shared g_shared;

struct Options {
    int size_w = 0, size_h = 0, scale = 2;
    bool unpaced = false, no_sound = false, emulator_timing = false, times = false, interpret = false;
    uint64_t stop_after = 0;
};
static Options g_opt;

// ---- input ---------------------------------------------------------------------------------
struct Pads : rta::PadSource {
    std::atomic<uint32_t> rumbles{0};
    void read(unsigned port, uint64_t, rta::PadState& state) override {
        if (g_shared.quit) apprt::finish(0);
        state = apprt::script_pad(port);
        if (port != 0) return;
        uint32_t keys = g_shared.keys, sticks = g_shared.sticks;
        state.buttons |= (uint16_t)keys | (uint16_t)g_shared.held;
        auto rest = [](uint8_t x, uint8_t y) { return x == 128 && y == 128; };
        if (rest(state.lx, state.ly)) {
            if (!rest((uint8_t)sticks, (uint8_t)(sticks >> 8))) { state.lx = (uint8_t)sticks; state.ly = (uint8_t)(sticks >> 8); }
            else {
                state.lx = (keys & KEY_STICK_LEFT) ? ((keys & KEY_STICK_RIGHT) ? 128 : 0) : (keys & KEY_STICK_RIGHT) ? 255 : 128;
                state.ly = (keys & KEY_STICK_UP) ? ((keys & KEY_STICK_DOWN) ? 128 : 0) : (keys & KEY_STICK_DOWN) ? 255 : 128;
            }
        }
        if (rest(state.rx, state.ry)) { state.rx = (uint8_t)(sticks >> 16); state.ry = (uint8_t)(sticks >> 24); }
    }
    void rumble(unsigned, uint8_t, uint8_t) override { rumbles++; }
};
static Pads g_pads;

// ---- the drawing thread ----------------------------------------------------------------------
struct Screen {
    EMSCRIPTEN_WEBGL_CONTEXT_HANDLE context = 0;
    GlBackend* backend = nullptr;
    int out_w = 0, out_h = 0;
    // hand-over from the decoder
    std::mutex lock;
    std::condition_variable changed;
    FrameList slot;
    bool busy = false;
    double submit_wait_ms = 0;                          // time the decoder waited for this thread
    // pacing
    double period_ms = 1000.0 / 59.94, last_present = 0;
    // figures (read by rta_web_info on the page's thread: plain words, no lock)
    std::atomic<uint64_t> presents{0}, vertices{0}, commands{0}, late{0};
    std::atomic<uint64_t> draw_us{0};

    bool create() {
        EmscriptenWebGLContextAttributes attributes;
        emscripten_webgl_init_context_attributes(&attributes);
        attributes.majorVersion = 2;
        attributes.minorVersion = 0;
        attributes.alpha = false;
        attributes.depth = false;
        attributes.stencil = false;
        attributes.antialias = false;
        attributes.powerPreference = EM_WEBGL_POWER_PREFERENCE_HIGH_PERFORMANCE;
        attributes.proxyContextToMainThread = EMSCRIPTEN_WEBGL_CONTEXT_PROXY_DISALLOW;
        attributes.renderViaOffscreenBackBuffer = false;
        context = emscripten_webgl_create_context("#canvas", &attributes);
        if (context <= 0) { fprintf(stderr, "rta: no WebGL 2 context on the canvas (%d)\n", (int)context); return false; }
        emscripten_webgl_make_context_current(context);
        backend = new GlBackend;
        out_w = g_opt.size_w ? g_opt.size_w : 640 * g_opt.scale;
        out_h = g_opt.size_h ? g_opt.size_h : 448 * g_opt.scale;
        backend->set_output_size(out_w, out_h);
        printf("rta: WebGL 2 (%s) on %s; picture drawn at %d x %d; blending: %s\n", (const char*)glGetString(GL_VERSION), (const char*)glGetString(GL_RENDERER),
               out_w, out_h, g_webgl_dual ? "dual-source (WEBGL_blend_func_extended)" : "basic (no dual-source extension)");
        return true;
    }
    // on the decoder's thread: take this list to be drawn; returns when the one before it was
    void submit(FrameList& frame) {
        std::unique_lock<std::mutex> hold(lock);
        double w0 = now_ms();
        changed.wait(hold, [this] { return !busy; });
        submit_wait_ms += now_ms() - w0;
        std::swap(slot.vertices, frame.vertices);
        std::swap(slot.commands, frame.commands);
        std::swap(slot.textures, frame.textures);
        std::swap(slot.targets, frame.targets);
        std::swap(slot.dead_textures, frame.dead_textures);
        slot.show_target = frame.show_target;
        memcpy(slot.show_rect, frame.show_rect, sizeof(slot.show_rect));
        slot.number = frame.number;
        busy = true;
        changed.notify_all();
    }

    // one turn of the drawing thread's event loop
    void turn() {
        {
            std::unique_lock<std::mutex> hold(lock);
            if (!busy) changed.wait_for(hold, std::chrono::milliseconds(4), [this] { return busy; });
            if (!busy) return;
        }
        bool unpaced = g_opt.unpaced || g_shared.unpaced;
        if (!unpaced && last_present != 0) {
            double due = last_present + period_ms, now = now_ms();
            if (due - now > 5.0) { std::this_thread::sleep_for(std::chrono::milliseconds(3)); return; }    // come back: the event loop goes on
            if (due > now) std::this_thread::sleep_for(std::chrono::duration<double, std::milli>(due - now));
        }
        double t0 = now_ms();
        backend->execute(slot);
        vertices += slot.vertices.size();
        commands += slot.commands.size();
        int cw = g_shared.canvas_w, ch = g_shared.canvas_h;
        if (cw <= 0 || ch <= 0) emscripten_webgl_get_drawing_buffer_size(context, &cw, &ch);
        backend->present(cw, ch, 4.0 / 3.0);
        if (g_shared.shot == 1) take_shot();
        double after = now_ms();
        draw_us += (uint64_t)((after - t0) * 1000.0);
        if (unpaced || last_present == 0) last_present = after;
        else {
            double due = last_present + period_ms;
            if (after - due > 2 * period_ms) { late++; last_present = after; } else last_present = due;
        }
        presents++;
        if (g_opt.stop_after && presents >= g_opt.stop_after) g_shared.quit = 1;
        { std::lock_guard<std::mutex> hold(lock); busy = false; }
        changed.notify_all();
    }

    std::vector<uint8_t> shot_pixels;
    void take_shot() {
        int w = 0, h = 0;
        if (!backend->read_shown(shot_pixels, w, h)) { g_shared.shot = 0; return; }
        g_shared.shot_w = w; g_shared.shot_h = h;
        g_shared.shot_ptr = (uint32_t)(uintptr_t)shot_pixels.data();
        g_shared.shot = 2;
    }
};
static Screen g_screen;

static app::Sink g_sink;
static render::Renderer* g_renderer;

// ---- what the page calls (on its own thread) -----------------------------------------------------
extern "C" {

EMSCRIPTEN_KEEPALIVE uint32_t* rta_web_shared() { return (uint32_t*)&g_shared; }

// figures since the start, as JSON; the page takes differences
EMSCRIPTEN_KEEPALIVE const char* rta_web_info() {
    static char text[2048];
    const uint8_t* ram = rta::memory();
    char level[13] = "";
    uint32_t sim = 0, frontend = 0, in_frontend = 0;
    if (ram) {
        memcpy(level, ram + 0x41b721, 12);
        for (char* p = level; *p; p++) if (*p < 32 || *p > 126 || *p == '"' || *p == '\\') *p = '?';
        memcpy(&sim, ram + 0x44fdcc, 4);
    }
    std::string sound = rta_sound_figures ? rta_sound_figures() : std::string();
    for (char& ch : sound) if (ch == '"' || ch == '\\' || ch < 32) ch = ' ';
    snprintf(text, sizeof text,
             "{\"now\":%.3f,\"fields\":%llu,\"presents\":%llu,\"game_ms\":%.3f,\"decode_ms\":%.3f,\"decode_cpu_ms\":%.3f,\"draw_ms\":%.3f,"
             "\"submit_wait_ms\":%.3f,\"late\":%llu,\"vertices\":%llu,\"commands\":%llu,\"draws\":%llu,\"gl_calls\":%llu,\"gl_skipped\":%llu,"
             "\"feedback_copies\":%llu,\"dual\":%d,\"disc_reads\":%llu,\"disc_bytes\":%llu,\"disc_ms\":%.1f,\"out\":[%d,%d],"
             "\"machine_s\":%.3f,\"sim\":%u,\"level\":\"%s\",\"rumbles\":%u,\"sound\":\"%s\","
             "\"vu_translated\":%d,\"vu_runs\":%llu,\"vu_run_ms\":%.3f,\"kick_ms\":%.3f,\"path3_ms\":%.3f,\"textures_made\":%llu,\"upload_mb\":%.1f,\"vu_bad\":%llu}",
             emscripten_get_now(), (unsigned long long)g_sink.blanks, (unsigned long long)g_screen.presents.load(), g_sink.game_ms,
             g_sink.decode_wall_ms, g_sink.decode_cpu_ms, g_screen.draw_us.load() / 1000.0, g_screen.submit_wait_ms,
             (unsigned long long)g_screen.late.load(), (unsigned long long)g_screen.vertices.load(), (unsigned long long)g_screen.commands.load(),
             (unsigned long long)(g_screen.backend ? g_screen.backend->draw_calls() : 0), (unsigned long long)g_webgl_calls,
             (unsigned long long)g_webgl_skipped, (unsigned long long)g_webgl_feedback_copies, g_webgl_dual,
             (unsigned long long)host::g_disc_reads.load(), (unsigned long long)host::g_disc_bytes.load(), host::g_disc_us.load() / 1000.0,
             g_screen.out_w, g_screen.out_h, ram ? apprt::machine_seconds() : 0.0, sim, level, g_pads.rumbles.load(), sound.c_str(),
             g_renderer ? (int)g_renderer->vif.vu.translated : -1, (unsigned long long)(g_renderer ? g_renderer->vif.stats.mscal : 0),
             g_renderer ? g_renderer->vif.stats.run_ms : 0.0, g_renderer ? g_renderer->gs.stats.kick_ms : 0.0, g_renderer ? g_renderer->gs.stats.path3_ms : 0.0,
             (unsigned long long)(g_renderer ? g_renderer->gs.stats.textures_made : 0), g_renderer ? g_renderer->gs.stats.upload_bytes / 1048576.0 : 0.0,
             (unsigned long long)(g_renderer ? g_renderer->vif.vu.bad : 0));
    (void)frontend; (void)in_frontend;
    return text;
}

// a word of the game's main memory (tests: where is the game?)
EMSCRIPTEN_KEEPALIVE uint32_t rta_web_peek(uint32_t address, int size) {
    const uint8_t* ram = rta::memory();
    if (!ram || address > 0x2000000 - 4) return 0;
    uint32_t v = 0;
    memcpy(&v, ram + address, size == 1 ? 1 : size == 2 ? 2 : 4);
    return v;
}

}  // extern "C"

static void turn() { g_screen.turn(); }

// The drawing thread's loop: `fn` once per task of this worker's event loop, through a
// message channel of the worker's own (a timer would be held to 4 ms a turn, and
// Emscripten's own "immediate" main loop sends every turn by way of the page's main thread).
EM_JS_DEPS(rta_web_loop_deps, "$callUserCallback,$runtimeKeepalivePush");
EM_JS(void, rta_web_loop, (int fn), {
    var channel = new MessageChannel();
    runtimeKeepalivePush();
    channel.port1.onmessage = function() {
        callUserCallback(function() { wasmTable.get(fn)(); });
        channel.port2.postMessage(0);
    };
    channel.port2.postMessage(0);
});

int main(int argc, char** argv) {
    std::vector<std::string> pass, script_args;
    for (int k = 1; k < argc; k++) {
        std::string a = argv[k];
        auto next = [&]() -> std::string { return k + 1 < argc ? argv[++k] : ""; };
        if (a == "--") { for (k++; k < argc; k++) pass.push_back(argv[k]); break; }
        else if (a == "--size") { std::string s = next(); sscanf(s.c_str(), "%dx%d", &g_opt.size_w, &g_opt.size_h); }
        else if (a == "--scale") { g_opt.scale = atoi(next().c_str()); if (g_opt.scale < 1) g_opt.scale = 1; if (g_opt.scale > 8) g_opt.scale = 8; }
        else if (a == "--unpaced") g_opt.unpaced = true;
        else if (a == "--no-sound") g_opt.no_sound = true;
        else if (a == "--basic-blend") g_webgl_want_dual = 0;
        else if (a == "--times") g_opt.times = true;            // time VU1 runs and the GS paths (a clock read around each)
        else if (a == "--interpret-vu") g_opt.interpret = true; // do not use the linked VU1 translation
        else if (a == "--emulator-timing") g_opt.emulator_timing = true;
        else if (a == "--script" || a == "--do" || a == "--sym") { script_args.push_back(a); script_args.push_back(next()); }
        else if (a == "--stop-after") g_opt.stop_after = strtoull(next().c_str(), nullptr, 10);
        else { fprintf(stderr, "rta: unknown option %s\n", a.c_str()); return 2; }
    }
    // the game's executable comes off the disc image the page was given
    mkdir("/data", 0755);
    std::string elf = "/data/SLUS_209.73";
    struct stat st;
    if (stat(elf.c_str(), &st) != 0 && !apprt::extract_from_disc("disc", "\\SLUS_209.73;1", elf)) {
        fprintf(stderr, "rta: SLUS_209.73 is not on this disc image\n");
        return 1;
    }
    if (!g_screen.create()) return 1;

    static Renderer renderer;
    g_renderer = &renderer;
    renderer.vif.time_runs = renderer.gs.time_paths = g_opt.times;
    if (g_opt.interpret) renderer.vif.vu.use_translation = false;
    g_sink.renderer = &renderer;
    g_sink.waited_downstream_ms = &g_screen.submit_wait_ms;
    renderer.on_frame = [](FrameList& frame) { g_screen.submit(frame); };
    g_sink.start();

    static std::vector<std::string> args = {"rta", "boot", "--elf", elf, "--disc", "disc", "--card", "/data/card"};
    if (g_opt.emulator_timing) args.push_back("--emulator-timing");
    if (!g_opt.no_sound) {
        args.push_back("--opt"); args.push_back("sound-out=device");
    }
    args.insert(args.end(), script_args.begin(), script_args.end());
    // the runtime ends a run when its script has ended unless it was told how long to go on:
    // a page goes on (a script that wants the end says `quit`)
    if (!script_args.empty()) { args.push_back("--fields"); args.push_back("4000000000"); }
    args.insert(args.end(), pass.begin(), pass.end());
    static std::vector<char*> run_args;
    for (auto& a : args) run_args.push_back(&a[0]);
    static rta::Hooks hooks;
    hooks.video = &g_sink;
    hooks.pad = &g_pads;
    std::thread game([] { rta::run((int)run_args.size(), run_args.data(), hooks); });
    game.detach();

    // the drawing thread from here on: one turn per task of this worker's event loop
    rta_web_loop((int)(uintptr_t)&turn);
    return 0;
}
