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
| Opened chests | **Observed** (`Chest_saveState` 0x292284): exactly 12 bytes: `u32` model hide mask from +0x54, `u16` remaining gold from +0x4c, bytes +0x58 (bomb choice) and +0x59 (class variant), then `u32` opened from +0x84. `Chest_ctor` 0x2920c0–0x292254 seeds the gold/bomb/mask fields; `Chest_interact` 0x292a60–0x292aac refuses an already opened chest and sets +0x84 on opening. The item/potion descriptor properties are not serialized in these 12 bytes; spawned loot is separate world objects if eligible. **Executed:** 16 synthetic save/load cases per seed establish exact bytes, restored fields, and calls to 0x170838/0x170bc8 when opened and 0x14f5f0 in both opened states (`Chest_loadState` 0x2922cc). **Executed elsewhere (2026-10-27):** `t3/research-death-reload` `24bd3ba` `docs/death-reload-objects.md` line 24 (OBJ2-3) runs the original constructor, cache setter 0x14f5f0 and animation calls without stubs for gold 0, 1, 32767, 32768 and 65535: an opened chest with signed gold ≤ 0 clears object flag 0x100000, positive gold keeps it, and the clip ends at its last frame with flags 0x204. **Observed** (0x29236c–0x292380): the class-definition argument is the word at 0x501698 + 4 × variant byte. `AutoChest_saveState` 0x23b06c emits a separate 12-byte hide mask, gold, two bytes and open word at +0xc8/+0xdc/+0xe4/+0xe5/+0xd8. `AutoChest_loadState` 0x23b0b4 is executed in the same OBJ2-3 row; it stores the mask with a 64-bit `sd`, so a mask with bit 31 set sign-extends into +0xcc. Trap-fuse restoration remains **Unknown**. A deleted chest has no eligible live record to save. |
| Killed enemies | **Observed** (`Creature_saveState` 0x116780–0x11691c): `u32` variant (+0xe8), `f32` current/max HP (+0x228/+0x22c), then, only when HP ≤ 0, `s32` interned death-animation string handle or −1; next is a `u32` bit field mapping five bits of +0xa8 to bits 0..4, +0x231 bit 0 to bit 5, and nonzero +0x312 to bit 6. Bit 6 appends one `s32` from +0x312. The +0xa8 masks are 0x1000000, 0x100000000, 0x400000, 0x800000 and 0x2000000000000. **Executed:** 24 alive/dead writer cases per seed cover these masks and the optional word; 12/16 bytes with no optional word. **Executed (round 3, this branch):** `Creature_loadState` 0x116920; see "Creature and jump-gate load effects" below. Corpse flag 0x2000 can be thinned at 0x14e140; transient 0x4000 objects are omitted. A dead or removed enemy need not reappear from `objects.ob`; corpse presentation and timers are not a proven full live-tick snapshot. |
| Triggered scripts | **Observed** (`Trigger_saveState` 0x1ecf18): five bytes, `u32` at +0x64 then byte at +0x60. **Executed:** exact writer bytes on both seeds. **Executed elsewhere:** `death-reload-objects.md` line 23 (OBJ2-2, `24bd3ba`): `Trigger_loadState` 0x1ecef4 consumes five bytes, restores +0x64/+0x60, keeps the constructor's grid and bucket membership, and neither runs the trigger's script nor moves it to the active list. Quest variables are in the main save, via `save_build` 0x221cf0 and `save_load` 0x221d60. A deleted one-use object is represented by absence. `script_setCurrent` 0x1ed650 loads a new machine and `preStart`/`start` run again at 0x217acc/0x217bac. The instruction pointer, call stack, deferred queue and active dialog are not a level-state section. **Inferred:** scripts re-derive effects from variables and object state; an in-flight script cannot resume at its old instruction. |
| Doors and gates | **Observed / Executed** writer bytes: `DoorSwing_saveState` 0x28ae3c emits 8 bytes (`u16` angle +0x50, sign-extended `s16` direction +0x58, `f32` speed +0x54); `DoorSecret_saveState` 0x28b1a0 emits one open byte +0x58; `RollDoor_saveState` 0x28dee8 emits 16 bytes (`s32` open +0x5a, `s32` piece index +0x4c, `f32` speed +0x50, `s32` counter +0x54); `JumpGate_saveState` 0x27d974 emits two bytes +0x4d/+0x4e. **Executed elsewhere:** `death-reload-objects.md` line 26 (OBJ2-5, `24bd3ba`) runs the three door loaders with original collision, height, pose and run-list services: open swing and rolling doors join the active list, a secret door's open surface drops by 300 units (−1184 quarter units from 16), a rolling door clears terrain bit 2 and restores the piece height. Line 27 (OBJ2-6) does the same for the non-portal gate 0x23ceb8. Door derived constructors were supplied there, not run. **Executed (round 3, this branch):** `JumpGate_loadState` 0x27d998; see below. Lights remain **Unknown**. The destination list is separately in the save header (`jumpgate_saveDestinations` 0x27dcf4 / load 0x27dd30). Moving-piece geometry itself comes from `.world`. |
| Dropped items | **Observed** (`ItemProp_saveState` 0x1596a4): a 0x48-byte item record from +0x148, with its first word temporarily converted from a definition pointer to its table index by `item_encodeDefinitionIndex` 0x107ea4, followed by the variable `Prop_saveState` 0x158d8c suffix. Save decodes the in-memory item pointer again before returning. **Executed:** 16 synthetic save/load cases per seed assert the prefix, original pointer restoration after save, decoded 0x48-byte item in the loaded object, Prop-load call address and transform-call address in `ItemProp_loadState` 0x159758. The input item bytes are random, so both state-bit branches are not covered. **Executed elsewhere:** `death-reload-objects.md` line 25 (OBJ2-4, `24bd3ba`) runs the original ItemProp alternate constructor, `Prop_loadState` 0x158f04, string-table resolution and 0x163b30 for both bit-39 branches and masks 8/10. The final translation comes from the base pose, not the suffix's coordinates. The primary factory route stops at syscall 124 there, so it remains **Unknown**. The Prop suffix has three interned string handles, a compact one-byte power-of-two mask or a 13-byte nonpower mask (`s32` −1, `u64` mask, zero byte), three signed quaternion bytes, a signed quaternion `s16` scalar and three signed coordinate `s16`s (0x158d8c–0x158ef0); 24/36 bytes in the two executed writer mask cases. The strings and quaternion depend on the surrounding world string table and live matrix. Picked-up items delete the world object (`itemprop_tryPickup` 0x154dbc). **Unknown:** exact retention of every temporary drop under thinning/flag policies. |

## Creature and jump-gate load effects (round 3, 2026-11-09)

**Executed** in `tools/difftest_save_world_travel.py`, which runs the original
bodies on synthetic objects and replaces only the callees listed in its
`STUBS` table with recording stubs. Those stubs are printed on every run.

`Creature_loadState` 0x116920, 48 cases per seed, alive and dead:

- It stores the variant word at +0xe8, then calls the virtual entry at
  vtable +0xe8 with the object. HP at +0x228 becomes max HP at +0x22c times
  the saved fraction (`mul.s` 0x116964). The saved value is a fraction, not
  absolute HP.
- HP ≤ 0 (`c.ole.s` 0x11698c) takes the corpse branch. It stores 20 at
  +0x232, ORs 0x2009 into the object flags, and calls `obj_stopRunning`
  0x14f290. The saved handle goes through the original `loadStr_ptr` 0x14f688,
  which reads the record string table at 0x5f8704; −1 gives no name. The
  original `strcmp` 0x3b8534 then searches the clip table at +0x24, starting
  at entry 1. On a match it runs `anim_clear`, `anim_push(+0x114, clip, 4)`
  and `anim_jumpTopToEnd(+0x114)`, sets bit 0x80 at +0x11a, and calls the
  virtual entry at vtable +0xe0 with argument 1. A missing name or handle −1
  skips the clip and that call.
- Still on the corpse branch, the original typeinfo getters
  `Orc_typeinfo` 0x3c4658 or `Creature_typeinfo` 0x3c2608 run, then
  `rtti_typeInfoEquals` 0x3b1250. Only an Orc gets byte 0x46 at +0x28.
- The packed bits are ORed into the 64-bit word at +0xa8. Loading never
  clears a bit that the constructor set. Bit 5 replaces bit 0 of +0x231.
- Bit 6 always consumes one more word. It takes effect only when +0x312 is
  not −1, object flag 0x20 is set and object flag 0x40 is clear. Then it
  clears the low byte of +0x310, stores the word's low half at +0x312, calls
  `handle_clear` 0x1a1698 on +0x234, and zeroes +0x234. Otherwise the word is
  skipped.
- It returns 12 (alive) or 16 (dead) bytes, plus 4 when bit 6 is set. This
  matches the writer in the table above.

`JumpGate_loadState` 0x27d998, 12 cases per seed: it restores bytes +0x4d and
+0x4e and returns 2. When +0x4e is nonzero, the original grid relink 0x148bc8
unlinks the node at +0x100 and pushes it onto the head of a 90 × 90 cell list
at 0x5d34d8. The cell index is (x + 0x2d00) >> 8 and (y + 0x2d00) >> 8, using
the floats at +0x130/+0x134; a position outside the grid goes to the list at
0x5db368. Then `res_find(+0x90, "jumpgate_idle.anm")` and
`anim_push(+0xd8, clip, 3)` are called. In both cases
`obj_runEveryFrame` 0x14f248 is called. **Unknown:** what the virtual hooks,
`obj_stopRunning`, `handle_clear` and the animation calls do to real objects
here. They are recording stubs in this probe; the death-reload branch runs
the animation and run-list services for other classes only. Destination
lists live in the save header (`jumpgate_saveDestinations` 0x27dcf4).

## What a level remembers across travel (round 3)

**Executed** as one composed sequence in the same file (`check_travel`).
The original `save_storeLevelState` 0x21777c, `save_writeLevelState` 0x218600,
`level_getQualifiedName` 0x1ec0f0, `save_levelStateStored` 0x2182d4,
`save_clearBuffer` 0x21f144 and `level_loadScriptAndObjects` 0x217978 all run
on one memory image. The act table is the executable's own static table at
0x4f8e10/0x4f8e48. Recording stubs supply the world, decal and automap
writers, plus the loader's file, script and object callees. Each departure
writes visit-tagged sentinel bytes. When a departure was not stored, nothing
was written.

| Event | Original result |
|---|---|
| Leave `hub`, then a level of act 2 | Two directory keys, with row sizes 15000 and the level's row. Bodies are adjacent at 0x8ab698. |
| Return to `hub` | The loader copies the *latest departure* body's world and decal blobs into 0x88d480, unpacks that visit's explored map, constructs saved records, then loads `objects.ob` with `filterOnly=1`. |
| Leave `hub` again | Slot 0 is rewritten in place with its old size. The other level's body bytes are unchanged, and returning there reads them. |
| Enter a level never left | `save_levelStateStored` is 0. Every `objects.ob` record is constructed (`filterOnly=0`): a fresh level. |
| Card state 4 at 0x88d3a0, or level flag 0x800 at 0x44fe08 | Neither store changes any byte of the 0x4bc78 image. |
| Leave `hub_west` | A new key with row 0's 15000 bytes. `hub_west` and `hub` are different keys, so each hub sub-area keeps its own state. |
| Act change: `save_clearBuffer(0)` | Only directory slot 0 survives, with its name, its first 15000 bytes in place, and its size set to act 0 row 0's 15000. Every other key is gone. `hub` still restores; the act's other levels and `hub_west` load fresh. Word 0x4f9234 is cleared. With block byte 0x4f8f2a set, the image is untouched. |
| Slot 0 is not a hub | `blood1` stored first keeps its name through the clear. Its size becomes 15000, not its row's 25000, while `hub` is dropped. |

**Observed / Executed (act table, read at run time; counts only):** all 13
acts have `hub` as row 0 with 15000 bytes, and act row counts range from 1 to
10. The largest act's rows total 153000 of the 220000 bytes after +0x16118.
**Inferred:** one act's own rows fit both the space and the ten readable
slots. Each extra `hub*` sub-area costs another 15000-byte slot, though. An
act with ten rows plus one visited hub sub-area reaches the write-only
eleventh slot (lines 28–45 above) if every row is departed.

**Cross-reference, not redone:** the departure call and its skips are
`t3/research-exits-r3` `e86f3de` `docs/exits-r4-travel.md` lines 25–43 and
51–56. The current level is not stored when its name is empty or `deathTask`
is running. The act-change block is lines 66–72: it runs only when the act
changed, card latch 0x4f8f28 is clear and no death task runs. It then calls
`save_clearBuffer(0)`, `jumpgate_resetDestinations`, `quest_clearAll` and
`vars_clearAll`, and removes flag-39 items. Line 111: a lookup miss on
arrival stores 300 in the idle-voice word 0x506054. A card load does not
touch the directory (`t3/research-save-screen` `c8895e2`
`docs/save-screen.md` lines 273–278). It does keep card state 4 and latch 1
until the live name matches the pending one (lines 281–286). **Inferred**
from those two notes plus the rows above: the level change after a card
load stores nothing over the loaded directory and does not clear it. The
loaded directory then drives every later revisit, not only the first level.

What is **not** carried per level, reset on every load: the script machine,
its stack and dialog, and deferred calls (`script_setCurrent` 0x1ed650,
`save_load` clearing at 0x1eda08). Any object class accepted by
`world_saveFilter` 0x15d9c8 is also rebuilt from `objects.ob`. Quest
variables, the jump-gate list, players and spawn poses live in the save
header, not the level body (lines 69–73 above).

## Checkpoints and the death reload (round 3)

**Executed** `save_game` 0x218128 (names.tsv; script `saveCheckPoint`,
`Savepoint_run` and the daemon), 20 cases per seed. The original act search,
qualified name, `strcmp` and `save_levelStateStored` run against the
executable's act table. Messages, `task_isRunning`, `save_build` and
`game_sendCharacterToLobby` are recording stubs.

1. It needs one counted living player. A record at 0x4d8af0 + slot × 0x4c30
   needs an object pointer at +0x43d8, object flag 8 clear, and HP at +0xac
   above 0. Otherwise nothing happens.
2. If act 0x88d3d4 is −1, or the `missionmenurun` task is running, it calls
   `save_build(a0, 0)` with no message.
3. If no act row is a prefix of the name, it shows `CheckPoint` and returns
   **without** building. The level's state is not stored.
4. For the exact row-0 name (`hub`; `hub_west` is not row 0) with no stored
   entry, it builds silently. Every other found level, and a stored `hub`,
   first gets a HUD message from 0x1d92a0 with arguments (text, 0xb4, −1, 0). The message is `CheckPoint` when a1 is 0,
   otherwise the level title from 0x22233c.
5. After any build, word 0x4f8f30 is cleared and
   `game_sendCharacterToLobby(−1)` 0x1eb5c8 is called.

`save_build` stores the current level into the same directory
(`t3/research-saves` `docs/save-format.md` lines 55–58). The checkpoint is
therefore the header plus the directory as of that moment, all in
`g_saveBuffer` 0x895580 (directory at +0x16010 = 0x8ab590).

**Cross-reference, not redone:** `t3/research-death-reload`
`docs/death-reload-sequence.md` lines 15–67: `deathTask` calls `save_reload`,
which calls `save_load` on that buffer. Lines 69–88: the following
`mainloop_loadRequestedWorld` finds the death task and skips the store, and
the buffer, directory and saved-world bytes stay identical. Later rounds of
that note (lines 116–468) still stop before `world_loadRecords` and
`Player_ctor`.

**Inferred** from the above: departures after a checkpoint write into the
same buffer and are not undone. A death reload therefore restores the
checkpoint's header (players, quests, spawn and level) together with each
level's *latest* stored body. A level left after the checkpoint comes back
in its departure state; the level being played when the party died comes
back in its last stored state, because the death skips its store. This is
composed from separate probes, and no continuous death-to-playable run
exists (the death-reload refusal stands).

## Client-implementable list (save-world)

Each item cites the evidence above. Items marked *refuse* must stay refusals
until the listed **Unknown** is probed.

1. Directory: qualified-name keys (`base` or `base_sub`). `hub*` names take
   act row 0's size; others take the first current-act row they start with,
   and no row means no store. A new key appends; an existing key keeps its
   size. Readers stop at the first empty name or after 10 entries (lines
   28–45; exits-r3 lines 25–43).
2. Departure store when leaving a level, unless the name is empty, a death
   task is running, card state is 4, or level flag 0x800 is set (travel
   table; exits-r3 lines 51–56).
3. Body framing: two length-framed blobs and a 0x16c8-byte explored map
   (lines 47–55).
4. Arrival: a hit loads saved records, then filtered `objects.ob`; a miss
   loads all `objects.ob` and sets idle voice 300. Script `preStart`/`start`
   always run on a fresh machine (lines 81–92; travel table; exits-r3 line
   111).
5. Act change with the latch clear and no death task: keep only slot 0, its
   name, and its first 15000 bytes, sized 15000. Drop every other level, and
   clear quests, variables and the jump-gate list (travel table; exits-r3
   lines 66–72).
6. Card load: take the directory as loaded, with no departure store and no
   clear during that level change (save-screen lines 273–286).
7. Checkpoint decision tree and silent first-hub build, as in the
   `save_game` steps above.
8. Class state, verified load effects: Chest, AutoChest (64-bit mask
   store), Trigger, ItemProp, Prop and the three doors (death-reload OBJ2-2
   to OBJ2-5), gate (OBJ2-6), Creature HP fraction, corpse flags, clip
   search, flag OR and the +0x312 rule, and JumpGate bytes and grid relink
   (this section).
9. *Refuse*: Creature and JumpGate virtual hooks, real animation and
   run-list effects (stubbed here); trap fuses; lights; ItemProp primary
   factory; thinning under budget overflow (lines 57–65); and death reload
   to a playable level.

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
3. **Implement the object registry and save policy.** Match stable class/property/pose identity, transient and filtered classes, deletion, save ordering and overflow behavior. Port the verified serialized layouts for Chest, ItemProp plus Prop suffix, Creature, Trigger and door/gate writers. Keep the original string table and definition-index semantics explicit in the native schema. Port the load effects verified in `death-reload-objects.md` OBJ2-2 to OBJ2-6 and the Creature/JumpGate section above. Refuse reconstruction that depends on the stubbed virtual hooks, trap fuses, lights or the ItemProp primary factory rather than fabricating it.
4. **Restore in original order.** Restore saved player spawn poses from the main save, load the actual level and a fresh script machine, consume and clear the saved spawn rank before `preStart`, then unpack the explored map, construct saved objects and their state, load decals, construct filtered `objects.ob` records, and run `start`. Rebuild moving-piece collision and doors only after their load effects are verified against the original with `.world` present.
4a. **Apply the travel rules** in "What a level remembers across travel": store on departure with the four skips, keep only slot 0 on an act change, and keep a card-loaded directory as loaded.
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

**Executed 2026-11-09, round 3, on the Mac mini** (`PYTHONDONTWRITEBYTECODE=1`, pinned
executable):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_save_world_travel.py /path/to/SLUS_209.73 --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_save_world_travel.py /path/to/SLUS_209.73 --seed 7
```

Each seed covers 48 Creature load cases (alive, dead, death clip found,
missing and −1, Orc and non-Orc, +0x312 word applied and skipped), 12
JumpGate loads, 20 `save_game` cases (silent build, message and build,
message only, nothing) and a 21-step travel sequence. Each run ends by
printing its stub list. Two deliberate reference mutations (a swapped
Creature flag mask, and swapped `save_game` message choice) each failed the
run before these passes. The retained logs are under the mini worktree's
`local/sw3-logs/`, untracked. `work/cursor-report.md` has the exact counts.
