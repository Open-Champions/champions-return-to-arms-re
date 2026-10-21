// gl_offscreen_win.cpp - see gl_offscreen.h; the Windows twin of gl_offscreen_mac.cpp.
//
// A hidden window of its own (never shown) gives WGL its device context; tools/recomp/app/win/wgl.cpp makes the
// OpenGL 4.1 (or 3.3) core context on it and fills the function table that render/backend_gl.cpp reaches through
// the two Qt-named classes of app/win/.  The backend draws into framebuffers of its own, so the window's own surface
// is never drawn into.  The context is made on the first call and made current on the calling thread after that.
#include "gl_offscreen.h"

#include "wgl.h"

#include <cstdio>

namespace gl_offscreen {

static HWND g_window;
static wgl::Context g_context;
static bool g_made;

bool make_current(std::string& why) {
    if (!g_made) {
        HINSTANCE instance = GetModuleHandleW(nullptr);
        WNDCLASSW wc = {};
        wc.style = CS_OWNDC;
        wc.lpfnWndProc = DefWindowProcW;
        wc.hInstance = instance;
        wc.lpszClassName = L"RtaGameOffscreenGL";
        RegisterClassW(&wc);                            // a second library start finds it registered: no harm
        g_window = CreateWindowExW(0, wc.lpszClassName, L"rta offscreen", WS_OVERLAPPEDWINDOW, 0, 0, 64, 64, nullptr, nullptr, instance, nullptr);
        if (!g_window) { why = "CreateWindowEx failed (error " + std::to_string((unsigned long)GetLastError()) + ")"; return false; }
        if (!wgl::create(g_window, g_context, why)) return false;
        g_made = true;
        if (!g_context.missing.empty()) fprintf(stderr, "rtag: the OpenGL driver lacks %s\n", g_context.missing.c_str());
        return true;
    }
    if (!wglMakeCurrent(g_context.dc, g_context.rc)) { why = "wglMakeCurrent failed (error " + std::to_string((unsigned long)GetLastError()) + ")"; return false; }
    return true;
}

std::string description() {
    return "OpenGL " + (g_context.version.empty() ? std::string("?") : g_context.version) + " on " +
           (g_context.renderer.empty() ? std::string("?") : g_context.renderer) + " (no window)";
}

}  // namespace gl_offscreen
