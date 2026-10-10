# The Drundar arena's monsters: Horsemen, Skelight, Zek

This document is the prose of `tools/ref_arena_monsters.py`, the reference model of the
monster classes of the evil-path arena (level `drunare`) of `SLUS_209.73` (US v2.00): the
knights (class `Horsemen`), the skeleton the fourth knight summons (`Skelight`), the boss
`Zek`, the Summon Skeleton skill and its spell, and Tagar's Insects — cast, spell and the
spell's per-tick run, which happens inside the third knight's own tick.
It sits on `docs/spec/creature-tick.md` (the base class) and does not repeat it.

Every statement in sections 2–7 was read from the instructions at the address given and
then **executed** (sections 8–10 collect the call-outs, the draws and the level script,
and say where each of their facts comes from): `tools/difftest_arena_monsters.py` runs the original constructors, run
functions and set-state functions under the instruction interpreter `tools/ee_emu.py`,
with the creature base class underneath running for real as well, and compares each call
with the model (section 13 has the counts and the coverage). Statements about code that
was read but not executed are marked **[O]** (Observed); **[I]** is Inferred. Nothing here
was run on a console or a whole-machine emulator; the one live result quoted is
`FINDINGS.md` V12 (`docs/issues/live-rig.md` 7.5).

## 0. Conventions

- As `docs/spec/creature-tick.md` section 0: `c` is the creature, offsets are creature
  offsets, floats are bit patterns where the decimal would mislead, `clock` is `c+0x300`,
  `frame` is `g_simFrame`, a **shared draw** advances `g_randSeed` 0x404464, an **own
  draw** is `GameObject_rand` on `c+0x44`. The **cosmetic generator** is 0x404460 (per
  machine once a frame has been drawn).
- `def` is the class definition the constructor hands to `Creature_ctor`; `c+0x24` points
  at it. Entry *k* of a definition keeps its loaded pointer at `def + 8k + 4`: entry 1 is
  the model, entry 2 its texture, entries 3 and up are animation clips. "clip +0x54" means
  the pointer at `def + 0x54` (entry 10).
- `ev` is the result of `Creature_stepAnim` for this tick: the OR of the event masks the
  clips passed. `anim` is the animation status word `c+0x11a`; the classes test bit 8
  ("the clip is still playing"), bit 0x10 (a reaction clip is playing) and bit 0x80 (the
  top clip has ended).
- `see(near, far, facing, arc)` is `Creature_canSeeTargetIn` (2.3) — false without a
  target. `cone(near, far, facing, arc)` is `creature_findEnemyInCone` 0x10cf78, which
  looks for **any** enemy and returns it. Both are call-outs: what "see" and "in the cone"
  mean geometrically is `creature_canSeeObj` 0x10c810 and 0x10cf78, not this model. Arcs
  are in 16-bit angle units (65536 a turn).
- `set(n)` is virtual slot 27 on the creature itself.
- "holder" is the weapon holder object at `c+0x50` (embedded in the creature; its own
  table at holder+0). Holder slot 17 with hand 1 returns that hand's damage descriptor,
  the last argument of a full-damage hit; without a holder the argument is 0.
- A **hit** is `Creature_hitTargetInArc` 0x119938 (the target only) or
  `Creature_hitAllEnemiesInArc` 0x119b58 (every enemy), with
  `(creature, facing, arc, min, max, attack rating, damage flags, descriptor; near, far)`.
  Both end in `damage_apply` (`tools/ref_combat.py`), which makes shared draws; they are
  call-outs here.

## 1. Who is in the level, and when each one runs

From `objects.ob` of the level (`docs/issues/arena-desync.md`, re-read here for the
properties) and the object factory:

| Object type | Class, variant | Name | Properties the classes read | Casts |
|---|---|---|---|---|
| `UndeadKnight1` | `Horsemen` 0, on foot | `knight` | `wait`, `deathscript`, `dropitem` | skill 4 Disease Bolt |
| `UndeadKnight2` | `Horsemen` 1 | `knight` | same | skill 7 Fire Storm |
| `UndeadKnight3` | `Horsemen` 2 | `knight` | same | skill 87 Tagar's Insects |
| `UndeadKnight4` | `Horsemen` 3 | `knight` | same | skill 11 Summon Skeleton |
| `CazicAvatar` | `Cazic` | `avatar` | `wait`, `deathscript` | not part of this model |
| `RalosZek` | `Zek` | `rallos` | `wait` | — (see below) |
| created by skill 11 | `Skelight` | `skelightm` (from the property list 0x503770) | — | — |

There are **four** knights and none is mounted. The mounted form of the class (`Rider…`
types, a `Nightmare` underneath) belongs to another level; its code is in the same three
functions and is modelled and tested with them, but nothing in this level reaches it.

`Zek` never fights here. The level script hides him at load; he is bound as an actor by
the last cutscene and the level changes in the tick that cutscene ends
(`docs/issues/arena-desync.md`, candidate D19). As a bound actor he runs `Zek_run` once per
tick in state 0 with inert bits set, where the class code does nothing beyond the base
tick (5.3). The class is modelled in full all the same.

Order inside a tick, for a knight on foot (3.3): holder update → `Creature_processDamage`
→ `Creature_run` (which runs the attached spells through slot 17, so a Tagar's Insects
spell attached to the third knight runs here) → `Creature_updateActive` →
`Creature_stepAnim` → `Creature_applyKnockback` → slot 23 target pick → the state switch.

## 2. Pieces of the base class these classes use

`docs/spec/creature-tick.md` left these out; they are in this model and run for real in the
test.

### 2.1 `Creature_ctor` 0x109d68 (creature, type name or 0, position, facing, def, property list; hit points)

1. `GameObject_ctor(creature, position, def, properties)` — a call-out. It draws the
   object's own seed from the shared seed (**one shared draw**) and registers the name.
2. Tables `c+0x48 = 0x50cc58`, `c+0x4c = 0x50d010`; `c+0x50 = 0`; byte `c+0x119 = 8`.
3. Zeroed: steering point `+0x2ec…`, target, ally, last attacker, `+0x360`, spell list
   `+0x364`, pending damage `+0xc8`, waypoint index and time-out, turn speed `+0x110`,
   pending flags `+0x2dc`, inert byte `+0x231`, class timer `+0xf4`, failures `+0x2c4`,
   the five frame timers, charm, clock, slow byte, move speed `+0xb8`, last-hit frame,
   `+0xe0`, side-step deadline `+0x2d8`, tint byte `+0xa0`.
   Set: home `+0x3b4` = position, facing, hit points and maximum = the argument (10.0
   from all three classes: a placeholder), show mask `+0x220` = all ones, object flag
   0x20, first waypoint = end marker, team and follow slot = −1, drawn height `+0x3c` =
   z, scale `+0xdc` = 1.0, path index `+0x58` = −1, activity radius `+0x3c4` = 600.
4. Serial byte `+0x230` = `g_creatureSerialCounter` (0x4f85c4, one byte), which is then
   incremented. The counter is zeroed at a level change, so serials follow creation order.
5. Properties, in this order (each `obj_getPropInt(c, name, 0)` unless noted; a value is
   read a second time when the first read was non-zero):

   | Property | Effect |
   |---|---|
   | `wait` | inert bit 1 |
   | `hide` | inert bit 8, `obj_moveOffGrid`, object flag 0x8000 |
   | `ShowName` (string) | `+0x368` = the text pointer, object flag 0x100000 |
   | `Dead` | pending damage `+0xc8` = 1000.0 |
   | `HomeRange` | `+0x3c0` = the value as a float (default 1000.0) |
   | `pointblankrange`, `visualrange`, `visualarc` | `+0x3ac`, `+0x3ae`, `+0x3b0` (defaults 300, 500, 0x4000) |
   | `Scale` | `+0xdc` = value × 0x3c23d70a (percent) |
   | `MiniBoss` | creature flag 1 |
   | `IgnoreDamage` | creature flag 0x1000000000000 |
   | `light1`, `light2`, `ambient` (strings) | creature flag 0x40000000 when any is present; the later ones are not asked once one is found |

6. With a type name: `c+0x34` = the name; `balance_lookup(name)` gives five factors
   (hp, armour, damage, attack, experience) or says "not found"; then
   `Creature_setStats(c, 1; five factors)` — all 1.0 when not found. `Creature_setStats`
   (`docs/spec/combat.md` 4.2, a call-out) makes **one own draw** for the hit-point roll.
   Without a type name (`Skelight`) nothing of this step happens here.
7. `c+0x2fa` = the facing.

### 2.2 The event table — `creature_setDefEntryParams` 0x118378 (creature, entry, four masks; four times)

Writes four (seconds, mask byte) pairs into animation entry `entry` **of the class
definition**: time *k* at entry record `+0x14 + 8k`, mask *k* at `+0x18 + 8k`. The record
is shared by every object of the class and rewritten, with the same numbers, by every
constructor call. The masks are the bits `ev` carries on the tick the clip passes that
time (`docs/spec/animation.md` 7.3). Sections 3.2, 4.2 and 5.2 list each class's table.

### 2.3 Small helpers

| Function | Rule |
|---|---|
| `Creature_canSeeTargetIn(c, facing, arc, rayMode; near, far, lead)` 0x118d40 | 0 without a target; else a tail call to `creature_canSeeObj(c, target, s16 facing, s16 arc, rayMode; near, far, lead)` and its result as it is |
| `Creature_turnToTarget(c)` 0x1187e0 | with a target: slot 26 `(c, 0, target position)`. Result 0 |
| `Creature_isTargetCharging(c)` 0x118f90 | 1 when both hold: `u32(b − s16 target.facing + 0x3fff) < 0x7fff`, where `b = atan2_16(target.y − c.y, target.x − c.x)` and the difference is **not** wrapped to 16 bits; and `100.0 < sqrt(vx² + vy²)` of the target's last move velocity `+0x308`, `+0x30c` (written by `Creature_moveBy`). Else 0. So "charging" is a target faster than 100 whose facing is within ±0x3ffe of the bearing from the creature **to** it — as coded, a target moving *away*, not one running at the creature |
| `Creature_countAlliesNearTarget(c; r)` 0x119258 | 0 without a target; else `creature_countAlliesNear(c, target position; r)` |
| `Creature_isBlockedByTarget(c)` 0x118f08 | 0 without a target; else `creature_isBlockedBy(c, target)` |
| `Creature_isNotRooted` 0x1195e0, `Creature_isNotStunned` 0x119608 | `+0x314 == 0`, `+0x31c == 0` |
| `Creature_isAttackReady` 0x1195f0 | zeroes the cooldown `+0x318` of a creature without a target, then `+0x318 == 0` |
| slot 16, 0x3c2738 | the model: `*(def + 0xc)` |
| slot 34, 0x3c2708 (c, v) | `HomeRange +0x3c0 = float(v & 0xffff)` — what script `setMonsterVal(name, 4, v)` calls |

On "charging": the bearing is taken from the creature to the target, and it is compared
with the target's own facing; they agree when the target looks away from the creature.
Whether that is what the authors meant is not something the code says. Both classes that
use it treat a true answer as a reason for a heavier swing (3.3 state 3, 5.3 states 3, 5).

### 2.4 Slot 25 — `Creature_canSeeTarget(c, force)` 0x10e658 → 0 or 1

```
mode = (force != 0) ? 1 : 0;   if u16 visualarc(+0x3b0) == 0x7fff:  mode = 1
if target and creature_canSeeObj(c, target, 0, 0x7fff, mode; 0.0, f32(u16 pointblankrange), 0.0):  return 1
if no target:  return 0
return creature_canSeeObj(c, target, s16 facing, s16 visualarc, mode; 0.0, f32(u16 visualrange), 0.0) != 0
```

Any damage sets the visual arc to 0x7fff (`Creature_takeDamage`), which also switches the
ray mode. `Horsemen` and `Zek` pass `force = 0`, `Skelight` passes 1.

### 2.5 Slot 28 — `Creature_onDeath(c, quiet)` 0x10beb8

```
cflags &= ~0x8c00000                                             follower bits
s = obj_getPropStr(c, "deathScript", 0)
if s:  g_scriptSelectedObj(0x4039f8) = c;  script_runByName(s);  g_scriptSelectedObj = 0
if not quiet:  d = obj_getPropStr(c, "dropitem", 0);  if d:  loot_spawnNamedItem(c position, d)
if flags & 2:  flags |= 0x4000;  anim_jumpTopToEnd(c+0x114);  obj_delete(c)
if g_pvpModeB:  arena_addKill(object behind c+0x2e4 or 0, 0)
creature_stopBossMusic(c)
```

The death script runs **inside the dying creature's own tick**, from its set-state. All
three classes call slot 28 with 0, except `Skelight`, which does not call it at all.

## 3. Horsemen

Table 0x515730, size 0x478, constructor 0x271c70, run 0x27236c, set-state 0x272f4c, draw
0x2721f8 **[O]**. Slots 2 (take damage), 20, 23, 25, 26, 28, 35 are the base bodies.

### 3.1 Layout beyond the base

| Offset | Type | Meaning |
|---|---|---|
| +0x3c8 | handle | the mount; empty on foot |
| +0x3d0 … +0x46f | object | embedded `WeaponShield` holder (table 0x50cda0); `c+0x50` points here |
| +0x470 | u8 | variant 0–3 (read signed where it selects the cast) |
| +0x472 | s16 | countdown of state 0x1a |
| +0x474 | s32 | clock value after which variants 0–2 may cast |

Base fields the class uses as its own: `+0xf4` (clock value until which an idle knight
stays idle), `+0xd0`, `+0xd2`, `+0xd4` (damage low, high, attack rating from
`Creature_setStats`).

### 3.2 Constructor — `Horsemen_ctor` 0x271c70 (object, type name, position, facing, properties, variant, mounted)

In order:

1. `Creature_ctor(…, def 0x5006e8, …; 10.0)` (2.1): one shared draw in
   `GameObject_ctor`, one own draw in `Creature_setStats`.
2. Table, empty mount handle, the holder initialised (its table set three times: base,
   `Weapon1`, `WeaponShield`; four hand records to −1, two bytes to 0xff, eight zero
   halfwords).
3. `+0x28 = 0x30`, radius 20.0, move speed 0, turn rate 0x3f999999 (1.2), state 0, kind
   `+0xb4 = 9`, `+0xec = frame`, `c+0x50 = holder`.
4. Holder slot 1 twice: hand 1 gets item-model entry `2v + 0x1b`, hand 2 gets `2v + 0x23`
   (`v` the variant).
5. Creature flags |= 0x2020020000 (0x20000 metal body, 0x20000000 never gibbed or frozen
   to pieces, bit 37); scale `+0xdc = 1.2`; `+0x472 = 0`; resistances `+0x5c = 0.2`,
   `+0x64 = +0x68 = 1.0`, `+0x6c = 0.3`.
6. **One own draw** `d`: `+0x474 = clock + 480 + d % 120` (the clock is 0 here).
7. `+0x470 = v`; `+0xe8 = 1 << v`; `+0x220 = model_buildHideMask(model, 1 << v)`.
8. Variant 3 only: `lump_load` of the skeleton's lump.
9. `anim_clear`, `anim_push(clip +0x54, 1)`, `obj_runEvery60` (a 60-frame run list until
   the first `Creature_updateActive` that finds it active).
10. The event table:

    | Entry (clip) | Used by state | Events: seconds → bit |
    |---|---|---|
    | 3 (+0x1c) | 6 | 0.2 → 1, 0.6 → 1 |
    | 4 (+0x24) | 7 | 0.2 → 1, 0.6 → 1, 1.0 → 1 |
    | 5 (+0x2c) | 10 | 0.3 → **2** |
    | 6 (+0x34) | 0xb | 0.3 → 1, 0.8 → 1, 1.6 → 1 |
    | 0xe (+0x74) | 8 | 0.5 → 1 |
    | 8 (+0x44) | 0x17 (cast) | 2.0 → 1 |
    | 0x11, 0x12, 0x13, 0x18 (+0x8c, +0x94, +0x9c, +0xc4) | 0x20, 0x21, 0x22, 0x1f | 0.2 → 1 |
    | 0xf (+0x7c) | death clip | 0.1 → 0x80 |

    Times are 0x3e4ccccc, 0x3f199999, 0x3e999999, 0x3f4ccccc, 0x3fcccccc and exact halves.
11. Mounted only: `pool_new(0x3d8)`; with a block `Nightmare_ctor(block, type name text,
    position, facing, 0x500848 + 12 v)`, the two handles linked both ways through `+0x3c8`
    of each, and `Horsemen_setState(c, 0x1b)` (a direct call).
12. `Creature_init(c)` — a call-out (height from the model, element properties,
    `initScript`).

### 3.3 Run — `Horsemen_run` 0x27236c

Head, on foot (`c+0x3c8` empty):

```
if holder:  holder.slot 21 (holder, def, c; 0.5)                 presentation (FINDINGS D37)
Creature_processDamage(c, model);  Creature_run(c, model)        (its result is tested; it is always 0)
Creature_updateActive(c)                                         result NOT used
ev = Creature_stepAnim(c; 1.0);  Creature_applyKnockback(c; 0.5);  slot 23 (c, 0)
```

Head, mounted: after the holder update the knight copies the mount's position and facing
and calls `obj_updateGridCell(c)`; then `Creature_processDamage`, `Creature_run`,
`Creature_updateActive`, `Creature_stepAnim` as above, **no** knock-back and **no** target
pick; instead, when the mount has a target and the knight has none or a different one:
`handle_clear(c+0x234)`, `handle_link(c+0x234, mount's target)`.

Then the switch on the state (read as signed 16 bits; an unsigned value of 0x24 or more
goes to the last row). Every row ends the tick.

| State | What it does | Leaves by |
|---|---|---|
| 0 idle | slot 25 `(c, 0)` | seen → `set(3)`; else `Creature_isAwayFromHome` → `set(1)`; else `+0xf4 < clock` → `set(1)`; else stays |
| 1 wander / go home | slot 25 `(c, 0)`; not seen: `Creature_moveToDest(c)` | seen → `set(0)` (idle first; the chase starts a tick later) |
| 3 chase | see below | |
| 5 between attacks | see below | |
| 6, 7, 0xb swing | `Creature_moveBy(c, 0)`; with a target: on `ev & 1` the full hit `(0–36, facing, arc 10000, +0xd0…+0xd2, +0xd4, flags 8, holder descriptor)`; else on `ev & 2` the weak hit; then `Creature_turnToTarget` | `anim & 8` clear → `set(3)` |
| 10 | the same code. Its clip only ever raises bit 2, so what lands is the weak hit: `(0–36, facing, arc 10000, +0xd0 / 3, +0xd2 / 3, +0xd4, flags 0x100001, no descriptor)`; the divisions truncate toward zero | same |
| 8 heavy swing | `Creature_moveBy(c, 0)`; with a target: on `ev & 1` the hit `(0–36, arc 10000, full damage, flags 0x40008, holder descriptor)`; `Creature_turnToTarget` | `anim & 8` clear → `set(3)` |
| 0x10 cooldown | `Creature_isAttackReady` false: `Creature_fleeFromTarget(c, 0)` | ready → `set(0)` |
| 0x11, 0x18 | nothing | `anim & 8` clear → `set(3)` |
| 0x12 hit reaction | nothing | `anim & 0x10` clear → `set(3)` |
| 0x13 stunned | nothing | `Creature_isNotStunned` → `set(3)` |
| 0x14 dead | `Creature_deadUpdate(c, ev, zero vector, 0; 20.0)` | never |
| 0x17 cast | with a target: on `ev & 1` the cast (3.5) and then **one own draw** `d`: `+0x474 = clock + 480 + d % 120`; `Creature_turnToTarget` | `anim & 8` clear → `set(3)` |
| 0x19 | `Creature_moveBy(c, 0)` | only from outside |
| 0x1a | `+0x472 > 0`: decrement | only from outside |
| 0x1b – 0x1e riding | nothing | only from outside |
| 0x1f – 0x22 mounted swings | with a target and `ev & 1`: `Creature_hitAllEnemiesInArc(0–36, facing − 0x4000, arc 10000, full damage, flags 8, holder descriptor)` | only from outside |
| 0x23 dismount | `Creature_moveBy(c, 0)`; if `(anim & 0x98) == 0x88`: queue count `c+0x118 = 0`, `anim &= ~0x80`, `anim_push(clip +0x84, 0x14)`; else if `(anim & 0x90) == 0x90`: `anim_start(clip +0x54, 3; 0.0)` | `anim & 0x18` clear → `set(0)` |
| 2, 4, 9, 0xc–0xf, 0x15, 0x16, anything else | `set(0)` | at once |

**State 3, the chase** (0x2725cc), first match wins:

```
no target:                                              set(0)
see(0, 36, facing, 10000):                              set(5)
see(0, 36, facing, 6000) and Creature_isTargetCharging: set(8)
see(0, 400, facing, 10000) and Creature_countAlliesNearTarget(c; 36.0) > 0:   set(5)     hold back: allies are on it
+0x474 < clock and variant < 3 (unsigned) and cone(0, 400, facing, 6000):     set(0x17)
variant == 3 (signed byte) and skill 11 .slot 1 (skill, c) != 0:               set(0x17)   no timer for the summoner
otherwise:                                              Creature_moveToTarget(c)
```

The facing is re-read from `c+0x38` at each test. The count is compared as a signed
32-bit number. A variant byte above 3 neither casts by timer nor summons.

**State 5, between attacks** (0x27273c):

```
rooted (+0x314 != 0):          see(0, 36, facing, 10000) ? set(6) : stay
see(0, 36, facing, 10000):     d1 = OWN DRAW;  if d1 odd and Creature_isBlockedByTarget(c):  set(10)
                               else:  d2 = OWN DRAW;  set(d2 odd ? 6 : 7)
see(0, 72, facing, 3000):      set(0xb)
otherwise:                     d = OWN DRAW;  if d % 60 != 0: stay
                               if Creature_countAlliesNearTarget(c; 36.0) > 0: stay
                               set(3)
```

So an unrooted knight with its target in reach makes one or two own draws every tick it
is in state 5, and one per tick while the target is out of reach.

Where the states come from: nothing in the run function enters 5, 0x10, 0x12, 0x13 or 0x14
except through set-state's own redirections — `Creature_filterState` turns a request
into 5 while the root timer runs, 0x13 while stunned, 0x10 while the cooldown runs
(`docs/spec/creature-tick.md` 12.3); 0x12 and 0x14 come from `Creature_processDamage`.
States 0x11, 0x18–0x23 are requested only from outside the class (the mount, cutscenes).

### 3.4 Set-state — `Horsemen_setState` 0x272f4c (c, state)

```
if Creature_filterState(c, &state):  return                      refused
cflags &= ~0x200
if mount handle set and state < 0x19 (signed):  return           a mounted knight ignores these
```

Then, with `start(clip, flags; blend)` = `anim_start(c+0x114, clip, flags; blend)` (blend
0x3dcccccc unless given) and `swing(clip, flags)` =
`anim_startBlendInOut(c+0x114, clip, flags; 0.1, 0.1)`:

| State | Effect |
|---|---|
| 0 | object flags &= ~9; **one own draw** `d`: `+0xf4 = clock + d % 120`; `start(+0x54, 3)`; a non-empty mount handle is cleared (cannot happen: see 13) |
| 1 | `Creature_clearPath`, `Creature_pickWanderDest`, `start(+0x6c, 0x803)`, `anim_syncToSimFrame` |
| 3, 0x10 | `Creature_clearPath`, `start(+0x6c, 0x803)`, `anim_syncToSimFrame` |
| 5 | `start(+0x3c, 3)` |
| 6, 7, 8, 10, 0xb, 0x17, 0x18 | `swing(+0x1c / +0x24 / +0x74 / +0x2c / +0x34 / +0x44 / +0x64, 0x808)` |
| 0x11 | cflags |= 0x200; `start(+0x3c, 3)` |
| 0x12 | if the current state is 6 and `anim & 8`: nothing, **the state stays 6**. Otherwise `swing(+0x4c, 0x10)` |
| 0x13 | `start(+0x54, 3; 0x3e999999)` |
| 0x14 | death, below |
| 0x19 / 0x1a / 0x1b | object flags |= 0xb / &= ~2 / |= 9; `start(+0xa4, 3)` |
| 0x1c, 0x1d, 0x1e, 0x1f | `start(+0xd4 / +0xcc / +0xbc / +0xc4, 3)` |
| 0x20, 0x21, 0x22 | `swing(+0x8c / +0x94 / +0x9c, 8)` |
| 0x23 | `start(+0xb4, 0x80c)`; with a mount handle: `handle_clear`, handle = 0, `z += 48.0` (position and drawn height) |
| 2, 4, 9, 0xc–0xf, 0x15, 0x16, 0x24 and up, negative | a nested `set(3)` — and then the **requested** number is stored as the state |

Last, in every row that did not return: `c+0x232 =` the low 16 bits of the state.

The last row means a request for, say, state 9 runs the whole chase set-up and leaves the
knight in "state 9"; the next run turns that into `set(0)`.

**Death (0x14), in order:**

1. cflags |= 0x20000000000.
2. Variant 3 (signed byte) only: `o = world_findObjectByName("skelightm")`; when `o`
   exists and has object flag 0x20: `o.slot 27 (o, 0x14)` — the skeleton's own set-state
   (4.4), in the same tick (FINDINGS K8). The lookup is by name only: it returns whatever
   object holds that name, whoever summoned it (`Cazic` and `FemaleDarkElf` summon under
   the same name).
3. `Creature_dropLoot(c, position, facing, 0; 36.0, 2.0, 0x3fe66666, 0x3f199999, 2.0, 0.25)`
   — a call-out; every roll in it is a shared draw (`docs/issues/kill-loot-xp.md` 3).
4. Holder slot 11 `(holder, 1, c, 0, 0)` then `(holder, 2, c, 0, 0)`: each held part
   becomes a physics prop. The holder pointer is read again between the two.
5. `start(+0x7c, 6)` — the death clip, whose event 0x80 at 0.1 s is what
   `Creature_deadUpdate` waits for.
6. Slot 28 `(c, 0)` (2.5): the knight's `deathScript` runs here (section 10), then its
   `dropitem`.

After the set-state returns, `Creature_processDamage` continues with the experience
call-outs (`docs/spec/creature-tick.md` 3.4 steps 5–11). Nothing here draws the shared
seed itself; the call-outs do: loot, the two props' constructors, the named item, and
later the tick on which each shed part comes to rest (FINDINGS D39).

### 3.5 The casts (0x272a64–0x272c74)

On the tick `ev & 1` arrives in state 0x17 (2.0 s into the clip), with a target. The
level argument is slot 35 — `int(g_levelMonsterLevel × 0x3e999999)` — and the facing
argument is the knight's facing:

| Variant | Call | Position argument | Result |
|---|---|---|---|
| 0 | skill 4 (object pointer 0x41b180) slot 2 | `(x + 0.0, y, z + height × 0.5)` | dropped |
| 1 | skill 7 (0x41b18c) slot 2 | the target's position | dropped |
| 2 | skill 87 (0x41b2cc) slot 2 | the knight's position | `creature_addSpell(c, result)` |
| 3 | skill 11 (0x41b19c) slot 2 | the knight's position | dropped (the leak of FINDINGS D22) |
| other | nothing | | |

The own draw for `+0x474` follows whatever the variant. "Can use" (skill slot 1) is asked
only for variant 3 and only in state 3; nothing asks it again at the cast, 120 ticks
later.

## 4. Skelight

Table 0x5174b0, size 0x468, constructor 0x2a8770, run 0x2a8b84, set-state 0x2a91b8, the
static's helper 0x2a946c. Slots 8, 9 and 15 (load state, save state, clone: 0x2a90b0,
0x2a8fdc, 0x126b58) are overridden **[O]**: the saved state adds the follow slot `+0x5a`,
the level `+0x460`, the held item entry and its element; loading re-runs
`Creature_setStats` with all factors 1.0 and no hit-point roll, under the same temporary
replacement of the level global as the constructor.

### 4.1 Layout beyond the base

| Offset | Type | Meaning |
|---|---|---|
| +0x3c8 … +0x45f | object | embedded `Weapon1` holder (table 0x50cf40) |
| +0x460 | s32 | level given by the caster |

`+0xf4` is used as a swing countdown in state 6.

### 4.2 Constructor — `Skelight_ctor` 0x2a8770 (object, position, facing, properties, level)

1. `Creature_ctor(…, type name 0, def 0x502728, …; 10.0)`: one shared draw
   (`GameObject_ctor`); **no** statistics yet.
2. Table; holder initialised; `+0x28 = 0x14`, turn rate 1.5, radius 12.0, move speed 0,
   state 0, `+0xec = frame`, cflags |= 0x10000 (bone body), `+0x64 = +0x68 = 1.0`,
   `c+0x50 = holder`; holder slot 1 `(holder, 1, 4)`.
3. `+0x460 = level`. Then, around one call:
   ```
   saved = g_levelMonsterLevel(0x4f714c);  g_levelMonsterLevel = f32(level)
   e = (level name 0x44fe18 equals "blomedal", any case) ? 0.0 : 1.0
   Creature_setStats(c, 1; 0x3faa3d70, 0x3f999999, 0x3f999999, 1.0, e)       one own draw (hit points)
   g_levelMonsterLevel = saved
   ```
   The fifth factor is experience: a skeleton is worth none in that one level.
4. `+0xe8 = 0`, `+0x220 = model_buildHideMask(model, 0)`, `anim_clear`,
   `anim_push(clip +0x3c, 0xc)`, `Skelight_setState(c, 0x17)` (direct),
   `obj_runEveryFrame(c)`.
5. Event table: entry 3 (clip +0x1c): 0.3 s → 1. Entry 4 (clip +0x24): 0.3 s → 1,
   1.0 s → 1.
6. `Creature_init(c)`; kind `+0xb4 = 0x10`; cflags bit 63 (**active**) set by hand.

So a skeleton is on the every-frame list and active from its first tick, whatever the
activity test would say; its first `Creature_updateActive` then decides.

### 4.3 Run — `Skelight_run` 0x2a8b84

```
if state != 0x17:  Creature_processDamage(c, model)              hits taken while rising WAIT
Creature_run(c, model);  Creature_updateActive(c)                result not used
row = holder ? holder.slot 15 (holder, 1) << 4 : 0
m = word at g_itemModels(0x3e9ce0) + row + 8
if holder:  holder.slot 22 (holder, m, c; 0.5)                   presentation (D37)
ev = Creature_stepAnim(c; 1.0);  Creature_applyKnockback(c; 0x3f333333);  slot 23 (c, 0)
```

| State | What it does | Leaves by |
|---|---|---|
| 0 | slot 25 `(c, 1)` | seen → `set(3)`; else away from home → `set(1)` |
| 1 | slot 25 `(c, 1)`; not seen: `Creature_moveToDest` | seen → `set(3)` |
| 3 chase | `see(0, 48, facing, 6000)` → `set(6)`. Else `see(0, 36, 0, 0x7fff)` → `Creature_turnToTarget`. Else `Creature_moveToTarget` | no target → `set(0)` |
| 5 | | `see(0, 48, facing, 6000)` → `set(6)`; else not rooted → `set(3)` |
| 6 swing | below | `+0xf4 ≤ 0` → `set(3)` |
| 0x10 | not ready: `Creature_fleeFromTarget(c, 0)` | ready → `set(0)` |
| 0x12 | | `set(3)` at once |
| 0x13 | | not stunned → `set(0)` |
| 0x14 | `Creature_deadUpdate(c, ev, zero vector, 1; 20.0)` | never (the object is already queued for deletion) |
| 0x17 rising | if `anim & 0x80`: `set(0)`. Then, on every tick including that one: `fx_spawn(7, position)` | the clip's end |
| anything else | nothing at all — the creature stays in that state | only from outside |

State 6:

```
if target:
    if ev & 1:  hit (0–48, facing, arc 6000, +0xd0…+0xd2, +0xd4, flags 8, holder descriptor)
    if anim & 8:  Creature_turnToTarget(c)
if not (anim & 8):  +0xf4 −= 1                                   anim is read again after the turn
if +0xf4 <= 0:  set(3)
```

Set-state 6 stores 1 in `+0xf4`, so the state ends on the first tick the clip is no
longer playing.

### 4.4 Set-state — `Skelight_setState` 0x2a91b8

After `Creature_filterState`:

| State | Effect |
|---|---|
| 0 | `anim_start(clip +0x34, 3; 0.1)`; `+0xf4 = clock + 60` |
| 1 | `Creature_clearPath`, `Creature_pickWanderDest`, `anim_start(clip +0x44, 0x803; 0.1)`, `anim_syncToSimFrame`; `+0xf4 = clock + 300` |
| 3, 0x10 | `anim_start(clip +0x44, 0x803; 0.1)`, `anim_syncToSimFrame` — the path is **not** cleared |
| 5, 0x13 | `anim_start(clip +0x34, 3; 0.1)` |
| 6 | **one own draw** `d`: `anim_startBlendInOut(clip +0x1c + 8 (d & 1), 0x808; 0.1, 0.1)`; `+0xf4 = 1` |
| 0x12 | nothing: the state stays what it was (a skeleton has no hit reaction) |
| 0x14 | death, below |
| 0x17 | stored, nothing else |
| anything else | state **0** is stored, with `anim_start(clip +0x34, 3; 0.1)` |

Neither writer of `+0xf4` in rows 0 and 1 has a reader in this class.

**Death (0x14):** object flag 2 (hidden); cflags |= 0x20000000000; the eight bytes at
0x8e4560 are zeroed (`Skelight_shatter`; nothing else in the executable refers to that
address); `n = model_getSamplePointCount(slot 16)`; for `i = 0, 3, 6, … < n`:
`model_getSamplePoint(slot 16, c+0x114, position, facing, i, &p, &q, 0; 1.0)` and
`fx_spawn(2, p)`; `obj_delete(c)`.

No `Creature_dropLoot`, no slot 28 (so no death script, no drop item, no boss-music
call), no dead bit set here (the caller `Creature_processDamage` set object flags 9
before). The object is destroyed at the start of the next object pass (FINDINGS D23). The
experience call-outs of `Creature_processDamage` still follow.

## 5. Zek

Table 0x5180c8, size 0x480, constructor 0x2c1f94, run 0x2c2440, take-damage 0x2c34e4,
set-state 0x2c382c, slot 35 0x2c3c54 (a tail call to the base: monster level × 0.3), draw
0x2c2378 **[O]**.

### 5.1 Layout beyond the base

| Offset | Type | Meaning |
|---|---|---|
| +0x3c8 … | object | embedded `Weapon1` holder |
| +0x460 | handle | the enemy the ground wave steers toward |
| +0x464 | s32 | a ground wave is travelling |
| +0x468 | s16 | heading of the wave |
| +0x46c | Vec3 | position of the wave |
| +0x478 | s32 | clock value the two specials are measured from |
| +0x47c | s32 | last attack state entered (6–0xe) |

### 5.2 Constructor — `Zek_ctor` 0x2c1f94 (object, type name, position, facing, properties)

`Creature_ctor(…, def 0x503688, …; 10.0)`; table; holder; `+0x28 = 0x32`, kind 0xb, turn
rate 1.2, radius 30.0, `+0xec = frame`, `+0xf4 = frame + 300`, cflags |= 0x2000040000,
resistances `+0x5c`, `+0x60`, `+0x64`, `+0x68`, `+0x6c` all 0.5, the wave fields and
`+0x478` zero, move speed 0, state 0; holder slot 1 `(holder, 1, 0x15)`; `anim_clear`;
`Zek_setState(c, 0)` (direct); `obj_runEvery60`; the event table; `Creature_init`. No own
draw and no property of its own.

| Entry (clip) | Used by state | Events |
|---|---|---|
| 3, 4 (+0x1c, +0x24) | 6 (one of two) | 0.8 s → 1 |
| 10 (+0x54) | 7 | 0.8 → 1 |
| 0x11 (+0x8c) | 8 | 0.3 → 1, 0.7 → 2 |
| 7, 9, 6, 8 (+0x3c, +0x4c, +0x34, +0x44) | 9, 10, 0xb, 0xc | 0.8 → 1 |
| 0x10 (+0x84) | 0xd | 1.8 → 1 |
| 5 (+0x2c) | 0xe | 0.8 → 1 |
| 0x13 (+0x9c) | death clip of one other level | 0.2 → 0x80 |

The death clip this level uses (+0xa4, entry 0x14) gets no event from the constructor.

### 5.3 Run — `Zek_run` 0x2c2440

```
Creature_processDamage(c, slot 16);  Creature_run(c, slot 16)
if Creature_updateActive(c) == 0:  return                        NOTHING below runs for an inactive Zek
if holder:  holder.slot 21 (holder, def, c; 0.5)
ev = Creature_stepAnim(c; 1.0);  Creature_applyKnockback(c; 0x3e4ccccc);  slot 23 (c, 0)
switch (state);  then the wave (5.4) on every path
```

`special()` below is, in this order: if `+0x478 < clock − 180` and
`cone(120, 800, facing, 5000)` → `set(0xe)`; else if `+0x478 < clock` and
`cone(0, 260, facing, 0x7fff)` → `set(0xd)`. All reach tests use 84.0.

| State | What it does | Leaves by |
|---|---|---|
| 0 | slot 25 `(c, 0)` | seen → `set(3)`; else away from home → `set(1)` |
| 1 | not seen: `Creature_moveToDest` | seen → `set(3)` |
| 3 chase | `see(0, 84, facing, 32000)` → `set(7)` if `Creature_isTargetCharging`, else `set(5)`. Else `special()`. Else `see(0, 84, facing, 0x7fff)` → `Creature_turnToTarget`; else `Creature_moveToTarget` | no target → `set(0)` |
| 5 between attacks | below | |
| 6, 7 | `Creature_settle`; on `ev & 1`: hit on the target `(0–84, facing, arc 8000, full damage, flags 0x80008, holder descriptor)` | `anim & 8` clear → `set(5)` |
| 8 | `Creature_settle`, `Creature_turnToTarget`; on `ev & 1`: hit on all `(0–84, facing, arc 8000, +0xd0 / 2, +0xd2 / 2, flags 0x440001, no descriptor)`; on `ev & 2` (both can fire in one tick): the same with flags 0x80001 | same |
| 9 / 10 / 0xb / 0xc | `Creature_settle`; on `ev & 1`: hit on all `(0–84, facing + 0 / −16000 / +16000 / −16000, arc 8000, full damage, flags 0x80008, holder descriptor)` | same |
| 0xd ground pound | `Creature_settle`; on `ev & 1`: spot = position + 84 along the facing (z unchanged); `pool_new(0x9c)`; with a block `GroundPoundEffect_ctor(block, spot, facing, skill 38 object (pointer 0x41b208), slot 35, c)`; `+0x478 = clock + 600` whether or not there was a block | same |
| 0xe wave | `Creature_settle`; on `ev & 1`: `e = cone(120, 800, facing, 10000)`; if `e`: `handle_link(c+0x460, e)`; `+0x464 = 1`; wave position = position + 120 along the facing; wave heading = facing; `+0x478 = clock + 600` | same |
| 0x10 | not ready: `Creature_fleeFromTarget(c, 0)` | ready → `set(0)` |
| 0x12 | | `anim & 0x10` clear → `set(5)` |
| 0x13 | | not stunned → `set(3)` |
| 0x14 | `Creature_moveBy(c, 0)`, `Creature_deadUpdate(c, ev, zero vector, 0; 20.0)` | never |
| 2, 4, 0xf, 0x11, anything else | `set(0)` | at once |

**State 5** (0x2c2700), first match wins:

```
see(0, 84, facing, 8000):       charging → set(7)
                                else  d = OWN DRAW:  last attack(+0x47c) != 8 → set(6 + d % 3)   (6, 7 or 8)
                                                     last attack == 8        → set(6 + (d & 1))
see(0, 84, facing + 16000, 8000):   set(9)
see(0, 84, facing − 16000, 8000):   set(10)
cone(0, 84, facing + 16000, 8000):  set(0xb)
cone(0, 84, facing − 16000, 8000):  set(0xc)
special()
see(0, 84, facing, 0x7fff):     Creature_turnToTarget
not rooted:                     set(3)
```

Halves truncate toward zero (`(x + sign) >> 1` on the signed 16-bit value).

As a cutscene actor (inert bits set) Zek stays in state 0: slot 25 answers 0 without a
target, slot 23 returns at once for an inert creature, and a request for state 1 is
refused by `Creature_filterState` — which the model and the original both do in the
test's inert ticks.

### 5.4 The ground wave — the tail of `Zek_run`, 0x2c3054

Runs every tick `+0x464` is non-zero and Zek is active, whatever his state:

```
old = wave position
wave.y += sin(heading) × 5.0;   wave.x += cos(heading) × 5.0
wave.z = terrain_height(g_world, wave position; 12.0) + 1.0
over = false
if |wave.z − old.z| > 12.0:                                      compared in double precision
    wave position = old;  over = true                            the height just stored is undone too
if enemy handle +0x460 not empty:
    b = atan2_16(wave.y − e.y, wave.x − e.x)                     the bearing from the ENEMY to the wave
    d = s16(b − heading)
    i = int(f32(d) × 0x3ba3d70a);   j = int(sqrt(0x3ca3d70a) × f32(i))
    heading −= (i − j)                                           stored as 16 bits
    if sqrt((wave.x − e.x)² + (wave.y − e.y)²) < 36.0:  over = true
if 0x491c4000 (640000) < (c.x − wave.x)² + (c.y − wave.y)²:  over = true          800 units from Zek
if over:
    +0x464 = 0
    fx_ringBurst(wave position; 4.0)
    sound_playOnObject(res_find(effects lump, explosion entry), c; 1.0)
    combat_applyAreaDamage(c, wave position, +0xd0 / 2, +0xd2 / 2, 0x80840, 0; 40.0, 180.0)
    d = OWN DRAW;  decal_add(wave position, s16(d), 9, 0; 48.0)
    b = pool_new(0xbc);  if b:  LightEffect_ctor(b, wave position, 0, 0; 128, 100, 78, −32, 0, 0, 0, 0; stack: 168, 60, 1.0, 0x3eb33333)
    handle_clear(c+0x460);  +0x460 = 0
fx_spawn(7, wave position)                                       also on the last tick
```

The steering turns the heading by about 0.43 % of `d` per tick **away** from `d = 0`
(which is "pointing straight away from the enemy") and so toward `d = ±0x8000`, pointing
at the enemy, where it flips sign every tick by ±140 units. The square root of 0x3ca3d70a
is taken at run time.

The own draw for the decal is made whatever the local decal option says; `decal_add`
itself is a call-out.

### 5.5 Take damage — `Zek_takeDamage` 0x2c34e4 (c, attacker, flags; amount), slot 2

When `flags & 0x2000`, the attacker exists and has object flag 0x20 (a monster — so not a
player's hit):

```
sound_playOnObject(res_find(effects lump, clang entry), c; 1.0)
if word 0x503748 == 0:  particleDef_ctor(0x8e4ba0, 200, 200, 150, 300, 200, 175, 100; 2.0, 5.0, −20.0; stack 0, 1, 2, 2, 0);  0x503748 = 1
a = atan2_16(attacker.y − c.y, attacker.x − c.x)
v = (cos a × 10, sin a × 10, 10);   p = (c.x + cos a × radius, c.y + sin a × radius, c.z + height × 0.25 + 0.0)
50 times:  u = point of the unit ball, THREE OWN DRAWS per try ((d × 2⁻¹⁶) doubled − 1.0), retried while 1.0 < |u|²
           v += 5 × u;   particle_spawn(0x8e4ba0, p, v; 0.0)
```

Then `Creature_takeDamage` unchanged. The sparks cost at least 150 own draws; they shift
every later own draw of Zek (state 5, clip choices, the decal). In this level no monster
attacks him.

### 5.6 Set-state — `Zek_setState` 0x2c382c

After `Creature_filterState`:

| State | Effect |
|---|---|
| 0 | `anim_start(clip +0x7c, 3; 0.1)` |
| 0x13 | `anim_start(clip +0x7c, 3; 0x3e999999)` |
| 1 | `Creature_clearPath`, `Creature_pickWanderDest`, `anim_start(clip +0x94, 0x803; 0.1)`, `anim_syncToSimFrame` |
| 3 | `Creature_clearPath`, the same clip and sync |
| 0x10 | cooldown `+0x318 = 60`, then as 3 |
| 5 | `anim_start(clip +0x7c, 3; 0.1)`, `anim_syncToSimFrame` |
| 6 | `+0x47c = 6`; **one own draw** `d`: `anim_startBlendInOut(clip +0x1c + 8 (d & 1), 0x808; 0.1, 0.1)` |
| 7, 8, 0xb, 0xc, 0xd, 0xe | `+0x47c =` state; `anim_startBlendInOut(clip +0x54 / +0x8c / +0x34 / +0x44 / +0x84 / +0x2c, 0x808; 0.1, 0.1)` |
| 9, 10 | `+0x47c =` state; clip +0x3c / +0x4c with flags 0x4808 |
| 0x12 | **one own draw** `d`: `anim_startBlendInOut(clip +0x5c + 8 (d & 3), 0x10; 0.1, 0.1)` |
| 0x14 | death, below |
| anything else | state **0** is stored; no clip, nothing else |

**Death:** cflags |= 0x20000000000;
`Creature_dropLoot(c, position, facing, 0; 36.0, 2.0, 0x3fcccccc, 0x3f199999, 0x3fb33333, 0.25)`;
then the level name is compared (exactly, case and all) with the text at 0x54e5f8, which
names the *other* arena level: there, `anim_start(clip +0x9c, 0x806; 0x3e4ccccc)`;
everywhere else — this level included — holder slot 11 `(holder, 1, c, 0, 0)` and
`anim_start(clip +0xa4, 0x806; 0x3e4ccccc)`; then slot 28 `(c, 0)`.

## 6. Skill 11, Summon Skeleton

Skill object 0x6e18e8 (pointer 0x41b19c), table 0x519890. `docs/spec/skills-01-34.md`
section 11 has the statistics; this section is the executed part.

### 6.1 Can use — 0x2e2368 (skill, caster) → 0 or 1

```
caster has object flag 0x40:  slot = word caster+0x3c8;  if slot >= 4 (unsigned): return 0
                              name = pointer table 0x503778 [slot]
else:                         name = pointer at 0x503788                       "skelightm"
return world_findObjectByName(name) == 0
```

One name for all monster casters. The lookup finds an object from its constructor until
its destructor has run — hidden, dead or queued for deletion alike
(`docs/issues/arena-desync.md` F4). So the limit is **one live skeleton object per name**,
and the fourth knight asks every tick it is in state 3 with nothing nearer to do.

### 6.2 Cast — 0x2e18a4 (skill, level, caster, position, facing) → spell or 0

1. Caster's second flash quad: `+0x98 = −128`, `+0x9a = −110`, `+0x9c = −128`, `+0x9e = 30`.
2. `n = model_getSamplePointCount(caster.slot 16)`. When `n ≠ 0`, particles, all from the
   **cosmetic generator**: 32 times { one draw `% n` picks a sample point
   (`model_getSamplePoint`); a unit-ball point (three draws per try, retried outside the
   ball) × 0x3e72af9a is added to it; a second ball point × 0x3d8b4634 is the velocity;
   `particle_spawn(0x8e5c80, …)` }, then 200 times { sample point; one ball point ×
   0x41c000e5 as velocity; `particle_spawn(0x8e5cd0, …)` }.
3. Spot = `position + 72 × (cos, sin)(facing)`, `z = terrain_height(g_world, spot; 12.0)`.
   When `|z − caster.z| > 24.0` (in double precision):
   `world_findFreeSpot(&out, caster position, 72, 12, &found, 0)` — shared draws, three a
   try — and the spot becomes `out` when it found one.
4. **Shared draw 1**: `d1 = f32(draw) × 2⁻¹⁶`. Always, before anything can fail.
5. `strength = skill.slot 12 (0, level, caster, 10)`.
6. Property list: 0x503770 for a monster; `0x503750 + 8 × slot` for a player in slots 0–3.
7. `b = pool_new(0x468)`. Without a block: skip to 9 and return 0.
   With one: `Skelight_ctor(b, spot, facing, list, strength)` (4.2: one shared draw for
   its own seed, one own draw for hit points, and whatever `Creature_init` does);
   `b.flags |= 0x4000`; `chance = skill.slot 12 (1, level, caster, 10)`;
   if `d1 < f32(chance) × 0x3c23d70a`: **shared draw 2**, `% 3` → holder slot 2, 4 or 6
   with argument 0 (fire, cold, shock weapon; each builds its element entry with a shared
   draw of its own — a call-out).
8. Player caster with `level > 0` only: `b+0x5a` = the caster's slot byte, b's cflags |=
   0x400000, `Creature_setCharm(b, −1, caster.slot 37)`, `b+0x3ac = 400`,
   `b.slot 34 (500)`. A monster's skeleton gets none of this: no charm, team −1.
9. `sound_playAtPos(res_find(…), position; 1.0)`.
10. With a skeleton: `s = pool_new(0x1c)`; with a block `SpellSummonSkeleton_ctor(s, level,
    caster, skill, b)` — **shared draw 3** (the spell's own seed) and `handle_link(s+0x18, b)`.
    Result `s`.

Shared draws of one monster cast, in order: (free-spot tries) → d1 → `GameObject_ctor` of
the skeleton → (elemental: draw 2, then the holder's) → the spell's seed. A failed
`pool_new(0x468)` leaves only d1.

### 6.3 The spell — `SpellSummonSkeleton` (table 0x519918)

Constructor 0x2e16ec: level byte `+0`, back list `+4 = 0`, skill `+8`, owner `+0xc`, own
generator `+0x10` = one shared draw's value, table `+0x14`, skeleton handle `+0x18`. Run
0x2e177c: when the handle is empty the spell destroys itself (its slot 1 with 3). It is
reached only through an owner's attached-spell list; `Horsemen_run` drops the cast's
result, so a knight's spell is never run and never freed: one 0x1c-byte block per summon
until the level is torn down, the same on every machine (FINDINGS D22).

## 7. Skill 87, Tagar's Insects

`docs/spec/skills-69-101.md` section 87 specifies the skill from a reading; this section
is the executed version. The spell is attached to the third knight (`creature_addSpell`),
so its run is called from **that knight's** `Creature_run`, through slot 17, once per tick
the knight runs — before the knight's own activity test, animation step and AI.

### 7.1 Cast and constructor

- Cast 0x30c708 (skill, level, caster, position, facing): `L = skill.slot 14 (level, 0x14)`;
  `sound_playAtPos(res_find(…), position; 1.0)`; `s = pool_new(0x94)`; with a block the
  constructor; result `s` (0 without a block; the knight then calls
  `creature_addSpell(c, 0)`).
- Constructor 0x30c95c (spell, L, owner, skill): the Spell base as in 6.3 — **one shared
  draw** for the spell's own generator `+0x10`; eight empty victim handles `+0x18`; clock
  `+0x78 = 0.0`; hunt end `+0x7c = 0x4000101f`; current slot `+0x80 = −1`; victims
  `+0x82 = 0`; heading `+0x84` = the owner's facing; wander `+0x86 = 0`; swarm position
  `+0x88` = the owner's position + 24 × (cos, sin)(facing), z + 48. Per slot *i*: handle
  `+0x18 + 4i`, time `+0x38 + 4i`, next damage tick `+0x58 + 4i`.

### 7.2 Run — `SpellTagarsInsects_run` 0x30cbc8 (spell, position, facing)

The two arguments are copied and never used. `DT` = 0x3c888888. An **own draw** in this
section is `Spell_rand` 0x16a964 on the spell's generator `+0x10`.

```
active = tickVictims(spell)                                      7.4, with the clock of the previous tick
clock += DT
if huntEnd <= clock:
    if not active:  spell.slot 1 (spell, 3)                      the spell destroys itself
    return
limit = min(8, skill.slot 12 (0, level, owner, 10))              level is the signed byte spell+0
if not (n < limit):  return                                      no movement, no draw, no particle
tgt = none
if current >= 0:
    if handle[current] empty:  current = −1
    else:  tgt = its object;  if not valid(tgt, no marker test):  current = −1
if current < 0:
    tgt = pickTarget(spell, n > 0)                               7.3
    if tgt:  current = n;  handle_link(handle[n], tgt);  time[n] = clock + dist2D(tgt, swarm) × 0x3ba1605b
speed = 0x434b0da1                                               203.05 units a second
if tgt:
    (dx, dy) = tgt.xy − swarm.xy
    if 1.0 < dx² + dy²:
        e = atan2_16(dy, dx) − s16 heading                       an integer, not wrapped
        if e >= 0x4000: e = 0x7fff − e;   else if e < −0x3fff: e = −0x8000 − e          a reflection, not a wrap
        heading += e / 5                                         C division; stored as 16 bits
    dist = sqrt(dx² + dy²);   eta = clock + dist × 0x3ba1605b
    if eta < time[current]:  time[current] = eta
    left = time[current] − clock
    speed = dist / left                                          computed even when left is 0 (FINDINGS F3)
    if DT < left:  swarm.z += ((tgt.z + 48.0) − swarm.z) / (left × 60.0)
    if time[current] <= clock + 0x3d088888:                      arrival
        n += 1
        time[current] = f32(skill.slot 12 (2, level, owner, 10)) + 0x3d088888
        nextTick[current] = clock
        m = pool_new(0x20)
        if m:  a marker spell: level byte 1, back list 0, skill 0, owner = tgt,
               own generator = ONE SHARED DRAW, table 0x51ba90, +0x18 = the spell's owner, +0x1c = 0x57
        creature_addSpell(tgt, m or 0)
        speed = 0x434b0da1
        sound_playAtPos(res_find(effects lump, hit entry), tgt position; 1.0)
        current = −1;   huntEnd += 0x3f0041aa
d = OWN DRAW;  if d < 0x4906:  d2 = OWN DRAW;  wander = int((f32(d2) × 2⁻¹⁶ − 0.5) × 0x45f81000)       16 bits
a = s16(heading + wander)
swarm.x += (cos a × speed) × DT;   swarm.y += (sin a × speed) × DT
grow = min(1.0, clock × 0x40226fa7)
50 times:                                                        the cloud
    u = ball point (3 OWN DRAWS per try, retried while 1.0 < |u|²);   velocity = u × ((grow × 0x436d90b9) × DT)
    w = ball point (3 OWN DRAWS per try);   w = w × rsqrt(|w|²)  (1.0 / sqrt, one instruction)
    r = OWN DRAW;   point = swarm + w × ((grow × 0x4151d268) × (f32(r) × 2⁻¹⁶))
    k = OWN DRAW;   definition = 0x8e7598 if k >= 0x7d01, 0x8e75e8 if k >= 0x3a99, else 0x8e7638
    particle_spawn(definition, point, velocity; 0.0)
one more particle (0x8e7688, velocity 0) at swarm + an offset built from sin / cos of the
    heading and of (g_simFrame << 10), radius 0x4151d268, tilt 0x3f0f56fb
```

A tick that passes step "limit" makes at least 1 + 50 × 8 own draws; the wander draw is
the first of them and the particle draws of **this** tick decide the wander draw of the
next. A rebuild that wants the same swarm path has to make every particle draw, with the
same single-precision rejection test, whether or not it draws particles.

### 7.3 Target selection — 0x30d998 (spell, later) and 0x30db9c

`valid(o, marker test)` 0x30db9c: `o` exists; object flags 1 and 8 clear; the owner's slot
20 `(owner, o)` is non-zero; and, with the marker test,
`creature_findSpell(o, 0x57, owner)` finds nothing.

- First victim (`later` = 0): `world_collectObjectsInArc(swarm, heading, &list, owner;
  120.0, 90.0, 0.0)`; the **first** list entry that is valid (with the marker test) is
  returned. With `n = 0` no slot is occupied, so nothing else is tested.
- Later victims: `world_collectInSphere(swarm, heading, &list; 120.0)`; among the entries
  that are valid (marker test) and whose object is not behind one of the handles
  `0 … n−1`, the one with the smallest `dx² + dy² + dz²` to the swarm (strict `<`, start
  value 0x49742400 = 1,000,000) is returned.

Both end with `handle_clear(&list)`. The order of the two lists is the world queries'
(call-outs here; `tools/ref_world.py`).

### 7.4 Victims — `SpellTagarsInsects_tickVictims` 0x30d558 (spell) → 0 or 1

For each slot `i < n` (n re-read each round) whose handle holds an object `v` and whose
`time[i]` is not negative:

```
if time[i] <= clock or not valid(v, no marker test):
    m = creature_findSpell(v, 0x57, owner);  if m:  m.slot 1 (m, 3)
    time[i] = −1.0;   next slot
v's second flash quad:  +0x98 = 100, +0x9a = 0, +0x9c = 0, +0x9e = 4
active += 1
if nextTick[i] <= clock:
    owner exists and has object flag 0x40:  (low, high) = skill.slot 8 (1, level, 0, &low, &high; 0x3e4ccccc)
    else:  f = f32(skill.slot 12 (1, level, owner, 0));  g = f × 0x3e4ccccc;  high = int(f + g);  low = int(f − g)
    damage_apply(v, owner, 100000, 0, 0, 0x4000000, none, 0; f32(low), f32(high))
    nextTick[i] += 1.0
5 times (j = 0…4):
    u = ball point (3 OWN DRAWS per try);   velocity = u × 4.0
    s = j odd ? −1.0 : 1.0;   a = (g_simFrame + j × 0x2aaa) << 9
    point = v + ((s × v.radius) × cos a, (s × v.radius) × sin a,
                 (s × sin((g_simFrame − j × 0x2aaa) << 10)) × (v.height × 0.25) + v.height × 0.5)
    particle_spawn(0x8e7598, point, velocity; 0.0)
return active > 0
```

`damage_apply` is the full damage function (`tools/ref_combat.py`), with its shared
draws. A knight's swarm takes the second branch (tier-2 statistic, 20 % spread, both ends
truncated to integers).

`g_simFrame` is read here and in the cloud for particle positions only; inside a tick it
is the lockstep frame.

## 8. Other objects these classes create — call-outs, not modelled

| Created by | Object | Where its rules are |
|---|---|---|
| knight 0 cast | Disease Bolt projectile | `docs/spec/skills-01-34.md` 4 |
| knight 1 cast | Fire Storm, its flares and light | `docs/spec/skills-01-34.md` 7; FINDINGS F3 |
| knight 2's swarm | the marker spell's base behaviour (it has none of its own), the spell's destructor 0x30caa4 | `docs/spec/skills-69-101.md` 87 |
| knight death | loot (`Creature_dropLoot`), two physics props (holder slot 11), the named drop item | `docs/issues/kill-loot-xp.md`; FINDINGS K8, D39 |
| mounted constructor | `Nightmare` | `docs/monsters-2.md` |
| Zek state 0xd | `GroundPoundEffect` | `docs/monsters-2.md` |
| Zek wave end | `LightEffect`, the decal, the area damage | — |

## 9. Draws, generator by generator

**Shared seed 0x404464 — made by this code itself:**

| Where | Count | Condition |
|---|---|---|
| `SkillSummonSkeleton_cast` 0x2e1f7c–0x2e1fc0 (d1) | 1 | every cast |
| same, 0x2e20a4–0x2e20cc | 1 | a skeleton was built and `d1 <` chance |
| `SpellSummonSkeleton_ctor` 0x2e1710–0x2e1754 | 1 | skeleton and spell block |
| `SpellTagarsInsects_ctor` 0x30c980–0x30c9b4 | 1 | every constructed spell |
| `SpellTagarsInsects_run` 0x30cfc4–0x30d018 | 1 | each arrival at a victim, when `pool_new(0x20)` gave a block |

No function of `Horsemen`, `Skelight` or `Zek` draws the shared seed itself. Their
call-outs do: `GameObject_ctor` (1 per object), `damage_apply` behind every hit helper and
behind `combat_applyAreaDamage`, `Creature_dropLoot`, `loot_spawnNamedItem`, the props of
holder slot 11, `world_findFreeSpot`, a death script, and everything
`docs/spec/creature-tick.md` section 13 lists for the base tick.

**Own generator `c+0x44`:**

| Class | Where | Draws |
|---|---|---|
| any | `Creature_setStats` hit-point roll (constructor) | 1 |
| Horsemen | constructor (`+0x474`) | 1 |
| | state 5, target in reach | 1, or 2 when the first is even or the knight is not blocked |
| | state 5, target out of reach and out of the 72 cone | 1 per tick |
| | state 0x17 on the cast tick | 1 |
| | set-state 0 | 1 |
| Skelight | set-state 6 | 1 |
| Zek | state 5, target in front and not charging | 1 |
| | set-state 6, set-state 0x12 | 1 each |
| | wave end | 1 |
| | take-damage sparks | 3 per try × 50 |

**The insects spell's own generator `spell+0x10`** (seeded by the shared draw of its
constructor): per run that gets past the limit test, 1 or 2 for the wander, then per
cloud particle 3 per try for each of two ball points, 1 and 1; per active victim and tick
3 per try × 5. A run that returns early (hunt over, or all victims reached) makes only
the victims' draws.

**Cosmetic generator 0x404460:** `SkillSummonSkeleton_cast` only, and only when the
caster's model has sample points: 232 sample picks and 264 ball points of three draws per
try. Its values reach `model_getSamplePoint` and `particle_spawn` and nothing else.

**Third generator 0x404468:** not used by any function of this model (the base class's
gib branch uses it, `docs/spec/creature-tick.md` 13).

## 10. The level script's part

From the decompiled script (`scripts/DRUNARE.txt`, local), `docs/script.md` for the
built-ins, `docs/issues/arena-entry.md` and `docs/issues/arena-desync.md` for the
cutscenes. `ArenaScript` in the model is this section as code; its timing is in the unit
tests. **[O]** throughout: the script machine was not executed here.

**At load (`start`).** `hideMonster` for Rallos, the avatar and every object named
`knight` (inert bit 8, off the grid, not run). `setMonsterVal(name, 4, 2000)` for the
avatar and the knights: slot 34, so HomeRange becomes 2000 — the half-size of their
target-scan box, their leash radius and the boss-meter reach
(`docs/spec/creature-tick.md` 4.10, 6, 11).

**The trigger volume (`incoming`).** First time (quest variable `sawknights` clear): the
cutscene `knights`, post action `nosave`, the variable set. Later times: `setCFlag` bit 0
on the avatar only. The post action sets the save inhibit and bit 0 (MiniBoss) of the
avatar. The cutscene binds the four knights as actors; when it ends they are live — inert
byte 0, on the grid, on the active run list from their first active tick (so
`docs/issues/arena-desync.md` F1 and F2; not re-read here). That is the single wave of
knights; nothing spawns later except the fourth knight's skeleton.

**Each knight's death** runs its own entry from slot 28 inside the knight's tick: it sets
one of four quest variables and calls `knightDefeatedPause`. When all four are set, that
entry zeroes a script global and queues the deferred entry `knightDefeatedDelay`, which
runs once per frame from the next frame on: unless `gamePaused()` it increments the
global; when `getScaledTime(global) > 300` it starts the cutscene `cazic` (once: quest
variable `sawcaz`), else it queues itself again. `getScaledTime(n)` is
`int((f32(n) × 60.0) × 0x3c888888)` (0x14412c), which is `n − 1` for every count reached
here; so the cutscene starts on the **302nd** counted frame after the fourth knight's
death tick. Killing the summoner removes its skeleton in the same tick (3.4); a skeleton
that is still alive when another knight dies last is frozen by the cutscene with
everything else.

**The avatar's death** zeroes another global and queues `bossDefeatedDelay`. Per frame,
unless paused, the global goes up; past 250 scaled (count 252) it shows a notice, plays a
sound, sets two quest variables — and, having no jump after that block, queues itself
**twice** on that frame (FINDINGS D17). From then on two copies run per frame and the
count rises by 2. Past 1500 scaled (count 1502): `endmission` → post action `levelChange`,
the cutscene `bossdefeated`, `reapEnemies` (every dead non-player creature is destroyed),
quest variable `killedAv`. Unpaused that is **877** frames after the avatar's death tick,
not 1502. The remaining copy runs once more in the cutscene's first frame, finds the
variable set and stops. The post action grants the mission and changes level.

**Win condition.** Nothing counts kills: the level ends through the avatar's
`deathScript` alone. The knights matter only because the avatar is released by the second
cutscene, which needs all four knight variables.

**The cutscenes and these objects** (`docs/issues/arena-desync.md` F2): all three have
header flag 8, so every creature whose inert byte is 0 — knights, a skeleton, corpses,
players — is frozen (inert bit 4, not run, off the grid) from the tick the cutscene
starts to the tick it ends. `Horsemen_run`, `Skelight_run` and their timers therefore do
not advance during `cazic`; the fourth knight is dead by then anyway.

## 11. Reads that are not lockstep state, and what each gates

The class code adds **no input of its own** to the list in
`docs/spec/creature-tick.md` section 14. What it adds is consequences of inputs already
there, and presentation:

| Read | Where | What it gates |
|---|---|---|
| cflags bit 63 (active), from `Creature_updateActive` — per machine only where FINDINGS D6 applies | `Zek_run` 0x2c24c4 | **everything after it** in Zek's tick: the animation step, the target pick, the whole state switch with its own draws, and the ground wave's movement and explosion. An instance of FINDINGS D41 that is wider than the base class's gates. Not reachable in this level: Zek runs only as a cutscene actor, whose activity radius is 44000 |
| the same bit | `Creature_stepAnim`, called at 0x2724d4 / 0x272438, 0x2a8c54 | for `Horsemen` and `Skelight` only what the base says: `ev` is 0 and `anim` does not change for an inactive creature. So an inactive knight still chases and wanders (states 0, 1, 3 move it), still makes its state-5 own draws, but lands no hit, casts nothing and does not leave a swing or cast state. The result of `Creature_updateActive` itself is ignored by both classes |
| the cosmetic generator 0x404460 | `SkillSummonSkeleton_cast` 0x2e194c–0x2e1e40 | sample-point indices and particle vectors — arguments of `model_getSamplePoint` and `particle_spawn` only. The number of draws depends on its own values (rejection loops); nothing else reads them |
| item-model table 0x3e9ce0 (loaded asset pointers) | `Skelight_run` 0x2a8c24 | the pointer handed to holder slot 22 (presentation, D37) |
| word 0x503748, definition 0x8e4ba0 | `Zek_takeDamage` 0x2c3570 | one-time particle set-up |
| level name 0x44fe18 | `Skelight_ctor` 0x2a88f8; `Zek_setState` 0x2c3b8c | the skeleton's experience factor; Zek's death clip and weapon drop. Lockstep (the same level on every machine) |
| `g_levelMonsterLevel` 0x4f714c | written and restored inside `Skelight_ctor` | lockstep; nothing else runs in between |
| the name table | `world_findObjectByName` at 0x273278 and behind 0x2e23ac | lockstep (constructor and destructor only write it) |
| the pool (`pool_new` results; FINDINGS D21) | 0x272124, 0x2c2df0, 0x2c33e8, 0x2e2020, 0x2e221c, 0x30c788, 0x30cfa8 | a refused block skips a constructor and its shared draws: no mount, no ground pound (the timer is still set), no light, no skeleton (d1 is still drawn, "can use" stays true, the knight casts again), no summon spell, no insects, no marker on a victim (and no shared draw for it; the victim is infested all the same) |
| `g_simFrame` 0x44fdcc | `SpellTagarsInsects_run` 0x30d468, 0x30d4a8, 0x30d4bc; `…_tickVictims` 0x30d794 | particle positions only. Lockstep inside a tick |

Inside call-outs, already on the ledger and not re-examined here: `fx_spawn`'s camera
test (effects 2 and 7), the holder update's `isNearView(480)` (D37), `decal_add`'s local
option, the status-counter decrement in `Creature_draw` (D12).

**Plainly: no per-machine read was found in `Horsemen`, `Skelight`, `Zek`, the two casts
or the insects spell that is not already on the ledger.** (For the spell this is FINDINGS
SC1, now executed.) The one thing worth adding to an existing row
is that for `Zek` the active bit gates the whole class tick (first row above).

## 12. What follows for the "OUT OF SYNC" question

- Given the same damage, targets and world answers, every state change, own draw, shared
  draw and store of these classes is the same on two machines: the comparison in section
  13 sets the per-machine inputs both ways and finds the model — which has no notion of
  "which machine" outside the base class's known inputs — equal to the original on both.
- The executed code agrees with `docs/issues/arena-desync.md` on the summon chain (its
  table "The skeleton's life") step for step, with the refinements of section 14.
- The live result stands beside it: two linked emulator instances stayed in sync through
  twelve arena runs (FINDINGS V12).
- **[I]** So if something differs between real machines in this fight, it enters from
  outside these classes' own logic — through a call-out (the hit helpers' `damage_apply`,
  the world rays behind `creature_canSeeObj`, the physics props), through the base
  class's known inputs, or through floating point on real hardware — and not from the
  state machines described here. That is a statement about these functions, not about
  the cause of the reported desync, which this work did not find.

## 13. What the differential test covers

`python3 tools/difftest_arena_monsters.py` builds one creature with the game's own
virtual tables through the **original constructor**, six other objects, four players, a
skeleton to kill and the skill objects, and plays 1,500 ticks per run (3,000 for Zek,
whose run function is the largest). A tick is: the
driver acts as the rest of the game (the per-machine inputs of the base test, timers,
flags, targets, animation flags, the knight's and Zek's timers, a wave in flight), damage
arrives through the class's slot 2, the class's run function runs — with the base class
under it for real — and now and then the driver asks for a state (every number, valid or
not), delivers a killing blow in a state of its choice, or calls a helper or a cast on
its own. In the third knight's runs the insects spell, once a cast has built it, is one
of the knight's attached spells and so runs inside `Horsemen_run` (through `Creature_run`
and slot 17); the driver also runs it and its helpers directly and moves its clock, times
and victims about. Fourteen runs: knight variants 0–3, the mounted form, the skeleton and
Zek, each on machine A and machine B. For every call the model and the original must agree on: the
call-outs in order with arguments (stack-passed ones included), the set of bytes stored
and their final values, the shared seed and the number of draws, and the result.

Result at seed 4177 (the default):

| Property | Result |
|---|---|
| calls, stores, seed, result, one-sided faults — each of the fourteen runs (70 lines) | PASS: 40,423 original calls compared, 0 mismatches, none unresolved |
| calls in which the original read unmapped memory | 6, all at 0x112b68 inside `Creature_run` (the path follower, `docs/spec/creature-tick.md` 4.3); the model stopped at the same place each time |
| shared-seed draws seen | 502 in direct `SkillSummonSkeleton_cast` calls, 214 in direct `SkillTagarsInsects_cast` calls, 34 in direct `SpellTagarsInsects_run` calls (arrivals), 101 inside `Horsemen_run` (the two casts and the spell reached through the knight's own tick, and the base class's own), 16 inside `Zek_run` (the base class's); none anywhere else |

Calls compared per entry point: Horsemen_ctor 332, Horsemen_run 14,678, Horsemen_setState
1,941, Skelight_ctor 87, Skelight_run 2,915, Skelight_setState 415, Zek_ctor 152, Zek_run
5,850, Zek_setState 775, Zek_takeDamage 762, Zek_slot35 107, Creature_takeDamage (slot 2 of
the other two classes) 2,426, SkillSummonSkeleton_canUse 456, SkillSummonSkeleton_cast 240,
SpellSummonSkeleton_run 148, SkillTagarsInsects_cast 238, SpellTagarsInsects_run 1,722
(besides the runs inside the knight's tick), tickVictims 134, pickTarget 158,
isValidTarget 172, and the small base helpers on their own: canSeeTarget 698,
canSeeTargetIn 707, isTargetCharging 1,457, countAlliesNearTarget 464, isBlockedByTarget
464, turnToTarget 678, onDeath 257, slot 16 438, slot 34 145, the three timer tests 438
each, slot 7 93.

Deaths: the test counts the AI state the creature was in on the tick that killed it. On
foot the knights died in every state from 0 to 0x23 and in the out-of-range numbers 0x24,
0x30, 0x7fff and −5 (variant 0: 36 different states, variants 1–3: 33, 35 and 31); the
skeleton in 0, 1, 3, 5, 6, 0x10, 0x13, 0x17 (through the charm rule of `Creature_run`;
damage cannot kill it there) and 0x7fff; Zek in every one of its states. The mounted
knight cannot be killed while mounted (3.4); its 13 deaths are after dismounting.

Coverage of the original as executed in that run (from the interpreter's trace; a block
starts at the function entry, at a branch target and after a conditional branch's delay
slot):

| Function | Basic blocks | Instructions |
|---|---|---|
| `Horsemen_ctor` | 15 of 15 | 354 of 354 |
| `Horsemen_run` | 102 of 102 | 760 of 760 |
| `Horsemen_setState` | 27 of 29 | 413 of 420 |
| `Skelight_ctor` | 10 of 10 | 189 of 189 |
| `Skelight_run` | 43 of 43 | 274 of 278 |
| `Skelight_setState`, `Skelight_shatter` | 11 of 11 | 176 of 176 |
| `Zek_ctor` | 7 of 7 | 249 of 249 |
| `Zek_run` | 118 of 118 | 1063 of 1065 |
| `Zek_takeDamage` | 10 of 10 | 210 of 210 |
| `Zek_setState`, `Zek_slot35` | 17 of 17 | 271 of 271 |
| `Creature_ctor` | 33 of 33 | 305 of 306 |
| `creature_setDefEntryParams` | 1 of 1 | 22 of 22 |
| the ten small base helpers of 2.3–2.5 | 44 of 44 | 251 of 254 |
| `SkillSummonSkeleton_canUse` | 7 of 7 | 25 of 25 |
| `SkillSummonSkeleton_cast` | 47 of 49 | 626 of 630 |
| `SpellSummonSkeleton_ctor`, `…_run` | 8 of 8 | 59 of 59 |
| `SkillTagarsInsects_cast`, `SpellTagarsInsects_ctor` | 6 of 6 | 132 of 132 |
| `SpellTagarsInsects_run` | 46 of 46 | 612 of 612 |
| `SpellTagarsInsects_tickVictims` | 26 of 26 | 272 of 272 |
| `SpellTagarsInsects_pickTarget`, `…_isValidTarget` | 31 of 31 | 166 of 166 |
| `Spell_rand` | 1 of 1 | 10 of 10 |
| **all 35** | **610 of 614 (99.3%)** | **6439 of 6460 (99.7%)** |

The instructions not counted in fully covered functions are padding after the last
return. The base class underneath is counted by its own test.

Floating point: every float is compared as a bit pattern under the interpreter's default
FPU model; the whole test was repeated under its three other adder models (`--fpu ps2g1`,
`chop`, `nearest`, 400 ticks per run, and again for the third knight with the insects
spell) with the same outcome. That shows the same operations in the same order, not that a
console produces the same last bit (`docs/issues/dynamic-tests.md`). The two
double-precision compares (wave step, summon height) run through the C library's own
soft-float routines on the interpreter side and as an exact comparison of the single
values on the model side; they agree for every finite value.

Blocks never entered, and why:

- `Horsemen_setState` 0x273020 (clearing the mount handle in case 0) and 0x2731e8 (case
  0x13 with a mount): a mounted knight has already returned for every state below 0x19,
  so both are dead code. The `or mounted` half of case 0x12 is dead for the same reason.
- `SkillSummonSkeleton_cast` 0x2e20f8 and 0x2e2108: exits of the three-way choice for a
  remainder that is none of 0, 1, 2.

These four are the whole difference between 610 and 614; no reachable block was left out.

What stays scripted: everything in `EXTERNALS` of the two models — in particular the
sight tests (`creature_canSeeObj`, `creature_findEnemyInCone`), the hit helpers, the
animation functions, `Creature_setStats`, `Creature_init`, `Creature_applyKnockback`,
`Creature_deadUpdate`, `Creature_dropLoot`, the weapon holder, object construction below
`Creature_ctor`, and the skills' statistic slots. Their answers are random within
plausible ranges: "the target is in reach" is an answer of the script, not geometry, so
combinations a real callee cannot produce are tested and combinations only a real callee
produces may be missed. Animation events arrive at random, not at the table's times.

The driver also stores state numbers no set-state would store (0x15 and up for Zek and
the skeleton) to reach the "anything else" rows.

## 14. Where earlier documents turned out wrong or short when executed

1. The brief for this work speaks of three mounted knights. The level has four, on foot;
   variant 2 (`UndeadKnight3`) casts Tagar's Insects and variant 3 (`UndeadKnight4`)
   summons. (`FINDINGS.md` D3 and `docs/issues/arena-desync.md` have it right.)
2. `docs/monsters.md`, Horsemen, "on the hit event a full-damage arc test…, on event bit
   1 a second test with a third of the damage": the two are alternatives on one tick, and
   the constructor's event table gives bit 1 to exactly one clip, state 10's, which has
   no bit-0 event. State 10 — entered from state 5 on an odd own draw when
   `creature_isBlockedBy` says so — is therefore the one-third hit with flags 0x100001
   and nothing else; states 6, 7 and 0xb are two, three and three full hits.
3. Same section, state 5: the "one draw in 60 returns to chase" also needs no ally near
   the target; and the choice among 10, 7 and 6 is "first draw odd **and** blocked → 10,
   else second draw odd → 6, even → 7".
4. `docs/monsters.md` 1.4, state 1 "leave to 3 with a target": a knight in state 1 that
   sees its target goes to state **0**; the skeleton and Zek go to 3.
5. Not in any document: `Horsemen_setState` stores the requested number for an unknown
   state after a nested set-state 3; `Skelight_setState` and `Zek_setState` store 0
   (Zek's without touching the animation); a mounted knight ignores set-state 0x14
   (but loses creature flag 0x200 and whatever `Creature_filterState` cleared).
6. `docs/monsters.md` 1.3 lists the holder update as an optional first step. It is first
   only in `Horsemen_run`; `Zek_run` does it after the activity test, and `Skelight_run`
   after it with a different slot (22, with an item model) —
   `docs/spec/creature-tick.md` 12.4 described that one correctly, now executed.
7. `docs/monsters.md`, Skelight: state 0x13 leaves to 0, not 3; set-state 0x12 is ignored;
   states 2, 4, 7–0xf, 0x11, 0x15, 0x16 do nothing in the run function (no way out), and
   set-state turns a request for them into state 0; the `+0xf4` "attack frames left" is 1
   and counts only once the clip has stopped playing.
8. `docs/monsters-2.md`, Zek: "0.43 % of the angle to the reverse bearing is subtracted"
   is right in size; the direction is away from the reverse bearing's zero, and at the
   enemy's bearing the heading alternates by ±140 units a tick rather than settling. Not
   stated there: state 5 synchronises its clip to the frame counter; the wave and every
   own draw stop while Zek is inactive; the default set-state stores 0 with no clip.
9. `docs/spec/skills-01-34.md` 11 and `docs/issues/arena-desync.md`: confirmed, with one
   addition — the fifth factor of the skeleton's `Creature_setStats` is the experience
   factor, 1.0 everywhere except one level.
10. `docs/spec/skills-69-101.md` 87 held up when executed: the run, the target choice
    and the victim loop of section 7 were written from the instructions and agree with
    its listing. Two additions: cast step 1 "level through slot 14 (no-op)" — the level
    stored in the spell is slot 14's **result**, a no-op only if that slot returns its
    argument (the slot is a call-out here); and both particle loops read `g_simFrame`
    for their positions.
11. `Creature_isTargetCharging` (named in `docs/monsters.md` 1.3 without a definition):
    as coded it is true for a fast target facing **away** from the creature (2.3).

## 15. Not done

- Disease Bolt, Fire Storm and its flares, `GroundPoundEffect`, `LightEffect`,
  `Nightmare`, `Cazic`, the insects spell's destructor: specified in the documents
  section 8 names, not modelled or executed here.
- The call-outs of section 13's last paragraph, above all `creature_canSeeObj`,
  `creature_findEnemyInCone`, the two hit helpers, `Creature_applyKnockback`,
  `Creature_deadUpdate`, `Creature_init` and the weapon holder's slots.
- The three draw functions and `Skelight`'s save / load / clone slots (read, not run).
- The level script was read from its decompile; the script machine did not run it.
- Nothing was run on a console.
