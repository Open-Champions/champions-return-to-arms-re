# Numeric IDs 16 and 23: bounded round 3

Status: **Executed, partial**. The original functions were executed in
`tools/ee_emu.py` against the existing independent `tools/ref_skills_a.py`
models by `tools/difftest_spell_projectiles_r3.py`. The run passed 402 original /
reference call comparisons and 3,532 assertions, with zero model mismatches,
zero unexpected callbacks and zero accepted interpreter faults. These are
synthetic function executions, not gameplay. No usage telemetry is available;
these IDs were selected as entry projectile routes, not by usage frequency.

The round-2 audit at `cursor-runs/audits/research-spells-r2.md` passed its narrower
scope; its earlier executions were inspected, not counted as round-3 runs.
This addition uses the family rig without changing existing reference APIs,
scenario vectors or files. Its public content contains authored contracts and
addresses, not game text, raw tables, disassembly or executable bytes.

## Executed contracts and addresses

| ID | Cost / admission / cast | Constructor / run / hit |
|---|---|---|
| 16 | `0x2ed1e4` / `0x2ed20c` / `0x2ecfcc` | `0x2eba48` / `0x2ebc50` / `0x2ecae8` |
| 23 | `0x2f8af8` / `0x2f8b24` / `0x2f8840` | `0x2f7404` / `0x2f77c0` / `0x2f84e4` |
| 23, child projectile | reached through the parent expiry | `0x2f68e0` / `0x2f6b3c` / `0x2f71ac` |

Original initialization runs at `0x16ac74` and `0x1ebca0`. Shared statistics
routes are `0x3c85fc` (tier 1), `0x3c8690` (tier 2 and cap), `0x3c87f0`
(owner selection) and `0x3c8864` (handle selection). Shared movement and
collision run at `0x1509f8`; object-generator transitions are at `0x1509d0`.
Constructors nested within a cast or expiry are included in that comparison,
not counted as separate calls.

### Exact cost, ranks 1–20

**Executed:** every rank of both IDs matches both the existing `mana_cost`
model and a new, independently authored rational-arithmetic oracle. Let
`Q(x)` truncate a nonnegative normal value to 24 binary significant bits:

- ID 16: `Q(7 + Q(3 * (rank - 1)))`.
- ID 23: `Q(7 + Q((6291525 / 2097152) * (rank - 1)))`.

The latter coefficient is exactly `3.000032901763916015625`. The new oracle
constructs that binary32 coefficient from the documented decimal `3.000033`
and performs each arithmetic truncation separately using integers and
fractions, without calling the reference FPU arithmetic or decoding the
original cost instructions. Comparison is equality of the final 32-bit float
pattern, never a tolerance. Its scope is the positive, finite rank-1–20
operands here; it is not a general PS2 FPU replacement. The emulator and
reference use their existing `ps2` FPU model, not a hardware measurement.

The negative control replacing ID 23's step with exactly 3 differs at all
19 ranks above rank 1. Both getters make no stores in these calls. Original
initialized metadata is kind 0, recast 30 frames and flags 0 for both IDs.
**Unknown here:** actual mana eligibility/payment, recast countdown, animation
release and prediction-copy admission through the player state machine. The
30-frame value is metadata evidence, not execution of that state machine.

### Admission, creation and targeting

**Executed:** each ID's admission function returns 1 without callbacks for
null, player, prediction-copy and non-player inputs. This tests only the
individual function; it does not authorize those inputs through the full
player route. Both casts return 0 whether allocation succeeds or fails. Casts
at every rank 1–20 set the expected rank, owner handles and expiry fields.

ID 16 requests an arc query with radius 360, angle 75 and the player owner as
filter, then consumes the supplied first list node. At creation frame +14 and
+15 it does not turn. At +16 it turns for rank 5 with a candidate; rank 4 and
an empty list are negative controls. The staged target produces a turn of 182
angle units at rank 5. A two-candidate case confirms first-node selection even
when the second candidate would turn in the opposite direction. The velocity
is the existing angle-library cosine/sine result multiplied by 450. Exact
mathematical `(450, 0, 0)` at heading zero is not assumed.

ID 23 makes no arc query during the cast. Its initial velocity uses the same
angle library multiplied by 350. No target acquisition is inferred from a
successful cast. **Unknown:** the real spatial query's filtering/sorting and
real target-list deletion/reuse behavior. The rig supplies the list and does
not execute the world-query implementation.

Allocation failure controls deny the primary allocation and verify zero
return, no initialized projectile and no scheduling callback. A separate
ID 23 allocation deliberately supplies a nonzero `+0x98`; the original and
model preserve it. Thus the constructor does not guarantee a zero initial
spin field under this fixture. The inherited allocator normally zero-fills;
the real allocator's initialization contract remains **Unknown here**.

### Effects and hit gates

**Executed:** 80 direct hit comparisons cover ranks 1–20: ID 16 with both kind
selectors (`0x10` versus other) and both tested PvP flag states; ID 23 with
player and non-player owners. Full outgoing callback arguments and every
unmasked non-stack store outside the argument scratch buffer are compared
against the independent model.

- ID 16 selects statistic 1 for kind byte `0x10`, otherwise statistic 0,
  always from tier 1. It passes direct low/high float amounts, an empty
  descriptor, and flag `0x80000` outside the tested PvP mode (0 within it).
  The maximum uses the documented positive `trunc(rolled + 1.0)` path.
  Two object-generator transitions are checked. The original/reference
  comparison checks the exact maximum; the explicit range assertion is an
  additional bound, not the sole numerical test.
- ID 23 selects statistic 0 through its owner handle. It passes zero direct
  float amounts and descriptor type `0x16` with the selected minimum, randomized
  maximum and zero fourth field. One object-generator transition is checked.
  Child hits use statistic 2 through their owner handle instead.

Positive/negative controls cover the scripted enemy answer, a non-player
creature's flag `0x200`, the player-bit exception to that filter, absent owner
handles, preexisting hit latches and non-creature contacts. ID 16 stops after
its first accepted hit. ID 23's primary handler still damages when its latch
is already set. ID 23 non-creature contacts bypass the creature enemy query
and pass a null attacker. These are callback admission contracts, not proof
of damage to real non-creature objects.

An additional ID 23 sequence accepts two successive targets and then rejects
a contact: the latch stays set, but the last-target pointer `+0xcc` becomes
zero on the rejected call. This limits the common shorthand that this field
always contains the last successfully damaged object. Child controls verify
excluded-target rejection, already-hit rejection, scripted friendliness,
flag filtering and the absent-owner path. Final HP, resistance, status,
knockback and death results remain **Unknown** in this file because `damage_apply`
is a stub. The [numeric contract](player-spells-numeric-r3.md) replays these hit
arguments through original `damage_apply` and creature `takeDamage`, and records
the player slot, the player death test, and the knock-back speeds.

### Timing, contact and child release

**Executed:** primary expiry is creation +180 for ID 16 and +120 for ID 23;
each survives boundary−1 and deletes at equality and boundary+1. Deletion
means a recorded destructor callback with argument 3. The original destructor
and actual reclamation are not executed. Before natural expiry, no contact,
ground contact, rejected object contact and accepted object contact are
separate controls. Ground contact ends the projectile; object contact ends it
only after the hit handler sets the latch. Movement and overlap checks run
for real against a scripted box-query answer and terrain height.

ID 23 child-release comparisons cover player ranks 4/5, 6/7, 20/21 and
non-player ranks 9/10, 14/15, 20/21, plus rank 24 for both owner types and
non-player rank 26. They
check the statistic-1 count,
allocation attempts, ten terrain probes per child, inherited rank and excluded
target, and child expiry at creation +60. The `cap 20` argument only clamps
the non-player tier route; the player route uses tier 1 without applying it.
Rank 24 distinguishes the player bypass: eight children for the player versus
two for the non-player. Non-player rank 26 distinguishes the clamp: two
children where the uncapped reference statistic is three. Ranks 20/21, or
non-player rank 24, alone would not distinguish the clamp because of rounded
counts.
The fixture supplies eight child blocks so higher counts are not silently
turned into allocation failures. One control denies every child and debris
allocation and still observes all three child attempts and primary deletion.

Three direction controls supply ten blocked probes, ten clear probes, or two
separated clear probes among blocked probes. Every child uses the initial
heading when none is clear, otherwise the last clear heading. The explicit
oracle reverses only the final 33 own-generator transitions for three
children (one initial draw plus ten probes each), avoiding an assumed count
for preceding particle/debris draws. Zero and negative ray results are clear;
positive results are blocked. The real terrain function is not executed.

Child lifetime checks at +59/+60/+61 confirm survival/deletion on the same
inclusive expiry boundary. **Unknown:** gameplay travel distance, scheduler order,
frame-counter wrap, deleted candidate-node behavior, and release after the
second owner handle `+0x54` is invalidated. The latter is dereferenced during
child construction and was deliberately not treated as a proven safe path.

## Dependencies and borrowed assumptions

The retained `Rig` runs original modeled function bodies, angle math and
reachable library helpers. It compares callback order/arguments, exact
non-stack store sets and resulting bytes, shared seed/draw count and defined
return values. No memory masks are added. Both-sided faults, one-sided
faults and unknown calls are failures in this addition.

Every external call recorded during these cases remains a stub unless the
family rig includes its original body in the real-function set. The reached
stub surface is checked against the unchanged family registry. In particular:

- Allocation: `pool_new` returns bounded synthetic blocks, zero-filled except
  the explicit spin-prefill control. Failures are scripted. No real pool or
  memory-pressure behavior is inferred.
- Handles and scheduling: `handle_link`, `handle_clear`, grid/run-list helpers
  and destruction callbacks use the family's synthetic nodes or recording
  callbacks. They do not prove ownership/lifetime safety.
- Queries: `world_collectObjectsInArc` and `world_collectObjectsInBox` return
  explicit lists. `terrain_height` returns a controlled value relative to the
  projectile; `terrain_raycast` returns the controlled sequence; `water_test`
  always returns false. Water effects are outside this run.
- Enemy and victim callbacks: the player `Creature.v20` answer is scripted.
  Non-player base functions included by the family rig can execute, but this
  is not a full faction system. `damage_apply` always returns 1 and changes
  no victim state in this addition. The target's collision callback is
  recorded, not a composed creature response.
- Presentation: particle, light, trail, resource lookup, sound and effect
  callbacks use the family answers. `PhProp_ctor` supplies scripted fields;
  `PhProp_initPhysics` and `LightEffect_ctor` are not real physics/visual
  execution. Shared draws hidden inside these stubbed constructors are not
  executed; the model's separate hidden-draw annotations are not gameplay
  random-stream evidence. `libc_sprintf` uses the inherited synthetic token,
  never exported game text.

The callable stub identifiers for this bounded route are `pool_new`,
`handle_link`, `obj_getPropInt`, `obj_runEveryFrame`, `obj_updateGridCell`,
`world_collectObjectsInArc`, `world_collectObjectsInBox`, `terrain_height`,
`terrain_raycast`, `water_test`, `Creature.v20`, `Creature.v6`, `Creature.v1`,
`damage_apply`, `trail_create`, `trail_addPoint`, `light_link`, `light_relink`,
`particle_spawn`, `res_find`, `sound_playOnObject`, `sound_playAtPos`,
`libc_sprintf`, `fx_spawn`, `LightEffect_ctor`, `PhProp_ctor` and
`PhProp_initPhysics`. These are existing authored callback identifiers.
The stack and argument scratch buffer are excluded by the inherited comparison;
no additional masks are applied.

Statistical effect/count expectations use the existing independent model,
not a new independently reconstructed statistics system. Both sides use the
same scripted external answers and initialized private tables. The cost
oracle and final direction-selection check add separate narrow assertions;
they do not remove the other borrowed dependencies. No running-game result
is claimed.

## Reproduction and counts

From this worktree, with the read-only `local/SLUS_209.73` symlink present:

```sh
mkdir -p local/spells-r3
PYTHONDONTWRITEBYTECODE=1 python3 -c 'import unittest,runpy,sys; sys.path.insert(0,"tools"); sys.argv=["tools/difftest_spell_projectiles_r3.py"]; runpy.run_path(sys.argv[0],run_name="__main__")' > local/spells-r3/projectiles-run.txt 2>&1
```

The input's digest is checked against the existing family's expected digest;
missing/wrong input exits 2, not PASS. Output is counts-only under
`local/spells-r3/`: `projectiles-counts.json` and the redirected log. The
`--output` argument refuses destinations outside that directory. Python
bytecode generation stays disabled and `unittest` is loaded before adding
`tools` to avoid `tools/dis.py` shadowing the standard library.

| Group | Comparisons |
|---|---:|
| Cost, every rank 1–20 | 40 |
| Admission | 8 |
| Cast fields, every rank 1–20 | 40 |
| Allocation denial / prefill | 3 |
| Direct effects | 80 |
| Hit gates / ordered hit sequence | 14 / 3 |
| Homing boundary and candidate order | 13 |
| Primary expiry / contact ending | 6 / 8 |
| Child release / direction selection | 16 / 3 |
| Child hit / child expiry | 6 / 3 |
| Additional compared setup calls | 159 |
| **Total** | **402** |

The receipt contains 3,532 assertion evaluations. Of the 402 comparisons,
40 are original cost calls checked against two oracles; the remaining 362
use `Rig.compare`, including 159 setup calls. **Result: PASS, zero mismatches.**
An initial added velocity assertion incorrectly assumed exact mathematical
axis values; all original/reference comparisons already matched. That
assertion was corrected to use the established angle-library result before
the final run. No reference model mismatch or existing-vector edit was needed.

The read-only review identified the need for the discriminating non-player
rank-26 case and for sanitization during initialization. Both were fixed.
A separate injected `UnimplementedInstruction` at initialization passes four
guard checks: exit 1, no comparisons, one type-only failure counter, and no
instruction diagnostic exported. Its deliberately failing probe receipt is
`local/spells-r3/projectiles-init-guard-counts.json`; the guard test itself is
PASS in `projectiles-init-guard-check.txt`. It is not a model mismatch or part
of the 402 original comparisons. The stub inventory check is in
`projectiles-stub-check.txt`: 27 observed, 27 documented, zero undocumented.

The broader suite and cleanup are reported in [the combined handoff](player-spells-r3.md).
