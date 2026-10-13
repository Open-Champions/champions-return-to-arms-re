# A new HUD drawn by Godot from the game's own state

Started 2026-10-13. The translated game runs as a library inside Godot
(`native-godot.md`). This work replaces the PS2 game's 640 x 448 HUD sprites with a clean
interface Godot draws itself, from numbers read out of the game's memory. Every statement
says **Ran** (with what was seen) or **Read**. Kept current as the work goes: a successor
needs only this file.

Nothing derived from the game is in the repository: names of characters, classes,
creatures, items and levels are read from the game's memory while it runs. Pictures,
memory images, routes and logs are under `local/godot-hud/`.

## STATE

(see the end of this file for the log; this section is rewritten at each milestone)

| Part | State |
|---|---|
| snapshot, own build and run helper (`local/godot-hud/hud.py`) | **Ran**: boots to the first level in a 480 x 360 test window in 15 s, window pictures by `app windowshot` |
| state interface `tools/recomp/app/gamestate.h/.cpp` | being written |
| extension class `RtaGameState` (new files) | being written |
| HUD scenes and scripts `tools/godot/project/hud/` | being written |

## How it is built and run here

The Godot agent owns `tools/godot/` and changes it while this is written, so everything
runs from a snapshot:

- `local/godot-hud/snap/godot/` - `tools/godot` as it was on 2026-10-13 13:20 (in the
  middle of a change there: `lib/scene_tap.*` had just become `scene_export.*`);
  `snap/recomp/{app,rt}` - the recomp sources the Godot agent's library was built from.
- The game library is the Godot agent's own build of 08:57 (`librta_game.dylib`, copied
  once into `local/godot-hud/project/bin/`); nothing of the library is rebuilt for the HUD.
- `python3 local/godot-hud/hud.py ext` compiles the snapshot's extension sources plus the
  HUD's new files directly with clang against the godot-cpp library the Godot agent built
  (`local/godot-spike/build/extension-template_debug/bin/libgodot-cpp...a`, by reference).
- `python3 local/godot-hud/hud.py stage` makes `local/godot-hud/project/`: the snapshot's
  project, `tools/godot/project/hud/` and the one hook line in `main.gd`.
- `python3 local/godot-hud/hud.py run NAME -- --script ROUTE ...` starts Godot (the one
  under `local/godot-spike/deps`, home redirected to `local/godot-hud/godot-home`) at
  nice 10 in a small window titled "AGENT TEST - HUD NAME", without focus, sound muted;
  log and data under `local/godot-hud/test/NAME/`.
- Routes: `local/godot-hud/mkroute.py` (power-on to the first level by the Godot agent's
  tick-keyed route, then a body from `local/godot-hud/routes/`), `mkfight.py` (the fight
  in `valor` with my own commands at chosen ticks).
