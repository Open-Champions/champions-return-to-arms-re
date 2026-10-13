# Views for the native build: overhead, action, chase, shoulder, first person

Started 2026-10-13. The owner asked "Is it possible to first person" and then made it the
main effort: the game "sick in first person, and multiple clean character views". This is
the camera system for the native build of Champions: Return to Arms (SLUS-20973 v2.00;
`docs/issues/native-app.md`, `native-graphics.md`). Every statement says whether it was
**Ran** (with what was seen) or only **Read**. Pictures are game output and stay under
`local/recomp-fp/pictures/`.

## STATE (rewritten at every step; read this first after a stop)

**2026-10-13 13:28 - base ready.**

- **Ran:** all five views in the first level (`hub`): the game's own camera is replaced for
  the length of the draw pass only, the game culls and draws for the new camera by its own
  code, sky and far ground included; easing between views; the camera stick turns (the
  game's own yaw) and looks up and down; the local player's model left out in first person;
  walking with the stick pushed up goes where the view looks. Pictures:
  `local/recomp-fp/pictures/base/hub-*.png` (1280 x 896).
- **Not yet run:** the tick-for-tick comparison per view (section 5), other levels, a
  fight, widescreen with a view, a window (only off-screen runs so far), wall pull-in on a
  level with walls, the settings file round trip.
- The patch is `tools/recomp/app/fpview.patch`; new files `tools/recomp/app/fpview.h`,
  `fpview.cpp`. Nothing in the shared tree compiles them until the patch is applied.
- My copy of the sources and my builds: `local/recomp-fp/` (`base` = `tools/recomp` as it
  stood 13:15, `src` = with the views, `root` = a stand-in workspace root whose
  `tools/recomp` is `src` and whose `local/recomp-out` holds my translation, objects and
  `bin/rta_app_fp`; `work` = scripts and test output).

Next: the tick comparison in every view; chase and shoulder on levels with walls (pull-in,
floor); first person on a corridor, a fight, a large outdoor level; then the views made
clean one by one.

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
  a level loaded, exactly one local player alive with an object. Otherwise the frame is the
  game's own (cutscene, dialogue, inventory, shop, death, two players on one machine, free
  camera) and the view eases back in afterwards from the game's camera.
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
| shoulder | 58 behind a point 64 up and 17 to the right | 60 | 8 | looks -55..+45 |
| first | 60 over the feet, 7 ahead; the player's model left out | 70 | 4 | looks -65..+65 |

Chase, shoulder and action pull in when the level is between the pivot and the camera (the
game's own `terrain_raycast` 0x18a5c0, the query its camera uses: in at once, out at 240
units a second) and stay 6 above the ground under the camera (`terrain_height` 0x183820).
Both queries advance the terrain visit stamp, as the game's own camera does per machine;
nothing else.

### For the two works that build on this: `fpview.h`

One header, nothing of the runtime in it. `fpview::view()` gives the frame's `View`: the
mode selected and shown, the blend, whether the frame fell back and why; eye, forward, up,
right, field of view, near and far of the camera the frame is drawn with; the game's own
camera of the frame (eye, axes, field of view, heading, zoom index, yaw word); the local
player (slot, object address, feet, head point, facing as angle and vector); the look yaw
and pitch; tick and frame number.

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

## 4. Controls: what a stick does in each view (Read, then Ran in the hub)

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
- The character does not turn with the view: it faces where it last ran or struck. In
  first person the view and the facing differ after strafing (the model is not shown, so
  it is not seen, but an attack goes along the facing). Turning the character with the
  view needs the simulation's help (a facing change is simulation state): not done here.

## 5. Does it change the game?

Not yet run. Planned: the rig comparison of `native-graphics.md` 1.3 (`rigcompare.py
boot-native --replay`, `fight3.rig`) with each view selected, and a native pair overhead
against each view with a script that also uses the camera stick, comparing the watch
columns and memory images.

## 6. Pictures

`local/recomp-fp/pictures/base/` (1280 x 896, 4:3, off screen, the first level at fixed
ticks): `hub-overhead.png`, `hub-action.png`, `hub-chase.png`, `hub-shoulder.png`,
`hub-first.png`, `hub-first-walk.png` (after walking "up"), `hub-first-turn.png` (camera
stick right), `hub-first-lookup.png` (camera stick up), the `-mid` ones 10 ticks into a
change of view.

Seen in them: the hub has a sky dome and distant mountains that the overhead view never
shows, and they hold up from the ground; the far ground is drawn to the horizon; the HUD
is where it was; in the action view the sky stops at a straight edge near the top of the
picture (the dome is built for a camera above it); in the shoulder view the character
fills a third of the picture (58 behind is too close for this model).
