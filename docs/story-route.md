# Hub to the first story combat level

US `SLUS_209.73` v2.00, research worktree `t3/research-story-route-r3`, 2026-10-23.
This is a function-level and disc-structure trace, not a running-game or native
playthrough result. `tools/ref_story_route.py` models the fresh route and
`tools/difftest_story_route.py` compares original EE functions at seeds 20973
and 7. Private archive contents and disassembly remain in ignored `local/`.

## Result and evidence boundary

**Observed, Executed within stated bounds:** A new character's `hub` script
`start` makes mission 0 available and complete. The fresh-state node
conditions select node 1; the archive's unconditional choices connect nodes
1 → 2 → 3. Either node 3 ending action makes mission 1 available and adds one
quest. Hub object 11 names a key and action; executing those script entries
with a synthetic fresh player returns a usable key and opens the mission menu
for slot 0 when the dialog is closed and recall is clear. The menu's row 0
story selection writes `blood1` to `g_pendingLevel` and `0xff` to orientation.
`blood1` is mission 1's story level and has hostile object records. `valor` is
mission 7's story level in the executable's mission table.

**Observed:** There is no `newWorld`, `newWorldPost`, or `simpleNewWorld`
import in the shipped `hub` script. The first story request is the mission
menu's direct pending-level write at 0x232220, not a script `newWorld` call.
`newWorldPost` is the dialog-close mechanism for other routes, not this one.
The hub gate menu is also a separate travel path; the visible portal rings
and the `Portal` object's presence do not make it the mission 1 exit.

**Unknown:** The whole NPC interaction, actual PushTrigger proximity/use
dispatch, carried state through a real level load, terrain placement,
`blood1` archive load and first attack have not run as one original or native
session in this research. The synthetic EE harness supplies selected external
services. It does not prove that the native client can fight. No arrival
coordinate, live actor count, gear or combat outcome is claimed. The full
NPC-to-menu route and default-marker selection remain inferred from checked
archive links and separate function-level runs. Section 6 continues from the
`blood1` request: which menu row the mission bytes select, which level confirm
writes, and which act that level is in. It does not remove the limits above.

## 1. Hub setup and the opening NPC

| Evidence | Field or event | Result |
|---|---|---|
| **Observed** `hub` script `start` offset 0x2838; built-ins 0x1420d0 and 0x1420a4 | `setMissionAvailable(0,1)`, `grantMission(0)` | Mission byte 0 becomes 3 (available and complete). **Executed** by `run_hub_entry(start)` with a clean player record at both seeds. |
| **Observed** `hub` script offset 0x29bc–0x2a0c | `getv(currentMission)`, then `setv(storeLevel,0)` when the first read is zero | This is the fresh-state branch. Later `start` branches manage other missions and the `firstmissionever` variable; they must not be flattened into a universal assignment. |
| **Observed** hub `objects.ob`, NPC record 10 | `dialogscript=startDia3314`; `startDia3314` calls `startDialog` at script offset 0x003c | The object is reached by the `Creature_interact` use-button path at EE 0x116bd8, then `script_startDialog` 0x143824 and `dialog_start` 0x22fa50. |
| **Observed, Executed** `firiona.dbin`, node conditions at script offsets 0x03f0, 0x011c, 0x0198 | Fresh-state condition results for nodes 0, 1 and 3 are 0, 1 and 0; the single choices in nodes 1 and 2 have empty conditions/actions and target 2 and 3 | `dialog_onMsg` 0x22ee2c selects the first true node (0x22efac), hence node 1. The selection and choice traversal are **Inferred** from the generic dialog rules; this test executes the conditions and checks the file structure, not `dialog_onMsg` on this dialog. |
| **Observed, Executed** node 3's two ending actions at script offsets 0x1e68 and 0x1ee8 | Both call `setMissionAvailable(1,1)` and `addQuest` | On a clean one-player record, each action yields mission byte 1 = 1 and quest count = 1, with the same title and description keys. The second action also requests a camera/store change. Both run through the shipped script image, `scr_load` 0x13e8f8, `scr_interpret` 0x13ecf8 and `script_runByName` 0x1ed694 in `ee_emu.py`. |

Mission bytes are at player record `g_players` 0x4d8af0 +0x4bbf,
13 bytes per difficulty. `g_difficultyIdx` is 0x4f719c. The quest list starts
at record +0x41d0 (eight entries of 0x40); its count is +0x43d0. The two
dialog actions do not call `setv`: they do not set `startedMission1` or
`currentMission`. A condition's `getv` can append an absent name with value
zero (`vars_get` 0x1ed778); do not mistake this for story progress. The
`firstmissionever` and `storeLevel` branches of `start` belong to their own
conditions. These record and variable rules are documented on
`t3/research-quests` and in `docs/spec/script-builtins.md`.

## 2. Portal prompt and menu request

The proposed actionable exit is the hub `PushTrigger` record 11, whose `key`
and `action` properties select `returnefa9` and `callScri8e04`. The shipped
script entry `callScri8e04` calls `warnDetect` (script offset 0x49c0).
`PushTrigger_interactPrompt` 0x1eca50 evaluates its ordered `key` properties;
`PushTrigger_interact` 0x1ecc70 dispatches the action on a use press. Those
generic functions were compared in `t3/research-exits-walkin` `ba48fe5`;
their dispatch on this specific hub object is **Inferred**, not executed here.
The `returnefa9` key entry returns 1 on the synthetic fresh state at both
seeds. A rectangle `Trigger` record 12 separately calls
`gatewaytrigger`. **Executed** with a synthetic named portal, this entry calls
the `trigger` built-in with `portal` and `0`; the built-in invokes virtual
trigger slot 3 on that object with argument 0. The request is guarded by
`warncheck`, `lockDetect` and a one-shot script variable: no request occurs
before mission 1 is offered or on a repeat call. A rendered visual change is
**Inferred** from the portal object's generic behavior because the synthetic
virtual method is a recording stub, not the shipped Portal implementation.
`ee_emu.py` cannot establish the rendered effect with this stubbed virtual
method and no renderer. The entry does not name a destination. The standalone
`Portal` record 6 belongs to the jump-gate system. The hub record
indices, links and key are asserted against the local archive; the two script
wrappers are asserted against the shipped script image, and the guarded portal
request is executed at both seeds.

`warnDetect` calls `warncheck` at script offset 0x4234. It tests an available,
incomplete mission with the matching `startedMissionN` variable set. In the
fresh mission 1 state, `startedMission1` is zero, so **Executed** `warncheck`
returns zero. Executing `callScri8e04` reaches `warnDetect`, which calls
`setEntrance(goodstart)` at offset
0x4a44 and `activateMissionMenu()` at 0x4a68. `setEntrance` 0x142a94 copies
the string into `g_entranceName` 0x4f8468. `activateMissionMenu` 0x143fa8
opens `missionMenu_open` for slot 0 with dialog closed, recall clear and
offline mode; an open-dialog control does not call it. The player must finish
the NPC conversation before this interaction. The alternate warning
branch shows a message and defers `missionmenuPause`; its complete timing is
not part of the fresh-route test.

`missionMenu_open` 0x231520 registers `missionMenu_run` 0x2316fc (task
priority 20). With only mission 1 available, the first menu tick selects row
0 (mission number 1) and pauses the simulation. Sixteen fade ticks take the
counter from 0 to 127; a confirm in state 2 takes the story column through
states 5, 6, 7 and 8. State 6 waits for fade value at least 128. In state 8,
the original writes the story pointer at `g_missionTable` 0x4fe540 +0x08,
which is `blood1`, to `g_pendingLevel` 0x41b6d0, and orientation `0xff` to
0x41b720 (**Executed**, 26 snapshots per seed). The table row's evil
alternate is null; its medal and bonus destinations are different columns.
`valor` is row 6 (mission 7), so direct loading it skips this campaign step.

## 3. Arrival and state carried into `blood1`

| Evidence | Native requirement |
|---|---|
| **Observed** `mainloop_loadRequestedWorld` 0x320edc–0x3214c0 | Save the old `hub` level state; call `save_actChanged`; apply any pending character selection; copy `hub` into `g_prevLevelName` 0x41b7c2; split and clear the request; load base name `blood1`; then place players. |
| **Executed** `save_findAct` 0x217d30; **Inferred** carryover | From current act 0, both `hub` and `blood1` resolve to act 0. The observed act-change branch should not clear mission bytes, quests, quest variables or non-quest inventory for this move, but their survival through a level load was not executed. `valor` resolves to act 6. |
| **Observed** `g_entranceName` 0x4f8468 and `Player1_ctor` 0x158928; **Inferred** placement | The script sets `goodstart`. The archive check asserts the complete `Player1` census: zero-based record 227 has only `default=1`, record 287 only `from=strife`, and record 298 only `from=drundar`. No record has `name=goodstart` or `from=hub`. The default is the applicable authored marker under the documented ranking rules, subject to an actual construction test. |
| **Observed** `mainloop_loadRequestedWorld` 0x321160–0x3214c0; `game_loadLevel` 0x1e55c0–0x1e6234 | Terrain height and `world_findFreeSpot` determine final spawn coordinates. An eligible living player gets a new `Player` object from the existing record. The loader sets record +0x4c27 to 30 (entry hit immunity). The orientation byte is copied to 0x41b7c1 and 0x41b720 becomes 0xfe; no gameplay reader of the copy was established in `t3/research-levels`. |
| **Observed** private `BLOOD1.GOB` count only | 363 object records, including 140 records in four selected hostile class families. This establishes authored combat candidates, not successfully constructed or live enemies. |

The old hub object instances and script machine are replaced. Per-player
mission flags, quest list, HP, experience, character identity and equipment
belong to the persistent player record. Quest variables are per game. The
native port must carry that state and the shared seed into the loader; the
level load and marker searches can then consume seed draws. The isolated
menu comparison only established that its selected path did not advance the
seed. Equipment construction, resource residency and actual blood1 actor
binding remain unverified. See `t3/research-levels` `docs/level-flow.md`
§§5–7 and `t3/research-quests` `docs/quests.md` §§1,5.

The marker census is an exact assertion over `BLOOD1.GOB`'s `objects.ob` in
`check_disc`, not an EE function result: `ee_emu.py` executes mapped functions
and this harness does not load the archive into an original world. A loader and
`Player1_ctor` run with those records would settle actual marker selection.

## 4. Ordered native port list

1. Run the real hub `script.scr` `preStart`/`start` and persist mission bytes,
   quest lists and quest variables in their proper player/game owners. Keep
   mission 0's initial state and fresh `storeLevel` branch.
2. Wire the NPC's use prompt to `dialogScript`, load its `.dbin`, evaluate
   initial node and visible choices using the original script VM, and run the
   selected action before the dialog closes. Verify this hub dialog's node
   transitions in an integrated interaction; file links and individual script
   entries alone do not establish it. Preserve the shop/camera side branch.
3. Implement the hub PushTrigger's `key`/prompt/use path, `warnDetect` and
   `setEntrance`. Confirm the record 11 dispatch with a real hub interaction;
   only its archive link, key entry and script wrapper were checked here.
   Keep its warning/deferred branch and the separate walk-in Trigger's guarded
   `trigger(portal,0)` request. Check the actual Portal virtual method and
   rendered effect in an integrated run; the executed synthetic object only
   establishes the request. Do not treat the `Portal` gate as the story exit.
4. Run `missionMenu_open`/`missionMenu_run` with the player's lockstep pad,
   availability gate, row/column, fade and state-8 direct pending-world write.
   For the fresh route, confirm row 0's story column to request `blood1`.
5. Carry pending level, previous level, entrance, player records, quests and
   variables through `mainloop_loadRequestedWorld`. Load the `blood1` archive,
   construct destination records in order, apply the default `Player1` marker,
   terrain/free-spot placement and player construction. Verify state survival
   and selected marker in a loader run; the current same-act and marker claims
   are inferred from separate functions and checked archive records.
6. Bind real enemy constructors, resources, equipment and combat services,
   then perform a native hub-dialog → PushTrigger → menu → `blood1` → first
   attack acceptance run. Compare level name, request, marker, record and
   combat traces to the original running game. The present function-level
   comparison does not close this integration gate.

## 5. Verification

Run with `PYTHONDONTWRITEBYTECODE=1` and the local owner-supplied ELF and
archives. `difftest_story_route.py` pins the executable SHA-256, checks the
shipped hub script/dialog/objects and exact blood1 marker records without
outputting their bytes. It executes `start`, the opening conditions, key,
wrapper, both mission actions and guarded `gatewaytrigger` via the original
interpreter. It records the portal virtual call under offered, unoffered and
repeat controls and the menu-open slot under closed and open dialog controls,
then compares the original mission menu to the
reference state after every tick at seeds 20973 and 7. It checks the direct
pending request and orientation, not a full `game_loadLevel` call.

The existing `difftest_natives.py` hub script comparison exercises all 82
shipped entry points and a 60-tick synthetic script sequence. Existing
`difftest_objects.py` marker properties and the full unit suite are separate
controls. Their results do not turn this route into an integrated playthrough.

Commands run (the two `.GOB` files and `scripts_raw/hub.scr` were extracted
under ignored `local/story-route/` from the owner's read-only disc):

```sh
ELF=/path/to/SLUS_209.73
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_story_route.py --elf "$ELF" --hub-gob local/story-route/disc/BG/DATA/HUB.GOB --blood-gob local/story-route/disc/BG/DATA/BLOOD1.GOB
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_natives.py "$ELF" --scripts local/story-route/scripts_raw --seed 20973 --quick -k hub.scr
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_natives.py "$ELF" --scripts local/story-route/scripts_raw --seed 7 --quick -k hub.scr
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_objects.py "$ELF" --quick --seed 20973 -k marker
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_objects.py "$ELF" --quick --seed 7 -k marker
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

Results: story route 26/26 menu snapshots and one guarded portal virtual call
per seed; hub native comparison 3/3 properties per seed (82/82 entry points
and a 68-case scripted sequence each); marker comparison 4/4 properties per
seed across four FPU models;
full unit suite 652/652. The `t3/research-exits-walkin` `ba48fe5` generic
dispatch difftest also passed at both seeds (268 trigger, 64 gate prompt,
48 PushTrigger prompt and 20 gate-arrival comparisons per seed). All were
function-level or synthetic-fixture checks; that generic test did not run
the hub object 11 use interaction.

## 6. Ordered beats after the first request

2026-11-03. `tools/difftest_story_beats.py` runs original `missionMenu_open`
`0x231520`, `missionMenu_run` `0x2316fc`, `mission_setAvailable` `0x1bf6d0`,
`mission_setComplete` `0x1bf770`, `game_setEvil` `0x1bf8f8`,
`game_setMadeDecision` `0x1bf980`, `game_getHubName` `0x1ec300`,
`save_findAct` `0x217d30` and `save_actChanged` `0x217f70` in `tools/ee_emu.py`,
on seeds 20973 and 7. The model added in `tools/ref_story_route.py` does not
change `menu_tick`. This is constructed state, not a played campaign.

The hub dialog that sets the next available bit, and the rule that a
registered menu task blocks that dialog, stay
`t3/research-mission-unlocks` `e5c6176`
(`docs/spec/mission-unlocks.md` lines 46–113 and 127–232). The mission 2
level list, the same-session offer, the pre-load stop, and the unstubbed
helper fault stay `t3/research-mission2-route` `b8e2d11`
(`docs/mission2-compose.md` lines 42–46, 76–96 and 133–139). They are not
re-run here. `0x18ebb8` stays stubbed on the compared menu path.

### What confirm writes

**Observed / Executed:** state 0 selects the highest available mission in
1..12, as a row, or row 0 when none of those is available. Mission 0 is not
a row. Completing the current mission does not move that row. Calling
`0x1bf6d0` for the next mission does not move it either, until down or until
`missionMenu_open` runs again and its state-0 tick does. Down will not step
onto an unavailable mission and will not skip one. Up will sit on a locked
row. Evidence: `opening_row` and `campaign_tick` in
`tools/ref_story_route.py` lines 87–91 and 139–176, compared on both seeds.

**Observed / Executed:** column 0 of state 8 copies `g_missionTable`
`0x4fe540` row `+0x08`, or `+0x0c` when `game_getEvil` is set and that
pointer is set. Only three rows have an evil pointer. The pending name and
the act from `save_findAct` with current act −1 are:

| Mission | Row | Story level | Evil level | Act |
|---|---:|---|---|---:|
| 1 | 0 | `blood1` | none | 0 |
| 2 | 1 | `innovat1` | none | 1 |
| 3 | 2 | `islc1` | none | 2 |
| 4 | 3 | `wat1` | none | 3 |
| 5 | 4 | `tormenta` | none | 4 |
| 6 | 5 | `swamp1` | `swamp2` | 5 |
| 7 | 6 | `valor` | none | 6 |
| 8 | 7 | `fire1` | none | 7 |
| 9 | 8 | `storm1` | none | 8 |
| 10 | 9 | `fay2` | `fay1` | 9 |
| 11 | 10 | `nit1` | none | 10 |
| 12 | 11 | `bossgood` | `bossevil` | 11 |

Orientation becomes `0xff`. Mission bytes and the seed are unchanged across
those ticks. Difficulty 1 reads that difficulty's bytes, not difficulty 0's,
and its evil bit is bit 1 of the evil byte: bit 0 still selects the story
level of the first row that has an evil pointer. `0x231078(0)` returns 1 on
a cleared mission row, and a confirm then writes `blood1` while mission 1's
byte stays 0. Later rows return 1 only when that mission is available.
The twelve `(story, evil, act-from-minus-one)` tuples above are asserted
against the image, and each evil name is the same act as its story name.
Evidence: `tools/difftest_story_beats.py` lines 59–72 and 310–318, and
`story_column_open` in `tools/ref_story_route.py`.

Medal and bonus columns are not re-run. The fade values passed here are 0
and 128; the exact-128 test stays `e5c6176` and is not remeasured.

### Between two story levels

**Observed / Executed:** `save_findAct` / `save_actChanged` from current act
−1 and from act 0. `hub`, `hub2`, `blood1`, `strife`, `drundar`, `drunarm`
and `drunare` are act 0, including `hub2` from inside act 0, because `hub`
is a prefix of `hub2`. `innovat1`, `inmine1`, `inmine2` and `innovat2` are
act 1, so the mission 2 menu request is an act change from act 0, and the
three later mission 2 names are not a further change from `innovat1`.
Missions 3..12 in the table above are each a further act. The quest-list
clear that runs when `save_actChanged` is nonzero was not executed in this
file. Evidence: `find_act` / `act_changed` lines 117–136.

**Observed / Executed, narrow:** `hub2` is `game_getHubName` only after
`game_setEvil(1)`, `game_setMadeDecision(1)` and mission 1's completion bit
on difficulty 0. Mission 2's completion bit does not replace that. The wider
difficulty matrix stays `e5c6176` / `b8e2d11` and is not repeated.
Evidence: `hub_name` lines 108–114 and `check_hub`.

**Observed / Executed:** a state-2 tick reads the pad when the word at
`0x8e2f10` is `0x3f800000` (float 1). A direction tick leaves it unequal to
that value, and the next cross is not read. Writing 1 back, in the test
rather than by an original task, lets the next cross through. `missionMenu`
draw `0x232300` is then entered with `follow` clear while the menu stubs
stay installed: `res_find` `0x17365c`, pause-menu open `0x18cbfc`, and
helper `0x18ebb8`. Those three callees do not run. The draw faults on an
8-byte write at `0x00000010` (pc `0x0017b968`). The store goes through the
display-list cursor at `0x44fe10`, which is 0 in this image, plus `0x10`.
The free-count word at `0x44fda4` is `0x88b8`, which is not below 3000, so
the skip in front of that store is not taken. This is not the helper fault
on `b8e2d11`. Who sets `0x8e2f10` back to 1 during play is **Unknown**.
Evidence: `tools/difftest_story_beats.py` lines 510–525.

**Observed / Executed:** reopening the menu stores state 0, clears
`0x8e2f00`, the countdown and the mark, and keeps the row, a nonempty
pending string, orientation and pause until the state-0 tick. That tick then
selects the new highest row and still leaves the old pending string. The
cancellation countdown and the "counter 0 is still registered" rule are
`e5c6176`; they are not remeasured. Evidence: the reopen check in
`difftest_story_beats.py` lines 430–446.

### What is still not a route

**Inferred from cited research, not re-executed:** after this file's `blood1`
request, the keyed exits request `strife` or `drundar`, and the ordinary
scripts continue toward `drunarm` or `drunare`. The explicit `grantMission(1)`
found there is the demo branch (`t3/research-strife-drundar`
`docs/strife-drundar.md` lines 249–255). After the menu writes `innovat1`,
the executed mission 2 chain is `innovat1` → `inmine1` → `inmine2` →
`innovat2` → hub, stopping at loader `0x1e55c0` (`b8e2d11`, lines cited
above).

**Unknown:** physical approach and use; the loader body and arrival; who
completes mission 1 on the ordinary path; in-level beats for missions 4–12;
hub2's dialog choices beyond the cited mission-2 and mission-3 offer;
the body that restores `0x8e2f10`; `0x18ebb8` beyond the cited fault.
Mission 3's in-level writers are section 7. A file that contains
`grantMission` is not, by that fact, the next beat. No continuous
hub → `blood1` → later mission session was run.

### What the client can implement from this

1. Open the mission menu on the highest available mission in 1..12. Mission
   0 does not get a row. Keep the fresh `blood1` path in sections 1–4.
2. Story confirm requests that row's story level, or the evil level for
   missions 6, 10 and 12 when `game_getEvil` is set. Row 0 still requests
   `blood1` when mission 1's available bit is clear; do not treat that as
   the hub having offered the mission. The offer itself is the cited dialog.
3. Do not advance the open cursor when a mission is completed. Advance on
   down, or on the state-0 tick after reopen, once `0x1bf6d0` has set the
   next bit. Do not skip a locked row.
4. Treat `0x8e2f10 == 1.0` as required before a state-2 tick will read the
   pad. Do not call draw `0x232300` to restore it until that fault is
   explained.
5. Keep mission bytes across the menu write. On the load, an act change is
   `save_actChanged`: the mission 1 names and both hubs stay in act 0;
   `innovat1` leaves act 0. Apply the existing quest clear only when that
   predicate is nonzero.
6. After `blood1`, follow the cited strife/drundar note, and do not mark
   mission 1 complete on entry. After `innovat1`, follow the cited mission 2
   chain through `innovat2` and stop where that note stops. Mission 3 can
   follow section 7. Missions 4–12 can request the table level and then
   refuse: their in-level beats are not established here. Mission 4's
   availability bit is the hub entries in section 7, not a side effect of
   granting mission 3.
7. Keep dialog admission on the live run task (`e5c6176`). A nonempty
   pending string does not mean the menu is idle, as the reopen check shows.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["difftest_story_beats.py","--elf","local/SLUS_209.73"]; runpy.run_path("tools/difftest_story_beats.py", run_name="__main__")'
```

Both seeds: 148 checks, 0 failed. The section 5 story-route command still
passes, 26 menu snapshots per seed. Preload stdlib `dis`, then
`python3 -m unittest discover -s tools -p 'test_*.py'` is 662 tests.
Section 7 has its own command.

## 7. Mission 3 after the islc1 request

2026-11-03. The menu confirm that writes pending `islc1` stays section 6.
Hub2's two choices that call `mission_setAvailable` for mission 3 stay
`t3/research-mission2-route` `b8e2d11`
(`docs/mission2-compose.md` lines 141–148) and are not re-run. Quest add and
remove stay `t3/research-quest-log` `28f1ccd`
(`docs/spec/quest-log.md` lines 207–217); this section only checks the
mission bytes and the quest count those entries leave. `dialog_onMsg` is
not run on these dialogs. The condition results below are the script
entries themselves.

Every executed entry goes through `scr_load` `0x13e8f8`, `scr_registerNatives`
`0x141310` and `script_runByName` `0x1ed694` in `tools/ee_emu.py`, on seeds
20973 and 7. Mission bytes start at `0xA0`. Quest slot bytes start at
`0x5A`, and the other three players' quest counts start at `0x5A5A5A5A`.
The pending level and entrance start as sentinel strings. One player,
difficulty 0. Item search, help text, cutscene lookup and sound playback
are stubbed and recorded. No dialogue text is copied.

### Level start

**Observed / Executed:** `islc1` `start` at script `0x30c` calls
`setMissionAvailable(3, 1)` at `0x340`, `setv(startedMission3, 1)` at
`0x374`, `setv(currentMission, 3)` at `0x3a8`, and `postAction(absorb)` at
`0x400`. Record 0's mission-3 byte becomes `0xA1`. Records 1–3 stay `0xA0`.
Mission 4 stays `0xA0` on all four records. The quest count stays 0. The
pending level stays the sentinel. The same three stores, without the post,
are `islcave1` `start` at `0x44` (`0x78`, `0xac`, `0xe0`).
Evidence: `tools/difftest_story_mission3.py` lines 244–261.

**Observed / Executed:** the posted `absorb` at `0x478` runs through
`script_runPostAction` `0x1edac0`. A missing `sawislc` is read as 0 and
then negated, so this first visit calls `cutScene` at `0x4dc` and stores
`sawislc` 1 at `0x510`. The script argument is `islcave`. The recorded
`cut_start` name is `islcave.cut`, and its resource is 0. `res_find` is
called with lump `.lmp` and entry `islcave.cut` and returns 0, because
this prepare leaves the level name empty. Running `absorb` again does not
call `cut_start`, and the variable stays 1. This is the request, not a
played cutscene. Evidence: lines 264–288.

### Dialog, quest, and the exits from islc1

**Observed:** `islc1` `mermaid.dbin` has three nodes. Nodes 0 and 1 use
condition `if4257`. Node 0's only choice has no action and targets node 1.
Node 1's action is `setvdea6` and targets node 2. Node 2 uses `ifa305` and
closes. No dialog text is copied. Evidence: lines 433–446.

**Observed / Executed:** `if4257` returns 1 when `wa_metKerriel` is absent
or 0, and 0 when it is 1. `ifa305` returns the opposite. The first-true
node rule would therefore open node 0 before the meeting and node 2 after
it. That selector was not run, so the reachability is **Inferred** from
those returns and the node order. Evidence: lines 297–308.

**Observed / Executed:** `setvdea6` at `0xb08` stores `wa_metKerriel` 1 at
`0xb3c` and calls `addQuest` at `0xb70`. The quest count becomes 1. The
stored title and body match that call's two script arguments. Record 1's
quest bytes stay `0x5A` and its count stays `0x5A5A5A5A`. Mission bytes
stay `0xA0`. Evidence: lines 280–295.

**Observed / Executed:** five `islc1` entries request another level and
entrance `boat`, and they set orientation `0xff` because no object is
selected. Mission bytes stay `0xA0`.

| Entry | Pending level |
|---|---|
| `lostHope` `0x7d0` | `islsm2a` |
| `solitary` `0x840` | `islsm1` |
| `regret` `0x8b0` | `islsm3a` |
| `gnome` `0x920` | `islgnome` |
| `kerriel` `0x990` | `islc1` |

`islc1` `g_racer.dbin` has two nodes. Node 1's four choices are
`postActifb1b`, `postActi6592`, `postActi928c` and `postActifd9a`, each
with target −1. Those entries are at `0x1fc`, `0x240`, `0x284` and
`0x2c8`. Each one's only call is `postAction` of `solitary`, `lostHope`,
`regret` and `gnome`, in that order. `kerriel` is not one of the four.
Which node play selects was not run. Evidence: lines 385–407. The five
travel runs stay lines 409–427.

### islgnome entrances and islc2 completion

**Observed / Executed:** `islgnome` `entrance1` `0x1bf8`, `entrance2`
`0x1d18` and `entrance3` `0x1e38` each write entrance `one`, `two` or
`three` and pending `islc2`. The eight `killMonster` `0x144a84` calls run
when `startedQuest` is 1 and `finishedQuest` is absent or 0, which is
`failQuest`. They do not run when `startedQuest` is absent or when
`finishedQuest` is 1. `getv` of a missing name creates it at 0, so an
absent `finishedQuest` takes the same eight calls as 0. The name table is
empty. All four states still request `islc2`. The gnome journal and the
`islgoth` post are a different script and were not run.
Evidence: lines 429–456.

**Observed:** `islc2` `mermaid.dbin` node 0 uses condition `iffbe4` and
action `callScri8a40`. Node 1 uses `if9be1`. Node 2 uses `iffa37`. Both
later choices close and have no action.

**Observed / Executed:** `iffbe4` returns 0 when the one-player
`inventory_countItemByName` of `shell` returns 0, and 1 when that count
is nonzero. The stub returns 0, 1 and 2 were run. One player is the
setup, so the sum is that single return for player 0. `if9be1` returns 1
when `wa_gotBlessed` is 1. `iffa37` returns 1 when that variable is absent
or 0. The selector was not run. Evidence: lines 307–338.

**Observed / Executed:** `callScri8a40` at `0x438` calls `endMission` at
`0x280`. From mission-3 byte `0xA1` on record 0 and `0xA0` on the others,
and from a planted one-entry quest whose title is that entry's
`removeQuest` argument: `wa_gotBlessed` becomes 1, the quest count becomes
0, `removePlayerItem` calls `inventory_findItemBySubstring` (stubbed to
not found, so the bag is not shown to change), `addHelpMessage` calls
`hud_showHelpMessage`, `grantMission(3)` makes record 0's byte `0xA3` and
records 1–3 `0xA2`, and `soundSequence` calls `sound_playOnObject`. Mission
4 stays `0xA0`. The seed is unchanged. Evidence: lines 327–347.

### The cave grant, and mission 4

**Observed / Executed:** `islcave1` `callScri7351` at script 0 passes data
offset 0 to `callScript`, and that string is the public entry
`steppedOnTrigger`. The entry grants mission 3 from the `0xA0` sentinel:
all four records become `0xA2`. It calls `hud_showHelpMessage` and does not
call the item finder, does not change the `0x5A` quest slot, and does not
change mission 4. Evidence: lines 349–363.

**Observed, not executed here:** the same `setMissionAvailable(4, 1)` call
also appears in `wat1` `start` at `0x314` and `water1` `start` at `0x78`.
`grantMission(4)` appears in `water1` `steppedOnTrigger` and in the six
`shardCheck` entries of `wate2a`, `wate2b`, `wate2c`, `watg2a`, `watg2b`
and `watg2c`. Those bodies were not run. Hub and hub2 also contain mission-3
availability entries; hub2's executed pair stays the citation above.

**Observed / Executed:** four hub entries set mission 4's bit and leave
mission 3 at `0xA0`. `setMissi5f9f` `0xc88` and `setMissidce3` `0xcd4`
leave the quest slot `0x5A` and the count 0. `setMissie8e9` `0x21ac` and
`setMissic4` `0x222c` also call `addQuest`, so the count becomes 1 and the
first quest byte is no longer `0x5A`. Only record 0 changes, to `0xA1`.
Which dialog node reaches them was not run. Evidence: lines 414–431.

### What the client can implement from this

1. After the section 6 confirm writes `islc1`, `islc1` `start` makes
   mission 3 available, stores `startedMission3` and `currentMission`, and
   posts `absorb`. Do not grant the mission there, and do not make mission
   4 available there.
2. That post requests cutscene `islcave` while `sawislc` is 0, then stores
   1. The recorded `cut_start` name is `islcave.cut`. A later `absorb` does
   not request it. `res_find` returned 0 and the level name was empty, so
   the lump argument was `.lmp`. Do not claim the cut plays.
3. The mermaid action `setvdea6` stores `wa_metKerriel` and adds one quest.
   It does not change mission bytes. The node order plus the two condition
   returns say the unmet dialog reaches that action and the met dialog does
   not. `dialog_onMsg` was not run on this file.
4. The five travel entries above may request those levels with entrance
   `boat` and orientation `0xff`. They are not mission completion.
5. The three `islgnome` entrances request `islc2`. Call the eight
   `killMonster`s when `startedQuest` is 1 and `finishedQuest` is absent
   or 0. An empty name table means this does not establish a kill.
6. `islc2` `callScri8a40` is the completion: set `wa_gotBlessed`, remove
   that quest, request the item removal and the help message, set mission
   3's completion bit on all four records, and request the sound. Leave
   mission 4 clear. The item finder was stubbed, so do not remove a real
   stack from this result.
7. `islcave1` `start` repeats the availability stores. Its trigger grants
   mission 3 and requests help, without the quest removal. Treat it as a
   second completion writer, not as proof of which entrance play uses.
8. Make mission 4 available from the four hub entries, not from either
   grant. Two of those entries also add a quest. What `wat1` does after
   the menu request is section 8.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["difftest_story_mission3.py","--elf","local/SLUS_209.73","--data","/path/to/BG/DATA"]; runpy.run_path("tools/difftest_story_mission3.py", run_name="__main__")'
```

Both seeds: 90 checks, 0 failed.

**Unknown:** the loader and arrival that follow the pending `islc1` write;
which object use reaches the mermaid and racer dialogs; who gives the item
`iffbe4` tests; a name table in which the eight `killMonster` calls change
a creature; a continuous session from the hub menu through `islc2`.
Missions 4 and 5 after their menu requests are section 8.

## 8. Missions 4 and 5 after the menu request

2026-11-03. The menu confirm that writes pending `wat1` or `tormenta` stays
section 6. Mission 3's grant, and the four hub entries that make mission 4
available, stay section 7. Quest removal of a last entry leaves the
`NoQuests` placeholder (`t3/research-quest-log` `28f1ccd`,
`docs/spec/quest-log.md` lines 214–215). `dialog_onMsg` is not run.
`watmedal` and `tormedal` are not run; their `grantBronze` calls are not
these completions.

Every executed entry goes through `scr_load` `0x13e8f8`, `scr_registerNatives`
`0x141310` and `script_runByName` `0x1ed694` in `tools/ee_emu.py`, on seeds
20973 and 7. Mission bytes start at `0xA0`. Quest slots start at `0x5A`, and
the other three players' quest counts start at `0x5A5A5A5A`. Pending level,
entrance and orientation start as `PENDING-SENTINEL`, `ENTRANCE-SENTINEL`
and `0x5A`. One player, difficulty 0, selected object 0. The words at
`g_paused` `0x41b4f4`, `0x500ae8` and `g_cutsceneActive` `0x44fcd0` are 0 in
the image; each prepare writes 0 again so a paused case cannot leak, and
the pause case below then sets `0x41b4f4` to 1. The test clears the deferred
queue before each `shardCheck` tick, so a queued name is from that call.
`inventory_countItemByName` is stubbed to the count named below.
`inventory_findItemBySubstring` returns not found. `res_find`, `cut_start`,
`text_lookup`, `hud_showHelpMessage`, `sound_playOnObject`,
`sound_setPlaysWhileFrozen`, `lump_load`, `dialog_isOpen`,
`shop_openOrStock` and `net_closeLocalMenus` return 0. No player object is
planted, so `onePlayerHasItem` does not reach the finder.

### Mission 4 starts

**Observed / Executed:** `wat1` `start` calls `setMissionAvailable(4, 1)` at
script `0x314`, then stores `startedMission4` and `currentMission`, and
posts `absorb` at `0x46c` while `sawWat1` is absent. The read creates
`sawWat1` at 0; that value byte is a recorded store. `startedMission4`
and `currentMission` are planted at `0x5A` and stored as 1 and 4. Record
0's mission-4 byte becomes `0xA1` from `0xA0`. Records 1–3 stay `0xA0`.
Missions 5 and 6 stay `0xA0`. The quest count becomes 1. With the evil
byte at record `+0x4c1a` clear, the title and body are the script
arguments `stopthe5b99` and `plugthe653b`. With that byte set, they are
`floodth5019` and `penetrataf0d`. The other quest is not added. Pending
level stays the sentinel. A second `start` with `sawWat1` already 1 still
stores `startedMission4` over `0x5A` and does not post.
Evidence: `tools/difftest_story_mission45.py` lines 358–411 and 928–948.

**Observed / Executed:** the posted `absorb` runs `waterIntro`, which calls
`cutScene` at `0x4f4` and stores `sawWat1` 1 over the 0 the start read
created. The script argument is `wat1`. The recorded `cut_start` name is
`wat1.cut` and its resource is 0. `res_find` is called with lump `.lmp`
and entry `wat1.cut` and returns 0, because the level name is empty. A
direct `absorb` does the same when `sawWat1` is absent, when it is planted
at `0x5A`, and when it is already 1, and each of those stores 1. The gate
is the `start` post, not the cut entry. This is the request, not a played
cutscene. Evidence: lines 382–410.

**Observed / Executed:** `water1` `start` repeats the three availability
stores at `0x78` and the two `setv`s, with no post and no quest.
`callScri7351` is at script 0 and passes data offset 0 to `callScript`;
that string is `steppedOnTrigger`. The trigger grants mission 4 from the
`0xA0` sentinel: all four records become `0xA2`. Missions 5 and 6 stay
`0xA0`. The quest slot stays `0x5A` and the count stays 0. The stubs are
`text_lookup` of `youcomp1861`, `text_lookup` of `goodfor8172`, and
`hud_showHelpMessage`. Each returns 0, so the help callee receives empty
text ids and nothing is drawn. The item finder is not called. A `water1`
object property is `t=callScri7351`. Which use reaches it was not run.
Evidence: lines 458–489 and 892–926.

### The two water routes

**Observed:** `wat1` objects pair `key=return10c8` with actions
`newWorld57c0`, `newWorld9711` and `newWorld7517`, and `key=return6198`
with `newWorldced`, `newWorldf0d` and `newWorldd7df`. Evidence: lines
778–783.

**Observed / Executed:** `return10c8` returns 1 only when the evil byte is
set, and `return6198` returns 1 only when it is clear. Both leave the
pending-level sentinel in place. The six actions then request a level and
store orientation `0xff` over the `0x5A` sentinel, because no object is
selected. They leave the entrance sentinel and mission bytes 4, 5 and 6
at `0xA0`. `net_closeLocalMenus` is called with 0 and the stub returns 0,
so no menu is closed.

| Entry | Pending level | Key that returns 1 |
|---|---|---|
| `newWorld57c0` | `wate2c` | `return10c8` (evil) |
| `newWorld9711` | `wate2b` | `return10c8` |
| `newWorld7517` | `wate2a` | `return10c8` |
| `newWorldced` | `watg2c` | `return6198` (not evil) |
| `newWorldf0d` | `watg2a` | `return6198` |
| `newWorldd7df` | `watg2b` | `return6198` |

The key-to-action pairing is **Inferred** from those properties and these
return values. `PushTrigger_interact` was not run. Evidence: lines 413–456.

**Observed / Executed:** `newWorlde6b4` on `wate2a`, `wate2b`, `wate2c`,
`watg2a`, `watg2b` and `watg2c` requests `wat1`, stores orientation
`0xff` over `0x5A`, and leaves the entrance sentinel and mission bytes
4, 5 and 6 at `0xA0`. `net_closeLocalMenus` is called with 0 and the stub
returns 0, so no menu is closed. Evidence: lines 413–456.

### How mission 4 is marked complete

**Observed:** each `shardCheck` compares a script variable with 25:
`wate2a` at `0x13ec`, `wate2b` and `wate2c` at `0x1374`, and `watg2a`,
`watg2b` and `watg2c` at `0xd00`. While `g_paused` is 0 the entry
increments that variable. While `g_paused` is 1 it does not. Evidence:
lines 40, 134–161 and 431–446.

**Observed / Executed:** the first 24 calls, with the item-count stub at
0, leave mission 4 at `0xA0` (or `0xA1` if that byte was already the
available value), leave a planted `wat_gotShard` of `0x5A` in place, queue
`shardCheck`, and do not call the item counter. The 25th call grants when
that stub returns 1 and when it returns 2. It does not grant when the
stub returns 0. The recorded call is `inventory_countItemByName` of
`shardofwater` for player 0. One player is the setup, so that return is
the sum `playerHasItem` compares with script local `0xa4`, which this
prepare leaves 0. From `0xA0`, all four records become `0xA2`. From
`0xA1` on record 0, that record becomes `0xA3` and the others `0xA2`.
The granting call stores `wat_gotShard` 1 over the planted `0x5A`.
Missions 5 and 6 stay `0xA0`. The 25th call's stubs, each returning 0,
are that count, `text_lookup` twice, `hud_showHelpMessage`, `res_find`
(`fx.lmp`, `quest_complete.anm`), `sound_playOnObject` with resource 0,
and `sound_setPlaysWhileFrozen`. No player object is planted, so
`onePlayerHasItem` does not call the item finder. The 25th call does not
queue another `shardCheck`. The same 25 calls with the count stub at 0
do not grant, leave the flood quest in place, and leave `wat_gotShard`
at `0x5A`. After 24 unpaused calls, one call with `g_paused` set to 1
does not grant and leaves `wat_gotShard` at `0x5A`; the next unpaused
call stores 1 and grants. Evidence: lines 501–589.

**Observed / Executed:** on that granting call, `watg2a`, `watg2b` and
`watg2c` remove a planted `stopthe5b99` quest. The slot is that title
before the 25th call and `NoQuests` after it, and the count becomes 0.
`wate2a` `shardCheck` leaves a planted `floodth5019` quest in place,
including on the 25 calls whose count stub returns 0. Evidence: lines
501–589.

**Observed / Executed, and stopped:** `brokeFinalWall` on the three
`wate2` levels faults inside `addParticleOnObject` `0x146e20`: a 4-byte
read at address `0x10`, pc `0x146ecc`. No object was planted. The entry
has queued `particleLoop` and has not removed the quest or granted the
mission. The seed word is not claimed after that fault. Evidence: lines
495–505.

**Observed / Executed:** `holeCheck` on the three `watg` levels returns 0
with no plug object planted. Mission bytes 4, 5 and 6 stay `0xA0`. The
planted `stopthe5b99` quest stays. `getv` creates `wat_complete` at 0,
and that value byte is a recorded store. There is no post and no help
call. The completion stores later in that entry were not reached. What
distance would pass is **Unknown**. Evidence: lines 591–628.

**Observed / Executed:** `wate2a` `iff46` returns 1 when `wat_complete`
is absent, when only `wat_gotShard` is 1, and when both are 1. It returns
0 when `wat_complete` is 1 and `wat_gotShard` is not. The portal property
that names `iff46` was not dispatched. Evidence: lines 516–528.

### Mission 5 starts, and the gol quest

**Observed / Executed:** `tormenta` `start` calls
`setMissionAvailable(5, 1)` at `0xd34`, stores `startedMission5` and
`currentMission` over a planted `0x5A`, and posts `absorb` at `0xdc8`.
It also reads `tor_bri1` and `tor_bri5`. Each read stores 0, and that
value byte is recorded. Record 0's mission-5 byte becomes `0xA1` from
`0xA0`. Missions 4 and 6 stay `0xA0`. No quest is added. No stub runs.
The post stores `tor_beenHere` 1 over a planted `0x5A` and does not call
`cut_start`. A later `start` with that variable already 1 still posts
`absorb`. Evidence: lines 630–666 and 928–948.

**Observed / Executed:** `preStart` writes entrance `goodstart` when the
evil byte is clear and `evilstart` when it is set. It creates
`tor_beenHere` at 0, and that value byte is a recorded store. The only
stub is `lump_load` of `bust.lmp`, which returns 0, so that resource is
not loaded. Mission bytes 4, 5 and 6 stay `0xA0`, and the pending level
stays the sentinel. Evidence: lines 656–666.

**Observed:** `tormenta` objects carry `t=if87a0`, `t=if3f82`,
`t=newWorld3aa4` and `dialogscript=startDia7a53`. Which use reaches them
was not run. Evidence: lines 808–810.

**Observed / Executed:** `if87a0` calls `cut_start` and stores `sawtorb`
1 the first time. The script argument is `torb`. The recorded `cut_start`
name is `torb.cut` and its resource is 0. `if3f82` does the same for
`sawtora`, and the recorded name is `tora.cut`. `res_find` is called with
lump `.lmp` and that `.cut` entry and returns 0, because the level name
is empty. Neither calls `cut_start` when its variable is already 1.
Mission bytes 4, 5 and 6 stay `0xA0`. Evidence: lines 668–690.

**Observed:** `gol.dbin` has nine nodes. Nodes 0 and 1 use `if1b74` and
`ifb0b8` and target node 2. Node 2's condition name is empty and its
action is `setv2725`. Node 3 uses `ifa33a` and closes. Node 4 uses
`if5184` and targets 5. Nodes 5–7 use `if799d` and target the next node.
Node 8 uses `if4fec` and its action is `callScri8c36`. No dialog text is
copied. Evidence: lines 786–795.

**Observed / Executed:** `if1b74` returns 1 only when the evil byte is
set and `tor_talkedToGol` is not 1. `ifb0b8` returns 1 only when the evil
byte is clear and that variable is not 1. `ifa33a` returns 1 when talked
is 1 and `tor_gotShard` is 0, and 0 when the shard variable is 1.
`if5184` and `if799d` return 1 when talked is 1, the shard variable is 1,
and `tor_finishedMission` is 0. `if4fec` returns 1 only when
`tor_finishedMission` is 1. The first-true rule would open node 1 before
an unmet good talk and node 0 before an unmet evil talk, then node 4
once the shard variable is 1 and the mission is not finished. Node 2's
empty condition was not executed as a selector, so that inference stops
there. `dialog_onMsg` was not run. Evidence: lines 595–639.

**Observed / Executed:** `setv2725` stores `tor_talkedToGol` 1 over a
planted `0x5A` and adds one quest. The title and body are the script
arguments at `0x748`, `findthe85aa` and `findtheaf23`. Mission bytes 4,
5 and 6 stay `0xA0`. Evidence: lines 691–700.

### Tormenta completion and the side doors

**Observed / Executed:** `endtor` grants mission 5 when
`tor_finishedMission` is absent or 0. All four records become `0xA2`
from `0xA0`. Missions 4 and 6 stay `0xA0`. The variable is stored as 1,
and that value byte is recorded. With no quest planted, the `0x5A` slot
stays `0x5A`. The stubs are `res_find` of `fx.lmp` and
`quest_complete.anm` (it returns 0, so `sound_playOnObject` receives
resource 0) and `sound_setPlaysWhileFrozen`, which also returns 0.
`callScri8c36` does the same, and with a quest planted from its
`removeQuest` argument (17 characters; the text is not copied here) the
count becomes 0 and that title is replaced by `NoQuests`. Calling
`endtor` again when the variable is already 1 does not grant, does not
remove the planted quest, and calls no stub. Node 8's condition is the
already-finished test, so this file does not show that the dialog's
opening node is the visit that grants. A choice walk from node 4 to
node 8 while the variable is still 0 was not run. Evidence: lines
747–783 and 892–910.

**Observed / Executed:** eight travel entries request the next level and
store orientation `0xff` over the `0x5A` sentinel. Mission bytes 4, 5
and 6 stay `0xA0`. `net_closeLocalMenus` is called with 0 and the stub
returns 0, so no menu is closed.

| Level | Entry | Pending level | Entrance |
|---|---|---|---|
| `tormenta` | `newWorld3aa4` | `tormentb` | sentinel |
| `tormentb` | `newWorld1223` | `tormenta` | `torb` |
| `tormentb` | `newWorld9066` | `torment2` | `frontdoor` |
| `torment2` | `newWorlda629` | `tormentb` | `frontdoor` |
| `torment2` | `newWorldf608` | `torment3` | `leftdoor` |
| `torment2` | `newWorld181f` | `torment3` | `rightdoor` |
| `torment3` | `newWorld6aa` | `torment2` | `rightdoor` |
| `torment3` | `newWorldbc33` | `torment2` | `leftdoor` |

Evidence: lines 785–810.

### What makes mission 5, then mission 6, available

**Observed:** `hub` `firiona.dbin` node 14 names `setMissif825` and
`setMissi9389`. Node 17 names `setMissicaba` and `setMissi6d46`.
`firiona_bak.dbin` node 14 names `setMissif825` and `setMissibbbb`, and
node 16 names `setMissi95d5` and `setMissi4082`. `hub2` `natasla.dbin`
node 9 names `setMissif825` and `setMissi9389`, and node 11 names
`setMissi95d5` and `setMissic3ab`. The bak file's node 9 and node 12 name
the other pair. Which node play selects was not run. Evidence: lines
892–926.

**Observed / Executed:** on `hub` and `hub2`, `setMissif825`,
`setMissibbbb` and `setMissi9389` set mission 5's bit on record 0 only
(`0xA1`) and add no quest. Missions 4 and 6 stay `0xA0`. On `hub`,
`setMissi95d5` and `setMissi4082` set mission 6 the same way with no
quest. `setMissicaba` and `setMissi6d46` set mission 6 and add one quest
whose title and body are `destroy8fcc` and `traveltc3c3`. On `hub2`,
`setMissi95d5`, `setMissi4082` and `setMissic3ab` set mission 6 and add
no quest. `setMissibbbb`, `setMissi9389` and `setMissi6d46` on `hub`, and
`setMissibbbb`, `setMissi9389`, `setMissi4082` and `setMissic3ab` on
`hub2`, also call `changeSwoop` and `activateStore`. The stubs are
`dialog_isOpen` and `shop_openOrStock`, both returning 0, so no shop is
opened. Granting mission 4 or mission 5 does not set the next available
bit. Evidence: lines 812–869.

### What the client can implement from this

1. After the section 6 confirm writes `wat1`, `wat1` `start` makes
   mission 4 available, stores `startedMission4` and `currentMission`,
   posts `absorb`, and adds one quest: `stopthe5b99` when the evil byte
   is clear, `floodth5019` when it is set. Do not grant the mission
   there, and do not make mission 5 available there.
2. That post requests cutscene `wat1` and stores `sawWat1` 1. The
   recorded `cut_start` name is `wat1.cut`. A later `start` does not
   post. A direct `absorb` requests the cut again, including when
   `sawWat1` is already 1 or planted at `0x5A`. `res_find` returned 0
   and the level name was empty, so the lump argument was `.lmp`.
3. The six `wat1` actions may request the levels in the table above,
   orientation `0xff`, with the entrance left alone. Treat `return10c8`
   as the evil key and `return6198` as the other key. The use dispatch
   was not run.
4. The six return entries request `wat1` the same way.
5. Mark mission 4 complete from `shardCheck`'s 25th call while
   `g_paused` is 0, when `inventory_countItemByName` of `shardofwater`
   for the one planted player returns at least 1. A return of 0 does not
   grant. A return of 2 does. A paused call does not count. Set the
   completion bit on all four records, store `wat_gotShard`, and request
   the help message and the completion sound. That count is the stub
   return, not a bag. `text_lookup`, `hud_showHelpMessage`, `res_find`
   and the sound callees return 0. On the `watg` levels, also remove the
   `stopthe5b99` quest. Do not remove `floodth5019` from `wate2`
   `shardCheck`.
6. Do not treat `brokeFinalWall` or `holeCheck` as completed work. The
   wall entry faults at pc `0x146ecc` before the quest removal. The hole
   entry returns without the completion stores when no plug object is
   planted.
7. `water1` `start` repeats the availability stores. Its trigger grants
   mission 4 and requests help, with no quest edit and no 25-call wait.
   Treat it as a second completion writer.
8. After the section 6 confirm writes `tormenta`, `start` makes mission
   5 available and posts `absorb`. That post stores `tor_beenHere` and
   does not request a cut. `preStart` selects `goodstart` or `evilstart`.
   `lump_load` of `bust.lmp` returned 0.
9. `if87a0` and `if3f82` request cuts `torb` and `tora` once each. The
   recorded `cut_start` names are `torb.cut` and `tora.cut`. `res_find`
   returned 0 with lump `.lmp`. `setv2725` stores `tor_talkedToGol` over
   `0x5A` and adds one quest. It does not change mission bytes.
10. `endtor`, including `callScri8c36`, grants mission 5 the first time,
    requests the completion sound, and removes the quest whose argument
    is the 17-character string at script `0x1e20`. A second call does
    not grant. The gol node's condition is true only after that
    variable is set; the choice walk was not run.
11. The eight travel entries may request the levels and entrances in
    the table. They are not mission completion.
12. Make mission 5 available from the three hub entries and the three
    hub2 entries, not from the mission-4 grant. Make mission 6 available
    from the four hub entries and the three hub2 entries, not from
    `endtor`. Only hub `setMissicaba` and `setMissi6d46` add the
    `destroy8fcc` quest. Where `activateStore` ran, the shop callee was
    stubbed.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["difftest_story_mission45.py","--elf","local/SLUS_209.73","--data","/path/to/BG/DATA"]; runpy.run_path("tools/difftest_story_mission45.py", run_name="__main__")'
```

Both seeds: 120 checks, 0 failed.

**Unknown:** the loader and arrival after pending `wat1` or `tormenta`;
which object use reaches the keys, the gol dialog and the water trigger;
a real `shardofwater` count rather than the stub; a player object for
the item removal; the `brokeFinalWall` statements after the particle
fault; the `holeCheck` distance that reaches its completion stores;
whether a gol choice walk calls `endtor` while `tor_finishedMission` is
0; `watmedal` and `tormedal`; a continuous session from the mission menu
through either grant.
