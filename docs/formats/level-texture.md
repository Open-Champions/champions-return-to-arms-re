# Level textures: `<LEVEL>.TEX`

How the textures of level geometry are stored in the `<LEVEL>.TEX` file beside each level
`.GOB` of *Champions: Return to Arms* (`SLUS_209.73`, US v2.00), and how the game streams,
unpacks and uploads them. Written for someone building a native loader; everything a
loader needs is in sections 2 to 6. `tools/ref_leveltex.py` is the executable form of this
document and `tools/test_ref_leveltex.py` checks it on synthetic cells.

This closes the item `docs/formats/world.md` left open ("Decoding cell textures to pixels was
not tried") and the one `docs/FORMATS.md` describes as "a packed form that the game unpacks".
Nothing here was run on a console or in an emulator: the layout was read from the executable
and then checked against every cell of every level file on the disc (section 8).

Status letters: **O** read in the code at the address given; **D** holds in every file on the
disc, no code read for it; **I** inferred; **U** unknown. Integers are little endian.

## 1. What the earlier documents got right and where this starts

- `world.md`: the directory, the cell id rule, the 3 × 3 streaming window, the 0x40-byte
  headers and the cell-relative payload offset (header +0x10) are confirmed below with the
  same addresses. Two corrections: the first u32 of the directory is never read (the game
  tests the *first record's id* against 0, 0x181f30), and the "always loaded" cells exist in
  code only — the function that would register one (0x17fe18) has no caller, and the count
  (0x7d35a0) is only ever reset (0x1826c8). So every level texture on the disc goes through
  the streaming slots.
- `model-texture.md`: header flags 0x0001 and 0x0100 "never set in a lump" is right. In the
  level file **every** texture has flags 0x010c (D, 157,820 of 157,820): 0x0100 is the
  block-table form described here, 0x0004 means 256-colour as in lumps, 0x0008 has no
  reader that was found. Flag 0x0001 (an extra indirection of the payload word,
  0x179f7c–0x179fa0, and a 1,200-instruction preparation routine at 0x17e6c0) occurs in no
  file; it is not described further and `ref_leveltex` refuses it.
- The native client's historic refusal count ("109 inputs exceed the bounded lump packet
  size", `open-champions-godot` `docs/TEXTURE_PREVIEW.md`) counts the loose `<LEVEL>.TEX`
  files it was shown — files, not textures. The disc has 111 level files holding 4,808
  cells and 157,820 textures (section 8). The two counts are different denominators.

## 2. The file: directory and cells

```
+0x00  u32        never read (0 in all 111 files, D)
+0x04  record[]   {s32 cell id, u32 file offset, u32 size}, ended by an id of -1 or -2
...
cell   at its file offset: see section 3
```

- `world_fixup` (0x181ec4–0x181fe8) reads the first 0x5000 bytes of `"%s.tex"` (format at
  0x5341d0, base name `g_levelTexName` 0x44fe18), skips the first word, and stops at a record
  whose `id + 2` is below 2 unsigned, i.e. id −1 or −2. If the first record's id is 0 there is
  no directory. O. On the disc every file ends with −2, has 4 to 148 records, 0 in the
  first word, and the directory never reaches 0x5000 bytes (D). `ref_leveltex.parse_directory`.
- Records go into the world's cell table (world header +0x64): `(highest − lowest + 1)`
  entries of `{offset, size}` placeholders `{0, 0x40}`, index `id − lowest`, with lowest and
  highest from world header +0x58 / +0x5c. The id is not range-checked (O); on the disc
  every id lies in its world's range and the ranges span up to 1,793 ids (D).
  `ref_leveltex.cell_table`.
- Cell id = `row × 100 + column`, `column = floor(x / size) + 50`, `row = floor(y / size) + 50`,
  size = world header +0x68 (720 in all 111 worlds; 0 would mean 960, 0x182264). O
  0x17d8e0–0x17d930. `ref_leveltex.cell_id_of`.
- Offsets and sizes are multiples of 2,048 (D, all 4,808 cells); the streamer rounds sizes up
  to 2 KB anyway (0x17df38). Cells are 2 KB to 1.5 MB.

## 3. A cell

```
+0x00   u32   texture count n (at most 16,000: 0x17e000 reports more as an error)
+0x04   zero to +0x40 (D)
+0x40   header 0 (0x40 bytes)      ... header n-1 at 0x40 * n
then    palette structures (section 5), block streams (section 6) and record lists (section 4),
        in no order a loader needs: everything is reached through offsets from the cell start
```

O 0x17dff8–0x17e05c (`worldtex_stream`, when the last piece of a cell has arrived):
`count = *(cell)`, then `tex_relocateInCell(world, cell + 0x40 + 0x40·i, blockMap, base)` for
each header.

**Header** (0x40 bytes; the same fields as a lump `.tex` header, `model-texture.md`, but
offsets are from the cell):

| Offset | Type | Meaning | Status |
|---|---|---|---|
| 0x00 | u16 | width in texels (1 to 1024 on the disc) | O 0x17cee4 (upload width) |
| 0x02 | u16 | height | D (rectangles fit it) |
| 0x04 | u16 | GS blocks the texture needs: 4 for the palette + the highest block number any rectangle writes + 1 (section 6) | O read by `texcache_alloc` 0x179bb0; the sum is D, all 157,820 |
| 0x06 | u16 | 0 in the file; relocation stores the upload length in qwords: `0x48 + Σ(6 + 16 × blocks)` over the rectangles | O 0x179fb0–0x17a0b0 |
| 0x08 | u16 | flags, 0x010c in every texture | D |
| 0x0a | u16 | 0; relocation stores 0xa7fb | O 0x179f34 |
| 0x0c | u32 | TEX0 fragment: TBW = 2 × DBW (section 6), PSM 0x13 (PSMT8), TW = TH = 10, TCC 1, TFX 0 — in every texture | D; use O `model-texture.md` |
| 0x10 | u32 | offset of the payload from the start of the cell (multiple of 4) | O 0x179f38–0x179f78 |
| 0x14 | u32 | 0; run time: pointer to the built upload chain, 0 = not built (section 7) | O 0x1888a8, 0x17d668 |
| 0x18 | s16 | 0; run time: first GS block | O |
| 0x1a | s16 | 0; run time: ring slot | O |
| 0x1c | u32 | 0; relocation stores −1, then the last frame that used the texture | O 0x179f2c |
| 0x20 | | zero | D |

`tex_relocateInCell` (0x179f28–0x17a0b8) is `tex_relocate` with one difference: every offset
goes through the cell's 128 KB block map, `pointer = base + (map[off >> 17] << 17) + (off & 0x1ffff)`
(0x179f44–0x179f70), because the cell was read in 128 KB pieces into whatever blocks of the
segment cache were free (section 7). The payload word and all block offsets of section 4 are
relocated this way; nothing else in the cell is. `ref_leveltex.relocate_offset`.

## 4. The payload: palette word and rectangle records

At header +0x10 (O 0x179fb4–0x17a0ac, relocation; 0x17d068–0x17d0e4, upload):

```
u32   offset of the palette structure (section 5), from the start of the cell
record...
record:  s8 x0, s8 y0, s8 x1, s8 y1     block coordinates; x0 == -1 ends the list
         u32 offset[(x1-x0+1) * (y1-y0+1)]   one block stream per block, rows y0..y1 outer, x0..x1 inner
```

A **block** is one GS block of 256 bytes: 16 × 16 texels of the 8-bit texture, which is
8 × 8 pixels of the 32-bit upload (section 6). Coordinates are in blocks, so a record
covers texels `[16·x0, 16·(x1+1)) × [16·y0, 16·(y1+1))`. D for all 157,820 textures:
`x0, y0 ≥ 0`, `x1 ≥ x0`, `y1 ≥ y0`, `(x1+1)·16 ≤ width rounded up to 16`, likewise for the
height, `(x1+1)·8 ≤ 64·DBW`; the records cover 61% to 100% of a texture (blocks no triangle
samples are left out, as the exporter does for lump textures); several blocks of a texture,
and blocks of different textures, often share one stream (identical content). Block offsets
are even (the bit reader fetches 16-bit words).

Relocation adds to header +6 `0x48` once, then `6 + 16 × blocks` per record
(0x179ff0–0x17a040 with the R5900 three-operand `mult` at 0x17a020 that the listing shows
as `<unknown>`): that is the qword length of the chain of section 7.
`ref_leveltex.read_records`, `relocated_qwords`.

## 5. The palette structure

Pointed at by the payload word; shared by textures (1 to 118 per cell on the disc), never by
two cells. O 0x17cdec–0x17cf7c (the worker thread copies and indexes it):

| Offset | Size | Contents |
|---|---|---|
| 0x000 | 0x400 | 256 RGBA (R, G, B, A bytes; A 0–0x80). Uploaded as a 16 × 16 32-bit rectangle, so entry *i* is at position *i* with bits 3 and 4 exchanged, as for lump 8-bit palettes (I: same upload, same order; the decoded pictures are right with it) |
| 0x400 | 0x800 | successor table: 256 rows of 8 bytes; row *v* lists eight texel values that may follow a texel of value *v* (symbols 0x105–0x10c pick one, section 6) |
| 0xc00 | u32 | *n*, number of code-table entries (262, 264, 266, 268 or 270 on the disc; the alphabet has 269 symbols, so an entry may be unused) |
| 0xc04 | u16 × n | `symbol[]`, symbols grouped by code length, in code order |
| +2n | s32 × 18 | `S[0..17]`: `S[k]` = index of the first symbol of length *k* minus its first code. `S[0]`, `S[17]` and the entries of lengths without codes are not read |
| +2n+0x48 | s32 × 17 | `T[0..16]`: `T[k]` = the last (highest) code of length *k*, −1 when there is none. `T[0]` is not read |

The code is a **canonical Huffman code** with lengths 1 to 16, read most significant bit
first: a code of length *k* belongs to length *k* when `T[k] ≥` its top *k* bits, tried from
the shortest length up; the symbol is `symbol[code + S[k]]`. The worker builds a 256-entry
table for lengths 1–8 first (0x17cf84–0x17d03c: for each 8-bit prefix the first `k ≤ 8` with
`T[k] ≥ prefix >> (8−k)`, entry `(symbol, k)`, or `(0, 0)` meaning "longer"), then decodes
longer codes by comparing `T[9]`, `T[10]`, … (0x17d2f0–0x17d368). On the disc all codes are
2 to 14 bits (D). `ref_leveltex.read_tables`, `build_fast_table`, `decode_symbol`.

## 6. A block stream, and where its texels go

**Bit reader** (O 0x17d2a0–0x17d2c4): the stream is 16-bit little-endian words; a 32-bit
window `(word[p >> 4] << 16) | word[(p >> 4) + 1]` is shifted left by `p & 15` and its top 16
bits are the next bits of the stream, most significant first. `ref_leveltex.BitReader`.

**Decoding one block** (O 0x17d288–0x17d3cc): 256 symbols are decoded, one per texel
*i* = 0 … 255, with *v* the previous texel's value (0 before the first):

| Symbol | Texel *i* | |
|---|---|---|
| 0x000–0x0ff | the symbol | literal |
| 0x100–0x104 | texel `i + d`, `d` = −1, −16, −17, −15, −2 (five signed bytes at 0x41c1a0) | the texel to the left, above, above-left, above-right, two to the left of a 16-wide raster |
| 0x105–0x10c | `successor[v][symbol − 0x105]` | one of the eight likely successors of the previous value |

A back-reference before texel 0 would read the stack; no block on the disc does it and
`ref_leveltex` refuses it. `ref_leveltex.decode_block`.

**Texel order.** Texel *i* of the decoded block is texel `(i & 15, i >> 4)` of the 16 × 16 block
— row by row. O: the 256-byte permutation the worker applies (`texcache_init` → 0x17a0c0,
transcribed in `ref_leveltex.block_permutation`) sends decoded texel `x + 16·y` to the byte
of the 8 × 8 32-bit pixel block where the GS keeps 8-bit texel (x, y); `test_ref_leveltex`
proves that for all 256 positions against the address formulas of `model-texture.md`. The
back-reference deltas are then the four raster neighbours and "two to the left".

**Upload** (O 0x17d0e8–0x17d200, 0x17d3d0–0x17d478): each record becomes one GS transfer of
32-bit pixels — `TRXPOS` destination `(8·x0, 8·y0)`, `TRXREG` `(8·(x1−x0+1), 8·(y1−y0+1))`,
`TRXDIR` 0, `BITBLTBUF` destination width `DBW = (width + 127) >> 7` in 64-pixel units
(0x17cee4–0x17cf08), format 0 (PSMCT32) — whose IMAGE data is the blocks of the record in
record order, each permuted into 8 rows of 8 pixels. The texture is then sampled as PSMT8 with
`TBW = 2·DBW` (header +0xc, D), which makes 32-bit block (bx, by) and 8-bit block (bx, by) the
same 256 bytes. The palette goes first: one 16 × 16 32-bit rectangle at (0, 0) of a buffer of
width 1 (0x17cdb0–0x17cde8), into the texture's first four GS blocks; the image starts four
blocks later (`gfx_dmaHandler` 0x16c008–0x16c030). Header +4 is therefore
`4 + max(page·32 + block) + 1` over the blocks written, with `page = (by >> 2)·DBW + (bx >> 3)`
and the 8 × 4 block table of `model-texture.md` (D, all 157,820). `ref_leveltex.allocation_blocks`.

**So, for a loader** (`ref_leveltex.decode_texture`): texel (x, y) is byte
`(y & 15)·16 + (x & 15)` of the decoded block `(x >> 4, y >> 4)` if some record covers that
block (the last record that does, as later uploads overwrite); otherwise the texture has no
data there (the reference returns index 0 and reports the texel uncovered). Colour =
palette entry, in index order after the bit-3/4 exchange. Alpha and blending are the level
chunk's business: which `ALPHA` and `TEST` the drawer writes, the sort layer, the
environment-map rows and the automap tile codes are executed in
`docs/formats/level-draw.md` (`docs/spec/render-pipeline.md` section 6 has the blend
equations: modulate, `ALPHA_1` 2 or 1 or 0x48 by chunk flags, no mip maps, repeat wrapping,
bilinear in layer 0). The GS replay
(`decode_texture_via_gs`) gives the same indices as this shortcut on every synthetic and real
texture tried; it exists to prove the shortcut.

## 7. Streaming, relocation base and lifetime

For a native loader this section is background: a PC can hold every cell of a level at once.
It is here because the planner asked for the relocation base and the lifetime.

- **Segment cache.** `world_prepare` (0x1823f0–0x1825bc) sizes it as the largest sum of
  `world_texCellBlocks` over any 3 × 3 cell window (rows and columns 1–98), in 128 KB blocks,
  stores the count at world +0x60 (−1 in the file) and the pointer at +0x7c
  (`mem_allocTagged(count << 17, "segment cache")`). One byte per block at 0x7d2ed0 says
  whether it is in use.
- **Slots.** Nine streaming slots: `g_texStreamCells` 0x7d2fd0 (cell id per slot, −1 empty),
  `g_texCellBlob` 0x425df8 (pointer to the cell's first block per slot; 17 entries, 9 + 8 for
  the never-used always-loaded pages), block maps at 0x7d2650 (slot × 0x80 bytes: piece *k*
  of the cell → cache block, 0xff past the end), `g_texCellSlot` 0x41c1b8 (one byte per cell
  id 0–39,999: slot or −1).
- **Which cells.** `worldtex_stream(-1)` (0x17d830, called from the main loop) wants the nine
  cells around `g_cameraFocus` (`ref_leveltex.cells_around` gives the order it lists them);
  `worldtex_stream(cell)` wants one named cell (`world_touchTexturesInView` 0x189df0). It is a
  four-state machine at 0x425e8c: (0) pick the wanted cell with a record (size ≠ 0) that is not
  loaded and nearest to the focus — the explicitly named cell counts as distance 0 — and, if
  the CD is idle, choose slots to evict (loaded slots not in the wanted list, until the free
  blocks cover the cell's size, 0x17dcf0–0x17dd98), stop the worker thread, open the file at
  the cell's offset; (3→2) evict: `tex_evict` 0x17feb8 for every header of each evicted slot
  (frees its upload chain and clears +0x14), free the slot's blocks, slot ← empty; (1) read one
  128 KB piece per call into a free block, recording it in the slot's block map; when the
  whole cell is in, relocate every header (section 3) and publish the slot. O.
- **Relocation base and lifetime.** The base is the segment cache (world +0x7c); the offsets
  become pointers once, when the cell is published, and stay valid until the slot is evicted —
  the cell's blocks are not moved while loaded. A texture's upload chain (header +0x14) is
  built later, on demand, and lives in a pool of 4 KB pages (0x7cfe48 base, 0x7cfe50 one
  `{owner, next}` pair per page, 0x500 pages); the worker frees chains that no draw used for
  3 frames (0x17cc40–0x17cd1c) and `tex_evict` frees them when the cell goes. O.
- **On demand.** `world_drawChunk` (0x188874–0x1888d0): a chunk whose cell is not loaded, or
  whose header still has +0x14 = 0, is not drawn; the latter is queued through
  `worldtex_requestUpload` 0x17fc78 (a 64-entry ring at 0x7d3340, head 0x7d3540, tail
  0x7d3544). The worker thread (entry 0x17ca58, created by `texcache_init` with a 16 KB
  stack, priority 6) takes textures off the ring between frames, decodes the blocks into the
  scratchpad, moves 4 KB at a time into the pool (0x17c730) and finally stores the chain head
  at +0x14. Upload to the GS happens in `gfx_dmaHandler` (0x16bff0–0x16c044): the chain is
  `call`ed as a DMA tag, after the palette block (+0x24 of the chain) and image block (+0x484)
  numbers are patched in. The chain is 0x48 qwords for the DMA tag, GIF tag, four registers,
  IMAGE tag and 64 palette qwords, plus per record 6 + 16 × blocks — the number relocation
  put in header +6. O.
- `game_clearLevel` → 0x17e2c8 stops the worker, frees the cache and resets the tables;
  0x17e4c8 (called from inventory, shop and level code) clears the request ring. O for the
  callers; bodies skimmed.

Per machine: which cells are loaded and which chains exist follow the camera and the
frame timer; a chunk whose texture is not ready is simply not drawn that frame
(`world.md` already lists this). Nothing here writes shared game state.

## 8. What was checked

| | Result |
|---|---|
| Disc | 111 `<LEVEL>.TEX` files, 4,808 cells, 157,820 textures; every header, TEX0 fragment, payload word, record list and code table satisfies sections 2–6 (flags 0x10c, PSMT8, TBW = 2·DBW, TW = TH = 10, TCC 1, TFX 0, run-time fields 0, rectangles inside the buffer and the texture, offsets inside the cell and even, `T` canonical, `T[k] + S[k]` inside `symbol[]`, header +4 as stated); every cell id inside its world's +0x58/+0x5c range; directories end with −2 and never reach 0x5000 bytes |
| Blocks decoded | all 10,558,802 block streams of all 111 levels (every block of every rectangle of the 157,820 textures, shared streams counted once per use) decode to 256 texels without an unmatched code or an out-of-block reference, consuming 14,335,566,510 bits, all inside their cells |
| GS replay | `decode_texture_via_gs` equals `decode_texture` on 22 real textures of six cells and on the synthetic cells of the tests |
| Looked at | two textures of one arena cell (a 255 × 49 atlas of ground marks, a 131 × 94 pre-lit soil patch with a shadow edge): coherent, no seams between blocks. Rendered pictures stay under `work/` of the worktree |
| Tests | `python3 -m unittest discover -s tools -p 'test_ref_leveltex.py'`: synthetic cells with short and long codes, all three symbol kinds, L-shaped and partial coverage, shared streams, truncated prefixes, bad flags / fields / rectangles / tables, directory and cell table, the permutation against the GS formulas, the relocation arithmetic |

Not checked: the alpha semantics in a drawn level (nothing was drawn), flag 0x0008, the
flag 0x0001 form (no input exists), the 0x17e6c0 routine.

Usage (private input; keep output out of the repository):

```
python3 -I tools/ref_leveltex.py LEVEL.TEX                 # cells
python3 -I tools/ref_leveltex.py LEVEL.TEX --cell 5050     # headers of a cell
python3 -I tools/ref_leveltex.py LEVEL.TEX --cell 5050 --index 3 --ppm out.ppm
```

## 9. Functions and data

New names are in `symbols/fmt-world.tsv` (and `fmt-model.tsv` for the permutation builder).

| Address | Name | Role |
|---|---|---|
| 0x181d30 | `world_fixup` | reads the directory (0x181ec4–0x181fe8) |
| 0x182360 | `world_prepare` | segment cache size (0x1823f0–0x1825bc) |
| 0x1822e8 | `world_texCellBlocks` | cell size in 128 KB blocks |
| 0x17d830 | `worldtex_stream` | the four-state streamer |
| 0x179f28 | `tex_relocateInCell` | header relocation through the block map |
| 0x17d680 | `worldtex_loadAlwaysPages` | always-loaded cells; its list is never filled (0x17fe18 has no caller) |
| 0x1887b8 | `world_drawChunk` | texture gate and upload request (0x188874–0x1888d0) |
| 0x17fc78 | `worldtex_requestUpload` | request ring |
| 0x17ca58 | `worldtex_workerThread` | decodes blocks, builds the upload chain |
| 0x17a0c0 | `worldtex_buildBlockPermutation` | the 256-byte swizzle table at 0x7d3040 |
| 0x17c730 | `worldtex_flushChainPage` | moves 4 KB of chain from the scratchpad to the pool |
| 0x17feb8 | `tex_evict` | frees a texture's chain |
| 0x17e2c8 | `worldtex_shutdown` | from `game_clearLevel` |
| 0x17e4c8 | `worldtex_clearRequests` | |
| 0x17e6c0 | — | flag 0x0001 preparation; no input on the disc |
| 0x16b998 | `gfx_dmaHandler` | sends the chain (0x16bff0–0x16c044) |
| 0x41c1a0 | `g_texBackrefDeltas` | the five deltas |
| 0x7d3040 | `g_texBlockPermutation` | |
