# UI text: batches, colour, button glyphs, wrapping and fitting

SLUS-20973 v2.00; research 2026-10-17, branch `t3/research-ui` (round 2).
Builds on the [font file contract](ui-fonts.md). Reference:
[ref_ui_text.py](../../tools/ref_ui_text.py), synthetic tests
[test_ref_ui_text.py](../../tools/test_ref_ui_text.py). No glyph art, glyph
tables, game strings or raw code are included here.

**Status:** the text module `0x17ffb0–0x181d30` is documented: batch state,
GS state, colour and icon tint, the glyph loop, both measuring functions,
the two wrapping drawers, centring wrappers, text clipping and the two
truncation helpers. **Executed:** 5,320 constructed-state calls of the
original functions matched the reference (section "Validation"). Still
**partial**: caller-side styling (which colours, pulses and fades each screen
uses), odd-y field placement and the frame-mode (`0x44fdb4`) raster.
No game was run and no original screen was compared.

O = observed in the addressed code, I = inferred, U = unknown.

## 1. Batch life cycle

| Function | Arguments | Contract | Level |
|---|---|---|---|
| `text_begin` `0x1800b8` | (font, layer, colour, iconAlpha) | Stores font `0x7d35bc`, **sort layer** `0x7d35d8`, colour `0x7d35b8`, icon alpha `0x44e020`; resets the character budget `0x7d35d0` to 100,000 and the clip flag `0x7d35d4` | O / high |
| `text_setColor` `0x1802e0` | (colour, iconAlpha, temporary) | Closes the current sprite run and emits RGBAQ = colour. Unless temporary, also stores colour, `0x44e024` and `0x44e020` = iconAlpha | O / high |
| `text_setClip` `0x1803e0` | (left, top, right, bottom) | Section 6 | O / high |
| `text_setCharBudget` `0x181a78` | (n) | n = -1 means 100,000; only callers are the dialog task (`0x2304f4`, `0x230754`, `0x2307c4`) | O / high |
| `text_end` `0x180500` | () | Restores the clip if one was set, closes the packet and submits it whole with `gfx_addSortedPacket` `0x16b7f0`, flag 1, at the stored layer; skipped while `g_loadscreenActive` `0x506094` is set | O / high |

Of 118 `text_begin` call sites, the layer argument is a constant 5, 6 or 7 at
95 (others pass 1, 3, 4 or a computed value); iconAlpha is -1 at 107 (others
pass a computed fade).
Of 131 `text_setColor` calls, 116 pass iconAlpha -1 and 127 pass
temporary = 0 (simple tally of the argument set-up before each call, I / high).

**O / high, GS state written by `text_begin`:** TEX1 = 1 (LCM set, nearest
magnification and minification: **no bilinear filtering**); ALPHA = 0x44
(`(Cs-Cd)*As/128 + Cd`); PRIM = 0x156 (sprite, textured, blended, UV
addressing); TEST = 0x3001d (alpha test **greater than 1**, failing pixels not
written; depth test always). The font texture's TEX0 fragment (in each of the
four audited fonts) is PSMT8, TCC = 1, TFX = 0 (modulate). So a glyph pixel
is texel x colour / 128 per channel, alpha likewise, and texels with
modulated alpha <= 1 are discarded (I / high from the register meanings).

**O / high, order:** each batch is one packet, so glyphs within a batch draw
in string order. Batches and sprites share the prepend queue of
[hud-layout.md](../hud-layout.md): a batch submitted later in a layer draws
**earlier**. A native painter must keep a batch together and reverse batches
with sprites per layer.

**O / high:** `text_drawWideImpl` `0x180f80` draws nothing unless at least
6,000 packet units are free (sprites need 3,000). In ordinary play
`0x44fdb4` is zero (its initial value) and the glyph loop runs once. With it
set, the run is emitted twice under GS SCANMSK 2 and then 3
(`0x181028–0x181248`), then SCANMSK is cleared; emitter `0x180878` selects
one stored field per pass (O / medium).

## 2. No in-band markup; colour is per run

**O / high:** the glyph loop `0x1809c0` and both measures treat only 0x0a
specially. There are no escape or colour codes inside strings.
`text_lookup` `0x173c84` strips double quotes from the **key**, hashes it and
returns the stored wide string unchanged; a miss returns `NF:` plus up to 16
key bytes from a 16-slot ring. ASCII-to-wide `0x19e884` zero-extends bytes;
wide-to-ASCII `0x19e8b4` keeps the low byte.

**O / high:** the text module never reads `g_uiPulse` `0x506060` or
`g_uiFadeIn` `0x506070`. Pulses, fades and per-row colours are computed by
callers and passed to `text_begin` / `text_setColor`. Example: the HUD name
batch passes layer 6 and a computed colour (`0x1da3a4–0x1da3c8`). Recording
each screen's colours is caller work outside this contract (**U** per screen).
No shadow or outline pass exists inside the module; whether callers draw
offset copies is **U** (settle by listing callers that draw the same string
twice).

### Button glyphs and their tint

**O / high:** glyph **indices** 0x5b..0x68 take a separate colour path
(`0x180ca0–0x180cfc`). In all four audited fonts these indices are the
character codes **0x7b..0x88** (map and glyph table agree).
`pad_buttonMaskToGlyph` `0x1eacb8` turns libpad button bits into
0x7b..0x86. By the libpad bit assignments, those are circle 0x7b,
triangle 0x7c, square 0x7d, cross 0x7e, left 0x7f, right 0x80, up 0x81,
down 0x82, L1 0x83, L2 0x84, R1 0x85, R2 0x86 (O / high for the
mapping; I / high for the button names). 0x87/0x88 have glyphs but that
function never produces them; [native-gameart.md](../issues/native-gameart.md)
names them R3/L3 (I / medium).

**O / high:** before such a glyph the loop calls `text_setColor`
temporarily with `(alpha << 24) | 0x606060`, where alpha is the colour's top
byte if `0x44e020` = -1, otherwise **its low byte**. Button art therefore draws
at 0x60/0x80 = 75 % of its texel colour whatever the text colour. The first
ordinary glyph after the icons, or the end of the run, restores the stored
colour non-temporarily with alpha `0x44e024`, which also copies `0x44e024`
into `0x44e020` (`0x180d00–0x180d24`, `0x180f30–0x180f4c`). That is a real
state change: a batch-specific iconAlpha from `text_begin` lasts only until the
first icon run ends. `TextState` models it.

## 3. Glyph lookup and the glyph loop

**O / high** (`0x180b18–0x180ba4`; identical in `font_measureWide`
`0x180710–0x18079c`):

- 0x0a gives the sentinel index 0x7ff: no draw and no advance.
- A code below 256 uses its signed map entry if >= 0 (0 included). A negative
  entry uses the **value** of map entry 45 (FNT +0x6e) read as u16.
- A higher code takes the first glyph whose u16 code matches; no match gives 0.
- Index <= 0 advances by glyph 0's advance and draws nothing.

**O / high, `0x1809c0` (x, y, wstr, count):** nothing is drawn when
`(y+100)` is not below 901 unsigned (y outside -100..800) or count = 0. The
run stops at NUL or after count units. For each drawn glyph, the destination is
`(pen, y + yOffset, u1-u0, v1-v0)` and the source is
`(u0, v0, u1-u0, v1-v0)` in woven logical texels, as in ui-fonts.md.
Pen arithmetic is the same in the interlaced path (1/32-pixel units,
`x*32 + 0x5800`) and the progressive path (1/16, `x*16 + 0x6c00`):

- advance: + glyph advance pixels;
- kerning (first matching row, as in ui-fonts.md): **+ adjustment / 2 pixels**
  (`0x180bd8`, `0x180c80`). Glyphs can sit on half pixels.
- the previous index becomes the current index, also for index 0 and for the
  newline sentinel (so a newline breaks kerning in the draw).

`glyph_run` returns pen positions in half pixels.

**O / medium, field placement (`0x180a24–0x180ac4`):** in the interlaced path
an odd y moves the GS y by +1 or -1 line according to `gfx_displayField`
bit 0 and selects the other stored field; the V base is 0, half the used
texture height, or either minus 4 sixteenths. Even-y placement with field bit 1
was executed (section "Validation"). Odd-y and field-0 raster parity are
**not** modelled; a woven progressive font texture is the intended native
equivalent (I / medium).

## 4. Measuring

`font_measureWide` `0x1806f0` (**O / high**) matches `font_measureAscii`
`0x17ffb0` except: wide lookup rules above, newline adds nothing and
**does not** change the previous index, and the lookup fallback for negative
map entries. Kerning in both measures is adjustment x16 when `0x44fdd4`
(interlace, initially 1) is set, else x8, in 1/16 units, result `>> 4`.

**O / high, consequence:** with interlace on, a measure counts kerning
twice as strongly as the draw. Measures and draws agree only for fonts or
pairs without kerning. The two `gamefont*` fonts have only the terminal
kerning row; the two PvP fonts have 27 real rows, so centring and wrapping of
PvP text differ from the drawn width by up to half the summed adjustments.
Preserve the measure, not a "corrected" width, to reproduce placement.

**O / high:** `text_drawAsciiCentered` `0x181af8` measures with the ASCII rule
(negative map entry = glyph 0 advance) but draws through the wide loop (map
entry 45's glyph). The audited fonts have 112–114 negative map entries.
`centered_x_ascii` and `centered_x_wide` keep that difference.

## 5. Alignment, wrapping and line height

| Function | Contract (O / high) |
|---|---|
| `text_drawAscii` `0x181aa0` | Converts to wide on a 2 KiB stack buffer, draws at x (left) |
| `text_drawWide` `0x181c10` | Thunk to the wide draw (left) |
| `text_drawAsciiCentered` `0x181af8`, also `0x181b78` | x - (ASCII width >> 1) |
| `text_drawWideCentered` `0x181ca0` | x - (wide width >> 1) |
| `text_drawWrapped` `0x181280` | (x, y, wstr, width, top, bottom, lineHeight) left, word split, budget |
| `text_drawWrappedCentered` `0x181530` | Same arguments; centred lines; no split, no budget |
| `0x181780` | ASCII copy of the centred wrapper; no callers found |

No right-aligned wrapper exists in the module (callers compute their own x).
`>> 1` is an arithmetic shift.

**Line height is a caller argument**, not a font field. The constants passed
to the two wrappers are 17 and 21 at most sites, also 14, 15, 16, 18, 19, 20 and
31 (argument tally, I / high). The FNT +2 word is not read anywhere in
`0x17ffb0–0x181d30` (O / high). Its meaning remains **U**.

### Wrapping algorithm (both drawers)

**O / high**, `0x1812e0–0x181464` and `0x181590–0x1816dc`:

1. A **word** starts at the cursor and ends before NUL or 0x0a, or **after**
   one space (0x20). Only 0x20 is a break character. With `g_language`
   `0x44fddc` = 5, every single unit is a word (per-character breaking). The
   menu at `0x3235a8` lists five languages, so which language uses 5 is **U**.
2. Left drawer only: while scanning, before each further unit it measures the
   word so far. When that is not below width, the word is cut one unit
   earlier. The final unit before a space is never checked, so words can still
   exceed width by one glyph.
3. Word width w = `font_measureWide` of the word, including its trailing space.
   If `lineWidth + w < width`, the word joins the line. Otherwise the pending
   line `[lineStart, cursor)` is flushed, y += lineHeight, and the word starts
   a new line with lineWidth = w. If the first word is already too wide, an
   **empty** line is flushed first (a blank line, count 0).
4. If the word ended at 0x0a, lineWidth += 1,000,000 (the next word forces a
   break) and the newline unit is skipped. It stays inside the flushed run
   and the glyph loop ignores it.
5. At NUL a non-empty pending line is flushed and y += lineHeight. Return value
   = final y - initial y (lines x lineHeight).

**Flush visibility:** a line is drawn only if `top < y < bottom` for its
**origin y** (strict, whole line, no pixel clipping). Hidden lines still
advance y and still count toward the left drawer's budget.

**Left drawer only, typewriter budget:** a drawn run has
`min(units, budget - used)` units; `used` grows by that amount for every
flushed line; once `used >= budget`, later lines are not drawn. The total shown
goes to `0x44e028` (reset to 0 at entry, written only when a line is drawn).
The dialog task reads it at `0x230598`.

**Centred drawer:** x for each line is `x - (measure(line) >> 1)`. The
measured line includes the trailing space before the break, so wrapped centred
lines sit half a space advance to the **left**.

**Hazards (O):** if one unit is not narrower than width, the left drawer makes
no progress and never returns. A width <= 0 makes its first cut point before
the cursor. The reference raises ValueError in both cases.

## 6. Text clipping

**O / high**, `text_setClip` `0x1803e0`: left/top are clamped to >= 0, right to
<= 640, bottom to <= 447. It writes GS SCISSOR as X `2*left .. 2*right-1` and
Y `top .. bottom` (both inclusive). In logical pixels: x half-open
`[left, right)`, y **inclusive** of bottom. Unlike the sprite scissor of
`0x17baac`, there is no field-parity adjustment. A right edge <= 0 makes a
negative X field that the code does not mask (it corrupts the packed
register). `text_end` restores `(0, [0x44fd74], 640, [0x44fd78])`, initially
`(0, 0, 640, 447)`, only when the batch set a clip. Glyphs are never
cropped by the CPU. `text_scissor` returns both forms.

## 7. Fitting into a width

**O / high**, `ui_fitText` `0x1bdf60` (font, slot, text, width): copies the
text into a 32-byte slot `0x4f3ec8 + slot*32` with an unbounded strcpy.

- Font given: drop the last byte while `width < font_measureAscii(text)`.
  Pixel mode, with **no room reserved** for the ellipsis.
- Font NULL: width is a **character count**. If longer, drop bytes until
  `len + 3 <= width`.
- If anything was dropped, append three ASCII periods. A pixel-mode result can
  be wider than width by the periods' width.

`text_truncateToWidth` `0x1ec1c0` (src, font, width, dest) applies the same
pixel rule through a 256-byte stack buffer (no callers found). `fit_ascii`
models both, with a guard against an emptied string. The original loops or
writes before the buffer if the string empties while still too wide.

## 8. Native implementation checklist

1. Use the FNT glyph rectangles from the woven texture, nearest sampling,
   modulate by colour/128, alpha test `> 1`, standard alpha blend.
2. Keep pen positions in half pixels. Use `measure_wide`, not the drawn
   extent, for centring and wrapping.
3. Keep each batch as one draw group in submission-reversed layer order.
4. Draw glyph codes 0x7b..0x88 with tint 0x606060 and the icon-alpha rule.
5. Implement wrapping by the five steps above, with the caller's line height
   and the origin-y visibility test; keep the typewriter budget for dialog.
6. Map clip rectangles with `text_scissor`.

## Validation

**Executed** (`local/r2-text/verify_text.py`, log
`local/r2-text/verify-text.log`, private): the four private fonts loaded into
`tools/ee_emu.py`, randomized constructed strings (invented letters, spaces,
button codes, newline, unmapped bytes, codes above 255) and both interlace
values:

| Original function | Cases | Compared |
|---|---|---|
| `font_measureWide` `0x1806f0` | 2,480 | return value, counts 0/1/3/len/unbounded |
| glyph loop `0x1809c0` (field bit 1, even y, `text_setColor` hooked) | 400 | decoded UV/XYZ2 of every sprite, colour-call sequence, final `0x44e020` |
| `text_drawWrapped` `0x181280` | 560 + 160 long words | runs (x, y, start, count), height, `0x44e028`; budgets 0/7/33/100,000, clip bands, language 0/5 |
| `text_drawWrappedCentered` `0x181530` | 560 + 160 long words | runs incl. centred x, height |
| `text_drawWideCentered` `0x181ca0` | 240 | x passed to the draw |
| `ui_fitText` `0x1bdf60` (pixel and character mode), `text_truncateToWidth` `0x1ec1c0` | 720 | resulting bytes |
| `text_setClip` `0x1803e0` | 40 | SCISSOR register value (right >= 1) |

All 5,320 matched. This is function-level execution on constructed state,
not a running game or a raster comparison. `tools/test_ref_ui_text.py` has 17
tests using one invented font; no private data is needed.

## Unknown

- FNT +2 meaning (read by none of the text functions).
- Language value 5's identity; any non-NTSC string conventions.
- Per-screen colours, pulses, fades and shadows (caller side).
- Odd-y / field-0 placement and frame mode (`0x44fdb4`) raster detail, and
  pixel parity of nearest-sampled glyphs on a native target. Settle with an
  original frame capture compared against a native render, glyph by glyph.
