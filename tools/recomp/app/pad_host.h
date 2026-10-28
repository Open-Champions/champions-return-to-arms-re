// pad_host.h - game controllers of the host, as the application's pad source reads them.
//
// One implementation per host: pad_mac.mm (macOS, GameController.framework).  A host
// without one links pad_none.cpp-style stubs (start() does nothing, read() returns false).
#pragma once
#include "iface.h"

#include <cstdint>
#include <string>

namespace hostpad {

// Main thread, once, after the application object exists: listens for controllers being
// attached and detached.  `log` gets one line per change (it is called on the main thread).
void start(void (*log)(const std::string& line));

#ifdef _WIN32
void set_window(void* hwnd);
// The PS2 small motor is on/off; the large motor is 0..255. Synthetic pads
// never drive hardware. Focus loss, detach and shutdown release both motors.
void rumble(uint8_t small, uint8_t large);  // compatibility: port 0
// Windows couch play: physical PS2 ports 0 and 1, never a multitap. Keyboard stays P1.
// Controllers claim players in first-use order, ignoring idle virtual devices.
// Assignments stay distinct; detach never promotes the other port. XInput slot indices
// are not persistent device IDs if Windows reassigns a controller to a different slot.
bool read(unsigned port, rta::PadState& state);
void rumble(unsigned port, uint8_t small, uint8_t large);
void release_motors();              // both ports on focus loss or shutdown; retries failed stops
std::string name(unsigned port);
uint32_t generation(unsigned port);
int xinput_slot(unsigned port);     // 0..3 backing slot, or -1; synthetic takeover keeps reservation
void test(unsigned port, const std::string& command, uint16_t buttons, const float values[6]);
#endif

// Any thread: the first attached controller as a PlayStation 2 pad.  False when none is
// attached, or when this application is not the one in front (a real controller is only
// listened to by the application in front; one made by test() is read wherever it is).
bool read(rta::PadState& state);

std::string name();             // of the first controller; empty: none
uint32_t generation();          // counts every attach and detach

// Tests.  No script can press a real controller's buttons; the framework can make a
// controller object whose state the program sets, and it is attached, read and detached
// exactly as a real one is.  command: "connect", "disconnect", "set" (buttons in
// rta::PadButton bits; values: left x, left y, right x, right y in -1..1 with up and right
// positive, then the two triggers in 0..1).  Carried out on the main thread.
void test(const std::string& command, uint16_t buttons, const float values[6]);

// Main thread, once: tells the system that this process is doing something a person is
// waiting for and that its timers must be kept (macOS: an activity that is user-initiated
// and latency-critical; without it a program that is not in front is put to "App Nap" and
// its waits are stretched by milliseconds).  It does not keep the display or the computer
// awake.  A host without such a thing does nothing.
void keep_timers();

}  // namespace hostpad
