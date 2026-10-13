// help_host.h - what a person has to be told by the window program itself: which keys are
// which buttons, what a controller needs (nothing), how to leave.
//
// macOS (help_mac.mm): a small panel beside the game's window - shown at the first start
// of a data directory, with F1, and from the Help menu - and the same words on the
// terminal the program was started from.  The panel takes no keyboard: the keys go on
// reaching the game while it is up.
#pragma once
#include <string>

namespace hosthelp {

// The words (also printed at the start of every run somebody plays).
std::string keys_text();

// Main thread, once the application object exists: the Help menu's entry.
void start();
// Any thread: show the panel, or put it away when it is up.
void toggle();
void show();
// Main thread: something the person must read before the program can go on (or cannot):
// a box with one button, waited for.  Also printed by the caller.
void box(const std::string& headline, const std::string& text);
// Tests: "info" says whether the panel is up and how many lines it holds; "show", "hide".
std::string test(const std::string& what);

}  // namespace hosthelp
