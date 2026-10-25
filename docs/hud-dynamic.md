# Dynamic HUD composition (per displayed frame)

SLUS-20973 v2.00, researched 2026-10-17 on `t3/research-ui` (round 2).
Extends [hud-layout.md](hud-layout.md) (frames, base bars, fills, slot origins and
promotion) without repeating it. Companions: [reference](../tools/ref_hud_dynamic.py),
[synthetic tests](../tools/test_ref_hud_dynamic.py). Text measuring and wrapping belong
to the font/text documents; this file only names the calls and their arguments.

**Status:** the order of every HUD drawer, the notice lines, the level-up glow and
status text colours, the one-line message, the boss meter, the gold counter and
floaters and the quick-cast selector are documented and function-executed. Round 3
(2026-10-20) adds the flying-number lifetime, the minimap mode tables and blip
colours, the compass anchor, the help and notice boxes, the arena step gate, and
the medal and net-camera prompts. The bust submission order was re-read. The
minimap's blip projector `0x168cac` and the compass mesh extents are still open.
Nothing here was run on a game; "Executed" means `tools/ee_emu.py` ran the
original function on constructed state.

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
| 3 | `arena_drawHud` 0x305904 | section 9 |
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

## 7. Bust, flying numbers, compass, net status

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
`frame.tex` at (499 - w/2, 369), both layer 6 (bust.lmp). Submission order, re-read
2026-10-20: one text batch (wrapped line, and either the centred value or the
second wrap), then the meter branch (clipped `bar_yellow` at `0x17fb88`, then
`fieldmeter.tex` at (511, 371)) or the number branch (`fieldnumber.tex`), then
the portrait, then the frame. Same layer, so the frame is the first thing
painted. Executed as a whole in [ui-text-gaps.md](ui-text-gaps.md) section 3,
which corrects two points: the caption font is the small font (word `0x4f7104`),
and the meter branch has one wrap only, at (527, 389).

**Flying numbers (O / high for the lifetime and the draw arithmetic).**
Constructor `0x202158` stores kind at +0x8c, the crit word at +0x84, random drift
`(rand % 60) - 30` at +0x78 and +0x7c, alpha +0x94 = 0x80, and life +0x96 = 180
when kind != 0 else 30. It registers the object with `obj_runEveryFrame`
`0x14f248`, so the lifetime is a simulation object: `FlyingText_run` `0x2022a8`
runs on every machine. Each tick subtracts 1 from life. While the incoming
signed life is below 31, alpha subtracts 3 (a negative result is stored as 0).
When the new signed life is <= 0 the object calls the destructor at vtable+8.
A plain number therefore lasts 30 sim ticks and fades on all of them; any other
kind lasts 180 and fades only over the last 30. **Executed**, 30 and 180 ticks.

`FlyingText_draw` `0x1f3830` returns immediately unless option `0x44fcf8` is set
and the camera mode at `g_localCamera`+0x34 is 1, so a network game still
simulates the number on a machine that is not drawing it. Default font, layer 5.
Colour `0x602060` for kind 1; `0x406e40` for kind 2 with +0x84 clear; when +0x84
is set (any kind other than the kind-1 path) the colour is `alpha<<24 | 0x008080`
(the low 16 bits only — not `0x408080`); otherwise `0x323c3c`. Kind 1 does not
read +0x84. Kind 1 and kind 2 without the crit word write +0x78 = 5 on the draw
and add 60 or 12 to a head offset of 72. Position: `mat4_transformPoint` with
`0x44f140`; x = +0x78 + trunc(0.5*x/w) + 320, y = +0x7c + trunc(y/w) + 224
(I that `0x44f140` maps to 1280-wide GS units, hence the half). Wide (+0x90) or
byte text via `0x181c30` / `0x181b78`. **Executed** for four (kind, crit) pairs
with the transform stubbed.

**Compass (O / high for the anchor and the label; the mesh rectangle is U).**
Needs `0x4f8424`, a compass player `0x4f841c` >= 0 with an object, no dialog, and
`0x4f66d5`. The model origin is `g_cameraPos` `0x44f038` plus the xyz from
`0x165fc0` applied to offset (-0.113998, 0.156996, -5.75479) and `g_viewProj`
`0x44f140` (`0x1df7dc–0x1df8e0`). `0x165fc0` uses rows of 16 consecutive floats
and discards w. **Executed** on one non-identity matrix. The model
(`compass.vif` / `compass.tex`) is then turned about axis 2 by
`atan2_16(target 0x86a8f0 - player) - 0x8000` and drawn twice at sort layer 5.
Its screen rectangle depends on the mesh, which this function does not hold.
Label `0x86aaf0` through `text_drawWrappedCentered` (65, 394, width 131, top
-100, bottom 500, line 18), small font, layer 5, colour `0x632f6159`. That
label call is the screen footprint that does not depend on the mesh.

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

## 9. Minimap, boxes, arena, prompts

**Minimap (O / high for the mode tables and the chase; the projector is U).**
`minimap_applyMode` `0x1e3ff0` writes five floats. With `players < 2` the byte
offsets are `mode<<3` and `(mode<<3)+4`; otherwise `(mode<<3)+0x18` and
`(mode<<3)+0x1c`. From `0x53e1b8` and `0x53e218`:

| mode | players | 0x86af58 scale | 0x86af5c | 0x86af60 | 0x86af64 | 0x86af68 |
|---|---|---|---|---|---|---|
| 0 | either | 0.9 | 0 | 0 | 320 | 224 |
| 1 | 1 | 0.7 | 200 | -120 | 120 | 100 |
| 1 | 2+ | 0.7 | -240 | 140 | 120 | 100 |
| 2 | 1 | 0 | 180 | -120 | 0 | 0 |
| 2 | 2+ | 0 | -240 | 140 | 0 | 0 |

**Executed** for those six calls (`0x168990` stubbed; the stores do not use it).
`minimap_draw` `0x1e42e0` chases each of the four offsets toward that target:
snap when the gap is below 0.005, otherwise add a quarter of the gap
(`0x1e4664–0x1e46a8`, and the same step for the other three). It then calls
`0x168cac` with zoom = scale × `0x4f71a0`, the four offsets, and two more
floats from `0x53e1f8[mode]` (16, 10, 10) and `0x53e208[mode]` (6, 5, 5).
What `0x168cac` does with them is **U**.

`minimap_blipColor` `0x1e40a8` writes three bytes to its out-pointers from the
word at object +0x3c8, which is also the player index whose health at +0xac
gates the blink (multiply at `0x1e4144`). Health <= 0 draws only when
`g_simFrame` bit 0x20 is set. The three bytes are (0xb6, 0x2f, 0x3a),
(0, 0xbf, 0), (0xb4, 0xb2, 0), (0x1d, 0x20, 0xa1) for 0..3. A non-player whose
flag word +0xc masked with 0x28 equals 0x20, and whose flags at +0xa8 have bit
43 set, uses (0xe7, 0xc1, 0x52). The grey (0xc8, 0xc8, 0xc8) with the scale
out-float set to 0.5 is the other flag arm (`0x1e424c`).

**Help box (O / high, `help_task` 0x1dcc78).** While `g_helpMessageOpen`
`0x41b928` is set, an offline game sets `g_paused`. The draw is skipped when
fewer than 3,000 display-list units are free. Title centred at (324, 100) if
the pointer at `0x86aa64` is set, colour `color_scale(0x8028444e, g_uiPulse)`,
font `0x4f7100`, layer 6. Body `text_drawWrapped` at (132, 130), width 404, top
0, bottom 448, line 21, colour `color_scale(0x80464646, pulse)`. The button
alpha is clamp(128 − closeDelay×10, 0, 128) over rgb `0x464646`, then scaled.
The '%c' glyph (byte `0x41b978`) is at x = 324 − halfWidth − 25; the
`Affirmation` string is left-aligned at 324 − halfWidth; both use y = wrap
height + 139. Frame `0x17fbb8` at (116, 94), size 416 by (height + 76), tint
`color_scale(0x80808080)`. Inner `ui_drawFrameImpl` at (124, 104), same width,
height = the wrap height + 76 (corrected 2026-10-21: both frame calls take the
register after the add at `0x1dce00`), style 0 (`ctile`), tint word `0x3f000000`,
layer 6. Executed in [ui-text-gaps.md](ui-text-gaps.md) section 2. Confirm on a raw
pad stores close delay 60, clears the open flag, and (offline) runs the post
action. The delay decrement at the top of the function only blocks that input.

**Notice box (O / high, same function from 0x1dd008).** Per slot while
`g_playerNoticeOpen` is set. The word at `0x86aa98[slot]` times 320 is the
column. Title at (column+160, 100). Body at (column+36, 130), width 256, line
21. Button at (column+135, height+135); the affirmation string at
(column+160, same y). Frame at (column+26, 94), size 268 by (height+76).
Rectangle (column+34, 102) to (column+302, height+178), colour word
`0x3f000000`. Dismiss is the released-then-pressed latch already described in
docs/ui.md; this read adds no network test around `script_runPostAction`.

**Arena overlay (O / high for the gate, partial for the point).**
`arena_drawHud` `0x305904` requires `g_pvpModeB`, not `g_pvpModeA`, not
`g_inFrontend`, not `g_localMenuOpen`. A player whose float at
`0x5038a0 + slot×12` is below 2 contributes up to five centred `arenaBonus`
strings, layer 6. Step k draws when max(0, timer − k×0.03) <= 1 (`max.s` at
`0x305ac0`). `fx_pulseColor` is called as (128 − 16k, 2000 − 200k). Step 0 uses
font `0x4f7100`; the later steps use `0x4f7104`. The position is the
`vec3_hermite` at `0x162310` of the anchors built just above that call; the
resulting point is **U** until that call is executed with the gold-table inputs.

**Medal prompt (O / high, `0x1e0698`).** Skipped while `pauseMenu` runs, and
unless word `0x4f66b0` is set. While `missionmenudraw` runs it calls
`hud_drawMessageBox` with keys `MedalRound` and either `MedalRoundPick` or,
when networked and `net_localIsFirstActive` is 0, `MedalRoundPickNet`.
Arguments: a2 0, a3 0x80, t0 0, t1 0x7c, t2 0, t3 −1, stack −28 and 1. The
message-box prologue turns that into x 320, y 192, width 520, layer 6. The
list `menuList_draw` at (320, 220) runs whenever the prompt is armed.

**Net-camera prompt (O / high, `0x1e01b8`).** Offline returns. Otherwise the
local slot's record is `g_players + slot×0x4c30` (the multiply at `0x1e01f4`).
`Camera_cycleSpectated(cam, 0)` runs when `0x1ec580` is nonzero, or when health
+0xac is 0 and (the object at +0x43d8 is missing or `g_playerDeadCountdown` is
0) and `g_alivePlayerCount` is nonzero. Dialog, a cutscene or the pause menu
then return without text, after that cycle. Confirm on the slot's raw pad
(`0x4028dc + slot×0x58`) cycles with argument 1. The spectated name is
`text_drawAsciiCentered` at (320, 352), layer 6, colour `player_slotColor`.
When two or more players are alive, `netCamToggle` is centred at (320, 372)
in colour `0x804d4d4d`.

## 10. Unknown and how to settle it

- `0x168cac`, the minimap projector: the floats it receives are in section 9;
  its sprite or matrix output is not.
- Compass mesh extents, so the model footprint in pixels. The label rectangle
  and the world anchor are known.
- The hermite point of `arena_drawHud`. The step gate is known.
- Selector prompt tail. Bust submission order is now read; the function is
  still not executed as a whole.
- Exact raster parity of any of this: requires original frame captures
  ([ui-parity.md](ui-parity.md)).

## Validation

Private, under `local/r2-hud/` (not tracked): five ee_emu traces, results in
`local/r2-hud/verification.log` — 10,240 notice-count cases, 2,400 message/boss
frames, 480 gold frames, 560 selector frames (558 with draws), 288 status frames
(1,358 notice submissions). Callees outside the function were stubbed except the
original sine/cosine/smoothstep, strstr and strcpy. No game, emulator or native
build was run.

Round 3, `tools/difftest_ui_r3.py`: `minimap_applyMode` for six (mode, player)
pairs; `FlyingText_run` for 30 and 180 ticks; `FlyingText_draw` for four
(kind, crit) pairs with the transform and text calls stubbed; `0x165fc0` on
one matrix; the present-gain slice `0x19ce3c–0x19cf08`; `color_scale`
`0x19ecac` at factors 1 and 0.5. All matched the reference.
