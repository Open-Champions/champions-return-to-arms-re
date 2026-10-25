# `blood1` first-story-level research (SLUS-20973 US v2.00)

2026-10-23. **Status: research handoff, not a playable native level.** The
native hub mission menu requests `blood1`; the level archive has authored
enemies. The comparison below runs isolated original functions through
`tools/ee_emu.py`. It does not run the original level or build these actors in
the native client. Private archive, script, model and resource bytes remain in
ignored `local/` only.

## Record census and constructor selection

**Observed** in the private `BLOOD1.GOB` `objects.ob`: 363 records, 29 class
strings. **Asserted** by the committed `tools/difftest_blood1.py` per-class
`Counter` against the counts below. **Executed** by that test: `world_loadRecords`
0x14e808 consumed 10,632 bytes and passed all 363 classes, angles and
property lists in file order to a recording factory. The original factory
0x159c94 then selected one pool size and constructor per row, or no object,
under both seeds 20973 and 7. The 351 selected objects include 140 hostile
placements. Allocation and derived constructors were stubbed in this test.

The table gives **counts only** for authored records; it does not copy any
record, position, property payload or game bytes. Size is the factory's pool
request, followed by the constructor address. A dash means no GameObject.

| Class | Records | Size / constructor |
|---|---:|---|
| `Ambient_Light` | 1 | — |
| `Ambient_Light2` | 1 | — |
| `Barrel` | 87 | 0x84 / 0x290c24 |
| `BFfiredoor` | 1 | 0x198 / 0x23c44c (`AutoProp`) |
| `BFhappydoor` | 1 | 0x198 / 0x23c44c (`AutoProp`) |
| `Blocker` | 33 | 0x4c / 0x28f15c |
| `charAmbient_Light` | 1 | 0x4c / 0x158bcc |
| `charDirectional_Light` | 1 | 0x4c / 0x158c6c |
| `charDirectional_LightD` | 1 | 0x4c / 0x158d0c |
| `clearColor` | 1 | — (level side effect) |
| `customVars` | 1 | — (level side effect) |
| `Directional_Light` | 1 | — |
| `Directional_Light2` | 1 | — |
| `Directional_LightD` | 1 | — |
| `Directional_LightD2` | 1 | — |
| `Kobold` | 118 | 0x3d0 / 0x27f0c0 |
| `koboldshaman` | 5 | 0x3d0 / 0x27f0c0 |
| `Koboldtough` | 8 | 0x3d0 / 0x27f0c0 |
| `NPC` | 1 | 0x480 / 0x29df04 |
| `orkbox` | 18 | 0xf8 / 0x23ad18 (`AutoChest`) |
| `Player1` | 3 | 0x4c / 0x158928 (arrival marker) |
| `Portal` | 1 | 0x164 / 0x27c694 (`JumpGate`) |
| `PowderKeg` | 13 | 0x84 / 0x290c24 |
| `PushTrigger` | 2 | 0x4c / 0x1ec900 |
| `Savepoint` | 3 | 0x118 / 0x28cb90 |
| `smokeBomb` | 44 | 0x4ac / 0x2c54f8 |
| `TestLocation` | 4 | — |
| `Trigger` | 1 | 0x70 / 0x1ecdf4 |
| `WarWraith` | 9 | 0x468 / 0x2c07a8 |

`Kobold`, `Koboldtough`, `koboldshaman` and `WarWraith` account for the 140
hostile records (118 + 8 + 5 + 9). The two doors and `orkbox` reach the
property fallback, rather than a factory test on their class strings.
`clearColor` and `customVars` do have factory side effects; the test's
constructor result of zero does not mean they are irrelevant. The six plain
level-light records and four `TestLocation` records also make no object.

### Native coverage at this date

**Observed** in the hand-written rebuild's playable-integration worktree
`native/src/script_commands_objects.cpp` on branch `codex/playable-integration`:
the script host's `kPorted` contains SmallSpider, Gnaw, Mosquito, Scorpion,
Badger, Skelight, Zek and Horsemen. None of the **20 constructor selections
above** is in that table. The three `Player1` markers have a separate gated
path; the other 348 selected records lack a constructor route in this snapshot.
The native client has partial support for
related systems (mission menu, generic script commands, moving-piece
passability, and some combat functions); that is not an executed constructor
for any `blood1` class. Other codex branches/reports under the same worktree
root describe AntQueen, Skeleton and Soul fixture constructors. They also do
not cover `blood1`. WarBoar and Minotaur work is in progress for `valor`;
neither class occurs here. A current build/merge or game run could change
this source snapshot.

## Resource requests for the unported constructors

**Executed** for the two hostile class definitions: `GameObject_ctor` 0x14cb10
walked the exact resource-entry table through `res_find` 0x17365c. The test
compares all 40 `(archive, entry)` requests to `ref_blood1.py` on both seeds
and checks that the names exist in the owner-supplied LMP archives. The
resolver returns a stub null handle; this proves requests and archive
presence, not residency, parsed animation or a live creature. `Kobold`'s
three type names share class definition 0x500af0; `WarWraith` uses 0x5034f0
(`docs/monsters-2.md` Kobold and WarWraith sections).

| Class(es) | Archive and entries requested by the class definition |
|---|---|
| `Kobold`, `Koboldtough`, `koboldshaman` | `kobold.lmp`: `kobold.vif`, `kobold.tex`, `attack1.anm`–`attack5.anm`, `death1.anm`–`death4.anm`, `evade.anm`, `evade_lft.anm`, `evade_ryt.anm`, `hitreact.anm`, `hitreact2.anm`, `knockdown.anm`, `idle1.anm`, `idle2.anm`, `run.anm`, `spell1.anm`, `walk.anm` (22) |
| `WarWraith` | `wwraith.lmp`: `warwraith.vif`, `warwraith.tex`, `ataklong.anm`, `atakswd1.anm`, `atakswd2.anm`, `death.anm`, `deathtouch.anm`, `fly.anm`, `forward.anm`, `hitreaction.anm`, `idle_axcythe.anm`, `idleweap.anm`, `cythe.vif`, `cythe.tex`, `dhaxe.vif`, `dhaxe.tex`, `dhsword1.vif`, `dhsword1.tex` (18) |

For the other constructors, `docs/objects.md` and `docs/monsters-2.md` give
**Observed general constructor rules**. This report's instance-specific names
and archive-presence notes are **unverified hypotheses** except for the four
classes named in `ref_blood1.py` `DIRECT_REQUESTS`: the committed difftest
checks direct requests for Barrel and PowderKeg, and zero named direct
requests for Blocker and smokeBomb, with lower services stubbed. The remaining
rows need committed direct-constructor and archive checks before native use.

| Class(es) | Constructor-stage request or resource boundary |
|---|---|
| `Barrel` | `barrel.lmp`: `barrel.vif`, `barrel.tex` (direct requests at 0x290c24) |
| `PowderKeg` | `powderk.lmp`: `powderkeg.vif`, `powderkeg.tex` (direct requests at 0x290c24) |
| `BFfiredoor`, `BFhappydoor` | Inferred `blodanim.lmp` model, texture and state animation requests; exact instance requests and archive presence are Unknown in this committed test. |
| `orkbox` | Inferred `orkbox.lmp` model, texture and chest animation requests; exact instance requests and archive presence are Unknown here. |
| `NPC` | Inferred `natasla.lmp` model, texture and idle animation requests; exact instance requests and archive presence are Unknown here. |
| `Portal` | Authored `lump=jumpgate` is asserted, but `jumpgate.lmp` request order and archive presence are Unknown here. |
| `Savepoint` | Prior manual probe suggested `savepoint.vif` and `savepoint.tex`; no committed instance check establishes requests or archive choice. |
| `Blocker`, `smokeBomb` | Bounded direct constructors make no named `res_find` request in the committed test. Later particle/effect dependencies remain Unknown. |
| `Player1`, `PushTrigger`, `Trigger`, three `char*Light` markers | Named direct requests are Unknown pending a committed probe. |

The possible absence of `BFfiredoor` numbered animations still needs a
committed archive check; stubbed pointer services cannot establish loading.
Audio, cutscene and dialog resources are outside the `res_find` constructor
table and still matter for full play.

## Hostile constructor and combat reference (2026-10-23)

`tools/ref_blood1_enemies.py` and `tools/difftest_blood1_enemies.py` compare
isolated original functions on seeds 20973 and 7. **Executed** for one
representative of each authored hostile class string: the derived constructor,
`Creature_ctor` 0x109d68, `GameObject_ctor` 0x14cb10 and its `res_find`
0x17365c calls. The resource service returns zero; animation, model, AI and
loot services below the class method are also stubs. This is a reference for
a future port, not an instantiated or fighting level creature.

| Priority / class | Placements | Constructor chain and class layout |
|---|---:|---|
| 1 `Kobold` | 118 | 0x27f0c0 → 0x109d68 (definition 0x500af0, initial HP argument 10) → 0x14cb10 → 22 ordered `kobold.lmp` requests. Size 0x3d0, vtable 0x515ef0; +0x3cc variant 0, +0xe8 0, radius +0x1c 12, kind +0xb4 9. |
| 2 `Koboldtough` | 8 | Same chain and resource definition; +0x3cc variant 1, +0xe8 1, radius 20 and scale +0xdc 1.5. |
| 3 `koboldshaman` | 5 | Same chain and resource definition; +0x3cc variant 2, +0xe8 2, radius 18 and scale +0xdc 1.2. |
| 4 `WarWraith` | 9 | 0x2c07a8 → 0x109d68 (definition 0x5034f0, initial HP argument 4) → 0x14cb10 → 18 ordered `wwraith.lmp` requests. Size 0x468, vtable 0x517f80; fade +0x3c8 100, radius 18, speed +0xb8 140, home range +0x3c0 600, embedded Weapon1 at +0x3d0 and +0x50 points to it. |

The two definitions' 40 distinct entry names and archive presence are checked
by `difftest_blood1.py`; the new test confirms each request within the actual
derived→base constructor chain. **Executed** separately against the private
`monsters.bal`: original balance lookup 0x223a4c returns five signed
percentage factors for each class, compared at the raw float bit level:
`Kobold` (69, 100, 60, 69, 80), `Koboldtough` (250, 80, 100, 179, 189),
`koboldshaman` (179, 179, 120, 139, 189), `WarWraith` (200, 200, 160, 100,
200). `Creature_ctor` reaches that lookup and calls stat scaling 0x10a620,
but the constructor-chain test stubs those downstream results. Final HP,
damage and equipment-derived stats for a loaded blood1 actor are **Unknown**.
The original WarWraith own-object RNG picks holder part type 15 from a fresh
synthetic object on seed 20973 and type 13 on seed 7. Those are probe results,
not the weapon distribution of the nine level placements; preceding level
objects consume shared draws.

For **run/AI**, the new test executes Kobold_run 0x27f52c and WarWraith_run
0x2c0c2c in states 0, 3, 6, 7 and 0x14, with synthetic active/no-target
inputs and an animation event stub. It asserts the ordered processDamage,
Creature_run, active, stepAnim, target-pick and state-specific calls. This
covers five branch routes per class string (20 probes), including the wraith's
holder update and fade/deletion path. A second synthetic target-handle and
event-bit-1 probe reaches `Creature_hitTargetInArc` 0x119938 for each Kobold
variant (flags 8, 0x440008, 8) and `Creature_hitTargetAtReach` 0x1196e8
for WarWraith (flags 8). The hit functions return stubs; target selection,
pathing, shaman ally healing, weapon descriptors, landed damage and live
animation timing remain
**Unknown** to this test; the manually observed state descriptions in
`docs/monsters-2.md` are port leads, not claims of executed blood1 combat.

For **damage/death**, the base `Creature_takeDamage` 0x116638 probe with a
synthetic 100 HP object, no attacker, 25 damage and flags 8 reaches 75 HP,
records 25 accumulated damage and ORs flags 8. Both classes inherit this slot;
an actual attacker, defense or kill transition is **Unknown** here.
`Kobold_setState` 0x27ff6c with state 0x14 calls `Creature_dropLoot`
0x10f2c8 with six asserted raw float arguments; `WarWraith_setState`
0x2c1648 first calls holder drop slot 0x11b080 and then
`loot_generateDrops` 0x100d54 with its own six asserted arguments. Those
callees and their item/Gold returns are stubs, so drop creation and credit
remain **Unknown**. The wraith's subsequent dead tick calls `obj_delete`
0x14f200 with the synthetic fade state; world removal is not executed.

### Ordered native port list by class

1. `Kobold` (118): one world-owned 0x3d0 identity; load `kobold.lmp` and the
   balance row; port the base constructor chain and variant 0 fields; connect
   idle/chase/melee/retreat/death tick, base damage, event markers and
   `Creature_dropLoot`. Verify actual target and player damage before enabling
   the class in a strict blood1 load.
2. `Koboldtough` (8): reuse that identity and chain with variant 1 scale,
   radius, event and charged-target logic; check its two-hit branch and loot.
3. `koboldshaman` (5): reuse the chain with variant 2; port ally selection,
   corpse and wounded-ally checks, revive/Healing requests and their real
   skill/resource dependencies. Refuse the unverified FrostArmor entry path
   until its requester is established.
4. `WarWraith` (9): load `wwraith.lmp` and its balance row, construct the
   embedded holder and selected weapon part, port fade, target arbitration,
   flight/chase and drain attack, then holder-part drop, loot generation and
   deletion. Compare real handle, drop and Gold outcomes against original
   execution before calling the class playable.

## Scripted events and objectives

The focused [script-flow trace](blood1-scripts.md) supersedes the earlier
manual sequence. `tools/difftest_blood1_scripts.py` executes all 21 entries
and their material branches through the original script loader, binder and
interpreter on two seeds, with built-in effects stubbed. It asserts the
nine-node NPC dialog graph, both keyed exits and the three cutscene files.
The authored script has no enemy spawn, boss, mission grant or direct hub
return. Mission completion and hub return are conditional paths in the
destination `strife` / `drundar` scripts, not a blood1 exit effect.

## Ordered native port work for a fully playable `blood1`

1. Keep the proven hub menu route and establish a real, ordered `blood1`
   loader with one GameObject identity for script, collision, combat, save and
   draw. Preserve `clearColor`/`customVars` side effects and explicit refusal
   for any unsupported class. Resolve default `Player1` placement from the
   carried hub state without a guessed coordinate.
2. Port the level-interaction constructors used before combat: blockers,
   arrival/light markers, save points, portal, triggers, the NPC, container
   and chest objects, both AutoProp doors, and `smokeBomb`. Bind their
   collision, prompts, state, resource and save/load behavior. Check the door
   animation-absence boundary against original runtime behavior.
3. Load the real resource definitions and `monsters.bal`, then port the
   `Kobold` constructor and three variants, run/set-state/AI, attacks,
   shaman ally/heal path and animation events. Add the `WarWraith` constructor,
   embedded Weapon1 holder, attack, fade, death and weapon-part drop path.
   Use the shared world/grid and real object handles; no fixture actors.
4. Connect real player input/attack and production HP, damage, target,
   death, experience, loot, dropped items, Gold pickup and delayed credit
   through those objects. Preserve level seed accounting and loaded resource
   results. The `valor` campaign-combat handoff at commit `328b072` explains
   why a factory allocation or an isolated `ee_emu` function test alone does
   not satisfy a fight.
5. Execute and compare the authored opening cutscene, quest and good/evil
   choice, shard handling, door states, NPC dialog, savepoint and both exits
   across save/load. Then run a strict native hub → menu → `blood1` campaign
   playthrough with a real enemy hit, death, drop/credit and objective/exit
   completion. Report each reached state and each remaining refusal.

## Audit fixes (census)

2026-10-23: The focused census audit found three medium and two low gaps.
The committed difftest now checks all 29 class frequencies, all 20 selected
class names and the 21-entry count. This document narrows the other resource
and objective claims to the direct requests and links actually asserted,
and corrects the native unsupported count to 348 non-marker records.
The paired results and exact commands are recorded below.

## Verification boundary

The paired `difftest_blood1.py` runs use `--seed 20973` and `--seed 7`.
The separate `t3/research-story-route` branch has a hub-to-`blood1`
script/menu difftest; it was not rerun in this worktree. `difftest_objects.py
-k load` checks the generic loader and
marker model. The full Python unit suite is the analysis-tool regression gate.
`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_blood1.py
local/SLUS_209.73 local/BLOOD1.GOB local/KOBOLD.LMP local/WWRAITH.LMP
--seed 20973` passed: 363 records/10,632 bytes, 351 factory objects, 140
hostile records, 40 hostile resource requests, four direct probes and 21
script entries. The same command with `--seed 7` passed with those counts.
`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_blood1_enemies.py
local/SLUS_209.73 local/BLOOD1.GOB local/BALANCE.LMP --seed 20973`
passed with 140 placements, four class selections, 84 constructor requests
across those selections, 37 event setups, four balance rows, 20 no-target
ticks/176 observed calls, four targeted attack dispatches, four death routes
and one base damage probe. The
same command with `--seed 7` passed with those counts.
`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_objects.py
local/SLUS_209.73 -k load --seed 20973` passed five of five properties
for the generic loader/marker model. `PYTHONDONTWRITEBYTECODE=1 python3
-m unittest discover -s tools -p 'test_*.py'` passed 652 of 652 tests.
None is a native
client combat, terrain or cutscene test.
