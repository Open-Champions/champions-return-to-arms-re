# Cut scenes and films in Remastered

Started 2026-10-26. The owner approved three things for Remastered: sharp films, the Elden Ring look on the players'
own figures in the game's cut scenes, and cinematic touches (wide framing, smooth 120 Hz camera, hold to skip).
Classic keeps the game's own films, framing and skip. Every statement says **Ran** (with what was seen) or **Read** /
**not run**. Nothing derived from the game or from Elden Ring is in the repository: the enlarged films, pictures, logs
and builds are under `local/` and the player's user data folder.

Builds: native `local/recomp-out/bin/rta_app_next` (fix set) and `rta_app_next_orig` (the disc's game with this code
linked, for the rig); Godot `local/godot-r29/` (`build.py all`, then `lib`, `extension`, `project`). Tests and pictures:
`local/cutscenes/`, `local/godot-r29/test/`.

## 1. Sharp films

**What the game's films are (Ran).** `film.cpp` now logs (`RTA_FILM_LOG=1`) what the game's film player hands the
host decoder: the developer's film at power-on is **seven separate MPEG-2 streams**, each fed whole in one
`sceMpegAddBs` after a `sceMpegReset` (60, 60, 60, 60, 60, 60, 50 pictures; 2.0 MB each, the first in `PORKO.LMP`, six in
`PORKO.SMG`). There is no other film on the disc (the endings and the title fly-over are in-engine).

**The key.** `film.cpp` names the film playing by the FNV-1a hash of the first 65,536 bytes of stream fed since the last
reset, and counts the pictures it hands out since then (display order). `rtag_film_now` / `RtaMachine.get_film()` give
both to the host; nothing reaches the game.

**The tool: `tools/install/films.py` (Ran).** Finds every stream on the player's own disc (a valid sequence header to its
sequence end, in `.LMP` / `.SMG` / `.M2V` / `.PSS` files; 0.2 s), names it by the same key - the seven keys it computes
are exactly the seven the game logged -, decodes it with ffmpeg (every picture, `-fps_mode passthrough`: 60/60/.../50,
the same counts as the game's decoder), enlarges with Real-ESRGAN (`realesrgan-ncnn-vulkan`, the official 2022-04-24
macOS release, already on this machine in the user's own files, unzipped to `local/upscaler/ncnn/`; model
`realesrgan-x4plus`, chosen over `realesr-animevideov3` and bicubic on one frame: `local/cutscenes/model/cmp.jpg` - the
anime model flattened the penguin's feathers), scales to 1344 lines (three times 448) and writes JPEG files under the
user data folder (`~/Library/Application Support/Play-RTA/films/<key>/00000.jpg`..., `manifest.json`; Windows
`%APPDATA%/Play-RTA/films`, Linux `~/.local/share/Play-RTA/films`). Without the upscaler it falls back to ffmpeg's lanczos
with a light sharpening and says so. Incremental (a manifest made the same way is kept). Ran: 8 streams (the seven
played and an unused 640 x 480 one), 470 pictures, 1920 x 1344, 172 MB, 1,324 s with the GPU shared with other agents'
games (about 3 s a picture).

**In Remastered (Ran, Godot r29).** `cinematic.gd` draws the enlarged copy of exactly the picture the game's decoder
handed out last, over the game's own picture, in the 4:3 place the game shows the film in (centred in a wide window);
pictures are read ahead on worker threads. The film itself is still the game's: its player, its timing (the
get-picture call's own pacing, `native-app.md` 10.3) and its sound - so it stays in step with the sound by
construction. `local/cutscenes/gf/{off,on3}/w-*.png` are the same blanks with the films off and on (unpaced,
deterministic): the same picture each time, aligned (`cmp-b.jpg`, `cmp-c.jpg`: original | enlarged). 432 of 439
pictures shown enlarged; the 7 others were the first picture of a stream while its copy was being read (the game's own
picture shows then). Classic (`--cinematic off`, or the portal's Classic) shows the originals.

**Found (Ran, measured, not changed):** Godot's own display of the film is darker than the stream's colours: mean
(56, 80, 108) over the film area where the stream's pictures decode to (94, 116, 135) (ffmpeg and `mpeg2.h` use the same
BT.601 conversion; the native program's film shows the stream's colours). The enlarged copy shows the stream's colours,
so it looks lighter than the Godot original. The darkening is in the Godot path of the game's 2-D picture (looks like the
sRGB curve applied once too often); not looked into here.

## 2. The Elden Ring look on the players in cut scenes

**Identity, not a guess (`er_layer.gd`, Ran).** A figure is a player's when the object whose animation state poses it
is a `Player` (vtable 0x511308 at +0x48) - the player itself or this machine's prediction copy - and its slot is
`Player +0x3c8`. The local player is found by the controls first (as before), then by this identity; the nearest-root
guess is used only when neither can decide and never for a figure that is not a player's while a cut scene runs (or
while the controls name a slot). A player whose state is not drawn is found by identity (the copy); a skeleton whose
state matches but whose owner is not that slot's Player is refused. `app er info` lists every person skeleton as
"player N" or "not a player".

- `bossevil`'s opening scene (`local/cutscenes/g/be3`): the player's own figure is in the scene and is **drawn fitted**
  (Iksar shaman in the necromancer set: `be3/fig.png`); the scene's knight (63 joints) is "not a player" and untouched.
- `dis2`'s scene (`g/ds1`): a **64-joint figure with a player's skeleton that is not a player** (and three 38-joint
  ones): refused - local skeleton -1, nothing dressed. This is the case that once took a story figure for the player.
- the hub: the 63-joint villager is "not a player".
- In the two-copy room (below) A drew both players fitted through the cut scene.
- First person: a cut scene's view is the game's camera (fallback), so the local player is drawn there too.

## 3. Cinematic touches

### Hold to skip (lockstep; `tools/recomp/app/cinematic.{h,cpp}`, `cinematic_hle.cpp`)

The game skips a cut scene when any player's lockstep row shows START pressed (`cut_runFrame` 0x199944, the loop at
0x199de4 sets `g_cutSkip`; Read in the disassembly). The fix-set translation now hands `cut_runFrame` to the application
(`hle-app.txt`, original emitted as `orig_00199944`): with the mode on, START's pressed bit is taken off every row for the
original call and put back on player 1's row only in the tick in which every player of the game (the count the game's
loop uses, 0x4d8ae0) has held START (the held word, +8) for 60 ticks; the rows are put back afterwards. The game's own
conditions stay its own (in a net game the two ending scenes `endgood` / `endbad` are not skipped before their 301st frame - every other scene may be skipped at once; no skip test in the front end, 0x41b510, or under the loading screen; corrected 2026-10-26 from the code at 0x199d68-0x199dd4). Counts live in
guest memory at 0xE1C00 (tick logs, the HUD); a hold that skipped must be released before it counts again. Mode off:
the original runs untouched.

A room option like Hardcore and aiming: a copy that wants it says bit 0x2000 of its fix-set word count (the portal's
Remastered bit) with the mode's figure folded in; `launch.cpp` launches a room only when every copy has it or none,
`net2_start` refuses a mixed room ("Not every copy in the room plays Remastered"), the room warning names it. Offline it
is the program's setting: `cinematic.skip = hold | tap`, `rta_app --cinematic hold`, `rtag_set_option("cinematic.skip")`;
Godot: Remastered (or `--cinematic on`) sets it, Classic sets `tap`.

- **Offline, native (Ran, `local/cutscenes/skip/n1`):** blood1's opening scene: a tap - held back; a half-second hold -
  held back; a full hold - skipped at frame 348, 60 ticks after the press (`sheet.jpg`). With `tap`
  (`skip/n2-tap`): the tap skipped at once, as the game does.
- **Offline, Godot (Ran, `g/c1`, `g/be3`):** the same, with the prompt "Hold START to skip" and a ring that fills.
- **Room of two Godot copies, both Remastered (Ran, `local/godot-r29/test/room29.py cs1 --level bossevil`):** both
  copies "hold to skip: on for this game". In bossevil's opening scene A held START alone for 90 ticks: no skip (prompt
  "1 / 2 holding", `pictures/a-cut-1-alone-holding.png`); B began holding at tick 1332 while A held again; the scene
  ended at **tick 1391 on both copies** - the tick B reached 60 (A at 97) (`a-cut-3-both-holding.png`, "2 / 2").
  Tick logs: **1,805 ticks compared, no shared column differs** once `g_cutFrame` is left out
  (`cs1/compare-nocutf.txt`); that column differs until the first scene of the game only: it is the front end's
  title fly-over clock left over on each machine, not lockstep state (it is equal from the scene's start on). The run
  ended with 21.5 million Godot errors at A's shutdown ("material is null", a 2.8 GB log, truncated): a scene of the
  drawer re-created after its release by the letterbox option; fixed (the option no longer creates a scene, and
  `cinematic.gd` stops when the machine has ended). **Second room run `cs2`** with the fix: A alone held 90 ticks, no
skip; the scene ended at tick 1373 on both copies; **1,768 ticks compared, no shared column differs** (without
`g_cutFrame`, as above); no Godot error at shutdown.
- **Review fixes (2026-10-26, review-codex items 1 and 3; mode figure "cinematic 2", block version 2).** Only the scene's
  own tick call (`cut_runFrame(0)`, 0x199930) counts; the load warm-up's `cut_runFrame(1)` (0x322ee8, a per-machine
  number of passes) and the front end's scenes (`g_inFrontend`) run the original untouched - no hold counted, no pressed
  word changed. The block's +0x18 holds the frame counted last plus one (0: none in this scene), so the first tick of a
  scene counts exactly once; a scene that ends in a tick clears it. A completed hold whose skip the game refuses is kept
  and the press offered again each tick; the release is required only once the game took the skip or the scene ended.
  Ran with native copies (`n2party.py` with hold input, `rta_app_reviewfix`): START held from 5 ticks before the level
  tick through bossevil's load into its opening scene - **3,212 ticks in step**, the cut-scene block a compared column,
  hold 1 at the scene's first tick on both (8,582 warm-up passes not counted), skipped at tick 1,662 on both; START
  pressed after the scene began and held past its frame 301 - **2,955 ticks in step**, skipped at tick 1,888 on both.
  The first run before the front-end change differed in the block's +0x18 only (the title fly-over's per-machine frame
  left in it). A synthetic probe of the real wrapper (10 / 20 / 3 / 40 warm-up passes, an ending scene refused until
  frame 301, release-before-next-scene, two calls in one frame) passes; the refused-skip path cannot be reached in a
  room short of the game's ending scenes.
- **Mode off, the rig (Ran):** `local/cutscenes/rig/check.py` (the fight session against the rig's log, the souls work's
  script) with `rta_app_next_orig`: overhead and first person **byte for byte** the reference reports (`off-over`,
  `off-first`).

### Wide framing (Ran)

In a cut scene the game paints its own letterbox: two black rectangles, top 42 and bottom 74 lines of 448 (the bottom
one carries the subtitles), drawn for a 4:3 picture. In Remastered the drawer leaves those two rectangles out (`RtaDrawer`
option `letterbox_off`: an untextured opaque black sprite draw whose every rectangle spans the picture's width as a band
at its top or bottom edge; 378 left out in `be3`) and `cinematic.gd` frames the scene itself: bars that slide in over
0.35 s to 2.0:1 of the game's picture and out when the scene ends. The scene is seen wider and centred; the subtitles
stay, over the picture (`g/be3/sheet.jpg`: two framings and a subtitle).

### Smooth camera at 120 Hz (written and run; the smoothness itself not measured)

At a display rate above 60 the pictures between game frames are normally carried on past the last frame
(extrapolated). In a cut scene they are now drawn a frame behind, between the two frames before (main.gd `tween_back`):
the tick picture shows the frame before (`redraw(-1)`), the pictures after it the way to the new one - the same
`interpolate_with(.., 1 + t)` of the camera and `rta_tween` of the kept meshes, ER figures and remastered models, with
t - 1. A camera that eases to a stop cannot overshoot. Ran paced at 120 Hz (`g/p1`..`p4`, `RTA_CINE_LOG` camera per
picture, `camstat.py`, `overshoot.py`): no backward step, no overshoot in either mode - but the machine carried about ten
other agents' games and gave 1 of 5 pictures between frames, so the comparison says nothing about smoothness; to be
measured on a quiet machine. `RTA_CINE_BETWEEN=0` turns it off.

## Found on the way (not mine to fix)

- **Hardcore's block overlaps aiming's block.** `soulscombat.h` BLOCK_SIZE 0xc80 from 0xE0800 reaches 0xE147F; its
  attributes part (`st_off`, 0x600 + slot x 0x80) begins at 0xE0E00 = `fpaim.h` AIM_BASE, whose header (magic, version,
  mode) is written there. Both modes are on in Remastered. Commit e184471 moved the aim block for this very reason; the
  stats round grew the souls block over it again. The cut-scene block is put at 0xE1C00, clear of both.

## Changed (tracked)

- New: `tools/recomp/app/cinematic.h`, `cinematic.cpp`, `cinematic_hle.cpp`, `tools/install/films.py`,
  `tools/godot/project/cinematic.gd`, this file.
- `tools/recomp/app/film.cpp` (the key, the picture, `rta_film_now`, `RTA_FILM_LOG`), `app_rt.{h,cpp}` (`film_now`),
  `hle-app.txt` (0x199944), `app_main.cpp` (blank, `--cinematic`, `app cine`, figures), `settings.h` (`cinematic.*`),
  `build.py`, `build_win.py` (the `--mac` list).
- `tools/recomp/net2/hooks.h` (`cine_*`), `launch.cpp` (describe, room check, end), `session.cpp` (warning, start refusal).
- `tools/godot/lib/rtag.{h,cpp}` (`rtag_film_now`, `cinematic.skip`, `has("cinematic")`, `app cine`, info `cine_want/on`,
  copy bit), `tools/godot/build.py` (export, `RTAG_HAVE_CINE`), `extension/src/rta_library.h`, `rta_machine.{h,cpp}`
  (`get_film`), `rta_drawer.{h,cpp}` (`letterbox_off`, `get_letterbox_left_out`, `get_scene_camera`), `rta_scene.cpp`
  (the option, the camera shown).
- `tools/godot/project/main.gd` (`--cinematic`, the node, `_apply_cinematic`, `tween_back`, `app cinematic`),
  `er_layer.gd` (identity, info, first person in a fallback view).

Other agents changed some of the same files at the same time (party scaling and 8 players: `app/build.py`,
`hle-app.txt`, `app_main.cpp`; the world and souls work in the Godot files): only the hunks named above are this work's.

## Not done

- Windows and Linux: `cinematic.cpp` is not in their app lists (their programs, `win_main.cpp` / `linux_main.cpp`, do not
  call it; the translation's weak `fn_00199944` runs the original there, so the skip stays the game's). The Godot
  libraries of `build_lib_win.py` / `build_lib_linux.py` get no `RTAG_HAVE_CINE`: Remastered there skips as Classic.
- The skip prompt names START (Return on the keyboard); no controller glyphs.
- Films: the copy of a stream's first picture can be late (the game's picture shows for that one picture); a prefetch
  of the next stream's first pictures would close it.
- The 120 Hz smoothness on a quiet machine (above).
