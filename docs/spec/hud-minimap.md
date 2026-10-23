# Minimap projector `0x168cac` (automap drawer)

SLUS-20973 v2.00, 2026-10-21. Model: [ref_hud_minimap.py](../../tools/ref_hud_minimap.py),
tests: [test_ref_hud_minimap.py](../../tools/test_ref_hud_minimap.py), difftest:
[difftest_hud_minimap.py](../../tools/difftest_hud_minimap.py). Extends
[hud-dynamic.md](../hud-dynamic.md) sections 9 and 10.

**Status:** the EE side of `0x168cac` is executed byte for byte: every display-list byte,
every call and every store. The map tiles themselves are drawn by a VU1 program
(`0x403e20`, loaded at micro address 0x79a). That program was read (O) but not executed;
ee_emu has no VU. No game or emulator was run.

## Body and arguments (O, Executed)

The body is `0x168cac..0x16a4b0`. There is one return (`0x16a4a8`), which agrees with
ghidra_funcs.tsv. The only caller is `minimap_draw` at `0x1e4d00`.

| Register | Meaning | Source in `minimap_draw` |
|---|---|---|
| a0 | `g_world` (+0x6c = the automap tile texture) | `0x44fdc8` |
| a1 | pointer to (x, y): the local camera's +0x18 and +0x1c | `g_localCamera` 0x4f8450 |
| a2 | callback, always `minimap_blipColor` 0x1e40a8 | immediate |
| a3 | s16 yaw from `Camera_getYaw` 0x207450 (camera +0x68) | local camera |
| f12, f13 | offsets x, y (`0x86af5c`, `0x86af60`) | chased, section 9 |
| f14 | zoom = scale × `0x4f71a0` | |
| f15, f16 | half width and half height (`0x86af64`, `0x86af68`) | |
| f17 | blip size (`0x53e208[mode]`: 6, 5, 5) | |
| f18 | icon size (`0x53e1f8[mode]`: 16, 10, 10) | |

## What it does, in order

1. **Gate** `0x16a838` (Executed): draws nothing if world +0x6c is 0, if fewer than 12000
   display-list units are free, or if trunc(half width) < 2. So mode 2 hides the map.
2. Reads EE timer 0 (`0x10000000`) for profiling.
3. **Scissor**: x0 = trunc(offx − hw) + 320, x1 = trunc(offx + hw) + 320, y0/y1 =
   trunc(offy) ∓ trunc(hh) + 220, clamped to 0..639 and 0..447. In GS units x is doubled.
4. **Rotation**: c = cos16(−yaw), s = sin16(−yaw). Pixels per cell: column step
   (c·7.5·z, s·7.5·z), row step (s·7.5·z, −c·7.5·z). World → cell is
   origin + world·0.25·(1/30) (`0x16a7dc`, the origin is `0x4044a8/ac`). The centre cell
   is placed at (offx, offy) from the screen centre (320, 224).
5. **Visible cell range**: radius r = trunc(hw)·1.333 / z · 0.1333 cells. Columns
   floor(max(cx − r − 1, 0)) .. ceil(min(cx + r, W)); rows the same with H
   (`0x4044dc`, `0x4044e0`). floor is libm `0x3a53c0`, ceil is `0x3a51b0` (Executed). An
   empty range returns without updating the counters.
6. **A. Blips**, only when z > 0.125. One packet. The callback is called with index
   0, 1, ... until it returns −1; 0 means skip. For each accepted object it draws a shadow
   triangle (PRIM 0x43, colour 0x60000000, +2 px down and right) and then the coloured
   triangle (PRIM 3, colour 0x80bbggrr). Shape from `0x404470`: (0, −1), (−0.75, 1),
   (0.75, 1) × blip size × the callback's scale. It is rotated by yaw + object +0x38 −
   0x3fff. Layer 5, texture 0.
7. **B. Map icons**: for each of `0x6e14d0` entries of the table `0x6e0f90` (stride 0x1c).
   An entry with a name at +0x14 is skipped when `vars_get` returns 0. An entry with a
   name at +0x18 is skipped when `script_runByName` returns 0. Otherwise one textured
   strip is drawn (PRIM 0x154): the position at +0/+4, the texture at +8 (s16 w, h), and
   +0xc = rotate with the camera. Corners come from `0x404488`, × size × 0.75. UV comes
   from `0x4044b0` × (w, h). Alpha = min(explored nibble of that cell << 4, 0x80), with
   rgb 0x808080. One packet per icon, layer 5, with the icon texture.
8. **C. Map strips**: one packet per 30 columns, with the start advancing by 29. Each
   packet carries GS state (TEX1 1, ZBUF = `0x44fd60`, TEST 0x3001c, colour 0x80808080,
   DIMX), then a DMA ref to the VU program `0x403e20` (102 instructions, MPG at 0x79a).
   It uploads a 15-qword block: cell origin in GS units (2·x + 2048, y + 2048), the
   column and row steps, tile UV extent 9.9, a GIF tag (PRIM 0x15c, 12 registers), the
   count, and eight orientation orders. Then MSCAL 0x79a. Then, per row, the raw cells
   (`memcpy` from `0x4044f0` + row·0x1b0 + col·2) as UNPACK V2-8 into the double buffer
   0x200/0, each followed by MSCAL 0x79c. It ends by restoring DIMX and the full scissor.
   Layer 5, texture = world +0x6c.
9. Adds the elapsed timer ticks to `0x4044d4` and increments `0x4044d8`.

**VU program (O, read only).** Per cell: tile index = cell bits 0–4 (u) and 8–11 (v),
×10 texels plus 0 or 9.9 per corner; orientation = cell bits 5–7, which picks one of the
eight vertex orders; colour (255, 255, 255, cell high byte). So the explored nibble
(bits 12–15) sets the alpha. Four corners per cell, emitted as one strip, then XGKICK.
**Not executed: `0x403e20..0x404150` (VU1 micro code).**

## Fields

| Address / offset | Type | Writer | Reader | Evidence |
|---|---|---|---|---|
| world +0x6c | ptr, automap texture | loader | gate, strip packets | Executed |
| `0x4044a8/ac` | float, cell origin | level load | 0x16a7dc, prologue | Executed |
| `0x4044dc/e0` | int, grid W/H | `automap_loadGrid` | prologue | Executed |
| `0x4044f0` | 216×216 u16 cells | load, reveal | icon alpha, strip upload | Executed |
| `0x6e0f90 + i·0x1c` | icon {x, y, tex, rotate, scale/value at +0x10, var, script} | `0x1689a4` from `PushTrigger_ctor` 0x1eca64, `JumpGate_ctor` 0x27c834, `Savepoint_ctor` 0x28ccf0 | phase B | O; projector Executed (+0x10 unread by projector) |
| `0x6e14d0` | icon count | `0x1689a4` increments at 0x168c64; `0x168990` clears | phase B | O; projector Executed |
| `0x6e14d4` | reveal-all flag | `automap_revealAll` 0x16a7d8 sets 1; `0x168990` clears | `minimap_draw` 0x1e4ae8 picks 960 or 3840 query radius | O; feed Executed (`difftest_hud_inputs.py`) |
| `0x44fd74/78` | full scissor y0, y1 | frame setup | packet ends | Executed |
| `0x44fd60` | ZBUF value (`g_zbufNoWrite`) | | strips | Executed |
| `0x44fe10` / `0x44fe0c` / `0x44fda4` | cursor / base / capacity | | gate, all | Executed |
| `0x4044d4/d8` | profile ticks / calls | this | U | Executed |
| `0x4f867c` | object list for the callback | `minimap_draw` | 0x1e40a8 | Executed |

## Calls (in order)

| Call | When | Seed draws |
|---|---|---|
| `0x16a838` gate | always | none, Executed |
| cos16, sin16, sin16, cos16 of −yaw | drawn | none, Executed |
| 0x3aef58 → floor/ceil → 0x3afac0, ×4 | drawn | none, Executed |
| callback 0x1e40a8 (i = 0..end) | z > 0.125 | none, Executed (vtable +4, 0x3c3ab8, 0x3b1250 stubbed) |
| 0x16a7dc, cos16, sin16 per blip | accepted | none, Executed |
| `gfx_addSortedPacket`(P, 5, 0, 0, 0) | blips | stubbed; U |
| `vars_get`, `script_runByName` per icon | names set | stubbed; **script may draw: U** |
| `gfx_addSortedPacket`(P, 5, tex, 0, 0) | per icon | stubbed |
| `memcpy` per row; `gfx_addSortedPacket`(P, 5, world+0x6c, 0, 0) per strip | | memcpy none, Executed |

The measured draws over all cases were shared 0, cosmetic 0, third 0, and the model
predicts 0. No store landed outside the display list, `0x44fe10` and `0x4044d4..db`.

## Constants

| Value | Address | Meaning |
|---|---|---|
| 1.333 (0x3faa9fbe) | 0x168e88 | radius aspect |
| 0.25, 1/30 (0x3d088888) | 0x168eb0, 0x16a7f0 | world → cell (1/120) |
| 7.5 | 0x168ed4 | pixels per cell at zoom 1 |
| 0.1333 (0x3e088888) | 0x168f00 | pixels → cells |
| 0.125 | 0x16904c | minimum zoom for blips |
| 320, 220; 639, 447 | 0x168dec, 0x168da0; 0x168d80, 0x168dbc | scissor centre, clamp |
| 12000 | 0x16a868 | minimum free display list |
| 2.0, 16, 32, 32768 | 0x169308..0x16932c | shadow offset, 12.4 fixed (x doubled), GS origin |
| 0.75 | 0x1698c4 | icon half size factor |
| 9.9, 2048 | 0x169f18, 0x169eec | tile UV extent, GS origin (VU block) |
| 30, 29 | 0x169ca4, 0x16a404 | strip width, strip step |
| 0x43, 3, 0x154, 0x15c | 0x169254, 0x1693e8, 0x1697e4, 0x169fb0 | PRIMs |
| 0x60000000, 0x808080, 0x80808080 | 0x169264, 0x1698e0, 0x169d48 | colours |
| 0x3001d / 0x3001c, 0x61 / 1, 0x44 | header code | TEST, TEX1, ALPHA |
| tables `0x404470`, `0x404488`, `0x4044b0` | .data | blip shape, icon corners, icon UV |

## Executed

`python3 tools/difftest_hud_minimap.py --seed 20973` and `--seed 7` (logs in local/), all ok:

| Property | 20973 | 7 |
|---|---|---|
| libm_floor_ceil | 600 | 600 |
| gate_16a838 | 300 | 300 |
| cell_16a7dc | 300 | 300 |
| draw_168cac (Python callback) | 200 (185 drew, 406 blips, 107 icons, 472 strips) | 200 (187, 385, 128, 513) |
| draw_with_blipColor (original 0x1e40a8) | 100 (170 blips) | 100 (163 blips) |

## Per machine vs simulation

Everything that positions the map is **per machine**: the local camera position and yaw,
`0x4f71a0` zoom, the mode `0x4f8400`, and the explored bits in `0x4044f0`. The blip list
comes from `world_collectObjectsInBox` around the local camera, with `net_objOrGhost`
applied. **Simulation risk:** phase B calls `vars_get` (it appends unknown names to
`g_questVars`) and `script_runByName` from draw code, on one machine only.

## Unknown

- What the VU program at `0x403e20` computes, numerically: needs a VU1 interpreter.
- The atlas layout of world +0x6c (10-texel tiles assumed from the code): decode one .world.
- `gfx_addSortedPacket` was stubbed. Whether it moves `0x44fe10` was not run.
- Whether icon scripts draw from a generator: depends on the script; it was stubbed.
- The icon table writer is `0x1689a4` (O, three constructor callers above). The
  projector does not read +0x10; what other consumers do with it is Unknown.

## Native client: what to implement

1. Gate and scissor (steps 1, 3): skip when hw < 2; clip to the computed rectangle.
   Executed.
2. Rotation and cell transform (steps 4–5): cells of 120 units, 7.5·z pixels per cell,
   rotated by −yaw, centred at (320 + offx, 224 + offy). Executed.
3. Blips (step 6) with `minimap_blipColor` colours: shadow then colour triangle. Executed.
4. Tiles: draw the visible cells from `0x4044f0` with the world +0x6c atlas, orientation
   bits 5–7, and alpha = the cell's high byte. EE packet Executed; VU arithmetic O only.
5. Icons (step 7): needs the icon table and a safe answer for the `vars_get` and script
   gates (do not run scripts from draw online). Executed for the packet.
