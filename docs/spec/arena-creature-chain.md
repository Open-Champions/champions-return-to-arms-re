# Arena creature construction chain, executed whole

US `SLUS_209.73` v2.00, 2026-10-21. Reference `tools/ref_arena_creature_chain.py`,
difftest `tools/difftest_arena_creature_chain.py`, unit tests
`tools/test_ref_arena_creature_chain.py`. Evidence words as in `CONTRIBUTING.md`.

Round 5 left the recipe classes as constructor fixtures (`arena-match-probe.md`). This
document covers the whole chain under one arena `world_createObject` call for arena
indices 3 (Goblin), 1 (Mummy) and 0 (Scorpion). Those are the classes of the first
recipe's waves 0–2.

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
element descriptor `(id, a, a + v, 0)` takes the second. On seed 7, 2 of the 18 test
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

| Seed | balance_lookup | Creature_init | Chain, empty table | Chain, disc table | Two-draw constructions |
|---:|---:|---:|---:|---:|---:|
| 20973 | 360 | 448 | 1,080 | 1,080 | 0 |
| 7 | 360 | 438 | 1,094 | 1,094 | 2 |

Each chain run makes 18 constructions: 3 classes × waves 0–2 (the monster level
`arena_startWave` stores), each built twice in one state. The comparisons cover the
shared and own seeds, the own-draw count, the ordered service calls, pool size,
position, home, facing, stats (hit points, maximum, armour, damage range, attack,
experience value), class fields and `Creature_init`'s height. With `--disc`, the
`monsters.bal` entry of the user's `balance.lmp` is copied into the emulator at run
time, where `balance_load` would put it. All 18 type names were found there. No values
are recorded here. There were no mismatches.

## 6. Limits

- `res_find` answers one authored part. The definitions' real models and clips are not
  loaded, so the hide mask, the clips the constructors push and `Creature_init`'s
  bounds are service answers.
- The `dead`, `change`, weapon and `initScript` branches of `Creature_init` were run
  only on authored objects. The arena list reaches none of them.
- Other Goblin roles, other Mummy variants and Scorpion variants are outside the plain
  arena types.
