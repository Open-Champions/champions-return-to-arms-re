# `blood1` scripted flow (SLUS-20973 US v2.00)

2026-10-23. Research worktree `t3/research-blood1-scripts`, based on
`t3/research-blood1` `5107fcb`. This is a bounded script-host trace, not a
running-game or native-client completion claim. Private inputs stay in ignored
`local/`. No dialog text, level coordinates, game bytes, or raw listings are
recorded here.

**Evidence:** `tools/difftest_blood1_scripts.py` checks the pinned executable,
the disc's `blood1` script, object links, dialog graph, and three authored
cutscenes. It runs the original loader `scr_load` 0x13e8f8, binder
`scr_registerNatives` 0x141310, lookup `scr_findEntry` 0x13eac8,
interpreter `scr_interpret` 0x13ecf8 and game dispatcher
`script_runByName` 0x1ed694 through `tools/ee_emu.py`. On each of
seeds 20973 and 7 it compares 36 controlled entry/branch traces with an
authored reference of native names, argument cells, order, return cells, and
unchanged seed words. The built-ins are stubbed at their binding addresses;
their real downstream effects come from the cited subsystem research and
remain an integration task. **Observed** below means disc cells or executable
addresses; **Executed** means this focused test or a named prior difftest;
**Unknown** means no such execution is claimed. A missing entry through the
game dispatcher returned −1, as the dialog condition contract requires.

## Event order and gates

The script has **21 entries and 21 imported built-ins**. Entry offsets below
are code-relative addresses in `script.scr`; they are not EE virtual addresses.
The order is conditional: the game calls entries on level load, trigger edges,
NPC use/dialog messages, cutscene completion, and exit use. There is no
single always-running script (`docs/script.md` §1). The test checks each entry
from a controlled fresh machine, so it does not prove one continuous visit.

| Order / event | Observed entry and executed branch | Host effect / boundary |
|---|---|---|
| 1. Arrival | Three `Player1` records: default, `from=strife`, `from=drundar`; one `Portal` with `lump=jumpgate`. `start` at `0x0000` is the level-load entry. | Marker constructor 0x158928 ranks arrivals; the JumpGate constructor 0x27c694 can choose another arrival when travel is active (`t3/research-exits-walkin` `95760d9`). Exact live placement is **Unknown**. |
| 2. Initial objective | `start` calls `getMissionComplete(1)` (`0x002c`). If false, `getEvil` (`0x005c`) chooses one of two `addQuest` title/body pairs (`0x0098` or `0x00d4`). It then calls `setMissionAvailable(1,1)` (`0x0108`), sets `startedMission1` (`0x013c`) and `currentMission` (`0x0170`) to 1, and posts `absorb` (`0x019c`). If mission 1 is already complete, only the quest addition is skipped. | Quest list/mission bits and variables use `addQuest` 0x1433c8, `setMissionAvailable` 0x1420d0, `setv` 0x143540 (`t3/research-quest-log` `03c2304`). This is objective creation, **not** mission completion. |
| 3. Previously chosen door | `start` tests `getMadeDecision` (`0x01c0`). If true, `getEvil` (`0x01ec`) selects `autoPropSetState('evildoor',1)` (`0x0228`) or `('gooddoor',1)` (`0x0264`). Otherwise it leaves both states alone. | `autoPropSetState` 0x142320 reaches AutoProp slot 18. Two authored `BFfiredoor` / `BFhappydoor` records carry those names. This is the explicit door-state restore on revisit; the initial choice takes the cutscene path below. |
| 4. Opening sequence | The load-end post-action runs `absorb` (`0x03b0`). If `bl_sawBlood1` is zero (`getv` at `0x03dc`), it starts `blood1.cut` (`0x0414`), sets the variable (`0x0448`), and posts `removeActors` (`0x0474`). `removeActors` (`0x048c`) calls `deleteMonster('actor')` (`0x04b8`) after the cutscene. A repeat `absorb` does only the `getv`. | `postAction` is one retained name, executed by `script_runPostAction` 0x1edac0 at load/cutscene/dialog completion; it is not a per-frame queue. `cutScene` 0x143f1c loads the named `.cut` and calls `cut_start` 0x19b4dc. The cutscene has 12 existing-object actor records (nine Kobold, one shaman, two tough); 11 hostile placements have `name=actor`, the cleanup target. Actual binding, deletion count and camera playback are **Unknown** here. |
| 5. NPC contact | One `NPC` has `dialogscript=startDia1ce`. Direct use runs that entry (`0x05e4`) and calls `startDialog('natasla',1,0)` (`0x0620`). One rectangular `Trigger` has `t=ifdcc4`; its entry (`0x0734`) opens the same dialog and sets `metNatasla=1` only when that variable was zero. | `Trigger_run` 0x1ecf3c is sampled on the 15-list schedule and runs the script on occupancy edge (`95760d9`). `Player_interact` 0x1b2640 and `Creature_interact` 0x116bd8 gate direct NPC use by prompt/facing/mutex (`t3/research-dialog` `334578d`). The script alone does not establish a successful live talk. |
| 6. Dialog choice | `natasla.dbin` has 9 nodes. Nodes 0–5 require `ifb5cc` (`0x07f4`: decision absent); node 6 requires `ifb7fd` (`0x0a24`: good); node 7 requires `if3877` (`0x0a98`: evil and talked); node 8 requires `ifa824` (`0x0b4c`: evil and not talked). The decision graph's terminal actions are `setEvil3024` (node 2) and `setEvil1037` (node 5). Node 8 can run `setva4d6`, marking talked. | Dialog message 0 picks the first true start-node condition; message 1 runs a choice action; message 3 runs the post action after close (`334578d`, `tools/difftest_dialog.py`). The test asserts node conditions, edges, and actions, but does not drive a whole rendered conversation. |
| 7a. Good decision | `setEvil3024` (`0x0868`) calls `setEvil(0)`, `setMadeDecision`, then posts `gooddoor` (`0x08e4`). `gooddoor` (`0x027c`) starts `gooddoor.cut` (`0x02a8`). | `setEvil(0)` has no clearing effect in the original handler 0x142058 (`docs/script.md`); a prior evil bit cannot be assumed cleared. At 3.93 s the cutscene's type-3 key targets actor 0, `BFhappydoor`, and dispatches virtual slot 3 with argument 1 (`docs/engine.md`). For Triggerable AutoProps that advances state via 0x23d1fc → 0x23d2ec; live collision passage is **Unknown** here. |
| 7b. Evil decision | `setEvil1037` (`0x08fc`) calls `setEvil(1)`, `setMadeDecision`, marks `talkedToNatasla=1`, removes the initial quest, adds the alternate objective, and posts `evildoor` (`0x0a0c`). `evildoor` (`0x02c0`) starts `evildoor.cut` and posts `giveshard`. | `giveshard` (`0x0330`) requests `givePlayerItem('shardofwar',0,0)` and queues `checkShardCount` with `addDeferedCall` 0x144160. That deferred entry (`0x04d0`) shows a help notice and checks slots 0–3; each count above 1 requests one removal for that slot. This is a one-pass per-slot limit, not a loop until the count reaches one. Item creation/removal is **Unknown** in this focused script-host test. |
| 8. Choice exits | Two `PushTrigger` records have keys `returnab41` (`0x0638`, true when good) and `returnc2d4` (`0x06b8`, true when evil). On use, `newWorld1c57` (`0x0674`) requests `strife`; `newWorldbcf6` (`0x06f0`) requests `drundar`. Both entries return 0. | `PushTrigger_prompt` 0x1eca94 evaluates `key` and `PushTrigger_interact` 0x1ecc70 runs `action` only on use (`95760d9`). `newWorld` 0x143dd0 passes the network gate, then requests the level via `script_setNextWorld` 0x1472c4; a successful integrated transition is **Unknown** here. The `Portal` is a separate JumpGate menu path, not either use exit. |

The cutscene files are **Observed**: `blood1.cut` has 143 keys, 12 actors,
32 camera keys and ends at about 31.30 seconds; `gooddoor.cut` has 13 keys,
2 actors, 12 camera keys and ends at about 8.47 seconds; `evildoor.cut` has
12 keys, 2 actors, 11 camera keys and ends at about 7.59 seconds. Its type-3
key at 4.91 s targets actor 1, `BFfiredoor`, by the same slot-3 path. Both
door cutscenes request binding existing `BFhappydoor` / `BFfiredoor` objects
by name (both actor flags at +0x2b are zero). Whether binding succeeds in a
loaded level is **Unknown** here. All three have header flag 8. Camera actor
−100 keys include position/yaw/pitch,
fade/cut and field-of-view types. `cut_evalCamera` 0x19712c and
`cut_runTask` 0x199928 are the host paths described in `docs/engine.md`;
the focused test asserts metadata and calls to `cutScene`, not frames or
pixels. AutoProp passability follows the end of the state animation
(`docs/monsters-2.md` §6); the key request alone does not prove a traversable
door during an integrated visit.

## Enemy, boss, completion, and hub boundary

**Observed and asserted:** the 21 imported built-ins have no
`generateMonster`, `showMonster`, `killMonster`, `grantMission`, or direct
`newWorld('hub')` path. There is no blood1 script boss or kill-count end
condition. The 140 authored Kobold/Koboldtough/koboldshaman/WarWraith
placements come from `objects.ob` and factory construction on load, not a
script spawn (`tools/difftest_blood1.py` and
`tools/difftest_blood1_enemies.py`). The opening cutscene choreographs
existing hostile actors and later requests deletion of `actor`-named
placements. The level's only walk-in `Trigger` starts NPC dialog; it does
not request enemy activation. AI wake/engagement through proximity,
cutscene restoration and the real world scheduler remain **Unknown** in
this task.

The blood1 exits lead to `strife` or `drundar`, **not directly to the hub**.
`t3/research-quest-log` `03c2304` asserts those destination scripts'
`exitzone` cells: a `demoRunning`/counter branch (threshold above 150)
calls `grantMission(1)` and `newWorld('hub')` (`strife` `0x1abc`/`0x1ae8`,
`drundar` `0x19ec`/`0x1a18`). Other branches request alternate levels.
The hub then has separate dialog action entries that make mission 2
available; mission completion alone does not prove the unlock action ran.
These are **Observed disc script paths**, not a continuous executed
blood1 → exit → mission-complete → hub trace. That cross-level branch,
including its demo/counter inputs and the real transition, remains a
playthrough gate. A native port must not award mission completion at a
blood1 exit just because the player reached it.

## Ordered native port work

1. Load `blood1` records, arrival markers, script image and object identities
   in authored order; keep explicit refusals for unsupported constructors.
   Preserve the asserted default/from-level marker variants, each keyed
   PushTrigger action pair, and JumpGate arrival priority. Check the authored
   entry and built-in call offsets before accepting a different script image.
2. Implement `start` and post-action timing with mission/quest/variable state,
   then the opening cutscene and actor cleanup. Keep the camera, player
   freeze/unfreeze and cutscene key scheduler tied to the original host.
3. Bind `Trigger_run` and NPC use to the nine-node dialog graph, including
   mutex, swoop, messages and the post-action timing. Test both decision
   paths and repeated visit conditions.
4. Bind both AutoProp doors to the named objects. Compare door state after
   each cutscene and on a revisit; execute cutscene object slot-3 keys and
   the explicit `autoPropSetState` restore. Preserve the zero create flags
   and the asserted camera-key type sets for each cutscene. Do not infer an
   opened collision path from a cutscene request alone.
5. Instantiate and fight the authored hostiles with real handles, targeting,
   damage, death, drops and credit. Their absence from script imports means
   no synthetic spawn event should stand in for the authored records.
6. Implement the two keyed PushTrigger use exits and the separate portal;
   carry state to `strife`/`drundar`, execute the destination `exitzone`
   branch, return to the hub, then verify the distinct mission-2 unlock
   action. Replay save/load and both good/evil routes before claiming the
   first story mission completable.

Related contracts: `t3/research-script` `52984db` (`docs/script-effects.md`,
`tools/difftest_script_effects.py`); `t3/research-dialog` `334578d`
(`docs/dialog.md`, `tools/difftest_dialog.py`); `t3/research-quest-log`
`03c2304` (`docs/spec/quest-log.md`, `tools/difftest_quest_log.py`);
`t3/research-exits-walkin` `95760d9` (`docs/exits-walkin.md`,
`tools/difftest_exits.py`). The latter tests execute host functions on
constructed states; their findings are inputs to the port order, not a
claim that this task reran a live level.

## Verification

All checks used `PYTHONDONTWRITEBYTECODE=1` and ran serially. The audit-fix
rerun asserted all 21 entry offsets, 21 reported built-in call sites, three
arrival variants, both keyed exit/action pairs, both door actor create flags
and all three camera-key type counts. The focused script trace passed 36/36
branch cases on **each** seed (20973 and 7), both through the interpreter and
the game dispatch wrapper; the full unit suite passed 652/652. Earlier
blood1 loader/factory and enemy difftests passed on both seeds (363 records, 351
factory selections, 140 hostile placements). The focused `difftest_amx.py`
shipped-script group passed A1–A6 for this one script: all 21 entries,
84 compared runs and 174 native calls. `difftest_dialog.py` passed 10/10
suites per seed; `difftest_exits.py` passed 598 comparisons per seed;
`difftest_quest_log.py` passed 14 controlled probes across both seeds and
three disc scripts; `difftest_script_effects.py` passed 15/15 suites; and
`python3 -m unittest discover -s tools -p 'test_*.py'` passed 652/652.
The command and output log is ignored under `local/`; the tests do not
establish a continuous original or native playthrough, resource return,
rendered camera motion, live NPC choice, combat or collision state.
