# Drawing a level texture

What the CPU and VU1 do with a WORLD geometry chunk and with an automap cell once the
pixels exist: blend, depth, draw order, environment mapping, and which atlas tile a cell
code selects. The pixels themselves are `docs/formats/level-texture.md`. The environment
UV formula was already checked in `docs/spec/render-pipeline.md` section 4.6; this note
re-executes the rows that formula consumes, and executes the automap mapping, which was
open.

`tools/ref_leveldraw.py` is the executable form. `tools/test_ref_leveldraw.py` checks it
on authored numbers. `tools/difftest_leveldraw.py` runs the same numbers through
`world_drawChunk` (0x1887b8), `gfx_addSortedPacket` (0x16b7f0) and the automap drawer
(0x168cac plus the VU1 microcode that drawer uploads).

Status letters: **O** read at the address, **D** holds in the files, **I** inferred,
**U** unknown. **Executed** means the original function was run in `tools/ee_emu.py` or
`tools/vu1_emu.py` on state this note built. Nothing here was run on a console, PCSX2
or Play!.

## 1. Geometry chunk header

`world_draw` (0x189870) walks the chunk tree and calls `world_drawChunk(world, chunk)`.
The chunk is the second argument. For a geometry chunk the header it writes, before the
DMA `ref` of the stored packet, is Executed:

| Chunk flags | `ALPHA_1` | `ALPHA_2` | `TEST_1` | Sort layer |
|---|---|---|---|---|
| none of the bits below | 2 | not written | 0x587f4 | 0 |
| 0x10 environment | 9 | 0x2a | 0x587f4, or 0x582f5 if 0x400 is also set | 0, or 4 if 0x200 is also set |
| 0x200 | 1 | | 0x587f4 | 4 |
| 0x400 | 1 | | 0x582f5 | 0 |
| 0x200 and 0x400 | 1 | | 0x582f5 | 4 |
| 0x10000 | 0x48 | | 0x587f4 | 0 |

`ref_leveldraw.chunk_gs`. Flags 0x80, 0x800, 0x4000 and 0x8000 leave this function for
water (`docs/formats/water-draw.md`), a scenery model, an emitter or a light
(O 0x1887b8). The table is the geometry path only.

No `ZBUF` register is written. Two marker words placed at `g_zbufWrite` (0x44fd58) and
`g_zbufNoWrite` (0x44fd60) did not appear in the packet (Executed). Depth test and depth
write are whatever `ZBUF` and `TEST` already are. The frame setup's `ZBUF_1` is
0x0200008c, which writes depth, and the test above is "greater or equal"
(`docs/spec/render-pipeline.md` sections 3 and 6). A flag-0x200 chunk is in layer 4, so
it is drawn after layers 0–3, and it still tests depth. It writes depth only while the
GS `ZBUF` mask is still clear; this drawer does not set or clear that mask.

The equations, with As the source alpha and 0x80 meaning 1 (O, the table in
render-pipeline section 6):

| Value | Result |
|---|---|
| 2 | `src × (1 − As)`. The destination is not added. Palette alpha 0 is solid; alpha 0x80 draws nothing. |
| 1 | `src × (1 − As) + dst × As`. Alpha 0 is opaque. |
| 9 | `src + dst × As`. The environment-mapped second pass. |
| 0x2a | `src`. The environment-mapped first pass (GS context 2). |
| 0x48 | `dst + src × As`. |

`TEST` 0x582f5 keeps a fragment only when its alpha is below 0x2f, and still tests
depth. The stored packet may write `ALPHA` and `TEST` again; the last write in the DMA
stream wins (D, `docs/formats/world.md`, the geometry packet). The header values above
are what is true at the start of that packet.

`STROW` is the chunk translation `(tx, ty, tz, 0)` (Executed, translations 16, 32, 48).
That is the same contract as `docs/formats/model-row-registers.md`.

Light, before the packet (Executed; the same precedence `docs/level-flow.md` section 16
recorded on the other research branch):

| Flags | Call | Then |
|---|---|---|
| 0x100 | constant −230 | bit 0x100 is cleared in the chunk; every other bit stays |
| 0x2000, and 0x100 clear | constant +230 | |
| 0x200, and both of those clear | constant 0 | |
| none of those | the dynamic-light call 0x149b90 | |

0x100 wins over 0x2000 (Executed, flags 0x2100). 0x2000 wins over 0x200 (flags 0x2200
give +230, layer 4 and `ALPHA_1` 1 together). `ref_leveldraw.chunk_light`. What 0x149b90
puts in the four light slots is the account in render-pipeline section 4.6, not re-run
here.

## 2. Order inside a layer

There is no depth sort. `gfx_addSortedPacket(packet, layer, texture, parent, flags)`
(0x16b7f0) keeps eight lists. Executed, and the same rules as render-pipeline section 8:

- Lists are sent layer 0, then 1, … then 7. A WORLD chunk is layer 4 exactly when flag
  0x200 is set, otherwise layer 0.
- A packet with no texture, and a packet whose flag bit 0 is set, is inserted at the
  front of its layer.
- Any other packet is inserted immediately after the previous packet of the same texture
  in that layer. One texture stays together, in submission order. Texture groups
  therefore run in reverse order of first use.
- A non-zero parent is the entry a previous call returned (`v0`). The new entry is
  linked behind it and is not also hung on the layer head (Executed, one link).

`ref_leveldraw.sorted_draw_order` is the no-parent case. World chunks are queued with
flag 0 (O 0x18921c, `addiu` of 0 into the flag argument).

## 3. Environment mapping

Flag 0x10 uploads six matrix rows and runs VU entry 0x16, then the packet's own
`MSCAL 0x48` (O 0x1887b8; the six-row count is Executed, the packet grows from 240 bytes
to 288). Rows 0–3 are `g_viewProjWorld` (0x44f180) with the chunk rotation folded in.
Rows 4–5 do not use that rotation. A free rotation (flag 0x1 clear, cosine 0 and sine
32767) changes rows 0–1 and leaves rows 4–5 alone (Executed).

Rows 4–5 are taken from the camera matrix at 0x44f110. Each axis is three floats
`(x, y, z)` and only `x, y` are read (Executed: floats 1, 2, 3, 4, 5, 6, 7, 8, 9 in
that memory produced `6 × (1, 2, 4, 5)` and `(6 × 7, 6 × 8, 192, 192)`; 3, 6 and 9 never
appeared). `ref_leveldraw.axis_xy`.

```
row4 = 6 × (m00, m01, m10, m11)
row5 = (6 × m20, 6 × m21, 192 + scroll, 192)
```

When flag 0x1 is set, the quarter-turn code in chunk +0x36 (low 3 bits) permutes the X
and Y pairs only. Bit 0 negates the first pair, bit 1 the second, bit 2 swaps the pairs.
The Z pair is not turned (Executed, codes 0..7). `ref_leveldraw.quarter_turn`.

`scroll` is `(g_simFrame & 0x3ff) × 0.25` when bit 2 of the level option word 0x44fe08
is set, and 0 otherwise (Executed: frame 100 with the bit set gives 217; frame 0x400
gives 192; frame 0x3ff gives 447.75). `ref_leveldraw.env_rows`.

Per vertex the microcode then does what render-pipeline section 4.6 already checked:

```
n' = stored normal / 16
(u, v) = (row5.z, row5.w) + n'.x × (row4.x, row4.y) + n'.y × (row4.z, row4.w)
         + n'.z × (row5.x, row5.y) + 0.07 × (sx, sy)
```

in texels. `ref_leveldraw.env_uv` is that formula. This round did not get a clean
`XGKICK` out of a hand-built 0x48 batch (the program ran, the GIF tag it kicked did not
end), so the per-vertex half is not re-difftested here. The rows it multiplies are.

The first pass is GS context 2: `ALPHA_2` 0x2a, the fixed environment texture
(`gfx_emitContext2Setup` 0x19c540; render-pipeline section 6). The second pass is the
chunk's own texture with `ALPHA_1` 9. Every one of 120 `env.lmp` lumps on the disc has
a single member, `envtex.etex` (D). The executable names `env.lmp` and does not name
`envtex`; the member name is inside the lump. Upload is 0x19e440, already traced in
render-pipeline section 6.

## 4. Automap tiles

The grid loaded by `automap_loadGrid` (0x168894) is 216 × 216 cells of u16 at 0x4044f0,
row-major, stride 432 bytes. The drawer 0x168cac copies a rectangle of those cells into
its display-list packet and uploads a small VU1 program (MPG, then `MSCAL` 0x79a and
0x79c). The cell codes are not turned into UVs on the CPU. Running that packet in
`tools/vu1_emu.py` gives the vertices below (Executed).

A cell:

| Bits | Meaning |
|---|---|
| 0–4 | atlas column |
| 5–7 | one of eight orientations |
| 8–11 | atlas row |
| 12–15 | explored level, 0 in the file (O, `world.md`) |

The quad whose corners are cells `(c, r)`, `(c, r+1)`, `(c+1, r)`, `(c+1, r+1)` shows
the tile of the bottom-right cell only. The four vertices are emitted in that corner
order. Column `col` and row `row` occupy GS UV

```
u from col × 160 to col × 160 + 158
v from row × 160 to row × 160 + 158
```

which is a 10-texel tile (UV is texels × 16) with the far edge 2/16 of a texel short of
the next tile. Orientations 0..7 are the eight assignments of those two U edges and two
V edges to the four vertices, in `ref_leveldraw.AUTOMAP_ORIENT`. Orientation 0 is
`(near, near), (near, far), (far, near), (far, far)`. `ref_leveldraw.automap_quad`.

Each vertex's alpha is the high byte of **that corner's** cell, not of the tile cell.
The high byte is `(explored << 4) | row`, so the corner's own row field adds 0..15 on
top of the explored level. Explored 0 with row 0 is alpha 0. The tile packet sets
`ALPHA_1` 0x44 (`src × As + dst × (1 − As)`), `TEST_1` 0x3001c (alpha test off, depth
test always), `TEX1_1` 1 (point sampling) and `ZBUF` from the 64-bit word at 0x44fd60
(`g_zbufNoWrite`). It is queued at layer 5 (Executed, both packets). An unexplored cell
is still drawn; with alpha 0 the blend leaves the destination unchanged.

Which screen rectangle the drawer fills depends on the floats the HUD passes and on the
grid width and height at 0x4044dc and 0x4044e0. Those floats were not reduced to a
formula here. The difftest feeds one fixed argument list, records which cells
`memcpy` copies, and checks the vertices against `automap_quad`.

## 5. `D_SWAMP.LMP` and `dome.vif`

Nothing loads `D_SWAMP.LMP`, and nothing loads a member named `dome.vif`.

- The executable contains the string `dome.lmp` once, and no `dome.vif`, `domeLump`,
  `D_SWAMP`, `d_swamp` or `d_air` (byte search, either case). O.
- `game_loadLevel` does `lump_findLoaded("dome.lmp")` and stores the pointer at
  0x86af54 (0x1e5d48–0x1e5d68). The only reader is `game_drawBackdrop` (0x1e78dc). It
  draws every `vif` in that already-loaded lump through `model_draw`. O. The lump is a
  member of the level GOB, found because the member is named `dome.lmp`.
- Of the 18 top-level `D_*.LMP` files, 10 are byte-for-byte the same as the `dome.lmp`
  member of one or more GOBs (D, whole-file comparison; the hashes are not recorded
  here). Those GOBs are `AIRARENA` (`D_AIR`), `BOSSEVIL` and `HUB` (`D_NEWAIR`),
  `BOSSGOOD` (`D_PF`), `CITADEL`, `PVPTOR`, `TORBONUS`, `TORMEDAL`, `TORMENT2`,
  `TORMENT3` (`D_CIT`), `DIS2` and `DISEASE0` (`D_DIS`), `ENDBAD` (`D_SPACE`),
  `ENDGOOD` and `ISLSM1` (`D_SUNNY`), `FIRE5` (`D_DRAG`), `INTRO` and `INTRO_~1`
  (`D_CS`), `TORMENT0`, `TORMENTA` and `TORMENTB` (`D_TORM`). 21 members.
- `D_SWAMP.LMP` matches none of them. Its only geometry member is `dome.vif`, and that
  name occurs in no other file. `SWAMP1.GOB` and `SWAMP2.GOB` have no `dome.lmp`. The
  other loose files that also match nothing are `D_BURN`, `D_CAVE`, `D_HATE`,
  `D_HATE2`, `D_HATEIN`, `D_KELETH` and `D_NIGHT`. D.
- `model_draw` does not emit `STROW` (`docs/formats/model-row-registers.md`). The retail
  domes that do draw are the embedded `dome.lmp` copies, through ordinary model
  programs. The 59 `MSCAL 0x46` packets in `D_SWAMP`'s `dome.vif` are not referenced.

So the native client's refusal of model form 0x46 has no retail picture. The three row
choices in `ref_model_rows` stay as they are; none of them is supplied by a loader of
this file.

## 6. Reference

```
chunk_gs(flags) -> alpha1, alpha2 or None, test, layer, env
chunk_light(flags) -> (kind, constant or None, flags after the call)
axis_xy(camera9) -> (m00, m01, m10, m11, m20, m21)
quarter_turn(axis, code) -> axis with the X/Y pairs turned
env_rows(axis, frame, level_options, quarter=None) -> (row4, row5)
env_uv(normal, rows, sx, sy) -> (u, v) texels
automap_fields(cell) -> col, orient, row, explored, alpha
automap_quad(cell_c_r, cell_c_r1, cell_c1_r, cell_c1_r1) -> four (u, v, alpha)
sorted_draw_order(items) -> layer -> payloads in send order
```

`chunk_gs` and `chunk_light` refuse flags 0x80, 0x800, 0x4000 and 0x8000.

## Still open

- The per-vertex environment UV was not re-run against program 0x48 in this round. The
  formula in render-pipeline section 4.6, and the rows above, are the two halves.
- Which way the automap's screen Y points relative to grid row 0. The vertex order is
  the corner order in section 4; the HUD floats that place the window were not reduced.
- The colours 0x149b90 writes for a dynamic light. The path is executed; the slot
  values are the earlier account in render-pipeline section 4.6.
