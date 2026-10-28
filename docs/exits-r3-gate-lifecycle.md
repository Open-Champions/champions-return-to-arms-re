# Gate destination list and task lifecycle

2026-10-27, round three.

Status: **Executed**, bounded synthetic-state comparisons against the original
functions. Full campaign hub selection, complete menu input, and a live level
transition remain **Unknown** here. No running-game result is claimed.

This supplement addresses the gate-list portion requested under client PE3-4 and
the fixed-destination/task-argument assertion gaps requested under audit EXR2-2.
The finding texts themselves are not materialized here; this document does not
declare the broader client or audit finding closed. Prior evidence and tests in
`local/pinned-exits/` remain unchanged, including `level-flow.md` section 9.

## Destination state

**Observed in prior pinned evidence; Executed here:** the list is fifteen
32-byte slots at `0x8e3a50`, followed by the count byte at `0x8e3c30`.
`tools/ref_exit_gate_lifecycle.py` models the complete 480-byte storage as well as
the active count. Tests compare inactive slots and string tails, not just the
active logical names. String copies terminate the new value but do not clear the
remaining slot. Guards on both sides of the region are also compared.

- **Reset**, `0x27db00`: a nonzero byte at `0x4f8f28` preserves the list and does
  not call the hub selector. Otherwise the function sets count one and copies
  the caller-supplied hub identity into slot zero, retaining other storage.
  Four latch values and four prior counts are compared per seed.
- **Current-level discovery**, `0x27db60`: executes the real qualified-name
  function `0x1ec0f0`, including its formatter when a sub-name is present. The
  synthetic base and sub-name are placed at `0x41b721` and `0x41b771`.
  Matching is case-sensitive. An existing qualified name returns immediately;
  it neither appends nor performs stale-entry cleanup.
- **Stale-entry replacement**, `0x27dc30–0x27dc8c`: after appending, scan from
  the beginning for the first entry containing the discriminator referenced at
  `0x547f28` whose full name differs from the supplied current hub. Remove that
  entry by string-copying subsequent entries one slot left and decrement the
  count. Only one stale entry is removed. An appended stale entry can remove
  itself. The last vacated slot remains in storage.
- **Capacity boundary:** a fourteen-entry append and a fifteen-entry duplicate
  are executed. A new sixteenth append is intentionally excluded. The prior
  section 9 observation reports no bound check; the reference model's refusal
  at capacity is its own safety boundary, not behavior attributed to the game.

**Stub boundary:** `0x1ec300` returns an allocated synthetic hub identity.
Neither its campaign decision logic nor the caller's act-change decision is
executed. These comparisons establish reset to `[supplied hub]`, not a full
campaign hub. Test identities are generated symbols; the discriminator is read
privately at runtime to exercise the original substring comparison. No shipped
destination list, names, or discriminator text are embedded or printed. No
executable instruction or read-only datum is patched in the final harness.

## Save and restore

**Executed:** `0x27dcf4` writes a 484-byte block: a little-endian count word,
then all 480 bytes of list storage. It sign-extends the count byte into the word.
`0x27dd30` restores the low byte of the input count word and copies all 480 bytes,
including inactive slots and tails. Both return 484. Their real copy routine
`0x3b5f0c` executes.

Eight save/restore cases per seed include count bytes 128 and 255 solely to
distinguish sign extension. Four additional restore words distinguish low-byte
truncation from validation. These malformed-state probes do not establish that
such counts are safe for subsequent discovery or menu execution.

Twenty-four connected histories per seed perform two discoveries with a
duplicate between them, save, reset, and restore. Every stage is compared with
the independently updated model, including the exact saved block.

**Observed only, retained from pinned section 9:** the enclosing save places
this block at save-buffer offset `+0x134`. The complete save builder/loader,
memory card I/O, checksums, and load-time caller sequencing are not executed.

## Opener, pointer handoff, and tasks

**Executed:** `JumpGate_openMenu` at `0x27da24` takes chooser in its first
argument and fixed-destination pointer in its second. It writes the chooser
byte at `0x8e3a3b`, stores that exact pointer at `0x8e3c34`, and clears state
`0x8e3a3a` and travel word `0x500ae8`.

The ordered four-argument registrations at `0x27da68` and `0x27da84` are
compared exactly:

1. `(0x27dd74, 20, 0x547e10, 0)` — synthetic identity `GATE_RUN`.
2. `(0x27e2d0, 20, 0x547ef8, 1)` — synthetic identity `GATE_DRAW`.

The expected name pointers are fixed in the independent model, not learned
from intercepted calls. The observer hooks allow real `task_add` `0x19e4a0`
to run. Tests compare every active task record, count `0x44fdb8`, and signed
cursor `0x44fdbc` in the real table `0x840100`.

Four chooser slots and three destination pointers exercise direct opening.
Reopening changes the destination, then clears it to null; both registration
calls still occur, but the real scheduler retains just one record per function.
Unrelated tasks before, at, and after priority 20 remain present in their
expected order. The prior four mutex/network combinations are extended across
four slots: accepted interaction `0x27d754` supplies null fixed destination;
refusal preserves chooser, destination, state, counter, and task table.

**EXR2-2 assertion correction:** the pinned prior test captured only the first
two registration arguments and checked existence/count. It did not compare
their values or assert `0x8e3c34`. The new assertions cover all four arguments
in order, full initialization/refusal fields, and actual scheduler membership.
This corrects the coverage gap without changing the prior reference API or
test vectors.

**Executed pointer handoff:** nine cases per seed connect the opener to real
state-5 execution at `0x27dd74`, entering with travel 181. Fixed destination
wins; null selects `0x8e3a50 + 32*index`, with indices 0, 2, and 14 tested.
The exact copy arguments, copied synthetic contents at `0x41b6d0`, orientation
255 at `0x41b720`, unchanged counter, and next state 6 are compared. The real
string-copy implementation executes. Earlier countdown vectors remain in the
pinned test and are not replaced.

## Removal and terminal dispatch

**Executed:** `0x27dac8` removes both gate functions only when travel is zero.
Nonzero travel preserves the table; repeated idle removal is harmless to
unrelated membership. The function's removal arguments and unchanged gate
initialization fields are compared as well as table/count/cursor.

**Executed:** real `tasks_call` `0x19e798` dispatches a synthetic draw pass and
two terminal simulation passes. Entry state 6 changes to 7 and retains travel;
entry state 7 clears travel and removes both gate tasks using real
`task_remove` `0x19e664`. Live cursor adjustment permits unrelated tasks to run
exactly as the independent model predicts after self-removal. Later run/draw
passes no longer dispatch the gate tasks. Twenty-four histories per seed use
several initial travel values and unrelated task flags.

External effects are bounded explicitly: opener callees `0x1eb000`,
`0x17365c`, `0x214230`, and the interaction mutex `0x22fc2c` are stubbed.
The draw callback body and synthetic unrelated callbacks are stubbed during
scheduler dispatch. The gate run callback, scheduler insertion/removal, and
dispatch are original code. No gate-list operation, qualifier, string
comparison/copy, save/restore operation, or scheduler operation is stubbed.

**Unknown:** complete states 0–4, pad/menu selection, rendering, effects,
network behavior beyond the bounded mutex predicate, actual destination-level
construction, and the main-loop order that determines whether a loaded level
first sees state 6 or 7. Two terminal dispatches on supplied state do not prove
a first/second-tick timing claim across an actual world load. Other terminal
global writes are outside these assertions.

## Reproduction and counts

From this worktree, using the read-only original at `local/SLUS_209.73`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_gate_lifecycle local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_gate_lifecycle local/SLUS_209.73 --seed 7
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

The harness verifies executable identity before execution, uses a 100,000-step
limit per entry call, and emits counts only. `-m` and the preloaded `unittest`
avoid the repository's `tools/dis.py` shadowing the standard library.

- Seed 20973: **780 entry calls, 2,246 assertions passed**.
- Seed 7: **780 entry calls, 2,245 assertions passed**.
- Repository unittest discovery: **652 tests passed**; retained counts/evidence
  log at `local/gate-lifecycle-r3/unittest.log`.
- Each seed: 143 discovery cases, 16 reset cases, 8 fixed-block round trips,
  4 count-width probes, 24 list histories, 69 opener checks, 16 interaction
  checks, 9 pointer handoffs, 60 idle-cleanup checks, and 120 dispatch checks.

Assertions and entry calls are distinct counts; nested original callees are
not included in the entry-call total. The one-assertion seed difference comes
from the randomized duplicate cases' additional no-hub-call check.

The original executable, prior pinned artifacts, and existing APIs/vectors
are unchanged. The round-three handoff is `docs/exits-r3.md`; local execution
and commit details are recorded in `work/cursor-report.md`.
