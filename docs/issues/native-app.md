# The native application

Started 2026-10-12. The pieces of a native build of Champions: Return to Arms (SLUS-20973
v2.00) existed separately: the translated game and its runtime
(`docs/issues/native-recomp.md`), a renderer (`docs/issues/native-render.md`), a sound
library (`docs/issues/native-sound.md`). This is the program that puts them into one
window: `tools/recomp/app/`. Every statement says whether it was **Ran** (with what was
seen) or only **Read**; "Not reached" lists the rest.

Nothing derived from the game is in the repository: generated C++, objects, programs,
pictures, streams and memory cards are under `local/recomp-out/`.

## Start it

```
python3 tools/recomp/app/build.py            # once, and after any change (about 1 minute)
local/recomp-out/bin/rta_app --disc "/path/to/Champions - Return to Arms (v2.00).iso"
```

The window is titled "Champions: Return to Arms - native build (experimental)". Memory
cards and settings go to `local/recomp-out/app-data` (`--data DIR` for another place).
`rta_app --help` lists the options; the head of `tools/recomp/app/app_main.cpp` describes
each. Keys: W A S D left stick, arrows direction pad, I J K L triangle / square / cross /
circle, Q E L1 R1, 1 3 L2 R2, X C L3 R3, Return Start, Backspace Select, F or F11 full
screen, Escape leaves it. The first game controller macOS knows is port 1 as well.

## Status (kept current; last update at the end of the file)

See "State" at the end.

## The parts

| File | Does |
|---|---|
| `app/build.py` | translates the game with the suggested fix set (`recomp.py --pnach`, `local/recomp-out/gen-app`), compiles it (`build.py run --gen … --name rta_native_fix`), compiles runtime, renderer, sound library and this directory, links `bin/rta_app`. `--original` links `bin/rta_app_orig` from the shared unpatched translation instead |
| `app/app_main.cpp` | options, the window (Qt 6, OpenGL 4.1 through `render/backend_gl.cpp`), pacing, keyboard, the pad source, the `app …` script commands |
| `app/pipeline.h` | the picture path: the runtime's sink copies on the game's thread, a decoder thread runs VIF1 / VU1 / the GS model, the main thread draws |
| `app/app_rt.h/.cpp` | the few things the window program needs from inside the runtime (script state, finish, reading a file out of the disc image) |
| `app/pad_host.h`, `app/pad_mac.mm` | game controllers through GameController.framework |
| `app/emushots.py` | reference pictures: runs the emulator build silently and offline over the same script and takes its `shotfb` where the script says `app shot` |

One program, one process: the translated game runs on the runtime's threads, the renderer
is installed through `rta::Hooks::video`, input through `rta::Hooks::pad`, and
`tools/recomp/sound/sound_rta.cpp` is linked in place of `rt/sound_null.cpp`.

(To be continued below as the work goes on.)
