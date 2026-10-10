# The object system: what exists, in which order it runs, how objects find each other

For someone rebuilding the simulation. Online play is deterministic lockstep, and the
order in which objects are created, run and returned by queries is the order in which the
shared seed is drawn: a rebuild that runs the same objects in a different order is out of
step on the first frame. This document gives that order.

Sources and status. Everything was read from the instructions at the addresses given
(**Observed**) and then run: `tools/ref_objects.py` is this document as code, and
`tools/difftest_objects.py` executes the original functions under `tools/ee_emu.py` (an
instruction interpreter, not a console) on long random scenarios and compares them with
the model after every step. "Executed" below means that comparison passed; section 9 says
exactly what it covers. Nothing here was run on a console or in PCSX2. The pool, the
handle lists and the list iterator are specified in `docs/spec/core.md` sections 11 and 12
and are only used here. `docs/objects.md` is the area document (fields, flags, the
factory table); where it and this document differ, section 10 says which was executed.

Addresses are those of SLUS_209.73. Floats are compared with the console's rules
(`docs/spec/core.md` section 2): the comparisons below are written exactly as the code
orders them, and `(int)x` means the conversion instruction, which truncates toward zero
and saturates.

## 1. The lists

Every list is a handle list (`docs/spec/core.md` section 12). Two rules decide all
ordering in this document:

- **a link goes to the front** (`handle_link` pushes at the head), and
- **walks go front to back**, with an iterator that stands behind the node it is on.

| Global | What | Linked through object head |
|---|---|---|
| `g_runListActive` 0x5db3a8 | objects run every tick | +4 |
| `g_runLists15` 0x5db3b0, 15 heads | objects run when `frame % 15` is the list number | +4 |
| `g_runLists60` 0x5db3f0, 60 heads | objects run when `frame % 60` is the list number | +4 |
| `g_deleteList` 0x5db4e0 | objects waiting to be destroyed | +0 |
| `g_alwaysDrawList` 0x5db4e8 | drawn every frame after the frustum walk | +0 |
| `g_grid` 0x5db4f0 | grid A: 120 rows × 120 columns of list heads, `[row = y][column = x]` | +8 |
| `g_gridB` 0x5e95f0 | grid B, same shape, for objects with flag 0x800 | +8 |
| `g_offGridList` 0x5f76f0 | objects whose position is outside the grid, and hidden objects | +8 |

Each object has three heads of its own: +0 ("who refers to me": every handle that points
at the object, and its back link when it is on the delete list or the always-draw list),
+4 (its run-list link, at most one) and +8 (its grid link, exactly one from construction
to destruction). Scalars: `g_runList60Cursor` 0x4039fc, `g_runList15Cursor` 0x403a00,
`g_poolFreeCount` 0x403a04 (100000 in the executable), `g_excludeMask` 0x4039b8,
`g_simFrame` 0x44fdcc, `g_randSeed` 0x404464.

## 2. Creation

### 2.1 Who creates

Every creator does `pool_new(size)` and, **only if that returned a block**, calls the
class constructor on it. A refused allocation creates nothing and draws nothing from the
shared seed (executed: the seed is unchanged). `pool_new` zero-fills the block; that
matters in step 4 below.

### 2.2 `GameObject_ctor` 0x14cb10 (this, pos, classDef, props) — field by field

Every class constructor calls this first. In the order of its stores and calls:

| Step | Addresses | What |
|---|---|---|
| 1 | 0x14cb7c–0x14cbc0 | heads +0, +4, +8 = 0; vtable +0x48 = `GameObject`'s (0x5122a8); radius +0x1c = 24.0; height extent +0x20 = 72.0; flags +0xc = 0; draw bytes +0x28 = 25, +0x29 = 73; position +0x10..+0x18 = pos; +0x34 = 0; class definition +0x24 = classDef |
| 2 | 0x14cbc4–0x14cc20 | if classDef is not null and its generation word (+4) differs from `g_lumpGeneration` 0x41bf78: for every (name, resolved) pair from +8 up to a null name, `resolved = res_find(classDef.lump, name)`; then the generation word takes the current value. A definition is therefore resolved once per level generation, by the first object that uses it |
| 3 | 0x14cc24–0x14cce0 | the grid link, `handle_link(list, this + 8, this)` — at the **front** of the list. The code tests flags 0x2 and 0x800 here, but it zeroed the flags in step 1, so the list is always the grid-A cell of the position, or the off-grid list when a cell coordinate is outside 0..119 (section 4.1). The grid-B branch 0x14cc84 is unreachable and was never entered in any run |
| 4 | 0x14cce4–0x14cd48 | `obj_getPropInt(this, "hide", 0)`; if non-zero the grid node moves to the front of the off-grid list. **This reads the property list through +0x2c before step 5 stores it.** For a block fresh from `pool_new` that word is 0, the lookup returns 0 and nothing happens (executed, with a `hide=1` list). Only a block that was not zeroed and still held a list pointer takes this branch (executed with a planted pointer). Hiding at load is done by the derived constructors instead: `Creature_ctor` has its own `hide` test at 0x109f10–0x109f3c (off-grid, flag 0x8000, bit 3 of +0x231) |
| 5 | 0x14cd64 | property list +0x2c = props |
| 6 | 0x14cd5c–0x14cd80 | **one draw from the shared seed**: `g_randSeed = g_randSeed * 0x19660d + 0x3c6ef35f`; the object's own generator state +0x44 = the new seed `>> 16` (a 16-bit number) |
| 7 | 0x14cd84–0x14cf58 | for n = 0, 1, …: the n-th property that starts with `name=` (list order) is registered with `objNames_add(value, this)` (section 4.5). A value in double quotes is unquoted **in place** in the property string |

Not written by this constructor, so zero from the pool: +0x30 (vertical speed), +0x38
(facing), +0x3c, +0x40.

After the base constructor the object is in exactly one grid list and **on no run list**.
The derived constructor decides what else happens, in this order of effect:

- it may set flags and call `obj_updateGridCell` (that is how a flag-0x800 object reaches
  grid B: the `Prop` family sets 0x1809, `docs/objects.md`);
- it links the object to a run list by calling one of `obj_runEveryFrame` 0x14f248 (155
  call sites), `obj_runEvery60` 0x14f2b8 (76) or `obj_runEvery15` 0x14f330 (7: triggers,
  shooters, floor switches among them) — or none (the `Player1` marker, for one). Each of
  these goes to the front of its list (section 5.1);
- any further constructor of the chain draws whatever it draws after the base draw.

### 2.3 When a new object first runs

From the two rules of section 1 (all executed against `runObjects`):

| The object is linked … | … to | It first runs |
|---|---|---|
| outside `runObjects` (level load, a script task, a message handler) | any list | in the next `runObjects` that walks its list, **before** every object linked to that list earlier |
| during the every-frame walk | the every-frame list | next tick, first in the list |
| during the every-frame walk | a slow list | **in the same tick** if the cursor it was given equals `frame % 15` (or `frame % 60`), because the slow lists are walked afterwards; otherwise when that list next comes round |
| during the 15-list walk | the 60-list of this frame | in the same tick |
| during a slow-list walk | the every-frame list | next tick |
| during a walk | the list being walked | not in that walk (it is in front of the iterator) |

`docs/spec/skills-35-68.md` section 1.4 states the every-frame rows; the slow-list rows
are new and matter for any class that uses `obj_runEvery60` in its constructor (most
level objects and monsters).

## 3. Deletion

### 3.1 Two ways

- **Deferred**: `obj_delete` 0x14f200 (50 call sites). It removes the run-list link (the
  object stops running at once) and links the object to the **front** of `g_deleteList`
  through head +0. Nothing else changes: the object keeps its grid link, so box queries
  still return it, handles to it stay valid, and the name table still finds it, until it
  is destroyed. Calling it twice puts the object on the list twice; it is still destroyed
  once (the first destruction clears both links).
- **Direct**: a virtual call of slot 1 with argument 3 (destroy and free). Used by the
  delete-list flush, the reaper, level teardown, and by game code that cannot wait.

### 3.2 The destructor chain

Slot 1 is the most-derived destructor (this, flags). The shape, read in `Player1_dtor`
0x3c2a00 and `Projectile_dtor` 0x3c2940 (the base destructor has 131 call sites, not all
read): store the class's own vtable, do the class's own clean-up (`Projectile` clears its
owner handle at +0x4c), call the base destructor with flags 0, and at the end, if bit 0
of the caller's flags is set, `pool_free(this)`. So the block is freed by the outermost
destructor, after the whole chain. The chain ends in:

`GameObject_dtor` 0x14cf90 (this, flags), in this order:

1. vtable = `GameObject`'s;
2. for n = 0, 1, …: `objNames_remove(value of the n-th name= property, this)`;
3. `handle_clear(this + 8)` — leaves the grid list;
4. `handle_clear(this + 4)` — leaves its run list;
5. `handle_clear(this + 0)` — every handle that pointed at the object now reads null, and
   the object leaves the delete list and the always-draw list;
6. if `flags & 1`: `pool_free(this)` (the base class frees only when it is itself the
   outermost destructor).

Once freed, the block is the head of its class's free list, so the **next** `pool_new`
of that size class gets this address (executed).

The order of 3–5 decides the order in which handle nodes return to the node pool and so
which node addresses later links get; a rebuild that wants identical addresses must keep
it.

### 3.3 What an iterator in progress sees

The run walks, the delete-list flush, the two `forEach` walkers and teardown all use the
list iterator, so (each case executed inside `runObjects`, with virtual runs and
destructors that create, delete and destroy):

- the current object may destroy itself, or be destroyed by something it called: the walk
  continues with the node that followed it;
- an object destroyed or unlinked before the walk reaches it is not visited;
- an object `obj_delete`d from inside a destructor **during the flush** lands in front of
  the iterator: it is not destroyed by this flush and lives one more tick (off every run
  list, still in the grid);
- the box query and the reaper walk cell lists directly (no iterator). The box query skips
  an iterator node it meets (its object pointer is null); it never runs code while it
  walks, so nothing can change under it.

## 4. The grids and the queries

### 4.1 Cell indexing

```
cell(c) = ((int)c + 0x3c00) >> 8          # 256 units per cell; 32-bit add, arithmetic shift
column  = cell(x)     row = cell(y)       # list index = row * 120 + column
```

The grid covers integer coordinates −15360 … 15359. Because the conversion truncates
toward zero, cell 60 takes every coordinate in (−1, 256) and cell 59 takes (−257, −1]:
the cell boundary at zero is at −1, not 0, on both axes (executed with coordinates −0.5,
−0.99, −1.0). An object whose column or row is outside 0..119 is in `g_offGridList`.

### 4.2 Moving between cells

- `obj_updateGridCell` 0x14f028 **must follow every position change** (64 call sites). It
  unlinks the grid node and pushes it at the **front** of the list for the current
  position — also when that is the list it was already in. Grid B if flag 0x800 is set at
  that moment, else grid A, else the off-grid list. It does not look at flag 0x2, and it
  brings an object that was moved off the grid back onto it.

  Consequence: **the order inside a cell is the reverse order of the most recent movement
  (or creation) calls of the objects in it**, not creation order. Every caller that rolls
  per query result inherits that.
- `obj_moveOffGrid` 0x14ef48: grid node to the front of the off-grid list (script
  `hideMonster`, the constructors' `hide`). `obj_isOffGrid` 0x14efa0 walks that list.
- `obj_linkToGrid` 0x14f120: a first link for an object that has none; flag 0x2 or an
  outside position selects the off-grid list. Its one caller is `net_frameLoop` 0x13b58c,
  for the prediction copy after the clone.
- Setting or clearing flag 0x800 does not move the object; it moves at its next
  `obj_updateGridCell`.

### 4.3 `world_collectObjectsInBox` 0x14a928 (min, max, out, limit)

The query nearly everything uses (95 call sites). Result order is draw order for every
caller that rolls per result.

```
rowLo = max(((int)min.y + 0x3ba0) >> 8, 0)      rowHi = min(((int)max.y + 0x3c60) >> 8, 119)
colLo = max(((int)min.x + 0x3ba0) >> 8, 0)      colHi = min(((int)max.x + 0x3c60) >> 8, 119)
n = 0
for row = rowLo .. rowHi:                       # ascending y
    for col = colLo .. colHi:                   # ascending x
        for node in g_grid[row][col], front to back:
            o = node.object;  skip if null
            skip if o.flags & g_excludeMask     # the global is read again for every object
            skip if o.flags & 0x20000           # the prediction copy, whatever the mask
            skip if o.x + o.radius < min.x  or  max.x < o.x - o.radius
            skip if o.y + o.radius < min.y  or  max.y < o.y - o.radius
            skip if max.z < o.z             or  o.z + o.height < min.z
            if n >= limit - 1: goto done        # the walk ENDS here
            out[n++] = o
done: out[n] = 0;  return &out[n]
```

- **Grid A only.** Objects in grid B (launched props, gibs, flying items) and on the
  off-grid list (hidden, out of bounds) are never returned.
- The cell range is the box grown by 96 units (0x3c00 − 0x3ba0). An object is found only
  if its **centre's cell** is in that range, so an object with a radius above 96 can
  overlap the box and be missed.
- Height is one-sided: the object occupies z … z + height (+0x20), not ±.
- **At most `limit − 1` results, and they are the first in walk order** (lowest row, then
  lowest column, then most recently moved), not the nearest. A caller with a small buffer
  in a crowd sees a subset decided by position on the map and by who moved last.
- The additions wrap in 32 bits: a box whose max converts to more than 0x7fffc39f gets a
  negative high cell and returns nothing (executed with 1e12).
- `limit` 0 or 1 returns nothing.

### 4.4 `world_collectInSphere` 0x14ab80 (f12 radius, a0 centre, a2 list)

Box query of centre ± radius on all three axes with limit 0x200 (511 objects). Every
result without flags 0x1, 0x4, 0x8 whose distance `sqrt((dx·dx + dy·dy) + dz·dz)` is
below `radius + o.radius` gets a node at the **front** of the caller's handle list. The
list therefore ends up in the **reverse** of box-query order. Register a1 is not read.

### 4.5 By name: `objNames_add` 0x14bce0, `objNames_remove` 0x14be58, `world_findObjectsByName` 0x14bf58

This is how scripts find objects. A 512-slot open-addressing table: keys (name pointers)
at 0x5f76f8, objects at 0x5f7ef8.

```
hash(name):  h = 0                                  # h is a SIGNED 32-bit number
             for c in name:  c = lower(c);  h += c;  h += h << 10;  h ^= h >> 6
             h += h << 3;  h ^= h >> 11;  return h & 0x1ff
```

- **add**(name, obj): a leading `"` is removed and the name cut at the next `"`, in
  place. From `hash(name)` step by one (wrapping) to the first slot whose key is empty
  **or** whose object is null and whose key equals the name ignoring case; store key and
  object there. A slot vacated by a *different* name is stepped over, never reused.
- **remove**(name, obj): from `hash(name)`, up to 523 probes, clear the object of the
  first slot that **holds this object** (keys are not compared; empty keys do not stop
  the search). The key stays.
- **find**(name, out, limit): from `hash(name)` until the first empty key: every slot
  whose key equals the name ignoring case and whose object is not null, until `limit − 1`
  are found; then a null. `world_findObjectByName` 0x14f498 is find with limit 2.

Result order is probe order: objects that share a name come back in the order they were
registered, except that a new object takes the earliest slot a same-named object has
vacated. Keys are never cleared during a level (only `world_init` and teardown zero the
table), so the table fills with every distinct name ever registered; with 512 distinct
names and no free key, add would not terminate (the model refuses).

### 4.6 By class: `world_findObjectsByClass` 0x14c0b8 (typeName, out, limit)

Walks the every-frame list, the 15 lists 0..14 and the 60 lists 0..59 (iterators with the
exclude mask) and returns the objects whose C++ type name — the string of the type-info
object, which is the length-prefixed form such as `10GameObject` — equals `typeName`
exactly, up to `limit − 1`. **Objects on no run list are not found.** One caller: script
`objInPlayerTrig` 0x142b2c, with `Trigger`'s type name and limit 50.

### 4.7 Whole-world walkers

`world_forEachGridObject` 0x14a610 (fn): the off-grid list, then grid A cell by cell in
memory order (row 0 columns 0..119, row 1, …), then grid B. `world_forEachRunObject`
0x14a7c8 (fn): the every-frame list, 15 lists, 60 lists. Both use iterators with the
exclude mask, so the callback may move, create or destroy objects (executed with callbacks
that do all three). By the iterator rules an object the callback moves into a list that
is walked later is visited again there, and one moved into the list being walked, or an
earlier one, is not.

These are all the readers there are. A scan for references to the eight list globals
finds only the functions of this document plus `world_drawObjects` 0x14b168,
`world_writeRecords` 0x14e140 (saving) and `obj_moveWithCollision` 0x14d4b8, which
carries two inline copies of `obj_updateGridCell` (0x14d5b8–0x14d6a0 before its own box
query at 0x14d714, and one ending at 0x14d9a4 inside its loop over the objects it
touched, taken when it is pushed out of one). A mover is therefore at the front of its
cell when it queries. The box query is the only way simulation code looks into grid
cells.

### 4.8 `world_findFreeSpot` 0x14acf8 (out, centre, int spread, int radius, bool *ok, anyHeight)

Shared-seed consumer; 20 call sites, one of them the level start marker (section 7.3).

```
result = centre
for tries = 0 .. 49:
    (x, y, z) = point in the unit ball from g_randSeed     # 3 draws per sample, repeated
                                                           # while x·x + y·y + z·z > 1
    cand = (centre.x + x·spread, centre.y + y·spread, centre.z)
    if terrain_testFlag1(world, radius, cand) != 0.0: continue
    h = terrain_height(world, radius, cand)
    if not (h - centre.z < 6.0) and not anyHeight: continue
    result = (cand.x, cand.y, h)                           # kept even if the next test fails
    list = world_collectObjectsInBox(result.xy ± radius, h ± 100000, limit 0x80)
    if no o in list with (o.flags & 1) == 0 and
          (o.x - result.x)² + (o.y - result.y)² <= radius·radius + o.radius²:  break
*ok = (tries != 50);  *out = result
```

- A try costs three draws times the number of rejected samples plus one (about 1.9
  samples on average), so the number of draws is data-dependent but the same everywhere.
- The height test is one-sided: a floor far below the centre passes.
- The object test compares with the **sum of the squares**, `radius² + r²`, which is less
  than `(radius + r)²`: spots that overlap a neighbour slightly are accepted.
- When all 50 tries fail, the result is the last candidate that passed the terrain and
  height tests (or the centre), and `*ok` is 0.

## 5. Run lists, activity and `runObjects`

### 5.1 Joining and leaving a run list

| Function | Effect |
|---|---|
| `obj_runEveryFrame` 0x14f248 | remove the current run link if any; link to the front of the every-frame list. Called on an object that is already there, it moves it to the front |
| `obj_runEvery60` 0x14f2b8 | remove; **step the cursor first** (`cursor = cursor + 1`, 60 becomes 0); link to the front of `g_runLists60[cursor]` |
| `obj_runEvery15` 0x14f330 | the same with 15 lists and their own cursor |
| `obj_stopRunning` 0x14f290 | remove |
| `obj_delete` 0x14f200 | remove (and join the delete list) |

Both cursors are 0 in the executable and are set to 0 by teardown, so the first slow
object of a level goes to list 1 and list 0 is used 60th (15th). The cursors are shared
state: every `obj_runEvery60` call anywhere shifts the frame on which all later slow
objects run.

### 5.2 Activity: `obj_updateActive` 0x14db08 (obj, wasActive, radius) → 0 or 1

```
if obj.flags & 0x80000: radius = 44000
r2 = (float)(int32)(radius * radius)            # integer multiply, low 32 bits
if g_cullByCamera:  active = dist2(obj, g_cameraFocus) < r2
else:               active = any dist2(obj, g_activityCenters[i]) < r2, i < count
if active == wasActive: return active           # nothing is relinked
if active: obj_runEveryFrame(obj)   else: obj_runEvery60(obj)
return active
dist2(a, b) = ((a.x-b.x)² + (a.y-b.y)²) + (a.z-b.z)²      # three axes
```

The function stores nothing in the object: **the caller keeps `wasActive`** (creatures in
a bit of their 64-bit flag word, `Creature_updateActive` 0x10c0f0; props in a byte or
word of their own). Callers: `Creature_updateActive` (74 call sites) and the run functions
of `MissileWeapon`, `UserParamProp`, `CosmeticPropAnim`, `AutoProp`, `AutoEmitter`,
`HateBridge`, `Catapult`, `JumpGate`, `Savepoint`, `PointSourceSound`, `LightningRod`,
`SpiritAnchor`. A radius of 46341 or more overflows the square and nothing is ever inside
it (executed). The fixed radii read are far below that (480, 1600, 44000); the creature
wrapper passes the largest of three 16-bit fields (+0x3c4, +0x3ac, +0x3ae), so a larger
value is representable there — whether any creature has one was not checked.

So an object's list follows activity like this: it is created on whatever list its
constructor chose; the first time its own run calls `obj_updateActive` with a different
answer, it moves — **to the front** of the every-frame list when it wakes, to the front
of the next 60-list when it falls asleep. Because the caller is the object's own run, a
waking object has already run this tick (from its slow list) and runs again next tick
from the every-frame list, first; a falling-asleep object runs **a second time in the
same tick** if the 60-list it is given is this frame's (executed), otherwise next within
1 to 60 ticks.

### 5.3 The activity centres: `gameSetObjectVis` 0x1e4d48

A run task with priority 0 (section 6), so it runs before `runObjects` in every tick and
the centres are positions from the **start** of the tick.

```
d = dialog_objIfOpen()
if d: count = 1; g_cullByCamera = 0; centres[0] = d.position; return
g_cullByCamera = (g_localCamera.mode(+0x34) != 1)
if g_networkMode and not g_cutsceneActive: g_cullByCamera = 0
count = 0
for slot = 0 .. g_numPlayers-1: if players[slot].object: centres[count++] = its position
```

Dead players' objects count; a slot without an object does not. `g_cullByCamera` is 1 in
the executable, so before the first tick of a session activity is judged from the camera.
In a net game the camera case is reachable only during a cutscene (FINDINGS D6).

`isNearView` 0x1e77c0 (pos, f12 reach) uses the same switch but a different shape:
`|pos.x − c.x| <= reach and |pos.y − c.y| <= reach` — a **square in x and y**, height
ignored — around the camera focus, or around any player slot's object (read from the
player table, not from the centres, so an open dialog does not narrow it).

### 5.4 `runObjects` 0x14b910 — one tick of every object

Run task, priority 10. In order:

1. **Flush the delete list** (0x14b94c–0x14b9a8): iterator with `g_excludeMask`; slot 1
   with argument 3 for each object, front to back — last deleted, first destroyed.
2. **Sample the pool** (0x14b9ac–0x14b9c4): if `g_simFrame & 0x3f == 0`,
   `g_poolFreeCount = pool_countFree()`.
3. **The reaper** (0x14b9c8–0x14bb1c), if `g_poolFreeCount < 300` — section 5.6.
4. If `game_isFrozen()` is 0 (0x14bb20), three walks, each `iter_begin(list,
   g_excludeMask)` with the mask read again for each list:
   1. `g_runListActive`,
   2. `g_runLists15[g_simFrame % 15]`,
   3. `g_runLists60[g_simFrame % 60]` (the frame number is read again for each),

   and for every object the iterator yields, unless it has flag 0x8000, a virtual call of
   **slot 4** with the object as its only argument.

`runObjects` does not advance the frame number (section 6.3 does).

### 5.5 The order objects run in

Within a list: front to back, which is the reverse order of linking. Therefore, on the
every-frame list:

- whatever linked itself most recently runs first: a projectile or effect object created
  in tick T runs first in tick T+1, before its creator;
- a monster that woke in tick T (5.2) runs in T+1 before everything that was active
  before it, the players included;
- `Player_ctor` 0x1a1d28 calls `obj_runEveryFrame` (0x1a2340, Observed), so a player is
  at the front from the moment its object is built. After a load the session code builds
  the players in slot order after the level's own objects
  (`docs/issues/arena-entry.md` section 2, not re-read here), so the highest slot runs
  first and all players run before every level object that was on the every-frame list
  already; a player object that is re-made during play goes to the front again
  (FINDINGS G17);
- an object that calls `obj_runEveryFrame` on itself or on another object each tick
  reshuffles the list each tick; the order is still a function of lockstep state.

Then the slow list of the frame, then the slowest. An object on a slow list therefore
always runs after every active object of the same tick.

### 5.6 The reaper

When the sampled free count is below 300 (the pool has 1056 blocks):

```
L = (g_simFrame << 4) & 0x0fffffff;  col = L % 120;  row = (L / 120) % 120
repeat 16 times:
    col += 1;  if col >= 120: col = 0, row += 1;  if row >= 120: row = 0
    for node in g_gridB[row][col], front to back:        # plain walk: no iterator, no mask
        o = node.object
        if not (o.flags & 0x1000): continue
        if g_networkMode == 0 and g_poolFreeCount >= 200
           and not (230400.0 < dist2(o, g_cameraFocus)): continue      # within 480: spared
        destroy o (slot 1, argument 3);  break            # one victim per cell per visit
```

- 16 cells a tick, the whole of grid B every 900 ticks; frame f looks at cells
  16f + 1 … 16f + 16 (mod 14400) in list-index order.
- The victim in a cell is the first expendable object in list order — the one that moved
  or was created last.
- In a net game the camera is never consulted (the test at 0x14ba80 skips it).
- The count is a sample: it is refreshed only on frames divisible by 64, and teardown
  sets it to 100000, so after a level load the reaper is off until the next such frame
  whatever the pool holds.
- The block is freed on the spot, before any object runs in this tick.

## 6. Tasks and the tick

### 6.1 The table

`g_tasks` 0x840100: 16-byte records {function, priority, name, flags}, kept sorted by
priority; `g_taskCount` 0x44fdb8; one global cursor `g_taskCursor` 0x44fdbc. The function
pointer is the task's identity. Flags bit 0 = draw task; the value 2 exists (two run
tasks) and is never tested. The full list of the program's 42 registrations is in
`docs/mainloop.md` section 2.

| Function | Behaviour (executed) |
|---|---|
| `task_add` 0x19e4a0 (fn, priority, name, flags) | nothing if a record with this fn exists. Otherwise insert behind every record whose priority is ≤ the new one (equal priorities keep registration order). If the cursor is at or past the insertion index it is incremented |
| `task_remove` 0x19e664 (fn) | close the gap; if the cursor is at or past the index it is decremented |
| `task_isRunning` 0x19e5e8 (name) | 1 if a record has exactly this name |
| `tasks_call` 0x19e798 (exclude, include) | cursor = 0; while the cursor is inside the table: call the record under it if `flags & exclude == 0` and (`include == −1` or `flags & include != 0`); cursor += 1. Count and cursor are read from memory after every call |

So during a pass, with the cursor at the running task's index: a task that removes itself
is followed by the right neighbour; a task inserted behind the cursor is called in the
same pass; a task inserted at or before the cursor waits for the next pass; a task removed
before it was reached is not called. One case is easy to get wrong: after the running
task has removed itself the cursor is one lower, so a task that is then inserted at the
index the running task had (same priority, registered now) **is called in this pass**
(executed as a fixed case; the rest with random tasks that add and remove tasks while the
pass runs).

### 6.2 Run tasks against draw tasks

The run pass is `tasks_call(1, −1)` (every record without bit 0), once per simulated
tick; the draw pass is `tasks_call(0, 1)` (records with bit 0), once per displayed frame,
on each machine at its own rate. Only the run pass is part of the lockstep. Relative to
the objects (priorities from `docs/mainloop.md`, registration of the two object tasks
read at 0x14c370):

| Priority | Run task | Why it matters here |
|---|---|---|
| 0 | `runwater`, then `gameSetObjectVis` | the activity centres are set before any object runs |
| 1 | `gameMiscSync` | |
| 10 | **`runObjects`** | every object's slot 4 |
| 11 | `camera` (does nothing in a net game) | the camera focus that the *next* tick's activity test may read |
| 20 … 125 | death task, menus, HUD, arena, dialog, **`Script`** (125) | scripts run after all objects of the tick; an object a script creates first runs in the next tick |
| 300 | `cutRunFrame` (during a cutscene) | |
| 1000 | `plotroute` | |

`world_drawObjects` 0x14b168 is the draw task with priority 21. It calls slot 5 of a
per-machine set of objects (FINDINGS D13) and is not modelled.

### 6.3 `tasks_run` 0x3226e4 (n) — n ticks

1. In a net game `g_menuInputLockout` 0x41b4fc = 0.
2. Save the two edge words (+0xc, +0x10) of the four pads.
3. n times (not at all for n ≤ 0):
   1. the run pass;
   2. offline only: if `game_isFrozen()` is 0 and `g_warmupFrames` 0x506048 is 0,
      `g_simFrame += 1`. (In a net game `net_frameLoop` sets the frame number around the
      call.) So the frame number objects see during a tick is the count of completed
      ticks;
   3. zero the pads' edge words, so only the first tick of a displayed frame sees a
      press;
   4. **end of tick**: `game_rebuildAlivePlayers` 0x1e72f8, `game_checkAllDead`
      0x1e7438, then (after an empty loop over the player count, 0x3227ec–0x322838)
      `pad_updateRumble` 0x17474c.
4. Once: if the lock-out is positive and the hold flag 0x41b500 is clear, it becomes 0
   when no pad has a button held (`held & 0xff0fffff`), else it is decremented.
5. Restore the saved edge words.

`game_rebuildAlivePlayers`: the alive list (0x4f8440, count 0x4f8420) is the slots, in
slot order, whose object exists and has not flag 0x8; the local list (0x4f8430, count
0x4f8424, first 0x4f841c, previous count 0x4f8428) is the subset for which
`net_isLocalSlot` answers 1. It runs **after** every run task of the tick, so during a
tick the list is the one from the end of the previous tick unless something rebuilt it on
the spot (FINDINGS G11).

## 7. Level load and teardown

### 7.1 Teardown: `world_deleteAllObjects` 0x14c460

Called from `game_clearLevel` 0x1e4e88, which afterwards runs `pool_init` (0x1e5118), so
a level starts with the pool handing out ascending addresses from its base again. In
order:

1. `g_poolFreeCount = 100000`; both round-robin cursors = 0; `g_worldTearingDown`
   0x4039bc = 1.
2. The delete list, with the exclude mask: slot 1 (3) for each.
3. Grid A, cell by cell in memory order (row 0 column 0 … row 119 column 119), each cell
   with an iterator and **mask 0**: slot 1 (3) for each object.
4. Grid B the same way.
5. The off-grid list, mask 0.
6. The name table is zeroed; `g_worldTearingDown` = 0.

The run lists and the always-draw list are not walked; they empty because each
destructor clears the object's own links. Destruction order is therefore **position
order** (row, column, then most recently moved first), not creation order — it matters
for destructors that have shared side effects. An object that a destructor destroys or
deletes on the way is handled by the iterator rules of 3.3; after the call no object and
no pool block is left (executed with destructors that delete and destroy others).

`world_init` 0x14c370 (once, at start-up) registers the two tasks and zeroes both grids,
the off-grid head and the name table without clearing nodes.

### 7.2 `world_loadRecords` 0x14e808 (blob, filterOnly) → bytes consumed

The object list of a level file and a saved level state share one format
(`docs/objects.md`, "Level-object records"; `RecordBlob` in the model builds one).

1. Reset the light-marker block at 0x44fde0 (drawing). Read count, flags and the string
   table; set header bit 2 ("offsets are pointers now"); `g_loadStrBase` 0x5f8704 =
   string table.
2. For each record **strictly in file order**:
   1. if `filterOnly`: skip the record unless `g_saveFilter` is installed and answers
      non-zero for the class name (with no filter every record is skipped);
   2. turn the property offsets into pointers (only on the first load of a blob);
   3. `obj = g_objectFactory(className, &position, angle, props)`; if it returned an
      object, store the class-name pointer at +0x34;
   4. if the header has bit 1 and an object was made: virtual slot 8 with the address of
      the record's state bytes (8-aligned behind the property list).
3. Flush the delete list (exclude mask), so an object whose constructor deleted it is
   gone before the first tick.

The factory (`world_objectFactory` 0x159c94, table in `docs/objects.md`) is a chain of
string tests on the class name, first match wins; a match is `pool_new` followed by one
constructor. So **objects are constructed in record order, each draws the shared seed
once in the base constructor (plus whatever its class draws), and each lands at the front
of its grid cell and of the run list it picks**: after a load, a cell holds its objects
in reverse record order and so does each run list. The two slow-list cursors advance in
record order.
`world_createObject` 0x14f6c8 (className, pos, angle, props) is the same factory call for
code that creates by name during play; its fourth argument is passed through untouched.

### 7.3 The start marker: `Player1_ctor` 0x158928

A `Player1` record becomes a 0x4c-byte object with flags 0x3 and the record's facing at
+0x38. It then competes for the spawn slots through `g_playerStartRank` 0x4f7108 (0 at
level load, 3 after a load from a save — `docs/issues/arena-entry.md` 1.4):

| Test, in this order | Result |
|---|---|
| rank is already 3 | nothing more |
| rank ≤ 0 | take, rank = 1 |
| rank is 1 and the record has a non-zero `default` | take, rank = 1 |
| `from` equals `g_prevLevelName` 0x41b7c2 and byte 0x41b51e is 0 | take, rank = 2 |
| byte 0x41b51e is not 0 and `from` is `gate` | take, rank = 3 |
| byte 0x41b51e is 0 and `name` equals `g_entranceName` 0x4f8468 | take, rank = 3 |

(String compares are exact. Byte 0x41b51e is written by `player_recallTick` 0x1b6260 and
the level loader 0x3214c0.) A marker that **takes** fills all four spawn slots, whatever
the player count:

```
for slot = 0 .. 3:
    g_spawnPos[slot]    = world_findFreeSpot(marker position, spread 36, radius 24)
    g_spawnFacing[slot] = marker facing + (one more shared draw) % 4000 - 2000
```

Markers are processed in record order like everything else. Among several `default`
markers, or several whose `from` matches, the **last** in the file wins (each takes
again); among markers that reach rank 3 the **first** wins (the later ones stop at the
first test). Every taking marker advances the shared seed by four searches and four
draws, including the ones whose result is then overwritten. What the
session code does with the slots afterwards (a second search for slots 1–3, the `Player`
constructors in slot order) is in `docs/issues/arena-entry.md` section 2.

## 8. Per-machine state read by this code, and what it gates

"Per machine" means a value that can differ between the machines of one net game. Rows
marked *ledger* are already in `FINDINGS.md`; the others are additions (proposed rows in
section 10).

| Value | Read at | Gates | Status |
|---|---|---|---|
| `g_excludeMask` 0x4039b8 | every iterator walk here: the three run walks and the delete-list flush in `runObjects`, `world_flushDeleteList`, the flush in `world_loadRecords`, the delete-list walk of teardown, both `forEach` walkers, `world_findObjectsByClass`, the two always-draw helpers; per object in the box query | which objects run, are destroyed, are returned | ledger G6 / D13 for runs, draws and the box query. **Addition:** the delete-list flush honours it too — an `obj_delete`d object that carries a masked flag survives the flush for as long as the mask names it |
| flag 0x20000 on an object | box query 0x14aa54 | never returned | ledger G6 |
| `g_poolFreeCount` 0x403a04 (= pool occupancy on frames divisible by 64) | `runObjects` 0x14b9c8, 0x14ba88 | whether the reaper runs, and offline whether it spares objects near the camera | ledger D21, `docs/objects.md` O1 |
| pool exhaustion | every creator | whether an object and its seed draw exist | ledger D21 |
| `g_networkMode` 0x402791 | reaper 0x14ba80; `gameSetObjectVis` 0x1e4db4; `tasks_run` 0x3226f4, 0x322774 | camera test in the reaper; camera activity outside cutscenes; who advances the frame number | not per machine within a game |
| `g_cameraFocus` 0x44f048 | reaper (offline only); `obj_updateActive` and `isNearView` when `g_cullByCamera` | activity, run list, everything gated on "near the view" | ledger D6, D29, D35 |
| `g_localCamera`→+0x34 (camera mode) | `gameSetObjectVis` 0x1e4dbc | `g_cullByCamera`; in a net game only while a cutscene is active | ledger D6. **Addition:** during a net cutscene the switch itself is per machine — a machine whose camera is in mode 1 judges activity from the players, the others from their camera focus |
| `g_cutsceneActive` 0x44fcd0 | `gameSetObjectVis` 0x1e4dd4 | the same | ledger D6 |
| `dialog_objIfOpen()` | `gameSetObjectVis` 0x1e4d50 | a single activity centre while a dialog is open | ledger D38 |
| `g_players[i]` object pointers | `gameSetObjectVis`, `isNearView`, `game_rebuildAlivePlayers` | activity centres, alive list | lockstep, except while prediction has swapped in the copy (ledger G3) |
| `net_isLocalSlot` | `game_rebuildAlivePlayers` 0x1e73c0 | the *local* alive list only | per machine by design |
| `game_isFrozen()` | `runObjects` 0x14bb20; `tasks_run` 0x322780 (offline) | whether any object runs; offline whether the frame number advances | in a net game it returns `g_paused` only (ledger D12) |
| `g_warmupFrames` 0x506048 | `tasks_run` 0x322794, offline only | frame number | per machine, offline only (`docs/mainloop.md`) |
| pads' edge and held words | `tasks_run` | menu lock-out; nothing in the object system | per machine |
| object addresses | handle targets, the name table's object column, `pool_free` | identity only; nothing here orders or hashes by address | `docs/objects.md` O8; executed: every address matched the model, which allocates from lockstep state only |
| the task table | `tasks_call`; `task_isRunning` by simulation code | which run tasks exist | `docs/mainloop.md` P7 |
| `g_prevLevelName` 0x41b7c2, `g_entranceName` 0x4f8468, byte 0x41b51e | `Player1_ctor` 0x158a20–0x158a98 | which marker takes the spawn slots, and so how many searches and shared draws a load makes | level-change state, written by the level loader, script `setEntrance` and `player_recallTick`; shared as far as those writers are (not checked here) |

Not per machine but easy to get wrong in a rebuild, because they are **shared state that
this code keeps outside the objects**: the two slow-list cursors, the order of every
list, and the name table's slot layout (its keys survive removals).

Addresses are a different matter. Handle-node addresses are per machine in a net game
(draw-side links and the prediction copy take nodes, `docs/issues/stale-pointers.md`
5.4), and so is the free list of the pool class the copy's block comes from. Nothing in
this code depends on them; a rebuild has to reproduce the free-list discipline only if it
wants its memory to be comparable with the original's, as the differential test does.

## 9. What the differential test covers

`python3 tools/difftest_objects.py` (seed 20973; `--quick` runs a tenth). The original
functions run for real on a world built by the original constructors in the
interpreter's memory; the model holds the same world. After **every** operation the test
compares: the operation's result; the order and arguments of every callback; every list
head and every node of every list (run lists, delete list, always-draw list, off-grid
list, all 28,800 grid cells); the 19 words of every live object; the pool and node free
lists; the shared seed, both cursors, the sampled pool count; all 512 slots of the name
table; class definitions; the task table.

Callbacks are recording stubs: slot 4 (run) and slot 1 (destructor, which then runs the
real `GameObject_dtor`) of the `GameObject` table, slot 8, the object factory, the save
filter, walker callbacks and tasks. What a stub does is decided by a seeded script while
the model runs, and replayed through the original functions by nested calls inside the
running original.

Last full run: **23 properties, 23 PASS, 0 FAIL** (seed 20973, about 10 minutes); the quick
run also passes with seeds 7 and 314159. No mismatch is left unresolved.

| Property | Steps compared | What it exercises |
|---|---|---|
| `create` | 1,680 | 981 constructions (29 more refused by a full size class: no object, seed untouched) and the destructions between them: every field, the seed draw, the grid list, the name table (quoted, repeated, empty and mixed-case names), class definitions across generation changes, unzeroed blocks with a stale property pointer |
| `order.cases` | 41 | 19 hand-made cases of the ordering rules of sections 2.3, 3.1, 4.3 and 5 (last linked runs first; the three lists in order; first run next tick; first run in the same tick on a slow list; running twice in one tick; relinking moves to the front; deleted objects; flag 0x8000 and the mask; box-query order, in-place move and limit; the `hide` read; one draw per constructor) |
| `run.offline` | 7,107 | 2,000 ticks of `runObjects` on 120–260 live objects: 25,929 virtual run calls and 2,825 destructor calls, all in the model's order, while the stubs made 26,406 operations from inside them (2,829 creations, 1,676 deferred deletes, 1,050 direct destroys with cascades from destructors, 7,277 moves, 4,147 run-list changes, 5,697 queries). One address was run twice in a tick 19 times; an address that held no object when the tick began was run in that tick 13 times |
| `run.net` | 3,583 | the same with the network flag set: 1,000 ticks, 12,084 run calls, 1,337 destructor calls |
| `query` | 4,406 | 2,473 box queries returning 9,667 objects in the same order (254 cut off by the limit; limits 0 to 512; masks 0, 0x8, 0x20000, 0x200000, 0x8009; boxes from a point to the whole grid, inverted, random bit patterns, wrapping), 399 sphere queries, 319 name lookups, on a world that moves between queries, with radii and heights changed on the way |
| `grid` | 3,150 | moves across cells and within them, coordinates on and around every boundary (−1, 0, ±256, the grid edges, 1e20, random patterns), flag 0x800 and 0x2 toggles, off-grid, the always-draw helpers under different masks, 30 first links through `obj_linkToGrid` |
| `active` | 3,310 | `obj_updateActive` with 0 to 4 centres or the camera, radii 0 to 2^20 and negative, flag 0x80000, every `wasActive` value; 1,089 calls changed the run list |
| `reaper.offline`, `reaper.net` | 2,503 + 2,547 | 196 ticks each on a pool filled to between 320 and 0 free blocks: sampling on the 64th frame, both thresholds, the camera test offline and its absence in a net game, several expendable objects per cell, expendable objects in grid A and non-expendable ones in grid B, destructors that destroy other objects; 1,277 and 1,355 destructions before the run walks; refused allocations |
| `walkers` | 3,568 | 16 rounds of: build about 140 objects, both `forEach` walkers with callbacks that move, create and destroy (4,036 callbacks), class lookups by four names and several limits, deletes and a flush, more deletes, `world_deleteAllObjects` under different masks — after which no object and no pool block is left |
| `tasks` | 3,825 | 1,201 passes of the task table (`tasks_call` with eight mask pairs, `tasks_run` for −1 to 3 ticks, offline and net, frozen, warm-up, lock-out, pads): 12,112 task calls in the same order while running tasks made 3,241 additions and 3,070 removals; `runObjects` itself runs as a task in these passes |
| `vis` | 13,876 | 3,000 random states of player table, dialog object, camera mode, cutscene flag and network flag through `gameSetObjectVis`, then `obj_updateActive`, `isNearView` (9,000 calls) and `game_rebuildAlivePlayers` under that state |
| `load.records` | 522 | 158 loads of made-up record blobs (with and without state bytes, with and without the filter, loaded a second time): 2,796 factory calls in file order with the same arguments, slot-8 calls with the right state address, objects that delete themselves in the factory, then `world_createObject` |
| `load.marker` | 2,556 | 896 free-spot searches with scripted terrain answers (25 ended without a spot) among real objects, and 604 `Player1` constructions over every rank, `from`, `name`, `default` and gate combination (340 took the spawn slots): positions, facings, rank, the seed |
| `query.*`, `active.*`, `load.marker.*` | 7,751 | a fifth of the three scenarios again under each of the adder models `ps2g1`, `chop`, `nearest` |

Coverage of the original as executed (basic blocks entered / basic blocks of the function;
a block starts at the function entry, at every branch target and after every conditional
branch):

| Function | Blocks | | Function | Blocks |
|---|---|---|---|---|
| `GameObject_ctor` | 54 / 56 | | `objNames_add` | 13 / 13 |
| `GameObject_dtor` | 34 / 35 | | `objNames_remove` | 8 / 8 |
| `obj_linkToGrid` | 11 / 11 | | `world_findObjectsByName` | 10 / 10 |
| `obj_updateGridCell` | 12 / 12 | | `world_findObjectsByClass` | 28 / 31 |
| `obj_moveOffGrid` | 4 / 4 | | `world_init` | 7 / 7 |
| `obj_isOffGrid` | 7 / 7 | | `world_deleteAllObjects` | 34 / 34 |
| `obj_delete` | 3 / 3 | | `world_loadRecords` | 27 / 27 |
| `obj_runEveryFrame` | 3 / 3 | | `world_createObject` | 3 / 3 |
| `obj_stopRunning` | 3 / 3 | | `world_findFreeSpot` | 20 / 20 |
| `obj_runEvery60` | 5 / 5 | | `Player1_ctor` | 23 / 23 |
| `obj_runEvery15` | 5 / 5 | | `obj_getPropInt` | 15 / 15 |
| `world_flushDeleteList` | 7 / 7 | | `obj_getPropStr` | 14 / 14 |
| `obj_addToAlwaysDraw` | 1 / 1 | | `task_add` | 14 / 14 |
| `obj_addToAlwaysDrawOnce` | 7 / 7 | | `task_isRunning` | 7 / 7 |
| `world_clearAlwaysDraw` | 5 / 5 | | `task_remove` | 15 / 15 |
| `world_collectObjectsInBox` | 23 / 23 | | `tasks_call` | 7 / 7 |
| `world_collectInSphere` | 8 / 8 | | `tasks_run` | 31 / 31 |
| `obj_updateActive` | 18 / 18 | | `gameSetObjectVis` | 11 / 11 |
| `runObjects` | 44 / 44 | | `isNearView` | 17 / 17 |
| `world_forEachGridObject` | 20 / 20 | | `game_rebuildAlivePlayers` | 10 / 10 |
| `world_forEachRunObject` | 17 / 17 | | **all 41 functions** | **605 / 611** |

The six blocks never entered cannot be: 0x14cc84 is the constructor's grid-B branch (the
flags are zero there); 0x14cf44 and 0x14d194 are the "not found" exits of a property
lookup that the compiler duplicated behind a lookup that has just succeeded; 0x14c148,
0x14c1f8 and 0x14c2c0 raise the C++ "typeid of a null pointer" error for an object
pointer the iterator never yields as null.

As a check on the test itself, ten single errors were planted in the model, one at a time
(slow lists walked in the other order; no relink when the cell is unchanged; query
results by column first; the 60-list cursor stepped after use; `obj_delete` also leaving
the grid; the destructor clearing the heads in the other order; the reaper one cell
further; a task inserted in front of equal priorities; a name slot reused for any name;
an activity radius off by one): each was reported as FAIL by the scenario that should
see it.

Limits of the comparison:

- Only base `GameObject`s (and `Player1` markers) are built. No derived constructor, run
  or destructor was executed, so which list each class joins and what each class draws is
  not covered here.
- `world_drawObjects`, `world_objectFactory`, the record writer (`obj_writeRecord`,
  `world_writeRecords`, `world_saveState`), `obj_runActionScripts`, `obj_removeProp`,
  `obj_getPropFloat`, `GameObject_clone` and `game_clearLevel` were not executed.
- The terrain queries inside `world_findFreeSpot` are scripted answers, not terrain.
- `game_isFrozen`, the three end-of-tick calls inside `tasks_run`
  (`game_rebuildAlivePlayers` was run on its own), `dialog_objIfOpen` and
  `net_isLocalSlot` are stubs.
- Floating point: the box and sphere queries, the activity test and the free-spot search
  agree bit for bit under the interpreter's default model and under its three other adder
  models; the reaper's distance test and `isNearView` were run under the default model
  only. Agreement shows that the model performs the same operations in the same order; it
  does not show that either matches a console in the last bit
  (`docs/issues/dynamic-tests.md`).

## 10. Corrections to earlier documents, proposed ledger rows

### 10.1 Earlier statements that execution or a second reading did not bear out

| Where | Statement | What was found |
|---|---|---|
| `docs/objects.md`, "Properties", and flag row 0x8000 ("set by hide") | "A `hide` property moves the object to the off-grid list" (said of the base constructor) | Executed: the base constructor looks `hide` up **before** it stores the property list (lookup 0x14ccf0, store 0x14cd64), so for a pool block the test reads a null list and never fires. Hiding at load is done by derived constructors that test `hide` themselves: `Creature_ctor` 0x109f10–0x109f3c (off-grid, flag 0x8000, +0x231 bit 3), `Catapult_ctor` 0x24d598. A class that does not test it ignores the property |
| `docs/objects.md`, grid table and flag row 0x2 | "new flag-2 objects" are linked to the off-grid list | Only `obj_linkToGrid` does that, and its single caller is the prediction-copy clone (0x13b58c). In `GameObject_ctor` the flags are zero when the link is made, so no constructed object starts off-grid because of a flag, and none starts in grid B (branch 0x14cc84 is unreachable): a constructor that sets 0x800 or 0x2 must relink |
| `docs/objects.md`, `runObjects` step 1, and row O6 | "Destroy every object on `g_deleteList`"; the exclude mask is listed for the box query, run walks and grid walks | The delete-list flush is an iterator walk with `g_excludeMask` too (0x14b928–0x14b950; the same in `world_flushDeleteList`, `world_loadRecords`, and the first walk of teardown): a deleted object that carries a masked flag is skipped |
| `docs/objects.md`, "Run lists" | "The slow lists are filled round-robin" | True, with a detail that fixes the frame numbers: the cursor is stepped **before** use, so after teardown the first slow object goes to list 1 |
| `docs/objects.md`, movement helpers | `world_findFreeSpot` draws "three draws per try" and accepts points "clear of blocking objects" | Three draws per *sample*; a try repeats samples until one is inside the unit ball. "Clear" means `dx² + dy² > radius² + r²`, not `(radius + r)²`, and the height test is one-sided (`docs/issues/arena-entry.md` section 2 says "within 6") |
| `docs/spec/skills-35-68.md` section 1.4 | "The walks of the 15-frame and 60-frame lists come after the every-frame walk, so an object created from those is also first run on the next frame" | Correct for objects that join the every-frame list. Not covered there, and executed here: an object that joins **this frame's slow list** during an earlier walk runs in the same tick, and an object that leaves the every-frame list for this frame's 60-list runs twice in one tick (section 2.3, 5.2) |
| `docs/OVERVIEW.md`, "Time and tasks" | "object visibility (-1)" | `gameSetObjectVis` is registered with priority 0 (0x322a8c), after `runwater` (also 0), as `docs/mainloop.md` has it |
| `docs/mainloop.md` section 2 | "a task added at or before the cursor waits for the next pass" | True of the cursor; but the cursor has stepped back when the running task removed itself first, and then a task inserted at that task's old index is called in the same pass (section 6.1, executed) |
| `names.tsv`, `world_createObject` | "(className, Vec3 *pos, angle)" | Four arguments: the property list in the fourth register is passed through to the factory (0x14f6c8–0x14f70c; the five call sites read all set it) |
| `names.tsv`, `world_findObjectsByClass` | "comparing the type-info name" | Yes; the name is the length-prefixed form (`10GameObject`, `7Player1` — executed), and only objects on a run list are found |
| `docs/objects.md`, "Deleting" | `world_flushDeleteList` 0x14f3a8 as one of the places the list is flushed | No call to it and no stored pointer to it was found; the flushes that happen are the inline copies in `runObjects`, `world_loadRecords` and `world_deleteAllObjects` |

Confirmed by execution, as written in the earlier documents: the box query's order, limit,
96-unit pad and the two skip tests (`docs/objects.md`, FINDINGS G6); `obj_updateGridCell`
relinking at the front even within one cell; the reaper's victim being decided by link
order with no mask and the camera test being skipped in a net game
(`docs/issues/stale-pointers.md` 5.3, ST5, O3); the pool sample on frames divisible by 64
and the thresholds 300 and 200; the teardown order of `docs/issues/arena-entry.md` 1.4;
the `Player1_ctor` rank rules and the four searches plus four draws of its section 2;
`tasks_run` as in `docs/mainloop.md` section 3; `gameSetObjectVis` as in FINDINGS D6 and
D38.

### 10.2 Proposed ledger rows

| # | Finding | Kind | Evidence |
|---|---|---|---|
| new | An object's run in a tick is not always "once": an object linked during the every-frame walk (or the 15-list walk) to the slow list that the same `runObjects` call walks later runs in the tick it was created or moved in, and an object that `obj_updateActive` moves off the every-frame list onto this frame's 60-list runs twice in that tick. Decided by `g_runList60Cursor`, `g_runList15Cursor` and `g_simFrame`, all lockstep state, so it is the same on every machine; a rebuild that runs each object once per tick, or keeps one list per object, diverges | Observed and executed | `runObjects` 0x14bb30–0x14bcb0; `obj_updateActive` 0x14dc60–0x14dcac; `tools/difftest_objects.py` properties `order.cases`, `run.*` |
| new | The delete-list flush uses the exclude mask. While the mask is 0x20000 (every simulated tick of a net game) an object with that flag that was `obj_delete`d stays on the delete list, in the grid and in the name table until a flush runs with another mask or teardown reaches its cell. Whether anything calls `obj_delete` on a prediction copy is **Unknown** (not searched) | Observed (mechanism), executed | 0x14b928, 0x14f3b4, 0x14ea00, 0x14c468 |
| refines D6 | The switch `g_cullByCamera` is `mode != 1` of **this machine's** camera object (`g_localCamera`→+0x34), kept in a net game only while a cutscene is active. So during a net cutscene not only the reference point but the choice between "camera" and "players" is per machine, if camera modes can differ between machines at that moment (Unknown) | Observed, executed with a stand-in camera | 0x1e4da8–0x1e4ddc |
| refines D29, D35 | `isNearView(pos, reach)` is a square of half-side `reach` in x and y around the reference (height ignored), not a distance, and reads player objects from the player table rather than the activity centres, so an open dialog (D38) narrows `obj_updateActive` but not `isNearView` | Observed, executed | 0x1e77c0–0x1e78cc |
| refines D21 / O1 | The reaper works from a sample: `g_poolFreeCount` changes only on frames divisible by 64 and is forced to 100000 by teardown, so the reaper is off from a level load until the next such frame and then acts on a count up to 63 ticks old | Observed, executed | 0x14b9ac–0x14b9c8, 0x14c4b4 |

No patch is proposed: nothing found here is a defect that a one-word change would fix,
and none of it was run on a console.

## 11. Not done

- The order in which `Player` objects are constructed and linked after a load, and the
  second free-spot search for slots 1–3, were taken from `docs/issues/arena-entry.md`,
  not executed.
- Which run list each of the ~150 classes joins in its constructor (a table of the 238
  call sites of the three link functions by class) was not made; it decides the initial
  run order of a level together with record order.
- `world_drawObjects` and the always-draw list were not examined beyond the list
  operations.
- The record writer and the save filter list (`world_saveFilter` 0x15d9c8), and
  therefore what a saved level state does to creation order on a revisit.
- Whether any caller of `world_findObjectsByName` passes a limit below 2 (the search has
  no bound then).
