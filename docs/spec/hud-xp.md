# Experience bar inputs and a new character's current health and mana

SLUS-20973 v2.00, 2026-10-21. Reference: [ref_hud_xp.py](../../tools/ref_hud_xp.py).
Tests: [test_ref_hud_xp.py](../../tools/test_ref_hud_xp.py) (synthetic),
[difftest_hud_xp.py](../../tools/difftest_hud_xp.py) (original code in ee_emu).

**Status:** the experience bar is Executed: its inputs, its edge cases, its texture
shape and the scissor the drawer builds. A new character's current health and mana are
Executed up to the first `player_recalcStats` that runs with a Player object attached.
`Player_ctor` itself was not executed (see Unknown).

## Part A: the experience bar

The bar is drawn by `hud_drawPlayerStatus` 0x1d9cd4 at 0x1da1dc–0x1da2bc, after the
health bar and its potion overlays and before the mana bar.

- It is drawn only when the slot is local and the acknowledged level (s8 +0x58) is
  above 0 (0x1da1e0). Offline every slot is local. Online, local means
  `net_isLocalSlot` 0x13e150 is true (0x1d9d60–0x1d9d90).
- Name: `bar_green%02d.tex` with frame `(sim_tick >> 2) % 11` (C remainder).
- Thresholds: upper = word at 0x41b558 + 4×ack (`T[ack]`), lower = word at
  0x41b554 + 4×ack (`T[ack-1]`). There is no bound check.
- Fill: `num = xp − lower` and `den = upper − lower` are 32-bit integer subtractions
  (they wrap). Each is converted to float. Then divide, multiply by 99.0, add
  float(X+15), truncate. No clamp.
- Submission to 0x17fb88: origin (X+15, 56), clip (X+15, 24, right, 124), tint
  0x80808080, layer 6, no flips.

Edge cases (Executed, `xp-edges`; S = X+15):

| Case | Result |
|---|---|
| ack 0 or negative | not drawn; mana bar still drawn |
| fresh character (ack 1, xp 0) | right = S, so the scissor keeps 0 columns |
| xp below lower | right < S: nothing visible |
| xp above upper (pending level, ack < +0x59) | right > S+99: whole bar visible (fills by the real xp, not the pending level) |
| ack 80, xp = T[80]−1 (the cap) | nearly full: T[80] is a sentinel, so the last level fills over T[79]..T[80] |
| equal thresholds | divide by zero gives ±0x7fffffff; right saturates to 0x7fffffff (num ≥ 0) or −0x80000000. The real table is strictly increasing, so this cannot happen with real data |
| ack 81..127 | reads words past the 81-word table. Not reachable while level ≤ 80 |

The clipped drawer 0x17b8b0 turns the clip into SCISSOR_1 (0x17baac–0x17bb7c).
Left and top below 0 become 0. Right ≥ 641 becomes 640. Bottom ≥ 448 becomes 447. Top
and bottom first lose the letterbox height (0x44fd70). In the interlaced arm (0x44fdd4
nonzero) the x endpoints are 2×left and 2×right−1, so the clip is half-open in logical
pixels. A full bar (right = S+99) shows 99 of the 100 columns. There is no lower clamp
on right: a negative right spills ones into the y fields (Executed). The source
rectangle is always (0, 0, 100, 6).

### bar_green textures (HUD.LMP, counts and shapes only)

| Item | Value | Evidence |
|---|---|---|
| entries | 11, bar_green00..10, first at lump offset 0x4d80, +0x680 each, 1616 bytes each | Observed 11/11 |
| used size (+0/+2) and source crop | 100×6, (0,0,100,6) | Observed 11/11; drawer Executed 11/11 (private) |
| pixel format | PSMT4 (4-bit), surface 128×8, TBW 2 | Observed 11/11 |
| GIF image upload | 104×8, PSMT4, buffer width 2 (2 rows and 4 columns beyond the used size) | Observed 11/11 |
| palette upload | 8×2 PSMCT32 (16 entries) | Observed 11/11 |
| field rows | 3 (used height / 2, the round-4 rule) | I |
| tex_relocate 0x179e10 | +0/+2 unchanged | Executed 11/11 (private), 1 shape in difftest |

The pairing is the same as the red and blue bars except the used height (6, not 8).
The model_info decoder decoded all 11 without error (private, `local/xp-real-headers.log`).

## Part B: current health and mana of a new character

Answer: when the first level's HUD can draw, **current health = maximum health and
current mana = maximum mana**, as computed by `player_recalcStats` with the Player object
attached. Before that the record holds 999999936.0 in both.

1. `player_initNewCharacter` 0x1b1d70: memset; +0xc4 = +0xc0 = 10.0 (0x1b20a0,
   0x1b20a8); +0x43d8 = 0 (0x1b21b0); +0xac = +0xb0 (0) and +0xc0 = +0xc4 (10.0)
   (0x1b22c4, 0x1b22d4); then +0xac = +0xc0 = 0x4e6e6b27 = 999999936.0 (0x1b23e8,
   0x1b23ec). Its `player_recalcStats` call (0x1b23f8) and the recalcs inside
   `player_giveStartingItems` skip the slot because +0x43d8 is 0 (0x1b64d8). So after
   creation: hp = mana = 999999936.0, max hp = 0, max mana = 10.0. Executed, all 12 models.
2. `Player_ctor` 0x1a1d28 stores the object at +0x43d8 (0x1a221c) and later calls
   `player_recalcStats` (0x1a2458). Observed. Level start reaches it from
   `mainloop_loadRequestedWorld` (0x321414); also `player_respawn`, `arena_startWave`,
   `cut_setup`.
3. That recalc computes the maxima and clamps: current = max only when max < current
   (0x1b6a24–0x1b6a48). Executed: current = max for every class.
4. The status HUD only draws for a slot with an object (0x1d9e64), so its first frame sees
   current = max: red and blue right = S+99; green right = S. Executed.

First-level values with the class-table statistics and real starting items (Executed,
both seeds; starting items carry no statistic modifiers, eff = base 15/15):
class 0 hp 33.5 mana 16.5; class 1 34.0/31.5; class 2 33.0/18.1; class 3 36.1/22.5;
class 4 32.4/42.5; class 5 37.4/17.4; class 6 32.8/36.7 (rounded; exact patterns from
the ps2 float model). A character made on the creation screen has other statistics; the
rule current = max is the same.

## Fields

| Field | Type | Writers | Readers | Evidence |
|---|---|---|---|---|
| record +0x58 ack level | s8 | init (1), `invmsg_dispatch` | HUD 0x1da1dc, 0x1da21c | O; Executed |
| record +0x5c experience | s32 | init (0), `player_giveExp` | HUD 0x1da244 | O; Executed |
| record +0xac hp | float | init 0x1b22c4, 0x1b23e8; recalc clamp 0x1b6a48; `player_respawn` 0x1bd134 (max, or max×0.5 when g_pvpModeA 0x4f711c is 0); `net_launchUpdate` 0x1373c0 (raised to max); arena 0x30586c, 0x305fd8, 0x306068 (= max); `player_giveExp` 0x1d3248; `player_rebuildAbilities` 0x1d377c/0x1d3784; import 0x1bd600; regen, damage, script and spell stores | HUD 0x1d9f24 | init, recalc, respawn Executed; net and arena O; others found by fieldxref, not read |
| record +0xc0 mana | float | init 0x1b20a8, 0x1b22d4, 0x1b23ec; recalc clamp 0x1b6a34; arena 0x305878, 0x306078; `player_giveExp` 0x1d324c; `player_rebuildAbilities` 0x1d37d8; import 0x1bd648; regen, Player_run, script, spells | HUD 0x1da318 | same |
| record +0xb0 / +0xc4 maxima | float | init (0 / 10.0), recalc | HUD, clamp | Executed |
| record +0x43d8 object | ptr | init 0x1b21b0 (0), `Player_ctor` 0x1a221c | recalc 0x1b64d4, HUD 0x1d9e54 | O; Executed |
| 0x41b558 g_expTable | s32[81] | data | HUD | Observed; T[0]=0, T[1]=1100, T[80]=9999999 |
| 0x4d8ae0 g_numPlayers | s32 | setup | recalc loop | Executed: slot ≥ count is not clamped |

## Calls (order) and seed draws

| Call | Shared / cosmetic / third | Evidence |
|---|---|---|
| 0x1d9cd4 HUD (callees except sprite sink, lookups, sprintf auto-stubbed) | 0 / 0 / 0 in its own body | Executed 418 + 29 calls per seed; stubbed callees (0x1dd270, 0x3054c4, text drawers and others) not measured |
| 0x179e10, 0x17fb88 → 0x17b8b0 | 0 / 0 / 0 | Executed (0x17ab50, 0x16b7f0, 0x19d9e4 stubbed) |
| 0x1b1d70 init, starting items real or stubbed | 0 / 0 / 0 | Executed 36 per seed (12 models with real items); no generator write from the starting-item descriptors |
| 0x1b6458 recalc with object (0x308a7c stubbed: feeds only resistances) | 0 / 0 / 0 | Executed |
| 0x1bd040 respawn (all callees stubbed, including Player_ctor) | 0 / 0 / 0 in its own body | Executed 60 per seed |

## Constants

| Value | Address | Meaning | Evidence |
|---|---|---|---|
| `bar_green%02d.tex` | 0x53c428 | name format | O |
| 11 | 0x1da1f8 | frames | Executed |
| 99 | 0x1d9eac | fill scale | Executed |
| 56, 24, 124, 6, 0x80808080 | 0x1da284, 0x1da2a0, 0x1da27c, 0x1da288, 0x1da280 | y, clip top/bottom, layer, tint | Executed |
| 640, 447 | 0x17bac0, 0x17bab8 | scissor clamps | Executed |
| 10.0 (0x41200000) | 0x1b2010 | init max mana and mana | Executed |
| 999999936.0 (0x4e6e6b27) | 0x1b23ac | init current hp and mana | Executed |
| 0.5 | 0x1bd118 | respawn hp factor outside PvP | Executed |

## Executed

`difftest_hud_xp`, both `--seed 20973` and `--seed 7` pass (`local/xp-seed20973.log`,
`local/xp-seed7.log`). Cases per seed: xp-draw 400 (317/345 drawn); xp-edges 18;
bar-green-drawer 296; new-character 36 inits (26/24 clamp checks, 10/12 unclamped,
18/14 first HUD frames); respawn 60.

## Unknown

- `Player_ctor` 0x1a1d28 was not executed; that no store between 0x1a221c and 0x1a2458
  changes +0xac/+0xc0 is from fieldxref only. Settle: run it with model loading stubbed.
- Starting items with a negative statistic reach a SYSCALL at 0x352e14 not modelled by
  ee_emu; not traced.
- Seed draws inside callees stubbed in the HUD and respawn runs.
- Hardware rounding of cvt.s.w, div.s and the ±max divide result: ee_emu model only.

## Native client: what to implement

1. Draw the green bar: PSMT4 104×8 upload, 8×2 PSMCT32 palette, sample (0,0,100,6) at
   (X+15,56), clip right from `xp_fill_right` (Part A table; Executed).
2. Starting current health and mana: hold 999999936.0 after creation and clamp to the
   recalculated maxima when the Player object is made; current = max on the first frame
   (Part B; Executed).
3. Use the half-open interlaced scissor: 99 of 100 columns at full, 0 at empty (Executed).
4. Respawn: health = max×0.5 offline, max in PvP; mana unchanged (Executed).
