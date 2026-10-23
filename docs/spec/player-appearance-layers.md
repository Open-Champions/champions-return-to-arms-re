# Player appearance layers — SLUS-20973 US v2.00

This is a function-level trace of the original character creation, constructor,
and draw paths. **Observed** means read in the executable at the given address;
**Disc observed** means names or model headers checked in the local v2.00 ISO;
**Executed** means compared with original functions in `tools/ee_emu.py` using
`tools/difftest_player_appearance.py`. None of this is a live visual check.
The body/animation mapping in `t3/research-player-model` commit `7f13899`
is complementary; this document concentrates on the record and worn layers.

## New character record and menu handoff

The player record starts at `g_players` 0x4d8af0 with stride 0x4c30. The
selection screen calls `player_initNewCharacter` 0x1b1d70 at 0x228618. It
passes four signed appearance choices, which init writes at 0x1b23b8 and
0x1b23d4–0x1b23e4. **Observed.**

| Record byte | Meaning | Selection-screen source | Constructor use |
|---|---|---|---|
| +0x20 | hair style, zero based; −1 suppresses the part | menu choice +0x21, sometimes forced to −1 by the comparison at 0x228600–0x228614 | 0x1a1ff0–0x1a2094 |
| +0x21 | hair/beard colour, zero based | menu choice +0x22 | 0x1a2048–0x1a2154 |
| +0x22 | beard style, zero based; −1 suppresses the part | menu choice +0x24 | 0x1a20b0–0x1a2154 |
| +0x23 | body skin variant, zero based | menu choice +0x23 | 0x1a218c–0x1a21e4 |

The menu's choice +0x20 selects the model index passed to init, and +0x25
points at its four ability values (0x2285c0–0x228618). The menu sometimes
forces hair to −1 by comparing two bytes in its selected model row. The exact
meaning of those two row bytes is **Unknown**; retain that conditional rather
than assigning a global no-hair rule. `player_initNewCharacter` stores model
index at record +0x54 and derived class at +0x50. **Observed:** 0x1b1ed0–0x1b1f70.

## Resource selection

`Player_ctor` 0x1a1d28 chooses `SELECT.LMP` for one player and `SELECT2.LMP`
when `g_numPlayers` 0x4d8ae0 is at least two or 0x506040 is set
(0x1a1eac–0x1a1ef0). It reads the body code from 0x4ebbb8 by record +0x54.
The following are **Observed** at 0x1a1ff0–0x1a21e4 and **Executed** in 96
constructor cases across seeds 20973 and 7. A missing entry produces a null
handle, not a substitute part.

| Choice | Mesh entry | Texture entry | Player object handles |
|---|---|---|---|
| hair `h != -1`, colour `c` | `{code}_hair{h+1}a.vif` | `{code}_hair{h+1}{a+c}.tex` | +0x548 / +0x558 |
| beard `b != -1`, colour `c` | `{code}_beard{b+1}a.vif` | `{code}_beard{b+1}{a+c}.tex` | +0x54c / +0x554 |
| body, skin `s` | `{code}_bodyv1.vif` | `{code}_bodyv{s+1}.tex` | +0x544 / +0x550 |

`a+c` denotes the ASCII letter beginning at `a`. The body mesh stays `v1`;
the skin choice changes its texture. Hair/beard meshes stay variant `a`;
colour changes their textures. The 12 body codes, in model-index order, are
`bm`, `bf`, `wem`, `wef`, `hem`, `hef`, `em`, `ef`, `dem`, `def`, `vm`, `im`.
**Observed:** 0x4ebbb8. The constructor's animation-lump mapping is in
`t3/research-player-model` at `7f13899`.

Both selection lumps were enumerated on the local disc. **Disc observed:**

| Code | Body textures | Hair meshes | Beard meshes |
|---|---|---|---|
| bm | 1–5 | 1–4 | 1–4 |
| bf | 1–4 | 1–6 | none |
| wem | 1–4 | 1–5 | none |
| wef | 1–4 | 1–6 | none |
| hem | 1–4 | 1–6 | none |
| hef | 1–4 | 1–6 | none |
| em | 1–4 | 1–3 | 1–3 |
| ef | 1–4 | 1–4 | none |
| dem | 1–4 | 1–5 | 1–4 |
| def | 1–4 | 1–7 | none |
| vm | 1–5 | 1–3 in SELECT; 1, 3, 4 in SELECT2 | none |
| im | 1–4 | 1–4 | 1–3 |

The hair/beard texture letters are `a`–`c`, except `vm` which has `a`
only. This is disc availability, not proof that each option is reachable in
the menu. A requested beard on a code with no beard mesh remains unresolved.

## Equipped item lookup and draw

`Player_drawEquipped` 0x1a3580 iterates the 17 equipped pointers at record
+0x43f0 (0x1a3610–0x1a3e04). Each item points to a definition at item +0x00;
the definition's equipment slot is byte +0x1c, picture base name pointer is
+0x30, and model-table index is signed halfword +0x34 (`docs/data-tables.md`
1.1). **Observed:** 0x1a3658–0x1a36f4, 0x1a3ac0–0x1a3b88.

| Slot route | Lookup | Evidence |
|---|---|---|
| 0, 1, 2, 3, 4, 9, 10, 11, 12, 13 | If definition +0x30 exists, `item_buildPictureFilename` 0x107edc builds the item variant's filename. The draw strips its `.tex` extension and asks `eqcache_lookupModel` 0x1a2d48 for a mesh/texture pair in the selected equipment cache. An asynchronous miss leaves the part absent for that frame. Without +0x30, definition +0x34 selects the pair from `g_itemModels` 0x3e9ce0. | 0x1a36f8–0x1a3b30; cache 0x1a2d48–0x1a2f68 |
| 16 | `item_getResourceIndex` 0x1083f8 indexes `g_itemModels` directly, using definition +0x34 plus item flag bits 11–15 when flag 36 is set. The selected row's +8/+0x0c loaded handles are the mesh/texture. | 0x1a3b38–0x1a3b8c; 0x1083f8–0x108430 |
| 5, 6, 7, 8, 14, 15 | No model part draw from this loop. | 0x1a366c–0x1a3694 |

The row names in the item definition table identify slot 0/1/2 as weapon
positions, 3 as shield, 4 as body armour, 9 as gloves, 10 as boots, 11 as
head gear, and 12 as leg armour; these labels are **Inferred** from the rows
(`docs/startup.md`). The route for slot 13 is **Observed**, but a retail item
category for it is **Unknown** here. A slot route is a candidate for a part:
the draw still applies its state and resource gates.

The jump table for slots 0–13 is at 0x535dc0. The per-player equipment
cache entries at 0x8659e8 are 0x58 bytes each, with a 0x160-byte block for
each routed slot (four players × 0x58). **Observed:** repeated address
construction at 0x1a36f8–0x1a3aa4. `eqcache_lookupModel` reads the header
from `EQCACHE.HDR` or `EQCACHE2.HDR`, and the model/texture payload from
`EQCACHE.DAT` or `EQCACHE2.DAT` (0x1a2680–0x1a2810,
0x1a2d48–0x1a2f68). Its header groups names and variant numbers; a
name/variant absent from that header has no cached mesh. The complete
name/variant directory is enumerated in the generated, ignored
`local/appearance/item-models.json`: 243 groups in `EQCACHE.HDR`, 245 in
`EQCACHE2.HDR`, and 155 in the separately loaded `WCACHE.HDR`. It also gives
all 134 static `g_itemModels` filename pairs by row. The exact packed
mesh/texture payload format and live load timing are **Unknown** in this
trace. **Disc observed:** the three headers, their paired data files, and
134 static model/texture names are present.

`Player_drawEquipped` draws a part only when both handles exist
(0x1a3b90–0x1a3b9c). It applies equipment-specific tests and effects before
`model_drawPart` 0x178c28 (0x1a3ba0–0x1a3dc8). The part normally uses the
attach slot in its `.vif` header +0x13 and the parent's attach table. The
second weapon loop slot explicitly overrides attach slot 1
(0x1a3cdc–0x1a3dc8). A shield in equipment slot 3 gets a variant show mask
selected by model index through 0x535e00 (0x1a3cfc–0x1a3d84); this selects
the appropriate geometry in the shield model. **Observed.** The exact
transforms are data, not class constants: parent `.vif` flag 0x04 and +0x22
locate 16 attach records of 0x34 bytes (joint, rotation, origin); the part's
+0x13 chooses one (`docs/formats/model-texture.md`, 0x1754a0,
0x175fb8). **Observed** there; disc models have the table.

The body show mask starts with `model_buildHideMask` 0x179550. After each
equipped part draw, its `.vif` header +0x00 hide bits are cleared from the
body mask (0x1a3de4–0x1a3df4). Hair +0x548 then beard +0x54c draw after
equipment, when their mesh and texture handles exist; their hide bits are
cleared likewise (0x1a3e34–0x1a3f30). Thus the native path must preserve
the mask effects of parts actually drawn. **Observed.** `Player_draw`
0x1a46c0 calls `Creature_draw` 0x10b048 before `Player_drawEquipped`
(0x1a4c28, 0x1a4d08); the exact timing of body-mask consumption inside
that broader draw path is **Unknown** here and needs a native frame trace.

## Ordered native port

1. Read record +0x54 and +0x20..+0x23. Resolve the exact selection lump,
   body pair, and optional hair/beard pairs above. Preserve null lookups.
2. Decode each loaded `.vif` hide/default/variant mask and its attach table;
   pair every mesh with the explicitly selected texture, rather than a
   same-basename guess. Keep animation poses from the player-model mapping.
3. Read all 17 equipped pointers and the underlying item definitions.
   Resolve item variants through `item_buildPictureFilename` and the equipment
   cache, or `g_itemModels` where the code takes that route. Treat an
   unresolved asynchronous cache entry as absent for that frame.
4. Reproduce the `Player_draw`/`Creature_draw` call order. Draw routed
   equipment on the body's current pose, including the second-weapon attach
   override and shield variant mask; clear each drawn part's body hide bits.
   Then draw hair and beard and clear their hide bits.
5. Use the selected body texture and resolve when its show mask is consumed
   by tracing one native frame. Check first-person/third-person and inventory
   views on the intended native client; these tests alone establish no
   visual parity.

## Verification and boundary

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_player_appearance.py
/Users/syndicatemike/champions-re/SLUS_209.73
"$HOME/Library/Application Support/Play-RTA/Champions - Return to Arms (v2.00).iso"
--manifest local/appearance/item-models.json` compares 96 constructor
requests/handles and 1,072 item-index calls with original functions, across
seeds 20973 and 7. It also enumerates 643 disc cache-header name groups.
The record is authored in test memory; world setup and
resource lookup are isolated, and equipment drawing itself was read rather
than executed. Original disc bytes, disassembly, and the generated filename
manifest stay ignored under `local/`.
