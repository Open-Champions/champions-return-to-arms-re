# Level arrival: deferred errors and equipment publication, round 2

2026-10-27, extending `9dd4904603ae0d8a46e57454cf5c84b1f25c8fd9`.
**STATUS: PARTIAL.** Both client refusal conditions have narrower, executed
contracts below. Neither a destination-specific command census nor a playable
arrival is established. Evidence is from the US v2.00 executable and synthetic
state in `tools/difftest_loading_arrival_r2.py`; no running-console claim.

## Deferred condition: error handling documented; arrival commands unknown

**Observed:** `0x1ed5a0` calls `0x1ed694` at `0x1ed5f4`, then overwrites the
return register with the front count at `0x1ed5fc`. It continues in order, without
branching on the script result. It neither retries the current name nor aborts
the pass because of a returned result. At `0x1ed63c–0x1ed644` it clears the back
count, assigns its captured value to the front count, and increments parity.
Returning through `0x1ed648` completes this pass; there is no success flag and
no requirement that the newly promoted front be empty. The loading owner calls
the wrapper `0x1eda24` at `0x322e6c`, as established in round 1.

**Observed:** the host wrapper `0x1ed694` initializes its result cell to zero
at `0x1ed6e8` on successful entry lookup. It calls VM entry `0x13ecf8` at
`0x1ed70c` and replaces the VM error return with the result cell at `0x1ed714`.
Missing name or absent machine returns minus one; neither stops queue traversal.
A reported VM error terminates that script execution according to VM semantics;
the queue then continues with the next name. It does not skip the failed VM
instruction and resume the same script after it.

**Executed, `deferred_errors`, 20 cases:** original wrapper, queue, entry lookup,
loader and interpreter run without script-body stubs. Authored synthetic scripts
cover successful execution, missing entry, HALT codes 0/4/27/minus-one, bounds
failure and division by zero. The reference VM runs the same entries in order.
In every case the following entry writes the expected data cell; counts and
parity promote exactly once, leaving queued work for later. These are VM-reported
errors, not arbitrary native-code faults. HALT can publish its result even with a
nonzero error code; the wrapper does not turn every nonzero error into result zero.

**Observed, Executed, `unbound_native`, one case:** an unregistered native's
zero handler makes the original jump to address zero. Function emulation stops
there; the following queued entry is not reached and count/parity promotion has
not happened. There is no demonstrated recovery handler in this call chain.
**Unknown:** real hardware/OS behavior after such a fault. This is not evidence
that all client refusals should be ignored. A native the client cannot implement
may have essential effects even when the original queue ignores return values.

**Unknown:** which queued entries and built-ins execute for the client's actual
single-player destination, save and prior state. The queue contains entry names,
not a fixed list of built-in commands. Existing loader evidence in `docs/script.md`
section 2.1 locates script attachment `0x1ed650` and initial entry calls at
`0x217acc/0x217bac`; their execution can enqueue work. This round has not executed
the actual destination loader/script/state into the queue. A static call inventory
would not prove the dynamic path. Resolve this with an authorized read-only
arrival fixture and a trace at enqueue `0x1ed52c`, dispatch `0x1ed694`, and native
call `0x141050`; retain counts/addresses and authored descriptions, never payload
names or script bytes in tracked artifacts.

## Equipment condition: publication and specialized I/O documented in fixtures

**Observed, Executed, `player_publication`, four cases:** the constructor
`0x1a1d28` writes the slot index at player `+0x3c8` at `0x1a2200`. Unless
player byte `+0x462` is nonzero (display-only), `0x1a221c` publishes the player
pointer to record `+0x43d8`, where record = `0x4d8af0 + index * 0x4c30`.
The probe runs the original constructor slice `0x1a21e8–0x1a2220` for indices
0/1 and both display-only values; the earlier constructor/resource calls are
outside execution. For index zero the published address is `0x4dcec8`, exactly
the address visited by loading warm-up. Setting only an unrelated client player
pointer is insufficient to satisfy the original lookup.

**Observed, Executed, `slot_publication`, 14 cases:** the common publication
store in equip function `0x1c27c0` is `0x1c2ce4`, writing the item pointer to
record `+0x43f0 + 4 * selected_slot`. The probe executes that store and its branch
for two record indices and seven synthetic slots. Selection, inventory validation,
weapon conflicts, hooks and stat updates are outside this slice; this does not
prove the whole equip function or initial inventory reconstruction.

**Observed:** scanner `0x1a30b0` maps specialized slots through table `0x535d40`:

| Equipment slot | Branch address | Cache address for player index zero |
|---|---|---|
| 3 | `0x1a3430` | `0x866648` |
| 4 | `0x1a31e8` | `0x8659e8` |
| 9 | `0x1a32b0` | `0x865ca8` |
| 10 | `0x1a3248` | `0x865b48` |
| 11 | `0x1a3310` | `0x865e08` |
| 12 | `0x1a3370` | `0x865f68` |
| 13 | `0x1a33d0` | `0x8660c8` |

**Observed, Executed, `specialized_slots`, 28 cases:** add `index * 0x58` to
these addresses. With the environment gate enabled (`word[0x4f85b0] != 0`) and
item-definition `+0x30 != 0`, every route builds an identifier through `0x107edc`,
removes its last four characters at `0x1a34a8`, then calls actual cache lookup
`0x1a2d48` at `0x1a34b0`. The formatter alone is a stub supplying an authored
synthetic identifier; string comparison/length and cache lookup execute. Matching
valid caches satisfy the scanner; pending caches younger than four draw frames
keep it pending. Record indices 0 and 1 are tested separately. This does not
establish real formatter output or all environment/category branches. Generic
model-table behavior remains the round-1 contract. The scanner consumes pointer
pairs; it does not publish persistent model pointers into the player object.

### Specialized read lifecycle

**Observed, Executed, `specialized_submission`, three cases:** after four draw
frames, with no prior submission and disc-busy predicate `0x172be8` returning
zero, `0x1a2d48` obtains metadata via `0x1a24e8` and sets cache short `+8 = 1`.
Let metadata words `+4 = begin`, `+12 = split`, and signed short `+10 = tail`.
It submits an offset of `begin * 0x800`, size
`(split - begin + tail) * 0x800`, destination cache word `+0`, and completion
pointer `0x4ef3e8` to `0x1729e8`. Cache `+0x4c` becomes
`(split - begin) * 0x800`. Source identifiers are referenced only by address:
cache byte `+0x54 != 0` selects `0x535d10`; otherwise byte `+0x56 != 0` selects
`0x535d20`, else `0x535d30`. Metadata search and disc-busy calls are stubs and
submission is captured; no private payload read is claimed by this probe.

**Observed, Executed, `io_completion`, five cases:** the original read service
`0x1729e8` saves the completion pointer at `0x7c25c0` (`0x172a7c`), clears its
byte (`0x172a8c`), records sector request words at `0x7c25b0` (active, sector,
sector count, destination), and marks byte `0x41bf90 = 1` at `0x172aa8`.
Size rounds up to sectors, offset shifts right by 11. File lookup, wait and low
I/O submission remain stubs; original request bookkeeping executes.

**Observed, Executed:** poller `0x172ca8` tests the read-active byte and mode
byte `0x41bf91`. On the ordinary path it queries `0x3618b0(1)`: nonzero keeps
pending. When idle, nonzero `0x362938()` requests retry through `0x172098` and
keeps pending. With no error it loads the saved completion pointer at `0x172d80`,
stores byte 1 at `0x172d84`, and clears active at `0x172d88`. Its alternate
streaming path calls `0x362e28`; only when remaining bytes reach zero does it
reach the same completion store. These service calls are controlled stubs;
actual media transfer, error recovery success and device behavior remain unknown.
An offline session does not bypass local media completion.

**Observed, Executed, `cache_publication`, two cases:** once submitted, a zero
completion byte keeps lookup pending. A nonzero byte causes fixups `0x179e10`
on cache `+0`, then `0x179130` on base plus `+0x4c`, copies the requested identity
from `0x8667a8` to cache `+0xc`, sets valid short `+0xa = 1`, and clears outstanding
word `0x4ef3ec` (`0x1a2f34–0x1a2f64`). Fixups are captured stubs; their actual
resource transformations remain unknown. Importantly, this call returns zero
and leaves both output pointers zero. The *next matching lookup* returns one
and publishes `(base + offset, base)` into its two output cells. A ready boolean
without identity, valid resource data and both pointers does not implement this.

**Observed, Executed, `header_selection`, four cases:** header loader `0x1a2680`
selects identifier address `0x535c08` when player count `0x4d8ae0 < 2` and byte
`0x506040 == 0`; otherwise it selects `0x535bf8`. This is a player-count/override
choice, not a network-mode test. Header contents and selection of actual equipment
metadata are not executed here.

**Inferred offline arrival requirements:** publish the actual player into its
record, preserve/rebuild actual equipped-item pointers, supply generic model pairs
or the applicable specialized metadata/resources, service local I/O to completion,
perform resource fixups and matching cache publication, then rescan. No peer or
server operation is needed for these local paths. The two resource fixups, actual
formatter/header search, full inventory/constructor behavior and real destination
script path remain **Unknown as end-to-end arrival behavior**. Keep the client
refusal wherever these effects cannot be performed or observed; do not substitute
an empty equipment table, placeholder pointers or ignored unknown commands.

## Verification boundary

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_loading_arrival_r2.py local/SLUS_209.73`
passes 81 cases: deferred 20, I/O 5, publication 2, specialized slots 28,
submission 3, slot publication 14, player publication 4, unbound native 1,
header selection 4. The deferred group compares actual script side effects to
`ref_amx.Machine`; equipment groups compare original execution to explicit synthetic
layout/lifecycle expectations. No instruction patches or existing-vector changes.
The script checks the existing executable digest and prints counts only.

Round-1 readiness passes 47 cases; existing loading difftest passes seeds 20973
and 7; analysis unit suite passes 652 tests. No live game, native client, Godot,
rendering, actual device I/O or playable handoff was tested. Private inputs were
read-only; original disassembly was inspected only through ignored `local/`.
