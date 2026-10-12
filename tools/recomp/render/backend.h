// backend.h - the boundary between the renderer and a graphics API.
//
// Everything above this line (vif1, vu1, gs) is portable C++ with no graphics calls: it
// turns what the game sends into a FrameList - textures as RGBA8 pictures, render targets
// by number and size, and an ordered list of draws, each with its complete state and a
// range of vertices in target coordinates.  A Backend executes FrameLists.  backend_gl.cpp
// is the OpenGL 4.1 one; a Direct3D or Metal one implements the same four functions.
//
// Coordinates: a vertex position is in pixels of its target's *logical* size (the size
// the game thinks the surface has, 1280 x 448 for the 3-D buffer), origin top left; the
// backend scales it to whatever the target really is.  z is 0..1, larger = nearer.
// Texture coordinates are (s, t, q): the sample position in texels is (s/q, t/q) *
// st_scale; q is 1 for draws that give texel coordinates.
#pragma once
#include <cstdint>
#include <vector>

namespace render {

struct Vertex {
    float x, y, z;
    float s, t, q;
    uint8_t r, g, b, a;
    uint8_t fog = 255, pad[3] = {0, 0, 0};      // the GS fog coefficient: 255 leaves the colour, 0 gives the fog colour
};

enum PrimKind : uint8_t { PK_TRIANGLES, PK_LINES, PK_POINTS };
enum WrapMode : uint8_t { WRAP_REPEAT, WRAP_CLAMP, WRAP_REGION_CLAMP, WRAP_REGION_REPEAT };
enum CmdKind : uint8_t { CMD_DRAW, CMD_COPY };

struct DrawCmd {
    CmdKind kind = CMD_DRAW;
    PrimKind prim = PK_TRIANGLES;
    uint32_t first = 0, count = 0;      // vertices
    uint32_t target = 0;                // render target number
    int scissor[4] = {0, 0, 0, 0};      // x0, y0, x1, y1 in logical pixels, x1/y1 exclusive
    // texture: 0 = none.  tex_is_target: sample render target number `texture` instead.
    uint32_t texture = 0;
    bool tex_is_target = false;
    float tex_size[2] = {1, 1};         // texels the picture is wide and high (normalisation)
    float tex_offset[2] = {0, 0};       // added to the texel position (a texture that starts inside a surface)
    uint32_t tex_missing = 0;           // the draw named a texture nothing was sent for: its TBP0 + 1 (untextured then)
    float st_scale[2] = {1, 1};
    bool linear = false;
    WrapMode wrap[2] = {WRAP_REPEAT, WRAP_REPEAT};
    float region[4] = {0, 0, 0, 0};     // minu, maxu, minv, maxv for the region modes
    // a surface sampled as a texture of a format without eight bits of alpha: 1 = 24 bit
    // (alpha is ta0), 2 = 16 bit (ta1 where the stored alpha is 0x80 or more, else ta0);
    // aem: alpha 0 where the colour is black and ta0 would be taken
    uint8_t texa_mode = 0, ta0 = 0, ta1 = 0x80;
    bool aem = false;
    uint8_t tfx = 0;                    // 0 modulate, 1 decal, 2 highlight, 3 highlight 2
    bool tcc = false;                   // texture alpha used
    // interface art stored as two stacked fields: sample line L of the woven picture from
    // row (L >> 1) + (L & 1) * weave_half of the stored one.  0 = off.
    float weave_half = 0;
    float weave_base = 0;               // V of the first row of the half this draw names
    // tests
    bool alpha_test = false;
    uint8_t atst = 1, aref = 0;         // GS ATST: 0 never, 1 always, 2 <, 3 <=, 4 ==, 5 >=, 6 >, 7 !=
    uint8_t afail = 0;                  // 0 keep, 1 colour only, 2 depth only, 3 rgb only
    bool depth_test = false;
    uint8_t ztst = 1;                   // 0 never, 1 always, 2 >=, 3 >
    bool depth_write = false;
    // blend: colour = (A - B) * C + D with A, B, D of {0 source, 1 destination, 2 zero} and
    // C of {0 source alpha, 1 destination alpha, 2 fix}; alpha 0x80 is 1.0
    bool blend = false;
    uint8_t ba = 0, bb = 0, bc = 0, bd = 0, fix = 0x80;
    bool mask_rgb = false, mask_a = false;  // channels not written
    // fogging: after the texture function the colour is F x colour + (1 - F) x fog colour,
    // F the vertex's coefficient (Vertex::fog / 256)
    bool fog = false;
    uint8_t fog_colour[3] = {0, 0, 0};
    // CMD_COPY: a rectangle of target `texture` copied to target `target` (logical pixels)
    int copy_src[4] = {0, 0, 0, 0}, copy_dst[4] = {0, 0, 0, 0};
};

struct TextureData {
    uint32_t id = 0;
    int width = 0, height = 0;
    std::vector<uint8_t> rgba;          // rows top to bottom, alpha as the GS has it (0x80 = 1.0)
};

struct TargetInfo {
    uint32_t id = 0;
    int width = 0, height = 0;          // logical
    bool screen = false;                // a surface the size of the picture: drawn at output resolution
};

struct FrameList {
    std::vector<Vertex> vertices;
    std::vector<DrawCmd> commands;
    std::vector<TextureData> textures;  // new this frame; made before any command runs
    std::vector<TargetInfo> targets;    // new or resized this frame
    std::vector<uint32_t> dead_textures;
    uint32_t show_target = 0;           // what the display circuit reads; 0 = nothing
    int show_rect[4] = {0, 0, 0, 0};    // x, y, width, height in that target's logical pixels
    uint64_t number = 0;
    void clear() {
        vertices.clear(); commands.clear(); textures.clear(); targets.clear(); dead_textures.clear();
        show_target = 0;
    }
};

struct Backend {
    virtual ~Backend() {}
    // The size of the picture in real pixels; screen targets are made this size.
    virtual void set_output_size(int width, int height) = 0;
    virtual void execute(const FrameList& frame) = 0;
    // Draw the shown target into the bound framebuffer of the given size (letterboxed to
    // `aspect`, width / height).
    virtual void present(int width, int height, double aspect) = 0;
    // The shown target as RGBA8, rows top to bottom, at its real size.
    virtual bool read_shown(std::vector<uint8_t>& rgba, int& width, int& height) = 0;
};

}  // namespace render
