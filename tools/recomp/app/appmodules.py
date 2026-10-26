"""appmodules.py - the application modules every program built around app_main.cpp compiles.

One list for app/build.py (rta_app) and build_win.py --mac (the macOS program beside the Windows
build), so a module app_main.cpp comes to need is added once and neither route can link without
it (review-codex item 10: --mac lacked party8.cpp after app_main.cpp began calling party8::).

Each entry is (file in this directory, kind).  The kind names the flags the module needs; each
build script supplies its own flags for a kind (its optimisation, its translation's include
directory), so the list says only what a module reaches:
  rt          the runtime's headers and the game's memory (rt flags, -I app)
  rt_render   the same and the renderer's headers (the frame list)
  testerkit   rt_render and the build id (buildid.py)
  plain       plain C++ (-I app)
  plain_rt    plain C++ that includes a runtime header (-I app -I rt)
  objc        Objective-C++ of the Mac (-I app -I rt)
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# every app_main.cpp program, whichever translation it links
APP_MODULES = [
    ('app_rt.cpp', 'rt'),
    ('gfx_rt.cpp', 'rt'),
    ('fpview.cpp', 'rt'),             # the view modes (fpview.h; docs/issues/native-first-person.md)
    ('fpworld.cpp', 'rt_render'),     # the world for a camera inside it (fpworld.h)
    ('fpcontrols.cpp', 'plain_rt'),   # the controls of the look views (the Windows program compiles the same file)
    ('soulscombat.cpp', 'rt_render'), # Hardcore mode (soulscombat.h; docs/issues/native-souls-combat.md)
    ('partyscale.cpp', 'rt'),         # Hardcore's party scaling (partyscale.h): its numbers are in Hardcore's room figure
    ('party8.cpp', 'rt'),             # the tables sized for four moved at run time (party8.h): app_main.cpp calls party8::
    ('fpaim.cpp', 'rt'),              # aiming by looking (fpaim.h)
    ('cinematic.cpp', 'rt'),          # hold to skip a cut scene (cinematic.h)
    ('testerkit.cpp', 'testerkit'),   # the tester's kit (testerkit.h); the build id is buildid.py's
    ('gamestate.cpp', 'plain'),       # the player's own boss music (bossmusic.h): the state reader and the decoders
    ('bossmusic.cpp', 'plain_rt'),
    ('look_mac.mm', 'objc'),
]

# the game entries that only the fix-set translation leaves open (hle-app.txt): not in rta_app_orig
FIXSET_MODULES = [
    ('film.cpp', 'rt'),               # the films: the library entry points of hle-app.txt
    ('cinematic_hle.cpp', 'rt'),      # cut_runFrame for hold to skip (cinematic.h)
    ('partyscale_hle.cpp', 'rt'),     # Creature_setStats for Hardcore's party scaling (partyscale.h)
]


def jobs(flags, modules=None, prefix='a_'):
    """(source, flags, object prefix) for `modules` (default APP_MODULES + FIXSET_MODULES); `flags` maps each kind to its
    flag list."""
    entries = APP_MODULES + FIXSET_MODULES if modules is None else modules
    missing = sorted({kind for _, kind in entries} - set(flags))
    if missing:
        raise KeyError('appmodules: no flags given for ' + ', '.join(missing))
    return [(os.path.join(HERE, name), list(flags[kind]), prefix) for name, kind in entries]
