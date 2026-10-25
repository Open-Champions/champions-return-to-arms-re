# HUD status block: bars and pending potion rectangles (`hud_drawPlayerStatus` 0x1d9cd4)

SLUS-20973 v2.00, researched 2026-10-21 on `t3/research-hud-gaps`.
Reference: [tools/ref_hud_status.py](../../tools/ref_hud_status.py). Synthetic tests:
[tools/test_ref_hud_status.py](../../tools/test_ref_hud_status.py). Comparison with the
original code: [tools/difftest_hud_status.py](../../tools/difftest_hud_status.py).
Companions: [hud-layout.md](../hud-layout.md), [hud-dynamic.md](../hud-dynamic.md),
[player.md](../player.md), [player-tick.md](player-tick.md).

**Status: Executed.** `difftest_hud_status` runs the original `0x1d9cd4` in
`tools/ee_emu.py` on constructed state, with `ui_drawRect` 0x17bd30 and `math_sin16`
0x1666e0 run as original code. Every clipped-sprite (0x17fb88) and rectangle (0x17bd30)
call matches the reference in call order, with all register and stack arguments, on seeds
20973 and 7. That closes the "not function-executed" note on the pending rectangles in
hud-layout.md. Text, notices and the spell selector are stubbed and not covered here.

Evidence words follow `CONTRIBUTING.md`: **O** observed at the address, **I** inferred,
**U** unknown, **Executed** (named property of `difftest_hud_status`). No game was run.
`R` is the player record `0x4d8af0 + slot*0x4c30`. `P` is the player object `R+0x43d8`.
`X` is the slot's HUD origin after network promotion (`hud_origins` in
`tools/ref_ui_layout.py`), and `S = X + 15`.

## 1. Gates before any draw

All Executed (property `gates`, each gate alone). Any one suppresses every draw, every
texture lookup, and the hit-flash clear. In code order (`0x1d9cdc–0x1d9ea4`):

1. `g_menuOpenFlag` 0x41b4f8 is nonzero.
2. `g_hudSuppressed` s8 0x4f66a8 is nonzero (0x80 counts too).
3. `g_shopOpen` 0x41b50c is nonzero.
4. The camera `*0x4f8450` has +0x34 other than 1 (0 and 2 tested).
5. `net_isSlotActive(slot)` 0x13dd40 returns 0.
6. `P` is null.
7. `P+0x540` (vehicle) is nonzero.
8. `g_dlCapacity` 0x44fda4 minus `(g_dlCursor - g_dlBase) >> 3` is below 3000.
   Exactly 3000 passes.

`ui_drawRect` makes the same 3000-unit test itself (0x17bd6c). Each rectangle packet takes
16 units (0x80 bytes). So with 3000 to 3015 units free, the second rectangle **call** is
made but writes no packet. Executed (`gates`: 30 such calls per seed). In the test the
sprite stub uses no space; in the game the bar sprites also use space before the
rectangles.

**Local flag** (`0x210(sp)`, `0x1d9d60–0x1d9d90`): true when `g_networkMode` 0x402791 is 0,
or when `net_isLocalSlot(slot)` 0x13e150 is true. Executed (`network`).

## 2. Calls in submission order

Only the rows marked "drawn" are compared one by one. Seed draws: Executed means writes
to 0x404460, 0x404464 and 0x404468 were counted around each `0x1d9cd4` call.

| # | Call | When | Arguments that matter | Seed draws | Evidence |
|---|---|---|---|---|---|
| 1 | `net_isSlotActive` 0x13dd40, `net_isLocalSlot` 0x13e150 | always (gates) | slot | stub; static scan: none | O |
| 2 | `lump_load` 0x173558 `hud.lmp` | always | — | stub; static: none | O |
| 3 | `net_isLocalSlot` per slot, then for slot 0 | net game | promotion loop | stub; static: none | O |
| 4 | `libc_sprintf` 0x3b7ef0, `lump_findEntry` 0x171de4 | always | `bar_red%02d.tex` | stub; static: none | Executed (names) |
| 5 | **drawn**: clipped sprite 0x17fb88, health bar | always | see section 3 | 0 | Executed |
| 6 | **drawn**: `ui_drawRect` 0x17bd30, pending health | section 4 gates | `(S+a, 47, right, 51, 6, 0x80000060)` | 0 (run) | Executed |
| 7 | **drawn**: `ui_drawRect` 0x17bd30, pending mana | section 4 gates | `(S+a, 66, right, 70, 6, 0x805a4632)` | 0 (run) | Executed |
| 8 | sprintf, lookup, **drawn** sprite: experience bar | local, s8 `R+0x58` > 0 | `bar_green%02d.tex` at `(S,56)` | 0 | Executed |
| 9 | sprintf, lookup, **drawn** sprite: mana bar | local | `bar_blue%02d.tex` at `(S,63)` | 0 | Executed |
| 10 | `math_sin16` 0x1666e0, name and level text (0x1800b8, 0x1802e0, 0x181af8, 0x180500, 0x3054c4, 0x1bf2a0, 0x1bdf60, 0x3b868c) | always | text; hud-dynamic.md | sin run: 0; text stubs; static: none | O |
| 11 | lookups `hud_statusbar00.tex`, `hud_multi.tex` | always, both | — | stub | Executed (names) |
| 12 | `resref_init` 0x173768 once, `res_find` 0x17365c, **drawn** glow sprite | local, `P+0xc` bit 0x8 clear, `R+0xac` > 0, `R+0x58` < `R+0x59` | `hud_statusbar00glow.tex` at `(X-4,36)` | 0 | Executed |
| 13 | **drawn**: frame sprite | always | local `hud_statusbar00.tex`, else `hud_multi.tex`, `(X-4,36)` | 0 | Executed |
| 14 | notices loop (0x17fb68 and text) | per active notice timer | ref_hud_dynamic | not run (timers 0) | O |
| 15 | `hud_spellSelect` 0x1dd270 | always | `(slot,0,0,0,0)` | stub; static: none | O |

**Seed draws.** Executed: 0 shared, 0 cosmetic, 0 third over every case of both seeds
(section 8). The stubs were not run. A static scan of the direct-call graph
(`ghidra_funcs.tsv` bodies, `jal`/`j` targets) found 277 functions reachable from 0x1d9cd4,
none of which addresses 0x404460, 0x404464 or 0x404468. Indirect calls (32 sites in that
set) were not followed, so this part is **I** for virtual calls.

## 3. Health and mana bar sprites

Executed (`offline`, `network`, `edges`, `caps`, `fields`). Clipped sprite arguments are
`(texture, x, y, layer, tint, left, top, right, bottom, flipX, flipY)`; the last three are
on the stack at +0, +8, +0x10.

| Bar | Texture | Origin | Clip | Layer | Tint |
|---|---|---|---|---|---|
| health | `bar_red%02d.tex` | `(S, 46)` | `(S, 24, fill(R+0xac, R+0xb0), 124)` | 6 | `0x80808080`; `0x80ffffff` when bit 0 of `0x41b930[slot]` is set |
| experience | `bar_green%02d.tex` | `(S, 56)` | `(S, 24, xpfill, 124)` | 6 | `0x80808080` |
| mana | `bar_blue%02d.tex` | `(S, 63)` | `(S, 24, fill(R+0xc0, R+0xc4), 124)` | 6 | `0x80acacac`; `0x2aacacac` when s16 `P+0x4ae` > 0 |

- Flip arguments are 0 and 0.
- The frame number is `(g_simFrame >> 2) % 11` with C remainder. A negative tick gives a
  negative number and a name such as `bar_red-1.tex`. Executed for the lookups. What the
  game does with that missing name is **U**; `g_simFrame` does not go negative in play (I).
- `fill(C, M) = trunc(float(S) + (C / M) * 99.0)`: divide, multiply, add, convert. There is
  no clamp. Negative C, C > M and tiny M were all run.
- `xpfill = trunc(float(S) + (float(exp - base) / float(next - base)) * 99.0)`, with
  `exp = R+0x5c`, `base = 0x41b554[ack]`, `next = 0x41b558[ack]`, `ack = s8 R+0x58`.
- Hit flash: the function clears bit 0 of `0x41b930[slot]` when it reads it set. Other
  bits stay. Executed (words 1, 2, 3, 0xffffffff).
- Cooldown is a signed compare: 0x8000 and 0xffff give alpha 0x80. Executed.
- A remote slot (local flag false) draws only the health bar and `hud_multi.tex`.

**Against `ref_ui_layout.hud_base_layers`.** Inside that function's domain (tick ≥ 0,
current ≥ 0, maximum > 0) the executed sprites, minus the glow, equal it exactly: 593 cases
(seed 20973), 627 (seed 7). `ref_hud_status` adds the rectangles, the glow, the stack
arguments, raw float patterns, and the inputs outside that domain.

## 4. Pending potion rectangles

Executed on every property. The rectangle is `ui_drawRect(x0, y0, x1, y1, layer, colour)`.
It reads no stack argument (O, 0x17bd30–0x17bf9c uses only the six register arguments).

**Gates** (`0x1d9f90–0x1da0e4`):

- `P+0xc` bit 0x8 (dead) clear. If it is set, both rectangles are skipped.
- Local flag true.
- Health rectangle: `R+0xb4 > 0.0`. Mana rectangle: `R+0xc8 > 0.0`. Each one is tested on
  its own. A zero or negative health pending value does not stop the mana rectangle.
- **There is no `health > 0` gate.** With the dead bit clear, a health of 0 or below still
  draws both rectangles. Executed: 196 such health rectangles with seed 20973, 201 with
  seed 7. The `health > 0` test belongs to the level-up glow only (call 12).
- **The mana rectangle has no gate the health one lacks.** It shares the dead-bit and
  local tests and adds only its own pending test.

**Arithmetic** (`0x1d9fd8–0x1da04c` health, `0x1da0e8–0x1da160` mana). C, M, p are the
float current, maximum and pending values.

```
a = trunc((C / M) * 99.0)
t = trunc(C + p)
if float(t) > M: t = trunc(M)
b = trunc((float(t) / M) * 99.0)
x0 = S + a
x1 = min(S + b, cap[raw slot])        caps 180, 605, 333; every other slot 447
y0, y1 = 47, 51 (health)  or  66, 70 (mana);  layer 6
```

- `trunc` saturates on overflow, as `ref_core.to_int`. Sums past 2^31 were run.
- The cap uses the raw slot, not the promoted origin (`0x1da050–0x1da0ac`,
  `0x1da164–0x1da1c0`).
- **The caps never bind with the shipped origin table.** Because `float(t) ≤ M`, `b ≤ 99`.
  The largest right edge is `X + 114`, and every reachable `X` for a local slot is below
  its cap minus 114. A non-local slot 0 has a promoted X but draws no rectangle. The
  property `caps` overwrites the table 0x53c408 to reach them: 318 (seed 20973) and 335
  (seed 7) rectangles ended at the cap.
- `x1 < x0` happens. Causes: truncating `C + p` below a fractional C, or C > M. Offline with seed 20973: 206 inverted and
  47 empty. The original passes such rectangles on unchanged.
- **Packet** (Executed, every rectangle): two XYZ2 words at packet +0x60 and +0x70.
  Interlaced (`0x44fdd4` nonzero) `X = 32x + 0x5800`; otherwise `X = 16x + 0x6c00`;
  `Y = 16y + 0x7200`; Z = 0xa. The colour is the RGBAQ word at +0x20 and the layer goes to
  `gfx_addSortedPacket`. The fields are combined with OR on sign-extended values. A corner
  with negative X (x below −704 interlaced) sets every bit of Y and Z. Executed in
  `offline` and `network`. A native port should treat such a rectangle as undefined, not
  as clipped.
- **Row convention.** The arguments are two corners. y1 is 51, not a height. Under the GS
  sprite rule a sprite covers `[Y0, Y1)` (I / high; render-pipeline.md and ui-parity.md
  section 1). So the health rectangle covers rows 47–50 and the mana one 66–69, four rows
  each, inside the 8-row bars at 46 and 63. Field parity in the interlaced path is not
  modelled (**U**, see unknowns).

## 5. Fields

The record and object offsets were Executed as the full read set of the function in the
`fields` property (`emu.reads`). Record: +0x58/1, +0x59/1, +0x5c/4, +0xac, +0xb0, +0xb4,
+0xc0, +0xc4, +0xc8, +0x43d8. Object: +0xc/4, +0x4ae/2, +0x540/4. `R+0` (name) is read by
a stubbed callee.

| Offset | Type | Writer(s) | Reader here | Evidence |
|---|---|---|---|---|
| `R+0x58` | s8 | `invmsg_dispatch` 0x1bfdb0 (player.md) | XP gate, XP table index, glow | Executed |
| `R+0x59` | s8 | stats / level-up (player.md) | glow gate; level text | Executed |
| `R+0x5c` | s32 | `player_giveExp` 0x1d3150, import | XP fill | Executed |
| `R+0xac` | float | damage, `Player_regenHealth` 0x1b3b90 (player-tick.md 4) | health fill, pending health, glow | Executed |
| `R+0xb0` | float | stats (player.md) | health fill, pending health | Executed |
| `R+0xb4` | float | `Player_usePotion` 0x1b9cb8 sets it; `Player_regenHealth` lowers it by `R+0xb8` | health rectangle gate and length | Executed |
| `R+0xc0` | float | `Player_regenMana` 0x1b3900, spell cost (player-tick.md 9) | mana fill, pending mana | Executed |
| `R+0xc4` | float | stats | mana fill, pending mana | Executed |
| `R+0xc8` | float | `Player_usePotion`; `Player_regenMana` lowers it by `R+0xbc` | mana rectangle gate and length | Executed |
| `R+0x43d8` | ptr | player object link | gates; `P` | Executed |
| `P+0xc` | u32 | object flags; 0x8 = dead (objects.md) | rectangle and glow gate | Executed |
| `P+0x4ae` | s16 | `Player_castSkill` 0x1a42b8 and use paths; minus 1 per tick (player-tick.md 8) | mana tint | Executed |
| `P+0x540` | ptr | vehicle (player.md) | gate | Executed |
| `0x41b930[slot]` | u32 | `Player_takeDamage` ORs bit 0 (drawsim.tsv) | health tint; bit 0 cleared here | Executed |
| `0x86aa50[slot]` | s32 | this function (+4, cap 128); `hud_run` resets (hud-dynamic.md) | glow alpha | Executed |
| `0x41b554[ack]`, `0x41b558[ack]` | s32 | level table (data) | XP fill | Executed |
| `0x53c408[4]` | s32 | data, values 12, 478, 167, 323 | origin X | Executed (overwritten in `caps`) |
| `0x44fdcc` | s32 | `g_simFrame` | bar frame, pulse | Executed |
| `0x44fdd4` | s8 | display mode (see difftest_ui_r4) | rectangle X formula | Executed |
| `0x402791` | s8 | `g_networkMode` | local flag, promotion | Executed |

## 6. Constants

| Value | Address | Meaning | Evidence |
|---|---|---|---|
| 99 (as float) | 0x1d9eac | fill span, also used for pending a and b | Executed |
| 15 | 0x1d9eb0 | `S = X + 15` | Executed |
| 46, 56, 63 | 0x1d9f64, 0x1da284, 0x1da35c | health, XP, mana bar y | Executed |
| 24, 124 | 0x1d9f70, 0x1d9f5c | clip top and bottom of every bar | Executed |
| 6 | 0x1d9f68, 0x1da0bc, 0x1da1d0 | sort layer of bars and rectangles | Executed |
| 0x80 / 0xff | 0x1d9eb4 / 0x1d9ee0 | health RGB normal / hit flash | Executed |
| 0xacacac, 0x80, 0x2a | 0x1da34c, 0x1da2f4, 0x1da308 | mana RGB, alpha, cooldown alpha | Executed |
| 0x80808080 | 0x1da298, 0x1da7dc | XP and frame tint | Executed |
| 11 | 0x1d9ef0 | animation frames | Executed |
| 47, 51, 0x80000060 | 0x1da0b4, 0x1da0b8, 0x1da0c4 | health rectangle y0, y1, colour | Executed |
| 66, 70, 0x805a4632 | 0x1da1c8, 0x1da1cc, 0x1da1d8 | mana rectangle y0, y1, colour | Executed |
| 180, 605, 333, 447 | 0x1da058–0x1da060, 0x1da078–0x1da080, 0x1da094–0x1da09c, 0x1da090–0x1da0ac | right cap by raw slot 0, 1, 2, other | Executed (`caps`) |
| 0x8 | 0x1d9fac | dead bit in `P+0xc` | Executed |
| 3000 | 0x1d9e9c, 0x17bd6c | free display-list units needed | Executed |
| 16 units (0x80 bytes) | 0x17bda0–0x17bf30 | one rectangle packet | Executed (`gates`) |
| 0x5800, 0x6c00, 0x7200, 0xa | 0x17be48, 0x17be68, 0x17be4c, 0x17bea0 | GS X (interlaced / not), Y offset, Z | Executed |
| −4, 36, (0,0,1000,1000) | 0x1da7d0, 0x1da7d4, 0x1da7e0 | frame and glow origin and clip | Executed |

## 7. Vectors for the native client

`python3 tools/ref_hud_status.py --vectors N [SEED]` prints N rows from the reference
alone. `python3 tools/difftest_hud_status.py --seed S --vectors FILE` writes only rows
whose case passed against the original code (2,696 rows per seed: `offline`, `network`,
`edges`, `caps`). Tab-separated. Float inputs and colours are `0x`-prefixed 32-bit hex.

Input and effect columns, in order: `slot` (raw), `x` (promoted origin X), `local` (0/1),
`obj_flags` (`P+0xc`), `health`, `health_max`, `health_pending`, `mana`, `mana_max`,
`mana_pending` (patterns of `R+0xac..0xc8`), `tick`, `flash` (`0x41b930[slot]` before),
`cooldown` (s16), `ack_level`, `level` (s8), `exp`, `exp_base`, `exp_next`, `glow_alpha`
(before), `new_flash`, `new_glow_alpha`, `count`.

Then `count` groups of 12: `kind` (`S` sprite or `R` rectangle), `resource` (`-` for R),
`x0`, `y0` (sprite origin; rectangle first corner), `x1`, `y1` (rectangle second corner;
`-` for S), `layer`, `tint`, `clip_left`, `clip_top`, `clip_right`, `clip_bottom` (`-`
for R). Groups are in call order. Reverse them within a layer for painter order
(hud-layout.md). Gates of section 1 are the caller's job and are not in the rows.

## 8. Executed

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_hud_status.py --seed N`, both seeds pass.
Logs: `local/status-seed20973.log`, `local/status-seed7.log`.

| Property | What varies | Cases 20973 / 7 | Pending rects compared 20973 / 7 (health + mana) |
|---|---|---|---|
| `offline` | slots 0–3, all inputs random, interlace 0/1 | 1500 / 1500 | 1312 (674+638) / 1344 (682+662) |
| `network` | 1–4 players, random local set, promotion | 800 / 800 | 295 (150+145) / 315 (155+160) |
| `edges` | C = 0, p past M, M = 0.5 and 1e-30, C > M, health ≤ 0, dead bit, 3e9 sums | 96 / 96 | 80 (40+40) / 80 (40+40) |
| `caps` | origin table overwritten | 300 / 300 | 600 (300+300) / 600 (300+300) |
| `gates` | each gate; free units 2999–3017 | 170 / 170 | 120 (60+60) / 120 (60+60) |
| `fields` | read set | 8 / 8 | 16 (8+8) / 16 (8+8) |
| **total** | | 2874 / 2874 | **2423 / 2475** |

Sprites compared: 10,080 (seed 20973) and 10,090 (seed 7). Rectangle packets decoded: 2,393
and 2,445 (the other 30 per seed are the inner-gate calls). Seed draws: 0 on every
generator in every case. Unit tests: `python3 -m unittest tools/test_ref_hud_status.py`.

## 9. Unknown

- **Field parity of the rectangles.** The GS row coverage under interlaced field rendering
  (which field rows 47–50 land in) is not executed. A GS-level capture, or the
  render-pipeline field model applied to the packet, would settle it.
- **GS sprite with x1 < x0.** Whether the GS draws nothing or a swapped rectangle is not
  established here. A GS rasteriser test (or PCSX2 capture) with such a packet would
  settle it.
- **Indirect calls from the stubbed callees.** 32 indirect call sites were not followed
  in the seed scan. Running the text and selector callees in the emulator would settle it.
- **Negative tick lookup.** A `bar_red-1.tex` lookup returns 0 in a real lump; what the
  next load does then is untested.
- **Dead bit versus health ≤ 0 in play.** How soon a player with health ≤ 0 gets object
  flag 0x8 is not settled here. Tracing the writers of `P+0xc` bit 0x8 for players would.

## 10. Native client: what to implement

1. **Gate pending rectangles on the dead bit, not on health > 0.** Both rectangles need:
   local slot, `P+0xc & 0x8 == 0`, and their own pending > 0. The play HUD now returns
   when `hp <= 0` (godot/ui/play_hud.gd `_add_pending`), and that also hides the mana
   rectangle. Section 4, Executed. If the dead bit is not available, say so; do not
   substitute health.
2. **Keep `hudPendingRects` arithmetic as it is.** All 9 rows of
   `native/tests/vectors/hud_pending.tsv` equal this reference, which equals the executed
   original. Section 4.
3. **Drop the input refusals the original does not have.** Negative current and
   current > maximum are drawn (inverted or empty rectangles). Pass inverted rectangles to
   the renderer as the original does, or document the policy. Section 4, Executed.
4. **Regenerate vectors from this reference** (section 7). They cover the bars, glow and
   frame too, and include the `caps` rows, the only rows where the caps change output.
5. **Mana bar and hit flash.** Cooldown is the signed s16 `P+0x4ae > 0` (alpha 0x2a); the
   flash is bit 0 of `0x41b930[slot]`, consumed by the draw. Section 3, Executed.
6. **Rectangle rows are corners.** Draw rows 47–50 and 66–69 (half-open `[y0, y1)`).
   Section 4, I / high.

## 11. Corrections to earlier documents (proposed)

| Document | Says | Should say | Evidence |
|---|---|---|---|
| hud-layout.md, "Known partial contracts" | pending rectangles "not function-executed" | Executed: `difftest_hud_status`, 2,423 / 2,475 rectangles on seeds 20973 / 7 | section 8 |
| hud-layout.md, same | "Health Y=47..51" | corners y0 = 47, y1 = 51; covered rows 47–50 (GS rule, I) | section 4 |
| open-champions play_hud.gd | pending drawn only while health > 0 | gate is the dead bit; health ≤ 0 still draws both | section 4 |
