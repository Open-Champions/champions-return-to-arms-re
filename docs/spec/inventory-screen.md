# In-game inventory and equipment screen — SLUS_209.73 v2.00

Research date: 2026-10-23. The executable pin is SHA-256
`292f6f48e3609c0026def2307d76c222cd5b389303d53b89b0e107d7b1dcd675`.
The bounded reference is `tools/ref_inventory_screen.py`; the differential
probe is `tools/difftest_inventory_screen.py`. Both seeds 20973 and 7 run the
original functions in `tools/ee_emu.py` on constructed state. This is not a
running-game capture or pixel comparison.

**Evidence labels:** **Observed** means code or an executable resource name
at the stated address; **Executed** means the stated `ee_emu` fixture reached
the call or write; **Inferred** connects these observations; **Unknown** is a
refusal for a native port. The source branches read first were
`t3/research-menus` `099900e`, `t3/research-menus-layout` `29c90a5`,
`t3/research-items` `49bc578`, `t3/research-items-gaps` `ecf9742`, and
`t3/research-ui-text-gaps` `523b3db`. The `research-menus-art` name in the
brief is the native menu report at
`~/Projects/open-champions/worktrees/menus/work/loop-menus-art-r1-report.md`,
not a branch in this research repository. The icon placement and item-picture
chain are in `t3/research-ui`'s `docs/formats/icon-association.md`.

## Screen and data path

| Evidence | Contract |
|---|---|
| **Observed** `menu_openInventory` 0x1c15c8, `inventory_runTask` 0x1c56a8, `inventory_runPanel` 0x1c00b8 | Opening registers the run/draw tasks. The run path calls `itemList_update` 0x1d14c8, which calls `itemList_input` 0x1cd988 and `itemList_draw` 0x1cd208. This is the screen that sends actions; the message handlers change inventory and equipment. |
| **Observed** `g_itemPanels` 0x4f4040, four records of 0x74; **Executed** draw/input | +0x00 is panel x; +0x28 participates in row scroll; +0x44/+0x48 are free cursor floats; +0x50 is page; +0x58 drag state; +0x60 hovered cell; +0x64/+0x68/+0x6c dragged item/column/row. Prior menu research established these fields; the new probe checks the hover and page dispatch. |
| **Observed** player record 0x4d8af0 + slot × 0x4c30 | Three bags start at +0x130, each holding up to 64 item records of 0x48 bytes (bag stride 0x1208). The separate on-screen grid uses 9 columns, 75 possible rows and a column stride of 0x1518. Equipped pointers are at +0x43f0; `inventory_isEquipped` 0x1c41d8 tests them. `docs/spec/items.md` defines the record and requirement logic. |
| **Executed** `itemList_draw` 0x1cd8f0/0x1cd914 | Pages 0–2 each submit 90 grid calls (9 columns × 10 visible rows). Pages 3–5 call `stats_screen` 0x1d1db8 once and submit no grid calls in the constructed fixture. The probe stubs `stats_screen`, so its interior behavior here comes from the earlier menu research. |

## Panel geometry and resources

All coordinates below are screen pixels in the game's 640 × 448 UI space.
They are function submissions; the renderer's clipped/field-dependent final
pixels have not been compared. The fixture uses panel x = 80.

| Evidence | Submission |
|---|---|
| **Observed** `itemList_draw` 0x1cd3a0/0x1cd3d0 | Looks up `inventry.lmp` / `mousecursor.tex` twice. `ui_drawSprite` 0x17fb18 submits layer-7 copies tinted `0x80808080` and `0x34000000`. In drag state, `itemList_draw` 0x1cd4b0–0x1cd524 also draws the held item's picture at the free cursor, as the icon research established. |
| **Executed** `itemList_draw` 0x1cd728 | 65 layer-4 one-pixel strips: x = panel x + 15 through panel x + 305; y = 413 through 477. Alpha rises from 1 to 127; `strip_rects` models the exact integer sequence. `check_draw` asserts the `inventoryunderbar.tex` lookup at 0x1cd754 and its layer-5 submission at 0x1cd774. |
| **Observed** format at 0x5394a8 and calls 0x1ccb04/0x1ccb18; **Executed** with `sprintf` replaced only for this format | `inventry.lmp` / `inventrybox%d.tex`, with the suffix from 1–3. Five rows at y = 116, 184, 252, 320, 388; each row has numbered pieces at x = panel x + 15, +111, +207, then `inventryboxend.tex` (lookup 0x1ccb68) at x = panel x + 303. `check_draw` asserts all 20 clipped sprite submissions at layer 0 with tint `0x80808080`. The bounded zero-state sequence is in the reference; it is an executed list, not a guessed general random algorithm. |
| **Observed** 0x1cd79c and 0x1ccaf8; **Executed** both seeds | The draw resets cosmetic state 0x86a6a4 to zero and writes it 15 times while choosing numbered box pieces, ending at `0xeef6843f` in this fixture. Shared `g_randSeed` 0x404464 remains at the input seed. The update includes arithmetic beyond a plain LCG, so the reference does not claim a general recurrence. |

The item icons are separate from the box art. **Observed** `itemList_drawGrid`
0x1cc7e0 calls `item_getPicture` 0x108358 through the picture cache, using the
viewing player's body type +0x54 to form equipment art. A cache miss uses the
`pic_dagger1.tex` placeholder (`t3/research-ui` icon association §1).
**Observed** at 0x1cc8b4–0x1ccf08: the grid has 32 × 34 pitch, a clipped
layer-5 icon within (0,102,640,600), and an underlay rectangle. The tint is
`0x20008000` when equipped, `0x20000080` when the equip check returns a reason
and item flag 41 is clear, otherwise `0x20445558`. The original code takes the
equipped branch first. **Executed** five constructed states, two populated
cells each; `check_highlight` also covers equipped plus blocked and compares
both fills, including the flag-41 split between the first and second cell.
The two baseline icons' layer and all five states' colours and equipped-branch
precedence matched the reference.
The icon research also records its width/height footprint, pulse, placeholder
and picture-name rules; this screen probe does not rerun the private picture
cache or decode icon pixels.

## Hover, item text and detail frame

**Observed** at `itemList_input` 0x1cdd40–0x1cdf70 and **Executed** for one
cell: `column = trunc((cursorX - panelX - 17)/32)` and
`row = trunc((cursorY - textureHeight/2 + 140 + panelScroll - 229)/34)`.
The mode-2 hover cell pointer is `base + page*0xbdd8 + column*0x1518 +
row*0x48`, bounded to pages 0–2, 9 columns and 75 rows; pages 3–5 skip it.
The base comes from the pointer word at 0x4ebbb0. The page stride is nine
column strides. **Executed** `check_cursor` uses distinct sentinels on all
three pages on each seed; x 97, y 100, panel x 80 selects the first cell,
record +0x130 on page 0. For this first-cell equip fixture, the sender's
item argument instead uses bag base `record + 0x130 + page*0x1208`. The probe
checks that argument against separate bag sentinels on pages 1 and 2; do not
substitute the display-grid stride for the action's bag stride.

| Evidence | Text and item field |
|---|---|
| **Observed** `itemList_drawRows` 0x1cc250/0x1cc2e8, 0x1cc310–0x1cc3cc; **Executed** one selected item | Calls `itemName_buildLocalizedName` 0x101e48. `text_widthWide` 0x181bf8 measures it. `check_draw` asserts `text_begin` with the small-font pointer word 0x4f7104, layer 6, base colour `0x80464646`, icon alpha -1; the selected colour at 0x1cc330 is `0x805c2913`. It also asserts the `text_drawWrappedCentered` 0x181530 call and its fixture geometry. The text pointer is zero in this stubbed fixture, so the actual name/description content and glyphs are **Unknown** here. |
| **Observed** 0x1cc3f8–0x1cc6c0 | `item_getValue` 0x1024a8 supplies the monetary field; `ui_insertThousandsSeparators` 0x1c7128 formats its integer. The row calls `text_drawAscii` 0x181aa0 twice and `text_widthAscii` 0x181af8 before closing its second small-font batch. Which localized label accompanies every numeric field is **Unknown** without the real language/text state. |
| **Observed** `itemList_drawRows` 0x1cc7a0 calls `itemList_drawItemInfo` 0x1c8d38; **Executed** category probes | The detail pane calls `player_itemWeight` 0x1b6338. Weapon category 0 calls `item_getDamageRange` 0x104100; armour category 1 calls `item_getArmorValue` 0x103ec8; other category 2 calls neither. There are branches for modifier/stat lines, requirements and gem slots from 0x1c96e8–0x1caef0 that the zero-modifier fixture does not settle. Do not fabricate absent labels or values. |
| **Executed** `itemList_drawItemInfo` 0x1cb05c | For the selected item, `ui_drawFrameImpl` 0x17c118 gets `(infoX - 109, infoY, 223, 77, 6, 0x80000000)` for category 0 and height 57 for categories 1–2. `itemList_drawRows` passes infoX = 244 and infoY = 230 with panel x 80, yielding `(135,230,223,77)` for the weapon fixture. All reached detail text batches use the small-font word 0x4f7104 on layer 6. A second frame call site 0x1cb008 was not reached. |

**Observed** `stats_screen` 0x1d1db8 is the character-stat page for pages
3–5. Earlier executed menu research found a small-font layer-5 batch, first
header at (160,107), stat lines at y 208 and 229, and a later line at y 306.
The current differential probe checks only that page dispatch reaches it and
skips the item grid. Stat-point selection remains **Unknown**: four sends
exist at 0x1d24d4/0x1d24f4/0x1d2510/0x1d252c, but their exact edge/cursor
precondition has not been executed.

## Equip, unequip and drop

**Observed** `itemList_input` mode 2 uses the pad mask words installed by
`game_initCamera` 0x1e6b68. In the cross-confirm set, equip is `0x40`, drop
is `0x10`; the alternative set uses `0x20` and `0x80`. The US build's active
set is still **Inferred** from prior menu research. On a matched ordinary
cell, equip sends inventory message 1 at 0x1ce87c through `invmsg_sendEquip`
0x1c5800; an equipped cell sends message 2 at 0x1ce868 through
`invmsg_sendUnequip` 0x1c5840. A drop sends message 0 at 0x1ceb1c through
`invmsg_sendDrop` 0x1c59d0. The equip branch wins if both bits are set.
For item flag bit 35, equip starts a drag by setting panel +0x58/+0x64/+0x68/
+0x6c instead of sending equip. **Executed** six mode-2 cases on each seed;
the receiver-side changes are in `docs/spec/game-messages.md` and the prior
item research, not rerun here. The path before a drop calls 0x14a928 and a
grid-object filter; its possible shared-seed use remains **Unknown**.

## Ordered native port

1. Load the selected disc's `inventry.lmp` and both font resources at runtime;
   use the original small-font page and glyph layout from `ui-fonts.md`. Keep
   absent assets as an explicit refusal.
2. Implement the panel/page state and input cursor mapping with the mode-2
   `page*0xbdd8` display-grid offset and the separate `page*0x1208` bag
   offset for the tested first-cell action. Retain exact item/equipment
   pointers; pages 3–5 dispatch the stat/skill sheet.
3. Draw the panel's cursor, scrollbar gradient, underbar, numbered box strips
   and end pieces at the submitted layers and coordinates. Use the observed
   zero-state box sequence for this bounded path; trace the general cosmetic
   update before claiming every state.
4. Draw clipped item pictures via the body-dependent picture-name/cache rule,
   including the placeholder, grid footprint, pulse and green/red/default
   underlays. Preserve layer order from the UI queue contract.
5. Render selected name, value/weight and item detail fields with the small
   font, documented colours, wrapping and category-dependent detail frame.
   Extend emulation to modifier, gem, requirement and language branches before
   exposing those as exact.
6. Wire equip, unequip, drag and drop sender conditions to the already
   specified message handlers; keep the drop-space and stat-point gates
   refused until their remaining paths are traced.
7. Compare actual original and native screen captures with a known item list,
   selected language, body type and frame field. The current function-level
   tests establish submissions, not final raster parity.

## Validation and open bounds

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_inventory_screen.py`
compared **32 properties, 0 failures** across seeds 20973 and 7: draw
submissions including underbar, box layer/tint and text batch, cosmetic/shared
seed writes, font/selection, five highlight states with both cells, three item
categories/detail frames, six mode-2 actions, pages 0–5 and three page-specific
hover/action targets. The test stubs resource lookup, the one box-name
`sprintf` format, original text drawing and gameplay/world callees; it does
not load the disc, execute the complete render packet or run a game. No
disassembly, executable data, text payload, font page or image is tracked.

Related reruns with `PYTHONDONTWRITEBYTECODE=1`: prior
`tools/difftest_menus.py` passed 6/6 properties; the item requirement check
(`tools/difftest_items.py --quick --jobs 2 -k equip`) compared 4,000 cases with
zero mismatches on each seed; `tools/difftest_ui_text_gaps.py --quick` passed
8/8 properties on each seed. The full unit suite on this worktree passed
652/652 with `python3 -m unittest discover -s tools -p 'test_*.py'`.

Still **Unknown**: second detail-frame branch at 0x1cb008; full modifier/gem
and localized field content; exact stat-point edge/cursor gate; the general
box variant arithmetic outside the reset zero-state draw; final interlaced
pixel geometry and live screen parity; drop preflight seed effect. These need
targeted fixtures or original-game captures before exact native claims.
