// app_main.cpp - rta_render: the native game (translated code + runtime) with its picture
// in a window.
//
//   rta_render [picture options] -- <arguments of the runtime: boot ... | resume ...>
//
//   --window WxH        window size in points (default 960x720); the picture keeps 4:3
//   --size WxH          resolution the picture is drawn at (default: the window's pixels)
//   --offscreen         no window at all (pictures and timings only)
//   --test "TEXT"       a test run on a computer somebody is using: the window is titled
//                       "AGENT TEST - TEXT", small, behind the others, takes no keyboard
//   --unpaced           do not hold the game to 59.94 pictures a second: as fast as the machine goes
//   --png PREFIX --at n,n,...   write the shown picture at these vertical blanks
//   --stop-after N      print the timings and end after N vertical blanks
//   --record FILE [--record-frames A-B]   also write the picture stream (stream.h)
//   --serial            decode on the game's thread (no decoder thread)
//
// Threads: three stages, each handing a whole frame to the next and waiting only when the
// next is still busy with the one before:
//   game threads   the runtime calls the picture sink; the sink copies what it is handed
//                  into the frame's batch, with the stores the game made into VU1 memory
//                  and the texture headers that changed (both read here, where the game
//                  stands still), and hands the batch over at the vertical blank;
//   decoder        VIF1, the VU1 interpreter and the GS model, on memories of their own
//                  (as when a recorded stream is played back), producing a FrameList;
//   main thread    OpenGL and the window; when paced, it holds each picture to its 1/59.94 s
//                  and that wait travels back through the two hand-overs to the game.
// --serial does all of it on the game's thread instead (one stage, for comparison).
#include "backend_gl.h"
#include "recorder.h"
#include "renderer.h"

#include "iface.h"

#include <QCoreApplication>
#include <QEvent>
#include <QGuiApplication>
#include <QImage>
#include <QOffscreenSurface>
#include <QOpenGLContext>
#include <QOpenGLExtraFunctions>
#include <QSurfaceFormat>
#include <QWindow>

#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <set>
#include <string>
#include <sys/resource.h>
#include <thread>
#include <unistd.h>
#include <vector>

using namespace render;

static double now_ms() {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
static double cpu_ms() {                                // processor time of the whole process
    rusage u;
    getrusage(RUSAGE_SELF, &u);
    return (u.ru_utime.tv_sec + u.ru_stime.tv_sec) * 1000.0 + (u.ru_utime.tv_usec + u.ru_stime.tv_usec) / 1000.0;
}

struct Options {
    int window_w = 960, window_h = 720, size_w = 0, size_h = 0;
    bool offscreen = false, unpaced = false, serial = false;
    std::string test, png, record;
    std::set<uint64_t> at;
    uint64_t stop_after = 0, record_first = 0, record_last = ~0ull;
};

static const QEvent::Type FrameEvent = (QEvent::Type)(QEvent::User + 1);

class Screen;
struct Sink;
static Sink* g_sink;
static double g_submit_wait_ms;           // time the decoder waited for the OpenGL thread to take a frame
static void report_stages();
static Screen* g_screen;
static Renderer* g_renderer;

// The main-thread side: owns the context, the backend and the window.
class Screen : public QObject {
  public:
    Options opt;
    QWindow* window = nullptr;
    QOffscreenSurface* offscreen = nullptr;
    QOpenGLContext* context = nullptr;
    GlBackend* backend = nullptr;
    // hand-over
    std::mutex lock;
    std::condition_variable done;
    // figures
    uint64_t blanks = 0;
    double draw_ms = 0, start_ms = 0, start_cpu = 0, gl_cpu = 0, deadline = 0;
    size_t vertices = 0, commands = 0;

    QSurface* surface() { return window ? (QSurface*)window : (QSurface*)offscreen; }

    void create() {
        QSurfaceFormat format = QSurfaceFormat::defaultFormat();
        if (opt.offscreen) {
            offscreen = new QOffscreenSurface;
            offscreen->setFormat(format);
            offscreen->create();
        } else {
            window = new QWindow;
            window->setSurfaceType(QSurface::OpenGLSurface);
            window->setFormat(format);
            if (!opt.test.empty()) {
                window->setTitle(QString("AGENT TEST - ") + QString::fromStdString(opt.test));
                window->setFlags(window->flags() | Qt::WindowDoesNotAcceptFocus | Qt::WindowStaysOnBottomHint);
            } else window->setTitle("Champions: Return to Arms (native)");
            window->resize(opt.window_w, opt.window_h);
            window->show();
            if (!opt.test.empty()) window->lower();
        }
        context = new QOpenGLContext;
        context->setFormat(format);
        if (!context->create() || !context->makeCurrent(surface())) { fprintf(stderr, "rta_render: no OpenGL 4.1 context\n"); _exit(1); }
        QOpenGLExtraFunctions* gl = context->extraFunctions();
        fprintf(stderr, "rta_render: OpenGL %s on %s\n", (const char*)gl->glGetString(GL_VERSION), (const char*)gl->glGetString(GL_RENDERER));
        backend = new GlBackend;
        int w = opt.size_w, h = opt.size_h;
        if (!w || !h) {
            double ratio = window ? window->devicePixelRatio() : 1.0;
            h = (int)(opt.window_h * ratio);
            w = h * 4 / 3;
        }
        opt.size_w = w; opt.size_h = h;
        backend->set_output_size(w, h);
        fprintf(stderr, "rta_render: picture drawn at %d x %d%s\n", w, h, opt.unpaced ? ", not paced" : ", paced at 59.94 pictures a second");
        start_ms = now_ms();
        start_cpu = cpu_ms();
    }

    // called on the decoder's (or, serial, the game's) thread: take this list to be drawn.
    // Returns as soon as the list before it has been drawn; the caller gets that one's
    // vectors back to fill again, so the next frame is decoded while this one is drawn.
    void submit(FrameList& frame) {
        std::unique_lock<std::mutex> hold(lock);
        double w0 = now_ms();
        done.wait(hold, [this] { return !busy; });
        g_submit_wait_ms += now_ms() - w0;
        std::swap(slot.vertices, frame.vertices);
        std::swap(slot.commands, frame.commands);
        std::swap(slot.textures, frame.textures);
        std::swap(slot.targets, frame.targets);
        std::swap(slot.dead_textures, frame.dead_textures);
        std::swap(slot.dead_targets, frame.dead_targets);
        slot.show_target = frame.show_target;
        memcpy(slot.show_rect, frame.show_rect, sizeof(slot.show_rect));
        slot.number = frame.number;
        busy = true;
        QCoreApplication::postEvent(this, new QEvent(FrameEvent));
    }
    FrameList slot;
    bool busy = false;

    bool event(QEvent* e) override {
        if (e->type() != FrameEvent) return QObject::event(e);
        FrameList* frame = &slot;                       // ours until busy is cleared
        double t0 = now_ms();
        context->makeCurrent(surface());
        QOpenGLExtraFunctions* gl = context->extraFunctions();
        backend->execute(*frame);
        vertices += frame->vertices.size();
        commands += frame->commands.size();
        if (!opt.png.empty() && opt.at.count(blanks)) save(blanks);
        if (window && window->isExposed()) {
            double ratio = window->devicePixelRatio();
            gl->glBindFramebuffer(GL_FRAMEBUFFER, context->defaultFramebufferObject());
            backend->present((int)(window->width() * ratio), (int)(window->height() * ratio), 4.0 / 3.0);
            context->swapBuffers(window);
        } else gl->glFlush();
        draw_ms += now_ms() - t0;
        if (!opt.unpaced) {
            // One picture per vertical blank of the console, 59.94 a second, whatever the
            // display's own rate: a deadline per picture; a late one is not made up for by
            // hurrying more than three pictures.
            const double period = 1000.0 / 59.94;
            double now = now_ms();
            if (deadline == 0 || now - deadline > 3 * period) deadline = now;
            deadline += period;
            if (deadline > now) std::this_thread::sleep_for(std::chrono::duration<double, std::milli>(deadline - now));
        }
        blanks++;
        if (opt.stop_after && blanks >= opt.stop_after) {
            gl->glFinish();
            report();
            fflush(stdout);
            if (window) window->close();
            _exit(0);
        }
        { std::lock_guard<std::mutex> hold(lock); busy = false; }
        done.notify_all();
        return true;
    }

    void save(uint64_t number) {
        std::vector<uint8_t> rgba;
        int w = 0, h = 0;
        if (!backend->read_shown(rgba, w, h)) return;
        QImage image(rgba.data(), w, h, w * 4, QImage::Format_RGBA8888);
        std::string name = opt.png + "-" + std::to_string(number) + ".png";
        image.convertToFormat(QImage::Format_RGB888).save(QString::fromStdString(name));
        fprintf(stderr, "rta_render: wrote %s (%d x %d)\n", name.c_str(), w, h);
    }

    void report() {
        double wall = now_ms() - start_ms, cpu = cpu_ms() - start_cpu, n = blanks ? (double)blanks : 1;
        double load[3] = {0, 0, 0};
        getloadavg(load, 3);
        printf("rta_render: %llu vertical blanks in %.0f ms: %.1f pictures a second of wall time at %d x %d (%s)\n", (unsigned long long)blanks, wall,
               1000.0 * n / wall, opt.size_w, opt.size_h, opt.offscreen ? (opt.unpaced ? "no window, not paced" : "no window, paced") : opt.unpaced ? "window, not paced" : "window, paced");
        printf("rta_render: %s\n", opt.serial ? "one stage: decoding on the game's thread" : "three stages: game, decoder thread, OpenGL thread");
        printf("rta_render: per picture %.2f ms of wall time, %.2f ms of processor time over all threads (game + runtime + renderer + OpenGL calls), of which the "
               "main thread waited %.2f ms on OpenGL; %.0f vertices, %.0f draw commands\n", wall / n, cpu / n, draw_ms / n, vertices / n, commands / n);
        report_stages();
        printf("rta_render: load average while measured: %.0f\n", load[0]);
    }
};


// One frame of what the sink was handed, in order.
struct Batch {
    struct Record { uint32_t kind, a; uint64_t b; size_t offset, count; };
    std::vector<Record> records;
    std::vector<uint32_t> words;
    void put(uint32_t kind, uint32_t a, uint64_t b, const uint32_t* data, size_t count) {
        records.push_back({kind, a, b, words.size(), count});
        if (count) words.insert(words.end(), data, data + count);
    }
    void clear() { records.clear(); words.clear(); }
};

static void play(Renderer& r, std::vector<uint8_t>& ram, const Batch& batch) {
    for (const Batch::Record& e : batch.records) {
        const uint32_t* w = batch.words.data() + e.offset;
        switch (e.kind) {
        case SK_VIF1: r.vif1(w, e.count); break;
        case SK_GIF: r.gif(w, e.count); break;
        case SK_REG: r.reg(e.a, e.b); break;
        case SK_VBLANK: r.vblank(e.a, e.b); break;
        case SK_VU1DATA: memcpy(r.vif.vu.data + (e.a & 0x3FF) * 16, w, 16); break;
        case SK_VU1MICRO: memcpy(r.vif.vu.micro, w, 0x4000); r.vif.vu.micro_changed(); break;
        case SK_RAM:                                    // a texture header (32 bytes)
            if ((uint64_t)e.a + e.count * 4 <= ram.size()) memcpy(ram.data() + e.a, w, e.count * 4);
            if (std::find(r.index.headers.begin(), r.index.headers.end(), e.a) == r.index.headers.end()) r.index.headers.push_back(e.a);
            break;
        default: break;
        }
    }
}

// The sink.  With a decoder thread it only copies; the decoder owns a renderer with its own
// VU1 memory and its own copy of main memory, kept right by what the sink sends along.
struct Sink : rta::VideoSink {
    bool serial = false;
    bool first = true;
    // pipelined
    Batch filling;
    std::mutex lock;
    std::condition_variable changed;
    Batch waiting;
    bool has_waiting = false;
    std::vector<uint8_t> ram_copy;                      // the decoder's main memory
    std::vector<uint8_t> vu_data, vu_micro;             // VU1 memory as last sent
    TexIndex index;                                     // over the game's memory, read on the game's thread
    std::vector<uint16_t> blocks;
    uint64_t blanks = 0;
    // figures: wall time the game side took per frame (from leaving one vertical blank to
    // entering the next, the sink's copying included), and the decoder's own processor time
    double game_ms = 0, decode_cpu_ms = 0, decode_wall_ms = 0, left_at = 0;

    void prepare() {
        if (!first) return;
        first = false;
        if (serial) {
            g_renderer->set_memory(rta::memory(), 0x2000000);
            if (g_renderer->needs_program()) g_renderer->load_program((const uint32_t*)(rta::memory() + 0x3e5ec0), 940 * 4);
            return;
        }
        ram_copy.assign(rta::memory(), rta::memory() + 0x2000000);
        vu_data.assign(0x4000, 0);
        vu_micro.assign(0x4000, 0);
        index.ram = rta::memory();
        index.size = 0x2000000;
        rescan();
    }
    void rescan() {
        // every header new to the list is sent once; the ones already known keep their state
        std::vector<uint32_t> old_headers = index.headers;
        std::vector<uint16_t> old_blocks = blocks;
        index.scan();
        blocks.assign(index.headers.size(), 0xFFFF);
        size_t at = 0;                                  // both lists are in address order
        for (size_t k = 0; k < index.headers.size(); k++) {
            while (at < old_headers.size() && old_headers[at] < index.headers[k]) at++;
            if (at < old_headers.size() && old_headers[at] == index.headers[k]) blocks[k] = old_blocks[at];
        }
        last_scan = blanks;
    }
    uint64_t last_scan = 0;
    void sync() {                                       // on the game's thread, before a transfer is queued
        const uint8_t* d = rta::vu1_data();
        for (uint32_t q = 0; q < 0x400; q++)
            if (memcmp(d + q * 16, vu_data.data() + q * 16, 16)) {
                memcpy(vu_data.data() + q * 16, d + q * 16, 16);
                filling.put(SK_VU1DATA, q, 0, (const uint32_t*)(d + q * 16), 4);
            }
        if (memcmp(rta::vu1_micro(), vu_micro.data(), 0x4000)) {
            memcpy(vu_micro.data(), rta::vu1_micro(), 0x4000);
            filling.put(SK_VU1MICRO, 0, 0, (const uint32_t*)rta::vu1_micro(), 0x1000);
        }
        for (size_t k = 0; k < blocks.size(); k++) {
            const uint8_t* h = index.ram + index.headers[k];
            uint16_t block = TexIndex::u16(h + 0x18);
            if (block == blocks[k]) continue;
            blocks[k] = block;
            uint32_t words[8];
            memcpy(words, h, 32);
            filling.put(SK_RAM, index.headers[k], 0, words, 8);
        }
    }
    void vif1(const uint32_t* words, size_t count) override {
        prepare();
        if (serial) { g_renderer->vif1(words, count); return; }
        sync();
        filling.put(SK_VIF1, 0, 0, words, count);
    }
    void gif(const uint32_t* words, size_t count) override {
        prepare();
        if (serial) { g_renderer->gif(words, count); return; }
        filling.put(SK_GIF, 0, 0, words, count);
    }
    void reg(uint32_t address, uint64_t value) override {
        if (serial) { g_renderer->reg(address, value); return; }
        filling.put(SK_REG, address, value, nullptr, 0);
    }
    void vblank(unsigned field, uint64_t number) override {
        if (serial) { g_renderer->vblank(field, number); return; }
        prepare();
        // the game loads textures as it goes: when the decoder met one it has no header for,
        // look through memory again (at most twice a second: it takes some milliseconds)
        blanks++;
        if (left_at != 0) game_ms += now_ms() - left_at;
        if (g_renderer->index.missed && blanks - last_scan >= 30) { g_renderer->index.missed = false; rescan(); }
        filling.put(SK_VBLANK, field, number, nullptr, 0);
        std::unique_lock<std::mutex> hold(lock);
        changed.wait(hold, [this] { return !has_waiting; });
        std::swap(waiting, filling);
        has_waiting = true;
        filling.clear();
        changed.notify_all();
        left_at = now_ms();
    }
    void decoder_loop() {                               // the decoder thread
        Batch mine;
        bool started = false;
        for (;;) {
            {
                std::unique_lock<std::mutex> hold(lock);
                changed.wait(hold, [this] { return has_waiting; });
                std::swap(mine, waiting);
                has_waiting = false;
                changed.notify_all();
            }
            if (!started) {
                started = true;
                g_renderer->set_memory(ram_copy.data(), (uint32_t)ram_copy.size());
                g_renderer->index.auto_rescan = false;
                if (g_renderer->needs_program()) g_renderer->load_program((const uint32_t*)(ram_copy.data() + 0x3e5ec0), 940 * 4);
            }
            timespec a, b;
            clock_gettime(CLOCK_THREAD_CPUTIME_ID, &a);
            double w0 = now_ms(), waited0 = g_submit_wait_ms;
            play(*g_renderer, ram_copy, mine);
            clock_gettime(CLOCK_THREAD_CPUTIME_ID, &b);
            decode_cpu_ms += (b.tv_sec - a.tv_sec) * 1000.0 + (b.tv_nsec - a.tv_nsec) / 1e6;
            decode_wall_ms += now_ms() - w0 - (g_submit_wait_ms - waited0);
            mine.clear();
        }
    }
};

static void report_stages() {
    if (!g_sink || g_sink->serial || !g_sink->blanks) return;
    double n = (double)g_sink->blanks;
    printf("rta_render: per picture, by stage: game side %.2f ms of wall time (translated game, runtime, the sink's copying); decoder %.2f ms of wall time, "
           "%.2f ms of its own processor time (VIF1, VU1, GS model)\n", g_sink->game_ms / n, g_sink->decode_wall_ms / n, g_sink->decode_cpu_ms / n);
}

int main(int argc, char** argv) {
    Options opt;
    std::vector<char*> rest;
    rest.push_back(argv[0]);
    int k = 1;
    for (; k < argc; k++) {
        std::string a = argv[k];
        auto next = [&]() -> std::string { return k + 1 < argc ? argv[++k] : ""; };
        if (a == "--") { k++; break; }
        else if (a == "--window") { std::string s = next(); sscanf(s.c_str(), "%dx%d", &opt.window_w, &opt.window_h); }
        else if (a == "--size") { std::string s = next(); sscanf(s.c_str(), "%dx%d", &opt.size_w, &opt.size_h); }
        else if (a == "--offscreen") opt.offscreen = true;
        else if (a == "--unpaced") opt.unpaced = true;
        else if (a == "--serial") opt.serial = true;
        else if (a == "--test") opt.test = next();
        else if (a == "--png") opt.png = next();
        else if (a == "--at") { std::string s = next(); for (char* p = &s[0]; *p;) { opt.at.insert(strtoull(p, &p, 10)); if (*p) p++; } }
        else if (a == "--stop-after") opt.stop_after = strtoull(next().c_str(), nullptr, 10);
        else if (a == "--record") opt.record = next();
        else if (a == "--record-frames") { std::string s = next(); sscanf(s.c_str(), "%llu-%llu", (unsigned long long*)&opt.record_first, (unsigned long long*)&opt.record_last); }
        else { fprintf(stderr, "rta_render: unknown option %s (the runtime's arguments go after --)\n", a.c_str()); return 2; }
    }
    for (; k < argc; k++) rest.push_back(argv[k]);
    if (rest.size() < 2) { fprintf(stderr, "usage: rta_render [--window WxH] [--size WxH] [--offscreen] [--test TEXT] [--unpaced] [--png P --at n,..] "
                                           "[--stop-after N] -- boot|resume <runtime arguments>\n"); return 2; }

    if (opt.offscreen || !opt.test.empty()) qputenv("QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM", "1");   // no Dock icon, never in front
    QSurfaceFormat format;
    format.setVersion(4, 1);
    format.setProfile(QSurfaceFormat::CoreProfile);
    format.setDepthBufferSize(0);
    format.setSwapInterval(opt.unpaced ? 0 : 1);
    QSurfaceFormat::setDefaultFormat(format);
    int qt_argc = 1;
    QGuiApplication app(qt_argc, argv);

    static Screen screen;
    screen.opt = opt;
    screen.create();
    g_screen = &screen;
    // serial: the renderer works in the runtime's VU1 memory (the game stores into it too);
    // pipelined: in its own, kept right by what the sink sends
    static Renderer renderer(opt.serial ? rta::vu1_micro() : nullptr, opt.serial ? rta::vu1_data() : nullptr);
    g_renderer = &renderer;
    renderer.on_frame = [](FrameList& frame) { g_screen->submit(frame); };

    static Sink sink;
    g_sink = &sink;
    sink.serial = opt.serial;
    if (!opt.serial) {
        std::thread decoder([] { sink.decoder_loop(); });
        decoder.detach();
    }
    static Recorder recorder;
    static rta::Hooks hooks;
    hooks.video = &sink;
    if (!opt.record.empty()) {
        recorder.out.open(opt.record.c_str());
        recorder.first_frame = opt.record_first; recorder.last_frame = opt.record_last;
        recorder.next = &sink;
        hooks.video = &recorder;
    }
    static std::vector<char*> run_args = rest;
    std::thread game([] { rta::run((int)run_args.size(), run_args.data(), hooks); });
    game.detach();
    return app.exec();
}
