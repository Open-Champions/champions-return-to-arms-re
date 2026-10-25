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
`tools/difftest_player_appearance.py` now asserts every row below in both
lumps: the complete body texture/mesh and hair/beard mesh style sets, each
style's texture letters, and the `vm` SELECT2 exception. The disc also has
body meshes `v2`–`v4` (and `v5` for `bm`/`vm`); the observed constructor
always requests `bodyv1.vif`. Likewise, the disc has `b`/`c` hair and beard
meshes for non-`vm` styles, while this constructor requests only `a` meshes.

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
0x1a2d48–0x1a2f68). Its header has a group count at +0, then 12-byte
groups `{entryOffset, nameOffset, entryCount}`. Each group points to an
ASCII stem and an even count of 8-byte entries. A pair shares one signed
variant id: `{id, textureSectorCount, textureStartSector}`, then
`{id, modelSectorCount, modelStartSector}`. Sectors are 2,048 bytes and
the model begins immediately after the texture. **Observed:** pointer
relocation 0x1a2748–0x1a2810; `eqcache_findEntry` 0x1a2600–0x1a2648;
sector arithmetic 0x1a2ea8–0x1a2eec; `tex_relocate` at 0x1a2f34 and
`model_relocate` at 0x1a2f44. **Disc observed:** all 16,945 texture/model
pairs in the three headers satisfy the shared id, adjacency, and DAT bounds.

A name/variant absent from the selected header has no cached part. The
generated, ignored `local/appearance/item-models.json` enumerates the
stem, variant id, texture/model sector offsets and lengths for each pair:
243 groups in `EQCACHE.HDR`, 245 in `EQCACHE2.HDR`, and 155 in the
separately loaded `WCACHE.HDR`. It also gives all 134 static
`g_itemModels` filename pairs by row. The cache API returns the model
handle and texture handle to the draw loop in that order
(0x1a2d88–0x1a2da0). **Unknown:** the live frame on which an asynchronous
cache miss resolves. The `.vif` and `.tex` payload formats are already
documented in `docs/formats/model-texture.md`; no payload bytes are tracked.

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

At entry, the body show mask at player object +0x220 is set to all ones
(0x1a3584–0x1a35c8). The signed global counter at 0x41b514 gates its
replacement: below `0x111` it remains all ones; at `0x111` or above,
`model_buildHideMask` 0x179550 receives body model handle +0x544 and variant
bit `1`, and its result replaces +0x220 (0x1a35cc–0x1a3600). **Observed;
Executed** by the mask cases at both threshold edges. After each equipped
part actually draws, its `.vif` header +0x00 hide bits are cleared from that
mask (0x1a3de4–0x1a3df4).

The draw-local cover flag starts at zero at 0x1a3604. Only equipped parts
that pass both handle checks at 0x1a3b90–0x1a3b9c reach its producer. These
tests call `libc_strstr` 0x3b96a8, so “contains” below means a non-zero
substring result; the strings are the item definition's name pointer +0x00
and picture base pointer +0x30. The flag is sticky for the rest of this
17-slot draw (0x1a3ba0–0x1a3ccc). **Observed; Executed** with the original
substring function for seeds 20973 and 7.

| Model index and definition slot | Condition that sets cover flag | Addresses |
|---|---|---|
| any except 7; slot 11 | name does **not** contain `circlet` | 0x1a3ba4–0x1a3bd8 |
| 7; slot 11 | picture base does **not** contain `cloth1`, then name does **not** contain `circlet` | 0x1a3be4–0x1a3c28 |
| 7; slot 4 | picture base contains `cloth3body` | 0x1a3c30–0x1a3c58 |
| 9; slot 4 | name contains `chain`, or a present picture base contains `chainbody` | 0x1a3c60–0x1a3cc8 |

After the equipment loop, hair reaches its handle checks at
0x1a3e40–0x1a3e50 when the flag is clear, or when it is set and model index
is 11, or when it is set and model index is 10 with skin byte +0x23 equal to
4 (0x1a3e08–0x1a3e30). Beard reaches its handle checks at
0x1a3eec–0x1a3efc when the flag is clear, or when it is set and model index
is 11, or when it is set and the head-item pointer at record +0x441c exists
and either its definition name contains `leatherhelmet` or model index is 6
(0x1a3e88–0x1a3ee8). Each part still requires both mesh and texture handles;
only a drawn part clears its hide bits from +0x220 (hair 0x1a3e70–0x1a3e84;
beard 0x1a3f1c–0x1a3f30). **Observed; Executed** in isolated draw branches
for both seeds. Null name pointers in a malformed equipped definition are
**Unknown** beyond this authored-state test boundary.

`Player_draw` 0x1a46c0 calls `Creature_draw` 0x10b048 before
`Player_drawEquipped` (0x1a4c28, 0x1a4d08). **Unknown:** the exact native
frame on which `Creature_draw` consumes the body show mask, and when an
asynchronous item-cache miss resolves. A native frame trace is needed to
settle those timing questions; the isolated gate tests are not visual proof.

## Ordered native port

1. Read record +0x54 and +0x20..+0x23. Resolve the exact selection lump,
   body pair, and optional hair/beard pairs above. Preserve null lookups.
2. Decode each loaded `.vif` hide/default/variant mask and its attach table;
   pair every mesh with the explicitly selected texture, rather than a
   same-basename guess. Keep animation poses from the player-model mapping.
3. Read all 17 equipped pointers and the underlying item definitions.
   Resolve item variants through `item_buildPictureFilename` and the equipment
   cache directory/sector pair, or `g_itemModels` where the code takes that route. Treat an
   unresolved asynchronous cache entry as absent for that frame.
4. Reproduce the `Player_draw`/`Creature_draw` call order. Draw routed
   equipment on the body's current pose, including the second-weapon attach
   override and shield variant mask. Initialize body show mask +0x220 to all
   ones; replace it with `model_buildHideMask(body, 1)` only when signed
   0x41b514 is at least `0x111`. Clear hide bits only for parts actually drawn.
5. Accumulate the cover flag from the four equipped-item substring conditions
   above, only after both equipment handles pass. Draw hair and beard only
   when their respective cover/model/skin/head-item gates and both part
   handles pass; clear their hide bits only after a draw.
6. Use the selected body texture with the gated show mask and resolve its
   consumption timing by tracing one native frame. Check first-person/third-person and inventory
   views on the intended native client; these tests alone establish no
   visual parity.

## Verification and boundary

`PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_player_appearance.py
SLUS_209.73
"$HOME/Library/Application Support/Play-RTA/Champions - Return to Arms (v2.00).iso"
--manifest local/appearance/item-models.json` compares 96 constructor
requests/handles and 1,072 item-index calls with original functions, across
seeds 20973 and 7. It asserts 24 complete disc variant rows, executes 8
body-mask threshold cases and 504 equipped-state/hair/beard gate cases,
and validates 643 disc cache-header name groups and 16,945 texture/model
sector pairs.
The record is authored in test memory; world setup and
resource lookup are isolated. The gate runs execute original branch code and
the original substring routine, while `model_drawPart` and mask-building
callees are stubbed; they do not prove a full equipment render. Original disc
bytes, disassembly, and the generated filename manifest stay ignored under
`local/`.
