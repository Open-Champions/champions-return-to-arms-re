# The weapon holder: Weapon1 and WeaponShield slots 1–17, the element setters, the part drop

US `SLUS_209.73` v2.00. Prose of `tools/ref_weapon_holder.py`. The comparison is
`tools/difftest_weapon_holder.py`; the synthetic tests are `tools/test_ref_weapon_holder.py`.
Written 2026-10-21 for item 8 of `docs/spec/full-placement.md` §4 (the Skeleton's element
slots).

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
and the model agreed on the calls to everything outside the models (in order, with
arguments; vectors read at the call), every byte stored outside the stack, the shared seed
`0x404464` with its draw count, and the result. **Observed**: read at the address.
**Inferred** and **Unknown** as usual. Nothing here ran on a console, in PCSX2 or on the
live rig.

## 1. How it was run

Holders of both classes are made up in interpreter memory: the game's own table at `+0`
(Weapon1 `0x50cf40`, WeaponShield `0x50cda0`), random hand bits `+4`, parts `+8` and
`+0x98`, and descriptor ids and values at `+0x50`. Each case takes one of slots 1–17 from
the table (address and `this` adjustment as the table holds them) and calls it with a hand
number from 0, 1, 2, 3, −1 and `0x80000001`, plus that slot's other arguments. About one
case in sixteen calls one of the three helpers directly.

What runs for real: every body in `ref_weapon_holder.EXECUTED` and the C library.

Callbacks (recording stubs answered by a scripted world):

- slot 11 of the Skill objects at `g_skillTable` `0x41b170` entries 12, 13, 14, 25 and 26,
  reached through each object's `+0x60` table. The objects are synthetic, some with a
  non-zero `this` adjustment;
- the creature's slot 16 (a synthetic table);
- `model_getAttachPoint` `0x1754a0` (it writes the point in three cases of ten);
- `pool_new` `0x14fdb8` (a block in eight cases of ten);
- `PhProp_ctor` `0x155a0c`.

`g_levelMonsterLevel` `0x4f714c` and the shared seed change between cases.

Commands:

    python3 -u tools/difftest_weapon_holder.py --seed 20973 -v
    python3 -u tools/difftest_weapon_holder.py --seed 7 -v
    python3 -m unittest tools.test_ref_weapon_holder

| | Seed 20973 | Seed 7 |
|---|---|---|
| Calls compared (34 slot bodies, about 130–195 each; the three helpers 110–132 each) | 6,000 | 6,000 |
| Shared draws seen | 883 | 882 |
| Mismatches (calls, writes, seed, result, faults) | 0 | 0 |

Checks (each change to the model was detected, on 600 calls of seed 20973):

- kind 6 building id `0x15` instead of `0x1f`: 19 mismatching calls;
- flag `0x100` added only for creature flag `0x1000000`: 3;
- WeaponShield slot 13 clearing bit 0 instead of setting it: 5.

## 2. Coverage (instructions executed of the body)

| Function | Address | Executed | Not executed |
|---|---|---|---|
| `creature_buildElementDamage` | `0x1176e0` | 341 of 404 | 18 blocks, all dead: see §3.1 |
| `creature_dropHeldPartAsProp` | `0x117d30` | 86 of 86 | |
| `damageDesc_getElement` | `0x117e88` | 31 of 32 | the padding `nop` `0x117f04` |
| Weapon1 slot 1 | `0x11afb0` | 14 of 16 | padding `nop`s `0x11afd4`, `0x11afec` |
| Weapon1 slots 8–17 | `0x11aff0`–`0x11b180` | all | |
| Weapon1 slots 2–7 | `0x3c1d08`–`0x3c1df8` | 11 of 12 each | the trailing padding `nop` |
| WeaponShield slot 1 | `0x11bc18` | 29 of 30 | padding `nop` `0x11bc3c` |
| WeaponShield slot 11 | `0x11bc90` | 52 of 52 | |
| WeaponShield slots 12, 13, 14 | `0x11bd60`, `0x11bda0`, `0x11bde0` | 15 of 16 each | the trailing padding `nop` |
| WeaponShield slot 17 | `0x11be20` | 8 of 8 | |
| WeaponShield slots 2–7 | `0x3c23e0`–`0x3c24d0` | 11 of 12 each | the trailing padding `nop` |
| WeaponShield slots 8, 9, 10 | `0x3c2500`, `0x3c2530`, `0x3c2560` | 12 of 12 each | |
| WeaponShield slots 15, 16 | `0x3c2590`, `0x3c25c0` | 10 of 12, 15 of 16 | padding `nop`s |

Both seeds give the same coverage.

## 3. The bodies

The holder `h`:

- word `+0` is the table;
- byte `+4` holds the hand bits: bit 0 means hand 1 carries a part, bit 1 means hand 2 does;
- byte `+8` is the hand-1 part;
- the hand-1 damage descriptor is at `+0x50`. Its layout is that of
  `difftest_monsters_1.decode_descriptor`: eight halfwords at `+0x10`, two bytes at `+0x20`,
  and four effect slots of `(id, value, value, 0)` at `+0x24`;
- WeaponShield only: byte `+0x98` is the hand-2 part.

The hand argument is tested on the full register:

- "hand 0 or 1" is an unsigned `sltiu 2`, so a negative hand is neither;
- "hand 1" and "hand 2" are equality tests.

No slot reads or writes anything outside the holder, except through the helpers.

### 3.1 creature_buildElementDamage `0x1176e0` (x, descriptor, kind)

*Executed.* `x` (the callers pass `h + 4`) is not read.

1. The kind is narrowed to its low byte (`andi` at `0x1176e4`).
2. All four effect slots are freed: id `0xffff` at `+0x3c`, `+0x34`, `+0x2c`, `+0x24`, in
   that order. This happens even for kinds that build nothing.
3. The jump table `0x5300d0` holds seven words, for kinds 0–6. Kind 0, and kind 7 and above,
   stop here.
4. Otherwise, with the kind's Skill object `S` and entry id from the table below:
   - `a` = slot 11 of `S` (its table at `S + 0x60`, slot 11 at table `+0x58`/`+0x5c`;
     `Skill_getStatTier2` in the real table, `docs/spec/antqueen-run.md` §3), called with
     `(0, trunc(g_levelMonsterLevel), 0)`.
   - **ONE SHARED DRAW** `d` (`0x404464`, stored at once).
   - `v = trunc((float(a) × 0.2) × (float(d) × 2⁻¹⁶))`, multiplied in that order.
   - Slot 0 gets `(id, a, a + v, 0)` as halfwords, with the low 16 bits of each.

| Kind | Id | Skill pointer (`g_skillTable` index) | Pointer load, id load |
|---|---|---|---|
| 1 | `0x15` | `0x41b1a4` (13) | `0x117750`, `0x117780` |
| 2 | `0x16` | `0x41b1a8` (14) | `0x117848`, `0x117878` |
| 3 | `0x17` | `0x41b1d8` (26) | `0x117940`, `0x117970` |
| 4 | `0x18` | `0x41b1a0` (12) | `0x117a38`, `0x117a68` |
| 5 | `0x26` | `0x41b1d4` (25) | `0x117b30`, `0x117b60` |
| 6 | `0x1f` | `0x41b1a4` (13, the same Skill as kind 1) | `0x117c28`, `0x117c58` |

Constants:

- 0.2 is `0x3e4ccccc` (`0x1177a4`/`0x1177a8`; each case has its own copy);
- 2⁻¹⁶ is `0x37800000` (`0x1177b4`).

The search for a slot of the same id, or a free one, always takes slot 0, because step 2
has just freed it. The 18 blocks never entered are that search's other exits in each case:
`0x117814`, `0x11781c`, `0x117834`, and their copies up to `0x117d08`. They are dead
(Inferred from the reading; the same dead search as `docs/spec/antqueen-run.md` §2).

Draws: one shared draw for each kind 1–6, none otherwise. Writes: the descriptor's
`+0x24`–`+0x2a` and the ids at `+0x2c`, `+0x34`, `+0x3c`.

### 3.2 damageDesc_getElement `0x117e88` (x, descriptor) → element

*Executed.* `x` is not read. The four ids at `+0x24 + 8k` are read as signed halfwords.
Each is tested in turn, and a later match replaces an earlier one:

- `0x15` → 1, `0x16` → 2, `0x17` → 3;
- otherwise `0x1f` → 6, then `0x18` → 4 (two `movz`, `0x117ee4`, `0x117eec`);
- any other id keeps the answer.

The result is 0 when nothing matched. Kind 5's id `0x26` is not reported. No draws, no
stores.

### 3.3 creature_dropHeldPartAsProp `0x117d30` (x, part, creature c, definition, flags)

*Executed.* `x` is not read, and no draws are made. Nothing happens for:

- part 0 (tested on the full register);
- `c` = 0;
- object flag 2 at `c + 0xc`.

Otherwise:

1. A zero definition becomes `c + 0x24`.
2. The record is `rec = definition + 8 · part`.
3. The bone is the **signed** byte `+0x13` of the record word `rec + 4`. It is loaded in
   the delay slot of the next call, so a null record faults there.
4. `model = c`'s slot 16 (table `+0x80`/`+0x84`, `this` adjusted).
5. `model_getAttachPoint(model, copy of c+0x10, s16(u16 facing − 0x4000), c + 0x114, bone,
   point out, second out; 1.0)`. The point buffer already holds the position, so a callee
   that writes nothing leaves the position.
6. The flags are the argument, or `0x4001` (`0x117da0`) when it is 0. They gain `0x100`
   when `c + 0xa8` (64 bits) has a bit of `0x101000000` (`0x8080 << 17`, `0x117e1c`).
7. `pool_new(0x248)`. Given a block: `PhProp_ctor(block, point, word definition+0,
   word rec+0, word rec+8, 1, flags, 0; scale c+0xdc)`.

Reads: `c + 0xc`, `+0x10`–`+0x18`, `+0x24` (when needed), `+0x38`, `+0x48`, `+0xa8`,
`+0xdc`, and the definition words. Writes: none (stack only).

### 3.4 The slots

| Slot | Weapon1 | WeaponShield |
|---|---|---|
| 1 (hand, part) | `0x11afb0`: hand 1 only. `+8` = part & 0xff; bit 0 set when the part is non-zero, cleared when it is zero | `0x11bc18`: hand 2 stores `+0x98` and bit 1; hand 1 stores `+8` and bit 0, with the same rule |
| 2–7 (hand) | `0x3c1d08`, `0x3c1d38`, `0x3c1d68`, `0x3c1d98`, `0x3c1dc8`, `0x3c1df8` | `0x3c23e0`, `0x3c2410`, `0x3c2440`, `0x3c2470`, `0x3c24a0`, `0x3c24d0` |
| | For hand 0 or 1: `creature_buildElementDamage(h+4, h+0x50, kind)` with kinds 1, 6, 2, 3, 4, 5 for slots 2–7 (the `addiu a2` in each delay slot) | the same |
| 8 (hand, kind) | `0x11aff0` (`Weapon1_setElement`): for hand 0 or 1, the same call with kind & 0xff | `0x3c2500`: the same |
| 9, 10 (hand, a, b, c, d) | `0x11b020`, `0x11b050`: for hand 0 or 1, the halfwords `+0x60`/`+0x68` … `+0x66`/`+0x6e` = the low bytes of a, b, c, d (d stored first). These are the descriptor's `+0x10`–`+0x1e` | `0x3c2530`, `0x3c2560`: the same |
| 11 (hand, c, definition, flags) | `0x11b080`: hand 0 or 1 with bit 0 → drop part `+8`, clear bit 0 | `0x11bc90`: the same; then hand 0 or 2 with bit 1 → drop part `+0x98`, clear bit 1 |
| 12 (hand) | `0x11b0d0`: hand 0 or 1 → bit 0 set | `0x11bd60`: the same; hand 0 or 2 → bit 1 set |
| 13 (hand) | `0x11b0f0`: hand 0 or 1 → bit 0 **cleared** | `0x11bda0`: hand 0 or 1 → bit 0 **set** (`ori`, `0x11bdb0`); hand 0 or 2 → bit 1 cleared |
| 14 (hand) → carried | `0x11b110`: hand 1 → bit 0, else 0 | `0x11bde0`: hand 2 → bit 1, hand 1 → bit 0, else 0 |
| 15 (hand) → part | `0x11b130`: hand 1 → `+8`, else 0 | `0x3c2590`: hand 2 → `+0x98`, hand 1 → `+8`, else 0 |
| 16 (hand) → element | `0x11b148`: hand 1 → a jump to `damageDesc_getElement(h+4, h+0x50)`, else 0 | `0x3c25c0`: hand 1 → a linked call of the same, else 0 |
| 17 (hand) → descriptor | `0x11b180`: hand 1 → `h + 0x50`, else 0 | `0x11be20`: the same; hand 2 → 0 |

In slot 11 the creature, definition and flags pass to the drop unchanged for both hands. A
hand's bit is cleared even when the drop made nothing (part 0, object flag 2, no block).

## 4. What a Skeleton does with its holder

From the callers, which are *Executed* (`docs/spec/combat-ctors.md`, `docs/spec/combat-ctors-2.md`)
or read in `Skeleton_run`.

- **Construction** (`Skeleton_ctor`, `docs/spec/combat-ctors.md` §4):
  - The element roll makes **own** draws (`+0x44`): one for the chance, one more for the
    element on success.
  - Element 1 calls slot 4 (kind 2, id `0x16`). Element 2 calls slot 2 (kind 1, id
    `0x15`). Element 3 calls slot 3 (kind 6, id `0x1f`). All three use hand 1.
  - Each of those calls makes **ONE SHARED DRAW**. It also asks Skill 14 (element 1) or
    Skill 13 (elements 2 and 3) through slot 11 for the level-wide monster level.
  - So a Skeleton with an element advances `g_randSeed` once at construction. One without
    an element does not. This draw was invisible to the constructor difftest, where the
    holder was a recording stub.
  - `ref_weapon_holder.SKELETON_ELEMENTS` has the table.
- **The hit descriptor**: slot 17 with hand 1 gives `h + 0x50`, the descriptor
  `Skeleton_run` state 6 hands to `Creature_hitTargetAtReach`.
- **The arrow**: in state 8, slot 16 with hand 1 gives element 2, 1 or 6 for elements 1, 2
  and 3. *Inferred*: that picks the Cold, Fire or Explode arrow, as `Skeleton_run` compares
  the result with 2, 1 and 6.
- **The shield**: `Skeleton_hasShield` `0x2a7da0` asks slot 15 with hand 2 for part `0x60`
  or `0x62`.
- **Death**: `Skeleton_setState` 0x14 calls slot 11 with hand 1, then hand 2, with
  `(c, skelcom 0x5023e0, 0)`. Each carried part becomes a `PhProp` (flags `0x4001`, plus
  `0x100` for a creature flag of `0x101000000`) through `creature_dropHeldPartAsProp`. The
  part is the row of the skelcom block. *Inferred*: `PhProp_ctor` builds a GameObject, so
  its shared draw (`GameObject_ctor`) follows each prop; `PhProp_ctor` is executed in
  `tools/ref_phprop.py`.

## 5. Corrections and sharpenings

- `docs/monsters-2.md` §2.2: slots 2–7 build kinds 1, 6, 2, 3, 4, 5 (ids `0x15`, `0x1f`,
  `0x16`, `0x17`, `0x18`, `0x26`). Kind 6 uses the same Skill as kind 1. Every build frees
  the other three slots, so an element replaces any other. Each build costs one shared
  draw.
- Slot 13 of WeaponShield sets bit 0 where Weapon1's clears it (Observed `0x11bdb0`). Hiding
  the shield hand with hand 0 therefore shows the weapon hand.
- `symbols/creatures.tsv`: the notes "body not read" on Weapon1 slots 8–17 and
  WeaponShield slots 11–17 can be replaced by §3.4. `symbols/runtime.tsv`:
  "WeaponShield_slot2/3/4 … 44 bytes" are the element setters for kinds 1, 6 and 2.
- `creature_buildElementDamage`'s note "one g_randSeed draw" holds for kinds 1–6 only;
  kind 0 or 7 and above only frees the slots.

## 6. Not executed

- Weapon2 (`0x50ce70`): its slots 2–8 are 100–116-byte two-hand versions; its 9–17 were not
  run.
- Slots 18–24 of both classes: drawing (`model_drawPart`, `creature_drawHeldPart`), the
  per-frame update slot 21 (`fx_modelStatusEffects` behind `isNearView(480)`, presentation),
  and the save/load slots 23 and 24.
- The callees: `model_getAttachPoint`, the creature's slot 16, and `PhProp_ctor` (executed
  elsewhere, a callback here).
