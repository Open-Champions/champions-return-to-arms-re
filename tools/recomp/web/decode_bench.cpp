// decode_bench.cpp - the renderer's CPU side alone (VIF1, VU1, the GS model: everything
// above render/backend.h), played from a recorded picture stream (render/stream.h), with
// no game, no runtime and no graphics API.  The same file is built for the Mac and for
// node, so that the cost of this code as WebAssembly can be told from its cost natively:
//
//   clang++ -std=c++17 -O2 -fno-strict-aliasing -ffp-contract=off -frounding-math -I tools/recomp/render \
//       tools/recomp/web/decode_bench.cpp tools/recomp/render/{vu1,vif1,gs,renderer}.cpp <vu1_translated.cpp | vu1_none.cpp> \
//       <vu1_fast.cpp | vu1_fast_none.cpp> -o decode_bench        (tools/recomp/render/speedbench.py does it)
//   em++ (the same, without -frounding-math) -sNODERAWFS=1 -sINITIAL_MEMORY=1024MB -o decode_bench.js
//
//   decode_bench <stream> [--loops N] [--interpret] [--no-vu] [--no-kick] [--times]
//                [--dump FILE | --compare FILE]
//
// --dump writes the vertices of the first pass (what a backend would be handed) to a file
// under local/; --compare reads such a file and says how far this build's vertices are
// from it: how one arithmetic differs from another in the picture, in numbers.
//
// The stream is read into memory first; the first pass (textures decoded, tables filled)
// is timed apart from the rest.  A recording is derived from the game: it stays under local/.
#include "prof.h"
#include "renderer.h"
#include "stream.h"

#ifdef __APPLE__
#include <libproc.h>
#include <unistd.h>
// instructions retired and processor cycles of this process so far (they do not move with
// the machine's load the way times do)
static void counters(uint64_t& instructions, uint64_t& cycles) {
    rusage_info_v4 info;
    if (proc_pid_rusage(getpid(), RUSAGE_INFO_V4, (rusage_info_t*)&info) != 0) { instructions = cycles = 0; return; }
    instructions = info.ri_instructions; cycles = info.ri_cycles;
}
#else
static void counters(uint64_t& instructions, uint64_t& cycles) { instructions = cycles = 0; }
#endif

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

using namespace render;

static double now_ms() {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

struct Record { uint32_t kind, a; uint64_t b; size_t offset, count; };

// A draw command folded into a figure, field by field (the structure has padding).
static uint64_t fold_command(uint64_t h, const DrawCmd& c) {
    auto word = [&](uint64_t x) { h = (h ^ x) * 0x100000001B3ull; };
    auto real = [&](float f) { uint32_t u; memcpy(&u, &f, 4); word(u); };
    word(c.kind); word(c.prim); word(c.first); word(c.count); word(c.target);
    for (int v : c.scissor) word((uint32_t)v);
    word(c.scissor_moved); real(c.scissor_x[0]); real(c.scissor_x[1]);
    word(c.texture); word(c.tex_is_target); real(c.tex_size[0]); real(c.tex_size[1]); real(c.tex_offset[0]); real(c.tex_offset[1]);
    word(c.tex_missing); real(c.st_scale[0]); real(c.st_scale[1]); word(c.linear); word(c.wrap[0]); word(c.wrap[1]);
    for (float v : c.region) real(v);
    word(c.texa_mode); word(c.ta0); word(c.ta1); word(c.aem); word(c.tfx); word(c.tcc); real(c.weave_half); real(c.weave_base);
    word(c.alpha_test); word(c.atst); word(c.aref); word(c.afail); word(c.depth_test); word(c.ztst); word(c.depth_write);
    word(c.blend); word(c.ba); word(c.bb); word(c.bc); word(c.bd); word(c.fix); word(c.mask_rgb); word(c.mask_a); word(c.made_by);
    word(c.fog); word(c.fog_colour[0]); word(c.fog_colour[1]); word(c.fog_colour[2]);
    for (int v : c.copy_src) word((uint32_t)v);
    for (int v : c.copy_dst) word((uint32_t)v);
    return h;
}

int main(int argc, char** argv) {
    std::string path;
    int loops = 20;
    bool interpret = false, no_vu = false, no_kick = false, times = false, old_translation = false, check = true;
    std::string dump, compare, list;
    FILE* list_file = nullptr;
    for (int k = 1; k < argc; k++) {
        std::string a = argv[k];
        if (a == "--loops" && k + 1 < argc) loops = atoi(argv[++k]);
        else if (a == "--interpret") interpret = true;
        else if (a == "--old-translation") old_translation = true;      // not the ahead-of-time translation: the older one of the main program
        else if (a == "--no-check") check = false;
        else if (a == "--list" && k + 1 < argc) list = argv[++k];       // the first pass's draw commands as text (derived from the game: under local/)                      // no checksum of the lists: the bench's own cost is smaller
        else if (a == "--no-vu") no_vu = true;
        else if (a == "--no-kick") no_kick = true;
        else if (a == "--times") times = true;
        else if (a == "--dump" && k + 1 < argc) dump = argv[++k];
        else if (a == "--compare" && k + 1 < argc) compare = argv[++k];
        else path = a;
    }
    StreamReader in;
    if (path.empty() || !in.open(path.c_str())) { fprintf(stderr, "decode_bench <stream> [--loops N] [--interpret] [--no-vu] [--no-kick] [--times]\n"); return 1; }
    std::vector<Record> records;
    std::vector<uint32_t> words;
    while (in.next()) {
        records.push_back({in.kind, in.a, in.b, words.size(), in.words.size()});
        words.insert(words.end(), in.words.begin(), in.words.end());
    }
    in.close();

    static Renderer renderer;
    renderer.vif.vu.use_translation = !interpret;
    renderer.vif.vu.use_fast = !interpret && !old_translation;
    renderer.vif.time_runs = renderer.gs.time_paths = times;
    if (no_vu) renderer.vif.run_programs = false;
    if (no_kick) renderer.vif.vu.kick = nullptr;
    uint64_t blanks = 0, vertices = 0, commands = 0, checksum = 0, command_checksum = 0;
    std::vector<Vertex> kept;                           // the first pass's vertices, with a count per blank
    std::vector<uint32_t> kept_counts;
    bool keeping = !dump.empty() || !compare.empty();
    renderer.on_frame = [&](FrameList& frame) {
        if (keeping) { kept.insert(kept.end(), frame.vertices.begin(), frame.vertices.end()); kept_counts.push_back((uint32_t)frame.vertices.size()); }
        vertices += frame.vertices.size();
        commands += frame.commands.size();
        // what a backend would be handed, folded into one number: two builds that print the
        // same one made the same lists
        if (list_file) {
            fprintf(list_file, "blank %llu: %zu vertices, %zu commands, %zu textures, %zu targets, shows %u\n", (unsigned long long)blanks, frame.vertices.size(),
                    frame.commands.size(), frame.textures.size(), frame.targets.size(), frame.show_target);
            for (const DrawCmd& c : frame.commands)
                fprintf(list_file, "  %d %d first %u count %u tgt %u sc %d,%d,%d,%d%s tex %u%s %gx%g off %g,%g miss %u st %g,%g lin %d wrap %d%d tfx %d tcc %d weave %g at %d:%d/%d/%d z %d:%d%s bl %d:%d%d%d%d %02x mask %d%d by %d fog %d\n",
                        c.kind, c.prim, c.first, c.count, c.target, c.scissor[0], c.scissor[1], c.scissor[2], c.scissor[3], c.scissor_moved ? "m" : "", c.texture, c.tex_is_target ? "T" : "",
                        c.tex_size[0], c.tex_size[1], c.tex_offset[0], c.tex_offset[1], c.tex_missing, c.st_scale[0], c.st_scale[1], c.linear, c.wrap[0], c.wrap[1], c.tfx, c.tcc, c.weave_half,
                        c.alpha_test, c.atst, c.aref, c.afail, c.depth_test, c.ztst, c.depth_write ? "w" : "", c.blend, c.ba, c.bb, c.bc, c.bd, c.fix, c.mask_rgb, c.mask_a, c.made_by, c.fog);
        }
        if (check) {
            for (const Vertex& v : frame.vertices) { uint32_t w[7]; memcpy(w, &v, 28); for (uint32_t x : w) checksum = (checksum ^ x) * 0x100000001B3ull; }
            // the draw commands too (their state and vertex ranges), into a figure of their own
            for (const DrawCmd& c : frame.commands) command_checksum = fold_command(command_checksum, c);
        }
        blanks++;
    };
    std::vector<uint8_t> ram;
    if (!list.empty()) list_file = fopen(list.c_str(), "w");
    double first_ms = 0, rest_ms = 0;
    uint64_t first_blanks = 0, first_checksum = 0, first_command_checksum = 0;
    uint64_t i0 = 0, c0 = 0, i1 = 0, c1 = 0;
    prof::calibrate();
    for (int loop = 0; loop < loops; loop++) {
        if (loop == 1) { counters(i0, c0); prof::start(); }
        double t0 = now_ms();
        for (const Record& r : records) {
            const uint32_t* w = words.data() + r.offset;
            switch (r.kind) {
            case SK_RAM:
                if (ram.empty()) { ram.assign(0x2000000, 0); renderer.set_memory(ram.data(), (uint32_t)ram.size()); }
                if ((uint64_t)r.a + r.count * 4 <= ram.size()) memcpy(ram.data() + r.a, w, r.count * 4);
                if ((uint64_t)r.a + r.count * 4 == ram.size() && renderer.needs_program()) renderer.load_program((const uint32_t*)(ram.data() + 0x3e5ec0), 940 * 4);
                break;
            case SK_VIF1:
                if (renderer.needs_program() && !ram.empty()) renderer.load_program((const uint32_t*)(ram.data() + 0x3e5ec0), 940 * 4);
                renderer.vif1(w, r.count);
                break;
            case SK_VU1DATA: memcpy(renderer.vif.vu.data + (r.a & 0x3FF) * 16, w, r.count * 4 < 16 ? r.count * 4 : 16); break;
            case SK_VU1MICRO: memcpy(renderer.vif.vu.micro, w, r.count * 4 < 0x4000 ? r.count * 4 : 0x4000); renderer.vif.vu.micro_changed(); break;
            case SK_GIF: renderer.gif(w, r.count); break;
            case SK_REG: renderer.reg(r.a, r.b); break;
            case SK_VBLANK: renderer.vblank(r.a, r.b); break;
            default: break;
            }
        }
        double took = now_ms() - t0;
        if (loop == 0) { first_ms = took; first_blanks = blanks; first_checksum = checksum; first_command_checksum = command_checksum; keeping = false; if (list_file) { fclose(list_file); list_file = nullptr; } } else rest_ms += took;
    }
    prof::stop();
    counters(i1, c1);
    double n = blanks > first_blanks ? (double)(blanks - first_blanks) : 1;
    printf("VU1: %llu runs, %llu of them in the ahead-of-time translation (%llu finished by the interpreter); main program otherwise %s\n",
           (unsigned long long)renderer.vif.vu.runs, (unsigned long long)renderer.vif.vu.fast_runs, (unsigned long long)renderer.vif.vu.fast_left,
           renderer.vif.vu.translated ? "in the older translation" : "interpreted");
    printf("first pass: %llu blanks in %.1f ms (%.2f ms each), list checksum %016llx\n", (unsigned long long)first_blanks, first_ms,
           first_ms / (first_blanks ? first_blanks : 1), (unsigned long long)first_checksum);
    // (the figure of all passes says the same of the later ones: the lists of a pass depend on what the passes before left)
    printf("draw commands of the first pass: checksum %016llx; all passes: vertices %016llx, commands %016llx\n", (unsigned long long)first_command_checksum,
           (unsigned long long)checksum, (unsigned long long)command_checksum);
    printf("then %d passes: %.0f blanks, %.3f ms each of wall time; per blank %.0f vertices, %.0f commands, %.0f VU1 instruction pairs in %.0f runs\n",
           loops - 1, n, rest_ms / n, vertices / (double)blanks, commands / (double)blanks, renderer.vif.vu.instructions / (double)blanks, renderer.vif.vu.runs / (double)blanks);
    if (i1 > i0 && loops > 1) {
        double load[3] = {0, 0, 0};
#ifdef __APPLE__
        getloadavg(load, 3);
#endif
        printf("per blank after the first pass: %.2f million instructions, %.2f million cycles (whole process, the bench's own reading and checksum included); load average %.0f\n",
               (i1 - i0) / n / 1e6, (c1 - c0) / n / 1e6, load[0]);
    }
    if (RTA_PROF_ON && loops > 1) prof::report(stdout, n);
    if (!dump.empty()) {
        FILE* f = fopen(dump.c_str(), "wb");
        uint32_t n_blanks = (uint32_t)kept_counts.size();
        if (f) { fwrite(&n_blanks, 4, 1, f); fwrite(kept_counts.data(), 4, n_blanks, f); fwrite(kept.data(), sizeof(Vertex), kept.size(), f); fclose(f); }
        printf("%s %s: %zu vertices of %u blanks\n", f ? "wrote" : "cannot write", dump.c_str(), kept.size(), n_blanks);
    }
    if (!compare.empty()) {
        FILE* f = fopen(compare.c_str(), "rb");
        uint32_t n_blanks = 0;
        std::vector<uint32_t> counts;
        std::vector<Vertex> other;
        if (f && fread(&n_blanks, 4, 1, f) == 1) {
            counts.resize(n_blanks);
            fread(counts.data(), 4, n_blanks, f);
            size_t total = 0;
            for (uint32_t c : counts) total += c;
            other.resize(total);
            if (fread(other.data(), sizeof(Vertex), total, f) != total) other.clear();
        }
        if (f) fclose(f);
        if (other.empty() || counts != kept_counts) printf("against %s: the blanks do not have the same numbers of vertices (%zu here, %zu there)\n", compare.c_str(), kept.size(), other.size());
        else {
            // positions are in pixels of the 1280 x 448 surface (or a 2-D one)
            uint64_t same = 0, moved = 0, far = 0, colour = 0, texel = 0;
            double worst = 0;
            int colour_worst = 0;
            for (size_t k = 0; k < kept.size(); k++) {
                const Vertex& a = kept[k]; const Vertex& b = other[k];
                if (!memcmp(&a, &b, sizeof(Vertex))) { same++; continue; }
                double dx = a.x - b.x, dy = a.y - b.y, d = (dx < 0 ? -dx : dx) > (dy < 0 ? -dy : dy) ? (dx < 0 ? -dx : dx) : (dy < 0 ? -dy : dy);
                if (!(d == d)) d = 1e9;
                if (d > 0) moved++;
                if (d > 0.5) far++;
                if (d > worst) worst = d;
                if (a.r != b.r || a.g != b.g || a.b != b.b || a.a != b.a) {
                    colour++;
                    int by[4] = {a.r - b.r, a.g - b.g, a.b - b.b, a.a - b.a};
                    for (int c : by) if ((c < 0 ? -c : c) > colour_worst) colour_worst = c < 0 ? -c : c;
                }
                if (a.s != b.s || a.t != b.t || a.q != b.q) texel++;
            }
            printf("against %s: of %zu vertices %llu are the same bytes; %llu differ in position (%llu by more than half a pixel, the largest by %.2f pixels), "
                   "%llu in colour (by %d of 255 at most), %llu in texture coordinates\n", compare.c_str(), kept.size(), (unsigned long long)same, (unsigned long long)moved,
                   (unsigned long long)far, worst, (unsigned long long)colour, colour_worst, (unsigned long long)texel);
        }
    }
    if (times) printf("per blank over all passes: VU1 runs with their kicks %.3f ms (the kicks' GS work %.3f ms), GIF channel %.3f ms\n",
                      renderer.vif.stats.run_ms / blanks, renderer.gs.stats.kick_ms / blanks, renderer.gs.stats.path3_ms / blanks);
    return 0;
}
