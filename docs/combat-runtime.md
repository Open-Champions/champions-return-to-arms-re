# Combat runtime: several live actors in one world

US `SLUS_209.73` v2.00. This document is for a rebuild (the native C++/Godot client in
particular) that must let **more than one live actor** share one world while they fight:
one memory, one identity scheme, one grid, one contact loop, one damage path, and the
order in which the original calls each service. It is the prose of
`tools/ref_combat_runtime.py`, which composes the existing executed models
(`tools/ref_objects.py`, `tools/ref_creature.py`, `tools/ref_arena_monsters.py`,
`tools/ref_combat.py`, `tools/ref_player.py`) on one shared memory image and adds the
bodies that none of them had.

Evidence labels, as everywhere in the project: **Executed** = the original instructions
were run one function at a time in `tools/ee_emu.py` (an instruction interpreter, not a
console) on constructed state and agreed with the model; the test is named. **Observed** =
read at the address given. **Inferred**. **Unknown**. **Authored** = a choice of this
contract (a fixture, a refusal, a driver), not a statement about the game. Nothing here
was run on a console, in PCSX2 or on the live rig.

## 1. The contract in brief

1. **Identity is the pool address; references that outlive a call are handles.** A handle
   word holds a node of the one handle pool (6,096 nodes at 0x847268); node +0xc is the
   object. Destroying an object clears its head +0, which unlinks every node that pointed
   at it, so every handle word to it reads 0 from then on. Freed blocks are handed out
   again last-in first-out, so the next object of the same size class gets the address of
   the last one destroyed. *Executed* (ref_objects / ref_core; and in this contract's
   tests, section 11).
2. **Lists link at the front and are walked front to back**, so the actor linked last runs
   first. A player is linked to the every-frame list by its constructor; a summoned
   Skelight too; level monsters that join a 60-frame list in their constructor
   (`docs/spec/object-system.md` 2.3) move to the every-frame list when they become active. *Executed* (ref_objects, `docs/spec/object-system.md` 5).
3. **Inactive creatures do not animate**, so their attack events never fire and a swing
   never ends: no activity centre (no player, camera not used) means no melee from
   monsters at all. *Executed* (ref_creature `Creature_stepAnim`; contract test
   `test_an_inactive_swing_never_lands`).
4. **A hit is applied at once and reacted to later.** `damage_apply` calls the victim's
   virtual slot 2 inside the attacker's run: a creature loses hit points there and then;
   a player only accumulates pending damage. The reaction - knock-back speed, hit
   reaction state, death - happens in the **victim's own** pending-damage function, on its
   next run: later in the same tick when the victim runs after the attacker, in the next
   tick when it ran before. *Executed* (test `test_hits_land_at_once_and_wait_for_the_
   victims_own_run`).
5. **Death never removes an object at once.** A dying Skelight calls `obj_delete` in its
   own run (it leaves its run list at once but stays in the grid, the name table and
   every handle); the object is destroyed at the start of the next `runObjects`; only then
   do handles to it read 0. A dead player is never deleted. *Executed* (section 7).
   **Round 2:** this holds for creatures and players. Projectiles and spell effects
   destroy themselves (slot 1 with 3) inside their own run, so handles to them read 0 at
   once; a deflected missile is the one deferred case (section 15.3).
6. **Touch order is fixed per mover.** `Creature_moveBy` calls only the *other* object's
   slot 6; `obj_moveWithCollision` (players) calls the other's slot 6 and then the
   mover's own; `obj_moveAndCollide` (projectiles) the hit object's and then the
   projectile's. No loop stops early except `Creature_moveBy` when settling against its
   target. *Executed* for all three (ref_creature; round 2: `difftest_combat_move`,
   `difftest_combat_ranged`, section 15).
7. **Targets come from the box query, in its order.** Every scan (creature target pick,
   player melee scan, ranged find-target, arc hits, cone searches) takes
   `world_collectObjectsInBox` in grid order - row, column, most recently moved first -
   and breaks ties by list position. *Executed*.
8. **All lockstep randomness is two kinds**: the shared seed 0x404464 (constructors,
   `damage_apply`, the player's pending-damage rolls) and each object's own seed +0x44
   (creature reactions, knock-back dust, Skelight's swing choice). The cosmetic seed
   0x404460 and the third generator 0x404468 are per machine. *Executed*.

## 2. One memory, one identity

### 2.1 What the actors share

| Field | Of | Written by | Read by |
|---|---|---|---|
| +0x0, +0x4, +0x8 | every object | the list functions | everything; +0 is "who refers to me" |
| +0xc flags | every object | constructors, `Creature_processDamage` (0x100, 9, 0x2000), `Player_processDamage` (0x100, 8, 1), Skelight death (2), `obj_delete` callers (0x4002) | box query, iterators (exclude mask), every enemy test |
| +0x10 position, +0x1c radius, +0x20 height | every object | movers, slides | box query, contact loops, cone and arc tests |
| +0x38 facing | creatures, players | turning, `Creature_moveBy` (root yaw) | arc and cone tests, the player melee scan |
| +0x44 own seed | every object | `GameObject_ctor` (one shared draw), `GameObject_rand` | reactions, dust, Skelight swing clip |
| +0x48 table | every object | constructors, destructors | every virtual call (section 9) |
| +0xc8 pending damage, +0x2dc pending flags | creatures, players | slot 2 | pending-damage functions |
| +0x228 hit points | creatures; for a player a copy of record +0xac made at the top of its run (0x1a527c-0x1a5280) | `Creature_takeDamage`, `Player_run` | `damage_apply` (cold status), death tests |
| +0x234 target, +0x2e4 last attacker, +0x238 ally, +0x360 status source | creatures, players | slot 23, slot 2, status setter | target logic, kill credit |
| +0x232 AI state / +0x58c action state | creatures / players | set-state functions | the run functions |
| record +0xac hit points, +0xcc/+0xd0/+0xd4 attack and damage | players (`g_players` 0x4d8af0 + slot x 0x4c30) | `Player_processDamage`, `Player_recalcDamage` | `damage_apply`, kill experience |

In the contract all of these are bytes of one image (`SharedMemory`); the object model,
the creature model and the damage model read and write the same bytes, and the handle
words are views of the one node pool. No field is copied between models, so there is no
import/publish step and no window in which two copies disagree. *Authored* (the design);
the fields are *Observed*/*Executed* in the documents named in each row of section 9.

### 2.2 Handles and what nulls them

- `handle_link(head, back, obj)` 0x1a1738 takes two nodes, links one at the front of
  `head` carrying `obj` and its partner at the front of `back` (the target's head +0).
  *Executed* (ref_core).
- The destructor chain clears, in this order: for a creature (`Creature_dtor` 0x117128)
  the attached spells (slot 1 of each, through an iterator), +0x364, +0x360, the
  attachment state at +0x320 (0x202500, not read), +0x2e4, +0x238, +0x234, the animation
  state, then `GameObject_dtor` 0x14cf90: +8 (grid), +4 (run list), +0 (every handle to
  it), and `pool_free` when bit 0 of the argument is set. `Skelight_dtor` 0x3cc67c only
  restores its table and calls `Creature_dtor`. `Player_dtor` 0x1a1bb8 first clears the
  record's object pointer (when +0x462 is 0), calls `game_rebuildAlivePlayers`, clears
  +0x588, two lights, +0x4b8 and the five heads +0x438, +0x420, +0x408, +0x3f0, +0x3d8 (in
  that order), then `Creature_dtor`.
  *Observed* (read for this document).
- So an actor's *own* handle fields are released when it is destroyed, and every handle
  *to* it reads 0 at the same moment. Between `obj_delete` and the flush (section 7) all
  of them are still live.
- `Creature_takeDamage` and `Player_takeDamage` link the last-attacker handle to whatever
  pointer they are given (FINDINGS ST3); the contract refuses a pointer that is not a live
  object (*Authored*).

### 2.3 Shared draws in a fight

Per hit through `damage_apply` (offline, damage-number option 0, no spells, no item
effects): a monster hitting a player made 7 shared draws in the composed duel (roll,
first hit roll, four element-chance rolls, second hit roll), a player hitting a monster 8
(the same, plus the stun roll every player attacker makes). `docs/spec/combat.md` 3 is the
full list. Besides: one per object constructed (`GameObject_ctor`); in
`Player_processDamage` one for the Strong Stance resist test whenever the flags carry a
knock-back class (0x3c0000) and one stagger roll for a surviving hit (section 6.4) -
round 2 (Executed): not in action states 3 or 7, not with 0x400000, not on a heavy attack,
so a knock-back hit whose reaction set state 3 draws once, not twice.
Creature reactions, knock-back dust and Skelight's swing choice use the object's own
seed. *Executed* (difftests named in sections 6 and 11).

## 3. The world: lists, grid, queries (summary)

All *Executed* by `tools/difftest_objects.py`; `docs/spec/object-system.md` has the full
text. What a fight depends on:

- **Run order**: `runObjects` 0x14b910 (run task, priority 10) first destroys everything
  on the delete list (last deleted first), samples the pool, reaps when short, then runs
  slot 4 of the every-frame list, then `g_runLists15[frame % 15]`, then
  `g_runLists60[frame % 60]`, skipping flag 0x8000 and whatever `g_excludeMask` names.
  Front to back; an object linked during a walk to the list being walked is not run by
  that walk.
- **Activity**: `Creature_updateActive` 0x10c0f0 moves a creature to the front of the
  every-frame list when it comes within max(+0x3c4, +0x3ac, +0x3ae) of an activity centre
  (each player object, set by `gameSetObjectVis` at priority 0) - or of the camera focus
  while `g_cullByCamera` is set - and to the next 60-frame list when it leaves.
- **Box query** `world_collectObjectsInBox` 0x14a928: grid A only, cells of the box grown
  by 96, rows then columns ascending, inside a cell the most recently linked or moved
  first; at most `limit - 1` results, the first in walk order; never an object with
  0x20000; skips whatever the exclude mask names (the creature target scan sets it to 8,
  dead, for that one call).
- **Grid membership**: an object is in exactly one grid list from construction to
  destruction; every position change must be followed by `obj_updateGridCell` (relink at
  the front of the cell's list, even the same cell).

## 4. One tick, in order

### 4.1 The run pass

Offline, `tasks_run` 0x3226e4 runs the run tasks in priority order (`docs/mainloop.md` 2):
`runwater` and `gameSetObjectVis` (0), `gameMiscSync` (1), **`runObjects` (10)**, camera
(11), ..., `deathTask` (20, only after a party wipe), HUD (50), arena (100), Script (125).
Then `g_simFrame += 1`, the pads' edge words are cleared, and the end of tick runs
`game_rebuildAlivePlayers` 0x1e72f8 and `game_checkAllDead` 0x1e7438. *Executed*
(object-system 6). The contract composes `gameSetObjectVis`, `runObjects` and the end of
tick only (*Authored*); a party wipe is refused (`deathTask` is not read).

### 4.2 A monster's tick (Skelight, `Skelight_run` 0x2a8b84)

*Executed* (`tools/difftest_arena_monsters.py`; `docs/spec/arena-monsters.md` 4.3). The
class run calls the base pieces in this order:

1. `Creature_processDamage(c, model)` 0x110d30 unless state 0x17 (rising) - **pending
   damage of the previous runs is handled first**;
2. `Creature_run(c, model)` 0x112948 - timers (attack cooldown +0x318 counts down here),
   status effects, burn and damage-over-time ticks (`damage_apply` on itself every 32nd
   frame), the corpse scavenger, an inactive sunk corpse deleted (cflag 0x1000000);
3. `Creature_updateActive(c)`;
4. the weapon holder (none in the contract);
5. `ev = Creature_stepAnim(c; 1.0)` - animation advances only while active; `ev` bit 0 is
   the hit event;
6. `Creature_applyKnockback(c; 0.7)` 0x115eb8 - **a second contact pass** (section 5.4);
7. slot 23 `Creature_pickTarget(c, 0)` 0x10ded0 (section 8.1);
8. the state switch; state 6 (the swing): with a target and `ev & 1`,
   `Creature_hitTargetInArc(0.0, 48.0; c, facing, 6000, +0xd0, +0xd2, +0xd4, flags 8,
   holder descriptor)`; while the clip plays (+0x11a & 8) `Creature_turnToTarget`;
   otherwise +0xf4 counts down and at 0 the state becomes 3 (chase).

Other monster classes call the same pieces in their own order (`docs/monsters.md` 1.3);
the base class's own slot 4 is empty.

### 4.3 A player's tick (`Player_run` 0x1a5030)

*Observed and executed* in `docs/spec/player-tick.md` (`tools/difftest_player.py`). The
parts that matter for combat, in order: `Creature_run(P, P+0x544)` (call at 0x1a5248),
`Creature_applyKnockback(P; 1.0)` (0x1a5254; players are knocked back offline only),
P+0x228 = record hit points (0x1a527c), the hit-immunity countdown R+0x4c27 and spawn protection +0x4b4, ...,
`Player_processDamage(P)` 0x1b2cc0 (unless dead), the action-state switch: state 2
(neutral: attack button and `P+0x48c x 60 <= frames since +0x448` start a swing, state
1), state 1 (melee, section 6.2), state 3 (staggered), state 4 (dead).

The contract's player slot 4 is an **authored driver**: it runs exactly those steps and
then ref_player's own executed state switch for states 1, 2 and 3, and refuses the rest.
Left out (each modelled in ref_player, each run every tick by the original): the breath
puff (own draws, cold levels), the white light, the **idle voice (a shared draw when it
fires; the fixture sets its limit +0x4b2 high)**, the rumble, the pad choice,
**`Player_idleFidget` (a shared draw while exactly four animation tracks play)**, the aura
globals, regeneration, the kill plane, the swap / interact gate, instant abilities, and
the tail. A rebuild must run them all; the contract only keeps the fight composable.
**Round 2:** `ref_combat_ptick.TickRuntime` (and `ref_combat_full.FullRuntime`) run the
real tick, `ref_player.Tick.run`, as slot 4: a standing player draws the shared seed once
every tick in `Player_idleFidget`, and the idle voice once when its counter passes +0x4b2
(section 15.2). The authored driver above stays as it was for round 1's pins.

## 5. Contacts and touches

### 5.1 `Creature_moveBy` 0x113c48 (monsters; players in knock-back and scripted walks)

*Executed* (ref_creature; `docs/spec/creature-tick.md` 8). One box query (+-r, +-r,
+-1000, limit 0x10) after the terrain slide; per object in list order: skip flag 1 and
itself; 2-D overlap `dist + 0.001 < r + o.r`; the stand-on rule when either has flag 0x10;
a push-out slide (mask 3) unless o has 0x200 or the mover 0x401; then **bit 2, the other
object's slot 6 with the mover**, and the object joins the touched list; the loop stops
only when settling (flag 0x8000000) against the mover's own target. After gravity:
slot 10 (slid) and slot 11 with the touched list. The mover's own slot 6 is never called
here. The call at 0x114220 does not test for the prediction copy (`docs/issues/touch-
handlers.md` 4).

### 5.2 `obj_moveWithCollision` 0x14d4b8 (players: `Player_move` -> `creature_moveSimple` 0x1186d8)

*Observed* (read twice for this document; `docs/spec/movement-camera.md` 5.5 agrees);
**Executed** in round 2 (`docs/spec/combat-movement.md` 2, 3,000 cases, 0 mismatches; the
relink is an inline copy of `obj_updateGridCell`, made twice, with no call):

```
d = vel x DT; if 0.001 < (d.x² + d.y²) + d.z²:
    mask = 1, 3 for a creature, 5 for a player; bits = slide(...) ? 1 : 0; relink (inline copy)
box query (+-r, +-r, +-1000), limit 0x40;  top = z + height (once);  stand = -100000
for o in list order (no break):
    skip flag 1, the mover, `ignore`, a creature when skipCreatures
    skip unless dist + 0.001 < r + o.r (2-D, from the position after earlier push-outs)
    if either has flag 0x10: skip when entirely below or above; within 5 of o's top:
        touch only when o has 0x200 or the mover 0x400, else stand on it (no touch)
    push-out (slide mask 1, relink, bits |= 2) unless o has 0x200 / mover 0x400 / dist <= 0.001
    TOUCH: o.slot6(o, mover) unless the MOVER has 0x20000 (0x14d9ac);  mover.slot6(mover, o)
ground = max(terrain_heightBelow, stand); vz -= 8.999999; z += vz x DT; land (bits |= 4)
```

Bit 2 means "pushed", not "touched" (a touch without a push leaves it clear). Verified
order of the two calls at 0x14d9d0 and 0x14d9ec for this document.

### 5.3 `obj_moveAndCollide` 0x1509f8 (projectiles)

*Observed*: position += vel x DT, one relink; a ground hit backs off in tenths; box query
of +-r, +-r, +-height, limit 0x100; per object: skip 0x201, 0x20000000, itself, the owner;
height overlap; `D.x² + D.y² < (r + o.r)²`; **the hit object's slot 6 first (0x150ddc),
then the projectile's own (0x150df8)**; no break, no copy guard. A "hit once" rule lives
in each projectile's handler. **Executed** in round 2 (`docs/spec/combat-projectiles.md`
4.1; the hit-once rule is the hit state +0xcc of `MissileWeapon_onTouch` 0x152a18).

### 5.4 Knock-back is a second contact pass

`Creature_applyKnockback` 0x115eb8 (*Executed*, `tools/difftest_combat_runtime.py`):

```
player and (g_networkMode or g_pvpModeB): +0x2e8 = 0; return
if not (0 < scale) or +0x2e8 == 0 or flag 2: return
v = (cos16(+0x2e0) x speed x scale, sin16(+0x2e0) x speed x scale, 0)
save root (+0xbc, 8 bytes) and root yaw (+0xc4); zero both
bits = Creature_moveBy(c, v)                  contact loop and slot-6 calls included
restore root and yaw;  speed -= 2.0 while positive, floored at 0
dust unless creature flags 0x2000000000100000 (in water / bit 20) or bits & 3:
    two puffs; each: spot = (x - r/2 + rand % int(r), y - r/2 + rand % int(r), z + rand % 10)
    (signed remainders), a unit-ball point from triples of own draws, x 10.45, a jitter of
    three own draws % 12 - 6; fx_spawn(0x11) on cold levels else particle_spawn(0x4f8710)
```

All draws are the object's own seed - simulation state, so their count must match. The
knock-back speed +0x2e8 and angle +0x2e0 come from the pending-damage functions (6.4).

### 5.5 Touch handlers met in a fight

`Creature_onTouch` 0x11a418 sets creature flag bit 59 when the toucher is a player (read by
`Creature_run` 4.13 for charmed creatures). `Player_onTouch` 0x1beaf0 does nothing for the
prediction copy or outside action state 9 (the rush, `SpellCharge_onContact`; that the
first touched object in list order uses up the charge contact is *Inferred*; not in the
domain). 38 other
implementations: `docs/issues/touch-handlers.md` 2.

## 6. The damage path

### 6.1 Monster attacks

*Executed* (`tools/difftest_combat_runtime.py`, entry points `canSeeObj`,
`hitTargetInArc`, `hitAllEnemiesInArc`, `findEnemyInCone`).

- `creature_canSeeObj` 0x10c810 (near, far, lead; c, obj, facing, arc, rayMode): no object
  -> 0. Target point = obj position, plus its last velocity (+0x308, +0x30c) x lead for a
  creature when lead != 0. `|s16(atan2_16(v.y, v.x) - facing)| < arc` (strict).
  `d = sqrt((c.x - p.x)² + (c.y - p.y)²)`; need `(d - obj.r) - c.r < far` and
  `near <= (d + obj.r) - c.r`. One terrain ray from half the creature's height along `v`,
  length factor 0x3f8ccccc, mask 3 when rayMode is 0 else 0; seen when `t < 0` or `1 < t`.
- `Creature_hitTargetInArc` 0x119938 (near, far; c, facing, arc, min, max, attack, flags,
  descriptor): no target -> 0; `creature_canSeeObj` on the target (lead 0, rayMode 0);
  then `damage_apply(f32(min), f32(max); target, c, attack, 0, 0, flags, descriptor, 0)`
  and its result. No enemy test and **no dead test**: a creature whose target handle still
  names a dying actor (section 7) can hit it.
- `Creature_hitAllEnemiesInArc` 0x119b58 (same arguments): one box query of
  `+-1.4 x far` (0x3fb33333) on all three axes, limit 0x80, the exclude mask as it is;
  for each object in list order: slot 20 non-zero, `creature_canSeeObj`, `damage_apply` -
  **at once, per candidate, in box order**; 1 when any landed.
- `creature_findEnemyInCone` 0x10cf78 (near, far; c, facing, arc): bestD = far², the box
  half-size `single(double(far) x 1.4)` through the soft doubles (1.4 is the double at
  0x52fc80); per object: score = slot 20, skip 0; skip 3-D d² < near²; arc test
  `|s16(s16(0x4000 - atan2_16(v.x, v.y)) - facing)| <= arc` (inclusive), with `v` aimed at
  half heights; skip when a terrain ray (mask 3, from the creature's full height) gives
  `0 <= t <= 1`; +1 when nearer than the best so far, +1 last attacker, +1 current target;
  take on a higher score, or an equal score and a smaller d². **`far` is not a cap**: the
  first enemy found inside the 1.4 x far box wins with score 1 against 0 whatever its
  distance (test `test_cone_search_has_no_hard_range`).
- Other helpers (*Observed* in round 1; all **Executed** in round 2 with corrections -
  `docs/spec/combat-monster-death.md` 2 and 7, summarised in section 15.4): `Creature_hitTargetAtReach` 0x1196e8 (a point
  `reach` ahead, the target within 60.0 of it in 3-D and not dead), `Creature_hitTarget
  InArcEdge` 0x119850 (as `hitTargetInArc` with `creature_canSeeObjEdge` 0x10c5b8, whose
  range uses only the object's radius), `Creature_hitTargetOrPlayerInArc` 0x119a20 (the
  target through `creature_canSeePoint` 0x10c238, else `creature_findPlayerInCone`
  0x10ca70), `Creature_knockbackTarget` 0x119d10 (target +0x2e8 = speed, +0x2e0 = the
  bearing), and two cooldown setters without names: 0x118bf0 (c, frames) and 0x118b58
  (c, frames, obj; also relinks the target), each calling slot 27 with 0x10 before storing
  +0x318.

### 6.2 Player attacks

- **Melee scan and hit frame** (`Player_run` state 1, 0x1a9678; *Executed* in
  `docs/spec/player-tick.md` state 1): on frame 1 of the swing, or without a target
  handle: box (+-48 or +-58, +-72), limit 0x100; candidates not flagged 0x49 or
  0x1000000 and, for a creature, not charmed and not friendly (or a PvP enemy); in front
  (`n . f >= 0`) - linked into the sweep list +0x4b8 for a class-2 weapon on combo step 3;
  within the 60° cone (`n . f >= 0.5`) and `distance - radius < reach`: the lowest
  `d - n.f x 32` wins (ties to the later); a creature winner's slot 12 is called with 3.
  The hit lands on `t == trunc(16.02 / speed)` offline (frame 16 at speed 1.0), and in a
  net game on frame 1 only when +0x55c is 0.
- **`Player_meleeHit`** 0x1b6a98 (scale; P, target, unused, extra flags) - *Executed*
  for an unarmed player with scale 0 (`playerMeleeHit`); the weapon, dual-wield, bow,
  heavy-attack and scale branches are *Observed*: nothing for the prediction copy; with scale 0
  a terrain ray (mask 0, length 1.0) from 36 above P along the 3-D difference, a hit
  (`t >= 0`) refuses the attack unless the target is an `AutoProp`; dual wield (both hands
  and the passive 0x40000 on an odd combo step) picks the second weapon; then
  `Player_recalcDamage(P, weapon, 0)`; flags = the weapon definition's damage bits (+0x20)
  or 1 unarmed; 0x1000 for weapon class 1 after 60 frames; knock-back class 0x40000, or
  0x80000 with a scale or a long weapon (class 3) after 60 frames; a bow or thrown
  weapon recomputes as unarmed and adds 0x200000; a heavy attack adds 0x200000 and
  **raises the record's damage range in place** (`R+0xd0 += round(R+0xd0 x s)`, s from
  passive 0x20000) and calls `Player_hitSparks` (a shared-seed user, not read); a scale
  multiplies the range in place; `SpellHarmTouch` may adjust min/max (round 2: every
  branch **Executed**, `docs/spec/combat-player-melee.md` 4; `Player_hitSparks` makes 200
  shared draws); then **one**
  `damage_apply(f32(R+0xd0), f32(R+0xd4); target, P, R+0xcc, item_getModifiedField1a(
  weapon), the item's word +8, flags | extra, weapon item, 0)` (the two middle values are
  not read by `damage_apply`; all 0 unarmed).
  The record values stay as written until the next `Player_recalcDamage`. A landed hit on
  a creature sets the trail's material (R+0x4ac5 + hand x 0x40) and a 5-frame timer.
- **`Player_findTarget`** 0x1bb3c8 (reach; P) - *Executed* (`playerFindTarget`): used by
  bows, throws and the class 4/6 combo. Nothing at all on a level whose name contains
  `stomedal` (a substring test). Box (+-reach, +-reach, +-72), limit 0x100, +0x4b8
  cleared; candidates: not P, flags & 0x49 clear, flag 0x20, charm 0 (so never another
  player); the 60° cone; `distance - radius < reach`; a terrain ray (mask 0, length 1.0)
  from 36 above P that must miss (`t < 0`); lowest `edge - dot x 32`, ties to the later;
  +0x234 cleared and relinked to the winner.

### 6.3 Take-damage (virtual slot 2)

| | `Creature_takeDamage` 0x116638 | `Player_takeDamage` 0x1b5330 |
|---|---|---|
| Evidence | Executed (ref_creature) | Executed (`playerTakeDamage`) |
| Early exits | inert +0x231; IgnoreDamage (timers zeroed) | recall countdown, spawn protection, vehicle, level `actintro`, jump-gate travel, menu lock-out, exit countdown; hit immunity R+0x4c27 (HUD flash only) |
| Hit points | **subtracted now** (`+0x228 -= amount`) | not touched; record +0xac changes in `Player_processDamage` |
| Pending | +0xc8 += amount, +0x2dc \|= flags, +0x304 = frame | +0xc8 += amount, +0x2dc \|= flags |
| Hit angle +0x2e0 | `0x4000 - atan2_16(V.x - A.x, V.y - A.y)` while hp > 0 | the same unless the new flags have 0x800000 |
| Last attacker +0x2e4 | relinked only while hp > 0 (so it names the killer) | relinked on **every** hit with an attacker |
| Owner rules | flag 0x80: the owner behind +0x4c; flag 0x10000000: the status source +0x360 | the same |
| Other | visual arc +0x3b0 = 0x7fff | block (states 8, 0xb; one shared draw in state 8 only; a front block - half-plane - zeroes the amount, or halves it with 0x20000, and calls `Player_blockSparks`, >= 150 own draws; round 2, Executed), Holy Shield (mana pays a fraction), HUD flash |

### 6.4 Pending damage (the victim's own run)

- **`Creature_processDamage`** 0x110d30 - *Executed* (ref_creature; creature-tick 3):
  nothing pending: knock-back speed and maybe a reaction; pending: +0xc8 = 0, a corpse
  returns with its flags kept, flag 0x100, the hit effect, survive (knock-back speed,
  hit reaction state 0x12 by own draws) or **die**: flags 9, statuses clamped, ice or
  gibs, knock-back speed, **slot 27 with 0x14** (the class's set-state), flag 0x2000,
  then (unless `Dead` or creature flag 0x100000000) the kill experience for every player
  (`docs/spec/combat.md` 5) and the skill-0x3b orb roll (own draw).
- **`Player_processDamage`** 0x1b2cc0 - *Executed* for the domain (`playerProcessDamage`):
  A. unless +0x2dc has 0x20000000, a cutscene or an open dialog drops everything.
  B. with flags & 0x3c0000 and action state not 6 or 10: slot 39 (rank of skill 0x3e),
  `SkillStrongStance_getStat0`, **one shared draw**, resist = `draw % 100 < stat`;
  +0x2e8 = 100 / 150 / 200 / 250 and level 1 / 2 / 3 / 3 for the first of 0x40000,
  0x80000, 0x100000, 0x200000 (halved, one level less, in PvP mode A); level > 0: blocking
  with `|s16(+0x2e0 - facing)| >= 0x6000` costs a level (the attacker in front,
  *Inferred*); level < 2 or not resisted: action state 3
  (+0x448 = frame, ghost rebase when local, a voice); level < 2: the small reaction clip
  unless 0x400000; level >= 2: the knock-down clip by bearing (or `SkillStrongStance_
  trigger` when resisted - not in the contract).
  C. pending <= 0 or action state 4: flags dropped, **pending kept**; debug invulnerability
  zeroes pending; **record +0xac -= pending**; blood (and one shared draw, a `GutChunk` 1 in
  8) only with `g_decalDetail > 0` or in a net game when flags & 0xd; flag 0x10 and hp <= 0
  disintegrates; pending = 0; flag 0x100.
  D. hp <= 0: a Resurrect spell may save (one player only); hp = 0, **flag 8**; a held spell (+0x588) is
  destroyed; the death clip; **action state 4**, +0x448 = frame, **flag 1**;
  `game_rebuildAlivePlayers` **at once**; local: menus closed, ghost rebase; with two or
  more players the other of slots 0/1 shouts; PvP kill credit or arena lives. The object
  is never deleted (it waits for respawn or resurrection; respawn re-makes it at the same
  address, FINDINGS ST2).
  (Round 2, Executed: the knock-down clip is `knockdown{1,2}_{a,b,c,d}.anm` by weapon class
  and bearing; the Resurrect save needs `g_numPlayers == 1` and skips E; blood draws once
  for the real player - `docs/spec/combat-player-defence.md` 3.)
  E. survived, unless 0x400000, action state 3 or 7, or a heavy attack: **one shared
  draw**; stagger when `draw < max(0.04 - R+0xdc x 0.04, 0) x 65536` or flags & 0x4000000,
  then (not in action state 6 or 10) action state 3 and the reaction clip.

## 7. Death and removal timing

| Tick | Attacker's run | Victim's run | Others in the same tick |
|---|---|---|---|
| T | the hit: `damage_apply` -> victim slot 2 (creature hp falls now) | if it runs **after** the attacker: its pending damage is handled in T | see full hp loss at once; no reaction yet |
| T or T+1 | | `Creature_processDamage` -> die: flags 9, slot 27 (0x14); Skelight: flag 2, `obj_delete` - **the rest of its run still executes** (`Creature_run`, activity, `stepAnim`, knock-back returns at flag 2, target pick, state 0x14 -> `Creature_deadUpdate`) | the corpse is still in the grid and the box query, but flag 1 (not solid) keeps it out of contact loops, flag 8 out of every enemy test and out of the creature target scan (mask 8); target handles to it are **still set** (`Creature_pickTarget` sends a creature with a dead target to state 0 and leaves the handle to the set-state) |
| next `runObjects` | | destroyed in the delete-list flush, before any object runs | every handle to it reads 0; the block is the next one its size class hands out |

*Executed* end to end in the contract (`test_kill_delete_destroy_in_three_ticks`) on top of
the executed pieces. Classes with a corpse phase do not delete at once: their set-state
calls `Creature_dropLoot` and slot 28 (`docs/issues/kill-loot-xp.md` 2, *Observed*);
slot 28 is `Creature_onDeath` 0x10beb8 (*Executed* in ref_arena_monsters: death script,
drop item, a hidden creature finished at once, PvP kill credit, boss music);
`Creature_deadUpdate` 0x1108a0 (*Executed* without its blood decal)
sinks a corpse with creature flag 0x1000000 by 0.35 per call once the death clip has
ended and deletes it when the sink exceeds its height (hold 0), or deletes it when the
clip has ended with one track left (hold 1); `Creature_run` deletes an **inactive** corpse
with that flag (0x113bc4). Players: section 6.4 D. FINDINGS D23 records the Skelight case.

## 8. How AI creatures pick targets and attack

### 8.1 Target choice - `Creature_pickTarget` 0x10ded0 (slot 23)

*Executed* (ref_creature; creature-tick 6). No draws. Inert: nothing; no-target timer or
friendly: handle cleared; a dead current target: set-state 0. The current target is kept
while slot 20 says enemy, except on a scan (every 32nd frame staggered by the serial byte
+0x230, or forced): box of +-HomeRange (+0x3c0) on all axes with the exclude mask forced
to 8, limit 0xc0; score = slot 20 (+1 last attacker, +1 current target); higher score,
then smaller 2-D distance (starting at HomeRange²); the leash refuses candidates outside
HomeRange of home and farther from home than the creature unless within 60 + both radii
(off for 480 frames after any hit).

### 8.2 The enemy test - slot 20

| Table | Body | Rule |
|---|---|---|
| Creature (and every monster class) | `Creature_isEnemy` 0x119328, Executed | 0 for none, itself, no 0x60 flag, flags 0x20008, cflags 0x4000800; else slot 37 of both (team byte +0x310; for a player record +0x4c24): equal 0, different 1 or 4 (cflag 0x100000000000) |
| Player | `Player_isEnemy` 0x1b5ea8, Executed | 0 for itself, no 0x20, flags 8 or 0x1000000, cflags 0x4000800; another player only in PvP mode A by record team; a creature: 1 unless charmed, a charmed one only in PvP mode A by team |

So, by these rules, an uncharmed monster is always a player's enemy, and a monster calls
a player an enemy when the monster's team byte +0x310 differs from the player record's
+0x4c24 (that the shipped values make every monster hostile is *Inferred*).

### 8.3 Seeing and attacking

A class's states combine slot 25 (`Creature_canSeeTarget` 0x10e658, *Executed* in
ref_arena_monsters: within pointblankrange +0x3ac all round, else within visualrange
+0x3ae inside visualarc +0x3b0; ray mode 1 when forced or the arc is 0x7fff, which every
hit sets), `Creature_canSeeTargetIn` 0x118d40, the cone searches (6.1), the move helpers
(`docs/spec/creature-tick.md` 9) and a hit helper on the event bit of a swing clip.
`creature_findPlayerInCone` 0x10ca70 (*Observed*; **Executed** in round 2): charmed
creatures use an inline copy of the enemy cone search; others take the nearest live player
object of `g_players[0..n)` in the cone, strict arc, 2-D distance, a clear terrain ray from
the creature's **full** height - no team test, no player-flag test, and here `far` **is**
a hard cap (unlike `creature_findEnemyInCone`). Skelight: section 4.2.

## 9. The virtual slots a fight reaches

Function words of the three tables (*Observed*: read from the executable for this
document; the bodies' evidence as stated):

| Slot | Meaning | Creature 0x50cc58 | Player 0x511308 | Skelight 0x5174b0 | Called by, in a fight |
|---|---|---|---|---|---|
| 1 | destructor (3) | 0x117128 | 0x1a1bb8 | 0x3cc67c | the delete-list flush |
| 2 | take damage (attacker, flags; amount) | 0x116638 Executed | 0x1b5330 Executed | = Creature | `damage_apply` |
| 4 | run | 0x3c7e98 (empty) | 0x1a5030 | 0x2a8b84 Executed | `runObjects` |
| 6 | touched by (other) | 0x11a418 Executed | 0x1beaf0 Observed | = Creature | the three movers (5) |
| 10, 11 | slid / touched list | 0x11a3f0, 0x11a448 (empty) | = Creature | = Creature | `Creature_moveBy` |
| 12 | nearby event (a, &pos, b; R) | 0x11a290 (empty) | = Creature | = Creature | `world_notifyObjectsNear` 0x11a2b8 (one player: 600 around a hit creature), the player melee scan (kind 3) |
| 17 | spells follow | 0x11a868 | = Creature | = Creature | `Creature_run` |
| 20 | is enemy | 0x119328 Executed | 0x1b5ea8 Executed | = Creature | target pick, arc hits, cone search, touch handlers |
| 23 | pick target (force) | 0x10ded0 Executed | = Creature | = Creature | class runs |
| 25 | can see target (force) | 0x10e658 Executed | = Creature | = Creature | class runs |
| 26 | turn toward (mode, point) | 0x10bb08 Executed | = Creature | = Creature | turn-to-target, the player melee scan |
| 27 | set state | 0x3c2688 (store only) | 0x1b5d68 | 0x2a91b8 Executed | every state change, death |
| 28 | on death (quiet) | 0x10beb8 Executed | = Creature | = Creature (not called) | class set-states |
| 30 | stun (frames, flash) | 0x118a58 Executed | 0x3c3b10 (empty) | = Creature | `damage_apply` stun |
| 37 | team | 0x3c2730 (+0x310) | 0x3c3b18 (record +0x4c24) | = Creature | slot 20 |
| 39 | skill rank (id) | - | 0x3c3b40 (`player_getSkillRank`) | - | `Player_processDamage` |

`world_notifyObjectsNear` (*Observed*): a box of +-R on all three axes, limit 0x80, and
slot 12 of every object in list order - the hit creature itself included; ten monster
classes override slot 12 (for example Goblins called to a hurt Goblin).

## 10. What reads per-machine state on this path

For online play (`docs/OVERVIEW.md`): activity (camera focus while `g_cullByCamera`,
FINDINGS D6) decides whether a creature animates and so whether it lands hits;
`Player_takeDamage` reads `g_localMenuOpen` and `net_isLocalSlot` only for a screen tint;
`Player_processDamage` uses `net_isLocalSlot` for menus and the ghost-rebase flag; the
swing sound uses the third generator; `damage_apply` reads the camera focus for a counter
nobody reads and, offline only, the damage-number option; blood needs `g_decalDetail`
offline but runs (with a shared draw) on every machine in a net game. In a net game every
damage number is a `FlyingText` object (a pool block, a shared draw, a run-list entry) -
not in the contract (section 13).

## 11. What was run

- `python3 -m unittest discover -s tools -p 'test_*.py'`: 679 tests, all pass;
  `tools/test_ref_combat_runtime.py` adds 27 synthetic-fixture tests (shared image and
  handles, one seed, run order, damage timing, the inactive swing, target choice, death,
  deletion and destruction, a dead player, player take-damage / pending damage /
  find-target, contact order and the prediction-copy guard, arc hits in box order, the
  cone search without a hard range, ray modes, knock-back dust, refusals, and a self-pin
  of an 80-tick duel - the last is evidence about the model only).
- `python3 tools/difftest_combat_runtime.py <your SLUS_209.73>` (seed 20973, 3,000 cases
  per entry point): **30,988 cases compared, 0 mismatches** - calls with arguments, every
  byte stored outside the stack, the shared seed, the result. Cases the model refuses as
  outside the domain are not run (2,012, all `Player_meleeHit` with a blocked line of
  sight or a heavy attack). Instructions of each body executed:

| Entry point | Compared | Instructions executed |
|---|---|---|
| `creature_canSeeObj` | 3,000 | 151 of 151 |
| `Creature_hitTargetInArc` | 3,000 | 58 of 58 |
| `Creature_hitAllEnemiesInArc` | 3,000 | 109 of 109 |
| `creature_findEnemyInCone` | 3,000 | 203 of 203 |
| `Creature_applyKnockback` | 3,000 | 252 of 254 |
| `Creature_deadUpdate` | 3,000 | 110 of 174 (no blood decal) |
| `Player_isEnemy` | 3,000 | 60 of 62 |
| `Player_takeDamage` | 3,000 | 144 of 280 (no block, no Holy Shield) |
| `Player_findTarget` | 3,000 | 212 of 212 |
| `Player_processDamage` | 3,000 | 450 of 784 (no knock-down, blood, PvP, Resurrect) |
| `Player_meleeHit` | 988 | 203 of 431 (unarmed) |

  A quick run with `--seed 7` also passes. The pieces they compose have their own
  difftests (objects, creature, arena monsters, combat, player).
- Not run: anything on a console, PCSX2 or the live rig.

## 12. Corrections

| Where | Was | Is | Evidence |
|---|---|---|---|
| a reading made for this document | `Player_findTarget` reads past its candidate list after a cone or range reject (the loop test using the word at 0x20) | No defect: the delay slot of the non-likely branch at 0x1bb52c always computes the next entry's address, so the rejects that branch to 0x1bb698 test the right word | Executed (`playerFindTarget`, 3,000 cases with the word at 0x20 both 0 and non-zero) |
| `docs/spec/movement-camera.md` 4.1(g) | `ev & (0x3f199999 <= s ? 4 : 1)` | the same, and with `s < 0.6` the soft-double routine 0x3af9b8 is called with `s` and the double at 0x5376a8 (0.3) and its result discarded (0x1b4934-0x1b4948) | Observed |
| `docs/spec/creature-tick.md` 18, `docs/spec/arena-monsters.md` call-outs | `Creature_applyKnockback`, `Creature_deadUpdate`, `Creature_hitTargetInArc`, `Creature_hitAllEnemiesInArc`, `creature_canSeeObj`, `creature_findEnemyInCone` not modelled | modelled and executed here | section 11 |
| `docs/spec/player-tick.md` 14 | `Player_meleeHit`, `Player_findTarget`, `Player_processDamage` callbacks, not models | modelled and executed (meleeHit unarmed, processDamage restricted) | section 11 |
| `symbols/player.tsv` note of `Player_findTarget` | "links it at +0x234; clears +0x4b8" | also: no virtual call, no draw; nothing at all on a `stomedal` level | Executed |
| `symbols/player.tsv` note of `Player_meleeHit` | "(scale, player, target, a, flags)" | the third argument is never read (overwritten at 0x1b6a9c); the fourth ORs into the flags | Observed, Executed |

Proposed ledger rows (for whoever edits `FINDINGS.md`):

| # | Finding | Kind | Evidence |
|---|---|---|---|
| new | A hit is reacted to in the victim's own run: in the tick of the hit when the victim runs after the attacker, else in the next. Hit points of a creature fall at once; a player's only in `Player_processDamage` | Executed (composition of executed functions) | 0x116638, 0x1b5330, 0x110d30, 0x1b2cc0; `test_hits_land_at_once_and_wait_for_the_victims_own_run` |
| new | An inactive creature lands no melee hit: its animation does not advance, so the hit event never fires and its swing state never ends | Executed | 0x1162b0; `test_an_inactive_swing_never_lands` |
| new | `Player_processDamage` draws the shared seed once for a surviving hit (the stagger roll; not in action states 3 or 7, with 0x400000 or on a heavy attack - round 2) and once for any hit with a knock-back class (Strong Stance), with no prediction-copy guard | Executed | 0x1b2d90-0x1b2dd8, 0x1b3718-0x1b37d0 |
| new | `creature_findEnemyInCone` has no hard maximum range: `far` only seeds the best distance | Executed | 0x10cfc4, 0x10d1d4-0x10d24c |

No patch is proposed.

## 13. Not done, not known

Status after round 2 (2026-10-17). What round 1 listed here and round 2 executed is struck
from the list and named in section 15. Round 3 (section 16) executed DiseaseCloud,
GutChunk, the Strong Stance phantom, and `MissileWeapon_run` kinds 1, 2, 5 and 6. What
remains:

- **Damage numbers in a net game**: `FlyingText` objects (pool block, shared draw in the
  constructor, run list, deletion) - their lifetime is not read; the contract refuses any
  pool request from `damage_apply` (also `LightEffect` on a stun, gas, disease).
- **Objects the defence path constructs**: GutChunk and the Strong Stance phantom are
  executed in section 16. Holy Shield's light and `Player_blockSparks` with silent != 0
  are executed in section 17. Section 18 executes the sample point inside that absorb
  and the angle both block-spark cosines receive. `DefenceModel` still refuses a
  nonzero silent.
- **The rest of `Player_run`** inside the composed world: regeneration, instant abilities
  and the dead state run (ref_player, executed) but respawn, `game_checkAllDead` and
  `deathTask` are not composed; `Player_interact` with an interactable object in reach is
  refused.
- **Ranged**: arrow kinds 1, 2, 5 and 6 are executed in section 16. Potion kinds 1-3
  are executed in section 17. Still open: deflection in the runtime, skill ranks above 0
  on a missile, other projectile classes (`LavaBomb`, `beetleProjectile`, ...), the
  player's bow release in state 0, and what `damage_apply` does with a projectile as
  attacker (Unknown).
- **Spells**: three are composed (Holy Strike, Shock of Fire, Wave of Flame). DiseaseCloud
  is executed in section 16; attaching the disease effect is composed there, not a slice
  of `damage_apply`. Section 18 executes Holy Shield's sample point and
  `MultiFireProjectile_run`. The other skill runs named there, player state 5's aim /
  mana / recast inside the composed world, and a creature destroyed with spells attached
  are still open.
- **Monster classes**: set-states and corpse phases of the classes not yet executed
  anywhere (Goblin's death state is executed, its other states are not). Section 18
  executes AntQueen's bank fade and spring, Skeleton's slot-25 forces, and Soul's
  demon test; the other states of those runs are not. `loot_generateDrops` objects
  are not composed. Who calls 0x118b58 (Unknown).
- **Per-machine inputs**: `game_buildScreenEdgePlanes` 0x1e71b0 (camera frustum) stays a
  call-out of the screen clamp.
- Water beyond the refusals, PvP modes, cutscenes, the prediction copy and two machines.
  Nothing was run on a console, in PCSX2 or on the live rig.

## 14. For the native client

What lifts the "exactly one live retained World actor" restriction of
`SESSION_CREATURE.md` without inventing behaviour:

1. Keep every actor in the one object World with its pool address as identity and route
   every cross-actor reference through handles of the one node pool; let destruction,
   not death, null them (2.2).
2. Run actors by the list discipline of section 3 and give each its class's slot 4 in the
   order of 4.2 / 4.3; allow the box query to return any number of actors and keep its
   order.
3. Use the three movers with their exact touch orders (5); run knock-back as the second
   `Creature_moveBy` pass.
4. Deliver hits through `damage_apply` to the victim's slot 2 at once and leave the
   reaction to the victim's own next run (6); delete in the victim's run and destroy in
   the next flush (7).
5. Install the service table of section 9: the base-class and Player bodies named there,
   with the call-outs this contract lists as refusals still refused.

6. (Round 2) Follow section 15: move through the executed movers with their touch orders,
   let projectiles and effects destroy themselves in their own run, run the real player
   tick (its idle-fidget draw every standing tick and the 200-draw heavy-attack sparks
   included), and take the executed `_full` bodies, not the round-1 contract code, where
   15.6 lists a difference.

`tools/ref_combat_runtime.py` is the executable form: `Runtime()` builds the world,
`spawn_player` / `spawn_skelight` place actors (authored set-up), `tick()` runs one pass,
and `Runtime.trace` / `CombatModel.calls` / `CombatModel.vcalls` give the order of every
service call for comparison.

## 15. Round 2 (2026-10-17): movement, player combat, projectiles, spells, monster death

Round 2 adds to round 1 and changes none of its code, APIs or pinned vectors: every new
body lives in its own module, subclassing `CombatModel` / `Runtime`, and every new area has
its own document. Where a round-1 method or statement turned out short or different, the
difference is listed in 15.6 and the executed body is in the new module; the round-1
method stays as it was.

| Target | Document | Module (model / runtime) | Difftest |
|---|---|---|---|
| 1. movement and collision | `docs/spec/combat-movement.md` | `ref_combat_move.py` (`MoveModel` / `MoveRuntime`) | `difftest_combat_move.py` |
| 2. combos, armed melee | `docs/spec/combat-player-melee.md` | `ref_combat_melee.py` (`MeleeModel` / `MeleeRuntime`) | `difftest_combat_melee.py` |
| 2. blocking, knock-downs; 7. the real player tick | `docs/spec/combat-player-defence.md` | `ref_combat_ptick.py` (`DefenceModel` / `TickRuntime`) | `difftest_combat_ptick.py` |
| 3. projectiles and ranged | `docs/spec/combat-projectiles.md` | `ref_combat_ranged.py` (`RangedModel` / `RangedRuntime`) | `difftest_combat_ranged.py` |
| 4. spells in combat | `docs/spec/combat-spells.md` | `ref_combat_spells.py` (`QueryModel` / `SpellRuntime`) | `difftest_combat_spells.py` |
| 5. death, loot, destructors; 6. hit and cooldown helpers | `docs/spec/combat-monster-death.md` | `ref_combat_monsters.py` (`MonsterCombatModel` / `MonsterRuntime`) | `difftest_combat_monsters.py` |
| all of them in one world | this section, 15.5 | `ref_combat_full.py` (`FullModel` / `FullRuntime`) | - (composition of the above) |

### 15.1 Movement and touches (*Executed*)

- `obj_moveWithCollision` 0x14d4b8: for every object of ONE box query, in its order, with
  no early exit: the other's slot 6 with the mover, then the mover's own slot 6. The
  other's call is skipped only when the **mover** is the prediction copy (0x14d9ac). The
  grid relink is an inline copy of `obj_updateGridCell`, twice, without a call.
- `Player_move` 0x1b4020, all modes 0..7, moving and still stick: a player moves along its
  **facing**, which turns 40 % of the remaining angle per tick toward the stick in mode 0;
  every call makes `dialog_isOpen`, `net_getCamYaw` and, last, `net_getCamFlag`; entering
  water draws the shared seed once; the velocity passes through the static vector 0x8657a0.
  A composed player walks 155.15/60 units per tick (fixture speed scale).
- `Player_animStep` 0x1b9520 writes the root motion that `Player_move` adds once as
  `root x 60`; `Player_clampToScreen` 0x1b3d90 runs on authored screen planes (the planes
  themselves come from the camera, per machine).
- Creature walking was already executed (`ref_creature`, 99.1 %); the movement document
  maps which class states use which helper and ties root motion and footsteps to the
  research-anim event tables.

### 15.2 Player combat (*Executed*)

- **The attack choice**: `Player_pickAttackAnim` 0x1bba88 draws the shared seed once and
  ignores the value. The hit is a frame count, not an animation event: `since ==
  trunc(16.02 / speed)` offline; the next swing may start once `since > (22.02 - trim) /
  speed`; the swing ends after `P+0x470 x 60` frames, not divided by the speed.
- **Armed melee**: `Player_meleeHit` 0x1b6a98, every branch - one `damage_apply` per
  target; a blocked line of sight still hits an `AutoProp`; a bow or thrown weapon in melee
  does fist damage with the weapon's flags; a heavy attack raises the range x1.9 in place
  and, on a creature, costs **200 shared draws** (`Player_hitSparks` 0x1bcc20, real player
  only). A bow or thrown combo press between 22.02 and 39.6 frames draws the seed and
  advances the step without a swing. 12,000 executed combo ticks (classes 4, 6, 7).
- **Blocking**: a front block (half-plane) takes nothing, or half with flag 0x20000; one
  shared draw in state 8 only; `Player_blockSparks` walks the player's own seed by at least
  150 draws.
- **Knock-downs**: level >= 2 picks `knockdown{1,2}_{a,b,c,d}.anm` by class and bearing;
  resisted calls `SkillStrongStance_trigger`; unresisted sets state 3 first.
- **The real tick** (target 7): `TickRuntime` runs `ref_player.Tick.run` as slot 4. A
  standing player (four tracks) draws the shared seed once every tick (`Player_idleFidget`),
  none while a fifth track plays; the idle voice adds one when its counter passes +0x4b2 -
  `docs/spec/player-tick.md` 10, rows 1 and 2.

### 15.3 Projectiles (*Executed*)

- Arrows and bolts of players and monsters are `MissileWeapon` (block 0x1c8), thrown
  weapons `playerProjectile` (0x1d0): one shared draw in construction, linked at the
  **front** of the every-frame list, so first run in the next tick, before older actors.
- Flight is `obj_moveAndCollide` 0x1509f8: the hit object's slot 6, then the projectile's.
  The hit state +0xcc lets one victim through per frame (first in box order); Penetrating
  Arrows re-arms it and keeps a victim list at +0x124 (2 shared draws per touch for a
  player's kind 0/3 arrow), then one deflection roll, then `damage_apply` with the owner
  as attacker (the projectile itself if the owner handle is 0).
- A projectile **destroys itself** in its own run (slot 1 with 3); only a deflected one
  goes through `obj_delete`.

### 15.4 Spells, monster helpers, death and destructors (*Executed*)

- A cast happens in the caster's run; an effect object first runs in the next tick, a
  player's attached spell in the tail of the same run (`Player_updateCast` calls slot 17),
  a creature's at the start of `Creature_run`. Victims come from
  `world_collectObjectsInArc` 0x1614f0 (creatures; first entry nearest, the rest in reverse
  acceptance order; partnerless nodes, so a destroyed object stays listed),
  `world_collectInSphere` 0x14ab80 and `world_damageInRadius` 0x161270 (damage at once, in
  box order; a non-creature costs one shared draw). Burning credits the caster through the
  status source +0x360 and flag 0x10000000. Effects destroy themselves at once.
- Hit helpers: `hitTargetAtReach` (60 in 3-D; no arc, ray or enemy test), `hitTargetInArc
  Edge`, `hitTargetOrPlayerInArc`, `knockbackTarget`, `world_notifyObjectsNear`, the sight
  helpers `canSeePoint` / `canSeeObjEdge` / `canSeeTargetIn` (their differences from
  `canSeeObj` are a table in `docs/spec/combat-monster-death.md` 1), and the cooldown
  setters `Creature_setAttackCooldown` 0x118bf0 / `Creature_setAttackCooldownOn` 0x118b58.
  None of them draws the shared seed.
- Death: `Creature_deadUpdate` with its blood decal (two own draws), `Creature_dropLoot`
  0x10f2c8 (eleven class tests, boss ranks, own-draw coins), Goblin's death state; the
  destructor chain `GameObject_dtor`, `Creature_dtor`, `Skelight_dtor`, `Player_dtor`
  agrees with round 1's `Runtime._slot1` order (pinned by a test), with the additions of
  15.6.

### 15.5 One world with all of it

`tools/ref_combat_full.py` merges the six models into `FullModel` and composes
`FullRuntime`, whose player slot 4 is the real tick with the executed `Player_move`,
`Player_meleeHit`, `Player_pickAttackAnim`, `Player_takeDamage` / `Player_processDamage`
and `Player_animStep`. It is a composition of executed bodies plus labelled fixtures;
it refuses what any area refuses. The six models' routing tables are merged explicitly
and checked at import (no name or vtable function routed two ways; every method one area
shadows in another is listed as reviewed). Choices made there (*Authored*): object
construction and destruction always go through the shared world (so projectile and effect
destructors keep the world's lists and pool); type-info names in mangled form; the spells
runtime's authored player spell walk is dropped because the real tick's tail calls slot 17;
queued casts run just before the tick's tail; the timed-modifier id list 0x537c08 is an
empty fixture. Scenarios (`tools/test_ref_combat_full.py`, 13 tests; evidence about the
model):

- **Round 1's 80-tick duel** in `FullRuntime`: the player makes exactly one more shared
  draw per tick (the idle fidget) on every tick except 31-50, while the swing's fifth track
  plays. With those draws injected into round 1's runtime, the damage calls, their results,
  the final seed and the Skelight's hit points are identical; the one remaining difference is
  the player record 0.68 higher - the real tick's regeneration, 0.01 for each of 68 ticks
  below the maximum. Final seed 0xa2e1c5fe (round 1's pin 0x60792ed2, which is unchanged in
  round 1's `Runtime`).
- **Walk and combo kill**: the touch order is the Skelight's slot 6 with the player, then
  the player's own; the player is held at the sum of the radii; the kill lands in tick N,
  `obj_delete` in the Skelight's run in N+1, destruction in the flush of N+2.
- **Arrow kill**: missile run, `damage_apply`, Skelight run, `obj_delete`; next tick the
  flush destroys the Skelight and the missile runs and destroys itself.
- **Burn kill**: damage on frames with `frame & 0x1f == 0`, flags 0x1180c040; the last
  attacker at death is the caster, experience is given, the spell detaches itself.
- **Two players, two monsters**: each tick's seed advance equals the sum of the actors'
  draws; a monster's are its `damage_apply` rolls, a player's are its damage rolls plus the
  fidget, stagger, idle voice and attack choice (all four seen).
- A 200-tick mixed scenario is pinned (seed 0x7d6b07d5).

The integration found one defect in a round-2 module, fixed: `MoveModel`'s water helper
hid `ref_creature`'s helper of the same name, so a creature knock-back in `MoveRuntime`
failed (regression test in `tools/test_ref_combat_move.py`).

### 15.6 Corrections to round 1

| Where | Was | Is | Evidence |
|---|---|---|---|
| 1 item 5 | death never removes an object at once | creatures and players only; projectiles and effects destroy themselves in their own run | Executed (`MissileWeapon_run`, `playerProjectile_run`, effect destructors) |
| 2.2 destructor chain | `pool_free` in `GameObject_dtor` when bit 0 | each destructor first stores its own table; the derived ones call their bases with 0 and the most derived frees the block; spells are ended through their table at +0x14 | Executed (`difftest_combat_monsters`) |
| 2.2 `Player_dtor` | clears the record's object pointer when +0x462 is 0 ... two lights | under `g_inGhostOp` no record write (the alive list is still rebuilt); a display-only player clears 0x4ef360 instead; record words +0x43dc..+0x43ec are zeroed; an `AnimState` at +0x560 is destroyed before the lights | Executed (`playerDtor`) |
| 2.3, FINDINGS proposal row 3 | a stagger roll for every surviving hit | not in states 3 or 7, with 0x400000, on a heavy attack; a knock-back hit draws once | Executed 0x1b3718-0x1b37c8 |
| 6.1 cooldown setters | each calls slot 27 with 0x10, then stores +0x318 | 0x118bf0 does nothing without a target and skips slot 27 (not the store) in state 0x14; 0x118b58 does nothing for a boss or a null object | Executed |
| 6.1 `hitTargetAtReach` | target within 60 of a point ahead, not dead | the same, in 3-D, with no arc, ray or enemy test | Executed |
| 6.3 block | one shared draw in state 8 | and a front block zeroes or halves the hit and calls `Player_blockSparks` | Executed |
| 6.4 D Resurrect | one player only | `g_numPlayers == 1`, and a save skips the stagger roll | Executed |
| 8.3 `findPlayerInCone` | nearest live player in the cone | `far` is a hard cap, the ray starts at full height, no player-flag test | Executed |
| contract code `move_with_collision` | calls `obj_updateGridCell` | the original inlines the same relink (no call); state identical | Executed (`difftest_combat_move --round1`) |
| contract code `player_move` (still stick) | - | the original also calls `dialog_isOpen` (0x1b40c0), the target-angle `net_getCamYaw` (0x1b41ec) and `net_getCamFlag` (0x1b51e8) every call, stores 0x8657a0, stores -0.0 (0x80000000) in the track weights +0x164/+0x16c/+0x184/+0x18c of a standing player, always stores the +0x482 countdown, passes a height pointer to `water_test`; offline with no dialog only the -0.0 patterns and the 0x8657a0 store differ in state | Executed (`--round1`: all 2,748 in-domain cases differ in calls) |
| `docs/spec/skills-35-68.md` 1.6 `world_damageInRadius` | (order not said) | raised to the minimum first, then capped at the maximum: the maximum wins when they cross | Executed |
| `ref_skills_a.py` notes, symbol note of 0x1614f0 | arc list "nearest first" / "output format not read" | only the first entry is the nearest; the rest in reverse order of acceptance | Executed |

The round-1 contract code is kept as it was so that its pinned vectors stay valid; a
rebuild should follow the executed bodies of the round-2 modules. The other documents'
own correction tables (`combat-movement.md` 7, `combat-player-melee.md` 8,
`combat-player-defence.md` 7, `combat-projectiles.md` 10, `combat-spells.md` 8,
`combat-monster-death.md` 7) have the details.

Proposed ledger rows (for whoever edits `FINDINGS.md`), in addition to section 12's:

| # | Finding | Kind | Evidence |
|---|---|---|---|
| new | A heavy attack that hits a creature makes 200 shared draws (`Player_hitSparks`), on the real player only | Executed | 0x1b6f34, 0x1bcc20 |
| new | A standing player draws the shared seed once every tick (`Player_idleFidget`, exactly four tracks) | Executed (pieces), composed | 0x1bc3d0 |
| new | Projectiles and spell effects destroy themselves in their own run; handles to them read 0 at once | Executed | 0x15157c-0x152510, 0x1bb368 |
| new | Of several enemies an arrow overlaps in one frame, only the first in box order is hit (hit state +0xcc), unless it pierces | Executed | 0x152a18 |
| new | `world_collectObjectsInArc` lists are partnerless: a destroyed object stays listed, and Holy Strike then homes on whatever object reuses its block | Inferred (from executed pieces) | 0x1614f0, `test_the_candidate_list_outlives_its_target` |
| new | `creature_findPlayerInCone` caps the distance at `far`; `creature_findEnemyInCone` does not | Executed | 0x10ca70, 0x10cf78 |

### 15.7 What was run

Every difftest below was re-run at its full case count on 2026-10-17 with
`python3 tools/difftest_combat_<area>.py <your SLUS_209.73>` (seed 20973): calls with
arguments, every byte stored outside the stack, the shared seed and its draw count, the
result. **157,137 cases compared, 0 mismatches** in round 2, plus 12,000 ticks of the
original `Player_run` against `ref_player.Tick` in state 1 (combo runs, 0 mismatches);
round 1's own difftest again 30,988 cases, 0 mismatches. Each area document has its
coverage table; in brief:

| Difftest | Entry points | Compared | Refused | Lowest coverage, and why |
|---|---|---|---|---|
| `combat_move` | `obj_moveWithCollision`, `creature_moveSimple`, `Player_move` (all modes; and the round-1 still-stick domain), `Player_animStep`, `Player_clampToScreen` | 18,000 | 0 | still-stick `Player_move` 825 of 1,220 (by design); moving 1,204 of 1,220 (nops, a dead delay slot) |
| `combat_melee` | `Player_pickAttackAnim`, `Player_meleeHit` (all branches; and round 1's generator), `Player_hitSparks`; combo runs | 12,000 + 12,000 ticks | 0 | `meleeHitFull` 425 of 432 (the null-target throw, nops) |
| `combat_ptick` | `Player_takeDamage` (block, Holy Shield), `Player_blockSparks` (silent 0), `Player_interact` (nothing in reach), `Player_processDamage` (all but object construction) | 11,606 | 394 | `blockSparks` 198 of 408 (silent != 0 not run); `interact` 142 of 416 (no interactable) |
| `combat_ranged` | `obj_moveAndCollide`, `Projectile_ctor`, `MissileWeapon` ctor / run / onTouch / slot 17 / dtor, `playerProjectile` ctor / run / dtor | 30,000 | 0 | `MissileWeapon_run` 317 of 1,024 (kinds 1, 2, 5, 6 not run); `playerProjectile_run` 171 of 674 (potions) |
| `combat_spells` | `world_collectObjectsInArc`, `world_collectInSphere`, `world_damageInRadius`, five effect destructors | 32,000 | 0 | all but padding |
| `combat_monsters` | sight, hit, knock-back, cooldown and notify helpers; four destructors; `Creature_deadUpdate` with decal; `Creature_dropLoot`; Goblin death | 53,531 | 469 | Goblin set-state 233 of 613 (death state only) |

Agreement with round 1 on its domain: `player_take_damage` 2,399 of 2,399 and
`player_process_damage` 1,437 of 1,437 cases identical to the `_full` bodies; round 1's
unarmed `player_melee_hit` identical on 3,000; round 1's `player_move` differs in calls on
all 2,748 of its in-domain cases (15.6). `MeleeRuntime`, and the round-1 `Runtime` with
`DefenceModel` swapped in, reproduce round 1's 80-tick duel pin.

Each area also has synthetic-fixture tests (`tools/test_ref_combat_{move,melee,ptick,
ranged,spells,monsters,full}.py`); they are evidence about the models, not about the game.
Nothing was run on a console, in PCSX2 or on the live rig.

## 16. Round 3 (2026-10-20)

`docs/spec/combat-round3.md` is the prose. `tools/ref_combat_round3.py` adds the bodies.
Round 1 and round 2 modules, APIs and pinned vectors are unchanged. `ArrowModel`
subclasses `RangedModel` and calls it for kinds 0 and 3.

Executed against the original (`tools/difftest_combat_round3.py`, seed 20973, 40 cases
each, 0 mismatches):

| Entry | Address | Instructions |
|---|---|---|
| `DiseaseCloud_ctor` | `0x2ce610` | 52 of 52 |
| `DiseaseCloud_run` | `0x2ce6e0` | 547 of 551 (the occupied descriptor-slot arm was not taken) |
| `GutChunk_ctor` | `0x201958` | 53 of 53 |
| `StrongStancePhantom_ctor` | `0x1618d4` | 95 of 95 |
| `StrongStancePhantom_run` | `0x161a54` | 33 of 33 |
| `MissileWeapon_run` kind 1 | `0x15153c` | 392 of 1,024 |
| `MissileWeapon_run` kind 2 | `0x15153c` | 201 of 1,024 |
| `MissileWeapon_run` kind 5 | `0x15153c` | 326 of 1,024 |
| `MissileWeapon_run` kind 6 | `0x15153c` | 247 of 1,024 |

The cloud's `damage_apply` has no attacker, which agrees with research-fx
`docs/effects.md` section 17. `disease_attach` (`0x1e9e28`) is composed onto the
already-executed disease-effect constructor; it is not a slice of `damage_apply`.
`PhProp_ctor` and `Creature_ctor` stay callbacks. A hit on kinds 1, 2, 5 and 6 stores
0 at `+0xec` and destroys the arrow on that frame, after `light_relink`. The stone-hit
effect remains kinds 0 and 3.

Not executed this round: potion kinds 1–3 (`playerProjectile_run` `0x1ba940`; kind 1
draws the shared seed inline), deflection inside the runtime, the bow release in
player state 0, the Holy Shield light, `Player_blockSparks` with silent != 0, further
monster death states, and combat paths of the remaining skills.

`python3 -m unittest tools.test_ref_combat_round3`: 13 tests, the fixtures only.

## 17. Round 4 (2026-10-20)

`docs/spec/combat-round4.md` is the prose. `tools/ref_combat_round4.py` adds the bodies.
Round 1, round 2 and round 3 modules, APIs and pinned vectors are unchanged.
`PotionModel` subclasses `RangedModel` and calls it for kinds other than 1, 2 and 3.

Executed against the original (`tools/difftest_combat_round4.py`, seed 20973, 40 cases
each, 0 mismatches; seed 7 the same):

| Entry | Address | Instructions |
|---|---|---|
| `playerProjectile_run` kind 1 | `0x1ba940` | 452 of 674 |
| `playerProjectile_run` kind 2 | `0x1ba940` | 203 of 674 |
| `playerProjectile_run` kind 3 | `0x1ba940` | 325 of 674 |
| `SpellHolyShield_absorb` | `0x2e8534` | 206 of 206 |
| `Player_blockSparks` silent ≠ 0 | `0x1b9658` | 302 of 408 |

Kind 1 draws the shared seed inline for two flame particles and one more, every run.
A hit or an expiry lays five `LooseFire` objects and five decals. Kind 2 lays one
`poisonGasSpell` (300 frames, radius 20, damage 5) when the pool returns a block.
Kind 3 lays a ring and `world_damageInRadius` with flags `0x40840`, skipped when the
level name is `innpit`, then a decal only when the ground is strictly within 4, and a
light. A potion does not clear bit 1 of the move result. The stone-hit effect stays
kinds 0, 4, 5 and 6.

`SpellHolyShield_absorb` draws the spell's own generator, not the shared seed. It lays
241 particles. A light is made only when `+0x1c` is at most 0, and that word then
becomes `0x3e86a832`. The result is the skill's slot 10 times `0x3c23d70a`. A sample
count of 0 is not modelled.

`Player_blockSparks` with a nonzero silent still reads the two hand points, then five
shared-seed sparks on each sample of the record object's model. Silent 1 and 2 spawn;
any other nonzero silent draws the balls and spawns nothing. Both jal sites pass 0.
`DefenceModel.player_block_sparks` still refuses a nonzero silent. The 106
instructions of the silent == 0 arm stay the round-2 difftest.

`python3 -m unittest tools.test_ref_combat_round4`: the fixtures only.
`RangedModel.thrown_run` still refuses a potion.

## 18. Round 5 (2026-10-20)

`docs/spec/combat-round5.md` is the prose. `tools/ref_combat_round5.py` adds the
bodies. Round 1 through round 4 modules, APIs and pinned vectors are unchanged.

Executed against the original (`tools/difftest_combat_round5.py`, seeds 20973 and 7,
0 mismatches):

| Entry | Address | Instructions |
|---|---|---|
| hit-effect angle in `Creature_processDamage` | `0x110e60`, `0x110e80` | 168 of 1515 |
| metal-spark angle in `Creature_processDamage` | `0x11110c`, `0x11111c` | 288 of 1515 |
| gib angles in `Creature_processDamage` | `0x111b44`, `0x111ce4` | 304 of 1515 |
| `Player_blockSparks` angle, silent 0 | `0x1b97dc`, `0x1b9800` | 198 of 408 |
| `AntQueen_fadeBankTracks` | `0x2385dc` | 30 of 30 |
| `AntQueen_updateBank` | `0x238448` | 101 of 101 (seed 7: 100) |
| `AntQueen_run` states 0 and 1 | `0x236f78` | 101 of 607 |
| `Skeleton_run` states 0 and 1 | `0x2a6864` | 143 of 809 |
| `Soul_run` phase gate | `0x2a9870` | 126 of 1062 |
| `Soul_isDemonNear` | `0x2ab2b4` | 58 of 58 |
| `SpellHolyShield_absorb` sample point | `0x2e8534` | 206 of 206 |
| `MultiFireProjectile_run` | `0x2da2bc` | 165 of 165 |

The live session stops AntQueen on the call it names `aq_ground`, Skeleton on the
slot-25 class check, and Soul on the call it names `demon` at tick 9. Those calls
are the fade at `0x237028`, slot 25 with the forces below, and `Soul_isDemonNear`
when `(g_simFrame XOR the byte at +0x230)` has a clear low nibble. The word at
`+0x44` is the generator. `Creature_updateActive` returning 0 leaves Skeleton and
Soul before that switch. AntQueen still reaches the fade.

Slot 25 passes 0 for the queen and for a skeleton's first call. A skeleton whose
kind word `+0x3d0` is 4 passes 1 on the second call when the first returned 0.
The client's refusal fires for any class other than Gnaw before it reads that
argument.

The hit-effect angle is the sign-extended hit halfword `+0x2e0` plus `0x7fff`.
The metal sparks and both block-spark cosines receive the sign-extended facing
halfword `+0x38`. Each gib chunk's angle is that hit halfword plus a
sign-extended sum of a bias and one own draw. The sine call receives the same
register as the cosine.

Holy Shield's 241 particles read the caster's pose through `model_getSamplePoint`
at scale 1. A missing pose is not modelled. `MultiFireProjectile_run` is the
MaleDarkElf volley, 165 of 165 instructions. Its `onHit` stays the description in
`docs/spec/skills-35-68.md`.

`python3 -m unittest tools.test_ref_combat_round5`: the fixtures only. 863 unit
tests pass from `python3 -m unittest discover -s tools -p 'test_*.py'`.

## 19. Round 6 (2026-10-20)

`docs/spec/combat-round6.md` is the prose. `tools/ref_combat_round6.py` adds the
bodies. Round 1 through round 5 modules, APIs and pinned vectors are unchanged.
The sentence above that leaves `MultiFireProjectile_onHit` to the skills
description is the state at round 5. This round executes that hit.

Skills 1–101 were already matched by `difftest_skills_a.py`, `difftest_skills_b.py`
and `difftest_skills_c.py`. This round is the handlers those tests left as
call-outs.

Executed against the original (`tools/difftest_combat_round6.py`, seeds 20973 and
7, 58 cases each, 0 mismatches):

| Entry | Address | Instructions |
|---|---|---|
| `poisonGasSpell_run` | `0x1fd0f0` | 296 of 303 |
| `DiseaseCorpse_run` | `0x2ce4a4` | 91 of 91 |
| `MultiFireProjectile_onHit` | `0x2da610` | 198 of 198 |
| `MultiFireProjectile_end` | `0x2da928` | 73 of 73 |
| `SmokeGen_run` | `0x31c898` | 132 of 139 |
| `Pustule_run` | `0x30bde0` | 435 of 435 |
| `SpellArena_run` | `0x305bbc` | 184 of 184 |
| `SpellHornOmenEffect_ctor` | `0x2fc574` | 39 of 39 |
| `SpellHornOmenEffect_run` | `0x2fc684` | 514 of 514 |
| `SpellPlanarSteelEffect_ctor` | `0x2fb728` | 127 of 127 |
| `SpellPlanarSteelEffect_run` | `0x2fb9b4` | 638 of 638 |

Gas damage flags are `0x01000040`. Smoke damage flags are `0x0100c040`. A
multi-fire hit skips a player-flagged victim on mask `0x01000040`, and skips a
creature (flag `0x20`) whose word `+0xa8` has bit `0x04000000`. The hit
recomputes its range from skill slots 13 and 10. It does not read the cast-time
minimum and maximum, and it has no already-ended test. Monster spread uses a
fraction in `[0, 1)`, so a positive stat takes the `+0.5` side. The box capacity
argument on these queries is `0x40`. Seven descriptor instructions in the gas
cloud and seven in the smoke generator do not run: the later-slot search is dead
because slot 0 is filled first.

`DiseaseCloud_ctor` and `SmokeGen_stepParticles` stay stubs. `StaticFire_run`
stays the FX difftest. Deflection inside this runtime, the bow release composed
into it, further monster deaths, Skeleton past state 1, AntQueen past state 1,
Soul's thrown hits, and a nonzero silent argument to `Player_blockSparks` stay
open. Spell destructors other than the two the skills difftest already follows,
and Hammer states 1 and 2, stay unmodelled. Haze kind 3 stays with the FX work.

`python3 -m unittest tools.test_ref_combat_round6`: the fixtures only. 877 unit
tests pass from `python3 -m unittest discover -s tools -p 'test_*.py'` once
stdlib `dis` is loaded first.

