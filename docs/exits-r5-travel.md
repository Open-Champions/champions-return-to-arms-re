# Level-to-level travel, round five: arrival

Verified 2026-11-09 against the read-only US v2.00 executable, SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`, and a
read-only copy of the disc's files (`BG/DATA`, 925 files). Labels are those of
`docs/exits-r4-travel.md`: **Observed** is addressed original code,
**Executed** means that body ran in `tools/ee_emu.py` on the stated inputs and
matched `tools/ref_exit_arrival.py`, **Inferred** composes those, **Unknown**
was not run. This is not a Play! session, and no client refusal is removed.

Round four (`docs/exits-r4-travel.md`) covered the departure side of
`mainloop_loadRequestedWorld` `0x320edc`. It left the disc load, free-spot
geometry, the object writer's bytes, and the entry scripts unknown. This round
runs each of those in the original code.

## What is supplied

Everything below runs original code except these, listed in the probe's
docstring (`tools/difftest_exit_arrival.py:1-20`) and counted in its `stubs`
field:

- libcdvd: `sceCdRead` `0x362600` serves 2048-byte sectors from the disc copy
  at synthetic sector numbers (`tools/difftest_exit_arrival.py:71-96`).
  `0x3618b0` and `0x362938` return 0, which `lump_pollAsync` `0x172ca8`
  takes as "done" and "no error" (`0x172cfc–0x172d88`).
- `gfx_waitVsync` `0x19d028` and `FlushCache` `0x352c60`. The first is a frame
  wait on a semaphore. The second's caller at `0x17382c` does not read v0, and
  the interpreter has no cache.
- `world_loadRecords` `0x14e808`. Its arguments are recorded. The object
  factory and constructors it would run are not.
- The level script's built-in handlers from the table at `0x403370`: 189
  distinct addresses other than `callScript` `0x143158`, which runs original.
  Each records its argument cells and returns a seeded value
  (`tools/difftest_exit_arrival.py:545-603`).
- Deci2 function `0x10` (the `dbg_printf` path) uses `EE.install_deci2_kputs`,
  cherry-picked unchanged from `t3/research-death-reload` (commits `20444735`
  and `9a567840` here). No other syscall is modelled.

The probe's own set-up runs original `mem_initHeap` `0x150598` on a
0x480000-byte region it chooses, and original `handle_initPool` `0x1a17d0`.
`engine_init` calls that one at `0x19d710`
(`tools/difftest_exit_arrival.py:156-157`).

## 1. Disc load

**Observed:** `engine_init` calls `cd_init` `0x172388` at `0x19d66c`. It
looks up the directory `\BG\DATA` through `0x3616a0` and passes its sector
and sector count to `0x1721e4`, with the table at `0x7ba8a0`. That parser
reads ISO 9660 directory records: name length at +0x20, name at +0x21, sector
at +2 and size at +0xa, both through `0x1721b4`. It stores 32-byte rows
(name, then sector at +0x10 and size at +0x14) and counts them at +0x7d00.
At 1000 rows it prints a message and calls `libc_exit(0)` (`0x1722d4–0x1722f0`).

**Executed:** the parser builds the table from a synthetic directory made of
the real file names and sizes: 927 rows, the 925 files plus the two `\0` and
`\1` records. It reads one sector per call
(`tools/difftest_exit_arrival.py:153-154`). The real sector numbers are not
known for the disc copy. The original never compares them, and only uses
them as offsets.

**Observed:** `cd_findFile` `0x1724fc` formats `"%s;1"`, upper-cases it
through the character table at `0x5628e1`, and compares it with each row in
order. `cd_readAsync` `0x1729e8` (name, destination, status byte, size,
offset) fills the request at `0x7c25b0` with the row's sector plus
`offset >> 11` and `(size + 0x7ff) >> 11` sectors (a size of 0 means the
row's size). It then issues the read through `0x172098` and sets busy byte
`0x41bf90`. `cd_readBlocking` `0x172ad0` polls `lump_pollAsync` and waits
one frame per pass until busy clears.

**Executed:** each blocking read makes exactly one frame wait
(`tools/difftest_exit_arrival.py:172-173`). A name with no row makes
`cd_readAsync` store 2 through the null lookup result. That is a 4-byte store
to address 0 at `0x172a64`. It issues no read and leaves busy clear
(`tools/difftest_exit_arrival.py:199-215`). On the console, what a store to
address 0 does is **Unknown**.

**Observed / Executed:** `gob_loadAll` `0x1737d8`, called by `game_loadLevel`
at `0x1e5914`, reads the GOB's first 0x800 bytes to `0x7c2680` as
the directory. It reads entry k from offset 0x800 plus the 0x800-rounded
sizes of entries 0 to k−1. It does not read the stored offset. Each entry
gets a heap block from `mem_allocTagged` `0x14ff88`, sized to the rounded size
plus 0x100. `lump_fixup` `0x1717d0` then runs on it, and `mem_realloc`
`0x14fe80` shrinks the block. Each entry becomes a 40-byte row at `0x7b9480`
(name, data at +0x10, size at +0x18, 1 at +0x24), counted at `0x41bf7c`. The
names `gaydark1.lmp` and `gaydark2.lmp` are renamed to `faydark1.lmp` and
`faydark2.lmp` (`0x173908–0x1739cc`, **Observed** only). On this disc copy
all 120 GOBs have stored offsets equal to that sequential layout, so the
unread offsets change nothing here.

**Executed** for `strife`, `hub`, `honor` and `storm1a`. The sector reads are
exactly: the directory sector, one read per lump in GOB order, and a 10-sector
read of `<LEVEL>.TEX` right after the lump holding the `.world` entry
(`tools/difftest_exit_arrival.py:162-171`, `tools/ref_exit_arrival.py:89-104`).
That last read is `world_fixup` `0x181d30` at `0x181f28`. It builds the name
from `g_levelTexName` `0x44fe18` and reads 0x5000 bytes. So `0x44fe18` must
hold the base name before `game_loadLevel` runs; round four showed
`0x320edc` copies it there. Lump names match the GOB
(`tools/difftest_exit_arrival.py:177`), and `lump_findLoaded` `0x17306c` finds
each lump. After fixup, the bytes of `script.scr` and `objects.ob` equal the
disc bytes. `lump_findNthByExtension` `0x171fd8` with `world` returns the
first `.world` entry. `game_loadLevel` stores that entry's data at `g_world`
`0x44fdc8` (`0x1e59ac`, `0x1e59bc`, **Observed**). The probe does the same
(`tools/difftest_exit_arrival.py:194`).

**Unknown:** the real sector numbers and directory order, IOP and libcdvd
behaviour, timing, retries after a reported error, the streaming path (byte
`0x41bf91`), the loading-screen thread, and the rest of `game_loadLevel`
(music, ambient sound, `world_prepare` `0x182360`, textures, water).

## 2. Placement on arrival

**Observed:** the arrival marker is class `Player1`, constructor `0x158928`.
It runs once per `Player1` record in `objects.ob`, in file order. Its ranking
uses `g_playerStartRank` `0x4f7108`, and the arrival function
`level_loadScriptAndObjects` `0x217978` sets that byte first: 3 when
`g_loadedFromSave` `0x8e1ad6` is set (then clears it), else 0
(`0x217a90–0x217ab0`).

**Executed** (`tools/ref_exit_arrival.py:239-271`, cases at
`tools/difftest_exit_arrival.py:302-326`): for each marker, with properties
read by `obj_getPropStr` `0x14f4c0` and `obj_getPropInt` `0x14c880`
(`key=value`):

1. At rank 3 the marker is skipped.
2. At rank 0 or below, the marker is taken and the rank becomes 1. At rank 1,
   a marker with a non-zero `default` is taken.
3. If `from` equals `g_prevLevelName` `0x41b7c2` and recall byte `0x41b51e`
   is clear, the marker is taken at rank 2.
4. If the recall byte is set and `from` is `gate`, the marker is taken at
   rank 3.
5. If `name` equals `g_entranceName` `0x4f8468` and the recall byte is clear,
   the marker is taken at rank 3.

A taken marker rewrites all four spawn slots at `0x4f70d0`. For each slot it
calls `world_findFreeSpot(out, marker position, 0x24, 0x18, 0, 0)`. It then
draws once more and sets the facing halfword at `0x4f8410 + 2*slot` to the
marker angle + `(seed >> 16) % 4000` − 2000. A later marker can take over
again. The probe runs a fresh arrival, one arrival per distinct `from` value,
a constructed `name=` marker, a constructed `from=gate` marker under the
recall byte, and a saved-game arrival at rank 3, on all four levels. The real
markers give rank-1 and rank-2 choices: strife has one marker without
properties and one `from=drunarm`, hub has `from=intro` and `default=1`,
honor has `from=valor2`, and storm1a has one marker.

**Executed:** `GameObject_ctor` `0x14cb10` draws one value from `g_randSeed`
`0x404464` for every object and keeps `seed >> 16` at +0x44
(`0x14cd5c–0x14cd80`; `tools/difftest_exit_arrival.py:244-245`). It
puts objects in the grid with `handle_link` `0x1a1738`.

**Executed** (`tools/ref_exit_arrival.py:187-236`): `world_findFreeSpot`
`0x14acf8`(out, origin, radius, size, found pointer, climb) makes up to 50
tries:

1. Three draws `seed = seed × 0x19660d + 0x3c6ef35f`, each mapped to
   2 × (seed >> 16) × 2⁻¹⁶ − 1, repeated until the squared length is at most
   1.
2. The candidate is origin + (x, y) × radius, at the origin's z.
3. It is rejected if `terrain_testFlag1` `0x183b48` (radius = size) is not
   0.0.
4. It is rejected if `terrain_height` `0x183820` is 6.0 or more above the
   origin, unless climb is set.
5. `world_collectObjectsInBox` `0x14a928` collects up to 128 objects in
   ±size horizontally and ±100000 vertically. An object without flag bit 0
   blocks when its squared distance is at most size² + its radius (+0x1c)
   squared.

The output keeps the last candidate that passed the terrain tests, with z set
to its terrain height. The found byte is `tries != 50`. The seed is stored
after each set of draws. These run on the real `.world` of each level after
the original `world_fixup`, against `tools/ref_world.py`'s terrain model, with
the probe's other `Player1` markers in the grid (flag bit 0 set, so they
never block). They also run with a constructed `GameObject` of radius 24, and
on strife one of radius 100 that blocks every try.
`tools/difftest_exit_arrival.py:226-283` compares rank, all four spawn
words, facings and the final seed. The loader's own pass at `0x3212e0`
(slots 1–3, radius 0x24, size 0xe, from the spawn slots) is executed the same
way (`tools/difftest_exit_arrival.py:286-299`). Round four had supplied it.

**Inferred:** in a real arrival, `g_randSeed` at the first `Player1` depends on
every object constructed before it in `objects.ob`, because each constructor
draws at least once. Objects built before the marker can also block free
spots. **Unknown:** the constructors of other classes and their draws, so the
retail seed and the blocking set at that point. The probe's seeds are
synthetic. In a net game, `net_startSync` `0x13dce0` zeroes the seed before
the load (`docs/startup.md`).

## 3. Level-state record bytes

**Executed** (`tools/difftest_exit_arrival.py:405-473`): original
`save_writeLevelState` `0x218600`(destination, space), with no stubs, writes:

| Offset | Bytes |
|---|---|
| +0 | u32 A, the object section length (also stored at `0x88d3e8`) |
| +4 | 4 bytes not written |
| +8 | object section, A bytes |
| +8+A | u32 B = 8 + 12 × decals |
| +0xc+A | 4 bytes not written |
| +0x10+A | u32 decal count, then 4 bytes not written |
| +0x18+A | 12 bytes per decal |
| +0x10+A+B | 5832 bytes of explored map |

The object section (`world_saveState` `0x14e5c8` with thinning level 0;
`tools/ref_exit_arrival.py:292-341`):

- Header: s16 count, u16 1, s32 string-table offset (record bytes + 8).
- Records follow from `world_writeRecords` `0x14e140`, in walk order: grid A
  `0x5db4f0` row by row, grid B `0x5e95f0`, then the off-grid list
  `0x5f76f0`.
- Then the strings: a length byte, the text and a NUL each, shared through
  `saveStr_intern` `0x14de60`.
- The end is rounded up to 4 by moving the pointer. Those pad bytes are not
  written.

One record (`obj_writeRecord` `0x14df50`):

- Class-name offset, s16 size, u16 angle (+0x38), position (+0x10–+0x18).
- One string offset per property (+0x2c list), then 0.
- The class name is the +0x34 text cut at the first `;` or `,`.
- Slot 9 of the vtable at +0x48 writes the class bytes. They start at
  `(record address + 4 × properties + 0x1f) & ~7`, and the size is rounded up
  to 4.

`obj_writeRecord` builds records in a stack buffer, and `memcpy` at
`0x14e734` copies the whole area. So the alignment gaps inside a record carry
stack bytes. The probe fills the stack with 0x5a and the destination with
0xa5 to tell them apart (`tools/difftest_exit_arrival.py:438-446`).

Flag 0x4000 objects are skipped. At level 0, 0x1000 and 0x2000 objects are
written. Retail runs with `g_saveFilter` `0x403a0c` set, because `main` calls
`objects_registerFactory` `0x15da54` at `0x323ecc`. That call installs
`world_saveFilter` `0x15d9c8`. The filter compares the whole +0x34 name,
ignoring case, with the 18 names at `0x403a68`. The probe runs that original
call (`tools/difftest_exit_arrival.py:517-531`): an exact name and its
upper-case form are skipped, and the same name with `;1` is written.

Slot-9 bodies are executed for five classes:

- `GameObject` `0x3c7ec0`: no bytes.
- `Counter` `0x28ed74`: u32 +0x4c.
- `Lever` `0x28e414`: f32 +0x4c, u32 flags +0xc, bytes +0x50 and +0x51.
- `JumpGate` `0x27d974`: bytes +0x4d and +0x4e.
- `Savepoint` `0x28dc9c`: u32 +0x84, or +0x80 when +0x84 is 0, then bytes
  +0xc5 and +0xc6.

343 vtables have a slot 9. They use 153 distinct bodies, and 111 of them use
the empty default. The other 148 bodies are **Unknown** here.

Decals (`decal_serialize` `0x19ee10`) are compared field by field. The
30 × 30 grid at `0x846458` is walked entry index first, then cells row by
row. Fields:

- Halfwords +0, +2 and +4 are entry +8, +0xa and +0xc.
- Halfword +6 is the integer part of √(x² + y²) + 0.5, where x and y are
  entry +0x10 and +0x12.
- Byte +0xa is (entry +0x14 − 0x3d3) >> 1.

Halfword +8, from `math_atan2_16` `0x166798`, has no independent reference
here. Byte +0xb is copied from an unset stack byte. The explored map
(`automap_packExplored` `0x16865c`) packs `0x4044f0` into 108 rows of 54
bytes, each `(g[a+1] & 0xf0) + (g[a+5] >> 4)`
(`tools/ref_exit_arrival.py:344-358`). The probe records every store outside
the stack and requires each one to fall in the destination, the size word,
the string-area pointers, or a list node or head. Each node and head must be
byte-identical afterwards, because the list iterators link themselves in and
out (`tools/difftest_exit_arrival.py:434-467`).

**Observed, not executed:** the thinning retries (`0x14e698`,
`0x14e6c4–0x14e6f8`), the −2 overflow returns (records over 0xcb20 bytes,
strings of 5000 bytes or more), and the type-name path when +0x34 is null
(`0x14df84–0x14dfd4`). **Unknown:** decal angle values.

## 4. Entry scripts and the stored-state reader

**Executed** (`tools/difftest_exit_arrival.py:606-690`): original
`level_loadScriptAndObjects` `0x217978`(level, qualified name) on the loaded
lump does the following, in this order:

1. Looks up the qualified name in the directory `0x8ab590`, summing the sizes
   before it (`0x2179c8–0x2179f8`). The restore flag is "the row where the
   search stopped has a name".
2. `script_setCurrent` `0x1ed650` with `script.scr` from the lump. That calls
   `scr_load` `0x13e8f8`, then `0x147a84`, which registers the table at
   `0x403370`.
3. `script_runByName("preStart")`, unless byte `0x4f8b58` is set.
4. With the flag set:
   - Copy A bytes from the stored entry to `0x88d480`, and B bytes after
     them.
   - `automap_unpackExplored` `0x1686c4` on the map bytes.
   - `world_loadRecords(0x88d480, 0)`.
   - `decal_loadList` `0x1a00b0` on the decal copy.
5. `world_loadRecords(objects.ob, flag)`. The flag is 1 when a stored state
   was restored, and then the level file recreates only the save-filter
   classes (`docs/objects.md`).
6. `script_runByName("start")`, unless `0x4f8b58` is set.

The stored case round-trips the writer's bytes from section 3. The copies
equal those bytes, original `decal_loadList` and `automap_unpackExplored`
run, and packing the map again reproduces the stored 5832 bytes
(`tools/difftest_exit_arrival.py:668-676`). For all four levels and both
seeds, the built-in call list of `preStart` and `start` matches
`tools/ref_amx.py` on the same `script.scr`, by name and argument cells, with
`callScript` nested in the original. The only reference to `0x4f8b58` found is
the read at `0x217ab8`. Its writer is **Unknown**, and it is 0 in the image.

Under all-0 and all-1 built-in results (model side, which matched the
original), the entry scripts reach:

- strife: `preStart` calls `getv` and `preloadResource`. `start` calls
  `addDeferedCall`, `callScript`, `getv`, `hideMonster`, `setv`, `showBust`
  and `showMonster`.
- hub: `start` calls `addDeferedCall`, `autoPropSetState`, `getNumPlayers`,
  `getPlayerFlag`, `getv`, `grantMission`, `refillPlayerMana`,
  `removePlayerItem`, `setMissionAvailable`, `setPlayerFlag`,
  `setSaveInhibit` and `setv`.
- honor: `start` calls `addDeferedCall`, `getv`, `playerHasItem` and
  `setParticle`.
- storm1a: no built-ins.

**Executed, the eleventh row:** ten other keys plus an 11th row `SYN_ELEVEN`.
Arriving at `strife`, which is not in the first ten rows, stops the search at
row 10. That row has a name, so the reader restores the 11th row's bytes from
the sum of the ten sizes (`tools/difftest_exit_arrival.py:621-629`). Round
four showed that the departure store appends that 11th row. **Inferred:** once
an 11th row exists, every arrival whose key is not among the first ten
restores the 11th row's state. That includes a key that was never stored.
Also, a row created when the bytes did not fit (round four, the writer
skipped) is restored from whatever is at its offset. **Unknown:** whether
retail play reaches 11 keys in one act. Acts have at most 10 rows and reserve
at most 153000 bytes, but qualified names with a sub-name are separate keys.

**Unknown:** built-in bodies on arrival (they are executed one by one in
`docs/spec/script-builtins.md`), the deferred calls `addDeferedCall` queues
(run by `script_runDeferred` `0x322e6c` after warm-up), the post-action at
`0x1e60b8`, and every object constructor `world_loadRecords` would run.

## What a client can implement from this

1. **Disc.** Keep a flat table of `BG\DATA` names with `;1`, compared after
   upper-casing. Read a GOB's 0x800-byte directory, then each entry at 0x800
   plus the rounded sizes of the entries before it. Fix up each lump, then
   read the level's `.TEX` header (0x5000 bytes) while fixing up the lump with
   the `.world`. That read uses the name in `0x44fe18`. Point `g_world` at the
   first `.world` entry. Treat a missing file as a fault, not an empty read.
2. **Order of arrival.**
   - Set the start rank to 3 if loaded from a save, else 0.
   - Install the level script.
   - Run `preStart`.
   - If the qualified name is stored: restore objects, explored map and
     decals.
   - Construct `objects.ob`, flag 1 when restored.
   - Run `start`.
   - Byte `0x4f8b58` skips both scripts.
3. **Player placement.** Apply the `Player1` ranking in file order. Run the
   free-spot search above with the 0x19660d / 0x3c6ef35f generator, and draw
   one value per constructed object. A client that wants the original's spawn
   points must construct the earlier `objects.ob` objects with their draws.
4. **Loader scatter.** Slots 1–3 search again with radius 0x24 and size 0xe,
   except in the cases round four listed.
5. **Level-state bytes.** Write and read the table in section 3, including the
   unwritten words. Apply the save filter by whole name, ignoring case.
   Implement slot-9 bodies per class: the five above are verified.
6. **Directory.** Do not copy the eleventh-row restore unless matching the
   original's bugs is the goal. Stop at ten keys, or search all rows.

Still not implementable from this research: the loading screen and warm-up,
shop stock, other object constructors and their draws, built-in bodies during
arrival, vehicles, and menu states 0–4. Both client refusals stay.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_arrival --seed 20973
PYTHONDONTWRITEBYTECODE=1 python3 -m tools.difftest_exit_arrival --seed 7
```

The disc copy is the untracked symlink `local/rta-disc` (pass `--disc` to use
another path). Each seed passes with zero failures:

- 232 entry calls and 1,102 assertions.
- 4 levels, 927 directory rows each, 21 sector reads and 13 lumps.
- 24 placement cases and 177 free-spot calls.
- 16 writer cases with 52 records.
- 16 arrivals and 4 missing-file cases.
- 195 supplied addresses.

Seed 20973 traces 207 built-in calls and seed 7 traces 212. Logs are kept in
`local/exit-travel-r5/arrival-20973.log` and `arrival-7.log`. In
`local/exit-travel-r5/negative-controls.log`, four deliberate reference
errors each fail on strife: the generator constant, one explored-map bit, the
missing `.TEX` read, and the model-side built-in results.
