// fpworld.h - the world for a camera that stands in it: what the game prepares for drawing
// when the frame is drawn through one of the views of fpview.h (chase, shoulder, first
// person) instead of the camera overhead it was made for.
// docs/issues/native-first-person-world.md says what is wrong from the ground, by cause,
// what each switch here does about it, and what was run.
//
// Everything here is on the draw side: it changes what is put into a frame's draw list, never
// what the simulation computes, and with the overhead view selected nothing of it runs.  Each
// part is a switch of its own:
//
//   world.clip     triangles that cross the near plane are cut there instead of dropped (the
//                  game's vertex programs drop a triangle with a corner off screen or behind
//                  the eye: holes in the floor at the feet).  render/gs.h, WorldView.
//   world.persp    level and model textures in perspective (the game interpolates texel
//                  coordinates across the screen: floors swim under a low camera).
//   world.objects  the object walk tests a grid cell as a box round the camera's height
//                  instead of from the camera's height down: objects stay when the view
//                  looks up.
//
//   world.ceilings a ceiling over the walked floor of a walled level, and
//   world.skirts   ground carried outward beyond the level's outer rim: generated at a level
//                  load from the level's own terrain (render/worldfill.h), published there for
//                  any renderer, and drawn by the OpenGL program in front of the frame's first
//                  level chunk.  auto (the default): ceilings in a level that clears to black,
//                  has no sky dome and is walled; skirts in a level without a sky dome.
//
// This header includes nothing of the runtime; fpworld.cpp is compiled with the runtime's
// flags (it supplies fn_<address> hooks listed under "the world from the ground" in
// tools/recomp/hle.txt).  Threads: setting() from any thread; the rest on the game's thread.
#pragma once
#include <cstdint>

namespace fpworld {

// "world" = views (the default: on while a view of fpview.h is drawn) | off | always;
// "world.<part>" = on | off, <part> one of clip, persp, objects; "world.ceilings", "world.skirts" =
// auto | on | off.  False when the key is not one.
bool setting(const char* key, const char* value);
// The settings as lines for the settings file.
const char* settings_text();

// Set the hook points.  After fpview::install(), before rta::run().
void install();

// One line of figures of the last draw pass and of the run so far (for "app world info").
const char* info();

}  // namespace fpworld
