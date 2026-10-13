// present_mac.mm - see present_host.h.
#define GL_SILENCE_DEPRECATION 1
#include "present_host.h"

#import <AppKit/AppKit.h>
#import <IOSurface/IOSurface.h>
#import <Metal/Metal.h>
#import <QuartzCore/CAMetalLayer.h>
#import <OpenGL/CGLIOSurface.h>
#import <OpenGL/OpenGL.h>
#import <OpenGL/gl3.h>

#include <atomic>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <vector>

namespace hostpresent {

struct Surface {
    CAMetalLayer* layer = nil;
    id<MTLDevice> device = nil;
    id<MTLCommandQueue> queue = nil;
    // the picture on its way: one IOSurface seen by OpenGL (a rectangle texture in a
    // framebuffer) and by Metal (a texture)
    IOSurfaceRef surface = nullptr;
    id<MTLTexture> texture = nil;
    GLuint gl_texture = 0, framebuffer = 0;
    int width = 0, height = 0;
    std::atomic<unsigned long long> presented{0}, refused{0};
    std::mutex glass_lock;
    std::vector<Glass> glass;                   // filled by the layer's presented handlers (a thread of the system's)
    void (*log)(const std::string&) = nullptr;
};

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
    if (log) log("present: the window's layers: " + seen);
    if (![layer isKindOfClass:[CAMetalLayer class]]) {
        if (log) log(std::string("present: the window's layer is not a Metal layer (") + (layer ? NSStringFromClass([layer class]).UTF8String : "none") + ")");
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
    if (log) log(std::string("present: through a Metal layer on ") + s->device.name.UTF8String + " (OpenGL draws into a surface shared with it)");
    return s;
}

static void release_picture(Surface* s) {
    if (s->framebuffer) { glDeleteFramebuffers(1, &s->framebuffer); s->framebuffer = 0; }
    if (s->gl_texture) { glDeleteTextures(1, &s->gl_texture); s->gl_texture = 0; }
    s->texture = nil;
    if (s->surface) { CFRelease(s->surface); s->surface = nullptr; }
    s->width = s->height = 0;
}

unsigned begin(Surface* s, int width, int height) {
    if (!s || width < 1 || height < 1) return 0;
    if (width == s->width && height == s->height && s->framebuffer) return s->framebuffer;
    release_picture(s);
    NSDictionary* properties = @{(id)kIOSurfaceWidth: @(width), (id)kIOSurfaceHeight: @(height), (id)kIOSurfaceBytesPerElement: @4,
                                 (id)kIOSurfacePixelFormat: @((unsigned)'BGRA')};
    s->surface = IOSurfaceCreate((__bridge CFDictionaryRef)properties);
    if (!s->surface) { if (s->log) s->log("present: no IOSurface of " + std::to_string(width) + " x " + std::to_string(height)); return 0; }
    GLint bound_texture = 0, bound_framebuffer = 0;
    glGetIntegerv(GL_TEXTURE_BINDING_RECTANGLE, &bound_texture);
    glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &bound_framebuffer);
    glGenTextures(1, &s->gl_texture);
    glBindTexture(GL_TEXTURE_RECTANGLE, s->gl_texture);
    CGLError error = CGLTexImageIOSurface2D(CGLGetCurrentContext(), GL_TEXTURE_RECTANGLE, GL_RGBA, width, height, GL_BGRA, GL_UNSIGNED_INT_8_8_8_8_REV, s->surface, 0);
    glTexParameteri(GL_TEXTURE_RECTANGLE, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_RECTANGLE, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glGenFramebuffers(1, &s->framebuffer);
    glBindFramebuffer(GL_FRAMEBUFFER, s->framebuffer);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_RECTANGLE, s->gl_texture, 0);
    GLenum status = glCheckFramebufferStatus(GL_FRAMEBUFFER);
    glBindTexture(GL_TEXTURE_RECTANGLE, (GLuint)bound_texture);
    glBindFramebuffer(GL_FRAMEBUFFER, (GLuint)bound_framebuffer);
    MTLTextureDescriptor* descriptor = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatBGRA8Unorm width:width height:height mipmapped:NO];
    descriptor.usage = MTLTextureUsageShaderRead;
    s->texture = [s->device newTextureWithDescriptor:descriptor iosurface:s->surface plane:0];
    if (error != kCGLNoError || status != GL_FRAMEBUFFER_COMPLETE || !s->texture) {
        char text[160];
        snprintf(text, sizeof text, "present: the shared surface of %d x %d could not be set up (CGL %d, framebuffer 0x%x, Metal texture %s)", width, height, (int)error,
                 (unsigned)status, s->texture ? "yes" : "no");
        if (s->log) s->log(text);
        release_picture(s);
        return 0;
    }
    s->width = width; s->height = height;
    s->layer.drawableSize = CGSizeMake(width, height);
    return s->framebuffer;
}

bool show(Surface* s, double now_ms, double due_ms) {
    if (!s || !s->texture) return false;
    @autoreleasepool {
        id<CAMetalDrawable> drawable = [s->layer nextDrawable];
        id<MTLTexture> target = drawable.texture;
        if (!drawable || (int)target.width != s->width || (int)target.height != s->height) { s->refused++; return false; }
        id<MTLCommandBuffer> commands = [s->queue commandBuffer];
        id<MTLBlitCommandEncoder> copy = [commands blitCommandEncoder];
        [copy copyFromTexture:s->texture sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0, 0, 0) sourceSize:MTLSizeMake(s->width, s->height, 1)
                    toTexture:target destinationSlice:0 destinationLevel:0 destinationOrigin:MTLOriginMake(0, 0, 0)];
        [copy endEncoding];
        // the caller's clock against the one presentedTime is told on
        double offset_ms = now_ms - CACurrentMediaTime() * 1000.0;
        [drawable addPresentedHandler:^(id<MTLDrawable> shown) {
            CFTimeInterval at = shown.presentedTime;
            std::lock_guard<std::mutex> hold(s->glass_lock);
            if (s->glass.size() < 100000) s->glass.push_back({due_ms, at > 0 ? at * 1000.0 + offset_ms : 0.0});
        }];
        [commands presentDrawable:drawable];
        [commands commit];
        s->presented++;
    }
    return true;
}

bool read(Surface* s, std::vector<unsigned char>& bgra, int& width, int& height) {
    if (!s || !s->surface) return false;
    IOSurfaceLock(s->surface, kIOSurfaceLockReadOnly, nullptr);
    width = s->width; height = s->height;
    size_t stride = IOSurfaceGetBytesPerRow(s->surface);
    const unsigned char* base = (const unsigned char*)IOSurfaceGetBaseAddress(s->surface);
    bgra.resize((size_t)width * height * 4);
    for (int y = 0; y < height; y++) memcpy(bgra.data() + (size_t)y * width * 4, base + y * stride, (size_t)width * 4);
    IOSurfaceUnlock(s->surface, kIOSurfaceLockReadOnly, nullptr);
    return true;
}

void glass(Surface* s, std::vector<Glass>& out) {
    out.clear();
    if (!s) return;
    std::lock_guard<std::mutex> hold(s->glass_lock);
    out.swap(s->glass);
}

void figures(Surface* s, unsigned long long& presented, unsigned long long& refused) {
    presented = s ? s->presented.load() : 0;
    refused = s ? s->refused.load() : 0;
}

}  // namespace hostpresent
