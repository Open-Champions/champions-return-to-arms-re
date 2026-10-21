# Drawing water

What `world_drawWaterChunk` (0x1876e0) puts in a water tile's packet, and what the height
step (0x196088) and the water VU1 entries do with the 32×32 grid. The chunk record and
the `waterenv.lmp` load are `docs/formats/world.md`. Sort order is
`docs/formats/level-draw.md` and `docs/spec/render-pipeline.md` section 8.

`tools/ref_waterdraw.py` is the executable form. It uses the chop float model, the same
one the difftest's VU1 uses. `tools/test_ref_waterdraw.py` checks it on authored numbers.
`tools/difftest_waterdraw.py` runs the same numbers through
`water_setup` (0x1875d4), `world_drawWaterChunk`, `world_drawChunk` (0x1887b8), the
height step, the simulation (0x186e38) and the VU1 microcode those entries call.

Status letters: **O** read at the address, **D** holds in the files, **I** inferred,
**U** unknown. **Executed** means the original function was run in `tools/ee_emu.py` or
`tools/vu1_emu.py` on state this note built. Nothing here was run on a console, PCSX2
or Play!.

## 1. One packet, on layer 3

`world_draw` calls `world_drawChunk`, which calls `world_drawWaterChunk` when chunk flag
0x80 is set (O 0x1887b8). The drawer builds one packet and queues it with
`gfx_addSortedPacket` (0x16b7f0) as layer **3**, parent 0, flags 0 (Executed). Flag
0x200 on the same chunk does not move it: `world_drawChunk` still queues that one
layer-3 packet (Executed). Ordinary world geometry is layer 0, and a geometry chunk
with flag 0x200 is layer 4, so water is after ordinary WORLD chunks and before those
flagged ones. There is no depth sort (`docs/formats/level-draw.md`).

The packet sets context 1 only. `TEX0_1` is written as 0 here; the texture pointer is
the third argument of the sort call, and the shared flush fills `TEX0` from it
(`docs/spec/render-pipeline.md` section 6). There is no second packet and no context-2
environment pass in this function (Executed: one sort call). Flag 0x10 is the geometry
environment flag; this drawer returns before that path.

`water_setup` stores its argument at 0x44f10c, and that is the pointer the drawer
queues (Executed). The loader passes the first `.tex` entry of `waterenv.lmp`
(`docs/formats/world.md`).

## 2. Colour and transparency

`water_setup` writes set 0 and leaves set 1 unchanged (Executed). On the load path
the reset at 0x18b270 runs first: `game_loadLevel` calls 0x1e4e88 at 0x1e5674 and
0x1e5718, and that calls the reset at 0x1e5070, both before `water_setup` at
0x1e5d80 (O). The reset stores set 0 as fix 98, colour 0x00808080 and scale
0x3cc00000, strength 41, radius 4 and timer 6, and writes set 1's fix, colour and
scale as 0 (Executed). `water_setup` then replaces set 0 with the table below,
stores strength 41, radius 10 and timer 4, and still does not write set 1
(Executed). Chunk flag 0x1000 selects set 1; otherwise set 0 (O 0x1876e0, Executed).

| | Set 0 | Set 1 (flag 0x1000) |
|---|---|---|
| FIX | 102 | 98 |
| RGBAQ | 0x006d6b5f, so R 95, G 107, B 109, A 0 | 0x00808080, so R 128, G 128, B 128, A 0 |
| Height scale | 0.0046875 (bits 0x3b999999) | 0.0234375 (bits 0x3cc00000), five times set 0 |

Setup also stores wave strength 41.0 at 0x44f064 and radius 10.0 at 0x44f068, and the
integer 4 at 0x44f06c. The strength and the radius are what the in-simulation splash
reads (section 6). The integer is `waterBumpTimer`; what reads it on the negative
countdown was not executed (section 8).

A level object can replace these words. `levelSettings_parse` (0x22e714) matches the
property name, and the `2` form is tested first so it is not swallowed by the shorter
name (O). `waterColor` and `waterColor2` take four integers. The first three are
packed `R | (G << 8) | (B << 16)` into 0x44f07c or 0x44f080. The fourth is stored as
that set's fix, 0x44f074 or 0x44f078 (Executed: `10,20,30,40` gives colour 0x001e140a
and fix 40; `1,2,3,4` gives colour 0x00030201 and fix 4). `waterWavyness` and
`waterWavyness2` parse a float into 0x44f084 or 0x44f088 and multiply it by
0x3cc00000, the static set-1 scale (Executed: 1 stays 0x3cc00000, and 0.5 is half of
that). The decimal conversion inside `sscanf` does not return in this interpreter, so
that test deposited the IEEE value and ran the original multiply. `waterBumpAmount`
and `waterBumpRadius` store the parsed float at 0x44f064 and 0x44f068 with no further
scale. `waterBumpTimer` stores an integer at 0x44f06c (Executed: 7). On the disc the
property text occurs in 65, 11, 48, 11, 41, 38 and 39 archives, in that order.

The texture is not one shared image. `game_loadLevel` loads `waterenv.lmp` (0x53db08),
finds extension `tex` at index 0 (0x171fd8) and passes that record's data pointer,
record+4, to `water_setup` (O 0x1e5d50). All 120 level archives contain that lump.
The lumps are three files, 113, 5 and 2 archives, and every first `.tex` entry is
the same size (D). Flag 0x1000 is set on 66 of the 9,884 water chunks, all of them
in the two archives that also contain `waterColor2` (D). Nine further archives
contain that property and no flagged chunk.

One `RGBAQ` covers the whole tile. Its alpha channel is 0 and is not the transparency.
The blend is `ALPHA_1` with C = FIX (0x80 means 1):

| Stored fix | `ALPHA_1` low 32 bits | High 32 bits | Result |
|---|---|---|---|
| 0 or positive | 0x64 | the fix | `(Cs − Cd) × F + Cd` |
| negative | 0x68 | the absolute value | `Cs × F + Cd` |

Set 0 and set 1 are both positive, so retail water is the first row, F = 102/128 or
98/128 (Executed, including a stored fix of −100, which took the second row).
`TEX1_1` is 0x61: bilinear magnification and minification, no mip maps (Executed).
`TEST_1` is 0x00071001 (Executed). With the field layout already used in
`docs/spec/render-pipeline.md` section 6, that word is: alpha test enabled, the test
never passes, AFAIL writes the colour buffer and not depth, depth test enabled,
ZTST = GREATER. Because the alpha test fails for every pixel, the depth comparison is
not reached: the tile is written over the colour buffer and the depth buffer is left
as the opaque geometry drew it (I from those fields).

The GIF tag is NLOOP 62, EOP, PRIM 0x15c, registers UV then XYZF2 (Executed). PRIM
0x15c is a triangle strip, gouraud, textured, integer UV, blend on, context 1
(`docs/formats/model-texture.md`). The tag's fourth word is the grid step; the GS
ignores it (NREG is 2) and the VU reads it.

## 3. The grid

A tile is 33 rows of 32 signed 16-bit heights, generated at run time. Nothing else is
stored in the chunk (`docs/formats/world.md`). The drawer turns the bounds and the
view into four matrix rows (Executed, `difftest_waterdraw.py` packet-set0):

```
step   = floor((maxX − minX) + 0.5) × S
origin = (floor(minX + 0.5), floor(minY + 0.5), chunkZ × 0.25)
```

`floor` is toward −infinity (0x3a57e8: 0.5 → 0, −1.2 → −2). S is the float at bits
0x3d088888, one ulp under the nearest float of 1/30. A width of 120 gives step bits
0x407fffff; a width of 100 gives 0x40555554 (Executed). Only the x extent is used, so
y steps by the same amount. `chunkZ` is the signed integer at chunk+0x30, not the
bounds z. The y translation at chunk+0x2c is not read.

The uploaded matrix, with `view` the four rows of `g_viewProjModel` (0x44f1c0), is:

```
row0 = scale × view.row2
row1 = view.row1
row2 = view.row0
row3 = originX × view.row0 + originY × view.row1 + originZ × view.row2 + view.row3
```

So, before the view, a sample sits at:

```
x = originX + rowIndex × step
y = originY + columnIndex × step
z = originZ + (height / 16) × scale
```

Height moves along view row 2, which is world z when that row is the world's up axis.
The scale is the only difference between the two constant sets: set 1 displaces the
surface five times as far for the same height. The frame number is not an input.
Drawing the same grid on frame 3 and frame 9 uploaded the same matrix and the same
step (Executed). There is no UV scroll.

Level option bit 8 makes `water_setup` fill every water chunk's 128-byte mask with
0xff (Executed). Other chunk kinds in the same list are left alone.

## 4. Vertices

The simulation block is a DMA `ref` of 0xa1 qwords starting at byte 0x40. Each of the
33 rows occupies 0x50 bytes: 32 heights, then a VIF tail. The tail of row 0 is empty.
Every later tail calls VU entry 0x38 and, except on the last row, unpacks the next
row's 32 heights into one of three buffers, at VU addresses 0, 0x12c and 0x258 in
turn (O 0x186bac, Executed: the same tail is present in every block the patch fills).
Entry 0x36 runs once first. It takes the clip flag from ITOP and the matrix plus the
GIF tag from memory 0..4.

Thirty-two rows are uploaded (records 1..32). Record 0 is never uploaded. The first
two calls do not kick a strip, so 30 strips are drawn. Call k (counting the first
upload as 0) places its row at `k × step` and is kicked for k ≥ 2. The kicked strip
joins that row to the previous call's row. The visible rows are records 2..32.

Each kicked call emits 62 vertices, current then previous, for column positions
`0, step, …, 30×step`. The height sample under column position i is column i+1.
Column 0 is only the left neighbour of that first sample, and column 31 is only the
right-hand lookahead. Both are used for the slope and are not positions of their own
(Executed, `difftest_waterdraw.py` vertices).

The vertex is that point, multiplied by the uploaded matrix and divided by its own w.
Screen x and y are the low 16 bits of `ftoi4(projected + 526336)`, chopping toward
zero. The UV, in 12.4 texels, masked to 14 bits, is:

```
u = ftoi4(32 + 0.0499200001 × (previousRow − thisRow) / 16)
v = ftoi4(32 + 0.0499200001 × (leftSample − thisSample) / 16)
```

A flat sample is 512 (32 texels). A sample 160 units above the sample to its left, or
above the sample in the previous row, is 504 (Executed). The constant's bits are
0x3d4c78ea. Ripples show up because the slope moves the lookup on `waterenv`, not
because the texture scrolls.

Clip (the ITOP flag nonzero) marks a vertex whose screen x or y is outside ±1000.
Exactly 1000 is kept. Projected z is not tested (Executed: z = 1200 with x = y = 0
stays clear). Vertices are emitted current-then-previous. After the first clipped
vertex of a strip, every later vertex of that strip is marked too, including one that
would have been inside; the next strip starts clear again (Executed).

The Z word stored for the GS is the float bits of `projectedZ + 2^65`. For a flat tile
at projected z 0 that word is 0x60000000, and the 24 bits the GS keeps are 0
(Executed). A ripple changes those bits only when the displacement reaches the ulp of
2^65, which the height scale does not. Combined with section 2, depth does not decide
whether the water pixel is drawn.

## 5. The wave

`runwater` (0x189844) calls 0x186e38 once a frame. That returns immediately when
`game_isFrozen` (0x1ebdf8) is nonzero (O). Otherwise it steps every simulation block
whose chunk pointer is set, then copies edges between neighbours. The step itself is
0x196088. Its arguments are the height rows, the velocity grid, and the 128-byte mask
at payload+0x10. The simulation reaches that mask as `chunk+0`, then +0x10: the block
stores the chunk at +0x12a0, and the chunk's first word is the payload (O 0x186e38,
Executed).

Heights and velocities are signed 16-bit and saturate at every add and subtract.
Shifts are arithmetic. For one column, with 0 standing in for a neighbour outside
0..31:

```
horiz(row) = sat(sat(h[c] + h[c+1]) + h[c−1])
```

Velocity row r−1 drives height row r. The 64 bytes at block+0xa50 are the velocity
for height row 0. Disturbance row 31 is not read or written. For height row r ≥ 2:

```
s = sat(sat(horiz(r+1) + horiz(r)) + horiz(r−1)) − h[r]
s >>= 3
s = sat(s − h[r])
s >>= 2
vel = sat(velocity[r−1] + s)
if the mask bit is clear: vel = 0
vel = sat(vel − (vel >> 7))
h[r] = sat(h[r] + vel)
```

Height row 1 uses 0 in place of horiz(row 0). Height row 0 is not updated from its
old samples: the value written there is the new velocity, so a row of 500 with a zero
velocity becomes 0 (Executed). A flat interior cancels. A lone velocity of 1000 on a
zero grid becomes 993 (1000 − (1000 >> 7)) and is added to the height one row later
(Executed). A clear mask bit stores velocity 0 and leaves the height, apart from row
0, unchanged.

The mask is 32 signed halfwords, twice. Halfword c is column c. Bytes 0..63 are height
rows 0..15 and bytes 64..127 are rows 16..31. Bit 15 of the halfword is the first row
of that bank, bit 14 the next, down to bit 0. A set bit means the sample is water and
the step may change it (Executed).

A block is kept while `g_drawFrame − stamp` is strictly less than 200, as a signed
difference. At 200 the simulation clears the block's chunk pointer and the payload's
simulation pointer at +8, and does not step it (Executed: 199 keeps, 200 drops). The
stamp is the frame on which the drawer claimed the block.

After every block has been stepped, two of the four neighbour indices are exchanged.
The index is a chunk index: the record is `world+0x24 + index × 0x3c`, and a
neighbour of −1 is absent (O 0x1870c0, Executed). Slot 0 (payload+0) is the column
seam. Slot 2 (payload+4) is the row seam. Slots 1 and 3 are not read here.

| Slot | Copied onto this tile | Copied back onto the neighbour |
|---|---|---|
| 0 | height column 30, rows 1..32, and velocity column 30 | height column 1 → the neighbour's column 31, and the same for velocity |
| 2 | height row 31 → this height row 1, and velocity row 30 → this velocity row 0 | height row 2 → the neighbour's height row 32, and velocity row 1 → the neighbour's velocity row 31 |

The copies see the grids after the step (Executed). Column 0 and row 1 are the
lookaheads the slope and the next step read; they are not themselves kicked as a
strip. The neighbour's column 31 and height row 32 are the lookahead on the far side,
and height row 32 is a kicked row, so this tile's row 2 is drawn as the neighbour's
far row (I from the kick rule in section 4).

`water_init` (0x187374) runs once, when the drawer claims a block. Its arguments are
the world and the new tile's payload (O, called at 0x187740). A neighbour index of −1,
or a neighbour whose simulation pointer at payload+8 is 0, contributes nothing
(Executed). Otherwise the neighbour record is `world+0x24 + index × 0x3c`, and the
samples come from that record's simulation block.

The constant is 0x3dcccccc, one ulp under 0.1. For loop row r and column c, both
0..31, the new height row r+1, column c is a weighted blend. The parts, in this
order, are:

| Slot | When | Sample | Distance |
|---|---|---|---|
| 0, payload+0 | c < 10 | neighbour height row r+1, column 31 | 10 − c |
| 2, payload+4 | r < 10 | neighbour height row 32, column c | 10 − r |
| 1, payload+2 | c ≥ 22 | neighbour height row r+1, column 0 | c − 21 |
| 3, payload+6 | r ≥ 22 | neighbour height row 1, column c | r − 21 |

Each part adds `float(sample) × float(distance) × 0x3dcccccc` to the numerator and
`float(distance) × 0x3dcccccc` to the denominator. Ten times the constant is
0x3f7fffff, still strictly under 1, so a single edge always takes the replacement
below. When the denominator compares less than 1.0 it is replaced with 1.0, and the
stored sample is the truncation of numerator / denominator (Executed). A neighbour
column of 1001 becomes 1000, 900, …, 100 across the ten columns. A lone 30000 becomes
29999, and −30000 becomes −29999. Two edges are divided by their real sum only once
that sum is at least 1: a corner with 30000 on one edge and 0 on the other stores
14999, while the same 30000 alone stores 29999. Two distance-1 weights still sum to
less than 1, so a pair of 30000 samples there stores 5999 (Executed).

Height row 0 is not written. Every disturbance sample is cleared. The per-frame step
and the two seams above are what happens after this seed.

## 6. Splashes

These are cosmetic. They are not a reflection pass.

The drawer does it only when level option bit 0x10 is set and the game is not frozen
(Executed: either condition clear skips it, and the seed at 0x404460 does not move).
It then advances that generator, `seed × 0x0019660d + 0x3c6ef35f`. When
`(newSeed >> 16) mod 300` is not 0, it stores that seed and stops (Executed).

On a hit it advances the generator twice more. The first of those two becomes the
unit interval `float(seed >> 16) × 0x37800000`, and 0x37800000 is 1/65536. The
disturb point is

```
x = minX + (maxX − minX) × u
y = minY + (maxY − minY) × u
z = minZ
```

The same `u` is used for x and y. `(maxZ − minZ) × u` is computed and is not an
argument (Executed). `water_disturb` (0x189514) is called with the world, that
point, strength 1500 and radius 6.

`terrain_height` (0x183820) then runs on the same point with radius 6. Its result
comes back in f0 and replaces the point's z (`docs/spec/world-queries.md`).
`particle_spawn` (0x18f3f8) is called with definition pointer 0x7d5d00, that point,
a zero vector, and f12 = 0. Both definition words are zero in the executable; the
names are not in this image.

The third generator step builds the second spawn's z only:

```
z = terrain + float(seed >> 16) × (1/65536) × 80 + 24
```

80 is 0x42a00000 and 24 is 0x41c00000. x and y stay put. The second definition
pointer is 0x7d5cb0, also zero in the executable, with the same zero vector and
f12 = 0 (Executed). A hit therefore consumes three seeds. Seed 324 with bounds
(0.4, −1.2, 3.5, 120.6, 10.0, 40.0) disturbs at bits 0x42a10bbd, 0x40c88098,
0x40600000. A terrain result of 123.5 then puts the second particle at z bits
0x4348b360, and the stored seed is 0xaa3e5b7d (Executed). The next seed, 325, is a
miss: one step, no calls.

`water_disturb` writes the velocity grid the step in section 5 reads. A nonzero byte
at 0x44fcec returns 0 and writes nothing (Executed). Otherwise the chunk query
(0x189240) returns up to 16 chunks. The box is x and y within the radius of the
point, and z from one below the point to 60 above it. A chunk whose flag 0x80 is
clear is left out (Executed: return 0, grid unchanged). A returned chunk with no
simulation block is counted and not written (Executed: return 1).

On a block, the width is maxX − minX. The origin is the signed integers at
chunk+0x28 and chunk+0x2c, each multiplied by 0.25. The cell count is the
truncation of `width × 0x3daaaaaa + 0.5`. The point's grid position is

```
inv = 1 / (float(count) × 12)
gx = (x − originX) × 32 × inv + 16
gy = (y − originY) × 32 × inv + 16
```

The radius goes through that same scale, and that grid radius is what the circle
uses. A cell is skipped when that radius squared is less than
`(float(row) − gx)² + (float(column) − gy)²`. The row is the world-x cell and the
column is the world-y cell. The rows and columns which are visited at all use the
world radius, not the grid radius: `trunc((g − radius) − 1)` through
`trunc((g + radius) + 1)`, clamped to 0..31 (Executed, including a 24-wide tile,
where that window cuts the circle, and an origin of 96 quarter-units).

The amount added is the truncation of `strength − d² × (strength / gridRadius²)`.
It is added to the signed sample. A sum above 32767 becomes 32767. A negative sum
is stored in the low 16 bits (Executed: 32000 at the centre becomes 32767, a cell
of −100 outside the circle stays −100, and strength −100 stores −100). A 120-wide
tile centred on the origin, strength 1500 and radius 6, writes the 3×3 at rows and
columns 15..17. The centre is 1500, the four edge neighbours are 914, and the four
corners are 328 (Executed). Moving the point in world x moves those rows.

One height step then adds velocity row r into height row r+1. The drawer uploads
height rows 1..32 and kicks from the third upload, so this 3×3 is inside the kicked
strips on the next frame. The same microcode the drawer runs produces those
vertices, and they are not the vertices of a flat tile (Executed).

Separately, the simulation itself splashes when the countdown at 0x44f200 is negative
on entry (O 0x186e38). That path reads the strength 41 and the radius 10 from section
2. A countdown that is zero or positive is decremented and the splash is skipped
(Executed: a countdown of 3 does not disturb the grid). The negative path was not
executed.

## 7. What a renderer draws

1. Queue the tile on layer 3, after ordinary world geometry and before flag-0x200
   world chunks. One pass. The texture is the `waterenv` image `water_setup` was given.
2. Colour the whole tile with the active set's RGB. A level property in section 2
   can replace that RGB and the fix. Blend as `(src − dst) × F + dst` when the fix
   is positive. Write colour. Do not update depth and do not reject the pixel for
   being behind what is already there.
3. Sample bilinear, repeating. UV is the slope formula in section 4, not a scroll.
4. Build the 30 strips from records 2..32. Height, in sixteenths times the set's
   scale, is world z. The row index steps in world x and the column index in world y,
   from the floored minimum corner, by the step in section 3.
5. Step the grid once a frame with section 5, then copy the two seams, and drop a
   block that has not been drawn for 200 frames. A splash from section 6 is in the
   velocity grid until that step, and the next frame's strips are what show it.

## 8. Open

- The simulation's splash when the countdown at 0x44f200 is negative.
- What reads `waterBumpTimer` at 0x44f06c. Setup stores 4 and the load reset stores
  6; the property parser stores the level's integer. The negative-countdown splash
  is the unread side of that word.
- Neighbour slots 1 and 3 beyond `water_init` reading them. The per-frame exchange
  does not.
