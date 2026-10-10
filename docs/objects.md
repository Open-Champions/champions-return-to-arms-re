# Objects: GameObject, the world lists, level records, the allocator, props, the factory

Area `objects`, code 0x147300–0x160000 (219 functions). Symbols: `symbols/objects.tsv`.
Everything here was read from the executable; nothing was run. Each claim is marked
**Observed** (read at the address given), **Inferred** or **Unknown** where it is not obvious.

## What is in the range

| Addresses | Contents |
|---|---|
| 0x1473b4–0x14799c | last script built-ins (already in `names.tsv`) |
| 0x147a84–0x14a480 | world lighting: level sun/ambient, per-object light state, a 90 × 90 grid of light nodes. Drawing only |
| 0x14a490–0x14f9f8 | **the world**: grid, run lists, delete list, object name table, `GameObject` constructor/destructor, property lookup, activity test, level-object records (save/load) |
| 0x14fa88 | program entry point (not part of this subsystem) |
| 0x14fcd8–0x150948 | **allocator**: the object pool and the tagged heap (`mem.cc`) |
| 0x1509d0–0x153900 | `GameObject_rand`, projectile movement, `Projectile`, `MissileWeapon`, `AnimatedMissile` |
| 0x1539fc–0x159b38 | the `Prop` family: `Prop`, `ParticleProp`, `PhProp`, `ItemProp`, `UserParamProp`, `Gold`, `CosmeticProp`, `CosmeticPropAnim`, light markers, `Player1` |
| 0x159c20–0x15da80 | **the object factory** (class-name string → constructor) |
| 0x15dac0–0x15ffff | `PushPhysicsProp`, `WaveMaker` (continues past 0x160000) |

Source file names that survive in assertion strings: `object.cc`, `mem.cc`. One assertion
names a field: the grid link at object +8 was called `gridReference` (0x5321d8).

## Reading the virtual tables: 16 slots, not 17

`tools/vtab.py` reported 17 entries for `GameObject` and 92 for `Creature` when this was
written; the tool and `vtables.txt` have since been corrected and give 16 and 39
(`docs/issues/vtable-labels.md`). **Observed**: the
last entry of every table is a null terminator, and the old scanner ran on past it when it
did not recognise the next table's type-info function. `GameObject` has **16** virtual
functions (table 0x5122a8, null at entry 17). `Creature` has **39** (table 0x50cc58, null at
entry 40); "entries 41–65" and "67–91" are the separate tables of `WeaponShield` (0x50cda0)
and `Weapon2` (0x50ce70), 24 functions each. Their type-info functions are 0x3c22b0 and
0x3c1e28. Corrected class names for every table are easy to get: the class's own name is the
last name string its type-info function references.

The earlier version of this section said the scanner failed where the next type-info
function was "too large". That was incomplete in two ways. The two functions are not
large: each is 0x9c bytes, and the function table in `tools/ps2elf.py` *measures* them as
0x130 and 0x1a0 (`docs/issues/vtable-labels.md` traces that to unreferenced code after
them, which the table does not see as a function). And a
third table was lost for a different reason: `PoisonRain` (0x51aa68) was hidden inside
`SkillLifeTap` because its type-info function 0x3cffd4 was cut short by a false function
start at 0x3d0000 in the same function table (that value occurs as a data word).

### GameObject virtual slots

Default bodies are one-instruction stubs at 0x3c7e88–0x3c7f28 and 0x3c8120 (runtime area).

| Slot | Meaning | Kind | Evidence |
|---|---|---|---|
| 1 | destructor (arg bit 0 = also free the block) | Observed | 0x14cf90; the delete-list flush at the top of `runObjects` passes 3 |
| 2 | take damage (amount, attacker, flags) | Observed | `Creature_takeDamage` 0x116638 |
| 3 | "trigger": script built-in `trigger`, cutscene keys and several net handlers call it | Observed | callers 0x1422e4, 0x196e8c; Creature body 0x11a5f0 |
| 4 | run, once per simulated frame | Observed | `runObjects` 0x14bb44–0x14bcc0 |
| 5 | draw | Observed | `world_drawObjects` |
| 6 | something touched me (other) | Observed | called in `obj_moveAndCollide`, `Creature_moveBy` (0x114208), `obj_moveWithCollision` |
| 7 | path search finished (found) | Observed | callers in the path service 0x184878, 0x1849c8 |
| 8 | load state from a level record (buf) → bytes read | Observed | `world_loadRecords` 0x14e9e4 |
| 9 | save state into a level record (buf) → bytes written | Observed | `obj_writeRecord` 0x14e0f8 |
| 10 | moved into terrain (hit normal); called by `Creature_moveBy` | Observed | 0x114348 |
| 11 | list of objects touched this move; called by `Creature_moveBy` | Observed | 0x1143a0 |
| 12 | "something happened near you" (radius, a, position, b) | Observed call, meaning Inferred | `world_notifyObjectsNear` 0x11a3b0, two sites in `Player_run` |
| 13 | interact prompt (text out, player slot) | Observed | `Player_interact` 0x1b2814 |
| 14 | interact (player slot) | Observed | `Creature_interact` 0x116bd8 |
| 15 | clone (copy constructor into a new pool block) | Observed | 0x11c1a0; the only virtual caller is `net_frameLoop` 0x13b540 |
| 16 | get model: creatures return the first resolved resource of their class definition, `GameObject` returns 0 | Observed | 0x3c2738; 209 call sites |

## GameObject layout (0x4c bytes)

All offsets **Observed** in `GameObject_ctor` 0x14cb10 and `GameObject_clone` 0x11c1a0 unless
noted.

| Offset | Type | Meaning | How known |
|---|---|---|---|
| +0x00 | handle head | "who refers to me": back links of every handle that points at the object. Also the back link used when the object sits on the delete list or the always-draw list | 0x14f234, 0x14edf8 |
| +0x04 | handle head | run-list membership (one link at most) | 0x14f27c, 0x14dc4c |
| +0x08 | handle head | grid-cell membership (`gridReference`) | linked at 0x14ccdc; `obj_updateGridCell` 0x14f028 |
| +0x0c | u32 | flags, see below | |
| +0x10 | float[3] | position x, y, height | |
| +0x1c | float | collision radius, default 24 | ctor |
| +0x20 | float | height extent, default 72 | ctor |
| +0x24 | ptr | class definition: `{lump, generation, {name, resolvedPtr}…}`; names are resolved once per level generation (global 0x41bf78) | ctor, `obj_setClassDef` 0x14f5f0 |
| +0x28 | u8 | draw half-width for frustum tests, default 25 | 0x14b3c0 |
| +0x29 | u8 | draw height for frustum tests, default 73 | 0x14b42c |
| +0x2c | ptr | property list: null-terminated array of `key=value` strings from the level record | 0x14c880 |
| +0x30 | float | vertical velocity (gravity subtracts 9 per frame) | tails of `obj_moveWithCollision` 0x14d4b8 and `Creature_moveBy` 0x113c48 |
| +0x34 | char * | class/type name string the factory was called with (creatures: the type name used for stats and boss tests) | `world_createObject` 0x14f6c8, `world_loadRecords` |
| +0x38 | u16 | facing angle | |
| +0x3c | float | creatures: smoothed height used for drawing | `Creature_run` tail |
| +0x40 | float | creatures: velocity of that smoothing | same |
| +0x44 | u32 | private random state (`GameObject_rand` 0x1509d0), seeded from `g_randSeed` | ctor 0x14cd80 |
| +0x48 | ptr | virtual table | |

`clone` copies +0x0c…+0x44 and starts the three handle heads empty.

### Properties

`obj_getPropInt` 0x14c880, `obj_getPropStr` 0x14f4c0 and `obj_getPropFloat` 0x14c9c0 take
(object, key, n) and return the n-th `key=value` entry (third argument is an occurrence
index, **not** a default; absent → 0). **Observed**: they lower-case the key string in place,
so key literals in `.data` change at run time. The constructor registers every `name=`
value in a 512-slot hash (`objNames_add` 0x14bce0; keys 0x5f76f8, objects 0x5f7ef8), which
is how scripts find objects (`world_findObjectsByName` 0x14bf58). A `hide` property moves
the object to the off-grid list. `action=` properties name scripts run by
`obj_runActionScripts` 0x14dcc8, which points the "script self" global 0x4039f8 at the
object while they run.

### Flag word at +0x0c

Bits already listed in OVERVIEW are repeated with their evidence here. "set"/"test" lists are
from a pattern search over the decompiled C for the word at +0xc; they are not exhaustive.

| Bit | Meaning | Kind | Evidence |
|---|---|---|---|
| 0x1 | not solid: movers do not push out of it, `world_findFreeSpot` ignores it | Observed | tests 0x1140a4 (`Creature_moveBy`), 0x14d75c (`obj_moveWithCollision`), `world_findFreeSpot`; set at death (0x2009) |
| 0x2 | not drawn by the grid walk; set for members of the always-draw list; a new flag-2 object is linked off-grid | Observed | 0x14b3b4, 0x14b574; `obj_addToAlwaysDraw` 0x14edd8; `obj_linkToGrid` 0x14f120 |
| 0x4 | excluded, together with 0x1 and 0x8, from `world_collectInSphere` (mask 0xd) | Observed test; meaning Unknown | `world_collectInSphere` 0x14ab80; about 20 setters in other areas |
| 0x8 | dead | Observed | |
| 0x10 | has a top that can be stood on: movers compare heights instead of pushing out | Observed | 0x114114, 0x14d7e4; set by `PushPhysicsProp_ctor` |
| 0x20 | is a Creature (set only by `Creature_ctor`) | Observed | `Creature_ctor` 0x109d68 |
| 0x40 | is a Player (set only at 0x1a1d28) | Observed | |
| 0x80 | has an owner handle at +0x4c (projectiles); damage is credited to the owner | Observed | `Projectile_ctor` 0x150e48, 0x11670c |
| 0x100 | hit flash, read and cleared by drawing | Observed | set 0x110de8, clear 0x10babc |
| 0x200 | touch-only: movers call slot 6 but are not pushed out; projectiles pass through | Observed | 0x11411c, 0x14d838, 0x150d1c |
| 0x400 | on the mover: do not push me out of other objects | Observed | 0x114174, 0x14d844 |
| 0x800 | lives in grid B (drawn, never returned by box queries) | Observed | 0x14cc78, 0x14f094 |
| 0x1000 | expendable: `runObjects` may delete it when the pool is nearly full; thinned from saves | Observed | 0x14ba74; `world_writeRecords` 0x14e140 |
| 0x2000 | killed creature / corpse; thinned from saves at higher thinning levels | Observed | set 0x111dfc and in `Creature_loadState`; `world_writeRecords` |
| 0x4000 | transient: never written to a save | Observed | 0x14e1dc; set by `Projectile_ctor`, `PhProp_ctor`, about 70 others |
| 0x8000 | not run (slot 4 skipped) | Observed | tested before each slot-4 call in `runObjects`; set by hide |
| 0x10000 | Unknown | — | set 0x2b1e80, 0x2b33f4 (torch/lantern constructors) |
| 0x20000 | prediction copy | Observed | hard-coded skip at 0x14aa54 in the box query |
| 0x40000 | Unknown | — | set 0x243624, 0x2b1e80, 0x2cb4e8, 0x31d180; tested in the object sweep 0x18b014 |
| 0x80000 | activity radius forced to 44000 (cutscene actors) | Observed | 0x14db24; set 0x19904c |
| 0x100000 | can be interacted with | Observed | `Creature_ctor`, `PhProp_ctor` for items |
| 0x200000 | this machine's own player | (FINDINGS D13) | |
| 0x400000, 0x800000 | set and cleared on player objects by a game-message handler; `Creature_updateActive` tests both, 0x1ec140 tests 0x800000 on every live player. They are the menu-state bits of game message 2 (`hudmsg_sendMenuState`, `docs/ui.md`): a non-zero state sets 0x400000, and 0x800000 as well when the state is above 1; state 0 clears 0x800000 and sets record +0x4bc8 to 10, the countdown after which `Player_run` clears 0x400000 (`docs/player.md`) | Observed; this row gave the meaning as Unknown | 0x1d8d84–0x1d8dec, 0x10c174, function 0x1ec140, 0x1ac6f8–0x1ac724 |
| 0x1000000 | friendly to players (script `friendly`) | Observed | 0x145304 |
| 0x2000000 | died burning; drawn darker | Observed | set 0x111510, test 0x10b178 |
| 0x4000000 | prediction copy is catching up | (OVERVIEW) | 0x132bfc |
| 0x8000000 | during `Creature_settle`: restore the old position if an object is touched | Observed | 0x119e78, 0x114230 |
| 0x10000000 | auto-prop state bit read by script `autoPropSetState`/`autoPropGetState` | Observed | 0x14237c |
| 0x20000000 | projectiles ignore this object | Observed | 0x150d28; set 0x28f274 |

Caution: `tools/flagxref.py` also reports hits for the 64-bit Creature flag word at +0xa8
when a load from +0xc happens to be nearby (for example `followPlayer`, `followPath`,
`friendly` write +0xa8). Check the decompile before trusting a hit.

## Handle lists (recap, with the node layout)

**Observed** in `handle_link` 0x1a1738 (player area). A link is two pool nodes taken from
the free list 0x864ea8:

```
node A (in the list):      next, prevSlot, partner = B, object
node B (in the object):    next, prevSlot, partner = A, 0
```

A is pushed at the head of the list, B at the head of one of the object's three heads.
`handle_clear(head)` removes every node on a list together with its partner, which is why
destroying an object (three `handle_clear` calls) empties every handle to it, and why
emptying a list frees the objects' back nodes. An iterator is itself a node spliced into the
list (object field 0), so the list may change under it. Lists are LIFO: the most recently
linked object comes first, and `obj_updateGridCell` relinks at the head even when the cell
has not changed, so the order of a cell's list follows the order of movement calls.

## The world

### Grids

| Global | What |
|---|---|
| `g_grid` 0x5db4f0 | 120 × 120 handle-list heads; cell index `((int)coord + 0x3c00) >> 8` on each axis, row = y |
| `g_gridB` 0x5e95f0 | the same shape for objects with flag 0x800 |
| `g_offGridList` 0x5f76f0 | objects outside the grid, hidden objects, new flag-2 objects |
| `g_alwaysDrawList` 0x5db4e8 | drawn every frame after the frustum walk |

`world_collectObjectsInBox` (0x14a928) searches **only `g_grid`**, pads the cell range by
96 units, skips objects whose flags match `g_excludeMask` and always skips 0x20000, tests
x/y against the object radius and height against +0x20, and writes at most `max − 1`
pointers plus a null. Result order is cell order, then list order. **Observed.**

Grid B holds launched props (debris, gibs, loose ice, items while they fly): the Prop
constructors and `Prop_launch` set 0x1809. Such objects are invisible to every box query
and therefore to collision, targeting and area damage. **Observed** 0x1539fc, 0x1541a0.

`world_drawObjects` (0x14b168, draw task priority 21) is described in FINDINGS D13. Two
additions, **Observed**: the per-object box uses the bytes at +0x28/+0x29, not the collision
radius; and the always-draw list is drawn last with the clip flag 0x41c148 forced on.

### Run lists and how an object moves between them

Three kinds of list, all linked through the object's +4 head:

| List | Run when | Put there by |
|---|---|---|
| `g_runListActive` 0x5db3a8 | every frame | `obj_runEveryFrame` 0x14f248 (155 callers), `obj_updateActive` when it turns active |
| `g_runLists15` 0x5db3b0 [15] | list `frame % 15` | `obj_runEvery15` 0x14f330 (7 callers) |
| `g_runLists60` 0x5db3f0 [60] | list `frame % 60` | `obj_runEvery60` 0x14f2b8 (76 callers), `obj_updateActive` when it turns inactive |

The slow lists are filled round-robin (cursors 0x403a00 and 0x4039fc) so the load is spread.
`obj_stopRunning` 0x14f290 removes the link. An object is on at most one list because every
setter unlinks first. **Observed.**

`obj_updateActive(obj, wasActive, radius)` 0x14db08 computes "is within `radius` of an
activity centre" (players, or the camera focus when `g_cullByCamera` — FINDINGS D6) and
relinks only when the answer differs from `wasActive`. Flag 0x80000 replaces the radius by
44000. The callers keep `wasActive` themselves (creatures keep it in a flag bit).

`runObjects` (0x14b910, run task priority 10), in order — **Observed**:

1. Destroy every object on `g_deleteList` (slot 1 with argument 3).
2. Every 64th frame refresh `g_poolFreeCount` = `pool_countFree()`.
3. If that count is below 300: visit 16 cells of **grid B** (a cursor derived from the frame
   counter), and in each destroy the first object with flag 0x1000. Offline, while the count
   is still ≥ 200, objects within 480 units of the camera focus are spared; in a net game
   that test is skipped (0x14ba80).
4. If `game_isFrozen()` is false: call slot 4 of every object on the active list, then on
   list `frame % 15`, then on list `frame % 60`, skipping flag 0x8000. All three walks use
   `g_excludeMask`.

### Deleting

`obj_delete` 0x14f200 (50 callers) removes the object from its run list and links it to
`g_deleteList` through head +0; it is destroyed in step 1 of the next `runObjects`, or by
`world_flushDeleteList` 0x14f3a8 / `world_loadRecords`. Code also destroys objects directly
through slot 1 (script `deleteMonster`, `reapEnemies`, the pool reaper).
`world_deleteAllObjects` 0x14c460 empties everything at level unload.

### Level-object records (level load and saved level state)

One format serves both the object list in a level file and the per-level saved state.
**Observed** in `world_loadRecords` 0x14e808 and `obj_writeRecord` 0x14df50.

```
blob header:  s16 count, u16 flags (1 = records carry saved state, 2 = already relocated),
              s32 offset of the string table
record:       s32 className (string-table offset)
              s16 record size, s16 facing angle
              float x, y, height
              s32 property string offsets…, 0
              (aligned to 8) state bytes written by slot 9 when header flag 1
```

Loading calls `g_objectFactory(className, &pos, angle, props)`, stores the class name at
+0x34 and, for saved blobs, calls slot 8. `world_writeRecords` 0x14e140 walks grid A, grid
B and the off-grid list, skipping flag 0x4000 and anything `g_saveFilter` accepts; if the
52000-byte record area or the 5000-byte string area would overflow, `world_saveState`
0x14e5c8 retries with a rising *thinning* level that drops a growing share of flag
0x1000/0x2000 objects. The save filter (`world_saveFilter` 0x15d9c8) is a list of class
names (lights, fires, `Line`, `Blocker`, …) that are instead re-created from the level
file: `world_loadRecords(levelBlob, 1)` creates only those.

## The allocator

### Object pool

**Observed** in `pool_init` 0x14fcd8, `pool_new` 0x14fdb8, `pool_free` 0x150470.

| Class | Block | Count | Typical users |
|---|---|---|---|
| 0 | 0x180 bytes | 512 | small objects, `Prop` (0x148) |
| 1 | 0x500 bytes | 512 | creatures (0x3c8–0x4f8), `PhProp` (0x248), `GutChunk` (0x268), `ItemProp` |
| 2 | 3000 bytes | 32 | `Player` (0x590), `WaveMaker`, the largest bosses |

The table is `g_poolClasses` 0x403a10 (`{size, count, base, freeHead}` × 3, then a
terminator of size 0x7fffffff); the memory is 0xe7700 bytes at 0x5f88c0. `pool_new(size)`
takes the first class that is big enough **and has a free block** (a full class spills into
the next larger one), zero-fills the block, and returns it. If nothing is free it prints the
heap and **returns 0**; nearly every caller tests for that and silently skips creating the
object. `pool_free` finds the class from the address. `pool_countFree` 0x150410 walks all
three free lists.

### Tagged heap

`mem_allocTagged(size, tag)` 0x14ff88, `mem_free` 0x150198, `mem_realloc` 0x14fe80: a
first-fit heap of blocks with a 0x1c-byte header `{u16 0xabcd, u16 used, s32 size, tag,
next, prev, groupMask, caller}`; the pointer returned for large requests is aligned to 256
bytes. `mem_freeGroup(bit)` 0x150510 frees every block allocated while a group bit was set
(level unload). The `mem_*` wrappers at 0x150680–0x1507a8 fall back to the C library until
`g_heapReady` is set. Not used for game objects.

## Movement helpers

| Address | Name | Notes |
|---|---|---|
| 0x14d238 | `world_slideMove` | terrain-only sweep and slide |
| 0x14d4b8 | `obj_moveWithCollision` | reached through `creature_moveSimple` 0x1186d8; the prediction copy does not call slot 6 of the objects it touches (test of 0x20000 at 0x14d9ac), though its own slot 6 runs |
| 0x1509f8 | `obj_moveAndCollide` | projectile step: terrain, a water splash that consumes one `GameObject_rand`, then slot 6 on both sides for overlapping objects that are not 0x201, not 0x20000000 and not the owner |
| 0x14acf8 | `world_findFreeSpot` | rejection-samples points with the **shared** seed (three draws per try, up to 50 tries) |

## Props

`Prop` (0x148 bytes) is a model part with a matrix; `PhProp` (0x248) adds a rigid body;
`ItemProp`/item `PhProp` carry an item record and are interactable.

| Offset (Prop) | Meaning | Evidence |
|---|---|---|
| +0x4c, +0x50 | model and texture resources | `Prop_ctorNamed` 0x153ac0 |
| +0x54, +0x64, +0xa4 | lump, model and texture names | same |
| +0xe8 | 64-bit mask of model parts | same |
| +0xf0 | centre offset from the model bounds | `Prop_ctorNamedLaunch` 0x153e54 |
| +0xfc, +0x100 | horizontal velocity | `Prop_launch` |
| +0x10c, +0x10e | s16 timers (lifetime 180 frames unless told otherwise) | `Prop_launch` |
| +0x110 | 48-byte matrix | |
| +0x140 | u16 prop flags: 1 at rest, 2 runs every frame, 4 expendable | `Prop_ctorNamed` |
| PhProp +0x148 | 72-byte item record (when +0x238 is set) | `PhProp_ctor` |
| PhProp +0x190… | rigid body, position, orientation, linear (+0x1bc) and angular (+0x1c8) velocity | `PhProp_initPhysics` |
| PhProp +0x240 | scale | |
| GutChunk +0x248 | chunk flags; bit 0 = "disappear at first landing" | 0x2019e0 (gameplay area) |

`Prop_launch` 0x1541a0 picks velocities with the object's own generator. Launched props are
flag 0x1809, so they are dead, non-solid, in grid B and reapable.

## The object factory

`world_objectFactory` 0x159c94 (15.6 KB) is installed in `g_objectFactory` by
`objects_registerFactory` 0x15da54. It is a chain of tests in the order below; the first
match wins, each match is `pool_new(size)` followed by one constructor call (a failed
`pool_new` returns no object). `==` is a case-insensitive full match, `prefix` a
case-insensitive prefix match (`str_prefixDiffers` 0x159c20), `prop` means "the property
list contains this key". **Observed** by parsing every test and the block it branches to.

| Test | Size | Constructor | | Test | Size | Constructor |
|---|---|---|---|---|---|---|
| == charAmbient_Light | 0x4c | 0x158bcc | | == Nightmare | 0x3d8 | 0x270968 |
| == charDirectional_Light | 0x4c | 0x158c6c | | prefix Orc2 | 0x488 | 0x2a0954 |
| == charDirectional_LightD | 0x4c | 0x158d0c | | prefix Orc | 0x488 | 0x2a0954 (after a call to 0x217edc) |
| == clearColor | — | writes 0x506044 | | == RedDragon | 0x418 | 0x25f470 |
| == customVars | — | calls 0x22e714 | | == RiderDisease/War/Pestilence/Death | 0x478 | 0x271c70 |
| == AntMaker | 0x3e8 | 0x2657a0 | | == Rondo | 0x3d0 | 0x29f10c |
| == AntTrapa | 0x1a0 | 0x24290c | | == Scorpion | 0x3d0 | 0x2a4d68 |
| == Antlighta/b/c | 0x448 | 0x2416c4 | | == SeaMonster | 0x3d0 | 0x2a428c |
| == Orca | 0x448 | 0x2547fc | | == WatSkel | 0x478 | 0x2a5af4 |
| == Trap | 0x50 | 0x294fa4 | | prefix Skeleton (then red / blue / other) | 0x478 | 0x2a5af4 (variant 2 / 3 / 0) |
| == LightningRod | 0x5c | 0x2958a8 | | == Skelight | 0x468 | 0x2a8770 |
| == EggSac | 0x448 | 0x242bd8 | | == SnowBeast, SnowBoss | 0x3d8 | 0x287998 |
| == GothTrap | 0x1a0 | 0x243088 | | == SmallSpider | 0x3c8 | 0x2ab450 |
| == HateHole | 0x1a0 | 0x24323c | | == Soul | 0x3e0 | 0x2a9478 |
| == HateBrdg | 0x1a0 | 0x243398 | | == SpiderQueen | 0x430 | 0x2ad1c0 |
| == Arenadoor | 0x198 | 0x243594 | | prefix Tormentor | 0x3d8 | 0x287998 |
| == apprings | 0x498 | 0x24388c | | prefix Ulthork | 0x468 | 0x2b5538 |
| == dragongoldpile | 0x64 | 0x295cf4 | | == UndeadKnight1…4 | 0x478 | 0x271c70 |
| == SpiritAnchorAct/Exp | 0x98 | 0x295ff4 | | == UndeadKnight | 0x478 | 0x2b3e30 |
| == disportGOOD/EVIL | 0x448 | 0x243cd0 | | == Vampire | 0x3c8 | 0x2b69d0 |
| == ptbridge | 0x198 | 0x243e3c | | == VampireLord | 0x480 | 0x2b76e4 |
| == Player1 | 0x4c | 0x158928 | | == Samurai, prefix Gladiator | 0x480 | 0x2bafb4 |
| == ArenaPlayerStart/Alternate | — | calls 0x30503c | | prefix WarBoar | 0x3d8 | 0x2ba03c |
| == AvatarAgony | 0x3d0 | 0x23396c | | prefix WoodElf, evilwoodelf | 0x3e8 | 0x2bc820 |
| == AntQueen | 0x3e8 | 0x236c70 | | == WarWraith | 0x468 | 0x2c07a8 |
| == AntTough, AntBlocker, prefix Ant | 0x3e8 | 0x235418 | | == Wraith | 0x3d8 | 0x2bf2ac |
| == Amphian | 0x3c8 | 0x234584 | | == raloszek | 0x480 | 0x2c1f94 |
| == Arenabeast | 0x3d8 | 0x238bb8 | | == WebTrap | 0xa0 | 0x2b04f8 |
| == SnoBadge, prefix Badger | 0x3d0 | 0x244018 | | == Torch, Fire, Campfire, Firepot, Firepot2, OilLamp | 0x8c | 0x2b1e80 |
| == castbadger | 0x3d0 | 0x244e4c | | == Candle, Candle2 | 0x94 | 0x2b2c70 |
| prefix BlackWidow, == Drachnid | 0x420 | 0x2ab958 | | == Candle3 | 0x50 | 0x2b30ec |
| prefix Bubonian | 0x470 | 0x247fb0 | | == Lantern | 0x98 | 0x2b33f4 |
| == cazicthule, cazicavatar | 0x3e8 | 0x24a670 | | == WaterSpout | 0x5c | 0x201fa8 |
| == cdeyeball | 0x3d0 | 0x28f5dc | | == MissileTrap | 0x50 | 0x202318 |
| prefix Clockwork | 0x500 | 0x24e124 | | == fireballShooter, arrowShooter, Shooter | 0x58 | 0x2023f8 |
| prefix CloudGiant | 0x538 | 0x2500b0 | | == UserParamProp | 0x170 | 0x15711c |
| == Creep | 0x500 | 0x253148 | | == SackSpill | 0x60 | 0x158600 |
| == CyclopsNew, CyclopsGrey, Cyclops | 0x458 | 0x2566d4 | | prefix Chest, == Chest2/3, ChestCav, IceChestLarge | 0x88 | 0x292030 |
| == FatCyclops | 0x468 | 0x257de8 | | prefix Barrel, prefix PowderKeg, the crate, pot, jar, Basket and MumTable names | 0x84 | 0x290c24 |
| prefix Demon | 0x468 | 0x25dc6c | | == Ice | 0x68 | 0x2028c8 |
| == droid | 0x3d0 | 0x27b840 | | == Trigger | 0x70 | 0x1ecdf4 |
| == EarthElemental, lb_block, LavaMonster | 0x430 | 0x28048c | | == TriggerParams | 0x50 | 0x1ecd64 |
| prefix FemaleDarkElf | 0x478 | 0x25947c | | == PushTrigger | 0x4c | 0x1ec900 |
| == BBeetle, LBeetle, prefix FireBeetle | 0x430 | 0x24587c | | == MonsterTrigger | 0x54 | 0x1ed288 |
| == FireFly | 0x470 | 0x24726c | | == Prop | 0x148 | 0x1539fc |
| prefix Froglock | 0x468 | 0x263e1c | | == ItemPhProp | 0x248 | 0x155dac |
| prefix Ghoul, GhulBlue | 0x3d8 | 0x266088 | | == ItemProp | 0x190 | 0x159458 |
| == Gnaw | 0x3c8 | 0x26741c | | == DoorSwing / DoorSecret / RollDoor | 0x5c | 0x28a960 / 0x28b0a8 / 0x28dd94 |
| == GnawSpawner | 0x3e0 | 0x267cf4 | | == Switch / FloorSwitch | 0x50 / 0x58 | 0x28a850 / 0x28b4e0 |
| == GnomeNavigator | 0x3c8 | 0x269eb8 | | == SavePoint | 0x118 | 0x28cb90 |
| prefix Gnome | 0x3d8 | 0x268fd4 | | == PortalHurt, Portal | 0x164 | 0x27c694 |
| prefix fgoblin, Goblin | 0x498 | 0x26a624 | | == PokeReflector | 0x4c | 0x28e1e4 |
| == Gremlin | 0x460 | 0x26e08c | | == Flag | 0x98 | 0x1580e8 |
| prefix Hag | 0x3d8 | 0x26f120 | | == Lever | 0x54 | 0x28e394 |
| == Innoruuk | 0x4d0 | 0x2735dc | | == WeaponRack | 0x98 | 0x28e87c |
| == IronGuardian | 0x3e8 | 0x27a00c | | == MetalCrateLrg/Sml | 0x118 | 0x15dddc |
| prefix Kobold | 0x3d0 | 0x27f0c0 | | == PushPhysicsProp | 0x118 | 0x15dd5c |
| prefix MaleDarkElf | 0x4f8 | 0x25afd8 | | == Counter / Timer | 0x50 / 0x54 | 0x28ed14 / 0x28ec1c |
| == MattMarr | 0x4a8 | 0x2835a0 | | == Lamp | 0x8c | 0x2b3718 |
| == Mermaid | 0x3c8 | 0x285b30 | | prefix Gold | 0xc0 | 0x157754 |
| == Minion | 0x3e8 | 0x285f10 | | == Container | 0x84 | 0x2909b0 |
| prefix Minotaur | 0x470 | 0x288fdc | | == CosmeticProp / CosmeticPropAnim | 0x60 / 0x98 | 0x15858c / 0x15806c |
| prefix Mosquito | 0x3c8 | 0x297788 | | == NPC | 0x480 | 0x29df04 |
| == MummyKing | 0x4a0 | 0x29afb4 | | == Teleporter | 0x3c8 | 0x28ee80 |
| prefix Mummy | 0x480 | 0x298418 | | == Blocker | 0x4c | 0x28f15c |
| == Natasla | 0x3c8 | 0x29d70c | | == Line | — | 0x20f844; a line named `wave` also makes a WaveMaker (0x768, 0x15ecf8) |
| == Ogre | 0x468 | 0x29fad0 | | == Boat / skulboat | 0x938 | 0x2f9f04 / 0x2fa3f4 |

Remaining named classes: `kelethinBomb` (0x58, 0x261dbc), `smokeBomb` (0x4ac, 0x2c54f8),
`catapult` (0xfc, 0x24d440), `weather` (0x2a0, 0x1d7778), `ScriptGenerator` (0x4c,
0x265f54), `HateGate` (0x1b8, 0x242e7c), `HateInto` (0x1b8, 0x242c5c).

When no name matches, properties decide: `CreatureContainer` (0x3d0, 0x243624),
`AutoContainer` (0x150 via 0x24259c, or 0x148 via 0x23d93c, chosen by 0x23a2b4),
`AutoChest` (0x100 via 0x241468, or 0xf8 via 0x23ad18), `AutoProp` (0x448 via 0x2416c4, or
the AutoDoor constructor), `AutoEmitter` (0x60, 0x240dc8), `AutoDoor`/`AutoSwitch` (0x198,
0x23c44c), `Critter` (0x448, 0x2547fc), `Generator` (0x3e8, 0x2657a0), `SmokeGen` (0x490,
0x31d180). Otherwise the factory returns 0.

The four horsemen entries pass a variant index to one constructor (FINDINGS D3). The clone
function of each class is listed in `docs/creatures.md` (the clone functions sit in the
creatures range).

## Per-machine state

Places in this area where code that changes shared state reads something that can differ
between machines, or where shared state is changed from draw code or without a test for
the prediction copy.

| # | What | Kind | Addresses |
|---|---|---|---|
| O1 | **Pool occupancy feeds the simulation.** `runObjects` samples `pool_countFree()` every 64th frame and below 300 destroys flag-0x1000 objects in grid B; `pool_new` returns 0 when no block is free and callers then skip the object, including the `g_randSeed` draw in `GameObject_ctor`. Pool occupancy is not shared state: it counts every block, including the prediction copy (a 3000-byte block per machine, re-made on its own schedule — FINDINGS G1) and objects whose lifetime depends on a local option (O2). Two machines can therefore cross the 300 threshold on different samples, and can disagree on whether a `pool_new` succeeds when a class is exhausted | Observed mechanism; that occupancy actually diverges is Inferred | sample 0x14b9b0–0x14b9cc, reaper 0x14b9cc–0x14bb18, `pool_new` failure path 0x14fe28–0x14fe34 |
| O2 | **A local display option changes how long gib objects live.** The `GutChunk` constructors (gameplay area) copy "option 0x44fdc0 < 2" into bit 0 of the object's +0x248, and `GutChunk` run destroys the object at its first landing when that bit is set; otherwise it lives for further bounces. 0x44fdc0 is an options-menu value (reset to 0 by the options default routine 0x1e6238, loaded from the saved configuration at 0x222d5c); other areas call it `g_decalDetail`. Gibs are grid-B objects, so box queries never see them; the effect on shared state is through O1 | Observed (constructors 0x2019e0, 0x201a80, 0x201b3c; run 0x1edb18 tests the bit at 0x1eddf4 and destroys itself at 0x1ede18); whether a net game forces the option equal on all machines is Unknown | creators in this project: `Creature_processDamage` 0x110d30 |
| O3 | The camera test in the pool reaper is skipped in net games — deliberately safe | Observed | 0x14ba80–0x14ba8c |
| O4 | `obj_updateActive` uses the camera focus when `g_cullByCamera` is set (FINDINGS D6). Everything that keys on activity inherits it: which run list an object is on, and for creatures whether AI runs at all | Observed | 0x14db28 onward |
| O5 | `world_drawObjects` calls slot 5 of a per-machine set of objects (FINDINGS D13). Draw functions in this area were not audited individually; `Creature_draw` is covered in `docs/creatures.md` | Observed / not audited | 0x14b4f8–0x14b8b0 |
| O6 | Box queries, run walks and grid walks honour `g_excludeMask`; `Creature_pickTarget` temporarily overwrites the mask with 8 around its query (0x20000 is still skipped by the hard-coded test). Harmless while simulating; it would expose the hidden real player if ever reached during prediction | Observed; reachability Inferred none | 0x10e004–0x10e050 |
| O7 | `obj_moveWithCollision` suppresses the other object's slot 6 for the prediction copy, but still calls the copy's own slot 6 and still pushes the copy; `Creature_moveBy` has no such test (it is not used for players' own movement as far as read) | Observed | 0x14d9ac, 0x114208 |
| O8 | Pointer values: object addresses are used only as identities (name hash values, handle targets, `pool_free` class lookup). No ordering or hashing by address was found in this area | Observed for the functions read | 0x14bce0, 0x150470 |

Not hazards, but easy to mistake for one: `world_findFreeSpot` and `Player1_ctor` draw
`g_randSeed` directly; both run from simulation code.

## Open questions

- Does a net launch copy one machine's options to the others, or otherwise pin 0x44fdc0?
  Writers are 0x1e62f8, 0x1e65e8, 0x1e6ea8, 0x222d5c; 0x1e6428 saves the option block and is
  called from game setup 0x1e16a0. Settles O2.
- How close do real scenes get to 300 free pool blocks, and can class 1 (512 blocks of
  0x500) be exhausted in a four-player fight? A memory snapshot of `g_poolClasses` answers it.
- Flags 0x4, 0x10000, 0x40000: meanings. (0x400000 and 0x800000 were listed here; they are
  the menu-state bits, see the flag table.)
- The lighting code (0x147a84–0x14a480) was only skimmed; names there are by shape.
- `MissileWeapon` (0x150ee4–0x153314), `AnimatedMissile`, `Gold`, `ItemProp`,
  `UserParamProp`, `CosmeticProp*`, `PushPhysicsProp` (0x15dac0–0x15e244) and `WaveMaker`
  (0x15ecf8–0x16…): virtual functions are named from the tables, bodies were not read.
  Their draw functions have not been checked for writes to shared state.
- Which objects, besides props, ever carry flag 0x1000 while in grid B. Only the Prop
  constructors, `Prop_launch`, `Prop_loadState` and 0x18c4e4 were seen setting or testing it.
- `world_collectInSphere` third argument and the exact meaning of mask 0xd.
