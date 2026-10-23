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
#include "texpack.h"

#include <QOpenGLContext>
#include <QOpenGLExtraFunctions>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <chrono>
#include <memory>
#include <thread>
#include <unordered_map>

#ifndef GL_SRC1_COLOR
#define GL_SRC1_COLOR 0x88F9
#endif
#ifndef GL_TEXTURE_SWIZZLE_A
#define GL_TEXTURE_SWIZZLE_A 0x8E45
#endif
#ifndef GL_TEXTURE_MAX_ANISOTROPY_EXT
#define GL_TEXTURE_MAX_ANISOTROPY_EXT 0x84FE
#define GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT 0x84FF
#endif

namespace render {

static const char* VERTEX_SOURCE = R"(#version 410 core
layout(location = 0) in vec3 a_pos;
layout(location = 1) in vec3 a_st;
layout(location = 2) in vec4 a_col;
layout(location = 3) in float a_fog;
uniform vec2 u_target;
// centroid: with multisampling a pixel on a triangle's edge is shaded at a place inside the
// triangle, not at the pixel's centre outside it - where the texture coordinate would run
// off the part of the page the triangle uses (specks of the neighbouring texels on edges)
centroid out vec3 v_st;
centroid out vec4 v_col;
centroid out float v_fog;
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
centroid in vec3 v_st;
centroid in vec4 v_col;
centroid in float v_fog;
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
        // how fast the coordinate moves across the screen, taken before the weave and the
        // wraps break it up: the mip level and the anisotropy are chosen from these
        vec2 gx = dFdx(tc), gy = dFdy(tc);
        if (u_weave_half > 0.0) {
            float line = floor(tc.y);
            tc.y = floor(line * 0.5) + mod(line, 2.0) * u_weave_half + 0.5;
            gx.y *= 0.5; gy.y *= 0.5;
        } else if (u_weave_half < 0.0) {
            // a replacement of a two-field picture holds the woven picture itself (twice;
            // the first copy is used): the woven line is the coordinate
            tc.y *= 0.5; gx.y *= 0.5; gy.y *= 0.5;
        }
        tc.x = wrap(tc.x, u_wrap.x, u_region.x, u_region.y);
        tc.y = wrap(tc.y, u_wrap.y, u_region.z, u_region.w);
        vec4 t = textureGrad(u_tex, (tc + u_tex_offset) / u_tex_size, gx / u_tex_size, gy / u_tex_size) * 255.0;
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
    // fbo/colour: what is sampled, copied and shown.  With multisampling the draws go to
    // ms_fbo and are resolved into fbo before the surface is read (dirty: not yet).
    struct Target {
        GLuint fbo = 0, colour = 0, depth = 0, ms_fbo = 0, ms_colour = 0;
        int lw = 0, lh = 0, pw = 0, ph = 0, samples = 0, requested_samples = 0;
        bool screen = false, dirty = false;
    };
    std::unordered_map<uint32_t, Target> targets;
    std::unordered_map<uint32_t, GLuint> textures;
    // ---- beyond the lists as they are: multisampling, mip maps, replacement pictures ----
    PictureOptions opt;
    PictureFigures fig;
    int max_samples = 0;
    float max_anisotropy = 1.0f;
    GLuint mip_samplers[2][2][2] = {{{0, 0}, {0, 0}}, {{0, 0}, {0, 0}}};     // anisotropic, clamp s, clamp t
    TexPack pack;
    bool replacements_on = true;
    // What is drawn in place of a texture: a replacement picture from the pack, or the
    // texture's own pixels with mip maps - whole, or the part that is drawn with.
    struct Picture {
        std::string file;               // the pack's file for it; empty: none
        int texels_w = 0, texels_h = 0; // the texels a picture of it is stretched over
        int named_w = 0, named_h = 0;
        std::shared_ptr<const std::vector<uint8_t>> own;        // the game's pixels (kept for mip maps of its own)
        int own_w = 0, own_h = 0;
        // how it is drawn
        float box[4] = {0, 0, 0, 0};    // the texels triangles use, x0 y0 x1 y1
        bool box_valid = false, sprites = false, repeats = false, scene = false;
        uint64_t last_drawn = 0;
        // what is held
        enum State { IDLE, ASKED, READY } state = IDLE;
        bool reask = false, failed = false, whole_only = false;
        uint64_t serial = 0;
        GLuint gl = 0;
        int part[4] = {0, 0, 0, 0};
        bool whole = true, two_field = false, from_file = false;
        size_t bytes = 0;
        int regrown = 0;
    };
    std::unordered_map<uint32_t, Picture> pictures;
    size_t picture_bytes = 0;
    uint64_t next_serial = 1;
    struct Use { Picture* picture = nullptr; float box[4] = {0, 0, 0, 0}; };
    std::vector<Use> uses;              // per command of the list being drawn
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
        GLint most = 0;
        f->glGetIntegerv(GL_MAX_SAMPLES, &most);
        max_samples = most;
        GLfloat aniso = 1.0f;
        f->glGetFloatv(GL_MAX_TEXTURE_MAX_ANISOTROPY_EXT, &aniso);
        if (f->glGetError() != GL_NO_ERROR || aniso < 1.0f) aniso = 1.0f;
        max_anisotropy = aniso;
    }
    void make_mip_samplers() {
        for (int a = 0; a < 2; a++)
            for (int cs = 0; cs < 2; cs++)
                for (int ct = 0; ct < 2; ct++) {
                    GLuint s;
                    f->glGenSamplers(1, &s);
                    f->glSamplerParameteri(s, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
                    f->glSamplerParameteri(s, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
                    f->glSamplerParameteri(s, GL_TEXTURE_WRAP_S, cs ? GL_CLAMP_TO_EDGE : GL_REPEAT);
                    f->glSamplerParameteri(s, GL_TEXTURE_WRAP_T, ct ? GL_CLAMP_TO_EDGE : GL_REPEAT);
                    if (a && fig.anisotropy > 1) f->glSamplerParameterf(s, GL_TEXTURE_MAX_ANISOTROPY_EXT, (float)fig.anisotropy);
                    mip_samplers[a][cs][ct] = s;
                }
    }
    // A surface drawn into with multisampling: bring what is read from it up to date.
    void resolve(Target& t) {
        if (!t.ms_fbo || !t.dirty) return;
        f->glBindFramebuffer(GL_READ_FRAMEBUFFER, t.ms_fbo);
        f->glBindFramebuffer(GL_DRAW_FRAMEBUFFER, t.fbo);
        f->glDisable(GL_SCISSOR_TEST);
        f->glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        f->glBlitFramebuffer(0, 0, t.pw, t.ph, 0, 0, t.pw, t.ph, GL_COLOR_BUFFER_BIT, GL_NEAREST);
        t.dirty = false;
    }
    // ... only a rectangle of it (pixels of the surface), for a copy out of it: the rest
    // stays to be brought up to date when it is read (a level with heat haze copies ten
    // small pieces of the 3-D surface a frame; resolving all of a 2619 x 1964 surface of
    // four samples for each was most of that frame's work on the graphics card).
    void resolve_part(Target& t, int x0, int y0, int x1, int y1) {
        if (!t.ms_fbo || !t.dirty) return;
        x0 = std::max(0, x0 - 2); y0 = std::max(0, y0 - 2); x1 = std::min(t.pw, x1 + 2); y1 = std::min(t.ph, y1 + 2);
        if (x1 <= x0 || y1 <= y0) return;
        f->glBindFramebuffer(GL_READ_FRAMEBUFFER, t.ms_fbo);
        f->glBindFramebuffer(GL_DRAW_FRAMEBUFFER, t.fbo);
        f->glDisable(GL_SCISSOR_TEST);
        f->glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        f->glBlitFramebuffer(x0, y0, x1, y1, x0, y0, x1, y1, GL_COLOR_BUFFER_BIT, GL_NEAREST);
    }
    void drop_picture(Picture& p) {
        if (p.gl) { f->glDeleteTextures(1, &p.gl); p.gl = 0; }
        picture_bytes -= p.bytes;
        p.bytes = 0;
        p.state = Picture::IDLE;
        p.reask = false;
        p.serial = 0;
    }
    void take_picture(PictureResult& r) {
        auto found = pictures.find(r.texture);
        if (found == pictures.end() || found->second.serial != r.serial) return;       // given up or asked again since
        Picture& p = found->second;
        if (!r.ok || r.levels.empty()) { p.failed = true; p.state = p.gl ? Picture::READY : Picture::IDLE; p.reask = false; return; }
        if (p.gl) { f->glDeleteTextures(1, &p.gl); picture_bytes -= p.bytes; }
        f->glGenTextures(1, &p.gl);
        f->glBindTexture(GL_TEXTURE_2D, p.gl);
        f->glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
        for (size_t level = 0; level < r.levels.size(); level++)
            f->glTexImage2D(GL_TEXTURE_2D, (GLint)level, GL_RGBA8, r.levels[level].width, r.levels[level].height, 0, GL_RGBA, GL_UNSIGNED_BYTE, r.levels[level].rgba.data());
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAX_LEVEL, (GLint)r.levels.size() - 1);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        p.bytes = r.bytes();
        picture_bytes += p.bytes;
        if (picture_bytes > fig.most_bytes) fig.most_bytes = picture_bytes;
        memcpy(p.part, r.part, sizeof(p.part));
        p.whole = r.whole; p.two_field = r.two_field; p.from_file = r.from_file;
        p.state = Picture::READY;
        p.reask = false;
        if (r.from_file) { fig.replaced++; if (!r.whole) fig.parts++; } else fig.own_made++;
    }
    void ask_picture(uint32_t id, Picture& p) {
        PictureJob job;
        job.texture = id;
        job.serial = p.serial = next_serial++;
        job.part = opt.pack_parts && !p.sprites && !p.repeats && !p.whole_only && p.box_valid;
        job.first = p.sprites;
        memcpy(job.box, p.box, sizeof(job.box));
        if (!p.file.empty()) {
            job.file = p.file;
            job.texels_w = p.texels_w; job.texels_h = p.texels_h;
            if (p.state != Picture::READY) p.state = Picture::ASKED;
            pack.ask(std::move(job));
        } else {
            job.own = p.own; job.own_width = p.own_w; job.own_height = p.own_h;
            job.texels_w = p.own_w; job.texels_h = p.own_h;
            PictureResult r = TexPack::make(job);       // small: made here and now
            take_picture(r);
        }
    }
    // The texels the triangles of a command use.
    static void box_of(const FrameList& frame, const DrawCmd& c, float* box) {
        float x0 = 1e30f, y0 = 1e30f, x1 = -1e30f, y1 = -1e30f;
        const Vertex* v = frame.vertices.data() + c.first;
        for (uint32_t i = 0; i < c.count; i++) {
            float q = v[i].q != 0.0f ? v[i].q : 1.0f;
            float s = v[i].s / q * c.st_scale[0], t = v[i].t / q * c.st_scale[1];
            if (s < x0) x0 = s;
            if (s > x1) x1 = s;
            if (t < y0) y0 = t;
            if (t > y1) y1 = t;
        }
        box[0] = x0; box[1] = y0; box[2] = x1; box[3] = y1;
    }
    // Before a list is drawn: what its commands draw with, pictures asked for and taken.
    void prepare_pictures(const FrameList& frame) {
        uses.assign(frame.commands.size(), Use());
        if (pictures.empty()) return;
        // finished pictures: at most 24 MB a frame go to the graphics card
        size_t handed = 0;
        PictureResult result;
        while (handed < (24u << 20) && pack.take(result)) { handed += result.bytes(); take_picture(result); }
        for (size_t k = 0; k < frame.commands.size(); k++) {
            const DrawCmd& c = frame.commands[k];
            if (c.kind != CMD_DRAW || !c.count || !c.texture || c.tex_is_target) continue;
            auto found = pictures.find(c.texture);
            if (found == pictures.end()) continue;
            Picture& p = found->second;
            if (p.file.empty() && !p.own) continue;
            p.last_drawn = frames;
            Use& use = uses[k];
            use.picture = &p;
            if (c.made_by == 2) p.sprites = true;
            else if (!p.repeats && !p.sprites) {
                box_of(frame, c, use.box);
                // beyond the size the name gives (and a texel for filtering): the texture repeats
                if (use.box[0] < -1.0f || use.box[1] < -1.0f || use.box[2] > p.texels_w + 1.0f || use.box[3] > p.texels_h + 1.0f) p.repeats = true;
                else if (!p.box_valid) { memcpy(p.box, use.box, sizeof(p.box)); p.box_valid = true; }
                else {
                    p.box[0] = std::min(p.box[0], use.box[0]); p.box[1] = std::min(p.box[1], use.box[1]);
                    p.box[2] = std::max(p.box[2], use.box[2]); p.box[3] = std::max(p.box[3], use.box[3]);
                }
            }
            if (c.made_by == 0 && c.linear) p.scene = true;
            // held as a part and drawn beyond it, or held as a part and now drawn by sprites
            // or repeating: asked for again (twice: then whole)
            if (p.state == Picture::READY && !p.whole && !p.reask) {
                bool beyond = p.sprites || p.repeats || use.box[0] < p.part[0] + 0.5f || use.box[1] < p.part[1] + 0.5f || use.box[2] > p.part[2] - 0.5f
                              || use.box[3] > p.part[3] - 0.5f;
                if (beyond) {
                    p.reask = true;
                    fig.regrown++;
                    if (++p.regrown >= 2) p.whole_only = true;
                    ask_picture(c.texture, p);
                }
            }
            if (p.state == Picture::IDLE && !p.failed && replacements_on) {
                bool wanted = !p.file.empty() || (opt.mipmaps && p.scene && p.own);
                if (wanted) ask_picture(c.texture, p);
            }
        }
        // a test that compares pictures: nothing is drawn before what it asks for is there
        if (opt.pack_wait) {
            PictureResult late;
            for (int waited = 0; pack.outstanding() > 0 && waited < 20000; waited++) {
                if (pack.take(late)) take_picture(late);
                else std::this_thread::sleep_for(std::chrono::milliseconds(1));
            }
        }
        // asked for and not drawn with for two seconds: given up (asked again when it is drawn)
        if ((frames & 31) == 0) {
            size_t budget = (size_t)opt.pack_memory_mb << 20;
            std::vector<std::pair<uint64_t, uint32_t>> old;
            for (auto& entry : pictures) {
                Picture& p = entry.second;
                if (p.state == Picture::ASKED && frames - p.last_drawn > 120) { pack.forget(entry.first); p.state = Picture::IDLE; p.serial = 0; fig.abandoned++; }
                else if (p.state == Picture::READY && p.from_file && frames - p.last_drawn > 600) old.push_back({p.last_drawn, entry.first});
            }
            // beyond the budget: those not drawn with for ten seconds go, the longest unused first
            if (picture_bytes > budget) {
                std::sort(old.begin(), old.end());
                for (size_t k = 0; k < old.size() && picture_bytes > budget; k++) { drop_picture(pictures[old[k].second]); fig.dropped++; }
            }
        }
        fig.held = 0;
        for (auto& entry : pictures) if (entry.second.gl) fig.held++;
        fig.held_bytes = picture_bytes;
        fig.pending = pack.waiting();
    }

    Target& make_target(const TargetInfo& info) {
        Target& t = targets[info.id];
        int pw = info.screen ? out_w : info.width * aux_scale(), ph = info.screen ? out_h : info.height * aux_scale();
        int requested_samples = info.screen && info.width >= 1024 ? fig.samples : 0;
        t.lw = info.width; t.lh = info.height; t.screen = info.screen;
        // Logical reuse can change multisampling without changing physical size.
        // Remember the attempted mode separately so an unsupported MSAA fallback
        // is reused rather than retried on every identical target announcement.
        if (t.fbo && t.pw == pw && t.ph == ph && t.requested_samples == requested_samples) return t;
        if (t.fbo) resolve(t);
        GLuint old_fbo = t.fbo, old_colour = t.colour, old_depth = t.depth, old_ms_fbo = t.ms_fbo, old_ms_colour = t.ms_colour;
        int old_pw = t.pw, old_ph = t.ph;
        t.pw = pw; t.ph = ph;
        // multisampling: the 3-D surface only (the display buffers get the finished picture)
        t.requested_samples = requested_samples;
        t.samples = requested_samples;
        t.ms_fbo = t.ms_colour = 0;
        t.dirty = false;
        f->glGenFramebuffers(1, &t.fbo);
        f->glGenTextures(1, &t.colour);
        f->glGenRenderbuffers(1, &t.depth);
        f->glBindTexture(GL_TEXTURE_2D, t.colour);
        f->glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, pw, ph, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        f->glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        f->glBindFramebuffer(GL_FRAMEBUFFER, t.fbo);
        f->glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, t.colour, 0);
        f->glBindRenderbuffer(GL_RENDERBUFFER, t.depth);
        if (t.samples > 1) {
            f->glRenderbufferStorageMultisample(GL_RENDERBUFFER, t.samples, GL_DEPTH_COMPONENT32F, pw, ph);
            f->glGenRenderbuffers(1, &t.ms_colour);
            f->glBindRenderbuffer(GL_RENDERBUFFER, t.ms_colour);
            f->glRenderbufferStorageMultisample(GL_RENDERBUFFER, t.samples, GL_RGBA8, pw, ph);
            f->glGenFramebuffers(1, &t.ms_fbo);
            f->glBindFramebuffer(GL_FRAMEBUFFER, t.ms_fbo);
            f->glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, t.ms_colour);
            f->glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, t.depth);
            if (f->glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
                fprintf(stderr, "backend: no multisampled surface of %d x %d with %d samples; drawing without\n", pw, ph, t.samples);
                f->glDeleteFramebuffers(1, &t.ms_fbo);
                f->glDeleteRenderbuffers(1, &t.ms_colour);
                t.ms_fbo = t.ms_colour = 0;
                t.samples = 0;
                f->glBindRenderbuffer(GL_RENDERBUFFER, t.depth);
            }
        }
        if (!t.ms_fbo) {
            f->glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT32F, pw, ph);
            f->glBindFramebuffer(GL_FRAMEBUFFER, t.fbo);
            f->glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, t.depth);
        }
        f->glDisable(GL_SCISSOR_TEST);
        f->glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        f->glDepthMask(GL_TRUE);
        f->glClearColor(0, 0, 0, 0);
        f->glClearDepthf(0.0f);
        f->glBindFramebuffer(GL_FRAMEBUFFER, t.fbo);
        f->glClear(t.ms_fbo ? GL_COLOR_BUFFER_BIT : GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        if (t.ms_fbo) {
            f->glBindFramebuffer(GL_FRAMEBUFFER, t.ms_fbo);
            f->glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        }
        if (old_fbo) {                                  // a surface that grew keeps its picture
            f->glBindFramebuffer(GL_READ_FRAMEBUFFER, old_fbo);
            f->glBindFramebuffer(GL_DRAW_FRAMEBUFFER, t.ms_fbo ? t.ms_fbo : t.fbo);
            f->glBlitFramebuffer(0, 0, old_pw < pw ? old_pw : pw, old_ph < ph ? old_ph : ph, 0, 0, old_pw < pw ? old_pw : pw, old_ph < ph ? old_ph : ph, GL_COLOR_BUFFER_BIT, GL_NEAREST);
            if (t.ms_fbo) t.dirty = true;
            // A sample-mode change at the same physical size keeps the old
            // depth tests as well as colour. Physical resizes retain their
            // existing cleared-depth behavior.
            if (old_pw == pw && old_ph == ph) {
                f->glBindFramebuffer(GL_READ_FRAMEBUFFER, old_ms_fbo ? old_ms_fbo : old_fbo);
                f->glBindFramebuffer(GL_DRAW_FRAMEBUFFER, t.ms_fbo ? t.ms_fbo : t.fbo);
                f->glBlitFramebuffer(0, 0, pw, ph, 0, 0, pw, ph, GL_DEPTH_BUFFER_BIT, GL_NEAREST);
            }
            f->glDeleteFramebuffers(1, &old_fbo);
            f->glDeleteTextures(1, &old_colour);
            f->glDeleteRenderbuffers(1, &old_depth);
            if (old_ms_fbo) { f->glDeleteFramebuffers(1, &old_ms_fbo); f->glDeleteRenderbuffers(1, &old_ms_colour); }
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
        // a picture for it: from the pack by its name (as it is known when it repeats: by
        // the size of what was sent; else by the size TEX0 names), or of its own pixels
        if (g.pack.size() || g.opt.mipmaps) {
            Impl::Picture p;
            p.named_w = t.named_width; p.named_h = t.named_height;
            if (t.named && g.pack.size()) {
                g.fig.named++;
                p.file = g.pack.find(t.figure, t.palette_figure, t.format, t.sent_width, t.sent_height);
                p.texels_w = t.sent_width; p.texels_h = t.sent_height;
                if (p.file.empty()) {
                    p.file = g.pack.find(t.figure, t.palette_figure, t.format, t.named_width, t.named_height);
                    p.texels_w = t.named_width; p.texels_h = t.named_height;
                }
                if (!p.file.empty()) g.fig.named_found++;
            }
            if (p.file.empty()) {
                if (g.opt.mipmaps) {
                    p.own = std::make_shared<const std::vector<uint8_t>>(t.rgba);
                    p.own_w = p.texels_w = t.width; p.own_h = p.texels_h = t.height;
                } else p.texels_w = p.texels_h = 0;
            }
            if (!p.file.empty() || p.own) g.pictures[t.id] = std::move(p);
        }
    }
    for (uint32_t id : frame.dead_textures) {
        auto t = g.textures.find(id);
        if (t == g.textures.end()) continue;
        f->glDeleteTextures(1, &t->second);
        g.textures.erase(t);
        auto p = g.pictures.find(id);
        if (p != g.pictures.end()) { g.pack.forget(id); g.drop_picture(p->second); g.pictures.erase(p); }
    }
    for (const TargetInfo& info : frame.targets) g.make_target(info);
    for (uint32_t id : frame.dead_targets) {
        auto t = g.targets.find(id);
        if (t == g.targets.end()) continue;
        f->glDeleteFramebuffers(1, &t->second.fbo);
        f->glDeleteTextures(1, &t->second.colour);
        f->glDeleteRenderbuffers(1, &t->second.depth);
        if (t->second.ms_fbo) { f->glDeleteFramebuffers(1, &t->second.ms_fbo); f->glDeleteRenderbuffers(1, &t->second.ms_colour); }
        g.targets.erase(t);
    }
    g.shown = frame.show_target;
    if (frame.commands.empty()) return;
    g.prepare_pictures(frame);

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
    Impl::Target* target = nullptr;
    // What the last draw left set: a call is made only for what the next draw has otherwise
    // (most draws of a frame differ from the one before in their texture and nothing else;
    // set one by one, the twenty-odd calls a draw were most of this thread's time).
    struct Cache {
        int textured = -1, tfx = -1, tcc = -1, atst = -1, blend_c = -1, wrap[2] = {-1, -1};
        float st_scale[2] = {NAN, NAN}, tex_size[2] = {NAN, NAN}, tex_offset[2] = {NAN, NAN}, region[4] = {NAN, NAN, NAN, NAN}, weave = NAN;
        float texa[4] = {NAN, NAN, NAN, NAN}, fog[4] = {NAN, NAN, NAN, NAN}, aref = NAN, blend[4] = {NAN, NAN, NAN, NAN}, fix = NAN;
        GLuint texture = ~0u, sampler = ~0u;
        int depth_func = -1, depth_mask = -1, mask_rgb = -1, mask_a = -1, blending = -1, equation = -1, scissor[4] = {-1, -1, -1, -1};
    } cache;
    // A draw is not sent at once: the next command is added to it when it draws the same
    // kind of primitive from the vertices that follow and changes nothing (the same
    // primitives in the same order, in one call: a draw call is what this thread's time
    // goes into).  `flush` sends what waits; everything that changes state calls it first.
    struct Waiting { GLenum mode = 0; GLint first = 0; GLsizei count = 0; } waiting;
    auto flush = [&] {
        if (!waiting.count) return;
        f->glDrawArrays(waiting.mode, waiting.first, waiting.count);
        g.draws++;
        waiting.count = 0;
    };
    auto set1i = [&](GLint location, int& held, int value) { if (held != value) { flush(); held = value; f->glUniform1i(location, value); } };
    auto set1f = [&](GLint location, float& held, float value) { if (!(held == value)) { flush(); held = value; f->glUniform1f(location, value); } };
    auto set2f = [&](GLint location, float* held, float a, float b) { if (!(held[0] == a && held[1] == b)) { flush(); held[0] = a; held[1] = b; f->glUniform2f(location, a, b); } };
    auto set4f = [&](GLint location, float* held, float a, float b, float c2, float d) {
        if (!(held[0] == a && held[1] == b && held[2] == c2 && held[3] == d)) { flush(); held[0] = a; held[1] = b; held[2] = c2; held[3] = d; f->glUniform4f(location, a, b, c2, d); }
    };
    auto bind = [&](GLuint texture, GLuint sampler) {
        if (cache.texture != texture) { flush(); cache.texture = texture; f->glBindTexture(GL_TEXTURE_2D, texture); }
        if (cache.sampler != sampler) { flush(); cache.sampler = sampler; f->glBindSampler(0, sampler); }
    };
    for (size_t command = 0; command < frame.commands.size(); command++) {
        const DrawCmd& c = frame.commands[command];
        auto found = g.targets.find(c.target);
        if (found == g.targets.end()) continue;
        if (c.kind == CMD_COPY) {
            auto src = g.targets.find(c.texture);
            if (src == g.targets.end()) continue;
            flush();
            Impl::Target& s = src->second;
            Impl::Target& d = found->second;
            float sx = (float)s.pw / s.lw, sy = (float)s.ph / s.lh, dx = (float)d.pw / d.lw, dy = (float)d.ph / d.lh;
            g.resolve_part(s, (int)(c.copy_src[0] * sx), (int)(c.copy_src[1] * sy), (int)((c.copy_src[0] + c.copy_src[2]) * sx) + 1,
                           (int)((c.copy_src[1] + c.copy_src[3]) * sy) + 1);
            g.resolve(d);
            cache = Cache();                            // the copy changes masks and bindings
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
        // a surface that is drawn into with multisampling and read here: resolved first
        if (c.texture && c.tex_is_target) {
            auto source = g.targets.find(c.texture);
            if (source != g.targets.end() && source->second.ms_fbo && source->second.dirty) {
                flush();
                g.resolve(source->second);
                f->glEnable(GL_SCISSOR_TEST);
                bound_target = 0;
                cache = Cache();
            }
        }
        if (c.target != bound_target) {
            flush();
            target = &found->second;
            f->glBindFramebuffer(GL_FRAMEBUFFER, target->ms_fbo ? target->ms_fbo : target->fbo);
            f->glViewport(0, 0, target->pw, target->ph);
            f->glUniform2f(g.u.target, (float)target->lw, (float)target->lh);
            bound_target = c.target;
        }
        target->dirty = true;
        float sx = (float)target->pw / target->lw, sy = (float)target->ph / target->lh;
        int x0 = (int)(c.scissor[0] * sx + 0.5f), y0 = (int)(c.scissor[1] * sy + 0.5f);
        int x1 = (int)(c.scissor[2] * sx + 0.5f), y1 = (int)(c.scissor[3] * sy + 0.5f);
        if (c.scissor_moved) { x0 = (int)(c.scissor_x[0] * sx + 0.5f); x1 = (int)(c.scissor_x[1] * sx + 0.5f); }
        {
            int box[4] = {x0, y0, x1 > x0 ? x1 - x0 : 0, y1 > y0 ? y1 - y0 : 0};
            if (memcmp(box, cache.scissor, sizeof box)) { flush(); memcpy(cache.scissor, box, sizeof box); f->glScissor(box[0], box[1], box[2], box[3]); }
        }
        // texture
        GLuint name = 0;
        bool linear = c.linear;
        if (c.texture) {
            if (c.tex_is_target) { auto t = g.targets.find(c.texture); if (t != g.targets.end()) name = t->second.colour; }
            else { auto t = g.textures.find(c.texture); if (t != g.textures.end()) name = t->second; }
        }
        set1i(g.u.textured, cache.textured, name ? 1 : 0);
        // a picture in its place: a replacement always, the texture's own mip-mapped pixels
        // where the game filters; a part only for a draw that stays inside it
        const Impl::Picture* picture = nullptr;
        if (name && g.replacements_on && g.uses[command].picture && g.uses[command].picture->gl) {
            const Impl::Picture& p = *g.uses[command].picture;
            const float* box = g.uses[command].box;
            bool inside = p.whole || (!p.sprites && !p.repeats && c.made_by != 2 && box[0] >= p.part[0] + 0.5f && box[1] >= p.part[1] + 0.5f
                                      && box[2] <= p.part[2] - 0.5f && box[3] <= p.part[3] - 0.5f);
            if (inside && (p.from_file || linear)) picture = &p;
        }
        if (name && picture) {
            bool clamp_s = !picture->whole || c.wrap[0] != WRAP_REPEAT || picture->texels_w != picture->named_w;
            bool clamp_t = !picture->whole || c.wrap[1] != WRAP_REPEAT || picture->texels_h != picture->named_h;
            if (!picture->from_file) { clamp_s = !picture->whole || c.wrap[0] != WRAP_REPEAT; clamp_t = !picture->whole || c.wrap[1] != WRAP_REPEAT; }
            bind(picture->gl, g.mip_samplers[c.made_by != 2 ? 1 : 0][clamp_s ? 1 : 0][clamp_t ? 1 : 0]);
            set1i(g.u.tfx, cache.tfx, c.tfx);
            set1i(g.u.tcc, cache.tcc, c.tcc ? 1 : 0);
            set2f(g.u.st_scale, cache.st_scale, c.st_scale[0], c.st_scale[1]);
            set2f(g.u.tex_size, cache.tex_size, (float)(picture->part[2] - picture->part[0]), (float)(picture->part[3] - picture->part[1]));
            set2f(g.u.tex_offset, cache.tex_offset, -(float)picture->part[0], -(float)picture->part[1]);
            if (cache.wrap[0] != c.wrap[0] || cache.wrap[1] != c.wrap[1]) { flush(); cache.wrap[0] = c.wrap[0]; cache.wrap[1] = c.wrap[1]; f->glUniform2i(g.u.wrap, c.wrap[0], c.wrap[1]); }
            set4f(g.u.region, cache.region, c.region[0], c.region[1], c.region[2], c.region[3]);
            set1f(g.u.weave_half, cache.weave, c.weave_half > 0 && picture->two_field ? -1.0f : c.weave_half);
            set4f(g.u.texa, cache.texa, 0.0f, (float)c.ta0, (float)c.ta1, 0.0f);
        } else if (name) {
            bind(name, g.samplers[linear ? 1 : 0][c.wrap[0] == WRAP_REPEAT ? 0 : 1][c.wrap[1] == WRAP_REPEAT ? 0 : 1]);
            set1i(g.u.tfx, cache.tfx, c.tfx);
            set1i(g.u.tcc, cache.tcc, c.tcc ? 1 : 0);
            set2f(g.u.st_scale, cache.st_scale, c.st_scale[0], c.st_scale[1]);
            set2f(g.u.tex_size, cache.tex_size, c.tex_size[0], c.tex_size[1]);
            set2f(g.u.tex_offset, cache.tex_offset, c.tex_offset[0], c.tex_offset[1]);
            if (cache.wrap[0] != c.wrap[0] || cache.wrap[1] != c.wrap[1]) { flush(); cache.wrap[0] = c.wrap[0]; cache.wrap[1] = c.wrap[1]; f->glUniform2i(g.u.wrap, c.wrap[0], c.wrap[1]); }
            set4f(g.u.region, cache.region, c.region[0], c.region[1], c.region[2], c.region[3]);
            set1f(g.u.weave_half, cache.weave, c.weave_half);
            set4f(g.u.texa, cache.texa, c.tex_is_target ? (float)c.texa_mode : 0.0f, (float)c.ta0, (float)c.ta1, c.aem ? 1.0f : 0.0f);
        }
        set4f(g.u.fog, cache.fog, (float)c.fog_colour[0], (float)c.fog_colour[1], (float)c.fog_colour[2], c.fog ? 1.0f : 0.0f);
        set1i(g.u.atst, cache.atst, c.alpha_test ? c.atst : 1);
        set1f(g.u.aref, cache.aref, (float)c.aref);
        // depth
        {
            int func = c.ztst == 1 ? GL_ALWAYS : c.ztst == 2 ? GL_GEQUAL : c.ztst == 3 ? GL_GREATER : GL_NEVER;
            if (cache.depth_func != func) { flush(); cache.depth_func = func; f->glDepthFunc((GLenum)func); }
            if (cache.depth_mask != (int)c.depth_write) { flush(); cache.depth_mask = c.depth_write; f->glDepthMask(c.depth_write ? GL_TRUE : GL_FALSE); }
            if (cache.mask_rgb != (int)c.mask_rgb || cache.mask_a != (int)c.mask_a) {
                flush();
                cache.mask_rgb = c.mask_rgb; cache.mask_a = c.mask_a;
                f->glColorMask(!c.mask_rgb, !c.mask_rgb, !c.mask_rgb, !c.mask_a);
            }
        }
        // blend: colour = (A - B) * C + D
        if (c.blend) {
            float sc = (c.ba == 0 ? 1.0f : 0.0f) - (c.bb == 0 ? 1.0f : 0.0f), sk = c.bd == 0 ? 1.0f : 0.0f;
            float dc = (c.ba == 1 ? 1.0f : 0.0f) - (c.bb == 1 ? 1.0f : 0.0f), dk = c.bd == 1 ? 1.0f : 0.0f;
            bool src_negative = sc < 0 && sk == 0, dst_negative = dc < 0 && dk == 0;
            int equation = dst_negative && !src_negative ? GL_FUNC_SUBTRACT : src_negative && !dst_negative ? GL_FUNC_REVERSE_SUBTRACT : GL_FUNC_ADD;
            if (cache.blending != 1) { flush(); cache.blending = 1; f->glEnable(GL_BLEND); f->glBlendFuncSeparate(GL_ONE, GL_SRC1_COLOR, GL_ONE, GL_ZERO); }
            if (cache.equation != equation) { flush(); cache.equation = equation; f->glBlendEquationSeparate((GLenum)equation, GL_FUNC_ADD); }
            if (src_negative && dst_negative) { sc = 0; dc = 0; }
            set4f(g.u.blend, cache.blend, sc, sk, dc, dk);
            set1i(g.u.blend_c, cache.blend_c, c.bc);
            set1f(g.u.fix, cache.fix, (float)c.fix / 128.0f);
        } else {
            if (cache.blending != 0) { flush(); cache.blending = 0; f->glDisable(GL_BLEND); }
            set4f(g.u.blend, cache.blend, 0, 1, 0, 0);
            set1i(g.u.blend_c, cache.blend_c, 2);
            set1f(g.u.fix, cache.fix, 1.0f);
        }
        {
            GLenum mode = c.prim == PK_TRIANGLES ? GL_TRIANGLES : c.prim == PK_LINES ? GL_LINES : GL_POINTS;
            if (waiting.count && waiting.mode == mode && waiting.first + waiting.count == (GLint)c.first) waiting.count += (GLsizei)c.count;
            else { flush(); waiting.mode = mode; waiting.first = (GLint)c.first; waiting.count = (GLsizei)c.count; }
        }
    }
    flush();
    f->glBindSampler(0, 0);
    f->glDisable(GL_SCISSOR_TEST);
    f->glDisable(GL_BLEND);
    f->glDisable(GL_DEPTH_TEST);
    f->glDepthMask(GL_TRUE);
    f->glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    f->glBindFramebuffer(GL_FRAMEBUFFER, 0);
}

void GlBackend::present(int width, int height, double aspect) { present_to(width, height, aspect, false); }
void GlBackend::present_top_down(int width, int height, double aspect) { present_to(width, height, aspect, true); }
void GlBackend::present_to(int width, int height, double aspect, bool top_down) {
    Impl& g = *impl;
    QOpenGLExtraFunctions* f = g.f;
    f->glViewport(0, 0, width, height);
    f->glClearColor(0, 0, 0, 1);
    f->glClear(GL_COLOR_BUFFER_BIT);
    auto t = g.targets.find(g.shown);
    if (t == g.targets.end()) return;
    if (t->second.ms_fbo && t->second.dirty) {
        GLint bound = 0;
        f->glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &bound);
        g.resolve(t->second);
        f->glBindFramebuffer(GL_FRAMEBUFFER, (GLuint)bound);
    }
    double window = (double)width / height;
    float w = window > aspect ? (float)(aspect / window) : 1.0f, h = window > aspect ? 1.0f : (float)(window / aspect);
    f->glUseProgram(g.present_program);
    if (top_down) f->glUniform4f(g.present_rect, -w, h, 2 * w, -2 * h);     // the picture's top row at the framebuffer's first
    else f->glUniform4f(g.present_rect, -w, -h, 2 * w, 2 * h);
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
    g.resolve(t->second);
    width = t->second.pw; height = t->second.ph;
    rgba.resize((size_t)width * height * 4);
    g.f->glBindFramebuffer(GL_FRAMEBUFFER, t->second.fbo);
    g.f->glPixelStorei(GL_PACK_ALIGNMENT, 1);
    g.f->glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE, rgba.data());
    g.f->glBindFramebuffer(GL_FRAMEBUFFER, 0);
    return true;
}

uint64_t GlBackend::draw_calls() const { return impl->draws; }

void GlBackend::configure(const PictureOptions& options) {
    Impl& g = *impl;
    g.opt = options;
    int samples = options.samples < 2 ? 0 : options.samples < 4 ? 2 : options.samples < 8 ? 4 : 8;
    if (samples > g.max_samples) samples = g.max_samples;
    g.fig.samples = samples < 2 ? 0 : samples;
    int anisotropy = options.anisotropy < 1 ? 1 : options.anisotropy;
    if ((float)anisotropy > g.max_anisotropy) anisotropy = (int)g.max_anisotropy;
    g.fig.anisotropy = anisotropy;
    g.make_mip_samplers();
    if (!options.pack.empty()) {
        g.fig.pack_files = g.pack.open(options.pack);
        if (g.fig.pack_files) g.pack.start(3);
    }
    // surfaces made before this (none in the application: it is called first)
    for (auto& entry : g.targets) {
        TargetInfo info;
        info.id = entry.first; info.width = entry.second.lw; info.height = entry.second.lh; info.screen = entry.second.screen;
        entry.second.pw = 0;
        g.make_target(info);
    }
}

PictureFigures GlBackend::figures() const { return impl->fig; }

void GlBackend::set_replacements(bool on) { impl->replacements_on = on; }

}  // namespace render
