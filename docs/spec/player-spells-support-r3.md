# IDs 49 and 55: bounded round-3 evidence

STATUS: COMPLETE — bounded research only. The living-player count now matches.

Executed on 2026-10-27 in branch `t3/research-spells-r3`, based on `77c2f70`.
The owned additions are this document and
[`tools/difftest_spell_support_r3.py`](../../tools/difftest_spell_support_r3.py).
`SpellHealing_run` now re-reads the living-player count. No other reference API
or existing vector changed.

The prior `cursor-runs/audits/research-spells-r2.md` reports PASS for its earlier
scope. It was read as retained evidence, not counted as a fresh execution. The
relevant inherited contracts are [the family specification](skills-35-68.md),
[its execution record](skills-35-68-executed.md), and [the shared routing
description](../skills.md). These IDs were selected for melee/support roles;
no usage telemetry or ranking of frequency is available.

## Execution and counting

From the worktree root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import unittest, runpy, sys; sys.path.append("tools"); sys.argv = ["tools/difftest_spell_support_r3.py"]; runpy.run_path(sys.argv[0], run_name="__main__")'
```

**Executed:** exit 0, `PASS`; 5,173 assertions, zero unexpected failures, zero
unknown call targets. There are **561 matching function comparisons** and **37
animation comparisons**. The former adversarial call is one of the 561. These
are 598 top-level original calls being checked, not a count of gameplay actions
or independently exercised branches. Startup and nested calls are not separately
counted. Constructors run inside the cast comparisons.

Round 4's receipt `local/spells-r3/support-parent-counts.json` is the file that
records `PASS_WITH_MODEL_DISCREPANCY`, 5,178 assertions and 560 matching
comparisons. The older `support-counts.json` from that round did not. This
round rewrites `local/spells-r3/support-counts.json` with the matching result.
That receipt contains only counts, addresses, fixed test labels and status. The
script validates the private input
against the existing expected digest before execution and exits 2 if it is absent
or different. It reads `local/SLUS_209.73` without modifying its symlink or target.
It confines generated output to `local/spells-r3/` and emits no extracted values,
tables, instruction listings, game text or bytes.

| Matching entry address | Comparisons | Purpose |
|---|---:|---|
| `0x2de334` | 7 | 49 equipment gate |
| `0x2de3bc` | 35 | 49 cast and nested constructor |
| `0x2de60c` | 20 | 49 cost, ranks 1–20 |
| `0x2de7dc` | 56 | 49 effect, timing and end conditions |
| `0x2e8cf8` | 45 | 55 cast and nested constructor |
| `0x2e8e94` | 20 | 55 cost, ranks 1–20 |
| `0x2e90b8` | 346 | 55 matching effect and timing cases, including the re-read count |
| `0x3c8218` | 3 | 55 base gate |
| `0x3c85fc` | 29 | Supporting statistic queries |

`0x16d748` adds 37 animation comparisons against `ref_anim.anim_advance`.
The count-reload case at `0x2e90b8` is included in the 561.
The exact group counts are retained in the counts artifact; comparisons include
setup casts and supporting getters, not just the final boundary calls.

`difftest_skills_b.Rig.compare` executes the original functions in `ee_emu`
against the existing `ref_skills_b.Model` on a copy-on-write view. It compares
external calls in order with arguments, non-stack written-byte sets and final
values, the shared seed and draw count, and applicable return values. Floats are
compared by bits using `ps2` arithmetic on both sides. This does not compare
complete store order. The new wrapper rejects both-side faults as failures too;
they cannot count as successful matches. The animation comparison checks event
bits, track time and status, not the entire animation state or pose.

## Cost: all ranks 1–20

**Executed:** 40 cost/rank pairs agree with the existing independent reference
and a separate integer-expression oracle converted using Python's float32 pack:

- 49, `0x2de60c`: `float32(16 + 3 * (rank - 1))`.
- 55, `0x2e8e94`: `float32(55 + 6 * (rank - 1))`.

These formulas describe the tested ranks only. Every resulting integer is exactly
representable, so the assertion is exact bit equality, not a tolerance or host
approximation of the underlying statistic arithmetic. The original startup
functions at `0x16ac74` and `0x1ebca0` construct the objects and statistics in
memory. No source table is reproduced in either new file. The cost getters reach
`0x3c88e4` and `0x3c85fc` in the existing harness. The cast helper's debit and
recast, including a below-cost debit, are executed separately in the
[numeric contract](player-spells-numeric-r3.md), with the cast slot returning 0.

## 49: gate, targeting, effect and timing

**Executed gate (`0x2de334`):** a player requires a nonzero equipment pointer at
record `+0x43fc` and a class byte at `+0x4a86` different from 4. Absent equipment,
class 4, adjacent classes 3/5, signed byte 255, and a non-player are separate
controls. The rejected player cases issue one recorded notice. Allocation
failure at `0x2de3bc` returns zero with no constructor draw, but the sound call
has already occurred. These are isolated skill gates, not all player gates.

**Executed constructor (`0x2de640`, selection store `0x2de7b4`):** empty lists,
eligible head, all excluded entries, excluded head followed by an eligible entry,
and eligible head followed by an excluded entry are explicitly staged. The
excluded-head/eligible-second case retains the **head**, not the eligible second
entry, at spell `+0x24`. The action state becomes 6. The recorded selection query
requests radius 100 and arc 90. Query results and their ordering are supplied by
the test; spatial collection itself is not executed.

**Executed strike (`0x2de7dc`; statistic/filter region `0x2de8e0–0x2decb8`):**
every rank 1–20 gets more candidate recipients than its cap, with an excluded
flag entry and a slot-20 rejection ahead of the accepted entries. Accepted hits
consume the cap in supplied list order. The independently asserted cap is
`1 + (rank + 1) // 4`; the centre is `50 + 10 * (rank - 1)` and the passed bounds
are exact float representations of 80% and 120% of that centre. The tested flags
are `0x40040` at ranks 1–5, `0x80040` at 6–15 and `0x200040` at 16–20, including
both sides of each transition. Each creature hit passes no-critical flag 1.
The damage callback records these arguments. The handed amount, creature HP
subtraction and stun-timer store are **Executed** in the
[numeric contract](player-spells-numeric-r3.md), with the player slot, the
player death test and the knock-back speeds.

**Executed stun boundary (`0x2deb4c–0x2deba0`):** at rank 5, deterministic shared
seeds produce a roll exactly equal to chance and one above it. Equality stuns;
the next roll does not. The recorded duration is statistic 2 multiplied by 60.
Scripted post-damage health at positive, zero and negative values proves that
only positive health consumes the stun draw. Separate two-hit cases prove one
light allocation attempt, on the first hit only: allocation success adds one
shared draw; failure adds none.

**Executed fallback and latch (`0x2de7dc`, done path `0x2ded38`):** wholly rejected
creature candidates trigger the supplied sphere list. Excluded entries followed
by two eligible props damage only the first eligible prop, with no-critical flag
0. A fully excluded sphere list damages nothing. Both paths mark the strike
done; a second call cannot retry. Repeating event bit 2 after a successful strike
also cannot deliver another hit.

**Executed timing (`0x16d748` and `0x2de7dc`):** the cast writes event mask 2 and
its event time into a synthetic resource header. A 120-tick synthetic clip with
one non-root track, speed 1, no sound and no yaw produces bit 2 on advance 36,
with no event on 35 or 37. Original/model animation comparisons cover all 37
advances. Those event results feed the recorded `Player_animStep` callback for
effect calls 35–37: no damage, one strike, no repeat. This composition does not
execute the actual player animation wrapper or original cast animation setup.
Status bit `0x10` present with no repeat latch keeps the effect active; clearing
that bit or setting owner `+0x450` records destruction and writes state 2.
Real clip length, recovery, root motion and slow-state timing remain **Unknown**.

## 55: targeting, effect and timing

**Executed gate/cast (`0x3c8218`, `0x2e8cf8`):** the base gate returns 1 for player,
non-player and null inputs. This does not make null input valid for construction.
Allocation failure returns zero before sound or constructor draw.

**Executed recipient range (`0x2e9108–0x2e93bc`):** all ranks 1–20 obtain radius
from the original/reference statistic getter. For each rank, six positive-float
controls put a recipient one float32 value below, exactly at and one above the
radius, separately on the horizontal and vertical axes. Both axes include
equality and exclude the next representable value. These are **120 explicit
range calls**, plus their setup casts/getters. Only supplied living-player slots
are processed; an empty list excludes even the owner. With mode A off, slot 22
is not consulted. With mode A on, scripted reject/accept answers exclude/include
the supplied recipients. Actual relationship implementations remain **Unknown**.

**Executed health boundary (`0x2e9150–0x2e93bc`):** with maximum 120 and rank 20,
health one float32 step below 119 and exactly 119 receives an increment. One
step above 119, 120 and 121 do not. The equality case exceeds the maximum after
addition: there is no final clamp in this function. The owner increment cached
at construction (`0x2e8ffc–0x2e90a0`, field `+0x1c`) stays fixed when its maximum
changes; another recipient uses its current maximum on each call. The
twofold-maximum control produces twice the other-recipient increment, bit exactly.
All stored amounts also match the existing model's ordered float operations.

**Executed non-player contrast (`0x2e93c4–0x2e95b0`):** living flags `0x20` versus
dead flags `0x28` control entry into the box-query branch. The owner bypasses the
ally callback; other recipients require it. At rank 1, `(x,z)=(60,60)` is accepted
by the planar distance test, and health already at maximum rises above maximum.
At x=61 it is rejected. The query is scripted: the latter is deliberately an
out-of-box input to isolate the callee's own radial rejection, not evidence about
the spatial collector. Object health at `+0x228` is the tested destination.

**Executed lifetime (`0x2e90b8`):** uninterrupted clock sequences at ranks 1, 10
and 20 each survive call 67 and record destruction on call 68. Each call,
including 68, adds health when the guard permits; the fixture keeps health low
between calls to isolate this fact from saturation. Tint writes occur on the
first eight calls. Adjacent-float controls around `0x3e050ef8` demonstrate the
strict pre-increment tint test. Three separately constructed preimages produce
post-increment clocks immediately below, exactly at and immediately above
`0x3f90a1df`; only the last ends the effect, after its health addition.
The increment is `0x3c888888` under the emulator's `ps2` arithmetic. This is
isolated execution, not a measurement on hardware or in a running game.

## Living-player count

**Executed, synthetic.** A mode-A slot-22 callback writes 0 to `g_alivePlayerCount`
`0x4f8420` on its first call. The original at `0x2e9180` reads that word again
on the next iteration and stops, so only the first recipient is healed. Round 4's
`healing_run` kept the initial Python `range` and called slot 22 twice. That was
the whole of the disclosed mismatch: the second recipient's health and tint.
`support-parent-counts.json` records it as `PASS_WITH_MODEL_DISCREPANCY` beside
5,178 assertions and 560 matching comparisons.

The model now uses the same re-read. Both sides call slot 22 once, the first
record is the cached amount added to a nonzero sentinel, and the second record
stays at that sentinel. The comparison is one of the 561. No other reference
API or vector changed. Whether a live callback reaches this write is still
**Unknown**. The test is a synthetic memory poke, not a gameplay defect.

## Stubs, borrowed assumptions and remaining unknowns

The original startup, registered family functions, shared/private generators,
handle/list machinery and the harness's allowed mathematical/library callees
execute in `ee_emu`. The animation event probe also executes `0x16d748` directly.
Everything outside `Rig.real` remains a recording stub inherited from
`difftest_skills_b.World`; unknown targets fail. In particular:

- `pool_new` supplies zero-filled synthetic blocks, with controlled success or
  failure. Resource/text lookups supply synthetic memory. Sound, notice, animation
  start, particle-group operations, particles and spell destruction are recorded.
  The effect-side object constructors borrow the existing harness's one shared
  draw behavior; they do not create real rendered objects or prove cleanup.
- World arc, sphere and box collectors return immutable test lists. Their
  geometry, ordering and capacity are not validated. Handle lists themselves run
  through the existing comparison. Slot 20/21/22 answers are controlled; slot 26
  turning and slot 30 stun application are recorded, not physically applied.
- `Player_move` is a no-op. `Player_animStep` returns forced events, including
  the separate animation probe's results. Attachment-point lookup returns the
  passed origin. Model samples use the existing seeded stub with a fixed nonzero
  sample count of 3. Zero-sample behavior is not claimed.
- `damage_apply` returns 1 without actual damage. The four stun controls alone
  script a post-damage health write. They do not test mitigation, death processing
  or composed damage-chain draws. Network identity/anchor and presentation stubs
  remain the existing harness's behavior. Terrain height is scripted flat.
- Both model and emulator share the existing arithmetic helpers and read the
  same privately initialized statistics. Agreement does not independently prove
  physical-console rounding or the provenance/meaning of each statistic. The
  integer cost and damage/cap assertions add separate compact oracles; no raw
  statistic table is used as an expected vector.

**Unknown:** actual spatial queries, actual team predicates, animation resource
validity and movement, destructor
and free behavior, scheduling of dead owners, and composed gameplay. The cast
helper's debit, recast and prediction-copy refusal, the creature HP subtraction,
the stun-timer store, the player damage slot, the player death test and the
knock-back speeds are executed in the
[numeric contract](player-spells-numeric-r3.md). Default resource headers and
authored animation tracks are fixtures, not disc evidence. No public server or
gameplay client was contacted.
Cleanup testing, repository-wide tests and the combined handoff are reported
separately in [the round-3 handoff](player-spells-r3.md).
