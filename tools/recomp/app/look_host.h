// look_host.h - the pointer as the look of a view (fpcontrols.h): hidden, held where it is,
// its motion handed on as counts.  One implementation per host: look_mac.mm (macOS); the
// Windows program does the same inside win_main.cpp (raw input).
//
// Main thread only.  A test window never captures: tests move the look through the control
// socket ("app fpc mouse DX DY"), never through the system's pointer.
#pragma once

namespace hostlook {

void start();               // once, after the application object exists
void capture(bool on);      // hide and hold the pointer / give it back; motion goes to fpcontrols::mouse_motion while held
bool captured();

}  // namespace hostlook
