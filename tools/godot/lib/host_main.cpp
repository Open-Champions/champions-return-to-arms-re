// host_main.cpp - rtag_host: the smallest host of the game library (rtag.h).  No window, no
// Godot: it loads the library, starts the machine and takes its frames - to run scripts,
// write pictures at chosen ticks ("app shot FILE.png" lines of a script), compare a
// session tick for tick with the original, and time the library by itself.
//
//   rtag_host [--lib FILE] --disc IMAGE [options] [-- <arguments for the runtime>]
//
//   --lib FILE          the library (default: librta_game.dylib beside this program, else in ../lib)
//   --disc IMAGE        your disc image (or $RTA_DISC), read in place
//   --data DIR          memory cards (default: host-data beside this program)
//   --workspace DIR     where SLUS_209.73, names.tsv and symbols/ are (default: three directories up, if it has them)
//   --script FILE       a script in the rig's language
//   --size WxH          the library's own renderer draws off screen at this size (default 640x448); --no-picture: it does not run
//   --samples N --anisotropy N --mipmaps   of that renderer (default: none, the plain picture)
//   --aspect W:H        the shape of the 3-D view (default 4:3)
//   --every-frame       read the picture back every frame (default: only for "app shot")
//   --lists             take the draw lists as a host that draws them would (counted, not drawn)
//   --scene3d           with the 3-D scene tap
//   --list-stats        (with --lists) what the lists use: how a frame is laid out over its surfaces, and every
//                       combination of blend, depth, alpha test, texture function and wrap with its number of draws
//   --list-frames A,B   ... and the layout of these frames (vertical blank numbers) in full
//   --sound none|machine|pull   (default machine; pull: this program asks for 10 ms every 10 ms and throws it away)
//   --paced             the library's own clock at 59.94 instead of as fast as it goes
//   --view NAME         the camera view (overhead, action, chase, shoulder, first); scripts: app view NAME
//   --no-game-hud       the game's own HUD layer is left out; scripts: app gamehud off|on
//   --stop-after N      end after N vertical blanks
//   --unpaced, --offscreen   accepted and ignored (rta_app's options, so that the same wrappers start both)
// After "--": what rta_app takes there ([boot|resume] --opt key=value --fields N ...).
// The exit code is the runtime's (0 done, 3 a script condition timed out, ...).
#include "rtag.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <map>
#include <set>
#include <libgen.h>
#include <mach-o/dyld.h>
#include <string>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>
#include <vector>

#define RTAG_FUNCTIONS(F) \
    F(rtag_api_version) F(rtag_start) F(rtag_step) F(rtag_poll) F(rtag_run) F(rtag_audio_pull) F(rtag_info) F(rtag_ended) \
    F(rtag_exit_code) F(rtag_stop) F(rtag_has) F(rtag_set_pad) F(rtag_set_option)
struct Api {
#define RTAG_MEMBER(name) decltype(&::name) name = nullptr;
    RTAG_FUNCTIONS(RTAG_MEMBER)
#undef RTAG_MEMBER
};

static bool file_exists(const std::string& path) { struct stat st; return stat(path.c_str(), &st) == 0; }

int main(int argc, char** argv) {
    char self[4096];
    uint32_t self_size = sizeof self;
    std::string here = ".";
    if (_NSGetExecutablePath(self, &self_size) == 0) { char real[4096]; if (realpath(self, real)) here = dirname(real); }
    std::string lib, disc = getenv("RTA_DISC") ? getenv("RTA_DISC") : "", data = here + "/host-data", workspace, script, sound = "machine";
    int width = 640, height = 448, samples = 0, anisotropy = 1, mipmaps = 0, every = 0, lists = 0, scene3d = 0;
    double aspect = 0;
    bool paced = false, stats = false, no_hud = false;
    std::string view;
    std::set<unsigned long long> stat_frames;
    std::map<std::string, unsigned long long> combos, layouts;
    unsigned long long stop_after = 0;
    std::vector<const char*> pass;
    int k = 1;
    for (; k < argc; k++) {
        std::string a = argv[k];
        auto next = [&]() -> std::string { return k + 1 < argc ? argv[++k] : ""; };
        if (a == "--") { k++; break; }
        else if (a == "--lib") lib = next();
        else if (a == "--disc") disc = next();
        else if (a == "--data") data = next();
        else if (a == "--workspace") workspace = next();
        else if (a == "--script") script = next();
        else if (a == "--size") { std::string s = next(); sscanf(s.c_str(), "%dx%d", &width, &height); }
        else if (a == "--no-picture") width = height = 0;
        else if (a == "--samples") samples = atoi(next().c_str());
        else if (a == "--anisotropy") anisotropy = atoi(next().c_str());
        else if (a == "--mipmaps") mipmaps = 1;
        else if (a == "--aspect") { std::string s = next(); double w = 0, h = 0; if (sscanf(s.c_str(), "%lf:%lf", &w, &h) == 2 && h > 0) aspect = w / h; }
        else if (a == "--every-frame") every = 1;
        else if (a == "--lists") lists = 1;
        else if (a == "--scene3d") { scene3d = 1; lists = 1; }
        else if (a == "--list-stats") { stats = true; lists = 1; }
        else if (a == "--list-frames") { std::string t = next(); for (char* q = &t[0]; *q;) { stat_frames.insert(strtoull(q, &q, 10)); if (*q) q++; } stats = true; lists = 1; }
        else if (a == "--sound") sound = next();
        else if (a == "--paced") paced = true;
        else if (a == "--view") view = next();
        else if (a == "--no-game-hud") no_hud = true;
        else if (a == "--stop-after") stop_after = strtoull(next().c_str(), nullptr, 10);
        else if (a == "--unpaced" || a == "--offscreen" || a == "--plain") {}
        else { fprintf(stderr, "rtag_host: unknown option %s (the head of tools/godot/lib/host_main.cpp lists them)\n", a.c_str()); return 2; }
    }
    for (; k < argc; k++) pass.push_back(argv[k]);
    if (lib.empty()) lib = file_exists(here + "/librta_game.dylib") ? here + "/librta_game.dylib" : here + "/../lib/librta_game.dylib";
    if (workspace.empty() && file_exists(here + "/../../../names.tsv")) workspace = here + "/../../..";

    void* handle = dlopen(lib.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!handle) { fprintf(stderr, "rtag_host: cannot load %s: %s\n", lib.c_str(), dlerror()); return 2; }
    Api api;
#define RTAG_LOAD(name) api.name = (decltype(api.name))dlsym(handle, #name); if (!api.name) { fprintf(stderr, "rtag_host: %s has no %s\n", lib.c_str(), #name); return 2; }
    RTAG_FUNCTIONS(RTAG_LOAD)
#undef RTAG_LOAD
    if (api.rtag_api_version() != RTAG_API_VERSION) { fprintf(stderr, "rtag_host: the library speaks version %d of the interface, this program %d\n", api.rtag_api_version(), RTAG_API_VERSION); return 2; }

    rtag_config config;
    memset(&config, 0, sizeof config);
    config.struct_size = sizeof config;
    config.disc = disc.c_str();
    config.data_dir = data.c_str();
    config.workspace = workspace.empty() ? nullptr : workspace.c_str();
    config.script = script.empty() ? nullptr : script.c_str();
    config.lists = lists;
    config.picture_width = width; config.picture_height = height;
    config.picture_every_frame = every;
    config.samples = samples; config.anisotropy = anisotropy; config.mipmaps = mipmaps;
    config.aspect = aspect;
    config.scene3d = scene3d;
    config.sound = sound == "none" ? RTAG_SOUND_NONE : sound == "pull" ? RTAG_SOUND_PULL : RTAG_SOUND_MACHINE;
    config.gain = 0;
    config.films = 1;
    config.view = view.empty() ? nullptr : view.c_str();
    config.argc = (int)pass.size();
    config.argv = pass.data();
    int started = api.rtag_start(&config);
    if (started != 0) {
        fprintf(stderr, "rtag_host: the machine did not start (%d)%s\n", started, started == -2 ? ": give your disc image with --disc or RTA_DISC" : "");
        return 2;
    }
    fprintf(stderr, "rtag_host: library %s (interface %d; fix set %s, films %s)\n", lib.c_str(), api.rtag_api_version(), api.rtag_has("fixes") ? "applied" : "not applied",
            api.rtag_has("films") ? "linked" : "not linked");
    bool pulling = true;
    std::thread puller;
    if (config.sound == RTAG_SOUND_PULL)
        puller = std::thread([&] {
            std::vector<int16_t> buffer(480 * 2);
            auto nextt = std::chrono::steady_clock::now();
            while (pulling) {
                nextt += std::chrono::milliseconds(10);
                std::this_thread::sleep_until(nextt);
                api.rtag_audio_pull(buffer.data(), 480);
            }
        });
    if (no_hud) api.rtag_set_option("game_hud", "off");
    if (paced) api.rtag_run(59.94);
    unsigned long long frames = 0, vertices = 0, draws = 0, textures = 0, scene_vertices = 0, scene_frames = 0, scene_pieces = 0;
    for (;;) {
        const rtag_frame* frame = nullptr;
        int got = paced ? api.rtag_poll(-1, &frame) : api.rtag_step(nullptr, -1, &frame);
        if (got < 0) break;
        if (got == 0) continue;
        frames++;
        vertices += frame->vertex_count; draws += frame->draw_count; textures += frame->texture_count;
        if (frame->scene && frame->scene->valid) { scene_frames++; scene_vertices += frame->scene->vertex_count; scene_pieces += frame->scene->piece_count; }
        if (stats && frame->draw_count) {
            // the layout: runs of consecutive draws into one surface, with what they read
            std::string layout;
            bool full = stat_frames.count(frame->number) != 0;
            if (full) {
                fprintf(stderr, "frame %llu (tick %u): shows surface %u rect %d %d %d %d aspect %.3f; %u draws, %u vertices\n", (unsigned long long)frame->number, frame->sim_tick,
                        frame->show_target, frame->show_rect[0], frame->show_rect[1], frame->show_rect[2], frame->show_rect[3], frame->aspect, frame->draw_count, frame->vertex_count);
                for (uint32_t t = 0; t < frame->target_count; t++)
                    fprintf(stderr, "  new surface %u: %d x %d%s\n", frame->targets[t].id, frame->targets[t].width, frame->targets[t].height, frame->targets[t].screen ? " (screen)" : "");
            }
            for (uint32_t d = 0; d < frame->draw_count;) {
                uint32_t e = d;
                std::set<uint32_t> reads;
                unsigned copies = 0, by[3] = {0, 0, 0}, verts = 0;
                while (e < frame->draw_count && frame->draws[e].target == frame->draws[d].target) {
                    const rtag_draw& c = frame->draws[e];
                    if (c.kind == RTAG_COPY) { copies++; reads.insert(c.texture); }
                    else { if (c.texture && c.tex_is_target) reads.insert(c.texture); by[c.made_by < 3 ? c.made_by : 2]++; verts += c.count; }
                    e++;
                }
                char text[256];
                int n = snprintf(text, sizeof text, "[s%u:", frame->draws[d].target);
                for (uint32_t r : reads) n += snprintf(text + n, sizeof text - n, " reads s%u", r);
                if (copies) n += snprintf(text + n, sizeof text - n, " %u copies", copies);
                snprintf(text + n, sizeof text - n, "]");
                layout += text;
                if (full) fprintf(stderr, "  run of %u draws into surface %u (%u VU1, %u CPU, %u sprite draws; %u vertices)%s\n", e - d, frame->draws[d].target, by[0], by[1], by[2], verts, text);
                d = e;
            }
            layouts[layout]++;
            for (uint32_t d = 0; d < frame->draw_count; d++) {
                const rtag_draw& c = frame->draws[d];
                if (c.kind != RTAG_DRAW) { combos["copy"]++; continue; }
                char text[256];
                snprintf(text, sizeof text, "blend %s", c.blend ? "" : "off");
                std::string key = text;
                if (c.blend) { snprintf(text, sizeof text, "(%c-%c)*%s+%c", "sd0"[c.ba % 3], "sd0"[c.bb % 3], c.bc == 0 ? "As" : c.bc == 1 ? "Ad" : "FIX", "sd0"[c.bd % 3]); key += text; }
                snprintf(text, sizeof text, " | depth %s%s", !c.depth_test ? "off" : c.ztst == 0 ? "never" : c.ztst == 1 ? "always" : c.ztst == 2 ? ">=" : ">", c.depth_write ? "+write" : "");
                combos[key + text]++;
                snprintf(text, sizeof text, "alpha test %s afail %d", !c.alpha_test ? "off" : c.atst == 0 ? "never" : c.atst == 1 ? "always" : c.atst == 2 ? "<" : c.atst == 3 ? "<=" : c.atst == 4 ? "==" : c.atst == 5 ? ">=" : c.atst == 6 ? ">" : "!=", c.alpha_test ? c.afail : 0);
                combos[text]++;
                snprintf(text, sizeof text, "texture %s tfx %d tcc %d %s wrap %d %d%s%s%s", !c.texture ? "none" : c.tex_is_target ? "surface" : "texture", c.tfx, c.tcc, c.linear ? "linear" : "nearest",
                         c.wrap_s, c.wrap_t, c.weave_half != 0 ? " weave" : "", c.texa_mode ? " texa" : "", c.fog ? " fog" : "");
                combos[c.texture ? text : "texture none"]++;
                if (c.texture && c.tex_is_target) {
                    snprintf(text, sizeof text, "reads a surface: into s%u, made_by %d, %s, depth %s%s, scene %s", c.target, c.made_by, key.c_str(),
                             c.ztst == 0 ? "never" : c.ztst == 1 ? "always" : c.ztst == 2 ? ">=" : ">", c.depth_write ? "+write" : "", c.scene_first >= 0 ? "world" : "flat");
                    combos[text]++;
                }
                snprintf(text, sizeof text, "prim %d made_by %d mask rgb %d a %d%s", c.prim, c.made_by, c.mask_rgb, c.mask_a, c.scissor_moved ? " scissor moved" : "");
                combos[text]++;
            }
        }
        if (stop_after && frames >= stop_after) { api.rtag_stop(); break; }
    }
    pulling = false;
    if (puller.joinable()) puller.join();
    fprintf(stderr, "rtag_host: %llu frames taken; in the lists %llu vertices, %llu draws, %llu textures; scene: %llu frames with a camera, %llu vertices, %llu mesh packets\n", frames, vertices,
            draws, textures, scene_frames, scene_vertices, scene_pieces);
    if (stats) {
        fprintf(stderr, "rtag_host: frame layouts (runs of draws per surface, in order), by number of frames:\n");
        for (auto& kv : layouts) fprintf(stderr, "  %8llu  %s\n", kv.second, kv.first.c_str());
        fprintf(stderr, "rtag_host: state combinations, by number of draws:\n");
        for (auto& kv : combos) fprintf(stderr, "  %8llu  %s\n", kv.second, kv.first.c_str());
    }
    fprintf(stderr, "rtag_host: %s\n", api.rtag_info());
    fflush(stderr);
    fflush(stdout);
    _exit(api.rtag_exit_code());
}
