# Rules data: where it lives and how to read it

US `SLUS_209.73` v2.00. This document answers one question for each kind of game rule:
*is it a table, a file on the disc, or a constant inside a function* — and gives the layout
so that a rebuild can read the same data from a player's own copy, and so that anyone can
check a rule without reading machine code.

Static reading only when it was written; nothing here was checked on a running game.
Since then parts of sections 1, 3, 4, 5 and 8 have been executed function by function in
`tools/ee_emu.py` (`docs/spec/items.md`, `docs/spec/combat.md`; marked **executed** where
folded in), and the project has a live game — the Play! emulator, which is not a PlayStation 2 and not PCSX2
— whose runs are listed in `FINDINGS.md`, "Run on the live game" (rows V1–V23) and `docs/issues/live-rig.md`.
The only rule of this document seen there is the load limit of a new character (strength +
125: 46 gave 171); no table was compared with the live game. No test patch has been run on a live game.
**Observed** = read at
the address given. **Inferred** = follows from observations. **Unknown** = not established.
Where a paragraph gives an address and no mark, it is Observed.

No table contents are reproduced here. `tools/dump_tables.py` prints them from your own
executable and disc files (section 9). Row counts below are for this build.

Earlier documents this builds on: `docs/startup.md` (the item module), `docs/skills.md`,
`docs/player.md`, `docs/creatures.md`, `docs/monsters.md`, `docs/objects.md`,
`docs/gameplay.md` (`damage_apply`), `docs/engine.md` (lumps and text). Section 10 lists
what in them turned out to be wrong or can now be filled in.

## 0. Summary

| Rules data | Where it lives | Records | Dump table |
|---|---|---|---|
| Item definitions (name, level, weight, damage, armour, price, slot, flags) | executable, `g_itemDefs` `0x3f7650` | 607 × 0x40 | `item_defs` |
| Preset ("named") items | executable, `g_itemPresets` `0x3ea550` | 835 × 0x40 | `item_presets` |
| Prefixes / suffixes | executable, `0x400e50` / `0x4019e0` | 73 × 0x28 / 165 × 0x14 | `item_prefixes`, `item_suffixes` |
| Item descriptor grammar | format strings `0x520190…0x5204b8`, codes in `item_parseDescriptor` `0x1069b8` | 42 modifier tokens + `mesh` | `item_tokens` |
| Drop quality rows | executable, `0x3e9c18` | 12 × 3 floats (10 used) | `loot_quality` |
| Drop parameters per monster class | constants at the 49 call sites of `Creature_dropLoot` `0x10f2c8` | 49 | `loot_calls` |
| Monster multipliers per type name | disc, `BALANCE.LMP` → `monsters.bal` | 184 × 12 bytes | `monster_balance` |
| Monster formula (hp, armour, damage, attack, experience) | code, `Creature_setStats` `0x10a620` | — | section 3.2 |
| Monster resistances, kind, speed | code, each class constructor | 73 creature classes | `creature_classes` |
| Monster placement and per-object switches | disc, `objects.ob` in each level lump | 18,675 records in 119 level archives | `objects` |
| Class starting statistics | executable, `0x4ef400` | 7 × 4 ints | `class_stats` |
| Max hp / max mana per class | code, `player_recalcStats` `0x1b6458` | 7 × 6 floats | `class_formulas` |
| Experience curve | executable, `0x41b558` | 81 ints | `exp_table` |
| Class skill trees | executable, seven tables `0x4f4898…0x4f5a18` | 122 × 0x28 | `skill_trees` |
| Class passives | executable, seven lists `0x4ebbe8…0x4ec748` | 52 × 0x38, plus an end row per list | `class_passives` |
| Skill ids → skill objects | executable, `g_skillTable` `0x41b170` | 101 | `skills` |
| Skill statistics per level | code, each skill's `initStats` (virtual slot 9) | 101 | `skills` |
| Difficulty modifiers | code, five functions (section 5) | — | — |
| Text | disc, `GTEXT.LMP` → `gtext.uni` | 5,498 entries (4,309 distinct keys) | `text` |
| Level list | executable, `g_levelTable` `0x4f7210` | 90 × 0x30 + default row | `levels` |
| Mission list | executable, `g_missionTable` `0x4fe540` | 12 used × 0x34 | `missions` |
| Type name → class | code, `world_objectFactory` `0x159c94` | 208 name tests | `object_factory` |

## 1. Items

`docs/startup.md` documents the item module in full; the layouts were re-read here and
agree. This section is the short form plus what is new.

### 1.1 Definition row (0x40 bytes) — `g_itemDefs` 0x3f7650 and `g_itemPresets` 0x3ea550

Both tables end with a row whose first word is null. Lookup is a linear `strcmp` of the
name (loops at `0x106ae4` for the base table and `0x106b24` for the preset table); an
unknown name silently becomes row 0.

| Offset | Type | Meaning | Kind |
|---|---|---|---|
| +0x00 | char* | name; in the preset table the *whole descriptor* (`base+mod+mod`) is the name | Observed |
| +0x04 | s16 | level (1–107 in the base table, 1–8 in the preset table) | Observed |
| +0x08 | float | weight per unit | Observed `0x103e08` |
| +0x0c | s16 | default stack count | Observed |
| +0x0e, +0x10 | s16 | weapon damage minimum, maximum | Observed `0x104100` |
| +0x14 | s32 | fixed price; ≥ 1 replaces the value formula | Observed `0x1024a8` |
| +0x18 | s16 | armour value | Observed `0x103ec8` |
| +0x1a | s16 | weapon **attack rating**: added to the wielder's attack rating (see 4.5) | Observed `0x103f88` → `0x1b721c`; new |
| +0x1c | u8 | equipment slot | Observed |
| +0x1d | u8 | category: 0 weapon, 1 armour, 2 other | Observed |
| +0x1e | u8 | weapon subtype (0 one-handed, 1–3 two-handed families, 4 bow, 6 thrown) | Observed |
| +0x20 | u32 | damage-type bits 1, 4, 8 | Observed |
| +0x28 | u64 | flags (bit table in `docs/startup.md`) | Observed |
| +0x30 | char* | picture base name or null | Observed |
| +0x34 | s16 | row in `g_itemModels` 0x3e9ce0 | Observed |
| +0x38 | ptr | zero in the file; filled at load for bows | Observed |
| +0x06, +0x12, +0x1f, +0x24, +0x36, +0x3c | | zero in all 1,442 rows of both tables | Observed (table scan) |

A saved item stores `(row address − 0x3f7650) / 0x40`, so preset rows have negative
indices (`item_encodeDefinitionIndex` 0x107ea4). A rebuild that reads the tables from the
executable must keep both tables and that numbering to stay save-compatible. **Inferred.**

### 1.2 The other item tables

| Address | Row | Fields | Rows |
|---|---|---|---|
| `g_itemPrefixes` 0x400e50 | 0x28 | +0 text key, +4 s16 level, +6/+7/+8 s8 colour index (weapon, armour, alternate weapon), +0x0c/+0x10/+0x14 modifier text for weapons / armour / other, +0x18 u64 mask of definition flags it may attach to, +0x20 u32 damage-type mask | 73 |
| `g_itemSuffixes` 0x4019e0 | 0x14 | +0 text key, +4 s16 level, +8/+0x0c/+0x10 modifier text for weapons / armour / other | 165 |
| `g_itemModels` 0x3e9ce0 | 0x10 | +0 model file, +4 texture file, +8/+0x0c pointers filled by `item_loadResources` | 134 |
| `g_weaponValueMult` 0x3e9cb0 | 4 | float per weapon subtype 0–6 | 7 |
| `g_bodyTypeCodes` 0x4026d8 | 4 | char* per player model 0–11 | 12 |
| `g_manaPotionNames` 0x402708, `g_healPotionNames` 0x402730 | 4 | item names, largest first, null-terminated | 9 each |

All Observed. A prefix or suffix is not a separate kind of record on an item: its
modifier text (itself in descriptor grammar, starting with `+`) is appended to the base
name and the result is parsed (`item_generateWithAffixes` 0x104ca4).

### 1.3 Descriptor grammar

```
descriptor := name ( '+' token )*
token      := word int                e.g. one value
            | word int '-' int        a range
            | word int ',' int        chance and one value
            | word int ',' int '-' int   chance and a range
            | 'mesh' int              visual variant, not a modifier
```

- The text is copied to a 208-byte stack buffer and cut at each `+` (`strchr` at
  `0x106a9c` and `0x106b64`). The name is everything before the first `+`. **Observed.**
- Each token is tried against 43 `sscanf` formats in a fixed order (`0x106b90–0x107bd0`);
  the first format for which `sscanf` returns non-zero wins (the test at `0x106ba4` is
  "not zero"; the earlier version said "converts at least one value"). The difference
  matters, executed in `docs/spec/items.md` §3.1: the library's `sscanf` returns −1 when
  the piece ends before the first value, so an empty piece, a cut word and a bare word
  without a number all match — the first format whose word starts with the piece — and
  store that code with value 0. A descriptor ending in `+` gains modifier 0x23 with value
  0; four pieces of the executable's own preset table are matched this way. The formats are the strings at
  `0x520190–0x5204b8`: a lower-case word immediately followed by `%d`, `%d-%d`, `%d,%d` or
  `%d,%d-%d`. Values are decimal and may be negative (the prefix table uses negative
  percentages). **Observed.**
- A matched token stores `{s16 code, s16 v0, v1, v2}` in the first of the item's four
  modifier slots that is empty or already holds the same code; if none qualifies the token
  is dropped (branches to `0x107c48`). **Observed.**
- Codes: 0x00–0x28 and 0x2a, one per token; 0x29 (cast a skill on hit, see
  `docs/gameplay.md` §2.2) has no token, so no descriptor can produce it. **Observed.**
  The token → code pairs are in `docs/startup.md`; `dump_tables.py --table item_tokens`
  prints them with the number of values each takes.
- After the last token, a variant argument of −1 makes the parser draw the visual variant
  from `g_randSeed` (`item_randomizeVariant` 0x1046e0). **Observed.**
- `requiredclass` takes one integer. The earlier version left **Unknown** whether it is
  the class index or the index plus one, and who tests code 0x13. Answered
  (`docs/spec/items.md` §6, executed): it is the class index **plus one**. The test is the
  last one in `inventory_checkEquipAllowed` 0x1c4948 — a non-zero value that differs from
  record class + 1 gives reason 1 — and that function is the only reader of all the
  `required…` codes; it also applies class rules by weapon subtype, damage type and cloth.

### 1.4 Weapon and armour statistics

There is no separate weapon or armour table. Everything is in the definition row plus the
item's modifiers:

| Statistic | Source | Function |
|---|---|---|
| damage range | definition +0x0e/+0x10, scaled by modifier 0x23 (percent), plus elemental modifiers 0x15–0x18, 0x26 | `item_getDamageRange` 0x104100 |
| attack rating | definition +0x1a, scaled by modifier 0x23 | `item_getModifiedField1a` 0x103f88 |
| armour | definition +0x18, scaled by modifier 0x0d (percent) | `item_getArmorValue` 0x103ec8 |
| weight | definition +0x08 × count, compressed above a threshold, scaled by modifier 0x24 | `item_getWeight` 0x103e08 |
| value | fixed price, or a formula over the above (constants in code) | `item_getValue` 0x1024a8 |
| attack animation and speed class | definition +0x1e | `Player_run` state 1 |

All Observed in the functions named (bodies summarised in `docs/startup.md`).

## 2. Loot and treasure

There is no loot table keyed by monster. A drop is computed from six numbers supplied by
the code of the thing that died or opened, one small table, and the item tables.

1. **Drop parameters are constants in each class.** Every creature class has a death
   helper that calls `Creature_dropLoot(zOffset, throwSpeed, goldScale, goldChance,
   qualityRow, itemChance, this, &pos, angle, reagentFilter)` (0x10f2c8) with float
   immediates. 49 call sites. **Observed** (e.g. `0x2344a0`); the table `loot_calls`
   lists all 49.
2. **`Creature_dropLoot` adds rules by rank and by class** (Observed, `0x10f2c8`):
   - nothing drops when the creature has flag 0x100000000 (revived / loaded dead), or has
     the `noloot` property (key string 0x52ffd8) outside PvP mode B;
   - a chain of eleven exact-class tests (type-info compares) gives named boss classes
     their own fixed sets of extra drop calls;
   - otherwise boss rank 2 (`creature_bossRank` 0x10d940) adds two richer calls and, per
     player, one equipment-only call that forces a preset item half the time; rank 1
     (`MiniBoss`) adds two calls and a per-player call that forces a preset a quarter of
     the time;
   - a creature with a tint preset (+0xa0 ≠ 0) has its gold scale ×3 and quality row ×4;
   - the ordinary call is made only when the `MiniBoss` flag is clear.
3. **`loot_generateDrops` (0x100d54) turns the six numbers into objects.** Sequence and
   chances are in `docs/startup.md`. Two details read again here: the quality row argument
   is clamped to 0…9 and blended linearly between row ⌊q⌋ and the next one
   (`0x100e68–0x100ef0`), and each gold roll is
   `(40 + rand % 40) × goldScale × level_monsterLevelTimes0_4() × 0.035`.
4. **`g_lootQualityRows` (0x3e9c18)**: 12 rows of three floats — chance of a poor drop
   (budget ×0.5), of a normal one, and of a good one (×3). Rows 10 and 11 are never
   selected and only pad the blend. **Observed.**
5. **What can drop** is decided by the item tables: level ≤ the generator's cap, flag 16
   excludes a definition from random generation, flag 35 marks the 123 reagent rows, flag
   45 the 20 figurine rows, and the preset table supplies "named" items. **Observed**
   (`docs/startup.md`).
6. **Fixed drops**: a creature's `dropitem` property (22 placements on the disc) and the
   script built-ins pass a descriptor to `loot_spawnNamedItem` 0x100ba0. Chests,
   containers and `AutoContainer` call the generators directly with budgets from
   `level_monsterLevelTimesDifficulty` 0x1ebf70 (`docs/monsters.md` §5). **Observed.**
7. **Shops**: `shop_openOrStock` 0x1c7af8 fills three stock lists per store level by
   calling the same generators with budgets and level caps computed from the mission
   reached and the difficulty. **Observed** outline (decompile only); the budget arithmetic
   was not transcribed.

## 3. Monsters

A monster's numbers come from four places. None of them is a per-monster record with hit
points in it.

| What | Where | Kind |
|---|---|---|
| five percentage multipliers per **type name** (hp, armour, damage, attack, experience) | `monsters.bal` on the disc | Observed |
| the formula that turns multipliers into statistics, using the level's monster level, the player count, boss rank and difficulty | `Creature_setStats` 0x10a620 | Observed |
| resistances, creature kind, turn and move speed, body-material flags, radius | immediates in each class constructor | Observed |
| switches per placed object (`MiniBoss`, `noloot`, `Scale`, `Dead`, `wait`, …) | property strings in `objects.ob` | Observed |

### 3.1 `monsters.bal`

Loaded by `balance_load` 0x223998 from lump `balance.lmp`, entry `monsters.bal`, on every
level load outside the front end (`objects_levelReset` 0x15da80, called from
`game_loadLevel`). **Observed.**

```
u16 count                      (184)
count × { u16 nameHash; s16 hp, armour, damage, attack, experience; }   percentages, 100 = ×1
```

`balance_lookup(typeName, …)` 0x223a4c hashes the name with `balance_hashName` 0x223914 and
scans the records in order; the first equal hash wins; no match gives five 1.0s.
**Observed.** The hash (lower-case first, signed chars):

```
h = 0
for c in name:  h = ((h + lower(c)) & 0xffff) * 0x401 & 0xffff;  h ^= h >> 6
h = h * 9 & 0xffff;  h = ((h >> 11) ^ h) * 0x8001 & 0xffff
```

The type name is the class string of the level record (object +0x34), not the C++ class:
one constructor serves many type names with different rows (the factory's prefix tests,
`docs/objects.md`). Because only the hash is stored, names have to be recovered by hashing
candidates: strings in the executable plus class names in the level files name 182 of the
184 records unambiguously. **Observed** (tool run over all 119 level archives). 134 of the
184 are used by a placed object; the rest are reachable only through generators and
scripts, or unused — **Unknown** which.

Callers: `Creature_ctor` (0x10a1b0) for every creature built with a type name, and the
two `CastBadger` functions 0x244e4c / 0x245568. **Observed.**

### 3.2 `Creature_setStats(hp%, armour%, damage%, attack%, exp%, this, rollHp)` — 0x10a620

`L` is `g_levelMonsterLevel` (float, 0x4f714c; section 5), `n` the player count,
`rank` = `creature_bossRank(this)`. Observed instruction by instruction.

```
damage *= 1.54
if rank == 1:                      # MiniBoss property
    hp *= 9.6;  damage *= 1.3;  attack *= 3;  exp *= 4
if n >= 2 and word 0x4f713c == 0:
    exp *= n
    hp  *= 1 + 0.6 * (n - 1)
    if rank != 2 and type name != "droid":   damage *= 1 + 0.15 * (n - 1)
if rollHp:
    r  = GameObject_rand(this) % 5           # the object's own generator
    hp = (15.5 + r) * pow(hp * L, 0.85)      # double arithmetic, then to float
    if level name is neither "stomedal" nor "innpit":
        hp *= {2: 1.5, 3: 2.0, 4: 2.5, 5: 3.0}[difficulty]   # difficulty 1: unchanged
    maxHp = hp
armour (+0xe4, s16) = int(armour * 14 * L)
dmgLow (+0xd0, s16) = int(damage * pow(L, 1.0))
dmgHigh(+0xd2, s16) = max(int(2 * damage * pow(L, 1.0)), dmgLow + 1)
attack (+0xd4, s16) = int(L * 14 * attack)
expValue (+0xd8, float) = float(int(pow(exp * L, 1.322) * 8))
if the object has the Dead property:  hp = 0
```

Four corrections to the block above from `docs/spec/combat.md` section 4.2, which
executed the function against a reference model (the block is left as first written):

- `pow` is `powf` — single precision (calls at 0x10a78c and for the other three powers).
  In the hit-point line only `(r + 15.5) × power` goes through the library's software
  doubles (0x10a79c–0x10a7d8), and those truncate instead of rounding. `powf(L, 1.0)` is
  exactly `L`. A rebuild that uses a host `pow` or host doubles gets different hit points
  in the last bit.
- The player-count damage scaling is skipped not only for the type name "droid" but also
  when the object has no type name at all (0x10a720), and the name compare ignores case
  (0x10a72c).
- `exp *= n` is computed as `exp × ((n − 1) + 1.0)`; same value.
- The `Dead` property sets `hp = 0` whether or not hit points were rolled, i.e. also when
  the last argument is 0 (0x10a980); `maxHp` keeps its value.

- The float passed to `Creature_ctor` as "maximum hit points" by each class constructor
  is overwritten by this function whenever a type name is supplied, which is every
  factory-made creature. It only matters for creatures built without a type name.
  **Observed** (`0x10a1b0`, `0x10a1d4`, `0x10a204`).
- `Creature_scaleStats` 0x1185d8 multiplies the five results again by five factors; three
  callers (not read).
- Word 0x4f713c: zeroed by `game_loadLevel`, non-zero suppresses the player-count scaling.
  **Unknown** who sets it.
- `creature_bossRank` 0x10d940 returns 2 when the type name equals one of a list of
  strings compared in code (0x52fd48 onward; three of them also need a particular `name`
  property), else 1 for the `MiniBoss` creature flag, else 0. **Observed**; the strings
  are printed by `--table boss_names`.

### 3.3 What the constructors hold

Each class constructor passes a class-definition block to `Creature_ctor` and then stores
immediates into the new object. Read with the layouts of `docs/creatures.md` and
`docs/gameplay.md` §2.3:

| Object field | Meaning | Kind |
|---|---|---|
| +0x5c, +0x60, +0x64, +0x68, +0x6c (float) | fire, cold, poison, disease, lightning resistance, 0…1; negative values occur (a weakness) | Observed stores; meaning from `damage_apply` |
| +0xb4 (s8) | creature kind. 0x10 is what the `undeadbonus` / `undeaddestroy` item effects test, 0x12 what `bugzapper` / `bugexploder` test | Observed tests; names Inferred from the token names |
| +0xb0, +0xb8 (float) | turn rate, move speed | Observed |
| +0x1c (float) | collision radius | Observed |
| +0xa8 (u64) | creature flags or-ed in: body material, resist / immune marks | Observed |
| +0xd0…+0xe4 | **not** set by constructors; they come from 3.2 | Observed |

The class-definition block (register 8, the fifth integer argument, at the `Creature_ctor`
call) is
`{char *lumpName; u32 generation; {char *resourceName; void *resolved;} …}` — the model,
texture and animation names for the class. **Observed** (e.g. 0x4fe910).

`--table creature_classes` prints these per constructor. It is produced by reading the
constructor straight through, so a value a constructor stores only for one variant is
shown as an alternative (`a|b`) without its condition.

### 3.4 Per-object properties

Level records carry `key=value` strings (format in 7.3). Across the 4,871 creature
placements on the disc the keys are behavioural: `name`, `deathscript`, `initscript`,
`resurrectscript`, `noloot`, `pathname`, `wait`, `miniboss`, `showname`, `dropitem`,
`scale`, `visualarc`, `visualrange`, `homerange`, `ignoredamage`, `change<n>`, light
keys and a few more. **No key carries a number for hit points, damage, level or
resistance.** **Observed** (tool run; 43 distinct keys on creature records). `MiniBoss`
changes statistics through `rank` in 3.2; `nomagicweapons` and the weapon-element keys
read by `Creature_init` 0x10a230 switch elemental riders (not read here). The properties `Creature_ctor` reads are listed in
`symbols/creatures.tsv` under 0x109d68.

### 3.5 Experience for a kill — `Creature_processDamage` 0x110d30 (0x111e88–0x1121e8)

```
sum  = sum of the players' levels (record +0x59)
xp   = int(int(pow(expValue / sum, 1.4)) * 0.75)
one player:   if alive: give min(xp, expTable[level+1] - expTable[level])
several:      share = 0.6 for the killer, 0.4 for the others, 0.5 for all when no player
              made the kill; a dead player's share is halved; each capped as above
class 0 only: the killer also gains mana = monster maxHp / 30 (capped at max mana)
```

The last line is right for several players only. With one player the class-0 mana gain
needs no killer: it is applied whoever or whatever made the kill (0x112200); with several
it goes to the killer alone (0x112100). The gain is applied after `player_giveExp`, so
after a level-up refill (`docs/spec/combat.md` section 5, executed).

Skipped for creatures with the `Dead` property or flag 0x100000000. **Observed.**

## 4. Characters

### 4.1 Classes, models and races

- The record holds a model index 0–11 (+0x54) and a class index 0–6 (+0x50).
  `player_initNewCharacter` 0x1b1d70 derives the class from the model: models 0,1 → 0;
  4,5 → 1; 8,9 → 2; 2,3 → 3; 6,7 → 4; 10 → 5; 11 → 6. **Observed** (the test chain near the
  top of the function).
- There is no race field and no race table: a race is a pair of models, and each race has
  exactly one class. The two-or-three-letter body codes at `g_bodyTypeCodes` (and a second
  copy at 0x4ebbb8 used by `Player_ctor`) name the models. **Observed.**
- Class names: `g_skillTreePictures` 0x53b5b8 is indexed by class and holds one picture
  name per class, each ending in a class word (in class order: barbarian, cleric,
  shadowknight, ranger, wizard, berserker, shaman). **Observed** strings; that these are
  the class names is **Inferred**.

### 4.2 Starting statistics — `g_classStartStats` 0x4ef400

7 rows of four s32: strength, intelligence, dexterity, stamina (order **Inferred** in
`docs/player.md` from the formulas that read them). Copied to record +0x78 when the caller
passes no stat bytes. A new character also gets 500 gold, level 1 and the starting gear of
4.7. **Observed** (`0x1b2314–0x1b2360`).

### 4.3 Maximum hit points and mana — constants in `player_recalcStats` 0x1b6458

```
maxHp   = level * hpPerLevel + stamina * hpPerStamina - hpOffset
maxMana = (intelligence - manaIntOffset) * manaPerInt + level * manaPerLevel
load limit = strength + 125 + 15 * rank of passive 0x40   (capped at 9999)
```

`level` is record +0x59; the statistics are the effective ones (+0x90: base plus item
modifiers 7–10 — and plus figurines: `player_recalcArmor`, called between the bonus
bytes and the maxima, adds 5 to 25 per figurine in bag 2 (definition flag bit 45) to one
of the four statistics, so figurines raise maximum hit points, mana and the load limit
but not the bonus bytes; `docs/spec/combat.md` sections 7 and 8, executed). The six constants are float immediates chosen by a chain of class tests
at `0x1b6740–0x1b694c`: defaults first, then overrides for class 0, 2, 1, 4, 3, 5, 6 in
that order. **Observed.** `--table class_formulas` evaluates the chain for each class.

### 4.4 Experience and levelling

- `g_expTable` 0x41b558: 81 s32, index = level. A character leaves level `l` when its
  experience reaches `table[l]`. `table[80]` is a sentinel far above the rest: experience
  is clamped to `table[80] − 1` (through the pointer 0x41b698), so level 80 is the last.
  `player_importCharacter` clamps imported experience to `table[50]` (0x41b620) and levels
  to 50. **Observed.**
- `player_giveExp(slot, amount)` 0x1d3150, per level gained: skill points (record +0xe8)
  += 1 below level 6, 2 below 16, 3 below 26, 4 below 36, else 5; stat points (+0xec)
  += 3; level (+0x59) += 1; `player_recalcStats`; hit points and mana refilled if alive.
  **Observed.**
- Two level bytes exist: +0x59 is the level earned, +0x58 the level the player has
  acknowledged in the level-up screen (`docs/ui.md`). Hit points and mana use +0x59;
  attack rating (4.5) and skill requirements (4.6) use +0x58. **Observed.**

### 4.5 Player damage and attack rating — `Player_recalcDamage` 0x1b7158

```
attack rating (record +0xcc) = level(+0x58) * 20 + bonus + weapon attack rating (def +0x1a)
damage min/max (record +0xd0/+0xd4) = weapon range + bonus          (unarmed: 1 + bonus, 2 + bonus)
bonus = dexterity / 4 for bows and thrown weapons (subtype 4, 6), else strength / 4
```

then multipliers from skills 60 and 61 (`1.15 + 0.05 × rank`, applied by the weapon's
damage-type bit), the passive with mask 0x40000 (+2.5 % per rank when a second weapon is
equipped), the archery and throwing skills, and status counters 2 and 4 (×1.5, ×1.2).
**Observed** for the first three lines (`0x1b71b8–0x1b7270`); the multiplier section was
read from the decompile only. It has since been executed against a reference model
(`docs/spec/combat.md` section 9), which adds two things this summary gets wrong or
leaves out: in the thrown-weapon branch the maximum is raised by the share of the *new*
minimum, not of the maximum (0x1b7478); and the dual-wield passive multiplies only the
factor of the weapon's own damage type (type 1 or type 8). The full order of the
multipliers, including Ancestral Call and the class-5 and class-6 state bonuses, is in
that section. Record +0xcc is what melee passes to `damage_apply` as
`attack`, where it is compared with the victim's armour (`docs/gameplay.md` §2.1, §2.5).

### 4.6 Skill trees, passives, skills

**Skill trees** — seven static tables, one per class (class → address: 0 → 0x4f4898,
1 → 0x4f4e38, 2 → 0x4f4b68, 3 → 0x4f5108, 4 → 0x4f53d8, 5 → 0x4f5720, 6 → 0x4f5a18;
selection at `0x1d47d4–0x1d4848`). Rows are 0x28 bytes; the list ends at a row whose `x`
is −1. 122 rows in all (16–20 per class). Observed in `skills_screen` 0x1d4660.

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | u8 | 1: +0x08 is a skill id (index into `g_skillTable`); 0: +0x08 is a passive mask |
| +0x01 | s8 | base level requirement; the next rank needs level ≥ this + current rank |
| +0x08 | u64 | skill id or passive mask |
| +0x10 | s32 | prerequisite kind: 1 skill id, 0 passive mask |
| +0x18 | s64 | prerequisite: −1 none; 0 means "any rank in skill 60 or 61"; else the id or mask that must have rank ≥ 1 |
| +0x20, +0x24 | s32 | position of the node on the tree picture |

Maximum rank is 20 (tests at `0x1d5418` and `0x1d5778`). Ten alternative prerequisites
("this skill may also be unlocked by that one") are *not* in the table but written as
class-and-id tests in `skills_screen` (`0x1d558c–0x1d5778`); a rebuild must copy them from
the code.

**Class passives** — seven source lists (class → address: 0 → 0x4ebbe8, 1 → 0x4ebec0,
2 → 0x4ec400, 3 → 0x4ec2b0, 4 → 0x4ec0b8, 5 → 0x4ec748, 6 → 0x4ec5c0), rows of 0x38
bytes ended by a row named `END`: `char name[0x20]`, +0x20 u8 (always 0), +0x21 u8 maximum
rank, +0x22 u8 point cost, +0x24 float (non-zero on one row; use Unknown), +0x28 u64 mask.
`classSkills_init` 0x1ac7a8 copies them to seven run-time tables of 48 rows at
`g_classPassiveTables` 0x4ef510 (stride 0xa88), from `game_resetState`. The rank of a
passive is the byte at record +0xef + row index (`player_getPassiveLevel` 0x1bed48). Rank
cost: `cost × (rank + 1)`, or `cost + int(pow(rank, 1.6))` when cost > 4
(`skills_nextRankCost` 0x1d436c). **Observed.**

**Legacy ability table** — `g_legacyAbilities` 0x4f5cc8, 21 rows of 0x68 bytes ended by
`END`, in the layout of the player's ability record (`docs/player.md`), with the passive
mask at +0x48. `player_rebuildAbilities` 0x1d34ac copies the row whose mask matches into
the record and applies three hard-coded side effects (mask 0x40: load limit +15; 0x80: hit
points +3; 0x100: mana +5). **Observed.** Inferred: left over from the engine's previous
game; most rows describe passives.

**Skills** — `g_skillTable` 0x41b170 is static: 102 pointers (ids 1–101 used) to objects
in `.bss`. Everything else about a skill is code:

- name, kind, recast delay and virtual table: the constructor, called (or inlined) by the
  static initialiser 0x16ac74;
- per-level statistics: `initStats` (virtual slot 9), called once for every id by
  `skills_callVslot9All` 0x1ebca0 ← `game_initCamera` 0x1e6b68 ← `main` 0x323e48;
- mana cost: virtual slot 5 (a formula or statistic 4);
- the text: key `<name>_name`, `<name>_rankdesc` (formatted by virtual slot 4).

Six constructors serve several ids and choose the name and numbers by id. `--table skills`
runs each constructor and each `initStats` with the real id, following the branches that
depend on it, and prints the two tiers of five statistics as stored (layout in
`docs/skills.md`: first level, value at that level, increase per level). **Observed** for
the mechanism; the printed values are as good as the reader in the tool (section 9).

### 4.7 Starting gear — `player_giveStartingItems` 0x1acc78

20 KB of code: 323 calls of the descriptor parser on string constants, selected by class,
by model (two models get their own sets) and by debug switches at 0x41b550–0x41b554.
There is no table. `--table fixed_descriptors` lists every descriptor string the function
references (231 references); which class gets which is in the branches. **Observed.**

## 5. Difficulty

`g_difficultyIdx` (0x4f719c) is 1–5. (An earlier version said it is also stored in bits 32–36 of record +0x4c18; those bits hold a character-kind value set at creation — see docs/issues/doc-corrections.md, row 16.) There is no
difficulty table. Every effect found is a constant in one of these functions (all
Observed):

| Function | Effect |
|---|---|
| `game_loadLevel` 0x1e55c0 (`0x1e5b98–0x1e5c94`) | `g_levelMonsterLevel` = level-table byte + 2 on difficulty 1; `(byte + 2) × 0.75 + {34, 61, 88, 115}` on difficulties 2–5; 3.0 in PvP mode B, but only on difficulty 1 — the difficulty 2–5 lines are computed from byte + 2 after the PvP store and overwrite it (0x1e5ba4–0x1e5c48; `docs/spec/combat.md` 4.1); then forced to 1.0 in `stomedal` and 2.0 in `innpit` |
| `Creature_setStats` 0x10a620 | monster hit points ×1.5, ×2, ×2.5, ×3 on difficulties 2–5 (not in those two levels) |
| `level_monsterLevelTimesDifficulty` 0x1ebf70 | monster level × {8, 9, 10, 11, 12}: budget for chests and script rewards |
| `item_generateFlag35Entry` 0x106214, `item_generateFlag45Entry` 0x106658 | minimum definition level for reagent and figurine drops: none, 17, 27, 32, 38 |
| `item_generateConsumable` 0x108590 | potion size from the monster level and min(difficulty, 3) |
| `shop_openOrStock` 0x1c7af8 | stock budget and level cap include `(difficulty − 1) × 11` and `× 24` terms |
| `AutoContainer_run` 0x23e430 | explosion damage ×3 on difficulty 2, ×6 on 3 |

Because everything a monster has is multiplied by `g_levelMonsterLevel` (3.2), the first
row is the main difficulty lever: the higher difficulties replace a level's 3–36 scale by
roughly 36–142.

Other writers of `g_levelMonsterLevel`: `arena_startWave` 0x305ed4, and four functions
that swap it temporarily — save, set, restore around one call — (`Skelight_ctor` 0x2a8770,
`Skelight_loadState` 0x2a90b0, `CastBadger_ctor` 0x244e4c, `CastBadger_loadState`
0x245568; the earlier version listed two of the four, `docs/issues/claims-audit.md`
row 80).
Which difficulties a player may select is decided in the front end from flag bits at
0x4f8f38 (`options_get4f8f38Level` 0x1ec448); **Unknown** what sets them. Mission
availability is stored per difficulty (record +0x4bbf + difficulty × 13 + mission).

## 6. Text

- One string file per language, wrapped in a lump: `GTEXT.LMP` (entry `gtext.uni`), and
  `GTEXT_DE.LMP`, `GTEXT_FR.LMP`, `GTEXT_SP.LMP` with the same entry name. The executable
  references only `gtext.lmp` (`main`, 0x323f9c); no string for the other three exists in
  it. **Observed.** Inferred: the US build always loads English.
- Format of a `.uni` entry stream (Observed in `text_registerTable` 0x173bac and by
  parsing all four files to their last byte):

  ```
  repeat until a key starts with a zero byte:
      key      ASCII, zero-terminated
      pad      to the next even offset after the terminator:  next = (start + len + 2) & ~1
      text     UTF-16LE, terminated by a zero code unit
  ```

  5,498 entries in the English file (4,309 distinct keys; a repeated key keeps its first
  entry reachable, see below), 4,304 in each of the others.
- Lookup: `text_lookup(key)` 0x173c84 drops double-quote characters from the key, hashes
  it with `text_hash` 0x173a74 to 13 bits and probes `g_textHash` (0x7c2ea0, 8,192
  pointers to keys) linearly until `strcmp` matches; the text is at
  `(keyAddress + strlen + 2) & ~1`. Registration inserts each entry at the first free slot
  from its hash, so of two entries with the same key the earlier one is found. A missing
  key returns `NF:` followed by the first 16 characters of the key. **Observed.**

  ```
  h = 0                                   # 32-bit
  for c in key:  h = (h + c) * 0x401;  h ^= (signed)h >> 6
  h = h * 9;  slot = (h ^ (signed)h >> 11) & 0x1fff
  ```
- Key conventions seen in code (Observed format strings): `<item name>_name` (0x520058),
  prefix and suffix keys straight from the affix tables, `<skill name>_name` and
  `<skill name>_rankdesc`, `<passive name>Desc` (0x53b660), `menu_mis0…12`, `mb_<class>`
  for monster names (`Creature_getName` 0x118418). About 1,900 keys are generated ids (a
  few letters of the English text plus hex digits) used by scripts and dialog.
- Item names are assembled from several entries with language-dependent grammar
  (`docs/startup.md`, "Display names").

## 7. Levels and missions

### 7.1 Level table — `g_levelTable` 0x4f7210

90 rows of 0x30 bytes, ended by a row with a null name; **that terminator row is also the
default row**, used for a name that matches nothing. Read by `game_loadLevel` 0x1e55c0.

| Offset | Type | Meaning | Kind |
|---|---|---|---|
| +0x00 | char* | level name | Observed |
| +0x04 | s8 | monster level; `g_levelMonsterLevel` = this + 2 (section 5) | Observed |
| +0x05 | s8 | × 0.25 into two floats at 0x41c16c / 0x41c170 (model code; purpose Unknown) | Observed |
| +0x08 | float | kill plane height → `g_killPlaneZ` 0x4f7188 | Observed |
| +0x0c, +0x10 | float | → 0x4f718c, 0x4f7190; no other reader found | Observed; purpose Unknown |
| +0x14 | s32 | element count of a pool allocated at load (0x12b0 bytes each, `0x186dbc`) | Observed; what the pool holds Unknown |
| +0x18 | s8 | → 0x4f7208; only `game_loadLevel` touches it | Observed; Unknown |
| +0x1c | float | → 0x44f030, read by 0x187eac | Observed; Unknown |
| +0x20 | u32 | level flag word → 0x44fe08, read by 34 functions (bits 0x100 and 0x10000000 are tested in `Creature_run`, `Player_run`, `AutoContainer_run`) | Observed; bit meanings Unknown |
| +0x24…+0x2a | s16 × 4 | arguments of the sound set-up call 0x2156e0 | Observed |
| +0x2c | s16 | → 0x4f7152 | Observed; Unknown |

Lookup (`strcmp` at 0x1e57ec, `strncmp` at 0x1e584c, `strstr` at 0x1e58b8): the request is `name` or `name_sub`
(`g_pendingLevel` 0x41b6d0 is split at the first `_` by `mainloop_loadRequestedWorld`
0x320edc into `g_levelName` and `g_levelSubName`). The table is searched three times: for a
row equal to `name_sub`, then for a row whose name starts with the requested name
(`strncmp` over the request's length), then for a row whose name occurs inside the
request (`strstr`). Because the first pass always compares against `name_` plus the
sub-name, a plain name is resolved by the prefix pass, which takes the first matching row
in table order — so the order of the rows is part of the data. **Observed.**

### 7.2 How a level names its files

For level `<name>` (Observed in `game_loadLevel`, format strings 0x53da80 `%s.gob`,
0x53daa0 `%s.lmp`):

| File / entry | Contents |
|---|---|
| `<NAME>.GOB` on the disc | archive of lumps: `<name>.lmp`, `env.lmp`, `waterenv.lmp` |
| `<name>.lmp` → `<name>.world` | geometry (entry found by the extension `world`) |
| `<name>.lmp` → `objects.ob` | object placement (7.3) |
| `<name>.lmp` → `script.scr`, `*.cut`, `ambient.bin`, `*_dialog.bin`, `*.dbin` | script, cutscenes, ambient sound list, dialog |
| `<NAME>.TEX`, `<NAME>.VAT` | streamed textures and audio (not read here) |
| `L<NAME>.LMP` (file name cut to 8 characters) | one entry `shot.tex`. Inferred: the loading picture; the code that opens it was not read |

Formats of GOB and LMP are in `docs/FORMATS.md`. 119 `.GOB` files on the disc contain an
`objects.ob`; the level table has 90 names (some archives are test or cutscene levels —
**Inferred**, not checked one by one).

### 7.3 `objects.ob`

Layout as in `docs/objects.md` ("Level-object records"), confirmed by parsing every file
on the disc to the last record:

```
s16 count;  u16 flags;  s32 stringTableOffset;
count × { s32 className; s16 recordSize; u16 angle; float x, y, height;
          s32 property[…]; s32 0; }          # string offsets relative to the string table
```

The class name goes to the factory (`world_objectFactory` 0x159c94), which tests it
against 208 names in a fixed order — exact or prefix, case-insensitive — and falls back to
property tests. The first match decides the C++ class and the allocation size; the full
name is kept at object +0x34 and is the key into `monsters.bal`. **Observed.**

### 7.4 Mission table — `g_missionTable` 0x4fe540

13 rows of 0x34 bytes; row `i` is mission number `i + 1` (mission 0 has no row; the
thirteenth row has no names). Read by `missionMenu_run` 0x2316fc and the helpers at
0x231078–0x2314c8.

| Offset | Type | Meaning | Kind |
|---|---|---|---|
| +0x00, +0x04 | char* | display-name keys (second: alternative used on the last row) | Observed strings; use of +0x04 Inferred |
| +0x08 | char* | level started for the story mission | Observed, `missionMenu_run` state 8 |
| +0x0c | char* | level started instead when it is non-null and `game_getEvil()` is set | Observed |
| +0x10 | char* | medal-round level (offered when the mission is complete) | Observed `0x2312a8` |
| +0x14 | char* | bonus level (offered with the top medal) | Observed `0x2313b4` |
| +0x18, +0x1c | char* | pictures | Observed strings |
| +0x20, +0x24, +0x28 | s32 | flags gating three menu entries: +0x20 with "mission complete" (0x231310), +0x24 with the medal lookups (0x23112c), +0x28 with the top-medal test (0x231360) | Observed tests; the names "replay / medals / bonus" are Inferred |
| +0x2c, +0x30 | s32 | position on the menu map | Inferred |

Menu text keys: `g_missionMenuTextKeys` 0x4f83c0 (13 pointers). Progress lives in the
player record: availability and completion per difficulty and mission, medals per mission
(`docs/player.md`). New characters get mission 0 available and complete on all five
difficulties (`0x1b2410–0x1b2450`).

## 8. Rules that are code, not data

A rebuild has to re-implement these by hand. Constants are float or integer immediates in
the function named unless stated.

| Rule | Function | Notes |
|---|---|---|
| Monster statistics from multipliers, level, players, rank, difficulty | `Creature_setStats` 0x10a620 | 3.2 |
| Which type names are bosses | `creature_bossRank` 0x10d940 | string compares |
| Monster resistances, kind, speeds, material flags | 73 creature constructors (`docs/monsters.md` §3.1) | 3.3 |
| Monster behaviour, attack choice, skill use | each class's run and setState functions | `docs/monsters.md` |
| Drop parameters per monster class | death helpers calling `Creature_dropLoot` 0x10f2c8 | 49 sites |
| Boss and mini-boss extra drops | `Creature_dropLoot` 0x10f2c8 | class tests |
| Drop sequence and chances | `loot_generateDrops` 0x100d54 | `docs/startup.md` |
| Random item generation, affix choice, required level | `item_generateWithAffixes` 0x104ca4, `item_generateFromSpecialTable` 0x104758, 0x106214, 0x106658, 0x108590 | |
| Item value | `item_getValue` 0x1024a8 | not fully transcribed here; transcribed and executed in `docs/spec/items.md` §5 |
| Item weight compression | `item_getWeight` 0x103e08 | |
| Descriptor token → modifier code | `item_parseDescriptor` 0x1069b8 | 1.3 |
| Hit, miss, critical, mitigation, elemental procs | `damage_apply` 0x1e8230 | `docs/gameplay.md` §2 |
| Kill experience and its split | `Creature_processDamage` 0x110d30 | 3.5 |
| Level-up rewards | `player_giveExp` 0x1d3150 | 4.4 |
| Max hit points, mana, load limit per class | `player_recalcStats` 0x1b6458 | 4.3 |
| Player damage and attack rating | `Player_recalcDamage` 0x1b7158 | 4.5 |
| Player armour | `player_recalcArmor` 0x1b5790 | not read here; read and executed since — `docs/spec/combat.md` section 8: resistances, figurines, armour from the 17 equipped items, and the `healthbonus` / `manabonus` modifiers (codes 5 and 6), which it adds to the maxima and its caller `player_recalcStats` then overwrites (0x1b69bc, 0x1b69c4) |
| Regeneration | `Player_regenHealth` 0x1b3b90, `Player_regenMana` 0x1b3900 | `docs/player.md` |
| Model → class | `player_initNewCharacter` 0x1b1d70 | 4.1 |
| Starting gear | `player_giveStartingItems` 0x1acc78 | 4.7 |
| Skill definitions and per-level numbers | constructors and `initStats` of 101 skills | `docs/skills.md` |
| Skill mana cost | each skill's virtual slot 5 | |
| Extra skill-tree prerequisites, maximum rank 20 | `skills_screen` 0x1d4660 | 4.6 |
| Passive rank cost | `skills_nextRankCost` 0x1d436c | 4.6 |
| Passive side effects (load, hp, mana) | `player_rebuildAbilities` 0x1d34ac | 4.6 |
| Level scale per difficulty; the two fixed-scale levels | `game_loadLevel` 0x1e55c0 | 5 |
| Chest / reward budget per difficulty | `level_monsterLevelTimesDifficulty` 0x1ebf70 | 5 |
| Shop stock | `shop_openOrStock` 0x1c7af8 | 2 |
| Type name → class and size | `world_objectFactory` 0x159c94 | 7.3 |
| Hub selection (good / evil) | `game_getHubName` 0x1ec300 | |
| Selectable difficulties | `options_get4f8f38Level` 0x1ec448 and `frontend_run` | 5 |

## 9. `tools/dump_tables.py`

Standard library only. It holds addresses, row sizes and field offsets and nothing from
the game; it refuses an executable whose SHA-256 is not this build's unless `--force` is
given.

```
python3 tools/dump_tables.py SLUS_209.73 --list
python3 tools/dump_tables.py SLUS_209.73 --table item_defs            # CSV on stdout
python3 tools/dump_tables.py SLUS_209.73 --balance BALANCE.LMP --text GTEXT.LMP \
        --objects LEVEL1.GOB LEVEL2.GOB --all --out dumps/           # CSV or --format json
python3 tools/dump_tables.py --iso game.iso --all --out dumps/        # reads everything from an image
```

Tested against this build's executable, `BALANCE.LMP`, the four `GTEXT*.LMP` files and
all level archives, both as separate files and read straight from the disc image; CSV and
JSON output both written and the JSON re-parsed. Row counts from that run:

| Table | Source | Rows | How it is read |
|---|---|---|---|
| `item_defs`, `item_presets` | executable | 607, 835 | fixed rows to the null row |
| `item_prefixes`, `item_suffixes`, `item_models` | executable | 73, 165, 134 | fixed rows |
| `loot_quality`, `weapon_value_mult`, `body_codes`, `potion_names` | executable | 12, 7, 12, 18 | fixed rows |
| `class_stats`, `exp_table` | executable | 7, 81 | fixed rows |
| `class_passives`, `skill_trees`, `legacy_abilities` | executable | 52, 122, 21 | fixed rows to the end marker |
| `levels`, `missions` | executable | 91 (with the default row), 13 | fixed rows |
| `item_tokens` | code | 43 | format string at each scanner call in the parser, and the code loaded after it; all 42 modifier codes found |
| `class_formulas` | code | 7 | walks the class test chain once per class with the class value known |
| `skills` | code | 101 | runs the static initialiser, each constructor and each `initStats` with constants tracked and id-dependent branches followed; every id got a name, a virtual table and a statistics function; no store with an unknown value |
| `boss_names` | code | 22 | string argument of each compare in `creature_bossRank` |
| `object_factory` | code | 208 | each name test and the allocation and constructor call its match leads to; agrees with the table in `docs/objects.md` on the rows compared |
| `creature_classes` | code | 75 | each caller of `Creature_ctor` read straight through; 62 have a constant hit-point argument, 56 a constant class-definition block, 70 a factory name |
| `loot_calls` | code | 49 | float arguments at each call of `Creature_dropLoot`; all six found at all 49 |
| `fixed_descriptors` | code | 282 | references to strings that start with an item definition name, in the 29 functions that call the parser |
| `monster_balance` | `BALANCE.LMP` | 184 | 182 names recovered by hashing |
| `text` | `GTEXT*.LMP` | 5,498 (English) | parsed to the last byte |
| `objects` | level `.GOB` / `.lmp` / `objects.ob` | 18,675 from 119 archives | parsed to the last record |

Limits of the "code" tables: `creature_classes` does not evaluate branches, so a value
stored for one variant only appears as an alternative without its condition, and a value
computed at run time is blank; `fixed_descriptors` lists references, not calls (several
call sites share one string); none of these tables was compared against memory of a
running game. Check anything that matters against the function address printed in the row.

Not dumped: `item_getValue`'s constants, the per-class branches of the starting gear, the
boss branches of `Creature_dropLoot`, the nine extra skill prerequisites, the shop
arithmetic, and monster behaviour.

## 10. Corrections and additions to earlier documents

| Document | Was | Is | Evidence |
|---|---|---|---|
| `docs/startup.md`, definition +0x1a | "Meaning Unknown" (open question 2) | weapon attack rating | `Player_recalcDamage` 0x1b7158 adds `item_getModifiedField1a` to record +0xcc, which melee passes as `damage_apply`'s `attack` |
| `docs/player.md`, record +0xcc | "damage type passed to the damage function" | attack rating = level × 20 + strength or dexterity / 4 + weapon rating | same; `docs/gameplay.md` §2.1 already describes the parameter |
| `docs/creatures.md`, creature +0xd4 and +0xe4 | "scaled stat, Unknown" | attack rating and armour class | `Creature_setStats`; monster melee passes +0xd0, +0xd2, +0xd4 to `Creature_hitTargetInArc` 0x119938, which forwards the third as `damage_apply`'s `attack` (read in `Amphian_run` 0x23483c) |
| `docs/monsters.md` §1.3 and §2.1, +0xd4 | "damage type" | attack rating; the *next* argument (8, 0x40001, …) is the flag word with the damage class | same |
| `docs/skills.md` id table | id 33 `criticalhit`, id 53 `rangercriticalhit` | the other way round (the statistics columns are already right) | `SkillCriticalHit_ctor` 0x2e72ac–0x2e72fc: id 0x35 takes the string at 0x550220, id 0x21 the one at 0x550248 |
| `docs/skills.md` slot 9 | "Who calls it was not found" | `skills_callVslot9All` 0x1ebca0, from `game_initCamera` 0x1e6b68, from `main` | call at 0x1e6bac; already named in `symbols/gameplay.tsv` |
| `docs/gameplay.md` §2.2 | "Kind 0x12 is Unknown" | the kind the `bugzapper` (0x19) and `bugexploder` (0x1a) item effects act on; 0x10 is the kind of `undeadbonus` (0x1b) and `undeaddestroy` (0x1c) | token → code pairs in `item_parseDescriptor`; constructors of the ant, beetle and spider classes store 0x12 at +0xb4. Inferred from names |
| `docs/startup.md`, quality table | "10 × 3 floats" | 12 rows are present; 10 are selectable | 0x3e9c90–0x3e9ca7 hold two more rows; clamp at `0x100e50` |

No patches are proposed and no ledger rows: nothing here touches online play.

## 11. Not done, and open questions

- `item_getValue`, the shop budget arithmetic and `player_recalcArmor` were not
  transcribed; a rebuild needs all three. (Two of the three are done since, both executed
  against the original: `item_getValue` in `docs/spec/items.md` §5, `player_recalcArmor` in
  `docs/spec/combat.md` section 8. The shop budget arithmetic is still open.)
- The boss branches of `Creature_dropLoot` (which class gets which extra calls) were read
  only as far as their shape.
- The multiplier half of `Player_recalcDamage` was read from the decompile, not the
  disassembly. (Executed since: `docs/spec/combat.md` section 9; see 4.5.)
- Who tests modifier code 0x13 (`requiredclass`) and the other `required…` codes, and
  whether the class value is 0- or 1-based. (Answered since: `inventory_checkEquipAllowed`
  0x1c4948 tests all of them, and the class value is 1-based; §1.3 above and
  `docs/spec/items.md` §6.)
- Level table +0x05, +0x0c, +0x10, +0x14, +0x18, +0x1c, +0x2c and the bits of +0x20.
- Word 0x4f713c (suppresses player-count scaling of monsters) and the flag bits at
  0x4f8f38 (difficulty unlock): writers not found.
- Two `monsters.bal` records have no name, and 50 records (those two and 48 named ones)
  match no object placed in a level file. Whether generators or scripts create them was
  not checked.
- Whether the US disc's other language lumps are reachable at all (the language byte
  0x44fddc changes grammar and number formatting, but no code path that loads
  `GTEXT_xx.LMP` was found).
- Everything in the "code" tables of the tool should be spot-checked against a memory
  snapshot of a running game: skill objects at 0x6e14d8 onward, a creature's +0x5c…+0x6c
  after construction, and `g_levelMonsterLevel` per level and difficulty.
