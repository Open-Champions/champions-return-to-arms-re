// gl_offscreen.h - an OpenGL 4.1 core context with no window, for the library's own
// renderer (tools/recomp/render/backend_gl.cpp draws into its own surfaces and the
// picture is read back).  gl_offscreen_mac.cpp: CGL.  Windows would make a hidden window
// and a WGL context as tools/recomp/app/win/wgl.cpp does.
#pragma once
#include <string>

namespace gl_offscreen {

// Makes the context on first call and makes it current on the calling thread.
bool make_current(std::string& why);
std::string description();              // version and renderer, after make_current

}  // namespace gl_offscreen
