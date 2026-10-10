# The pose cache (D34 / rescan R1): can a draw-built skeleton pose reach shared state?

Follow-up to `docs/issues/rescan.md` R1 and ledger row D34. That finding described the
mechanism and left open whether it reaches a position that matters. This document traces
it for the Drundar arena classes first, then for everything else as far as the work got.

Evidence labels: **Observed** (read at the address given), **Executed** (the game's own
instructions run by `tools/posecache_test.py` on state the test built; see section 7 for
what that does and does not show), **Inferred**, **Unknown**. Nothing here was seen on a
running game. The patches in section 8 are **untested on a running game**. `FINDINGS.md`
and `patches/` were not edited.

**This revision is a working draft: sections 7 (executed demonstration) and 8 (patch) are
filled in as that work is done; section 9 lists what is not done.**

## 1. Verdict in short

| Question | Answer | Kind |
|---|---|---|
| Is the mechanism real? | Yes: a simulation query returns whatever pose is attached, and drawing attaches poses | Observed (section 2) |
| Does a skeleton position reach shared state? | Yes, in more places than R1 allowed. Beyond the obvious ones (cast position, thrown-weapon release, monster projectile origins) every debris prop does: a `PhProp` that comes to rest builds a resting `Prop`, whose constructor draws `g_randSeed`. The tick on which it comes to rest depends on where it started, and it starts at a joint. R1 called debris "presentation"; that is wrong | Observed (section 5) |
| Can the pose differ between machines at such a query? | Only in this pattern: the pose was built by drawing (or by an earlier query), the tracks were then changed by a call that does not detach, and the query follows with no animation step between (section 3) | Observed rules, Inferred completeness |
| Does that pattern occur for Player, Horsemen, Skelight, Zek or the weapon holders in the arena fight? | **Not found.** Players: `Player_updateCast` queries the skeleton at the end of every `Player_run`, after the step and after every track change of the tick, so a pose built by the simulation is attached on every machine when the tick ends and drawing never builds one for a real player. Knights and Zek: the one shared-state query (weapons dropped at death) runs before the step but before any track change of that tick. Skelight: particles only. Buffer exhaustion needs about 25 distinct animated models drawn; the fight has about a dozen | Observed steps; "not found" is Inferred |
| So is D34 the every-run arena desync? | **No route found; the lead is not supported for the arena.** It stays a real hazard for other classes (section 6) and under buffer exhaustion | Inferred |
| Fix | Section 8: make the simulation query rebuild instead of trusting the cache | proposal |

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
| `Player_updateCast` reads attach points 0 and 1 unconditionally, every tick, at the end of `Player_run`, and hands their midpoint to the player's slot 17, which passes it to every attached spell | 0x1a3f70 (calls 0x1a3fe8, 0x1a402c) | Observed |
| The VU0 program that turns the blended joints into matrices is straight-line code with no state of its own between calls except the parent matrices it stores per depth | 0x3e5c50, 77 instructions | Observed |

Calls that change the pose at once and do not detach (**Observed**): `anim_push`,
`anim_pushWithWeights`, `anim_pushChained`, `anim_clear`, `anim_syncToSimFrame`,
`anim_randomizeTopTime`, `anim_dropNonPersistent`, `anim_stop` with no blend time,
`anim_start` / `anim_startBlendInOut` on an empty or full state, and direct stores into
track fields (`Player_move` above; `SpellRaiseArmy_raiseInRing` 0x313e54 writes a track
time; `cut_advance` nudges track times, D8). Calls that detach: `anim_advance`,
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
| 0 ranged | 0x1a8198 | `Player_castSkill` 0x1a837c, 0x1a9174; thrown release 0x1a83ec (spawn position and aim of the projectile, then two `g_randSeed` draws); 0x1a8a18 | none |
| 1 melee | 0x1aa170 | `Player_castSkill` 0x1aac60 | none |
| 2 neutral | inside `Player_move` (0x1a8094, or 0x1a7ca8 followed by 0x1a7cb8) | none | **`Player_castSkill` 0x1a7048** (abilities of record kind 7, cast straight from neutral) |
| 3 staggered | 0x1ab2ac | none | none |
| 4 dead | 0x1ab4e4, only while a per-slot counter is above 1 | none | 0x1ab3cc, 0x1ab410: midpoint of the hands for a blood decal (two `g_randSeed` draws are made whatever the position is) |
| 5 casting | 0x1ab584 | `Player_castSkill` 0x1ab7dc; 0x1ab880, 0x1ab8c4 | none |
| 8 blocking | 0x1a6150 | 0x1a6338, 0x1a637c | none |
| 6, 9–0xe | first call of the case | none | none |
| every state | — | **`Player_updateCast` at the end** (0x1a3fe8, 0x1a402c) | — |

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
2. `Player_updateCast` runs at the end of every `Player_run` that reaches the switch. It
   runs after the step and after `Player_move`'s direct weight writes. So when the tick
   ends, a pose built by the simulation from the final tracks of that tick is attached on
   every machine. A machine that draws the player re-stamps that buffer and builds
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
box queries do not see. **Observed** in `PhProp_run` (0x155fcc), which every `PhProp`,
`LooseIceChunk` and (through its own run) `GutChunk` executes:

- when the prop has come to rest (its timer at +0x10e has run out and all six velocity
  components are under 0.2), or the timer is below −220, it creates its replacement — a
  resting `Prop` (`Prop_ctorRes` 0x153c88 or `Prop_ctorNamed` 0x153ac0) or an `ItemProp` —
  and deletes itself;
- both `Prop` constructors call `GameObject_ctor`, which draws one value from
  `g_randSeed`;
- a prop launched with the burning flag (+0x23a = 1) also creates a `StaticFire` when it
  first slows down (0x2c5240), another constructor.

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

Sites where the pattern of section 3 exists or cannot be excluded:

| Site | Why | State |
|---|---|---|
| the set-state functions R1 lists (`Clockwork_setState`, `Mummy_setState`, `Orc_setState`, `Soul_setState`, `WoodElfSoldier_setState`; `Skeleton_setState` only if a track change precedes the shatter, which R1 says it does not) | a set-state called from `Creature_processDamage` runs before the step; where it changes tracks at full weight and then creates debris at a joint, a machine that drew the creature starts the debris at the old pose and one that did not at the new pose, and section 5 turns that into a seed difference | **open: each case needs the order of track change and query read**; none of these classes is in the arena |
| `Player_castSkill` from neutral with a full track list | 4.1 item 4 | not excluded |
| any creature that is not stepping (inactive, frozen) and is damaged | the pose a drawing machine holds can be many ticks old; any track change since then shows | not traced |

## 7. Executed demonstration

*Pending in this revision.*

## 8. Patch proposal

*Pending in this revision.*

## 9. Not done, not determined

- The 58 simulation-side functions that both query the skeleton and create objects or deal
  damage were not all read: the monster run functions (Amphian, Bubo, Cazic, Clockwork,
  CloudGiant, Cyclops, FatCyclops, MaleDarkElf, RedDragon, GnawSpawn, Goblin, Gremlin,
  Innoruuk, IronGuardian, Droid, LavaMonster, Minion, SpiderQueen, VampireLord, Wraith,
  Soul, UndeadKnight), the chest and container run functions, `MissileWeapon`, and the
  player spells (`SpellCharge`, `SpellCyclone`, `SpellBash`, `SpellShieldBash`,
  `SpellRoar`, `SpellBattleCry`, `SpellWizardBeam`, `SpellPlanarWind`,
  `SpellShadowStep`, `SpellUndeadShield`, `SkillFireAxe`, `SkillColdAxe`,
  `SkillStrongStance`, `SpellHarmTouch`, `SkillRiposte`, `SpellHolyShield`). For player
  spells the query runs from `Player_updateCast`, after the step; for monsters the shape of
  `docs/monsters.md` 1.3 puts it after the step. Neither was re-checked per function.
- Which skills use the cast position they are handed (`docs/spec/skills-*.md` say per
  skill; not collated here).
- The order of track change and debris query in each set-state function of section 6.
- Non-stepping creatures.
- Whether `animtrack_decode` gives the same joint values whatever the history of its
  decoder slot (the format description says decoding restarts from the initial pose when
  time goes back, and velocities are applied per key, which makes it a function of time
  only; **Inferred**, the test compares one case).
