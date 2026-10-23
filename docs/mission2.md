# Mission 2 story levels: Plane of Innovation (SLUS-20973 US v2.00)

2026-10-23. **Research handoff, not a playable native mission.** The mission
menu's row 1 story pointer is `innovat1` (`t3/research-story-route`,
`76d4447`); the separate medal and bonus pointers are `innmedal` and
`innpit`. Mission 2 must first be made available by one of the hub actions
identified in `t3/research-quest-log` (`03c2304`); mission 1 completion by
itself does not prove that action ran. The shipped story object/script links
then lead `innovat1` → `inmine1` → `inmine2` → `innovat2`.

The four archives and their object/script records were **Observed** in the
owner's read-only disc. `tools/difftest_mission2.py` asserts the counts,
class selections and addressed exit/script cells below. Its original
`world_loadRecords`, factory and four derived → `Creature_ctor` →
`GameObject_ctor` chains are **Executed** by `ee_emu.py` on synthetic state,
seeds 20973 and 7. Allocations, resource returns, animation/model services,
combat and actual scene transitions are stubbed. `newWorld(0)` is a null
script argument; this check does not resolve its runtime destination.

## Story route and objectives

| From | Authored link and addressed call | Limit |
|---|---|---|
| Mission menu | Row 1 story pointer `innovat1` | The menu requires mission 2 availability; the hub dialog path is not executed here. |
| `innovat1` | One `PushTrigger` action `newWorld9ddd`: `newWorld('inmine1')` at script offset `0x154` | Physical use and level load untested. |
| `inmine1` | Two `PushTrigger` actions: `newWorld1f84` calls `newWorld(0)` at `0x02c`; `newWorldb54d` calls `newWorld('inmine2')` at `0x070` | The zero argument's resolved destination is Unknown here. |
| `inmine2` | Two `PushTrigger` actions: `newWorld9ddd` calls `newWorld(0)` at `0x02c`; `newWorld5ccf` calls `newWorld('innovat2')` at `0x070` | The zero argument's resolved destination is Unknown here. |
| `innovat2` | `newWorldb54d` returns to `inmine2` at `0x070`; its `Portal` has `script=return1c66`, a gate that reads `in_killediron` | The destination selected by the portal is not established by this script check. |

**Observed and asserted** in `innovat1`: `start` calls
`setMissionAvailable(2,1)` at `0x0b34`, sets `startedMission2` and
`currentMission`, and posts `absorb`. That action has a one-time
`cutScene('innovat1')` call at `0x0c4c`. Two NPC records link to distinct
dialog entries; two branch actions add the same quest title key with
different body keys. A turn-in action removes the quest and a
`coppersprocket`, then defers `receivedShard`; that entry gives
`shardofinnovate` and calls `grantMission(2)` at `0x0d00`. The current test
asserts the named `addQuest`, `removeQuest` and grant call cells, not the
dialog choice or every condition required to reach them. Other branch
actions exchange `sprocket1` or `sarcophaguskey1` for `shard`; their
reachability is Unknown here.

**Observed and partially asserted** in `innovat2`: the one
`IronGuardian` record has `dropitem=coppersprocket` and
`deathscript=callScricb75`. Two `Trigger` records lead to the `ironboss`
and `portalMessage` script entries. `ironboss` may play the `iron` cutscene,
set the save inhibit flag and mark the named boss as a miniboss. The
`killediron` entry sets `in_killediron=1` and clears save inhibit; the portal
gate reads that variable. The difftest pins the cutscene and variable cells,
the deathscript property and the portal property, but does not execute the
boss death or prove the indirect call reaches `killediron`. Actual item
drop, quest completion, save behavior and portal travel remain Unknown.

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

The four new hostile-class constructor probes execute one representative
each of `clockworkcutter`, `clockworkhammer`, `Droid` and `IronGuardian`
through the original factory, `Creature_ctor` and `GameObject_ctor` at both
seeds. The class definitions and named archive entries are checked against
the executable and owner disc. A null resource result is returned, so
archive presence and request order are proven, but residency, loaded model,
animation and fighting behavior are not.

| Class or group | Constructor-stage resource result and limit |
|---|---|
| Both clockwork variants | Class definition `0x4ff260` requests 26 entries from `clokwork.lmp`: model/texture, cutter and hammer attack/death/hit/idle/walk clips and left/right swoosh model/texture. Both variants use one `0x24e124` constructor and the same definition; sub-kind behavior still needs a state/tick comparison. |
| `Droid` | Definition `0x500a88` requests 10 `droid.lmp` entries: model/texture, explode, hit, two idle, run, walk and two death clips. The IronGuardian's separate Droid spawning path remains untested here. |
| `IronGuardian` | Definition `0x500960` requests 34 `iron.lmp` entries: model/texture, attack 1–4, catapult, death, two hit, two idle, shoot, walk and ten junk model/texture pairs. `docs/monsters-2.md` also records a separate `droid.lmp` load in this constructor; the new probe stubs that lower service. |
| `PowderKeg` | A separate direct constructor probe asserts `powderk.lmp` requests for `powderkeg.vif` and `powderkeg.tex`. |
| `Blocker`, `PushTrigger`, `Trigger`, `Weather`, `smokeBomb` | Bounded direct constructor probes make zero named `res_find` calls with lower services stubbed. They may still need effect, world or script resources later. |
| `Rat`, `Seagull` | Their `Critter` constructor has no class-definition pointer and formats resource names dynamically. The owner archives `rat.lmp` and `seagull.lmp` contain matching model/texture and movement/idle identifiers. Exact ordered requests on these records are **Unknown** to this difftest; no class-definition result is inferred for them. |
| `gbarrel`, `lavakeg`, `gearbox` | Record properties name those three LMPs, which are present on the disc. They use `AutoContainer` or `AutoChest` fallback constructors. Exact instance request strings and archive residency are **Unknown** to the committed test because the stubbed formatting service does not resolve them. |
| `NPC`, `Portal`, `Savepoint`, lights and markers | Instance-specific resource requests are **Unknown** here. The `innovat2` portal's `lump=jumpgate` property is asserted; the `innovat1` portal has no such property. |

**Native snapshot, 2026-10-23.** The inspected
`open-champions/worktrees/playable-integration` script host has a
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
2. Port blockers, three character-light markers, save points, triggers,
   portals, NPC dialog hooks, weather, smoke effects, PowderKegs,
   AutoContainers and AutoChests with their property/resource and save
   behavior. Establish real collision and trigger use before accepting an
   exit. Check dynamically formatted request names against original calls.
3. Port Rat/Seagull `Critter` identity and actual `rat.lmp` / `seagull.lmp`
   requests. Then port the two Clockwork variants through their shared
   constructor, holder, animation events, targeting, damage and death.
   Compare real loaded handles, seeded draws and attacks, not just pool size.
4. Port Droid construction and tick in `inmine1`, then the
   `IronGuardian` constructor, Droid spawn budget, boss AI, junk/missile
   attacks, death and `coppersprocket` drop in `innovat2`. Preserve the
   shared object/grid/seed and real player damage, item pickup and credit.
5. Execute the two NPC choice paths, quest add/turn-in, mission grant,
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
loader bytes, 660 factory selections, 70 definition entries, five dynamic
archive-presence checks, 96 named requests through four constructor chains,
six bounded direct constructor probes and six addressed exits. The generic
object loader passed 5/5 properties at each seed. The existing quest model
passed 7/7; quest-log 14/14 controlled page probes plus three disc scripts;
story route 26/26 menu snapshots per seed; mission-menu art 39/39 draw and
20/20 input cases per seed; and the full Python unit suite 652/652. All
commands ran serially with `PYTHONDONTWRITEBYTECODE=1`; their logs are under
ignored `local/`. These are original-function and static-fixture results,
not a running-game mission or native port.
