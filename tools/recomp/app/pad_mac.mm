// pad_mac.mm - pad_host.h on macOS, through GameController.framework.
//
// The framework knows the layout of the controllers macOS supports (DualSense, DualShock 4,
// Xbox, Switch Pro and others, by USB or Bluetooth) and presents each as the same "extended
// gamepad": two sticks, a direction pad, four face buttons, two shoulders, two triggers,
// two stick buttons, Menu and Options.  That is a PlayStation 2 pad, so nothing has to be
// bound.  Map and dead zones are those of the emulator-based application
// (tools/play-net/src/RtaPad.mm), written against rta::PadState.
#import <AppKit/AppKit.h>
#import <Foundation/Foundation.h>
#import <GameController/GameController.h>

#include "pad_host.h"

#include <array>
#include <atomic>
#include <cmath>
#include <mutex>

namespace {

// Sticks: nothing inside this part of the way out (a worn stick does not rest at the
// middle), then evenly up to the edge.  Triggers: pressed beyond this part of the way.
const float STICK_DEAD_ZONE = 0.15f;
const float TRIGGER_PRESSED = 0.30f;

std::mutex g_mutex;                         // the list and the name
NSMutableArray<GCController*>* g_pads;      // extended gamepads, in the order they came
GCController* g_simulated = nil;            // the one a test makes; also in g_pads
std::string g_name;
std::atomic<uint32_t> g_generation{0};
std::atomic<bool> g_active{false};          // this application is the one in front
std::atomic<bool> g_started{false};
void (*g_log)(const std::string&) = nullptr;

std::string text(NSString* s) { return s ? std::string([s UTF8String]) : std::string(); }

std::string describe(GCController* c) {
    if (c == g_simulated) return "simulated controller";
    std::string category = text(c.productCategory), vendor = text(c.vendorName);
    if (category.empty()) return vendor.empty() ? "game controller" : vendor;
    return category;
}

void changed(const char* what, GCController* c) {       // main thread
    std::string line;
    {
        std::lock_guard<std::mutex> hold(g_mutex);
        g_name = [g_pads count] ? describe(g_pads[0]) : std::string();
        line = std::string("controller ") + what + ": " + describe(c);
        std::string vendor = text(c.vendorName);
        if (!vendor.empty() && c != g_simulated) line += " (" + vendor + ")";
        if (![c extendedGamepad]) line += " - not a gamepad with two sticks, left alone";
        line += "; port 1 is now " + (g_name.empty() ? std::string("the keyboard only") : "the keyboard and " + g_name);
        g_generation++;
    }
    if (g_log) g_log(line);
}

void attached(GCController* c) {
    if (!c) return;
    {
        std::lock_guard<std::mutex> hold(g_mutex);
        if ([g_pads containsObject:c]) return;
        // a test's controller goes in front of a real one, so that it is the one read
        if (c == g_simulated) [g_pads insertObject:c atIndex:0];
        else if ([c extendedGamepad]) [g_pads addObject:c];
    }
    changed("attached", c);
}

void detached(GCController* c) {
    if (!c) return;
    bool known;
    {
        std::lock_guard<std::mutex> hold(g_mutex);
        known = [g_pads containsObject:c];
    }
    if (!known && [c extendedGamepad]) return;
    {
        std::lock_guard<std::mutex> hold(g_mutex);
        [g_pads removeObject:c];
    }
    changed("detached", c);
}

uint8_t axis_byte(float v) {                // -1 .. 1 to 0 .. 255 with 128 in the middle
    float scaled = v >= 0 ? 128.0f + v * 127.0f : 128.0f + v * 128.0f;
    long r = std::lround(scaled);
    return (uint8_t)(r < 0 ? 0 : r > 255 ? 255 : r);
}

// A stick as the two bytes of a PlayStation 2 pad (up and left are 0).
void stick(GCControllerDirectionPad* s, uint8_t& out_x, uint8_t& out_y) {
    float x = s.xAxis.value, y = s.yAxis.value;
    float length = std::sqrt(x * x + y * y);
    if (!(length > STICK_DEAD_ZONE)) { out_x = out_y = 128; return; }
    float wanted = (length - STICK_DEAD_ZONE) / (1.0f - STICK_DEAD_ZONE);
    if (wanted > 1.0f) wanted = 1.0f;
    out_x = axis_byte(x / length * wanted);
    out_y = axis_byte(-(y / length * wanted));
}

// The whole map, in one place.
void read_controller(GCController* c, rta::PadState& state) {
    GCExtendedGamepad* pad = [c extendedGamepad];
    if (!pad) return;
    uint16_t b = 0;
    auto set = [&](bool pressed, uint16_t bit) { if (pressed) b |= bit; };
    // by place, as on a PlayStation pad: A is the bottom button, B the right one, X the
    // left one, Y the top one
    set(pad.buttonA.pressed, rta::PAD_CROSS);
    set(pad.buttonB.pressed, rta::PAD_CIRCLE);
    set(pad.buttonX.pressed, rta::PAD_SQUARE);
    set(pad.buttonY.pressed, rta::PAD_TRIANGLE);
    set(pad.dpad.up.pressed, rta::PAD_UP);
    set(pad.dpad.down.pressed, rta::PAD_DOWN);
    set(pad.dpad.left.pressed, rta::PAD_LEFT);
    set(pad.dpad.right.pressed, rta::PAD_RIGHT);
    set(pad.leftShoulder.pressed, rta::PAD_L1);
    set(pad.rightShoulder.pressed, rta::PAD_R1);
    set(pad.leftTrigger.value > TRIGGER_PRESSED, rta::PAD_L2);      // the game takes L2 and R2 as buttons
    set(pad.rightTrigger.value > TRIGGER_PRESSED, rta::PAD_R2);
    set(pad.leftThumbstickButton && pad.leftThumbstickButton.pressed, rta::PAD_L3);
    set(pad.rightThumbstickButton && pad.rightThumbstickButton.pressed, rta::PAD_R3);
    // Menu is Options on a DualSense, Start elsewhere; Options is Create / Share / Back / View
    set(pad.buttonMenu.pressed, rta::PAD_START);
    set(pad.buttonOptions && pad.buttonOptions.pressed, rta::PAD_SELECT);
    if (@available(macOS 11.0, *)) {        // a Sony pad's touchpad, pressed, is Select too
        GCControllerButtonInput* touchpad = c.physicalInputProfile.buttons[GCInputDualShockTouchpadButton];
        set(touchpad && touchpad.pressed, rta::PAD_SELECT);
    }
    state.buttons = b;
    stick(pad.leftThumbstick, state.lx, state.ly);
    stick(pad.rightThumbstick, state.rx, state.ry);
}

}  // namespace

namespace hostpad {

void start(void (*log)(const std::string&)) {
    if (g_started.exchange(true)) return;
    g_log = log;
    g_pads = [[NSMutableArray alloc] init];
    NSNotificationCenter* center = [NSNotificationCenter defaultCenter];
    NSOperationQueue* queue = [NSOperationQueue mainQueue];
    [center addObserverForName:GCControllerDidConnectNotification object:nil queue:queue usingBlock:^(NSNotification* note) { attached((GCController*)note.object); }];
    [center addObserverForName:GCControllerDidDisconnectNotification object:nil queue:queue usingBlock:^(NSNotification* note) { detached((GCController*)note.object); }];
    // Only the application in front listens to the controller: two copies on one Mac would
    // otherwise both move, and what was held when the application was left would stay held.
    [center addObserverForName:NSApplicationDidBecomeActiveNotification object:nil queue:queue usingBlock:^(NSNotification*) { g_active = true; }];
    [center addObserverForName:NSApplicationDidResignActiveNotification object:nil queue:queue usingBlock:^(NSNotification*) { g_active = false; }];
    g_active = [NSApp isActive];
    [NSTimer scheduledTimerWithTimeInterval:0.5 repeats:YES block:^(NSTimer*) { g_active = [NSApp isActive]; }];
    for (GCController* c in [GCController controllers]) attached(c);      // those attached before the start
    bool none;
    {
        std::lock_guard<std::mutex> hold(g_mutex);
        none = [g_pads count] == 0;
    }
    if (none && g_log) g_log("controller: none known yet; one that is attached (or found in a moment) is taken up at once");
}

bool read(rta::PadState& state) {
    if (!g_started) return false;
    @autoreleasepool {
        std::lock_guard<std::mutex> hold(g_mutex);
        if ([g_pads count] == 0) return false;
        GCController* c = g_pads[0];
        if (!g_active && c != g_simulated) return false;
        read_controller(c, state);
    }
    return true;
}

std::string name() {
    std::lock_guard<std::mutex> hold(g_mutex);
    return g_name;
}

uint32_t generation() { return g_generation; }

void test(const std::string& command, uint16_t buttons, const float values[6]) {
    if (!g_started) return;
    std::string what = command;
    std::array<float, 6> v;
    for (int i = 0; i < 6; i++) v[i] = values ? values[i] : 0.0f;
    dispatch_async(dispatch_get_main_queue(), ^{
        if (what == "connect") {
            if (g_simulated) return;
            GCController* c = [GCController controllerWithExtendedGamepad];
#if !__has_feature(objc_arc)
            [c retain];
#endif
            g_simulated = c;
            [[NSNotificationCenter defaultCenter] postNotificationName:GCControllerDidConnectNotification object:c];
        } else if (what == "disconnect") {
            if (!g_simulated) return;
            GCController* c = g_simulated;
            [[NSNotificationCenter defaultCenter] postNotificationName:GCControllerDidDisconnectNotification object:c];
            g_simulated = nil;
#if !__has_feature(objc_arc)
            [c release];
#endif
        } else if (what == "set") {
            if (!g_simulated) return;
            GCExtendedGamepad* pad = [g_simulated extendedGamepad];
            auto on = [&](uint16_t bit) { return (buttons & bit) ? 1.0f : 0.0f; };
            // the other way round from read_controller(), written out again on purpose
            [pad.buttonA setValue:on(rta::PAD_CROSS)];
            [pad.buttonB setValue:on(rta::PAD_CIRCLE)];
            [pad.buttonX setValue:on(rta::PAD_SQUARE)];
            [pad.buttonY setValue:on(rta::PAD_TRIANGLE)];
            [pad.dpad setValueForXAxis:on(rta::PAD_RIGHT) - on(rta::PAD_LEFT) yAxis:on(rta::PAD_UP) - on(rta::PAD_DOWN)];
            [pad.leftShoulder setValue:on(rta::PAD_L1)];
            [pad.rightShoulder setValue:on(rta::PAD_R1)];
            [pad.leftTrigger setValue:on(rta::PAD_L2) != 0 ? 1.0f : v[4]];
            [pad.rightTrigger setValue:on(rta::PAD_R2) != 0 ? 1.0f : v[5]];
            [pad.leftThumbstickButton setValue:on(rta::PAD_L3)];
            [pad.rightThumbstickButton setValue:on(rta::PAD_R3)];
            [pad.buttonMenu setValue:on(rta::PAD_START)];
            [pad.buttonOptions setValue:on(rta::PAD_SELECT)];
            [pad.leftThumbstick setValueForXAxis:v[0] yAxis:v[1]];
            [pad.rightThumbstick setValueForXAxis:v[2] yAxis:v[3]];
        }
    });
}

void keep_timers() {
    static id activity;
    if (activity) return;
    activity = [[NSProcessInfo processInfo] beginActivityWithOptions:(NSActivityUserInitiatedAllowingIdleSystemSleep | NSActivityLatencyCritical)
                                                              reason:@"the game is running"];
}

}  // namespace hostpad
