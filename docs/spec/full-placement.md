# The round-5 Full-fight placement with AntQueen and Skeleton: how far the original gets

US `SLUS_209.73` v2.00. Prose of `tools/probe_full_placement.py` (tests:
`tools/test_probe_full_placement.py`). Written 2026-10-21, after this round executed
`Skeleton_isEnemy`, every AntQueen state, `AntQueen_pickFlyDest`, `Soul_takeDamage`, the
two takeDamage wrappers, six destructors and potion 1's fire entry
(`docs/spec/combat-ctors-2.md`, `docs/spec/antqueen-run.md`, `docs/spec/fire-touch.md`).

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
