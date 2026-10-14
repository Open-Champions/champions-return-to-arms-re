// worldfill_main.cpp - the fill of a level from its .world file, without the game: figures,
// and the meshes as a Wavefront file to look at.
//
//   worldfill_test LEVEL.world [--obj OUT.obj] [--no-ceilings] [--no-skirts]
//
// Build: clang++ -std=c++17 -O2 worldfill.cpp worldfill_main.cpp -o worldfill_test
// (OUT.obj is derived from game data: write it under local/.)
#include "worldfill.h"

#include <cstdio>
#include <cstring>
#include <vector>

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr, "worldfill_test LEVEL.world [--obj OUT.obj] [--no-ceilings] [--no-skirts]\n"); return 2; }
    render::FillOptions opt;
    const char* obj = nullptr;
    for (int k = 2; k < argc; k++) {
        if (!strcmp(argv[k], "--obj") && k + 1 < argc) obj = argv[++k];
        else if (!strcmp(argv[k], "--no-ceilings")) opt.ceilings = false;
        else if (!strcmp(argv[k], "--no-skirts")) opt.skirts = false;
    }
    FILE* f = fopen(argv[1], "rb");
    if (!f) { fprintf(stderr, "cannot read %s\n", argv[1]); return 1; }
    std::vector<uint8_t> data;
    uint8_t buffer[65536];
    for (size_t n; (n = fread(buffer, 1, sizeof buffer, f)) > 0;) data.insert(data.end(), buffer, buffer + n);
    fclose(f);
    auto level = render::build_fill(data.data(), data.size(), 0, false, argv[1], opt);
    if (!level) { fprintf(stderr, "%s: not a .world as the documents describe it\n", argv[1]); return 1; }
    size_t ceilings = 0, skirts = 0;
    for (const render::FillMesh& m : level->meshes) (m.kind == render::FILL_CEILING ? ceilings : skirts) += m.count / 3;
    printf("%s: floor %.0f square units; walls that carry a ceiling: %d cells, lid %.0f over the floor (median); ceiling %.0f square units in %zu triangles; "
           "skirt %.0f square units in %zu triangles; %zu meshes; %.1f ms\n",
           argv[1], level->floor_area, level->walls, level->lid_median, level->ceiling_area, ceilings, level->skirt_area, skirts, level->meshes.size(), level->build_ms);
    if (obj) {
        FILE* o = fopen(obj, "w");
        if (!o) { fprintf(stderr, "cannot write %s\n", obj); return 1; }
        for (const render::FillVertex& v : level->vertices) fprintf(o, "v %.2f %.2f %.2f\n", v.position[0], v.position[1], v.position[2]);
        size_t at = 1;
        for (const render::FillMesh& m : level->meshes) {
            fprintf(o, "g %s\n", m.kind == render::FILL_CEILING ? "ceiling" : "skirt");
            for (uint32_t k = 0; k < m.count; k += 3) fprintf(o, "f %zu %zu %zu\n", at + m.first + k, at + m.first + k + 1, at + m.first + k + 2);
        }
        fclose(o);
    }
    return 0;
}
