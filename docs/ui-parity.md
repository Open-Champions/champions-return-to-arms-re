# Comparing a native UI renderer with the original

SLUS-20973 v2.00, researched 2026-10-17 on `t3/research-ui` (round 2).
Companions: [reference compositor](../tools/ref_ui_composite.py),
[synthetic tests](../tools/test_ref_ui_composite.py),
[HUD and frame contracts](hud-layout.md), [fonts](formats/ui-fonts.md),
[render pipeline sections 6–8](spec/render-pipeline.md).

**Status: method documented, reference compositor and comparators written and
unit-tested on invented data. No comparison of a native renderer with the
original was run in this pass** (no game, emulator or application was started:
a live session owned the machine's game process). Every capture tool named
below exists; the procedures that combine them are proposed.

O = observed at the address given, I = inferred, U = unknown.

## 1. What the original's 2D path sets

| Draw | `TEX1_1` | `ALPHA_1` | `PRIM` | `TEST_1` | Evidence |
|---|---|---|---|---|---|
| Sprite (`ui_drawSpriteImpl` 0x17b590, clipped 0x17b8b0) | 1, point sampled | 0x44 | 0x156: sprite, textured, blended, UV in texels | 0x3001d | **O** template built at 0x17a49c–0x17a4f8 into 0x7d3140, which 0x17b658 and 0x17b97c reference; colour 0x80808080 at 0x17a484 |
| Text batch (`text_begin` 0x1800b8 … `text_end` 0x180500) | 1 | 0x44 | 0x156 | 0x3001d | **O** 0x1801ac–0x1801f8 |
| Flat rectangle (`ui_drawRect` 0x17bd30) | — | 0x44 | 0x46: sprite, untextured, blended | 0x31001 | **O** 0x17bdd0–0x17be1c; colour from the argument as RGBAQ |

Decoded (**I / high**, the GS register definitions applied to those values):

- `ALPHA` 0x44 is `((Cs − Cd) × As >> 7) + Cd`, As the source alpha with
  0x80 = 1.0. `COLCLAMP` is 1 per frame (0x19c86c, O in render-pipeline.md 8),
  so results clamp to 0..255. Alpha itself is not blended.
- `TEST` 0x3001d: alpha test **pass when alpha > 1**, failing pixels keep the
  frame buffer; depth test "always". `TEST` 0x31001: alpha test "never" with
  fail mode "frame buffer only", so a rectangle always blends its colour.
- Texture function and alpha use come from the texture header's `TEX0`
  (`gfx_dmaHandler` 0x16b998); interface and font textures carry TFX 0
  (modulate) and TCC 1 ([inventory-icons.md](formats/inventory-icons.md),
  [ui-fonts.md](formats/ui-fonts.md)). Modulate is `(Ct × Cf) >> 7` per
  channel, alpha included, with Cf the RGBAQ tint word
  (R bits 0–7, G 8–15, B 16–23, A 24–31; 0x80 = 1.0).
- Coordinates: **O** 0x17be38–0x17be74, interlaced path: GS X = 32x + 0x5800,
  Y = 16y + 0x7200 (1/16 pixel), i.e. X = 2x + 1408, Y = y + 1824; otherwise
  X = 16x + 0x6c00. A rectangle is two corners; a GS sprite covers
  `[x0, x1) × [y0, y1)` (I / high).
- A second packet header at 0x17a6a0–0x17a720 (function 0x17a5a0) sets
  bilinear `TEX1` 0x61, `ALPHA` 0x2a (source only) and `TEST` 0x3001c (no
  alpha test). Its caller is **U** here; it is not the sprite path.
- Order: layers 0..7, every 2D packet prepended inside its layer (0x16b7f0,
  O; [hud-layout.md](hud-layout.md)). A text begin/end pair is **one packet**
  (render-pipeline.md 7, O), so glyphs inside a batch keep their own order
  while batches and sprites reverse.
- Both drawers skip their work below 3,000 free display-list units
  (0x17bd6c for rectangles, O). A comparison scene must not be near that limit.

## 2. What happens to the picture after it is drawn

These are the reasons the original's pixels differ from a straightforward
composite of the same draws. All buffer facts are **O** in render-pipeline.md
section 8 (0x19c8fc, 0x19bf04, 0x19cbb0); their consequences are **I**.

1. **16-bit draw buffer with dither** (`PSMCT16`, `DTHE` 1). Each channel keeps
   5 bits: up to 7 lost per channel, plus the dither offset. The matrix is the
   GS register `DIMX` (id `0x44`). The game builds `0x3131757531317575` at
   `0x19c46c` (init), `0x17b210` (sprite path), `0x177fcc` (model option bit
   `0x02`) and `0x190664`, and stores it as that register's data. Low nibble
   first, the signed 3-bit entries are the rows (−3, −1, −3, −1), (+1, +3, +1,
   +3), repeated. **O.** Per frame, `gfx_emitFrameSetup` `0x19c9a4` writes
   `DTHE` (`0x45`) = 1 and `COLCLAMP` (`0x46`) = 1 and does not rewrite `DIMX`.
   `dither5` in the reference is the inferred clamp-then-shift to 5 bits; it is
   not applied by `composite()`. Alpha is one bit in the buffer: compare RGB only.
2. **1280 × 448 buffer.** Logical x is doubled; the present pass box-filters
   2 × 2 into the display. Two GS columns per logical pixel make the horizontal
   filter neutral for 2D art (I).
3. **Fields.** In the normal mode an interface sprite draws only the half of
   its stacked-field texture that matches the current display field
   (`ui_emitSpriteQuad` 0x17ab50, O), stretched over the full height; in the
   half-rate mode (`g_displayRateMode` 0x44fd44, `gfx_setDisplayRateMode`
   0x19dd48) both halves are drawn under `SCANMSK` (O, symbols/fmt-model.tsv).
   One capture in the normal mode is therefore **one field of the art, line
   doubled**, not the woven picture. Which screen rows take which field also
   depends on the sprite's top row parity (the recompiled renderer models this
   as `field_shift`, tools/recomp/render/gs.cpp:1688).
4. **Present colour.** `gfx_present` `0x19cbb0` multiplies each channel by
   `2 × v × (0.8 × brightness + 0.2)` (`0x19ce3c–0x19cef4`, O). The double is an
   add of the product with itself; the result is truncated toward zero and
   clamped to 0..255. Brightness is the float at `0x44fd80`. The reset path
   `0x1e6260` stores 0.5 when its argument is −1, which makes the gain 0.6 and
   a channel of 128 into 153. **Executed** for (128, 0, 255) at that
   brightness. v is the word at `0x44fd8c` / `0x44fd90` / `0x44fd94` when
   `gfx_present`'s third argument is 0, and 128 otherwise (`0x19cc4c`). Those
   three words then step toward 128 by 4, snapping across 124..132
   (`0x19cf0c–0x19cf94`). The packed word is R, G, B in bits 0, 8, 16. The
   pass may also blend with the last displayed image (`gfx_setScreenDarken`).
   The Play! notes measured a clear colour shown ×0x99/0x80
   (tools/play-net/README.md, "Along the top of the menu screens"). A capture
   taken after present is **not** the draw buffer. 0x99/0x80 = 153/128, which
   is the 0.5-brightness result above.
5. **Edges.** Line 0 and the outermost pixels are often not drawn by menus
   (tools/play-net/README.md, same row): a television hides them. Mask them.

## 3. Capture points that exist today

| Side | Tool | What it gives | Where |
|---|---|---|---|
| Original, function level | `tools/ee_emu.py` with stubbed draw sinks | API records (resource, x, y, clip, tint, layer) of one function on constructed state | round 1: `local/trace_hud_base.py`, `local/trace_frames.py` (private); records match `ref_ui_layout` |
| Original, GS level | Play! build control socket `drawlog FILE [frames [x0 y0 x1 y1]]` | every draw of a frame with its GS registers and texture; primitives inside a rectangle vertex by vertex | tools/play-net/ctl.py:19–80, tools/play-net/README.md (`drawlog`) |
| Original, picture | `shotfb` (640 × 448 × factor, as drawn), `shotview` (presented part), `burst NAME n` (consecutive pictures with clocks), `probe` | pictures; `displaypatch all 0`, `texreplace 0`, `upscale 0`, `edge 0` give the shipped look at factor 1 | tools/play-net/ctl.py:24–60 |
| Original, scripted | `tools/recomp/app/emushots.py` | runs the Play! build silent and offline, drives the same `.rig` script the native app gets, `app shot` → `shotfb` | tools/recomp/app/emushots.py:1–15 |
| Translation, GS model | `render::Gs` → `FrameList` of `DrawCmd` | per draw: scissor (exclusive x1/y1), texture id and size, `tfx`, `tcc`, alpha test, blend `(A−B)×C+D` fields and `fix`, `weave_half`, `made_by` (2 = sprite) | tools/recomp/render/backend.h:32–84; registers read at gs.cpp:1211–1219; blend at gs.cpp:1286–1291 |
| Translation, recorded stream | `recorder.h` writes the GIF stream; `rta_replay <stream> --png --at n --trace n --no-weave --interlace` replays it with no game | deterministic re-rendering of the same frames | tools/recomp/render/recorder.h:1–8, replay_main.cpp:1–8 |
| Translation, who drew it | `gfx_rt.cpp` scopes: `fn_001d9cd4`, `fn_001dc708`, `fn_001df720`, `fn_001e42e0`, `fn_001dd270` mark HUD (`M_EDGE`), `fn_001d93b0` / `fn_001d99f0` text (`M_TEXT`), inventory/menu 3D (`M_MENU3D`) | marks in the stream (`0xA5` words) that attribute packets to HUD functions | tools/recomp/app/gfx_rt.cpp:41, 293–310; hle.txt:18, 23 |
| Translation, picture | `app shot FILE.png` in a script; `--plain` (4:3, no multisampling, mip maps or pack); `--game-hud off`, `--game-hud-text off` | pictures at the drawn size | tools/recomp/app/app_main.cpp:31–51, 1340, 1531–1569 |

Existing private pictures (listed, not copied): under
`~/champions-re/local/recomp-out/app-test/` there are 113 PNG/BMP files,
including `shots/` (boot and level pictures, `cmp-fight.png`),
`emu-shots/` (4 emulator references), `s12/det/<name>/` (tick-keyed route
pictures with `sums.txt` MD5 lists, compared by `s12/detcmp.py`) and
`s13/hud-*-sheet.png` (HUD on/off sheets). `render/pic/` holds 3 replay
pictures. Those comparisons are exact-hash or eye checks between builds of the
translation; none is a UI raster comparison against `shotfb`.

**Not existing yet (proposed):** API-level logging inside the translation.
Adding `17b590`, `17b8b0`, `17bd30`, `1800b8`, `180500`, `1803e0`, `180f80`
to an HLE list and wrapping them the way gfx_rt.cpp:294 wraps
`hud_drawPlayerStatus` would log exactly the records `ref_ui_layout` emits,
for whole frames of the real game rather than single functions in `ee_emu`.
Resource names come from the texture pointer via the lump directory.

## 4. Tier A: draw-record parity

Compare **what is drawn**, before any rasterisation. Exact equality is the
criterion; there is no tolerance at this tier.

1. Capture the original's records for a frame: ee_emu traces (one function,
   constructed state) or, once added, the translation's API log; GS-level
   `drawlog` when only the emulator is at hand (then map texture → resource by
   the texture identity the Play! notes describe).
2. Capture the native renderer's records for the same tick in the same form.
   A native UI that reimplements the contracts should emit API records; a native
   UI with its own art (docs/issues/native-hud.md) cannot be compared here, only
   at the state level (its section 3).
3. Normalise both (`ref_ui_composite.normalize` / `painter_order`): plain
   sprites +1 y, clipped sprites not; whole-texture source rectangles; layer
   ascending; reverse submission inside a layer; a text batch is one unit.
4. `diff_records(original, native, textures)` aligns the two painter-order
   streams and returns every replaced, missing or extra unit. An empty list is
   parity for that frame.

What tier A proves: resources, positions, clips, tints, layers and order. What
it does not: sampling, field handling, blending arithmetic, the art itself.

## 5. Tier B: raster parity

Compare **pixels**. Reduce the original's side to the logical 640 × 448 woven
picture before comparing; never compare a 640 × 480 export directly.

1. **Original capture.** Play! build at factor 1, `displaypatch all 0`,
   `texreplace 0`, `upscale 0`, `edge 0`, then `shotfb`. Prefer the half-rate
   mode, where one capture holds both fields (§2.3). In the normal mode take
   `burst NAME 2` on a static scene and weave by field; check the field with
   the `gs` command. Exact weave rules for odd sprite tops are **U**.
2. **Present gain.** Remove the present multiplier: measure it on a known flat
   colour in the same capture (a cleared area or a `ui_drawRect` of known
   colour), or fix the brightness option and use the 0x19cbb0 formula (I).
3. **Native capture.** Render the same frame at 640 × 448 logical, 4:3
   (`--plain` for the translation), with no widescreen extension
   (layout.h:1–30 is the host's, not the original's). A square-pixel 640 × 480
   output must be resampled back to 448 rows first.
4. **Reference.** Optionally composite the original records with
   `ref_ui_composite.composite` and decoded textures; this separates "records
   right, raster wrong" from "records wrong".
5. **Compare** with `compare(a, b, tolerance, mask, slack)`:
   - mask the 3D scene (everything below sort layer 5 has no UI parity
     meaning), row 0, and the outermost columns;
   - tolerance **12 per channel** at factor 1 is the proposed starting value
     (7 for 5-bit truncation, up to 4 for dither, 1 for rounding; I, not yet
     validated against a capture);
   - `slack=1` forgives one-row shifts at field and box-filter edges;
   - report `max_delta`, `over`/`total`, `bbox`, `first`. Proposed pass:
     `over == 0` after mask and slack, for a static frame.
6. Any failure goes back to tier A first.

## 6. Scenes to cover and how to reach them

Driving uses the `.rig` script language shared by the Play! build
(`emushots.py`, `tools/recomp/sound/emuref.py` driver) and the native app
(`--script`): `at`, `wait`, `tap`, `tapuntil … timeout`, `until <global> ==
… timeout`, `app shot`. Tick-keyed routes (`s12/mkdet.py`, `det.sh`) give the
same simulation tick in both builds; `rta_replay` re-renders a recorded
stream with no game. Nothing below was run in this pass.

| Scene | Content to compare | How |
|---|---|---|
| HUD, one player | status frame, three bars at fractions 0, ½, 1, flash, cooldown dim, level text | first level after boot route; `poke` health/mana (tests only) as native-hud.md §3 did |
| HUD, two to four players | slot origins [12,478,167,323], remote frame `hud_multi.tex` | offline multi-pad game; network promotion only with two machines (VALIDATION.md) |
| HUD adjuncts | potion overlays (rects), level-up glow, notices, gold, boss meter, selector, compass, minimap | the same route, events forced; contracts partly **U** (hud-layout.md) |
| Menu frames | styles 0/1/2 (`ctile`, `btile`, `tile`), small and large sizes | pause menu, options, dialogue boxes |
| Text | small and medium fonts, kerning pairs, centred names, wrapped help text | character creation name, help boxes, item descriptions |
| Inventory | picture-cache icons, item panels, 3D figure (mask it) | `menu_openInventory` from a tick-keyed route |
| Title and front end | full-screen art, edge lines | boot route `boot-shots.rig` |

## 7. The reference compositor

`tools/ref_ui_composite.py` (pure Python, standard library):

- `normalize`, `painter_order`: the record rules of §4.
- `composite(records, textures)`: 640 × 448 RGBA with GS alpha; modulate tint,
  alpha test > 1, blend 0x44 with clamp, rectangles as two corners, scissor
  clamped to 640 × 447 and applied half-open (an approximation of the field
  scissor; hud-layout.md explains odd bottoms). It does **not** model the
  16-bit buffer, dither, fields, the present pass or texture sampling offsets:
  it is the ideal picture the original approximates.
- `compare(...)` and `diff_records(...)`: tiers B and A.
- Full-screen speed: one 640 × 448 comparison 0.47 s, a full-screen
  blended rectangle 0.91 s (`local/r2-parity/timing.log`).

## 8. Validation and what is left

**Executed:** `python3 -m unittest discover -s tools -p 'test_ref_ui_composite.py'`,
25 tests on invented textures: submission vs painter order, layers, text
batches, +1 y, half-open clip and clamp, flips, rectangles, modulate, clamp,
blend arithmetic including negative differences, alpha test, a base-HUD
composition from `ref_ui_layout.hud_base_layers`, comparator tolerance, mask,
slack and record diffs.

**U / left:**
- the exact weave of normal-mode captures for odd sprite tops; the caller of
  the 0x17a5a0 header (no direct `jal`; pointer calls were not searched);
- a capture at a brightness other than the 0.5 default, to confirm the gain
  formula on real pixels (the formula itself is executed);
- the API-level log in the translation (proposed in §3);
- any run of tier A over whole frames or of tier B against `shotfb`. The
  tolerance of §5 is a proposal until one original capture and one reference
  composite of the same static frame have been compared.
