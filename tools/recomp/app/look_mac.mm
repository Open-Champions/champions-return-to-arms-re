// look_mac.mm - see look_host.h.  While the pointer is held it is dissociated from the mouse
// (it stays where it was, inside the window, so clicks still reach the window) and the
// mouse's own motion is read from the events' deltas.
#include "look_host.h"
#include "fpcontrols.h"

#import <AppKit/AppKit.h>
#import <CoreGraphics/CoreGraphics.h>

#include <cstdio>
#include <string>

namespace hostlook {

static id g_monitor = nil;
static bool g_captured = false;

void start() {
    if (g_monitor) return;
    NSEventMask mask = NSEventMaskMouseMoved | NSEventMaskLeftMouseDragged | NSEventMaskRightMouseDragged | NSEventMaskOtherMouseDragged;
    g_monitor = [NSEvent addLocalMonitorForEventsMatchingMask:mask handler:^NSEvent*(NSEvent* event) {
        // deltaX grows to the right, deltaY downward
        if (g_captured) fpcontrols::mouse_motion((float)event.deltaX, (float)event.deltaY);
        return event;
    }];
}

void capture(bool on) {
    if (on == g_captured) return;
    if (on) {
        // the pointer goes to the middle of the game's window first, so that a click lands in it
        NSWindow* window = [NSApp keyWindow];
        if (!window) return;
        NSRect frame = [window contentRectForFrameRect:window.frame];
        CGFloat top = NSMaxY([NSScreen screens].firstObject.frame);      // Quartz counts from the top of the first screen
        CGWarpMouseCursorPosition(CGPointMake(NSMidX(frame), top - NSMidY(frame)));
        CGAssociateMouseAndMouseCursorPosition(false);
        [NSCursor hide];
    } else {
        CGAssociateMouseAndMouseCursorPosition(true);
        [NSCursor unhide];
    }
    g_captured = on;
}

bool captured() { return g_captured; }

std::string state() {
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    bool visible = CGCursorIsVisible();
#pragma clang diagnostic pop
    NSWindow* key = NSApp ? [NSApp keyWindow] : nil;
    char text[160];
    snprintf(text, sizeof text, "pointer: held=%d shown=%d; this program in front=%d, a window of it has the keyboard=%d", (int)g_captured, (int)visible,
             NSApp != nil && [NSApp isActive], key != nil);
    return text;
}

}  // namespace hostlook
