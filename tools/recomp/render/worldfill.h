// worldfill.h - geometry a level does not have, made from what it has, for a camera that
// stands in it.  docs/issues/native-first-person-world.md says what is missing and why.
//
// The levels of this game were built to be looked at from above: measured over 17 of them
// (tools/recomp/render/worldfill_measure.py) no walked floor has a ceiling, every wall is a
// solid block that ends in a lid 100 to 200 units over the floor, and the level stops at the
// outer rim of the outermost lid.  From the floor that reads as: nothing above the walls, and
// a world that ends in a cut edge.  This makes two kinds of mesh from a level's own terrain
// (the height samples every 4 units, which are the top surface of everything, and the path
// grid, which says where the floor is):
//
//   FILL_CEILING   over the walked floor of a walled level, a surface that meets every wall
//                  at the height of its lid and rises a little away from the walls (a low
//                  vault), carried on over the lids so no gap shows at a wall's top.  Made
//                  where a wall of at least `wall_min` stands within `reach`.
//   FILL_SKIRT     beyond the level's outer rim, where the rim is a lid (high ground nobody
//                  walks on) and not a floor: the lid carried outward `skirt_width` units,
//                  sinking, with alpha falling to nothing - ground for the haze to lie on,
//                  and a horizon where the saw-tooth edge was.  A floor that ends at the rim
//                  (a floating island, a beach) gets none: there the edge is the design.
//
// What it is NOT: nothing here is the game's art.  A vertex has a position, a normal, a
// place for a tiling texture (world x, y / 64) and a grey level that says how near the next
// wall is (ceilings: 255 at the wall, falling to `far_shade` in the middle of a hall) or how
// far out it lies (skirts: alpha 128 at the rim, 0 at the outer edge).  How it is shaded is
// the renderer's: the OpenGL program draws it plain and dark (gs.cpp, Gs::draw_fill); Godot
// lights it.  Whether a level is an interior at all is decided by the caller (app/fpworld.cpp
// has the rule) and passed in FillOptions.
//
// Input: the level's `.world` entry (docs/formats/world.md) - either the file's bytes
// (relocated = false) or the fixed-up structure in the machine's memory (relocated = true:
// `memory` is main memory, `world` the address in it, offsets are addresses).  Plain C++,
// no graphics API, nothing of the runtime; building takes some tens of milliseconds.
#pragma once
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace render {

enum : uint8_t { FILL_CEILING = 1, FILL_SKIRT = 2 };

struct FillVertex {
    float position[3];      // world space: z is up, the game's units (a character is about 60 high)
    float normal[3];        // unit length: a ceiling's looks down, a skirt's up
    float uv[2];            // world x, y / 64: for a tiling texture of the renderer's choice
    uint8_t rgba[4];        // grey level in r, g, b (see above); a: 128 = opaque (the GS's 1.0)
};

struct FillMesh {           // a block of one kind: triangles, three vertices each
    uint8_t kind, pad[3];
    uint32_t first, count;  // FillLevel::vertices
    float bounds[6];        // min x, y, z, max x, y, z
};

struct FillOptions {
    bool ceilings = true, skirts = true;
    float wall_min = 70;        // a wall carries a ceiling when its lid is this far over the floor beside it
    float reach = 4000;         // ... and the floor is within this distance of it
    int over = 12;              // cells (16 units) the ceiling is carried on over the lids and over gaps
    float vault = 0.50f;        // the ceiling rises by this much per unit of distance from the nearest wall,
    float vault_most = 600;     // up to this much: a corridor 100 wide gets 25 at its middle, a court 1000 wide 250,
                                // so the far wall of a wide room is not hidden behind a ceiling that hangs at lid height
    float clearance = 96;       // and is never nearer to the floor than this
    float skirt_width = 480, skirt_drop = 0.12f;
    float rim_min = 40;         // the rim is a lid when it is this far over the nearest floor
    uint8_t far_shade = 150;
};

struct FillLevel {
    std::string name;
    uint64_t serial = 0;        // a number of the build: another level, or other options, another number
    std::vector<FillVertex> vertices;
    std::vector<FillMesh> meshes;
    // figures: square units
    double floor_area = 0, ceiling_area = 0, skirt_area = 0;
    float lid_median = 0;       // of the walls that carry a ceiling, over the floor beside them
    int walls = 0;              // cells of such walls
    float bounds[6] = {0, 0, 0, 0, 0, 0};
    double build_ms = 0;
};

// Build the fill of a level.  Null when the data is not a .world as the documents describe it.
std::shared_ptr<const FillLevel> build_fill(const uint8_t* memory, size_t size, uint32_t world, bool relocated, const char* name, const FillOptions& options);

// The fill of the level that is loaded: published by whoever builds it (the game side, at a
// level load), read by whoever draws it (another thread: a renderer keeps the pointer it took).
void publish_fill(std::shared_ptr<const FillLevel> level);
std::shared_ptr<const FillLevel> current_fill();

}  // namespace render
