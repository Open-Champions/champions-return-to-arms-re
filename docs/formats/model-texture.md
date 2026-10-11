# Models (`.vif`) and textures (`.tex`, `.etex`)

How characters, monsters, props and item models are stored in the lumps of *Champions: Return
to Arms* (`SLUS_209.73`), and how their textures are stored. Written for someone building a
native loader. `tools/model_info.py` reads both formats and is the executable form of this
document.

Nothing here was run on a console or an emulator. That is still true of these formats:
the emulator the project now runs the game in (Play!, not a PlayStation 2 and not PCSX2;
`FINDINGS.md`, "Run on the live game" (rows V1–V23) and `docs/issues/live-rig.md`) is used with
no video output, so nothing drawn was compared. The layouts were read from the executable
and then checked against **every** model and texture on the US v2.00 disc with the tool.

Status letters used in the tables:

| | |
|---|---|
| **O** | Observed: read in the code at the address given, and the samples agree |
| **D** | Observed in the data only: holds in every file on the disc, no code that reads it was found or read |
| **I** | Inferred |
| **U** | Unknown |

All integers are little endian. "qword" means 16 bytes.

## Contents on the disc

| | Count | Where |
|---|---|---|
| `.vif` models | 2,323 | 385 top-level `.LMP` files and the `dome.lmp` of 21 level `.GOB` files |
| `.tex` textures | 3,109 | the same lumps; also interface, effect and menu lumps |
| `.etex` textures | 127 | one `envtex.etex` in the `env.lmp` of each level `.GOB` |

- Every `.vif` has a `.tex` of the same base name in the same lump (D, 2,323 of 2,323). The
  model file holds **no texture name and no material record**. The caller passes one texture
  with each draw call (`model_draw` 0x1779b0, second argument), and the names come from tables
  in the executable or the level: creature class definitions (`{name, pointer}` pairs,
  `x.vif` then `x.tex`), the item model table `g_itemModels` 0x3e9ce0, prop properties, and
  the model chunks of a `.world` file (`docs/formats/world.md`). One model, one texture.
- Level geometry and its textures (`<LEVEL>.TEX`) are a different container;
  see `docs/formats/world.md`. The texture *header* described below is the same one.
  The earlier version named `WCACHE.DAT` beside `<LEVEL>.TEX`; it is not a level texture
  container. The world code opens only `<level>.tex` (0x181d30, 0x17d680, 0x17d830), and
  the strings `wcache.hdr` and `wcache.dat` are referenced only from the equipment cache
  code (0x1a2680, 0x1a2d48) — Inferred there: the weapon model cache.
- Fix-up after loading is by extension in `lump_fixupEntry` (0x17153c): `.vif` →
  `model_relocate` (0x179130), `.tex` → `tex_relocate` (0x179e10). `.etex` is recognised and
  left alone.

## Units and axes

- Positions are signed 16-bit, 16 to a world unit (O: the vertex programs convert with a
  "divide by 16" instruction, 0x3e7668 and 0x3e7c10; the CPU-side readers multiply by 0.0625,
  0x178e18). Bounding boxes and hull points are whole world units in signed bytes.
- Z is up, in a right-handed world; camera space has x right, y down and z forward
  (`docs/spec/render-pipeline.md` section 3, which settles what this section left open).
  The samples looked at face −Y with their left and right along X (D: the exported
  player, skeleton and cyclops stand upright with the face towards −Y). A standing human
  player body is about 75 units tall.
- Vertices are stored in the model's rest pose, in model space — not relative to their
  joints (D: unposed exports are intact figures; O: the joint matrices the vertex program
  multiplies by are filled with the plain model transform when there is no animation,
  0x3e71b8).

## `.vif`: header

The file is a multiple of 16 bytes. Offsets are from the start of the file.

| Offset | Type | Meaning | Status |
|---|---|---|---|
| 0x00 | u64 | For a part worn on a body (hair, beard, armour piece): the meshes of the **body** that must not be drawn while this part is. `Player_drawEquipped` clears these bits in the body's show mask after drawing each part (0x1a3de4–0x1a3df4). Non-zero in 309 files, all in `SELECT.LMP` / `SELECT2.LMP` | O |
| 0x08 | u64 | meshes hidden by default. The show mask starts as the complement of this (`model_buildHideMask` 0x179550) | O |
| 0x10 | u16 | flags, below | |
| 0x12 | s8 | mesh count *n*, 1 to 64 | O |
| 0x13 | s8 | for a part: which attach slot of the parent it sits on; −1 = none (`model_emitPartSetup` 0x175fb8, `creature_drawHeldPart` 0x117f44). 0–8 occur | O |
| 0x14 | u32 | 0 in every file; no reader found | D |
| 0x18 | u64 | GS `ALPHA_1` register value for the model (`model_emitDrawSetup` 0x175670). Values on the disc: 1 (1,796 files), 9 (516), 0x8000000029 (9), 0xac00000029 (1), 0x48 (1) | O |
| 0x20 | u8 | FIX alpha for the second GS context: `ALPHA_2 = FIX << 32 \| 0x64`, written only when flag 0x10 is set. 0x80 in 516 files, 40 in 9, 58 in 1 | O |
| 0x21 | u8 | variant table, offset ÷ 16 (flag 0x02) | O |
| 0x22 | u8 | attach table, offset ÷ 16 (flag 0x04) | O |
| 0x23 | u8 | facing-point table, offset ÷ 16 (flag 0x40). 0 in every file | O (code only) |
| 0x24 | u8 | sample-point block, offset ÷ 16; 0 = none (596 files have one) | O |
| 0x25 | u8 | hull-point table, offset ÷ 16; present in every file | O |
| 0x26 | s8 | number of mesh tables. `model_relocate` raises anything below 1 to 1; the drawers clamp the requested table index to count − 1. 1 in every file, so nothing on the disc has a second level of detail | O |
| 0x27 | u8 | effect segment, offset ÷ 16; 0 = none (128 files) | O |
| 0x28 | u32[tables × (n + 1)] | mesh offsets from the start of the file. Mesh *i* is the bytes `[off[i], off[i+1])`. `model_relocate` adds the load address to every entry | O |
| after | 10 bytes × n | mesh records | O |

Flags (+0x10):

| Bit | Meaning | Status |
|---|---|---|
| 0x01 | Not established. Set in 1,020 files; 893 of those use a joint other than 0, against 11 of the 1,303 files without it. No reader found | U |
| 0x02 | variant table present (tested at 0x179550) | O |
| 0x04 | attach table present (350 of 350) | D |
| 0x08 | when the model is placed as world scenery it is queued in sort layer 4 instead of 0 (`world_drawModelChunk`, 0x188770). 26 files, trees among them | O |
| 0x10 | two-pass model: the second GS context is set up from +0x20 and the packets use vertex program 0x44 (526 of 526) | O |
| 0x20 | the packets carry a second set of normals for the shell pass (108 of 108, mostly `EQUIPMNT.LMP`); `model_draw` then calls `model_emitShellPasses` (0x174e78) | O |
| 0x40 | facing-point table present (`model_evalFacingPoints` 0x175b80). Never set on the disc | O (code only) |

Mesh record (10 bytes):

| Offset | Type | Meaning | Status |
|---|---|---|---|
| +0 | s8[3] | bounding box minimum x, y, z in world units | O 0x179400 |
| +3 | s8[3] | bounding box maximum. Both ends saturate at ±127 (tall trees) | O, saturation D |
| +6 | u8 | joint the mesh belongs to; used when a mesh is torn off as a physics prop (`model_getMeshJoint` 0x179358) | O |
| +7 | u8 | 0 in all 9,600 meshes | D |
| +8 | u16 | triangle count. Equal to the count rebuilt from the strips in 9,270 meshes and 1 to 112 above it in the other 330 | I |

A 64-bit **show mask** selects the meshes of a draw call: bit *i* set = mesh *i* is drawn
(`model_draw` walks the bits and emits one DMA reference per run of adjacent shown meshes).
The file contributes three things to it: the default at +0x08, the variant table, and the
part masks (+0x00) of whatever is worn.

## `.vif`: tables

**Variant table** (flag 0x02) — 32 records of `{u64 show, u64 hide}`, one per variant bit
(D: all 134 files leave room for 32 before the next table). O 0x179550:

```
mask = ~header.hiddenByDefault
for each set bit i of the object's 32 variant bits:
    mask = (mask | rec[i].show) & ~rec[i].hide
```

The variant bits of a creature are its `change0` … `change31` properties
(`docs/creatures.md`, +0xe8).

**Attach table** (flag 0x04) — 16 records of 0x34 bytes (D: room for exactly 16 in all 350
files; the code indexes without a bound). O 0x1754a0, 0x175fb8:

| Offset | Type | Meaning |
|---|---|---|
| +0x00 | s32 | joint index |
| +0x04 | float[9] | rotation, three rows; orthonormal in the samples. `model_getAttachPoint` returns the second row (+0x10) as the direction |
| +0x28 | float[3] | origin, in model rest space |

World position of an attach point = joint matrix × origin, then the model's scale, facing
and position. A part model whose +0x13 is *k* is drawn with joint matrix × record *k* of its
**parent** as its only matrix (vertex program entry 0x1a, 0x3e7488).

**Hull points** — for each mesh, eight points of three signed bytes (world units): 24 bytes
per mesh. `PhProp_run` uses them as the contact points of a rigid body
(`model_getHullPoints` 0x179320). O.

**Effect segment** — two float vec3. `model_getEffectSegment` (0x1791a0) returns them, or
(0, 4.5, 0) and (0, 38, 0) when the header byte is 0; its caller is the weapon and status
effect code (`fx_modelStatusEffects`). In the one sword looked at the segment runs from the
hilt to the tip. O for the layout, I for the purpose.

**Sample points** — points on the model's surface: effects spawn at them
(`model_getSamplePoint` 0x178e18, 68 callers) and `model_drawShadow` (0x1762e8) sends the
whole block to the vector unit.

| Offset | Type | Meaning | Status |
|---|---|---|---|
| +0x00 | u32 | length in qwords of the VIF packet that starts at +0x10 (used as a DMA reference size, 0x1762e8) | O |
| +0x04 | u32 | number of points (`model_getSamplePointCount` 0x1799c8) | O |
| +0x10 | VIF | `FLUSHA`, then groups of at most 45 points: `UNPACK V4-16` to absolute address 0x200 or 0x300 (alternating), first element (points in this group, 0, 0, 0), then the points; `MSCAL 0x30`. Ends with `FLUSHA` and NOPs | D |

The CPU side skips the VIF codes by arithmetic: point *i* is at
`block + 0x20 + i*8 + (i / 45) * 0x10` (integer division). A point is four s16:
x, y, z (÷ 16, model rest space) and a word whose low byte is joint × 4 and whose high byte
is a size (the reader returns the whole word times the model scale; the vertex program
masks the low byte off as a matrix address, 0x3e67d8+). O for position and joint, I for
"size".

**Facing points** (flag 0x40) — 16-byte records ended by a first byte of −1: s16 position
at +2 (÷ 16), s8 normal at +8 (÷ 128), s8 joint at +15. Read by `model_evalFacingPoints`
(0x175b80); no file has the table, so nothing more is known. O (code only).

## `.vif`: mesh data

### It is a VIF1 stream

A mesh is not a vertex buffer. It is a ready-made PlayStation 2 **VIF1 packet**: the engine
points the DMA controller at the bytes in the lump (`ref` tag with the mesh's address and
qword count, `model_draw` 0x1779b0 and `model_emitMeshRefs` 0x179260), and the VIF unpacks
them into vector unit 1 memory and starts a microprogram. So the "format" is the VIF codes
plus what the microprogram expects to find. Both were read: the VIF codes in all 9,600
meshes, the microprogram in the executable's `.vutext` section.

VU1 data memory as the model code uses it (O unless marked):

| Address (qwords) | Contents |
|---|---|
| 0x000–0x0ff | up to 64 joint matrices of 4 qwords. Filled by entry 0x0c from the pose, one per joint of the clip (animated); by entry 0x1e with the model transform in the first 63 slots (not animated, 0x3e71b8); or slot 0 only by entry 0x1a (part on an attach point) |
| 0x100 and 0x27b | the two halves of the double buffer: `BASE 0x100`, `OFFSET 0x17b` (VIF codes at 0x3e9968 and 0x3e996c, sent once after the microprogram) |
| half + 0x00 … 0x7f | input: the vertex data of one packet |
| half + 0x80 | GIF tag of the outgoing strip |
| half + 0x81 … | outgoing strip, 3 or 4 qwords per strip vertex |
| 0x3f6–0x3ff | constants and mode words kept by the microprogram |

The microprogram starts with a jump table, one entry every two instructions; `MSCAL n`
enters at instruction *n*. Entries the model code uses:

| Entry | Called from | What it does | Status |
|---|---|---|---|
| 0x02 | CPU, per draw (0x175670) | takes the 4×4 transform that was just unpacked | O call, body not read |
| 0x0c / 0x1e | CPU, per draw | build the joint matrices: transform × pose matrix for every joint, or the transform copied into 63 slots | O |
| 0x1a | CPU, per part | joint matrix × attach matrix into slot 0 | O |
| 0x2a | CPU, shell pass | switches the mesh programs to the shell path and stores a colour and a distance | O |
| 0x30 | sample-point block | one quad per sample point (shadow). It does not draw to the screen: it draws into an off-screen surface, through its own joint matrices at 0x100 loaded by entries 0x2c / 0x2e (`docs/spec/render-pipeline.md` section 4.9) | O for the data it reads |
| 0x3a | CPU (`anim_emitPose` 0x16f880) | converts the uploaded pose (three s16 quadruples per joint: rotation ÷ 4096, translation ÷ 64) into matrices | O |
| **0x42** | mesh data | one-pass packet, 3 qwords per strip vertex (0x3e7550) | O |
| **0x44** | mesh data | two-pass packet, 4 qwords per strip vertex (0x3e7ac8) | O |
| **0x46** | mesh data | the level-geometry program (see `docs/formats/world.md`): no weights, positions unpacked with `STMOD 1`. Only `dome.vif` of `D_SWAMP.LMP` uses it (59 packets) | D, body not read |

Because the two buffer halves alternate, a packet's vertex data goes into one half and its
strip is built in the *other* half (the program picks 0x181 or 0x2fc as the output base
depending on which half it was given, 0x3e7af8). That is why the texture coordinates come
**after** the `MSCAL` in the stream: by then the VIF has switched halves, and they are
unpacked straight into the outgoing strip.

### Packet layout

A mesh is a sequence of packets (67,304 on the disc) separated by NOP padding. With *N* the
vertex count, every packet is exactly this (D for all of them; the unpack addresses have the
"relative to the buffer half" bit 0x8000 set; "unsigned" is bit 0x4000):

| # | VIF code | Elements | Address | Contents |
|---|---|---|---|---|
| 1 | `ITOP N` | | | vertex count, 1 to 41 |
| 2 | `UNPACK V3-16` signed | N | 0 | positions x, y, z |
| 3 | `UNPACK V3-8` signed | N | N | normals; length 127 |
| 4 | `UNPACK V3-16` unsigned | N + 2 | 2N | slot rows (below) |
| 5 | `UNPACK V4-8` unsigned | ≥ 1 | 3N + 2 | weight entries (below). Absent with program 0x46 |
| 6 | `UNPACK V4-16` unsigned | 1 + c | follows 5 | (c, 0, 0, 0), then c copy rows |
| 7 | `UNPACK V4-32` | 1 or 2 | follows 6 | GIF tags: 1 for programs 0x42 and 0x46, 2 for 0x44 |
| 8 | `UNPACK V3-8` signed | N | follows 7 | shell normals; only in models with flag 0x20 |
| 9 | `MSCAL 0x42`, `0x44` or `0x46` | | | run the vertex program |
| 10 | `STCYCL cl = nreg, wl = 1` | | | |
| 11 | `UNPACK V2-16` unsigned | nloop | 0x81 | texture coordinates, one per strip vertex, each written to the first qword of its strip vertex |
| 12 | `STCYCL cl = 1, wl = 1` | | | |

Program 0x46 packets have `STMOD 1` before step 2 and `STMOD 0` after it (the caller's row
registers are added to the positions).

Limits that follow from the buffer size and hold in every file: input ≤ 128 qwords, strip
≤ 83 vertices with 3 registers or 62 with 4.

**GIF tag** (O for the fields the program uses, D for the values). `nloop` is the number of
strip vertices, EOP and PRE are set, the primitive is a triangle strip with Gouraud shading,
texturing and texel coordinates (`FST`), with or without alpha blending (PRIM 0x15c in
63,164 packets, 0x11c in 4,140). `nreg` and the register list:

| Program | nreg | Registers per strip vertex | Tags |
|---|---|---|---|
| 0x42, 0x46 | 3 | UV, RGBAQ, XYZF2 | one |
| 0x44 | 4 | UV, (unused), RGBAQ, XYZF2 | first tag |
| 0x44 | 4 | (unused), UV, RGBAQ, XYZF2, second GS context | second tag |

Vertex colours are **not** in the file. The program computes RGBAQ from the normal and the
lights (clamped to 255) and writes it with the transformed position.

### Building the strip

The vertex program reads vertices in order and writes each to the place in the outgoing
strip named by the slot rows. This is what turns N vertices into `nloop` strip vertices.
O for programs 0x42 and 0x44 (loops at 0x3e7550+ and 0x3e7bb0–0x3e7c70; copy loops at
0x3e7cb0); D: replaying the rules below fills **every** strip position of every packet on
the disc with a vertex.

An *address* is a qword offset from the first strip vertex. With 3 registers a strip
position *p* has address 3p; with 4 registers it has address 4p + 1 (the first qword of a
strip vertex belongs to the texture coordinate and is never written by the program). Bit 15
of an address written to is carried into the XYZF2 qword, where it is the GS "do not draw"
bit: the triangle that would end on that strip vertex is skipped.

- Row *j* of block 4 is `(a, src, dst)`. The loop is two vertices behind its input, so `a`
  of row *j* is where vertex *j − 2* goes. Rows 0 and 1 are placeholders, (3, 0, 3) or
  (5, 0, 5); whatever they write is overwritten later.
- `src`, `dst` of the same row are an unrelated copy: the strip vertex at `src` (as it is
  before this row's own vertex is stored) is copied to `dst`, taking the no-draw bit from
  `dst`. `src == dst` means no copy. This is how a vertex appears twice.
- Copy rows of block 6 are `(src1, dst1, src2, dst2)`: two more copies each, done after the
  loop, for vertices used more than twice.
- In a model with flag 0x20 the middle value of row 0 is not a copy source: it is the
  address of the shell normals (block 8) within the input half (O 0x3e8160; D in all 764
  such packets).

```
slots = [empty] * nloop
for j, (a, src, dst) in enumerate(rows):          # N + 2 rows
    copy = slots[pos(src)]                        # read first
    if j >= 2: slots[pos(a)] = (vertex j - 2, nodraw = a >> 15)
    if copy is a vertex: slots[pos(dst)] = (copy.vertex, nodraw = dst >> 15)
for (s1, d1, s2, d2) in copyRows:
    slots[pos(d1)] = (slots[pos(s1)].vertex, d1 >> 15)
    slots[pos(d2)] = (slots[pos(s2)].vertex, d2 >> 15)
triangles = [(slots[p-2], slots[p-1], slots[p]) for p in 2 .. nloop-1 if not slots[p].nodraw]
uv of a corner = uvList[its strip position]
```

`tools/model_info.py` does the same thing one qword at a time, which also covers the
placeholder rows. Triangles that repeat a vertex are stitching and should be dropped.

**Winding carries no information.** Compared with the stored normals, half the triangles
face each way, both by strip parity and by parity since the last restart (D: 2.5 million
triangles; `docs/formats/world.md` found the same for level geometry). The GS does not
cull, and no back-face test was seen in the vertex loops that were read. Draw two-sided, or
turn each triangle to agree with its normals as the tool's OBJ export does.

### Texture coordinates

Unsigned 16-bit pairs in GS `UV` format: texels × 16, measured from the top-left texel of
the texture. In all 2,315 models with a non-empty texture the largest coordinate is within
the width and height stored in the `.tex` header (D). Divide by 16 and by the texture size
to get the usual 0–1 range. They belong to strip positions, not to vertices, so one vertex
can carry different coordinates in different triangles.

### Weights and joints

Block 5 is a list of 4-byte entries `(j1, w1, j2, w2)` that the program consumes as it
walks the vertices (O 0x3e7e38 onward):

| Entry | Meaning |
|---|---|
| `j2 == 0xff` | a run: the next `w2` vertices follow joint `j1` only. `w1` is not used |
| otherwise | **one** vertex blended from `j1` with weight `w1/255` and `j2` with `w2/255` |
| … and `w1 + w2 != 255` | the following entry `(j3, w3, j4, w4)` belongs to the same vertex: a third joint, and a fourth unless `j4 == 0xff` |

- A joint byte is the address of the joint's matrix in VU1 memory: **joint index × 4** (O:
  the CPU writes `joint << 2` for attach points, 0x175fb8; D: every joint byte in every file
  is a multiple of 4).
- Weights of a vertex always add up to 255 (D). On the disc 80% of vertices have one joint,
  17% two, 3% three, 0.3% four.
- The list may end with one unused entry `(0, 255, 255, 255)` (2,711 packets). The program
  fetches one entry ahead and finds block 6 by where that pointer ends up, so the exporter
  pads when the last run ends exactly at the last vertex (I).
- Joint indices run from 0 to 63; 47 models have vertices on joint 63 (D).
- A model drawn without an animation still goes through this code: the first 63 matrix
  slots hold the same transform (slot 63 is not filled on that path, O 0x3e71b8).

**The skeleton is not in the `.vif`.** There is no joint count, no hierarchy and no rest
pose in it; the only joint data are the indices above and those in the attach, sample and
mesh records. The matrices come from the animation state (`anim_emitPose` 0x16f880 uploads
the pose, entry 0x3a converts it) and each one maps rest-pose model space straight to posed
model space, so vertices, attach origins and sample points are all multiplied by them as
stored. The skeleton itself — parent links and rest positions — is repeated in every `.anm`
clip and is described in `docs/formats/anim-audio.md` (sections 2.2, 2.5 and 2.8). Joints
are matched by index only: in 1,016 of the 1,018 flag-0x01 models that share a lump with
clips, the highest joint index used is below a clip's joint count (D).

### Passes, blending, shell

There are no material records. What a native renderer has to reproduce is spread over:

- **Header +0x18**, the GS blend equation for the model's own texture. Value 1 means
  `out = src + (dst − src) × As`, value 9 means `out = src + dst × As`, where `As` is the
  texture's alpha with 0x80 = 1.0. Note the direction: with value 1 **alpha 0 is opaque**
  and 0x80 is fully transparent (D: in the model textures looked at, solid areas have alpha
  0 and unused or cut-out areas about 0x7e). `model_emitDrawSetup` also sets `TEST_1` =
  0x507f5: pixels pass when alpha < 0x7f, depth test "greater or equal".
- **Flag 0x10 and program 0x44.** Each strip is sent twice: first with the second tag (GS
  context 2, the second UV qword, which the program computes from the transformed normal),
  then with the first tag (context 1, the stored UVs) — order O at 0x3e7da8. Context 2
  blends with `FIX` from +0x20. Which texture context 2 holds was not traced here; it is
  the level's `envtex.etex`, as guessed (0x19c77c, 0x19e440; `docs/spec/render-pipeline.md`
  section 13). With +0x18 = 9 the model
  texture's alpha then acts as "how much of the first pass shows through".
- **Per-packet PRIM**: whether blending is on at all.
- **The texture's own flags** (TEX0 fragment: `TFX` 3 = HIGHLIGHT2 in model textures).
- **Flag 0x20, the shell pass.** For each record of a caller-supplied list (colour, float;
  `model_setShellList` 0x1797d8) the meshes are sent again with the programs in a second
  mode: position + shell normal × distance, flat colour (0x3e80e8–0x3e8238). I: this is
  the glow drawn around enchanted weapons.
- `model_setFade` (0x1797b8) replaces the blend equation by a FIX fade for one draw.

## `.tex`: header

A lump entry is a 0x80-byte header followed by one GS upload packet. (In a level texture
cell the same header is 0x40 bytes and the packet offset is relative to the cell; see
`docs/formats/world.md`.)

| Offset | Type | Meaning | Status |
|---|---|---|---|
| 0x00 | u16 | width in texels of the part that is used | O `ui_drawSpriteImpl` 0x17b590 reads it as the sprite size; D for models (UV range) |
| 0x02 | u16 | height, likewise. 8 files are 0 × 0: a palette and no image | O / D |
| 0x04 | u16 | number of 256-byte GS blocks the texture needs, palette included (`texcache_alloc` 0x179bb0; a texture needing more than the cache holds is drawn untextured, 0x16b83c) | O |
| 0x06 | u16 | length of the upload packet in qwords (DMA reference size, `gfx_dmaHandler` 0x16b998) | O |
| 0x08 | u16 | flags, below | |
| 0x0a | u16 | 0 in the file; `tex_relocate` stores 0xa7fb | O |
| 0x0c | u32 | bits 14–45 of the GS `TEX0` register: buffer width ÷ 64 (6 bits), pixel format (6), log2 width (4), log2 height (4), TCC (1), TFX (2). The handler builds `TEX0 = (block + 4) \| fragment << 14 \| block << 37 \| 2 << 61` | O |
| 0x10 | u32 | offset of the upload packet from the start of the header; 0x80 in every lump entry. A pointer after `tex_relocate` | O |
| 0x14 | u32 | 0 in the file. Run time: streaming state of level textures | O |
| 0x18 | s16 | 0 in the file. Run time: first GS block given to the texture, 0 = not in GS memory | O |
| 0x1a | s16 | run time: slot in the 16-entry ring of resident textures | O |
| 0x1c | u32 | 0 in the file; −1 after `tex_relocate` (which is also its "already done" test); then the number of the last frame that used the texture (`gfx_addSortedPacket` 0x16b7f0) | O |
| 0x20 | ptr[8] | run time: per sort layer, the last draw entry of this frame that uses the texture | O |
| 0x40–0x7f | | zero | D |

Flags (+0x08). Only four are tested by code that was found; the storage kind is otherwise
D (it matches the pixel format in +0x0c in all 3,236 files).

| Bit | Meaning | Files | Status |
|---|---|---|---|
| 0x0001, 0x0100 | level-texture forms handled by `tex_relocate` / `tex_relocateInCell`; never set in a lump | 0 | O (code only) |
| 0x0004 | 8-bit, 256-colour palette. The handler patches the image destination at packet +0x474 | 2,537 | O |
| 0x2000 | 4-bit, 16-colour palette. Destination patched at packet +0xb4 | 537 | O |
| 0x0020 | 32-bit, no palette | 160 | D |
| 0x0080 | no pixels: the packet is one empty GIF tag. `blank.tex`, `bigblank.tex` of `ENGINE.LMP` (16-bit surfaces the engine draws into) | 2 | D |
| 0x0010 | model texture: set on the texture of every model (2,323 of 2,323) and on 11 alternative skins of models, nothing else. TFX = 3 in all but one | 2,334 | D |
| 0x0040 | set on interface, picture and effect textures and on no model texture but one; TFX = 0 in all but that one. Every texture found to be stored as two fields (below) has it | 612 | D; meaning U |
| 0x0200, 0x0400, 0x0800, 0x1000 | — | 1, 290, 70, 160 | U |

## `.tex`: pixel data

The packet is what the GS needs to receive the texture; decoding means replaying it. It is
made of GIF tags of two kinds only (D, 3,236 files): register lists (`BITBLTBUF`, `TRXPOS`,
`TRXREG`, `TRXDIR`, and `LABEL` as padding) and IMAGE data. Base pointers in `BITBLTBUF`
are 0 in the file and patched at run time, so destinations are told apart by order: the
first `BITBLTBUF` is the palette (if the texture has one), the second the image.

| Kind | Palette | Image |
|---|---|---|
| 8-bit | 16 × 16 rectangle, 32-bit RGBA, 1,024 bytes | one or more rectangles sent **as 32-bit pixels** into a buffer half as wide (in pixels) as the texture's |
| 4-bit | 8 × 2 rectangle, 32-bit RGBA, 64 bytes, in index order | one rectangle sent as 4-bit texels: plain rows, low nibble first (533 files). Four 640 × 448 menu backgrounds are sent as 32-bit pixels instead, like the 8-bit kind |
| 32-bit | none | one rectangle of RGBA, plain rows |

**Why "sent as 32-bit" matters (the swizzle).** The GS stores each pixel format in its own
interleaved order. Uploading bytes as 32-bit pixels and then sampling the same memory as
8-bit texels is a fast-upload trick, and it means the file holds the 8-bit image *in GS
memory order*, not in rows. To decode: place every uploaded rectangle in GS memory as
32-bit pixels, then read the texture back as 8-bit (or 4-bit). The layout rules, from the
GS documentation:

- A page is 8,192 bytes: 64 × 32 pixels at 32 bits, 128 × 64 texels at 8 bits, 128 × 128
  at 4 bits. Pages run left to right, top to bottom, `buffer width ÷ page width` to a row.
- A page is 32 blocks of 256 bytes: 8 × 8 pixels at 32 bits, 16 × 16 texels at 8 bits,
  32 × 16 at 4 bits. For 32-bit and 8-bit the block order is 8 columns × 4 rows:
  `0 1 4 5 16 17 20 21 / 2 3 6 7 18 19 22 23 / 8 9 12 13 24 25 28 29 / 10 11 14 15 26 27 30 31`;
  for 4-bit it is 4 columns × 8 rows: `0 2 8 10 / 1 3 9 11 / 4 6 12 14 / 5 7 13 15 /
  16 18 24 26 / 17 19 25 27 / 20 22 28 30 / 21 23 29 31`.
- Inside a block, 32-bit pixel (x, y) is word `(y >> 1) * 16 + (y & 1) * 2 + W[x]` with
  `W = 0 1 4 5 8 9 12 13`.
- Inside a block, 8-bit texel (x, y): let `r = y & 3`; the word is
  `(y >> 2) * 16 + (r & 1) * 2 + W[(x & 7) ^ s]` where `s` is 4 when `((y + 2) >> 2)` is
  odd and 0 otherwise; the byte within the word is `(r >> 1) + 2 * ((x >> 3) & 1)`.
- 4-bit texel (x, y): the same word; the nibble within it is `(r >> 1) + 2 * ((x >> 3) & 3)`.

D: an image decoded this way is coherent for every kind (wood grain, faces, the 640 × 448
backgrounds), and the 8-bit rule was checked against an independently derived closed
formula for every texel of three buffer widths. The rectangles need not cover the texture:
the exporter left out regions no triangle uses (a barrel texture is an L shape of two
rectangles). Uncovered texels read as index 0.

**Palette order.** A 256-entry palette is stored in the GS's own order: entry *i* is at
position *i* with bits 3 and 4 exchanged (entries 8–15 and 16–23 of every 32 swap places).
A 16-entry palette is in plain order. Colours are R, G, B, A bytes. D.

**Alpha** is 0–0x80 as usual on this hardware, but what it means depends on who draws the
texture: for model textures 0 is opaque (see "Passes, blending, shell"); sprites and effects
are drawn by other code with their own blend settings (not read).

**Mip maps:** none. No packet uploads more than one image (D, all files), the header has no
field for further levels, and the model setup code writes `TEXFLUSH`, `TEX0`, `ALPHA` and
`TEST` only — no `MIPTBP`, no `TEX1` (O 0x175670).

**Sizes.** Width and height at +0x00 are the used part; the GS texture is the next powers
of two (in +0x0c). A lump entry shorter than 1,616 bytes is padded with zeros to exactly
1,616 (344 files); the packet length at +0x06 is the true size.

**Interface pictures are two fields.** Textures drawn by the 2D sprite code are stored as
the two fields of an interlaced picture, one above the other: rows 0 … h/2 − 1 are the
picture's lines 0, 2, 4, … and rows h/2 … h − 1 its lines 1, 3, 5, …, where h is the height
at +0x02. O: the quad builder used by every sprite drawer (`ui_emitSpriteQuad` 0x17ab50)
draws the top half of the texture on one field and the bottom half on the other — in one
display mode by asking for the current field (0x19d9e4) and adding half the height to the V
coordinate, in the other by drawing both halves over the same rectangle with the GS
scanline mask. D: decoded as stored, a
full-screen controls picture shows the pad twice at half height; interleaving the halves
gives one correct 640 × 448 picture. A loader has to interleave them (`--weave` in the
tool). Nothing in the header was identified that marks such a texture: it follows from how
the texture is drawn. A similarity test (is row k closer to row k + h/2 than to row k + 1?)
over the disc finds field storage only among textures with flag 0x0040: 469 of the 612
clearly are, 48 clearly are not, the rest are too small or too flat to tell. The lumps of
the inventory, icons, HUD, shop, menus and loading screens are stored as fields; head
portraits, map icons, effect sprites (halos, trails) and the two star-field backgrounds
are not. Of 92 textures sampled without the flag, none is. D.

**`.etex`.** Same header and packet; all 127 are 128 × 128, 32-bit, flags 0x0420. Who loads
them was not traced here; the main loop does, through 0x19e440
(`docs/spec/render-pipeline.md` section 13).

## What was checked

`tools/model_info.py` is strict: every VIF code, unpack address, element count, GIF tag and
table offset has to be what this document says, otherwise it stops with a message.

| | Result |
|---|---|
| `.vif` on the disc | 2,323 of 2,323 parse: 9,600 meshes, 67,304 packets, 2,294,215 vertices, 2,557,871 triangles; no strip position left unfilled; all weight lists cover their vertices exactly |
| `.tex` and `.etex` on the disc | 3,236 of 3,236 headers and packets parse; 3,226 decode to pixels; the other 10 have none (8 are 0 × 0, 2 are blank surfaces) |
| looked at by eye | 11 models exported to OBJ and rendered with their textures (two player bodies, a hair part, skeleton, cyclops, barrel, chest, sword, an item axe, a tree, a sky dome); 6 more textures of the other kinds (32-bit, 4-bit sent as 32-bit, a full-screen 8-bit picture before and after interleaving, an item picture, two effect sprites) |
| rejects | an `.anm`, an `objects.ob`, a `.world`, a level `.TEX`, truncated copies of a model and a texture: each fails with a specific message and exit status 2 |

Usage:

```
python3 -I -B tools/model_info.py barrel.vif -v
python3 -I -B tools/model_info.py barrel.vif --obj out.obj --tex barrel.tex
python3 -I -B tools/model_info.py barrel.tex --ppm out.ppm --pgm alpha.pgm
python3 -I -B tools/model_info.py picture.tex --ppm out.ppm --weave
```

Keep extracted files and exports outside the repository.

## What a native loader needs, in order

1. **Lump access and names.** Already available (`tools/gob.py`). Pair `x.vif` with `x.tex`
   from the same lump; take the names from the same tables the game uses.
2. **Textures.** Header, then replay the upload packet: palette, then the image through the
   GS memory order for the 8-bit kind (four fifths of all textures), the direct 4-bit kind,
   then 32-bit. Output RGBA of width × height. Remember that model textures use alpha 0 as
   opaque and that interface pictures are two stacked fields. No mip maps to load; generate
   them if wanted.
3. **Static meshes.** Header and mesh table; walk the VIF codes of each mesh; replay the
   slot rows into strips and the strips into triangles; positions ÷ 16, normals ÷ 127,
   UV ÷ 16 ÷ texture size. Draw two-sided. This alone shows every prop, item and rest-pose
   character correctly.
4. **Mesh selection.** The show mask: default mask at +0x08, the 32 variant records, and the
   +0x00 masks of worn parts. Without it creatures show all their alternative heads and
   armour at once.
5. **Attach slots and parts.** The 16 attach records, and +0x13 of the part, to put weapons
   and shields in hands. Needs joint matrices; with none, use the rest pose (identity).
6. **Skinning.** Decode the weight list to at most four (joint, weight) pairs per vertex
   and blend the joint matrices of the current pose, which map rest-pose model space to
   posed model space. The pose comes from the `.anm` decoder (`docs/formats/anim-audio.md`);
   allow 64 joints.
7. **Blending.** Per model the equation from +0x18, per packet the blend bit of the GIF
   tag, alpha test at 0x7f.
8. **Lighting.** The file has normals and no colours; the original lights per vertex in the
   vector unit. Any per-vertex or per-pixel diffuse light will do to start with; matching
   the original needs the light upload code (0x149268) and the rest of the vertex programs.
9. **Extras, last.** The second pass of flag-0x10 models (reflection layer), the shell pass
   of flag-0x20 models, shadows from the sample points, hull points for physics props, the
   effect segment for weapon effects.

## Corrections to earlier documents

- `docs/engine.md` and `symbols/engine.tsv` call 0x179550 `model_buildHideMask` and its
  result a hide mask. The result is a **show** mask (a set bit draws the mesh); what the
  file stores at +0x08 is the hidden set, and the function returns its complement adjusted
  by the variant records. `docs/monsters.md` (+0xe8 "bit mask of hidden model parts") has
  the same slip: +0xe8 holds variant bits, +0x220 the show mask.
- `docs/monsters.md` describes the per-class block at object +0x24 as "model at +0xc, second
  model at +0x14". The second resource is the model's **texture**: the class tables list
  `x.vif` followed by `x.tex`, and `Creature_draw` passes it as the texture argument of
  `model_draw`.
- `docs/formats/world.md` leaves two points open that the vertex programs settle for the
  model packets, which use the same strip table: rows 0 and 1 are placeholders because the
  loop stores each vertex two rows after reading it, and the middle value of row 0 doubles
  as the address of the shell normals when the model has them.
- `docs/FORMATS.md` lists models and textures as unknown.

## Open questions

- **`creature_drawHeldPart` (0x117f08)** passes the same pointer as the model and as the
  texture of `model_draw` (0x118018–0x118028). Read literally, `gfx_addSortedPacket` would
  then treat the model header as a texture header and overwrite its +0x1c–0x3f. Either
  that path does not run for real models or something was missed; it needs a look on a
  running game before anyone relies on the texture argument rule above for held parts.
- Flag 0x01 of the model header; texture flags 0x40, 0x200, 0x400, 0x800, 0x1000.
- Which texture the second pass of flag-0x10 models uses, and how the program computes its
  coordinates and the vertex colour (entries 0x02 and the lighting part of 0x42/0x44 were
  not read in detail).
- Texture wrap and filter modes: the model code that was read writes neither `CLAMP` nor
  `TEX1`, so both are inherited from state set elsewhere. (`docs/spec/render-pipeline.md`
  section 6 lists the GS state per kind of draw.)
- Program 0x46 in a model (one file), and where its row registers are set for it. (Still
  open, with one more fact: 0x175950, the function that would set that program up for a
  model — entries 0x16 and 0x34 — has no caller. How the one sky dome that uses it is
  drawn is Unknown; `docs/spec/render-pipeline.md` section 13.)
- The mesh record's +8 count where it differs from the rebuilt triangle count.
- `.etex` loading; the 2D sprite and font code (0x17a5a0–0x17c730) that draws the interface
  textures was not read.

## Functions

Names are in `names.tsv`, `symbols/engine.tsv` and `symbols/fmt-model.tsv`.

| Address | Name | Role |
|---|---|---|
| 0x17153c | `lump_fixupEntry` | dispatch by extension |
| 0x179130 | `model_relocate` | mesh offsets → pointers |
| 0x1779b0 | `model_draw` | setup, joint matrices, one DMA reference per run of shown meshes |
| 0x175670 | `model_emitDrawSetup` | GS registers, transform, entry 0x02 |
| 0x178c28, 0x175fb8 | `model_drawPart`, `model_emitPartSetup` | a part on a parent's skeleton or attach slot |
| 0x174e78 | `model_emitShellPasses` | flag 0x20 |
| 0x1762e8 | `model_drawShadow` | sample-point packet |
| 0x179260 | `model_emitMeshRefs` | show mask → DMA references |
| 0x179550 | `model_buildHideMask` | default mask and variants → show mask |
| 0x1754a0, 0x175330, 0x1795f8, 0x1796e0 | attach point readers | |
| 0x178e18, 0x1799c8, 0x1799e8 | sample point readers | |
| 0x179400, 0x179358, 0x179320, 0x1791a0 | bounds, mesh joint, hull points, effect segment | |
| 0x16f880 | `anim_emitPose` | pose upload, entry 0x3a |
| 0x179e10 | `tex_relocate` | packet offset → pointer |
| 0x16b7f0 | `gfx_addSortedPacket` | queues a draw entry under its texture |
| 0x16b998 | `gfx_dmaHandler` | uploads textures, patches `BITBLTBUF` and `TEX0` |
| 0x17ab50 | `ui_emitSpriteQuad` | 2D sprite quad; picks or interleaves the two stored fields |
| 0x179bb0, 0x179b08, 0x17a3a0 | `texcache_alloc`, `texcache_reset`, `texcache_setRange` | GS block cache |
| 0x3e5ed0 | (data) VU1 microprogram, 1,868 instructions in eight uploads of 0x808 bytes | instruction *i* is at `0x3e5ed0 + (i / 256) * 0x808 + (i % 256) * 8` |

No patches are proposed and no ledger rows: nothing in these formats touches shared game
state.
