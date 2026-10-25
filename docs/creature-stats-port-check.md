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
# Weapon holder slot 1

The two executed bodies at 0x11afb0 and 0x11bc18 update the embedded holder
hand bytes. The base holder accepts hand 1: it stores the low entry byte at
+0x08 and sets/clears flag bit 0 at +0x04 according to whether the entry is
nonzero. The shield holder additionally accepts hand 2, storing at +0x98 and
setting/clearing flag bit 1. Unsupported hands return 1 without writes. The
return on a supported hand is the new flag byte. `tools/difftest_holder_attach.py`
compared each body with this reference model on 300 authored cases for each of
seeds 20973 and 7, with zero differences.

# Nightmare construction seam

`tools/difftest_nightmare_ctor.py` executes `Nightmare_ctor` at 0x270968 and
its direct state-zero body at 0x27155c in `ee_emu.py`. It delegates the already
researched Creature base constructor, animation, object random, event setup,
run registration, and Creature_init bodies as recorded call-outs. The authored
reference model compares the constructor's final bytes and the ordered callees
on 100 fresh-pool cases for each seed 20973 and 7; both sets had zero
differences. This establishes the bounded constructor stores and call order,
not the mount's later tick, animation, collision, or resource behavior.
