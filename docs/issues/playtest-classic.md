# Classic played: a tester's run through the campaign

The task: play **Classic** (the portal's Classic choice in Godot, and the native Classic program) the
way a player does - fight through the levels, pick things up, use the levels' exits and the game's own
mission flow, level up, shop, save, load, die and restart - and look for glitches all the time; tell
ours from the original's against the emulator; fix ours. Started 2026-10-26 (evening); acts 9-12, both endings and the
open suspects 2026-10-27 (morning, section "Acts 9-12 and the open suspects"). Every statement
says **Ran** (with what was seen) or **Read**. Pictures and logs under `local/playtest/` (not tracked).

## How it was played (Ran)

The earlier checks (`classic-complete.md`) asked for each level by name and pictured it. Here the
character walks, fights and leaves by the game's own exits:

- **The Godot copy takes a control port** (`main.gd --control PORT`, `project/dev/control.gd`,
  127.0.0.1): the native program's control-socket commands - hold a controller state, read and write
  the game's memory (`RtaMachine.peek_bytes` / `poke_bytes`, test aids), a picture of the window, the
  host's `app` lines, the drawer's scene options (`sceneopt`), quit. Several drivers can be connected
  at once. It marks in the frame log what its own reads and pictures cost, so that a measure of the
  game's pacing can leave those frames out, and it notes every frame that draws next to nothing after
  a scene (a black flash a player would see) with the level, and can picture it (`fewshots DIR`).
- **One driver plays both programs** (`tools/recomp/app/playtest.py`): `launch godot|native|emu RUN
  [--portal]` (`--portal`: the portal's first screen, the Classic card's Play - `portal/dev/shots.gd`
  `solo` - then the game), `newgame` (memory card, title, new game, a class, abilities, a name, the
  hub), `loadgame`, `mission` (Firiona's offer, the mission portal, the mission menu, the story start),
  `play` (fight what is there, pick up gold and things lying about, open chests and barrels, rest when
  hurt, a health potion, level-ups through the game's own screen, the save point every 600 experience,
  on to the next creature that stands alone), `exit LEVEL` (the level's own trigger that asks for that
  level, walked into or used), `travel`, `goto`, `fight`, `loot`, `put` (a teleport, logged as one).
- **The way is learnt as a player learns it**: the stick's axes come from the camera's yaw; a grid of
  where the character stood and where it could not go, A* over it with the unknown taken as free; a
  road map of the places things stand on (creatures, chests, save points, triggers) for long ways, a
  leg that fails costing more.
- **The exits come from the disc** (`tools/recomp/app/exitmap.py`, output under `local/` only): each
  level's `Trigger`, `PushTrigger` and gate with what its script reaches - `newWorld` and its level,
  `setEntrance`, the mission menu, the store - followed through `callScript` and the script's own
  calls (`docs/level-flow.md` 6.4). 150 objects in 120 levels ask for a level.
- **Checked at every step**: stuck (stick held, no movement), a fall far below where the character
  stood, hit points not a number or above the maximum, an enemy struck beside the character for 12 s
  whose hit points do not move, an exit that does not take the character away, a level that does not
  start, a picture of one colour while the game plays. Pictures every 8 s of play and at every event.
- **Last resorts**, said where used: `put` (a teleport) and, after three deaths in one level, the
  game's own invulnerability switch for the rest of that level (`G_INVULNERABLE`, as `tour.py` uses it).

## What was played (Ran, 2026-10-26 evening to 2026-10-27 night)

| Run | Program | What |
|---|---|---|
| `g1`, `g2`, `g3`, `g4` | Godot Classic, **through the portal's Classic card** (`--portal`; `g1` `--edition classic`) | new game (Barbarian, the card's questions, the class, appearance, abilities, name); the hub: Firiona's offer, the mission portal, the mission menu; **Act 1 by play**: `blood1` fought through (deaths, a level-up through the game's screen, chests, barrels, gold, items, the save point), its exit to `strife`, `strife` fought through to its Orc boss; then `drunarm`, `drundar` (its Ogre "Thud"), `drunare` (the arena's knights and Cazic), `boar1`; acts 2-6 level by level (`innovat1` ... `disbonus`, 36 levels in all, 7 bosses killed: Iron Guardian, Sea Monster, Ogre, Tormentor, Black Widow, Gnaw Spawn, Minotaur); a load of the card's save from the title (`Load Saved Game`) |
| `n4`, `n6` | native Classic program (`rta_app` built from main, `--as rta_app_playc`) | the same new game and mission flow; `blood1` and `strife` played (the strife Orc killed), the other Act 1 levels and acts 7-8 (`valor` ... `firbonus`, 15 levels) |
| `room1` | two Godot Classic copies in one room (`roomparty.py --godot-control`, a rendezvous of its own on 127.0.0.1) | hub > `blood1`, the host played by the driver through its control port: **every tick in step (14,198)**, both launched and finished, 1 death |
| `e1` | the emulator (Play!, no patch section) | the reference for each suspect below |
| `g7` (+ `g9`, `g10`) | Godot Classic through the portal's card, a level-10 Barbarian from `g4`'s card (17 by the end) | **acts 9-12**: `storm1` ... `stobonus`, `fay1` ... `faybonus`, `nit1` ... `nitbon2`, `bossgood` (Cazic Thule killed), `endgood` (its closing scene, the game's own "Completed Game" save, the title); the evil path from the same card: `bossevil` (Mithaniel Marr killed), `endbad` (its closing scene, the title); 21 levels + 4, 8 bosses killed, 1,159 pictures, the frame log and the master bus recorded (2 h 9 min) |
| `n11`, `n12` | the native Classic program (`rta_app_playc` from this round's main), a level-3 Barbarian from `n6`'s card (7 by the end) | the same 21 levels of acts 9-12, `bossgood` and `endgood` (its scene, the "Completed Game" save, the title), `bossevil`; 5 bosses killed, 1,120 pictures |
| `n7`, `e2`, `e5` | native, emulator, the same card | act bosses' damage, hit by hit (`fire1`, `bossevil`): the driver's question |
| `n8`-`n10`, `e3`, `e4`, `g7`, `g8` | native, emulator, Godot, the same card | **pictures a frame apart** (`playtest.py burst`) through a level change and through an opening scene skipped with START |
| `g11`, `g12`, `g13` | Godot | audio: the Godot mix and the sound engine's own output recorded side by side; a quiet frame-rate check of `fay2`, `fay3`, `nitdung2` |
| `sl-n`, `sl-g` | native, Godot | the shop, a save point, quit, start again, `Load Saved Game` |
| `gn*`, `nn*`, `bn*`, `ps-*`, `boot1`, `ld1` | both | the glitches' close looks: bursts of pictures at the name screen, level banners, the hub's edge, loads, boot |

**Last resorts used** (each in the run's `play.log`): teleports where the learnt way did not reach an exit or a
boss (blood1 4, strife 3, drundar 2, drunare 1, and in acts 2-8 where an exit's way was not found); the game's own
invulnerability after three deaths in `blood1` and for the act sweep (a level-1..6 character in act 2-8 levels);
a later act's level asked for through the game's own level change (`g_pendingLevel`) where no exit of the level
before leads there (the acts are entered from the hub's mission menu, which this driver used only for mission 1);
an act boss's hit points written down to a twentieth after 150 s of fighting.

## Glitches

Severity: **high** - a player cannot read, play on, or sees it everywhere; **medium** - plainly visible in
places; **low** - small, rare, or in test tools only.

| # | Severity | Where / when | Picture | Cause | Fix |
|---|---|---|---|---|---|
| G1 | high | Both programs: the **name-entry screen's letters** and **dialogue text** (Firiona's first lines) garbled in every second frame - the text flickers between right and wrong at 30 a second; not every run (a race) | `local/playtest/gn6/shots/b0*.png` (Godot), `nn3/shots/b0*.png` (native); the emulator: right | the renderer asks the game's texture headers for a two-field picture's height; a lookup that failed was asked again only when the header list grew - a header already listed whose block number the game fills in after the upload never answered, and the picture was woven by the sent size (half 128 instead of 89-90) | `a2c72f6` (render/renderer.cpp: asked again after 30 blanks) |
| G2 | medium | Both programs: a **level's name banner garbled** for its first frames ("Pjane �/ Va�e" for "Plane of Valor", arriving from the hub) | `local/playtest/n6/shots/0009-valor-walk.png` | G1's lookup asked again only every 30 blanks | `cea9017`: where the header list is kept by the program's sink (rta_app, the Godot library) every blank; banners of valor, fire1, hub, storm1 at 8 pictures a second right (`bn2`) |
| G3 | medium | Godot: **the art pack's two-field letters** (the name screen's font, 256 x 180 in a 256 x 256 page) never drawn: the game's own blurry font in their place | `local/playtest/gn1` against `gn4` | a two-field picture that covers part of its texture was left out ("until the shader has it") | `a2c72f6`: held whole and every draw of it sampled over the texels it covers, as the native program does (rta_pack.cpp, rta_drawer.cpp) |
| G4 | medium | Godot: **the hub's lower clouds a flat lavender disc** with a sharp curved edge, beside the island (seen from the mission portal) | `local/playtest/ps-g1/shots/0007-hub-place.png`; native `ps-n1` and emulator `e1/shots/0007-hub-ring.png`: clouds | the painted dome taken as whole packets, with the triangles the game drops under and round the eye | `b11a893`: dome draws take the list's own triangles (rta_scene.cpp); `ps-g9` = the emulator's |
| G5 | low | the portal walk (`shots.gd solo`: the portal's Classic card in a test): a script error at every frame | `local/playtest/g2/godot-1.out` (3,041 lines) | the walk replaced the portal's options with its own, without `host_party` / `join_code` | `295868e` |
| G6 | medium | Godot: **at every level change the old level showed through the loading black** (about ten frames of the last picture dimmed, after one black frame); natively (G10) half a loading screen. Found as "a black frame now and then" (12 in 2 h 40 min of `g2`): every such frame is at a level change | `local/playtest/g7/burst-lv-storm1/f-0001571-831.png` ... `f-0001579-10.png` (old level, dim); the emulator `e4/burst-lv-storm1/f00-1.png` ... `f00-7.png` (black) | the game turns both display circuits off (PMODE 0) while it draws the loading screen into the shown buffer; our GS model kept showing that buffer. The black frame itself is the game's own (the emulator: the scene, 7 black frames, the loading screen) | `1d0d106` (render/gs.cpp: nothing shown while PMODE has neither circuit on); `g8`: the scene, 10 black frames, the loading screen, as the emulator |
| G7 | low | Godot: **frame-time spikes during play** (Classic): 2-6 % of game frames over 25 ms in the play runs, 0.1 % over 50 ms; stalls of 0.5-13 s in the long `g2` run | `local/playtest/g2/frames.csv`, `playtest.py frames` | most are this run's own measuring: the driver reads ~1 MB of the object pool several times a second through the control port and the machine stood at a load average of 6-37 (the Remastered playtest's 2-4 copies, builds); the quiet `fps-verdict.md` measure of the same build: a steady 60 | **not ours to fix here** (the measure, not the game); the control port now marks its reads in the frame log so they can be left out; acts 9-12 in `g7`: `fay2` 45, `fay3` 24, `nitdung2` 44 a second during the driven run, **60.0 standing in the same levels on a quiet machine** (`g13`: 2-6 frames over 25 ms a level, none over 50) |
| G8 | low | Godot: audio - one 22 ms zero gap in 15 min (`g3`), 13 in 2 h 10 min (`g2`); `sound_late` 0 except `g2` (5, longest 388 ms) | `local/playtest/g3/master.wav` at 861.7 s | **not ours on a quiet machine**: `g12` recorded the Godot mix and the sound engine's own output (`--opt sound-wav`) side by side through 6 min of play - the same zero runs in both (142.4 ms twice, 153.8 s apart: the game's own material, as the exact repeats of 103.9 ms every 91 s in `storm3` and 110.9 ms every 47.7 s in `nit2` in `g7`); the host added none. `g3`'s one 22 ms run lay in continuous fight sound under a load of 6-37 | **closed** (nothing of ours to fix quietly; under heavy load see G7) |
| G9 | low | the launchers `Play Champions - native*.command` start `bin/rta_app` of **2026-10-22**: without this round's art-pack finding, Classic boss music off and G1-G2 | - | the program people start was not rebuilt after the Classic fixes | **fixed**: `bin/rta_app` rebuilt from main with G1, G2, G6/G10 (2026-10-27 08:24, `1d0d106`; `build.py --as rta_app_next`, then `mv`) |
| G10 | medium | native: **a half-made loading screen for two blanks at every level change** (the picture pushed to the top, "LOADING" at the top left, no band) before the right one | `local/playtest/n8/burst-lv-storm1/f-0007.png`, `burst-lv2-fire3/f-0007.png`; the emulator: black there | as G6: the shown buffer while PMODE has both circuits off (the native log: `pmode 0` for frames 1415-1421, the loading screen drawn into target 2, `pmode 2` at 1422) | `1d0d106`; `n10`: scene, 10 black blanks, the loading screen |
| G11 | low | native: **one start hung at boot and crashed** after 145 s (`rt_sleep`, access fault at 0x725411a7ec; the stack: the game's start-up `fn_003566f0` from its main loop) | `local/playtest/n11` (first start; its report is in the session's log, the folder was reused) | not found; the next three native starts booted normally. Other crashes in `local/` with the scheduler (`reschedule`) at quit are not this | **open** (not reproduced) |

## Checked and right (Ran)

- **Input**: the keyboard (W A S D walk, Return pauses and unpauses, L backs out) and a made controller (the left
  stick in 8 directions, half a stick half speed, inside the dead zone nothing, START pauses) move the character as
  the control port's own pad does (`g3`, an open place in blood1: 89-157 units a second along the camera's axes).
- **Menus**: the pause menu, options, the bag's six pages, the map, Firiona's dialogue and shop, the save point's
  card questions (overwrite: square), the level-up screen's ability and skill pages, the mission menu, the
  title's Load Saved Game - pictured in both programs.
- **Save and load**: a save at the save point, the program quit and started again, the card loaded from the
  title: level, place (0 units), experience, gold, character level, maximum hit points the same (`sl-n`, native).
  Godot: the save made at blood1's first save point, the program quit, started again through the portal, the card
  loaded from the title: blood1 at the save point, experience and gold as saved (`g2`, 21:57). (`sl-g`'s own save
  was not made: the driver did not reach the hub's save point - nothing on the card to load.)
- **The shop**: Firiona's lines, the shop, a purchase (200,000 -> 196,828 gold), the sell list (`sl-g`).
- **Deaths and restarts** (8 in `blood1` in Godot, 3 natively): the fall, the fade, the restart at the save.
- **Bosses killed by play**: the strife Orc (both programs), and with the last resort above the Iron Guardian,
  the Sea Monster, the Ogre of islgoth, the Tormentor, the Black Widow, the Gnaw Spawn and the Minotaur (Godot).
- **Online**: two Godot Classic copies, hub > blood1, played: 14,198 ticks in step, no shared column different.
- **Logs**: no script error and no warning of ours in any game run (`godot.out`, `native.out`).
- **Pictures** (about 4,900 taken, every eighth or so looked at in sheets of 16): no wrong or missing textures, z-fighting, stretched
  polygons, floating things or popping beyond the above; the one-colour pictures the detector flagged are the
  game's own black between a load and its first scene (the same in the emulator, `e1`).

## Not ours (the original's own; the emulator the same)

- **After an opening scene is skipped with START** (the open item of the first round): the emulator shows 86 black
  frames and then a 32-frame fade in; the native program 85 and the same fade; Godot 86 and the same fade (pictures a
  frame apart: `e4/burst-skip`, `n10/burst-skip`, `g8/burst-skip`). The "one" and "two" black pictures seen before were
  this second and a half of the game's own black at 0.3 s spacing.
- **The act bosses the native driver did not kill** (`valor2`, `fire1`, `fire2`, `fire5`): the damage is the game's -
  the same 7.8-9.2 a hit and the same share of swings that land natively and in the emulator from one card (`fire1`:
  34 of 184 and 42 of 186; `bossevil`: 1.44 a hit in both) - and the driver's: it read the whole object pool at every
  swing (a swing every second or two under the load of that night) and never swung at `fire5`'s dragon, whose own place
  is out of reach. Fixed in the driver (`ad4c94e`): the four bosses down natively in 175-225 s.
- **Creatures in acts 9-12 that take no damage**: `fay1`'s Orc Commander and the Orcs around him are the game's friends
  ("Talk to Orc Commander"); `faybonus`'s Wraith heals faster than a level-7 character hurts it (the hit points climb
  back from 159 to 3,158 natively; the level-13 Godot character killed it); `nitdung4`'s Agony and a Gnaw stand where
  the character never meets them. The driver's limits, not glitches.
- **"You must obtain the Final Shard"** at the last bosses' portals: the story's own key (the driver picks up gold and
  things, not the shard); the endings were reached by the game's own level change after each boss fell.

- **"Magic is not premitted in this area."** (innpit's notice): the game's own spelling.
- **The strife blocked direction** at (38, -3889): the emulator and the native program walk away freely in all
  eight directions from the same place (`e1`, `n5` probes); the Godot copy that stuck there had been put there by a
  teleport beside an Orc's corpse - the driver's, not a glitch.
- **The black before a level's opening scene** (the load's end): the emulator shows the same black (`e1/shots/0010-0019`).
- **Enemies "not reacting"** (the driver's `no-damage` suspect, 20-odd times): each picture showed the creature in its
  own hit or attack animation beside the character, or on a ledge the swing does not reach; none stood idle
  under attack. Not a glitch seen; no comparison with the emulator was made for them.

## Open

- G11 (one native start hung and crashed at boot, not reproduced), G7 under heavy load (the driver's reads and a busy
  machine; 60 when quiet).
- The Godot fix of G6 reaches the owner's `local/godot-spike` copy at its next `build.py` (the playtest built its own,
  `local/godot-play-classic3`).
- The driver: the story items that open the last portals, the friendly Orcs of `fay1`/`fay2` taken for foes, the
  native `bossgood` Cazic left at 10 hit points (its body out of reach of a level-4 character); the endings came by the
  game's level change.
- Not played: a person playing it through.

## Acts 9-12 and the open suspects (2026-10-27, 03:55-08:30; Ran)

Method as above: the portal's card (Godot) and the native program from a save, the levels in order, fights, things
picked up, chests, save points, level-ups through the game's screen, the boss of each level, a picture every 8 s and at
every event (2,280 in the two main runs; looked at in sheets of 16-24, roughly every fifth, and every suspect kind
opened), the logs, the frame log, the master bus recorded. The driver's last resorts as before (invulnerability, a
boss's hit points cut to a twentieth after 150 s, teleports where the way was not found, the game's level change where
no exit of the level before leads on); new: a teleport that lands where there is no ground puts the character back
(it had dropped to -100,000 below `fay2` - the driver's doing), Mithaniel Marr is a foe in `bossevil`.

- **Godot** (`g7`, level 10-17): all 21 levels of acts 9-11 and both last bosses; bosses down: storm1b's Goblin, the
  Tormentor (storm4), the Wraith (faybonus), the Minotaur (nit1), the Vampire Lord (nit2), the Spider Queen (nitbon2),
  **Cazic Thule** (bossgood), **Mithaniel Marr** (bossevil). Both closing scenes; after `endgood` the game wrote its own
  "Completed Game" save and went to the title, where the portal took over (the session is over at the front end).
  No death, no script error; the one warning is Godot's at exit (two `GDScriptFunctionState`s of the portal's test walk,
  `portal/dev/shots.gd`, awaiting when it quits - the test window, not the game).
- **Native** (`n11`, `n12`, level 3-7): the same 21 levels; bosses down: storm1b's Goblin, the Tormentor, the Minotaur,
  the Vampire Lord, the Spider Queen; Cazic and Marr left at 10 and 4 hit points (a level-4 character: the same 1.44 a
  hit as the emulator, which also lands 4 % of swings); `endgood` with the "Completed Game" save and the title.
- **G6 settled and fixed, G10 found and fixed** (above): pictures a frame apart in all three programs.
- **The skipped opening scene** settled: the game's own 1.4 s of black (above).
- **G8 closed** (above). **G9 fixed** (the launchers' program rebuilt).

## How to repeat

```
python3 tools/recomp/app/exitmap.py                                   # local/playtest/exitmap.json
python3 tools/recomp/app/playtest.py launch godot local/playtest/G --portal --audio    # or: native / emu
python3 tools/recomp/app/playtest.py local/playtest/G newgame 3 3     # Barbarian, stamina
python3 tools/recomp/app/playtest.py local/playtest/G mission         # Firiona, the gateway, mission 1
python3 tools/recomp/app/playtest.py local/playtest/G play --timeout 1500
python3 tools/recomp/app/playtest.py local/playtest/G exit strife
python3 tools/recomp/app/playtest.py local/playtest/G sweep drunarm drundar drunare boar1 innovat1 ... --timeout 120
python3 tools/recomp/app/playtest.py frames local/playtest/G/frames.csv
python3 tools/recomp/app/playtest.py local/playtest/G burst lv 160 --level storm1    # a frame apart through a level change
python3 tools/recomp/app/playtest.py local/playtest/G burst skip 160 --press start   # ... through a skipped opening scene
python3 tools/recomp/app/playtest.py launch godot local/playtest/G --audio -- -- --opt sound-wav=$PWD/local/playtest/G/engine.wav
local/audio-quality/bin/audiocheck local/playtest/G/master.wav --start 60 --len 600
RTA_GODOT_OUT=local/godot-play-classic python3 -B tools/play-net/roomparty.py local/playtest/room1 --copies godot,godot \
    --godot-control 31100 --godot-frame-log --play 2400 --level blood1 --play2 12000   # then playtest.py ROOM/run1/host-play ...
```
