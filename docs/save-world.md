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

**Observed** (`save_storeLevelState` 0x217858–0x217910): insertion walks slots
0..9 in order, stops at the first empty first byte or exact `strcmp` match,
and sums the sizes of earlier slots for the body offset. A duplicate rewrites
its body using the *existing* size; it does not refresh the name or size from
the act row. A new slot copies the name and row size before the unsigned fit
check against 0x4bc78. On a fit failure the name and size remain, but the body
is not written. There is no eviction or rotation. When all ten are occupied,
the writer addresses the extra 0x18-byte gap at +0x16100 as slot 10. Its first
insertion writes a name, size and body; subsequent misses reuse that body's
offset and size without changing the ghost name. **Executed** in the new
`difftest_save_world.py`: eleven distinct `hub*` names occupied slots 0..10,
a twelfth wrote the slot-10 body again, and a duplicate of slot 4 retained its
original size. **Observed** (`save_levelStateStored` 0x2182fc–0x218340 and
`level_loadScriptAndObjects` 0x217a18–0x217a9c): lookup stops at the first
empty name and examines only slots 0..9. **Executed**: `save_levelStateStored`
reported false for the eleventh name and true for the tenth. The gap is thus
not a usable eleventh saved level. A retained entry whose body write failed is
also not a proven valid restore target.

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
| Opened chests | **Observed** (`Chest_saveState` 0x292284): exactly 12 bytes: `u32` model hide mask from +0x54, `u16` remaining gold from +0x4c, bytes +0x58 (bomb choice) and +0x59 (class variant), then `u32` opened from +0x84. `Chest_ctor` 0x2920c0–0x292254 seeds the gold/bomb/mask fields; `Chest_interact` 0x292a60–0x292aac refuses an already opened chest and sets +0x84 on opening. The item/potion descriptor properties are not serialized in these 12 bytes; spawned loot is separate world objects if eligible. **Executed:** 16 synthetic save/load cases per seed establish exact bytes, restored fields, and calls to 0x170838/0x170bc8 when opened and 0x14f5f0 in both opened states (`Chest_loadState` 0x2922cc). **Unknown:** load behavior for zero gold, the interactable flag, animation callback arguments and resulting state, and the class-definition argument; the probes do not establish these effects. `AutoChest_saveState` 0x23b06c emits a separate 12-byte hide mask, gold, two bytes and open word at +0xc8/+0xdc/+0xe4/+0xe5/+0xd8; `AutoChest_loadState` 0x23b0b4 and trap-fuse restoration remain unexecuted. A deleted chest has no eligible live record to save. |
| Killed enemies | **Observed** (`Creature_saveState` 0x116780–0x11691c): `u32` variant (+0xe8), `f32` current/max HP (+0x228/+0x22c), then, only when HP ≤ 0, `s32` interned death-animation string handle or −1; next is a `u32` bit field mapping five bits of +0xa8 to bits 0..4, +0x231 bit 0 to bit 5, and nonzero +0x312 to bit 6. Bit 6 appends one `s32` from +0x312. The +0xa8 masks are 0x1000000, 0x100000000, 0x400000, 0x800000 and 0x2000000000000. **Executed:** 24 alive/dead writer cases per seed cover these masks and the optional word; 12/16 bytes with no optional word. **Unknown:** `Creature_loadState` 0x116920–0x116bd0 has no committed load probe, so reconstructed HP, stopped motion, corpse animation arguments/state and reapplied flags remain unverified. Corpse flag 0x2000 can be thinned at 0x14e140; transient 0x4000 objects are omitted. A dead or removed enemy need not reappear from `objects.ob`; corpse presentation and timers are not a proven full live-tick snapshot. |
| Triggered scripts | **Observed** (`Trigger_saveState` 0x1ecf18): five bytes, `u32` at +0x64 then byte at +0x60. **Executed:** exact writer bytes on both seeds. **Unknown:** `Trigger_loadState` 0x1ecef4 has no committed load probe, so restoration of these fields remains unverified. Quest variables are in the main save, via `save_build` 0x221cf0 and `save_load` 0x221d60. A deleted one-use object is represented by absence. `script_setCurrent` 0x1ed650 loads a new machine and `preStart`/`start` run again at 0x217acc/0x217bac. The instruction pointer, call stack, deferred queue and active dialog are not a level-state section. **Inferred:** scripts re-derive effects from variables and object state; an in-flight script cannot resume at its old instruction. |
| Doors and gates | **Observed / Executed** writer bytes: `DoorSwing_saveState` 0x28ae3c emits 8 bytes (`u16` angle +0x50, sign-extended `s16` direction +0x58, `f32` speed +0x54); `DoorSecret_saveState` 0x28b1a0 emits one open byte +0x58; `RollDoor_saveState` 0x28dee8 emits 16 bytes (`s32` open +0x5a, `s32` piece index +0x4c, `f32` speed +0x50, `s32` counter +0x54); `JumpGate_saveState` 0x27d974 emits two bytes +0x4d/+0x4e. **Unknown:** no committed load probe covers `DoorSwing_loadState` 0x28ae74, `DoorSecret_loadState` 0x28b1b8, `RollDoor_loadState` 0x28df24 or `JumpGate_loadState` 0x27d998. Motion, piece collision, pose, light and animation reconstruction, including callback arguments/state, remain unverified. The destination list is separately in the save header (`jumpgate_saveDestinations` 0x27dcf4 / load 0x27dd30). Moving-piece geometry itself comes from `.world`. |
| Dropped items | **Observed** (`ItemProp_saveState` 0x1596a4): a 0x48-byte item record from +0x148, with its first word temporarily converted from a definition pointer to its table index by `item_encodeDefinitionIndex` 0x107ea4, followed by the variable `Prop_saveState` 0x158d8c suffix. Save decodes the in-memory item pointer again before returning. **Executed:** 16 synthetic save/load cases per seed assert the prefix, original pointer restoration after save, decoded 0x48-byte item in the loaded object, Prop-load call address and transform-call address in `ItemProp_loadState` 0x159758. The input item bytes are random, so both state-bit branches are not covered. **Unknown:** load flag changes for either state-bit branch, `Prop_loadState` 0x158f04 effects, and the arguments and resulting transform of `mat34_setPosRotZ` 0x163b30. The Prop suffix has three interned string handles, a compact one-byte power-of-two mask or a 13-byte nonpower mask (`s32` −1, `u64` mask, zero byte), three signed quaternion bytes, a signed quaternion `s16` scalar and three signed coordinate `s16`s (0x158d8c–0x158ef0); 24/36 bytes in the two executed writer mask cases. The strings and quaternion depend on the surrounding world string table and live matrix. Picked-up items delete the world object (`itemprop_tryPickup` 0x154dbc). **Unknown:** exact retention of every temporary drop under thinning/flag policies. |

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
2. **Define the native world-state envelope.** Key by qualified level name and version the native schema. Preserve current player/quest/position fields; add per-level object records, decals and explored map. Choose an explicit capacity and failure policy. The original's ten readable slots, write-only overflow gap, retained failed-fit entry and 0x4bc78-byte limit cannot serve as an all-level guarantee.
3. **Implement the object registry and save policy.** Match stable class/property/pose identity, transient and filtered classes, deletion, save ordering and overflow behavior. Port the verified serialized layouts for Chest, ItemProp plus Prop suffix, Creature, Trigger and door/gate writers. Keep the original string table and definition-index semantics explicit in the native schema. Treat Chest, AutoChest, Creature, Trigger, ItemProp/Prop and door/gate load effects as Unknown until targeted executable probes cover their branches, callback arguments and resulting state; refuse reconstruction that depends on those effects rather than fabricating it.
4. **Restore in original order.** Restore saved player spawn poses from the main save, load the actual level and a fresh script machine, consume and clear the saved spawn rank before `preStart`, then unpack the explored map, construct saved objects and their state, load decals, construct filtered `objects.ob` records, and run `start`. Rebuild moving-piece collision and doors only after their load effects are verified against the original with `.world` present.
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

**Executed 2026-10-23, round 2:** the extended save-world difftest adds 16
Chest save/load, 16 ItemProp save/load, six other slot-9 writers, two Prop
suffix mask forms, 24 Creature alive/dead flag combinations, and directory
insert/read/overflow/duplicate probes per seed. The Prop and ItemProp probes
use recording callbacks for string interning, matrix math or the nested Prop
call; they establish the addressed byte boundary and calls, not a full
disc-backed item or rendered object. Class load callbacks with world services
remain isolated, and real memory-card or native integrated save/load parity
is still Unknown.

**Executed 2026-10-23, SW2-1 audit correction:** reran the save-world difftest
on seeds 20973 and 7, the separate save difftest (26/26 properties), and the
full Python unit suite (652/652) with `PYTHONDONTWRITEBYTECODE=1`; all passed.
The class rows and port list above now keep unprobed load effects Unknown.
These reruns do not add zero-gold, item state-bit, callback-argument, or
world-service coverage.
