# "startup" area: picture cache, items and loot, creature movement helpers

Range `0x100000–0x109d68`, 53 functions, US `SLUS_209.73` v2.00. Static reading only;
nothing here was checked on a running game. **Observed** = read at the address given,
**Inferred** = follows from observations, **Unknown** = not established.

## What this range really is

It is not program start-up. It is the first object code in link order, and that code is
the **item module**: a streaming cache for item pictures, the item definition tables and
everything that builds, names, prices, generates and drops items. The last six functions
are creature movement and area-effect helpers that sit directly in front of the
`Creature` constructor (`0x109d68`).

How this was established:

- **Observed:** the ELF entry point is `0x14fa88` and `main` is `0x323dcc`; neither
  calls anything in this range directly (see "Start-up path" below).
- **Observed:** no data word in the executable holds the address of any of the 53
  entries (scan of both data segments), so none is a virtual function, a task, a script
  built-in or a static constructor. Everything here is reached by direct calls.
- **Observed:** the module's read-only strings start at the first byte of `.rodata`
  (`0x520000`, the two cache file names) and its tables start at the first byte of
  `.data` (`0x3e9c00`) and run to `0x402758`; its zero-initialised storage starts just
  after the start of `.bss` (`0x564380`). First in code, first in every data section.
- **Observed:** callers are loot code (`Creature_dropLoot` `0x10f2c8` and level objects
  in the monsters area), the script built-ins that give or drop items, the player's
  inventory and damage code, the shop and item-list UI, and save code.

Three functions have no caller and no pointer to them (**Observed**): `0x10404c`,
`0x105be8`, `0x108844`. They are leftovers.

## How the pieces fit

```
item text  --item_parseDescriptor-->  Item (0x48 bytes)  --embedded in-->  item prop object,
"name+mod+mod"      0x1069b8             |                                 inventory lists,
                                         |                                 shop stock lists
 generators (budgeted, from g_randSeed)  |
 0x104ca4 / 0x104758 / 0x106214 /        +--> value 0x1024a8, damage 0x104100, armour 0x103ec8,
 0x106658 / 0x108590                     |    weight 0x103e08
        ^                                +--> display name 0x101e48 (language dependent)
        |                                +--> picture file name 0x107edc --> picture cache
 loot_generateDrops 0x100d54                                               0x1008bc
 (called on creature death)
```

1. **Definitions** are constant 64-byte rows. An **item** is a 0x48-byte value that points
   at a definition and adds a count, a flag word, a prefix and suffix index and up to four
   numeric modifiers.
2. **`item_parseDescriptor` (`0x1069b8`)** is where every item starts. Its input is
   text: a definition name followed by `+token` modifiers. Random generation works by
   *building such a string* (base name + the prefix's modifier text + the suffix's
   modifier text) and parsing it (Observed, `0x104ca4`). Fixed gear is the same kind of
   text supplied by the caller: `player_giveStartingItems` alone has 323 call sites, and
   the script built-ins pass the script's own string.
3. **Generators** pick candidates with the shared generator `g_randSeed`, price each with
   `item_getValue` and keep the most valuable one that fits a gold budget.
4. **`loot_generateDrops` (`0x100d54`)** is the death-drop roll. It creates `Gold` objects
   and item props in the world.
5. **Pictures.** `item_buildPictureFilename` derives a texture file name; the
   **picture cache** streams it from `piccache.dat` in the background and
   `item_getPicture` returns a placeholder until it has arrived.
6. **Creature helpers** (`0x108970–0x109d67`): obstacle avoidance used by
   `Creature_moveTo`, an area-damage loop, a "count monsters near a point" query and a
   random relocation used by two monster classes.

## Data structures

### Item (0x48 bytes) — Observed in `0x1069b8`, `0x107ca8`, `0x108924`

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | ptr | definition row; a table index while saved (see `0x107ea4`) | `0x106b58`, `0x107ea4`, `0x107ec0` |
| +0x04 | s16 | count (stack size), from definition +0x0c | `0x106b4c`; multiplied into value and weight |
| +0x08 | u64 | flags, copied from definition +0x28; bits 11–15 are then replaced by the chosen visual variant | `0x106b50`, `0x1046e0` |
| +0x10 | s16[4] | zeroed on creation and copy; use Unknown | `0x106a40`, `0x107ca8` |
| +0x18 | s16[4] | zeroed on creation and copy; use Unknown | same |
| +0x20 | u8 | prefix row index, 0xff = none | `0x101e48`, `0x104ca4` |
| +0x21 | u8 | suffix row index, 0xff = none | same |
| +0x22 | s16 | zeroed by copy; use Unknown here. Since established: **not written at creation**; `inventory_giveItem` later stores the bag index here (`docs/issues/kill-loot-xp.md`, `docs/spec/items.md` §2) | `0x107ca8` |
| +0x24 | 4 × 8 bytes | modifiers: `s16 type` (0xffff = empty), `s16 v0, v1, v2`. The slots end at +0x44 | `0x1069b8` tail `0x107b6c–0x107c40` |
| +0x44 | 4 bytes | padding, never written | `docs/spec/items.md` §2 |

Bytes the code that builds a record never writes (executed in `docs/spec/items.md` §2):
+0x06, +0x22, the three values of an empty modifier slot, and the padding +0x44…+0x47.
The parser builds the record in its own stack frame and copies all 0x48 bytes out, so
those bytes of a new item are whatever lay in that frame. Two records of the same item
are therefore not byte-equal in general, and the word compared at +0x20 below includes
+0x22 (proposed ledger row I1 in `docs/spec/items.md` §13).

Two items are "the same kind" for `0x108924` when definition, flags and the 32-bit word
at +0x20 match.

### Item definition (0x40 bytes), base table `0x3f7650` (607 rows + terminator)

| Offset | Type | Meaning | Evidence |
|---|---|---|---|
| +0x00 | char* | name; also the text key (`<name>_name`) | `0x1069b8`, `0x101e48` |
| +0x04 | s16 | level; generators require level ≤ their cap (values 1–107) | `0x104ca4`, `0x106214` |
| +0x08 | float | weight per unit | `0x103e08` |
| +0x0c | s16 | default count (20 on the ammunition row, 40 on 28 thrown-weapon rows, else 1) | `0x106b44` |
| +0x0e, +0x10 | s16, s16 | damage min, max; non-zero on all 162 weapon rows and no others | `0x104100`, table |
| +0x14 | s32 | fixed price; when ≥ 1 it replaces the value formula (set on ammunition, the thrown potions and 162 of the 209 category-2 rows) | `0x1024a8` first test |
| +0x18 | s16 | armour value; non-zero on exactly the 236 armour rows | `0x103ec8`, table |
| +0x1a | s16 | the weapon's attack rating (weapons only, near the mean damage): raised by modifier 0x23 (percent) and summed into player record +0xcc, the attack rating that melee passes to `damage_apply` (`docs/data-tables.md` §4.5). The earlier version gave the meaning as Unknown | `0x103f88`, `0x1b721c` |
| +0x1c | u8 | equipment slot: 0 one hand, 2 two hands or ranged, 3 shield, 4 body, 5 ring, 7 neck, 8 ammunition, 9 gloves, 10 boots, 11 head, 12 legs, 14 ear, 16 none | Inferred from row names; used at `0x104c48`, `0x107edc` |
| +0x1d | u8 | category: 0 weapon, 1 armour, 2 everything else | every generator |
| +0x1e | u8 | weapon subtype: 0 one-handed, 1–3 two-handed families, 4 bow, 6 thrown (5 is excluded from the value formula) | `0x104c04`, `0x1024a8`, `0x108434` |
| +0x20 | u32 | damage-type bits (1, 4, 8); tested against a prefix's mask | `0x104c04`, `0x104ca4`; names Inferred: blunt, pierce, slash |
| +0x28 | u64 | flags, see below | |
| +0x30 | char* | picture base name, or 0 to use the model-table row's texture name | `0x107edc` |
| +0x34 | s16 | row in the model table `0x3e9ce0` | `0x1083f8` |
| +0x38 | ptr | filled at load for bows: their shot animation | `0x108434` |

Definition / item flag bits (bit numbers of the u64):

| Bit | Mask | Meaning | Kind |
|---|---|---|---|
| 9 | 0x200 | display name is never decorated with prefix or suffix (one row) | Observed `0x101e48` |
| 11–15 | 0xf800 | definition: number of visual variants; item: chosen variant | Observed `0x1046e0` |
| 16 | 0x10000 | never picked by the random generators | Observed, all generators |
| 19–22 | 0x80000… | armour material classes (cloth, leather, chain, plate); a prefix lists the classes it may attach to | Observed use `0x104ca4`; names Inferred from rows |
| 23 | 0x800000 | weapon picture uses the prefix's alternate colour index | Observed `0x107edc` |
| 33 | 0x200000000 | set on no definition; on an item it turns on a draw effect | Observed `0x1046c4`, `0x1068d8`; who sets it Unknown |
| 34 | 0x400000000 | weapon picture name is not varied (ammunition, thrown potions) | Observed `0x107edc` |
| 35 | 0x800000000 | "reagent" group (123 rows): only `0x106214` drops them | Observed |
| 36 | 0x1000000000 | model-table row = +0x34 plus the variant (3 rows) | Observed `0x1083f8` |
| 45 | 0x200000000000 | "figurine" group (20 rows): only `0x106658` drops them | Observed |

### The other tables (all Observed; row counts from walking to the null terminator)

| Address | Rows × size | Contents |
|---|---|---|
| `0x3e9c18` | 12 × 3 floats, 10 selectable | drop quality rows: chance of a poor (budget ×0.5) and of a normal drop; the rest is good (×3). Row 0 is 99 % poor, row 9 is always good. `loot_generateDrops` interpolates between rows; it clamps the row argument to 0…9 (`0x100e64–0x100e88`), so rows 10 and 11 (`0x3e9c90–0x3e9ca7`, word for word the same as row 9) only pad the blend. The earlier version counted 10 rows |
| `0x3e9cb0` | 7 floats | value multiplier per weapon subtype |
| `0x3e9cd0` | 16 bytes | draw-effect parameter block written by `0x1068d8` |
| `0x3e9ce0` | 134 × 16 | model table: model file name, texture file name, and two pointers filled by `item_loadResources` |
| `0x3ea550` | 835 × 0x40 | **preset table**: definitions whose *name is a full descriptor* (base name plus modifiers). Its terminator row ends exactly where the base table starts, so a preset has a negative index (−836…−2) under `0x107ea4`; `0x108968` returns 836 |
| `0x400e50` | 73 × 0x28 | prefixes: +0 text key, +4 s16 level, +6/+7/+8 s8 picture colour indices (weapon, armour, alternate weapon), +0x0c three modifier strings (one per category), +0x18 u64 definition-flag mask, +0x20 u32 damage-type mask |
| `0x4019e0` | 165 × 0x14 | suffixes: +0 text key, +4 s16 level, +8 three modifier strings (one per category) |
| `0x4026d8` | 12 ptrs | two- and three-letter body-type codes used in worn-armour picture names, indexed by the body-type argument of `0x107edc` (Inferred: the player model number, 0–11) |
| `0x402708`, `0x402730` | 9 ptrs each | mana and healing potion names, largest first |

### Modifier types — Observed, token → code pairs read from `0x106b90–0x107c48`

| Code | Token | Code | Token | Code | Token |
|---|---|---|---|---|---|
| 0x00–0x04 | resistfire, resistcold, resistpoison, resistdisease, resistmagic | 0x0e–0x13 | requiredlevel, requiredstrength, requiredintelligence, requireddexterity, requiredstamina, requiredclass | 0x1f–0x22 | fireburst, frostburst, poisonburst, lightningburst |
| 0x05–0x0a | healthbonus, manabonus, strengthbonus, intelligencebonus, dexteritybonus, staminabonus | 0x14 | attackspeed | 0x23 | damageincrease (percent) |
| 0x0b, 0x0c | healthregeneration, manaregeneration | 0x15–0x18 | firedamage, colddamage, poisondamage, shockdamage (min–max) | 0x24, 0x25 | weightmodifier, costmodifier (percent) |
| 0x0d | armorbonus (percent) | 0x19–0x1e | bugzapper, bugexploder, undeadbonus, undeaddestroy, critical, stunresistance | 0x26 | diseasedamage (min–max) |
| | | | | 0x27, 0x28, 0x2a | requiredblunt, requiredslashing, resistall |

A token carries one to three integers (`v0`, `v1`, `v2`). A repeated token overwrites its
slot; a fifth distinct token is silently dropped. A `mesh` token sets the visual variant
instead of adding a modifier. Code 0x29 is not produced by the parser.

### Picture cache — Observed in `0x100000–0x100973`

`piccache.hdr` (loaded whole, pointers fixed up in place):

| Where | Type | Meaning |
|---|---|---|
| header +0 | u32 | number of groups |
| group +0 (12 bytes each, from header +4) | ptr | this group's entries |
| group +4 | ptr | picture name stem |
| group +8 | u32 | number of entries |
| entry +0 (10 bytes each) | s16 | number after the stem, −1 if the name has none |
| entry +2 | u16 | first sector inside `piccache.dat` (2048-byte units) |
| entry +4 | u16 | sectors to read |
| entry +6, +8 | s16 | width, height |

Runtime state:

| Address | Size | Meaning |
|---|---|---|
| `0x3e9c00` | u8 | work pending (a slot is queued or loading) |
| `0x3e9c04` | s32 | slot being loaded; negative when none |
| `0x3e9c08` | u8 | set by the file system when the read has finished |
| `0x3e9c0c`, `0x3e9c10`, `0x5bf600` | | header allocation, group count, group array |
| `0x5b4600` | 64 × 0xc0 | slots: +0 name (empty = free), +0x40 s16 block list (−1 pending or terminator, −2 not in the header), +0x7c last-use display frame, +0x80 the 64-byte picture header that callers receive |
| `0x564600` | 256 × 0x500 | blocks: +0 tag word (quadword count ≤ 79, plus a "more follows" or "last" code), +4 pointer to the next block, +0x10 data. Byte 0 doubles as the in-use marker. Inferred: these are PS2 DMA chain packets so the picture can be uploaded without copying |
| `0x5b7600` | 0x8000 | read buffer; one read in flight at a time |

A picture header's +0x06 is its total quadword count and +0x14 receives the address of the
first block; +0x0a is stamped with a marker once the chain is built (`0x1003cc`).

### Fields of other structures used here

| Structure | Offset | Meaning | Evidence |
|---|---|---|---|
| Creature | +0x2f8 | u8 avoidance side: 0 none, 1 or 2 = steer to one side until all three probes are clear | `0x108a60` |
| Gold object (0xc0 bytes, vtable `0x511a88`) | +0x80 | amount | `0x157668` called from `0x100974` |
| Item prop (0x248 bytes, vtable `0x511ba8`; the class is `PhProp` — a `PhProp` built with an item record. `ItemProp` is a different class, 0x190 bytes, table `0x511c38`) | +0x148 | embedded Item; +0xfc/+0x100 initial throw velocity | `PhProp_ctor` `0x155a0c`; stores at `0x101938`, `0x10194c` |
| Player record (`g_players[i]`) | +0x50 | class id; id 4 steers armour drops toward cloth | `0x104ca4`, `0x104758` |
| Shop stock list | +0x1200 | count of 0x48-byte items stored from +0 | `0x107d54` |

## The functions that matter

All 53 are named in `symbols/startup.tsv` with a one-line note each. The ones worth
reading first:

| Address | Name | Why |
|---|---|---|
| `0x1069b8` | `item_parseDescriptor` | 378 call sites; defines the Item layout and the modifier codes |
| `0x1046e0` | `item_randomizeVariant` | the hidden `g_randSeed` draw inside the parser |
| `0x100d54` | `loot_generateDrops` | the drop roll; order of seed draws below |
| `0x104ca4` | `item_generateWithAffixes` | the random-equipment generator (also shop stock, the script built-in givePlayerRandom, level objects) |
| `0x104758` | `item_generateFromSpecialTable` | preset ("named") items: 10 picks among the eligible rows. The pick is off by one (`0x104a3c–0x104a44`: a draw of 0 and a draw of 1 both stop at the first eligible row), so the first eligible row is twice as likely as the others and the last is never picked (`docs/spec/items.md` §7.1, executed) |
| `0x1024a8` | `item_getValue` | price; also the generators' budget test |
| `0x101e48` | `itemName_buildLocalizedName` | display name |
| `0x107edc` | `item_buildPictureFilename` | picture and equipment-texture names |
| `0x1003cc` | `picCache_serviceRequests` | the only thing in this range the main loop calls every frame |
| `0x108434` | `item_loadResources` | load-time set-up, with a side effect on `g_randSeed` |

### `loot_generateDrops` in order (Observed, `0x100d54–0x101997`)

Every random number is taken from `g_randSeed`. With more than one player the gold
amount is ×2.4, the gold chance ×1.5 and the equipment chance ×2 (`0x100dd8–0x100e3c`).

1. One draw selects quality (poor ×0.5, normal, good ×3) from the caller's quality row.
2. One draw selects 1, 2 or 3 gold rolls; each roll takes two draws (chance, amount) and
   may call `loot_spawnGold`. No gold in one PvP mode (`g_pvpModeA`).
3. Consumable: chance 7.5 % + 5 % per extra player (8 % + 6 % in the other PvP mode,
   `g_pvpModeB`). A second draw picks arrows or `item_generateConsumable`.
4. Reagent (flag 35): 1.25 %, or 0.8 % when the caller restricts it to one picture name.
5. Figurine (flag 45): 0.5 %.
6. Equipment: the caller's chance. Budget = quality × (0.8…1.2) × level factor × 200,
   tripled 1 % of the time and doubled 4 %. Category by one or two draws. 3 % of the time, or
   when the caller forces it, a preset item; otherwise `item_generateWithAffixes`. The
   prop is thrown in a random direction within ±45° of the given angle.
   Corrections from `docs/spec/items.md` §8 (executed): the caller's chance is not used
   as it stands — after the ×2 for more than one player it is halved for everyone, and in
   PvP mode B it is a fixed 0.25 whatever the caller passed; the preset branch multiplies
   the budget by 1.7 (by 7 when the budget is 3 or less) before calling
   `item_generateFromSpecialTable`. And for steps 4 and 5: the reagent and figurine
   generators are given half the level, not the level.

Steps 4 and 5 `return` from the whole function when their chance succeeds but no
definition qualifies, skipping the later steps (branches at `0x101320`, `0x10134c`,
`0x1014bc`). Each object created draws `g_randSeed` again in its constructor (see
OVERVIEW).

### `item_generateWithAffixes` (Observed, `0x104ca4`)

Counts players of class 4; for armour this decides whether cloth is excluded or
preferred. Rolls a weapon group (7 % thrown with a fifth of the budget, 5 % group 1,
88 % the rest) or one of six armour slots. Then 10 tries (15 for weapons): pick a random
eligible definition and a random suffix whose level fits; the first try is the plain
item, later tries build one candidate per eligible prefix (category 2 takes a simpler
path: one candidate per try, suffix only). That sentence is too kind to the code
(`docs/spec/items.md` §7.2, executed): the first try parses the plain item once *per
fitting prefix row*, variant draws included; and the prefix loop of the later tries runs
over the first N rows of the prefix table, N being the *number* of rows that fit the
level cap, not over the fitting rows — the table is not sorted by level, so at caps 1 to
18 up to 10 fitting prefixes lie beyond row N and are never tried. Each candidate is parsed and
priced; unless it is a potion it also receives a `requiredlevel` modifier computed from
its value (capped at 80). The best candidate not above the budget wins and
`item_randomizeVariant` finishes it.

### `item_getValue` (Observed outline, `0x1024a8`)

Fixed price × count when the definition has one. Otherwise a base (weapons: from the
damage range and the weapon modifiers, times the subtype multiplier; armour: from
`item_getArmorValue`, halved for shields; other: 5) is raised to a fixed power, a term
per remaining modifier is added (a `costmodifier` scales the running total by a
percentage), and the sum is multiplied by 40, by 0.004 for thrown stackables (name
contains the spear stem, or definition flag bits 42–44), by about 8 for the jewellery
slots, then by the count. The constants are in the function; they were not all
transcribed. They are now, in `docs/spec/items.md` §5 (executed): the power is 1.95
(0x3ff99999); the jewellery factor is 8.009912 (0x41002899) and applies only to category 2
with slot 5, 6, 7, 14 or 15; and for armour an `armorbonus` slot falls into the code-0x1a
term instead of adding nothing.

### Display names (Observed, `0x101998–0x1024a7`)

`itemName_buildLocalizedName(item, decorated)` writes UTF-16 into one static buffer
(`0x564420`). Text comes from the string table by key (`<definition name>_name`, the
prefix key, the suffix key). The language byte `0x44fddc` selects the word order and
whether the prefix must agree with the noun: the noun's text ends in an underscore tag
that `itemName_stripGrammarSuffix` removes and turns into a form number, and
`itemName_getAffixForm` picks that form from a bar-separated prefix text. Inferred:
language 4 is German (one-letter tags, three genders plus plural), 1 and 3 are Romance
languages (two-letter gender+number tags), everything else uses English order with the
literal "of" key between noun and suffix. (Supported since by the disc's text files,
`docs/spec/items.md` §9: the German file carries one-letter tags, the French and Spanish
files two-letter tags. Which of 1 and 3 is French and which Spanish is still Unknown.)

## Start-up path, and when code in this range runs

None of this is inside the range; it is here because the range was thought to be it.

| Step | Address | What happens | Kind |
|---|---|---|---|
| 1 | `0x14fa88` | ELF entry. Zeroes `.bss` `0x564300–0x90a434`, makes two kernel calls (numbers 0x3c, 0x3d), calls the library initialiser `0x35c2a0`, flushes the cache, enables interrupts, calls `main` with argc/argv from `0x5f8740`, passes the result to the exit routine `0x3b3828` | Observed; the kernel calls being thread and heap set-up is Inferred from the standard Sony start-up module |
| 2 | `0x323dcc` | `main` (debug markers name its source file `core.cc`). Calls a run-once routine first (`0x3ad310`; Inferred: the static-constructor walker), initialises subsystems and message handlers, loads the always-resident lumps (fonts, text, interface, effects, engine), runs two modal presentation callbacks (`0x321640`, `0x321788`), reads the switches `--splash`, `--net`, `--stress`, and when not started with `--net` builds default player records (`0x323a3c`, called at `0x3241d4`) | Observed `0x323e10–0x3241d4` |
| 3 | `0x3241f4–0x324278` | `main`'s endless loop: unload low-priority lumps (`0x1713c0(5)`), enter the front end the first time when offline (`frontend_start` `0x1e1f34`), run one **session** (`0x322998`), then re-enter the front end according to the session's exit code | Observed |
| 4 | `0x322998` | Session start. **Offline: `g_cosmeticSeed` and `g_randSeed` are both loaded from the CPU cycle counter (COP0 Count) at `0x3229f0` and `0x322a00`. Net game: only `g_cosmeticSeed` is set, to 0 (`0x3229e8`).** Registers the session's tasks | Observed |
| 5 | `0x322d24–0x323104` | When a world name is pending: in a net launch `net_startSync` (`0x13dce0`, called at `0x322d8c`) sets `g_randSeed = 0`; `mainloop_loadRequestedWorld` (`0x320edc`, called at `0x322e30`) calls `game_loadLevel` (`0x1e55c0`); a warm-up loop draws frames while resources stream in; a net game waits for the peers; for the four store worlds the shop stock is generated (`shop_openOrStock` at `0x3230c4` or `0x3230f0`) | Observed |
| 6 | `0x3231d8–0x3234d0` | The per-frame part: simulate (offline `tasks_run`, net `net_main`), run draw tasks, service audio, files and **`picCache_serviceRequests` (`0x323378`)**, flip | Observed |
| 7 | `0x3234e0–0x3235a7` | Session exit: tear-down, ending with **`picCache_freeHeader` (`0x323570`)** | Observed |

`names.tsv` gives `main_loop` as `0x32316c`. That address is an instruction in the middle
of step 5 (a resource lookup), not a function entry and not the loop head; the function is
`0x322998` and the per-frame branch starts at `0x3231d8` (also noted in
`docs/mainloop.md`).

When this range's code runs:

| When | What | Evidence |
|---|---|---|
| In `main`, before the first session, offline boot only | `item_parseDescriptor` (and through it `item_randomizeVariant`): `0x323a3c` sets the player count to 1 (4 with a switch) and calls `player_initNewCharacter` at `0x323cf4`, which ends in `player_giveStartingItems` | Observed call chain `0x3241d4` → `0x323cf4` → `0x1b2400` → `0x1acc78`. The seed it advances is overwritten at session start (step 4) |
| Inside `game_loadLevel`, only for a world other than the front-end world and only if `hud.lmp` is not already loaded (`0x1e5690–0x1e56ac`) | `item_loadResources` (`0x1e56bc`), then `picCache_loadHeader` (`0x1e56c4`) | Observed. Inferred: that is the first game world after boot or after a visit to the front end, because loading the front-end world (`0x1e5738`) and leaving a session (`0x32353c`) unload that lump group |
| Later in `game_loadLevel`, after those | `g_cosmeticSeed = g_randSeed` (`0x1e59b4`) | Observed |
| After a store world has loaded | generators, through `shop_openOrStock` | Observed `0x3230c4`, `0x3230f0` |
| Every displayed frame | `picCache_serviceRequests` | Observed `0x323378` |
| Session exit | `picCache_freeHeader` | Observed `0x323570` |
| On demand | everything else: deaths, scripts, chests, inventory, shop, drawing | callers |

That first row is the earliest execution of anything in the range. With `--net` it is
skipped and the first execution is inside the first world load.

## Per-machine state

Scan result first. **Observed:** no instruction in `0x100000–0x109d68` reads COP0, a
hardware register (`0x1000xxxx`) or makes a kernel call, and no function here references
`g_cosmeticSeed`, the camera, the pads, audio state or the local-player slot (every global
reference in the range was listed). The module does not seed any generator. What it does
do:

1. **`g_randSeed` is advanced by a resource loader, behind a per-machine condition.**
   `item_loadResources` parses all 607 base definitions with variant −1 (`0x108524`);
   the parser then calls `item_randomizeVariant` (`0x107c78`), which draws from
   `g_randSeed` for each definition that has visual variants — 223 draws. The call is
   made only when `hud.lmp` is not loaded on *this* machine (`0x1e56a4–0x1e56ac`), and in
   a net launch it comes after the seed was zeroed (`0x322d8c`), so it is part of the
   starting state of the game. **Observed** (mechanism). **Inferred:** harmless when
   every machine reaches the first world from the front end, because then all of them
   make the same 223 draws. Whether any flow lets one machine keep that lump group loaded
   while another does not was **Unknown** here; `docs/issues/sync-breakers.md` section 6b
   followed the lump keep-levels through the launch paths and found none: no flow leaves
   `hud.lmp` loaded on one peer only.
2. **The parser draws from `g_randSeed` whenever its variant argument is −1** — almost
   every call. **Observed.** Any caller that runs on one machine only, or from draw or
   menu code, would move the shared seed. Callers not classified here: the store stock
   calls in the session function (`0x3230c4`, `0x3230f0`; not a run task, placed after the
   net ready-wait loop), `player_giveStartingItems` (`0x1acc78`), object constructors at
   `0x152a18`, `0x155dac`, `0x159458`, and the monster and skill callers listed by
   `tools/ps2elf.py xref 1069b8`. **Unknown** per caller.
3. **Picture availability differs per machine.** The cache is driven by local disc
   completion (`0x3e9c08`), is serviced once per *displayed* frame and evicts by the
   per-machine display-frame counter `0x44fdd0` (`0x1002d4`). `item_getPicture` returns
   the real picture or a placeholder accordingly (`0x108388`). **Observed.** Its callers
   are the item-list drawing functions `0x1cc7e0`, `0x1cd208`, `0x1cbbe8`; **Inferred:**
   display only.
4. **`item_buildPictureFilename` is also used for worn-equipment textures**
   (`0x1a30b0`, `Player_drawEquipped` `0x1a3580`, `0x1bc768`, `0x1be7e8`), and the session
   warm-up loop waits on `0x1a30b0` per machine (`0x322f64`). **Observed** callers; the streaming
   itself is outside this range and was not read.
5. **Draw code writes a global.** `item_selectDrawEffect` (`0x1068d8`) fills the
   parameter block `0x3e9cd0` and the engine's effect selector from draw functions
   (vtable slot 5 at `0x15991c`, `Player_drawEquipped`, `WeaponRack_draw`). **Observed.**
   Nothing in this range reads the block back; **Inferred:** cosmetic.
6. **Language-dependent text.** Names depend on `0x44fddc`, a per-machine setting, and
   live in static buffers (`0x564420`, `0x564380`). **Observed.** Callers are the item
   props' prompt virtual (slot 13: `0x154d10`, `0x159870`) and `itemList_drawRows`;
   **Inferred:** display only.
7. **No test for the prediction copy (flag 0x20000) anywhere in the range.**
   `loot_spawnGold`, `loot_spawnNamedItem`, `loot_generateDrops`,
   `combat_applyAreaDamage`, `Creature_relocateAlongClearRay` and
   `Creature_computeAvoidanceOffset` (which writes creature +0x2f8) all change shared
   state unconditionally. **Observed.** Whether the copy can reach them depends on the
   callers: `combat_applyAreaDamage` ends in `damage_apply`, which refuses the copy as
   attacker (per `symbols/gameplay.tsv`); `Creature_dropLoot` and the monster callers
   were not checked. **Unknown.**
8. **Item identity is a pointer while in memory** (`0x108924`), converted to a table
   index for saving (`0x107ea4`). **Observed.** Both tables are constant data at fixed
   addresses, so the pointers are equal on every machine running this executable;
   **Inferred:** not a hazard.

For context, on the start-up path outside the range (**Observed**): the offline seeds
come from COP0 Count (`0x3229f0`, `0x322a00`); in a net game the cosmetic seed is 0 at
session start and the shared seed is 0 after `net_startSync`; `game_loadLevel` then copies
the shared seed into the cosmetic one (`0x1e59b4`), so on a net launch both generators
start from values fixed by the load sequence, not by a clock. The main loop reads timer
T0 twice per frame (`0x32321c`, `0x323274`) only to store a duration at `0x44fd48`.

## What the area should be called, and its boundaries

- **Name:** `items` ("picture cache, item definitions, generation, loot, naming").
  The current label "program start, early engine setup" is wrong.
- **Start `0x100000`:** correct; it is the first function of `.text`.
- **End:** the item code ends at `0x10896f`. The six functions `0x108970–0x109d67`
  use no item data and no strings; they take creatures, write a `Creature` field
  (+0x2f8) and are called from `Creature_moveTo`, `Creature_moveToDirect`,
  `Creature_fleeFrom` and monster `run` functions. They belong to **creatures**, whose
  range should start at `0x108970`. Inferred: they are free helpers at the top of the
  creature source file; no symbol or string proves the file boundary.
- The picture cache (`0x100000–0x100973`) is a self-contained unit and could be listed
  separately; its only clients in this range are `0x108358` and `0x1083a4`.

## Not done

- `item_getValue`: structure read, constants not all transcribed, no worked example.
- `item_buildPictureFilename`: the armour branch (body-type selection, circlet special
  cases) was read once and is summarised, not verified case by case.
- The six creature helpers were read from the decompile only; their ray-cast callees
  (`0x18ad94`, `0x18a5c0`, `0x183820`) were not opened.
- `main`'s initialisation calls (step 2) were listed, not read.
- Callers were classified by area and name, not read, except where stated.

## Open questions

1. Item +0x10 and +0x18 (two `s16[4]` arrays) and +0x22: who writes them after creation?
   Search writers at item-relative offsets inside the inventory lists (record +0x130,
   stride 0x48).
2. Definition +0x1a: what does player record +0xcc feed? That names the field.
   (Answered since: +0xcc is the player's attack rating, so +0x1a is the weapon's attack
   rating; see the definition table above.)
3. Who sets item flag bit 33 (no definition has it)? It drives the draw effect and
   `item_getFlag33Level`.
4. Per-machine item 1: can `hud.lmp`'s lump group be loaded on one net peer and not on
   another when the first world loads? Reading the lump priority code (`0x1713c0`,
   `0x17128c`) and the net launch path in `frontend_run` would settle it. (Answered: no —
   `docs/issues/sync-breakers.md` section 6b.)
5. Per-machine item 2: are the store stock calls at `0x3230c4`/`0x3230f0` reached with the same
   `g_randSeed` on every machine? It follows a wait loop that calls `net_main`.
6. The meaning of language codes 1, 3 and 4, and whether the US disc can select them.
   (Partly answered: 4 is German, 1 and 3 are French and Spanish in an order not
   established — `docs/spec/items.md` §9. Whether the US disc can select them is open.)
7. `0x101c0c` is inert in this build (its state word is never set). Was it live in the
   engine's earlier game?
8. Can the prediction copy reach `Creature_computeAvoidanceOffset` through
   `Creature_moveTo` and friends from `Player_run`?
