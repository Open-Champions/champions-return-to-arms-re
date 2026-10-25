# Mission 1 exits: `strife` and `drundar` (SLUS-20973 US v2.00)

2026-10-23. **Research handoff, not a playable native route.** The two keyed
`blood1` exits request `strife` (good choice) and `drundar` (evil choice), as
traced in `t3/research-blood1-scripts` `532f69c`. These destinations are
separate story levels. `tools/difftest_strife_drundar.py` checks the private
disc records against committed count-only and constructor references on seeds
20973 and 7. The original loader, factory and selected constructors execute
in `ee_emu.py` on synthetic state. Allocation and resource returns are
stubbed; combat, script built-ins and actual transitions are not run. Script
objectives below are **Observed static cells and links** plus an **Inferred**
event order, not a continuous script-host run.

## Object census

**Observed and asserted:** `STRIFE.GOB` has 283 records (35 class strings),
9,780 loader bytes and 267 factory selections. `DRUNDAR.GOB` has 270 records
(29 class strings), 11,960 loader bytes and 254 selections. The committed
`Counter` assertions cover each class below. The loader check compares all
records, angles and joined property text in file order. No complete object
record, position or raw property array is committed; the census assertion
stores counts only. One `Crate` without `autocontainer` makes no object, while the
other 70 select AutoContainer. `clearColor` and `customVars` also return no
object but have factory side effects. The generic table reader joins property
strings with semicolons; its `customVars` entry contains an embedded semicolon,
so the loader test checks its original joined text and does not assert the
individual property boundary or resulting side effect.

| Class | Strife | Drundar |
|---|---:|---:|
| `Ambient_Light` | 1 | 1 |
| `Ambient_Light2` | 1 | 1 |
| `ammocart` | 2 | 0 |
| `arenadoor` | 0 | 4 |
| `Barrel` | 0 | 29 |
| `Blocker` | 6 | 12 |
| `boxafay` | 36 | 0 |
| `boxbfay` | 35 | 0 |
| `Catapult` | 2 | 0 |
| `charAmbient_Light` | 1 | 1 |
| `charDirectional_Light` | 1 | 1 |
| `charDirectional_LightD` | 1 | 1 |
| `clearColor` | 1 | 1 |
| `Crate` | 0 | 71 |
| `customVars` | 1 | 1 |
| `dbridge` | 3 | 0 |
| `Directional_Light` | 1 | 1 |
| `Directional_Light2` | 1 | 1 |
| `Directional_LightD` | 1 | 1 |
| `Directional_LightD2` | 1 | 1 |
| `Firepot` | 6 | 0 |
| `GoblinArcher` | 0 | 23 |
| `GoblinRecruit` | 0 | 9 |
| `GoblinSoldier` | 0 | 39 |
| `gobstand` | 5 | 0 |
| `kelethinBomb` | 15 | 0 |
| `leanto` | 6 | 0 |
| `NPC` | 4 | 0 |
| `Ogre` | 0 | 14 |
| `Orc2Archer` | 20 | 0 |
| `Orc2Leader` | 2 | 0 |
| `Orc2Leader1` | 2 | 0 |
| `Orc2Shaman` | 2 | 0 |
| `Orc2Soldier` | 43 | 0 |
| `orkbox` | 0 | 3 |
| `Player1` | 2 | 1 |
| `Portal` | 1 | 1 |
| `PushTrigger` | 2 | 13 |
| `Savepoint` | 3 | 3 |
| `TestLocation` | 8 | 7 |
| `Torch` | 64 | 0 |
| `Trigger` | 2 | 6 |
| `uwflag` | 0 | 15 |
| `UWStair` | 0 | 1 |
| `uwswitch` | 0 | 8 |
| `Weather` | 1 | 0 |

The original factory selected 69 Orc placements in Strife and 85 Goblin/Ogre
placements in Drundar. These are authored records, not observed live fights.

## Required constructors and native coverage

**Executed:** all 553 factory calls selected the following pool sizes and
constructors on both seeds. The reference in `tools/ref_strife_drundar.py`
pins every case-sensitive class string; grouped rows here share a constructor.
A dash means no GameObject allocation.

| Class group | Pool / constructor |
|---|---|
| Orc2Archer, Orc2Leader, Orc2Leader1, Orc2Shaman, Orc2Soldier | 0x488 / 0x2a0954 |
| GoblinArcher, GoblinRecruit, GoblinSoldier | 0x498 / 0x26a624 |
| Ogre | 0x468 / 0x29fad0 |
| Catapult | 0xfc / 0x24d440 |
| kelethinBomb | 0x58 / 0x261dbc |
| Firepot, Torch | 0x8c / 0x2b1e80 |
| Barrel | 0x84 / 0x290c24 |
| ammocart, boxafay, boxbfay, 70 Crate | 0x148 / 0x23d93c (AutoContainer) |
| leanto, orkbox | 0xf8 / 0x23ad18 (AutoChest) |
| dbridge, gobstand, UWStair, uwflag, uwswitch | 0x198 / 0x23c44c (AutoProp) |
| arenadoor | 0x198 / 0x243594 |
| NPC | 0x480 / 0x29df04 |
| Blocker | 0x4c / 0x28f15c |
| Savepoint | 0x118 / 0x28cb90 |
| Portal | 0x164 / 0x27c694 (JumpGate) |
| PushTrigger | 0x4c / 0x1ec900 |
| Trigger | 0x70 / 0x1ecdf4 |
| Weather | 0x2a0 / 0x1d7778 |
| Player1 | 0x4c / 0x158928 (arrival marker) |
| charAmbient_Light, charDirectional_Light, charDirectional_LightD | 0x4c / 0x158bcc, 0x158c6c, 0x158d0c respectively |
| six plain lights, TestLocation, clearColor, customVars, one Crate | — |

**Native snapshot:** `codex/playable-integration` has a small `kPorted`
constructor list and no selected Orc, Goblin or Ogre constructor above.
The separate `fx_props` code contains bounded Torch/Firepot tick logic,
and the dialog code recognizes Orc2 class names; neither proves those level
objects construct and run in the play scene. Generic script and interaction
support is likewise partial. The parallel `port-warboar` work establishes
bounded WarBoar/Minotaur
resources and refuses the still separate combat worlds; neither family occurs
in these levels. `t3/research-blood1` `5107fcb` supplies Kobold/WarWraith
reference chains for the preceding level, but its native constructors are not
on that inspected list and neither class occurs here. `native-horsemen` round
4 (`2a8e6cb`) builds four on-foot `UndeadKnight` rows, without a combat
runtime. Its research explicitly locates those rows in **`DRUNARE.GOB`**, the
Drundar arena reached after this story level's normal exit. This `DRUNDAR.GOB`
census contains zero `UndeadKnight` records. A native branch snapshot or
factory selection does not prove a playable actor or complete load.

## Resource requests and constructor reference

**Executed:** one representative per nine hostile class strings takes a
derived constructor → `Creature_ctor` 0x109d68 → `GameObject_ctor`
0x14cb10 chain on each seed. `res_find` 0x17365c is recorded with null
returns. The class-definition tables and all listed archive members are
checked against owner inputs. This proves request names/order and archive
presence, not resident handles or model/animation use.

| Class group | Definition / requests per representative |
|---|---|
| Five Orc2 variants | 0x501df8: 45 ordered `orc_vari.lmp` entries (`orc2.vif`, `orc2.tex`, 43 animation entries), then 34 model/texture requests for 17 named parts in `orc_wep2.lmp`; 79 total. |
| Three Goblin variants | 0x500298: 25 ordered `goblin.lmp` model, texture and animation entries, then 14 model/texture requests for seven named parts in `goblin_z.lmp`; 39 total. |
| Ogre | 0x501bf8: 15 `ogre.lmp` model, texture, animation and hammer-part entries. |

The test compares all **527 ordered requests** through these nine chains and
checks 89 definition entries across the hostile, Catapult and firebomb tables.
The Orc part names are `oaxe1`, `obow1`, `ocleever`, `ohook`, `omace`,
`oquiver`, `oscimitar`, `oshield1`–`oshield5`, `ospear`, `osword1`–`osword3`
and `oarrow`. The Goblin parts are `g_arrow`, `g_staff`, `g_bow`, `g_shield`,
`g_axe`, `g_sword1` and `g_sword2`.

**Executed bounded direct requests:** Catapult asks `catapult.lmp` for
`catapult.vif`, `catapult.tex`, `catapult.anm`; `kelethinBomb` asks
`firebomb.lmp` for `firebomb.vif` and `firebomb.tex`; Barrel asks
`barrel.lmp` for `barrel.vif` and `barrel.tex`. Blocker, PushTrigger,
Trigger, Weather, Torch and Firepot made no named direct request with their
lower services stubbed. The named entries' archive presence is asserted.

**Observed property selectors, not executed request lists:** the authored
`lump`/`lumpname` values are `jumpgate`, `catapult`, `we_sldr`, `ammocart`,
`boxafay`, `boxbfay`, `dbridge`, `gobstand`, `leanto` in Strife and
`jumpgate`, `ehubanim`, `uwadoor`, `orkbox`, `uwflag`, `uwswitch` in Drundar.
The test checks each class's selector, but the actual ordered requests for
NPC, Portal, AutoContainer, AutoChest, AutoProp, arena door, Savepoint and
character lights remain **Unknown**. The simple stub returns empty archive
strings for some of their dependent calls; those are not a resource contract.
Sound, cutscene, dialog and particle dependencies also remain outside this
`res_find` probe.

## Scripted objectives, exits, and mission-1 flow

The script test asserts 47 Strife entries/21 imports and 36 Drundar
entries/20 imports, selected addressed calls inside their expected entries,
and per-record NPC, switch, bridge, boss, door and exit links.
These are **Observed static links**. The objective order below is **Inferred**
from those links and manual script inspection. The test does not execute the
script machine, dialog choices, timer/deferred work, collision or cutscene
playback.

**Strife:** `preStart` preloads the bust resource and restores the stage-3
counter. `start` selects which of four scout NPCs is visible according to
stage-complete variables. The four NPC records link to four distinct dialog
entry points. A first-scout dialogue action posts the Orc counter and adds a
quest; later scout actions trigger three named bridges and eventually remove
that quest. Thirteen Orc records (eight Archers, five Soldiers) carry the
stage-1 init/death callbacks; two Shamans carry stage-2 callbacks; the two
Catapults carry the stage-3 death callback. The counters, deferred delays and
three named cutscenes lead from the first group through shamans to two
catapult deaths; `showCatCounter` tests a count of two. The other Orc
placements are not thereby counted as objective targets. One PushTrigger
calls `exitzone`; another and one walk-in Trigger request `blood1`. A second
Trigger calls the first-scout dialog gate. `exitzone`'s non-demo branch
requests `drunarm`. Under `demoRunning`, a deferred counter above 150
calls `grantMission(1)` and requests `hub`. Exact runtime reachability of
each branch is **Unknown**.

**Drundar:** `start` sets values on the named Ogre miniboss and restores
eight persistent pillar states. Eight `uwswitch` records each have a distinct
key/action pair; their actions increment a switch count, set a pillar
variable and start a particle effect. `showSwitchCount` tests for all eight,
then inhibits saving, defers `doorsdelay`, and the `doors` entry requests a
cutscene, clears the inhibit and records the door-seen variable. Four
`arenadoor` records share the `door` name; `UWStair` uses the `stairs` name.
Six walk-in Triggers are linked to two script entries, one for the arena
message/quest and one for `exitzone`. Eight PushTriggers have only a clock
icon, one returns to `blood1`, and four use the eight-switch key and call
`exitzone`. The non-demo exit requests `drunare`. The demo/counter branch
above 150 grants mission 1 and requests `hub`. Actual switch interaction,
door passability, Ogre fight and level transitions remain **Unknown**.

Thus `blood1`'s choice exits do **not** complete mission 1 on entry to
either destination. The scripted ordinary route continues toward
`drunarm` or `drunare`; the explicit `grantMission(1)`/hub calls occur in
the demo branch. The separate hub action making mission 2 available remains
a further step (`t3/research-blood1-scripts` `532f69c`,
`t3/research-quest-log` `03c2304`). A continuous original/native route has
not been verified.

## Ordered native port and verification work

1. Bind the `blood1` keyed exit and arrival marker to ordered Strife or
   Drundar loads, using one shared world/object identity and authored seed.
   Preserve all 553 records, metadata side effects and the propertyless
   Crate's no-object case. Refuse unsupported constructors explicitly.
2. Port the common interaction foundations: Blocker, light/arrival markers,
   Savepoint, Portal, PushTrigger, Trigger, NPC/dialog, Weather, containers,
   chests and property-driven resources. Then port Strife bridges, props,
   Catapult, falling bomb and Drundar switches, stairs and arena doors.
   Verify direct resource handles, collision and save state before using an
   objective link.
3. Port the five Orc2 variants through their shared 0x488 constructor and
   ordered body/weapon requests, with real targeting, event attacks, damage,
   death callbacks and credit. Check the 13 tagged stage-1 rows, two Shaman
   callbacks and two Catapult death callbacks against the script host.
4. Port the three Goblin variants and Ogre through their distinct 0x498 and
   0x468 constructors, attachment requests, AI, damage, drops and miniboss
   state. Keep all 85 authored hostile identities in the actual combat world.
5. Execute and compare scout dialog, counters, three Strife cutscenes, all
   eight Drundar switch actions, deferred door sequence, save inhibit,
   walk-in and use exits on both branches, including save/load. Run a strict
   native `blood1` → destination → arena or demo-hub route and separately
   verify mission completion and mission-2 availability. Do not substitute
   an isolated factory call or fixture fight for this playthrough.

## Verification

Run serially with `PYTHONDONTWRITEBYTECODE=1`:

```sh
python3 tools/difftest_strife_drundar.py local/SLUS_209.73 local/BG/DATA --seed 20973
python3 tools/difftest_strife_drundar.py local/SLUS_209.73 local/BG/DATA --seed 7
python3 tools/difftest_objects.py local/SLUS_209.73 -k load --seed 20973
python3 tools/difftest_objects.py local/SLUS_209.73 -k load --seed 7
python3 -m unittest discover -s tools -p 'test_*.py'
```

**Results:** each seed passed 553 class-counted records / 21,740 consumed
loader bytes, 521 factory selections, 89 class-definition entries, 527
ordered requests through nine hostile constructor chains, nine bounded
direct probes and two static script/exit contracts. The generic object loader
passed 5/5 properties on each seed. The full Python unit suite passed
652/652. All commands used `PYTHONDONTWRITEBYTECODE=1` in one serial
background run. Logs stay in ignored `local/`; this research creates no
pictures. None of these checks proves native combat, scripted objective
reachability, a live cutscene or a level transition.
