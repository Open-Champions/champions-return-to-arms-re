# Combat runtime, round 2: projectiles and ranged attacks

US `SLUS_209.73` v2.00. Round 2 of `docs/combat-runtime.md` (round 1, commit 9289d56):
how arrows, bolts and thrown weapons are made, fly, touch, damage and end in the one
shared world of that contract. It is the prose of `tools/ref_combat_ranged.py`, which adds
the projectile bodies to round 1's `CombatModel` and a `RangedRuntime` in which projectiles
live beside players and creatures. Round 1's APIs and test vectors are unchanged; this
module only subclasses them.

Evidence labels as in round 1: **Executed** = the original instructions were run one
function at a time in `tools/ee_emu.py` (an instruction interpreter, not a console) on
constructed state and agreed with the model (the test is `tools/difftest_combat_ranged.py`
unless another is named); **Observed** = read at the address given; **Inferred**;
**Unknown**; **Authored** = a choice of this contract (fixture, refusal, driver). Nothing
here was run on a console, in PCSX2 or on the live rig.

## 1. The contract in brief

1. **Every arrow and bolt a player or a monster shoots is a `MissileWeapon`** (class table
   0x50e5a0, block 0x1c8); a thrown weapon is a `playerProjectile` (table 0x50e470, block
   0x1d0) built on the same constructor and touch handler. Both come from `pool_new`, so a
   projectile's identity is its pool address like any object's; both blocks are in the
   large size class that creatures use, so a destroyed arrow's block is the next block a
   creature or arrow gets (*Executed* in the contract: `test_destroyed_missile_block_is_
   reused_by_the_next_large_object`, on ref_objects' executed pool).
2. **Construction makes one shared draw** (`GameObject_ctor` inside `Projectile_ctor`
   0x150e48) and links the projectile to the **front of the every-frame list**
   (`obj_runEveryFrame`, 0x1513e0), so a projectile made during a tick runs first in the
   next tick and is not run by the walk in which it was made (*Executed*; list rule of
   round 1 section 3).
3. **Flight is `obj_moveAndCollide` 0x1509f8**, one call per run: position += velocity /
   60, a terrain test with a back-off, then ONE box query and, for every overlapping object
   in box order, **the hit object's slot 6 and then the projectile's own slot 6**; no
   break, no prediction-copy guard (*Executed*, 3,000 cases; section 4).
4. **The hit-once rule is the projectile's hit state +0xcc**: `MissileWeapon_onTouch`
   0x152a18 returns at once when it is non-zero, and the first accepted victim sets it, so
   of several enemies overlapping in one frame only the first in box order is hit - unless
   Penetrating Arrows makes the arrow pierce, which clears +0xcc again and remembers the
   victim in the list +0x124 (*Executed*; section 5).
5. **Damage is `damage_apply` inside the projectile's run** (from within its touch
   handler), with the **owner** as attacker - or the projectile itself when the owner
   handle has gone to 0 (*Executed* 0x1531e0-0x15324c). So a hit lands during the
   projectile's run and the victim reacts in its own run, exactly round 1's item 4.
6. **A projectile destroys itself** with its own slot 1 (argument 3) inside its run - not
   `obj_delete` - so handles to it read 0 and its block is free the moment it ends
   (*Executed*: `MissileWeapon_run` 0x15157c-0x152510, `playerProjectile_run` 0x1bb368). The
   one deferred case is a deflected missile (`obj_delete`, 0x1531c8). Round 1's "death never
   removes an object at once" holds for creatures and players; projectiles are the
   exception.
7. **Lifetime** (section 6): a hit on a creature ends the arrow in the next tick (expiry
   = frame + 1) unless it sticks; a hit on a player, a non-creature, the terrain or a
   refused damage ends it in the same run; nothing hit ends it after 300 frames.
8. **Shared draws on a missile touch**: two (Penetrating Arrows) when the owner is a player
   and the kind is 0 or 3, then one deflection roll for every creature or player victim
   that got past the enemy test, then `damage_apply`'s own (*Executed*; section 5.2). All
   happen in box order inside the projectile's run, so the box order fixes the seed.

## 2. The classes and who makes them

| Class | Table | Size | Made by (call sites of `MissileWeapon_ctor` 0x150ee4, Observed) | In this contract |
|---|---|---|---|---|
| `MissileWeapon` | 0x50e5a0 | 0x1c8 | `Player_run` state 0 bow release 0x1a9240 (and 0x1a9344, 0x1a944c in the older arrow kinds); `SkillMultiFire_cast` 0x2d9fc4; the monster run functions of Clockwork 0x24f07c, CloudGiant 0x251ca8, MaleDarkElf 0x25cb64 / 0x25cc5c, Froglock 0x264e18, Goblin 0x26c1a4, Gremlin 0x26ece0, IronGuardian 0x27ac04, Orc 0x2a278c, Skeleton 0x2a7388, WoodElfSoldier 0x2bd710 and `WoodElfSoldier_trigger` 0x2bdae8; the traps `Shooter_run` 0x1f5158 and `MissileTrap_run` 0x1f3ccc; an unnamed function 0x3cb730 (call 0x3cb7f8); the LavaBomb built inline in `LavaMonster_run` 0x281480 | Executed: kinds 0 and 3 run; every kind constructs and touches |
| `playerProjectile` | 0x50e470 | 0x1d0 | `Player_run` state 0 throw (via `playerProjectile_ctor` 0x1bef58); the thrown-axe skills (`docs/spec/skills-69-101.md` 98, 99) | Executed: kinds 0 and 4.. (weapons); 1-3 (potions) refused |
| `beetleProjectile` | 0x50e3d8 | 0x1d0 | `beetleProjectile_ctor` 0x247884 (calls `MissileWeapon_ctor`) | not read |
| `AnimatedMissile`, `DummyDamager`, `LavaBomb`, `DiseaseProjectile`, `PoisonProjectile`, `JunkProjectile`, `HateProjectile`, `LightningBolt`, `HolyBolt`, `OniBall`, `IceBall`, the skill arrows (`FireArrowProjectile` ...) | see `symbols/objects.tsv`, `symbols/monsters*.tsv` | | own constructors, runs and touch handlers | not read in this round |

**Monster arrows** (Observed at each call site listed, 0x24f014-0x2bdaec): kind 0
(`a1` = 0), no launch or impact sample, weapon rating 0, item flags 0, **no item** (so
`damage_apply` gets an empty descriptor), damage minimum from the creature's +0xd0,
attack rating from its +0xd4; the maximum from +0xd2 or a register computed before the
call, and damage flags 4 in the Orc call (0x2a2754; the other sites pass a register, value
*Unknown* without reading each). Position and velocity are each class's own (MaleDarkElf:
`docs/spec/skills-35-68.md` S.9). The **owner** is the monster.

**The player's bow arrow** (Observed, 0x1a9188-0x1a9244): kind `P+0x480`; models from the
item model table rows 0x3e9ce8/0x3e9cec; launch and impact sample 0; damage minimum and
maximum record +0xd0/+0xd4 (ability record +0x26/+0x28 for a non-zero kind); weapon rating
and item flags of the bow; attack rating record +0xcc; damage flags the item definition's
+0x20 (bit 4 cleared for a non-zero kind); **the bow item as damage descriptor**; facing
`spread - 0x4000`; owner the player. Real player only (the prediction copy makes no
missile, `docs/spec/player-tick.md` state 0).

**When the shot leaves** (from `docs/spec/player-animation-dispatch.md` 4 and
`docs/spec/creature-animation-dispatch.md` 4.3 on `t3/research-anim`, Observed there):
the player releases on a frame count, `since == trunc(base / speed)` with base 22 (11 for
a throw), halved in a net game; a creature releases on the event bit 0x1 of its attack
clip. So an inactive creature, whose animation does not advance, never shoots - round 1's
item 3 applies to archers too (*Inferred* from the two executed pieces).

## 3. Construction

`MissileWeapon_ctor` 0x150ee4 takes (obj, kind, model A, model B, pos*, vel*, facing,
owner) in registers and nine words on the stack: launch sample, impact sample, damage
min, damage max, weapon rating, item flags, attack rating, damage flags, item
(*Executed*, `missileCtor`, 348 of 348 instructions). The field table of
`docs/spec/skills-35-68.md` S.8 is right; executed additions:

- Order: `Projectile_ctor(obj, pos, owner, 0)` (GameObject_ctor - one shared draw -, flags
  |= 0x4081, owner handle +0x4c, radius 12, +0x50 = 0); table 0x50e5a0; five handle words
  at +0x5c, +0x74, +0x8c, +0xa4, +0xbc zeroed (released by the destructor; their use is
  *Unknown*); the light record at +0x174 filled and linked (`light_link`); kind-dependent
  launch sound for kinds 1, 2, 5, 6; the light unlinked again for kinds 0 and 3.
- The item test reads the item's four modifier slots (+0x24 + 8k) for the ids 0x18, 0x16,
  0x15, 0x17, 0x26 **in that order**, taking for each id the first slot that carries it;
  a non-zero value of any of them means "elemental": no trail, +0x170 = 0. A weapon class
  6 definition (+0x1e) gives radius 24 and height 100.
- The trail (`trail_create`, presentation) only for kind 0, no elemental modifier and level
  flag 0x100 clear. Otherwise the constructor does not write +0x170 and the word keeps
  `pool_new`'s zero (pool_new zero-fills, `docs/spec/object-system.md` 2).
- Expiry +0xec = frame + 300; `obj_runEveryFrame`; +0xcd = 1; launch sample voice at +0xf0
  (presentation); impact sample at +0x1bc.

`playerProjectile_ctor` 0x1bef58 (obj, model A, model B, pos*, vel*, facing, owner, launch;
stack: impact, dmin, dmax, weapon rating, item flags, attack, kind, item) calls
`MissileWeapon_ctor` with **kind 0 and damage flags 4**, then +0x1c8 = 0, spin +0x1cc =
2000 (**-2000 for kind 0**), table 0x50e470, kind byte +0x1ce, and links the owner a second
time at +0x1c8 (*Executed*, `thrownCtor`, 84 of 84).

## 4. Flight

### 4.1 `obj_moveAndCollide` 0x1509f8 (obj, vel) -> bits

*Executed* (`moveAndCollide`, 3,000 cases, 275 of 276 instructions; the one missed is a
likely-branch delay slot). The reading of `docs/spec/skills-35-68.md` S.7 is confirmed in
every detail:

```
step = vel x (1/60)  (0x3c888888, per component);  pos += step;  obj_updateGridCell
if z < terrain_height(world, pos; radius):                     bit 1
    k = 0.1; repeat: cand = pos - step x k;  stop when terrain_height(cand) <= cand.z;
                     k += 0.1 while k < 2.0
    pos = cand (the last candidate, found or not)
    first time only (+0x50): water_test(pos; 12) -> +0x50 = 1, ONE OWN DRAW, splash sound,
                     water_disturb(700, 24)
box (pos +- radius, +- radius, +- height +0x20), limit 0x100; owner = handle +0x4c
for o in box order:
    skip flags & 0x201, flags & 0x20000000, o == obj, o == owner
    skip when o's top < obj.z - h or obj.z + h < o.z
    if (dx² + dy²) < (r + o.r)²:  bit 2;  o.slot6(obj);  obj.slot6(o)
return bits
```

The position is never rewound after an object overlap; the loop does not look at what the
handlers did (a handler that destroys or deletes the projectile mid-loop leaves the loop
reading the dead object's fields: `MissileWeapon_onTouch` only `obj_delete`s, so the
object is still intact - *Inferred* from the executed bodies). The box query never returns
the prediction copy (flag 0x20000, round 1 section 3), and the function has no copy test.

### 4.2 `MissileWeapon_run` 0x15153c (slot 4)

*Executed* for kinds 0 and 3 (`missileRun`, 3,000 cases with the real `obj_moveAndCollide`,
the real `MissileWeapon_onTouch` as the missile's slot 6 and the real `obj_updateActive`).
Kinds 1, 2, 5, 6 make particles and `LightEffect`s on impact (0x151978-0x1523b4) and are
refused (*Observed* only).

```
stuck (+0x128 set):  +0xcd = obj_updateActive(this, +0xcd, 480)
                     host flag 0x20 and creature flag bit 41: obj_delete(this); return
                     model = host.slot16(); if model: +0x10 = sample point +0xf4 of the host
                     obj_updateGridCell; return                       (no expiry test)
+0xcc != 0:          slot1(this, 3); return                           (destroyed now)
spin +0xfa: +0xfc += +0xfa
r = obj_moveAndCollide(this, velocity +0x1b0)       (no gravity: the velocity never changes)
res = (r & 1) | (+0xcc != 0 ? 2 : 0)                (an overlap counts only if a handler hit)
res != 0: +0xec = 0
    res 2 (kinds 0, 3): +0xcc 2 -> spark fx;  3 -> +0xec = frame;  1 -> +0xec = frame + 1
    res 1: impact fx (8 on level flag 0x40000, 0x11 on 0x100, else 2), impact sound,
           impact sample +0x1bc
kind 0: with level flag 0x100 one OWN DRAW, and when it is divisible by 3 a second own draw
        for a puff (in place of the trail point); otherwise the trail point when +0x170 set
kind 3: the trail point when +0x170 set
frame >= +0xec: slot1(this, 3)
```

Executed correction: the trail point of kind 0 is added **on every run that reaches the
end**, hit or not (S.8 had it only for the no-hit case).

### 4.3 `playerProjectile_run` 0x1ba940 (slot 4)

*Executed* for kinds 0 and 4 and above (`thrownRun`, 3,000 cases). Kinds 1-3 (fire, gas and
exploding potions) are refused: kind 1 draws the shared seed every frame for its flame
particles (0x1ba990-0x1babf0) and all three make objects at the end.

```
spin: kind 0 +200 while below 5000; kinds 4..6 +3000 (wrapping); others -200 while above -5000
velocity.z -= 8.999999                 (the only gravity in this round: thrown weapons fall)
r = obj_moveAndCollide(this, velocity);  res as in 4.2
res != 0: +0xec = 0; res 1: impact fx 2 at (pos.x, pos.y, terrain_height + 5) for kinds 0, 4,
          5, 6, and the impact sound
frame >= +0xec: slot1(this, 3)
```

A thrown weapon that hits anything ends in that run: unlike the arrow it has no stuck
state and no "frame + 1" (`playerProjectile_run` does not test +0x128 or +0xcc before
moving).

## 5. Touches and damage: `MissileWeapon_onTouch` 0x152a18 (slot 6)

*Executed* (`missileOnTouch`, 3,000 cases, 553 of 575 instructions; the missed ones are
the bad-typeid throw for a null victim and a path that needs a victim to lose its
creature flag between two reads, both unreachable as far as read). It is the touch handler
of both classes.

### 5.1 The order

1. +0xcc non-zero, or no victim: nothing. The owner is read from +0x4c first.
2. Victim not a creature (flag 0x20 clear): an `AutoContainer` or `Container` victim gets
   slot 2 with (0, 0; 0.0); in every case +0xcc = 2. **No enemy test, no draw.**
3. Owner present and a creature: `owner.slot20(victim)` must accept, else nothing (the
   arrow passes through and keeps flying).
4. Victim already in the pierced list +0x124: nothing.
5. Owner a player and kind 0 or 3: Penetrating Arrows (skill 93) rank of the owner, its two
   fractions u and p; **shared draw** -> unblockable when `draw / 65536 <= u`; **shared
   draw** -> pierce when `<= p`, else the pierced list is cleared. At rank 0 both are 0.0
   and each test still passes when the draw is exactly 0.
6. Victim a creature and owner a player: a player victim only in PvP mode A; a victim with
   flag 0x1000000 that is not a player: nothing. Then, not piercing and kind 0, **the arrow
   sticks**: +0x128 linked to the victim, +0xf4 = slot 17 (the nearest strong sample point,
   section 5.3); dropped again when that index is 0 or the victim is a `Skeleton`;
   otherwise a local orientation +0x100 from four matrix helpers (presentation). In every
   case of this branch the arrow's own flag 1 (not solid) is set. Kinds 1, 5, 6 set damage
   flags 0x20 / 0x400 / 0x80 and attack 10000.
7. Deflection chance c: a player victim - the larger of its Dodge-type fractions of skills
   2 and 0x53 x 100 (truncated); a creature victim - when its slot 36 is non-zero, skill 2's
   slot 11 at that level; else 0. **Shared draw**: deflected when `draw % 100 + 1 < c`:
   block sparks on a player, three `item_parseDescriptor` calls, a dropped `PhProp` when the
   missile's model A is not one of the three potion models, `obj_delete(this)`.
8. `damage_apply(victim, attacker = owner or else the missile, attack +0xe4, +0xdc, +0xe0,
   flags +0xe8 | (unblockable ? 0x40 : 0), descriptor +0x12c, 0; float(+0xd4),
   float(+0xd8))`. Result 1: +0xcc = 3 for a player victim, 1 otherwise; result 0: 2.
9. Piercing and +0xcc set: the victim joins +0x124 and +0xcc = 0 again.

### 5.2 Consequences for several actors

- **One victim per missile per frame** in box order, unless piercing (step 9 re-arms the
  arrow inside the same box loop, so a piercing arrow can hit every enemy it overlaps in
  one frame, each once) - *Executed* (`test_one_hit_per_missile_when_two_enemies_overlap`
  in the contract; the per-call rule in the difftest).
- **No friendly fire while the owner lives**: the owner's slot 20 is asked first (step 3);
  a player object carries flag 0x20 too, so for a player's arrow that is `Player_isEnemy`
  (another player refused outside PvP mode A; step 6 repeats the PvP test) and for a
  monster's arrow `Creature_isEnemy` (team bytes). *Executed*
  (`test_monster_arrow_passes_through_a_non_enemy` for the monster case).
- **An orphaned missile hits anyone and is its own attacker**: when the owner was destroyed
  (a monster archer deleted while its arrow flies) +0x4c reads 0, step 3 is skipped and
  `damage_apply` gets the missile as attacker (*Executed* for the call; what `damage_apply`
  makes of a projectile attacker - kill credit, the 0x80 owner rule - is *Unknown*; the
  contract refuses it).
- **Thrown weapons go through the same rules**, Penetrating Arrows included: they are
  constructed with kind 0 at +0xd0 (*Executed*, `thrownCtor`), so steps 5 and 6 apply; a
  thrown weapon that "sticks" is still destroyed in its run because `playerProjectile_run`
  never follows +0x128 (*Executed* run; that the stick link is then just released by the
  destructor is *Inferred*).
- **Draw count per touch** (shared seed): 2 x [player owner, kind 0 or 3] + 1 x [the victim
  reached step 7] + `damage_apply`'s. `test_shared_draws_of_a_player_arrow_hit` counts the
  three of the missile for an unskilled player.

### 5.3 Slot 17 0x153314 (this, victim) -> sample index

*Executed* (`missileSlot17`, 128 of 128): 0 without a victim, a model (slot 16) or sample
points; otherwise the largest weight w over all sample points, then the point nearest the
missile (3-D) among those with weight >= 0.75 w; ties to the first. Index 0 means "do not
stick" to step 6, so an arrow never sticks to sample point 0.

## 6. Lifetime and deletion timing

| What happened in the run at frame F | +0xcc | +0xec | Ends |
|---|---|---|---|
| hit a creature, damage landed, no stick | 1 | F + 1 | next run: destroyed at its start (slot 1) |
| hit a creature, stuck | 1 | F + 1 | follows the host's sample point every run; destroyed when the host is destroyed (its handle reads 0, then +0xcc != 0) or `obj_delete`d when the host has creature flag bit 41; **no expiry while stuck** |
| hit a player (damage landed) | 3 | F | this run |
| damage refused, non-creature touched | 2 | 0 | this run (spark fx) |
| terrain | 0 | 0 | this run |
| deflected | 0 | unchanged | `obj_delete`: off the run list now, destroyed in the next flush |
| nothing | 0 | ctor frame + 300 | the run at frame ctor + 300 |

Range: 300 frames x speed / 60 (5000 units at 1000 units per second). *Executed*
(`test_a_missile_that_hits_nothing_lives_300_frames`, `test_player_arrow_damages_at_once_
and_is_destroyed_next_tick`, `test_monster_arrow_on_a_player_is_destroyed_in_the_same_run`,
`test_terrain_hit_backs_off_and_destroys_in_the_same_run`, on the executed bodies).

### 6.1 The destructor chain

`MissileWeapon_dtor` 0x151454 (*Executed*, 57 of 58): table 0x50e5a0; `trail_release` when
+0x170; `light_dtor(+0x174, 2)`; `handle_clear` of +0x128, +0x124, then +0xbc, +0xa4, +0x8c,
+0x74, +0x5c; table 0x5120b8 (`Projectile`); `handle_clear(+0x4c)`; `GameObject_dtor(this,
0)`; `pool_free` when bit 0 of the argument is set. `playerProjectile_dtor` 0x3c6468
(*Executed*, 27 of 28): its table, `handle_clear(+0x1c8)`, then `MissileWeapon_dtor(this,
0)` and `pool_free`. The order of the `handle_clear` calls decides which handle nodes go
back to the node pool first (round 1 section 2.2).

## 7. What reads per-machine state on this path

- `fx_spawn` ids 2, 8, 0x11 return early unless near the camera focus (symbol note of
  0x1ef270): presentation only. Trails, lights, sounds and the stuck orientation +0x100
  are presentation (*Inferred*: nothing on the simulation path reads them).
- No prediction-copy test in any of the bodies; the guard is in the callers (only the real
  player builds a missile or a thrown weapon, `docs/spec/player-tick.md` state 0).
- The own draws (water splash, cold-level puffs) and the shared draws of section 5 are
  simulation state and happen on every machine that runs the missile.

## 8. In the contract (`RangedRuntime`)

- `spawn_missile(owner, pos, vel, ...)` / `spawn_thrown(...)` are **authored call sites**:
  `pool_new` of the class size and the executed constructor with the arguments a monster
  or the player passes (section 2). The rest - list position, flight, touch order, damage,
  self-destruction, the destructor chain, handle nulling, block reuse - is the executed
  bodies on round 1's shared image.
- Presentation call-outs (lights, trails, sounds, matrix helpers, block sparks, fx) are
  traced and ignored; `terrain_height` uses the runtime's terrain fixture.
- Refused (Unsupported): kinds 1, 2, 5, 6 in the arrow run and 1-3 in the thrown run; a
  deflection (it needs `item_parseDescriptor` with a random variant and a `PhProp`); a
  missile as attacker; a weapon item as damage descriptor (round 1 refuses descriptors;
  monster arrows have none); Penetrating Arrows or Dodge above rank 0; water.
- Not composed: the player's own bow release (`Player_run` state 0 needs
  `world_collectObjectsInArc`, attach points and the inventory, none modelled here); the
  monster run functions that shoot.

## 9. What was run

- `python3 tools/difftest_combat_ranged.py local/SLUS_209.73` (seed 20973, 3,000 cases per
  entry point): see the table; `--seed 7 --quick` also passes.

| Entry point | Compared | Mismatches | Instructions executed |
|---|---|---|---|
| `obj_moveAndCollide` 0x1509f8 | 3,000 | 0 | 275 of 276 |
| `Projectile_ctor` 0x150e48 | 3,000 | 0 | 39 of 39 |
| `MissileWeapon_ctor` 0x150ee4 | 3,000 | 0 | 348 of 348 |
| `MissileWeapon_onTouch` 0x152a18 | 3,000 | 0 | 553 of 575 |
| `MissileWeapon` slot 17 0x153314 | 3,000 | 0 | 128 of 128 |
| `MissileWeapon_run` 0x15153c (kinds 0, 3) | 3,000 | 0 | 317 of 1,024 (the rest is kinds 1, 2, 5, 6) |
| `MissileWeapon_dtor` 0x151454 | 3,000 | 0 | 57 of 58 |
| `playerProjectile_ctor` 0x1bef58 | 3,000 | 0 | 84 of 84 |
| `playerProjectile_run` 0x1ba940 (kinds 0, 4..) | 3,000 | 0 | 171 of 674 (the rest is kinds 1-3) |
| `playerProjectile_dtor` 0x3c6468 | 3,000 | 0 | 27 of 28 |

  Compared: the calls with their arguments (strings by content, vectors by value), every
  byte stored outside the stack, the shared seed, the result. Real besides the entry:
  `GameObject_rand`, the C library (sprintf's stores into its own reentrancy block are not
  compared), and in the run entries the real `obj_moveAndCollide`, `MissileWeapon_onTouch`
  and `obj_updateActive`; in the constructors and destructors the base bodies.
- `python3 -m unittest tools/test_ref_combat_ranged.py`: 18 synthetic-fixture tests
  (flight, lifetime, gravity of thrown weapons, terrain back-off, damage timing for
  creature and player victims, touch order, one hit per missile, no friendly fire for a
  monster arrow, the missile's shared draws, block reuse, the orphaned missile; the bodies
  on a bare image).
- Not run: anything on a console, PCSX2 or the live rig.

## 10. Corrections and additions

| Where | Was | Is | Evidence |
|---|---|---|---|
| `docs/spec/skills-35-68.md` S.8, `MissileWeapon_run` | trail point only when nothing was hit | the kind-0 tail (trail point or cold-level puff) runs on every run that reaches the end, hit frames included | Executed 0x152418-0x1524d8 |
| `docs/spec/skills-35-68.md` S.8 step 6 | the stick link, dropped for index 0 or a Skeleton | also: the missile's own flag 1 is set in every case of that branch | Executed 0x152e04-0x152e14 |
| `docs/spec/skills-35-68.md` S.8 | (not said) | the stick, Penetrating Arrows and the kind 1/5/6 overrides need a **player** owner; a monster's arrow never sticks | Executed 0x152b98-0x152e58 |
| `docs/spec/skills-35-68.md` S.8 step 8 | `+0xcc` 2 for result 0 | and for a non-creature victim that reaches step 8 only when its class is `PushPhysicsProp` (else unchanged); not reachable as read | Observed 0x153278-0x1532bc |
| `docs/combat-runtime.md` 1, item 5 | death never removes an object at once | true for creatures and players; a projectile destroys itself in its own run (slot 1 with 3) | Executed |
| `docs/combat-runtime.md` 5.3 | Observed only; not in the domain | Executed; in the domain of `RangedRuntime` | section 9 |
| `symbols/objects.tsv` 0x150ee4, 0x151454, 0x15153c, 0x152a18, 0x153314 | "body not read" | executed (proposed notes below) | section 9 |

Proposed symbol lines (for whoever edits `symbols/objects.tsv`; not changed here):

```
00150ee4	MissileWeapon_ctor	(obj, kind, modelA, modelB, pos*, vel*, facing, owner; stack: launch, impact, dmin, dmax, wrating, iflags, attack, dflags, item); executed (docs/spec/combat-projectiles.md 3)
00151454	MissileWeapon_dtor	slot 1: trail, light, handles +0x128, +0x124, +0xbc..+0x5c, +0x4c, GameObject_dtor; executed
0015153c	MissileWeapon_run	slot 4: stuck follow, self-destroy on +0xcc, obj_moveAndCollide, expiry +0xec; executed for kinds 0 and 3
00152a18	MissileWeapon_onTouch	slot 6 of MissileWeapon and playerProjectile: hit state +0xcc, owner enemy test, Penetrating Arrows (2 shared draws), stick, deflection (1 shared draw), damage_apply with owner or self; executed
00153314	MissileWeapon_nearestSamplePoint	slot 17 (this, creature): nearest sample point among those with weight >= 0.75 of the largest; 0 = none; executed (was MissileWeapon_slot17)
001509f8	obj_moveAndCollide	(obj, vel*) -> 1 terrain, 2 overlap: step 1/60, terrain back-off in tenths, box query, slot 6 of the hit object then of the mover; no copy guard; executed
001ba940	playerProjectile_run	slot 4: spin, gravity 8.999999, obj_moveAndCollide, destroyed on any hit; executed for kinds 0, 4..; kinds 1-3 (potions) not modelled
```

## 11. Not done, not known

- The impact branches of arrow kinds 1, 2, 5, 6 and the potion kinds 1-3 (effect objects,
  shared draws of kind 1 every frame).
- The other projectile classes of section 2's last row, and the monster run functions
  that aim and release (only their constructor arguments are read).
- `damage_apply` with a projectile as attacker; the five handle words +0x5c..+0xbc.
- `Player_run` state 0 composed into the runtime (it needs `world_collectObjectsInArc`).
- Deflection in the runtime (the variant draws of `item_parseDescriptor`, the `PhProp`).
