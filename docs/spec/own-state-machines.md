# Own creature state machines

2026-10-20, round 4. SLUS-20973 US v2.00. The ten classes whose run function is its
own state switch, rather than the shared creature base. Clip selection for the
state they request is already the round-3 table in
[creature-animation-dispatch](creature-animation-dispatch.md) and the per-class
rows of [creature-animation-dispatch-classes](creature-animation-dispatch-classes.md).
This document is the tick that decides the next state, and the few animation
calls the run function makes itself.

**Executed** means one original run function in `tools/ee_emu.py`, callees
stubbed, synthetic object, checked by `tools/difftest_own_machines.py` against
`tools/ref_own_machines.py` (253 ticks, plus three NPC root-motion stores).
The synthetic lock is `tools/test_ref_own_machines.py`. Not a running game:
a helper returns the value the vector asks for, and a branch these vectors
never take is not claimed. **Observed** is a prior reading at the address
given. **Unknown** is not settled here.

Gnaw and Skelight already had executed bodies (`ref_monsters_1.gnaw_run`,
`ref_arena_monsters.skelight_run`). Those APIs are unchanged. The new step
agrees with them on every vector below.

## 1. What a tick does to animation

A tick does not pick a clip by name. It does one of three things:

1. It requests a state through virtual slot 27. setState, tabulated in round 3,
   starts or blends the clip and stores `+0x232`. The run function's own
   slot 27 is stubbed here, so the request is recorded and the state word is
   left as it was.
2. It calls the animation player directly. In these ten run functions the only
   such call in the executed vectors is Critter's fidget
   (`anim_startBlendInOut` 0x16ceb0, flags 0x808, both blends 0.1).
3. It updates a track weight without starting a clip. AntQueen calls
   `0x2385dc` (ground, fade the bank tracks) or `0x238448` (air, the banking
   spring) and those stay one stubbed call. Their weight writes were not
   followed (**Observed** in `docs/monsters-2.md` at those addresses, not
   re-executed).

The shared prologue is the same shape on every class that has it: damage
(Critter has none — its takeDamage 0x255c54 is empty and the run never calls
0x110d30), `Creature_run`, `Creature_updateActive` (stubbed active, so the
inactive return is not taken), `Creature_stepAnim`, knockback, slot 23.
Skelight also calls holder slots 15 and 22, Skeleton holder slot 21, NPC and
GnomeNavigator a name compare. Those are omitted from the decision lists.

Comparisons of the creature clock `+0x300` with a deadline `+0xf4` are signed.
"Queue < 4" is the byte at `+0x118` (a track count), not the flag halfword at
`+0x11a`. AntQueen's flight deadline is `+0x3d4`, a different word from `+0xf4`.

## 2. Gnaw — run 0x267654, setState 0x267a0c

| state | executed decision |
|---|---|
| 0 | slot 25 → 3; else away from home → 1 |
| 1 | slot 25 → 3; else `moveToDest` |
| 3 | no target → 0; first `canSee` → 5; second `canSee` → turn; else `moveToTarget` |
| 5 | first `canSee` → 6; second → turn; else not rooted → 3 |
| 6 | turn; event bit 0 → `hitTargetInArc`; anim flag 8 clear → 5 |
| 0x10 | attack ready → 0, else flee |
| 0x12 | anim flag 0x10 clear → 5; the flag set → stay |
| 0x13 | not stunned → 3 |
| 0x14 | `deadUpdate` and `obj_delete`, every tick |
| any other | → 0 |

No seed draw in the run. The bite-clip draw is inside setState (round 3).
The two `canSee` calls are the arc test and then the any-direction test; with
a stub they are distinguished by order, not by geometry.

## 3. Skelight — run 0x2a8b84, setState 0x2a91b8

Same chase shape as Gnaw, with these differences (all executed):

| state | decision |
|---|---|
| 3 | first `canSee` → 6 (not 5) |
| 5 | `canSee` → 6; else not rooted → 3. No second `canSee` |
| 6 | with a target and event bit 0: holder slot 17, then `hitTargetInArc`. Anim flag 8 → turn, and `+0xf4` is not decremented. Otherwise `+0xf4` loses 1 (wrapping). Signed `+0xf4` ≤ 0 → 3. A swing with no target and flag 8 clear still counts down |
| 0x12 | → 3 on the same tick, no flag test |
| 0x13 | not stunned → 0 (not 3) |
| 0x14 | `deadUpdate` only (setState already deleted it) |
| 0x17 | anim flag 0x80 → 0, then `fx_spawn` on that tick as well. Flag clear: `fx_spawn` only |
| any other probed | no request |

setState of state 6 stores `+0xf4 = 1` (**Observed**, `skelight_set_state`).
The countdown then leaves on the tick the clip flag clears, or sooner if the
word was already ≤ 1. Flag 8 with a leftover count of 0 and no target still
requests 3, because the compare runs even when the decrement was skipped.

## 4. GnomeNavigator — run 0x26a1e0, setState 0x26a3f4

Follow mode is creature-flag bits 0x400000 and 0x800000. Either bit is enough.
With neither bit, state 0 does nothing even if the timer has expired or the
creature is away from home.

| state | decision |
|---|---|
| 0, following | clock > `+0xf4` → 1; else away → 1 |
| 1 | `moveTo`; arrived, or clock > `+0xf4`, → 0. Both can be true; the call still happens |
| 3 | no target → 0. A target produces no move and no request |
| 5 | not rooted → 3 |
| 0x13 | not stunned → 0 |
| 0x14 | `deadUpdate` |
| 6, 0x12, and the other probed numbers | no request |

The level-name test that skips damage on `beachhub` / `island2` sits in the
prologue (**Observed**, `docs/monsters-2.md`). It was not varied here.
setState refuses a request for 1 unless a follow bit is set, and refuses 6
and 0x12 (**Observed** in that note; the run side never asks for those).

## 5. Mermaid — run 0x285c58, setState 0x285ddc

Every probed state, including ones with no decision, starts with a zero
`moveBy`. Arrival from `moveToDest` does not change state.

| state | decision |
|---|---|
| 0 | clock > `+0xf4` → 1 |
| 1 | clock > `+0xf4` → 0; else `moveToDest` |
| 3 | no target → 0 |
| 5 | not rooted → 3 |
| 0x12 | anim flag 0x10 clear → 0 |
| 0x14 | anim flag 0x80 → `obj_stopRunning`. No `deadUpdate` and no slot 27 |
| 0x13 and the other probed numbers | no request |

## 6. Natasla — run 0x29dbf0, setState 0x29dc3c

Executed across idle, a noisy state-1 tick (seen, away, a target) and death:
no decision call and no slot 27. The class has no AI switch. Animation, if
any, is whatever setState was asked for by something outside this function
(round-3 rows; several requests store the state and start nothing).

## 7. NPC — run 0x29ea40, setState 0x29efcc

| state | decision |
|---|---|
| 0 | creature flag 0x8000000 (the path flag) → 1. Otherwise nothing |
| 1 | `moveToDest` after the root-motion gate below |
| other probed | nothing. No damage, no slot 25, no target chase |

**Executed** root gate, state 1: if either root-motion word `+0xbc` or `+0xc0`
has absolute value greater than 0.5, `+0xb8` is stored as 0 for the move and
then restored. The pattern 0x3f000000 (exactly 0.5) does not clear it; one
ulp above, and the same step below −0.5, do. `root_clears_speed` locks the
predicate. The restore is the truncated speed; only an integer-valued speed
was measured, so the truncation itself is **Observed** (`docs/monsters-2.md`),
not a new measurement.

The `we_king` lump match (strcmp in the prologue) enters a rejection loop at
0x29ec6c. With a sample helper that never accepts, it does not finish.
**Unknown** here: the loop's accept condition. The ordinary, non-matching
name is the executed path.

## 8. AntQueen — run 0x236f78, setState 0x237918

Ground states call 0x2385dc. Air states call 0x238448. State 5, the stun
states and the empty states call neither.

| state | decision |
|---|---|
| 0 | slot 25, and a second slot 25 unless the first returned true while the queue was below 4 (0x237044, 0x237080). Either true result with queue < 4 → 3. Otherwise clock > `+0xf4` → 1 |
| 1 | slot 25 → 3; else `moveToDest` |
| 3 | no target → 0. One `GameObject_rand`: `(rand & 3) == 0` and the rear-cone helper returns a creature → 7; else `canSee` → 6. Otherwise `moveToTarget`, and if clock > `+0x3d4` and queue < 4 → 8. The rear test is not followed by `canSee` when it misses. No target: the rand is not drawn |
| 5 | same rand and, only with a target, the same two tests. Otherwise not rooted → 3 |
| 6 | event bit 0 with a target → `hitTargetAtReach` and no turn (the hit latches `+0x3cc`). Else with a target, turn. Anim flag 8 clear → 3. Both the hit and the leave can be the same tick |
| 7 | event bit 0 → a null call (the skill-table slot is 0 under this stub) then `hitTargetOrPlayerInArc`. No target test. Anim flag 8 clear → 3 |
| 8 | no target → 0. clock > `+0x3d4` → 0x17. Anim flag 8 → stay (takeoff still playing). Else `canSee` → 9, then one rand, and `+0x3d4 = 0` when `rand % 3 == 0` (executed for 0 and 3; 1 and 2 leave the word). Else a second `canSee` → turn, else `moveToTarget` |
| 9 | event bit 0 with a target → null call, `hitTargetAtReach`. Turn every tick a target exists, including the tick the clip ends. Flag 8 clear → 8 |
| 10 (0xa) | the same hit and turn. Flag 8 clear → 0x17 |
| 0x12 | flag 0x10 clear and queue < 4 → 3. Queue ≥ 4 stays |
| 0x13 | not stunned → 0 |
| 0x14 | `deadUpdate` |
| 0x17 | no target → 0. Flag 8 → stay. While clock ≤ `+0x3d4`: `moveTo` the point at `+0x104`; arrival, or failed-search count `+0x2c4` ≥ 31, stores `+0x3d4 = 0` on that tick and does not yet look for a landing. After the deadline: turn, `canSee` → 0x18 |
| 0x18 | flag 8 clear and queue < 4 → 3 |
| 0x19 | with a target, on the tick clock == `+0xf4 − 120`: `cos16`, `sin16`, `pool_new` (0x14fdb8, the AntWave). clock > `+0xf4` and queue < 4 → 3 |
| 2, 0x10, and the other probed holes | no request |

States 10 and 0x19 are executed once entered. Nothing in this run requests
them (**Observed**: the run's immediate requests are 0, 1, 3, 6, 7, 8, 9,
0x17, 0x18). Who would ask for 10 or 0x19 was not re-searched; the earlier
note found no in-class requester.

The banking helpers are not followed, so this does not re-execute the spring.
setState is what starts takeoff, sting, walk and the fly tracks (round-3
rows). Run only decides when to ask.

## 9. Skeleton — run 0x2a6864, setState 0x2a7768

Weapon kind is `+0x3d0`. Kind 4 is the bow. The idle and wander sight test
calls slot 25 once; a bow calls it again unless the first call already
requested 3 (the same shape as the queen's idle).

| state | decision |
|---|---|
| 0 | slot 25 (bow: the second call as well) → 3. Else clock > `+0xf4` → 1, else away → 1 |
| 1 | the same sight test → 3. Else clock > `+0xf4` → 0, else `moveToDest` |
| 3 | no target → 0. Bow: `canSee` → 8; second `canSee` → turn; else `moveToTarget`. Melee: `canSee` → 6; else ally-in-line non-zero → one rand and state 5; else second `canSee` → turn; else `moveToTarget` |
| 5 | bow `canSee` → 8; melee `canSee` → 6. Else once not rooted: clock > `+0xf4` → 3; no target → stay; ally-in-line returning 0 → 3. A non-zero ally stays. Rooted stays after the unroot call |
| 6 | event bit 0 → holder slot 17, `hitTargetAtReach`. Anim flag 8 → turn. Flag 8 clear → `+0xf4` counts down, and signed ≤ 0 → 3. Flag 8 holds the count (executed: timer 1 stays 1). Hit and turn both happen when the event and the flag are set; the hit is first |
| 8 | no target → 0, and if flag 8 is clear the same countdown can also request 3 (executed: timer 1, flag clear → requests 0 then 3; timer 5 → only 0, word becomes 4). With a target: `cos16`, `sin16`, `leadTargetPoint`, and slot 26 while flag 8 is set. Flag clear: the countdown, → 3 at ≤ 0 |
| 0x10 | ready → 0, else flee |
| 0x11 | clock > `+0xf4` → 3 |
| 0x12 | flag 0x10 clear → 3 |
| 0x13 | not stunned → 0 |
| 0x14 | `deadUpdate` |
| 0x17 | `fx_spawn` every tick; flag 0x10 clear → 0. The effect is first, then the request. The flag is 0x10, not Skelight's 0x80 |
| 7 and the other probed holes | no request. setState has a case 7; this run never asks for it |

**Not executed:** the state-8 release when event bit 0 is set. A rand stub
that keeps returning 0 does not leave the in-sphere rejection at 0x2a70b0, so
the projectile choice (cold / fire / burst / plain missile) is still the
**Observed** account in `docs/monsters-2.md`, not a completed tick. The ally
wait stores `+0xf4 = clock + 240 + rand % 240` (**Observed** there); the
executed tick shows the rand call and the request for 5, not the stored sum.

## 10. Critter — run 0x255008, setState 0x255c5c

No damage call, no slot 23, no target pick. Class flags are `+0x43c`.
Flag 0x10 skips `moveBy` / `moveTo` and nothing else. Flag 2 uses
`moveToDirect` instead of `moveTo`. Flag 8, on an arrival that is still
inside the timer, picks a new wander point instead of returning to idle.

| state | decision |
|---|---|
| 0 | `moveBy` unless flag 0x10. If fidget clip A exists and clock > `+0x410`: `anim_startBlendInOut` (flags 0x808, blends 0.1) and one rand to reschedule; when clip B also exists, a rand is drawn first. That fidget skips the leave test even if the wander timer has expired. Otherwise, once anim flag 8 is clear and a move clip exists: clock > `+0xf4` → 1, else away → 1. Flag 8 does not even call the away test |
| 1 | `moveToDirect` (flag 2) or `moveTo`, unless flag 0x10. On arrival or clock > `+0xf4`: with an idle clip → 0, except flag 8 on an early arrival, which re-picks (`clearPath`, wander, one rand). Without an idle clip, the same re-pick. Anim flag 8 does not block the return to 0 |
| 0x10 | no target → 0 if an idle clip exists, else 1. With a target and a flee clip: `fleeFrom`. clock > `+0xf4` → `handle_clear` and 0 if idle, else 1 |
| 0x14 | `obj_stopRunning` and slot 28 |
| 0x16 | the path follower 0x210128. Return 0: that call only. Return non-zero and the snap byte `+0x3d9` clear: `angle_approach` 0x166c18. Snap set: no approach call |
| 0x17 | the same fidget, with no `moveBy` |
| 2–0xf except 0x10, and 7 | no request |

**Not executed:** states 0x18 and 0x1a (the inactive object is deleted there;
`updateActive` is stubbed to 1), player proximity on 0x17/0x19 (no player
table), and root motion while a path is followed (`stepAnim` is stubbed and
writes no `+0xbc`). The species table and which clip pointer is which remain
the **Observed** constructor note in `docs/monsters-2.md`.

## 11. Soul — run 0x2a9870, setState 0x2aac38

An owned soul (`+0x3c8` set) and state 0x1b skip the idle `moveBy`. Every
other probed state starts with one. The demon test is
`(g_simFrame ^ serial) & 15 == 0`, then `isDemonNear` 0x2ab2b4. It is not a
rand draw. Frame 0 and 16 call it; frames 1 and 15 do not.

| state | decision |
|---|---|
| 0 | on a phase frame, demon near → 0x18. Else clock > `+0xf4` → 1, else away → 1 |
| 1 | on a phase frame, demon near → 0x18 and `moveTo` is skipped. Else `moveTo`; arrived or clock > `+0xf4` → 0 |
| 0x18 | on a phase frame, demon not near → 0. Near, or an off-phase frame, stays. The timer does not leave this state |
| 3 | no target → 0. Nothing in this run requests 3 |
| 5 | not rooted → 0 |
| 0x12, 0x19 | anim flag 0x10 clear → 0x18 |
| 0x17 | clock > `+0xf4` → 1 |
| 0x14 | one `model_getRandomSample` when that helper returns 0, including while waiting. clock > `+0xf4` or anim flag 0x80 → `obj_delete` |
| 0x22 | the same sample call; the same end condition → `obj_stopRunning` instead of delete |
| 0x1b | samples, `mat_place`, `mat_rot`, `cos16`, `sin16`. clock > `+0xf4` → delete, and terrain is not asked. Otherwise terrain; from z 0 with the terrain stub returning 0 the tick deletes (the inline step goes below 0); from z 100.0 it does not |
| 0x1a while owned | no call |
| 6 and the other holes | `moveBy` only, when not owned |

Owned state 0 still runs the demon test and will request 0x18. setState's
filter, which refuses that request while `+0x3c8` is set, is **Observed**
(0x2aaca0) and was not re-executed; the slot 27 stub accepts the request.

**Not executed:** victim steering and the per-player damage in 0x1b (no
player table), a sample helper that returns a point (the "up to 3 particles"
bound), and `isDemonNear`'s real box test (the stub returns the vector's
bit). The phase gate and the branch on that bit are executed.

## 12. Still open on these ten

- AntQueen bank-spring weights, and any caller of states 10 and 0x19.
- Skeleton's arrow release (event bit 0 of state 8) and the numeric ally-wait
  deadline.
- Critter proximity, the inactive delete, and path root motion.
- Soul thrown-state hits, and the particle rejection bound.
- NPC `we_king` particles.
- GnomeNavigator's level-name damage skip.
- Clip choice when two setState fields are both set is in
  [creature-animation-dispatch](creature-animation-dispatch.md) section 7
  (`ref_field_precedence`). These ten setState rows had no second field condition.
  Other setState side effects (loot, flags, the held-soul filter) were not run again.
