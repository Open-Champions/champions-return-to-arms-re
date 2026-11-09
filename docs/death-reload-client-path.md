# Death reload for a native client, without the original boot

Round 8, 2026-11-09, branch `t3/research-death-reload`. Executable SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
Re-pinned after audit R8 (round 9, 2026-11-09): [SW] is now `31a0ca6` and
[EX4]/[EX5] are `350fc8b`.

This note collects audited facts about what a death reload restores and in
what order. It answers one question: which steps can a native client do with
its own loader (it already passes `FULL_SAVE_LOAD`) without emulating the
original boot? It adds no new execution. Every statement carries a label and
cites the note that holds the evidence. Labels are the repository's:
**Observed** (addressed instructions), **Executed** (original functions run
in `tools/ee_emu.py` on synthetic input, as stated in the cited note),
**Inferred** (composed from those), **Unknown** (not established). Track A
of round 8
([death-reload-sequence.md](death-reload-sequence.md#round-8-the-sif-wall-2026-11-09))
is the original boot. Nothing here depends on it.

Citation keys:

- **[R2]** this branch at `9a34671`, `docs/death-reload.md` lines 40-91, and
  `docs/death-reload-sequence.md` lines 15-100 (round 2).
- **[SW]** `t3/research-save-world` at `31a0ca6`, `docs/save-world.md` lines
  13-109 and 241-316.
- **[SS]** `t3/research-save-screen` at `c8895e2`, `docs/save-screen.md` lines
  181-325.
- **[EX4]** `t3/research-exits-r3` at `350fc8b`, `docs/exits-r4-travel.md`
  lines 25-126. The death-task +0x24 oracle was added in `5f1814e`, an
  ancestor of `350fc8b`.
- **[EX5]** `t3/research-exits-r3` at `350fc8b`, `docs/exits-r5-travel.md`
  lines 110-160 and 273-330.
- **[M2]** `t3/research-mission2-route` at `d17b46f`, `docs/mission2-round4.md`
  lines 62-67.

## 1. What the checkpoint holds, and what a death reload reads

- **Observed** [SW 15-26, 273-274]: the save buffer `g_saveBuffer` 0x895580 is
  0x4bc78 bytes. `save_build` 0x221914 fills its header, players and quests,
  and stores the current level into a ten-entry level directory at +0x16010
  (0x8ab590) with bodies at +0x16118. `save_storeLevelState` 0x21777c also
  stores the old level into the same directory before a normal transition
  (`mainloop_loadRequestedWorld` 0x320edc).
- **Observed** [SW 54-72]: a level body is the world record blob, the decal
  blob and 0x16c8 bytes of explored automap. It is a bounded snapshot of
  surviving eligible objects, not geometry and not an event log.
- **Executed** [SW 241-267]: `save_game` 0x218128 does not always build a
  checkpoint. With no counted living player it does nothing. When no act row
  is a prefix of the level name it shows the `CheckPoint` text and returns
  without building, so that level's state is not stored either. This holds
  for a1 = 0 and for the daemon's `save_game(0, 1)`.
- **Observed** [SW 269-275], citing `t3/research-saves` `8d43286`: when the
  game is complete, `save_build` skips `save_findAct` and the level store, so
  that checkpoint adds no body for its own level.
- **Inferred** [SW 285-303]: the memory image a death reload reads is the
  live `g_saveBuffer`, not a frozen copy taken at the checkpoint. Departure
  stores after the checkpoint write into the same buffer and are not undone.
  A death reload therefore restores the checkpoint's header (players,
  quests, spawn and level) together with each level's *latest* stored body.
  A level left after the checkpoint comes back in its departure state. The
  level being played when the party died comes back in its last stored
  state, because the death skips its store (step 6). There are three
  exceptions, each **Inferred** there:
  - **An act change after the checkpoint.** The clear block runs
    `save_clearBuffer(0)` 0x21f144 on that same buffer (**Observed /
    Executed** [EX4 69-80]). Only slot 0 survives. The checkpoint level
    (unless it is slot 0) and the old act's other levels come back fresh,
    not in their latest stored state.
  - **A completed game.** `save_build` skips the level store, so the
    checkpoint adds no body for its own level. That level's body is
    whatever the directory already held.
  - **The gap slot.** Once slot 10, the 0x18-byte gap at +0x16100, has been
    written, a level that misses comes back with the gap body (step 9).
- **Observed / Executed** [R2 53-72]: on the reload path, the whole
  0x4c30-byte player record comes back from the checkpoint header, except
  the documented +0x43d8 clear. Gold, XP, bags and equipment therefore roll
  back to their values at the checkpoint. **Unknown:** whether there is a
  separate death fee; [R2 71-72] establishes none. The probe used an
  empty-inventory record. **Unknown:** item fixup with populated bags.

## 2. Ordered sequence

| # | Step | Label and evidence |
|---|---|---|
| 1 | Lethal damage zeroes HP. Object flags `0x109`, state 4, death animation. | **Observed / Executed** [R2 seq. 31-36]: `Player_processDamage` 0x1b2cc0. |
| 2 | 240 frames of party countdown. On frame 240 `deathTask` 0x1e75e8 is registered at priority 20, and the fade is cleared. | **Observed / Executed** [R2 seq. 37-42]; [R2 41-50]. The scheduler timing is **Unknown**. |
| 3 | 32 frames of fade, +4 each, to 128. Then phase 1. | **Observed / Executed** [R2 seq. 43-48]. The packets are built. A visible fade is **Unknown** (not shown). |
| 4 | No menu and no choice. The alternate-death flag 0x4f712c sends the task to phase 10, a separate script path. | **Observed** [R2 74-76]. The script's revival is **Unknown**. |
| 5 | `save_findAct` 0x217d30 on the checkpoint's level. If found: `save_reload` 0x22266c, then `save_load` 0x221d60 on the live `g_saveBuffer` (section 1). No card is read. | **Observed / Executed** [R2 53-61]; [R2 seq. 49-55]. "Live buffer" is the section-1 **Inferred** statement. |
| 5a | `save_load` restores the player record, pose and facing, player count, camera, jump-gate destinations, quest variables, act, difficulty and time. It clears deferred script calls at 0x1eda08 and sets the loaded byte 0x8e1ad6. It requests the saved level with marker 253 (0xfd). Then phase 2. | **Observed** [SW 76-80]. **Executed** [R2 seq. 57-67] for an empty quest list and one camera, with the camera, destination, fixup, deferred, variable and act callees run unstubbed. |
| 5b | If not found: request the current level with marker 253, set HP to max HP, remove the task. Every other record byte keeps its current value. No rollback. | **Observed / Executed** [R2 62-68]. |
| 6 | `mainloop_loadRequestedWorld` 0x320edc does not store the dying world while the death task runs (`task_isRunning` 0x19e5e8 at `0x320f28`, after the empty-name test at `0x320f1c`), so that level's last stored body survives. | **Observed / Executed** [R2 82-86]; [R2 seq. 71-78], with a no-task control that does reach the store; [EX4 56-58]. |
| 6a | While the death task runs, the act-change clear block `0x320fa8`-`0x321020` is skipped. That block would run `save_clearBuffer(0)` 0x21f144, reset jump gates (0x27db00), clear quests (0x1d3adc), remove flag-39 items (0x1be1d8) and zero variables (0x1ed728). The act index is still updated. | **Observed / Executed** [EX4 67-80], with the four world calls supplied. It comes before step 7. |
| 7 | The loader writes the previous name at 0x41b7c2, splits the request into base 0x41b721 and subname 0x41b771, clears the pending name, saves the marker at 0x41b7c1 and replaces it with 0xfe (254) at `0x321118`-`0x321128`, then calls `game_loadLevel` 0x1e55c0 with the base. | **Observed / Executed** [EX4 84-91], callees supplied; [R2 seq. 80-83]. |
| 8 | The target `.GOB` and `.world` are loaded anew. Geometry, terrain, moving pieces, water and paths come from level data, not from the save. | **Observed** [SW 82-86]. |
| 9 | `level_loadScriptAndObjects` 0x217978: level lump, a fresh script machine, `preStart`. The directory search compares names in slots 0..9 only (loop `0x2179c0`-`0x2179f4`). The restore test at 0x217a18 reads the first name byte of the slot where the search stopped. On a hit that is the matching slot. After ten misses it is gap slot 10: if slot 10 has a name, the gap body is restored for that level, whatever its name; if it is empty, the level loads fresh. With the flag set: copy the world and decal blobs, unpack the explored map, `world_loadRecords(blob, 0)`, load decals. Then `objects.ob` with `filterOnly` = the flag. Then `start`. | **Observed / Executed** [SW 44-52] (round 4 `check_travel`); **Executed** [EX5 279-281, 320-326] (the eleventh row restored for a key absent from the first ten). **Observed** [SW 88-99]; **Executed** [SW 94-99] on 32 synthetic cases per seed (call order, record selection, scratch bytes). Whether retail play reaches 11 keys in one act is **Unknown** [EX5 328-330]. |
| 9a | On a restored level the `objects.ob` pass constructs only classes `world_saveFilter` 0x15d9c8 accepts, so killed creatures and opened chests do not respawn. | **Observed** [SW 101-109]. "Absent records stay absent" is **Inferred** there. |
| 10 | Placement, still inside 0x320edc. The loaded byte makes `level_loadScriptAndObjects` set rank byte 0x4f7108 to 3 (`0x217a90`-`0x217ab0`). At rank 3 every `Player1` arrival marker is skipped, so the saved poses are not replaced. At rank 3 the free-spot search `world_findFreeSpot` 0x14acf8 in placement is skipped too. Terrain height 0x183820 sets z. A player object is built (0x14fdb8, 0x1a1d28) only for a slot whose record HP at +0xac is above 0, whose peer test 0x13dd40 is true, and, when 0x4f713c is set, which 0x1ec5a8 reports as the medal slot 0x4f7148. On an act change the record +0x24 write is skipped while the death task runs. | Rank: **Executed** [EX5 112-117]. Marker skip: **Executed** [EX5 124]. Free-spot skip at rank 3: **Observed / Executed** [EX4 100-104]. That both skips apply on a death reload is **Inferred** from step 5a setting the loaded byte. HP, peer and medal gates: **Observed / Executed** [EX4 107-117], with terrain, allocation, peer test and constructor supplied. +0x24 skip: **Observed / Executed** [EX4 118-121] (round five, oracle in `5f1814e`), state function supplied. |
| 11 | Phase 2 removes the task once the pending request is empty and the qualified names match. | **Observed** [R2 76-79]. **Executed** as separate controls [R2 seq. 90-96]. |

## 3. A card load reaches the same loader

- **Observed / Executed** [SS 258-279]: a card load copies 0x4bc78 bytes into
  `g_saveBuffer` and calls the same `save_load` (when 0x8e1ab9 is set). That
  replaces the whole buffer, directory included, with the card image. The
  marker becomes 0xfd and the loaded flag 1. `save_load` does not read the
  level directory. `level_loadScriptAndObjects` later does that
  (**Observed** [SS 288-291]).
- **Observed / Executed** [EX4 27-29]: `save_storeLevelState` does nothing
  while the card word 0x88d3a0 is 4. **Executed** [SS 281-287]: the load
  screen keeps state 4 until the live level name matches. **Observed /
  Executed** [EX4 69-70]: the act-clear block also needs the card latch
  0x4f8f28 clear, and **Executed** [SS 261-262]: the load path sets the latch
  at 0x2195a8.
- **Inferred:** the departure store and the act clear are suppressed in both
  paths: by the death task in a death reload, and by card state 4 and the
  latch in a card load. After `save_load`, both requests go through the same
  `0x320edc` and `level_loadScriptAndObjects` order. The differences, each
  **Inferred** from the cited evidence:
  - **The buffer.** A card load restores the card image, header and
    directory together. A death reload feeds `save_load` the live
    `g_saveBuffer`: the checkpoint header, with each level's latest stored
    body as later departure stores and act-change clears left it (section
    1, [SW 285-301]).
  - The not-found branch 5b, which exists only for death.
  - The task that waits for the name match: `deathTask` phase 2, or load
    step 5.
  - The record +0x24 write: skipped by the death task, and in a card load by
    card state 4 (**Observed / Executed** [EX4 118-121]).

## 4. What the client can do with its own loader

**Can do, from the evidence above.** Each item rests on the Observed or
Executed contracts cited in its step. The convergence with the card load
(section 3) and the live-buffer reading (section 1) are **Inferred**.

1. Keep the save buffer live, as `g_saveBuffer` is. The checkpoint builds
   its header and current-level body into it. Later departure stores and
   act-change clears keep writing into it, and a death reload reads it as
   they left it. Do not snapshot it at the checkpoint. On death, do not
   store the dying level into it (step 6). Build no checkpoint where
   `save_game` builds none, and store no body for the current level after a
   completed game (section 1).
2. Run the countdown and fade (steps 2-3) with no menu (step 4).
3. Look the level up in the act table. If found, feed the live buffer to
   the same `save_load` equivalent that `FULL_SAVE_LOAD` uses for a card
   image: record, pose, camera, destinations, quests, act, time, and the
   loaded flag (step 5a). If not found, reload the current level and only
   refill HP (step 5b).
4. Issue the level request with the 0xfd marker. While the death is
   pending, skip the departure store and the act clear (steps 6-6a).
5. Load the level with the client's own GOB/world loader, then apply the
   stored body in the step 9 order. Decide restore with the stopped-slot
   rule of step 9, not with a name match alone. Choose and document a
   gap-slot policy ([SW 314-316]: copy the original, where every miss after
   ten keys restores slot 10, or refuse it); do not present slot 10 as an
   eleventh saved level. Use the step 9a filter for `objects.ob`.
6. Spawn at the saved poses at rank 3 (no marker ranking, no free-spot
   search), at terrain height, building only players that pass the HP,
   peer and medal-slot gates (step 10). Finish when the names match (step
   11).

**Inferred**, and limited to a client that has its own loader: none of
these steps needs that client to emulate SIF, the IOP, CDVD RPCs or
`engine_init`. This is not a statement about the original. Original level
loads do reach SIF: with `game_clearLevel` and `mem_free` stubbed, the
mission-2 round-4 loader stops at `sceSifSetDma` 0x352da0, called from
0x35edd0 (**Observed / Executed** [M2 62-67]).

**Unknown, so the client must not fabricate them:**

- Per-class load effects when saved records are reconstructed. These are the
  save-world unknowns. [R2] executed only selected Creature, Chest, door,
  JumpGate, ItemProp and Trigger cases.
- Item fixup with populated bags. Camera presentation. What the destination
  payload means.
- `game_loadLevel` as a whole on the original. In emulation it still stops
  in teardown, before reconstruction. The loading screen. What the
  free-spot search reads from geometry or `g_randSeed` when it does run (it
  does not at rank 3, step 10) [EX4 105-106].
- Whether retail play reaches an eleventh directory key in one act
  [EX5 328-330].
- Behaviour with an invalid or uninitialised checkpoint. Scheduler timing.
  Rendered overlays. The alternate-death script.
- A continuous death-to-playable run. No such run exists in any branch.

The native `blocked_death_reload` gate is in the client repository and is not
changed here. **Inferred** (section 3, composed from separate probes): a
client death reload is a card-load equivalent fed from the live save buffer,
not from a frozen checkpoint image. It restores the checkpoint header with
each level's latest stored body, subject to the act-change, completed-game
and gap-slot exceptions in section 1, and it refuses the per-class effects
marked Unknown. Whether to lift the gate on that basis is the client owners'
decision.
