# Level-exit research, round three

2026-11-02. Research branch `t3/research-exits-r3`, recovered at `d9ef99a`
("Keep physical probe failures counts-only"). Bounded research is complete;
live client exit acceptance remains **Unknown**. This work does not remove
client refusals or claim successful physical campaign departure.

## Recovery and evidence

The starting tree had exactly seven untracked additions and no tracked diff.
`work/cursor-report.md` was absent, so there was no latest report to trust.
The recovered Creature and PushTrigger references, difftests and documents
were reviewed and rerun before being retained in separate commits. The seventh
file, this summary, was refreshed to distinguish retained prior claims from
current execution. No pending research file was discarded. Unverified old
parent/scout/client-status wording was removed from the Creature summary;
it was not evidence of a current native result.

**Observed** denotes addressed original-code evidence. **Executed** denotes
original functions run in `tools/ee_emu.py` against synthetic state and an
independent reference. **Inferred** denotes composition not executed as one
chain. **Unknown** remains unsupported. Nothing here ran as a Play! or native
campaign playthrough.

Private input is read via ignored `local/SLUS_209.73` with SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
Existing tracked references, APIs and vectors were not edited. Retained pinned
`ref_exits.py`, `difftest_exits.py`, `exits-walkin.md` match `95760d9` exactly;
`level-flow.md` matches `18e1a34`. All four comparisons were checked against git
objects before replaying the prior difftest. Their copies remain under ignored
`local/pinned-exits/`; no sibling working tree is needed for those reads.

## Documented contracts for the client owner

- **Walk-in — Observed / Executed:** original constructor `0x1ecdf4`, first
  linked-parameter query, RTTI and edge dispatch `0x1ecf3c`, shape `0x1ed238`,
  five-byte persistence and rearming. The serialized script property is `t`.
  Linked actions inherit the previous active-player context; Trigger binds its
  own active slot afterward. See `docs/exits-r3-handoff.md:12` and
  `tools/difftest_exit_walkin.py:34`.
- **Keyed/host prompt — Observed / Executed:** original first-active selector
  `0x13e5a0`, host-only branch and ordered key evaluation `0x1eca94`, including
  empty prompt versus usable return, are compared with new independent rules.
  See `docs/exits-r3-handoff.md:62` and `tools/difftest_exit_handoff.py:57`.
- **Level request — Observed / Executed:** original `newWorld` `0x143dd0`,
  `simpleNewWorld` `0x143e70`, network gate `0x143d04`, request helper `0x1472c4`,
  named entrance and post-action setters. Destination/orientation writes,
  cooldowns, rejection preservation and distinct retained buffers are compared.
  See `docs/exits-r3-handoff.md:100` and `tools/difftest_exit_handoff.py:132`.
- **Physical use — Observed / Executed:** unchanged original ordered query
  within complete `Player_interact` `0x1b2640` compares extents, exclusions,
  truncation before usability, movement-sensitive ties, prompt/edge gates,
  actual active-player store and slot-14 call. See
  `docs/exits-r3-physical.md:16`, `:37`, `:61`. Its success and failure output
  remains counts-only; no physical-probe detail is published.
- **One-shot PushTrigger — Observed / Executed:** original action dispatcher
  `0x14dcc8` and immediate destructor `0x3c3a00`, before interaction returns;
  real save/load/filter/factory calls preserve record absence on reentry.
  Reusable, unused and deferred-deletion controls distinguish the lifetime.
  See `docs/exits-r3-push-lifecycle.md:11`, `:58`.
- **Portal list/task handoff — Observed / Executed:** unchanged reset/discovery,
  484-byte save/restore, exact fixed pointer and four task-registration
  arguments, real scheduler operations and terminal dispatch. State-5 request
  copies the fixed/selected name and orientation 255; destination construction
  supplies eventual positions. See `docs/exits-r3-gate-lifecycle.md:15`, `:75`,
  `:106`; pinned arrival evidence `95760d9:docs/exits-walkin.md:153`.
- **Base Creature payload — Observed / Executed:** recovered unpatched,
  unstubbed original `0x116780` / `0x116920`, 36 paired saves/loads per seed,
  independently built payloads and full object-write comparisons. This does
  not establish derived corpse lifecycle. See `docs/exits-r3-creature-state.md:11`.

## Partial and unknown

**Partial:** script bodies are callbacks in Trigger/PushTrigger probes; argument
decoding is supplied in command probes. Host identity selection executes, but
transport and menu side effects are supplied services. Physical candidates have
synthetic extents/type data; gate reset has a supplied campaign hub; Portal
arrival has supplied terrain/object queries. These limits are local to the
individual documents, not implicit claims that missing inputs are irrelevant.

**Inferred:** these contracts support a client implementation carrying pending
destination, orientation, named entrance and post action, with exact trigger
context and persistence. They do not demonstrate an uninterrupted dispatch,
script VM, save, teardown, destination construction and placement chain.

**Unknown:** actual BLOOD1 predicate/item/quest effects, full script execution,
live vehicle state, all competing object constructors/grid order, menu states
0–4 and real confirmation, destination blocking geometry, and mixed living/dead
derived-object bytes inside the level writer. Round four executes the
level-to-level consumer around those gaps: act selection, the departure
directory, request splitting, orientation, and player-construction gates.
See `docs/exits-r4-travel.md`. `walk_in_exit_trigger` and
`blood1_keyed_exit_host_action` remain consumer acceptance requirements; no
current client state was verified here.

The consumer should implement the evidenced paths, retain refusal before
mutation for unsupplied inputs, and compare real action effects, departure,
reentry and arrival with original execution. No fixture, existing assertion or
refusal was weakened. Reproduction commands, all results and local commit hashes
are in `work/cursor-report.md`; new comparisons are detailed in
`docs/exits-r3-handoff.md:169`.
