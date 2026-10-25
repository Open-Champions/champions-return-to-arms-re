# Save/load screen art and layout — SLUS-20973 v2.00

2026-10-23. This is research for the shared native client, not a native change.
The original ELF is pinned by SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
`tools/difftest_save_screen.py` executes original functions in `tools/ee_emu.py`
against authored memory at seeds 20973 and 7; `tools/ref_save_screen.py` holds the
numeric reference. **Executed** below means that bounded synthetic test, not a
Play! or console capture. **Observed** means the code or named asset structure at
the stated address was read. Round 2 also read one completed slot file from the
existing Play! rig without modifying it. No live card-screen capture, localized
text, texture pixels, or retail screen was captured.

Prior evidence: `t3/research-menus` `docs/menus.md` and
`t3/research-menus-layout` `docs/frontend-layout.md` at `29c90a5`, plus
`t3/research-saves` `tools/difftest_save.py`. This document extends their
forced-state card captures with save/load specific row data, art selection,
preview fields, prompts, and input. The native menu art report is a private working note (not in the
repository).

## Entry and screen phases

| Field or function | Evidence | Meaning |
|---|---|---|
| `g_memcardState` 0x88d3a0 | **Observed** dispatch 0x2189e0 | 3 saves, 4 loads. This is the outer screen selector. |
| `memcard_saveScreen` 0x218afc | **Executed** 0x218b44, 0x218bcc | Looks up `menu_savegame`, calls `memcard_browser` 0x219b90 while browser stage 0x88d3e4 is zero, then calls `memcard_slotList` 0x21c3a4 while slot stage 0x88d3d8 is zero. |
| `memcard_loadScreen` 0x219360 | **Executed** 0x2193ac, 0x2193f8 | Same two-stage route, with `menu_loadgame` and `MemcardLoad` keys. |
| Browser state 0x88d3e0 | **Observed** jump table 0x53f440; prior **Executed** 35 forced states | Card check, format and errors precede the slot list. `hud_drawMessageBox` 0x1df248 supplies shared prompts. |
| Slot state 0x88d3dc | **Observed** jump table 0x53f7f0; **Executed** selected states | 4 draws and accepts the list, 5 is overwrite confirmation, 9 is delete confirmation, 15 is an error prompt. The test forces states independently; it does not assert a full live sequence. |
| `g_cardXferLatch` 0x4f8f28 | **Observed** 0x218ba4, 0x218c18, 0x2195a8, 0x2190d0 | Set when a save/load slot is committed, cleared after clean completion as documented in `docs/issues/sync-breakers.md` B10. |

## The art actually selected

**Executed:** `memcard_slotList` submits two `ui_drawFrame` 0x17fbb8 calls,
at 0x21d814 and 0x21e548. In the settled fixture both pass
`(x=61, y=126, w=519, h=97, layer=6, tint=0x7f616369)`; their last flags are
1 and 0. The wrapper at 0x17fbb8 adjusts the rectangle to
`(60,122,521,105)` and **forces frame style 2** at 0x17fbd0. The frame
implementation 0x17c118 chooses the style-2 prefix `tile` at 0x17c1b4.
Its resource lump is `interfac.lmp` at 0x17c194. This corrects any reading of
the wrapper's final flag as the texture style.

**Observed:** format strings at 0x5340b8–0x534138 form nine `tile*.tex`
lookups: `tiletopleft`, `tiletopright`, `tilebotleft`, `tilebotright`,
`tileleft`, `tileright`, `tilebot`, `tiletop`, `tilecenter`. The read-only
`INTERFAC.LMP` directory/header check finds all nine: center 320×224, each
other piece 32×32. These are source texture dimensions, not the on-screen
piece rectangles. A second **Executed** fixture follows `ui_drawFrameImpl`
with authored texture descriptors matching those header dimensions. The first
wrapper call makes 40 tile submissions to 0x17b590/0x17b8b0: four corners at
`(60,194)`, `(549,194)`, `(60,121)`, `(549,121)`; top and bottom strips at
`x=92+32i`, `i=0..14`, `y=122/195`; left and right strips at `x=60/549`,
`y=154/186`; and two center submissions at `(67,128)` and `(387,128)`.
The second wrapper call, whose final stack flag is 1, makes no tile submission
in this fixture. All nine texture names reach the resource lookup. Exact
cropping, alpha blending and GPU pixels remain **Unknown** because resource
lookup and packet generation were replaced with authored descriptors/stubs.

**Executed:** no dedicated card icon sprite or `ui_drawSprite` submission
occurs in the followed slot-list body for the populated fixture. The browser
uses `hud_drawMessageBox`; the prior `MESSAGE_BOX_CALLS` capture on
`t3/research-menus-layout` puts its shared frame at `(60,186,520,68)` plus
the inner `(68,196,520,68)`, with small-font text. A card-specific picture
must not be chosen from an asset count alone. **Unknown:** what the full
front-end background shows behind these calls, and the finished retail pixels.

## Typography, rows and selection

**Executed:** `memcard_slotList` starts `text_begin` 0x1800b8 at 0x21c404
with the small-font pointer read from 0x4f7104, layer 6, base colour
`0x001e6464` with fade word 0x8e11f8 placed in the alpha byte. The settled
fixture has alpha 0x7f. The later batch at 0x21d830 uses the same small font,
layer 6, `0x801e6464`; colour calls include 0x21c6f8 (`0x7f3c4646` in the
fixture) and 0x21d850 (`0x7f323c3c`). These alpha values are fixture states,
not constants for all frames. The title is centered at `(320,110)` at
0x21d6e8. Text width and localized glyph rendering are stubbed.

**Executed:** five visible rows are considered, with `y=128+17r` for
`r=0..4`. The scroll base is 0x879e2c. Each visible numbered row submits
ASCII at `(77,y)` from 0x21d99c. A populated row additionally submits the
level line wide at `(100,y)` 0x21da8c, date ASCII at `(365,y)` 0x21db24,
and clock ASCII at `(487,y)` 0x21dbe8. With `g_memcardState=3` (save), the
first free row uses `MemcardNewSave` and wide text at `(100,y)` 0x21d9f4;
with `g_memcardState=4` (load), an empty list submits no rows. Rows beyond
the cache count retain only their numbered marker when count is nonzero.
The fixture covers counts 0, 1, 2, 5 and 6 in both modes, plus count 8 in the
indexed-row probe. The source does not establish that a real card holds eight
usable entries.

**Executed**, now with a settled nonzero scroll and distinct rows: the list
count is read from 0x4f9238. Visible row `r` uses index `0x879e2c + r` at
0x21d930–0x21d950. The metadata address is `0x88d300 + 16*index` at
0x21da10–0x21da24; the cached header address is
`0x8e1200 + 0x70*index` at 0x21da18–0x21da74. For scroll base 2 and count
8, `indexed_rows` passed headers 2–6 (0x8e12e0 through 0x8e14a0) and each
distinct date/clock on both seeds. The committed probe also checks five
`%d.` formatter calls with values 3–7 at 0x21d94c, paired with five numbered
ASCII draw submissions at 0x21d99c and y=128+17r. Text formatting and glyph
rendering remain stubbed. The target scroll word 0x879e30 must also be 2;
otherwise the list updates 0x879e2c back to zero at 0x21c9dc–0x21c9f8. Header +0x64, +0x6a,
and +0x6c feed play time, player count, and difficulty. These index and stride
calculations are **Observed** at the stated addresses and **Executed** in the
settled fixture. Actual card capacity and scroll reachability remain **Unknown**.

**Observed and Executed** in `date_boundary` and `clock_boundary`: the date
formatter call at 0x21db0c receives `%d/%d/%d` and single-digit BCD month/day
arguments `(1,9,2026)` from metadata bytes +6, +5 and +7 (year plus 2000).
That format requests no zero padding; the text formatter itself is stubbed.
The clock at
0x21da24–0x21da70 and 0x21db30–0x21dbec turns BCD +3 (hour) and +2
(minute) into `%d:%s%d%s`: 00:05 → `12:05am`, 11:10 → `11:10am`,
12:00 → `12:00pm`, 13:25 → `1:25pm`, and 23:59 → `11:59pm` on both seeds.
The minute below ten gets a leading zero; the suffix is lowercase and has no
space. Real card directory timestamps and locale-dependent display remain
**Unknown** because the completed slot file does not contain those directory
metadata bytes.

### Completed slot file check

**Read only:** the existing, previously run Play! rig's
`local/rig-out/run6-6/data-b/vfs/mc0/BASLUS-20973/BASLUS-20973_slot0`
under the original checkout is 310,392 bytes (0x4bc78), SHA-256
`c969195418643f79e31ddc493ad30c3cd5c24802be0aa34614fb584299027796`.
Its 0x70-byte header contains level identifier `strife` with an empty second
part, 59 play seconds, one player, and difficulty index 1. This is a finished
slot record, not a fabricated header. The committed optional `--completed-slot`
probe verifies size, SHA-256 and the three header fields before running
`memcard_slotList` on seeds 20973 and 7 with debug both off and on. The
original function passes that header to the level-label lookup at
0x21da74/0x22233c; the localized
level text is **Unknown** with lookup stubbed. With the record loaded into the
cache, the single-player branch at 0x21e194–0x21e208 and difficulty key
`memcardDifficulty1` at 0x21e258 execute on both seeds. The debug-only time
line at 0x21dd48–0x21e0f0 selects `MemcardBrowseMinutes` and passes numeric
1.0 for 59 seconds to the value submission at 0x21e088 (0x21dd94–0x21ddb8
clamps zero minutes to one). With debug
off, that line is absent. The character/class suffix uses separate cache state
at 0x88cf80/0x4f8e80; this record check does not establish its displayed
text. The real directory timestamp, localization, and rendered pixels were
not captured.

**Executed:** selection rectangle 0x21e508 follows displayed selection word
0x879e28: endpoints `(66,133+17r)` to `(574,152+17r)`, layer 6. The base
colour is `0x00366876` at 0x21e4c8, with an alpha computed from fade and
interpolation; the fixture submits `0x3f366876`. A second tile frame follows
at 0x21e548. There was no explicit text clip in this fixture. This rectangle
is **Inferred** to be the selected-row highlight from its motion with
0x879e28; forcing an out-of-count row also moves it, so the test alone does
not prove retail cursor bounds.

## Selected-slot summary and prompts

**Executed:** with a populated synthetic header selected, the summary draws
`MemcardSavePlayers` at `(220,247)` (0x21dce4/0x21dd00) and
`MemcardDifficulty` at `(220,264)` (0x21dd10/0x21dd28). Values appear at
`(320,247)` 0x21e208 and `(320,264)` 0x21e2c0. Header +0x6a drives the
player count and +0x6c selects one of the difficulty lookup keys at
0x21e230–0x21e2b4. When debug byte 0x4f8ee0 is nonzero,
`MemcardSaveTime` appears at `(100,281)` 0x21dd48/0x21dd60 and the value at
`(320,281)` 0x21e0f0 from header +0x64. With that byte zero the save-time
line is absent. **Unknown:** all localized strings, text widths, and some
single-character character/class description branches at 0x21e194–0x21e208;
the basic fixture's artificial header is not a validated save file. The
completed-record check above verifies the header-backed routes separately.

| Slot state | **Executed** lookup keys and draw anchors | Input result in the settled fixture |
|---|---|---|
| 4 list | title `(320,110)`; save mode adds `MemcardNewSave` at the first free row | confirm mask 0x40 on the first populated slot enters state 5; bit 0x80 enters state 9; repeat mask 0x204000 advances selection one row when another cached slot exists; cancel mask 0x20 starts the back fade (0x21ccc0) |
| 5 overwrite | `MemcardConfirmOverwrite` `(320,264)` 0x21cedc/0x21cf34; `MemcardContinueBack` `(320,320)` 0x21cf54/0x21cfa4 | bit 0x20 returns to 4; bit 0x80 enters 11 and marks write intent at 0x88d400. Card write completion is not part of this one-call assertion. |
| 9 delete | `MemcardConfirmDelete` `(320,247)`, `MemcardDeleteSlot` `(320,264)`, `MemcardYesBack` `(320,320)` at 0x21d234–0x21d328 | bit 0x20 returns to 4; confirm bit 0x40 starts a fade before the delete queue path (0x21d360–0x21d3c0). |
| 15 error | `MemcardError` `(320,196)`, `MemcardMissingError2` wrapped at `(320,230)`, `MemcardContinueBack` `(320,320)` at 0x21d4f0–0x21d6bc | Key and anchors verified; the text and card result type are **Unknown** for this artificial state. |

Button labels depend on the configured scheme word at 0x41b69c; these are
**button masks**, not an unconditional promise about face-button names. The
normal scheme's masks were executed on `t3/research-menus` at
0x1e6b68. `memcard_slotList` reads owner raw-pad words from 0x4028d0 at
stride 0x58, using slot byte 0x4f923c, edge +0x0c and repeat +0x10
(0x21c478–0x21c4ac). This is per-machine draw-task UI.

## Ordered native port list

1. Reuse the disc-selected **small font** and localization lookup for title,
   rows, preview and prompts. Do not render card names from a host font.
2. Load the nine named `tile*.tex` pieces from `INTERFAC.LMP` at runtime and
   implement the 0x17fbb8 wrapper plus 0x17c118 nine-piece frame. Verify the
   resulting rectangles and alpha in a graphical capture before calling it
   visually equivalent.
3. Build the card-browser stage and shared message boxes, preserving save/load
   titles, pending/error prompts and the two-stage routing at 0x218afc/0x219360.
4. Populate the five-row list from real card directory entries and cached
   save headers; use the **Observed** `base+r`, 16-byte metadata stride and
   0x70-byte header stride. Submit numbered rows from the settled base+r
   index, using `%d.`. Implement the save-only new row, BCD `%d/%d/%d` date and
   12-hour clock formatting, selected-slot preview, and debug-only time line.
   Preserve the completed-record one-player route, difficulty-index lookup,
   and minimum-one-minute debug value established by the pinned record probe.
   Treat missing or invalid card data as an explicit state rather than an
   invented slot. Verify directory timestamps and localized level/class text
   against a live card capture before claiming complete display parity.
5. Bind highlight interpolation, scroll and raw-pad input to 0x879e24–0x879e34
   and the configured button masks. Port overwrite/delete confirmation, back,
   wait, retry and error transitions, then the card-operation queue. Keep the
   existing save/load buffer and latch semantics in `docs/audio-save.md` and
   `docs/issues/sync-breakers.md`.
6. Compare native captures with a permitted real-card capture for text width,
   actual card icons/background, language, frame tiling, fades and prompts.
   Those are **Unknown** here and should remain labelled until observed.

## Reproduction and limits

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_save_screen.py
local/SLUS_209.73 '<private-disc>.iso' --completed-slot
'local/rig-out/run6-6/data-b/vfs/mc0/BASLUS-20973/BASLUS-20973_slot0'`
passed **189 checks** across seeds 20973 and 7, including indexed numbered
rows, the single-digit date format, clock boundaries, read-only tile header
dimensions, and completed-record preview branches with debug on and off.
The companion `difftest_frontend_screens.py`, `difftest_frontend_art.py`, `difftest_menus.py`
and `difftest_save.py` on their existing research worktrees also passed.
The full Python unit suite passed 652 tests. The new difftest follows
the original UI control functions, frame wrapper and frame implementation
with authored texture descriptors; resource lookup, text shaping, card I/O
and GPU presentation are stubbed. It proves call
submissions and selected state changes under authored inputs, not pixel or
memory-card parity. No game bytes or raw disassembly are tracked.
