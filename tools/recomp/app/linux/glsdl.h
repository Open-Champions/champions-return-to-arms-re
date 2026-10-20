// glsdl.h - OpenGL on Linux without Qt: the functions of the context SDL2 made, behind the
// two classes of Qt that render/backend_gl.cpp is written against (as app/win/wgl.h does
// for Windows; the list of names is that file's - a function the backend starts to use
// that is not in it is a compile error naming it: add it to both lists).
//
// backend_gl.cpp reaches OpenGL through QOpenGLContext::currentContext()->extraFunctions()
// and calls f->glSomething(...).  The Linux build puts this directory on its include path;
// the files QOpenGLContext and QOpenGLExtraFunctions here include this header.
#pragma once
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

namespace glsdl {

struct Functions {
#define RTA_GL_MEMBER(name) decltype(&::name) name = nullptr;
    RTA_GL_FUNCTIONS(RTA_GL_MEMBER)
#undef RTA_GL_MEMBER
};

// Fills the table from the context current on the calling thread (SDL_GL_GetProcAddress).
// `missing`: the names the driver does not have.
void load(std::string& missing);
Functions* functions();                 // after load(); null before

}  // namespace glsdl

// ---- what backend_gl.cpp includes from Qt ---------------------------------------------------
class QOpenGLExtraFunctions : public glsdl::Functions {};

class QOpenGLContext {
  public:
    static QOpenGLContext* currentContext();
    QOpenGLExtraFunctions* extraFunctions() const;
    unsigned defaultFramebufferObject() const { return 0; }
};
