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

**Observed** in `~/Projects/open-champions/worktrees/playable-integration`
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

## Scripted events and objectives

**Observed by manual inspection** of the private `blood1` script image with
`tools/scr.py`: the following is a proposed event sequence, not a committed
body-level or end-to-end execution result. `difftest_blood1.py` asserts 21
entry names, selected imports and four object-property links only. Each
objective, branch action, cutscene effect, item change and destination below
is **Unknown to the committed difftest** until body or runtime checks land.

1. `start` checks mission 1 completion and the current good/evil state,
   offers the appropriate objective, marks mission 1 available, sets
   `startedMission1` and `currentMission`, and posts `absorb`. A prior decision
   sets the corresponding door state. `absorb` plays the `blood1` cutscene
   once under `bl_sawBlood1`, then posts `removeActors`.
2. The NPC with `dialogscript=startDia1ce` opens the `natasla` dialog. The
   proximity `Trigger` calls `ifdcc4`: it opens the dialog only before
   `metNatasla` is set, then marks that variable. The dialog's branch actions
   include `setEvil3024` (good) and `setEvil1037` (evil). The evil branch
   changes the active objective, sets `talkedToNatasla`, and posts the evil
   door event; the good branch posts the good door event. These are script
   links, not a tested native dialog traversal.
3. `gooddoor` plays the `gooddoor` cutscene. `evildoor` plays its cutscene,
   then posts `giveshard`; that gives `shardofwar` and defers
   `checkShardCount`. The latter presents a help message and checks each
   player slot for excess copies. The script also has `removeActors`, which
   deletes the object named `actor` after the opening cutscene.
4. Two `PushTrigger` exits guard on `getEvil` and call `newWorld` for `strife`
   or `drundar` respectively. Three `Player1` arrival markers exist: a
   default and records for arrivals from those two levels. The `Portal`
   uses the `jumpgate` resource. The direct hub mission-menu request and
   same-act carryover are documented in `docs/story-route.md` on
   `t3/research-story-route`; exact arrival placement in a live native load
   remains unverified.

Manual inspection suggests the script imports `getMissionComplete`, `addQuest`/`removeQuest`, item
grant/check/remove, `autoPropSetState`, `cutScene`, `startDialog`, `newWorld`
and related decision/variable calls. Cutscene names correspond to entries in
the level archive; the NPC dialog has its own `.dbin` entry. The authored
object records alone do not prove objectives, cutscenes or exits complete in
the native client.

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
The existing `difftest_story_route.py` checks the hub-to-`blood1` script/menu
route at both seeds. `difftest_objects.py -k load` checks the generic loader and
marker model. The full Python unit suite is the analysis-tool regression gate.
`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_blood1.py
local/SLUS_209.73 local/BLOOD1.GOB local/KOBOLD.LMP local/WWRAITH.LMP
--seed 20973` passed: 363 records/10,632 bytes, 351 factory objects, 140
hostile records, 40 hostile resource requests, four direct probes and 21
script entries. The same command with `--seed 7` passed with those counts.
The full unit suite is reported with the follow-on enemy research commit.
None is a native
client combat, terrain or cutscene test.
