# Remastered played as a player: the glitches

2026-10-26 / 27. The portal's **Remastered** choice with every feature on (Hardcore with its stats, weapons, flasks,
spellbook and death drop; the five views and aiming by look; the new HUD; the remastered models; the Elden Ring outfits,
creatures and world layer with the hub rebuild; boss music; cut scenes framed wide with hold-to-skip; 120 Hz), played
the way a player plays it - the hub's dialogue, the portal, the game's own mission map, the levels' own exits, fights
in Hardcore, deaths, save points, a save and a load - and looked at picture by picture. Earlier checks loaded levels by
name (`remastered-complete.md`); this one walks.

Every statement says **Ran** (what was seen) or **Read**. One Apple-silicon Mac (3024 x 1964, 120 Hz) shared with an
fps-measuring agent (finished before the heavy play began) and a Classic playtest running two Godot copies: load
average 3-19 through the play. Evidence in `local/playtest-rem/` (not tracked): `runs/*/journal.txt` (every teleport
and test aid, with the place and the reason), `runs/*/pics/` (pictures), `runs/*/out.txt`, `online/` (rooms).

## How it was played

- **Build.** `origin/main` (`dc7b4cf`) in a clean worktree, `RTA_GODOT_PARTY8=1 build.py all` into
  `local/godot-play-rem` (the 8-player library, as the desktop launcher's); the fixes below were built and checked in
  `local/godot-play-rem2`.
- **A closed loop on the game.** The game's script runner learnt `follow FILE` (`tools/recomp/rt/script.cpp`, a test
  aid): lines appended to a file run as they come. A driver (`local/playtest-rem/tools/drive.py`, `play.py`) appends
  stick and button lines and `show` reads, reads the answers back from the game's output (one game frame a round
  trip), and plays: it walks by the stick toward a goal (its heading learnt from where the character actually went, so
  any camera works), plans over the level's own object places (`objects.ob` from the disc, local), locks on and fights
  in Hardcore (light, heavy, dodges, guard, flasks), talks (use button, cross through the dialogue), uses exits and
  save points with the use button, and pictures the window.
- **What it is not.** A scripted player is not a person: Hardcore crowds (blood1's kobold camps, strife's archers,
  Rallos Zek's knock-downs) killed it again and again. Deaths, the drop and the reload were played many times
  (below); for progress after that, two test aids, each said in the journal where it was used: the character was given
  experience by the game's own `player_giveExp` (level 1 -> 18) and saved at a save point; and later its hit points
  were held (refilled when a read found them low; 5,000 against Rallos Zek). Where the walk could not find a way (the
  planner knows object places, not walls) the character was **teleported**: 9 times in blood1, about 30 in strife, 2 in
  drunarm, each with the reason; and to boss arenas. Rallos Zek's hit points were brought to 40 of 1,097 after a
  minute of fighting (a +0 club does 7 a hit).

## Route (Ran)

| Where | How | Seen |
|---|---|---|
| Portal | the Remastered card's Play (alone), the test window | every feature in force (`effective settings`: Hardcore, aim look, new HUD, boss music 82 tracks, ER models/creatures/world, remastered models, display rate auto = 120) |
| Front end | the game's own screens: card, new character (Iksar Shaman), name | - |
| hub | walked to Firiona Vie, talked (the dialogue to its end), walked to the portal ring, used it | the mission map (the game's), Plane of War, accepted |
| blood1 | arrival cut scene (31 s); walked and fought toward Natasla; died 6 times (drops, reloads, gold); level-up and points at the save point; saved; loaded the save from the title screen; talked to Natasla, the good answer, the good door's cut scene; to the good exit, used it | `strife` |
| strife | the engineer's dialogue; stage 1 (13 marked orcs: the counter "12 Orcs Remaining" to none), the two shaman bosses; died and reloaded 3 times; the north exit used | `drunarm` (the catapult stage was left: the catapults want the level's bombs) |
| drunarm | fought through the gladiators to Rallos Zek; boss bar, **boss music** (an Elden Ring track, the game's music at 0), killed; his cut scene; loot picked up; music handed back (`state idle`, the game's music at 1.00) | Act 1's boss: done |
| pause menu | Exit This Mission, Yes | the hub's mission map |
| Act 2 | missions marked available (test aid: the player record's mission bytes), Plane of Innovation chosen on the game's mission map; `innovat1 -> inmine1 -> inmine2 -> innovat2`, each by its own exit (the character put beside it, the use button) | the five views and a fight in each; Iron Guardian found but not killed (the character wedged in debris by the teleport) |
| Acts 3-12 | the pause menu's Exit This Mission and the mission map (`acts.py`): the map's choice took only some of the time, the rest of the levels asked for by name; 45 levels from `islc1` to `fearboss`: arrival, the five views, the status lines, a fight where a creature was near; 10 exits used by the use button (5 led where the campaign goes, 5 back or sideways); 32 levels with no usable exit within reach (locked by their quests) asked for by name | no SCRIPT or SHADER ERROR; 12 levels whose five views were one picture, without the HUD (the views were asked for while the game's own camera held the frame at the level's opening, where no view applies; not a fault of the views); `islgoth` black in three views at one arrival (entered by name from `islgnome`), not again when entered from the hub (`series-goth-*`: Remastered 62, Classic 67 of 255 after the fade) |

## Online (Ran; a rendezvous service of the run's own on 127.0.0.1)

| Run | Copies | How | Ticks in step |
|---|---|---|---|
| `online/r2a` | 2 portals | Remastered cards, friends, room, Start; hub -> drunare -> valor -> arachna1, players beside creatures (deaths, reloads) | 6,389, no shared column differs |
| `online/r4b` | 4 portals | the same, C and D in by the room's code (after the test-window fix, glitch 8) | 6,325, all six pairs; four clean quits |
| `online/r6a` | 6 Godot copies | `local/party8/room8gx.sh` with this build: Remastered (Hardcore, aiming by look, the Elden Ring layer, shoulder view), started for rooms of eight, party scaling at six, valor > drunare, Hardcore's test aid putting players beside creatures | 4,427 - 4,441, all 15 pairs; 2 deaths; no error |

No desync, no drift; no relay needed (every route direct on this machine).

## Sound (Ran)

The master bus recorded (`--audio-tap`, `runs/audio1/`) through the hub, `blood1`'s opening scene skipped by holding
START, play, and the boss music engaged and handed back: `audiocheck` over the whole 157 s - no clipped sample, no
zero-filled gap, no dropout, no jump; the capture kept time with the wall clock (no deficit in `master-clock.tsv`).

## The glitches

Severity: **Major** spoils play or the picture often; **Medium** clearly wrong, seen in normal play; **Minor** a detail.
Pictures under `local/playtest-rem/runs/`.

| # | Severity | What, where, when | Picture | Cause | State |
|---|---|---|---|---|---|
| 1 | **Major** | The game's menus drawn **under** our figures: at a save point's card screens the player's fitted outfit, the save globe, the pedestal, a potion and the gold were drawn over the save list; in the hub's dialogue the box was see-through and its text broken up by the floor drawn over it | `a1/pics/b1-save-a.png`, `b1-save-L3.png`, `hub-talk-2.png` | Godot's transparent pass sorts an instance by the distance of its origin along the view less its sorting offset; the game's draws all have the world's origin, ours (figures, outfits, remastered models, grass, world pieces) their own place, so the list's order did not hold: an outfit sorted 1e6 "after everything" was after the menus too | **fixed** `cf326fe`: the 2-D layer after the last draw of the 3-D scene has render priority 1 (`rta_drawer.cpp`); `a2/pics/fix7-save.png`, Natasla's and the engineer's dialogues clean |
| 2 | Medium | The new HUD's lock-on corners, enemy bars and the arc stayed over the save point's card screens | `a2/pics/fix7-save.png` | a card screen in a level was no "menu" for the HUD | **fixed** `cf326fe` (`gamestate.cpp`: `g_memcardState` in a level is a menu; presentation only); `a3/pics/fix-hud-save.png` |
| 3 | Medium | Cut scenes at 120 Hz **flicker**: every other picture is nearly black or a stale one from before the scene - blood1's and dis2's openings showed the LOADING picture every other picture | `runs/sheet-series.jpg`, `series-*/p/` | the pictures between game frames were drawn "a frame behind" in a cut scene (`cinematic.gd` between -> `main.gd` `drawer.redraw(t - 1)`). **Why (Ran, Read):** the game frame's own picture is asked again *in the refresh it is taken* (`redraw(-1)` right after `submit`), and `RtaDrawer::redraw` switches every surface off but the world and the one shown before it asks for those two again: a cut scene's own surfaces (what the shown one copies from) were never rendered while the mode was on - the shown surface kept the LOADING picture, the other pictures came out nearly black | **fixed** `b7b3287` (behind-mode off), then **properly** (round 2 below): `redraw` in the refresh of a submit leaves its passes as the submit set them and only moves the camera and the kept models (`rta_drawer.cpp`); the behind-mode is on again in Remastered (`RTA_CINE_BETWEEN=0` off; Classic keeps the plain pictures). dis2 with it on: 38 38 0 25 51 67 66 66 ... 45, the same as the plain mode picture for picture (before: 39 39 1 8 38 8 38 8 38 ...); blood1 the same in both modes |
| 4 | Medium | The mission map (and gate menu, loading picture) in a wide picture: beside its 4:3 the kept world and a flagstone floor on one side, a piece of the starfield on the other | `a1/pics/hub-portal-2.png`, `a3/pics/mm-all.png` | the game draws these for 4:3; the "backdrop" (a ground for levels without one) was started by a list with no level in it | **fixed** `cf326fe`: black sides beside the 4:3 on these screens (`hud.gd`), and the backdrop neither starts nor stays while the game is paused, on a card screen or blank (`scene_view.gd`); `v2/pics/v2-mm.png` |
| 5 | Minor | Hardcore's lines over the stamina bar and the level-up hint drawn over each other | `a1/pics/b1-sheet-0.png` | two HUD pieces at the same place | **fixed** `cf326fe` (`status.gd` above `souls.gd`'s lines); `a3/crop-bl.png` |
| 6 | Minor | A spell's cooldown read "0.0" in its last tenth | `a3/crop-br.png` | `%.1f` of 0.04 | **fixed** `cf326fe` (rounded up) |
| 7 | Minor | The portal printed a SCRIPT ERROR every frame when embedded (the test window): 759 in two minutes | `a1/out.txt` (first run) | options handed by the host lacked `host_party` / `join_code` | **fixed** `cf326fe` (`portal.gd` fills missing defaults) |
| 8 | Minor (tests) | Rooms of three and four portals no longer formed: the host's room code was empty, C and D could not join | `online/r4a` | the portal now asks a Remastered host the party size; the test window did not answer | **fixed** in `shots.gd` (answers "Up to 4") |
| 9 | Medium | The hub's sky in chase, shoulder and first person: a blue cap with a hard round edge above the painted dome | `a1/pics/hub0-view-first.png`, `b1/sheet-sky.jpg` | **not the hub's dome at all (Ran, measured):** 5b73a2 is the colour of the front end's fly-over sky (`intro`, a hemisphere dome to 90 degrees). The level's name changes in the game's memory before the last frames of the level before are drawn and taken; `sky_reset` ran at the name change and those frames were then learnt as the new level's dome: top at 90 degrees, the ring the fly-over's. The learnt top only rises (a higher ring coming into view), so the hub's own upper edge (18 degrees) was never learnt and its blend into the sky never began: the hard edge. Timing-dependent (b1-b3 at 1920 x 1080 every time; a run alone at 1280 x 720 not). The same carried the hub's lavender dome into blood1 and strife (dark levels without a dome) | **fixed** (round 2): the packets of the level before's dome are not learnt from in the first 90 frames of a level, and a level that goes two seconds without a dome forgets one (`rta_scene.cpp`). Before/after, the same script: hub horizon 5b73a2 -> 938ec2, seamless in chase, shoulder and first person (`fixrem/runs/sky-ab.jpg`); blood1 "dome" a694bc -> dark; dis2, islsm1, tormenta, citadel unchanged |
| 10 | Medium | Elden Ring soldiers (strife's orcs) drawn pale white, far brighter than the game's own orcs in the same dark, rainy level | `a3/sheet-er2.jpg`, `a3/crop-ersoldier.png` | **two causes (Ran):** (1) a creature's pieces never got the game's light on the figure - only the fitted outfits of the players did (`_draw_fitted` sets `game_amb` ...; `_draw_figure`, which draws creatures, set nothing, so `er_armour.gdshader` took tint 1: the full texture under the scene's light, which is why switching the scene's lights did nothing); strife's light on a soldier is ambient 30 33 43, sun 56 60 62, fill 24 26 34 (a tint of 0.3 - 0.8); (2) the soldier model is painted pale steel (albedo luminance 0.45 - 0.65 against the game orc's dark green) | **fixed** (round 2): creatures and their weapons take `_game_light` as the fitted outfits do (every second frame, `er_layer.gd`), and `er_creatures.cfg [tone]` tones the soldier to 0.5. strife, the same tick, region of the three soldiers: brightest 5 % from 100 (before) -> 71 (light) -> 28 (light and tone); the game's orcs 19, top 1 % 61 / 59 (`fixrem/runs/cr-ab.jpg`, `strx3/`); blood1's kobolds and drunarm's gladiators darker with them likewise |
| 11 | Minor | Elden Ring demi-humans (blood1's kobolds): black speckles over their fur | `a2/crop-er.png` | **Read, measured:** the demi-human's hair cards are a dark strand mask (opaque texels' luminance 0.16, strands 20-40 of 255), meant to be coloured by the other game's hair shader; drawn as they are, thin near-black strands cut out over a pale hide - a scatter of black specks | **fixed** (round 2): `er_creatures.cfg [hair]` gives a model's hair cards their colour (demihuman 0.36 0.34 0.31; the strands' own shading kept round it: `er_armour.gdshader` `hair_tint`) and the light of item 10 puts hide and hair in the cave's light (`fixrem/runs/fur-zoom-ab.png`) |
| 12 | Minor | The first picture of the pause menu without the player's figure (it is there a moment later) | `a3/pics/pause-0.png`, `pause-exit-1.png` | **not a glitch (Ran, measured):** in drunarm the figure stood at x 914-1064, y 586-656 of 1920 x 1080 (`pause-exit-1`, below the smaller quit box); the pause menu's panel covers x 701-1221, y 386-771 - the figure is behind the game's opaque panel, in every picture of that menu (`pause-exit-sel` too). In the hub, where the figure stands below the panel, Remastered and Classic show it in the first picture of the pause (`fixrem/runs/pause-rc.jpg`) | the game's own |
| 13 | Medium | Frame rate: blood1 median 24, strife 30, drunarm 39 pictures a second through the play (load 10-19, a second machine's runs beside; the driver's window pictures each stall about 0.4 s); strife at 400-560 thousand vertices a picture, 17 a second at 977 thousand after a reload in the shoulder view; the Elden Ring creatures off or on made no measurable difference (39 / 39, 33 / 46 in turn) | `runs/a3/out.txt` speed lines, `p1/` | the machine was never quiet; the fps agent's own verdict is the measure | **open** (needs the quiet-machine measurement) |
| 14 | - | Death drop with the reload: the share is taken from the gold *after* the game's reload restored the save's gold, so a death can leave more gold than before it (250 -> 375; 379 -> 311) | `a1/journal.txt` | design: `soulscombat.h` "taken from the gold then"; with a reload the game has already put the save's gold back | noted |
| 15 | - | The HUD's experience reads "170,025 / 1,100" after levels gained | `a1/pics/b1-sheet-0.png` | the game's own acknowledged level (`+0x58`, the level-up screen behind SELECT): the original HUD (0x1d9cd4) does the same | the game's own |
| 16 | Minor | In Natasla's dialogue (blood1, chase view) a round inset at the lower left shows a magnified barrel | `a2/pics/nat-0.png`, `sheet-nat.jpg` | **the game's own (Ran):** the dialogue camera is the game's (the views fall back to it), and a barrel stands in front of it. The same route (teleport beside Natasla, the use button) in Godot Remastered, Godot Classic and the native program (`rta_app`, chase view and overhead view): the same barrel at the same place in all five (`fixrem/runs/nat-rc.jpg`, `nat-native.jpg`, `nat-native-overhead.jpg`) | the game's own |

Not seen anywhere: a SCRIPT ERROR or SHADER ERROR in a game run (a2, a3: 0), a crash, a softlock, a save that did not
restore (the load from the title screen put the level-18 character back at the save point, `a2/pics/load-2.png`), the
Classic look changed.

## Classic unchanged, lockstep untouched (Ran)

- The same script (power-on to the hub, a picture, the chase view, the pause menu) in **Godot Classic** with the
  build before the fixes (`godot-p8x`) and after (`godot-play-rem2`): the three pictures identical byte for byte.
- **Two Remastered portals in one room** (`online/r2a`, a rendezvous service on 127.0.0.1, hub -> drunare -> valor ->
  arachna1, the players put beside creatures, deaths and reloads): 6,389 ticks, no shared column differs (the title's
  fly-over clock `cutf` left out, as before).

## Round 2: the open glitches (Ran, 2026-10-27)

Build `local/godot-fixrem-a` (`origin/main` e8a7795, before) and `local/godot-fixrem-b` (with the fixes), both
`RTA_GODOT_PARTY8=1`; scripts and pictures in `local/fixrem/` (`run.py`, `*.rig`, `runs/`). Every before/after pair is
the same script on both builds, so the same game ticks; nice 10, muted.

- **Sky (9)**: found and fixed above. Other domed levels entered from the hub (`skylevels.rig`): blood1 lost the hub's
  carried-over dome; dis2, islsm1, tormenta, citadel the same before and after.
- **Soldiers (10), fur (11)**: above. The light is the same model of the game's vertex light the players' outfits
  already took (docs `native-er-layer.md` round 5); the tone and the hair colour are ours, in `er_creatures.cfg`.
- **Pause (12), Natasla (16)**: not ours, measured above.
- **Cut scenes a frame behind (3)**: the cause found and fixed in `RtaDrawer::redraw`; the mode is the default again in
  Remastered.
- **Classic unchanged**: the playtest's Classic script (power-on to the hub, a picture, the chase view, the pause
  menu, 1920 x 1080) on both builds: the three pictures identical byte for byte.
- **Lockstep untouched**: two Remastered portals in one room on a service of the run's own on 127.0.0.1 (`online/room.sh fx2 2`, build B: hub -> drunare -> valor -> arachna1, players put beside creatures): 6,414 ticks, no shared column differs (the fly-over clock `cutf` left out, as before).

## Changed (tracked)

- `tools/godot/extension/src/rta_drawer.cpp`, `rta_drawer.h` (glitch 1); `tools/recomp/app/gamestate.cpp` (2);
  `tools/godot/project/cinematic.gd` (3); `tools/godot/project/hud/hud.gd`, `tools/godot/project/scene_view.gd` (4);
  `hud/status.gd`, `hud/souls.gd` (5); `hud/bottom.gd` (6); `portal/portal.gd` (7); `portal/dev/shots.gd` (8);
  `tools/recomp/rt/script.cpp` (`follow`, the test aid).
- This file, `remastered-complete.md` (section 11), `docs/PROGRESS.md` (the Remastered row).
- Round 2: `tools/godot/extension/src/rta_scene.cpp` (9), `rta_drawer.cpp`, `rta_drawer.h` (3);
  `tools/godot/project/er_layer.gd`, `er_creatures.cfg`, `shaders/er_armour.gdshader` (10, 11); `cinematic.gd` (3).
