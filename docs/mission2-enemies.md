# Mission 2 hostile construction and bounded combat contracts

US `SLUS-20973` v2.00. **Observed** addresses below are original executable
entry points or class-definition addresses. **Executed** statements refer to
`tools/difftest_mission2_enemies.py` with seeds 20973 and 7, against isolated
`tools/ee_emu.py` state. The reference values are in
`tools/ref_mission2_enemies.py`. No original level was run by these tests.

## Placement order and constructor chain

| Class | Placements (`innovat1`, `inmine1`, `inmine2`, `innovat2`) | Factory bytes | Constructor / run / setState | Definition and requested archive |
|---|---:|---:|---|---|
| `clockworkcutter` | 23, 23, 20, 0 = **66** | `0x500` | `0x24e124` / `0x24e758` / `0x24f90c` | `0x4ff260`, `clokwork.lmp` |
| `clockworkhammer` | 29, 23, 14, 0 = **66** | `0x500` | `0x24e124` / `0x24e758` / `0x24f90c` | `0x4ff260`, `clokwork.lmp` |
| `Droid` | 0, 30, 0, 0 = **30** | `0x3d0` | `0x27b840` / `0x27ba78` / `0x27c0a0` | `0x500a88`, `droid.lmp` |
| `IronGuardian` | 0, 0, 0, 1 = **1** | `0x3e8` | `0x27a00c` / `0x27a390` / `0x27b550` | `0x500960`, `iron.lmp` |

**Executed:** the factory at `0x159c94` selects those allocation sizes and
constructors. Each constructor calls `Creature_ctor` (`0x109d68`) with
placeholder 10 HP and its definition; that calls `GameObject_ctor`
(`0x14cb10`), `balance_lookup` (`0x223a4c`) and
`Creature_setStats` (`0x10a620`). The test checks the calls, definition
pointers, event entry IDs and ordered resource requests. All resource lookup
returns are null in the harness, so the resulting handles and loaded models
are **Unknown**. `IronGuardian_ctor` additionally requests `droid.lmp`
through `lump_load` (`0x173558`); what that service loads is **Unknown**.

**Executed:** the reference difftest derives every ordered request name from
the owner executable at those definition addresses, compares the constructor
calls to that list and verifies each named member of the matching archive.
It can write the complete 26/10/34-name handoff to an ignored local file with
`--resource-manifest local/mission2_enemy_resource_names.txt`; exact names
remain outside tracked research files under the mission-2 audit boundary.

## Layout and balance

**Executed:** the zero-result constructor harness asserts these class-owned
fields. All four vtables select the base `Creature_takeDamage` at `0x116638`.
An isolated call reduces 100 HP by 25, writes the damage amount at `+0xc8`
and records kind 8 at `+0x2dc`; no actual attack or death transition follows
from that probe.

| Class | Vtable | Distinct fields in the checked fixture | `monsters.bal` row offset | Balance: HP, armour, damage, attack, experience (%) |
|---|---|---|---:|---|
| Cutter | `0x514300` | `+0x3c8` byte 0, `+0x1c` radius 22, `+0xb0` turn 0.6, `+0xdc` scale 0.9, `+0x50` holder at `this+0x3d0` | `0xe6` | 100, 200, 110, 100, 129 |
| Hammer | `0x514300` | `+0x3c8` byte 1, radius 28, turn 0.6, same holder | `0xda` | 120, 250, 139, 100, 150 |
| Droid | `0x515da8` | radius 15, turn 1.4, `+0x3cc` self-destruct deadline 3600 at frame 0 | `0x872` | 60, 100, 350, 100, 100 |
| IronGuardian | `0x515c60` | radius 35, turn 0.3, `+0x3c0` home range 3000, `+0x3c4` activity range 3000, `+0x3d4` spawn count 0 | `0x866` | 1800, 550, 400, 500, 1800 |

The percentages are **Observed** `monsters.bal` rows; `balance_lookup`
returns their signed factors on both seeds. The test does not supply a loaded
level, difficulty or player roster to establish final HP, defence, damage,
attack or experience. Those final values are **Unknown**.

## Tick, attack and death boundaries

**Executed:** 16 fresh-object synthetic active ticks (states 0, 3, 6 and
`0x14` per class) compare the ordered external call sequence to the reference
model. The head reaches `Creature_processDamage` (`0x110d30`),
`Creature_run` (`0x112948`) and `Creature_updateActive` (`0x10c0f0`).
Animation, holder, AI movement and effect services return stub results. A
synthetic target with state 6 asserts cutter `Creature_hitTargetInArc`
(`0x119938`, flags `0x40008`), hammer the same call (flags 1), and
IronGuardian `Creature_hitAllEnemiesInArc` (`0x119b58`, flags 8). These are
dispatches, not landed damage.

**Executed:** Droid's state `0x17` with animation flag `0x80` calls
`world_damageInRadius` (`0x161270`) with radii 60/144, test maximum damage
123 from `+0xd2` and type `0x40840`; it also dispatches the effect and ten
physics-prop construction calls. The damage service is stubbed, so affected
targets and actual damage are **Unknown**.

**Executed:** direct setState `0x14` routes through `Creature_filterState`
(`0x10a9c0`) and on-death slot 28 (`0x10beb8`). Both Clockwork variants
call `Clockwork_shedParts` (`0x24fd8c`) eight times in the tested fresh-object
seed state, then `Creature_dropLoot` (`0x10f2c8`). IronGuardian calls the same
drop helper. All three use the six raw float arguments for 36, 2, 1.6, 0.6,
1.4 and 0.25. Droid's setState `0x14` calls no drop helper. The actual item
roll, item instance, pickup and quest credit are **Unknown**. The authored
IronGuardian `dropitem=coppersprocket` property is asserted by
`tools/difftest_mission2.py`; whether a live boss death grants it is
**Unknown**.

Unexecuted states, loaded-resource behavior, player damage application,
IronGuardian's Droid spawn budget in a real level, save/load, and the boss
portal remain **Unknown** here. The broader static descriptions in
`docs/monsters-2.md` sections 3 and 5 guide later bounded probes; they are
not promoted to executed findings by this test.

## Ordered native port gates by class

**Inferred:** this implementation order follows the observed placement counts
and class dependencies. It is a port plan, not an executed native result.

1. **Cutter (66):** preserve `clokwork.lmp` order, base stats and the
   `+0x3c8 = 0` layout; implement holder and event clips, targeting, melee
   flags, charge missile windows, damage, part shedding and loot. Compare
   native ticks and attacks to original calls with loaded resources.
2. **Hammer (66):** use the same constructor/definition with `+0x3c8 = 1`;
   keep radius, attacks, steam draws, death-clip explosion and loot distinct.
   Check own-generator draws and effects before claiming parity.
3. **Droid (30):** preserve the 3600-clock expiry, fuse/explosion state,
   radius damage, death props and no class drop. Check original versus native
   target selection, timing and actual victim damage.
4. **IronGuardian (1):** load both requested archives, implement melee,
   missile/junk dispatch, four live Droid handles and fifty total budget,
   then death loot and the authored `coppersprocket` property. Compare the
   mixed clock/frame spawn timing, real boss death and portal gate in a
   loaded `innovat2` scene.

These class gates follow the placement counts; level-object and script gates
remain in `docs/mission2.md`. A function difftest does not establish a native
port or playable mission.

## Verification, 2026-10-23

All commands ran serially with `PYTHONDONTWRITEBYTECODE=1`:

```sh
python3 tools/difftest_mission2_enemies.py local/SLUS_209.73 local --seed 20973 --resource-manifest local/mission2_enemy_resource_names.txt
python3 tools/difftest_mission2_enemies.py local/SLUS_209.73 local --seed 7
python3 tools/difftest_mission2.py local/SLUS_209.73 local --seed 20973
python3 tools/difftest_mission2.py local/SLUS_209.73 local --seed 7
python3 tools/difftest_objects.py local/SLUS_209.73 -k load --seed 20973
python3 tools/difftest_objects.py local/SLUS_209.73 -k load --seed 7
python3 -m unittest discover -s tools -p 'test_*.py'
```

Both hostile seeds passed 163 placements, 96 ordered constructor requests,
38 event setups, four balance rows, 16 synthetic ticks/162 external calls,
three targeted hit dispatches, one Droid explosion dispatch, four death
routes and one inherited damage probe. Both mission seeds passed 699 records,
22,156 consumed loader bytes, 660 factory selections, 96 requests, six direct
probes and six addressed exits. Object loading passed 5/5 properties on each
seed; the full Python unit suite passed 652/652. The serial run log and
resource-name manifest are ignored under `local/`.
