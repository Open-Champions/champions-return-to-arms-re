# Mounted Horsemen: the Nightmare mount, the rider–mount link and its lifecycle

Status (2026-10-23): **Executed** in `tools/ee_emu.py` against the reference model
`tools/ref_horsemen_mount.py` by `tools/difftest_horsemen_mount.py`, seeds 20973 and 7, no
mismatch (section 9). Nothing here has run on a console or a full emulator. Addresses are
SLUS_209.73 US v2.00 (SHA-256 `292f6f48…d7`). No raw game bytes are in this document;
the two decoded property fields and their addresses are recorded below.

This document is the prose version of `tools/ref_horsemen_mount.py`. The rider side of the
class (`Horsemen_ctor`, `Horsemen_run`, `Horsemen_setState` with its mounted branches) is
already modelled and executed in `tools/ref_arena_monsters.py` /
`docs/spec/arena-monsters.md` section 3; this document cites it and adds what was missing:
the mount class, the link, the factory rows and the whole lifecycle with both objects
running for real.

Reading guide: "Executed" = compared instruction by instruction with the model on the
states the difftest built; "Observed" = read at the address; "Inferred" = follows from
those; "Unknown" = not settled, with what would settle it.

## 1. What is built, and from which records

The level factory has five rows that produce a `Nightmare`:

| Row (name compare) | Class-string address | Allocation | Constructor call | Arguments |
|---|---|---|---|---|
| rider variant 0 | 0x532cc8 | `pool_new(0x478)` 0x15b2ec | `Horsemen_ctor` at 0x15b3d4 | (block, record name, position, facing, property list, 0, **1**) |
| rider variant 1 | 0x532cd8 | 0x15b32c | 0x15b3d4 | variant 1, mounted 1 |
| rider variant 2 | 0x532ce8 | 0x15b36c | 0x15b3d4 | variant 2, mounted 1 |
| rider variant 3 | 0x532cf8 | 0x15b3ac | 0x15b3d4 | variant 3, mounted 1 |
| `Nightmare` alone | 0x532c98 | `pool_new(0x3d8)` 0x15b1c4 | `Nightmare_ctor` at 0x15b1e4 | (block, record name, position, facing, property list) |

The rider rows are the class `Horsemen` with the mounted flag (`docs/monsters.md` section
5 table: types `RiderDisease`, `RiderWar`, `RiderPestilence`, `RiderDeath`; the factory
difftest of research commit dfcc8d3 executes the name compares and the arguments with the
constructor stubbed). **Executed here end to end** (section 9.2): each rider row from its
name compare through the real `Horsemen_ctor`, which allocates and builds the real mount
with the real `Nightmare_ctor`; and the `Nightmare` row through the real `Nightmare_ctor`.

Native-horsemen r3 (`codex/native-horsemen` 8c2ae9f) builds these four pairs; its focused
audit passed. That is a constructor result, not a play-scene run. Section 11 lists the
remaining runtime work.

### 1.2 Four on-foot rows (Observed factory, Executed comparison)

| Class text at | Name | Entry / constructor site | Pool | Variant / mounted |
|---|---|---|---|---|
| 0x532dc8 | `UndeadKnight1` | 0x15b804 / 0x15b900 | 0x478 | 0 / 0 |
| 0x532dd8 | `UndeadKnight2` | 0x15b844 / 0x15b900 | 0x478 | 1 / 0 |
| 0x532de8 | `UndeadKnight3` | 0x15b884 / 0x15b900 | 0x478 | 2 / 0 |
| 0x532df8 | `UndeadKnight4` | 0x15b8c4 / 0x15b900 | 0x478 | 3 / 0 |

Each branch compares the record type with `libc_strcasecmp` (0x3b81a0), allocates one
0x478 block through `pool_new` (0x14fdb8), and calls the same `Horsemen_ctor` (0x271c70).
The record's type-name pointer, position, facing and property-list pointer are passed
through; there is **no fixed property list in these factory rows**. The constructor's
last argument is zero (0x15b904). Its mounted branch at 0x27211c is skipped, so it
builds one `Horsemen` with variant +0x470, state 0, no +0x3c8 mount link and no Nightmare.
The record's property pointer reaches `Creature_ctor` / `GameObject_ctor` (0x271cec,
0x109d68); the level record, not the factory type, determines its properties. A read-only
scan of the v2.00 disc's 120 level GOB files (120 `objects.ob` lumps, 18,675 records)
found exactly one `objects.ob` placement per on-foot type, all in
`DRUNARE.GOB::drunare.lmp`. `tools/difftest_horsemen_onfoot.py` asserts the whole scan,
the exact records and fields, then executes the original property parser in `ee_emu.py`
on both seeds (section 9.5). **Observed** record-relative offsets and decoded fields
(the offset is within that lump's `objects.ob`, not an EE address):

| Type | Record / property-pointer array | Ordered property fields | `dropitem` |
|---|---|---|---|
| `UndeadKnight1` | 0x124 / 0x138 | `deathscript`, `wait=1`, `light1`, `light2`, `name=knight`, `dropitem` | `rejuvpotion` |
| `UndeadKnight2` | 0x154 / 0x168 | same fields | `healingpotion` |
| `UndeadKnight3` | 0x184 / 0x198 | same fields | `rejuvpotion` |
| `UndeadKnight4` | 0x1b4 / 0x1c8 | same fields | `healingpotion` |

The four `deathscript` values are distinct and nonempty; the two light properties are
identical across the four placements. `docs/spec/arena-monsters.md` section 1 documents
their arena role. A record constructed by script or from other unexamined sources could
carry different properties: the factory does not choose this table by type.

The four branches through the real constructor match `ref_arena_monsters.Model` for
calls, writes and shared seed on both seeds, 4/4 each; section 9.2 gives the probe.
An allocation failure branches to 0x15d9a4 without a constructor call (Observed at
0x15b824, 0x15b864, 0x15b8a4, 0x15b8e4).

### 1.1 What one rider record consumes (Executed, section 9.2)

In this order, inside the one factory call:

| # | Call (site) | Pool | Shared seed 0x404464 | Object's own generator +0x44 |
|---|---|---|---|---|
| 1 | `pool_new(0x478)` (row) | rider block | – | – |
| 2 | `GameObject_ctor(rider, …)` inside `Creature_ctor` 0x109d68 | – | **1 draw** (seeds rider +0x44; `docs/spec/arena-monsters.md` 2.1, `docs/spec/object-system.md` 2.2) | – |
| 3 | `Creature_setStats` (rider, with a type name) | – | – | 1 draw (hit-point roll; arena spec 2.1) |
| 4 | first cast time `+0x474 = clock + 480 + d % 120` (`Horsemen_ctor`) | – | – | 1 draw |
| 5 | `pool_new(0x3d8)` 0x272124 (only when the mounted argument is non-zero, test 0x27211c) | **mount block** | – | – |
| 6 | `GameObject_ctor(mount, …)` inside the mount's `Creature_ctor` | – | **1 draw** (seeds mount +0x44) | – |
| 7 | `Creature_setStats` (mount; type name text 0x547380) | – | – | mount: 1 draw |
| 8 | `Nightmare_setState(mount, 0)` called directly at 0x270ab8 | – | – | mount: 1 draw (`+0xf4`) |
| 9 | `Creature_init(mount)` 0x270b20 | – | – | – |
| 10 | `handle_link(rider + 0x3c8, mount)` 0x272194, `handle_link(mount + 0x3c8, rider)` 0x2721a4 | – | – | – |
| 11 | `Horsemen_setState(rider, 0x1b)` direct call 0x2721b0 | – | – | – |
| 12 | `Creature_init(rider)` 0x2721b8 | – | – | – |

So a rider record takes **two pool blocks and two shared-seed draws**; an on-foot
`UndeadKnight` record takes one of each. A failed mount allocation (`pool_new` returns 0,
test 0x272130) skips 6–11: the knight is built on foot, unlinked, in state 0. (The second
null test at 0x272184, after the constructor, is redundant.)

## 2. The two objects and the link

### 2.1 Rider (`Horsemen`, vtable 0x515730, block 0x478) — fields the link uses

| Offset | Type | Meaning while mounted | Writers / readers |
|---|---|---|---|
| +0x3c8 | handle | the mount (node; object at node +0xc). 0 = on foot | linked 0x272194; dropped by `Horsemen_setState` 0x23 and 0 (`handle_clear` + store 0) |
| +0x10..+0x18, +0x38 | vec3, s16 | copied from the mount every tick, then `obj_updateGridCell` (head of `Horsemen_run`, 0x2723c4–0x2723fc) | |
| +0x234 | handle | target: replaced by the mount's target whenever the mount has one and it differs (0x272444–0x272490) | |
| +0x232 | s16 | AI state; 0x1b–0x1e riding poses, 0x1f–0x22 mounted swings, 0x23 dismount, 0x19/0x1a hide/show | pushed by the mount (section 5) |
| +0xc | u32 | object flags; state 0x1b sets 9 (not solid + bit 8), state 0 clears 9, 0x19 sets 0xb, 0x1a clears 2 | `Horsemen_setState` |
| +0x470 | s8 | variant 0–3: selects the mount's property list (`0x500848 + 12 v`, 0x272138–0x272178) | |
| +0x18 | float | on dismount (0x23) z and drawn height +0x3c are raised by 48.0 (0x27358c) | |

The rider's own run in states 0x1b–0x1e does nothing; 0x1f–0x22 hit every enemy in a
10000 arc turned −0x4000 (to the side) on event bit 0 (`docs/spec/arena-monsters.md` 3.3).
`Horsemen_setState` with the mount handle set returns, after `Creature_filterState` and the
clearing of creature flag 0x200, for **every request below 0x19** (0x272f7c–0x272f94).

### 2.2 Mount (`Nightmare`, vtable 0x5155e8, block 0x3d8, class definition 0x500680)

| Offset | Type | Meaning | Where |
|---|---|---|---|
| +0x3c8 | handle | the rider; 0 for a factory `Nightmare` | cleared 0x270a30; linked 0x2721a4; dropped in set-state 0x14 (0x2719ac) |
| +0x3cc | s16 | fade: +1 per tick while dead (deleted at 100), set 120 by state 0x1a and counted down to 0; draw fades the model and skips it at ≥ 98 | run 0x14 / 0x1a, set-state 0x1a, draw |
| +0x3d0 | s32 | clock until which the mount stays non-solid after trampling a player (clock + 120) | slot 11 0x271534; run head 0x270c94 |
| +0x3d4 | s32 | kick latch: bit-0 event sets it, bit-2 event clears it, while set the mount turns to its target | run kicks; set-state 6/0x17/0x18 clears |
| +0xf4 | s32 | idle / wander / hidden timer | set-state 0, 1, 0x19; run 1 |
| +0xe0 | float | −20.0: seat offset along the facing (used by the seat transform) | ctor 0x270a64 |
| +0xdc | float | scale 1.2 | ctor 0x270a74 |
| +0x318 | s16 | attack cooldown 60 on entering 0x10 | set-state 0x2718cc |
| +0xd0/+0xd2/+0xd4 | s16 | damage min/max/rating from `Creature_setStats`; kicks and trampling use **twice** min and max | run, slot 11 |

The property list the rider hands over is a 12-byte, null-terminated pointer array per
variant at `0x500848 + 12 v`. **Observed** in SLUS_209.73 US v2.00:

| Variant | Pointer slot → text | Field | Value | Status |
|---|---|---|---|---|
| 0 | 0x500848 → 0x547320 | `miniboss` | 1 | Observed |
| 0 | 0x50084c → 0x547330 | `name` | `horsedisease` | Observed |
| 1 | 0x500854 → 0x547320 | `miniboss` | 1 | Observed |
| 1 | 0x500858 → 0x547348 | `name` | `horsewar` | Observed |
| 2 | 0x500860 → 0x547320 | `miniboss` | 1 | Observed |
| 2 | 0x500864 → 0x547358 | `name` | `horsepestilence` | Observed |
| 3 | 0x50086c → 0x547320 | `miniboss` | 1 | Observed |
| 3 | 0x500870 → 0x547370 | `name` | `horsedeath` | Observed |

The null slots at 0x500850, 0x50085c, 0x500868 and 0x500874 are **Observed**.

There are no other entries before each null pointer. `obj_getPropInt` 0x14c880 reads
`miniboss` as 1. `Creature_ctor` 0x109d68 reads it at 0x10a0e8 and sets creature
flag bit 0 at `+0xa8` at 0x10a100. `GameObject_ctor`
0x14cb10 stores the list pointer at `+0x2c` (0x14cd64), parses `name` in
0x14cd84–0x14cf58 and calls `objNames_add` at 0x14cf4c (target 0x14bce0).
Each name resolves back to its
mount through `world_findObjectByName` 0x14f498. `obj_getPropStr` 0x14f4c0 returns
the name value; `ShowName` is absent, so `+0x368` and object flag 0x100000 stay clear.
The two constructor effects and parser results were **Executed** against the original
code for all four lists with seeds 20973 and 7 by `difftest_horsemen_props.py` (section 9.3).
`Nightmare_ctor` then
overwrites three fields such a list could have set: HomeRange `+0x3c0 = 2400.0`,
visualrange `+0x3ae = 2400` and scale `+0xdc = 1.2`. (Earlier documents called this
argument "variant data"; it is the constructor's property-list argument, passed through to
`Creature_ctor` in t1: Observed at 0x27096c / 0x2709d0, Executed.)

### 2.3 Constructor `Nightmare_ctor` 0x270968 (block, type name, position, facing, property list)

`Creature_ctor(block, type name, position, (s16) facing, def 0x500680, property list;
10.0)`, then (all Executed):

| Field | Value | Instruction |
|---|---|---|
| +0x48 table | 0x5155e8 | 0x270a04 |
| +0xb0 turn rate | 0.6 (0x3f199999) | 0x2709dc / 0x270a0c |
| +0x1c radius | 30.0 | 0x2709ec / 0x270a20 |
| +0x28 (u8) | 50 | 0x2709f8 / 0x270a28 |
| +0x3c8 rider | 0 | 0x270a30 |
| +0xb8 move speed | 0 (root motion) | 0x270a34 |
| +0x232 state | 0 | 0x270a38 |
| +0xec | clock (0x44fdcc) | 0x270a40 / 0x270a58 |
| +0x3c0 HomeRange | 2400.0 (from integer 0x960) | 0x2709e8 / 0x270a5c |
| +0x5c fire resistance | 1.0 | 0x270a44 / 0x270a60 |
| +0xe0 seat offset | −20.0 | 0x270a50 / 0x270a64 |
| +0xb4 kind | 10 | 0x270a24 / 0x270a68 |
| +0x3ae visualrange | 2400 | 0x270a6c |
| +0xa8 creature flags | \|= 0x20200040000 | 0x270a10–0x270a1c / 0x270a70 |
| +0xdc scale | 1.2 (0x3f999999) | 0x2709c0 / 0x270a74 |
| +0xf4, +0x3cc | 0 | 0x270a78, 0x270a88 |

Then `anim_clear(+0x114)` 0x270a84, `anim_push(+0x114, entry 3 (+0x1c), 1)` 0x270aac,
`Nightmare_setState(0)` **direct** 0x270ab8 (no rider yet, so nothing is pushed),
`creature_setDefEntryParams` for entries 4 (0x270ae4) and 8 (0x270b10), each with masks
1, 2, 2, 4 at 0.5, 0.8, 1.2, 1.5 seconds (0x270a7c, 0x270a98, f20, 0x270aa4) — entries of
the shared class definition — `obj_runEvery60` 0x270b18, `Creature_init` 0x270b20.

## 3. Tick order

The objects tick in their run-list order (`docs/spec/object-system.md` section 5). The
constructor calls `obj_runEvery60` for the rider first (0x271f10), then for the mount
(0x270b18); that function (0x14f2b8) steps a shared 0..59 cursor **before** linking to
the front of its selected slow list. Thus the pair starts in adjacent slow lists, rider
then mount in the cyclic 60-list order (**Inferred** from these Observed calls and the
executed object-system model). When `Creature_updateActive` (0x10c0f0) changes activity,
`obj_updateActive` (0x14db08) moves that object to the front of the every-frame list
(0x14f248), or the next slow list; these independent relinks can change which member
runs first. The difftest calls mount then rider on each synthetic tick, so its results do
**not** establish a fixed play-scene pair order. A native port should use its ordinary
object run-list scheduler and check order in an integrated scene.

### 3.1 Rider, mounted head (`Horsemen_run` 0x27236c; arena spec 3.3)

holder slot 21 → position and facing from the mount → `obj_updateGridCell` →
`Creature_processDamage` → `Creature_run` (non-zero ends the tick) →
`Creature_updateActive` → `Creature_stepAnim(1.0)` → **no** knock-back, **no** target pick →
take the mount's target → state switch.

### 3.2 Mount (`Nightmare_run` 0x270bbc)

`Creature_processDamage` 0x270be4 → `Creature_run` 0x270bf4 (non-zero ends the tick) →
`Creature_updateActive` 0x270c04 (result unused) → `Creature_stepAnim` 0x270c48 with 0.9
(0x3f666666, 0x270c2c) in state 7 while animation flag 0x20 is up, else 1.0 →
`Creature_applyKnockback(0.2)` 0x270c60 → slot 23 (pick target) 0x270c7c → outside state
0x14, object flag 1 cleared once `+0x3d0 < clock` (0x270c94–0x270cb4) → switch on the state
(signed; 27-entry jump table 0x546f70; anything else ends the tick).

## 4. Mount states (run)

| State | Run (Executed) | Leaves by |
|---|---|---|
| 0 idle | slot 25 (can see target) → 3; `Creature_isAwayFromHome` → 1 | |
| 1 wander | slot 25 → **3**; `+0xf4 < clock` → 0; else `Creature_moveToDest` | |
| 3 chase | no target → 0; `creature_findEnemyInCone(facing, 4000; 0, 36)` → 5; `Creature_canSeeTargetIn(facing, 0x7fff; 0, 36, 0)` → 5; `Nightmare_pickChargeTarget` and `findEnemyInCone(facing, 2000; 0, 240)` → **7**; target seen within 120 (arc 0x7fff) but not within arc 6000 → 0x17; else `Creature_moveToTarget` | 0x270d94–0x270ea4 |
| 5 close in | no target → 0; `findEnemyInCone(facing, 4000; 0, 36)` → 6; `canSeeTargetIn(**0**, 0x7fff; 0, 36, 0)`: then by `Creature_angleToTarget` a (signed): \|a\| < 4000 → 6, \|a + 0x4000\| < 6000 → **8**, \|a + 20000\| < 6000 → 0x18, else 0x17; otherwise seen within 120 but outside arc 6000 → 0x17; else `Creature_isNotRooted` → 3 | 0x270eb4–0x271010 |
| 6, 0x17, 0x18 kick | `Creature_settle`; event bits 0 or 1: `Creature_hitAllEnemiesInArc(facing, 0x1194, 2·min, 2·max, rating, flags 1, no descriptor; 0, 42)`; event bit 2: the same with flags 0x100041; latch (2.2); animation flag 8 down → 3 | 0x271018–0x2710e0 |
| 7 charge | turn to target while animation flag 0x20, else only when `canSeeTargetIn(facing, 6000; 0, 2400, 0)`; `Creature_moveBy(0,0,0)` (root motion; contacts reach slots 10/11); while flag 8 up and 0x10 down: one `terrain_raycast(world, position + (0,0,24), (cos f, sin f, 0)·360, 0; 480)`, a result strictly in (0, 1) starts clip entry 7 (+0x3c, 0x803, 0.1), syncs it, then blends entry 6 (+0x34, 0x810, 0.1, 0.1); flags 8 and 0x10 both down → 3 | 0x2710e8–0x27129c |
| 8 rider's swing | no rider → 0; the **rider's** animation flag 8 up → wait; else → 5 | 0x2712a4 |
| 0x10 back off | `Creature_isAttackReady` → 3; else `Creature_fleeFromTarget(0)` | 0x2712f0 |
| 0x13 stunned | `Creature_isNotStunned` → 0 | 0x2712d8 |
| 0x14 dead | position += (cos f, sin f)·11.666666 (0x413aaaa9) with **no collision test**, `obj_updateGridCell`, fade +1, `Creature_deadUpdate(ev, 0-vector, 1; 30.0)`; at fade ≥ 100: object flags \|= 0x4002, `obj_delete` | 0x271334–0x271404 |
| 0x1a reappear | fade > 0 → fade − 1; at 0 → 0 | 0x270ce4 |
| 2, 4, 9–0xf, 0x11, 0x12, 0x15, 0x16, 0x19 | nothing | |

Slot 10 `Nightmare_onHitTerrain` 0x27142c: in state 7, set-state 3. Slot 11
`Nightmare_onTouchList` 0x271484: in state 7 only, for every touched object with object
flag 0x40 (a player) that `creature_inKnockdownAnim` says is not knocked down:
`damage_apply(victim, mount, 100000, 0, 0, 0x100041, no elements, 0; 2·min, 2·max as
floats)` (rating 100000 = always hits), then object flag 1 and `+0x3d0 = clock + 120`.

`Nightmare_pickChargeTarget` 0x271a6c: for each player slot below the player count
(0x4d8ae0, re-read every step) whose object (record +0x43d8, stride 0x4c30) exists with
object flag 8 clear, up to eight rays `terrain_raycast(world, player + (0,0,24),
(cos a, sin a, 0)·360, 0; 480)` for a = 0, 0x2000, …; a result strictly between 0 and 1
is a hit and ends that player. The first player with no hit becomes the mount's target
(`handle_clear` + `handle_link` on +0x234) and 1 is returned; else 0. The table
capacity and the maximum player count are **Unknown** here (not cited in the research); a
native port must clamp or refuse a player count above whatever capacity it establishes
rather than copy this unbounded read. It reads the
**global** player table (all players, not local ones) and the terrain: no per-machine
input (`docs/monsters-2.md` per-machine note confirmed by execution).

## 5. Mount set-state and what it pushes onto the rider

`Nightmare_setState` 0x27155c: `Creature_filterState` (a refusal returns without storing),
then the case (27-entry jump table 0x546fe0), then the state is stored at +0x232
(0x2719bc). With a rider linked, the case calls the rider's slot 27:

| Mount state | Own work | Rider gets |
|---|---|---|
| 0 | `+0xf4 = clock + own % 120`; clip +0x1c (3, 0.3) | 0x1b |
| 1 | path cleared, wander destination, `+0xf4 = clock + own % 120 + 300`; clip +0x3c (0x803, 0.3), synced | 0x1c |
| 3 | clip +0x3c (0x803, 0.1), synced | 0x1c |
| 5 | clip +0x1c (6, 0.3) | 0x1b |
| 6, 0x17 | clip +0x44 blended (8, 0.1, 0.1); latch 0 | 0x1e |
| 0x18 | same | 0x1f |
| 7 | clip +0x44 blended (0x24, 0.1, 0.0); clip +0x2c chained (0x80b) | 0x1d |
| 8 | nothing of its own | **0x20 + own % 3** (one own draw; nothing without a rider) |
| 0x10 | cooldown +0x318 = 60, path cleared, clip +0x3c (0x803, 0.1), synced | 0x1d |
| 0x12 | the CURRENT state is stored (no hit reaction) | 0x1b |
| 0x13 | clip +0x1c (3, 0.1) | 0x1b |
| 0x14 | object flag 0x4000, slot 28 (on death, 0), clip +0x2c (0x806, 0.3); **no loot call** | 0x23, then the mount's handle is dropped |
| 0x19 | object flags \|= 0xb, `+0xf4 = clock + 300` | 0x19 |
| 0x1a | object flags &= ~0xb, fade = 120, clip +0x1c (3, 0.1) | 0x1a |
| others (2, 4, 9–0xf, 0x11, 0x15, 0x16, ≥ 27) | only the store | – |

All randomness is the mount's own generator. **No function of this document draws from
the shared seed** (Executed: the model's draw count matched the original on every call; the
only shared draws observed under `Nightmare_run`, 12 and 6 over the two seeds, come from
the base `Creature_run` burn path for an object with the player flag 0x40, which the driver
sometimes gives the object under test and a real mount does not carry — Inferred).

## 6. Lifecycle

**Spawn.** Section 1.1. After the factory call: rider state 0x1b with object flags 9 (not
solid, and bit 8 — the bit `Nightmare_pickChargeTarget` treats as "dead" for players; which
target searches skip a monster carrying it was not checked here), mount state 0, both
linked.

**Riding.** The mount's AI decides; each of its state changes pushes a riding pose or swing
onto the rider (section 5). The rider's set-state ignores everything below 0x19, so the
base class's own requests (hit reactions, stun, root, death from damage) do nothing to a
mounted rider. The rider's attacks happen only through the mount's state 8 (one of the
three mounted swings 0x20–0x22) and the mount's state 0x18, which pushes the 0x1f swing;
mount states 6 and 0x17 push the 0x1e pose, which does nothing (rider runs in 0x1b–0x1e do
nothing, section 2.1). The rider's damage is its own `hitAllEnemiesInArc` in 0x1f–0x22.

**Mount death.** Damage kills the mount like any creature (`Creature_processDamage` →
slot 27 0x14). Set-state 0x14 sends the rider 0x23 and drops the mount's handle; the
rider's 0x23 starts the dismount clip (+0xb4, 0x80c), drops its own handle and is lifted
48 units. The dead mount gallops off along its facing at 11.666666 units per tick through
walls, fading for 100 ticks, and is deleted (`obj_delete`; its handles read null once the
delete list is flushed, `docs/spec/object-system.md` destructor step 5). It drops no loot
itself (slot 28 still runs).

**Dismount.** Only the mount's death (or a direct set-state 0x23 / 0 on the rider) ends
the ride. In 0x23 the rider waits for the clip, pushes the stand clip (+0x84) when its flags
show "ended, still queued", and goes to state 0, which clears object flags 9: from then on
it is an ordinary on-foot knight with its variant's cast (`docs/spec/arena-monsters.md` 3.3).

**Rider lethal damage.** `Creature_takeDamage` (0x116638) subtracts the rider's own HP;
the mount takes none of that damage. At HP ≤ 0, `Creature_processDamage` (0x110d30)
requests rider state 0x14 at 0x111de8, which the mounted `Horsemen_setState` (0x272f4c)
refuses for states below 0x19. The base death path continues to `player_giveExp`
(call at 0x1120e4 or 0x1121e8)
even though the rider remains linked and in riding state. In the directed function-level
probe (section 9.4), a lethal rider hit leaves HP negative, rider state 0x1b, both links
intact and mount state 0; four `player_giveExp` calls are recorded. **Executed**, including
the award call sequence; whether a shipped play scene can target and damage a mounted
rider is **Unknown**. After the mount dies and sends 0x23, a fresh rider hit enters 0x14
on foot. A direct `killMonster` request while linked also passes through slot 27 and is
refused (**Inferred** from `docs/script.md` section 31 and the set-state execution).

**Stranded rider (Executed; reachability Unknown).** The rider's 0x23 passes through the
rider's own `Creature_filterState` first. With the rider's stun timer (+0x31c), root timer
(+0x314) or attack cooldown (+0x318) running, or in the PvP-mode-B refusal case, the filter
turns 0x23 into 0x13 / 5 / 0 / 0x10 or refuses it; any of those is below 0x19, so the
mounted set-state returns — but the mount drops its own handle regardless. The rider stays
linked to a dying mount, keeps copying its galloping position, and once the mount is
deleted is left on foot in a riding state (0x1b–0x1e, or a swing) with object flags 9 still
set, which nothing in its run clears. Seen 4 times per seed in the difftest, whose driver
sets those timers often; whether anything in the game can stun, root or cool down a mounted
rider is not established (the script built-in `rootMonster` sets +0x314 = −1 on any
creature by name, `docs/script.md` §21; whether a shipped script roots a rider would settle
it).

**Hide / show.** Mount 0x19: flags 0xb (not solid, not drawn, dead bit), rider 0x19 (rider
flags 0xb); mount 0x1a: flags back, fade in from 120, rider 0x1a. No caller of 0x19/0x1a was
found: the scripts reach slot 27 only with 0 (`rootMonster`, `stopFollowingPath`) and 0x14
(`killMonster`) (`docs/script.md` §21, §31, §40); **Unknown** otherwise.

## 7. Drawing (presentation, Executed)

`Nightmare_draw` 0x270b4c: with a fade, `model_setFade(fade)`; below 98 `Creature_draw`;
with a fade `model_resetDrawState`.

`Horsemen_mountSeatTransform` 0x2719d4 (mount, matrix out):
`model_getAttachWorldMatrix(model, (x + cos f·e, y + sin f·e, z), f, anim, **attach point
10**, out; scale)` with e = +0xe0 (−20). `Horsemen_draw` 0x2721f8, mounted: that matrix
times the inverse of the rider's own **attach point 9** (`model_getAttachMatrix` 0x27224c,
`mat34_invert` 0x272258, `mat34_mul` 0x272268), a shadow (0x2722b4), and `model_draw` with
centre (x, y, z + height·0.5) and the show mask +0x220 (0x2722e0); on foot `Creature_draw`.
Then holder slot 18 (held parts). Nothing is stored into either object.

## 8. Constants with addresses

Every value below is in the model and was compared by execution.

| Constant | Value | Address |
|---|---|---|
| mount block size | 0x3d8 | 0x272128 (rider), 0x15b1c8 (factory) |
| rider block size | 0x478 | 0x15b2f0 … 0x15b3b0 |
| mount class definition | 0x500680 | 0x27098c / 0x27099c |
| mount vtable | 0x5155e8 | 0x2709f4 |
| mount property lists | 0x500848 + 12·variant | 0x272170–0x272178 |
| mount type-name text | 0x547380 | 0x27213c / 0x272148 |
| placeholder hp | 10.0 | 0x2709a4 |
| run jump table | 0x546f70, 27 entries | 0x270cd0 |
| set-state jump table | 0x546fe0, 27 entries | 0x271598 |
| charge animation speed | 0.9 | 0x270c2c |
| knock-back scale | 0.2 | 0x270c54 |
| chase/close cone | 4000, 36.0 | 0x270db8 / 0x270db0 |
| charge cone | 2000, 240.0 | 0x270e30 / 0x270e1c |
| side-kick ranges | 120.0, arc 6000 | 0x270e4c, 0x270e84 |
| angle bands | 4000, +0x4000 / 6000, +20000 / 6000 | 0x270f34, 0x270f50 / 0x270f5c, 0x270f78 / 0x270f84 |
| kick arc, reach | 0x1194, 42.0 | 0x271034, 0x271040 |
| kick flags | 1; 0x100041 | 0x271050; 0x271068 / 0x271098 |
| charge turn range | 2400.0, arc 6000 | 0x27110c, 0x271114 |
| ray height, length, factor | 24.0, 360.0, 480.0 | 0x271170, 0x2711e0, 0x271200 (picker: 0x271af8, 0x271b6c, 0x271b8c) |
| picker step, probes | 0x2000, 8 | 0x271bac, 0x271bd4 |
| player count, table, stride, object | 0x4d8ae0, 0x4d8af0, 0x4c30, +0x43d8 | 0x271a78, 0x271aec, 0x271ab0, 0x271b1c |
| trample rating, flags, non-solid time | 100000, 0x100041, 120 | 0x2714dc, 0x2714e8, 0x27152c |
| gallop speed | 11.666666 (0x413aaaa9) | 0x271358 |
| dead update factor | 30.0 | 0x2713b4 |
| fade limit, draw cut | 100; 98 | 0x2713e8; 0x270b64 |
| idle / wander / hide timers | % 120; % 120 + 300; + 300 | 0x271630; 0x271698 / 0x2716c4; 0x2715bc |
| reappear fade | 120 | 0x2715e4 |
| back-off cooldown | 60 | 0x2718cc |
| rider swing pick | % 3 + 0x20 | 0x271848 / 0x271870 |
| seat offset, attach points | −20.0; 10 (mount), 9 (rider) | 0x270a50; 0x271a34, 0x272248 |
| rider mounted refusal | state < 0x19 | 0x272f90 |
| dismount lift | 48.0 | 0x27358c |

## 9. What was executed

### 9.1 The random runs

`python3 tools/difftest_horsemen_mount.py <owner SLUS_209.73> --seed N -v`, 1,500 ticks per
run, six runs (a factory `Nightmare` on machines A/B; a mounted rider on A/B, net and
offline). Everything outside the models is a scripted stub; the creature base class, the
arena model and this model run for real on both sides.

| | seed 20973 | seed 7 |
|---|---|---|
| calls compared | 15,410 | 16,121 |
| properties passing (calls, writes, seed, result, faults per run + factory and damage chains) | 32 / 32 | 32 / 32 |
| `Nightmare_run` / `Nightmare_setState` calls | 5,657 / 528 | 6,246 / 578 |
| `Horsemen_run` / `Horsemen_setState` calls | 5,977 / 381 | 5,980 / 335 |
| mount deaths / fade-outs deleted | 161 / 66 | 143 / 53 |
| rider dismounted by the mount's death / left linked | 10 / 4 | 7 / 4 |
| rider death on foot | 35 | 30 |

Block coverage of the original, both seeds: `Nightmare_ctor`, `_draw`, `_onHitTerrain`,
`_onTouchList`, `_setState`, `_pickChargeTarget`, the seat transform, `Horsemen_ctor`,
`Horsemen_draw` and `Creature_angleToTarget` 100 %; `Nightmare_run` 98.8 % / 100 %;
`Horsemen_setState` 86.2 %; `Horsemen_run` 63.7 % / 61.8 % (the on-foot states, covered by
`tools/difftest_arena_monsters.py`).

### 9.2 The factory rows

The same command runs `factory_chain` first: four rider rows, four on-foot rows and the
`Nightmare` row,
from the row's name compare (the class string copied from the image into a scratch buffer
in memory only) to the instruction after the constructor call, with the real constructors
underneath; then calls, writes and seed are compared with `pool_new` + the model's
constructor, and the link is checked on the original's memory (both handles, rider state
0x1b and variant, mount state 0, the property list the mount's `GameObject_ctor` received,
rider flags 9). The on-foot checks assert one `GameObject_ctor`, the passed-through record
property pointer, variant, state 0 and no mount link. 9 / 9 rows pass on both seeds. The
factory test passes the list pointer through a stubbed `GameObject_ctor`; section 9.3
separately executes that constructor, the property parser and `Creature_ctor` on the
four fixed **mount** lists. The on-foot row's record list varies by placement; its four
shipped GOB lists and the original parser are checked separately in section 9.5.

### 9.3 Property-list execution and unit tests

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_horsemen_props.py <owner SLUS_209.73>
--seed N` for N=20973 and N=7: 4/4 variants, zero mismatches on each seed. The reference
is `tools/ref_horsemen_props.py`. The difftest asserts all 12-byte pointer arrays and the
decoded two-entry contents against the executable, then runs the original `Creature_ctor`
and its real `GameObject_ctor`, `obj_getPropInt`, `obj_getPropStr`, name registration and
lookup. It checks MiniBoss flag bit 0, stored list pointer, registered name, absence of
`ShowName`, and absent-key parser results. The test's pool and world are synthetic; it is
function execution, not a game run.

`tools/test_ref_horsemen_mount.py`, 14 tests, no game files: the addressed property model, the push table, the rider's
swing choice, the stranded rider, the factory construction, the constructor constants, the
picker, trampling, the dead mount's run-off. They compute expected values from the model's
own formulas and constants, so they are a regression guard on the model and are **not
evidence** about the original; the comparison with the original is the difftest (9.1, 9.2).

### 9.4 Directed damage routing

`difftest_horsemen_mount.py -k damage --seed N` for N=20973 and 7 compares seven calls
per seed: the real mounted constructor, a lethal hit and tick for the rider, a lethal hit
and tick for the mount, then a fresh hit and tick for the on-foot rider. Both seeds match
the `ref_creature`, `ref_arena_monsters` and `ref_horsemen_mount` models for external calls,
writes, shared-seed draws, results and faults. The probe clears a synthetic
`IgnoreDamage` flag that the scripted `obj_getPropInt` may set; it does not establish
the presence of that flag in a shipped scene. It observes four `player_giveExp` calls
after the linked rider's lethal hit, followed by a dismount on mount death and rider
state 0x14 after a new on-foot hit. This remains function-level execution.

### 9.5 On-foot placement and property evidence

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_horsemen_onfoot.py
<owner SLUS_209.73> <owner v2.00 ISO> --seed N` for N=20973 and 7: both pass.
The read-only ISO scan walks all 120 GOBs, all 120 `objects.ob` lumps and 18,675
placement records, asserting exactly one of each `UndeadKnight1`–`4`, all in Drundar.
It checks the four exact record/property-array offsets, all six ordered property keys,
`wait=1`, `name=knight`, alternating potion drops, four distinct nonempty death scripts
and identical two-light values. For each list it places its disc strings in scratch
memory and executes the original `obj_getPropInt` / `obj_getPropStr` in `ee_emu.py`:
24 parser reads per seed, no mismatch. The executable SHA-256 is pinned; scan coverage
counts and content assertions reject a changed disc. This proves the shipped GOB
placements and parser behavior, not properties of objects created by scripts.

## 10. Open

- Integrated run-list order after activity changes (section 3).
- Whether a play-scene attack can target a mounted rider and award experience while he
  remains linked (section 6).
- Property lists of any on-foot records created outside the scanned level GOB placements
  (section 1.2).
- Who requests mount states 0x19 / 0x1a (section 6).
- Whether a mounted rider can carry a stun, root or cooldown in the game (section 6).
- Slot 1 of the mount table (0x3cae50) was not read (`docs/monsters-2.md`).
- Which shipped scripts, if any, look up the four observed mount names is not established
  by the property-list difftest.
- Table capacity / maximum player count for the charge-target picker (section 4).

## 11. Ordered native port and verification list

The audited native-horsemen r3 branch (`codex/native-horsemen` 8c2ae9f) builds the four
mounted rider/MiniBoss pairs. It leaves the four on-foot factory rows unbuilt and has no
verified mounted play-scene tick. The list below starts from that state; construction
success alone does not verify movement, combat or lifecycle.

1. **Build the four on-foot factory rows** (section 1.2): map `UndeadKnight1`–`4` to
   variants 0–3 of the same 0x478 `Horsemen` constructor, with mounted = 0, one pool
   allocation and the record's own property list. Do not attach the fixed Nightmare
   MiniBoss lists or infer every level's properties from the Drundar arena. Compare the
   four factory paths in `difftest_horsemen_mount.py -k factory`, the Drundar record
   pointers, fields and whole-level count in `difftest_horsemen_onfoot.py` (both seeds),
   and the existing on-foot run / cast paths in `difftest_arena_monsters.py`.
2. **Schedule both objects by ordinary run-list rules** (section 3): the constructor
   assigns consecutive slow-list slots; activity can independently relink each to the
   every-frame list. Verify the first active ticks and later relinks in an actual scene,
   recording which runs first and whether the rider copies current or prior mount pose.
3. **Port mount movement and charge** (sections 3.2–4): `Nightmare_run`, states 0/1/3/5/7,
   target selection, root-motion `Creature_moveBy`, terrain ray, charge clip changes,
   and slots 10/11 for terrain and trampling. Keep the original picker bounds explicit;
   refuse a player count beyond established host capacity. Check position, facing,
   contact damage and non-solid cooldown against directed function-level vectors.
4. **Port attacks and state coupling** (sections 2, 4–5): mount kicks and twice-stat
   damage, rider swing states 0x1f–0x22 and their own hit arcs, mount-to-rider state
   pushes, target-copy timing and each object's own random generator. Compare both
   objects' state, hit calls and draws before claiming a mounted combat path.
5. **Port damage and lifecycle as observed** (section 6 and 9.4): keep rider and mount HP
   separate; include the linked rider's refused death state and base experience-award
   path, mount death to rider 0x23, filter-dependent stranded rider, 100-tick mount
   fade/deletion, rider dismount and later on-foot death. Do not silently redirect
   damage between objects or repair the original refusal in an exact port.
6. **Port presentation and verify in the play scene** (section 7): mount fade and the
   rider seat transform; inspect riding, charge, kicks, both lethal-hit orders,
   dismount and deletion at scene level. Keep the fixed mount 0x19/0x1a cases available
   but their caller **Unknown**; do not invent a hide/show trigger.
