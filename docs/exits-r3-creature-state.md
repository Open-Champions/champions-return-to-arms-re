# Base Creature payload on ordinary departure

**STATUS: COMPLETE for the bounded synthetic base-state comparison; full corpse
lifecycle and campaign departure/reentry remain unknown.** Reverified 2026-11-02
on branch `t3/research-exits-r3`.

The additive reference is `tools/ref_exit_creature_state.py`; the executable
comparison is `tools/difftest_exit_creature_state.py`. Existing reference APIs,
vectors, native code, and executable inputs are unchanged.

## Scope and evidence

**Observed:** base virtual slot 9 is `Creature_saveState` at `0x116780`; slot 8
is `Creature_loadState` at `0x116920`. The original base vtable is `0x50cc58`.
The implementation was inspected from the hash-pinned private executable;
private inspection material stays under `local/creature-state-r3/`.

**Executed:** both exact entry points and every reached callee run in
`tools/ee_emu.py` with no stubs, hooks, instruction patches, automatic memory
mapping, or replacement vtables. Each entry has a 100,000-instruction limit.
The executable identity is checked before execution:

`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`

The retained 36-pair matrix was rerun on seeds 20973 and 7 on 2026-11-02.
These are individual functions on constructed state, not a running game,
a level transition, or a derived class.

**Observed in pinned prior research, not executed as a chain here:** ordinary
departure follows `0x320edc` -> `0x21777c` -> `0x218600` ->
`0x14e5c8` / `0x14e140` -> slot 9. Reentry uses `0x14e808` -> slot 8.
See `18e1a34:docs/level-flow.md:383` and `:415` (retained unchanged in
`local/pinned-exits/level-flow.md`). This test executes only the base slot
bodies. Native corpse support and its current refusal sites were not inspected
in this recovery; no native acceptance or refusal removal is claimed.

## Independently expected payload

**Observed and Executed:** the payload is little endian. Save writes the model
variant from `+0xe8`, then the float32 ratio `HP / maximum HP` from
`+0x228 / +0x22c`. Source HP at or below zero adds an animation-name offset,
followed by packed flags. Nonzero signed charm at `+0x312` adds a sign-extended
32-bit word. Thus length is `12 + 4 * dead + 4 * charm_present`: live 12/16,
dead 16/20 bytes (`0x1167a0–0x116904`).

| Packed bit | Source field |
|---|---|
| 0 | Creature flag bit 24 (`0x1000000`) |
| 1 | Creature flag bit 32 (`0x100000000`) |
| 2 | Creature flag bit 22 (`0x400000`) |
| 3 | Creature flag bit 23 (`0x800000`) |
| 4 | Creature flag bit 49 (`0x2000000000000`) |
| 5 | Inert byte `+0x231`, bit 0 |
| 6 | Charm word present; source signed halfword is nonzero |

The dead animation is the source top track's clip, found by pointer equality
among the class definition's resources. Its resource name is interned by
original `saveStr_intern` `0x14de60`; no match serializes offset `-1`.
The test uses invented ASCII names only. An independently built string table
predicts length-byte/name/NUL entries, nonzero offsets, and deduplication of
preexisting names. It never learns its expected offset from the executed save.

Each pair compares save size, every payload word and write, table contents and
cursor, source/destination preservation, and guards/tails. Load receives the
reference's payload and table, not bytes copied from the executed save.
This prevents a matching encoder/decoder error from passing as a round trip.
The reference uses existing `ref_core` float32 arithmetic independently of EE;
this is not a new hardware floating-point validation.

## Independently expected restore writes

**Observed and Executed:** load restores the variant and computes HP as
`destination maximum HP * saved ratio`; it need not equal source HP bit for
bit. Destination maxima vary across 50, 100, and 200. Slot 29 executes original
`Creature_refreshVariant` `0x11a668`, the original model accessor, and
`model_getVariant` `0x179550`. The empty model gives an all-set 64-bit variant
handle at `+0x220`.

For reconstructed HP at or below zero (`0x116984`), load writes state `0x14`
at `+0x232`, ORs object flags with `0x2009`, and calls original stop-running
helper `0x14f290`. The fixture starts with zero object flags and no run-list
link, so the observed final object flags are exactly `0x2009`; unlinking a
populated run list is outside this test.

A matching animation name additionally executes original animation reset
`0x1707b0`, push `0x170838`, jump-to-end `0x170bc8`, and base death hook
`0x10beb8` with its restore argument. The one track has flag 4, weight and life
1, rates and sound cursor 0, and time equal to the synthetic clip length.
Animation-state flags retain their previous bits and gain `0x84`.
This is jump-to-end, not evidence that all corpse motion/decode state is
restored. The death hook clears cflag bits 27, 22, and 23 before saved flags
are reapplied. Missing or unmatched references still restore dead state and
object flags but skip animation initialization and the death hook.

Saved cflags are ORed into the destination (`0x116aac`); absent saved bits do
not clear them. Inert bit 0 is replaced, preserving the other inert bits.
The comparison uses randomized preexisting destination cflags, an inert byte
with other bits set, nonzero state/variant/HP sentinels, and numeric canaries.
It compares the complete 0x3c8-byte object image and the exact ordered
object-relative writes, including redundant stores.

**Observed boundary:** optional charm is consumed even when application is
skipped (`0x116b54–0x116bac`). Existing timer `-1`, missing object flag `0x20`,
or player flag `0x40` prevents application. The tested fresh destinations have
zero object flags and timer 0; all retain timer 0 despite source charm 60/-1.
Zero player count is part of the fixture, not an explanation of that guard.
**Unknown:** actual charm restoration in constructed gameplay creatures or
players. The reference refuses those destination states rather than claiming
this fixture establishes their behavior.

All reached refresh, string-table, animation, property lookup, base death-hook,
and type-information routines execute originally. Empty properties, absent
external death-event object, null class-name field, empty caches, no handles,
and no players keep their dependent paths bounded. Lazy original type-information
cache writes are permitted only at eight listed field addresses in the harness;
their values are outside the independent oracle. No other external write is
accepted. This is an object-write oracle, not a complete global-state oracle.

## Matrix, refusal limits, and reproduction

Per seed:

- 18 core pairs: HP 50/0/-1 × charm 0/60/-1 × saved flags off/all
  (six live, twelve dead).
- 14 mapping/preservation pairs: each of five saved cflags, inert bit 0, and
  excluded cflag bit 31, each with live/dead HP.
- Four dead negative controls: missing source clip reference or unmatched
  destination animation, each with HP 0/-1.
- Total: **36 pairs, 72 entry calls, 1,404 assertions**, **13 live / 23 dead**;
  19 animated dead restores and four dead restores without animation.
- **20 reference refusals** covering invalid maximum HP/ratio domains, charm
  width, oversized names, non-base vtable, unsupported destination flags/charm,
  nonempty pose, unsupported capacity, truncated/extra payload, and unknown
  packed flags. These are reference boundary checks, not claims that the original
  safely rejects malformed data. Zero, negative, nonfinite or subnormal maximum
  HP and branch-changing ratio underflow are deliberately unsupported.

Seeds randomize variants, destination cflags and maxima, synthetic clip lengths,
numeric canaries, buffer guards and tails. Every pair uses a fresh EE instance
and separately allocated source/destination. The fixed branch matrix is the
same for both seeds.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_creature_state local/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_creature_state local/SLUS_209.73 --seed 7
TMPDIR="$PWD/local/tmp" PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

Both seeds passed the counts above with **zero stubs, patches, automatic mapped
pages, or failures**. Repository unittest discovery passed **652 tests**;
its local log is `local/creature-state-r3/unittest.log`.
The `-m` invocation and preloaded `unittest` avoid the
repository's `tools/dis.py` shadowing the standard library. Output is counts
only, and a missing/wrong executable or a failed comparison exits nonzero.

**Unknown / excluded:** derived vtables and death hooks, full corpse lifecycle,
root motion, model/pose/decoder resources, effects/scripts/loot, populated
run/grid/handle lists, real class construction, actual gameplay charm restore,
malformed original payload safety, world-record packing/thinning, the complete
departure/reentry chain, and campaign acceptance. Settling those requires their
own bounded original-function fixtures and eventually the relevant runtime
integration; this additive result makes no such claim.
