# Level flow: which files make a level, where players start, how levels change

Status 2026-10-17, SLUS-20973 v2.00. Branch `t3/research-levels`. **Round 2 (2026-10-18):
section 16 settles four points this document left contradictory or underspecified: the
WORLD entry, the light level, recall timing in cutscenes and the moving-piece arithmetic. It
does so by running the original code, and marks each statement it corrects with "→ 16.x"
where the statement stands.** **Round 3 (2026-10-20): section 17 is the start rule for the
18 levels a radius-4 query at the origin calls empty.** This document gathers in
one place the contracts a native client needs to load an arbitrary level and move between
levels, which until now were spread over `docs/mainloop.md` 7, `docs/data-tables.md` 7,
`docs/spec/object-system.md` 7, `docs/issues/arena-entry.md`, `docs/audio-save.md`,
`docs/formats/world.md` and `docs/monsters-2.md`. It adds what those leave out, and section
14 lists the corrections it makes to them.

`tools/ref_levels.py` is the executable form (stdlib plus `tools/ref_world.py`'s float
arithmetic), with synthetic-fixture tests in `tools/test_ref_levels.py`.

## How this was established

The code was read statically in `SLUS_209.73` (Ghidra exports and `tools/dis.py`). Data
regularities come from a scan of every archive on the disc image (120 `.GOB`, 119 with an
`objects.ob`, 120 `script.scr`, 118 with a `.world`). Only counts are reported here.
**Nothing in this document was run on a console, in PCSX2 or in the Play! emulator.** Section
16 alone was **Executed** function by function in `tools/ee_emu.py`
(`tools/difftest_levels.py`). Section 17 was executed the same way
(`tools/difftest_levels_r3.py`). Of
the function bodies, `world_findMovingPiece` 0x182768, `water_test` 0x189438 and the
placement code 0x321100–0x321240 were re-read instruction by instruction while writing
`tools/ref_levels.py`. The rest were read once, by one reader.

Tags as in CONTRIBUTING.md: **O** observed at the address given; **D** a regularity in the
disc data with its count, no code read for it; **I** inferred; **U** unknown, with what
would settle it.

---

## 1. Names

| Buffer | Address | Size | Meaning | Tag |
|---|---|---|---|---|
| `g_pendingLevel` | 0x41b6d0 | 0x50 | requested level, `name` or `name_sub`; non-empty means a change is pending | O |
| orientation byte | 0x41b720 | 1 | written by every requester; see 6.3 | O |
| `g_levelName` | 0x41b721 | 0x50 | current level, part before the first `_` | O |
| `g_levelSubName` | 0x41b771 | 0x50 | part after the first `_`, may be empty | O |
| orientation copy | 0x41b7c1 | 1 | the loader's copy of 0x41b720; no reader found | O |
| `g_prevLevelName` | 0x41b7c2 | 0x50 | the level just left, qualified (`a_b` or `a`) | O 0x321030–0x32105c |
| `g_levelTexName` | 0x44fe18 | | copy of the base name, used for `.TEX`/`.VAT` and the loading picture | O 0x321110 |

- The request is split at the **first** `_` (O 0x321064–0x3210f8). `level_getQualifiedName`
  0x1ec0f0 rebuilds `base_sub`, or `base` when the sub-name is empty.
- **Every file name is built from the base name.** The sub-name only selects the
  level-table row (2), keys the saved state (7.3) and the jump-gate list (9), and goes into
  `g_prevLevelName` (O 0x1e5794–0x1e57b4, 0x1e5f88, 0x217978).
- No upper- or lower-casing happens on this path. `cd_findFile` 0x1724fc upper-cases the
  name and appends `;1` before an exact compare with the disc directory, so disc files are
  effectively case-insensitive. Entries inside a lump are found with an exact `strcmp`
  (`lump_findEntry` 0x171de4, `res_find` 0x17365c), so they are case-sensitive (O).
- All name buffers are 0x50 bytes, copied with `strcpy` and no length check (O).
- D: all 163 `newWorld` calls in the shipped scripts pass a plain name; **none uses
  `name_sub`**. So with shipped content the sub-name is always empty, unless a save header
  carries one.

## 2. Level table row (`g_levelTable` 0x4f7210)

There are 90 rows of 0x30 bytes, ended by a null name. The terminator row doubles as the
**default row** (`docs/data-tables.md` 7.1 has the field list). `game_loadLevel` searches the
table three times, taking the first match of each pass in table order (O 0x1e5790–0x1e58c8):

1. `strcmp(row, base + "_" + sub) == 0`. The `_` is always appended, so a plain name never
   matches here;
2. the row starts with `base` (`strncmp(base, row, strlen(base))`);
3. the row occurs inside `base` (`strstr(base, row)`);
4. otherwise the default row: monster level byte 1, +5 = 2, kill plane −100000,
   +0x0c/+0x10 = −100000/100000, water pool 48, +0x18 = 0, +0x1c = 1.0, flags 0, sound 0,
   +0x2c = 0 (O, data at 0x4f7210 + 90 × 0x30).

Fields used by a native client:

| Row | Use | Tag |
|---|---|---|
| +0x04 | monster level: `g_levelMonsterLevel` = byte + 2. PvP mode B and difficulty 1 give 3.0. Difficulties 2–5 then overwrite it with `(byte + 2) × 0.75 + {34, 61, 88, 115}`. Finally `stomedal` = 1.0 and `innpit` = 2.0 | O 0x1e5b70–0x1e5c94 |
| +0x08 | `g_killPlaneZ` 0x4f7188 | O; D: −100000 in every row, so it never fires |
| +0x14 | number of **water simulation blocks** (section 12) (0x12b0 bytes each; allocation tag "water patches", `water_allocPool` 0x186dbc). Not allocated for `intro` | O; this settles the U in data-tables.md 7.1 |
| +0x20 | level flag word 0x44fe08. Bits read here: 0x8 full water masks; 0x10 random water splashes; 0x800 no saved level state; 0x1000 deadly water; 0x04000000 and 0x20000000 give base light level 0x40 / 0x20, and **0x40 when both are set** (→ 16.2: round 1 said "level-light alpha" and implied 0x20 wins) | O 0x187628, 0x1876e0, 0x21777c, `Player_move`, 0x1e60e0–0x1e6154 |
| +0x05, +0x0c, +0x10, +0x18, +0x1c, +0x2c | stored (0x41c16c/70, 0x4f718c, 0x4f7190, 0x4f7208, 0x44f030, 0x4f7152; +0x2c read unsigned); purposes U | O stores |

D: all 90 row names have a `.GOB`. 30 archives have no row of their own and take whatever
row passes 2–3 or the default give them. Which row each of the 30 resolves to was not
tabulated (U: run `ref_levels.find_level_row` over the real table).

## 3. Manifest: the files of a level, in load order

`game_loadLevel(base)` 0x1e55c0–0x1e6234. **Required** means the game crashes when the file is
missing: `lump_load` 0x173558 prints an error and stores to address 0
(0x173630–0x17363c), and the raw CD read 0x1729e8 does the same (0x172a4c–0x172a64). A lump
already resident is returned without a read (0x173568). All rows O.

| # | Step | File | Required? | Address |
|---|---|---|---|---|
| 1 | clear medal/ack words; loading flag 0x4f7198 = 1 (script `levelLoading`) | – | – | 0x1e55f0–0x1e5638 |
| 3 | `game_clearLevel(1)`: every object destroyed, keep-level-0 lumps unloaded | – | – | 0x1e5674 |
| 4a | not `intro`, `hud.lmp` not resident: unload to keep 9; item resources (223 shared draws); `fx.lmp`, `hud.lmp`, `mapicons.lmp`, `icons.lmp`; raise keep to 10 | 4 lumps | required | 0x1e56a0–0x1e5704 |
| 4b | not `intro`: `game_loadPlayerLumps` 0x1e5148 (12 race lumps, table 0x4f71a8 or the low-detail table 0x4f71d8 with ≥ 2 players; hair, beard and body from `select.lmp`/`select2.lmp`). If it reloads anything, the level is cleared again. `g_gameLevelLoaded` 0x4f85b0 = 1 | player lumps | required | 0x1e5708–0x1e5728 |
| 4c | `intro`: `g_gameLevelLoaded` = 0, unload to keep 10, release the equipment cache | – | – | 0x1e5730 |
| 5 | loading screen, 3.1 | `L<alias>.LMP` or `LMISS.LMP`; `LOADMISC.LMP` | picture optional (falls back), loadmisc required | 0x1e5758, 0x321e60 |
| 6 | level-table row, section 2 | – | – | 0x1e5790 |
| 7 | `gob_loadAll("<base>.gob")`, 3.2. The `.world` fixup inside it reads the first 0x5000 bytes of `<BASE>.TEX` | `<BASE>.GOB`, `<BASE>.TEX` | required | 0x1e58e8, 0x181f08 |
| 8 | `g_world` 0x44fdc8 = the first entry with extension `world` in `<base>.lmp`, in lump (directory) order, with no null test (→ 16.1, Executed; round 1's `ref_levels.py` sorted instead) | `*.world` | required | 0x1e5978–0x1e59bc |
| 9 | `g_cosmeticSeed = g_randSeed` | – | – | 0x1e59c4 |
| 10 | not a recall leg (0x41b51c, 0x41b51e): voice directory `dialog.bin`; the first record whose name contains `enttag` starts the entry music, otherwise stream 2 is stopped | `dialog.bin` | optional in effect | 0x1e59c0–0x1e5a88 |
| 11 | `ambient.bin` copied into a 5120-byte stack buffer (unbounded copy) and parsed; `ambient_parse(0)` when absent | `ambient.bin` | optional | 0x1e5ab4–0x1e5b3c |
| 12 | row fields (section 2) | – | – | 0x1e5b54–0x1e5c94 |
| 13 | not `intro`: water pool, row +0x14 | – | – | 0x1e5ca4–0x1e5cd8 |
| 14 | `arena_init` (only in PvP mode B: `arena.lmp`, `pvpfont.lmp`) | 2 lumps | required in PvP B | 0x1e5cdc |
| 15 | not `intro`: `gooddog.lmp`, `skele_b.lmp` | 2 lumps | required | 0x1e5cf4–0x1e5d0c |
| 16 | `world_prepare` 0x182360: `<name>.lmp` for every chunk with flag 0x800 (scenery model); always-loaded texture cells; segment cache (section 13) | model lumps; `.TEX` | required | 0x1e5d2c, 0x182390–0x1823e8 |
| 17 | 0x44f030 = row +0x1c; `dome.lmp` if resident (0 otherwise) | `dome.lmp` | optional | 0x1e5d40–0x1e5d68 |
| 18 | `waterenv.lmp`; `water_setup` with its first `.tex` entry, without a null test | `waterenv.lmp` | required | 0x1e5d60–0x1e5d84 |
| 20 | kill plane and the other row floats; potion counters and level timer 0x4f85cc = 0; sound set-up | – | – | 0x1e5da0–0x1e5df8 |
| 24 | `g_levelBounds` 0x86aee8 = union of all chunk bounds | – | – | 0x1e5f14–0x1e5f6c |
| 26 | `hub` only: `msel.lmp` | `msel.lmp` | required in hub | 0x1e5fc8–0x1e5fe8 |
| 27 | `objects_levelReset`; outside the front end, reload `monsters.bal` | balance lump | – | 0x1e5fec |
| 28 | `level_loadScriptAndObjects`, 3.3 | `script.scr`, `objects.ob` | script optional, objects required | 0x1e6000 |
| 29 | `arena_begin` (PvP B) | – | – | 0x1e6028 |
| 30 | **`world_disableUnclaimedPieces`** (11.2); `paths_joinSegments` | – | – | 0x1e6060 |
| 32 | `script_runPostAction`: a post action left over from the old level runs in the new script (FINDINGS E10) | – | – | 0x1e60b8 |
| 33 | loading flag 0x4f7198 = 0 | – | – | 0x1e60d4 |
| 34 | level light: sun direction 0x44fdf8, colours 0x44fde0, alphas 0; the **base light level** from the flag word (section 2; → 16.2) | – | – | 0x1e60e0 |
| 35 | `save_armAutosave`, `dialog_loadBox` | – | – | 0x1e6174 |
| 36 | every player record +0x4c27 = 30 (hit immunity) | – | – | 0x1e61bc–0x1e61f0 |

Then `mainloop_loadRequestedWorld` places the players (section 5). The main loop runs the
warm-up, the deferred calls, the network barrier and shop stock, and after the load uploads
the environment texture of `env.lmp` if it is resident (`docs/mainloop.md` 7 steps 7–11).

### 3.1 Loading picture (`loadscreen_start` 0x321e60) — O

The base name first passes an alias table (`loadscreen_selectWorldAlias` 0x321c9c; first match
wins):

| Rule | Result |
|---|---|
| contains `blo` | `blood1` |
| equals `innovat2` | `innova2` |
| contains `val` | `valor` |
| contains `bas` | `bastion1` |
| contains `nitdung` | `nitdung1/2/4` become `nitdun1/2/4`; other names unchanged |
| contains `torme` | `tormenta/tormentb/torment2/torment3` become `torma/tormb/torm2/torm3`; others unchanged |
| equals `pvpfire2` | `pvpfir2` |
| otherwise | the name itself |

The file is `"l" + alias`, **cut to 8 characters**, then `.lmp`. If it is absent the same name
is tried once more, and then `lmiss.lmp` is used. The picture is the entry `shot.tex`. The
title texture comes from `loadmisc.lmp` and is chosen by `g_language`. D: on the disc 32
names are long enough to be cut, and 18 levels have no picture of their own and fall back to
`LMISS.LMP`.

### 3.2 Archives (`gob_loadAll` 0x1737d8) — O, D

- Directory: 0x800 bytes of 0x28-byte records (name, size at +0x24), ended by an empty name.
  **The record's offset field is ignored**: lumps are read back to back from file offset
  0x800, each rounded up to 0x800 (0x173890–0x1738a8). D: all 120 disc archives are laid out
  that way, so both readings agree on shipped files.
- Each lump is fixed up on arrival (`lump_fixup` 0x1717d0: `ntsc_dialog.bin` is renamed
  `dialog.bin` and `pal_*` entries are dropped). Two archive lumps are renamed:
  `gaydark1/2.lmp` become `faydark1/2.lmp` (0x173908–0x1739e8).
- D: every archive holds `<name>.lmp`, `env.lmp` and `waterenv.lmp`; 21 also hold `dome.lmp`.
  None of those three exists as a loose file, so they must come from the archive. 9 archives
  have no `.TEX` and 4 no `.VAT`; loading one of the 9 would crash in the world fixup (I).
  All 33 model-chunk lump names exist in their archive or in `DATA/`.
- `.VAT` is never opened by the load. It is opened by name (`stream_levelFileName` 0x216820)
  when a level voice stream plays (O for the name; I for the timing).
- Keep levels: 10 for fonts, interface and the four HUD lumps; 5 for player lumps; 0 for
  everything of the level (O).

### 3.3 Script and objects (`level_loadScriptAndObjects(base, qualified)` 0x217978) — O

```
look up qualified in the saved-state directory (10 entries; 7.3)
lmp = lump_load(base + ".lmp")
script machine = entry "script.scr" if present and non-empty, else none
g_playerStartRank 0x4f7108 = g_loadedFromSave 0x8e1ad6 ? 3 : 0;  g_loadedFromSave = 0
run "preStart"
if a saved state exists:
    build the saved object records first (world_loadRecords(saved, filterOnly 0)),
    then the decals, then the explored map
world_loadRecords(objects.ob, filterOnly = saved state exists)
run "start"
```

- With a saved state, only the 18 save-filter classes are built from `objects.ob`
  (`world_saveFilter` 0x15d9c8, list 0x403a68, case-insensitive exact): lights, fire pots,
  bombs, `Blocker`, `Line`, `customVars`, `clearColor`, `zzRoutepoint` and a few more (the
  list is in `ref_levels.SAVE_FILTER_CLASSES`). Everything else, start markers included,
  comes back from the saved records. Those records are written in grid order, not file
  order, so among several `default` markers a re-entry can pick a different one from the
  first visit (I; U until a level with several markers is saved and re-entered).
- Records are built strictly in file order, and the objects deleted in their constructor are
  flushed at the end of `world_loadRecords` (0x14ea0c–0x14ea5c).
- The skip byte 0x4f8b58 tested before both script entries has no writer (two scans), so
  `preStart` and `start` always run (I; U through a computed pointer).

## 4. Where a new game, an act and a mission start

- **There is no "starting floor" field** in any table (level, act, mission, `objects.ob`
  header) (O).
- A new game starts in **`hub`**. `frontend_startPlayerSelect` 0x1e3ba0 sets the
  destination to `hub`, or to the arena level in PvP mode B. `playerSel_finish` 0x22a360
  copies it to the request and replaces `hub` with `game_getHubName()` 0x1ec300, which gives
  `hub2` only when the decision was made, the player is evil and mission 1 is complete
  (O 0x22a450–0x22a4b4).
- Story start of each mission: mission table row +0x08 (+0x0c when non-null and evil), chosen
  in `missionMenu_run` state 8 (`docs/data-tables.md` 7.4; O 0x2321c4–0x2322d4).
- The 13 act lists (`g_actLevelTables` 0x4f8e48, counts 0x4f8e10, `g_actCount` 0x4f8e7c) all
  start with `hub`. They size saved states and decide act changes (7.2); they never choose
  where to start (O).
- Boot writes `strife` (`main` 0x323edc); the front end writes `intro`.

**What "starting floor" amounts to in practice is the spawn height rule (5.3):** a player
starts on the **highest** terrain sample within 12 units of the chosen spot. The marker's own
height is ignored.

## 5. Start markers and player placement

### 5.1 State

| Address | Layout | Writers (O) |
|---|---|---|
| `g_spawnPos` 0x4f70d0 | 4 × (x, y, z) floats | `Player1_ctor`, `JumpGate_ctor` 0x27ca44, `save_load` 0x221f28, placement 0x3211b4 / 0x321204 / 0x32130c / 0x321368 |
| `g_spawnFacing` 0x4f8410 | 4 × u16 (65536 = full turn, I) | `Player1_ctor` 0x158b9c, `JumpGate_ctor` 0x27ca70, `save_load` 0x221eec, placement 0x321364 |
| `g_playerStartRank` 0x4f7108 | s8 | 3.3 (0 or 3), `Player1_ctor`, `JumpGate_ctor` (3) |
| `g_entranceName` 0x4f8468 | string | script `setEntrance` 0x142a94 and `game_resetState` 0x1e6fc4 only. **A level change does not clear it** |
| 0x41b51c | s8 | "returning from recall": set by `player_recallTick` 0x1b628c, cleared at 0x3211c4 |
| 0x41b51e | s8 | "going to the hub by recall": set at 0x1b6260, cleared at the end of placement 0x3214c0 |
| 0x41b520 | 4 × xyz | recall return positions |

All of these are 0 in the executable's data (O). **Nothing resets the spawn positions or
facings between levels** (→ 17.4). The start rank is reset, to 0 or to 3, before the
markers run.

### 5.2 Which marker places the players

Markers rank themselves while the records are built, in file order. `Player1_ctor` 0x158928
(O; `docs/spec/object-system.md` 7.3 and `ref_objects.World.player1_marker` agree):

| Test, in this order | Result |
|---|---|
| rank is already 3 | nothing |
| rank ≤ 0 | take, rank 1 |
| rank is 1 and `default` is a non-zero integer | take, rank 1 |
| `from` equals `g_prevLevelName` and not 0x41b51e | take, rank 2 |
| otherwise, 0x41b51e set and `from` is `gate` | take, rank 3 |
| `name` equals `g_entranceName` and not 0x41b51e | take, rank 3 |

A marker that takes fills **all four** slots, whatever the player count: for each slot
`world_findFreeSpot(marker, spread 36, radius 24, anyHeight 0)` and one shared draw,
`facing = angle + (draw >> 16) % 4000 − 2000`. Consequences:

- among `default` markers, or several whose `from` matches, the **last** in the file wins;
- among rank-3 markers, the **first** wins;
- every taking marker spends four searches and four draws, even when a later marker
  overwrites the result.

Other rank-3 sources (O):

- **Gate arrival.** `JumpGate_ctor` 0x27c694 (classes `Portal`, `PortalHurt`) acts when the
  travel state 0x500ae8 ≠ 0 and the gate menu was not given a fixed destination
  (0x8e3c34 = 0). For each slot below the player count it calls
  `world_findFreeSpot(gate, 36, 24, anyHeight 1)` and sets the facing to a full shared draw
  `>> 16`. It then sets rank 3 without testing the rank (0x27c974–0x27ca84).
- **Load from a save.** `save_load` writes the saved positions and angles and makes the start
  rank 3.

If no marker takes (rank 0 after the objects), the spawn slots keep the **previous level's**
values (O: no writer resets them).

D (119 levels):

- `Player1` markers: 18 levels have none, 61 have one, 40 have more than one (up to 9);
  182 records in all.
- Properties on them: `from` 87, `name` 51, `default=1` 28, none 73. One record has the
  misspelt `defualt=1`, which does nothing.
- **No marker has `from=gate`**, and **no object of any class has `orientation=`**.
- The 18 levels without a marker are the front end, two cutscene archives and the 15
  `comp*`/`pvp*` arenas. The arenas place players through `ArenaPlayerStart` (15 records) and
  `ArenaPlayerAlternate` (232) instead, via 0x30503c and `arena_pickSpawnPoint` 0x3050a4
  (→ 17.3, 18).
- 38 levels have one `Portal` each.
- Of 72 (`setEntrance`, `newWorld`) pairs, 58 have a matching `name` marker in the destination.
  The other 14 fall back to the `from`/default rules.

### 5.3 Placement after the load (`mainloop_loadRequestedWorld` 0x321160–0x3214c0) — O

```
if 0x41b51c:  for slot < numPlayers: spawn[slot].x, .y = 0x41b520[slot].x, .y   (z not copied)
              0x41b51c = 0
for slot < numPlayers:
    spawn[slot].z = terrain_height(radius 12.0, spawn[slot])          (0x321220)
if g_gameLevelLoaded and not g_pvpModeB:
    for slot < numPlayers, in order:
        if slot != 0 and rank != 3:
            spawn[slot] = world_findFreeSpot(spawn[slot], 36, 14, anyHeight 0)
            facing[slot] += 8000;  spawn[slot].z = terrain_height(12.0, spawn[slot])
        if record hp > 0 and peer active and (no medal mission or slot == medal slot):
            Player_ctor(pool_new(0x590), spawn[slot], facing[slot], slot)
        if act changed and card state != 4 and no deathTask: record +0x24 = "None"
0x41b51e = 0
```

- `terrain_height` 0x183820 returns the **highest** sample whose cell centre lies within the
  radius, and **never reads the query's z**. With no floor it returns −1000000.0. The
  height-respecting `terrain_heightBelow` 0x1834a8 is not used here. So on a bridge or a
  walkway over a floor, the player starts on the top surface (O for the calls; I for the
  consequence).
- The scattered positions and the extra 8000 of facing are **written back** to the globals,
  so a later level without a marker inherits them and adds 8000 again (O).
- Players are created only inside the "real level, not PvP B" test, and in a medal mission
  only the medal slot is created. `docs/mainloop.md` 7 step 6 and
  `docs/issues/arena-entry.md` 2 leave this out (section 14).
- What `Player_ctor` does with the position, and that a sentinel from this snap is stored
  as-is, is in section 17 (→ 17.2). The kill plane cannot kill that spawn: it is off in
  every level-table row (section 2).

## 6. Requesting a level change

### 6.1 Who writes the request (O unless marked)

| Writer | Name written | Orientation | Condition |
|---|---|---|---|
| scripts `newWorld` 7 / `newWorldAlways` 8 → `script_setNextWorld` 0x1472c4 | argument | `orientation=` of the selected object (last wins), else 0xff | `newWorld_netGate` 0x143d04 unless in a post action |
| `newWorldParameter` 107 0x1471fc | the selected object's `level=` | as above | no gate |
| `simpleNewWorld` 6 0x143e70 | argument | 0xff | same gate |
| dialog end 0x22f7c4–0x22f7ec | the `newWorldPost` buffer 0x4fdcf0, if non-empty | 0xff | then the post action |
| pause-menu level warp (messages 7, 11; 0x1d9004, 0x18cb80) | menu entry | 0xff | only with `g_debugCheats` (`docs/ui.md`) |
| `player_recallTick` 0x1b6264–0x1b62fc | hub name, or player 0's record +0x24 | 0xfd | section 10 |
| `deathTask` 0x1e76c4 | `g_levelTexName` (base; sub dropped) | 0xfd | party wipe in a level outside every act |
| `save_load` 0x2220f4 | header name (`a_b` when the sub is set) | 0xfd | reload or card load |
| `game_openMissionMenu` 0x1eb5b4 | hub name | 0xff | pause-menu "exit mission" (message 8, then a countdown), medal-screen cancel, or the medal player's slot dropping |
| `script_runMedalSuccess` 0x141b98 / `runMedalFail` 0x141e24 | `g_levelName` (retry) | 0xff | medal player's confirm |
| `missionMenu_run` 0x232220 | mission row +0x08 / +0x0c / +0x10 / +0x14 | 0xff | chooser's lockstep pad |
| `jumpgate_menuRun` state 5 0x27e1d0 | the menu's fixed destination, else the selected list entry | 0xff | section 9 |
| `arena_runTask` 0x306cb8 | arena rotation | 0xff | PvP, mode A set (→ 18) |
| `net_launchUpdate` 0x137560 | hub name or the PvP arena | 0xff | net launch |
| front end 0x1e20ac, 0x1e24f4; `main` 0x323ef4; `playerSel_finish` 0x22a424 | `intro`, `strife`, new-game destination | 0xff | — |
| front end "Start Net Game" 0x1e17d8 | `kelethin` | 0xff | debug entry; there is no `KELETHIN.GOB` (U whether it is reachable) |

Two places clear the request:

- the per-frame cancel (`mainloop_runSession` 0x322c00–0x322ca8). It fires when a level is
  loaded, the front end is not running, this machine's card is not busy, PvP B is off and
  **no player record has hp above 0**. It runs outside the lockstep and reads per-machine
  card state (`docs/mainloop.md` P1);
- the loader itself, after it splits the name.

### 6.2 The `newWorld` gate

`newWorld_netGate` 0x143d04 (`docs/spec/script-builtins.md` 1.10): in a net game with an active
player, the change is refused while that player's 600-tick cooldown (record +0x4bca) runs and
at least two players are alive. Otherwise the cooldown is set to 600. Offline it always passes.

### 6.3 The orientation byte does nothing in v2.00

The only reader of 0x41b720 is the loader. It copies the byte to 0x41b7c1 and writes 0xfe back
(O 0x321118–0x321138, re-read). Two static scans found no reader of 0x41b7c1. D: no object on
the disc has an `orientation=` property. A native client may keep the byte but must not act on
it. U: a read through a computed pointer; settle with a read watchpoint on 0x41b7c1 across a
level change.

### 6.4 How exits are authored (D, 120 scripts and 119 object files)

- **Exits are scripts.** Except for recall, gates, party wipes, medal screens and the mission
  menu, the engine never chooses a destination.
- Following each trigger's script through `callScript` (depth ≤ 6) to a `newWorld` call:

  | Exit | Count |
  |---|---|
  | `PushTrigger` whose `action` snippet calls `newWorld` directly | 79 |
  | the same, preceded by `setEntrance` | 41 |
  | `PushTrigger` through `callScript` (without / with `setEntrance`) | 9 / 7 |
  | rectangle `Trigger` (direct without / with `setEntrance`; through `callScript`) | 11 / 1; 4 |

- Built-in call counts: `newWorld` 163 calls in 71 scripts, `setEntrance` 76 in 30,
  `simpleNewWorld` 4, `newWorldPost` 5, `saveCheckPoint` 16. `newWorldAlways`,
  `newWorldParameter` and `loadCheckPoint` are never called.

## 7. The change itself, and what survives it

### 7.1 Sequence, request to first tick

Steps marked † are not in `docs/mainloop.md` 7.

1. Inside tick N a writer of 6.1 fills the request. In a net game the rest of that
   `net_frameLoop` does nothing (`docs/netcode.md`).
2. Next main-loop pass: the cancel test (6.1). In a net game, the save wait and
   `net_flushBeforeLoad`. Then `g_simFrame = 0`, the ambient countdown is set to 60 (unless on
   a recall leg), and the display is blanked and the camera reset.
3. `mainloop_loadRequestedWorld` 0x320edc (O):
   1. unless `deathTask` runs: `save_storeLevelState(qualified old name)` (7.3); † if a medal
      mission used `savePlayer`, the player record is restored (0x320f60);
   2. act check (7.2). On an act change, unless the card latch 0x4f8f28 is set or `deathTask`
      runs: clear the save buffer, reset the gate list to [hub name], clear quests, remove
      items with flag 39, zero every quest value (the names stay);
   3. `playerSel_applyPending`;
   4. `g_prevLevelName` = qualified old name; split the request; clear the request;
      `g_levelTexName` = base; † orientation copied and set to 0xfe; sound muted for 0.05 s;
   5. `game_loadLevel(base)` (section 3);
   6. placement (5.3), including † the recall x/y copy, † the medal-slot filter, † the write-back
      of scattered positions, and † `None` in every record's recall destination on an act
      change;
   7. if the level had no saved state, the idle-voice countdown is set to 300.
4. Warm-up loop, deferred calls once, network barrier, shop stock, loading screen off
   (`docs/mainloop.md` 7 steps 7–11). The first tick is F0 = N + 1 on every machine
   (`docs/issues/arena-entry.md` 1.3).

### 7.2 Acts

`save_findAct(name)` 0x217d30 matches a row when the name **starts with** the row name
(`strncmp(row, name, strlen(row))`), searching the current act first and then acts 0–12; it
returns −1 if nothing matches. `save_actChanged` 0x217f70 switches to the found act when it
differs from the current one. A session starts at act −1 (`save_setAct(-1)` 0x1e6f14), so its
first real level is always an act change (O; I for the consequence). The 13 lists, with the
size of each level's saved state, are read from the executable at 0x4f8e48. A native client
should take them from there rather than copy them.

### 7.3 Saved level states (`save_storeLevelState` 0x21777c) — O

- Nothing is stored while this machine's card state is 4 or the level has flag 0x800.
- The size comes from the act table: `hub*` uses row 0 of the current act, and any other
  level must be an exact row of the **current** act. Levels outside it are not stored, and so
  are never restored and never checkpointed. With byte 0x4f85c5 set, the size is fixed at
  35000.
- The directory `g_saveLevelDir` 0x8ab590 has 10 entries of {char[0x14] key, u32 size}. The
  key is the qualified name. The data area runs from save buffer +0x16118 to 0x4bc78.
- An entry is created even when the data will not fit. With all 10 entries used and no
  match, the code writes an 11th entry over the 0x18 bytes before the data (I: unreachable
  with shipped acts, whose longest list has 10 levels).
- What is saved: object records with their state bytes, decals, the explored map
  (`docs/audio-save.md`). `save_build` 0x221914 also stores the current level's state, so
  every checkpoint includes it.

### 7.4 Kept and reset

| Kept across a change | Notes |
|---|---|
| player records (0x4c30 each): stats, hp, bags, gold, medals, quest list, recall destination +0x24 / +0x44, `newWorld` cooldown +0x4bca | the Player objects are destroyed and rebuilt |
| quest variables, gate list, save buffer and level states | cleared only on an act change |
| post action | runs in the new level (FINDINGS E10) |
| `g_entranceName` | never cleared by a change |
| jump-gate travel state 0x500ae8 and its tasks | only while travelling (`jumpgate_removeTasksIfIdle` 0x27dac8) |
| `g_spawnPos`, `g_spawnFacing` | never reset |
| recall flags and positions | consumed by the load |

`game_clearLevel` 0x1e4e88 resets the rest (O). That covers objects, the name table, the pool,
decals, paths, particles, the recall countdown, alternate death, save inhibit, deferred script
calls, dialog, `g_paused`, and the keep-level-0 lumps. It also resets the world's pieces and
water: all pieces are released, back at their rest pose with collision on, but **element z is
not restored** (0x18b270); and every water block is released.

## 8. Triggers and interactables

- **`Trigger`** (0x70 bytes; `Trigger_ctor` 0x1ecdf4). An axis-aligned rectangle from (x, y)
  to (x + w, y − h), stored as min/max, from the integer properties `w` and `h`. Its script
  is the property `t`; the angle is ignored. `Trigger_contains` 0x1ed238 tests x and y
  inclusively, with no height (O). `Trigger_run` 0x1ecf3c is edge-driven on "somebody
  inside". The first player in slot order inside becomes the active player; entering runs
  `t` and leaving runs `"not" + t`; nothing happens while a recall counts down. It runs on
  one of the fifteen 15-frame lists. Its saved state is 5 bytes: the delay +0x64 and the
  inside flag +0x60 (O; `docs/spec/script-builtins.md` 1.9). D: 95 triggers in 48 levels,
  properties only `w`, `h` and `t`, every angle 0; no script defines a `"not"+t` entry.
- **`PushTrigger`** (0x4c bytes; ctor 0x1ec900). An interactable, never run.
  `PushTrigger_prompt` 0x1eca94: in a net game a `netHostOnly` object is usable only by the
  first active slot. Then every `key` predicate must return non-zero. `PushTrigger_interact`
  0x1ecc70 refuses `shop` objects while another player is busy, runs every `action=` (raw
  unless `offOnly`), and deletes the object when `once` is set (O). D: 205 in 74 levels.
- **`MonsterTrigger`** (radius 60 by default; `radius` overrides) counts creatures. It is
  never an exit (O; D 201 in 8 levels).
- The active player for an interact is the presser (`Player_interact` 0x1b2b70). The prompt
  predicates also run from `Player_draw` on the owner's machine (`docs/script.md` P1).

## 9. Jump gates

- **Destinations.** 0x8e3a50 holds 15 × char[0x20] qualified names; the count byte is at
  0x8e3c30. `jumpgate_addCurrentLevel` 0x27db60 appends the current qualified name unless it
  is already listed. After an append it removes the first entry that contains `hub` but is
  not the current hub name (the stale hub after the hub-to-hub2 switch). **There is no bound
  check**: a 16th append would overwrite the count byte (O; D: no act has that many gates).
  `jumpgate_resetDestinations` 0x27db00 (act change only, not while the card latch is set)
  resets the list to [hub name]. The list is saved at save +0x134 (count u32 + 0x1e0 bytes;
  `docs/audio-save.md`).
- **Prompt.** `JumpGate_interactPrompt` 0x27d7a0, ordinary gates only:
  - no prompt while the gate menu is open or the gate's `script` predicate returns 0;
  - the first prompt marks the gate found (+0x4d) and adds the level;
  - with only the hub listed, the text is `JumpGateVirgin` and the gate cannot be used;
  - every other alive player must be within 96 units, otherwise `JumpGateNeedPlayers`.

  This also runs from the draw path, so the gate can be marked found up to a frame early on
  the owner's machine (`docs/online-setup.md`).
- **Menu.** `JumpGate_openMenu` 0x27da24 and `jumpgate_menuRun` 0x27dd74:
  - the current level cannot be chosen;
  - offline the game is paused while choosing;
  - after confirm the travel state counts from 1 to 181 (180 ticks), then the request is
    written (orientation 0xff);
  - the travel state survives the load, so the destination gate's constructor places
    everyone at that gate (5.2);
  - the task clears the travel state on the first or second tick of the new level.

  The menu's pad test has the per-machine pause-menu branch already listed as FINDINGS U2.
- D: 38 `Portal` objects, one per level, with properties `lump` (37) and `script` (10). No
  gate has `hurt` or `destination`, so the fixed-destination path is unused.

## 10. Recall, party wipe, checkpoints

**Recall.** `player_recallTick` 0x1b5fa0 runs when the 60-tick countdown ends, outside a
cutscene, with someone alive (O). Section 16.3 gives the exact timing and what a cutscene
does to it: the countdown keeps running during a cutscene, and a cutscene on the last tick
cancels the recall. The two legs:

| Leg | Saved / restored | Request | Placement on arrival |
|---|---|---|---|
| level → hub | each record +0x44 = its player's position (or a free spot near the first alive player); +0x24 = qualified level; set 0x41b51e | hub name, 0xfd | `from`/`name` ranks disabled; no marker says `from=gate`, so the hub's `default` or first marker wins |
| hub → level | set 0x41b51c; copy every +0x44 to 0x41b520 | player 0's +0x24 (for everyone), 0xfd | markers rank normally, then x/y are replaced by the saved positions, z from terrain; slots 1–3 still scatter unless rank 3 |

`clearRecall` and an act change set +0x24 to `None`. Both recall legs skip the entry-music
step.

**Party wipe.** `game_checkAllDead` 0x1e7438, then `deathTask` 0x1e75e8 (O):

- alternate death (`setAlternateDeath`): wait until someone is alive;
- a level outside every act (`save_findAct(g_levelTexName) == −1`): every record's hp is set
  to max and the level restarts by base name, with ordinary marker ranking;
- otherwise `save_reload` = `save_load` of the last save buffer: the saved level, saved
  positions, saved quest variables, saved gate list and rank 3, so players stand exactly
  where the save put them.

**Checkpoint.** `saveCheckPoint` calls `save_game(0, 0, 1)` 0x218128. In a level outside every
act it shows the HUD line and **saves nothing**. Otherwise it builds the header (qualified
name, act, difficulty), the camera, the gate list, the players with their positions, the
quest variables and the current level's state.

## 11. Moving pieces (doors, bridges, stairs)

The record layout is in `docs/formats/world.md` ("Moving pieces"). Added here:

| Fact | Tag |
|---|---|
| +0x08..+0x16 (rest translation, cos, sin) equal the first chunk's own fields in all 178 pieces; +0x1a equals the collision element's z (the rest collision height); nothing in the piece API reads it | D; O for the absence in 0x182768–0x182f24 |
| chunk count 1 in every piece; chunk flags 0x20 (173) or 0x60 = mirrored (5), never the quarter-turn code | D |
| 123 of 178 pieces have texture cell 0: collision-only pieces whose visible part is the claiming object's own model | D |
| every piece function returns at once for index < 0 (`getPieceHeight` returns 0, `getPieceBounds` zeros) | O 0x182914, 0x182940, 0x182b00, 0x182b74, 0x182bb4, 0x182bf4, 0x182c98 |

### 11.1 Claiming (`world_findMovingPiece` 0x182768) — O, re-read

```
best = 6400.0 (80²);  bestIndex = -1
for each piece i, in file order:
    t = rest translation × 0.25;  c, s = rest cos, sin × 0x38000100
    pivot.x, .y = (t.x·c − t.y·s, t.x·s + t.y·c)       mirrored (chunk flag 0x40): (t.x·c + t.y·s, t.x·s − t.y·c)
    pivot.z = t.z
    d2 = (dx² + dy²) + dz²         full 3-D, against the object's position
    if not (best < d2): best = d2; bestIndex = i
if bestIndex < 0 or piece[bestIndex] is claimed: return -1     no fallback to the next piece
claim it; return bestIndex
```

- 80 is inclusive, and the **later** of two equally near pieces wins.
- An unrotated piece's cosine becomes 0x3f7fffff, slightly less than 1, so pivots are a hair
  short of the stored translation (`tools/test_ref_levels.py`
  `test_nearest_inclusive_80_later_wins_ties`).
- D: every claim on the disc is unique; claim distances are 0–60.

### 11.2 After the objects: unclaimed pieces lose collision

`world_disableUnclaimedPieces` 0x1826ec runs at 0x1e6060 (O). That is after the saved states
have been applied, after objects deleted in their constructor have been flushed (their
destructor released the claim), and after `start`. It turns collision off for every piece
still unclaimed. One consequence: a `DoorSwing` with `disable` is drawn closed but can be
walked through (O for each step; I for the combination; D: no shipped DoorSwing has
`disable`).

### 11.3 Moving and collision

- `world_movePiece(piece, offset, angle)` 0x182c98 sets an **absolute** pose relative to rest.
  Only the chunk's drawn translation and rotation are rewritten: the geometry turns by
  +angle about the pivot and shifts by the offset in the piece's rest frame (world units).
  This is **drawing only**. The exact arithmetic is in 16.4 (Executed).
- **Collision never moves or turns** (O). It has exactly two controls:
  - element flag 2: set means the element is absent from every terrain query
    (`world_setPieceCollision` 0x182b00);
  - element z: truncated to an integer (`world_setPieceHeight` 0x182bb4).

  `tools/ref_world.py` models both.
- The world layer does nothing per tick for pieces (O: no task touches the table). Each call
  takes effect at once, inside the calling object's run, so later objects in the same tick
  see it.
- The load-time wall rewrite of piece height fields (samples with flag 1 become height 2000)
  is in `world_fixup` 0x181e2c–0x181ec0 and is modelled by `ref_world.Level`.

### 11.4 Who claims pieces on the disc (D)

- 178 pieces in 19 levels; 174 claimed, 4 unclaimed (actintro 1, arachna1 2, blood1 1;
  3 of the 4 stay drawn but can be walked through).
- **167 claims come from `AutoProp` objects with the property `AutoDoor`** (`AutoProp_ctor`
  0x23c868). Open means collision off and the piece drawn 256 lower; closed means collision
  on and the rest pose (`AutoProp_setPassable` 0x23d7ac).
- Only 7 come from the `WorldPart` family: the `DoorSwing`s of `islgoth`.
- `Switch`, `FloorSwitch`, `DoorSecret`, `RollDoor`, `FallPlatform`, `GothTrap`, `HateHole`
  and `HateBridge` are never placed, and `FallPlatform` has no factory entry at all. Shipped
  content does not need them. What was read, for completeness (O):

  | Class | Behaviour |
  |---|---|
  | `Switch` 0x28a8f0 | one use: draws the piece 8 units along its local x, runs every `action=` (raw) |
  | `FloorSwitch` 0x28b56c | box = piece bounds with max z + 6; pressed by any object without flag 1 (or only by the `keyObject` name). Sinks 1 unit in 0.25 steps, setting element z = trunc(rest − depth). Runs the actions with 1 or `not<action>` (with `onOnly`/`offOnly`). Saves 1 byte |
  | `DoorSecret` 0x28b370 | after use: recess 5 units in 20 frames, slide 100 units along local +y over frames 121–180, collision off from frame 181. Loading an open one drops it 300 under the floor. Saves 1 byte |
  | `RollDoor` 0x28e01c | never moves its piece (the rolling stone is its own model); collision off after 120 frames |
  | `FallPlatform` 0x28bb5c | shakes, falls with gravity 8.999999 to 720 below (element z follows), rises back spinning; the only caller of the flash flag 0x100 |
- `DoorSwing` (run 0x28af54) is the one WorldPart a native client needs:
  - each tick the angle (s16) grows by the speed, which is 600 on open and then multiplied
    by 0.98;
  - past 0x637c it bounces back with speed × −0.74;
  - it stops below |speed| 1;
  - on open, collision goes off and the swing direction comes from which side of the hinge
    the player stood;
  - the gothic variant (`gothic` in the level name) is dead: no level name contains it;
  - saved state: 8 bytes, the u16 angle, s16 direction and f32 speed (`saveState`
    0x28ae3c, `loadState` 0x28ae74).

## 12. Water

| Rule | Tag |
|---|---|
| **`water_test(radius, pos, &height)`** 0x189438 is simulation. Box: x and y from (p − r) − 1 to (p + r) + 1, z from pos.z − 1 to pos.z + 60. The collector 0x189240 is called with cap 2, so only the **first** water tile overlapping in chunk-tree walk order counts (split nodes without bit 14 are skipped; the second child is visited first). Height = that tile's bounds.min.z (chunk +0x10). The 32 × 32 mask is not read. So a point more than 60 below the surface is "not in water" | O, re-read |
| **`water_disturb(strength, radius, pos)`** 0x189514: its return value is simulation. It is the number (≤ 15, cap 16) of tiles overlapping x, y ± r (no +1), z from −1 to +60, or 0 while a cutscene is skipped. It is counted whether or not the tile has a ripple grid. The ripples themselves are cosmetic | O |
| Water is entered with `water_test(12)` and left when `water_disturb` returns 0: one unit of horizontal hysteresis | O (`Creature_moveBy` 0x113c48, `Player_move` 0x1b4020) |
| A player entering water advances `g_randSeed` once. Level flag 0x1000 gives lethal damage (1e8) every 16th frame in water; D: only `fire3`, `fire4`, `fire5` have it. There is no swim mode | O; D |
| Ripple pool: row +0x14 blocks of 0x12b0 bytes (32 × 32 s16 heights and velocities), handed out least-recently-used **when a tile is drawn**, freed after 200 undrawn ticks; 8-neighbour step with 1/128 damping (0x196088); random bumps from `g_cosmeticSeed`. Per machine and cosmetic | O 0x186dbc, 0x1876e0, 0x186e38 |
| Water chunk data: neighbours in the order **−y, +y, −x, +x**. Mask: two 64-byte halves (rows 0–15, 16–31); the u16 at byte 2·col is column col (along y); bit 15 − (row mod 16) is row (along x). The ripple step uses row r + 1's bit for row r, a cosmetic off-by-one | O; D: 84 % agreement with the terrain under the surface in two levels |
| Drawing: texture = first `.tex` of `waterenv.lmp`. Chunk flag 0x1000 selects the second colour/alpha/wave set, which level settings can set (`waterColor2`, `waterWavyness2`; defaults 0). Alpha v ≥ 0 gives `ALPHA_1` (Cs − Cd)·FIX + Cd; v < 0 gives Cs·FIX + Cd. Drawn at z = chunk translation z / 4 | O 0x1875d4, 0x1876e0, 0x22e714 |

## 13. Material and texture addressing of WORLD geometry

Builds on `docs/formats/world.md` ("Textures of geometry chunks", "Level texture file") and
`docs/spec/render-pipeline.md` 4.6, 6, 13. Its headline corrects a long-standing open item:
**`<LEVEL>.TEX` holds one texture format only, and the "packing" is a per-block Huffman code,
not a swizzle.** What a native client was missing is the decoder of 13.3. There is no
collection of unsupported formats behind it.

### 13.1 Directory and cells

- `world_fixup` reads the first 0x5000 bytes of `<LEVEL>.TEX` (0x181efc–0x181f28). The
  leading u32 is skipped unread. Records are 12 bytes, {s32 cell id, u32 file offset, u32
  size}, up to an id of −1 or −2; the test is `(unsigned)(id + 2) < 2`, so both end the list
  alike (O 0x181f88, 0x181fd8). A first id of 0 skips the fill. Ids are not checked against
  the world's lowest/highest cell (O). D: 111 files, all end with −2, leading word 0.
- Before the fill every world table entry is set to {0, 0x40}; then `table[id − lowest] =
  {offset, size}` (O 0x181f3c–0x181fd0).
- **Cell id** = `row × 100 + column`, with `column = floorf(x / size) + 50` and
  `row = floorf(y / size) + 50`. `size` is world +0x68, which is 720 in every file; 0 would
  mean 960 (O 0x17d8e0–0x17d930, 0x18224c).
- **Streaming** (per machine, drawing only):
  - the game keeps the 3 × 3 cells around `g_cameraFocus` in 9 slots and reads the missing
    cell nearest the focus first, one at a time (O 0x17d934–0x17dbe0);
  - cells are read in 128 KB blocks into a segment cache whose blocks need not be
    contiguous. An offset inside a cell maps through the slot's block list as
    `cache + map[off >> 17] × 0x20000 + (off & 0x1ffff)` (`tex_relocateInCell` 0x179f28; O);
  - world +0x60 is −1 in the file. `world_prepare` replaces it with the worst 3 × 3 window's
    total in 128 KB blocks (O 0x1823f0–0x1825bc). D: 9 to 91 blocks, median 47.
- The "always loaded" list exists (0x7d3560, at most 8 cells; `worldtex_loadAlwaysPages`
  0x17d680), but its only adder 0x17fe18 has **no caller**. Every world texture streams
  (O for the absence; I for "never").
- A chunk is not drawn when its cell is not resident, or when its texture's GS packet is not
  built yet; in the second case an upload is queued (0x17fc78) and the chunk appears a frame
  or more later (O 0x1887b8). A PC client can hold every cell and ignore this.
- **Cell layout**: u32 texture count at +0, zeros to +0x40, then 0x40-byte headers at
  0x40 × (i + 1). A geometry chunk's +0x20 is the byte offset of its header (O 0x1887b8,
  0x17dffc). D: 4,808 cells in 111 files, 4 to 148 per level, at most 252 textures and
  2.2 MB per cell.

### 13.2 Texture header (0x40 bytes, in a cell)

| Offset | Type | Value | Meaning | Tag |
|---|---|---|---|---|
| +0x00, +0x02 | u16 | width, height | the used size; every chunk's UVs fit it | D |
| +0x04 | u16 | GS blocks to allocate | = 5 + the highest GS block address among the stored blocks, in all 157,820 textures | O use `texcache_alloc` 0x179bb0; D |
| +0x06 | u16 | 0 | upload length in qwords, computed by relocation | O 0x179fb0–0x17a0b0 |
| +0x08 | u16 | 0x010c in every texture | 0x0100 = this block form; 0x0004 = 8-bit palette; 0x0008 no reader found (U); 0x0001 selects a vector-quantised form (decoder 0x17e6c0) that **no disc texture uses** | O 0x179fa8, 0x17cba8; D |
| +0x0c | u32 | TEX0 bits 14–45 | PSM 0x13 (PSMT8), TBW = 2·ceil(w/128), TW = TH = 10 (1024), TCC 1, TFX 0 (modulate) | O 0x16c308; D all |
| +0x10 | u32 | | cell offset of the texture's **record block** (13.3); a pointer after relocation | O 0x179f38 |
| +0x14 | u32 | 0 | run time: the built GS packet (0 = not built) | O 0x1887b8 |
| +0x1c | u32 | 0 | run time: −1 after relocation, then last-used frame | O 0x179f48 |

### 13.3 The decoder (worker 0x17ca58, block path 0x17cbe0–0x17d678) — O; D 157,820 of 157,820

Record block, at cell + header +0x10:

```
u32 codebook offset                                     (cell-relative)
repeat:  s8 x0, y0, x1, y1                              x0 == -1 ends; inclusive, in 16-texel blocks
         u32 stream offset per block, y outer, x inner  (cell-relative)
```

Code book, at cell + codebook offset (O 0x17cd84–0x17d03c):

| Offset | Size | Content |
|---|---|---|
| 0x000 | 0x400 | palette, 256 × RGBA8, stored in GS CLUT order (entry i at position i with bits 3 and 4 exchanged) |
| 0x400 | 0x800 | successor table `succ[previous][k]`, 256 × 8 |
| 0xc00 | 4 + 2N | u32 N, then N u16 symbols |
| then | 2 × 18 × 4 | s32 `base[18]`, s32 `limit[18]` |

Codes are canonical Huffman. A code value c of length L is valid when `c ≤ limit[L]`, and its
symbol is `sym[base[L] + c]`.

Each 16 × 16 block decodes on its own:

- The stream is little-endian u16 words read most-significant bit first. The window is the
  next 16 bits. Lengths 1–8 go through a 256-entry table built per code book (0x17cf88);
  then length 9; then 10 and up.
- Symbols:
  - below 0x100: a literal palette index;
  - 0x100–0x104: copy an earlier texel of the same block at −1, −16, −17, −15 or −2 (left,
    up, up-left, up-right, two left; s8 table 0x41c1a0, re-read);
  - 0x105–0x10c: `succ[previous texel][symbol − 0x105]`.
- The previous texel starts at 0 in every block (O 0x17d238–0x17d3cc; thresholds at
  0x17d370, 0x17d37c re-read).
- The game writes each block through a permutation (0x7d3040, built by 0x17a0c0). That
  permutation is exactly the standard placement of 8-bit texels in a block uploaded as
  32-bit, so **the decoded 256 bytes are already plain row-major**. Block (bx, by) holds
  texels (16·bx … 16·bx + 15, 16·by … 16·by + 15). No swizzle is needed natively (O for the
  table; I for the GS equivalence, all 256 entries checked).
- Blocks that no record lists are never written. On the console they hold stale GS memory.
  D: no UV of any chunk falls into such a block.

The code books that a texture header's record block points at are shared by several
textures of one cell (D: 73,823 books for 157,820 textures).

How the decoder was checked (D, private, counts only):

- all 157,820 textures decode with no out-of-range symbol, no code over 16 bits and no
  reference before a block start;
- across 8.3 M consecutive stream pairs, no stream runs into the next;
- header +0x04 matches the rule above in every texture;
- neighbouring texels are closer in palette colour than random pairs in 157,452 textures.

No decoded image was looked at. `ref_levels.decode_texture` was compared with the agent's
private decoder texel by texel on three levels (section 13.6).

### 13.4 Per-chunk material (`world_drawChunk` 0x1887b8)

The chunk header the drawer writes (O) starts with `TEXFLUSH` and a `TEX0_1` that the DMA
handler patches with TBP = block + 4, CBP = block, CPSM CT32, CLD 2 (O 0x16bff0–0x16c044,
0x16c308–0x16c330). Then:

| Chunk flags | ALPHA_1 | ALPHA_2 | TEST_1 |
|---|---|---|---|
| 0x10 (environment-mapped) | 0x09 | 0x2a | 0x582f5 if 0x400, else 0x587f4 |
| else 0x10000 | 0x48 | — | as above |
| else 0x200 or 0x400 | 0x01 | — | as above |
| else | 0x02 | — | 0x587f4 |

Lighting is tested in this order (O 0x18900c–0x18904c, re-read):

1. 0x100: constant −230, and the flag is cleared;
2. 0x2000: constant +230;
3. 0x200: constant 0;
4. otherwise up to four point lights.

The sort layer is 4 with 0x200, otherwise 0. `TEX1`, `CLAMP` and the mip registers are not
written. They come from frame state: bilinear, repeat, no mip maps (`render-pipeline.md` 6).

**The packet's own DIRECT blocks override this, batch by batch** (last write wins). D: seven
state sequences occur:

| Sequence | Chunks |
|---|---|
| {ALPHA 2, TEST 587f4} | 106,795 |
| {1, 582f5} | 19,269 |
| {2a/9, 587f4} | 14,344 |
| {2a/9} then {2} | 10,642 |
| {2} then {1, 582f5} | 5,106 |
| {1, 587f4} | 1,244 |
| {2a/9}, {2}, {1, 582f5} | 420 |

The GIF tag's ABE bit turns blending off for 0x308e4000 tags. Those occur only in packets
that carry a {1, 582f5} block (D).

**Texel alpha** (0..0x80; **0 is opaque** under these equations). D over the 2.70 billion
texels that UVs actually reach:

| Chunk group | Textures | A = 0 | 1–0x2e | 0x2f–0x7f | 0x80 | So |
|---|---|---|---|---|---|---|
| no blend flags | 106,795 | 100 % | 0 | 0 | 0 | opaque |
| 0x400 | 24,375 | 51.6 % | 13.2 % | 25.8 % | 9.4 % | cut-out (A ≥ 0x2f discarded) with a blended soft edge |
| 0x200, 0x2200 | 1,244 | 13.0 % | 7.9 % | 60.8 % | 18.3 % | genuinely translucent, drawn in layer 4 |
| 0x10, 0x410 | 25,406 | 45.3 % | 53.2 % | 1.5 % | 0.04 % | alpha is the reflection strength |

A material a Godot client can follow (`ref_levels.chunk_header_state`, `batch_material`). In
every row the colour is `texel.rgb × vertex colour / 128` (vertex colour = base level plus the
light rule); a = A / 128; depth test is ≥.

| Batch state | Blend | Depth write |
|---|---|---|
| ALPHA 2 | opaque | yes |
| ALPHA 1, ABE on | `mix(src, dst, a)`: alpha 0 opaque, 0x80 invisible | yes (I for layer 4) |
| ALPHA 1, ABE off | opaque | yes |
| TEST 0x582f5 | discard where A ≥ 0x2f (no colour, no depth) | — |
| ALPHA 9 after the context-2 pass | pass 1 writes `env(uv2).rgb × c / 128` opaque; pass 2 adds the base: `base + pass1 × a` | yes |
| ALPHA 0x48 | additive `dst + src × a`; no disc chunk | — |

- UV: `u = U / (16 × width)`, `v = V / (16 × height)`. D: every UV lies inside the size and
  inside a stored block, and none reaches 1024, so **clamp-to-edge** is the faithful
  sampler. Use bilinear filtering and no mip maps (I).
- Environment texture: `envtex.etex` in the archive's `env.lmp`, a 128 × 128 PSMCT32 lump
  texture decodable with `docs/formats/model-texture.md`. It is uploaded after the load and
  bound as `TEX0_2`, and repeats (O per `render-pipeline.md` 6, 13). Its coordinates are
  computed in VU1 program 0x48 from the camera-space normal (`render-pipeline.md` 4.6). With
  level flag bit 2 they scroll by `(g_simFrame & 0x3ff) / 4`.
- `waterenv.lmp` holds one 64 × 64 PSMT8 texture used by the water drawer, not by geometry
  (D, two archives).
- D, chunk flags of the 157,820 drawn chunks (bits 0x1 and 0x40 ignored): 0: 106,200;
  0x10: 24,980; 0x400: 24,375; 0x200: 1,128; 0x4: 493; 0x410: 420; 0x2200: 116; 0x20: 54;
  0x20000: 48; 0x14: 6; 0x10000: 0. Flags 0x4, 0x20 and 0x20000 have no material effect in
  0x1887b8 (O).
- 988 geometry chunks have cell 0 and are never drawn (O, D). 123 of them are moving pieces
  (11.4).

### 13.5 Automap tile texture (world +0x6c)

D over 118 worlds: a lump-style header with flags 0x2450, PSMT4 with an 8 × 2 CT32 palette,
sent as plain 4-bit rows. The height is 160 (140 or 150 in two worlds), the width 10 to 210 in
steps of 10. It should decode with the lump rules (not run). Which tile an automap cell code
selects is still U.

### 13.6 Private comparison

`ref_levels.decode_texture` against the agent's scratch decoder (kept under `local/`, not
committed), on every drawn chunk of `drundar`, `islgoth` and `disbonus`: 7,464 drawn chunks, 7,464 resolved
through the directory and header, 7,464 decoded without error and identical texel for texel
(D, 2026-10-17). In the same run `ref_levels.find_moving_piece`, applied in record order to
the objects that claim pieces (`AutoDoor` set, or a WorldPart class), claimed all 57 pieces of
the three levels (5 + 7 + 45, as in 11.4). These are private counts. The scripts are not
committed, and nothing decoded was written out.

## 14. Corrections to other documents

| Document | Was | Now |
|---|---|---|
| `docs/mainloop.md` 7 step 6 | Players are built for every slot with hp > 0 and an active peer | only inside the "real level, not PvP B" test, and only the medal slot in a medal mission (0x32125c–0x3213b4). Also missing: the recall x/y copy (0x321160), the write-back of the scatter, the orientation copy (0x321118), `None` in record +0x24 on an act change (0x32141c) |
| `docs/issues/arena-entry.md` 2, bullet 4 | the same | the same gate and medal condition |
| `docs/data-tables.md` 7.1 +0x14 | pool contents Unknown | water simulation blocks (12) |
| `docs/data-tables.md` 7.2 | the loading picture is Inferred; GOB holds `<name>.lmp`, `env.lmp`, `waterenv.lmp` | observed with the alias table and the 8-character cut (3.1); 21 archives also hold `dome.lmp`; `.TEX` is read during the GOB load |
| `docs/FORMATS.md`, GOB | records carry offsets | the game ignores them and reads lumps back to back from 0x800 (3.2) |
| `docs/script.md` / `docs/spec/script-builtins.md` 1.10 | "entrance orientation" | it has no reader beyond the loader's copy (6.3) |
| `docs/spec/object-system.md` 7.3 | — | add: no marker on the disc has `from=gate`; `g_entranceName` survives level changes |
| `docs/formats/world.md` | piece +0x1a U; water mask bit order U | +0x1a = the element's rest z (D); bit order and neighbour order (12) |
| `docs/FORMATS.md`, `tools/play-net/disctex.py` | a `.TEX` unpacker is open; cell textures are "stored packed" | the per-block Huffman decoder of 13.3; the 0x7d3040 permutation is only the standard 8-bit GS block placement |
| `docs/formats/world.md`, level texture file | −1/−2 terminators; always-loaded cells; +0x10 "pixel-data description"; decoding U | treated alike; the list's adder has no caller; +0x10 is the record block; decoded (13) |
| `docs/spec/render-pipeline.md` 11, level texture alpha | open | settled by the counts of 13.4 |
| `docs/monsters-2.md` 6.1 / 6.2 | 0x182bf4 "shake"; tolerance of −1 not read; DoorSwing `disable` leaves closed geometry | 0x182bf4 toggles the one-frame flash flag 0x100 (only `FallPlatform` calls it); every piece function ignores −1; a disabled DoorSwing's piece loses its collision (11.2) |
| `names.tsv` 0x189240 | `world_collectChunksInBox`, "keeps chunks with flag 0x80" | correct; add that it descends only into split nodes with bit 14 (water below), visits the second child first, and stops at cap − 1 hits (not renamed here) |

## 15. Open

Round 2 settled none of the items below. Round 3 settled the start height (section 17).
Round 4 settled the three archives whose cold origin has no floor (section 18).
What remains:

1. Which row each of the 30 levels without a table row resolves to (2).
2. Whether some test other than the placement snap and `Player_ctor` rejects a sentinel
   height before the first tick. Those two store it unchanged (→ 17.2). The kill plane
   cannot fire (section 2).
3. The rest of `Player_ctor` after the radius store and the height snap (→ 17.2). Readers
   of 0x41b7c1, and writers of 0x4f8b58 through computed pointers, are still open.
4. Marker order after a re-entry from a saved state (3.3).
5. Whether a piece's changed element z survives into a reload of the same level (7.4):
   check whether `<level>.lmp` is always re-read.
6. `arena_pickSpawnPoint` with a0 = 0 (respawn) was read and not run. The rotation that
   requests the next arena level, and the wave start on the three cold-origin archives,
   are section 18. The wave-start path on the other arenas was run in section 17 (→ 17.3).
7. Texture: what −1 vs −2 and header flag 0x0008 mean; the edge rules of the unused
   flag-1 form; the look of environment-mapped chunks and whether layer-4 chunks write
   depth (compare a GS frame dump); the automap tile mapping.
8. None of this has a recorded Play! run. A recorded run through a `PushTrigger` door, a gate, a recall
   pair and a party wipe with and without a checkpoint would confirm sections 5, 9 and 10
   (`docs/VALIDATION.md`).

## 16. Round 2 corrections (2026-10-18)

**Why this section exists.** The first native implementation of this contract
(`codex/level-flow` at 1cbd5db in open-champions, report
`work/loop-level-flow-r1-report.md` there) refused four things under its rule not to guess:
two because this document and `tools/ref_levels.py` contradicted each other, two because
neither gave the exact arithmetic or timing. Each is settled here by **running the original
function** in `tools/ee_emu.py` on state the test built (**Executed**, as CONTRIBUTING.md
defines it). The tool is `tools/difftest_levels.py`; it needs your own `SLUS_209.73` and
exits 0 without it. Everything it compares is a 32-bit pattern. Nothing in this section
ran on a console, in PCSX2 or in the Play! emulator.

Full run, 2026-10-18, seed 20973:

| Property | Cases | What the original code was run on |
|---|---|---|
| `light_level` | 204 | 0x1e60e0–0x1e6158, with `light_setLevelLight` 0x14a2d8 run for real |
| `chunk_light` | 216 | 0x189008–0x189070 of `world_drawChunk` |
| `world_pick` | 900 | `lump_findNthByExtension` 0x171fd8, with libc `strrchr`/`strcmp` run for real |
| `world_pick_load` | 100 | `game_loadLevel` 0x1e5954–0x1e59c0, with `lump_load` stubbed |
| `recall_tick` | 3,430 calls | `player_recallTick` 0x1b5fa0, every callee stubbed |
| `move_piece` | 400, plus 40 under each of five other float models | `world_movePiece` 0x182c98, with `math_sin16`, `math_cos16` and `floorf` run for real |
| `move_piece_rest` | 1 | the fixed case of 16.4 |

All pass. Before trusting them, each property was checked to fail when the model is
deliberately wrong in the way round 1 was ambiguous: sorted WORLD pick, 0x20 winning,
recall deferred past a cutscene, mirrored sign swapped.

### 16.1 Several WORLD entries: directory order (the prose was right, the reference was wrong)

- `game_loadLevel` loads `<base>.lmp`, calls `lump_findNthByExtension(lmp, "world", 0)`
  0x171fd8, and stores record +4 (the data pointer) in `g_world` 0x44fdc8 without a null
  test (O 0x1e5978–0x1e59bc; Executed `world_pick_load`).
- 0x171fd8 walks the directory in its stored order (u16 count at lump +0, 12-byte records
  {name, data, size} from +4). For each name it takes the text after the **last** `.`
  (`libc_strrchr` 0x3b95d8) and skips a name with no `.`. It compares that text with the
  extension by exact `strcmp` 0x3b8534, so the test is case-sensitive: `a.WORLD` and
  `a.world.bak` do not match, but `x.y.world` and `.world` do. It returns the n-th match
  (n = 0 is the first) or 0 (O; Executed `world_pick` for n = 0, 1, 2).
- `lump_fixup` 0x1717d0 drops entries (moving later records down) and renames
  `ntsc_dialog.bin`. It **never reorders** them (O 0x1718d4–0x171a50). So "lump order" is
  the file's directory order minus dropped entries.
- D (all 119 level lumps on the disc, counts only): 118 have exactly one `.world` and 1 has
  none. **None has two**, so shipped content never reaches this case. None of the 119
  directories is in `strcmp` order, and none is in case-insensitive order either, so a sort
  is not even an approximation of the stored order.
- Side note, not followed up: `symbols/engine.tsv` describes `lump_findEntry` 0x171de4 as a
  binary search, but the directories are not sorted. The note, or the key the search uses,
  should be re-read (U).
- A level lump with no `.world` makes the interpreter fault at 0x1e59ac (a read of address
  4). What the console does with that read is U. The file stays **required**.
- `ref_levels.first_entry_with_extension(entries, ext, n=0)` is the function.
  `level_manifest` now uses it, and its `level_entries` argument is documented as directory
  order. Round 1 sorted at this point.

### 16.2 Light precedence: base light level, and 0x40 wins

The conflict: the section 2 row read "level-light alpha 0x40 / 0x20 (later test wins)",
which implied 0x20 wins, while `ref_levels.level_light_alpha` returned 0x40 with both bits
set. Cross-check: `docs/lighting.md` 1 on `t3/research-fx` (d7922ef) gives "0x80, or 0x40
with 0x04000000, or 0x20 with 0x20000000", without saying which wins. Its
`ref_lighting.base_level` tests 0x04000000 first, so it also gives 0x40.

Executed (`light_level`):

```
level = 0x80
if flags & 0x20000000: level = 0x20      movn at 0x1e6108 (tested first)
if flags & 0x04000000: level = 0x40      movn at 0x1e611c (tested second, so it wins)
light_setLevelLight(dir, ..., stack[0] = 0, stack[8] = level)
```

- 0x14a2d8 stores the second stack argument in **`g_worldLightLevel` 0x5d347c**, the base
  level of every level vertex (lighting.md 1). It is **not an alpha**. The two alpha bytes
  0x5d3473 and 0x5d347b get the other stack argument, 0 (Executed, both bytes checked).
- So the reference was right about precedence and the prose was wrong about both precedence
  and name. `ref_levels.base_light_level` is the accurate name; `level_light_alpha` stays,
  for API stability, as the same function. `ref_lighting.base_level` agrees on every input.
- **Per-chunk light** (13.4) is unchanged and is now Executed (`chunk_light`): 0x100 gives
  −230 and clears the flag; else 0x2000 gives +230; else 0x200 gives 0; else the chunk is
  lit dynamically. lighting.md 2 lists the three constants without an order. With
  **0x2200** (116 disc chunks, 13.4) the constant is **+230**, not 0.
- **Light chunks.** The research-fx corrections to the light-chunk *data*
  (`docs/formats/world.md` "Light chunks": +0x20 glow size, +0x22 wobble shift, +0x28
  depth bias) touch nothing in this document, which reads no light-chunk data field. Its
  chunk-record +0x20 (13.1, texture header offset) is the geometry meaning. For light and
  emitter chunks the record's +0x20 is a run-time timer, as world.md's chunk table already
  says. No conflict.

### 16.3 Recall countdown: exact ticks, and what a cutscene does

`g_recallCountdown` 0x41b51d is set to 60 by `recall_execute` 0x18c3c8 (game message 3).
`player_recallTick` 0x1b5fa0 is the **first call of the run task `gameMiscSync`** 0x1e3d60
(priority 1, `docs/mainloop.md` 2) in every tick. Nothing in front of it tests
`game_isFrozen`, a cutscene or the pause state (O 0x1e3d70). Executed (`recall_tick`, random
start values, cutscene flags and alive counts):

```
v = (s8) countdown;  if v == 0: return
if v == 60: start the aura on every player
countdown = v - 1 (byte);  if countdown != 0: return
clear every player's aura lights                    0x1b60a4-0x1b6110
if g_cutsceneActive 0x44fcd0 != 0: return           recall LOST
if g_alivePlayerCount 0x4f8420 == 0: return         recall LOST
recall_finish (10): hub test, positions, request
```

- **The countdown keeps running during a cutscene, and while paused.** Only the call that
  takes it from 1 to 0 looks at the cutscene flag. If a cutscene is active then, the recall
  is **cancelled, not deferred**: the countdown is already 0, nothing re-arms it, and the
  potion that `recall_execute` took is not given back. The same happens when nobody is
  alive. A cutscene that starts and ends within the 60 ticks changes nothing.
- **Which tick.** The first call that sees the countdown non-zero sees 60 and starts the
  aura. The **60th** call writes the request.
  - Net game: messages run in `net_frameLoop` before that frame's run pass
    (`docs/netcode.md`, "The tick"). With message 3 in frame F, the aura starts in tick F
    and the request is written in tick **F + 59**. The pending request then idles the
    following steps until the load.
  - Offline: `net_sendGameMsg` runs the message at once. From `player_pollRecallButton`
    (called in `gameMiscSync` right after `player_recallTick`, 0x1bcff4) in tick S, and
    from the pause menu (0x18db80, draw pass), the first call is in tick S + 1 and the
    request in tick **S + 60**.
  - `ref_levels.recall_request_tick(set_tick, set_before_run_pass)` gives both cases.
- **Which value of the cutscene flag the call sees.** It is set only by `cut_start`
  0x19b57c (caller: script `cutScene` 0x143f1c). It is cleared by `cut_end` 0x19a0dc
  (callers `cut_runFrame` 0x199f44, `frontend_stop` 0x1e2174, and the net-failure path of
  the HUD draw task 0x1dbe64 / 0x1dc0b4) and by 0x199fbc from `game_clearLevel` 0x1e4f28
  (O). Scripts, objects and dialog run at priorities 10–125, `cutRunFrame` at 300, and the
  HUD draw task in the draw pass. So the recall call reads the flag **as the previous tick
  (or the load) left it** (I, from the task order).
  - Consequence: a `cutScene` call in the same tick as the last countdown call does not stop
    the recall. One made in the tick before it does.
  - The HUD draw path is per machine. A net failure that ends a cutscene exactly one tick
    before a recall completes would diverge (I; only on that failure path).
- Unchanged: while the countdown is non-zero, `Trigger_run` does nothing, and the damage
  early-out and player state 0xb apply (8; `docs/player.md`).
- `ref_levels.RecallCountdown`: `start()`, `running`, and `tick(cutscene_active,
  alive_count)`, which returns `aura`, `finish`, `dropped: cutscene`, `dropped: nobody
  alive` or None. Call it once per tick at the priority-1 position, with the flag values as
  the previous tick left them. Then `recall_finish` (round 1) on `finish`.

### 16.4 `world_movePiece` arithmetic

`world_movePiece(world, piece, offset, angle)` 0x182c98. Executed (`move_piece`; random
rest translations and rotations including non-unit ones, offsets, angles, 1–3 chunks of
mixed mirroring, counts 0 and −1, index −1; every chunk field compared and **no other
memory written** outside the stack):

```
if piece < 0: return                            (bltz on the sign-extended register)
a  = (s16) angle;  ca = math_cos16(a);  sa = math_sin16(a)
o  = offset * 4.0                               per axis, first (world -> quarter units)
P  = world +0x54 + piece * 0x1c                 the PIECE record, not the chunk
c, s = (float) P.cos (+0x14), (float) P.sin (+0x16);  K = 0x38000100
cos' = round_s16(((ca*c)*K - (sa*s)*K) * 32767.0)
sin' = round_s16(((sa*c)*K + (ca*s)*K) * 32767.0)
round_s16(x) = clamp((int) floorf(x + 0.5), -32768, 32767)      floorf 0x3a57e8
for i in 0 .. (s16) P.count (+0x04) - 1:        nothing when the count is <= 0
    C = world +0x24 + (P.first (+0x00) + i) * 0x3c
    X, Y, Z = (float) P.t (+0x08, +0x0c, +0x10, s32) + o        each axis: i2f then add
    if C.flags & 0x40 (mirrored):  C.tx = trunc(X*ca - Y*sa);   C.ty = trunc(X*sa + Y*ca)
    else:                          C.tx = trunc(X*ca + Y*sa);   C.ty = trunc((-X)*sa + Y*ca)
    C.tz = trunc(Z);  C.cos (+0x36) = cos';  C.sin (+0x38) = sin'
```

`trunc` is `cvt.w.s` (toward zero). Products are formed in exactly the order written
(`ref_levels.move_piece` follows it operation by operation). It agreed under all six
float-model settings.

- **Absolute.** Only the piece record's rest values are read, so repeated calls do not
  accumulate and a call with the same arguments always gives the same fields.
- **Angle 0 is not an identity.** `math_sin16(0)` is 2⁻²² and `math_cos16(0x4000)` is
  ±2⁻²², not 0 (`docs/spec/core.md` 4). So the translation can move by one quarter unit
  (0.25 world units) even with offset 0 and angle 0. Executed fixed case
  (`move_piece_rest`): rest (400, −800, 40), cos 32767, sin 0, offset (0, 0, −256) (an
  `AutoDoor` opening), angle 0 gives (**399**, −800, −984). After the first call, a piece is
  therefore not necessarily drawn at its file translation, even "at rest" (I for callers
  that pass zero).
- **What it means geometrically.** Apply the drawing rule of `docs/formats/world.md`
  (translation added before the rotation). In real arithmetic the moved geometry is
  `pivot + Rrest · offset + R(angle) · (rest geometry − pivot)`, where `pivot` is
  `ref_levels.piece_pivot` and `Rrest` is the rest matrix (mirrored for flag 0x40). So the
  piece turns by +angle about the pivot and shifts by the offset in its rest frame, as
  11.3 said. The plain branch rotates the translation by −angle and the mirrored branch by
  +angle; both give +angle on screen. Checked numerically, within 0.5 units, in
  `test_ref_levels.Round2MovePiece` (I: this is algebra, not a run).
- For a native client, the exact route is: compute these five fields with
  `ref_levels.move_piece`, then draw with the world.md rule. Using the identity directly
  differs by less than one unit. Collision is not touched (11.3, now also Executed: no
  other write).

### 16.5 What changed in `tools/ref_levels.py`

All round-1 names and signatures are unchanged. The new code is in its section "Round 2
corrections and additions".

| Item | Change |
|---|---|
| `level_manifest` | step 8 takes the first `.world` in the given order (`first_entry_with_extension`), no longer `sorted(...)[0]` |
| `first_entry_with_extension` | new: `lump_findNthByExtension` 0x171fd8 |
| `level_light_alpha` | unchanged result; docstring and flag-constant comments corrected (base light level, 0x20000000 tested first) |
| `base_light_level` | new alias of the same function |
| `RecallCountdown`, `recall_request_tick`, `RECALL_*` | new: 16.3 |
| `move_piece` | new: 16.4 (`ref_core.cos16`/`sin16` for the angle) |

Tests: `tools/test_ref_levels.py` classes `Round2*` (synthetic). Comparison with the game:
`tools/difftest_levels.py`.

### 16.6 Running the tests: `tools/dis.py` shadows the standard library

`python3 -m unittest discover -s tools -p 'test_*.py'` from the repository root works. Run
from inside `tools/` (`cd tools; python3 -m unittest test_ref_levels`), it fails before any
test: the current directory comes first on `sys.path`, so `import inspect` inside
`unittest` loads `tools/dis.py` instead of the standard `dis`, and stops with
`AttributeError: module 'dis' has no attribute 'COMPILER_FLAG_NAMES'` (reproduced
2026-10-18, Python 3.12.3). The modules' own trick of appending `tools/` to `sys.path`
cannot help, because the import happens before they run. The native agent worked around it
by importing `unittest` before putting `tools/` on the path.

Proposed fix, written as a comment in `tools/test_ref_levels.py` and
`tools/difftest_levels.py` and **not applied** here, because 24 tracked files name the
script and other branches touch them: `git mv tools/dis.py tools/eedis.py` and update those
references. No module imports it, so nothing else changes.

## 17. Round 3: where the 18 origin-test levels start (2026-10-20)

**Why this section exists.** A native client that asks `terrain_height_below` 0x1834a8
for a floor at the origin, radius 4 (pattern 0x40800000), finds 18 of the 111 paired
levels empty. Those 18 are the paired archives whose first `.world` has a zero moving-piece
count (header +0x50), no chunk with flag 0x80 and no chunk with flag 0x20, and for which
that query returns the sentinel −1000000.0 (0xC9742400). The original start is a different
query. This section is that query, run on the original functions in `tools/ee_emu.py`
(`tools/difftest_levels_r3.py`, seeds 0 and 20973). The ELF SHA256 is
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.

### 17.1 The marker, then one height snap

The marker choice is section 5.2, unchanged. On a cold start (`g_prevLevelName` empty,
`g_entranceName` empty, the recall flags clear, not loaded from a save) every `Player1` is
considered in file order. The first takes at rank 1, and each later `default` whose atoi is
nonzero takes again. The last of those wins.

Among the 18 the `Player1` counts are 10 levels with one, 5 with two, 1 with six and 2 with
none (26 records). The 16 with a marker finish at rank 1. The 2 with none are the 2 that
contain an `ArenaPlayerStart`. A story load leaves their spawn at the previous value, which
is (0, 0) at boot (5.1).

`Player1_ctor` does call `world_findFreeSpot` for slot 0 (spread 36, radius 24, anyHeight 0).
The placement loop does not search slot 0 again. With the recall-return flag clear it writes
only z, for every slot below the player count (0x3211c8–0x321238):

```
spawn.z = terrain_height(f12 = 0x41400000, world, spawn)
```

`terrain_height` 0x183820 ignores the query z and returns the highest sample in that disc,
or the sentinel. **Executed** on the 18 with the player count 1 and the cold marker's xy
(the file position; the search not yet applied): xy unchanged, and z equal to that
radius-12 height. All 18 are a floor.

`Player_ctor` 0x1a1d28 stores the same radius and snaps again. `GameObject_ctor` sets
object +0x1c to 24.0. The store at 0x1a2244 overwrites it with 0x41400000. From there to
the call, no instruction stores offset 0x1c through $21, which holds the player. At
0x1a2420–0x1a245c it loads f12 from +0x1c, calls `terrain_height` and stores f0 at
object +0x18. It does not test the sentinel, does not call `terrain_height_below` and does
not move x or y. **Executed:** the stretch 0x1a2220–0x1a2264 leaves +0x1c equal to
0x41400000, and the snap stretch on the same 18 positions stores the same floor.

`g_killPlaneZ` 0x4f7188 is tested at 0x1a5b38 only when the plane is above −90000
(0xC7AFC800). Every level-table row is −100000, so the plane never fires (section 2). A
sentinel z is stored by the snap and is not removed by that test. Whether some other
first-tick test rejects a sentinel was not searched. These 18 are not that case: the
radius-12 query at the cold marker is a floor on all 18.

### 17.2 Why a query at the origin comes back empty

Of the 18, `terrain_height` at radius 4 on the origin is a floor on 11, and `terrain_height`
at radius 12 on the origin is a floor on the same 11. `terrain_height_below` still returns
the sentinel there: a sample more than 12 above the query z is skipped, and the query z is
0 (the rule in `ref_world.terrain_height_below`). `terrain_height_at_point` 0x182f28 returns
0 off the grid and never the sentinel. On these 18 it was not the sentinel, so a test that
ORs it with `terrain_height_below` reduces to `terrain_height_below`. The emulator and
`ref_world` agreed on every one of these queries (0 mismatches).

The other 7 have no sample within radius 12 of the origin. Each of them has a `Player1`,
and the radius-12 query at that marker is a floor.

The search can leave the marker. `world_findFreeSpot` 0x14acf8 tries up to 50 points.
Unless anyHeight is set, it rejects a candidate whose height is not strictly less than 6.0
(0x40C00000) above the centre, and it accepts a candidate any distance below the centre,
including the sentinel. On a total failure it keeps the centre and clears the ok byte.
**Executed** against the original on four synthetic worlds: a floor at 20 keeps the centre,
a floor at 5 is taken, a floor at exactly 6 is rejected, and an off-mesh candidate is
accepted with the sentinel. On the 18, with the object list stubbed empty and with seeds 0
and 20973, the original search matched `ref_objects` on all 36 calls, and the following
radius-12 snap was a floor on all 36. The seed at the moment `Player1_ctor` draws is not a
fixed constant, because other constructors draw `g_randSeed` 0x404464 first, so this is
those two seeds. A scatter that leaves the mesh is stored, and the snap does not walk back
onto it.

### 17.3 Arena wave start (`arena_pickSpawnPoint` 0x3050a4, a0 ≠ 0)

`arena_begin` is 0x304f5c. It runs when `g_pvpModeB` is set. If mode A is clear it calls
0x306440, stores 3 at 0x8e733a, and calls `arena_startWave` 0x305ed4 with a0 = 1. That
calls `arena_pickSpawnPoint` with a0 ≠ 0 (the call at 0x306000 passes 1), then `pool_new`
and `Player_ctor` at 0x30604c, so the radius-12 snap of 17.1 runs on the result. PvP B
skips the story `Player_ctor` in the placement loop. This is the constructor that runs
instead.

For a0 ≠ 0, **Executed** (property `arena_initial`, and the two levels below):

- The active count is the word from `net_countActiveSlots` 0x1ec878. The angle is the low
  16 bits of `s16(65535 / count) * slot`, passed to `math_cos16` 0x166630 and `math_sin16`
  0x1666e0. The multiply is the three-operand form at 0x305130. A MIPS III listing prints
  that instruction as unknown, because the destination register is not zero. A count that is not greater than 0 divides by a
  zero word. That quotient is left undefined; `arena_ring_angle` raises.
- The ring radius is 180.0 (0x43340000) when `g_pvpModeA` is set, and 36.0 (0x42100000)
  otherwise. The centre is entry 0 of the table at `*0x503888` plus `(cos·R, sin·R)`. An
  entry is 16 bytes: xyz and an s16 angle at +0xc. z is the entry's z.
- `world_findFreeSpot(centre, 36, 24, anyHeight 0)`. The ok byte is the caller's stack
  slot. When it is 0, one more search from the same centre, spread 240 (0xF0), radius 24,
  anyHeight 0. There is no third search.
- Facing, when the facing pointer is nonzero. If the word at 0x4f7124 is nonzero, facing
  is the table angle minus 0x4000. Otherwise facing is
  `s16(−0x4000 − math_atan2_16(dx, dy))`, with f12 = pos.x − entry.x and f13 = pos.y −
  entry.y (`math_atan2_16` 0x166798). When mode A is clear, facing then loses 0x8000. All
  of these are the low 16 bits.
- The word at 0x4f7124 has no symbol. The direct stores found are zeroes, at 0x323f44,
  0x1e1668 and 0x1e18d8. Its address is taken at 0x13748c and 0x1e1910. Whether a nonzero
  value is stored through those pointers is **U**. The branch was executed both ways on
  synthetic data.

On the 2 of the 18 that have an `ArenaPlayerStart`, the original wave start with count 1,
slot 0, mode A clear, 0x4f7124 clear, seed 20973 and an empty object list matched
`arena_initial_place`, and the radius-12 snap of that position was a floor, 2 of 2. A story
load of those two leaves mode B clear and does not take this path. Their origin radius-12
query is already a floor, which puts them in the 11 of 17.2. Three further archives have an
`ArenaPlayerStart` and no floor at the origin. They have water chunks, so they are not in
these 18 (→ 18).

The other entry, a0 = 0, is the respawn. Its caller at 0x305818 passes a0 = 0, and
`player_respawn` 0x1bd040 calls `Player_ctor` at 0x1bd154, so the same snap follows it.
**Observed, not executed.** When a byte at 0x402791 is set, the index is a shared-generator
draw modulo the count at 0x8e7342. Otherwise the function prefers table points within 240
of the point at 0x45f048 and, failing that, searches from that point with spread 72 and
radius 24, storing facing 0. A table point adds 0x4000 to the stored angle. The rotation
that requests the next arena level is section 18.

### 17.4 Acts, gates, and what a level change leaves alone

Act tables do not choose a marker (sections 4 and 7.2). A session starts at act −1, so the
first real level is an act change, and the placement loop writes `None` into the record's
from field (record +0x24) unless the card state is 4 or a death task is running. None of
the 26 `Player1` records on these 18 has `from` equal to `None` or to `gate` (0 and 0), so
that write matches nothing and the cold-start rule stands. `g_prevLevelName` is written
before `game_loadLevel` (7.1). `g_entranceName` is not cleared by a level change (5.1).

A gate arrival is `JumpGate_ctor` (5.2): `world_findFreeSpot(gate, 36, 24, anyHeight 1)`
for each slot below the player count, facing a full draw, rank 3 with no rank test. The
placement loop still snaps z at radius 12, including slot 0. The rank-3 test only skips the
later scatter. The anyHeight search was not re-run on the disc. Where the level has a
`Portal` or a `PortalHurt`, the gate's own xy was queried at radius 12 and was a floor.

Entry plans **executed** on the real heightfields, with an identity search and radius 12:
a cold start, each distinct `from`, each distinct `name`, the recall flag, and a gate when
a portal exists. 65 plans, and none returned the sentinel. The recall flag blocks the
`from` and `name` upgrades. The copied return xy at 0x41b520 is the player's previous
position and is not a field of the level, so it is not one of these 65. When 0x41b51c is
set, the placement loop copies that xy (not z) and then snaps z the same way.

What a level change leaves alone, re-checked against the writers in 5.1:

- `g_spawnPos` 0x4f70d0 and `g_spawnFacing` 0x4f8410 are not cleared. The writers are
  `Player1_ctor`, `JumpGate_ctor`, `save_load` (0x221f28 and 0x221eec) and the placement
  loop. With the recall-return flag clear, the z loop leaves xy where the markers put it.
  **Executed** on the 18.
- `g_playerStartRank` is cleared. `level_loadScriptAndObjects` writes 0 at 0x217ab0, or 3
  at 0x217aac when the level was loaded from a save, before the markers run.
- `g_entranceName` is not cleared (5.1).
- 0x41b51c is cleared at 0x3211c4 after the xy copy. 0x41b51e is cleared at 0x3214c0.

### 17.5 What the reference gained

`tools/ref_levels.py` gained the following and did not change the round-1 results of
`marker_decision`, `run_markers` or `place_players`. `place_players` still passes the
Python float 12.0 to its callback.

- `PLACEMENT_RADIUS` (0x41400000) and `player_ctor_z`
- `ARENA_RING_MODE_A` (0x43340000), `ARENA_RING_MODE_B` (0x42100000), `ARENA_FIRST_SPREAD`
  (36), `ARENA_RETRY_SPREAD` (240), `ARENA_SEARCH_RADIUS` (24)
- `arena_ring_angle`, `arena_ring_centre`, `arena_initial_place`

Synthetic coverage is `Round3Placement` and `Round3Arena` in `tools/test_ref_levels.py`.
`tools/vu1_emu.py` is not on this path: the queries are scalar EE. The difftest's six
properties all pass. On the disc, `spawn_real` reports paired 111, the 18 above, origin
radius-4 floor 11, origin radius-12 floor 11, marker radius-12 floor 18, search-then-snap
floor 36 of 36, arena floor 2 of 2, scenario misses 0. Private notes stay under `local/`.

## 18. Round 4: the three archives with no floor at the cold origin (2026-10-20)

**Why this section exists.** A radius-12 `terrain_height` at the cold story slot is a floor
on 108 of the 111 paired archives and the sentinel on 3. Those 3 sit outside section 17
because each has water chunks, so that section's geometry filter skipped them. A client
that snaps the cold slot therefore loads 108 and stops on these 3. The original places
them somewhere else. This section is that placement, run on the original functions in
`tools/ee_emu.py` (`tools/difftest_levels_r4.py`, seeds 0 and 20973). The ELF SHA256 is
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.

Each of the 3 has zero moving pieces, zero chunks with flag 0x20, water chunks (24, 112
and 7), no `Player1`, no `Portal` and one `ArenaPlayerStart`. The cold slot is the origin
(rank 0; the previous spawn is 0 at boot). The radius-12 query there is the sentinel, and
so is the same query at radius 4, 24, 36, 48, 64 and 96. `terrain_height` ignores chunk
flags, so a water sample counts as a floor. The queries below returned a height.

### 18.1 Who requests them

The 13 act lists (86 rows at `g_actLevelTables` 0x4f8e48) and the four level-name fields
of the 13 mission rows (`g_missionTable` 0x4fe540, +0x08 through +0x14) contain none of
the three names. **Observed.** A bounded search of every archive in the data directory
finds each name twice in its own archive, as the lump name and the `.world` name, and in
no other archive.

The names live in the mode-A pointer table at 0x5037b8: 13 names, then a null. The three
are indices 8, 10 and 12. Two of them also sit in the mode-B table at 0x503798 (7 names,
then a null), at indices 1 and 3. The mode-B selector below reads index 0 of that table.

**Observed**, frontend 0x1e18f4–0x1e1984. The chosen menu string is tested with `strstr`:

- the substring at 0x53d008 (`vs`) stores 1 or 0 at `g_pvpModeA` 0x4f711c
- the substring at 0x53d010 (`scramble`) stores 1 or 0 at 0x4f7124
- the substring at 0x53d020 (`arena`) contributes to `g_pvpModeB` 0x4f7120

Mode B is stored as 1 when the arena substring hits, or when the facing word was set.
Every store that names the displacement 0x711c or 0x7120 writes 0: mode A at 0x1e1664,
0x1e18dc and 0x323f34, and mode B at 0x1e1670, 0x1e18e4, 0x307160, 0x3234f4 and 0x323f38.
The menu tests above, and the net launch below, store through a register that holds the
address. When mode A is set, this handler opens the menu at 0x4f6c98.
`frontend_startPlayerSelect` 0x1e3ba0 also runs from 0x1e19c0, 0x1e1a48, 0x1e1a78,
0x1e1ad0 and 0x1e1ba4. With mode B set it copies the name from the picker 0x304bc8 to
0x4fdc30.

The picker, **observed**:

- Mode A set: `game_scanCm1Vars(0)` returns the word at 0x4f7110, and that word indexes
  0x5037b8.
- Mode A clear: the dividend is the mode-A word, which is 0, and the divisor is the
  halfword at 0x503886, which is 5. The remainder is 0, so the record at 0x503868. Five
  records of 6 bytes live there. The first byte's low nibble, through the shift in
  `arena_record_table_offset`, is the table-B index. Those five nibbles are 0, 1, 5, 3
  and 2. Record 0 selects index 0, which is not one of the three. The high nibble is the
  count walked by 0x306440; it does not select the level.

`game_set4f7110` 0x1ec830 stores its argument at 0x4f7110, or the result of
`game_scanCm1Vars(1)` when the argument is −1. That scan walks `m11cm1`, `m9cm1`,
`m8cm1`, `m7cm1`, `m6cm1`, `m5cm1`, `m4cm1`, `m2cm1` and `m1cm1`. It returns 0..7 for the
first one set, 8 when `m1cm1` is set, and 9 when none is set. The frontend at 0x1e204c
and boot at 0x323e90 pass −1, so the saved index on that path is 0..9. Net launch
0x1374a8 clears both mode words, sets mode B when its type byte is 1, 2 or 3, sets mode A
when the type is 2 or 3, sets 0x4f7124 when the type is 3, and then, if mode A is set,
stores the word at offset 0xf4 of the message as the index. That word is not clamped.
What a peer writes there is **U**.

The rotation is `arena_runTask` 0x306b78. When the countdown halfword at 0x8e733c reaches
0x1e0, or 0x3c0 while `g_networkMode` is set, and the halfword at 0x8e733a is nonzero:
if mode A is clear the task calls `arena_nextWave(1)` and stays on the same level. If mode
A is set, the byte at 0x8e7343 becomes `(byte + 1) mod 13`, and a remainder of 0 is
replaced by `game_scanCm1Vars(0)`, the saved index. Table A of that byte is copied to
`g_pendingLevel` with orientation 0xff (the copy is at 0x306cb8). `arena_begin` 0x304f5c,
called from the load at 0x1e6028, stores 3 at 0x8e733a. That is the only store with
displacement 0x733a.

The byte survives an arena-to-arena load. `arena_init` 0x304c4c returns at once when mode
B is clear. When mode B is set, 0x307d48 reports whether `g_prevLevelName` is in the
current mode's table. If it is, and the word at 0x503894 is 0, init skips the reset and
leaves the byte alone. The timer path does not store 0x503894. It also does not call
`arena_shutdown` 0x304fb0, and that function is the only remover of the arena task: the
pointer 0x306b78 is built only at 0x304de0 (the `task_add` in init) and at 0x305000
(the `task_remove` in `arena_shutdown`). The next timer therefore advances the same byte. The word at 0x503894
is cleared on the full init path (0x304dcc) and set to 1 at 0x306dd4 and 0x306f94; the
load after that takes the full init and stores the saved index back into the byte.

On the menu path the saved index S is 0..9. The levels played are table A at S, then
S+1, and so on through 12, then S again. Indices 10 and 12 are on every such cycle.
Index 8 is on it for S in 0..8, and it is the first level when S is 8. It is absent when
S is 9.

The mode-B path at 0x306cc8 reads the halfword at 0x8e7338, adds 1 in a register, divides
by 3 and then by the record count, and does not store the sum. The strcpy is at 0x306d1c.
The only store with displacement 0x7338 is 0x304db8, which writes −1. `(−1 + 1) / 3`
modulo 5 is record 0 again. That path is reached when 0x8e733a is 0 and mode A is clear.
After `arena_begin` the halfword is 3. Init (0x1e5cdc) and begin (0x1e6028) both sit
inside the load, init first.

### 18.2 The point the player stands on

`arena_init`, on the full path and on the continuation, stores 1 at 0x8e7342 and calls
0x30503c with index 0 and xyz 0. Entry 0 of the table at `*0x503888` is the origin until
a record replaces it.

The `ArenaPlayerStart` factory at 0x15a284 calls 0x30503c with a0 = 0. It overwrites
entry 0 and leaves the count alone. The `ArenaPlayerAlternate` factory at 0x15a2b0 calls
it with a0 = −1, so it writes at the count and increments. With the count at 1, the first
alternate is entry 1. Entry 0 is the Start, whichever record was built first.

`arena_begin` runs when mode B is set (17.3). Mode A set skips 0x306440, and the ring
radius is 180 (0x43340000). `arena_startWave` calls `arena_pickSpawnPoint` with a0 = 1.
PvP B skips the story `Player_ctor`. The radius-12 snap of 17.1 runs on this result.

Slot 0's angle is `s16(65535 / count) * 0`, which is 0 for every positive count, so that
slot's centre does not depend on the player count. `cos16(0)` is 1 and the x offset is
exactly 180. The y offset is `sin16(0)` times 180, which is not 0. z is the Start's z.

**Executed**, count 1, slot 0, mode A set, 0x4f7124 clear, the collect stub writing an
empty list, seeds 0 and 20973: the original wave start matches `arena_initial_place` on
6 of 6 calls. Radius 12 at the origin is the sentinel, 0 of 3. At the Start it is a
floor, 3 of 3. At the mode-A slot-0 centre it is a floor, 3 of 3. The ctor snap stores
that floor, 6 of 6.

The same radius-12 query is a floor at the mode-A centres for counts 2 and 4, every slot.
Those centres were compared in the reference. The emulator ran the wave start for slot 0.

### 18.3 Whether the seed and the object list move the snap off the floor

`world_findFreeSpot` returns a point at most 36 from the centre. When every try fails it
keeps the last point that passed the terrain tests, or the centre. An object only rejects
a try (17.2). The result stays inside that disc.

On each of the 3, at the mode-A slot-0 centre and at the other angles of counts 2 and 4:
every integer offset inside radius 37 has a floor at radius 11.25, 0 misses out of 4293
on each centre. A point of the spread-36 disc is at most half a unit from one of those
lattice points on each axis. 11.25 plus that distance is under 12, and radius 37 leaves
more than that distance outside the spread, which covers a candidate the adder places a
few ulps past 36. Every point the search can return has a radius-12 floor, and so does
the centre. The seed changes which point is chosen. The ground result stays a floor for
every seed and every object list.

**Executed** on the original with the empty collect stub, the two seeds: 6 of 6 snaps are
floors, and the positions match the reference. The reference search with every parsed
record constructed at its xyz, default radius 24 and flags 0 (solid), also snaps to a
floor, 6 of 6. Those stand-ins are not the radii the class constructors store. The
lattice is what covers the real list. The emulator agreed with the reference on the
origin, the Start, the slot-0 centre and every searched point (0 mismatches).

A disc with a hole does lose the floor. **Executed** on a synthetic one-sample pad: one
seed of the original search keeps a floor and another accepts a point whose radius-12
snap is the sentinel (`seed_matters`). On a synthetic solid disc the same call keeps a
floor. The reference, for seeds 0..15 and 20973, with and without a solid object on the
centre, keeps a floor on every call, including the calls that return ok 0.

### 18.4 What the reference gained

Round 1–3 results of `marker_decision`, `run_markers`, `place_players` and the round-3
arena functions are unchanged.

- `ARENA_MODE_A_COUNT` (13), `ARENA_MODE_B_COUNT` (7), `ARENA_RECORD_BYTES` (6)
- `arena_mode_a_next`, `arena_record_table_offset`, `arena_register_spawn`

Synthetic coverage is `Round4ArenaEntry` and `Round4Ground`. `tools/vu1_emu.py` is not on
this path. The difftest's two properties pass. On the disc, `cold_three` reports cold 3,
origin floor 0, Start floor 3, ring floor 3, search snap 6 of 6, stand-in snaps 6 of 6,
lattice misses 0, act hits 0, mission hits 0, other-archive name hits 0. Private notes
stay under `local/`.

Still **U**: `arena_pickSpawnPoint` with a0 = 0 (17.3), and the word a net peer stores at
message offset 0xf4.
