# Spec: UI text gaps (fields, calls, seed draws, constants)

SLUS-20973 v2.00. This is the table form of [../ui-text-gaps.md](../ui-text-gaps.md), which
has the evidence and the ranking.

- Model: `tools/ref_ui_text_gaps.py`.
- Difftest: `tools/difftest_ui_text_gaps.py`: 8 properties, seeds 20973 and 7, all PASS
  when it was run; it needs the disc and an emulator, so the PASS is not reproducible from this
  repository alone.
- Status words: O observed, E executed, I inferred.
- "Seed draws" lists reads or writes of `g_cosmeticSeed` 0x404460, `g_randSeed` 0x404464
  and 0x404468. The first 80 calls of each property were recorded (20 for the chime).

## Fields

| Address | Type | Name | Written by | Read by | Status |
|---|---|---|---|---|---|
| 0x506060 | float[4] | `g_uiPulse` | `ui_startPulse` 0x320ea4 (2.0); step 13 (decay) | `help_task` colours | E |
| 0x506070 | float[4] | `g_uiFadeIn` | `ui_restartFadeIn` 0x320ec4 (0.0); step 13 (+0.12, clamp 1.0) | `dialog_runTask` gate, `dialog_drawTask` alpha | E |
| 0x41b69c | s8 | button layout | data value 1; no store found | `config_setDefaults` 0x1e6238, `game_initCamera` 0x1e6b68 | O, E |
| 0x41b978 | s32 | confirm glyph code | `game_initCamera` (0x7e for layout 1, 0x7b for layout 0) | 23 functions; `"%c"` in `help_task` and `dialog_drawTask` | O, E |
| 0x41b97c | s32 | the other glyph | `game_initCamera` (0x7b / 0x7e) | medal prompt, menus | O, E |
| 0x41bfbc | s32 | `g_btnConfirmMask` | data 0x40; `game_initCamera` (0x40 / 0x20) | `help_task` confirm, dialog | O, E |
| 0x41bfb8 | s32 | other mask | data 0x20; `game_initCamera` (0x20 / 0x140) | menus | O, E |
| 0x41b960–0x41b974 | s32 × 6 | more layout words | `game_initCamera` (section 7 of the main doc) | menus | E |
| 0x4f66cc | s32 | help close delay | open 90, close 60, −1 per call while > 0 | `help_task` | E |
| 0x41b928 | s8 | help box open | `hud_showHelpMessage`, `help_task` | `help_task` | E |
| 0x86aa64 / 0x86aa68 | ptr | help title / body | `hud_showHelpMessage` | `help_task` | E |
| 0x44fda4, 0x44fe10, 0x44fe0c | s32 | display-list free count inputs | renderer | `help_task` gate (≥ 3,000) | E |
| 0x4f7100 / 0x4f7104 | ptr | gamefontmed / gamefontsmall | startup 0x323f64–0x323f94 | help box / bust caption and compass label | O, E |
| 0x4f66d4 | s8 | bust shown (lease) | `hud_setBust` 5, `hud_run` −1 | `hud_drawBust` | E |
| 0x4f66a9 | s8 | bust hide latch | `hud_tickMessage`, `hud_spellSelect`; cleared by `hud_drawBust` | `hud_drawBust` | E |
| 0x4f66d0 | float | bust fade | `hud_drawBust` (±0.08445, clamp 0..1) | `hud_drawBust` | E |
| 0x86ab30 / 0x86ab34 | s32 | bust value / maximum | `hud_setBust`; value clamped to ≥ 0 by `hud_drawBust` | `hud_drawBust` | E |
| 0x4f6b48 | char[40] | bust portrait name | `hud_setBust` | `res_find("bust.lmp", …)` | E |
| 0x44fdcc | s32 | `g_simFrame` | engine | bar frame `(t / 2) % 4` | E |
| 0x44fdb4 | s32 | frame (half-rate) mode | `gfx_setDisplayRateMode` 0x19dd48 | `ui_emitSpriteQuad` | E |
| 0x44fdd4 | s8 | field mode | data 1; 1 at 0x322a5c, 0x3236fc, 0x32382c; 0 at 0x19ded8 | `ui_emitSpriteQuad` | O, E |
| 0x83d258 | s32 | display field | vblank | `gfx_displayField` 0x19d9e4 (bit 0) | O |
| 0x4f8424 | s32 | compass gate | | `hud_drawCompass` | E |
| 0x4f841c | s32 | compass player slot (−1 none) | | `hud_drawCompass` | E |
| 0x4d8af0 + 0x4c30·slot + 0x43d8 | ptr | the player's object | | `hud_drawCompass` (+0x10, +0x14) | E |
| 0x4f66d5 | s8 | compass shown (lease) | `hud_setCompassTarget` 5, `hud_run` −1 | `hud_drawCompass` | E |
| 0x86a8f0 | float[2] (of 3) | compass target | `hud_setCompassTarget` | `hud_drawCompass` | E |
| 0x86aaf0 | u16[32] | compass label | `hud_setCompassTarget` | label | E |
| 0x41c168 | u32 | model draw flags (0x20: depth ALWAYS) | 0x179890 (\|= 0x20), `model_resetDrawState` (0) | `model_draw` 0x177b34 | E (state), O (meaning) |
| 0x4039a0 / 0x4039a4 | s32 | light flag / light depth counter | 0x14a0b8 (1), 0x14a138 (+10), `light_resetObjectLight` | lights | E |
| 0x871a68 + 0x4c·i | slot × 32 | `g_soundSeqs` | `sound_playOnObject`, `soundSeq_updateAll` | | E |
| slot +0x04 / +0x06 / +0x08 | s8 / u16 / track | track count / state flags / track (clip +0x00, time +0x18, cursor +0x1e) | | | E |
| slot +0x28 / +0x2c / +0x38 | ptr / float[3] / u16 | object handle / position / serial | | | E |
| slot +0x3a / +0x3b / +0x3c / +0x40 | s8 / s8 / s8 / float | no position / plays while frozen / released / volume | | | E |
| clip +0x40 | s32 | sequence duration (run-time) | `anm_bindSounds` | released restart | E |
| 0x872880 + 0x14·v | voice × 43 | +4 flags (4 in use, 0x10 loop), +6 owner, +8 generation | | free path | E |
| 0x4f8a00 / 0x4f8a04 | s32 / float | current sound slot / volume | `soundSeq_updateAll` (−1 / 1.0 after) | `animsound_*` | E |
| 0x8e2d68 / 0x8e2cdc | u16[] / s32 | dialog name text / length | `dialog_onMsg` 0x22f234 / 0x22f28c | `dialog_drawTask` | E |
| 0x41bfa8 / 0x7caea0 | s32 / 16 × u16[20] | miss ring index / ring | `text_lookup` | | E |

## Calls

| Function | Arguments → result | Calls out | Seed draws | Status |
|---|---|---|---|---|
| session step 13, 0x323448–0x3234d0 | per displayed frame, after `gfx_endFrame` | none | none | E `ui.ramps` |
| `game_initCamera` 0x1e6b68, slice 0x1e6bb4–0x1e6ca8 | layout byte → layout words | none in the slice | none | E `layout.glyph` |
| `pad_buttonMaskToGlyph` 0x1eacb8 | mask → glyph code or −1 | none | none | E |
| `help_task` 0x1dcc78 (draw task 50) | state → draws, pause, close | `color_scale` 0x19ecac ×4, `text_begin`, `text_drawWideCentered`, `text_setColor` ×2, `text_drawWrapped`, `sprintf`, `text_lookup` ×2, `text_widthWide`, `text_drawAscii`, `text_drawWide`, `text_end`, 0x17fbb8 → 0x17c118, 0x17c118, `script_runPostAction` 0x1edac0, `net_isLocalSlot` 0x13e150, `hudmsg_sendMenuState` 0x1de0dc | none in the function. `script_runPostAction` runs script code | E `help.task` |
| `hud_drawBust` 0x1dfb6c (HUD draw step 5) | state → draws | `text_begin`, `text_drawWrapped`, `text_setColor`, `sprintf`, `text_drawAsciiCentered` 0x181af8, `text_end`, `res_find` ×3–4, 0x17fb88, 0x17fb68 ×3 | none | E `bust.draw` |
| `ui_emitSpriteQuad` 0x17ab50 (dl, tex, x, y, u0, v0, u1, v1) | → 4 or 11 GIF qwords | `gfx_displayField` 0, 1 or 2 times | none | E `sprite.fields` |
| `hud_drawCompass` 0x1df720 (HUD draw step 6) | state → two model draws and a label | `dialog_isOpen`, 0x165c08, 0x165fc0, 0x165680, 0x165b10, 0x166798, 0x163000, 0x179890, `res_find` ×4, `model_draw` 0x1779b0 ×2, 0x179978 ×2, 0x14a0b8, 0x14a138, 0x148340, `text_begin`, 0x181530, `text_end` | none | E `compass.draw` |
| `soundSeq_updateAll` 0x2147c0 (from `sound_update` 0x212670, per displayed frame) | slots → freed slots, stops, steps | `game_isFrozen` 0x1ebdf8, `sound_stop` 0x213ea0, `anim_advanceUnitSpeed` 0x1709d8 → `animsound_fireRange` 0x16d558 | none in the loop. `animsound_fireRange` → `animsound_play` 0x16d360 draws `g_cosmeticSeed` (O, `docs/spec/animation.md` 6) | E `sound.seqUpdate` |
| `sound_setPlaysWhileFrozen` 0x216ad0 (handle) | slot +0x3b = 1 for a valid handle | none | none | O |
| `dialog_onMsg` 0x22f208–0x22f28c (message 0) | speaker → name text | `obj_getProp` 0x14f4c0, `text_lookup` 0x173c84, `wstr_copy` 0x19e854, `creatures_freezeAll` 0x11a450, `dialog_clearText` 0x230fe4, `wstr_len` 0x19e994 | none | E `dialog.showName` |
| `obj_getProp` 0x14f4c0 (obj, key, nth) | → pointer after `key=`, or 0; lowercases the key in place | 0x3b8dc4, 0x3b91d8 | not watched | O |

## Constants

| Value | Meaning | Address of the operand or word |
|---|---|---|
| 0x3df5c28f (0.12) | fade step per displayed frame | 0x3234ac / 0x3234b0 |
| 0x3f800000 (1.0) | fade clamp, pulse floor | 0x323468 |
| 0x3f4ccccc (0.8) | pulse decay of the excess | 0x323484 / 0x323488 |
| 0x40000000 (2.0) | `ui_startPulse` value | 0x320ea4 |
| 9 | displayed frames from 0.0 to 1.0 | computed (E) |
| 0x7e / 0x7b | glyph code, layout 1 / 0 | stores at 0x1e6c18 / 0x1e6c90 |
| 1 | layout byte data value | data word 0x41b69c |
| 3000 (0xbb8) | help draw: minimum free display-list units | 0x1dcd10 |
| 0x8028444e, 0x80464646 | help title, body colour (before `color_scale`) | 0x1dcd20/0x1dcd28, 0x1dcd74/0x1dcd78 |
| 0x464646, `clamp(128 − 10·delay)` | help button colour | 0x1dce04–0x1dce48 |
| 0x80808080 | help frame tint | 0x1dceb0 / 0x1dceb8 |
| 0x3f000000 | help inner frame tint | 0x1dcef8 |
| 0 | help inner frame style (ctile) | t2 at 0x1dcefc |
| (124, 104, 416, h + 76) | help inner frame | 0x1dcee4–0x1dcef0 |
| (116, 94, 416, h + 76) | help outer frame (wrapper: −1, −4, +2, +8, style 2) | 0x1dcebc–0x1dced0; 0x17fbbc–0x17fbd0 |
| (324, 100) | help title centre | 0x1dcd5c / 0x1dcd64 |
| (132, 130, 404, 0, 448, 21) | help body wrap | 0x1dcda0–0x1dcdb8 |
| `324 − W/2 − 25`, `h + 139` | glyph position | 0x1dce24, 0x1dce80, 0x1dcde8 |
| `324 − W/2`, `h + 139` | label position | 0x1dce70 |
| 0x53c768 `"%c"`, 0x53c770 `Affirmation` | help glyph format, label key | 0x1dcdd4, 0x1dcddc |
| 60 | close delay and input lockout after a confirm | 0x1dcf50 |
| 0x3dacf3df (0.08445) | bust fade step | 0x1dfbac / 0x1dfbb0 |
| 0x42dc0000 (110.0) | bust caption alpha factor | 0x1dfc38 |
| 0x43000000 (128.0) | bust number and sprite alpha factor | 0x1dfcd0 and each sprite |
| 0x395f6b | bust text RGB | 0x1dfc84, 0x1dfd14 |
| 0x808080 | bust sprite RGB | 0x1dfedc, 0x1dff50, 0x1dffc8, 0x1e0058, 0x1e00cc |
| (523, 391) / (527, 389), width 112, −100, 500, line 14 | bust wrap, number / meter branch | 0x1dfcb0–0x1dfcc8 / 0x1dfd5c–0x1dfd74 |
| (542, 371), 10000 | bust number centre | 0x1dfd3c–0x1dfd4c |
| (521, 377), clip right `521 + fill − 2` | bust bar | 0x1dfe8c, 0x1dfeb4, 0x1dfef0 |
| (511, 371) / (510, 370) | fieldmeter / fieldnumber | 0x1dff5c / 0x1dffd0 |
| 499, 366, 369 | portrait and frame x centre, portrait base, frame y | 0x1dfff0, 0x1e0030, 0x1e00d8 |
| 0x7200, 0x5800 / 0x6c00 | GS Y offset; X offset field / progressive | 0x17abb4, 0x17abd0 / 0x17ae74 |
| 0xa000 dsll 20 | Z of every quad | 0x17ac30 / 0x17ac34 |
| 0x22 / 0x03 / 0x05 | SCANMSK / UV / XYZ2 register ids | 0x17ac88, 0x17ac6c, 0x17ac84 |
| (0xbde977c8, 0x3e20c38f, 0xc0b8273d) | compass offset | 0x1df728–0x1df748 |
| 0x8000 | compass angle bias | 0x1df940 |
| 2 | compass rotation axis | 0x1df944 |
| 5, (0, 0, 1) | compass model layer, third vector | 0x1df98c, 0x1df984–0x1df9a8 |
| 0x20 | model flag: depth test ALWAYS | 0x17989c; read at 0x177b54 |
| 10 | light depth step between passes | 0x14a144 |
| (65, 394, 131, −100, 500, 18), 0x632f6159 | compass label | 0x1dfa50–0x1dfa68, 0x1dfa30 / 0x1dfa3c |
| 0x7fffffff | sound event terminator | 0x214838 / 0x214840 |
| 0x80 | state flag: REPORT_END track ended | 0x214864 |
| 0x4 \| 0x10 | voice flags stopped on free | 0x214884–0x214894 |
| 0x2b (43), 0x20 (32) | voices, slots | 0x2148c4, 0x214980 |
| 0x540ca8 `showName` | dialog name property | 0x22f210 |

Layout byte 0 (glyph 0x7b) is never observed in game data: 0x41b69c holds only the value 1,
so only layout 1 is observed (cross glyph 0x7e); the layout 0 row is inferred from the code.
