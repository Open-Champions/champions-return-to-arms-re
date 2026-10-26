// rta_remaster.h - RtaRemaster: the game's own figures remastered on the player's machine (look.remaster_models).
//
// Nothing of a model is stored with the program: every figure is taken from the frame the game draws (the skeleton
// stream of tools/godot/lib/skeleton_export.h - each skinned object's bind-pose packets, their joints and weights, the
// corners with their texture coordinates) and baked here, once per model, into a smoother mesh of the same shape:
//
//   geometry   the object's packets welded into one surface (by position: a seam between two packets is one edge), the
//              triangles split 1 -> 4 per level by Loop's rules (a vertex: (1 - n b) v + b sum of its neighbours; an edge:
//              3/8 of its ends and 1/8 of the two opposite corners).  An edge is a CREASE - kept sharp, subdivided as a
//              curve of its own (1/8 3/4 1/8, edge points the midpoint) - where the game's own normals part across it by
//              more than `crease` (a cosine: the model's hard edges), on the boundary and where more than two triangles
//              meet; three creases at a vertex make it a corner (not moved).  Loop's surface lies inside its control mesh
//              (a thin arm comes out thinner): the control points are fitted `fit` times so that the subdivided surface
//              passes through the game's own vertices again (p0 += keep (game - S^N p0)) - the proportions stay the game's.
//              Skin weights are subdivided with the same weights as the positions (joints merged, the four largest kept);
//              texture coordinates linearly per triangle (the texture stays where it was on the model); normals from the
//              new surface, averaged only across faces whose game normals agree (hard edges stay hard).
//   drawing    the baked mesh is in the bind pose: a RenderingServer skeleton holds the frame's skin matrices (the very
//              matrices the game's vertex program used: rtag_skeleton::skin), so the body moves exactly as the game's.
//   materials  derive_maps: from an albedo (the art pack's 4x picture, or the game's own) a height (luminance, filtered
//              edge-aware so that a painted edge stays one and noise goes, the broad shading taken off), its normal map,
//              and per texel a class - skin, leather, metal, cloth - by colour and local contrast, giving roughness,
//              metalness and a cavity term (ORM: r occlusion, g roughness, b metal).
//
// model_remaster.gd drives it; nothing here reaches the game (it only reads the frame).
#pragma once
#include "rta_machine.h"

#include <godot_cpp/classes/image.hpp>
#include <godot_cpp/classes/ref_counted.hpp>
#include <godot_cpp/variant/array.hpp>
#include <godot_cpp/variant/dictionary.hpp>
#include <godot_cpp/variant/packed_int32_array.hpp>
#include <godot_cpp/variant/packed_vector4_array.hpp>
#include <godot_cpp/variant/rid.hpp>
#include <godot_cpp/variant/string.hpp>

#include <atomic>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

namespace godot {

class RtaRemaster : public RefCounted {
    GDCLASS(RtaRemaster, RefCounted)
  public:
    ~RtaRemaster();
    // The skinned figures of the machine's current frame, one per object: {figures: [{object, skeleton, state, joints,
    // key, pieces, piece_keys, root, corners}], players: [{slot, state, character_class}]}
    Dictionary scan(const Ref<RtaMachine>& machine);
    // Bake one object of the current frame (its data is copied now; the work runs on a thread of its own).  options:
    // levels (1..3), crease (cosine), fit (iterations), keep (0..1), max_tris (the finest level's triangles at most: a
    // dense model is split fewer times).  Level 0 of the result is the game's own mesh (for far away).  Returns the model's key ("" when not found).
    String bake_start(const Ref<RtaMachine>& machine, int64_t object, const Dictionary& options);
    // {} while running; {"failed": why}; else {"levels": [per level {"surfaces": [arrays of Mesh.ARRAY_*], ...}],
    // "piece_keys": PackedStringArray (surface order), "stats": String}
    Dictionary bake_take(const String& key);
    int64_t bakes_running() const;
    // per packet surfaces (Mesh arrays, as bake_take gives them) gathered into `count` surfaces: packet i into groups[i]
    // (the packets drawn with one material: a draw call each instead of one a packet)
    Array merge(const Array& surfaces, const PackedInt32Array& groups, int64_t count) const;
    // The skin matrices of skeleton `skeleton` (an index into this frame's skeletons) into a RenderingServer skeleton
    // (its data allocated as needed); the matrices before are kept for tween
    bool pose(const Ref<RtaMachine>& machine, int64_t skeleton, const RID& rid);
    // between two game frames (RtaDrawer.redraw): T game frames past the last pose (T < 0: between the last two)
    void tween(const RID& rid, double t);
    void forget(const RID& rid);
    // The game's own light on a figure this frame (its vertex program's colours against its normals), as nine spherical
    // harmonic coefficients (rgb in x y z; 1.0 = the game's 128); [] when too few corners
    PackedVector4Array light_sh(const Ref<RtaMachine>& machine, const PackedInt32Array& pieces);
    // An albedo's normal and ORM maps (above).  options: strength (bump), scale (picture pixels per game texel),
    // class ("" / auto | skin | cloth | leather | metal: every texel that class), metal (0..1), rough (multiplier)
    Dictionary derive_maps(const Ref<Image>& albedo, const Dictionary& options) const;

  protected:
    static void _bind_methods();

  private:
    struct Job;
    std::unordered_map<std::string, std::shared_ptr<Job>> jobs;
    std::vector<std::thread> threads;
    struct Pose { int n = 0; std::vector<float> before, now; };
    std::unordered_map<uint64_t, Pose> poses;
    std::unordered_map<uint64_t, String> hex_cache;     // a packet's key as text, made once
};

}  // namespace godot
