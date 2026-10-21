# Mounted Horsemen: the Nightmare mount, the rider–mount link and its lifecycle

Status (2026-10-21): **Executed** in `tools/ee_emu.py` against the reference model
`tools/ref_horsemen_mount.py` by `tools/difftest_horsemen_mount.py`, seeds 20973 and 7, no
mismatch (section 9). Nothing here has run on a console or a full emulator. Addresses are
SLUS_209.73 US v2.00 (SHA-256 `292f6f48…d7`). No game bytes, strings or decoded data are
in this document; class and property identifiers are named, values are described.

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

The native client counts these four rider records as unbuilt ("mounted Horsemen needs
Nightmare_ctor", open-champions creature-stats round 3 report: 4 records over the disc's
111 levels; disc counts only).

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

The property list the rider hands over is a 12-byte list per variant at `0x500848 + 12 v`
(Executed only as a pointer: the difftest compares the pointer passed to `Creature_ctor`
and `GameObject_ctor`, `difftest_horsemen_mount.py`, and never reads the list). **Unknown:**
what the entries are. An earlier draft said "a MiniBoss flag and a name"; nothing in this
branch decodes or checks the contents, so that is **Inferred at most** (from the list being
the same kind of argument a placed record passes) and is not used below. In particular,
whether the mount gets creature flag 1 (the boss-meter block of `Creature_run`,
`docs/creatures.md` C3) or a per-variant object name (`docs/spec/object-system.md` 2.2
step 7) is **not established**. A native port must read the list from the image, must not
assume a MiniBoss flag, and must refuse to hard-code either until the 12-byte lists are
decoded and difftested (section 10). `Nightmare_ctor` then
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

The objects tick in their run-list order (`docs/spec/object-system.md`); the difftest runs
mount then rider, which is what the rider's head assumes (it copies the mount's position
of this tick). Which order the game's run lists give a rider and its mount is **Unknown**:
both join `obj_runEvery60` in the one factory call, the rider first (its own
`obj_runEvery60` in `Horsemen_ctor`, `docs/spec/arena-monsters.md` 3.2 step 9, before the
mount is allocated) and the mount second (0x270b18); since a link goes to the front of a
list (`docs/spec/object-system.md`), settling it needs that document's run-list rules
applied to the two calls and to the later move to the active list.

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

**Rider death.** Impossible while linked (the set-state refuses 0x14; Executed: the event
"rider refused state 0x14 while mounted" 14 and 18 times over the two seeds; it holds for
the script built-in `killMonster` too, which goes through slot 27 — `docs/script.md` §31,
Inferred). On foot it dies as an UndeadKnight does (loot, held parts dropped, slot 28;
arena spec 3.4).

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
| calls compared | 15,399 | 16,110 |
| properties passing (calls, writes, seed, result, faults per run + factory rows) | 31 / 31 | 31 / 31 |
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

The same command runs `factory_chain` first: the four rider rows and the `Nightmare` row,
from the row's name compare (the class string copied from the image into a scratch buffer
in memory only) to the instruction after the constructor call, with the real constructors
underneath; then calls, writes and seed are compared with `pool_new` + the model's
constructor, and the link is checked on the original's memory (both handles, rider state
0x1b and variant, mount state 0, the property list the mount's `GameObject_ctor` received,
rider flags 9). 5 / 5 pass on both seeds.

### 9.3 Unit tests

`tools/test_ref_horsemen_mount.py`, 13 tests, no game files: the push table, the rider's
swing choice, the stranded rider, the factory construction, the constructor constants, the
picker, trampling, the dead mount's run-off. They compute expected values from the model's
own formulas and constants, so they are a regression guard on the model and are **not
evidence** about the original; the comparison with the original is the difftest (9.1, 9.2).

## 10. Open

- Run-list order of rider and mount (section 3).
- Who requests mount states 0x19 / 0x1a (section 6).
- Whether a mounted rider can carry a stun, root or cooldown in the game (section 6).
- Slot 1 of the mount table (0x3cae50) was not read (`docs/monsters-2.md`).
- The contents of the four 12-byte mount property lists (`0x500848 + 12 v`) were never
  decoded or compared: whether they hold a MiniBoss flag and/or a name is Unknown
  (Inferred at most). To settle it, decode the lists from the image in the difftest and
  assert the entries, with seeds 20973 and 7, citing the entry addresses. Until then the
  mount's creature flag 1 and any per-variant object name are unestablished, and so is
  which script, if any, addresses a mount by a name.
- Table capacity / maximum player count for the charge-target picker (section 4).

## 11. What the native client should implement, ranked

For open-champions-godot `native/` (state read on 2026-10-21 from the creature-stats
worktree: `script_commands_objects.cpp` refuses the four rider records as "mounted Horsemen
needs Nightmare_ctor"; `arena_monsters.cpp` already has the rider's mounted set-state and
head from `tools/ref_arena_monsters.py`, and treats `Nightmare_ctor` as an external).

1. **Account a rider record as two blocks and two shared draws** (section 1.1), even
   while it stays refused: `pool_new(0x478)` then `pool_new(0x3d8)` (only when the first
   succeeded), and two `GameObject_ctor` draws, rider first. Today the refused record
   counts one block and one unmodelled draw, so the pool and the draw count after it are
   short by one each. Small, and it keeps later pool exhaustion right.
2. **`Nightmare_ctor` and the mounted tail of `Horsemen_ctor`** (sections 1.1, 2.3): this
   alone turns the four records into built objects. It reuses what the native already has
   (`Creature_ctor` with the property list, `Creature_setStats` from the object's own
   generator, `creature_setDefEntryParams`), plus the two `handle_link`s, the direct
   `Nightmare_setState(0)` (one own draw) and `Horsemen_setState(0x1b)`, in the order of
   1.1. Test vectors: `tools/difftest_horsemen_mount.py` factory rows (section 9.2).
3. **The mount's tick and set-state** (sections 3.2, 4, 5): `Nightmare_run`,
   `Nightmare_setState` with the rider push table, slots 10 and 11, the charge-target picker
   and `Creature_angleToTarget`. No shared-seed draws; every random choice is the mount's own
   generator. Without it a built mount stands still and the rider never leaves 0x1b.
4. **The lifecycle edges exactly as executed** (section 6): mount death → rider 0x23 through
   the rider's own filter (including the stranded-rider outcome, which must not be
   "fixed"), the dead mount's 100-tick run-off without collision and its deletion, the
   rider's dismount clip and return to state 0. The tick order of the pair is still Unknown
   (section 3): keep it a host decision that is reported, not assumed.
5. **Presentation**: the seat transform (attach point 10 of the mount at facing·(−20)) times
   the inverse of the rider's attach point 9 for the rider's model matrix, and the mount's
   fade (section 7). Nothing in simulation reads these.
6. **Leave refused**: a set-state 0x19 / 0x1a request has no known caller (section 6).
   Implement the executed cases but do not invent a trigger for them.
