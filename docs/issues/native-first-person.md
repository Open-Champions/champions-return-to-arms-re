# Views for the native build: overhead, action, chase, shoulder, first person

Started 2026-10-13. The owner asked "Is it possible to first person" and then made it the
main effort: the game "sick in first person, and multiple clean character views". This is
the camera system for the native build of Champions: Return to Arms (SLUS-20973 v2.00;
`docs/issues/native-app.md`, `native-graphics.md`). Every statement says whether it was
**Ran** (with what was seen) or only **Read**. Pictures are game output and stay under
`local/recomp-fp/pictures/`.

## STATE (rewritten at every step; read this first after a stop)

**2026-10-13 14:16 - all five views run; the simulation is the overhead view's in each.**

- **Ran:** overhead, action, chase, shoulder, first person in seven levels (hub, valor,
  honor, arachna1, fire3, tormenta, islsm1), a fight, level changes, and the opening
  cutscenes of blood1, fay1 and drunare (the game's own camera through them, in every
  view); the same simulation tick in every view (section 6).
- **Ran:** the tick comparison in every view, two sessions (section 5): every simulation
  column identical to overhead at every tick; the object pool differs in pose-cache and
  decoder-slot pointers only.
- Three things had to be found for that (section 5.2): the view is held off during the
  blanked warm-up; a view's draw pass costs the virtual console no time; the game's
  "terrain late" count is held while a view is drawn.
- **Not run:** a window (every run was off screen), the V key, widescreen with a view, the
  settings file round trip, a net game (the prediction copy as anchor, section 3, is Read
  only), two local players, death, the pause menu, inventory and dialogue with a view
  selected (the fallback rule covers them by the camera mode; only cutscenes and loads were
  seen).
- The patch is `tools/recomp/app/fpview.patch`; new files `tools/recomp/app/fpview.h`,
  `fpview.cpp`. Nothing in the shared tree compiles them until the patch is applied.
- My copy of the sources and my builds: `local/recomp-fp/` (`base` = `tools/recomp` as it
  stood 13:15, `src` = with the views, `root` = a stand-in workspace root whose
  `tools/recomp` is `src` and whose `local/recomp-out` holds my translations, objects and
  `bin/rta_app_fp`, `bin/rta_app_orig_fp`; `work` = scripts and results; `pictures`).

Next (section 8 has the list): a window and the key; chase and shoulder against creatures
and trees in the way; the first-person eye from the head joint; the listener of the sound
at the view.

## 1. How to apply, build and select a view

```
cd tools/recomp && patch -p1 --dry-run < app/fpview.patch && patch -p1 < app/fpview.patch
python3 tools/recomp/app/build.py --as rta_app_next          # translates again: hle.txt gained 5 addresses
python3 tools/recomp/app/build.py --original --as rta_app_orig_next
```

To build without touching the shared tree, the way it was done here: a stand-in root
(`local/recomp-fp/root`: links to `SLUS_209.73`, `names.tsv`, `symbols`, `patches`,
`ghidra_funcs.tsv`, `tools/play-net`, `tools/rig`; `tools/recomp` -> the copy of the
sources; a `play-net` link beside the copy for `net/online.cpp`'s include; its own
`local/recomp-out` with `gen-vu` copied in), then
`python3 local/recomp-fp/root/tools/recomp/app/build.py --as rta_app_fp` (2 minutes for the
game, then `--no-game` for every later change: seconds).

Selecting a view:

| Where | How |
|---|---|
| command line | `--view overhead\|action\|chase\|shoulder\|first` (default `overhead`: nothing of the view code runs); `--view-set view.first.fov=75` |
| settings file | `view = first`, and `view.<mode>.<name> = value` lines (list: `fpview.h`, `setting`) |
| key | `V` next view, `Shift+V` previous (not in a test window, like `F`) |
| script / control socket | `app view NAME`, `app view next`, `app view set KEY VALUE`, `app view info` (prints the view of the last frame: eye, forward, field of view, the game's own camera, the player, the fallback reason) |
| runtime option | `-- --opt view=NAME`; `--opt view-log=1` one line a second; `--opt view-zoom=off` (section 4) |

## 2. The camera in the game (Read, then Ran)

| What | Where |
|---|---|
| the game's camera object | pointer `g_localCamera` 0x4f8450; mode +0x34 (1 = follow, 0 = held by a menu / dialogue / cutscene, 3..5 free fly), reset state +0x48, zoom index +0x54 (0..2: distance 170 / 340 / 450, pitch 41 / 55 / 66 degrees), yaw word +0x68, pitch word +0x6a, the slot whose pad drives it +0x40 (`docs/spec/movement-camera.md` 7) |
| who places the engine camera each tick | `Camera_update` 0x203400 (run task `camera`, priority 11; in a net game from `net_predictLocalPlayer`) -> `Camera_updateFollow` 0x204938 -> `Camera_apply` 0x2035c8 -> `camera_setView(pos, mat34)` 0x18a2b0 |
| `camera_setView` | writes `g_cameraPos` 0x44f038, `g_cameraMatrix` 0x44f110 (rows are world x, y, z; columns are the camera's right, down, forward; then the translation), builds `g_viewProj` 0x44f140, `g_viewProjWorld` 0x44f180, `g_viewProjModel` 0x44f1c0 with `mat4_setProjection` x 3 (sx 1, sy 0.4667, `g_projScale`, depth 1..4095.9, **near 18, far 1800** as constants), then `camera_buildFrustum` 0x1863fc: six planes in world space at 0x44f0a8 and the second set at 0x7d5c08, sign bytes at 0x7d89d8 / 0x7d89f0; the far plane is moved to `g_farClip` 0x7d8a04 (level or cutscene script, capped at 1800), the near plane to 18 |
| field of view | `camera_setProjection(fov, aspect, fov2, v)` 0x18619c: `g_projScale` 0x44f108 = 477.5 / tan(fov / 2) and the camera-space planes (0x7d5bc0 with one degree to spare; 0x7d5c68 for `fov2`). `fov` is the **vertical** angle: 50 degrees in play. Called when a level or a cutscene starts, not every frame |
| the camera stick | `Camera_followRotateInput` 0x205db0: x turns the yaw word (growing word = clockwise seen from above; **Ran**: stick right, heading falls). `Camera_followZoomInput` 0x205880: y beyond 0.9 steps the zoom index. Pad floats: `g_pads` 0x41bfd8 + slot x 0x58, +0x1c x, +0x20 y (negative = pushed up) |
| the player | `g_players[slot]` + 0x43d8 = object (0x4dcec8 + slot x 0x4c30); position +0x10 (feet), facing word +0x38. The camera is "behind the character" at yaw word 0x4000 - facing, so the character's heading = the camera's heading - ((0x4000 - facing) - yaw word) (**Ran**: constant while only the camera turns, 2.4 degrees off the camera's heading after walking "up" - the 0x41c2 of `Player_move`) |
| local alive players | count 0x4f8424, slots 0x4f8430 |
| what reads the view in the simulation | the yaw word and the mode (`docs/spec/movement-camera.md` 7.1), `g_cameraFocus` 0x44f048 (music counter in `damage_apply`, the camera-gated effects of `docs/gameplay.md` 8), the planes for the offline two-player screen clamp (`native-graphics.md` 1.3) |

## 3. How the views are done: the game's camera is never touched

`tools/recomp/app/fpview.cpp`; five addresses in `hle.txt`.

- The game's camera object and the engine camera run as they always did, through the whole
  run pass. Every word the simulation reads - yaw, mode, focus, planes - is the overhead
  view's.
- **For the length of the draw pass only** (`tasks_call(0, 1)` 0x19e798, the call at
  0x323284) another camera is in place. Before the pass: the words `camera_setProjection`
  and `camera_setView` write are saved (11 ranges, 632 bytes, with `g_farClip`); the view's
  camera is made on the host (floats of the host: none of it is simulation); the game's own
  `camera_setProjection` and `camera_setView` are called with it - through the widescreen
  hooks of `gfx_rt.cpp`, so a view is wide like the game's - and `transformSceneLight`
  0x148018 once more so the sun and fill directions are in the new camera's space. Then the
  game's draw tasks run: `world_draw`, the object walk, decals, particles, glows, names
  over heads, all cull and project with their own code for that camera. After the pass the
  game's projection and view are run once more with the game's values (that brings
  `gfx_rt`'s host-side copies back) and the saved bytes are put back.
- `camera_updateFocus` 0x18a520, which `drawWorld` calls inside the pass, is handed the
  game's own position and matrix for the length of the call: `g_cameraFocus` is what it is
  in the overhead view.
- `worldtex_stream` 0x17d830 (after the pass; keeps the 3 x 3 texture cells round the focus
  loaded) sees the drawn view's focus (eye + forward x 600) for the length of its call: a
  view along the ground needs the cells ahead, not the ones under the camera.
- **The player's model in first person**: `Player_draw` 0x1a46c0 runs as always (everything
  it does to the pose cache, the status counters, the prompt code happens); the range of the
  display list it filled is noted, and when the runtime walks the list for VIF1 the data of
  the tags in that range is left out (`rt_dma_skip`, new in `rt/runtime.cpp`; a skipped
  `call` tag takes its subroutine with it).
- **Fallback**: a view is put in place only when the game's camera is in follow mode
  (+0x34 = 1), not resetting (+0x48 = 0), no cutscene (`g_cutsceneActive`), no load screen,
  no warm-up (`g_warmupFrames`, section 5.2), a level loaded, exactly one local player
  alive with an object. Otherwise the frame is the game's own (cutscene, dialogue,
  inventory, shop, death, two players on one machine, free camera). Afterwards the view
  eases back in from the game's camera - or, after a warm-up, is simply there when the
  picture comes back from black (which is how a cutscene, a load and a closed menu end).
- **In a net game** the object on screen for this machine's player is the prediction copy
  (`g_ghost` 0x4027bc): position, facing and the hidden model are those of
  `net_objOrGhost(object)` 0x13e180 (`View::drawn_object`). **Read, not run.**
- **Two timing matters of the virtual console** (section 5.2): a view's draw pass costs
  its clock nothing (`rt_unit_cost`), and the main loop's "terrain late" count is held at 0
  while a view is drawn.
- **Easing**: a change of view takes `view.ease` seconds (0.35), position and field of view
  linear, orientation spherical, on a smoothstep; the pose it starts from is kept relative
  to the character and the heading, so it travels with a moving character. Time is counted
  in simulation ticks, so pictures at fixed ticks repeat.

The views (defaults; every number is a setting):

| View | Camera | Field of view (vertical) | Near | Stick y |
|---|---|---|---|---|
| overhead | the game's | 50 | 18 | zoom (the game's) |
| action | 215 behind and above a point 55 over the feet, 33 degrees down, at the game camera's yaw | 50 | 18 | - |
| chase | 150 behind a point 62 over the feet, 14 degrees down | 58 | 12 | looks -45..+25 |
| shoulder | 88 behind a point 66 up and 20 to the right, 8 degrees down | 60 | 8 | looks -55..+45 |
| first | 60 over the feet, 7 ahead; the player's model left out | 70 | 4 | looks -65..+65 |

All distances are multiplied by the character's height extent (object +0x20) / 72.

**The level in the way** (chase, shoulder, action; `pose_of` in `fpview.cpp`). The level's
walls are blocks of its height field, and the game's own query for a line across it is
`terrain_raycast` 0x18a5c0 (what its camera uses). Per frame: (1) the camera must see the
character's head and knees - two rays; when it does not it first **swings up** over what
is in the way, as the game's own camera does (steps of 9 to 52 degrees, the first that
sees both; eased at 150 degrees a second up, 35 down); (2) what is then still between the
pivot and the camera makes it **come closer**, at once, and go back out at 240 units a
second, so that a pillar passing between does not make the picture jump; (3) it stays 7
above the floor under it (`terrain_height` 0x183820) - only a floor near the character's
own: over a wall the query gives the wall's lid, and the camera is not lifted onto walls.
The queries advance the terrain visit stamp, as the game's own camera does per machine;
nothing else. **Ran** in `honor` (parapets, pools, walls): the first version, which only
pulled in along one ray and lifted the camera to any ground under it, put the camera on
top of walls and behind parapets there; `tour/honor-chase-a.png` and `-d.png` are the
present one.

### For the two works that build on this: `fpview.h`

One header, nothing of the runtime in it. `fpview::view()` gives the frame's `View`: the
mode selected and shown, the blend, whether the frame fell back and why; eye, forward, up,
right, field of view, near and far of the camera the frame is drawn with; the game's own
camera of the frame (eye, axes, field of view, heading, zoom index, yaw word); the local
player (slot, object address, feet, head point, facing as angle and vector); the look yaw
and pitch; tick and frame number.

`fpview::add_pitch(degrees)` adds to the selected view's pitch at the next draw pass,
inside its limits, from any thread (the controls work's mouse).

Two call-outs, both on the game's thread with the translated code's `Ctx*` (game functions
can be called with it; `fpview.cpp`'s `GuestCall` shows how):

- `fpview::on_view(fn)`: after the view's camera is made and **before the game builds its
  projection and planes**. Change `eye`, `forward`, `up`, `fov`, `near_plane`,
  `far_plane` (the depth range of the projection), `cull_far` (the far plane everything is
  culled by, `g_farClip`; the game's `camera_setFarClip` caps at 1800 but the word itself
  takes any value), `stream_focus`, `hide_player`: what is in the `View` when the call-out
  returns is what gets built.
- `fpview::on_drawn(fn)`: when the draw pass has returned, the frame's draw list complete
  and the view still in place; the game's words are put back right after.

`fpview::ray` and `fpview::ground` are the two terrain queries. To hook further game
functions: add the address to `hle.txt` (under "view modes" or a section of your own),
supply `fn_<address>` in a file of your own, call `orig_<address>`; a translation and a
full compile follow (2 minutes).

## 4. Controls: what a stick does in each view (Read, then Ran)

The simulation's meaning of a pad row is the overhead view's in every view, because the
game's camera is the overhead camera in every view:

- **Move stick**: `Player_move` turns the character toward `atan2(lx, ly) - yaw word -
  0x41c2` and runs it that way. The yaw word is the game camera's. Every view here looks
  along the game camera's heading, so "up" is into the screen in all of them, left is
  left. (**Ran**: first person, stick up for 60 ticks: the character went from (131, -96)
  to (31, 18), along the view.)
- **Camera stick x**: turns the game camera's yaw (its own code, its own speed and
  easing) - and with it the view and what "up" means. Offline the simulation reads the
  yaw live; in a net game it travels in the input record. Identical in every view.
- **Camera stick y**: in chase, shoulder and first person it looks up and down (host-side
  state). The game's camera still sees the same stick: pushed beyond 0.9 it steps its
  hidden zoom index, as in overhead. That is kept by default because holding it off
  changes what the game camera does with a pad row (at zoom index 0 the yaw turns at 0.595
  of the speed and the camera is drawn behind the character while it moves). `--opt
  view-zoom=off` holds `Camera_followZoomInput` off in views that look with the stick;
  the same pad row then gives another yaw than in overhead once the stick has been pushed
  fully up or down - for the controls work to decide.
- The character does not turn with the view: it faces where it last ran or struck, and
  the view looks where the game's camera looks. **Ran** (the fight route, by script: walk
  at the boars, strike): the character turns to the creature it strikes by itself, the
  view does not, and in first person the fight was beside the picture - only the weapon's
  trail crossed its left edge (`fight/fight-2-first.png`), while the shoulder view shows
  character and boar as they meet (`fight/valor-meet-shoulder.png`). The stick, by script
  in the first level (camera heading 134.9 degrees throughout): 60 ticks "up" moved the
  character 154 units along the heading; 60 ticks "left" 153 units at heading + 85.5
  degrees, the character now facing heading + 87.7; "down" straight back; "right" (in the
  shoulder view) to the right. So "up" walks into the picture in every view, and left
  runs the character left across it (it turns to face left and runs: there is no sidestep
  in this game) while the view stays where it was. So first person as it is
  here is a camera, not yet a way to play: the view has to be turned to what the
  character faces (or the character to the view), and both are input matters - the
  controls work's.

## 5. Does it change the game?

**No: in every view the simulation computes what it computes in overhead.** Two sessions,
both from power-on through the front end, character creation, the first level, a change
to `valor`, a walk and a fight with boars (5,410 ticks of `valor`), the unpatched
translation with the view hooks (`rta_app_orig_fp`), off screen, the view selected from
power-on. Columns: tick, shared seed, position, facing, action state, object seed, hit
points, mana, gold, experience, bag, statistics, equipment, abilities, skills, the whole
player record, the object pool, the task table, the pads.

### 5.1 Results (Ran)

| Session | overhead | action | chase | shoulder | first |
|---|---|---|---|---|---|
| **the rig's controller rows replayed** (`fight3.rig`; `rigcompare.py boot-native --replay` against the rig's log of the original) | the result file is `merge/rig-final-compare.txt`, byte for byte | as overhead in every simulation column at every tick | the same | the same | the same |
| **the camera stick in use** (`work/stick.rig`: the same route with the camera stick held on 370 of its pad lines - turns both ways, full pushes up and down that step the game's zoom, diagonals). Each view runs it; then overhead is given, tick for tick, the rows that run delivered | - | every column identical at all 5,410 ticks, the player record and the frame counter included | the same | the same | the same |

What differs, in every view and in nothing else:

- **the object pool's CRC**. Memory was written at ticks 1500, 2701 and 3905 (in the fight)
  and compared with overhead's byte for byte (`local/recomp-gfx/out/work/pooldiff.py`): 2
  to 71 bytes, all of them at +0x114 (the pose-buffer pointer of the animation state) and
  +0x120 + 0x20 n (the decoder-slot pointer of track n) of the `Player` and of 2 to 8
  `WarBoar` - handles into caches that drawing fills (`docs/issues/pose-cache.md`); what
  widescreen changes too (`native-graphics.md` 1.3). No position, hit point, state, timer
  or generator of any object.
- **the cosmetic seed** (drawing draws from it).

So: a view is another picture of the same simulation, and two players of a net game can
each use the view they like. What that rests on, beyond these runs: in a net game the tick
is driven by the lockstep loop and "frozen" is the pause flag only, so the two timing
matters below (which are offline matters) do not arise; the yaw travels in the input
record and is the game camera's own, which no view changes; and which objects a machine
draws differs between machines of a net game anyway (FINDINGS D13). **Not run:** a net
game with different views on the two machines.

### 5.2 What had to be found first (Ran)

The first comparison did **not** pass: every view gave the same *other* simulation from
tick 1261 of `valor` on (another seed, a `Skeleton` that exists 90 ticks earlier). Three
causes, each in the timing of the offline game, none in the picture:

1. **The warm-up.** After a load, a cutscene or a menu the picture is blanked for 10
   displayed frames (`g_warmupFrames` 0x506048) and the count starts again while the
   texture stream is busy. Offline the tick counter stands still for its length and
   `game_isFrozen` is true, but parts of the run pass go on: its length is simulation
   timing. A view drawn through it asks for other textures, the stream is busy two frames
   longer, the warm-up is 13 frames instead of 11 (seen at tick 1171, the end of the
   opening cutscene). **Now:** while `g_warmupFrames` is not 0 the frame is the game's own
   (it is thrown away unseen anyway) and the view cuts in, without easing, when the picture
   comes back from black.
2. **The virtual console's clock.** The runtime counts 4 cycles for every call and
   backward branch of translated code, and a field is 4,920,115 cycles; a draw pass for a
   camera along the ground draws far more than the console's camera ever asked for (the
   whole session: 421 million units in first person against 236 million in overhead) and
   runs past its field, upon which the game steps two ticks in the next frame with one
   controller sample (72 frames in a row in first person at one place of the fight
   route). **Now:** `rt_unit_cost` (new, `rt/runtime.cpp`): the draw pass of a view costs
   the virtual clock nothing. `--opt view-clock=counted` is the old behaviour.
3. **"Terrain late".** The main loop counts displayed frames in a row with the texture
   stream's "late" flag up (`g_terrainLateFrames` 0x5060a8) and after 21 asks for half the
   display rate, to give the stream time. A view along the ground has level chunks in
   sight whose texture cell is outside the 3 x 3 cells the game keeps loaded; the flag
   never drops, and the game ran at two ticks a picture for as long as they were in sight
   (282 frames of a tour of `valor` and `honor` in first person; none with the far plane
   at 1300 or nearer). **Now:** the count is set to 0 after every draw pass of a view
   (`worldtex_stream` hook). The chunks themselves are still drawn with whatever texture
   they have: that is the world work's matter (`native-first-person-world.md`).

All three are the *offline* game: there a frame that steps two ticks reads the controller
once, so what a person holds reaches other ticks. Tick for tick, with the controller rows
of that run, the simulation was the same even then (the pair comparison was made for
first person before 2 and 3 were fixed: every column identical but the pads' own
structure). `--opt view-timing=1` prints every frame longer than 1.2 fields with where its
time went; no view has one now in any of the runs of section 6.

Also found: `fight3.rig` writes three memory images into `local/recomp-out/pilot/` (its
own `dump` lines); my first runs of it wrote them like every run of that script does. The
runs here use a copy without those lines (`work/mkrig.py`).

How to repeat: `local/recomp-fp/work/rig.sh VIEW` (result `work/rig/VIEW/compare.txt`),
`RIG_SCRIPT=work/stick.rig RIG_NAME=stick-VIEW RIG_REPLAY= work/rig.sh VIEW` then
`work/pair.sh stick-VIEW` (result `work/rig/stick-VIEW-pair/compare.txt`).

## 6. Pictures

All 1280 x 896, 4:3, off screen, the program's own capture; every run is keyed on the
simulation tick, so a row of five is the same tick of the same simulation (checked: the
player's position at each stop is the same in the five runs).

| Set | What | Files (`local/recomp-fp/pictures/`) |
|---|---|---|
| `base/` | the first level, one run cycling the views | `hub-overhead.png`, `hub-action.png`, `hub-chase.png`, `hub-shoulder.png`, `hub-first.png`, `hub-first-walk.png`, `hub-first-turn.png`, `hub-first-lookup.png` |
| `fight/` | the fight route, one run per view: `valor-stand`, `valor-walk1..3`, `valor-meet` (the boars arrive), `fight-1..6` | `NAME-VIEW.png` |
| `tour/`, `tour2/` | `valor`, `honor`, `arachna1`, `fire3`; `tormenta`, `islsm1`, `blood1`, `fay1`: a = standing, b = after walking "up" 90 ticks, c = after 45 ticks of camera stick right, d = after walking 90 more | `LEVEL-VIEW-a..d.png` |

The ones to show: `base/hub-chase.png`; `tour2/tormenta-chase-a.png`,
`tormenta-shoulder-a.png`, `tormenta-first-a.png` beside `tormenta-overhead-a.png`;
`tour/honor-chase-d.png`, `honor-shoulder-d.png`, `honor-first-d.png`;
`fight/valor-meet-shoulder.png` (a boar at arm's length); `tour2/islsm1-first-a.png` (the
beach and the sea).

What they show, by kind of level:

| Level | Good | Broken or missing |
|---|---|---|
| hub (floating island) | a sky dome and far mountains the overhead view never shows; holds up from the ground in every view | in the action view the dome stops at a straight edge near the top of the picture |
| tormenta (fortress in the clouds) | the best: cloud backdrop all round, walls and spikes read well from the ground | - |
| valor (forest) | ground, cliffs, trees and barrels from the ground; the boars arriving in the shoulder view (`fight/valor-meet-shoulder.png`); two ticks on, the shoulder camera has come in to the shoulder itself for the slope behind and the character fills the lower left corner (`fight-2-shoulder.png`) | sky is the plain background colour; tree crowns hang in front of the chase and action cameras (they hide the character in overhead too); a cliff the character stands against shows holes in first person (triangles the game drops whole near the eye) |
| honor (walled gardens) | corridors and pools from the shoulder and the eyes | black above the walls (no sky, no ceiling); in the action view a wall top fills a corner at some places |
| arachna1, fay1 (caves) | dark, lit by torches, convincing from behind the character | first person against a wall is a blur of one texture; black where the cave has no roof |
| fire3 (lava field) | the lava glows to the horizon | a flat orange background for a sky; a grid of dark squares at the horizon where far lava tiles are cut |
| islsm1 (beach) | sea, foam and a sky with clouds in first person | the level's ogre stands at the start: in chase and shoulder the camera is behind *him* and his back fills the picture (creatures are not in the camera's line-of-sight test) |
| blood1, fay1, drunare | open with a cutscene: every view shows the game's own camera through it, letterbox and all, as intended | - |

Everywhere: the HUD is where it was; names and prompts follow the view (they are
projected by the game with the view's matrix); the heading the view looks along is the
game camera's, not the character's (section 4), so in first person a fight the character
turns to by itself can be out of the picture (`fight/fight-2-first.png`: only the weapon's
trail crosses the left edge).

## 7. What was changed where

| File | What |
|---|---|
| `tools/recomp/app/fpview.h`, `fpview.cpp` (new) | everything of the views; the interface for other work |
| `tools/recomp/hle.txt` | 5 addresses under "view modes": `tasks_call` 0x19e798, `camera_updateFocus` 0x18a520, `worldtex_stream` 0x17d830, `Player_draw` 0x1a46c0, `Camera_followZoomInput` 0x205880 |
| `rt/rt.h`, `rt/runtime.cpp` | `rt_dma_skip` (a tag's data left out of the VIF1 stream; a skipped `call` takes its subroutine; the state ends with the chain), `rt_unit_cost` (the price of a unit on the virtual clock) |
| `app/gfx_rt.h`, `gfx_rt.cpp` | `projection_args` (the game's last `camera_setProjection` arguments), `set_depth_range` (near and far for the three projection builders while a view is in place) |
| `app/settings.h`, `app/app_main.cpp`, `app/help_mac.mm`, `app/build.py` | the `view` settings, `--view`, `--view-set`, `app view ...`, the V key, the help text, the job list |

All of the last four rows are in `tools/recomp/app/fpview.patch` (merge notes at its head).

Runtime options of `fpview.cpp` (after `--`): `view=NAME`, `view-zoom=off`,
`view-clock=counted`, `view-log=1`, `view-timing=1`; for tests `view-stream=off`,
`view-collide=off`, `view-light=off`.

## 8. Left

- **A window.** Nothing here was run in a window: the V key, the easing as a person sees
  it, the stick's look speed, a change of the window's shape with a view selected.
- **The first-person eye.** A fixed height (60 x the character's height extent / 72) over
  the smoothed feet. The head joint can be read (`model_getAttachPoint` 0x1754a0,
  `anim_getJointMatrix` 0x16f720 on the animation state at creature +0x114); it is not
  used: a query builds a pose when none is attached, which is the pose cache's business
  (`docs/issues/pose-cache.md`), and an eye that swings with every blow is not obviously
  better. The model is hidden whole; arms and weapon in view are the controls work's.
- **Creatures, trees and props in the way** of the chase and shoulder cameras: the camera
  only asks the terrain (`terrain_raycast`). `world_raycast` 0x18ad94 adds object circles
  but counts every creature, the one being fought included.
- **Sound** is heard from the game's own camera in every view (`sound_panAtten` 0x213c50
  and `soundSeq_updateAll` 0x2147c0 read `g_cameraPos` outside the draw pass): left and
  right are right, since the heading is the same; distance is the overhead camera's.
- **The gold floater** (`hud_addGoldFloater` 0x1dc268, called from the simulation) is
  placed with the game's own matrix: in a view it starts at the wrong place on screen.
- **Following the facing.** Every view looks along the game camera's yaw. A chase camera
  that swings behind the character by itself needs the game's yaw to follow the facing
  (the game has that: its own "behind the character" pull at zoom index 0, or a written
  yaw word, which the controls work has shown is lockstep-safe): that is input, not
  picture, and belongs to the controls work.
- **Not seen with a view selected:** death, the pause menu, the inventory, a shop, a
  dialogue, two local players, a net game, a vehicle.
