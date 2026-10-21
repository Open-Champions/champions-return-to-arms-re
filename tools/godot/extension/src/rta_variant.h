// rta_variant.h - the variants of the one shader (project/shaders/gs_draw.gdshaderinc), as bits.
#pragma once
#include <cstdint>

namespace rta_variant {

enum : uint32_t {
    V_BLEND_SUB = 1, V_DEPTH_ALWAYS = 2, V_DEPTH_INVERTED = 4, V_DEPTH_WRITE = 8, V_LINEAR = 16, V_REPEAT = 32,
    V_WORLD = 64,       // scene mode: the vertex is a world position under Godot's camera
    V_LIT = 128,        // ... and the surface takes Godot's lights and shadows on top of the game's own (baked) light
    V_CASTER = 256,     // ... a twin that is only drawn into Godot's shadow maps
    V_NORMALS = 512,    // ... the mesh carries the game's own normals (world space, in CUSTOM1)
    V_NOFOG = 1024,     // ... the haze leaves it alone (the game's sky dome)
    V_NEARFADE = 2048,  // ... it fades as it comes up to the eye (camera-facing sprites placed in the world by their depth)
    V_MODEL = 4096,     // ... a solid model (a character, a creature, a prop): per-pixel form light, rim light, sharper texture
    V_CONTACT = 8192,   // ... a solid piece of the level: darkened under the characters standing on it (contact shadows)
    // Forward+ / Mobile blend in linear light, the GS in stored values: a surface with no 3-D scene in it is drawn with
    // the stored values themselves as the colour (blended as the GS blends: a translucent overlay, an additive glow), and
    // what reads it decodes the sRGB curve Godot puts on it (docs/issues/native-godot.md, ninth round)
    V_STORED = 16384,   // the colour is written as stored values (the pass is a stored-space one)
    V_DECODE = 32768,   // the texture is such a surface: its sRGB curve is taken off when it is read
};

}  // namespace rta_variant
