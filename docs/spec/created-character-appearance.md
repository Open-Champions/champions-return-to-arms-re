# Created-character appearance: menu values to resource handles

Research date: 2026-10-27. Executable revision: the US v2.00 SHA-256 pin in
`tools/difftest_char_appearance.py`. **Observed** means addressed executable
inspection; **Executed** means original instructions in `tools/ee_emu.py` on
constructed state. **Inferred** and **Unknown** are stated separately. Nothing
here claims a running game, rendered frame, or modified playable client.

This adds to the audited appearance research at `e088796`, model research at
`7f13899`, and creation research at `b6dda4e`. Their reference APIs and vectors
are unchanged. Resource strings, archive contents and disassembly remain private;
the new tests resolve identifiers from the pinned executable in memory and emit
counts only.

## Selection state and the critical index distinction

**Observed; Executed:** the menu row at `0x4fdb80 + playerSlot*0x2c` contains
a **carousel row index**, not the final model index, at byte `+0x20`.
`0x22483c–0x22489c` and `0x2285c0–0x228608` use it to select a descriptor
at `D = 0x4fbbf8 + carouselRow*0x26c`, then read the final model from
`D+0x10`. For example, row 1 selects model 11 and row 2 selects model 10.
The deferred handoff skips row index zero; treating zero as a newly selected
model would create a character the original path skips.

The four per-carousel arrays are signed bytes:

| Meaning | Array base | Menu byte | Player-record byte |
|---|---:|---:|---:|
| Hair style | `0x8e2bc0` | `+0x21` | `+0x20` |
| Shared hair/beard colour | `0x8e2bd0` | `+0x22` | `+0x21` |
| Beard style | `0x8e2be0` | `+0x24` | `+0x22` |
| Body skin variant | `0x8e2bf0` | `+0x23` | `+0x23` |

**Observed; Executed:** the acceptance slice `0x226c68–0x226ce8` copies
the active carousel's four array values into the selected player's menu row.
The test supplies the caller's slot offset and stops before starting-stat
allocation. It does not execute the input predicate that admits this slice.

**Observed correction:** `0x22d7c8–0x22d804` copies four existing-record
appearance **values** into active array index zero. It is not an option-count
initializer. This older investigation lead must not be used as count evidence.
That existing-record restoration path is not executed by this new harness.

## Resource-driven counts and control semantics

**Observed; Executed:** `0x22b978` probes the chosen archive through resource
lookup `0x17365c`. It counts consecutive body textures starting at variant one.
It then probes consecutive hair meshes; for each successful mesh it probes
consecutive texture letters starting at character value 97. A missing mesh or
zero textures stops the style scan, even if later entries exist. The last
successful hair style overwrites the colour count. With no successful hair
style, the prior colour count is retained. Beard scanning follows the same
mesh/texture stopping rules but does not replace the shared colour count.

Counts live at descriptor `D+0x18` (body), `+0x19` (hair including any absent
option), `+0x1a` (colour), and `+0x1b` (beard including absent). Hair adds an
absent option when `D+0x12` is nonzero; beard always adds one. Independent
Python membership scans match every ordered original lookup, including the
terminating misses, for all twelve nonzero carousel rows in both archives.
Synthetic empty/first-style/second-style omissions and first/middle/last-style
colour gaps additionally verify early stops, retained colour, and replacement
of the shared colour count by later successful styles.

**Executed count results**, using the archive pointers at `0x5353e0` (first)
and `0x535b68` (second). These are helper limits, not a claim of controller
reachability for every Cartesian product of options.

| Carousel row | Model | Optional hair | Body count | Hair count first / second | Colour count | Beard count |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 11 | 0 | 4 | 4 / 4 | 3 | 4 |
| 2 | 10 | 1 | 5 | 4 / 2 | 1 | 1 |
| 3 | 0 | 1 | 5 | 5 / 5 | 3 | 5 |
| 4 | 1 | 0 | 4 | 6 / 6 | 3 | 1 |
| 5 | 2 | 0 | 4 | 5 / 5 | 3 | 1 |
| 6 | 3 | 0 | 4 | 6 / 6 | 3 | 1 |
| 7 | 4 | 0 | 4 | 6 / 6 | 3 | 1 |
| 8 | 5 | 0 | 4 | 6 / 6 | 3 | 1 |
| 9 | 6 | 1 | 4 | 4 / 4 | 3 | 4 |
| 10 | 7 | 1 | 4 | 5 / 5 | 3 | 1 |
| 11 | 8 | 0 | 4 | 5 / 5 | 3 | 5 |
| 12 | 9 | 0 | 4 | 7 / 7 | 3 | 1 |

**Observed; Executed:** four helper bounds use those counts:

| Helper | Value | Lower bound | Upper bound | Delta-zero reset |
|---|---|---:|---:|---:|
| `0x22b580` | skin | 0 | body count − 1 | 0 |
| `0x22b720` | hair | −1 if optional, otherwise 0 | hair count − 2 if optional, otherwise count − 1 | 0 |
| `0x22b7e8` | colour | 0 | colour count − 1 | 0 |
| `0x22b890` | beard | −1 | beard count − 2 | −1 |

For nonzero delta, the old value is compared with the appropriate bound;
accepted changes add delta and store a byte, returning one. Rejected changes
return zero. Delta-zero resets return zero. There is no post-add clamp:
synthetic deltas ±2 can cross a bound. A host picker should supply unit steps
when applying these helper contracts, not assume arbitrary-delta validation.
Boundary probes include out-of-range initial values; those are robustness
observations, not valid character presets.

The skin helper always refreshes preview mesh/texture handles at preview object
`+0x428/+0x42c`, even when no change is accepted. Its object comes from
`*(scratch + 0x1558 + 4*carouselRow)`, with scratch at `0x4fdb7c`.
Both ordered requests and stored handles are compared; the preview renderer
and its camera are **Unknown** here.

**Observed; Executed:** `0x2275dc–0x2275f0` calls normalizer `0x22e6a4`
only for carousel row 2 (model 10). Skin 0 gives hair 0, skin 3 gives hair 1,
skin 4 gives hair 2, and other skin values give hair −1. The following UI
branch at `0x227620` skips that row's ordinary hair/colour controls;
that UI branch is **Observed**, not a tested full screen. The normalizer
does not remap to whichever meshes happen to exist in an archive.

## Two handoff routes and the actual player record

**Observed; Executed:** deferred `0x2247ec` checks pending word `0x4fbbd8`,
visits player slots below `0x4d8ae0`, skips menu row-index zero, and clears
pending after processing. Disabled pending, zero players, and four empty
selection rows produce no initializer calls. Each nonzero row calls
`0x1b1d70` with the translated model, menu name, four signed choices, and
four stats at menu `+0x25`. The direct confirmation slice
`0x2285bc–0x22861c` uses the same appearance mapping for slot zero.

Both routes replace hair with −1 exactly when descriptor `D+0x19` equals
`D+0x12`. The scanner now explains this comparison: there are no discovered
hair styles beyond the optional absent choice. Equal and unequal cases are
executed explicitly, including optional flag zero and one.

The initializer executes from `0x1b1d70` through return, including its actual
memory clear, string copy, model/class writes, and signed-byte appearance stores
at `0x1b23b8/0x1b23d4/0x1b23dc/0x1b23e4`. The result is checked at
`0x4d8af0 + slot*0x4c30`: model `+0x54`, appearance `+0x20..+0x23`, name,
and kind bits 32–36 at `+0x4c18` (deferred default one; direct confirmation
two). Five unrelated initializer services are explicit zero-return stubs:
`0x1bec10`, `0x1b6458`, `0x1acc78`, `0x1bf770`, `0x1bf6d0`. Their load/stat,
inventory/equipment and mission-bit effects are **Unknown** in this new test; initialization
of a complete playable character is not established by these field checks.

## Record to mesh/texture handles

**Observed; Executed:** original constructor slice `0x1a1ea0–0x1a21f4`
consumes the actual initialized record. A test supplies object/slot/caller
registers, reserves a stack frame, and stubs only light registration
`0x14a4f0` and the resource lookup. All formatting and library calls execute.
No unmapped-memory fallback or default unknown-callee stub is enabled.

The archive selection is tested for one player, two players, and one player
with override byte `0x506040` set. The latter two select pointer `0x535b68`;
ordinary single-player selects `0x5353e0` (`0x1a1eac–0x1a1ef0`). Model
index `+0x54` indexes prefix pointers at `0x4ebbb8`. Runtime formatting
templates are resolved at the addresses below; no filename table is embedded.

| Layer | Mesh format | Texture format | Mesh / texture object offsets |
|---|---:|---:|---|
| Hair | `0x535b78` | `0x535b88` | `+0x548 / +0x558` |
| Beard | `0x535b98` | `0x535ba8` | `+0x54c / +0x554` |
| Body | `0x535bc0` | `0x535bd0` | `+0x544 / +0x550` |

Hair and beard each use zero-based style plus one and shared colour plus 97
for the texture selector; style −1 skips both requests and clears both handles.
The body mesh remains fixed while skin plus one selects its texture. Requests
occur hair pair, beard pair, then body pair. Every name, order and destination
handle is compared with an independently authored reference using private
formats as input data. Null lookup results stay null, including controls that
start with poisoned nonzero handles.

**Observed; Executed missing resource:** model 10, skin 3 normalizes hair to
index 1, whose requested mesh/texture pair is absent from the second archive.
The first archive contains the pair. This is not permission to substitute
another style or infer that menu scanning skips gaps. All five skin values for
this model are exercised independently of the random cases.

## Handle gates, hide masks, and attachment packets

**Observed; Executed:** `tools/difftest_char_attachment.py` complements the
constructor probe with original final appearance branches
`0x1a3e08–0x1a3f30`, complete part draw `0x178c28`, and complete packet setup
`0x175fb8`. Only renderer-queue submission `0x16b7f0` is stubbed in this
harness. Parent/part models are explicitly allocated synthetic relocated
records. The entry state supplies the record/object/context and cover flag;
this is not a full seventeen-slot equipment traversal.

The prior cover flag is sticky and only eligible equipped parts with both
mesh and texture handles can set it (`0x1a3b90–0x1a3ccc`). The original
substring routine executes using tokens loaded privately from the ELF:

| Model / definition slot | Cover condition | Token addresses |
|---|---|---|
| Any except 7 / slot 11 | definition name does not contain token A | A: `0x535d70` |
| 7 / slot 11 | picture base lacks B and definition name lacks A | B: `0x535d78` |
| 7 / slot 4 | picture base contains C | C: `0x535d80` |
| 9 / slot 4 | name contains D, or nonnull picture base contains E | D: `0x535d90`; E: `0x535d98` |

**Observed; Executed:** with cover clear, both optional layers reach their
handle checks. With cover set, hair reaches them only for model 11 or model
10 with skin 4; beard reaches them only for model 11, or a present head item
whose definition name contains token `0x535da8` or whose player model is 6.
Each layer independently requires both mesh and texture. The tests include
all sixteen combined handle-presence patterns, positive and negative cover
conditions, and exact/embedded substring controls.

**Observed; Executed:** body mask `object+0x220` starts as all 64 bits set.
Signed counter `0x41b514 >= 0x111` replaces it with original `0x179550`
using the body model and selection bit one. That function complements header
default-hidden bits and applies selected variant records in ascending bit
order: add show bits, then remove hide bits. Only actually drawn equipment,
hair, or beard clears its header's hide mask from the body mask. Nonzero
authored hide masks and individual missing handles verify these writes,
including exact hair/beard write sites `0x1a3e84/0x1a3f30`.

**Observed; Executed attachment correction:** `0x1760ec` reads signed part
header `+0x13` first. If it is −1, attachment selection is disabled **even
when an explicit override is nonnegative**. Otherwise the effective index is
the override unless that is −1, in which case the header is used. The record
address is:

```text
parent + (parent.byte[0x22] * 16) + effectiveIndex * 0x34
```

The selector itself does not check parent flag `0x04`. Therefore that flag's
format meaning must not be turned into a runtime conditional absent from
`0x1760f8–0x176134`. Tests exercise all sixteen valid attachment indices,
header −1 with a null parent and an override, and a valid table with parent
flag clear. The joint index is multiplied by four for the packet at
`0x17614c`; matrix packet copies, including mirrored first-row values, match
an independent reference. Invalid indices are outside the tested table
boundary; the original selector does not supply a safety clamp.

Direct draw probes also compare mesh-table clamping and mask-selected
contiguous mesh ranges through actual packet writes. A synthetic 64-mesh
edge preserves the original EE shift behavior (bit-zero clearing and an
unflushed trailing shown run); retail reachability of that edge is **Unknown**.
The linked one-equipment-iteration probe executes the second-slot attachment
override, model-2 mirroring/reset, body hide update, and then the final optional
layers. The shield variant bit, the published starting-slot draw arguments, and
the shell parameter block are executed in the following section. Animated joint
evaluation, the shell primitive `0x174e78`, and VU/GS rendering remain
**Unknown**.

The handle fields join constructor output to these consumers
**compositionally**. Synthetic attachment tests by themselves do not establish
which attachment indices occur in selected retail assets, nor when the body
draw consumes the updated mask. Those are distinct from verifying selector
arithmetic and emitted packet fields.

## Equipment visuals by class and body

Starting armor definitions, header selection, and metadata offsets are the
audited round-4 map. This section does not re-derive them. It executes the
draw arguments that consume those pointer slots, plus the shield mesh bit
selected by body model.

**Reused, not re-executed:** `docs/starting-equipment-r4.md` in
`t3/research-loading-readiness` at `366b65a`. Armor pointer slots are 4, 10
and 12 for every body. Weapon pointer slot and class index are the table at
lines 43–56 of that note. Single-player header group counts and the slot
4/10/12 metadata deltas are lines 76–124 there. Those items already have
variant bits at item `+8` equal to zero for the generated armor. This probe
therefore enters the draw with flag word zero on those published slots. It
does not open the header loader or the cache again.

**Observed; Executed:** definition slot 3 takes `0x1a3cfc–0x1a3d84`. The
unsigned compare at `0x1a3d00` sends any model that is not 0..11 to variant
bit 0. Models 0..11 jump through `0x535e00` and select one bit:

| Body | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Class, from the reused map | 0 | 0 | 3 | 3 | 1 | 1 | 4 | 4 | 2 | 2 | 5 | 6 |
| Shield bit | 1 | 0 | 9 | 8 | 7 | 6 | 5 | 4 | 3 | 2 | 1 | 9 |

The bit is the selection word of `0x179550` on the **part** model, and that
function's show mask is the show-mask argument of the part draw. A class
pair does not share a bit. Body 10 matches body 0, and body 11 matches body
2, because the jump table says so, not because they share a class. The
original slice was run for all twelve bodies, for models −1, 12 and 15, with
the variant table enabled and disabled and with item flag bit 33 clear and
set. Evidence:
[shield rows, lines 477–517](../../tools/difftest_char_attachment.py#L477)
and [the bit table, lines 122–148](../../tools/ref_char_attachment.py#L122).
The record's class word at `+0x50` is stored with a mismatched value and is
not read.

**Observed; Executed:** each published pointer slot is also one original
iteration of `0x1a3b90–0x1a3df8`, with the pointer index equal to the
definition slot. None of those indices is 1, so the attach override stays
−1 and the packet uses header `+0x13`. The show-mask argument stays all ones
because the slot is not 3, so `0x179550` is not called. Model 2 does not
mirror on these slots. Both resource handles are present, so the part's
hide qword is cleared from object `+0x220`. Evidence:
[starting rows, lines 519–551](../../tools/difftest_char_attachment.py#L519).
A separate off-hand iteration (pointer index 1) still forces override 1.
The override compare at `0x1a3dd0` calls `0x179978` whenever that override
is not −1, for every model. Model 2 additionally calls `0x179860` before
the draw. The reset stores `0x41c150` at `0x41c160` and clears the shell
count. A shield in that same off-hand iteration still applies the
body-model bit.
Evidence:
[composed rows, lines 554–598](../../tools/difftest_char_attachment.py#L554).

**Observed; Executed:** `0x1068d8` reads item flag bit 33 through `0x1046c4`,
which returns 7 when the bit is set and 0 when it is clear. Clear stores
the block address `0x3e9cd0` at `0x41c160` and count 0 at `0x41c164`, and
does not write the block. Set stores the same pointer and count 2. The
scale is `7 * 0.025 + 0.6` in the R5900 truncating operations, clamped down
to 1 only when that sum exceeds 1; with this constant 7 the clamp is not
taken. Byte `+3` is the truncated scale times 64 (49). Byte `+11` is the
truncated scale times 72 (55). Float `+4` is the draw argument times 200.
Float `+12` is the draw argument times 100. No other block byte is written.
This is not an item-level lookup. Evidence:
[shell fields, lines 292–312](../../tools/ref_char_attachment.py#L292)
and [direct calls, lines 601–614](../../tools/difftest_char_attachment.py#L601).

The draw argument itself, for the caller at `0x1a4d08`, is executed from
`0x1a4cac` with the other projection terms set to zero. f0 is absolute-valued,
then the result is 5 when that magnitude is at least 360. Below 360 it is
`5 - (360 - magnitude) *` the constant loaded at `0x1a4cdc`, and at least 1.
The three factors that form the projection before this slice are **Unknown**.
The other caller, `0x1c0c6c`, loads the constant 1.5 at `0x1c0c64`. Evidence:
[argument rows, lines 615–628](../../tools/difftest_char_attachment.py#L615)
and [the clamp, lines 269–289](../../tools/ref_char_attachment.py#L269).

Part flag `0x20` together with a positive count at `0x41c164` is what sends
`0x178c28` into `0x174e78`. The cases above leave flag `0x20` clear. The
primitive itself is executed in the next section.

## Pose, the body-mask frame, and the shell primitive

Three different clips are installed, and the body draw reads the show mask
that the previous equipment pass stored.

**Observed; Executed** creation restart `0x2254bc–0x2255b4`. The preview
object is `*(scratch + 0x1558 + 4*row)` with the scratch pointer loaded
from `0x4fdb7c`. A start happens only when the halfword at object `+0x11a`
has bit `0x80` and the count byte at object `+0x118` is less than 2.
Bit `0x08` of that halfword selects the format at `0x53ff58`; otherwise
the format is `0x53ff68`. Both are a leading `%s` plus a fixed suffix.
The `%s` is the descriptor name at `0x4fbbf8 + row*0x26c`, unless that
name is the literal at `0x53fd38`. That literal instead copies one of the
thirteen short names selected by the signed byte at `0x8e2c91` (the byte
plus one, and only results 0..12). `anim_start` is called with flags 3.
The new cell's time and weight are 0. On an empty state the 0.2 blend
loaded at `0x225584` is forced to 0, so the rate is 1. When the count is
already 1 the new cell keeps that blend and the rate is `0x3daaaaab`.
Evidence:
[creation rows](../../tools/difftest_char_picture.py#L139).
`playerSel_task` and the helpers through `0x22e700` do not call
`anim_advance`. The installed frame is therefore time 0 and weight 0.
Which other task steps that preview object before a draw is **Unknown**.

**Observed; Executed** three transition setups, same empty-state cell
(time 0, weight 0, rate 1):

| Slice | Format | Flags |
|---|---:|---:|
| `0x226dec–0x226e44` | `0x5400c8` | 6 |
| `0x228508–0x22855c` | `0x5400c8` | `0x16` |
| `0x228a88–0x228ad8` | `0x540330` | `0xe` |

**Observed; Executed** `inventory_selectIdleAnim` `0x1c3f08`. The lump name
is chosen by the model index through `0x5385b0`, and the clip name is
chosen by weapon class `+0x4a86`: classes 1, 2, 3, 4, 5 and 7 each have
their own address, and every other class shares `0x538598`. Flags are
`0x43` (loop, purge-below, fixed step). If that clip is already the
current track, the time word is not written. A fresh empty state stores
time 0, weight 0 and rate 1; the 0.1 blend at `0x1c4078` is forced off
for cell 0. The inventory draw then calls `anim_advance` at speed 1 from
`0x1c0a10`, before `model_draw`. One such step from that fresh cell stores
time `0x3f7fffff` and weight 1. That is the first frame the inventory
stand draws. Evidence:
[inventory and play rows](../../tools/difftest_char_picture.py#L206).

**Observed; Executed** `player_resetIdleAnim` `0x1b2470`. No player at
`+0x43d8`, or hit points `+0xac` not greater than 0, leaves a prefilled
clip word unchanged. Otherwise cells 0..3 receive the definition clips at
`class*0x68 + {0x44, 0x4c, 0x54, 0x5c}`, the count becomes 4, cell 0's
weight and life become 1, and the flags are `0x1205`. Object byte `+0x462`
nonzero replaces only cell 0, with the idled name for classes 1, 2, 3, 4
and 7, and `0x537628` for every other class. The time word and the rate
word are not written: a nonzero sentinel in either one survives. The frame
shown in play is therefore whatever later steps have done to that time.
At rest, `Player_move` already steps cell 0 at rate 1
(`docs/spec/player-animation-selection.md` on `t3/research-player-anim`);
this round did not re-execute that function. Cache release `0x171118` is
stubbed here, as in that earlier selector test.

**Observed** `Player_draw` reaches the body in this order. One path calls
`model_draw` at `0x1a4bfc` with show-mask argument −1, calls `0x179978`,
and skips the body. The other path calls `Creature_draw` at `0x1a4c28`
and only afterwards `Player_drawEquipped` at `0x1a4d08`. Inventory does
the same kind of split: `model_draw` at `0x1c0c58`, then
`Player_drawEquipped` at `0x1c0c6c`.

**Observed; Executed** the load that feeds that body draw. `Creature_draw`
at `0x10ba84` reads object `+0x220` and passes that 64-bit word as `r10`
of `model_draw`. Inventory reads the same word at `0x1c0a28` and passes it
from `0x1c0c20` with layer 6, mesh object `+0x544` and texture object
`+0x550`. The walk `0x177df4–0x177eb0` then emits the same mesh runs as
`mesh_runs` for masks 0, 1, `0b010`, `0b101` and all-ones, including one
empty mesh. The body picture therefore uses the mask stored by the
previous `Player_drawEquipped`, not the update that follows the body draw
in the same call. Evidence:
[mask rows](../../tools/difftest_char_picture.py#L317).

**Observed; Executed** `model_emitShellPasses` `0x174e78`. Flag `0x20`
clear leaves a prefilled packet unchanged. Flag set walks table 0: the
boundary list is read at model `+0x28`. A positive count at `0x41c164`
and that flag are both required at the `model_draw` gate `0x177da4` and
the `model_drawPart` gate `0x178c88`; either one missing skips the call.
The call is `(cursor, model, 1, pointer at 0x41c160, count)`. Each 8-byte
record is four colour bytes and one float. The pass stores that float,
those bytes, and `0x1400002a`, then one DMA reference per nonempty run of
table 0 (the low mesh-count bits are set). A zero third argument selects
the `0x44` setup word; the callers pass 1, which selects `0x48`. The
trailer stores `0x6001c000`, `0x1400002a` and a zero word, then the qword
at model `+0x18` and test word `0x507f5`. The byte image is
[shell_packet](../../tools/ref_char_attachment.py#L398). Joint matrices
and the GS rasterizer remain **Unknown**.

## Remaining boundaries and client handoff

- **Documented:** appearance count discovery, helper bounds/reset semantics,
  the special skin/hair rule, acceptance-field snapshot, both addressed handoff
  routes, record stores, resource selection and exact handle destinations.
  Original optional-layer gates, hide-mask changes and attachment-packet
  selection are documented within the synthetic boundaries above. The shield
  variant bit for each body model, the draw arguments of the published
  starting pointer slots, and the flag-33 shell block are documented in the
  equipment section. The creation, inventory and in-play clip installs,
  the show-mask argument of the body `model_draw`, and the shell packet are
  in the pose section.
- **Partial:** the test joins bounded slices and full helper functions with
  constructed entry state. Resource lookup proves archive membership and
  returned-handle propagation, not actual loading/relocation or GPU use.
  Starting item identity and metadata offsets are reused from round 4; this
  note does not re-execute that loader. The draw argument's projection inputs
  are not named. The creation preview is installed at time 0 and weight 0;
  the task that would step it was not found in the selection functions.
  In-play time is not rewritten by the idle reset, and `Player_move` was
  not re-executed. `anim_releaseCaches` stays stubbed.
- **Unknown:** input reachability of every option combination, the full menu
  confirmation/cancellation lifecycle, live preview/camera parity, which
  task advances the creation preview, animated joint matrices, and a
  continuous created-character-to-rendered-player run. No native refusal
  was removed and no client files were changed.

The client can implement these pieces without inventing values:

1. Appearance gates and handle pairs, lines 193–208. Keep a null optional
   pair when lookup fails.
2. Attachment packets, lines 210–227: header `+0x13` of −1 selects nothing,
   including when the override is nonnegative; otherwise the override
   replaces −1 only. Copy the 3×4 matrix, mirroring the first row when the
   draw flag says so.
3. Starting visuals by body: use the round-4 class, weapon slot, armor slots
   4/10/12, and metadata deltas. Draw those parts with show mask all ones,
   attach index from the part header, and the hide-bit clear. Do not switch
   that path on the class word. A worn shield (definition slot 3) instead
   uses the body-model bit table in this section.
4. Shell parameters: flag bit 33 clear means count 0; set means count 2 and
   the four block fields above. Draw `0x174e78` only when the part flag
   `0x20` is set and that count is positive. Each record is one pass over
   every nonempty table-0 mesh, then the restore pass. The byte image is
   `shell_packet`.
5. Creation pose: the restart rules and the three transition formats above.
   Install time 0 and weight 0. Do not invent a step the selection task
   does not perform.
6. Inventory pose: the model lump and the class idle filename, flags `0x43`.
   The first drawn frame is one fixed step later: time `0x3f7fffff`, weight
   1. A repeated draw keeps stepping; do not restart a clip that is already
   playing.
7. In-play pose: the four definition clips, or the idled name when object
   `+0x462` is set. Leave the current time in place across a reset.
8. Body meshes: pass object `+0x220` as the show mask of `model_draw`.
   Use the mask from the previous equipment pass. The runs are `mesh_runs`.

Preserve explicit unknown appearance for records lacking the four choice
bytes. Leave animated joint matrices and the creation-preview step refused
until they have their own executed evidence.

## Reproduction

Owner inputs belong under ignored `local/`. Run from this worktree, with
`unittest` loaded before adding `tools/` to avoid the local `dis.py` shadow:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
import unittest, sys, runpy
sys.path.insert(0, 'tools')
for seed in (20973, 7):
    sys.argv = ['tools/difftest_char_appearance.py', 'local/SLUS_209.73',
                'local/char-appearance/disc.iso', '--seed', str(seed)]
    runpy.run_path(sys.argv[0], run_name='__main__')
PY
```

Each seed passes 24 scanner rows, 3,308 control/normalizer cases, 462
handoff/constructor cases and 15 failure controls. Disc-backed null returns
are 8 for seed 20973 and 16 for seed 7 because the additional random skin
choices differ. They are expected null outcomes, not ignored failures.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_char_attachment.py \
  local/SLUS_209.73 --seeds 20973 7
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_*.py'
```

The attachment probe passes the previous 12,069 cases per seed (42 variant
masks, 14 initializations, 4,627 direct part draws, 1,818 cover gates, 4,608
appearance cases and 960 linked equipment/appearance cases) and adds 60 shield
rows, 48 starting-slot rows, 3 composed off-hand rows, 20 shell-block calls
and 11 draw-argument rows.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/difftest_char_picture.py \
  local/SLUS_209.73 --seeds 20973 7
```

The picture probe passes 7 creation rows, 211 pose rows and 16 draw rows on
each seed. The repository analysis suite stays 652 tests. These results are
executed evidence, not screenshots.
