// partyscale_hle.cpp - the game's Creature_setStats (0x10a620) as the fix-set translation hands it to the application
// (app/hle-app.txt): Hardcore mode's party scaling, partyscale.h.  Linked only into the fix-set build; with the mode off
// it is the original translation and nothing else.
#include "partyscale.h"
#include "rt.h"
#include "funcs.h"

void fn_0010a620(Ctx* c) { partyscale::set_stats(c, orig_0010a620); }
