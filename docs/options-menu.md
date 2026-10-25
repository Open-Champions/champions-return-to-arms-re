# Options and settings menus — SLUS-20973 US v2.00

**Status: MORE.** The list records, value edits and front-end exit route below were
executed with `tools/ee_emu.py` at seeds 20973 and 7. This is function-level
evidence, not a Play! or console run. The executable is pinned by SHA-256 in
`tools/difftest_options_menu.py`. Texture pixels, localized glyphs, the full
controls sub-screen and memory-card I/O remain open.

## Evidence and reuse

- **Executed:** `tools/difftest_options_menu.py` runs the original list handler
  0x1a01d0, parent `frontend_run` 0x1e08f0 and config functions 0x1e6238 /
  0x1e6650. Its reference data is `tools/ref_options_menu.py`; it saves no game
  bytes. The independent layout, menu, audio and save difftests cited below were
  rerun for this branch.
- **Observed:** the 16-byte menu records at 0x4f6e88 (front end) and 0x44f218
  (pause), and addressed code/data facts already documented in
  `docs/issues/sync-breakers.md` §7 and `t3/research-saves` `docs/save-format.md`.
- **Inferred** and **Unknown** are used for meanings and display behavior not
  established by those executions. `tools/ee_emu.py` cannot show final pixels,
  audio output or a successful memory-card transaction.
- Prior contracts: `t3/research-menus` `docs/ui.md` and
  `tools/difftest_menus.py`; `t3/research-menus-layout`
  `docs/frontend-layout.md` and its layout, screens and art difftests (the
  requested menu-art follow-up lives on that branch); `t3/research-audio`
  `docs/audio-playback.md`; `t3/research-saves` `docs/save-format.md`.

## Reachability and records

**Executed** on the front end: accepting main row 2 calls `config_backup`
0x1e6428 and enters state 11 with table 0x4f6e88 (earlier
`difftest_frontend_layout.py`, `main_accept`). Accepting row 3 of that options
table enters state 12, the four-player controller-selection list at 0x4f6fc8.
Cancel from state 11 enters state 14, the save-choice state. In state 14,
0x1e0bac calls `config_commitOptions(0,1,0)` to query differences. Accept
calls `config_commitOptions(0,0,0)` at 0x1e0ca4; cancel calls
`config_commitOptions(0,0,1)` at 0x1e0cbc, which commits in memory without
requesting a card save. These paths returned to front-end state 0 in the
synthetic fixture. The cancel-without-changes decision and exact modal art
need a fully initialized screen fixture.

**Observed in addressed code, not executed by this fixture** on pause: the
normal table 0x44f3b8 has an Options row at index 5. `pauseMenu_open`
0x18e334 installs that table at 0x44fa70; `pauseMenu_task` 0x18cc08 in
state 5 has the list draw and run call sites at 0x18d5cc and 0x18d720,
with table 0x44f218 and raw pad 0x4028d0. The committed list-handler
probe calls 0x1a07c4 and 0x1a01d0 directly; its input uses the front-end
pad 0x41bfd8. It does not prove the pause state transition or pad routing.
Existing static analysis identifies the pause exit query
and commit at 0x18d180, 0x18d2c8 and 0x18d2e0
(`docs/issues/draw-sim-leaks.md` U1). The pause list's final communications
row has no equivalent in the front-end list. Its destination is **Unknown**.
The controls row is disabled while in a net game (`pauseMenu_task` 0x18cc08,
`docs/issues/draw-sim-leaks.md` U1).

Both lists have the same first thirteen records. The record values below
are **Observed** and the first thirteen are asserted by the committed
fixture. The final pause record's key, kind 0 and null value pointer are
also asserted; its action destination remains **Unknown**.

| Row | Lookup key | Kind | Live value / use |
|---:|---|---:|---|
| 0 | `menu_bright` | 4 | float brightness 0x44fd80 |
| 1 | `menu_music` | 4 | float music volume 0x4f8944 |
| 2 | `menu_sfx` | 4 | float effects volume 0x4f8940 |
| 3 | `menu_controls` | 0 | opens controller configuration; no direct value pointer |
| 4 | `menu_combatCam` | 3 | combat camera 0x4f845c |
| 5 | `menu_reverseYaw` | 3 | reverse yaw 0x4f8460 |
| 6 | `menu_vibration` | 3 | pad vibration 0x41bfb0 |
| 7 | `menu_stereo` | 3 | stereo 0x4f8948 |
| 8 | `menu_blood` | 3 | blood/decal detail 0x44fdc0 |
| 9 | `menu_subtitles` | 3 | subtitles 0x44fcf4 |
| 10 | `menu_damagedisplay` | 3 | damage numbers 0x44fcf8 |
| 11 | `menu_chat` | 3 | chat 0x50391c |
| 12 | `menu_markers` | 3 | player markers 0x4f8458 |
| pause 13 | `menu_comm` | 0 | communications sub-screen; destination **Unknown** |

The keys are short resource identifiers, not rendered game text. They are
addressed in the executable at the pointer in each record. Kind 4 is a float
slider, kind 3 a binary toggle, and kind 0 an action; the type and pointer
are the second and third words of each record.

**Executed** for each slider at both tables: pad-repeat right bit 0x2000
adds the FPU result of about 1/120; left bit 0x8000 subtracts it. Inputs
0 and 1 clamp at their respective boundaries. From 0.5, right yields
IEEE word `0x3f022222`; left yields `0x3efbbbbb`. The test also covers
0→right, 0→left, 1→right and 1→left on all three sliders. The exact
intermediate bit pattern follows the PS2 FPU and should not be replaced
by an arbitrary UI percentage increment. A kind-3 accept press (0x40)
sets 0→1, 1→0 and nonzero 2→0 on all nine toggles. Left/right presses
also toggle type 3 in the original handler; a native UI should keep
those inputs. No other legal range is established for a loaded config
file; malformed values were not validated by this screen probe.

**Difficulty is a separate setup screen**, not one of these option records.
Front-end state 3 uses the four-row table at 0x4f6e38, whose lookup keys
are `menu_easy2`, `menu_normal2`, `menu_hard2`, `menu_harder2`.
`g_difficultyIdx` 0x4f719c is stored in a slot save at offset +0x6c
(`t3/research-saves` `docs/save-format.md`); the four row-to-index
transitions were not established by this options fixture. The native port
must keep difficulty in game setup and slot state, rather than put it in
the 760-byte options image.

## Layout, typography and art

**Executed** in `menuList_draw` 0x1a07c4, using a zero text-width callee:
`difftest_options_menu.py` compares all row anchors and all three submitted
frames' geometry, layer, tint and style on each table and seed.

| Screen | Text anchors | Frames submitted to 0x17c118 |
|---|---|---|
| Front-end options | Rows 0–2: x=297; rows 3–12: x=320. y=89+22r | selected row 0 `(180,89,280,33)` layer 7 style 0; backing `(214,78,212,320)` layer 7 style 2; front overlay `(223,90,210,312)` layer 6 style 0 |
| Pause options | Rows 0–2: x=297; rows 3–13: x=320. y=80+22r | selected row 0 `(180,80,280,32)` layer 7 style 0; backing `(214,69,212,342)` layer 7 style 2; front overlay `(223,81,210,334)` layer 6 style 0 |

The selected frame tint is `0x300000ff`, the backing tint
`0x80808080`, and the overlay tint `0x3f000000`. The first three
rows reserve width for values; the format and glyphs of those values
remain **Unknown** because resource and text-width callees are stubbed.
The shared list begins a medium-font batch from `g_fontMedium` 0x4f7100,
layer 7 (`t3/research-menus-layout` `font_uses`). Its front-end parent
adds a small-font batch at 0x1e0dcc; pause adds a medium-font batch at
0x18d5e8. The frame texture family is **Inferred** from the formatted
`INTERFAC.LMP` identifiers and `t3/research-ui` frame research: style 0
uses `ctile*.tex`, style 2 uses `tile*.tex`. The font atlas, localized
words, full frame expansion after text measurement, alpha over time and
pixel appearance are **Unknown**. The list fixture submits no separate
slider texture; whether resource helpers produce one was not followed.

## Applying values and persistence

**Executed/Observed** `config_setDefaults` 0x1e6238 sets brightness, music
and effects to 0.5; stereo, vibration, subtitles, damage numbers,
markers and combat camera to 1; reverse yaw and blood to 0. It fills
four controller rows of nine button masks according to scheme byte
0x41b69c. Scheme 1's first row is `0x40,0x20,0x10,0x80,0x08,0x02,1,0x400,0x04`;
scheme 0 swaps the first three. See `t3/research-saves`
`docs/save-format.md` for the whole 760-byte synthetic image.

The live variables are read by their owning systems:

| Setting | Addressed application path |
|---|---|
| Music | `frontend_run` calls `music_applyVolume` 0x215e78 after the options handler at 0x1e10c8. `music_updateDucking` 0x212500 scales music channel 2 by 0x4f8944; `music_playGlobal` gates new queues below float word `0x3d4ccccc` (`t3/research-audio` `docs/audio-playback.md`). |
| Effects and stereo | `voice_setVolume` 0x213a78 scales effects by 0x4f8940; mono averages left/right. `audio_sendVolumes` 0x2166e0 sends channel volumes and stereo to the IOP (`symbols/audio-save.tsv`). |
| Brightness | The display path reads 0x44fd80 (`docs/issues/sync-breakers.md` §7); exact transfer curve **Unknown** here. |
| Controls | Per-slot button tables 0x41b980…0x41ba30 feed player simulation. The controller sub-screen is `frontend_openControlConfig` 0x1e2510 / `frontend_controlConfigRun` 0x1e259c; its complete glyph and remap flow is **Unknown**. |
| Camera | `Camera_followRotateInput` reads 0x4f845c and 0x4f8460; camera yaw enters the local input record (`docs/issues/sync-breakers.md` §7). |
| Vibration | Pad code reads 0x41bfb0. Exact motor magnitudes **Unknown** here. |
| Blood, subtitles, damage, markers, chat | Addressed readers are the damage/decal paths, `cut_setup`/`cut_drawFrame`, `damage_apply`/`FlyingText_draw`, `Player_drawMarker`, and text-chat task respectively (`docs/issues/sync-breakers.md` §7). |

**Executed** config query/commit: `config_commitOptions` 0x1e6650
detects a changed music scalar without altering the 760-byte saved image
in query mode; commit copies the changed scalar to image offset +8;
the next query reports zero differences. Changing each of the twelve
direct table values, including chat, adds one to the query count.
The commit copies saved controller rows
into the per-slot button tables, even in a net game, when any tracked
option changes (`docs/issues/draw-sim-leaks.md` U1); this is a real
native parity and multiplayer hazard.

**Observed** in `t3/research-saves` `docs/save-format.md`: the options
image is exactly 0x2f8 (760) bytes at `g_savedConfig` 0x4f8f38, without
a checksum. Scalars occupy +4…+0x30, four 9-word control rows occupy
+0x34…+0xc3, chat is the word at +0xc4, voice settings occupy
+0xc8…+0xd4, and profile variables start +0xf8. The earlier save
research left the +0xc4…+0xd4 pairing **Unknown**; the new
`config_commitOptions` probes resolve it: live chat 0x50391c → +0xc4,
voice 0x505af0 → +0xc8, 0x505af4 → +0xcc, 0x505b00 → +0xd0, and
0x505afc → +0xd4. For each, changing only that global and committing
changed the corresponding image word. The memory-card config-save state 5 queues a 760-byte write from
that address (`memcard_saveConfigScreen` 0x21f4a4). The config load
states are 0 and 1; the options screen's copy into live globals is at
0x222d5c (`docs/issues/sync-breakers.md` §7). The actual card open
uses a pointer at 0x88d418 while `save_init` also constructs a config
name at 0x88d438. Which name is opened after browser setup remains
**Unknown**; no real card was accessed. Slot-save difficulty at +0x6c
is separate from this image.

## Ordered native port work

1. Model the two menu tables and key-based actions, including front-end
   state 11→12 controls and state 11→14 save choice. Execute the pause
   Options transition in an isolated fixture before wiring its state-5
   table/pad routing; preserve net-game controls disabling. Model the extra
   pause communications row as a kind-0 action with unknown destination.
2. Reproduce the list text anchors, three frame calls, layer/tint ordering,
   medium/small font batches and localization lookup; resolve actual
   frame textures and value formatting from owned art in an isolated
   visual fixture before claiming pixel parity.
3. Implement 1/120 float-slider edits with boundary clamp and binary
   toggles, then wire live brightness, audio, pad, camera and display
   readers. Keep difficulty as its separate setup/slot-save route.
4. Implement the controller mapping screen and nine masks per local
   port; keep online per-slot maps separate from local saved maps.
5. Implement default, backup, query, commit and restore of the 760-byte
   config image. Preserve the front-end state-14 query, accept/cancel
   commit call sites, state-0 return and accept-only card-save request;
   execute the pause exit route separately. Then implement the card
   load/save state machine. Resolve the config filename with an
   executed browser/card fixture before native persistence is called
   equivalent.
6. Verify displayed pixels, audio output, controls, card round-trip and
   online option changes in an integrated runtime. This function-level
   research alone does not establish those outcomes.

## Validation (2026-10-23)

All checks ran serially with `PYTHONDONTWRITEBYTECODE=1` and the pinned
owned executable. `python3 tools/difftest_options_menu.py
<owned-executable>` passed 154 checks on
each of seeds 20973 and 7. The sibling difftests passed:
`difftest_menus.py` 6 properties, `difftest_frontend_layout.py` 236
checks, `difftest_frontend_screens.py` 204 checks,
`difftest_frontend_art.py` 124 checks, `difftest_audio.py` 23
properties and `difftest_save.py` 26 properties. The full current-head
unit command `python3 -m unittest discover -s tools -p 'test_*.py'`
passed 652 tests. The logs are ignored local files under `local/`.
The 154-check rerun asserts both state-14 query/choice call pairs, state-0
return, accept-only card-save request, full row anchors and frame arguments;
the pause parent transition remains an unexecuted static observation.
