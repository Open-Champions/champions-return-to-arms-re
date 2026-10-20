// gfx_rt.h - the game-side half of the native picture options (gfx_rt.cpp), behind plain
// functions like app_rt.h: app_main.cpp includes nothing of the runtime.
//
// Widescreen is done where the game makes its view, not in the renderer: the horizontal
// scale of the three projection matrices is multiplied by k = (4/3) / aspect, and the
// aspect the frustum planes are built with is divided by it.  The game then draws a
// picture of the wide view into its unchanged 1280 x 448 buffer (anamorphic), everything
// it projects on the CPU lands in the same picture, and everything it culls by the view
// planes is culled by the wide ones.  The renderer shows the buffer at the wide aspect
// and puts the 2-D layer back into shape (render/layout.h); for that this file also says
// which draw function made which packets.
//
// Nothing here writes a word the simulation reads: docs/issues/native-graphics.md,
// "What the simulation sees".
#pragma once
#include <cstdint>

namespace gfxrt {

// Set the hook points of the runtime.  Before rta::run().
void install();
// The aspect ratio of the 3-D view, width / height; 4/3 is the game as it is.  From any
// thread; the game takes it at its next frame.
void set_aspect(double aspect);
// The marks that say which draw function made which packets are sent at 4:3 as well (they are only needed for the
// wide picture's layout otherwise): for a renderer that is asked to leave the game's own HUD layer out (Gs::hide_edge).
// From any thread; takes effect with the next frame's draw functions.
void set_hud_marks(bool on);
// Figures for the report: frames built wide, calls of the screen clamp that were handed
// the 4:3 planes.
void figures(uint64_t& wide_frames, uint64_t& clamp_calls, uint64_t& marks);
// The game's display list: the units (of 8 bytes) the fullest frame took, and what a frame has.
void list_figures(uint32_t& most, uint32_t& room);
// For app/fpview.cpp (the view modes).  The four arguments of the game's last call of
// camera_setProjection (fov, aspect, fov2, v) as raw floats; and a near and far distance
// that mat4_setProjection x 3 are given in place of the game's 18 and 1800 while a view of
// its own is in place (0, 0 = the game's).  Game thread only.
void projection_args(uint32_t out[4]);
void set_depth_range(float near_plane, float far_plane);
// The aspect (width / height) the 3-D view of the frame being built has: the game's 1.33, made wider by
// the widescreen factor.  Game thread only.
float view_aspect();
// For app/fpworld.cpp (the world for a camera inside it).  world_drawObjects 0x14b168 is this
// file's hook (the marks for names over heads); when this pointer is set the walk is handed to
// it, with the original to call.  Game thread only.
struct ObjectWalk { void (*run)(void* ctx, void (*original)(void* ctx)); };
extern ObjectWalk object_walk;

}  // namespace gfxrt
