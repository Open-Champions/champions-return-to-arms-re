# Main loop and task scheduler (`core.cc`)

Area `mainloop`, nominal range 0x320000–0x323dcc of `SLUS_209.73` (see
[OVERVIEW.md](OVERVIEW.md)). Everything here was read from the executable; nothing was
run when it was written. Since then the project has a live game — in the Play! emulator,
which is not a PlayStation 2 and not PCSX2 — and what was run on it is listed in
`FINDINGS.md`, "Run on the live game" (rows V1–V13) and `docs/issues/live-rig.md`. Of this
document that touches: `tasks_run` entered once per simulated frame, the two frame
counters (`g_drawFrame` up by one per rendered frame, `g_simFrame` reset at a level load),
and the developer LAN launch of section 7 step 3 (marked **Ran** there). Everything else here is still reading
only; no per-machine item below and the only test patches run on a live game are the two for K1 and K2 (FINDINGS V10, V11).
**Observed** = read at the address given, **Inferred** = follows from observations,
**Unknown** = not established. Names of functions outside this area are the ones other
area files in `symbols/` use; where none exists the address is given.

## 1. What is in this range, and where it really starts and ends

The nominal range cuts through two source modules. The real layout (Observed unless
marked):

| Addresses | Module | How we know |
|---|---|---|
| …–0x31d24f | last skill class (`SmokeGen`, constructor 0x31d180) | last functions that appear in a class virtual table are 0x31c898 and 0x31cbf8 |
| 0x31d2a0–0x31fdf3 | text chat, USB keyboard and voice comm. **Not skills.** Holds three task functions registered by this area: `textMessageProcess` 0x31dc80, `textMessageDraw` 0x31deec, `commProcess` 0x31fb30 | task names; 0x31fd38 registers two network handlers. It sits in the skills area's nominal range; only the task entry points were read here |
| 0x31fdf4–0x320ea3 | MPEG movie player (20 functions: one before 0x320000, 15 listed and 4 unlisted inside this area's range) | allocation tags and the decoder calls at 0x372948–0x373708; first function 0x31fdf4 builds the GS upload chain and is called only from `movie_update` |
| 0x320ea4–0x324287 | `core.cc`: UI ramps, level entry, boot screens, loading-screen thread, `tasks_run`, the session loop, modal loops, argument handling, and **`main` at 0x323dcc** | the stack-check calls pass the file name `core.cc` with rising line numbers: 346–430 in 0x320edc, 1916–2089 in 0x322998, 2765–3063 in 0x323dcc |
| 0x324288– | lobby client (`lobby_task`, registered under the task name `srs`) | netlib area |

So the module boundary at the top is 0x324288, not 0x323dcc: the function at 0x323dcc is
the program's `main(argc, argv)` (its only call site is in the C start-up code, 0x14fcb8) and
belongs to this module. It does not set the player-versus-player flags to anything but
zero (0x323f34–0x323f44); the setters are in the front end. `main` is described in
section 8 but is not named in `symbols/mainloop.tsv` because it is outside the range.

The Ghidra table has 39 functions in range; all 39 are named (two were already in
`names.tsv`). Seven more small functions exist in the range that the table does not
list and nothing references (dead code); they are named too and marked as such.

### Function map

| Address | Name | Role |
|---|---|---|
| 0x320038–0x32018c (7) | `movie_pack…` | pack DMA tags, GIF tags and four GS transfer registers |
| 0x3201b0 | `movie_startGifChain` | start DMA channel 2 on a tag chain |
| 0x3201ec † | `movie_waitForField` | busy-wait on the vblank counter |
| 0x320238 | `movie_feedStream` | give the decoder the stream; clear "finished" |
| 0x3202c0 | `movie_open` | set up descriptor, buffers, decoder |
| 0x320498, 0x3204a4 † | `movie_isFinished`, `movie_hasQueued` | |
| 0x3204b4, 0x320530 | `movie_setSource`, `movie_queueNext` | no callers |
| 0x3205c8 †, 0x3205e0 † | `movie_enableAudioSync`, `movie_disableAudioSync` | |
| 0x3205ec | `movie_update` | one step per `gfx_beginFrame` while a movie is open |
| 0x320dcc | `movie_close` | |
| 0x320ea4 | `ui_startPulse` | `g_uiPulse[i] = 2.0` |
| 0x320ec4 | `ui_restartFadeIn` | `g_uiFadeIn[i] = 0` |
| 0x320edc | `mainloop_loadRequestedWorld` | enter the pending level (section 7) |
| 0x321524, 0x321640, 0x321700 †, 0x321788 | `splash_legalScreen`, `splash_soeLogo`, `splash_ubiLogo`, `splash_introMovie` | boot screens, written as callbacks for the modal loop; only the SOE logo and the intro movie are used |
| 0x321870 † | `mainloop_setAmbientCountdown` | |
| 0x32187c, 0x321c9c, 0x321e60, 0x3224d8 | `loadscreen_renderLoop`, `_selectWorldAlias`, `_start`, `_stop` | loading-screen thread |
| 0x322520 | `mainloop_pollAmbientAudio` | level music and ambience, once per displayed frame |
| 0x3226e4 | `tasks_run` | run pass (section 3) |
| 0x322934 | `mainloop_startWarmup` | start the 10-frame warm-up |
| 0x322954 | `mainloop_startFadeWait` | start an n-frame fade wait |
| 0x322970 | `task_plotroute` | run task, priority 1000 |
| 0x322998 | `mainloop_runSession` | the session: level changes and frames (sections 4–7) |
| 0x3235a8 † | `splash_languageMenu` | |
| 0x3236bc, 0x3237f8 | `mainloop_runModalCallback`, `…WithDisplayReset` | private frame loops that run no tasks |
| 0x3238f4, 0x32393c, 0x32396c | `mainloop_bootCardStep`, `mainloop_waitSaveStep`, `mainloop_runBootCardCheck` | modal callbacks and the boot memory-card check |
| 0x32399c, 0x323a3c | `mainloop_findArgument`, `mainloop_setupOfflinePlayersFromArguments` | developer command line |
| 0x323d70 | `dbg_scanIopMemory` | unreferenced; purpose Inferred |

† not in `ghidra_funcs.tsv`.

## 2. The task system

The list itself is engine code at 0x19e4a0–0x19e853 (outside this area), but this area is
its main user, so it is documented here in full.

### Task record (`g_tasks` 0x840100, 16 bytes each, sorted by priority) — Observed

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x0 | function pointer | task body, no arguments; also the task's identity | compared in `task_add` 0x19e4dc and `task_remove` 0x19e680 |
| +0x4 | s32 | priority; low runs first | insertion loop 0x19e52c |
| +0x8 | char * | name | `task_isRunning` 0x19e620 compares it with `strcmp` (case sensitive) |
| +0xc | u32 | flags: bit 0 = draw pass. Value 2 is used by two run tasks and never tested | `tasks_call` 0x19e7d8 |

`g_taskCount` 0x44fdb8, `g_taskCursor` 0x44fdbc. The next global after the table is at
0x840300, so there is room for 32 records (Inferred); `task_add` has no bounds check
(Observed). Forty-two registrations exist; how many can be live at once was not worked
out.

### Operations — Observed

- `task_add(fn, priority, name, flags)` 0x19e4a0: does nothing if a record with the same
  `fn` exists. Otherwise inserts after every record whose priority is less than or
  **equal** to the new one (equal priorities keep registration order). If the insertion
  index is at or below the cursor, the cursor is incremented.
- `task_remove(fn)` 0x19e664: finds by `fn`, closes the gap; if the index is at or below
  the cursor, the cursor is decremented.
- `task_isRunning(name)` 0x19e5e8: 1 if a record has that name. Used 34 times as a cheap
  global state flag (list in section 9, P7).
- `tasks_call(exclude, include)` 0x19e798: sets the cursor to 0 and walks the table
  through the global cursor, calling every record with `(flags & exclude) == 0` and
  (`include == −1` or `(flags & include) != 0`).

Consequences while a pass is running: a task may remove itself or any other task and the
walk continues with the right neighbour; a task added behind the cursor is called in the
same pass if its flags match; a task added at or before the cursor waits for the next
pass. One case goes the other way (executed, `docs/spec/object-system.md` 6.1): when the
running task has removed itself, the cursor has stepped back by one, and a task that is
then inserted at the index the running task had (same priority, registered now) is called
in the same pass. The cursor is one global, so passes cannot nest (none does).

Two passes exist: the **run pass** `tasks_call(1, −1)` inside `tasks_run` (flags 0 and
2), and the **draw pass** `tasks_call(0, 1)` at 0x323284 (flags 1). Nothing passes a mask
that separates flags 2 from flags 0.

### Every task in the program — Observed

Arguments recovered from the instructions before each of the 42 calls to `task_add`.
"Life" says whether the task exists for the whole run or comes and goes.

Run pass (called once per simulation tick, in this order; equal priorities in
registration order):

| Pri | Name | Function | Flags | Registered by | Life |
|---|---|---|---|---|---|
| 0 | `runwater` | 0x189844 | 2 | `mainloop_runSession` 0x322a3c | always |
| 0 | `gameSetObjectVis` | 0x1e4d48 | 0 | 0x322a90 | always |
| 1 | `gameMiscSync` | 0x1e3d60 | 0 | 0x322ac8 | always |
| 10 | `runObjects` | 0x14b910 | 0 | `world_init` 0x14c38c | always |
| 11 | `camera` | 0x1ebbe0 | 0 | `game_addCoreTasks` 0x1e6d04 | always |
| 12 | `transformSceneLight` | 0x148018 | 0 | 0x148ae4 | always |
| 15 | `updateParticles` | 0x18f970 | 2 | `particle_init` 0x18e7fc | always |
| 20 | `Async Load/Save Daemon RUN` | 0x2188a8 | 0 | `save_init` 0x2173a4 | always |
| 20 | `deathTask` | 0x1e75e8 | 0 | `deathTask_schedule` 0x1ebd7c | after a party wipe; removes itself |
| 20 | `missionmenurun` | 0x2316fc | 0 | `missionMenu_open` 0x231650 | while the mission menu is open |
| 20 | `jumpgate` | 0x27dd74 | 0 | `JumpGate_openMenu` 0x27da68 | while the gate menu is open |
| 24 | `playerSelectionCache` | 0x225428 | 0 | `playerSel_initCache` 0x22453c | front end |
| 25 | `frontend` | 0x1e08f0 | 0 | `frontend_start` 0x1e20d0 | front end |
| 25 | `srs` | 0x324288 | 0 | `lobby_addTask` 0x327f9c | while the lobby client exists |
| 50 | `HUD Run` | 0x1db870 | 0 | `hud_addTasks` 0x1dc1ec | in a level |
| 100 | `arena` | 0x306b78 | 0 | `arena_init` 0x304df0 | arena levels |
| 110 | `Dialog Demon Run` | 0x22ff48 | 0 | `dialog_addTasks` 0x22f8d8 | always |
| 110 | `warpMenu` | 0x18e00c | 0 | `main` 0x323f40 | always |
| 123 | `textMessageProcess` | 0x31dc80 | 0 | 0x322ae4 | always |
| 124 | `commProcess` | 0x31fb30 | 0 | 0x322b1c | always |
| 125 | `Script` | 0x1ed5a0 | 0 | `script_init` 0x1eda5c | always |
| 300 | `cutRunFrame` | 0x199928 | 0 | `cut_start` 0x19b630 | during a cutscene |
| 1000 | `plotroute` | 0x322970 | 0 | 0x322aac | always |

Draw pass (called once per displayed frame):

| Pri | Name | Function | Registered by | Life |
|---|---|---|---|---|
| 9 | `playerSelection` | 0x225478 | `playerSel_start` 0x2247ac | character select |
| 20 | `Async Load/Save Daemon DRAW` | 0x2189e0 | `save_init` 0x2173c0 | always |
| 20 | `missionmenudraw` | 0x232300 | 0x23166c | mission menu |
| 20 | `jumpgatedraw` | 0x27e2d0 | 0x27da84 | gate menu |
| 21 | `drawObjects` | 0x14b168 | `world_init` 0x14c3a8 | always |
| 28 | `drawFloorSprites (must be before drawworld)` | 0x19f4e8 | `decal_init` 0x1a01bc | always |
| 30 | `drawWorld` | 0x1ebc18 | `game_addCoreTasks` 0x1e6d20 | always |
| 50 | `inventoryRun` | 0x1c56a8 | `menu_openInventory` 0x1c17a0 | inventory open |
| 50 | `inventoryDraw` | 0x1c1108 | 0x1c17bc | inventory open |
| 50 | `shop` | 0x1c6068 | `shop_openOrStock` 0x1c89b4 | shop open |
| 50 | `stats` | 0x1d1bc0 | 0x1d3124 | stats screen |
| 50 | `HelpMessage` | 0x1dcc78 | `help_addTask` 0x1dd25c | always |
| 51 | `HUD Draw` | 0x1dbc48 | `hud_addTasks` 0x1dc208 | in a level |
| 52 | `pauseMenu` | 0x18cc08 | `pauseMenu_open` 0x18e3f8 | pause menu open |
| 65 | `drawParticles` | 0x18e628 | `particle_init` 0x18e818 | always |
| 100 | `arenaDraw` | 0x307284 | `arena_init` 0x304e10 | arena levels |
| 110 | `Dialog Demon Draw` | 0x230628 | `dialog_addTasks` 0x22f8f4 | always |
| 125 | `textMessageDraw` | 0x31deec | 0x322b00 | always |
| 300 | `cutDrawFrame` | 0x1995fc | `cut_start` 0x19b64c | during a cutscene |

Points worth knowing:

- `inventoryRun`, `shop`, `stats`, `pauseMenu` and `HelpMessage` are menu **logic**
  registered in the draw pass. They run once per displayed frame on the machine that
  opened them, outside the lockstep.
- The task named `warpMenu` is the pause-menu opener (it calls `pauseMenu_open` 0x18e2a4
  and `pauseMenu_close` 0x18e2cc).
- `camera` does nothing in a net game (test at 0x1ebbf8); there the camera is advanced
  from `net_predictLocalPlayer` and from drawing.
- `tasks_run` takes a second argument (0 from the main loop, 2 from `net_frameLoop`) and
  never reads it: register `$a1` is overwritten at 0x322770 before any use. Together
  with the unused flag value 2 on `runwater` and `updateParticles` this looks like a
  removed "skip the cosmetic run tasks" option (Inferred). As compiled, both run on every
  lockstep tick.

## 3. `tasks_run(n)` 0x3226e4 — one call runs n simulation ticks

Observed, in order:

1. In a net game, `g_menuInputLockout` (0x41b4fc) is set to 0.
2. The two edge words of all four pads (`g_pads[i]` +0xc "pressed" and +0x10) are saved.
3. n times:
   1. `tasks_call(1, −1)` — the run pass.
   2. Offline only: if `game_isFrozen()` is false and `g_warmupFrames` is 0,
      `g_simFrame` (0x44fdcc) is incremented. (In a net game `net_frameLoop` sets
      `g_simFrame = g_netFrame` around the call instead.)
   3. The edge words of all four pads are zeroed, so only the first tick of a displayed
      frame sees a button press.
   4. `game_rebuildAlivePlayers()`, then `game_checkAllDead()`.
   5. `pad_updateRumble()` 0x17474c.
4. If `g_menuInputLockout` is positive and the hold flag 0x41b500 is clear: it becomes 0
   when no pad has a button held (`g_pads[i]` +8 masked with 0xff0fffff), otherwise it is
   decremented — once per call, not once per tick.
5. The saved edge words are restored, so the draw pass sees the same presses.

The run tasks are not skipped when the game is paused; each task tests `game_isFrozen`
itself.

## 4. `mainloop_runSession` 0x322998 — start of a session

Called by `main` in an endless loop; one call lasts from "front end started" until
something sets `g_sessionExitCode` (0x41b508). Observed, in order (0x322998–0x322b38):

1. `g_simFrame = 0`. Offline, `g_cosmeticSeed` and `g_randSeed` are both set from the
   CPU cycle counter (0x3229f0, 0x322a00). In a net game only `g_cosmeticSeed = 0` is
   written. (A session is entered with the network flag set only through the `--net`
   argument; the normal front end clears the flag before the session starts.)
2. Level name and previous-level name are cleared; `game_addCoreTasks()`; `runwater` is
   registered; `inventory_resetPanels()`; display blanked for one frame;
   `g_sessionExitCode = 0`; light set-up 0x148728; `g_uiPulse[0..1] = 1.0`.
3. The six tasks listed above with "0x322a…" are registered.
4. If the pair at 0x8eda70 (name pointer, value) is set, `vars_set(name, value)` is
   called and the pointer cleared. No writer of that pair was found (Unknown).

Then the loop of section 5. On exit (0x3234e0–0x3235a7) it blanks the display, clears
the PvP flag `g_pvpModeB`, shuts the arena down, clears the current script, calls
`game_clearLevel(1)`, stops the three audio streams, unloads lumps down to keep level 10,
frees the equipment cache, closes the pause menu, removes the HUD tasks, clears
`g_paused` and `g_world`, and returns.

## 5. One pass of the session loop

Loop head 0x322b3c. Each pass is one displayed frame, preceded by a level change when one
is pending. Observed:

| Step | Addresses | What happens |
|---|---|---|
| A | 0x322b3c, 0x3234d4 | leave the loop if `g_sessionExitCode` ≠ 0 |
| B | 0x322b48–0x322bfc | idle voice: while no cutscene, not paused, no local menu, no dialog, `g_idleVoiceCountdown` counts down; at 1 a random player (cosmetic seed) gets `player_voice(slot, 2)`, which only does anything for a local slot |
| C | 0x322c00–0x322ca8 | **cancel a pending level change** if a level is loaded (0x4f85b0), the `frontend` task is not running, `memcard_isBusy()` is false, not PvP mode B, and no player has hit points above 0 |
| D | 0x322cac–0x322cd0 | `g_flag505b00Delay` counts down; at 0 the comm option flag 0x505b00 is set again |
| E | 0x322cd4–0x3231d4 | if `g_pendingLevel` is non-empty: the level change (section 7) |
| F | 0x3231d8–0x3234d0 | the frame (below) |

### The frame (step F), offline

| # | Address | Call | Notes |
|---|---|---|---|
| 1 | 0x323208 | `gfx_beginFrame(colour, 0)` | colour is `g_backgroundColor`, or opaque black while a local menu is open, warm-up is running or a fade wait is running. Also runs `movie_update` when a movie is open |
| 2 | 0x32321c | read hardware timer 0 | only for the unused measurement in step 6 |
| 3 | 0x323220 | `n = engine_frameStep()`, capped at 2 | section 6 |
| 4 | 0x323258 | `pad_readAll()` | polls the four controllers into `g_pads` and copies them to `g_rawPads` |
| 5 | 0x323264 | `tasks_run(n, 0)` | n simulation ticks; no input is read between the ticks |
| 6 | 0x323288 | timer 0 delta → `g_lastSimTimerDelta` | never read |
| 7 | 0x323284 | `tasks_call(0, 1)` | the draw pass, once |
| 8 | 0x32328c–0x32334c | fade wait / terrain-late test | if `g_fadeWaitFrames` ≠ 0: when terrain streaming is idle (0x17fe88) it counts down and calls `gfx_setScreenDarken(0x40)` (called "darkens the screen" in the earlier version; the value is the FIX alpha of the present pass, which mixes the new image with the previous one and does not darken by itself — `docs/spec/render-pipeline.md` section 8); forced to 0 after 1500 displayed frames; the frame's sorted draw packets are discarded (`gfx_resetSortedPackets`). Otherwise: if the terrain "late" flag 0x41c181 is set, `g_terrainLateFrames` counts up and above 21 asks for half-rate display (0x32333c) |
| 9 | 0x323350 | `mainloop_pollAmbientAudio()` | |
| 10 | 0x323358–0x323380 | `sound_update()`, `animsound_updateGroupVolumes()`, `lump_pollAsync()`, terrain streaming service 0x17d830(−1) (works from `g_cameraFocus`), `picCache_serviceRequests()`, wake the worker thread 0x17fce0 | per-machine services |
| 11 | 0x3233bc–0x32343c | warm-up tail | if `g_warmupFrames` ≠ 0: reset to 10 while streaming is busy, else count down; forced to 0 after 1500 displayed frames; the frame's draw packets are discarded; when it reaches 0 the colour offset is set to black-fading-in and the display un-blanked |
| 12 | 0x323440 | `gfx_endFrame(0)` | hands the frame to the display, waits for the vertical blank, updates the pacing variables, resets timer 0, increments `g_drawFrame` |
| 13 | 0x323448–0x3234d0 | `g_uiPulse[i]` decays toward 1 (×0.8 of the excess), `g_uiFadeIn[i]` rises by 0.12 to 1 | four slots each |

### The frame, net game

Steps 4–5 are replaced by one call, `net_main(0, 0)` at 0x323248. Everything else is the
same. Inside `net_main` (netcode area; order Observed by reading the decompile, key call
sites given):

1. `net_pumpReceive()` 0x132ee4 — incoming packets, including other peers' input.
2. Keep-alive and kick traffic (uses `g_drawFrame` for its cadence).
3. `pad_readPort(0)` 0x133420 reads this machine's controller; `Camera_getYaw` of the
   local camera 0x133464 goes into the record; `pad_apply` into `g_rawPads[localSlot]`
   0x1334dc.
4. Throttle decision (0x133548–0x13360c): no new input this frame when the local input
   frame is 39 or more ahead of the slowest peer's acknowledgement, and periodically
   when this machine has been running ahead of the others (details in the netcode area).
5. If not throttled, `engine_frameStep()` (1 or 2) new input records are appended for
   frames `g_localInputFrame`, `g_localInputFrame + 1` (loop at 0x1336a8). Both records
   of a 2-step frame carry the same controller sample.
6. Input packets are sent to the peers whose turn it is (`net_sendInputPacket` 0x1341a8).
7. The number of ticks is decided (0x134380–0x1343d4, section 6) and, if at least 1,
   `net_frameLoop(n)` 0x1343dc runs them. Otherwise the stall counter
   `g_netStallCalls` goes up.
8. `net_predictLocalPlayer(throttled)` 0x13444c — runs the prediction copy forward over
   the unconfirmed frames, and the local camera.
9. `g_pads[localSlot]` is overwritten with `g_rawPads[localSlot]` (0x134454 onward), so
   the draw pass and the menus see this machine's real controller.

`net_frameLoop(n)` 0x139e88, per tick (Observed): skipped entirely while
`g_pendingLevel` is non-empty (0x139fb4); `g_simFrame = g_netFrame`; every peer's input
record for the frame is decoded and applied to `g_pads[slot]` (0x13ac84);
`g_inSimTick = 1`; players of peers flagged to leave on this frame take a lethal hit
(0x13aeb8);
`tasks_run(1, 2)` 0x13aee0; `g_inSimTick = 0`; `path_service(1)` 0x13af3c (blocking
pathfinder pass); `g_netFrame++`; the sync hash for the frame is stored and compared;
the edge words of `g_rawPads` are zeroed. After the ticks the exclude mask is switched to
0x200000 (0x13b1f0) and the prediction copy is re-made when more than 30 frames are
unconfirmed.

## 6. How many simulation ticks one displayed frame gets

### The pacing variables (all per machine; engine area, read here because the main loop depends on them)

| Variable | Meaning | Written |
|---|---|---|
| hardware timer 0 (0x10000000) | counts at bus clock / 256 (mode 0x82 set in `engine_init`); 0x2626 counts are treated as one display field | zeroed in `gfx_endFrame` 0x19dcd8 and in the load warm-up loop 0x322f04 |
| 0x83d2c8 | fields the last frame took: (timer 0 + 0x1314) / 0x2626, sampled just before the reset | `gfx_endFrame` 0x19dcf4 |
| 0x44fd44 / 0x44fd40 / 0x44fdb4 | display rate mode: 0 = full rate (a new frame every field), 1 = half rate (meaning Inferred from `gfx_endFrame` and the vblank handler). 0x44fd40 is its inverse, 0x44fdb4 a copy read by the terrain drawer | only by 0x19dd48 (not named), which does nothing while the screen-darken level 0x44fd88 is below 0x80 or byte 0x44fd7c is set (the only store to that byte writes 0, at 0x1c03f4) |
| 0x44fdb0 | consecutive frames that missed their field in full-rate mode; the 32nd in a row → half rate | `gfx_endFrame` 0x19dc8c–0x19dcac |
| 0x44fdac | spare timer counts accumulated in half-rate mode by frames that took less than one field; above 0x7272 → full rate; zeroed by any frame that took longer | `gfx_endFrame` 0x19db08–0x19db50 |
| `g_terrainLateFrames` 0x5060a8 | see step 8 above | main loop |
| 0x44fd50 | signed byte, initial value 0, **no writer anywhere** | — |
| vblank semaphore 0x8400f0, counter 0x44fd98 | signalled / incremented by the vblank handler 0x19b6e4 | |
| `g_drawFrame` 0x44fdd0 | displayed frames since boot; also advanced by the loading-screen thread | `gfx_endFrame` 0x19daf8 |

### `engine_frameStep()` 0x19e3a8 — Observed

- Full-rate mode: returns clamp(0x44fd50 + 1, 1, 2). Since 0x44fd50 is always 0, this is
  **1**.
- Half-rate mode: returns clamp(0x83d2c8, 1, 2): **2** when the previous frame took two
  or more fields, **1** when it fitted in one.

### Offline

Ticks = `engine_frameStep()`, capped at 2 again at 0x323234–0x323240. So:

- At full rate the game runs exactly one tick per displayed frame. A frame that misses
  its field is simply shown late (no wait at 0x19dc74); the simulation slows down with
  it. There is no catch-up.
- On the 32nd late frame in a row (or the 22nd frame in a row with the terrain "late"
  flag) the display drops to half rate. From then on each displayed frame is held for
  two fields (Inferred from the two semaphore waits at 0x19db74 and 0x19dc7c) and gets
  two ticks, both run back to back from the single controller sample of that frame; the
  second tick sees no button-press edges.
- A frame that takes three or more fields still gets only two ticks: the game slows.
- When frames again finish inside one field and enough spare time has accumulated (about
  three fields' worth), the display returns to full rate.

### Net game

- Input production: `engine_frameStep()` records per displayed frame, unless throttled.
- Ticks run this displayed frame (0x134380–0x1343d4): 0 if `net_main` was called with its
  first argument set (loading); otherwise
  min(`engine_frameStep()`, number of consecutive frames starting at `g_netFrame` for
  which every active peer's input has arrived, counted up to
  `g_localInputFrame − g_netFrame − 1`).
- So a machine can run at most as many ticks per displayed frame as its own display mode
  allows (1 or 2). It cannot burst to catch up after a stall. A machine that is short of
  input runs 0 ticks, keeps drawing, and keeps predicting.
- Consequence for a slow machine (`docs/issues/lag.md` C5, FINDINGS L5): the rate below
  which it holds the others back is 60 pictures per second, not 30, for as long as its
  display is at full rate. There a call stands for one step however long the picture took,
  so every missed field costs every other machine one frame of lead. Only after 32 late
  pictures in a row, when the display has dropped to half rate and a call stands for two
  steps, is 30 per second neutral.
- While a level change is pending the ticks inside `net_frameLoop` do nothing, so every
  machine stops on the same lockstep frame.

## 7. Changing level (step E) — Observed

A level change is requested by writing a name, optionally `name_sub`, into
`g_pendingLevel` (0x41b6d0). Writers are simulation code (scripts, recall, jump gate,
mission menu, arena, death restart) and the front end. The main loop acts on it at the
top of the next pass:

1. Net game: if the save flag 0x4f8f2c is set, run the modal loop with
   `mainloop_waitSaveStep` until it clears (0x322d04). Then `net_flushBeforeLoad()`
   0x322d18: keep sending until every peer has acknowledged this machine's input up to
   `g_netFrame`.
2. `g_simFrame = 0`.
3. Developer LAN launch, at most once per boot (`g_netLaunchLatch`), only when flag
   0x402792 is set: `net_gameInit(0)`, `net_launchTransfer()`, modal loop with
   `net_debugLanLobby`, `net_startSync()` (0x322d38–0x322d90). The retail lobby path does
   its launch in the front end instead. "Only when flag 0x402792 is set" was read as a
   debug flag that is off in the shipped game. It is not: the byte is 1 in the executable's
   data (the word at 0x402790 is 0x00010000). The three tests are `g_networkMode` set
   (0x322d38), that byte set (0x322d44) and the latch clear (0x322d54); what the retail
   game lacks at this point is `g_networkMode`, because its lobby path sets it later, in
   the front end. The boot argument `--net` sets it at start, and then this step runs.
   **Ran** on one machine (`docs/issues/live-rig.md` 4d, FINDINGS V6): with `--net` there is
   no front end at all, the pending level `strife` triggers this step, the lobby announces
   itself by broadcast and the level loads on the confirm button. Whether a console or
   PCSX2 can pass that argument was not tried.
4. Unless positions are being restored (0x41b51c, 0x41b51e), `g_ambientCountdown = 60`.
5. Display blanked; local camera reset (`Camera_reset`) unless flag 0x4f8f28 is set, or
   the memory-card state is 8 with flag 0x4f8f2b clear (0x322dc0–0x322e00). The second
   condition is never true: no call of `memcard_setState` passes 8
   (`docs/issues/arena-entry.md`, corrections).
6. `mainloop_loadRequestedWorld()` 0x320edc:
   - if a level is current and no `deathTask` is running, its object state is stored into
     the save buffer (`save_storeLevelState`). The caller tests the result and would
     return at once on non-zero (0x320f44–0x320f4c), but the function returns 0 on every
     path, so that return is dead (`docs/issues/arena-entry.md`);
   - if the act changed (tested only outside the front end, and skipped when flag
     0x4f8f28 is set or a `deathTask` is running): save buffer cleared, quests and quest
     variables cleared, flagged items removed. Flag 0x4f8f28 is `g_cardXferLatch`, the
     "card load or save in progress" latch: set when a slot is chosen in the load or save
     screen, cleared when the loaded level has been entered or the "saved" box closes.
     Transient in normal use, but a save that ends in the card-error state leaves it set,
     and a machine with a stuck latch skips this block (and the camera reset of step 5) at
     later act changes (`docs/issues/sync-breakers.md` section 4c, B10, B11);
   - the previous name is kept in `g_prevLevelName`; the request is split at `_` into
     `g_levelName` and `g_levelSubName`; `g_pendingLevel` is emptied;
   - `game_loadLevel(g_levelName)` — this starts the loading-screen thread first thing;
   - spawn positions (0x4f70d0, 12 bytes per player) get a terrain height; when a real
     level is loaded and PvP mode B is off, players 1–3 are moved to a free spot near
     their position with `world_findFreeSpot`, which draws from `g_randSeed` (skipped
     when byte 0x4f7108 is 3);
   - a `Player` object (0x590 bytes) is constructed for every slot whose record has hit
     points above 0 and whose peer is active;
   - `g_idleVoiceCountdown = 300` when the level has no stored state.
7. `mainloop_startWarmup()`; the deferred script calls are run once
   (`script_runDeferred`, 0x322e6c) — outside any tick; net game: `net_clearGhost()`.
8. **Load warm-up loop** (0x322eb0–0x322fd0), repeated while `g_warmupFrames` ≠ 0:
   `game_rebuildAlivePlayers()`, `Camera_update(local camera)`, `drawWorld()`, and if a
   cutscene is active `cut_runFrame(1)`; then `lump_pollAsync()`, terrain streaming,
   timer 0 reset, worker wake. The counter goes down by one per pass while terrain
   streaming is idle and back to 10 while it is busy; it is held at 3 or more while any
   player's equipment models are still loading (0x1a30b0); it is forced to 0 once 1500
   displayed frames have passed. No frame is begun or ended here — the loading-screen
   thread owns the display.
9. Net game: `net_main(1, 0)`; `net_clearHeardFlags()`; then spin until
   `net_allPeersHeard()` or the stall limit (0x40279c ≥ 601), calling `net_main(1, 1)`
   each time `g_drawFrame` changes (0x323004–0x323060). This is the "everyone has
   finished loading" barrier.
10. Shop stock is generated for the four store levels by name: `hub`/`hub2`,
    `islgnome`, `stobonus` (`shop_openOrStock(0, 1|2|3, 1)`, 0x323064–0x3230f4).
11. `loadscreen_stop()`; particles reset; blank 6 frames; colour offset to black; the
    environment texture of `env.lmp` is uploaded if that lump is loaded; `g_simFrame = 0`.

Then the frame of step F runs as usual, with `g_warmupFrames` normally already 0.

The length of the warm-up loop differs per machine. What it calls is limited:
`drawWorld` skips the minimap and backdrop while the loading screen is up (0x1ebc18
tests `g_loadscreenActive`), and `cut_runFrame(1)` skips `cut_advance` (argument) and
returns at its `g_loadscreenActive` test before the skip and end handling. What still
runs per pass is `cut_setup` on the first pass only, the cutscene camera evaluation
`cut_evalCamera` 0x19712c, and `Camera_update`.

## 8. The top-level state machine

`main(argc, argv)` 0x323dcc (Observed):

1. Runtime start 0x3ad310; `engine_init`; clears the level names; `game_initCamera`;
   then registers the network message handlers in this order — cutscene 0x19b4b4, comm
   0x31fd38, dialog, HUD, inventory, text chat 0x31da4c, shop (the netcode notes say
   handler ids follow registration order); `save_init` (adds the two save-daemon
   tasks); `dialog_addTasks`; the object factory.
2. `g_pendingLevel = "strife"`; PvP flags zeroed; `warpMenu` task added.
3. Loads the fonts and interface lumps, raising their keep level so that level changes
   do not unload them.
4. `mainloop_runBootCardCheck()` — the memory-card screen, in a modal loop.
5. Unless a button skipped them: SOE logo, then the intro movie, each in a modal loop.
6. Command line: `--net` sets `g_networkMode`; `--stress` sets 0x4f85c7; `--splash` is
   looked up and ignored; `mainloop_setupOfflinePlayersFromArguments` handles `--pvp`,
   `--char`, `--female`. (Whether a retail boot ever passes arguments: Unknown.)
7. Forever: unload lumps down to keep level 5; on the first pass, offline,
   `frontend_start(0)`; `mainloop_runSession()`; if flag 0x40285c is set, `net_shutdown(0)`;
   then `frontend_start(0)`, `(1)` or `(2)` for exit codes 1, 0x65, 0xc9.

So the states are:

| State | How it is represented | Leaves by |
|---|---|---|
| Boot screens | modal loops in `main` | callbacks returning 1 |
| Front end | `frontend` task running, `g_inFrontend` = 1, level `intro` loaded (0x4f85b0 = 0), network flag off | the front end writes `g_pendingLevel` and removes its task (`frontend_stop`) |
| Loading | step E above; `g_loadscreenActive` = 1 | end of step E |
| Playing | level loaded (0x4f85b0 = 1), HUD tasks present | `g_pendingLevel` written (next level) or `g_sessionExitCode` written |
| Level change | same as Loading; the session function is not left | |
| Quit to front end | `g_sessionExitCode` ≠ 0: session returns, `main` restarts the front end | writers: scripts `leaveGame`/`exitToMainMenu`, pause menu, net "alone" test, HUD net-status draw, save screens, arena |

There is no explicit state variable; the task list and these flags are the state.

### Modal loops

`mainloop_runModalCallback(callback, blankFirst, teardown)` 0x3236bc is a private frame
loop: begin frame, `pad_readAll`, callback, `lump_pollAsync`, input-lockout countdown,
`g_simFrame++`, end frame, `sound_update`. It runs **no tasks**. While it runs,
`g_simFrame` counts displayed frames, which is what the splash callbacks time themselves
with. Used for: boot card check, the two splash screens, the developer LAN lobby, and
(variant 0x3237f8) waiting for a save before a net level change.

### Loading-screen thread

`loadscreen_start` (called from `game_loadLevel`) loads the level's loading lump, creates
a thread on first use and starts it. The thread (`loadscreen_renderLoop`, priority 5,
above the main thread's 10) loops begin frame → sprites → end frame until
`g_loadscreenStop`. It therefore increments `g_drawFrame`, resets timer 0 and drives the
rate-mode logic while the main thread loads. `loadscreen_stop` waits for it to go
dormant.

### Movie player

Driven from `gfx_beginFrame` (0x19d904) while `g_movieActive`: `movie_update` reads the
stream in chunks into two alternating buffers, decodes one picture per call unless audio
stream 2 is behind the picture count (it holds the picture then), and uploads it. Used by
`splash_introMovie` and by the engine's blocking player 0x19dea4. Not connected to the
simulation.

## 9. Per-machine state

### P-list: places where per-machine state can reach shared state

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| P1 | The cancel of a pending level change (step C) runs once per displayed frame outside the lockstep and depends on `memcard_isBusy()`, this machine's memory-card state. If a level change is requested while every player is at 0 hit points, a machine whose card screen is idle cancels it and a machine whose card is busy loads the level | Observed code, Inferred consequence | 0x322c00–0x322ca8; the test at 0x322c3c; write at 0x322ca8 |
| P2 | Thirteen of the 23 run tasks are not simulation, yet run inside every lockstep tick (table below). Their shared effects have to go through game messages; each one that does not is a desync source | Observed | section 2 table; `net_frameLoop` 0x13aee0 |
| P3 | `save_daemonRun` (run task) counts the autosave countdown only when this machine's card is idle, no full-screen menu is open here and the local camera is in follow mode, then calls `save_game`. The snapshot frame can differ per machine. Already described in docs/audio-save.md | Observed | 0x2188d8, 0x218984, 0x2189cc |
| P4 | `gameMiscSync` advances `g_randSeed` every 1800th tick, but only when `net_allPlayersState2()` holds (flag 0x4f7134, flag 0x4f85c5, a field of every player record). If those differ between machines the shared seed differs. They cannot: the front-end flag is cleared at launch on every machine, `g_lobbyLaunch` 0x4f7134 comes from the same test on every machine of a lobby game, `g_gameCompleteFlag` 0x4f85c5 is written by a lockstep script and by `game_resetState`, and the record kind bits are transferred at launch (`docs/issues/sync-breakers.md` section 6a) | Observed code; the inputs cannot differ between machines of one retail game (was Unknown) | 0x1e3e8c–0x1e3ee0; 0x1ec5d8 |
| P5 | `hud_tickMessage`, called from the `HUD Run` task inside the tick, counts the HUD message timer 0x4f66e0 down only while this machine's `g_warmupFrames` is 0. Readers of the timer found: the boss-meter draw and 0x207dc4, which the earlier version called a camera function; the address is a call inside `Vehicle_run` 0x207c3c (the driver help text, which also clears vehicle +0x408; `docs/issues/arena-desync.md`). The first is per machine; the second is simulation code. What the timer gates there (followed in `docs/issues/claims-audit.md` row 72): while the timer is non-zero `Vehicle_run` leaves the latch at vehicle +0x408 set and shows nothing; once it is zero it clears the latch and shows the one-time driver help text. Nothing else reads +0x408, so the per-machine timer changes when a help line appears and one private word of the vehicle; vehicles only | Observed | 0x1d935c; readers 0x1d93b8, 0x207dc4; 0x207dac–0x207dd4 |
| P6 | The `warpMenu` run task returns early on this machine's display-list fill, `g_warmupFrames` and `g_localMenuOpen` before it looks at the pads. Its effects are the local pause menu and a menu-state message | Observed | 0x18e014–0x18e084, 0x18e2a4 |
| P7 | The task list is itself state that simulation code reads by name: `Player_run` asks whether `jumpgate` or `missionmenurun` is running (0x1a56ac, 0x1a56c0); so do the recall-button poll 0x1bcf5c, `hud_run` 0x1dba44, `save_game` 0x2181d0 and `mainloop_loadRequestedWorld` (`deathTask`). Those tasks are opened from lockstep code, so this is shared as long as every opener is. The draw-pass names (`pauseMenu`, `playerSelection`, `missionmenudraw`) are per machine and are queried by `game_isFrozen` (offline branch only), `cut_runFrame` 0x199c98 and menu code | Observed list; Inferred that the run-task openers are all lockstep | call sites of 0x19e5e8 |
| P8 | Level entry does shared work outside any tick: object construction, `world_findFreeSpot` draws from `g_randSeed`, the deferred script calls, shop stock. It is the same work at the same lockstep frame on every machine, provided the state going in is the same | Observed code, Inferred safety | 0x320edc, 0x322e6c, 0x3230c4 |
| P9 | The load warm-up loop runs a per-machine number of passes of `Camera_update`, `drawWorld` and `cut_runFrame(1)`. `cut_setup` (creates and hides objects) runs in the first pass on every machine — that applies only to a cutscene started during the load (`preStart`, `start`, the load-time post action or the promoted deferred queue); a cutscene started from a trigger inside a tick is not touched by this loop. Whether `cut_evalCamera` 0x19712c accumulates anything per call was Unknown; answered in `docs/issues/arena-entry.md` section 3.2: it recomputes the camera from the clock on every call and keeps one latch, the time of the last camera cut for which it raised a fade wait (0x44fd00, zeroed by `cut_start`) | Observed | 0x322eb0–0x322fd0; guards 0x199bd8–0x199c10, 0x199d68 |
| P10 | `engine_frameStep()` (pacing) is called inside the tick by `pad_updateRumble` only; it scales rumble timers of local slots. Not shared state | Observed | 0x1747f0, 0x174858, 0x1748f0 |
| P11 | Offline only: both seeds come from the CPU cycle counter at session start. In a net game the session start does not touch `g_randSeed`; `net_startSync` zeroes it | Observed | 0x3229f0–0x322a04; 0x13dce0 |
| P12 | In a net game `g_simFrame` equals `g_netFrame` only during a tick. Between ticks it holds a stale per-machine value, so draw code that uses it as a clock is per machine, and any draw code that stored it into shared state would be a problem. Not audited | Observed mechanism | `net_frameLoop` 0x13af98, 0x13b28c |

P1 is new. P3 belongs to the audio-save document. None has been tested on a running game —
still true of these twelve rows: the live game the project now has (`docs/issues/live-rig.md`)
has run one machine only, and none of P1–P12 was exercised on it.

### Every run task: simulation or not

"Scan" means the task body and its direct callees were searched mechanically for reads
of the raw pads, camera, local slot, local menu flags, audio status, `g_drawFrame`,
timer 0, the cosmetic seed and the pacing variables; "read" means the body was read.

| Task | Verdict | Per-machine things it touches | Depth |
|---|---|---|---|
| `runwater` 0x189844 | cosmetic, not simulation | cosmetic seed 0x186ed0; water ripple heights only | read in part |
| `gameSetObjectVis` 0x1e4d48 | simulation, with one per-machine input | local camera mode at 0x1e4dac sets `g_cullByCamera`; net games overwrite it unless a cutscene is active (FINDINGS D6) | read |
| `gameMiscSync` 0x1e3d60 | mixed | recall countdown and level request (shared); polls the **raw** local pad for the recall button and sends game message 3 (0x1bcfa8); closes local menus for the local slot (0x1e3da0–0x1e3dcc); P4; draws debug text | read |
| `runObjects` 0x14b910 | simulation | see docs/objects.md; D6 | not re-read |
| `camera` 0x1ebbe0 | per machine; no-op in net games | | read |
| `transformSceneLight` 0x148018 | rendering maths only | camera matrix 0x44f110 → light vectors | read |
| `updateParticles` 0x18f970 | cosmetic, not simulation | particle pools; frees empty groups | read |
| `Async Load/Save Daemon RUN` 0x2188a8 | per machine | P3; play-time counter gated by `g_localMenuOpen` | read |
| `deathTask` 0x1e75e8 | simulation | none found | read |
| `missionmenurun` 0x2316fc | mixed | per docs/ui.md: driven by the owning player's lockstep pad; `net_isLocalSlot` at 0x231a4c. That test is not a harmless local one: together with `pauseMenu_isOpen` (0x231a5c) it makes the function return before its pad test on the chooser's own machine while that machine's pause menu is open, and the other machines act on the press — a per-machine branch in a lockstep menu (FINDINGS U2; `docs/issues/draw-sim-leaks.md`; the same lines are in `jumpgate_menuRun` 0x27dee0–0x27df0c) | scan; 0x231a4c–0x231a78 read |
| `jumpgate` 0x27dd74 | mixed | `net_isLocalSlot` 0x27dee0; a callee reads the camera (0x27e6b0) | scan |
| `playerSelectionCache` 0x225428 | per machine (front end) | keyboard 0x31d34c | read |
| `frontend` 0x1e08f0 | per machine (front end, offline by construction) | audio, `g_drawFrame`, vblank wait | scan |
| `srs` 0x324288 | per machine (lobby client) | network I/O | not read |
| `HUD Run` 0x1db870 | per machine with message output | raw pads 0x1db960, local slot, local menu flag, camera; opens menus (FINDINGS: `hud_run`); P5 | scan |
| `arena` 0x306b78 | simulation, plus | writes `g_pendingLevel` and `g_sessionExitCode` (0x307164); closes local menus | scan |
| `Dialog Demon Run` 0x22ff48 | per machine with message output | raw pads 0x2300b4, audio position 0x23024c, audio status 0x23032c, camera, `g_uiFadeIn` 0x2302a4; sends dialog messages | scan |
| `warpMenu` 0x18e00c | per machine with message output | P6 | read |
| `textMessageProcess` 0x31dc80 | per machine with message output | keyboard; sends a game message 0x31db18 | read in part |
| `commProcess` 0x31fb30 | per machine | voice hardware | not read |
| `Script` 0x1ed5a0 | simulation | `script_runByName` stamps `g_drawFrame` + 20 into 0x4f8694 when a name is not found. The word has one reader, the same function: it compares the word with the display-frame counter (0x1ed6f4) and renews the stamp only when the old one has passed (0x1ed708); the comparison decides nothing else (`docs/issues/claims-audit.md` row 73; the earlier version said no reader was found) | read |
| `cutRunFrame` 0x199928 | simulation, plus | per docs/engine.md and FINDINGS D8: audio status 0x199e64, vblank wait 0x199e34, reseeds the cosmetic seed 0x199f88; the `g_warmupFrames` test at 0x199bd8 is offline only | head read |
| `plotroute` 0x322970 | simulation | timer 0 inside `path_service` (FINDINGS D5) | read |

Per tick, after the tasks: `game_rebuildAlivePlayers` (uses `net_isLocalSlot` to build
the local-only lists), `game_checkAllDead` (closes local menus), `pad_updateRumble`
(P10).

### Everything the main loop does between ticks, other than drawing

| What | Where | Can it change shared state? |
|---|---|---|
| idle voice line | step B | no: `player_voice` returns unless the slot is local; cosmetic seed only (head of 0x1b7ba8 read) |
| pending-level cancel | step C | **yes — P1** |
| comm flag 0x505b00 restore | step D | read by `commProcess` and config code; no simulation reader found |
| level change | step E | yes by design — P8, P9 |
| `net_main`: receive, local pad, input records, send | step F | this is the lockstep itself |
| `net_predictLocalPlayer` | 0x13444c | known hazard class, FINDINGS G1–G10 |
| raw pad copied over `g_pads[localSlot]` | 0x134454 | the next tick rebuilds every pad field from the input record (FINDINGS G5) |
| draw pass | 0x323284 | the draw tasks that are really menu logic (inventory, shop, stats, pause, help, player select, save screens) act here; see docs/ui.md. `HUD Draw` can write `g_sessionExitCode` (0x1dbe80, 0x1dc0c4) — per machine by intent |
| fade wait, warm-up tail | steps 8, 11 | `g_fadeWaitFrames` is read only by the main loop. `g_warmupFrames` is read inside the tick only at the places in P5, P6 and (offline only) `tasks_run`, `game_isFrozen`, `cut_runFrame` |
| `mainloop_pollAmbientAudio` | step 9 | zeroes the byte counters at 0x4f7158 that `damage_apply` increments (0x1e837c); **nothing reads them** — the "music intensity" consumer no longer exists. Audio only |
| sound, streaming, picture cache | step 10 | terrain streaming follows the local camera; whether simulation queries depend on which terrain blocks are loaded is Unknown (engine area) |
| `gfx_endFrame` | step 12 | pacing variables only |
| UI ramps | step 13 | `g_uiFadeIn[0]` gates part of `dialog_runTask` (0x2302a4), a per-machine task |

### Frame pacing and the simulation

The variables are listed in section 6. Readers, complete for this binary:

- `engine_frameStep()` (0x44fd40, 0x44fd50, 0x83d2c8): main loop 0x323220; `net_main`
  0x1336a8, 0x1343a0; `net_predictLocalPlayer` 0x131de0, 0x132bc0; `pad_updateRumble`
  (three sites, inside the tick, P10); two draw-pass menu functions 0x1c0a4c
  (`inventory_drawPlayerModel`, spins the model; the record field it writes, +0x4a58, has
  no simulation reader) and 0x1cee74 (`itemList_analogCursor`).
- 0x44fd44: begin/end frame and display set-up only. 0x44fdb4: terrain and model drawers
  (0x17ab50–0x180fec) and the main loop test at 0x323330. 0x44fdb0, 0x44fdac, `g_terrainLateFrames`,
  `g_lastSimTimerDelta`: no reader outside the function that writes them.
- Timer 0 directly: the pathfinder budget (FINDINGS D5), `gfx_endFrame`, a worker-wake
  measurement 0x17fce0, the main loop measurement.
- `g_drawFrame`: read by one simulation function found by another area,
  `ShopDaemon_run` 0x1d149c (see docs/ui.md), and otherwise by drawing, menus, audio and
  the network send cadence.

So no simulation code reads the rate mode or the field count. Pacing reaches the
lockstep only through how many input records a machine produces and how many ticks it
may run per displayed frame, which is by design.

## 10. Data owned by this module

| Address | Name | Type | Meaning | Evidence |
|---|---|---|---|---|
| 0x41b508 | `g_sessionExitCode` | s32 | 0 = keep running; 1 / 0x65 / 0xc9 select the front-end mode on restart | 0x3234d4; `main` 0x32423c |
| 0x41b6d0 | `g_pendingLevel` | char[] | next level request, `name` or `name_sub` | section 7 |
| 0x41b721 | `g_levelName` | char[] | current level | 0x320edc |
| 0x41b771 | `g_levelSubName` | char[] | text after `_` | 0x320edc |
| 0x41b7c2 | `g_prevLevelName` | char[] | level left behind | 0x320edc |
| 0x506044 | `g_backgroundColor` | u32 | frame clear colour | 0x323204 |
| 0x506048 | `g_warmupFrames` | s32 | frames to wait for streaming before showing the picture | 0x322948 |
| 0x50604c, 0x506050 | `g_fadeWaitFrames`, `g_fadeWaitStart` | s32 | same idea for camera cuts | 0x322964 |
| 0x506054 | `g_idleVoiceCountdown` | s32 | | step B |
| 0x506058 | `g_flag505b00Delay` | s32 | | step D |
| 0x506060 | `g_uiPulse` | float[4] | UI brightness pulse | step 13 |
| 0x506070 | `g_uiFadeIn` | float[4] | dialog fade-in | step 13 |
| 0x506080 | `g_warmupStartFrame` | s32 | for the 1500-frame limit | 0x322950 |
| 0x506084 | `g_skipSplash` | s32 | | 0x3216e8 |
| 0x50608c | `g_ambientCountdown` | s32 | | 0x322550 |
| 0x506090–0x5060a0 | `g_loadscreenThread`, `…Active`, `…Frame`, `…Phase`, `…Stop` | | loading-screen thread | 0x321e60 |
| 0x5060a4 | `g_netLaunchLatch` | s32 | set once, never cleared (no other reference in the program) | 0x322d50 |
| 0x5060a8 | `g_terrainLateFrames` | s32 | | 0x323310 |
| 0x8eb060 | `g_movie` | 6 words | lump name, entry name, stream file, chunk table, chunk number, loop flag; queued copy at 0x8eb078 | 0x3202c0 |
| 0x50602c–0x506038 | `g_movieFinished`, `…ReadSlot`, `…PlaySlot`, `…ReadDone`, `…Active`, `…AudioSync`, `…Frame` | | movie player state | 0x3205ec |

## 11. Corrections to existing files (not edited — reported)

- `names.tsv` `main_loop` 0x32316c is not a function. It is one instruction (a call that
  looks up the environment texture) in the middle of the level-change block of
  0x322998. The frame part of the loop starts at 0x3231d8, the loop head is 0x322b3c.
  Because of the entry, the tools show 0x32316c–0x3235a7 as a separate function.
- `names.tsv` `task_add`: the fourth parameter is a flag word (0, 1 or 2), not a
  boolean.
- OVERVIEW "Time and tasks": the object-visibility task has priority 0, not −1. The
  priority-15 particle task is a **run** task (flags 2); the particle draw task is 65.
  `inventoryRun` is a draw-pass task.
- `tasks_run(1, 2)`: the second argument is ignored.
- FINDINGS G5 says 0x41c138 is never written; `pad_updateRumble` decrements it and clamps
  at 0 every tick (0x174780–0x174790). It starts at 0, so the conclusion stands.
- `player_pollRecallButton` 0x1bcf6c asks for a task named `pausemenu`; the task is
  registered as `pauseMenu` and the comparison is case sensitive, so that test can never
  be true.

## 12. Open questions and what was not done

- P1: is there a real sequence in which a level change is requested with every player
  at 0 hit points in a net game (for example a trigger volume or timed script firing on
  the tick the last player dies)? Needs the script list and a two-machine test.
- P4: can flag 0x4f7134, flag 0x4f85c5 or the record field tested by
  `net_allPlayersState2` differ between machines? (Answered: no —
  `docs/issues/sync-breakers.md` section 6a.)
- P9: read `cut_evalCamera` 0x19712c for per-call accumulation (it calls
  `mainloop_startFadeWait` at 0x198e98, which is harmless, but was not read further).
  (Answered in `docs/issues/arena-entry.md` section 3.2: one latch, otherwise a function
  of the clock.)
- Whether terrain streaming (which follows the local camera) can change the result of
  any simulation query.
- The 32-record capacity of the task table against the worst simultaneous task count.
- The deferred quest-variable pair at 0x8eda70: no writer found.
- Whether the retail boot passes any command-line argument.
- The run tasks marked "scan" or "not read" above were not read in full; the per-machine
  column for them lists only what the mechanical search found, and virtual calls were not
  followed.
- The chat / keyboard / voice module 0x31d2a0–0x31fdf3 (nominally in the skills range)
  was not read beyond its three task entry points.
- The movie player was read for structure only; the decoder library was not identified
  by name.
- `dbg_scanIopMemory`: what the remote call returns.
