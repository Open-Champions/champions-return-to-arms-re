# Mission offers: composed original dialog and script execution

2026-10-27. **STATUS: partial.** Research base `7efd3ce`; sibling quest-log
handoff read at `03c2304`. No running-game claim and no complete first-act or
campaign graph. This closes the bounded dialog-message-to-second-availability
write gap; physical interaction, completion and travel remain outside the proof.

## Execution and provenance

**Executed:** `tools/difftest_mission_unlocks.py` loads the owner's private disc
read-only, resolves the current hub through original function `0x1ec300`, and
selects the shipped dialog containing the action at script public offset
`0x7b0`. No extracted input is written. The executable SHA-256 is enforced.
Dialog reference/harness dependencies are read from local Git object
`334578d310179760daff20ea6098353a54958df8`; their APIs are unchanged.

The composed path executes original `dialog_onMsg` `0x22ee2c`, node selection
(loop at `0x22ef7c`), confirmation, `script_runByName` `0x1ed694`, interpreter
`0x13ecf8`, native dispatcher `0x141050`, and mission writer `0x1bf6d0`.
The independent dialog/script/native models receive the same private input.
Comparisons cover node, visible choices, all four players' mission/quest-list
spans and alignment/decision bytes, the packed quest-variable table and shared
random seed. Direct predicate results are also compared. Implicit emulator
fallback calls are rejected; explicitly installed host stubs remain allowed.

**Limits:** the world contains a synthetic actor; the dialog resource lookup
returns the selected shipped dialog. Localization returns synthetic text.
Camera, audio, task status, UI and other surrounding services use the pinned
harness stubs. Confirmation controls presentation-complete state, rather than
capturing controller/render timing. No level startup, physical NPC interaction,
trigger containment, item acquisition, completion, world transition or save/load
is established. This is original execution on constructed states, not a played
campaign. The old census in `docs/quests.md` remains a census outside this scope.

## Normal-mode start-node predicates

**Executed:** all 31 dialog-node predicates, including repeated conditions, are
compared in 352 states (10,912 predicate comparisons) and composed with original
start-node selection. These include each of twelve associated quest variables
independently at -128, -1, 0, 1, 2 and 127 crossed with all four mission low-bit
states, plus 64 mixed states. Difficulty and alignment/decision vary. This is a
bounded differential matrix; the general expressions below are **Inferred**
from those controls and the original command dependencies, not an exhaustive
proof over every possible imported record.

Let `A(n)` be availability bit 0, `C(n)` completion bit 1, and `V(n)` the signed
quest variable identified below. All mission reads use player 0 and the current
difficulty. `active = any(A(n) && !C(n) && V(n) != 0)` for n=1..12.
Node 0's condition is checked first, then the remaining nodes in file order;
first nonzero wins, with node 0 as fallback. This is **dialog priority**, not
travel order or inferred adjacency of mission numbers.

| Nodes | Script public offset | Condition | Associated private variable pool offset |
|---|---|---|---|
| 0 | `0x3f0` (calls `0x3524`) | active | all twelve below |
| 1, 2 | `0x11c` | !A(1) | — |
| 3 | `0x198` | A(1) && !C(1) && V(1)==0 | `0x6c8` |
| 4, 5 | `0x498` | false in tested executable's normal mode | — |
| 6 | `0x680` | false in tested executable's normal mode | — |
| 7 | `0x734` | !A(2) | — |
| 8 | `0x898` | A(2) && !C(2) && V(2)==0 | `0x6d8` |
| 9, 10 | `0x9a0` | !A(3) | — |
| 11 | `0xb04` | A(3) && !C(3) && V(3)==0 | `0x6e8` |
| 12 | `0xc0c` | !A(4) | — |
| 13 | `0xd70` | A(4) && !C(4) && V(4)==0 | `0x6f8` |
| 14 | `0xe78` | !A(5) | — |
| 15 | `0xfdc` | A(5) && !C(5) && V(5)==0 | `0x708` |
| 16, 17 | `0x10e4` | !A(6) | — |
| 18 | `0x1248` | A(6) && !C(6) && V(6)==0 | `0x718` |
| 19 | `0x1350` | !A(7) | — |
| 20 | `0x14b4` | A(7) && !C(7) && V(7)==0 | `0x728` |
| 21 | `0x15bc` | !A(8) | `0x738` used by active |
| 22 | `0x1638` | !A(9) | `0x748` used by active |
| 23, 24 | `0x16b4` | !A(10) | — |
| 25 | `0x1818` | A(10) && !C(10) && V(10)==0 | `0x758` |
| 26 | `0x1920` | !A(11) | — |
| 27 | `0x1a84` | A(11) && !C(11) && V(11)==0 | `0x76c` |
| 28, 29 | `0x1b8c` | !A(12) | — |
| 30 | `0x1cf0` | A(12) && !C(12) && V(12)==0 | `0x780` |

Offsets identify private inputs without reproducing game strings. The original
`demoRunning` native returns zero here. Nodes 21/22 are unavailable-status
branches; their predicates alone do not make them mission-granting offers.
Quest-variable reads may create absent entries with zero; preserve this effect.

## First offer and second offer

**Executed:** when mission 1 is unavailable (raw byte 0 or 2), with later mission
bytes zero and associated variables zero, opening selects node 1. Two confirms
traverse nodes 2 then 3 without a mission write. Either choice at node 3 writes
`setMissionAvailable(1,1)` through the original native path. The 20 cases cover
both choices, both initial bytes and all five difficulties.

**Executed:** 1,280 second-offer matrix cases cross two scratch-state seeds,
five difficulties, both alignment values, both decision values, all four raw
low-bit states of each of missions 1 and 2, and both choice controls. Other
missions are unavailable; associated quest variables start absent/zero:

| Mission 1 raw byte | Mission 2 raw byte | Opening node |
|---|---|---|
| 0 or 2 | any of 0..3 | 1 |
| 1 | any of 0..3 | 3 |
| 3 | 0 or 2 | 7 |
| 3 | 1 | 8 |
| 3 | 3 | 9 |

Opening alone never writes availability. At node 7, visible choice 0 dispatches
public `0x7b0`; choice 1 dispatches `0x2064`. Both execute exactly one
`mission_setAvailable(difficulty,2,1)`. Only bit 0 of mission 2's current row
changes; its completion bit and the other difficulty rows remain unchanged.
Choice 1 additionally invokes the original UI/store command path, whose host
side effects are stubbed; do not treat it as a decline that suppresses unlocking.
At node 8, choice 1 closes without an availability write.

**Executed:** public `0x734`, entered independently, returns `!A(2)` in all
16 first/second-byte combinations; its only native command is
`getMissionAvailable`. The completion prerequisite of the composed zero-variable
example comes from earlier start-node priority, not this local predicate.

**Executed suppressors:** recall, an already-running mission menu, or both
prevent script dispatch and availability writes. Independently varying each
associated quest variable proves that an available, incomplete mission with a
nonzero variable selects the node-0 active branch ahead of node 7. In particular,
setting V(1) nonzero on raw mission byte 1 changes the selected node from 3 to 0;
it does not authorize a new mission. Zero and signed nonzero controls are distinct.

## Mission-menu cancellation and task lifetime (2026-11-02)

**Observed / Executed, bounded:** `tools/difftest_mission_lifecycle.py` adds
an independent lifetime extension in `tools/ref_mission_lifecycle.py` without
changing any existing reference API or test vector. It runs the original
`missionMenu_open` `0x231520`, `missionMenu_run` `0x2316fc`, `task_add`
`0x19e4a0`, `task_remove` `0x19e664`, `task_isRunning` `0x19e5e8`, and
run-phase scheduler `tasks_call(1,-1)` `0x19e798` in `tools/ee_emu.py`.
The executable digest is pinned; implicit fallback calls and stubbed original
entrypoints are rejected. This follow-up supersedes the cancellation-countdown
Unknown in `docs/quests.md:193,357-358`; it does not replace the wider campaign
Unknowns above or below. The earlier probe's save/load exclusion still applies
to that probe, not to the bounded save-body experiments described here.

### Cancellation and the observable end

**Observed / Executed:** state 4 subtracts 16 at `0x232068`, stores that
result at `0x232074`, and continues closing if the result is **nonnegative**
(`0x232070`). It does not end merely because the counter equals zero.
With normal entry counter 127, the eight subsequent scheduled calls leave
111, 95, 79, 63, 47, 31, 15, then 0. The eighth call first writes -1, then
clamps to zero at `0x2320a4`. The cancel-input call only enters state 4;
it is not one of these eight decrements. Circle, select and inactive-slot
closure were executed offline and with the network-mode byte set, using
explicit host slot-status responses (no network session).

**Observed / Executed:** on that negative-result call, if the word at
`0x8e2f00` is zero, the original requests `net_lockLocalInput(chooser,5)`
(call `0x2320e0`), removes the run task (call `0x2320ec`) and removes the
draw task (call `0x2320f8`). It clears pause `0x41b4f4` at `0x2320a8`.
The state byte remains 4, the counter remains 0, the word at `0x8e2f00`
remains 0, and pending destination `0x41b6d0` and orientation `0x41b720`
retain their previous values. The menu-open flag is cleared on the first
closing tick (`0x232064`), well before task termination; it is not a lifetime
indicator. These statements describe the executed bodies and requested input
lock, not execution of the input-lock service or menu drawing.

**Observed / Executed controls:** starting state 4 with counters
0, 1, 15, 16, 17, 32, 127 or 128 confirms the strict-negative test. A
constructed start at 16 produces a still-running menu at counter 0; its next
call terminates. With `0x8e2f00` set to 1 or 9, crossing below zero instead
calls the stubbed `pauseMenu_close` service (`0x2320c4`), enters state 5
(`0x2320d4`) and retains both tasks. **Unknown:** natural reachability of
this nonzero-word closing branch; the tests deliberately construct it.

**Observed / Executed:** task removal changes the count at `0x44fdb8` and
compacts the 16-byte records at `0x840100`; the active scheduler cursor at
`0x44fdbc` is adjusted by `0x19e664`. Both menu registrations are absent
when the closing call returns. Subsequent original scheduler calls do not
invoke the menu and leave its residual state unchanged. Original
`task_isRunning` compares registered names (`0x19e624`) and returns zero
for the removed run task. The dialog asks this exact function at `0x22ee98`
using the run-task name at `0x540c70`; it does not inspect the state byte,
counter, pause flag or destination string.

**Inferred client contract:** represent task lifetime explicitly and use it
for the already-running-menu suppressor. `(state==4 && counter<=0)` is
insufficient, as the exact-zero and nonzero-word controls demonstrate. State
fields alone also miss explicit removal: original `missionMenu_removeTasks`
`0x2316b8` removes both registrations when `0x8e2f00==0`, retaining even a
state-2 menu's fields; with a nonzero word it leaves the registrations intact.
These removal-guard cases were **Observed / Executed** independently.

### Launch and reopening

**Observed / Executed:** acceptance enters state 5 and sets `0x8e2f00=1`.
State 5 advances to 6; state 6 advances to 7 only when the controlled fade
service returns **exactly 128** (`0x232120`); returns 0, 127, 129 and 255
stay in state 6 and increment that word. This refines the older quest table's
“128 or more” wording without changing its reference API. The next call
enters state 8 but still has both tasks. The following call executes state
8's body: clears `0x8e2f00` (`0x232198`), removes run/draw registrations
(`0x23219c`, `0x2321a8`), then copies the destination (`0x232254`,
`0x232294` or `0x2322c4` for the tested story/medal/bonus columns), and
sets orientation to `0xff` (`0x2322d4`). State remains 8 and the normal
counter remains 127; offline pause remains 1 at this boundary. **Unknown:**
actual loading, pause release by later services, fade timing and pixels.

**Observed / Executed:** opening, including reopening after cancellation or
launch, stores the new chooser at `0x4fe7ec` (`0x2315b8`) and resets:

| Field | Address | Value on return from open | Writer |
|---|---|---|---|
| State | `0x8e2efc` | 0 | `0x231628` |
| Transition word | `0x8e2f00` | 0 | `0x23162c` |
| Countdown | `0x8e2f04` | 0 | `0x23164c` |
| Selection animation counter | `0x8e2f08` | 0 | `0x231654` |

**Observed / Executed:** open re-registers run/draw tasks at priority 20;
`task_add` de-duplicates existing function registrations. Open itself retains
row/column, pause, pending destination and orientation. Its first scheduled
state-0 call initializes row/column (`0x231940`, `0x231974`) and sets pause
to 1 only offline (`0x23197c..0x231988`). Reopen controls use all four chooser
slots, retained synthetic pending text, nonzero counters and old orientation;
launch/reopen also retains the destination read from the private mission table.
A nonempty pending string therefore coexists with a newly registered running
menu and cannot establish inactivity.

**Observed / Executed composition:** ten new controls connect the real task
registry to the existing shipped dialog/VM probe, with no task-status stub.
Closing at 127, last-positive 15, constructed zero-but-running, arrival in
state 8, reopened-with-pending, and restored-active menus block predicate
execution and grants. Cancelled, launched, explicitly removed-state-2 and
restored-terminated menus admit node 7 on the controlled offer inputs; a
confirm executes exactly the mission-2 availability writer. This proves the
bounded admission boundary, not natural actor reachability or playable travel.

### Save/restore: snapshot versus live task registry

**Observed / Executed, partial:** original `save_build(0,0)` `0x221914` and
`save_load` `0x221d60` run on five phases: intro, active, closing, cancelled
and launched. Each build executes a one-player header/record-copy path.
Camera and jump-gate serializers return their documented sizes `0xc4` and
`0x1e4`; player snapshot/fixup, quest-variable enumeration/restoration,
act services and world serialization use explicit bounded host stubs. The
current level is authored test text with an empty subname. This is not a
memory-card, full checkpoint, object-serialization or world-reload proof.

**Observed / Executed in that bounded configuration:** all five builds produce
identical buffers and leave menu fields and registrations unchanged. A read
trace of the executed build body contains no reads of the tested menu fields,
pending request or task registry. Its header copies the current level from
`0x41b721` (`0x2219e4`), not the pending request. This supports absence of a
menu snapshot in this executed serialization path, not in unexecuted callees.

**Observed / Executed in that bounded configuration:** after changing the live
counter and animation counter, `save_load` retains their changed values and
current registration state. It neither rewinds an in-progress menu nor
resurrects a terminated one. Copying each buffer into an independently
initialized empty registry likewise creates no menu tasks. Load **does**
replace pending with the saved level (`0x222114`, empty-subname branch), and
sets orientation to `0xfd` (`0x22212c`). Reopening afterward resets the four
fields above while retaining this newly published request. The original
scheduler can still run an active menu after the direct load body returns.

**Inferred client boundary:** serializing a campaign record does not justify
serializing/restoring menu lifetime or treating the restored destination as
proof of inactivity. The task registry at the point of the dialog query is
the observed admission authority. **Unknown:** the ordering and effects of
all real save/load callers, omitted serializers and subsequent level teardown;
whether ordinary input can save in each constructed menu phase; full subname,
multiplayer, card and world-reconstruction behavior. Settling those requires
composing those original callers/services through the transition, not assuming
that the direct `save_load` experiment proves the completed reload lifecycle.

Reproduce the additive probe (both register seeds 20973 and 7, plus ten
composed dialog controls; private input is read only):

```
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_mission_lifecycle.py --elf local/SLUS_209.73 --iso local/game.iso
```

## Ordinary mission 1 completion (2026-11-03)

The offer and menu notes above do not mark mission 1 complete.
`tools/difftest_mission1_complete.py` runs the shipped entries in the original
interpreter. `grantMission` `0x1420a4`, `mission_setComplete` `0x1bf770`,
`getScaledTime` `0x14412c`, `gamePaused` `0x14699c`, `demoRunning` `0x141764`,
`playerHasItem` `0x145590`, `onePlayerHasItem` `0x145690`,
`removePlayerItem` `0x14598c`, `removeQuest` `0x143448`, `newWorld` `0x143dd0`,
`script_runDeferred` `0x1ed5a0` and `script_runPostAction` `0x1edac0` are the
original functions. Cutscene, sound, HUD, monster and bag-walk callees are
stubbed. `inventory_countItemByName` `0x1c5880` returns the test's counts;
`inventory_findItemBySubstring` `0x1c5a70` and `inventory_removeItem`
`0x1c1cb0` record one removal and do not walk a bag. The register seed is
unchanged. This is not a played fight, a cutscene, or a level load.

**Observed:** a full `grantMission` scan of `drunare`, `drunarm`, `strife`,
`drundar`, `blood1`, and `hub` finds five sites. The mission-1 sites are
`drunare` `levelChange` at `0xac4`, `drunarm` `shardCheckLoop` at `0x97c`,
and the `exitzone` sites already named in `docs/quests.md` (`strife` `0x1abc`,
`drundar` `0x19ec`). Each argument is 1. `blood1` has none. `hub` `start`
calls `grantMission(0)` at `0x28c4`. The four completion entries do not call
`setMissionAvailable`, `grantBronze`, `grantSilver`, `grantGold`, or
`givePlayerExp`.

### Exits do not complete it

**Executed:** real `demoRunning` returns 0. `strife` `exitzone` then requests
`drunarm`. `drundar` `exitzone` requests `drunare`. Mission 1's planted
available-only byte (`1`) stays, the post-action name stays empty, and both
deferred halves stay empty. The demo/counter `grantMission(1)` /
`newWorld('hub')` branch is the one already mapped at
`t3/research-strife-drundar` `docs/strife-drundar.md` lines 198–201 and
249–255; this run does not take it. `addHelpMessage` in that demo branch is
stubbed and is not entered.

### Evil arena

**Observed:** `CazicAvatar` `deathscript` is `callScria381`, which only calls
`bossDefeatedPause`. The four `knight` death scripts set `knight1`..`knight4`
and are not read by the completion entries.

**Executed:** `bossDefeatedPause` stores 0 into script global 0. A planted
`0x5a` is 0 after `callScria381`, and the queued name is `bossDefeatedDelay`.
With pause clear, deferred call 0 only promotes that name and leaves the cell
at 0. Call 1 stores 1. Call 252 sets quest variables `endsound` and
`firstmissionever` to 1 and does not set the post action or the complete bit.
Call 877 runs `endmission` because `killedAv` was clear: post action
`levelChange`, `removeQuest` of that entry's title, and `killedAv` stored
lowercased as `killedav` (`vars_set` already lowercases). `cutScene` and
`reapEnemies` are stubs. The mission byte is still the planted available-only
`1`. Eight paused calls never reach that post action. A second `endmission`
after `killedAv` is set does not replace a cleared post action and does not
grant.
`tools/ref_mission1_complete.py` `evil_end_frame` is this queue, using the
original `getScaledTime` as the oracle. The same threshold wording is the
unread script note in `docs/spec/arena-monsters.md` lines 959–967; the frame
indexes here are the executed ones.

**Executed:** `script_runPostAction` then runs `levelChange`. `grantMission(1)`
sets bit 1 on all four records at the current difficulty. Slot 0 goes from
the planted available value `1` to available and complete (`3`); the other
three slots, which were planted `0`, become complete-only (`2`). Direct
`levelChange` at difficulty 1 writes that same `2` into all four slots of
difficulty 1 and leaves difficulty 0's planted slot-0 value `1`. Before the
grant the probe plants gold `0x01020304`, experience `0x05060708`, thirteen
medal bytes `0x21`+mission, evil `0x2a`, decision `0x3c`, mission 2 `0x40`
on every slot and difficulty, and `0x50` in every other mission byte of the
rows this grant does not write. Those words stay, on all four player records,
so this `newWorld('hub2')` is not `game_getHubName`. It stores `hub2` at
`0x41b6d0` and orientation `0xff` at `0x41b720`. The quest list loses the
matching title and keeps the other test entry. Same-act loads do not do that
removal; both arena names and both hubs are act 0
(`t3/research-story-route-r3` `019a155`, `docs/story-route.md` lines
271–276). A same-act change keeps bags and quest-variable values
(`t3/research-inventory-reset` `6f8beb9`, `docs/inventory-reset.md` lines
48–51). Lines 127–129 of that pin are the summary that separates those
same-act bags from an act change, which takes the quest list and zeroes
quest-variable values.

### Good arena

**Executed:** `start` stores original `playerHasItem('shardofwar')` into
script global `0xc`. The count itself is stubbed `inventory_countItemByName`.
A planted `0x5a` becomes 0 when that count is 0 and 1 when it is 1. `start`
leaves planted global `0x8` (`0x5b`) and global `0` (`0x5c`) unchanged and
queues `shardCheckLoop` on the back half. The probe then stores 0 into global
`0x8` so the schedule below starts from 0. Call 0 promotes the name. Each later unpaused call increments global
`0x8`. The copy that reaches 25 clears it and compares the live count with
the snapshot. Just before deferred call 25 the cell is 24 and the front half
is still `shardCheckLoop`. `script_runDeferred` leaves the back half empty
because it promotes that half into the front count. A live count that is not
greater leaves `shardCheckLoop` on the front half. A greater count plays the
stubbed item sound and the stubbed help message, sets a 14-character quest
variable and `firstmissionever` to 1, calls `grantMission(1)`, posts
`endmission`, and leaves both halves empty. With the snapshot at 0 and the
live count at 1, that is deferred call 25, and global `0xc` is still 0.
With the snapshot at 1, call 25 clears global `0x8`, leaves `0xc` at 1, does
not grant, and leaves the front name queued; raising the live count to 2
grants on call 50 and leaves the front half empty. Twenty-five paused calls
leave the planted global `0x8` and do not grant. The mission bytes written
are the same four-record pattern as `levelChange`. Gold, experience, the
medal bytes, evil, decision, mission 2, global 0, and the other difficulty
rows stay at the sentinels planted above. `endmission` here is the stubbed
help message and `soundSequence`: it does not grant again and it does not
request a level. Pending level stays empty.

**Executed:** one `removePlayerItem` runs only when `onePlayerHasItem`
returns a count above 1. A rise from 0 to 1 grants and removes nothing. A
rise from 1 to 2 grants and removes one cell from slot 0. `inventory_findItemBySubstring`
and `inventory_removeItem` are stubs: the removal record is slot 0, index 0,
bag 0, and the bag is not walked. The real walk and equipped-pointer fixups
stay `inventory_removeItem` as already bounded in `6f8beb9`.

**Executed, separate from the grant:** `getHitPoints` is a stub.
`rallosHPcheck` queues `endDelay` when that cell is 0 or below and stores 0
into global `0x10` (a planted `0x5a`). It queues itself and leaves the
sentinel when the cell is 1 or above. The split is `(0, 1)`. `endDelay`'s
body is `gamePaused`, `getScaledTime`, `callScript('playRallosRuns')`, and
`addDeferedCall('endDelay')`, and it has no `grantMission`. Deferred call 277
is the copy that calls `playRallosRuns`. That entry's original `postAction`
is `removeRallos` and its original `removeQuest` drops the matching title;
the planted `Keep` remains and the quest count goes from 2 to 1. The mission
byte stays the planted `1`. `showMonster`, `cutScene`, and `setSaveInhibit`
are stubs. The following `script_runPostAction` runs `removeRallos`, whose
natives are all stubbed (`killMonster`, `hideMonster`, `deleteMonster`); the
mission byte and the quest count stay. Both deferred halves are empty after
call 277. `playRallosRuns` and `removeRallos` contain no `grantMission`.
Who reaches the trigger, and the real hit-point float before `getHitPoints`
converts it, stay **Unknown**.

### What the hub and the menu then read

**Executed** on the bytes `levelChange` just wrote. The grant left the planted
evil `0x2a` and decision `0x3c`. The probe then stores 0 into both, and
`game_getHubName` `0x1ec300` returns `hub`. With both of those probe stores
set to 1 it returns `hub2`. That agrees with the matrix already executed in
`docs/quests.md` lines 279–283. The arena request above does not consult it.

**Executed** with the hub script loaded on those same mission-1 bytes. The
probe sets mission 2 back to 0 before these reads; the grant had left the
planted `0x40`. `if441a` (`0x198`) is the node-3 pending predicate:
available, not complete, and `startedMission1` clear. On the completed byte
it returns 0. It returns 1 when the byte is available-only and
`startedMission1` is clear, and 0 when that variable is 1 or the byte is 0.
The unavailable offer stays nodes 1 and 2 at `0x11c` (`if99a5`). `if7b2c`
(`0x734`) returns 1 while mission 2 is unavailable and 0 after
`setMissic270` (`0x7b0`) has called `setMissionAvailable(2,1)`. That public's
body is only that native. Node 7 choice 0 in this file (`e5c6176`, lines
107–109) is `setMissic270` at `0x7b0`. Choice 1 is `setMissi3c49` at
`0x2064`. This probe runs `setMissi3c49` directly: mission 2 becomes 1,
mission 1 stays 3, and the stubbed `changeSwoop` and `activateStore` run.
`setMissid125` (`0x7fc`) is a third entry with that same native list, also
run directly here. Which dialog node reaches `0x7fc` stays **Unknown** until
that node is executed. Row helper `0x231078` returns 1 for row 0 and 0 for
row 1 until that bit is set, then 1 for row 1. Mission 1's byte stays
complete.

### What the client can implement from this

1. Do not mark mission 1 complete on the `blood1` exits or on the ordinary
   `strife` / `drundar` exits. Those exits request `drunarm` or `drunare`.
2. On the evil arena, run the avatar death entry, then the deferred delay.
   The death entry stores 0 into global 0. Set `endsound` and
   `firstmissionever` when scaled time passes 250. On the call that passes
   1500, if `killedAv` is clear, remove that quest, remember `levelChange`,
   and only then let the post-action grant mission 1 and request `hub2`.
   Do not grant on the death tick itself. Leave the planted evil and decision
   bytes as they were.
3. On the good arena, remember the `shardofwar` count at `start` in global
   `0xc`. The counter is global `0x8`, not global 0. Every 25 unpaused
   deferred calls, if the live count is greater, grant mission 1, set
   `firstmissionever`, post the help/sound entry, and do not queue another
   check. A count that is not greater queues `shardCheckLoop` again. Remove
   one `shardofwar` only from a slot whose count is above 1. Do not request
   the hub from this grant. The Rallos chain posts `removeRallos` and removes
   its own quest; it does not grant.
4. Leave mission 2 at its previous byte until a hub action runs
   `setMissionAvailable(2,1)`. Node 7 choice 0 is `setMissic270` (`0x7b0`).
   Choice 1 is `setMissi3c49` (`0x2064`), which also opens the stubbed store.
   `setMissid125` (`0x7fc`) is another writer; its dialog node is not
   executed here. The menu row for mission 2 stays locked until that write.
   `game_getHubName` still needs the evil bit, the decision bit, and the
   complete bit. The evil arena's own request is `hub2` while the planted
   evil and decision bytes stay.
5. Keep medals, gold, experience, mission 2, evil, decision, and the other
   difficulty rows at the values they had before the grant. Apply `removeQuest`
   for the evil `endmission` title and for the Rallos outro title. Do not run
   the act-change bag clear: these names stay in act 0.

**Unknown:** the fight that reaches the avatar death script; the trigger that
reaches `rallosHPcheck`; cutscene playback; the real bag cell `removePlayerItem`
would delete; the loader and arrival after `hub2` is requested; the good
path's later return to a hub; `blomedal`'s medal grants, which these entries
do not call.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import dis,runpy,sys; sys.argv=["difftest_mission1_complete.py","--elf","local/SLUS_209.73","--disc","local/disc","--seed","20973"]; runpy.run_path("tools/difftest_mission1_complete.py", run_name="__main__")'
```

Seed 7 is the same command with `--seed 7`. `local/disc` is the private level
directory, ignored, and is not named in tracked files beyond this relative path.

## Remaining research / client boundary

**Unknown:** complete campaign prerequisite graph beyond mission 1's two
completion writers above, and every offer/turn-in outside this one hub
dialog. Specifically: actual actor resource/entry binding and containment;
level startup and dialog initiation; the good arena's return to a hub;
mission 8/9 availability writers; replay and repeat paths outside tested
records; physical travel and save/load composition. No order is derived
from filenames or mission indices.

Mission 1's two completion writers are the section above. The next round
must still bind real world entry to the avatar death and to the good arena's
return, and execute the later acts' completion writers, before claiming the
first act or the campaign complete. The client's blanket campaign refusal
cannot be removed from this evidence.
A bounded client binding can cite the executed second-offer action only when
its actual dialog/resource/state inputs and admission conditions are established.

Reproduce (private read-only symlinks under ignored `local/`):

```
python3 tools/difftest_mission_unlocks.py --elf local/SLUS_209.73 --iso local/game.iso
python3 -m unittest discover -s tools -p 'test_*.py'
```
