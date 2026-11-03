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

## Remaining research / client boundary

**Unknown:** complete campaign prerequisite graph, a complete first-act chain,
and every offer/turn-in outside this one hub dialog. Specifically: actual actor
resource/entry binding and containment; level startup and dialog initiation;
item and boss gates feeding completion; alternative hub/alignment paths;
variable mission arguments; mission 8/9 availability writers; replay and repeat
paths outside tested records; demo-specific behavior; physical travel and
save/load composition. No order is derived from filenames or mission indices.

The next round must bind real world entry/interaction to these dialog paths,
then execute each first-act completion writer and its positive/negative
containment/item/quest-variable controls, before claiming the first act complete.
The client's blanket campaign refusal cannot be removed from this evidence.
A bounded client binding can cite the executed second-offer action only when
its actual dialog/resource/state inputs and admission conditions are established.

Reproduce (private read-only symlinks under ignored `local/`):

```
python3 tools/difftest_mission_unlocks.py --elf local/SLUS_209.73 --iso local/game.iso
python3 -m unittest discover -s tools -p 'test_*.py'
```
