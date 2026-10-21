# Quests, missions and the campaign

US `SLUS_209.73` v2.00. The quest list, the mission bits, medals, the evil and
decision bits, quest variables and the gold split were already executed in
`tools/ref_natives.py` (`docs/spec/script-builtins.md` §§1.5, 1.11, 2). This
note is the rest of a play-through: how those calls are arranged in the level
scripts, what an act change does to them, what `player_giveExp` does to one
record, and the mission menu's run task. `tools/difftest_quests.py` runs the
original functions. `tools/ref_quests.py` is the model. Nothing here was seen
on a running game.

`setCFlag` is not a campaign flag. `script_applyCFlag` 0x1445fc stores creature
bit 0 (boss, and it starts the boss music) and bit 26 (friendly). Any other bit
is stored nowhere (`docs/script-effects.md` in the script research). The 120
level scripts call it 18 times: seven pass bit 0, one passes bit 26, nine pass
a name rather than an integer. Campaign progress is the quest variables, the
mission bytes, the medals, the evil and decision bits, and the per-player
script flags at record +0x4c28.

## 1. Where the state lives

Per character, inside the player record (`g_players` 0x4d8af0, stride 0x4c30):

| Offset | What | Who writes it |
|---|---|---|
| +0x41d0 | quest list: 8 entries of 0x40 (title[0x20], text[0x20]), count at +0x43d0 | `quest_add` 0x1d386c, `quest_remove` 0x1d3968, `quest_clearAll` 0x1d3adc |
| +0x4bbf | 5 × 13 mission bytes, one row per difficulty. Bit 0 available, bit 1 complete. Mission 0 is the first byte of the row | `mission_setAvailable` 0x1bf6d0, `mission_setComplete` 0x1bf770 |
| +0x4c0d | 13 medal bytes, one per mission, not per difficulty | `mission_grantMedal` 0x1bdb80 |
| +0x4c1a | evil, one bit per difficulty | `game_setEvil` 0x1bf8f8 |
| +0x4c1b | decision made, one bit per difficulty | `game_setMadeDecision` 0x1bf980 |
| +0x5c, +0x59, +0xe8, +0xec | experience, level, skill points, stat points | `player_giveExp` 0x1d3150 |
| bags +0x130 | items. Flag bit 39 marks a quest item (`docs/player.md`) | `player_removeFlag39Items` 0x1be1d8 |

`quest_add` stops at the first player whose list is full or already has that
title, so a later slot can miss it. `quest_remove` rewrites matches with the
nine-byte placeholder and then slides the list once. Both are executed in
`difftest_natives`. `mission_setAvailable` writes bit 0 on the first
`g_numPlayers` records. `mission_setComplete` writes bit 1 on all four records;
the value −1 sets the bit, and any other value stores that value's own bit 0.

Per game, not per character:

| Location | What |
|---|---|
| `g_questVars` 0x86da80 | name, a zero, a signed value byte. `vars_get` appends an unknown name with 0. `vars_clearAll` zeros the values and keeps the names |
| `g_difficultyIdx` 0x4f719c | which mission row and which evil/decision bit |
| `g_currentAct` 0x88d3d4 | the act, or −1 before the first level |
| `g_missionTable` 0x4fe540 | 13 rows of 0x34. Row `i` is mission `i + 1`. Mission 0 has no row (`docs/data-tables.md` §7.4) |
| `g_actLevelTables` 0x4f8e48 | 13 acts (`g_actCount` 0x4f8e7c). Counts at 0x4f8e10. Each row is a name pointer and a saved-state size |

New characters get mission 0 available and complete on all five difficulties
(0x1b2410–0x1b2450, `docs/data-tables.md`). The mission menu does not show
mission 0: its cursor is the highest available mission in 1..12, as a row, or
row 0 when none of those is available. **Executed.**

## 2. How scripts start, advance and complete a quest

Recounted from the 120 `script.scr` files on the disc. The command totals match
`docs/spec/script-builtins.md` §3. Arguments below are the integer literals.
A missing integer means the script passed a variable or a string. No quest
title is copied here; `addQuest` still uses the generated id `docs/data-tables.md`
already describes.

The calls, and how many level files contain each:

| Command | Calls | Files | What a play-through uses it for |
|---|---|---|---|
| `getv` / `setv` | 790 / 571 | 64 / 73 | the step counter. 260 distinct `setv` names, 233 `getv` names |
| `setMissionAvailable` | 88 | 23 | always `(mission, 1)` when both arguments are integers. No literal turns a mission off |
| `grantMission` | 33 | 32 | marks that mission complete |
| `addQuest` / `removeQuest` | 43 / 30 | 20 / 19 | puts the line on the quest list, then takes it off |
| `getMissionAvailable` / `getMissionComplete` | 129 / 115 | 3 / 13 | the tests in front of those writes |
| `grantBronze` / `grantSilver` / `grantGold` | 9 each | 9 each | the medal, once per medal mission |
| `playerAdjustStat` | 27 | 9 | stat points after a medal, not experience |
| `givePlayerItem` | 10 | 6 | the quest item |
| `countQuestItems` / `playerHasItem` / `removePlayerItem` | 61 / 61 / 147 | 13 / 20 / 34 | the turn-in |
| `givePlayerGold` | 4 | 2 | 400, 100, 10, and one non-literal |
| `givePlayerExp` / `addv` | 0 / 0 | 0 | not used by these scripts |
| `activateMissionMenu` | 4 | 2 | `hub` and `hub2`, twice each |
| `setEvil` / `setMadeDecision` | 2 / 2 | 1 / 1 | both in `blood1` |

Names that show up as gates, not as dialogue: `currentMission`, `whichAct`,
`finishedQuest`, `finishedMission`, `startedMission2` through `startedMission12`,
`firstmissionever`, `playerisevil`, `playerisgood`, `storeLevel`. `getv` of an
unknown name creates it with value 0, so a test is also a write.

The integer call sites group by mission like this. "Unlock" is
`setMissionAvailable(n, 1)`. "Complete" is `grantMission(n)`. A file can do
both. `hub` and `hub2` repeat several of these because more than one branch
asks for the same mission.

| Mission | Unlocked in | Completed in | Medal script |
|---|---|---|---|
| 1 | `hub`, `blood1` | `strife`, `drundar`, `drunare`, `drunarm` | `blomedal` |
| 2 | `hub`, `hub2`, `innovat1` | `innovat1` | `innmedal` |
| 3 | `hub`, `hub2`, `islc1`, `islcave1` | `islc2`, `islcave1` | none |
| 4 | `hub`, `hub2`, `wat1`, `water1` | `water1`, `wate2a`, `wate2b`, `wate2c`, `watg2a`, `watg2b`, `watg2c` | `watmedal` |
| 5 | `hub`, `hub2`, `tormenta` | `tormenta` | `tormedal` |
| 6 | `hub`, `hub2`, `swamp1`, `swamp2` | `swamp1`, `dis2` | `dismedal` |
| 7 | `hub`, `hub2`, `valor` | `valor`, `honor` | `valmedal` |
| 8 | `valor`, `obsfor1` | `obsfor1`, `fire5` | `firmedal` |
| 9 | `valor`, `storm1` | `storm2` | `stomedal` |
| 10 | `hub`, `hub2`, `fay1`, `fay2` | `fay3` | none |
| 11 | `hub`, `hub2`, `nit1`, `nitmar1` | `nit2`, `nitmar1` | `nitmedal` |
| 12 | `hub`, `hub2`, `fearboss` | `fearboss`, `endgood`, `endbad` | none |

Missions 3, 10 and 12 are the table rows whose medal and bonus pointers are
null and whose three flag words are 0. They have no `grantBronze` call. The
other nine medal scripts are one `grantBronze`, one `grantSilver` and one
`grantGold` of that mission number.

`blood1` is the decision. It calls `setEvil(0)`, `setEvil(1)` and
`setMadeDecision` twice. `swamp2` is the evil story level for mission 6: it
unlocks 6 and does not call `grantMission`. `hub2` is `game_getHubName`
(below), and it carries the same unlocks as `hub` from mission 2 upward plus
a literal unlock of mission 1.

`fire1` calls `setMissionAvailable` with a mission that is not an integer
literal. `airarena`, `bossevil` and `bossgood` pass a variable to both the
unlock and `grantMission`. `givePlayerItem` sits in `blood1`, `innovat1`,
`dis2`, `islgoth`, `stomedal` and `torbonus`. The three literal gold amounts
are all in `islgnome`. `innpit` is the gold call whose amount is not a literal.

Folding repeated `getv` calls, the scripts that do more than one of these
commands most often do one of three things. Five copies run the medal block
`getMedal`, `grantGold`, `grantSilver`, `grantBronze`, then `playerAdjustStat`.
Three copies run `setMissionAvailable`, `setv`, `setv`, `grantMission`. The
turn-ins run `playerHasItem` or `countQuestItems`, then `setv`, `removeQuest`,
`grantMission` and `removePlayerItem`. That is a census of the call order in
the file, not a run of the script VM, so which branch actually fires is still
the dialog and the conditions around it.

## 3. Rewards

### Experience

`givePlayerExp` has no call in these 120 scripts. Kill experience is the split
in `docs/spec/combat.md` §5, and that calls `player_giveExp` 0x1d3150.
**Executed**, with `player_recalcStats` 0x1b6458 stubbed so only this body is
on test. The thresholds are the 81 words at 0x41b558, read at run time.

`exp = min(exp + amount, table[80] − 1)`. While `table[level] ≤ exp` and the
level is below 80: skill points +1 below 6, +2 below 16, +3 below 26, +4 below
36, otherwise +5; the stat-point byte at +0xec gains 3 and wraps; the level
byte gains 1; `player_recalcStats` runs once per level gained. If hit points
are greater than 0, hit points and mana become their maxima. A dead record
still gains the level and the points, and both pools stay where they were.
A negative amount lowers experience and does not by itself lower the level.
Another slot's record is left alone. The same rules are already stated in
`docs/spec/combat.md` §6; this round is the run.

### Gold and items

`givePlayerGold` adds `amount / g_numPlayers` to each player, C division toward
zero, capped at `MAX_GOLD`. That split is executed in `difftest_natives`.
The four script calls are the 400, 100 and 10 in `islgnome` and the non-literal
in `innpit`.

`givePlayerItem` is still the path through `item_parseDescriptor` and the bag
insert. This round did not enter that body. The ten call sites are listed above.

`countQuestItems` reads player 0's bags only (already in `ref_natives`).
`player_removeFlag39Items(slot)` 0x1be1d8 walks that slot's bags, including
bag 2. An item whose flag bit 39 is clear stays. An item with the bit stays
when its definition name (the pointer at the definition's first word) contains
`bloodstone` or `shardof`, or is exactly `spiritrunes`, `emptybag`, `fullbag`,
`pickaxe` or `twistedkey`. The compare is case-sensitive, so `Bloodstone` is
not kept and `pickaxe2` is not kept. Anything else with the bit is handed to
`inventory_removeItem` 0x1c1cb0. **Executed** for the keep-or-drop decision.
The difftest follows `strstr` and `strcmp` and stubs the remove so the slot
actually slides down; the remove's equipped-pointer fixups are the inventory
function already named in `symbols/ui.tsv` and were not compared here.

## 4. The mission menu

`missionMenu_open` 0x231520 registers `missionMenu_run` 0x2316fc and the draw
0x232300 at priority 0x14, stores the chooser slot at 0x4fe7ec, and leaves the
state byte 0x8e2efc at 0. The draw was not run. The run task was, one button
per tick, offline, with `net_isSlotActive` returning 1 unless a case says
otherwise. The pressed word is pad 0 at 0x41bfd8+0x0c. Face bits are the set
in `docs/engine.md`: cross 0x40, circle 0x20, select 0x100, up 0x1000, right
0x2000, down 0x4000, left 0x8000.

Row and column are the bytes at 0x8e2f0c and 0x8e2f0d. Column 0 is the story
level, 1 the medal level, 2 the bonus level. The cursor covers rows 0..11.

| State | What the tick that finds it does |
|---|---|
| 0 | Row becomes the initial row, column 0, `g_paused` 0x41b4f4 = 1, the counter at 0x8e2f04 = 0, go to state 1 |
| 1 | Counter += 8. At 128 it stores 127 and goes to state 2. Sixteen ticks end in state 1 (0, 8, …, 120); the next ends in state 2 |
| 2 | The word at 0x8e2f08 increases by 8. Then the button, below. Leaving for state 5 stores 1 at 0x8e2f00 |
| 3 | Go to state 2. The button is not read |
| 4 | Counter -= 16. Circle and select enter this state; the subtract starts on the following tick. Followed from 127 down through 63. `g_paused` was still 1 |
| 5 | Go to state 6 |
| 6 | Call `hud_stepFade(4)`. While it returns below 128, stay and add 1 to the word at 0x8e2f00. At 128 or more, go to state 7 and do not add |
| 7 | Go to state 8 |
| 8 | Copy the chosen level's file name to 0x41b6d0, store 0xff at 0x41b720, and clear the word at 0x8e2f00. The copy is this tick, not the tick that entered state 8 |

Two early exits in state 2, before the button. If `net_isLocalSlot(chooser)`
is true and `pauseMenu_isOpen` is true, `net_lockLocalInput(slot, 4)` and the
tick ends. If `net_isSlotActive(chooser)` is false, go to state 4. Stubbing
that function as 0 makes the second state-2 tick close the menu; the arrival
tick itself is still state 1's body.

The button, one bit at a time. A chord was not tested.

- Cross accepts the current column and goes to state 5. Story accepts when
  mission `row + 1` is available (0x231078). Medal accepts when that mission
  is complete and the row's medal-level pointer is set (0x2312a8); the flag
  words are not part of this test. Bonus accepts when the medal is at least 3
  and the word at +0x28 is set (0x231438). A refused cross stays in state 2.
- Circle and select go to state 4. Triangle, square and start do nothing.
- Up moves to the previous row and stops at 0. It does not look at
  availability, so it will sit on a locked row.
- Down moves one row when the destination mission is available (0x2310d4) and
  stops at row 11. It does not skip a locked row.
- Toward the side columns, and back toward the story, depend on the row.
  `0x2314bc` returns bit 0 of the row. On an odd row, right walks toward the
  side columns and left walks back. On an even row, left walks toward the
  side columns and right walks back.

Toward the side columns: from the story column, move to the medal column when
0x231228 is true, otherwise to the bonus column when 0x2313b4 is true,
otherwise stay. From the medal column, move to the bonus column when 0x2313b4
is true. The bonus column stays. Toward the story: from the bonus column, move
to the medal column when 0x231228 is true and otherwise straight to the story
column. From the medal column, move to the story column. The story column stays.

0x231228 is true when the mission is complete, the word at +0x24 is set, and
the medal-level pointer is set. 0x2313b4 is true when the medal is at least 3
and the word at +0x28 is set. So a finished mission whose medal is still 0 can
open the medal column, and a medal of 3 can open the bonus column without the
story being the thing under the cursor. An even row's right button, pressed
on the medal column of a row that fails 0x2314bc, walks back to the story
column. That is why a row such as row 2, whose flag words are 0, cannot be
walked onto a side column, and a right press while sitting there returns to
the story column.

State 8 copies one of the row's level pointers. Column 1 copies +0x10, column
2 copies +0x14. Column 0 copies +0x0c when `game_getEvil` is set and that
pointer is set, and +0x08 otherwise. The evil bit is the current difficulty's
bit in record 0's evil byte. **Executed** for a story row, a medal column, a
bonus column, an evil row and a row whose evil pointer is null.

The twelve helpers at 0x231078, in address order, return 0 or 1.
**Executed** for rows 0, 2, 5 and 11, medals 0..3, complete and not, and with
each flag word and the medal pointer forced off:

| Helpers | True when |
|---|---|
| 0x231078, 0x2310a8, 0x2310d4 | the mission (`row + 1`) is available. The flag words are not read |
| 0x23112c, 0x231180, 0x2311d4 | medal at least 1, 2 or 3, and +0x24 |
| 0x231228 | complete, +0x24, and a medal-level pointer |
| 0x2312a8 | complete and a medal-level pointer. The flag words are not read |
| 0x231310 | complete and +0x20 |
| 0x231360, 0x2313b4, 0x231438 | medal at least 3, and +0x28 |

This is the same flag column as `docs/data-tables.md` §7.4, plus the medal
pointer on 0x231228 and 0x2312a8. Rows 2, 9 and 11 have all three flag words
clear and a null medal pointer, so every side-column helper returns 0 there
even at medal 3 with the mission complete. The story helpers still return 1
when that mission is available.

## 5. Acts, the hub, and what an act change clears

`save_findAct` 0x217d30 matches a level name when a row's name is a prefix of
it, case-sensitive. The current act is searched first, then acts 0..12. A
current act below 0 or past the last act is skipped. **Executed** against the
86 row names in the executable: `blood1_x` matches the `blood1` row, `blood`
and `fire` and `HUB` match nothing, `hub2` matches a `hub` row. Because the
current act is first, `hub` and `hub2` match the act you are already in
whenever that act has a `hub` row, which each of them does. `save_actChanged`
0x217f70 returns 1 and stores the new act when the found act differs, and
returns 0 and leaves `g_currentAct` when it does not, including when no row
matches. From the session's starting act of −1, the first real level is a
change into whichever act contains that name. A later load of `hub` or `hub2`
is not a change.

`game_getHubName` 0x1ec300 returns `hub2` when record 0 has this difficulty's
bit set in both the evil byte and the decision byte and mission 1 is complete
(bit 1, not merely available). Otherwise it returns `hub`. **Executed** for
difficulty 0, 1 and 2, including a bit in the wrong position and a mission
byte of 1.

The act-change block in `mainloop_loadRequestedWorld` (0x320f8c–0x321020,
`docs/spec/script-builtins.md` §1.5) runs when `save_actChanged` is non-zero,
the card latch 0x4f8f28 is clear and no death task is running. It clears the
save buffer, the jump gates, every joined player's quest list, the flag-39
items, and the quest-variable values. Two of those bodies were run here:

- `quest_clearAll` writes `NoQuests` over the front of the title and the text
  of each used entry and sets the count to 0. Bytes after that nine-byte
  copy stay. Entries past the old count stay. Records at or above
  `g_numPlayers` stay. **Executed.**
- `player_removeFlag39Items` is the keep list in §3. **Executed.**

`vars_clearAll` was already executed: values become 0, names stay. A stuck
card latch skips the whole block (FINDINGS B10, B11).

## 6. What the save stores

`save_build` was not re-run. The layout in `docs/audio-save.md` is the one a
campaign reload uses. The player block at +0x320 is the 0x4c30 record, so the
quest list, mission bytes, medals, evil and decision bits, gold, experience,
level and the bags are per character. Quest variables start at +0x13418
(name[0x20], s32 value, until an empty name). The act is the u16 at +0x6e,
the difficulty is the byte at +0x6c, and the level name is at +0. Level
object state is only kept for levels in the current act (`docs/level-flow.md`
§7); a level outside that act is not in the file. `save_load` clears the
quest variables and then sets each saved one, and when 0x4f85b4 is set it
calls `inventory_shareQuestItems(0)`. A net save packs the local character
into that block; the level, the variables and the level states in the buffer
are this machine's.

## 7. What still blocks a start-to-finish campaign

In order. The first items are why a client that already has combat, movement
and the script commands in `ref_natives` still cannot play the story through.

1. **Dialog.** The calls in §2 sit inside conversation branches. `dialog_runTask`
   0x22ff48 is a separate machine and was not entered. The file-to-mission
   table says which file contains the call, not which line the player has to
   pick. This is the hole in front of every unlock and every turn-in.

2. **Granting a quest item.** `givePlayerItem`'s ten calls still go through
   `item_parseDescriptor` and the bag insert, which touch the shared random
   seed. The check (`countQuestItems`, `playerHasItem`) and the act-change
   keep list are known. The grant is not, so a turn-in cannot be fed by play.

3. **Removing a turned-in item.** `removePlayerItem` is 147 calls in 34 files.
   Flag 39's decision calls `inventory_removeItem`, and that decision was
   executed, but the remove body's equipped-pointer fixups were stubbed. A
   turn-in that must take the item back is still that inventory function.

4. **Cutscenes and the shop.** Neither has a native body (the script-composition
   map). They are not on the mission-number path above, and they are still
   between the player and some of the levels.

5. **The menu draw** 0x232300 was not run. The run task is enough to choose a
   level and write the pending name. `activateMissionMenu` is the four calls
   in `hub` and `hub2`. A client can use the state machine without the
   original draw.

6. **Save and load of this record** is specified in `docs/audio-save.md` and
   was not re-executed. The card write is a separate path. Level state outside
   the current act is not in the file.

7. **Inside one file, which entry point runs.** The census is not a run of
   `script_runByName` through these entries. A client that already executes
   the level scripts will hit the calls; this note does not replace that.

Already specified, so skipping them desyncs the campaign rather than being
unknown: the quest-variable rules, the mission bits, `quest_add` /
`quest_remove`, the gold split, `player_giveExp`, the hub name, the act
prefix match (including `hub2` not changing the act you are in), the quest-list
clear, and the flag-39 keep list. `setCFlag` does not belong in that list.
State 4's countdown was not followed to 0, and a tick with two buttons held
was not tested. Neither is on the path that writes the pending level.
