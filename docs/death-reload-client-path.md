# Death reload for a native client, without the original boot

Round 8, 2026-11-09, branch `t3/research-death-reload`. Executable SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.

This note collects audited facts about what a death reload restores and in
what order. It answers one question: which steps can a native client do with
its own loader (it already passes `FULL_SAVE_LOAD`) without emulating the
original boot? It adds no new execution. Every line cites the note that holds
the evidence. Labels are the repository's: **Observed** (addressed
instructions), **Executed** (original functions run in `tools/ee_emu.py` on
synthetic input, as stated in the cited note), **Inferred** (composed from
those), **Unknown** (not established). Track A of round 8
([death-reload-sequence.md](death-reload-sequence.md#round-8-the-sif-wall-2026-11-09))
is the original boot. Nothing here depends on it.

Citation keys:

- **[R2]** this branch at `9a34671`, `docs/death-reload.md` lines 40-91, and
  `docs/death-reload-sequence.md` lines 15-100 (round 2).
- **[SW]** `t3/research-save-world` at `e7d8972`, `docs/save-world.md` lines
  13-102.
- **[SS]** `t3/research-save-screen` at `c8895e2`, `docs/save-screen.md` lines
  181-325.
- **[EX]** `t3/research-exits-r3` at `e86f3de`, `docs/exits-r4-travel.md`
  lines 24-125.

## 1. What the checkpoint holds

- **Observed** [SW 13-24]: the checkpoint is the 0x4bc78-byte save buffer
  that `save_build` 0x221914 fills: header, players, quests, and a ten-entry
  level directory at +0x16010 with bodies at +0x16118. The current level is
  stored into it when a checkpoint is built.
- **Observed** [SW 47-64]: a level body is the world record blob, the decal
  blob and 0x16c8 bytes of explored automap. It is a bounded snapshot of
  surviving eligible objects, not geometry and not an event log.
- **Observed / Executed** [R2 53-72]: on the reload path, the whole 0x4c30-byte
  player record comes back from the checkpoint, except the documented +0x43d8
  clear. Gold, XP, bags and equipment therefore roll back to their values at
  the checkpoint. There is no separate death fee. The probe used an
  empty-inventory record. Item fixup with populated bags is **Unknown**.

## 2. Ordered sequence

| # | Step | Label and evidence |
|---|---|---|
| 1 | Lethal damage zeroes HP. Object flags `0x109`, state 4, death animation. | **Observed / Executed** [R2 seq. 31-36]: `Player_processDamage` 0x1b2cc0. |
| 2 | 240 frames of party countdown. On frame 240 `deathTask` 0x1e75e8 is registered at priority 20, and the fade is cleared. | **Observed / Executed** [R2 seq. 37-42]; [R2 41-50]. The scheduler timing is **Unknown**. |
| 3 | 32 frames of fade, +4 each, to 128. Then phase 1. | **Observed / Executed** [R2 seq. 43-48]. The packets are built. A visible fade is not shown. |
| 4 | No menu and no choice. The alternate-death flag 0x4f712c sends the task to phase 10, a separate script path. | **Observed** [R2 74-76]. The script's revival is **Unknown**. |
| 5 | `save_findAct` 0x217d30 on the checkpoint's level. If found: `save_reload` 0x22266c, then `save_load` 0x221d60 on the buffer already in memory. No card is read. | **Observed / Executed** [R2 53-61]; [R2 seq. 49-55]. |
| 5a | `save_load` restores the player record, pose and facing, player count, camera, jump-gate destinations, quest variables, act, difficulty and time. It clears deferred script calls and sets the loaded byte 0x8e1ad6. It requests the saved level with marker 253 (0xfd). Then phase 2. | **Observed** [SW 69-73]. **Executed** [R2 seq. 57-67] for an empty quest list and one camera, with the camera, destination, fixup, deferred, variable and act callees run unstubbed. |
| 5b | If not found: request the current level with marker 253, set HP to max HP, remove the task. Every other record byte keeps its current value. No rollback. | **Observed / Executed** [R2 62-68]. |
| 6 | `mainloop_loadRequestedWorld` 0x320edc does not store the dying world while the death task runs, so the checkpoint body survives. | **Observed / Executed** [R2 82-86]; [R2 seq. 71-78], with a no-task control that does reach the store. |
| 7 | The loader writes the previous name, splits the request into base and subname, clears the pending name, saves the marker and replaces it with 0xfe (254), then calls `game_loadLevel` 0x1e55c0 with the base. | **Observed / Executed** [EX 78-87], callees supplied; [R2 seq. 80-83]. |
| 7a | While the death task runs, the act-change clear block is skipped. That block would clear the save buffer, reset jump gates, clear quests, remove flag-39 items and zero variables. The record +0x24 write is also skipped. | **Observed / Executed** [EX 67-76, 106-109], with supplied world calls. |
| 8 | The target `.GOB` and `.world` are loaded anew. Geometry, terrain, moving pieces, water and paths come from level data, not from the save. | **Observed** [SW 75-79]. |
| 9 | `level_loadScriptAndObjects` 0x217978: level lump, a fresh script machine, `preStart`. With a matching directory entry: copy the world and decal blobs, unpack the explored map, `world_loadRecords(blob, 0)`, load decals, then `objects.ob` with `filterOnly=1`. Then `start`. | **Observed** [SW 81-92]. **Executed** [SW 86-91] on 32 synthetic cases per seed (call order, record selection, scratch bytes). |
| 9a | On a saved level the `objects.ob` pass constructs only classes `world_saveFilter` 0x15d9c8 accepts, so killed creatures and opened chests do not respawn. | **Observed** [SW 94-102]. "Absent records stay absent" is **Inferred** there. |
| 10 | Spawn: the loaded byte suppresses start-marker replacement of the saved poses. Terrain height sets z. The player object is built only for a slot whose record HP is above 0. | **Observed** [SW 72-73]. **Observed / Executed** [EX 88-105], with terrain, free spot and constructor supplied. |
| 11 | Phase 2 removes the task once the pending request is empty and the qualified names match. | **Observed** [R2 76-79]. **Executed** as separate controls [R2 seq. 90-96]. |

## 3. A card load reaches the same loader

- **Observed / Executed** [SS 258-279]: a card load copies 0x4bc78 bytes into
  `g_saveBuffer` and calls the same `save_load` (when 0x8e1ab9 is set). The
  marker becomes 0xfd and the loaded flag 1. It does not read the level
  directory. `level_loadScriptAndObjects` later does that [SS 288-291].
- **Observed** [EX 28-29]: `save_storeLevelState` does nothing while the card
  state is 4. [SS 281-287] shows that the load screen keeps state 4 until the
  live level name matches. The act-clear block also needs the card latch
  clear [EX 67], and the load path sets the latch at 0x2195a8 [SS 261-262].
- **Inferred:** the departure store and the act clear are suppressed in both
  paths: by the death task in a death reload, and by card state 4 and the
  latch in a card load. After `save_load`, both requests go through the same
  `0x320edc` and `level_loadScriptAndObjects` order. The differences:
  - The source of the buffer: in memory for death, the card for a load.
  - The not-found branch 5b, which exists only for death.
  - The task that waits for the name match: `deathTask` phase 2, or load
    step 5.
  - The record +0x24 write: skipped by the death task, and in a card load by
    card state 4 [EX 108].

## 4. What the client can do with its own loader

**Can do, from the evidence above (Observed or Executed contracts; the
convergence in section 3 is Inferred):**

1. Keep the checkpoint image in memory when it is built. On death, never
   store the dying level into it (step 6).
2. Run the countdown and fade (steps 2-3) with no menu (step 4).
3. Look the level up in the act table. If found, feed the in-memory image
   to the same `save_load` equivalent that `FULL_SAVE_LOAD` uses for a card
   image: record, pose, camera, destinations, quests, act, time, and the
   loaded flag (step 5a). If not found, reload the current level and only
   refill HP (step 5b).
4. Issue the level request with the 0xfd marker. Skip the act clear and the
   departure store while the death is pending (steps 7-7a).
5. Load the level with the client's own GOB/world loader, then apply the
   saved directory body in the step 9 order. Use the step 9a filter for
   `objects.ob`.
6. Spawn at the saved poses, at terrain height, building only players with
   HP above 0 (step 10). Finish when the names match (step 11).

None of this needs SIF, IOP, CDVD RPCs or `engine_init`. Those belong to
the original boot, which happens once before any death.

**Unknown, so the client must not fabricate them:**

- Per-class load effects when saved records are reconstructed. These are the
  save-world unknowns. [R2] executed only selected Creature, Chest, door,
  JumpGate, ItemProp and Trigger cases.
- Item fixup with populated bags. Camera presentation. What the destination
  payload means.
- `game_loadLevel` as a whole on the original. In emulation it still stops
  in teardown, before reconstruction. The free-spot search and its seed use.
  The loading screen.
- Behaviour with an invalid or uninitialised checkpoint. Scheduler timing.
  Rendered overlays. The alternate-death script.
- A continuous death-to-playable run. No such run exists in any branch.

The native `blocked_death_reload` gate is in the client repository and is not
changed here. On this evidence, a client death reload is a card-load
equivalent fed from memory, refusing the per-class effects marked Unknown.
Whether to lift the gate on that basis is the client owners' decision.
