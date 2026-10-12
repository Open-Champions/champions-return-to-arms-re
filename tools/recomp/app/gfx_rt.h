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
// Figures for the report: frames built wide, calls of the screen clamp that were handed
// the 4:3 planes.
void figures(uint64_t& wide_frames, uint64_t& clamp_calls, uint64_t& marks);
// The game's display list: the units (of 8 bytes) the fullest frame took, and what a frame has.
void list_figures(uint32_t& most, uint32_t& room);

}  // namespace gfxrt
