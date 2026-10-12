# `.world` — level geometry

One `.world` entry sits in each level lump (`<level>.lmp` inside `<LEVEL>.GOB`). It holds
everything about the level that is not an object: the render geometry, the terrain used for
height and collision, the navigation grid, water, placed scenery models, fixed particle
emitters and lights, moving pieces (doors, lifts) and the automap. Textures are in a second
file on the disc, `<LEVEL>.TEX`, which the world refers to by cell and offset.

`python3 tools/world_info.py <file.world>` parses the format described here.

## How this was established

Everything was read from the executable `SLUS_209.73` and from level files unpacked from the
disc; nothing was run. That still describes this document: the project's live game
(the Play! emulator, which is not a PlayStation 2 and not PCSX2; `FINDINGS.md`, "Run on the live game" (rows V1–V23) and `docs/issues/live-rig.md`)
loads levels, but it runs with no video and no statement about the format was compared
with it. The 119 `.world` files on the disc (one per `.GOB` that has a level)
were all parsed. Each statement is marked:

- **O** (Observed) — read in the code at the address given *and* seen to hold in the files;
- **D** (Observed in data) — a regularity that holds in all 119 files (counts are given),
  for which no code was read; treat as Inferred when building on it;
- **I** (Inferred) — follows from the above but was not seen directly;
- **U** (Unknown).

Functions are named as in `symbols/engine.tsv` and `symbols/fmt-world.tsv`. All integers are
little endian. "Offset" always means a byte offset from the start of the `.world` entry; the
loader turns offsets into pointers in place.

## Coordinates and units

| | | |
|---|---|---|
| Axes | x and y span the ground, z is height (up) | O: terrain heights add to z (`terrain_height` 0x183820); water level is a z value (`water_test` 0x189438) |
| Handedness, which way +y points on screen | right-handed, z up; camera space has x right, y down, z forward. Which way the axes point on the compass is still open | O for the screen: `docs/spec/render-pipeline.md` section 3 (`Camera_apply` 0x2035c8); U for the compass |
| World unit | the unit of object positions (floats) | O |
| Stored positions | integers in quarter units: world = stored × 0.25 | O: 0x18b810, 0x18ba18, 0x182768; D: decoded vertices reproduce the stored chunk bounds |
| Height samples | 4 units apart; heights in 1/16 unit | O: 0x183820 |
| Rotations | cosine and sine as s16 / 32767 | O: 0x183820, 0x1887b8 |
| Terrain grid cell | 160 units | O: 0x183248 |
| Path node spacing | 24 units | O: 0x183e40 |
| Automap cell | 120 units | O: 0x168cac |
| Texture cell | header float, 720 in every file | O: 0x17d830 |
| Scenery tile | 120 units square is the usual chunk and height-field size (30 samples) | D |

## File layout

The header is 0x84 bytes. Sections follow in this order in every file (D); between them
there is zero padding. The files are 96 KB to 3.6 MB with 67 to 4,984 chunks; the example
column is one small arena level of 557,372 bytes.

| Section | Reached from header | Example |
|---|---|---|
| header | — | 0x84 bytes |
| path grid | +0x38 | 65 × 55 nodes |
| bit grid | +0x4c | 144 × 112 bits |
| automap texture | +0x6c | 0x40-byte header + pixel data |
| height fields | terrain elements | 9 fields |
| chunk tree | +0x04 | 28 split nodes, 29 leaves |
| moving pieces | +0x54 | 4 |
| chunk data: effect records and VIF packets | chunk records | 61 distinct blocks |
| texture cell table | +0x64 | 102 entries |
| automap grid | +0x80 (= +0x78) | 13 × 11 cells |
| terrain cell lists | terrain grid | |
| terrain grid | +0x18 | 11 × 11 cells |
| terrain elements | +0x20 | 59 |
| chunk records | +0x24 | 257 |

## Header

| Offset | Type | Meaning | |
|---|---|---|---|
| 0x00 | u32 | number of chunks | O 0x181d30 |
| 0x04 | u32 | offset of the chunk tree. The first u16 there is the marker 0x4567, which the loader skips; the root node follows | O 0x181d30; marker present in all files |
| 0x08, 0x0c | s32 × 2 | terrain grid origin, in cells of 160 units | O 0x183248 |
| 0x10, 0x14 | u32 × 2 | terrain grid width, height in cells | O |
| 0x18 | u32 | offset of the terrain grid: width × height u32, row by row (row = y) | O |
| 0x1c | u32 | number of terrain elements | O 0x181d30 |
| 0x20 | u32 | offset of the terrain elements (0x24 bytes each) | O |
| 0x24 | u32 | offset of the chunk records (0x3c bytes each) | O |
| 0x28, 0x2c | s32 × 2 | path grid origin, in nodes of 24 units | O 0x183e40 |
| 0x30, 0x34 | u32 × 2 | path grid width, height. Both 0 in two levels that have no path grid | O |
| 0x38 | u32 | offset of the path grid: width × height u32 (0 when there is none) | O |
| 0x3c, 0x40 | s32 × 2 | origin of the bit grid | I |
| 0x44, 0x48 | u32 × 2 | bit grid width, height; always multiples of 16 | I, D |
| 0x4c | u32 | offset of the bit grid, width × height / 8 bytes | O: relocated at 0x181e1c; no other reader found |
| 0x50 | u32 | number of moving pieces | O 0x182768 |
| 0x54 | u32 | offset of the moving pieces (0x1c bytes each) | O |
| 0x58, 0x5c | s32 × 2 | lowest and highest texture cell id | O 0x181d30, 0x1822e8 |
| 0x60 | s32 | −1 in every file. When non-zero, `world_prepare` (0x182360) replaces it with the size of the texture segment cache in 128 KB blocks | O |
| 0x64 | u32 | offset of the texture cell table: (highest − lowest + 1) entries of {u32 offset, u32 size}. The file holds placeholders {0, 0x40}; the loader fills the table from `<LEVEL>.TEX` | O 0x181d30 |
| 0x68 | float | texture cell size in world units; 0 means 960. 720 in every file | O 0x181d30, 0x17d830 |
| 0x6c | u32 | offset of the automap tile texture, in the format of a `.tex` entry (relocated by `tex_relocate` 0x179e10) | O |
| 0x70 | u32 | 0 in every file. If non-zero the loader does not read the automap grid and tells the lump loader to keep only the first [+0x78] bytes of the entry | O 0x181d30, 0x168894, 0x17153c; never exercised |
| 0x74 | u32 | 0 in every file | U |
| 0x78 | u32 | offset of the tail block. Terrain grid entries are relative to it | O 0x181d30 |
| 0x7c | u32 | 0 in the file; at run time the pointer to the texture segment cache | O 0x182360 |
| 0x80 | u32 | offset of the automap grid; equal to +0x78 in every file | O 0x168894 |

## Chunks

A chunk is one placed thing: a piece of geometry, a water tile, a scenery model, a particle
emitter or a light. Records are 0x3c bytes.

| Offset | Type | Meaning | |
|---|---|---|---|
| 0x00 | u32 | offset of the chunk's data; what it is depends on the flags | O 0x181d30 |
| 0x04 | u32 | geometry: length of the VIF packet in 16-byte units. 0 in the file for every other kind; used at run time (emitter type index, light slot, animation slot) | O 0x1887b8, 0x18b810, 0x18ba18, 0x187eac |
| 0x08 | float × 3 | bounds, minimum x, y, z (world units) | O 0x189870, 0x189240 |
| 0x14 | float × 3 | bounds, maximum x, y, z | O |
| 0x20 | u32 | geometry: byte offset of the chunk's texture header inside its texture cell (a multiple of 0x40). 0 otherwise; emitters and lights keep a timer here at run time | O 0x1887b8 |
| 0x24 | u32 | flags, below | O |
| 0x28 | s32 × 3 | translation x, y, z in quarter units | O |
| 0x34 | s16 | texture cell id (row × 100 + column). 0 = the chunk is never drawn | O 0x1887b8 |
| 0x36 | s16 | flag 1 clear: cosine × 32767. Flag 1 set: orientation code in bits 0–2 (higher bits are leftovers) | O 0x1887b8 |
| 0x38 | s16 | sine × 32767 (ignored when flag 1 is set) | O |
| 0x3a | s16 | 0 in every file | U |

For a **geometry** chunk, local coordinates (lx, ly, lz) become world coordinates like this
— O in 0x1887b8 and 0x182768; D: with these rules the decoded vertices of 168,581 of 168,630
geometry chunks reproduce the stored bounds to within one unit (the other 49 are off by 6
to 11.5 units):

```
px = (lx + tx) / 4        py = (ly + ty) / 4        world z = (lz + tz) / 4
flag 1 clear:             world x = px*cos - py*sin      world y = px*sin + py*cos
flag 1 clear, flag 0x40:  world x = px*cos + py*sin      world y = px*sin - py*cos
flag 1 set, code bit 2 clear:   world x = ±px (minus if bit 0)   world y = ±py (minus if bit 1)
flag 1 set, code bit 2 set:     world y = ±px (minus if bit 0)   world x = ±py (minus if bit 1)
```

Note that the translation is added *before* the rotation. For every **other** kind the
translation is already in world axes: the thing sits at (tx, ty, tz) / 4, and a model is
rotated about that point (O 0x187eac, 0x18b810, 0x18ba18, 0x189514; D: that point lies
inside the stored bounds, the rotated one does not).

### Flags

| Bit | Meaning | |
|---|---|---|
| 0x1 | orientation is a quarter-turn code, not cos/sin | O 0x1887b8 |
| 0x2 | set on every emitter, light and model chunk, on no geometry chunk | D; no reader found |
| 0x4 | seen with 0x1 and 0x10 | U |
| 0x10 | packet has environment-mapped batches; six matrix rows are sent instead of four | O |
| 0x20 | chunk of a moving piece; its stored bounds are padded by 48 units on every side | O 0x182940; D: exactly the pieces' chunks |
| 0x40 | mirrored | O |
| 0x80 | water tile | O |
| 0x100 | run time only: draw once with a constant light level of −230, then the bit clears itself (`world_setPieceFlash` 0x182bf4) | O |
| 0x200 | no dynamic lights (constant light level 0) and sort key 4 instead of 0 when queued for drawing | O |
| 0x400 | GS `TEST_1` = 0x582f5 (alpha test on) instead of 0x587f4; D: such packets have batches with blending off | O |
| 0x200 or 0x400 | GS `ALPHA_1` = 1 instead of 2. The default 2 is not a blend with the frame buffer: it is `src × (1 − As)` (`docs/spec/render-pipeline.md` sections 6 and 13) | O |
| 0x800 | scenery model reference | O |
| 0x1000 | water: use the second set of water drawing constants | O 0x1876e0 |
| 0x2000 | no dynamic lights, constant light level 230 | O |
| 0x4000 | particle emitter | O |
| 0x8000 | light | O |
| 0x10000 | GS `ALPHA_1` = 0x48, additive: `dst + src × As` (was Inferred; confirmed in `docs/spec/render-pipeline.md` section 13); not set in any file | O, code only |
| 0x20000 | set on 48 chunks | U |

Kinds in the 119 files: 168,630 geometry, 9,884 water, 6,969 model, 4,350 emitter, 1,090 light.

### Chunk tree

A binary tree of split planes used for the frustum walk (`world_draw` 0x189870) and for box
queries (`world_collectChunksInBox` 0x189240). Nodes are arrays of 16-bit words.

Split node (10 words) — O:

| Word | Meaning |
|---|---|
| 0 | bit 15 set. Bit 14: a water chunk exists below this node. Bits 0–11: axis, 0 = x, 1 = y, 2 = z |
| 1–2 | s32 A: upper bound of the first child along the axis, divided by 4 |
| 3–4 | s32 B: lower bound of the second child along the axis, divided by 4 |
| 5–6, 7–8 | s32 lowest and highest z of everything below the node, divided by 4 |
| 9 | s16 distance in words from word 9 to the second child. The first child starts at word 10 |

Leaf — O: word 0 is a count (bit 15 clear), followed by that many u16 chunk indices.

D: every chunk is in exactly one leaf (190,923 chunks). For all 45,181 split nodes the bounds
of the geometry, water and model chunks under the first child do not exceed A × 4, those
under the second do not start below B × 4, and bit 14 is set exactly when a water chunk is
below. Emitter and light chunks have large bounds and can overhang the planes. The walk
starts with x and y unbounded and z from −60 to 780.

### Geometry chunks: the VIF packet

The data of a geometry chunk is a ready-made PS2 VIF1 packet. The engine does not copy it:
for each visible chunk it writes a short header into the display list and then a DMA `ref`
tag pointing at the stored packet (O 0x1887b8). The header carries what the packet relies on:

- GS registers for the chunk's texture and blending;
- the chunk's rotation combined with the camera matrix (4 rows, 6 with flag 0x10), and a
  call of VU1 microprogram entry 0x16;
- the lights. The earlier version said "entry 0x34" here; the lights are loaded by entries
  0x0e and 0x04, and entry 0x34 only stores a word that nothing reads
  (`docs/spec/render-pipeline.md` section 4.6);
- `STROW tx, ty, tz, 0` — the chunk translation goes into the VIF row registers, so that
  the packet's `STMOD 1` adds it to every position as it is unpacked.

So the same packet is drawn in many places: 8,376 distinct packets serve the 168,630
geometry chunks (D).

Packet layout — D, identical in all 8,376 packets (1,184,394 batches); the VIF codes are the
standard PS2 ones:

```
12 zero bytes
DIRECT            GS writes: ALPHA_1, optionally ALPHA_2, TEST_1
batch, batch, …
[DIRECT, batch, …]     up to two more state blocks in 888 packets
[FLUSH], NOP padding to the stored length

batch:
  ITOP nv
  STMOD 1
  UNPACK V3-16 signed    nv        positions (the row registers are added)
  STMOD 0
  UNPACK V3-8 signed     nv        normals, 127 = 1.0
  UNPACK V3-16 unsigned  nv + 2    strip table
  UNPACK V4-16 unsigned  1 + k     first row (k, 0, 0, 0); then k rows of extra copies
  UNPACK V4-32 unsigned  1 or 2    GIF tag(s)
  MSCAL 0x46 (one tag) or 0x48 (two tags)
  STCYCL cl = registers per vertex, wl = 1
  UNPACK V2-16 unsigned  nloop     texture coordinates
  STCYCL cl = 1, wl = 1
```

The first word of a GIF tag holds `nloop` (the number of strip vertices) with the EOP bit;
the second word holds the primitive: always a textured, Gouraud-shaded triangle strip with
texel (not normalised) coordinates. Three forms occur:

| Tag word 1 | Registers | Use |
|---|---|---|
| 0x30ae4000 | UV, RGBAQ, XYZF2 | normal, blending enabled |
| 0x308e4000 | UV, RGBAQ, XYZF2 | blending off (the alpha-tested batches) |
| 0x40ae4000 then 0x41ae4000 | UV, NOP, RGBAQ, XYZF2 and NOP, UV, RGBAQ, XYZF2 (second GS context) | environment-mapped: the same vertices are sent twice |

Vertex colours are not stored. Each vertex has a position, a normal and one or more places
in the strip; the microprogram lights it. Texture coordinates are stored per strip position
and are written straight into the outgoing GS packet (that is what the `STCYCL` around the
last unpack does), so they are GS `UV` values: texels × 16.

**Strip table** — D (replaying the rules below in stream order fills every strip position
of all 1,184,394 batches exactly once), I for the meaning. Model files use the same table,
and `docs/formats/model-texture.md` read the model vertex programs (entries 0x42, 0x44)
that execute it; the world programs (0x46, 0x48) were not read. Let `nreg` be the registers
per vertex (3 or 4).

- Rows 0 and 1 are constants: (3, 0, 3) when `nreg` is 3, (5, 0, 5) when it is 4. In the
  model programs they are placeholders, because the loop places each vertex two rows after
  reading it; I: the same here.
- Row *r + 2* belongs to vertex *r*. Its first value *a* puts the vertex at strip position
  `(a & 0x7fff) / nreg` (integer division).
- The second and third values of a row are an unrelated *copy*, done before the row's own
  vertex is placed: "the vertex now at position `src / nreg` also goes to position
  `(dst & 0x7fff) / nreg`". A pair with `src == dst` means no copy. Vertices used more than
  twice overflow into the extra rows of the V4-16 block, two (src, dst) pairs per row,
  applied after all rows.
- Bit 15 of *a* or *dst* marks a strip position that does not complete a triangle. The
  first two positions of every batch have it (D, all batches). In two levels checked,
  triangles ending on a marked position are three times larger than the others, as
  expected of strip restarts.

Triangles are (p−2, p−1, p) for every unmarked position p. About 15% repeat a vertex
(stitching) and should be dropped. The winding is **not** consistent: compared with the
vertex normals it is half one way and half the other, with either parity rule (D, three
levels). Draw without back-face culling or orient triangles by their normals.

What the world microprograms do with the data was not read (entries 0x16, 0x34, 0x46,
0x48). U.

### Textures of geometry chunks

- The chunk names a texture cell (+0x34) and a byte offset inside that cell (+0x20). O
  0x1887b8: the texture header is at `cell data + offset`.
- D: all 167,642 drawn geometry chunks name *different* textures. Lighting is not in the
  vertices, so each placed chunk evidently has its own pre-lit texture; I.
- 988 geometry chunks have cell 0 and are skipped by the drawing code (O); 123 of them
  belong to moving pieces. Why they exist was not established. U.

### Water chunks (flag 0x80)

Data, 0x90 bytes — O 0x187374, 0x1875d4, 0x1876e0:

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | s16 × 4 | chunk indices of the four neighbouring water tiles, −1 for none; used to continue the surface across tiles |
| 0x08 | u32 | 0; run time pointer to the tile's simulation block |
| 0x10 | 128 bytes | a 32 × 32 bit mask; I: which cells of the tile are water. Bit order U |

The surface is a 32 × 32 grid generated at run time; nothing else is stored. The chunk
translation is the tile's centre (D, all 9,884 tiles) and the height it is drawn at.
`water_test` returns the chunk's minimum z as the water height; that equals the drawn
height in 9,035 tiles and is 5 lower or 13 higher in the rest (D). Tiles are 120 units
square in almost all cases (D).

### Model chunks (flag 0x800)

Data, 0xb0 bytes — O 0x187eac, 0x182360:

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | char[0x50] | lump name without extension; `<name>.lmp` is loaded with the level |
| 0x50 | char[0x50] | model name; `<model>.vif`, `<model>.tex` and `<model>.anm` are looked up in that lump. Anything from the first `_` on is cut off |
| 0xa0, 0xa4, 0xa8 | u32 × 3 | 0; run time pointers to the three entries |
| 0xac | u32 | lighting: value 1, 2 or 8 chooses one of three lighting set-ups, none of them means lit from the lights near the chunk position; 4 is tested but unidentified; 0x10 is set at run time when the model name had a `_`. The files use 0, 1 and 8 |

The model is drawn at the chunk translation with the chunk rotation. Models that share an
`.anm` share one animation state and play in step.

### Emitter chunks (flag 0x4000)

Data: a 0x48-byte particle emitter description (O 0x181d30: the loader keeps up to 16
distinct descriptions per level and stores the index in chunk +4). Bytes 0–6 and the three
s16 at +8 are the generator parameters handed to 0x18f118; a short name is at +0x3d. The
other fields belong to the particle system and were not read. U.

### Light chunks (flag 0x8000)

Data, 0x30 bytes — O 0x18ba18:

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | char[16] | name |
| 0x10, 0x12 | u16 × 2 | radius, low and high |
| 0x14 | u16 | 0 steady at the low radius; 1 a random radius between the two every `period` frames; 2 ramp back and forth; 3 switch between the two; 4 off. The files use 1 and 2 |
| 0x16 | u16 | period in frames |
| 0x18 | u16 × 4 | colour |
| 0x20 | u16, u8 | glow sprite: base value and shift of a random addition; I: rotation |
| 0x23 | u8 × 4 | glow sprite colour |
| 0x27 | u8 | non-zero = draw the glow sprite |
| 0x28 | u8 | first parameter of the glow sprite; I: its size |

At most 16 such lights are live at once (least recently drawn is replaced). The flicker
uses the cosmetic random generator, so it differs between machines; it only lights things.

The level's sun and ambient light are **not** in this file: they come from light-marker
objects in `objects.ob` (see `docs/objects.md`).

## Terrain: height and collision

Three tables: a coarse grid to find candidates, the *elements* (placed height fields) and
the height fields themselves, which are shared (136,466 elements use 4,375 fields).

**Terrain grid** — O 0x183248. Cell (i, j) covers x from (originX + i) × 160 and y from
(originY + j) × 160. Each u32 is an offset *relative to header +0x78* of a list of s16
element indices ended by −1. D: an element is listed in every cell its rectangle touches.

**Terrain element**, 0x24 bytes — O 0x183248, 0x183820, 0x185a40:

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | s16 × 4 | rectangle in world units: min x, min y, max x, max y. D: contains every sample that has ground (all files; in three levels measured, with 4 to 12 units to spare) |
| 0x08 | u32 | 0; run time visit stamp |
| 0x0c | u32 | offset of the height field |
| 0x10 | u32 | flags: 1 mirrored; 2 ignored (run time, set for an open door); 4 the field has flagged samples, so the "everything here is lower" shortcut must not be taken (D: bit 4 is set exactly when a sample has flag bits). Executed (`docs/spec/world-queries.md` sections 6, 9.1): that is all the bit does — in the sweep it disables the shortcut always, in the ray only when the ray was given a flag mask |
| 0x14 | s32 × 3 | position x, y and height offset z, world units |
| 0x20 | s16 × 2 | cosine, sine × 32767 |

**Height field** — O:

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | s32 × 2 | sample index of the first column and row (x0, y0) |
| 0x08 | u32 × 2 | width, height in samples |
| 0x10 | s16 | lowest height among samples that have ground (D: 4,170 of 4,375 fields; the rest have none or differ) |
| 0x12 | s16 | highest height; used to skip the field early. The loader sets it to 2000 for the fields of moving pieces |
| 0x14 | s16[width × height] | samples, row by row |

A sample is `height × 16 + flags`: height = sample >> 4 (arithmetic), flags = low 4 bits.
Height −2000 means there is no floor. The ground height at a sample is height + element z.
Sample (i, j) of the array is at local position ((x0 + i) × 4, (y0 + j) × 4), and

```
world x = lx*cos - ly*sin + element x        (mirrored: lx*cos + ly*sin + element x)
world y = lx*sin + ly*cos + element y        (mirrored: lx*sin - ly*cos + element y)
```

Sample flags (only 1 and 2 occur; 31% of samples have 1, a few hundred have 2):

| Flag | Meaning | |
|---|---|---|
| 1 | blocks everything that moves along the ground: every caller's mask has bit 0. In the height field of a moving piece the loader turns such samples into walls of height 2000 | O 0x185a40, 0x181d30 |
| 2 | blocks creatures: `Creature_moveBy` (0x113c48) passes mask 3. `obj_moveWithCollision` (0x14d4b8) passes 3 for creatures, 5 for players and 1 for other objects, and `Prop_run` (0x154514) passes 1, so through those routines flag 2 stops monsters but not players or props | O |
| 4 | would block players only (mask 5 above); no sample has it | O code, D |

How the engine uses the samples — O, summarised:

- *Height under a disc* (`terrain_height` 0x183820): of the samples whose grid point lies
  inside the disc, the highest. −1,000,000 when there is none.
- *Moving circle* (`terrain_sweepCircle` 0x185a40): every sample is a point obstacle at
  its grid position. It stops the circle when its ground height is at least 12 above the
  mover's base, or when one of its flags is in the mover's mask. So steps under 12 units
  are walked up, anything higher is a wall, and walls need no geometry of their own.
- *Ray* (`terrain_raycast` 0x18a5c0): against the same samples. The earlier version said it
  "marches 240 units at a time"; executed (`docs/spec/world-queries.md` 9.1), 240 units is
  the segment for which elements are collected, and each element is then marched one
  4-unit sample at a time. Flags do not block the ray: each flag bit that is in the
  caller's mask adds 65536 to the sample's height, so a flagged sample is a very high wall.

D: rasterising all elements of a level this way gives a clean floor plan (rooms, corridors,
door lines, pillars) — `world_info.py --flags-pgm`.

## Path grid

O 0x183e40, 0x184798. One u32 per node, row by row. Node (i, j) is the world point
((originX + i) × 24, (originY + j) × 24). Only the **start** of a search is snapped to the
nearest node; the goal is used as a point with a radius (the earlier version said "a
position is snapped"; executed, `docs/spec/world-queries.md` 10.3, 10.4).

| Bits | Meaning |
|---|---|
| 0–7 | which neighbours can be walked to, in the order (−1,−1), (0,−1), (+1,−1), (+1,0), (+1,+1), (0,+1), (−1,+1), (−1,0) |
| 8–15 | 0 in the file; search mark at run time (link number + 1; 15 for the start node) |
| 16–31 | 0 in the file; at run time a block counter, 0–16, raised and lowered by the torch and fire objects (0x18b6c0, 0x18b584); a node with a non-zero counter is never entered. The earlier version said "non-zero blocks the node", which is the effect but not the coding (`world-queries.md` 10.1) |

D (6,250,065 nodes): only bits 0–7 are ever set in a file, no link leaves the grid, and
1.7% of the 31 million links have no link back (one-way drops).

## Moving pieces

A door, lift or bridge is a level object (`WorldPart` and its subclasses) that takes over
one piece of the world. Records are 0x1c bytes — O 0x182768, 0x182c98, 0x182b00:

| Offset | Type | Meaning |
|---|---|---|
| 0x00 | s32 | first chunk |
| 0x04 | s16 | number of chunks (1 in every file) |
| 0x06 | u16 | 0; bit 0 is set at run time when an object claims the piece |
| 0x08 | s32 × 3 | rest translation, quarter units, in the piece's rotated frame like a chunk translation |
| 0x14 | s16 × 2 | rest cosine, sine × 32767 |
| 0x18 | s16 | terrain element that is the piece's collision |
| 0x1a | s16 | varies (−349 … 289). U |

An object finds its piece by position (`world_findMovingPiece`, nearest within 80 units).
Moving it rewrites the chunk's translation and rotation; opening it sets flag 2 on the
terrain element. Pieces nobody claimed lose their collision after the objects are created
(`world_disableUnclaimedPieces` 0x1826ec). 178 pieces exist in 19 of the 119 levels.

## Level texture file and texture cells

`<LEVEL>.TEX` is a separate file on the disc, not part of the GOB. O unless marked.

- Directory, read by `world_fixup` (first 0x5000 bytes): a u32 (0 in the three files
  looked at), then 12-byte records {s32 cell id, u32 file offset, u32 size}, ended by an id
  of −1 or −2. The loader copies offset and size into the world's cell table.
- Cell id = row × 100 + column, where column = floor(x / cellSize) + 50 and row =
  floor(y / cellSize) + 50 (0x17d830). The engine keeps the 3 × 3 cells around the camera
  focus loaded, reading 128 KB at a time, plus any "always loaded" cells.
- A cell starts with a u32 texture count; texture headers of 0x40 bytes follow at 0x40,
  0x80, … (0x17d680). In a header: u16 width at +0, u16 height at +2 (D: in three levels
  the largest texture coordinate of each of 1,942 chunks fits the size found here), u16
  flags at +8, and at +0x10 the offset of the pixel-data description **from the start of
  the cell** (0x179f28; in a `.tex` lump entry the same field is relative to the header).
- The header fields and the pixel data are the texture format, described in
  `docs/formats/model-texture.md`. Decoding cell textures to pixels was not tried here. U.

The world also refers to `waterenv.lmp` (water texture, loaded by name in `game_loadLevel`
0x1e55c0) and to the lumps named by its model chunks.

## Automap

- Header +0x6c: a small tile texture. Its pixel format was not decoded. U.
- Header +0x80: s16 x0, y0, width, height, then width × height u16 cells, copied by
  `automap_loadGrid` (0x168894) into a 216 × 216 run-time grid. A world position maps to
  cell (x0 + x / 120, y0 + y / 120) — O 0x168cac.
- Cell: bits 12–15 are 0 in the file and hold the explored level at run time (O 0x16865c,
  0x1686c4, `automap_revealAll`). Bits 5–7 take all eight values and bits 0–4 and 8–11 are
  small indices (D); I: orientation and tile selection. Exact tile lookup: U.

## Bit grid (header +0x3c … +0x4c)

One bit per cell. Where a path grid exists the origin is twice the path origin, rounded
toward zero to a multiple of 16 (D, 117 files), and the size is within 32 of twice the path
grid's, so the cells are probably 12 units. The loader relocates the pointer and no other
code that reads it was found (a search for loads at world +0x4c in 0x147000–0x1a0000 finds
only the loader). Read as rows of 16 × 16-cell blocks it gives a recognisable but untidy
outline of the level; the exact bit order was not found. A native loader can ignore it. U.

## What is not in the `.world` file

| Thing | Where it is |
|---|---|
| objects, monsters, triggers, player starts, sun and ambient light | `objects.ob` in the level lump |
| scripts, cutscenes, dialog | `script.scr`, `.cut`, `*_dialog.bin` |
| I: ambient sound | `ambient.bin` (its text is handed to 0x214eb0, in the sound area, by `game_loadLevel`) |
| texture pixels | `<LEVEL>.TEX` |
| the object grid (120 × 120 cells of 256 units) and light grid | built at run time |

## Shared and per-machine state

For online play it matters which parts of the loaded world belong to the simulation.

- Shared (must be identical on every machine): height fields and element flags, including
  the changes made by moving pieces; the path grid; chunk bounds used by `water_test`.
- Per machine, drawing only: which texture cells are loaded (follows `g_cameraFocus`,
  0x17d830); a chunk whose texture is not loaded yet is simply not drawn (0x1887b8). Water
  simulation blocks exist only for tiles that have been drawn (0x1876e0).
- Cosmetic: light flicker (0x18ba18) and the random water splashes (0x1876e0) draw from
  `g_cosmeticSeed`.

## What a native loader needs, and in what order

1. **Containers.** Read `<LEVEL>.GOB`, take `<level>.lmp`, take its first entry with the
   extension `world` (this is how `game_loadLevel` finds it). `tools/gob.py` does both.
2. **Header, chunk records, chunk tree.** Check the 0x4567 marker and that every table lies
   inside the file. Drawing the chunk bounds as boxes already shows the level and tests the
   tree. Nothing needs relocating if you keep offsets.
3. **Terrain.** Elements, height fields, grid. Implement the height query and the moving-circle
   test exactly as above (4-unit point samples, the 12-unit step, flag masks 1, 3 and 5): the
   simulation's movement results depend on them, so a rebuild that must stay in step with
   the original has to match sample for sample. With this a character can walk the level.
4. **Path grid.** Eight link bits per node; needed as soon as monsters move.
5. **Geometry.** Walk each packet as a list of VIF codes; per batch collect positions,
   normals, the strip table, the tag and the texture coordinates; build triangles from the
   strip positions; apply the chunk transform. Cache by data offset — packets are shared.
   Skip chunks whose texture cell is 0. No culling by winding.
6. **Textures.** Read the `.TEX` directory, load cells (all at once is fine on a PC),
   find each chunk's header at cell + offset, divide the stored coordinates by 16 and by
   the texture size. Needs the texture pixel format. Blending: honour the GS state blocks
   in the packet (alpha-tested and environment-mapped batches) and chunk flags 0x200/0x400.
7. **Moving pieces** (needed for doors and lifts, hence for most levels' scripts), then
   **water** (a flat animated quad per tile at the chunk's z is enough to start; `water_test`
   matters to gameplay, the ripples do not), **model chunks** (needs the model format),
   **lights** and **emitters** (cosmetic).
8. **Automap** last.

For lighting a PC renderer can start with the textures alone, since they are per chunk and
appear to carry the baked light; the normals are there for the dynamic lights.

## Still unknown

- The world VU1 microprograms (0x16, 0x34, 0x46, 0x48): what exactly they do with normals,
  lights and the second texture coordinate. (Since read: `docs/spec/render-pipeline.md`
  section 4.6.)
- The bit grid's layout and purpose; header +0x74; chunk flags 0x2, 0x4, 0x20000; chunk
  +0x3a; moving piece +0x1a; why some geometry chunks have texture cell 0.
- The emitter description beyond its size; the automap cell and tile coding; the water
  mask's bit order.
- Whether cell textures and the automap tile texture decode with the rules of
  `docs/formats/model-texture.md`; not tried.
- Which way the axes point relative to the screen and compass. (Answered for the screen in
  `docs/spec/render-pipeline.md` section 3: the world is right-handed with z up; camera
  space has x right, y down, z forward. The compass is still open.)
- None of this was checked on a running game (still so; see "How this was established").

## Corrections to earlier documents

- `docs/engine.md`, terrain element flag 4 "tested by ray casts": more exactly, the element
  has flagged samples, so callers that pass a flag mask must test it even when it lies
  below them (0x18a5c0, 0x185a40).
- `docs/engine.md` lists `world_fixup` as not read; it is described above.
- `docs/FORMATS.md` still lists `.world` as unknown.
- `docs/formats/model-texture.md` named `WCACHE.DAT` beside `<LEVEL>.TEX` as a level texture
  container (it has been corrected since). The world code opens only `<level>.tex` (0x181d30, 0x17d680, 0x17d830). The strings
  `wcache.hdr` and `wcache.dat` are referenced only from the equipment cache code
  (0x1a2680, 0x1a2d48); I: it is the weapon model cache, not level data.
