# Classic played: a tester's run through the campaign

The task: play **Classic** (the portal's Classic choice in Godot, and the native Classic program) the
way a player does - fight through the levels, pick things up, use the levels' exits and the game's own
mission flow, level up, shop, save, load, die and restart - and look for glitches all the time; tell
ours from the original's against the emulator; fix ours. Started 2026-10-26 (evening). Every statement
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
| `g1`, `g2`, `g3`, `g4` | Godot Classic, **through the portal's Classic card** (`--portal`; `g1` `--edition classic`) | new game (Barbarian, the card's questions, the class, appearance, abilities, name); the hub: Firiona's offer, the mission portal, the mission menu; **Act 1 by play**: `blood1` fought through (deaths, a level-up through the game's screen, chests, barrels, gold, items, the save point), its exit to `strife`, `strife` fought through to its Orc boss; then `drunarm`, `drundar` (its Ogre "Thud"), `drunare` (the arena's knights and Cazic), `boar1`; acts 2-6 level by level (`innovat1` ... `torment3`, 30 levels in all, 4 bosses killed: Iron Guardian, Sea Monster, Ogre, Tormentor); a load of the card's save from the title (`Load Saved Game`) |
| `n4`, `n6` | native Classic program (`rta_app` built from main, `--as rta_app_playc`) | the same new game and mission flow; `blood1` and `strife` played (the strife Orc killed), the other Act 1 levels and acts 7-8 (`valor` ... `firbonus`, 15 levels) |
| `room1` | two Godot Classic copies in one room (`roomparty.py --godot-control`, a rendezvous of its own on 127.0.0.1) | hub > `blood1`, the host played by the driver through its control port: **every tick in step (14,198)**, both launched and finished, 1 death |
| `e1` | the emulator (Play!, no patch section) | the reference for each suspect below |
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
| G6 | low | Godot: **a black frame** now and then while playing (12 in 2 h 40 min of `g2`, 2 in 15 min of `g3`; a frame whose list draws 0-2 things after 90-1,400) | `local/playtest/g3/shots/few-3847-2.png` (black), `few-4261-0.png` (the frame before shown again: no flash) | not found: the game's list for that frame is all but empty (the library hands it over so); not seen natively (no counter there) | **open** - `dev/control.gd` marks and pictures every such frame (`fewshots DIR`) for the next look |
| G7 | low | Godot: **frame-time spikes during play** (Classic): 2-6 % of game frames over 25 ms in the play runs, 0.1 % over 50 ms; stalls of 0.5-13 s in the long `g2` run | `local/playtest/g2/frames.csv`, `playtest.py frames` | most are this run's own measuring: the driver reads ~1 MB of the object pool several times a second through the control port and the machine stood at a load average of 6-37 (the Remastered playtest's 2-4 copies, builds); the quiet `fps-verdict.md` measure of the same build: a steady 60 | **not ours to fix here** (the measure, not the game); the control port now marks its reads in the frame log so they can be left out |
| G8 | low | Godot: audio - one 22 ms zero gap in 15 min (`g3`), 13 in 2 h 10 min (`g2`); `sound_late` 0 except `g2` (5, longest 388 ms) | `local/playtest/g3/master.wav` at 861.7 s | the mixer was asked for sound on time (`master-clock.tsv`); `g2`'s are inside its long stalls (G7) | **open, not reproduced quietly** |
| G9 | low | the launchers `Play Champions - native*.command` start `bin/rta_app` of **2026-10-22**: without this round's art-pack finding, Classic boss music off and G1-G2 | - | the program people start was not rebuilt after the Classic fixes | **open** (the owner's launcher; `build.py --as rta_app_next` then `mv` over `rta_app`, as `build.py` says) |

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
  the Sea Monster, the Ogre of islgoth and the Tormentor (Godot).
- **Online**: two Godot Classic copies, hub > blood1, played: 14,198 ticks in step, no shared column different.
- **Logs**: no script error and no warning of ours in any game run (`godot.out`, `native.out`).
- **Pictures** (about 4,900 taken, every eighth or so looked at in sheets of 16): no wrong or missing textures, z-fighting, stretched
  polygons, floating things or popping beyond the above; the one-colour pictures the detector flagged are the
  game's own black between a load and its first scene (the same in the emulator, `e1`).

## Not ours (the original's own; the emulator the same)

- **"Magic is not premitted in this area."** (innpit's notice): the game's own spelling.
- **The strife blocked direction** at (38, -3889): the emulator and the native program walk away freely in all
  eight directions from the same place (`e1`, `n5` probes); the Godot copy that stuck there had been put there by a
  teleport beside an Orc's corpse - the driver's, not a glitch.
- **The black before a level's opening scene** (the load's end): the emulator shows the same black (`e1/shots/0010-0019`).
- **Enemies "not reacting"** (the driver's `no-damage` suspect, 20-odd times): each picture showed the creature in its
  own hit or attack animation beside the character, or on a ledge the swing does not reach; none stood idle
  under attack. Not a glitch seen; no comparison with the emulator was made for them.

## Open

- G6 (a near-empty list now and then in Godot), G8 (rare audio gaps under load), G9 (the launchers' old native
  program).
- After an opening scene is skipped with START: the native program shows one black picture (0.3 s apart), Godot
  two, before the level; the emulator's pictures (0.75 s apart) show none - too coarse to settle (`n5`, `g5`, `e1`).
- Native act bosses (valor2, fire1, fire2, fire5) were not killed in 6 minutes even with the last resort; the
  pictures show the character beside them swinging in a crowd - not established whether the driver's or the
  game's (no difference to the emulator was looked for).
- Not played: acts 9-12 (storm, fay, nit, the last bosses and endings) - the earlier checks loaded and pictured
  them (`classic-complete.md`); a person playing it through.

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
local/audio-quality/bin/audiocheck local/playtest/G/master.wav --start 60 --len 600
RTA_GODOT_OUT=local/godot-play-classic python3 -B tools/play-net/roomparty.py local/playtest/room1 --copies godot,godot \
    --godot-control 31100 --godot-frame-log --play 2400 --level blood1 --play2 12000   # then playtest.py ROOM/run1/host-play ...
```
