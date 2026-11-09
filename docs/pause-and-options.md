# Pause menu, in-play screens and options — SLUS-20973 US v2.00

2026-11-09. Research for the shared native client. The executable is pinned by SHA-256
in `tools/difftest_pause_menu.py:20`. **Executed** means that test ran the original
function in `tools/ee_emu.py` on authored state at seeds 20973 and 7 and asserted the
stated result. **Observed** means the code or data at the address was read and not run.
**Inferred** and **Unknown** are as in `CONTRIBUTING.md`. Nothing here was captured
from Play!, PCSX2 or a console, and no rendered pixels, audio output or card I/O were
checked. Game text is not stored. Rows and prompts are named by lookup key or address.

Inputs reused: `docs/options-menu.md` (this branch, 603b2b7: the options list,
slider/toggle edits and the 760-byte config image); `t3/research-quest-log` 965ec52
`docs/spec/quest-log.md`; `t3/research-save-screen` c8895e2 `docs/save-screen.md`;
`t3/research-levelup` 98a8a47 `docs/spec/levelup.md`; `t3/research-inventory-screen`
4a8a78a `docs/spec/inventory-screen.md`; `t3/research-menus` 099900e `docs/menus.md`.

## 0. Answer in short

- The pause menu has **no** inventory, skills, quest-log, map or save row. Its normal
  table 0x44f3b8 has nine rows: return to game, recall, load game, level warp (debug),
  a literal debug editor row, options, kick players (host), exit mission and exit game.
  Only six of them are normally visible offline (§2).
- Inventory, stats, quests and skills are pages of one HUD panel opened by the
  inventory button (§4). Saving happens at save points and through the script
  command (§4). There is no full-screen map. The mission chooser is a separate
  trigger-opened screen.
- Options are the same 14-row list as the front end, plus a voice-comm sub-list, a
  controller-slot chooser and a card options screen. Leaving the list queries the
  760-byte config image and, if anything changed, asks whether to save it (§5).
- Offline, opening the pause menu sets `g_paused` 0x41b4f4, which freezes objects and
  the frame counter. Online, nothing is paused: the menu is a local draw-task overlay (§7).

## 1. Fixture and disclosed stubs

`tools/difftest_pause_menu.py:38` follows only `pauseMenu_task` 0x18cc08,
`menuList_handleInput` 0x1a01d0, `menuList_setSelection` 0x1a076c, `libc_strcmp`
0x3b8534 and `libc_strstr` 0x3b96a8. Each probe follows its own target instead:
0x18e334, 0x18df90, 0x18e00c, 0x1ebdf8, 0x1db870, 0x1c15c8, 0x1c52dc or 0x222b10.
Every other callee is a recorded stub returning 0, except those listed at
`:41–46` and `:70–75`: `memcard_getState` −1, `net_localIsFirstActive` 1,
`net_firstActiveSlot` 0, `net_isLocalSlot` 1, `net_getLocalPlayerSlot` = the pad
index, and `net_isSlotActive(slot)` = slot < player count. Some cases override
one of these. The authored state (`Fixture`, `:56–115`) uses confirm mask 0x40 at
0x41bfbc and cancel mask 0x20 at 0x41bfb8, the cross-confirm set that
`docs/menus.md:80` executes for byte 0x41b69c = 1. Player hit points +0xac are 1.0,
the local camera 0x4f8450 has +0x34 = 1, and the level name at 0x44fe18 is
synthetic. Rows are selected by writing the list terminator's +4 word. Raw-pad
edges go to `g_rawPads` 0x4028d0 + 0x58 × pad (+0xc) and repeats to +8. After
every task frame the test asserts that the shared seed words 0x404460/0x404464 are
unchanged (`:100–106`).

Button names are **Inferred** from the byte-swapped pad layout these masks follow
(0x40 cross, 0x20 circle, 0x10 triangle, 0x80 square, 0x100 select, 0x800 start,
0x2000/0x8000 right/left), matching `docs/menus.md:80`.

## 2. Pause menu entries and actions

Tables and records (16 bytes: key pointer, kind, value pointer, flags). Kinds: 0
action, 3 toggle, 4 slider, 5 disabled (drawn but skipped by the cursor), 8 comm
volume. Flags bit 0 hides a row. The selection is stored in the terminator's +4
word as `row | row << 8` (**Executed** `:282–286`; **Observed** 0x1a07b4–0x1a07c0).
All records are **Executed** reads (`check_tables`, `:122–150`). The reference is
`tools/ref_pause_menu.py:12–45`.

| Row | Key | Shown when (per frame, pass at 0x18cc4c–0x18cf94, second pass 0x18d2fc–0x18d4ec) | Accept action |
|---:|---|---|---|
| 0 | `menu_returntogame` | always | `pauseMenu_close`; `g_menuInputLockout` 0x41b4fc = 60 |
| 1 | `menu_recall` | hidden if `g_pvpModeB` 0x4f7120 or task `missionmenurun` runs; disabled (5) if a dialog is open, task `jumpgate` runs, local camera +0x34 ≠ 1, or (net game and local player dead) | `hudmsg_sendRecall(pad)` 0x1de138 (game message 3, `docs/spec/game-messages.md:295`) |
| 2 | `menu_loadgame` | disabled in a net game, in PvP mode B or in a medal mission 0x4f713c | `pauseMenu_close`; lockout 60; `memcard_requestLoad(pad, 1)` 0x2176e0 |
| 3 | `menu_levelwarp` | hidden unless `g_debugCheats` 0x4f8ee0 | sub-menu 1: table 0x44f508, filled by 0x18e40c |
| 4 | literal debug row | hidden unless `g_debugCheats` | byte 0x44f210 = 1: following frames run `debug_missionEditor` 0x1e31c0 instead of the list; the flag becomes the editor's result inverted |
| 5 | `menu_option` | always | `config_backup` 0x1e6428; sub-menu 2: options table 0x44f218 |
| 6 | `menu_kickplayers` | net game, `net_localIsFirstActive`, not a medal mission, at least two active slots; disabled if a dialog is open (that case **Observed** only, 0x18ceb4) | sub-menu 4: table 0x44f4a8 rebuilt with every other active slot, cursor on row 1 |
| 7 | `menu_exitmission` | hidden in a level whose name contains the substring at 0x534330 (the hub), on a non-host machine, when the host slot's player is dead, or in PvP mode B; disabled if a dialog is open | confirmation state 1 (§6) |
| 8 | `menu_exitgame` | always | confirmation state 2 (§6) |

**Executed:** twelve visibility fixtures (`VISIBILITY`, `:223–247`) and every row's
accept (`check_main_accept`, `:259–325`, with the argument checks at `:273–286`).
A cursor left on a hidden or disabled row is moved to row 0 by the list handler
before dispatch, and that accept acts as row 0 (`:287–298`). Hide bits for rows
3 and 4 are only ever set, never cleared (**Observed** 0x18cf0c–0x18cf84). The other
rows recompute each frame.

The debug table 0x44f458 replaces the main table when `g_debugCheats` is set and the
lockstep slot-0 held word 0x41bfe0 is exactly 0x803 (**Executed** `:153–177`). Its
rows are return, level warp, `menu_invulnerability` (toggle of 0x44f20c, **Executed**
`:306–314`) and a literal row that calls `pauseDebug_sweepObjects` 0x18c7bc
(**Executed** `:299–305`). The dispatcher also compares against `menu_savegame`
(→ `memcard_requestSave`), `menu_moremenu`, `menu_changeplayers` and a literal
shop row. No table this task installs has those keys (`:146–149`; **Observed**
0x18d928, 0x18dcac, 0x18d45c, 0x18db94).

Sub-menus (word 0x44fa6c; `SUBMENU_TABLE`, `ref_pause_menu.py:48`), **Executed**
`check_submenus` `:382–478`:

| Sub | Table | Accept | Cancel |
|---:|---|---|---|
| 0 | main 0x44f3b8 | §2 table | `pauseMenu_close`, lockout 60 (`:412–415`) |
| 1 | level list 0x44f508 | offline `hudmsg_sendLoadLevel` 0x1de598, online `hudmsg_sendNewWorld` 0x1d9250, with the row's key; row kept in 0x44fa74; nothing during a cutscene 0x44fcd0 (`:452–478`) | back to sub 0 |
| 2 | options 0x44f218 | `menu_controls` → sub 3; `menu_comm` → sub 5; toggles/sliders are edited by the list handler (`docs/options-menu.md`) | sub 0x33 (§5) |
| 3 | controller slots 0x44f368 | `frontend_openControlConfig(row)` 0x1e2510 | back to sub 2 |
| 4 | kick list 0x44f4a8 | `net_kickPeer(slot byte 0x7d8a18[row])` 0x131cb8, then close; no confirmation (`:435–450`) | back to sub 0 |
| 5 | comm 0x44f308 | rows edited in place | back to sub 2 |

## 3. Opening and closing

**Executed** `check_poll` (`:540–582`), the run task `warpMenu` 0x18e00c (registered by
`main`, `docs/mainloop.md:145`). It walks the player slots. For a slot where
`net_isLocalSlot` holds and the **lockstep** pad edge 0x41bfe4 + 0x58 × slot has bit
0x800, it toggles `g_pauseMenuOpen` 0x44f208:

- closed → `pauseMenu_open(slot)`;
- open on the main table → `pauseMenu_close`, stop stream 2 if playing, then
  `config_commitOptions(0,0,0)` (0x18e2cc–0x18e2f8);
- open on any other table → nothing (start does not leave a sub-menu).

Opening is refused while `game_isFrozen` 0x1ebdf8 returns nonzero, while
`memcard_isBusy`, for a non-local slot, and offline while the local player is dead or
a dialog is open (a dead player may open it online). Closing still works while frozen. **Observed** further gates
before the pad loop (0x18e014–0x18e1e8): display-list head room ≥ 3000, `g_warmupFrames`
0x506048, `g_recallCountdown` 0x41b51d, `g_localMenuOpen` 0x41b69d, the cutscene byte
0x44fcd0, jump-gate travel, 0x4f66c8, local camera mode, PvP/medal and `missionmenurun`
host tests. The controller-removed notice also calls `pauseMenu_open` (0x1db678,
**Observed**).

`pauseMenu_open(pad)` 0x18e334, **Executed** (`:153–177`, five fixtures): it stores
pad → 0x7d8a10 and calls `hudmsg_sendMenuState(pad,1,0)`. Offline only, it sets
0x44fa80 = 1 and `g_paused` = 1. It installs the main or debug table at 0x44fa70,
calls `menuList_setSelection(table,0)`, clears the sub word and calls
`ui_startPulse(0)`. It sets `g_pauseMenuOpen` and 0x44fa78, then calls
`task_add(0x18cc08, 0x34, "pauseMenu", 1)`.
`pauseMenu_close` 0x18df90 (`:179–198`): if 0x44fa78 is set, it clears
`g_pauseMenuOpen` and the confirmation byte. Offline only, it clears `g_paused` and
0x44fa80. It clears 0x44fa78, calls
`hudmsg_sendMenuState(localSlot,0,0)` and `task_remove(0x18cc08)`. A second close does
nothing.

Each frame (`pauseMenu_task`), **Observed** order with the executed parts marked:
skip everything while `frontend_controlConfigRun` is active (0x4f709c ≠ 0) or the
card state is not −1 (0x18cfd4–0x18d004). Then the exit confirmation (§6), the editor
flag, the leave-options query (§5), the visibility passes, `menuList_draw(320,240,…)`
0x18d5cc (geometry: `docs/options-menu.md` for table 0x44f218), the footer key
0x534a08 (options) or 0x534a20 (others) at (320,412), and `menuList_handleInput` with
the raw pad. After that come the audio preview, `music_applyVolume` and
`audio_sendVolumes` every frame (**Executed** `:481–488`). Then the accept dispatch
(confirm edge, with accept sound) and the cancel dispatch (cancel edge, with back sound).

## 4. Where the other in-play screens live

| Screen | Opened by | Evidence |
|---|---|---|
| Inventory (bags, pages 0–2) | `hud_run` 0x1db870 (run task): raw-pad edge 0x100 with held 0x80 clear, no local menu open, pause menu closed, not frozen, plus the observed gates at 0x1db96c–0x1dbacc → `menu_openInventory(slot, 0)` | **Executed** `check_inventory` `:599–626` |
| Level-up / stats page | same press while acknowledged level +0x58 < earned level +0x59 → `menu_openInventory(slot, 1)` | **Executed** `:618`; page contract `t3/research-levelup` `docs/spec/levelup.md:64–90` |
| Quest log | page 4 of the same panel (`stats_screen` mode 1) | `t3/research-quest-log` `docs/spec/quest-log.md:60–72` (L1/R1 change page per `docs/issues/live-rig.md` §18.4) |
| Skills | page 5 (`skills_screen` 0x1d4660) | `docs/spec/levelup.md:92–115`; `docs/spec/quest-log.md:64–67` |
| Save | save-point object `Savepoint_run` (call at 0x28dc68), script `saveGame` 0x146c04 (call 0x146c60), save-screen reopen 0x2192f4 → `memcard_requestSave` 0x2175b4. The pause menu's `menu_savegame` compare at 0x18d944 is unreachable | **Observed** call sites; screen flow `t3/research-save-screen` `docs/save-screen.md:22–31`, `:246–256` |
| Load | pause row 2 → `memcard_requestLoad(pad,1)` | **Executed** `:277–278`; screen `docs/save-screen.md:251–256` |
| Map | no full-screen map was found. The HUD minimap mode 0x4f8400 and zoom 0x4f71a0 have direct stores only in `game_resetState` (0x1e6fd4, 0x1e6ff8) and arena setup (0x304ec8). The mission chooser `missionMenu_open` 0x231520 comes from a hub trigger | **Observed** (direct-store search only; `gxref` caveat in `docs/issues/sync-breakers.md:594`); `docs/spec/quest-log.md:54–58` |

`menu_openInventory` 0x1c15c8, **Executed** offline and online, modes 0 and 1
(`:627–648`), does these things: `g_localMenuOpen` 0x41b69d = 1; record +0x4a58 = 0;
`g_paused` = 1 **offline only** (0x1c176c); `hudmsg_sendMenuState(slot,1,0)`; tasks
0x1c56a8 (`inventory_runTask`) and 0x1c1108, each priority 0x32, flag 1. Mode 1 also
clears +0xed and sends one game message (inventory message 9, `docs/spec/levelup.md:43–44`).
0x1c52dc (`inventory_close`) stores `g_paused` = 0 at 0x1c530c in both network modes
(**Executed** `:649–661`; `docs/ui.md:277` P3).

### Inventory and equipment flow

From `docs/spec/inventory-screen.md:149–163` (4a8a78a) and `docs/menus.md` §2
(**Executed** there, not rerun here): in inventory mode 2 on a matched cell, confirm
(0x40) sends equip (inventory message 1, `invmsg_sendEquip` 0x1c5800), or unequip
(message 2, 0x1c5840) when `inventory_isEquipped` 0x1c41d8 is true. An item with flag
bit 35 starts a drag (panel +0x58/+0x64/+0x68/+0x6c) instead. Triangle (0x10) sends
drop (message 0, `invmsg_sendDrop` 0x1c59d0). Equip wins if both are pressed. The
message handlers (`docs/spec/game-messages.md`) change the bags and the equipment
pointers at record +0x43f0. **There is no "use" action in the inventory screen.**
Potions are used from the HUD quick slots (`Player_usePotion` 0x1b9fcc;
`t3/research-hud-inputs` `docs/spec/hud-quickslots.md`). Stat points are spent on
page 3/5 (`docs/spec/levelup.md:64–90`) and skill points on page 5 (`:92–115`).

## 5. Options state and where it is stored

Values, kinds and live addresses of the 14 option rows are in `docs/options-menu.md`
(Reachability and records) and `tools/ref_options_menu.py`: brightness 0x44fd80, music
0x4f8944, effects 0x4f8940 (sliders in steps of 1/120), combat camera 0x4f845c, reverse
yaw 0x4f8460, vibration 0x41bfb0, stereo 0x4f8948, blood 0x44fdc0, subtitles 0x44fcf4,
damage numbers 0x44fcf8, chat 0x50391c, markers 0x4f8458 (toggles). New here:

- **Comm sub-list** 0x44f308 (**Executed** reads `:122–150`): `menu_commenable`
  toggle 0x505b00, `menu_commecho` toggle 0x505afc, `menu_commplay` slider 0x505af4,
  `menu_commthresh` slider 0x505af0, `menu_commvolume` kind 8 at 0x505af8. These are
  config image +0xd0, +0xd4, +0xcc and +0xc8 (`docs/options-menu.md`, Applying values).
  How kind 8 is edited, and whether 0x505af8 is saved, is **Unknown**.
- **Controls** (row 3) opens the controller-slot chooser. The chooser is rebuilt every
  frame from `ui_fitText` of each player record into 0x4f3ec8 + 32 × row (**Executed**
  `:391–400`). Choosing a row calls `frontend_openControlConfig(row)`. The remap screen
  then runs from the pause task while 0x4f709c is nonzero (**Observed**
  0x18cfd8–0x18cfec; its flow is **Unknown**, as in `docs/options-menu.md`). The
  controls row is disabled (kind 5) in a net game (**Observed** 0x18d364–0x18d3a4).
- **Triangle in the options list** (edge 0x10) calls 0x222b10 (**Executed** `:528–538`).
  That calls `memcard_cancel` 0x21e614 and `memcard_setState(10)`, and clears browser
  stage 0x88d3e4. The card dispatcher's state 10 is `memcard_optionsScreen` 0x222b40
  (jump-table word 0x53f0b8, **Executed** read `:664–678`). That screen copies a card
  config into the live globals at 0x222d5c (`docs/options-menu.md`). Its prompts and
  flow are **Unknown** here.
- **Audio preview** (**Executed** `:489–526`): a changed music value plays
  `music_playGlobal(0x534a60, 0x41)` on stream 2 if that stream is idle, and resets the
  idle counter 0x44fa7c. After 240 idle frames the stream is stopped if still playing.
  A changed effects value plays a sample when `frame & 7 == 0` (frame word 0x44fdd0).
  `music_applyVolume` and `audio_sendVolumes` run every frame the menu is open, so a
  slider change is heard at once.
- **Leaving options** (cancel in sub 2 → sub 0x33), **Executed** `:416–433`: the next
  frame calls `config_commitOptions(0,1,0)` (query). With no differences it commits
  with `(0,0,1)` (in memory, no card save), returns to the main table and sub 0. With
  differences it draws `hud_drawMessageBox` (title/body keys at 0x5349b0/0x5349c8)
  until confirm, which commits `(0,0,0)` and requests the card save as in the front end
  (`docs/options-menu.md`, state 14), or cancel, which commits `(0,0,1)`. Start on the
  main list also commits `(0,0,0)` (§3).
- **Storage:** `config_commitOptions` copies live values into the 760-byte image
  `g_savedConfig` 0x4f8f38 (layout in `docs/options-menu.md`, Applying values;
  `t3/research-saves` `docs/save-format.md`). A card save writes it as the config file.
  The image is separate from slot saves. `config_backup` on entering options is the
  restore point. The commit also rewrites all four per-slot button tables from the
  saved controller rows. That is the multiplayer hazard U1
  (`docs/issues/draw-sim-leaks.md:57`).

## 6. Exit confirmation

**Executed** `check_confirm` (`:327–367`, eight cases). While byte 0x44fa68 is nonzero,
the task draws only `hud_confirmBox` 0x1dadc0 and skips the list. Result 1 clears the
state, result 2 accepts, and other results wait.

| State | Condition | Prompt key | On accept |
|---:|---|---|---|
| 2 (exit game) | — | 0x534968 | offline `g_sessionExitCode` 0x41b508 = 1 (back to the front end); online `g_netExitCountdown` 0x4f6948 = 30; then close |
| 1 (exit mission) | not a hub level, no PvP mode B, local slot = first active slot | 0x534990 | `hudmsg_sendExitCountdown` 0x1de25c (game message 8); close |
| 1 | otherwise, offline | 0x534968 | as state 2 offline |
| 1 | otherwise, online | 0x534978 | as state 2 online |

## 7. Pause semantics

- **Offline**, `pauseMenu_open` and `menu_openInventory` (also the shop, card screens,
  help boxes and mission menu, `docs/ui.md:277–305`) set `g_paused`.
  `game_isFrozen` 0x1ebdf8 returns it (**Executed** both modes, `:584–597`). While it is
  set, `runObjects` skips every object's run call (`docs/spec/object-system.md:390–405`),
  `tasks_run` does not advance `g_simFrame` (`:505–520`), and `Player_run` skips input
  (`docs/spec/player-tick.md:153`). Run and draw tasks still execute. The pause task
  itself is a draw task (priority 0x34). The HUD inventory button and a new pause press
  are refused while frozen (**Executed** `:622–623`, `:558–582`). Opening plays and
  stops nothing (**Executed** exact call list `:171–176`). Audio streams keep playing and
  volumes are pushed each frame.
- **Returning** via return to game, load or cancel sets `g_menuInputLockout` 0x41b4fc =
  60, which `Player_run` tests (`docs/spec/player-tick.md:153`). `tasks_run` clears
  it once no button is held and otherwise counts it down
  (`docs/spec/object-system.md:520–521`); online it is zeroed every tick (`:507`).
  **Inferred** purpose: the closing press does not reach the character.
- **Online**, `g_paused` is not touched by the pause menu or the inventory open
  (**Executed**), so the world keeps simulating. Only the menu-state message is sent.
  `pauseMenu_isOpen` 0x18cbfc is read by the jump-gate and mission menus, which then
  lock the local pad (U2, `docs/issues/live-rig.md:1850–1880`), and by prediction
  (`docs/engine.md:566`). Whether the local character keeps acting on lockstep input
  while the pause list takes the raw pad is **Unknown**. `docs/issues/online-quality.md:92`
  shows the menus do not stall the session.

## 8. Client-implementable list

1. Run a per-frame start-button poll on each local slot's lockstep pad (edge 0x800).
   Apply the §3 open gates. Toggle open/closed. Closing from the main list commits
   options with `(0,0,0)`. Start does nothing inside a sub-menu.
2. Open: remember the pad index and send menu-state (slot,1). Offline, set the pause
   flag. Install the main table, or the debug table for cheats + held 0x803. Cursor
   row 0, sub 0, pulse 0. Close: the reverse, idempotent; online never touch the
   pause flag.
3. Recompute the main rows' visibility and disabled kinds every frame with the §2 rules.
   Skip hidden and kind-5 rows in navigation, and snap an invalid cursor to row 0.
   Store selection as `row | row << 8`.
4. Dispatch accept by row key exactly as §2. Return, load and cancel set the
   60-frame input lockout. Recall sends game message 3. Load opens the load browser
   with flag 1. Kick needs no confirmation and is offered only to the host.
5. Exit flows through the two-state confirmation in §6. Exit game ends the session
   offline (exit code 1) or starts the 30-frame net exit countdown. Exit mission sends
   message 8 when the host is in a mission.
6. Options: reuse the front-end list model (`docs/options-menu.md`): kinds 4/3, the
   1/120 step, clamp, and live readers. Back it up on entry. Add the comm sub-list
   (kinds 3/4/8), the per-player controller chooser that opens the remap screen, and
   triangle → card options screen. Leaving runs the query/confirm/commit sequence in §5.
7. While options are open, push volumes every frame. Preview music on stream 2 when
   music changes and stop it after 240 idle frames. Play an effects sample every
   eighth frame while effects change.
8. Keep inventory/stats/quests/skills on the HUD panel. Select (0x100) opens it,
   held square (0x80) blocks it, and the opening page is the level-up page when a
   level is unacknowledged. Equip, unequip, drag and drop go as in §4. There is no
   use action there, and potions stay on the quick slots.
9. Saving is only at save points and the script command; the pause menu must not
   offer save.
10. Pause semantics: offline, freeze object runs and the sim frame counter while menus
    are up. Keep draw/run tasks and audio alive. Online, never freeze. Treat a local
    pause menu as display-only and keep U1/U2 in mind (`docs/issues/draw-sim-leaks.md`).

## 9. Unknown

- Pixel geometry of the pause list beyond the call arguments recorded here, its
  frame art, the footer and pulse rendering.
- Comm kind 8 editing, the controller remap screen flow, and the card options screen
  (state 10) flow.
- The level-warp list builder 0x18e40c's contents (debug only, not executed beyond
  the call), and `debug_missionEditor`'s pages.
- Whether a net-game player keeps acting on lockstep input while their pause list
  is open.
- The roles of 0x1c1108 and of the extra stores made by 0x1c52dc (0x4039c0, 0x41b4f8,
  0x4d8a08).

## 10. Validation (2026-11-09, Mac mini, serial)

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_pause_menu.py local/SLUS_209.73`:
**203 checks passed on each of seeds 20973 and 7** (tables 25, open/close 75,
visibility 12, main accept 24, confirmation 8, sub-menus 19, audio preview 9, poll 12,
freeze 4, inventory 12, card options 3). `tools/test_ref_pause_menu.py` adds 5 static
reference tests. Reruns, the unit suite and the sibling difftests are listed in
`work/cursor-report.md`. Logs are ignored files under `local/`.
