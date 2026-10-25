# Item -> inventory picture association (SLUS-20973 v2.00)

Research date: 2026-10-17, round 2 on `t3/research-ui`.
Companions: [reference](../../tools/ref_icon_assoc.py),
[synthetic tests](../../tools/test_ref_icon_assoc.py),
[picture payload](inventory-icons.md), [index layout](../startup.md) ("Picture cache"),
[item tables](../data-tables.md) section 1, [item records](../spec/items.md) section 2.

**Status:** the item -> picture-name rule, the name -> index-entry lookup,
the placeholder, the streaming states and the grid placement are documented
from addressed code. The name rule and the index lookup were **Executed**
against the original functions on the real item tables (counts in
"Validation"). No game was run; nothing here proves that a native inventory
shows the same picture on screen.

O = observed in code at the address given; I = inferred; U = unknown.
Names quoted below are format strings and short identifiers the code uses,
not game text. No item names, index contents or pictures are in this
repository.

## 1. There is no picture id

An item record (0x48 bytes) and its definition row (0x40 bytes) hold no
picture index. **O / high**, `item_getPicture` `0x108358`:

1. `item_buildPictureFilename(out, bodyType, item)` `0x107edc` writes a file
   name such as `stem<digits>.tex`.
2. `picCache_getOrRequestPicture(out)` `0x1008bc` returns the cached 64-byte
   picture header when its data is resident, else 0 and queues a read.
3. On 0 the caller gets `res_find("equipmnt.lmp", "pic_dagger1.tex")`
   (`0x10837c–0x108390`): a fixed placeholder from a **lump**, not a
   cache entry. A native must draw that placeholder for any frame in which
   the original has not finished streaming, or accept that difference.

`item_getPictureDimensions` `0x1083a4` builds the same name and returns the
index entry's +6/+8 width/height (`0x10086c`), or 0 x 0 when the name is not
in the index. Dimensions are therefore known before the pixels arrive.

`bodyType` is player record +0x54, the character model 0–11
([player.md](../player.md)); the only callers pass the viewing player's
value (`0x1cc8ec`, `0x1cc904` in `itemList_drawGrid`; `0x1cd4b0` in
`itemList_draw`; `0x1cbd2c` in unnamed `0x1cbbe8`, which computes the same
footprint for up to 75 bag items, I: grid packing). So the **same armour item has a different
picture for different characters**. **O / high.**

## 2. Item -> name, `0x107edc`

Inputs: definition `name` +0, `category` +0x1d (s8), `slot` +0x1c,
`subtype` +0x1e, `dmgMin` +0x0e, `dmgMax` +0x10, `picture` +0x30,
`modelRow` +0x34; item `flags` +0x08 (u64, variant in bits 11–15) and
`prefix` +0x20 (0xff none); prefix row +6/+7/+8 colour bytes (weapon, armour,
alternate weapon, s8); `g_itemModels` row +4 texture name; `g_bodyTypeCodes`
`0x4026d8`. All **O / high** at the addresses in the reference docstrings.

**Base name.** `picture + ".tex"` when the definition has a picture name,
else the model table row's texture name, indexed by `modelRow` **without**
the variant (`0x107f2c–0x107f40`; contrast `item_getResourceIndex`
`0x1083f8`, which adds it for 3D models).

Let `V = ((flags >> 11) + 1) & 31` (`0x108070–0x108090`): the variant plus
one, so variant 31 prints as 0.

| Case | Test | Name |
|---|---|---|
| Weapon | category 0 and item flag bit 34 clear | base with its **last five characters** replaced by `"%d%d.tex" % (V, colour)` |
| Armour, slot 3 | category 1, slot byte 3 | base unchanged |
| Armour | category 1 | `"%s_%s" % (bodyCode[body], base)` with the **last four** replaced by `"%d.tex" % colour` |
| Anything else (and weapons with bit 34) | base contains `1.tex` anywhere | last five replaced by `"%d.tex" % V` |
| | otherwise | base unchanged |

Weapon colour (`0x107f84–0x108024`), applied in this order:
prefix weapon colour (+6), or 1 without prefix; 1 for bows (subtype 4);
the prefix's alternate colour (+8) when item flag bit 23 is set and there is
a prefix; for a preset row (definition name contains `+`) the signed
remainder `(dmgMin + dmgMax) % 18`; finally 0 becomes 1.

Armour body (`0x1080c8–0x108160`): bodies 6 and 7 are the only cloth sheets.
Cloth armour (item flag bit 19) on another body uses 7 if that body number is
odd and below 10, else 6. Non-cloth armour on body 6 or 7 uses 0 or 1. Every
other combination keeps the body. Circlets (definition name contains
`circlet`) skip that mapping; on body 6 or 7 only, the base becomes
`cloth<k>helmet6<n>.tex` where k and n are read from the definition name with
`sscanf("circlet<k>%d")` (`0x108184–0x108234`). If the name does not start
with that text the original uses an uninitialised stack word; the reference
refuses such input.

Armour colour (`0x10825c–0x1082d8`): prefix armour colour (+7); for a preset
row `item_getValue(item) % 4` (signed); then **no prefix forces 1, even for a
preset** (the test at `0x1082c8` comes last). Unlike weapons, a colour of 0
stays 0 and a negative prefix byte prints with its sign.

**I / high:** base picture names end in a placeholder digit before `.tex`
(the five-character cut removes it); the placeholder resource itself is named
that way. A base name shorter than the cut would make the original write
before its buffer; the reference refuses it.

## 3. Name -> index entry, `0x100000`

**O / high**, executed (section 6):

1. Copy the name, cut at the **last** `.`; an empty result finds nothing.
2. The number is the maximal run of trailing decimal digits, never including
   the first character; none means -1. It is parsed with `atoi` and compared
   with the entry's s16, so numbers above 32,767 never match.
3. Scan groups in file order: on a case-sensitive stem match, scan its
   entries for the number; when none matches, continue with later groups.

Consequences a native must keep:

- **Build the string, then split it.** The weapon number is the decimal
  concatenation of V and colour, and the split takes every trailing digit,
  including digits of the base stem (circlet sheets yield three-digit
  numbers such as `6` + n + colour). (V 1, colour 12) and (V 11, colour 2)
  give the same name; the index cannot tell them apart and neither can a
  native that copies the rule. Do not key a native table by (stem, variant,
  colour).
- An item whose name is not in the index keeps the placeholder forever: the
  slot is marked -2 and never read (`0x1006f8`).

`parse_index` / `find_entry` in the reference implement this with bounds
checks (native policy; the original trusts the file).

## 4. Streaming and placeholder frames

**O / high**, `0x1002d4–0x1008bc`; the runtime fields are in
[startup.md](../startup.md):

- 64 named slots. A request for a name with no slot takes a free one; with
  none free it evicts the slot with the **oldest** last use that is strictly
  older than the display frame counter `0x44fdd0` minus 8 and is not being
  read (first such slot on ties). If nothing qualifies the request is
  dropped and simply repeated by the next draw (`0x100790–0x100800`).
- `picCache_serviceRequests` runs once per displayed frame (`0x323378`).
  It finishes the outstanding read (chaining 0x500-byte blocks), then, if the
  file system is idle (`0x172be8`), resolves pending slots in slot order:
  names missing from the index are marked -2 and skipped; the first found
  starts the frame's **only** disc read (`0x1006b0–0x10074c`). So at most one
  new picture becomes resident per displayed frame, plus completion latency.
- When the 256 data blocks are exhausted and nothing can be evicted, the
  partial chain is released, the slot returns to pending and the read is
  retried on a later frame (`0x100550–0x1005d8`; the retry is I / high).
- Last use is refreshed by every successful request (`0x100958`) and for the
  slot being read (`0x10042c`).

`PictureCache` in the reference models these states for comparison captures
(block exhaustion excluded). A native loader that decodes synchronously shows
the real picture on frames where the original shows the placeholder; this is
display-only and per machine (see startup.md hazard 3).

## 5. How the grid draws it

**O / high**, `itemList_drawGrid` `0x1cc7e0`; these are the facts needed to
place a decoded picture, not a full inventory-screen contract:

- Footprint: `cols = width / 32 + 1` (integer division, so a 32-wide picture
  takes **two** columns), `rows = ceil(height * 0.0294117648f)` (the float
  constant `0x3cf0f0f0`, about 1/34; `0x3a51b0` **executed** as ceil on
  1.5, 2.0, 0.2, 2.0001, -1.5). Cell pitch is 32 x 34 (`0x1cc8b4–0x1cc8c8`).
  The multiply of rows by 34 sits in an instruction the disassembler cannot
  print (`0x1cc958`); I / high from the stored default 34 and the use.
- Origin: `x = panelX + 15 + column*32 + footW/2 - width/2`,
  `y = int(rowY - 30) + (footH - height)/2 + 6`, halves truncating toward
  zero (`0x1ccc24–0x1cccc0`, `0x1ccd98–0x1ccdf8`).
- Draw: clipped sprite `0x17fb88`, sort layer 5, clip (0, 102, 640, 600),
  tint `0x80000000 | a*0x010101` with a = 0x80 (0x80808080), or under the cursor
  `a = int(sin16(frame << 10) * 32 + 140)` (`0x1ccd44–0x1ccd8c`). Behind it
  (`ui_drawRect`, submitted first) a cell tint: green `0x20008000` for an
  equipped item, red `0x20000080` when `inventory_checkEquipAllowed` gives a
  reason and item flag bit 41 is clear, else `0x20445558` (`0x1cce14–0x1ccf08`).
- `itemList_draw` `0x1cd4b0–0x1cd524` draws the item held by the cursor with
  plain sprites at layer 7: the picture at (cx+22, cy+22) tint 0x80808080 and
  a black shadow copy at (cx+22, cy+25) tint 0x34000000, submitted after the
  picture (so drawn under it; see [hud-layout.md](../hud-layout.md) on queue
  order). Plain sprites add one to y inside the callee.
- Neither function reads header flag 0x0800.

## 6. Validation

**Executed** (`local/r2-icons/verify_assoc.py`, private; counts only):

- `0x107edc` executed **22,986** times on records built from the real
  definition tables (607 base and 835 preset rows; first/last/one middle
  variant; no prefix and two prefix rows chosen per definition; with and without
  item flag bit 23; all twelve bodies for armour), the reference agreeing in
  **all 22,986** names. A second pass built **7,285** records with the game's own
  `item_parseDescriptor` `0x1069b8` (every row, every variant, every body for
  armour) and again matched in all cases. `sprintf` and `sscanf` were stubbed
  with `%s`/`%d`-only Python versions; `strstr`, `strlen`, `strcpy`,
  `item_getValue` and the function itself ran in `ee_emu`.
- `0x100000` executed **1,652** times with the private `piccache.hdr`
  installed (every seventh indexed name plus malformed probes: no extension,
  empty stem, leading digit, two dots, overflowing number): 0 mismatches.
- Coverage with the reference: all **7,285** parser-built (definition,
  variant, body) names resolve to an index entry, for base and preset rows
  alike. Enumerating every base row with every variant, all 73 prefix rows and
  every body gives 228,664 names, **all** found. Arbitrary prefixes forced onto
  preset armour (which the game never builds, since a preset's prefix comes
  from its descriptor) miss 188,340 of 253,080 names, so a native must not
  invent prefixes for presets. The broad enumeration reaches 9,950 of the
  11,511 index entries; the other 1,561 were not reached by these combinations
  (I: colour/variant combinations needing other prefix and flag mixes, or
  unused art; not settled).
- `0x3a51b0` executed on five values (ceil, section 5).
- `tools/test_ref_icon_assoc.py`: 15 synthetic tests (invented names, tables
  and index), no game input.

**Screens (O / high for direct calls, 2026-10-20).** The two `jal`s to
`item_getPicture` are inside `itemList_drawGrid` and `itemList_draw`.
`itemList_drawGrid` is called only from `itemList_draw` (`0x1cd8f0`,
`0x1cd914`). `itemList_draw`'s only caller is `itemList_update` `0x1d14c8`
at `0x1d1520`. That update is called from `inventory_runPanel` `0x1c00b8`
(itself called by `inventory_runTask` `0x1c56a8`) and from `shop_run`
`0x1c74c0` (called by `shop_task` `0x1c6068`). `0x1c7908` also calls the
update and has no `jal` caller (U whether a task pointer reaches it). The
dimension function is also called from `0x1cbbe8`, which
`inventory_pollResources`, `inventory_refreshPanelModel` and `shop_run` call.
No stats or equipment function calls `item_getPicture`; equipment models go
through the eqcache. Pointer calls were not searched.

**Not done / U:** which `bodyType` a spectator view passes; screenshots of
the original inventory against a native one (the parity method for this
needs a capture of the original grid with a known item list).
