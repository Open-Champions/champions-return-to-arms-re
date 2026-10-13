// rta_variant.h - the variants of the one shader (project/shaders/gs_draw.gdshaderinc), as bits.
#pragma once
#include <cstdint>

namespace rta_variant {

enum : uint32_t {
    V_BLEND_SUB = 1, V_DEPTH_ALWAYS = 2, V_DEPTH_INVERTED = 4, V_DEPTH_WRITE = 8, V_LINEAR = 16, V_REPEAT = 32,
    V_WORLD = 64,       // scene mode: the vertex is a world position under Godot's camera
    V_LIT = 128,        // ... and the surface takes Godot's lights and shadows on top of the game's own (baked) light
    V_CASTER = 256,     // ... a twin that is only drawn into Godot's shadow maps
};

}  // namespace rta_variant
