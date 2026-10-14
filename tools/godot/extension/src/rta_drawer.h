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
#include <godot_cpp/variant/vector3.hpp>
#include <godot_cpp/variant/aabb.hpp>
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
    RID get_world_viewport() const;
    RID get_world_environment() const;
    // debugging: the draws of the frame taken last that go to the 3-D surface, one line each (state, where on screen,
    // and for the scene's draws how far from the eye and at what elevation their vertices are)
    String describe_frame(int max_lines) const;
    // The sky as the game drew it in the frame taken last (rta_scene.cpp, "the sky"): `clear` the colour the game cleared
    // the picture to, `dome` whether the level has a painted dome round the camera, `top` / `bottom` the elevations
    // (radians) it reaches, `ring` 256 x 2 RGB: the colours of its upper edge (row 0) and lower edge (row 1) by
    // direction, `version` counts changes of the ring, `sun` a direction to the brightest part of it.
    Dictionary get_sky_info() const;
    void sky_reset();                               // a new level: what was learnt of the dome is forgotten
    void set_output_size(const Vector2i& size);
    // The level's generated ceilings and skirts (rta_fill.cpp): the shader they are drawn with (project/shaders/fill.gdshader),
    // and what was done with them
    void set_fill_shader(const Ref<Shader>& shader);
    Dictionary get_fill_info() const;
    // The character card (rta_card.cpp): the local player's character copied out of the scene into another scenario (the
    // portal's card: scene_view.gd makes the SubViewport); card_focus once a frame before submit (where the player stands,
    // and whether to take the figure this frame), set_card_turn to turn it
    void set_card_scenario(const RID& scenario);
    void card_focus(const Vector3& feet, bool capture);
    void set_card_turn(double radians);
    Dictionary get_card_info() const;
    Vector2i get_output_size() const { return output_size; }

  protected:
    static void _bind_methods();

  private:
    struct Pass {                                   // one viewport
        RID viewport, scenario, camera, environment, texture;
        std::vector<RID> instances, meshes;
        std::vector<uint8_t> overridden;            // per instance: it carries a material of its own (place_mesh)
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
    // scene mode: every texture's brightness, coarsely (THUMB x THUMB means): the level's light is painted into its
    // textures, and where it comes from is read out of them (rta_scene.cpp, Scene::sun_sum)
    enum { THUMB = 16 };
    struct Thumb { uint8_t lum[THUMB * THUMB]; };
    std::unordered_map<uint32_t, Thumb> thumbs;
    std::unordered_map<uint32_t, Target> targets;
    std::unordered_map<uint32_t, Ref<Shader>> shaders;      // by variant bits (a Shader resource: its set_code runs the preprocessor)
    struct Material { RID rid; uint64_t last_used = 0; };
    std::unordered_map<std::string, Material> materials;
    std::vector<Pass*> all_passes;
    Target* shown = nullptr;
    int shown_rect[4] = {0, 0, 0, 0};
    uint64_t frames = 0;
    float last_aspect = 0;
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
    RID place_mesh(Pass& pass, RID mesh, RID material, float order);
    RID instance_for(Pass& pass);
    RID mesh_for(Pass& pass);

    // ---- scene mode ----
    struct Scene;
    Scene* scene = nullptr;
    bool scene_mode = false;
    Target* world_target();
    void scene_begin(const rtag_frame& frame);
    void scene_scan_sky(const rtag_frame& frame, const Target& world);
    bool scene_take(Pass& pass, const rtag_frame& frame, const rtag_draw& draw, const Target& target, RID texture, float order);
    void scene_end(const rtag_frame& frame);
    void scene_release();
    static void add_surface_bytes(RID mesh, int primitive, const PackedByteArray& positions, const PackedByteArray& attributes, int count, bool normals = false, const AABB* box = nullptr);
    friend struct Scene;

    // ---- the fill (rta_fill.cpp) ----
    struct Fill;
    Fill* fill = nullptr;
    struct CpuTexture { int w = 0, h = 0; std::vector<uint8_t> rgba; };
    std::unordered_map<uint32_t, CpuTexture> cpu_textures;     // scene mode: every texture's pixels, for what is cut out of them
    void fill_build(const rtag_fill& f, RID scenario);
    void fill_frame(const rtag_frame& f, const Vector3& eye, RID scenario);
    void fill_learn(const rtag_scene* tap, const rtag_draw& d, const rtag_scene_piece* pieces, uint32_t piece_count, const Vector3& eye);
    void fill_order();
    void fill_option(const String& name, double value);
    void fill_note_level(float order);
    bool fill_drops(const rtag_frame& f, const rtag_draw& d);
    void fill_release();
    void fill_free();
    RID fill_material(Fill& fl, uint8_t kind, RID texture);
    void fill_params(Fill& fl);
    friend struct Fill;

    // ---- the character card (rta_card.cpp) ----
    struct Card;
    Card* card = nullptr;
    void card_take(const rtag_scene* tap, const rtag_draw& d, const rtag_scene_piece* pieces, uint32_t count);
    void card_end(const Target& world);
    void card_clear();
    void card_free();
};

}  // namespace godot
