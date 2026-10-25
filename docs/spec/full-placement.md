# The round-5 Full-fight placement with AntQueen and Skeleton: how far the original gets

US `SLUS_209.73` v2.00. Prose of `tools/probe_full_placement.py` (tests:
`tools/test_probe_full_placement.py`). Written 2026-10-21, after this round executed
`Skeleton_isEnemy`, every AntQueen state, `AntQueen_pickFlyDest`, `Soul_takeDamage`, the
two takeDamage wrappers, six destructors and potion 1's fire entry
(`docs/spec/combat-ctors-2.md`, `docs/spec/antqueen-run.md`, `docs/spec/fire-touch.md`).

**Round 4 (2026-10-21, `t3/research-combat-ctors-4`): §7.** It supersedes §6.4 and §6.5.

**Round 3 (2026-10-21, `t3/research-combat-ctors-3`): §6.** It supersedes §3.3 and §4.
Every item of §4's list 1–8 is executed now. On this placement the three classes run the
default Full fight to their deaths without meeting an unexecuted body.

Evidence words as in `CONTRIBUTING.md`. This is a **probe**, not a comparison: the
original's own code decides the path, and the probe only records which bodies that path
reaches. Everything it says about the original is *Executed* in `tools/ee_emu.py`; the
world around it is *Authored* (below). Nothing here ran on a console, in PCSX2 or on the
live rig.

## 1. Why a probe

The native client (`open-champions` `codex/combat-ctors`, report
`work/loop-combat-ctors-r1-report.md`) measured, on the round-5 Full placement, that the
Skeleton's first target scan calls `Skeleton_isEnemy` at ready tick 32 and the AntQueen
enters state 3 at ready tick 33 — both refusals, so neither creature could stay in the
default Full fight. Those two bodies are executed now. The question is where the fight
stops next. A port can only answer that by porting first; the probe answers it from the
original.

## 2. Method

One class per run (`--class antqueen|skeleton|soul`):

- The world is `tools/difftest_combat_ctors.py`'s (class definitions, the game's own
  virtual tables, the skelcom block, the level name), with every stubbed answer replaced
  by a deterministic one.
- The creature is built by its original constructor and its original run function is
  called once per tick, its switch included (the round-5/ctors range-test patch is not
  applied).
- A callee runs **for real** when some difftest of this tree has executed its body
  (`executed_bodies()`: the `MODELLED` / `EXECUTED` / `CLASS_BODIES` tables of the
  `ref_*.py` modules, `ref_combat_full.FULL_MODELLED`, `ref_combat_runtime.EMPTY_BODIES`,
  `damage_apply`), or when it is C library or C++ type-info runtime.
- Everything else is a named stub, classified as
  - **service**: what the composed runtimes answer from fixtures or treat as bookkeeping
    and presentation (`SERVICES`: animation, handles, lists, the pool, terrain, sound,
    particles, the camera test `isNearCameraFocus480`, `obj_delete`);
  - **recorded**: not executed, but recorded and answered by the native World as it does
    for Gnaw (`RECORDED`: weapon holder slots 1 and 21, `Creature_init`);
  - **unexecuted**: game logic no difftest has run. The probe stops at the first one
    (`--all` answers it with 0 and goes on, listing each with the tick it first appears).
- The run switch is a stop too when it dispatches into a state whose arm no difftest
  executed (`RUN_STATES_EXECUTED`: every AntQueen state; Skeleton 0 and 1; no Soul arm —
  round 5 executed only the Soul's demon check inside states 0 and 0x18).
- Every executed pc is mapped to its function (`ghidra_funcs.tsv`), so a body entered by a
  plain jump, which the interpreter does not record as a call, is still caught. None was.

### 2.1 The world (Authored)

| Item | Value | Source |
|---|---|---|
| Player 0 | (0, 0, 0), team 0, object flags 0x60, the Player table `0x511308`, idle | native `full_setup` |
| Skelights | (80, 0) facing 0x8000 and (-40, 0) facing 0, team 0xff, table `0x5174b0` | native `full_setup` |
| AntQueen, Skeleton, Soul | (0, 140), (70, 140), (-70, 140), facing 0xc000, 120 hit points | native 9c224e7 `place(4..6)` |
| `--placement native` | the Soul at (-60, 100) instead | native ed062c3 |
| Other actors | static stand-ins with their own class's table; only the probed class runs | — |
| Ground | flat, dry, z = 0, no walls, rays miss | `ref_combat_runtime.FlatTerrain` |
| Animation | every clip 20 ticks, then flag 0x80; no root motion, no events | `ref_combat_runtime.AnimTimeline` |
| Pool | refuses every block (no effect objects; so no `GutChunk_ctor`) | — |
| `g_simFrame` `0x44fdcc` | starts at 0; native ready tick k runs frame k − 1 | native `SessionAdapter::ready_tick` |
| Serial counter `0x4f85c4` | `--serial s` (default 0); AntQueen gets s, Skeleton s + 1, Soul s + 2 | native placement order |
| Shared seed `0x404464` | starts at 0; `GameObject_ctor` makes its one draw for `+0x44` | `ref_skills_a` |
| `--hit-every N` | before the run, the player hits through the creature's own slot 2 (10.0, flags 1) | stand-in for the attacking player |

The serial matters: `Creature_pickTarget` scans when `(g_simFrame XOR s8(+0x230)) & 0x1f`
is 0, so the first enemy test comes on frame `serial & 0x1f`. With serials 30 and 31 the
Skeleton's first scan is frame 31 = ready tick 32, the native's figure.

## 3. Results

`python3 tools/probe_full_placement.py --ticks 600 [--all] [--hit-every 25] --class …`
(log: `local/probe/full-placement.txt`, untracked).

### 3.1 The idle fight (no hits)

- **AntQueen: no unexecuted body in 3,000 ticks.** States (frame:state) 0:0, 1:1, 3:3,
  181:8 (take-off at creature clock 181, `+0x3d4` = 180 absolute), 209:9, then 8/9 every
  20 or 21 frames, 314:0x17 (`AntQueen_pickFlyDest`, executed), 442:0x18, 462:3, 569:6
  (bite), then 3/6 alternating. With serial 30 on the native placement she enters 3 on
  frame 30 and the same sequence follows, shifted.
- **Skeleton: stops at `Skeleton_run` state 3**, on the first sighting of the player:
  frame 123 (ready tick 124) with serial 1 (the idle timer `+0xf4` = clock + 120 runs
  out first); frame 32 (ready tick 33) with serial 31. `Skeleton_isEnemy` now runs for
  real on every scan before that. In the same tick state 3 calls
  `creature_allyInLineOfFire` `0x10d5e8`, also unexecuted.
- **Soul: stops in its constructor** at `Creature_setCharm` `0x1189f0` (Observed only,
  `docs/spec/skills-35-68.md`; the native ports that prose). With `--all` the next stops
  are `Soul_run` state 0 (frame 0) and state 1 (frame 1): the native's Soul, which wanders
  in states 0 and 1 for the whole default fight, runs arms that are executed only up to
  the demon check.

### 3.2 The attacking player (`--hit-every 25`)

- **AntQueen: stops at `Skeleton_onNearbyEvent` `0x2a7688`** on the first hit (frame 24):
  `Creature_processDamage` → `world_notifyObjectsNear` calls slot 12 of every object in
  its box, and the Skeleton at (70, 140) is in it. AntQueen's own slot 12 is the empty
  `Creature_slot12` `0x11a290`. With `--all`: flinch 0x12 at 24 and 174, death (0x14) on
  frame 299 after twelve hits, and there `anim_findTrack` `0x170d88`,
  `loot_generateDrops`, `player_getSkillRank`, `player_giveExp`.
- **Skeleton: stops at its own `Skeleton_onNearbyEvent`** on the first hit (frame 24).
  With `--all`: state 3 at 25 (the hit gives it its target), `creature_allyInLineOfFire`,
  state 0x12 at 99, and at death (frame 299) state 0x14, `Skeleton_shatter` `0x2a7ef0`,
  WeaponShield slot 11, `creature_bossRank`, `loot_generateDrops`, `player_getSkillRank`,
  `player_giveExp`.
- **Soul:** a player's hit is not a Demon's, so `Soul_takeDamage` does nothing (executed);
  the stops are those of 3.1.

### 3.3 Answer

With this round's bodies, the AntQueen can stay in the default (idle) Full fight: on the
round-5 placement it runs through every state it reaches for at least 3,000 ticks without
meeting an unexecuted body. The Skeleton gets past `Skeleton_isEnemy` and stops at the
next one, its own run switch in state 3, on its first sighting of the player (ready tick
33 on the native's serial, 124 on serial 1). Once anything near a Skeleton is hit, the
first stop is `Skeleton_onNearbyEvent`.

## 4. What is still missing, ranked

By how early it stops the native Full fight (idle first, then attacked), then by size.

| # | Body | Address | Size | Reached |
|---|---|---|---|---|
| 1 | `Skeleton_run` switch past states 0, 1: state 3 (98), 8 (389, the bow release), 5 (55), 6 (48), 0x17 (17), 0x12 (13), 0x14 (12), 0x10 (11), 0x11 (7), 0x13 (6) | `0x2a6864` | 666 of 809 not executed | idle, first sighting |
| 2 | `creature_allyInLineOfFire` | `0x10d5e8` | — | idle, Skeleton state 3 |
| 3 | `Soul_run` arms of states 0 (23) and 1 (31) past the demon check; then 0x1b (498), 0x14/0x22 (234), 0x1d (139) | `0x2a9870` | 936 of 1062 not executed | idle, frame 0 (the native's slot-6 Soul) |
| 4 | `Creature_setCharm` | `0x1189f0` | — | Soul constructor (native uses the Observed body) |
| 5 | `Skeleton_onNearbyEvent` (slot 12) | `0x2a7688` | 49 | first hit on anything near a Skeleton |
| 6 | `GutChunk_ctor` (blood; not reached here because the probe's pool refuses blocks) | `0x201958` | — | first bleeding hit (native: tick 28) |
| 7 | The death path: `Skeleton_shatter` `0x2a7ef0`, WeaponShield slot 11, `creature_bossRank`, `loot_generateDrops`, `player_giveExp`, `player_getSkillRank`, `anim_findTrack` `0x170d88` | — | — | first kill |
| 8 | Weapon holder slots 2–4 (Skeleton elements, shared draws) | — | — | a Skeleton with an element (under 10 % of constructions; not on this placement) |
| 9 | `AntWave_ctor` `0x238654` and the AntWave object | — | — | AntQueen state 0x19, which nothing requests |
| 10 | The touch dispatch that decides how often a LooseFire's slot 6 runs, and a Frost Armor carrier's burn tick (recurses without end at chance ≥ 100) | — | — | potion 1 on a player (`docs/spec/fire-touch.md`) |

Sizes in instructions from the run switches' jump tables (`0x54bf00`, `0x54c2c0`,
`0x541b80` hold the arm addresses).

## 5. Limits

- One real class per run; the others are static stand-ins. A moving Skelight, a walking
  player or the other real class could change when things happen, not which bodies the
  first ones are. The Skeleton and the AntQueen never target each other (same team, and
  `Skeleton_isEnemy` returns 0 for a non-Skeleton).
- No root motion: a creature walks only by `Creature_moveBy` / `Creature_moveTo` speed.
- The pool refuses blocks, so effect objects (gut chunks, AntWaves) are never built; their
  constructors are listed from the native run and the class bodies instead.
- The probe's answers for `GameObject_ctor`, `Creature_setStats` and `balance_lookup` are
  fixtures; a seed-exact reproduction of the native's numbers is not claimed.

## 6. Round 3: after items 1–8 (2026-10-21)

### 6.1 What was executed

Every body listed here ran against a model on seeds 20973 and 7 with 0 mismatches. The
prose is in the documents named.

| §4 # | Bodies | Document |
|---|---|---|
| 1 | `Skeleton_run`, every state (808 of 809 instructions; the one left is dead) | `skeleton-run.md` §3 |
| 2 | `creature_allyInLineOfFire` (132 of 133), and under it `world_countLivingNonplayerCreaturesInBox` (60/60) and `creature_objInArcRange` (106/106); `Creature_leadTargetPoint` (54/54) | `skeleton-run.md` §4, §4a, §5 |
| 3 | `Soul_run`, every state 0–0x22 (1061 of 1062; the one left is dead) | `soul-run.md` |
| 4 | `Creature_setCharm` (25/25) | `soul-run.md` §4 |
| 5 | `Skeleton_onNearbyEvent` (49/49), `Skeleton_hasShield` (25/25) | `skeleton-run.md` §6 |
| 6 | Under `GutChunk_ctor`: `PhProp_ctor`, `Prop_ctorNamedLaunch`, `Prop_launch`, `PhProp_initPhysics` (668 of 668) | `gut-chunk.md` |
| 7 | `Skeleton_shatter`, WeaponShield slot 11, `creature_dropHeldPartAsProp`, `PhProp_ctor2`, `Gold_ctor2`; `loot_generateDrops`, `creature_bossRank`, `player_giveExp`, `player_getSkillRank` and `anim_findTrack`, which other difftests had already executed (see below) | `combat-death.md`, `gut-chunk.md` §7a–7b |
| 8 | Weapon1 and WeaponShield slots 1–17, the element setters, `creature_buildElementDamage`, `damageDesc_getElement` | `weapon-holder.md` |

Five death-path bodies of §4 #7 were not missing. `loot_generateDrops` (`difftest_items`),
`creature_bossRank`, `player_giveExp`, `player_getSkillRank` (`difftest_combat`) and
`anim_findTrack` (`difftest_anim`) had been executed. The probe could not see them because
their modules keep no address table. The same holds for the item bodies the loot reaches.
The probe now lists:

- the `difftest_items` bodies by property, in `ITEM_BODIES`. The properties were rerun on
  2026-10-21, 22 of 22 PASS. The list also takes in their two game callees,
  `item_getUnitMultiplier` and `item_randomizeVariant`;
- `ref_combat_death.EXECUTED`, for the rest.

**Findings that change the seed:**

- A bleeding hit's gut chunk costs **1 shared draw** (`GameObject_ctor`) and 7 own draws.
- Each shattered bone (`PhProp_ctor2`) and the gold pile (`Gold_ctor2`) cost 1 shared draw
  each.
- A Skeleton constructed with an element makes **one shared draw** in the holder's element
  setter (`weapon-holder.md`). The constructor difftest could not see it, because the holder
  was a stub there.

### 6.2 Probe changes

All are AUTHORED and labelled in `tools/probe_full_placement.py`.

- `--pool` hands out zero-filled blocks. The objects built in them do not run.
- `--type NAME` sets the constructor's type name, so `SkeletonBow` (kind 4) and the others
  can be probed. The report prints the weapon kind `+0x3d0`.
- The page `0x00c00000` that holds the world's fixture handles is zero-filled. The fixture
  model `0x00c00040` was a pointer to nothing, and `creature_dropHeldPartAsProp` (executed)
  reads it at a Skeleton's death.
- These became services:
  - the rigid-body calls `rigidbody_init`, `quat_*` and `rigidbody_updateDerived`. The
    body's one draw is the cosmetic seed;
  - `obj_stopRunning`;
  - the lookups `model_getMeshJoint`, `anim_getJointMatrix` and `resref_get`, as `res_find`
    and `model_getBounds` already were;
  - `libc_sprintf`, answered by rendering the format.
- `MAX_STEPS` is 400 M per call. A boss's death builds items with the real C string
  routines, and 4 M steps was not enough. That was a budget, not an unexecuted body.

### 6.3 Results

`python3 -u tools/probe_full_placement.py --pool --class … [--ticks N] [--hit-every 25]
[--serial s] [--type T] [--placement native] [--all]`. The log is
`local/probe/full-placement-r3.txt` (untracked). In every row there was no STOP and no
unexecuted body, with `--all` too.

| Class | Run | States entered (frame:state) | End |
|---|---|---|---|
| Skeleton (kind 1), serial 1 or 31 | idle, 3,000 ticks | 0:0, 121:1, 123:3 | still chasing at 3,000 (see 6.4) |
| Skeleton, native placement | idle, 3,000 | 0:0, 2:3 | still chasing |
| SkeletonBow (kind 4) | idle, 3,000 | 0:0, 121:1, 123:3, 156:8, then 3/8 every 20 and 7 frames | no stop |
| Skeleton, serial 1 | hit every 25 | 25:3, 99:0x12, 100:3, 199:0x12, 200:3, **299:0x14** | death: shatter and the bonechip loot (17 PhProp blocks of 0x248 between them, one gold pile of 0xc0), then the delete |
| Skeleton, serial 31 | hit every 25 | 32:3, 99/199/274:0x12, **299:0x14** | death, as above |
| SkeletonBow | hit every 25 | 3/8 with 0x12 on hits, **0x14** at 299 | death, as above |
| AntQueen | idle, 3,000 | as round 2 (0, 1, 3, 8/9, 0x17, 0x18, 3/6) | no stop |
| AntQueen | hit every 25 | flinches 24 and 174, **299:0x14** | death: boss loot (items built through `difftest_items` bodies, 3 PhProps and 3 gold piles), 16 gut chunks earlier; 300 ticks of state 0x14 |
| Soul, both placements | idle, 3,000 | 0/1 alternating (391:0, 513:1, …) | no stop |
| Soul | hit every 25 | 0/1 | no stop: a player's hit is not a Demon's |

Answer, round 3: on the round-5 placement, the original AntQueen, Skeleton (melee and bow)
and Soul run the default Full fight, idle for 3,000 ticks and attacked to their deaths,
through executed bodies and services only.

### 6.4 Limits found this round

- **The idle Skeleton never closes in.** Its states 1 and 3 walk by root motion from the
  clip, and the probe's clip clock has none (§5). A melee Skeleton never reaches its swing
  (state 6) or block (0x11) here. Those arms are executed (`skeleton-run.md`), but the probe
  does not show when the native would reach them.
- **The bow never releases.** State 8's release waits for event bit 0 of
  `Creature_stepAnim`, and the clip clock raises no events. No arrow block (`0xb0`, `0x74`,
  `0x1c8`) is asked for. The release arm and its projectile calls are executed by
  `difftest_skeleton_run`. The arrow constructors run there as recording stubs, and are
  executed elsewhere (`skeleton-run.md` §8).
- §3.1's "frame 32 (ready tick 33) with serial 31" does not reproduce. With serials 30–32
  the probe's Skeleton first enters state 3 at frame 123, after the idle timer. The native's
  tick-33 figure was measured with its own placement and timing; it is not this probe's.
- The objects the pool hands out never run. Each new object would need its own run body
  for that: `GutChunk_run` (on `PhProp_run`, about 890 instructions of rigid-body physics),
  the bone props' `PhProp_run`, `Gold_run`, and the arrows.

### 6.5 What is still missing, ranked

Nothing on this placement stops the probe. Ranked by when the native could reach it:

| # | Body | Address | Reached |
|---|---|---|---|
| 1 | `GutChunk_run` and `PhProp_run` (gut chunks, bone props) | `0x1edb18`, `0x155fcc` | every frame after the first bleeding hit or shatter; own draws only, plus decals and particles |
| 2 | `Gold_run`, `Gold_onTouch`; the item props' run and pickup | `0x157b58`, `0x157a9c` | after a death, while the loot lies |
| 3 | The arrows' and `MissileWeapon`'s runs | — | after a bow release |
| 4 | Holder slots 18–24 (draw, per-frame update, save/load) and Weapon2's slots; slot 21 stays *recorded* | — | every Skeleton tick (slot 21) |
| 5 | `creature_getAttachMatrix0`, `model_getAttachMatrix` | `0x287940`, `0x1795f8` | a Soul held by its owner (Minion), state 0x1d |
| 6 | `AntWave_ctor` and the AntWave object | `0x238654` | AntQueen state 0x19, which nothing requests |
| 7 | The touch dispatch and the Frost Armor carrier's burn tick (§4 #10) | — | potion 1 on a player |

## 7. Round 4: the next list executed; real clips; objects that run (2026-10-21)

### 7.1 What was executed

Every body below ran against a model on seeds 20973 and 7 with 0 mismatches. Each document
lists every field read and written, every call with its seed draws and every constant with
its address.

| §6.5 # | Bodies | Figures (per seed) | Document |
|---|---|---|---|
| 1 | `GutChunk_run` `0x1edb18` (333/333), `PhProp_run` `0x155fcc` (888/890; two delay slots of likely branches), and under them `rigidbody_pointVelocity`, `rigidbody_applyCollisionImpulse`, `rigidbody_integrate`, `rigidbody_addForceAtPoint`, `model_getHullPoints`, `Prop_ctorNamed`, `Prop_ctorRes`, `ItemProp_ctor3` (all 100 %) | 3,000 single calls per entry; 180 lives (gut chunks, bones, props) built by the real constructors and stepped every frame (about 27,000 frames compared) | `phprop-run.md` |
| 2 | `Gold_run` `0x157b58`, `Gold_onTouch` `0x157a9c`, the credit (`hud_addGoldFloater`, `hud_tickGold`, `hud_flushGold`), the item pickup (`itemprop_tryPickup`, `PhProp_interact`, `ItemProp_interact`, both prompts), `ItemProp_ctor2`, `Prop_run` (16 bodies, every instruction) | 49,000 cases; 1,000 pile sequences (real `Gold_ctor2`, N ticks, a touch, the credit ticks) | `gold-run.md` |
| 3 | The Skeleton's four arrows chained from the real constructor with its arguments: `MissileWeapon` construction, run, touch, end, destructor; the element arrows' runs, hits and ends; their three destructors `0x3cde04`, `0x3cdf4c`, `0x3ce30c` | 600 arrows, 75,264 and 77,455 calls compared | `arrow-run.md` |
| 4 | Holder slots 18–24 of Weapon1, WeaponShield and Weapon2 (24 bodies), `creature_drawHeldPart`, Weapon2 slots 8 and 16 | 6,000 calls; every block entered | `weapon-holder-slots.md` |
| 5 | `creature_getAttachMatrix0` `0x287940` (22/22), `model_getAttachMatrix` `0x1795f8` (57/57), `model_getAttachWorldMatrix` `0x175330` (91/92), `anim_getJointMatrix` re-executed; and inside `Soul_run` state 0x1d (about 2,800 entries) | 3,000 cases per function | `attach-matrix.md` |
| 6 | `AntWave_ctor` `0x238654` (inside AntQueen state 0x19), `AntWave_run`, `AntWave_draw`, `AntWave_dtor` (100 %) | about 80,000 calls; 151/155 waves, 63 run to their end (601 runs each) | `antwave.md` |
| — | `PhProp_dtor`, `GutChunk_dtor`, `Prop_dtor`, `ItemProp_dtor`, `Gold_dtor`, `anim_advanceUnitSpeed` (the bodies the probe met next once the objects ran) | 3,000 cases per body; all instructions but each destructor's padding `nop` | `tools/ref_prop_dtors.py` |

**Findings that matter for a port or for sync:**

- **Gold** goes whole to the toucher's slot (`g_players[slot] + 0xe4`, capped at 99,999,999),
  not split by `g_numPlayers` as the script's `givePlayerGold` is. It is credited 43 ticks
  after the touch through one of 8 floaters, then paid (p + 7) >> 3 per tick. The pickup
  path makes no shared draw. `gold-run.md` §9 compares this with `t3/research-items`: no
  disagreement.
- A resting prop (a gut chunk, a bone, a loot item) costs **one shared draw** when it comes
  to rest and is rebuilt (`Prop_ctorNamed`, `Prop_ctorRes` or `ItemProp_ctor3`). Rest comes
  on frame 181 at the earliest and on frame 402 at the latest (`phprop-run.md` §3.8).
- A **monster's arrow never sticks** and never pierces (both need owner flag 0x40); no arrow
  class has gravity. Every arrow costs one shared draw at construction; a plain arrow one
  more per victim that passes the enemy test.
- **Holder slot 21** stores nothing outside the stack and makes no shared draw. The load
  slot 24 rebuilds the element: one shared draw per element of kind 1–6.
- The **held Soul** in state 0x1d only places particles with the two matrices; its position
  is set by `Minion_run`. No shared or cosmetic draw.
- **AntQueen state 0x19**: no code requests it (258 set-state call sites and every store to
  `+0x232` searched; *Observed*), so the AntWave stays *Inferred* unreachable.

### 7.2 Animation for the probe: what the research documents, and the gap

The task was to supply root motion and animation events from the animation research. What is
documented:

- **The mechanism**, executed: `anim_advance`, `Creature_stepAnim` and the track operations
  (`animation.md` §5, §7; `tools/ref_anim.py`), event windows and root-motion extraction
  (`t3/research-anim`, `creature-animation-dispatch.md` §4, `rendered-creature-animation.md`
  §6).
- **The Skeleton's events**, executed: its constructor's fifteen `anm_setEventSlots` on the
  shared skelcom block (`combat-ctors.md` §4): bit 0 at 0.3 s on the swing rows, 0.3 and
  0.9 s on rows 0x1d/0x1e, and on the bow rows 0x39–0x3b bit 1 at 0.2 s then bit 0 at
  1.3 s. `t3/research-anim`'s per-class table has **no** Skeleton events (its `EVENTS` entry
  is empty and its clip entries are unnamed), because its scan reads the class definition,
  and the Skeleton's clips live in the skelcom block instead.

What is **not** documented anywhere in the research: the clips' own data — each clip's length,
the root track that gives the motion, the event slots' values before a constructor writes
them. They are the contents of the skeleton commander's, the ant queen's and the soul's lumps on the disc. That is
the gap; no table of them is committed, and none may be (they are game data).

So the probe does not fake them. **`--clips [PATH]`** reads them at run time from the user's
own disc image (or a directory of its `.LMP` files): every `.anm` entry of the probed class's
definitions and of the skelcom block, and the definitions' `.vif` models, copied in and
relocated by the game's own `anm_relocate` / `model_relocate`; any `.anm`/`.vif` that
`res_find` asks for later is loaded the same way. The animation bodies then run **for real**:
`anim_init`, `anm_relocate` and the bodies `difftest_anim` executed (`ANIM_BODIES`), with the
VU0 pose program run by `difftest_anim`'s own interpreter of its instruction words. The event
bits are what the constructors install; the root motion is what `anim_advance` takes from the
clip. Without `--clips` the probe keeps the 20-tick clip clock and says so.

Verification of that path: `tools/difftest_anim.py` was rerun on exactly the 118 clips the
probe loads (skelcom, AntQueen, Soul, skelnorm): **61 of 61 properties PASS on seed 20973 and
on seed 7** (`--quick`; 2,659 and 2,743 steps with a root-motion delta). The probe's own
`world_slideMove` service applies the delta on flat ground (§2.1).

### 7.3 Other probe changes (AUTHORED, labelled in the code)

- `--run-objects` (implies `--pool`): the probe keeps the run lists the `obj_runEvery*`
  calls join and, each frame, calls slot 4 of every pool-built object in `runObjects` order
  (`object-system.md` §5.4: the every-frame list, newest first, before the creature; then
  this frame's 15- and 60-lists). `obj_delete`d objects get slot 1 (3) at the start of the
  next frame; `handle_clear(+4)` leaves the list. A class whose run or destructor is not
  executed is a stop. When the probed creature deletes itself, what it left keeps running.
- `--skills`: the game's start-up initialiser builds the 101 Skill objects first, as
  `difftest_skills_a` does (`0x16ac74 (1, 0xffff)`, `0x1ebca0`). The AntQueen's state-7 and
  state-9 strikes read SkillPoisonWeapons (`g_skillTable[26]`); without it they read address
  0, which real events now reach.
- `--placement duel`: round5 without the other two classes' stand-ins (see 7.4).
- **Two corrections of the world.** `world_collectObjectsInBox` now follows its executed
  contract (`object-system.md` §4.3: radius and height overlap, cell order, at most limit − 1)
  instead of a point test; with the point test an arrow at chest height never found the
  player. The stand-ins' last move `+0x308`/`+0x30c` is 0 (idle): the difftest worlds left
  random values there (99, −120 on the player), and the bow's lead point
  (`Creature_leadTargetPoint`) aimed at a player who was not moving.
- Holder slot 21 runs for real (`ref_holder_slots`); `RECORDED` keeps only `Creature_init`.
- `jumpgate_getTravelState` (a getter, run real by every `difftest_natives` case) and the math
  leaves of `difftest_core`'s table count as executed.
- New services, each with its evidence in the code: `sound_playHit` (name, `res_find`,
  `sound_playOnObject`; no seed), `light_link`, `light_unlink`, `light_relink`, `light_dtor`,
  `trail_*`, `sound_playSample` (no call, no seed word), `fx_modelStatusEffects` (cosmetic
  seed only, D37), `fx_impactPuffNearCamera`, `fx_ringBurst`, `camera_shake`,
  `water_disturb`.

### 7.4 Results

`python3 -u tools/probe_full_placement.py --run-objects --clips --skills --ticks 3000 --class …
[--type T] [--placement P] [--hit-every 25]`; the script is `local/probe/matrix-r4.sh` and
the log `local/probe/full-placement-r4.txt` (untracked). **No row stops**: every body the
fight reaches, the objects it leaves included, is executed or a service.

| Class | Placement | Run | What happens (frames) |
|---|---|---|---|
| Skeleton (kind 1) | round5 | idle | 0:0, 121:1, 123:3; walks by root motion from (70, 140) to (−22.5, 116.9) toward the **Soul stand-in** (team 0, nearer than the player), 192:6; 19 swings land (`Creature_hitTargetAtReach` → `damage_apply`, first 210), 3/6 alternating to 3,000 |
| Skeleton (kind 1) | duel | idle | 2:3; walks 104 units to (30.2, 48.0), 56.7 from the player; 66:6; **the swing lands on the player at 84** (`Player_takeDamage`), 20 swings in 3,000 frames |
| SkeletonBow (kind 4) | duel | idle | 18:8; **the first arrow leaves at 96 and hits the player at 116**; 24 arrows, every one hits (the bow stands still: state 8 does not walk) |
| SkeletonBow | round5 | idle | first release 234, 23 arrows, each hits its target (the Soul stand-in) |
| Skeleton, both kinds, both placements | — | hit every 25 | 0x12 on hits, 299:0x14; the shatter's 17 bones run 402 frames each (6,834 `PhProp_run`) and come to rest at 701 as 17 `Prop`s (`Prop_ctorNamed`, one shared draw each; the bones' `PhProp_dtor` at the next flush); the props run `Prop_run` and destroy themselves through slot 1 from frame 1002 (`Prop_dtor`, 16 of them by frame 1300); a gold pile, when the loot makes one, runs `Gold_run` to the end |
| AntQueen | round5 | idle | as round 3 (0, 1, 3, 8/9, 0x17, 0x18, 3/6); now with real clips her bites land (`Creature_hitTargetAtReach`, first 283, 23 in 3,000) on the Soul stand-in |
| AntQueen | round5 | hit every 25 | flinches 24 and 124, 187:8, 277:9, **299:0x14**; 15 gut chunks (6,030 `GutChunk_run`; 15 destroyed or rested), 5 bones and items, 3 gold piles; every object runs to frame 3,000 or its end |
| Soul | round5, native | idle / hit | 0/1 alternating; wanders by root motion up to about 310 from the player |

Seed-relevant timing the clip clock could not give (all *Executed* in the probe, on the
authored world): the melee Skeleton's swing event fires 18 frames after it enters state 6;
the bow's release 78 frames after state 8 (bit 0 at 1.3 s); an arrow covers the 156 units
to the player in 20 frames.

### 7.5 Limits

- **The player is a stand-in.** It does not run: `Player_takeDamage` gets the hits (the
  amounts are 0 because `Creature_setStats` is a fixture that writes only hit points), but
  the pending damage never reaches `+0x228`; and it never walks over a gold pile, so
  `Gold_onTouch` and the credit, executed in `gold-run.md`, are not reached here. The
  touch needs the player's own `obj_moveWithCollision` (`gold-run.md` §8).
- On round5 the Skeleton and the AntQueen target the Soul stand-in, not the player; §3.1's
  "first sighting of the player" was this. `duel` is the placement on which they reach the
  player.
- Clips the disc image has no entry for (`fx.lmp::game_swish_chest*.anm`, sound sequences)
  keep the world's stand-in record; they are listed in the report.
- The probe's grid has the creatures only (grid A); pool-built objects are not returned by
  the box query, as grid-B props are not in the game either.
- Element arrows are not on this placement (a Skeleton gets an element in under 10 % of
  constructions). Their hit paths reach `Creature_setEffectTimer` `0x118950` (cold) and
  `LightEffect_ctor` `0x201bd8` (exploding), not executed (`arrow-run.md`).

### 7.6 What is still missing, ranked

| # | Body | Address | Reached |
|---|---|---|---|
| 1 | The player's own tick on the stand-in: `Player_run`, the pending damage, `obj_moveWithCollision`'s touch dispatch (then the executed `Gold_onTouch`, credit and item pickup) | — | every frame of a real player |
| 2 | `Creature_setEffectTimer`, `LightEffect_ctor` | `0x118950`, `0x201bd8` | a cold or exploding arrow's hit |
| 3 | `StaticFire_ctor` and the fire | `0x2c5240` | burning debris (`+0x23a` = 1) from an exploding container |
| 4 | `PhProp_ctor4` | `0x155bdc` | a deflected plain arrow with model words |
| 5 | `Minion_run`'s placement of the held Soul | `0x286364`–`0x2863e0` | a Soul held by its owner |
| 6 | `Gold_draw`, `Gold_ctor`, Weapon2 slots 1–7, 9–15, 17, `AntWave_clone` | — | drawing, a level's placed pile, two-hand holders |

## 8. Round 5: the rigid body, the arrows' hit paths, StaticFire_ctor and the held Soul (2026-10-21)

### 8.1 What was executed

Each ran against a model on seeds 20973 and 7 with 0 mismatches; every document lists the fields
read and written, the calls with their seed draws and the constants with their addresses. The
checks of each comparison (a model mutated by hand and caught) are in the documents.

| §7.6 # | Bodies | Figures (per seed) | Document |
|---|---|---|---|
| (new) | `rigidbody_init` `0x1682f0` (140/140), `rigidbody_updateDerived` `0x167a58` (111/111), `quat_fromMat3` (146/146), `quat_normalize` (25/25), and `PhProp_initPhysics` composed with all four real | 3,000 + 3,000 + 1,000 composed cases | `rigidbody-init.md` |
| 2 | `Creature_setEffectTimer` `0x118950` (39/40), `LightEffect_ctor` `0x201bd8` (163/163), and the cold, fire and exploding arrow chains re-run with both real | 3,000 + 3,000 direct; chains 600 arrows, 75,264 and 77,455 calls (unchanged) | `arrow-hit.md` |
| 3 | `StaticFire_ctor` `0x2c5240` (172/174), `StaticFire_initCommon` `0x2c5814` (82/82), the particle body `0x2c6aa8` (70/70) | 3,000 each | `staticfire-ctor.md` |
| 5 | `Minion_run` `0x2862c0` from its entry to the state dispatch, with the held Soul's placement `0x286364`–`0x2863e0` (32/32); 89 of 1,116 instructions of the body | 3,000 (1,299 / 1,270 placed a held object) | `minion-place.md` |

**Findings that matter for a port or for sync:**

- **`rigidbody_init` makes one *cosmetic* draw** (`0x404460`, never the shared seed) and clears the
  0x98-byte body. `PhProp_initPhysics` then overwrites the orientation it drew, so for any PhProp
  only the inertia, the inverse mass and the seed word survive; a crate keeps the drawn turn
  (`q = (0, 0, 1, u)`, `u` the draw's high half over 2¹⁶). The three recordings of the native
  World can be replaced by `rigidbody-init.md` §2–§4.
- **A cold arrow ADDS to the victim's chill timer** (`+0x344 += stat 3 / 2` through
  `Creature_setEffectTimer(victim, 1, owner, …)`); it does not set it. The explosion's light lasts
  `max(trunc(0.25 × 60), 1)` = 15 frames and costs the one shared draw of its `GameObject_ctor`.
- **A StaticFire costs one shared and two own draws** (initCommon's `mod 300` and the particle
  body's phase pick); its neighbour count includes every object the 30-unit box finds, and
  four or more halve its life.
- **The held Soul is placed every Minion tick after the Minion's own move, animation step and
  knock-back, before its state handler**: the attach point of index 0 with the Minion's scale
  and facing, the facing copied, the grid cell updated; no draw.

### 8.2 The probe now

`python3 -u tools/probe_full_placement.py --run-objects --clips --skills --ticks 3000 …` (the
script is `local/probe/matrix-r5.sh`, the log `local/probe/full-placement-r5.txt`, untracked). The
rigid-body bodies, `Creature_setEffectTimer`, `LightEffect_ctor` and `StaticFire_ctor` now run for
real instead of as recording stubs; four services are new (AUTHORED, labelled in the code): the
circle sweep (flat dry ground, no wall: the whole move), the tagged heap, the path-grid block and
the always-draw list. A prop with a real body moves sideways, which is why the sweep is asked now
and was not in round 4. The report now lists the pool objects' lifecycle (built, ran, ended, how,
after how many frames).

**No row of the 14-row matrix stops**; every body the three fights reach, the objects they leave
included, is executed or a service. The distances (3,000 ticks, idle and with the player hitting
every 25):

| Class | Placement | Run | What happens (frames) |
|---|---|---|---|
| AntQueen | round5 | idle | as round 4: 0, 1, 3, 8/9, 0x17, 0x18, 3/6; 23 bites land from frame 283; ends at 3,000 |
| AntQueen | round5 | hit every 25 | flinches 24 and 124, 8 at 187, 9 at 277, **0x14 (death) at 299**; the hits and the death together make **15 gut chunks, 5 loot items (`PhProp`) and 3 gold piles**. **Every gut chunk destroys itself on its first bounce, 56–65 frames after it is built** (913 `GutChunk_run` in all; in round 4, with an all-zero body, they never bounced and ran 402 frames each: 6,030). The 5 items rest after **259–403 frames** (median 403: most on the unconditional rest of the 402nd frame) and become 5 `ItemProp`s the pool keeps and the run lists do not (a loot item waits for a pickup); the gold runs to the end (8,100 `Gold_run`) |
| Skeleton (kind 1) | round5 / duel | idle | as round 4: walks by root motion, swings from 210 (round5, 19 swings) or the player at 84 (duel) |
| Skeleton, both kinds, both placements | — | hit every 25 | 0x12 on hits, 0x14 at 299; the shatter's **17 bones** (18 for the bow on duel) rest after **193–403 frames** (median 403); 16 become `Prop`s (the others `ItemProp`s, which wait for a pickup) that run 301 frames and destroy themselves (`Prop_run` 4,816 runs) |
| SkeletonBow | round5 / duel | idle | arrows from 234 (round5, 23) or 96 (duel, 24; hits the player at 116); each lives 17–22 frames and destroys itself on its hit |
| Soul | round5 / native | idle / hit | 0/1 alternating for 3,000 frames; wanders up to about 310 from the player. No Minion holds it here: the held placement is executed by `difftest_minion` alone |

Seed-relevant timing, all *Executed* in the probe on the authored world: a loot item or bone prop
rests on its 193rd–403rd frame; a gut chunk (these all had bit 0) ends on its 56th–65th.

### 8.3 What is still missing, ranked

| # | Body | Address | Reached |
|---|---|---|---|
| 1 | The player's own tick on the stand-in: `Player_run`, the pending damage, `obj_moveWithCollision`'s touch dispatch (then the executed `Gold_onTouch`, credit and item pickup) | — | every frame of a real player; unchanged from §7.6 #1 |
| 2 | `StaticFire_run` `0x2c595c`, `StaticFire_draw` `0x2c65e8`, `StaticFire_dtor` `0x2c5770`, `StaticFire_clone` `0x1300e0`, `StaticFire_ctor2` `0x2c54f8` | as listed | any fire built (burning debris from an exploding container, FireBomblet, ShadowStep): the constructor is executed, the fire's frame is not, so a probe stops on the first fire's first run |
| 3 | `LightEffect_run` `0x1ee050` (`Observed` in `ref_combat_spells`, no difftest) | `0x1ee050` | the 15 frames after an exploding arrow, and 65 constructor callers |
| 4 | `Minion_run`'s state dispatch (states 0–0x17, 1,027 of 1,116 instructions) and the Minion class's bodies; who sets and clears the held handle `+0x3c8` | `0x2863ec`–`0x287400` | a Soul held by a Minion (the placement itself is executed) |
| 5 | `PhProp_ctor4` | `0x155bdc` | a deflected plain arrow with model words |
| 6 | `Gold_draw`, `Gold_ctor`, `ItemProp` / `Prop` draw bodies, Weapon2 slots 1–7, 9–15, 17, `AntWave_clone` | — | drawing, a level's placed pile, two-hand holders |
| 7 | The services the probe answers: `terrain_sweepCircle` `0x185a40`, `terrain_heightBelow`, `terrain_height`, `water_test` | — | every prop frame; with real levels the answers are disc data, read at run time: where chunks, bones and items rest on slopes and against walls is not known from this probe (flat dry ground) |
| 8 | Clip lengths, root motion and the hull tables of the models | disc data | taken at run time with `--clips`; not documented, not committed |

Ranked by how soon the native could reach it: #1 (a player fight), #2 and #3 (any exploding arrow
or container), then #4.
