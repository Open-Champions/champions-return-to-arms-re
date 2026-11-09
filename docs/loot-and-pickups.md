# Loot and pickups in normal play

2026-11-09, SLUS_209.73 US v2.00 (SHA-256 `292f6f48…dcd675`). Branch
`t3/research-loot-drop`, started from `77c2f70`. This note covers a creature's
death drop, the ground objects that result, how a player picks them up, and
chests. It cross-references existing work instead of repeating it:

- generation (rolls, budgets, generators): `docs/spec/items.md` §8, lines 485–567,
  executed against `tools/ref_items.py` by `tools/difftest_items.py`;
- flight, settling, Gold contact and credit, Chest opening: `docs/loot-drop.md`
  §§1–6 (this branch, `cbd59bf`/`7cb3620`/`77c2f70`);
- `givePlayerItem`: `t3/research-items` `5a683b4`, `docs/give-player-item.md`;
- item generators as used by shops: `t3/research-vendor-stock` `fdf6752`,
  `docs/spec/vendor-stock.md` lines 154–185.

New here: the first execution of `Creature_dropLoot` 0x10f2c8, all of whose
branches had only been skimmed (`symbols/creatures.tsv` line 33). The other new
items are level/difficulty scaling and gold amounts measured on the real roll,
the `ItemProp_ctor2` 0x1590ec call sites (an open item in `5a683b4`,
`give-player-item.md` line 183), the givePlayerItem-versus-pickup boundaries,
and the generic `AutoChest_dropLoot` 0x23ba3c roll. `creature_bossRank`
0x10d940 is executed with its 16 plain names and three name/property pairs.
A census gives the five `loot_spawnNamedItem` 0x100ba0 call sites.

**Labels.** **Observed** means read from addressed original instructions.
**Executed** means those instructions ran in `tools/ee_emu.py` on constructed
state in `tools/difftest_loot_and_pickups.py` (cited as `lp:<line>`), run with
seeds 20973 and 7. Only the gold comparison in §1.3 depends on the seed.
Every other section scripts or stubs each draw it depends on, so the two
seeds give the same results there (§7). **Inferred** is a deduction. **Unknown** means not
established. Nothing here was seen in a running game. No game text is stored.
Descriptor and key strings are read from the executable at run time, and
creature classes are named only by their type-getter address. The matching
symbol rows are in `symbols/runtime.tsv`.

## 1. What a creature drops when it dies

### 1.1 The caller supplies six numbers

**Observed** (`docs/data-tables.md` lines 160–181; `docs/monsters-2.md` per
class): there is no per-monster loot table. Each class's death state (0x14)
calls `Creature_dropLoot(zOffset, throwSpeed, goldScale, goldChance,
qualityRow, itemChance; this, &pos, angle, reagentFilter)` with float
immediates. The most common set is `(36, 2, 1.6, 0.6, 1.4, 0.25)`.
**Executed** (`lp:223`): there are exactly 49 `jal 0x10f2c8` sites.

### 1.2 `Creature_dropLoot` 0x10f2c8, executed

Stubs and constructed state in this section (`drop_run`, `lp:132–184`):

- `loot_generateDrops` 0x100d54 is a recorder that keeps the position copy,
  angle, filter, force flag and the six floats of each call.
- The own generator `GameObject_rand` 0x1509d0 is a stub that returns a scripted
  sequence (and asserts it is asked for the creature itself), so that each
  threshold is tested on both sides.
- The creature's type getter (the word at vtable + 4; the vtable pointer is at
  object `+0x48`) is a stub. For the
  plain creature it returns a sentinel type object built in emulator memory,
  whose name is the made-up string `probe-only-type`, so it matches none of the
  eleven classes. For a class test it returns what the real class getter
  (0x3c4888, …) returned when run first.
- The object (0x600 zeroed bytes), its flags, name pointer, tint byte and
  property list are constructed.

Everything else is original: `obj_getPropInt` 0x14c880, `creature_bossRank`
0x10d940, type compare 0x3b1250 and the string routines. The reference is
`ref_drop` (`lp:187–212`), written from the instructions at
0x10f2c8–0x110718.

**Observed / Executed**, in order:

1. Creature flag `+0xa8 & 0x100000000` set: no drop at all (0x10f33c–0x10f358).
2. Property `noloot` (key at 0x52ffd8) with a **nonzero integer value**: no drop,
   unless PvP mode B (0x4f7120) is set (0x10f360–0x10f37c). The property is read
   with `obj_getPropInt`, so `noloot=0` still drops (`lp:255`).
3. Eleven exact-type tests (the getter's type compared by 0x3b1250, which
   matches on pointer or name). The count of eleven is the earlier Observed
   reading (`docs/data-tables.md` line 173; `docs/issues/kill-loot-xp.md`
   line 236). The tool runs those eleven getters (`lp:49–50`) but
   does not itself count the type compares in 0x10f2c8–0x110718. A matching
   class makes its own calls and **returns**: no tint and no trailing ordinary
   call (`lp:272–318`). Two are gated: class 5 (getter 0x3cc568) only when
   `+0xa8` bit 0 is set (0x10fb7c), and class 6 (0x3ca4ac) only when the word
   at `+0x3d8` is nonzero (0x10fcfc). Ungated, both fall through to the generic
   path, tint included (Executed).
4. Generic path. Rank comes from `creature_bossRank` 0x10d940, **Executed**
   on its own (`lp:322–383`, the real function, no stubs):
   - 0 unless object flag `+0xc & 0x20` (0x10d954–0x10d95c).
   - 2 if the type name at `+0x34` equals one of 16 strings (0x52fd48–0x52fe10
     and 0x52fe50, 0x52fe60; compares 0x10d964–0x10dbb0 through 0x3b81a0). The
     names are compared by content: the test stores a fresh copy.
   - 2 for two more type names only together with a value of the creature's
     own **`name` placement property**. The key is at 0x52fab0, read with
     `obj_getPropStr` 0x14f4c0 at 0x10dad8, 0x10db18 and 0x10db5c. The pairs
     are (0x52fe20, 0x52fe30), (0x52fe20, 0x52fe38) and (0x52fe40, 0x52fe48).
     It is a property of the object, not the level name. This is the reading
     of `docs/data-tables.md` lines 296–298, now executed. With any other value
     these two names fall to the MiniBoss bit.
   - Otherwise `+0xa8 & 1` (the MiniBoss flag), also when `+0x34` is 0.
   - **Observed, not executed:** if one of the two conditional names has no
     `name` property, `obj_getPropStr` returns 0 and the string compare at
     0x10dae8 reads address 0 (there is no null test). The emulator does not
     map address 0. On the console the result depends on what is there
     (**Unknown**).

   Then:
   - Rank 2 makes three calls before the per-player loop: the caller's six
     numbers with its filter, then `(4, 1, 6, 2)`, then `(5, 1, 7, 2)`. These
     are gold scale, gold chance, quality row and item chance, with the caller's
     z offset and throw speed. Then, for each joined player, one own draw and
     `(0, 0, 8.5, 2)`, with the preset forced when the draw is below 0x8000.
   - Rank 1 makes two calls, `(4, 1, 3, 1.5)` and `(5, 1, 5, 1.5)`. Then, per
     player, `(0, 0, 7, 1.5)`, with the preset forced when the draw is below
     0x4000.
   - `GameObject_rand` returns `state >> 16`, so 0…0xffff (Executed earlier,
     `docs/issues/dynamic-tests.md` line 319, row i7). Below 0x8000 is
     therefore one half of the values and below 0x4000 one quarter.
   - Tint byte `+0xa0` nonzero: gold scale ×3 and quality row ×4, applied only
     to the trailing ordinary call (0x1106bc–0x1106dc).
   - Trailing ordinary call (caller's numbers and filter, force 0): only when
     `+0xa8` bit 0 is clear (0x1106e0).

**Executed consequences:** a rank-2 boss that is not flagged MiniBoss gets its
extras **and** the ordinary drop: 5, 6 or 8 calls for 1, 2 or 4 players. A
MiniBoss gets 2 + players calls and no ordinary drop. A MiniBoss-flagged object
without `+0xc & 0x20` drops **nothing**, because its rank is 0 and the ordinary
call is gated off (`lp:246`, `a8=1 c=0`). **Observed:** `Creature_ctor`
0x109d68 ORs 0x20 into `+0xc` at 0x109e54–0x109e64. The path from entry to
there has no branch and one call, 0x14cb10 at 0x109db4. So every creature built
through `Creature_ctor` has the bit, and the "drops nothing" case needs
something to clear it. Whether anything does is **Unknown**, as is the meaning
of the bit and of `+0x3d8`.

Class branches (Executed, 3 players, `LOCK` lines in the retained log). The
first number set is (gold scale, gold chance, quality row, item chance), "c" is
the caller's numbers with its filter, and "forced" is the per-player preset
rule:

| Getter | Calls before the per-player loop | Per player | Forced |
|---|---|---|---|
| 0x3c4888, 0x3cc938, 0x3cca98, 0x3c9330, 0x3cc29c | c; 4/1/6/2; 5/1/7/2 | 0/0/8/2 | own draw < 0x8000 |
| 0x3c3c78, 0x3cba24 | c; 4/1/6/2; 5/1/7/2 | 0/0/8/2 | always, no draw |
| 0x3ca4ac (needs `+0x3d8` ≠ 0) | c; 4/1/6/2; 5/1/7/2 | 0/0/8/2 | always, no draw |
| 0x3cc568 (needs `+0xa8` bit 0) | 4/1/5/2; 5/1/6/2 (no c) | 0/0/7.5/2 | own draw < 0x8000 |
| 0x3cb1a0 | c; 15/1/6/2; 20/1/7/2 | 0/0/8/2 | own draw < 0x8000 |
| 0x3ccd64 | 4/1/4/2; 4/1/5/2; 6/1/7/2 (no c) | 0/0/8.5/2 | own draw < 0x8000 |

The per-player preset choice uses the **creature's own** generator (`+0x44`).
Every roll inside `loot_generateDrops` uses the shared seed 0x404464
(`docs/issues/kill-loot-xp.md` lines 246–275).

### 1.3 `loot_generateDrops`: the roll, and what scales it

The full roll is `docs/spec/items.md` lines 485–556 (executed by
`difftest_items.py`; on this branch it gave 5/5 properties on both seeds,
`docs/loot-drop.md` §9). For a client:

- **Party size** (lines 491–495): with 2 or more players, item chance ×2, gold
  chance ×1.5 and gold scale ×2.4 (float×double). Item chance is then halved for
  everyone, or fixed at 0.25 in PvP mode B.
- **Quality** (497–503): row clamped to 0…9 and blended from `0x3e9c18`. Poor
  ×0.5, normal ×1, good ×3.
- **Gold** (504–510): 1, 2 or 3 rolls (draw ≤ 60999, ≤ 63999, else 3). Each
  roll succeeds with `goldChance`, and its amount is
  `trunc(float(draw % 40 + 40) × goldScale × levelFactor04 × 0.035)`. None in
  PvP mode A.
- **Consumable / reagent / figurine** (512–527): 7.5 % + 5 % per extra player;
  1.25 % (0.8 % with a filter); 0.5 %. Reagent and figurine return early when
  nothing qualifies.
- **Equipment** (529–542): budget `quality × U(0.8, 1.2) × levelFactorDiff ×
  200`, tripled 1 % of the time and doubled 4 %. Category: weapon 30000/65536,
  then armour or other. Preset 3 % or when forced, otherwise affixes.

**Executed** (`lp:390–478`). `level_monsterLevelTimes0_4` 0x1ebf20 =
`L × 0.4`, and `level_monsterLevelTimesDifficulty` 0x1ebf70 = `L × (8, 9, 10,
11, 12)` for difficulty 1…5. In PvP mode B, L is replaced by `max(1, L − 4)` in
both. These equal `ref_items.Game` on 60 states: L ∈ {1, 4, 4.5, 5, 22, 60}
(which include the `max(1, L − 4)` edges), difficulty 1…5, and PvP B 0/1.

Gold amounts: the real 0x100d54 matched `ref_items.loot_generate_drops` on
1,152 runs per seed. The caller numbers were z 36, throw speed 2, gold scale
1.6, quality row 1.4 and item chance 0. Gold chance was 0, 0.25, 0.6 (the
common value) and 1.0. The other variables were players 1/2/4, L 1/10/22/40,
difficulty 1/5 and PvP A 0/1. What this comparison leaves out:

- `loot_spawnGold` 0x100974 is a **recorder** on the emulator side, and the
  reference's default `World.spawn_gold` draws nothing (`tools/ref_items.py`
  lines 1326–1340). So the real Gold's own shared-seed draws are absent on
  **both** sides: three scatter draws per try (redrawn while outside the unit
  sphere), up to ten tries, plus one
  `GameObject_ctor` draw (`docs/spec/items.md` lines 558–563). After the first
  gold roll, the draw sequence compared is therefore not the in-game one. The
  first roll's amount, and the rule, are unaffected.
- The pool refuses every item (`spawn_item` returns False on the reference
  side), and every non-roll service is an auto-stub (`emu.follow`).
- The 576 PvP-A runs have no gold by construction, so they compare empty
  lists. The 144 non-PvP-A runs per chance made 0, 54, 126 and 152 gold calls
  at chances 0, 0.25, 0.6 and 1.0 on seed 20973, and 0, 56, 128 and 158 on
  seed 7 (`INFO goldChance` lines).

Results:

- **Gold does not scale with difficulty.** For each chance, the same start
  seed gave identical gold at difficulty 1 and 5. Difficulty enters only the
  equipment budget and chests (`levelFactorDiff`).
- PvP mode A produced no gold call, and gold chance 0 produced none.

Gold per successful roll for the common gold scale 1.6 (from the reference;
amounts are integers):

| Monster level | 1 player | 2+ players |
|---:|---:|---:|
| 1 | 0–1 | 2–4 |
| 10 | 8–17 | 21–42 |
| 22 | 19–38 | 47–93 |
| 40 | 35–70 | 86–169 |

Item generators are the ones the shops use, with the same eligibility, budget
fit and shared-seed order (`vendor-stock.md` lines 154–185). Loot passes
`levelFactorDiff × 200` budgets and `int(L)` as the level cap. Reagent and
figurine generators get half the level (`items.md` line 547).

### 1.4 Fixed drops

`dropitem` placements and script built-ins use `loot_spawnNamedItem` 0x100ba0:
parse, `world_findFreeSpot`, then a PhProp 36 above the point
(`docs/loot-drop.md` lines 53–56; `items.md` lines 565–567).

**Executed** static census (`lp:224–240`): there are exactly **five**
`jal 0x100ba0` sites in 0x100000–0x3c0000. Each site's function is the nearest
preceding stack-frame prologue:

| Site | Function |
|---|---|
| 0x10bf54 | `Creature_onDeath` 0x10beb8 (the `dropitem` property; `docs/issues/kill-loot-xp.md` lines 220–222) |
| 0x147838 | script native 173 `dropItem` 0x1477ac (`docs/script.md` line 734) |
| 0x1478b0 | script native 174 `selectDropItem` 0x147860 (`docs/script.md` line 735) |
| 0x26d648 | 0x26ccfc (symbol row `Goblin_setState`, `symbols/monsters.tsv`) |
| 0x2a3d9c | 0x2a323c (symbol row `Orc_setState`, `symbols/monsters.tsv`) |

The native numbers come from the handler table 0x403370. What the two
monster-state sites drop, and when, was not read (**Unknown**).

## 2. From drop to ground object

| Object | Made by | Constructor | Notes |
|---|---|---|---|
| Flying item (PhProp, 0x248) | the four `loot_generateDrops` sites, named drops, chests | `PhProp_ctor` 0x155a0c, flags 0x441 | rigid body; interactable while flying (`loot-drop.md` §§1–2, lines 24–123) |
| Resting item (ItemProp, 0x190) | a flying item that settles (0x156c4c) | `ItemProp_ctor3` 0x1592bc, supplied matrix | no run list, no expiry (`loot-drop.md` lines 108–123) |
| Thrown-down item (ItemProp, 0x190) | inventory drop, script gifts that do not fit | `ItemProp_ctor2` 0x1590ec, Prop flags 0 | `Prop_run`, not the rigid body (`loot-drop.md` lines 131–140) |
| Gold (0xc0) | `loot_spawnGold` 0x100974, AutoContainer | `Gold_ctor2` 0x157668 | radius 24 / height 72, 41-frame countdown (`loot-drop.md` lines 241–275) |

### 2.1 `ItemProp_ctor2` 0x1590ec: every caller

**Executed** (static census, `lp:499–528`). There are seven `jal` sites, each a
few instructions after `pool_new(0x190)`, and every one passes `a3 = 0`
(launch flags):

| Site | Function | Position |
|---|---|---|
| 0x145c78, 0x145cd0 | script native 53, `givePlayerItem` 0x145a88 | the player object's `+0x10`; when the record's object pointer `+0x43d8` is 0, the object of `g_alivePlayers[0]` (0x4f8440) |
| 0x145ef0 | native 54, `giveOnePlayerItem` 0x145d20 | Observed only |
| 0x146130, 0x146234 | native 55, `givePlayerRandom` 0x145f18 | Observed only; no shipped script calls it (`docs/script.md` line 733) |
| 0x1c24a4 | 0x1c2120, which nothing calls directly (`docs/issues/claims-audit.md` line 216) | Observed only |
| 0x1c47f4 | `inventory_dropItem` 0x1c4310 | `world_findFreeSpot` point (`docs/pickups.md` lines 152–167) |

The symbol row's "5 callers" (`symbols/objects.tsv` line 145) counts functions,
not the seven sites.

**Executed: the givePlayerItem drop closes the `5a683b4` open item**
(`lp:621–712`). With a real pool block, an overweight gift calls
`pool_new(0x190)` and then ctor2 at 0x145c78 with the player object's position
unchanged, the parsed 0x48-byte record, and flags 0. Nothing is written to the
bag and the script result is 0. Other cases:

- `load + weight == limit` is still a drop, because the give test is strict `<`.
- With a null object pointer, 0x145cd0 uses `g_alivePlayers[0]`'s object.
- Two overweight players get one ground item each, at their own position.
- A pool refusal loses the gift.

Replaying the recorded inputs into the real constructor gives vtable
`0x511c38`, the record at `+0x148`, flags `0x102009`, `0x1800` clear, one
`Prop_launch`, no rigid body, radius 4, height 72 and timer 180. The
velocities stay at the zero-filled pool's zeros, because launch flags 0
request no throw. Resource lookup and bounds are synthetic here: the handles
are sentinels, as in `difftest_loot_drop.constructor_cases`. The disc-backed
ctor2 run is `loot-drop.md` lines 150–156.

## 3. Pickup

### 3.1 Gold: walk-over, automatic

**Observed / Executed** (`loot-drop.md` lines 271–295). The normal movement
contact (horizontal `sqrt(dx² + dy²) + 0.001 < 12 + 24`, vertical box ±1000)
calls `Gold_onTouch` 0x157a9c. It requires a player toucher, no prediction
copy, countdown 0 and amount ≠ 0. It queues a HUD floater, zeroes the amount
and deletes the Gold. The balance (`record +0xe4`) is credited by
`hud_tickGold` 0x1dcb80, starting at floater age 43 at `(pending + 7) >> 3`
per tick, capped at 99,999,999. When all eight floaters are busy it credits at
once. No button is involved.

**Inferred** (from the object table in §2, not from a census of touch
handlers): Gold is the only walk-over loot. Every other loot object above is an
item that needs the use button (§3.2). **Inferred:** the LifeTap orb (`docs/spec/skills-35-68.md` lines 6901–6939) is a
skill reward, not loot.

### 3.2 Items: use button

**Observed / Executed** (`loot-drop.md` lines 219–240; `pickups.md` lines
99–137). `Player_interact` 0x1b2640 queries x/y ±48 and z…z+60 and picks the
nearest object with bit `0x100000`. On the use edge, PhProp slot 14 0x155020
or ItemProp slot 14 0x159b38 calls `itemprop_tryPickup` 0x154dbc. Flag-39 items
try every player.

**Executed end to end** (`lp:687–712`): the ground ItemProp built by the
replayed ctor2 is refused at limit 0 and stays. At `limit == weight` it is
taken: it is in the bag through the real `inventory_giveItem`, and its
destructor is called once. "Destroyed" means exactly that call. The
destructor, the word at vtable 0x511c38 + 0xc, is replaced by a **recorder**
that only notes its argument (`lp:692–693`). The real destructor did not
run. Other recorded stubs on the taking path are 0x17365c,
`player_recalcStats` 0x1b6458, `player_countPotions` 0x1ba5f8,
`script_runByName` 0x1ed694 and a sound at 0x214230. On refusal the only one
is 0x1b7ba8. `PICKUP_REAL` (`lp:88`) lists what ran as original
code. The player record and its bags are constructed (`give_machine`).

### 3.3 `itemprop_tryPickup` against `givePlayerItem`

Both paths insert through the real `inventory_giveItem` 0x1c1868, on the same
definition and bag states. Load recalculation is stubbed so that the
constructed load stays fixed (`lp:718–781`).

**Executed:**

| State (one item, weight w) | `givePlayerItem` 0x145a88 | `itemprop_tryPickup` 0x154dbc |
|---|---|---|
| load 0, limit w + 1 | bag | bag (returns 1) |
| load 0, limit w | **ground** (ctor2) | **bag** |
| load 1, limit w | ground | refused, object stays |
| bag count 63 | **bag** (appends cell 63) | **refused** |
| bag count 64 | **lost**: `inventory_giveItem` called once, no cell, no ground item | refused |
| zero weight, limit 0 | bag | bag |
| zero weight, count 63 | bag | refused |

So: pickup refuses at 63 and when `limit < load + w`. A gift appends up to 64,
drops to the ground when `load + w ≥ limit` and w ≠ 0, and silently loses the
item when the bag is already at 64 (`give-player-item.md` lines 67–81 for the
64 case). Starting equipment uses neither path
(`give-player-item.md` lines 141–151).

## 4. Chests and containers

- **Ordinary Chest** (`Chest_interact` 0x292a2c; `loot-drop.md` lines 158–218):
  placed `item=`, `potions=` and `random=` loops build PhProps 12 above the
  chest. Then one `loot_generateDrops(36, 2, 0, 0, 5, 0.95)`, which has no
  gold chance. The chest's own gold is `+0x4c`:
  `r1 % 100 + trunc((r2 % 24 + 12) × worth × (act + 1) × levelFactor04) + 50`,
  with worth 1.5 by default. A second use pays it through the HUD floater.
  Traps zero it.
- **AutoChest** (`AutoChest_dropLoot` 0x23ba3c, Executed `lp:787–830`).
  Stubs and scripted inputs in this run:
  - `loot_generateDrops` 0x100d54 is a recorder, so the rolls themselves did
    not run. Only their arguments are checked.
  - `GameObject_rand` 0x1509d0 is scripted to return one fixed value per run:
    4999, 5000, 14999, 15000, and 0 for the `+0xec` case.
  - `item_parseDescriptor` 0x1069b8 is a stub returning 0.
    `item_generateConsumable` 0x108590 is a stub returning 1.
  - `pool_new` 0x14fdb8 is a stub returning 0, so no object is built.
  - The chest object (0x200 zeroed bytes, position, facing, `+0xec`) is
    constructed.

  With no placed properties and `+0xec == 0` it makes three generic rolls,
  `(36, 2, 0, 0, 5, 0x3f733333)`, `(36, 2, 0, 0, 6, 0x3ca3d70a)` and
  `(36, 2, 0, 0, 9, 0x3ba3d70a)`. These have no gold chance, are at the chest
  position and facing `+0x38`, and pass no filter and no force. Then comes one
  own draw: below 5000 it parses descriptor 0x542130 with variant −1; below
  15000 it calls `item_generateConsumable` 0x108590; otherwise nothing. With
  `+0xec` nonzero it makes no roll and no draw. The meaning of `+0xec` is
  **Unknown**. The placed-property branches are `docs/monsters.md` lines
  747–758, Observed only.
- **AutoContainer** (`AutoContainer_run` 0x23e430, `loot-drop.md` lines 243–257):
  a broken container with no placed item draws own < 24000. Then, only after a
  successful `pool_new(0xc0)`, Gold of
  `1 + trunc(float(draw & 3) × levelFactor04)` at the container position.

## 5. Client-implementable list

1. On creature death (state 0x14), call `Creature_dropLoot` with the class's six
   numbers. Implement §1.2 exactly: dead-loaded flag, nonzero `noloot` unless
   PvP B, the eleven class branches (two gated) that return early, rank 2/1
   extras with per-player own-draw preset forcing, tint ×3/×4 on the ordinary
   call only, and the ordinary call only without the MiniBoss bit.
2. Implement `loot_generateDrops` from `items.md` §8 and `ref_items.py`.
   Shared seed for every roll, in order. Party scaling 2.4 / 1.5 / 2 (then
   item chance ×0.5). Gold uses `L × 0.4` only, never difficulty. Equipment
   uses `L × (8…12)`. Keep the early returns and allocation losses.
3. Loot items are PhProps (flags 0x441, rigid body) that settle into
   `ItemProp_ctor3`. Inventory drops and script gifts that do not fit are
   `ItemProp_ctor2` with flags 0 (no throw, `Prop_run`), at the player
   object's position (or the free spot for inventory drops). Do not substitute
   one constructor for the other.
4. Gold is walk-over: contact radius sum 36, countdown 41 frames, credit through
   the HUD floater queue with the 43-frame delay and 1/8 per tick, capped at
   99,999,999.
5. Items need the use button: nearest interactable in the ±48 / z+60 box, on
   the press edge only. `tryPickup` refuses at bag count 63 or `limit <
   load + w`. Flag 39 tries every player. Destroy the object only on
   acceptance.
6. `givePlayerItem` is not pickup. It appends to 64, drops when `load + w ≥
   limit` (w ≠ 0), loses the item at 64, and always returns 0 to the script.
7. Chests: Chest gold from `+0x4c` on second use. Chest and AutoChest generic
   rolls never make Gold. AutoChest's extra own-draw item is as in §4.
   AutoContainer Gold is `1 + trunc((draw & 3) × L × 0.4)`.

## 6. Unknown

- `creature_bossRank` for a conditional type name with no `name` property
  (the compare reads address 0; §1.2). Which retail creatures carry those
  names and property values, a tint byte, or `+0x3d8`. Whether anything clears
  `+0xc & 0x20` after `Creature_ctor`.
- The eleven-class count is the earlier Observed reading; the type compares
  were not counted by the tool.
- What the `loot_spawnNamedItem` sites at 0x26d648 and 0x2a3d9c drop.
- Gold in the in-game draw order: the Gold scatter and constructor draws were
  left out on both sides (§1.3).
- Touch handlers of other object types: "Gold is the only walk-over loot" is
  Inferred (§3.1).
- `giveOnePlayerItem` and `givePlayerRandom` ctor2 sites, and 0x1c2120: not
  executed.
- `ItemProp_ctor2` with real resources from these callers (only synthetic
  handles here). Its landing and `Prop_run` motion with flags 0.
- Nothing was watched in PCSX2 or the native client. The PCSX2 BIOS gap in
  `loot-drop.md` §9 still applies.

## 7. Reproduction

From the worktree, with the private executable in ignored `local/`. The
research `tools/dis.py` shadows the standard library, so stdlib modules are
imported first:

```sh
export PYTHONDONTWRITEBYTECODE=1
for s in 20973 7; do
  python3 -c 'import inspect, argparse, unittest, runpy, sys; sys.argv=["t", "local/SLUS_209.73", "--seed", sys.argv[1]]; runpy.run_path("tools/difftest_loot_and_pickups.py", run_name="__main__")' $s
done
```

Each run's first line is `commit <sha> tool-sha256 <hash> seed <n>`; the
commit is followed by `(tracked files modified)` when the worktree differs from
it. Results, logs and the commit they were run at are in `work/cursor-report.md`.
Logs are kept in ignored `local/loot-and-pickups/seed-{20973,7}.log`, with the
`LOCK` class rows, the named-item `INFO` rows and the gold `TABLE` lines.

**Seed dependence.** Only the scale section uses the seed: the gold start
seeds are derived from it. The drop and autochest sections script
`GameObject_rand` and stub `loot_generateDrops`. The compare section and the
givePlayerItem cases stub `ItemProp_ctor2` and make no roll. The ctor2 replay
runs `GameObject_ctor` on the seed, but it checks only values that do not depend
on the draw: vtable, record, flags, launch count, radius, height, timer and
zero velocity. The two seed logs, diffed, differ only in the header, the
`INFO goldChance` counts and the summary line. Seed 7 adds coverage only to the gold comparison. No existing
reference API, vector or difftest was changed.
