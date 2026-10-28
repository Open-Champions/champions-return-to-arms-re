# Physical exit use: ordered live query through dispatch

2026-10-27. Round-three research starts at `77c2f70`. Prior exit research
`95760d9`, level-flow research `18e1a34`, and the exit/client audits are the
comparison baseline. This document supersedes no existing reference API or
test vector. `tools/ref_exit_physical.py` and
`tools/difftest_exit_physical.py` are additive.

**Executed** means original functions ran in `tools/ee_emu.py`, against
synthetic state and an independent reference model. It does not mean a
running game or the playable client was tested. The executable is read-only,
SHA-256 `292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.

## Established boundary

**Observed, Executed** `Player_interact` **0x1b2640–0x1b2cb8** now runs
from entry to return with the **original** `world_collectObjectsInBox`
**0x14a928**, not a supplied result list. Original pool/handle/world setup,
`GameObject_ctor` **0x14cb10**, grid updates **0x14f028**, and off-grid
movement **0x14ef48** establish the synthetic objects' actual grid links.
The reference uses the existing, unchanged `ref_objects.World` and EE
binary32 arithmetic. Observation hooks record query inputs and outputs;
none changes the program counter, registers, or instructions.

**Observed, Executed** eligibility at **0x1b2674–0x1b26b4**:

- A nonzero ridden-vehicle pointer at input player **+0x540** returns
  before querying or prompting.
- The slot at input player **+0x3c8** selects the record at
  **0x4d8af0 + 0x4c30 × slot**. Health **+0xac** must be positive and
  object **+0x43d8** nonzero. Zero/negative health and missing record
  objects perform no query, prompt, active-player store, or use callback.
- Query position comes from that **record object's +0x10/+0x14/+0x18**,
  not necessarily the input object's position. The tests deliberately
  give them different positions and exercise all four slots.

**Observed, Executed** query/selection at **0x1b26b8–0x1b27e4**:

- Bounds are horizontal ±48, vertical z through z+60; limit is **256**,
  hence at most **255** objects plus terminator. The actual ordered list
  and the returned terminator pointer are compared on every eligible call.
- Actual extents participate: radius-24 centres at horizontal 72 touch
  the box and qualify; 72.25 does not. Height-72 bases at z=-72 qualify;
  -72.25 does not. z=60 qualifies; 60.25 does not.
- Grid B, off-grid, prediction-flag **0x20000**, and objects matching
  **0x4039b8**'s exclusion mask do not compete. The fixed 96-unit cell
  margin can miss a very large-radius object even when its extent overlaps.
- Within one cell, the most recently linked/moved object comes first.
  Across cells, ascending row then column wins. Identical-distance cases
  prove both forms of ordering; movement in the same cell changes a tie.
- Selection examines only flag **0x100000**, without an exit-class
  whitelist. It minimizes `(dx² + dy²) + dz²` using EE arithmetic,
  with strict comparison and initial bound 10,000,000. A synthetic tall
  object at exactly that squared distance is returned by the query but
  not selected; just-below/just-above controls distinguish the boundary.
- **Truncation comes first.** In a 261-object synthetic crowd, 255
  nonusable objects can fill the result and exclude the nearest usable
  object. Relinking that usable object to the front makes it selectable.
  Filtering to usable objects before applying the query cap is incorrect.

**Observed, Executed** prompt and use at **0x1b2800–0x1b2b88**:

- Only the selected object's virtual slot 13 is called, with the player
  slot. Prompt result and first UTF-16 character are independent inputs.
  An empty prompt blocks dispatch, even if the result is usable.
  An unusable nearest prompt does not fall through to a farther candidate.
- A one-space prompt takes the original presentation shortcut at
  **0x1b2834–0x1b283c**; a normal synthetic character exercises the other
  presentation path. No branch is bypassed by a harness hook.
- Simulation result 1 uses the per-slot mask at **0x41b9c0**; result 2
  uses bit **0x10**. Both read pressed edges at pad **+0xc**. Held-only,
  wrong-mask, zero-mask, result 0/3, and display-only controls do not use.
- The actual store at **0x1b2b70** sets **0x4d8ae4** before the actual
  virtual slot-14 call at **0x1b2b84**. Its callback asserts selected
  object, slot argument, active-player value, and a distinct effect
  increment. Refused calls leave the sentinel active-player value intact.
- Prompt evaluation occurs without a use edge and in display-only mode;
  dispatch remains gated. This establishes the call boundary needed by
  proximity discovery, not the gate's discovery side effects themselves.

## Supplied services and remaining unknowns

**Partial**: candidates are original base objects with synthetic extents,
flags and virtual tables. Their slot-13 and slot-14 callbacks are supplied;
the callback effect is not an executed level script. Presentation RTTI
comparisons are supplied as nonmatches; glyph lookup, text width and final
draw are stubbed. Original UTF-16 copy/concatenation and the complete
`Player_interact` body execute. Real derived-class construction, item/NPC
presentation categories, controller delivery and the surrounding
`Player_run`/`Player_draw` schedule are outside these tests.

**Unknown**: the client still needs authoritative vehicle state and a
complete live query world: every competing object's constructor-derived
extents/flags, grid membership, movement order and exclusions. Static exit
records cannot provide those guarantees. This research addresses the
algorithm behind **PE3-1/2/9**, and closes **EXR2-1**'s missing dispatch
assertions; it does not authorize removing a refusal while required live
inputs are absent. Full physical departure remains unverified.

**Audit clarification**: prior `95760d9` wording about `Trigger_run`
**0x1ecf3c** is too broad: recall suppression happens after **+0x68** is
reset to -1, before writing the found slot or changing the inside byte
(**EXW-1**). Its old reference/vector already encodes this correctly.
The round-two use test stopped at **0x1b2b6c**, before the store/call;
the additive test here asserts those effects (**EXR2-1**).

## Reproduction

From the research worktree, with the private executable under `local/`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_physical --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_physical --seed 7
```

Both seeds **PASS**: **348 cases per FPU model**, four models
(`ps2`, `ps2g1`, `chop`, `nearest`), **2,784 total comparisons**.
The totals include 261-object crowd scenarios. There are zero control-flow
bypasses. Output contains counts only; no private level data is committed.
