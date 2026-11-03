STATUS: COMPLETE (bounded synthetic lifecycle; campaign departure remains unknown)

# PushTrigger once lifecycle and saved-record participation

The bounded PE3-10 lifecycle and the PushTrigger portion of PE3-11 are **Executed**
in `tools/ee_emu.py` against the original executable, using synthetic records and
an independent reference. Ordinary dead-Creature departure remains **Unknown**.
This document does not close PE3-11 as a whole or claim a running-game result.

## Immediate destruction, not deferred deletion

**Observed / Executed:** `PushTrigger_interact` `0x1ecc70` invokes the virtual
destructor at `0x1ecd48` with argument `3` after its action calls when `once` is
nonzero. The real PushTrigger table `0x511450` resolves that call to
`PushTrigger_dtor` `0x3c3a00`, which reaches `GameObject_dtor` `0x14cf90`.
This is slot 1, at table offset `+8` with the function pointer at `+12`.
The earlier description of a virtual delete slot must not be interpreted as
`obj_delete` `0x14f200`.

**Executed:** once destruction removes the object from its grid/off-grid list,
run list, always-draw references, name lookup and allocator's live allocation
before interaction returns. The following explicit `world_flushDeleteList`
`0x14f3a8` has nothing further to do for that object. The tests compare the actual
original list nodes and all 28,800 grid heads against the existing object model;
there is no parallel boolean consumed/used list standing in for membership.
Once objects are exercised in grid A, grid B and off-grid, including a surviving
neighbour in the same cell.

**Executed control:** calling real `obj_delete` removes the run-list membership
and enqueues destruction, but leaves grid membership intact. That pending object
still appears in the original saved records. Only after real flush/destruction
does it disappear. Merely labelling an object deleted is therefore insufficient
to model the once behavior or its persistence boundary.

## Actions and context

**Executed:** original property accessors, `PushTrigger_interact`, and
`obj_runActionScripts` `0x14dcc8` run without replacement. Only the script entry
body at `0x1ed694` is a callback stub for this path. Fixtures contain zero, one or
two authored action identifiers, both `once` values and both `offOnly` values.
Properties use the serialized lowercase key `offonly`; real property lookup
lowercases the query key before comparing it.

The callback trace checks each action's identity and order, the selected object
at `0x4039f8`, and the inherited active-player slot at `0x4d8ae4`. Action callbacks
apply distinct, order-sensitive effects to a separate emulated accumulator; the
independent model computes the expected effect. Destruction must follow the last
callback. The stub returns zero, so the consumed once cases also establish that
these script returns do not veto destruction.

**Executed:** no action property means no action and no once destruction. A
reusable trigger remains usable on a second interaction. Selected context clears
after an action dispatch; active-player context survives. Interaction's passed
slot and the inherited active slot are varied independently. These tests begin
at `PushTrigger_interact`; they do not establish the upstream player-selection
producer. Script bodies do not mutate the context globals or object lifetimes.

## Original save and re-entry boundary

**Executed:** four synthetic first-load/save/unload/re-entry scenarios per seed
run these original functions:

- `world_loadRecords` `0x14e808`, with real factory `0x159c94` and constructor
  `0x1ec900` for the initial records and for the saved records.
- `world_saveState` `0x14e5c8`, `world_writeRecords` `0x14e140`, and
  `obj_writeRecord` `0x14df50`, using a bounded 64-KiB buffer.
- Real save filter `0x15d9c8`, destructor/flush functions, and
  `world_deleteAllObjects` `0x14c460` between visits.
- PushTrigger state slots `0x3c7ec0` (save) and `0x3c7eb8` (load).

**Executed:** first load uses the initial records with filtering disabled. A
saved visit loads saved records with filtering disabled, then the initial records
with filtering enabled. The actual save filter returns zero for `PushTrigger`,
so omitted once records do not come back from the initial source. A direct
positive control returns one for the short class identifier `Line`; no Line
constructor is substituted into the lifecycle fixtures.

Each scenario starts with six records: consumed once, reusable, untouched once,
once without an action, a deferred-deletion control and a transient-flag control.
The writer emits five records initially, four after the once interaction, four
while the deferred control is queued, and three after flush. Re-entry recreates
those three identities. The reusable survivor runs again, and the untouched
once survivor can then be consumed. Full class, position, facing and property
content is compared in addition to counts. The source blob's second load also
exercises its already-relocated representation.

**Executed control:** a nonzero query exclusion mask that would hide all of
these PushTriggers from world queries does not remove them from saved records.
The writer's traversal ignores that query mask. Every saved PushTrigger record
must end at the aligned end of its property terminator; the parser also rejects
an authored extra-state control rather than silently ignoring a state payload.

**Observed / Executed:** PushTrigger's state slots return zero: persistence is
record presence, not a separate used flag in a class-state payload. The writer
visits grid A, then grid B, then off-grid; the general world walker visits
off-grid first. The real PushTrigger factory passes facing zero even when the
source record has a nonzero facing. The reference includes both distinctions.

## Verification

Reverified 2026-11-02 on seeds 20973 and 7; all retained comparisons passed.

From this worktree, with the original read-only ELF at `local/SLUS_209.73`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import unittest,runpy; runpy.run_path("tools/difftest_exit_push_lifecycle.py", run_name="__main__")' --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import unittest,runpy; runpy.run_path("tools/difftest_exit_push_lifecycle.py", run_name="__main__")' --seed 7
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

The unittest preload prevents `tools/dis.py` from shadowing the standard library.
The probe checks the executable identity, bounds each original call, and emits
counts only. Seeded positions, facing values, action order and player context
vary while mandatory immediate/deferred and save/re-entry controls remain.

Both seeds passed with zero mismatches. Per seed: 12 action/lifecycle cases,
4 save/re-entry scenarios, 208 paired operations, 84 membership checks,
40 action/context/effect checks, 20 saved-record comparisons, 12 record loads,
and 17 required original function bodies entered. The repository suite passed
all 652 tests. A separate bounded reference check confirmed two refusals:
unsupported saved class and unsupported constructor property.

## Limits

**Unknown:** the complete ordinary departure chain through
`mainloop_loadRequestedWorld` `0x320edc`, `save_storeLevelState` `0x21777c`,
`save_writeLevelState` `0x218600` and `level_loadScriptAndObjects` `0x217978` was
not executed here. Act eligibility, directory capacity, memory-card states,
decals, explored-map serialization, save thinning/overflow and actual disc
content are outside this probe. In particular, dead-Creature ordinary departure
and re-entry remain **Unknown**; knowing a Creature state serializer is not
evidence that a corpse participates in every departure path. The new reference
refuses unsupported saved classes instead of treating them as empty-state
PushTriggers.

No shop, icon registration, physics-property, callback-driven object destruction,
network, native client, console or running-emulator claim is added. The fixtures
initialize a synthetic world with its `+0x70` field zero and offline network mode
for the real factory. Existing Rig support stubs remain in place; the original
functions listed above are observed at entry without replacing their bodies.
The original ELF file stays read-only; records and output remain in
emulated memory. Prior pinned references and difftests remain unchanged.

Owned additions: `tools/ref_exit_push_lifecycle.py`,
`tools/difftest_exit_push_lifecycle.py`, and this document.
