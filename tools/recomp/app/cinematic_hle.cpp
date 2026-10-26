// cinematic_hle.cpp - the game's cut_runFrame (0x199944) as the fix-set translation hands it to the application
// (app/hle-app.txt): hold to skip, cinematic.h.  Linked only into the fix-set build; with the mode off it is the
// original translation and nothing else.
#include "cinematic.h"
#include "rt.h"
#include "funcs.h"

void fn_00199944(Ctx* c) { cinematic::run_frame(c, orig_00199944); }
