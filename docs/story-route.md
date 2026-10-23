# Hub to the first story combat level

US `SLUS_209.73` v2.00, research worktree `t3/research-story-route`, 2026-10-23.
This is a function-level and disc-structure trace, not a running-game or native
playthrough result. `tools/ref_story_route.py` models the fresh route and
`tools/difftest_story_route.py` compares original EE functions at seeds 20973
and 7. Private archive contents and disassembly remain in ignored `local/`.

## Result and evidence boundary

**Observed, Executed:** A new character's `hub` script `start` makes mission 0
available and complete. On a fresh mission state, the first NPC dialog selects
node 1. Its choice chain reaches node 3, where either of two ending actions
makes mission 1 available and adds one quest to the character's list. The hub
`PushTrigger` leads to `warnDetect`, which sets entrance name `goodstart` and
opens the mission menu on this fresh state. The menu's row 0 story selection
writes `blood1` to `g_pendingLevel` and `0xff` to the orientation byte.
`blood1` is mission 1's story level and has hostile object records. `valor` is
mission 7's story level in the executable's mission table.

**Observed:** There is no `newWorld`, `newWorldPost`, or `simpleNewWorld`
import in the shipped `hub` script. The first story request is the mission
menu's direct pending-level write at 0x232220, not a script `newWorld` call.
`newWorldPost` is the dialog-close mechanism for other routes, not this one.
The hub gate menu is also a separate travel path; the visible portal rings
and the `Portal` object's presence do not make it the mission 1 exit.

**Unknown:** The whole NPC interaction, menu opening, terrain placement,
`blood1` archive load and first attack have not run as one original or native
session in this research. The synthetic EE harness supplies selected external
services. It does not prove that the native client can fight. No arrival
coordinate, live actor count, gear or combat outcome is claimed.

## 1. Hub setup and the opening NPC

| Evidence | Field or event | Result |
|---|---|---|
| **Observed** `hub` script `start` offset 0x2838; built-ins 0x1420d0 and 0x1420a4 | `setMissionAvailable(0,1)`, `grantMission(0)` | Mission byte 0 becomes 3 (available and complete). **Executed** by `run_hub_entry(start)` with a clean player record at both seeds. |
| **Observed** `hub` script offset 0x29bc–0x2a0c | `getv(currentMission)`, then `setv(storeLevel,0)` when the first read is zero | This is the fresh-state branch. Later `start` branches manage other missions and the `firstmissionever` variable; they must not be flattened into a universal assignment. |
| **Observed** hub `objects.ob`, NPC record 10 | `dialogscript=startDia3314`; `startDia3314` calls `startDialog` at script offset 0x003c | The object is reached by the `Creature_interact` use-button path at EE 0x116bd8, then `script_startDialog` 0x143824 and `dialog_start` 0x22fa50. |
| **Observed, Executed** `firiona.dbin`, node conditions at script offsets 0x03f0, 0x011c, 0x0198 | Fresh-state condition results for nodes 0, 1 and 3 are 0, 1 and 0 | `dialog_onMsg` 0x22ee2c selects the first true node (0x22efac), hence node 1. The node 1 → 2 → 3 choices are in the local dialog file; no dialog text is reproduced here. |
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

The actionable exit is the hub `PushTrigger` record 11, whose `action`
property selects `callScri8e04`. That entry calls `warnDetect` (script offset
0x49c0). `PushTrigger_interactPrompt` 0x1eca50 evaluates its ordered `key`
properties; `PushTrigger_interact` 0x1ecc70 dispatches the action on a use
press. A rectangle `Trigger` record 12 separately calls
`gatewaytrigger`, which invokes `trigger(portal,0)` and changes the portal
visual state. It does not name a destination. The standalone `Portal` record
6 belongs to the jump-gate system. These distinctions follow the observed
object properties and the `t3/research-exits-walkin` function trace.

`warnDetect` calls `warncheck` at script offset 0x4234. It tests an available,
incomplete mission with the matching `startedMissionN` variable set. In the
fresh mission 1 state, `startedMission1` is zero, so **Executed** `warncheck`
returns zero. `warnDetect` then calls `setEntrance(goodstart)` at offset
0x4a44 and `activateMissionMenu()` at 0x4a68. `setEntrance` 0x142a94 copies
the string into `g_entranceName` 0x4f8468. `activateMissionMenu` 0x143fa8
refuses while a dialog is still open or recall is pending, so the player must
finish the NPC conversation before this interaction. The alternate warning
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
| **Executed** `save_findAct` 0x217d30 | From current act 0, both `hub` and `blood1` resolve to act 0. No act-change clear runs for this move, so the mission byte, quest list, quest-variable values and non-quest inventory remain in their player/game owners. `valor` resolves to act 6 and would take the act-change path. |
| **Observed** `g_entranceName` 0x4f8468 and `Player1_ctor` 0x158928 | The `goodstart` name survives level loading. `blood1` has three `Player1` records: one default and two `from` records for other previous levels; none has `name=goodstart` or `from=hub`. The default marker is therefore the applicable authored marker, subject to construction and rank order. |
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

## 4. Ordered native port list

1. Run the real hub `script.scr` `preStart`/`start` and persist mission bytes,
   quest lists and quest variables in their proper player/game owners. Keep
   mission 0's initial state and fresh `storeLevel` branch.
2. Wire the NPC's use prompt to `dialogScript`, load its `.dbin`, evaluate
   initial node and visible choices using the original script VM, and run the
   selected action before the dialog closes. Preserve the shop/camera side
   branch without making it a prerequisite for the mission unlock.
3. Implement the hub PushTrigger's `key`/prompt/use path, `warnDetect` and
   `setEntrance`. Keep its warning/deferred branch and the separate walk-in
   Trigger/portal visuals. Do not treat the `Portal` gate as the story exit.
4. Run `missionMenu_open`/`missionMenu_run` with the player's lockstep pad,
   availability gate, row/column, fade and state-8 direct pending-world write.
   For the fresh route, confirm row 0's story column to request `blood1`.
5. Carry pending level, previous level, entrance, player records, quests and
   variables through `mainloop_loadRequestedWorld`. Load the `blood1` archive,
   construct destination records in order, apply the default `Player1` marker,
   terrain/free-spot placement and player construction. Do not clear campaign
   state on this same-act move.
6. Bind real enemy constructors, resources, equipment and combat services,
   then perform a native hub-dialog → PushTrigger → menu → `blood1` → first
   attack acceptance run. Compare level name, request, marker, record and
   combat traces to the original running game. The present function-level
   comparison does not close this integration gate.

## 5. Verification

Run with `PYTHONDONTWRITEBYTECODE=1` and the local owner-supplied ELF and
archives. `difftest_story_route.py` pins the executable SHA-256, checks the
shipped hub script/dialog/objects and blood1 records without outputting their
bytes, executes `start`, the opening conditions and both mission actions via
the original interpreter, then compares the original mission menu to the
reference state after every tick at seeds 20973 and 7. It checks the direct
pending request and orientation, not a full `game_loadLevel` call.

The existing `difftest_natives.py` hub script comparison exercises all 82
shipped entry points and a 60-tick synthetic script sequence. Existing
`difftest_objects.py` marker properties and the full unit suite are separate
controls. Their results do not turn this route into an integrated playthrough.

Commands run (the two `.GOB` files and `scripts_raw/hub.scr` were extracted
under ignored `local/story-route/` from the owner's read-only disc):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_story_route.py --elf /Users/syndicatemike/champions-re/SLUS_209.73 --hub-gob local/story-route/disc/BG/DATA/HUB.GOB --blood-gob local/story-route/disc/BG/DATA/BLOOD1.GOB
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_natives.py /Users/syndicatemike/champions-re/SLUS_209.73 --scripts local/story-route/scripts_raw --seed 20973 --quick -k hub.scr
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_natives.py /Users/syndicatemike/champions-re/SLUS_209.73 --scripts local/story-route/scripts_raw --seed 7 --quick -k hub.scr
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_objects.py /Users/syndicatemike/champions-re/SLUS_209.73 --quick --seed 20973 -k marker
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_objects.py /Users/syndicatemike/champions-re/SLUS_209.73 --quick --seed 7 -k marker
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

Results: story route 26/26 menu snapshots per seed; hub native comparison
3/3 properties per seed (82/82 entry points and a 68-case scripted sequence
each); marker comparison 4/4 properties per seed across four FPU models;
full unit suite 652/652. All were function-level or synthetic-fixture checks.
