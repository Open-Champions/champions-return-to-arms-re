# The translated game inside Godot (spike)

Started 2026-10-13. Question: can the statically recompiled game (`native-recomp.md`,
`native-app.md`) run inside Godot as its game logic, with Godot doing window, input, sound
and - step by step - the drawing? Everything here says **Ran** (with what was seen) or
**Read**. Kept current as the work goes; a successor needs only this file.

Nothing derived from the game is in the repository. `tools/godot/` holds glue, build
scripts, the Godot project's scripts and shaders. The translated code, the libraries, the
staged project, exported applications, pictures and logs are under `local/godot-spike/`.

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

### State (23:45)

- **net2 through the library: done and run** (below, "A room of our own").  One hunk in `recomp.patch` (net2/launch.cpp).
- **Ceilings and skirts drawn by Godot**: code in (`extension/src/rta_fill.cpp`, `shaders/fill.gdshader`, look `fill`);
  first pictures being made (`r4/fill2/`).
- **The game's own lights as Godot lights**: code in (`RtaMachine.get_lights`, look `lights`); being looked at.
- Character card, persistent meshes: not started.

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
