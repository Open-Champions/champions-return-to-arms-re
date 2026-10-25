# Item, gold, skill and monster-builder script commands

US `SLUS_209.73` v2.00. This note is the contract for the level-script commands the
native client still refuses because their bodies were not documented: the item
commands (have, count, give, take, equip, the load limit, gold), `clearAllSkills` and
its overlap with the mission bytes, how a script or the arena builds a monster, and
`game_scanCm1Vars(0)`.

The command wrappers were already run against the original with their callees stubbed
(`tools/difftest_natives.py`, `docs/script.md`, `docs/spec/script-builtins.md`). What is
new here is the callees and the composition. `inventory_giveItem`,
`inventory_removeItem` and `inventory_equipItem` were already executed through the
inventory messages (`tools/ref_messages.py`, `docs/spec/game-messages.md` 5), and
`item_parseDescriptor` and `item_getWeight` through the item tests
(`tools/ref_items.py`, `docs/spec/items.md`). This note composes them with the commands.

| File | What |
|---|---|
| `tools/ref_script_items.py` | model: bag scans, item weight, carried load, load limit, the 12 item and gold handlers, `clearAllSkills`, `game_scanCm1Vars`, `game_set4f7110` |
| `tools/ref_monster_build.py` | model: `arena_spawnMonster`, `ScriptGenerator_spawn`, the `generateMonster` name table, the factory rows of the arena names |
| `tools/difftest_script_items.py` | runs the originals in `tools/ee_emu.py` and compares them with the model |
| `tools/difftest_monster_build.py` | the same for the monster builder |
| `tools/test_ref_script_items.py`, `tools/test_ref_monster_build.py` | 40 synthetic tests, no game file needed |
| `tools/items_census.py` | disc counts (counts only) |

"Executed" below means run in `tools/ee_emu.py` against the model by one of the two
difftests. Nothing here was seen on a running game.

## 1. State

Player record (`g_players` 0x4d8af0, stride 0x4c30; `docs/player.md`):

| Offset | Type | Use here |
|---|---|---|
| +0x50 | s32 | class, selects the class-skill table `0x4ef538 + class × 0xa88` |
| +0x90 | s32 | effective strength, read by the load limit |
| +0xe4 | s32 | gold |
| +0xe8 | s32 | skill points (`clearAllSkills`) |
| +0xef | s8[48] | class-passive levels, parallel to the 48 rows of the class-skill table |
| +0x120 | float | carried load |
| +0x124 | float | load limit |
| +0x128 | u64 | cleared by `clearAllSkills`; meaning unknown |
| +0x130 + bag × 0x1208 | item[64] | three bags of 0x48-byte records; count s32 at +0x1200 of each bag |
| +0x43d8 | ptr | the Player object; object +0x0c bit 3 (8) is "dead", +0x10 the position, +0x3c8 the slot |
| +0x43f0 | item*[17] | equipment slots, cleared by `inventory_removeItem` for the entry it removes |
| +0x4434, +0x4438, +0x443c | item* | weapon set 0, weapon set 1, second weapon |
| +0x4460 + k × 0x68 | s16, u8 | ability record k: skill id and the byte at +4 |
| +0x4a80, +0x4a84, +0x4a85 | u32, u8, u8 | ability pad mask; records bound to buttons A and B |
| +0x4b08 | {s16 id, s16 rank}[48] | skill ranks, the list ends at the first id −1 |
| +0x4bbf + d × 13 + m | u8 | mission byte, difficulty d 1..5 (section 4) |

Globals:

| Address | What |
|---|---|
| 0x4d8ae0 | `g_numPlayers` |
| 0x4d8ae8 | `g_loadLimitBonus`, a word that only `player_recalcStats` reads (section 2.3) |
| 0x4f713c | medal mode: non-zero means give only to the medal player |
| 0x4f7148 | the medal player, u8 (written by the mission menu) |
| 0x4f8440 | `g_alivePlayers[]`; entry 0 is the fallback drop position |
| 0x4f719c | `g_difficultyIdx`, 1..5; the executable image holds 1 |
| 0x404464 | the shared seed |
| 0x41b170 | `g_skillTable`, a pointer per skill id. Entries 0x49 (Axe Bandolier, at 0x41b294) and 0x4a (Light Quiver, at 0x41b298) are passed to the weight complements |
| 0x4f7110 | `g_cm1Index` (section 6) |
| 0x5d32c8, 0x4f8409 | the `generateMonster` name table and its s8 count (section 5.3) |

## 2. Items

### 2.1 Looking (Executed, suite `helpers` and the handler suites)

`inventory_countItemByName(name, slot)` 0x1c5880 visits bags 0, 1 and 2. In each bag it
visits entries 0 up to the bag's count, and re-reads the count after every entry. Each
entry whose definition name (the string at definition +0) equals `name` under
`libc_strcmp` adds its s16 stack count at +0x04. The sum is 32-bit. The comparison is
exact and case-sensitive. The definition pointer is not tested: an entry inside the count
with definition 0 reads its name pointer from address 0. The slot is not range-checked.

`inventory_findItemBySubstring(slot, text, *index, *bag)` 0x1c5a70 stores −1 in `*index`
first, and writes `*bag` only on a match. It walks the bags in the same way. An entry
matches when its definition name occurs inside `text` (`libc_strstr(text, name)`). Each
match overwrites both outputs, so the last matching entry of the last bag with a match
wins. A definition whose name is empty matches any text.

| Command | Address | Arguments | Result | Reads | Error paths |
|---|---|---|---|---|---|
| `playerHasItem` | 0x145590 | s item | the 32-bit sum of the count over slots 0 .. `g_numPlayers` − 1. The player count is re-read after every slot | bags | none. No object or death test |
| `onePlayerHasItem` | 0x145690 | i player, s item | the count for that slot, or 0 | `g_numPlayers`, +0x43d8, object +0x0c | the test `player < g_numPlayers` is signed, so a negative player passes and reads the record in front of `g_players`. 0 when the object is 0 or has flag 8. The string is read only after the tests |
| `countQuestItems` | 0x145720 | s item | the count for slot 0 | bags | no player-count or object test |

None of the three draws from the seed or writes anything.

### 2.2 Taking (Executed)

| Command | Address | Arguments | What it does | Writes |
|---|---|---|---|---|
| `removePlayerItem` | 0x14598c | i player, s text | Player −1: for each slot 0 .. `g_numPlayers` − 1, find the entry by substring and, when one is found, call `inventory_removeItem(slot, index, bag, 0)`. Any other player that is below `g_numPlayers` (signed test): the same for that slot. The handler's bag word starts at 0 and is not reset between players. It is used only after a match, which writes it | bags, equipment slots, weapon pointers, stamps at +0x22, the count (all through `inventory_removeItem`) |
| `removeAllItems` | 0x145758 | – | For the medal player, for bags 0, 1 and 2: the count is read once. That many times, entry 0 is removed (`inventory_removeItem(slot, 0, bag, 0)`) when its definition word is not 0 | as above |
| `removeAllWeapons` | 0x145828 | – | The same loop on bag 0 only, then +0x4434, +0x4438 and +0x443c are set to 0. Equipment slots +0x43f0.. change only through the removals | as above, plus the three pointers |

`inventory_removeItem` refreshes this machine's inventory screen copies when the slot is
local and its menu is open. That is the only per-machine part, and it does not touch
shared state (`docs/spec/game-messages.md`). No seed draw.

### 2.3 Weight, carried load and load limit (Executed)

`player_itemWeight(slot, item)` 0x1b6338 returns 1.0 for a null item, and also for an
item whose definition pointer is 0. Otherwise it computes a factor f, starting at 1.0:

- Ammunition (definition +0x1c = 8): f = 0.5 when `player_getPassiveLevel(slot, 0x10000)`
  is non-zero. The same test is then made a second time and halves f again. When
  `player_getSkillRank(slot, 0x4a)` is non-zero, f is also multiplied by Light Quiver's
  complement `0x2ff4b4(g_skillTable[0x4a], rank)`.
- Otherwise, an item with flag bit 42 (`0x8000 << 27`, thrown axes): f becomes Axe
  Bandolier's complement `0x2ff2e4(g_skillTable[0x49], rank 0x49)` when that rank is
  non-zero.

The weight is f × `item_getWeight(item)` 0x103e08. The complements are
`docs/spec/skills-69-101.md` 73 and 74. In this test they are seeded stubs.

`player_getPassiveLevel(slot, mask)` 0x1bed48 returns 0 when the unsigned slot is 5 or
more, so slot 4 is accepted. It searches the 48 rows of 0x38 bytes of the class's table
for the 64-bit mask and returns the s8 at +0xef + row, or 0 when that byte is negative.
`player_getSkillRank(slot, id)` 0x1bf330 walks the pairs at +0x4b08 up to the first id −1.
It has no count limit: with no −1 among the 48 pairs it goes on reading at +0x4bc8.

`player_recalcLoad(slot)` 0x1bec10 sets +0x120 to 0. Then, bag by bag and entry by entry
inside the count (re-read each time), it adds that entry's `player_itemWeight` with one
float add. An empty entry inside the count weighs 1.0.

The load limit is written by `player_recalcStats` 0x1b6458 (0x1b6964–0x1b6a20). That
function walks slots 0 .. `g_numPlayers` − 1. It skips a record whose object pointer is 0
(0x1b64d8), and that record keeps its old limit. Otherwise:

```
limit = float(+0x90 + 125)                                           0x1b6988
limit = limit + float(player_getPassiveLevel(object +0x3c8, 0x40)) * 15.0   15.0 at 0x1b69c8
if word 0x4d8ae8 != 0:  limit = limit + 5000.0                        5000.0 at 0x1b69f4
if 9999.0 < limit:      limit = 9999.0                                9999.0 at 0x1b6a0c
```

The passive is asked for with the slot the object names (+0x3c8), not the loop's slot.
Suite `limit` ran the whole function with every other call-out stubbed, and compared
+0x124 only. No writer of 0x4d8ae8 was found by a scan for the immediate offset. The
image holds 0. `docs/player.md` gave the limit without the object test and without the
bonus word.

### 2.4 Giving (Executed)

`givePlayerItem` 0x145a88 takes (s descriptor, i equip, i usePresets). **The third script
argument is the parser's usePresets argument, not a variant.** The handler always passes
variant −1 to `item_parseDescriptor(text, record, −1, usePresets)` 0x1069b8, so the visual
variant is random unless the descriptor has a `mesh` piece (`docs/spec/items.md` 3). Then,
for slot 0 .. `g_numPlayers` − 1 (re-read), skipping every slot except the medal player
while 0x4f713c is non-zero:

1. Parse the descriptor into the handler's stack record. The handler pre-sets the record
   (codes −1, affixes 0xff), but the parser copies its own 0x48-byte frame record over
   it.
2. w = `player_itemWeight(slot, record)`.
3. If load + w < limit (`c.olt.s`), or w is exactly 0 (`c.eq.s`, so −0.0 counts too):
   index = `inventory_giveItem(slot, record, 1)`, then `player_recalcLoad(slot)`. When
   equip is non-zero: `inventory_equipItem(slot, entry, 0)` with entry = record +0x130 +
   bag × 0x1208 + index × 0x48, where bag is the definition's category byte +0x1d. Then
   `player_resetIdleAnim(slot)`.
4. Otherwise: `pool_new(0x190)`, and when a block comes back, `ItemProp_ctor2(block,
   position, record, 0)`. The position is the 12 bytes at the player object +0x10. When
   the record has no object, the position comes from the object of `g_alivePlayers[0]`.
   That object is read only after `pool_new` returned a block.

`giveOnePlayerItem` 0x145d20 takes (i player, s descriptor, i equip, i usePresets). It
needs player < `g_numPlayers` (signed) and an object without flag 8. Its weight test is
strict: a weight of 0 must also fit. It does not call `player_resetIdleAnim` after
equipping, and it drops at the player's own object.

Error paths (all executed):

- **Bag full, or a held unique item.** `inventory_giveItem` returns −1 when the entry at
  `count` is not empty, or when the item is one of the two names that may be held only
  once (`docs/spec/game-messages.md`). The handler does not test the result. The item is
  lost: it is neither given nor dropped. `player_recalcLoad` still runs, and with equip
  set, `inventory_equipItem` receives the address 0x48 bytes before the bag start.
- **No ground block.** `pool_new` returning 0 loses the item without a word.
- **No object at all.** If neither the player nor `g_alivePlayers[0]` has an object, the
  original reads the position from address 0x10. The model raises `Fault`. The
  emulator's memory fault agreed in 8 of 200 cases (seed 20973).
- An unknown definition name parses to row 0 of the table (`docs/spec/items.md` 3). The
  disc never does this (section 7).

Seed draws per given or dropped item: one inside the parser when the result's variant is
still −1 and the definition has variants (bits 11–15 of its flags), and one inside
`ItemProp_ctor2` per ground item (`tools/ref_messages.py` notes it; it is a stub here).
Equipping can run the `*weaponEquipNotify` and `*bowEquipNotify` script hooks, and it
plays sounds only for the local slot (`inventory_equipItem`, executed in
`difftest_messages`).

`givePlayerRandom` 0x145f18 is modelled in `tools/ref_natives.py` and was not composed
here. No shipped script calls it.

### 2.5 Gold (Executed)

| Command | Address | What |
|---|---|---|
| `givePlayerGold` | 0x1462dc (i amount) | each slot gains amount / `g_numPlayers` (C division, toward zero), with the 32-bit wrap. A sum above 99,999,999 (0x5f5e0ff, built at 0x146300–0x14630c) is stored and then replaced by the cap. A wrapped negative sum stays |
| `takePlayerGold` | 0x1463ec (i amount) | each slot loses amount / `g_numPlayers`, floored at 0 |
| `checkPlayerGold` | 0x14644c | the 32-bit sum |
| `checkPlayerMinGold` | 0x146494 | the smallest. With fewer than two players it is slot 0's gold, even with no players |

With `g_numPlayers` 0, give and take do nothing. The divide is inside the loop, so it
never runs with 0.

## 3. `clearAllSkills` and the mission bytes (Executed)

`clearAllSkills` 0x1458e0 acts on the record of the medal player (u8 0x4f7148). It
writes:

- +0x128 (8 bytes), the 48 bytes at +0xef, and +0xe8: all set to 0.
- The 48 pairs at +0x4b08: both halves set to −1. These are bytes +0x4b08..+0x4bc7.
- +0x4a85 = **1**, +0x4a80 = 0, +0x4a84 = 0.
- For each of the 15 ability records, the skill id is set to −1 and the byte after it
  to 0.

It returns 0, draws nothing and calls nothing.

**The overlap the quests port reported is real, and harmless in the game.** The pair
stores end at +0x4bc7. The mission bytes are `+0x4bbf + d × 13 + m`. The row for d = 0
would be +0x4bbf..+0x4bcb, and its first nine bytes are cleared skill pairs (0xff, so
available and complete). But no mission row 0 is ever used:

- Rows 1..5 are +0x4bcc..+0x4c0c, and the medal bytes start right after them at +0x4c0d.
  Five rows of 13 fill that gap exactly.
- `player_initNewCharacter` marks mission 0 available and complete for d = 1..5 (loop
  bound at 0x1b2390 and 0x1b2430, Observed).
- Every writer of `g_difficultyIdx` stores 1, 5, a menu choice or a saved byte, and the
  executable image holds 1 (`docs/data-tables.md` gives 1–5). Row 0 would also cover the
  countdown bytes +0x4bc8 and +0x4bc9 and the cooldown +0x4bca.

Suite `missions` ran `clearAllSkills`, then `mission_isAvailable` and
`mission_isComplete` (the originals) for d = 0..5 and m = 0..12. Only d = 0 saw the
cleared bytes, for missions 0–8. Neither the slot count, `P_SKILL_SLOTS` nor
`P_MISSIONS` is off. **What the port needs to do:** start `g_difficultyIdx` at 1, as the
executable image does, not at 0. With difficulty 0, the port reads mission state out of
the skill list and the countdowns.

## 4. Seed and machine summary

| Function | Seed draws | Per machine |
|---|---|---|
| the three counts, `removePlayerItem`, `removeAll*`, gold, `clearAllSkills`, `game_scanCm1Vars` | none | none |
| `givePlayerItem`, `giveOnePlayerItem` | parser 0/1 per item, `ItemProp_ctor2` 1 per ground item | equip sounds and the remove-refresh are local only. The first-recall hint is offline only |
| `arena_spawnMonster` | 1 when `pool_new` returns the spell block, plus 3 per sample inside `world_findFreeSpot` (`docs/spec/world-queries.md`) | none in the function |
| `ScriptGenerator_spawn` | none itself; the class constructor may draw | none |
| `game_scanCm1Vars(1)` | none | **reads this machine's profile** (0x4f9030). See section 6 |

## 5. How a monster is built

### 5.1 From a script: `generateMonster` → `ScriptGenerator_spawn` (Executed)

`generateMonster(generator, className)` 0x1473d4 interns the class name in the table at
0x5d32c8 (24-byte entries, s8 count at 0x4f8409). An equal name (`strcmp`) is reused.
Otherwise the count is raised and the name copied with `strcpy`. The copy has no length
limit, so a name of 24 bytes or more runs into the next entry. Past 127 names the signed
count goes negative and the copy lands in front of the table. `game_clearLevel` sets the
count to 0 (0x1e4f98), so this is per level. The handler then calls
`ScriptGenerator_spawn` for each object of the generator's name whose RTTI is
`ScriptGenerator`. That wrapper half is in `tools/ref_natives.py`, and suite `intern`
reran the name half.

`ScriptGenerator_spawn(generator, typeName)` 0x265fc4 does the following:

- `world_createObject(typeName, position, angle, props)`. The position is the
  generator's +0x10..+0x18, copied. The angle is s16(u16 generator +0x38 − 0x4000), a
  quarter turn back. The props are the word at generator +0x2c.
- When an object comes back: u64 +0xa8 |= 0x1000000, and +0x34 = typeName (the same
  pointer `world_createObject` stores).
- If the object's dynamic type is exactly `Skeleton`, it goes to AI state 0x17 (the
  rise), through vtable slot 27. The test calls vtable entry 0 (RTTI) and compares with
  0x3cc62c using 0x3b1250.
- An object of any other class keeps the state its constructor gave it. A null result
  does nothing more.

Suite `generator` ran the original with the real class tables of `Skeleton`, `Orc`,
`Creature` and `ScriptGenerator`.

`world_createObject` 0x14f6c8 calls the factory installed at 0x5f76f4, passing the props
in the fourth register, and stores the class name at +0x34 of a non-null result.
`world_objectFactory` 0x159c94 is the table in `docs/objects.md`: case-insensitive tests,
then `pool_new(size)` and one constructor. Suite `factory` ran it for the 30 arena class
names in their own case, in upper case and in lower case: 90 of 90 reached the size and
constructor that `docs/objects.md` lists.

**Level and stats** come from the constructor, not from these functions. A creature
constructor calls `Creature_ctor` 0x10a1b0 with its type name, which finds the type's
multiplier row by hash (`docs/data-tables.md` 3.1). `Creature_setStats` 0x10a620 then
turns those multipliers into hit points, armour, damage, attack and experience using
`g_levelMonsterLevel` 0x4f714c, the player count, the boss rank and the difficulty
(`docs/data-tables.md` 3.2 with the corrections of `docs/spec/combat.md` 4.2).
`game_loadLevel` sets the level from the level table. `arena_startWave` sets it to
wave × 0x3f2bc579 + 5 (`docs/arena-modes.md`). The script commands `setCreatureParams`
and `initScriptSetParams` rescale afterwards through `Creature_scaleStats`
(`docs/script-effects.md` in the script research).

### 5.2 In the arena: `arena_spawnMonster(className, creature)` 0x3065fc (Executed)

1. cycle = float((s16 wave 0x8e7338 / 3) / s16 recipe count 0x503886), both divisions
   toward zero. The image holds 5 recipes. This is the number of full passes through the
   recipes.
2. The ring search runs up to 17 times. The angle a is the halfword at 0x8e7360, and the
   point is (cx + cos16(a) × 200, cy + sin16(a) × 200, cz) around the vector that the
   word 0x503888 points at (200.0 at 0x306768). Each try calls
   `world_findFreeSpot(out, point, 0x60, 0x18, &ok, 0)`. A miss adds 4000 to the stored
   angle and to a counter. When the counter passes 65536, the function returns with no
   monster.
3. With a class name: `world_createObject(name, spot, s16(a − 0x8000), 0x8e7230)`, so the
   monster faces the centre. Then object +0x0c |= 2, with no null test: a null result
   writes address 0xc. Then `Creature_scaleStats(obj; s, s, s, s, s)`, with s = cycle +
   ADD[k]. k is the index of the name in the 30 pointers at 0x5037f0 (`strcmp(table[k],
   name)`). ADD is 1.0 except k 5: 0x3f0666a9, 6: 0x3f40c4cd, 7: 0x3f12b042,
   8: 0x3f66a800, 10: 0x3f3a9ff0, 14: 0x3f410624 (built at 0x306670–0x306760). A name
   outside the table reads the stack word past the 30 entries, which the function never
   writes. Its three callers (0x306124, 0x306300, 0x30638c) pass either 0 or a pointer
   taken from that same table, so the miss cannot happen from them (Observed).
4. Without a class name (the saved-monster list, caller 0x306124): the creature's
   +0x10..+0x18 = spot, byte +0x231 = 0, +0x38 = a − 0x8000, then
   `Creature_clearStatus`.
5. `pool_new(0x18)`. When it returns a block, that block becomes a `SpellArena` record:
   +0 byte 0, +4 0, +8 0, +0xc the creature, +0x10 a fresh draw (seed >> 16), +0x14 the
   `SpellArena` table 0x51b4f8 (the `Spell` table 0x515ba0 is stored first and then
   overwritten). Then `creature_addSpell(obj, block or 0)`.
6. Vtable slot 34 with 5000 (the home range), then slot 27 with 0 (AI state 0). Both go
   through the table entry's this-adjustment.
7. The angle at 0x8e7360 gains the step 0x8e7364 (`arena_setRingStep`).

## 6. `game_scanCm1Vars(0)` (Executed)

`game_scanCm1Vars(recompute)` 0x1eb950 behaves in two ways:

- **Argument 0:** it returns the word at 0x4f7110 and reads nothing else.
- **Any other argument:** it calls `profile_getVar` on `m11cm1`, `m9cm1`, `m8cm1`,
  `m7cm1`, `m6cm1`, `m5cm1`, `m4cm1`, `m2cm1` and `m1cm1` (0x53e170 + 8k), in that order.
  It returns the index of the first non-zero one, or 9 when none is. There is no `m10cm1`
  or `m3cm1`. `profile_getVar` appends an unknown name with 0, so the scan writes this
  machine's profile table for every name it reaches.

The word 0x4f7110 holds −1 in the executable image. Only `game_set4f7110(v)` 0x1ec830
writes it: v, or `game_scanCm1Vars(1)` when v is −1. It has three callers:

| Caller | Value |
|---|---|
| `frontend_start` 0x1e204c | −1: rescan |
| the start-up path 0x323e90 | −1: rescan |
| the net launch receiver 0x137504 | the word at launch message +0xf4 |

The host's launch builder fills message +0xf4 with `game_scanCm1Vars(1)` at 0x13542c,
under a flag test at 0x135400 (bit 0 of a byte, meaning unknown) (Observed). So in a net
game every machine uses the host's profile index, and this is the "message +0xf4" word
that `docs/arena-modes.md` left open. Mode A uses `game_scanCm1Vars(0)` as the arena
level index, both in `arena_levelName` 0x304bc8 and when the index wraps (0x306c7c). It
indexes the 13-name table 0x5037b8 with no range check: 9 when no profile variable is
set, and −1 (the word before the table) only before the first `game_set4f7110`.

Suite `cm1` ran both forms and the setter with the real `profile_getVar` on random
profile tables, and compared the result and the profile table bytes.

## 7. On the disc (counts only)

`python3 tools/items_census.py --disc <private copy> --elf <SLUS_209.73>` over the 120
`script.scr` files of the read-only private disc copy. Output is in
`local/census/items-census.txt` (untracked).

| Command | Calls | Scripts | All arguments literal |
|---|---:|---:|---:|
| `playerHasItem` | 61 | 20 | 60 |
| `onePlayerHasItem` | 36 | 32 | 0 (the player is a variable) |
| `countQuestItems` | 61 | 13 | 61 |
| `removePlayerItem` | 147 | 34 | 61 |
| `removeAllItems`, `removeAllWeapons` | 1, 1 | 1, 1 | – |
| `givePlayerItem` | 10 | 6 | 8 |
| `giveOnePlayerItem` | 2 | 1 | 0 |
| `givePlayerRandom` | 0 | 0 | – |
| `givePlayerGold`, `takePlayerGold`, `checkPlayerGold`, `checkPlayerMinGold` | 4, 1, 4, 0 | 2, 1, 1, 0 | – |
| `clearAllSkills` | 2 | 2 | – |
| `generateMonster` | 136 | 11 | 121 |

These are the totals of `docs/script.md`. How the literal arguments fall:

- Names of `playerHasItem`, `onePlayerHasItem` and `countQuestItems`: 150 match a base
  or preset definition name exactly. 0 match only in another case. 2 match none (always
  0). 6 are not literals.
- Texts of `removePlayerItem`: 66 contain exactly one definition name and **75 contain
  several**. For those, the entry removed depends on bag order (last match wins).
  1 contains none. 5 are not literals.
- `givePlayerItem`: 10 descriptors whose head names a base definition. Equip is 1 in 2
  calls. usePresets is 0 in 8 calls. 2 calls push only two cells after declaring 12
  bytes (`docs/spec/script-machine.md` 9). For those, usePresets is the caller's saved
  frame pointer, which is 0 in an entry function (Inferred). `giveOnePlayerItem`: both
  calls pass usePresets 1, and both texts are preset names.
- `generateMonster`: 121 calls with both arguments literal: 16 distinct class names, at
  most 6 distinct in one script. None is 24 bytes or longer. All 121 reach a constructor
  through the original factory, and none reaches the `Skeleton` constructor. **Corrected
  in `docs/spec/generate-monster-names.md`:** the other 15 calls are 12 computed class
  names and 3 computed generator names, and the 3 bring 2 more literal classes (18
  distinct in all). The computed classes are rows of constant string tables, picked
  through `getRand` shuffles. 2 of the 3 computed-generator calls pass a class that the
  factory builds with the `Skeleton` constructor. So the rise state **is** reachable from
  shipped scripts whenever that generator is a `ScriptGenerator`.

## 8. What the native client should implement first

Ranked by disc calls, by what each call blocks, and by what each one needs that the
client lacks. The quests round names the item commands as the blocker of a
start-to-finish play-through.

| Rank | What | Calls / scripts | Needs | Why here |
|---|---|---|---|---|
| 1 | `playerHasItem`, `onePlayerHasItem`, `countQuestItems` with `inventory_countItemByName` | 158 / 65 | the bags, exact `strcmp` | read-only, a few lines, and they gate quest branches |
| 2 | `removePlayerItem` with `inventory_findItemBySubstring` | 147 / 34 | `inventory_removeItem` (`ref_messages.remove_item`) | the most calls left. The substring rule (name inside text, last match wins) decides 75 calls |
| 3 | `g_difficultyIdx` starts at 1; `clearAllSkills` | 2 / 2 | nothing | ends the false mission bytes the quests round saw |
| 4 | `givePlayerItem`, `giveOnePlayerItem` | 12 / 7 | `ref_items.parse_descriptor`, `inventory_giveItem`, weight, carried load and limit, `inventory_equipItem` (for 2 calls), `ItemProp_ctor2` for drops | quest rewards. usePresets is the third argument |
| 5 | `game_scanCm1Vars(0)` and `game_set4f7110` at the frontend, and +0xf4 in the net launch | – | this machine's profile variables | unblocks the arena mode-A wrap that the arena round refused |
| 6 | `generateMonster` → `ScriptGenerator_spawn` | 136 / 11 | `world_createObject` and the factory rows of the 16 names, and their constructors | many calls, but it needs the object factory and constructors the client may not yet build. Start with the classes it already has |
| 7 | gold, `removeAllItems`, `removeAllWeapons` | 9 / 4 and 2 / 2 | the bags | trivial, rare |
| 8 | `arena_spawnMonster` | arena only | factory, `Creature_scaleStats`, `SpellArena` | after the arena's own wave code |

## 9. Runs

- `python3 tools/difftest_script_items.py --cases 200`: 17 suites, 0 failed, seed 20973.
  Also `--cases 100 --seed 7`. Per handler, 200 cases. Results, stub calls (with item
  records and vectors by content), the four records, every byte written outside them,
  and the seed must all agree, and a call to any non-listed address fails the case.
- `python3 tools/difftest_monster_build.py --cases 300`: 4 suites, 0 failed, seeds 20973
  and 7. The arena suite covers class and creature forms, hit and give-up, with and
  without a spell block. The factory suite covers 90 names.
- `python3 -m unittest discover -s tools -p 'test_ref_script_items.py'` (26 tests) and
  `... 'test_ref_monster_build.py'` (14 tests).

## 10. Open

All six points were taken up in `docs/spec/items-gaps.md`:

- The writer of 0x4d8ae8: none in the executable (section 1 there). The word stays 0.
- The flag bit that guards message +0xf4 (0x135400): the host bit, bit 0 of 0x402a30
  (section 2 there, executed).
- `ItemProp_ctor2`'s draw and `givePlayerRandom`: `docs/spec/item-drops.md`.
- The 15 non-literal `generateMonster` arguments: `docs/spec/generate-monster-names.md`.
- Which disc objects are `ScriptGenerator`s: 105 records in 11 levels
  (`docs/spec/hide-monster.md`).
