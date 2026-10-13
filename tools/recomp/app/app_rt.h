// app_rt.h - the few things the window program needs from inside the runtime, kept behind
// plain functions so that app_main.cpp includes nothing of the runtime but iface.h
// (rt.h brings the translated code's types and macros with it).  app_rt.cpp implements
// them and is compiled with the runtime's flags.
#pragma once
#include "iface.h"

#include <cstdint>
#include <string>

namespace apprt {

// What the script (--script, --do) holds on a port right now.
rta::PadState script_pad(unsigned port);

// Script lines "app <text>" arrive here, on the game's thread, at a vertical blank.
void set_command_handler(void (*handler)(const std::string& text, uint64_t frame));
// An "app <text>" line that did not come from a script (the control socket's): it goes the
// way a script's line goes - through whoever chained itself in front of the handler above
// (the network: "online ...", "net ...", net/online.cpp) and then to the handler.
void command(const std::string& text, uint64_t frame);
// Host threads that carry one of the game's threads now, started in all, and ended by the
// game's TerminateThread (rt/runtime.cpp).
void thread_figures(unsigned& now, unsigned& made, unsigned& ended);
// Called once when the run ends (script `quit`, --fields, the window closed), before the
// runtime prints its report.
void set_finish_handler(void (*handler)());
// End the run from the game's thread (prints the reports, ends the process).
[[noreturn]] void finish(int code);

// The game's threads started from now on are scheduled as the player's own (host.h).
void interactive_threads();

bool films_linked();            // app/film.cpp is part of this program (the films play)
void films_report();
std::string sound_figures();    // key=value figures of the sound side (empty without tools/recomp/sound)
uint64_t fields();              // vertical blanks since power-on
double machine_seconds();       // the virtual clock

// Copies one file out of the disc image (ISO 9660), e.g. "\\SLUS_209.73;1".  False when
// the image or the file cannot be read.
bool extract_from_disc(const std::string& image, const char* path_on_disc, const std::string& to);

}  // namespace apprt
