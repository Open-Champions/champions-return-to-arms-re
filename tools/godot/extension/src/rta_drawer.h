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
#include "rta_pack.h"

#include <godot_cpp/classes/image.hpp>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/classes/shader.hpp>
#include <godot_cpp/variant/packed_byte_array.hpp>
#include <godot_cpp/variant/packed_float32_array.hpp>
#include <godot_cpp/variant/packed_int64_array.hpp>
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
#include <unordered_set>
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
    // A picture between two game frames (main.gd, the display rate above 60): the frame taken last drawn again with
    // the camera, and the kept models' corners (scene mode, option `tween`), carried T game frames on from where they
    // were - T in 0..1 is past the last frame (from the last two: the motion between them, on), T < 0 between them.
    // The game is not asked anything; the passes of the last submit are rendered again in their order.
    void redraw(double t);
    RID get_shown_texture() const;
    Rect2 get_shown_region() const;                 // in that texture's pixels
    bool get_shown_flipped() const { return rd; }   // the region is stored bottom up (Forward+ / Mobile): show it turned over
    Ref<Image> get_shown_image() const;             // what Godot drew into the shown surface (after the frame was rendered)
    String figures() const;
    void dump_surfaces(const String& prefix) const; // debugging: every surface as Godot holds it now, PREFIX-s<id>-p<pass>.png
    void log_draws(int frames);                     // debugging: every draw of the next FRAMES lists to the output, with its state
    bool get_shown_stored() const;                  // the shown picture holds stored values under the sRGB curve (view.gd decodes it)
    int draw_log = 0;
    void release();                                 // free everything made in the RenderingServer

    // ---- scene mode (rta_scene.cpp) ----
    void set_scene_mode(bool on);
    void set_scene_option(const String& name, double value);
    // The scene's objects (rtag_scene_piece::object) the next frames leave out: their draws are not made at all.  For a
    // host that draws something else in their place (er_layer.gd: a figure posed by the object's skeleton).
    void set_hidden_objects(const PackedInt64Array& objects);
    // ... only their skinned packets (model_remaster.gd: the body drawn there, what the figure holds left to the game)
    void set_hidden_skinned(const PackedInt64Array& objects);
    Dictionary get_scene_info() const;
    // per skinned figure packet of the frame taken last (index into its rtag_scene::pieces): [texture RID, tex_size, tex_offset,
    // st_scale, alpha cut (-1 none), alpha from (0 texture, 1 TEXA ta0, 2 none), ta0, blended] (rta_scene.cpp)
    Dictionary get_piece_textures() const;
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
    void set_fill_shader(const Ref<Shader>& shader, const Ref<Shader>& skirt_shader);
    Dictionary get_fill_info() const;
    // The character card (rta_card.cpp): the local player's character copied out of the scene into another scenario (the
    // portal's card: scene_view.gd makes the SubViewport); card_focus once a frame before submit (where the player stands,
    // and whether to take the figure this frame), set_card_turn to turn it
    void set_card_scenario(const RID& scenario);
    void card_focus(const Vector3& feet, bool capture);
    void set_card_turn(double radians);
    Dictionary get_card_info() const;
    Vector2i get_output_size() const { return output_size; }
    // The art pack (rta_pack.h): the folder ("" none), and mip maps for every texture (the game's own too).  Returns the
    // number of pictures found in the folder.  Before the first frame; textures made later take it.
    int64_t set_art_pack(const String& folder, bool mipmaps);
    Dictionary get_pack_info() const;
    // the Elden Ring world layer (rta_world.cpp; project/er_world.gd)
    void set_world_layer(bool on, const Dictionary& table);
    Dictionary get_world_info(int64_t frames_back) const;
    PackedFloat32Array get_grass(const Vector3& eye, double radius, int64_t max_points);
    int64_t get_grass_epoch() const { return (int64_t)grass_epoch; }
    void world_reset();
    // ... the rebuild (er_world.gd): shapes of the level drawn by Elden Ring pieces fitted over them; a draw lying wholly
    // inside one of these volumes is left out (drawing only: nothing of the game's changes).  volumes: [[cx, cy, cz, hx,
    // hy, hz, yaw degrees, cylinder 0/1, kinds (1 level chunks, 2 models, 3 both)], ...]
    void set_world_hide(const Array& volumes);
    Array get_world_hide() const;           // per volume: [order of its first draw left out this frame (-1 none), draws, mean colour, draws in it]
    void world_dump(const String& path);    // the next list's pieces (every draw's packets, world space) as an OBJ file

  protected:
    static void _bind_methods();

  private:
    struct Pass {                                   // one viewport
        RID viewport, scenario, camera, environment, texture;
        std::vector<RID> instances, meshes;
        std::vector<uint64_t> shapes;               // per mesh of the pool: the vertex count and primitive it holds (mesh_for_flat), 0 other
        std::vector<uint8_t> overridden;            // per instance: it carries a material of its own (place_mesh)
        size_t used = 0;                            // instances with something to draw this frame
        bool drawn_once = false;
        bool stored = false;                        // its picture holds stored values under Godot's sRGB curve (V_STORED)
        bool stored_next = false;                   // ... what this frame's run draws it as (taken over when it is rendered)
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
    RtaPack* pack = nullptr;                        // set_art_pack: pictures from the pack and mip maps, made on its threads
    bool pack_mipmaps = false;
    std::unordered_set<uint64_t> woven_textures;   // RIDs holding an art pack's two-field picture (weave_half -1)
    std::unordered_map<uint32_t, uint64_t> texture_serial;     // which answer of the pack's a texture waits for
    uint64_t pack_serial = 0, pack_named = 0, pack_found = 0, pack_replaced = 0, pack_replaced_files = 0;
    std::vector<rtag_texture_name> name_buffer;
    void pack_frame(const rtag_frame& f);
    // scene mode: every texture's brightness, coarsely (THUMB x THUMB means): the level's light is painted into its
    // textures, and where it comes from is read out of them (rta_scene.cpp, Scene::sun_sum)
    enum { THUMB = 16 };
    struct Thumb { uint8_t lum[THUMB * THUMB]; };
    std::unordered_map<uint32_t, Thumb> thumbs;
    std::unordered_map<uint32_t, Target> targets;
    std::unordered_map<uint32_t, Ref<Shader>> shaders;      // by variant bits (a Shader resource: its set_code runs the preprocessor)
    // Godot builds a render pipeline the first time a shader variant is drawn with a vertex layout: 150 to 350 ms each on
    // Metal, on the main thread - level entries stopped for up to two seconds (islsm1).  The scene's variants seen in
    // earlier sessions are kept in user://rta_variants.txt and drawn once, as triangles of no area, when a world first
    // appears (warm_up), so that a level entry finds them built.
    std::unordered_set<uint32_t> warm_known;    // variants listed in the file (and added this session)
    bool warm_loaded = false;
    RID warm_scenario;
    std::vector<RID> warm_rids;                 // the warm-up's meshes, materials and instances, freed some frames later
    uint64_t warm_frame = 0;
    void warm_note(uint32_t variant);
    void warm_up(RID scenario);
    void warm_free();
    struct Material { RID rid; uint64_t last_used = 0; };
    std::unordered_map<std::string, Material> materials;
    std::vector<Pass*> all_passes;
    Target* shown = nullptr;
    int shown_rect[4] = {0, 0, 0, 0};
    uint64_t frames = 0;
    float last_aspect = 0;
    // figures
    uint64_t redraws = 0, passes_skipped = 0;
    bool scene_drops_blob(const rtag_frame& f, const rtag_draw& d) const;      // rta_scene.cpp: scene_take leaves this draw out
    bool tween_global = false;                      // redraw has set the global rta_tween: submit puts it back to 0
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
    bool rd = false;                                // Forward+ / Mobile: surfaces stored the other way up (setup)
    uint32_t draw_space = 0;                        // V_STORED / V_DECODE for the draw being added (submit sets it)
    bool stored_colours = true;
    float world_bias = 0.00002f;                    // scene mode: draws that do not write depth come this much nearer (clip space)

    Pass* make_pass(Target& target);
    void free_pass(Pass* pass);
    void size_target(Target& target);
    RID shader_for(uint32_t variant);
    RID material_for(const rtag_draw& draw, const Target& target, bool inverted, RID texture, bool texture_flipped, uint32_t extra = 0,
                     const rtag_draw* second = nullptr, RID second_texture = RID(), uint32_t er = 0);
    static bool blend_of(const rtag_draw& d, float& sc, float& sk, float& dc, float& dk, float& fix, int& blend_c, bool& subtract);
    void add_draw(Pass& pass, const rtag_frame& frame, const rtag_draw& draw, const Target& target, RID texture, bool texture_flipped, float order);
    void add_copy(Pass& pass, const rtag_draw& draw, const Target& target, const Target& source, RID texture, float order);
    RID place(Pass& pass, RID material, float order);
    RID place_mesh(Pass& pass, RID mesh, RID material, float order);
    RID instance_for(Pass& pass);
    RID mesh_for(Pass& pass);
    RID mesh_for_flat(Pass& pass, int primitive, const PackedByteArray& positions, const PackedByteArray& attributes, int count);
    uint64_t flat_reused = 0;
    // a big draw the CPU makes anew each frame (islsm1's sea: 1.26 million corners): the pool's mesh holds room for a little
    // more than it needs and is written again in place; the rest of the room holds triangles of no area
    int big_capacity(Pass& pass, int count) const;
    RID mesh_for_big(Pass& pass, const PackedByteArray& positions, const PackedByteArray& attributes, int capacity, const AABB& box);
    uint64_t big_reused = 0, big_made = 0;

    // ---- scene mode ----
    struct Scene;
    Scene* scene = nullptr;
    bool scene_mode = false;
    // Remastered's cut scenes (cinematic.gd, docs/issues/native-cutscenes.md): the game's own letterbox - opaque black
    // untextured rectangles of the 2-D layer across the picture's whole width at its top or bottom edge - left out,
    // so that the scene is seen to the window's edges (the host frames it itself)
    bool letterbox_off = false;
    Transform3D camera_shown;
    uint64_t letterbox_left_out = 0;
    bool is_letterbox(const rtag_frame& f, const rtag_draw& d, const Target& target) const;
public:
    int64_t get_letterbox_left_out() const { return (int64_t)letterbox_left_out; }
    Transform3D get_scene_camera() const { return camera_shown; }     // the camera of the picture drawn last (scene mode; a test aid)
private:
    Target* world_target();
    void scene_begin(const rtag_frame& frame);
    void scene_scan_sky(const rtag_frame& frame, const Target& world);
    bool scene_take(Pass& pass, const rtag_frame& frame, const rtag_draw& draw, const Target& target, RID texture, float order);
    void scene_end(const rtag_frame& frame);
    // the level's batches (rta_scene.cpp, Scene::batch_on)
    const std::vector<RID>* frame_texture_of = nullptr;     // submit(): this list's texture per draw
    bool batch_take(Pass& pass, const rtag_frame& frame, const rtag_draw& draw, const Target& target, RID texture, float order);
    void batch_flush(Pass& pass);
    static bool draw_commutes(const rtag_draw& d);
    void scene_learn_level(const rtag_draw& d, const rtag_scene_piece* pieces);
    void scene_caster(Pass& pass, RID mesh, RID material);
    void scene_release();
    static void add_surface_bytes(RID mesh, int primitive, const PackedByteArray& positions, const PackedByteArray& attributes, int count, bool normals = false, const AABB* box = nullptr, bool carry = false);
    std::vector<Pass*> last_order;                  // the passes the last submit rendered, in order (redraw)
    void scene_tween(double t);                     // rta_scene.cpp: the camera of a picture between game frames
    friend struct Scene;

    // ---- the fill (rta_fill.cpp) ----
    // the Elden Ring world layer (rta_world.cpp): per texture what it reads as, and the grass scattered on the level
    struct WorldTex {
        std::string name;                           // figure-palette, as the art pack names it ("" not named)
        uint8_t cls = 0, cls_b = 0;                 // what is drawn: the class, and a second one decided per pixel
        uint8_t guess = 0, guess_b = 0;             // what its texels read as
        uint8_t from_table = 0;                     // 1: by its name in the host's table, 2: its class remapped for the level
        float mean[3] = {0, 0, 0};
        float frac[12] = {0};
        float edge = 0, aniso = 0, opaque = 0;
        float coherence = 0;                        // how much its edges run one way (0 every way .. 1 one way: grain, boards)
        float sat = 0, contrast = 0, glint = 0;     // mean saturation; spread of brightness over its mean; share of glints
        float cool = 0;                             // share of its coloured texels that are blue-grey (180..260 degrees)
        uint64_t draws = 0;
        bool pending = false;                       // not read yet (at its first draw: world_scan)
        float tint[3] = {1, 1, 1};                  // the mean of the game's vertex light on it (1 = 128)
        float hot = 0;                              // share of glowing texels (bright orange to yellow: lava)
        bool lit_grey = false;                      // read as under a colourless light (its own left it in no family)
    };
    std::unordered_map<uint32_t, WorldTex> world_tex;
    std::unordered_map<uint32_t, uint64_t> world_seen_frame;
    std::unordered_map<std::string, int> world_overrides;
    int world_remap[16] = {-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1};
    bool world_on = false;
    float world_cobble_edge = 0.85f, world_wood_aniso = 1.45f, world_wood_edge = 0.25f, world_grass_density = 0.0f;
    float world_wood_coherence = 0.6f, world_metal_glint = 0.1f, world_metal_contrast = 0.85f;
    float world_grass_ground = 0.3f;              // the share of a piece's area that must face up for grass to grow on it
    float world_grass_clear = 10.0f;              // units around a point looked at for a painted feature (0: only under it)
    bool world_water_read = false;                // water likewise
    bool world_lava_read = false;                 // lava is read only on a level whose section says it has some
    float world_lava_hot = 0.25f;                 // share of its lava-coloured texels that glow (yellow to orange), for lava
    float world_ice_edge = 0.6f;                  // edges over which a pale blue texture is rock, not ice
    std::vector<rtag_texture_name> world_names;
    void world_classify(const rtag_texture& t, const rtag_texture_name* name);
    void world_read(uint32_t id, const float tint[3]);
    void world_apply(WorldTex& w);
    uint32_t world_code(uint32_t game_texture);
    void world_scan(const rtag_draw& d, const rtag_scene* tap);
    struct GrassPoint {
        float x, y, z, r, g, b, seed, nx, ny, nz;
        float room = 40.0f;                         // units to the nearest painted feature that is not grass (its texture's)
        float cell_room = 40.0f;                    // ... to the nearest other surface that is not grass, at or over its height
        uint32_t cell_gen = 0;                      // (ground_gen when cell_room was found)
        uint64_t piece = 0;                         // the level piece it grows on
    };
    struct WallCell { float lo = 1e30f, hi = -1e30f; };
    static constexpr float GRASS_CELL = 128.0f, WALL_CELL = 8.0f;
    std::unordered_set<uint64_t> grass_pieces;
    std::unordered_map<uint64_t, std::vector<GrassPoint>> grass_cells;
    std::unordered_map<uint64_t, WallCell> wall_cells;
    uint64_t grass_total = 0;
    std::unordered_map<uint64_t, uint64_t> grass_seen;      // per grass piece: the frame it was last drawn
    uint64_t grass_epoch = 0;                               // up by one when a grass piece comes back (the host gathers again)
    static constexpr uint64_t GRASS_GONE = 90;              // frames a piece may go undrawn before its tufts go
    bool grass_near_wall(float x, float y, float z) const;
    // grass is not grown under the level's painted decals (flower patches, paths: blended chunks drawn over the ground)
    static constexpr float DECAL_CELL = 4.0f;
    std::unordered_set<uint64_t> decal_pieces;
    std::unordered_map<uint64_t, WallCell> decal_cells;     // cells a decal covers, with the height span it covers them at
    std::unordered_map<uint32_t, bool> decal_textures;      // per texture: see-through somewhere (a decal's)
    void world_decal(const rtag_draw& d, const rtag_scene* tap);
    bool grass_under_decal(float x, float y, float z) const;
    // what else keeps the grass off: the level's surfaces that are not grass, facing up (a path laid on the ground, a kerb,
    // a floor: no tuft leans over them), and its see-through sheets (a lake's, a river's surface: nothing grows under them)
    static constexpr float GROUND_CELL = 8.0f;
    std::unordered_map<uint64_t, WallCell> ground_cells;
    std::unordered_map<uint64_t, WallCell> cover_cells;     // ... and where grass covers the ground (its upper surfaces)
    std::unordered_map<uint64_t, WallCell> sheet_cells;
    uint32_t ground_gen = 1;
    float grass_cell_room(float x, float y, float z) const;
    bool grass_under_sheet(float x, float y, float z) const;
    void world_mark(std::unordered_map<uint64_t, WallCell>& cells, const rtag_scene_full& a, const rtag_scene_full& b, const rtag_scene_full& c);
    // the rebuild's volumes (set_world_hide)
    struct WorldHide {
        float c[3] = {0, 0, 0}, h[3] = {0, 0, 0}, cos_yaw = 1, sin_yaw = 0;
        bool cylinder = false;
        int kinds = 1;
        float order = -1;
        uint64_t draws = 0;
        double rgb[3] = {0, 0, 0}, weight = 0;
    };
    std::vector<WorldHide> world_hide;
    std::unordered_map<uint64_t, int> world_hide_cache;     // per draw (its packets and where they lie): the volume holding it, -1 none
    uint64_t world_hide_frame = 0;
    int world_hidden(const rtag_draw& d, const rtag_scene* tap, float order);
    uint64_t world_hide_gen = 0;                            // changes with the volumes (kept meshes of models made again)
    bool world_hide_models = false;                         // a volume takes models' triangles
    int world_tri_hidden(const rtag_scene_full* corners, float order);     // the volume, -1 none
    void world_hide_colour(int volume, const rtag_draw& d);
    bool world_model_taken(const rtag_draw& d, const rtag_scene* tap);    // a model draw whose middle is in a volume for models
    std::string world_dump_path;
    void* world_dump_file = nullptr;
    uint64_t world_dump_frame = 0, world_dump_vertices = 0;
    void world_dump_take(const rtag_draw& d, const rtag_scene* tap, size_t index);

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
