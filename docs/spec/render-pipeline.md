# Render pipeline

How *Champions: Return to Arms* (`SLUS_209.73`) turns its stored geometry into pixels: the
vector-unit programs that transform, light and assemble every 3D vertex, the data they are
fed, the Graphics Synthesizer (GS) state around each kind of draw, and what a renderer on a
PC has to do to get the same picture. `tools/vu_dis.py` disassembles the vertex programs
from your own copy of the executable.

File layouts are in `docs/formats/world.md` (level chunks) and
`docs/formats/model-texture.md` (models, textures); they are not repeated here.

## 1. How this was established

Static reading only. Nothing was run on a console or in an emulator.

| Mark | Meaning |
|---|---|
| **V** | Observed **and verified**: read in the microcode, written down as a formula, and the formula compared with the result of executing the microcode itself in a small interpreter over sample data from the disc (section 12 gives the counts). |
| **O** | Observed: read in the microcode or in the executable's code at the address given. |
| **D** | Regularity in data files, no code read for it. |
| **I** | Inferred. |
| **U** | Unknown. |

The interpreter is a scratch program written for this study (float32 arithmetic, the
divider's 7/13-cycle latency, the 4-instruction latency of the MAC, status and clip flags,
branch delay slots). It is not the console: where it agrees with a formula, that shows the
formula is a correct reading of the instructions, not that hardware behaves so. Sections 7
(2D, effects) and 8 (frame) come from one reading pass over the CPU code with addresses;
their central points (the sort rule, the frame registers, the buffer sizes) were re-read,
the rest was not.

Addresses of vertex-program instructions are written `VU 0x46` (instruction index). In the
executable, instruction *i* of the main program is at
`0x3e5ed0 + (i >> 8) * 0x808 + (i & 255) * 8`.

## 2. The frame in one page

1. Draw tasks run once per displayed frame (`docs/mainloop.md`). Each drawer appends a
   **packet** to the display list at `g_dlCursor` and registers it with
   `gfx_addSortedPacket(packet, layer, texture, parent, flags)` (0x16b7f0). O
2. A packet is a DMA chain fragment ending in a `ret` tag. Its payload is VIF1 codes:
   `DIRECT` blocks carrying GS register writes, `UNPACK` blocks that copy matrices and
   lights into vector unit 1 (VU1) data memory, `MSCAL n` to run the vertex program from
   instruction *n*, and DMA `ref` tags pointing at geometry stored in the level or model
   file, which is itself VIF1 code and is never copied. O
3. The vertex program writes finished GS primitives into VU1 memory and hands them to the
   GS with `XGKICK`. All 3D geometry reaches the GS this way; 2D sprites, text, glows and
   lines are built on the CPU and sent with `DIRECT`. O
4. At the next `gfx_beginFrame` the finished lists are streamed to the GS, layer 0 to
   layer 7 (section 8). So what is queued during frame N is rasterised at the start of
   frame N+1. O 0x19d914, 0x16c938
5. The 3D target is a **1280 × 448, 16-bit colour** buffer with a **16-bit depth** buffer.
   At frame end it is drawn, as a bilinear texture, into a 640-pixel-wide 32-bit display
   buffer; a full-screen colour multiplier and a blend with the previous image are applied
   in that pass. O 0x19c86c, 0x19bf04, 0x19cbb0

## 3. Coordinates, end to end

| Space | Convention | |
|---|---|---|
| World | right-handed, x and y on the ground, z up; positions are floats in world units | O: camera construction below; `docs/formats/world.md` |
| Level geometry | signed 16-bit, stored value + chunk translation, 4 per world unit. The vertex program divides by 16, so it works in world/4 and the chunk matrix carries a factor 4 | V |
| Model geometry | signed 16-bit, 16 per world unit; normals signed 8-bit of length 127 | V |
| Camera | x right, y **down**, z forward (also right-handed). `g_cameraMatrix` (0x44f110) is 3 rows that are the camera-space images of the world x, y, z axes, then a translation row: `cam = p.x*m[0] + p.y*m[1] + p.z*m[2] + m[3]` | O `Camera_apply` 0x2035c8: right = forward × (0,0,1), down = forward × right; `camera_setView` 0x18a2b0 |
| Projection | `sx = F * cam.x / cam.z`, `sy = F * 0.4666667 * cam.y / cam.z`, in pixels of the 1280 × 448 buffer measured from its centre. `F = 477.5 / tan(fov / 2)` (`g_projScale` 0x44f108). The game camera uses fov 50°, so F = 1024; cutscenes pass their own | O `camera_setProjection` 0x18619c, `mat4_setProjection` 0x165950; callers 0x18a260, 0x19b4dc, 0x199944 |
| Depth | `zb = 16 * (A + B / cam.z)` with `A = 4095.94 - K/(far-near)`, `B = K*near/(far-near)`, `K = 4094.94 * far`, near = 18, far = 1800. That is 65535 at the near plane and 16 at the far plane: **larger is nearer**. The depth test everywhere is "greater or equal" and the buffer is cleared to 0 | O 0x165950, 0x18a2b0; V for the conversion |
| GS primitive coordinates | `X = 2048 + sx`, `Y = 2048 + sy` in 12.4 fixed point. `XYOFFSET` is (1408, 1824), so the window is X 1408…2688, Y 1824…2272. On alternate fields the Y offset is 1824.5 (half a buffer line, for the interlaced display) | V for the vertex side; O 0x19c960 for the register |
| 2D | a sprite at screen (x, y) of a 640 × 448 layout is drawn at `X = 2x + 1408`, `Y = y + 1824`: the 3D buffer is twice as wide as the screen | O 0x17ad18 |

Remarks:

- 0.4666667 = 448/960 is the pixel aspect of a 1280 × 448 buffer shown on a 4:3 screen.
  In square-pixel terms the frustum has `tan(hfov/2) = 640/F` and `tan(vfov/2) = 480/F`:
  the fov argument is, within half a percent, the vertical field of view, and the aspect
  is 4:3. I
- Three view-projection matrices are rebuilt by `camera_setView`: `g_viewProj` 0x44f140
  (plain depth 1…4095.94, used by CPU-side projection), `g_viewProjModel` 0x44f1c0 and
  `g_viewProjWorld` 0x44f180 (camera rows × 4). The last two have their depth terms
  multiplied by 2^50 for the vertex programs' number format (section 4.3). O
- The far distance used for culling is set separately (`camera_setFarClip`, at most 1800);
  the projection always uses 18 and 1800. O

## 4. The vertex programs

### 4.1 Where they are and how they get to VU1

| Program | In the executable | Loaded at | When |
|---|---|---|---|
| Main VU1 program, 1,868 instructions | section `.vutext`, packet at 0x3e5ec0: a DMA tag, eight `MPG` blocks, then `BASE 0x100`, `OFFSET 0x17b`, `MSCAL 0` | VU 0x000–0x74b | once, by `gfx_uploadMicrocode` (0x19be08) from `engine_init`, and again on the restart path 0x19d090. O |
| Floor-decal program, 102 instructions | `.data` 0x403af0 | VU 0x79a–0x7ff | every frame, by a DMA reference whose tag carries the `MPG` code (`decal_drawTask` 0x19f4e8). O |
| Trail program, 98 instructions | `.data` 0x404150 | VU 0x79e–0x7ff | every frame the trail drawer runs (`trail_drawAll` 0x193ad0). It overwrites most of the decal program, which is why both are re-sent. O |
| VU0 program, 77 instructions | `.vutext` 0x3e5c40 (`g_vu0PoseProgram`) | VU0 | once, same function. Animation maths, not drawing; see `docs/formats/anim-audio.md`. O for the upload |

```
python3 -I -B tools/vu_dis.py SLUS_209.73 vif 3e5ec0 3ac0 --dmatag --jumptable 0x4c
python3 -I -B tools/vu_dis.py SLUS_209.73 exe 403af0 102 --origin 0x79a
python3 -I -B tools/vu_dis.py SLUS_209.73 exe 404150 98  --origin 0x79e
```

After the upload the CPU also writes VU1 data memory **directly**, through its mapping at
0x1100c000 (qword *q* is at 0x1100c000 + 16 q). Only two functions do this (O):

- `gfx_uploadMicrocode`: qword 0x3f6 = an empty GIF tag with the end-of-packet bit (and
  two GIF tag words in qword 0x3fb that no instruction reads).
- `light_writeVuConstants` (0x148728), every frame from `gfx_beginFrame`: qword 0x3fc =
  (2^23 + L, 2^23 + L, 2^23 + L, 2^23 + 128) with L = `g_worldLightLevel`; qword 0x3fd =
  2^23 four times.

### 4.2 VU1 data memory

1,024 qwords. O unless marked.

| Qwords | Use |
|---|---|
| 0x000–0x0ff | models: 64 joint matrices of 4 rows. Other drawers reuse the low end while they run: the particle type table (32 records of 4 qwords), the water constants (0–4), the trail constants (0–5) |
| 0x100–0x27a, 0x27b–0x3f5 | the two halves of the VIF double buffer. A geometry packet unpacks its input into one half (offsets 0x00–0x7f) and `MSCAL` flips the halves; the program builds the outgoing strip in the **other** half: GIF tag at +0x80, strip from +0x81. The packet's texture coordinates follow the `MSCAL` in the stream, so they land directly in the strip being built |
| 0x100–0x1ff, 0x200, 0x300 | the shadow pass uses absolute addresses instead: its own joint matrices at 0x100, sample points at 0x200 or 0x300 |
| 0x3ce–0x3e8 | decal program: matrix, GIF tag, texture-rectangle table |
| 0x3f6 | empty GIF tag, kicked between the two passes of a two-pass strip so that the first transfer has finished before the tag is replaced (I for the purpose) |
| 0x3f7 | copy of the per-light floor row (world); shell colour (models) |
| 0x3f8 | .x: a word written by entry 0x34 that no instruction reads; .y: 0/1 = strip stride 3/4 in shell mode |
| 0x3fb | .x shell distance, .w shell mode flag |
| 0x3fc | world base colour, written by the CPU each frame |
| 0x3fd | 2^23 four times, written by the CPU each frame |
| 0x3fe | .xyz = 256 / length of each column of the model matrix; .w = the model clip flag |
| 0x3ff | .y = 1/255, .z = joint count of the last pose, .w = 2^23 + 255 |

State also lives in VU registers **between** `MSCAL`s: the set-up entries only load
registers and stop, and the mesh entries rely on what the last set-up entries left.

### 4.3 Number formats the programs rely on

The programs never convert floats to integers for the GS. They add a large constant so
that the IEEE bit pattern of the sum contains the wanted integer. V

| Quantity | Constant added | Field the GS reads | Result |
|---|---|---|---|
| colour component | 2^23 | low 8 bits | the integer part (0–255 after clamping to 2^23 + 255) |
| X, Y | 2^19 + 2^11 = 526336 | low 16 bits | (value + 2048) × 16 |
| Z | 2^65 | bits 4–27 of the word | value / 2^46; with the 2^50 in the matrix this is 16 × depth |
| second texture coordinate | 2^19 + 192 | low 16 bits | (value + 192) × 16 |

The fourth word of a position qword receives the strip-table value, whose bit 15 is the
GS "do not draw" bit (XYZF2 ADC). Its other bits fall on the fog field, which is unused
because no primitive enables fogging. O

### 4.4 Entry points

The first 0x4c instructions are a jump table, two instructions per entry; `MSCAL n`
enters at instruction *n*. "Caller" is the CPU function that emits the `MSCAL`.

| Entry | Does | Caller |
|---|---|---|
| 0x00 | clears data memory, writes qword 0x3ff | the upload packet |
| 0x02 | model: load the 4 × 4 transform, compute 256/column length → qword 0x3fe | `model_emitDrawSetup` 0x175670, `world_drawModelChunk`, 0x1786c8 |
| 0x04 | world: load light floors, positions, radius², falloff | `light_emitWorldLights` 0x149b90, `light_emitWorldConstant` 0x149ab8 |
| 0x08, 0x0a | pose upload scaled by a weight; 0x0a adds to the pose already there | no `MSCAL` with these values found in the code (U) |
| 0x0c | joint matrix = pose matrix × transform, for the joint count in 0x3ff.z | `model_draw` 0x1779b0 and its variants |
| 0x0e | world: four light colours (s16 → float) | the two world light emitters |
| 0x10 | model: light directions × (256 / column length) | `light_emitModelLights` 0x149268 and variants |
| 0x14 | particles: matrix, constants, GIF tags, type table | `particle_draw` 0x194888 |
| 0x16 | world: load 4 (or 6) matrix rows, clip flag | `world_drawChunk` 0x1887b8 |
| 0x17 / 0x18 | one page of particles (0x17 is one no-op earlier) | particle pages 0x18e718, `particle_emitLists` 0x194450 |
| 0x1a | joint matrix × attach matrix → slot 0 (a part on an attach point) | `model_emitPartSetup` 0x175fb8 |
| 0x1e | copy the transform into joint slots 0–62 (model without animation) | `model_draw` |
| 0x22 | particles: switch to line mode | `particle_emitLists` |
| 0x24 | model: four light colours, and ambient + 2^23 | the model light emitters |
| 0x26, 0x28 | trail: one run of points; per-trail constants | `trail_drawAll` |
| 0x2a | shell mode on (colour, distance) or off | `model_emitShellPasses` 0x174e78 |
| 0x2c, 0x2e | shadow: joint matrices at 0x100 from the pose / from the transform alone | `model_drawShadow` 0x1762e8 |
| 0x30 | shadow: one screen-aligned sprite per sample point | the model file's sample-point block |
| 0x34 | stores a word in 0x3f8.x that nothing reads | `world_drawChunk` |
| 0x36, 0x38 | water: constants; one row of the height grid | `world_drawWaterChunk` 0x1876e0, the water patch block (0x186bac) |
| 0x3a | pose upload with weight 1 | `anim_emitPose` 0x16f880 |
| 0x3c | negate matrix row 2 (the chunk is then drawn again mirrored in z) | `world_drawChunk`, level option 0x1 |
| **0x42** | model strip, one pass | model file |
| **0x44** | model strip, two passes | model file |
| **0x46** | level strip, one pass | level file (and one sky-dome model) |
| **0x48** | level strip, two passes (environment mapped) | level file |
| 0x4a | particles: replace the matrix | `particle_draw` (particle groups) |
| 0x1c, 0x06, 0x12, 0x20, 0x32 | a delay loop; four empty entries | none found |

Which geometry uses which program:

| Geometry | Path |
|---|---|
| level chunks | 0x16, 0x0e, 0x04, 0x34, then 0x46 / 0x48 from the file |
| skinned models | 0x02, 0x10, 0x24, 0x3a, 0x0c, then 0x42 / 0x44 from the file |
| rigid models | the same with 0x1e instead of 0x3a + 0x0c; parts on attach points add 0x1a |
| weapon glow | 0x2a, then the same mesh data again through 0x42 / 0x44 in shell mode |
| water | 0x36, then 0x38 per row |
| shadows | 0x2c / 0x2e, then 0x30 |
| particles | 0x14, 0x4a, 0x22, 0x17 |
| trails, beams | 0x28, then 0x26 or the trail program at 0x79e |
| floor decals | the decal program, 0x79a / 0x79c |
| sprites, text, glows, lines, heat haze | no vertex program: CPU-built GS packets |

### 4.5 Strip assembly (all four mesh programs)  — V

The input of a packet is N positions, N normals, a strip table of N + 2 rows `(a, src, dst)`,
optionally joint weights, a block of extra copies, and one or two GIF tags. The output strip
has `nloop` vertices of `nreg` qwords (3: texture coordinate, colour, position; 4: texture
coordinate, second texture coordinate, colour, position). An *address* is a qword offset
from the first strip vertex: 3 p for position p when nreg is 3, 4 p + 1 when it is 4.

```
for k in 0 .. N+1:                      # the loop runs two rows past the vertices
    (a, src, dst) = table[k]
    copy = strip[src]                   # colour(s) and position, read first
    if k >= 2: strip[a] = vertex k-2, no-draw bit = a >> 15
    strip[dst] = copy, no-draw bit = dst >> 15
for (s1, d1, s2, d2) in extra rows:     # both sources are read before either store
    strip[d1] = strip[s1], no-draw = d1 >> 15
    strip[d2] = strip[s2], no-draw = d2 >> 15
tag -> qword before the strip; XGKICK
```

The loop is software-pipelined two vertices deep, which is why row k places vertex k − 2
and why rows 0 and 1 are placeholders. A row with `src == dst` is not skipped: the slot is
rewritten with the no-draw bit of `dst`. In the files this only ever clears the bit of
strip position 0 or 1, where it has no effect. V

The primitive is the one in the packet's GIF tag: a triangle strip, Gouraud shaded,
textured with texel coordinates. A triangle (p − 2, p − 1, p) is drawn unless p carries the
no-draw bit. No program tests winding and the GS does not cull: draw two-sided. O

**Clip rejection.** The clip flag is set when the frustum test finds the bounding box not
wholly inside its plane set (world: `world_draw` 0x189cc4 passes it and `world_drawChunk`
sends it as `ITOP` before entry 0x16; models: `drawObjects` 0x14b168 sets byte 0x41c148,
which travels as `ITOP` before entry 0x02 into qword 0x3fe.w). O. When it is set, a second
loop walks the finished strip and sets the no-draw bit of every vertex p for
which p, p − 1 or p − 2 is more than 1000 pixels from the centre in X or Y, or has a depth
value far below zero. Triangles are dropped whole, never clipped. V for X and Y; O for depth

### 4.6 Level chunks: entries 0x16, 0x0e, 0x04, 0x46, 0x48

What `world_drawChunk` puts in front of the stored packet (O 0x1887b8):

```
DIRECT   TEXFLUSH; TEX0_1 (filled in later); [ALPHA_2]; ALPHA_1; TEST_1      section 6
ITOP     clip flag
UNPACK   4 rows (6 with chunk flag 0x10)        MSCAL 0x16
UNPACK   4 light colours, s16 rgba              MSCAL 0x0e
UNPACK   6 rows: floor, x, y, z, Rsq, K         MSCAL 0x04
ITOP 0|1                                        MSCAL 0x34   (no effect)
STROW    tx, ty, tz, 0
ref      the chunk's packet in the level file
[MSCAL 0x3c, ref again]                         level option 0x1: mirrored copy
```

Rows 0–3 are `g_viewProjWorld` with the chunk's rotation folded into rows 0 and 1
(`docs/formats/world.md` gives the rotation rules). Rows 4–5, for environment-mapped
chunks, are `6 × (m00, m01, m10, m11)` and `(6 × m20, 6 × m21, 192 + scroll, 192)` taken
from the camera matrix m, the first four permuted by the chunk's quarter-turn code but
**not** rotated by a free rotation; scroll is `(tick & 0x3ff) × 0.25` when the level
option word 0x44fe08 has value 4 set. O

Per vertex — V:

```
p    = (stored position + (tx, ty, tz)) / 16          # chunk space, world/4
clip = p.x*row0 + p.y*row1 + p.z*row2 + row3
sx, sy, sz = clip.xyz / clip.w
X, Y = (2048 + sx, 2048 + sy) * 16        Z = sz / 2^46

for each of the 4 light slots i:
    d    = L[i].pos - p
    a[i] = max((|d|^2 - L[i].Rsq) * L[i].K, 0)
lit = some slot with floor < 1 has |d|^2 < Rsq
if lit:
    for each slot: a[i] *= clamp((d . n) * 255 / (|d| * 32768), L[i].floor, 1)   # n = stored normal, length 127
a[i]  = min(a[i], 1)
rgba  = base + sum a[i] * colour[i]       # base = (L, L, L, 128), qword 0x3fc
rgba  = min(rgba, 255)
```

- If all four `Rsq` are zero the program takes a short loop that writes `base` to every
  vertex. V
- `(d . n) * 255 / (|d| * 32768)` is the cosine times 0.99. A slot whose floor is 1 or
  more is not a directional term at all: it adds `a × colour` whatever the normal. O, V
- There is no lower clamp except on the lit path, and there it is applied to the vertex
  *before* the one that took the path (a pipelining artefact). A negative sum that is not
  clamped wraps: the 2^23 trick then yields `(2 × value) mod 256`. The constant light of
  −230 that `world_setPieceFlash` asks for (chunk flag 0x100, one frame) is such a case:
  the interpreter gives 52 at base level 128, 180 at 64 and 116 at 32, on all three
  channels. Whether that wrap is what the authors wanted is not known. V for the
  arithmetic
- The constant terms of the other flagged chunks are plain: flag 0x200 gives exactly the
  base level with no dynamic lights, flag 0x2000 gives base + 230, clamped to 255. V
- Program 0x48 additionally computes, per vertex, the second texture coordinate

  ```
  n' = stored normal / 16
  (u2, v2) = (row5.z, row5.w) + n'.x*(row4.x, row4.y) + n'.y*(row4.z, row4.w) + n'.z*(row5.x, row5.y)
             + 0.07 * (sx, sy)
  ```

  in texels, i.e. about `192 + 47.6 × (camera-space normal).xy + 0.07 × (screen offset)`.
  The strip is kicked twice: first with the second tag (GS context 2, second coordinate),
  then, after the empty packet at 0x3f6, with the first tag (context 1, stored
  coordinates). V
- Vertex colours are not stored in level files, and the pre-lit look comes from the
  textures; what the program adds is the base level and the dynamic lights. V, D

### 4.7 Models: entries 0x02, 0x10, 0x24, 0x3a, 0x0c, 0x1e, 0x1a, 0x42, 0x44

What `model_draw` emits (O 0x1779b0, 0x175670):

```
DIRECT   TEXFLUSH; TEX0_1; ALPHA_1; [ALPHA_2]; TEST_1                        section 6
UNPACK   4 rows T = model matrix (mat34) x g_viewProjModel
ITOP     clip flag                              MSCAL 0x02
UNPACK   3 rows: x, y, z of 4 light directions  MSCAL 0x10
UNPACK   5 rows s16 rgba: 4 light colours, ambient   MSCAL 0x24
[pose: UNPACK (count, then 3 qwords of s16 per joint)   MSCAL 0x3a]
MSCAL 0x0c (animated) or 0x1e (not animated)
[shell passes]
ref ...  one per run of adjacent shown meshes
```

Pose and joint matrices — V:

```
pose qword c of joint j (c = 0, 1, 2) = (R0[c], R1[c], R2[c], t[c])     s16: rotation / 4096, translation / 64
joint[j].row r = R_r.x*T0 + R_r.y*T1 + R_r.z*T2          (r = 0, 1, 2)
joint[j].row 3 = t.x*T0 + t.y*T1 + t.z*T2 + T3
```

Entry 0x1e writes T itself into slots 0–62 and leaves slot 63 alone, so a model with
vertices on joint 63 drawn without an animation uses whatever the last pose left there. V

Per vertex — V (weights as in `docs/formats/model-texture.md`; up to four joints):

```
M    = sum (w/255) * joint[j]                          # all four rows blended
p    = stored position / 16
clip = p.x*M0 + p.y*M1 + p.z*M2 + M3;   X, Y, Z as for level chunks
n'   = (stored normal / 32768) rotated by the 3 x 3 part of M
for the 4 light slots i:
    nl[i] = max( dir[i] . (n' * (256 / column length of T)) , 0 )
rgba = min(ambient + sum nl[i] * colour[i], 255)
```

Dividing by the column lengths of T removes the projection's scale and any model scale, so
`nl` is the plain cosine (× 0.99) between the normal and the light direction, both in
camera space. The directions are uploaded with z negated because the projection's depth
column is negative (`light_emitModelLights`, 0x149268). There are no positional terms in
the vertex program: point lights are turned into directions and pre-attenuated colours on
the CPU, once per model. O, V

Program 0x44 adds the second texture coordinate
`(192 + 64 × c.x, 192 + 64 × c.y)` texels, c = the camera-space unit normal (× 0.99), and
kicks the strip twice exactly like program 0x48. V

**Shell mode** (entry 0x2a, models with header flag 0x20). O, not run in the interpreter.
The CPU uploads `(1, distance, rgba)` and re-sends the meshes; programs 0x42/0x44 then take
a different loop: no lighting, position = `p + shellNormal / 32768 × distance` (the shell
normals are a second normal block in the packet, found through the middle value of strip
row 0), colour = the uploaded rgba for every vertex, one kick with the first tag. A final
upload with 0 switches the mode off.

### 4.8 Water: entries 0x36, 0x38 — O, not verified numerically

`world_drawWaterChunk` unpacks four matrix rows and a GIF tag to qwords 0–4 and calls 0x36
(with `ITOP` as the clip flag). The tile's simulation block is itself VIF data: for each of
33 rows, 32 signed 16-bit heights unpacked to one of three rotating buffers, then
`MSCAL 0x38`. Each call makes the vertices of that row (height ÷ 16 along one matrix axis,
column and row counters stepping by a constant along the other two), projects them, and
emits a strip of 62 vertices joining the row to the previous one. The texture coordinate
is `32 + 0.0499 × (height difference to the previous row, to the previous column)` texels:
the water texture is looked up by surface slope, which is what makes ripples visible on a
flat-coloured surface. There is no per-vertex colour (the tag's registers are texture
coordinate and position; one `RGBAQ` is set for the whole tile).

### 4.9 Shadows: entries 0x2c, 0x2e, 0x30 — O for the microcode; the CPU side was only skimmed

`model_drawShadow` builds a small orthographic matrix whose translation already contains
the 526336 bias (no perspective divide is done), uploads it with a GIF tag to absolute
address 0x300, and calls 0x2c (pose present) or 0x2e to fill a second set of joint matrices
at 0x100. The model's sample-point block then unpacks groups of up to 45 points and calls
0x30, which emits one GS sprite per point: centre = joint matrix × point, half-size = the
point's size word × a scale, texture rectangle (4, 4)–(26, 26) of a 32 × 32 blob. The
sprites are drawn through GS context 2 retargeted at a 128 × 128 16-bit surface
(`bigblank.tex`); that surface is afterwards drawn on the ground. Directions come from the
three nearest lights and the sun (`light_pickShadowLights` 0x148c98). How the ground quad
is built was not read.

### 4.10 Particles: entries 0x14, 0x4a, 0x22, 0x17 — O, not verified numerically

A particle is two qwords of signed 16-bit values: `(x, y, z, birth tick)` and
`(256 vx, 256 vy, 256 vz, 4 × type)`. Its type record (four qwords, uploaded to qwords
0–127 each frame) holds two texture corners, gravity, size and size rate, start colour and
colour rate. Entry 0x14 loads a matrix whose x, y, z are pre-scaled so that the VU clip
instruction tests ±800 × ±400 pixels and the depth range. Per particle:

```
age    = now - birth
pos    = p0 + v * age / 16 ;  pos.z += gravity * age^2
size   = size0 + rate * age
colour = clamp(c0 + c1 * age, 0, 255)
centre = project(pos);  corners = centre -/+ (2 * size / w, size / w)     # 2:1 because the buffer is 1280 wide
```

Output is one GS sprite per particle (colour, corner texture coordinate and position
twice); a particle outside the clip volume gets the no-draw bit. Entry 0x22 selects a
second loop that draws each particle as a two-vertex line between two ages (I for the
exact ages). 30 particles per page; pages are DMA-referenced in place.

### 4.11 Trails and beams: entries 0x28, 0x26 — O, not verified numerically

A trail is a ring of points `(2x, 2y, 2z, stamp)`. Per point the program projects the
point, takes the screen-space direction from the previous point, and offsets
perpendicular to it by `width / w` (doubled in x), giving two strip vertices. The texture
coordinate along the trail is `age × 128 / lifetime` texels, across it the two edges of
the trail's row in `trail.tex`. The first chunk of a trail also emits a tiny GS packet
with the trail's colour and its `ALPHA_1` value. Runs of at most 32 points are joined by
re-emitting the last pair. Trails with per-vertex colour use the separate program at
0x79e (not read). A beam is two trails rebuilt every frame.

### 4.12 Floor decals: the program at 0x79a — O, not verified numerically

Three qwords per decal: colour; centre × 4 with z raised by 3 units; `(cos, sin) × size × 4`
and the address of its texture rectangle. The program forms the four corners
`centre ± (c, s, 0)` and `centre ± (s, −c, 0)`, transforms them with `g_viewProjWorld`,
and emits a four-vertex strip. If any corner is outside the ±1000-pixel box the quad is
dropped.

## 5. Lights

### 5.1 Level light: sun, fill, ambient, base level

The level's light is a small record at 0x5d3448 (O):

| Field | Meaning |
|---|---|
| `g_sunDirWorld` 0x5d3448 | unit vector **towards** the directional light |
| 0x5d3474, 0x5d3478 | sun and ambient colour as set (rgba bytes); 0x5d346c, 0x5d3470 are the copies multiplied each frame by `g_lightScale` 0x4039ac (cutscene fades) |
| `g_worldLightLevel` 0x5d347c | the colour every level vertex starts from |

`game_loadLevel` fills it with `light_setLevelLight` (0x14a2d8) from three marker objects
in the level's `objects.ob`, whose **positions** are the values (O 0x158bcc, 0x158c6c,
0x158d0c, 0x1e60e0–0x1e6154):

| Object | Position means | Default when absent |
|---|---|---|
| `charAmbient_Light` | ambient (r, g, b) = position × 0.5 | (0x20, 0x20, 0x20) |
| `charDirectional_Light` | sun (r, g, b) = position × 0.5 | (0x44, 0x44, 0x44) |
| `charDirectional_LightD` | direction towards the sun | (0, −1, 1) |

Both alphas are 0. The base level is 0x80, or 0x40 / 0x20 when level option bit
0x04000000 / 0x20000000 is set (the per-level option word 0x44fe08).

`light_recalcSun` (0x148018, a task) rotates the sun direction into camera space each
frame and derives the **fill** direction: the sun direction with x and y negated and z
halved, normalised. The fill colour is 0.8 × the ambient colour as set. O 0x148340

### 5.2 Light nodes

Point lights are nodes in a 90 × 90 grid of 256-unit cells (`g_lightGrid`). A node has a
position (+0x30), a colour for models (+0x0a, s16 rgb), a colour for level geometry
(+0x12, s16 rgba), radius and falloff for each (+0x1c/+0x20 and +0x24/+0x28), and the
floor (+0x2c). O. Sources: the level's light chunks (16 slots, flicker included; they set
both colours and radii alike, falloff 1/R², floor 0 — O 0x18ba18), `LightEffect` objects,
torches and spell effects (`light_link`, 96 callers; not read individually).

### 5.3 What a level chunk receives  — O 0x149b90

The four nodes nearest the chunk's centre among those whose box overlaps the chunk's
bounds. Nodes with floor < 1 fill slots from 0 up, the others from 3 down. Positions are
rotated into chunk space and multiplied by 0.25; `Rsq = R² / 16`, `K = −16 × falloff`, so
with falloff 1/R² the attenuation is `1 − D²/R²` in world units. Chunks with flag 0x200,
0x2000 or 0x100 get a single constant term instead (0, 230 or −230) from
`light_emitWorldConstant`.

### 5.4 What a model receives  — O 0x149268

| Slot | Direction | Colour |
|---|---|---|
| 0, 1 | from the model's position towards each of the two best nodes (smallest D² − R²) | node rgb × clamp((R² − D²) × falloff, 0, 1) × per-object scale; alpha 0 |
| 2 | fill | `g_objFillColor` 0x5db380 |
| 3 | sun | `g_objSunColor` 0x5db378 |
| ambient | — | `g_objAmbient` 0x5db370 |

The three per-object colours start as the level's and are changed by the drawing code of
individual objects, then put back by `light_resetObjectLight` (0x148340, 32 callers):

- `light_addObjectAmbient` (0x148140) adds a signed bias to the ambient — the colour bias a
  creature gets while a status effect runs (`docs/creatures.md`, +0x70);
  `light_setObjectAmbient` (0x14a0c8) replaces it (hit flash);
- `light_scaleObjectLight` (0x148210) multiplies all of them by an (r, g, b) factor — the
  tint presets;
- `light_setObjectSun` / `light_setObjectFill` (0x14a150, 0x14a1d8) replace the sun or
  fill direction and colour for one draw. `creature_drawPropLight` (0x10ab18) calls them
  with a direction built from two angles and a colour with noise flicker: these are the
  `light1` / `light2` properties of a creature.

Scenery models placed by the level choose a simpler set by the lighting word of their
chunk: full set, ambient only (`light_emitModelAmbientOnly`), or sun and fill without
point lights (`light_emitModelLightsNoPoint`). O 0x188590–0x188640

Because model textures use the GS texture function "highlight 2" (section 6), a light's
**alpha** is not transparency: the vertex alpha is added to the texel colour. Level and
point-light alphas are 0, so this only matters when code sets an ambient alpha. I

## 6. GS state per kind of draw

Blend values are the raw `ALPHA` register; As is the source alpha with 0x80 = 1.

| `ALPHA` | Result |
|---|---|
| 0x01 | `src × (1 − As) + dst × As` — alpha 0 is opaque |
| 0x02 | `src × (1 − As)` — nothing of the destination |
| 0x09 | `src + dst × As` |
| 0x2a | `src` |
| 0x44 | `src × As + dst × (1 − As)` — the usual blend |
| 0x48 | `dst + src × As` — additive |
| 0x64 + FIX | `src × F + dst × (1 − F)`, F = FIX/128 |
| 0x68 + FIX | `dst + src × F` |

`TEST` values: 0x587f4 = no alpha test, depth ≥, depth written. 0x582f5 = pass alpha <
0x2f, depth ≥. 0x507f5 = pass alpha < 0x7f, depth ≥. 0x71001 = depth >, **no depth
write**. 0x3001d = pass alpha > 1, depth always. 0x31001 = depth always, no depth write.
0x5001d = pass alpha > 1, depth ≥.

| Draw | Texture function | `ALPHA_1` | `TEST_1` | Notes |
|---|---|---|---|---|
| Level chunk | modulate, RGBA (D: all 213 textures of one level file) | 2; 1 if chunk flag 0x200 or 0x400; 0x48 if 0x10000 | 0x587f4; 0x582f5 if flag 0x400 | O 0x1887b8. The stored packet repeats the same two registers (D: every packet of the four levels looked at) and may change them between batches |
| Level chunk, env-mapped | first pass: fixed environment texture, context 2, `ALPHA_2` 0x2a, `TEST_2` 0x50013; second pass as above with `ALPHA_1` 9 | | | O 0x1887b8, 0x19c540 |
| Model | highlight 2, RGBA (D: model textures) | header +0x18: 1 or 9 mostly; a fade replaces it by 0x64 + (0x80 − fade) | 0x507f5 | O 0x175670 |
| Model, two-pass | first pass context 2: environment texture; `ALPHA_2` = 0x64 + header +0x20 | | | O |
| Weapon glow shell | **untextured** (`PRMODECONT` 0, `PRMODE` 0x48) | 0x48 (or 0x44) | 0x71001 | O 0x174e78 |
| Water tile | modulate | 0x64 + F or 0x68 + F, F = a per-level constant; one colour for the tile | 0x71001 | O 0x187830–0x187948; bilinear |
| Shadow blobs | into the 128 × 128 surface | | `TEST_2` 0x31001 | O (frame pass) |
| Floor decals | modulate | 0x44 | 0x5001d, depth writes masked with `ZBUF` | O 0x19f664 |
| Particles | modulate | 0x44 or 0x48 by the definition's mode | 0x71001 | O 0x1949c4; point sampled |
| Trails, beams | modulate | 0x44, 0x48 or 0x09 by flags | 0x71001 | O 0x193c94; `CLAMP_1` region clamp while drawing |
| Glow sprites, lines | modulate / none | 0x44 or 0x48; lines 0x48 | 0x71001 | O 0x1908c4, 0x193568 |
| Sprites, text | modulate | 0x44 | 0x3001d | O 0x17a3e8, 0x1801a0; Z constant; point sampled |
| Rectangles | none | 0x44 | 0x31001 | O 0x17bd9c |

Texture binding. `gfx_dmaHandler` patches each packet's `TEX0` just before it is sent:
base and palette pointers from the texture cache, everything else (size, format, the
texture function and the RGBA bit) from the texture header. No mip maps anywhere. O

**Filtering.** `TEX1_1` is not written by the level or model drawers. The present pass
ends each frame with `TEX1_1 = 0x61` (bilinear), and that is what layer 0 inherits; the
2D drawers set 1 (point sampling) and do not restore it, so a model drawn in a UI layer
after sprites is point sampled. O for the writers, I for the consequence.

**Wrapping.** `CLAMP_1` is written only by the trail drawer and reset to 0; `CLAMP_2` is 0.
So level and model textures **repeat**. The second texture coordinates are built around
192 on a 128-texel environment texture precisely because of that. O for the writers; that
the register is 0 at start rests on the GS reset state (I).

**Environment texture.** GS context 2 is set up once: same target and depth buffer, a
fixed 128 × 128 32-bit texture (`TEX0_2`, modulate, RGB only), bilinear, repeat. The
texture is the level's `envtex.etex`, uploaded when the level starts (0x19e440 from the
main loop). O

## 7. 2D and effects built on the CPU — O (one pass; see section 1)

- **Sprites** (`ui_drawSpriteImpl` 0x17b590 and variants): a GS sprite of two vertices,
  texel coordinates, `PRIM` 0x156, colour 0x80808080 = unmodified. Interface textures are
  two stacked fields (`docs/formats/model-texture.md`): in the normal mode only the half
  matching the current display field is drawn, stretched over the full height; in the
  half-rate mode both halves are drawn over the same rectangle under the GS scanline
  mask. A PC renderer weaves the two halves once and draws one quad.
- **Text** (`text_begin` 0x1800b8 … `text_end` 0x180500): one packet per begin/end pair,
  two-register vertices (texel coordinate, position), same state as sprites. A font is a
  texture, a 256-entry character map, 16-byte glyph records (code, u0, u1, v0, v1,
  y offset, advance, first kerning record) and 6-byte kerning records. Clipping is a GS
  scissor (`text_setClip`), not per glyph.
- **Glow sprites** (`glow_add` → `glow_draw` 0x1907d0): projected on the CPU with
  `g_viewProj`, pulled towards the camera by a bias, drawn as a sprite of half-size
  `(2s, s)` or as a rotated quad; additive or blended; depth tested, not written.
- **Lines** (`gfx_queueLine` → `line_draw` 0x1934c0): GS lines, additive.
- **Heat haze** (`particle_drawHaze` 0x18fe18): copies a small rectangle of the draw
  buffer into `blank.tex` with a GS local transfer and draws it back, displaced, as a fan
  whose alpha falls to 0 at the rim.
- **Screen effects** are in the present pass (section 8).

## 8. Frame, buffers and order — O (one pass; the items marked ✓ were re-read)

| | |
|---|---|
| Draw buffer | 1280 × 448, 16-bit colour (`FRAME_1`: width 20 × 64, PSMCT16), not double buffered ✓ 0x19c8fc |
| Depth buffer | 16-bit (`ZBUF_1` = 0x0200008c) ✓ 0x19c910. Cleared to 0 together with the colour buffer by 20 untextured sprites drawn with the depth test set to "always", when the caller passes a clear colour (the main loop always does). 0x19ca0c |
| Per-frame defaults | scissor 0…1279 × 0…447; `XYOFFSET` (1408, 1824 or 1824.5); `DTHE` 1; `COLCLAMP` 1; `PRMODECONT` 1. No default `ALPHA`, `TEST` or `TEX1`: every drawer sets its own ✓ 0x19c86c |
| Display | NTSC interlaced. Two 640 × 224 32-bit buffers, one per field, in the normal mode; one 640 × 448 buffer in the half-rate mode (`g_displayRateMode`). 0x19b6e4, 0x19d364 |
| Present | the draw buffer is sampled bilinearly, half a texel off, into the display buffer: a 2 × 2 box filter in the normal mode. Dither is on while drawing (16-bit target) and off here. 0x19bf04 |
| Colour multiplier | present vertex colour = `2 × v × (0.8 × brightness + 0.2)` per channel, v from `gfx_setColorOffset` (0x80 = neutral, moving back to neutral by 4 per frame); the texture function multiplies by it. This is how fades to black and the brightness option work. 0x19cbb0 |
| Blend with previous image | the present sprite is blended with a FIX alpha taken from `gfx_setScreenDarken` (0x80 = none, creeping back by 3 per frame), in the normal mode after the other display buffer has been copied into the target. I for the visible result: the new image mixed with the last displayed one, not a darkening. 0x19cbb0 |

**Order.** There is no depth sorting anywhere. ✓ 0x16b7f0

- Eight layers, sent 0 → 7, each closed by a GS `FINISH` before the next starts.
- Inside a layer: a packet with a texture already used in that layer this frame goes
  directly after the last packet with that texture (so same-texture packets are together,
  in submission order); any other packet, and every packet queued with flag 1 (all 2D),
  goes to the **front**. Texture groups therefore run in reverse order of first use and
  2D packets in reverse submission order.
- A packet queued with a parent is chained behind the parent (model parts).

| Layer | What is queued there |
|---|---|
| 0 | level chunks; scenery models; floor decals (queued before the world, hence sent after it in this layer); a few props |
| 1 | creatures, players, props, items, their shadows |
| 2 | heat haze |
| 3 | water; spell and projectile models; lines; one pass of glows |
| 4 | level chunks with flag 0x200; scenery models with header flag 0x08 (trees); particles; trails; the other pass of glows |
| 5 | automap, compass, some name sprites |
| 6, 7 | interface and text |

So translucency is ordered by kind, not by distance: opaque world and characters first
with depth writes, then water, then the alpha-tested and blended scenery and all effects
with depth test but **no depth write**.

## 9. What a modern renderer has to do

Nothing in the picture depends on the PS2 tricks; they can all be replaced by their
plain meaning.

1. **Geometry.** Decode packets as the format documents say; build triangles from the
   strip table with the rule in 4.5; drop triangles that repeat a vertex; draw two-sided.
2. **Transform.** World: `(stored + translation) / 4`, then the chunk rotation, gives
   world units. Models: `stored / 16`, blended joint matrices, then the model matrix.
   Camera: x right, y down, z forward; a standard perspective projection with
   `tan(hfov/2) = 640/F`, `tan(vfov/2) = 480/F`, near 18, far 1800, F = 1024 for the game
   camera. A normal depth buffer of 24 bits or more replaces the 16-bit one; keep "nearer
   wins, equal passes".
3. **Level colour.** Vertex colour = base level (0x80 unless the level says otherwise) +
   up to four point lights per chunk with attenuation `1 − D²/R²` and a clamped cosine,
   as in 4.6; final = texel × colour / 128, so 0x80 leaves the texture unchanged and
   lights can brighten it up to twice. Start with the base level alone: the textures are
   pre-lit.
4. **Model colour.** ambient + sun + fill + two point lights, each `colour × max(N·L, 0)`,
   clamped at 255; final = texel × colour / 128 + vertex alpha. Sun direction, sun and
   ambient colour come from the three marker objects; fill = opposite horizontal
   direction at half the height, 0.8 × ambient.
5. **Alpha.** Texture alpha 0 is opaque in model and level textures. Level chunks:
   `src × (1 − a)` (no blending with the background) unless flagged, then
   `src × (1 − a) + dst × a`. Models: by header value. Alpha test thresholds as in
   section 6. As = texel alpha × vertex alpha / 128 for level chunks (vertex alpha is
   128 unless a light has alpha), texel alpha alone for models.
6. **Two-pass surfaces.** Draw the environment texture first, modulated by the same
   vertex colour, with coordinates `(192 + 64 n.x, 192 + 64 n.y) / 128` (models) or the
   formula of 4.6 (level), repeat addressing; opaque for level chunks, weighted by header
   +0x20 / 128 for models (0x80 = opaque). Then the base texture over it with
   `src + dst × a`.
7. **Order.** Follow the layer table. Opaque: level, models. Then water, then flagged
   chunks, trees, particles, trails and glows with depth test and no depth write, then
   the interface. No sorting by distance is needed to match the original.
8. **Sampling.** Bilinear, repeat, no mip maps for 3D; point sampling for interface art.
9. **Post.** Multiply by the fade colour; optionally blend with the previous frame when
   the game asks for it. Supersampling 2× horizontally reproduces the original's
   smoothing.

Simplest correct order of implementation: (1) camera and projection with untextured
chunk boxes; (2) level geometry with textures at base level, blend equation 2, alpha
test; (3) rigid models with texture and the sun/ambient terms; (4) skinning; (5) layer
order, depth-write rules, model blend values; (6) point lights on level and models;
(7) environment passes; (8) water as a flat textured grid, then its slope-indexed
texture; (9) particles, glows, trails, decals; (10) shadows; (11) interface and text;
(12) fades.

## 10. `tools/vu_dis.py`

Standard-library Python 3. Modes: `exe` (address in an ELF, mapped through the program
headers), `raw` (file offset), `vif` (walks a VIF packet, lists every code, disassembles
the microcode of each `MPG` at its load address), `sections`. Output per instruction: VU
address, source address, the I/E/M/D/T flag bits, upper instruction, lower instruction (or
the float constant when the I bit is set). Branch targets get labels; `--entry` names
them; `--jumptable N` marks the entry table.

An encoding the tables do not cover is printed as `???` with the raw word, and bits that
must be zero for the decoded instruction but are not are reported as "reserved bits";
both are listed again on stderr and make the exit status 3. All 2,145 instructions of the
four programs in this executable decode with neither. The instruction tables were written
from the published VU instruction set; the interpreter used for section 12 decodes
independently of them only in code, not in source of knowledge.

## 11. Not reached

- **Hardware confirmation.** Nothing was compared with a console or an emulator frame.
  Float rounding on the VU (the interpreter rounds to nearest) can move a colour or a
  1/16-pixel coordinate by one unit.
- **Shadows**: the CPU side of `model_drawShadow` (the projection, how the 128 × 128
  surface is put on the ground, its blend state) was skimmed only.
- **Water, particles, trails, decals, shell mode**: read in the microcode, not run in the
  interpreter. The trail program at 0x79e and the particle line loop (VU 0x0a9) were not
  read in detail. The water matrix (which axis is height) and the water constants at
  0x44f074–0x44f080 were not traced.
- **Entries 0x08 / 0x0a** (weighted pose upload): no caller found; either unused or
  reached through a computed `MSCAL`.
- **`light_emitModelLightsVariant`** (0x149828) and the automap drawer 0x168cac.
- **Level texture alpha**: whether level textures really keep alpha 0 on solid texels
  (which the blend equation 2 requires for them not to darken) was not checked in the
  texture data; the level texture upload packets did not parse with the model texture
  walker.
- **`TEXA`, initial `CLAMP_1`**: no writer exists in the executable; they rest on the GS
  reset state.
- **Per-object code**: the 96 callers of `light_link` and the individual effect classes
  were not read; `Creature_draw` itself was not re-read (its light calls are taken from
  the callee side and `docs/creatures.md`).
- Of a mesh packet's inputs only the fog bits of the position word go unused (and the
  shell normals outside shell mode); nothing else in a packet is unexplained.

## 12. What was checked in the interpreter

Random camera, field of view, lights (positive and negative colours, floors 0, 0.3, 1),
base levels and clip flag for every case; formula and microcode output compared per strip
vertex; tolerance one unit in X, Y (1/16 pixel), depth and colour, exact for the stored
texture coordinates and the no-draw bit beyond strip position 1.

| Program | Sample | Strip vertices compared | Differences |
|---|---|---|---|
| 0x46 (with 0x16, 0x0e, 0x04) | 30 chunks of one arena level, 3 trials each | 37,692 | 0 |
| 0x46 | 60 chunks of a second level | 46,230 | 0 |
| 0x48 | 40 env-mapped chunks of that level | 90,555 | 32, all one unit (1/16 texel) in the computed coordinate |
| 0x44 (with 0x02, 0x10, 0x24, 0x3a, 0x0c, 0x1e) | a monster, a barrel, a player body with 1–4 joints per vertex, an axe | 17,352 for the body, 3,631 and 1,022 and 422 for the others, each ×4 set-ups | 0 with a pose; without a pose only vertices on joint 63 differ, as explained in 4.7 |
| 0x42 | a hair part, two item models | 1,390, 231, 117, each ×4 | 0 |

## 13. Corrections to earlier documents

- `docs/formats/world.md`, chunk flags: 0x200/0x400 "`ALPHA_1` = 1 instead of 2" is right,
  but 2 is not a blend with the frame buffer: it is `src × (1 − As)`. "0x10000 … (I:
  additive)" is confirmed: 0x48 is `dst + src × As`.
- `docs/formats/world.md`, "the lights (entry 0x34)": the lights are loaded by entries
  0x0e and 0x04; entry 0x34 only stores a word that nothing reads.
- `docs/formats/world.md` and `model-texture.md` leave the handedness and screen axes
  open: world right-handed, z up; camera x right, y down, z forward.
- `docs/formats/model-texture.md`, entry 0x30 "(shadow)": it draws into an off-screen
  surface through its own joint matrices at 0x100 (entries 0x2c/0x2e), not to the screen.
- `docs/formats/model-texture.md`, "which texture context 2 holds was not traced": it is
  the level's `envtex.etex` (0x19c77c, 0x19e440); "who loads `.etex`": the main loop,
  through 0x19e440. "Texture wrap and filter modes … inherited": see section 6.
- `docs/formats/model-texture.md` says program 0x46 in a model has no known source for
  its row registers; 0x175950, which would set that program up for a model (entries 0x16
  and 0x34), has no caller. U remains how the one sky dome that uses it is drawn.
- `gfx_setScreenDarken` (`docs/engine.md`, `docs/mainloop.md`): the value it keeps is the
  FIX alpha of the present pass, which mixes the new image with the previous one; it does
  not darken by itself (section 8, I for the visible result).
- `symbols/engine.tsv`: `ui_drawRect` takes two corners and (layer, colour), not
  (x, y, w, h, colour) (0x17be38–0x17be74); the unnamed fourth argument of
  `ui_drawSpriteImpl` is the sort layer (0x17b888).
- Not stated before: packets queued in frame N are rasterised at `gfx_beginFrame` of
  frame N+1, so anything that reads "what was drawn" lags the draw tasks by a frame.

No patches are proposed and no ledger rows: nothing here writes shared game state. The
per-machine items this area touches (light flicker from the cosmetic generator, field
parity, display rate mode) are already listed in `docs/engine.md` and `docs/mainloop.md`.

New names are in `symbols/render.tsv`.
