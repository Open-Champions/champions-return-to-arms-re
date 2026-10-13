// replay_main.cpp - plays a recorded picture stream (stream.h) through the renderer, with
// no game, runtime or disc: pictures to PNG files, timings, and optionally a window.
//
//   rta_replay <stream> [--size WxH] [--png <prefix>] [--at n,n,...] [--loops n]
//              [--no-weave] [--interlace] [--trace] [--target n]
//
// --png writes <prefix>-<blank>.png for the vertical blanks named with --at (default: the
// last one).  Pictures are game output: keep them under local/recomp-out/.
#include "backend_gl.h"
#include "renderer.h"
#include "stream.h"

#include <QGuiApplication>
#include <QImage>
#include <QPainter>
#include <QOffscreenSurface>
#include <QOpenGLContext>
#include <QOpenGLExtraFunctions>
#include <QSurfaceFormat>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <sys/resource.h>
#include <unistd.h>
#include <set>
#include <string>

using namespace render;

static double now_ms() {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

static double cpu_ms() {                                // processor time of the whole process
    rusage u;
    getrusage(RUSAGE_SELF, &u);
    return (u.ru_utime.tv_sec + u.ru_stime.tv_sec) * 1000.0 + (u.ru_utime.tv_usec + u.ru_stime.tv_usec) / 1000.0;
}

int main(int argc, char** argv) {
    qputenv("QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM", "1");   // no Dock icon: nothing is shown
    QSurfaceFormat format;
    format.setVersion(4, 1);
    format.setProfile(QSurfaceFormat::CoreProfile);
    format.setDepthBufferSize(24);
    QSurfaceFormat::setDefaultFormat(format);
    QGuiApplication app(argc, argv);

    std::string path, png;
    int width = 1280, height = 896, loops = 1, read_target = 0;
    std::set<uint64_t> at;
    bool weave = true, interlace = false;
    int trace = 0;
    int crop[4] = {0, 0, 0, 0};                         // --crop x,y,w,h: write only this part of the picture
    std::string translate;                              // --translate-vu <file.cpp>: write the main VU1 program as C++
    bool interpret = false;                             // --interpret: do not use a linked translation
    bool old_translation = false;                       // --old-translation: not the ahead-of-time one (vu1_fast.h), the older one of the main program
    bool reference = false;                             // --reference: VU1 interpreted, and the GS model and UNPACK the long way too
    int list_at = -1;                                   // --list <blank>: print that blank's command list
    unsigned vu_lo = 0, vu_hi = 0;
    int vu_n = 0;
    std::string sheet;                                  // --sheet <file.png> <first id>: the first 48 textures made, from that id on
    int sheet_first = 1;
    // the picture options of the application (docs/issues/native-graphics.md): --aa N, --anisotropy N,
    // --mipmaps, --pack DIR (every frame waits for its pictures), --no-layout
    PictureOptions picture;
    bool layout = true;
    for (int k = 1; k < argc; k++) {
        std::string a = argv[k];
        auto next = [&]() -> std::string { return k + 1 < argc ? argv[++k] : ""; };
        if (a == "--size") { std::string s = next(); sscanf(s.c_str(), "%dx%d", &width, &height); }
        else if (a == "--png") png = next();
        else if (a == "--at") { std::string s = next(); for (char* p = &s[0]; *p;) { at.insert(strtoull(p, &p, 10)); if (*p) p++; } }
        else if (a == "--loops") loops = atoi(next().c_str());
        else if (a == "--no-weave") weave = false;
        else if (a == "--interlace") interlace = true;
        else if (a == "--trace") trace = atoi(next().c_str());
        else if (a == "--vu") { std::string v = next(); sscanf(v.c_str(), "%x-%x:%d", &vu_lo, &vu_hi, &vu_n); }
        else if (a == "--crop") { std::string v = next(); sscanf(v.c_str(), "%d,%d,%d,%d", &crop[0], &crop[1], &crop[2], &crop[3]); }
        else if (a == "--translate-vu") translate = next();
        else if (a == "--interpret") interpret = true;
        else if (a == "--old-translation") old_translation = true;
        else if (a == "--reference") reference = true;
        else if (a == "--list") list_at = atoi(next().c_str());
        else if (a == "--target") read_target = atoi(next().c_str());
        else if (a == "--sheet") { sheet = next(); sheet_first = atoi(next().c_str()); }
        else if (a == "--aa") picture.samples = atoi(next().c_str());
        else if (a == "--anisotropy") picture.anisotropy = atoi(next().c_str());
        else if (a == "--mipmaps") picture.mipmaps = true;
        else if (a == "--pack") { picture.pack = next(); picture.pack_wait = true; }
        else if (a == "--no-layout") layout = false;
        else path = a;
    }
    if (path.empty()) { fprintf(stderr, "usage: rta_replay <stream> [--size WxH] [--png prefix] [--at n,...] [--loops n]\n"); return 2; }

    QOffscreenSurface surface;
    surface.setFormat(format);
    surface.create();
    QOpenGLContext context;
    context.setFormat(format);
    if (!context.create() || !context.makeCurrent(&surface)) { fprintf(stderr, "no OpenGL 4.1 context\n"); return 1; }
    QOpenGLExtraFunctions* gl = context.extraFunctions();
    printf("OpenGL: %s | %s\n", (const char*)gl->glGetString(GL_VERSION), (const char*)gl->glGetString(GL_RENDERER));

    GlBackend backend;
    backend.configure(picture);
    backend.set_output_size(width, height);
    Renderer renderer;
    renderer.gs.name_textures = !picture.pack.empty();
    renderer.gs.layout.enabled = layout;
    renderer.gs.weave = weave;
    renderer.gs.no_interlace = !interlace;
    renderer.gs.trace = trace;
    renderer.vif.vu.use_translation = !interpret;
    renderer.vif.vu.use_fast = !interpret && !old_translation;
    if (reference) { renderer.vif.vu.use_translation = renderer.vif.vu.use_fast = false; renderer.gs.fast_runs = false; renderer.gs.copy_kicks = true; renderer.vif.fast_unpack = false; }
    renderer.vif.time_runs = renderer.gs.time_paths = getenv("RTA_TIME") != nullptr;
    if (getenv("RTA_NO_VU")) renderer.vif.run_programs = false;         // for telling the parts' processor time apart
    if (getenv("RTA_NO_KICK")) renderer.vif.vu.kick = nullptr;
    if (getenv("RTA_DEBUG_STORE")) renderer.vif.vu.debug_store = atoi(getenv("RTA_DEBUG_STORE"));
    if (getenv("RTA_WATCH")) {                          // RTA_WATCH=lo-hi (hex qwords): every VU1 store and UNPACK into the range
        unsigned lo = 0, hi = 0;
        sscanf(getenv("RTA_WATCH"), "%x-%x", &lo, &hi);
        renderer.vif.vu.debug_store_lo = lo; renderer.vif.vu.debug_store_hi = hi; renderer.vif.vu.debug_store = 1 << 30;
        renderer.vif.debug_unpack_lo = lo; renderer.vif.debug_unpack_hi = hi; renderer.vif.debug_unpack = 1 << 30;
    }
    if (getenv("RTA_DEBUG_RING")) renderer.vif.debug_ring = atoi(getenv("RTA_DEBUG_RING"));
    if (getenv("RTA_DEBUG_UNPACK")) renderer.vif.debug_unpack = atoi(getenv("RTA_DEBUG_UNPACK"));
    renderer.vif.vu.debug_lo = vu_lo; renderer.vif.vu.debug_hi = vu_hi; renderer.vif.vu.debug_left = vu_n;
    uint64_t blank = 0, last_blank = 0;
    double decode_ms = 0, draw_ms = 0, mark = 0, decode_cpu = 0, draw_cpu = 0, cpu_mark = 0;
    size_t vertices = 0, commands = 0;
    auto save = [&](uint64_t number) {
        std::vector<uint8_t> rgba;
        int w = 0, h = 0;
        bool ok = read_target ? backend.read_target((uint32_t)read_target, rgba, w, h) : backend.read_shown(rgba, w, h);
        if (!ok) { fprintf(stderr, "blank %llu: nothing shown\n", (unsigned long long)number); return; }
        QImage image(rgba.data(), w, h, w * 4, QImage::Format_RGBA8888);
        std::string name = png + "-" + std::to_string(number) + ".png";
        QImage rgb = image.convertToFormat(QImage::Format_RGB888);
        if (crop[2] > 0) rgb = rgb.copy(crop[0], crop[1], crop[2], crop[3]);
        rgb.save(QString::fromStdString(name));
        printf("wrote %s (%d x %d)\n", name.c_str(), w, h);
    };
    QImage sheet_image(1536, 1152, QImage::Format_RGB888);
    sheet_image.fill(QColor(40, 0, 60));
    int sheet_count = 0;
    renderer.on_frame = [&](FrameList& frame) {
        if (!sheet.empty())
            for (const TextureData& t : frame.textures) {
                if ((int)t.id < sheet_first || sheet_count >= 48) continue;
                QImage image(t.rgba.data(), t.width, t.height, t.width * 4, QImage::Format_RGBA8888);
                QPainter painter(&sheet_image);
                QRect cell((sheet_count % 8) * 192, (sheet_count / 8) * 192, 190, 176);
                painter.drawImage(cell, image.convertToFormat(QImage::Format_RGB888).scaled(190, 176, Qt::KeepAspectRatio));
                painter.setPen(Qt::white);
                painter.drawText(cell.left() + 2, cell.bottom() + 13, QString("%1: %2x%3").arg(t.id).arg(t.width).arg(t.height));
                sheet_count++;
            }
        if ((int)blank == list_at) {
            for (const TargetInfo& t : frame.targets) printf("target %u: %d x %d%s\n", t.id, t.width, t.height, t.screen ? " (screen)" : "");
            printf("shows target %u\n", frame.show_target);
            size_t index = 0;
            for (const DrawCmd& c : frame.commands) {
                if (c.kind == CMD_COPY) { printf("%4zu copy target %u (%d,%d %dx%d) -> target %u (%d,%d)\n", index++, c.texture, c.copy_src[0], c.copy_src[1], c.copy_src[2], c.copy_src[3], c.target, c.copy_dst[0], c.copy_dst[1]); continue; }
                float x0 = 1e9f, y0 = 1e9f, x1 = -1e9f, y1 = -1e9f, z0 = 1e9f, z1 = -1e9f, s0 = 1e9f, s1 = -1e9f, t0 = 1e9f, t1 = -1e9f;
                for (uint32_t k = c.first; k < c.first + c.count; k++) {
                    const Vertex& v = frame.vertices[k];
                    x0 = std::min(x0, v.x); x1 = std::max(x1, v.x); y0 = std::min(y0, v.y); y1 = std::max(y1, v.y);
                    z0 = std::min(z0, v.z); z1 = std::max(z1, v.z);
                    s0 = std::min(s0, v.s / v.q); s1 = std::max(s1, v.s / v.q); t0 = std::min(t0, v.t / v.q); t1 = std::max(t1, v.t / v.q);
                }
                const Vertex& f = frame.vertices[c.first];
                printf("%4zu tgt %u %s n %-5u x %.1f..%.1f y %.1f..%.1f z %.4f..%.4f | tex %s%u %gx%g uv %.2f..%.2f %.2f..%.2f %s tfx %d tcc %d wrap %d%d weave %g | rgba %02x%02x%02x%02x | at %d:%d/%d z %d%s | blend %d:%d%d%d%d fix %02x | sc %d,%d-%d,%d\n",
                       index++, c.target, c.prim == PK_TRIANGLES ? "tri" : c.prim == PK_LINES ? "lin" : "pnt", c.count, x0, x1, y0, y1, z0, z1,
                       c.tex_missing ? "?" : c.tex_is_target ? "T" : "", c.tex_missing ? c.tex_missing - 1 : c.texture, c.tex_size[0], c.tex_size[1], s0 * c.st_scale[0], s1 * c.st_scale[0], t0 * c.st_scale[1], t1 * c.st_scale[1],
                       c.linear ? "lin" : "pt", c.tfx, c.tcc, c.wrap[0], c.wrap[1], c.weave_half, f.r, f.g, f.b, f.a, c.alpha_test, c.atst, c.aref, c.ztst,
                       c.depth_write ? "w" : "", c.blend, c.ba, c.bb, c.bc, c.bd, c.fix, c.scissor[0], c.scissor[1], c.scissor[2], c.scissor[3]);
            }
        }
        double t0 = now_ms(), c0 = cpu_ms();
        decode_ms += t0 - mark;
        decode_cpu += c0 - cpu_mark;
        vertices += frame.vertices.size();
        commands += frame.commands.size();
        backend.execute(frame);
        gl->glFinish();
        draw_ms += now_ms() - t0;
        draw_cpu += cpu_ms() - c0;
        if (!png.empty() && at.count(blank)) save(blank);
        blank++;
        mark = now_ms();
        cpu_mark = cpu_ms();
    };

    std::vector<uint8_t> ram;                           // main memory as the stream gives it
    StreamReader in;
    if (!in.open(path.c_str())) { fprintf(stderr, "cannot read %s\n", path.c_str()); return 1; }
    double start = now_ms();
    for (int loop = 0; loop < loops; loop++) {
        in.rewind_to_start();
        mark = now_ms();
        cpu_mark = cpu_ms();
        while (in.next()) {
            switch (in.kind) {
            case SK_RAM:
                if (ram.empty()) { ram.assign(0x2000000, 0); renderer.set_memory(ram.data(), (uint32_t)ram.size()); }
                if ((uint64_t)in.a + in.words.size() * 4 <= ram.size()) memcpy(ram.data() + in.a, in.words.data(), in.words.size() * 4);
                // the whole of memory has arrived: a resumed machine's VU1 program is loaded now,
                // before the stores the CPU made into VU1 memory are played back over it
                if ((uint64_t)in.a + in.words.size() * 4 == ram.size() && renderer.needs_program())
                    renderer.load_program((const uint32_t*)(ram.data() + 0x3e5ec0), 940 * 4);
                break;
            case SK_VIF1:
                if (renderer.needs_program() && !ram.empty()) renderer.load_program((const uint32_t*)(ram.data() + 0x3e5ec0), 940 * 4);
                renderer.vif1(in.words.data(), in.words.size());
                break;
            case SK_VU1DATA: memcpy(renderer.vif.vu.data + (in.a & 0x3FF) * 16, in.words.data(), std::min<size_t>(in.words.size() * 4, 16)); break;
            case SK_VU1MICRO: memcpy(renderer.vif.vu.micro, in.words.data(), std::min<size_t>(in.words.size() * 4, 0x4000)); renderer.vif.vu.micro_changed(); break;
            case SK_GIF: renderer.gif(in.words.data(), in.words.size()); break;
            case SK_REG: renderer.reg(in.a, in.b); break;
            case SK_VBLANK: renderer.vblank(in.a, in.b); break;
            default: break;
            }
        }
        last_blank = blank;
    }
    double total = now_ms() - start;
    if (!png.empty() && at.empty() && last_blank) save(last_blank - 1);
    if (!sheet.empty()) sheet_image.save(QString::fromStdString(sheet));
    if (!translate.empty()) {
        // the main program is the 1,868 pairs the executable uploads once (instructions 0x000-0x74b)
        bool ok = renderer.vif.vu.write_translation(translate.c_str(), 0x74c);
        printf("%s %s\n", ok ? "wrote" : "cannot write", translate.c_str());
    }
    printf("VU1: %llu runs, %llu of them in the ahead-of-time translation (%llu finished by the interpreter); main program otherwise %s\n",
           (unsigned long long)renderer.vif.vu.runs, (unsigned long long)renderer.vif.vu.fast_runs, (unsigned long long)renderer.vif.vu.fast_left,
           renderer.vif.vu.translated ? "in the older translation" : "interpreted");
    {
        PictureFigures f = backend.figures();
        printf("picture: %d samples, anisotropy %d; pack files %llu, textures named %llu, found %llu, read %llu (%llu as parts), own mip-mapped parts %llu, held %llu pictures, %.1f MB\n",
               f.samples, f.anisotropy, (unsigned long long)f.pack_files, (unsigned long long)f.named, (unsigned long long)f.named_found, (unsigned long long)f.replaced,
               (unsigned long long)f.parts, (unsigned long long)f.own_made, (unsigned long long)f.held, f.held_bytes / 1048576.0);
    }
    const GsStats& s = renderer.gs.stats;
    const Vif1Stats& v = renderer.vif.stats;
    double n = blank ? (double)blank : 1;
    double load[3] = {0, 0, 0};
    getloadavg(load, 3);
    printf("%llu blanks in %.1f ms: %.2f ms each (decode+VU1+GS %.2f, OpenGL %.2f) = %.0f pictures a second at %d x %d\n",
           (unsigned long long)blank, total, total / n, decode_ms / n, draw_ms / n, 1000.0 * n / total, width, height);
    printf("processor time per blank: reading the stream + VIF1 + VU1 + GS model %.2f ms, OpenGL calls %.2f ms; load average %.0f\n", decode_cpu / n, draw_cpu / n, load[0]);
    if (renderer.vif.time_runs)
        printf("of the processor time per blank: VU1 runs with their kicks %.2f ms (the kicks' GS work %.2f ms), GIF channel (uploads) %.2f ms\n",
               renderer.vif.stats.run_ms / n, renderer.gs.stats.kick_ms / n, renderer.gs.stats.path3_ms / n);
    printf("per blank: %.0f vertices, %.0f commands, %.0f VU1 instructions in %.0f runs, %.0f UNPACK, %.0f GS primitives\n",
           vertices / n, commands / n, renderer.vif.vu.instructions / n, renderer.vif.vu.runs / n, v.unpacks / n, s.prims / n);
    printf("GIF packets %llu, register writes %llu, uploads %llu (%.1f MB), textures made %llu, found again %llu, draws without their texture %llu, copies %llu, FINISH %llu\n",
           (unsigned long long)s.packets, (unsigned long long)s.reg_writes, (unsigned long long)s.uploads, s.upload_bytes / 1048576.0,
           (unsigned long long)s.textures_made, (unsigned long long)s.texture_hits, (unsigned long long)s.texture_missing,
           (unsigned long long)s.copies, (unsigned long long)s.finish);
    printf("VIF1: %llu codes, %llu MPG, %llu unknown; VU1 instructions not implemented: %llu; GS registers unknown: %llu\n",
           (unsigned long long)v.codes, (unsigned long long)v.mpg, (unsigned long long)v.unknown, (unsigned long long)renderer.vif.vu.bad,
           (unsigned long long)s.unknown_regs);
    printf("program starts by entry:");
    for (int e = 0; e < 128; e++) if (renderer.vif.entry_counts[e]) printf(" %x:%llu", e, (unsigned long long)renderer.vif.entry_counts[e]);
    printf("\n");
    fflush(stdout);
    _exit(0);                                           // no teardown: nothing to save, and the context's can take long on a busy machine
}
