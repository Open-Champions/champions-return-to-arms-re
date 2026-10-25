# The weapon holder, slots 18–24: drawing, the per-frame effect update, save and load

US `SLUS_209.73` v2.00. Prose of `tools/ref_holder_slots.py`. The comparison is
`tools/difftest_holder_slots.py`; the synthetic tests are `tools/test_ref_holder_slots.py`.
Written 2026-10-21. It continues `docs/spec/weapon-holder.md` (slots 1–17 of Weapon1 and
WeaponShield), whose §6 left these slots open, and covers the three holder classes:
Weapon1 (table `0x50cf40`), WeaponShield (`0x50cda0`) and Weapon2 (`0x50ce70`).

Evidence words as in `CONTRIBUTING.md`. **Executed**: the original ran in `tools/ee_emu.py`
and the model agreed on the calls to everything outside the models (in order, with every
argument: vectors and matrices read at the call, `f12`/`f13`, the stack arguments), every
byte stored outside the stack, the shared seed `0x404464` with its draw count, and the
result. **Observed**: read at the address. **Inferred** and **Unknown** as usual. Nothing
here ran on a console, in PCSX2 or on the live rig.

## 1. How it was run

Holders of the three classes are made up in interpreter memory: the game's own table at
`+0`, random hand bits `+4`, parts `+8` and `+0x98`, random descriptors at `+0x50` and
`+0xe0`, junk in the effect blocks `+0xc` and `+0x9c`. Each case takes one of slots 18–24
from the class's table (address and `this` adjustment as the table holds them) and calls it
with arguments from a scripted world: a part definition or 0, parents and chains (non-zero
in 85 % of cases), a creature or 0, a buffer, and `f12` from 0.5, 1.0, 0, −1.0 and 100.
Creatures get random object flags `+0xc`, position, facing `+0x38`, byte `+0x231`, state
`+0x232` (0–20, `0xffff`, `0x8006` and random), scale `+0xdc` and the word `+0x220`. One case
in twenty calls `creature_drawHeldPart` directly; about one in fourteen calls Weapon2's
slot 8 or 16 directly with hands 0, 1, 2, 3, −1 and `0x80000001`.

What runs for real: every body in `ref_holder_slots.EXECUTED` and in
`ref_weapon_holder.EXECUTED` (the save and load slots reach slots 16 and 8 through the
holder's own table, and through them `damageDesc_getElement` and
`creature_buildElementDamage`), and the C library.

Recording stubs answered by the world:

- `model_drawPart` `0x178c28`, `model_draw` `0x1779b0`: the answer is not used;
- `model_getAttachPoint` `0x1754a0` (always writes a point), `model_getAttachWorldMatrix`
  `0x175330` (always writes twelve words);
- `isNearView` `0x1e77c0` (1 in seven cases of ten; its body is executed elsewhere,
  `ref_creature.Model.is_near_view`);
- `fx_modelStatusEffects` `0x1f6ac8`;
- the creature's slot 16 (a synthetic table) and the Skills' slot 11 (synthetic Skill
  objects planted in `g_skillTable`, as in `difftest_weapon_holder.py`).

`g_levelMonsterLevel` `0x4f714c` and the shared seed change between cases.

Commands:

    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_holder_slots.py --seed 20973 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -u tools/difftest_holder_slots.py --seed 7 -v
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tools -p 'test_ref_holder_slots.py'

| | Seed 20973 | Seed 7 |
|---|---|---|
| Calls compared (24 keys: 21 slot bodies by class, Weapon2 slots 8 and 16, `creature_drawHeldPart`; 191–297 each) | 6,000 | 6,000 |
| Shared draws seen (all from slot 24 and Weapon2 slot 8) | 715 | 731 |
| Callbacks the original made: `fx_modelStatusEffects` / `isNearView` / `model_drawPart` / `model_draw` | 212 / 412 / 650 / 470 | 194 / 399 / 636 / 541 |
| Mismatches (calls, writes, seed, result, faults) | 0 | 0 |

Synthetic tests: 20, all pass.

Checks (each change to the model was detected, on 600 calls of seed 20973):

- the "attacking" range of slot 21 as `state − 6 < 9` instead of `< 10`: 1 mismatching call
  each in Weapon2 slot 21 and WeaponShield slot 21;
- slot 18's texture word at `d + 8p + 8` instead of `+ 0xc`: 13 (Weapon1), 7
  (WeaponShield), 10 (Weapon2);
- Weapon2's hand-2 effect block at `+0xa0` instead of `+0x9c`: 4 (Weapon2 slot 21);
- the save writing the element of hand 2 instead of hand 1 in byte 2: 15, 19, 18 (slot 23
  of the three classes).

## 2. Coverage (instructions executed of the body)

Both seeds give the same coverage.

| Function | Address | Executed | Not executed |
|---|---|---|---|
| `creature_drawHeldPart` | `0x117f08` | 84 of 84 | |
| Weapon1 slot 18 | `0x11b198` | 28 of 28 | |
| slot 19 (all three classes) | `0x11b208` | 25 of 26 | padding `nop` `0x11b26c` |
| Weapon1 slot 20 | `0x11b270` | 14 of 14 | |
| slot 21 (Weapon1, WeaponShield) | `0x11b2a8` | 80 of 80 | |
| slot 22 (all three classes) | `0x11b3e8` | 73 of 74 | padding `nop` `0x11b50c` |
| Weapon1 slot 23 | `0x11b510` | 28 of 28 | |
| Weapon1 slot 24 | `0x11b580` | 27 of 28 | padding `nop` `0x11b5ec` |
| WeaponShield slot 18 | `0x11be40` | 63 of 64 | padding `nop` `0x11bf3c` |
| WeaponShield slot 20 | `0x11bf40` | 29 of 30 | padding `nop` `0x11bfb4` |
| WeaponShield slot 23 | `0x11bfb8` | 35 of 36 | padding `nop` `0x11c044` |
| WeaponShield slot 24 | `0x11c048` | 33 of 34 | padding `nop` `0x11c0cc` |
| Weapon2 slot 18 | `0x11b948` | 63 of 64 | padding `nop` `0x11ba44` |
| Weapon2 slot 20 | `0x11ba48` | 29 of 30 | padding `nop` `0x11babc` |
| Weapon2 slot 21 | `0x118058` | 138 of 138 | |
| Weapon2 slot 23 | `0x11bac0` | 44 of 44 | |
| Weapon2 slot 24 | `0x11bb70` | 42 of 42 | |
| Weapon2 slot 8 | `0x3c2238` | 29 of 30 | padding `nop` `0x3c22ac` |
| Weapon2 slot 16 | `0x11b8c8` | 20 of 22 | `nop`s `0x11b8ec` (after the tail jump's delay slot) and `0x11b91c` |

Every basic block of every body was entered.

## 3. The tables

| Slot | Weapon1 `0x50cf40` | WeaponShield `0x50cda0` | Weapon2 `0x50ce70` |
|---|---|---|---|
| 18 draw the carried parts on a parent | `0x11b198` (hand 1) | `0x11be40` (both hands) | `0x11b948` (both hands; the same code as WeaponShield's) |
| 19 draw a given part | `0x11b208` | `0x11b208` | `0x11b208` |
| 20 draw the carried parts at their bones | `0x11b270` (hand 1) | `0x11bf40` (both hands) | `0x11ba48` (both hands; the same code) |
| 21 effect update, model from the definition | `0x11b2a8` (hand 1) | `0x11b2a8` (hand 1 only) | `0x118058` (both hands) |
| 22 effect update, model given | `0x11b3e8` | `0x11b3e8` | `0x11b3e8` |
| 23 save | `0x11b510` (3 bytes) | `0x11bfb8` (4 bytes) | `0x11bac0` (5 bytes) |
| 24 load | `0x11b580` | `0x11c048` | `0x11bb70` |

All `this` adjustments are 0. Slot 25 is null in all three tables; slot 26 is a type-info
getter. (Observed in the tables.)

A WeaponShield runs Weapon1's slot 21, so its hand-2 part (the shield) never gets status
effects. Only Weapon2 has a second descriptor (`+0xe0`) and a second effect block
(`+0x9c`).

## 4. The holder fields these slots touch

| Offset | Width | Meaning | Read by | Written by |
|---|---|---|---|---|
| `+0` | word | the table | 23, 24 (the inner virtual call) | — |
| `+4` | byte | hand bits: bit 0 hand 1, bit 1 hand 2 | 18, 19, 20, 21, 22, 23 | 24 (the whole byte) |
| `+8` | byte | hand-1 part | 18, 20, 21 (not 19, 22), 23 | 24 |
| `+0xc` | ~0x40 bytes | hand-1 effect block | — (address passed to `fx_modelStatusEffects`) | `fx_modelStatusEffects` only (D37) |
| `+0x50` | descriptor | hand-1 damage descriptor | 23 (through slot 16) | 24 (through slot 8) |
| `+0x98` | byte | hand-2 part (WeaponShield, Weapon2) | 18, 20, Weapon2 21, 23 | 24 |
| `+0x9c` | ~0x40 bytes | hand-2 effect block (Weapon2) | — (address passed) | `fx_modelStatusEffects` only |
| `+0xe0` | descriptor | hand-2 damage descriptor (Weapon2) | Weapon2 23 (slot 16) | Weapon2 24 (slot 8) |

The part definition `d` (for a Skeleton the skelcom block `0x5023e0`; for
`creature_drawHeldPart` the creature's word `+0x24`) is read as words `d + 8p + 4` (the
part's model; its byte `+0x13` is the bone, as in `creature_dropHeldPartAsProp`) and
`d + 8p + 0xc` (the word `model_drawPart` takes as its texture argument). *Inferred*: the
definition is a table of 8-byte rows and slot 18 takes the texture from the next row.

Hand tests are on the bits byte only: none of these slots takes a hand argument.

## 5. The bodies

### 5.1 Slot 18: the carried parts on a parent (Executed)

`(h, d, parent, chain)`. For hand 1: bit 0 set, part `p = +8` non-zero, and `d`, `parent`
and `chain` all non-zero (full registers) →
`model_drawPart(word d+8p+4, word d+8p+0xc, 0, parent, chain, −1, −1, 0)`.
WeaponShield and Weapon2 then do the same for hand 2 with bit 1 and part `+0x98`.
No stores, no draws. The −1 constants are `addiu` immediates (`0x11b1e0`, `0x11b1f0` and
their copies).

`Skeleton_draw` `0x2a67c4` calls it with `(skelcom 0x5023e0, the model from creature slot
16, the result of Creature_draw)` (Observed). Other callers (Observed by a scan for calls
at table offset `0x90` on the holder loaded from the creature's `+0x50`; a pattern scan, so
the list may be short): the `_draw` functions of Bubo,
CloudGiant, Clockwork, Creep, Demon, FatCyclops, FemaleDarkElf, MaleDarkElf, Froglock,
Goblin, Gremlin, Horsemen, Marr, Minotaur, Mummy, MummyKing, Ogre, Orc, UndeadKnight,
Ulthork, Warrior, WarWraith and Zek.

### 5.2 Slot 19: a given part (Executed)

`(h, part, tex, parent, chain)`, one body for all three classes. Bit 0 set and the four
arguments non-zero → `model_drawPart(part, tex, 0, parent, chain, −1, −1, 0)`. The holder's
own part is not read. Caller: `Skelight_draw` `0x2a8a64` (at `0x2a8b50`).

### 5.3 Slot 20 and creature_drawHeldPart (Executed)

Slot 20 `(h, c)`: bit 0 → `creature_drawHeldPart(h + 4, part +8, c)`. WeaponShield and
Weapon2 re-read the bits byte, then bit 1 → the same with part `+0x98`.

`creature_drawHeldPart` `0x117f08` `(x, part, c)`; `x` is not read.

1. Nothing for part 0 or `c` = 0 (full registers).
2. `rec` = word `(word c+0x24) + 8·part + 4`. The bone is the signed byte `rec + 0x13`; a
   negative bone draws nothing.
3. `model` = creature slot 16 (table `c+0x48`, `+0x80`/`+0x84`, `this` adjusted).
4. `model_getAttachPoint(scale c+0xdc; model, copy of c+0x10…0x18, s16 facing c+0x38,
   c + 0x114, bone, point out, 0)`.
5. `model` = creature slot 16 again.
6. `model_getAttachWorldMatrix(scale; model, a fresh copy of the position, facing,
   c + 0x114, bone, matrix out)`.
7. `model_draw(rec, rec, 1, point, matrix, c + 0x114, the 64-bit word c+0x220, 0; one stack
   argument 0)`; `rec` is re-read from `c + 0x24`.

Reads: `c + 0x10`–`0x18`, `+0x24`, `+0x38`, `+0x48`, `+0xdc`, `+0x220` (64 bits), the
definition row and the bone byte. No stores outside the stack, no draws. Unlike
`creature_dropHeldPartAsProp`, the facing is not turned by −0x4000, the scale is `+0xdc`
(not 1.0) and the definition is always `c + 0x24`.

Callers of slot 20: only `WeaponObject_slot20` `0x3c1ae8` (a forwarder, §7). No direct call
through a creature's `+0x50` was found.

### 5.4 Slot 21: the per-frame effect update (Executed)

`(h, d, c; f12)`. Weapon1 and WeaponShield, hand 1 only:

1. Bit 0 clear, part `p = +8` zero, `d` zero or `c` zero → return.
2. Object flag 2 at `c + 0xc` (hidden) → return.
3. `isNearView(c + 0x10; 480.0)` is 0 → return. 480.0 is `0x43f00000`, an `lui` immediate
   (`0x11b320`).
4. Byte `c + 0x231` has bit 8 → return.
5. `model` = creature slot 16.
6. `fx_modelStatusEffects(f12, scale c+0xdc; h + 0x50, word d+8p+4, h + 0xc, copy of
   c+0x10…0x18, s16 facing c+0x38, model, c + 0x114, attacking; stack 0, 0)` where
   `attacking` = 1 when the u16 state `c + 0x232` lies in 6–15 (`addiu −6` at `0x11b380`,
   `sltiu 10` at `0x11b3ac`), else 0.

**What it reads**: holder `+4`, `+8`; the definition row word; creature `+0xc`,
`+0x10`–`+0x18`, `+0x231`, `+0x232`, `+0x38`, `+0x48` and its table slot 16, `+0xdc`;
through `isNearView`, `g_cullByCamera` and the camera focus or the player objects
(`ref_creature.Model.is_near_view`). **What it writes**: nothing outside the stack (Executed:
no byte in any slot-21 call of either seed, 748 and 791 calls of the three classes, with
the callees stubbed). **Draws**: none of the shared seed.

Weapon2 slot 21 `0x118058` does hand 1 the same way, then hand 2: bit 1, part `+0x98`, `d`,
`c`, flag 2, `isNearView` asked again, `+0x231`, slot 16, and `fx_modelStatusEffects` with
descriptor `h + 0xe0` and effect block `h + 0x9c`. The constants are at `0x1180d4`
(480.0), `0x118134`/`0x118158` and `0x1181b4`, `0x118214`/`0x118244`.

Caller for a Skeleton: the prologue of `Skeleton_run` (`0x2a68f8`), every tick of an active
Skeleton, with `(skelcom 0x5023e0, c; 0.5)` (`docs/spec/skeleton-run.md`). The `_run`
functions of 23 other classes call it at table offset `0xa8` (scan, as in §5.1): Bubo,
CloudGiant, Clockwork, Creep, Demon, FatCyclops, FemaleDarkElf, MaleDarkElf, Froglock,
Goblin, Gremlin, Horsemen, Marr, Minotaur, Mummy, MummyKing, Ogre, Orc, UndeadKnight,
Ulthork, Warrior, WarWraith and Zek.

### 5.5 Slot 22: the effect update with a given model (Executed)

`(h, m, c; f12)`, one body for all three classes. Bit 0, `m` and `c` non-zero, then steps
2–6 of §5.4 with `m` in place of the definition row word. The part `+8` is not read.
Constants: 480.0 at `0x11b450`; `−6`/`10` at `0x11b4b8`/`0x11b4d8`. Caller: `Skelight_run`
(`0x2a8c38`) with an item-model pointer from `0x3e9ce0` (`docs/spec/arena-monsters.md`).

### 5.6 Slots 23 and 24: save and load (Executed)

The serialized layout, byte by byte:

| Byte | Weapon1 | WeaponShield | Weapon2 | Saved from | Loaded into |
|---|---|---|---|---|---|
| 0 | ✓ | ✓ | ✓ | the bits byte `+4` | `+4` |
| 1 | ✓ | ✓ | ✓ | the hand-1 part `+8` | `+8` |
| 2 | ✓ | ✓ | ✓ | low byte of slot 16 (hand 1): the hand-1 element | slot 8 (hand 1, this byte) |
| 3 | | ✓ | ✓ | the hand-2 part `+0x98` | `+0x98` |
| 4 | | | ✓ | low byte of slot 16 (hand 2): the hand-2 element | slot 8 (hand 2, this byte) |
| result | 3 | 4 | 5 | | |

The result is the number of bytes (pointer difference). Both slot 16 and slot 8 are called
through the holder's own table: for Weapon1 they are `0x11b148` and `0x11aff0`
(`weapon-holder.md` §3.4), for WeaponShield `0x3c25c0` and `0x3c2500`, for Weapon2
`0x11b8c8` and `0x3c2238` (§5.7). Load writes bytes 0, 1 (and 3) before or between the
calls in the table's order: `+4`, `+8`, slot 8 (1), `+0x98`, slot 8 (2).

What a save and load does to the holder:

- **The element is rebuilt, not restored.** The save keeps only the element number
  (`damageDesc_getElement`: 0, 1, 2, 3, 4 or 6). The load hands it to slot 8 as a kind, and
  `creature_buildElementDamage` builds a new entry: a fresh slot-11 value of the kind's Skill
  at the current `g_levelMonsterLevel` and **ONE SHARED DRAW** (`0x404464`) per element of
  kind 1–6. Element 0 only frees the four effect slots (no draw).
- The round trip keeps the element: 1 → id `0x15` → 1, 2 → `0x16`, 3 → `0x17`, 4 → `0x18`,
  6 → `0x1f` (`ref_holder_slots.ROUND_TRIP`). Kind 5 (id `0x26`) is reported as 0, so a
  kind-5 element is **lost**: the load frees the descriptor.
- Not saved: the descriptor's values (re-rolled), its halfwords `+0x60`–`+0x6e` (slots 9
  and 10), its other effect slots, and the effect blocks.

*Unknown*: who calls slots 23 and 24. The only calls found are the forwarders
`WeaponObject_slot23` `0x3c1b90` and `WeaponObject_slot24` `0x3c1bd8` (§7); no caller of
those was found. `Skeleton_saveState` `0x2a7508` and `Skeleton_loadState` `0x2a75d4` do not
use them (Observed): they save the weapon-kind word `+0x3d0` and the two parts as 32-bit
words from slot 15 (hands 1 and 2), and load them back through slot 1. So a Skeleton's
element is not part of its saved state.

### 5.7 Weapon2 slots 8 and 16 (Executed)

- Slot 8 `0x3c2238` `(h, hand, kind)`: kind & 0xff; hand 0 or 1 (`sltiu 2`) →
  `creature_buildElementDamage(h + 4, h + 0x50, kind)`; then hand 0 or 2 → the same on
  `h + 0xe0`. Hand 0 builds both, with two shared draws.
- Slot 16 `0x11b8c8` `(h, hand)`: hand 2 → a tail jump to `damageDesc_getElement(h + 4,
  h + 0xe0)`; hand 1 → the same on `h + 0x50` (a linked call); else 0.

## 6. Can slot 21 change the simulation?

- **The body itself** (Executed, §5.4): no store outside the stack, no shared draw. Its
  only effects are its calls.
- **`isNearView`** is a pure query (executed in `ref_creature`). With `g_cullByCamera` set
  it reads the camera focus, which is per machine during a net cutscene (FINDINGS D6). Its
  answer only decides whether `fx_modelStatusEffects` is called.
- **The creature's slot 16** returns the model. For a Skeleton it is
  `Creature_default_slot16` `0x3c2738` (Observed: word `+0xc` of the record at `c + 0x24`,
  no store); 67 classes share it.
- **`fx_modelStatusEffects`** (not executed; read in `docs/issues/rescan.md` §6, FINDINGS
  D37): writes only the effect block it is handed (`h + 0xc`, or `h + 0x9c`) and
  presentation tables (particles, glows, trails, beams); draws the **cosmetic** seed
  `0x404460` (Observed: its `addiu …, 0x4460` sites, e.g. `0x1f7178`, `0x1f7ec0`), never the
  shared one; no allocation, no damage call, no virtual call. No holder slot loads from
  the effect blocks `+0xc`–`+0x4b` or `+0x9c`–`+0xdb`; slots 21 and 22 only pass their
  addresses (Observed in slots 18–24 here and slots 1–17 in `weapon-holder.md`).
- Two indirect routes exist, neither on a Skeleton placement: the beam table it fills is
  read by `CloudGiant_run` (`beam_create`'s result, docs/monsters-2.md M1, D28), and the
  cosmetic seed reaches game state only through D27/D30 (piston traps, path-following
  Critters).

So for a Skeleton, slot 21 is presentation: running it or not leaves every simulation
byte and the shared seed as they were. (Executed for the body; Observed for the callee.)

## 7. The WeaponObject forwarder

A creature carries a `WeaponObject` (type-info `0x3c1608`, base `WeaponInterface`, table
`0x50d010`) at `+0x4c`; its word `+4` (the creature's `+0x50`) is the holder, set by its
slot 25 `0x3c1658`. Its slots 1–24 (`0x3c1660`–`0x3c1bd8`) forward the same slot to the
holder when the pointer is set (`symbols/runtime.tsv`). The run and draw functions call the
holder at `+0x50` directly. Not executed.

## 8. Corrections and sharpenings

- `symbols/creatures.tsv`: `Weapon1_slot18`–`24`, `WeaponShield_slot18/20/23/24`,
  `Weapon2_draw`, `Weapon2_slot20/23/24` and `Weapon2_update` can carry §5; the "body not
  read" notes are out of date. `creature_drawHeldPart`'s caller note is right.
- `docs/issues/rescan.md` §6 says "three-byte save and load (23, 24)": three bytes for
  Weapon1, four for WeaponShield, five for Weapon2; and the load **makes a shared draw**
  per element (D37 is unaffected: the load does not read the effect block).
- `docs/spec/weapon-holder.md` §6: slots 18–24 of the three classes and Weapon2's slots 8
  and 16 are now executed.
- `fx_modelStatusEffects`'s note "cosmetic seed" (`symbols/gameplay.tsv`) is right: the
  `0x4460` sites are the cosmetic generator, not `g_randSeed`.

## 9. Not executed

- `fx_modelStatusEffects` `0x1f6ac8` (17 KB), `model_drawPart`, `model_draw`,
  `model_getAttachPoint`, `model_getAttachWorldMatrix`: recording stubs here.
- `isNearView` and the creature's slot 16: stubs here (`isNearView` is executed in
  `ref_creature`).
- Weapon2 slots 1–7, 9–15 and 17 (`0x11b5f0`, `0x3c1fc8`–`0x3c21d0`, `0x11b668`–`0x11b898`,
  `0x11b920`).
- The `WeaponObject` forwarders `0x3c1660`–`0x3c1bd8`, and the callers of slots 23 and 24.
