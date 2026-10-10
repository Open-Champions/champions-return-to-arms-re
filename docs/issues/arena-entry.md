# Entering the Drundar arena: level change, load, first frames, opening cutscene

Companion to `docs/issues/arena-desync.md`. That document worked through the fight. This
one covers everything between the script command that leaves `drundar` and the last tick of
the arena's opening cutscene `knights`, on every machine of a net game.

Everything here was read from the executable (SLUS_209.73, v2.00) and from the unpacked
level files of `drundar` and `drunare`. **Nothing was run, and every patch below is
untested.** Claims are **Observed** (read at the address given), **Inferred** or
**Unknown**. New names are in `symbols/entry.tsv`.

## Result in short

| Question | Answer |
|---|---|
| Is anything in this phase per machine in an ordinary entry (two living players, no menu or card screen open)? | **No route to shared state was found.** The frame every machine leaves on, every shared-seed draw of the load, the start positions, the trigger test, the cutscene set-up and its 1,270 ticks all take only lockstep inputs |
| What is per machine in this phase | (a) the tick the first prediction copy is made after the load, and whether it is frozen with the players; (b) the checkpoint autosave on the first tick (gated by local card, menu and camera state); (c) the number of load warm-up passes and the frame-warm-up counter that `cut_start` restarts; (d) the camera; (e) a notice box that runs the pending post-action script from the draw pass; (f) the boss-meter bit in a creature's flag word. For each, the readers were followed: none reaches the sync hash in the default case |
| New mechanism worth a ledger row | **E9**: closing a per-player notice box runs the pending post-action script in the *draw* pass, on that machine only, with no network test (0x1dd1f0). The sibling path for the full-screen help box has the test (0x1dcf58). In this level a post action is pending for the whole of `knights` and of `bossdefeated` |
| Most useful next step | Record the frame of the first hash mismatch relative to three marks (first tick in the level, cutscene start, cutscene end) and use the two bisecting patches X1 (no prediction copy) and X2 (cutscenes end in the tick they start). Table at the end |

So this phase does not explain an every-run desync either. What it adds is a precise list of
what must be equal at each mark, so that one two-machine run can say which side of the
opening cutscene the divergence is on.

## Timeline

N is the lockstep frame in which the script wrote the next-level name. All **Observed**
unless marked.

| # | When | What | Where |
|---|---|---|---|
| 1 | tick N, object pass | In `drundar` one of four `Trigger` rectangles (run from a 15-frame list) or one of four `PushTrigger` doors (from `Player_interact`) runs the script entry that ends in `newWorld('drunare')`. The handler passes the net gate, calls `net_closeLocalMenus(0)` and writes the name into `g_pendingLevel`; no entrance property, so the orientation byte is 0xff | 0x1ecf3c, 0x1ecc70 → 0x14dcc8; 0x143dd0, 0x143d04, 0x1472c4 |
| 2 | rest of tick N | The other tasks of the pass run; `g_netFrame` becomes N+1; the sync record for N+1 is stored and compared | 0x13aee0–0x13b048 |
| 3 | same `net_frameLoop` call | Further steps do nothing: each step tests the name first. A rebase of the prediction copy can still happen at the end of the call | 0x139fb4–0x139fbc; 0x13b1c8 |
| 4 | next main-loop pass | Cancel test (level loaded, no `frontend` task, card not busy, not PvP, nobody above 0 hit points): not met here | 0x322c00–0x322ca8 |
| 5 | | If this machine's card write flag is set: private frame loop until the save screen has closed itself (in a net game the "saved" box closes at once when a level name is pending) | 0x322cf4–0x322d04; 0x32393c; save screen sub-state 4 |
| 6 | | `net_flushBeforeLoad`: `net_main(1,1)` plus a vertical-blank wait, until every peer that is neither dropped nor being kicked has acknowledged this machine's input up to `g_netFrame`; at most 121 passes | 0x322d18; 0x132db0, limit 0x132e48 |
| 7 | | `g_simFrame = 0`; display blanked; local `Camera_reset` unless this machine's card latch 0x4f8f28 is set; creature serial counter 0x4f85c4 = 0; world pieces not drawn until the end of the change | 0x322d34, 0x322dc4–0x322dfc, 0x322e20, 0x322e2c |
| 8 | | `mainloop_loadRequestedWorld`: store `drundar`'s object state in the save buffer; no act change (both levels are in the first act's list); `game_loadLevel("drunare")`; players created | 0x322e30; 0x320edc |
| 9 | | frame warm-up counter = 10; the deferred-script queue is promoted once; `g_ghost = 0` | 0x322e58, 0x322e6c, 0x322e98 |
| 10 | | Load warm-up loop, a per-machine number of passes (at least 10): rebuild the alive lists, `Camera_update`, `drawWorld`, `cut_runFrame(1)` only if a cutscene is already active (none is), disc and texture service | 0x322eb0–0x322fd0 |
| 11 | | `net_main(1,0)` (this appends new input records), clear the heard flags, then `net_main(1,1)` once per displayed frame until every peer has been heard or the long-stall counter reaches 601 | 0x323014–0x32305c |
| 12 | | Loading screen stopped; `g_simFrame = 0` | docs/mainloop.md step 11 |
| 13 | tick N+1 = **F0** | First tick in the arena. Uses the input records for frame N+1, which were sampled in `drundar` | 0x139e88 |
| 14 | F0, task 20 | Checkpoint autosave if this machine's gate is open | 0x2188a8 |
| 15 | F0 … F0+30 | Each machine makes its first prediction copy on its own tick | 0x13b1e8 |
| 16 | tick **S** | The `incoming` trigger finds a player inside: script starts `knights`, sets the post action, sets `sawknights` | 0x1ed15c; scripts/DRUNARE.txt |
| 17 | S, task 300 | `cut_setup`: actors bound, every creature with inert byte 0 frozen (players included) | 0x19a6cc; 0x199024 |
| 18 | S+1 … E−1 | Only the four actors, the props and the tasks run. Players do not run | arena-desync.md F2 |
| 19 | tick **E** ≈ S + 1,270 | Keys exhausted: `cut_end`, camera mode 1, post action `nosave`, 60 ticks of hit immunity | 0x199ef8–0x199f8c |

## 1. The level change in a net game

### 1.1 Who decides the frame

- The name is written by lockstep code inside a tick (step 1). Both routes in `drundar` are
  object-pass code: `Trigger_run` tests the positions of the player objects in slot order
  and sets `g_scriptActivePlayer` to the first one inside (0x1ed15c); `PushTrigger_interact`
  is reached from `Player_run` → `Player_interact`, which sets the active player to the
  presser (0x1b2b70) and only when called from the run path (its display-only call from
  `Player_draw` skips that block). **Observed.**
- The gate `newWorld_netGate` reads the active player's cooldown (record +0x4bca) and the
  alive count. The cooldown is counted down at the tail of `Player_run` behind a test for
  the prediction copy (0x1ac6b0–0x1ac6e8), so it is the same on every machine; it does not
  count while that player's run returns early (inert, hidden, frozen in a cutscene).
  **Observed.** A refusal is therefore also the same everywhere. (The alive count is the
  G11–G13 list; not re-examined.)
- No game message is involved on this path. Messages 3/7 and 3/11 are the pause-menu and
  mission-menu routes.

### 1.2 What is flushed, and what is not

- Flushed: this machine's input up to `g_netFrame` must be acknowledged by every active
  peer (step 6). Because the lead is at least 2 (docs/netcode.md), the record for frame N+1
  already exists on its owner and is normally delivered before anybody loads.
  **Observed** rule, **Inferred** consequence.
- Not flushed: input records beyond `g_netFrame` (up to 38 of them) and any game message
  queued in tick N. `net_closeLocalMenus(0)` queues menu-state message 3/2 for the local
  slot on every machine (0x1eb02c → 0x1de0dc). A message is attached to an input frame
  that has not been sent yet and is not older than `g_netFrame` (docs/netcode.md), and no
  tick runs before F0, so those messages are executed in the arena, each on one lockstep
  frame. Their handler sets the 10-tick "menu closed" countdown (record +0x4bc8), clears
  object flag 0x800000 and masks the owner's face buttons for 60 calls (0x1d8dbc–0x1d8df0).
  **Observed** pieces, **Inferred** timing.
- The first `lead` ticks of the arena therefore run on stick and camera-yaw samples taken
  in `drundar`. Same records everywhere.

### 1.3 How the first frame is agreed

There is nothing to agree: F0 = N+1 on every machine because no step ran after N. A machine
may run F0 as soon as its own load and the barrier are done; it already holds the peers'
N+1 records. The barrier only waits for one accepted packet per peer since the flags were
cleared (step 11). Its escape is `g_netLongStallCalls` ≥ 601, and that counter only starts
after 300 calls without a tick, counted from the flush on (0x134408–0x134448), so the wait
is at most about 900 calls. The per-peer silence counter keeps counting during the wait and
starts a kick above 900 (0x133060). **Observed** constants; **Inferred:** a machine that
needs about 15 seconds longer to load than another is dropped, not desynchronised.

### 1.4 What the load does to shared state, in order

| Step | Shared effect | Per-machine input | Where |
|---|---|---|---|
| `save_storeLevelState("drundar")` | writes this machine's save buffer only | skipped while this machine's card state is 4 (load screen) or the level has option bit 0x800; always returns 0, so the early return that follows the call in the caller cannot happen | 0x320f44; 0x21777c |
| act-change block | not entered: `drundar` and `drunare` are rows of the same act list (table pointers 0x4f8e48) | — | 0x320f9c |
| pending character selection | `playerSel_applyPending` re-creates a character for every slot with a pending choice when 0x4fbbd8 is set, then clears it | 0x4fbbd8 is menu state; reachability in a net game **Unknown** (set by `playerSel_start`, cleared by `playerSel_finish`) | 0x321024; 0x2247ec |
| `game_clearLevel(1)` | destroys every object (grid A, grid B, off-grid list with mask 0; delete list with the exclude mask), zeroes the name table, both round-robin cursors, the deferred queue, save inhibit, recall countdown, active player; unloads keep-level-0 lumps; rebuilds the pool free lists | the prediction copy is destroyed here with `g_inGhostOp` clear, so its destructor also zeroes the slot's object pointer and five record words; the real player's destructor does the same on every machine, so the end state is equal | 0x1e5674; 0x1e4e88, 0x14c460; 0x1a1bb8 |
| item loader (223 shared draws) | not run: `hud.lmp` is loaded on every machine after the first level of a session (docs/issues/sync-breakers.md 6b) | — | 0x1e5690–0x1e56bc |
| `game_loadPlayerLumps` | returns 0 when the loaded model lumps and the equipment cache match the records; otherwise reloads them and re-validates two appearance bytes of each record against the selection lump | the reload is also taken when the card state is 4; the result written is data-determined | 0x1e5708; 0x1e5148 |
| loading screen | one cosmetic draw before the copy below; the thread itself draws from neither generator (scan of 0x32187c to call depth 3) | — | 0x1e5758; 0x321ea0 |
| `g_cosmeticSeed = g_randSeed` | the cosmetic generator is equal on all machines while the objects are built | — | 0x1e59b4 → 0x1e59c4 |
| script image | script globals start from the file: the level lump was unloaded with the other keep-level-0 lumps at teardown and is read again (Inferred from docs/issues/sync-breakers.md 6b) | — | 0x217a74 |
| start rank = 0 | (3 after a load from a save) | flag 0x8e1ad6 is set only by `save_load` | 0x217aac–0x217ab0 |
| `preStart` | not defined in this level | — | 0x217acc |
| saved level state | none for `drunare` on a first visit (directory `g_saveLevelDir` has no entry) | this machine's buffer; see section 5 | 0x217978 head |
| `objects.ob`, 39 records in file order | one shared draw per constructed object for its own generator; creatures take a serial number from the zeroed counter; slow-list links advance the two cursors; `Cazic_ctor` stores `g_simFrame`, which is 0 on every machine here | — | 0x14e808; 0x14cd54; 0x109e14; 0x24a6dc |
| `Player1` record (fifth in the file) | four `world_findFreeSpot` calls and four single shared draws (section 2) | — | 0x158928 |
| `start` | hides Rallos, the avatar and all four objects named `knight` (the name lookup returns every match); removes a quest; `getv('killedAv')`; two `setMonsterVal` | — | 0x217bac; 0x144c00, 0x14bf58 |
| `script_runPostAction` | runs a left-over post action in the new script. The buffer is not cleared by level teardown; its only clearers are this function and `script_resetState`. `drundar` never sets one | a machine that already consumed it through E9 has none left | 0x1e60b8; 0x1edac0 |
| `save_armAutosave` | countdown 0x88d40c = 1 | not armed while this machine's card state is 4 (the test for 8 can never be true: no caller sets that state) or a `deathTask` runs | 0x217f14 |
| hit immunity | record +0x4c27 = 30 for every player | — | 0x1e61c0–0x1e61f0 |
| players | section 2 | `net_isSlotActive` (dropped flag, which changes on a lockstep frame) | 0x321294–0x321414 |
| deferred queue | promoted; empty here | — | 0x322e6c |
| warm-up loop | nothing shared: alive lists (idempotent), camera, texture requests; `world_draw` draws no piece while 0x44f054 is 0 | pass count | 0x322eb0–0x322fd0 |
| shop stock | not for this level | — | 0x323064–0x3230f4 |

**Answer to "does anything advance the shared seed a per-machine number of times":** no.
Every shared draw between tick N and F0 is in a constructor, in `Player1_ctor` or in the
two `world_findFreeSpot` loops, and their inputs are the level file, the terrain and the
objects already built. **Inferred** from the rows above. Weakest link: the constructors
were scanned for per-machine reads to call depth 3 (`Player_ctor`, `Horsemen_ctor`,
`Cazic_ctor`, `AutoProp_ctor`, `Trigger_ctor`, `PushTrigger_ctor`, `Player1_ctor`), not
read line by line; `Zek_ctor` and the light and settings records were not scanned.

### 1.5 What F0 starts with

| State | Value at the start of F0 | Equal on all machines? |
|---|---|---|
| `g_randSeed` | value after tick N plus the load's draws | yes if the load is deterministic (1.4) |
| `g_cosmeticSeed` | copy of the shared seed at 0x1e59c4 plus the cosmetic draws of the constructors and the music choice (0x1e5a40) | equal until the first drawn frame; per machine from then on |
| `g_netFrame` | N+1 | yes |
| `g_simFrame` | set to `g_netFrame` inside the tick; between ticks it is 0 until this machine's first rebase | inside ticks yes |
| level tick counter 0x4f85cc | 0 | yes |
| lockstep pads | rebuilt from records N+1 by `pad_apply`, with the per-peer previous-button state carried across the load | yes (FINDINGS G5) |
| player records | carried over. Changed by the load: +0x4c27 = 30; the quest list (the `start` script); nothing else found. Cooldown +0x4bca = 600 for the player who triggered the change | yes, except the bytes already known to be per machine (+0xed, +0xee, +0x4a58, +0x4a5c) |
| creature serial numbers | creation order from 0 | yes |
| run lists | level objects in creation order on the slow lists; players at the head of the active list, highest slot first | yes |
| name table, pool | rebuilt | yes |
| quest variables | carried over | section 4 |
| prediction copy | none; the real local player does not have flag 0x200000 yet | per machine, by design |
| local camera | reset and settled during the warm-up loop | per machine, by design |
| frame warm-up counter | 0 (the loop only ends at 0) | yes at this point |
| save buffer | still the last snapshot from `drundar` plus `drundar`'s level state | section 5 |

## 2. Player placement

**Observed** in `Player1_ctor` 0x158928, `world_findFreeSpot` 0x14acf8 and
0x321160–0x321414.

- `drunare` has one `Player1` record and it has no properties. With the start rank at 0 it
  becomes rank 1 ("first one found"). It then fills all four spawn slots, whatever the
  player count: for each slot one `world_findFreeSpot(centre = marker, range 36, radius 24)`
  and one more shared draw for a facing of marker angle ± 2000.
- `world_findFreeSpot` tries up to 50 times: a point in the unit ball by rejection (three
  shared draws per attempt), scaled by the range in x and y; accepted when the terrain test
  0x183b48 passes, the height is within 6 of the centre's and no collidable grid-A object
  overlaps (box query, so the exclude mask and the prediction-copy flag apply; neither
  exists during a load). The result is the last point that passed the terrain tests.
- After `game_loadLevel` the session code gives every slot a terrain height, and for every
  slot but 0 (rank is not 3) a second `world_findFreeSpot(centre = its spot, range 36,
  radius 14)` and 8000 added to the facing. The call is made for every slot index below the
  player count, alive or not.
- A `Player` object is constructed, in slot order, for each slot whose record has hit
  points above 0 and whose peer is not dropped. A player who is dead at the door gets no
  object in the arena. Each constructor links itself at the head of the active run list
  (docs/issues/arena-desync.md F1), takes the next creature serial number and makes the
  shared draw every object makes for its own generator (0x14cd54).
- Resulting region: slot 0 within 36 units of the marker, the others within 72. The marker
  is about (333, −215), just inside the south-east door.
- The prediction copy: `net_clearGhost` only zeroes the pointer; the rebase clock
  0x4027d4 keeps its value from `drundar`. The first copy is made at the end of the first
  `net_frameLoop` call in which `g_netFrame` − 0x4027d4 > 30, or at once if
  `g_forceGhostRebase` is still non-zero from the old level, and only while the local
  player has an object, the game is not paused and the local pause menu is closed
  (0x13b1e8–0x13b23c). So between 1 and 31 ticks after F0, a different tick on each
  machine. The copy is linked into the grid (0x14f120 after the clone) but its run link is
  left empty by the clone, so it is on no run list.

Verdict: start position, facing, creation order and run-list order are fixed by lockstep
state. **Inferred** from the Observed steps.

## 3. The opening trigger and cutscene

### 3.1 Nobody starts inside

**Observed** from `objects.ob` and `Trigger_ctor` 0x1ecdf4 / `Trigger_contains` 0x1ed238
(rectangle = marker corner to corner + (w, −h), inclusive edges).

- The `incoming` rectangle is a north–south strip across the arena: x from about −36 to
  183, y from about −547 to 548.
- The spawn region of section 2 has x ≥ 261. The nearest possible start is 77 units from
  the strip, slot 0 at least 113. The level's second rectangle (the way back to `drundar`)
  starts at x = 415 and cannot contain a start either.
- A `Trigger` is on one of the fifteen 15-frame lists (round-robin cursor, zeroed at
  teardown and advanced before use, 0x14f330). The only other callers of that function are
  the `Shooter`, `FloorSwitch` and `FallPlatform` classes, none of which is in this
  level's file, so the exit rectangle gets list 1 and `incoming`, the next record, list 2:
  it is tested on ticks with `g_netFrame` mod 15 = 2. **Inferred** from Observed pieces.
- The trigger is edge-driven: it runs its script when "somebody inside" changes, and the
  inside flag and delay are part of the level's saved state (slots 8 and 9, 5 bytes).

So S is the first tick with frame mod 15 = 2 on which a player object stands in the strip:
some tens of ticks after F0, never F0 itself. Whether a machine already has its first
prediction copy at S is a matter of that machine's rebase clock.

### 3.2 Can the load warm-up loop touch this cutscene?

No. The loop (step 10) runs before F0 and the cutscene starts from a trigger inside a tick.
`cut_runFrame` has two callers, the task wrapper (argument 0) and that loop (argument 1);
the second matters only for a cutscene started by `preStart`, `start`, the load-time post
action or the promoted deferred queue. **Observed.**

What does happen: `cut_start` itself calls `mainloop_startWarmup` (header flag 2 is clear,
0x19b514), inside tick S. The frame warm-up counter 0x506048 is then counted down once per
*displayed* frame by each machine (docs/mainloop.md step 11) and the same call is made
again in tick E (0x199f44). Readers of the counter inside a tick, complete list from
`gxref`: `hud_tickMessage` (HUD timer), the pause-menu opener, `Camera_update` (user-control
flag), and three offline-only tests (`tasks_run` 0x322794, `game_isFrozen`, the clock test
in `cut_runFrame` 0x199bd8, which is bypassed by the network flag). **Observed**; no
shared effect.

`cut_evalCamera` 0x19712c, asked about in docs/mainloop.md P9: it recomputes the camera
from the clock on every call and keeps one latch, the time of the last camera cut for
which it raised a fade wait (0x44fd00, zeroed by `cut_start`). Its other outputs are the
cutscene camera globals, the colour offset, the screen darken level, the per-machine
fade-wait counter and texture requests. **Observed** (every store and call in the function
was listed).

### 3.3 Tick S, in order

1. Task 0, `gameSetObjectVis`: no cutscene yet, so activity is judged from players.
2. Task 10, `runObjects`: the active list (players included) runs first, then the 15-frame
   list with the trigger. Script `incoming`: `cutScene('knights')`, then
   `postAction('nosave')`, then `setv('sawknights', 1)`.
3. Inside `cutScene` → `cut_start` 0x19b4dc, all on every machine: frame warm-up;
   `net_closeLocalMenus(0)` (queues 3/2 for the local slot, closes this machine's pause
   menu, inventory, shop and card screen if open, resets all notice boxes 0x1e03c0);
   removes one spell type (`SpellFireFlares`) from every player; clock = 1; input lockout
   60; local camera mode 0; adds the two cutscene tasks.
4. Task 20, save daemon: camera mode is now 0, so no autosave from here on.
5. Task 300, `cut_runFrame` (reached in the same pass, arena-desync.md F3): `cut_setup`,
   one `cut_advance`, camera, skip test.

`knights` (file facts, **Observed**): header flag 8; four bound actors, the knights, each
given the serial number in its actor record; 57 keys over 21.15 s; no dialog file, no
music key, so the lip-sync preload block (docs/engine.md P6), the voice hand-shake and the
audio nudge are never entered in this cutscene (no dialog table is loaded, 0x44fd1c stays
0, and the key list has no dialog keys). Camera cuts at 10.9 s and 17.3 s. The knights are shown at time 0, given
walk targets from 10 s on and placed at their fight positions by the last four keys.

### 3.4 What is frozen, and what the copy does

- `cut_setup`'s three walks go over the run lists (0x14a7c8) with the exclude mask. The
  prediction copy is on no run list (section 2), so the walks cannot touch it whatever the
  mask is. **Observed.**
- A copy made before S is therefore not frozen: on its owner's machine it keeps running
  from local input, on the grid, for up to 30 ticks, while the real player stands off the
  grid with inert bit 4. Box queries skip it (flag 0x20000), actors are bound by box query
  and by type name, and nothing calls its take-damage slot, so no route to shared state was
  found; this is the G-series audit, not repeated here.
- Every copy cloned during the cutscene copies the frozen player's flag word and inert
  byte. Its `Player_run` takes the inert branch (0x1a55a0–0x1a5604): animation only when
  the action state +0x58c is 0, nothing when it is neither 0 nor 1, and the scripted walk
  only when it is 1, which the freeze does not set. **Observed.**
- `cut_end`'s restore walk (0x199074) again goes over the run lists, so the copy stays
  frozen after tick E until the next rebase, up to 30 ticks. On the owner's screen the
  character stands still for that long while the real one already moves. Presentation
  only, as far as the readers of the copy go. **Inferred.**
- Machines differ in which of these cases they are in. A machine whose pause menu is open
  makes no copy at all.

### 3.5 Ticks S+1 to E

- `g_cullByCamera` is set from the local camera's mode word at the start of every tick
  (0x1e4d48). `cut_start` wrote 0 there after closing the menus that could write 1, so it
  is set on every machine (arena-desync.md, D6/D7 section).
- The camera transition flag (+0x48) cannot be pending here: see correction 1.
- Each tick: the four actors run with the cosmetic seed forced to clock + index
  (0x1992a8), then a blocking pathfinder pass (0x1992e8), then the keys. The walk keys
  clear the inert byte around their set-state call and put it back without the hidden bit
  (case 0 of `cut_execKey`).
- **The sync hash should not change at all between S+1 and E.** Players do not run, so
  their positions are fixed, and no shared draw is on the path of an idle or walking actor:
  `Creature_run` draws only for a burning creature (0x1133e8) or a corpse (0x1126ac), and
  the walk draws from the shared seed only in its last-resort teleport after 300 stuck
  ticks (docs/creatures.md). In a game where every character is lobby-stored there is one
  shared draw on frames divisible by 1800 (`gameMiscSync`). **Inferred.** This makes the
  cutscene a clean probe: see the recording table.
- Skip: the test reads the pressed word of the lockstep pads (0x199df0); on a press every
  machine runs `cut_advance` to the end inside that tick. The same button opens the pause
  menu on the presser's machine only, which is the usual message-driven menu state.

### 3.6 Tick E

`cut_end` 0x19a0dc: tasks removed; bound actors lose flags 0x88000 and inert bit 1; every
creature whose inert byte is exactly 4 is unfrozen; non-persistent animation tracks of the
living players dropped. Then, still in `cut_runFrame`: frame warm-up again; camera mode 1;
`script_runPostAction` → `nosave` (save inhibit on; the avatar's boss bit, which only
restarts music, 0x1192b0); `player_setHitImmunity(−1)`: record +0x4c27 = 60 for every
player; cosmetic seed = `g_simFrame`. **Observed** 0x199ef8–0x199f8c.

Hit immunity (new detail, **Observed**): `Player_takeDamage` ignores a hit while record
+0x4c27 is positive (0x1b5438). The byte is 30 after every level load and 60 after every
cutscene in a net game (0x1bfaf8), and is counted down at the top of `Player_run` for real
players only (0x1a5330–0x1a5384). Lockstep; it means the knights' first second of attacks
does nothing.

## 4. Quest variables and saved level state

- **Where they live.** `g_questVars` 0x86da80, a packed list of name, NUL, one signed
  value byte, in this machine's memory. Never transmitted. `getv` appends a missing name
  with value 0 (0x1ed778), so the *order* of the list can differ between machines; lookups
  are by name. **Observed.**
- **Writers of values** (all ten callers of `vars_set` and three of `vars_clearAll`):
  script `setv`/`addv` (lockstep); `Player_usePotion` (a first-drink flag, real player
  only, inside the tick) and `inventory_equipItem` (a bow flag, in a message handler);
  `inventory_giveItem` (offline only); `game_resetState`, which zeroes every value at a
  net launch (0x1e6f58 from 0x1e0b40); the act-change block (0x32101c); `save_load`, which
  zeroes and then restores from this machine's save buffer (party-wipe reload inside a
  tick, or the load screen); two places in the selection screen (`needPlayers`); and a
  deferred pair in the session start code that has no writer (docs/mainloop.md).
  **Observed.**
- **On a first visit in a session** `sawknights`, `killedAv`, `knight1`–`knight4`,
  `sawcaz` and `endsound` are 0 on every machine, because the launch zeroed them and only
  this level's script writes them. **Inferred.** A player's own saved game cannot bring a
  value in: the launch discards them and the save buffer is cleared in the hand-shake
  (0x1375cc).
- **How they could differ later:**
  1. A machine whose card latch 0x4f8f28 is stuck skips the act-change clearing
     (docs/issues/sync-breakers.md N1). Both levels are in the first act, so this needs a
     trip to another act and back within the session.
  2. A party-wipe reload restores each machine's own snapshot. The snapshots are equal when
     the last `save_game` ran on the same tick everywhere (section 5, E8).
  3. The post action `nosave` does not write a variable, so E9 cannot change one here.
- The script never resets `knight1`–`knight4` or `sawknights`. On a second visit with
  `sawknights` set, `incoming` only sets the avatar's boss bit; the knights stay hidden
  because only the cutscene's keys show them. Same on every machine.
- **Saved level state.** `save_storeLevelState` reserves a fixed size per level from the
  act table (both levels have a row) and writes three sections; the loader restores them
  when the directory has the level's name. On the first entry there is no entry for
  `drunare`, so nothing is restored. A re-entry restores from this machine's buffer:
  object records with their state bytes (trigger inside flag, prop states, creature
  state), decals and the explored map. The buffer is written in lockstep; the known ways it
  can differ are the card-state-4 skip above, the stuck latch, and contents that follow a
  local option (decals). Not traced further: the level cannot be left before the avatar is
  dead, and its ending goes to `hub2`.

## 5. This pair of levels

| Carried from `drundar` | Where it lives | Per machine? |
|---|---|---|
| quest variables (`drun_*`, `pillar*on`) | `g_questVars` | no |
| player records: hit points, mana, cooldown +0x4bca, quest list, inventory | record table | no (known menu bytes aside) |
| previous-level name, used by `Player1` `from=` matching | 0x41b7c2 | no; `drunare`'s marker has no `from` |
| entrance name 0x4f8468, orientation byte 0x41b720 | globals | no; neither is used by this level's single marker |
| `drundar`'s object state | save buffer, level directory | written at step 8 on every machine |
| last checkpoint snapshot (a save point stands beside one of `drundar`'s arena doors) | save buffer | equal if taken in lockstep |
| script globals, deferred calls, save inhibit, recall countdown | cleared at teardown | — |
| pending post action | 0x86fa80, survives teardown | none set by `drundar` |
| prediction rebase clock, forced-rebase count | 0x4027d4, 0x402797 | yes, by design |
| local camera mode and state | camera object | yes, by design |
| card latch, card state | 0x4f8f28, 0x88d3a0 | yes |

Doors, the `safety` door state and the hidden monsters are not carried: they are built from
the level file on a first entry and set by `start`. They are restored from the buffer only
on a re-entry (section 4).

## Findings, each with its chain

### E8. The entry autosave is gated by local state

- **Chain (Observed):** armed at the end of every load (0x217f58). `save_daemonRun` fires
  it on the first tick where this machine's card state is idle (0x218934), the save inhibit
  is clear, `g_menuOpenFlag` is clear (0x21897c), the local camera mode is 1 (0x218990) and
  the game is not paused; it calls `save_game(0, 1)` (0x2189cc), which rebuilds the player
  and quest-variable sections of this machine's buffer and zeroes the ticks-since-save
  counter.
- **In this level:** the gate is open at F0 on a machine with nothing open. If it is shut
  until tick S on some machine, that machine never takes the snapshot: the camera mode is 0
  for the cutscene and `nosave` sets the inhibit in tick E. Its buffer then still describes
  `drundar`.
- **What shuts it at F0:** nothing in an ordinary entry. `newWorld` closed the menus in
  tick N; the save screen closes itself when a net level change is pending and the main
  loop waits for the write flag (step 5); the HUD task that could reopen a menu runs after
  the daemon. This agrees with docs/issues/sync-breakers.md section 1, which lists the
  residual cases.
- **Weakest link:** whether any card screen can be left in a state other than idle across
  a load (card error states were not followed).
- **If it were the cause:** nothing shows until the party is wiped. After the reload the
  two machines stand in different levels or at different positions, and the first hash
  after the reload differs.
- **Two-machine test:** after F0 compare the level name at the head of the save buffer
  (0x895580) and 0x88d40c on both machines.
- **Patch:** X3.

### E6. First prediction copy on a per-machine tick; copy not frozen with the player

- **Chain:** sections 2 and 3.4. **Observed** mechanism.
- **Weakest link:** the claim that the un-frozen copy cannot reach shared state rests on
  the G-series audit of `Player_run` for the copy; it was not repeated with a cutscene
  active.
- **If it were the cause:** the mismatch would come within 30 ticks after S or after E, on
  one machine, and would change with X1.
- **Two-machine test:** note `g_ghost` (0x4027bc) and 0x4027d4 on both machines at S.
- **Patch:** X1 removes the copy altogether.

### E9. A notice box runs the pending post-action script from the draw pass

- **Chain (Observed):** `help_task` 0x1dcc78 is a draw task. With no full-screen help box
  open it walks the slots; for a slot whose notice flag `g_playerNoticeOpen` is set it
  draws the box, and when that slot's pad shows the confirm button pressed after a release
  it sets the input lockout, clears the flag and calls `script_runPostAction`
  (0x1dd1e8–0x1dd1f4). There is no test of the network flag on this path. The other path
  in the same function, closing the full-screen help box, tests it and skips the call in a
  net game (0x1dcf58).
- Notice flags are set only for a local slot (`hud_showPlayerNotice` 0x1d9954). Its twelve
  call sites are in the item-list and workshop input, the skills screen, and in three
  places that run inside a tick: `Player_usePotion` (the first drink of a kind above 1
  while the first-drink quest variable is 0, call 0x1b9dd8; the variable is zeroed again
  at every act change), `inventory_equipItem` (handler of inventory message 1: an item the
  character cannot wield, call 0x1c28f8) and `inventory_combineGems` (message 8, call
  0x1cf79c). So notices are ordinary events, and each appears on its owner's machine
  only.
- **Consequence (Inferred):** while a post action is pending, the machine whose player
  closes a notice runs that script early, outside the lockstep, and the buffer is then
  empty on that machine when the others run it.
- **In this level:** pending from S to E (`nosave`) and for the whole of `bossdefeated`
  (`levelChange`). `cut_start` clears every notice flag in tick S, the menus that raise
  notices cannot be opened during a cutscene, and a frozen player's potion press is not
  processed. What remains is a notice raised by a game message that was already queued
  when the cutscene started (an equip or item action sent from an inventory that
  `cut_start` then closed). For `nosave` the early run changes nothing that is read before
  E. For `levelChange` it would send one machine to the next level alone.
- **Weakest link:** whether an equip or combine message can still be in flight when a
  cutscene starts (it needs a button press in an inventory during the last `lead` frames
  before tick S), and whether the item list sends the equip message for an item its own
  checks would refuse (the list code was not read).
- **Elsewhere:** in a net game the help box does not run the post action, so a script that
  pairs `addHelpMessage` with `postAction` (five entry points in the shipped scripts)
  leaves it pending until the next cutscene, dialog or level load; any notice closed in
  that time runs it on one machine.
- **Two-machine test:** watch 0x86fa80 (post-action name, empty when none) on both
  machines during the cutscene.
- **Patch:** X4.

### E11. The boss-meter bit is per machine

- **Chain (Observed):** `Creature_run`, for a creature with the boss bit (creature flag
  bit 0) and inert byte 0, looks for a *local* alive player within +0x3c0
  (`g_localAliveCount`, `g_localAlivePlayers`) and sets or clears bit 31 of the creature
  flag word +0xa8 and the meter globals 0x41b6a0 / 0x41b6a4 (0x113960–0x113ad8).
  `nosave` gives the avatar the boss bit.
- Readers of bit 31: the same block and `script_applyCFlag` (search of every decompiled
  function for a test or store of that bit at +0xa8). The flag word is written into the
  level's saved state.
- **Verdict:** a per-machine bit in a shared word with no simulation reader. Listed so
  that nobody compares flag words between machines and takes it for the divergence.

### E12. Camera reset at the level change

Correction 1 below. Closed for net games.

### E14. Load barrier and kick

Section 1.3. A drop, not a desync.

### E15. Pending character selection applied at level entry

- **Chain (Observed):** 0x2247ec, called at 0x321024 on every level entry: if 0x4fbbd8 is
  set, `player_initNewCharacter` for each slot with a stored choice (which gives starting
  items, so shared draws), then the flag is cleared.
- **Unknown:** whether the lobby's character creation can leave the flag set on one
  machine at launch. If it can, that machine rewrites a transferred record during the
  first load of the session; the effect would show on the first tick of the first level,
  not at the arena.

## Ranked list for this phase

1. **Nothing level-specific found.** With two living players and no menu, the phase is
   lockstep from tick N to tick E as far as it was read.
2. **E9** (post action from the draw pass). Real mechanism, new; in this level it needs a
   notice raised during a cutscene, and only the last cutscene's post action is harmful.
3. **E8** (autosave gate). Real mechanism, known; shows only after a party wipe, and needs
   a card screen or menu surviving the load.
4. **E6** (copy timing and freeze). Per machine by design; no route found.
5. **E11, E12, E14, E15.** Closed, or not specific to this level.

If the arena does go out of sync on every run, the recording below decides between "before
S", "during the cutscene" and "after E" in one run; the second and third then have a
one-word patch that removes the whole phase.

## What to record on two machines

Marks: **P** = first frame on which 0x41b6d0 is non-empty in `drundar`; **F0** = P + 1;
**S** = first frame with 0x44fcd0 set; **E** = first frame after S with it clear;
**M** = frame of the first sync mismatch (out-of-sync byte, peer +0x44d7).

| Read | Address | Expect | If not |
|---|---|---|---|
| `g_netFrame` at P | 0x4027ac | equal | the trigger or the gate ran on different frames: divergence is older than the door |
| `g_randSeed` at the barrier, before F0 | 0x404464 | equal | the load drew differently: compare the three below |
| spawn positions, facings, start rank | 0x4f70d0 (4 × 3 floats), 0x4f8410 (4 × s16), 0x4f7108 | equal | `Player1` or the free-spot loops; check the door objects and 0x8e1ad6 |
| creature serial counter after the load | 0x4f85c4 | equal | a machine built a different object list: look at `g_saveLevelDir` 0x8ab590 |
| quest variable bytes for `sawknights`, `killedav` | list at 0x86da80 | 0, 0 on a first visit | section 4 |
| save-buffer level name and autosave countdown after F0 | 0x895580, 0x88d40c | `drunare`, 0 | E8 |
| card state, card latch | 0x88d3a0, 0x4f8f28 | −1, 0 | E8; sync-breakers N1 |
| `g_ghost`, rebase clock at S | 0x4027bc, 0x4027d4 | differ freely | E6 only if M follows within 30 ticks |
| S and S mod 15 | 0x4027ac | equal, 2 | player positions already differed |
| hash of every frame from S+1 to E | local sync ring, peer +0x18ac | **constant** | a seed draw or a moving player inside the cutscene; compare player positions and inert bytes (+0x231 = 4) |
| post-action name during the cutscene | 0x86fa80 | `nosave` until E | E9 |
| E − S | | equal, about 1,270 unless skipped | the key lists ran differently |
| run-list cursors at E | 0x4039fc, 0x403a00 | equal | activity was judged from different centres during the cutscene (D6) |

Reading of M: M ≤ F0 + 1 → the load. F0 < M < S → ordinary play, not this level. S < M ≤ E
→ inside the cutscene, where the hash should be constant. M > E → the fight
(arena-desync.md).

## Proposed ledger rows

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| E1 | A script level change stops every machine after the same frame: the name is written inside a tick, later steps test it first, and the first frame of the new level is the next frame number. No message is involved | Observed | 0x143dd0, 0x1472c4, 0x139fb4 |
| E2 | Between that frame and the next, every shared-seed draw is made by object constructors, `Player1_ctor` and two free-spot loops; no input of those is per machine on a first visit | Inferred from Observed steps | 0x14cd54, 0x158928, 0x3212e0; section 1.4 |
| E3 | `Player1_ctor` fills four spawn slots with a free spot within 36 units of the best start marker and a facing within ± 2000; the session code moves slots 1–3 again by up to 36 and creates the players in slot order | Observed | 0x158928; 0x321294–0x321414 |
| E4 | In `drunare` no start can lie inside either trigger rectangle; the opening cutscene starts on a frame with remainder 2 modulo 15, after a player has walked at least 77 units | Observed (data), Inferred (remainder) | `objects.ob`; 0x1ecdf4, 0x14f330 |
| E5 | `cut_start` restarts the per-machine frame warm-up counter inside a tick, and `cut_runFrame` does so again at the end; no reader of the counter inside a net tick changes shared state. `cut_evalCamera` keeps one latch and is otherwise a function of the clock | Observed | 0x19b514, 0x199f44; `gxref` 0x506048; 0x44fd00 |
| E6 | After a level load the first prediction copy is made 1–31 ticks in, on a per-machine tick. The copy is on no run list, so a flag-8 cutscene neither freezes nor unfreezes it; clones made during the cutscene inherit the freeze and keep it up to 30 ticks after the end | Observed | 0x13dcd0, 0x13b1e8; 0x14a7c8; 0x1a55a0 |
| E7 | In a net game players ignore damage for 30 of their own run ticks after every level load and 60 after every cutscene | Observed | 0x1e61c0, 0x1bfaf8, 0x1a5330, 0x1b5438 |
| E8 | In this level a machine whose autosave gate is shut from the first tick to the cutscene start never takes the entry snapshot (the cutscene holds the camera mode and its post action sets the save inhibit) | Inferred from Observed pieces | 0x2188a8; scripts/DRUNARE.txt |
| E9 | Closing a per-player notice box calls `script_runPostAction` from a draw task with no network test; the full-screen help box's path has the test | Observed | 0x1dd1f0; 0x1dcf58 |
| E10 | The post-action name is not cleared by level teardown; `game_loadLevel` runs a left-over one in the new level's script | Observed | 0x1e60b8; writers of 0x86fa80 |
| E11 | Bit 31 of the creature flag word and the boss-meter globals are set from the local alive list; nothing else reads the bit | Observed | 0x113960–0x113ad8 |
| E12 | The main loop resets the local camera at every level change unless the card latch is set; in a net game the transition flag is cleared by the first camera update of the load warm-up loop | Observed | 0x322dfc; 0x204fb0; 0x2065e8–0x2065f4 |
| E13 | In `knights` the sync hash cannot change between the tick after it starts and the tick it ends, apart from a stuck actor's teleport and the 1800-frame seed step of lobby games | Inferred | section 3.5 |
| E14 | After a load a machine waits for one packet from every peer for at most about 900 calls; a peer's silence counter keeps running meanwhile and starts a kick above 900. A much slower loader is dropped, not desynchronised | Observed (constants), Inferred (outcome) | 0x323014–0x32305c; 0x134408–0x134448; 0x133060 |
| E15 | Every level entry applies a pending character selection (flag 0x4fbbd8) by re-creating that slot's character; whether a net launch can start with the flag set on one machine is not established | Observed (code), Unknown (reachability) | 0x321024; 0x2247ec |

## Test patches (all untested)

One change each. PCSX2 form: `patch=1,EE,<address>,word,<new>`. Original words were read
from the executable.

| # | Address | Original | New | What it changes | What could go wrong | Every player? |
|---|---|---|---|---|---|---|
| X1 | 0x0013b21c | 106000df | 100000df | The "local player has an object" branch in front of the rebase is taken always: no prediction copy is ever made. The local character is then drawn from the real object, with the input delay visible | Must be active before the first level of a session (an existing copy would never be replaced). Own weapon trails disappear; draw code that uses the frame counter between ticks sees a stale value; controls feel late | No, it touches nothing shared; for a clean test, both |
| X2 | 0x00199df8 | 10400004 | 00000000 | The "start button pressed" branch of the cutscene skip test never branches away: every in-level cutscene is run to its end in the tick it starts (not `endgood` / `endbad` in a net game, which wait 300 ticks) | No cutscene is seen; voice lines are cut; a mix of patched and unpatched machines desyncs at the first cutscene | Yes |
| X3 | 0x00217f58 | 24030001 | 24030000 | `save_armAutosave` stores 0: no checkpoint autosave after a level load on this machine | After a party wipe the reload uses an older snapshot (the last save point or script checkpoint); with none in the buffer the behaviour was not traced | Yes, for a clean test |
| X4 | 0x001dd1f0 | 0c07b6b0 | 00000000 | The notice box no longer runs the post-action script | Offline, a post action that was meant to follow a notice would wait for the next cutscene, dialog or level load; no shipped use was identified, not checked | Per machine; a fix needs it on all |

How to use them: X2 first. If the arena still goes out of sync with X2 on both machines,
the opening cutscene's 1,270 ticks are not needed for it, and M relative to E says whether
the fight or the load is. Then X1: if the result does not change, the prediction copy is
not involved in any way. T5 of arena-desync.md (0x001e4dd4) remains the test for
camera-judged activity.

## Corrections to earlier documents

1. docs/issues/arena-desync.md, "Camera-driven activity": the callers of `Camera_reset`
   are listed as player respawn, loading a camera state, a spectator-slot change and
   session start. The main loop also calls it at **every level change** (0x322dfc), and the
   "session start" caller is `Camera_init`. The conclusion stands in a net game:
   `Camera_computeTarget` can only fail offline (0x2065e8–0x2065f4), so the first
   `Camera_update` of the load warm-up loop reaches the end of the follow routine and
   clears the flag (0x204fb0) before any tick.
2. docs/issues/prediction-copy.md 3.1, scripted walk: "the freeze callback skips players"
   holds for `creatures_freezeAll` only. With header flag 8 the real players get inert
   bit 4 and a copy cloned from them inherits it. The row's conclusion stands for a
   different reason: the walk also needs action state +0x58c = 1 (0x1a55ac–0x1a5604).
3. docs/mainloop.md P9: "`cut_setup` runs in the first pass on every machine" applies only
   to a cutscene started during the load. The Unknown about `cut_evalCamera` is answered in
   section 3.2.
4. docs/script.md 2.5 lists two calls of `script_runPostAction` in `help_task` without
   saying that it is a draw task, that one call is offline-only and that the other has no
   network test (E9). Section 2.4 says the deferred queue is cleared at teardown; the post
   action is not (E10).
5. docs/audio-save.md: `save_armAutosave`'s test for card state 8, and the same value in
   the level-change code (0x322ddc) and in `game_loadPlayerLumps`, can never be true: no
   call of `memcard_setState` passes 8 (the 27 call sites were listed; the one wrapper that
   passes its argument through has no caller).
6. docs/mainloop.md section 7 step 6: the early return after `save_storeLevelState` cannot
   be taken; the function returns 0 on every path.

## Not done

- `Zek_ctor`, the light and settings records and `arena_init` / `arena_begin` were not
  scanned for the load. `game_clearLevel`'s callees were read by name only.
- The branches in front of the twelve calls of `hud_showPlayerNotice` were not read (E9).
- `playerSel_start` / `playerSel_finish` and the lobby character-creation path (E15).
- Card error sub-states of the save and config screens across a level load (E8).
- The player's run speed, so the number of ticks between F0 and S is only bounded below.
- The party-wipe reload (`deathTask`, `save_reload`) was followed only as far as needed to
  say what the entry snapshot is for.
- A re-entry of `drunare` with stored level state was reasoned about, not traced.
- Nothing here was run. Floating-point behaviour of different hosts (docs/netcode.md
  row 11; docs/issues/float-divergence.md, written in parallel) is outside this trace and
  is not excluded by it: every "equal" above assumes the machines compute the same bits.
