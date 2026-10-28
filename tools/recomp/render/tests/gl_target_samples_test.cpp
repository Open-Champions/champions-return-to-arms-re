// Authored Windows OpenGL target-allocation regression; no original game inputs.
#include "backend_gl.h"
#include "wgl.h"
#include <cstdio>
#include <cfenv>
#include <cstring>
#include <vector>
using namespace render;
namespace {
unsigned checks = 0, failures = 0;
struct DrawObservation { GLint samples = -1, framebuffer = -1; };
std::vector<DrawObservation> observations;
static decltype(&::glDrawArrays) real_draw;
static decltype(&::glCheckFramebufferStatus) real_check;
static decltype(&::glGenFramebuffers) real_generate;
static decltype(&::glBlitFramebuffer) real_blit;
static decltype(&::glRenderbufferStorageMultisample) real_storage_multisample;
bool round_two_to_four = false;
void APIENTRY storage_multisample(GLenum target, GLsizei samples, GLenum format, GLsizei width, GLsizei height) {
    real_storage_multisample(target, round_two_to_four && samples == 2 ? 4 : samples, format, width, height);
}
int driver_samples(int requested) {
    auto* f = wgl::functions();
    GLuint framebuffer = 0, storage[2] = {};
    f->glGenFramebuffers(1, &framebuffer);
    f->glGenRenderbuffers(2, storage);
    f->glBindFramebuffer(GL_FRAMEBUFFER, framebuffer);
    f->glBindRenderbuffer(GL_RENDERBUFFER, storage[0]);
    f->glRenderbufferStorageMultisample(GL_RENDERBUFFER, requested, GL_RGBA8, 960, 720);
    f->glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, storage[0]);
    f->glBindRenderbuffer(GL_RENDERBUFFER, storage[1]);
    f->glRenderbufferStorageMultisample(GL_RENDERBUFFER, requested, GL_DEPTH_COMPONENT32F, 960, 720);
    f->glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, storage[1]);
    bool complete = f->glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE;
    GLint actual = 0;
    if (complete) f->glGetIntegerv(GL_SAMPLES, &actual);
    GLenum error = f->glGetError();
    f->glBindFramebuffer(GL_FRAMEBUFFER, 0);
    f->glBindRenderbuffer(GL_RENDERBUFFER, 0);
    f->glDeleteFramebuffers(1, &framebuffer);
    f->glDeleteRenderbuffers(2, storage);
    std::fprintf(stderr, "reference request %d gives %d samples (complete=%d error=%u)\n", requested, actual, int(complete), unsigned(error));
    return complete && error == GL_NO_ERROR ? actual : -1;
}
unsigned allocations = 0, forced_failures = 0, depth_blits = 0;
bool fail_next_multisample_check = false;
void check(bool value, const char* name) {
    ++checks;
    if (!value) { ++failures; std::fprintf(stderr, "FAIL %s\n", name); }
}
void APIENTRY draw(GLenum mode, GLint first, GLsizei count) {
    auto* f = wgl::functions();
    DrawObservation o;
    f->glGetIntegerv(GL_SAMPLES, &o.samples);
    f->glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &o.framebuffer);
    observations.push_back(o);
    real_draw(mode, first, count);
}
GLenum APIENTRY framebuffer_status(GLenum target) {
    GLenum result = real_check(target);
    if (fail_next_multisample_check) {
        fail_next_multisample_check = false;
        ++forced_failures;
        return GL_FRAMEBUFFER_UNSUPPORTED;
    }
    return result;
}
void APIENTRY generate(GLsizei count, GLuint* names) {
    allocations += unsigned(count);
    real_generate(count, names);
}
void APIENTRY blit(GLint sx0, GLint sy0, GLint sx1, GLint sy1,
                   GLint dx0, GLint dy0, GLint dx1, GLint dy1, GLbitfield mask, GLenum filter) {
    if (mask & GL_DEPTH_BUFFER_BIT) ++depth_blits;
    real_blit(sx0, sy0, sx1, sy1, dx0, dy0, dx1, dy1, mask, filter);
}
void rectangle(FrameList& f, float x0, float x1, float height, bool green) {
    const float xy[6][2] = {{x0,0},{x1,0},{x0,height},{x0,height},{x1,0},{x1,height}};
    for (const auto& p : xy) {
        Vertex v{}; v.x = p[0]; v.y = p[1]; v.z = .5f;
        v.r = green ? 0 : 255; v.g = green ? 255 : 0; v.a = 128;
        f.vertices.push_back(v);
    }
}
FrameList list(TargetInfo info, bool initial) {
    FrameList f;
    f.targets.push_back(info);
    rectangle(f, 0, float(info.width)/2, float(info.height), false);
    rectangle(f, float(info.width)/2, float(info.width), float(info.height), true);
    DrawCmd d; d.target = info.id; d.count = 12;
    d.scissor[2] = info.width; d.scissor[3] = info.height;
    // Later draws still query actual bound storage but cannot alter the retained image.
    d.mask_rgb = d.mask_a = !initial;
    f.commands.push_back(d);
    return f;
}
bool read(GlBackend& b, std::vector<uint8_t>& pixels) {
    int w = 0, h = 0;
    return b.read_target(1, pixels, w, h) && w == 960 && h == 720
        && pixels.size() == size_t(w)*h*4;
}
void run_case(const char* name, int samples, const std::vector<TargetInfo>& sequence,
              const std::vector<int>& expected, bool force_fallback = false) {
    std::fprintf(stderr, "CASE %s\n", name);
    GlBackend b;
    PictureOptions options; options.samples = samples;
    b.configure(options); b.set_output_size(960,720);
    std::vector<uint8_t> original;
    GLuint last_framebuffer = 0;
    unsigned allocations_after_first = 0;
    for (size_t i = 0; i < sequence.size(); ++i) {
        observations.clear();
        if (!i && force_fallback) fail_next_multisample_check = true;
        b.execute(list(sequence[i], !i));
        check(observations.size() == 1, "one unchanged draw dispatch");
        if (!observations.empty()) {
            check(observations[0].samples == expected[i], "actual draw samples follow current target request");
            if (i && expected[i] != expected[i-1])
                check(GLuint(observations[0].framebuffer) != last_framebuffer, "sample-mode transition replaces draw storage");
            if (i && expected[i] == expected[i-1] && sequence[i].width == sequence[i-1].width
                && sequence[i].height == sequence[i-1].height && sequence[i].screen == sequence[i-1].screen)
                check(GLuint(observations[0].framebuffer) == last_framebuffer, "identical target announcement reuses storage");
            last_framebuffer = GLuint(observations[0].framebuffer);
        }
        std::vector<uint8_t> pixels;
        bool ok = read(b,pixels); check(ok,"read complete physical target");
        if (!i && ok) {
            original = pixels;
            bool pattern = true;
            for (size_t p = 0; p < pixels.size()/4; ++p) {
                bool green = p%960 >= 480;
                pattern &= pixels[p*4+(green?1:0)] > 200 && pixels[p*4+(green?0:1)] == 0 && pixels[p*4+2] == 0;
            }
            check(pattern,"initial authored red/green pattern covers all691200pixels");
        } else if (ok) check(pixels == original,"sample transition preserves every retained RGBA pixel");
        check(wgl::functions()->glGetError() == GL_NO_ERROR,"no GL error");
        if (!i) allocations_after_first = allocations;
        else if (force_fallback) check(allocations == allocations_after_first,"unsupported mode fallback is not repeatedly allocated");
    }
}
void run_depth_case(const char* name, TargetInfo first, TargetInfo second,
                    bool preserve_depth, bool force_second_fallback = false) {
    std::fprintf(stderr, "CASE %s\n", name);
    GlBackend backend;
    PictureOptions options; options.samples = 4;
    backend.configure(options); backend.set_output_size(960,720);
    FrameList initial = list(first, true);
    for (auto& v : initial.vertices) v.z = .8f;
    initial.commands[0].ztst = 2;
    initial.commands[0].depth_test = initial.commands[0].depth_write = true;
    backend.execute(initial);
    std::vector<uint8_t> before, after, control;
    check(read(backend,before), "read initial retained-depth target");
    bool pattern = before.size() == 960u*720u*4u;
    for (size_t p = 0; p < before.size()/4; ++p) {
        bool green = p%960 >= 480;
        pattern &= before[p*4+(green?1:0)] > 200 && before[p*4+(green?0:1)] == 0 && before[p*4+2] == 0;
    }
    check(pattern, "initial depth-writing pattern covers every pixel");
    FrameList behind = list(second, true);
    for (auto& v : behind.vertices) { v.z = .2f; v.r = v.g = 0; v.b = 255; }
    behind.commands[0].ztst = 2;
    behind.commands[0].depth_test = behind.commands[0].depth_write = true;
    unsigned previous_depth_blits = depth_blits;
    if (force_second_fallback) fail_next_multisample_check = true;
    backend.execute(behind);
    check(read(backend,after), "read depth-tested transition target");
    if (preserve_depth) check(after == before, "compatible storage preserves retained depth occlusion");
    else {
        bool blue = after.size() == 960u*720u*4u;
        for (size_t p = 0; p < after.size()/4; ++p)
            blue &= after[p*4] == 0 && after[p*4+1] == 0 && after[p*4+2] > 200;
        check(blue, "incompatible sample counts keep cleared depth so lower geometry draws");
        check(depth_blits == previous_depth_blits, "incompatible sample counts issue no depth blit");
    }
    if (force_second_fallback)
        check(depth_blits == previous_depth_blits + 1, "fallback copies matching actual single-sample depth");
    check(wgl::functions()->glGetError() == GL_NO_ERROR, "depth transfer has no GL error");
    behind.commands[0].ztst = 1;
    backend.execute(behind);
    check(read(backend,control), "read always-pass depth control");
    check(control != before, "always-pass control proves the lower-depth geometry draws");
    check(wgl::functions()->glGetError() == GL_NO_ERROR, "depth control has no GL error");
}
}
int main(int argc, char** argv) {
    if (argc != 1 && (argc != 2 || std::strcmp(argv[1], "--round-two-to-four") != 0)) return 2;
    round_two_to_four = argc == 2;
    std::fesetround(FE_TOWARDZERO);
    check(std::fegetround() == FE_TOWARDZERO, "application rounding mode");
    WNDCLASSW wc{}; wc.style = CS_OWNDC; wc.lpfnWndProc = DefWindowProcW;
    wc.hInstance = GetModuleHandleW(nullptr); wc.lpszClassName = L"ChampionsTargetSamplesRegression";
    if (!RegisterClassW(&wc)) return 2;
    HWND window = CreateWindowW(wc.lpszClassName,L"Champions target samples regression",WS_OVERLAPPEDWINDOW,
                               0,0,64,64,nullptr,nullptr,wc.hInstance,nullptr);
    if (!window) return 3;
    wgl::Context context; std::string error;
    if (!wgl::create(window,context,error) || !context.missing.empty()) {
        std::fprintf(stderr,"context unavailable: %s %s\n",error.c_str(),context.missing.c_str()); return 4;
    }
    auto* f = wgl::functions(); GLint maximum = 0; f->glGetIntegerv(GL_MAX_SAMPLES,&maximum);
    if (maximum < 4) { std::fprintf(stderr,"requires a driver supporting four samples; maximum=%d\n",maximum); return 5; }
    std::fprintf(stderr,"GL %s on %s\n",context.version.c_str(),context.renderer.c_str());
    real_storage_multisample = f->glRenderbufferStorageMultisample;
    if (round_two_to_four) f->glRenderbufferStorageMultisample = storage_multisample;
    // OpenGL 4.1 section 4.4.2 permits rounding a minimum request upward.
    // Use an independent same-format/same-size FBO as the driver's oracle.
    int two_samples = driver_samples(2), four_samples = driver_samples(4);
    if (two_samples < 2 || four_samples < 4) {
        std::fprintf(stderr,"requires usable RGBA8/depth32F multisampled targets\n");
        f->glRenderbufferStorageMultisample = real_storage_multisample;
        return 5;
    }
    real_draw = f->glDrawArrays; real_check = f->glCheckFramebufferStatus; real_generate = f->glGenFramebuffers;
    real_blit = f->glBlitFramebuffer;
    f->glDrawArrays = draw; f->glCheckFramebufferStatus = framebuffer_status; f->glGenFramebuffers = generate;
    f->glBlitFramebuffer = blit;
    run_case("narrow-to-wide",4,{{1,640,224,true},{1,1280,448,true},{1,1280,448,true}},{0,four_samples,four_samples});
    run_case("wide-narrow-wide",4,{{1,1280,448,true},{1,640,224,true},{1,1280,448,true}},{four_samples,0,four_samples});
    run_case("auxiliary-to-screen",4,{{1,480,360,false},{1,1280,448,true}},{0,four_samples});
    run_case("screen-to-auxiliary",4,{{1,1280,448,true},{1,480,360,false}},{four_samples,0});
    run_case("same-mode-logical-reuse",4,{{1,640,224,true},{1,640,448,true},{1,480,360,false}},{0,0,0});
    run_case("antialiasing-off",0,{{1,640,224,true},{1,1280,448,true},{1,480,360,false}},{0,0,0});
    run_case("two-sample-request",2,{{1,640,224,true},{1,1280,448,true},{1,640,224,true}},{0,two_samples,0});
    run_case("unsupported-mode-fallback",4,{{1,1280,448,true},{1,1280,448,true},{1,1280,448,true}},{0,0,0},true);
    run_depth_case("depth-narrow-to-wide",{1,640,224,true},{1,1280,448,true},false);
    run_depth_case("depth-wide-to-narrow",{1,1280,448,true},{1,640,224,true},false);
    run_depth_case("depth-auxiliary-to-screen",{1,480,360,false},{1,1280,448,true},false);
    run_depth_case("depth-screen-to-auxiliary",{1,1280,448,true},{1,480,360,false},false);
    run_depth_case("depth-single-sample-reuse",{1,640,224,true},{1,480,360,false},true);
    run_depth_case("depth-compatible-fallback",{1,640,224,true},{1,1280,448,true},true,true);
    check(forced_failures == 2,"exactly two unsupported-mode responses injected");
    check(!fail_next_multisample_check,"fallback injection was consumed");
    f->glDrawArrays = real_draw; f->glCheckFramebufferStatus = real_check; f->glGenFramebuffers = real_generate;
    f->glBlitFramebuffer = real_blit;
    f->glRenderbufferStorageMultisample = real_storage_multisample;
    std::printf("{\"checks\":%u,\"failures\":%u,\"authored_inputs_only\":true,\"production_gl_backend\":true,\"pixels_per_target\":691200,\"simulated_two_to_four_rounding\":%s,\"actual_for_request2\":%d,\"actual_for_request4\":%d}\n",checks,failures,round_two_to_four?"true":"false",two_samples,four_samples);
    wglMakeCurrent(nullptr,nullptr); wglDeleteContext(context.rc); ReleaseDC(window,context.dc); DestroyWindow(window);
    return failures ? 1 : 0;
}
