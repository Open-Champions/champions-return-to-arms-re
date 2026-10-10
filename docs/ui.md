# ui — inventory, shop, character sheet, HUD, front end, game state (0x1c0000–0x1e8000)

222 functions. Read from the decompile and the disassembly only; nothing here was seen on a
running game. Names are in `symbols/ui.tsv`. Unless a line says *Inferred* or *Unknown*, a
statement is *Observed* at the address given.

## What is in the range

The static-constructor table at 0x3e99c8 gives the source-file boundaries (each file with
global objects ends with a constructor/destructor pair):

| Range | Unit | Contents |
|---|---|---|
| 0x1c00b8–0x1c5d28 | inventory | inventory panels, give/remove/equip/drop item, message senders. The unit starts in the player area (its message handler is 0x1bfdb0) |
| 0x1c5d28–0x1d19c8 | shop | shop messages, shop task, the item-list panel shared by inventory and shop, workshop (gem combining), store stock generation, `ShopDaemon` |
| 0x1d19c8–0x1d7778 | character sheet | stats page, skill tree page, level up, experience, quest list |
| 0x1d7778–0x1d8ca0 | `Weather` | a level object (vtable 0x512890); not UI |
| 0x1d8ca0–0x1e08f0 | HUD | game-message handler, status bars, messages, help boxes, gold counter, spell selector, compass, bust, fade |
| 0x1e08f0–0x1e8000 | game (front part of the unit holding "game.cc" asserts) | front-end menu, controller configuration, minimap, level load and clear, core task registration, alive-player list, death handling |

### Tasks registered here

`task_add(fn, priority, name, isDraw)`. A *run* task runs once per simulated frame (inside
the lockstep tick in a net game); a *draw* task runs once per displayed frame.

| Task name | Function | Kind | Priority | Registered by |
|---|---|---|---|---|
| HUD Run | `hud_run` 0x1db870 | run | 50 | `hud_addTasks` 0x1dc1d0 |
| HUD Draw | 0x1dbc48 (`hud_netStatusDraw` in names.tsv; it is the whole HUD draw task) | draw | 51 | same |
| inventoryRun | `inventory_runTask` 0x1c56a8 | **draw** | 50 | `menu_openInventory` 0x1c15c8 |
| inventoryDraw | `inventory_drawTask` 0x1c1108 | draw | 50 | same |
| shop | `shop_task` 0x1c6068 | draw | 50 | `shop_openOrStock` 0x1c7af8 |
| stats | `stats_task` 0x1d1bc0 | draw | 50 | only the unreferenced `stats_open` 0x1d2eb8; `stats_screen` removes it. The stats page is normally drawn inside the inventory panel |
| HelpMessage | `help_task` 0x1dcc78 | draw | 50 | `help_addTask` 0x1dd240 |
| frontend | `frontend_run` 0x1e08f0 | run | 25 | `frontend_start` 0x1e1f34 |
| camera | 0x1ebbe0 | run | 11 | `game_addCoreTasks` 0x1e6cc0 |
| drawWorld | 0x1ebc18 | draw | 30 | same |

So every menu "run" function except the HUD's and the front end's is a draw-type task. They
read `g_rawPads` (0x4028d0, this machine's controllers), not the lockstep pads, and are
supposed to change the game only by sending game messages. The pause menu ("pauseMenu",
draw, priority 52, 0x18cc08) and the mission menu (run, priority 20, 0x2316fc) live in other
areas; the mission menu is the one menu that is driven by lockstep pads.

## Game-message channels

`net_registerMsgHandler` 0x13da98 returns a small channel id for a handler; `net_sendGameMsg
(channel, buf, len)` queues a message that every machine's handler receives in the lockstep
tick. First byte = message type. Four channels belong to this area.

### Inventory channel (id at 0x866d18, handler `invmsg_dispatch` 0x1bfdb0)

| Type | Bytes after the type | Handler | Meaning |
|---|---|---|---|
| 0 | slot, u16, item index u32, u16, bag, 2 bytes | `inventory_dropItem` 0x1c4310 | drop to the ground |
| 1 | flag, slot u16, item address u32 | `inventory_equipItem` 0x1c27c0 | equip |
| 2 | 0, slot u16, item address u32 | `inventory_unequipItem` 0x1c2f20 | unequip |
| 4 | panel, slot, levelUp | `inventory_onJoinPanel` 0x1c0360 | a player takes an inventory panel |
| 5 | slot, weapon class | inline | sets record +0x4a86, recalculates |
| 6 | slot, stat u16 | `inventory_onStatPoint` 0x1c2548 | spend a stat point (0–3), free raise (4–7), add a skill point (8) |
| 7 | slot, a, 0, value u32 | `inventory_onSkillPoint` 0x1c2648 | spend skill points |
| 8 | slot, 3 × u32 | `inventory_combineGems` 0x1ceeb8 | workshop combine |
| 9 | slot, level | inline | record +0x58 = level acknowledged |
| 10 | slot, 4 × u16 | `Player_usePotion` | potion |

"Item address" is the address of a 0x48-byte item record inside `g_players[slot]`. The table
is static, so the address is the same on every machine as long as the inventories are.

### Shop channel (id at 0x86a6a0, handler `shop_onMsg` 0x1c5d28)

| Type | Bytes | Meaning |
|---|---|---|
| 0 | slot, 0 u16, **address of a record in the sender's stock table** | buy → `shop_buy` 0x1d1240 |
| 1 | slot, u16, item index u32, u16, bag, 2 bytes | sell: adds a value computed from the item price and stack count to gold (0 for some item kinds), then `inventory_dropItem` with the same arguments as inventory message 0 |

### Game ("HUD") channel (id at `g_netGameConn` 0x86ac40, handler `hud_onMsg` 0x1d8ca0)

| Type | Sender | Effect in the handler |
|---|---|---|
| 0 | `hudmsg_sendQuickSlot` 0x1de06c | `hud_onQuickSlot`: record +0x4a84/+0x4a85 |
| 1 | `hudmsg_sendAssignSpell` 0x1de3ec | `hud_onAssignSpell`: ability records at +0x4440 |
| 2 | `hudmsg_sendMenuState` 0x1de0dc (net games only) | state ≠ 0: sets object flag 0x400000 on the player (and 0x800000 when state > 1), record +0x4bc8 = 0. State 0: `net_maskLocalButtons(slot, 60, 0xf0)`, record +0x4bc8 = 10, clears 0x800000 |
| 3 | `hudmsg_sendRecall` 0x1de138 | recall (0x18c230) unless a dialog or the mission menu is open |
| 4 | `hudmsg_sendPlayerLeft` 0x1de16c | "player left" message; kills that player's object |
| 5 | `hudmsg_sendSavepoint` 0x1de1a0 | passes the 32-bit value in the message to `Savepoint_startSavedEffect` 0x28cdc4 as an object address (see P8) |
| 6 | `hudmsg_sendDisconnectRequest` 0x1de1e0 | remote player asks to leave; revive someone if he was the only one alive; `net_disconnectPlayer` |
| 7 | `hudmsg_sendNewWorld` 0x1d9250 | pending level name ← string; closes the pause menu; `g_paused = 0` |
| 8 | `hudmsg_sendExitCountdown` 0x1de25c | exit countdown 0x4f694a = 240 (1 offline) |
| 9, 10 | 0x1de430, `net_sendChecksums` | character checksum exchange |
| 11 | `hudmsg_sendLoadLevel` 0x1de598 | 0x18cb80: pending level ← string, `g_paused = 0` |
| 12 | `hudmsg_sendMedalAck` 0x1de5ec | sets 0x4f7140 |
| 13 | `hudmsg_sendQuickCastWarn` 0x1de0a4 | HUD text |

### Null channel (id at 0x86aa60)

Its handler 0x1e01b0 is an empty function. `shop_close` sends on it in a net game
(`nullmsg_sendShopClosed` 0x1e0134); nothing happens on receipt.

## Data structures

### Player record fields touched by this area (`g_players` 0x4d8af0, 0x4c30 bytes each)

| Offset | Type | Meaning | How known |
|---|---|---|---|
| +0x00 | char[] | character name | printed by the HUD (0x1dbc48) and "player left" message |
| +0x50 | s32 | class index (row of the skill table 0x4ef530, 0xa88 bytes per class; this is the table `docs/data-tables.md` gives as `g_classPassiveTables` 0x4ef510 — 0x4ef530 is the part of each 0x38-byte row after its 0x20-byte name) | 0x1d436c |
| +0x58 | s8 | level the player has acknowledged in the level-up screen | msg 9 handler; `hud_run` compares it with +0x59 |
| +0x59 | s8 | level | `player_giveExp` 0x1d3150 |
| +0x5c | s32 | experience; thresholds at 0x41b558, cap at 0x41b698 | same |
| +0x78 | s32[4] | the four base stats | `inventory_onStatPoint` |
| +0xac / +0xb0 | float | hit points / maximum | level up refills; `save_game` tests > 0 |
| +0xc0 / +0xc4 | float | mana / maximum (*Inferred* from the refill pattern) | `player_giveExp` |
| +0xe4 | s32 | gold, capped at 99,999,999 | `shop_buy`, `hud_tickGold` |
| +0xe8 | s32 | skill points (1–5 per level by level band) | `player_giveExp` |
| +0xec | s8 | stat points (3 per level) | same |
| +0xed, +0xee | s8 | level-up screen bookkeeping (owner slot; "all stat points spent") | menu code only |
| +0x130 | item[64] | bag 0; item = 0x48 bytes, first word → static item definition (table 0x3f7650, 0x40 bytes per row), s16 stack count at +4, flag qword at +8 | `save_snapshotPlayer`, `inventory_countItemByName` |
| +0x1330 | s32 | bag 0 count; bags 1 and 2 follow at stride 0x1208 (+0x1338, +0x2540) | same |
| +0x41d0 | char[8][0x40] | quest list: title[0x20], text[0x20] | `quest_add` 0x1d386c |
| +0x43d0 | s32 | quest count | same |
| +0x43d8 | ptr | the player's object | everywhere |
| +0x43f0 | ptr[17] | equipped items (addresses into the bags) | `save_snapshotPlayer` |
| +0x4434, +0x4438, +0x443c | ptr | three more item pointers: +0x4434 and +0x4438 are the primary weapon of weapon set 0 and set 1, indexed by the active-set byte +0x4a7c, and +0x443c is the second weapon when dual wielding, as in `docs/player.md` (the earlier version inferred "ranged weapon / ammunition"; ammunition is equipment slot 8 at +0x4410) | `inventory_unrefItem`; `inventory_equipItem` 0x1c27c0, `Player_weaponSwapInput` 0x1bb718 |
| +0x4440 | 0x68-byte records | abilities / quick-cast assignments | `hud_onAssignSpell` |
| +0x4a58 | u32 | cleared when the inventory opens | `menu_openInventory` |
| +0x4a84, +0x4a85 | u8 | quick-slot selection | `hud_onQuickSlot` |
| +0x4a86 | u8 | weapon class of the weapon in hand | msg 5 |
| +0x4bc8 | u8 | set to 10 when a menu closes, 0 while open | `hud_onMsg` type 2 |

### Item-list panel (`g_itemPanels` 0x4f4040, 4 × 0x74 bytes)

One per on-screen inventory/shop column. Known words: +0x08/+0x0c initial 0x140/0x1c0,
+0x14..+0x28 and +0x3c/+0x40 cursor and scroll state (`menu_resetListState`), +0x34 owner
slot (−1 free), +0x44/+0x48 free-cursor position moved by the analogue stick, +0x4c state
(0 active, 2 idle), +0x50 current page (set to 5 for a level-up; *Inferred* meaning).
+0x30 and +0x58 are state words whose meaning is not established. The shop uses a second
pair at 0x86a4b0.

### Shop stock (`g_shopStock` 0x866e78)

Three lists (weapons, armour, other), each 64 × 0x48-byte item records followed by a count:
0x866e78 / count 0x868078, 0x868080 / 0x869280, 0x869288 / 0x86a488.

### Gold floaters (`g_goldFloaters` 0x86a918, 8 × 0x24)

Screen path for drawing at −0x18..−0x04 (from the local camera), +0x00 start frame
(`g_simFrame` 0x44fdcc), +0x04 amount, +0x08 slot, +0x09 off-screen flag. `hud_tickGold`
moves an entry to `g_goldPending[slot]` when `(frame − start) * 3 > 127` and then pays an
eighth of the pending amount into record +0xe4 each frame. The timing uses only the frame
counter, so it is the same on every machine although the path is not.

## How the pieces work

### Opening and closing the inventory

`hud_run` (run task) looks at each player's **raw** pad: start pressed and select not held,
no menu open on this machine, pause menu closed, game not frozen, camera in mode 1, no
cutscene, player alive, not mounted (object +0x540), no jump gate or mission menu, and
object flag 0x400000 clear. It then calls `menu_openInventory(slot, levelUpPending)`, whose
body runs only when the slot is local. That function sets `g_localMenuOpen`, the menu flags,
sends menu-state message 2 (net game) and registers the two inventory tasks. In an offline
game it also takes the menu mutex and sets `g_paused`.

`inventory_runTask` → `inventory_runPanel` → `itemList_update` → `itemList_input` (raw pad,
sends messages) and `itemList_draw`. `inventory_close` (0x1c5100) removes the tasks, sends
menu state 0 and message 5, and clears the flags.

### Shop

`shop_openOrStock(slot, 0, …)` opens the shop for a local slot. Stock is generated
separately: the session loop calls `shop_openOrStock(0, type, 1)` right after loading a
level named hub or hub2 (type 1), islgnome (2) or stobonus (3) (calls at 0x3230c4 and
0x3230f0). Generation fills the three lists with the item generators
`item_generateWithAffixes` 0x104ca4 and `item_generateFromSpecialTable` 0x104758 (both
draw from `g_randSeed`), seeds a few fixed items (arrows, potions), and sorts each
list by price. Price level comes from the quest variable `storeLevel` and the difficulty.

Buying: `itemList_input` → `shopmsg_sendBuy` sends the stock record's address;
`shop_onMsg` → `shop_buy` reads the record at that address, charges price × 0.6 (0.45 for
one item class, 1.0 for flagged items) if the player has the gold, and calls
`inventory_giveItem`.

### Character sheet

`stats_screen` 0x1d1db8 and `skills_screen` 0x1d4660 draw and read input in one function
each. Spending is by message 6 / 7. `player_giveExp` is simulation code (called by kills and
by script `givePlayerExp`): on each level it adds points, refills hit points and mana, and
shows the level-up message on the owner's machine only.

### HUD

`hud_run`: gold floaters, the pick-a-player list, HUD message timer, exit countdown, the
"single player left in a net game" timer, menu opening, a debug cheat (below).
The draw task draws everything and also owns the network exit logic: while
`g_netExitCountdown` (0x4f6948) runs it sends disconnect requests, and at the end it closes
menus, ends any cutscene, shuts the net session down and leaves the game loop. The same
exit path is taken after a long stall (counter 0x40279c above 1800, or 600 with the lost-
connection flag, when more than two players).

`hud_showMessage(text, frames, slot, force)` shows text only on the machine that owns
`slot` (−1 = all). `hud_showHelpMessage` and `hud_showPlayerNotice` open boxes that
`help_task` draws and dismisses.

### Front end and game setup

`frontend_run` is a state machine on `g_frontendState` (0x4f6b78) with the current menu
table in `g_frontendMenu`: 0 main menu, 1 normal / net game, 2 number of players, 3
difficulty, 4 game mode, 5 kill limit, 6 net host / client, 7–9 net game options (mode,
mission), 10 waiting for the lobby, 11 options, 12 per-player options, 14 "save config?"
prompt, 15 credits (states 7–12 *Inferred* from the menu tables they select). Offline setup writes `g_numPlayers`, `g_pvpModeA`, `g_pvpModeB`,
0x4f7124, the kill limit 0x4f8408 and `g_difficultyIdx`, then `frontend_startPlayerSelect`.
Net setup fills the settings block at 0x402a30 (0x14c bytes: +0 host flag, +2 difficulty,
+3 mode, +4 mission, +5 kill limit, +7 player count) and calls `frontend_startNetGame`
(0x1e21e0), which starts the launch transfer. While the launch flag 0x402793 is set,
`frontend_run` polls 0x135638; on success it sets `g_networkMode`, calls `game_resetState`,
clears `g_paused`, takes the player count from the settings block and zeroes the shared
seed through 0x13dce0. The lobby screens themselves are in the netlib area.

### Level load and clear

`game_loadLevel` 0x1e55c0 loads the level lumps, music and objects; midway (0x1e59c4) it
copies `g_randSeed` into `g_cosmeticSeed`. `game_clearLevel` 0x1e4e88 closes menus, pays
out pending gold (`hud_flushGold`), frees per-level data and clears `g_paused`.

## Per-machine state

### P1. Shop purchases read each machine's own stock table — Observed mechanism, Inferred consequence

- `shopmsg_sendBuy` (0x1c5f78, store at 0x1c6024) puts the **address** of the chosen stock
  record in the message. `shop_onMsg` (0x1c5d28) hands that address to `shop_buy`
  (0x1d1240), which reads price and item from the receiver's own `g_shopStock`.
- Stock generation (0x1c7af8, mode ≠ 0) makes three draws from `g_cosmeticSeed`
  (0x1c7ea0, 0x1c80c4, 0x1c8498). Each one, with probability 0.1, adds a call to the item
  generator 0x104758 (calls at 0x1c7f70, 0x1c8184, 0x1c855c), which draws from
  `g_randSeed` and appends an extra item before the list is sorted.
- So if two machines reach stock generation with different cosmetic seeds, they can (a)
  consume a different amount of the shared seed, which changes the sync hash at once, and
  (b) hold different lists, so the same address names different items and a purchase
  changes inventories and gold differently.
- *Unknown*: whether the cosmetic seeds do differ there. `game_loadLevel` sets the cosmetic
  seed equal to the shared seed during the load; afterwards the session loop calls
  `drawWorld` in a wait loop whose length depends on local loading (0x322998, loop on
  0x506048), and `drawWorld` reaches cosmetic-seed users by direct calls (0x16d0b8,
  0x16d360, 0x1876e0, 0x18ba18, 0x195400). Whether any of them fires during that loop needs
  a running game: compare 0x404460 on two machines at 0x3230c4.

### P2. A deferred script can run from draw code on one machine — Observed

`help_task` (draw task) calls `script_runPostAction` (0x1edac0) at 0x1dd1f0 when a
per-player notice box is dismissed, with no network test. The notice flag
(`g_playerNoticeOpen`, 0x41b518) is set only on the machine that owns the slot
(`hud_showPlayerNotice` 0x1d9954; raised by item-list errors and by `Player_usePotion`).
`script_runPostAction` runs and clears the script name stored by the script built-in
`postAction`, which 45 level scripts use to continue after a cutscene or dialog. If a
notice is dismissed while such a name is pending, that machine runs the script early and
outside the lockstep tick; the others run it at the normal point. (The second call, at
0x1dcf60 for the modal help box, is skipped in a net game.) *Unknown*: whether a notice can
be open while a post-action is pending; `net_closeLocalMenus` clears the notices
(`hud_resetNotices` 0x1e03c0) when a dialog starts.

### P3. The pause flag

Writers of `g_paused` (0x41b4f4), from `gxref`:

| Address | Function | Value | In a net game |
|---|---|---|---|
| 0x1c176c | `menu_openInventory` | 1 | not executed (offline test) |
| 0x1c530c | `inventory_close` | 0 | **yes, from local input**, no test |
| 0x1c876c | `shop_openOrStock` (open) | 1 | not executed |
| 0x1d0b7c | `shop_close` | 0 | not executed |
| 0x1d2f08 | `stats_open` | 1 | no test, but the function is unreferenced |
| 0x1d903c | `hud_onMsg` type 7 | 0 | yes, in lockstep (message) |
| 0x1dcce4 | `help_task` modal box | 1 | not executed |
| 0x1dcf84 | `help_task` dismiss | 0 | **yes, from the raw local pad in a draw task**, when no menu is open |
| 0x1e0b58, 0x1e1770, 0x1e1ad4 | `frontend_run` | 0 | game setup, before the simulation |
| 0x1e2034 | `frontend_start` | 0 | front end |
| 0x1e3bf0 | `frontend_startPlayerSelect` | 0 | front end |
| 0x1e50f8 | `game_clearLevel` | 0 | level change (every machine) |
| 0x21e868 / 0x21e8f4 | `memcard_pushPause` / `memcard_popPause` | 1 / old | not executed |
| 0x231988 | `missionMenu_run` open | 1 | not executed |
| 0x2320a8 | `missionMenu_run` close | 0 | yes, in lockstep (run task, lockstep pad) |
| 0x141800, 0x141c44 | script `runMedalSuccess` / `runMedalFail` | 1 | not executed |
| 0x146cc0 | script `saveEndConfig` | 1 | **yes**, in lockstep; the only place that pauses a net game |
| 0x18c498 | recall 0x18c230 | 0 | yes, in lockstep (message 3) |
| 0x18cbc4 | 0x18cb80 | 0 | yes, in lockstep (message 11) |
| 0x18dfcc | pause menu close 0x18df90 | 0 | not executed |
| 0x18e38c | pause menu open 0x18e334 | 1 | not executed |
| 0x27de70, 0x27e13c | jump gate 0x27dd74 | 1 / 0 | open: not executed; close: no test |
| 0x32356c | session loop exit | 0 | leaving the game |

So a net game is paused only by `saveEndConfig` (game completed). After that, the local
writers marked bold would un-pause one machine alone. *Inferred*: this cannot break
anything, because `saveEndConfig` goes on to call `net_dropAllRemotes` (0x13def8), which
ends the net session on that machine. While `g_paused` is 0 the bold writers store the
value it already has.

### P4. Player-record fields written by local menu code — Observed

- `menu_openInventory` 0x1c15c8 (local slot only): +0x4a58 = 0; with a level-up pending,
  +0xed = slot and +0xee = 0.
- `stats_screen` 0x1d1db8: +0xed = 0xff, +0xee = 0.
- The same bytes are also written in lockstep by `inventory_onJoinPanel` and
  `inventory_onStatPoint`. They therefore differ between machines. Only menu code reads
  them (0x1cd208, 0x1cb098, 0x1d1db8, 0x1d1bc0 and character creation), but they are inside
  the 0x4c30 bytes that are saved and that the character checksum may cover (*Unknown*:
  check `player_checksum` 0x1bdc98 for +0xed, +0xee, +0x4a58).
- Everything else the item, stat and skill screens change goes through the message tables
  above (checked by scanning every assignment into 0x4d8af0–0x4ebbb0 in the range).
- `itemList_drawGold` 0x1c7218 clamps record +0xe4 (gold) to 99,999,999 with a store at
  0x1c72dc. It is draw code and runs only where the panel is on screen. Every gold credit
  read in this range clamps to the same limit already, so the store should never change
  the value; gold writers in other areas were not checked.
- Quest variables: the only writers in the range are `inventory_giveItem` (sets
  `PLAY_firstRecall`, and record +0x4c25, only when not in a net game), `inventory_equipItem`
  (sets `bowEquipped` inside the lockstep handler) and `game_resetState`. No menu or HUD
  draw code calls `vars_set`.
- Object state: the only writes to a player object's flag word from this range are in
  `hud_onMsg` (messages 2 and 4), i.e. in lockstep. The scan covered accesses through
  `g_players[i]` +0x43d8 only; writes through other object pointers were not searched.

### P5. Debug cheat keyed on a per-machine flag — Observed

`g_debugCheats` (0x4f8ee0) is set at boot when the memory card holds a file `debug.sht`
(`save_init`, 0x2173cc). With it set, `hud_run` (0x1dbb64) gives player 0 1,500,000 gold
and every player 20,000 experience when player 0's lockstep pad has bit 0x4000 in word
+0xc and bit 0x8 in word +0x8 (and the front end is not running), and the pause menu exposes `debug_missionEditor` 0x1e31c0, which writes
difficulty, the evil / decision bits and mission medals directly. A machine with the file
desyncs from one without.

### P6. `hud_run` uses raw local pads inside a run task — Observed, harmless as shipped

The per-player loop in `hud_run` tests the raw pad words at 0x4028dc and 0x4028d8 (+0x58 per
slot). What follows is local (`menu_openInventory`)
except `script_runByName("*inventoryOnNotify")`. `inventory_runPanel` likewise runs
`*exitInventoryNotify` from a draw task. No level script defines either hook (searched all
120 decompiled scripts), nor `*bowEquipNotify` / `*weaponEquipNotify`.

### P7. HUD draw task changes session state — Observed

0x1dbc48 calls `net_closeLocalMenus`, `cut_end` and sets the leave-game code 0x41b508 from
draw code, in the two exit paths described under HUD. Both end this machine's
participation, so nothing shared survives; listed for completeness.

### P8. A game message carries an object address — Observed

Game message 5 (`hudmsg_sendSavepoint` 0x1de1a0, sent by `Savepoint_run`) carries a 32-bit
value that the handler (0x1d8f00) passes to `Savepoint_startSavedEffect` as an object
pointer. It is correct on the receivers only if every machine allocated that savepoint at
the same address. The shop buy message (P1) is the other address on the wire; that one
points into a static table.

### P9. The character checksum also covers each machine's save buffer — Observed

`net_sendChecksums` 0x1de46c computes, per player, the checksum of the live record and of
that player's record inside the local save buffer (0x1de4d0). The handler (case 10 of
`hud_onMsg`) compares both with what the owner sent. The save buffer is built and
temporarily rewritten on per-machine timing; see docs/audio-save.md A1 for the cases where
that produces a false failure.

### P10. Things that are per machine by design

- `g_minimapMode` (0x4f8400) is cycled from raw pads inside `minimap_draw` and is written
  into the save file. `script` code does not read it (only 0x1e3ff0, 0x1e42e0, save, reset
  and 0x304ec8).
- `hud_setCompassTarget` and `hud_setBust` (script built-ins) do nothing on a machine that
  has a menu or dialog open; they only set HUD state.
- `hud_addGoldFloater` projects through the local camera for the drawn path only.
- `ShopDaemon_run` 0x1d1490 would restock from a per-machine tick counter (0x44fdd0) with
  shared-seed item generators, but nothing constructs a `ShopDaemon` (no call or pointer to
  0x1d13c8).
- `menu_cursorInput` 0x1c6570 clears direction bits in `g_rawPads` while a list is open.
- `itemList_tabInput` 0x1c6938 zeroes word +0x10 of the lockstep pad `g_pads[slot]`
  (0x1c6a04) as well as of the raw pad, from a draw task. `pad_apply` rewrites the pad at
  the start of the next simulated frame, so no simulation code should see it (*Inferred*).

## Open questions

- P1: are the cosmetic seeds equal at 0x3230c4 in a net game? One memory snapshot per
  machine settles it.
- P2: can a notice box be open on one machine while a `postAction` name is pending?
- Who clears object flag 0x400000 after a menu closes: the state-0 branch of message 2
  clears only 0x800000 (mask 0xff7fffff at 0x1d8dd4; 0x400000 is set at 0x1d8d88).
  (Answered in `docs/player.md`: the tail of `Player_run` counts record +0x4bc8 down —
  the 10 that state 0 stores — and clears 0x400000 when it reaches 0, 0x1ac6f0–0x1ac724.)
- `script_playerAdjustStat` calls both `inventory_onStatPoint` and the message sender
  0x1c5780; in a net game every machine would send. Not followed.
- `inventory_onJoinPanel` sends message 9 from inside a handler, so each machine sends one;
  the handler is idempotent.
- 0x1c8d38 (item description, 8.9 KB), 0x1d59f0 (skill tree lines, 7.3 KB), most of
  `frontend_run`'s options states, `frontend_controlConfigRun`, `Weather`, and the tail of
  the game unit past 0x1e7000 were only skimmed. Unreferenced functions (0x1c04e8,
  0x1c2120, 0x1c3420, 0x1c7908, 0x1d1548, 0x1d1668, 0x1d3f2c, 0x1de8c4, 0x1df120,
  0x1e6528) were not read; `tools` found no call or pointer to them.
- The second shop panel table at 0x86a4b0 and the workshop state at 0x4f4878 are not laid
  out.
