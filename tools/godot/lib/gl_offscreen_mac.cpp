// gl_offscreen_mac.cpp - see gl_offscreen.h.
#define GL_SILENCE_DEPRECATION
#include "gl_offscreen.h"

#include <OpenGL/OpenGL.h>
#include <OpenGL/gl3.h>

namespace gl_offscreen {

static CGLContextObj g_context;

bool make_current(std::string& why) {
    if (!g_context) {
        const CGLPixelFormatAttribute attributes[] = {
            kCGLPFAOpenGLProfile, (CGLPixelFormatAttribute)kCGLOGLPVersion_GL4_Core,
            kCGLPFAAccelerated, kCGLPFAColorSize, (CGLPixelFormatAttribute)24, kCGLPFAAlphaSize, (CGLPixelFormatAttribute)8,
            (CGLPixelFormatAttribute)0};
        CGLPixelFormatObj format = nullptr;
        GLint count = 0;
        CGLError error = CGLChoosePixelFormat(attributes, &format, &count);
        if (error != kCGLNoError || !format) { why = std::string("CGLChoosePixelFormat: ") + CGLErrorString(error); return false; }
        error = CGLCreateContext(format, nullptr, &g_context);
        CGLDestroyPixelFormat(format);
        if (error != kCGLNoError || !g_context) { why = std::string("CGLCreateContext: ") + CGLErrorString(error); g_context = nullptr; return false; }
    }
    CGLError error = CGLSetCurrentContext(g_context);
    if (error != kCGLNoError) { why = std::string("CGLSetCurrentContext: ") + CGLErrorString(error); return false; }
    return true;
}

std::string description() {
    const char* version = (const char*)glGetString(GL_VERSION);
    const char* renderer = (const char*)glGetString(GL_RENDERER);
    return std::string("OpenGL ") + (version ? version : "?") + " on " + (renderer ? renderer : "?") + " (no window)";
}

}  // namespace gl_offscreen
