# HUD gaps: what the native client still needed, and what it should build first

SLUS-20973 v2.00, researched 2026-10-21 on `t3/research-hud-gaps` (research-ui `3e39392`
merged in). This page is an index and a ranking. The evidence is in the five spec
documents below; every address and constant cited here is in their tables, with its
evidence label. Nothing here was run on a game. "Executed" means `tools/ee_emu.py` ran the
original function on constructed state, and a reference model matched it on seeds 20973
and 7.

The gaps come from the native reports `hud-overlay` round 1 and `player-state`
rounds 1 and 2 (open-champions). Their refusals were: the minimap projector,
unexecuted pending rectangles, XP bar art pairing, created-character current mana, the
gold counter gate, and the belt/quick-cast inputs.

| Topic | Spec | Reference / tests / difftest | Executed cases (seed 20973 / 7) | Seed draws |
|---|---|---|---|---|
| Pending health/mana rectangles, health and mana bars | [spec/hud-status.md](spec/hud-status.md) | `ref_hud_status`, `test_ref_hud_status`, `difftest_hud_status` | 2,874 / 2,874 states; 2,423 / 2,475 rectangles; 10,080 / 10,090 sprites | none on any generator |
| XP bar, `bar_green` pairing, starting current health/mana | [spec/hud-xp.md](spec/hud-xp.md) | `ref_hud_xp`, `test_ref_hud_xp`, `difftest_hud_xp` | 400 draws (317 / 345 drawn), 18 edges, 296 drawer, 36 inits, 60 respawns | none in run calls |
| Gold counter and its producers | [spec/hud-gold.md](spec/hud-gold.md) | `ref_hud_gold`, `test_ref_hud_gold`, `difftest_hud_gold` | 7 properties: 17,534 / 17,532 checks, plus 400 runs x 220 ticks | cosmetic: one per filled floater, on every machine; shared and third: none |
| Quick slots: potion notices, D-pad, ring icons | [spec/hud-quickslots.md](spec/hud-quickslots.md) | `ref_hud_quickslots`, `test_ref_hud_quickslots`, `difftest_hud_quickslots` | 1,380 cases plus 1,680 selector frames (1,583 / 1,597 drawn) | none; the stubbed sound call's cosmetic draws are U |
| Minimap projector `0x168cac` | [spec/hud-minimap.md](spec/hud-minimap.md) | `ref_hud_minimap`, `test_ref_hud_minimap`, `difftest_hud_minimap` | 1,200 slices; 200 full draws (185 / 187 drew), 100 with the real blip callback | none (icon scripts stubbed: U) |

## Corrections to earlier contracts

- **Pending rectangles have no `health > 0` gate** (Executed, hud-status.md). They need
  only: a local slot, the object's dead bit 0x8 clear, and their own pending value above 0.
  `play_hud.gd` hides both rectangles at health <= 0, and that is wrong. The arithmetic
  in hud-layout.md and the native `hudPendingRects` is right: all 9 `hud_pending.tsv` rows
  equal the reference. The slot caps never take effect with the shipped origins.
- **`hud_showPlayerNotice` 0x1d9954 does not start a notice line.** It fills the per-player
  text box (hud-quickslots.md).
- **Off-screen byte +0x21 of a gold floater has no reader in the gold code.** This goes
  against the research-combat-ctors-4 note (hud-gold.md).
- **The starting-item code made no shared-seed draw** for the 12 models in the XP run.
  This qualifies docs/startup.md (hud-xp.md).

## Ranked native work

The ranking puts the biggest visible gain per unit of work first. Within a rank, items need
nothing they do not list.

1. **Starting current health and mana = maxima** (hud-xp.md, Executed).
   - `player_initNewCharacter` 0x1b1d70 stores 999999936.0.
   - The recalculation that `Player_ctor` runs at 0x1a2458 clamps current to the maxima.
   - This unblocks the real mana fill and the pending rectangles for a created character.
   - Respawn: health = max x 0.5 offline, full in PvP. Mana unchanged.
2. **Pending rectangle gate fix** (hud-status.md). Gate on the dead bit, not health.
   Pass inverted rectangles through. Regenerate vectors with `ref_hud_status.py --vectors`.
3. **XP bar** (hud-xp.md).
   - Art: `bar_green%02d.tex`, 100x6 used, PSMT4 with an 8x2 PSMCT32 palette. All 11
     disc headers were measured (counts and shapes only).
   - Fill: integer differences, then divide, multiply by 99.0, add, truncate.
   - Gate: acknowledged level > 0.
4. **Gold counter** (hud-gold.md).
   - Floaters: create one on every machine at gold pickup and at chest gold. Each takes one
     cosmetic draw.
   - Credit: `hud_tickGold` pays after 43 ticks, `(p+7)>>3` per tick, capped at 99,999,999.
   - Display: the per-machine hold 60 / alpha +-4 state machine, separators by the language
     byte with both quirks, slots 1 and 3 right-aligned, and the coin.
   - Without the floater the counter never appears; that is the original behaviour, not a bug.
5. **Potion notices** (hud-quickslots.md).
   - Starters in `Player_usePotion`: missing potion 120 frames, used with 1..5 left
     240 frames.
   - Counts from `player_countPotions`: bag-2 sums at 0x41b940 / 0x41b950.
   - Draw-side timers and the 2x2 grid (hud-dynamic.md section 3).
   - Potion A/B are game buttons, not D-pad.
6. **Quick-cast selector input** (hud-quickslots.md).
   - Gates: nine at 0x1dd374–0x1dd404, with `g_localMenuOpen` overriding all of them.
   - The 3-frame button mask.
   - Messages 0 (assign +0x4a84 / +0x4a85) and 13 (queue the cast).
   - Ring icons: record k, 0..7; the background `spellbook.tex`, the blank `icblank.tex`.
7. **Minimap** (hud-minimap.md).
   - In order: the gate and scissor; the cell transform and the rotation by minus the camera
     yaw; blips with `minimap_blipColor` colours; then tiles.
   - The tile arithmetic runs in VU1 microcode, which was read (O) but not executed. Keep
     tiles behind a refusal until a VU1 interpreter or a frame capture confirms them.
   - Do not run icon scripts from draw code online: the original does, on one machine only.
8. **Remaining notice lines and the selector tail.** These are the camera, ammunition and
   thrown lines (not run here, partly modelled in `ref_player`), and the name, AssignCast
   prompt and sheet-mode parts of the selector.

## Still unknown

- The VU1 minimap tile arithmetic, and the tile layout of the world +0x6c texture.
- Cosmetic draws inside the stubbed sound calls (selector, potions) and the minimap icon
  scripts.
- How console displayed frames relate to ticks (gold floater paths, all draw-stepped fades).
- `Player_ctor` 0x1a1d28 as a whole. A static store scan, not a run, says nothing between
  its object store and its recalculation writes current health or mana.
- Raster parity: GS field rows of the rectangles, and inverted rectangles on the GS. This
  needs original frame captures (ui-parity.md).

## Validation

`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'`: 849 tests
OK. The baseline before this work was 765. Each difftest above passed with `--seed 20973`
and `--seed 7`. Logs are kept privately under `local/`. Private inputs were the ELF and
read-only HUD lumps. Only counts and shapes are recorded.
