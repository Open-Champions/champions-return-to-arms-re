# Arena creature construction chain, executed whole

US `SLUS_209.73` v2.00, 2026-10-21. Reference `tools/ref_arena_creature_chain.py`,
difftest `tools/difftest_arena_creature_chain.py`, unit tests
`tools/test_ref_arena_creature_chain.py`. Evidence words as in `CONTRIBUTING.md`.

Round 5 left the recipe classes as constructor fixtures (`arena-match-probe.md`). This
document covers the whole chain under one arena `world_createObject` call for arena
indices 3 (Goblin), 1 (Mummy) and 0 (Scorpion), which are the classes of the first
recipe's waves 0–2. It also covers the two most common later indices, 4 (Orc2) and 25
(SnoBadge). Section 7 adds the free-spot search every spawn uses, and the Life Tap orb a
kill can drop. The probe composes them in `arena-match-probe.md` (round 6 section).

## 1. What executes

`world_createObject` → `world_objectFactory` → class constructor → `Creature_ctor` →
`GameObject_ctor`, `creature_bossRank`, `balance_lookup`, `balance_hashName`,
`Creature_setStats`, the class body, `Mummy_setState` (called by the Mummy constructor),
`Creature_filterState` and its helpers, `obj_runEvery60`, `creature_setDefEntryParams`,
holder slot 1, the property queries, the C library and `Creature_init`. The Mummy's rare
branch also runs `Weapon1_slot4`/`slot7`, `creature_buildElementDamage` and the skill's
slot 11. The full list is `REAL` in the reference.

Services, which stay call boundaries:

- `pool_new`: a zero-filled block.
- `res_find`: one authored part for every entry.
- `handle_link` and `handle_clear`.
- `model_buildHideMask`, `anim_clear`, `anim_push` and `anim_start`.
- `model_getBounds`: authored z bounds.

The property list is arena_init's list. `arena_init` 0x304c4c stores `0x8e7230 =
{0x8e7238, 0}` and copies one byte from 0x551e80 into 0x8e7238 (0x304e58–0x304e84,
**Observed**). In the image that byte is the empty string. The 101 Skill objects are
built first by the game's start-up initialiser (0x16ac74, 0x1ebca0, as in
`tools/difftest_skills_a.py`); it moves the shared seed, so the seed is set afterwards.

## 2. `balance_lookup` 0x223a4c (new, Executed)

- All five outputs are 1.0 first. A null name returns 0.
- `balance_hashName(name, strlen(name))`, as in `docs/data-tables.md`.
- The records are scanned for the first equal hash. They sit at the word 0x4fb5c4, and
  0x4fb5c8 holds the count. `balance_load` 0x223998 stores both: the pointer is the entry
  data + 2 and the count is the first halfword (0x223a28/0x223a2c, **Observed**).
- On a match each factor is `float(u16 value) × 0x3c23d70a` (0.01). The loads are
  **unsigned** (`lhu`); `data-tables.md` calls them s16. The function returns 1. No draw.

Checked on 60 authored tables per seed: duplicate hashes, values 0x8000–0xffff, counts
0 and −1, and a null name.

## 3. `Creature_init` 0x10a230 (new, Executed)

Read from 0x10a230–0x10a61b:

1. With creature flag bit 0 (MiniBoss), virtual slot 18 is called.
2. `model = slot 16` (`*(def + 0xc)`). With a model: `model_getBounds(model, −1, six int
   outputs)`. Then `+0x20 = max(float(maxZ − minZ), 84.0)` (0x42a80000), and byte
   `+0x29 = trunc(+0x20) + 1`.
3. If `obj_getPropStr("dead")` is present: creature flag bit 32 is set, then slot 27
   `(c, 0x14)` and `anim_snapTopToEnd(c + 0x114)`.
4. `mask` is the OR of `1 << k` over each `change<k>` that is present (k 0–31, built with
   `sprintf`). A non-zero mask sets `+0xe8 = mask` and
   `+0x220 = model_buildHideMask(model, mask)`.
5. For `FireWeapons`, `FireBurstWeapons`, `ColdWeapons`, `PoisonWeapons`,
   `ShockWeapons`, `DiseaseWeapons` and `NoMagicWeapons`: when
   `obj_getPropInt` (`libc_atoi`) is non-zero and a holder exists, holder slots 2–8 are
   called with `(holder, 0)`; slot 8 also gets a third argument, 0.
6. When the cutscene byte 0x44fcd0 is clear and `initScript` is present: the script runs
   by name with `g_scriptSelectedObj` 0x4039f8 = c around the call.

The function's own code makes no draw. It was checked on 80 authored objects per seed,
covering every branch. With the arena's empty list, only step 2 has an effect.

## 4. The chain contract

| Step | Shared draws | Own draws |
|---|---:|---:|
| Goblin's pre-base draw on the zeroed `+0x44` | 0 | 1 |
| `GameObject_ctor`: `+0x44 = new seed >> 16` | **1** | 0 |
| `Creature_setStats` hit-point roll (balance factors, `ref_combat.monster_stats`) | 0 | 1 |
| Goblin: role draws (`ref_arena_match_classes`) | 0 | 2–3 |
| Mummy: mask, rare roll, `Mummy_setState(0)` (`+0xf4 = d % 120`) | 0 | 3 |
| Mummy rare roll `float(d) × 2⁻¹⁶ < 0x3dcccccc` (0x2986f0–0x29871c): one more own draw picks modifier `(m & 1) + 1` | 0 | +1 |
| ... modifier 1 → holder slot 7, element kind 5; modifier 2 → slot 4, kind 2 (hand 1, after the hide mask, 0x298938–0x2989b0) | **+1** (`creature_buildElementDamage`) | 0 |
| Scorpion: scale and skin draws (`ref_monsters_1`) | 0 | 2 |
| `Creature_init` (empty list) | 0 | 0 |

So a plain arena creature costs **one** shared draw. A rare Mummy costs **two**: its
element descriptor `(id, a, a + v, 0)` takes the second. On seed 7, 2 of the 30 test
constructions took it; on seed 20973, none did. The
Goblin also resolves its family entry block `0x500448 + 0x80 × family` (`+0x490`; 0 for
the plain type) under the same generation test as the class definition
(0x26a774–0x26a840, **Observed**). The second construction of a class therefore asks
`res_find` for neither block.

## 5. Results

```text
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arena_creature_chain.py local/SLUS_209.73 --seed 20973 --disc <disc>/BG/DATA
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_arena_creature_chain.py local/SLUS_209.73 --seed 7 --disc <disc>/BG/DATA
```

| Seed | balance_lookup | Creature_init | world_findFreeSpot | OniBall_ctor | Goblin_onNearbyEvent | Chain, empty table | Chain, disc table | Two-draw constructions |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20973 | 360 | 448 | 480 | 640 | 360 | 1,854 | 1,854 | 0 |
| 7 | 360 | 438 | 480 | 640 | 360 | 1,868 | 1,868 | 2 |

Each chain run makes 30 constructions: 5 classes (indices 3, 1, 0, 4, 25) × waves 0–2
(the monster level `arena_startWave` stores), each built twice in one state. The comparisons cover the
shared and own seeds, the own-draw count, the ordered service calls, pool size,
position, home, facing, stats (hit points, maximum, armour, damage range, attack,
experience value), class fields and `Creature_init`'s height. With `--disc`, the
`monsters.bal` entry of the user's `balance.lmp` is copied into the emulator at run
time, where `balance_load` would put it. All 30 type names were found there. No values
are recorded here. There were no mismatches.

## 6. Orc2 and SnoBadge (indices 4 and 25)

- **Orc2.** The factory passes model-set flag 1 for `Orc2` names: class block 0x501df8
  and weapon list 0x502090 (`docs/monsters-2.md`, Orc). The plain type name `orc2`
  matches no variant prefix, so it is the recruit (variant 0). Own draws, read at
  0x2a09c8 and 0x2a0d50–0x2a0e74, `Orc_pickHandParts` 0x2a14f8 and 0x2a11cc:
  1. the pre-base `rand % 14 + 4`, then the hit-point roll;
  2. `r`, which picks the model-variant bit (`r & 1`: 0x1 if `r & 2` else 0x2;
     otherwise 0x100 if `r & 2`, 0x200 if `r & 4`, else 0x400);
  3. one more draw when `r & 0x32` (even: a shield in hand 2);
  4. `Orc_pickHandParts`' one draw (hand-1 part 1, 7 or 5);
  5. the idle clip's `% 3`.

  The weapon list block is resolved under the generation test. One shared draw.
  Compared: own seed and draw count, stats, `+0xe8`, speed 80, turn rate 1.2, radius 18,
  `+0x478`/`+0x47c`/`+0x480`. The creature flags set by `Orc_applyVariantFlags` are not
  compared.
- **SnoBadge.** `Badger_ctor` variant 1 (`ref_monsters_1`, the exact factory name). No
  own draw beyond the hit-point roll; one shared draw.

## 7. `world_findFreeSpot` 0x14acf8 and `OniBall_ctor` 0x294014 (new, Executed)

**`world_findFreeSpot(out, centre, range, radius, ok, anyHeight)`**, read from
0x14acf8–0x14b167:

- **Sampling.** Each sample takes three shared draws (the R5900 three-operand `mult`
  makes the generator step). Each coordinate is `(f(d) × 2⁻¹⁶ doubled) − 1.0`. A sample
  repeats while `1.0 < (px² + py²) + pz²`. The seed is stored once per try.
- **Candidate.** `(cx + px × range, cy + py × range)` at the centre's z.
  `terrain_testFlag1` must answer 0.0. Then `height − cz < 6.0` (0x40c00000), unless
  `anyHeight` is set.
- **Box.** The spot becomes `(x, y, height)`, and the box is `x ∓ r`, `y ∓ r`,
  `height ∓ 100000`. An object without object flag 1 blocks when
  `dx² + dy² ≤ float(radius²) + its radius²`.
- **Result.** At most 50 attempts; `ok` is 1 on success and 0 after 50 failed
  attempts. The reference returns the number of attempts (1–50 on success),
  while the original's loop counter is zero-based (0–49 on success). The out spot
  is the last accepted candidate, or the centre.

It was checked on 120 authored cases per seed: open, walled, stepped, crowded and fully
blocked ground, ranges 0–96 and radii 0–30. In the probe it is checked on every call
against the real box query's answers.

**`OniBall_ctor(block, position, facing (unused), creature, 0)`** is the Life Tap orb of
`creature-tick.md` §4 step 9. Read from 0x294014–0x2941e3:

- `Projectile_ctor` makes one shared draw. Then vtable 0x50e878, and five own draws:
  - facing `+0x38`;
  - a roll `< 0x7333` choosing byte `+0x74` and which of creature `+0x38c`/`+0x394`
    gets 30;
  - offsets `(x − 50) + d % 100`, `(y − 50) + d % 100` and `(z + 36) + d % 2000 + 36`.
- `+0x54 = frame + 600`, `+0x58 = trunc(max hp × 0x3d4ccccc)`, creature `+0xf0 = frame`,
  then `obj_runEveryFrame`.

It was checked on 40 authored creatures per seed.

**`Goblin_onNearbyEvent(goblin, event, position, source)`** is Goblin virtual slot 12,
which `world_notifyObjectsNear` calls on each kill. Read from 0x26c9f4–0x26cb43:

- **Event 0.** The source's type info must equal `Goblin_typeinfo` 0x3c44e8's
  (`rtti_typeInfoEquals`), and the state (u16) must be below 2. Then slot 27
  `(goblin, 2)` is called and the position is stored at `+0x104…+0x10c`.
- **Event 2.** It needs `Goblin_hasShieldUp` 0x26d7e4 (holder slot 15, hand 2, answers
  part 7, then slot 14, hand 2, is non-zero), a source, and state 3 or 5. Then
  `b = atan2_16(source − goblin)`, and when `u32(b − s16 facing + 0x270f) < 0x4e1f`, slot
  27 `(goblin, 0x11)` is called.
- Nothing else happens, and there is no draw.

It was checked on 120 authored Goblins per seed, against Goblin, Mummy and Player
sources. The real type-info getters made the decisions; the holder answers and slot 27
were recording stubs. Seed 20973 issued 21 set-state-2 and 25 set-state-`0x11` requests;
seed 7 issued 22 and 22.

## 8. Limits

- `res_find` answers one authored part. The definitions' real models and clips are not
  loaded, so the hide mask, the clips the constructors push and `Creature_init`'s
  bounds are service answers.
- The `dead`, `change`, weapon and `initScript` branches of `Creature_init` were run
  only on authored objects. The arena list reaches none of them.
- Other Goblin roles, other Mummy variants and Scorpion variants are outside the plain
  arena types.
