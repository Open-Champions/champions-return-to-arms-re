# Player model resources — SLUS-20973 v2.00

This is a constructor and disc trace, not a running-game visual check. **Observed** means
read at the given executable address; **Disc observed** means checked in the local US
v2.00 image. `tools/difftest_player_model.py` executes the original constructor with
`tools/ee_emu.py` and compares its resource requests with `tools/ref_player_model.py`.
Its generated, ignored `work/player-model/resource-manifest.json` lists all 111 resource
slots for each model index, including repetitions; it contains identifiers only.

## Selection

The player record is `g_players + slot * 0x4c30` (`g_players` 0x4d8af0). `+0x54` is the
model index; `+0x50` is the derived class; `+0x20..+0x23` are four signed appearance
bytes. **Observed:** `Player_ctor` 0x1a1d28 reads the model at 0x1a1d98, picks the
animation definition through 0x4ef330 at 0x1a1da4–0x1a1db4, and reads the body code
through 0x4ebbb8 at 0x1a2014–0x1a21d4. `player_initNewCharacter` 0x1b1d70 sets the
class mapping (`docs/data-tables.md` 4.1).

| Model index | Class | Body code | Animation lump in `/BG/DATA/` | Definition address | Unique `.anm` names in 111 slots |
|---:|---:|---|---|---|---:|
| 0 | 0 barbarian | `bm` | `RAGNAR2.LMP` | 0x4ecc58 | 69 |
| 1 | 0 barbarian | `bf` | `SONYA2.LMP` | 0x4ec8d0 | 69 |
| 2 | 3 ranger | `wem` | `ELF_MWO2.LMP` | 0x4ee188 | 32 |
| 3 | 3 ranger | `wef` | `ELF_FWO2.LMP` | 0x4ede00 | 32 |
| 4 | 1 cleric | `hem` | `HEM_HIGH.LMP` | 0x4eda78 | 31 |
| 5 | 1 cleric | `hef` | `ELF_FHI2.LMP` | 0x4ed6f0 | 31 |
| 6 | 4 wizard | `em` | `ERU_MALE.LMP` | 0x4ee898 | 30 |
| 7 | 4 wizard | `ef` | `ERU_FEM.LMP` | 0x4ee510 | 30 |
| 8 | 2 shadowknight | `dem` | `ELF_MDK.LMP` | 0x4ecfe0 | 70 |
| 9 | 2 shadowknight | `def` | `ELF_FDK2.LMP` | 0x4ed368 | 70 |
| 10 | 5 berserker | `vm` | `VASHIR.LMP` | 0x4eec20 | 69 |
| 11 | 6 shaman | `im` | `IKSAR.LMP` | 0x4eefa8 | 42 |

**Observed:** each definition is 113 pairs of `{entry-name pointer, loaded-resource
pointer}` at eight-byte spacing. Pair 0 names the `.lmp`; pairs 1–111 name animation
or sound resources; pair 112 has a zero name pointer. The clip set is the `.anm` names
in pairs 1–111, fetched from that model's lump. `silent.vag` also occurs in the table
but is not a clip. Names repeat across slots: the native clip table must preserve slot
order, not just load the distinct files. **Disc observed:** every named `.anm` is in
the selected animation lump. This trace does not establish that all 111 slots are
loaded at spawn; the table holds lazy resource pointers. At spawn
`player_resetIdleAnim` 0x1b2470 reads the definition through object +0x24 and copies
the selected clip pointer into animation state +0x11c (0x1b25b0–0x1b25c0).

The class numbers and body codes above are **Observed**. The English class labels
are **Inferred** from the skill-tree picture names (`docs/data-tables.md` 4.1).

## Body and appearance lookups

**Observed:** `Player_ctor` chooses `select2.lmp` when `g_numPlayers` 0x4d8ae0 is at
least 2, or byte 0x506040 is nonzero; otherwise it chooses `select.lmp`
(0x1a1eac–0x1a1ef0). Both reside in `/BG/DATA/` on the disc. It formats the following
entry names and calls `res_find` 0x17365c, in this order:

| Condition / field | `.vif` lookup and object handle | `.tex` lookup and object handle | Address |
|---|---|---|---|
| Hair style `h = s8(record+0x20)` != −1 | `{code}_hair{h+1}a.vif` → +0x548 | `{code}_hair{h+1}{chr(ord('a')+colour)}.tex` → +0x558, colour = `s8(+0x21)` | 0x1a1ff0–0x1a2094 |
| Beard style `b = s8(record+0x22)` != −1 | `{code}_beard{b+1}a.vif` → +0x54c | `{code}_beard{b+1}{chr(ord('a')+colour)}.tex` → +0x554 | 0x1a20b0–0x1a2154 |
| Always | `{code}_bodyv1.vif` → +0x544 | `{code}_bodyv{skin+1}.tex` → +0x550, skin = `s8(+0x23)` | 0x1a218c–0x1a21e4 |

The body mesh file is always `bodyv1`; the skin byte changes its texture, not its mesh.
The hair and beard mesh use variant `a` while the colour byte changes the texture.
The two optional pairs are zeroed when their style is −1. A name absent from a lump
returns a null handle. **Disc observed:** beard entries exist for `bm`, `em`, `dem`,
and `im`; the other eight codes have none, so an authored beard request for those
codes is unresolved. Each of the twelve codes has a body mesh and first body texture
in both selection lumps.

**Disc observed:** available texture variants in both selection lumps are below.
Hair/beard style numbers are one-based; texture letters are `a`–`c` except `vm`,
which has only `a`. The corresponding style `a.vif` meshes were also present.

| Code | Body texture versions | Hair styles | Beard styles |
|---|---|---|---|
| `bm` | 1–5 | 1–4 | 1–4 |
| `bf` | 1–4 | 1–6 | none |
| `wem` | 1–4 | 1–5 | none |
| `wef` | 1–4 | 1–6 | none |
| `hem` | 1–4 | 1–6 | none |
| `hef` | 1–4 | 1–6 | none |
| `em` | 1–4 | 1–3 | 1–3 |
| `ef` | 1–4 | 1–4 | none |
| `dem` | 1–4 | 1–5 | 1–4 |
| `def` | 1–4 | 1–7 | none |
| `vm` | 1–5 | 1–3 in `SELECT`, 1, 3, 4 in `SELECT2` | none |
| `im` | 1–4 | 1–4 | 1–3 |

**Observed:** `Creature_ctor` 0x109d68 initializes scale `object+0xdc` to 1.0;
`Player_ctor` does not replace it with a class value. It sets collision radius
`object+0x1c` to 12.0 at 0x1a2230–0x1a2244. There is no fixed equipment mesh lookup
in the constructor. The character's starting items are assigned at creation by
`player_giveStartingItems` 0x1acc78, then equipment comes from record +0x43f0 and
the equipped draw path (`Player_drawEquipped` 0x1a3580; `docs/player.md`,
`docs/data-tables.md` 4.7). **Disc observed:** every `bodyv1.vif` here has a model
attach table (header flag 0x04); attach transforms and each part's parent slot live
in the `.vif` records (`docs/formats/model-texture.md`), not a per-class constructor
constant. Hair and beard parts can hide body meshes using their header mask +0x00.

## Native client handoff for blocker 4

1. Read the player record's model index and four appearance bytes. Use the table above
   to choose the exact animation lump, and use the constructor's selection rule for
   `SELECT.LMP` versus `SELECT2.LMP`. Look up the six possible entries by the formats
   above; keep null optional parts. Current `level_flow::LoadServices::player_lumps`
   only reports that player lumps were reloaded; it does not publish these handles.
2. Extend the `real_creature` path to accept a body mesh and its explicit body texture
   entry, plus optional hair/beard mesh-texture pairs. Its current companion-texture
   lookup requires the same base name in one lump; `bodyv1.vif` paired with
   `bodyv2.tex` and hair meshes paired with alternate colour textures violate that
   assumption. Apply the documented part hide masks and attach records.
3. Resolve animation table slots from the model's animation lump, not the selection
   lump. On spawn select the idle track as `player_resetIdleAnim` does, then load and
   bind later clips by the game's slot/name choice. The current preview selects a
   model and clip from one archive by trial, so it cannot establish this pairing.
   The `.anm` supplies the skeleton; the `.vif` supplies weighted joint indices.
4. Use scale 1.0 for the base model. Obtain visible worn equipment from the player's
   equipped item records and their draw/cache path. This research does not map every
   item to its attachment mesh and does not claim a visual or retail runtime pass.
