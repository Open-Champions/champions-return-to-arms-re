# Ground items (`ItemProp_ctor2`) and `givePlayerRandom`

US `SLUS_209.73` v2.00. This note closes two gaps of `docs/script-items.md` 10: the seed
draw inside `ItemProp_ctor2` (the ground-item path of every give and of the inventory
drop), and `givePlayerRandom` composed with its real callees.

| File | What |
|---|---|
| `tools/ref_item_drops.py` | model: `ItemProp_ctor2`, `Prop_ctorNamedLaunch`, `Prop_launch`, `GameObject_ctor` (no definition, no properties), `item_getResourceIndex`, `givePlayerRandom` |
| `tools/difftest_item_drops.py` | runs the originals in `tools/ee_emu.py` against the model (suites `ctor`, `random`) |
| `tools/test_ref_item_drops.py` | 9 synthetic tests, no game file needed |

The prop-chain bodies follow `tools/ref_phprop.py` and `tools/ref_skills_a.py` on
`t3/research-combat-ctors-3` (9ff6ae0). They were executed again here under
`ItemProp_ctor2`. "Executed" means the difftest ran it. Nothing was seen on a running game.

## 1. `ItemProp_ctor2(block, position, item, launch)` 0x1590ec (Executed)

### 1.1 Callers

All seven call sites pass launch 0 and a block from `pool_new(0x190)` (Observed):

| Site | Function |
|---|---|
| 0x145c78, 0x145cd0 | `givePlayerItem` (own object, or the object of `g_alivePlayers[0]`) |
| 0x145ef0 | `giveOnePlayerItem` |
| 0x146130, 0x146234 | `givePlayerRandom` (special item, random item) |
| 0x1c24a4 | 0x1c2120 (unnamed, inventory code) |
| 0x1c47f4 | `inventory_dropItem` 0x1c4310 (inventory message 0, mode 0) |

### 1.2 What it does

1. Copies the 12-byte position to its frame.
2. Calls `item_getResourceIndex(item)` 0x1083f8 twice. The row is definition +0x34, plus the
   variant (flag bits 11–15) when flag bit 36 is set (`ref_items.resource_index`).
3. Calls `Prop_ctorNamedLaunch(block, &position copy, lump 0x5326b0, model, texture, part mask, launch)`.
   The model name is word +0 and the texture name word +4 of 16-byte row `row` of the model
   table 0x3e9ce0. The part mask is −1 (t1, so all 64 bits).
4. Sets table +0x48 = 0x511c38.
5. Writes the empty item record at +0x148: halfwords +0x16c, +0x174, +0x17c, +0x184 = 0xffff,
   bytes +0x169 and +0x168 = 0xff, halfwords +0x158..+0x166 = 0.
6. Copies the 0x48 bytes of the item over it with `ld`/`sd`. Both the item and block +0x148
   must be 8-aligned.
7. Sets flags +0xc = (flags | 0x102000) & ~0x1800, and also & ~0x3000 when bit 39 of the
   copied item flags (+0x150, the test value 0x8000 << 24) is set.
8. Calls `obj_updateGridCell(block)`.
9. Sets the matrix +0x110 to `mat34_setPosRotZ(position +0x10, s16(facing +0x38 + 0x4000))`.

It does **not** call `PhProp_initPhysics` and plays no sound. That is the difference from
`PhProp_ctor` (`ref_phprop`).

`Prop_ctorNamedLaunch` 0x153e54 does the following:

- `GameObject_ctor(block, position, 0, 0)` 0x14cb10, which writes heads +0/+4/+8, flags +0xc,
  +0x34 = 0, table 0x5122a8, radius +0x1c = 24.0, height +0x20 = 72.0, bytes +0x28 = 0x19
  and +0x29 = 0x49, the position, +0x24 = 0, the grid link
  `handle_link(cell, block+8, block)` (cell from ((int)x + 0x3c00) >> 8, 120 × 120 at
  0x5db4f0, else the off-grid list 0x5f76f0), `obj_getPropInt(block, 'hide' 0x5321a8, 0)`
  and +0x2c = 0, then **+0x44 = one shared draw**.
- Table 0x511d58, then the lump, model and texture names `strcpy`'d to +0x54, +0x64 and
  +0xa4.
- +0x4c / +0x50 = `res_find(lump copy, model copy / texture copy)`, and +0xe8 = the part
  mask.
- **One own draw**: the facing +0x38.
- +0x10c = 0 and +0x30 = +0x100 = +0xfc = 0.
- The centre of `model_getBounds` at +0xf0..+0xf8, and +0x108 = centre z − min z.
- Launch bit 4 moves the position by the centre.
- Then `Prop_launch` 0x1541a0, which writes: flags |= 0x1809, `obj_updateGridCell`, radius
  4.0, velocity draws by launch bit, `obj_runEveryFrame`, and life +0x10e = 180 (0x7fff
  with 0x8000). The table of launch bits is in `ref_item_drops.Ground.prop_launch` and
  `docs/spec/gut-chunk.md` on that branch.

### 1.3 Draws

| Draw | Generator | Decides |
|---|---|---|
| 1 | **shared seed 0x404464** (in `GameObject_ctor`) | seeds the prop's own generator +0x44 = seed >> 16 |
| 2 | own +0x44 (`GameObject_rand` 0x1509d0) | facing +0x38 = low 16 bits |
| 3.. | own +0x44 | velocity, by launch bit: 1 → 2, 8 → 2, 0x10 → 3, 0x20 → 1, 0x40 → 1 |

**With launch 0, as every caller passes, a ground item costs exactly one shared draw and
one own draw.** The suite checked that the shared seed advanced by exactly one step in
every case. The facing then comes from the prop's own generator, and no later shared draw
depends on it.

Per machine: none in the chain. The leaf call-outs `res_find`, `model_getBounds`, the grid
and run lists are object or world bookkeeping (stubs here).

## 2. `givePlayerRandom` 0x145f18 (Executed)

For slot 0 .. `g_numPlayers` − 1 (re-read after each player), the stack record at frame +0:

1. **Blank.** Halfwords +0x24, +0x2c, +0x34, +0x3c = 0xffff, bytes +0x21 and +0x20 = 0xff,
   halfwords +0x10..+0x1e = 0. **+0x00..+0x0f (definition, count, flags), +0x22/+0x23 and
   +0x44.. are not written**: they keep what the stack held.
2. **d = one shared draw.** s = `level_monsterLevelTimesDifficulty()` 0x1ebf70.
   budget = cvt.w.s((float)d × s × 0.015), with 0.015 = 0x3c75c28f, as two single
   multiplies in that order.
3. **Special level.** If `strstr(level name 0x41b721, 0x5312a8)` is non-null:
   - For difficulty (0x4f719c) 1, 2 or 3: `item_parseDescriptor(text, record, 0, 0)`, with
     the texts at 0x5312b8, 0x531308 and 0x531358. Variant 0 means no draw. Then bytes
     +0x20/+0x21 = (0x12, 0x33), (0x33, 0x34) or (0x24, 0x35).
   - For any difficulty, give or drop (step 5). For difficulty 4 or 5 the record is still
     the blank one.
4. **Up to 10 times** (0x146194): r = one shared draw, then
   `item_generateWithAffixes(record, budget, r & 1, −1, cvt.w.s(g_levelMonsterLevel 0x4f714c))`.
   It stops at a non-zero result. r & 1 picks the category: 0 weapon, 1 armour. On failure
   the record is not written (Executed: the model leaves it, and every compared case
   agreed).
5. **Give or drop**, run whatever the record holds. w = `player_itemWeight(slot, record)`.
   - If load + w < limit (`c.olt.s` only, so a weight of 0 needs room too):
     `inventory_giveItem(slot, record, 1)`, then `player_recalcLoad(slot)`. The result is
     not tested, so a full bag loses the item.
   - Otherwise `pool_new(0x190)`. When it returns a block:
     `ItemProp_ctor2(block, position of record +0x43d8's object, record, 0)`. There is no
     null test for the object. A null block loses the item.

Shared draws per player: 1 (budget) + 1 per generator call (1–10) + the generator's own
draws + the parser's 0 + **1 per ground item**. Each player makes at most two ground items
(special and random).

Error paths (all executed: both sides fault, or both agree):

- **The generator fails 10 times** (a small d makes a small budget). The record keeps the
  blank fields plus the stale +0x00..+0x0f, and is then given or dropped. With a stale
  definition 0, the weight is 1.0. `inventory_giveItem` then reads the category at address
  0x1d, or `item_getResourceIndex` reads 0x34 on the drop path. The emulator faults; on a
  console these are kernel-memory reads with an unknown result. The model raises `Fault`.
- **Special level at difficulty 4 or 5.** The same stale record is given or dropped once
  before the random item.
- **Drop for a record without an object** reads address 0x10, the same as `givePlayerItem`.
  The model raises `Fault`.
- **Bag full or held-once item** loses the item (`docs/script-items.md` 2.4).

## 3. Disc

`givePlayerRandom` has **0 calls** in the 120 shipped scripts (`docs/script-items.md` 7). The
only reach is a non-shipped script.

## 4. Runs

- `python3 tools/difftest_item_drops.py --cases 200 -k ctor` (seed 20973) and
  `--cases 100 --seed 7 -k ctor`: the block, calls, seed and outside writes are compared,
  and every case must make one shared draw.
- `python3 tools/difftest_item_drops.py --cases 40 -k random` (seed 20973) and
  `--cases 20 --seed 7 -k random`. These replace the library string routines, as the
  `-fast` suites of `difftest_items` do. `--full` keeps them original. A case costs about
  3–7 s.
- `python3 -m unittest discover -s tools -p 'test_ref_item_drops.py'` (9 tests).

Results are in the parent report and `docs/script-items.md`.

## 5. What the native client should do

1. **Ground items (needed now).** Replace the `ItemProp_ctor2` refusal with: one
   shared-seed draw, which seeds the prop's own generator, then one own draw for the
   facing. Copy the record to +0x148 and set the flags as in 1.2. The position is not
   moved (launch 0). This unblocks the drop path of `givePlayerItem`/`giveOnePlayerItem`
   and the inventory drop, with the shared seed kept in step.
2. **`givePlayerRandom`.** Keep it refused. No shipped script calls it. Implementing it
   would mean porting `item_generateWithAffixes` (already specified in
   `docs/spec/items.md`) and copying the stale-record fault behaviour, for no disc
   benefit.

## 6. Unknown / open

- What the stack held in the record's +0x00..+0x0f on a real console when the generator
  fails 10 times. It depends on earlier calls. The difftest plants a definition 0 or a
  valid definition.
- The 0x1c2120 caller was not identified beyond "inventory code".
- The `random` suite was not run with `--full` (library original) at volume.
