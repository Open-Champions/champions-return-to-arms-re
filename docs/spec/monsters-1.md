# Monster classes, batch 1: SmallSpider, Gnaw, Mosquito, Scorpion, Badger

This document is the prose of `tools/ref_monsters_1.py`, a reference model of five ordinary
monster classes of `SLUS_209.73` (US v2.00), written on top of the creature base class
(`docs/spec/creature-tick.md`, `tools/ref_creature.py`) and of the base-class pieces in
`tools/ref_arena_monsters.py` (`docs/spec/arena-monsters.md` section 2). The conventions of
`docs/spec/arena-monsters.md` section 0 apply and are not repeated: `c`, `clock`, `frame`,
`ev`, `anim`, `see(near, far, facing, arc)`, `cone(…)`, `set(n)`, "clip +0x54", **own
draw**, **shared draw**.

Every statement in sections 2–7 was read from the instructions at the address given and
then **executed**: `tools/difftest_monsters_1.py` runs the original constructors, run
functions and set-state functions under the instruction interpreter `tools/ee_emu.py`,
with the creature base class underneath running for real, and compares each call with the
model (section 11 has the counts and the coverage). **[O]** marks what was read but not
executed, **[I]** what is inferred. Nothing here was run on a console or a whole-machine
emulator.

**The batch was cut short.** Ten classes were chosen (section 1); five are done and
matched, five were not started. Section 13 says exactly what is missing.

## 1. The classes of this batch

The rule: the monsters a player meets most — the common melee and ranged enemies of the
early and middle levels (undead, the orc and goblin kind, spiders and insects, animals, and
their archer variants) — and among those the ones whose run and set-state functions are
smallest first. Not taken: `Horsemen`, `Skelight`, `Zek` (done in
`docs/spec/arena-monsters.md`), bosses, mounts and vehicles, and the friendly or summoned
creatures (`CastBadger`, `Mermaid`, `Gnome`, …).

Sizes are bytes of code from the function index (`ghidra_funcs.tsv`); "run + set" is the
sorting key.

| # | Class | Factory type names | Table | Object size | Constructor | Run | Set-state | Other functions of the class | run + set | State |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `SmallSpider` | `SmallSpider` | 0x50fd40 | 0x3c8 | 0x2ab450 (320) | 0x2ab5d8 (300) | 0x2ab704 (476) | slot 6 touch 0x2ab8e0 (120) | 776 | **matched** |
| 2 | `Gnaw` | `Gnaw` | 0x515038 | 0x3c8 | 0x26741c (488) | 0x267654 (952) | 0x267a0c (744) | — | 1696 | **matched** |
| 3 | `Mosquito` | `Mosquito*` | 0x516a08 | 0x3c8 | 0x297788 (652) | 0x297b30 (1060) | 0x297f54 (888) | lose a part 0x2982cc (332) | 1948 | **matched** |
| 4 | `Scorpion` | `Scorpion` | 0x50fe88 | 0x3d0 | 0x2a4d68 (712) | 0x2a5068 (1412) | 0x2a55ec (1028) | sever a part 0x2a59f0 (260) | 2440 | **matched** |
| 5 | `Badger` | `Badger*`, `SnoBadge` | 0x510f30 | 0x3d0 | 0x244018 (776) | 0x244380 (1820) | 0x244aa4 (936) | slot 11 0x244a9c (empty) | 2756 | **matched** |
| 6 | `Vampire` | `Vampire` | 0x50f968 | 0x3c8 | 0x2b69d0 (516) | 0x2b6bfc (1548) | 0x2b7208 (1244) | — | 2792 | not started |
| 7 | `Ogre` | `Ogre` | 0x517220 | 0x468 | 0x29fad0 (740) | 0x29fe50 (1980) | 0x2a060c (840) | — | 2820 | not started |
| 8 | `WarBoar` | `WarBoar*` | 0x517cf0 | 0x3d8 | 0x2ba03c (772) | 0x2ba3a0 (2232) | 0x2bac60 (852) | slot 11 0x2bac58 (empty) | 3084 | not started |
| 9 | `Gremlin` (archer) | `Gremlin` | 0x515358 | 0x460 | 0x26e08c (896) | 0x26e4c4 (2516) | 0x26ee98 (648) | — | 3164 | not started |
| 10 | `Ghoul` | `Ghoul*`, `GhulBlue*` | 0x5104f0 | 0x3d8 | 0x266088 (880) | 0x266420 (1932) | 0x266c68 (1676) | slot 12 nearby event 0x266bac (188) | 3608 | not started |

The draw functions (0x2ab590, 0x267604, 0x297a14, 0x2a5030, 0x244320) are presentation and
are not part of the model **[O]**.

All five matched classes use the base body for every virtual slot except 4 (run), 5
(draw), 27 (set-state), and: `SmallSpider` slot 6; `Badger` slot 11 (an empty body).
Slot 2 (take damage) is `Creature_takeDamage` in all five.

## 2. What the five share

### 2.1 The head of the tick

```
Creature_processDamage(c, model);  Creature_run(c, model)       (its result is tested; it is always 0)
if Creature_updateActive(c) == 0:  return                       NOTHING below runs for an inactive creature
ev = Creature_stepAnim(c; 1.0);  Creature_applyKnockback(c; k)
slot 23 (c, 0)                                                  target pick — not SmallSpider
switch (state)
```

`model` is `*(def + 0xc)`, except `Gnaw`, which asks slot 16 (the same value through the
base body). `k` is 1.0 (`SmallSpider`, `Gnaw`), 1.5 (`Mosquito`), 0.5 (`Scorpion`), 0.2
(`Badger`). The state is read as an unsigned 16-bit number where the switch has a jump
table (all but `SmallSpider`).

All five return when the activity test says "inactive": the animation step, the target
pick, the whole state switch and every own draw in it wait until the creature is active
again (FINDINGS D41; section 9).

### 2.2 Call-outs added to the two models underneath

| Function | Arguments as the classes pass them |
|---|---|
| `Creature_hitTargetAtReach` 0x1196e8 | (creature, min, max, attack rating, damage flags, descriptor or 0; reach) |
| `Creature_hitTargetInArcEdge` 0x119850 | as `Creature_hitTargetInArc` |
| `GutChunk_ctorFromProp` 0x201ad0 | (block, position, facing, model, animation state, words 0, 2 and 4 of the class definition; 1.0) |
| `anim_randomizeTopTime` 0x16d0b8 | (animation state): phase of the top clip from the cosmetic seed |

`loot(a, b, c, item)` below is `Creature_dropLoot(c, position, facing, item; 36.0, 2.0, a,
b, c, 0.25)`. `start(clip, flags; blend)` is `anim_start` (blend 0.1 unless given),
`swing(clip, flags)` is `anim_startBlendInOut(…; 0.1, 0.1)`, `sync` is
`anim_syncToSimFrame`.

### 2.3 Shedding a piece (from the `pool_new` calls at 0x298378 and 0x2a5a50)

`Mosquito` and `Scorpion` end their part-loss functions the same way: `pool_new(0x268)`
and, with a block, `GutChunk_ctorFromProp` at the creature's position and facing, then the
block's `+0x1c4` raised by 2.0. Before that both call `model_buildHideMask(model, +0xe8)`
twice: once with the old variant word (result dropped) and once with the new one, whose
result is the show mask `+0x220`.

### 2.4 `str_prefixDiffers` 0x159c20 (text, prefix) → 0 or 1

0 when the text starts with the prefix. An upper-case letter on either side (bit 0 of the C
library's class table at 0x5628e1, indexed by the signed character) is lowered by adding
0x20 before the compare. The object factory's prefix test; `Mosquito_ctor` uses it.

### 2.5 Software doubles in two constructors

`Gnaw_ctor` and `Scorpion_ctor` compute their scale through the library's double routines
(float → double 0x3aef58, add 0x3af410, multiply 0x3af4d0, double → float 0x3afb90), which
truncate (`tools/ref_core.py` 8b). Which routine multiplies and which adds was settled by
running them.

## 3. SmallSpider

A harmless ambient creature: it has no target, attacks nothing, and dies when a player
touches it.

### 3.1 Layout

No field beyond the base. `+0xf4` is the clock value until which it sits still.

### 3.2 Constructor — `SmallSpider_ctor` 0x2ab450 (object, type name, position, facing, properties)

`Creature_ctor(…, def 0x502818, …; 1.0)` (one shared draw in `GameObject_ctor`, one own
draw in `Creature_setStats`); table; move speed 50; radius 5 (10 is stored first); turn
rate 0.7; kind `+0xb4 = 0x12`; scale 0.2; `+0x64 = 1.0`; `+0xec = frame`; creature flags |=
0x8004001000 (0x4000000: picks no target and is nobody's enemy); the facing stored again;
state 0 stored directly; `anim_push(clip +0x3c, 1)`; `anim_randomizeTopTime`;
`obj_runEvery60`; `Creature_init`. No own draw, no event table, no property.

### 3.3 Run — `SmallSpider_run` 0x2ab5d8

The head of 2.1 without the target pick, then:

| State | What it does |
|---|---|
| 0 | `+0xf4 < clock` → `set(1)` |
| 1 | `Creature_moveToDest(c)` (which calls `set(0)` on arrival) |
| 0x14 | `Creature_deadUpdate(c, ev, zero vector, 0; 10.0)` |
| anything else | nothing |

### 3.4 Set-state — `SmallSpider_setState` 0x2ab704

After `Creature_filterState`:

| State | Effect |
|---|---|
| 0 | **one own draw** `d`: `+0xf4 = clock + 120 + d % 300`; `start(+0x3c, 3; 0.3)` |
| 1 | `Creature_clearPath`, `Creature_pickWanderDest`, `start(+0x4c, 3; 0.3)` |
| 5, 0x10, 0x12, 0x13 | ignored: the state stays what it was (no reaction, no stun, no cooldown state) |
| 0x14 | death, below |
| anything else | the number is stored, nothing is done — and the run function has no way out of it |

**Death:** object flags |= 9; **three own draws** `d1, d2, d3`:
`decal_add(position, s16(d1), 6, 1; f32(10 + d2 % 10))`, then
`start(+0x1c + 8 (d3 & 3), 6; 0.3)` (one of four death clips); for a hidden spider (object
flag 2) `anim_jumpTopToEnd`; slot 28 `(c, 0)`. No loot call. The draws are made whatever
the local decal option says; `decal_add` is a call-out.

### 3.5 Touched — `SmallSpider_onTouch` 0x2ab8e0 (c, toucher), slot 6

```
if toucher and state != 0x14 and toucher.flags & 0x40:  slot 27 (c, 0x14)
Creature_onTouch(c, toucher)                                    the base body (bit 59)
```

The only test of the toucher is object flag 0x40 (0x2ab90c–0x2ab914). The prediction copy
of a local player carries 0x40 too. See section 10.

## 4. Gnaw

### 4.1 Layout

No field beyond the base. `+0xf4` is written by the constructor and read by nothing.

### 4.2 Constructor — `Gnaw_ctor` 0x26741c (object, type name, position, facing, properties)

`Creature_ctor(…, def 0x5000a0, …; 10.0)`; table; kind 1; turn rate 1.2; radius 6; move
speed 0; `+0xec = frame`; `+0xf4 = frame + 300`; creature flags |= 0x200001000. **One own
draw** `d`: scale `+0xdc = (float)((double)(f32(d) × 2⁻¹⁶) × A + B)` with the doubles at
0x545ea0 (0.3) and 0x545ea8 (0.449999988…, the single 0.45 widened), every step truncated:
between 0.45 and 0.75. `anim_clear`; `Gnaw_setState(c, 0)` (direct); `obj_runEveryFrame`
— every frame, not a 60-frame list; event 0.2 s → bit 0 on entries 3, 4, 5 (the three
bite clips); `Creature_init`.

### 4.3 Run — `Gnaw_run` 0x267654

| State | What it does | Leaves by |
|---|---|---|
| 0 | slot 25 `(c, 0)` | seen → `set(3)`; else away from home → `set(1)` |
| 1 | not seen: `Creature_moveToDest` | seen → `set(3)` |
| 3 chase | `see(0, 6, facing, 8000)` → `set(5)`. Else `see(0, 6, facing, 0x7fff)` → `Creature_turnToTarget`. Else `Creature_moveToTarget` | no target → `set(0)` |
| 5 | `see(0, 6, facing, 8000)` → `set(6)`. Else `see(0, 6, facing, 0x7fff)` → turn | else not rooted → `set(3)` |
| 6 bite | `Creature_turnToTarget`; on `ev & 1`: `Creature_hitTargetInArc(c, facing, 8000, +0xd0, +0xd2, +0xd4, flags 8, no descriptor; 0, 6)` | `anim & 8` clear → `set(5)` |
| 0x10 | not ready: `Creature_fleeFromTarget(c, 0)` | ready → `set(0)` |
| 0x12 | (reachable only by a direct store: set-state refuses it) | `anim & 0x10` clear → `set(5)` |
| 0x13 | | not stunned → `set(3)` |
| 0x14 | `Creature_deadUpdate(c, ev, zero vector, 1; 20.0)` and `obj_delete(c)`, on every tick it is still run | never: no corpse |
| 2, 4, 7–0xf, 0x11, 0x15 and up | `set(0)` | at once |

The facing argument of the sight tests is the creature's own facing even in the
"any direction" test (arc 0x7fff).

### 4.4 Set-state — `Gnaw_setState` 0x267a0c

| State | Effect |
|---|---|
| 0 | `start(+0x1c, 3)` — the first bite clip, looping: the class has no idle clip |
| 1 | `Creature_clearPath`, `Creature_pickWanderDest`, `start(+0x3c, 0x803)`, `sync` |
| 3 | `Creature_clearPath`, `start(+0x3c, 0x803)` (no sync) |
| 5 | **one own draw** `d`: `start(+0x1c + 8 (d % 3), 3)`, `sync` |
| 6 | **one own draw** `d`: `swing(+0x1c + 8 (d % 3), 0x808)` |
| 0x10 | cooldown `+0x318 = 60`; `Creature_clearPath`, `start(+0x34, 0x803)`, `sync` |
| 0x12 | ignored: the state stays (no hit reaction) |
| 0x13 | `start(+0x1c, 3; 0.3)` |
| 0x14 | death, below |
| anything else | state **0** is stored; no clip, nothing else |

**Death:** six times, with the spot `(x, y, z + 24.0)`: on the first two passes
`pool_new(0x268)` and, **only with a block**, one own draw `d`,
`GutChunk_ctor(block, spot, d % 3, 2; 1.0)`, `PhProp_initPhysics(block, 0x12)`; on every
pass `fx_spawn(9, spot)`. Then `start(+0x1c, 0x803)` and slot 28 `(c, 0)`. No
`Creature_dropLoot`.

## 5. Mosquito

### 5.1 Layout

No field beyond the base. `+0xf4` is written (constructor, set-state 0 and 5) and read by
nothing in the class. The model-variant word `+0xe8` collects the parts already shed.

### 5.2 Constructor — `Mosquito_ctor` 0x297788 (object, position, facing, properties, type name)

`Creature_ctor(…, def 0x5017a0, …; 10.0)`; `+0x28 = 0x1e`; kind 0x12; table; turn rate
1.2; radius 10; move speed 0; `+0xec = frame`; `+0xf4 = frame + 300`; creature flags |=
0x8000001000; resistances `+0x5c = −0.2` (0xbe4ccccc), `+0x64 = +0x68 = 1.0`. Scale
`+0xdc = 0.7` when `str_prefixDiffers(type name, text at 0x549af0)` is non-zero — every
mosquito but the large kind. `anim_clear`; `Mosquito_setState(c, 0)` (direct: one own
draw); `obj_runEvery60`; events; `Creature_init`.

| Entry (clip) | Used by | Events |
|---|---|---|
| 3, 4 (+0x1c, +0x24) | state 6, one of two | 0.2 s → 1 |
| 5 (+0x2c) | death clip | 1.0 s → 0x80 |
| 6, 7 (+0x34, +0x3c) | death clips | 1.5 s → 0x80 |
| 8 (+0x44) | death clip | 0.5 s → 0x80 |

### 5.3 Run — `Mosquito_run` 0x297b30

| State | What it does | Leaves by |
|---|---|---|
| 0 | slot 25 `(c, 0)` | seen → `set(3)`; else away from home → `set(1)` |
| 1 | not seen: `Creature_moveToDest` unless `anim & 0x20` | seen → `set(0)` |
| 3 chase | nothing while `anim & 0x10`. `see(0, 40, facing, 6000)` → `set(6)`. Else `see(0, 40, facing, 0x7fff)` → turn. Else `Creature_moveToTarget` | no target → `set(0)` |
| 5 | `Creature_turnToTarget`; `see(0, 40, facing, 6000)` → `set(6)` | no target → `set(0)`; else not rooted → `set(3)` |
| 6 bite | `Creature_moveBy(c, 0)`; with a target: on `ev & 1` `Creature_hitTargetInArcEdge(c, facing, 6000, +0xd0, +0xd2, +0xd4, flags 4, no descriptor; 0, 40)`, then `Creature_turnToTarget` | `anim & 8` clear → `set(3)` |
| 0x10 | not ready: `Creature_fleeFromTarget(c, 0)` | ready → `set(0)` |
| 0x12, 0x17 | `Creature_moveBy(c, 0)` | `anim & 0x10` clear → `set(3)` |
| 0x13 | | not stunned → `set(3)` |
| 0x14 | `Creature_moveBy(c, 0)`, `Creature_deadUpdate(c, ev, zero vector, 0; 15.0)` | never |
| 2, 4, 7–0xf, 0x11, 0x15, 0x16, 0x18 and up | `set(0)` | at once |

Nothing in the class requests state 0x17.

### 5.4 Set-state — `Mosquito_setState` 0x297f54

| State | Effect |
|---|---|
| 0 | `start(+0x84, 3)`; **one own draw** `d`: `+0xf4 = clock + d % 120` |
| 1 | `Creature_clearPath`, `Creature_pickWanderDest`, `start(+0x64, 0x803; 0.5)` |
| 3 | `Creature_clearPath`, `start(+0x64, 0x803)` |
| 5 | `start(+0x84, 3)`; **one own draw** `d`: `+0xf4 = clock + 60 + d % 120` |
| 6 | **one own draw** `d`: `swing(+0x1c + 8 (d & 1), 0x808)` |
| 0x10 | cooldown `+0x318 = 60`, then as 3 |
| 0x12 | **two own draws**: `swing(+0x6c + 8 (d1 & 1), 0x810)`, then `Mosquito_losePart(c, d2 % 3 + 1)` |
| 0x13 | `start(+0x84, 3)` |
| 0x14 | `loot(1.6, 0.6, 1.4, 0)`; **two own draws**: `start(+0x2c + 8 (d1 & 3), 0x806; 0.2)`, `Mosquito_losePart(c, (d2 & 3) + 4)`; slot 28 `(c, 0)` |
| 0x17 | **one own draw** `d`: `swing(+0x4c + 8 (d % 3), 0x810)` |
| anything else | state **0** is stored, nothing else |

Last, in every row: creature flag 0x100000 (no water test in `Creature_moveBy`) is cleared
when the stored state is 0 or 0x14 and set otherwise.

### 5.5 `Mosquito_losePart` 0x2982cc (c, part)

Part → bit of `+0xe8`: 1, 2 → 0x10; 3 → 0x40; 4 → 2; 5 → 1; 6 → 4; 7 → 8; any other number
sets none. Then 2.3. So every hit reaction that reaches set-state 0x12 sheds a piece — a
new 0x268-byte object each time the pool has a block, also when the bit was set already.

## 6. Scorpion

### 6.1 Layout beyond the base

| Offset | Type | Meaning |
|---|---|---|
| +0x3c8 | u8 | skin 0 / 1, read by the draw function **[O]** |

`+0xf4`: in state 0 the clock value after which it wanders; in states 6 and 7 a countdown.
`+0xd0`, `+0xd2` (damage low, high) are rewritten by the sting (6.3).

### 6.2 Constructor — `Scorpion_ctor` 0x2a4d68 (object, type name, position, facing, properties)

`Creature_ctor(…, def 0x502238, …; 10.0)`; table; `+0x28 = 0x46`; kind 0x12; turn rate
1.2; move speed 0; `+0xec = frame`; `+0x64 = 0.4`; creature flags |= 0x8000001000;
`+0xe8 = 0`. **Two own draws**: `d1` gives the scale
`+0xdc = (float)((double)(f32(d1 % 6) × 0x3d4ccccc) + 0.75)` — 0.75 to 1.0 in six steps —
and the radius `30.0 × scale`; `d2` gives the skin `+0x3c8 = d2 & 1`. Show mask from
`model_buildHideMask(model, 0)`; `anim_clear`; `anim_push(clip +0x84, 1)`;
`obj_runEvery60`; events; `Creature_init`.

| Entry (clip) | Used by | Events |
|---|---|---|
| 5, 6, 7 (+0x2c, +0x34, +0x3c) | state 6, the three claw clips | 0.3 s → 1 |
| 8 (+0x44) | state 7, the sting | 0.3 s → 1 |
| 0xb, 0xc (+0x5c, +0x64) | death clips | 0.5 s → 0x80 |

### 6.3 Run — `Scorpion_run` 0x2a5068

| State | What it does | Leaves by |
|---|---|---|
| 0 | slot 25 `(c, 0)` | seen → `set(3)`; else away from home → `set(1)`; else `+0xf4 < clock` → `set(1)` |
| 1 | not seen: `Creature_moveToDest` | seen → `set(0)` |
| 3 chase | `see(0, 20, facing, 6000)` → `set(6)`. Else `see(0, 20, facing, 0x7fff)` → turn. Else `Creature_moveToTarget` | no target → `set(0)` |
| 5 | | `see(0, 20, facing, 6000)` → `set(6)`; else not rooted → `set(3)` |
| 6 claw, 7 sting | below | |
| 0x10 | not ready: `Creature_fleeFromTarget(c, 0)` | ready → `set(0)` |
| 0x12 | | `anim & 0x10` clear → `set(3)` |
| 0x13 | | not stunned → `set(0)` |
| 0x14 | `Creature_deadUpdate(c, ev, zero vector, 0; 25.0)` | never |
| 0x17, 0x18 | `Creature_moveBy(c, 0)` | `anim & 8` clear → `set(3)` |
| 2, 4, 8–0xf, 0x11, 0x15, 0x16, 0x19 and up | nothing at all | only from outside |

States 6 and 7 (0x2a529c):

```
if target:
    if ev & 1:
        state 6:  Creature_hitTargetAtReach(c, +0xd0, +0xd2, +0xd4, flags 8, no descriptor; 36.0)
        state 7:  if g_difficultyIdx(0x4f719c) == 2:  +0xd0 = +0xd0 / 4;  +0xd2 = +0xd2 / 4     toward zero, STORED
                  if g_difficultyIdx == 3:            +0xd0 = +0xd0 / 8;  +0xd2 = +0xd2 / 8
                  descriptor = one effect (id 0x17, +0xd0, +0xd2, 0), built on the stack
                  Creature_hitTargetAtReach(c, +0xd0, +0xd2, +0xd4, flags 0x10004, descriptor; 36.0)
    if anim & 8:  Creature_turnToTarget(c)
if not (anim & 8):  +0xf4 −= 1                                   anim is read again after the turn
if +0xf4 > 0:  return
d = OWN DRAW;   set(0x17) if d & 1,  else set(0x18) if d & 2,  else set(3)
```

Two things follow from the order:

- The division is written back and never undone: on those two difficulty values every
  sting hit frame with a target — whether or not it connects — shrinks the damage of every
  later claw and sting of that scorpion. `g_difficultyIdx` is shared game state.
- The countdown is tested on every tick, also while the clip plays. Set-state 6 stores
  `d % 20` in it, so with a remainder of 0 (one attack in twenty) the scorpion leaves the
  attack on its **first** tick, 0.3 s before the hit frame, into a flank clip or the chase.

The descriptor is the same record the weapon holders keep: eight zero halfwords at +0x10,
two 0xff bytes at +0x20, four effect slots of (id, three values) from +0x24, all four ids
−1 first; the code then looks for the first slot that is free or already holds id 0x17,
which is always the first.

### 6.4 Set-state — `Scorpion_setState` 0x2a55ec

| State | Effect |
|---|---|
| 0 | **one own draw** `d`: `+0xf4 = clock + 120 + d % 60`; `start(+0x84, 3; 0.3)` |
| 1 | `Creature_clearPath`, `Creature_pickWanderDest`, `start(+0x94, 0x803; 0.3)` |
| 3, 0x10 | `Creature_clearPath`, `start(+0x9c, 0x803; 0.3)` (the cooldown is not set here) |
| 5 | `start(+0x8c, 3)` |
| 6 | `start(+0x8c, 3)`; **own draw** `d1`: `d1 % 6 == 0` → the state becomes **7** and `swing(+0x44, 8)`; else **own draw** `d2`: `swing(+0x2c + 8 (d2 % 3), 8)`. Then **own draw** `d3`: `+0xf4 = d3 % 20` |
| 0x12 | ignored (the state stays) when the current state is 0x13, or is 6 with `anim & 8`; otherwise `swing(+0x7c, 0x10)`. A sting (state 7) is interrupted |
| 0x13 | `start(+0x84, 3; 0.3)` |
| 0x14 | death, below |
| 0x17 / 0x18 | `start(+0x8c, 3)`, `swing(+0x6c / +0x74, 0x808)` |
| anything else | the number is stored, nothing is done |

**Death:** **own draw** `d1`; when `d1 % 3 == 0` a second one and
`Scorpion_severPart(c, d2 % 6)`; `loot(1.6, 0.6, 1.4, the item named at 0x54b648)`; **own
draw** `d`: `start(+0x5c + 8 (d & 1), 0x806; 0.3)`; slot 28 `(c, 0)`.

### 6.5 `Scorpion_severPart` 0x2a59f0 (c, part)

`+0xe8 |= 1 << (part & 31)`, then 2.3.

## 7. Badger

### 7.1 Layout beyond the base

| Offset | Type | Meaning |
|---|---|---|
| +0x3c8 | s32 | this attack has hit (cleared when an attack starts) |
| +0x3cc | u8 | variant: 1 the snow kind, anything else the ordinary one |

### 7.2 Constructor — `Badger_ctor` 0x244018 (object, type name, position, facing, properties, variant)

`Creature_ctor(…, def 0x4fecf8 + 0xa0 × variant, …; 10.0)`; table; kind 3; turn rate 1.0;
move speed 0 (walking is root motion); `+0xec = frame`; creature flags |= 0x200000000;
`+0x3cc = variant`. Variant byte 1: radius 25, `+0x28 = 0x28`, scale 0.8, `+0xe0 = −10`,
`+0x5c = −0.3` (0xbe999999), `+0x60 = 1.0`. Any other: radius 35, `+0x28 = 0x2d`,
`+0xe0 = −15`. `+0xe8 = 0` and its show mask; `anim_clear`; `anim_push(clip +0x7c, 1)`;
`obj_runEvery60`; events; `Creature_init`. No own draw.

| Entry (clip) | Used by state | Events |
|---|---|---|
| 4, 5, 6, 7 (+0x24, +0x2c, +0x34, +0x3c) | 6, 8, 10, 9 | 0.3 s → 1, 0.8 s → 2 |
| 10 (+0x54) | 7 | 0.5 s → 1, 0.9 s → 2 |
| 0xb, 0xc (+0x5c, +0x64) | death clips | 1.0 s → 0x84 |

### 7.3 Run — `Badger_run` 0x244380

| State | What it does | Leaves by |
|---|---|---|
| 0 | slot 25 `(c, 0)` | seen → `set(3)`; else away from home → `set(1)` |
| 1 | not seen: `Creature_moveToDest` | seen → `set(0)` |
| 3 chase | below | |
| 5 | with a target: `see(0, 25, facing, 7000)` or `cone(0, 25, facing, 7000)` → `set(6)` | else (and without a target) not rooted → `set(3)` |
| 6–10 attacks | below | |
| 0x10 | not ready: `Creature_fleeFromTarget(c, 0)` | ready → `set(0)` |
| 0x12 | | `anim & 0x10` clear → `set(3)` |
| 0x13 | | not stunned → `set(0)` |
| 0x14 | `Creature_deadUpdate(c, ev, zero vector, 0; 35.0)`; on `ev & 4` object flag 1 is set (the 0x84 event at the end of the death clip) | never |
| 2, 4, 0xb–0xf, 0x11, 0x15 and up | nothing at all | only from outside |

**State 3**, first match wins; `pick()` is one own draw `d`: `d % 5 == 0` → 8,
`== 1` → 9, else 6:

```
no target:                                 set(0)
see(0, 60, facing, 7000):                  set(pick())
see(25, 100, facing, 7000):                set(10)
see(0, 60, facing + 8000, 3000):           set(8)
see(0, 60, facing − 8000, 3000):           set(9)
cone(0, 25, facing, 7000):                 set(pick())
cone(0, 25, facing + 8000, 3000):          set(8)
cone(0, 25, facing − 8000, 3000):          set(9)
see(0, 20, 0, 0x7fff):                     Creature_turnToTarget
otherwise:                                 Creature_moveToTarget
```

**States 6 (front), 7, 8 (left), 9 (right), 10** (0x2447c4):

```
Creature_settle(c)
if ev & 1:
    flags = 8
    if variant byte != 1 and state is 6, 7 or 10:  d = OWN DRAW;  flags = (d % 3 == 0) ? 0x80008 : 0x40008
    Creature_hitAllEnemiesInArc(c, facing, 7000, +0xd0, +0xd2, +0xd4, flags, no descriptor; 0, radius + 25.0)
    +0x3c8 = 1
if target and anim & 8 and see(0, 10, facing, 7000):
    state 6 with +0x3c8 == 0, state 10, state 7:   Creature_turnToTarget     (6 only before its hit)
if ev & 2 and state != 6 and see(0, 60, facing, 7000):  set(6)       the chain into a front attack
if not (anim & 8):  set(3)                                       also on the tick the chain started
```

### 7.4 Set-state — `Badger_setState` 0x244aa4

| State | Effect |
|---|---|
| 0 | `start(+0x7c, 3)`; `+0xf4 = clock + 180` (nothing reads it) |
| 1 | `Creature_clearPath`, `Creature_pickWanderDest`; `start(+0x8c, 0x803)` — or `start(+0x4c, 0x803)` while the charm timer `+0x312` is non-zero; `sync` |
| 3 | `Creature_clearPath`; unless the current state is 3 or 6–10: `start(+0x4c, 0x803; 0.2)`; `sync` either way |
| 5, 0x13 | `start(+0x7c, 3)` |
| 6 / 7 / 10 | `swing(+0x24 / +0x54 / +0x34, 0x808)`; `+0x3c8 = 0` |
| 8 / 9 | `swing(+0x2c / +0x3c, 0x4808)`; `+0x3c8 = 0` |
| 0x10 | `Creature_clearPath`, `start(+0x44, 0x803)`, `sync` (the cooldown is not set here) |
| 0x12 | when the current state is 6 and `anim & 8`: nothing, the state stays 6. Otherwise **one own draw** `d`: `swing(+0x6c + 8 (d & 1), 0x10)` |
| 0x14 | object flag 1 cleared unless the creature is hidden (flag 2); `loot(2.8, 3.0, 3.0, 0)`; **one own draw** `d`: `start(+0x5c + 8 (d & 1), 6)`; slot 28 `(c, 0)` |
| anything else | the number is stored, nothing is done |

Nothing in the run function requests state 7.

## 8. Draws, generator by generator

**Shared seed 0x404464:** no function of the five classes draws it. Their call-outs do:
`GameObject_ctor` (1 per object, the creature and every `GutChunk`), `damage_apply` behind
the three hit helpers, `Creature_dropLoot`, slot 28's script and named item, and what
`docs/spec/creature-tick.md` section 13 lists for the base tick.

**Own generator `c+0x44`** (besides `Creature_setStats`' one in every constructor and the
base class's own):

| Class | Where | Draws |
|---|---|---|
| SmallSpider | set-state 0 | 1 |
| | set-state 0x14 | 3 |
| Gnaw | constructor (scale) | 1 |
| | set-state 5, 6 | 1 each |
| | set-state 0x14 | 0, 1 or 2: one per chunk the pool gave a block for |
| Mosquito | set-state 0 (so also the constructor), 5, 6, 0x17 | 1 each |
| | set-state 0x12, 0x14 | 2 each |
| Scorpion | constructor (scale, skin) | 2 |
| | set-state 0 | 1 |
| | set-state 6 | 2 (sting) or 3 (claw) |
| | set-state 0x14 | 2, or 3 when a part is severed |
| | states 6 / 7, each tick the countdown is at or below 0 | 1 |
| Badger | state 3, target or any enemy in the front cone | 1 |
| | states 6, 7, 10 on the hit event, ordinary variant | 1 |
| | set-state 0x12 (when not ignored), 0x14 | 1 each |

**Cosmetic generator 0x404460:** only inside `anim_randomizeTopTime`, called by
`SmallSpider_ctor` (a call-out here).

**Third generator 0x404468:** not used.

## 9. Reads that are not lockstep state, and what each gates

| Read | Where | What it gates |
|---|---|---|
| cflags bit 63 (active), through the result of `Creature_updateActive` — per machine only where FINDINGS D6 applies | the result of the calls at 0x2ab614, 0x2676c0, 0x297b70, 0x2a50a8, 0x2443c4 | **everything after it** in the tick of all five classes: the animation step, the target pick, the state switch with its own draws, hits, deaths' follow-up. Instances of FINDINGS D41, as wide as `Zek`'s (`docs/spec/arena-monsters.md` section 11) |
| the toucher's object flag 0x40, which the prediction copy carries | `SmallSpider_onTouch` 0x2ab90c | the spider's death: section 10 |
| the pool (`pool_new`; FINDINGS D21) | 0x267c1c (`Gnaw` death), 0x298378, 0x2a5a50 (shed pieces) | a refused block skips a `GutChunk` and its shared draw; for `Gnaw` also the own draw for its variant (the gnaw is deleted on its next tick, so nothing later reads that stream) |
| the cosmetic generator | inside `anim_randomizeTopTime`, from `SmallSpider_ctor` | the phase of the first idle clip. Nothing in the class tests an animation flag before set-state replaces the clip **[I]** |
| `g_difficultyIdx` 0x4f719c | `Scorpion_run` 0x2a531c | the sting's damage and the write-back of 6.3. Shared game state |
| `g_simFrame` | the five constructors (`+0xec`, `+0xf4`) | lockstep inside a tick |
| type-name text | `Mosquito_ctor` | the scale. Level data |

Inside call-outs, already on the ledger and not re-examined: `fx_spawn`'s camera test
(effect 9 in `Gnaw`'s death), `decal_add`'s local option (`SmallSpider`; the three own
draws are made before the call whatever the option), the status-counter decrement in
`Creature_draw` (D12).

Apart from section 10, no per-machine read was found in these five classes that is not
already on the ledger.

## 10. Proposed ledger row: the small spider's touch

Not on the ledger. FINDINGS G25 describes the base body `Creature_onTouch` 0x11a418 (bit
59, acted on only for followers and pets), and the test patch "creatures ignore being
touched by the prediction copy" rewrites that body (0x11a41c–0x11a430).
`SmallSpider_onTouch` has a test of its own in front of it and is not covered by either.

| # | What | Kind | Addresses |
|---|---|---|---|
| new | `SmallSpider`'s slot 6 kills the spider (set-state 0x14: object flags 9, three own draws, a decal, the death clip, slot 28 with its `deathScript` and `dropitem`) when the toucher has object flag 0x40. Nothing excludes the prediction copy, which carries 0x40 as well as 0x20000; the copy's own move step is what calls slot 6 of what it touches (G25, V22). A small spider touched by a machine's own copy and not, on the same tick, by the real player is therefore dead on that machine only | Observed code, executed in isolation (the test, the call and the death branch); that a copy reaches it in play is Inferred from G25 / V22 and was not run | 0x2ab8f4–0x2ab934; 0x2ab704 case 0x14 |

The words at 0x2ab90c–0x2ab918 are `8e22000c 30420040 50400009 0200202d` (load the
toucher's flags, mask 0x40, branch-likely past the call, delay slot). Excluding the copy
needs the test `(flags & 0x20040) == 0x40`, which does not fit in the one masking
instruction there; a patch would have to move code. **No patch is proposed**: none was
designed or tested.

Followed up in `docs/issues/touch-handlers.md` (FINDINGS G26, V61), which qualifies the
row above in one point and supplies the patch:

- "The copy's own move step is what calls slot 6 of what it touches" is true of
  `Creature_moveBy` only (the call at 0x114220). A player's ordinary step goes through
  `obj_moveWithCollision`, which skips the call for a copy (0x14d9ac). **Ran**: a
  predicted player that walks through a small spider with the stick does not kill it
  early.
- The copy reaches `Creature_moveBy` through `Player_run`'s scripted-control exit
  (0x1a5604), for instance while a cutscene has the players frozen in action state 1.
  **Ran** in two forced forms of that walk: the spider dies on the copy's machine only
  (first difference at tick 1530; in the frozen form silent for 280 ticks).
- The patch is at the caller, not in this handler: the section "no touch handler runs for
  a prediction copy that walks into something" (one word at 0x114220, eight in unused
  code). With it neither form differs.

## 11. What the differential test covers

`python3 tools/difftest_monsters_1.py` builds one creature through the **original
constructor**, with the game's own virtual table, six other objects and four players, and
plays 1,500 ticks per run; two runs per class (machine A and machine B, both as a net
game). A tick is: the driver acts as the rest of the game (the per-machine inputs of the
base test, timers, flags, targets, animation flags, the difficulty value, hidden or not),
damage arrives through slot 2, the class's run function runs — with the base class under
it for real — and now and then the driver asks for a state (every number, valid or not),
stores a state number no set-state would store, delivers a killing blow in a state of its
choice, or calls a helper on its own. For every call the model and the original must
agree on: the call-outs in order with arguments, the set of bytes stored and their final
values, the shared seed and the number of draws, and the result.

Result at seed 7301 (the default):

| Property | Result |
|---|---|
| calls, stores, seed, result, one-sided faults — each of the ten runs (50 lines) | PASS: 19,268 original calls compared, 0 mismatches, none unresolved |
| calls in which the original read unmapped memory | 13, all at 0x11a418: `SmallSpider_onTouch` called by the driver with no toucher, which the class code survives and the base body does not. The model stopped at the same place each time |
| shared-seed draws seen | 47, all inside the run functions and all made by the base class underneath (the corpse scavenger's draw, `docs/spec/creature-tick.md` 4.11); none by class code |

Calls compared per entry point: SmallSpider_ctor 99, SmallSpider_run 2,903,
SmallSpider_setState 342, SmallSpider_onTouch 142; Gnaw_ctor 81, Gnaw_run 2,920,
Gnaw_setState 382; Mosquito_ctor 86, Mosquito_run 2,916, Mosquito_setState 377,
Mosquito_losePart 94; Scorpion_ctor 75, Scorpion_run 2,927, Scorpion_setState 379,
Scorpion_severPart 95; Badger_ctor 76, Badger_run 2,925, Badger_setState 360;
str_prefixDiffers 84; and `Creature_takeDamage` 1,973 and `Creature_slot7` 32 on the way.

Deaths, by the AI state the creature was in on the tick that killed it: `SmallSpider` in 24
different states (every number the driver stores), `Gnaw` in 11, `Mosquito` in 13,
`Scorpion` in 27, `Badger` in 23.

Coverage of the original as executed in that run (from the interpreter's trace; a block
starts at the function entry, at a branch target and after a conditional branch's delay
slot):

| Function | Basic blocks | Instructions |
|---|---|---|
| `SmallSpider_ctor` | 1 of 1 | 80 of 80 |
| `SmallSpider_run` | 14 of 14 | 74 of 75 |
| `SmallSpider_setState` | 8 of 8 | 119 of 119 |
| `SmallSpider_onTouch` | 6 of 6 | 30 of 30 |
| `Gnaw_ctor` | 1 of 1 | 122 of 122 |
| `Gnaw_run` | 29 of 29 | 237 of 238 |
| `Gnaw_setState` | 15 of 15 | 186 of 186 |
| `Mosquito_ctor` | 3 of 3 | 163 of 163 |
| `Mosquito_run` | 34 of 34 | 264 of 265 |
| `Mosquito_setState` | 12 of 12 | 222 of 222 |
| `Mosquito_losePart` | 8 of 8 | 82 of 83 |
| `Scorpion_ctor` | 1 of 1 | 178 of 178 |
| `Scorpion_run` | 56 of 59 | 346 of 353 |
| `Scorpion_setState` | 17 of 17 | 257 of 257 |
| `Scorpion_severPart` | 5 of 5 | 64 of 65 |
| `Badger_ctor` | 4 of 4 | 194 of 194 |
| `Badger_run` | 79 of 80 | 452 of 455 |
| `Badger` slot 11 | 1 of 1 | 2 of 2 |
| `Badger_setState` | 22 of 22 | 234 of 234 |
| `str_prefixDiffers` | 5 of 5 | 29 of 29 |
| **all 20** | **321 of 325 (98.8%)** | **3335 of 3350 (99.6%)** |

Blocks never entered, and why:

- `Scorpion_run` 0x2a53f0, 0x2a53f8, 0x2a541c: the search for a free descriptor slot beyond
  the first. The record is filled with −1 a few instructions earlier, so the first slot
  always matches; dead code.
- `Badger_run` 0x244668: one of the three outcomes of the own draw after the enemy-cone
  test of state 3 (remainder 1 → state 9). Entered with `--seed 99`, a run of 19,454
  calls that also passes with `Badger_run` at 80 of 80.

The instructions not counted in fully covered functions are padding or the delay slots of
untaken likely-branches. The base class underneath is counted by its own test.

Floating point: every float is compared as a bit pattern under the interpreter's default
FPU model; the whole test was repeated under its three other adder models (`--fpu ps2g1`,
`chop`, `nearest`, 400 ticks per run) with the same outcome. That shows the same
operations in the same order, not that a console produces the same last bit
(`docs/issues/dynamic-tests.md`). The two scale computations run through the library's
own double routines on the interpreter side and through `tools/ref_core.py`'s on the model
side.

What stays scripted: everything in `EXTERNALS` of the three models — in particular the
sight tests (`creature_canSeeObj`, `creature_findEnemyInCone`), the three hit helpers, the
animation functions, `Creature_setStats`, `Creature_init`, `Creature_applyKnockback`,
`Creature_deadUpdate`, `Creature_dropLoot`, `GutChunk` construction and
`model_buildHideMask`. Their answers are random within plausible ranges: "the target is in
reach" is an answer of the script, not geometry, so combinations a real callee cannot
produce are tested and combinations only a real callee produces may be missed. On a
quarter of the ticks the script answers "no" to all sight questions but the n-th, so that
every test of a chain is reached. Animation events and flags arrive at random, not at the
event table's times.

## 12. Where earlier documents turned out wrong or short when executed

`docs/monsters-2.md` held up for these five classes: every transition, clip offset, flag
word and constant it gives for them agreed with the executed code. What it and
`docs/monsters.md` leave out or get slightly wrong:

1. `docs/monsters-2.md`, Scorpion, "after it, +0xf4 counts down; at 0 one draw": the
   counter is tested on every tick, also while the clip plays, and set-state 6 stores
   `draw % 20` in it — so one attack in twenty ends on its first tick, before the hit
   frame (6.3). Not stated either: a hit reaction interrupts a sting (state 7) but not a
   claw that is still playing.
2. `docs/monsters-2.md`, Gnaw: the scale is `draw × 2⁻¹⁶ × 0.3 + 0.45` as it says, and
   the identity of the two library routines it marks Inferred is now executed (0x3af4d0
   multiplies, 0x3af410 adds, both truncate; the second constant is the single 0.45
   widened, a little below 0.45). Not stated: the own draw for a death chunk is made only
   when the pool gave a block; states 0 and 0x13 loop the first **bite** clip (the class
   has no idle clip); the death "clip" is that bite clip with flags 0x803; `obj_delete` is
   called on every tick the dead gnaw is still run.
3. `docs/monsters-2.md`, Mosquito: `model_buildHideMask` is called twice per lost part;
   set-state 0 and 5 each make an own draw for a `+0xf4` nothing reads (so the
   constructor, through its set-state 0, makes one too).
4. `docs/monsters-2.md`, SmallSpider and Scorpion, and `docs/monsters.md` 1.4: a state
   number the set-state does not know is **stored as requested** by `SmallSpider`,
   `Scorpion` and `Badger` (whose run functions then do nothing in it, with no way out)
   and stored as **0** by `Gnaw` and `Mosquito`.
5. `docs/monsters.md` 1.4, state 1 ("the skeleton and Zek go to 3, a knight goes to 0"):
   of these classes `Gnaw` goes to 3; `Mosquito`, `Scorpion` and `Badger` go to 0. State
   0x13 leaves to 3 in `Gnaw` and `Mosquito` and to 0 in `Scorpion` and `Badger`.
6. `docs/monsters.md` 1.3 step 4 ("several classes return when it says inactive"): all
   five do, and for all five that gates the whole class tick (section 9).
7. `docs/monsters-2.md`, Badger: on the tick the chain into a front attack starts
   (event bit 1), the "clip no longer playing → state 3" test still runs after the nested
   set-state 6.
8. FINDINGS G25 and the touch patch cover the base body of slot 6 only; `SmallSpider`'s
   override is a separate test with a larger consequence (section 10).

## 13. Not done

- **Five of the ten chosen classes were not started**: `Vampire`, `Ogre`, `WarBoar`,
  `Gremlin`, `Ghoul` (the work was stopped early). Nothing about them in this document
  beyond the table of section 1; `docs/monsters-2.md` remains a reading for them.
- No `tools/test_ref_monsters_1.py` (unit tests without the game's files) was written.
- The five draw functions; `Creature_init`, `Creature_deadUpdate`,
  `Creature_applyKnockback`, the hit helpers 0x1196e8 / 0x119850 / 0x119938 / 0x119b58 and
  the sight tests behind them (call-outs, as in the two documents underneath).
- No patch for section 10; nothing was run on a console or on linked emulators. (Both
  done since for section 10, on linked Play! emulator instances: see the end of that
  section. Still nothing on a console or in PCSX2.)

### Recommended for the next batch

In this order, by the rule of section 1: the five left over here — `Vampire` 0x2b6bfc /
0x2b7208, `Ogre` 0x29fe50 / 0x2a060c (a `Weapon1` holder, as `Skelight`), `WarBoar`
0x2ba3a0 / 0x2bac60, `Gremlin` 0x26e4c4 / 0x26ee98 (the three arrow constructors of
`tools/ref_skills_b.py` as call-outs), `Ghoul` 0x266420 / 0x266c68 (with its slot 12) —
then `Kobold` 0x27f52c / 0x27ff6c (the caster: skills 55 and 96), `Ant` 0x2359fc /
0x236708, `FireBeetle` 0x245f54 / 0x2469d0 with `FireFly`, `BlackWidow` 0x2abdd8 /
0x2acb78 and `Skeleton` 0x2a6864 / 0x2a7768. `Ogre` and `WarBoar` need only call-outs the
models already have; `Vampire` and `Ghoul` add `creature_allyInLineOfFire` 0x10d5e8 as a
call-out (and `creature_findClearHeading`, which `tools/ref_creature.py` has).

`tools/difftest_monsters_1.py` is built to take them: a class is one row in its `CLASSES`
table (table, class definitions, constructor argument order, state list), its entries and
its function bodies.
