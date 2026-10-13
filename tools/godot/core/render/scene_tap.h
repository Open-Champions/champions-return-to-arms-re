// scene_tap.h - the 3-D scene as the vertex programs were given it.
//
// PROPOSED FOR tools/recomp/render/ (new files; kept under tools/godot/core/render/ until the
// owner of that directory takes them; tools/godot/build.py copies them into its snapshot).
//
// The renderer's output (backend.h, FrameList) is what the game's vertex programs made:
// triangles already projected to the screen.  A host that wants to light the scene, throw
// shadows on it or look at it from somewhere else needs what went INTO the programs.  This
// taps it, for the four mesh programs that draw nearly all of the 3-D scene
// (docs/spec/render-pipeline.md 4.4: entries 0x42 / 0x44, models, and 0x46 / 0x48, level
// chunks): for every mesh packet a program kicks,
//   - the packet's vertices in OBJECT space as the VIF unpacked them: position (the stored
//     16-bit value / 16), NORMAL (the stored 8-bit vector, unit length here), up to four
//     joints with weights (models);
//   - the MATRICES the program transformed them with: the four rows the set-up entry was
//     given (level: entry 0x16; rigid model: 0x02 through the joint slots) or the joint
//     matrices in VU1 memory (models), all of them object -> the game's clip space;
//   - which vertex became which vertex of the draw list: the strip the program builds is
//     replayed from the packet's slot rows (docs/formats/model-texture.md, "Building the
//     strip"), so every FrameList vertex of the packet has its source vertex;
//   - an IDENTITY: a figure over the packet's own bytes - the same packet of the same file
//     gives the same value in every frame - with the number of earlier packets of that
//     identity in the frame, and a number that changes with every set-up (one draw of one
//     object).
// And, when the game side says where its camera is (camera(), below), every vertex in WORLD
// space with its world normal: clip space taken back through the inverse of the game's
// view-projection matrix.
//
// A packet is only handed on when it checks: the tap projects its own reconstruction and
// compares it with the positions the program itself wrote into the strip (to 1/4 pixel).
// What does not check - a program state not understood, a shell pass - is counted and left
// out; the host then has the draw list's vertices and nothing else for it, as before.
//
// Nothing here draws or includes a graphics API; it reads VU1 memory and the FrameList's
// vertex count.  Both ways of running the programs feed it - the interpreter (vu1_step.h)
// and the translation (vu1_fast.h) call the same Vu1::kick, which is where it listens -
// and it changes nothing they compute: lists with and without the tap are the same bytes.
//
// Hooks (tools/godot/recomp.patch has them as a patch against vif1.h / vif1.cpp):
//   Vif1::on_program     called before a microprogram runs (set-up entries are read here)
//   Vif1, NOP notes      NUM 0xA8 / 0xA9: words from the game side (the camera block)
//   Vu1::kick            wrapped by install(): no change to the sources
#pragma once
#include <cstddef>
#include <cstdint>
#include <unordered_map>
#include <vector>

namespace render {

class Renderer;

enum : uint8_t { TAP_LEVEL = 1, TAP_MODEL = 2 };
enum : uint8_t {
    TAP_TWO_PASS = 1,       // a two-pass program: this piece is one of two kicks of the same packet
    TAP_FIRST_PASS = 2,     // ... the first one (the environment-map layer, GS context 2)
    TAP_SKINNED = 4,        // some vertex follows more than one joint, or a joint other than the first
    TAP_MIRRORED = 8,       // drawn again mirrored in z (entry 0x3c)
    TAP_CLIP_FLAG = 16,     // the game's clip flag was set for the object (it may drop triangles near the edge)
};

struct TapSource {          // one vertex of a packet as the program was given it
    float position[3];      // object space
    float normal[3];        // object space, unit length (zero when the packet has none)
    uint8_t joint[4];       // joint indices (0..63); models
    uint8_t weight[4];      // of 255; the sum is 255
};

struct TapVertex {          // one per FrameList vertex of a piece
    float world[3];         // world space (when TapFrame::have_camera)
    float normal[3];        // world space, unit length
    float clip[4];          // the game's clip space, as the program computed it (x, y, depth x 2^-50, w)
    uint16_t source;        // which TapSource of the piece
    uint16_t pad;
};

struct TapPiece {
    uint8_t kind, entry, flags, pad;
    uint32_t object;        // counts set-ups: pieces with the same number are one draw of one object
    uint64_t mesh;          // identity of the packet's data
    uint32_t occurrence;    // pieces with the same identity before this one in the frame
    uint32_t list_first, list_count;        // FrameList::vertices
    uint32_t first;         // TapFrame::vertices (list_count of them, the same order)
    uint32_t source_first, source_count;    // TapFrame::sources
    uint32_t joints;        // TapFrame::joints: index of the first of 64 matrices (models), or of 1 (level)
};

struct TapFrame {
    std::vector<TapPiece> pieces;
    std::vector<TapVertex> vertices;
    std::vector<TapSource> sources;
    std::vector<float> joints;              // 16 floats each: object -> clip, rows as the program holds them
    bool have_camera = false;
    float world_to_view[12];                // g_cameraMatrix: four rows of three (camera = p.x r0 + p.y r1 + p.z r2 + r3)
    float view_projection[16];              // world -> clip, the depth column x 2^-50
    float proj_scale = 0;                   // g_projScale
    void clear() { pieces.clear(); vertices.clear(); sources.clear(); joints.clear(); }
};

struct TapStats {
    uint64_t kicks = 0, pieces = 0, vertices = 0;
    uint64_t rejected_count = 0;            // the list did not grow by three vertices per drawn triangle
    uint64_t rejected_check = 0;            // the reconstruction is not where the program put the vertices
    uint64_t rejected_layout = 0;           // the packet is not laid out as the documents say
    uint64_t other_entries = 0;             // kicks of other programs (particles, water, trails, shadows): not tapped
    uint64_t checked = 0, off = 0;          // vertices compared with the program's own positions, and how many were off
    uint64_t camera_blocks = 0, level_setups = 0, level_rows_equal = 0;     // set-ups whose depth and translation rows are the camera's
    double worst = 0;                       // largest difference of an accepted vertex, GS units (1/16 pixel)
};

class SceneTap {
  public:
    // Attach to a renderer (before anything is fed).  The renderer's kick goes through the tap from here on.
    void install(Renderer& renderer);
    // The game's camera, as the game holds it when the packets that follow were made: the 62 words at
    // 0x44f108 (g_projScale, g_cameraMatrix, g_viewProj, g_viewProjWorld, g_viewProjModel).  Either
    // called directly, or carried in the VIF1 stream as notes (camera_notes() makes them).
    void camera(const uint32_t* words, size_t count);
    // The frame's pieces so far; the caller swaps them out at a vertical blank (after the FrameList's
    // on_frame, before the next transfer) and the tap starts again.
    void take(TapFrame& out);
    TapStats stats;
    bool check = true;                      // compare every piece with the program's own output (leave on: it is cheap)

    // The notes: `count` words as VIF1 codes (NOP, NUM 0xA8 then 0xA9, sixteen bits each) to put in
    // front of a transfer.
    static void camera_notes(const uint32_t* words, size_t count, std::vector<uint32_t>& codes);
    enum { CAMERA_ADDRESS = 0x44F108, CAMERA_WORDS = 62 };

    // ---- the hooks ----
    void program(int entry);                // Vif1::on_program
    void note(uint32_t num, uint32_t imm);  // Vif1: a NOP with NUM 0xA8 / 0xA9

  private:
    Renderer* r = nullptr;
    TapFrame frame;
    float rows[16];                         // the last set-up's transform (object -> clip)
    bool have_rows = false, mirrored = false, clip_flag = false;
    uint8_t rows_kind = 0;
    uint32_t object = 0;
    int joints_at = -1;                     // where this object's joint matrices are in frame.joints (-1: not copied yet)
    double inverse[16], inverse_world[16];  // of view_projection, and of g_viewProjWorld (world / 4 -> clip)
    float camera_world[16];                 // g_viewProjWorld as it came
    std::vector<uint32_t> note_words;
    uint32_t note_expect = 0, note_half = 0, note_low = 0;
    std::unordered_map<uint64_t, uint32_t> seen;    // identities of this frame, for the occurrence count
    static void kick(void* user, uint32_t qword);
    void kicked(uint32_t qword, size_t before, size_t after);
};

}  // namespace render
