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
`t3/research-levelup` 98a8a47 and 8d38a0b `docs/spec/levelup.md`;
`t3/research-inventory-screen` 4a8a78a `docs/spec/inventory-screen.md`;
`t3/research-menus` 099900e `docs/menus.md`; `t3/research-hud-inputs` 0dc311c
`docs/spec/hud-live-producers.md` and `docs/spec/hud-input-producers.md`;
`t3/research-ui` 1ed740a `docs/hud-dynamic.md`.

## 0. Answer in short

- The pause menu has **no** inventory, skills, quest-log, map or save row. Its normal
  table 0x44f3b8 has nine rows: return to game, recall, load game, level warp (debug),
  a literal debug editor row, options, kick players (host), exit mission and exit game.
  Only six of them are normally visible offline (§2).
- Inventory, stats, quests and skills are pages of one HUD panel opened by the
  inventory button (§4). Saving happens at save points, through the script commands
  `saveGame` and `saveCheckPoint`, and at the end of the campaign (§4). The mission
  chooser is a separate trigger-opened screen.
- The map is the HUD minimap. Its map button cycles `g_minimapMode` 0x4f8400 through
  three modes. Mode 0 is a big centred map (offsets (0, 0), half-size 320 × 224), mode 1
  the corner map and mode 2 hides it. Holding the button with the camera stick zooms
  (§4.1, **Executed**).
- Options are the same 14-row list as the front end, plus a voice-comm sub-list, a
  controller-slot chooser and a card options screen. Leaving the list queries the
  760-byte config image and, if anything changed, asks whether to save it (§5).
- Offline, opening the pause menu sets `g_paused` 0x41b4f4, which freezes objects and
  the frame counter. Online, nothing is paused: the menu is a local draw-task overlay (§7).

## 1. Fixture and disclosed stubs

`tools/difftest_pause_menu.py:49` follows only `pauseMenu_task` 0x18cc08,
`menuList_handleInput` 0x1a01d0, `menuList_setSelection` 0x1a076c, `libc_strcmp`
0x3b8534 and `libc_strstr` 0x3b96a8. Each probe follows its own target instead:
0x18e334, 0x18df90, 0x18e00c, 0x1ebdf8, 0x1db870, 0x1c15c8, 0x1c52dc, 0x222b10 (with
`memcard_setState` 0x21f238) or the card dispatcher 0x2189e0. `check_options_commit`
(`:783`) also follows the original `config_commitOptions` 0x1e6650. `check_minimap`
(`:833`) runs `minimap_draw` 0x1e42e0 and every callee in 0x3a0000–0x3c0000 (the
soft-float helpers it calls), or `minimap_applyMode` 0x1e3ff0.
Every other callee is a recorded stub returning 0, except those listed at
`:52–57` and `:76–86`: `memcard_getState` −1, `net_localIsFirstActive` 1,
`net_firstActiveSlot` 0, `net_isLocalSlot` 1, `net_getLocalPlayerSlot` = the pad
index, and `net_isSlotActive(slot)` = slot < player count. Some cases override
one of these. The authored state (`Fixture`, `:67–127`) uses confirm mask 0x40 at
0x41bfbc and cancel mask 0x20 at 0x41bfb8, the cross-confirm set that
`docs/menus.md:80` executes for byte 0x41b69c = 1. Player hit points +0xac are 1.0,
the local camera 0x4f8450 has +0x34 = 1, and the level name at 0x44fe18 is
synthetic. Rows are selected by writing the list terminator's +4 word. Raw-pad
input goes to `g_rawPads` 0x4028d0 + 0x58 × pad: the pressed (edge) word +0xc and the
held word +8, from which the list handler derives its repeat. After every task frame
the test asserts that the shared seed words 0x404460/0x404464 are unchanged and that
no store hit the key word of any main or debug record (`:111–118`, `KEY_WORDS` `:130`).

Button names are **Inferred** from the byte-swapped pad layout these masks follow
(0x40 cross, 0x20 circle, 0x10 triangle, 0x80 square, 0x100 select, 0x800 start,
0x2000/0x8000 right/left), matching `docs/menus.md:80`.

## 2. Pause menu entries and actions

Tables and records (16 bytes: key pointer, kind, value pointer, flags). Kinds: 0
action, 3 toggle, 4 slider, 5 disabled (drawn but skipped by the cursor), 8 comm
volume. Flags bit 0 hides a row. The selection is stored in the terminator's +4
word as `row | row << 8` (**Executed** `:336`; **Observed** 0x1a07b4–0x1a07c0).
All records are **Executed** reads (`check_tables`, `:139–172`). The reference is
`tools/ref_pause_menu.py:12–45`.

| Row | Key | Shown when (per frame, pass at 0x18cc4c–0x18cf94, second pass 0x18d2fc–0x18d4ec) | Accept action |
|---:|---|---|---|
| 0 | `menu_returntogame` | always | `pauseMenu_close`; `g_menuInputLockout` 0x41b4fc = 60 |
| 1 | `menu_recall` | hidden if `g_pvpModeB` 0x4f7120 or task `missionmenurun` (key 0x534958) runs; disabled (5) if a dialog is open, task `jumpgate` (key 0x5349e0) runs, local camera +0x34 ≠ 1, or (net game and the local slot's player is dead; 0x18d3c4–0x18d3f8) | `hudmsg_sendRecall(pad)` 0x1de138 (game message 3, `docs/spec/game-messages.md:295`) |
| 2 | `menu_loadgame` | disabled in a net game, in PvP mode B or in a medal mission (word 0x4f713c, test at 0x18d434) | `pauseMenu_close`; lockout 60; `memcard_requestLoad(pad, 1)` 0x2176e0 |
| 3 | `menu_levelwarp` | hidden unless `g_debugCheats` 0x4f8ee0 | sub-menu 1: table 0x44f508, filled by 0x18e40c |
| 4 | literal debug row | hidden unless `g_debugCheats` | byte 0x44f210 = 1: following frames run `debug_missionEditor` 0x1e31c0 instead of the list; the flag becomes the editor's result inverted |
| 5 | `menu_option` | always | `config_backup` 0x1e6428; sub-menu 2: options table 0x44f218 |
| 6 | `menu_kickplayers` | net game, `net_localIsFirstActive` (0x18ce18), not a medal mission (0x18ce28), at least two active slots; disabled if a dialog is open (that case **Observed** only, 0x18ceb4). Prior: `docs/issues/online-quality.md:78–81` | sub-menu 4: table 0x44f4a8 rebuilt with every active slot except `net_firstActiveSlot` (0x18dad8–0x18db30), cursor on row 1 |
| 7 | `menu_exitmission` | hidden in a level whose name contains the substring at 0x534330 (the hub), when `net_localIsFirstActive` is false, when the player record of `net_firstActiveSlot` is dead (0x18ccb0–0x18ccd4), or in PvP mode B; disabled if a dialog is open | confirmation state 1 (§6) |
| 8 | `menu_exitgame` | always | confirmation state 2 (§6) |

**Executed:** nineteen visibility fixtures (`VISIBILITY`, `:263–290`) and every row's
accept (`check_main_accept`, `:310–394`, with the argument checks at `:322–336`).
The cause fixtures separate each condition:

- The task stub answers 1 for one name key per case (`:243`, `:277–279`): only
  `missionmenurun` hides recall, and only `jumpgate` disables it.
- The medal word 0x4f713c = 1 disables load offline. For a two-player host it hides
  kick (`:280–282`).
- One record is dead per case, with local pad 1 and `net_firstActiveSlot` 0
  (`:283–290`). A dead slot 0 hides exit mission, offline and online. A dead slot 1
  (the local slot) disables recall online only and leaves exit mission shown. The
  fixture decouples `net_localIsFirstActive` from the slot numbers so that the record
  each test reads can be seen. In a real session the first active slot is the host,
  and only the host passes the `net_localIsFirstActive` test.
- Kick with four players, first active slot 1 and local pad 1 lists slots 0, 2 and 3.
  Each row points at that player's record, the slot bytes are 0x7d8a18[1..3], and row
  4 is the terminator (`:338–345`). Prior research (`online-quality.md:83`) agrees:
  "the other active players".

A cursor left on a hidden or disabled row is moved to row 0 by the list handler
before dispatch, and that accept acts as row 0 (`:356–366`). Hide bits for rows
3 and 4 are only ever set, never cleared (**Observed** 0x18cf0c–0x18cf84). The other
rows recompute each frame.

The debug table 0x44f458 replaces the main table when `g_debugCheats` is set and the
lockstep slot-0 held word 0x41bfe0 is exactly 0x803 (**Executed** `:175–230`). Its
rows are return, level warp, `menu_invulnerability` (toggle of 0x44f20c, **Executed**
`:375–383`) and a literal row that calls `pauseDebug_sweepObjects` 0x18c7bc
(**Executed** `:368–374`).

**Save compare.** The accept dispatch jumps through table 0x534ae0 by sub-menu. Its
five words are **Executed** reads (`:170–171`). Sub 0 enters the key chain at
0x18d8c8; subs 1–4 go to 0x18dce0, 0x18dd80, 0x18ddf4 and 0x18de04. The chain compares
the row key with `menu_savegame` (key 0x534a88; `strcmp` called at 0x18d934, block
0x18d928–0x18d93c). On a match it calls `memcard_requestSave(pad)` from 0x18d944.
Prior notes cite the same compare as 0x18d92c (`docs/ui.md:95`,
`docs/issues/sync-breakers.md:588–589`); that is the address of its key load.
**Executed** with a planted key (`:346–355`): a main record carrying 0x534a88 reaches
`memcard_requestSave(pad)` from 0x18d944.

**Inferred**: the save branch is unreachable in shipped play. The basis is limited to
three things. No main or debug record has that key (`check_tables`, **Executed** read).
Only sub 0 runs the chain, and sub 0 shows only the main or debug table (open, cancel
and return all install 0x44f3b8 or 0x44f458). No executed frame stored into a main or
debug key word (`KEY_WORDS`). The sub-tables do get run-time keys (kick rows point at
player records, controller rows at fitted names, the level-warp list is **Unknown**),
but sub 1–4 accepts never reach this chain. The same chain also compares
`menu_moremenu`, `menu_changeplayers` and a literal shop row (**Observed** 0x18dcac,
0x18d45c, 0x18db94); no installed table has those keys either.

Sub-menus (word 0x44fa6c; `SUBMENU_TABLE`, `ref_pause_menu.py:48`), **Executed**
`check_submenus` `:456–556`:

| Sub | Table | Accept | Cancel |
|---:|---|---|---|
| 0 | main 0x44f3b8 | §2 table | `pauseMenu_close`, lockout 60 (`:486–489`) |
| 1 | level list 0x44f508 | offline `hudmsg_sendLoadLevel` 0x1de598, online `hudmsg_sendNewWorld` 0x1d9250, with the chosen row's key (a distinct planted key pointer, `:526–543`); row kept in 0x44fa74; nothing during a cutscene 0x44fcd0 (`:544–552`) | back to sub 0 |
| 2 | options 0x44f218 | `menu_controls` → sub 3; `menu_comm` → sub 5; toggles/sliders are edited by the list handler (`docs/options-menu.md`) | sub 0x33 (§5) |
| 3 | controller slots 0x44f368 | `frontend_openControlConfig(row)` 0x1e2510 | back to sub 2 |
| 4 | kick list 0x44f4a8 | `net_kickPeer(slot byte 0x7d8a18[row])` 0x131cb8, then close; no confirmation (`:509–525`) | back to sub 0 |
| 5 | comm 0x44f308 | rows edited in place | back to sub 2 |

## 3. Opening and closing

**Executed** `check_poll` (`:622–664`), the run task `warpMenu` 0x18e00c (registered by
`main`, `docs/mainloop.md:145`). It walks the player slots. For a slot where
`net_isLocalSlot` holds and the **lockstep** pad edge 0x41bfe4 + 0x58 × slot has bit
0x800, it toggles `g_pauseMenuOpen` 0x44f208:

- closed → `pauseMenu_open(slot)`;
- open on the main table → `pauseMenu_close`, stop stream 2 if playing, then
  `config_commitOptions(0,0,0)` (0x18e2cc–0x18e2f8). With the original commit
  followed (`:816–830`), that call requests a card config save
  (`memcard_requestConfigSave` 0x217bdc, called at 0x1e6b2c) only when a live option
  differs from the image. With no difference it requests nothing;
- open on any other table → nothing (start does not leave a sub-menu).

Opening is refused while `game_isFrozen` 0x1ebdf8 returns nonzero, while
`memcard_isBusy`, for a non-local slot, and offline while the local player is dead or
a dialog is open (a dead player may open it online). Closing still works while frozen.
**Observed** further gates before the pad loop (0x18e014–0x18e1e8): display-list head
room ≥ 3000, `g_warmupFrames` 0x506048, `g_recallCountdown` 0x41b51d,
`g_localMenuOpen` 0x41b69d, the cutscene byte 0x44fcd0, jump-gate travel, 0x4f66c8,
local camera mode, PvP/medal and `missionmenurun` host tests. The controller-removed
notice also calls `pauseMenu_open` (0x1db678, **Observed**).

`pauseMenu_open(pad)` 0x18e334, **Executed** (`:175–206`, five fixtures, with
sentinels): it stores pad → 0x7d8a10 (planted 0xEE) and calls
`hudmsg_sendMenuState(pad,1,0)`. Offline only, it sets 0x44fa80 = 1 and `g_paused` = 1.
Online, a planted `g_paused` = 1 and 0x44fa80 = 0 survive, and the recorded writes
contain neither address. It installs the main or debug table at 0x44fa70 (planted 0),
calls `menuList_setSelection(table,0)`, clears the sub word (planted 7) and calls
`ui_startPulse(0)`. It sets `g_pauseMenuOpen` and 0x44fa78, then calls
`task_add(0x18cc08, 0x34, "pauseMenu", 1)`.
`pauseMenu_close` 0x18df90 (`:207–228`): if 0x44fa78 is set, it clears
`g_pauseMenuOpen` and the confirmation byte (planted 2). Offline only, it clears
`g_paused` and 0x44fa80. Online, neither address is in the recorded writes and the
planted `g_paused` = 1 survives. It clears 0x44fa78, calls
`hudmsg_sendMenuState(localSlot,0,0)` and `task_remove(0x18cc08)`. A second close does
nothing.

Each frame (`pauseMenu_task`), **Observed** order with the executed parts marked:
skip everything while `frontend_controlConfigRun` is active (0x4f709c ≠ 0) or the
card state is not −1 (0x18cfd4–0x18d004). Then the exit confirmation (§6), the editor
flag, the leave-options query (§5), the visibility passes, `menuList_draw(320,240,…)`
0x18d5cc (geometry: `docs/options-menu.md` for table 0x44f218), the footer key
0x534a08 (options) or 0x534a20 (others) at (320,412), and `menuList_handleInput` with
the raw pad. After that come the audio preview, `music_applyVolume` and
`audio_sendVolumes` every frame (**Executed** `:558–565`). Then the accept dispatch
(confirm edge, with accept sound) and the cancel dispatch (cancel edge, with back sound).

## 4. Where the other in-play screens live

| Screen | Opened by | Evidence |
|---|---|---|
| Inventory (bags, pages 0–2) | `hud_run` 0x1db870 (run task): raw-pad pressed word +0xc bit 0x100 with held word +8 bit 0x80 clear, then the HUD gates 0x1db96c–0x1dbacc (local menu open 0x41b69d, pause menu open, frozen, camera, cutscene, …) → `menu_openInventory(slot, 0)` | **Executed** here `check_inventory` `:696–755`: edge, held, pause-menu-open and frozen. The 14 HUD gates, including the local-menu-open gate, are **Executed** one by one in `t3/research-hud-inputs` 0dc311c `docs/spec/hud-live-producers.md:231–239`, not planted here |
| Stats sheet (page 3) | L1/R1 page change on the same panel; `stats_screen` mode 0 | `t3/research-quest-log` `docs/spec/quest-log.md:62–66` |
| Quest log (page 4) | page 4 of the same panel (`stats_screen` mode 1) | `docs/spec/quest-log.md:60–72` (L1/R1 change page per `docs/issues/live-rig.md` §18.4) |
| Level-up page (page 5): stat and skill points | same press while acknowledged level +0x58 < earned level +0x59 → `menu_openInventory(slot, 1)`, which sets panel +0x50 (0x4f4090) = 5 | **Executed** `:709–740`; stat points need screen argument 2 (`t3/research-levelup` 98a8a47 `docs/spec/levelup.md:64–76`); skills `skills_screen` 0x1d4660 (`levelup.md:92–115`) |
| Save | save-point object `Savepoint_run` → `memcard_requestSave` 0x2175b4 (call at 0x28dc68; `save_game` also lists it as a caller); script `saveGame` 0x146c04 → `memcard_requestSave` (call 0x146c60); script `saveCheckPoint` 0x142a40 → `save_game(0,0,1)` 0x218128 (call 0x142a5c); save-screen reopen 0x2192f4 → `memcard_requestSave`. End of campaign: script `endGame` 0x146ad4 → `memcard_requestEndGameSave(0,1)` 0x217c38 (call 0x146ae0), and `saveEndConfig` 0x146c78 → `memcard_requestConfigSave` 0x217bdc (call 0x146d40; config image only). The pause menu's `menu_savegame` branch (0x18d944) is **Inferred** unreachable (§2) | **Observed** call sites; `docs/issues/sync-breakers.md:609–610`; `docs/script.md:642–647`; screen flow `t3/research-save-screen` `docs/save-screen.md:22–31`, `:246–256`. The full caller set of `memcard_requestSave` and `save_game` was not re-searched here |
| Load | pause row 2 → `memcard_requestLoad(pad,1)` | **Executed** `:328–329`; screen `docs/save-screen.md:251–256` |
| Map | the HUD minimap's map button cycles mode 0 (big centred map), 1 (corner) and 2 (hidden) (§4.1) | **Executed** `check_minimap` `:833–946` |
| Mission chooser | `missionMenu_open` 0x231520 from a hub trigger | `docs/spec/quest-log.md:54–58` |

### 4.1 Map (minimap modes)

There is no separate map screen and no pause row for it. The map is drawn by
`minimap_draw` 0x1e42e0 (draw-world path). Prior: `docs/ui.md:391` and
`symbols/ui.tsv:171` (raw pads cycle the mode); 0dc311c `hud-input-producers.md:89`;
1ed740a `hud-dynamic.md:340–352` (mode tables executed).

- **Input loop** (0x1e4398–0x1e45d8, **Executed**). For every slot below the player
  count, the loop reads that slot's raw pad and its configured map-button mask
  0x41b9e0[slot]. The mask is one of the nine per-port controller-config words
  (`symbols/drawsim.tsv:4`). The test plants a synthetic mask. Offline, a slot is skipped
  without an object or when object +0xc has bit 8. Online, every slot is read, even
  with no object (`:895–909`). The loop is skipped while frozen or in a cutscene. A
  press edge sets the slot's pending word 0x4f8680[slot] (0x1e4424). On a later frame
  with the button no longer held, a pending press clears and advances
  `g_minimapMode` = (mode + 1) mod 3 (0x1e456c–0x1e45b4). The test sees 0 → 1 → 2 → 0
  over three press/release pairs, with the only store at 0x1e45b4 (`:866–874`).
  Press and release in the same frame cycles at once, and another bit does nothing
  (`:875–879`).
- **Zoom** (**Executed** `:880–894`): while the button is held, a camera-stick value
  (raw pad +0x20) above 0.9 multiplies `0x4f71a0` by 1/1.01 and below −0.9 multiplies it
  by 1.01, every frame. Either one also clears the pending press, so that release does
  not change the mode. A stick of 0.85 neither zooms nor cancels. While held, the zoom
  is clamped to [0.5, 2.0]; without the button an out-of-range zoom is left alone.
- **Modes** (`MINIMAP_MODES`, `ref_pause_menu.py:122–137`; **Executed**
  `minimap_applyMode` `:934–946` and the projector call `:910–924`): with the
  current floats at the target, `minimap_draw` calls the projector 0x168cac from
  0x1e4d00 with x, y, scale × zoom, half-width and half-height in f12–f16.

  | Mode | 1 player | 2+ players |
  |---:|---|---|
  | 0 | (0, 0), scale 0.9, half-size 320 × 224 | same |
  | 1 | (200, −120), scale 0.7, 120 × 100 | (−240, 140), 0.7, 120 × 100 |
  | 2 | (180, −120), scale 0, 0 × 0 | (−240, 140), 0, 0 × 0 |

  The offsets and sizes chase the target by a quarter of the gap per drawn frame
  (`:925–933`: from (100, −100, 120, 100) toward mode 0 the next frame has
  (75, −75, 170, 131)). **Inferred:** mode 0 is a full-screen map. Its half-size
  320 × 224 centred at (0, 0) spans the 640 × 448 frame. How the projector rasterises it
  is not executed here (0dc311c executes the projector in `difftest_hud_minimap.py`).
  Mode 2 hides the map: scale and size 0.
- `g_minimapMode` is per machine and is written into the save file (`docs/ui.md:391`;
  `docs/spec/levelup.md:367` on 8d38a0b restores it in `save_load`).

### 4.2 Opening the inventory

`menu_openInventory` 0x1c15c8 is **Executed** offline and online, for mode 0 slot 0,
mode 1 slot 0 and mode 1 slot 1 (`:709–740`, with sentinels). It does these things:

- `g_localMenuOpen` 0x41b69d = 1;
- record +0x4a58 = 0 (planted 0x5A5A5A5A);
- `g_paused` = 1 **offline only**, stored at 0x1c176c. Online, a planted 1 survives and
  no store to 0x41b4f4 is recorded;
- `hudmsg_sendMenuState(slot,1,0)`;
- tasks 0x1c56a8 (`inventory_runTask`) and 0x1c1108, each priority 0x32, flag 1.

Mode 1 also sends one game message (inventory message 9, `docs/spec/levelup.md:43–44`).
It stores the **slot** at record +0xed (0x1c183c) and 0 at +0xee (0x1c1840): slot 1
stores 1. It also sets panel +0x50 (0x4f4090) = 5, the level-up page (0x1c1834). Mode 0
stores none of these. This matches 0dc311c `hud-live-producers.md:253–255` and 8d38a0b
`levelup.md:421–422`.

0x1c52dc (`inventory_close`) stores `g_paused` = 0 at 0x1c530c in both network modes
(**Executed** `:741–755`; `docs/ui.md:277` P3).

### 4.3 Inventory and equipment flow

From `docs/spec/inventory-screen.md:149–163` (4a8a78a) and `docs/menus.md` §2
(**Executed** there, not rerun here): in inventory mode 2 on a matched cell, confirm
(0x40) sends equip (inventory message 1, `invmsg_sendEquip` 0x1c5800), or unequip
(message 2, 0x1c5840) when `inventory_isEquipped` 0x1c41d8 is true. An item with flag
bit 35 starts a drag (panel +0x58/+0x64/+0x68/+0x6c) instead. Triangle (0x10) sends
drop (message 0, `invmsg_sendDrop` 0x1c59d0). Equip wins if both are pressed. The
message handlers (`docs/spec/game-messages.md`) change the bags and the equipment
pointers at record +0x43f0. **There is no "use" action in the inventory screen.**
Potions are used from the HUD quick slots (`Player_usePotion` 0x1b9fcc;
`t3/research-hud-inputs` `docs/spec/hud-quickslots.md`).

Page 3 is the read-only stats sheet. Stat points and skill points are both spent only
on page 5, the level-up page, which `menu_openInventory(slot, 1)` opens
(`levelup.md:64–76` stat-point screen argument 2, "wrong page … suppresses the send";
`:92–115` skills).

## 5. Options state and where it is stored

Values, kinds and live addresses of the 14 option rows are in `docs/options-menu.md`
(Reachability and records) and `tools/ref_options_menu.py`: brightness 0x44fd80, music
0x4f8944, effects 0x4f8940 (sliders in steps of 1/120), combat camera 0x4f845c, reverse
yaw 0x4f8460, vibration 0x41bfb0, stereo 0x4f8948, blood 0x44fdc0, subtitles 0x44fcf4,
damage numbers 0x44fcf8, chat 0x50391c, markers 0x4f8458 (toggles). New here:

- **Comm sub-list** 0x44f308 (**Executed** reads `:139–172`): `menu_commenable`
  toggle 0x505b00, `menu_commecho` toggle 0x505afc, `menu_commplay` slider 0x505af4,
  `menu_commthresh` slider 0x505af0, `menu_commvolume` kind 8 at 0x505af8. These are
  config image +0xd0, +0xd4, +0xcc and +0xc8 (`docs/options-menu.md`, Applying values).
  How kind 8 is edited, and whether 0x505af8 is saved, is **Unknown**.
- **Controls** (row 3) opens the controller-slot chooser. The chooser is rebuilt every
  frame from `ui_fitText` of each player record into 0x4f3ec8 + 32 × row (**Executed**
  `:465–474`). Choosing a row calls `frontend_openControlConfig(row)`. The remap screen
  then runs from the pause task while 0x4f709c is nonzero (**Observed**
  0x18cfd8–0x18cfec; its flow is **Unknown**, as in `docs/options-menu.md`). The
  controls row is disabled (kind 5) in a net game (**Observed** 0x18d364–0x18d3a4).
- **Triangle in the options list** (edge 0x10, test at 0x18d830) calls 0x222b10
  (**Executed** `:610–618`). That calls `memcard_cancel` 0x21e614 and
  `memcard_setState(10)`, and clears browser stage 0x88d3e4. **Executed** chain
  (`:756–781`): `memcard_setState` stores 10 in the dispatcher's state word 0x88d3a0.
  One run of the card dispatcher 0x2189e0 then jumps through word 0x53f0b8 to the
  state-10 case and calls `memcard_optionsScreen` 0x222b40 from 0x218ac8. That screen
  copies a card config into the live globals at 0x222d5c (`docs/options-menu.md`).
  Its prompts and flow are **Unknown** here.
- **Audio preview** (**Executed** `:558–621`; mask and bound **Observed** at the
  addresses given):
  - A changed music value tests stream 2 (`0x211b20(2)` at 0x18d784). If status bit
    0x20 is clear it plays `music_playGlobal(0x534a60, 0x41)`. In either case it zeroes
    the idle counter 0x44fa7c (0x18d7ac).
  - The counter is then incremented. When the new value is 241 or more (`slti 0xf1`,
    0x18d7c0), it tests stream 2 again (0x18d7cc) and, if status bit 0x40 is set, stops
    stream 2 (0x18d7e0). Planted 240 stops and planted 239 does not.
  - A changed effects value plays a sample (0x18d76c) when `frame & 7 == 0` for the
    frame word 0x44fdd0 (`andi 7` at 0x18d740). Frames 8 and 16 play; frames 2, 4 and 9
    do not.
  - **Inferred:** bit 0x20 means "stream busy" and bit 0x40 means "stream playing".
    The test scripts both status values; the meaning of the bits is not checked
    against the IOP.
  - `music_applyVolume` and `audio_sendVolumes` run every frame the menu is open, so a
    slider change is heard at once.
- **Leaving options** (cancel in sub 2 → sub 0x33). Two executed forms:
  1. Routing with `config_commitOptions` as a **stub** whose query result is scripted
     to 0, 1 or 2 (`:490–508`, the `R.LEAVE_OPTIONS` cases plus a result of 2). Only the
     call arguments, the message box and the sub/table result are checked there.
  2. The **original** `config_commitOptions` (`check_options_commit`, `:783–815`). The
     image is synchronised first, then zero, one or two live values are changed. The
     direct query returns 0, 1 or 2.

  Executed result: the next frame calls `config_commitOptions(0,1,0)` (query). With no
  differences it commits with `(0,0,1)` (in memory). It draws no box and requests no
  card save, and it returns to the main table and sub 0. With differences it draws
  `hud_drawMessageBox` (title/body keys at 0x5349b0/0x5349c8) until an answer:
  - confirm commits `(0,0,0)`, which copies the changed value into the image and
    requests the card config save (`memcard_requestConfigSave` 0x217bdc, one call from
    0x1e6b2c inside the commit);
  - cancel commits `(0,0,1)`, with no card request;
  - with no answer the sub stays 0x33 and nothing is requested.

  Start on the main list also commits `(0,0,0)`. That requests the card save only if
  a live value differs (§3).
- **Storage:** `config_commitOptions` copies live values into the 760-byte image
  `g_savedConfig` 0x4f8f38 (layout in `docs/options-menu.md`, Applying values;
  `t3/research-saves` `docs/save-format.md`). A card save writes it as the config file.
  The image is separate from slot saves. `config_backup` on entering options is the
  restore point. The commit also rewrites all four per-slot button tables from the
  saved controller rows. That is the multiplayer hazard U1
  (`docs/issues/draw-sim-leaks.md:57`).

## 6. Exit confirmation

**Executed** `check_confirm` (`:396–442`, ten cases). While byte 0x44fa68 is nonzero,
the task draws only `hud_confirmBox` 0x1dadc0 and skips the list. Result 1 clears the
state, result 2 accepts, and other results wait.

| State | Condition (0x18d038–0x18d074) | Prompt key | On accept |
|---:|---|---|---|
| 2 (exit game) | — | 0x534968 | offline `g_sessionExitCode` 0x41b508 = 1; online `g_netExitCountdown` 0x4f6948 = 30; then close |
| 1 (exit mission) | not a hub level, no PvP mode B, local slot = first active slot | 0x534990 | `hudmsg_sendExitCountdown` 0x1de25c (game message 8); close |
| 1 | otherwise, offline (executed for the hub, PvP mode B, and a non-first local slot) | 0x534968 | as state 2 offline |
| 1 | otherwise, online (executed for a non-first local slot and PvP mode B) | 0x534978 | as state 2 online |

Exit code 1 ends the session and restarts the front end in mode 0. This is
**Observed** in the reader, not executed here: `mainloop_runSession` 0x3234d4 and
`main` 0x32423c (`docs/mainloop.md:217`, `:608`; `symbols/mainloop.tsv:53`). Script
`exitToMainMenu` stores the same value (`docs/script.md:643`).

## 7. Pause semantics

- **Offline**, `pauseMenu_open` and `menu_openInventory` (also the shop, card screens,
  help boxes and mission menu, `docs/ui.md:277–305`) set `g_paused`.
  `game_isFrozen` 0x1ebdf8 returns it (**Executed** both modes, `:666–680`). While it is
  set, `runObjects` skips every object's run call (`docs/spec/object-system.md:390–405`),
  `tasks_run` does not advance `g_simFrame` (`:505–520`), and `Player_run` skips input
  (`docs/spec/player-tick.md:153`). Run and draw tasks still execute. The pause task
  itself is a draw task (priority 0x34). The HUD inventory button and a new pause press
  are refused while frozen (**Executed** `:696–708`, `:640–664`). The minimap's
  mode/zoom input is skipped while frozen (**Executed** `:895–909`). Opening plays and
  stops nothing (**Executed** exact call list `:202–204`). Audio streams keep playing and
  volumes are pushed each frame.
- **Returning** via return to game, load or cancel sets `g_menuInputLockout` 0x41b4fc =
  60, which `Player_run` tests (`docs/spec/player-tick.md:153`). Once per `tasks_run`
  call, if the lockout is positive and the hold flag 0x41b500 is clear, it becomes 0
  when no pad button is held and is otherwise decremented
  (`docs/spec/object-system.md:520–521`). In a net game `tasks_run` zeroes it first on
  every tick (`:507`), so the lockout only has an effect offline. **Inferred**
  purpose: the closing press does not reach the character.
- **Online**, `g_paused` is not stored by the pause menu or the inventory open
  (**Executed**: a planted 1 survives and the recorded writes have no store to
  0x41b4f4, `:175–230`, `:709–740`), so the world keeps simulating. Only the menu-state
  message is sent. `pauseMenu_isOpen` 0x18cbfc is read by the jump-gate and mission
  menus, which then lock the local pad (U2, `docs/issues/live-rig.md:1850–1880`), and by
  prediction (`docs/engine.md:566`). Whether the local character keeps acting on
  lockstep input while the pause list takes the raw pad is **Unknown**.
  `docs/issues/online-quality.md:92` shows the menus do not stall the session.

## 8. Client-implementable list

1. Run a per-frame start-button poll on each local slot's lockstep pad (edge 0x800).
   Apply the §3 open gates. Toggle open/closed. Closing from the main list commits
   options with `(0,0,0)`, which requests a card config save only when a live option
   differs from the image. Start does nothing inside a sub-menu.
2. Open: remember the pad index and send menu-state (slot,1). Offline, set the pause
   flag. Install the main table, or the debug table for cheats + held 0x803. Cursor
   row 0, sub 0, pulse 0. Close: the reverse, idempotent; online never touch the
   pause flag.
3. Recompute the main rows' visibility and disabled kinds every frame with the §2 rules
   (including the medal-mission load/kick rules). Skip hidden and kind-5 rows in
   navigation, and snap an invalid cursor to row 0. Store selection as `row | row << 8`.
4. Dispatch accept by row key exactly as §2. Return, load and cancel set the
   60-frame input lockout (offline effect only). Recall sends game message 3. Load
   opens the load browser with flag 1. Kick needs no confirmation, is offered only to
   the host, and lists every active slot except the first active one.
5. Exit flows through the two-state confirmation in §6. Exit game ends the session
   offline (exit code 1) or starts the 30-frame net exit countdown. Exit mission sends
   message 8 when the host is in a mission, outside the hub and PvP mode B.
6. Options: reuse the front-end list model (`docs/options-menu.md`): kinds 4/3, the
   1/120 step, clamp, and live readers. Back it up on entry. Add the comm sub-list
   (kinds 3/4/8), the per-player controller chooser that opens the remap screen, and
   triangle → card options screen (card state 10). Leaving runs the
   query/confirm/commit sequence in §5. Only a confirmed commit with differences
   requests the card save.
7. While options are open, push volumes every frame. When music changes, preview it
   on stream 2 unless that stream reports busy (status bit 0x20). Stop stream 2 if it is
   still playing (bit 0x40) once more than 240 frames have passed since the last
   change. Play an effects sample on frames where `frame & 7 == 0` while effects change.
8. Keep inventory/stats/quests/skills on the HUD panel. Select (0x100 pressed) opens
   it and held square (0x80) blocks it. The opening page is the level-up page (page 5)
   when a level is unacknowledged. Stat and skill points are spent only there. Equip,
   unequip, drag and drop go as in §4.3. There is no use action there, and potions stay
   on the quick slots.
9. Map: implement the HUD minimap modes of §4.1, not a pause row. Each local slot's map
   button cycles 0 (big centred map, half-size 320 × 224) → 1 (corner) → 2 (hidden) on
   release. Held with the camera stick past ±0.9, it zooms by 1.01 per frame within
   [0.5, 2.0] instead. Ease the offsets and sizes by a quarter step per frame. Skip
   the input while frozen or in a cutscene. Save the mode with the game.
10. Saving is at save points, the script commands `saveGame` and `saveCheckPoint`, and
    the end-of-campaign saves (`endGame`, `saveEndConfig`). The pause menu must not
    offer save.
11. Pause semantics: offline, freeze object runs and the sim frame counter while menus
    are up. Keep draw/run tasks and audio alive. Online, never freeze. Treat a local
    pause menu as display-only and keep U1/U2 in mind (`docs/issues/draw-sim-leaks.md`).

## 9. Unknown

- Pixel geometry of the pause list beyond the call arguments recorded here, its
  frame art, the footer and pulse rendering, and the minimap projector's raster output.
- Comm kind 8 editing, the controller remap screen flow, and the card options screen
  (state 10) flow.
- The level-warp list builder 0x18e40c's contents (debug only, not executed beyond
  the call), and `debug_missionEditor`'s pages.
- Whether a net-game player keeps acting on lockstep input while their pause list
  is open.
- The roles of 0x1c1108 and of the extra stores made by 0x1c52dc (0x4039c0, 0x41b4f8,
  0x4d8a08). `menu_openInventory` stores the same three addresses on opening (recorded
  writes at 0x1c16a8–0x1c16b4).
- The default physical button behind the map mask 0x41b9e0.

## 10. Validation (2026-11-09, Mac mini, serial)

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_pause_menu.py local/SLUS_209.73`:
**274 checks passed on each of seeds 20973 and 7** (tables 26, open/close 90,
visibility 19, main accept 28, confirmation 10, sub-menus 20, audio preview 13, poll 12,
freeze 4, inventory 14, card options 5, options commit 7, minimap 26).
`tools/test_ref_pause_menu.py` has 6 static reference tests. Reruns and the unit suite
are listed in `work/cursor-report.md`. Logs are ignored files under `local/`.
