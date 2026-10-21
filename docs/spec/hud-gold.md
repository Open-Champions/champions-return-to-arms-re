# HUD gold counter, end to end

SLUS-20973 v2.00, researched 2026-10-21 on `t3/research-hud-gaps`. Reference
[tools/ref_hud_gold.py](../../tools/ref_hud_gold.py), synthetic tests
[tools/test_ref_hud_gold.py](../../tools/test_ref_hud_gold.py), comparison
[tools/difftest_hud_gold.py](../../tools/difftest_hud_gold.py). Extends
[hud-dynamic.md](../hud-dynamic.md) section 5 and the pickup half of `docs/spec/gold-run.md`
on branch `t3/research-combat-ctors-4` (read there, not merged).

**Status:** the producers, the credit, the counter's hold/alpha state machine, the text,
the separator rule and the coin are Executed in `tools/ee_emu.py` on both seeds. The
counter shows only after a floater (pickup or chest) or an arena bonus life. Nothing here
ran on a console. Evidence: O observed at the address, I inferred, U unknown, Executed
(`difftest_hud_gold.py`, property named).

## 1. In brief

- Gold reaches the HUD only through `hud_addGoldFloater` 0x1dc268. It has three callers:
  `Gold_onTouch` 0x157b30, `AutoChest_interact` 0x23ba1c and `Chest_interact` 0x293180 (O).
  Every other gold writer stores record +0xe4 directly and never shows the counter.
- The floater is the counter's only "show" signal. While a floater of a **local** slot is
  busy, every displayed frame sets hold = 60. The counter fades in 4 a frame to 128, stays
  while hold runs down, then fades out 4 a frame (Executed `draw`, `life`).
- One pickup, one displayed frame per tick: the counter is visible for 133 frames. The
  floater is drawn for frames 0–42, the gold starts arriving at tick 43 in eighths, full
  alpha from frame 31 to 101, gone at frame 133 (Executed `life`, 100 single pickups).
- The credit is lockstep: only `g_simFrame` and the floater's amount, start and slot are
  read. No shared draw anywhere. `hud_addGoldFloater` draws the **cosmetic** seed once per
  filled floater, on every machine (Executed `add`, `life`).
- The separator rule: `sprintf("%d")`, then a separator before each group of three from the
  right. ',' when the s8 language byte 0x44fddc is 0, '.' for any other value. Correct for
  every gold amount (at most 8 digits). It breaks for 9 digits and for "-123" (Executed `sep`).

## 2. Producer chain

| # | Function | What it does for gold | Evidence |
|---|---|---|---|
| 1 | `Gold_onTouch` 0x157a9c | toucher a player (flag 0x40), not the prediction copy (0x20000), countdown +0x4c 0, amount +0x80 ≠ 0: coin sound, `hud_addGoldFloater(toucher +0x3c8, pile position, +0x80)`, amount 0, delete | O; Executed in gold-run.md (ctors-4) |
| 2 | `AutoChest_interact` 0x23b894 | first use opens the chest; with s16 +0xdc > 0 it stays interactable. Second use: `game_pu_coin.anm` sound, `hud_addGoldFloater(slot, chest position, s16 +0xdc)`, then +0xdc = 0 | O 0x23b9a8–0x23ba24 |
| 3 | `Chest_interact` 0x292a2c | when +0x84 (opened) is set: +0x54 = 1, coin sound, `hud_addGoldFloater(slot, chest position, s16 +0x4c)`, then +0x4c = 0 | O 0x293130–0x293188 |
| 4 | `hud_addGoldFloater` 0x1dc268 | first free floater (amount 0), index 0 first. None free: record(slot) +0xe4 += amount, capped; no draw. Else amount, slot byte, start = `g_simFrame`, off-screen byte, screen position and drift (section 4) | Executed `add` |
| 5 | `hud_tickGold` 0x1dcb80 | first call of `hud_run` 0x1db890 (run task). Floater with `(frame − start) × 3 ≥ 128` (43 ticks) moves to `g_goldPending[s8 slot]`; each pending p > 0 pays `(p + 7) >> 3` into +0xe4, capped | Executed `tick` |
| 6 | `hud_flushGold` 0x1dc5f4 | from `game_clearLevel` 0x1e4e88: everything at once, then hold and alpha of slots 0–3 = 0 | Executed `flush` |

Gold writers that do **not** show the counter (O): `shop_buy` 0x1d1240, script
`givePlayerGold` 0x1462dc (its own cap at 0x146300/0x14630c), `takePlayerGold` 0x1463ec,
`player_initNewCharacter` 0x1b1d70 (500), the `hud_run` debug cheat (1,500,000, docs/ui.md
P5), `itemList_drawGold` 0x1c7218 (clamp). No shop-sell path calls the floater. The arena
bonus life (section 5) spends gold and does show the counter.

## 3. Fields

| Address / offset | Type | Writers | Readers | Evidence |
|---|---|---|---|---|
| `g_goldFloaters` 0x86a900, 8 × 0x24 | | add, tick, flush, draw | same | O gxref; Executed |
| floater +0x00..+0x08 | f32[3] | add (z = 0), draw (physics) | draw | Executed `add`, `draw` |
| floater +0x0c..+0x14 | f32[3] | add (z = 0), draw | draw | Executed |
| floater +0x18 | u32 start tick | add | tick, draw (alpha) | Executed |
| floater +0x1c | u32 amount, 0 = free | add, tick, flush | add, tick, flush, draw | Executed |
| floater +0x20 | s8 slot | add | tick, flush, draw | Executed |
| floater +0x21 | u8 off-screen | add (0x1dc378, 0x1dc3e4) | **none found** (draw reads +0x00..+0x20 only) | O |
| `g_goldPending` 0x86ace8 | s32[4] | tick, flush | tick, flush | Executed |
| hold 0x86acd8 | s32[4] frames | draw (60 at 0x1dc7c0; −1 at 0x1dc9a0), flush (0, 0x1dc6f0) | draw | O gxref; Executed |
| alpha 0x4f6950 | s32[4] | draw (+4 0x1dc9bc, −4 0x1dc9d8), flush (0, 0x1dc6e4), 0x307ee0 (128, 0x307f34) | draw | O gxref; Executed `bonus` |
| record +0xe4 (`g_players` 0x4d8af0, stride 0x4c30) | s32 gold | add (all busy), tick, flush, and the direct writers above | draw (`%d`) | Executed |
| 0x4f6710 / 0x4f6720 / 0x4f6730 | s32[4] y / coin x / text x | none found (image data) | add, draw, `arena_drawHud` 0x305a2c | O |
| 0x44fddc | s8 language | `mainloop_runSession` | separators (0x1c71d4) | O; Executed `sep` |
| 0x44fdd8 | font | — | draw (0x1dc754, 0x1dca58) | O |
| 0x41b4f8 (s32), 0x4f66a8 (s8) | HUD-off gates | — | draw: non-zero skips everything, nothing steps | Executed `draw` |

`g_goldFloaters` 0x86a918 in `symbols/ui.tsv` is entry 0's +0x18; the array starts at 0x86a900.

## 4. Calls, in call order

| Call | Where | Seed draws (shared / cosmetic / third / libc) | Evidence |
|---|---|---|---|
| `hud_addGoldFloater(slot, pos, amount)` | lockstep pickup, every machine | 0 / **1 per filled floater**, 0 when all busy / 0 / none | Executed `add`, 3,000 per seed |
| ↳ `mat4_transformPoint(out, g_viewProj 0x44f140, pos)` | inside | 0 | Executed (runs real) |
| `hud_tickGold()` | run task, every machine, no local-slot gate | 0 / 0 / 0 | Executed `tick` |
| `hud_flushGold()` | level clear | 0 / 0 / 0 | Executed `flush` |
| `0x307ee0(slot)` arena bonus life | `arena_runTask` 0x3071d4 | 0 / 0 / 0 | Executed `bonus` |
| `hud_drawGold()` | draw task, per displayed frame | 0 / 0 / 0 | Executed `draw` |
| ↳ `text_begin(font, 6, 0x804080e4, −1)` | | | Executed |
| ↳ per floater 0..7: `net_isLocalSlot(s8 slot)`; if local and busy: hold = 60, `sprintf("%d", amount)`, physics, `text_setColor(a<<24 \| 0x4080e4, −1, 0)`, `text_drawAscii(trunc x, trunc y, text, 100000)` | | sprintf: none | Executed |
| ↳ per slot 0..3: `net_isLocalSlot(slot)`; if local: step hold/alpha; if alpha > 0: `text_setColor`, `sprintf("%d", +0xe4)`, `ui_insertThousandsSeparators`, slots 1/3 `text_widthAscii(font, text, 100000)`, `text_drawAscii(x, y, text, 100000)` | | none | Executed |
| ↳ `text_end()` | | | Executed |
| ↳ per slot 0..3 with alpha > 0: `res_find("hud.lmp", "gold03.tex")`, `ui_drawSprite(tex, coin x, y − 10, 6, alpha<<24 \| 0x808080)` | | | Executed |

## 5. Hold and alpha state machine (per displayed frame, local slots)

1. Floater loop: each busy floater of local slot s sets hold[s] = 60 (0x1dc7c0).
2. Counter step (0x1dc980–0x1dc9d8): hold > 0 → hold − 1, and alpha + 4 while alpha < 128.
   hold = 0 → alpha − 4 while alpha > 0.
3. Draw when alpha > 0.

Floater alpha is `128 − 3 × (g_simFrame − start)`, clamped to 0..128 (0x1dc900–0x1dc920). It
reaches 0 at age 43, the tick the floater is freed.

Single pickup, one displayed frame per tick, pickup before that tick's draw (Executed
`life`; `ref_hud_gold.counter_timeline`):

| Frame (age) | Floater | hold after | alpha after | gold |
|---|---|---|---|---|
| 0 | drawn, alpha 128 | 59 | 4 | unchanged |
| 31 | drawn | 59 | 128 | unchanged |
| 42 | last frame drawn (alpha 2) | 59 | 128 | unchanged |
| 43 | freed into pending | 58 | 128 | + (p+7)>>3 |
| 101 | — | 0 | 128 | |
| 102 | — | 0 | 124 | |
| 133 | — | 0 | 0 (hidden) | |

Hold and alpha step per **displayed** frame, the credit per **tick**. With two draws per tick
the counter fades faster in ticks; the floater still lasts 43 ticks. Draws are skipped while
0x41b4f8 or 0x4f66a8 is set, and nothing steps then. A non-local slot is never stepped.

Other writers: `hud_flushGold` zeroes hold and alpha (the counter vanishes at level clear).
The arena bonus life 0x307ee0 sets alpha = 128 with hold untouched: the counter shows at
once and fades over 32 frames. `arena_runTask` calls it after taking the price from +0xe4
when gold ≥ price (0x3071c4); the price 0x8e7358 starts at 100 (`arena_init` 0x304e70) and
doubles (O). No other writer was found (gxref over every lui-addressed access). The counter
does not show at level start, in the shop or in the inventory.

## 6. Floater start (presentation, per machine)

(p, w) = `mat4_transformPoint(g_viewProj, pos)`. Off-screen byte = 1 when w < 20, or
w × 700 < |p.x|, or w × 300 < |p.y|; it is never read. Screen x = p.x × (1/w) × 0.5 + 320,
y = p.y × (1/w) + 240, z = 0. d = (text x − x, y-table − y, −0), normalised with
`rsqrt(1, d·d)`. One cosmetic draw c = seed >> 16; k = (c × 2⁻¹⁶ − 0.5) × 9. Drift =
(d.y × k, −d.x × k, 0). Each displayed frame: `pos += vel`, then
`w = vel + (target − pos) × 0.0063659`, `vel = w − w × 0.0877665`
(`ref_hud_dynamic.gold_floater_step`). The amount is drawn as plain `%d`, no separators.

## 7. Separators (`ui_insertThousandsSeparators` 0x1c7128)

n = `libc_strlen`, g = (n − 1) / 3. Pass i (0..g−1): cur = cur % 3, or cur / 2 when that is
0 (cur starts as n); pos = cur + 4i; bytes pos..n+g shift right one; byte pos = separator.
So byte n+g+1 (one past the new terminator) is also written. Results: up to 8 digits the
usual grouping; 9 digits "1234,,56789"; "-123" → "-,123", "-1234" → "-1,234". Capped gold
never has 9 digits; a negative counter needs a wrapped +0xe4. Executed `sep`: random
amounts 0..99,999,999, edges, negatives, every language byte 0..255, raw digit strings of
length 0..15, 40 bytes of the buffer compared.

## 8. Text placement

Default font 0x44fdd8, layer 6, one batch. Slots 0/2: x = 50. Slots 1/3: x = 590 −
`text_widthAscii(font, text, 100000)` (0x181a60, a thunk to `font_measureAscii` 0x17ffb0,
docs/formats/ui-text.md section 4). y = 200 (slots 0, 1), 250 (2, 3). Coin `gold03.tex`
from `hud.lmp` at (16 or 593, y − 10), layer 6, after the text batch. Raw slot, no network
promotion. Painter order: HUD 2D packets are prepended per layer (hud-dynamic.md section
1), so the coins are painted under the text.

## 9. Constants

| Value | Address | Meaning | Evidence |
|---|---|---|---|
| 99,999,999 (0x5f5e0ff) | 0x1dc2f4/0x1dc2fc, 0x1dcc30/0x1dcc34 | gold cap | Executed |
| 0x80 | 0x1dcbc0 | credit delay: 3 × age ≥ 128 → 43 ticks | Executed |
| (p + 7) >> 3 | 0x1dcc1c–0x1dcc24 | payout per tick | Executed |
| 60 (0x3c) | 0x1dc7ac | hold frames | Executed |
| 4, 128 | 0x1dc9b4, 0x1dc9d4, 0x1dc9ac | alpha step, maximum | Executed |
| 3, 128, 0x81 | 0x1dc908, 0x1dc844, 0x1dc914 | floater alpha slope, start, clamp | Executed |
| 0x804080e4 / 0x4080e4 | 0x1dc75c, 0x1dc868, 0x1dc9f8 | text colour | Executed |
| 0x808080 | 0x1dcb20 | coin tint | Executed |
| −10 | 0x1dcb3c | coin y offset | Executed |
| 100000 (0x186a0) | 0x1dc958, 0x1dca68, 0x1dca94 | text length argument | Executed |
| "%d" 0x53c488 | 0x1dc7b0, 0x1dca1c | format | Executed |
| "hud.lmp" 0x53c388, "gold03.tex" 0x53c758 | 0x1dcb00, 0x1dcb08 | coin resource | Executed |
| 0x2c / 0x2e | 0x1c716c / 0x1c7170 | ',' / '.' | Executed |
| 20.0 0x41a00000 | 0x1dc380 | near limit for the off-screen byte | Executed |
| 700.0 0x442f0000, 300.0 0x43960000 | 0x1dc398, 0x1dc3b8 | edge factors | Executed |
| 0.5 0x3f000000, 320.0 0x43a00000, 240.0 0x43700000 | 0x1dc408, 0x1dc424, 0x1dc418 | screen mapping | Executed |
| 2⁻¹⁶ 0x37800000, 9.0 0x41100000 | 0x1dc480, 0x1dc494 | drift spread | Executed |
| 0.0063659 0x3bd099e0, 0.0877665 0x3db3be9b | 0x1dc808, 0x1dc830 | pull, damping | Executed |
| 50, 590, 50, 590 / 200, 200, 250, 250 / 16, 593, 16, 593 | 0x4f6730 / 0x4f6710 / 0x4f6720 | text x / y / coin x | O (image) |
| 128 | 0x307f1c | bonus-life alpha | Executed |
| 100 | 0x304e64 | first bonus-life price | O |

## 10. Executed

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_hud_gold.py --seed 20973` and `--seed 7`;
logs in `local/gold-seed20973.log` and `local/gold-seed7.log`. Every property compares
the state (8 floaters, pending, hold, alpha, gold of 4 records, cosmetic seed), stray stores
outside those (none) and the draw count of each of the three generators.

| Property | Seed 20973 | Seed 7 | Compared |
|---|---|---|---|
| sep | 7,134 checks | 7,132 checks | buffer after sprintf + separators |
| add | 3,000 (1,066 direct credit, 471 off-screen) | 3,000 (1,100 direct credit, 436 off-screen; 1,900 cosmetic draws) | state; 1,934 cosmetic draws = filled floaters |
| tick | 3,000 | 3,000 | state |
| flush | 1,000 | 1,000 | state |
| draw | 3,000 (7,158 counters, 2,053 right-aligned) | 3,000 (7,175 counters, 2,132 right-aligned) | call list with texts and arguments, state |
| bonus | 400 | 400 | alpha 128, lives +1, sound call |
| life | 400 sequences × 220 ticks (1,894 cosmetic draws) | 400 (1,869 cosmetic draws) | state after every tick; single pickup visible 133 frames |

Shared and third draws: 0 in every property. Cosmetic: exactly one per filled floater.

## 11. Unknown

- The ratio of displayed frames to ticks on the console. The hold is 60 **frames**, the
  delay 43 **ticks**. Settle with a frame/tick counter capture on hardware or PCSX2.
- Where in a tick `hud_run` runs relative to the toucher's `Player_run`. It does not change
  any credit (age 0 never credits) but decides whether the pickup tick's draw shows the
  floater. Settle by reading the run-task priorities of player objects against 50.
- Whether anything outside the lui-addressed scan reads the off-screen byte +0x21
  (pointer-based access would be missed). A memory watch in PCSX2 would settle it.
- Not executed here: `arena_runTask` 0x306b78 (the price test and spend around 0x3071c4, O only), `AutoChest_interact` 0x23b894 and `Chest_interact` 0x292a2c (O only), `Gold_onTouch` (executed on ctors-4 only).
- `font_measureAscii` widths of the default font: from the font data (ui-text.md).

## 12. Native client: what to implement (ranked)

1. **Floater records on every machine** at each `Gold_onTouch` / chest gold: first free
   of 8, start = tick, amount, slot; all busy → credit at once. Then `hud_tickGold` each
   tick: 43-tick delay, pending, `(p + 7) >> 3`, cap 99,999,999. This alone gives the
   original gold timing and keeps +0xe4 lockstep (Executed `add`, `tick`, `life`).
2. **The counter state machine** in the draw pass, local slots only: hold = 60 while a
   busy floater of the slot exists, then the ±4 alpha steps; draw at alpha > 0. Without it
   the counter never appears, which is today's native gap (Executed `draw`, `life`).
3. **The counter text**: `%d` of +0xe4, separators with ',' / '.' from the language byte
   (section 7, quirks included), colour alpha<<24 | 0x4080e4, layer 6, default font, x =
   590 − width for slots 1/3, y 200/250; coin `gold03.tex` at (16/593, y − 10), tint
   alpha<<24 | 0x808080 (Executed `draw`, `sep`).
4. **Level clear** zeroes hold and alpha and pays everything (`hud_flushGold`); the arena
   bonus life sets alpha 128 (Executed `flush`, `bonus`).
5. **The flying amount**: start from the camera projection, one cosmetic draw for the
   drift, per-frame pull/damp, alpha 128 − 3 × age, plain `%d` at the truncated position.
   It changes no shared state, so it may be approximated (Executed `add`, `draw`).
6. Chest gold (`AutoChest_interact`, `Chest_interact`) through the same floater (O).

## Proposed symbols

| Address | Name | Evidence |
|---|---|---|
| 0x307ee0 | `arena_giveBonusLife` | O: lives halfword +1, alpha 0x4f6950[slot] = 128, `bonuslife.vag`; Executed `bonus` |
| 0x86acd8 | `g_goldHold` (s32[4]) | Executed `draw` |
| 0x4f6950 | `g_goldAlpha` (s32[4]) | Executed `draw` |
| 0x86a900 | `g_goldFloaters` (move from 0x86a918) | O |
| 0x8e7358 | `g_arenaBonusLifePrice` | O 0x304e70, 0x3071a8 |
