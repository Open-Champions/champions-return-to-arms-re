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
