# Game messages: the handlers and the inventory logic behind them

A specification of what happens when a game message is executed, written so that a rebuild
can reproduce it. The same content as code is `tools/ref_messages.py`; the comparison with
the original machine code is `tools/difftest_messages.py` (section 11 says exactly what it
covers); `tools/test_ref_messages.py` tests the model's own logic without game files.

Status words. **Executed**: the statement is what the original code did under
`tools/ee_emu.py` (an instruction interpreter, not a console) and the model does the same
for every input of the differential test. **Observed**: read in the code at the address
given, not run. **Inferred**, **Unknown**: as in `CONTRIBUTING.md`. Nothing here was seen on
the live game except where section 10 quotes `docs/issues/live-rig.md`.

Everything in sections 1–5 is **Executed** unless a line says otherwise. Section 6 (gem
combining) and the dialog channel are **Observed** only.

## 0. Conventions

- `R` is a player record, `g_players` 0x4d8af0 + slot × 0x4c30 (`docs/player.md`). An *item*
  is a 0x48-byte record (`docs/spec/items.md` section 2): +0 definition pointer, +4 s16
  count, +8 u64 flags, +0x20 prefix, +0x21 suffix, +0x22 s16 *stamp* (its index in its bag),
  +0x24 four modifier slots. A *definition* is a 0x40-byte row: +0 name pointer, +0x1c
  equipment slot (`es`), +0x1d category (0 weapon, 1 armour, 2 other; also the bag number),
  +0x1e weapon subtype, +0x28 u64 flags.
- Bags: `R`+0x130 + bag × 0x1208, 64 records, s32 count at +0x1200 of the bag
  (`R`+0x1330 + bag × 0x1208).
- Equipment pointers `E[k]` = `R`+0x43f0 + 4k, k = 0..16 (0 one-hand weapon, 1 second
  hand, 2 two-hand or ranged weapon, 3 shield, 5 and 6 rings, 7 a single category-2 slot,
  8 ammunition, 14 and 15 earrings). Weapon-set pointers `W[0]`, `W[1]` = `R`+0x4434, +0x4438;
  `second` = `R`+0x443c; active set `R`+0x4a7c; weapon class `R`+0x4a86 (5 = unarmed,
  7 = dual wield, otherwise the weapon's subtype).
- A one-byte message field is read sign-extended (`lb`), a 16-bit field with `lh`, a 32-bit
  field with `lw`; multi-byte fields sit at fixed aligned offsets. "slot" is therefore a
  signed byte and is **never range-checked**: every handler indexes `g_players` with it as
  it comes.
- Callbacks (things other models own) are written `name(...)`; their list with addresses is
  `EXTERNALS` in `tools/ref_messages.py`.

## 1. Channels

### 1.1 The table

`net_registerMsgHandler(fn)` 0x13da98 returns the index of `fn` in the 16-word table
0x5d1498, or stores it in the first zero entry and returns that index (a 17th handler would
be written just past the table). Start-up makes seven calls in this order
(0x323e50–0x323e80); the ids below are what those calls return:

| Id | Family | Handler | Id stored at | Registered by |
|---|---|---|---|---|
| 0 | cutscene | 0x198f64 | 0x83d1c8 | 0x19b4b4 |
| 1 | voice | 0x31f354 | 0x505b14 | 0x31fd38 |
| 2 | NPC dialog | `dialog_onMsg` 0x22ee2c | 0x8e2e94 | 0x22f974 |
| 3 | game ("HUD") | `hud_onMsg` 0x1d8ca0 | 0x86ac40 | `hud_registerMsgHandler` 0x1dc194 |
| 4 | null | 0x1e01b0, an empty function | 0x86aa60 | same |
| 5 | inventory | `invmsg_dispatch` 0x1bfdb0 | 0x866d18 | 0x1c59a8 |
| 6 | text line | 0x31d82c | 0x8e8ed8 | 0x31da4c |
| 7 | shop | `shop_onMsg` 0x1c5d28 | 0x86a6a0 | 0x1d13a0 |

This is the table of `docs/netcode.md`, now executed.

### 1.2 Sending and executing

`net_sendGameMsg(id, bytes, n)` 0x13db38:

- offline (`g_networkMode` 0x402791 = 0): calls `handler[id](bytes, n)` at once, on the
  sender's own buffer;
- net game: appends {id, n, bytes} to the message ring of peer
  `net_getLocalPlayerSlot(0)` (ring at peer + 0xc + 0x24a0, 0x2000 bytes, write position at
  peer + 0x44ac). Attaching to a frame and the wire form are `docs/spec/net-wire.md`
  section 10.

The tick (0x13acc0–0x13ad3c) copies the `n` payload bytes of each message into one buffer on
its own stack and calls `handler[id](buffer, n)`. **Observed**: the buffer is not cleared,
so a handler that reads past `n` reads what earlier messages left there. Only one message
as sent depends on that (message 11 of the game channel, section 3).

A handler runs on every machine in the same frame, so everything it does to records and
objects is lockstep. Two handlers send a message themselves (`inventory_unrefItem`,
`inventory_onJoinPanel`): in a net game **each machine queues its own copy**, so the game
executes it once per machine, some frames apart; offline it runs nested, in the middle of
the handler.

## 2. Inventory channel (id 5, `invmsg_dispatch` 0x1bfdb0)

Jump table 0x537cc0, eleven entries. A type byte above 10 (unsigned compare of the
sign-extended byte, so 0x80–0xff too) and type 3 do nothing.

| Type | Bytes | Layout after the type byte | Sender (all are local menu code reading the raw pad, unless noted) |
|---|---|---|---|
| 0 | 13 | slot, s16 column, u32 index, s16 row, bag, panel, mode | `invmsg_sendDrop` 0x1c59d0 from `itemList_input` (drop, mode 0), `workshop_input` (the used gem, mode 2) and `Player_usePotion` (mode 2, K2) |
| 1 | 8 | quiet, s16 slot, u32 item address | `invmsg_sendEquip` 0x1c5800 from `itemList_input`; `inventory_unrefItem` from inside a handler |
| 2 | 8 | 0, s16 slot, u32 item address | `invmsg_sendUnequip` 0x1c5840 from `itemList_input` |
| 4 | 4 | panel, slot, levelUp | `invmsg_sendJoinPanel` 0x1c5628: a second local player takes an idle panel |
| 5 | 3 | slot, weapon class | `inventory_close` 0x1c5100 for each local panel owner: 5 with no weapon in the active set, 7 when `E[1]` is set and the active set is 0, else the weapon's subtype (**Observed**) |
| 6 | 4 | slot, s16 stat | `invmsg_sendStatPoint` 0x1c5780 from `stats_screen` |
| 7 | 8 | slot, kind, 0, u32 value | `invmsg_sendSkillPoint` 0x1c57b8 from `skills_screen` |
| 8 | 16 | slot, 0, 0, u32 bag, u32 descriptor address, u32 item address | `invmsg_sendCombine` 0x1c5738 from `workshop_input` |
| 9 | 3 | slot, level | `menu_openInventory` with a level-up pending; `inventory_onJoinPanel` from inside the handler |
| 10 | 10 | slot, s16 kind, s16 column, s16 row, s16 panel | none: 0x1c55e0 is never called |

The byte layouts are what the real senders queued (property `senders`); no sender leaves a
byte undefined.

### Type 0 — drop: `inventory_dropItem(slot, index, bag, column, row, panel, mode)` 0x1c4310

Followed by `game_sendCharacterToLobby(slot)` (below). mode 0 = to the ground, 1 = sold
(the shop handler's tail), 2 or more = silent.

1. `item` = `R`+0x130 + index × 0x48 + bag × 0x1208. **If its definition pointer is 0, return.**
   This is the only test. The index is not compared with the bag count, bag and index are
   used as they come.
2. Byte +0x47a of the player object (`R`+0x43d8) = 0. No test for a null object: a
   departed player gets address 0x47a written.
3. If mode < 2 and `net_isLocalSlot(slot)`: the item's *material sound* (below), drop set.
4. If the weapon class is 7: `inventory_unrefItem(slot, item)` (5.5).
5. If `W[active set]` == item: weapon class = 5, `player_resetIdleAnim(slot)`.
6. `taken` = min(count, 20) when `es` = 8, or the definition name contains the stem at
   0x5385e0 (thrown weapons), or definition flags & 0x1c0000000000; otherwise 1.
   count −= `taken` (16-bit). A count of 0 or less gives `taken` = count.
7. *This machine's screen copies* (per machine, see section 9): if `net_isLocalSlot(slot)`
   and the grid pointer 0x4ebbb0 is not 0, every one of the 9 × 75 cells of grid
   (panel, category) that is the *same item* (definition, flags and the word at +0x20
   equal — `item_sameIdentityFields` 0x108924) has `taken` subtracted from its count.
8. If mode = 0: `spot = world_findFreeSpot(player position, 0x30, 0xc, 0, 0)`;
   `block = pool_new(400)`; if a block came back, `ItemProp_ctor2(block, spot, item, 0)` and
   s16 at block + 0x14c = `taken` (the stack of the dropped object). The record handed to
   the constructor already has the reduced count.
9. If the count is now below 1: (per machine, same condition as 7) every matching cell
   other than (column, row) gets definition 0, then cell (column, row) gets definition 0;
   `inventory_removeItem(slot, index, category, panel)` (5.2) — **the bag is the
   definition's category, not the message's bag byte**; `inventory_selectIdleAnim(slot,
   0x866850 + slot × 0x108, 0)`.
10. `player_recalcLoad(slot)`, `player_recalcStats()`.

Material sound: one of 13 entries chosen from the item flags, in this order — 0x800000
(three sizes by subtype 1–4 / flag 0x20000000 / else), 0x200000, `es` = 3, 0x400000, 0x40000
(three sizes by subtype 1–3 / 0x20000000 / else), 0x100000, 0x80000, 0x1000000, else the
last. Equip uses a parallel set; unequip uses the drop set without the size split.

`game_sendCharacterToLobby(slot)` 0x1eb5c8: nothing unless `net_allPlayersState2()` and
`g_pvpModeB` 0x4f7120 = 0 and 0x4f713c = 0. It lists the active slots (`net_isSlotActive`,
0..`g_numPlayers`−1); for slot ≠ −1 the machine whose first local slot equals
`active[g_simFrame mod count]` calls `lobby_sendCharacter(slot, 0)`; for slot = −1 every
machine calls it for `active[(g_randSeed + own slot) mod count]` (unsigned). It reads the
seed and changes nothing in the game.

### Type 1 — equip: `inventory_equipItem(slot, item, quiet)` 0x1c27c0

The item is an **address**. Nothing checks that it lies in the player's bags: any address
whose first word is non-zero is treated as an item, including another player's record.

1. Definition pointer 0 → return.
2. `reason = inventory_checkEquipAllowed(slot, item)` (`docs/spec/items.md` section 6). If
   non-zero: cancel sound for the local slot, then `hud_showPlayerNotice(slot,
   text_lookup(title), text_lookup(table 0x537ff0[reason]), panel)` where panel = 1 when
   panel 0's word +0x38 is not this slot and panel 1's is, else 0 (per machine, presentation);
   return.
3. `es` = 0x10 → return (not equippable).
4. `set` = −1. For a weapon (category 0) that is not ammunition: subtype 4 or 6 (bow,
   thrown) → `set` = 1, `script_runByName` of the bow hook, `vars_set("bowEquipped", 1)`;
   any other → `set` = 0, `script_runByName` of the weapon hook. (No level script defines
   either hook, `docs/ui.md` P6.)
5. A shield (`es` 3) while the active set is 1, `W[1]` ≠ 0 and the weapon class is not 6:
   `set` = 0, and if `W[0]` ≠ 0 the handler calls itself for `W[0]` with quiet 0.
6. If `set` ≠ −1: active set = `set`. For a weapon: both `W` entries equal to the item are
   cleared; then
   - **dual wield**: one-hand weapon (`es` 0), passive 0x40000 above 0, `W[0]` ≠ 0 and that
     is a one-hand weapon → if `E[0]` ≠ `W[0]` the handler calls itself for `W[0]`;
     `second` = item;
   - otherwise `W[set]` = item.
7. Slot store, skipped when `E[es]` already is the item:
   - weapon: unless ammunition, weapon class = subtype. Then by `es`:
     2 (two-hand, ranged): `E[2]`, `E[0]`, `E[1]` = 0, and unless the subtype is 4 or 6 also
     `E[3]` = 0 and `second` = 0. 0 (one-hand): if `E[2]` holds a weapon, `E[2]` and `E[0]`
     = 0; then with the dual-wield passive and `E[0]` ≠ 0: `E[3]` = 0, weapon class = 7 and
     the item goes to `E[1]` instead of `E[0]`. Unless ammunition: `player_resetIdleAnim`,
     `inventory_selectIdleAnim`. Store `E[es]` (or `E[1]`) = item.
   - armour: for a shield, if `E[2]` holds a weapon and the class is not 6: `E[2]` = 0,
     `W[active set]` = 0, class = 5; else if `second` ≠ 0: `second` = 0, `E[1]` = 0,
     class = 0; either way the two animation calls. Store `E[es]` = item.
   - category 2: a ring (`es` 5) goes to slot 6 when 5 is taken and 6 is free; an earring
     (`es` 14) with the second-earring byte `R`+0x4c26 set goes to 15 when 14 is taken and
     15 is free. Store. An occupied slot is simply overwritten.
8. If quiet = 0: the material sound (equip set) for the local slot.
9. `inventory_selectIdleAnim(slot, …, 0)`, `player_recalcStats()`.

The previous occupant of a slot is not "unequipped": its pointer is overwritten and the
record stays in the bag.

### Type 2 — unequip: `inventory_unequipItem(slot, item)` 0x1c2f20

No test of the definition pointer and no test that the item is equipped.

- weapon: if `second` ≠ 0 and `es` = 0 → `inventory_unrefItem(slot, item)`. Otherwise:
  ammunition → `E[8]` = 0; else if `W[active set]` == item → `swapped =
  Player_weaponSwapInput(player, lockstep pad of the slot, 1)`; if 0, class = 5 and `E[es]`
  = 0; the two animation calls. Then both `W` entries equal to the item are cleared. (A
  weapon of the inactive set therefore only loses its `W` entry.)
- armour: `E[es]` = 0, whatever was there.
- category 2: the first of `E[6]`, `E[5]`, `E[14]`, `E[15]` that equals the item is
  cleared; if none and `es` = 7, `E[7]` = 0.

Then the material sound for the local slot, `inventory_selectIdleAnim`,
`player_recalcStats()`.

### Type 4 — join panel: `inventory_onJoinPanel(panel, slot, levelUp)` 0x1c0360

All of it is this machine's menu state — the panel struct `g_itemPanels` 0x4f4040 + panel ×
0x74 gets its list state zeroed, +0x18 = word +0x70, +0x4c = 0, +0x24 = word +0x70 × word
0x4f4240; `inventory_refreshPanelModel(slot, panel, 0)`; byte 0x44fd7c = 0 on the machine
whose first local slot is `slot` — except with levelUp ≠ 0: `owner` = **the panel's own
word +0x34** (per machine); level-up sound if `owner` is local; `net_sendGameMsg` of
{9, owner, `R(owner)`+0x59}; `R(owner)`+0xed = owner, +0xee = 0; panel +0x50 = 5; level-up
flag byte 0x4f65c8 (+ panel × 0x74 offline) = 1.

### Type 5 — weapon class

`R`+0x4a86 = byte; `player_resetIdleAnim(slot)`. No recompute of statistics.

### Type 6 — stat point: `inventory_onStatPoint(slot, stat)` 0x1c2548

- stat < 4 (signed): if the stat-point byte `R`+0xec is not 0, word `R`+0x78 + 4 × stat += 1
  and the byte −= 1; sound for the local slot; if the byte is 0 (also when it already was),
  `R`+0xee = 1. **A negative stat passes this test** and increments a word before +0x78.
- stat 4–7: word `R`+0x68 + 4 × stat += 1 — base statistic stat − 4 for nothing.
- stat 8: skill points `R`+0xe8 += 1. Above 8: nothing.
- always `player_recalcStats()`.

The script built-in `playerAdjustStat` calls the handler directly (`docs/ui.md`), which is
where 4–8 come from.

### Type 7 — skill point: `inventory_onSkillPoint(slot, kind, value)` 0x1c2648

Nothing if skill points ≤ 0. One point always buys exactly one rank; class, level,
prerequisites and price are not looked at (**Unknown** whether the sending screen sends
several messages for a dearer rank).

- kind 0 — value is a passive's mask (sign-extended to 64 bits): if
  `player_getPassiveLevel` < 20: points −= 1, `player_rebuildAbilities(mask, slot, −1)`
  (5.6), then the passive's level byte = level + 1. A mask the class does not have still
  costs the point.
- kind ≠ 0 — value is a skill id: if the rank (pairs at `R`+0x4b08) < 20: points −= 1;
  rank > 0 → rank + 1; else if the skill object's kind word (+8) is 3 → rank 1; else
  `player_addSkillAbility(id, slot)` (5.6).

No `player_recalcStats`.

### Types 8, 9, 10

- 8: `inventory_combineGems(slot, bag, descriptor, item)` 0x1ceeb8, section 6.
- 9: `R`+0x58 = level byte (the level the attack rating uses).
- 10: `Player_usePotion(player object of the slot, kind, column, row, panel)` 0x1b9cb8
  (`docs/spec/player-tick.md`); a callback here.

## 3. Game channel (id 3, `hud_onMsg` 0x1d8ca0)

Jump table 0x53c350, fourteen entries; a type byte above 13 does nothing.

| Type | Bytes | Layout after the type | Sender |
|---|---|---|---|
| 0 | 4 | slot, button, ability index | `hudmsg_sendQuickSlot` 0x1de06c from `hud_spellSelect` |
| 1 | 16 | slot, ability index, 0, u32 kind, u64 value | `hudmsg_sendAssignSpell` 0x1de3ec, same |
| 2 | 4 | slot, state, flag (not read) | `hudmsg_sendMenuState` 0x1de0dc, net games only |
| 3 | 2 | slot | `hudmsg_sendRecall` 0x1de138 from `player_pollRecallButton` 0x1bce88 and the pause menu (0x18db80) |
| 4 | 2 | slot | `hudmsg_sendPlayerLeft` 0x1de16c |
| 5 | 8 | three bytes (each 5), u32 object address | `hudmsg_sendSavepoint` 0x1de1a0 |
| 6 | 2 | slot | `hudmsg_sendDisconnectRequest` 0x1de1e0: the first local slot |
| 7 | len + 2 | level name, 0 | `hudmsg_sendNewWorld` 0x1d9250; called only in a net game (0x18dd4c) |
| 8 | 1 | — | `hudmsg_sendExitCountdown` 0x1de25c |
| 9 | 1 | — | `hudmsg_sendChecksumStart` 0x1de430 |
| 10 | 12 | slot, 0, 0, u32 live checksum, u32 saved checksum | `net_sendChecksums` 0x1de46c |
| 11 | **4** | 0, 0, 0 — the name is not part of the message | `hudmsg_sendLoadLevel` 0x1de598; called only offline (0x18dd6c) |
| 12 | 1 | — | `hudmsg_sendMedalAck` 0x1de5ec |
| 13 | 3 | slot, ability index | `hudmsg_sendQuickCastWarn` 0x1de0a4 from `hud_spellSelect` |

- **0** `hud_onQuickSlot(slot, button, index)` 0x1de28c: sound for the local slot. button 0
  binds `R`+0x4a84, any other `R`+0x4a85; if the other button holds `index` it receives
  this button's old value (exchange). The index is not range-checked.
- **1** `hud_onAssignSpell(slot, index, kind, value)` 0x1de61c. `rec` = ability record
  `R`+0x4440 + index × 0x68. Search records 0–7 for the value — kind 1: s16 id at +0x20
  equal to the 64-bit value; otherwise u64 mask at +0x48 — the last match is `found`. If
  found: that record takes over what `rec` holds: mask = all ones, id = `rec`'s id, and if
  that id is not −1: when `rec`'s name contains the marker name, the marker name (9
  bytes), kind byte +0x25 from the skill object, level byte +0x24 = the skill's rank;
  otherwise `player_rebuildAbilities(0x20000, slot, found)`. Then kind 1: `rec` gets the
  marker name, every one of records 0–7 whose id equals the value has its id set to 0, then
  `rec` id = value, kind from the skill object `g_skillTable[value]`, level = rank; other
  kinds: `player_rebuildAbilities(value, slot, index)`. Sound for the local slot. Index and
  skill id are not range-checked.
- **2** menu state (0x1d8d50): nothing when the slot's object pointer is 0. state ≠ 0:
  object flags (+0xc) |= 0x400000, `R`+0x4bc8 = 0, and for state ≥ 2 (signed) |= 0x800000.
  state 0: `net_maskLocalButtons(slot, 60, 0xf0)` 0x13e540 — entry slot × 12 of 0x5d0bc8:
  frames = max(old, 60), mask = 0xf0, third word 0 —, `R`+0x4bc8 = 10, flags &= ~0x800000.
- **3** recall: nothing while `dialog_isOpen()` or `task_isRunning("missionmenurun")`.
  `recall_execute(slot)` 0x18c230: `pauseMenu_close()`; an error text for everybody
  (`hud_showMessage(text, 180, −1, 0)`) when `game_inNoSaveZone()`, when hit points ≤ 0,
  or when the level name 0x41b721 contains "hub" and the stored return level `R`+0x24 is
  "None". Outside the hub it needs a recall potion: with a player object and hit points
  above 0, the first record of bag 2 (index below the count) whose definition name is the
  recall potion's has its count reduced by 1 and is removed with
  `inventory_removeItem(slot, i, 2, 0)` when that reaches 0; without one, an error text
  for the owner and return. Then `g_recallCountdown` 0x41b51d = 60; for each entry of the
  alive list, `pool_new(0x60)` and, if it gave a block, `RecallEffect_ctor(block, that
  player's position)`; a sound on **every** machine; `stream_queueStop(2)` if
  `audio_streamStatus(2)` & 0x40; `g_menuInputLockout` 0x41b4fc = 60, `g_paused` = 0, byte
  0x44fa80 = 0. Back in the handler: `net_closeLocalMenus(0)` if the countdown byte is not 0.
- **4** player left (0x1d8e40): `hud_showMessage(name + " " + text, 300, −1, 0)`; if the
  slot has an object: flags &= ~0x400000, the object's virtual slot 2 with (0, 0x20000040;
  1,000,000.0) — the damage call —, then `Player_processDamage(object)`.
- **5** `Savepoint_startSavedEffect(address)`: the address goes to the callee unchecked.
- **6** disconnect request (0x1d8f5c): nothing on the machine that owns the slot. Elsewhere:
  if the alive count is 1 and the one alive is this slot, the first other active slot `i`
  gets `player_respawn(i, leaver's position, leaver's facing, 2, 8)` (the leaver's object
  pointer is used without a test); then `net_disconnectPlayer(slot, 1)`.
- **7** new world (0x1d9004): `strcpy` of the name to `g_pendingLevel` 0x41b6d0 — no
  length limit; the sender's own buffer holds 79 characters, the wire 253 —, byte 0x41b720
  = 0xff, `pauseMenu_close()`, lockout word = 60, `g_paused` = 0, byte 0x44fa80 = 0, stream
  stop as in 3.
- **8** `g_exitCountdown` 0x4f694a = 240 in a net game, 1 offline.
- **9** checksum count byte 0x86aaa8 = 0, word 0x4f7138 = 1.
- **10** (0x1d90a4) received[slot] = the two words; count += 1; when the count (as a signed
  byte) equals `g_numPlayers`: for every player and both words, a difference from this
  machine's expected table 0x86ab38 sets `g_checksumFailed` 0x4f7144 and, unless that
  player is this machine's first local slot, calls `net_disconnectPlayer(i, 1)` — twice
  when both words differ.
- **11** load level (0x18cb80): like 7 with the name read at **payload + 4**, and byte
  0x44f208 = 0 as well. Since the message is four bytes long, the name is not on the wire:
  offline the handler runs on the sender's buffer, where the name follows; in a net game it
  would read whatever the previous messages left in the tick's buffer. The game never sends
  it in a net game.
- **12** word 0x4f7140 = 1.
- **13** `hud_onQuickCastWarn(slot, index)` 0x1de340 — more than a warning: with no cast
  queued (object +0x488 = 0), an ability of kind 1 (+0x25) shows the warning text to the
  owner; any other kind is **queued**: object +0x488 = address of the ability record, when
  the object's action state +0x58c is 2. No test for a null object.

## 4. Shop channel (id 7, `shop_onMsg` 0x1c5d28)

| Type | Bytes | Layout | Sender |
|---|---|---|---|
| 0 | 8 | slot, 0, 0, u32 address of a stock record | `shopmsg_sendBuy` 0x1c5f78: the **last** record of the three stock lists that is the same item as the chosen grid copy; nothing is sent when none is |
| 1 | 13 | as inventory type 0, mode 1 | `itemList_input` (a copy of the sender is 0x1d1330) |

Any other type does nothing. Both first call 0x1bf5a0, a loop without effect.

- **Buy** `shop_buy(slot, record)` 0x1d1240. factor = 0.6; 0.45 for category 1; 1.0 for
  record flags & 0x30000000000 or `es` = 8. price = trunc(`item_getValue(record)` × factor)
  in single precision (0.6 is 0x3f199999, so a value of 100 costs 59). If gold `R`+0xe4 ≥
  price (signed): gold −= price, then `inventory_giveItem(slot, record, 1)` (5.1) **whose
  result is ignored**: with a full bag, or one of the two single-copy items already held,
  the gold is gone and nothing arrives. The stock record is not changed and not checked:
  the address may be any readable item, e.g. one in a player's bag.
- **Sell** (0x1c5d70). `item` as in drop step 1, **without** the empty-cell test: the
  value of an empty cell is computed through a null definition pointer before
  `inventory_dropItem` rejects the cell. v = float(`item_getValue(item)`); × 20 for the
  kinds that leave 20 at a time (drop step 6, stem at 0x538660); paid = trunc(v / count ×
  0.05), at least 1; 0 for `es` = 8 or definition flags bit 46. gold += paid, capped at
  99,999,999. Then `inventory_dropItem` with the message's seven fields.

## 5. Inventory operations

### 5.1 `inventory_giveItem(slot, item, announce)` 0x1c1868 → index or −1

1. bag = the definition's category. `had` = some player's byte `R`+0x4c25 is 1 (offline: any
   of the `g_numPlayers` players; net game: this slot's).
2. Stackable (item flag 0x100): the first of the 64 cells with the same definition, flags,
   prefix and suffix gets count += the new count (16-bit, no limit); `player_recalcLoad`,
   `player_countPotions(slot, 0)` and `(slot, 1)`, `player_recalcStats`; return its index.
   Before the add, the first-recall hint (below) under: difficulty word 0x4f719c = 1, not
   `had`, announce ≠ 0, the name is the recall potion's, `vars_get` of the hint variable = 0,
   offline.
3. If the name is one of the two single-copy names (0x537e08, 0x537e10) and a record below
   the count has the same name: return −1.
4. cell = bag + count × 0x48. If its definition pointer is not 0: return −1. With count =
   64 the "cell" is the count word itself, so a full bag ends here: **a bag holds 64**; the
   63 of the pick-up code (`docs/issues/kill-loot-xp.md`) is the caller's own test.
5. Copy the 0x48 bytes; the hint under: announce ≠ 0, recall potion, `vars_get` = 0,
   offline, not `had` (the variable is asked before the last two); the two
   `player_countPotions` calls; stamp +0x22 = count; `player_recalcStats`; count += 1;
   return the old count. No `player_recalcLoad` on this path.

Hint: `R`+0x4c25 = 1, `vars_set(variable, 1)`, `hud_showHelpMessage(slot, two texts)`.

### 5.2 `inventory_removeItem(slot, index, bag, panel)` 0x1c1cb0

No argument is checked and the definition pointer of the cell is followed without a test.

1. Clear the equipment pointer naming the record: rings look at `E[5]` then `E[6]`,
   earrings at `E[14]` then `E[15]`, everything else at `E[es]`.
2. If `W[active set]` is the record: class = 5, `player_resetIdleAnim`. Then `W[0]` is
   cleared if it is the record, else `W[1]` if it is.
3. While index < count − 1: copy the next record down, repoint all 17 `E`, both `W` and
   `second` from the old address to the new one, zero the definition pointer of the vacated
   cell.
4. Per machine: if `net_isLocalSlot(slot)` and `g_localMenuOpen` 0x41b69d and the grid
   pointer are all non-zero, every non-empty cell of grid (panel, bag) gets its stamp set
   to the index of the (last) bag record that is the same item.
5. Stamps of the records from the removed index to the old last index − 1 are reduced by
   1; definition pointers from the new end to cell 63 are zeroed (from `index` when it was
   the last or beyond); count −= 1 (**also when the cell was empty or the index beyond the
   count**); `player_recalcStats()`.

### 5.3 Equip, unequip

Sections 2 type 1 and type 2. In short: weapons belong to set 0 (melee) or set 1 (bow,
thrown) and equipping selects the set; a two-hander empties both hands and, unless it is a
bow or thrown weapon, the shield; a one-hander evicts a two-hander; with the dual-wield
passive a second one-hander goes to `E[1]` / `second` and evicts the shield; a shield
evicts a two-hander (not a thrown weapon) or the second weapon; rings and earrings fill the
second slot when the first is taken. Requirements are tested once, at equip.

### 5.4 Drop, stacks

Section 2 type 0. A stack shrinks by one per message, by up to 20 for ammunition and
thrown weapons; the dropped object carries what was taken. Stacks merge only in
`inventory_giveItem` (5.1 step 2); nothing splits a stack except drop and sell.

### 5.5 `inventory_unrefItem(slot, item)` 0x1c3350 (dual wield)

- item == `W[0]`: `W[0]` = 0, `E[0]` = 0, **send** inventory message 1 {quiet 0, slot,
  `second`} (the second weapon becomes the weapon), `E[1]` = 0, `second` = 0. In a net
  game the equip then happens once per machine, frames later; until then the player holds
  nothing in set 0.
- item == `second`: class = 0, `second` = 0, `E[1]` = 0, the two animation calls.

### 5.6 Ability records and ranks

- `player_getSkillRank` 0x1bf330 / `player_setSkillRank` 0x1bf3a0: {s16 id, s16 rank}
  pairs at `R`+0x4b08, id −1 ends the list. Set appends where the −1 was and writes no new
  terminator.
- `player_getPassiveLevel(slot, mask)` 0x1bed48 / `player_raisePassiveLevel` 0x1bedd0:
  the class table 0x4ef538 + class × 0xa88 has 48 entries of 0x38 bytes starting with a
  u64 mask; the level byte is `R`+0xef + entry. Negative bytes read as 0; a slot above 4
  reads as 0; raise only stores a higher value.
- `player_addSkillAbility(id, slot)` 0x1d32e4: nothing for a skill of kind 3 or when a
  record with the marker name already has the id; else the first of the 15 records whose
  id is −1 is zeroed, named with the marker, id, level byte 1, kind from the skill object;
  rank = max(rank, 1).
- `player_rebuildAbilities(mask, slot, index)` 0x1d34ac: index −1 picks the first record
  with id −1, or none when the mask is already in `R`+0x128. The row of the old-ability
  table 0x4f5cc8 (0x68-byte rows, ended by the name "END") whose mask (+0x48) equals `mask`
  is copied into the record (all fields from the name to +0x63; not for a row whose id is
  0x1d); mask 0x40 adds 15.0 to the load limit `R`+0x124; 0x80 adds 3.0 to hit points and
  their maximum, 0x100 adds 5.0 to mana and its maximum (each clamped to the maximum);
  `R`+0x128 |= mask. A mask with no row does nothing.

### 5.7 What recomputes

| Operation | `player_recalcStats` | `player_recalcLoad` | others |
|---|---|---|---|
| drop, sell | yes (twice when the record is removed) | yes | idle animation calls |
| equip, unequip | yes | no | idle animation calls |
| give (buy) | yes | only when stacked | `player_countPotions` × 2 |
| stat point | yes | no | |
| skill point, assign, quick slot, weapon class, level byte | no | no | |

`player_recalcStats`, `player_recalcArmor` and `Player_recalcDamage` are
`tools/ref_combat.py`.

## 6. Gem combining — `inventory_combineGems(slot, bag, descriptor, item)` 0x1ceeb8 (**Observed**, not modelled)

Message 8 carries two addresses. `descriptor` is a string "…+token+token" from the gem
table 0x4f42a8 (rows of three pointers: gem name, text for weapons, text for armour — in
the executable, so the same everywhere). `item` is the address of the record to improve.

1. The descriptor is copied to a 208-byte stack buffer and cut at each '+'.
2. `rec` = the record of (slot, bag) whose index is **the stamp at `item` + 0x22** — the
   handler finds the record through the stamp and writes through the address.
3. For each token: count `rec`'s used modifier slots (code ≠ −1). More than 3 — or more
   than 2 when the descriptor contains one of two damage words (0x5396e0, 0x5396f0) —
   refuses with a notice (sound for the local slot; panel flag as in equip) and returns 0.
4. The token is matched against the list of formats the descriptor parser uses
   (`docs/spec/items.md` section 3.2). If `rec` already holds that modifier code with a
   non-zero value: a second notice, return 0.
5. Otherwise the modifier is written into the first slot of the item **at the address**
   whose code is −1 or the same code. Returns 1.

The sending side (`workshop_input` 0x1d0b90, draw code): refuses a target with a suffix,
ammunition, category ≥ 2 or flag 0x1000000 by itself; runs this handler directly on each
matching grid copy first (which changes only the copies) and sends nothing if that returned
0; then sends message 8 with the record's address, a drop message with mode 2 for the gem,
and calls `player_recalcLoad(slot)` on its own machine.

The handler does not call `player_recalcStats`. Not executed: `tools/ref_messages.py`
passes message 8 to a callback.

## 7. Validation: what a wrong message does

| Message | What is checked | What is not |
|---|---|---|
| any | type byte within the table | slot (signed, indexes `g_players` as is); length |
| drop | the cell's definition pointer ≠ 0 | index against count, bag 0–2, panel 0–3, a null player object (writes address 0x47a) |
| equip | definition ≠ 0; the requirement test; `es` ≠ 0x10 | that the address is one of the player's records |
| unequip | nothing | definition ≠ 0; that the item is equipped (an armour message empties the slot of that kind whatever is in it) |
| stat point | stat < 4 selects "spend" | stat ≥ 0 |
| skill point | points > 0; rank or level < 20 | id / mask exists for the class; price |
| quick slot, assign | — | ability index 0–14, skill id |
| menu state | object pointer ≠ 0 | — |
| recall | no-save zone, alive, target, potion | — |
| player left | object pointer ≠ 0 before the kill | — |
| disconnect, quick cast | — | the object pointers they follow |
| new world, load level | — | name length (unbounded `strcpy` into 0x41b6d0) |
| buy | gold ≥ price | that the address is a stock record; that the item was received |
| sell | (drop's test, after the gold) | the cell before its value is computed |

A stale drop — the record was already removed — is harmless when the cell is now empty and
acts on the record that moved into the cell otherwise. A stale equip of an address that
has since been vacated returns at once; one whose cell was refilled equips the new
occupant. In the differential test a departed player (object pointer 0) and a dead one
(hit points ≤ 0) change nothing except where the table says so.

## 8. Shared-seed draws

No handler draws from `g_randSeed` 0x404464 itself. Draws happen inside callees, in call
order: `world_findFreeSpot` (drop, mode 0: three per sample, up to 50 tries —
`docs/spec/world-queries.md`), the constructor of the dropped object (one, for its own
seed), `RecallEffect_ctor` per alive player, the damage call of message 4, `player_respawn`
of message 6. `game_sendCharacterToLobby` reads the seed.

## 9. Reads that are not lockstep state

| Read | Where | What it gates | Ledger |
|---|---|---|---|
| `net_isLocalSlot(slot)` | drop, equip (two places), unequip, stat point, join panel, quick slot, assign | a sound | by design |
| `net_isLocalSlot` + grid pointer 0x4ebbb0 (+ `g_localMenuOpen` 0x41b69d in remove) | drop steps 7 and 9, remove step 4 | writes into this machine's grid copies only. With the panel byte −1 that `Player_usePotion` sends, the "grid" is the 0x23988 bytes in front of the buffer's grids; a write needs a 0x48-byte pattern there equal to the item | K2, `docs/issues/draw-sim-leaks.md` |
| panel words 0x4f4078, 0x4f40ec | equip refusal, combine refusal | which panel shows the notice | draw-sim-leaks |
| panel struct, 0x4f4240, 0x44fd7c, 0x4f65c8 | join panel | menu state | draw-sim-leaks |
| **panel word +0x34** | join panel with levelUp | which record gets +0xed / +0xee written and which slot and level the nested message 9 carries. On a machine whose panel does not name the joining player the write goes to another record, or with −1 to the memory in front of `g_players` | draw-sim-leaks ("never sent with one player per machine"); detail new |
| first local slot, `g_simFrame`, seed | `game_sendCharacterToLobby` | which machine uploads to the lobby | by design |
| first local slot | `net_sendGameMsg` in a net game; checksum handler | whose ring; "do not disconnect yourself" | by design |
| this machine's expected checksums 0x86ab38 | message 10 | failure word, disconnect | `docs/ui.md` P9 |
| `net_isLocalSlot(slot)` | message 6 | the leaver's machine does nothing | by design |
| `audio_streamStatus(2)` | messages 3, 7, 11 | an audio call | — |
| pause-menu state inside `pauseMenu_close`, menus inside `net_closeLocalMenus` | messages 3, 7, 11 | local menus; a machine with its pause menu open sends a menu-state message from the handler (**Observed**, 0x18df90) | — |
| addresses in the payload | equip, unequip, combine, buy, savepoint | everything they point at; the stock table is per machine (`docs/ui.md` P1), a savepoint object per machine (P8) | P1, P8 |
| low memory through null pointers | unequip of an empty cell, sell of an empty cell, drop / quick cast / disconnect for a slot without an object, the K2 message for slots 1–3 | whatever the machine has at addresses 0x1c–0x58c | new, see 10 |

The handlers of messages 3, 7 and 11 **write** `g_menuInputLockout` 0x41b4fc = 60 on every
machine in the same frame; this is the word of D26, and here it is set in lockstep.

## 10. K2 as executed

`Player_usePotion` 0x1b9cb8 was run itself, on a two-player net game, for the owner's
machine (inventory screen open, grid built by the screen's own builder 0x1cbbe8 with one
cell per item) and for the other machine, and the message it queued was then executed by
the handler on both (property `K2 potion message`). Bag 2 held a non-potion (3), the health
potion the code chooses (2) and a mana potion (2).

- The other machine takes the potion at once: 3, 2, 2 → 3, **1**, 2. It sends nothing.
- The owner's machine keeps 3, 2, 2 and queues a drop message with mode 2, panel byte −1,
  column 0, row 0, and **bag and index taken from cell (0, 0) of the bag-2 grid of the
  panel whose number is the player's slot** (0x1ba3c8: slot × 0x23988).
- **Owner in slot 0.** The builder puts bag-2 record 0 into cell (0, 0) (first fit, record
  order). The message is {slot 0, index 0, bag 2}: every machine takes one from bag-2
  record 0 — owner 3, 2, 2 → **2**, 2, 2; other 3, 1, 2 → **2**, 1, 2. So the earlier
  write-up is right for this slot: "one of whatever is in the first cell", here not even a
  potion.
- **Owner in slot 1** (the case of `docs/issues/live-rig.md` 7.3). A net game draws its
  single panel as panel 0 whatever the local slot (`menu_openInventory` 0x1c15c8), so
  panel 1's grids are never built: their definition pointers were zeroed when the buffer
  was set up (0x1bfbc8) and their stamps hold what the buffer held. The potion code reads
  the bag byte through that null pointer (address 0x1d) and the stamp as index. With zeroes
  there the message is {slot 1, index 0, bag 0}: bag 2 is not touched by it (owner stays
  3, 2, 2, other 3, 1, 2 — what the rig logged), and **record 0 of bag 0 loses one** on
  both machines (in the test it was the last one, so the record was removed: 11 → 10).

So both readings were right, each for one slot. What the rig's message did depends on one
byte of low memory and on bag 0, neither of which was logged; with a zero byte the owner's
first bag-0 record (a weapon) silently lost one on both machines. **Unknown**: the byte at
address 0x1d on the console and on the live rig.

## 11. What the differential test covers

`python3 tools/difftest_messages.py` — 44 properties, all pass (seed 20973):

- `channel ids`: the seven registration functions, and the model's, give the table of 1.1.
- `senders`: 25 sender functions run for real with two stack fills; the queued bytes equal
  the model's encoders and do not depend on the stack.
- `K2 potion message`: section 10; the handler runs of it are compared with the model too.
- Eight runs of 2,500 messages (20,000 in all): 1, 2 and 4 players offline, 2, 3 and 4
  players in a net game, executed as the owner's machine, as another machine and as a
  machine with two local players, with the local menu flag and the grid pointer both ways,
  panel bytes 0–3 and −1, players made dead or object-less, bags filled to 63, records
  added between messages. Per run: calls with arguments, bytes written, their values, the
  seed, and "returned or stopped" are equal for every message. No message stopped on
  unmapped memory (the first page of memory is mapped as zeroes for null pointers).
- By type (one run of the default seed): drop 1,694, equip 2,555, unequip 1,282, join 388,
  class 434, stat 835, passive 615, skill 604, combine 389 (callback), level 396, potion
  426 (callback), other inventory types 1,292; quick slot 557, assign 843, menu 608,
  recall 608, left 197, savepoint 204, disconnect 396, new world 228, exit 198, checksum
  start 189, checksum 634, load level 170, medal 197, quick cast 623, other 393; buy 997,
  sell 1,355, other shop types 693.

Coverage of the original, basic blocks entered: **649 of 651** over the 29 functions that
run for real.

| Function | Blocks | Function | Blocks |
|---|---|---|---|
| `invmsg_dispatch` | 12 / 12 | `hud_onMsg` | 53 / 53 |
| `inventory_dropItem` | 69 / 69 | `hud_onQuickSlot` | 8 / 8 |
| `inventory_equipItem` | 114 / 114 | `hud_onAssignSpell` | 22 / 22 |
| `inventory_unequipItem` | 55 / 55 | `hud_onQuickCastWarn` | 6 / 7 |
| `inventory_unrefItem` | 6 / 6 | `net_maskLocalButtons` | 1 / 1 |
| `inventory_removeItem` | 55 / 55 | `recall_execute` | 30 / 30 |
| `inventory_giveItem` | 44 / 44 | load-level body 0x18cb80 | 3 / 3 |
| `inventory_onJoinPanel` | 10 / 10 | `shop_onMsg` | 14 / 14 |
| `inventory_onStatPoint` | 12 / 12 | `shop_buy` | 8 / 8 |
| `inventory_onSkillPoint` | 12 / 12 | `net_sendGameMsg` | 7 / 7 |
| `game_sendCharacterToLobby` | 16 / 16 | `net_registerMsgHandler` | 11 / 11 |
| `player_getSkillRank`, `player_setSkillRank` | 6 / 6, 8 / 8 | `player_addSkillAbility` | 14 / 14 |
| `player_getPassiveLevel`, `player_raisePassiveLevel` | 8 / 9, 6 / 6 | `player_rebuildAbilities` | 33 / 33 |
| `item_sameIdentityFields` | 6 / 6 | | |

The two blocks never entered: 0x1bed58 (a slot above 4 in `player_getPassiveLevel`) and
0x1de3a4 (a test of the address of an ability record against zero, which cannot be true).
The equip test 0x1c4948 and `item_getValue` 0x1024a8 also run for real; their model is
`tools/ref_items.py`.

Limits of the test, plainly:

- Slots outside 0–3 were sent only as −1 on the drop message. Other out-of-table slots,
  bag bytes outside 0–2 and unaligned addresses are described from the code, not executed.
- Callees are stubs: the statistics recompute, the animation calls, the weapon-swap helper
  (answers 0 or 1, changes nothing), object constructors. The seed is advanced by the
  stubs, so "seed" checks order and that the handlers add no draw of their own.
- The three skill objects of kind 3 were made by the test: in the interpreter every skill
  object's kind word reads 0 after the class tables are built (**Unknown** where the game
  fills it).
- Floating point occurs only in the shop prices, the three bonus masks and the recall's
  hit-point tests; results are bit-identical under the interpreter's 'ps2' model. The
  operations are int→float, one multiply or divide by a constant, truncation, and adds of
  small integers, none of which depends on the adder's guard bits in practice
  (`docs/issues/dynamic-tests.md`).
- `sprintf` (used only to copy a sound name) is replaced, because the library's own keeps
  state outside the game's data.

## 12. Corrections to earlier documents, proposed ledger rows

Corrections (all **Executed** unless noted):

- `docs/ui.md` and `docs/netcode.md`, game message 11: it is four bytes long; the level
  name is not in the message. Its only caller runs offline; message 7 is the net form.
- `docs/ui.md` and `docs/netcode.md`, game message 13 ("HUD text", "quick-cast warning"):
  the handler queues the cast (object +0x488) for abilities whose kind is not 1; the text
  is the other branch.
- `docs/ui.md`, inventory message 0 layout "slot, u16, item index u32, u16, bag, 2 bytes":
  the fields are slot, column, index, row, bag, panel, mode.
- `docs/ui.md`, inventory message 8 "slot, 3 × u32": bag, descriptor address, item address.
- `docs/ui.md`, "price × 0.6 … if the player has the gold, and calls `inventory_giveItem`":
  the gold is taken whether or not the item is received.
- `docs/ui.md`, shop message 0: the address sent is that of the last identical stock
  record, and nothing is sent when the grid copy matches none.
- `docs/issues/kill-loot-xp.md` K2, step 2 and verdict, and `docs/issues/live-rig.md` 7.3:
  the cell read is that of the panel numbered like the slot. "Removes one of whatever sits
  in the first cell of its potion list" holds for slot 0 only; for slots 1–3 in a net game
  the message names a record through a null pointer (section 10). The "last byte −1 …
  *Inferred* out of range" is confirmed: the panel byte is −1 and addresses the memory in
  front of the grids.
- `docs/issues/kill-loot-xp.md` section 4, "bag … already holds 63 items → refuse" is the
  pick-up's own limit; `inventory_giveItem` fills a bag to 64.
- `docs/player.md`, +0x43f0 table: slot 1 is the second weapon's slot, slot 7 a single
  category-2 slot (**Observed** in unequip), neither listed there.

Proposed ledger rows:

| Row | Statement | Status | Where |
|---|---|---|---|
| M1 | The K2 drop message names bag and index from the grid of the panel whose number is the owner's slot. Slot 0: bag-2 record 0. Slots 1–3 in a net game: a never-built grid, so bag = the byte at address 0x1d and index = a stale stamp; with zeroes, bag-0 record 0 loses one on every machine | Executed (interpreter); the low-memory byte Unknown | 0x1ba3c8, 0x1c4310; `tools/difftest_messages.py` K2 |
| M2 | Message handlers do not range-check slot, index, bag, stat or ability index, and equip / unequip / buy / combine / savepoint act on addresses from the wire; only an empty cell (drop, equip) and the requirement test stop a handler | Executed for the cases of section 11, Observed for the rest | section 7 |
| M3 | `shop_buy` deducts the price and ignores `inventory_giveItem`'s refusal (bag at 64, single-copy item held) — the same on every machine | Executed | 0x1d1308 |
| M4 | `inventory_unrefItem` and `inventory_onJoinPanel` send a game message from inside a handler: one copy per machine in a net game. The join-panel copy carries the slot found in each machine's own panel struct | Executed (one machine at a time) | 0x1c33b0, 0x1c0478, 0x1c0400 |
| M5 | Game message 11 is sent with length 4; its handler reads the level name past the length | Executed | 0x1de5cc, 0x1d920c |

No patch is proposed here; K2's patches are in `docs/issues/kill-loot-xp.md`.

Names used here for functions nobody had named (no symbol file was written):
`recall_execute` 0x18c230 is in `symbols/engine.tsv`; the load-level body
0x18cb80, the empty shop helper 0x1bf5a0 and the grid builder 0x1cbbe8 (`itemGrid_build`
would fit: fills one panel's three 9 × 75 grids from a player's bags or the shop stock) are
unnamed.

## 13. Not done

- `inventory_combineGems` 0x1ceeb8 (6,964 bytes) is described from the decompile and is a
  callback in the model: its 40-odd token formats were not executed.
- `dialog_onMsg` 0x22ee2c (five types, `docs/audio-save.md`), the cutscene, voice and text
  channels: callbacks, not read again.
- `Player_usePotion` behind inventory message 10 is `tools/ref_player.py`'s; here it was run
  for real only in the K2 property.
- `player_recalcStats` and friends are not wired in: after a handler the derived fields
  are whatever `tools/ref_combat.py` makes of the record.
- Two machines were never run against each other here: each run is one machine's view.
  That the same message gives the same record on an owner's and another machine follows
  from the per-machine reads of section 9 gating nothing shared, which the runs show for
  each machine kind separately.
- The senders' local conditions (which button, which screen state) are taken from
  `docs/ui.md`; only their byte output was executed.
