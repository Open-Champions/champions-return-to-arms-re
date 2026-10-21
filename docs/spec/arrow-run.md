# The Skeleton's arrows: flight, hit, stick, expiry and the destructor

US `SLUS_209.73` v2.00. Prose of `tools/ref_arrow_run.py`. The comparison is
`tools/difftest_arrow_run.py`; the synthetic tests are `tools/test_ref_arrow_run.py`.
Written 2026-10-21 for the arrows a SkeletonBow (Skeleton kind 4) releases in
`Skeleton_run` state 8 (`docs/spec/skeleton-run.md` §3.1, the release `0x2a6ed4`–`0x2a738c`,
`tools/ref_skeleton_run.py` `ARROWS`).

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
and the model agreed on the calls to everything outside the models (in order, with
arguments), every byte stored outside the stack, the shared seed `0x404464` with its draw
count, and the result. **Observed**: read at the address. **Inferred** and **Unknown** as
usual. Nothing here ran on a console, in PCSX2 or on the live rig.

## 1. The four arrows

| Element (holder slot 16, hand 1) | Class | Table | Block | Built by | Slot 4 run | Slot 6 touch | Ends with | Slot 1 destructor |
|---|---|---|---|---|---|---|---|---|
| 0, 3–5, 7+, negative | `MissileWeapon` | `0x50e5a0` | `0x1c8` | `MissileWeapon_ctor` `0x150ee4` | `0x15153c` | `MissileWeapon_onTouch` `0x152a18` | its own slot 1 with 3, inside its run | `MissileWeapon_dtor` `0x151454` |
| 1 | `FireArrowProjectile` | `0x518de0` | `0xb0` | `_ctor` `0x2d6238` | `0x2d66ac` | `_onHit` `0x2d685c` | `_end` `0x2d6bb8` → `obj_delete` | `0x3cde04` |
| 2 | `ColdArrowProjectile` | `0x518ef8` | `0xb0` | `_ctor` `0x2d6fb4` | `0x2d73c8` | `_onHit` `0x2d7aac` | `_end` `0x2d7ecc` → `obj_delete` | `0x3cdf4c` |
| 6 | `ExplodeArrowProjectile` | `0x519240` | `0x74` | `_ctor` `0x2daeb4` | `0x2db17c` | `_onHit` `0x2db4f0` | `_explode` `0x2db50c` → `obj_delete` | `0x3ce30c` |

The constructor arguments are the release's (Observed in `docs/spec/skeleton-run.md` §3.1,
Executed there): `MissileWeapon_ctor(block, 0, word 0x3e9ce8, word 0x3e9cec, origin, velocity,
a − 0x4000, skeleton; stack 0, 0, s16 +0xd0, s16 +0xd2 / 2, 0, 0, s16 +0xd4, 4, 0)` and
`XxxArrowProjectile_ctor(block, origin, a, skeleton, trunc(g_levelMonsterLevel 0x4f714c),
g_skillTable[43 / 44 / 47])`. The origin is `(x, y, (z + height × 0.5) + 18)`. The plain arrow
gets the aimed velocity (400 toward the lead point, the target's mid-height, plus 48 × a
unit-ball scatter); the three element arrows get only the angle and fly **level** at the
origin's height (velocity `(cos a, sin a, 0) × speed`).

The element-arrow element tables all have 17 slots (`+8 × 17 + 4` holds 0); the slots this
module runs are 1, 4 and 6; slots 2, 3, 7–15 are the `Projectile` base's (Observed, the
table words).

## 2. What was already executed, and where (audit, 2026-10-21)

| Body | Executed before by | In a table `probe_full_placement.executed_bodies()` reads | Covered before | Gap for the Skeleton |
|---|---|---|---|---|
| `MissileWeapon_ctor`, `_run`, `_onTouch`, slot 17, `_dtor`, `obj_moveAndCollide`, `Projectile_ctor` | `tools/difftest_combat_ranged.py` (`docs/spec/combat-projectiles.md` §9): one call per case on random state | yes, through `ref_combat_full.FULL_MODELLED` (`ref_combat_ranged.RangedModel.RANGED_MODELLED`); `obj_moveAndCollide` and `Projectile_ctor` through `ref_skills_a` | run 317 / 1,024, touch 553 / 575 | never a chain: no arrow was built by the real constructor and then flown and touched on its own state; the Skeleton's argument set was never used |
| element arrows' `_ctor`, `_ctor2`, `_run`, `_onHit`, `_end` / `_explode` | `tools/difftest_skills_b.py` (`docs/spec/skills-35-68-executed.md` §1, 43, 44, 47): casts by players and monsters, then runs to the end | yes, `ref_skills_b.MODELLED` | 691 / 699, 1,363 / 1,369, 802 / 803 for the three skills | `GameObject_ctor` was a stub there (its draw made by the script); the Skeleton calls the FIRST constructor with `g_levelMonsterLevel`, not the cast's level |
| the three element-arrow destructors `0x3cde04`, `0x3cdf4c`, `0x3ce30c` | nobody ("not modelled for any id: … the destructors") | no | 0 | an element arrow is `obj_delete`d and destroyed by the next flush through slot 1: an unexecuted body on every element arrow |

So before this round the arrow bodies were all in the probe's tables except the three
element destructors; what was missing was evidence that the bodies compose: a Skeleton's
arrow built by the real constructor, flown, touching, ending and destroyed, each step on
the state the previous one left.

## 3. What was run

`tools/difftest_arrow_run.py` builds on `tools/difftest_skills_b.py`'s world (the
executable's own Skill objects, made by running its static initialisers `0x16ac74` and
`0x1ebca0`; a handle-node pool at `0x864ea8`; players, monsters and props with stub
tables) and stub machinery. A **case** is a chain of compared calls: the constructor, then
one run per frame (`g_simFrame` + 1 before each), until the arrow ends; an arrow that
`obj_delete`s itself then gets its slot 1 with 3, as the next flush does. Each call runs
the model first on a copy-on-write view, then the original on the same memory; the next
call starts from the original's result.

Real in every call: everything in `ref_arrow_run.EXECUTED` (the 23 bodies of §1 and
`GameObject_ctor`, `Projectile_ctor`, `obj_moveAndCollide`), `ref_skills_b`'s machinery
(`handle_link` / `handle_clear` / `handle_removeNode`, `GameObject_rand` `0x1509d0`, the
Skill slots 8, 10–15), the angle functions and the C library (`rtti_typeInfoEquals`
`0x3b1250`). Stubs with scripted answers (the same on both sides): the victims' and the
owner's virtual slots (0, 2, 6, 16, 20, 36), `damage_apply`, `terrain_height`,
`world_collectObjectsInBox`, `water_test`, sound, light, trail, particle and effect calls,
`obj_delete`, `obj_runEveryFrame`, `obj_updateGridCell`, `GameObject_dtor`, `pool_free`,
`player_getSkillRank`, `SkillDodge_getStat0Fraction`, `item_parseDescriptor`,
`item_getResourceIndex`, `PhProp_ctor4`, `Creature_setEffectTimer`, `LightEffect_ctor`
(whose GameObject draw the script makes), `obj_updateActive`, `model_getSamplePoint(Count)`.

The scene of a case (scripted): the Skeleton at a random point, ground `z0` of 0, 10 or −35;
a target at 30–1,200 along a random bearing: the **idle player** (object flags `0x60`), a
**creature**, a creature and the player side by side (**crowd**), a **prop** or
**container**, an **ally** (the owner's slot 20 answers 0), **nothing** (expiry), a terrain
**ramp** (ground hit) or a terrain **wall**; in "orphan" cases the owner's back list is
cleared after 1–5 frames (its handles read 0) and it leaves the scene. `terrain_height`
answers the scene's ground; `world_collectObjectsInBox` answers the scene's objects whose
x / y extent (± radius) and height span meet the box, rotated by a per-case offset.
`g_levelMonsterLevel` 1.0–40.0, level flags 0, `0x100`, `0x40000`, PvP mode A on or off, the
two model words `0x3e9ce8` / `0x3e9cec` zero or not (they are 0 in the image), Dodge ranks
0–20 and, three times in ten, a Dodge chance set to the deflection roll or the roll + 1. A
**control group** (one plain arrow in five) is owned by a player instead, to show the stick
and the stuck-follow path the Skeleton's arrows never reach; it is reported apart.

Commands:

    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_arrow_run.py --seed 20973 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_arrow_run.py --seed 7 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tools/test_ref_arrow_run.py

| Seed | Cases | Calls compared | Mismatches | Stopped on both sides | Monster-owned runs with a stuck host | Player-owned (control) cases that stuck |
|---|---|---|---|---|---|---|
| 20973 | 600 | 75,264 | 0 | 0 | 0 | 11 |
| 7 | 600 | 77,455 | 0 | 0 | 0 | 5 |

Calls per body (seed 20973 / seed 7; every one compared, 0 mismatches): MissileWeapon ctor
301 / 299, run 21,475 / 20,389, dtor 39 / 42 (the rest are destroyed inside their run);
Fire ctor, dtor 98 / 102, run 26,688 / 24,269; Cold ctor, dtor 94 / 97, run 20,613 / 23,858;
Explode ctor, dtor 107 / 102, run 5,493 / 7,931; `handle_clear` (owner or host destroyed)
57 / 65. `python3 -m unittest tools/test_ref_arrow_run.py`: 14 tests, OK.

Outcomes (seed 20973; seed 7 alike): every class hit the idle player, a creature, the
creature and the player in one frame (crowd), the terrain, and expired; the MissileWeapon
also hit containers, was deflected by the player and by creatures, and passed allies; the
ExplodeArrow damaged props and, in the wall-foot scenes, knocked its owner. Mean runs to
the end: 300.0 for every unobstructed MissileWeapon, 601.0 for every unobstructed element
arrow.

Draws per case (means; shared `0x404464` / the arrow's own +0x44 / cosmetic `0x404460`),
seed 20973: MissileWeapon 1.48 / 17.18 / 0, Fire 1.00 / 1.74 / 0, Cold 1.00 / 21,264 / 0,
Explode 1.97 / 2,051 / 0; seed 7: 1.56 / 13.62 / 0, 1.00 / 1.97 / 0, 1.00 / 23,569 / 0, 1.90 /
3,106 / 0. Shared draws above 1 are the MissileWeapon's deflection rolls and the
ExplodeArrow's LightEffect.

Instruction coverage of each body over both seeds (they reach the same instructions):

| Body | Instructions executed (20973 / 7) | What is not executed (§8) |
|---|---|---|
| `GameObject_ctor` `0x14cb10` | 115 / 115 of 285 | a class definition, properties |
| `obj_moveAndCollide` `0x1509f8` | 271 / 271 of 276 | five likely-branch delay slots |
| `Projectile_ctor` `0x150e48` | 39 / 39 of 39 | — |
| `MissileWeapon_ctor` `0x150ee4` | 198 / 198 of 348 | kinds 1–6, an item, a launch sample |
| `MissileWeapon_dtor` `0x151454` | 50 / 50 of 58 | the return without bit 0 |
| `MissileWeapon_run` `0x15153c` | 304 / 300 of 1,024 | kinds 1, 2, 3, 5, 6, spin, impact sample |
| `MissileWeapon_onTouch` `0x152a18` | 534 / 532 of 575 | player-skill and other-kind arms, unreachable arms |
| `MissileWeapon_nearestSamplePoint` `0x153314` | 128 / 128 of 128 (control group only) | — |
| `FireArrowProjectile_ctor` / `_run` / `_end` | 130 / 79 / 26, all of them | — |
| `FireArrowProjectile_onHit` `0x2d685c` | 126 of 215 | the player-owner branch |
| `ColdArrowProjectile_ctor` / `_run` / `_end` | 118 / 366 / 384, all of them | — |
| `ColdArrowProjectile_onHit` `0x2d7aac` | 150 of 264 | the player-owner branch |
| `ExplodeArrowProjectile_ctor` / `_run` / `_onHit` | 75 / 173 / 7, all of them | — |
| `ExplodeArrowProjectile_explode` `0x2db50c` | 353 of 354 | one delay slot |
| Fire / Cold / Explode destructors | 28 of 33 / 28 of 33 / 22 of 27 | the return without bit 0 |

Checks of the comparison itself (made by hand, model restored after each, with
`PYTHONDONTWRITEBYTECODE=1`): the deflection roll `draw % 100 + 1` changed to `+ 2` →
`--cases 200`: 4 calls of 24,632 FAIL (the player hit becomes a block: `damage_apply` against
`Player_blockSparks`, and the stores of the destruction); 60 cases without the
roll-boundary answers did not catch it, which is why the script now aims three Dodge answers
in ten at the boundary. The lit arrows' `light_dtor(+0x70, 2)` changed to `1` → `--quick`: 21
of 6,992 calls FAIL (every Fire and Cold destructor).

## 4. MissileWeapon (element 0) on the Skeleton's arguments

### 4.1 Construction, `MissileWeapon_ctor` `0x150ee4`

*Executed*. Fields written (offset, width, value for the Skeleton):

| Offset | Width | Value | Constant at |
|---|---|---|---|
| `GameObject_ctor` `0x14cb10`: +0, +4, +8, +0xc, +0x34 | 4 | 0 (then the grid link, `handle_link(cell, +8, obj)`) | — |
| +0x10 | 12 | the origin | — |
| +0x1c / +0x20 | 4 | 24.0 / 72.0 (then +0x1c = 12.0 in `Projectile_ctor`) | `0x14cb10` body; `0x41400000` in `Projectile_ctor` |
| +0x24, +0x2c | 4 | 0, 0 (class definition, properties) | — |
| +0x28, +0x29 | 1 | 0x19, 0x49; then +0x28 = 0x48 | `0x151040` |
| +0x44 | 4 | the high half of **one shared draw** (the arrow's own generator) | — |
| +0x48 | 4 | `0x5122a8`, `0x5120b8`, `0x50e5a0` | `0x150f6c` |
| +0x4c | 4 | owner handle: `handle_link(+0x4c, skeleton, skeleton)` | — |
| +0x50 | 1 | 0 (splash done) | — |
| +0xc | 4 | `0x4081` (Projectile) \| `0x4001` | `0x1513bc` |
| +0x5c, +0x74, +0x8c, +0xa4, +0xbc | 4 | 0 (five handle words, released by the destructor; use Unknown) | loop `0x150f7c` |
| +0x124, +0x128 | 4 | 0 (pierced list, stuck host) | — |
| +0x174..+0x1a3 | — | light record: +0x17d 0, +0x184/+0x18c −32, +0x190/+0x198 168.0, +0x194/+0x19c `0x38149b92`, +0x1a0 0, colour (0xff, 0x9b, 0) at +0x17e and +0x186, +0x17c 0; `light_link`, then `light_unlink` (kind 0) | `0x150fbc`, `0x150fdc`/`0x150fe0`, `0x150fb8`, `0x150fc4`, `0x150fcc` |
| +0x1a4 | 12 | the origin (light position) | — |
| +0xfa, +0xfc, +0xfe | 2, 2, 1 | 0 | — |
| +0xd0 | 4 | kind 0 | — |
| +0x170 | 4 | `trail_create(1, 0x7a, 0, 0x80, 0x80, 0x80, 0x20; 0.151) ` and `trail_addPoint(trail, pos)` unless level flag `0x100`; otherwise untouched (0 from the pool) | `0x151304`/`0x151308`, `0x151310`–`0x15132c` |
| +0xd4, +0xd8 | 4 | s16 +0xd0, s16 +0xd2 / 2 of the Skeleton (damage minimum, maximum: names Inferred) | — |
| +0xdc, +0xe0 | 4 | 0, 0 | — |
| +0xe4 | 4 | s16 +0xd4 of the Skeleton (attack rating) | — |
| +0xe8 | 4 | 4 (damage flags) | — |
| +0x1b0 | 12 | the velocity | — |
| +0x38 | 2 | a − 0x4000 | — |
| +0x1c0, +0x1c4 | 4 | the two words of `0x3e9ce8` / `0x3e9cec` | — |
| +0x12c | 4 | 0 (no item: no weapon-class test, no element test) | — |
| +0xf4 | 4 | 0 | — |
| +0xcc | 1 | 0 (hit state) | — |
| +0xf8 | 1 | 1 | — |
| +0xec | 4 | `g_simFrame` + 300 | `0x151364` (frame), 300 immediate |
| +0xcd | 1 | 1 (active) | `0x151360` |
| +0xf0 | 4 | 0 (no launch sample) | — |
| +0x1bc | 4 | 0 (no impact sample) | — |

Calls in order: `GameObject_ctor` (real), `handle_link` (+0x4c), `light_link(+0x174)`,
`light_unlink(+0x174)`, `trail_create` + `trail_addPoint` (not on a cold level),
`obj_runEveryFrame(obj)`. **Draws: one shared** (inside `GameObject_ctor`), no own, no
cosmetic. Executed figures: §3.

### 4.2 Flight, `MissileWeapon_run` `0x15153c` (slot 4)

*Executed*, every run of every case. For a Skeleton's arrow:

```
+0x128 (stuck host) is 0 for a Skeleton's arrow, so the stuck branch is never taken (4.4)
+0xcc != 0:   slot 1 with 3 - destroyed now (the frame after a creature hit)
spin +0xfa is 0
r = obj_moveAndCollide(this, copy of +0x1b0)       velocity never changes: no gravity
res = (r & 1) | (+0xcc != 0 ? 2 : 0)
res != 0: +0xec = 0
   res 2 (a touch that set the hit state): +0xcc 2 -> fx_spawn(2, or 0x11 on a cold level, pos);
            3 -> +0xec = frame; 1 -> +0xec = frame + 1
   res 1 (terrain): libc_sprintf(buffer, 0x532538) (no conversion); fx 8 (level flag 0x40000)
            or 0x11 (0x100) or 2; res_find(0x532478, buffer); sound_playOnObject(entry, this; 1.0)
kind 0 on a cold level (0x100): ONE OWN DRAW; when it is divisible by 3 a second OWN DRAW
   for a puff (fx 0x11 at z + d / 65536 x 18.0) in place of the trail point
otherwise the trail point (trail_addPoint) when +0x170
g_simFrame >= +0xec: slot 1 with 3
```

Fields read: +0x128, +0xcc, +0xfa, +0x1b0..+0x1b8, +0xd0, +0x10..+0x18, +0x170, +0x1bc,
+0xec; written: +0xec, +0x10..+0x18 (in `obj_moveAndCollide`), +0x44 (own draws).
Constants: `0x44fe08` level flags (`0x151774`, `0x15185c`), 2⁻¹⁶ `0x37800000` and 18.0
`0x41900000` (`0x152474`, `0x152484`), the divisor 3 (`0x15243c`), fx ids 0x11 / 2 / 8
(`0x15178c`, `0x1517bc`, `0x151888`), `0x532478` / `0x532538` (`0x15187c`, `0x1518b4`).

**Gravity**: none in any of the four classes (*Executed*: no run stores to the velocity
words, and the difftest compares every stored byte). Only `playerProjectile` (thrown
weapons) falls (`docs/spec/combat-projectiles.md` 4.3). An aimed plain arrow descends only
because the aim points down: from the origin (54 above a 72-high Skeleton's feet) to the
target's mid-height.

### 4.3 `obj_moveAndCollide` `0x1509f8`: ground and wall

*Executed* in every run (`docs/spec/combat-projectiles.md` 4.1 for the steps). Its only
world queries are `terrain_height` (twice or more: the position, then the back-off
candidates), `water_test` (once per object, byte +0x50) and `world_collectObjectsInBox`.
There is **no wall test**: a wall stops an arrow only as terrain (the height at the new
point above the arrow's z), and the scene's terrain wall was executed exactly like the ramp
(bit 1, back-off by tenths of the step, the stone hit, destroyed in the same run).

### 4.4 Touch, `MissileWeapon_onTouch` `0x152a18` (slot 6), monster owner

*Executed*. The order for a Skeleton's arrow (owner flags `0x20`, not `0x40`):

1. +0xcc ≠ 0 or no victim → nothing. The owner is read through +0x4c first.
2. Victim without the creature flag `0x20` (a prop): slot 0 (type-info) compared with
   `AutoContainer_typeinfo` `0x3c9558` then `Container_typeinfo` `0x3c3308`
   (`rtti_typeInfoEquals`); a container gets slot 2 `(0, 0; 0.0)`; +0xcc = 2 in every case.
   No enemy test, no draw.
3. Owner present with flag `0x20`: `owner.slot20(victim)` (`Skeleton_isEnemy`) must accept;
   0 → nothing, the arrow flies on (Executed: the ally cases).
4. Victim in the pierced list +0x124 → nothing (the list is always empty: only Penetrating
   Arrows fills it, a player's skill).
5. **Penetrating Arrows and the stick are skipped**: both need owner flag `0x40`
   (Observed `0x152ba0`–`0x152ba8` and `0x152c90`–`0x152c98`). So a monster's arrow never
   sticks, never pierces, never gets the 1/5/6 damage overrides. *Executed*: 0 runs with a
   stuck host +0x128 in all monster-owned cases of both seeds; the player-owned control
   group stuck in 11 and 5 cases and followed its host (§3).
6. Deflection chance: a player victim (`0x40`): `player_getSkillRank(slot, 2)` →
   `SkillDodge_getStat0Fraction(g_skillTable[2], rank)` × 100.0 (`0x42c80000`, `0x152e84`)
   truncated, the same for skill `0x53` (`0x152e9c`), the larger. A creature victim: its
   slot 36 (`Creature_slot36`, the boss level 4 / 10 / 0) asked twice; non-zero → Skill 2's
   slot 11 `(0, level, 0)`. **ONE SHARED DRAW**: deflected when `draw % 100 + 1 < chance`
   (`0x152f64`, `0x152f84`).
7. Deflected: `Player_blockSparks(player, 0)` for a player; three `item_parseDescriptor
   (0x532570 / 0x532580 / 0x532590, record, −1, 0)`; when +0x1c0 and +0x1c4 are both
   non-zero, `item_getResourceIndex` per record and, when no row's word equals +0x1c0,
   `pool_new(0x248)` + `PhProp_ctor4(block, pos, A, B, 1, 0x2a, 0; 1.0)` (`0x15317c`,
   `0x1531a0`, `0x1531bc`); then `obj_delete(this)`. The hit state stays 0, so a second
   object overlapped in the same frame is still touched (*Executed*: "deflected by
   creature, damage to player" in a crowd, destroyed in its run while on the delete list).
8. Not deflected, victim a creature: `damage_apply(victim, skeleton, +0xe4, +0xdc, +0xe0,
   +0xe8 (= 4), +0x12c (= 0), 0; float +0xd4, float +0xd8)`; result 1 → +0xcc = 3 for a
   player victim, 1 for a creature; otherwise 2.
9. An orphaned arrow (the Skeleton destroyed, +0x4c reads 0): step 3 is skipped (it hits
   anyone it overlaps) and `damage_apply` gets the arrow itself as attacker (*Executed*,
   orphan cases).

Draws per touch of a Skeleton's arrow: **one shared** (step 6) for every player or creature
victim that passed step 3, plus whatever `damage_apply` draws (a call-out here; executed in
`tools/difftest_combat.py`) and, on a deflection, `item_parseDescriptor`'s variant draws
(one each when the definition has variants, `docs/spec/items.md` §3; a call-out here).
None on a prop or an ally.

### 4.5 Lifetime of a Skeleton's MissileWeapon

| What happened in the run at frame F | +0xcc | +0xec | Ends (*Executed*) |
|---|---|---|---|
| hit the idle player, damage landed | 3 | F | this run (slot 1 with 3) |
| hit a creature, damage landed | 1 | F + 1 | next run, at its start |
| damage refused, or a prop / container touched | 2 | 0 | this run (spark fx) |
| terrain (ground or wall) | 0 | 0 | this run (stone hit) |
| deflected | 0 | unchanged | `obj_delete`: off the run list; the next flush calls slot 1 with 3 |
| nothing | 0 | F₀ + 300 | the run at frame F₀ + 300 |

### 4.6 Destructor, `MissileWeapon_dtor` `0x151454`

*Executed* (both from inside the run and after a deflection's `obj_delete`): table
`0x50e5a0`; `trail_release(+0x170)` when non-zero; `light_dtor(+0x174, 2)`; `handle_clear` of
+0x128, +0x124, +0xbc, +0xa4, +0x8c, +0x74, +0x5c; table `0x5120b8`; `handle_clear(+0x4c)`;
`GameObject_dtor(this, 0)`; with bit 0 of the argument a tail jump to `pool_free`
`0x150470` (`0x151518`). No draws.

## 5. The element arrows

The bodies are `tools/ref_skills_b.py`'s; their constants and fields are in
`docs/spec/skills-35-68.md` sections 43, 44 and 47 (with addresses). What this round adds
is the Skeleton's composition and the destructors.

### 5.1 What the Skeleton's arguments give

- Level = trunc(`g_levelMonsterLevel`). The constructors ask the speed (and FireArrow the
  radius) through Skill slot 12 with the owner and **cap 10** (`0x2d6370`/`0x2d6394`,
  `0x2d70e4`, `0x2daf24`): for a monster the level is limited to 10. The hit handlers ask
  damage through slot 13 with **cap 0**: no limit (Observed, `docs/spec/skills-35-68.md`
  S.9; *Executed* here for levels 1–40). ExplodeArrow, Skill 47 in the image: half edge 45,
  47, 50, 54 at levels 1, 3, 6, ≥ 10 and damage 2, 6, 12, 20, 24, 32, 50, 80 at levels 1, 3,
  6, 10, 12, 16, 25, 40 (computed with the executed slot-12 body on the image's Skill
  object).
- Level flight at the origin height: a Skeleton's element arrow can hit only what spans
  `z0 + 54` (with the arrow's own height 72 from `GameObject_ctor`: anything whose
  `z .. z + height` meets `54 − 72 .. 54 + 72` above the Skeleton's feet), and meets the ground
  only where the terrain rises to it.

### 5.2 Constructors `0x2d6238` / `0x2d6fb4` / `0x2daeb4`

*Executed* with the Skeleton's arguments. `Projectile_ctor(obj, copy of origin, skeleton, 0)`
(**one shared draw** in `GameObject_ctor`; owner handle +0x4c; radius 12), then: table;
Fire and Cold a light record at +0x70..+0xab (`light_link`; Fire radius 96.0 `0x42c00000`
at `0x2d62c4`, falloff `0x38e38e38` `0x2d62dc`; Cold 156.0 `0x431c0000` `0x2d703c`,
`0x382c598a` `0x2d7054`); skill +0xac (Explode +0x70); facing s16 +0x64; level +0x6c (Fire)
or +0x68 (Cold, Explode); radius +0x1c: Fire statistic 2 (slot 12), Cold 7.0 `0x40e00000`
(`0x2d70d4`), Explode 8.0 `0x41000000` (`0x2daf30`); velocity +0x54 = `(cos16 a, sin16 a, 0)
× statistic 1` (slot 12, cap 10); age (Fire +0x68, others +0x6c) = 0; ended +0x60 = 0;
`obj_runEveryFrame`; the launch sound (`res_find` + `sound_playOnObject(…; 1.0)`).
ExplodeArrow reads its owner back through +0x4c with no null test (an arrow built without
an owner would fault; the Skeleton always passes itself).

### 5.3 Runs `0x2d66ac` / `0x2d73c8` / `0x2db17c` (slot 4)

*Executed*. `+0x60` set → nothing (*Executed* by an extra call after the end in about one
element case in five; in the game the arrow is off the run list by then, Inferred from
`obj_delete`). Age + 1; `obj_moveAndCollide(this, copy of +0x54)` (the touch handler runs
inside); terrain bit → end(1) (Explode: explode(1)); age ≥ 601 (`slti 0x259` at `0x2d6724`,
`0x2d7448`, `0x2db208`) → end(0); otherwise the flying-frame presentation: Fire
`fx_impactPuffNearCamera(pos, velocity / 60, 1; radius, radius² × 0.021989 + 0.267)`
(`0x2d6748`, `0x2d6784`) and the light follows (`light_relink`); Cold the light and 8
particles, Explode 6 particles. An arrow that meets nothing ends in run 601 after 601
moves (*Executed*: "expiry" rows, 601.0 runs).

**Draws per flying frame** (own generator +0x44 only; never the shared seed, never the
cosmetic one): Fire 0; Cold 8 particles × two unit-ball samples (≥ 48 draws); Explode 6 ×
(a unit-ball sample + 1). *Executed*: the means of §3's draw table.

### 5.4 Hit handlers `0x2d685c` / `0x2d7aac` / `0x2db4f0` (slot 6), monster owner

*Executed*.

- **Fire**: owner handle +0x4c empty → nothing. `s` = slot 13 (stat 0, level, &+0x4c, cap 0);
  **ONE OWN DRAW** r; owner (no flag `0x40`): `owner.slot20(victim)` must accept, then
  `damage_apply(victim, skeleton, 100000, 0, 0, 0x60, descriptor {(0x15, s, s, 0)}, 0; s,
  s + trunc(s × 0.2 × r / 65536))` (0.2 `0x3e4ccccc` at `0x2d6900`, 0x60 at `0x2d6910`,
  2⁻¹⁶ at `0x2d6944`); end(2). **No hit-state test**: every object overlapped in the same
  frame is damaged (*Executed*: "damage to creature+player" in crowds). There is no
  creature test on the monster path: whether a prop is damaged is the owner's slot 20's
  answer for it (the scripted world said no; what `Skeleton_isEnemy` says of a prop was not
  part of this test).
- **Cold**: no owner → nothing; `owner.slot20(victim)`; `fx_spawn(10, pos)`; `s` = slot 13
  (stat 0, cap 0); **ONE OWN DRAW**; `damage_apply(victim, skeleton, 100000, 0, 0, 0x40, 0,
  0; s, s + spread)` (no descriptor); a victim with flag `0x20` (the player too):
  `Creature_setEffectTimer(victim, 1, skeleton; +0x344 + float(stat 3 (cap 10) / 2))`;
  end(2).
- **Explode**: explode(2), whatever was touched (no test at all; the owner is never
  touched because `obj_moveAndCollide` skips it).

### 5.5 End functions `0x2d6bb8` / `0x2d7ecc` / `0x2db50c`

*Executed*, once per arrow (guard +0x60; the second call in a crowd frame returns at once,
*Executed*). Fire: reason ≠ 0 → impact sound; `obj_delete`; +0x60 = 1. Cold: reason 1 adds
a ground burst of level × 10 + 27 particles; reason ≠ 0 the level × 10 pairs and the
sound; `obj_delete`; +0x60 = 1. Explode: reason 0 → only `obj_delete` (no explosion on
expiry); otherwise **ONE OWN DRAW** for the sound name (stone, or ice on level flag
`0x40000`), `fx_ringBurst`, `pool_new(0xbc)` + `LightEffect_ctor` (a GameObject: **ONE SHARED
DRAW** when the pool gives a block), `camera_shake(0; level / 2)`; with an owner: the cube of
half edge statistic 2 (cap 10) through `world_collectObjectsInBox` (limit `0x80`,
`0x2db864`); the owner itself only gets a zero-damage knock call from the arrow when within
half the edge (3-D; *Executed* only in the scenes where the Skeleton stands up on the
wall's foot, 15 below the arrow: from the release the arrow is 54 above the Skeleton's
feet and the half edge is at most 27, so a Skeleton on flat ground is never knocked);
a creature the owner's slot 20 rejects is skipped; everything else **ONE OWN DRAW**, the
knock call (attacker the arrow, flags by level: < 6 none, 6–11 `0x40000`, ≥ 12 `0x80000` or
`0x40000` on an odd own draw for a monster, `0x2db790`–`0x2db7e4`) and
`damage_apply(object, skeleton, 100000, 0, 0, 0x840, 0, 0; s, s + spread)`.

### 5.6 Destructors `0x3cde04` / `0x3cdf4c` / `0x3ce30c` (slot 1) — new

*Executed* (every element case ends with one, argument 3):

```
Fire / Cold (132 bytes each, the same code):        Explode (108 bytes):
  +0x48 = own table (0x518de0 / 0x518ef8)             (no light)
  light_dtor(+0x70, 2)
  +0x48 = 0x5120b8 (Projectile)                       +0x48 = 0x5120b8
  handle_clear(+0x4c)       (the owner handle)        handle_clear(+0x4c)
  GameObject_dtor(this, 0)                            GameObject_dtor(this, 0)
  argument bit 0: tail jump to pool_free 0x150470     argument bit 0: tail jump to pool_free
```

Table stores at `0x3cde24` (Fire, value from `0x3cde08`/`0x3cde14`), `0x3cde48` (`0x3cde38`/
`0x3cde3c`); `pool_free` jump `0x3cde6c` (Fire), `0x3ce35c` (Explode). No draws. Not
executed: the return without bit 0 (`0x3cde74`–`0x3cde88`, `0x3cdfbc`–`0x3cdfd0`,
`0x3ce364`–`0x3ce378`): every caller met passes 3 (the run's slot 1, the flush).

## 6. Draws, all four arrows (shared `0x404464` / own +0x44 / cosmetic `0x404460`)

| Arrow | Construction | Each flying frame | Touch | End |
|---|---|---|---|---|
| MissileWeapon | 1 / 0 / 0 | 0 / 0 (1–2 on a cold level) / 0 | 1 per player or creature victim past the enemy test (+ `damage_apply`'s; + 3 × `item_parseDescriptor`'s on a deflection) / 0 / 0 | 0 |
| FireArrow | 1 / 0 / 0 | 0 / 0 / 0 | 0 (+ `damage_apply`'s) / 1 / 0 | 0 |
| ColdArrow | 1 / 0 / 0 | 0 / ≥ 48 / 0 | 0 (+ `damage_apply`'s) / 1 / 0 | 0 / bursts / 0 |
| ExplodeArrow | 1 / 0 / 0 | 0 / ≥ 24 / 0 | — (explodes) | 1 (LightEffect) / 1 + 1 per object + 1 for a monster of level ≥ 12 / 0 |

*Executed* (the counts match the original's seed and the original's +0x44 in every call;
the cosmetic generator was never touched: 0.00 per case in both seeds).

## 7. What a probe must supply for a Skeleton's arrow to fly and hit the idle player

1. **A block**: `pool_new(0x1c8 / 0xb0 / 0x74)` must return a zero-filled block (the probe's
   default refuses, so no arrow exists; `--pool` gives blocks). A refused block means no
   arrow and no draw.
2. **The Skill objects** for the element arrows (and for any deflection roll on a creature):
   the constructors call slot 12 of `g_skillTable[43 / 44 / 47]` through its `+0x60` table,
   the hit handlers slot 13; `MissileWeapon_onTouch` calls `SkillDodge_getStat0Fraction`
   on `g_skillTable[2]` and `[0x53]` (player victim) and slot 11 of `g_skillTable[2]` (boss
   creature victim). A world without them faults on the first virtual call; this difftest
   builds them with the executable's own initialisers `0x16ac74(1, 0xffff)` and `0x1ebca0()`.
3. **Running the arrow**: `obj_runEveryFrame` puts it at the front of the every-frame list;
   the probe must call its slot 4 (`0x15153c`, `0x2d66ac`, `0x2d73c8`, `0x2db17c`, from the
   table at +0x48) every tick from the next tick on, and honour `obj_delete` (the element
   arrows, a deflected MissileWeapon) by calling slot 1 with 3 at the next flush, and the
   MissileWeapon's own slot 1 call inside its run (the block is free at once).
4. **The flight**: `obj_moveAndCollide` `0x1509f8` real; `terrain_height` the ground (the
   probe's flat 0 is enough: the arrow flies at 54 above a Skeleton standing at 0, a plain
   arrow descends towards the target's mid-height and, if it misses, meets the ground about
   three times the target distance away); `water_test` 0.
5. **The touch dispatch**: `world_collectObjectsInBox` must return the idle player when the
   arrow's box (±radius in x, y, ±height +0x20 in z around the arrow) meets the player's
   extent: the player stand-in needs a real radius +0x1c and height +0x20, object flags
   `0x60` without `0x201`, `0x20000000` or the prediction-copy bit `0x20000`, and a table
   whose slot 6 is `Player_onTouch` `0x1beaf0` (executed). The Skeleton must be in the same
   answer or not (it is skipped as the owner). The owner's slot 20 (`Skeleton_isEnemy`
   `0x2a7e04`, executed) must accept the player (team bytes).
6. **The hit**: for the plain arrow `player_getSkillRank` (service, 0) and
   `SkillDodge_getStat0Fraction` (executed, needs item 2), one shared draw, `damage_apply`
   (executed), then the arrow destroys itself in the same run (`MissileWeapon_dtor`,
   `GameObject_dtor` executed; `light_dtor`, `trail_release`, `pool_free` services). For
   Fire: slot 13 of the Skill, one own draw, `damage_apply`, `obj_delete`. For Cold:
   additionally **`Creature_setEffectTimer` `0x118950`** on the player (flag `0x20`): not
   executed by any difftest - the first unexecuted body a cold arrow meets. For Explode:
   **`LightEffect_ctor` `0x201bd8`** (not executed; a GameObject with one shared draw) and
   `fx_ringBurst` `0x1f3d00`, `camera_shake` `0x1ebae0` (presentation, not in the probe's
   SERVICES yet).
7. **Presentation call-outs not yet in `SERVICES`**: `light_relink` `0x14a528` (Fire and Cold,
   every flying frame), `fx_impactPuffNearCamera` `0x1fc150` (Fire, every flying frame),
   `fx_ringBurst`, `camera_shake`. The type-info getters `AutoContainer_typeinfo` `0x3c9558`,
   `Container_typeinfo` `0x3c3308` and `PushPhysicsProp_typeinfo` `0x3c7bc8` (a plain arrow
   touching a prop) are C++-runtime getters like the ones the probe already runs for real.

## 8. Not executed

- `MissileWeapon_run` kinds 1, 2, 5, 6 (`0x151978`–`0x1523b4` and the sound arms
  `0x1516c0`–`0x151744`), kind 3, a non-zero spin (`0x151664`) or impact sample
  (`0x151954`): no Skeleton arrow has them. The stuck branch's "host without creature flag"
  delay slot `0x1515c4`.
- `MissileWeapon_ctor` kinds 1–6, an item (`0x151174`–`0x1512dc`), a launch sample
  (`0x1513f8`): not on the Skeleton's arguments.
- `MissileWeapon_onTouch`: kinds 1/3/5/6 arms, the pierced-list walk (`0x152b78`–`0x152b98`,
  a player's skill), the null-victim type-info throw (`0x152d38`), the `PushPhysicsProp` arm
  after the deflection test (`0x153278`–`0x1532bc`, unreachable as read: a non-creature
  returned at step 2), and delay slots of owner-without-creature-flag tests.
- `MissileWeapon_dtor` without bit 0 (`0x151520`–`0x15153c`); the destructors' same arm.
- Fire / Cold hit handlers' player-owner branches (`0x2d6974`–`0x2d6ac8`,
  `0x2d7b60`–`0x2d7d24`) and the descriptor "slot already in use" arms; Cold's second
  owner-null test `0x2d7b48` is unreachable (the same register was tested non-zero at
  `0x2d7ae4`).
- `GameObject_ctor` with a class definition or a property list (`0x14cbc4`–`0x14cf60`).
- `damage_apply`, `item_parseDescriptor`, `Creature_setEffectTimer`, `LightEffect_ctor`,
  `PhProp_ctor4` are call-outs here.

## 9. Corrections and sharpenings

| Where | Was | Is | Evidence |
|---|---|---|---|
| `docs/spec/skills-35-68-executed.md` §1 | "Not modelled for any id: … the destructors" | the three arrow destructors are executed | §5.6 |
| `docs/spec/combat-projectiles.md` §5.1 step 7 / §6 | a deflected missile is `obj_delete`d | and, since the hit state stays 0, the same run can still damage a second overlapped object and then destroy the arrow through slot 1 while it is on the delete list | Executed, crowd cases |
| `docs/spec/combat-projectiles.md` §4.2 | (not said) | a stuck arrow (player owner only) has no expiry; it is destroyed only through its host (handle cleared → +0xcc set → slot 1) or `obj_delete`d when the host has creature flag bit 41 | Executed, control group |
| `docs/spec/skills-35-68.md` 47 | (not said) | a Skeleton's exploding arrow never knocks the Skeleton on flat ground: the arrow flies 54 above its feet, the knock needs a 3-D distance below half the edge (≤ 27) | Executed / Inferred from the geometry |
