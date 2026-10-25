# Mission 2 story levels: Plane of Innovation (SLUS-20973 US v2.00)

2026-10-23. **Research handoff, not a playable native mission.** The mission
menu's row 1 story pointer is `innovat1` (`t3/research-story-route`,
`76d4447`); the separate medal and bonus pointers are `innmedal` and
`innpit`. Mission 2 must first be made available by one of the hub actions
identified in `t3/research-quest-log` (`03c2304`); mission 1 completion by
itself does not prove that action ran. The shipped story object/script cells
support an **Inferred** `innovat1` → `inmine1` → `inmine2` → `innovat2`
route; the exact record-to-entry links and call containment remain Unknown.

The four archives and their object/script records were **Observed** in the
owner's read-only disc. `tools/difftest_mission2.py` asserts the counts,
class selections and addressed exit/script cells below. Its original
`world_loadRecords`, factory and four derived → `Creature_ctor` →
`GameObject_ctor` chains are **Executed** by `ee_emu.py` on synthetic state,
seeds 20973 and 7. Allocations, resource returns, animation/model services,
combat and actual scene transitions are stubbed. `newWorld(0)` is a null
script argument; this check does not resolve its runtime destination.

## Story route and objectives

The difftest checks each addressed call cell and the aggregate action-link
set separately. It does not establish which individual record carries each
link or that a call cell lies inside the listed entry. Those pairings are
**Unknown** until checked against per-record properties and parsed entry
boundaries.

| From | Addressed call cell and aggregate action link | Limit |
|---|---|---|
| Mission menu | Row 1 story pointer `innovat1` | The menu requires mission 2 availability; the hub dialog path is not executed here. |
| `innovat1` | `PushTrigger` action-link set includes entry `0x128`; `newWorld('inmine1')` call cell is at `0x154` | Physical use and level load untested. |
| `inmine1` | Action-link set includes entries `0x000`, `0x044`; `newWorld(0)` and `newWorld('inmine2')` cells are at `0x02c`, `0x070` | The zero argument's resolved destination is Unknown here. |
| `inmine2` | Action-link set includes entries `0x000`, `0x044`; `newWorld(0)` and `newWorld('innovat2')` cells are at `0x02c`, `0x070` | The zero argument's resolved destination is Unknown here. |
| `innovat2` | Action-link set includes entry `0x044`; `newWorld('inmine2')` cell is at `0x070`; its `Portal` script link is separately checked | The destination selected by the portal is Unknown. |

**Observed and statically asserted** in `innovat1`: `start` begins at
`0x0b00`; addressed cells call `setMissionAvailable(2,1)` at `0x0b34`, set
two distinct mission variables to 1 and 2, and post the entry at `0x0be0`.
A `cutScene('innovat1')` call cell is at `0x0c4c`. The combined properties
of two NPC records include two distinct dialog entries; **which record
links to which entry is Unknown** to this test. Two addressed `addQuest`
cells use the same title key and different body keys. Addressed cells
remove that quest and a `coppersprocket`, defer the entry at `0x0c98`, give
an item, and call `grantMission(2)` at `0x0d00`. Assigning those cells to
specific branch or turn-in entries is **Inferred** until entry containment
is asserted. Dialog choices, conditions, execution and other branch
reachability remain Unknown.

**Observed and statically asserted** in `innovat2`: the one
`IronGuardian` record has a `coppersprocket` drop property and a deathscript
link. The combined properties of two `Trigger` records include links to
entries at `0x150` and `0x194`; **which record carries which link is
Unknown** to this test. Addressed cells at `0x17c` and `0x1c0` call the
boss and portal-message entries. Other addressed cells call the `iron`
cutscene and save inhibit on. The entry at `0x46c` is asserted separately
from cells that set the variable read by the portal gate and call save
inhibit off. Which entry contains each call cell is **Unknown** to this
test. The miniboss flag call is **Observed**, not asserted by this test. No
script entry, boss death or portal is executed here; actual item drop,
quest completion, save behavior and portal travel remain Unknown.

## Authored object census and required constructors

**Counts only** from the four `objects.ob` images; no position, angle,
property payload or game byte is tracked. The last column is the original
factory's allocation size and selected constructor, checked for all 699
records on both seeds. A dash means no GameObject allocation at this
factory boundary; `clearColor` and `customVars` can still have level side
effects. All 31 distinct class strings are represented.

| Class | `innovat1` | `inmine1` | `inmine2` | `innovat2` | Total | Factory size / constructor |
|---|---:|---:|---:|---:|---:|---|
| `Ambient_Light` | 1 | 1 | 1 | 1 | 4 | — |
| `Ambient_Light2` | 1 | 1 | 1 | 1 | 4 | — |
| `Blocker` | 19 | 4 | — | 30 | 53 | `0x4c` / `0x28f15c` |
| `charAmbient_Light` | 1 | 1 | 1 | 1 | 4 | `0x4c` / `0x158bcc` |
| `charDirectional_Light` | 1 | 1 | 1 | 1 | 4 | `0x4c` / `0x158c6c` |
| `charDirectional_LightD` | 1 | 1 | 1 | 1 | 4 | `0x4c` / `0x158d0c` |
| `clearColor` | 1 | 1 | 1 | 1 | 4 | — |
| `clockworkcutter` | 23 | 23 | 20 | — | 66 | `0x500` / `0x24e124` |
| `clockworkhammer` | 29 | 23 | 14 | — | 66 | `0x500` / `0x24e124` |
| `customVars` | 1 | 1 | 1 | 1 | 4 | — |
| `Directional_Light` | 1 | 1 | 1 | 1 | 4 | — |
| `Directional_Light2` | 1 | 1 | 1 | 1 | 4 | — |
| `Directional_LightD` | 1 | 1 | 1 | 1 | 4 | — |
| `Directional_LightD2` | 1 | 1 | 1 | 1 | 4 | — |
| `Droid` | — | 30 | — | — | 30 | `0x3d0` / `0x27b840` |
| `gbarrel` | — | 77 | 51 | — | 128 | `0x148` / `0x23d93c` |
| `gearbox` | 6 | 5 | 3 | — | 14 | `0xf8` / `0x23ad18` |
| `IronGuardian` | — | — | — | 1 | 1 | `0x3e8` / `0x27a00c` |
| `lavakeg` | 113 | — | — | — | 113 | `0x148` / `0x23d93c` |
| `NPC` | 2 | — | — | — | 2 | `0x480` / `0x29df04` |
| `Player1` | 2 | 2 | 2 | 1 | 7 | `0x4c` / `0x158928` |
| `Portal` | 1 | — | — | 1 | 2 | `0x164` / `0x27c694` |
| `PowderKeg` | — | 33 | 11 | — | 44 | `0x84` / `0x290c24` |
| `PushTrigger` | 1 | 2 | 2 | 1 | 6 | `0x4c` / `0x1ec900` |
| `Rat` | 36 | — | — | 8 | 44 | `0x448` / `0x2547fc` |
| `Savepoint` | 2 | 2 | 2 | — | 6 | `0x118` / `0x28cb90` |
| `Seagull` | 30 | — | — | 12 | 42 | `0x448` / `0x2547fc` |
| `smokeBomb` | 17 | — | — | 4 | 21 | `0x4ac` / `0x2c54f8` |
| `TestLocation` | 5 | — | 2 | — | 7 | — |
| `Trigger` | — | — | — | 2 | 2 | `0x70` / `0x1ecdf4` |
| `Weather` | — | 1 | — | — | 1 | `0x2a0` / `0x1d7778` |

Totals: `innovat1` 297 records / 284 selections (52 clockwork enemies,
66 ambient Critters); `inmine1` 213 / 205 (46 clockwork and 30 Droid);
`inmine2` 118 / 108 (34 clockwork); `innovat2` 71 / 63 (one
IronGuardian and 20 ambient Critters). Across the route: **699 records,
660 factory selections, 163 authored hostile placements**, plus 86 Rat or
Seagull Critters. `world_loadRecords` consumed 22,156 bytes in total and
passed every class, angle and property list to the recording factory in
file order. It does not construct the full level.

## Resource requests and native coverage

The placement-ordered hostile constructor, layout, balance, synthetic tick,
damage and death contracts are in [mission2-enemies.md](mission2-enemies.md).
Its companion `tools/ref_mission2_enemies.py` pins addresses, counts and
bounded behavior; `tools/difftest_mission2_enemies.py` derives ordered resource
names from owner inputs and checks the constructor requests on both seeds.
These are isolated original-function checks.

The four new hostile-class constructor probes execute one representative
each of `clockworkcutter`, `clockworkhammer`, `Droid` and `IronGuardian`
through the original factory, `Creature_ctor` and `GameObject_ctor` at both
seeds. The test reads ordered entry names from the owner executable in memory
and checks that the executed requests match and the entries occur in the
owner archives. Ordered names remain in memory during the check or in an
ignored local manifest. Null resource results
leave residency, loaded model, animation and fighting behavior Unknown.

| Class or group | Constructor-stage resource result and limit |
|---|---|
| Both clockwork variants | Class definition `0x4ff260` makes 26 requests from `clokwork.lmp`. Both variants use one `0x24e124` constructor and the same definition; bounded sub-kind ticks are compared in `mission2-enemies.md`, while loaded combat remains untested. |
| `Droid` | Definition `0x500a88` makes 10 requests from `droid.lmp`. The IronGuardian's separate Droid spawning path remains untested here. |
| `IronGuardian` | Definition `0x500960` makes 34 requests from `iron.lmp`. `docs/monsters-2.md` also records a separate `droid.lmp` load in this constructor; the new probe stubs that lower service. |
| `PowderKeg` | A separate direct constructor probe asserts two named resource requests; their names and archive membership are not committed or checked here. |
| `Blocker`, `PushTrigger`, `Trigger`, `Weather`, `smokeBomb` | Bounded direct constructor probes make zero named `res_find` calls with lower services stubbed. They may still need effect, world or script resources later. |
| `Rat`, `Seagull` | Their `Critter` constructor has no class-definition pointer and formats resource names dynamically. Matching member presence and exact ordered requests are **Unknown** to this difftest. |
| `gbarrel`, `lavakeg`, `gearbox` | They use `AutoContainer` or `AutoChest` fallback constructors. Exact instance request strings and archive residency are **Unknown** because the stubbed formatting service does not resolve them. |
| `NPC`, `Portal`, `Savepoint`, lights and markers | Instance-specific resource requests are **Unknown** here. The `innovat2` portal script link is asserted; destination behavior remains Unknown. |

**Native snapshot, 2026-10-23.** The inspected
`codex/playable-integration` (Godot repository) script host has a
`kPorted` constructor list for SmallSpider, Gnaw, Mosquito, Scorpion,
Badger, Skelight, Zek and Horsemen. None of this mission's 22 selected
class strings is on that list. Its seven `Player1` records use a separate,
conditional marker path; the other 653 selected records need a dedicated
native route or an explicit refusal. This is a source snapshot, not a
native load test. The separate `port-warboar` branch implements bounded
WarBoar/Minotaur paths and still refuses missing resources/ticks; the
`native-horsemen` and `playable-integration` reports cover partial Horsemen
construction and unverified play-scene combat. Those classes do not occur in
mission 2. `t3/research-blood1` (`5107fcb`) provides Kobold/WarWraith
constructor and attack references for mission 1, with no native
Kobold/WarWraith constructor in the inspected script-host list. None of
these parallel efforts substitutes for Clockwork, Droid, Critter or
IronGuardian construction here.

## Ordered native port and verification gates

1. Connect mission-2 availability and row-1 selection to a strict ordered
   `innovat1` load. Preserve all 699 object records and metadata side
   effects, the seven conditional `Player1` markers and the real level seed.
   Refuse any unsupported selected class explicitly.
2. Before native objective claims, assert each NPC, `PushTrigger` and
   `innovat2` `Trigger` link per record, and locate each claimed call cell
   inside its parsed entry bounds. Then execute the start, two NPC branches,
   turn-in/deferred grant, boss/portal wrappers, and both boss gate states
   through the original script host on controlled state. Compare native
   effects and prove both Trigger links reach their entries. Static cells
   alone do not establish ordering or reachability.
3. Port blockers, three character-light markers, save points, triggers,
   portals, NPC dialog hooks, weather, smoke effects, PowderKegs,
   AutoContainers and AutoChests with their property/resource and save
   behavior. Establish real collision and trigger use before accepting an
   exit. Check dynamically formatted request names against original calls.
4. Port Rat/Seagull `Critter` identity and actual resource
   requests. Then port the two Clockwork variants through their shared
   constructor, holder, animation events, targeting, damage and death.
   Compare real loaded handles, seeded draws and attacks, not just pool size.
5. Port Droid construction and tick in `inmine1`, then the
   `IronGuardian` constructor, Droid spawn budget, boss AI, junk/missile
   attacks, death and `coppersprocket` drop in `innovat2`. Preserve the
   shared object/grid/seed and real player damage, item pickup and credit.
6. Execute the two NPC choice paths, quest add/turn-in, mission grant,
   cutscenes, boss/save inhibit gate, portal condition and every linked
   `PushTrigger` across save/load. Compare actual original and native
   transitions, including what each `newWorld(0)` resolves to. A function
   difftest or direct level request does not establish a playable route.

## Verification

Run with `PYTHONDONTWRITEBYTECODE=1`, serially under machine load:

```sh
python3 tools/difftest_mission2.py local/SLUS_209.73 local --seed 20973
python3 tools/difftest_mission2.py local/SLUS_209.73 local --seed 7
python3 tools/difftest_objects.py local/SLUS_209.73 -k load --seed 20973
python3 tools/difftest_objects.py local/SLUS_209.73 -k load --seed 7
python3 -m unittest discover -s tools -p 'test_*.py'
```

**Results, 2026-10-23:** both mission-2 seeds passed 699 records / 22,156
loader bytes, 660 factory selections, 70 definition entries,
96 requests through four constructor chains,
six bounded direct constructor probes and six addressed exits. The generic
object loader passed 5/5 properties at each seed. The existing quest model
passed 7/7; quest-log 14/14 controlled page probes plus three disc scripts;
story route 26/26 menu snapshots per seed; mission-menu art 39/39 draw and
20/20 input cases per seed; and the full Python unit suite 652/652. All
commands ran serially with `PYTHONDONTWRITEBYTECODE=1`; their logs are under
ignored `local/`. These are original-function and static-fixture results,
not a running-game mission or native port.

**Audit FIX rerun, 2026-10-23:** seeds 20973 and 7 each passed the mission
difftest with the 22,156-byte total now asserted. The test also pins the
addressed objective call cells and aggregate NPC/Trigger links described
above, plus the deathscript and portal properties. Per-record link pairing
and call containment are Unknown. The full Python unit suite passed 652/652.
Ordered resource names are
derived only in memory from owner inputs; dynamic Critter/container member
presence and all objective execution remain Unknown.

**Second-round audit fix, 2026-10-23:** the report now labels the candidate
route Inferred and leaves per-record link pairing and call containment
Unknown until directly asserted. The mission difftest again passed seeds
20973 and 7 (699 records, 22,156 consumed bytes, 660 factory selections,
96 constructor requests and six addressed exits per seed); the full Python
unit suite passed 652/652. Both ran serially with
`PYTHONDONTWRITEBYTECODE=1`.
