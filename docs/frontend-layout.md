# Frontend layout and sound, US v2.00 (SLUS-20973)

**Status: MORE.** This is a function-level capture of the menu list, publisher
logo, pause list, main-menu destinations, character and card screens, and the
five art questions revisited below. It does not establish pixel-exact finished
screens or the class model's rendered pose.
The executable SHA-256 is `292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
The previous flow contract is `t3/research-menus` `099900e`; the primitive
frame/font contract is `t3/research-ui` `3e39392`; the music contract is
`t3/research-audio` `6b08886`. The native front end's missing layout is
described in `open-champions/worktrees/menus/work/loop-menus-r2-report.md`.

## Evidence labels

| Label | Meaning |
|---|---|
| **Executed** | Reproduced by a committed difftest under `tools/ee_emu.py` at seeds 20973 and 7. The tool is named in the row. |
| **Static** | Decoded from the instruction words by `tools/scan_lookup_sites.py`. A candidate only: a branch may reach the call with another register value (see the sound note below). |
| **Inferred** | A reading of names or identifiers, not traced. |
| **Unknown** | Not captured. |
| **Observed** | Read from executable or private-disc structure at the stated address or resource offset; execution is identified separately. |

Draw-call numbers are reproduced by a difftest; the new **Observed** disc
structure and instruction facts identify their own source. The seeds (word
0x404460) do not change any record in these fixtures; they are kept because the
earlier contract used them.

## Method and limits

Tools (all take the owned executable path; none writes game bytes):

- `tools/difftest_frontend_layout.py` with `tools/ref_frontend_layout.py`: the menu
  list (0x1a07c4), `frontend_run` (0x1e08f0), publisher logo (0x321640), pause
  (0x18cc08), name entry (0x22c920), credits (0x223c64/0x223d3c), boot/card,
  intro, selection start, card dispatch, menu sounds, music gate and fonts.
- `tools/difftest_frontend_screens.py` with `tools/ref_frontend_screens.py`: every
  state of `playerSel_task` (0x225478), `memcard_slotList` (0x21c3a4),
  `memcard_browser` (0x219b90) and `memcard_importScreen` (0x21fa2c), plus
  `hud_drawMessageBox` (0x1df248) and the pinned static lookup sites.
  `--print-table` regenerates the tables.
- `tools/scan_lookup_sites.py`: constant-string call sites in a code range.
- `tools/count_frontend_assets.py`: read-only counts on the private disc.
- `tools/difftest_frontend_art.py` with `tools/ref_frontend_art.py`: card row
  submissions and selection-word rectangle, class-selection helper path, menu
  frame call, multi-line credits and movie call sequence at seeds 20973 and 7.
  An optional `BG/DATA` directory or private ISO argument checks UTF-16 line
  counts and MPEG sequence headers without writing resource bytes.
- `tools/test_ref_frontend_layout.py`: unit tests of the tables, no game file.

Texture lookup, localization, text width and GPU packet generation are stubbed,
so frame widths are **minimum widths in these fixtures**, not retail text-width
results. For the screen sweeps the state word of each function is forced to
each value of its own jump table with every callee stubbed; the states are not
claimed to occur in that order in play. Text is recorded only by call site;
no localized string, image or sound is stored. The UI's 640×448 coordinates
are draw API coordinates; the plain sprite primitive adds one to y when making
its GPU packet (`research-ui/tools/ref_ui_layout.py`). No screenshot or audio
playback was captured. **Executed**, not Ran.

For `ui_drawFrameImpl` (0x17c118), the first row of a list submits a style-0
frame call with tint `0x300000ff` (**Executed**). The `ctile*.tex` expansion
is **Inferred** here from the literal `%s…tex` strings and prior frame research.
The backing frame uses
style 2 `tile*.tex` and tint `0x80808080`; the front overlay uses style 0
and tint `0x3f000000`. All nine frame pieces are separate textures in
`INTERFAC.LMP`; their source sizes, clipping and assembly order are the
executed `menu_frame` contract in `research-ui/tools/ref_ui_layout.py`.
The three calls for a four-row ordinary list with selected row 0 are
`(300,259,40,33,layer 7)`, `(292,248,56,122,layer 7)`, and
`(301,260,54,114,layer 6)` respectively. They expand from the frame-wrapper
call `(293,252,54,114,layer 7,0x80808080)`. The selected-row frame's height
is 32 at an even y, 33 at an odd y. Only selected row zero is covered by the
frame model. The exact per-table calls are asserted by the difftest; text width
can enlarge them.

## Art follow-up: five former unknowns

The new difftest plants distinct nonzero 16-byte card records, a zero-record
control and authored UTF-16 test tokens in emulator memory. These records are
not validated card headers. It does not save private resource data. A blank
cell means the function makes no such UI submission in the stated fixture,
not that the retail screen lacks an image. All coordinates are draw-call arguments.

| Item | Result and source | Texture / dimensions / clip / tint / layer |
|---|---|---|
| Class art in creation | **Executed** `class_draw`, phase 1 of `playerSel_task` 0x225478, class bytes 0, 1, 2, 5, 11 planted for slot 0: 0x2257ac calls 0x22a968 and 0x2258c8 calls 0x22a83c. Following those two helpers yields no `ui_drawSprite` 0x17fb68, resource lookup 0x17365c or UI clip 0x1803e0. The footer frames at 0x2297b8 `(21,18,0,355)` style 1 and 0x229958 `(300,402,40,32)` style 0 submit, both layer 6/tint `0x08000000`. **Inferred:** the class figure may use a 3D scene path, outside these followed callees. **Unknown:** the model, pose and animation mapping; other class values and the complete call tree. | No class `.tex` lookup or UI image rectangle among the followed callees. `SELECT.LMP` and `SELECT2.LMP` entry counts do not associate an entry with a class. |
| Cursors | **Executed** `menu_cursor`: main row zero calls `ui_drawFrameImpl` at 0x1a1104 with `(300,259,40,33)`, layer 7, tint `0x300000ff`, style 0. **Observed** `interfac.lmp` at 0x534090 and nine `%s…tex` format strings at 0x5340b8–0x534138. **Inferred:** style 0 supplies the `ctile` prefix; the formatting callee 0x17c118 is not followed here. **Executed** `slot_draw`: varying 0x879e28 from 0 through 5 moves the rectangle to `(66,133+17r)–(574,152+17r)` at 0x21e508, layer 6, colour `0x366876`; changing 0x879e24 alone does not move it. No text clip is requested. **Inferred:** this rectangle is a list-row highlight. | Menu frame: 40×33 wrapper at row zero; nine formatted textures are not traced by this fixture. Card rectangle: 508×19 endpoints, including an out-of-count position at r=5 with count 1. Its use as a selection cursor remains **Inferred**. |
| Card rows | **Executed** `slot_draw`, `memcard_slotList` 0x21c3a4 state 4 with planted count 0–6 at 0x4f9238 and five authored 16-byte records at 0x88d300. The fixture reads record bytes at offsets +2, +3, +5, +6 and +7 for rows below the count; both nonzero and all-zero records reach the same draw call sites when count is 1. At most five rows submit: y `128+17r`, `r=0…4`. Rows below the count submit ASCII `(77,y)` at 0x21d99c, wide `(100,y)` at 0x21da8c, ASCII `(365,y)` at 0x21db24 and `(487,y)` at 0x21dbe8. Rows above a nonzero count submit only `(77,y)`; count 0 submits none. **Unknown:** whether a planted nonzero record is a valid card header or how real card data changes text. | Small-font layer-6 batch; no per-row sprite or clip in this fixture. The count is a list bound, not proof of populated or valid cards. |
| Intro calls | **Executed** `intro_draw`: `splash_introMovie` 0x321788 requests `porko_l.vag` at 0x3217bc and `porko.lmp` at 0x3217c8. A separate `movie_update` 0x3205ec call with zeroed decode state reaches `FlushCache` 0x352c60, `sceGsSyncPath` 0x34fe78 and `movie_startGifChain` 0x3201b0 at 0x320d68. Calls to 0x3502e8 and 0x350618, and the 0x8eb0e0 argument, are **Unknown**. The recorded 0x80808080 second argument of `FlushCache` is stale register state, not a colour. No UI sprite, resource lookup or text clip is submitted. **Observed** by optional private-ISO structure check: `PORKO.LMP/porko0.m2v` has a 640×448 MPEG header; `porko000.m2v` has a 640×480 header (also noted in `docs/issues/native-app.md`). **Unknown:** which entry `movie_open` selects; the intro fixture stops before that call. | These call submissions have no UI layer/rectangle/clip arguments. The GS upload chain is built by 0x31fdf4 (`docs/mainloop.md:25`); neither a decoded picture nor displayed crop/timing is established by this fixture. |
| Credits layout | **Executed** `credit_draw`, `credits_run` 0x223d3c: a pointer array beginning at 0x4fb5e8 submits each authored UTF-16 line twice, shadow `(322,scroll+19r+2)` at 0x22401c and main `(320,scroll+19r)` at 0x224044, for line index `r`. At scroll 224, all three tested normal lines use colours `0x20000000` (0x224004) and `0x5e405e5e` (0x22402c). At scroll 400, two lines have different colours: first `0x07000000`/`0x14405e5e`, second `0x02000000`/`0x06405e5e`; colour can vary by line position. A two-character backslash-plus-`b` prefix in the authored UTF-16 test line changes the main colour to `0x5b1a444c`; both submitted text pointers advance four bytes past the prefix. The scroll word drops by 1 per call. **Observed** by optional private-ISO structure check: four UTF-16 BOM/CRLF `.txt` entries in `CREDITS.LMP` have 360, 360, 362 and 361 lines (English, German, French, Spanish). The counter includes a final nonempty line without LF. No text is reproduced. | `CREDITS.LMP` has zero `.tex`; medium font, layer 7, no sprite or explicit clip in this followed path. Full locale typography and onscreen timing remain **Unknown**. |

## Fonts

`0x4f7100` is the medium font word and `0x4f7104` the small one
(`research-ui/docs/formats/ui-fonts.md`). Each `text_begin` call's font was found by
planting distinct sentinels in both words (**Executed**, `font_uses` in
`difftest_frontend_layout.py` and the `text_begin` records of the screen tables):

| Batch | Site | Font | Layer | Colour in the fixture |
|---|---|---|---|---|
| Front-end parent, states 0–4, 11 | 0x1e0dcc | small | 7 | `0x64464646` |
| Front-end list text (`menuList_draw`) | 0x1a09e8 | medium (the caller passes 0x4f7100) | 7 | `0` |
| Difficulty extra line | 0x1e13c8 | small | 6 | `0x082d5049` |
| Name entry | 0x22c9c0, 0x22d198 / 0x22d0e4 | medium / small | 6 | `0x585e5d` / `0x316864` |
| Credits | 0x223e40 | medium | 7 | `0x80000000` |
| Pause | 0x18d5e8 | medium | 7 | `0x80464646` |
| Every character, slot-list and message-box batch swept | see tables | small | 6 | see tables |

This corrects an earlier line of this document that gave `0x4f7100` for the
parent batch at 0x1e0dcc: it reads the small word. The pause list text takes a
zero font word in the pause fixture, so its list font is **Unknown**. Colours
are fixture values: the alpha byte and some channels depend on fade state, so
real animation times are not covered.

## Screen captures

All list entries below are centered text calls. The first x/y pair is entry 0;
successive y positions are 22 apart. Entry meanings are descriptions, not
copies of localized game strings. The table keys in `tools/ref_frontend_layout.py`
and the words "players", "difficulty", "mode", "options" are local geometry
aliases taken from `docs/ui.md:214-223` (state meanings, **Inferred** from the
menu tables); descriptions of what each row's choices are (counts of players,
mission choices, and so on) are **Inferred** and not traced to a research file.

| Screen | Draw submission | Remaining evidence needed |
|---|---|---|
| Boot/card check | **Executed** (`shallow_screen_calls`) 0x32396c requests config load at 0x323974 and installs modal callback 0x3238f4 at 0x323988; the callback calls `save_daemonDraw` 0x2189e0 at 0x3238fc. It submits no UI primitive itself. The screen it shows is the card screens below. | Populated card state to reach real prompts and the spinner (`memcard_tickSpinner` 0x222e10 draws nothing in a zeroed run). |
| Publisher logo | **Executed** (`logo_draw`) `splash_soeLogo` submits `SOELOGO.LMP/soe_splash_url.tex` at `(192,330)` and `soe_splash.tex` at `(64,50)`, both layer 3, tint `0x80808080`, no explicit clip. | Texture sizes and animation/fade across frames. |
| Intro | **Executed** `splash_introMovie` 0x321788: display-rate mode 1 at 0x321790, `stream_playGlobal` at 0x3217bc, `lump_load` at 0x3217c8, stream-ready check 0x3217d0, `movie_isFinished` 0x32180c. **Static** (`scan_lookup_sites`): `porko_l.vag` and `porko.lmp`. GPU upload calls and the disc picture size are in the art follow-up above. | Displayed crop, timing, fade and soundtrack playback. |
| Main menu, state 0 | Four rows at `x=320`, `y=259,281,303,325`. **Executed** title: lookup 0x1e0aac is `FRONTEND.LMP/title.tex`; sprite call 0x1e0ac8 submits `(141,15)`, layer 5, tint `0x80808080`, for states 0–4 and not for state 11 (`frontend_details`). **Executed** row destinations (`main_accept`): selected index lives in the word at table+4·16+4 (0x4f6bcc); accepting row 0 enters state 1 (the table at 0x4f6bf8), row 1 calls `memcard_requestLoad` 0x2176e0 at 0x1e166c and stays in state 0, row 2 calls the options setup 0x1e6428 and enters state 11 (table 0x4f6e88), row 3 enters state 15 and requests the credits music (`mx_endcredits_ext_l.vag`, flags 3) and `credits_load`. Every accept first plays `menu_main_accept.anm`. The dispatch compares the row's entry key to constants with the original string comparison 0x3b8534, so a native port must dispatch by key, not by index assumption. | Exact title size, background movie/frame, localized glyphs, text-width frame expansion, fade alpha. |
| Game type, state 1 | Two rows at `x=320`, `y=281,303`. Same title submission. | Same unresolved art/font details. |
| Players, state 2 | Four rows at `x=320`, `y=259,281,303,325`. Same title submission. | Same. |
| Mode, state 4 | Two rows at `x=320`, `y=281,303` (table 0x4f6c68). A three-row table 0x4f6c28 has `y=270,292,314`. Same title submission. | Which table each network setup branch selects. |
| Difficulty, state 3 | Four rows at `x=320`, `y=259,281,303,325`. **Executed** the parent also submits a text batch (small font, layer 6, 0x1e13c8) and a centered text call at `(320,366)` (0x1e13e0); its content and final colour were not established. Same title submission. | Content and colour of the extra line, disabled-entry treatment. |
| Options, state 11 | Thirteen rows with first three at `x=297` (the table's value flag), remaining ten at `x=320`; `y=89,111,133,...,353`. No title sprite. Minimum backing-frame call `(214,78,212,320)`, layer 7, style 2. What rows 0–2 control is **Unknown** here. | Value bars/knobs, glyphs, current values and fade. The music slider timing contract is in `docs/spec/music-volume.md` on the combat-constructors branch. |
| Character creation | See the next section. | |
| Name entry | **Executed** `nameEntry_draw` 0x22c920 submits centered text calls at `(163,98)` (0x22cba4) and `(233,98)` (0x22ccec), sets layer 6 at `text_begin` 0x22c9c0, draws a rectangle `(0,−9)`–`(0,11)` on layer 6 with colour `0x1e3053` at 0x22d084 and requests text clip `(41,0,640,480)` at 0x22d20c, in the zeroed fixture. Three wide-text calls `(81,138)`, `(81,158)`, `(81,178)` (0x22ce4c, 0x22ceb0, 0x22cf14), one wrapped call `(41,38)` (0x22d12c) and one ASCII call `(41,72)` (0x22d26c). Batches: medium 0x585e5d (0x22c9c0), small 0x316864 (0x22d0e4), medium 0x585e5d (0x22d198), all layer 6. `text_setClip` 0x1803e0 clamps to 640×447 (`symbols/engine.tsv:166`). The rectangle is zero width in this fixture; a visible cursor cannot be inferred. Static menu sounds in `nameEntry_run` (0x22be68): toggle sites 0x22bff0, 0x22c0bc, 0x22c150, 0x22c1fc, back 0x22c3b8, accept 0x22c474 (**Static**). | Grid glyphs, accepted-name colours, executed sounds. |
| Load/save | See the card section. | |
| Credits, state 15 | **Executed** `credits_load` 0x223c64 then `credits_run` 0x223d3c opens a medium-font batch at 0x223e40 on layer 7, colour `0x80000000`. With one authored wide-string line (`credits_authored_line`) at scroll value y the code submits two centered calls: `(322,y+2)` at 0x22401c after a colour call at 0x224004, and `(320,y)` at 0x224044 after a colour call at 0x22402c; the scroll value drops by 1 per call. Colour values: y=448 gives `0` and `0x00405e5e`; y=400 gives `0x07000000` and `0x14405e5e`; y=224 gives `0x20000000` and `0x5e405e5e` (the three y values are asserted points, the curve between them is not). End: a zero return from `credits_run` runs `0x211338(2)`, requests the frontend theme again with flags 1 and returns to state 0 (`credits_exit`); nonzero keeps state 15. Lumps loaded: `credits.lmp` at 0x223d10 and 0x223e20 (**Static**). Multi-line spacing and resource structure are in the art follow-up. | Displayed typography, exit input and sound. |
| Pause | Normal offline `pauseMenu_open` 0x18e334 and `pauseMenu_task` 0x18cc08 enabled table rows 0,1,2,5,8 in the synthetic no-level fixture. Five centered calls: `x=320`, `y=179,201,223,245,267`. Backing-frame call `(292,168,56,144)`, layer 7, style 2, tint `0x80808080`; cursor `(300,179,40,33)`, layer 7, style 0, tint `0x300000ff`; front overlay `(301,180,54,136)`, layer 6, style 0, tint `0x3f000000`. A subsequent `text_begin` uses the medium font, layer 7, colour `0x80464646`. | Game-scene background, glyph placement, conditional net/debug rows, fade and prompts. |

### Character creation (class, appearance, ability points, name)

`playerSel_task` 0x225478 is a draw task (priority 9, registered at 0x2247ac). Its
phase byte 0x8e2c02 selects one of 16 handlers through the jump table 0x5404a0 at
0x225950; the handlers are reached only when the float at 0x8e2c44 equals 1.0
(0x2258e4). **Executed** (`difftest_frontend_screens.py`, table
`PLAYERSEL_PHASES`): every phase's UI primitive calls, with fonts, layers,
colours, positions and the lookup-key call sites. Phase meanings below are
**Inferred** from the lookup-key identifiers at the listed sites (the keys
are never stored) and from the helper calls:

| Phase | Reading | Calls that matter (site) |
|---|---|---|
| 0, 13, 15 | import prompt footer | footer only |
| 1 | import selection | wrapped text `(41,29)` 0x228430; menu accept/back sounds 0x226120/0x226178 |
| 2 | appearance (look and skin) | wide `(41,38)` 0x227018, wrapped-centered `(41,93)` 0x2270ec, colour call `0x08585e5d` 0x227074 |
| 3 | ability points: four stat rows | wide text at `x=41`, `y=106,123,140,157` (17 apart); centered value calls; a glyph for a pad button via `pad_buttonMaskToGlyph` 0x1eacb8 (0x228230); description wrapped `(41,208)` 0x228430 |
| 4 | name entry | calls `nameEntry_run` 0x22be68 and `nameEntry_draw` 0x22c920 |
| 6 | "next player" box | `hud_drawMessageBox` 0x1df248 at 0x228978 |
| 7 | fade step | `hud_stepFade` 0x1df5ec at 0x228af0 |
| 8 | character summary | `text_getClassName` 0x1eb0f8 at 0x229128, ASCII values `x=172`, `y=130…215` step 17 (six rows) and wide labels at `x=157` on the same y, header ASCII-centered `(151,29)`, wrapped-centered `(151,46)` |
| 9, 10, 11, 14 | prompt footer | footer only |
| 5, 12 | nothing in the zeroed fixture | |

The common footer (every phase that reaches 0x2297b8): frame `(21,18,w,355)` layer
6, tint `0x08000000`, style 1; a prompt line centered at `(320,404)` (0x229cb4)
and a small frame `(300,402,40,32)` style 0 with a centered line at `(320,374)`.
**Class selection** has no phase of its own in this sweep (no key names it).
The figure's UI-sprite absence and footer frames are in the art follow-up; its
3D model pose remains **Unknown**. Per-race animation resources (**Static**:
`%s_intro1/2/4.anm` format names at 0x22556c, 0x226e0c, 0x228524, 0x228aa0,
0x228ee0, 0x229584, 0x22968c, 0x229f24) have no mapped model/pose here.
**Executed** menu sounds in the selection task
(`PLAYERSEL_SOUNDS`, lockstep pad words 0x41bfe0+0x58·slot set to one mask): phase 1
accept `menu_main_accept.anm` 0x226120/0x226130 and back `menu_main_back.anm`
0x226178/0x22618c; phase 3 accept 0x227ba4/0x227bc0 and 0x227ca8/0x227cbc, back
0x227d50/0x227d64. Pad masks follow `docs/netcode.md:138` (0x40 cross, 0x20 circle,
0x4000 down; face buttons Inferred there). The other `menu_main_toggle.anm` and
accept sites decoded by `scan_lookup_sites` (0x2275c0, 0x227704, 0x227818, 0x22794c,
0x227e3c, 0x226d74, 0x226e50, 0x226ea8, 0x226f34) are **Static**; site 0x227d50
shows the scanner is not authoritative (it decodes toggle, execution looks up back).

### Memory card, load and save

`save_daemonDraw` 0x2189e0 pumps the queue at 0x218a14 and dispatches on
`g_memcardState` 0x88d3a0: 3 save screen 0x218afc, 4 load screen 0x219360, 0/1 config
0x219a88/0x219b14, 5 config save 0x21f390, 6 end-game save 0x21f6dc, 9 import
0x21fa2c, 10 options 0x222b40 (**Executed**, `CARD_DRAW_DISPATCH`; mapping from
`docs/audio-save.md:168-171`). Save, load, config and end-game screens each do one
text lookup and call `memcard_browser` 0x219b90 (**Executed**, zeroed direct calls).

- **Browser** (state word 0x88d3e0, 35 states; `BROWSER_STATES`, **Executed**): every
  fixture state draws through `hud_drawMessageBox` (0x1df248) or only looks up text;
  the one direct text batch is state 5 at 0x21a1e0 (small, layer 6, `0x323c3c`). The
  message box (`MESSAGE_BOX_CALLS`, **Executed** with authored one-character title
  and body) opens a small-font layer-6 batch with colour `0x323c3c`, makes
  wrapped-centered calls at `(320,212)` (two), `(320,191)` and `(320,208)` (two) with
  width argument 470 and line height 17, then a frame wrapper `(60,186,520,68)`
  tint `0x808080` and an inner frame `(68,196,520,68)`; 520 is its default width
  and the height is the minimum for zero lines.
- **Slot list** (state word 0x88d3dc, 16 states; `SLOTLIST_STATES`, **Executed**):
  every state opens a small-font layer-6 batch, colour `0x001e6464` plus the fade
  word `0x8e11f8` shifted into the alpha byte, at 0x21c404. States 12–14 submit only
  that batch; 0–3 and 7 only the message box. States 4, 5, 6, 8, 10 and 11 add a title
  centered at `(320,110)` (0x21d6e8), a second batch `0x801e6464` with colour calls
  `0x323c3c` and `0x1e6464`, wrapped-centered text at `(320,230)` width 500
  (0x21d908), a rectangle `(66,133)–(574,152)` on layer 6, colour `0x366876` at 0x21e508
  (**Inferred**: a list-row highlight) and a message box (0x21e584). States 4 and 8
  add a prompt centered at `(320,320)` (0x21c8b0, 0x21d208); state 5 adds lines at
  `(320,264)` and `(320,320)`; state 9 lines at `(320,247)`, `(320,264)` and
  `(320,320)`; state 15 a prompt `(320,320)`, a centered line `(320,196)` (0x21d638),
  wrapped text `(320,230)` width 450 and the title. The readings overwrite (5),
  delete (9) and error (15) are **Inferred** from key identifiers.
- **Import** (state word 0x88d3a8, 24 states; `IMPORT_STATES`, **Executed**): all states
  except 21 and 22 draw through a small-font layer-6 batch `0x323c3c` at 0x220d0c and
  a message box at 0x2215f4. State 17 (**Inferred**: a character list with a preview)
  adds ASCII rows at `x=119`, `y=95…299` step 17 (13 rows, site 0x220ea4), a
  rectangle `(108,101)–(298,118)` on layer 6, colour `0x366876` at 0x221578 (the
  same colour as the slot-list rectangle, so both are **Inferred** row highlights),
  `text_getClassName` 0x1eb0f8 at 0x220f20, wrapped-centered text `(451,230)` width
  212, wide lines at `x=451` and ASCII values at `x=472`, both at `y=264,281,298,315,332`,
  and a lump lookup at 0x221378. State 23 calls
  `hud_stepFade`.
- Slot highlight and populated-row anchors are in the art follow-up above;
  text content and widths with real file data, spinner and card sounds remain
  **Unknown**. Static sounds in the slot list: toggle 0x21ca0c, accept 0x21caec
  (**Static**).
- The card sweeps do not play sounds; no error sound identifier is established.

## Menu sound and first theme

**Executed:** an actual move in the main list looks up
`FX.LMP/menu_main_toggle.anm` and calls `sound_playOnObject` 0x214230
(site 0x1a03fc). Choosing the first entry looks up `menu_main_accept.anm`; cancel
from the game-type list looks up `menu_main_back.anm`. Cancel on the main list had
no transition and no sound in this fixture. Pad bits: the lockstep words
0x41bfe0/E4/E8 (`docs/spec/player-tick.md:76`) with 0x4000 = down, 0x40 = cross and
0x20 = circle (`docs/netcode.md:138`; face buttons Inferred there). These IDs are
resource names; sample bytes, mix level and speaker output were not captured. Other
screens' sounds are listed per screen above.

**Executed:** `frontend_run` makes its initial theme request with flags 1 or
5 at 0x1e09b0/0x1e09c4. `music_playGlobal` gates the resulting queue at
music volume `0x3d4ccccc` (about 0.05), also traced in
`t3/research-combat-ctors` `docs/spec/music-volume.md:33-35`. Volumes 0, −1.0
(`0xbf800000`) and just below the gate queue nothing; the gate value and 0.5
queue one entry. The queue count is the word at `g_streams`+2·0x1c4+0x1c0 with
`g_streams` at 0x876c10 (`docs/audio-save.md:249`, stream 2 is music). The native
menu report states that its initial request is queued without this check. The
native client should apply the gate at the music service boundary, while retaining
the original request flags; the `0x40` fade-stop flag is absent from this first
queue. This is a concrete discrepancy, not a claim that a speaker played or stayed
silent in a live capture.

## Private structural count

Read-only counts from `BG/DATA` on the private disc, reproduced by
`tools/count_frontend_assets.py BG/DATA` without exporting texture data:
`SOELOGO.LMP` 2 `.tex`; `FRONTEND.LMP` 2; `INTERFAC.LMP` 28; `HEADPIC.LMP` 12
(loaded by `frontend_run` at 0x1e0960); `SELECT.LMP` 263; `SELECT2.LMP` 297;
`SAVEPNT.LMP` 1; `SAVEPNT2.LMP` 1. These total 606 standalone `.tex` entries in the
related lumps. `FONT.LMP`, `PVPFONT.LMP`, `PFONT.LMP`, and `PPVPFONT.LMP` contain 2
`.fnt` entries each (8) with embedded texture pages, not standalone `.tex`.
`PORKO.LMP` and `CREDITS.LMP` contain zero of either. Counts do not prove which
asset is drawn by any state.

## Ranked work for native-menus-layout

Implement in this order; each item names its evidence level.

1. **Menu list and frame geometry** (main, game type, players, mode, difficulty,
   options, pause): anchors, frame wrapper and three expansions, selected-row height
   parity, value-row shift. **Executed**. Measure text width with the original fonts
   before trusting frame widths.
2. **Dispatch by key, plus the main-row destinations** (new game → game type,
   card load, options, credits with its music) and the three navigation sound
   resources. **Executed**. Apply the music-volume gate at the first theme request.
3. **Fonts per batch** (table above): medium for the list, small for the parent
   batch and every card/character batch. **Executed**.
4. **Title and publisher-logo sprites**, including title position `(141,15)`
   layer 5 tint `0x80808080` for states 0–4 only. **Executed**; the title size,
   clip and fade are Unknown and need a displayed capture.
5. **Shared footer and message box** used by character and card screens
   (frames `(21,18,·,355)` and `(300,402,40,32)`, prompt lines `(320,404)` and
   `(320,374)`; message box `(320,212)` width 470). **Executed** with minimum
   widths.
6. **Name entry** anchors, batch colours and clip, then the **ability-point** screen
   (four rows from y=106, 17 apart) and the **character summary** (six rows from
   y=130). **Executed** positions; glyphs and the name-entry insertion cursor
   remain Unknown.
7. **Slot list and card prompts**: up to five rows at y=128–196 in steps of 17,
   four columns at x=77/100/365/487, rectangle 508×19 driven by 0x879e28,
   title `(320,110)`, body `(320,230)`, prompt `(320,320)`. **Executed** with
   authored record bytes and counts 0–6; calling it a highlight is **Inferred**.
   Real card validity, content and widths remain **Unknown**.
8. **Credits**: UTF-16 line pointers, 19-unit spacing, two-pass shadow offset
   (+2,+2), one-unit scroll and music handoff. **Executed** with authored lines;
   resource line counts **Observed**. Check displayed typography later.
9. **Intro movie**: retain the movie path rather than treating it as a `.tex`
   sprite. **Executed** `movie_startGifChain` 0x3201b0 in a zeroed decode
   fixture; **Observed** two MPEG headers, 640×448 and 640×480, in the private
   lump. The chosen entry, decoded-picture upload, crop, timing and audio are
   **Unknown** until the entry argument and displayed run are captured.
10. **Class figure and animation mapping**: investigate the inferred 3D scene
    path and avoid selecting a `HEADPIC` sprite from its count alone. No UI
    sprite among the two followed helpers is **Executed**; the 3D art route
    is **Inferred** and exact model/pose remain **Unknown**.

Do not copy any coordinate not marked Executed in this document into the native
client, and do not remove the native `HOST LAYOUT` label on screens whose exact
assets, font layout, values or state-specific drawings remain Unknown (class
model pose, appearance art, card text and movie presentation).
