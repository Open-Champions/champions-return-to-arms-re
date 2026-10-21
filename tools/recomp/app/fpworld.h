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
//   world.cells    textures of cells the game no longer keeps: a texture of a resident cell,
//                  once prepared, is copied to the runtime's shelf (rt_shelf), and a chunk of a
//                  cell that is not resident is drawn with that copy (the game keeps nine cells
//                  of 720 x 720 round one point; a view along the ground sees 1,800 units).  A chunk of a
//                  resident cell whose texture the game has not prepared (its texture thread's page pool
//                  keeps what the last frames drew; a view draws far more) is drawn with the copy too.
//   world.sweep    (off by default) a second stream focus: while the view is still and chunks in
//                  sight have no cell, the texture stream is pointed 1,300 units ahead for a while,
//                  so far cells are loaded, drawn and shelved.  Off: a turn right after a sweep
//                  showed holes near the feet (docs/issues/native-first-person-world.md 8.3).
//
//   (always)       a box of the level's chunk tree is tested 256 units wider on every side (some
//                  boxes do not cover their ground, which only a camera at eye height shows: a hole
//                  of a chunk's size near the feet); world-box-xy=N, world-box-z=N to change it.
//   (always)       a view's object walk leaves out object boxes beyond 650 units of the player
//                  while 140 or more of the animation decoder's 165 slots are held by root-motion
//                  tracks, and every box from 158 on: with all of them held animcache_alloc loops
//                  for ever (it hung `dismedal` in first person).
//
//   world.ceilings a ceiling over the walked floor of a walled level, and
//   world.skirts   ground carried outward beyond the level's outer rim: generated at a level
//                  load from the level's own terrain (render/worldfill.h), published there for
//                  any renderer, and drawn by the OpenGL program in front of the frame's first
//                  level chunk.  auto (the default): ceilings in a level that clears to black,
//                  has no sky dome and is walled; skirts in a level without a sky dome.
//   world.rims     a surface falling away under a floor's edge over nothing (render/worldfill.h,
//                  FILL_RIM), drawn as the skirt is, as a background.  auto: in a level WITH a sky
//                  dome (floating ground: storm2, torment2, fay2, pvpfire2).
//
// This header includes nothing of the runtime; fpworld.cpp is compiled with the runtime's
// flags (it supplies fn_<address> hooks listed under "the world from the ground" in
// tools/recomp/hle.txt).  Threads: setting() from any thread; the rest on the game's thread.
#pragma once
#include <cstdint>

namespace fpworld {

// "world" = views (the default: on while a view of fpview.h is drawn) | off | always;
// "world.<part>" = on | off, <part> one of clip, persp, objects, cells, sweep; "world.ceilings", "world.skirts", "world.rims" =
// auto | on | off.  False when the key is not one.
bool setting(const char* key, const char* value);
// The settings as lines for the settings file.
const char* settings_text();

// Set the hook points.  After fpview::install(), before rta::run().
void install();

// One line of figures of the last draw pass and of the run so far (for "app world info").
const char* info();

}  // namespace fpworld
