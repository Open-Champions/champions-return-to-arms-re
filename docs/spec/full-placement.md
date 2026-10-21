# The round-5 Full-fight placement with AntQueen and Skeleton: how far the original gets

US `SLUS_209.73` v2.00. Prose of `tools/probe_full_placement.py` (tests:
`tools/test_probe_full_placement.py`). Written 2026-10-21, after this round executed
`Skeleton_isEnemy`, every AntQueen state, `AntQueen_pickFlyDest`, `Soul_takeDamage`, the
two takeDamage wrappers, six destructors and potion 1's fire entry
(`docs/spec/combat-ctors-2.md`, `docs/spec/antqueen-run.md`, `docs/spec/fire-touch.md`).

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
