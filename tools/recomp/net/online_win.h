// online_win.h - what app/win_main.cpp needs of net/online_win.cpp (no <windows.h> here:
// handles and messages travel as plain values).
#pragma once
#include <cstdint>

namespace onlinewin {

// The game's window (an HWND), once it exists and before rta::run().  test: a test's window
// or one that is never shown - no dialogue, the title stays, nobody is asked.
void attach(void* window, bool test);
bool quiet();
// From the window procedure, for every message from WM_APP on: true when it was one of
// this file's (the name question, a note for the title, a warning) and has been handled.
bool window_message(void* window, unsigned message, uintptr_t wparam, intptr_t lparam);
// From the window's loop, before TranslateMessage: true when the message (a MSG*) belonged
// to an open dialogue and has been dealt with.
bool dialog_message(void* msg);

}  // namespace onlinewin
