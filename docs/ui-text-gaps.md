# UI text gaps: help box, bust panel, compass, chime, fade step, glyph byte, quoted names

SLUS-20973 v2.00, researched 2026-10-21 on `t3/research-ui-text-gaps` (merges
`t3/research-strings` d4987fd, `t3/research-dialog` 334578d and `t3/research-ui` 3e39392).

The native strings round (`codex/strings`) and dialog round (`codex/dialog`) left these
items refused, not drawn, or drawn without evidence:

- the help box: its inner frame, button glyph and label;
- the bust panel: its meter, text font, sprite colour, and art layout (the art decodes as
  two half-height copies);
- the compass mesh;
- the help chime sound;
- the dialog UI fade step constant;
- the dialog cursor and "more" glyph byte;
- the miss text for quoted name keys.

This document settles each one with addressed evidence. The table form (fields, calls,
seed draws, constants) is [spec/ui-text-gaps.md](spec/ui-text-gaps.md).

Evidence words follow CONTRIBUTING.md:

- **O**: observed at the address given.
- **E**: executed. The original function or slice ran in `tools/ee_emu.py` under
  `tools/difftest_ui_text_gaps.py` and matched `tools/ref_ui_text_gaps.py` on seeds 20973
  and 7. The property is named.
- **I**: inferred from O and E.
- **U**: unknown.
- **D**: counted on the disc by `tools/ui_text_gaps_census.py`. Counts only.

Nothing here ran on a game.

| Part | Model | Difftest property | Cases per seed |
|---|---|---|---|
| UI fade and pulse ramps | `ui_ramps_step`, `fade_ramp`, `pulse_ramp` | `ui.ramps` | 6,004 |
| Button layout words, glyph byte | `button_layout`, `pad_mask_to_glyph`, `glyph_text` | `layout.glyph` | 2,445 |
| Help box | `help_task`, `help_inner_frame` | `help.task` | 5,000 |
| Bust panel | `hud_draw_bust` | `bust.draw` | 5,000 |
| Field use of every 2D sprite | `sprite_quad`, `field_calls`, `woven_line` | `sprite.fields` | 8,000 |
| Compass | `compass_world`, `hud_draw_compass` | `compass.draw` | 3,000 |
| Help chime slot | `Slot`, `sound_seq_update_all`, `chime_frames` | `sound.seqUpdate` | 1,323 / 1,314 |
| Dialog name of a quoted key | `show_name` | `dialog.showName` | 3,000 |

## 1. The dialog UI fade step (and the pulse)

**O, E `ui.ramps`.** The step is not in the dialog code. It is step 13 of the session
loop's frame (`docs/mainloop.md` section 5), slice `0x323448–0x3234d0`, right after
`gfx_endFrame`. So it runs **once per displayed frame**, after the draw pass, on every
machine. For each of the four slots i:

```
if 1.0 < g_uiPulse[i]:   g_uiPulse[i] = (g_uiPulse[i] - 1.0) * 0.8 + 1.0     # 0x3f4ccccc
if g_uiFadeIn[i] < 1.0:  g_uiFadeIn[i] += 0.12                              # 0x3df5c28f
                         if 1.0 < g_uiFadeIn[i]: g_uiFadeIn[i] = 1.0
```

- `g_uiPulse` is at 0x506060 and `g_uiFadeIn` at 0x506070, each `float[4]`.
- The sum is stored before the clamp test (0x3234c4, then 0x3234c8).
- `ui_restartFadeIn(i)` 0x320ec4 stores 0.0. `ui_startPulse(i)` 0x320ea4 stores 2.0.
  Both are executed.
- Values of 1.0 and above are never touched. A fade above 1.0 stays there.

**The ramp from `ui_restartFadeIn` (E).** Nine displayed frames:

```
0x3df5c28f 0x3e75c28f 0x3eb851eb 0x3ef5c28e 0x3f199998 0x3f3851e9 0x3f570a3a 0x3f75c28b 0x3f800000
```

The eighth value is still below 1.0. The ninth add passes 1.0 and is clamped to exactly 1.0.

**What the dialog does with it (`docs/dialog.md` 5.1 step 7 and section 7; I from the
ramp):**

- The box draws with alpha `(int)(f × 128) << 24`, or `1 − f` while closing. So the box
  fades in over 9 displayed frames and out over 9.
- `dialog_runTask` sends message 3 (or 4 with swoop) only once `g_uiFadeIn[0]` is exactly
  1.0. So the end handler (unfreeze, mutex release, pending level, post action, deferred
  shop) runs on the first simulated tick after the ninth displayed frame of the closing
  fade.
- This makes the end's timing depend on the display rate. At one tick per displayed frame
  the delay is 9 ticks. When `engine_frameStep` runs 2 ticks per frame it is about 18
  ticks, because the fade still steps once per frame.
- `g_uiFadeIn` is per machine, so in a net game each machine's own fade gates its own
  send of message 3 (I, `docs/dialog.md` 9).

The help box title, body, label and frame colours are scaled by `g_uiPulse[0]` (section
2). `ui_startPulse(0)` at each opening sets it to 2.0, and it decays by 0.8 of the excess
per displayed frame (E). The native "`g_uiPulse` decay in host floats" item is therefore
this exact float recurrence.

## 2. The help box (`help_task` 0x1dcc78)

**E `help.task`.** The whole function was run, with the notice boxes closed (0x41b518[slot]
all zero). The colours went through the real `color_scale` 0x19ecac, the glyph through the
real `sprintf`, and the frame wrapper 0x17fbb8 ran for real into a recorded
`ui_drawFrameImpl` 0x17c118. One call does the following, in order:

1. If the close delay 0x4f66cc is above 0, subtract 1.
2. If the box is closed (0x41b928 = 0), return.
3. Offline (`g_net` 0x402791 = 0): `g_paused` 0x41b4f4 = 1 and the byte 0x44fa80 = 1.
4. **Draw**, only when at least 3,000 display-list units are free:
   `[0x44fda4] − (([0x44fe10] − [0x44fe0c]) >> 3) ≥ 3000` (`slti … 0xbb8` at 0x1dcd10).
   Let `p` = `g_uiPulse[0]`, `cs(c)` = `color_scale(c, p)` and `h` = the body's wrap height
   (0 without a body).

   | # | Call | Arguments |
   |---|---|---|
   | 1 | `text_begin` 0x1800b8 | font word 0x4f7100 (gamefontmed), layer 6, `cs(0x8028444e)`, −1 |
   | 2 | `text_drawWideCentered` 0x181ca0, only with a title | 324, 100, title pointer 0x86aa64, 1,000,000 |
   | 3 | `text_setColor` 0x1802e0 | `cs(0x80464646)`, −1, 0 |
   | 4 | `text_drawWrapped` 0x181280, only with a body | 132, 130, body pointer 0x86aa68, width 404, top 0, bottom 448, line 21 → `h` |
   | 5 | `sprintf(buf, "%c", word 0x41b978)` | the glyph (section 7); string at 0x53c768 |
   | 6 | `text_lookup("Affirmation")` | the key string at 0x53c770 |
   | 7 | `text_widthWide` 0x181bf8 | font word 0x4f7100, the label, 1,000,000 → `W` |
   | 8 | `text_setColor` | `cs(a << 24 | 0x464646)`, −1, 0, with `a = clamp(128 − 10 × delay, 0, 128)` |
   | 9 | `text_drawAscii` 0x181aa0 | `324 − half − 25`, `h + 139`, the glyph, 100,000 |
   | 10 | `text_lookup("Affirmation")` | again |
   | 11 | `text_drawWide` 0x181c10 | `324 − half`, `h + 139`, the label, 1,000,000 |
   | 12 | `text_end` 0x180500 | |
   | 13 | frame wrapper 0x17fbb8 | 116, 94, 416, `h + 76`, layer 6, `cs(0x80808080)`. It calls `ui_drawFrameImpl(115, 90, 418, h + 84, 6, tint, style 2, 0, 0)` |
   | 14 | `ui_drawFrameImpl` 0x17c118 (call at 0x1dcf04) | 124, 104, 416, `h + 76`, layer 6, tint **0x3f000000**, style **0**, no-center 0, no-border 0 |

   `half` is `(W + (W >> 31)) >> 1`, a C division by two. `delay` is the value after
   step 1.
5. If the delay is not 0, return.
6. **Confirm.** For every pad k below `g_numPlayers` 0x4d8ae0 whose raw word
   (0x4028dc + 0x58k) has a bit of `g_btnConfirmMask` 0x41bfbc:
   - open = 0;
   - `g_menuInputLockout` 0x41b4fc = 60;
   - offline, `script_runPostAction` 0x1edac0;
   - delay = 60;
   - 0x44fa80 = 0;
   - `g_paused` = 0 unless `g_localMenuOpen` 0x41b69d is set;
   - for each slot of the alive list (0x4f8420, 0x4f8440), `net_isLocalSlot` 0x13e150,
     and for a local slot, `hudmsg_sendMenuState(slot, 0, 0)` 0x1de0dc.

**The three native gaps:**

- **Inner frame (O, E).** Style argument 0 means the `ctile*.tex` pieces of
  `interfac.lmp` (`docs/hud-layout.md`, frame resource manifest; all 9 present, D). The
  frame is drawn with border and centre, at (124, 104), size 416 × `(h + 76)`, tint
  0x3f000000 on layer 6. That tint is black at alpha 0x3f, about half under the GS
  modulate rule (`docs/ui-parity.md` 1). Its geometry is research-ui's executed
  `menu_frame(124, 104, 416, h + 76, style=0)` (`help_inner_frame`).
  **Correction:** `docs/hud-dynamic.md` section 9 and `ref_hud_dynamic.help_box` gave the
  inner height as `h`. Both frame calls read the register after the add at 0x1dce00, so
  the inner frame is as tall as the outer frame's argument, `h + 76`. Both files are
  corrected in this branch.
- **Button glyph (O, E).** It is the single byte `word 0x41b978 & 0xff`, drawn as ASCII
  text in gamefontmed. In this build that byte is 0x7e, the cross button (section 7). Code
  0x7e is a button glyph, so the glyph loop tints it `(alpha << 24) | 0x606060`, not the
  button colour (`docs/formats/ui-text.md`, "Button glyphs and their tint"). Before
  `game_initCamera` runs the word is 0 and `"%c"` gives an empty string (E).
- **Label (O, E).** It is the text of the key `Affirmation` (present in GTEXT, D), looked
  up twice per drawn frame. It is left-aligned at `324 − half` and shares the glyph's
  baseline. The glyph sits 25 units to its left. Both use the button colour, whose alpha
  grows from 0 to 128 as the close delay runs down from 12 to 0. So the prompt appears
  over the last 13 frames before a confirm is accepted.

**Two quirks (E):**

- **No break.** Every pad that holds confirm on the closing call closes the box again.
  Each extra close runs `script_runPostAction` again and resends the menu-state
  messages.
- **The gate skips only the draw.** Below 3,000 free units the delay still counts down
  and a confirm still closes the box.

## 3. The bust panel (`hud_drawBust` 0x1dfb6c)

**E `bust.draw`.** The whole function was run with every outward call recorded. The
original `sprintf` built the number and the bar name. Let `f` be the fade.

1. Return at once unless `g_hudBustShown` 0x4f66d4 ≠ 0. The fade does not move on frames
   when the bust is not shown.
2. `f = f − 0.08445` when the latch 0x4f66a9 is set, else `f + 0.08445` (0x3dacf3df).
   Clamp to [0, 1], then clear the latch. A negative value at 0x86ab30 is stored as 0.
3. `text_begin(font word 0x4f7104, 6, (u(f × 110) << 24) | 0x395f6b, −1)`, where `u` is the
   float-to-unsigned idiom and only its low byte survives the shift.
   - **Font correction:** 0x4f7104 is **gamefontsmall** (`docs/formats/ui-fonts.md`). The
     native client drew the caption in gamefontmed.
4. Then one of two branches:
   - **Maximum −1** (0x86ab34): `text_drawWrapped(523, 391, 0x86aab0, 112, −100, 500, 14)`.
     Then `text_setColor((u(f × 128) << 24) | 0x395f6b, −1, 0)`, then
     `text_drawAsciiCentered(542, 371, sprintf("%d", value), 10000)`. The number is
     brighter (× 128) than the caption (× 110).
   - **Any other maximum**: `text_drawWrapped(527, 389, 0x86aab0, 112, −100, 500, 14)`
     only. **There is no second wrap.** The "second wrap of the maximum branch" in the
     native report came from `docs/hud-dynamic.md`'s summary, and the code has one wrap
     per branch.
5. `text_end`.
6. `res_find("bust.lmp", "frame.tex")` and `res_find("bust.lmp", name at 0x4f6b48)`.
7. **Meter** (maximum ≠ −1):
   - `res_find(… "fieldmeter.tex")`.
   - `res_find(… sprintf("bar_yellow0%d.tex", (g_simFrame / 2) % 4))`, with C division and
     remainder, so a negative frame count would name `bar_yellow0-1.tex`.
   - `fill = round_half_away(float(value) / float(max) × float(s16 bar width))`.
   - The clipped sprite 0x17fb88 draws the bar at (521, 377), layer 6, with clip
     (521, 377)–(`521 + fill − 2`, `377 + s16 bar height`).
   - Then `fieldmeter.tex` at (511, 371).
   - A maximum of 0 divides by zero. The R5900 gives the largest float, and the clip
     saturates (E, the model's `F.div`). So the meter needs **no** extra contract for the
     20 disc calls with a non-literal maximum: the same formula runs on the run-time value.
   - **Number** (maximum −1): `fieldnumber.tex` at (510, 370).
8. Portrait at (`499 − s16(w)/2`, `s16(frame h) − s16(portrait h) + 366`), then
   `frame.tex` at (`499 − s16(frame w)/2`, 369). Both are plain sprites 0x17fb68 on
   layer 6.

**Sprite colour (O, E).** Every bust sprite (bar, meter, number plate, portrait, frame)
has tint `(u(f × 128) << 24) | 0x808080`. 0x80 is 1.0 under modulate, so the RGB is
neutral and only the alpha fades. The native's neutral RGB is right.

**Art layout.** See section 4. All 23 BUST.LMP textures, the 16 portraits included, are
stored as two fields (D), and the sprite path always draws them as fields. The woven
picture the native client draws is the right progressive equivalent.

## 4. How 2D art uses the two stored fields (`ui_emitSpriteQuad` 0x17ab50)

`docs/formats/model-texture.md` established that interface pictures hold two fields, one
above the other. `docs/ui-parity.md` left the odd-top rule **U**. Every plain and clipped
sprite reaches this quad builder: 0x17b590 calls it at 0x17b7c0, and 0x17b8b0 calls it at
0x17bbec (O).

**E `sprite.fields`.** The builder was run in all three modes, with tops of both parity
and both answers of `gfx_displayField` 0x19d9e4. With `X` and `Y` the GS coordinates, `h`
the s16 height at texture +2, and `v` the caller's source row, it appends:

| Mode | Selected by | Quads | V of the quad |
|---|---|---|---|
| frame | `0x44fdb4` ≠ 0 (half rate, `gfx_setDisplayRateMode`) | two over the same rectangle, under `SCANMSK`; then `SCANMSK` 0 | top half `v·8 + 4`, bottom half `(h/2)·16 + v·8`. Even Y: top on even lines (mask 3), bottom on odd (mask 2). Odd Y: swapped |
| field | `0x44fdd4` ≠ 0 (the normal mode) | one | even top: field bit 1 → `v·8 + 4` (top half), 0 → `v·8 + (h/2)·16` (bottom). Odd top: field bit 1 → Y + 1 line and `v·8 + (h/2)·16 + 4`; bit 0 → Y − 1 line and `v·8` |
| progressive | both 0 | one | `v·16 + 8`: the stored texture as is, both halves stacked |

The odd-top case asks `gfx_displayField` twice: once for the shift and once for the half.
X is `32x + 0x5800` in the field and frame modes and `16x + 0x6c00` in the progressive
mode. Y is `16y + 0x7200`. Z is 10 (`0xa000 << 20`).

- **When each mode runs (O).** `0x44fdd4` holds 1 in the executable's data. The session
  start (0x322a5c) and the modal loops (0x3236fc, 0x32382c) store 1, and only 0x19dea4
  stores 0. So in play every interface sprite takes the field or frame path. The
  progressive path, which would show the two stacked copies, is not the game's.
- **Odd tops (I / high).** Take the even-top case: the decoded picture is only correct
  when the field with bit 1 shows the even frame lines (`model-texture.md`, D). Under that
  assignment the odd-top case puts picture line 2k on line `y + 2k` and picture line
  2k + 1 on line `y + 2k + 1`. That is the same woven picture placed at the same y. In the
  frame mode this is executed directly: the masks swap with the top's parity.
- **Rule for a progressive client.** Weave every 2D texture
  (`stored_y = y // 2 + (h // 2 if y odd)`, as `inventory-icons.md`) and draw it at its y,
  whatever the y's parity. `woven_line` states the mapping.

## 5. The compass (`hud_drawCompass` 0x1df720)

**E `compass.draw`.** This ran with the original `mat4_translateLocal` 0x165c08, the
transpose transform 0x165fc0, `mat34_setIdentity` 0x165680, `mat34_translateLocal`
0x165b10, `math_atan2_16` 0x166798, `mat34_rotateAxis` 0x163000, 0x179890,
`model_resetDrawState` 0x179978, 0x14a0b8 and 0x14a138. `model_draw`, `res_find`, the
light reset and the text calls were recorded.

1. **Gates.** It draws only when all of these hold:
   - the word 0x4f8424 is not 0;
   - the compass player 0x4f841c is not −1;
   - its object (`0x4d8af0 + slot × 0x4c30 + 0x43d8`) is not 0;
   - `dialog_isOpen` is 0;
   - `g_hudCompassShown` 0x4f66d5 is not 0.
2. **World matrix.**
   - `M` = a copy of `g_viewProj` 0x44f140, then `mat4_translateLocal(0, 0, 0, M)`.
   - `o` = `g_cameraPos` 0x44f038 + the 0x165fc0 transform of `M` with the offset
     (0xbde977c8, 0x3e20c38f, 0xc0b8273d).
   - `W` = identity, then translated by `o`.
   - `W` is rotated about axis 2 by
     `s16(atan2_16(player.y − target.y, player.x − target.x) − 0x8000)`, with the target at
     0x86a8f0.
3. **Two passes**, both `model_draw(compass.vif, compass.tex, layer 5, &(0, 0, 1), W, 0,
   −1, 0, 0)`, with resources from `compass.lmp`:
   - **pass 1:** 0x179890 first ORs 0x20 into the model flags 0x41c168. `model_draw`
     writes the `TEST` register only when the flags have 0x28 (0x177b34). With 0x20 the
     depth test field ZTST is 1, ALWAYS (0x177b54 and 0x177bb4, value 1 loaded at
     0x177ad0). With 0x8 alone it would be 2, GEQUAL. So the first pass draws over the
     scene (O; `model_draw` was recorded, not run);
   - between the passes: `model_resetDrawState` (flags 0), then 0x14a0b8 stores 1 at
     0x4039a0, and 0x14a138 adds 10 to the light depth counter 0x4039a4
     (`light_pushLevelLight`'s counter, `symbols/render.tsv`);
   - **pass 2:** flags 0, so `model_draw` writes no `TEST` and the model keeps the normal
     depth state, with that light state;
   - then `model_resetDrawState` and `light_resetObjectLight` 0x148340.
4. **Label.** `text_begin(font word 0x4f7104, 5, 0x632f6159, −1)`, then
   `text_drawWrappedCentered(65, 394, 0x86aaf0, 131, −100, 500, 18)`, then `text_end`.

**The mesh.** No screen rectangle is stored in the executable. The compass is a 3D model
placed just in front of the camera and drawn by the ordinary model path with the game's
own view and projection. A client reproduces it by loading `compass.vif` / `compass.tex`
from the player's disc and drawing them with `W` and its own copy of the camera matrices.

- On the disc (D): 1 mesh, 1 level of detail, 739 vertices and 640 triangles.
  `compass.tex` is a model texture, not field-stored.
- The extents stay on the disc and out of this repository.
- What the pass-2 light change looks like on screen is **U**.

## 6. The help chime's slot (`soundSeq_updateAll` 0x2147c0)

The chime is started by `hud_showHelpMessage` (`docs/strings.md` 3.3):

- `sound_playOnObject(res_find("fx.lmp", "butn_message.anm"), 0, 1.0)`: no object, so
  +0x3a "no position" is 1;
- then `sound_setPlaysWhileFrozen` 0x216ad0, which stores 1 at slot +0x3b.

**E `sound.seqUpdate`.** All 32 slots were run with the original `anim_advance`.
`animsound_fireRange` 0x16d558 was recorded, and `game_isFrozen` 0x1ebdf8 and `sound_stop`
0x213ea0 were stubbed. `sound_update` calls `soundSeq_updateAll` once per displayed frame
(`docs/audio-save.md`). For each slot i with a track (s8 +0x04 ≠ 0):

1. **Not released (+0x3c = 0).** The slot is freed when:
   - the clip has no event table (+0x38 = 0);
   - or the event at the cursor (s16 +0x26) is the terminator 0x7fffffff;
   - or the state flags (+0x06) carry 0x80 (a REPORT_END track reached its end).

   Freeing stores 0 at +0x04. It stops (`sound_stop(v)`) only the voices v of the 43 at
   0x872880 whose flags have both 4 (in use) and 0x10 (looping), whose owner (s16 +6) is i
   and whose generation (s16 +8) is the slot serial (+0x38). One-shot voices play on. The
   slot then gets no step on this call.
2. **Released.** If `float(clip +0x40) < track time` (+0x20), the time becomes 0.
3. Frozen (`game_isFrozen`) and +0x3b = 0: no step.
4. **Position (+0x2c).** If the handle +0x28 is set, copy the linked object's +0x10..+0x1b.
   Then, if +0x3a is set, copy `g_cameraPos`. The camera wins when both are set (E: the
   first model got this wrong).
5. `g_curSoundVolume` 0x4f8a04 = +0x40 and `g_curSoundSlot` 0x4f8a00 = i, then
   `anim_advanceUnitSpeed(slot, slot + 0x2c, 0, 0)` 0x1709d8. That is `anim_advance` with
   speed 1.0, sound events on, and no root or yaw (`docs/spec/animation.md` 5 and 6).

After the loop it sets `g_curSoundSlot` = −1 and `g_curSoundVolume` = 1.0.

**For the chime (I from E, D):**

- The help box pauses the game offline. The chime still advances, because +0x3b is set.
- It follows the camera, because +0x3a is set.
- `butn_message.anm` has 3 sound events, none past its length, in a non-zero sound group
  (D). So the first update fires all three through `animsound_fireRange`, and the second
  frees the slot by the cursor rule (`chime_frames` gives 2, D).
- The group's start cap (`g_soundGroupLimit` 0x4f8a28, `docs/audio-playback.md`) can
  refuse a chime only while two others of that group are still in their slots, for
  example when a box is reopened on the next frame.
- The native "slots never finish" gap is closed. A slot table must free each chime slot on
  its second update.

## 7. The glyph byte 0x41b978 (help box, dialog cursor and "more")

**O, E `layout.glyph`.**

- The help box (section 2) and `dialog_drawTask` (cursor at 0x230a10, "more" at 0x230a70,
  format string 0x540d50) draw `sprintf("%c", word 0x41b978)` with `text_drawAscii`.
  `%c` keeps the low byte.
- 23 functions read the word (`tools/gxref.py`). Its only writer is `game_initCamera`
  0x1e6b68, called once from `main`, through the layout byte 0x41b69c.
- 0x41b69c holds **1** in the executable's data. `tools/gxref.py` finds no store to it (its
  readers are `config_setDefaults` 0x1e6238 and `game_initCamera`), and no data word
  points at it (`ps2elf.py ptrs`).

| Layout byte | 0x41b978 glyph | 0x41b97c | `g_btnConfirmMask` 0x41bfbc | 0x41bfb8 | other words |
|---|---|---|---|---|---|
| **1 (this build)** | **0x7e (cross)** | 0x7b | 0x40 | 0x20 | 0x41b960 0x40, 0x41b964 0x7e, 0x41b968 0x10, 0x41b96c 0x7c, 0x41b970 0x80, 0x41b974 0x7d |
| 0 | 0x7b (circle) | 0x7e | 0x20 | 0x140 | 0x41b960 0x20, 0x41b964 0x7b, 0x41b968 0x80, 0x41b96c 0x7c |
| anything else | not written (0 before the call) | | | | |

- `pad_buttonMaskToGlyph` 0x1eacb8 (E, every single bit and 2,000 random masks) maps the
  confirm mask of each layout to that layout's glyph: 0x40 → 0x7e, 0x20 → 0x7b. So the
  drawn glyph is always the button that confirms.
- The data values of 0x41bfbc (0x40) and 0x41bfb8 (0x20) already match layout 1.
- **Answer:** draw code 0x7e of gamefontmed. In all four audited fonts the codes
  0x7b–0x88 are the button glyphs (indices 0x5b–0x68), and `docs/formats/ui-text.md` names
  0x7e the cross. The glyph loop tints them with 0x606060.
- The dialog's cursor is the same cross, drawn at x 56. The y blends between the choice
  rows, or is 398 without choices. The "more" prompt is the cross at (51, 398), then the
  `dialogMore` text (key present, D) at (81, 398) (`docs/dialog.md` 7).

## 8. The miss text of a quoted showName key

**O, E `dialog.showName`.** Message 0 of `dialog_onMsg` (0x22f208–0x22f28c) does:

1. `obj_getProp(speaker, "showName", 0)` 0x14f4c0. It lowercases the key in place
   (0x14f508–0x14f538) and returns a pointer to the raw text after `=` (0x14f5ac), quotes
   included.
2. `text_lookup` of that pointer.
3. `wstr_copy` 0x19e854 into 0x8e2d68.
4. `wstr_len` 0x19e994 into 0x8e2cdc.

The slice ran with the real lookup, copy and length on synthetic tables, with 1 to 3
quotes inserted at random places in present and missing keys:

- `text_lookup` drops every `"` from its stack copy before hashing (`docs/strings.md`
  1.4). A quoted key whose bare form is in the table is **found**.
- A miss copies `NF:` plus the first 16 bytes of the **bare** key, without quotes and
  sign-extended. The terminator follows. The length is that visible length (19 at most).
- A key made only of quotes looks up the empty key and shows `NF:`.
- Each miss advances the ring index 0x41bfa8, which is compared after every case.

**On the disc (D):**

- All 33 `showName` values are written in quotes.
- 32 are found once the quotes are dropped.
- 1, on an object with `dialogScript`, is missing. It shows `NF:` and its bare key, which
  is not longer than 16 bytes, so nothing is cut.
- A client that does not drop quotes misses all 33.

## 9. On the disc (counts only)

`python3 tools/ui_text_gaps_census.py --disc /path/to/extracted-disc`.
The folder was only read.

| What | Count |
|---|---|
| BUST.LMP entries / textures | 23 / 23 |
| fixed names `hud_drawBust` asks for (frame, fieldmeter, fieldnumber, four bar_yellow), present | 7 of 7 |
| BUST.LMP textures read as two stacked fields / single / unclear / refused | 23 / 0 / 0 / 0 |
| … of them portraits, stacked | 16 |
| `showBust` calls with a literal portrait name / found in BUST.LMP / not literal | 31 / 31 / 0 |
| `ctile` pieces in INTERFAC.LMP | 9 of 9 |
| compass.vif, compass.tex present | 1, 1 |
| compass.vif meshes / levels of detail / vertices / triangles | 1 / 1 / 739 / 640 |
| compass.tex stored as fields | 0 |
| butn_message.anm in FX.LMP / sound events / events after its length | 1 / 3 / 0 |
| chime sound group 0 (no cap) | 0 (capped group) |
| `sound_update` calls the chime's slot lives / frees by the cursor rule | 2 / 1 |
| GTEXT keys `Affirmation`, `dialogMore` present | 1, 1 |
| objects with showName / quoted / found without quotes / missing | 33 / 33 / 32 / 1 |
| … missing on an object with dialogScript / missing and over 16 bytes | 1 / 0 |

## 10. Seeds

No property touched a seed word. The first 80 calls of each property (20 for the chime)
recorded every load and store. None reached `g_cosmeticSeed` 0x404460, `g_randSeed`
0x404464 or 0x404468, on either seed.

- The fade and pulse ramps, the layout words, `help_task`'s own code, `hud_drawBust`,
  `ui_emitSpriteQuad`, `hud_drawCompass` (atan2 and the matrix functions included), the
  `soundSeq_updateAll` loop and the showName path draw nothing.
- **Two callees outside the executed scope do draw.** The chime's events go from
  `animsound_fireRange` to `animsound_play` 0x16d360, which takes pitch, volume and delay
  variation from `g_cosmeticSeed` (`docs/spec/animation.md` 6, O; recorded, not run here).
  The help box's `script_runPostAction` runs whatever the script asked for.
- Every item here is per-machine presentation, except the help box's offline pause, its
  post action and its menu-state messages (`docs/strings.md` 3.6), and the fade gate on
  dialog message 3 (section 1).

## 11. What the native client should implement, ranked

Ranked by what changes behaviour first, then by disc use per unit of work.

1. **The fade gate on the dialog's end (1).** Step `g_uiFadeIn[0]` by 0.12f per displayed
   frame, clamp at 1.0, and send message 3 only at exactly 1.0. This is 9 frames after
   closing starts.
   - It is the only item here that moves a simulation event: unfreeze, pending level, post
     action and shop open 9 frames later than without it.
   - It also gives the box's fade-in and fade-out alpha.
   - Two constants, one recurrence.
2. **Drop quotes before every text lookup (8).** All 33 showName values are quoted. The
   native dialog table must strip `"` from the request, not from the stored key. The
   refused talks then open: 32 names resolve, and 1 shows `NF:` + bare key. This replaces
   the dialog branch's own text table with the `champions-strings` lookup (STRINGS.md
   suggests this already).
3. **The glyph byte (7).** A constant 0x7e (cross) for this build. Draw it through the
   font's button-glyph path, tinted 0x606060. It unblocks the help box button, the dialog
   cursor and the "more" prompt at once, plus 21 other functions that read the same word.
   Keep the layout table if a build with layout 0 ever appears.
4. **The help box's inner frame and label (2).** `menu_frame(124, 104, 416, h + 76,
   style 0)` with tint 0x3f000000, under the outer frame. Then the `Affirmation` label at
   (`324 − W/2`, `h + 139`) and the glyph 25 to its left, in the button colour
   `clamp(128 − 10 × delay, 0, 128)`. Keep both quirks: no break in the confirm loop, and
   the draw gate does not stop the confirm.
5. **Bust corrections (3).**
   - The caption uses gamefontsmall (word 0x4f7104).
   - The number's alpha is fade × 128, and the caption's is fade × 110.
   - The meter has one wrap at (527, 389), and its clip right is
     `521 + round_half_away(value / max × bar width) − 2` on the run-time maximum, which
     covers the 20 non-literal ones.
   - The RGB is neutral 0x808080 (confirmed).
   - The art stays woven (4; 23 of 23 textures).
6. **The chime's slot (6).** Free the slot on its second `sound_update` (cursor rule).
   Keep +0x3b (plays while paused) and the camera position. Hand the three events to the
   audio job's `animsound_play`, which draws the cosmetic seed.
7. **The field rule for odd tops (4).** No change for a client that already weaves: the
   woven picture goes at y for either parity. Only a raster-exact client needs the
   per-field quads.
8. **The compass (5).** Last, as in `docs/strings.md` 7: 3 disc calls, all in levels
   outside the level table with missing keys. Draw `compass.vif` with `W` in two passes
   (depth ALWAYS, then the normal depth state with light depth + 10), plus the label.

## 12. Validation

| Run | Command | Result |
|---|---|---|
| Model tests | `python3 -m unittest tools/test_ref_ui_text_gaps.py tools/test_ref_hud_dynamic.py` | 63 tests OK |
| Difftest, seed 20973 | `python3 tools/difftest_ui_text_gaps.py --seed 20973` | 8 properties, 8 PASS |
| Difftest, seed 7 | `python3 tools/difftest_ui_text_gaps.py --seed 7` | 8 properties, 8 PASS |
| Mutations | `python3 tools/difftest_ui_text_gaps.py --quick --mutate NAME`, for each of nine | all 9 caught |
| Census | `python3 tools/ui_text_gaps_census.py --disc …` | section 9 |
| Full unit suite | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'` | 879 tests OK |

The nine mutations, each caught by the property named:

| Mutation | Property |
|---|---|
| fade step 0.125 | `ui.ramps` |
| pulse decay 0.75 | `ui.ramps` |
| layout 1 glyph 0x7b | `layout.glyph` |
| inner frame height `h` | `help.task` |
| bust caption alpha × 128 | `bust.draw` |
| field answer ignored | `sprite.fields` |
| compass pass 1 without flag 0x20 | `compass.draw` |
| chime ignores the end status | `sound.seqUpdate` |
| showName keeps its quotes | `dialog.showName` |

## 13. Unknown

- What the compass's second pass looks like: the meaning of 0x4039a0 and of light depth
  + 10 beyond `light_emitModelLights` reading the flag. Its pixel footprint needs the
  game's camera, which only a run gives.
- Which display field `gfx_displayField` (0x83d258) reports as 1 on the console. The
  odd-top conclusion rests on the even-top case being correct (4).
- The notice-box half of `help_task` (0x1dcff4 onward) was not re-executed here. It is
  `docs/hud-dynamic.md` section 9.
- Exact console behaviour: everything ran in the interpreter.
