# Frontend layout and sound, US v2.00 (SLUS-20973)

**Status: MORE.** This is a function-level capture of the menu list, publisher
logo, pause list and shallow entry paths for the other front-end screens. It
does not yet establish pixel-exact finished screens.
The executable SHA-256 is `292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
The previous flow contract is `t3/research-menus` `099900e`; the primitive
frame/font contract is `t3/research-ui` `3e39392`; the music contract is
`t3/research-audio` `6b08886`. The native front end's missing layout is
described in `open-champions/worktrees/menus/work/loop-menus-r2-report.md`.

## Method and limits

`tools/difftest_frontend_layout.py` runs `frontend_run` (0x1e08f0),
`menuList_draw` (0x1a07c4), `splash_soeLogo` (0x321640), the normal
`pauseMenu_task` (0x18cc08), `nameEntry_draw` (0x22c920),
`credits_load`/`credits_run` (0x223c64/0x223d3c), boot/card (0x32396c,
0x3238f4), intro (0x321788), selection (0x2245b8/0x225478), card
draw dispatch (0x2189e0), and `music_playGlobal` (0x2110e0) under
`tools/ee_emu.py`. It compares the submitted call records with
`tools/ref_frontend_layout.py` at seeds 20973 and 7. The pause fixture uses
the original string comparisons and a card-idle result. Texture lookup,
localization, text width and GPU packet generation are stubbed. Thus the
listed list-frame widths are **minimum widths in this fixture**, not retail
text-width results. The UI's 640×448 coordinates are draw API coordinates;
the plain sprite primitive adds one to y when making its GPU packet
(`research-ui/tools/ref_ui_layout.py`). No screenshot or audio playback was
captured. **Executed**, not Ran.

For `ui_drawFrameImpl` (0x17c118), the first row of a list uses a style-0
`ctile*.tex` cursor frame with tint `0x300000ff`. The backing frame uses
style 2 `tile*.tex` and tint `0x80808080`; the front overlay uses style 0
and tint `0x3f000000`. All nine frame pieces are separate textures in
`INTERFAC.LMP`; their source sizes, clipping and assembly order are the
executed `menu_frame` contract in `research-ui/tools/ref_ui_layout.py`.
The three calls for a four-row ordinary list with selected row 0 are
`(300,259,40,33,layer 7)`, `(292,248,56,122,layer 7)`, and
`(301,260,54,114,layer 6)` respectively. They expand from the frame-wrapper
call `(293,252,54,114,layer 7,0x80808080)`. The selected-row frame's height
is 32 at an even y, 33 at an odd y. The exact per-table calls are asserted
by the difftest; text width can enlarge them.

## Screen captures

All entries below are centered text calls. The first x/y pair is entry 0;
successive y positions are 22 apart. Entry meanings are descriptions, not
copies of localized game strings. The less-used table keys in
`tools/ref_frontend_layout.py` are local geometry aliases; their semantic
names and row meanings remain **Inferred**. Only selected row zero is covered
by the frame model.

| Screen | Executed draw submission | Remaining evidence needed |
|---|---|---|
| Boot/card check | **Executed** 0x32396c requests config load at 0x323974, then installs modal callback 0x3238f4 at 0x323988. The callback calls `save_daemonDraw` at 0x3238fc. Direct entry calls submit no UI primitive with zeroed card state and stubbed callees. | Populate card state and run nested browser/slot paths; capture every prompt and spinner. |
| Publisher logo | `splash_soeLogo` submits `SOELOGO.LMP/soe_splash_url.tex` at `(192,330)` and `soe_splash.tex` at `(64,50)`, both layer 3, tint `0x80808080`, no explicit clip. | Texture sizes and animation/fade across frames. |
| Intro | **Executed** 0x321788 changes display-rate mode at 0x321790, requests stream 0 at 0x3217bc, loads a resource at 0x3217c8, and checks stream readiness at 0x3217d0 and movie completion at 0x32180c. The shallow fixture submits no UI sprite. `docs/mainloop.md:499-503` locates picture decode/upload in the frame path. | MPEG picture, timing, fade and actual soundtrack playback from the movie path. |
| Main menu, state 0 | Four rows at `x=320`, `y=259,281,303,325`. Row destination mapping is **Unknown**; `docs/ui.md:214-223` establishes state meanings, not these four indices. **Executed** title lookup at 0x1e0aac is `FRONTEND.LMP/title.tex`; sprite call 0x1e0ac8 submits `(141,15)`, layer 5, tint `0x80808080`. | Exact title size, background movie/frame, localized glyphs, text-width frame expansion, fade alpha. |
| Game type, state 1 | Two rows at `x=320`, `y=281,303`; offline and network choices. Same title submission. | Same unresolved art/font details. |
| Players, state 2 | Four rows at `x=320`, `y=259,281,303,325`; player-count choices. Same title submission. | Same unresolved art/font details. |
| Mode, state 4 | Two rows at `x=320`, `y=281,303` for the offline table (mission and arena choices). A three-row mode table also has `y=270,292,314`. Same title submission. | Which table is selected for each network setup branch; exact frame width with font loaded. |
| Difficulty, state 3 | Four rows at `x=320`, `y=259,281,303,325`. The parent additionally submits a centered text call at `(320,366)` with layer 6; content and final colour were not established. Same title submission. | Content and colour of the extra line, disabled-entry treatment. |
| Character model/class/appearance/ability points | **Executed** 0x2245b8 registers the selection draw task at 0x2247ac; the 0x225478 task calls selection helpers at 0x2257ac and 0x2258c8. No UI primitive is reached with a zeroed cache and stubbed helpers. Class, appearance and ability-point draw calls are **Unknown**. | Populate model/cache and execute each state; capture 3D model pose, class art, control highlights and point grid. |
| Name entry | **Executed** `nameEntry_draw` 0x22c920 submits centered text calls at `(163,98)` (0x22cba4) and `(233,98)` (0x22ccec), sets layer 6 at `text_begin` 0x22c9c0, draws a rectangle `(0,−9)`–`(0,11)` on layer 6 with colour `0x1e3053` at 0x22d084, and requests text clip `(41,0,640,480)` at 0x22d20c in the zeroed fixture. | Grid glyphs, cursor, accepted-name colours and sound. |
| Options, state 11 | Thirteen rows with first three at `x=297`, remaining ten at `x=320`; `y=89,111,133,...,353`. The first three are value rows (brightness, music, effects). There is no title sprite in this state. Minimum backing-frame call: `(214,78,212,320)`, layer 7, style 2. | Value bars/knobs, option-specific glyphs, current values and fade animation. The earlier music slider timing contract is in `docs/spec/music-volume.md` on the combat-constructors branch. |
| Load/save | **Executed** `save_daemonDraw` 0x2189e0 pumps the queue at 0x218a14. State 3 dispatches save at 0x218a48; state 4 dispatches load at 0x218a68. `memcard_slotList` 0x21c3a4 begins a layer-6 text batch with colour `0x001e6464` at 0x21c404 in the zeroed fixture. File-list geometry is **Unknown**. | Slot/card state fixtures with resources, file-list positions, error dialogs and sounds. |
| Credits, state 15 | **Executed** `credits_load` 0x223c64 then `credits_run` 0x223d3c submits `text_begin` at 0x223e40 on layer 7, colour `0x80000000`. No lines appear with the loader stubbed. The frontend title sprite is absent at state 15 in this fixture. | Credits data layout, scroll positions and speed, images and exit sound. |
| Pause | Normal offline `pauseMenu_open` 0x18e334 and `pauseMenu_task` 0x18cc08 enabled table rows 0,1,2,5,8 in the synthetic no-level fixture. Five centered calls: `x=320`, `y=179,201,223,245,267`. The backing-frame call is `(292,168,56,144)`, layer 7, style 2, tint `0x80808080`; cursor is `(300,179,40,33)`, layer 7, style 0, tint `0x300000ff`; front overlay `(301,180,54,136)`, layer 6, style 0, tint `0x3f000000`. A subsequent `text_begin` uses the word at `0x4f7100`, layer 7, colour `0x80464646`. | Game-scene background, font glyph placement, conditional net/debug rows, fade and prompts. |

### Additional fixture boundaries

The zeroed **name-entry** fixture submits three more wide-text calls at
`(81,138)`, `(81,158)` and `(81,178)` (0x22ce4c, 0x22ceb0, 0x22cf14), a
wrapped-text call at `(41,38)` (0x22d12c), and an ASCII-text call at
`(41,72)` (0x22d26c). Its `text_begin` colours are `0x585e5d` at
0x22c9c0, `0x316864` at 0x22d0e4, and `0x585e5d` again at 0x22d198,
all layer 6. The rectangle at 0x22d084 is only a zero-width call in this
fixture; a final visible cursor cannot be inferred. The clip call at
0x22d20c requests right/bottom `(640,480)`; `text_setClip` 0x1803e0
clamps to the 640×448 UI bounds (`symbols/engine.tsv:166`).

The **card** draw dispatcher tests state `−1,0,1,3,4,5,6,9,10` in the
difftest. Its cases are direct calls only; state 0/1 config, 3 save, 4 load,
5/6 config/end-game save, 9 import and 10 options follow the mapping in
`docs/audio-save.md:168-171`. The zeroed slot-list entry has a text batch
but no file rows. `memcard_browser` 0x219b90 and
`memcard_tickSpinner` 0x222e10 need active card and asset state for their
draw lists. The original font word, file row geometry, cursor, highlight,
sprite texture/size/clip/tint/layer, timing and sounds of those states are
**Unknown**.

The **intro** picture is decoded and uploaded from `movie_update` in the
frame path (`docs/mainloop.md:499-503`), so the sprite API capture does not
measure its texture size, tint or clip. The **character** fixture has no
populated selection cache, so class, appearance, ability-point, 3D model,
cursor and highlight geometry, fonts, colours, animation and sounds remain
**Unknown**. The **credits** resource loader is stubbed, leaving scroll
position/speed, line colours and any imagery **Unknown**; only its opening
font batch is executed. No move/select/back/error sound ID is established
for boot/card, intro, character, name, load/save or credits. This is a
fixture limit, not evidence that their real screens are silent.

The normal front-end list starts from the font word at `0x4f7100` in the
parent `text_begin` at 0x1e0dcc, layer 7; **Executed** colour in the zeroed
capture is `0x64464646`, asserted for states 0–4 and 11 at both seeds.
Alpha must be tested at real animation times. The list's
own `text_begin` is layer 7 but its colour depends on initialized state.
`research-ui/docs/formats/ui-fonts.md` identifies the two fonts in
`FONT.LMP` and their embedded glyph pages. A system font substitution cannot
verify the original character widths or highlight fit.

## Menu sound and first theme

**Executed:** an actual move in the main list looks up
`FX.LMP/menu_main_toggle.anm` and calls `sound_playOnObject` 0x214230.
Choosing the first entry looks up `menu_main_accept.anm`; cancel from the
game-type list looks up `menu_main_back.anm`. Cancel on the main list had no
transition and no sound in this fixture. These IDs are resource names;
sample bytes, mix level and speaker output were not captured. Other screens'
move/select/back/error paths remain **Unknown**. No general error sound ID
is established by this test.

**Executed:** `frontend_run` makes its initial theme request with flags 1 or
5 at 0x1e09b0/0x1e09c4. `music_playGlobal` gates the resulting queue at
music volume `0x3d4ccccc` (about 0.05), also traced in
`t3/research-combat-ctors` `docs/spec/music-volume.md:33-35`. Volumes 0,
−1 and just below the gate
queue nothing; the gate value and 0.5 queue one entry. The native menu report
states that its initial request is queued without this check. The native
client should apply the gate at the music service boundary, while retaining
the original request flags; the `0x40` fade-stop flag is absent from this
first queue. This is a concrete discrepancy, not a claim that a speaker
played or stayed silent in a live capture.

## Private structural count

Read-only counts from `BG/DATA` on the private disc, reproduced by
`tools/count_frontend_assets.py BG/DATA` without exporting texture data:
`SOELOGO.LMP` 2 `.tex`; `FRONTEND.LMP` 2; `INTERFAC.LMP` 28;
`SELECT.LMP` 263; `SELECT2.LMP` 297; `SAVEPNT.LMP` 1; `SAVEPNT2.LMP` 1.
These total 594 standalone `.tex` entries in the related lumps. `FONT.LMP`,
`PVPFONT.LMP`, `PFONT.LMP`, and `PPVPFONT.LMP` contain 2 `.fnt` entries each
with embedded texture pages, not standalone `.tex`. `PORKO.LMP` and
`CREDITS.LMP` contain zero `.tex`. Counts do not prove which asset is drawn
by any state.

## Ranked work for native-menus-layout

1. Shared menu list geometry, frame primitive and original font measurement:
   main, game type, players, mode, difficulty, options and pause all use it.
2. Theme volume gate and the three verified main-list navigation resource
   IDs. The gate changes silent-volume behavior at the first theme request;
   other screen sounds have no verified IDs yet.
3. Title and publisher-logo sprite submissions through the original texture
   decoder, preserving their verified positions, layers and tints. Measure
   texture sizes, clips and fades in a displayed capture.
4. Name-entry anchors, text batch colours and clip, then options values.
   The zero-width name rectangle is fixture-specific; populate the name
   state before implementing its visible cursor or grid.
5. Character class/appearance/ability points, card slot screens and credits
   after populated cache/card/credits fixtures yield complete draw lists.
6. Intro movie presentation after its decode/upload path yields frame size,
   timing and audio synchronization evidence.

Do not remove the native `HOST LAYOUT` label on screens whose exact assets,
font layout, values or state-specific drawings remain unresolved.
