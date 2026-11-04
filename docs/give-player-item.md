# What `givePlayerItem` does with a quest item

2026-11-03. The campaign inventory note still lists this grant as open
(`t3/research-inventory-reset` `6f8beb9`, `docs/inventory-reset.md` lines 21 and
125). Starting equipment is a different caller. `player_initNewCharacter`
`0x1b1d70` calls `player_giveStartingItems` `0x1acc78` once, and that function
calls `item_parseDescriptor` and `inventory_giveItem` itself. It does not enter
`givePlayerItem`. The executed starting-equipment mapping stays
`t3/research-loading-readiness` `366b65a`, `docs/starting-equipment-r4.md`
lines 19–25. This note is only the script native.

**Evidence convention:** Observed below includes **Executed** original EE
instructions on constructed state, seeds 20973 and 7. Addresses are US v2.00.
No game text, disassembly, or disc bytes are stored here. Nothing was seen on
a running game. `player_recalcStats` `0x1b6458`, `player_resetIdleAnim`
`0x1b2470`, `player_countPotions` `0x1ba5f8`, `inventory_selectIdleAnim`
`0x1c3f08`, the three sound players, `hud_showPlayerNotice` `0x1d9954`,
`text_lookup`, `vars_get` / `vars_set`, and `pool_new` `0x14fdb8` (returning 0)
are stubbed. `net_isLocalSlot` `0x13e150` returns 0.

## Argument contract

**Observed / Executed:** native index 53. The table at `0x403370` is 8-byte
records. The handler word of record 53 is `0x145a88`.

The script calls it through `scr_callNative` `0x141050` `(machine, index, &PRI,
params)`. A one-native image whose only name is this command was loaded with
`scr_load` `0x13e8f8` (return 0) and bound with `scr_registerNatives` `0x141310`
(return 0). The bound cell is `0x145a88`. `params[0]` is the byte count. The
handler does not read it. The three cells are the descriptor, equip, and
usePresets.

`item_parseDescriptor` `0x1069b8` is entered from inside `0x145a88`–`0x145d20`
with variant −1 and with usePresets equal to the third cell. Executed for
usePresets 0 and 1, on categories 0, 1 and 2. The older built-in row in
`docs/spec/script-builtins.md` line 642 calls that third cell a variant. The
value the parser receives in its fourth register is usePresets. The variant
register is −1 either way.

`item_randomizeVariant` `0x1046e0` still runs. On a definition whose variant
count (flag bits 11–15) is 0, the seed at `0x404464` does not move.

## Which record, which bag

**Observed / Executed:** the loop is slot 0 while the slot is below
`g_numPlayers` `0x4d8ae0` (the count is re-read). A record at or above that
count is not written. With two players, slots 0 and 1 each receive the item
and slot 2 does not.

While the medal word `0x4f713c` is nonzero, only the medal player (byte
`0x4f7148`) is visited. Executed with that byte set to 1: slot 0 stays empty
and slot 1 receives the item.

The bag is the definition's category byte at `+0x1d`. An empty bag receives
the item at index 0. The halfword at cell `+0x22` is 0. The other two bags
stay empty. Executed for categories 0, 1 and 2.

## Stacking

**Observed / Executed:** flag bit 8 (`0x100`) adds the new count into the
first cell that has the same definition, the same flags, the same prefix byte
`+0x20` and the same suffix byte `+0x21`. The bag count stays 1 and the next
cell stays empty. The added count is the definition's count halfword. Changing
the first cell's prefix byte makes the next give append a second cell. This is
the same match `inventory_giveItem` `0x1c1868` already uses.

## A full bag

**Observed / Executed:** `inventory_giveItem` writes at index `count`, and
only when that cell's definition word is 0. Count 63 appends at index 63, the
stamp is 63, and the count becomes 64.

Count 64 makes that address the count word itself. The word is 64, so the
give returns −1 and copies nothing. The handler does not test the result. The
64 cells stay empty, the count stays 64, and the handler's result is still 0.
`player_recalcLoad` `0x1bec10` still runs. Each empty cell inside the count
weighs 1.0, so record `+0x120` becomes 64.0 (`0x42800000`).

When equip is nonzero, `inventory_equipItem` `0x1c27c0` is still called, with
the address `0x48` bytes before the bag and with quiet 0. That word was 0, so
equip returns without writing an equipment pointer.

## Weight, and the value the script sees

**Observed / Executed:** carried `+0x120` + weight `<` limit `+0x124`, or the
weight is exactly 0. A positive weight at limit 0 calls `pool_new(0x190)` and
does not touch the bag. `pool_new` returned 0, so `ItemProp_ctor2` `0x1590ec`
was not entered. The handler result is 0.

A definition whose weight word or count halfword is 0 can be given at limit
0. Among rows with no variant bits, slot other than 8, and without the thrown
axe bit, 44 have a zero count or a zero weight word, and one of them was
given. **Unknown:** whether each of the other 43 is given. The exception is
this call, not a claim about every row.

The handler result is 0 on a successful give, on the full bag, and on the
drop. Through `scr_callNative`, PRI becomes that 0 and the dispatcher's own
result (machine error `+0x5c`) is 0. The script cannot tell a gift from a
lost item.

## Flag 39 and the keep list

**Observed:** 43 base definition rows have flag bit 39 set. All 43 use
category 2, so a script gift of one of those rows goes to bag 2.

**Observed / Executed:** one such row was given with its own flags, not a
forced bit. It landed in bag 2 with bit 39 set. `givePlayerItem` does not
call `player_removeFlag39Items` `0x1be1d8`.

The keep list belongs to that remover. After three flag-39 cells were stored,
their definition name pointers were aimed at `pickaxe`, at a name containing
`bloodstone`, and at a name on neither list. `player_removeFlag39Items` kept
the first two and removed the third, through the real `inventory_removeItem`
`0x1c1cb0`. The exact names and the contained strings are the list already
specified on `t3/research-quests` `7efd3ce`, `docs/quests.md` lines 163–169.
This run used one exact name and one contained string.
**Unknown:** the other exact names and `shardof` were not passed to this
remover again here.

## Equipment

**Observed / Executed:** equip nonzero calls `inventory_equipItem(slot, cell,
0)` and then `player_resetIdleAnim(slot)`. The idle call's site is inside
`0x145a88`–`0x145d20`. Its body is stubbed.

The comparison row at `0x3f7f50` is the class-0 starting weapon from the
loading-readiness note. Here the caller was `0x145a88`, not `0x1acc78`.
`inventory_checkEquipAllowed` `0x1c4948` returned 0. The equipment pointer at
record `+0x43f0 + 4 × slot` became the new cell, and the weapon-class byte
`+0x4a86` became the definition subtype. `script_runByName` `0x1ed694` was
called once. `g_scriptMachine` `0x86b270` was 0, so that call returned without
a level script.
**Unknown:** the weapon and bow hooks when a level script is loaded. Equip
sounds and the notice box were stubbed.

An item with flag bit 41 is still placed in the bag. Equip is called and does
not leave that cell in the equipment slot.

## What is not this function

**Observed**, from the `jal` targets in those ranges, not from running them:

| Range | `givePlayerItem` | `inventory_giveItem` | `inventory_equipItem` | `item_parseDescriptor` |
|---|---:|---:|---:|---:|
| `player_giveStartingItems` `0x1acc78`–`0x1b1d70` | 0 | 320 | 82 | 323 |
| `player_initNewCharacter` `0x1b1d70`–`0x1b2470` | 0 | 0 | 0 | 0 |

`player_initNewCharacter` has one `jal` to `player_giveStartingItems`. Character
creation never enters `0x145a88`. This round did not re-execute `0x1acc78`.

## What the client can implement

A campaign client that already has the bags, `item_parseDescriptor`,
`inventory_giveItem` and `inventory_equipItem` can now implement the script
command:

1. `givePlayerItem(descriptor, equip, usePresets)` visits every joined slot, or
   only the medal player while `0x4f713c` is set. The script result is 0
   whether or not a cell was written.
2. Parse with variant −1 and that usePresets value.
3. The bag is category `+0x1d`. Bit 8 stacks when definition, flags, prefix
   and suffix match. If the cell at `count` is not empty, the item is lost
   and it is not dropped. Count 63 still appends. The following load
   recompute still runs.
4. Give when carried + weight is below the limit, or when the weight is 0.
   Otherwise the gift is a ground object. That constructor is still open, so
   a client without it should refuse the overweight drop rather than invent
   the prop.
5. A nonzero equip calls `inventory_equipItem` on the new cell with quiet 0,
   then the idle-anim reset. The −1 index from a full bag still makes that
   call; a zero definition word there changes no equipment pointer.
6. The 43 flag-39 base rows are bag 2 and keep the bit. Do not apply the keep
   list at give time. The act-change remover in the inventory-reset note does
   that later.

`giveOnePlayerItem` `0x145d20` was not re-entered. Its strict weight test
remains `docs/script-items.md` section 2.4.

## Unknown

- The body of `ItemProp_ctor2` when a gift does not fit. `pool_new` returned 0.
- Which of the other 43 zero-count or zero-weight rows are given at limit 0.
- `shardof` and the exact keep names other than `pickaxe`, on this call.
- Weapon and bow hooks while `g_scriptMachine` points at a loaded level.
- Equip sounds, the notice, `player_resetIdleAnim`'s body, and
  `player_recalcStats`.
- A preset descriptor under usePresets 1. The register was executed. The
  preset match was not the subject of this run.
- No running game was watched.

## Reproduction

From this worktree, with the private executable in ignored `local/`:

```sh
export PYTHONDONTWRITEBYTECODE=1
python3 tools/difftest_give_player_item.py local/SLUS_209.73 --seed 20973
python3 tools/difftest_give_player_item.py local/SLUS_209.73 --seed 7
```

Both seeds pass 45 checks: the native slot, the starting-item `jal` counts,
one bag per category, both players, medal mode, stacking, count 63 and 64,
the zero-weight give, the positive-weight drop, the equip pointer, flag bit
41, a retail flag-39 row, the keep and drop of `player_removeFlag39Items`, and
PRI 0 from `scr_callNative` on a success and on a full bag. Existing
`difftest_script_items.py` vectors are not edited.
