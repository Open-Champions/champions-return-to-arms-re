# UI font file and glyph layout contract

SLUS-20973 v2.00; research 2026-10-17, branch `t3/research-ui` from `a2b145b`.
Reference: `Font` / `parse_font` in [ref_ui_layout.py](../../tools/ref_ui_layout.py).
Scope: unrelocated FNT data, glyph rectangles, ordinary ASCII width and the
base HUD's selected font. Colour, button glyphs, measuring of wide strings,
wrapping, alignment, clipping and truncation are in [ui-text.md](ui-text.md)
(round 2, 2026-10-17).
No font art, glyph table contents or game text are included here.

## Addressed file layout

All fields are little-endian. **Observed / high confidence:** relocation
`0x181a20–0x181a50` adds the FNT base independently to +8, +0x0c and +0x10,
then calls texture relocation `0x179e10` on the embedded texture. ASCII width
`0x17ffb0–0x1800b4`, wide text `0x180b2c–0x180bc8`, and glyph draw
`0x180be8–0x180c28` establish the field widths, strides and signedness below.
Unknown/inferred header fields are marked separately.

| FNT offset | Type | Meaning / evidence |
|---|---|---|
| +0x00 | s16, positive in valid files | Glyph count; signed load for wide-codepoint search at `0x180b60` path |
| +0x02 | u16 retained word | **Unknown** semantic meaning; 8 in the four audited fonts. Not read by any text function in `0x17ffb0–0x181d30`; a 2026-10-20 scan found no reader of this word (the offset-2 loads in that neighbourhood are glyph fields or a TEX header). Line height is a caller argument ([ui-text.md](ui-text.md) section 5) |
| +0x04 | u32 | **Inferred / high:** kerning-record count including terminal row; agrees with all four table spans. Not needed by the observed unbounded width loop |
| +0x08 | u32 | Glyph table offset from FNT base; pointer after relocation |
| +0x0c | u32 | Kerning table offset from FNT base; pointer after relocation |
| +0x10 | u32 | Embedded TEX header offset from FNT base; pointer after relocation |
| +0x14 | s16[256], 0x200 bytes | Byte-codepoint to glyph-index map; ASCII `0x17ffdc–0x17ffec` |
| after +0x214 | variable | Tables and embedded texture, located by offsets rather than assumed alignment |

**Observed / high:** each glyph is 16 bytes, with fields:

| Glyph offset | Type | Meaning |
|---|---|---|
| +0 | u16 | Character code, compared by wide lookup |
| +2 | s16 | u0 |
| +4 | s16 | u1 |
| +6 | s16 | v0 |
| +8 | s16 | v1 |
| +0x0a | s16 | y offset relative to the text API's y origin |
| +0x0c | s16 | Horizontal advance |
| +0x0e | s16 | First kerning-record index; negative means no kerning |

**Observed / high**, `0x180010–0x18007c` and `0x180c2c–0x180c9c`:
kerning records are six bytes: `u16 previous_glyph_index`,
`u16 current_glyph_index`, `s16 adjustment`. These are **glyph indices**, not
Unicode character values. Starting at the glyph's kerning index, scan while
the current index matches. Apply the first row whose previous index matches,
then stop. Terminal/current-index mismatch ends a group. The original loop
does not bounds-check this; a native reader should.

The embedded texture is a normal TEX with its own used dimensions and packet
offset. **Its packet offset is relative to the embedded TEX, not to the FNT.**
Evidence: FNT fixup `0x181a4c`, texture fixup `0x179e20–0x179e40`.
Use the existing [texture format contract](model-texture.md), not the narrow
inventory-only decoder for arbitrary font textures.

## Resource pairing and private structural audit

**Observed / high:** these are table offsets **relative to each FNT**;
the FNT-header column is an offset within its containing private lump.
The glyph texture is embedded; there is no missing separately named PNG/TEX
to invent. Read the LMP directory to locate entries; offsets below identify
the exact audited evidence, not a replacement for directory parsing.

| Lump / entry | FNT header | Glyph count | Kern count | Glyph table | Kern table | TEX header | Used texture W x H |
|---|---|---|---|---|---|---|---|
| FONT.LMP / gamefontmed.fnt | 0x80 | 147 | 1 | 0x214 | 0xb44 | 0xb4c | 256 x 178 |
| FONT.LMP / gamefontsmall.fnt | 0xc580 | 147 | 1 | 0x214 | 0xb44 | 0xb4c | 256 x 130 |
| PVPFONT.LMP / pvpfontbig.fnt | 0x80 | 152 | 28 | 0x214 | 0xb94 | 0xc3c | 256 x 478 |
| PVPFONT.LMP / pvpfontsmall.fnt | 0x1f200 | 149 | 28 | 0x214 | 0xb64 | 0xc0c | 256 x 228 |

**Observed / high:** startup `0x323f64–0x323f94` loads gamefontmed and
gamefontsmall; the small font pointer is `0x4f7104` (register setup at
`0x323e14`, store at `0x323f94`). `hud_drawPlayerStatus` reads that pointer
and selects layer 6 at `0x1da3a4–0x1da3c8` and `0x1da5d8–0x1da5f0`.
The medium font is also installed as the default at `0x323fa4`.
Screen-by-screen PvP font selection is **unknown** in this contract.

## Logical glyph rectangles and width

**Observed / high**, `0x180bf4–0x180c28`, `0x180dc8–0x180e64`:
u/v bounds and y offset are integer **logical texels**, not normalized UVs
and not pre-scaled 1/16 units. U is shifted by four; in the interlaced path V
and y offset are shifted by three, then the destination height is doubled.
The field base uses half the embedded texture's **used** height
(`0x180a60–0x180abc`). Therefore, after weaving the embedded texture to
progressive rows, a glyph's half-open source rectangle is
`(u0,v0,u1-u0,v1-v0)` and its destination is
`(pen_x, text_y+y_offset, u1-u0, v1-v0)`.
`Font.glyph_rects` returns those two rectangles. It does not claim text_y is
a typographic ascender baseline; no such metric has been identified.

**Observed / high:** normal field packet coordinates add 4 to 1/16-unit UVs
(quarter-texel bias), and use the selected field's V base. Progressive-mode
packet construction uses an 8-unit UV bias (`0x180e68–0x180ed4`). These are
raster sampling rules, not extra source-border widths. Do not add four or eight
whole texels to an atlas rectangle. The modern progressive rectangle above is
the authored interpretation of the field draw; exact edge sampling still needs
a rendered comparison.

**Observed / high**, width function `0x17ffb0`:

1. Start pen in 1/16 logical-pixel units at zero, previous glyph index -1.
2. Stop at NUL or the caller's byte count. This function does not perform
   newline wrapping or infer line spacing from header +2.
3. Read signed map[byte]. For an index <=0, add glyph 0 advance *16.
   This missing character still becomes the previous index.
4. For a positive index, apply matching kerning. Multiply adjustment by 16
   when `0x44fdd4 !=0`, otherwise by 8. Then add glyph advance *16.
5. Return arithmetic `pen >> 4`.

The shift for negative kerning must stay signed. Advances are not bitmap
widths. `Font.width_ascii` follows this algorithm and supports the byte-count
limit. Its bounded kerning scan is a native safety policy; the game trusts data.

**Observed / high:** centered ASCII wrapper `0x181af8–0x181b58` measures
first, subtracts `width >> 1` from supplied x, converts the string to wide
characters (`0x19e884`), then draws through `0x180f80`. The HUD's name and
level origins in [hud-layout.md](../hud-layout.md) are these center anchors.
Text clipping is batch GS scissor (`text_setClip` `0x1803e0`), not per-glyph
texture cropping. `text_begin` is `0x1800b8`, `text_end` is `0x180500`.

**Observed / high** (round 2), `0x180b2c–0x180ba4`: the wide drawing path
differs from byte width. A negative map entry for a code below 256 falls back
to the glyph index **stored in** map entry 45 (FNT +0x6e). Higher codes search
the glyph table's u16 codes. Newline uses sentinel index 0x7ff. Glyph indices
0x5b..0x68 are the controller button glyphs (codes 0x7b..0x88) drawn with a
neutral tint. In the draw, kerning moves the pen by adjustment/2 pixels in
both modes. Details and the executed comparison are in [ui-text.md](ui-text.md).

## Bounded reader and validation

**Authored policy:** `parse_font` accepts the observed ordered table layout,
requires a complete 0x214-byte prefix, positive signed-range glyph count,
nonoverlapping in-file tables and at least a 0x40-byte embedded TEX header.
It rejects out-of-range mapped glyph and kerning-start indices. It preserves
the unknown +2 word and the embedded texture bytes without trying to relocate
them. This is not a claim that the original loader validates hostile files.

**Executed:** all four private fonts parsed. `local/verify_contracts.py`
compared **128** ASCII width cases against `0x17ffb0` in `ee_emu`: four fonts,
both values of the interlace boolean, ordinary/missing/extended byte strings,
embedded NUL, and zero/short/full/long count limits. Private results are in
`local/contract-verification.log`. These are function-level executions, not
gameplay or a font-raster test. Synthetic unittests use three invented glyphs
and invented negative kerning; they require no private data.

**Unknown:** semantic meaning of +2; every screen's selected font and
colours; pixel-exact field placement for odd y and the frame-mode raster in a
native renderer. Wrapping, line height (a caller argument), colour/button
glyphs, non-ASCII lookup and clipping are now in [ui-text.md](ui-text.md).
Comparing original text images is still required; substituting a system font
would not validate this contract.
