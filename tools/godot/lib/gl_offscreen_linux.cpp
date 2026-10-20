// gl_offscreen_linux.cpp - see gl_offscreen.h; the Linux twin of gl_offscreen_mac.cpp.
//
// An OpenGL 4.1 core context with no window through EGL: the display of the desktop the
// host runs on (X11 or Wayland, through EGL_DEFAULT_DISPLAY), or - with no desktop (a
// server, a container) - Mesa's surfaceless platform.  The context is made current with no
// surface when the driver allows it (EGL_KHR_surfaceless_context), else on a small pbuffer;
// render/backend_gl.cpp draws into framebuffers of its own either way.
//
// libEGL is opened at run time (dlopen), so the library loads on a machine without it and
// only its own renderer is missing there.  backend_gl.cpp reaches OpenGL through Qt's two
// classes; tools/recomp/app/linux/glsdl.h stands in for them (the Linux program fills that
// table from SDL, glsdl.cpp); here the same table is filled from eglGetProcAddress, and
// this file supplies what glsdl.cpp would.
#include "gl_offscreen.h"

#include "glsdl.h"

#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <dlfcn.h>

#include <cstdio>
#include <cstdlib>

namespace glsdl {

static QOpenGLExtraFunctions g_functions;
static bool g_loaded;
static QOpenGLContext g_context;
static void* (*g_get_proc)(const char*);

Functions* functions() { return g_loaded ? &g_functions : nullptr; }

void load(std::string& missing) {
#define RTA_GL_LOAD(name) \
    g_functions.name = (decltype(g_functions.name))(g_get_proc ? g_get_proc(#name) : nullptr); \
    if (!g_functions.name) { missing += missing.empty() ? "" : " "; missing += #name; }
    RTA_GL_FUNCTIONS(RTA_GL_LOAD)
#undef RTA_GL_LOAD
    g_loaded = true;
}

}  // namespace glsdl

QOpenGLContext* QOpenGLContext::currentContext() { return glsdl::g_loaded ? &glsdl::g_context : nullptr; }
QOpenGLExtraFunctions* QOpenGLContext::extraFunctions() const { return &glsdl::g_functions; }

namespace gl_offscreen {

namespace {

struct Egl {
    void* lib = nullptr;
    PFNEGLGETPROCADDRESSPROC GetProcAddress = nullptr;
    EGLDisplay (*GetDisplay)(EGLNativeDisplayType) = nullptr;
    EGLBoolean (*Initialize)(EGLDisplay, EGLint*, EGLint*) = nullptr;
    EGLBoolean (*Terminate)(EGLDisplay) = nullptr;
    EGLBoolean (*BindAPI)(EGLenum) = nullptr;
    EGLBoolean (*ChooseConfig)(EGLDisplay, const EGLint*, EGLConfig*, EGLint, EGLint*) = nullptr;
    EGLContext (*CreateContext)(EGLDisplay, EGLConfig, EGLContext, const EGLint*) = nullptr;
    EGLSurface (*CreatePbufferSurface)(EGLDisplay, EGLConfig, const EGLint*) = nullptr;
    EGLBoolean (*MakeCurrent)(EGLDisplay, EGLSurface, EGLSurface, EGLContext) = nullptr;
    const char* (*QueryString)(EGLDisplay, EGLint) = nullptr;
    EGLint (*GetError)() = nullptr;
};

Egl g_egl;
EGLDisplay g_display = EGL_NO_DISPLAY;
EGLContext g_context = EGL_NO_CONTEXT;
EGLSurface g_surface = EGL_NO_SURFACE;
std::string g_platform;

bool has_word(const char* list, const char* word) {
    if (!list) return false;
    std::string all = std::string(" ") + list + " ";
    return all.find(std::string(" ") + word + " ") != std::string::npos;
}

bool open_egl(std::string& why) {
    if (g_egl.lib) return true;
    void* lib = dlopen("libEGL.so.1", RTLD_NOW | RTLD_LOCAL);
    if (!lib) lib = dlopen("libEGL.so", RTLD_NOW | RTLD_LOCAL);
    if (!lib) { why = std::string("no libEGL: ") + dlerror(); return false; }
#define RTA_EGL(field, name) g_egl.field = (decltype(g_egl.field))dlsym(lib, name); \
    if (!g_egl.field) { why = std::string("libEGL has no ") + name; dlclose(lib); return false; }
    RTA_EGL(GetProcAddress, "eglGetProcAddress")
    RTA_EGL(GetDisplay, "eglGetDisplay")
    RTA_EGL(Initialize, "eglInitialize")
    RTA_EGL(Terminate, "eglTerminate")
    RTA_EGL(BindAPI, "eglBindAPI")
    RTA_EGL(ChooseConfig, "eglChooseConfig")
    RTA_EGL(CreateContext, "eglCreateContext")
    RTA_EGL(CreatePbufferSurface, "eglCreatePbufferSurface")
    RTA_EGL(MakeCurrent, "eglMakeCurrent")
    RTA_EGL(QueryString, "eglQueryString")
    RTA_EGL(GetError, "eglGetError")
#undef RTA_EGL
    g_egl.lib = lib;
    return true;
}

std::string egl_error(const char* what) {
    char text[64];
    snprintf(text, sizeof text, " (EGL error 0x%04x)", g_egl.GetError ? (unsigned)g_egl.GetError() : 0u);
    return std::string(what) + text;
}

// A context on one display; false (and the display let go) when it cannot have one.
bool try_display(EGLDisplay display, const char* platform, std::string& why) {
    if (display == EGL_NO_DISPLAY) { why += std::string(why.empty() ? "" : "; ") + platform + ": no display"; return false; }
    EGLint major = 0, minor = 0;
    if (!g_egl.Initialize(display, &major, &minor)) { why += (why.empty() ? "" : "; ") + egl_error((std::string(platform) + ": eglInitialize").c_str()); return false; }
    const char* extensions = g_egl.QueryString(display, EGL_EXTENSIONS);
    bool surfaceless = has_word(extensions, "EGL_KHR_surfaceless_context");
    if (!g_egl.BindAPI(EGL_OPENGL_API)) {
        why += (why.empty() ? "" : "; ") + egl_error((std::string(platform) + ": no desktop OpenGL").c_str());
        g_egl.Terminate(display);
        return false;
    }
    const EGLint config_attributes[] = {
        EGL_SURFACE_TYPE, surfaceless ? 0 : EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE};
    EGLConfig config = nullptr;
    EGLint count = 0;
    if (!g_egl.ChooseConfig(display, config_attributes, &config, 1, &count) || count < 1) {
        why += (why.empty() ? "" : "; ") + egl_error((std::string(platform) + ": no configuration").c_str());
        g_egl.Terminate(display);
        return false;
    }
    const EGLint context_attributes[] = {
        EGL_CONTEXT_MAJOR_VERSION, 4, EGL_CONTEXT_MINOR_VERSION, 1,
        EGL_CONTEXT_OPENGL_PROFILE_MASK, EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT, EGL_NONE};
    EGLContext context = g_egl.CreateContext(display, config, EGL_NO_CONTEXT, context_attributes);
    if (context == EGL_NO_CONTEXT) {
        why += (why.empty() ? "" : "; ") + egl_error((std::string(platform) + ": no OpenGL 4.1 core context").c_str());
        g_egl.Terminate(display);
        return false;
    }
    EGLSurface surface = EGL_NO_SURFACE;
    if (!surfaceless) {
        const EGLint pbuffer_attributes[] = {EGL_WIDTH, 16, EGL_HEIGHT, 16, EGL_NONE};
        surface = g_egl.CreatePbufferSurface(display, config, pbuffer_attributes);
        if (surface == EGL_NO_SURFACE) {
            why += (why.empty() ? "" : "; ") + egl_error((std::string(platform) + ": no pbuffer").c_str());
            g_egl.Terminate(display);
            return false;
        }
    }
    g_display = display;
    g_context = context;
    g_surface = surface;
    g_platform = platform;
    return true;
}

}  // namespace

bool make_current(std::string& why) {
    if (g_context == EGL_NO_CONTEXT) {
        if (!open_egl(why)) return false;
        std::string tried;
        bool made = false;
        // the desktop's display first (the GPU the host's own window uses), then no desktop at all
        if (getenv("DISPLAY") || getenv("WAYLAND_DISPLAY"))
            made = try_display(g_egl.GetDisplay(EGL_DEFAULT_DISPLAY), "default display", tried);
        if (!made) {
            auto get_platform_display = (PFNEGLGETPLATFORMDISPLAYEXTPROC)g_egl.GetProcAddress("eglGetPlatformDisplayEXT");
            const char* client = g_egl.QueryString(EGL_NO_DISPLAY, EGL_EXTENSIONS);
            if (get_platform_display && has_word(client, "EGL_MESA_platform_surfaceless"))
                made = try_display(get_platform_display(EGL_PLATFORM_SURFACELESS_MESA, EGL_DEFAULT_DISPLAY, nullptr), "surfaceless", tried);
        }
        if (!made && !(getenv("DISPLAY") || getenv("WAYLAND_DISPLAY")))
            made = try_display(g_egl.GetDisplay(EGL_DEFAULT_DISPLAY), "default display", tried);
        if (!made) { why = tried.empty() ? "no EGL display" : tried; return false; }
        glsdl::g_get_proc = (void* (*)(const char*))g_egl.GetProcAddress;
    }
    if (!g_egl.MakeCurrent(g_display, g_surface, g_surface, g_context)) { why = egl_error("eglMakeCurrent"); return false; }
    if (!glsdl::g_loaded) {
        std::string missing;
        glsdl::load(missing);
        // as app/linux/linux_main.cpp: the table names a few functions newer than 4.1 that the backend does not call
        if (!missing.empty()) fprintf(stderr, "rtag: OpenGL functions this driver does not have: %s\n", missing.c_str());
        if (!glsdl::g_functions.glGetString || !glsdl::g_functions.glDrawArrays) { why = "the OpenGL driver lacks: " + missing; return false; }
    }
    return true;
}

std::string description() {
    auto get_string = glsdl::g_functions.glGetString;
    const char* version = get_string ? (const char*)get_string(GL_VERSION) : nullptr;
    const char* renderer = get_string ? (const char*)get_string(GL_RENDERER) : nullptr;
    return std::string("OpenGL ") + (version ? version : "?") + " on " + (renderer ? renderer : "?") + " (no window; EGL, " + g_platform + ")";
}

}  // namespace gl_offscreen
