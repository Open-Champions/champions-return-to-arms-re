// wgl.h - OpenGL on Windows without Qt: the context (WGL), the functions, and the two
// classes of Qt that render/backend_gl.cpp is written against.
//
// backend_gl.cpp reaches OpenGL through QOpenGLContext::currentContext()->extraFunctions()
// and calls f->glSomething(...).  On Windows the build puts this directory on its include
// path; the files QOpenGLContext and QOpenGLExtraFunctions here include this header, and
// the two classes below give the backend the same expressions over a table of function
// pointers taken from the driver.  backend_gl.cpp itself is not changed.
//
// A function the backend starts to use that is not in the list below is a compile error
// naming it ("no member named glX"): add the name to RTA_GL_FUNCTIONS.  Its type comes
// from the prototype in <GL/glcorearb.h>, so the list is names only.
//
// Written and compiled on a Mac with a cross-compiler; NOT RUN (docs/issues/native-windows.md).
#pragma once
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#ifndef GL_GLEXT_PROTOTYPES
#define GL_GLEXT_PROTOTYPES             // the prototypes are only used for their types
#endif
#include <GL/glcorearb.h>

#include <string>

#define RTA_GL_FUNCTIONS(F) \
    F(glActiveTexture) F(glAttachShader) F(glBindAttribLocation) F(glBindBuffer) F(glBindBufferBase) F(glBindBufferRange) \
    F(glBindFramebuffer) F(glBindRenderbuffer) F(glBindSampler) F(glBindTexture) F(glBindVertexArray) F(glBlendColor) \
    F(glBlendEquation) F(glBlendEquationSeparate) F(glBlendFunc) F(glBlendFuncSeparate) F(glBlitFramebuffer) F(glBufferData) \
    F(glBufferSubData) F(glCheckFramebufferStatus) F(glClear) F(glClearBufferfi) F(glClearBufferfv) F(glClearBufferiv) \
    F(glClearBufferuiv) F(glClearColor) F(glClearDepthf) F(glClearStencil) F(glColorMask) F(glCompileShader) \
    F(glCopyTexImage2D) F(glCopyTexSubImage2D) F(glCreateProgram) F(glCreateShader) F(glCullFace) F(glDeleteBuffers) \
    F(glDeleteFramebuffers) F(glDeleteProgram) F(glDeleteRenderbuffers) F(glDeleteSamplers) F(glDeleteShader) \
    F(glDeleteTextures) F(glDeleteVertexArrays) F(glDepthFunc) F(glDepthMask) F(glDepthRangef) F(glDetachShader) \
    F(glDisable) F(glDisableVertexAttribArray) F(glDrawArrays) F(glDrawArraysInstanced) F(glDrawBuffers) F(glDrawElements) \
    F(glDrawElementsInstanced) F(glEnable) F(glEnableVertexAttribArray) F(glFinish) F(glFlush) F(glFramebufferRenderbuffer) \
    F(glFramebufferTexture2D) F(glFramebufferTextureLayer) F(glFrontFace) F(glGenBuffers) F(glGenFramebuffers) \
    F(glGenRenderbuffers) F(glGenSamplers) F(glGenTextures) F(glGenVertexArrays) F(glGenerateMipmap) F(glGetAttribLocation) \
    F(glGetError) F(glGetFloatv) F(glGetIntegerv) F(glGetProgramInfoLog) F(glGetProgramiv) F(glGetShaderInfoLog) \
    F(glGetShaderiv) F(glGetString) F(glGetStringi) F(glGetUniformLocation) F(glInvalidateFramebuffer) F(glIsEnabled) \
    F(glLineWidth) F(glLinkProgram) F(glMapBufferRange) F(glPixelStorei) F(glPolygonOffset) F(glReadBuffer) F(glReadPixels) \
    F(glRenderbufferStorage) F(glRenderbufferStorageMultisample) F(glSamplerParameterf) F(glSamplerParameteri) F(glScissor) \
    F(glShaderSource) F(glStencilFunc) F(glStencilFuncSeparate) F(glStencilMask) F(glStencilMaskSeparate) F(glStencilOp) \
    F(glStencilOpSeparate) F(glTexImage2D) F(glTexImage3D) F(glTexParameterf) F(glTexParameteri) F(glTexStorage2D) \
    F(glTexSubImage2D) F(glTexSubImage3D) F(glUniform1f) F(glUniform1fv) F(glUniform1i) F(glUniform1iv) F(glUniform1ui) \
    F(glUniform2f) F(glUniform2fv) F(glUniform2i) F(glUniform2iv) F(glUniform3f) F(glUniform3fv) F(glUniform3i) F(glUniform4f) \
    F(glUniform4fv) F(glUniform4i) F(glUniform4iv) F(glUniformMatrix3fv) F(glUniformMatrix4fv) F(glUnmapBuffer) \
    F(glUseProgram) F(glValidateProgram) F(glVertexAttrib4f) F(glVertexAttribDivisor) F(glVertexAttribIPointer) \
    F(glVertexAttribPointer) F(glViewport)

namespace wgl {

struct Functions {
#define RTA_GL_MEMBER(name) decltype(&::name) name = nullptr;
    RTA_GL_FUNCTIONS(RTA_GL_MEMBER)
#undef RTA_GL_MEMBER
};

struct Context {
    HDC dc = nullptr;
    HGLRC rc = nullptr;
    int major = 0, minor = 0;
    std::string version, renderer;      // GL_VERSION, GL_RENDERER
    std::string missing;                // functions of the list the driver does not have
};

// Gives the window a double-buffered RGBA pixel format, makes an OpenGL 4.1 core context
// (3.3 core when the driver has no 4.1) current on the calling thread and fills the
// function table.  False with `error` set when there is no such context.
bool create(HWND window, Context& out, std::string& error);
// 1: SwapBuffers waits for the display; 0: it does not.  False when the driver cannot be told.
bool swap_interval(int interval);
Functions* functions();                 // of the context made by create(); null before

}  // namespace wgl

// ---- what backend_gl.cpp includes from Qt ---------------------------------------------------
class QOpenGLExtraFunctions : public wgl::Functions {};

class QOpenGLContext {
  public:
    static QOpenGLContext* currentContext();
    QOpenGLExtraFunctions* extraFunctions() const;
    unsigned defaultFramebufferObject() const { return 0; }
};
