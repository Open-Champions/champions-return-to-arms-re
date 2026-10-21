# AntQueen_run, every state, and AntQueen_pickFlyDest

US `SLUS_209.73` v2.00. Prose of `tools/ref_antqueen_run.py`; the comparison is
`tools/difftest_antqueen_run.py`, the synthetic tests `tools/test_ref_antqueen_run.py`.

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
on a queen its own constructor built (game virtual table, creature base real underneath,
`AntQueen_setState` real with `AntQueen_pickFlyDest` real inside it, `AntQueen_fadeBankTracks`
and `AntQueen_updateBank` real), and the model agreed on the calls to everything outside the
models (in order, with arguments; the stack damage descriptor decoded), every byte stored
outside the stack, the shared seed `0x404464` with its draw count, and the result.
**Observed**: read at the address. **Inferred** and **Unknown** as usual. Nothing here ran
on a console, in PCSX2 or on the live rig.

## 1. What was executed before this

- `docs/spec/combat-ctors.md` (`t3/research-combat-ctors` e9777eb): constructor, set-state,
  and the run up to its switch, with the switch's range test patched out in the
  interpreter.
- Combat round 5 (`docs/spec/combat-round5.md`): states 0 and 1 on planted objects with
  the prologue stubbed, plus the two bank helpers on their own (30 of 30, 101 of 101).
- Not executed anywhere before this: the switch past state 1 (101 of 607 instructions
  had run), `AntQueen_pickFlyDest` (a recording stub in every rig).

This round removes the patch: the original runs the whole function, every state.

## 2. Coverage and figures

`python3 tools/difftest_antqueen_run.py` (seed 20973) and `--seed 7`: four runs of 3000
ticks each (machines A and B, two seeds each), 16,095 and 16,152 calls compared, 0
mismatches in calls, stores, seed or result.

| Function | Address | Seed 20973 | Seed 7 |
|---|---|---|---|
| `AntQueen_run` | `0x236f78` | 593 of 607 | 593 of 607 |
| `AntQueen_pickFlyDest` | `0x238150` (to `0x238360`) | 132 of 132 | 132 of 132 |
| `AntQueen_fadeBankTracks` | `0x2385dc` | 30 of 30 | 30 of 30 |
| `AntQueen_updateBank` | `0x238448` | 101 of 101 | 101 of 101 |
| `AntQueen_setState` | `0x237918` | 526 of 526 | 526 of 526 |

Calls per entry (seed 20973): run 11,958, set-state 2,941, pickFlyDest on its own 497,
constructor 221, `Creature_takeDamage` 478.

The 14 instructions of the run never executed are dead, by reading:
- `0x237224`: state 5's fall-through after the bite test. It is reached only when the
  draw's low bits are non-zero, and the branch before it is taken exactly then.
- `0x237580`–`0x2375b4` and `0x23779c`–`0x2377cc` (six blocks): the search for a free
  descriptor slot past slot 0. The descriptor is initialised with every slot free
  immediately before, so slot 0 is always taken (the same dead search as
  `poisonGasSpell_run` and `LooseFire_onTouch`).

As a check, changing the state-6 reach to 40 and the flight probe distance to 151 gives
61 call mismatches in a tenth of the ticks.

The 0x238360–0x238448 body between `pickFlyDest` and `updateBank` is the unreferenced
gib spawner of `docs/monsters-2.md`; it is not part of `pickFlyDest` (which ends at its
return at `0x23835c`).

## 3. The tick

Notation: `c` the queen; `T` the target handle `+0x234` (its object at node `+0xc`);
`clock` the creature clock `+0x300` (zeroed by `Creature_ctor`, +1 in each
`Creature_run`); `ev` the event bits `Creature_stepAnim` returns; `queue < 4` the signed
byte `+0x118` (track count) below 4; `flag n` the halfword `+0x11a` and mask n;
`see(arc, far)` = `Creature_canSeeTargetIn(c, s16 facing +0x38, arc, ray 0; near 0, far,
lead 0)`; `st(n)` = slot 27 (`AntQueen_setState`). A timer word "expired" means its signed
value is strictly below the signed clock.

**Prologue** (unchanged from `combat-ctors.md`): `Creature_processDamage` and `Creature_run`
with the class model (definition `+0x24` → `+0xc`), a non-zero `Creature_run` returns;
`Creature_updateActive` (result NOT tested); `ev = Creature_stepAnim(c; 1.0)` (literal
`0x3f800000` at `0x236fc0`); `Creature_applyKnockback(c; 0.5)` (`0x3f000000` at `0x236fd4`);
slot 23 (0). Then the state, the s16 at `+0x232`, is compared UNSIGNED with 0x1a
(`0x237004`): negative numbers and 0x1a and above return. The jump table is the 26 words
at `0x541b80`.

| State | Reads | Writes | Calls (in order) and draws |
|---|---|---|---|
| 0 idle | `+0x118`, `+0xf4`, `+0x300` | — | `fadeBankTracks`; slot 25 (0); if it saw and queue < 4 → `st(3)`; slot 25 (0) AGAIN; if it saw and queue < 4 → `st(3)`; `+0xf4` expired → `st(1)` |
| 1 wander | — | — | `updateBank`; slot 25 (0) → `st(3)`; else `Creature_moveToDest` |
| 3 chase | `T`, `+0x44`, `+0x38`, `+0x3d4`, `+0x300`, `+0x118` | `+0x44` | `updateBank`; no T → `st(0)`; ONE OWN DRAW d; `d & 3` ≠ 0: `see(6000, 20)` → `st(6)`; `d & 3` = 0: `creature_findEnemyInCone(c, s16(u16 facing − 0x7fff), 6000; 0, 40)` non-zero → `st(7)`; then `Creature_moveToTarget`; `+0x3d4` expired and queue < 4 → `st(8)` |
| 5 | as 3, plus `+0x314` | `+0x44` | ONE OWN DRAW d; the same two exclusive tests as 3, each only with T; then `Creature_isNotRooted` → `st(3)`. No bank call |
| 6 bite | `T`, `+0xd0`, `+0xd2`, `+0xd4`, `+0x3cc`, `+0x11a` | `+0x3cc` = 1 | `fadeBankTracks`; with T: on `ev & 1` `Creature_hitTargetAtReach(c, s16 +0xd0, s16 +0xd2, s16 +0xd4, 0x40008, no descriptor; 36)` and `+0x3cc` = 1; while `+0x3cc` is 0 `Creature_turnToTarget`; flag 8 clear → `st(3)` |
| 7 rear sting | `+0x38`, `+0xd0`, `+0xd2`, `+0xd4`, `0x41b1d8`, `0x4f714c`, `+0x11a` | — (stack descriptor) | `fadeBankTracks`; on `ev & 1`, with NO target test: v = slot 11 of the skill at `g_skillTable[26]` (SkillPoisonWeapons; `(0, trunc(g_levelMonsterLevel), 0)`); descriptor `(0x17, v, v, 0)` (low 16 bits); `Creature_hitTargetOrPlayerInArc(c, s16(u16 facing + 0x7fff), 3000, s16 +0xd0, s16 +0xd2, s16 +0xd4, 0x40008, descriptor; 0, 40)`; flag 8 clear → `st(3)` |
| 8 flying chase | `T`, `+0x3d4`, `+0x300`, `+0x11a`, `+0x44` | `+0x3d4` = 0 (sometimes), `+0x44` | `updateBank`; no T → `st(0)`; `+0x3d4` expired → `st(0x17)`; flag 8 set → nothing; `see(6000, 20)` → `st(9)` then ONE OWN DRAW, `d % 3` (unsigned) = 0 → `+0x3d4` = 0; else `Creature_canSeeTargetIn(c, 0, 0x7fff, 0; 0, 20, 0)` → `Creature_turnToTarget`, else `Creature_moveToTarget` |
| 9, 10 sting | `T`, `+0xd0`–`+0xd4`, skill as 7, `+0x11a`, `+0x232` | — | `fadeBankTracks`; with T: on `ev & 1` the poison descriptor of 7 and `Creature_hitTargetAtReach(c, s16 +0xd0, s16 +0xd2, s16 +0xd4, 0x10004, descriptor; 40)`; then `Creature_turnToTarget` (every tick with T); flag 8 clear → `st(0x17)` from 10, `st(8)` from 9 |
| 0x12 hit | `+0x11a`, `+0x118` | — | `fadeBankTracks`; flag 0x10 clear and queue < 4 → `st(3)` |
| 0x13 stunned | `+0x31c` | — | `Creature_isNotStunned` → `st(0)` |
| 0x14 dead | — | — | `fadeBankTracks`; `Creature_deadUpdate(c, ev, &(0, 0, 0), 0; 30)` |
| 0x17 fly to a point | `T`, `+0x3d4`, `+0x300`, `+0x11a`, `+0x104`–`+0x10c`, `+0x2c4` | `+0x3d4` = 0 (sometimes) | `updateBank`; no T → `st(0)`; `+0x3d4` expired: `Creature_turnToTarget`, `see(3000, 500)` → `st(0x18)`, and nothing else (no flag test); not expired: flag 8 set → nothing; `Creature_moveTo(c, copy of +0x104)` returns non-zero, or signed `+0x2c4` ≥ 31 → `+0x3d4` = 0 |
| 0x18 landing | `+0x11a`, `+0x118` | — | `fadeBankTracks`; flag 8 clear and queue < 4 → `st(3)` |
| 0x19 wave | `T`, `+0xf4`, `+0x300`, `+0x10`–`+0x1c`, `+0x38`, `+0x118` | — | `fadeBankTracks`; with T and clock = `+0xf4` − 120 (32-bit equality): `pool_new(0x3d8)`, and with a block `AntWave_ctor(block, target object, (x + cos16(f)·(r + 10), y + sin16(f)·(r + 10), z), f, 600)`, f the s16 facing and r the radius `+0x1c`; `+0xf4` expired and queue < 4 → `st(3)` |
| 2, 4, 0xb–0x11, 0x15, 0x16 | — | — | nothing |

Slot 25 is `Creature_canSeeTarget` `0x10e658` (pointblank range, then visual range in the
visual arc; the base body of `ref_arena_monsters.slot25_can_see_target`). The bank
helpers read and write only the queen: `fadeBankTracks` the rates `+0x128 + 32k` of
tracks whose clip `+0x11c + 32k` is one of the class words `+0xb4`, `+0x44`, `+0xbc`,
`+0x4c`; `updateBank` the spring `+0x3dc`, `+0x3e0`, the halfword `+0x3e4` and the weights
`+0x124 + 32k` (`docs/spec/combat-round5.md`). Neither draws.

**Draws.** The run itself draws only the queen's own generator `+0x44`: one per tick in
states 3 and 5, one more when state 8 asks for 9. It never draws the shared seed
directly. Shared draws in a tick come only from what it calls: `Creature_moveTo`'s
free-spot teleport (`world_findFreeSpot`), `Creature_processDamage`, `Creature_run` and the hit calls'
`damage_apply`. Set-state draws are `combat-ctors.md` §3 (all own draws).

### Constants and where they come from (Observed)

| Value | Use | Address |
|---|---|---|
| 0x1a | state count (unsigned compare) | `0x237004` |
| `0x541b80` | jump table, 26 words | `0x237014` / `0x23701c` |
| 4 | queue limit (signed less-than) | `0x237058`, `0x237094`, `0x2371b8`, `0x237870` |
| 6000 | bite and cone arc | `0x237144`, `0x237184`, `0x2371f8`, `0x23722c`, `0x237388` |
| 20.0 `0x41a00000` | bite far range | `0x237134`, `0x2371f0`, `0x237380` (kept in f21 for the second test) |
| 40.0 `0x42200000` | rear cone, state-7 arc range, state 9/10 reach | `0x237170`, `0x237240`, `0x2375cc`, `0x2377d8` |
| 36.0 `0x42100000` | state 6 reach | `0x237460` |
| 0x40008 | bite and rear sting damage flags | `0x23745c`+`0x237474`, `0x2375bc`+`0x2375f4` |
| 0x10004 | state 9/10 damage flags | `0x2377d4`+`0x2377f8` |
| 0x17 | poison descriptor entry | `0x237554`, `0x237770` |
| `0x41b1d8` | `g_skillTable` `0x41b170` + 4·26 (SkillPoisonWeapons, object `0x6e1f00`) | `0x237520`+`0x237524`, `0x237738`+`0x237740` |
| slot 11 (table +0x58) | `Skill_getStatTier2` `0x3c8690` in table `0x51c1f0`, reached through the skill's `+0x60` | `0x237534`–`0x23754c` |
| `0x4f714c` | `g_levelMonsterLevel`, truncated by `cvt.w.s` | `0x23752c`, `0x237748` |
| 3000 | rear sting arc, state 0x17 landing arc | `0x2375ec`, `0x2372c8` |
| 500.0 `0x43fa0000` | state 0x17 landing far range | `0x2372b8` |
| 0x7fff | state 8 any-direction arc; the rear offsets ±0x7fff | `0x2373f8`; `0x237164`, `0x23723c`, `0x2375c8` |
| 3 | state 8 reset divisor (`divu`) | `0x2373cc` |
| 31 | state 0x17 stuck limit (signed less-than 0x1f) | `0x23732c` |
| 30.0 `0x41f00000` | `Creature_deadUpdate` size | `0x2378b0` |
| 120 | wave frame offset | `0x237628` |
| 10.0 `0x41200000` | wave offset past the radius | `0x237638` |
| 0x3d8, 600 | AntWave block size, its last argument | `0x237668`, `0x2376a4` |

## 4. AntQueen_pickFlyDest (0x238150)

`(out, queen) -> out`. Executed, 132 of 132.

- No target (`+0x234` zero): out = the queen's position `+0x10`–`+0x18`. No draw, no call.
- Otherwise up to ten tries. Each try makes THREE OWN DRAWS of the queen's `+0x44`:
  angle a = s16 of the first; distances `d · 2⁻¹⁶ · 300 + 300` from the second (x) and the
  third (y), as `((f32(d) × 2⁻¹⁶) × 300) + 300`. The candidate is `(target.x + dist_x ×
  cos16(a), target.y + dist_y × sin16(a), queen.z)`, the target object re-read for each
  axis.
- A probe 150 behind the queen's FACING (not behind the candidate): `cos16` / `sin16` of
  `s16 facing − 0x7fff`, passed without narrowing to 16 bits (the routines fold the angle
  themselves), times 150, added to the candidate. `terrain_height(g_world 0x44fdc8,
  probe; queen radius +0x1c)`.
- The try is accepted when `z − 12 < h` and `h < z + 12`, both strict, z the queen's z
  re-read; out = the candidate. After ten misses: out = the queen's position.
- Constants: 2⁻¹⁶ `0x37800000` (`0x2381b0`), 300 `0x43960000` (`0x2381c0`), 150
  `0x43160000` (`0x2381cc`), 12 `0x41400000` (`0x2382c0`), 10 tries (`0x2382e4`,
  `0x238304`), −0x7fff (`0x23824c`, `0x23827c`).
- Draws: 3 per try, 3 to 30 own draws, never the shared seed. *Inferred*: on flat ground
  (every probe at the queen's height) the first try is always taken.

## 5. What the queen does in a fight (Inferred from the above)

- A new queen is in state 0 with `+0xf4` = 0 (the constructor stores state 0 without its
  entry). On her first tick without a sighting `+0xf4` (0) is below the clock (1), so she
  asks for state 1 (wander) at once.
- **When she sees a player she enters state 3** (from 0 or 1, through slot 25). The native
  client measured this at ready tick 33 of the round-5 Full placement. In state 3, every
  tick: the bank spring; one own draw; three ticks in four she tests for a bite (target
  inside 20 in the 6000 arc ahead) and goes to 6; one tick in four she looks for any enemy
  inside 40 in the 6000 cone BEHIND her and goes to 7 (the rear poison sting, which hits the
  target or a player in the arc behind her). Otherwise she walks to the point on the
  target's rim facing her (`Creature_moveToTarget`).
- Take-off: the constructor's `+0x3d4` is the absolute value 180, so from clock 181 on,
  any chasing tick with fewer than four tracks asks for state 8 (flight: speed 240, a new
  `+0x3d4` = clock + 300 + d % 180). In the air: stings (9) while she sees the target
  within 20 ahead; when `+0x3d4` runs out, 0x17 (fly to `pickFlyDest`'s point, then land
  through 0x18 when the target is within 500 in the 3000 arc), then 3 again.
- States 5, 10 and 0x19 are never requested by the run. 0x19 and 10 have no requester in
  the class (`docs/monsters-2.md`); state 5 is stored only on an outside request. The
  AntWave (state 0x19) stays *Inferred* unreachable.
- *Open*: the common filter may turn a request into 0x10 (attack cooldown `+0x318`
  running, `docs/monsters-2.md`). State 0x10 does nothing in this run, so a queen put
  there stays until something else sets her state (a hit's 0x12, death's 0x14).

## 6. Corrections to `docs/monsters-2.md` (AntQueen states)

- State 0 calls slot 25 TWICE unless the first call saw and the queue was below 4. A
  sighting with a full queue does not leave state 0, and the wander test still runs: a
  queen that sees her target with four or more tracks can go to 1.
- State 7's facing is `u16 facing + 0x7fff` narrowed to s16; the cone tests of 3 and 5 use
  `u16 facing − 0x7fff` narrowed. The descriptor value is slot 11 of the skill through its
  `+0x60` table (table offset 0x58; the prose's "offset 0x5c" is that slot's function
  word), low 16 bits stored twice.
- State 0x17, timer expired: the turn and the landing sight run without the flag-8 test;
  only the moving branch waits for flag 8.
- `pickFlyDest`: both height bounds are strict; the probe is behind the queen's facing,
  not the candidate's direction; three own draws per try.

## 7. Callees

Bodies executed elsewhere (each a recording stub here, answered by the scripted world):
`creature_canSeeObj` `0x10c810`, `creature_findEnemyInCone` `0x10cf78`,
`Creature_applyKnockback` `0x115eb8`, `Creature_deadUpdate` `0x1108a0`
(`tools/ref_combat_runtime.py`); `Creature_hitTargetAtReach` `0x1196e8` and
`Creature_hitTargetOrPlayerInArc` `0x119a20` (`tools/ref_combat_monsters.py`);
`terrain_height` `0x183820` (`tools/ref_world.py`); `Skill_getStatTier2` `0x3c8690`
(`tools/ref_skills_a.py`); `pool_new` `0x14fdb8`; the anim calls of set-state
(research-anim).

`AntWave_ctor` `0x238654` and the AntWave object (run `0x238938`, draw `0x2387d0`,
destructor `0x238750`), reached only from state 0x19, are executed since 2026-10-21
(`docs/spec/antwave.md`); nothing requests that state (the search is there). *Unknown*: how `Creature_hitTargetOrPlayerInArc` treats a poison entry 0x17
on a player victim beyond `damage_apply`'s round-1 contract.
