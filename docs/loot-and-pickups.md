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
and the generic `AutoChest_dropLoot` 0x23ba3c roll.

**Labels.** **Observed** means read from addressed original instructions.
**Executed** means those instructions ran in `tools/ee_emu.py` on constructed
state, seeds 20973 and 7, in `tools/difftest_loot_and_pickups.py` (cited
as `lp:<line>`). **Inferred** is a deduction. **Unknown** means not
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
**Executed** (`lp:207`): there are exactly 49 `jal 0x10f2c8` sites.

### 1.2 `Creature_dropLoot` 0x10f2c8, executed

`loot_generateDrops` 0x100d54 is replaced by a recorder that keeps the position
copy, angle, filter, force flag and the six floats of each call. The own
generator `GameObject_rand` 0x1509d0 is replaced by a scripted sequence, so that
each threshold is tested on both sides. Everything else is original:
`obj_getPropInt` 0x14c880, `creature_bossRank` 0x10d940, type compare 0x3b1250
and the string routines (`lp:116–168`). The reference is `ref_drop`
(`lp:171–196`), written from the instructions at 0x10f2c8–0x110718.

**Observed / Executed**, in order:

1. Creature flag `+0xa8 & 0x100000000` set: no drop at all (0x10f33c–0x10f358).
2. Property `noloot` (key at 0x52ffd8) with a **nonzero integer value**: no drop,
   unless PvP mode B (0x4f7120) is set (0x10f360–0x10f37c). The property is read
   with `obj_getPropInt`, so `noloot=0` still drops (`lp:222`).
3. Eleven exact-type tests (the getter's type compared by 0x3b1250, which
   matches on pointer or name). A matching class makes its own calls and
   **returns**: no tint and no trailing ordinary call (`lp:239–289`). Two are gated: class 5 (getter
   0x3cc568) only when `+0xa8` bit 0 is set (0x10fb7c), and class 6 (0x3ca4ac)
   only when the word at `+0x3d8` is nonzero (0x10fcfc). Ungated, both fall
   through to the generic path, tint included (Executed).
4. Generic path. Rank comes from `creature_bossRank`: 0 unless object flag
   `+0xc & 0x20`. Then 2 if the type name at `+0x34` is on its list (0x10d964
   onward, plus three level-name conditions, Observed only). Otherwise
   `+0xa8 & 1` (the MiniBoss flag).
   - Rank 2 makes four calls before the per-player loop: the caller's six
     numbers with its filter, then `(4, 1, 6, 2)`, then `(5, 1, 7, 2)`. These
     are gold scale, gold chance, quality row and item chance, with the caller's
     z offset and throw speed. Then, for each joined player, one own draw and
     `(0, 0, 8.5, 2)`, with the preset forced when the draw is below 0x8000
     (one half).
   - Rank 1 makes two calls, `(4, 1, 3, 1.5)` and `(5, 1, 5, 1.5)`. Then, per
     player, `(0, 0, 7, 1.5)`, with the preset forced when the draw is below
     0x4000 (one quarter).
   - Tint byte `+0xa0` nonzero: gold scale ×3 and quality row ×4, applied only
     to the trailing ordinary call (0x1106bc–0x1106dc).
   - Trailing ordinary call (caller's numbers and filter, force 0): only when
     `+0xa8` bit 0 is clear (0x1106e0).

**Executed consequences:** a rank-2 boss that is not flagged MiniBoss gets its
extras **and** the ordinary drop: 5, 6 or 8 calls for 1, 2 or 4 players. A
MiniBoss gets 2 + players calls and no ordinary drop. A MiniBoss-flagged object
without `+0xc & 0x20` drops **nothing**, because its rank is 0 and the ordinary
call is gated off (`lp:213`, `a8=1 c=0`). The meaning of `+0xc & 0x20` and
`+0x3d8` is **Unknown**. **Inferred:** `+0xc & 0x20` is set by creature
construction.

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

**Executed** (`lp:292–372`). `level_monsterLevelTimes0_4` 0x1ebf20 =
`L × 0.4`, and `level_monsterLevelTimesDifficulty` 0x1ebf70 = `L × (8, 9, 10,
11, 12)` for difficulty 1…5. In PvP mode B, L is replaced by `max(1, L − 4)` in
both. These equal `ref_items.Game` on 60 states (L 1…60, difficulty 1…5, PvP B
0/1). The real 0x100d54, with `loot_spawnGold` recorded, the pool refusing and
every non-roll service auto-stubbed, matched `ref_items.loot_generate_drops`
gold amounts on 288 runs per seed (players 1/2/4, L 1/10/22/40, difficulty
1/5, PvP A 0/1).

- **Gold does not scale with difficulty.** The same seed gave identical gold at
  difficulty 1 and 5. Difficulty enters only the equipment budget and chests
  (`levelFactorDiff`).
- PvP mode A produced no gold call.

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
(`docs/loot-drop.md` lines 53–56; `items.md` lines 565–567). It has callers at
0x10bf54 (inside `Creature_onDeath` 0x10bf08), 0x147838, 0x1478b0 and 0x26d648
(Observed `jal` census).

## 2. From drop to ground object

| Object | Made by | Constructor | Notes |
|---|---|---|---|
| Flying item (PhProp, 0x248) | the four `loot_generateDrops` sites, named drops, chests | `PhProp_ctor` 0x155a0c, flags 0x441 | rigid body; interactable while flying (`loot-drop.md` §§1–2, lines 24–123) |
| Resting item (ItemProp, 0x190) | a flying item that settles (0x156c4c) | `ItemProp_ctor3` 0x1592bc, supplied matrix | no run list, no expiry (`loot-drop.md` lines 108–123) |
| Thrown-down item (ItemProp, 0x190) | inventory drop, script gifts that do not fit | `ItemProp_ctor2` 0x1590ec, Prop flags 0 | `Prop_run`, not the rigid body (`loot-drop.md` lines 131–140) |
| Gold (0xc0) | `loot_spawnGold` 0x100974, AutoContainer | `Gold_ctor2` 0x157668 | radius 24 / height 72, 41-frame countdown (`loot-drop.md` lines 241–275) |

### 2.1 `ItemProp_ctor2` 0x1590ec: every caller

**Executed** (static census, `lp:390–419`). There are seven `jal` sites, each a
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
(`lp:512–606`). With a real pool block, an overweight gift calls
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
once. No button is involved, and Gold is the only walk-over loot.
**Inferred:** the LifeTap orb (`docs/spec/skills-35-68.md` lines 6901–6939) is a
skill reward, not loot.

### 3.2 Items: use button

**Observed / Executed** (`loot-drop.md` lines 219–240; `pickups.md` lines
99–137). `Player_interact` 0x1b2640 queries x/y ±48 and z…z+60 and picks the
nearest object with bit `0x100000`. On the use edge, PhProp slot 14 0x155020
or ItemProp slot 14 0x159b38 calls `itemprop_tryPickup` 0x154dbc. Flag-39 items
try every player.

**Executed end to end** (`lp:578–606`): the ground ItemProp built by the replayed
ctor2 is refused at limit 0 and stays. At `limit == weight` it is taken: it is
in the bag through the real `inventory_giveItem` and destroyed once. Recorded
stubs on that path are 0x17365c, `player_recalcStats` 0x1b6458,
`player_countPotions` 0x1ba5f8, `script_runByName` 0x1ed694 and a sound at
0x214230. On refusal the only stub is 0x1b7ba8. `PICKUP_REAL` (`lp:72`) lists
what ran.

### 3.3 `itemprop_tryPickup` against `givePlayerItem`

Both paths insert through the real `inventory_giveItem` 0x1c1868, on the same
definition and bag states. Load recalculation is stubbed so that the
constructed load stays fixed (`lp:609–675`).

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
- **AutoChest** (`AutoChest_dropLoot` 0x23ba3c, Executed `lp:678–723`): with no
  placed properties and `+0xec == 0` it makes three generic rolls,
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

- The three name-list exceptions inside `creature_bossRank` (Observed, not
  executed). Which retail creatures have `+0xc & 0x20`, a tint byte, or
  `+0x3d8` set.
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

Both seeds: `PASS loot-and-pickups seed N: 74 checks, 0 failed, 415 cases`.
Logs are in ignored `local/loot-and-pickups/seed-{20973,7}.log`, with the
`LOCK` class rows and the gold `TABLE` lines. Regression runs after the final
edit: `difftest_loot_drop.py` 1,172/1,172 and `difftest_pickups.py` 17/17 on
both seeds, and `unittest discover -s tools -p 'test_*.py'` 652 tests OK. No
existing reference API, vector or difftest was changed.
