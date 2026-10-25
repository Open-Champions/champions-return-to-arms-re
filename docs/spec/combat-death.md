# The Skeleton and AntQueen death path: Skeleton_shatter, the boss test, skill ranks, experience, the clip search, loot

US `SLUS_209.73` v2.00. Prose of `tools/ref_combat_death.py`. The comparison is
`tools/difftest_combat_death.py`; the synthetic tests are `tools/test_ref_combat_death.py`.
Written 2026-10-21 for item 7 of `docs/spec/full-placement.md` §4: the bodies the probe met
when a Skeleton or an AntQueen dies. The weapon holder's slot 11, the dropped weapon, is in
`docs/spec/weapon-holder.md`.

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
and the model agreed on the calls to everything outside the models (in order, with
arguments; stack arguments and vectors read at the call), every byte stored outside the
stack, the shared seed `0x404464` with its draw count, and the result. **Observed**: read
at the address. Nothing here ran on a console, in PCSX2 or on the live rig.

## 1. How it was run

`tools/difftest_weapon_holder.py`'s MiniRig runs each body for real (the C library too, so
the comparisons use the original `libc_strcasecmp` `0x3b81a0`) and calls it directly on
made-up state:

- creatures with every show-mask bit of the shatter groups;
- the game's own boss-name strings (read from your executable at run time), their copies in
  upper, lower and mixed case, near misses (a letter more, a letter less) and other names;
- player records at levels 0–80, with experience around the thresholds of the game's own
  table `0x41b558`, and every hit-point sign (−0.0 included);
- skill lists of 0–30 pairs, with ids searched for that are present and absent, and
  negative ids and ranks;
- animation states with counts 0–8, `0x80` and `0xff`.

Callbacks (recording stubs answered by a scripted world):

- `pool_new` (a block in eight cases of ten);
- `PhProp_ctor2` `0x1556c0`, with its three stack arguments read at the call;
- `obj_getPropStr`, `player_recalcStats` `0x1b6458`, `net_isLocalSlot` `0x13e150`,
  `res_find`, `sound_playOnObject`, `text_lookup`, `hud_showMessage`.

`loot_generateDrops` `0x100d54` was already executed by `tools/difftest_items.py` against
`ref_items.loot_generate_drops` (`docs/spec/items.md` §8). The probe did not count it
because its module keeps no address table. `difftest_combat_death.py` runs that difftest's
own `loot` job again (library string routines replaced; a quarter of the calls with seeds
searched so that the rare rolls succeed), records every pc of the body, and reports the
coverage below.

Commands:

    python3 -u tools/difftest_combat_death.py --seed 20973 -v
    python3 -u tools/difftest_combat_death.py --seed 7 -v
    python3 -m unittest tools.test_ref_combat_death

| | Seed 20973 | Seed 7 |
|---|---|---|
| `Skeleton_shatter` | 1,570 | 1,585 |
| `creature_bossRank` | 1,980 | 2,057 |
| `player_getSkillRank` / `Player_slot39` | 1,166 / 481 | 1,080 / 488 |
| `player_giveExp` | 1,578 | 1,616 |
| `anim_findTrack` | 1,225 | 1,174 |
| Shared draws in these bodies | 0 | 0 |
| `loot_generateDrops` (difftest_items' loot job) | 300 calls, 59,516 draws; 133 gold, 35 consumable, 11 reagent, 5 figurine, 88 equipment drops; 38 early returns, 6 refused blocks | 300 calls, 46,082 draws; 143, 46, 13, 7, 72; 35, 3 |
| Mismatches | 0 | 0 |

Checks (each change to the model was detected, on 800 calls of seed 20973):

- the first skill-point band ending at 7 instead of 6: 19 mismatching calls;
- group 8 without its last mask: 26.

## 2. Coverage (instructions executed of the body)

| Function | Address | Executed | Not executed |
|---|---|---|---|
| `Skeleton_shatter` | `0x2a7ef0` | 155 of 155 | |
| `creature_bossRank` | `0x10d940` | 165 of 166 | the padding `nop` `0x10dbb4` |
| `player_getSkillRank` | `0x1bf330` | 25 of 26 | the padding `nop` `0x1bf384` |
| `Player_slot39` | `0x3c3b40` | 6 of 6 | |
| `player_giveExp` | `0x1d3150` | 101 of 101 | |
| `anim_findTrack` | `0x170d88` | 26 of 28 | the padding `nop`s `0x170da4`, `0x170db4` |
| `loot_generateDrops` | `0x100d54` | 782 of 785 | `0x1017b0`–`0x1017b8`: the factor 7.0 for a preset item when the budget is not above 3.0 (`ref_items` has it; 600 calls did not reach it) |

Both seeds give the same coverage.

## 3. Skeleton_shatter `0x2a7ef0` (skeleton c, group)

*Executed.* Its only caller is `Skeleton_setState` 0x14 with group 8.

1. The first word of the static list `0x8e44c0` is zeroed (`0x2a7f24`, in a delay slot,
   for every group).
2. Groups 1–8 go through the jump table `0x54bfd0`. The group's 64-bit masks are stored
   into the list, followed by a zero word:

| Group | Masks, in list order | Stored at |
|---|---|---|
| 1 | `0xfe000000000000`, `0xc0` | `0x2a7f40` |
| 2 | `0x80000`, `0x100000`, `0x200000`, `0x1000001000000000` | `0x2a7f60` |
| 3 | `0x10000`, `0x20000`, `0x40000`, `0x2000002000000000` | `0x2a7f80` |
| 4 | `0x2`, `0x4000`, `0x8000` | `0x2a7fb4` |
| 5 | `0x1`, `0x1000`, `0x2000` | `0x2a7fc8` |
| 6, 7, and anything outside 1–8 | none: the list is empty | |
| 8 | `0xc0`, `0x338`, `0xc04`, `0x10000`, `0x20000`, `0x80000`, `0x100000`, `0x1`, `0x2`, `0x1000`, `0x4000`, `0x40000`, `0x200000`, `0x8000`, `0x2000`, `0xfe000000000000` | `0x2a7fec` |

3. The show mask `c + 0x220` (64 bits) is read once. For each mask `m` of the list, up to
   the zero word:
   - `p = mask & m`. When `p` is non-zero, `pool_new(0x248)` is called. With a block:
     `PhProp_ctor2(block, copy of c+0x10, s16 facing c+0x38, model = word def+0xc, anim
     c+0x114, words def+0, def+8, def+0x10; 1.0)`, where `def` is `c + 0x24`. The stack
     arguments are `p` (64 bits), `0x107` (`0x2a80dc`) and 0.
   - The bits of `m` (not only `p`) are removed from the mask, whether a block came or not.
4. The mask is stored back at `c + 0x220`.

Reads: `c + 0x220`, `+0x24` (and the four definition words), `+0x10`–`+0x18`, `+0x38`.
Writes: the list `0x8e44c0` and `c + 0x220`.

Draws: none here. *Unknown*: the draws of `PhProp_ctor2`. Its body (844 bytes, not
executed) calls `GameObject_rand`, `Prop_ctorNamedLaunch`, `PhProp_initPhysics`,
`res_find` and `sound_playOnObject`. *Inferred*: a group-8 shatter of a whole skeleton
makes up to 16 props, and each draws whatever the prop constructor draws.

## 4. creature_bossRank `0x10d940` (creature c) → 0, 1 or 2

*Executed.*

- Without object flag `0x20` (`c + 0xc`), the result is 0.
- With no type name (`c + 0x34` = 0), the result is bit 0 of the creature flags `c + 0xa8`.
- Otherwise the type name is compared, without case, with each of the following. The first
  match returns 2:
  1. 14 names at `0x52fd48`, `0x52fd58`, `0x52fd68`, `0x52fd78`, `0x52fd88`, `0x52fd90`,
     `0x52fda0`, `0x52fdb0`, `0x52fdc0`, `0x52fdd0`, `0x52fde0`, `0x52fdf0`, `0x52fe00`,
     `0x52fe10`.
  2. Three name-and-property pairs. Each match asks `obj_getPropStr(c, "name" 0x52fab0, 0)`
     and compares the property with the pair's value. They are `0x52fe20` with value
     `0x52fe30`; `0x52fe20` **again**, with a second property call, and value `0x52fe38`;
     and `0x52fe40` with value `0x52fe48`.
  3. Two more names, `0x52fe50` and `0x52fe60`.
- Anything else returns bit 0 of the creature flags (MiniBoss).

No draws, no stores. The model reads the strings from the executable.

## 5. Skill ranks

**player_getSkillRank `0x1bf330` (slot, skill id) → rank.** *Executed.*

- The record is `0x4d8af0 + slot × 0x4c30`; the `mult` is at `0x1bf338`.
- It walks the (id, rank) halfword pairs at record `+0x4b08`. When the first id is −1, the
  result is 0.
- Otherwise the first pair whose id (sign-extended) equals the full register of the
  argument gives its rank, sign-extended. A negative rank is returned as negative.
- Before each next pair, an id of −1 ends the walk with 0.

**Player_slot39 `0x3c3b40` (player object, skill id).** *Executed.* It replaces `a0` with
the slot word `+0x3c8` and jumps to `player_getSkillRank` (a jump, not a call).

No draws, no stores.

## 6. player_giveExp `0x1d3150` (slot, amount)

*Executed.* `r` is the record.

1. `exp` (`+0x5c`) += amount. The sum is stored, then replaced by `table[80] − 1` when it is
   larger. The cap word `0x41b698` is read at `0x1d3188`; the compare is signed.
2. While `table[level] ≤ exp` (signed; `level` is the signed byte `+0x59`, re-read each
   time; the table is `0x41b558`):
   - skill points (`+0xe8`) += 1 when `level` < 6, 2 when < 16, 3 when < 26, 4 when < 36,
     else 5. The bounds are tested at `0x1d31cc`–`0x1d3210`, against the level before the
     increment;
   - stat points (byte `+0xec`) += 3;
   - the level byte += 1;
   - `player_recalcStats()` (its `a0` is left over and not an argument);
   - if hp (`+0xac`) > 0.0, then hp = max hp (`+0xb0`) and mana (`+0xc0`) = max mana
     (`+0xc4`). A −0.0 or negative hp is not refilled;
   - if `net_isLocalSlot(slot)`: `sound_playOnObject(res_find(0x53b1f0, 0x53b338), 0;
     1.0)`;
   - `hud_showMessage(text_lookup(0x53b348), 0x168, slot, 0)`, on every machine.

No draws.

Here `player_recalcStats` is a callback, so the refill reads the maxima as they were. In
the game it recomputes them first; `tools/difftest_combat.py` executes both together
(`docs/spec/combat.md` §6–7).

The callers (Executed, `ref_creature.process_damage`):

- `Creature_processDamage` asks `player_getSkillRank(killer, 0x3b)` for the kill orb.
- It then calls `player_giveExp` per slot, with the amount capped by `cap(level)`
  (`docs/spec/combat.md` §5).

## 7. anim_findTrack `0x170d88` (state, clip) → track

*Executed.* The result is 0 when the state or the clip is 0. Otherwise the tracks are
walked; their count is the **signed** byte `state + 4`, so a negative count means none.
The first track whose clip word `state + 8 + 32k` equals the clip gives
`state + 8 + 32k`; if none matches, the result is 0. No draws, no stores.

`AntQueen_setState` 0x14 uses it to skip the take-off clip while a flight track (`+0x3c`)
plays (`docs/spec/combat-ctors.md`).

## 8. loot_generateDrops `0x100d54`

*Executed*, `docs/spec/items.md` §8, all from the shared seed.

- Its callees executed by the same difftest are listed in `ref_combat_death.EXECUTED_ELSEWHERE`:
  `loot_spawnGold` `0x100974` (the `gold` job, with the Gold constructor `0x157668`
  answered), `item_generateFromSpecialTable` `0x104758`, `item_generateWithAffixes`
  `0x104ca4`, `item_generateFlag35Entry` `0x106214`, `item_generateFlag45Entry`
  `0x106658`, `item_generateConsumable` `0x108590`, and the level factors `0x1ebf20` and
  `0x1ebf70`.
- `item_parseDescriptor` and `item_getResourceIndex` are already in another module's table.
- The `PhProp_ctor` and `PhProp_initPhysics` it calls are `tools/ref_phprop.py`'s.

## 9. What a death runs, in order (from the callers, all Executed)

**Skeleton** (`Skeleton_setState` 0x14, `docs/spec/combat-ctors.md` §5):

1. Holder slot 11 with hand 1, then hand 2: one `PhProp` per carried part.
2. Object flags `|= 0x4002`; creature flag `0x20000000000`.
3. `Skeleton_shatter(c, 8)`.
4. Unless creature flag `0x1000000`: `Creature_dropLoot` (with `creature_bossRank` and
   `loot_generateDrops` inside).
5. `obj_delete`, slot 28.

`Creature_processDamage` also awards the experience (§6). Its order relative to the
set-state was not looked at here.

**AntQueen** (`AntQueen_setState` 0x14):

1. `Creature_dropLoot`;
2. the death clip;
3. `anim_findTrack`;
4. slot 28.

Shared draws on these paths come only from:

- `loot_generateDrops` (from 7 to several hundred per call);
- the prop constructors (`PhProp_ctor`, `PhProp_ctor2`);
- `GameObject_ctor` inside them.

## 10. Corrections and sharpenings

- `docs/spec/full-placement.md` §4 item 7 lists `creature_bossRank`, `loot_generateDrops`,
  `player_giveExp`, `player_getSkillRank` and `anim_findTrack` as unexecuted. All five had
  been executed: by `tools/difftest_combat.py`, `tools/difftest_items.py` and
  `tools/difftest_anim.py`. The probe could not see it, because those modules keep no
  address table. They are now in `ref_combat_death.EXECUTED` and were executed again here.
- `symbols/monsters2.tsv`, `Skeleton_shatter`:
  - the list holds masks for groups 1–5 and 8 (6 and 7 are empty);
  - the constructor is `PhProp_ctor2` with the part bits as a 64-bit stack argument and
    `0x107`;
  - a mask's bits are cleared even when the pool refuses a block.
- `symbols/creatures.tsv`, `creature_bossRank`:
  - the list is 14 names, 3 name-and-property pairs (the first name twice) and 2 more names;
  - "0 normal" is 0 only for a non-creature or a creature without the MiniBoss bit.
- `symbols/ui.tsv`, `player_giveExp`:
  - the HUD message is shown on every machine; only the sound is behind `net_isLocalSlot`;
  - the refill needs hp strictly above 0.0.

## 11. Not executed on this path

- `PhProp_ctor2` `0x1556c0` (844 bytes): `Skeleton_shatter`'s prop constructor.
- `model_getAttachPoint` `0x1754a0`, the drop's attach point.
- `net_isLocalSlot` `0x13e150`, `text_lookup` `0x173c84`, `hud_showMessage` `0x1d92a0`,
  `sound_playOnObject` `0x214230`: presentation and the machine's own slot.
- `player_recalcStats` `0x1b6458`: executed by `tools/difftest_combat.py`, and a callback
  here.
- The Gold constructor `0x157668`.
