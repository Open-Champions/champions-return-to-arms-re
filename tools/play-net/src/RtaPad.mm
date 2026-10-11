// Game controllers, through macOS's GameController framework. See Rta.h.
//
// Play!'s own controller support on macOS reads HID reports itself and leaves it to the
// player to bind every button in the Controller Manager. The framework used here knows
// the layout of the controllers macOS supports - DualSense, DualShock 4, Xbox, Switch Pro
// and others, by USB or Bluetooth - and presents each as the same "extended gamepad":
// two sticks, a direction pad, four face buttons, two shoulders, two triggers, two stick
// buttons, Menu and Options. That is a PlayStation 2 pad, so nothing has to be bound:
// the first controller that is attached is the pad in port 1, on top of whatever the
// keyboard and Play!'s own bindings say.
//
// The controller is read where the machine reads its pad (once a frame, on the machine's
// thread, immediately before the frame is computed), so it adds no delay of its own.
#import <AppKit/AppKit.h>
#import <Foundation/Foundation.h>
#import <GameController/GameController.h>
#include <array>
#include <atomic>
#include <cmath>
#include <mutex>
#include <string>
#include "ControllerInfo.h"
#include "Rta.h"

namespace
{
	typedef PS2::CControllerInfo::BUTTON Button;

	// Sticks: nothing inside this part of the way out (a worn stick does not rest at the
	// middle), then evenly up to the edge. Triggers: pressed beyond this part of the way.
	const float STICK_DEAD_ZONE = 0.15f;
	const float TRIGGER_PRESSED = 0.30f;

	std::mutex g_mutex;                    // the list and the name
	NSMutableArray<GCController*>* g_pads; // extended gamepads, in the order they came
	GCController* g_simulated = nil;       // the one the tests make; also in g_pads
	std::string g_name;                    // of the first one; empty: none
	std::atomic<uint32_t> g_generation{0}; // counts every change of the list
	std::atomic<bool> g_active{false};     // this application is the one in front
	std::atomic<bool> g_started{false};

	std::string Text(NSString* string)
	{
		return string ? std::string([string UTF8String]) : std::string();
	}

	std::string Describe(GCController* controller)
	{
		if(controller == g_simulated) return "simulated controller";
		std::string category = Text(controller.productCategory);
		std::string vendor = Text(controller.vendorName);
		if(category.empty()) return vendor.empty() ? "game controller" : vendor;
		return category;
	}

	// main thread
	void Changed(const char* what, GCController* controller)
	{
		std::string line;
		{
			std::lock_guard<std::mutex> lock(g_mutex);
			g_name = ([g_pads count] != 0) ? Describe(g_pads[0]) : std::string();
			line = std::string("controller ") + what + ": " + Describe(controller);
			std::string vendor = Text(controller.vendorName);
			if(!vendor.empty() && (controller != g_simulated)) line += " (" + vendor + ")";
			if(![controller extendedGamepad]) line += " - not a gamepad with two sticks, left alone";
			line += "; port 1 is now " + (g_name.empty() ? std::string("the keyboard only") : g_name);
			g_generation++;
		}
		Rta::LogLine(line);
	}

	void Attached(GCController* controller)
	{
		if(!controller) return;
		{
			std::lock_guard<std::mutex> lock(g_mutex);
			if([g_pads containsObject:controller]) return;
			// a test's controller goes in front of a real one, so that it is the one read
			if(controller == g_simulated)
				[g_pads insertObject:controller atIndex:0];
			else if([controller extendedGamepad])
				[g_pads addObject:controller];
		}
		Changed("attached", controller);
	}

	void Detached(GCController* controller)
	{
		if(!controller) return;
		bool known = false;
		{
			std::lock_guard<std::mutex> lock(g_mutex);
			known = [g_pads containsObject:controller];
		}
		if(!known && [controller extendedGamepad]) return;
		// logged while it is still in the list, then taken out (the list keeps it alive
		// for the machine's thread until then)
		{
			std::lock_guard<std::mutex> lock(g_mutex);
			[g_pads removeObject:controller];
		}
		Changed("detached", controller);
	}

	uint8_t AxisByte(float value)
	{
		// -1 .. 1 to 0 .. 255 with 128 in the middle
		float scaled = (value >= 0) ? (128.0f + (value * 127.0f)) : (128.0f + (value * 128.0f));
		long rounded = std::lround(scaled);
		return static_cast<uint8_t>(rounded < 0 ? 0 : (rounded > 255 ? 255 : rounded));
	}

	// A stick as the two bytes of a PlayStation 2 pad (up and left are 0); false when it
	// is at rest
	bool Stick(GCControllerDirectionPad* stick, uint8_t out[2])
	{
		float x = stick.xAxis.value;
		float y = stick.yAxis.value;
		float length = std::sqrt((x * x) + (y * y));
		if(!(length > STICK_DEAD_ZONE)) return false;
		float wanted = (length - STICK_DEAD_ZONE) / (1.0f - STICK_DEAD_ZONE);
		if(wanted > 1.0f) wanted = 1.0f;
		x = (x / length) * wanted;
		y = (y / length) * wanted;
		out[0] = AxisByte(x);
		out[1] = AxisByte(-y);
		return true;
	}

	// The whole map, in one place.
	void Read(GCController* controller, Rta::PadState& state)
	{
		GCExtendedGamepad* pad = [controller extendedGamepad];
		if(!pad) return;
		uint32_t buttons = 0;
		auto set = [&](bool pressed, Button button) {
			if(pressed) buttons |= (1u << button);
		};
		// by place, as on a PlayStation pad: A is the bottom button, B the right one,
		// X the left one, Y the top one
		set(pad.buttonA.pressed, Button::CROSS);
		set(pad.buttonB.pressed, Button::CIRCLE);
		set(pad.buttonX.pressed, Button::SQUARE);
		set(pad.buttonY.pressed, Button::TRIANGLE);
		set(pad.dpad.up.pressed, Button::DPAD_UP);
		set(pad.dpad.down.pressed, Button::DPAD_DOWN);
		set(pad.dpad.left.pressed, Button::DPAD_LEFT);
		set(pad.dpad.right.pressed, Button::DPAD_RIGHT);
		set(pad.leftShoulder.pressed, Button::L1);
		set(pad.rightShoulder.pressed, Button::R1);
		// the game takes L2 and R2 as buttons
		set(pad.leftTrigger.value > TRIGGER_PRESSED, Button::L2);
		set(pad.rightTrigger.value > TRIGGER_PRESSED, Button::R2);
		set(pad.leftThumbstickButton && pad.leftThumbstickButton.pressed, Button::L3);
		set(pad.rightThumbstickButton && pad.rightThumbstickButton.pressed, Button::R3);
		// Menu is Options on a DualSense, Start elsewhere; Options is Create / Share / Back / View
		set(pad.buttonMenu.pressed, Button::START);
		set(pad.buttonOptions && pad.buttonOptions.pressed, Button::SELECT);
		// a Sony pad's touchpad, pressed, is Select too
		if(@available(macOS 11.0, *))
		{
			GCControllerButtonInput* touchpad = controller.physicalInputProfile.buttons[GCInputDualShockTouchpadButton];
			set(touchpad && touchpad.pressed, Button::SELECT);
		}
		state.buttons = buttons;
		state.stickSet[0] = Stick(pad.leftThumbstick, state.stick[0]);
		state.stickSet[1] = Stick(pad.rightThumbstick, state.stick[1]);
	}
}

// main thread, once
void Rta::StartGamePads()
{
	if(g_started.exchange(true)) return;
	g_pads = [[NSMutableArray alloc] init];
	NSNotificationCenter* center = [NSNotificationCenter defaultCenter];
	NSOperationQueue* queue = [NSOperationQueue mainQueue];
	[center addObserverForName:GCControllerDidConnectNotification object:nil queue:queue usingBlock:^(NSNotification* note) { Attached((GCController*)note.object); }];
	[center addObserverForName:GCControllerDidDisconnectNotification object:nil queue:queue usingBlock:^(NSNotification* note) { Detached((GCController*)note.object); }];
	// Only the application in front listens to the controller: two copies on one Mac
	// would otherwise both move. (The framework itself stops reporting to an application
	// that is not in front unless told otherwise, which is left alone; this makes sure
	// that what was held when the application was left is not held for ever.)
	[center addObserverForName:NSApplicationDidBecomeActiveNotification object:nil queue:queue usingBlock:^(NSNotification*) { g_active = true; }];
	[center addObserverForName:NSApplicationDidResignActiveNotification object:nil queue:queue usingBlock:^(NSNotification*) { g_active = false; }];
	g_active = [NSApp isActive];
	// and asked now and then, in case a notification is missed
	[NSTimer scheduledTimerWithTimeInterval:0.5 repeats:YES block:^(NSTimer*) { g_active = [NSApp isActive]; }];
	// those that were attached before the application started
	for(GCController* controller in [GCController controllers]) Attached(controller);
	bool none = false;
	{
		std::lock_guard<std::mutex> lock(g_mutex);
		none = ([g_pads count] == 0);
	}
	if(none) Rta::LogLine("controller: none known yet; one that is attached (or found in a moment) is taken up at once");
}

// machine thread, once a frame
Rta::PadState Rta::GamePadState()
{
	PadState state;
	state.generation = g_generation;
	if(!g_started) return state;
	@autoreleasepool
	{
		std::lock_guard<std::mutex> lock(g_mutex);
		if([g_pads count] == 0) return state;
		GCController* controller = g_pads[0];
		state.attached = true;
		// a test's controller is read wherever the application is
		if(!g_active && (controller != g_simulated)) return state;
		Read(controller, state);
	}
	return state;
}

std::string Rta::GamePadName()
{
	std::lock_guard<std::mutex> lock(g_mutex);
	return g_name;
}

// ---- for tests ---------------------------------------------------------------------------
// No controller can be pressed by a script. The framework can make a controller object
// whose buttons are set by the program; it is attached, read and detached exactly as a
// real one is (the same notification, the same list, the same map), so everything here
// but the framework's own reading of a real device is exercised.

void Rta::GamePadTest(const std::string& command, uint32_t buttons, const float values[6])
{
	if(!g_started) return;
	std::string what = command;
	std::array<float, 6> v;
	for(int i = 0; i < 6; i++) v[i] = values ? values[i] : 0.0f;
	dispatch_async(dispatch_get_main_queue(), ^{
	  if(what == "connect")
	  {
		  if(g_simulated) return;
		  GCController* controller = [GCController controllerWithExtendedGamepad];
#if !__has_feature(objc_arc)
		  [controller retain];
#endif
		  g_simulated = controller;
		  [[NSNotificationCenter defaultCenter] postNotificationName:GCControllerDidConnectNotification object:controller];
	  }
	  else if(what == "disconnect")
	  {
		  if(!g_simulated) return;
		  GCController* controller = g_simulated;
		  [[NSNotificationCenter defaultCenter] postNotificationName:GCControllerDidDisconnectNotification object:controller];
		  g_simulated = nil;
#if !__has_feature(objc_arc)
		  [controller release];
#endif
	  }
	  else if(what == "set")
	  {
		  if(!g_simulated) return;
		  GCExtendedGamepad* pad = [g_simulated extendedGamepad];
		  auto on = [&](Button button) { return ((buttons >> button) & 1) ? 1.0f : 0.0f; };
		  // the other way round from Read(), written out again on purpose
		  [pad.buttonA setValue:on(Button::CROSS)];
		  [pad.buttonB setValue:on(Button::CIRCLE)];
		  [pad.buttonX setValue:on(Button::SQUARE)];
		  [pad.buttonY setValue:on(Button::TRIANGLE)];
		  [pad.dpad setValueForXAxis:(on(Button::DPAD_RIGHT) - on(Button::DPAD_LEFT)) yAxis:(on(Button::DPAD_UP) - on(Button::DPAD_DOWN))];
		  [pad.leftShoulder setValue:on(Button::L1)];
		  [pad.rightShoulder setValue:on(Button::R1)];
		  [pad.leftTrigger setValue:(on(Button::L2) != 0 ? 1.0f : v[4])];
		  [pad.rightTrigger setValue:(on(Button::R2) != 0 ? 1.0f : v[5])];
		  [pad.leftThumbstickButton setValue:on(Button::L3)];
		  [pad.rightThumbstickButton setValue:on(Button::R3)];
		  [pad.buttonMenu setValue:on(Button::START)];
		  [pad.buttonOptions setValue:on(Button::SELECT)];
		  [pad.leftThumbstick setValueForXAxis:v[0] yAxis:v[1]];
		  [pad.rightThumbstick setValueForXAxis:v[2] yAxis:v[3]];
	  }
	});
}
