// look_mac.mm - see look_host.h.  While the pointer is held it is dissociated from the mouse
// (it stays where it was, inside the window, so clicks still reach the window) and the
// mouse's own motion is read from the events' deltas.
#include "look_host.h"
#include "fpcontrols.h"

#import <AppKit/AppKit.h>
#import <CoreGraphics/CoreGraphics.h>

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

}  // namespace hostlook
