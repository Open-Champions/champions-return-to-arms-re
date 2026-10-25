# Skeleton_run, every state; the line-of-fire sweep, the lead point and slot 12

US `SLUS_209.73` v2.00. Prose of `tools/ref_skeleton_run.py`; the comparison is
`tools/difftest_skeleton_run.py`, the synthetic tests `tools/test_ref_skeleton_run.py`.
Written 2026-10-21.

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
on a skeleton its own constructor built (game virtual table, creature base real underneath,
`Skeleton_setState` real, `Skeleton_isEnemy` and the type-info getters real inside slot
23's target scan, and the five bodies of this page real), and the model agreed on the calls
to everything outside the models (in order, with arguments; stack arguments and the hit
descriptor decoded), every byte stored outside the stack, the shared seed `0x404464` with
its draw count, and the result. **Observed**: read at the address. **Inferred** and
**Unknown** as usual. Nothing here ran on a console, in PCSX2 or on the live rig.

## 1. What was executed before this

- `docs/spec/combat-ctors.md`: the constructor, `Skeleton_setState`, and the run up to its
  switch (the range test patched out in the interpreter).
- `docs/spec/combat-round5.md` §1.2: only the slot-25 force arguments of states 0 and 1.
- `docs/spec/combat-ctors-2.md`: `Skeleton_isEnemy`, `Skeleton_takeDamage`, `Skeleton_dtor`.
- `docs/spec/full-placement.md` §4 ranked what was left: the switch past states 0 and 1
  (666 of 809 instructions), `creature_allyInLineOfFire`, `Skeleton_onNearbyEvent`.

This round removes the patch for the Skeleton: the original runs the whole function.

## 2. How it was run, figures and coverage

    python3 -u tools/difftest_skeleton_run.py --seed 20973 -v
    python3 -u tools/difftest_skeleton_run.py --seed 7 -v
    python3 -m unittest tools.test_ref_skeleton_run

Four runs of 3000 ticks per seed (machines A and B, `seed` and `seed + 1`). The driver puts
the skeleton in any state (all 24 and out-of-range numbers), moves `+0xf4` around the
clock and around 0, the weapon kind `+0x3d0` (bow or not), the clip flags `+0x11a`, the
frame (so the sweep's every-eighth-frame test passes), stun, root and cooldown timers,
`g_levelMonsterLevel`, the target (present or not, near or far, moving), the facing, and now
and then removes the weapon holder `+0x50`. The others get the game's tables of Skeleton,
Skelight, Soul, AntQueen, Player and Demon or the synthetic one. The holder answers every
hand part and element (slots 15, 16, 17), the pool gives or refuses blocks.

| | Seed 20973 | Seed 7 |
|---|---|---|
| Calls compared, all entries | 18,653 | 18,658 |
| `Skeleton_run` | 11,999 | 11,998 |
| `Skeleton_setState` (requests between ticks) | 2,930 | 2,912 |
| `creature_allyInLineOfFire` directly | 1,015 | 973 |
| `Creature_leadTargetPoint` directly | 468 | 455 |
| `Skeleton_onNearbyEvent` directly | 1,173 | 1,214 |
| `Skeleton_hasShield` directly | 338 | 331 |
| `Skeleton_ctor`, `Creature_takeDamage` | 248, 482 | 293, 482 |
| Release calls seen inside the run: sound / MissileWeapon / cold / fire / exploding arrow | 97 / 49 / 2 / 5 / 1 | 144 / 70 / 10 / 5 / 5 |
| Line-of-fire rays cast inside the run | 158 | 335 |
| Mismatches (calls, stores, seed, result, one-sided faults) | 0 | 0 |

| Function | Address | Executed (both seeds) | Not executed |
|---|---|---|---|
| `Skeleton_run` | `0x2a6864` (to `0x2a7508`) | 808 of 809 | `0x2a68c4` |
| `creature_allyInLineOfFire` | `0x10d5e8` (to `0x10d7fc`) | 132 of 133 | `0x10d7cc` |
| `Creature_leadTargetPoint` | `0x11aaf8` (to `0x11abd0`) | 54 of 54 | |
| `Skeleton_onNearbyEvent` | `0x2a7688` (to `0x2a774c`) | 49 of 49 | |
| `Skeleton_hasShield` | `0x2a7da0` (to `0x2a7e04`) | 25 of 25 | |

The two instructions never executed are dead, by reading:

- `0x2a68c4` is the delay slot of the branch-likely taken when `Creature_run` returns
  non-zero. `Creature_run` `0x112948` always returns 0 (executed, `ref_creature.run`).
- `0x10d7cc` is a `nop` after an unconditional branch and its delay slot; nothing jumps to it.

Checks: each of these model changes was detected. Arrow origin 17 above mid-height instead
of 18: 3 call mismatches in a tenth of the ticks. Slot 12's window ±10000 instead of
±9999: 1 mismatch in a tenth. The sweep's count threshold taken from previous 0/1 instead
of zero/non-zero: 27 of 107. `MissileWeapon_ctor`'s fourth stack word halved by an
arithmetic shift instead of toward zero: 6 call mismatches over the full run (only negative
`+0xd2` values tell them apart).

## 3. The tick

Notation: `c` the skeleton; `T` the target handle `+0x234` (its object at node `+0xc`);
`clock` the creature clock `+0x300`; `f4` the word `+0xf4`; `ev` the event bits
`Creature_stepAnim` returns; `bow` means the weapon-kind word `+0x3d0` equals 4 (a 32-bit
compare); `flag n` the clip flags halfword `+0x11a` and mask n; `st(n)` = slot 27
(`Skeleton_setState`); `see(arc, ray, far)` = `Creature_canSeeTargetIn(c, s16 facing +0x38,
arc, ray; near 0, far, lead 0)`; "expired" means the signed `f4` is strictly below the signed
clock. Slot numbers of the holder `+0x50` are table offset / 8 (`+0x88` is slot 17).

**Prologue** (unchanged from `combat-ctors.md`): `Creature_processDamage` and
`Creature_run` with the class model; `Creature_updateActive`, an inactive skeleton returns;
holder slot 21 (skelcom block `0x5023e0`, c; 0.5); `ev = Creature_stepAnim(c; 1.0)`;
`Creature_applyKnockback(c; 0.7)`; slot 23 (0). Then the state, the s16 at `+0x232`, is
compared UNSIGNED with 0x18 (`0x2a6954`): negative numbers and 0x18 and above return. The
jump table is the 24 words at `0x54bf00` (formed at `0x2a6964`, read at `0x2a696c`).

| State | Reads | Writes | Calls (in order) and draws |
|---|---|---|---|
| 0 idle | `+0x3d0`, `f4`, `+0x300` | — | slot 25 (0) → `st(3)`; bow: slot 25 (1) → `st(3)`; expired → `st(1)`; else `Creature_isAwayFromHome(c, 1)` → `st(1)` |
| 1 walk | as 0 | — | the same two sights → `st(3)`; expired → `st(0)`; else `Creature_moveToDest(c, 0)` |
| 3 chase | `T`, `+0x3d0`, `+0x38`, `+0x1c`, `+0x300` | `f4` (sometimes) | no T → `st(0)`. Bow: `see(2000, 1, 400)` → `st(8)`; `see(0x7fff, 1, 400)` → `Creature_turnToTarget`, else `Creature_moveToTarget`. Melee: `see(6000, 0, 24)` → `st(6)`; `creature_allyInLineOfFire(c, T object, 0; 300, radius × 3)` non-zero → ONE OWN DRAW d, `f4` = clock + d % 240 + 240 (stored before the call), `st(5)`; else `see(0x7fff, 0, 20)` → turn, else chase |
| 5 wait | `+0x3d0` (twice), `+0x314`, `f4`, `+0x300`, `T`, `+0x1c` | — | bow: `see(2000, 0, 400)` → `st(8)`; then the kind is READ AGAIN and only a non-bow makes `see(6000, 0, 20)` → `st(6)`; `Creature_isNotRooted` 0 → stay; expired → `st(3)`; no T → stay; `creature_allyInLineOfFire(c, T object, 1; 300, radius × 3)` non-zero → stay; else `st(3)` |
| 6 swing | `T`, `+0x50`, `+0xd0`–`+0xd4`, `+0x11a` (twice), `f4` | `+0xa8` bit `0x200`, `f4` | with T: on `ev & 1` `Creature_hitTargetAtReach(c, s16 +0xd0, s16 +0xd2, s16 +0xd4, 8, holder slot 17 (1) or 0 without a holder; 36)`; flag 8 set → `Creature_turnToTarget`, clear → creature flag `0x200` set (64-bit or). Then flag 8 clear (re-read) → `f4` − 1; signed `f4` > 0 → stay, else `st(3)` |
| 8 bow | `T`, `+0x10`–`+0x20`, `+0x38`, `+0x50`, `+0xd0`–`+0xd4`, `0x4f714c`, skill words, `0x3e9ce8`, `0x3e9cec`, `+0x11a`, `f4` | `+0x44` (own draws), `f4` | no T → `st(0)` and ON to the count-down below. With T: aim = the point 300 ahead of the facing, then `Creature_leadTargetPoint(c, aim; 400)` (§5). On `ev & 1` the release (§3.1). On `ev & 2` holder slot 1 (2, 0x56). Flag 8 set → slot 26 (0, the aim point). Then flag 8 clear (re-read) → `f4` − 1; `f4` > 0 → stay, else `st(3)` |
| 0x10 | `T`, `+0x318` | `+0x318` (no target) | `Creature_isAttackReady` → `st(0)`; else `Creature_fleeFromTarget(c, 0)` |
| 0x11 block | `f4`, `+0x300` | — | expired → `st(3)` |
| 0x12 hit | `+0x11a` | — | flag 0x10 clear → `st(3)` |
| 0x13 stunned | `+0x31c` | — | `Creature_isNotStunned` → `st(0)` |
| 0x14 dead | — | — | `Creature_deadUpdate(c, ev, &(0, 0, 0), 1; 20)` |
| 0x17 rise | `+0x10`–`+0x18`, `+0x11a` | — | `fx_spawn(7, copy of the position)`; flag 0x10 clear → `st(0)` |
| 2, 4, 7, 9–0xf, 0x15, 0x16 | — | — | nothing |

Slot 25 is `Creature_canSeeTarget` `0x10e658`, slot 26 `Creature_turnToward` `0x10bb08`,
slot 27 `Skeleton_setState` `0x2a7768`. A state change by slot 27 happens inside the tick;
in state 8 without a target the tick requests 0 and then, when `f4` reaches 0, 3 as well.

### 3.1 The release (state 8, event bit 0)

1. Holder slot 1 (2, 0) when there is a holder: the hand-2 part off.
2. Origin `o = (x, y, (z + height +0x20 × 0.5) + 18)` (two separate float adds).
3. `delta = aim − o`; `a = atan2_16(delta.y, delta.x)`.
4. When `|a − s16 facing|` > 1000 (32-bit difference, `slti 0x3e9` at `0x2a6f80`): the aim
   point becomes the point 300 ahead of the facing again (x, y and z of the creature, not
   of the origin), and `a` is computed AGAIN from the SAME delta, so it does not change.
   Only slot 26's turn point changes.
5. `delta × rsqrt(1.0, |delta|²)` (the EE `rsqrt.s` at `0x2a7048`; the sum is x² + y², then
   + z²), each component then × 400.
6. A unit-ball vector by OWN-DRAW rejection: three draws a try, each `2 × (d × 2⁻¹⁶) − 1`,
   tried again while x² + y² + z² > 1 (strict). velocity = delta + that × 48.
7. ONE OWN DRAW d: `libc_sprintf(buffer, 0x54bed8, (d & 3) + 1)` (the whoosh clip name,
   one `%d`), `res_find(0x54bef0, buffer)` (the effects lump), `sound_playOnObject(entry,
   c; 1.0)`.
8. `e` = holder slot 16 (1), 0 without a holder, compared as a signed register:

   | e | Block | Constructor and arguments |
   |---|---|---|
   | 2 | `pool_new(0xb0)` | `ColdArrowProjectile_ctor` `0x2d6fb4` (block, o, a, c, trunc(`g_levelMonsterLevel`), word `0x41b220` = `g_skillTable[44]`) |
   | 1 | `pool_new(0xb0)` | `FireArrowProjectile_ctor` `0x2d6238` (…, word `0x41b21c` = `[43]`) |
   | 6 | `pool_new(0x74)` | `ExplodeArrowProjectile_ctor` `0x2daeb4` (…, word `0x41b22c` = `[47]`) |
   | anything else (0, 3–5, 7+, negative) | `pool_new(0x1c8)` | `MissileWeapon_ctor` `0x150ee4` (block, 0, word `0x3e9ce8`, word `0x3e9cec`, o, velocity, a − 0x4000, c; stack 0, 0, s16 `+0xd0`, s16 `+0xd2` / 2 toward zero, 0, 0, s16 `+0xd4`, 4, 0) |

   A refused block skips the constructor. The three arrow classes take the angle, not
   the velocity: the scatter of step 6 reaches only the `MissileWeapon`. The two words at
   `0x3e9ce8` / `0x3e9cec` are 0 in the image (Observed); who writes them is Unknown.

**Draws.** The run draws only the skeleton's own generator `+0x44`: one in state 3 when the
sweep says yes, and 3 × (tries) + 1 in a release. It never draws the shared seed directly;
shared draws in a tick come from the prologue's callees (`Creature_processDamage`,
`Creature_run`, slot 23) and from `Creature_moveToDest` / `Creature_moveTo`.

### 3.2 Constants (Observed)

| Value | Use | Address |
|---|---|---|
| 0x18 | state count, unsigned | `0x2a6954` |
| `0x54bf00` | jump table, 24 words | `0x2a6964` / `0x2a696c` |
| 0.5 `0x3f000000` | holder slot 21 | `0x2a68f0` |
| 1.0 `0x3f800000` | stepAnim | `0x2a690c` |
| 0.7 `0x3f333333` | knockback | `0x2a6920` / `0x2a6924` |
| 400.0 `0x43c80000` | bow sight range; lead speed and arrow speed | `0x2a6af8`, `0x2a6c68`; `0x2a6e78` |
| 2000 | bow sight arc | `0x2a6b10`, `0x2a6c70` |
| 0x7fff | any-direction arc | `0x2a6b40`, `0x2a6c18` |
| 6000 | melee sight arc | `0x2a6b6c`, `0x2a6cb0` |
| 24.0 `0x41c00000` | state 3 melee range | `0x2a6b58` |
| 20.0 `0x41a00000` | state 3 turn range, state 5 melee range, deadUpdate size | `0x2a6c08`, `0x2a6ca8`, `0x2a74a0` |
| 3.0 `0x40400000` | sweep distance = radius × 3 | `0x2a6b94`, `0x2a6d08` |
| 300.0 `0x43960000` | sweep range; aim distance ahead | `0x2a6ba8`, `0x2a6d18`; `0x2a6e50` |
| 240 | state 3 wait (`divu` and add) | `0x2a6bc8`, `0x2a6bf4` |
| 36.0 `0x42100000` | swing reach | `0x2a6d90` |
| 8 | swing damage flags | `0x2a6da8` |
| 0x200 | blocking creature flag | `0x2a6dd4` |
| 0.5, 18.0 `0x41900000` | arrow origin height | `0x2a6f04`, `0x2a6f1c` |
| 1000 | far-lead test (`slti 0x3e9`) | `0x2a6f80` |
| 1.0 | rsqrt numerator; ball bound; sound volume | `0x2a702c`; `0x2a70ac` |
| 2⁻¹⁶ `0x37800000` | draw scale | `0x2a7090` |
| 48.0 `0x42400000` | scatter | `0x2a7128` |
| `0x54bed8`, `0x54bef0` | whoosh format, effects lump | `0x2a71b0`/`0x2a71b8`, `0x2a71c4`/`0x2a71c8` |
| 2, 1, 6 | element tests | `0x2a7214`, `0x2a7228`, `0x2a7224` |
| 0xb0, 0x74, 0x1c8 | pool sizes | `0x2a7250`/`0x2a7290`, `0x2a72d0`, `0x2a7310` |
| `0x41b220`, `0x41b21c`, `0x41b22c` | skill words (cold, fire, exploding) | `0x2a7260`+`0x2a726c`, `0x2a72a0`+`0x2a72ac`, `0x2a72e0`+`0x2a72ec` |
| `0x4f714c` | `g_levelMonsterLevel`, `cvt.w.s` | `0x2a7264`, `0x2a72a4`, `0x2a72e4` |
| `0x3e9ce0` + 8, + 0xc | `MissileWeapon_ctor` words | `0x2a731c`/`0x2a7324`, `0x2a733c`, `0x2a7330` |
| 4 | `MissileWeapon_ctor` stack word 7 | `0x2a7340` |
| 0x56 | hand-2 part on event bit 1 | `0x2a73ac` |
| 7 | rise effect | `0x2a697c` |

## 4. creature_allyInLineOfFire `0x10d5e8` (creature c, target T, previous p; range, distance)

*Executed*, 132 of 133. Returns 0, 1 or p.

1. T is 0 → p. `(g_simFrame XOR s8 +0x230) & 7` non-zero → p (`0x10d634`). So on seven
   frames in eight the caller's previous answer passes through unchanged.
2. `n = world_countLivingNonplayerCreaturesInBox(copy of T position; T radius +0x1c ×
   1.75)` (`0x3fe00000` at `0x10d648`).
3. `creature_objInArcRange(c, T, 0x4000; range)` 0 → 0 (no ray).
4. `b = atan2_16(T.x − c.x, T.y − c.y)` — the x difference in the first (f12) argument —
   and the heading `h = s16(0x4000 − b)` (`0x10d6a0`).
5. `t, hit = world_raycast(g_world 0x44fdc8, origin (c.x, c.y, c.z + 13), direction (cos16 h
   × distance, sin16 h × distance, 0), c, &hit (zeroed first), 3, 0; 1.0)` (13.0
   `0x41500000` at `0x10d6fc`, mask 3 at `0x10d730`).
6. p = 0: 1 when n ≥ 4 (`slti 4` at `0x10d754`), 0 < t < 1 (both strict) and hit ≠ T.
   p ≠ 0: the same with n ≥ 3 (`0x10d790`). Otherwise 0.

Reads: `g_simFrame`, `c+0x230`, `c+0x10`–`+0x18`, `T+0x10`–`+0x1c`. Writes: nothing
outside its stack. No draws. Callees: `world_countLivingNonplayerCreaturesInBox` `0x108970`,
`creature_objInArcRange` `0x10c410`, `math_atan2_16`, `math_cos16`, `math_sin16`,
`world_raycast` `0x18ad94`.

*Inferred*: the "ally" of the name is not tested here. The ray answers any object of mask 3
but the target; the count is of living non-player creatures around the target. The Skeleton
uses it to wait (state 5) while some other body is between it and its target in a crowd.

## 4a. The sweep's two callees (added 2026-10-21 by the parent run)

`tools/ref_sweep.py`, compared by `tools/difftest_sweep.py`, synthetic tests
`tools/test_ref_sweep.py`. The comparison is this document's whole run (§2) with the two
bodies REAL inside the sweep. Between ticks it also enters both directly. The box count is
taken on the creature's or another object's position, with half sizes 0–300. The arc test
is made on every other object, placed at headings within and across the arc, with arcs 0,
2000, 0x4000, 0x7fff, 0x8000 and 0xffff and ranges 0–600. Crowds of living creatures are
planted so that the 3 / 4 thresholds are crossed.

    python3 -u tools/difftest_sweep.py --seed 20973 -v
    python3 -u tools/difftest_sweep.py --seed 7 -v
    python3 -m unittest tools.test_ref_sweep

| | Seed 20973 | Seed 7 |
|---|---|---|
| Calls compared in the whole run | 18,930 | 18,719 |
| `world_countLivingNonplayerCreaturesInBox` entered directly | 1,445 | 1,472 |
| `creature_objInArcRange` entered directly | 1,404 | 1,411 |
| Mismatches (calls, stores, seed, result) | 0 | 0 |
| `world_countLivingNonplayerCreaturesInBox` `0x108970` | 60 of 60 | 60 of 60 |
| `creature_objInArcRange` `0x10c410` | 106 of 106 | 106 of 106 |

With both callees real, `Skeleton_run` reached 790 of 809 instructions on each seed. The
block not entered is `0x2a6bc0`–`0x2a6c04`, state 3's "something in the way" request. It
needs all of these at once: a crowd of 4, the target inside the arc and range, a clear
terrain ray, and a world ray that hits something else. Its arm is covered by §2's run, where
the sweep's callees are scripted.

Checks: each of these model changes was detected (`--quick`).

- The living mask set to 0x60 instead of 0x68: 27 mismatches.
- The ray origin at half the height instead of the full height: 10 mismatches.

**world_countLivingNonplayerCreaturesInBox `0x108970` (centre; half size h)** (*Executed*).

1. The centre is copied. The box is centre − h to centre + h on each axis (`sub.s`, then
   `add.s`).
2. `world_collectObjectsInBox(low, high, list, 0x80)` (capacity at `0x108974`).
3. The result is the number of listed objects whose flags `+0xc & 0x68` are exactly `0x20`
   (`0x108a38`, `0x108a10`): a creature that is neither a player (`0x40`) nor dead (`8`).
   Other bits do not matter.

Reads: the centre and each listed object's `+0xc`. No stores outside the stack, no draws.

**creature_objInArcRange `0x10c410` (creature c, object o, arc; range r)** (*Executed*).
Returns 0 or 1.

1. An `o` of 0 gives 0.
2. d = o − c on x and y. On z, d is the difference of the mid-heights, `z + height
   +0x20 × 0.5` each (0.5 at `0x10c450`).
3. The bearing is `s16(0x4000 − atan2_16(dx, dy))` (`math_atan2_16` with f12 = dx and
   f13 = dy). Subtract the facing, read unsigned, and narrow to s16. Take the absolute value
   (`negu`, so −0x8000 becomes 0x8000).
4. That value must be below the arc, which is narrowed to s16 at `0x10c414`/`0x10c42c`, in a
   signed compare. An arc of 0x8000 is therefore −0x8000 and nothing passes.
5. Then `(c − o)²` on x and y, less o's radius `+0x1c`, must be below r² (strict,
   `0x10c50c`).
6. Then `terrain_raycast(g_world, c's position with z + height +0x20 (the full height),
   d, 3; 1.1)` (`0x3f8ccccc` at `0x10c538`, mask 3 at `0x10c54c`). The result is 1 when the
   ray misses (t < 0) or t > 1; anything else gives 0.

Reads: c `+0x10`–`+0x20` and `+0x38`; o `+0x10`–`+0x20`. No stores outside the stack, no
draws.

## 5. Creature_leadTargetPoint `0x11aaf8` (creature c, out or 0; speed)

*Executed*, 54 of 54. No target handle, or a handle whose object is 0 → 0 and `out` is not
touched. Otherwise `k = sqrt(dx² + dy²) / speed` with `(dx, dy)` the target position less
c's, and the point `(T.x + T+0x308 × k, T.y + T+0x30c × k, T.z + T+0x20 × 0.5)` (`0x3f000000`
at `0x11ab30`) is written to `out` when it is not 0; the result is 1. `+0x308`/`+0x30c` are
the target's last move (`Creature_moveBy`). No draws, no calls.

## 6. Skeleton_onNearbyEvent `0x2a7688` (slot 12) and Skeleton_hasShield `0x2a7da0`

*Executed*, 49 of 49 and 25 of 25.

`Skeleton_onNearbyEvent(c, code, position, other)`: the three words at `position` are copied
to the stack and never used (Observed `0x2a76a4`–`0x2a76bc`; the pointer must be readable).
Only `code` 2 (`0x2a768c`, a full-register compare): `Skeleton_hasShield(c)` 0 → nothing;
state (s16 `+0x232`) not 3 or 5 → nothing; `other` 0 → nothing; else `b = atan2_16(other.y
− c.y, other.x − c.x)` and, when `(b − s16 facing + 9999)` is below 19999 unsigned (9999 at
`0x2a7710`, 19999 at `0x2a7714`; that is −9999 ≤ difference ≤ 9999, no 16-bit wrap), slot 27
with 0x11 (`0x2a771c`). No draws; the only store is through `Skeleton_setState`.

`Skeleton_hasShield(c)`: holder `+0x50` 0 → 0; else holder slot 15 (2); 1 when the answer is
0x60 or 0x62 (`0x2a7dd8`, `0x2a7de4`), else 0. For the Skeleton's own WeaponShield holder,
slot 15 is `0x3c2590`.

## 7. Corrections and sharpenings

- `docs/monsters-2.md`, Skeleton state 8: without a target the run requests 0 and still
  counts `+0xf4` down in the same tick, so it can request 3 right after (both requests go
  through `Skeleton_setState`). The origin's height is `(z + height × 0.5) + 18`, two adds.
  The `MissileWeapon` stack words are 0, 0, `+0xd0`, `+0xd2` / 2 (toward zero), 0, 0,
  `+0xd4`, 4, 0; the names min / max / rating there stay *Inferred*.
- State 5: after the bow's sight fails the kind word is read again, and only a non-bow makes
  the melee sight (so a kind changed in between would take the melee test; nothing changes
  it). States 0 and 1 compare `+0xf4` with the clock strictly signed.
- State 6: the blocking flag `0x200` is set on every tick with a target while the clip is
  not playing (flag 8 clear), not once.
- `symbols`: `creature_allyInLineOfFire` — the "every 8th frame" is "returns the previous
  answer unchanged on 7 frames in 8"; the thresholds 4 / 3 and the target exclusion are
  §4. `Skeleton_onNearbyEvent` — "purpose not established" is §6 (block on a kind-2 event in
  front while chasing or waiting, with a shield). `Creature_leadTargetPoint` — §5 (returns
  0 and leaves `out` alone without a target).

## 8. Still not executed

Callees the run reaches whose bodies no difftest has run (recording stubs here):

- (`world_countLivingNonplayerCreaturesInBox` `0x108970` and `creature_objInArcRange`
  `0x10c410` are now executed: §4a.)
- WeaponShield slots 15 `0x3c2590` (slot 12 through `hasShield`), 16 `0x3c25c0` (state 8
  release, the element), 17 `0x11be20` (state 6, the hit descriptor), 1 `0x11bc18` (state 8,
  hand-2 part), 21 `0x11b2a8` (prologue).
- `world_raycast` `0x18ad94` (a service in the probe).

Bodies executed elsewhere, stubs here: `Creature_hitTargetAtReach`, `Creature_deadUpdate`,
`Creature_applyKnockback`, `creature_canSeeObj` (`tools/ref_combat_full.py`), the three
arrow constructors (`tools/ref_skills_b.py`), `MissileWeapon_ctor` (`tools/ref_combat_full.py`).

*Unknown*: who sends slot 12 event code 2 to a Skeleton (`docs/monsters-2.md` infers
`Player_run`), and who writes `0x3e9ce8` / `0x3e9cec`.
