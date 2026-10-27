# Classic: done?

The goal: **Classic** - the original *Champions: Return to Arms*, faithful - in the Godot portal's
Classic mode and in the native program, on macOS, Windows and Linux, online. Classic keeps the
game's own HUD, menus, overhead camera, combat, music and cut scenes; it adds only the art pack and
a steady 60 frames a second (`DIRECTION.md`, `native-portal.md` "the first screen").

Every statement says **Ran** (with what was seen) or **Read** (from another document, not run here).
Started 2026-10-26. Evidence under `local/classic/` (not tracked): pictures, logs, tick logs, sheets.

## The checklist

| | Item | State |
|---|---|---|
| [x] | Every campaign level loads in the native program, Classic settings | **Ran**: 82 of 82 reachable levels (13 act lists + the mission table's medal and bonus levels) |
| [x] | ... in the Godot scene with the portal's Classic choice | **Ran**: 81 of 82 (the last, `endgood`, asked for while the previous ending's save screen was up: see 3) |
| [x] | Pictures match the original (emulator, no fix set) level by level | **Ran**: native against the emulator at 82 levels; Godot against native at 81 |
| [x] | No Remastered feature in force, level by level | **Ran**: native 95 of 95 level visits; Godot 81 of 81 dumps (section 2) |
| [x] | The game's own HUD, pause menu, options, bag pages, map, dialogue | **Ran** (Godot, hub); native **Read** (`tour.py screens`, `native-app.md`) |
| [x] | Shops | **Ran** (section 6): the first level's shop - the keeper's lines, Enter Shop, the Buy / Sell menu, the buy list, a purchase, the sell list - in both programs, the same picture at the same tick |
| [x] | Save points, level-ups, deaths and restarts | **Ran** (section 6): the save point (Check Point Saved, Save Game, Save Successful), a level-up given the game's own way (the message, the screen's ability and skill pages), a death and the restart, pictured in both programs and the same; deaths also online (section 4) |
| [x] | Cut scenes at level entry, boss introductions, the endings | **Ran**: 17 levels open on a scene, skipped with the game's own buttons in both programs; both bosses' introductions and both endings' closing scenes (with their text) the same as the emulator's; both endings end on the game's own save screen, as in the emulator |
| [x] | Bosses | **Ran**: `bossgood` and `bossevil` load with the boss and its bar; `bossgood` in an online room of three (section 4) |
| [x] | Classic online, 2 to 4 copies, Godot Classic + native + the Mac application | **Ran**: three rooms, through 2-3 level changes each, a boss level, forced relay, every pair in step (section 4) |
| [x] | The art pack and Classic defaults in the native program | **Ran** (section 7): found by itself where Godot finds it; boss music off in Classic; Godot Classic no longer reads the Elden Ring materials |
| [x] | 60 fps paced | Native **Ran**: 60.0 a second, 0 of ~300 pictures off the 60 grid in 11 of 13 levels measured cleanly; Godot **Ran on a quiet machine** (2026-10-26, [fps-verdict](fps-verdict.md); load under 20 and the GPU idle at each start): Classic at 3024 x 1964, hub, fire1, arachna1, water1, drunare, islsm3b, fearboss, bossgood, storm5, nitdung2, wate2c, twice: 59.9-60.0 game frames a second in every level, the slowest second 58-60, 0-7 intervals over 25 ms a level |
| [~] | Windows and Linux in Classic | **Ran** (section 8): both built from this tree; Linux aarch64 and x86-64 (container, Xvfb) take the 11 tick-keyed `--plain` pictures - the same scenes as the Mac's, a rounding difference of the GL driver only - and the rig comparison byte for byte; Windows built and linked only (no wine here); no Classic campaign on either |
| [~] | Played through like a tester | **Ran** (2026-10-27, [playtest-classic](playtest-classic.md)): Godot Classic through the portal's card and the native program driven by play - new game, the hub's mission flow, Act 1 fought through by walking, fighting and the levels' own exits (blood1, strife to its boss), the other Act 1 levels and acts 2-8 level by level (45 levels in all, bosses fought), deaths, level-ups, chests, the save point and a load after a restart, menus, keyboard and controller, a 2-copy online room played (14,198 ticks in step); 9 glitches found, 4 of ours fixed (garbled woven text and level banners in both programs, the art pack's font in Godot, the hub's cloud disc in Godot), 3 open; acts 9-12 not played, nobody human yet |

## 1. The campaign walk (Ran)

`tools/recomp/app/tour.py native|emu campaign` (new) reads the 13 act lists (`g_actLevelTables`
0x4f8e48) and the mission table (`g_missionTable` 0x4fe540: story, evil story, medal round, bonus
level) from the running game, then asks for every level in that order the way the sweeps do (the
name into `g_pendingLevel`), answers what holds the game, takes the picture on arrival and after 300
blanks of play, and reads what is in force. `tour.py rigscript campaign` writes the same route as a
script for the Godot scene (it has no control socket); `--screens` adds the hub's screens.
`main.gd` gained `--edition classic|remastered` (the portal's choice without the portal, exactly as
`handover.gd` maps it) and the script line `app effective FILE` (`effective_settings()` as JSON).

- Native: the program built for this (`build.py --as rta_app_classic`, fix set 9ac29719), the art pack,
  paced. Godot: the project staged from the last commit plus the `main.gd` change (other work in
  progress in the tree left out), scene mode, `--edition classic`, paced, with a frame log.
- The emulator reference: `tour.py emu campaign`, the Play! build with no patch section.
- **82 levels** reachable: 74 act-list rows less one, plus 9 medal rounds. All load in 2.7-3.5 s
  (medal rounds 7.5 s) natively.
- **`disease0` is left out**: an act-list row that no exit and no mission row names (the level names
  of every other archive and the mission table were searched); asked for directly it hangs the
  original game in the emulator in the same way, and the native program (it hung once, crashed once
  in the loader's thread switch while the machine stood at a load average above 100). No player can
  get there.
- Pictures: native and emulator agree level for level (`local/classic/sheet-c1.png`, `-c2`, `-c3`:
  the same geometry, light, HUD, level-name banner, prompts and objective counters); Godot and native
  agree likewise (`sheet-g2.png`, `sheet-g3.png`). The light shafts of some water levels (`islsm3b`,
  `watg2a`) were fainter in Godot: found and fixed (section 7).
- No complaint in the native program's output at any level; render counters: `tex_missing` rose in 4
  levels (1 to 938 lookups), nothing else.

## 2. What is in force (Ran)

- Native, at every one of 95 level visits: `souls: off`, `aim: off`, `cinematic: hold to skip off`,
  `view: selected overhead, shown overhead`; the boss-music director `on, 0 tracks` (it plays only files
  a player puts in `<data>/music/boss/`).
- Godot, 81 dumps (`app effective`), all identical: edition classic, souls 0, aim 0, cine 0, view
  overhead and locked, HUD `original`, boss music off, display rate 60 at one picture a game frame,
  the art pack (122,205 pictures), every Classic look key off (sky, fog, sun, lamp, bloom, grade,
  foliage, fill, lights, backdrop, contact, models, preset, er_models, er_creatures, remaster_models,
  er_world), no preset applied, and the copy `fix=9ac29719,words=189` - the original fix set's own
  description. `effective_settings()` now lists every key Classic turns off (it left out four).

## 3. Faults

Fixed (small): the campaign driver's pacing read (it counted a 120 Hz display's normal two refreshes
as late, and its picture write fell inside the measured blanks); `effective_settings()`'s missing keys.

Fixed since (section 7): the native program finds the art pack by itself; its boss music is off in
Classic; Godot Classic no longer reads the Elden Ring world materials at start; Godot's water-level
light shafts are as bright as the native program's.

Not a fault:
1. **After an ending** the game stands in its save screen; a level asked for from there does not load
   (as in the emulator). Not a fault of the port; the route asked for `endgood` from there.

## 4. Online (Ran)

`tools/play-net/roomparty.py` gained a `godot` copy (the Godot scene with the same script and runtime
options as a native copy, `--edition classic`) and several levels in a row (`--level A,B,C`,
`--level-every`). A room service of the run's own on this Mac; drawn input.

| Run | Copies (host first) | Levels | Ticks in step, every pair |
|---|---|---|---|
| `room1` | Godot Classic, native, Mac application | hub > blood1 > boar1 | 4,570 - 4,577 |
| `room2` | native, Mac application, Godot Classic; one copy forced onto the relay | hub > valor > bossgood (the last boss) | 4,725 - 4,736 |
| `room3` | Mac application, Godot Classic, native, Godot Classic | hub > fire1 > storm1 > nit1, 4 deaths | 6,872 - 6,878, all 6 pairs |

Every run: all copies launched and finished, "no shared column differs", the application quit with
exit 0. The Godot copy described itself as `set=9ac29719 words=189`. Load average 250-500.

## 5. Pacing

- Native (`app stats`, display 120 Hz, a picture should stand two refreshes): 13 levels measured with
  the picture write outside the window: 60.0 a second, 0 to 2 of ~302 off the grid, longest 16.6-26.7
  ms; the bosses' levels 3-4 off, longest 66-112 ms. The earlier 82-level walk had its picture write
  inside the window (57-59.6 a second, one stall each) - not a measure of the game.
- Godot (frame log, game frames per second over 300 after each level's start): average 55 a second,
  3 of 82 levels with no late frame, the worst water and medal levels 25-47 a second - while my own
  online rooms and other work held the load average at 200-500. Not a verdict; to be measured again
  on a quiet machine.

## 6. Shop, save point, level-up, death (Ran, 2026-10-26)

`tour.py ... campaign --moments` (both the socket route and `rigscript`) visits, before the levels,
what a player meets between them (`MOMENTS` in `tour.py`): the first level's shop (the proof's town
session's place and presses: the keeper's lines, Enter Shop, Buy, a purchase, Sell), its save point
(the card check, a new save), a level-up (the game's own `player_giveExp` 0x1d3150 asked at a
vertical blank for the experience to the end of level 1 - the script's `call`, now also a command of
the native control socket - then select: the screen's ability page, three points, the skill page)
and a death in `blood1` (invulnerability off, hit points 1, a large pending damage on the player
object, which `Player_processDamage` takes off: the fall, the fade, the restart at full hit points).

The same rig script (`tools/recomp/examples/boot-to-hub-ticks.rig` + the moments) run by the
native program (`rta_app --script`, the art pack, 640x448) and by the Godot scene (`--edition
classic`, the project with this round's changes): **25 pictures each, the same moment in both**
(`local/classic/moments/sheet-native-godot.png`): every menu, its text and figures (200,000 gold,
198,268 after the purchase; "Save Successful"; "Press the SELECT button to Level Up"; 3 ability
points, then 1 skill point), the HUD, the fall and the restart. Both printed the same state at every
picture (level, pause flag, hit points, level 1 -> 2, experience 0 -> 1,150; the death at frame
6,242 in both).

## 7. This round's fixes (Ran, 2026-10-26)

- **Native art pack** (`app/settings.h` `find_art_pack`, the three programs' settings step): with no
  `--art-pack`, the pack is found as `main.gd _art_pack_folder` finds it - `$RTA_ART_PACK`, else the
  settings file's `art_pack`, else the Play-RTA folder's `textures/` (macOS `~/Library/Application
  Support/Play-RTA/textures`, Windows `%APPDATA%\Play-RTA\textures`, Linux
  `~/.local/share/Play-RTA/textures`) when it is there. `none` / `off` (command line, variable or
  file) keeps the game's own art; `--plain` and the measuring runs (`--offscreen`) look for nothing,
  so the tick-keyed pictures of `native-app.md` 12 and 13 stay the game's own art. Ran, a fresh data
  folder: no option -> the Play-RTA pack (122,205 pictures); `--art-pack none` and
  `RTA_ART_PACK=none` -> none.
- **Native boss music** (`bossmusic.cpp`): `music.boss = auto` is the new default: on when a
  Remastered mode is wanted (Hardcore `combat.mode`, aiming `combat.aim`), off in Classic; `on` /
  `off` as before. Ran: `app music info` says `auto, off` without options, `auto, on` with
  `--combat hardcore`. The launchers in the game folder need no change: the Classic ones start
  without Hardcore (off), the Hardcore one with it (on); they start `bin/rta_app`, which takes this
  when it is next rebuilt.
- **Godot Classic start** (`scene_view.gd`): the Elden Ring world layer (`er_world.gd`) is made only
  while `look.er_world` is on - never in Classic, and at the first frame after a switch to
  Remastered (`clear_look` puts the key back on). Ran: the Classic runs print no `er world` line
  (before: "8 materials ... in 456 ms" at every start); `app look er_world on` in a Classic run reads
  them then ("11 materials ... in 483 ms") and the layer goes on for the level.
- **Light shafts** (`rta_drawer.cpp`, `rta_scene.cpp`, `gs_draw.gdshaderinc`, `scene_view.gd`): a
  Godot draw difference. Forward+ blends in linear light; the 3-D world was the one surface still
  blended so, and an additive draw over a dark one (a shaft over dark water, the mist) comes out
  fainter than the GS's sum of stored values. While the portal's Classic look is in force (every key
  it turns off is off, so nothing of Godot's light, sky or models is in the scene) the world is now
  drawn and blended in stored values as the other surfaces are (`stored_world`; a fused level batch's
  two passes added in stored values too). Ran, the same script in three runs at 960x720: the shaft
  corner of `watg2a` averages 44/68/72 natively, 40/57/60 blended in linear light
  (`RTA_GODOT_LINEAR_BLEND=1`), 44/68/72 now; the whole picture's mean difference from the native
  one falls from 2.9 to 0.6 (`watg2a`) and from 1.8 to 0.8 (`islsm3b`)
  (`local/classic/shafts/sheet-shafts.png`).

Checks of this round:
- `native-app.md` 12/13's standing checks on the new program against one built from the same tree
  without this round's changes: the rig comparison (`s12/rig.sh`, the unpatched translation, default
  picture and `--plain`) **the same as `merge/rig-final-compare.txt`, line for line**, both; the 11
  tick-keyed pictures with `--plain` **11 of 11 identical**; the default pictures differ in a few
  pixels (1-13 per picture) between my program and the baseline - and as much between two runs of
  the baseline itself (7 of 11 differ), so that is the machine (multisampled pictures under a load
  average of 100+), not the change.
- An online room (`roomparty.py`, `local/classic/mine/room-cc`): Godot Classic (this round's project)
  as host, this round's native program, the Mac application; hub > blood1 > boar1: **every pair in
  step** (5,358 - 5,363 ticks), all three launched and finished. The Mac application, after the other
  two had left, ended with `recursive_mutex lock failed` in its teardown (exit -6): found and fixed in
  section 8.
- Not built here: the Windows and Linux programs carry the same settings step (`win_main.cpp`,
  `linux_main.cpp`); `settings.h` picks the place per system.

## 8. The Mac application's quit; Windows and Linux (Ran, 2026-10-26)

**"The Mac application"** of `roomparty.py` is the Play! build with this project's patch and
`tools/play-net/src` (`--app`, default `local/app-rv/build/Source/ui_qt/Play.app/Contents/MacOS/Play`).
Two faults, one after the other:

- **`recursive_mutex lock failed`** (the run of section 7): that default build was from
  2026-10-14 03:52, before the fix of `app-rendezvous.md` 9 (net2's lock made by `CRoom`'s
  constructor, the session closed in `Detach`); the crash report's stack is `~CRoom` <- `~CState` <-
  `exit`. Rebuilt from the tree's sources (`tools/play-net/src`, `tools/recomp/net2` as committed):
  the line went, every quit prints "room: the session is closed (the application ends)".
- **`mutex lock failed: Invalid argument`**, then 1 quit in 3 (`local/classic/room-quit`, run 1;
  the same stack in two earlier crash reports of the day and in the test matrix's F1): the
  display clock (`RtaMac.mm`) starts a CoreVideo display link whose thread calls `OnRefresh`
  60-120 times a second and was never stopped; `OnRefresh` locks `g_tickMutex`, a namespace-scope
  static. At `exit` the static went while the link's thread still ran: a destroyed mutex,
  `EINVAL`, `std::terminate`. A race, hence 1 in 3. **Fix** (`tools/play-net/src/RtaMac.mm` only;
  nothing in `tools/recomp/net2` or `tools/rendezvous`): the lock and its condition are made on
  the heap and never destroyed; `StartDisplayClock` registers an `atexit` step (after those
  objects exist, so it runs before any static of the file goes) that clears `g_running` and calls
  `CVDisplayLinkStop`, which returns when the link's thread has left its callback; `OnRefresh`
  returns at once when `g_running` is off.

**Ran** (`local/classic/room-quit2`, the same room as section 7: Godot Classic host, `rta_app_cc`,
the rebuilt application; hub > blood1 > boar1): **4 runs, every pair in step** (5,154 - 5,493
ticks), **4 of 4 quits clean** - exit 0, the session closed, no `mutex` line - after the other two
had left. Neither the native program nor the Godot library contains `RtaMac.mm`, so lockstep and
mode-off are untouched by it (and see below).

**Windows** (`build_win.py`, clang for `x86_64-w64-mingw32`, the tree as it stands): `rta_app.exe`,
`rta_native.exe`, `fpcheck.exe`, `pnghash.exe` compiled and linked (PE32+ x86-64; Windows system
DLLs and the UCRT only); the exe carries the settings step of section 7 (`RTA_ART_PACK`,
`music.boss`). Not run: no wine on this machine.

**Linux** (`build_linux.py --docker both --original`, the colima `rta` profile, Ubuntu 24.04):
`rta_app`, `rta_app_orig`, `rta_native`, `fpcheck` for aarch64 and x86-64. **Ran** in the
container under Xvfb (Mesa llvmpipe):
- the 11 tick-keyed pictures of `native-app.md` 12/13 (`s12/mkdet.py`'s route, `--plain
  --offscreen --unpaced`, 1280 x 896) against this round's Mac program's (`s12/det/cc-plain-fast`):
  **the same scene at every tick** (title, hub, the fight in valor;
  `local/classic/linux-det/sheet-mac-linux-a64.png`); not the same bytes - the drivers round
  differently: mean difference 1.1 (aarch64) and 0.25 (x86-64) of 255, pixels off by more than 16:
  0.002 - 0.18 %. The rig comparison (`rta_app_orig --plain`, the controller rows replayed):
  **`merge/rig-final-compare.txt` line for line on both** (`linux/rig/cc-a64`, `cc-x64`). A
  script there needs `names.tsv` and `symbols/` beside the program; the x86-64 folder lacked them
  (copied from the aarch64 one).

Left: Windows run (a Windows machine or wine), a Classic campaign on Windows and Linux, a person
playing it. Played by a driver since: `playtest-classic.md`.

## How to repeat

```
python3 tools/recomp/app/build.py --as rta_app_classic
RTA_TOUR_APP=local/recomp-out/bin/rta_app_classic python3 tools/recomp/app/tour.py native campaign \
    --out local/classic/native --paced --skip disease0 --app-arg=--art-pack --app-arg=PACK
python3 tools/recomp/app/tour.py emu campaign --out local/classic/emu --skip disease0
python3 tools/recomp/app/tour.py rigscript campaign LEVELS... --out local/classic/g.rig --shots DIR --screens
#   (after tools/recomp/examples/boot-to-hub-ticks.rig), then the Godot scene:
#   main.gd -- --mode scene --edition classic --script FILE --frame-log FILE
python3 tools/recomp/app/tour.py rigscript campaign --moments --out local/classic/moments/tail.rig --shots DIR
#   after boot-to-hub-ticks.rig: rta_app --script FILE --art-pack PACK, and the Godot scene with the same FILE
RTA_GODOT_OUT=local/godot-classic python3 -B tools/play-net/roomparty.py local/classic/room \
    --copies app,godot,native,godot --native-window local/recomp-out/bin/rta_app_classic \
    --play 900 --level fire1,storm1,nit1 --play2 1200 --level-every 2400
# section 8: the application rebuilt from tools/play-net/src (local/app-rv/sync.sh), then
RTA_GODOT_OUT=local/godot-classic python3 -B tools/play-net/roomparty.py local/classic/room-quit2 \
    --copies godot,native,app --native-window local/recomp-out/bin/rta_app_cc --play 1600 \
    --level blood1,boar1 --level-every 2400 --play2 600 --runs 4
python3 tools/recomp/app/build_win.py; python3 tools/recomp/app/build_linux.py --docker both --original
local/recomp-out/linux/lin.sh arm64|amd64 NAME rta_app --offscreen --unpaced --plain --size 1280x896 \
    --data D --script ROUTE -- --opt sound-clock=machine      # ROUTE: s12/mkdet.py D
```
