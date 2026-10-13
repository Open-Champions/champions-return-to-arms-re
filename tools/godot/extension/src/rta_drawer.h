// rta_drawer.h - RtaDrawer: Godot draws the game's frame.
//
// Each frame of the machine carries a draw list (rtag.h): textures, surfaces, and draws in
// the order the game's Graphics Synthesizer was given them, each with vertices already in
// screen space and its complete state.  The drawer submits that list through Godot's
// RenderingServer:
//
//   surface (render target)   a viewport with a scenario of its own, never cleared; a small
//                             surface that is drawn, read and drawn again within one frame
//                             (the ground shadows) gets one viewport per such pass
//   texture                   a 2-D texture made from the RGBA the list hands over
//   draw                      a mesh (rebuilt every frame: position, colour, texture
//                             coordinates and fog per vertex) on an instance of its own, with
//                             a shader material for its state (materials are kept per
//                             distinct state; the shader is project/shaders/gs_draw.gdshaderinc)
//   order                     every material is drawn in the transparent pass, and each
//                             instance's sorting offset makes that pass keep the list's order;
//                             the depth test and the depth write are the draw's own
//   order of surfaces         the viewports are activated in the order the list needs them
//                             (a surface is rendered after what it reads and before what
//                             reads it)
//   the picture               the surface the display circuit reads is a texture the window
//                             shows (project/view.gd)
//
// In scene mode (set_scene_mode) the draws the vertex programs made go into a 3-D world
// instead: see rta_scene.cpp.
#pragma once
#include "rta_machine.h"

#include <godot_cpp/classes/image.hpp>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/classes/shader.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/rect2.hpp>
#include <godot_cpp/variant/rid.hpp>
#include <godot_cpp/variant/transform3d.hpp>
#include <godot_cpp/variant/projection.hpp>
#include <godot_cpp/variant/vector2i.hpp>

#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace godot {

class RtaDrawer : public RefCounted {
    GDCLASS(RtaDrawer, RefCounted)
  public:
    RtaDrawer();
    ~RtaDrawer();
    // output_size: the real size of a surface as large as the picture; samples: multisampling of the 3-D surface
    void setup(const Ref<RtaMachine>& machine, const RID& parent_viewport, const Vector2i& output_size, int samples);
    void set_shader_code(const String& code);       // project/shaders/gs_draw.gdshaderinc
    void submit();                                  // the machine's current frame
    RID get_shown_texture() const;
    Rect2 get_shown_region() const;                 // in that texture's pixels
    Ref<Image> get_shown_image() const;             // what Godot drew into the shown surface (after the frame was rendered)
    String figures() const;
    void dump_surfaces(const String& prefix) const; // debugging: every surface as Godot holds it now, PREFIX-s<id>-p<pass>.png
    void release();                                 // free everything made in the RenderingServer

    // ---- scene mode (rta_scene.cpp) ----
    void set_scene_mode(bool on);
    void set_scene_option(const String& name, double value);
    Dictionary get_scene_info() const;
    RID get_world_scenario() const;
    RID get_world_camera() const;

  protected:
    static void _bind_methods();

  private:
    struct Pass {                                   // one viewport
        RID viewport, scenario, camera, environment, texture;
        std::vector<RID> instances, meshes;
        size_t used = 0;                            // instances with something to draw this frame
        bool drawn_once = false;
    };
    struct Target {
        uint32_t id = 0;
        int lw = 0, lh = 0, pw = 0, ph = 0;
        bool screen = false;
        std::vector<Pass*> passes;
        Pass* latest = nullptr;                     // holds the surface's content as of the end of the last list
    };
    struct Node {                                   // a run of draws rendered by one viewport in one frame
        Target* target = nullptr;
        Pass* pass = nullptr;
        size_t first_draw = 0, last_draw = 0;
        bool sealed = false;
        std::vector<int> after;                     // nodes that must be rendered before this one
        size_t count = 0;
    };

    Ref<RtaMachine> machine;
    RID parent_viewport;
    Vector2i output_size;
    int samples = 0;
    std::string shader_code;
    std::unordered_map<uint32_t, RID> textures;
    std::unordered_map<uint32_t, Target> targets;
    std::unordered_map<uint32_t, Ref<Shader>> shaders;      // by variant bits (a Shader resource: its set_code runs the preprocessor)
    struct Material { RID rid; uint64_t last_used = 0; };
    std::unordered_map<std::string, Material> materials;
    std::vector<Pass*> all_passes;
    Target* shown = nullptr;
    int shown_rect[4] = {0, 0, 0, 0};
    uint64_t frames = 0;
    // figures
    uint64_t draws_submitted = 0, vertices_submitted = 0, materials_made = 0, meshes_made = 0, passes_rendered = 0, stale_reads = 0, approximated = 0,
             depth_always_writes = 0, textures_made = 0, skipped = 0;
    double submit_usec = 0;
    bool inverted_depth_ok = true;
    // Conventions found by trying (Godot 4.5.2, Compatibility): a position a spatial shader writes itself has y down in
    // the viewport's picture, as the list's positions have; a viewport's texture is read with v down; and ALBEDO is
    // taken for an sRGB colour and goes through an approximate round trip that the shader undoes (gs_draw.gdshaderinc,
    // to_linear).  Test aids turn each over.
    float flip_y = 1.0f;
    bool flip_surfaces = false;
    bool stored_colours = true;
    float world_bias = 0.00002f;                    // scene mode: draws that do not write depth come this much nearer (clip space)

    Pass* make_pass(Target& target);
    void free_pass(Pass* pass);
    void size_target(Target& target);
    RID shader_for(uint32_t variant);
    RID material_for(const rtag_draw& draw, const Target& target, bool inverted, RID texture, bool texture_flipped, uint32_t extra = 0);
    void add_draw(Pass& pass, const rtag_frame& frame, const rtag_draw& draw, const Target& target, RID texture, bool texture_flipped, float order);
    void add_copy(Pass& pass, const rtag_draw& draw, const Target& target, const Target& source, RID texture, float order);
    RID place(Pass& pass, RID material, float order);
    RID mesh_for(Pass& pass);

    // ---- scene mode ----
    struct Scene;
    Scene* scene = nullptr;
    bool scene_mode = false;
    Target* world_target();
    void scene_begin(const rtag_frame& frame);
    bool scene_take(Pass& pass, const rtag_frame& frame, const rtag_draw& draw, const Target& target, RID texture, float order);
    void scene_end(const rtag_frame& frame);
    void scene_release();
    static void add_surface_bytes(RID mesh, int primitive, const PackedByteArray& positions, const PackedByteArray& attributes, int count);
    friend struct Scene;
};

}  // namespace godot
