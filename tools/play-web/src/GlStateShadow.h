#pragma once

// play-web: GL state remembered on this side, so that a call which would set what is set
// already is not made.
//
// Play!'s OpenGL handler sets a group of state again whenever the game writes the
// register behind it, changed or not, and this game writes them all before nearly every
// draw: about 28,700 GL calls a frame in the first level, 7,800 of them glTexParameteri.
// A desktop driver drops a redundant call in a few nanoseconds. In a browser every call
// is checked by the page's WebGL layer, packed into a command buffer, and unpacked,
// checked again and passed on by the browser's GPU process: it costs whether it changes
// anything or not.
//
// Included at the end of GSH_OpenGL.h, so everything that draws for the handler goes
// through it (the handler's three source files and the web front end). It is only
// active in the browser build. The names of GL objects are never given out twice by
// Emscripten's GL layer, so a remembered name cannot come to mean another object.
// One GL context, used from one thread: the state is one object.

#ifdef __EMSCRIPTEN__

#include <cstring>
#include <vector>

namespace RtaGl
{
	const GLuint UNKNOWN = 0xFFFFFFFF;

	struct TextureParams
	{
		GLint minFilter = -1;
		GLint magFilter = -1;
		GLint wrapS = -1;
		GLint wrapT = -1;
		GLint swizzleR = -1;
	};

	struct State
	{
		GLenum activeTexture = UNKNOWN;
		GLuint texture2d[4] = {UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN};
		std::vector<TextureParams> textureParams;
		GLuint arrayBuffer = UNKNOWN;
		GLuint uniformBuffer = UNKNOWN;
		GLuint uniformBufferBase[4] = {UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN};
		GLuint vertexArray = UNKNOWN;
		GLuint program = UNKNOWN;
		GLuint drawFramebuffer = UNKNOWN;
		GLuint readFramebuffer = UNKNOWN;
		int blend = -1, depthTest = -1, scissorTest = -1;
		GLint viewport[4] = {-1, -1, -1, -1};
		GLint scissor[4] = {-1, -1, -1, -1};
		int colorMask = -1;
		int depthMask = -1;
		GLenum depthFunc = UNKNOWN;
		GLenum blendFunc[4] = {UNKNOWN, UNKNOWN, UNKNOWN, UNKNOWN};
		GLenum blendEquation[2] = {UNKNOWN, UNKNOWN};
		GLfloat blendColor[4] = {-1, -1, -1, -1};
		// calls made and calls left out, for the figures
		unsigned int made = 0, skipped = 0;
	};
	inline State g_state;

	inline bool Skip(bool same)
	{
		if(same)
			g_state.skipped++;
		else
			g_state.made++;
		return same;
	}

	inline void ActiveTexture(GLenum unit)
	{
		if(Skip(g_state.activeTexture == unit)) return;
		g_state.activeTexture = unit;
		glActiveTexture(unit);
	}

	inline void BindTexture(GLenum target, GLuint texture)
	{
		unsigned int unit = g_state.activeTexture - GL_TEXTURE0;
		if(target != GL_TEXTURE_2D || unit >= 4)
		{
			glBindTexture(target, texture);
			return;
		}
		if(Skip(g_state.texture2d[unit] == texture)) return;
		g_state.texture2d[unit] = texture;
		glBindTexture(target, texture);
	}

	inline void TexParameteri(GLenum target, GLenum name, GLint value)
	{
		unsigned int unit = g_state.activeTexture - GL_TEXTURE0;
		GLuint texture = (target == GL_TEXTURE_2D && unit < 4) ? g_state.texture2d[unit] : UNKNOWN;
		if(texture == UNKNOWN || texture == 0 || texture > 0x100000)
		{
			glTexParameteri(target, name, value);
			return;
		}
		if(texture >= g_state.textureParams.size()) g_state.textureParams.resize(texture + 256);
		auto& params = g_state.textureParams[texture];
		GLint* held = nullptr;
		switch(name)
		{
		case GL_TEXTURE_MIN_FILTER:
			held = &params.minFilter;
			break;
		case GL_TEXTURE_MAG_FILTER:
			held = &params.magFilter;
			break;
		case GL_TEXTURE_WRAP_S:
			held = &params.wrapS;
			break;
		case GL_TEXTURE_WRAP_T:
			held = &params.wrapT;
			break;
		case GL_TEXTURE_SWIZZLE_R:
			held = &params.swizzleR;
			break;
		default:
			glTexParameteri(target, name, value);
			return;
		}
		if(Skip(*held == value)) return;
		*held = value;
		glTexParameteri(target, name, value);
	}

	inline void BindBuffer(GLenum target, GLuint buffer)
	{
		GLuint* held = (target == GL_ARRAY_BUFFER) ? &g_state.arrayBuffer : ((target == GL_UNIFORM_BUFFER) ? &g_state.uniformBuffer : nullptr);
		if(!held)
		{
			glBindBuffer(target, buffer);
			return;
		}
		if(Skip(*held == buffer)) return;
		*held = buffer;
		glBindBuffer(target, buffer);
	}

	inline void BindBufferBase(GLenum target, GLuint index, GLuint buffer)
	{
		if(target != GL_UNIFORM_BUFFER || index >= 4)
		{
			glBindBufferBase(target, index, buffer);
			return;
		}
		// The call also sets the general binding point. When the indexed point holds the
		// buffer already the call is left out and the general point stays what it is, in
		// GL and here alike: nothing in the handler takes the general point from this
		// call (it binds before every glBufferData).
		if(Skip(g_state.uniformBufferBase[index] == buffer)) return;
		g_state.uniformBufferBase[index] = buffer;
		g_state.uniformBuffer = buffer;
		glBindBufferBase(target, index, buffer);
	}

	inline void BindVertexArray(GLuint vertexArray)
	{
		if(Skip(g_state.vertexArray == vertexArray)) return;
		g_state.vertexArray = vertexArray;
		glBindVertexArray(vertexArray);
	}

	inline void UseProgram(GLuint program)
	{
		if(Skip(g_state.program == program)) return;
		g_state.program = program;
		glUseProgram(program);
	}

	inline void BindFramebuffer(GLenum target, GLuint framebuffer)
	{
		bool draw = (target == GL_FRAMEBUFFER || target == GL_DRAW_FRAMEBUFFER);
		bool read = (target == GL_FRAMEBUFFER || target == GL_READ_FRAMEBUFFER);
		if(Skip((!draw || g_state.drawFramebuffer == framebuffer) && (!read || g_state.readFramebuffer == framebuffer))) return;
		if(draw) g_state.drawFramebuffer = framebuffer;
		if(read) g_state.readFramebuffer = framebuffer;
		glBindFramebuffer(target, framebuffer);
	}

	inline void GetIntegerv(GLenum name, GLint* value)
	{
		if(name == GL_DRAW_FRAMEBUFFER_BINDING && g_state.drawFramebuffer != UNKNOWN)
		{
			g_state.skipped++;
			*value = static_cast<GLint>(g_state.drawFramebuffer);
			return;
		}
		glGetIntegerv(name, value);
	}

	inline int* Capability(GLenum capability)
	{
		switch(capability)
		{
		case GL_BLEND:
			return &g_state.blend;
		case GL_DEPTH_TEST:
			return &g_state.depthTest;
		case GL_SCISSOR_TEST:
			return &g_state.scissorTest;
		default:
			return nullptr;
		}
	}

	inline void Enable(GLenum capability)
	{
		int* held = Capability(capability);
		if(held)
		{
			if(Skip(*held == 1)) return;
			*held = 1;
		}
		glEnable(capability);
	}

	inline void Disable(GLenum capability)
	{
		int* held = Capability(capability);
		if(held)
		{
			if(Skip(*held == 0)) return;
			*held = 0;
		}
		glDisable(capability);
	}

	inline void Viewport(GLint x, GLint y, GLsizei width, GLsizei height)
	{
		GLint now[4] = {x, y, width, height};
		if(Skip(memcmp(now, g_state.viewport, sizeof(now)) == 0)) return;
		memcpy(g_state.viewport, now, sizeof(now));
		glViewport(x, y, width, height);
	}

	inline void Scissor(GLint x, GLint y, GLsizei width, GLsizei height)
	{
		GLint now[4] = {x, y, width, height};
		if(Skip(memcmp(now, g_state.scissor, sizeof(now)) == 0)) return;
		memcpy(g_state.scissor, now, sizeof(now));
		glScissor(x, y, width, height);
	}

	inline void ColorMask(GLboolean r, GLboolean g, GLboolean b, GLboolean a)
	{
		int now = (r ? 1 : 0) | (g ? 2 : 0) | (b ? 4 : 0) | (a ? 8 : 0);
		if(Skip(g_state.colorMask == now)) return;
		g_state.colorMask = now;
		glColorMask(r, g, b, a);
	}

	inline void DepthMask(GLboolean flag)
	{
		int now = flag ? 1 : 0;
		if(Skip(g_state.depthMask == now)) return;
		g_state.depthMask = now;
		glDepthMask(flag);
	}

	inline void DepthFunc(GLenum function)
	{
		if(Skip(g_state.depthFunc == function)) return;
		g_state.depthFunc = function;
		glDepthFunc(function);
	}

	inline void BlendFuncSeparate(GLenum srcRgb, GLenum dstRgb, GLenum srcAlpha, GLenum dstAlpha)
	{
		GLenum now[4] = {srcRgb, dstRgb, srcAlpha, dstAlpha};
		if(Skip(memcmp(now, g_state.blendFunc, sizeof(now)) == 0)) return;
		memcpy(g_state.blendFunc, now, sizeof(now));
		glBlendFuncSeparate(srcRgb, dstRgb, srcAlpha, dstAlpha);
	}

	inline void BlendEquationSeparate(GLenum rgb, GLenum alpha)
	{
		if(Skip(g_state.blendEquation[0] == rgb && g_state.blendEquation[1] == alpha)) return;
		g_state.blendEquation[0] = rgb;
		g_state.blendEquation[1] = alpha;
		glBlendEquationSeparate(rgb, alpha);
	}

	inline void BlendColor(GLfloat r, GLfloat g, GLfloat b, GLfloat a)
	{
		GLfloat now[4] = {r, g, b, a};
		if(Skip(memcmp(now, g_state.blendColor, sizeof(now)) == 0)) return;
		memcpy(g_state.blendColor, now, sizeof(now));
		glBlendColor(r, g, b, a);
	}
}

#define glActiveTexture RtaGl::ActiveTexture
#define glBindTexture RtaGl::BindTexture
#define glTexParameteri RtaGl::TexParameteri
#define glBindBuffer RtaGl::BindBuffer
#define glBindBufferBase RtaGl::BindBufferBase
#define glBindVertexArray RtaGl::BindVertexArray
#define glUseProgram RtaGl::UseProgram
#define glBindFramebuffer RtaGl::BindFramebuffer
#define glGetIntegerv RtaGl::GetIntegerv
#define glEnable RtaGl::Enable
#define glDisable RtaGl::Disable
#define glViewport RtaGl::Viewport
#define glScissor RtaGl::Scissor
#define glColorMask RtaGl::ColorMask
#define glDepthMask RtaGl::DepthMask
#define glDepthFunc RtaGl::DepthFunc
#define glBlendFuncSeparate RtaGl::BlendFuncSeparate
#define glBlendEquationSeparate RtaGl::BlendEquationSeparate
#define glBlendColor RtaGl::BlendColor

#endif
