# Program 0x46 in a model file: the row registers

What the VIF row registers hold when a `.vif` model packet runs vertex program 0x46, the
level-geometry program, whose positions are unpacked with `STMOD 1` (the VIF adds its ROW
registers to every position). `docs/formats/model-texture.md` left this open; the native
client refuses the one such model for want of "the external row transform". This note says
exactly where the rows come from, so the refusal can be an informed decision rather than a
gap. `tools/ref_model_rows.py` is the executable form; `tools/test_ref_model_rows.py` runs
it on authored vectors.

Status letters as in `model-texture.md`: **O** observed at the address, **D** data only,
**I** inferred, **U** unknown.

## 1. The mechanism

- `STMOD 1` is VIF "offset mode": after a V3-16 signed unpack each component is sign-extended
  to 32 bits and ROW0..ROW2 are added as 32-bit integers, before the data is written to VU1
  memory (PS2 VIF behaviour; the level program then divides by 16,
  `docs/spec/render-pipeline.md` 4.6: `p = (stored + (tx, ty, tz)) / 16`).
- ROW0..ROW3 are VIF1 state set by a `STROW` code (0x30000000 followed by four words) in the
  DMA stream and kept until the next `STROW`. Nothing resets them per frame: no `STROW` is
  emitted by `gfx_beginFrame` (0x19c86c; its 0x3000 constant at 0x19c870 is a DMA `ref` tag).

## 2. Who writes the rows (O)

Every `lui …, 0x3000` in the rendering code (0x160000–0x1a0000, 29 sites) was classified by
what the register is used for. Twenty-seven build DMA `ref` tags (`or` into an address, `sd`
of a 64-bit tag). Two are VIF `STROW` codes:

| Site | Function | Rows written |
|---|---|---|
| 0x1890b4–0x1890c0 | `world_drawChunk` 0x1887b8, before each geometry chunk's packet | `(tx, ty, tz, 0)`: the chunk's translation in 1/16 units (`world.md`, "the chunk translation goes into the VIF row registers") |
| 0x175a6c–0x175ae4 | 0x175950 | `(0, 0, 0, 0)` |

0x175950 is the model-side set-up for the level programs: `DIRECT` with `TEXFLUSH`, `TEX0_1`
(0, patched by the DMA handler), `ALPHA_1` = model header +0x18, `TEST_1` = 0x507f5; `ITOP 1`;
`UNPACK V4-32` of the caller's 4 × 4 matrix to VU address 0; `MSCAL 0x16`; `ITOP 1`;
`MSCAL 0x34`; `STROW 0, 0, 0, 0`. **It has no caller** (`tools/dis.py` reports callers=0;
`docs/spec/render-pipeline.md` section 13 and `docs/issues/doc-corrections.md` row 106 said
so already). Its existence shows what the authors intended for a 0x46 model: rows of zero,
positions stored absolute in 1/16 units like any model.

None of `model_draw` 0x1779b0, `model_emitDrawSetup` 0x175670, `model_drawPart` 0x178c28,
`model_emitMeshRefs` 0x179260, `world_drawModelChunk` 0x187eac or `game_drawBackdrop`
0x1e78d0 emits a `STROW`.

## 3. What that means for the one model (I for the rows, O and D for the loader)

The only `.vif` with a 0x46 packet on the disc is `dome.vif` of the top-level `D_SWAMP.LMP`
(59 packets, `model-texture.md`). Drawn through `model_draw`, its positions would receive the
rows of the last `world_drawChunk` sent before it in that frame's VIF1 stream — a chunk
translation of up to thousands of 1/16 units, different every frame — or zero before any
chunk was ever drawn. There is no model-side value. A standalone reader therefore has three
honest options, and `ref_model_rows.rows_for_model` names them:

- `uncalled-0x175950`: rows (0, 0, 0, 0), what the dormant set-up would give;
- `inherited`: rows supplied by the caller from a known preceding chunk (the reference refuses
  to invent them);
- refuse, as the native client does today.

Whether the question ever arises on the retail disc is settled, and it does not
(`docs/formats/level-draw.md` section 5):

- the executable contains the string `dome.lmp` and no `dome.vif`, `domeLump`, `D_SWAMP`
  or `d_swamp` (byte search, either case). O;
- `game_drawBackdrop` draws only the lump found under the name `dome.lmp`
  (`lump_findLoaded`, 0x1e5d48–0x1e5d68, stored at 0x86af54). O. Ten of the eighteen
  top-level `D_*.LMP` files are byte-for-byte that member inside 21 level GOBs. D.
  `D_SWAMP.LMP` is not one of them, `dome.vif` occurs only inside it, and `SWAMP1.GOB`
  and `SWAMP2.GOB` have no `dome.lmp`.

The 59 `MSCAL 0x46` packets are unreferenced. The native refusal of model form 0x46 has
no retail picture. The three choices above stay available for a file that is opened
some other way; no such open was found.

## 4. Contract for the reference (`tools/ref_model_rows.py`)

```
stmod_add(position, rows)        32-bit wrap-around add per component
world_units(position, rows)      (stored + row) / 16
rows_for_level_chunk(tx, ty, tz) (tx, ty, tz, 0)
rows_for_model(provenance, preceding_chunk_rows=None)
packet_positions(stored, rows)
```

The tests cover zero rows, non-zero rows with positive and negative components, the 32-bit
wrap, sign extension of 16-bit inputs, and that `inherited` without a preceding chunk is an
error.

## 5. Corrections to earlier documents

- `model-texture.md`, open questions: "where its row registers are set for it" — answered
  above: by nothing on the model side; the uncalled 0x175950 would set them to zero.
- `world.md`, "the chunk translation goes into the VIF row registers" is confirmed as the
  only live `STROW` in the renderer.
