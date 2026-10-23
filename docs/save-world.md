# World state across save and level reload (SLUS-20973 US v2.00)

This is a research contract for the original, not the native client's OCNSAVE
format. **Observed** means read at the listed executable address. **Executed**
means `tools/ee_emu.py` ran that function with synthetic input. **Inferred**
states a consequence of those observations. **Unknown** marks a missing proof.
The executable pin is SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
See also `docs/audio-save.md`, `docs/objects.md`, `docs/formats/world.md`,
and the separate research in `t3/research-saves`, `t3/research-levels`, and
`t3/research-script`.

## What a saved level contains

**Observed** (`save_build` 0x221914, `save_storeLevelState` 0x21777c,
`save_writeLevelState` 0x218600): the 0x4bc78-byte save buffer has a ten-entry
directory at +0x16010 and level bodies at +0x16118. Keys are qualified level
names; the act table supplies each reserved body size. The current level is
stored when building a checkpoint or card image, and the old level is stored
before a normal transition (`mainloop_loadRequestedWorld` 0x320edc). State is
not stored while card state is 4 or the level flag 0x800 is set. Ordinary level
names require a match in the current act's list. **Executed** in the prior
`t3/research-saves` save difftest: a qualified name beginning `hub` uses act row
0 even when the name is absent from that list (`hub_west` stored under row 0
named `town`; `save_storeLevelState` 0x21777c). The finite directory and total buffer
mean that the original does **not** promise state for an unlimited set of levels.

**Observed** (0x218620–0x218690): a body has `u32 world_length`, four unused
bytes, the world record blob, `u32 decal_length`, four unused bytes, the decal
blob, then 0x16c8 bytes of explored automap. The unused words and unused tail
retain old buffer bytes; the function does not clear them. The world writer receives
`reserved_size - 0x16c8 - 0x18` as its budget. **Executed**:
`difftest_save_world.py` compared 16 varying synthetic layouts per seed with
the original writer. The earlier `t3/research-saves` difftest also compared
whole empty-object save images; its `docs/save-format.md` has the full header,
player, quest and directory layout.

**Observed** (`world_writeRecords` 0x14e140, `world_saveState` 0x14e5c8,
`obj_writeRecord` 0x14df50): the world blob uses the level object's record
format plus slot-9 state bytes. It walks the live grid and off-grid lists;
objects marked 0x4000 or accepted by the save filter are omitted. When the
record or string budgets overflow, the writer retries with increasing
thinning of 0x1000/0x2000 objects. Thus a saved world is a bounded snapshot
of surviving eligible objects, not an event log or a byte image of the entire
simulation. **Unknown:** complete per-class fidelity under thinning and the
native client's equivalent capacity policy.

## Reload sequence and the division of ownership

**Observed** (`save_load` 0x221d60): the card reader restores header, camera,
jump-gate destination list, players and spawn poses, quest variables, act,
difficulty and time, then requests the saved level. It does not consume the
per-level body. It clears deferred script calls at 0x1eda08. The loaded-from-save
byte 0x8e1ad6 suppresses start-marker replacement of the saved spawn poses.

**Observed** (`game_loadLevel` 0x1e55c0, `gob_loadAll` 0x1737d8,
`world_fixup` 0x181d30, `world_prepare` 0x182360): the target `.GOB` and
`.world` are loaded anew. Geometry chunks, terrain cells and elements, moving
pieces, water, paths, and texture-cell references come from level data. The
save body contains no `.world` geometry or terrain surface list.

**Observed** (`level_loadScriptAndObjects` 0x217978–0x217bd8): after the level
lump and a fresh `script.scr` machine are selected, `preStart` runs. With a
matching directory entry, the loader copies the world and decal blobs into
scratch, unpacks the explored map, constructs saved object records with
`world_loadRecords(blob, 0)`, and loads decals. It then passes `objects.ob` to
`world_loadRecords` with `filterOnly=1`; without a saved entry the flag is 0.
Finally `start` runs. The rank byte from a card load is consumed and cleared
before `preStart`. **Executed:** `difftest_save_world.py` observes rank 3 and
the cleared loaded byte inside the original `preStart` callback (or the first
load callback when scripts are skipped), and compares the original's call
order, record selection and scratch bytes for 32 synthetic cases per
seed, including no saved entry and the script-skip byte.

**Observed** (`world_loadRecords` 0x14e808): saved records are constructed by
the factory, then slot 8 loads each record's state. On a saved level, the
`objects.ob` pass constructs only classes accepted by `world_saveFilter`
0x15d9c8 (lights, fire, `Line`, `Blocker`, `customVars`, route points and
other filtered classes). This prevents deleted chests or killed creatures
from respawning merely because they remain in `objects.ob`. The separate
`tools/ref_objects.py` / `difftest_objects.py` covers record ordering and
factory callbacks. **Inferred:** absent eligible records stay absent on a
revisit, provided the saved entry was retained and the class is not filtered.

## State examples and script limits

| Case | Original treatment and evidence |
|---|---|
| Opened chests | **Observed:** the vtable slots identify `Chest_saveState` 0x292284 and `Chest_loadState` 0x2922cc (see `symbols/monsters.tsv`). **Unknown:** the Chest payload size, fields, load effects and lid-animation behavior need an addressed body trace or class-state execution. `AutoChest_saveState` 0x23b06c / load 0x23b0b4 has a separately documented 12-byte hide mask, gold and state (`docs/monsters-2.md` 9.2); its trap fuse timer is outside those bytes. A deleted chest has no eligible live record to save. **Inferred:** it stays absent when the level's saved entry is used. |
| Killed enemies | **Observed:** `Creature_saveState` 0x116780 writes variant, HP fraction, selected flags and dead animation; `Creature_loadState` 0x116920 puts a dead record into corpse state. Corpse flag 0x2000 can be thinned at 0x14e140; transient 0x4000 objects are omitted. **Inferred:** a dead or removed enemy need not reappear from `objects.ob`, but corpse presentation and timers are not a full live-tick snapshot. |
| Triggered scripts | **Observed:** `Trigger_saveState` 0x1ecf18 / load 0x1ecef4 saves five bytes (delay and inside flag). Quest variables are in the main save, via `save_build` 0x221cf0 and `save_load` 0x221d60. A deleted one-use object is represented by absence. `script_setCurrent` 0x1ed650 loads a new machine and `preStart`/`start` run again at 0x217acc/0x217bac. The instruction pointer, call stack, deferred queue and active dialog are not a level-state section. **Inferred:** scripts re-derive effects from variables and object state; an in-flight script cannot resume at its old instruction. |
| Doors and gates | **Observed:** `DoorSwing_saveState` 0x28ae3c writes angle, direction and speed; its load 0x28ae74 re-enables motion. `DoorSecret_saveState` 0x28b1a0 writes the open byte and load 0x28b1b8 moves its piece to the open pose. `RollDoor_saveState` 0x28dee8 writes its open state, piece index, speed and counter; load 0x28df24 rebuilds motion/collision. `JumpGate_saveState` 0x27d974 saves two object bytes; the destination list is separately in the save header (`jumpgate_saveDestinations` 0x27dcf4 / load 0x27dd30). The moving-piece geometry itself is from `.world`. |
| Dropped items | **Observed:** the vtable slots identify `ItemProp_saveState` 0x1596a4 and `ItemProp_loadState` 0x159758 (see `symbols/objects.tsv`). **Unknown:** the ItemProp payload size, encoded definition, delegation to Prop, decode and transform effects need an addressed body trace or class-state execution. Picked-up items delete the world object (`itemprop_tryPickup` 0x154dbc), so the saved eligible-object pass does not recreate that drop. **Unknown:** exact retention of every temporary drop under thinning/flag policies. |

## Multi-surface terrain on reload

**Observed** (`docs/formats/world.md`, executable 0x181d30, 0x183248,
0x183820): the `.world` file has a terrain grid; each cell holds a list of
terrain-element indices. An element points to a height field with position,
rotation and flags. `terrain_collectElements` collects multiple overlapping
elements, and `terrain_height` chooses the highest sample in the query disc.
The loader relocates the whole grid and all elements from the level file each
time. **Executed:** `difftest_world.py --generated-only --quick` compared the
original terrain queries with `ref_world.py` on a generated level containing
40 placed elements, including overlap, rotation and moving pieces, on both
seeds. This tests the terrain query, not a rendered scene or card I/O.

**Observed in the current native play-enemies worktree:**
`gdextension/src/session_controller.cpp` `present_terrain` refuses more than
256 elements and then refuses any scene other than one plain element. Its
`present_geometry` has a separate 16,384-static-surface / four-million-triangle
cap. The playthrough report's terrain-surface refusal is therefore a scene
presentation limit; changing save bytes cannot make that preview accept a
multi-element level. The original's terrain elements and render surfaces are
also distinct concepts. **Unknown:** whether a complete native scene can load,
display, save and revisit every shipped level with full object fidelity.

## Ordered native port list

1. **Load the actual level data first.** Decode `.GOB`/`.lmp` and `.world`, retain every terrain cell, height-field element, chunk, piece and texture reference, then remove the one-plain-element presentation refusal through a measured multi-element renderer. Keep simulation terrain and rendered surfaces separate.
2. **Define the native world-state envelope.** Key by qualified level name and version the native schema. Preserve current player/quest/position fields; add per-level object records, decals and explored map. Do not silently inherit the original ten-slot / 0x4bc78-byte capacity as an all-level guarantee.
3. **Implement the object registry and save policy.** Match stable class/property/pose identity, transient and filtered classes, deletion, save ordering and overflow behavior. Export only class states with verified slot-9/slot-8 payloads and load effects; the Chest and ItemProp slot identities alone do not establish their payloads. Refuse unknown classes rather than fabricating state.
4. **Restore in original order.** Restore saved player spawn poses from the main save, load the actual level and a fresh script machine, consume and clear the saved spawn rank before `preStart`, then unpack the explored map, construct saved objects and their state, load decals, construct filtered `objects.ob` records, and run `start`. Rebuild moving-piece collision and doors through their object load callbacks after `.world` exists.
5. **Port persistent script effects.** Quest variables, trigger delay/inside flag, one-use deletion, jump-gate list and class-specific counters belong to their documented stores. Treat the interpreter PC, stack, pending dialog and deferred work as fresh on reload unless a separately evidenced native feature requires a different policy.
6. **Validate at real-level scale.** For a first visit, a checkpoint, a cross-level revisit and a card load, compare object counts/identities and states, map exploration, piece collision, terrain height and visible geometry. Include a multi-element level and capacity cases; record explicit refusals for missing constructors or unsupported state. Only then claim every-real-level save/load.

## Reproduction and limits

From this worktree, with a private copy of the pinned executable passed as an
argument:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_save_world.py /path/to/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_save_world.py /path/to/SLUS_209.73 --seed 7
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_world.py /path/to/SLUS_209.73 --quick --generated-only --no-alt --seed 20973 -k terrain_height
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_world.py /path/to/SLUS_209.73 --quick --generated-only --no-alt --seed 7 -k terrain_height
```

These are isolated function tests with synthetic memory. They do not run the
memory-card hardware path, a shipped level's full load, or native gameplay.

**Executed 2026-10-23:** both seeds passed 16 writer and 32 reload-order
cases each; generated 40-element terrain passed 300 `terrain_height`, 300
`terrain_heightBelow` and 150 `terrain_heightAtPoint` cases per seed. The
existing record-loader difftest passed 54 steps / 18 loads on seed 20973 and
53 steps / 17 loads on seed 7. The level `.world` selection difftest passed
10 cases per seed. The earlier save-format difftest passed 26 properties on
the pinned executable. The complete local Python unit suite passed 652 tests.
