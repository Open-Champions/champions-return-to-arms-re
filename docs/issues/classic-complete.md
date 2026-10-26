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
| [~] | Shops | Godot: the route did not reach the shop this round; **Read**: shop screens drawn correctly in Godot (`PROGRESS.md`), shop compared tick for tick natively (`native-proof.md` R3.2) |
| [~] | Save points, level-ups, deaths and restarts | Deaths: **Ran** online (4 deaths in the 4-copy room, in step). Save point, level-up, restart: **Read** (`native-proof.md` R3.2, 15 sessions identical to the original); not pictured in Classic this round |
| [x] | Cut scenes at level entry, boss introductions, the endings | **Ran**: 17 levels open on a scene, skipped with the game's own buttons in both programs; both bosses' introductions and both endings' closing scenes (with their text) the same as the emulator's; both endings end on the game's own save screen, as in the emulator |
| [x] | Bosses | **Ran**: `bossgood` and `bossevil` load with the boss and its bar; `bossgood` in an online room of three (section 4) |
| [x] | Classic online, 2 to 4 copies, Godot Classic + native + the Mac application | **Ran**: three rooms, through 2-3 level changes each, a boss level, forced relay, every pair in step (section 4) |
| [~] | 60 fps paced | Native **Ran**: 60.0 a second, 0 of ~300 pictures off the 60 grid in 11 of 13 levels measured cleanly; Godot **not settled**: measured at a load average of 200-500 from other work (section 5) |
| [ ] | Windows and Linux in Classic | **Read** only: the native program runs and plays online on both (`native-windows.md`, `native-linux.md`); no Classic campaign there this round |
| [ ] | A person playing it through | never done |

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
  agree likewise (`sheet-g2.png`, `sheet-g3.png`). One difference seen and not chased: the light shafts
  of some water levels (`islsm3b`, `watg2a`) look fainter in Godot.
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

Not fixed - for the owner:
1. **The native program does not find the art pack by itself**; Godot does (the Play-RTA folder). A
   player who never sets `art_pack` plays the native Classic with the game's own textures.
2. **The native boss-music director is on by default.** Inert without files; a Remastered feature by
   the portal's own mapping. Whether the native program should default to off is a decision.
3. **Godot Classic still loads the Elden Ring world materials** at start (about 0.5 s) though
   `er_world` is off; nothing of it is drawn.
4. **After an ending** the game stands in its save screen; a level asked for from there does not load
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

## How to repeat

```
python3 tools/recomp/app/build.py --as rta_app_classic
RTA_TOUR_APP=local/recomp-out/bin/rta_app_classic python3 tools/recomp/app/tour.py native campaign \
    --out local/classic/native --paced --skip disease0 --app-arg=--art-pack --app-arg=PACK
python3 tools/recomp/app/tour.py emu campaign --out local/classic/emu --skip disease0
python3 tools/recomp/app/tour.py rigscript campaign LEVELS... --out local/classic/g.rig --shots DIR --screens
#   (after tools/recomp/examples/boot-to-hub-ticks.rig), then the Godot scene:
#   main.gd -- --mode scene --edition classic --script FILE --frame-log FILE
RTA_GODOT_OUT=local/godot-classic python3 -B tools/play-net/roomparty.py local/classic/room \
    --copies app,godot,native,godot --native-window local/recomp-out/bin/rta_app_classic \
    --play 900 --level fire1,storm1,nit1 --play2 1200 --level-every 2400
```
