// wgl.cpp - see wgl.h.  NOT RUN.
#include "wgl.h"

#include <cstdio>
#include <cstring>

namespace wgl {

static QOpenGLExtraFunctions g_functions;
static bool g_loaded;
static QOpenGLContext g_context;

Functions* functions() { return g_loaded ? &g_functions : nullptr; }

// A function of OpenGL 1.1 is exported by opengl32.dll; everything newer comes from the
// driver through wglGetProcAddress, which answers 0 (or 1, 2, 3, -1) for the old ones.
static void* lookup(const char* name) {
    void* p = (void*)wglGetProcAddress(name);
    if (p == nullptr || p == (void*)1 || p == (void*)2 || p == (void*)3 || p == (void*)-1) {
        static HMODULE module = LoadLibraryA("opengl32.dll");
        p = module ? (void*)GetProcAddress(module, name) : nullptr;
    }
    return p;
}

typedef HGLRC(WINAPI* CreateContextAttribs)(HDC, HGLRC, const int*);
typedef BOOL(WINAPI* SwapInterval)(int);
static SwapInterval g_swap_interval;

bool create(HWND window, Context& out, std::string& error) {
    out.dc = GetDC(window);                             // the window class has CS_OWNDC: kept for good
    PIXELFORMATDESCRIPTOR pfd;
    memset(&pfd, 0, sizeof pfd);
    pfd.nSize = sizeof pfd;
    pfd.nVersion = 1;
    pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
    pfd.iPixelType = PFD_TYPE_RGBA;
    pfd.cColorBits = 32;
    pfd.cAlphaBits = 8;
    pfd.cDepthBits = 0;                                 // the backend draws into its own targets
    pfd.iLayerType = PFD_MAIN_PLANE;
    int format = ChoosePixelFormat(out.dc, &pfd);
    if (!format || !SetPixelFormat(out.dc, format, &pfd)) { error = "no RGBA pixel format for the window"; return false; }
    // An old-style context first: only with one current does the driver say how to make a core one.
    HGLRC old = wglCreateContext(out.dc);
    if (!old || !wglMakeCurrent(out.dc, old)) { error = "no OpenGL context at all (is a graphics driver installed?)"; return false; }
    CreateContextAttribs create_attribs = (CreateContextAttribs)(void*)wglGetProcAddress("wglCreateContextAttribsARB");
    if (!create_attribs) {
        const char* v = (const char*)glGetString(GL_VERSION);
        error = std::string("the OpenGL driver cannot make a core profile context (it says: ") + (v ? v : "nothing") + ")";
        wglMakeCurrent(nullptr, nullptr);
        wglDeleteContext(old);
        return false;
    }
    static const int versions[][2] = {{4, 1}, {3, 3}};
    for (auto& v : versions) {
        const int attribs[] = {0x2091 /* WGL_CONTEXT_MAJOR_VERSION_ARB */, v[0], 0x2092 /* MINOR */, v[1],
                               0x9126 /* WGL_CONTEXT_PROFILE_MASK_ARB */, 0x0001 /* CORE_PROFILE_BIT */, 0};
        if ((out.rc = create_attribs(out.dc, nullptr, attribs))) break;
    }
    wglMakeCurrent(nullptr, nullptr);
    wglDeleteContext(old);
    if (!out.rc || !wglMakeCurrent(out.dc, out.rc)) { error = "the OpenGL driver has no 4.1 or 3.3 core profile context"; return false; }
#define RTA_GL_LOAD(name) \
    g_functions.name = (decltype(g_functions.name))lookup(#name); \
    if (!g_functions.name) { out.missing += out.missing.empty() ? "" : " "; out.missing += #name; }
    RTA_GL_FUNCTIONS(RTA_GL_LOAD)
#undef RTA_GL_LOAD
    g_loaded = true;
    g_swap_interval = (SwapInterval)(void*)wglGetProcAddress("wglSwapIntervalEXT");
    if (g_functions.glGetString) {
        const char* v = (const char*)g_functions.glGetString(GL_VERSION);
        const char* r = (const char*)g_functions.glGetString(GL_RENDERER);
        out.version = v ? v : "";
        out.renderer = r ? r : "";
    }
    if (g_functions.glGetIntegerv) {
        g_functions.glGetIntegerv(GL_MAJOR_VERSION, &out.major);
        g_functions.glGetIntegerv(GL_MINOR_VERSION, &out.minor);
    }
    return true;
}

bool swap_interval(int interval) { return g_swap_interval && g_swap_interval(interval); }

}  // namespace wgl

QOpenGLContext* QOpenGLContext::currentContext() { return wgl::g_loaded ? &wgl::g_context : nullptr; }
QOpenGLExtraFunctions* QOpenGLContext::extraFunctions() const { return &wgl::g_functions; }
