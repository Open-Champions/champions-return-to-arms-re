// decode_bench.cpp - the renderer's CPU side alone (VIF1, VU1, the GS model: everything
// above render/backend.h), played from a recorded picture stream (render/stream.h), with
// no game, no runtime and no graphics API.  The same file is built for the Mac and for
// node, so that the cost of this code as WebAssembly can be told from its cost natively:
//
//   clang++ -std=c++17 -O2 -fno-strict-aliasing -ffp-contract=off -frounding-math -I tools/recomp/render \
//       tools/recomp/web/decode_bench.cpp tools/recomp/render/{vu1,vif1,gs,renderer}.cpp <vu1_translated.cpp | vu1_none.cpp> -o decode_bench
//   em++ (the same, without -frounding-math) -sNODERAWFS=1 -sINITIAL_MEMORY=1024MB -o decode_bench.js
//
//   decode_bench <stream> [--loops N] [--interpret] [--no-vu] [--no-kick] [--times]
//
// The stream is read into memory first; the first pass (textures decoded, tables filled)
// is timed apart from the rest.  A recording is derived from the game: it stays under local/.
#include "renderer.h"
#include "stream.h"

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

int main(int argc, char** argv) {
    std::string path;
    int loops = 20;
    bool interpret = false, no_vu = false, no_kick = false, times = false;
    for (int k = 1; k < argc; k++) {
        std::string a = argv[k];
        if (a == "--loops" && k + 1 < argc) loops = atoi(argv[++k]);
        else if (a == "--interpret") interpret = true;
        else if (a == "--no-vu") no_vu = true;
        else if (a == "--no-kick") no_kick = true;
        else if (a == "--times") times = true;
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
    renderer.vif.time_runs = renderer.gs.time_paths = times;
    if (no_vu) renderer.vif.run_programs = false;
    if (no_kick) renderer.vif.vu.kick = nullptr;
    uint64_t blanks = 0, vertices = 0, commands = 0, checksum = 0;
    renderer.on_frame = [&](FrameList& frame) {
        vertices += frame.vertices.size();
        commands += frame.commands.size();
        // what a backend would be handed, folded into one number: two builds that print the
        // same one made the same lists
        for (const Vertex& v : frame.vertices) { uint32_t w[7]; memcpy(w, &v, 28); for (uint32_t x : w) checksum = (checksum ^ x) * 0x100000001B3ull; }
        blanks++;
    };
    std::vector<uint8_t> ram;
    double first_ms = 0, rest_ms = 0;
    uint64_t first_blanks = 0, first_checksum = 0;
    for (int loop = 0; loop < loops; loop++) {
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
        if (loop == 0) { first_ms = took; first_blanks = blanks; first_checksum = checksum; } else rest_ms += took;
    }
    double n = blanks > first_blanks ? (double)(blanks - first_blanks) : 1;
    printf("VU1 main program: %s\n", renderer.vif.vu.translated ? "translated" : "interpreted");
    printf("first pass: %llu blanks in %.1f ms (%.2f ms each), list checksum %016llx\n", (unsigned long long)first_blanks, first_ms,
           first_ms / (first_blanks ? first_blanks : 1), (unsigned long long)first_checksum);
    printf("then %d passes: %.0f blanks, %.3f ms each of wall time; per blank %.0f vertices, %.0f commands, %.0f VU1 instruction pairs in %.0f runs\n",
           loops - 1, n, rest_ms / n, vertices / (double)blanks, commands / (double)blanks, renderer.vif.vu.instructions / (double)blanks, renderer.vif.vu.runs / (double)blanks);
    if (times) printf("per blank over all passes: VU1 runs with their kicks %.3f ms (the kicks' GS work %.3f ms), GIF channel %.3f ms\n",
                      renderer.vif.stats.run_ms / blanks, renderer.gs.stats.kick_ms / blanks, renderer.gs.stats.path3_ms / blanks);
    return 0;
}
