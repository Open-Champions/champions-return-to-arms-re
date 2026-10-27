# Remastered: done?

The goal: **Remastered** at 100 % - the portal's Remastered choice in Godot with every feature on (Hardcore with
attributes, spellbook, weapons, flasks and the death drop; the five views and aiming where you look; the fitted Elden
Ring armour, the remastered models, the Elden Ring world layer and boss music from the owner's own Elden Ring files;
cut scenes in wide framing with hold-to-skip; 60 frames a second or more, 120 where the display allows), through the
whole campaign to an ending, and online with two to four copies (`DIRECTION.md`).

Every statement says **Ran** (with what was seen) or **Read**. Started and run 2026-10-26 on one Apple-silicon Mac
(3024 x 1964, 120 Hz) that other agents' Godot and native runs shared all day: the load average was 11-19 at its
quietest and 40-450 for most of the runs; frame-rate figures below are given with the load they were taken at.
Evidence under `local/godot-remaster-check/` (not tracked): the build, routes, logs, pictures, sheets, tick logs.

## The checklist

| | Item | State |
|---|---|---|
| [x] | Remastered from the portal's first screen | **Ran**: the Remastered card's **Play** (alone) pressed as a player presses it (the portal in the test window, `shots.gd` scenario `solo`, new); effective settings: edition remastered, Hardcore on, aim look, hold-to-skip on, HUD new, boss music with 82 Elden Ring tracks, `er_models` / `er_creatures` on, cleaner and remastered models on, art pack 122,205 pictures, display rate auto at 2 pictures a game frame (`campaign/*/portal/solo-01-effective.json`). The portal's own note said "Not run: Play (alone) from a card into a level" - now run |
| [x] | Every story level loads, in order, to an ending | **Ran**: 54 levels of the good path from `blood1` to `fearboss` and `endgood` (the order of the executable's level and mission tables; runs `c1`, `c2-1`, `c3`), each by the game's own level request; then the evil branch and the bonus and medal levels - drundar boar1 blomedal innpit innmedal wate2a wate2b wate2c watmedal watbonus tormedal torbonus swamp2 dismedal disbonus valmedal honor2 firmedal firbonus stomedal stobonus fay1 faybonus nitmedal nitbonus nitbon2 bossevil endbad (`c4`, `c5`): all 28 load; with the good path every level of the Classic check's list (`classic-complete.md`) plus `fearboss`. Three requests in the long runs brought back a level instead (`honor` -> `fire1`, `nitdung1` -> `nitdung2`, `nitbon2` -> `bossevil`); all three levels loaded and were checked in runs of their own (`c3`, `c5`). `endgood` plays its closing scene and ends on the game's own save screen, as the original does (native program the same, below); two crosses later the portal is back in front ("the session is over (frontend)", `c2-2`); `endbad` the same (`c4-2`) |
| [x] | Hardcore combat in every level | **Ran**: in each level ten rounds of the mode's test aid (the player beside the nearest living creature), lock-on, light, heavy, dodge, block; over the long run 254 hits on creatures, 1,582 hits taken (155 dodged), 7 staggers, 3 backstabs, 6 guard counters, 392 swings cancelled by a dodge, 3 heavies interrupted, 37 flasks drunk and 23 refills at save points, 9 death drops, 4 picked up again (4,763 gold), 5,747 gold lost by dying again, 5 upgrade materials dropped |
| [x] | Stats, spellbook, level-ups, weapons, the save point | **Ran** (`s1`, `valor`): 20,000 experience through the game's own `player_giveExp` (level 1 -> 9), the character screen opened at the save point, 5 points spent, 3 spell-slot changes, the weapon upgraded +1 with gold and materials (damage 120 -> 135 %), the save point used and a save written to the card through the game's own card screens. In the long run (`c2-1`) the same screen was refused: the player had walked away from the save point by then (by design: the mode's screen opens at save points) |
| [x] | Spells and aimed projectiles | **Ran** (section 10.3): in Godot with the Remastered options, first person in `valor`: an Erudite Wizard's Shock of Frost cast three times, each bolt leaving at the look's pitch exactly (+13.6, +0.4, +10.3 degrees), 3 spell hits on the boar; a Wood Elf Ranger's four arrows at +13.6, +0.4, -11.1 and +10.3 degrees, each at the look's pitch exactly; the native program the same numbers. The campaign check had cast none: its route pressed only the first skill button, which has no spell for the classes played |
| [x] | All five views | **Ran**: overhead, action, chase, shoulder, first person pictured in every level (`campaign/*/pictures/LEVEL-view-*.png`). The black pictures in some of them: the game's own blank after a load (not the view change), and a look kept from one level to the next, now started level at every level (section 10.1, 10.2) |
| [x] | Fitted armour, remastered models, the world layer | **Ran**: the Elden Ring outfit fitted on the player and creatures drawn as Elden Ring enemies in every level (`er info`: demi-humans, trolls, nobles, skeletons, boars, soldiers); 204 of the game's figures baked as remastered models over the long run; the world layer on in all 53 levels it was asked in |
| [x] | Boss music | **Ran**: the director took the fight over (state playing / leaving, an Elden Ring track, the game's music at 0) in `islsm1`, `islsm3b`, `fire5`, `storm4`, `storm5`, `bossgood` (the last boss's bar up), `fearboss`, `blomedal`, `valmedal`, `honor2`, `nitbon2` and `bossevil`; back to the game's music after |
| [x] | Cut scenes: wide framing, hold to skip | **Ran**: `blood1`'s, `dis2`'s and `bossevil`'s opening scenes: a 75-tick hold of START skipped them (scenes skipped 1, 2; taps held back); the game's letterbox left out and the scene framed by the host's bars (`blood1-cut-wide.png`); the endings' closing scenes framed the same. Sharp films: not reached in this route (the power-on films are tapped through by the boot script) |
| [x] | Shops | **Ran**: the hub's shop through the dialogue, the Buy list, a tab, out (`c1/pictures/hub-shop-*.png`) |
| [x] | Bosses | **Ran**: every boss level loaded with its boss (boss bar in `bossgood`, boss music above) and fought by the route; the first boss of the good path, `islsm1`'s Broon (1,714 hit points), killed through the portal in Hardcore (boss music on, the kill, the music handed back) and in Godot with Hardcore off; native the same ticks (section 10.5). The other bosses were not killed one by one |
| [~] | 60 fps paced, 120 where possible, per level | **Mostly met** on a quiet machine (2026-10-26, [fps-verdict](fps-verdict.md): load and GPU gated, 3024 x 1964, every feature on, display auto = 120 Hz, eleven levels twice): 60 in 9 of 11 levels in one run (59.7-60.0, 85-103 pictures a second) and 5 of 11 in the other; **not** `arachna1` (50: the GPU, 4x multisampling at full size) and `wate2c` (40-53 at the end of a long session: the main thread). Fixed on the way: the game ran 63-66 a second at 120 Hz (the pacing dropped part of a refresh at every game frame), and pictures between game frames are held back while the GPU is behind. The earlier figures (fire1 and bossgood 38) were measured with other programs holding the GPU |
| [x] | No script or shader errors | **Ran**: no SCRIPT ERROR, SHADER ERROR or Parse Error in any run's output (campaign, rooms); the test window's "unknown option" warnings fixed (bug 8). A later commit (`e1d87ed`) brought one back in rooms - `model_remaster.gd` reading a figure's `name` that is not always there, 3,063 times in a two-copy room - fixed (section 8) |
| [x] | Pictures per level | **Ran**: about 12 per level (arrival, HUD window picture, five views, end), sheets in `local/godot-remaster-check/` |
| [x] | Remastered online, 2 copies through the portal | **Ran** (`online/r2a`): two portals, both Remastered by their cards, friends, room, Start; hub -> `drunare` -> `valor` -> `arachna1`, deaths and the reload; **6,467 ticks, no shared column differs** (the cut-scene clock column `cutf` left out: the front end's title fly-over clock, as `native-cutscenes.md` notes); copy A crashed at quit (bug 4) |
| [x] | Remastered online, 3 and 4 copies | **Ran** (`online/r3a`, `r4a`: Godot copies with the Remastered options on the command line, launched by `n2party.py` through a service on this Mac): 3 copies 6,131 / 6,131 / 6,143 ticks every pair in step, 4 copies 6,038-6,045 ticks every pair in step; hub -> `drunare` -> `valor` -> `arachna1`, 6 and 8 deaths, 2 reloads after everybody died; Hardcore, aiming and hold-to-skip "ON (a room's game)" on every copy. Then **through the portals** (section 10.6): four portals, each Remastered by its card, in one room of a rendezvous service on 127.0.0.1 (friends, an invitation, two in by the room's code, the game's own character screens, Start): 6,344-6,352 ticks, every pair in step through hub -> `drunare` -> `valor` -> `arachna1`; three portals the same |
| [x] | Long sessions draw cleanly | **Ran** after the fix (section 9): one Remastered session through the portal over 81 levels and both paths to `endgood`, and a Classic session over the 54 levels of the good path - no black build-up (bug 1, fixed) |
| [ ] | A person playing it through | never done |

## 1. How it was run

- **Build.** The last commit at the start (`8490744`) in a clean worktree (other agents' uncommitted Godot work left
  out), `RTA_GODOT_OUT=local/godot-remaster-check`, `build.py all` (library, extension, project), `run.py import`.
  Godot 4.5.2. The level presets made by `presets.py` (round 7's) copied into it - see bug 3.
- **Route** (`campaign/mkroute.py`): power-on -> the game's own front end and character screens -> the hub and its
  shop, then per level: the level asked for by name (`g_pendingLevel`, as every sweep does), the arrival, the opening
  scene (pictured; held to skip where one was known), the HUD, the five views, aiming in first person, the Hardcore
  round, a flask, a walk, per-level marks in the frame log and `--speed-log 60`. `valor`: level-ups, the character
  screen, the upgrade, the save point and the card. Driven through the portal: `campaign/solo.sh` starts the project's
  `portal/dev/shots.tscn -- --only solo` (the portal in the test window; the name; the Remastered card's Play) with
  the route as the game's `--script`; `campaign/resume.sh` starts again from the level a killed run was in (one run
  was killed by another agent's `pkill -x Godot`).
- **Runs:** `s1` (smoke: blood1, valor, endgood), `c1` (hub to islc1; killed), `c2-1` (islc1 to endgood), `c2-2`
  (endgood again, with the presses to the title), `c3` (8 levels again at the day's lowest load: the frame-rate
  figures), `c4-1` (the evil branch, bonus and medal levels), `c4-2` (endbad), `c5` (bossevil), `t1` / `t2` and
  `endgood/*` (bug 1 and the ending).
- **Order of the good path:** blood1 strife drunarm drunare - innovat1 inmine1 inmine2 innovat2 - islc1 islc2 islsm1
  islsm2a islsm2b islsm3a islsm3b islgnome islgoth - wat1 watg2a watg2b watg2c - tormenta tormentb torment2 torment3 -
  swamp1 dis2 arachna1 - valor valor2 honor - fire1..fire5 - storm1 storm1a storm1b storm1c storm2 storm3 storm4
  storm5 - fay2 fay3 - nit1 nitdung1 nitdung2 nit2 nitdung4 - bossgood fearboss - endgood.

## 2. The ending (Ran)

`endgood` plays its closing scene (wide framing, `endgood-b.png`) and stops on the game's own "Create New Save Game"
screen; the game's frame count stops there (2,059) until a button is pressed. The native program (`rta_app_next`) does
exactly the same (`endgood/n-*.png`), and two crosses take it to the title (`m.out`). In the portal two crosses end the
session and the portal comes back ("the session is over (frontend)", `c2-2`). Not a fault.

## 3. Bugs, by severity

| # | Severity | What | Where / cause | State |
|---|---|---|---|---|
| 1 | **Blocker** | In every long Remastered session (4 of 4) black geometry - a slab with jagged spikes and thin black streaks - appears and then stays fixed to the player through every later level, view and the ending, growing until the 3-D picture is wholly black: from `drunarm`'s Hardcore round in `c1` (levels 3-9 covered), from `watg2a` in `c2-1` (the next 34 levels and `endgood`'s closing scene), from `watg2a` in `t2` (nearly the whole picture black), from `disbonus` in `c4-1` (every later level's 3-D picture mean 0.0 of 255 while the game ran on with 300-700 draws a picture; only the HUD showed). A player cannot finish the campaign in one sitting | Godot side: the native program with the same route and modes draws cleanly (`endgood/w1`); seen also without the portal, paced (`w2`: the streaks); not seen in two short runs. Not removed by switching off any of `remaster_models`, `er_models`, `er_creatures`, `models`, `fill`, `er_world`, `lights`, `contact`, `backdrop`, `sky`, `batch`, `prepass`, nor by the display rate 60 (`t1`, `t2`). Left: the scene's kept meshes and the between-frames carry (`tools/godot/extension/src/rta_scene.cpp` `keep` / `carry`, `rta_drawer.cpp`), which no look key turns off. Other agents work in those files | **fixed** (section 9): the 3-D surface kept its picture between lists and every world draw is blended, so a pixel once non-finite stayed so; it is now cleared wherever the list begins with the game's own clearing rectangle |
| 2 | **Major** | 60 a second not held: game frames 37.7 a second in `fire1` and 37.9 in `bossgood`, 51.8-59.1 elsewhere, at load 11-19; the 120 Hz picture rate reached only walking in light levels (`fearboss` 119.7, `valor` 92) | the machine was never quiet (other agents' Godot runs); `native-godot.md` measured 58.5-60 in fire1 alone. Needs a measurement on a quiet machine before a cause is named | **open** |
| 2 (2026-10-26) | **Major** | Measured quiet ([fps-verdict](fps-verdict.md)): 60 held in most levels after the pacing fix; `arachna1` 50 (GPU-bound: 4x MSAA at 3024 x 1964, 884 ms of GPU a second) and `wate2c` 40-53 (main thread) remain | the cause in fire1/bossgood was other programs on the GPU; arachna1 needs cheaper multisampled passes without changing the picture | **open** (narrowed) |
| 3 | Medium | Remastered's per-level look presets reached no player: `levels.cfg` was kept as game output under `local/` and staged only where `presets.py make` had run, so no build since round 7 had it | the file holds only our own look numbers (shade, fog, bloom, light energy, brightness, contrast, saturation, sun height by level name; no colour, texture, geometry or code of the game): now tracked as `tools/godot/project/presets/levels.cfg` (the measurement comments left out); `build.py` stages and exports it with the project, `build_setups.py` no longer refuses the name | **fixed** (section 8) |
| 4 | Medium | Crash at quit of a room copy: signal 11 in `RendererRD::MaterialStorage::free` from `BaseMaterial3D::~BaseMaterial3D` of `ArrayMesh`es held in nested GDScript dictionaries, freed in `SceneTree::finalize` after the rendering server's materials (`online/r2a/a.txt`; the crash report in the copy's `reports/`). 1 of about 12 Godot exits | a script-held mesh cache (`er_layer.gd`, `model_remaster.gd` or `er_world.gd` keep such dictionaries) not cleared before shutdown; clearing it in `_exit_tree` would avoid it | **fixed** (section 9): `er_layer.gd` lets go of `models` (the outfits' glTF meshes: the chain in the backtrace), the weapons', `surface_arrays` and its own mesh at `release()` / `_exit_tree`; 9 clean quits since |
| 5 | Minor | Remastered played at 4:3 between black bars in the test window's 16:9 picture | the profile's `wide` was on (the default since 2026-10-13); the game scene took the shape from the window, not from the viewport it is shown in - the portal's test window puts the portal into a 16:9 off-screen viewport inside a window of another shape. Now the viewport's shape; Classic kept at 4:3 whatever the setting | **fixed** (section 8) |
| 6 | Minor | The game's picture in the Godot window was darker than the game's own picture - 2-D screens most visibly (the ending's save screen mean 3-4 against 19-22), the 3-D picture too | `view.gd`'s canvas shader multiplied `texture(TEXTURE, UV)` by `COLOR`, which in Godot 4 already holds the texture's colour: every value squared (not the sRGB curve twice) | **fixed** (section 8) |
| 7 | Minor | The library's room status kept the text "the game runs: level hub" after level changes | `tools/recomp/net2/launch.cpp`: the text was set once at the start; now set again with the level when the presence sees it change | **fixed** (section 8) |
| 8 | Cosmetic | Every run of the portal test window printed "unknown option" for the test window's own arguments | `main.gd` now knows the test window's and the join test's options (with their values) | **fixed** (section 8) |
| 10 | Medium | First person black in the levels without a sky (`watg2a/b/c`, `swamp1`, `islc1`; `valor2` in Classic): the look kept from the level before, where the route had looked up | `tools/recomp/app/fpview.cpp` (ours, native and Godot alike): each view's look up or down was kept over level changes, so the view arrived looking 65 degrees up at a black sky | **fixed** (section 10.2): the look starts level at every level |
| 9 | - | Three level requests in the long runs brought back a level (`honor` -> `fire1`, `nitdung1` -> `nitdung2`, `nitbon2` -> `nitbonus` four times instead of `bossevil`); each level loads when asked for in a run of its own | not found; the route's request may meet the game's own restart or a bonus level's return | noted |

Fixed since: bugs 3 and 5-8 (section 8), bugs 1 and 4 (section 9), bug 10 (section 10).

## 4. Online (Ran)

| Run | Copies | How | Levels | Ticks in step |
|---|---|---|---|---|
| `online/r2a` | 2 | two portals, Remastered cards, friends, room, Start (`online/room2.py`, from `room29.py`) | hub, drunare, valor, arachna1 | 6,467, no shared column differs (`cutf` left out) |
| `online/r3a` | 3 | Godot copies, Remastered options on the command line, `n2party.py --program as-godot.py` | the same, 6 deaths, 2 reloads | 6,131 / 6,131 / 6,143 |
| `online/r4a` | 4 | the same | the same, 8 deaths, 2 reloads | 6,038 to 6,045, every pair |

Routes direct on this computer (no relay). In `arachna1` the players fought the level's spiders and died; the Spider
Queen herself was not engaged in a room.

## 5. Frame rate (Ran; `campaign/fps.py`, `speed.py`)

`c3`, paced, through the portal, 120 Hz display, load 11-19:

| level | game frames / s | slowest second | pictures / s | walking |
|---|---|---|---|---|
| blood1 | 55.8 | 31 | 68.2 | 53.7 |
| drunare | 59.1 | 31 | 61.8 | 55.7 |
| valor | 57.2 | 40 | 88.8 | 92.1 |
| fire1 | 37.7 | 11 | 38.9 | 46.4 |
| nitdung2 | 53.4 | 23 | 69.7 | 52.0 |
| storm5 | 51.8 | 26 | 54.5 | 50.3 |
| bossgood | 37.9 | 10 | 41.6 | 37.7 |
| fearboss | 56.6 | 21 | 86.0 | 119.7 |

The long runs (load 40-450) averaged 18-45 pictures a second per level (`speed.py c1/out.txt c2-1/out.txt`); `c4-1`
(load about 10-16) 48-64 a second in most medal and bonus levels, `wate2c` 37.7 - but from `disbonus` on its pictures
were black (bug 1), so its later figures do not count.

## 6. Open items

- Bug 2 (60 / 120 on a quiet machine).
- The sharp films seen in this route.
- Remastered online with three and four copies through the public service and from two networks (through a service
  on this Mac: section 10.6).
- The bosses after the first killed one by one.
- (Closed in section 10: the transient black pictures, spells and projectiles aimed by the look, weapon arts and
  two-handing, a boss killed, three and four portals in one room.)
- Windows and Linux: hold-to-skip is not in their programs or Godot libraries (`native-cutscenes.md`, "Not done").
- A person playing it.

## 7. Changed (tracked)

- `tools/godot/project/portal/dev/shots.gd`: scenario `solo` (the Remastered or Classic card's Play pressed, the game
  run with the command line's script to its end).
- `docs/issues/remastered-complete.md` (this file), `docs/PROGRESS.md` (the Remastered row).
- Section 10: `tools/recomp/app/fpview.cpp` (the look started level at a level start, bug 10);
  `tools/godot/project/portal/dev/shots.gd` (scenario `room5` with `--party 3 | 4`: copies C and D join by the room's
  code); `tools/godot/project/main.gd` (`--party` known to the game scene, so no "unknown option").

## 8. Fixed after the check (Ran, 2026-10-26)

Built from a clean worktree of `5249c6e` with only these changes (`build.py all` into `local/rfix-out`, `run.py
import`); evidence in `local/rfix-check/` (not tracked).

- **Bug 3, the look presets ship.** `tools/godot/project/presets/levels.cfg` (111 levels, our own look keys only) is
  tracked; `build.py project` stages it from the project and no longer copies `OUT/presets`; the export takes it with
  the project; `presets.py make` writes `OUT/levels.cfg` with its measurement comments and says to copy the key lines
  into the project. Fresh build: `look presets: 111 levels from res://presets/levels.cfg, res://presets/tuning.cfg`;
  in a level `level valor: look preset { brightness 1.22, shade 0.72, fog_start 420, fog_end 1350, saturation 1.196,
  bloom_strength 0.75 }` (the made preset with the hand-tuning over it); Classic still `preset=off`.
- **Bug 6, the window's brightness.** Cause found with a two-file Godot project: a viewport texture holding 127 shows
  127 through a plain canvas item and 63 through `view.gd`'s shader (`texture(TEXTURE, UV) * COLOR`: COLOR already
  is the texture's colour, so every value was squared); `vec4 c = COLOR` shows 127. Means of 255 (the window's own
  picture; the native program's at the same point of the same script):

  | Picture | native | Godot window before | Godot window now |
  |---|---|---|---|
  | title menu (2-D) | 123.3 124.7 156.9 | 74.1 72.8 116.3 | 123.8 125.9 158.5 (the screen itself, captured: 125.9 127.1 168.6) |
  | hub (3-D) | 99.6 87.6 86.7 | 50.6 38.5 40.3 | 96.8 84.8 84.1; Godot Classic through the portal 100.2 88.0 87.0 |
  | `endgood`'s save screen (2-D) | 25.5 28.6 27.3 | 3.4 4.1 3.7 | 25.5 28.7 27.4 |

  The films and cut scenes go through the same shader. The look presets were picked from Godot's own drawing (`app
  shot`), not from the window, so they stay as they were.
- **Bug 5, widescreen.** The wide view already exists and is on by default (profile `wide`, `--aspect`, the library's
  `aspect` option: the game's own projection widened, `native-graphics.md` 1.3: nothing the simulation computes
  changes, the screen clamp of offline two-player games kept at 4:3). `main.gd` now takes the shape of the viewport the
  game is shown in; Classic stays 4:3 whatever the setting (`handover.gd`, `main.gd apply_settings`, also on a switch
  of edition while running). Through the portal (`shots.gd solo`, 1920 x 1080): Remastered `aspect 1.778`, the
  picture filling the width; Classic `aspect 1.333`.
- **Bug 7.** In rooms the status now reads `the game runs: level hub`, `... drunare`, `... valor`, `... arachna1` in turn.
- **Bug 8.** No "unknown option" in the portal test runs (`solo`, Remastered and Classic).
- **Rooms, two copies, one 16:9 and one 4:3** (`n2party.py`, Godot copies with the Remastered options, hub -> drunare
  -> valor -> arachna1, deaths and reloads): 6,418 ticks in step (`r2`), and after the `model_remaster.gd` fix 6,171
  ticks in step with no script error (`r3`).

## 9. Bug 1 and bug 4 fixed (Ran, 2026-10-26)

Built from a clean worktree of `5249c6e` with only the change below (`build.py all` into `local/bug1`, `run.py
import`); evidence in `local/bug1/` (not tracked): `runs/` (the reproduction and the bisection), `campaign/` (the long
sessions), `online/` (rooms). Load average 9-17 throughout.

**Reproduced fast.** The check's route without the portal (`runs/run.sh`, paced, Remastered options) over `wat1`
alone: after the level's opening fade 17 % of the 3-D picture stayed black, fixed to the screen, through every later
view, the Hardcore round and the walk (`r2`: `s0005` .. `wat1-2-end` 0.17-0.18 black). Then, at the same tick, the
world viewport cleared once (a test option, `dbg_clear`): **0.00** - nothing was being drawn black; what was black was
left in the surface from before.

**Cause.** The world's viewport keeps its picture between lists (`ENV_BG_KEEP`, made so because the GS never clears),
and every draw of the world - the level's batches too - is in Godot's blended pass: `source x A + destination x (1 -
A)`, with A = 1 for what covers. A destination that is not a finite number survives that (NaN x 0 = NaN), so a pixel
that once took such a value - a fade, a light or a degenerate triangle in one list - stayed black under everything
drawn later, in every view and level, and more of them gathered over a session. It was not in the kept meshes, the
between-frames carry or any look layer, which is why switching each off changed nothing: they were not adding it,
and switching one off did not clear what was there. (The value itself was not read back: the surface is half-float
inside Godot. That it is non-finite follows from finite colours being replaced by the next draw with A = 1, and from
one clear removing it all.)

**Fix** (`tools/godot/extension/src/rta_scene.cpp`). A list whose first draw into the 3-D surface is the game's own
opaque clearing rectangle (`scene_scan_sky`: whole surface, untextured, its blend not reading the destination) has
the surface cleared (`ENV_BG_CLEAR_COLOR`) - the game draws every pixel of it anew there anyway, so nothing it shows
changes; lists without one, and lists without the scene (menus over the picture, films), keep what is there as before.
The figures line says how many: `the 3-D surface cleared in 261700 lists` of 262242 in the long session.

**Proof.**

| Run | What | Black share of the chase picture, mean over levels | levels > 0.5 | levels wholly black |
|---|---|---|---|---|
| `c2-1` (before) | Remastered, 46 levels from `islc1` | 0.32 | 4 | 0 |
| `c4-1` (before) | Remastered, 28 medal / bonus levels | 0.45 | 12 | 12 (mean 0 from `disbonus` on) |
| `campaign/L1` (after) | Remastered through the portal, one session: hub, shop, the good path `blood1` .. `fearboss`, the 27 evil-branch, medal and bonus levels to `bossevil`, then `endgood` - 81 levels, 2 h 22 min of game | **0.07** | 0 | 0 |
| `campaign/K1` (after) | Classic through the portal, one session, the good path to `endgood` (54 levels) | 0.04 | 0 | 0 |

`endbad` in a run of its own (`L2`): as in the check (`c4-2`). Every level's pictures in `L1` were looked at where the
share was above 0.3: dark levels, the game's fades and the end of a level's walk, nothing fixed to the screen; the
same levels' next pictures and the next level clean. The reproduction route (`r5`, `r6`: `wat1`, `watg2a`, `watg2b`)
after the fix: 0.00 after the fade, and where it is not 0 (`watg2a` 0.2-0.5, an unlit underwater level) one clear
changes nothing (`z-before` 0.34, `z-clear` 0.36): what is black there is drawn black.

**Not build-up (left as they are).** Some pictures are wholly black for a moment and the next view is clean: the
overhead and action views in `wat1`, `innovat1`, `islc1`, `islsm1`, `storm1`, `storm4` right after the view changes
(a series in `wat1` every 4 ticks: black until tick 72, then the game's fade-in, `runs/o2`), and first person in the
underwater levels `watg2a/b/c`, `swamp1`, `valor2`. Godot Classic shows the same pictures black in the same places
(`K1`), so these come with the game's picture; to be checked against the native program view by view. (Checked in
section 10: the first kind is the game's own blank after a load; the second our look kept over a level change, fixed.)

**Two copies still in step.** `online/r2`: two Godot copies with the Remastered options in a room (`n2party.py`),
hub -> drunare -> valor -> arachna1, 6 deaths, 3 reloads: 6,250 ticks in step; `online/r4`: four copies, 8 deaths,
5,894-5,905 ticks, every pair in step. Each copy cleared its surface in 96 % of its lists.

**Bug 4** (`tools/godot/project/er_layer.gd`). The backtrace's chain - a script dictionary, a dictionary, an array, a
dictionary, an `ArrayMesh` - is `models[set].meshes[i].mesh`, the outfits' glTF meshes. `release()` (called from
`scene_view.gd` before the drawer lets go, on the way out of `main.gd`) and `_exit_tree` now drop `models`,
`weapon_models`, `surface_arrays`, the materials in waiting and the player's own mesh while the rendering server is
whole, instead of leaving them to the script's destruction in `SceneTree::finalize`. Since: 2 + 4 room copies and the
portal's quits after the three campaign runs, 9 of 9 clean. The crash was 1 in about 12, so this is a check, not a proof.

Seen on the way, not from this change: `model_remaster.gd:477` (`f.name` on a figure without it, 90,401 script
errors in `L1`) is in the `5249c6e` tree this was built from and already fixed on main (section 8, `r3`);
`er_world.gd:434` (`paths`, 2 errors in `L1`) is the hub-rebuild work's file.

## 10. The open items closed (Ran, 2026-10-26, evening)

Built from a clean worktree of `e9289ce` with only the changes listed in section 7 (`build.py all` into
`local/rem-close`, `run.py import`); native programs: `rta_app_next` (this morning's, the Remastered modes),
`rta_app_next_orig` (the game as on the disc, none of our modes) and `rta_app_remclose` (`build.py --no-game --as`:
`rta_app_next`'s game with this section's `fpview.cpp`). Evidence in `local/rem-close/` (not tracked): `runs/` (the
routes `mkseries.py`, `mkviews.py`, `mkpitch.py`, `mkfeat.py`, `mkboss.py` and each run's pictures and output),
`online/` (`roomn.py`, `room.sh`, `cmp.py`, the rooms). Load average 2-20.

### 10.1 Black for a moment after a view change: the game's own blank after a load

The check's route asked for the views as soon as the level's tick count reached 150. A picture every 4 blanks from that
moment for 120 blanks (`mkseries.py`), in the native program, once with no view change at all (chase, as it was) and
once with the overhead view asked for at the first picture; and in the game as on the disc:

| Level | black pictures of 30: native, no view change | native, overhead asked | the game as on the disc | Godot, no view change |
|---|---|---|---|---|
| `wat1` | 18 | 18 | 18 | 11 |
| `islc1` | 21 | 21 | 21 | 22 |
| `storm1` | 21 | 21 | - | - |
| `innovat1` | - | 20 | 20 | - |
| `islsm1` | - | 14 | 14 | - |
| `storm4` | - | 13 | 13 | - |

The same pictures are black with and without the view change, to the blank, and in the program without any of our
code; then the game's fade-in (`wat1`: mean 6 -> 53 of 255 over 32 blanks). The view's own status in those blanks:
"the game's camera: warm-up (the picture is blanked)" - the game's wait loop after a load (`0x506048`, session loop
`0x322998`, `docs/ui.md` P1), whose length follows the loading (Godot 11 to 22). So it is not the view change and
not ours: the check's first one or two views simply fell into it. Routes that picture views now wait for
`0x506048` to be 0 and for the fade.

### 10.2 First person black in levels without a sky: the look kept from the level before (bug 10, fixed)

- **Not the levels.** Fresh from the hub, first person in `watg2a`, `watg2b`, `swamp1`, `valor2` (the check's own views
  route, `mkviews.py`, a picture every 3 blanks): Godot 0.17-0.49 of the picture black, native 0.15-0.56 - dark
  levels, drawn.
- **What the check had.** In `L1` / `K1` the first-person picture came after every earlier level's first person had
  looked up (the route's `stick R 200 100`): the look was kept from level to level and stood at 65 degrees up
  (`aim info`: pitch 11833 at `watg2a`); the draw counts there fell from about 3,500 a list to 4-54 (the speed lines:
  only the HUD). Looking straight at the sky of a level that clears to black and has no dome shows black.
- **Reproduced** (`mkpitch.py`: first person in `watg2a`, the look up for 60 blanks; then `watg2b` and `swamp1`
  asked for, first person there): native `rta_app_next` 0.93 and 0.95 black, its view info "forward -0.285 0.311
  0.906" in both new levels; Godot (the section 9 build) `watg2b` 0.98. The native program is black too, and the
  cause is ours: `fpview.cpp` kept each view's pitch over level changes.
- **Fix** (`tools/recomp/app/fpview.cpp`, `begin_pass`): when the game's tick count is lower than at the last pass - a
  level started or restarted - every view's look starts level again. It is this machine's view; the aim's pitch
  (`fpaim`) is sent as this player's input in game message 4 and follows what is shown, as it does whenever the stick
  moves the look, and every copy applies the message alike, so the lockstep rule holds (nothing in the tick reads the
  view). After: native `rta_app_remclose` `watg2b` 0.29 and `swamp1` 0.42 black with the view "forward -0.675 0.737
  0.000"; Godot 0.43 and 0.23. The rooms of 10.6 ran with it through three level changes, every pair in step.

### 10.3 Spells and projectiles aimed by the look (Godot, Remastered options)

`mkfeat.py`: `valor` by the boar, first person, Hardcore and aim look; the nearest creature locked and held in front
(test aid `app souls pose front`); the look moved up or down by the right stick, then the skill button; the aim block's
words after each (`0xe1800`: projectiles aimed, the last one's heading, pitch, class, speed).

| Run | Character | What | Seen |
|---|---|---|---|
| `gfW` | Erudite Wizard (8 presses right on the class page) | the second skill button at the look +13.6, +0.4, -11.1, +10.3 degrees | 3 Shock of Frost bolts aimed, each at the look's pitch exactly (aim words 2477, 64, 1883 = the look's), 350 a second, 3 spells cast, **3 spell hits** on the boar (mana 42.5 -> 36.1 each); the cast looking down not made (not looked into; the one before it 115 blanks earlier) |
| `gfR` | Wood Elf Ranger (4 presses right) | the attack at the same four looks, no creature beside | **4 arrows aimed** at 2477, 64, -2019, 1883 (the look's exactly), 1,000 a second |
| `fW`, `fR` | the same, native `rta_app_next` | the same | the same numbers |
| `f0` | the first class (the check's) | both skill buttons | the first button casts nothing (no spell bound for this class), the second casts the homing bolt: 1 cast, 1 hit, not turned onto the look - homing bolts are left to the game by design (`native-first-person-aim.md` 4) |

So the check's "spells cast 0" was its route: it pressed only the first skill button.

### 10.4 Weapon arts and two-handing (Godot, Hardcore)

The same runs, chase view: L3 held + attack = the weapon art; L3 held + the weapon swap = two-handing, then three swings,
then back. `gfW`: 1 weapon art (mana 42.5 -> 34.6), two-handing on and off (toggles 2) with the swings between; `gfR`:
the bow's art (1), two-handing not taken for the bow (0 toggles); native `f0` (the first class, a mace): 1 art,
2 toggles. No script or shader error in any of them.

### 10.5 A boss killed

`mkboss.py`: `islsm1`, whose boss - Broon, the FatCyclops, 1,714 hit points (the boss meter's name `broon`) - stands
beside the arrival; locked on (Hardcore) in the chase view, four swings at full strength, then its hit points brought to
6 by the test aid and the player's own swings until it falls.

| Run | Seen |
|---|---|
| `sB`: through the portal (the Remastered card's Play, as the campaign) | boss music engaged at tick 1,282 (an Elden Ring track from the player's own files, the game's music at 0.32 then 0); the meter 1,714 / 1,714; **killed at tick 1,706**: hit points -11.05, its AI state 0x14 (a corpse), the meter cleared, the player level 1 -> 2 from the experience; "the fight is over (tick 1939): back to the game's music over 3.0 s" |
| `gbH`: Godot scene, Hardcore | the same ticks and numbers |
| `gbN`: Godot scene, Remastered look, **Hardcore off** (the game's own combat; no lock-on, which is Hardcore's: the same object by its address) | **killed at tick 1,622**: -8.83, state 0x14, the meter cleared, level 2 |
| `bH`, `bN`: native | the same as `gbH`, `gbN` |

### 10.6 Three and four portals in one room through the service path

`shots.gd` scenario `room5` now takes `--party 3 | 4`: the host waits for that many in the room and in "everybody
ready", copies C and D join by the room's code after B is in (by the host's invitation, as before), and every copy
waits for all the others at the end. `online/roomn.py` (`room2.py` for two to four portals) starts a rendezvous service
of the run's own on 127.0.0.1 (`tools/rendezvous/rendezvous.py --bind 127.0.0.1`, as `check_client.py` does) and the
portals, each choosing Remastered on its card; the game's own character screens; Start; then hub -> `drunare` (tick
1,600) -> `valor` (3,100) -> `arachna1` (4,600), the players put beside the nearest creature in turn from 4,800 (test
aid in every copy's `tick-do`). Compared with `tools/rig/compare.py ticks`, every pair, the title fly-over clock `cutf`
left out (`cmp.py`).

| Run | Portals | Ticks | Result |
|---|---|---|---|
| `r4` | 4 | 6,344 to 6,352 | **no shared column differs on any tick, all six pairs**; 6 deaths in `arachna1`; every copy Hardcore, aim look, hold-to-skip, 16:9 |
| `r3b` | 3 | 6,365 to 6,378 | **no shared column differs, all three pairs**; 7 deaths |
| `r3` | 3 | 2,284 to 2,291 (a shorter stay) | in step, all three pairs |

Every copy quit cleanly (exit 0, 10 of 10), no script or shader error. `r3` and `r4` printed "unknown option --party"
from the game scene; `main.gd` now knows it (`r3b`: none).
