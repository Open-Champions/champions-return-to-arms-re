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

}  // namespace hostpad
