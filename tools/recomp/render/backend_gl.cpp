// backend_gl.cpp - the OpenGL backend (4.1 core profile, the newest macOS has; nothing
// newer is used, so it is also plain OpenGL 3.3 + dual-source blending on other systems).
//
// The only file of the renderer that makes graphics calls.  It reaches OpenGL through
// Qt's QOpenGLExtraFunctions, which resolves the functions of the current context on every
// platform Qt runs on, so there is no loader library and no system header in here.
//
// Surfaces are kept with row 0 at the top (the game's orientation): a vertex at logical
// y = 0 goes to the first row of the framebuffer object, textures made from surfaces are
// sampled without a flip, and the one flip is in present().
#include "backend_gl.h"

#include <QOpenGLContext>
#include <QOpenGLExtraFunctions>

#include <cstdio>
#include <cstring>
#include <unordered_map>

#ifndef GL_SRC1_COLOR
#define GL_SRC1_COLOR 0x88F9
#endif
#ifndef GL_TEXTURE_SWIZZLE_A
#define GL_TEXTURE_SWIZZLE_A 0x8E45
#endif

namespace render {

static const char* VERTEX_SOURCE = R"(#version 410 core
layout(location = 0) in vec3 a_pos;
layout(location = 1) in vec3 a_st;
layout(location = 2) in vec4 a_col;
layout(location = 3) in float a_fog;
uniform vec2 u_target;
out vec3 v_st;
out vec4 v_col;
out float v_fog;
void main() {
    v_st = a_st;
    v_col = a_col * 255.0;
    v_fog = a_fog;
    gl_Position = vec4(a_pos.x / u_target.x * 2.0 - 1.0, a_pos.y / u_target.y * 2.0 - 1.0, a_pos.z * 2.0 - 1.0, 1.0);
}
)";

// Colours are carried in the GS's units: 0..255, with 128 = 1.0 for alpha and for the
// colour a texture is multiplied by.
static const char* FRAGMENT_SOURCE = R"(#version 410 core
in vec3 v_st;
in vec4 v_col;
in float v_fog;
uniform vec4 u_fog;         // fog colour (0..255), on
uniform sampler2D u_tex;
uniform int u_textured;
uniform int u_tfx;
uniform int u_tcc;
uniform vec2 u_st_scale;
uniform vec2 u_tex_size;
uniform vec2 u_tex_offset;
uniform ivec2 u_wrap;
uniform vec4 u_region;
uniform float u_weave_half;
uniform vec4 u_texa;        // mode (0 none, 1 24 bit, 2 16 bit), ta0, ta1, aem
uniform int u_atst;
uniform float u_aref;
uniform vec4 u_blend;       // source: coefficient of C, constant; destination: coefficient of C, constant
uniform int u_blend_c;      // 0 source alpha, 1 destination alpha (taken as 1), 2 fix
uniform float u_fix;
layout(location = 0, index = 0) out vec4 o_col;
layout(location = 0, index = 1) out vec4 o_fac;
float wrap(float c, int mode, float lo, float hi) {
    if (mode == 2) return clamp(c, lo, hi + 0.999);
    if (mode == 3) return float((int(floor(c)) & int(lo)) | int(hi)) + fract(c);
    return c;
}
void main() {
    vec4 c = v_col;
    if (u_textured != 0) {
        vec2 tc = v_st.xy / v_st.z * u_st_scale;
        if (u_weave_half > 0.0) {
            float line = floor(tc.y);
            tc.y = floor(line * 0.5) + mod(line, 2.0) * u_weave_half + 0.5;
        }
        tc.x = wrap(tc.x, u_wrap.x, u_region.x, u_region.y);
        tc.y = wrap(tc.y, u_wrap.y, u_region.z, u_region.w);
        vec4 t = texture(u_tex, (tc + u_tex_offset) / u_tex_size) * 255.0;
        if (u_texa.x > 0.5) {
            bool black = u_texa.w > 0.5 && t.r + t.g + t.b < 0.5;
            t.a = (u_texa.x > 1.5 && t.a >= 127.5) ? u_texa.z : (black ? 0.0 : u_texa.y);
        }
        if (u_tfx == 0) {
            c.rgb = min(t.rgb * v_col.rgb / 128.0, 255.0);
            c.a = u_tcc != 0 ? min(t.a * v_col.a / 128.0, 255.0) : v_col.a;
        } else if (u_tfx == 1) {
            c.rgb = t.rgb;
            c.a = u_tcc != 0 ? t.a : v_col.a;
        } else {
            c.rgb = min(t.rgb * v_col.rgb / 128.0 + v_col.a, 255.0);
            c.a = u_tcc == 0 ? v_col.a : (u_tfx == 2 ? min(t.a + v_col.a, 255.0) : t.a);
        }
    }
    if (u_fog.w > 0.5) c.rgb = c.rgb * v_fog + u_fog.rgb * (1.0 - v_fog);
    if (u_atst != 1) {
        bool pass = true;
        float a = floor(c.a + 0.01);
        if (u_atst == 0) pass = false;
        else if (u_atst == 2) pass = a < u_aref;
        else if (u_atst == 3) pass = a <= u_aref;
        else if (u_atst == 4) pass = a == u_aref;
        else if (u_atst == 5) pass = a >= u_aref;
        else if (u_atst == 6) pass = a > u_aref;
        else pass = a != u_aref;
        if (!pass) discard;
    }
    float factor = u_blend_c == 0 ? c.a / 128.0 : (u_blend_c == 1 ? 1.0 : u_fix);
    o_col = vec4(c.rgb / 255.0 * abs(u_blend.x * factor + u_blend.y), c.a / 255.0);
    o_fac = vec4(vec3(abs(u_blend.z * factor + u_blend.w)), 1.0);
}
)";

static const char* PRESENT_VERTEX = R"(#version 410 core
out vec2 v_uv;
uniform vec4 u_rect;
void main() {
    vec2 p = vec2(float(gl_VertexID & 1), float(gl_VertexID >> 1));
    v_uv = vec2(p.x, 1.0 - p.y);
    gl_Position = vec4(u_rect.xy + p * u_rect.zw, 0.0, 1.0);
}
)";
static const char* PRESENT_FRAGMENT = R"(#version 410 core
in vec2 v_uv;
uniform sampler2D u_tex;
out vec4 o_col;
void main() { o_col = vec4(texture(u_tex, v_uv).rgb, 1.0); }
)";

struct GlBackend::Impl {
    QOpenGLExtraFunctions* f = nullptr;
    int out_w = 1280, out_h = 896;
    GLuint program = 0, present_program = 0, vao = 0, vbo = 0, present_vao = 0;
    GLuint samplers[2][2][2] = {{{0, 0}, {0, 0}}, {{0, 0}, {0, 0}}};     // linear, clamp s, clamp t
    struct Uniforms {
        GLint target, tex, textured, tfx, tcc, st_scale, tex_size, tex_offset, wrap, region, weave_half, texa, atst, aref, blend, blend_c, fix, fog;
    } u;
    GLint present_rect = -1, present_tex = -1;
    struct Target { GLuint fbo = 0, colour = 0, depth = 0; int lw = 0, lh = 0, pw = 0, ph = 0; bool screen = false; };
    std::unordered_map<uint32_t, Target> targets;
    std::unordered_map<uint32_t, GLuint> textures;
    uint32_t shown = 0;
    size_t vbo_capacity = 0;
    uint64_t draws = 0, frames = 0;

    GLuint compile(GLenum kind, const char* source) {
        GLuint s = f->glCreateShader(kind);
        f->glShaderSource(s, 1, &source, nullptr);
        f->glCompileShader(s);
        GLint ok = 0;
        f->glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
        if (!ok) { char log[2048]; f->glGetShaderInfoLog(s, sizeof(log), nullptr, log); fprintf(stderr, "shader: %s\n", log); }
        return s;
    }
    GLuint link(const char* vs, const char* fs) {
        GLuint p = f->glCreateProgram();
        f->glAttachShader(p, compile(GL_VERTEX_SHADER, vs));
        f->glAttachShader(p, compile(GL_FRAGMENT_SHADER, fs));
        f->glLinkProgram(p);
        GLint ok = 0;
        f->glGetProgramiv(p, GL_LINK_STATUS, &ok);
        if (!ok) { char log[2048]; f->glGetProgramInfoLog(p, sizeof(log), nullptr, log); fprintf(stderr, "program: %s\n", log); }
        return p;
    }
    void init() {
        f = QOpenGLContext::currentContext()->extraFunctions();
        program = link(VERTEX_SOURCE, FRAGMENT_SOURCE);
        present_program = link(PRESENT_VERTEX, PRESENT_FRAGMENT);
#define U(name) u.name = f->glGetUniformLocation(program, "u_" #name)
        U(target); U(tex); U(textured); U(tfx); U(tcc); U(st_scale); U(tex_size); U(tex_offset); U(wrap); U(region); U(weave_half);
        U(atst); U(aref); U(blend); U(blend_c); U(fix); U(texa); U(fog);
#undef U
        present_rect = f->glGetUniformLocation(present_program, "u_rect");
        present_tex = f->glGetUniformLocation(present_program, "u_tex");
        f->glGenVertexArrays(1, &vao);
        f->glGenVertexArrays(1, &present_vao);
        f->glGenBuffers(1, &vbo);
        f->glBindVertexArray(vao);
        f->glBindBuffer(GL_ARRAY_BUFFER, vbo);
        f->glEnableVertexAttribArray(0);
        f->glEnableVertexAttribArray(1);
        f->glEnableVertexAttribArray(2);
        f->glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)0);
        f->glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)12);
        f->glVertexAttribPointer(2, 4, GL_UNSIGNED_BYTE, GL_TRUE, sizeof(Vertex), (void*)24);
        f->glEnableVertexAttribArray(3);
        f->glVertexAttribPointer(3, 1, GL_UNSIGNED_BYTE, GL_TRUE, sizeof(Vertex), (void*)28);
        for (int linear = 0; linear < 2; linear++)
            for (int cs = 0; cs < 2; cs++)
                for (int ct = 0; ct < 2; ct++) {
                    GLuint s;
                    f->glGenSamplers(1, &s);
                    f->glSamplerParameteri(s, GL_TEXTURE_MIN_FILTER, linear ? GL_LINEAR : GL_NEAREST);
                    f->glSamplerParameteri(s, GL_TEXTURE_MAG_FILTER, linear ? GL_LINEAR : GL_NEAREST);
                    f->glSamplerParameteri(s, GL_TEXTURE_WRAP_S, cs ? GL_CLAMP_TO_EDGE : GL_REPEAT);
                    f->glSamplerParameteri(s, GL_TEXTURE_WRAP_T, ct ? GL_CLAMP_TO_EDGE : GL_REPEAT);
                    samplers[linear][cs][ct] = s;
                }
    }
    Target& make_target(const TargetInfo& info) {
        Target& t = targets[info.id];
        int pw = info.screen ? out_w : info.width * aux_scale(), ph = info.screen ? out_h : info.height * aux_scale();
        t.lw = info.width; t.lh = info.height; t.screen = info.screen;
        if (t.fbo && t.pw == pw && t.ph == ph) return t;
        GLuint old_fbo = t.fbo, old_colour = t.colour, old_depth = t.depth;
        int old_pw = t.pw, old_ph = t.ph;
        t.pw = pw; t.ph = ph;
        f->glGenFramebuffers(1, &t.fbo);
        f->glGenTextures(1, &t.colour);
        f->glGenRenderbuffers(1, &t.depth);
        f->glBindTexture(GL_TEXTURE_2D, t.colour);
        f->glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, pw, ph, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        f->glBindRenderbuffer(GL_RENDERBUFFER, t.depth);
        f->glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT32F, pw, ph);
        f->glBindFramebuffer(GL_FRAMEBUFFER, t.fbo);
        f->glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, t.colour, 0);
        f->glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, t.depth);
        f->glDisable(GL_SCISSOR_TEST);
        f->glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        f->glDepthMask(GL_TRUE);
        f->glClearColor(0, 0, 0, 0);
        f->glClearDepthf(0.0f);
        f->glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        if (old_fbo) {                                  // a surface that grew keeps its picture
            f->glBindFramebuffer(GL_READ_FRAMEBUFFER, old_fbo);
            f->glBlitFramebuffer(0, 0, old_pw, old_ph, 0, 0, old_pw < pw ? old_pw : pw, old_ph < ph ? old_ph : ph, GL_COLOR_BUFFER_BIT, GL_NEAREST);
            f->glDeleteFramebuffers(1, &old_fbo);
            f->glDeleteTextures(1, &old_colour);
            f->glDeleteRenderbuffers(1, &old_depth);
        }
        return t;
    }
    int aux_scale() const { int s = (out_h + 223) / 448; return s < 1 ? 1 : s > 4 ? 4 : s; }
};

GlBackend::GlBackend() : impl(new Impl) { impl->init(); }
GlBackend::~GlBackend() { delete impl; }

void GlBackend::set_output_size(int width, int height) {
    if (width == impl->out_w && height == impl->out_h) return;
    impl->out_w = width; impl->out_h = height;
    for (auto& entry : impl->targets) {
        TargetInfo info;
        info.id = entry.first; info.width = entry.second.lw; info.height = entry.second.lh; info.screen = entry.second.screen;
        impl->make_target(info);
    }
}

void GlBackend::execute(const FrameList& frame) {
    Impl& g = *impl;
    QOpenGLExtraFunctions* f = g.f;
    g.frames++;
    for (const TextureData& t : frame.textures) {
        GLuint name;
        f->glGenTextures(1, &name);
        f->glBindTexture(GL_TEXTURE_2D, name);
        f->glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
        f->glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, t.width, t.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, t.rgba.data());
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
        g.textures[t.id] = name;
    }
    for (uint32_t id : frame.dead_textures) {
        auto t = g.textures.find(id);
        if (t == g.textures.end()) continue;
        f->glDeleteTextures(1, &t->second);
        g.textures.erase(t);
    }
    for (const TargetInfo& info : frame.targets) g.make_target(info);
    for (uint32_t id : frame.dead_targets) {
        auto t = g.targets.find(id);
        if (t == g.targets.end()) continue;
        f->glDeleteFramebuffers(1, &t->second.fbo);
        f->glDeleteTextures(1, &t->second.colour);
        f->glDeleteRenderbuffers(1, &t->second.depth);
        g.targets.erase(t);
    }
    g.shown = frame.show_target;
    if (frame.commands.empty()) return;

    f->glBindVertexArray(g.vao);
    f->glBindBuffer(GL_ARRAY_BUFFER, g.vbo);
    size_t bytes = frame.vertices.size() * sizeof(Vertex);
    if (bytes > g.vbo_capacity) { g.vbo_capacity = bytes * 3 / 2; f->glBufferData(GL_ARRAY_BUFFER, g.vbo_capacity, nullptr, GL_STREAM_DRAW); }
    else f->glBufferData(GL_ARRAY_BUFFER, g.vbo_capacity, nullptr, GL_STREAM_DRAW);     // orphan
    f->glBufferSubData(GL_ARRAY_BUFFER, 0, bytes, frame.vertices.data());
    f->glUseProgram(g.program);
    f->glUniform1i(g.u.tex, 0);
    f->glActiveTexture(GL_TEXTURE0);
    f->glEnable(GL_SCISSOR_TEST);
    f->glEnable(GL_DEPTH_TEST);
    f->glDisable(GL_CULL_FACE);
    uint32_t bound_target = 0;
    const Impl::Target* target = nullptr;
    for (const DrawCmd& c : frame.commands) {
        auto found = g.targets.find(c.target);
        if (found == g.targets.end()) continue;
        if (c.kind == CMD_COPY) {
            auto src = g.targets.find(c.texture);
            if (src == g.targets.end()) continue;
            const Impl::Target& s = src->second;
            const Impl::Target& d = found->second;
            float sx = (float)s.pw / s.lw, sy = (float)s.ph / s.lh, dx = (float)d.pw / d.lw, dy = (float)d.ph / d.lh;
            f->glBindFramebuffer(GL_READ_FRAMEBUFFER, s.fbo);
            f->glBindFramebuffer(GL_DRAW_FRAMEBUFFER, d.fbo);
            f->glDisable(GL_SCISSOR_TEST);
            f->glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
            f->glBlitFramebuffer((int)(c.copy_src[0] * sx), (int)(c.copy_src[1] * sy), (int)((c.copy_src[0] + c.copy_src[2]) * sx),
                                 (int)((c.copy_src[1] + c.copy_src[3]) * sy), (int)(c.copy_dst[0] * dx), (int)(c.copy_dst[1] * dy),
                                 (int)((c.copy_dst[0] + c.copy_dst[2]) * dx), (int)((c.copy_dst[1] + c.copy_dst[3]) * dy),
                                 GL_COLOR_BUFFER_BIT, GL_LINEAR);
            f->glEnable(GL_SCISSOR_TEST);
            bound_target = 0;
            continue;
        }
        if (!c.count) continue;
        if (c.target != bound_target) {
            target = &found->second;
            f->glBindFramebuffer(GL_FRAMEBUFFER, target->fbo);
            f->glViewport(0, 0, target->pw, target->ph);
            f->glUniform2f(g.u.target, (float)target->lw, (float)target->lh);
            bound_target = c.target;
        }
        float sx = (float)target->pw / target->lw, sy = (float)target->ph / target->lh;
        int x0 = (int)(c.scissor[0] * sx + 0.5f), y0 = (int)(c.scissor[1] * sy + 0.5f);
        int x1 = (int)(c.scissor[2] * sx + 0.5f), y1 = (int)(c.scissor[3] * sy + 0.5f);
        f->glScissor(x0, y0, x1 > x0 ? x1 - x0 : 0, y1 > y0 ? y1 - y0 : 0);
        // texture
        GLuint name = 0;
        bool linear = c.linear;
        if (c.texture) {
            if (c.tex_is_target) { auto t = g.targets.find(c.texture); if (t != g.targets.end()) name = t->second.colour; }
            else { auto t = g.textures.find(c.texture); if (t != g.textures.end()) name = t->second; }
        }
        f->glUniform1i(g.u.textured, name ? 1 : 0);
        if (name) {
            f->glBindTexture(GL_TEXTURE_2D, name);
            f->glBindSampler(0, g.samplers[linear ? 1 : 0][c.wrap[0] == WRAP_REPEAT ? 0 : 1][c.wrap[1] == WRAP_REPEAT ? 0 : 1]);
            f->glUniform1i(g.u.tfx, c.tfx);
            f->glUniform1i(g.u.tcc, c.tcc ? 1 : 0);
            f->glUniform2f(g.u.st_scale, c.st_scale[0], c.st_scale[1]);
            f->glUniform2f(g.u.tex_size, c.tex_size[0], c.tex_size[1]);
            f->glUniform2f(g.u.tex_offset, c.tex_offset[0], c.tex_offset[1]);
            f->glUniform2i(g.u.wrap, c.wrap[0], c.wrap[1]);
            f->glUniform4f(g.u.region, c.region[0], c.region[1], c.region[2], c.region[3]);
            f->glUniform1f(g.u.weave_half, c.weave_half);
            f->glUniform4f(g.u.texa, c.tex_is_target ? (float)c.texa_mode : 0.0f, (float)c.ta0, (float)c.ta1, c.aem ? 1.0f : 0.0f);
        }
        f->glUniform4f(g.u.fog, (float)c.fog_colour[0], (float)c.fog_colour[1], (float)c.fog_colour[2], c.fog ? 1.0f : 0.0f);
        f->glUniform1i(g.u.atst, c.alpha_test ? c.atst : 1);
        f->glUniform1f(g.u.aref, (float)c.aref);
        // depth
        f->glDepthFunc(c.ztst == 1 ? GL_ALWAYS : c.ztst == 2 ? GL_GEQUAL : c.ztst == 3 ? GL_GREATER : GL_NEVER);
        f->glDepthMask(c.depth_write ? GL_TRUE : GL_FALSE);
        f->glColorMask(!c.mask_rgb, !c.mask_rgb, !c.mask_rgb, !c.mask_a);
        // blend: colour = (A - B) * C + D
        if (c.blend) {
            float sc = (c.ba == 0 ? 1.0f : 0.0f) - (c.bb == 0 ? 1.0f : 0.0f), sk = c.bd == 0 ? 1.0f : 0.0f;
            float dc = (c.ba == 1 ? 1.0f : 0.0f) - (c.bb == 1 ? 1.0f : 0.0f), dk = c.bd == 1 ? 1.0f : 0.0f;
            bool src_negative = sc < 0 && sk == 0, dst_negative = dc < 0 && dk == 0;
            f->glEnable(GL_BLEND);
            f->glBlendFuncSeparate(GL_ONE, GL_SRC1_COLOR, GL_ONE, GL_ZERO);
            f->glBlendEquationSeparate(dst_negative && !src_negative ? GL_FUNC_SUBTRACT : src_negative && !dst_negative ? GL_FUNC_REVERSE_SUBTRACT : GL_FUNC_ADD, GL_FUNC_ADD);
            if (src_negative && dst_negative) { sc = 0; dc = 0; }
            f->glUniform4f(g.u.blend, sc, sk, dc, dk);
            f->glUniform1i(g.u.blend_c, c.bc);
            f->glUniform1f(g.u.fix, (float)c.fix / 128.0f);
        } else {
            f->glDisable(GL_BLEND);
            f->glUniform4f(g.u.blend, 0, 1, 0, 0);
            f->glUniform1i(g.u.blend_c, 2);
            f->glUniform1f(g.u.fix, 1.0f);
        }
        f->glDrawArrays(c.prim == PK_TRIANGLES ? GL_TRIANGLES : c.prim == PK_LINES ? GL_LINES : GL_POINTS, (GLint)c.first, (GLsizei)c.count);
        g.draws++;
    }
    f->glBindSampler(0, 0);
    f->glDisable(GL_SCISSOR_TEST);
    f->glDisable(GL_BLEND);
    f->glDisable(GL_DEPTH_TEST);
    f->glDepthMask(GL_TRUE);
    f->glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    f->glBindFramebuffer(GL_FRAMEBUFFER, 0);
}

void GlBackend::present(int width, int height, double aspect) {
    Impl& g = *impl;
    QOpenGLExtraFunctions* f = g.f;
    f->glViewport(0, 0, width, height);
    f->glClearColor(0, 0, 0, 1);
    f->glClear(GL_COLOR_BUFFER_BIT);
    auto t = g.targets.find(g.shown);
    if (t == g.targets.end()) return;
    double window = (double)width / height;
    float w = window > aspect ? (float)(aspect / window) : 1.0f, h = window > aspect ? 1.0f : (float)(window / aspect);
    f->glUseProgram(g.present_program);
    f->glUniform4f(g.present_rect, -w, -h, 2 * w, 2 * h);
    f->glUniform1i(g.present_tex, 0);
    f->glActiveTexture(GL_TEXTURE0);
    f->glBindTexture(GL_TEXTURE_2D, t->second.colour);
    f->glBindSampler(0, 0);
    f->glBindVertexArray(g.present_vao);
    f->glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
}

bool GlBackend::read_shown(std::vector<uint8_t>& rgba, int& width, int& height) { return read_target(impl->shown, rgba, width, height); }

bool GlBackend::read_target(uint32_t id, std::vector<uint8_t>& rgba, int& width, int& height) {
    Impl& g = *impl;
    auto t = g.targets.find(id);
    if (t == g.targets.end()) return false;
    width = t->second.pw; height = t->second.ph;
    rgba.resize((size_t)width * height * 4);
    g.f->glBindFramebuffer(GL_FRAMEBUFFER, t->second.fbo);
    g.f->glPixelStorei(GL_PACK_ALIGNMENT, 1);
    g.f->glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE, rgba.data());
    g.f->glBindFramebuffer(GL_FRAMEBUFFER, 0);
    return true;
}

uint64_t GlBackend::draw_calls() const { return impl->draws; }

}  // namespace render
