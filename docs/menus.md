# menus — inventory, shop, skills, stats, pause, save

The screens a player uses to equip, trade, spend points, pause and save on US
SLUS_209.73 v2.00. The message handlers behind them are already specified in
`docs/spec/game-messages.md` and `tools/ref_messages.py`. This document is the
screen: where it draws, which button sends which message, and the two formulas
that were not in that model (the next skill-rank cost, and the save file's item
index). `tools/ref_menus.py` is the same contract as code.
`tools/difftest_menus.py` runs the original functions in `tools/ee_emu.py`.

HUD bars, fonts and icon pixels stay in the UI research
(`docs/formats/ui-text.md`, `docs/formats/ui-fonts.md`,
`docs/formats/icon-association.md` on that branch). Ordinary UI is 640×448.
`text_begin` is 0x1800b8, `ui_drawRect` is 0x17bd30, `ui_drawSprite` is 0x17fb68.
The small-font pointer is the word at 0x4f7104; the word at 0x4f7100 is the one
the pause menu loads.

Status words are the ones in `CONTRIBUTING.md`. **Executed** means
`tools/difftest_menus.py` ran the original function on state the test built.
Nothing here was seen on a live game.

## 0. How important each screen is

The native client already has the handlers. What it lacks is the screen that
sends the messages. Ranked by what a playing character cannot do without that
screen:

1. **Inventory** (`itemList_input` mode 2). Equip, unequip and drop are messages
   1, 2 and 0, and this is the screen that sends them. The level the player has
   acknowledged (`record +0x58`) stays behind the real level until this screen
   has been opened (`docs/ui.md`, message 9).
2. **Stats and level-up** (the same panel, pages 3, 4 and 5). `player_giveExp`
   adds the points; this screen is what spends them (message 6). Page 5 is the
   level-up page `docs/ui.md` already names.
3. **Skills**. One confirm sends one skill-point message. The tree is also the
   only place the next-rank cost is shown. Assigning a spell to a hotkey is a
   HUD message (`hudmsg_sendAssignSpell`), and this screen does not send it.
4. **Save and load**. Equipment survives a save only after the pointer-to-index
   conversion below. The card browser itself was not executed.
5. **Shop**. Buy and sell are the gold path in the hub. A character can finish
   a level without it; the hub's stock cannot change hands without it.
6. **Pause**. Recall, options and leaving the session. A net game is paused by
   the end-of-game script, not by this menu (`docs/ui.md` P3). It is the screen
   a player uses to stop, and the one combat can do without.

## 1. What every item screen shares

`g_itemPanels` is 0x4f4040, four records of 0x74 (`docs/ui.md`). Executed, by
changing one word at a time and by the draws in the difftest:

| Offset | Role |
|---|---|
| +0x00 | integer x origin of the inventory grid and of the skill tree |
| +0x28 | integer added into the row calculation |
| +0x44, +0x48 | free-cursor x and y, floats, moved by `itemList_analogCursor` 0x1cec68 |
| +0x50 | page. 0, 1 and 2 are the three bags. 3, 4 and 5 draw `stats_screen` and skip the grid (0x1cd564–0x1cd5e8) |
| +0x58 | 1 while a holdable item is being dragged |
| +0x60 | cell under the cursor |
| +0x64, +0x68, +0x6c | dragged cell, its column, its row |

The cursor test in `itemList_input` (0x1cdd40–0x1cdf70), executed for a texture
of height 0:

- column = truncate toward zero of `(cursor x − panel x − 17) / 32`
- row = truncate toward zero of `(cursor y + (−height/2 + 0x8c) + panel +0x28 − 229) / 34`
- the cell is `base + column × 0x1518 + row × 0x48`, and only column 0..8 and
  row 0..74 match
- mode 0 reads the grid pointer at 0x4f4228; any other mode reads 0x4ebbb0.
  The page then adds `page × 0xbdd8` (one bag of 75×9 cells)
- page 5, and any page of 3 or more, skips the cell (0x1cdf4c, 0x1cdf54)

`g_rawPads` is 0x4028d0, stride 0x58. The edge word at +0xc is what the cell
test reads; the executed cases also set +0x10, because a slot whose equipment
byte is 2 or more reads that word instead. `g_menuInputLockout` (0x41b4fc)
must be 0 or the function reads a different pad.

The button masks are stored by `game_initCamera` 0x1e6b68 from the byte at
0x41b69c. Executed, both values of that byte:

| Byte | 0x41b960 equip | 0x41b968 second | 0x41b970 shop (modes 0 and 1) | 0x41bfbc confirm | 0x41bfb8 cancel |
|---|---|---|---|---|---|
| 1 | 0x40 cross | 0x10 triangle | 0x80 square | 0x40 | 0x20 circle |
| 0 | 0x20 circle | 0x80 square | not stored | 0x20 | 0x140 |

The same function stores 0x7b, 0x7c, 0x7d, 0x7e beside those words. They are
wider than a pad bit. What reads them was not followed. **Unknown**: which
instruction writes the byte at 0x41b69c. The only text-section reference found
is this load. Byte 1 is the set whose confirm bit is the attack bit the live
rig recorded (0x40, `docs/issues/live-rig.md`), and it is the only set that
gives the shop a button. That the US build takes byte 1 is **Inferred** from
those two facts.

On a matched cell the edge word is tested against those masks
(`tools/ref_menus.py` `item_action`, executed, 18 cases):

| Mode | Screen | Shop bit | Equip bit | Second bit |
|---|---|---|---|---|
| 0 | shop stock | `shopmsg_sendBuy` | | |
| 1 | the bag while the shop is open | sell message, or `hud_confirmBox` when the cell is already equipped | equip, or unequip when it is equipped | |
| 2 | inventory | | equip, unequip, or a drag when item flag bit 35 is set | `invmsg_sendDrop` |
| 3 | workshop | `workshop_input` runs for the cell with no button test | | |

Where two bits are down, the shop bit wins on mode 1 and the equip bit wins on
mode 2. The sell is the inline `net_sendGameMsg` at 0x1ce520 (13 bytes, the
shop message 1 that `docs/spec/game-messages.md` already executes). Equip and
unequip are `invmsg_sendEquip` 0x1c5800 and `invmsg_sendUnequip` 0x1c5840.

## 2. Inventory

### Layout

`itemList_draw` 0x1cd208, executed with panel x = 80. The first
`ui_drawRect` is `(panel x + 15, 413, panel x + 305, 414)`, layer 4. The same
call then repeats one pixel higher. That is the scrollbar.

With panel +0x58 clear, two sprites go through 0x17fb18 at layer 7, tints
0x80808080 and 0x34000000. With +0x58 set, the cell at +0x64 is drawn at the
free cursor (0x1cd48c–0x1cd520): that is the dragged icon. The icon pitch of
32 by 34 is the cursor math above and the grid in `icon-association.md`.

`itemList_drawItemInfo` 0x1c8d38 is the stat pane (damage, armour, gem slots).
It calls `ui_drawFrameImpl` at 0x1cb008 and 0x1cb05c. Its positions were not
executed. **Unknown**.

### Input and state

Mode 2, cross-confirm masks, executed:

- cross on an ordinary cell sends equip, or unequip when `inventory_isEquipped`
  says it is worn
- cross on a cell whose flag qword has bit 35 set does not send. It stores the
  cell at panel +0x64, the column at +0x68, the row at +0x6c, and 1 at +0x58
- triangle sends drop (`invmsg_sendDrop` 0x1c59d0)
- square sends nothing

No function in 0x1c0000–0x1d2000 reads panel +0x64 except `itemList_draw` and
`workshop_input`. A dragged cell is not copied onto another bag cell. Moving
an ordinary item is equip, unequip or drop. The handlers
(`docs/spec/game-messages.md` sections 2 and the item record in
`docs/spec/items.md`) are what change the bag, the equipment pointers and the
weight.

Before the drop message the screen calls 0x14a928 with a box around the player
and then `world_forEachGridObject` with `itemList_dropBlockerFilter`. 0x14a928
sits between the grid iterators and `world_collectInSphere`; it is not
`world_findFreeSpot`. **Unknown** whether 0x14a928 draws `g_randSeed`. The
shared-seed search that places the prop is the handler's, three draws per
sample (`docs/spec/game-messages.md`). The executed buy, equip and drag paths
did not call `world_findFreeSpot`.

## 3. Shop

### Layout

`shop_buySellMenu` 0x1c6bb8, executed on a zeroed shop panel at 0x86a4b0.
`menu_cursorInput(0, 0, 2, 0)` — two choices. A sprite at (66, 210), layer 0,
tint 0x80808080. Centred wide text at y = 203 and y = 243. `text_begin` is
layer 0, colour 0x80323c3c, icon alpha −1. The font pointer is the word at
0x44fdd8 (load at 0x1c6cbc). A second sprite site at y = 248 (0x1c6cac) did
not run for that zeroed panel.

The stock grid and the player's bag are the two item lists, modes 0 and 1.

### Input and state

Executed with the byte-1 masks: square on mode 0 sends buy; square on mode 1
sends sell, or opens `hud_confirmBox` when the cell is equipped; cross on mode
1 equips or unequips. Prices, the gold debit and the bag write are
`shop_buy` and `shop_sell` in `tools/ref_messages.py` (executed there, not
repeated): buy truncates value × 0.6, × 0.45 for category 1, × 1.0 for flag
bits 40 and 41 or equipment slot 8, and the gold is taken even when
`inventory_giveItem` fails. Sell truncates value / count × 0.05, at least 1,
and 0 for slot 8 or definition flag bit 46.

Stock generation draws `g_cosmeticSeed` three times and, with probability 0.1
each, `g_randSeed` (`docs/ui.md` P1). The seeds are equal at that point
(`docs/issues/sync-breakers.md`). That generation was not run again here.

## 4. Skills

### Layout

`skills_screen` 0x1d4660, executed with panel x = 0 and again with panel x = 40,
a zeroed record (class 0, ranks 0). `text_begin` loads the font at 0x4f7104,
layer 5, colour 0x801e6464, icon alpha −1. The header is centred at
`(origin + 53, 106)` and drawn at `(origin + 70, 106)`. A clipped sprite sits
at `(origin, 98)`, layer 5, and another at `(origin, 158)`, layer 3.

Node captions for that zeroed class-0 walk were submitted at x = origin plus
86, 137, 196, 247 or 306, and at y = 164, 261, 349, 446, 534, 622 or 710.
`skills_drawTreeLines` 0x1d59f0 was called 17 times with the panel origin as
its fourth argument. The local x was one of 17, 68, 127, 178, 237 and the
local y one of 24, 121, 209, 306, 394, 482, 570. Other classes were not walked.
The lines are the class table, so those coordinates are the class-0 picture,
not a formula for every class.

### Input and state

`skills_nextRankCost` 0x1d436c, executed for param in {0, 1, 4, 5, 8, −1, 20}
and level in {0, 1, 2, 3, 10}. The row is `0x4ef530 + class × 0xa88 + index × 0x38`.
Param is the signed byte at row + 2. Level is `player_getPassiveLevel` of the
mask at row + 8.

- param below 5: `param × (level + 1)`, low 32 bits
- otherwise: param plus the truncation toward zero of `level` raised to the
  float 0x3fcccccc

The cost is an argument of `skills_drawDescription` 0x1d3b78 (0x1d4ecc–0x1d4f20),
so it is description text. The confirm path (0x1d57e0) sends
`invmsg_sendSkillPoint` once when skill points are above 0, and a second site
(0x1d58dc) does the same when a row byte is nonzero. It does not loop over the
cost. The handler spends one point and raises one rank, and does not read the
cost (`docs/spec/game-messages.md`, message 7). A rank whose description shows
a cost above 1 still spends one point per confirm. **Inferred** from the send
site and the handler together; the screen was not itself executed through to
the send.

The screen's calls do not include `hudmsg_sendAssignSpell` or
`hudmsg_sendQuickSlot`. Hotkeys are the HUD spell selector.

Points arrive from `player_giveExp` 0x1d3150: +1 while level is below 6, +2
below 16, +3 below 26, +4 below 36, otherwise +5 (`tools/ref_combat.py`). That
function was not re-run here.

## 5. Stats and level-up

### Layout

`stats_screen` 0x1d1db8, executed as `stats_screen(0)` with the font pointer
set. First `text_begin`: the word at 0x4f7104, layer 5, colour 0x80323c3c,
icon alpha −1. Lines submitted:

| Call | Position |
|---|---|
| centred ascii | (160, 107) |
| centred wide | (160, 129) |
| wide, then centred wide | (81, 208) and (143, 208) |
| wide, then centred wide | (81, 229) and (143, 229) |
| wide, then centred ascii | (85, 306) and (163, 306) |
| sprite | (4, 99), layer 4 |

A frame is set up at 0x1d201c through `ui_drawFrame` 0x17fbb8 with width 0x124
and height 0x197. The x and y of that frame were not recovered. **Unknown**.

`itemList_draw` calls this function for pages 3, 4 and 5 and then skips the
grid (0x1cd564). `stats_screen` itself calls `skills_screen` at 0x1d253c, so
the skill tree is also a page of this sheet.

### Input and state

Four sites (0x1d24d4, 0x1d24f4, 0x1d2510, 0x1d252c) call `invmsg_sendStatPoint`
with the stat index 0, 1, 2 or 3. The index comes from a word compared with
those constants. The button mask is loaded from 0x41bfe8 plus a cursor scale
(0x1d2460–0x1d2478). A call of `stats_screen(0)` with every pad bit set and
that word filled did not reach the sites. **Unknown** which edge bit gets
there, and which cursor value selects which stat.

What the message does is executed in `inventory_onStatPoint`: stat 0–3 spends
one stat point on `record +0x78`; 4–7 raises a base stat for free; 8 adds a
skill point. `player_giveExp` adds 3 stat points per level. The screen also
writes `record +0xed` and `+0xee` locally (`docs/ui.md` P4) and calls
`player_recalcStats` from the draw task.

No seed draw was recorded on the executed `stats_screen(0)` draw.

## 6. Pause

`pauseMenu_open` 0x18e334 sets `g_paused` offline, sends menu-state message 2
and adds `pauseMenu_task` 0x18cc08 as a draw task (`docs/engine.md`). With no
open state the task only polls and draws nothing. The open-state geometry was
not executed. **Unknown** as positions.

Observed at the one `text_begin` in the task (0x18d5e8): font is the word at
0x4f7100, layer 7, colour 0x80464646.

Observed as calls out of the task, which is the action list: recall
(`hudmsg_sendRecall` 0x1de138), the exit countdown (`hudmsg_sendExitCountdown`),
options commit (`config_commitOptions` 0x1e6650), the level-warp messages 7 and
11, and the save helpers 0x217550, 0x2166e0, 0x2175b4, 0x2176e0. The normal
menu table has no save entry; its comparison with `menu_savegame` never matches
(`docs/ui.md`, message 11). Whether any of those calls draws a seed was not
executed.

## 7. Save and load

The file layout is `docs/audio-save.md`. Two functions were not in the message
model and are executed here.

`save_itemPtrToIndex(item, record)` 0x216bf8 walks the three bags at
`record +0x130`, stride 0x1208, up to the count at `+0x1330`. A null pointer
is −1. A pointer equal to cell `i` of bag `b` is `b × 1000 + i`. Anything else,
including a cell past the count, is −1.

`save_itemIndexToPtr(index, record)` 0x216e10 is the inverse. Index −1 is a
null pointer. Any index that no counted cell produces is a null pointer.

`save_snapshotPlayer` 0x216c80 copies the record to `g_savedPlayers` 0x879ec0,
runs the conversion on the 17 equipment pointers at +0x43f0, the two at
+0x4434 and +0x4438, and the one at +0x443c, then
`item_encodeDefinitionIndex` on each counted item. Its only other call is
0x1bf328. There is no random call in the function. **Observed** from that body;
the snapshot itself was not executed, the index pair was.

`save_fixupPlayer` 0x216ea8 reverses the conversion on the live record and
zeroes the object pointer at +0x43d8. The caller copies the saved record over
the live one; this function does not.

The memory-card browser (0x218afc, 0x219360, 0x219b90) was not executed. Its
frame positions are **Unknown**.

## 8. Still open

- The item description pane's coordinates (`itemList_drawItemInfo`).
- Which button and which cursor value reach the four stat-point sends.
- The skill screen executed through to `invmsg_sendSkillPoint` (the send is
  one call when points remain; the screen itself was not run to that call).
- Pause-menu and memory-card frame positions.
- Who writes the byte at 0x41b69c, and what the 0x7b–0x7e mask words mean.
- Whether 0x14a928, called on the way to a drop, draws `g_randSeed`.
