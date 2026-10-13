// present_mac.mm - see present_host.h.
//
// Three parties: the drawing thread (OpenGL: begin, show), a presenter thread of this
// file's own (Metal: the layer's next drawable, the copy, the present), and the system,
// which says afterwards when a picture was on the glass.  Two pictures go round between
// the first two, so that the drawing thread never waits for the layer: CAMetalLayer's
// nextDrawable stands for up to a second when the display is asleep or the compositor is
// not taking pictures, and a picture that finds both in use is simply not shown.
#define GL_SILENCE_DEPRECATION 1
#include "present_host.h"

#import <AppKit/AppKit.h>
#import <IOSurface/IOSurface.h>
#import <Metal/Metal.h>
#import <QuartzCore/CAMetalLayer.h>
#import <OpenGL/CGLIOSurface.h>
#import <OpenGL/OpenGL.h>
#import <OpenGL/gl3.h>
#include <pthread.h>
#include <pthread/qos.h>

#include <atomic>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <thread>
#include <vector>

namespace hostpresent {

// One picture on its way: an IOSurface seen by OpenGL (a rectangle texture in a
// framebuffer) and by Metal (a texture).
struct Picture {
    IOSurfaceRef surface = nullptr;
    id<MTLTexture> texture = nil;
    GLuint gl_texture = 0, framebuffer = 0;
    int width = 0, height = 0;
    std::atomic<bool> held{false};              // the presenter (or the graphics card's copy) still needs it
};

struct Surface {
    CAMetalLayer* layer = nil;
    id<MTLDevice> device = nil;
    id<MTLCommandQueue> queue = nil;
    Picture pictures[2];
    int drawing = -1;                           // the one begin() gave out (drawing thread)
    // hand-over to the presenter
    std::mutex lock;
    std::condition_variable work;
    int waiting = -1;                           // picture to present, -1: none
    double waiting_offset_ms = 0, waiting_due_ms = 0;
    std::atomic<unsigned long long> presented{0}, refused{0}, skipped{0};
    std::atomic<double> longest_ms{0};          // the longest the layer kept the presenter waiting for a drawable
    std::mutex glass_lock;
    std::vector<Glass> glass;                   // filled by the layer's presented handlers (a thread of the system's)
    void (*log)(const std::string&) = nullptr;
};

static void presenter(Surface* s) {
    pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
    pthread_setname_np("rta presenter");
    for (;;) {
        int index;
        double offset_ms, due_ms;
        {
            std::unique_lock<std::mutex> hold(s->lock);
            s->work.wait(hold, [s] { return s->waiting >= 0; });
            index = s->waiting; offset_ms = s->waiting_offset_ms; due_ms = s->waiting_due_ms;
            s->waiting = -1;
        }
        Picture* p = &s->pictures[index];
        @autoreleasepool {
            CFTimeInterval t0 = CACurrentMediaTime();
            id<CAMetalDrawable> drawable = [s->layer nextDrawable];
            double took = (CACurrentMediaTime() - t0) * 1000.0;
            if (took > s->longest_ms) s->longest_ms = took;
            id<MTLTexture> target = drawable.texture;
            if (!drawable || (int)target.width != p->width || (int)target.height != p->height) { s->refused++; p->held = false; continue; }
            id<MTLCommandBuffer> commands = [s->queue commandBuffer];
            id<MTLBlitCommandEncoder> copy = [commands blitCommandEncoder];
            [copy copyFromTexture:p->texture sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0) sourceSize:MTLSizeMake(p->width, p->height, 1)
                        toTexture:target destinationSlice:0 destinationLevel:0 destinationOrigin:MTLOriginMake(0, 0, 0)];
            [copy endEncoding];
            [drawable addPresentedHandler:^(id<MTLDrawable> shown) {
                CFTimeInterval at = shown.presentedTime;
                std::lock_guard<std::mutex> hold(s->glass_lock);
                if (s->glass.size() < 100000) s->glass.push_back({due_ms, at > 0 ? at * 1000.0 + offset_ms : 0.0});
            }];
            // the picture is free for OpenGL again when the copy has been made
            [commands addCompletedHandler:^(id<MTLCommandBuffer>) { p->held = false; }];
            [commands presentDrawable:drawable];
            [commands commit];
            s->presented++;
        }
    }
}

Surface* create(void* native_view, void (*log)(const std::string& line)) {
    NSView* view = (__bridge NSView*)native_view;
    CALayer* layer = view.layer;
    // (Qt 6 gives the view a container layer and puts the Metal layer inside it)
    std::string seen = layer ? NSStringFromClass([layer class]).UTF8String : "none";
    for (int depth = 0; depth < 3 && layer && ![layer isKindOfClass:[CAMetalLayer class]]; depth++) {
        CALayer* inner = nil;
        for (CALayer* sub in layer.sublayers) {
            seen += std::string(" > ") + NSStringFromClass([sub class]).UTF8String;
            if (!inner || [sub isKindOfClass:[CAMetalLayer class]]) inner = sub;
        }
        layer = inner;
    }
    if (![layer isKindOfClass:[CAMetalLayer class]]) {
        if (log) log("present: the window has no Metal layer (its layers: " + seen + ")");
        return nullptr;
    }
    Surface* s = new Surface;
    s->log = log;
    s->layer = (CAMetalLayer*)layer;
    s->device = s->layer.device ?: MTLCreateSystemDefaultDevice();
    if (!s->device) { if (log) log("present: no Metal device"); delete s; return nullptr; }
    s->layer.device = s->device;
    s->layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
    s->layer.framebufferOnly = NO;              // the drawable is the destination of a copy
    s->layer.opaque = YES;
    s->layer.displaySyncEnabled = YES;
    s->layer.presentsWithTransaction = NO;      // straight to the compositor, not with the main thread's transaction
    s->queue = [s->device newCommandQueue];
    std::thread(presenter, s).detach();
    if (log) log(std::string("present: through a Metal layer on ") + s->device.name.UTF8String + " (OpenGL draws into a surface shared with it; layers: " + seen + ")");
    return s;
}

static void release_picture(Picture* p) {
    if (p->framebuffer) { glDeleteFramebuffers(1, &p->framebuffer); p->framebuffer = 0; }
    if (p->gl_texture) { glDeleteTextures(1, &p->gl_texture); p->gl_texture = 0; }
    p->texture = nil;
    if (p->surface) { CFRelease(p->surface); p->surface = nullptr; }
    p->width = p->height = 0;
}

static bool make_picture(Surface* s, Picture* p, int width, int height) {
    release_picture(p);
    NSDictionary* properties = @{(id)kIOSurfaceWidth: @(width), (id)kIOSurfaceHeight: @(height), (id)kIOSurfaceBytesPerElement: @4,
                                 (id)kIOSurfacePixelFormat: @((unsigned)'BGRA')};
    p->surface = IOSurfaceCreate((__bridge CFDictionaryRef)properties);
    if (!p->surface) { if (s->log) s->log("present: no IOSurface of " + std::to_string(width) + " x " + std::to_string(height)); return false; }
    GLint bound_texture = 0, bound_framebuffer = 0;
    glGetIntegerv(GL_TEXTURE_BINDING_RECTANGLE, &bound_texture);
    glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &bound_framebuffer);
    glGenTextures(1, &p->gl_texture);
    glBindTexture(GL_TEXTURE_RECTANGLE, p->gl_texture);
    CGLError error = CGLTexImageIOSurface2D(CGLGetCurrentContext(), GL_TEXTURE_RECTANGLE, GL_RGBA, width, height, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, p->surface, 0);
    glTexParameteri(GL_TEXTURE_RECTANGLE, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_RECTANGLE, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glGenFramebuffers(1, &p->framebuffer);
    glBindFramebuffer(GL_FRAMEBUFFER, p->framebuffer);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_RECTANGLE, p->gl_texture, 0);
    GLenum status = glCheckFramebufferStatus(GL_FRAMEBUFFER);
    glBindTexture(GL_TEXTURE_RECTANGLE, (GLuint)bound_texture);
    glBindFramebuffer(GL_FRAMEBUFFER, (GLuint)bound_framebuffer);
    MTLTextureDescriptor* descriptor = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm width:width height:height mipmapped:NO];
    descriptor.usage = MTLTextureUsageShaderRead;
    p->texture = [s->device newTextureWithDescriptor:descriptor iosurface:p->surface plane:0];
    if (error != kCGLNoError || status != GL_FRAMEBUFFER_COMPLETE || !p->texture) {
        char text[160];
        snprintf(text, sizeof text, "present: the shared surface of %d x %d could not be set up (CGL %d, framebuffer 0x%x, Metal texture %s)", width, height, (int)error,
                 (unsigned)status, p->texture ? "yes" : "no");
        if (s->log) s->log(text);
        release_picture(p);
        return false;
    }
    p->width = width; p->height = height;
    return true;
}

unsigned begin(Surface* s, int width, int height) {
    if (!s || width < 1 || height < 1) return 0;
    s->drawing = -1;
    // the picture the presenter is not holding (the one used last first: its surface is warm)
    for (int k = 0; k < 2; k++) {
        Picture* p = &s->pictures[k];
        if (p->held.load()) continue;
        if (p->width != width || p->height != height) {
            if (!make_picture(s, p, width, height)) return 0;
            CGSize size = CGSizeMake(width, height);
            if (!CGSizeEqualToSize(s->layer.drawableSize, size)) s->layer.drawableSize = size;
        }
        s->drawing = k;
        return p->framebuffer;
    }
    s->skipped++;                               // both are on their way: the layer is not taking pictures just now
    return 0;
}

bool show(Surface* s, double now_ms, double due_ms) {
    if (!s || s->drawing < 0) return false;
    int index = s->drawing;
    s->drawing = -1;
    glFlush();                                  // (the caller has finished or flushed; a flush costs nothing then)
    {
        std::lock_guard<std::mutex> hold(s->lock);
        if (s->waiting >= 0) {
            // the one handed over before has not even been taken: this newer one replaces it
            s->pictures[s->waiting].held = false;
            s->skipped++;
        }
        s->pictures[index].held = true;
        s->waiting = index;
        s->waiting_offset_ms = now_ms - CACurrentMediaTime() * 1000.0;     // the caller's clock against the one presentedTime is told on
        s->waiting_due_ms = due_ms;
    }
    s->work.notify_one();
    return true;
}

void glass(Surface* s, std::vector<Glass>& out) {
    out.clear();
    if (!s) return;
    std::lock_guard<std::mutex> hold(s->glass_lock);
    out.swap(s->glass);
}

bool read(Surface* s, std::vector<unsigned char>& bgra, int& width, int& height) {
    if (!s) return false;
    // the one drawn last and not being drawn now: either will do for a test's look
    Picture* p = s->pictures[0].surface ? &s->pictures[0] : &s->pictures[1];
    if (!p->surface) return false;
    IOSurfaceLock(p->surface, kIOSurfaceLockReadOnly, nullptr);
    width = p->width; height = p->height;
    size_t stride = IOSurfaceGetBytesPerRow(p->surface);
    const unsigned char* base = (const unsigned char*)IOSurfaceGetBaseAddress(p->surface);
    bgra.resize((size_t)width * height * 4);
    for (int y = 0; y < height; y++) memcpy(bgra.data() + (size_t)y * width * 4, base + y * stride, (size_t)width * 4);
    IOSurfaceUnlock(p->surface, kIOSurfaceLockReadOnly, nullptr);
    return true;
}

void figures(Surface* s, unsigned long long& presented, unsigned long long& refused, unsigned long long& skipped, double& longest_wait_ms) {
    presented = s ? s->presented.load() : 0;
    refused = s ? s->refused.load() : 0;
    skipped = s ? s->skipped.load() : 0;
    longest_wait_ms = s ? s->longest_ms.load() : 0;
}

}  // namespace hostpresent
