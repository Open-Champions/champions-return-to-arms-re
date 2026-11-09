# Player spell research: round 3 handoff

2026-10-27, `t3/research-spells-r3`, starting at `77c2f70`.
Status: **MORE — bounded original-function contracts documented; playable
integration and composed gameplay remain unknown.**

This round supplies executable contracts for numeric IDs **16, 23, 49 and 55**,
plus original cleanup for ID 4's existing projectile and its shared base.
The two entry projectiles and the melee/support pair are an **Inferred research
priority**, not a measured popularity ranking: no usage telemetry was supplied.
Private executable input remains under ignored `local/`; receipts contain counts.

## What a client port can use

| Scope | Documented result | Addressed evidence |
|---|---|---|
| ID 16 | Rank-1–20 cost, cast fields, forward-arc callback, first supplied target, rank/arm-time homing controls, filtered hit, outgoing direct damage and inclusive 180-frame expiry | Cost `0x2ed1e4`, cast `0x2ecfcc`, run `0x2ebc50`, hit `0x2ecae8`; [projectile contract](player-spells-projectiles-r3.md) |
| ID 23 | Exact fractional cost step, forward projectile, descriptor damage, repeated/rejected-hit bookkeeping, 120-frame primary expiry, rank-dependent child release and 60-frame child lifetime | Cost `0x2f8af8`, cast `0x2f8840`, run `0x2f77c0`, hit `0x2f84e4`, child run `0x2f6b3c`; [projectile contract](player-spells-projectiles-r3.md) |
| ID 49 | Rank-1–20 cost, equipment gate, target ordering, one animation-triggered strike, target cap, outgoing damage and conditional stun, action-state ending | Gate `0x2de334`, cast `0x2de3bc`, cost `0x2de60c`, run `0x2de7dc`; [melee/support contract](player-spells-support-r3.md) |
| ID 55 | Rank-1–20 cost, stable-list recipient/range/team gates, actual synthetic-state health writes, cached versus recipient-current maximum, first-eight-call tint and 68th-call ending | Cast `0x2e8cf8`, cost `0x2e8e94`, run `0x2e90b8`; [melee/support contract](player-spells-support-r3.md) |
| Existing ID 4 cleanup | Derived and base destructor order, real handles, names and registries, pool release, immediate terminal destruction, separate deferred flush | Run `0x2ca1a8`, derived `0x3ccfd4`, shared `0x3c2940`, base `0x14cf90`; [cleanup contract](projectile-cleanup-r3.md) |
| IDs 16, 23, 49, 55 numeric delivery | Original `damage_apply` amount, creature HP subtraction, cold timer, bash stun store, heal product, and cast-helper debit/recast | `0x1e8230`, `0x116638`, `0x118a58`, `0x2e90b8`, `0x1a42b8`; [numeric contract](player-spells-numeric-r3.md) |
| Combat round 6 | Hit direction `+0x2e0` and knock-back push, player block, stagger rolls, kill credit to `player_giveExp`, creature death and despawn, real cast bodies inside the helper | `0x1b5330`, `0x116638`, `0x1b2cc0`, `0x110d30`, `0x1108a0`, `0x1a42b8`; [combat round 6](combat-r6.md) |

These are **Executed** contracts: original instructions ran in `tools/ee_emu.py`
and were compared with existing independent reference models plus new narrow
assertions. The documents state the synthetic inputs, stubs and exact compared
outputs. Numerical rank formulas are bounded to tested ranks; original execution
does not by itself prove console FPU fidelity. One reference correction is
below. No other reference API or historical vector changed.

**Count correction:** the original healing walk reloads `0x4f8420` at `0x2e9180`
and stops after one slot-22 call when that callback clears the count. Round 4's
reference kept the initial range and called twice. That mismatch is
`local/spells-r3/support-parent-counts.json`: `PASS_WITH_MODEL_DISCREPANCY`,
5,178 assertions, 560 matching comparisons. The model now re-reads the count.
The same case matches, so the support probe is `PASS`, 5,173 assertions and 561
function comparisons, in `local/spells-r3/support-counts.json`. No other
reference API or vector changed. Reachability through a live callback is
**Unknown**.

## Prior evidence and the common player boundary

The prior research audits passed at `2225004` and `46b340a`. The first client
round's input-release finding was repaired in `947c002`; the second client audit
passed through `11ae759`. Those are **reviewed historical results**, not client
tests rerun in this research worktree. This branch began at `77c2f70` and does
not contain the earlier round's pipeline file; its contents were read using
`git show 46b340a:docs/spec/player-spell-pipeline.md`.

The prior pipeline observes the following common rules at `0x1a42b8` and the
state-5 interval `0x1ab4f8–0x1ab7dc`: the player helper dispatches the chosen
skill, then pays cost and sets recast even when the cast returns zero; ordinary
casts wait for animation blend 1.0 offline or 0.5 in network mode. A returned
zero can still mean an independently allocated projectile was created. Current
round-3 cast probes start at individual skill entries, so the composed player
admission, held input, mana debit and animation route remain **Unknown in these
new comparisons**. There is no newly invented universal cast delay.

The old client audit's explicit ID-4 cleanup refusal now has a tested research
contract. Removing that refusal still requires a separate native port, preserved
failure boundaries and client validation. The research worktree owns no client
implementation, and no playable support is claimed merely from this handoff.

## Partial and unknown

**Partial:** The four new spell families use the existing skill harnesses with
scripted world queries, allocation, relationships, victim damage outcomes and
presentation dependencies. IDs 16/23 also stub handle ownership; the 49/55
harness runs original handle/list functions on synthetic state. ID 55 really writes the supplied
health state; this does not establish the live game's surrounding health flow.
ID 49's 36th-advance strike uses a synthetic animation fixture and is not a
measured number of display frames or seconds from user input. Only the separate
cleanup harness exercises original pool reclamation and derived destruction.

**Executed after the family probes:** the [numeric contract](player-spells-numeric-r3.md)
runs the captured hit arguments through original `damage_apply` `0x1e8230` and, for a
creature victim, original `Creature_takeDamage` `0x116638`. It also stores the bash
stun with original `Creature_stun` `0x118a58`, checks the ID 55 heal product, and
runs `Player_castSkill` `0x1a42b8` with the cast slot returning 0. It also runs
`Player_takeDamage` `0x1b5330`, `Player_processDamage` `0x1b2cc0`,
`Creature_processDamage` `0x110d30` and `Creature_applyKnockback` `0x115eb8`.
Seeds 20973 and 7, 869 assertions, 0 failures.

**Unknown:** Real spatial-query outcomes and terrain, the hit direction, the
stagger threshold, creature kill credit, native casts composed inside the helper,
destructors other than the ID 4 cleanup, camera/audio/visual fidelity, full
selection-to-effect composition, campaign availability and a continuous
original/client session. Frame wrap and unprobed invalid lifetime states remain
unknown. Do not substitute approximate values or reuse one derived destructor for
another table without evidence.

The next implementation pass should pin this round's commits and take the
selected ID's complete addressed contract, including its remaining refusal
boundaries. Independent cost, targeting, effect and timing observations are
useful port inputs; they are not a claim of executable campaign acceptance.
