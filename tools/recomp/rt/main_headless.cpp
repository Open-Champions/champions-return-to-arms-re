// main_headless.cpp - the machine with nothing attached: no picture, no sound, no
// network; input from a script.  An application with a window links the same objects
// except this file and calls rta::run() with its own rta::Hooks (iface.h).
#include "iface.h"

int main(int argc, char** argv) {
    rta::Hooks hooks;
    return rta::run(argc, argv, hooks);
}
