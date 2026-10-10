# The pose cache (D34 / rescan R1): can a draw-built skeleton pose reach shared state?

Follow-up to `docs/issues/rescan.md` R1 and ledger row D34. That finding described the
mechanism and left open whether it reaches a position that matters. This document traces
it for the Drundar arena classes first, then for everything else as far as the work got.

Evidence labels: **Observed** (read at the address given), **Executed** (the game's own
instructions run by `tools/posecache_test.py` on state the test built; see section 7 for
what that does and does not show), **Inferred**, **Unknown**. Nothing here was seen on a
running game, and that has not changed: the project's live game (the Play! emulator, not a
PlayStation 2 and not PCSX2; `FINDINGS.md`, "Run on the live game" (rows V1–V8) and `docs/issues/live-rig.md`) runs without video, and
nothing about the pose cache was looked at on it. The patches in section 8 are **untested on a running game**; no
test patch of the project has been run on one yet. `FINDINGS.md`
and `patches/` were not edited.

## 1. Verdict in short

| Question | Answer | Kind |
|---|---|---|
| Is the mechanism real? | Yes: a simulation query returns whatever pose is attached, and drawing attaches poses | Observed (section 2) |
| Does a skeleton position reach shared state? | Yes, in more places than R1 allowed. Beyond the obvious ones (cast position, thrown-weapon release, monster projectile origins) every debris prop does: a `PhProp` that comes to rest builds a resting `Prop`, whose constructor draws `g_randSeed`. The tick on which it comes to rest depends on where it started, and it starts at a joint. R1 called debris "presentation"; that is wrong | Observed (section 5) |
| Can the pose differ between machines at such a query? | Only in this pattern: the pose was built by drawing (or by an earlier query), the tracks were then changed by a call that does not detach, and the query follows with no animation step between (section 3) | Observed rules, Inferred completeness |
| Does that pattern occur for Player, Horsemen, Skelight, Zek or the weapon holders in the arena fight? | **Not found.** Players: `Player_updateCast` queries the skeleton at the tail of `Player_run` on every tick of a living player, after the step and after every track change of the tick, so a pose built by the simulation is attached on every machine when the tick ends and drawing never builds one for a real player. Knights and Zek: the one shared-state query (weapons dropped at death) runs before the step but before any track change of that tick. Skelight: particles only. Buffer exhaustion needs about 25 distinct animated models drawn; the fight has about a dozen | Observed steps; "not found" is Inferred |
| So is D34 the every-run arena desync? | **No route found; the lead is not supported for the arena.** It stays a real hazard for other classes (section 6) and under buffer exhaustion | Inferred |
| Fix | Section 8: inside the lockstep tick, make the query detach and rebuild instead of trusting the cache (13 words, executed under the interpreter). It is hardening and a diagnostic, not a known cure | proposal, untested on a running game |

## 2. The mechanism, with the facts R1 did not have

Structures: an animation state (creature +0x114) starts with a pointer to its pose buffer
or 0; count at +4, capacity at +5 (8 for every creature, set at 0x109df0), tracks of 0x20
bytes from +8. A pose buffer is 0x620 bytes: joint count at +8, 0x18 bytes per joint from
+0x10, owner state at +0x610, list links at +0x614 / +0x618, draw stamp at +0x61c.

| Fact | Where | Kind |
|---|---|---|
| `anim_getJointMatrix` builds only when the state's pointer is 0, otherwise converts the attached buffer | 0x16f738–0x16f74c | Observed |
| `anim_advance` clears pointer and owner on every call | 0x16d7b0–0x16d7c8 | Observed |
| `anim_buildPose` never writes the stamp. Only `anim_emitPose` does (0x16f8e4). A buffer taken by a simulation build therefore keeps an old stamp and can be taken again by any later build as soon as the walk from the old end of the list reaches it | 0x16ed8c–0x16eedc, 0x16f8dc–0x16f8e4 | Observed |
| The walk never takes the buffer at the recent end of the list | 0x16ed8c, 0x16eda8, 0x16edc8–0x16edd0 | Observed |
| A buffer that is taken has its previous owner's pointer zeroed first. This also holds for the static fallback buffer 0x7b89c0: it has an owner field like the others | 0x16ee88–0x16eea4 | Observed |
| When no buffer qualifies a draw caller gets nothing (default pose 0x7b8380), a simulation caller gets the fallback buffer; `anim_emitPose` never draws from the fallback: it detaches it and tries again | 0x16edd4–0x16ede4, 0x16f898–0x16f8b0 | Observed |
| With no fully weighted base track (`min(weight, life) ≥ 1`, time ≥ 0, joint masks covering every joint) the state ends with pointer 0 and the query reads the default pose | 0x16ede8–0x16ee80, 0x16f754–0x16f760 | Observed |
| A track is blended only when its clamped weight is at least 0.001 and its time is not negative | 0x16f0f0–0x16f150 | Observed |
| `anim_start` and `anim_startBlendInOut` always create the track at weight 0 (rate 1 per tick when the blend time is under one tick or the state was empty). They change the pose before the next step in two cases only: the state was empty (no base track: default pose) or full (the top track is replaced) | 0x16cfe0, 0x16ceb0 | Observed |
| `anim_syncToSimFrame` rewrites the time of **every** track, the fully weighted ones included | 0x1709f8 | Observed |
| `AnimState_copy` zeroes the copy's pointer, so the prediction copy never shares a buffer with the real player | 0x16ffe8 (store after the block copy) | Observed |
| `Creature_stepAnim` calls `anim_advance` only when bit 63 of the creature flags (+0xa8, "is active") is set. An inactive creature keeps whatever pose is attached for as long as it is inactive | 0x116324 | Observed |
| `Player_move` steps the animation itself (0x1b48e8 / 0x1b48f8) and afterwards writes the weight and life of track 1 directly (0x1b498c, 0x1b499c; a second block zeroes tracks 1–3 at 0x1b4bb8–0x1b4bc4). Those writes change the pose and do not detach | `Player_move` 0x1b4020 | Observed |
| `Player_updateCast` reads attach points 0 and 1 on every call, whether or not a spell is attached, and hands their midpoint to the player's slot 17, which passes it to every attached spell. `Player_run` calls it at the common tail of the state switch on every tick on which the float at 0x4d8b9c + slot × 0x4c30 (record +0xac, hit points) is above 0 | 0x1a3f70 (calls 0x1a3fe8, 0x1a402c); test and call at the label 0x1ac680 | Observed |
| The VU0 program that turns the blended joints into matrices is straight-line code with no state of its own between calls except the parent matrices it stores per depth | 0x3e5c50, 77 instructions | Observed |

Calls that change the pose at once and do not detach (**Observed**): `anim_push`,
`anim_pushWithWeights`, `anim_pushChained`, `anim_clear`, `anim_syncToSimFrame`,
`anim_randomizeTopTime`, `anim_dropNonPersistent`, `anim_stop` with a blend time (the zero-time branch calls `anim_releaseCaches` first, which detaches — corrected by the third documentation pass),
`anim_start` / `anim_startBlendInOut` on an empty or full state, and direct stores into
track fields (`Player_move` above; `SpellRaiseArmy_raiseInRing` 0x313e54 writes a track
time; `cut_advance` nudges track times, D8). That list of direct stores is short. The
field audit (`docs/issues/field-claims-audit.md` 4.2, row 30) adds `Player_run` itself
(0x1a6c08–0x1a6c1c; loops at 0x1a7298 / 0x1a72a0 and 0x1a7f08 / 0x1a7f10; indexed stores
0x1ab1a8, 0x1ab82c), `Player_updateCast` (0x1a423c, 0x1a4240, after its two skeleton
queries: it clamps a weight to 1 and sets a fade rate), `Player_idleFidget` (0x1bc388,
0x1bc390, called from `Player_run` 0x1a576c), `player_resetIdleAnim` (which releases the
caches) and `AntQueen_fadeBankTracks` 0x238638. The argument for the player in section 4
is not affected: all of these run inside `Player_run` before the tail query, except the two
stores of `Player_updateCast`, which do not change the blended pose until the next step
(*Inferred* there from the clamp rule). Calls that detach: `anim_advance`,
`anim_jumpTopToEnd`, `anim_snapTopToEnd`, `anim_releaseCaches`, `AnimState_dtor`.

## 3. When two machines can get different values

Write, for one animation state, S for an animation step (detach), M for a track change
that does not detach, Q for a simulation query, D for "this machine drew the object"
(between two ticks; builds only if nothing is attached).

| Sequence | Result |
|---|---|
| S … Q | fresh build from the current tracks: the same everywhere |
| S … Q … M … Q | the second Q returns the pose from before M — on every machine, as long as the buffer was not taken in between |
| S … D … Q | the draw-built pose; equal to a fresh one because the tracks did not change |
| **S … D … M … Q** | a machine that drew returns the pose from before M, a machine that did not returns the pose after M |
| S … Q … M … (many builds) … Q | the pose from before M where the buffer survived, a fresh one where it was taken. A machine that draws the object re-stamps the buffer every picture and keeps it for ever; a machine that does not loses it after about (100 − recently drawn) further builds |

So a difference needs a track change **after** the last possible draw and **before** the
query, with no step between: the change and the query both sit in the part of a tick that
runs before the object's own step, or the object does not step at all (inactive creature,
frozen creature, dead player), or the change is made by another object's code.

"Drew the object" differs between machines far more often than R1 said. Besides the view
frustum and the real local player, a machine that runs two ticks in one call of the frame
loop (which the netcode does whenever input arrives late) has no picture between them. For
the second tick it behaves like a machine that drew nothing.

Whether a pose is attached when a tick ends is itself decided by the simulation: if any
simulation query ran after the object's step, that pose is attached on every machine and
drawing does not replace it.

## 4. The arena classes

### 4.1 Player

Order inside `Player_run` (0x1a5030), **Observed** from the jump table at 0x536260 and the
call addresses:

| State | Step | Queries after the step | Queries before the step |
|---|---|---|---|
| 0 ranged | 0x1a8198 | `Player_castSkill` 0x1a837c, 0x1a9174; thrown release 0x1a83ec and bow release 0x1a8a18 (attach point 0 is the spawn position of the projectile and the point the aim is taken from) | none |
| 1 melee | 0x1aa170 | `Player_castSkill` 0x1aac60 | none |
| 2 neutral | inside `Player_move` (0x1a8094, or 0x1a7ca8 followed by 0x1a7cb8) | none | **`Player_castSkill` 0x1a7048** (abilities of record kind 7, cast straight from neutral) |
| 3 staggered | 0x1ab2ac | none | none |
| 4 dead | 0x1ab4e4, only while a per-slot counter is above 1 | none | 0x1ab3cc, 0x1ab410: midpoint of the hands for a blood decal (two `g_randSeed` draws are made whatever the position is) |
| 5 casting | 0x1ab584, then `Player_move` 0x1ab5a4 / 0x1ab5c0 | `Player_castSkill` 0x1ab7dc; 0x1ab880, 0x1ab8c4 (hand midpoint; use not read to the end) | none |
| 8 blocking | 0x1a6150 | 0x1a6338, 0x1a637c (a random point between the hands; the two `g_randSeed` draws that follow are made whatever the positions are; use not read to the end) | none |
| 6, 9–0xe | first call of the case | none | none |
| every state, at the common tail | — | **`Player_updateCast`** (0x1a3fe8, 0x1a402c) while the record's hit points are above 0. Two paths return from inside the switch and skip it (one in state 10, one in state 0xd) | — |

What the positions are used for: `Player_castSkill` (0x1a42b8) takes the midpoint of
attach points 0 and 1, clamps its height to at most 58 above the feet and passes it to the
skill's cast function; the thrown release passes attach point 0 to the projectile
constructor and aims from it; `Player_updateCast` passes the midpoint to every attached
spell each tick. All shared state. `Player_meleeHit` does not use the skeleton (no query
call in it).

Why no machine-dependent value was found:

1. In every state but 2 and 4 the step comes first, so the first query of the tick is a
   fresh build on every machine, and later queries of the same tick reuse it on every
   machine.
2. `Player_updateCast` runs at the tail of `Player_run` on every tick of a living
   player (two return paths in states 10 and 0xd excepted). It runs after the step and
   after `Player_move`'s direct weight writes. So when the tick ends, a pose built by the
   simulation from the final tracks of that tick is attached on every machine. A machine that draws the player re-stamps that buffer and builds
   nothing. The owner's machine, which never draws its real player, has the same pose
   attached, or — if the unstamped buffer was taken — builds an equal one at the next
   query, because:
3. between that query and the neutral-state `Player_castSkill` of the next tick no call
   was found that changes the pose at once. What runs in between: other objects
   (`Player_takeDamage`: `anim_startBlendInOut` only), and the head of `Player_run`
   (`Player_processDamage`: `anim_start` / `anim_startBlendInOut` only). Those add tracks
   at weight 0.
4. The exception to 3 is a full state: with 8 live tracks `anim_start` replaces the top
   one. The stale pose is then returned on every machine that still holds the buffer and
   a fresh one where it was taken — and it is the non-drawing owner whose buffer can be
   taken. Eight live tracks need eight starts within the six ticks a 0.1 s blend lasts
   (tracks with flag 2 remove the ones under them when blended in). **Not excluded; not
   an every-run event.**
5. The early return for a player under cutscene control (inert byte set, states 0 / 1:
   step, return at 0x1a55d0 / 0x1a55e8) skips `Player_updateCast`. Then drawing does build
   the pose. `cut_end` calls `anim_dropNonPersistent` on the actors after the objects have
   run. A query before the player's next step would see the difference; in states 0 and 1
   the step comes first, and in state 2 the only query before the step needs an ability
   press on that exact tick. **Narrow, not excluded.**

The prediction copy has its own state and its own buffers (`AnimState_copy`); its queries
only change which pool buffers are free on its owner's machine.

Side observation, not part of this lead: G22 (the Cyclone animation started twice on the
real player on every machine but the owner's) changes the tracks themselves per machine,
and through them every skeleton position and the root motion of that player while both
tracks blend in. It should be ranked on its own.

### 4.2 Horsemen (the knights), Zek

Neither run function calls a query (no call site in `Horsemen_run` 0x27236c or `Zek_run`
0x2c2440; the two Horsemen sites 0x271a4c and 0x27224c are draw code). Shared code they
reach:

| Query | Runs | Feeds | Verdict |
|---|---|---|---|
| weapon dropped at death: `Horsemen_setState` case 0x14 calls the weapon holder's slot 11 for parts 1 and 2 (0x273278…), `Zek_setState` case 0x14 for part 1; that is `creature_dropHeldPartAsProp` 0x117d30, query at 0x117e10 | from `Creature_processDamage` (slot 27 call with 0x14), i.e. **before** the step of that tick | start position of a `PhProp` — shared state through section 5 | the query comes before the `anim_start` of the death animation in the same case, and `Creature_filterState` 0x10a9c0 touches no track. Nothing else changes the knight's tracks between the end of the previous tick and this point. Draw-built and fresh pose are equal. **No difference found** |
| `Creature_processDamage` 0x111060, 0x1110b0 | before the step | particles for creatures with flag 0x20000 | presentation |
| `fx_shatterToLooseIce` 0x1fb240 (1 in 8 on the death of a chilled creature) | before the step, before the set-state | start positions of `LooseIceChunk` props (a `PhProp`) | shared through section 5; no track change before it in the tick. **No difference found** |
| `fx_disintegrateModel` 0x1f4340 | before the step | callee list holds particle and sample-point helpers only | presentation (Inferred from the callee list) |

A knight hit while its attack cooldown runs is sent to state 0x10 by `Creature_filterState`,
and `Horsemen_setState` cases 1, 3 and 0x10 call `anim_syncToSimFrame`: a real track change
before the step. What queries the knight's skeleton between that and the step of the same
tick is `Creature_run` handing the body centre (not a joint) to attached spells, and
status-effect particles. No shared-state query was found in that window.

### 4.3 Skelight

`Skelight_setState` case 0x14 (reached from the knight's death, K8, and from its own
damage processing) hides the object, loops over its sample points (0x2a93f4) and hands
each to `fx_spawn` with id 2, then queues the delete. `Skelight_shatter` 0x2a946c only
clears a static word. Particles only: **presentation**. `SkillSummonSkeleton_cast`
(0x2e19e8, 0x2e1cfc) was already read as particles only (ledger, "Ruled out").

### 4.4 Weapon holders

`creature_drawHeldPart` 0x117f08 (slots 18–20, two queries per part) is draw code.
`creature_dropHeldPartAsProp` 0x117d30 (slot 11) is the only simulation-side query and is
covered in 4.2. The per-frame update (slots 21 / 22) reaches `fx_modelStatusEffects`
(0x1f6da4), presentation (rescan section 6).

### 4.5 Buffer exhaustion in the arena

A drawn, stepping model needs a new buffer every picture and each stays reserved for the
current and three earlier pictures (stamp test at 0x16edb8–0x16edc0), so about 25 distinct
animation states drawn per picture use up the 100 buffers. Several draw passes of one model
share one buffer (the later `anim_emitPose` calls find it attached). The arena fight has
up to four knights, their skeletons (one per summoning knight), two to four players and
later Zek: about a dozen. **Not reached** (Inferred from the object count; a memory
snapshot of the list at 0x7b8344 would settle it).

## 5. Correction to R1: a debris prop's start position is shared state

R1 treated the start position of debris (dropped weapons, shed parts, shattered bones,
ice chunks) as presentation because debris props are not solid and sit in the grid that
box queries do not see. **Observed** in `PhProp_run` (0x155fcc), which is slot 4 of `PhProp` and
`LooseIceChunk` and is called by `GutChunk_run` (0x1edb18):

- when the prop has come to rest (its timer at +0x10e has run out and all six velocity
  components are under 0.2), or the timer is below −220, it creates its replacement — a
  resting `Prop` (`Prop_ctorRes` 0x153c88 or `Prop_ctorNamed` 0x153ac0) or an `ItemProp` —
  and deletes itself;
- both `Prop` constructors call `GameObject_ctor`, which draws one value from
  `g_randSeed`;
- a prop whose byte +0x23a is 1 also creates a `StaticFire` (0x2c5240) the first time it
  is near the ground with every velocity component under 0.8: another constructor.

So the tick on which a piece of debris comes to rest is a tick on which the shared seed
advances. The sync hash is the seed plus the players' positions, so two machines on which
the same piece settles on different ticks disagree for every tick in between and the
out-of-sync test fires on the first of them. Where the piece starts decides when it
settles, and it starts at a joint position.

This widens the set of queries that matter to every debris-creating function:
`creature_dropHeldPartAsProp`, `Creature_spawnPartProp`, `Clockwork_shedParts`,
`Skeleton_shatter`, `Orc_severPart`, `WoodElfSoldier_dropWeaponProps`, `Droid_run`,
`LavaMonster_run`, `fx_shatterToLooseIce`, `GutChunk_ctorFromProp`.

## 6. Every query site

236 call sites of the six query functions in 132 functions (`model_getAttachPoint` 117,
`model_getSamplePoint` 88, `PhProp_ctor2` 14, `model_getAttachMatrix` 9,
`model_getAttachWorldMatrix` 5, `model_getAttachLocal` 3), plus one more route into
`anim_getJointMatrix` (`model_evalFacingPoints`, from `model_draw`; it only acts on a
model table no file on the disc has). Classified with `tools/drawsim.py` roots and by
reading:

| Class | Sites | Functions | How established |
|---|---|---|---|
| draw code only | 24 | 18 | `drawsim` category P, or reached only through a draw slot (`creature_drawHeldPart`) |
| not reached from any root | 8 | 8 | no caller found (`Creature_spawnPartProp`, `Cyclops_dropClub`: dead code) or callers not resolved (`fx_spawnIceChunks`, four `fx_` emitters, 0x1fade0) |
| simulation, function calls only effect helpers | 76 | 48 | callee list holds no allocation, constructor, damage or world-query call; **Inferred presentation** — except `Player_updateCast`, which is shared through a virtual call (4.1), so this column over-trusts virtual calls |
| simulation, function also creates objects or deals damage | 128 | 58 | needs reading site by site |

Read site by site in this pass: all of `Player_run`, `Player_castSkill`,
`Player_updateCast`, `Creature_processDamage`, `creature_dropHeldPartAsProp`,
`Horsemen_setState`, `Zek_setState` (death case), `Skelight_setState`. **The remaining
functions of the last row were not read here** (list in section 9); `docs/monsters.md`
1.3 states that monster projectiles are spawned from attach points inside the state
switch, which is after the step.

Two mechanical checks over all simulation-side sites (address order inside a function, so
they over-report rather than under-report):

- In every function that contains its own animation step (`Creature_stepAnim`,
  `Player_animStep`, `Player_move`, `anim_advance`), 96 query sites lie after the first
  step and two before it: `JumpGate_run` 0x27cc50 and `Savepoint_run` 0x28d020, props that
  advance their own animation.
- In none of those functions does a call to `anim_push`, `anim_pushWithWeights`,
  `anim_pushChained`, `anim_clear`, `anim_syncToSimFrame`, `anim_stop`,
  `anim_dropNonPersistent` or `anim_randomizeTopTime` lie between a step and a later query
  site.

The other 78 functions with query sites contain no step: helpers, spell code, set-state and
drop functions. For those the caller decides. The death cases of the set-state functions
that create debris were read for the order of track change and query:

| Function, case 0x14 | Order | Track call before the debris query |
|---|---|---|
| `Horsemen_setState` 0x272f4c | drop parts 1 and 2, then `anim_start` | none |
| `Zek_setState` 0x2c382c | drop part 1, then `anim_start` | none |
| `Clockwork_setState` 0x24f90c | `Clockwork_shedParts` × 8, then `anim_start` | none |
| `Orc_setState` 0x2a323c | drop parts, `Orc_severPart`, then `anim_start` | none |
| `Skeleton_setState` 0x2a7768 | drop parts, `Skeleton_shatter`; no track call | none |
| `WoodElfSoldier_setState` 0x2bdb24 | `WoodElfSoldier_dropWeaponProps`, then `anim_start` | none |
| `Mummy_setState` 0x29a6f4 | `anim_start`, then drop part 1 | `anim_start` only: weight 0, no pose change unless the state is full |

So the pattern R1 feared for debris — full-weight change, then query, in one set-state —
does not occur in the death cases; the full-weight calls of those functions (`anim_push`,
`anim_syncToSimFrame`) sit in other cases.

Sites where the pattern of section 3 exists or cannot be excluded:

| Site | Why | State |
|---|---|---|
| debris dropped at death by any class, with a full track list (8 live tracks) | the `anim_start` that precedes or follows then replaces the top track at once | not excluded; needs eight starts within a blend time |
| a creature hit while its attack cooldown runs: `Creature_filterState` turns the reaction into state 0x10, whose set-state calls `anim_syncToSimFrame` before the step of that tick | every query on that creature between there and its step sees old track times on a machine that drew it | the queries found in that window are effect code and spells handed the body centre; **no shared-state query found, not every spell read** |
| `Soul_setState` (0x2ab0c0, 0x2ab0fc), `Skelight_ctor`, `Soul_ctor`, `Savepoint_run` from R1's list | query after a track change in one function | callee lists show effect helpers only (Inferred presentation); not read line by line |
| `Player_castSkill` from neutral with a full track list | 4.1 item 4 | not excluded |
| any creature that is not stepping (inactive, frozen) and is damaged | the pose a drawing machine holds can be many ticks old; any track change since then shows | not traced |

## 7. Executed demonstration

`python3 -I -B tools/posecache_test.py` — 38 checks, all passing at the time of writing;
prints `SKIP` and exits 0 without the executable.

What runs: the game's own `anim_init`, `anim_push`, `anim_clear`, `anim_syncToSimFrame`,
`anim_advance`, `animtrack_decode`, `anim_buildPose`, `anim_getJointMatrix`,
`anim_emitPose`, `anim_releaseCaches` and `model_getAttachPoint`, under
`tools/ee_emu.py`, on animation states the test builds. The two clips are synthetic
(three joints, written in the documented `.anm` layout). **The vector unit is not
executed by the interpreter.** `anim_buildPose` contains nine COP2 instructions and two
calls into the 77-instruction VU0 program at 0x3e5c50; the test reads that program's
words from the executable and interprets them with a small model that knows only the forms
the program uses, with the interpreter's FPU arithmetic standing in for the vector unit's.
Check a5 compares the result with the joint position worked out by hand from the clip
definition (agreement to the 1/64-unit step of the output), so the model is right to that
precision; its last bits are not established. Every other comparison is exact equality
between two runs of the same arithmetic, or a difference of several units.

"Drawn machine" and "undrawn machine" are two runs that differ only in whether
`anim_emitPose` was called. Nothing here shows that a sequence occurs in a real game.

| Id | Claim | Result |
|---|---|---|
| a1–a4 | a query after a step is a fresh build; a second query builds nothing | after `anim_advance` the pointer is 0; the first query calls `anim_buildPose` once and leaves the buffer attached, **unstamped**, owned, at the recent end of the list; the second query makes no call and returns the same matrix |
| a5 | the chain decoder → blend → VU0 model is right | joint 2 at time 30: (10.203, 11.703, 45.000) executed, (10.205, 11.714, 45.000) by hand |
| a6 | the decoder slot's history does not show | the same track time reached by 30 steps or written directly gives bit-identical matrices |
| b1–b2 | draw, then `anim_clear` + `anim_push` of another clip, then query with no step | the drawn machine makes no build and returns the matrix from before the change; the undrawn machine builds. Joint matrix differs by up to 22.19; attach point (984.9, 1994.0, 75.0) against (1011.3, 1987.3, 69.0) |
| b4–b5 | the same with `anim_syncToSimFrame` | matrix differs by up to 8.22; attach point (984.9, 1994.0, 75.0) against (981.7, 2006.3, 75.0) |
| b3, b6 | control: a step between the change and the query | both machines equal |
| b7 | a pose attached by a simulation query is what the draw uses | `anim_emitPose` sends and stamps that buffer and builds nothing |
| c1 | all 100 buffers stamped recent | the query builds into 0x7b89c0; values equal to a pooled build |
| c2–c3 | a second state queried in the same tick | it takes the static buffer; **the first state's pointer is zeroed before the buffer is overwritten**, and a later query on the first state rebuilds and returns its own pose. The static buffer never serves one object another's pose |
| c4 | drawing and the static buffer | `anim_emitPose` detaches it and, with nothing free, sends the default pose |
| c5 | what exhaustion changes | query X, change X's tracks, query Y, query X: with buffers free X gets the old pose (no build); with the pool exhausted Y took the static buffer and X is rebuilt. Matrix differs by 22.19 |
| c6–c7 | life of an undrawn pose built by a query | taken by the 100th later build with no buffer stamped recent, by the 40th with 60 stamped recent: 100 minus the number of recently drawn buffers |
| c8 | the same pose on a machine that draws the object | still attached after 150 pictures and 150 other builds |

So for 1(c) of the task: the second build does overwrite the static buffer, but only after
detaching the first state from it; no state is left pointing at another object's pose.
What exhaustion does change is *which* queries are rebuilt, and with it the result of any
query that follows a track change (c5).

## 8. Patch proposal

Both variants are **untested on a running game**. Both were executed under the
interpreter (checks e0–e6, f0–f6); the original words were read from the executable and
are checked by the test (e0, f0).

Why not the two fixes R1 names. Rebuilding always by changing the branch alone leaves the
old buffer's owner field pointing at a state that no longer uses it (R1's objection,
correct). Detaching at the end of `anim_emitPose` is safe for the simulation but a model is
sent by more than one draw pass per picture (`model_draw`, `model_drawShadow` and four
more callers of `anim_emitPose`), and each pass would then build and reserve its own
buffer: two or three times the buffers per drawn model, exhaustion at about ten models
instead of 25, and the default pose drawn for the rest. The proposal below leaves the
draw side alone and makes the *query* stop trusting the cache.

### PC-A (proposed): inside the lockstep tick a query always detaches and rebuilds

The branch at 0x16f73c ("something is attached: use it") becomes a jump to a 12-word
routine. The routine: nothing attached → the original build; `g_excludeMask` (0x4039b8)
not 0x20000 → the original "use it" path; otherwise clear the buffer's owner and the
state's pointer, then the original build. `g_excludeMask` is 0x20000 from the start of a
tick (0x139f4c) to its end (0x13b1f0, where it becomes 0x200000 for prediction and
drawing; `net_predictLocalPlayer` sets 0x200000 as well, 0x131e38); its value in the file
is 0. Draw code, the prediction copy and offline play therefore keep the original
behaviour.

The routine is written over `Cyclops_dropClub` (0x257ab4–0x257b9f, 59 words). That
function is dead: no call, jump or branch anywhere in the code segment leads into it and
no word of any loaded segment holds an address inside it (check d0 scans all three
segments; `symbols/monsters2.tsv` already recorded "no caller and no data reference").

| Address | Original | New | Instruction |
|---|---|---|---|
| 0x0016f73c | 14400004 | 08095ead | `j 0x257ab4` (the delay slot 0x16f740 still saves the output pointer) |
| 0x00257ab4 | 27bdffb0 | 10400007 | `beqz v0, +7` — nothing attached: build |
| 0x00257ab8 | 24020001 | 3c030040 | `lui v1, 0x40` |
| 0x00257abc | ffb00030 | 8c6339b8 | `lw v1, 0x39b8(v1)` — `g_excludeMask` |
| 0x00257ac0 | 0080802d | 3c010002 | `lui at, 2` |
| 0x00257ac4 | ffb10038 | 14610005 | `bne v1, at, +5` — not the tick: use the attached pose |
| 0x00257ac8 | 0000882d | 00000000 | `nop` |
| 0x00257acc | 14a2000f | ac400610 | `sw zero, 0x610(v0)` — buffer owner |
| 0x00257ad0 | ffbf0040 | ae000000 | `sw zero, 0(s0)` — state pointer |
| 0x00257ad4 | 8e020024 | 0805bdd1 | `j 0x16f744` — the original build call |
| 0x00257ad8 | 8e0500e8 | 00000000 | `nop` |
| 0x00257adc | 0c05e554 | 0805bdd4 | `j 0x16f750` — the original "use it" path |
| 0x00257ae0 | 8c44000c | 00000000 | `nop` |

```
[Net test: skeleton queries rebuild inside the tick (pose cache, D34)]
patch=1,EE,0016F73C,word,08095EAD
patch=1,EE,00257AB4,word,10400007
patch=1,EE,00257AB8,word,3C030040
patch=1,EE,00257ABC,word,8C6339B8
patch=1,EE,00257AC0,word,3C010002
patch=1,EE,00257AC4,word,14610005
patch=1,EE,00257AC8,word,00000000
patch=1,EE,00257ACC,word,AC400610
patch=1,EE,00257AD0,word,AE000000
patch=1,EE,00257AD4,word,0805BDD1
patch=1,EE,00257AD8,word,00000000
patch=1,EE,00257ADC,word,0805BDD4
patch=1,EE,00257AE0,word,00000000
```

- **What it changes.** Every skeleton position read inside a tick is computed from the
  tracks as they are at that moment. It no longer depends on what was drawn, on how many
  pictures lay between two ticks, or on which buffers the least-recently-drawn rule handed
  out.
- **Executed** (e1–e6): drawn and undrawn machine return the same matrix and attach point
  for both track changes of section 7, equal to the unpatched fresh build; the draw-built
  buffer is left unowned and stamped, and keeps its contents; the draw before and the draw
  after a patched query each send an attached, stamped buffer (drawing still gets a pose);
  120 further builds recycle the pool with every owner field consistent; the exhaustion
  sequence c5 gives one result whether or not the pool is exhausted; five queries in a row
  build five times inside the tick, never in the draw phase, never with the mask at 0.
- **What could go wrong.**
  1. It changes results where the original is stale *identically* on every machine (query,
     track change, query, in one tick): the second query now sees the change. Debris and
     effect positions in those cases move. That is a rule change, small, but it means
     **patched and unpatched machines disagree there**.
  2. Cost. Every query inside the tick is a full pose build. Steady load is small (two per
     player per tick from `Player_updateCast`, a few per creature with a status effect),
     but effect bursts that sample many points in one call (`Creature_emitLinkParticles`:
     100 particles, two queries each; the disintegrate and vertex emitters) become 100–200
     builds in one tick. Expect a slow frame on those.
  3. A drawn model whose skeleton is also queried in the tick uses one buffer per picture
     even when it does not step (dead player, frozen creature); stepping models already do.
  4. `Creature_pickTarget` (0x10e044) and `Vehicle_collideObjects` (0x20e410) change the
     mask for the length of a box query; a skeleton query inside such a window would take
     the old path. None was found.
  5. If something outside this project's knowledge calls `Cyclops_dropClub`, it now runs
     the routine with a wrong register set. The scan found no route to it.
- **Who must apply it.** Every player (point 1).
- **What a result means.** If the arena desync disappears with PC-A on all machines, the
  pose cache was in the chain after all and section 4 missed a route. If it stays, D34 is
  closed for the arena.

### PC-B (alternative, not proposed): every query rebuilds, six words in place

No routine: 0x16f73c–0x16f750 are rewritten so that the owner of an attached buffer is
cleared with a branch-likely and the build is always called.

| Address | Original | New | Instruction |
|---|---|---|---|
| 0x0016f73c | 14400004 | 54400001 | `bnezl v0, +1` |
| 0x0016f740 | 00c0882d | ac400610 | `sw zero, 0x610(v0)` (runs only when something is attached) |
| 0x0016f744 | 0c05bb50 | 00c0882d | `move s1, a2` |
| 0x0016f748 | 0000282d | 0c05bb50 | `jal anim_buildPose` |
| 0x0016f74c | 8e020000 | 0000282d | `move a1, zero` |
| 0x0016f750 | 0040402d | 8e080000 | `lw t0, 0(s0)` |

Executed with the same results (f1–f5). It is not proposed because it also applies to the
queries draw code makes (`creature_drawHeldPart`, `Player_draw`, `Horsemen_draw` and 15
more draw functions), to the prediction copy and to offline play (f6): a model whose draw
function queries between two draw passes then reserves two buffers per picture, which
halves the number of models that can be drawn before the default pose appears.

## 9. Not done, not determined

- **Nothing was run on a console or a full emulator.** (A full emulator exists in the
  project now, `docs/issues/live-rig.md`; nothing of this document was run on it, and it
  has one machine.) The two-machine observation that
  would confirm or close this: on both machines, at the branch 0x16f73c, when the pointer
  is non-zero and `g_excludeMask` is 0x20000, build a second pose into scratch memory and
  compare with the attached one; log tick, state address and return address on a
  mismatch. A mismatch on one machine only, followed by an out-of-sync message, confirms
  a route. With stock tools: apply PC-A on every machine and see whether the arena
  desync changes (protocol in `docs/VALIDATION.md`).
- Of the 58 simulation-side functions that both query the skeleton and create objects or
  deal damage, these were read site by site: `Player_run`, `Player_castSkill`,
  `Creature_processDamage`, `creature_dropHeldPartAsProp`. The others were covered only
  by the two mechanical checks of section 6 (monster run functions: every site after the
  step, no full-weight track call between) or not at all (spell code without a step of its
  own: `SpellCharge`, `SpellCyclone`, `SpellBash`, `SpellShieldBash`, `SpellRoar`,
  `SpellBattleCry`, `SpellWizardBeam`, `SpellPlanarWind`, `SpellShadowStep`,
  `SpellUndeadShield`, `SkillFireAxe`, `SkillColdAxe`, `SkillStrongStance`,
  `SpellHarmTouch`, `SkillRiposte`, `SpellHolyShield`, `HateBeam_run`, `MissileWeapon`,
  the chest and container run functions). For player spells the query runs from
  `Player_updateCast`'s slot-17 call, after the step and after its own query.
- What each of those sites uses the position for was not tabulated site by site; the
  counts of section 6 are by callee list.
- Which skills use the cast position they are handed (`docs/spec/skills-*.md` say so per
  skill; not collated).
- The 76 sites classed as presentation by callee list were not read; a virtual call can
  hide a shared use, as it does in `Player_updateCast`.
- Creatures that do not step (inactive, frozen) and are damaged; whether one can be drawn
  on one machine while inactive.
- G22 was not followed up.
- The last bits of the VU0 arithmetic.

## 10. Proposed ledger rows

| ID | Claim | Kind | Evidence |
|---|---|---|---|
| D34 (answer) | For Player, Horsemen, Skelight, Zek and the weapon holders no sequence was found in which a draw-built or left-over pose differs from a fresh one at a query that feeds shared state. Players: `Player_updateCast` queries at the tail of `Player_run` on every tick of a living player, after the step and every track change, so a simulation-built pose is attached on every machine and the cast position of the next tick reads it or an equal one. Knights and Zek: the weapon drop at death reads the skeleton before the step but before any track change of the tick. Skelight: particles. Exhaustion needs about 25 drawn models. The lead is not supported as the every-run arena cause | Inferred from Observed steps | docs/issues/pose-cache.md sections 3, 4 |
| D39 | The start position of every debris prop is shared state: a `PhProp` that comes to rest constructs a resting `Prop`, and the constructor draws `g_randSeed`, so the settling tick moves the shared seed. Debris starts at a joint position | Observed | `PhProp_run` 0x155fcc (rest test and constructor calls), `Prop_ctorRes` 0x153c88, `Prop_ctorNamed` 0x153ac0, `GameObject_ctor` 0x14cb10 |
| D40 | A pose built by a simulation query is not stamped; on a machine that does not draw the object it is taken by the (100 − recently drawn)th later build, on a machine that draws it it stays for ever. With the pool exhausted, simulation queries share one static buffer, each taking it from the previous owner, so a query that follows a track change is stale on a machine with free buffers and fresh on an exhausted one | Executed in isolation | checks a3, c1–c8 |
| X5 | The pose cache behaves as D34 says when executed: draw, track change without a step, query returns the pose from before the change on the machine that drew and the new one on the machine that did not (joint matrix differs by 22 units for a clip change, 8 for `anim_syncToSimFrame`); with a step in between both agree. Patch PC-A removes the difference and drawing still gets a pose | Executed in isolation (VU0 program interpreted by a model) | `tools/posecache_test.py`, 38 checks |

## 11. Corrections to earlier documents (reported, not edited)

- **rescan.md R1, "Debris props are non-solid … so that is presentation, apart from pool
  occupancy".** Wrong: section 5.
- **rescan.md R1, "`Player_run` uses only `anim_start` / `anim_startBlendInOut`".**
  `Player_move`, called from it, writes track weights directly after stepping
  (0x1b498c–0x1b499c, 0x1b4bb8–0x1b4bc4).
- **rescan.md R1, the cast position "is read … before that tick's step … from a possibly
  draw-built pose".** Before the step, yes (0x1a7048); but the attached pose is the one
  `Player_updateCast` built at the end of the previous tick, on every machine, not a
  draw-built one.
- **rescan.md R1, the ten set-state functions.** In the death cases that create debris the
  query comes before the track call, or after an `anim_start` only (section 6).
- **symbols note of `anim_start` ("the first track of an empty state starts at full
  weight").** It starts at weight 0 with a rate of 1 per tick (0x16cfe0); `docs/engine.md`
  has it right.
- **engine.md P11.** As rescan says; in addition the stamp is written by `anim_emitPose`
  only, which is what makes simulation-built poses short-lived on machines that do not
  draw the object.
