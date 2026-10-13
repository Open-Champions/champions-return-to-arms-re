// present_host.h - handing a finished picture to the window without the window's thread.
//
// macOS (present_mac.mm).  An OpenGL context that has a view may only be updated and, in
// practice, flushed from the main thread, and the main thread belongs to AppKit: its
// display cycle for the window stands for 100 ms and more while the window server is busy
// with other programs' windows (docs/issues/native-app.md 12.3).  So the window is given a
// Metal layer instead of an OpenGL view, the OpenGL context has no view at all (it can live
// on any thread), and the picture goes from one to the other through an IOSurface: OpenGL
// draws the window's picture into a texture that is the surface, Metal copies the surface
// into the layer's next drawable and presents it.  CAMetalLayer's nextDrawable and present
// may be called from any thread; nothing here waits for the main thread.
//
// The drawing thread never waits for the layer either: a presenter thread inside
// present_mac.mm asks the layer for its drawable (that call stands for up to a second when
// the display is asleep), and a picture that finds the two shared surfaces both still on
// their way is drawn and not shown.
//
// A host without this links nothing of it (the Windows program presents through WGL on
// its own window thread: app/win_main.cpp).
#pragma once
#include <string>
#include <vector>

namespace hostpresent {

struct Surface;

// Main thread, after the window is shown: `view` is the window's native view (QWindow::winId()
// of a window whose surface type is QSurface::MetalSurface).  Null when the view has no Metal
// layer or there is no Metal device (one line through `log` says which).
Surface* create(void* view, void (*log)(const std::string& line));

// Drawing thread, OpenGL context current: the framebuffer to draw the window's picture
// into, of exactly width x height pixels, FIRST ROW ON TOP (as Metal shows it).  0: none
// just now (both surfaces are still on their way to the glass): this picture is not shown.
unsigned begin(Surface* surface, int width, int height);

// Drawing thread, after the picture is in the framebuffer begin() gave and OpenGL has
// FINISHED it (glFinish): hand it to the presenter, which presents it at the display's next
// refresh.  Returns at once.  `now_ms` is the caller's clock now and
// `due_ms` the moment the picture is meant for on that clock (0: none): the system tells
// afterwards when the picture really was on the glass, and glass() hands that on.
bool show(Surface* surface, double now_ms, double due_ms);

// What the system said of pictures shown since the last call, oldest first: the moment
// each was meant for and the time it was on the glass (both on the caller's clock;
// on_glass_ms 0: it never was - the window was hidden, or the picture was dropped).
struct Glass { double due_ms, on_glass_ms; };
void glass(Surface* surface, std::vector<Glass>& out);

// Tests: what was last drawn for the window, as the layer is given it (rows from the top,
// four bytes a pixel: blue, green, red, alpha).
bool read(Surface* surface, std::vector<unsigned char>& bgra, int& width, int& height);

// Figures: pictures presented; how often the layer had no drawable (or one of another size:
// a resize under way); pictures not shown because the ones before were still on their way;
// the longest the layer kept the presenter waiting for a drawable.
void figures(Surface* surface, unsigned long long& presented, unsigned long long& refused, unsigned long long& skipped, double& longest_wait_ms);

}  // namespace hostpresent
