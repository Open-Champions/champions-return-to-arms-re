# The translated game inside Godot (spike)

Started 2026-10-13. Question: can the statically recompiled game (`native-recomp.md`,
`native-app.md`) run inside Godot as its game logic, with Godot doing window, input, sound
and - step by step - the drawing? Everything here says **Ran** (with what was seen) or
**Read**. Kept current as the work goes; a successor needs only this file.

Nothing derived from the game is in the repository. `tools/godot/` holds glue, build
scripts, the Godot project's scripts and shaders. The translated code, the libraries, the
staged project, exported applications, pictures and logs are under `local/godot-spike/`.

## TWELFTH ROUND (2026-10-22, night): fire1's crowd at 60, the boar fight past 100 at 120

Built into `local/godot-r14/` (`RTA_GODOT_OUT=local/godot-r14`; a fresh snapshot of `tools/recomp` with round 11's patch
merged, and this round's `recomp.patch`; `build.py snapshot --refresh`, `lib`, `extension`, `project`). Tests, logs and
traces: `local/godot-r14/test/` - `fight.sh`, `fire.sh` (as round 11's; `SHOTS=...` takes window pictures at ticks),
`final14.sh` (the table's runs and the room), `mktable14.py`, `cols.py` / `persec.py` (the frame log by column, pictures in
each second), `imgdiff.py` (two pictures compared), `xfire.sh` + `tpsum.py` / `gpusum.py` / `encsum.py` (Instruments in
fire1's crowd), `room14.py`, `tapcheck/` (the tap's output compared, `rtag_host`). The machine as in round 11 (M5 Pro,
ProMotion up to 120 Hz; another agent's tests ran on it now and then).

| Asked | State |
|---|---|
| fire1's crowd (and any big crowd) at a steady 60, display resolution, everything on | **nearly, Ran**: 58.5 pictures a second at the rate 60, the slowest second 56.4 (it was 41.2 / 34.4); per second 56 to 61. At the rate auto 72.9 (was 40.6). What is left is the decoder's thread at the heaviest moment (16 ms a blank, below) |
| the boar fight / heavy fights closer to 120 | **Ran**: 106.1 pictures a second in the boar fight at the rate auto, the slowest second 100.1 (it was 90.7 / 87.7); 60.0 at the rate 60 with no picture over budget; walking in valor 110.5 (the slowest second 101.0, was 87.9) |
| measure each change: min / mean / 1 %-low, over budget, draws a frame, in hub, valor walk, boar fight, fire1 crowd, at 60 and auto | **Ran**, table below; the steps were measured in fire1's crowd as they were made |
| simulation untouched | **Ran**: two Godot copies in one room, A at the rate auto (7,754 pictures, 1,937 of them between game frames, the Elden Ring players and creatures on), B at 60: 1,842 ticks through a level change (hub, drunare), no shared column differs (`room1.log`). The tap on its thread makes the same bytes (below) |
| the picture correct | **Ran**: window pictures at fixed ticks, batches on against off (and the old tap): the level the same (fire1 without the Elden Ring creatures: mean difference 0.05 of 255, no pixel over 32; valor's hub and boar fight: mean 0.02 / 0.27 / 0.15, the HUD's target label most of it). With the Elden Ring creatures on, their figures differ in 0.24 % of the pixels by more than 32 (see "Still wrong") |

### What the crowd was made of (measured)

The "2,500 to 4,500 draws" of round 11 are fire1's **level**, not the crowd: a list of the crowd (describe at tick 700)
had 1,828 draws into the 3-D surface, 1,678 of them level chunks - 839 chunks drawn in **two passes** each (the first,
the environment-map layer, covers: `(0 - 0) x fix + Cs`; the second over it: `Cs + Cd x As`) - and 142 model draws.
The chunks' textures are shared: one texture for every first pass, about 70 for the second passes. And all 1,678 lie in
one stretch of the list, with nothing between them that blends over them.

Where the time went in the crowd (Instruments, round 11's code with the first batches): the decoder's thread **100 %
busy** (the scene tap 45 % of it), Godot's main thread 65 %, the GPU **96 % busy** - one render pass of 16 ms of
fragment work a picture (the boar fight's was 4.6). The level is drawn in Godot's transparent pass (the list's order),
which has no depth pre-pass: every chunk behind another was shaded in full (the lights, the sun's shadow, the contact
shadows, two textures).

### What was done (each measured in the crowd at the rate 60)

1. **The level's batches** (`rta_scene.cpp`, `Scene::batch_on`; look key `batch`, `RTA_BATCH=0` off). A level draw whose
   result does not depend on what is under it and that tests and writes depth "commutes": any order of such draws gives
   the same picture, but for exact ties of depth. Such draws go into the batch of their state (material) - one mesh per
   batch, written again each list from the chunks of that list (only where its bytes changed; positions that moved less
   than 0.01 unit are kept: the tap's positions differ in their last bits frame to frame) and drawn where the first of
   them was in the list's order. A draw that does not commute ends the stretch in which batches gather. A two-pass
   chunk is **one draw** (`GS_FUSED`, `V_FUSED`): the first pass's coordinates and colour ride in CUSTOM2, its state in
   "2" parameters, and the shader does the GS blend of the second over the first (`rgb2nd + rgb1st x destination`, both
   lit by the same light, so the blend of the lit colours is the light of the blend). No texture atlas or array is
   needed for fire1 (the textures are shared); valor's chunks each have their own texture and gather little (70 draws
   in 63 batches) - an array would be the next step there, if it is ever the limit. Crowd: 1,678 level draws in
   **65 batches**; 41.2 -> 45.8 pictures a second; Godot's drawing time the same and the GPU still 96 % busy.
2. **Depth first** (`GS_PREPASS`, look key `prepass`, `RTA_PREPASS=0` off): every solid batch (no alpha test: `GS_SOLID`,
   the alpha test's discard compiled out, so the GPU tests depth before shading) has its depth drawn first, before the
   first batch of its stretch, by a shader that writes depth and leaves the colour; the batches are then shaded only
   where they are in front (the depth test passes on equal). The crowd's main pass **16.0 -> 6.8 ms** of GPU a picture
   (the GPU 96 -> 61 % busy); 46.7 -> 52.4 pictures a second (with step 3's first form).
3. **The scene tap on a thread of its own** (`recomp.patch`, `render/scene_tap.{h,cpp}`): at each kick of the four mesh
   programs the decoder copies what the tap reads of VU1 memory (the strip, the packet's inputs and copy rows, a model's
   joint matrices) with the set-up's state, 32 kicks at a time to one worker, which runs the same `kicked()` in the
   same order. Then: the second kick of a two-pass packet takes the first's vertices instead of computing them again;
   the list's vertices and the corners are written in place (their counts are known); the clock read for one kick in
   eight. Checked: a figure over every piece, vertex, corner, joint matrix and source the tap made for 3,550 lists of
   the fire route (`RTA_TAP_DIGEST`, `tools/godot/lib/scene_export.cpp`) is **the same** with the tap on the decoder's
   thread and on its own (`RTA_TAP_ASYNC=0/1`), after each step; the skeleton check the same (194 million corners,
   largest difference 0.00071). The crowd's decoder **18.4 -> 13.3 ms** a blank on average, 16.1 at the heaviest moment;
   the worker 13.6 ms at that moment. In pictures a second: the thread itself 45.8 -> 46.7 (the GPU was the limit then),
   the copies trimmed and handed over 32 at a time 52.4 -> 57.0, the second pass's vertices and the writes in place
   57.6 -> 58.5.
4. **The main thread**: the 2-D layer's draws (a mesh made anew each list: Godot made new buffers and pipelines for each)
   are written again in place when they have as many vertices as the draw the pool's mesh held last
   (`mesh_for_flat`); the cleaner models' welded normals in an open-addressing table, and only for packets near enough
   to be curved and not left out for an Elden Ring figure (a crowd's hidden goblins were all welded). submit 6.4 ->
   5.0 ms a game frame; 57.0 -> 57.6.
5. **`display.upscale`** (`--display-upscale`, `settings.cfg [display] upscale`, `RTA_DISPLAY_UPSCALE`: off | metalfx |
   fsr; default off): only while pictures are drawn between game frames, the 3-D surface at 3/4 each way and enlarged
   (MetalFX spatial on Metal - Godot 4.5.2 has it - else FSR 1); at 60 every pixel. Measured with the batches and depth
   first: the boar fight at auto 101.6 -> 103.0, the crowd 69.6 -> 74.8 - the GPU is no longer what stops 120, so it
   stays off.

**Evaluated and not done**: GPU instancing of repeated props and creatures (the crowd's creatures are 142 draws and
the Elden Ring figures; switching the figures off changed nothing measurable); a texture array or atlas (above);
persistent RIDs for unchanged static packets (the kept meshes did that already; the batches are kept meshes written only
where they changed); cheaper shadows (the sun off was +3 pictures a second before the depth pass; not needed); Godot's
occlusion culling (needs occluders; the depth pass does the job for the level).

### Figures (`fstats.py`; paced; 3024 x 1964; shoulder; art pack, cleaner models, Elden Ring players and creatures)

As round 11 (min = the slowest one-second window; over budget = intervals over 1.5 x the usual one). "Round 11" are
its runs (`local/godot-r13/test`), on the same machine.

| Part | Run | pictures a second: min / mean / 1 %-low | over budget | worst interval | judder | controller to picture |
|---|---|---|---|---|---|---|
| hub | round 11, rate 60 (`final60e`) | 42.9 / 55.2 / 4.3 | 3 (1.6 %) | 235 ms | 40.1 ms | 35 ms |
| hub | round 11, rate auto (120) (`final120e`) | 71.2 / 98.7 / 9.5 | 8 (2.4 %) | 220 ms | 30.4 ms | 32 ms |
| hub | now, rate 60 (`h60`) | 42.2 / 55.0 / 4.2 | 5 (2.6 %) | 238 ms | 43.8 ms | 35 ms |
| hub | now, rate auto (120) (`h120`) | 68.1 / 97.9 / 8.3 | 12 (3.6 %) | 243 ms | 33.9 ms | 30 ms |
| valor, walking | round 11, rate 60 (`final60e`) | 59.0 / 60.0 / 38.4 | 2 (0.1 %) | 36 ms | 4.0 ms | 34 ms |
| valor, walking | round 11, rate auto (120) (`final120e`) | 87.9 / 110.7 / 62.8 | 49 (1.1 %) | 27 ms | 4.2 ms | 24 ms |
| valor, walking | now, rate 60 (`h60`) | 59.2 / 60.0 / 39.5 | 3 (0.1 %) | 35 ms | 3.6 ms | 33 ms |
| valor, walking | now, rate auto (120) (`h120`) | 101.0 / 110.5 / 59.3 | 159 (3.7 %) | 27 ms | 4.1 ms | 24 ms |
| valor, the boar fight (the heaviest fight) | round 11, rate 60 (`final60e`) | 58.8 / 59.9 / 36.5 | 25 (3.3 %) | 29 ms | 5.5 ms | 35 ms |
| valor, the boar fight (the heaviest fight) | round 11, rate auto (120) (`final120e`) | 87.7 / 90.7 / 66.8 | 1 (0.1 %) | 17 ms | 6.1 ms | 37 ms |
| valor, the boar fight (the heaviest fight) | now, rate 60 (`h60`) | 59.3 / 60.0 / 40.0 | 0 (0.0 %) | 25 ms | 4.5 ms | 34 ms |
| valor, the boar fight (the heaviest fight) | now, rate auto (120) (`h120`) | 100.1 / 106.1 / 57.6 | 175 (13.7 %) | 17 ms | 4.5 ms | 25 ms |
| fire1, the goblin band | round 11, rate 60 (`fire60e`) | 34.4 / 41.2 / 18.8 | 3 (0.3 %) | 195 ms | 20.7 ms | 43 ms |
| fire1, the goblin band | round 11, rate auto (120) (`fire120e`) | 31.7 / 40.6 / 17.3 | 6 (0.7 %) | 193 ms | 22.2 ms | 74 ms |
| fire1, the goblin band | now, rate 60 (`c60b`) | 56.4 / 58.5 / 18.8 | 106 (11.7 %) | 203 ms | 10.0 ms | 35 ms |
| fire1, the goblin band | now, rate auto (120) (`c120b`) | 58.7 / 72.9 / 21.5 | 17 (1.6 %) | 207 ms | 11.4 ms | 40 ms |

At the rate 60 on a 120 Hz display ProMotion runs with the drawing; with the drawing faster now, more game frames fall on
the turn after their time, 8 and 25 ms apart (the crowd's 11.7 % "over budget" at 60 are those; its judder 20.7 -> 10.0
ms). **Draws a list**: fire route (mostly the crowd) 914 list draws, of them 696 in 65 batches, 65 depth-only; the fight
route 181, of them 70 in 63 batches (52.5 depth-only).

**Where the crowd stops now** (blank by blank, `cols.py`): the decoder's thread at the heaviest moment (blanks 3,264 to
3,392: 16.1 ms a blank, its worker 13.6) - the GS model's strips (`Gs::world_run`), the copies for the tap, the hand-over
(`scene::take`, 3 to 4 ms there). Next: the hand-over on the worker or a second worker for the strips.

### Files changed (tracked)

`tools/godot/extension/src/rta_scene.cpp` (batches, fused pairs, depth first, weld table), `rta_drawer.{h,cpp}` (the
second pass's state in `material_for`, `blend_of`, `mesh_for_flat`), `rta_variant.h` (V_FUSED, V_REPEAT2, V_SOLID,
V_PREPASS), `tools/godot/project/shaders/gs_draw.gdshaderinc` (GS_FUSED, GS_SOLID, GS_PREPASS), `scene_view.gd` (look
keys `batch`, `prepass`; upscale), `main.gd` (`display.upscale`), `tools/godot/lib/scene_export.cpp` (`RTA_TAP_DIGEST`),
`tools/godot/recomp.patch` (the tap's thread), this file, `docs/PROGRESS.md`.

### For the coordinator (tools/recomp)

- Merge `tools/godot/recomp.patch` (render/scene_tap.cpp, scene_tap.h): the tap on a thread of its own, the second pass's
  vertices taken from the first, writes in place. Same bytes out (above). `RTA_TAP_ASYNC=0` keeps the old way.

### Still wrong / not done

- fire1's crowd: 56 to 61 a second, not a steady 60 at the heaviest moment (the decoder's thread). The 120 in the boar
  fight: 106 (the main thread and the decoder at 120 pictures).
- With the Elden Ring creatures on, their figures differ from before in a few places (0.24 % of the pixels of a crowd
  picture by more than 32; with the creatures off the level is the same): lava shows through translucent parts of the
  goblins' figures in other places. The figures are drawn in the transparent pass by the place of their game draws; a
  batch is drawn where the first of its chunks was, so chunks that came after a figure's place come before it now.
  Not looked at side by side by eye beyond crops; which of the two is right was not settled.
- The first second of the crowd (a teleport into it): stops of 0.2 s (and in one run three of 0.5 s: new materials and
  Godot's pipelines for the new shader variants); the hub's arrival stop as in round 11.
- Windows and Linux libraries not rebuilt (nothing new is required of them).

## ELEVENTH ROUND (2026-10-22, evening): 60 in the heavy fight, and more than 60 on a faster display

Built into `local/godot-r13/` (`RTA_GODOT_OUT=local/godot-r13`; the snapshot of `tools/recomp` is round 10's, taken
2026-10-22 12:22, with this round's `recomp.patch`; `build.py lib`, `extension`, `project`). Tests, logs and traces:
`local/godot-r13/test/` - `fight.sh` / `mkfight13.py` (the fight route: hub, valor, the boars, then 15 s more of
fighting; the Elden Ring layer with players and creatures on, shoulder view, the art pack, the cleaner models, paced, the
picture 3024 x 1964 = the display's pixels), `fire.sh` / `mkfire13.py` (fire1, the player put beside the goblin band),
`fstats.py` (the figures below from the new `--frame-log`), `fsplit.py`, `ftoggle.py` (look settings switched during
one fight), `xprof.sh` + `tpsum.py` / `gpusum.py` / `encsum.py` (Instruments' Time Profiler and Metal System Trace,
recorded with `xctrace`, summed), `room13.py`. The machine: this Mac (M5 Pro, ProMotion display up to 120 Hz); another
agent's headless Godot tests ran on it now and then (load average 1.5 to 4).

| Asked | State |
|---|---|
| 60 held in the heaviest fight (art pack, cleaner models, Elden Ring layer with players and creatures) | **done, Ran** in the boar fight of valor: at the rate 60, 59.9 game frames and pictures a second (the slowest second 58.8; it was 47.0, the slowest second 42.8); at the rate auto 90.7 pictures a second (the slowest second 87.7) over the same 60 game frames a second. Cause and fix below |
| more than 60 on a faster display, the game still a 60 lockstep | **done, Ran**: `display.rate` 60 / 120 / auto (default auto); the pictures between game frames drawn from the last two |
| proof: paced frame times at 120 | **in part**: 120 on the title and front-end screens, 110.7 pictures a second walking in valor, 90.7 in the boar fight - the drawing, not the game, is the limit there (below) |
| proof: no judder | **Ran**: every picture's own game time against when it was drawn (`fstats.py`, "judder") |
| proof: the simulation untouched | **Ran**: two Godot copies in one room, one at 120, one at 60: 1,827 ticks through a level change (hub, drunare), no shared column differs |
| fire1 crowd | **not 60**: 41.2 pictures a second at the rate 60 (it was 31.5), 40.6 at auto (the pictures between are left out there by themselves) - draw count (below) |

### What made the dips (measured)

**The decoder.** The library's decoder thread (VIF1, the VU1 programs, the GS model, the scene tap, the hand-over of
the scene) took **21.3 ms a blank** in the boar fight with the art pack and the layer on (`base60`; `rtag_info` has
new figures for it: `tap_ms`, `kick_ms`, `take_ms`, `skel_ms`). A frame is decoded after the game has finished it, and
the game stands at each blank until Godot lets it go: past 16.7 ms that is fewer than 60 game frames a second -
43 to 47 in the fight, `wait 10.4 ms` of every game frame on Godot's side. Instruments (Time Profiler, the fight): two
thirds of the decoder's time in `SceneTap::kicked` and below it. Two things in the tap (`recomp.patch`, for
`tools/recomp/render/scene_tap.cpp`):
- each source vertex was taken back to the world (a 4 x 4 inverse in double, the normal too) for **every corner** it
  stands at, in the list and again in the complete geometry - up to six times; now once per packet, the same bytes;
- the packet's identity was an FNV over its words **one byte at a time** - several kilobytes a kick, a few thousand
  kicks a frame; now XXH3 over the same words (`render/xxh3_64.h`, already in the tree). The identity is only ever
  compared within a run (kept meshes, the two passes of a packet, the occurrence count); its values changed.

Result: the tap 9.1 -> 4.2 ms, **the decoder 21.3 -> 9.4 ms a blank** in the fight (the walk 9.7 -> 4.4).

**Looked at and not the cause here:** texture uploads (1,062 textures made over the whole route of 5,758 lists, none
in the fight's profiles), shader compiles (none in the fight's profiles; the hub's arrival has one stop of 220 to 300
ms - a level load and its first shaders, "worst" below, not looked into), the curved models (PN triangles: 2.6 ms of a game
frame with the layer off, measured by switching `model_smooth` during a fight - within 60's
budget; a distance limit of 300 or 200 instead of 520 saved nothing measurable, the figures in a fight are near), the
game's own ground shadows (their small surfaces: 10 extra viewports a list in the fight, see below).

**Also fixed on the way:**
- The library's queue: the 60 path took the oldest of up to three finished frames waiting there (controller to
  picture 67 to 70 ms); now the newer one is taken too and drawn over it when that goes on for half a second (below).
- 60 on a 120 Hz display: Godot's loop runs with the display, and ProMotion follows it at whatever the drawing allows (90
  to 120 a second); a game frame is taken on the turn its time has come, so its pictures fall 8 or 25 ms apart now and
  then (3 % over 25 ms in the fight). Holding the loop to 60 by Godot's own clock (`Engine.max_fps`, with or without the
  display's pacing) was tried and was worse - 43 to 51 game frames a second, the turns 16 to 25 ms apart (kept as a test
  aid, `RTA_RATE60_HELD=1`). The rate auto has no such beat: every turn is drawn, at its own time.
- The character card's 3-D picture (`card.gd`, 256 x 320, MSAA) was drawn every refresh; now only while the portal is
  in front or its texture was asked for in the last two seconds.
- The game's ground-shadow surfaces: where Godot throws real shadows the drawer leaves the game's subtraction out, but
  still rendered the small surface the game drew each silhouette into - up to ten viewports a list in the fight. A run
  into a surface that only left-out shadows read is no longer drawn (`passes_skipped`), and reads by left-out draws no
  longer split a surface into runs (`RtaDrawer::scene_drops_blob`).

### More than 60: pictures between game frames (`main.gd` `_display_rate`, `_paced_between`; `RtaDrawer::redraw`)

`--display-rate 60|120|auto`, `user://settings.cfg [display] rate`, `RTA_DISPLAY_RATE`; default auto (the display's
refresh when it is a whole number of game frames: 120 Hz -> two pictures a game frame; 60 Hz -> as before). The game is
untouched: one blank let go, one list taken, per game frame, at 60 a second. Between two game frames:
- **the camera** of the last two game frames, carried on (`Transform3D::interpolate_with`, the field of view the same);
  a cut (moved more than 160 units, or turned more than 45 degrees) is not carried;
- **every moved object and its skin**: a kept mesh (rta_scene.cpp: the same draw from frame to frame - characters,
  creatures, weapons, the level) carries beside each corner where it was in the game frame before (`CUSTOM2`, 16
  bytes a corner, `w` = 2 when it moved); the world shader puts the corner `rta_tween` frames on along that motion
  (`gs_draw.gdshaderinc`, also the shadow twins); a draw whose box jumped (more than 40 units: a teleport, two alike
  that changed places) is not carried; one that stopped has its history cleared. Skinned figures are posed by the game
  on the CPU, so this is their pose carried on corner by corner;
- **the Elden Ring figures** (`er_layer.gd` `tween`): their bones of the last two game frames, carried on, the skin
  re-posed; the held weapons the same way; the carried lamp (`scene_view.gd`);
- what the CPU projects every frame (sprites, the game's 2-D layer) stays where it was.
The drawer draws the last list again with these (`redraw(t)`: the world's run and the shown surface's - the one that
copies the world - in their order; the rest of the frame's surfaces hold what they had).

**Carried on, not between.** A game frame is shown as soon as it is there, as at 60; the picture after it shows the
state half a game frame on, from the motion between the last two (a picture *between* the last two would show every
game frame half a frame later). **Releases ahead.** Each blank is let go `lead` refreshes before the picture that shows
it (the controller is read then): as few as the measured time from a blank's release to its finished frame allows
(`rtag_frame_age_ms`, `rtag_frame_since_release_ms`; 95th percentile + 1.5 ms; up at once when a frame was late, down
after two seconds). New optional library exports: `rtag_release` (let go without taking), `rtag_frame_age_ms`,
`rtag_frame_since_release_ms`. **When the game frames themselves come late** (their own drawing longer than a game
frame: fire1's crowd), the pictures between are left out - they would only take the game frames' time - and come back
after two seconds of game frames on time.

### Figures (`fstats.py`; paced; 3024 x 1964; shoulder; art pack, cleaner models, Elden Ring players and creatures)

Pictures a second: min = the slowest one-second window, 1 %-low = the rate of the slowest 1 % of picture intervals;
over budget = intervals over 1.5 x the usual one (a missed refresh at 120, over 25 ms at 60); judder = the spread of
(when a picture was drawn - its own game time), the slow drift of the two clocks taken out. "Before" is this round's
first run with round 10's code (the frame log added); at the rate 60 the 120 Hz display showed each game frame once
(the old code at 120 Hz was the same: a game frame every other refresh).

| Part | Run | pictures a second: min / mean / 1 %-low | over budget | worst interval | judder | controller to picture |
|---|---|---|---|---|---|---|
| hub | before, 60 (`base60`) | 33.0 / 50.2 / 3.3 | 6 (3.1 %) | 300 ms | 62.9 ms | - |
| hub | after, rate 60 (`final60e`) | 42.9 / 55.2 / 4.3 | 3 (1.6 %) | 235 ms | 40.1 ms | 35 ms |
| hub | after, rate auto (120) (`final120e`) | 71.2 / 98.7 / 9.5 | 8 (2.4 %) | 220 ms | 30.4 ms | 32 ms |
| valor, walking | before, 60 (`base60`) | 49.2 / 58.8 / 31.0 | 56 (2.3 %) | 52 ms | 6.8 ms | - |
| valor, walking | after, rate 60 (`final60e`) | 59.0 / 60.0 / 38.4 | 2 (0.1 %) | 36 ms | 4.0 ms | 34 ms |
| valor, walking | after, rate auto (120) (`final120e`) | 87.9 / 110.7 / 62.8 | 49 (1.1 %) | 27 ms | 4.2 ms | 24 ms |
| valor, the boar fight (the heaviest fight) | before, 60 (`base60`) | 42.8 / 47.0 / 25.0 | 46 (6.0 %) | 45 ms | 15.3 ms | - |
| valor, the boar fight (the heaviest fight) | after, rate 60 (`final60e`) | 58.8 / 59.9 / 36.5 | 25 (3.3 %) | 29 ms | 5.5 ms | 35 ms |
| valor, the boar fight (the heaviest fight) | after, rate auto (120) (`final120e`) | 87.7 / 90.7 / 66.8 | 1 (0.1 %) | 17 ms | 6.1 ms | 37 ms |
| fire1, the goblin band | before, 60 (`firebefore`) | 23.0 / 31.5 / 11.9 | 38 (4.2 %) | 196 ms | 38.2 ms | 388 ms |
| fire1, the goblin band | after, rate 60 (`fire60e`) | 34.4 / 41.2 / 18.8 | 3 (0.3 %) | 195 ms | 20.7 ms | 43 ms |
| fire1, the goblin band | after, rate auto (120) (`fire120e`) | 31.7 / 40.6 / 17.3 | 6 (0.7 %) | 193 ms | 22.2 ms | 74 ms |

**Controller to picture** (the blank's release, when the controller is read, to the picture that shows that game
frame; the shown surface copies the world drawn the list before, so a game frame is on screen one picture after it is
taken): at the rate 60 35 / 34 / 35 ms (hub / walk / fight), at the rate auto 32 / 24 / 37 ms - the same within 2 ms in the fight, lower elsewhere. The first runs of this round with the release time logged gave 67 to 70 ms at the rate 60: the old 60 path took the oldest of up to three finished frames waiting in the library's queue (the first frame of the run is made before any release, and a slow stretch leaves more behind). Now, at either rate, when the frame taken is older than the release pattern says for half a second of frames in a row, the newer one waiting is taken in the same turn and drawn over it (both lists go to the drawer: a list names the textures the ones before it made). fire1's crowd: 43 ms at 60 (388 before), 74 ms at auto.

### Where 120 stops in the heavy fight (measured)

Metal System Trace in the boar fight at 120: the GPU 95 % busy with Godot's work, 88 % of it fragment work; the main
3-D pass about 4.6 ms a picture, a second large pass 2.6. Taking away MSAA (`aa=0`), the sun's shadows, a quarter of the
pixels (`scale3d=0.75`, a new look key: the 3-D surface drawn smaller and enlarged with FSR 1) - each and together -
lifted the fight from about 90 to 100-110 pictures a second, never to 120: with the GPU then half idle, the CPU's
encoding of the frame (about 6.5 ms from the first to the last command encoder) and the GPU's execution follow one
another per picture. A bare Godot window on this display runs at 120 (7.9 ms median); the title and front-end screens
of the game run at 120. Godot's separate render thread (`--render-thread separate`, it runs under Forward+) changed
nothing. Left as it is: the full look at about 91 in the fight and 111 walking, smooth (judder figures), rather than a
lesser look at 105.

**fire1's crowd** is another matter: 2,500 to 4,500 draws and 500,000 to 840,000 vertices a list (valor's fight: 270
and 133,000). The decoder there: 20 ms a blank (it was over 30); the main thread: `submit()` 9 to 12 ms and Godot's own
drawing 9 to 16 ms, both by the draw count (each draw of the level has its own pre-lit texture, so batching draws of one
state would merge few). 41.6 pictures a second (it was 31.5); not 60.

### The room (`room13.py`)

Two Godot copies, each the portal with the game under it, on a room service of their own (127.0.0.1): copy A at the
rate auto (120 on this display: 8,431 pictures, 2,448 of them between game frames, the Elden Ring layer with players and
creatures on), copy B at the rate 60; friends, a room, the game's character screens, Start, the hub, a level change in
one lockstep tick to drunare, play in both. `compare.py ticks a b`: **1,827 ticks compared, no shared column differs**
(`local/godot-r13/test/room1.log`). The game's simulation is not touched by the rate: the pictures between are drawn
from what the last two lists already hold.

**The scene tap's change** checked in the C++ host (`rtag_host --scene3d --skeleton-check`, the fight route): 5,028,747
packets kicked, all handed on, 277,895,052 vertices checked against the programs' own positions, 0 off; 237,176,616
drawn corners re-skinned from their bind-pose sources: largest difference 0.00035 units (as in round 10)
(`local/godot-r13/test/skelcheck.txt`).

### Files changed (tracked)

`tools/godot/project/main.gd` (display rate, frame log, release timing), `scene_view.gd` (tween, `rta_tween`,
`scale3d`), `er_layer.gd` (tween of the figures), `card.gd`, `shaders/gs_draw.gdshaderinc`,
`tools/godot/extension/src/rta_drawer.{h,cpp}` (redraw, the CUSTOM2 format, skipped runs), `rta_scene.cpp`,
`rta_machine.{h,cpp}`, `rta_library.h`, `tools/godot/lib/rtag.{h,cpp}`, `skeleton_export.{h,cpp}`,
`tools/godot/build.py` (exports), `tools/godot/recomp.patch` (scene tap), this file, `docs/PROGRESS.md`.

### For the coordinator (tools/recomp)

- Merge `tools/godot/recomp.patch` (render/scene_tap.cpp, scene_tap.h): the tap's world positions once per vertex,
  XXH3 for the identity, its time counted.

### Still wrong / not done

- 120 in the heavy fight (about 91) and in fire1 (about 41 at either rate); the hub's arrival stop (220 to 300 ms, a
  level load).
- The Windows and Linux libraries are not rebuilt with the new exports (they keep working: every new export is
  optional; at a high rate without them the lead is not measured and stays high).
- The pictures between game frames were checked by figures (50.7 kept draws a list carried, 0.05 jumped), not by eye
  side by side.

## TENTH ROUND (2026-10-22): the skeletons of the frame, another game's figures on them

Built into `local/godot-r10/`. The library hands over each drawn animated model's skeleton (the game's own pose buffers,
parents, bind pose) and its bind-pose mesh (`rtag_skeletons_get`, `RtaMachine.get_skeletons`); the "real re-posing needs
object-space verts/joints" of the fourth round is done that way. The Elden Ring layer (`look.er_models`) draws the owner's
own converted models on it. All of it: `native-er-layer.md`.

## NINTH ROUND (2026-10-21, evening): the tester's kit, rims, the shop's Buy list, the Windows setup with Godot

Built into `local/godot-r9/` (`RTA_GODOT_OUT=local/godot-r9`; snapshot of `tools/recomp` taken this round; `run.py
import` once after `build.py all`). Tests and pictures: `local/tester/` (`g1`, `g2`: the kit; `grim/`: rims; `shop/`: the
shop; `hubcmp/`: the hub before and after the blending change).

| Asked | State | Shown |
|---|---|---|
| the tester's kit in Godot | **done, Ran**: the library keeps the rings and the crash handler (`app/testerkit.cpp`, `-DRTAG_HAVE_TESTERKIT`; new optional exports `rtag_report_begin`, `rtag_report_finish`, `rtag_build_line`, `rtag_report_told`; `RtaMachine.report_begin/finish`, `build_line`, `report_told`); `project/testerkit.gd` is the host's half: F8 or L3 + R3 held for a second, the window's picture into the report, a box (LineEdit; Enter / Start saves, Escape / Select drops), F9 the build line (left of the new HUD's minimap), the notes; `main.gd` holds the controller at rest while the box is open, adds its lines (`report_lines`: Godot's version, mode, window, the portal's settings) and hands `app report ...` lines to it | `local/tester/g1/box-s.png`, `note-s.png`; `g2` (crash and the next start) |
| rims | **done, Ran**: `rta_fill.cpp` draws RTAG_FILL_RIM blocks as skirts (the skirt's shader, no depth written), with the plain stone darkened by their grey (`fill.gdshaderinc` kind 3); `fill_rims` scene option; `RtaMachine.get_fill_info().rims` | `local/tester/grim/pvpfire2/sheet.png` (off left, on right) |
| the shop's Buy list | **opened, Ran; what drew wrong found and fixed**: the round-7 route with cross on "Buy" (`local/tester/shop/mkshop.py`: the list, down, its four tabs, an item, back out), the same route in the native program as the reference | `shop/v1.png`, `crop-buy-h.png` |
| the Windows setup with Godot | see below | |

**What drew wrong in the Buy list, and why.** Against the native program (the library's own renderer gives the same
picture to the pixel: `shop/g5`), Godot's scene mode had: the selected item's green glow white-grey, the red cells
(items too dear) gone, the whole list about 17 % darker; 14 % of the picture off by more than 8 of 255. The draws
(`app drawlog N`, new: `RtaDrawer.log_draws`, each draw's state): the glow is the item drawn 100 times a pixel apart in
the fog colour, added (`blend 0201`, fog on); the red cells one untextured quad list, red at alpha 32 over the cells;
the cells' textures are translucent over a black clear; and the whole list is copied 1.2 times brighter into the surface
that is shown (`tfx 2`, colour 153). With `--rendering-method gl_compatibility` the picture was right (within 1 of
255): **Forward+ blends in linear light**, the GS in stored values, and every translucent or additive draw over another
came out different. Opaque draws were exact already (the exact sRGB inverse of the fifth round).
**Fix** (`rta_drawer.cpp`, `rta_variant.h`, `gs_draw.gdshaderinc`, `view.gd`): under Forward+ / Mobile a surface with
no 3-D scene in it this frame - every 2-D surface, and the world's own surface in a frame where the game draws no scene
(the shop, the bag, the title screens) - is drawn in **stored space**: its draws write the stored values themselves as
the colour (`GS_STORED_SPACE`), so Godot's blending works on them as the GS's does; Godot then puts its sRGB curve on
the picture, which is taken off where such a surface is read (`GS_DECODE`, also by the world's draws), where it is shown
(`view.gd`, a canvas shader) and where it is written (`get_shown_image`). The world's surface with a scene in it is
drawn in linear light as before (Godot's lights, haze, shadows need it). `RTA_GODOT_LINEAR_BLEND=1` gives the old way
for comparing. **Ran**: draw mode, the whole shop route: 0.000 of every picture off by more than 8 (was 0.14);
scene mode 0.005 (the item's glow edge a pixel off, two thin seams at the item card's corner); the hub in scene mode,
chase, first person and the pause menu over the scene: 0.0001 or less off by more than 8 against the old way (`hubcmp/`).
**Not fixed**: in a frame with the scene, the 2-D layer over it (the HUD, the pause menu) still blends in linear light;
draw mode (not scene mode) under Forward+ draws no level after the shop (the same with the old blending: not this
change; not looked into).

**The Windows setup with the Godot version** (`tools/install/setup/build_setups.py`, `windows/setup-windows.ps1`).
`build_setups.py` puts the Windows export (`--godot-windows`, default `local/godot-r9/export/windows`: `RtaGodot.exe`,
`RtaGodot.pck`, the extension's DLL; made by `build.py extension --release --platform windows` and `build.py export
--platform windows`, our code only) into the payload as `godot/`, and a `SOURCE_ID` file (the commit; the build id of
`app/buildid.py` where there is no git) into the source. `setup-windows.ps1`: with `godot\RtaGodot.pck` in the payload it
asks `fromdisc.py` for `--godot` (`tools/godot/build_lib_win.py` on the player's PC, the library into `%APPDATA%\Open
Champions\RTA Godot`), and when `local\install.txt` names the library this build made, copies the three files to
`%LOCALAPPDATA%\Champions\godot` and makes "Champions Godot" on the desktop and in the Start menu (`RtaGodot.exe -- --disc
"<image>"`). Without the export, or if the library did not build, the setup is what it was. The proof passed: 737 files,
nothing of the game; `local/dist-setups-r9/Champions-Setup-Windows.exe` 39.9 MB (not uploaded anywhere).
**Ran in the Windows 11 ARM VM from a fresh user folder** (`C:\fresh9`: USERPROFILE, LOCALAPPDATA, APPDATA pointed at
empty folders, the setup started with `-Disc ... -Console -NoStart` by a task in the desktop session): Python 3.13.9 and
llvm-mingw 20261006 downloaded and checked (sizes, SHA-256), the source unpacked, the game translated and built (95 of 95
files in 32 s), the Godot library (40 of 40 files in 8 s, the translated game's 49 objects of the native build reused):
**6 min 38 s** from start to "@done", two shortcuts each on the desktop and in the Start menu. Then the installed
Godot version, from the fresh folder: (a) scripted (`--rendering-driver opengl3_angle`, scene mode, offscreen corner,
`RTA_TESTERKIT=1`): the library found in the fresh `APPDATA`, boot to the hub, a bug report with the text box
(`local/tester/winsetup/gbox.png`: the box and the build line "RTA 79dbdc1+ 2026-10-21 23:48 fixes 9ac29719 Windows
10.0.26300 x86-64" - the id from `SOURCE_ID`), the zip in the fresh data folder; (b) as the shortcut starts it (no
options but the disc, `--quit-after 1200`): Vulkan refused ("VK_KHR_surface not found"), Godot fell back by itself to
Direct3D 12 on Microsoft's Basic Render Driver, Forward+, ran the 1,200 frames and ended with 0. The installed native
`rta_app.exe` started too (llvmpipe; without `GALLIUM_DRIVER=llvmpipe` it ends with 0x80070057 - the Mesa D3D12-over-WARP
fault of `native-windows.md`, VM only). The setup in `local/dist-setups-r9/` was made again after the run with one line
more in `tools/godot/build_lib_linux.py` (the build id given to its container) and these notes; the copy that ran is
`Champions-Setup-Windows.tested-in-vm.exe`. **Not run**: a real PC (GPU, x86-64 processor), the setup's window (the
console mode was used), the portal by hand.


## EIGHTH ROUND (2026-10-21): aiming by looking, the Windows game library, the skirt's depth

Built into `local/godot-r8/` (`RTA_GODOT_OUT=local/godot-r8`; snapshot of `tools/recomp` taken this round; after `build.py
all` the staged project needs `run.py import` once, or the extension is not registered and `main.gd` does not parse).

| Asked | State | Shown |
|---|---|---|
| aiming by looking in the library and the portal | **done, Ran**: `fpaim.cpp` compiled (`-DRTAG_HAVE_AIM`), `rtag.cpp` as `app_main.cpp`, `main.gd --aim`, the room screen's "Aim" choice; two Godot portals in one room with it: 2,333 ticks in step, 24 arrows at 19 pitches, 2 casts (`docs/issues/native-first-person-aim.md` 3.5) | `local/aim/r8/groom3/` |
| a Godot game library for Windows | **done, Ran in the VM**: `tools/godot/build_lib_win.py` (the existing MinGW-w64 toolchain of `build_win.py`, its objects of the game when current), `librta_game.dll` 28.5 MB, 66 functions exported, only Windows' own DLLs; `fromdisc.py --godot` builds it on Windows (`install-windows.ps1 -Godot`) | `local/aim/r8/wgodot/` |
| the skirt hid the level (as the OpenGL program's 8.8 cause 3) | **found and fixed, Ran**: `fill_skirt.gdshader` writes no depth | `local/aim/r8/skirt/compare.png` |

**The Windows library.** New: `build_lib_win.py`; `lib/gl_offscreen_win.cpp` (a hidden window and `app/win/wgl.cpp`'s
core context); the Windows half of `lib/host_godot.cpp` (host_win32.cpp's threads, disc reads and sleep; quit tells the
library instead of ending); in `rtag.cpp` `cpu_ms` by `GetProcessTimes`, `_mkdir`, and `file_exists` by `_stat64` (the
C library's `stat` has a 32-bit size under MinGW and said "no disc image at that path" for the 4 GB image - found in the
VM); `png_write.h` without zlib there (`RTA_PNG_NO_ZLIB`: stored deflate blocks, its own CRC and Adler sums); the
one-step online's `net/online_win.cpp` linked (its window questions are never attached). **Ran** in the Windows 11 ARM VM
(no graphics chip; `native-windows.md`): the round-8 export (`build.py extension --release --platform windows`, `export
--platform windows`: `RtaGodot.exe`, `.pck`, the extension DLL, 94.2 MB) with `librta_game.dll` beside it.
`--rendering-driver opengl3` with Mesa's `opengl32.dll` beside the program: "Failed to create an OpenGL window" (Godot
does not take the OpenGL of a DLL beside it, Inferred). `--rendering-driver opengl3_angle` (ANGLE over Direct3D 11 on
Microsoft's Basic Render Driver) works: **picture mode** (the library's own renderer: "OpenGL 4.6 Mesa 26.2.4 on llvmpipe
(no window)", Mesa's DLL found beside the program, `GALLIUM_DRIVER=llvmpipe`, `GALLIUM_OVERRIDE_CPU_CAPS=sse4.1`) booted to
the hub, 2,621 blanks at 54.6 pictures a second, the hub's picture as on the Mac (`wgodot/hub-picture.png`); **scene mode**
(Godot's Compatibility renderer through ANGLE) the same route at 20.2 pictures a second (`wgodot/hub-scene.png`). Not
run on Windows: a room, the portal, sound (no device in the VM), a real GPU.

**The skirt.** `firbonus` in scene mode, first person at its start, headings 5 and 6 of the OpenGL program's probe
(`local/aim/r8/skirt/mkfb.py`, `fb.sh`): before (round 7's build) heading 6 has a pale band over the lava at the right edge
that `app look fill off` removes (1.45 % of the lower picture differs); after, fill on and off give the same lower
picture at both headings (0 %). Cause and fix in `native-first-person-world.md` 8.8, cause 3.

## SEVENTH ROUND (2026-10-20, afternoon): cleaner models, the game's own screens, an export without the game, room modes

**Read this first.**  Built into `local/godot-r7/` (`RTA_GODOT_OUT=local/godot-r7`; the sixth round's snapshot of
`tools/recomp`, with this round's `recomp.patch` hunk applied).  Pictures, logs and test scripts: `local/godot-r7/test/`
(`models.sh`, `mkmodels.py`, `screens.sh`, `mkscreens.py`, `probe.sh`, `mkprobe.py`, `fight.sh`, `room7.py`,
`memcard/`), `local/godot-r7/levels/`, `local/godot-r7/linux-test/`, `local/fresh-r7/` (the fresh-folder run).

| Asked | State | Shown |
|---|---|---|
| cleaner models | **done, Ran**: per-pixel form light, rim light, finer texture sampling, PN-triangle curving of skinned models, contact shadows (below) | `test/m4/sheet-{hub,valor}-{front,side}.jpg` (5 characters x 2 levels, off above / on below), `test/f1/sheet.jpg` (the boars in valor) |
| the shop and the other screens | **Ran**: the dialogue to "Enter Shop", the shop's Buy / Sell page, its Sell grid, back out; pause (all entries), the bag's four pages (equipment, items, the character sheet, quests); in the chase and overhead views | `test/s2/*.png` (`s1` is the same route before a fix) |
| the 7 unchecked levels, islc1, storm4 | **looked at, Ran** (below) | `test/p1/sheet.jpg`, `levels/seven/` |
| arenas without ground | **done, Ran**: the backdrop | `levels/arenas3/sheet.jpg`, `levels/arenas6/sheet.jpg` |
| an export without the game | **done**: macOS, Windows, Linux arm64 and x86-64 built; macOS and Linux arm64 run end to end (below) | `local/fresh-r7/pictures/`, `test/export1/sheet.jpg`, `linux-test/sheet.jpg` |
| a character from a memory card | **written, reader Ran on a made-up card; a real save not run** (below) | `test/memcard/` |
| arena and versus in a room launch | **done, Ran**: two Godot portals, the room's new "Game" choice, the game's own arena (Wave 1) and versus (Fight!) in pvparena, in step | `test/arena1/`, `test/arena2/` |

### Cleaner models (`rta_scene.cpp`, `gs_draw.gdshaderinc` GS_MODEL / GS_CONTACT, `scene_view.gd` keys `models`, `model_*`, `contact`)

Nothing the game computes changes: only how Godot draws what the tap hands over.  The model draws are the packets of
kind 2 (characters, creatures, props, weapons), solid ones (depth write, opaque or alpha-tested), not the sky dome.

- **Per-pixel form light** (`model_form`, 0.7): the game lit the model per vertex; the same normals per pixel give a
  soft key light from where the level's light comes from (`rta_sky_sun`), 0.8 .. 1.14 of the colour, wrapped.
- **Rim light** (`model_rim`, 0.35) in the sky's horizon colour, lighter (a warm one in dark levels).
- **Finer texture** (`model_sharp`, 0.6): the footprint the mip level is chosen from is scaled down for models (the
  art pack's pictures are sharp enough to take it; the level keeps its own).
- **PN triangles** (`model_smooth` 2, `model_crease` 0.35, `model_near` 520): every triangle of a *skinned* packet within
  520 units of the eye becomes 2 x 2 curved triangles (Vlachos et al. 2001), built on the CPU as the mesh is built; the
  normals the curve follows are welded over the frame by position (1/8 unit), so neighbouring triangles and the
  packets of one body meet without cracks; an edge whose welded normals part by more than the crease stays straight.
  Colours, texels and shading normals are interpolated.  Kept meshes take it (the smoothing level is in their figure).
- **Contact shadows** (`contact`, 0.55): the drawer finds the frame's standing figures (skinned objects' boxes, pieces of
  one figure merged, at most 16: `get_sky_info().contacts`); the level's solid draws (GS_CONTACT) darken softly within
  each figure's radius at its feet's height.
- **Found and fixed on the way**: a two-pass model (a face, a shoulder piece) was curved in its first pass and not in its
  second (blended, no depth write): the two fought in the depth buffer and the face showed dark specks (`test/s1`
  dialogue pictures).  The curve is now decided by the packet, never by the draw's state (`test/s2`: clean).
- **Cost** (the fourth round's fight route, chase, 1280 x 720, unpaced, `test/f1`..`f3`): `submit()` 2.98 ms a list with
  the models off, 8.8 ms with the first version, **6.1 ms** now (grid points made once per patch, the weld table
  reserved, nothing curved beyond 520 units); 141,685 curved corners a list in the fight; 63.6 -> 59.5 pictures a
  second unpaced.  The cost is on Godot's main thread: at 3024 x 1701 paced it was not measured again.
- How it looks: a little more shape and a lighter edge; textures crisper; the silhouettes rounder at shoulders, heads,
  tails.  Low-poly hands and feet stay what they are (2 x 2 does not add detail, it rounds).  Before/after pictures are 6
  frames apart (the idle animation moves a little between them).  `--look models=off` is the sixth round's look.
- The five characters: the class screen taken 0, 1, 3, 5, 8 times to the right (an Iksar, a Vah Shir, two Barbarians,
  an Elf); each other tap is lost there, so 1/2, 3/4 ... give the same class (`mkmodels.py`).

### The game's own screens (`test/s2`, `mkscreens.py`)

The sixth round's route never reached the shop: a press on the "More..." page went to the choice page before the
script pressed "down", and its "cross" then took "End".  Now: cross on "More...", wait for the choice page, down, cross:
**the shop opens** (Buy / Sell); down and cross open Sell, the bag's grid with "Sell / Back"; back out to the hub (Buy's list itself was not opened by the route).  All
of it is the game's own screen drawn by Godot in scene mode, pixel-clean.  What is left to say of them: the game's
full-screen menus are 4:3 and stand between black bars in a 16:9 window (as the game drew them); the 3-D scene is
not drawn behind them by the game.  Pause: all five entries; the bag: four pages (equipment with an item's card, the
items, the character sheet - level, experience, health, mana, armour, attack, damage, the four abilities, resistances
- the quest page).  Nothing drew wrong except the face specks above.

### The seven levels, islc1, storm4 (`test/p1`, `mkprobe.py`; `levels/seven`)

- `blood1`, `bossevil`, `bossgood`, `dis2`: a scripted opening holds the game's camera ("fallback cutscene"); tapped
  through (cross, start, circle), **the chase view along the ground is there** in each (pictures `*-2-forced.png`), with
  the presets of the sixth round in force: they look right (dark with torches, the purple sky, the forest at night).
- `endbad`, `endgood`, `intro`: films of the game's own camera with **no local player** ("fallback no local player",
  "camera reset"): `endbad` and `endgood` go on to the title, `intro` is the title's own fly-over.  There is no view
  along the ground to have; the game's camera is right there.
- `islc1` is in a ground view in the walk now; `storm4` at its last stop.

### The backdrop for arenas (`scene_view.gd` `backdrop`, `shaders/backdrop.gdshader`)

Of 16 arenas walked alone (`levels/arenas`), four put the character where the level is not: `pvpblo`, `pvpblo2`,
`pvpfire` hold the player at z = -100000 (the arena's own placement waits for a versus game), `pvpfire2` lets him walk
off its edge and fall.  The drawer now counts the solid draws whose box reaches under the player's feet
(`get_sky_info().ground_near`); after half a second without any, in a view along the ground, a plane of flagstones is
laid at the feet (colour from the level's sky, a soft shadow under the character, into the haze), drawn after the sky
and before every draw of the list; it follows the feet (a falling character stands on it), and goes a second after
ground is under the feet again.  `pvpinn` and the hub: never shown (`levels/arenas6`, `ground_near` 3..4).

### An export without the game (`build.py export --platform macos|windows|linux`, `project/gamelib.gd`, `fromdisc.py --godot`)

- **What an export holds** (checked by `build.py` after each export: no `librta_game*`, no `levels.cfg`): Godot's
  official 4.5.2 release template (from the archive of the official release, already here), our extension built for
  that platform, the project's scripts and shaders.  macOS `RtaGodot.app` 179.8 MB (8 files); Windows `RtaGodot.exe` +
  `.pck` + `rta_godot.windows.template_release.x86_64.dll` 94.2 MB (MinGW-w64 cross build from this Mac,
  `extension/cmake/mingw-x86_64.cmake`; it needs only Windows' own DLLs); Linux arm64 63.1 MB (built in the colima `rta`
  profile, image `rta-godot-linux:arm64` = the Linux build's image with cmake, ninja, git); Linux x86-64 69.6 MB, the same
  through the container's emulation (`rta-godot-linux:amd64`): it starts and loads the extension (headless, no disc).  The look presets made from the game's pictures (`levels.cfg`) are
  not in an export (`--with-game` makes the old private export with them and the library).
- **First start**: the game library is found by `res://gamelib.gd` (used by `main.gd`, the portal's profile and the
  extension's net2): `--lib`, the one chosen once (`user://settings.cfg [game] library`), beside the extension or the
  executable, **the installer's per-user place** (macOS `~/Library/Application Support/Open Champions/RTA Godot/`, Linux
  `$XDG_DATA_HOME/open-champions/rta-godot/`, Windows `%APPDATA%\Open Champions\RTA Godot\`).  The portal's disc screen
  now has a second state: the disc is there, the library is not - it says the installer builds it and offers to
  choose it.  `rta_net2.cpp` looked for `.dylib` on Linux too: fixed (`.so`), and it asks `gamelib.gd` first.
- **The installer**: `tools/install/fromdisc.py --godot` (on by default in `install-mac.command`, `--no-godot` to
  leave it out): after the native build, `build.py snapshot --refresh` and `lib` into `local/godot-install/`, the
  library copied to the per-user place; on Linux `tools/godot/build_lib_linux.py --here` (new, by a helper agent:
  arm64 and x86-64 built and dlopen-tested in the container, 66 exports each).  Windows: no Godot library build yet.
- **Ran, macOS, from a fresh folder** (`local/fresh-r7/`: the working tree's tracked and new files copied, a HOME of the
  test's own): `fromdisc.py --platform mac --godot` - the executable out of the disc, the translation, the native
  program, the Godot library - **about 2.5 minutes**; the clean `RtaGodot.app` then found the library by itself, booted
  to the title, the hub, valor (`pictures/1-title`, `2-hub`, `3-valor`); and **two copies of the exported application
  in a room on a local service** (`tools/rendezvous/rendezvous.py` on 127.0.0.1; `room7.py export1` with `ROOM_EXPORT`):
  friends, invitation, room, the game's character screens, Start, both in the hub, 250 ticks compared, "no shared
  column differs on any tick" (`test/export1/sheet.jpg`).
- **Windows (2026-10-21, round 8)**: the library now exists (`build_lib_win.py`) and the export ran in the VM: above.
- **Ran, Linux arm64** in the container (Xvfb, Godot's OpenGL renderer on llvmpipe): the clean export with the Linux
  library in the per-user place: title, hub (`linux-test/sheet.jpg`), 9 pictures a second in software.
- **Windows: built, not run** (no Windows here).

### Room modes (`portal/screens/room.gd` "Game", `recomp.patch` hunk in `net2/launch.cpp`, `dev/shots.gd` RTA_SHOTS_GAME)

The room has a "Game" choice: Missions / Arena / Versus 5 / Versus 10 / Versus 25 (`net2_options.mode` 0, 1, 2 and
`kill_limit`).  The library's direct launch wrote 0 into the settings block's mode, mission and kill-limit bytes; the
hunk writes the room's (+3 mode, +4 mission for missions, +5 the kill limit's entry 0/1/2 - that the byte is the entry
and not the number is not checked).  **Ran** (`room7.py arena1` / `arena2`, two Godot portals, local service): Arena ->
the game loads `pvparena` and says "Wave 1"; Versus 5 -> `pvparena`, "Fight!", the two players marked friend and foe;
both in step (223 and 235 ticks compared, no shared column differs).  The choices fit four in a row now (`Choice.narrow`).

### A character from a memory card (`portal/memcard.gd`, `screens/characters.gd` "From a memory card")

The characters screen has a card "From a memory card": a PCSX2 memory card file (`.ps2`, with or without the 16
bytes of error correction a page) or a folder of save directories; the directories of this game (`BASLUS-20973*`) and
of the first game (`BASLUS-20565*`, which the game's own Import lists) are copied into the copy's card folder
(`DATA/card/mc0/`), then the game's own character screen opens, where Import (triangle) takes one.  **Ran**: the reader
on a card file made by the test (`test/memcard/mkcard.py`: the card's file system with made-up files, a 5,000-byte file
over five clusters): both of the game's folders taken, the other left, every byte equal.  **Not run**: a real card
(none here) and the import itself - no card here holds a saved character (a save needs a save point: the autosave
fills the buffer only, docs/audio-save.md), and the scripted runs make new characters.

### Files changed this round (tracked)

`tools/godot/build.py` (extension and export per platform, the clean export and its check), `extension/src/rta_scene.cpp`,
`rta_drawer.cpp`, `rta_variant.h`, `rta_net2.cpp`, `extension/cmake/mingw-x86_64.cmake` (new), `project/shaders/gs_draw.gdshaderinc`,
`project/shaders/backdrop.gdshader` (new), `project/scene_view.gd`, `project/main.gd`, `project/gamelib.gd` (new),
`project/rta_godot.gdextension`, `project/export_presets.cfg`, `project/portal/{portal,profile,widgets}.gd`,
`project/portal/memcard.gd` (new), `project/portal/screens/{characters,disc,first,home,room}.gd`, `project/portal/dev/shots.gd`,
`recomp.patch`, `build_lib_linux.py` and `lib/gl_offscreen_linux.cpp` (new, the helper agent), `tools/install/fromdisc.py`,
`tools/install/install-mac.command`, this file, `native-hud.md`, `native-portal.md`.  Nothing in `tools/recomp`.

### For the coordinator (tools/recomp)

- Merge `tools/godot/recomp.patch` (net2/launch.cpp: the room's mode, mission, kill limit into the settings block).

### Still wrong / not done

- PN curving costs about 3 ms of Godot's main thread a list in a fight (6.1 against 2.98); not measured paced at full
  resolution.  It could move to the drawer's own thread, or be kept for meshes whose pose did not change.
- The kill limit's byte: entry or number - not checked (a versus game was not played to its end).
- A real memory card and the import: not run (above).  Windows: built only.  Linux x86-64: built, started headless only (no game run under emulation).
- The 4:3 full-screen menus between black bars in 16:9 (the game's own); nothing behind them.
- The look presets are not in a clean export (made from the game's pictures): a player's export uses the defaults and
  `tuning.cfg`; the installer could make them (`presets.py walk` + `make`, about half an hour) - not wired.

## SIXTH ROUND (2026-10-20): the souls mode in the library and the room, look presets for all 111 levels, the HUD in five views

**Read this first.**  Built into `local/godot-r6/` (`RTA_GODOT_OUT=local/godot-r6`; snapshot of `tools/recomp` taken
2026-10-20 with `build.py snapshot --refresh`: it carries `app/soulscombat.*`, `rt_replace_function`, the net2 room
option).  Tests, pictures and logs: `local/godot-r6/test/`, `local/godot-r6/presets/`, `local/godot-r6/balance/`.

| Asked | State | Shown |
|---|---|---|
| the souls combat mode in the library | **done, Ran**: `build.py` compiles `soulscombat.cpp`; `rtag.cpp` calls `soulscombat::blank` beside `fpcontrols::translate`, takes `combat.*` options and `app souls ...`, says the copy's room description in `rtag_info`; `main.gd --combat souls` | offline: dodge, heavy, lights, a poise break, blocks paid (`test/souls1/out.txt`) |
| ... on the portal's room screen | **done, Ran**: "Combat: Classic / Souls-style" (host); `gameflow.gd` says the copy's description to the room; the joiner's library follows; a copy without the mode: warning, Start refused | `test/souls2` (two Godot portals: **5,931 ticks in step**, every column equal, the mode's included; a fight in drunare, deaths), `test/refuse1` (-7 refused); `native-souls-combat.md` 6b |
| presets for every level | **done for 111** (`tools/godot/presets.py`: walk, make, sheets, stats; `project/presets/tuning.cfg` for hand-tuning; `scene_view.gd` loads them) | `presets/sheets/LEVEL.jpg` (before above, after below), `presets/sheets/index.jpg` |
| the Forward+ balance | **done**: the sun is computed for linear light, 0.6 of the way from the old rule (`balance`), and Forward+ grades with saturation 1.22 | `balance/` and the table below |
| the HUD everywhere | **Ran in all five views**; party frames added to first person; stamina moved onto the player's frame | `native-hud.md` STATE 2026-10-20 |

### The look presets (`tools/godot/presets.py`, `scene_view.gd`)

- **The walk**: one Godot program per chunk of 8 levels from power-on (a level whose scene keeps the game's camera
  can spoil the rest of a program: seen after `bossevil`, `dis2`, `blood1` - the walk puts the camera back to
  following the player, `[0x4F8450]+0x34 = 1`, as `tour.py` does), at most 3 at a time, 960 x 540, unpaced.  At 300
  ticks into each level, chase view: stop `a`; `g` the same moment with all of Godot's look off (the game's own
  colours); `b` after a walk, `c` the camera turned, `f` first person; each stop as the fifth round drew it (`old`)
  and with this round's balance (`base`); one `rta_look_stats` line a stop (clear colour, dome, dark, light level, far
  plane, the painted sun, the game's light nodes near the eye).
- **The pick** (`make`), per level: the kind (open sky 28, painted dome 19, dark 21, dark with three or more of the
  game's lights near 43) sets shade, haze distance and amount, bloom, the game's lights' energy, contrast, a low sun
  under a warm clear colour; brightness and saturation are moved half of the way to a target made from the `g`
  picture (0.85 of its brightness, 1.25 of its saturation), within 0.9..1.15 and 1.0..1.4.  Each section of the made
  file says why (`; dark, lit by the game's lights; light level 128; 7 of the game's lights near; brightness ...`).
- **Files**: `OUT/levels.cfg` (game output, staged into the project by `build.py project` as `res://presets/levels.cfg`,
  and into an export), `project/presets/tuning.cfg` (tracked, my numbers), `user://look_presets.cfg`, `--look-presets
  FILE` / `$RTA_LOOK_PRESETS`.  A key given with `--look` or `app look` stays as given; `--look preset=off` leaves
  them out.  `app look stats` prints the line the walk reads.
- **Not seen in a view along the ground** (their pictures are the game's own camera: a scripted opening or an
  ending): `blood1`, `bossevil`, `bossgood`, `dis2`, `endbad`, `endgood`, `intro` - presets made from their colours all
  the same, not looked at.

### The Forward+ balance (Ran, `local/godot-r6/balance`, stop a / b / c, lower two thirds, mean of 255)

| level | Compatibility (fifth round's look) | Forward+, fifth round | Forward+ now (balance 0.6, the level's preset) | the game's own colours (look off) |
|---|---|---|---|---|
| hub | 107, saturation 0.28 | 86, 0.22 | 104, 0.23 | 115, 0.19 |
| valor | 35, 0.58 | 29, 0.44 | 37, 0.44 | 52, 0.36 |
| tormenta | 61, 0.53 | 48, 0.65 | 60, 0.65 | 70, 0.52 |

Stop a, lower two thirds of the picture, mean brightness of 255 and mean saturation (`presets.py stats`; the
Compatibility pictures: `presets.py walk local/godot-r6/balance --renderer gl_compatibility`).  Brightness now matches
the Compatibility renderer within 3 of 255; the full linear rule (balance 1) went past it (hub 114, valor 47).
Over all 111 levels, stop a: 39.7 before, 45.6 after; saturation 0.406 -> 0.439.  **Left**: valor and the hub are still
less saturated than under Compatibility (0.44 / 0.58, 0.23 / 0.28) - its shadow tint and its sRGB approximations add
colour that Forward+ does not; the per-level saturation of the presets can be raised in `tuning.cfg` if wanted.

### Hand-tuning (`project/presets/tuning.cfg`)

From the contact sheets: the hub kept at brightness 1 (the made preset dimmed it), `storm5` (ice under a pale sky)
less bright and less glow, the four fire levels under an orange clear colour (`fire1`, `fire2`, `firbonus`,
`firmedal`) less saturation and glow.  Ran again after the change (`presets/after-h*.out`: the presets in force).

### Files changed this round

`tools/godot/build.py` (soulscombat.cpp; the presets staged and exported), `lib/rtag.cpp`, `presets.py` (new),
`project/main.gd` (`--combat`, `--look-presets`), `project/scene_view.gd` (presets, the Forward+ sun, grade keys,
`app look stats`), `project/presets/tuning.cfg` (new), `project/export_presets.cfg` (`presets/*.cfg` exported),
`project/portal/gameflow.gd`, `project/portal/screens/room.gd`, `project/portal/dev/shots.gd` (room5 with the
combat choice and the refusal), `project/hud/souls.gd`, `project/hud/status.gd`.  Nothing in `tools/recomp`.

### Still wrong / not done

- 7 levels never reached a view along the ground in the walk (scripted openings, endings, the title): see above.
  `islc1` and `storm4` were in a ground view before but not in the after walk (the game's camera at the stops).
- The arenas without a place for a character (`compsto`, `pvp*`) show the character in the void: not judged.
- The shop's own screens were not reached by the script (`native-hud.md`); a person should open one.
- Not played with hands: the combat mode in Godot, the room option, the presets in motion.
- Windows / Linux builds of the Godot library: not touched here (another agent's files).


## FIFTH ROUND (2026-10-19): Forward+ on Metal, the art pack, kept meshes written in place; the portal on the real service

**Read this first.**  Built into `local/godot-r5/` (`RTA_GODOT_OUT=local/godot-r5`, new in `build.py` / `run.py`: another
build directory beside the shared `local/godot-spike/`, which was NOT touched; the downloads are still taken from
`local/godot-spike/deps`).  Snapshot of `tools/recomp` taken again 2026-10-19 (it carries `net2/tls.cpp`: the game
library links Network and Security).  Tests and pictures: `local/godot-r5/test/` (`fight.sh NAME [main.gd options]`,
`fsum.py`, `cmp.sh`, `room.py`).

| Asked | State | Shown |
|---|---|---|
| the renderer | **Forward+ on Metal** is the project's renderer now (`project.godot`); the Compatibility renderer still works (`--rendering-method gl_compatibility`): the shaders carry both (`CURRENT_RENDERER`) | below |
| the art pack (the owner: "vision all blurry") | **done**: the native program's pack (`--art-pack DIR`, `$RTA_ART_PACK`, `user://settings.cfg [game] art_pack`, else `~/Library/Application Support/Play-RTA/textures` when it is there; `none` = without); mip maps for every texture, anisotropic 16x in the scene; two-field interface pictures sampled by the woven line as the native program does | `test/pairs/*-before.png` / `*-after.png`, `*-crop-before-after.jpg`; `test/fp/title-cmp.jpg` (the interface text, game's own above, pack below) |
| full resolution | the picture is drawn at the window's own pixels and follows the window (full screen, resized) when no `--size` is given; it was fixed at the size of the first frame's window | |
| 60 in the heaviest fight at 3024 x 1701 | **reached in the fight proper** (table); dips to 38-48 under a load average of 22-34 (another agent's three `rta_app_next` on 6 performance cores) | `test/*/out.txt` |
| character card on the portal's character screens | **hooked**: `portal.character_card()`; the home card, my seat in the room and the current character on the character screen take it (`Portrait.live`); not seen in a run (the room runs stood in the overhead view; the card needs the character standing in a view that shows it) | |

### What the time went into (sampled, `sample PID`, the fight at 3024 x 1701, Compatibility)

The main thread was the limit, not the library's decoder: 81 % busy at 26 pictures a second; 62 % of it Godot's
rendering through Apple's OpenGL-on-Metal layer (glDrawArrays 900 samples of 6271, shadows 600, post 550), 35 %
`RtaDrawer::submit` (of it `mesh_free` 902 and `mesh_add_surface` 687: the moving characters' meshes made and freed
every frame, 138 a list, 10,800 held).  The decoder thread (VIF1, VU1, GS model, the scene tap: `SceneTap::kicked`
two thirds of it) was 53 % busy - 7 to 12 ms a list, on its own thread, below a picture's 16.7 ms.

### What was done

1. **Forward+ / Metal.**  `gs_draw.gdshaderinc`: the 2-D surfaces' depth as Forward+ wants it (0..1, reversed: near is
   1; `1 - z`, the same winner of every depth test), the world draws' depth bias the other way; the exact sRGB inverse
   where the Compatibility renderer needed the inverse of its own approximations (`to_linear`, also `fill.gdshader`,
   `sky.gdshader`).  The surfaces are stored bottom up there: `RtaDrawer` (`rd`) turns over a surface read as a texture
   (`flip_surfaces`), the picture written (`get_shown_image`) and the region shown (`get_shown_region` +
   `get_shown_flipped`; `view.gd` draws it turned over).  First tries: everything black (the depth), then upside down,
   then washed out (the colour) - `test/cmp/`.  Left: Forward+ is a little darker and less saturated in the lit
   scene than the Compatibility renderer (valor's mean 51/61/46 against 58/65/44; the hub's painted sky pixel-exact):
   the sun / ambient balance (`scene_view.gd` `light_energy`, `rta_light_ambient`) wants a second look under Forward+.
2. **The art pack** (`extension/src/rta_pack.*`, `RtaDrawer.set_art_pack`, `main.gd` `--art-pack`, `--mipmaps`): the
   library names every texture as the emulator-based build does (`rtag_texture_names`, new optional export; scene mode
   turns `Gs::name_textures` on; `rtag_set_option("name_textures", "1")` for the other modes); three threads of low
   priority read the PNG, put it over the game's own pixels enlarged where it covers only the texture's corner, make
   the mip maps and hand it back; the texture's RID is given it (`texture_replace`), at most 48 MB a frame.  The fight
   route: 924 textures named, 921 found in the pack's 122,205, 920 replaced from files; the title screen 19 of 19 (17
   two-field interface pictures).  World draws sample with mip maps and anisotropy (`textureGrad` from the
   coordinates before the wraps: no seams).
3. **Kept meshes written in place** (`rta_scene.cpp`): a kept mesh is keyed by the draw's identity (its packets'
   figures, kinds, corner counts, and how many draws of that identity came before it in the frame); a draw whose
   content changed has its buffers written again (`mesh_surface_update_vertex_region` / `_attribute_region`,
   `mesh_set_custom_aabb`).  Fight: 0.5 meshes made a list instead of 138.4, 138.5 written in place, 384 held
   instead of 10,800; `submit()` 4.14 -> 2.84 ms a list.
4. Not done: the decoder's own cost (`SceneTap::kicked`, `tools/recomp/render/scene_tap.cpp`: another agent's tree);
   Godot's separate render thread (`--render-thread separate` crashed at start under Compatibility - not tried under Forward+).

### Figures (the fight route of the fourth round, chase, 3024 x 1701, paced; "fight" = blanks 3600 to 4900)

| Run | Renderer, textures | Fight: pictures a second min / mean / max | late (> 20 ms) | load |
|---|---|---|---|---|
| `base` (window in the corner) | Compatibility, the game's own | 25.4 / 41.0 / 56.0 | 662 of 1320 | 13-18 |
| `fplus3` (window in the corner) | Forward+, the game's own | **58.9 / 60.0 / 61.0** | 94 | 13-18 |
| `pack1` (window in the corner) | Forward+, the art pack, mip maps | 30.4 / 58.1 / 61.2 (the low ones are the windows with the route's 3024 x 1701 PNG writes) | 233 | ~13 |
| `t-new` (no PNG writes) | Forward+, pack | 47.7 / 57.2 / 60.9 | 331 | 16-22 |
| `t-new3` (no PNG writes, meshes in place) | Forward+, pack | 37.8 / 53.2 / 60.3 | 346 | 24-34 |

Found on the way: the route's pictures (six 3024 x 1701 PNGs, `Image.save_png` on the main thread, 1.7 to 2 s each)
were inside the fourth round's "heaviest fight" windows (blanks 4920 to 5280): those 17 to 22 pictures a second were
the test's own writes.  Without them the Compatibility renderer is not 60 there either (sampled above), Forward+ is.
A test window wholly off the screen is not drawn by Godot on macOS (the Compatibility renderer wrote black pictures,
a portal program stopped at `frame_post_draw`): `RTA_TEST_OFFSCREEN=1` (main.gd, shots.gd) now puts a borderless
test window beyond the lower right edge but for two points of its corner.

## STATE (2026-10-13, 09:15)

All five stages run. Nothing of this work is still running; test windows are closed.

| Stage | State | How it is known |
|---|---|---|
| 1. The game as a library | **done** | `librta_game.dylib` / `librta_game_orig.dylib`, C interface `tools/godot/lib/rtag.h`; 11 of 11 pictures identical to `rta_app`'s; the rig's session comparison the same file as the native application's |
| 2. In a Godot window | **done** | boots from power-on in a Godot 4.5.2 window; keyboard through Godot's input (110 key events: power-on to play); sound pulled by Godot's mixer; rig comparison through Godot the same file; 11 of 11 pictures identical |
| 3. Godot draws | **runs** | every draw of the list through the RenderingServer; 11 pictures within 3 of 255 of the library's own (mean 0.3); 15.6 ms of processor time a picture against `rta_app`'s 5.2 |
| 4. The scene in 3-D | **runs on the first level** | the scene's vertices put back into the world, a Godot camera following the game's; a Godot sun throwing real-time shadows of the characters on the level, a Godot lamp, the camera pulled back and turned: pictures under `local/godot-spike/test/scene/scene/` |
| 5. Export | **macOS done, Windows described** | `local/godot-spike/export/RtaGodot.app` starts the game (run without a window: two pictures identical to the library's) |

**What to look at first** (all under `local/godot-spike/test/`; nothing derived from the
game is in the repository):

- `scene/scene/hub-2-shadow.png` - the first level with a Godot directional light: the
  two characters and the props throw shadows on the floor, in real time, from Godot's
  shadow map. `hub-3-shadow-light.png`: the same with a warm Godot point light carried
  above the player.
- `scene/scene/hub-5-pulled-back.png`, `hub-6-orbit.png` - Godot's camera 2.2 times as
  far away, and turned by 40 degrees and tilted: the level as a 3-D object - and the
  honest part: the island ends in a saw-tooth edge where the game culled chunks for its
  own view, and the sky is a dome the size of a room.
- `scene/scene/hub-1-game-camera.png` against `scene/draw/hub-1-game-camera.png` - the
  same tick with Godot's camera on the game's, and drawn flat.
- `det/godot-draw/*.png` against `det/lib/*.png` - stage 3 against stage 2, 11 ticks.
- `g-keys/k2-pause-window.png` - the Godot window after a session played by keys alone.

**Left** (in the order it would be wanted): section "Left" at the end.

## FOURTH ROUND (2026-10-13, from 23:05): ceilings, the game's lights, the character card, speed; net2 from the library

**Kept current; whoever resumes reads this first.**  Pictures, logs, helpers: `local/godot-spike/test/r4/` (`go.sh`,
`mkroute.py` as in r3, pictures into `r4/NAME`; `R3_POST="app look lights"` = lines after picture a).  `base/` = before
this round (the library's plain dark fill in the list, no torches), five levels, first person and chase.

### State (2026-10-14, 00:45)

Nothing of this work is running.  Pictures of the end state: `test/r4/fill7/` - `before-after-first-[ac].jpg` (left
`base/`, right this round; honor, arachna1, nitdung1, inmine1, drunare), the chase pictures `LEVEL-chase-[ac].png`
against `base/LEVEL-chase-[ac].png`, the character cards `LEVEL-chase-card.png`.

| Asked | State | Shown |
|---|---|---|
| ceilings and skirts in Godot, textured from the level | **done** (Ran, five levels, two views) | `fill7/before-after-first-c.jpg`: honor grey stone, nitdung1 brown stone, inmine1 mossy rock, arachna1 dark rock, where it was black or one flat dark colour; drunare's ceiling is above its awnings, not in view |
| lights at the game's torches, braziers, glowing things | **done**: Godot omni lights at the game's own light nodes, the nearest two with shadows; the carried lamp only where no game light reaches | modest: arachna1's lower half 16.8 -> 22.6 of 255 by the camp fire, inmine1 38.9 -> 41.4, nitdung1 none (its torches are 538 and 831 away at the stop) |
| the portal's character card | **done**: `handover.game.call("get_character_card")` -> Texture2D | `fill7/*-chase-card.png`, `card2/hub-card.png` |
| 60 paced at display resolution in a heavy fight, everything on | **not reached** (table below) | `speed1..5/out-chase.txt` |
| `app view set` prefix | fixed in the library by the integrator; `app view set first.fov 62` taken without a refusal (`speed1`) | |
| heat haze reading last frame's picture | **not done** | |
| macOS export | **Ran**: `extension --release`, `export` (202.5 MB, signature verifies); started without a window, its two pictures identical to the third round's (`test/r4/export/`) | |
| net2 through the library | **Ran** (below) | |
| the merges of 0a89b9e (game-art hooks, g_ram guards) | **Ran**: snapshot refreshed, both libraries rebuilt; smoke test 2 of 2 pictures identical; the portal started without a disc (plain skin) and with one (the game's skin), no script errors (`test/r4/smoke/`, `test/r4/portal/`) | |

**Speed** (paced, the tick-keyed fight route `mkfight.py`, chase, 16:9; the machine shared, load average 18 to 29 the
whole time; processor time = all threads of the process; "fight" = blanks 3600 to 4900 of the route):

| Run | Picture | Look | Fight: pictures a second | processor ms a picture | submit() over the run |
|---|---|---|---|---|---|
| `speed1` | 3024 x 1701 | everything on (sky, haze, sun 4 splits, 8 torch lights 2 with shadows, lamp, bloom, grade, fill, aa 4) | 20 to 32 | 41 to 63 | 9.9 ms |
| `speed2` | 3024 x 1701 | torch shadows off, aa 0 | 25 to 38 | 36 to 53 | 6.7 ms |
| `speed3` | 1280 x 720 | everything on | 34 to 44 | 32 to 48 | 6.1 ms |
| `speed4` | 1280 x 720 | sun and torch lights off | 34 to 47 | 30 to 51 | 6.7 ms |
| `speed5` | 1280 x 720 | as speed4, the tap's check off (`RTA_SCENE_CHECK=0`) | 30 to 37 | 36 to 51 | |

Before the fight the same runs hold 60 (valor, 3024 x 1701, everything on: 59.4 to 59.9 a second, 19 ms).  The fight in
chase is **processor-bound, not bound by the picture size or the lights**: up to 290,000 vertices a list; the library's
decoder thread (VU1, GS model, scene tap) 10 to 13 ms a list on average (5.4 in the third round's first-person valor),
the game thread 22 to 28 ms of wall time a blank, Godot's main thread 7 to 14 ms.  What this round did for it: kept
meshes (below) - on the same five-level tour, unpaced, submit() 18.8 -> 8.0 ms a list and 20.2 -> 42.2 pictures a
second (`base/` against `fill5/`; NOT at the same load average).  What it would take further, in this order: the
decoder's cost per vertex (the full-geometry replay of every packet), re-posing kept model meshes from the tap's
object-space vertices and joints (needs `TapFrame` sources and joints through `rtag.h` and the source index of each
`TapFull` corner: a `scene_tap` change), fewer draws a list.

### Ceilings and skirts (`extension/src/rta_fill.cpp`, `project/shaders/fill.gdshader`; look `fill`, `fill_light`, `fill_scale`)

- The level's fill comes from `rtag_fill_get` (`RtaMachine.fill()` / `get_fill_info()`): one Godot mesh and instance per
  128-unit block, made again when the serial changes.  Drawn in the list's order right before the level's first
  depth-writing draw (after the sky, the dome and the clearing rectangle; skirt before ceiling), depth tested and
  written (a skirt since round 8 not written: `fill_skirt.gdshader`), in the transparent pass (which casts no shadow).  A ceiling block only while the eye is under its top, and a
  ceiling seen from below only (as `Gs::draw_fill`).  The library's own plain fill in the list (the world work draws
  it through the GS too) is recognised and left out while Godot draws it (figure "the library's own fill draws left out").
- **Material: a swatch of the level's own texture.**  While the level is drawn, a level chunk near the eye whose wall
  triangles reach up to the ceiling's lid (a 32-unit grid of the fill's lowest ceiling height says where; for skirts:
  ground facing up beside the rim) gives a 64 x 64 swatch: a patch cut from INSIDE its largest triangle in texels (a
  chunk's texture is an atlas of its faces - a bounding box of many triangles brought black parts of other faces with
  it), its grain softened (x 0.65), brought to one brightness (0.30), mirrored-tiled in the shader (`fill_scale` 0.45 a
  64-unit tile).  One swatch a frame at most, at most 40 a level, none within 300 (ceilings) / 420 (skirts) units of
  another; each block takes the nearest of its kind (48 blocks re-assigned a frame; all at once when the first is cut);
  before any is cut, a dark stone made in the shader.  The drawer keeps every texture's pixels in scene mode for this
  (`cpu_textures`, freed with the texture).  `RTA_GODOT_FILL_DUMP=DIR` writes the swatches (game pictures: local only).
- Shading: swatch x `fill_light` (0.42), a crease where the ceiling meets the wall (x 0.40 at the wall to 1 at 34 units),
  darker toward the middle of a hall (to x 0.70 at 200 units); haze as the level's (a ceiling at 0.72 of its distance);
  the ceiling keeps its own colour where no light is (EMISSION) and Godot's point lights add (light()); the sun does not
  reach it (layer 2; the sun's cull mask is layer 1, and the shader adds nothing of a directional light to a ceiling).
  A skirt is lit like the ground (rta_light_ambient + sun) and fades with its alpha.

### The game's lights (`RtaMachine.get_lights`, `scene_view.gd` `_torches`; look `lights`, `light_energy`, `light_max`, `light_shadows`)

- The game's point lights are nodes of its 90 x 90 light grid (`g_lightGrid` 0x5d34d8, 256-unit cells from -11520, the
  first word of a node is the next; overflow list 0x5db368; `render-pipeline.md` 5.2; the walk read from the translated
  `light_collectNear` 0x147bf0).  Fields as read (Ran, five levels): +0x08 layer (s8, against 0x4039a4), +0x12 the level
  colour (s16 x 4, 0x80 = 1), +0x1c the radius the game's own search uses, +0x28 falloff = 1 / radius^2, +0x2c floor,
  +0x30 position.  Found: nitdung1 and arachna1 warm (0.40, 0.30, 0.14), radius 240 (torches); inmine1 blue (0.27, 0.39,
  1.72), radius 136..141 (it moves: the game's flicker); honor blue-white (1.13, 1.59, 1.91) at 65.5 high, radius 100..103;
  drunare warm (1.56, 1.17, 0.39), radius 129..137; arachna1 also a white one (1.47) 8 units from the eye.
- Each frame the nearest `light_max` (8) within 1300 units of the eye become Godot omni lights: the game's colour made
  a little warmer (30 % toward 1.0, 0.70, 0.42), range 1.15 x the game's radius (so its flicker comes through), energy
  `light_energy` x 2.4 x (1.25 in a dark level, 0.8 else) x the colour's peak (0.25..1.6), and a slow flicker of Godot's
  own (three sines, +-13 %); the nearest `light_shadows` (2) throw shadows (the caster twins; their meshes now carry real
  boxes, so Godot culls them per light).  The carried lamp (auto) fades out where one of the game's lights reaches the
  player.  `app look lights` prints them.

### The character card (`extension/src/rta_card.cpp`, `project/card.gd`)

- **The call for the portal: `handover.game.call("get_character_card")` -> `Texture2D`** (main.gd; a SubViewport's
  texture, 256 x 320, transparent background, changes by itself; `has_character_card()` says whether a figure was taken).
- The player's model packets are those of the tap standing in a cylinder of 34 units round `rtag_view::player`, up to
  120 above the feet; they are taken when the character has stood still 30 frames (again every 6 s while it stands),
  copied relative to the feet with their own copies of the textures, and drawn in the card's own world with the scene's
  materials, a warm key and a cool rim light, turning at 0.45 radians a second.  In first person the game leaves the
  player out of its frames: the card keeps what it had (nothing, if the player has only ever been in first person).
- Found on the way: a SubViewport with `own_world_3d` renders a COPY of its `world_3d` - instances put into
  `world_3d.scenario` from C++ are not drawn; `find_world_3d().scenario` is the one.

### Speed: kept meshes (`rta_scene.cpp`, scene option `keep`)

- A draw whose packets are, by identity, exact colours and texels and positions to 1/16 unit, those of a mesh made
  before takes that mesh (`place_mesh`: the material on the instance) instead of being built and sent again; meshes
  nothing drew for 30 frames go.  First try keyed on the bytes: only 33 of 222 draws a list were taken in the hub (the
  tap's world positions differ in the last bits while the camera moves).  Keyed as now: 228 of 354 draws a list on the
  five-level tour (86,000 corners a list not sent again); in the fight 73 of 210 (the characters move).
- Every mesh of the scene now carries its real box (it had one of +-1,000,000): Godot pairs the lights with what they
  reach and culls the shadow casters per light.

### Other changes of this round

- `build.py project` puts a copied library over its name instead of writing into the old file (a Godot that has the old
  one loaded - another agent's test - keeps running).
- `lib/scene_export.cpp`: `RTA_SCENE_CHECK=0` (test aid) turns the tap's own check off.
- `project/dev/net2_flow.gd`, main.gd `--net2-flow ROLE:DIR`: the room flow as the portal is to drive it.
- New in `extension/src`: `rta_fill.cpp`, `rta_card.cpp`, the header `rta_net2_api.h`.  `CMakeLists.txt` takes them by
  its glob and needs no new include path (only the net2 option changed).  Built from clean with everything of this
  round in it (00:45: 1036 steps, 0 warnings; earlier the mock-only variant: 1038 steps, 0 warnings).

### Still wrong / not done

- The ceiling is a height field (the library's): in honor it hangs down over the court's gaps as a curtain - now
  visible as stone where it was black.  Swatches come from what has been drawn: the first seconds of a level show the
  shader's plain stone.  Skirts were seldom given a swatch (0 or 1 a level: their rim is rarely near the eye).
- The torch lights are modest; where the game's own vertex light already makes the torches' pools, Godot adds little.
  `light_energy` is the knob.
- The card needs the character seen standing in a view other than first person (the game leaves it out there); it is
  posed as it stood, not animated.
- 60 in a fight in chase: not reached.  Heat haze: still last frame's picture.

### Files outside `tools/godot` this round needed

- `tools/recomp/net2/launch.cpp`: the lock around the game's calls - merged by the coordinator (aa7ffd6).  Nothing else.

### A room of our own: RtaNet2 on the library's net2 (Ran)

- `extension/CMakeLists.txt`: `RTA_GODOT_NET2_SERVICE` (default ON) = RtaNet2 takes `net2_*` from the GAME LIBRARY (one
  session object in the process, `docs/issues/native-rendezvous.md` 5.1); the extension compiles none of net2 and has no
  socket code (`nm`: 0 net2 symbols; the library exports 46).  OFF: its own copy of session code with `NET2_NO_SERVICE`,
  the mock only.  Both built from clean (1035 / 1038 steps, 0 warnings).  `src/rta_net2_api.h` is the table every call
  goes through.  `RtaNet2.open()` loads the library itself when RtaMachine has not (config `library`, else main.gd's places).
- New for the portal: `has_game()`, `from_library()`, `get_error()`, `game_attach()`, `game_status()` ({phase, launches,
  failed, text, character, level, tick, players, difficulty_unlocked}), `game_choose(as_host)`, `game_launch()`, `game_stop()`.
- **Run** (`test/r4/net2/flow.py` -> `run2/`): two Godot programs (game scene, own data folders, `--opt net2-boot=1`), a
  service on 127.0.0.1:41950; the session side is `project/dev/net2_flow.gd` (`--net2-flow ROLE:DIR`: what the portal is
  to do - open, game_attach, host / join(code), game_choose at TITLE, ready at CHOSEN, start when every other member is
  ready and back); the game's screens by n2party's own script lines.  Room DYUCG: game 1 to tick 1167 (host) / 934
  (joiner, who then left by the pause menu), both back at the title, "Play again" (choose, ready, start), game 2 past tick
  738; both exit 0.  Tick logs NOT compared column by column.
- **Found**: `launch.cpp` `on_tasks` held `net2impl::big_lock()` across do_launch's calls of the game; the game reached a
  vertical blank and waited for the host's step while the host (Godot's main thread) waited for the lock in `net2_poll`:
  both programs stood still at "the room started" (`run1`, sampled stacks).  `recomp.patch` lets the lock go around each
  game call of do_choose / do_launch (notes at its head).  For the owner of `tools/recomp/net2`.
- The portal does not yet call game_attach / game_choose / ready around its room (the portal agent's part).

## THIRD ROUND (2026-10-13, from 15:25): sky, haze, light, the portal's joins, the HUD's requests

A new agent on the Godot side, from the notes above and below.  **Kept current; a usage limit can stop the work
without warning - whoever resumes reads this section first.**  Everything says **Ran** or **Read** / **not run**.
Pictures are game output: `local/godot-spike/test/r3/` (`base/` = before, as the second round left it).

### State (16:45)

**Ran** (pictures: `local/godot-spike/test/r3/`; `base/` is the state the second round left)
- **The snapshot is the shared tree** of 15:50 through a stand-in root (`local/godot-spike/root`: `tools/recomp`
  copied, two lines added to its `hle.txt`, the game translated and compiled again there, both variants) -
  `build.py snapshot --refresh --from local/godot-spike/root`.  `scene_tap.*` is found in `render/` (merged there).
  Both libraries, the extension (debug and release) and the staged project are built from it.
- **Sky for every level, haze by distance and height**, in chase, shoulder and first person through hub,
  tormenta, valor, honor, arachna1, fire3, islsm1 (`sky2/`: first person; `look1/`: chase and shoulder, `*-w.png` =
  the Godot window with the new HUD).  The ring dome's seam is gone (hub, tormenta), the hemisphere of islsm1
  stands as it is, levels without a dome have a sky from their clear colour, black stays black.
  Before / after: `base/hub-first-a.png` -> `sky2/hub-first-a.png`; `base/tormenta-first-c.png` ->
  `sky1/tormenta-first-c.png`; `base/valor-first-c.png` -> `sky1/valor-first-c.png`; `base/arachna1-first-a.png` ->
  `sky2/arachna1-first-a.png`.  To show: `look1/hub-chase-a-w.png`, `look1/tormenta-shoulder-a-w.png`,
  `look1/valor-shoulder-c-w.png`, `sky2/fire3-first-a.png`, `sky2/islsm1-first-a.png`, `fight1/fight-1-first.png`.
  **The last set, with everything of this round in it** (the sun from the level, thinned foliage, the new HUD):
  `final/LEVEL-chase-[ac]-w.png`, `final/LEVEL-first-[ac]-w.png` - e.g. `final/arachna1-chase-a-w.png` (the cave
  under the player's lamp), `final/valor-chase-c-w.png`; a fight over the shoulder: `fight2/fight-2-shoulder-w.png`.
- **The overhead view is untouched by all of it**: overhead with the default look against everything switched
  off, 6 pictures (hub, valor, arachna1), **identical pixel for pixel** (`ovdef/` against `ovplain/`,
  `test/r3/cmp.py`; both with `aa=0`).  The one thing the default changes there is multisampling (`aa=4`: 3 to
  4.5 % of the pixels, all along edges; `ovaa/`).
- **Bloom and grade do something** in the Compatibility renderer on the drawer's viewport: the same tick with and
  without (`bloomon/` against `bloomoff/`, `gradeoff/`): bloom changes 25 to 38 % of the pixels (0.1 % by more
  than 16 of 255), the grade nearly all by at most 12.
- **A fight in first person** (`fight1/`, the tick-keyed fight route): no "blocky cloud".  What that was: sprites
  that are depth-tested (particles, glows, sparks) were drawn as a flat layer over everything; they are in the
  world by their depth now and fade near the eye.  What still covers the picture in valor's forest is level art -
  the crowns of the trees are flat cards at head height (`fight1/fight-5-first.png`); such cut-out cards are now
  thinned out within 64 units of the eye (look switch `foliage`; `fight2/fight-5-first.png` against
  `fight1/fight-5-first.png`: the sheet across the eyes is a stippled veil one sees through - grainy, a smoother
  pattern would be better).
- **The look controls are in the library** (`fpcontrols.cpp` compiled in, wired as `app_main.cpp` wires it).
  `app fpc hud` prints their state in a Godot run.  The pointer path of `main.gd` (capture, Escape, buttons) is
  **not run** (a test window takes no pointer).
- **The extension builds from clean** (a fresh CMake directory, 1036 steps, exit 0; `local/godot-spike/build/clean-r3`).
  No source file was added to `extension/src`, `CMakeLists.txt` is unchanged.
- **The portal's joins: 17 of 17 checks pass** (`project/dev/join_test.gd`, the game scene under the real portal,
  a script to the first level; `test/r3/join/out.txt`, pictures `join-1 .. join-4`): the game scene knows its
  portal; view, picture shape and sharpness arrive at the first start; view, shape (4:3 -> 16:9), sharpness and
  music volume change while the game runs; the controller is held while the portal is in front of the running
  game and given back; "session over" brings the portal back with the game standing blurred behind it
  (`join-4-portal-after-the-session.png`) and the program goes on; "play again" wakes the same scene.
- **The HUD agent's requests** ("For the HUD" below): all four built; `music_volume` and `game_hud_text` are
  accepted by the library built here.  That the boss meter / prompt box really go and that the music really gets
  quieter was **not looked at / listened to**.
- **Speed, paced** (`paced2/`, `paced-*/`; a 640 x 480 test window, picture 1280 x 896, first person, sound
  pulled by Godot's mixer, load average 10 to 12): valor **60.0 pictures a second at 9.5 to 9.9 ms of processor
  time a picture over all threads**, 0 to 5 pictures of 300 later than 20 ms; the hub's first seconds in first
  person 44 a second with shader variants being made (164 late, once per run); the title scene (overhead, 175,000
  vertices a list) 60 at 25 ms.  **The look costs the processor nothing measurable**: the same route with sky,
  fog, sun, bloom, grade and multisampling all off: 9.1 to 9.7 ms (the sun with 2 splits: 9.5 to 10.4).  The time
  is the game, the decoder (5.4 ms) and `submit()` (3 ms: a mesh per draw, rebuilt every frame).
- **The macOS export** (`build.py extension --release && build.py export`, 201.9 MB, signature verifies): started
  without a window - the portal passes straight on - its two pictures are identical to the second round's
  (`test/r3/export/`).  One line at its end: "ObjectDB instances leaked at exit" (not looked into).

**Found on the way**
- The new HUD shows the word "down" in the player's frame in the tour pictures (`sun1/hub-shoulder-d-w.png`): the
  tour route writes the game's invulnerability word (0x44f20c) - for the HUD agent to look at, not a Godot matter.
- **The disk was full at 15:55** (under 400 MB free of 1.8 TB; not this work's) and macOS **evicted files of the
  synchronised workspace folder** ("dataless": `ls -lO`): seven of `symbols/*.tsv`, parts of `tools/recomp`
  (`rigcompare.py`, `sound/spu2.cpp`, `sound/audio_out.cpp`, `app/pad_mac.mm`, ...), many `tools/*.py`, some
  `docs/issues/*.md`.  Reading one blocks (a test run stood in `script_add_symbols` for minutes); at 16:10 they
  still did not come back within 10 s.  The test runs here need no workspace symbol files any more
  (`test/r3/mkroute.py`, `mkfight.py` write addresses; `go.sh` gives no `--workspace`).  **Because of this the rig
  session comparison and the 11 reference pictures were NOT run again on the new libraries** (both need
  `rigcompare.py` / the symbol files), and a `snapshot --refresh` from the shared tree would hang.
- **16:9 changes where the character starts** (stand-alone `rta_app`, off screen, overhead view, no input): hub,
  tick 20: 4:3 `131.57 -96.23`, facing word 15436; 16:9 `113.79 -157.66`, 16482; the front end is one displayed
  frame longer at 16:9.  Not the look controls.  `test/r3/wide/`.  Told to the coordinator.
- `fire3`'s grid of dark squares in the sky is the level's own geometry (the stand-alone program draws it too).
- Foreground `sleep` does nothing in this agent's shell: waits are `python3 -c "import time; time.sleep(N)"`.

**Not done**
- **Persistent meshes** (the tap's object-space vertices, joints and matrices through the C interface): not
  started.  By the figures above it would take at most the 3 ms of `submit()` and part of Godot's own upload.
- **The sun's direction from the level** is read (see "The look"), but only the first level's textures say it
  clearly; the others take the first level's.  Not checked against the painted shadows level by level.
- **Lights at torches**: none; a dark level gets one warm lamp carried by the player.  The game's own point
  lights are already in the vertex colours it computes.
- **Water, lava, heat haze**: looked at only as far as the pictures of islsm1 and fire3 go (they look as in the
  stand-alone program).  A surface read in the middle of its own draws (the haze) still gets last frame's picture.
- **The character alone for the portal's card** (`Portrait.texture`): not built.  The game behind the portal,
  blurred: works through the portal's own backdrop once a game has run (`join-3`, `join-4`); the title scene
  behind the portal before the first game: not built (the machine is not started before "Play").
- A restart of the program for a new game after the machine has ENDED (one machine per process).
- The pointer look, a real controller, sound: nobody has played it.
- The rig comparison and the reference pictures on the new libraries (see above).

### How to run a test here

```
. local/godot-spike/test/env.sh
R3_SHOTS=ac local/godot-spike/test/r3/go.sh NAME VIEW "hub valor ..." [main.gd options, e.g. --look sky=off]
#   -> local/godot-spike/test/r3/NAME/LEVEL-VIEW-[a-d].png (Godot's own capture), out-VIEW.txt, figures-VIEW.txt
#   R3_PRE="app look fog off;app option music_volume 0.5"   host lines after the view is selected
#   R3_DESCRIBE=1    LEVEL-VIEW-a.txt: every draw of that frame that goes to the 3-D surface (state, screen box,
#                    distance and elevation from the eye) - RtaDrawer.describe_frame, the way the dome was found
#   R3_HUD=--no-hud  without the new HUD
```
The route is the camera agent's (`native-first-person.md`, `mktour.py`): power-on by the tick-keyed script, each
level by its name written to `g_pendingLevel`, pictures at fixed ticks (a standing, b after 90 ticks of stick up,
c after 45 of camera stick right, d after 90 more).  Not paced, 1280 x 896, a 480 x 360 test window.

### The look (`project/scene_view.gd`, `shaders/atmosphere.gdshaderinc`, `shaders/sky.gdshader`, `extension/src/rta_scene.cpp`)

Switches, each `off | on | auto` (auto = only in chase, shoulder, first person - never in the game's own overhead
view, never while the game's camera has the frame: there the picture is the game's as it was): `sky`, `fog`, `sun`,
`lamp`, `bloom`, `grade`; `aa` = 0 / 2 / 4 / 8.  `--look sky=on,fog=off,...`, `app look KEY VALUE`, `app look info`,
`main.apply_settings({"look": ...})`.  More keys at the head of `scene_view.gd`.

- **What the game draws of a sky** (found with `describe_frame`): the first draw into the 3-D surface is a
  rectangle over all of it in the clear colour (untextured, depth test "always", writes depth); in a level with a
  dome, model packets without a depth write follow, before the first level chunk (hub: 7 draws, 48 packets, rings
  at -70..-43, -43..-12, -12..+18 degrees, radius 275 to 372).  Only the segments in view are drawn.
- **The drawer learns the dome** (`scene_scan_sky`): the clear colour from the rectangle; the dome's draws by that
  rule; the dome's upper and lower edge as 256 directions of colour each - the packet's own texture sampled along
  the edge's triangles through the draw's texture function and blend over the clear colour (the texture's pixels
  from the frame that brings it, or read back once).  `RtaDrawer.get_sky_info()`; `sky_reset()` on a new level.
- **The sky** is a sphere round the camera drawn before every draw of the list (an instance in the drawer's
  scenario with a sorting offset of -1,000,000; `sky.gdshader`): the ring of edge colours at the dome's upper edge,
  rising to a zenith colour (the ring's mean, deeper); below the lower edge the lower ring to a ground colour.  The
  game's own dome is still drawn, over it - the sky continues it, so the seam has the same colour on both sides.
  With the sky on, the game's clearing rectangle is left out (it would cover the sky).  **A level without a dome**:
  horizon, zenith and ground are made from the clear colour (brightest channel under 0.09: "dark" - black above
  with a breath of colour at the horizon; else "open" - paler at the horizon, deeper overhead, a glow round the
  sun's direction).  Nothing per level is written down: all of it is read from the frame's draws at run time.
- **The haze** is in the draw shader (`gs_draw.gdshaderinc`, `GS_WORLD`): by distance from the eye (starts at 380,
  complete at 1350 or 0.78 of the level's far plane - the game streams 1300 to 1800 ahead), thinner above the
  player's height, always complete over the last tenth; its colour is the sky ring's in that direction.  An
  additive draw only fades; an opaque one becomes haze.  The dome's draws are not hazed (`GS_NOFOG`).  Global shader
  parameters `rta_*`, set once per frame.
- **Light**: Godot's ambient light is off in the lit variant (`ambient_light_disabled`); what arrives without the
  sun is put in by the shader as the surface's own light - the game's colour times `rta_light_ambient`, plus the
  haze - which is exact in stored values; the sun's pass adds the rest (energy `(1 - shade)^2.2`, the measured
  rule of the second round).  A shadow keeps `shade` of the colour (0.64; 0.84 / 0.90 in dark levels) with 30 % of
  the sky's tint; the sun's colour is what brings a lit, facing surface back to the game's own colour.  Only what
  writes depth is lit (glows, the dome, decals keep the game's colours).  In a dark level the "sun" stands at 82
  degrees (a soft shadow under things) and a warm lamp is carried by the player.
- **Where the sun stands** is read out of the level (Ran): the game's light is painted into its textures, so per
  texture the drawer takes the covariance of texel brightness (a 16 x 16 thumbnail of every texture, made when it
  arrives) with the normals of the level-chunk vertices that carry it, and sums that over the level
  (`Scene::sun_sum`, `get_sky_info().sun`): a vector toward the light whose length says how clearly the textures
  agree.  Taken from 30,000 vertices on, kept at 150,000.  Found: hub azimuth -33 degrees, strength 0.0121 -
  which is where the game's own sun flare stands in that level (`sun1/hub-shoulder-d-w.png`: the flare ahead, the
  character back-lit); tormenta azimuth -75, strength 0.0159; valor 0.0011 (azimuth -31), fire3 0.0010, islsm1
  0.0026 (azimuth -43), the title scene 0.0013 - below the bar of 0.004, so those levels take the last clear
  direction (that of the level played before) instead of an own one.  Elevation is held between 38
  and 62 degrees (the textures say little about it).  `sun_az` / `sun_el` of the look override.
- **Sprites that are depth-tested** (particles, glows, sparks: `made_by` 2 with depth test "greater or equal") were
  the 2-D layer, drawn over everything; the library now puts them into the world by their 16-bit depth
  (`lib/scene_export.cpp`; `RTA_SCENE_SPRITES=0` turns it off) so Godot's depth hides them behind what is in front,
  and they fade between 75 and 18 units from the eye (`GS_NEARFADE`) - the game sizes them for a camera 400 away
  and one at the eye covers the picture.

### The portal's joins (`project/main.gd`; Ran: `project/dev/join_test.gd`)

- `signal session_over(why)`: "frontend" when `g_inFrontend` becomes 1 after a level was played, "ended" when the
  machine ends.  Under the portal (the scene's ancestor in group "portal", not "passing") the portal is told
  (`handover.finish("over")`) and **the program is not ended**; a script run still ends as before.  The machine
  is one run per process: after "ended" a new game needs a restart of the program (not built).
- `hold_input(on)`: the controller is neutral while the portal is in front (`portal.shown_changed`).
- `apply_settings(d)`: `view`, `wide` (library option `aspect`, new; the 3-D surface's viewport follows),
  `sharpness` (`RtaDrawer.set_output_size`), `music` / `effects` (`music_volume` against the player's volume),
  `look`.  The portal's stored settings are looked at twice a second (`_portal_settings`) and applied when they
  change, so nothing in `portal/` had to be touched.  Test aids: `app hold on|off`, `app setting KEY VALUE`.
- The HUD's one line is in `_ready` (`--no-hud` leaves it out).

### For the HUD

| Asked | Done |
|---|---|
| `RtaMachine.get_controls_hud()` | the fields of `fpcontrols::Hud` under their own names, plus `wants_pointer`; `{}` when the library has no controls.  C side: `rtag_controls_hud`, `rtag_mouse`, `rtag_mouse_button` - **optional symbols, the interface version stays 6** |
| the camera in `rtag_view` in the overhead view | filled from `g_cameraPos` / `g_cameraMatrix` / `g_projScale` when no view of `fpview` is in place (`rtag.cpp`, `view_drawn`) |
| `set_option("music_volume", "0..1")` | in `rtag.cpp` when the snapshot's `sound/drivers.cpp` has `rta_sound_set_music_gain` (the HUD agent's hunk: in `recomp.patch`) |
| `set_option("game_hud_text", "off")` | `render/layout.h` `M_TEXT`, `Gs::hide_text`, two wrappers in `app/gfx_rt.cpp`: in `recomp.patch`; **needs two lines in `tools/recomp/hle.txt` and a new translation first** (the notes at the head of `recomp.patch` say exactly what and in which order) |

### Files outside `tools/godot` that need a change (for the coordinator)

- `tools/recomp/hle.txt`: `1d93b0`, `1d99f0` (then translate and compile the game again), **before**
- `tools/godot/recomp.patch` onto `tools/recomp` (`app/gfx_rt.cpp`, `render/gs.cpp`, `gs.h`, `layout.h`,
  `sound/drivers.cpp`; `sound/audio_out.cpp` as before).

## SECOND ROUND (2026-10-13, from 09:30): Godot as the presentation layer

The coordinator's brief after the spike: Godot becomes the presentation layer on the
translated core. Tasks, in its order: (1) a real 3-D hand-over from the vertex programs'
inputs, (2) scene mode everywhere, (3) 60 pictures a second with proper lighting, (4)
cleaner models, (5) plug-in points for the camera, world and HUD agents, (6) exports.
**Kept current here; newest state first.**

### State (14:20)

- **The scene's geometry is the packets' own, complete (Ran).** For every mesh packet the
  tap now also hands over EVERY triangle of its strip (`TapPiece::full_first`,
  `rtag_scene::full`: world position, normal, texel coordinate and the colour the
  program computed, three corners a triangle), with the strip's own no-draw bits
  replayed from the slot rows - not the program's, which also carry its clip pass. Scene
  mode draws that (`set_scene_option("packets", 0)` goes back to the list's triangles).
  Checked: the replayed no-draw bits against the program's for objects without the clip
  flag: 63,111,105 strip vertices compared, **0 different**; 9.7 million triangles the
  clip pass had dropped are back over the views route (about 2,650 a list in the first
  level); over the shoulder and in first person the floor reaches the bottom of the
  picture (`test/views-godot/g-shoulder-sun.png`). **So scene mode is now immune to
  both of the world agent's faults** (dropped triangles near the eye: Godot clips them;
  texturing: with perspective) - Ran in the first level's four views, not yet looked at
  in a level with walls.
- The extension's CMake takes two modules of other agents when their sources exist:
  `RtaGameState` (HUD: `src/rta_gamestate.*`, `tools/recomp/app/gamestate.*`) and
  `RtaNet2` (portal: `src/rta_net2.*`, `tools/recomp/net2/session*.cpp`, compiled with
  `NET2_NO_SERVICE`: no socket code in the extension). A source file dropped into
  `extension/src/` is compiled by the glob: one that needs a new include path breaks the
  build until `CMakeLists.txt` knows it (it did twice today).
- A test run that cannot start (no library, version mismatch, no disc) now ends with
  exit code 2 instead of waiting with a message (two runs hung on a stale extension).
- Speed: **not measured in this round** - the load average was 120 to 200 the whole
  afternoon (other agents' builds); the unpaced figures in the logs (23 to 62 pictures a
  second) say nothing. **The macOS export was re-run on the rebased library (Ran,
  14:25)**: `build.py extension --release && build.py export`, the exported application
  started without a window with `--view chase`, its two pictures identical to the
  library's.
  `local/godot-spike/src.before-fp/` is the snapshot as it was before the rebase.

- **(1) The tap at the vertex programs' inputs: done and verified (Ran).** Section
  "The scene tap" below. The 16-bit-depth route of stage 4 is now only the fallback for
  what the mesh programs do not draw.
- Scene mode uses it: exact positions, the game's own normals (smooth, per pixel), one
  shadow per character (the game's blob shadows are left out when Godot casts).
- **(5) The camera agent's views through the library: done (Ran).** The snapshot is
  rebased on a root with `app/fpview.patch` applied and built (`build.py snapshot
  --refresh --from local/recomp-fp/root`); `rtag_config::view`, `rtag_set_option("view",
  NAME)` and `("view.<mode>.<name>", VALUE)`; script line `app view NAME`; in Godot
  `--view NAME`, the V key, `RtaMachine.set_option`. The look inputs are the
  controller's own (the right stick through `rtag_set_pad`): `fpview` reads the game's
  camera stick. **The scene simply follows**: the camera block the tap gets is taken in
  `fpview`'s `on_drawn` call-out, while the view's camera is still in place (the game puts
  its own back right after), with the view's near and far plane; the tap's check passes
  in every view (72,320 of 72,320 level set-ups bit for bit, 0 vertices off through
  action, chase, shoulder and first person).
- **(5) The view of the frame, for the HUD agent: done (Ran).** `rtag_frame::view`
  (`rtag_view`: laid out as `rta_gs_view` of `app/gamestate.h` up to `yaw`, then near /
  far, player position, facing, look pitch, tick) - the view of the draw pass that built
  the frame's list, carried with the frame; `RtaMachine.get_view() -> Dictionary`.
  The HUD agent's `RtaGameState` (its `extension/src/rta_gamestate.*`) is compiled into
  the extension and registered (`CMakeLists.txt` names `tools/recomp/app` for
  `gamestate.h`).
- **(5) The switch for the game's own HUD layer: done (Ran).** `rtag_set_option(
  "game_hud", "off")`, `app gamehud off|on`, `--no-game-hud`. Patch lines for the core
  (in `recomp.patch`, with the reasons): `gfxrt::set_hud_marks` (marks also at 4:3; and a
  tag outside the display list resets the mark, or the present pass went on under the
  HUD's mark and the picture was black), `Gs::hide_edge` (in `rebuild_state`: what is
  marked `M_EDGE`, drawn into the 3-D buffer without a depth test, is skipped - not in
  `Layout::primitive`, which is not called at 4:3). Picture:
  `local/godot-spike/test/hud/no-game-hud.png`; first person without the game's HUD,
  drawn by Godot with its sun: `test/views-godot/g-first-sun-lamp.png`.
- Regression on the rebased library (Ran): 11 of 11 pictures identical to `rta_app`'s;
  the rig's session comparison the same file as before.
- **Open, in order**: sky and atmosphere per level (the world agent's catalogue,
  `native-first-person-world.md` sections 4 and 6: mine); geometry from the tap's packets
  instead of the list's triangles (persistent meshes per identity, re-posed; this is
  also what makes the scene immune to the triangles the programs drop near the eye);
  60 pictures a second paced; lighting, fog, bloom, anti-aliasing as switches; the art
  pack and model clean-up; `worldfill.h` meshes when they exist; the Windows
  preparation (nothing of it is started: the DLL through `build_win.py`'s route and the
  extension cross-built with MinGW, as stage 5 describes it).

**For the world agent - is the scene immune to its two faults?** (Read, from how the
scene is built; not looked at in a close view.)
- *Texturing without perspective*: **immune** in scene mode. The mesh is in world space
  and Godot interpolates the texel position with perspective (stage 4, the difference
  against draw mode). Draw mode and picture mode show the game's own mapping.
- *Whole triangles dropped near the eye*: **not immune yet.** The scene's triangles are
  the draw list's - what the program kicked with the no-draw bit clear - with exact
  world positions attached; a triangle the program's clip pass dropped never reaches
  the list. The tap HAS the whole packet (every vertex and the slot rows, whose own
  no-draw bits are the strip's stitching, not the clip pass), so building the scene's
  geometry from the packets instead of from the list restores every dropped triangle
  and lets Godot clip them properly; that is the same step as the persistent meshes of
  task 3 and is the next piece of work here.

### The scene tap (Ran)

New files, **proposed for `tools/recomp/render/`** and kept under
`tools/godot/core/render/` until that directory's owner takes them (`build.py lib`
copies them into the snapshot): `scene_tap.h`, `scene_tap.cpp` - renderer-independent,
no graphics calls. Hooks, in `tools/godot/recomp.patch` (7 lines in `render/vif1.h` /
`vif1.cpp`): `Vif1::on_program` (called before a microprogram runs), and NOP notes with
NUM 0xA8 / 0xA9 handed to the tap; the kick is wrapped by `SceneTap::install()` without
a source change. Both ways of running the programs call the same `Vu1::kick`, so the
interpreter and the translation feed it alike.

What it hands over for every mesh packet the four mesh programs kick (entries 0x42 /
0x44 models, 0x46 / 0x48 level chunks - `render-pipeline.md` 4.4; packet layout from
`docs/formats/model-texture.md`):

| | From |
|---|---|
| object-space positions (stored 16-bit / 16) | the input half of the VIF double buffer, at `TOP`, `ITOP` vertices |
| **normals** (stored 8-bit, both for models and level chunks: the programs light per vertex with them) | the block after the positions |
| up to four joints and weights per vertex (models) | the weight entries, walked as the program walks them |
| the matrices: the four rows of the set-up (level: entry 0x16; mirrored copy: 0x3c) or the 64 joint matrices in VU1 memory (models, after 0x0c / 0x1e / 0x1a) - object to the game's clip space | read when the set-up entry starts / when the packet is kicked |
| which vertex became which vertex of the draw list | the strip is replayed from the packet's slot rows and copy rows; the GS model emits three list vertices per drawn triangle in strip order |
| an identity: a figure over the packet's own bytes (stable from frame to frame), its occurrence number in the frame, and a number per set-up (one draw of one object) | |
| world position and world normal | clip space back through the inverse of the game's view-projection (`g_viewProjModel`; for the level `g_viewProjWorld`, whose space is world / 4) |

**The camera travels with the packets.** The library's sink puts the 62 words at
0x44f108 (`g_projScale`, `g_cameraMatrix`, the three view-projection matrices) in front of
the first VIF1 transfer after each vertical blank, as notes in the stream; the decoder
has the camera the packets were made with on whatever thread it runs. This replaces the
"one blank earlier" guess of stage 4.

**It checks itself.** A packet is handed on only if the tap's own projection of its
reconstruction lands where the program itself put the vertices in the strip. Figures
(the whole route - power-on, title, first level, `valor`, a fight; 5,308 lists):

| | |
|---|---|
| mesh packets kicked / handed on | 3,990,182 / 3,867,623 (the rest draw no triangle) |
| left out: list did not grow as kicked / not where the program put them / not laid out as documented | 0 / 0 / 0 |
| vertices compared with the programs' own positions | 211,857,142; **0 off**; largest difference 1.65 of 1/16 pixel |
| level set-ups whose depth and translation rows are the noted camera's, bit for bit | **176,778 of 176,778** |
| level vertices on the quarter-unit grid the files store them on (first level) | **99.75 %** (14.3 % with the depth route) |
| the same route to the first level with every program interpreted (`RTA_VU1_INTERPRET=1`) | the same counts, 0 off |
| the 11 fixed-tick pictures with the tap on | identical to `rta_app`'s (the tap changes nothing the renderer computes) |
| per list in the first level | 185 draws / 92,700 vertices from the inputs with normals; under one draw by its depth (the game's ground-shadow quads) |
| kicks of other programs (particles, water, trails, shadow sprites) | 163,146: not tapped; triangles among them go by their depth as before |

Through the C interface (`rtag.h`, version 4): `rtag_scene::normals` (three per list
vertex), `rtag_scene::pieces` (identity, occurrence, object number, kind, flags, list
range), `rtag_draw::scene_kind` (from the inputs / by depth). The tap's own frame
(`TapFrame`: object-space vertices, joints and weights, the matrices) is not exported
through C yet: it is what persistent, re-posed Godot meshes will be built from (task 3).

Not tapped, and why it matters: a shell pass (weapon glow: the mesh again, pushed out
along a second set of normals) would fail the tap's check and go by its depth - **none
occurred in the routes run, so this is Read**; water (0x36 / 0x38), particles, trails
and decals have their own input formats (`render-pipeline.md` 4.8 to 4.11) and no tap.

## From nothing

```
export RTA_DISC="/path/to/your/disc image.iso"
python3 tools/recomp/app/build.py && python3 tools/recomp/app/build.py --original   # the translated game (objects)
python3 tools/godot/build.py all            # snapshot, library, extension, staged project
python3 tools/godot/build.py lib --original # the unpatched game as a library (for the rig comparison)
python3 tools/godot/run.py import           # once: Godot's import cache (bounded headless editor start)
python3 tools/godot/run.py -- --disc "$RTA_DISC"                 # the game in a Godot window (picture mode)
python3 tools/godot/run.py -- --disc "$RTA_DISC" --mode draw     # Godot draws the frame itself
```

`run.py` starts the Godot under `local/godot-spike/deps` on the staged project
`local/godot-spike/project` (a copy of `tools/godot/project` with `bin/` beside it:
Godot's import cache and `.uid` files stay out of the repository) and points Godot's own
directories at `local/godot-spike/godot-home` (`XDG_*_HOME`, which Godot honours on
macOS): nothing is written to `~/Library`. The options after `--` are at the head of
`tools/godot/project/main.gd`. **The first import**: Godot 4.5.2 can crash when it shuts
down after its first import (godotengine/godot#111645); `run.py import` is the bounded
editor start open-champions-godot uses (`--headless --editor --quit-after 120
--frame-delay 50`) and ended normally here (Ran).

Downloads the Godot side needs (the owner agreed to exactly these; each in its own
directory under `local/godot-spike/deps/`):

| What | From | Size | Check |
|---|---|---|---|
| `godot-editor/Godot_v4.5.2-stable_macos.universal.zip` (Godot 4.5.2 standard editor) | `github.com/godotengine/godot/releases/download/4.5.2-stable/` | 162,276,911 bytes | SHA-512 `0b309feb…2b5d7c0` = the release's `SHA512-SUMS.txt` = the pin in open-champions-godot's CI (checked before it was unpacked or run) |
| `godot-cpp/src` (godot-cpp, Godot 4.5 API) | `github.com/godotengine/godot-cpp`, commit `e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77` fetched by its hash (`git fetch --depth 1 origin <hash>`) | 9.3 MB | `git rev-parse HEAD` = the pin; the extension's CMake refuses any other commit |

| `godot-templates/Godot_v4.5.2-stable_export_templates.tpz` (export templates, for stage 5) | the same release | 1,353,063,159 bytes | SHA-512 `003aa337…3fcfab6c` = the release's `SHA512-SUMS.txt`; only `templates/macos.zip` (126,967,457 bytes) and `version.txt` are unpacked |

Same pins as `open-champions-godot/gdextension/dependencies.json` (copied as
`tools/godot/extension/dependencies.json`). No Homebrew install, nothing else fetched:
godot-cpp is built with the CMake (4.4.4) and Ninja already on the machine, SCons is not
needed.

## Stage 1: the game as a library (Ran)

`python3 tools/godot/build.py snapshot` copies `tools/recomp/{rt,render,sound,app}` and
the compiled translated game (`local/recomp-out/obj-rta_native_fix`, `obj-run`, the VU1
translations of `gen-vu`) into `local/godot-spike/src/` and applies
`tools/godot/recomp.patch`; `build.py lib` compiles that copy with the files of
`tools/godot/lib/` into a dynamic library. `tools/recomp/` itself is not touched (another
agent owns it and changes it meanwhile; `build.py snapshot --refresh` takes it again as
it is then).

What is in the library: the runtime (`rt/runtime.cpp`, `iop.cpp`, `script.cpp`), the
translated game, the renderer's processor side (VIF1, VU1 with both translations, the GS
model, `renderer.cpp`), the OpenGL backend (`backend_gl.cpp`, optional at run time), the
sound core (`sound_rta.cpp`), the game-side picture hooks (`app/gfx_rt.cpp`), the films
(`app/film.cpp`, fix-set library only), the picture path of the application
(`app/pipeline.h`: the sink that copies on the game's thread and the decoder thread).
**Not in it: the network** (`tools/recomp/net`). The translation leaves the network
library's entries open with weak defaults that are the original code, so the game links
and plays offline exactly as before, and nothing in the library can open a socket.

What `tools/godot/lib/` adds (all written for this spike, nothing derived from the game):

| File | Does |
|---|---|
| `rtag.h` | the C interface: `rtag_start` (disc path, data directory, picture and sound options, more runtime arguments), `rtag_step` / `rtag_poll` / `rtag_run` (one vertical blank at a time, or on the library's own clock), `rtag_set_pad`, `rtag_audio_pull` (48 kHz stereo), the frame (`rtag_frame`: draw list with every draw's complete state, new textures and surfaces, optionally the picture as RGBA, the pictures a script asked for), `rtag_memory`, `rtag_info`, `rtag_stop` |
| `rtag.cpp` | the hand-over: the game's thread stands at every blank until it is let go; finished lists wait in a queue of three for the host; the library's own renderer (when a picture size is given) runs on the decoder's thread in a context without a window and writes `app shot` pictures itself |
| `host_godot.cpp` | `rt/host.h` for a machine inside another program: `quit()` does not end the process - the library reports the end and the game's thread stands still for good |
| `audio_host.inc` | the "sound device": the host asks for the sound. Included by `sound/audio_out.cpp` (the one change of `recomp.patch`) |
| `gl_standin/QOpenGLContext`, `QOpenGLExtraFunctions` | Qt's two classes that `backend_gl.cpp` is written against, forwarding to macOS's OpenGL framework (the Windows build does the same over WGL: `app/win/wgl.h`). `backend_gl.cpp` is compiled unchanged, without Qt |
| `gl_offscreen.h`, `gl_offscreen_mac.cpp` | an OpenGL 4.1 core context with no window (CGL) |
| `png_write.h` | pictures as PNG with the system's zlib |
| `scene_tap.h/.cpp` | stage 4 |
| `host_main.cpp` | `rtag_host`: the smallest host - loads the library with `dlopen`, runs scripts, takes frames; exit code is the runtime's |

`recomp.patch` (16 lines): `sound/audio_out.cpp` includes the file named by
`RTA_AUDIO_HOST` in place of its own devices. Everything else needed no change:
`rt/host.h` already is the boundary for ending a run, the picture sink and the pad source
are `rta::Hooks`, `texpack.cpp` has `RTA_NO_QIMAGE`.

Limits of the library as it is: **one machine per process and one run per machine** (the
translated game keeps its state in globals; `rtag_start` after `rtag_stop` is refused);
arm64 macOS only (the Windows sources exist, see stage 5); exported symbols are the
fourteen `rtag_*` functions and nothing else.

### Proof (Ran, 2026-10-13 morning; machine shared, load average 6 to 23)

`local/godot-spike/test/` (scripts written for this; results beside them):

| Check | Result |
|---|---|
| power-on, 409 blanks, two pictures (`smoke/`) | card screens drawn; 0.33 s |
| **pictures at fixed ticks** (`det/`: the tick-keyed route of `app-test/s11/mkdet.py` - power-on, title, first level, change to `valor`, a fight; 5,309 blanks; 11 pictures at 1280 x 896, plain picture) through `rtag_host` and through `local/recomp-out/bin/rta_app --offscreen --unpaced --plain` | **11 of 11 identical, pixel for pixel** (`test/piccmp.py`, decoded pixels; the PNG files differ because the encoders do) |
| **the rig's session comparison** (`test/rig.sh lib`: `rigcompare.py boot-native --script fight3.rig --replay` with `rtag_host --lib librta_game_orig.dylib` standing in for the headless build, then `boot-compare`; 7,904 fields) | **the same file as `app-test/merge/rig-final-compare.txt`, byte for byte** (`cmp`): the result the native application has - front end, first level, 5,410 ticks of `valor` - reproduced through the library |
| speed of that route, not paced, 1280 x 896 | library: 317 pictures a second, 3.97 ms of processor time a picture over all threads (decoder with OpenGL 2.65 ms); `rta_app` in the same minutes: 337 a second, 5.16 ms |

## Stage 2: in a Godot window (Ran)

`tools/godot/extension/` is a GDExtension (CMake, the layout and options of
`open-champions-godot/gdextension`; built against the pinned godot-cpp with
`build.py extension`, about three minutes the first time for the bindings). **It holds no
game code and does not link the game library**: `RtaMachine.load_library(path)` loads it
at run time (`dlopen`; `LoadLibrary` is written for Windows) and takes the fourteen
functions by name.

| Class | Does |
|---|---|
| `RtaMachine` (`rta_machine.cpp`) | `load_library`, `start(config)`, `set_pad`, `step(wait_ms)` / `poll` / `run`, the frame last taken (`get_picture()` as an `Image`, `get_shots()`, `get_host_commands()`), `peek_*` into the machine's memory, `stop` |
| `RtaAudioStream`, `RtaAudioPlayback` (`rta_audio.cpp`) | an `AudioStream` whose playback (`AudioStreamPlaybackResampled`, 48 kHz) calls `rtag_audio_pull` when Godot's mixer asks: the game's sound side runs on Godot's audio thread and clock, by itself, as the console's sound processor does (`sound-clock=real`), and Godot's buses and volume apply |
| `RtaDrawer` (`rta_drawer.cpp`) | stage 3 |

`tools/godot/project/` (scripts only): `main.gd` is the host - options, window, pacing
(one step per 1/60 s, held to the display when its rate is a multiple of 60), keyboard
and controller polled through Godot's `Input` once per picture (the native application's
key map; first joypad Godot knows), the sound player, pictures; `view.gd` shows the
picture letterboxed to the frame's shape. Script lines `app key down|up NAME` and `app
gcpad ...` become `InputEventKey` / `InputEventJoypad*` sent through
`Input.parse_input_event`, so a script exercises Godot's own input path; `app windowshot
FILE` writes the root viewport (what is in the window).

Proof (Ran; test windows 480 x 360 points titled "AGENT TEST - ...", without focus, in the
screen's corner, sound muted):

| Check | Result |
|---|---|
| power-on in a Godot window, paced (`test/g-win`) | 429 pictures in 7.25 s (59.2 a second with start-up); the window's own picture (`g-win/b-window.png`, the root viewport) shows the card screen; Godot's mixer asked for 7.26 s of sound in 2,721 requests, longest time between two requests of the sound side 10.7 ms, none late |
| **keyboard through Godot's input** (`test/g-keys`: `app-test/keyboard-play.rig`, 110 key events and nothing else) | power-on, card screens, title, menus, character creation, first level; W for 60 frames moved the character by (-102.4, +116.0) (the native application's own run of this script: (-102.5, +116.0)), D and S+A moved it on, K put it into its strike state, Return opened and closed the pause menu; `g-keys/k2-pause-window.png` is the Godot window with the pause menu over the first level |
| **the rig's session comparison through Godot** (`test/rig.sh godot`: Godot headless, the extension, `librta_game_orig.dylib`, 7,904 fields) | the same file as `app-test/merge/rig-final-compare.txt`, byte for byte |
| **pictures at fixed ticks** in a Godot window (`test/det/godot-picture`, picture mode, 1280 x 896) against `rta_app`'s | 11 of 11 identical, pixel for pixel |

Found on the way: Godot buffers input events until its next frame
(`Input.use_accumulated_input`), so a script's key was pressed and released between two
of the machine's blanks without being seen; the host flushes after each
(`Input.flush_buffered_events()`). A real key press arrives with Godot's own event
processing before `_process` and needs nothing.

Not done in stage 2: a real controller was not attached (the mapping is exercised by
`app gcpad` only as far as Godot's `Input` goes; not run yet); rumble is counted, not
sent; nobody listened to the sound (tests are muted) - that it is pulled at the right
rate is what the figures say.

## Stage 3: Godot draws (Ran)

How (`rta_drawer.h` has the full account):

- **A surface is a viewport** with a scenario, a camera and an environment of its own
  (`ENV_BG_KEEP`, clear mode "never": the GS never clears, the game does). A small
  surface that is drawn, read and drawn again within one frame - the ground shadows: up
  to eight passes a frame in `valor` - gets one viewport per pass.
- **A draw is a mesh instance.** Meshes are rebuilt every frame from the list's vertices
  through `mesh_add_surface` with raw buffers (position; colour as four bytes; texture
  coordinates s, t, q and fog as a float custom channel - no conversion through Godot's
  packed arrays, the bytes are the GS's).
- **One shader** (`gs_draw.gdshaderinc`), a line-for-line port of the OpenGL backend's
  fragment shader: texture functions (modulate with 0x80 = 1.0, decal, highlight),
  `TEXA`, the weave of two-field interface art, region wraps, fog, the alpha test, the
  scissor (as a discard), and the blend. Its variants (defines): blend equation, depth
  test, depth write, texture filter, repeat. One material per distinct state, kept
  between frames (211 alive at a time in `valor`).
- **Blend**: `(A - B) x C + D` is `source x |sc F + sk| +/- destination x |dc F + dk|`;
  everything with a plus is Godot's `blend_premul_alpha` with `ALPHA = 1 - destination
  factor` (opaque draws included), destination minus source is `blend_sub`. The only form
  this cannot do is source minus destination (counted; none in the sessions run).
- **Order.** The GS draws in the order it is told. Every material is drawn in Godot's
  transparent pass, and each instance's sorting offset (`instance_set_pivot_data`) makes
  that pass keep the list's order; depth test and depth write are the draw's own
  (`depth_draw_always` / `never`, `depth_test_disabled`).
- **"Depth test always, and write"** (every 2-D draw of this game) is not a mode Godot
  has: such a draw is submitted twice, once with the default test and once with
  `depth_test_inverted` (new in 4.5) - exactly one of the two passes at every pixel.
- **Order of surfaces.** The viewports are children of the window's viewport (rendered
  before it) and are deactivated and activated again every frame in the order the list
  needs (a surface after what it reads; the present pass, which opens a list and reads
  the 3-D surface as the frame before left it, before that surface's new draws).
- **The picture**: the viewport of the surface the display circuit reads, drawn into the
  window by `view.gd`.

Three things about Godot 4.5.2's Compatibility renderer that were found by trying and
that the drawer depends on (`test/gamma/` is the probe for the third):

1. `RenderingServer.shader_set_code` does not run the shader preprocessor; a `Shader`
   resource's `set_code` does. `shader_type` must be the first statement, before defines.
2. A position a spatial shader writes itself (`POSITION`) has y down in the viewport's
   picture, as the list's positions have; a viewport's texture reads with v down.
3. **`ALBEDO` is taken for an sRGB colour**: the renderer converts it to linear light and
   back when it writes the pixel, each way with a fast approximation, and the round trip
   lowers dark values (10 of 255 comes back as 4, 42 as 40). The shader puts in the
   colour whose round trip is the wanted one (`to_linear`: one exact inverse, three
   Newton steps). Blending then happens on the stored values, as on the GS.

**Compared with stage 2** (`test/det/godot-draw`: the tick-keyed route, Godot's capture
of the shown surface's viewport at each of the 11 ticks, 1280 x 896, against the
library's own OpenGL picture of the same tick; `test/piccmp.py`):

| Picture | Pixels that differ at all | Largest difference (of 255) | Mean |
|---|---|---|---|
| title | 61 % | 2 | 0.28 |
| first level (hub) | 69 % | 2 | 0.33 |
| `valor`, nine pictures (cutscene, play, fight) | 71 to 73 % | 2 to 3 | 0.34 to 0.36 |

No picture has a pixel that differs by more than 3. What the differences are (Read, from
the way they are spread - nearly every pixel, by one): the rounding of the colour round
trip above (float to 8 bits twice), and the present pass, which reads the 3-D surface
with the game's bilinear filter from a viewport texture. Nothing is missing or misplaced:
ground shadows, alpha-tested foliage, the HUD and its bars, text.

Differences in kind, known and counted by the drawer (`figures()`), none of which showed
in these sessions:

- **A surface read in the middle of its own draws** (the heat haze of the fire levels:
  a piece of the 3-D surface is copied out and drawn back distorted) gets the picture of
  the frame before, HUD included: one viewport renders once a frame. 7 such reads in
  5,309 lists here (level changes). Not looked at in a fire level.
- The alpha the GS writes into a surface is not kept (Godot writes the blend's own); a
  draw that reads a surface's alpha (`TEXA` modes take theirs from the register) would
  differ. Depth test "greater" is drawn as "greater or equal".
- Multisampling, mip maps, anisotropy and the art pack of the native application are not
  wired here (`--samples` sets Godot's MSAA on the 3-D surface's viewport: not compared).

**Processor time** (the same route, not paced, 1280 x 896, plain picture, load average
about 10, Apple M5 Pro; all threads of the process):

| | Pictures a second | ms of processor time a picture | Where |
|---|---|---|---|
| `rta_app --offscreen --plain` | 337 | 5.16 | decoder 1.66, OpenGL thread 2.0 |
| the library with its own renderer (`rtag_host`) | 317 | 3.97 | decoder with OpenGL 2.65 |
| Godot, picture mode (window) | 259 | 5.50 | decoder with OpenGL 3.5; read-back and texture upload every picture |
| **Godot draws** (window) | **75** | **15.6** | decoder 1.73; `submit()` 5.4 ms on Godot's main thread (236 draws and 91,000 vertices a list: a mesh, an instance and a material lookup per draw, 43 draws a list doubled for the depth rule); the rest is Godot rendering 4 viewports a frame |

So Godot's own drawing of the unchanged list costs about three times the native
application's whole picture path, and still leaves room at 60 pictures a second on this
machine (13.4 ms a picture of wall time, not paced). Where it would be made cheaper
(not done): one mesh per frame with a surface per draw instead of one mesh per draw;
not doubling 2-D draws nothing tests depth against; keeping the instances' sort keys.

Paced, in a test window of 640 x 480 points, the whole session from power-on with 560
blanks in the first level (`test/paced`; **the machine was not free: load average 45,
192 over five minutes** - another agent's builds): draw mode 52 pictures a second, scene
mode 54, scene mode with sun and lamp 43; sound asked for without a gap (longest time
between two requests 10.7 ms, none late) in all three. On a quieter machine the same
modes ran not paced at 61 to 76 a second, so 60 is within reach but **was not shown
paced**; with the sun on (four shadow splits, every opaque draw drawn into them) it is
the tightest.

## Stage 4: the scene in 3-D (Ran, on the first level)

The draw list is already projected. To let Godot light the scene or look at it from
somewhere else, every vertex has to be where it was in the world.

**How the world position is got** (`tools/godot/lib/scene_tap.cpp`, `rtag_scene` in
`rtag.h`). Not by decoding the vertex programs' inputs, but by turning the game's
projection round per vertex. The programs compute, for a camera-space point (x right, y
down, z forward; `docs/spec/render-pipeline.md` section 3):

```
sx = F k x / z        sy = F 0.4666667 y / z      pixels of the 1280 x 448 buffer from its centre
zb = 16 (A + B / z)                               the 16-bit depth, larger = nearer
```

with `F` = `g_projScale` (0x44f108), `k` the widescreen factor, and the world-to-camera
matrix `g_cameraMatrix` (0x44f110). So z comes from the vertex's depth, x and y from its
pixel position, and the world position from the inverse of the camera matrix. One rule
for every program - level chunks, skinned models (posed: after skinning, which is what a
renderer wants), shells, trails, decals - and for what the CPU projects itself (the
game's own ground shadows).

- **Ran: the rule is right.** The player's own position put through the camera and the
  projection lands on the character (buffer pixel 640, 266 in play). And with
  `RTA_SCENE_DIAG=1` the library counts how many of the programs' vertices land on the
  quarter-unit grid level geometry is stored on: 14.3 % with the depth constant A as
  above, 4.9 % and 4.4 % with A moved by half a unit either way, 1.2 % (chance) from 1.5
  units on. A sharp peak at exactly the documented constant.
- **Which camera.** A list closed at blank N holds what the game queued during the frame
  before, so the camera sampled at blank N - 1 is used (grid score 14.3 % against 13.6 %
  and 13.5 % for the neighbours; the camera rarely moves in this session, so this is
  weak evidence - see "Left").
- **Precision.** The game sends texel coordinates, not S, T, Q (its texturing is not
  perspective-correct), so there is no 1/z per vertex to take: everything goes by the
  16-bit depth. Its step is 1/16 in A + B/z: 0.005 units at z = 78, 0.13 at the usual
  camera distance of 385, 0.2 at 500 (a character is about 20 units tall).
- What comes out: 185 draws and 92,700 vertices a list in the world in the first level;
  75 draws a list stay flat (the 2-D layer).

**How Godot draws it** (`extension/src/rta_scene.cpp`, `--mode scene`). The viewport of
the 3-D surface gets a perspective camera placed where the game's is (field of view from
`F`; the viewport takes the view's shape, 4:3, because Godot's camera has square
pixels). The scene's draws are the same meshes with the world position as the vertex and
the shader's `GS_WORLD` variant (Godot's `MODELVIEW` / `PROJECTION`); still in the list's
order, each with its own depth test and write, the depth now Godot's own. The 2-D layer
of that surface is drawn as before, in order, without depth. **The game's colours -
texture times its own vertex light - are the surface's colour: baked light.**

- `--shadow`: a `DirectionalLight3D`-equivalent made through the RenderingServer in the
  drawer's scenario (`project/scene_view.gd`), with a four-split shadow map. The shader's
  `GS_LIT` variant lets Godot's ambient light and lights decide how much of the baked
  colour arrives; every opaque draw has a twin instance that is only drawn into the
  shadow maps (the ordered draws are in the transparent pass, which does not cast).
- `--light`: a point light carried 34 units above the first player (its position read
  from the machine's memory every frame).
- `--pull-back F`, `--orbit DEG` (and `app camera pull|orbit|raise|game`, `app scene
  shadow|light on|off` from a script).

**Compared with stage 3 at the same ticks** (`test/scene`: scene mode against draw mode,
Godot's camera on the game's, 1280 x 896): mean difference 2.5 of 255; 1.5 % of the
pixels differ by more than 16. Where (`test/scene/diff-scene-draw.png`): along edges -
the world viewport is 1195 pixels wide and is read back at 1280 - and on large triangles
seen at a slant, which Godot textures with perspective and the game without. Nothing is
missing; the game's own ground shadows are there (after one fault: their texture
coordinates are S, T, Q and were divided per pixel under Godot's perspective as well -
the division is done per vertex now).

**Measured light** (`test/scene/cal`). The Compatibility renderer draws a light that has
a shadow map in a pass of its own and adds that pass to the picture as stored values,
after the conversion from linear light: ambient 0.55 with a sun of 0.45 gave 2.2 times
the game's light. The energies that add up to the game's own picture are `shade^2.2` and
`(1 - shade)^2.2`; with `shade` 0.62: sunlit stone 0.95 of the game's stored value, a
shadow 0.66, sunlit grass 0.79 (dark colours come out lower, because the renderer's
conversion is not a pure power). A point light's fall-off is by distance^-attenuation,
and the game's unit is small: attenuation 0.35 and energy 5.

**What breaks, honestly:**

- **Culling.** The game draws what its own camera sees. Pulled back or turned, the level
  ends where the game's frustum ended (the saw-tooth edge in `hub-5`, `hub-6`), and
  characters outside it are not there. Fixing that is on the game's side: the widening
  the graphics work does for 16:9 (`app/gfx_rt.cpp`, the frustum planes) is the place.
- **The sky** is a small dome round the camera, drawn first; from outside it is a disc.
- **Effects built in screen space** stay in the 2-D layer: the full-screen colour
  multiply and the blend with the previous picture (present pass), heat haze (not looked
  at: no fire level was run in scene mode), anything drawn with "depth always". They are
  drawn in the list's order without depth - right under the game's camera, wrong under
  another.
- **The HUD** is the game's 2-D layer and stays where it was: it does not know the camera
  moved (which is what one wants of a HUD). Text and bars are drawn before the present
  pass and get its colour multiply, as in the game.
- **The game's own ground shadows** are still drawn, so with Godot's sun there are two
  shadows per character. They are projected quads floating 10 units above the floor,
  pulled toward the camera; from another camera they are not on the floor.
- **No normals.** The list has none (the programs consume them); the lit variant uses
  the triangle's own facing, so a point light shades by flat facets. The sun is applied
  without facing at all (the game's shading is in the colour already).
- **Light is added on stored values** (above): bright where two lights overlap, and
  dark colours take less than their share.
- **Depth from 16 bits**: far geometry wobbles by a fraction of a unit when the camera
  moves; not seen at the usual distance.
- Two shadows of the same thing, alpha-tested foliage casting as hard cut-outs, shadow
  bias on small props: tuned by eye once, not studied.

**What a tap at the programs' inputs would add** (not done): exact positions (the int16
model coordinates and their matrices instead of 16-bit depth), normals, the joint
matrices and weights (so that Godot could skin and animate by itself), the light slots.
It needs one decoder per program entry (`render-pipeline.md` section 4 lists nine for
models and five for chunks) and a hook where VIF1 starts a program
(`render/vif1.cpp`, at `MSCAL`); the un-projection here needs none and gives the same
vertices to within the depth's step.

## Stage 5: export (Ran for macOS; Read for Windows)

`python3 tools/godot/build.py extension --release && python3 tools/godot/build.py export`
makes `local/godot-spike/export/RtaGodot.app` (201 MB: Godot's universal release
template, the release extension, the game library, the project's scripts as a pack):

1. the project is copied to `local/godot-spike/export/project` without the test
   settings and without the game library; `export_presets.cfg` gets the template's path;
2. the bounded editor start, then `godot --headless --export-release macOS`;
3. `librta_game.dylib` is copied into `Contents/Frameworks` beside the extension (the
   host looks there), extended attributes are cleared (a synchronised folder leaves
   them) and the bundle is signed ad hoc.

**The application contains the translated game and must not leave the machine.** What
could be given to others is the same export without step 3 plus a way to build the
library from one's own disc.

- Ran: the exported application started without a window (`--headless`), loaded the
  library from its own bundle, copied the executable out of the disc image (no workspace
  is given to it), booted and ran a script; its two pictures are identical to the
  library's (`test/export`). `codesign --verify --deep` passes.
- **Not run: the exported application with its window.** Its first frames would carry
  the application's own title, not a test title; the same scripts and extension ran in a
  window from the staged project. Without options it asks for the disc image with a file
  dialog once and remembers the path (`user://settings.cfg`): Read, not run.
- The official macOS template is universal and the preset has to say so
  (`binary_format/architecture="universal"`; "arm64" asks for a template the archive
  does not have). The extension and the game library are arm64 only: on an Intel Mac the
  application starts and reports that the extension is missing. The project needs
  `rendering/textures/vram_compression/import_etc2_astc=true` to export for macOS at all.

**Windows, the same route** (Read; nothing of it was built or run):

- *The game library as a DLL.* `tools/recomp/app/build_win.py` already compiles the same
  sources for x86-64 with MinGW or clang (`native-windows.md`): runtime with
  `rt/host_win32.cpp`, renderer, sound, the translated game. For the library: link
  `-shared` instead of a program, with `tools/godot/lib/rtag.cpp`, `scene_tap.cpp`, a
  `host_godot` twin of `host_win32.cpp` (`quit()` that stops the machine instead of the
  process) and export the fourteen `rtag_*` functions. `audio_host.inc` is portable.
  For the library's own renderer (picture mode) `gl_offscreen` needs a WGL twin (a hidden
  window and a 4.1 core context, as `app/win/wgl.cpp` makes one) and `backend_gl.cpp`
  the include path `app/win` instead of `lib/gl_standin`; draw and scene mode need
  neither.
- *The extension.* `extension/CMakeLists.txt` has the Windows branches of
  open-champions-godot's (static runtime, library names); `rta_library.cpp` has
  `LoadLibrary`; `rta_machine.cpp` `_chdir`. Built with MSVC as that repository's CI
  does, or with the same MinGW as the game library. The x86-64 game computes as the
  arm64 one does (`native-windows.md`, the stand-in comparison), so the same proofs
  apply once it runs.
- *The export.* A "Windows Desktop" preset; the template is in the same archive that was
  downloaded (`templates/windows_release_x86_64.exe`), so a Mac can export the `.exe`
  and its `.pck`; the DLLs go beside them.
- *What could be wrong there*: everything `native-windows.md` lists as not run, and the
  three renderer conventions of stage 3 (they were found on macOS's OpenGL; Godot's
  Compatibility renderer on Windows may run on ANGLE, where y and depth conventions are
  handled by Godot but were not checked here).

## How this relates to open-champions-godot

That repository is a hand-written port, system by system, with no game code and no game
data: an archive browser, texture and model previews, a movement test. This spike is the
other route: the game's own code, translated, as the logic, with Godot as the platform.
They meet at Godot, at the same pins (Godot 4.5.2 standard, godot-cpp `e83fd09`, single
precision, CMake, the Compatibility renderer).

**What could be moved there as it is** (written for this spike, nothing derived from the
game in it):

| What | Why it fits |
|---|---|
| `tools/godot/extension/` (CMake project, `RtaMachine`, `RtaAudioStream`, `RtaDrawer`, scene mode) | the layout and options of `gdextension/`; it does not link or contain the game: it loads a library the user builds, by path |
| `tools/godot/project/` (`main.gd`, `view.gd`, `scene_view.gd`, `shaders/gs_draw.gdshaderinc`, the presets) | scripts and one shader; the shader is a general "PS2 GS draw state in Godot" piece and would serve a hand-written renderer just as well |
| `tools/godot/lib/rtag.h` | the contract between a Godot front end and any back end that produces GS-level draw lists |
| the three renderer findings of stage 3 and the light measurements of stage 4 | they hold for any project that wants stored colours and ordered draws out of Godot's Compatibility renderer |

What that repository would have to decide: its `AGENTS.md` forbids importing a sibling's
generated output and asks that "native tools, decoded assets, Godot exports, playable
scenes" each have their own evidence. The extension respects the first (it imports
nothing); a playable scene made this way is playable only with a library the user builds
privately, and the repository's CI cannot run it (no disc). So it would live there as an
optional second front end ("bring your own library"), tested there only as far as "the
extension loads and reports that no library is present".

**What cannot be public**: `librta_game*.dylib` and everything under
`local/godot-spike/src/` (the translated game), the exported application, every picture
and log, and - by the project's own rule - `tools/godot/lib/rtag.cpp`,
`scene_tap.cpp`, `host_godot.cpp`, `audio_host.inc`, `build.py` and `recomp.patch` are
only useful together with `tools/recomp` (they are public here, in this repository, with
the rest of the native build; they contain no game code, but they are not Godot code and
belong with the runtime they wrap).

**What each side could use of the other**: the hand-written port's decoded models,
skeletons and world geometry are exactly what stage 4's "tap at the programs' inputs"
would otherwise have to recover - a mixed renderer could take static level meshes and
skinned characters from that side (with normals, whole levels, no culling by the game's
camera) and positions, poses and everything dynamic from the running game. The other way
round, this spike is a reference to compare the port's systems against, tick for tick,
inside the same engine.

## What is in tools/godot

```
build.py            snapshot | lib [--original] | extension [--release] | project | export | patch
run.py              starts Godot on the staged project; `import` for the bounded first start
recomp.patch        the one change to tools/recomp's sources (sound/audio_out.cpp, 16 lines)
lib/                the library's own sources: rtag.h, rtag.cpp, scene_tap.*, host_godot.cpp,
                    audio_host.inc, gl_offscreen*, gl_standin/, png_write.h, host_main.cpp (rtag_host)
extension/          CMakeLists.txt, dependencies.json, src/: register, rta_library, rta_machine,
                    rta_audio, rta_drawer, rta_scene, rta_variant.h
project/            project.godot, rta_godot.gdextension, export_presets.cfg, main.tscn, main.gd,
                    view.gd, scene_view.gd, shaders/gs_draw.gdshaderinc
```

Test aids (environment): `RTA_SCENE_DIAG=1`, `RTA_SCENE_DELAY=n` (library);
`RTA_GODOT_FLIP`, `RTA_GODOT_TEXFLIP`, `RTA_GODOT_STORED`, `RTA_GODOT_NO_INVERTED`,
`RTA_GODOT_BIAS`, `RTA_GODOT_DUMP=DIR` (drawer; the last writes every surface as Godot
holds it at each `app shot`). `rtag_host --list-stats` prints how the lists are laid out
over their surfaces and every state combination with its number of draws.

Tests are scripts under `local/godot-spike/test/` (`env.sh`, `rig.sh`, `piccmp.py`, one
directory per run with `route.rig` and `out.txt`). **A run's data directory must be
new**: a memory card left by an earlier run changes the boot route and the script times
out (found the slow way).

## Left

1. **Paced at 60 on a free machine**, draw and scene mode (the machine was loaded when
   it was tried); and the cheap gains of stage 3 (one mesh per frame, no doubled 2-D
   draws), which are probably what makes it comfortable.
2. **The camera's delay while the camera moves** (stage 4): walk and compare a level
   vertex's world position frame by frame; one blank is argued and weakly measured.
3. **Culling for another camera**: widen the game's frustum from the host (the hooks of
   `gfx_rt.cpp`), so that a pulled-back camera has a level to look at.
4. Scene mode beyond the first level: a fight in `valor` (trails, hit effects), a fire
   level (heat haze reads the 3-D surface in the middle of its draws: last frame's
   picture in this drawer), the menus' 3-D figure (its own projection: the one camera
   per frame taken here is the level's), cutscenes (their own field of view is read each
   blank and should just work: not looked at).
5. A real controller (Godot's joypad path is written and was not exercised: `app gcpad`
   exists and was not run), rumble, a second player, a listening test.
6. The exported application with its window; Windows (stage 5); an Intel slice.
7. Wide screen in the Godot modes (`--aspect` reaches the game and the tap carries `k`;
   not run), multisampling and the art pack in draw mode.
8. Network: left out of the library on purpose; `tools/recomp/net` would be linked as
   `app/build.py` links it.
