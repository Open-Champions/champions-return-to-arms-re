# Story missions 6, 7 and 8 after the menu request

US `SLUS_209.73` v2.00, branch `t3/research-story-m6-8` (rebased onto
`t3/research-story-route-r3` `3c7987c`), 2026-11-09. This continues
`docs/story-route.md` §§6–8. It is a function-level trace on constructed
state. It is not a played campaign, a loader run or a native client result.
`tools/difftest_story_mission68.py` (below, "the test") runs every claim
marked **Executed** at seeds 20973 and 7. Evidence is named by test
function or table (`check_…`, `SITES`, `ENTRIES`, `TEXT`, `WRITERS`,
`REACH`), not by line number.

## 0. Evidence boundary

The menu confirm that writes `swamp1`, `swamp2` (mission 6 when
`game_getEvil` is set), `valor` and `fire1` is `docs/story-route.md` §6 and
is not re-run here. The hub entries that set mission 6's available bit are
§8 of that file. `dialog_onMsg` is not run on any dialog here. Node
selection is **Inferred** from the condition returns and the first-true rule
in `docs/story-route.md` §1 (`ref_story_route.dialog_start_node`). No
loader, arrival, object construction, combat or item drop is run.

**Harness (Observed / Executed).** Each entry runs through `scr_load`
`0x13e8f8`, `scr_registerNatives` `0x141310` with the native table at
`0x403370`, and `script_runByName` `0x1ed694` (posts:
`script_runPostAction` `0x1edac0`) in `tools/ee_emu.py`. Prepare is
`difftest_story_mission45.prepare` plus one extra sentinel. Before every
run:

- the mission bytes on all four records (`g_players` `0x4d8af0` + slot ×
  `0x4c30` + `0x4bbf`) are `0xA0`;
- the quest slots are `0x5A`, record 0's quest count is 0, and the other
  three counts are `0x5A5A5A5A`;
- the pending level, entrance, orientation and the `newWorldPost` buffer
  `0x4fdcf0` hold `PENDING-SENTINEL`, `ENTRANCE-SENTINEL`, `0x5A` and
  `POSTLEVEL-SENTINEL`;
- there is one player at difficulty 0, the evil byte (record `+0x4c1a`) is
  as stated, and `g_paused` `0x41b4f4` is 0 unless a case sets it.

A variable "stored" below means the test saw a 1-byte write of that value to
that variable's value byte (`Run.stored`, via `require_stored`). A `0x5A`
plant means the variable was set to `0x5A` first, so a stored 0 or 1 is a
real write and not the leftover fill. "Held" means every mission byte 5–9 on
all four records stayed `0xA0` unless the claim names a change (`Run.held`).
Each native list below is the interpreter's own call sequence: the
`emu.calls` targets that are handlers in the `0x403370` table
(`Run.__init__`, `Run.natives`). It is not inferred from stub hits.

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
test pins each id at its site (`TEXT`, `check_sites`) and checks which sites
share a key. The keys themselves are in ignored `local/`.
`check_text_untracked` reads every tracked file (`git ls-files`) and fails
if any file holds one of the keys, or a word whose SHA-256 prefix is one
of the ids. So no id here can be decoded from another tracked file.

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
| `i:9f656ce178`, `i:e997dd831a`, `i:b60324e54d` | bust text, valve info, portal info | `dis2` `0xc90` and `0xd20`; `fire3` `0x8c`/`0x130`; `fire5` `0x76c` |

Script offsets are code offsets in each level's `script.scr`, as in
`docs/story-route.md`. Every call-site offset named below is a `SITES`,
`TEXT`, `WRITERS`, `REACH` or `HONOR_QUEST_ADDS` row (native and immediate
arguments asserted). Every
entry offset is an `ENTRIES` row, checked against the script's
`internals` table. Script locals are not named by offset.

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

From `0xA0`, record 0's mission-6 byte becomes `0xA1`. From `0xA2` it
becomes `0xA3`, and in that case neither `getEvil` nor `addQuest` runs.
Records 1–3 and missions 5, 7, 8 and 9 are held. Both variables are stored
over `0x5A`. With `0xA0`, the recorded natives are
`getMissionComplete, getEvil, addQuest, setMissionAvailable, setv, setv`
(not evil) or the same list without `addQuest` (evil). No stub runs. There
is no post, no deferred call, no cut and no request. All eight
(level × evil × prior-byte) cases run at both seeds. Evidence:
`check_swamp`; `SITES`.

**Observed / Executed.** Both swamps' `newWorldda5d` (`0x0`) calls
`newWorld(dis2)` at `0x2c`; `dis2` is the pool string at offset 0.
Orientation becomes `0xff`, and the entrance sentinel and mission bytes are
held. The native is `newWorld`, and the one stub is
`net_closeLocalMenus(0)`, which returns 0. Each swamp has five PushTriggers
with `action=newWorldda5d` and one rectangle Trigger `t=newWorldda5d`.
Evidence: `check_swamp` (via `travel`), `check_links`.

**Observed / Executed; no caller found.** `swamp1` `steppedOnTrigger`
(`0x194`) calls `grantMission(6)` at `0x1c0` and `addHelpMessage` at `0x1f4`
(`h:0125fd7019`, `h:afcd253e53`). All four records go from `0xA0` to
`0xA2`, and record 0 goes from `0xA1` to `0xA3`. The stubs are two
`text_lookup` calls and `hud_showHelpMessage(-1, 0, 0)`. Both lookups return
0, so the help gets empty text. `swamp2` has no such entry. Evidence:
`check_swamp`, `check_links`.

What "no caller found" covers (`check_unlinked`, `check_links`):

- no object property value in `swamp1` is `steppedOnTrigger`;
- the `swamp1` script has no pool string `steppedOnTrigger`, so no
  immediate argument (a `callScript`, `postAction` or `addDeferedCall`
  wrapper like `obsfor1`'s) can name it;
- `swamp1` has no `callScript`, `postAction` or `addDeferedCall` call at
  all;
- `swamp1` has no `.dbin` dialog;
- the executable contains no `steppedOnTrigger` string.

Compare `obsfor1`, where Trigger `t=callScri7351` calls `callScript` at
`0x2c` with pool string 0, `steppedOnTrigger` (`SITES`). Whether the engine
reaches the entry some other way is **Unknown**.

### dis2 opening

**Observed / Executed.** `prestart` (`0x37c`) calls
`preloadResource(bust.lmp)` at `0x3a8`, which reaches the `lump_load` stub
and gets 0. It then reads `dis_portalCount` at `0x3d4` into the portal
counter, so the count carries across visits. With `dis_portalCount` 5
planted, three portal hits and one `everyFrame` store 8 and grant, and two
hits store 7 and do not (`check_dis_portals`).

`start` (`0x444`) posts `absorb` at `0x51c` only when the player is not
evil and `dis_sawScene` is 0. On a fresh good start, the natives are 6
calls, 9 `hideMonster`, then `getv, getEvil, getv`
(`DIS_START_GOOD_FRESH`). It creates `dis_portalCount`, `dis_sawScene` and
`dis_activatedAllPortals` at 0, and those stores are recorded.

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

Evidence: `check_dis_start`.

### Good path: eight portals

**Observed.** The eight `disportGOOD` objects carry
`action1=callScrief4c`, which calls `portalTrig`. The eight `disportEVIL`
objects carry `action1` portInit wrappers that call
`autoPropSetState(evilportalX, …)` and then `portalTrig`. `portalTrig`
(`0xd38`) adds one to the portal counter and calls no native. Evidence:
`check_links`; the wrapper natives are checked in `portal_hits`.

**Observed / Executed.** After `prestart` and N wrapper calls, one
`everyFrame` (`0xa74`) stores `dis_portalCount` = N at `0xae8`.

- **N < 8:** it re-defers itself, stores nothing else and grants nothing.
  It calls `showBust(bust_portal.tex, i:9f656ce178, 8 − N)` at `0xc90`
  (good) or `0xd20` (evil) only in the rows marked "bust" below. The stubs
  are `text_lookup` and `hud_setBust(bust_portal.tex, 0, 8 − N, -1)`.
  `check_dis_bust` runs N = 1, 5, 6 and 7 (arguments 7, 3, 2 and 1) in
  each row:

  | Player | `dis_sawScene` | `dis_talkedToBertoxx` | Bust |
  |---|---|---|---|
  | good | 1 | absent | bust |
  | good | absent or 0 | absent | none |
  | evil | 1 or absent | 1 | bust |
  | evil | 1 | absent | none |

- **N = 8, good player:** it stores `dis_activatedAllPortals` 1 at `0xb40`,
  calls `gotAllPortals` (`0xd64`) at `0xb6c`, and does not re-defer itself.
  `gotAllPortals` runs `getEvil`, then:
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
- **N = 8, evil player:** it stores `dis_activatedAllPortals` 1.
  `gotAllPortals` runs `getEvil` and then only `addHelpMessage` at `0xf58`
  (`h:a0df82f764`, `h:0efe320d7b`). There is no grant and no deferred call,
  and the planted Bertoxx quest stays.

Evidence: `check_dis_portals`, `check_dis_bust`.

**Observed / Executed.** The deferred `pause` (`0x1190`) counts unpaused
calls in a script local. On the 61st unpaused call it calls
`addHelpMessage` at `0x1280` (`h:a0df82f764`, `h:5d38865288`) and queues
itself again. On the 92nd it calls `receivedShard` (`0x1110`) and stops
queueing. `receivedShard` shows the help at `0x1144` (`h:65a1721c33`,
`h:de988ded64`) and calls `soundSequence(fx.lmp, quest_complete.anm)` at
`0x1178`. Its sound stubs are `res_find` (which returns 0, so
`sound_playOnObject` gets resource 0) and `sound_setPlaysWhileFrozen`.

A paused call after an unpaused one queues `pause` again and counts nothing.
After `prestart`, a paused *first* call does not queue `pause` again, so
the chain stops there. Evidence: `check_dis_pause`.

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

The rectangle Triggers `t=if18fc` and `t=if69ee` are the only `t=`
triggers. Evidence: `check_links`.

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
`Camera_update(0)` and `net_isLocalSlot(0)`. `lump_load` and
`net_isLocalSlot` return 0, so no dialog is opened here, and Trigger
dispatch is not run. A good player only runs `getEvil`. Evidence:
`check_dis_bert`.

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

The seed is unchanged. Evidence: `check_dis_bert`.

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
| `setEntra9e0f` | one PushTrigger | `arachna1` | `left` |
| `setEntrae2b1` | one PushTrigger | `arachna1` | `right` |
| `newWorld3914` | four PushTriggers `name=goodexit` | `swamp1` | sentinel |
| `newWorld5a4f` | four PushTriggers `name=evilexit` | `swamp2` | sentinel |
| `if69ee` | Trigger | `swamp2` if evil, else `swamp1` | sentinel |

Evidence: `check_dis_travel`; `check_links` (`DIS_EXIT_COUNT`).

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
Evidence: `check_mission7_offer`, `check_links`. Across all 119 level
scripts, these six hub entries and `valor` `start` are the only mission-7
availability writers (`check_writers`, `WRITERS`).

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
4. The wave branch reads `numberOfWaves` at `0x1094`. When it is 0 (absent
   on a fresh run), `start` stores `numberOfWaves` 1 at `0x10d4` and
   `skelPopulation` 0 (over `0x5A`). With `numberOfWaves` planted at 1 or
   2, it writes no `numberOfWaves`. In place of those two stores it runs
   `getv, getv, setv` (`VALOR_START_WAVES_SET`). In both cases it defers
   `checkperiodicSpawn` at `0x1290`. `numberOfWaves` is not planted
   `0x5A`, because a non-zero value changes this branch.
5. Posts `absorb` at `0x12f4` while `sawValor` is 0. The read creates
   `sawValor` at 0, and that store is recorded.

Fresh, record 0's mission-7 byte becomes `0xA1`, no quest is added, no stub
runs, and the 24-call native list is pinned (`VALOR_START_FRESH`). With
mission 8 at `0xA1` the fire quest is added. With mission 8 at `0xA3` and
mission 9 at `0xA1`, the storm quest is added. With both at `0xA3`, or
mission 8 at `0xA2`, nothing is added. With `sawValor` 1, nothing is posted.

The posted `absorb` (`0x172c`) calls `valorIntro` (`0x1770`). While mission
8 is not complete, that calls `cutScene(valor)` at `0x17d4` (stubs
`res_find(.lmp, valor.cut)` and `cut_start`, both returning 0) and stores
`sawValor` 1 at `0x1808`. Once mission 8 is complete it calls neither, and
a planted `0x5A` stays. Evidence: `check_valor_start`.

**Observed / Executed; no caller found.** `valor` `steppedOnTrigger`
(`0x1820`) grants mission 7 on all four records at `0x184c` and requests
the `h:0125fd7019` / `h:afcd253e53` help at `0x1880`, with the same stubs
as in swamp1. "No caller found" has the same meaning as for `swamp1`
(`check_unlinked`, `check_links`):

- no object property value names it;
- there is no pool string `steppedOnTrigger`;
- each of the script's nine `callScript`/`postAction`/`addDeferedCall`
  calls takes an immediate pool string;
- its one dialog, `mattmar.dbin`, has no such action;
- the executable has no such string.

Evidence: `check_valor_start`, `check_unlinked`.

### Matt Marr

**Observed.** `MattMarr` (`name=mattmar`) has `dialogscript=startDiaff8`
(`0x220`). That calls `startDialog(mattmar, 1, 0)` at `0x25c`, which reaches
the same three dialog stubs, with `lump_load` returning 0. `mattmar.dbin`:

| Node | Condition | Choice action | Target |
|---|---|---|---|
| 0 | `if2a2e` | `setMissi1bb4` | 1 |
| 1 | `if84f0` | `setv6151` | close |
| 2 | `ifa054` | `setMissie47a` | 3 |
| 3 | `if7275` | `setv3d8c` | close |
| 4 | `ife995` | `setv7ac2` | 5 |
| 5 | `if4ffe` | `newWorldf844`; a second choice with no action | close |
| 6 | `if550a` | `newWorld511b` | close |

Evidence: `check_links`.

**Observed / Executed.** `check_marr` runs all seven conditions in 64
states. The states are every byte-8 value × every byte-9 value (`0xA0`,
`0xA1`, `0xA2`, `0xA3`: available bit 0, complete bit 1), × `MarrDone`
absent or 1, × good or evil. Each condition calls only
`getMissionAvailable`, `getMissionComplete`, `getv` and `getEvil`, reaches
no stub and changes no mission byte. The returns match this rule
(`marr_model`) in all 64 states:

| Node | Condition returns 1 when |
|---|---|
| 0 | mission 8 not available |
| 1 | mission 8 available and not complete |
| 2 | mission 9 not available |
| 3 | mission 9 available and not complete |
| 4 | mission 9 available and complete, good, `MarrDone` absent |
| 5 | mission 9 available and complete, good, `MarrDone` 1 |
| 6 | mission 9 available and complete, evil (`MarrDone` either) |

Nodes 0–3 return the same for good and evil players, and `MarrDone` changes
only nodes 4 and 5.

**Inferred (first-true rule; the selector was not run).** Applying
`dialog_start_node` to each measured row:

- node 5 or 6 comes first only when both bytes are `0xA3`. That is node 5
  for a good player with `MarrDone` 1, and node 6 for an evil player with
  `MarrDone` absent or 1 (`check_marr` asserts exactly these three rows);
- the good sequence is node 0 → 1 → (mission 8 completed) 2 → 3 →
  (mission 9 completed) 4 → 5;
- an evil player follows the same nodes 0–3, never selects node 4 or 5,
  and gets node 6 once mission 9 is complete.

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
- `setv7ac2` (`0x9f8`): stores `MarrDone` 1.
- `newWorldf844` (`0xb84`, good) and `newWorld511b` (`0xd20`, evil):
  - `newWorldPost(valor2)` at `0xbb0` / `0xd4c` copies `valor2` into
    `0x4fdcf0`. The pending level and orientation sentinels stay.
  - Each removes the storm quest and adds the honor quest `q:4ff8a3b5ae`,
    with body `q:1030edc5cb` (good) or `q:537f710378` (evil).

No action reaches a stub. The dialog-end handler that would act on
`0x4fdcf0` (`docs/spec/script-builtins.md` line 366) was not run.
Evidence: `check_marr`.

### Doors and the gate

**Observed / Executed.**

- **`tofire` and `tostorm`.** Both PushTriggers use `key=return4520` and
  `action=callScrib1e7`. The key returns 1 when `mar_fire` or `mar_storm` is
  1, and 0 when neither is set. The action calls `marrPortal` (`0x2244`).
  That requests `fire1` at `0x22a4` when `mar_fire` is set, and then
  `storm1` at `0x2304` when `mar_storm` is set. With both set, two
  `newWorld` calls run and `storm1` is left pending. With neither, nothing
  is requested. Each `newWorld` stores orientation `0xff` and reaches
  `net_closeLocalMenus(0)`. The entrance sentinel stays.
- **`tovalor`.** Its key, `return25eb`, returns 0 and calls no native.
- **The gate.** The rectangle Trigger `t=callScri1ef1` calls
  `gatewaytrigger` (`0x20b8`). When `mar_fire` is set, or `mar_storm` alone
  is set, and `gateon` is not, it calls `trigger(portal, 0)` at `0x21ac`
  and stores `gateon` 1 at `0x21e0`. `mar_storm` is read only when
  `mar_fire` is not set. No object named `portal` is planted, so no virtual
  call is made. The guarded request with a planted portal is the hub case
  in `docs/story-route.md` §2, not this level. With `gateon` 1, no trigger
  runs.

Evidence: `check_valor_doors`, `check_links`.

### How mission 7 is marked complete

**Observed / Executed.** `valor2`'s only PushTrigger runs `newWorld6440`,
which requests `honor`. `honor`'s exit `newWorlda6a0` requests `valor2` at
`0x2c`. Both store orientation `0xff` and leave the entrance sentinel.
Evidence: `check_honor`.

**Observed / Executed.** `honor` `start` (`0x2f8`) calls `setParticle`,
whose stub is `particle_define` (returns 0). It defers `particleEffects`
(`0x554`) at `0x3f8`. It then stores `playerHasItem(shardofvalor)` from
`0x534` in a script local, using the `inventory_countItemByName` stub.
`shardCheck` (`0x1120`) runs as follows:

- On entry, once the call counter has reached 25, it resets the counter
  and compares the current count (`playerHasItem` at `0x1184`) with the
  count stored at `start`.
- The compare is a signed greater-than. When it holds, it:
  1. calls `playerHasItem` again at `0x11c4`;
  2. requests help at `0x1200` (`h:0d52ad7552`, `h:4169aeb71b`);
  3. calls `grantMission(7)` at `0x122c`;
  4. removes the honor quest at `0x1258`;
  5. calls the sound;
  6. runs four `onePlayerHasItem` calls.
- Last, it calls `gamePaused`, and adds 1 to the counter when that returns
  0.

In the test:

- With the count stub 0 at `start`, each of calls 1–25 runs only
  `gamePaused` (asserted per call) and grants nothing.
- The 26th call, with the stub at 1, grants. All four records become
  `0xA2` (record 0 becomes `0xA3` from `0xA1`), and the planted honor
  quest becomes `NoQuests`.
- With the stub at (start, check) = (1, 1), (2, 1), (1, 0) or (0, −1),
  nothing is granted, the 26th call runs `playerHasItem, gamePaused`, and
  the quest stays. (1, 2) and (−1, 0) grant (`COMPARE_CASES`). The second
  read at `0x11c4` stopped no grant in these cases, including a count of 0;
  its use is not separated.
- One paused call moves the grant to the 27th call.

This file calls `shardCheck` directly. In play, the caller is
`particleEffects`, through `callScript` at `0xc44`, which was not run. The
count is the stub's return for one player, not a real bag. The grant does
not test for the honor quest or for any mission byte. Evidence:
`check_honor`.

**Observed / Executed (all-archive sweep, `check_reach`).** Over all 119
level scripts:

- the only level requests naming `valor2` or `honor` are the two
  `newWorldPost(valor2)` calls in Matt Marr's node-5 and node-6 actions,
  `valor2`'s `newWorld(honor)` and `honor`'s `newWorld(valor2)` (`REACH`).
  The natives covered are `newWorld`, `newWorldAlways`, `simpleNewWorld`,
  `newWorldPost` and `newWorldParameter`;
- no level request takes a computed name, and none uses
  `newWorldParameter`;
- the only object properties with the value `valor2` or `honor` are the
  two `Player1` `from=` markers;
- the honor quest title is added only at `valor` `0xc10` and `0xdac`;
- the menu's story rows (`difftest_story_beats.TABLE_FROM_MINUS_ONE`,
  asserted against the executable there) name neither level.

**Inferred.** On the script route, `valor2`, and so `honor`, is reached
only through node 5 or 6. Under the first-true rule, those are selected
only once missions 8 and 9 are both available and complete. So mission 7's
`honor` grant follows missions 8 and 9 for good and evil players. This
rests on the first-true selection and the dialog-end handler (neither run),
and on there being no non-script route to `valor2` (the loader, saves and
net games are **Unknown**). The grant also needs a shard-of-valor count
greater than the one read at `honor` `start`. `valor` `steppedOnTrigger` is
a second mission-7 writer with no caller found.

### What makes mission 8 available

**Observed / Executed.** Matt Marr's node-0 action `setMissi1bb4`, and the
`fire1` and `obsfor1` `start` entries (section 3). No hub or hub2 entry
writes mission 8. Granting mission 7 does not set mission 8's bit.
Evidence: `check_writers`, `check_marr`, `check_honor`.

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
kept. There is no post, cut or stub. Evidence: `check_fire1`.

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

In `fire3`, exactly one object has a `key=` property: the PushTrigger for
the center ladder (`setEntrabca8`), with `key=return7da1`. That key returns
1 only when `switch1done` and `switch2done` are both 1. The two
`pipevalveswitch` actions `hideMons7bb4` and `hideMonsc5f1` each run
`hideMonster`, store `switch1done` or `switch2done` 1 over `0x5A`, and call
`setInfo` (`i:e997dd831a`). The `setInfo` stubs are `text_lookup` and
`hud_showMessage(0, 180, -1, 0)`. Evidence: `check_fire_travel`,
`check_links`.

### fire5: dragon, shard and completion

**Observed / Executed.** `fire5` `start` (`0xd0`):

- stores `playerHasItem(shardoffire)` from `0x110` in a script local
  (count stub);
- defers `shardCheck` at `0x144`;
- calls `setSaveInhibit(1)` at `0x1a8` only while `killedDragon` is 0
  (absent or planted 0), creating it at 0. That sets the save-inhibit word
  `0x50605c` (`docs/spec/script-builtins.md` line 516) to 1 over a planted
  `0x5A5A5A5A`. With `killedDragon` 1 or `0x5A`, there is no call and the
  word keeps the plant;
- always posts `absorb` at `0x1d4`.

`absorb` (`0x1ec`), while `fire_sawDragon` is 0:

1. `cutScene(dragon)` at `0x250`, with the cut stubs;
2. stores `fire_sawDragon` 1 at `0x284`;
3. posts `firsaved` (`0x2fc`) at `0x2b0`.

`firsaved` calls `saveCheckPoint`, whose stubs are `dbg_printf` and
`save_game(0, 0, 1)`. `save_game` returns 0, so nothing is saved. It then
calls `setminiboss` (`0x364`). That runs `setCFlag(reddragon, …)` at
`0x3a0` and three `setMonsterVal(reddragon, …)` calls at `0x3dc`, `0x418`
and `0x454`, with the targets pinned in `SITES`. No object is planted. With
`fire_sawDragon` 1, `absorb` goes straight to `setminiboss`.

The `reddragon` record has `dropitem=shardoffire` and
`deathscript=callScri3971`. That calls `deadDragon` (`0x784`). It stores
`killedDragon` 1 over `0x5A` at `0x7b8` and calls `setSaveInhibit(0)` at
`0x7e4`, which sets the word from 1 to 0. Evidence: `check_fire5`,
`check_links`.

**Observed / Executed.** `shardCheck` (`0x46c`) adds 1 to a script-local
counter on every call, with no pause test.

- On the 25th call it resets the counter and compares the current count
  (`playerHasItem` at `0x4e4`) with the one stored at `start`. The compare
  is a signed greater-than. When it holds, it:
  1. requests help at `0x52c` (`h:6d5f292589`, `h:ec992006f4`);
  2. stores `fire_gotShard` 1 at `0x560`;
  3. calls `grantMission(8)` at `0x58c`;
  4. calls the sound;
  5. runs the `onePlayerHasItem` loop;
  6. does not queue itself again.
- Otherwise it queues itself (`0x6bc`/`0x6f0`).

In the test, with the stub 0 at `start` and 1 afterwards, each of calls
1–24 runs only `addDeferedCall` and leaves `shardCheck` queued (asserted
per call). The 25th grants: all four records `0xA2` (record 0 `0xA3` from
`0xA1`), and `fire_gotShard` is stored over `0x5A`. With `g_paused` 1 on
every call it also grants on the 25th call. The planted fire quest is
**not** removed. With the stub at (start, check) = (1, 1), (2, 1), (1, 0)
or (0, −1), there is no grant, the 25th call runs
`playerHasItem, addDeferedCall`, and `fire_gotShard` keeps `0x5A`. (1, 2)
and (−1, 0) grant (`COMPARE_CASES`). Evidence: `check_fire5`.

**Observed / Executed.** The jump-gate `Portal` record (`lump=jumpgate`,
`script=return2c8d`) has a script that returns 1 only when `fire_gotShard`
is 1. It returns 0 when the variable is absent or `0x5A`. The Trigger
`t=callScricb6b` calls `portalMessage`, which calls `setInfo`
(`i:b60324e54d`) until the shard variable is set. The gate's destination
belongs to the jump-gate system and was not run. Evidence: `check_fire5`,
`check_links`.

**Observed / Executed.** `obsfor1` `start` repeats mission 8's availability
and the two `setv`s, with no quest. Its only Trigger, `t=callScri7351`,
calls `steppedOnTrigger` through `callScript` at `0x2c`. That grants
mission 8 on all four records and requests the `h:0125fd7019` /
`h:f401646fec` help. It is a second completion writer, like the `water1`
and `islcave1` triggers in `docs/story-route.md` §§7–8. Evidence:
`check_obsfor1`, `SITES`.

### What makes mission 9 available, and its grant

**Observed / Executed.** Matt Marr's node-2 action `setMissie47a` sets
mission 9's bit and removes the fire quest. The mission-8 grant does not set
mission 9. No hub entry writes mission 9.

**Observed, not run.**

- `storm1` `start` calls `setMissionAvailable(9, 1)` at `0x24c`.
- The only mission-9 grant site on the disc is `storm2` `checkEveryFrame`,
  `grantMission(9)` at `0xf70` (`WRITERS`). It is the completion that the
  Matt Marr node 4–6 conditions wait for.

Evidence: `check_marr`, `check_writers`.

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
   `dis_portalCount`, so portals used on an earlier visit still count. A
   good player's first `start` posts the `dis` cutscene request, then
   `initLevel`, which sets `dis_sawScene` and starts the `everyFrame` loop.
   Evil players get no cut. Their loop starts only after they have talked to
   Bertoxx.
4. **Portals.** Each portal use adds one to the counter. `everyFrame`
   saves the counter to `dis_portalCount`. While fewer than eight are
   used, it shows the portal bust with 8 − N for a good player with
   `dis_sawScene` 1, or an evil player who has talked, and no bust
   otherwise.
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
   portal help:
   - The level Trigger `if18fc` requests the Bertoxx dialog (stubbed here)
     while the player has not talked. The return to Bertoxx after the
     eighth portal is the inferred node-3 choice.
   - The node-2 action `setv7c05` stores the talk and adds the Bertoxx
     quest.
   - The node-3 action `setv7df7` stores `dis_finishedQuest` and grants
     mission 6, removes the Bertoxx quest, and requests the shard give,
     help and sound.
   - The node choice is inferred; `dialog_onMsg` was not run.
7. **Second mission-6 writer.** `swamp1` `steppedOnTrigger` grants mission
   6, but no caller was found (no object, wrapper, dialog or executable
   string names it). Do not wire it to an object without evidence.
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
    - on a first visit (`numberOfWaves` 0), stores `numberOfWaves` 1 and
      `skelPopulation` 0; on every visit, defers `checkperiodicSpawn`;
    - adds the fire quest while mission 8 is open, or the storm quest while
      mission 9 is open;
    - posts `absorb` once. That requests the `valor` cutscene and stores
      `sawValor` only while mission 8 is incomplete.
11. **Matt Marr.** Drive Matt Marr from the condition rule in §2. It was
    measured over all 64 states for good and evil players. The node choice
    is the first-true rule, not run here.
    - Node 0 makes mission 8 available, and node 1 stores `mar_fire` and
      adds the fire quest.
    - Node 2 makes mission 9 available and removes the fire quest, and
      node 3 stores `mar_storm` and adds the storm quest.
    - Node 4 (good only) stores `MarrDone`.
    - Node 5 (good, after `MarrDone`) or 6 (evil) posts `valor2` through
      `0x4fdcf0`, removes the storm quest and adds the honor quest. Both
      need mission 9 available and complete.
    - An `addQuest` whose title is already in the log keeps the old entry.
12. **Valor doors.** `tofire`/`tostorm` open once `mar_fire` or
    `mar_storm` is set, and request `fire1` or `storm1`. `storm1` wins when
    both are set. `tovalor` stays locked. The gate Trigger makes one
    `trigger(portal, 0)` request and stores `gateon` once either variable is
    set. The Portal's virtual method was not run here.
13. **Mission 7 completion.** Complete mission 7 in `honor`:
    - When `shardCheck` sees the counter at 25 and a shard-of-valor count
      greater than the count read at `honor` `start` (signed), grant on
      all four records, remove the honor quest, and request the help and
      sound.
    - Paused calls do not advance the counter.
    - The count was a stub. `particleEffects`, which calls `shardCheck` in
      play, was not run.
    - `valor` `steppedOnTrigger` is a second mission-7 writer with no
      caller found. Do not wire it to an object without evidence.
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
    - While `killedDragon` is 0 it sets the save-inhibit word to 1.
    - Posting `absorb` requests the `dragon` cutscene once, then
      `firsaved` (checkpoint save request; `save_game` was stubbed) and the
      miniboss values.
    - The dragon's death script stores `killedDragon` and sets the
      save-inhibit word to 0.
16. **Mission 8 completion.**
    - Grant mission 8 on the 25th `shardCheck` call when the fire-shard
      count is greater (signed) than at `start`, paused or not.
    - Store `fire_gotShard`, request the help and sound, and stop the
      loop.
    - Leave the fire quest in the log; Matt Marr's node 2 removes it.
    - The fire5 jump gate's script opens once `fire_gotShard` is 1.
    - `obsfor1` is a second grant writer, reached through its Trigger's
      `callScript` wrapper.
17. **Mission 9 availability.** Make mission 9 available from Matt Marr
    node 2 (and `storm1` `start`), not from the mission-8 grant.
18. **Writer list.** The test's all-archive writer set (`WRITERS`) is the
    complete list of script sites that make missions 6–9 available or grant
    them. No other script site writes these missions. Two entries, `swamp1`
    and `valor` `steppedOnTrigger`, have no caller found. Keep them
    unwired until there is evidence, as in items 7 and 13.

## 5. Commands and results

Run on the Mac mini with the owner's `SLUS_209.73` (SHA-256 pinned in the
test) and the read-only disc data folder, from a git checkout (the text
check reads `git ls-files`):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["difftest_story_mission68.py","--elf","local/SLUS_209.73","--data","/path/to/BG/DATA"]; runpy.run_path("tools/difftest_story_mission68.py", run_name="__main__")'
```

Both seeds: 409 checks each, 0 failed (`PASS seed 20973: 409 mission-6/7/8
checks`, `PASS seed 7: 409 mission-6/7/8 checks`). The PASS log from after
the final edit, with the commit and the test's SHA-256 in its header, is
kept in ignored `local/story-m68.log`. The earlier story difftests and the
unit suite results are in `work/cursor-report.md`.

## 6. Unknown

- The loader and arrival after each pending write, and any non-script route
  into `valor2` or `honor` (saves, net games).
- Which object use reaches the dis2 portals, Bertoxx, Matt Marr, the valor
  doors and the fire3 valves, and `dialog_onMsg` on `bertoxx.dbin` and
  `mattmar.dbin`.
- Which hub dialog node play selects to reach `ifcceb` after mission 6.
- `particleEffects` and the honor sarcophagus and ring entries that lead to
  the shard of valor, and what the second shard read at `honor` `0x11c4`
  is for.
- A real shard count or give in place of the inventory stubs.
- The rendered effect of `trigger(portal, 0)` and of the jump gates in
  `honor` and `fire5`.
- `checkperiodicSpawn`, the skeleton waves past the `start` branch, and the
  excal sword entries (`swordKeyCheck`, `receiveSword`).
- `storm1`, `storm2` and mission 9 beyond the sites named above.
- Whether anything reaches `swamp1` or `valor` `steppedOnTrigger`.
- A continuous session from the menu through any of these grants.
