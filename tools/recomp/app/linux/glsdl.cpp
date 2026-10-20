// glsdl.cpp - see glsdl.h.
#include "glsdl.h"

#include <SDL.h>

namespace glsdl {

static QOpenGLExtraFunctions g_functions;
static bool g_loaded;
static QOpenGLContext g_context;

Functions* functions() { return g_loaded ? &g_functions : nullptr; }

void load(std::string& missing) {
#define RTA_GL_LOAD(name) \
    g_functions.name = (decltype(g_functions.name))SDL_GL_GetProcAddress(#name); \
    if (!g_functions.name) { missing += missing.empty() ? "" : " "; missing += #name; }
    RTA_GL_FUNCTIONS(RTA_GL_LOAD)
#undef RTA_GL_LOAD
    g_loaded = true;
}

}  // namespace glsdl

QOpenGLContext* QOpenGLContext::currentContext() { return glsdl::g_loaded ? &glsdl::g_context : nullptr; }
QOpenGLExtraFunctions* QOpenGLContext::extraFunctions() const { return &glsdl::g_functions; }
