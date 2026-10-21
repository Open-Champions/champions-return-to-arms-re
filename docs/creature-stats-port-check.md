# Creature statistics port check (2026-10-21)

RTA US v2.00. The existing reference models in `tools/ref_combat.py`,
`tools/ref_objects.py`, `tools/ref_arena_monsters.py`, and `tools/ref_items.py`
were compared again with the original function bodies in `tools/ee_emu.py`.
The executable stayed outside this worktree. The checks used the interpreter's
constructed state and its documented call-outs, not live gameplay.

| Body or family | Differential test | Seeds | Result |
|---|---|---|---|
| `Creature_setStats` 0x10a620 and level scale | `difftest_combat.py --quick -k monster` | 20973, 7 | zero mismatches; hp, max hp, armour, damage, attack, experience and own seed compared bit for bit |
| `Player1_ctor` 0x158928 and `world_findFreeSpot` 0x14acf8 | `difftest_objects.py --quick -k marker` | 20973, 7 | zero mismatches; spawn slots, marker rank, shared seed |
| `Horsemen_ctor` 0x271c70 and lifecycle | `difftest_arena_monsters.py --quick -k knight0` | 20973, 7 | zero mismatches in calls, stores and seed |
| `Skelight_ctor` 0x2a8770 and lifecycle | `difftest_arena_monsters.py --quick -k skel` | 20973, 7 | zero mismatches in calls, stores and seed |
| `Zek_ctor` 0x2c1f94 and lifecycle | `difftest_arena_monsters.py --quick -k zek` | 20973, 7 | zero mismatches in calls, stores and seed |
| `item_loadResources` 0x108434 seed side | `difftest_items.py --quick --jobs 2 -k load` | 20973, 7 | zero mismatches; three start seeds per run, 223 draws each |
| `balance_hashName` 0x223914 and `balance_lookup` 0x223a4c | `difftest_balance_lookup.py --cases 300` | 20973, 7 | zero mismatches on authored rows, including duplicate hashes, absent hashes and negative s16 encodings |

**Correction to `docs/data-tables.md` section 3.1:** the five percentage
halfwords are read as **unsigned** by `balance_lookup`, although the table was
described as s16. A synthetic row with 0xff80 yields a large positive factor.
The model initially used signed halfwords and the differential test caught it.
The original also multiplies the converted integer by the single-precision
0.01 constant, so a stored 100 produces 0x3f7fffff, not 1.0.

The arena family filters run constructor calls during their setup and later
lifecycle calls. The scope is the individual executed bodies with the listed
call-outs. It does not establish complete level-load or retail play behavior.
