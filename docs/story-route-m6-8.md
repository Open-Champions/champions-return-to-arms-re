# Story missions 6, 7 and 8 after the menu request

US `SLUS_209.73` v2.00, branch `t3/research-story-m6-8` (from
`t3/research-story-route-r3` `28b3712`), 2026-11-09. This continues
`docs/story-route.md` §§6–8. It is a function-level trace on constructed
state, not a played campaign, a loader run or a native client result.
`tools/difftest_story_mission68.py` (below, "the test") runs every claim
marked **Executed** at seeds 20973 and 7.

## 0. Evidence boundary

The menu confirm that writes `swamp1`, `swamp2` (missions 6 when
`game_getEvil` is set), `valor` and `fire1` is `docs/story-route.md` §6 and
is not re-run. The hub entries that set mission 6's available bit are §8 of
that file. `dialog_onMsg` is not run on any dialog here. Node selection is
**Inferred** from the condition returns and the first-true rule in
`docs/story-route.md` §1. No loader, arrival, object construction, combat
or item drop is run.

**Harness (Observed / Executed).** Each entry runs through `scr_load`
`0x13e8f8`, `scr_registerNatives` `0x141310` with the native table at
`0x403370`, and `script_runByName` `0x1ed694` (posts:
`script_runPostAction` `0x1edac0`) in `tools/ee_emu.py`. Prepare is
`difftest_story_mission45.prepare`, plus one extra sentinel. Before every run:

- mission bytes on all four records (`g_players` `0x4d8af0` + slot ×
  `0x4c30` + `0x4bbf`) are `0xA0`;
- quest slots are `0x5A`, record 0's quest count is 0 and the other three
  counts are `0x5A5A5A5A`;
- pending level, entrance, orientation and the `newWorldPost` buffer
  `0x4fdcf0` hold `PENDING-SENTINEL`, `ENTRANCE-SENTINEL`, `0x5A` and
  `POSTLEVEL-SENTINEL`;
- one player, difficulty 0, the evil byte (record `+0x4c1a`) as stated, and
  `g_paused` `0x41b4f4` at 0 unless a case sets it.

A variable "stored" below means the test saw a 1-byte write of that value to
that variable's value byte (`require_stored`, via `Run.stored` line 495). A `0x5A` plant means the
variable was set to `0x5A` first, so a stored 0 or 1 is a real write and not
the leftover fill. "Held" means every mission byte 5–9 on all four records
stayed `0xA0` unless the claim names a change (`Run.held`, test line
505). Each native list below is the interpreter's own call sequence:
`emu.calls` targets that are handlers in the `0x403370` table (lines
451–460 and 483–484). It is not inferred from stub hits.

**Stubs.** The responder (`difftest_story_mission45.Quiet`) answers
`inventory_countItemByName` with the count a case names,
`inventory_findItemBySubstring` with "not found", and every other stub with
0. The stubs hit in this file are `text_lookup`, `hud_showHelpMessage`,
`hud_showMessage`, `hud_setBust`, `res_find`, `cut_start`,
`sound_playOnObject`, `sound_setPlaysWhileFrozen`, `lump_load`,
`Camera_update`, `net_isLocalSlot`, `net_closeLocalMenus`, `dialog_isOpen`,
`shop_openOrStock`, `item_parseDescriptor`, `player_itemWeight`,
`inventory_giveItem`, `player_recalcLoad`, `inventory_countItemByName`,
`particle_define`, `dbg_printf` and `save_game`. Each claim names the stubs
it reached. No world objects or player objects are planted. Natives that act
on objects (`hideMonster`, `showMonster`, `autoPropSetState`, `setCFlag`,
`setMonsterVal`, `onePlayerHasItem`, `trigger`) therefore find nothing, and
no visual, monster or bag change is claimed.

**Text ids.** Quest titles and bodies, help ids, info ids and the bust
text are not written here. Each one is read from its script call site and
named by the first ten hex digits of its SHA-256, e.g. `q:d19c4065ff`. The
test pins each id at its site (test lines 47–94 and 257–306) and checks
which sites share a key. The keys themselves are in ignored `local/`.

| Id | Role | Sites |
|---|---|---|
| `q:d19c4065ff` / `q:ad638205f7` | swamp quest title / body | `swamp1`/`swamp2` `0xe0`; title also `dis2` `0xe54` |
| `q:d0882500e8` / `q:8e248adef8` | Bertoxx quest title / body | `dis2` `0x18c`; title also `0x1004` |
| `q:b2b7b8b5f1` | fire quest title | `valor` `0xe7c`, `0x668`, `0x75c`; `fire1` `0xb0` |
| `q:a09d8f2789`, `q:1f0eb138af` | fire quest bodies | `valor` `0xe7c` and `fire1` `0xb0`; `valor` `0x668` |
| `q:d124df7d2f` | storm quest title | `valor` `0xf3c`, `0x89c`, `0xbdc`, `0xd78` |
| `q:4167398c60`, `q:d34aa9dad6` | storm quest bodies | `valor` `0xf3c`; `valor` `0x89c` |
| `q:4ff8a3b5ae` | honor quest title | `valor` `0xc10`, `0xdac`; `honor` `0x1258` |
| `q:1030edc5cb`, `q:537f710378` | honor quest bodies | `valor` `0xc10`; `valor` `0xdac` |
| `h:0125fd7019` + `h:afcd253e53` | trigger-grant help pair | `swamp1` `0x1f4`, `valor` `0x1880` |
| `h:0125fd7019` + `h:f401646fec` | `obsfor1` grant help | `obsfor1` `0x158` |
| `h:a0df82f764` + `h:0efe320d7b` / `+ h:5d38865288` | dis2 portal help | `dis2` `0xf58` / `0x1280` |
| `h:65a1721c33` + `h:de988ded64` | dis2 shard help | `dis2` `0x1144` |
| `h:0d52ad7552` + `h:4169aeb71b` | honor grant help | `honor` `0x1200` |
| `h:6d5f292589` + `h:ec992006f4` | fire5 grant help | `fire5` `0x52c` |
| `i:9f656ce178`, `i:e997dd831a`, `i:b60324e54d` | bust text, valve info, portal info | `dis2` `0xc90`; `fire3` `0x8c`/`0x130`; `fire5` `0x76c` |

Script offsets are code offsets in each level's `script.scr`, as in
`docs/story-route.md`.

## 1. Mission 6: swamp1 or swamp2, then dis2 (act 5)

### How it starts

**Observed / Executed.** `swamp1` `start` (`0x44`) and `swamp2` `start`
(`0x44`) run the same three steps:

1. `getMissionComplete(6)` at `0x70`. If that returns 0, `getEvil()` runs,
   and only a non-evil player gets `addQuest` at `0xe0` (`q:d19c4065ff`,
   `q:ad638205f7`).
2. `setMissionAvailable(6, 1)` at `0x114`.
3. `setv startedMission6 1` at `0x148` and `setv currentMission 6` at
   `0x17c`.

From `0xA0`, record 0's mission-6 byte becomes `0xA1`; from `0xA2` it
becomes `0xA3`, and in that case neither `getEvil` nor `addQuest` runs.
Records 1–3 and missions 5, 7, 8 and 9 are held. Both variables are stored
over `0x5A`. With `0xA0`, the recorded natives are
`getMissionComplete, getEvil, addQuest, setMissionAvailable, setv, setv`
(not evil) or the same list without `addQuest` (evil). No stub runs. There
is no post, no deferred call, no cut and no request. All eight
(level × evil × prior-byte) cases run at both seeds. Evidence: test lines
588–622; sites lines 183–191.

**Observed / Executed.** Both swamps' `newWorldda5d` (`0x0`) requests
`dis2`, which is the pool string at offset 0. Orientation becomes `0xff`,
and the entrance sentinel and mission bytes are held. The natives are
`newWorld`, and the one stub is `net_closeLocalMenus(0)`, which returns 0.
Each swamp has five PushTriggers with `action=newWorldda5d` and one
rectangle Trigger `t=newWorldda5d`. Evidence: lines 573–586, 623, 340–350.

**Observed / Executed, unlinked.** `swamp1` `steppedOnTrigger` (`0x194`)
calls `grantMission(6)` at `0x1c0` and `addHelpMessage` at `0x1f4`
(`h:0125fd7019`, `h:afcd253e53`). All four records go from `0xA0` to
`0xA2`, and record 0 goes from `0xA1` to `0xA3`. The stubs are two
`text_lookup` calls and `hud_showHelpMessage(-1, 0, 0)`. Both lookups return
0, so the help gets empty text. No object property in `swamp1` names this
entry, and `swamp2` has no such entry. Evidence: lines 624–634, 349–352.

### dis2 opening

**Observed / Executed.** `prestart` (`0x37c`) calls
`preloadResource(bust.lmp)`, which reaches the `lump_load` stub and gets 0.
It then copies `getv(dis_portalCount)` into script local `0xe0`, the portal
counter, so the count carries across visits through the quest variable.
`start` (`0x444`) posts `absorb` at `0x51c` only when the player is not
evil and `dis_sawScene` is 0. On a fresh good start, the natives are 6
calls, 9 `hideMonster`, then `getv, getEvil, getv` (test line 636). It
creates `dis_portalCount`, `dis_sawScene` and `dis_activatedAllPortals` at
0, and those stores are recorded.

The posted `absorb` (`0x934`) calls `cutScene(dis)` at `0x960` and posts
`initLevel` at `0x98c`. Its stubs are `res_find(.lmp, dis.cut)` and
`cut_start(0, dis.cut)`, both returning 0. This is the request, not a
played cut. `initLevel` (`0x9a4`) stores `dis_sawScene` 1 at `0xa30` and
defers `everyFrame` at `0xa5c`.

On later starts:

| Player | Variables | Result |
|---|---|---|
| evil | `dis_sawScene` absent | no post, no deferred call |
| good | `dis_sawScene` 1 | defers `everyFrame` |
| evil | `dis_sawScene` 1, not talked | no deferred call |
| evil | `dis_sawScene` 1, `dis_talkedToBertoxx` 1 | defers `everyFrame` |

Evidence: lines 640–697.

### Good path: eight portals

**Observed.** The eight `disportGOOD` objects carry
`action1=callScrief4c`, which calls `portalTrig`. The eight `disportEVIL`
objects carry `action1` portInit wrappers that call
`autoPropSetState(evilportalX, …)` and then `portalTrig`. `portalTrig`
(`0xd38`) increments local `0xe0` and calls no native. Evidence: lines
353–364; wrapper natives are checked in `portal_hits`, lines 699–708.

**Observed / Executed.** After `prestart` and N wrapper calls, one
`everyFrame` (`0xa74`) stores `dis_portalCount` = N at `0xae8`.

- **N = 7:** it re-defers itself, stores nothing else and grants nothing.
  For a good player with `dis_sawScene` set, or an evil player who has
  talked, it calls `showBust` with `bust_portal.tex`, `i:9f656ce178` and
  8 − N. The stubs are `text_lookup` and
  `hud_setBust(bust_portal.tex, 0, 1, -1)`.
- **N = 8, good player:** it stores `dis_activatedAllPortals` 1 at `0xb40`,
  calls `gotAllPortals` (`0xd64`) at `0xb6c`, and does not re-defer itself.
  `gotAllPortals` then runs in this order:
  1. defers `pause` at `0xdc0`;
  2. `givePlayerItem(shardofdisease, 0, 0)` at `0xdfc`. This reaches the
     stubs `item_parseDescriptor`, `player_itemWeight(0)`,
     `inventory_giveItem(0, 1)` and `player_recalcLoad(0)`, all returning
     0. It is the give request, not a bag change.
  3. `grantMission(6)` at `0xe28`: all four records `0xA2`;
  4. `removeQuest(q:d19c4065ff)` at `0xe54`: the planted swamp quest
     becomes `NoQuests` and the count 0;
  5. four `onePlayerHasItem` calls. No player object is planted, so they
     find nothing and nothing is removed.
- **N = 8, evil player:** it stores `dis_activatedAllPortals` 1. The only
  call in `gotAllPortals` is `addHelpMessage` at `0xf58`
  (`h:a0df82f764`, `h:0efe320d7b`). There is no grant and no deferred call,
  and the planted Bertoxx quest stays.

Evidence: lines 710–767; native lists lines 733–760.

**Observed / Executed.** The deferred `pause` (`0x1190`) counts unpaused
calls in local `0xe8`. On the 61st unpaused call it calls `addHelpMessage`
at `0x1280` (`h:a0df82f764`, `h:5d38865288`) and queues itself again. On
the 92nd it calls `receivedShard` and stops queueing. `receivedShard`
shows the help at `0x1144` (`h:65a1721c33`, `h:de988ded64`) and calls
`soundSequence(fx.lmp, quest_complete.anm)`. Its sound stubs are `res_find`
(which returns 0, so `sound_playOnObject` gets resource 0) and
`sound_setPlaysWhileFrozen`.

A paused call after an unpaused one queues `pause` again and counts nothing.
After `prestart` clears local `0xf0`, a paused *first* call does not queue
`pause` again, so the chain stops there. Evidence: lines 769–807.

### Evil path: Bertoxx

**Observed.** NPC record `bertoxx` has `dialogscript=startDiaae3c` and
`exclamation=returnaf44`. `bertoxx.dbin` has five nodes:

| Node | Condition | Choice action | Target |
|---|---|---|---|
| 0 | `ifd05` | none | 1 |
| 1 | `ifd05` | none | 2 |
| 2 | `ifcb59` | `setv7c05` | close |
| 3 | `if2de9` | `setv7df7` | close |
| 4 | `if41a3` | none | close |

Rectangle Trigger `t=if18fc` and `t=if69ee` are the only `t=` triggers.
Evidence: lines 353–386.

**Observed / Executed.** Condition returns:

- `ifd05` returns 1 when `dis_talkedToBertoxx` is absent, and 0 when it is
  1 or `0x5A`.
- `ifcb59` returns 1 while `dis_activatedAllPortals` is absent, and 0 when
  it is 1.
- `if2de9` returns 1 only when the player has talked, all portals are
  activated and `dis_finishedQuest` is unset.
- `if41a3` returns `dis_finishedQuest`.
- The exclamation `returnaf44` returns the negation of
  `dis_talkedToBertoxx`.

`if18fc` calls `startDialog(bertoxx, 1, 0)` at `0x21b4` only for an evil
player who has not talked. That reaches the stubs `lump_load(.lmp)`,
`Camera_update(0)` and `net_isLocalSlot(0)`. `lump_load` returns 0, so no
dialog file is loaded here. A good player only runs `getEvil`. Evidence:
lines 809–846.

**Observed / Executed.** `setv7c05` (`0xf8`) stores `dis_talkedToBertoxx` 1
over `0x5A`, defers `everyFrame`, and adds `q:d0882500e8` /
`q:8e248adef8`. It does not change mission bytes.

`setv7df7` (`0x28c`) stores `dis_finishedQuest` 1 over `0x5A` and calls
`talkedToBert` (`0xf70`). That runs the same give stubs as above, then:

- `grantMission(6)` at `0xfd8`: all four records `0xA2`, or `0xA3` on
  record 0 from `0xA1`;
- `removeQuest(q:d0882500e8)` at `0x1004`, which leaves `NoQuests`;
- four `onePlayerHasItem` calls, which find nothing;
- `receivedShard`, with the help and sound stubs above.

The seed is unchanged. Evidence: lines 847–873.

**Inferred, not run.** For an evil player, the first-true rule opens node 0
before the talk. The unconditional choices lead to node 2, and node 2's
action records the talk and adds the Bertoxx quest. After the eighth portal,
node 3 is the first true condition, and its action grants. A good player
gets the grant from the eighth portal and does not need Bertoxx.

### dis2 exits

**Observed / Executed.** Each request stores orientation `0xff` and
reaches `net_closeLocalMenus(0)`, which returns 0. Mission bytes are held.

| Entry | Linked from | Pending | Entrance |
|---|---|---|---|
| `setEntra9e0f` | PushTrigger | `arachna1` | `left` |
| `setEntrae2b1` | PushTrigger | `arachna1` | `right` |
| `newWorld3914` | four PushTriggers `name=goodexit` | `swamp1` | sentinel |
| `newWorld5a4f` | four PushTriggers `name=evilexit` | `swamp2` | sentinel |
| `if69ee` | Trigger | `swamp2` if evil, else `swamp1` | sentinel |

Evidence: lines 875–894, 365–372.

### What makes mission 7 available

**Observed / Executed.** `ifcceb` returns 1 while mission 7's available bit
is clear (`0xA0`) and 0 once it is set (`0xA1`). It does not test mission
6's completion. The `hub` and `hub2` entries `setMissi26bc`, `setMissi167`
and `setMissib9fb` each set record 0's mission-7 byte to `0xA1`. Records
1–3 and the other watched missions are held, and no quest is added.
`setMissi167` and `setMissib9fb` also call `changeSwoop` and
`activateStore`. That reaches the stubs `dialog_isOpen` and
`shop_openOrStock`, both returning 0, so no shop opens.

The dialog rows that name these entries are:

- `firiona.dbin` node 19: `ifcceb`; `setMissi26bc`, `setMissib9fb`;
- `firiona_bak.dbin` node 18: `ifcceb`; `setMissi26bc`, `setMissi167`;
- `natasla.dbin` node 14: `ifcceb`; `setMissi26bc`, `setMissib9fb`;
- `natasla_bak.dbin` node 15: `ifcceb`; `setMissi26bc`, `setMissi167`.

Granting mission 6 (all three writers) does not set mission 7's bit.
Evidence: lines 896–920, 431–440. Across all 119 level scripts, these six
hub entries and `valor` `start` are the only mission-7 availability writers
(lines 1389–1450).

## 2. Mission 7: valor, then valor2 and honor (act 6)

### How it starts

**Observed / Executed.** `valor` `start` (`0xdc4`):

1. If mission 8 is available and not complete, it adds the fire quest at
   `0xe7c` (`q:b2b7b8b5f1`, `q:a09d8f2789`). Otherwise, if mission 9 is
   available and not complete, it adds the storm quest at `0xf3c`
   (`q:d124df7d2f`, `q:4167398c60`).
2. `setMissionAvailable(7, 1)` at `0xf70`.
3. Stores `startedMission7` 1 at `0xfa4` and `currentMission` 7 at
   `0xfd8`, both over `0x5A`.
4. On a first visit, stores `numberOfWaves` 1 and `skelPopulation` 0 (over
   `0x5A`), and defers `checkperiodicSpawn` at `0x1290`.
5. Posts `absorb` at `0x12f4` while `sawValor` is 0. The read creates
   `sawValor` at 0, and that store is recorded.

Fresh, record 0's mission-7 byte becomes `0xA1`, no quest is added, no stub
runs, and the 24-call native list is pinned (line 922). With mission 8 at
`0xA1` the fire quest is added. With mission 8 at `0xA3` and mission 9 at
`0xA1`, the storm quest is added. With both at `0xA3`, or mission 8 at
`0xA2`, nothing is added. With `sawValor` 1, nothing is posted.

The posted `absorb` calls `valorIntro`. While mission 8 is not complete,
that calls `cutScene(valor)` at `0x17d4` (stubs `res_find(.lmp, valor.cut)`
and `cut_start`, both returning 0) and stores `sawValor` 1 at `0x1808`.
Once mission 8 is complete it calls neither, and a planted `0x5A` stays.
Evidence: lines 930–988.

**Observed / Executed, unlinked.** `valor` `steppedOnTrigger` (`0x1820`)
grants mission 7 on all four records at `0x184c` and requests the
`h:0125fd7019` / `h:afcd253e53` help at `0x1880`, with the same stubs as in
swamp1. No object property in `valor` names it. Evidence: lines 989–997,
395.

### Matt Marr

**Observed.** `MattMarr` (`name=mattmar`) has `dialogscript=startDiaff8`.
That calls `startDialog(mattmar, 1, 0)` at `0x25c`, which reaches the same
three dialog stubs, with `lump_load` returning 0. `mattmar.dbin`:

| Node | Condition | Choice action | Target |
|---|---|---|---|
| 0 | `if2a2e` | `setMissi1bb4` | 1 |
| 1 | `if84f0` | `setv6151` | close |
| 2 | `ifa054` | `setMissie47a` | 3 |
| 3 | `if7275` | `setv3d8c` | close |
| 4 | `ife995` | `setv7ac2` | 5 |
| 5 | `if4ffe` | `newWorldf844`; a second choice with no action | close |
| 6 | `if550a` | `newWorld511b` | close |

Evidence: lines 384–409.

**Observed / Executed.** The seven condition returns, by state (byte 8,
byte 9, `MarrDone`, evil):

| State | Returns, nodes 0–6 | First true |
|---|---|---|
| `A0`, `A0`, –, good | 1 0 1 0 0 0 0 | 0 |
| `A1`, `A0`, –, good | 0 1 1 0 0 0 0 | 1 |
| `A3`, `A0`, –, good | 0 0 1 0 0 0 0 | 2 |
| `A3`, `A1`, –, good | 0 0 0 1 0 0 0 | 3 |
| `A3`, `A3`, –, good | 0 0 0 0 1 0 0 | 4 |
| `A3`, `A3`, 1, good | 0 0 0 0 0 1 0 | 5 |
| `A3`, `A3`, –/1, evil | 0 0 0 0 0 0 1 | 6 |

The "First true" column is **Inferred**: the selector was not run.
Evidence: lines 1002–1025.

**Observed / Executed.** The choice actions:

- `setMissi1bb4` (`0x4f4`): `setMissionAvailable(8, 1)` at `0x528`; record
  0 becomes `0xA1`.
- `setv6151` (`0x600`): stores `mar_fire` 1 over `0x5A` and adds
  `q:b2b7b8b5f1` / `q:1f0eb138af` at `0x668`. If that title is already in
  the log, the count stays 1 and the earlier body stays.
- `setMissie47a` (`0x6fc`): `setMissionAvailable(9, 1)` at `0x730`, and
  removes the fire quest at `0x75c`, which leaves `NoQuests`.
- `setv3d8c` (`0x834`): stores `mar_storm` 1 and adds `q:d124df7d2f` /
  `q:d34aa9dad6`.
- `setv7ac2`: stores `MarrDone` 1.
- `newWorldf844` (good) and `newWorld511b` (evil):
  - `newWorldPost(valor2)` copies `valor2` into `0x4fdcf0`. The pending
    level and orientation sentinels stay.
  - Each removes the storm quest and adds the honor quest `q:4ff8a3b5ae`,
    with body `q:1030edc5cb` (good) or `q:537f710378` (evil).

No action stubs. The dialog-end handler that would act on `0x4fdcf0`
(`docs/spec/script-builtins.md` line 366) was not run. Evidence: lines
1026–1081.

### Doors and the gate

**Observed / Executed.**

- **`tofire` and `tostorm`.** Both PushTriggers use `key=return4520` and
  `action=callScrib1e7`. The key returns 1 when `mar_fire` or `mar_storm` is
  nonzero. The action calls `marrPortal`, which requests `fire1` at
  `0x22a4` when `mar_fire` is set and then `storm1` at `0x2304` when
  `mar_storm` is set. With both set, two `newWorld` calls run and `storm1`
  is left pending. With neither, nothing is requested. Each `newWorld`
  stores orientation `0xff` and reaches `net_closeLocalMenus(0)`. The
  entrance sentinel stays.
- **`tovalor`.** Its key, `return25eb`, returns 0 and calls no native.
- **The gate.** The rectangle Trigger `t=callScri1ef1` calls
  `gatewaytrigger`. When `mar_fire` or `mar_storm` is set and `gateon` is
  not, it calls `trigger(portal, 0)` at `0x21ac` and stores `gateon` 1. No
  object named `portal` is planted, so no virtual call is made. The guarded
  request with a planted portal is `docs/story-route.md` §2's hub case, not
  this level. With `gateon` 1, no trigger runs.

Evidence: lines 1083–1124, 388–397.

### How mission 7 is marked complete

**Observed / Executed.** `valor2`'s only PushTrigger runs `newWorld6440`,
which requests `honor`. `honor`'s exit `newWorlda6a0` requests `valor2`.
Both store orientation `0xff` and leave the entrance sentinel. Evidence:
lines 1129–1131.

**Observed / Executed.** `honor` `start` (`0x2f8`) calls `setParticle`,
whose stub is `particle_define` (returns 0). It defers `particleEffects`
and stores `playerHasItem(shardofvalor)` in local `0xe4`, using the
`inventory_countItemByName` stub. `shardCheck` (`0x1120`) runs as follows:

- On entry, if the counter (local `0xe0`) is 25, it resets the counter and
  compares the current count with local `0xe4`.
- If the count has grown, it requests help at `0x1200` (`h:0d52ad7552`,
  `h:4169aeb71b`), calls `grantMission(7)` at `0x122c`, removes the honor
  quest at `0x1258`, and calls the sound.
- Last, it calls `gamePaused`, and adds 1 to the counter when that returns
  0.

In the test:

- With the count stub 0 at `start` and for 25 calls, there is no grant and
  each call's only native is `gamePaused`.
- The 26th call, with the stub at 1, grants. All four records become
  `0xA2` (record 0 becomes `0xA3` from `0xA1`), and the planted honor
  quest becomes `NoQuests`.
- With the same count at `start` and at the check (1 and 1), nothing is
  granted and the quest stays.
- One paused call moves the grant to the 27th call.

This file calls `shardCheck` directly. In play, the caller is
`particleEffects` at `0xc44`, which was not run. The count is the stub's
return for one player, not a real bag. Evidence: lines 1126–1184.

**Inferred from the condition returns and node order.** The honor quest
and the `valor2` post come only from nodes 5 and 6, and those require
mission 9 available and complete. On this route, mission 7 is completed
after missions 8 and 9. The grant needs a shard-of-valor count that grows
after `honor` `start`.

### What makes mission 8 available

**Observed / Executed.** Matt Marr's node-0 action `setMissi1bb4`; the
`fire1` and `obsfor1` `start` entries (section 3). No hub or hub2 entry
writes mission 8. Granting mission 7 does not set mission 8's bit.
Evidence: lines 1389–1450, 1028–1033, 1126–1158.

## 3. Mission 8: fire1 through fire5 (act 7)

### How it starts

**Observed / Executed.** `fire1` `start` (`0x44`):

1. `getMissionComplete(8)` at `0x70`.
2. If that is 0, it adds `q:b2b7b8b5f1` / `q:a09d8f2789` at `0xb0`. This
   is the same title and body as `valor` `start` at `0xe7c`.
3. `setMissionAvailable(8, 1)` at `0xe4`.
4. Stores `startedMission8` 1 at `0x118` and `currentMission` 8 at
   `0x14c`, over `0x5A`.

From `0xA0` or `0xA1`, record 0 becomes `0xA1` and the quest is added. From
`0xA3`, no quest is added. If Matt Marr's fire quest (same title, body
`q:1f0eb138af`) is already in the log, the count stays 1 and its body is
kept. There is no post, cut or stub. Evidence: lines 1186–1215.

### Travel and the fire3 valves

**Observed / Executed.** Each entry below stores orientation `0xff` and
reaches `net_closeLocalMenus(0)`, which returns 0. The natives are
`newWorld`, or `setEntrance, newWorld` where an entrance is named. Mission
bytes are held.

| Level | Entry | Pending | Entrance |
|---|---|---|---|
| `fire1` | `newWorlda6b0` | `fire2` | sentinel |
| `fire2` | `newWorld5cd` | `fire3` | sentinel |
| `fire2` | `newWorldaaf1` | `fire1` | sentinel |
| `fire3` | `setEntrabca8` | `fire4` | `centerladder` |
| `fire3` | `setEntra5ac0` | `fire4` | `eastladder` |
| `fire3` | `setEntra1124` | `fire4` | `westladder` |
| `fire3` | `setEntraf090` | `fire4` | `southladder` |
| `fire3` | `newWorlda6b0` | `fire2` | sentinel |
| `fire4` | `setEntraf725` | `fire3` | `southladder` |
| `fire4` | `setEntraf555` | `fire3` | `westladder` |
| `fire4` | `setEntra3624` | `fire3` | `eastladder` |
| `fire4` | `setEntraa02b` | `fire3` | `centerladder` |
| `fire4` | `newWorld9251` | `fire5` | sentinel |

Only the `fire3` center ladder (`setEntrabca8`) has a key, `return7da1`.
That key returns 1 only when `switch1done` and `switch2done` are both 1. The
two `pipevalveswitch` actions `hideMons7bb4` and `hideMonsc5f1` each run
`hideMonster`, store `switch1done` or `switch2done` 1 over `0x5A`, and call
`setInfo` (`i:e997dd831a`). The `setInfo` stubs are `text_lookup` and
`hud_showMessage(0, 180, -1, 0)`. Evidence: lines 1217–1257, 426–430.

### fire5: dragon, shard and completion

**Observed / Executed.** `fire5` `start` (`0xd0`):

- stores `playerHasItem(shardoffire)` in local `0x30` (count stub);
- defers `shardCheck` at `0x144`;
- calls `setSaveInhibit(1)` at `0x1a8` only while `killedDragon` is 0,
  creating it at 0;
- always posts `absorb` at `0x1d4`.

`absorb`, while `fire_sawDragon` is 0:

1. `cutScene(dragon)` at `0x250`, with the cut stubs;
2. stores `fire_sawDragon` 1 at `0x284`;
3. posts `firsaved`.

`firsaved` calls `saveCheckPoint`, whose stubs are `dbg_printf` and
`save_game(0, 0, 1)`. `save_game` returns 0, so nothing is saved. It then
calls `setminiboss`, which runs `setCFlag` and three `setMonsterVal` on
`reddragon`. No object is planted. With `fire_sawDragon` 1, `absorb` goes
straight to `setminiboss`.

The `reddragon` record has `dropitem=shardoffire` and
`deathscript=callScri3971`. That calls `deadDragon`, which stores
`killedDragon` 1 over `0x5A` and calls `setSaveInhibit(0)`. Evidence: lines
1259–1305, 1338–1345, 414–418.

**Observed / Executed.** `shardCheck` (`0x46c`) adds 1 to local `0x2c` on
every call, with no pause test.

- On the 25th call it resets the counter and compares the current count
  with local `0x30`. If the count has grown, it:
  1. requests help at `0x52c` (`h:6d5f292589`, `h:ec992006f4`);
  2. stores `fire_gotShard` 1 at `0x560`;
  3. calls `grantMission(8)` at `0x58c`;
  4. calls the sound;
  5. runs the `onePlayerHasItem` loop;
  6. does not queue itself again.
- Otherwise it queues itself.

In the test, with the stub 0 at `start` and 1 afterwards, calls 1–24 only
defer, and the 25th grants: all four records `0xA2` (record 0 `0xA3` from
`0xA1`), and `fire_gotShard` stored over `0x5A`. With `g_paused` 1 on every
call it grants on the 25th call too. The planted fire quest is **not**
removed. With the count equal at `start` and at the check, there is no
grant and the entry queues itself. Evidence: lines 1306–1337.

**Observed / Executed.** The jump-gate `Portal` record (`lump=jumpgate`,
`script=return2c8d`) has a script that returns 1 only when `fire_gotShard`
is 1. It returns 0 when the variable is absent or `0x5A`. The Trigger
`t=callScricb6b` calls `portalMessage`, which calls `setInfo`
(`i:b60324e54d`) until the shard variable is set. The gate's destination
belongs to the jump-gate system and was not run. Evidence: lines 1346–1361,
419–420.

**Observed / Executed.** `obsfor1` `start` repeats mission 8's availability
and the two `setv`s, with no quest. Its only Trigger, `t=callScri7351`,
calls `steppedOnTrigger`, which grants mission 8 on all four records and
requests the `h:0125fd7019` / `h:f401646fec` help. It is a second
completion writer, like the `water1` and `islcave1` triggers in
`docs/story-route.md` §§7–8. Evidence: lines 1366–1385.

### What makes mission 9 available

**Observed / Executed.** Matt Marr's node-2 action `setMissie47a` sets
mission 9's bit and removes the fire quest. **Observed, not run:**
`storm1` `start` calls `setMissionAvailable(9, 1)` at `0x24c`. The
mission-8 grant does not set mission 9. No hub entry writes mission 9.
Evidence: lines 1046–1052, 1389–1450.

## 4. What the client can implement from this

1. **Mission 6 start.** After the menu writes `swamp1` (or `swamp2` when
   evil), run that level's `start`:
   - Set mission 6 available on record 0, and store `startedMission6` and
     `currentMission` 6.
   - Add the swamp quest (`q:d19c4065ff`) only when mission 6 is not yet
     complete and the player is not evil.
   - Do not grant there, and do not post a cut.
2. **Swamp exits.** Every swamp exit object (`newWorldda5d`) requests
   `dis2` with orientation `0xff` and the entrance left unchanged.
3. **dis2 opening.** `prestart` restores the portal counter from
   `dis_portalCount`. A good player's first `start` posts the `dis`
   cutscene request, then `initLevel`, which sets `dis_sawScene` and starts
   the `everyFrame` loop. Evil players get no cut. Their loop starts only
   after they have talked to Bertoxx.
4. **Portals.** Each portal use adds one to the counter. `everyFrame`
   saves the counter to `dis_portalCount` and shows the portal bust with
   the remaining count.
5. **Good-player grant.** On the eighth portal, a good player gets the
   whole `gotAllPortals` list:
   - mission 6 complete on all four records;
   - the swamp quest removed;
   - the shard give request (the item stubs ran; do not claim a bag
     change);
   - the deferred `pause` chain, with help on unpaused tick 61 and the
     shard help and sound on tick 92;
   - do not start that chain if the game is paused on its first tick.
6. **Evil players.** On the eighth portal, an evil player gets only the
   portal help and must return to Bertoxx:
   - The level Trigger `if18fc` forces the Bertoxx dialog until the
     player has talked.
   - The node-2 action `setv7c05` stores the talk and adds the Bertoxx
     quest.
   - The node-3 action `setv7df7` stores `dis_finishedQuest` and grants
     mission 6, removes the Bertoxx quest, and requests the shard give,
     help and sound.
   - The node choice is inferred; `dialog_onMsg` was not run.
7. **Second mission-6 writer.** `swamp1` `steppedOnTrigger` grants mission
   6, but no object links it. Do not wire it to an object without evidence.
8. **dis2 exits.**
   - `goodexit` requests `swamp1`, `evilexit` requests `swamp2`, and the
     `if69ee` Trigger chooses by the evil flag.
   - The two `arachna1` exits use entrances `left` and `right`.
   - None of them is a completion.
9. **Mission 7 availability.**
   - Use hub `setMissi26bc`, `setMissi167` and `setMissib9fb` and their
     hub2 copies.
   - Their dialog condition `ifcceb` only checks that mission 7 is not yet
     available.
   - `setMissi167` and `setMissib9fb` also request the store; the shop
     callees were stubbed.
   - Do not set mission 7 from any mission-6 grant.
10. **Mission 7 start.** After the menu writes `valor`, `valor` `start`:
    - sets mission 7 available and stores `startedMission7` /
      `currentMission`;
    - starts the skeleton waves and defers `checkperiodicSpawn`;
    - adds the fire quest while mission 8 is open, or the storm quest while
      mission 9 is open;
    - posts `absorb` once. That requests the `valor` cutscene and stores
      `sawValor` only while mission 8 is incomplete.
11. **Matt Marr.** Drive Matt Marr from the seven conditions in the table:
    - Node 0 makes mission 8 available, and node 1 stores `mar_fire` and
      adds the fire quest.
    - Node 2 makes mission 9 available and removes the fire quest, and
      node 3 stores `mar_storm` and adds the storm quest.
    - Node 4 stores `MarrDone`.
    - Node 5 (good) or 6 (evil) posts `valor2` through `0x4fdcf0`, removes
      the storm quest and adds the honor quest.
    - An `addQuest` whose title is already in the log keeps the old entry.
12. **Valor doors.** `tofire`/`tostorm` open once `mar_fire` or
    `mar_storm` is set and request `fire1` or `storm1`; `storm1` wins when
    both are set. `tovalor` stays locked. The gate Trigger makes one
    `trigger(portal, 0)` request and stores `gateon`. The Portal's virtual
    method was not run here.
13. **Mission 7 completion.** Complete mission 7 in `honor`:
    - When `shardCheck` sees the counter at 25 and the shard-of-valor count
      above the count read at `honor` `start`, grant on all four records,
      remove the honor quest, and request the help and sound.
    - Paused calls do not advance the counter.
    - The count was a stub. `particleEffects`, which calls `shardCheck` in
      play, was not run.
    - `valor` `steppedOnTrigger` is a second, unlinked writer.
14. **Mission 8 start.** After the menu, or `valor`'s door, writes `fire1`:
    - `fire1` `start` makes mission 8 available and stores
      `startedMission8` / `currentMission`.
    - It adds the fire quest only if mission 8 is not complete; a matching
      title from Matt Marr is kept as is.
    - Follow the travel table for `fire1` → `fire5`. Keep the `fire3`
      center ladder locked until both valves have stored their switch
      variables.
15. **fire5 opening.**
    - `start` reads the fire-shard count and starts the `shardCheck` loop.
    - It inhibits saving until `killedDragon` is set.
    - Posting `absorb` requests the `dragon` cutscene once, then
      `firsaved` (checkpoint save request; `save_game` was stubbed) and the
      miniboss values.
    - The dragon's death script stores `killedDragon` and lifts the save
      inhibit.
16. **Mission 8 completion.**
    - Grant mission 8 on the 25th `shardCheck` call when the fire-shard
      count is higher than at `start`, paused or not.
    - Store `fire_gotShard`, request the help and sound, and stop the
      loop.
    - Leave the fire quest in the log; Matt Marr's node 2 removes it.
    - The fire5 jump gate's script opens once `fire_gotShard` is 1.
    - `obsfor1` is a second grant writer.
17. **Mission 9 availability.** Make mission 9 available from Matt Marr
    node 2 (and `storm1` `start`), not from the mission-8 grant.
18. **Writer list.** The test's all-archive writer set (lines 1389–1450)
    is the complete list of mission 6–9 availability and grant sites. Do
    not add other writers.

## 5. Commands and results

Run on the Mac mini with the owner's `SLUS_209.73` (SHA-256 pinned in the
test) and the read-only disc data folder:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["difftest_story_mission68.py","--elf","local/SLUS_209.73","--data","/path/to/BG/DATA"]; runpy.run_path("tools/difftest_story_mission68.py", run_name="__main__")'
```

Both seeds: 256 checks each, 0 failed (`PASS seed 20973: 256 mission-6/7/8
checks`, `PASS seed 7: 256 mission-6/7/8 checks`). The PASS log from after
the final code edit is kept in ignored `local/story-m68.log`. The earlier
story difftests and the unit suite results are in `work/cursor-report.md`.

## 6. Unknown

- The loader and arrival after each pending write.
- Which object use reaches the dis2 portals, Bertoxx, Matt Marr, the valor
  doors and the fire3 valves, and `dialog_onMsg` on `bertoxx.dbin` and
  `mattmar.dbin`.
- Which hub dialog node play selects to reach `ifcceb` after mission 6.
- `particleEffects` and the honor sarcophagus and ring entries that lead to
  the shard of valor.
- A real shard count or give in place of the inventory stubs.
- The rendered effect of `trigger(portal, 0)` and of the jump gates in
  `honor` and `fire5`.
- `checkperiodicSpawn`, the skeleton waves and the excal sword entries
  (`swordKeyCheck`, `receiveSword`); the sword entries touched no mission
  byte in an exploratory run that is not part of the test.
- `storm1`, `storm2` and mission 9 beyond the sites named above.
- `swamp1` and `valor` `steppedOnTrigger` reached by any object.
- A continuous session from the menu through any of these grants.
