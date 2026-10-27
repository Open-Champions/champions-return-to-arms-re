# Loading-completion readiness contract

2026-10-27; extends audited research pin `3ba61c7` for the US v2.00 executable.
Evidence is **Observed** addressed instructions and **Executed** original functions
or bounded slices in `tools/difftest_loading_readiness.py`. All state is synthetic;
this is not a running-game transition or proof of the client's implementation.
The executable digest is checked against the existing loading difftest pin.

## Deferred scripts — documented

**Observed:** the load branch calls `0x1eda24` once at `0x322e6c`, after
`mainloop_startWarmup` and before the warm-up loop. That wrapper calls
`0x1ed5a0`; it does not test a persistent completion flag or drain until empty.
The actual function entry is `0x1ed5a0`, not the internal call site `0x1ed5f4`
used as its entry in one older table in `docs/script.md`.

| State | Meaning and writer |
|---|---|
| `0x86da78`, word | Front count; read during execution; assigned the back count at `0x1ed640` |
| `0x86da7c`, word | Back count; incremented by enqueue `0x1ed52c` at `0x1ed55c`, cleared at `0x1ed63c` |
| `0x4f8690`, word | Buffer parity; incremented at `0x1ed644` |
| `0x86b278`, two buffers | Each has 64 slots of stride `0x50`; front selected by parity bit 0, back by its inverse |

**Observed:** enqueue copies a name into the back buffer and silently declines
when its count is already 64 (`0x1ed550–0x1ed590`). Execution visits the current
front entries in order via `0x1ed694`, then promotes the back buffer. Clear
`0x1eda08` zeroes both counts and parity. The load/reset/save-load owners of that
clear are documented in `docs/script.md` section 2.4.

**Executed:** 12 front/back/parity combinations through the wrapper, plus a
callback that queues further work. The callback's newly queued work survives in
the next front buffer. Script interpreter bodies are stubbed, not executed by
this probe. **Inferred port contract:** `deferred_complete` can mean the one
required pass returned successfully; requiring both counts to be zero is stronger
than the original and can prevent legitimate self-deferring scripts from entering.
Attachment alone does not satisfy this pass. **Unknown:** whether the current
client can execute every destination callback; unsupported commands still refuse.

## Equipment and warm-up — documented, resource integration unknown

**Observed:** `0x322f38–0x322f9c` visits records `i < word[0x4d8ae0]`;
the player pointer is at `0x4dcec8 + i * 0x4c30`. Null pointers are skipped.
For each live pointer it calls `0x1a30b0`. Nonzero raises the warm-up word
`0x506048` to at least 3. This is recomputed work, not a saved ready byte.

**Observed:** `0x1a30b0` selects the record using player word `+0x3c8` and
record base `0x4d8af0 + index * 0x4c30`. It scans 17 equipment pointers at
record `+0x43f0`. Null items do not wait. For item slot 3, a selected pointer
from record `+0x4434 + 4 * signed_byte[record+0x4a7c]` whose definition byte
`+0x1e` is 4 skips that slot (`0x1a3118–0x1a3148`). Definition byte `+0x1c`
values 5, 6, 7 and 8 mark the scan pending directly (`0x1a315c–0x1a3178`,
`0x1a353c`). If byte `0x41b69d` is zero and word `0x44fe08` has bit
`0x10000000`, definition categories 0, 2 and 3 are skipped.

For remaining items, the switch at `0x1a31c0–0x1a31e0` selects specialized
model paths for slot indices 3 through 13 or the generic item-index lookup
`0x1083f8`. The generic path reads the two model pointers at table
`0x3e9ce0 + model_index * 16 + {8,12}`. At `0x1a3528–0x1a353c`, either
pointer being zero sets the return accumulator to 1. The specialized paths
use item/model metadata and `0x1a2d48`, with additional environment guards;
this document does not assign semantic names to unverified slot categories.

**Observed:** cache lookup `0x1a2d48` supplies both pointers when cache short
`+0xa` is nonzero and its name matches (`0x1a2d6c–0x1a2da0`). Otherwise
it zeros both outputs. Global `0x4ef3ec` owns an outstanding cache slot;
`0x4ef3f0` records the request frame. A miss can assign that slot and frame at
`0x1a2e08–0x1a2e14`. After at least four draw frames it services the read:
cache short `+8` marks submission, completion byte `0x4ef3e8` is passed to
read service `0x1729e8`, and publication performs resource fixups, sets short
`+0xa` to 1 and clears the outstanding slot (`0x1a2f28–0x1a2f64`). The read
service's internal completion-byte writer is **Unknown in this research**.
A ready flag without matching model identity is insufficient.

**Executed:** original scanner against all four null/non-null model-pointer
pairs on the generic path; original cache hit and younger-than-four-frame
pending cases; six warm-up slices with terrain/equipment/timeout variations.
Other specialized item paths and actual I/O completion remain **Unknown as
executed behavior**. The generic item's index lookup is stubbed to select a
synthetic table entry; model construction and terrain service are stubbed.

**Observed, Executed:** idle terrain decrements the counter; busy terrain
resets it to 10 (`0x322f10–0x322f34`). Pending equipment floors it to 3.
Elapsed draw-frame difference **1501 or greater**, not 1500, forces it to zero
(`0x322fa0–0x322fc0`, signed comparison against `0x5dd`). The branch then
continues even if work is pending. **Inferred port contract:** a safer refusal
on timeout is permitted by the client's existing policy, but timeout is not
evidence of resource readiness. Offline play does not exempt equipment work.

## Peers — documented; bypassed offline

**Observed, Executed:** signed byte `0x402791 == 0` jumps directly from
`0x323008` to `0x323064`. There is no network wait or peer predicate call
on that path, independently of the peer table contents. **Inferred port
contract:** an explicitly offline session can report this barrier satisfied
without opening a network connection.

Online, the session calls `0x132e90(1,0)`, clears heard flags with `0x13dfc0`,
then polls `0x13e008`. Clear visits word count `0x4027c4`, table base
`0x5bf838`, stride `0x44e0`, and zeros each peer word `+0x44d0`.
The predicate accepts an entry if *any* of signed bytes `+0x44d4` (local),
`+0x44d5` (dropped), `+0x44d6` (kick state) is nonzero, or heard word
`+0x44d0` is nonzero; one unqualified entry returns 0. Zero entries returns 1.
Accepted packet processing sets heard to 1 at `0x13b75c`; local/dropped/kick
writers are addressed in `docs/netcode.md`'s peer layout table.

**Observed:** while waiting, `0x132e90(1,1)` runs when the draw frame changes.
The loop also exits if word `0x40279c >= 601` (`0x323054–0x323060`), so its
exit alone is not proof that every remote peer replied. Existing
`symbols/lag.tsv` traces that word's writer to `0x134408–0x134448`.
**Executed:** seven original clear/predicate table cases, including a second
unheard peer, and three caller slices for offline bypass, online ready and
online stall escape. Packet reception, sockets and synchronization are not
executed; online readiness in the current client remains **Unknown**.

## Stores and saves — documented dispatch; generated contents unknown

**Observed:** after the optional peer barrier, `0x323064–0x3230fc` compares
the destination string at `0x41b721` against four static identifiers. It
invokes **at most one** synchronous stock call, not four stores per load:

| Identifier address | Call to `0x1c7af8` |
|---|---|
| `0x554678` or `0x554680` | `(0,1,1)` |
| `0x554688` | `(0,2,1)` |
| `0x554698` | `(0,3,1)` |
| No match | No stock call |

**Executed:** all four addressed identifiers and a synthetic nonstore name,
using the original comparison function and dispatch slice; generator calls
are captured stubs. **Observed:** nonzero mode enters stock generation at
`0x1c7ba8`, distinct from mode 0's UI path. No asynchronous stock-ready flag
is tested by the caller; returning from the applicable call precedes
`loadscreen_stop` at `0x323104`. **Inferred port contract:** a destination
that fails all four exact comparisons requires no transition stock job.
A matching destination requires successful equivalent stock generation;
no-op completion would be unsupported. **Unknown:** generator contents and
all item/RNG effects are not difftested here. This is a documented applicability
check, not proof that the native store implementation is complete.

**Observed:** save readiness is a separate **pre-load, network-only** gate at
`0x322ce8–0x322d1c`. It tests byte `0x4f8f2c`, invoking modal callback
`0x32393c` if busy. That callback services `0x222e10` and `0x2189e0`, then
returns whether the signed busy byte equals zero. Normal save sets busy=1
at `0x218d04` and clears it at `0x2190cc` or `0x2192a0`; initialization
clears it at `0x2170bc`. Configuration/end-game screen writers also occur
at `0x21f494/0x21f7bc`, with clears at `0x21f518/0x21f60c/0x21f6bc`
and `0x21f858/0x21f930`. These flags belong to card operations/screens,
not store stock. Offline bypass does not imply saving has occurred.
**Executed:** busy values 0, 1, 255 in the actual callback, plus all four
network-mode/busy caller combinations. Card services/modal scheduling are
stubbed; actual persistence and full save-state-machine execution remain
**Unknown**.

## Client handoff and limits

**Inferred:** an offline nonstore transition needs one supported deferred
pass and observable terrain/equipment warm-up work, but no peer wait or
store generation. This establishes applicability, not permission to hard-code
success for missing client services. The read-only integration branch's
`_loading_prerequisite_state()` must continue refusing any required operation
that its controller cannot perform or observe. Script content compatibility,
specialized equipment resources, save persistence, online behavior, and a real
playable handoff are not established by these synthetic slices.

Validation: `PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_loading_readiness.py
local/SLUS_209.73` reports deferred 13, equipment 12, peers 10, stores/save 12
cases (47 total). Existing loading difftest passes both seeds; the full analysis
unit suite passes 652 tests. Hardware writes in warm-up are mapped as inert
memory; display, I/O, script bodies and stock generation are outside the probe.

Round 2: [deferred error handling and equipment publication](loading-arrival-r2.md)
executes VM-error continuation, specialized slot routes and the I/O completion
writer. Destination-specific queued commands and end-to-end resource behavior
remain explicitly unknown.
