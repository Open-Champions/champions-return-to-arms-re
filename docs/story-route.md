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
Evidence: `story_column_open` lines 100–105 and the seed log of
`difftest_story_beats.py`.

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
draw `0x232300`, entered with its callees live after that direction tick,
faults on an 8-byte write at `0x00000010` (pc `0x0017b968`). Who sets the
word back to 1 during play is **Unknown**.

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
completes mission 1 on the ordinary path; every in-level exit and completion
writer for missions 3–12; hub2's dialog choices; the body that restores
`0x8e2f10`; `0x18ebb8` beyond the cited fault. A file that contains
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
   chain through `innovat2` and stop where that note stops. Missions 3–12
   can request the table level and then refuse: their in-level beats are
   not established here.
7. Keep dialog admission on the live run task (`e5c6176`). A nonempty
   pending string does not mean the menu is idle, as the reopen check shows.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["difftest_story_beats.py","--elf","local/SLUS_209.73"]; runpy.run_path("tools/difftest_story_beats.py", run_name="__main__")'
```

Both seeds: 147 checks, 0 failed. The section 5 story-route command still
passes, 26 menu snapshots per seed. Preload stdlib `dis`, then
`python3 -m unittest discover -s tools -p 'test_*.py'` is 661 tests.
