# Arrival research round 3: resource transformations and remaining route evidence

2026-10-27, extending audited research `d6f035fab6bb5cbe66f5c72a55a1a6aef05ee8df`.
**STATUS: PARTIAL.** Resource transformations are now executed without fixup
stubs. The normal single-player deferred-command census and association of these
resources with the player's actual starting inventory remain **Unknown**.
No playable arrival or normal-route trace is claimed.

## Resource transformations

**Observed, Executed:** `0x179e10` is a leaf transformation of the first resource
in the cache pair. It returns unchanged when resource word `+0x1c` is nonzero
(`0x179e14–0x179e18`). Otherwise it adds the resource base to word `+0x10`,
writes short `+0xa = 0xa7fb`, and word `+0x1c = -1`
(`0x179e20–0x179e40`). These are pointer relocation and header bookkeeping,
not decompression or asynchronous transfer.

**Observed, Executed:** flags at unsigned short `+8` control further work.
Bit zero set, or bit `0x100` clear, ends transformation after that header update.
Otherwise the table reached through the original relative `+0x10` receives:

- Its first word is relocated by the same base (`0x179e54–0x179e5c`).
- Four signed bytes describe inclusive column/row endpoints. A first byte of
  minus one terminates the table (`0x179e64–0x179e68`, `0x179f0c–0x179f14`).
- For each rectangle, one following word per inclusive row/column combination
  receives the base (`0x179ed0–0x179f08`). The next rectangle follows these words.
- The accumulator starts at `0x48`; each rectangle adds six plus the signed
  product `(rows * 0x800 * columns) / 128`, truncated toward zero. Its low
  halfword is written at `+6` (`0x179e90–0x179ec8`, `0x179f18`).

**Observed, Executed:** `0x179130` is a separate leaf transformation on the second
resource, using that resource's own base. Signed count byte `+0x26` is replaced
with one if nonpositive (`0x179130–0x17914c`). Let that resulting count be `n`,
and `w = signed_byte[+0x12] + 1`. It adds the resource base to each of
`max(0, n*w)` consecutive words at `+0x28` (`0x179154–0x179190`).
It does not set or test the first resource's relocation guard. Calling it twice
adds the base twice; it must not be applied repeatedly during readiness rescans.
The multiplications at `0x17915c/0x179184` are executed R5900 integer operations;
an unrecognized mnemonic in a third-party text disassembly is not a missing
emulator operation.

**Executed:** `tools/difftest_loading_arrival_r3.py` compares all resource bytes
against independently authored byte models. Its 45 synthetic cases cover all
four flag combinations, zero/nonzero guard, two rectangle sizes, signed count
boundaries including minus 128/zero/127, and three width fields. Second-call
controls distinguish guarded texture relocation from repeated model relocation.
These controls do not establish arbitrary malformed-input safety.

**Executed:** two additional fixtures run original cache lookup `0x1a2d48` with
both fixups executing, in order, rather than captured stubs. Request frame 100
and current frame 104 exercise the request-relative service interval. Whole
paired-resource bytes match the composed models; identity/valid/outstanding
publication follows, both output cells remain zero on completion, and the next
matching lookup returns the pair without transforming it again. Earlier media
submission and I/O are not executed in these two already-completed fixtures.

**Executed, private standalone-lump sample:** the optional folder argument reads
private inputs without modifying them, selects resource roles by extension at
runtime, and emits counts only. All **2,624 texture entries and 1,958 model entries**
match original execution byte-for-byte. Counts are entries, not distinct resources
or starting-equipment items. This sample excludes resources embedded only in
outer archives and specialized sector ranges that are not standalone lump entries.
No payload identities, bytes or script text are retained in tracked artifacts.

**Unknown:** which specialized resource pair and header record belongs to each
actual starting item on this route. Generic resource transformation evidence
does not prove initial-item generation, equipment-slot selection, metadata lookup,
device transfer, renderer use, or playable model readiness. The client must still
establish those inputs rather than select an arbitrary passing sample resource.

## Deferred command census: still unknown

**Executed, bounded initial-entry probes only:** private local probing found one
script image for each of the three requested destinations, ran the original loader
and native registration, then called original wrapper `0x1ed694` using the two
initial identifier addresses from caller sites `0x217acc/0x217bac`:

| Route ordinal | Initial identifier at `0x53f000` | Identifier at `0x53f020` |
|---|---|---|
| 0, hub | Returns minus one (missing entry) | Executes native `0x1473b4`, then stops before `0x1420d0` |
| 1, first mission | Stops before native `0x14222c` | Not reached |
| 2, following destination | Returns minus one (missing entry) | Stops before native `0x142084` |

The stops are intentional hooks before supplying unestablished world/mission/media
state; they are **not original faults, successful initial entries, or a normal
arrival trace**. Native `0x1473b4` executes its actual unconditional save-inhibit
store. `0x1420d0` modifies mission state, `0x142084` queries it using difficulty
word `0x4f719c`, and `0x14222c` reaches blocking resource loader `0x173558`.
Existing handler evidence is in `docs/script.md`. No return value was fabricated
for these stopped natives. No queue census follows from this prefix experiment.
Private probe helper and inputs remain ignored under `local/`.

**Unknown:** the front/back queues after the complete normal loader/object/start
path, their ordered entry addresses, the commands those entries actually execute,
and their native-call counts. This worktree has an executable and read-only disc,
but no captured normal-arrival EE memory fixture carrying player/quest/object/cache
state through all three transitions. Initializing those services with zeroes or
using arbitrary native results would select an unproven path. The function-level
EE tool is not a console emulator and provides no automatic disc/world bootstrap.

To settle this item, execute/capture the actual loader and initial entries with
established route state and media/object services, preserving mission/player
changes between destinations. Observe enqueue `0x1ed52c`, ordered dispatch
`0x1ed694`, and native dispatcher `0x141050` through returned loading pass
`0x1eda24` at caller `0x322e6c`. Export ordinal/count/address evidence only.
No zero-command census or unsupported-command success is inferred here.

## Verification

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_loading_arrival_r3.py local/SLUS_209.73 local/disc`
passes 45 transformation cases, two integrated cache cases, and 4,582 private
entry comparisons. The executable digest is checked before execution; original
instructions, existing reference APIs and vectors are unchanged. The local disc
link is ignored and the source input remains read-only.

Round-2 probes: 81 cases PASS. Round-1 readiness: 47 cases PASS. Existing loading
difftest: seeds 20973 and 7 PASS. Analysis suite: 652 tests PASS (5.446 seconds).
No client builds, rendering, device I/O or actual playable acceptance were run.
