# Frontend layout and sound, US v2.00 (SLUS-20973)

**Status: MORE.** This is a function-level capture of the menu list, publisher
logo and pause list. It does not yet establish pixel-exact finished screens.
The executable SHA-256 is `292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
The previous flow contract is `t3/research-menus` `099900e`; the primitive
frame/font contract is `t3/research-ui` `3e39392`; the music contract is
`t3/research-audio` `6b08886`. The native front end's missing layout is
described in `open-champions/worktrees/menus/work/loop-menus-r2-report.md`.

## Method and limits

`tools/difftest_frontend_layout.py` runs `frontend_run` (0x1e08f0),
`menuList_draw` (0x1a07c4), `splash_soeLogo` (0x321640), the normal
`pauseMenu_task` (0x18cc08), and `music_playGlobal` (0x2110e0) under
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
copies of localized game strings.

| Screen | Executed draw submission | Remaining evidence needed |
|---|---|---|
| Boot/card check | `mainloop_runBootCardCheck` 0x32396c starts a modal callback; the zeroed card fixture submitted no drawing. | Run `mainloop_bootCardStep` and `memcard_browser` with card states and loaded resources; capture every prompt and spinner. |
| Publisher logo | `splash_soeLogo` submits `SOELOGO.LMP/soe_splash_url.tex` at `(192,330)` and `soe_splash.tex` at `(64,50)`, both layer 3, tint `0x80808080`, no explicit clip. | Texture sizes and animation/fade across frames. |
| Intro | `splash_introMovie` 0x321788 calls the movie path and a stream path; it submitted no UI sprite under the fixture. | MPEG picture, audio and timing from the movie path. |
| Main menu, state 0 | Four rows at `x=320`, `y=259,281,303,325`; indices 0–3 lead to new-game, load, options and credits flows. Title sprite lookup is `FRONTEND.LMP/title.tex`; submission `(141,15)`, layer 5, tint `0x80808080`. | Exact title size, background movie/frame, localized glyphs, text-width frame expansion, fade alpha. |
| Game type, state 1 | Two rows at `x=320`, `y=281,303`; offline and network choices. Same title submission. | Same unresolved art/font details. |
| Players, state 2 | Four rows at `x=320`, `y=259,281,303,325`; player-count choices. Same title submission. | Same unresolved art/font details. |
| Mode, state 4 | Two rows at `x=320`, `y=281,303` for the offline table (mission and arena choices). A three-row mode table also has `y=270,292,314`. Same title submission. | Which table is selected for each network setup branch; exact frame width with font loaded. |
| Difficulty, state 3 | Four rows at `x=320`, `y=259,281,303,325`. The parent additionally submits a centered text call at `(320,366)` with layer 6; content and final colour were not established. Same title submission. | Content and colour of the extra line, disabled-entry treatment. |
| Character model/class/appearance/ability points | `playerSel_start` 0x2245b8 and `playerSel_task` 0x225478 ran with synthetic state. The latter reached selection helpers but no UI draw call without a populated selection cache. | Populate model/cache and execute each state; capture 3D model pose, class art, control highlights and point grid. |
| Name entry | `nameEntry_draw` 0x22c920 submitted centered text calls at `(163,98)` and `(233,98)` and a layer-6 rectangle in the zeroed fixture. Its other calls require initialized selection data. | Grid glyphs, cursor, clipped regions, accepted-name colours and sound. |
| Options, state 11 | Thirteen rows with first three at `x=297`, remaining ten at `x=320`; `y=89,111,133,...,353`. The first three are value rows (brightness, music, effects). There is no title sprite in this state. Minimum backing-frame call: `(214,78,212,320)`, layer 7, style 2. | Value bars/knobs, option-specific glyphs, current values and fade animation. The earlier music slider timing contract is in `docs/spec/music-volume.md` on the combat-constructors branch. |
| Load/save | `save_daemonDraw` 0x2189e0 and `memcard_browser` 0x219b90 ran with zeroed card state; no complete browser list was submitted. | Slot/card state fixtures with resources, file-list positions, error dialogs and sounds. |
| Credits, state 15 | `credits_load` 0x223c64 then `credits_run` 0x223d3c submitted `text_begin` on layer 7, colour `0x80000000`, but no lines because the resource loader was stubbed. The front-end title sprite is absent. | Credits data layout, scroll positions and speed, images and exit sound. |
| Pause | Normal offline `pauseMenu_open` 0x18e334 and `pauseMenu_task` 0x18cc08 enabled table rows 0,1,2,5,8 in the synthetic no-level fixture. Five centered calls: `x=320`, `y=179,201,223,245,267`. The backing-frame call is `(292,168,56,144)`, layer 7, style 2, tint `0x80808080`; cursor is `(300,179,40,33)`, layer 7, style 0, tint `0x300000ff`; front overlay `(301,180,54,136)`, layer 6, style 0, tint `0x3f000000`. A subsequent `text_begin` uses the word at `0x4f7100`, layer 7, colour `0x80464646`. | Game-scene background, font glyph placement, conditional net/debug rows, fade and prompts. |

The normal front-end list starts from the font word at `0x4f7100` in the
parent `text_begin`, layer 7; its colour in the zeroed capture was
`0x64464646`, so alpha must be tested at real animation times. The list's
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
music volume `0x3d4ccccc` (about 0.05). Volumes 0 and just below the gate
queue nothing; the gate value and 0.5 queue one entry. The native menu report
states that its initial request is queued without this check. The native
client should apply the gate at the music service boundary, while retaining
the original request flags; the `0x40` fade-stop flag is absent from this
first queue. This is a concrete discrepancy, not a claim that a speaker
played or stayed silent in a live capture.

## Private structural count

Read-only count of related entries in the private disc, without exporting
texture data: `SOELOGO.LMP` 2 `.tex`; `FRONTEND.LMP` 2 `.tex`;
`INTERFAC.LMP` 28 `.tex`; `FONT.LMP`, `PVPFONT.LMP`, `PFONT.LMP`, and
`PPVPFONT.LMP` 2 `.fnt` each with embedded texture pages, not standalone
`.tex`. This gives 32 standalone related `.tex` entries across the first
three lumps and 8 font entries. `PORKO.LMP` and `CREDITS.LMP` have zero
`.tex` entries. These are counts, not proof of which asset every state uses.

## Native implementation order

1. Shared menu list geometry, frame primitive and original font measurement:
   main, game type, players, mode, difficulty, options and pause all use it.
2. Theme volume gate and the three verified navigation resource IDs. The
   audio gate changes silent-volume behavior at the first theme request.
3. Title and logo sprites through the original texture decoder; verify their
   sizes and fade in a displayed capture.
4. Options values and character creation, using populated state fixtures.
5. Card slot screens, credits and intro movie after their data/decoder paths
   can produce a full draw list.

Do not remove the native `HOST LAYOUT` label on screens whose exact assets,
font layout, values or state-specific drawings remain unresolved.
