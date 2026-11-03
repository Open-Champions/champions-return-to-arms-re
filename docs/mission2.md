# Mission 2 story levels: Plane of Innovation (SLUS-20973 US v2.00)

2026-10-27. **Partial research handoff, not a playable native mission.** The mission
menu's row 1 story pointer is `innovat1` (`t3/research-story-route`,
`76d4447`); the separate medal and bonus pointers are `innmedal` and
`innpit`. Mission 2 must first be made available by one of the hub actions
identified in `t3/research-quest-log` (`03c2304`); mission 1 completion by
itself does not prove that action ran. The shipped story object/script cells
support an **Executed request route** `innovat1` → `inmine1` → `inmine2` →
`innovat2`, with the three reverse exits. Exact record-to-entry links and
call containment are now asserted. The original dialog selector, objective
VM, deferred completion, death callback and portal request gates execute on
controlled state; actual inventory effects, physical use and completed loads
remain **Unknown**. See [the addressed route handoff](mission2-route.md) for
the new tests, controls and precise boundaries. The
[2026-11-02 offer/hub continuation](mission2-offer-hub.md) adds the ordinary
hub second-offer binding, trigger action/menu request, and controlled hub-return
requests. The [2026-11-03 route-list continuation](mission2-compose.md) builds
the return list with the original reset and current-level insertion, then
stops that hub request at the same pre-load boundary. The same note runs the
second offer, the mission menu, and that stop in one emulator, and applies
the audited counter-0 menu lifetime without re-deriving it. Hub2's cold
dialog choices, its trigger key, and the particle reset after pool init are
in that note. In-range physical use, the loader body after the archive
lookup, and arrival remain Unknown.

The four archives and their object/script records were **Observed** in the
owner's read-only disc. `tools/difftest_mission2.py` asserts the counts,
class selections and addressed exit/script cells below. Its original
`world_loadRecords`, factory and four derived → `Creature_ctor` →
`GameObject_ctor` chains are **Executed** by `ee_emu.py` on synthetic state,
seeds 20973 and 7. Allocations, resource returns, animation/model services,
combat and actual scene transitions are stubbed in that older test.
**Correction:** `newWorld(0)` supplies AMX string offset zero, not a null
destination. The new original-VM test resolves it to `innovat1` from
`inmine1`, and to `inmine1` from `inmine2`.

## Story route and objectives

`difftest_mission2_links.py` checks twelve individual record links, one
Portal without a script property, and 35 complete argument/call/cleanup
packets within parsed entry bounds. `difftest_mission2_travel.py` executes
all six exit entries through the original native command. These establish
authored identity and pending requests, not physical exit reachability.

| From | Record, entry and native-call cell | Request and limit |
|---|---|---|
| Mission menu | Row 1 story pointer `innovat1` | The ordinary hub dialog and record-11 action/menu path now execute on controlled state; see the offer/hub continuation. Physical use and arrival remain Unknown. |
| `innovat1` | Record 263 → `0x128`; call `0x154` | `inmine1`; physical use and load untested. |
| `inmine1` | Records 139/140 → `0x000`/`0x044`; calls `0x02c`/`0x070` | `innovat1`/`inmine2`; original pending writes execute. |
| `inmine2` | Records 38/102 → `0x000`/`0x044`; calls `0x02c`/`0x070` | `inmine1`/`innovat2`; original pending writes execute. |
| `innovat2` | Record 31 → `0x044`; call `0x070` | `inmine2`; Portal record 57 separately runs gate `0x110` and chooses a runtime destination-list entry, not a fixed script destination. |

**Observed and Executed on controlled state:** `innovat1` NPC records
72/73 link to entries `0x000`/`0x094`. Their shipped dialog tables select
offer actions `0x2e0`/`0x910` and the shared turn-in `0x418` through
original native open/confirm messages and the VM. The start entry `0xb00`
sets availability and two mission variables and posts `0xbe0`; the latter
requests its cutscene only before its guard variable is set. Turn-in writes
its finish variable, requests item removal, removes the journal title and
queues `0xc98`. With an initially empty queue the first deferred task call
promotes it, the second executes its item-give handler and mission-2 grant.
Completion is unchanged before that execution. Inventory and presentation
services remain controlled; completed item delivery is not established.

**Observed and Executed on controlled state:** `innovat2` boss record 30
links death entry `0x000` → `0x46c` and the same item used by turn-in.
Trigger records 58/59 link to `0x150`/`0x194`. The first boss branch posts
`0x32c`, which enables save inhibition then sets creature flag 0 through
`0x39c`; the repeat branch calls `0x39c` directly and leaves save inhibition
unchanged. Original `Creature_onDeath` at `0x10beb8` runs the death script
before the named-item drop call: the portal gate becomes 1 and save
inhibition clears even for quiet death, which suppresses the drop call.
The item-spawn callee remains stubbed. Portal prompt/menu execution reaches
a pending request; full loader `0x1e55c0`, arrival, physical boss death,
item pickup, save behavior and playable completion remain **Unknown**.

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
seeds. The test reads ordered entry names from the owner executable in memory
and checks that the executed requests match and the entries occur in the
owner archives. Only aggregate counts are committed. Null resource results
leave residency, loaded model, animation and fighting behavior Unknown.

| Class or group | Constructor-stage resource result and limit |
|---|---|
| Both clockwork variants | Class definition `0x4ff260` makes 26 requests from `clokwork.lmp`. Both variants use one `0x24e124` constructor and the same definition; sub-kind behavior still needs a state/tick comparison. |
| `Droid` | Definition `0x500a88` makes 10 requests from `droid.lmp`. The IronGuardian's separate Droid spawning path remains untested here. |
| `IronGuardian` | Definition `0x500960` makes 34 requests from `iron.lmp`. `docs/monsters-2.md` also records a separate `droid.lmp` load in this constructor; the new probe stubs that lower service. |
| `PowderKeg` | A separate direct constructor probe asserts two named resource requests; their names and archive membership are not committed or checked here. |
| `Blocker`, `PushTrigger`, `Trigger`, `Weather`, `smokeBomb` | Bounded direct constructor probes make zero named `res_find` calls with lower services stubbed. They may still need effect, world or script resources later. |
| `Rat`, `Seagull` | Their `Critter` constructor has no class-definition pointer and formats resource names dynamically. Matching member presence and exact ordered requests are **Unknown** to this difftest. |
| `gbarrel`, `lavakeg`, `gearbox` | They use `AutoContainer` or `AutoChest` fallback constructors. Exact instance request strings and archive residency are **Unknown** because the stubbed formatting service does not resolve them. |
| `NPC`, `Portal`, `Savepoint`, lights and markers | Instance-specific resource residency remains **Unknown** here. The route handoff executes the final Portal's predicate/menu request; completed travel remains Unknown. |

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
2. Use the now-asserted per-record links and contained calls plus the
   executed start, NPC choices, turn-in/deferred grant and boss/portal
   contracts in `mission2-route.md`. Preserve completion-at-consumption,
   the distinct first/repeat boss behavior and original dialog selection.
   Physical NPC/Trigger dispatch and actual inventory effects still need
   original/native comparisons; the controlled fixtures do not settle
   those integration boundaries.
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
6. Compose the researched NPC choices, journal/turn-in, mission grant,
   boss/save gate and travel request with real cutscenes, inventory and
   every physical exit across save/load. Both `newWorld(0)` string-offset
   destinations are now established. Full original/native loading and
   carried-state arrival remain unproved; pending-name parity alone does
   not establish a playable route.

## Verification

The following are retained **2026-10-23 historical results and limits**.
The 2026-10-27 link/VM/dialog/travel results and remaining limits supersede
their unknowns as described in [mission2-route.md](mission2-route.md).

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
