# Frame-rate verdict: Godot Remastered and Classic at the display's own size

2026-10-26. Build `local/godot-r38p8`: origin/main `dc7b4cf` (model remaster round 2, world sweep, hub gate 8, the
view.gd brightness fix, the hitch fixes, the black-picture fix, presets, the fpview fix, the boss-music level fix
`57b769e`, the 8-player phase 3 `6902c8c` and `dc7b4cf`) with the two fixes below, built as the launcher's build for
rooms of up to eight: `RTA_GODOT_PARTY8=1 RTA_GODOT_OUT=local/godot-r38p8 python3 tools/godot/build.py all`.
The same tree without the party8 switch is `local/godot-r38` (the first measurements). Apple M5 Pro, Godot 4.5.2,
Metal Forward+, the built-in 120 Hz display.

## Verdict

- **Classic: a steady 60.** Every level of the eleven, both runs: 59.9-60.0 game frames a second, the slowest second
  58-60, 0-7 intervals over 25 ms in a level (the longest 26-50 ms, at a level's first frames).
- **Remastered: 60 in 9 of 11 levels in one run (59.7-60.0), 5 of 11 in the other (59.0-60.0); not in `arachna1` (50) and `wate2c`
  (40-53).** Where it holds, the game is at 60.0 (it ran 64-66 before the pacing fix below, too fast) with 85-103
  pictures a second on the 120 Hz display. `arachna1` is bound by the GPU (MSAA 4x over 3024 x 1964), `wate2c` by
  the main thread at the end of a long session. Not met overall: see "What is left".
- **`wate2c` late in a long session: found and fixed (2026-10-26, "The long session").** Remastered figures were
  dropped one by one over a session (a per-figure counter that never reset), and the game's own figures took their
  place, curved on the CPU: wate2c as the eleventh level now costs the main thread what it does fresh (26-28 ms of
  processor time a game frame, `submit()` 7.6-8.1 ms; it was 37.8 / 15.3).

## How it was measured

- **Settings.** Remastered exactly as the portal's Remastered card sets it (`--edition remastered`: scene mode, the
  look with every feature on and the per-level presets, the Elden Ring figures and creatures, the world layer,
  Hardcore, aiming by looking, the new HUD, display rate **auto = 120 Hz**, chase view), the 3-D picture at
  **3024 x 1964** (the display's own pixels, the size a full-screen window gives with the default sharpness) and the
  shape of that screen (`--aspect 3024:1964`), in a 1512 x 982-point window. Classic: `--edition classic` (overhead,
  the Classic look, display rate 60) at the same size. The art pack, the owner's Elden Ring folders, sound running
  but muted.
- **Route.** The hitch-codex route (`docs/issues/hitch-codex.md`): boot to the hub, then each level asked for in
  turn; in each: 12 taps through its opening, idle 3 s, walk, turn, five attacks, shoulder view and back. Levels:
  hub, fire1, arachna1, water1, drunare, islsm3b, fearboss, bossgood and, as the heaviest of the earlier campaign
  measurement, storm5, nitdung2 and wate2c - one session through all eleven (as a player goes from level to level).
- **Figures.** From the frame log (`--frame-log`), per level from the level's entry mark to its end mark (the entry
  and its fade included): **game frames a second** (frames taken from the game - the game-picture handoff rate;
  `game_frame` rows, wall-clock), the **slowest second** of game frames, the **pictures a second** (refreshes drawn
  at 120 Hz, the ones between game frames included), the **picture interval** p50 / p99 / max, and the counts of
  picture intervals and of game-frame intervals over 25 ms. (At 120 Hz the frame log marks every refresh as a new
  picture, so the game-picture rate is taken from the game-frame column, not from `new_picture`.)
- **Quiet.** Each run started only when the 1-minute load was under 20 **and the GPU** (ioreg's Device Utilization)
  under 25 %; the load at start and end and the GPU before start are given under each table. The GPU check matters:
  the first runs of the day were taken at a load of 8-19 while other agents' programs (a native application, other
  Godot copies, a browser) held the GPU at 80-99 % - a load average does not show that, and those runs measured the
  machine, not the game (table at the end).
- Each condition twice. Tooling (local, not tracked): `local/fps-verdict/bench.py` (the route, the settings),
  `stats.py`, `series.py` (the quiet gate), `tools/` (Metal System Trace and Time Profiler of our own process,
  `gpu.py`, `tp.py`).

## Remastered, final build (`godot-r38p8`, both fixes)

Cells: **game frames/s** (slowest 1 s) · pictures/s · picture interval p50 / p99 / max ms · picture intervals > 25 ms ·
game-frame intervals > 25 ms.

| Level | f-rem-1 | f-rem-2 |
|---|---:|---:|
| hub | **60.0** (59) · 85 · 11.4 / 17.5 / 23.8 · 0 · 126 | **60.0** (59) · 92 · 10.6 / 17.1 / 19.2 · 0 · 72 |
| fire1 | **51.8** (40) · 65 · 14.2 / 28.2 / 57.0 · 57 · 86 | **59.7** (55) · 92 · 11.2 / 16.5 / 43.6 · 3 · 66 |
| arachna1 | **49.9** (28) · 57 · 16.2 / 36.5 / 37.3 · 152 · 222 | **50.6** (29) · 59 · 15.9 / 35.2 / 36.1 · 145 · 226 |
| water1 | **59.9** (59) · 101 · 10.0 / 14.8 / 18.2 · 0 · 32 | **59.9** (59) · 103 · 10.0 / 15.3 / 18.2 · 0 · 45 |
| drunare | **56.2** (45) · 85 · 10.1 / 25.7 / 41.4 · 21 · 29 | **59.8** (57) · 99 · 10.0 / 16.5 / 34.7 · 2 · 38 |
| islsm3b | **57.7** (38) · 90 · 9.8 / 26.6 / 44.5 · 29 · 46 | **59.8** (58) · 99 · 9.5 / 16.6 / 22.7 · 0 · 21 |
| fearboss | **59.8** (56) · 95 · 10.2 / 17.3 / 44.5 · 2 · 85 | **60.0** (59) · 101 · 10.0 / 15.5 / 17.4 · 0 · 29 |
| bossgood | **59.0** (48) · 83 · 10.2 / 25.5 / 33.4 · 15 · 46 | **60.0** (59) · 96 · 10.0 / 17.1 / 20.7 · 0 · 44 |
| storm5 | **54.2** (43) · 55 · 20.1 / 26.7 / 37.6 · 21 · 27 | **59.8** (58) · 90 · 10.9 / 16.0 / 29.9 · 2 · 42 |
| nitdung2 | **59.9** (59) · 92 · 10.6 / 16.9 / 19.5 · 0 · 85 | **59.8** (58) · 95 · 9.7 / 17.4 / 22.9 · 0 · 146 |
| wate2c | **40.5** (22) · 47 · 19.3 / 54.3 / 76.0 · 466 · 488 | **53.1** (38) · 67 · 15.3 / 28.2 / 38.9 · 38 · 75 |

Load average (1 min) at start -> end; GPU busy before start (3 samples, %): `f-rem-1` 7.2 -> 5.2, GPU [0, 0, 0]; `f-rem-2` 3.1 -> 3.1, GPU [0, 0, 0]

The game-frame intervals over 25 ms in the levels that hold 60 are the 120 Hz grid, not lost frames: where the
refreshes come every 10-11 ms (85-100 pictures a second) a game frame falls 2 or 3 refreshes after the one before
(21 or 32 ms), 60.0 a second on average; the pictures between keep the motion at 10-11 ms (p99 15-18 ms).

## Classic, final build

| Level | f-cls-1 | f-cls-2 |
|---|---:|---:|
| hub | **60.0** (59) · 60 · 16.2 / 24.1 / 26.0 · 1 · 1 | **60.0** (59) · 60 · 16.1 / 24.1 / 26.8 · 3 · 3 |
| fire1 | **59.9** (58) · 60 · 15.9 / 24.2 / 49.3 · 4 · 4 | **59.9** (59) · 60 · 15.4 / 24.4 / 45.1 · 4 · 4 |
| arachna1 | **60.0** (59) · 60 · 16.9 / 24.4 / 27.4 · 6 · 6 | **60.0** (59) · 60 · 16.9 / 24.6 / 26.2 · 5 · 5 |
| water1 | **59.9** (58) · 60 · 16.8 / 23.9 / 50.5 · 3 · 3 | **60.0** (59) · 60 · 15.9 / 23.4 / 27.5 · 5 · 5 |
| drunare | **60.0** (59) · 60 · 15.9 / 24.5 / 30.5 · 5 · 5 | **60.0** (59) · 60 · 15.7 / 24.2 / 32.6 · 2 · 2 |
| islsm3b | **60.0** (59) · 60 · 16.0 / 24.5 / 34.7 · 5 · 5 | **59.9** (59) · 60 · 15.5 / 24.5 / 43.0 · 4 · 4 |
| fearboss | **60.0** (59) · 60 · 17.0 / 24.0 / 34.7 · 2 · 2 | **60.0** (60) · 60 · 16.4 / 23.6 / 24.6 · 0 · 0 |
| bossgood | **60.0** (59) · 60 · 17.5 / 24.6 / 32.7 · 4 · 4 | **60.0** (59) · 60 · 17.6 / 24.3 / 28.7 · 6 · 6 |
| storm5 | **60.0** (59) · 60 · 15.4 / 24.3 / 25.6 · 2 · 2 | **60.0** (59) · 60 · 15.8 / 24.0 / 27.9 · 1 · 1 |
| nitdung2 | **60.0** (59) · 60 · 16.5 / 23.9 / 26.2 · 3 · 3 | **60.0** (60) · 60 · 17.1 / 23.2 / 27.7 · 1 · 1 |
| wate2c | **60.0** (59) · 60 · 17.8 / 24.5 / 25.8 · 1 · 1 | **60.0** (59) · 60 · 18.1 / 24.8 / 26.6 · 7 · 7 |

Load average (1 min) at start -> end; GPU busy before start (3 samples, %): `f-cls-1` 5.2 -> 3.1, GPU [0, 0, 0]; `f-cls-2` 3.1 -> 5.5, GPU [0, 0, 0]

## Remastered before the fixes (the same library and project, `main.gd` of `dc7b4cf`)

| Level | b-rem-1 | b-rem-2 |
|---|---:|---:|
| hub | **64.0** (61) · 90 · 11.0 / 16.3 / 20.0 · 0 · 18 | **64.0** (60) · 91 · 10.8 / 16.1 / 20.0 · 0 · 21 |
| fire1 | **64.9** (58) · 81 · 13.6 / 18.9 / 49.1 · 3 · 31 | **56.1** (48) · 69 · 13.9 / 25.0 / 47.7 · 13 · 28 |
| arachna1 | **52.2** (29) · 56 · 16.3 / 35.6 / 36.5 · 148 · 154 | **52.5** (29) · 57 · 16.1 / 35.3 / 35.8 · 146 · 155 |
| water1 | **64.7** (63) · 95 · 10.4 / 14.2 / 22.1 · 0 · 4 | **63.9** (62) · 97 · 10.3 / 14.4 / 19.4 · 0 · 34 |
| drunare | **54.9** (37) · 78 · 11.1 / 27.7 / 51.5 · 70 · 76 | **59.0** (48) · 85 · 10.3 / 22.8 / 36.2 · 4 · 12 |
| islsm3b | **60.2** (39) · 89 · 10.3 / 25.9 / 39.0 · 18 · 43 | **63.5** (61) · 96 · 9.9 / 17.2 / 28.9 · 1 · 21 |
| fearboss | **64.4** (63) · 96 · 10.4 / 17.1 / 24.3 · 0 · 26 | **64.1** (61) · 99 · 10.2 / 16.2 / 24.6 · 0 · 19 |
| bossgood | **65.2** (59) · 85 · 10.6 / 18.4 / 22.4 · 0 · 21 | **64.0** (60) · 93 · 10.3 / 17.3 / 20.3 · 0 · 15 |
| storm5 | **54.1** (38) · 56 · 18.0 / 30.6 / 40.3 · 36 · 38 | **59.4** (53) · 60 · 16.6 / 22.0 / 47.9 · 3 · 6 |
| nitdung2 | **66.5** (59) · 93 · 10.6 / 17.3 / 38.0 · 1 · 30 | **65.6** (59) · 91 · 10.8 / 16.9 / 24.6 · 0 · 25 |
| wate2c | **45.2** (27) · 53 · 17.9 / 38.7 / 63.9 · 343 · 359 | **45.1** (27) · 52 · 19.6 / 40.2 / 69.3 · 374 · 381 |

Load average (1 min) at start -> end; GPU busy before start (3 samples, %): `b-rem-1` 5.2 -> 4.4, GPU [0, 0, 0]; `b-rem-2` 4.4 -> 3.0, GPU [0, 0, 0]

Above 60 is not headroom: the game itself ran fast (next section). `wate2c` 45 and `arachna1` 52 then.

## Fixes

1. **The game ran 6-10 % fast at 120 Hz** (`main.gd` `_paced_between`). After a game frame was taken, the clock of
   the game was put back to 0 when it was taken early (up to half a refresh before its tick), dropping the
   remainder. With refreshes of exactly 8.33 ms nothing is lost; with refreshes of 9-12 ms (any scene that does not
   draw 120 a second) part of a refresh was gained at every game frame: in the hub the game ran at **63-66 frames a
   second** for minutes (speed log), and a replay of the hub's own refresh times through the rule gives 63.3 against
   60.0 with the remainder kept. Now the remainder is kept (down to minus half a refresh). The game's speed is 60.0
   in every level that keeps up (`b-rem` 64-66 -> `f-rem` 59.8-60.0), and the heavy levels no longer pay for frames
   ahead of time. Nothing of the simulation changes - only when the host lets the next tick go - so rooms stay in
   step; Classic's 60 Hz path is a different branch and untouched.
2. **Pictures between game frames only when the GPU has the time** (`main.gd`). At 120 Hz the picture between two
   game frames redraws the whole world viewport; in a level whose world costs more than a refresh, each such
   picture took its time from the next game frame (the old switch turned them off only after the game frames had
   averaged 12 % late, and back on after two good seconds, so heavy levels swung). Now a refresh that came more than
   half a refresh late holds the pictures between for a quarter of a second. A picture is never drawn differently;
   fewer of them are drawn where they cost game frames (figures: "N not drawn: a refresh had come late").
   Its effect alone is not separated from the first fix's: `storm5`, `drunare` and `fire1` 59.7-59.8 in one run
   after (54-59 before), but 52-56 again in the other; `wate2c` 45 / 45 before, 40.5 / 53.1 after.

## What is left (Remastered)

- **`arachna1`: the GPU, MSAA 4x at 3024 x 1964.** Metal System Trace of our process in the level's play, quiet
  machine: the GPU busy **884 ms of every second**, the world's main pass 707 ms/s (about 14.5 ms a picture) and a
  second pass 263 ms/s. One feature off at a time (diagnostics, not candidates): anti-aliasing off **469 ms/s** of GPU
  and 53 game frames a second (the main pass 295 ms/s, the second pass gone); the sun off 734 ms/s, 48; the torch
  lights off 746 ms/s, 45; their shadows off 901 ms/s (no change); the Elden Ring figures off 816 ms/s, 46; the world
  layer, fog, bloom, sky, foliage, the lamp, the grade, contact shading: no measurable change. At a quarter of the
  pixels (1512 x 982) the level ran 61.5. The cost is the 4x multisampled transparent pass at the display's full
  size: every draw of the level is in Godot's transparent pass (the game's own order), so the engine's opaque
  pre-pass does not help it. Keeping the picture identical rules out the knobs that would fix it (2x MSAA, a
  smaller 3-D surface with FSR, `display.upscale`); the next step is in the renderer's use of multisample targets
  (fewer render passes over them), not in our settings.
- **`wate2c` at the end of a long session: the main thread.** 40.5 and 53.1 in the two runs (a 4-level session:
  56). Time Profiler, 7 s of the level: the main thread busy 90 % - `RtaDrawer::submit` 38 % (its `scene_take`
  26 %, self time 13 %: the per-corner work of the level's curved and kept meshes), Godot's render 31 % (culling,
  instance updates 6 %, surface pipelines made in play 4 %), `RtaRemaster::light_sh` 2 %. The processor time per
  picture rises from 34-49 ms (short session) to 60-88 ms (last of eleven); not thermal (no thermal or performance
  warning recorded). Found and fixed: see "The long session" below.
- `fire1`, `islsm3b`, `drunare`, `storm5` held 60 in one run and 52-58 in the other (both quiet by the gate): the
  first run of a pair is the slower in each pair here; not attributed.

## The long session: what grew, and the fix (2026-10-26, late)

**Cause.** `model_remaster.gd` leaves a figure to the game when its model "keeps changing" (texture coordinates that
move): more than 6 changes of its model's key under one figure id. The id is the figure's animation state - a guest
address - and its place among that state's objects, and the game hands those addresses out again: in the next level,
and to the next creature of the same one. The counter (`unstable`) was never reset, so over a session every reused
address went over 6 once and for good, and its figures - in a level eleven deep, nearly all of them - were the game's
own: not remastered (a different picture from a fresh session), and drawn by the drawer with the cleaner look's
curved triangles (PN, 2 x 2), made on the main thread in `scene_take`. Late in the route that is **228-235 thousand
curved corners a list** that a fresh session does not have (the per-corner self time of the Time Profiler above).
Nothing else grew in a way that costs a frame (counts below).

**Fix** (`model_remaster.gd`, `scene_view.gd`). Only changes that come close together count (each within 120 game
frames of the one before; a change after a pause starts again from 0), and a new level clears the counter and the
`settled` table (`model_remaster.new_level`, called by `scene_view._level` when the level's name changes). A model
whose texture coordinates really move changes every frame and is still left to the game after 7 frames, as before.
Drawing only: nothing reaches the game.

**How it was measured.** The machine was busy the whole time (two playtest agents running games, load average
18-42 at the runs' starts and ends), so wall-clock frame rates say nothing here; the figures are **processor time of
the main thread** (`CLOCK_THREAD_CPUTIME_ID`, read at the route's marks) per game frame, and of `RtaDrawer::submit`
alone per list, from the idle mark to the end mark of each level (735 game frames), with counts read at the same
marks. Temporary counters, not committed (`local/fps-leak/instrumentation.patch`: the drawer's and the remaster's
caches, every script's dictionaries and arrays, nodes by place and class, Godot's monitors and rendering info, the
drawer's per-list draws, kept meshes, curved corners, draws left out). The same route and settings as above
(`local/fps-leak/bench.py`, a copy of this one's), the build `local/godot-leak` (`godot-r38p8` with the counters),
`nice -n 10`.

Per level: main thread ms / `submit()` ms per game frame · curved corners a list · draws left out a list (the
figures the remaster or the Elden Ring layer draws instead). Before = the session's counter as it was (`L2`), after =
the fix (`L3`, `L4`).

| Level | before (`L2`) | after (`L3`) | after (`L4`) |
|---|---:|---:|---:|
| hub | 17.5 / 4.9 · 0k · 599 | 17.9 / 5.1 · 0k · 599 | 16.1 / 4.7 · 0k · 599 |
| fire1 | 19.3 / 6.5 · 1k · 329 | 19.5 / 6.5 · 1k · 329 | 18.2 / 6.1 · 1k · 335 |
| arachna1 | 16.5 / 4.7 · 2k · 618 | 17.6 / 4.8 · 2k · 618 | 11.7 / 3.5 · 7k · 365 |
| water1 | 8.2 / 1.8 · 0k · 238 | 8.4 / 1.9 · 0k · 238 | 8.5 / 2.0 · 1k · 238 |
| drunare | 14.2 / 5.2 · 68k · 609 | 11.5 / 3.0 · 2k · 677 | 10.6 / 2.8 · 2k · 667 |
| islsm3b | 16.3 / 6.4 · 49k · 66 | 11.8 / 3.5 · 0k · 300 | 11.5 / 3.5 · 0k · 300 |
| fearboss | 13.6 / 5.0 · 80k · 0 | 8.5 / 1.8 · 0k · 238 | 8.3 / 1.8 · 0k · 238 |
| bossgood | 24.1 / 13.1 · 235k · 417 | 14.7 / 5.6 · 6k · 655 | 13.7 / 5.3 · 6k · 657 |
| storm5 | 27.9 / 12.7 · 228k · 36 | 17.7 / 5.3 · 0k · 274 | 17.4 / 5.4 · 0k · 284 |
| nitdung2 | 19.6 / 9.3 · 228k · 0 | 9.1 / 1.9 · 0k · 238 | 10.2 / 2.3 · 0k · 239 |
| **wate2c** | **37.8 / 15.3** · 228k · 561 | **27.7 / 8.1** · 0k · 799 | **26.1 / 7.6** · 0k · 760 |

**wate2c fresh** (hub, then wate2c): 27.7 / 8.2 · 0k · 804 before the fix (`S2`), 26.8 / 8.1 · 0k · 804 after (`S3`).
The eleventh-level wate2c now costs what the fresh one does (26.1-27.7 against 26.8-27.7 ms; `submit()` 7.6-8.1
against 8.1-8.2), and draws what it does: 599-618 draws a list submitted (855 before), 1,880 objects in Godot's
frame at the end mark (fresh 1,915; 2,483 before). The game drew the same in every run (its draws per list in the
speed log alike, second for second); what differed was only how many of them the remaster took over. The levels from
drunare on were all paying for it (bossgood 24.1 -> 14.7, storm5 27.9 -> 17.7, nitdung2 19.6 -> 9.1 ms).

**What else was counted** (end of wate2c, fresh / eleventh before / eleventh after): kept meshes 686 / 922 / 658,
materials 259 / 277 / 259, game textures 391 / 352 / 349, the retire queue 0 / 0 / 0, the remaster's figures 24 / 24 /
25 - flat. Growing over a session but costing no frame time: nodes 997 / 1,783 / 2,072 (the Elden Ring outfits and
weapons loaded so far, kept hidden under `er_layer`: one tree per outfit, a handful a session), the remaster's baked
models 18 / 41 / 41 and its per-packet tables (1,251 / 2,525 / 2,465 entries: one per model packet seen, bounded by
the game's models), static memory 444 / 614 / 554 MB. These are caches by content (bounded by what the game has), not
per frame; left as they are.

**Checks.** The picture: wate2c's end shot fresh and eleventh (`S3`, `L4` `wate2c.png`) show the same remastered
figure in the same place; before the fix the eleventh level left 561 draws a list to others against 799-804 fresh
(the figures the remaster did not take were the game's own; no shot of that run). No
script error in any run. Classic: `model_remaster` is off there, the counter is never filled; a Classic hub -> wate2c
run (`C1`) with no script error. Two copies in a room (`local/fps-leak/room.sh`: two Godot copies of this build,
Remastered, `n2p8x.py`, hub -> drunare -> valor): **3,938 ticks in step**, no script error on either copy; an
earlier two-copy room in valor (`room2`, 6 deaths, 3 reloads) 8,340 ticks in step.

Seen on the way, not changed: the sky of the eleventh wate2c's end shot is darker than the fresh one's (not
looked into), not part of this fix.

## The first measurements (GPU not quiet), for the record

`local/godot-r38` (the same tree before `57b769e`, without the fixes), 3510 x 1964 (the window's shape, which the
test window got wrong - corrected to the screen's shape afterwards), load 13-19, the GPU shared with other agents'
programs:

| Level | r38-rem-1 | r38-rem-2 |
|---|---:|---:|
| hub | **43.8** (32) · 44 · 22.4 / 34.3 / 39.5 · 224 · 224 | **52.1** (41) · 52 · 19.0 / 26.5 / 34.9 · 26 · 27 |
| fire1 | **43.0** (33) · 44 · 23.7 / 42.0 / 72.8 · 368 · 372 | **50.5** (40) · 52 · 20.1 / 26.7 / 60.4 · 33 · 41 |
| arachna1 | **24.6** (14) · 25 · 40.1 / 72.5 / 80.3 · 832 · 833 | **31.7** (18) · 32 · 29.7 / 57.9 / 60.2 · 710 · 711 |
| water1 | **41.1** (29) · 42 · 25.0 / 38.6 / 69.3 · 482 · 486 | **55.2** (43) · 61 · 17.3 / 24.5 / 26.1 · 8 · 52 |
| drunare | **47.8** (27) · 71 · 9.1 / 40.1 / 64.7 · 233 · 236 | **53.6** (41) · 80 · 8.8 / 25.9 / 42.4 · 31 · 35 |
| islsm3b | **60.9** (52) · 94 · 9.4 / 20.3 / 31.5 · 2 · 9 | **60.5** (45) · 88 · 9.9 / 23.9 / 39.3 · 5 · 9 |
| fearboss | **61.2** (52) · 76 · 14.6 / 20.4 / 23.8 · 0 · 3 | **58.6** (46) · 70 · 15.5 / 23.1 / 27.1 · 3 · 8 |
| bossgood | **59.3** (39) · 70 · 15.8 / 27.0 / 34.1 · 27 · 28 | **58.4** (41) · 63 · 16.6 / 25.8 / 56.5 · 20 · 22 |
| storm5 | **41.0** (33) · 42 · 23.4 / 41.9 / 50.2 · 412 · 414 | **48.1** (41) · 49 · 20.3 / 33.1 / 50.4 · 36 · 40 |
| nitdung2 | **50.7** (43) · 52 · 19.3 / 25.8 / 38.6 · 19 · 23 | **52.7** (47) · 53 · 18.8 / 23.7 / 31.8 · 7 · 8 |
| wate2c | **33.1** (21) · 34 · 29.9 / 56.6 / 76.8 · 564 · 568 | **35.2** (22) · 36 · 28.6 / 49.1 / 68.9 · 605 · 609 |

Load average (1 min) at start -> end; GPU busy before start (3 samples, %): `r38-rem-1` 15.8 -> 19.0, GPU -; `r38-rem-2` 13.8 -> 13.4, GPU -

Classic in the same conditions (reruns at load under 20): every level 59.8-60.0 but `bossgood` and `wate2c` once
(53-57) at load 19-39.

## Files

- `tools/godot/project/main.gd`: the two fixes.
- `tools/godot/project/model_remaster.gd`, `scene_view.gd`: the long-session fix (the remaster's change counter).
- Local: `local/fps-leak/` (runs `L*`, `S*`, `C1`, `room2`, `room3`, `bench.py`, `seg.py`, `counts.py`,
  `instrumentation.patch`), the build `local/godot-leak`.
- Local: `local/fps-verdict/` (runs `f-rem-*`, `f-cls-*`, `b-rem-*`, `v-*`, `r38-*`, diagnostics `d-*`, `q*`, `tp-*`,
  the scripts), the builds `local/godot-r38` and `local/godot-r38p8`.
- The *Play Champions - REMASTERED (new)* launcher (Desktop, not tracked) now starts `local/godot-r38p8`.
