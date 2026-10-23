# HUD quick slots: potion notices, D-pad selector, skill icons

SLUS-20973 v2.00, researched 2026-10-21 on `t3/research-hud-gaps`. Extends
[hud-dynamic.md](../hud-dynamic.md) sections 3 and 6 (the drawing of the notice lines
and of the ring). Reference: [ref_hud_quickslots.py](../../tools/ref_hud_quickslots.py);
synthetic tests: [test_ref_hud_quickslots.py](../../tools/test_ref_hud_quickslots.py);
emulator comparison: [difftest_hud_quickslots.py](../../tools/difftest_hud_quickslots.py).

**Status:** every store to the notice timer table is listed. The potion starters, the
potion counts, the selector's gates, fade, mask, ring, icons, button labels, the three
messages, the name text, the prompt and the character-sheet tail are Executed in
`tools/ee_emu.py` (seeds 20973 and 7). The camera, ammunition and thrown starters are
Observed here (the ammunition and thrown ones are also modelled in `tools/ref_player.py`).
Nothing was run on a game.

O = observed at the addresses given, I = inferred, U = unknown. `R` = player record
0x4d8af0 + 0x4c30 × slot, `P` = player object.

## 1. Notice timers

The eight lines (hud-dynamic.md section 3) are started by these stores. Each store
writes the timer, then calls `hud_countActiveNotices(slot, line)` 0x1dacf4 and stores
the result as the row (0x41b8a8 + same index). The draw never reads the row.

| Line | Frames | Store | Function | Condition (O) |
|---|---|---|---|---|
| 0 nocamera | 120 | 0x205d50 | `Camera_followZoomInput` | zoom input past its limit |
| 0 nocamera | 120 | 0x206378 | `Camera_followRotateInput` | rotate input above 0.5 |
| 1 nohealth | 120 | 0x1ba1a8 | `Player_usePotion` | kind 0, hp + pending < max, no health potion in bag 2 |
| 2 nomana | 120 | 0x1ba5a0 | `Player_usePotion` | kind 1, same for mana |
| 3 noarrows | 120 | 0x1a7650, 0x1a7e0c | `Player_run` | after a shot `R+0x4410` is 0; real player only (object flag 0x20000 clear); also `player_voice(slot, 5)` |
| 4 counthealth | 240 | 0x1ba0d8 | `Player_usePotion` | a health potion was used and `player_countPotions` returns 1..5 |
| 5 countmana | 240 | 0x1ba4bc | `Player_usePotion` | same for mana |
| 6 countarrows | 240 | 0x1a75d0, 0x1a7da0 | `Player_run` | ammunition stack `R+0x4410` holds 1..20 |
| 7 countthrown | 240 | 0x1a88bc | `Player_run` | thrown stack holds 1..20 after the throw (no copy test) |
| 7 countthrown | 240 | 0x1bb9ec | `Player_weaponSwapInput` | swap lands on weapon set 1 and its primary has class (+0x1e) 6 |
| 7 countthrown | 240 | 0x319cf0, 0x31a624 | `SkillFireAxe_cast`, `SkillColdAxe_cast` | conjured axe stack holds 1..20 |

Clearers: `player_initNewCharacter` 0x1b1f88 (all 16 words of the slot);
`menu_openInventory` 0x1c1720–0x1c172c (timers 3, 6, 7); the draw (−1 per frame,
row 0 at ≤ 0). `hud_resetNotices` 0x1e03c0 does not touch them (O).

**Not a notice starter:** `hud_showPlayerNotice` 0x1d9954 fills the per-player text box
(0x86aa70/0x86aa80/0x86aa98, flags 0x41b518 and 0x86aa90) for local slots only.
`Player_usePotion` calls it for the first-drink tutorial, kind ≥ 2 only (0x1b9d48).

**Simulation or draw.** All potion, ammunition, thrown and axe starters run inside the
simulation (`Player_run` and its callees) on every machine and for every slot, with no
local test. Only the camera starters are per machine. The timers and rows are never read
by simulation code (O, gxref over 0x41b828–0x41b95c), so a difference is harmless. One
real difference exists: with the inventory open on the owner's machine (`g_localMenuOpen`
0x41b69d, `net_isLocalSlot`, grid 0x4ebbb0) the potion is not taken from the stack at
once (`invmsg_sendDrop`), so that machine counts one more potion (Executed: the
`menu_path` cases of `use_potion`).

## 2. Potion counts and use

`player_countPotions(slot, kind)` 0x1ba5f8 sums the quantity (+4, s16) of every bag-2
cell (`R+0x2540`, 0x48 bytes each, count `R+0x3740`) whose definition name (def +0) equals
one of nine names. Kind 0 uses entries 9..17 of 0x4ef4c8 (the health names); any other
kind uses entries 0..8 (mana). The total goes to 0x41b950 when kind is 1, otherwise to
0x41b940, and is returned. Callers: `Player_usePotion` and the inventory handlers
(game-messages.md). The table holds the same 18 pointers as 0x4ef478 (health, smallest
first) and 0x4ef4a0 (mana) (Executed, 18 distinct names).

`Player_usePotion(P, kind, ...)` 0x1b9cb8, kinds 0 and 1 (player-tick.md 9.7 has the
rest):

```
if P.flags & 0x20000 or hp <= 0: return
R+0xb8 = min(maxhp * 1/480, 0x3effffff); R+0xbc = same from maxmana
if max <= cur + pending: return                    # full: no notice at all
found[i] = last bag-2 cell with name i (i = 0..8)
size = trunc(max - (cur + pending) + 1) / 60, at most 8
if found[size] < 0: size = 8 if found[8] >= 0 else largest present else -1
if size == -1: start line 1 (or 2), 120; return
pending += (size + 1) * 60, capped at max - cur
local: play potion_health.anm / potion_mana.anm
if g_localMenuOpen and local and grid: invmsg_sendDrop(...)
else: cell qty -= 1; at 0 inventory_removeItem(slot, cell, 2, 0)
n = player_countPotions(slot, kind); if 1 <= n <= 5: start line 4 (or 5), 240
R+0x120 = carried load over bags 0..2; use counter 0x4f85ca (health) / 0x4f85c8 (mana) += 1
```

The potion buttons: `Player_run` calls `Player_usePotion(P, 0, 0, 0, −1)` on potion A
(mask 0x41ba10[slot]) and `(P, 1, ...)` on potion B (0x41ba20[slot]) in the pressed word
of the slot's pad (player-tick.md section 3 item 6). These are game buttons from the
input record, not the D-pad.

## 3. Quick-cast selector input (`hud_spellSelect` 0x1dd270)

Callers: `hud_drawPlayerStatus` 0x1dacb8 with (slot, 0, 0, 0, 0); the skill screen
0x1d4cd8 with (slot, page, menu flag, kind, 64-bit value), "character-sheet mode".

Returns at once unless `net_isLocalSlot(slot)` and `R+0xac` > 0. The D-pad of the raw
local pad `g_rawPads` 0x4028d0 + 0x58 × slot (+8 held) is read only when none of these
is set, in this order (0x1dd374–0x1dd404):

| # | Gate | Address |
|---|---|---|
| 1 | `g_menuInputLockout` | 0x41b4fc |
| 2 | `dialog_isOpen()` | 0x22fbc0 |
| 3 | camera mode `g_localCamera`→+0x34 ≠ 1 | 0x4f8450 |
| 4 | `g_paused` | 0x41b4f4 |
| 5 | pause menu open (byte) | 0x44fa78 (set 0x18e3fc, cleared 0x18dfd4) |
| 6 | `memcard_isBusy()` | 0x217518 |
| 7 | `g_medalDialogTicks` | 0x4f7114 |
| 8 | `task_isRunning("jumpgate")` | 0x19e5e8 |
| 9 | input-block byte | 0x4f66c8 (only store found: 0 in `hud_addTasks` 0x1dc230) |

If any is set the pad is still read when `g_localMenuOpen` 0x41b69d is set. Right then
left set dx (+1/−1), up then down set dy; the later bit wins. Any direction bit calls
`net_maskLocalButtons(slot, 3, A|B|Use)` 0x13e540 with the slot's masks 0x41b990,
0x41b9a0, 0x41b9c0: entry 0x5d0bc8 + 12 × slot gets frames = max(old, 3), the mask,
and 0. So the A, B and Use presses do not reach the game while a direction is held.
`g_spellSelectorHeld` 0x41b818[slot] = 1 when dx, dy or menu mode, else 0 (0 again
when alpha reaches 0). `Player_run` skips `Player_interact` while it is 1.

Fade, direction and ring: hud-dynamic.md section 6 (record +0x4a74 float timer, +0x4a78
speed, alpha 0x86a8d8[slot]). The stored direction is `g_spellSelectorDir` 0x4f66b8;
a change plays `menu_spell_high.anm` from fx.lmp. Note that +0x4a74/+0x4a78 are written
from a draw task into the shared record.

**Buttons (direction ≠ −1).** The pressed word (+0xc) of the same raw pad:

| Mode | Button | Effect |
|---|---|---|
| HUD | A (0x41b990[slot]) | `hudmsg_sendQuickSlot(slot, 0, dir)`: message 0, bytes (0, slot, 0, dir) |
| HUD | else B (0x41b9a0) | message 0 with button 1 |
| HUD | else Use (0x41b9c0) | `hudmsg_sendQuickCastWarn(slot, dir)`: message 13, bytes (13, slot, dir) |
| sheet | accept (0x41b960, **entry 0 for every slot**, 0x1ddce8) | `hudmsg_sendAssignSpell(slot, dir, kind, value)`: message 1, 16 bytes |

Where the skill is cast: `hud_onQuickSlot` 0x1de28c writes `R+0x4a84` (button A) or
`R+0x4a85` (B), exchanging with the other button if it held the index. The A/B ability
buttons then use record `R+0x4440 + index × 0x68` in `Player_run` (player-tick.md
section 5 and state 2) and `Player_castSkill` 0x1a42b8. Message 13's handler 0x1de340
queues the record in `P+0x488` (state 2 only; kind-1 records only show a warning), which
`Player_run` casts as a forced record (game-messages.md). Both handlers run in the tick.

**Labels.** In HUD mode each ring position gets a text batch (`text_begin` font
0x4f7104, layer 7, colour A | 0x323c3c), and for button j = 0, 1 whose byte
`R+0x4a84+j` equals k the glyph of logical button j+1 (0x1df060). The glyph is
0x7b + i for the first i with `GLYPH_MASKS[i]` (0x53c8f0) equal to the slot's configured
mask `0x4f8f6c[slot][n]`; 0 (empty text) when none.

**Tail (direction ≠ −1).** Name: `text_lookup` of `EmptySpellSlot` (id −1), of
`<skill name>_name` (new-style record: `g_skillTable[id]`+0), or `<record name>_name`.
Drawn with `text_drawWideCentered(cx + 320 × page + 16, cy + 92, text, 1000000)`, colour
(alpha/2) << 24 | grey. HUD mode then formats `AssignCast` with the glyphs of logical
buttons 1, 2, 3 (`wstr_format` 0x19ea78) and calls `hud_drawPromptBox(text, 0x80, slot, 0)`.
**Sheet mode** (also when direction = −1): an icon at (320 × page + 141, 250), layer 6:
the skill's icon for kind 1, else the texture at 0x4f8674 (`icslam.tex`), none if 0; the
arrow again at layer 6 when direction ≠ −1; `spellbookparch.tex` (inventry.lmp) at
(320 × page + 57, 165), layer 6. Labels and the top arrow are skipped in sheet mode.

## 4. Skill icons

Ring position k shows ability record k (`R+0x4440 + k × 0x68`, records 0..7 of 15); the
quick map is simply the first eight records. For each (0x1dd8c4–0x1dd950):

- id (+0x20) = −1: the blank resref 0x86aa40.
- name equals `newstyle`: virtual slot 7 of `g_skillTable[id]` (table at skill+0x60,
  entry at +0x38: s16 this-adjust, function at +0x3c). The base 0x3c82c0 returns
  `res_find("icons.lmp", "icblank.tex")`; 71 classes have their own copy naming their
  icon (runtime.md), e.g. 0x3ccfb0 `icdiseasebolt.tex`.
- otherwise (older record): `0x4f85e0[id]`; when 0, the blank resref.

`hud_loadIcons` 0x1e7068 fills `0x4f85e0` from icons.lmp: index 25 `icroot.tex`, 28
`icfroststorm.tex`, 37 `icslam.tex`, and the notice icons 30–36 and 38. Other indices
stay 0. Resrefs set by `hud_staticInit` 0x1e08d0 → 0x1e07f0 (`resref_init` 0x173768):
0x86aa20 = hud.lmp/`hudbox.tex`, 0x86aa30 = hud.lmp/`spellbook.tex` (ring background),
0x86aa40 = icons.lmp/`icblank.tex`.

## Fields

| Address / offset | Type | Writers | Readers | Evidence |
|---|---|---|---|---|
| 0x41b828 + 0x20 × slot + 4 × line | s32 | section 1 | draw 0x1da8d8, 0x1dacf4 | O; Executed (lines 1, 2, 4, 5) |
| 0x41b8a8 + same | s32 | section 1 | none but the draw's clear | O; Executed |
| 0x41b940[slot] / 0x41b950[slot] | s32 | `player_countPotions` 0x1ba6f8 / 0x1ba6e0 | draw 0x1dab1c / 0x1dab38 | Executed |
| `R+0x2540`, `R+0x3740` | item[64], s32 | inventory | 0x1ba5f8, 0x1b9cb8 | Executed |
| `R+0xb4` / `R+0xc8` | float | `Player_usePotion` | regen | Executed |
| `R+0x4a74` / `R+0x4a78` | float / s32 | 0x1dd4f8, 0x1dd524, 0x1dd55c | selector | Executed |
| `R+0x4a84` / `R+0x4a85` | s8 | `hud_onQuickSlot` 0x1de28c | selector labels, `Player_run` | O |
| `R+0x4440 + k × 0x68` (+0, +0x20) | name, s16 id | `hud_onAssignSpell` 0x1de61c | selector icons and name | Executed |
| 0x41b818[slot] | s32 | selector | `Player_run`, `Player_draw` | Executed |
| 0x4f66b8[slot] | s32 | selector 0x1dd6ec | selector | Executed |
| 0x86a8d8[slot] | s32 | selector | selector | Executed |
| 0x5d0bc8 + 12 × slot | 3 × s32 | `net_maskLocalButtons` | input encoder | Executed |
| 0x41b960/0x41b990/0x41b9a0/0x41b9c0 | s32[4] masks | `game_initCamera` 0x1e6c3c (0x41b960) | selector | O |
| 0x4f8f6c | u32[4][9] | `config_setDefaults` 0x1e63b4 | 0x1df060 | Executed (glyph) |
| 0x4f85e0 | tex*[] | `hud_loadIcons` | notices, selector | O; Executed (lookup) |

## Calls (submission order, one HUD-mode drawn frame)

| # | Call | Seed draws | Evidence |
|---|---|---|---|
| 1 | `net_isLocalSlot`, gates 2/6/8 | 0 / 0 / 0 | Executed (stubbed) |
| 2 | `net_maskLocalButtons` | 0 | Executed (real) |
| 3 | `res_find` + `sound_playOnObject(menu_spell_high.anm)` on a change | stubbed; the sound path draws from the cosmetic generator, count **U** | O |
| 4 | arrow, background, per k: corona, icon, label batch | 0 | Executed |
| 5 | `hudmsg_send*` → `net_sendGameMsg` 0x13db38 | 0 (stubbed sender) | Executed |
| 6 | name text, `wstr_format`, `hud_drawPromptBox` | 0 (stubbed) | Executed (arguments) |
| — | `player_countPotions` | 0 | Executed |
| — | `Player_usePotion` | 0 (sound, removal, drop, load stubbed) | Executed |
| — | `0x1df060` glyph | 0 | Executed |

Shared 0x404464, cosmetic 0x404460 and third 0x404468: no write in any executed call.

## Constants

| Value | Address | Meaning | Evidence |
|---|---|---|---|
| 240 | 0x1ba0c4, 0x1ba4a8, 0x1a75c4, 0x1a7d94, 0x1a88a8, 0x1bb9d4, 0x319cdc, 0x31a610 | counted-line frames | O; Executed (0x1ba0c4, 0x1ba4a8) |
| 120 | 0x1ba194, 0x1ba58c, 0x1a763c, 0x1a7df8, 0x205d44, 0x206360 | "no" line frames | O; Executed (potion ones) |
| 1..5 | 0x1ba0b0, 0x1ba494 | potions left that show a count | Executed |
| 1..20 | 0x1a75b0, 0x1a7d80, 0x1a8894 | ammunition left that shows a count | O |
| 0x3b088888 (1/480), 0x3effffff | 0x1b9d3c, 0x1b9d64 | per-tick potion rate and its cap | Executed |
| 60.0 | 0x1b9f40, 0x1ba320 | potion size step | Executed |
| 3 | 0x1dd4a4 | mask frames while a direction is held | Executed |
| 0x7b | 0x1df0e4 | first glyph character | Executed |
| 100000 / 1000000 | 0x1ddbec / 0x1dde34 | label / name text width | Executed |
| (141, 250), (57, 165) | 0x1ddf60, 0x1de024 | sheet icon and parchment | Executed |
| +16, +92 | 0x1dde2c, 0x1ddc44 | name text offset from the centre | Executed |
| 0x80 | 0x1ddec8 | prompt box alpha | Executed |

## Executed

`tools/difftest_hud_quickslots.py`, seeds 20973 and 7 (logs in `local/`), all PASS:

| Property | Cases (20973 / 7) | What |
|---|---|---|
| count_potions | 400 / 400 | return and global, kinds 0/1/2, random bag 2; the 18 names distinct |
| use_potion | 600 / 600 | timers, rows, pending, rates, stack, removal, drop, sound, count, load, counter; notices started: lines 1/2/4/5 = 40/39/45/45 and 38/47/44/43 |
| glyph | 300 / 300 | 0x1df060 |
| gates | 80 / 80 | each gate alone and with `g_localMenuOpen`, four slots |
| selector | 1680 / 1680 frames | 24 runs (4 slots × offline/net × HUD/sheet page 0/sheet page 1); 1583 / 1597 drawn frames; every sprite, text batch, label, name, format, prompt, message, sound, the mask entry, alpha, timer, speed, direction, held flag and bust latch |

## Unknown

- Seed draws of the selector's sound (`sound_playOnObject` 0x214230 with
  `menu_spell_high.anm`) and of the potion sounds: run the sound path in ee_emu.
- Who sets byte 0x4f66c8 (only its clear was found): a write watch on a running game.
- Readers of `R+0x4a74`/`R+0x4a78` other than the selector (they are written from the
  draw task into the shared record): a field cross-reference over all code.
- The exact zoom and rotate conditions of the camera starters (line 0) were read only
  at the store sites; executing `Camera_followZoomInput` would settle them.
- Lines 3, 6, 7 were not executed here; `tools/ref_player.py` (`hud_notice`) models them
  inside `Player_run` for `tools/difftest_player.py`.

## Native client: what to implement

1. **Potion notices from the simulation.** In `Player_usePotion`, start line 1/2 for 120
   frames when no potion of the kind is in bag 2 (only when not full), and line 4/5 for
   240 frames after a use when 1..5 are left; keep 0x41b940/0x41b950 from
   `player_countPotions` (section 1, 2; Executed `use_potion`, `count_potions`).
2. **The draw side** already specified: decrement the timers per drawn frame for local
   slots and draw the 2 × 2 grid with the counts (hud-dynamic.md section 3).
3. **Potion buttons** are game buttons 0x41ba10/0x41ba20 decoded from the input record
   and handled in `Player_run` (player-tick.md 3.6); no D-pad involved.
4. **Ammunition and thrown starters** (lines 3, 6, 7; section 1 table, O) and the camera
   line 0 (per machine).
5. **Selector input:** read the local raw D-pad behind the nine gates (section 3), mask
   A/B/Use for 3 frames with `net_maskLocalButtons`, set `g_spellSelectorHeld`; on A/B
   send message 0 and on Use message 13 (Executed `gates`, `selector`).
6. **Ring icons:** record k of the first eight; Skill vslot 7 for `newstyle` records,
   `0x4f85e0[id]` for older ones, `icblank.tex` otherwise; background `spellbook.tex`
   (section 4; Executed `selector`).
7. **Tail:** name text, `AssignCast` prompt with button glyphs (0x1df060), and the sheet
   mode parchment and icon (section 3; Executed `selector`).
