# Dynamic HUD composition (per displayed frame)

SLUS-20973 v2.00, researched 2026-10-17 on `t3/research-ui` (round 2).
Extends [hud-layout.md](hud-layout.md) (frames, base bars, fills, slot origins and
promotion) without repeating it. Companions: [reference](../tools/ref_hud_dynamic.py),
[synthetic tests](../tools/test_ref_hud_dynamic.py). Text measuring and wrapping belong
to the font/text documents; this file only names the calls and their arguments.

**Status:** the order of every HUD drawer, the notice lines, the level-up glow and
status text colours, the one-line message, the boss meter, the gold counter and
floaters and the quick-cast selector are documented and function-executed. The bust
panel, flying damage numbers, net-status lines and the compass are partly documented.
The minimap, the help/notice boxes, the arena overlay, the medal and net-camera
prompts are **unknown** beyond their entry points. Nothing here was run on a game;
"Executed" means `tools/ee_emu.py` ran the original function on constructed state.

O = observed at the addresses given, I = inferred, U = unknown. Coordinates are the
640 x 448 API arguments. Plain sprites (`ui_drawSprite` 0x17fb68) gain one row inside
the callee; clipped sprites (0x17fb88), rectangles (0x17bd30) and text do not.

## 1. Order and painter rule

**O / high**, `hud_addTasks` 0x1dc1d0, task list docs/mainloop.md: "HUD Draw"
0x1dbc48 is a draw task of priority 51. Draw tasks run lowest priority first:
drawObjects 21, drawWorld 30 (which calls `minimap_draw` 0x1e42e0 at 0x1ebc60),
inventory/shop/stats/HelpMessage 50, HUD Draw 51, pauseMenu 52, drawParticles 65,
arenaDraw 100, dialog 110, textMessageDraw 125, cutscene 300.

**O / high**, 0x1dbc48–0x1dc190, the HUD draw task calls, in this order:

| # | Call | Condition |
|---|---|---|
| 1 | `hud_drawGold` 0x1dc708 | not 0x41b4f8, not `g_hudSuppressed` |
| 2 | `hud_drawPlayerStatus` 0x1d9cd4 for slot 0, 1, ... `g_numPlayers`-1 | its own gates (hud-layout.md) |
| 3 | `arena_drawHud` 0x305904 | U inside |
| 4 | 0x1d93b0: one-line message, then boss meter | section 4 |
| 5 | `hud_drawBust` 0x1dfb6c | 0x4f66d4 set |
| 6 | `hud_drawCompass` 0x1df720 | section 7 |
| 7 | `hud_drawNetCamPrompt` 0x1e01b8 | U |
| 8 | `hud_drawControllerOut` 0x1db3c8 | warm-up 0x506048 and `g_cutsceneActive` both zero |
| 9 | `hud_drawMedalPrompt` 0x1e0698 | U |
| 10 | net game only: checksum line, out-of-sync lines, lost-connection icon and notices, exit / disconnect boxes | section 8 |

Inside one `hud_drawPlayerStatus` call the submission order is: health bar,
pending-health rectangle, pending-mana rectangle, experience bar, mana bar, name
text, level text, level-up glow, status frame, notice lines 0–7, then the quick-cast
selector (`hud_spellSelect(slot,0,0,0,0)` at 0x1dacb8). The selector is therefore
part of each slot's status call, not a separate HUD step.

**O / high**, `gfx_addSortedPacket` 0x16b7f0: sprites (flag 1, 0x17b888) and text
batches (flag 1, `text_end` 0x180618) are prepended in their layer; `ui_drawRect`
passes flag 0 **and no texture** (0x17bf64–0x17bf70), and a null texture also takes
the prepend branch (0x16b834, 0x16b8d0, 0x16b918). So every HUD 2D packet follows
one rule: layers 0→7, and inside a layer **reverse submission order**. Consequences
(I / high): within layer 6 a slot's frame is painted first and its bars over it; the
glow is painted over the frame; gold (submitted first) is painted last of the HUD;
HelpMessage packets (task 50) are painted over HUD packets of the same layer, and
pause-menu packets (task 52) under them. Text batch order is the order of `text_end`.

| Layer | HUD content |
|---|---|
| 4 | notice icons and counts |
| 5 | boss name and bar rectangle, compass model and label, flying numbers |
| 6 | status bars, frames, glow, name/level text, gold, boss frame sprite, bust, selector icons, message (normal) |
| 7 | selector arrow, corona and button labels, forced message, controller-out box, net status text and icon |

## 2. Clocks and per-machine timers

**O / high:** two clocks are used. `g_simFrame` 0x44fdcc (simulation ticks) drives
the bar animation (hud-layout.md), the shared pulse below, notice icon brightness,
gold-floater fade and bust-meter frames. `g_drawFrame` 0x44fdd0 (displayed frames)
drives the selector highlight and the lost-connection icon blink (bit 0x20,
0x1dbf30). Fades and countdowns are stepped where noted; "draw" steps run once per
displayed frame of the drawing machine and are per-machine state.

| State | Stepped in | Rule | Address |
|---|---|---|---|
| notice timers 0x41b828[slot][8] | draw, local slots only, only when the status call passes its gates | -1 per frame; at <=0 the row word is zeroed | 0x1dac60–0x1dac94 |
| counted-notice alpha 0x86ac3c[slot][8] | draw | +4 while timer>81, -4 while timer<38, clamp 0..128 | 0x1da9d0 |
| level-up glow 0x86aa50[slot] | draw | +4 to 128 while a level is pending; reset only by `hud_run` opening the menu (0x1dbaec) | 0x1da6f8 |
| message timer 0x4f66e0 | run task (`hud_tickMessage` 0x1d934c) | -1 per tick unless suppressed or warming up | 0x1d936c |
| message alpha 0x4f66ec | draw | 4*timer below 32, else +3, max 128; not reset by a new message | 0x1d93fc |
| boss bar alpha 0x41b6a8 | draw | set to 78 on the first visible frame; -3 per frame after hp reaches 0 | 0x1d95c0, 0x1d96f8 |
| gold hold 0x86acd8 / alpha 0x4f6950 | draw | visible floater sets hold 60; hold>0: -1 and alpha +4 below 128; else alpha -4 | 0x1dc7c0, 0x1dc980 |
| gold floater position/velocity | draw | section 5 | 0x1dc7cc |
| selector alpha 0x86a8d8, record +0x4a74/+0x4a78 | draw | section 6 | 0x1dd4c0 |
| bust fade 0x4f66d0 (float) | draw | ±0.08445 per frame, clamp 0..1 | 0x1dfb9c |
| flying-number alpha +0x94 | object run (sim) | -3 per tick when lifetime +0x96 < 31; removed at 0 | 0x2022b4 |

**O / high:** the pulse is `p = trunc(sin16(g_simFrame << 10) * 25.0)`
(`math_sin16` 0x1666e0, 0x1da390 and 0x1da844): a 64-tick cycle, range -25..25.
`pulse_grey(p, a)` = alpha a with R=G=B=p+103 tints the glow and notice icons.

## 3. Status adjuncts per slot (0x1da388–0x1dacbc)

**Executed:** `local/r2-hud/trace_status_dynamic.py`, 288 frames over 48
constructed players (1/2/4 players, blink masks, pending levels, weapon classes,
hidden-count level names): all notice sprites and texts (1,358 submissions),
timers, alphas, row clearing, name and level colours and glow sprites matched
`notice_frame`, `name_colour`, `pending_level_colour` and `glow_sprite`.

**Status text (O / high).** Both batches use the small font, layer 6, base colour
0x80323c3c. The name origin is (X+73,17), the level (X+134,44) (hud-layout.md).
Name colour precedence: base; the arena colour if 0x3054c4 returns nonzero; the
`player_slotColor(slot,0x80)` colour whenever `g_numPlayers` >= 2. If bit `slot` of
0x505b04 is set, RGB is halved while `(g_simFrame/32)` is odd (blink). A pending level
(acknowledged +0x58 < level +0x59) sets R=G=p/2+60, B=p/2+50, alpha 0x80 (C division)
before each batch; the name batch then sets its own colour, so **only the level number
pulses** (0x1da43c vs 0x1da598). Name width budget for `ui_fitText` 0x1bdf60 is 131,
less the width of the `x 000` sample when `g_pvpModeB` is set and `g_pvpModeA` is not.
With `g_debugCheats` and a network save pending for this slot the name is replaced by
a fixed save notice (0x1da444–0x1da47c).

**Level-up glow (O / high).** Local slot, object present and not dead, health > 0 and
a pending level: alpha steps as in section 2, then `hud_statusbar00glow.tex` is a
clipped sprite at (X-4,36), clip (0,0,1000,1000), layer 6, tint `pulse_grey(p, alpha)`,
submitted before the frame (so painted over it). `levelup.tex` from icons.lmp is
only bound here (0x1da748); where it is drawn is **U**.

**Notice lines (O / high).** Eight per slot; drawn only for local slots with a nonzero
timer. Base x = `0x53c4d8[slot] + 37` = 37, 514, 199, 358; in a net game every local slot
uses slot 0's base (0x1da8a0). The row each starter stores in 0x41b8a8 (from
`hud_countActiveNotices`) is loaded and then **overwritten** by a fixed row, so the
layout is a 2 x 2 grid, not a stack:

| Line | Resource (icons.lmp, via 0x4f85e0) | dx | row | Count shown |
|---|---|---|---|---|
| 0 | nocamera.tex | +51 | 1 | — |
| 1 | nohealth.tex | -17 | 0 | — |
| 2 | nomana.tex | -17 | 1 | — |
| 3 | noarrows.tex | +51 | 0 | — |
| 4 | counthealth.tex | -17 | 0 | 0x41b940[slot] |
| 5 | countmana.tex | -17 | 1 | 0x41b950[slot] |
| 6 | countarrows.tex | +51 | 0 | quantity of item at record +0x4410, else 0 |
| 7 | countthrown.tex | +51 | 0 | quantity at +0x43f8 when weapon class +0x4a86 is 6, else hidden |

Icon origin (base+dx, 27*row+82), layer 4, plain sprite. Lines 0–3: tint alpha 0x80,
`pulse_grey`. Lines 4–7: count text `x %d` at (base+dx+31, 27*row+81), small font,
layer 4, colour alpha<<24 | 0x4080e4, then the icon with `pulse_grey(p, alpha)`.
A count below zero, or a current level name containing `stomedal` (strstr at
0x1dab4c on 0x41b721), hides both, but the alpha step and timer decrement still
run. In those cases the text batch begun at 0x1daaa4 is not ended (O; effect **U**).
Starters observed: counted lines get 240 frames (e.g. 0x1ba0c4, 0x1a88a8), the camera
line 120 (0x205d44). Nothing prevents a "no" line and its count line from sharing a
cell; `hud_countActiveNotices` treats 4/1, 5/2, 6/3 and 7/3 as exclusive only when
counting (**Executed:** 10,240 cases of 0x1dacf4 matched `count_active_notices`,
`local/r2-hud/trace_notices_count.py`).

## 4. One-line message and boss meter (0x1d93b0)

**Executed:** `local/r2-hud/trace_boss_message.py`, 2,400 frames (60 runs, five
language values, forced/suppressed messages, random damage): draw calls and all
state words matched `message_frame` and `boss_meter_frame`.

**Message (O / high).** `hud_showMessage` 0x1d92a0 accepts text only for a local
slot (or -1) and, unless forced, not while a local menu is open; it copies the wide
text to 0x86ab78 and sets timer 0x4f66e0 and force 0x4f66e2. Drawn while timer > 0
and (not suppressed or forced): default font 0x44fdd8, layer 6 (7 if forced), colour
alpha<<24 | 0x1e6464, centred at (320,78). Background: `ui_drawFrameImpl` style 0
(ctile), x = 300 - w/2, y = 76, width w+40, height 32, where w = max(300, text width),
tint (alpha/2)<<24 with **RGB 0** — a translucent dark box behind the text.

**Boss meter (O / high).** Gates: not suppressed, no local menu (0x41b69d), camera
+0x34 == 1. `g_bossMeterHp` 0x41b6a0, maximum 0x41b6a4 (raised to any larger hp),
alpha 0x41b6a8, visible 0x4f66f0, previous hp s16 0x86a8a0.

```
if hp > max: max = hp
if not (hp > 0 and max > 0) and alpha <= 0: visible = 0; stop
if hp <= 0: hp = 0; alpha -= 3
name: small font, layer 5, colour alpha<<24|0x464646, centred (320,408)
fill = trunc((float(hp)/float(max)) * 194.0), left = 218
  language 0x44fddc in {3,4}: fill = trunc(... * 315.0), left = 162
if visible: colour = alpha<<24 | (0x808080 if hp < previous else 0x181850)
else:       alpha = 78; colour = 0x4e181850
rect (left,414)-(left+fill,430), layer 5        # fills left to right
sprite bossmeter.tex at (209,409), or bossmeter_pal.tex at (158,409) for 3/4,
       layer 6, tint 0x80808080 (never fades)
previous = hp; visible = 1
```

The bar is white on any frame its hp dropped, dark red otherwise; the frame sprite
stays fully opaque while the bar fades. The first frame's name text uses the old alpha.

## 5. Gold (0x1dc708)

**Executed:** `local/r2-hud/trace_gold.py`, 480 frames with random local sets,
floaters and counters: draw calls and every float bit of position and velocity
matched `gold_floater_step`, `gold_floater_alpha`, `gold_counter_step`.

**O / high.** Initialised tables, no writer found: text x 0x4f6730 = 50, 590, 50, 590;
y 0x4f6710 = 200, 200, 250, 250; coin x 0x4f6720 = 16, 593, 16, 593. They are indexed by
the **raw slot** (no network promotion). All text uses the default font, layer 6,
colour alpha<<24 | 0x4080e4, in one batch.

Floaters (`g_goldFloaters` 0x86a900, 8 x 0x24: +0 position, +0xc velocity, +0x18 start
tick, +0x1c amount, +0x20 slot), for each local slot with a nonzero amount, in index
order: hold timer = 60; `pos += vel` (old velocity); `d = (tx-x, ty-y, -z)`;
`w = vel + d*0.0063659`; `vel = w - w*0.0877665` (raw 0x3bd099e0, 0x3db3be9b);
alpha `clamp(128 - 3*(g_simFrame - start), 0, 128)`; amount drawn left-aligned at
`(trunc(x), trunc(y))`. The physics runs in the draw task, so floater paths depend
on the display rate (I). Crediting is `hud_tickGold` in the run task (docs/ui.md).

Counters, local slots 0–3: step hold/alpha (section 2); if alpha > 0 draw the gold
(record +0xe4) after `ui_insertThousandsSeparators` 0x1c7128 (comma or period by
language; exact rule **U** here) at (50,y) for slots 0/2, right-aligned to 590 for
1/3. After the batch, `gold03.tex` (hud.lmp) at (coin x, y-10), layer 6, tint
alpha<<24 | 0x808080 for each slot with alpha > 0.

## 6. Quick-cast selector (`hud_spellSelect` 0x1dd270)

**Executed:** `local/r2-hud/trace_selector.py`, 560 frames over four slots, offline
and network, nine pad states: alpha, record +0x4a74 / +0x4a78 matched every frame,
and the arrow, background, eight icons, corona and button labels matched in 558
drawn frames (`selector_*`). Later prompt/name submissions were not compared.

**O / high.** Local slot with health > 0 only. Centre (0x53c790[slot]+67, 145) =
x 67, 538, 223, 383; slot 0's column in a net game; (141,249) in character-sheet mode
(third argument, caller 0x1d4cd8). The D-pad of the raw local pad (0x4028d8 + 0x58*slot;
bits 0x1000 up, 0x2000 right, 0x4000 down, 0x8000 left) is read only when no menu,
dialog, card screen, jump gate or the other listed gates (0x1dd374–0x1dd404) block it;
it is masked from the game by `net_maskLocalButtons`. Direction 0..7 runs clockwise
from up; -1 none. A change of direction plays `menu_spell_high.anm`.

```
if held or menu_mode: held=1; timer=30.0; speed=4  else held=0
if timer == 0.0: speed = -1
timer -= 1.0;  alpha = clamp(alpha + 4*speed, 0, 128)
if alpha > 64 and slot >= 2 and players >= 4: bust hide latch
if alpha <= 0: held = 0; stop
```

So it opens in 8 frames, stays 29 frames after release, then closes at -4 per frame.
Draws (page 0 from the HUD; page n adds 320*n to x):

A = selector alpha in the top byte.

| Element | Origin | Layer | Tint |
|---|---|---|---|
| `spellbookarrow{dir}.tex` (if dir >= 0, not menu mode) | (cx-26, cy-24) | 7 | A, grey 0x80 |
| background (resref 0x86aa30) | (cx-68, cy-65) | 6 | A, grey 0x80 |
| ability k icon, k = 0..7, angle a = -0x4000 + 0x2000k | (cx + trunc(r cos16 a), cy + trunc(r sin16 a)) | 6 | A, grey 0x80 |
| selected k == dir: corona `smallspelliconcorona.tex`, submitted first | icon origin - (6,6) | 7 | alpha trunc(s*16+128), grey 0x80 |
| selected icon | as above | 6 | A, grey trunc(s*16+239) |
| quick-slot button label (record +0x4a84 / +0x4a85 equals k) | (cx + trunc(r2 cos a)+6, cy + trunc(r2 sin a)+3) | 7 | A, colour 0x323c3c |

r = trunc(smoothstep(alpha/128) * 60), r2 = the same with 32, through `math_hermite`
0x1658f0; the truncated radius is converted back to float before the cos/sin
products. s = `sin16(g_drawFrame << 10)`. Icons come from the skill's icon method or
the blank resref 0x86aa40. After the ring: name/`AssignCast` text, `hud_drawPromptBox`
0x1d99f0 and `spellbookparch.tex` — **U** in detail.

## 7. Partly documented elements

**Bust panel (O / medium, 0x1dfb6c).** Shown while 0x4f66d4 is set (script
`showBust`). Fade ±0.08445 per frame toward 0 while latch 0x4f66a9 is set (by
`hud_tickMessage` in 4-player offline games while a message runs, and by a slot 2/3
selector above alpha 64 with 4 players), toward 1 otherwise. Text alpha = fade*110,
sprite alpha = fade*128 (unsigned conversions). Text through `text_drawWrapped` 0x181280 with raw arguments (523,391,text,112,-100,500,14)
without a maximum or (527,389,...) with one; colour alpha<<24 | 0x395f6b, layer 6
(argument meanings: text document).
With a maximum (0x86ab34 != -1): `fieldmeter.tex` at (511,371), then
`bar_yellow0{(g_simFrame/2)%4}.tex` clipped at (521,377), clip right =
521 + round_half_away(value/max * texture width) - 2 (left-to-right). Without a
maximum: the value as text centred at (542,371) and `fieldnumber.tex` at (510,370).
Portrait (name at 0x4f6b48) at (499 - w/2, frame h - portrait h + 366), then
`frame.tex` at (499 - w/2, 369), both layer 6 (bust.lmp). Exact submission order
of all branches is only partly checked; not executed.

**Flying numbers (O / medium, `FlyingText_draw` 0x1f3830).** Only with the
damage-number option 0x44fcf8 and camera mode 1. Default font, layer 5, alpha +0x94.
Colour 0x602060 for kind 1, 0x406e40 for kind 2 without +0x84, 0x408080 when +0x84 is
set, otherwise 0x323c3c (kinds 1/2 also force x offset +0x78 = 5 and raise the anchor by
60 / 12 units over the +72 head offset). Position: `mat4_transformPoint` with 0x44f140;
x = +0x78 + trunc(0.5*x/w) + 320, y = +0x7c + trunc(y/w) + 224 (I that 0x44f140 maps to
1280-wide GS units, hence the half). Wide (+0x90) or byte text via 0x181c30 / 0x181b78.

**Compass (O / medium, 0x1df720).** Needs 0x4f8424, a compass player 0x4f841c >= 0
with an object, no dialog, and 0x4f66d5. A 3D model (`compass.vif` / `compass.tex`
in compass.lmp) placed in the camera matrix 0x44f140 at offset (-0.11399, 0.15699,
-5.7548) plus 0x44f038, turned about Z by `atan2_16(target 0x86a8f0 - player) - 0x8000`,
drawn twice at sort layer 5. Label 0x86aaf0 through `text_drawWrappedCentered` with raw arguments
(65, 394, label, 131, -100, 500, 18), small font, layer 5, colour 0x632f6159.
Screen footprint depends on projection: **I** only.

**Net status (O / high, 0x1dbcec–0x1dc0c8).** "Net Checksum Failure" at (10,300) and
one out-of-sync line per peer at (10, 320+18i): default font, layer 7, 0x80404080.
While `g_netLongStallCalls` is nonzero, `noconnect.tex` is centred at (320,224), layer 7,
blinking with bit 0x20 of `g_drawFrame`; after 1,201 calls a cable help box or a
300-frame message follows. Exit logic is in docs/ui.md.

**Controller removed (O / medium, 0x1db3c8).** `text_drawWrappedCentered` from
(320,200) with 400 as its fourth argument, layer 7, colour 0x801e6464, over a frame from wrapper 0x17fbb8 at
(112,192), width 416.

## 8. Multi-player layouts

| Element | Offline, 1–4 players | Network |
|---|---|---|
| status frame and bars | every slot local: full frame at slot x (hud-layout.md) | local slots promoted to slot 0's x; remote slots `hud_multi.tex`, health only |
| notice lines | each slot at 0x53c4d8[slot]+37 | every local slot in slot 0's column |
| selector | 0x53c790[slot]+67 | slot 0's column |
| gold | raw slot: 0/2 left, 1/3 right; rows 200 / 250 | same raw-slot table, local slots only |
| message, boss meter, bust, compass | one instance, fixed positions | same |

**I / medium:** with four players the bottom-right bust competes with the slot 2/3
selectors and the message, which is why the latch hides it. Widescreen anchoring
is not original (hud-layout.md).

## 9. Unknown and how to settle it

- `minimap_draw` 0x1e42e0 (3D automap, layer 5, modes `g_minimapMode` 0x4f8400 cycled by
  raw pads, stick zoom 0x4f71a0) — trace its matrix and sprite calls.
- `help_task` 0x1dcc78 boxes, `g_uiPulse` readers 0x1a09c8–0x1a0ea0, `arena_drawHud`,
  medal and net-camera prompts, pending-potion overlays in execution (round 1 has
  them O only).
- Selector prompt tail and bust submission order — extend the private traces.
- Exact raster parity of any of this: requires original frame captures (see the
  parity method document of this round, if present).

## Validation

Private, under `local/r2-hud/` (not tracked): five ee_emu traces, results in
`local/r2-hud/verification.log` — 10,240 notice-count cases, 2,400 message/boss
frames, 480 gold frames, 560 selector frames (558 with draws), 288 status frames
(1,358 notice submissions). Callees outside the function were stubbed except the
original sine/cosine/smoothstep, strstr and strcpy. No game, emulator or native
build was run.
