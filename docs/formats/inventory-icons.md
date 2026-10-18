# Inventory picture-cache pixels (SLUS-20973 v2.00)

Research date: 2026-10-17. Branch `t3/research-ui`, based on `a2b145b`.
Companion: [reference decoder](../../tools/ref_inventory_icons.py),
[synthetic tests](../../tools/test_ref_inventory_icons.py).

**Observed, high confidence:** the serialized payload contract below is sufficient
to decode all **11,511 entries in 449 groups** of the privately supplied v2.00
`BG/DATA/PICCACHE.HDR` / `PICCACHE.DAT`. Every logical pixel was covered by an
upload in the reference decoder. This is a full-cache structural/decoder audit,
not a screenshot comparison or a claim that every item is displayed correctly
by the native client. No game, server, native build or online session was run.

## Addressed evidence

All addresses are EE virtual addresses in this revision. O = observed in code or
private file structure; I = inference; U = unknown. Confidence applies to the
stated observation, not to untested runtime integration.

| Evidence | Established fact | Level |
|---|---|---|
| `picCache_serviceRequests` `0x1003cc`, specifically `0x100700–0x100728` | Read `entry.sector << 11`, `entry.sectors << 11` from `piccache.dat` | O / high |
| `0x100458–0x1004e4` | Copy only the first 0x40 bytes into the cached picture header | O / high |
| `0x1004f0–0x100500` | u16 qword count at +6; packet offset at +0x10 is relative to the start of the sector payload | O / high |
| `0x100504–0x100654` | Split contiguous upload data into at most 79 qwords per 0x500-byte cache block | O / high |
| `0x100620–0x100630`, `0x100694–0x10069c` | Runtime +0x14 becomes the DMA chain head; +0x0a becomes 0xa7fb; +0x10 becomes zero | O / high |
| `gfx_dmaHandler` `0x16b998`; [existing texture research](model-texture.md) | GS upload and TEX0 reconstruction; palette/image destination bases are patched at runtime | O / high |
| `ui_drawSpriteImpl` `0x17b590`, clipped variant `0x17b8b0`, core `0x17ab50` | Used dimensions, full-resource source bounds, field selection | O / high |
| `0x17abc0–0x17ac2c`, `0x17ad18–0x17ae10` | Source V uses half logical height plus the selected field's base | O / high |
| Full HDR/DAT scan, byte offsets in the following tables | One palette and one image per entry; dimensions agree with index | O / high |

The name/group/variant index is already described in
[startup.md, Picture cache](../startup.md). A DAT entry is **not** a PNG, a raw
`width * height` index array, or a runtime DMA chain. The chain is built after
reading the contiguous serialized GIF packet.

## Serialized header

All integers are little-endian. Offsets here are relative to
`DAT + entry.first_sector * 2048`, bounded by `entry.sectors * 2048`.
The following structure is **O / high**, from the addressed consumers above and
the full cache scan. Unknown meanings are explicitly retained.

| Offset | Type / size | Meaning |
|---|---|---|
| +0x00 | u16 | Logical used width W, also the index entry's width |
| +0x02 | u16 | Logical used height H, also the index entry's height |
| +0x04 | u16 | GS allocation size in 256-byte blocks, including palette; `texcache_alloc` `0x179bb0` |
| +0x06 | u16 | Q: total serialized upload length in 16-byte qwords |
| +0x08 | u16 | Flags: observed 0x0044, 0x0844, 0x1044, 0x1844 |
| +0x0a | u16 | Zero on disc; runtime relocation marker, not a pixel format |
| +0x0c | u32 | TEX0 fragment described below |
| +0x10 | u32 | P: byte offset to GIF packet; **0x80 in every cache entry** |
| +0x14–0x3f | 44 bytes | Zero on disc, runtime state after loading; not pixels |
| +0x40–0x7f | 64 bytes | Zero padding in the audited cache |
| +P | Q * 16 bytes | Contiguous GIF packet |
| after packet | remaining sector bytes | Sector padding; do not decode or use as extra texels |

TEX0 fragment fields (O / high, `0x16b998`, corroborated by all entries):
bits 0–5 TBW (units of 64 texels) = 2; bits 6–11 PSM = 0x13 (PSMT8);
bits 12–15 TW and 16–19 TH are allocated log2 dimensions; bit 20 TCC = 1;
bits 21–22 TFX = 0. Allocated dimensions are not the output crop.

Flag 0x0004 selects the 256-colour upload form in the DMA handler.
The meanings of 0x0040, 0x0800 and 0x1000 are **U** beyond existing texture
research and the observed profiles here. Do not make field weaving depend on
one of those bits: this contract identifies the picture-cache draw path.

Observed counts: 0x0044 = 5,852; 0x0844 = 5,464; 0x1044 = 102;
0x1844 = 93. Width 7–95, height 22–174 (even), allocation 2–7 sectors,
Q 129–781; 2–10 runtime DMA blocks per picture.

## GIF and pixel payload

**O / high:** full-cache scan; register interpretation follows `0x16b998` and
the [GS texture contract](model-texture.md). Each GIF tag is two u64 words:
NLOOP = low word bits 0–14, FLG = bits 58–59, NREG = bits 60–63 (zero means 16).
Packed tags use FLG=0, NREG=1, descriptor 0xE (A+D). Each following qword is
`u64 value; u64 GS_register_id`. IMAGE tags use FLG=2; NLOOP counts data qwords.
Do not mistake IMAGE bytes for another register list. EOP does not replace Q
as the serialized buffer bound.

| File-relative offset | Content |
|---|---|
| 0x080 | Packed tag, four A+D writes |
| 0x090, 0x0a0, 0x0b0, 0x0c0 | BITBLTBUF 0x50, TRXPOS 0x51, TRXREG 0x52, TRXDIR 0x53 |
| 0x0d0 | IMAGE tag, 64 qwords |
| 0x0e0–0x4df | 1,024 palette bytes: 16 x 16 RGBA32 upload |
| 0x4e0 | Packed tag, one A+D write |
| 0x4f0 | Image BITBLTBUF |
| 0x500 | Packed tag, three A+D writes |
| 0x510, 0x520, 0x530 | Image TRXREG, TRXPOS, TRXDIR |
| 0x540 | Image IMAGE tag |
| 0x550 onward | `upload_width * upload_height * 4` image upload bytes |
| optionally after image | Packed tag + eight LABEL 0x62 writes (195 entries); no additional pixels |

The ordinary 11,316 entries end after image data. A native decoder should walk
tags with bounds checks, rather than assume all packets end at the same offset.
Q = 77 + image-byte-count / 16, plus 9 when the LABEL tail is present.

Both transfers are host-to-local (TRXDIR value 0), PSMCT32 (DPSM=0), DBW=1,
destination X=Y=0. BITBLTBUF DBW is bits 48–53, DPSM bits 56–61;
TRXPOS DX bits 32–42, DY bits 48–58; TRXREG width bits 0–11, height bits 32–43.
Destination bases are relocation placeholders: distinguish the palette and image
by successive BITBLTBUF writes, not by equal on-disc destination addresses.

**O / high:** the image is an upload rectangle of **32-bit words**, not the
logical icon rectangle. There are 128 distinct upload shape pairs. The palette
is always 16 x 16; image dimensions vary and include padding. Never infer the
image transfer size from W/H or TW/TH.

## Decode into native RGBA

The GS address rules below are **I / high** for this cache: they apply the
established GS mapping in `tools/play-net/disctex.py` and
[model-texture.md](model-texture.md) to the observed uploads. The reference's
synthetic tests cover address bijections, page boundaries and selected byte
landmarks. All cache entries pass coverage checks; no independent colour oracle
or rendered-game comparison was executed in this pass.

1. Upload each 4-byte word to the address for PSMCT32 `(x,y,DBW=1)`.
   Pages are 64 x 32 pixels / 8,192 bytes. Within a page, use 8 x 8 blocks
   in GS block order, then column word order. `gs32_word` in the reference
   returns a **word** address, so multiply by four before copying bytes.
2. Read that memory using PSMT8 addressing `(x,stored_y,TBW=2)`.
   Pages are 128 x 64 indices / 8,192 bytes; blocks are 16 x 16 indices.
   `gs8_byte` returns a **byte** address. Copying upload bytes straight into
   a row-major image skips this format reinterpretation and corrupts the icon.
3. For output `(x,y)`, use `stored_y = y//2 + (H//2 if y is odd else 0)`.
   Use logical H, not the power-of-two height and not twice the transfer height.
   This progressive weave follows the addressed sprite field path above.
4. For index i, palette slot is
   `(i & ~0x18) | ((i & 8) << 1) | ((i & 16) >> 1)`.
   Swap index bits 3 and 4, then read four consecutive palette bytes.
5. Return exactly W x H RGBA bytes, preserving RGB under zero alpha.
   Keep original GS alpha in the contract output (0x80 is opaque).
   `display_rgba` optionally maps alpha to `min(255, 2*a)` for conventional
   presentation. That conversion is an explicit native presentation policy,
   not proof of the original modulate/blend equation.

The block/word maps and page formulas are given as authored code in
`gs32_word` / `gs8_byte`, so implementers need not reconstruct a swizzle from
sample artwork. Track which GS words were supplied and reject a logical pixel
that reads an unwritten word. Zero-filling a missing upload conceals a decoder
error. The reference rejects unsupported profiles, odd logical heights, invalid
packet ranges, wrong transfer formats, and unsupplied visible pixels.

## Runtime chain is a different representation

**O / high, `0x100504–0x100654`:** each cache block has a 16-byte DMA header
and at most 79 data qwords. Non-final tag word = `0x20000000 | count` (NEXT);
final tag word = `0x60000000 | count` (RET, **not END**). +4 links the next
block; payload starts at +0x10. Blocks occupy 0x500 bytes. The copied texture's
+0x14 points to the first block. This chain is not present in PICCACHE.DAT.
`dma_chunks` models tag kinds and exact payload partitioning without inventing
runtime addresses. This is useful to compare an in-memory cache with serialized
input; a native asset decoder does not need the chain allocator.

## Validation and remaining boundary

**Executed / high:** `python3 local/audit_icons.py` scanned all entries and
validated dimensions, bounds, tag families and transfer shapes.
`nice -n 10 python3 local/verify_contracts.py` decoded all 11,511 entries
(41.17 s for that portion), with no missing logical pixels. These private
helpers and logs remain under this worktree's ignored `local/`.
`tools/test_ref_inventory_icons.py` uses invented headers, palettes and pixel
patterns only; it requires no game input.

**U:** semantic purpose of unused flag bits; native inventory integration,
all-item association/coverage in the other worktree, and rendered alpha/colour
parity. A colour comparison against the existing NumPy decoder was attempted
but that interpreter has no NumPy; it is not counted as a successful check.
The native item-upscale agent can now implement the serialized cache profile
and feed decoded RGBA into its existing upscaler. Pixel fidelity in the actual
inventory still needs an original/reference image comparison.
