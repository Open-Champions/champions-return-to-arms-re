// backend_webgl.cpp - the renderer's backend (render/backend.h, class GlBackend of
// render/backend_gl.h) on WebGL 2, for the page.  The port of render/backend_gl.cpp, which
// is OpenGL 4.1 core through Qt; this file takes its place in the web build and is called
// with a WebGL 2 context current on the calling thread (web_main.cpp makes it on an
// OffscreenCanvas, so every call here is a direct WebGL call of that worker).
//
// What OpenGL 4.1 core has and WebGL 2 (OpenGL ES 3.0) has not, as far as this backend
// uses it, and what stands in:
//
//  1. Dual-source blending (a second fragment output as the destination's factor,
//     GL_SRC1_COLOR).  The GS blends (A - B) * C + D, and the desktop backend gives the
//     source's and the destination's coefficient as two outputs.  Here, two ways:
//       - the extension WEBGL_blend_func_extended when the browser has it: the same two
//         outputs, the same blend function, nothing else changes ("dual");
//       - without it ("basic"): the destination's coefficient is either a constant of the
//         draw (C is the fixed value, or the destination is not scaled by alpha at all) -
//         then it is the blend colour (GL_CONSTANT_COLOR) - or it follows the source's
//         alpha, As or 1 - As: then the fragment's alpha output carries As (0x80 = 1.0)
//         for GL_SRC_ALPHA / GL_ONE_MINUS_SRC_ALPHA, and the alpha that is *stored* is
//         scaled back to the GS's own (0x80 = 128/255) by the alpha blend function
//         (GL_CONSTANT_ALPHA with 128/255).  The one loss: a source alpha above 0x80 in
//         such a draw is stored as 0x80.
//  2. GLSL 4.10 -> GLSL ES 3.00: precision statements; no `index` layout without the
//     extension; gl_PointSize has to be written for points.
//  3. A surface may not be sampled while it is the one drawn into (WebGL refuses the draw
//     as a feedback loop; desktop OpenGL lets it pass).  Such a draw samples a copy made
//     just before it; they are counted (`feedback_copies`).
//  4. Nothing else: vertex array objects, sampler objects, framebuffer blits, 32-bit float
//     depth, integer operations in shaders and gl_VertexID are all in WebGL 2.
//
// A browser checks every WebGL call and ships it to another process, so calls that would
// set what is set already are left out (uniforms and state are shadowed here); the
// emulator's page needed the same (tools/play-web/src/GlStateShadow.h).
#include "backend_gl.h"

#include <GLES3/gl3.h>
#include <emscripten/html5.h>

#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <unordered_map>

#ifndef GL_SRC1_COLOR_EXT
#define GL_SRC1_COLOR_EXT 0x88F9
#endif

namespace render {

uint64_t g_webgl_calls = 0, g_webgl_skipped = 0, g_webgl_feedback_copies = 0;
int g_webgl_dual = -1;              // 1 dual-source blending, 0 basic; set when the backend is made
int g_webgl_want_dual = 1;          // 0: use the basic way even where the extension exists (for comparing)

static const char* VERTEX_SOURCE = R"(#version 300 es
precision highp float;
layout(location = 0) in vec3 a_pos;
layout(location = 1) in vec3 a_st;
layout(location = 2) in vec4 a_col;
uniform vec2 u_target;
out vec3 v_st;
out vec4 v_col;
void main() {
    v_st = a_st;
    v_col = a_col * 255.0;
    gl_PointSize = 1.0;
    gl_Position = vec4(a_pos.x / u_target.x * 2.0 - 1.0, a_pos.y / u_target.y * 2.0 - 1.0, a_pos.z * 2.0 - 1.0, 1.0);
}
)";

// Colours are carried in the GS's units: 0..255, with 128 = 1.0 for alpha and for the
// colour a texture is multiplied by.  %s: the outputs; %s: how they are written.
static const char* FRAGMENT_HEAD = R"(#version 300 es
%s
precision highp float;
precision highp int;
precision highp sampler2D;
in vec3 v_st;
in vec4 v_col;
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
uniform int u_alpha_out;    // basic blending: 1 = the alpha output is the source alpha as a factor
%s
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
%s
}
)";
static const char* DUAL_EXTENSION = "#extension GL_EXT_blend_func_extended : require";
static const char* DUAL_OUTPUTS = "layout(location = 0, index = 0) out vec4 o_col;\nlayout(location = 0, index = 1) out vec4 o_fac;";
static const char* DUAL_WRITE =
    "    o_col = vec4(c.rgb / 255.0 * abs(u_blend.x * factor + u_blend.y), c.a / 255.0);\n"
    "    o_fac = vec4(vec3(abs(u_blend.z * factor + u_blend.w)), 1.0);";
static const char* BASIC_OUTPUTS = "out vec4 o_col;";
static const char* BASIC_WRITE =
    "    o_col = vec4(c.rgb / 255.0 * abs(u_blend.x * factor + u_blend.y), u_alpha_out != 0 ? min(c.a / 128.0, 1.0) : c.a / 255.0);";

static const char* PRESENT_VERTEX = R"(#version 300 es
precision highp float;
out vec2 v_uv;
uniform vec4 u_rect;
void main() {
    vec2 p = vec2(float(gl_VertexID & 1), float(gl_VertexID >> 1));
    v_uv = vec2(p.x, 1.0 - p.y);
    gl_Position = vec4(u_rect.xy + p * u_rect.zw, 0.0, 1.0);
}
)";
static const char* PRESENT_FRAGMENT = R"(#version 300 es
precision highp float;
in vec2 v_uv;
uniform sampler2D u_tex;
out vec4 o_col;
void main() { o_col = vec4(texture(u_tex, v_uv).rgb, 1.0); }
)";

struct GlBackend::Impl {
    int out_w = 1280, out_h = 896;
    bool dual = false;
    GLuint program = 0, present_program = 0, vao = 0, vbo = 0, present_vao = 0;
    GLuint samplers[2][2][2] = {{{0, 0}, {0, 0}}, {{0, 0}, {0, 0}}};     // linear, clamp s, clamp t
    struct Uniforms {
        GLint target, tex, textured, tfx, tcc, st_scale, tex_size, tex_offset, wrap, region, weave_half, texa, atst, aref, blend, blend_c, fix, alpha_out;
    } u;
    GLint present_rect = -1, present_tex = -1;
    struct Target { GLuint fbo = 0, colour = 0, depth = 0, copy = 0, copy_fbo = 0; int lw = 0, lh = 0, pw = 0, ph = 0; bool screen = false; };
    std::unordered_map<uint32_t, Target> targets;
    std::unordered_map<uint32_t, GLuint> textures;
    uint32_t shown = 0;
    size_t vbo_capacity = 0;
    uint64_t draws = 0, frames = 0;

    // ---- what is set, so that it is not set again -------------------------------------
    struct Shadow {
        bool valid = false;
        int textured = -1, tfx = -1, tcc = -1, atst = -1, blend_c = -1, alpha_out = -1, wrap[2] = {-1, -1};
        float st_scale[2], tex_size[2], tex_offset[2], region[4], weave_half, texa[4], aref, blend[4], fix, target[2];
        GLuint texture = ~0u, sampler = ~0u;
        int scissor[4] = {-1, -1, -1, -1};
        GLenum depth_func = 0, equation = 0, dst_factor = 0, src_alpha = 0;
        int depth_mask = -1, mask_rgb = -1, mask_a = -1, blend_on = -1;
        float blend_colour[4] = {-1, -1, -1, -1};
    } s;
    void forget() { s = Shadow(); }
#define CALL(x) do { g_webgl_calls++; x; } while (0)
#define SKIP() g_webgl_skipped++
    void u1i(GLint loc, int& have, int v) { if (have == v) { SKIP(); return; } have = v; CALL(glUniform1i(loc, v)); }
    void u1f(GLint loc, float& have, float v) { if (s.valid && have == v) { SKIP(); return; } have = v; CALL(glUniform1f(loc, v)); }
    void u2f(GLint loc, float* have, float a, float b) {
        if (s.valid && have[0] == a && have[1] == b) { SKIP(); return; }
        have[0] = a; have[1] = b; CALL(glUniform2f(loc, a, b));
    }
    void u4f(GLint loc, float* have, float a, float b, float c, float d) {
        if (s.valid && have[0] == a && have[1] == b && have[2] == c && have[3] == d) { SKIP(); return; }
        have[0] = a; have[1] = b; have[2] = c; have[3] = d; CALL(glUniform4f(loc, a, b, c, d));
    }

    GLuint compile(GLenum kind, const char* source) {
        GLuint sh = glCreateShader(kind);
        glShaderSource(sh, 1, &source, nullptr);
        glCompileShader(sh);
        GLint ok = 0;
        glGetShaderiv(sh, GL_COMPILE_STATUS, &ok);
        if (!ok) { char log[2048]; glGetShaderInfoLog(sh, sizeof(log), nullptr, log); fprintf(stderr, "shader: %s\n", log); }
        return sh;
    }
    GLuint link(const char* vs, const char* fs) {
        GLuint p = glCreateProgram();
        glAttachShader(p, compile(GL_VERTEX_SHADER, vs));
        glAttachShader(p, compile(GL_FRAGMENT_SHADER, fs));
        glLinkProgram(p);
        GLint ok = 0;
        glGetProgramiv(p, GL_LINK_STATUS, &ok);
        if (!ok) { char log[2048]; glGetProgramInfoLog(p, sizeof(log), nullptr, log); fprintf(stderr, "program: %s\n", log); }
        return p;
    }
    void init() {
        dual = g_webgl_want_dual && emscripten_webgl_enable_extension(emscripten_webgl_get_current_context(), "WEBGL_blend_func_extended");
        g_webgl_dual = dual ? 1 : 0;
        std::string fragment(strlen(FRAGMENT_HEAD) + 1024, '\0');
        int n = snprintf(&fragment[0], fragment.size(), FRAGMENT_HEAD, dual ? DUAL_EXTENSION : "", dual ? DUAL_OUTPUTS : BASIC_OUTPUTS, dual ? DUAL_WRITE : BASIC_WRITE);
        fragment.resize(n);
        program = link(VERTEX_SOURCE, fragment.c_str());
        present_program = link(PRESENT_VERTEX, PRESENT_FRAGMENT);
#define U(name) u.name = glGetUniformLocation(program, "u_" #name)
        U(target); U(tex); U(textured); U(tfx); U(tcc); U(st_scale); U(tex_size); U(tex_offset); U(wrap); U(region); U(weave_half);
        U(atst); U(aref); U(blend); U(blend_c); U(fix); U(texa); U(alpha_out);
#undef U
        present_rect = glGetUniformLocation(present_program, "u_rect");
        present_tex = glGetUniformLocation(present_program, "u_tex");
        glGenVertexArrays(1, &vao);
        glGenVertexArrays(1, &present_vao);
        glGenBuffers(1, &vbo);
        glBindVertexArray(vao);
        glBindBuffer(GL_ARRAY_BUFFER, vbo);
        glEnableVertexAttribArray(0);
        glEnableVertexAttribArray(1);
        glEnableVertexAttribArray(2);
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)0);
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)12);
        glVertexAttribPointer(2, 4, GL_UNSIGNED_BYTE, GL_TRUE, sizeof(Vertex), (void*)24);
        for (int linear = 0; linear < 2; linear++)
            for (int cs = 0; cs < 2; cs++)
                for (int ct = 0; ct < 2; ct++) {
                    GLuint sm;
                    glGenSamplers(1, &sm);
                    glSamplerParameteri(sm, GL_TEXTURE_MIN_FILTER, linear ? GL_LINEAR : GL_NEAREST);
                    glSamplerParameteri(sm, GL_TEXTURE_MAG_FILTER, linear ? GL_LINEAR : GL_NEAREST);
                    glSamplerParameteri(sm, GL_TEXTURE_WRAP_S, cs ? GL_CLAMP_TO_EDGE : GL_REPEAT);
                    glSamplerParameteri(sm, GL_TEXTURE_WRAP_T, ct ? GL_CLAMP_TO_EDGE : GL_REPEAT);
                    samplers[linear][cs][ct] = sm;
                }
    }
    static void surface_texture(GLuint name, int pw, int ph) {
        glBindTexture(GL_TEXTURE_2D, name);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, pw, ph, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    }
    Target& make_target(const TargetInfo& info) {
        Target& t = targets[info.id];
        int pw = info.screen ? out_w : info.width * aux_scale(), ph = info.screen ? out_h : info.height * aux_scale();
        t.lw = info.width; t.lh = info.height; t.screen = info.screen;
        if (t.fbo && t.pw == pw && t.ph == ph) return t;
        forget();
        GLuint old_fbo = t.fbo, old_colour = t.colour, old_depth = t.depth;
        int old_pw = t.pw, old_ph = t.ph;
        if (t.copy) { glDeleteTextures(1, &t.copy); glDeleteFramebuffers(1, &t.copy_fbo); t.copy = 0; t.copy_fbo = 0; }
        t.pw = pw; t.ph = ph;
        glGenFramebuffers(1, &t.fbo);
        glGenTextures(1, &t.colour);
        glGenRenderbuffers(1, &t.depth);
        surface_texture(t.colour, pw, ph);
        glBindRenderbuffer(GL_RENDERBUFFER, t.depth);
        glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT32F, pw, ph);
        glBindFramebuffer(GL_FRAMEBUFFER, t.fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, t.colour, 0);
        glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, t.depth);
        glDisable(GL_SCISSOR_TEST);
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        glDepthMask(GL_TRUE);
        glClearColor(0, 0, 0, 0);
        glClearDepthf(0.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        if (old_fbo) {                                  // a surface that grew keeps its picture
            glBindFramebuffer(GL_READ_FRAMEBUFFER, old_fbo);
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER, t.fbo);
            glBlitFramebuffer(0, 0, old_pw, old_ph, 0, 0, old_pw < pw ? old_pw : pw, old_ph < ph ? old_ph : ph, GL_COLOR_BUFFER_BIT, GL_NEAREST);
            glDeleteFramebuffers(1, &old_fbo);
            glDeleteTextures(1, &old_colour);
            glDeleteRenderbuffers(1, &old_depth);
        }
        return t;
    }
    // the surface's picture as it is now, for a draw that samples the surface it draws into
    GLuint copy_of(Target& t) {
        if (!t.copy) {
            glGenTextures(1, &t.copy);
            surface_texture(t.copy, t.pw, t.ph);
            glGenFramebuffers(1, &t.copy_fbo);
            glBindFramebuffer(GL_FRAMEBUFFER, t.copy_fbo);
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, t.copy, 0);
        }
        glBindFramebuffer(GL_READ_FRAMEBUFFER, t.fbo);
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, t.copy_fbo);
        glDisable(GL_SCISSOR_TEST);
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        glBlitFramebuffer(0, 0, t.pw, t.ph, 0, 0, t.pw, t.ph, GL_COLOR_BUFFER_BIT, GL_NEAREST);
        glEnable(GL_SCISSOR_TEST);
        glBindFramebuffer(GL_FRAMEBUFFER, t.fbo);
        s.mask_rgb = s.mask_a = -1;
        s.texture = ~0u;
        g_webgl_feedback_copies++;
        return t.copy;
    }
    int aux_scale() const { int k = (out_h + 223) / 448; return k < 1 ? 1 : k > 4 ? 4 : k; }
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
    Impl::Shadow& s = g.s;
    g.frames++;
    for (const TextureData& t : frame.textures) {
        GLuint name;
        glGenTextures(1, &name);
        glBindTexture(GL_TEXTURE_2D, name);
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, t.width, t.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, t.rgba.data());
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
        g.textures[t.id] = name;
        g_webgl_calls += 6;
    }
    for (uint32_t id : frame.dead_textures) {
        auto t = g.textures.find(id);
        if (t == g.textures.end()) continue;
        glDeleteTextures(1, &t->second);
        g.textures.erase(t);
    }
    for (const TargetInfo& info : frame.targets) g.make_target(info);
    g.shown = frame.show_target;
    if (frame.commands.empty()) return;

    g.forget();                                         // a frame starts from nothing known
    glBindVertexArray(g.vao);
    glBindBuffer(GL_ARRAY_BUFFER, g.vbo);
    size_t bytes = frame.vertices.size() * sizeof(Vertex);
    if (bytes > g.vbo_capacity) g.vbo_capacity = bytes * 3 / 2;
    glBufferData(GL_ARRAY_BUFFER, g.vbo_capacity, nullptr, GL_STREAM_DRAW);            // a new store: the old one may still be drawn from
    glBufferSubData(GL_ARRAY_BUFFER, 0, bytes, frame.vertices.data());
    glUseProgram(g.program);
    glUniform1i(g.u.tex, 0);
    glActiveTexture(GL_TEXTURE0);
    glEnable(GL_SCISSOR_TEST);
    glEnable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    g_webgl_calls += 10;
    uint32_t bound_target = 0;
    Impl::Target* target = nullptr;
    for (const DrawCmd& c : frame.commands) {
        auto found = g.targets.find(c.target);
        if (found == g.targets.end()) continue;
        if (c.kind == CMD_COPY) {
            auto src = g.targets.find(c.texture);
            if (src == g.targets.end() || src == found) continue;
            const Impl::Target& from = src->second;
            const Impl::Target& d = found->second;
            float sx = (float)from.pw / from.lw, sy = (float)from.ph / from.lh, dx = (float)d.pw / d.lw, dy = (float)d.ph / d.lh;
            glBindFramebuffer(GL_READ_FRAMEBUFFER, from.fbo);
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER, d.fbo);
            glDisable(GL_SCISSOR_TEST);
            glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
            glBlitFramebuffer((int)(c.copy_src[0] * sx), (int)(c.copy_src[1] * sy), (int)((c.copy_src[0] + c.copy_src[2]) * sx),
                              (int)((c.copy_src[1] + c.copy_src[3]) * sy), (int)(c.copy_dst[0] * dx), (int)(c.copy_dst[1] * dy),
                              (int)((c.copy_dst[0] + c.copy_dst[2]) * dx), (int)((c.copy_dst[1] + c.copy_dst[3]) * dy),
                              GL_COLOR_BUFFER_BIT, GL_LINEAR);
            glEnable(GL_SCISSOR_TEST);
            g_webgl_calls += 6;
            bound_target = 0;
            s.mask_rgb = s.mask_a = -1;
            continue;
        }
        if (!c.count) continue;
        if (c.target != bound_target) {
            target = &found->second;
            CALL(glBindFramebuffer(GL_FRAMEBUFFER, target->fbo));
            CALL(glViewport(0, 0, target->pw, target->ph));
            g.u2f(g.u.target, s.target, (float)target->lw, (float)target->lh);
            bound_target = c.target;
        }
        float sx = (float)target->pw / target->lw, sy = (float)target->ph / target->lh;
        int x0 = (int)(c.scissor[0] * sx + 0.5f), y0 = (int)(c.scissor[1] * sy + 0.5f);
        int x1 = (int)(c.scissor[2] * sx + 0.5f), y1 = (int)(c.scissor[3] * sy + 0.5f);
        int box[4] = {x0, y0, x1 > x0 ? x1 - x0 : 0, y1 > y0 ? y1 - y0 : 0};
        if (memcmp(box, s.scissor, sizeof box)) { memcpy(s.scissor, box, sizeof box); CALL(glScissor(box[0], box[1], box[2], box[3])); } else SKIP();
        // texture
        GLuint name = 0;
        bool linear = c.linear;
        if (c.texture) {
            if (c.tex_is_target) {
                auto t = g.targets.find(c.texture);
                if (t != g.targets.end()) name = (c.texture == c.target) ? g.copy_of(t->second) : t->second.colour;
            } else { auto t = g.textures.find(c.texture); if (t != g.textures.end()) name = t->second; }
        }
        g.u1i(g.u.textured, s.textured, name ? 1 : 0);
        if (name) {
            if (s.texture != name) { s.texture = name; CALL(glBindTexture(GL_TEXTURE_2D, name)); } else SKIP();
            GLuint sampler = g.samplers[linear ? 1 : 0][c.wrap[0] == WRAP_REPEAT ? 0 : 1][c.wrap[1] == WRAP_REPEAT ? 0 : 1];
            if (s.sampler != sampler) { s.sampler = sampler; CALL(glBindSampler(0, sampler)); } else SKIP();
            g.u1i(g.u.tfx, s.tfx, c.tfx);
            g.u1i(g.u.tcc, s.tcc, c.tcc ? 1 : 0);
            g.u2f(g.u.st_scale, s.st_scale, c.st_scale[0], c.st_scale[1]);
            g.u2f(g.u.tex_size, s.tex_size, c.tex_size[0], c.tex_size[1]);
            g.u2f(g.u.tex_offset, s.tex_offset, c.tex_offset[0], c.tex_offset[1]);
            if (s.wrap[0] != c.wrap[0] || s.wrap[1] != c.wrap[1]) { s.wrap[0] = c.wrap[0]; s.wrap[1] = c.wrap[1]; CALL(glUniform2i(g.u.wrap, c.wrap[0], c.wrap[1])); } else SKIP();
            g.u4f(g.u.region, s.region, c.region[0], c.region[1], c.region[2], c.region[3]);
            g.u1f(g.u.weave_half, s.weave_half, c.weave_half);
            g.u4f(g.u.texa, s.texa, c.tex_is_target ? (float)c.texa_mode : 0.0f, (float)c.ta0, (float)c.ta1, c.aem ? 1.0f : 0.0f);
        }
        g.u1i(g.u.atst, s.atst, c.alpha_test ? c.atst : 1);
        g.u1f(g.u.aref, s.aref, (float)c.aref);
        // depth
        GLenum depth_func = c.ztst == 1 ? GL_ALWAYS : c.ztst == 2 ? GL_GEQUAL : c.ztst == 3 ? GL_GREATER : GL_NEVER;
        if (s.depth_func != depth_func) { s.depth_func = depth_func; CALL(glDepthFunc(depth_func)); } else SKIP();
        if (s.depth_mask != (int)c.depth_write) { s.depth_mask = c.depth_write; CALL(glDepthMask(c.depth_write ? GL_TRUE : GL_FALSE)); } else SKIP();
        if (s.mask_rgb != (int)c.mask_rgb || s.mask_a != (int)c.mask_a) {
            s.mask_rgb = c.mask_rgb; s.mask_a = c.mask_a;
            CALL(glColorMask(!c.mask_rgb, !c.mask_rgb, !c.mask_rgb, !c.mask_a));
        } else SKIP();
        // blend: colour = (A - B) * C + D
        int alpha_out = 0;
        if (c.blend) {
            float sc = (c.ba == 0 ? 1.0f : 0.0f) - (c.bb == 0 ? 1.0f : 0.0f), sk = c.bd == 0 ? 1.0f : 0.0f;
            float dc = (c.ba == 1 ? 1.0f : 0.0f) - (c.bb == 1 ? 1.0f : 0.0f), dk = c.bd == 1 ? 1.0f : 0.0f;
            bool src_negative = sc < 0 && sk == 0, dst_negative = dc < 0 && dk == 0;
            GLenum equation = dst_negative && !src_negative ? GL_FUNC_SUBTRACT : src_negative && !dst_negative ? GL_FUNC_REVERSE_SUBTRACT : GL_FUNC_ADD;
            if (src_negative && dst_negative) { sc = 0; dc = 0; }
            float fix = (float)c.fix / 128.0f;
            if (s.blend_on != 1) { s.blend_on = 1; CALL(glEnable(GL_BLEND)); } else SKIP();
            GLenum dst_factor, src_alpha = GL_ONE;
            float colour[4] = {s.blend_colour[0], s.blend_colour[1], s.blend_colour[2], s.blend_colour[3]};
            if (g.dual) dst_factor = GL_SRC1_COLOR_EXT;
            else if (c.bc == 0 && dc != 0 && !(dc > 0 && dk != 0)) {
                // the destination's coefficient follows the source's alpha: As, or 1 - As
                dst_factor = dk == 0 ? GL_SRC_ALPHA : GL_ONE_MINUS_SRC_ALPHA;
                src_alpha = GL_CONSTANT_ALPHA;
                colour[3] = 128.0f / 255.0f;
                alpha_out = 1;
            } else {
                // a constant of the draw: |dc * C + dk| with C the fixed value, 1 for "destination alpha"
                // (and 1 + As, which the target clamps to 1 anyway)
                float k = c.bc == 0 ? (dc != 0 ? 1.0f : dk) : std::fabs(dc * (c.bc == 1 ? 1.0f : fix) + dk);
                if (k > 1) k = 1;
                dst_factor = k == 0 ? GL_ZERO : k == 1 ? GL_ONE : GL_CONSTANT_COLOR;
                if (dst_factor == GL_CONSTANT_COLOR) colour[0] = colour[1] = colour[2] = k;
            }
            if (memcmp(colour, s.blend_colour, sizeof colour)) { memcpy(s.blend_colour, colour, sizeof colour); CALL(glBlendColor(colour[0], colour[1], colour[2], colour[3])); }
            if (s.dst_factor != dst_factor || s.src_alpha != src_alpha) {
                s.dst_factor = dst_factor; s.src_alpha = src_alpha;
                CALL(glBlendFuncSeparate(GL_ONE, dst_factor, src_alpha, GL_ZERO));
            } else SKIP();
            if (s.equation != equation) { s.equation = equation; CALL(glBlendEquationSeparate(equation, GL_FUNC_ADD)); } else SKIP();
            g.u4f(g.u.blend, s.blend, sc, sk, dc, dk);
            g.u1i(g.u.blend_c, s.blend_c, c.bc);
            g.u1f(g.u.fix, s.fix, fix);
        } else {
            if (s.blend_on != 0) { s.blend_on = 0; CALL(glDisable(GL_BLEND)); } else SKIP();
            g.u4f(g.u.blend, s.blend, 0, 1, 0, 0);
            g.u1i(g.u.blend_c, s.blend_c, 2);
            g.u1f(g.u.fix, s.fix, 1.0f);
        }
        if (!g.dual) g.u1i(g.u.alpha_out, s.alpha_out, alpha_out);
        s.valid = true;
        CALL(glDrawArrays(c.prim == PK_TRIANGLES ? GL_TRIANGLES : c.prim == PK_LINES ? GL_LINES : GL_POINTS, (GLint)c.first, (GLsizei)c.count));
        g.draws++;
    }
    glBindSampler(0, 0);
    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_BLEND);
    glDisable(GL_DEPTH_TEST);
    glDepthMask(GL_TRUE);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    g_webgl_calls += 7;
    g.forget();
}

void GlBackend::present(int width, int height, double aspect) {
    Impl& g = *impl;
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    glViewport(0, 0, width, height);
    glClearColor(0, 0, 0, 1);
    glClear(GL_COLOR_BUFFER_BIT);
    auto t = g.targets.find(g.shown);
    if (t == g.targets.end()) return;
    double window = (double)width / height;
    float w = window > aspect ? (float)(aspect / window) : 1.0f, h = window > aspect ? 1.0f : (float)(window / aspect);
    glUseProgram(g.present_program);
    glUniform4f(g.present_rect, -w, -h, 2 * w, 2 * h);
    glUniform1i(g.present_tex, 0);
    glActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, t->second.colour);
    glBindSampler(0, 0);
    glBindVertexArray(g.present_vao);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    g_webgl_calls += 11;
}

bool GlBackend::read_shown(std::vector<uint8_t>& rgba, int& width, int& height) { return read_target(impl->shown, rgba, width, height); }

bool GlBackend::read_target(uint32_t id, std::vector<uint8_t>& rgba, int& width, int& height) {
    Impl& g = *impl;
    auto t = g.targets.find(id);
    if (t == g.targets.end()) return false;
    width = t->second.pw; height = t->second.ph;
    rgba.resize((size_t)width * height * 4);
    glBindFramebuffer(GL_FRAMEBUFFER, t->second.fbo);
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE, rgba.data());
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    return true;
}

uint64_t GlBackend::draw_calls() const { return impl->draws; }

}  // namespace render
