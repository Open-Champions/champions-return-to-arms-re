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
//   --skeleton-check    (with --scene3d) re-skin every posed packet's bind-pose sources with the frame's skeletons
//                       (rtag_skeletons_get) two ways - the skin matrices, and joint frames x inverse rest as a
//                       Skeleton3D does - and compare with the corners the game's programs drew; figures at the end
//   --unpaced, --offscreen   accepted and ignored (rta_app's options, so that the same wrappers start both)
// After "--": what rta_app takes there ([boot|resume] --opt key=value --fields N ...).
// The exit code is the runtime's (0 done, 3 a script condition timed out, ...).
#include "rtag.h"

#include <chrono>
#include <cmath>
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
    bool skeleton_check = false;
    std::set<uint32_t> dump_ticks;          // --skeleton-dump TICK PREFIX: the skeletons of the first frame at or after TICK as JSON
    std::string dump_prefix;
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
        else if (a == "--skeleton-check") skeleton_check = true;
        else if (a == "--skeleton-dump") { dump_ticks.insert((uint32_t)strtoul(next().c_str(), nullptr, 10)); dump_prefix = next(); skeleton_check = true; }
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
    auto skeletons_get = (int (*)(rtag_skeletons*))dlsym(handle, "rtag_skeletons_get");
    struct SkelFigures { unsigned long long frames = 0, skeletons = 0, corners = 0, over_001 = 0, over_01 = 0; double worst_skin = 0, worst_joint = 0, sum_skin = 0;
                         double bone_worst = 0; unsigned long long bones = 0; std::set<uint32_t> states, clips; } sk;
    for (;;) {
        const rtag_frame* frame = nullptr;
        (void)0;
        int got = paced ? api.rtag_poll(-1, &frame) : api.rtag_step(nullptr, -1, &frame);
        if (got < 0) break;
        if (got == 0) continue;
        frames++;
        vertices += frame->vertex_count; draws += frame->draw_count; textures += frame->texture_count;
        if (frame->scene && frame->scene->valid) { scene_frames++; scene_vertices += frame->scene->vertex_count; scene_pieces += frame->scene->piece_count; }
        rtag_skeletons skel;
        memset(&skel, 0, sizeof skel);
        skel.struct_size = sizeof skel;
        if (skeleton_check && skeletons_get && frame->scene && frame->scene->valid && skeletons_get(&skel) && skel.piece_count == frame->scene->piece_count) {
            const rtag_scene* sc = frame->scene;
            sk.frames++;
            if (getenv("RTA_SKEL_TRACE") && frame->sim_tick % 50 == 0) {
                unsigned posed = 0, models = 0;
                for (uint32_t k = 0; k < sc->piece_count; k++) if (sc->pieces[k].kind == 2) { models++; if (skel.pieces[k].skeleton >= 0) posed++; }
                fprintf(stderr, "skel-trace: tick %u skeletons %u (poses seen %u) model pieces %u posed %u\n", frame->sim_tick, skel.skeleton_count, skel.poses_seen, models, posed);
            }
            if (!dump_ticks.empty() && frame->sim_tick >= *dump_ticks.begin()) {
                const uint32_t tick = *dump_ticks.begin();
                dump_ticks.erase(dump_ticks.begin());
                std::string path = dump_prefix + "-" + std::to_string(tick) + ".json";
                if (FILE* o = fopen(path.c_str(), "w")) {
                    fprintf(o, "{\"tick\": %u, \"player\": [%.4f, %.4f, %.4f], \"skeletons\": [", frame->sim_tick, frame->view.player[0], frame->view.player[1], frame->view.player[2]);
                    for (uint32_t k = 0; k < skel.skeleton_count; k++) {
                        const rtag_skeleton& s = skel.skeletons[k];
                        fprintf(o, "%s\n {\"object\": %u, \"pose\": %u, \"state\": %u, \"clip\": %u, \"joints\": %d, \"scale\": %.5f, \"parent\": [", k ? "," : "", s.object, s.pose, s.state, s.clip, s.joint_count, s.scale);
                        for (int j = 0; j < s.joint_count; j++) fprintf(o, "%s%d", j ? ", " : "", s.parent[j]);
                        fprintf(o, "], \"bind\": [");
                        for (int j = 0; j < s.joint_count; j++) fprintf(o, "%s[%.4f, %.4f, %.4f]", j ? ", " : "", s.bind[j][0], s.bind[j][1], s.bind[j][2]);
                        fprintf(o, "], \"joint\": [");
                        for (int j = 0; j < s.joint_count; j++) {
                            fprintf(o, "%s[", j ? ", " : "");
                            for (int c = 0; c < 12; c++) fprintf(o, "%s%.5f", c ? ", " : "", s.joint[j][c]);
                            fprintf(o, "]");
                        }
                        fprintf(o, "]}");
                    }
                    fprintf(o, "],\n \"pieces\": [");
                    bool first = true;
                    for (uint32_t k = 0; k < sc->piece_count; k++) {
                        if (sc->pieces[k].kind != 2) continue;
                        const rtag_skin_piece& sp = skel.pieces[k];
                        fprintf(o, "%s\n {\"object\": %u, \"skeleton\": %d, \"flags\": %u, \"sources\": %u, \"corners\": %u, \"slot0\": [", first ? "" : ",", sc->pieces[k].object, sp.skeleton,
                                sc->pieces[k].flags, sp.source_count, sc->pieces[k].full_count);
                        for (int c = 0; c < 12; c++) fprintf(o, "%s%.4f", c ? ", " : "", sp.slot0[c]);
                        fprintf(o, "], \"weights\": [");
                        for (uint32_t v = 0; v < sp.source_count; v++) {
                            const rtag_skin_source& q = skel.sources[sp.source_first + v];
                            fprintf(o, "%s[%.3f, %.3f, %.3f, %u, %u]", v ? ", " : "", q.position[0], q.position[1], q.position[2], q.joint[0], q.weight[0]);
                        }
                        fprintf(o, "]}");
                        first = false;
                    }
                    fprintf(o, "]}\n");
                    fclose(o);
                }
            }
            sk.skeletons += skel.skeleton_count;
            for (uint32_t k = 0; k < skel.skeleton_count; k++) {
                const rtag_skeleton& s = skel.skeletons[k];
                sk.states.insert(s.state); sk.clips.insert(s.clip);
                // a bone's length in the pose against the rest (joints keep their offset from the parent unless the clip moves them)
                for (int j = 1; j < s.joint_count; j++) {
                    int p = s.parent[j];
                    if (p < 0 || s.scale <= 0) continue;
                    double a = 0, b = 0;
                    for (int c = 0; c < 3; c++) { double d = s.joint[j][c * 4 + 3] - s.joint[p][c * 4 + 3], e = s.bind[j][c] - s.bind[p][c]; a += d * d; b += e * e; }
                    if (b < 1.0) continue;
                    double ratio = std::sqrt(a) / s.scale / std::sqrt(b);
                    sk.bones++;
                    sk.bone_worst = std::max(sk.bone_worst, std::fabs(ratio - 1.0));
                }
            }
            for (uint32_t k = 0; k < sc->piece_count; k++) {
                const rtag_skin_piece& sp = skel.pieces[k];
                const rtag_scene_piece& piece = sc->pieces[k];
                if (sp.skeleton < 0 || piece.kind != 2) continue;
                const rtag_skeleton& s = skel.skeletons[sp.skeleton];
                if (s.joint_count < 1) continue;
                for (uint32_t n = 0; n < piece.full_count; n++) {
                    const uint32_t at = piece.full_first + n;
                    const rtag_scene_full& drawn = sc->full[at];
                    const rtag_skin_source& src = skel.sources[sp.source_first + skel.full_source[at]];
                    double a[3] = {0, 0, 0}, b[3] = {0, 0, 0};
                    for (int i = 0; i < 4; i++) {
                        if (!src.weight[i]) continue;
                        const double w = src.weight[i] / 255.0;
                        const int j = src.joint[i];
                        const float* m = s.skin[j];
                        const float* g = s.joint[j];
                        // Skeleton3D: global pose x inverse rest, the rest being T(bind[j]): p -> G (p - bind[j])
                        double q[3] = {src.position[0] - s.bind[j][0], src.position[1] - s.bind[j][1], src.position[2] - s.bind[j][2]};
                        for (int c = 0; c < 3; c++) {
                            a[c] += w * (m[c * 4] * src.position[0] + m[c * 4 + 1] * src.position[1] + m[c * 4 + 2] * src.position[2] + m[c * 4 + 3]);
                            b[c] += w * (g[c * 4] * q[0] + g[c * 4 + 1] * q[1] + g[c * 4 + 2] * q[2] + g[c * 4 + 3]);
                        }
                    }
                    double ea = 0, eb = 0;
                    const float d[3] = {drawn.x, drawn.y, drawn.z};
                    for (int c = 0; c < 3; c++) { ea = std::max(ea, std::fabs(a[c] - d[c])); eb = std::max(eb, std::fabs(b[c] - d[c])); }
                    sk.corners++; sk.sum_skin += ea;
                    sk.worst_skin = std::max(sk.worst_skin, ea); sk.worst_joint = std::max(sk.worst_joint, eb);
                    if (std::max(ea, eb) > 0.01) sk.over_001++;
                    if (std::max(ea, eb) > 0.1) sk.over_01++;
                }
            }
        }
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
    if (skeleton_check)
        printf("rtag_host: skeletons: %llu frames, %llu skeletons (%zu animation states, %zu clips); %llu drawn corners of posed packets re-skinned from their bind-pose "
               "sources: through the skin matrices largest difference %.5f (mean %.6f) world units, through joint frames x inverse rest %.5f; over 0.01: %llu, over 0.1: %llu; "
               "%llu bones measured, largest change of length against the rest %.4f\n", sk.frames, sk.skeletons, sk.states.size(), sk.clips.size(), sk.corners,
               sk.worst_skin, sk.corners ? sk.sum_skin / sk.corners : 0.0, sk.worst_joint, sk.over_001, sk.over_01, sk.bones, sk.bone_worst);
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
