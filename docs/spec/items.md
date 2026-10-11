# Items — implementation specification

How `SLUS_209.73` (US v2.00) turns an item description into an item, generates random items
and loot, and computes an item's name, value, weight and statistics. Written for someone who
has to reproduce it: every draw from the shared random generator is listed in order, because
in a net game every machine must make the same draws.

The rules below are implemented in `tools/ref_items.py` (the reference model) and were
**executed against the original machine code** by `tools/difftest_items.py`, which runs the
game's own functions in `tools/ee_emu.py` and compares results. Section 12 says exactly what
was compared and on how many inputs; at the largest sample every property passed with no
mismatch. That is stronger than reading, but it is still not a running game: one function at
a time, on state the test builds, with the callees named in section 12 replaced. (The
project has a running game since — the Play! emulator, which is not a PlayStation 2 and not PCSX2;
`FINDINGS.md`, "Run on the live game" (rows V1–V23) and `docs/issues/live-rig.md` — but nothing in this
document was checked on it.)

Marks: **[O]** Observed at the address given, **[I]** Inferred, **[U]** Unknown. A rule
without a mark is [O] in the function named in its heading *and* covered by the test of
section 12. *(dec)* = read from the decompile only. Earlier documents: `docs/startup.md`
(the item module), `docs/data-tables.md` §1–2 (tables), `docs/issues/kill-loot-xp.md` (who
calls the loot function). Section 13 lists what in them needs correcting.

No table contents are reproduced here. `tools/ref_items.py` reads them from your own
executable; `tools/dump_tables.py` prints them.

## 0. Conventions

| | |
|---|---|
| Shared generator | `g_randSeed` 0x404464. `draw()`: `seed = seed × 0x19660D + 0x3C6EF35F (mod 2³²)`, result `seed >> 16` (0…65535). The code is inlined at every use |
| Floats | single precision, given as bit patterns; the decimal in brackets is only a reading aid. Every `+ − × /` is one operation, in the order written. `f(i)` = integer to float, `int(x)` = float to integer (toward zero, saturating). The console truncates every result and has no infinities or NaNs (section 11) |
| `get(code, k)` | value `k` (0, 1 or 2) of the **first** modifier slot whose code equals `code`, else 0. The original inlines this lookup everywhere; it never looks at "the slot it is processing" |
| Integers | 32-bit two's complement, wrapping; `s16(x)` keeps the low 16 bits as a signed number |
| `contains(name, A)` | the C library's `strstr(name, string at address A) ≠ 0`. The strings are name stems; read them from the executable at the address |

Globals the item code reads: `g_numPlayers` 0x4d8ae0; the class id of each player record
(`g_players[i]` 0x4d8af0 + i × 0x4c30, +0x50); `g_difficultyIdx` 0x4f719c (1…5); `g_pvpModeA`
0x4f711c; `g_pvpModeB` 0x4f7120; `g_levelMonsterLevel` 0x4f714c (float, called `L` below).

## 1. Tables

Layouts are in `docs/data-tables.md` §1 and were used unchanged: definitions
`g_itemDefs` 0x3f7650 and presets `g_itemPresets` 0x3ea550 (rows of 0x40, ended by a null
name), prefixes 0x400e50 (0x28), suffixes 0x4019e0 (0x14), drop quality rows 0x3e9c18
(12 × 3 floats), weapon value multipliers 0x3e9cb0 (float per subtype), potion name lists
0x402708 (mana) and 0x402730 (healing). Field names used below: `level` +0x04, `weight` +0x08,
`count` +0x0c, `dmgMin` +0x0e, `dmgMax` +0x10, `price` +0x14, `armor` +0x18, `attack` +0x1a,
`slot` +0x1c, `category` +0x1d, `subtype` +0x1e, `dmgBits` +0x20, `flags` +0x28, `picture`
+0x30, `modelRow` +0x34. Prefix: `level` +4, `text[category]` +0x0c, `mask` +0x18 (u64),
`dmgMask` +0x20. Suffix: `level` +4, `text[category]` +8.

The affix text arrays are indexed with the definition's category byte without a range check
(`text[category]` is the pointer at `row + 0x0c + 4 × category`, respectively `+ 8`). [O]

Definition / item flag bits met in this document (bit numbers of the u64):

| Bit | Mask | Use | |
|---|---|---|---|
| 8 | 0x100 | stackable (`inventory_giveItem`) | `docs/issues/kill-loot-xp.md` |
| 9 | 0x200 | name is never decorated | §10 |
| 11–15 | 0xf800 | definition: number of visual variants; item: chosen variant | §3 |
| 16 | 0x10000 | never picked by the random generators | §8 |
| 19 | 0x80000 | cloth armour | §7, §8 |
| 35 | 0x800000000 | reagent group | §8.4 |
| 36 | 0x1000000000 | model row = `modelRow` + variant; also lifts the class-4 weapon rule | §7 |
| 40 | 0x10000000000 | the shop does not stock it | [O] *(dec)* `shop_openOrStock` 0x1c7af8 |
| 41 | 0x20000000000 | cannot be equipped (reason 9) | §7 |
| 42–44 | 0x1c0000000000 | value × 0.004 | §6 |
| 43 | 0x80000000000 | class-4 weapon rule: decided by skill 0x5c | §7 |
| 45 | 0x200000000000 | figurine group | §8.4 |

## 2. The item record (0x48 bytes)

| Offset | Type | Content |
|---|---|---|
| +0x00 | ptr | definition row (base or preset table) |
| +0x04 | s16 | count |
| +0x06 | 2 bytes | **never written** by the code that builds a record |
| +0x08 | u64 | flags: the definition's, with bits 11–15 replaced by the variant |
| +0x10, +0x18 | s16[4] each | zero |
| +0x20, +0x21 | u8, u8 | prefix row, suffix row; 0xff = none |
| +0x22 | s16 | **never written** at creation; `inventory_giveItem` later stores the bag index here (`docs/issues/kill-loot-xp.md`), `item_copyMutableFields` 0x107ca8 zeroes it |
| +0x24 | 4 × {s16 code, s16 v0, v1, v2} | modifier slots; code −1 = empty. The three values of an empty slot are **never written** |
| +0x44 | 4 bytes | padding, **never written** |

Every function that builds a record starts with the same inlined constructor: the four codes
become −1, prefix and suffix 0xff, the two arrays zero — and nothing else (parser
0x1069f8–0x106a48). The parser builds its record in its own stack frame and copies all 0x48
bytes to the caller's (0x106a58–0x106a94), so the unwritten bytes of a new item are whatever
lay in the parser's frame. The test confirms this byte for byte (it fills that part of the
stack with random bytes before each call and finds them in the record). In a generator the
frame is reused between candidates, and there the bytes at +0x22 and +0x44 were seen to hold
pieces of floating-point temporaries of an earlier candidate's value computation, and +0x06
whatever the stack held before the generator was called. [O] under emulation.

Consequence: two records of "the same item" are not byte-equal in general. Compare fields,
not bytes — except where the original compares bytes: `item_sameIdentityFields` 0x108924
(definition, flags, and the **32-bit word at +0x20**, which includes +0x22). See §13, row I1.

Helpers (all tested): `item_copyMutableFields(dst, src)` copies count, flags, prefix, suffix
and the 32 bytes of the four slots, zeroes +0x10…+0x1f and +0x22, leaves the definition, +0x06
and +0x44 of `dst` alone. `item_encodeDefinitionIndex` 0x107ea4 replaces the pointer by
`(pointer − 0x3f7650) >> 6` (arithmetic, so preset rows are negative); 0x107ec0 is the
inverse. `item_getResourceIndex` 0x1083f8 = `modelRow`, plus the variant when flag bit 36 is
set.

## 3. The descriptor parser — `item_parseDescriptor(text, out, variant, usePresets)` 0x1069b8

```
copy text into a 208-byte stack buffer            # no length check: 208 bytes or more overrun it
record = new record (section 2)
cut the buffer at its first '+';  head = the part before it
definition = usePresets ? first preset row whose name equals the WHOLE text (not cut)
                        : first base row whose name equals head
             no such row: row 0 of that table
record.definition = definition; record.count = definition.count; record.flags = definition.flags
for each further piece (the text is cut at every '+', so pieces may be empty):
    three integers a, b, c = 0
    for each of the 43 formats, in the order of the table below:
        r = sscanf(piece, format, &a, &b, &c)
        if r == 0: continue                          # any non-zero result is a match, −1 included
        "mesh" format:  variant = a
        otherwise:      i = first slot that is empty or already holds this code
                        if there is one: slot[i] = {code, s16(a), s16(b), s16(c)}
                                         (b, c forced to 0 when the format has fewer conversions)
                        if there is none: the piece is dropped
        stop trying formats
if variant == −1: item_randomizeVariant(record)
else:             record.flags = sign-extended 32-bit (variant << 11)  |  (record.flags & ~0xf800)
```

`item_randomizeVariant` 0x1046e0: `n` = bits 11–15 of the **definition's** flags; if `n > 0`,
`variant = draw() mod n`, else no draw and variant 0; then `flags = (variant << 11) |
(flags & ~0xf800)`. So a parse with variant −1 costs exactly one draw when the definition has
variants and none otherwise.

Things that follow from the code and that the test exercises:

- A fixed variant is **not** masked to five bits: variant 33 sets bit 16 as well. [O] 0x107c58
- A "mesh" piece with value −1 asks for a random variant, like the argument.
- The preset lookup compares the whole text, so a preset is found only by its exact name;
  its modifiers are then parsed from the same text like any other descriptor.

### 3.1 The scanner

Each format is a lower-case word immediately followed by `%d`, `%d-%d`, `%d,%d` or
`%d,%d-%d`. The library's `sscanf` 0x3b7f88 behaves as follows for them (tested directly,
section 12):

- Literal characters must match exactly (case matters). A mismatch ends the scan and returns
  the number of values converted so far.
- **If the text ends where a literal or a number is expected and nothing has been converted
  yet, the result is −1**, which the parser takes as a match. So an empty piece, a piece that
  is a prefix of a format's word, and a bare word without a number all match — the first
  format, in table order, whose word starts with the piece — and store that code with value
  0. Example: a descriptor ending in `+` gains modifier 0x23 with value 0.
- `%d` skips white space, takes an optional sign and decimal digits. A sign with no digit is a
  mismatch (result so far, 0 if first), not an end-of-text.
- The digits are converted with saturation to a signed 64-bit `long`, then cut to 32 bits, and
  the parser cuts to 16. `65537` stores 1.
- Text after the last conversion is ignored.

Four pieces in the executable's own preset table are matched by the end-of-text rule: three
empty ones (giving modifier 0x23 with value 0) and one bare word (its own code, value 0). [O] tool run over
1,679 pieces of the preset, prefix and suffix texts; every other piece matches with all its
values, and no preset has more than four distinct modifiers.

### 3.2 The 43 formats, in the order tried (0x106b90–0x107bd0)

The words are in `docs/startup.md` ("Modifier types") and are printed by
`dump_tables.py --table item_tokens`; here are order, format string address, code stored and
shape. `1` = `%d`, `r` = `%d-%d`, `cv` = `%d,%d`, `cr` = `%d,%d-%d`.

| # | Address | Code | | # | Address | Code | | # | Address | Code | |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0x520190 | 0x23 | 1 | 15 | 0x5202b0 | 0x11 | 1 | 30 | 0x5203d0 | 0x03 | 1 |
| 1 | 0x5201a8 | 0x1e | 1 | 16 | 0x5202c8 | 0x12 | 1 | 31 | 0x5203e0 | 0x04 | 1 |
| 2 | 0x5201c0 | 0x1d | 1 | 17 | 0x5202e0 | 0x13 | 1 | 32 | 0x5203f0 | 0x21 | cv |
| 3 | 0x5201d0 | 0x1c | 1 | 18 | 0x5202f0 | 0x0d | 1 | 33 | 0x520408 | 0x1f | cr |
| 4 | 0x5201e0 | 0x1b | 1 | 19 | 0x520300 | 0x0b | 1 | 34 | 0x520420 | 0x20 | cr |
| 5 | 0x5201f0 | 0x1a | 1 | 20 | 0x520318 | 0x0c | 1 | 35 | 0x520438 | 0x22 | cr |
| 6 | 0x520200 | 0x19 | r | 21 | 0x520330 | 0x05 | 1 | 36 | 0x520450 | 0x24 | 1 |
| 7 | 0x520210 | 0x15 | r | 22 | 0x520340 | 0x06 | 1 | 37 | 0x520468 | 0x25 | 1 |
| 8 | 0x520220 | 0x16 | r | 23 | 0x520350 | 0x07 | 1 | 38 | 0x520478 | 0x27 | 1 |
| 9 | 0x520230 | 0x18 | r | 24 | 0x520360 | 0x08 | 1 | 39 | 0x520488 | 0x28 | 1 |
| 10 | 0x520248 | 0x17 | r | 25 | 0x520378 | 0x09 | 1 | 40 | 0x5204a0 | 0x2a | 1 |
| 11 | 0x520260 | 0x14 | 1 | 26 | 0x520390 | 0x0a | 1 | 41 | 0x5204b0 | mesh | 1 |
| 12 | 0x520270 | 0x0e | 1 | 27 | 0x5203a0 | 0x00 | 1 | 42 | 0x5204b8 | 0x26 | r |
| 13 | 0x520280 | 0x0f | 1 | 28 | 0x5203b0 | 0x01 | 1 | | | | |
| 14 | 0x520298 | 0x10 | 1 | 29 | 0x5203c0 | 0x02 | 1 | | | | |

## 4. Statistics

`pct = 0x3c23d70a` [0.01]. Because 0.01 is not exact and results are truncated, a percentage
whose exact result is a whole number usually comes out one short: +50 % of 12 armour is 17.

**Weight** — `item_getWeight` 0x103e08, returns a float:

```
w = def.weight;  limit = (category == 1) ? 5.0 : 15.0
if limit < w:  w = w − (w − limit) × 0x3f44ec4f [0.7692308]
w = w × f(count)
return f(get(0x24,0)) × pct × w + w
```

**Armour** — `item_getArmorValue` 0x103ec8: `p = get(0x0d,0)`; `p == 0` → `def.armor`, else
`def.armor + int(f(def.armor) × (f(p) × pct))`.

**Attack rating** — `item_getModifiedField1a` 0x103f88: `r = f(def.attack)`; if
`p = get(0x23,0)` is not 0, `r = f(p) × pct × r + r`; result `int(r)`.

**Damage range** — `item_getDamageRange(item, &min, &max, withElemental)` 0x104100:

```
lo = f(def.dmgMin);  hi = f(def.dmgMax)
p = get(0x23,0);  if p != 0:  k = f(p) × pct + 1.0;  hi = hi × k;  lo = lo × k
if withElemental:
    for code in 0x15, 0x16, 0x18, 0x17, 0x26 (this order):
        if get(code,0) != 0:  lo = lo + f(get(code,0));  hi = hi + f(get(code,1))
min = int(f(int(lo × 1.0 + 0.5)));  max = int(f(int(hi × 1.0 + 0.5)))
```

(The 1.0 is the return value of `item_getUnitMultiplier` 0x1046b4.)

## 5. Value — `item_getValue` 0x1024a8

```
if def.price >= 1:  return def.price × count                      # 32-bit product

base = 0.0
if category == 0 and subtype != 5:
    (mn, mx) = item_getDamageRange(item, withElemental = 0)
    lo = f(mn) × 0x3f199913 [0.599992];  hi = f(mx) × 0x3f199913
    for each of the four slots, c = its code:                      # values come from get(), not from the slot
        0x13:  hi = hi × 0x3f666666 [0.9];  lo = lo × 0x3f666666
        0x14:  s = f(get(c,0)) × 0x3d3851eb [0.045];  lo = s × lo + lo;  hi = s × hi + hi
        0x15, 0x16, 0x17, 0x18, 0x26, only if get(c,2) <= 0:
               lo = lo + f(get(c,0)) × K;  hi = hi + f(get(c,1)) × K
               K = 0x3f028fb0, 0x3f051ec9, 0x3f028f4b, 0x3effffde, 0x3f000000 in that order
        0x19:  lo = lo + f(get(c,0)) × 0x3e0a3d70 [0.135];  hi = hi + f(get(c,1)) × 0x3e0a3d70
        0x1b:  lo = lo + (f(get(c,0)) × 0x3fa2d0aa [1.272]) × (lo × pct)
               hi = hi + (f(get(c,1)) × 0x3fa2d0aa) × (hi × pct)
        0x1d:  q = f(get(c,0)) × pct;  lo = lo + ((q + q) × lo) × 0x3fd997bb [1.6999]
               q = f(get(c,1)) × pct;  hi = hi + ((q + q) × hi) × 0x3fd997bb
        0x1f, 0x20, 0x22:  q = f(get(c,0)) × pct
               lo = lo + (f(get(c,1)) × q) × K;  hi = hi + (f(get(c,2)) × q) × K
               K = 0x3f70621b, 0x3f743914, 0x3f826e6d
        0x21:  q = f(get(c,0)) × pct;  t = (f(get(c,1)) × q) × 0x42540011 [53.000065]
               lo = lo + t;  hi = hi + t
        other codes: nothing
    m = float at 0x3e9cb0 + 4 × subtype
    hi = hi × m;  lo = lo × m
    base = (lo + hi) × 0.5 − (hi − lo) × 0x3dcccccc [0.1]
if category == 1:
    base = (f(item_getArmorValue(item)) × 0x3f199999 [0.6]) × 0x3f8ccc5f [1.0999869]
    if slot == 3:  base = base × 0.5
if category == 2:  base = 5.0

total = powf(base, 0x3ff99999 [1.95])
for each of the four slots, c = its code:
    if c == 0x0d and category == 1:  c = 0x1a        # the armour case jumps into the code-0x1a case
    c in the exponent table:  total = total + powf(f(get(c,0)), exponent[c])
    c == 0x25:                total = (f(get(0x25,0)) × pct) × total + total
total = total × 40.0
if contains(def.name, 0x520070) or def.flags & 0x1c0000000000:  total = total × 0x3b83126e [0.004]
if category == 2 and slot in {5, 6, 7, 14, 15}:                   total = total × 0x41002899 [8.009912]
return int(total + 0.5) × count                                   # 32-bit product
```

Exponent table (the second argument of `powf`, bit patterns):

| Code | Exponent | Code | Exponent | Code | Exponent |
|---|---|---|---|---|---|
| 0x00 | 0x3fc03e18 | 0x06 | 0x3fd2d056 | 0x0c | 0x3fdba3d2 |
| 0x01 | 0x3fcccaab | 0x07 | 0x3ff998b7 | 0x0d | 0x3f4105f2 |
| 0x02 | 0x3fb8d299 | 0x08 | 0x3ff623d9 | 0x1a | 0x3fff9d4d |
| 0x03 | 0x3fb3322f | 0x09 | 0x3ffccc57 | 0x1c | 0x4009ba3c |
| 0x04 | 0x3faf5b9a | 0x0a | 0x40001027 | 0x1e | 0x3ffdd263 |
| 0x05 | 0x3fd31105 | 0x0b | 0x3fdb8383 | 0x2a | 0x402ccd29 |

Notes:

- `powf` is the C library's (0x3a7930 through the wrapper 0x3a5ac8) and has to be reproduced
  operation for operation to get the same value; `ref_items.powf` is such a transcription.
- A **negative** first argument (a negative modifier value on one of the exponent-table codes)
  makes `powf` compute 0/0, which on this FPU is the largest float; the value then saturates
  at 0x7fffffff × count. [O] under emulation; what a console returns for 0/0 is the same rule
  in `ee_emu`, not measured.
- For armour an `armorbonus` slot adds the code-0x1a term instead of nothing: with no 0x1a
  slot that is `powf(0, …) = 0`; with one, its term is counted twice.
- 438 of the 607 base definitions have no fixed price and use the formula. [O] tool run

**Level requirement from a value** (the block at 0x104a98, 0x105654, 0x1059f0):

```
e = value − 1200 (32-bit);  if e < 0: e = 0
lvl = int(powf(f(e / 5000), 0x3f28f5c2 [0.66])) × 2 + 1;   if lvl >= 81: lvl = 80
```

It is stored as modifier 0x0e in the first slot that is empty or already 0x0e (dropped when all
four slots hold other codes), and only when `contains(def.name, 0x520180)` is false.

## 6. The requirement test — `inventory_checkEquipAllowed(slot, item)` 0x1c4948

Outside the item module (ui area), but it is the only reader of the `required…` modifiers.
It returns 0 when the player may equip the item, else a reason. `rec` = `g_players[slot]`;
`rank(id)` = `player_getSkillRank` 0x1bf330 (pairs {s16 id, s16 rank} from `rec` +0x4b08,
ended by id −1).

```
r = 0;  cls = rec.class (+0x50);  st = def.subtype;  bits = def.dmgBits
if category == 1:
    if item.flags & 0x80000:                        r = (cls != 4)          # cloth: class 4 only
    else if not contains(def.name, 0x5385e8) and cls == 4:  r = 1           # class 4: cloth and that stem only
else if cls == 1:  r = st in {3, 4} or bits in {8, 4}
else if cls == 3:  r = st in {1, 2, 3}
else if cls == 4:  r = st in {1, 2, 4} or bits in {8, 4}
                   if item.flags & 0x1000000000:  r = 0
                   if (st == 0 or item.flags & 0x80000000000) and rank(0x5c) != 0:  r = 0
else if cls == 6:  r = st in {1, 4}
if (s8) rec[+0x58] < get(0x0e,0):  r = 2            # level
if rec[+0x90] < get(0x0f,0):       r = 3            # strength
if rec[+0x94] < get(0x10,0):       r = 4            # intelligence
if rec[+0x98] < get(0x11,0):       r = 5            # dexterity
if rec[+0x9c] < get(0x12,0):       r = 6            # stamina
if rank(0x3c) < get(0x27,0):       r = 7
if rank(0x3d) < get(0x28,0):       r = 8
if item.flags & 0x20000000000:     r = 9
if get(0x13,0) != 0 and cls != get(0x13,0) − 1:  r = 1
return r
```

All tests are made; a later one replaces the reason of an earlier one. `requiredclass` holds
the class index **plus one**. The level compared is the acknowledged level +0x58, not +0x59.
Callers: the equip handler 0x1c27c0 and the item list 0x1cc7e0 (not read). [O]

## 7. Generators

Common pieces:

- `clothFraction = f(number of players i < g_numPlayers with class 4) / f(g_numPlayers)`.
- "level cap" `cap`: an integer argument; a row qualifies when `row.level <= cap`.
- Each candidate is priced with §5 and receives the level requirement of §5.
- "keep the best": `best` starts at −1; a candidate replaces the result when
  `best <= value` **and** `value <= budget` (so of equal values the later one wins), and then
  `best = value`. At the end, if `best < 0` the function returns 0 and the output is whatever
  it was; otherwise `item_randomizeVariant(output)` (one more draw if the definition has
  variants) and return 1.
- Every `parse` below is `item_parseDescriptor(text, candidate, −1, …)` and therefore draws
  once when the definition has variants.

### 7.1 Preset items — `item_generateFromSpecialTable(out, budget, category, cap)` 0x104758

```
excludeCloth = false
if category == 1:  excludeCloth = int(clothFraction × 65536.0) < draw() mod 0xffff          # draw 1
eligible(row): not flags & 0x10000, (category == −1 or row.category == category),
               row.level <= cap, not flags & 0x800000000,
               not (excludeCloth and row.category == 1 and flags & 0x80000)
n = number of eligible preset rows;  if n == 0: return 0
repeat 10 times:
    p = draw() mod n
    row = eligible row number max(p − 1, 0)      # counting from 0
    candidate = parse(row.name, usePresets = 1)
    price it, attach the level requirement, keep the best
```

The pick is off by one in the original: the countdown stops at the first eligible row for a
draw of 0 **and** of 1, so the first eligible row is twice as likely as the others and the
last one is never picked. [O] 0x104a3c–0x104a44

### 7.2 Random equipment — `item_generateWithAffixes(out, budget, category, wantSuffix, cap)` 0x104ca4

```
excludeCloth = preferCloth = false
if category == 1:
    if int(clothFraction × 65536.0) < draw() mod 0xffff:  excludeCloth = true              # draw
    else if 0.0 < clothFraction:  preferCloth = (draw() mod 0xffff) <= 0xbfff              # draw
weaponGroup = armourGroup = −1
if category == 0:
    x = f(draw()) × 2⁻¹⁶                                                                   # draw
    weaponGroup = 0 if x < 0x3d8f5c28 [0.07], else 1 if x < 0x3df5c28f [0.12], else 2
    if weaponGroup == 0:  budget = budget / 5
if category == 1:
    x = f(draw()) × 2⁻¹⁶                                                                   # draw
    armourGroup = first i of 0…4 with x < {0x3e23d70a, 0x3ea3d70a, 0x3ef5c28f, 0x3f23d70a, 0x3f4ccccc}[i], else 5
eligible(def): not flags & 0x10000, (category == −1 or def.category == category), def.level <= cap,
               not flags & 0x800000000, not flags & 0x200000000000,
               not (preferCloth and def.category == 1 and not flags & 0x80000 and not contains(def.name, 0x520188)),
               not (excludeCloth and def.category == 1 and flags & 0x80000),
               def.category != 0 or weaponGroupOf(def) == weaponGroup,
               def.category != 1 or armourGroupOf(def) == armourGroup
n = number of eligible base rows;  if n == 0: return 0
if wantSuffix == −1:
    if category == 2: wantSuffix = 1
    else if draw() < 0x1964: wantSuffix = 1                                                # draw (9.9 %)
N = number of prefix rows with level <= cap
tries = 15 if category == 0 else 10
for t = 0 … tries − 1:
    def = eligible row number (draw() mod n)                                               # draw
    s = draw() mod (number of suffix rows);  while cap < suffix[s].level:  s = draw() mod …   # 1 or more draws
    sfx = wantSuffix > 0 and suffix[s].text[def.category] != null and not contains(def.name, 0x520180)
    if category == 2:
        candidate = parse(def.name + (sfx ? suffix[s].text[def.category] : suffix[0].text[def.category]))
        candidate.prefix = 0xff;  candidate.suffix = sfx ? s : 0
        price it, attach the level requirement, keep the best
    else for p = 0 … N − 1:                       # the FIRST N rows, not the N fitting rows
        if cap < prefix[p].level: continue
        text = def.name;  pfx = false
        if t > 0:
            pfx = ((def.flags & prefix[p].mask) != 0 or prefix[p].mask == 0) and prefix[p].text[def.category] != null
            if pfx: text += prefix[p].text[def.category]
            if sfx: text += suffix[s].text[def.category]
        candidate = parse(text)
        if t > 0:
            if pfx: candidate.prefix = p
            if prefix[p].dmgMask != 0:  candidate.prefix = (def.dmgBits & prefix[p].dmgMask) ? p : 0xff
            if sfx: candidate.suffix = s
        price it, attach the level requirement, keep the best
```

`weaponGroupOf` (`item_classifyCategory0` 0x104c04): 0 for subtype 6; 1 for subtype 3 with
damage bit 8; else 2. `armourGroupOf` (`item_classifyCategory1` 0x104c48) by slot:
11 → 0, 4 → 1, 9 → 2, 12 → 3, 3 → 4, other → 5.

What an implementer would not guess:

- Try 0 parses the plain name once **per fitting prefix row**, so for a definition with
  variants it makes that many draws for candidates that differ only in the variant.
- The prefix loop covers the first `N` rows. The prefix table is not sorted by level, so for
  caps 1 to 18 between 1 and 10 fitting prefixes lie beyond row `N` and are never tried
  (cap 1: 31 fit, 10 of them out of reach). From cap 19 on none is missed. [O] tool run
- A prefix with a damage-type mask sets or clears the prefix **index** independently of
  whether its modifier text was appended: an item can carry the prefix's name without its
  modifier, or the modifier without the name.
- A category-2 item always carries a suffix index: 0 (the first suffix row) when none was
  chosen, together with that row's text.
- If no suffix row fits the cap the redraw loop never ends. The smallest suffix level in this
  build is 1 and no caller passes less. [O] table, [I] callers
- With `category == −1` both groups stay −1, so no weapon or armour row qualifies.

### 7.3 `item_appendGeneratedUnique(list, budget, unused, category)` 0x107d54 (shop restock)

Up to two calls of §7.2 with `wantSuffix = −1`, `cap = 1`. After each call the buffer is
compared with every list entry (definition non-null and equal, flags equal); if none matches,
`{definition, count, flags}` are appended (count at list +0x1200) and the function returns.
**The generator's return value is not looked at**: when a call produced nothing, the buffer
still holds the item of the previous call, or, on the first call, unwritten stack. [O]
0x107df4–0x107e80. The model covers the first case and refuses the second.

### 7.4 Reagents and figurines — 0x106214, 0x106658

`floor` = 0x11, 0x1b, 0x20, 0x26 for difficulty 2, 3, 4, 5, else −1. `cap` is taken as a signed
16-bit value.

- `item_generateFlag35Entry(out, cap, picture)`: rows with category 2, flag bit 35, and
  `floor <= level <= cap`; when `picture` is null additionally not flag 0x10000, otherwise
  `strcmp(def.picture, picture) == 0` (and flag 0x10000 is **not** tested).
- `item_generateFlag45Entry(out, cap)`: not flag 0x10000, category 2, flag bit 45,
  `floor <= level <= cap`.

Both: no qualifying row → return 0 with no draw. Otherwise row number `draw() mod n`,
`parse(name)`, `item_randomizeVariant`, return 1 — one draw plus one or two more for a
definition with variants.

### 7.5 Consumables — `item_generateConsumable(out)` 0x108590

```
d = min(g_difficultyIdx, 3);  (a, b) = g_pvpModeB ? (0x7fff, 0x10000) : (30000, 60000)
r = draw()
if r >= b:  parse(string at 0x52b798);  return
list = (r < a) ? 0x402708 : 0x402730
x = (f(draw()) × 2⁻¹⁶) × 0x3e4ccccc [0.2] + L × 0x3da3d70a [0.08]
i = 11 if x <= 1.0, 10 if x <= 2.0, else 9
parse(name whose pointer is at list + 4 × (i − 3 × d))
```

### 7.6 The loader's draws — `item_loadResources` 0x108434

Besides resolving model files it parses every base definition with variant −1 and throws the
result away: one draw per definition with variants, 223 in this build. [O], tested with the
resource lookup replaced.

## 8. Loot — `loot_generateDrops` 0x100d54

Arguments: floats `zOffset`, `throwSpeed`, `goldScale`, `goldChance`, `qualityRow`,
`itemChance`; then position pointer, `angle`, `reagentFilter` (picture name or null),
`forcePreset`. Who passes what: `docs/data-tables.md` §2 and `docs/issues/kill-loot-xp.md`.

```
if g_numPlayers >= 2:
    itemChance = itemChance + itemChance
    goldChance = (float)((double)goldChance × 1.5)
    goldScale  = (float)((double)goldScale × double at 0x520048 [2.4])      # see section 11
itemChance = itemChance × 0.5;  if g_pvpModeB: itemChance = 0.25

q = qualityRow clamped to 0.0 … 9.0;  i = int(q);  u = q − f(i);  k = 1.0 − u
x = f(draw()) × 2⁻¹⁶                                                        # draw 1
poor   = row[i].a × k + row[i+1].a × u
normal = row[i].b × k + row[i+1].b × u
quality = 1.0;  if x < poor: quality = 0.5;  if poor + normal < x: quality = 3.0

r = draw()                                                                  # draw 2
rolls = 1 if r <= 60999, 2 if r <= 63999, else 3
goldScale = goldScale × levelFactor04;  if g_pvpModeA: goldChance = 0.0
repeat rolls times:
    if f(draw()) < goldChance × 65536.0:                                    # one draw per roll …
        amount = int((f(draw() mod 40 + 40) × goldScale) × 0x3d0f5c28 [0.035])   # … and one more on success
        loot_spawnGold(position, amount)

c = g_pvpModeB ? f(g_numPlayers − 1) × 0x3d75c28f [0.06] + 0x3da3d70a [0.08]
               : f(g_numPlayers − 1) × 0x3d4ccccc [0.05] + 0x3d999999 [0.075]
if f(draw()) < c × 65536.0:                                                 # draw
    if draw() < 8000:  item = parse(string at 0x520040)                     # draw
    else:              item = item_generateConsumable()
    make the item prop

c = reagentFilter ? 0x3c03126e [0.008] : 0x3c4ccccc [0.0125]
if f(draw()) < c × 65536.0:                                                 # draw
    if item_generateFlag35Entry(halfLevel, reagentFilter) made nothing:  RETURN
    make the item prop
if f(draw()) < 0x43a3d70a [327.68]:                                         # draw (0.5 %)
    if item_generateFlag45Entry(halfLevel) made nothing:  RETURN
    make the item prop

if not (f(draw()) < itemChance × 65536.0):  return                          # draw
ra = draw();  rb = draw()                                                   # two draws
budget = (quality × ((f(ra) × 2⁻¹⁶) × 0x3ecccccc [0.4] + 0x3f4ccccc [0.8])) × (levelFactorDiff × 200.0)
if f(rb) < 0x4423d666 [655.35]:  budget = budget × 3.0
else if f(rb) < 0x454ccbff [3276.75]:  budget = budget + budget
B = int(budget)
category = 0;  if draw() >= 30000:  category = (draw() > 59999) ? 2 : 1    # one or two draws
if f(draw()) < 0x44f5c28f [1966.08] or forcePreset:                         # draw (3 %)
    made = item_generateFromSpecialTable(int(f(B) × (3.0 < budget ? 0x3fd99999 [1.7] : 7.0)), category, int(L))
else:
    made = item_generateWithAffixes(B, category, −1, int(L))
if not made: return
make the item prop;  if that failed: return
a = angle + ((draw() & 0x3fff) − 0x2000)                                    # draw
launch velocity x, y = math_cos16(a) × 24.0 × throwSpeed, math_sin16(a) × 24.0 × throwSpeed
```

- `levelFactor04` = `level_monsterLevelTimes0_4` 0x1ebf20: `L × 0x3ecccccc`; in PvP mode B
  `max(1.0, L − 4.0) × 0x3ecccccc`. `levelFactorDiff` = 0x1ebf70: the same with the factor
  8, 9, 10, 11, 12 for difficulty 1…5.
- `halfLevel` = `int(L)` halved toward zero, as a signed 16-bit value.
- "make the item prop": `pool_new(0x248)`; if it returns null the drop is skipped (and for
  equipment so is the angle draw); otherwise `PhProp_ctor` at `(x + 0.0, y, z + zOffset)`.
  The constructor is outside this module and draws from the shared generator
  (`GameObject_ctor` takes one value per object; `docs/issues/kill-loot-xp.md`). The model
  leaves those draws to a `World` object; the test replaces the constructor by one that takes
  0 or 1 value, on both sides.
- The two early `RETURN`s skip the later rolls entirely, so the number of draws of a call
  depends on the tables and the level.
- Minimum for a call in which nothing succeeds: 7 draws with one gold roll, 9 with three.

**`loot_spawnGold(position, amount)`** 0x100974 — nothing when `amount <= 0`. Otherwise up to
ten tries: draw three values `v = (f(draw()) × 2⁻¹⁶) × 2 − 1.0` (computed as `t + t − 1.0`),
redrawing all three while `vx² + vy² + vz² > 1.0`; offset `(vx × 12.0 × 3.0, vy × 12.0 × 3.0)`;
`h = terrain_height(12.0, world, position + offset)`; accept when `|h − z| < 6.0`, moving the
position by the offset and setting its height to `h`. After a hit or ten misses:
`pool_new(0xc0)` and the Gold constructor. Tested with scripted heights.

**`loot_spawnNamedItem(position, descriptor)`** 0x100ba0 (the `dropitem` property, script
built-ins): `parse(descriptor)` with variant −1, then `world_findFreeSpot` (three draws per
try, `symbols/objects.tsv`), `pool_new`, `PhProp_ctor`. The parse and its draw are tested.

## 9. Display names — `itemName_buildLocalizedName(item, decorated)` 0x101e48

Text comes from the string table by key (`text_lookup` 0x173c84): the noun's key is
`sprintf(format at 0x520058, name)`, a prefix's or suffix's key is the first field of its row.
`lang` is the signed byte 0x44fddc. The result is built in the static wide buffer 0x564420.

`strip(text)` (`itemName_stripGrammarSuffix` 0x101998) removes a grammar tag from the end of
the text and returns a form number:

| `lang` | Rule |
|---|---|
| 4 | if the last but one character is `_`: cut both; form 1, 2, 3, 4 for a last letter m, f, n, p (either case), else 0. No `_` there: form 0, text unchanged |
| 1, 3 | if neither of the two characters before the last is `_`: form 1, unchanged. Else by the last two letters (either case): `ms` 1, `fs` 2, `mp` 3, `fp` 4, cutting three characters; else last letter `m` → 1 or `f` → 2, cutting two; else cut three, form 0 |
| other | form 0, unchanged |

`affix(form, key)` (`itemName_getAffixForm` 0x101d0c): the key's text; when `form != −1` and
the text contains `|`, alternative number `form` of the bar-separated list, and then for
`lang` 1 and 3 that alternative loses its last three characters.

```
if not decorated or item.flags & 0x200:   return strip(text of the key made from the FULL definition name)
noun = text of the key made from the name cut at its first '+'
lang 1 or 3:  out = strip(noun);  F = its form
              prefix:  out += " " + affix({1:0, 2:1, 3:2, 4:3}[F] or −1, prefix key)
              suffix:  out += " " + text(suffix key)
lang 4:       prefix:  out = affix({1:0, 2:1, 4:3}[F] or 2, prefix key) + " "       # F from strip(noun)
              out += strip(noun)
              suffix:  out += " " + text(suffix key)
other:        prefix:  out = affix(0, prefix key) + " "
              out += noun
              suffix:  out += " " + text(key at 0x520068) + " " + affix(0, suffix key)
```

Tested with an invented string table and with the four text files of the disc served to both
sides (the lookup function itself is replaced). The German file carries one-letter tags and
the French and Spanish files two-letter tags, so `lang` 4 is German and 1 and 3 are French
and Spanish; which of the two is which is [U]. [O] tag shapes, tool run over the files.

Not modelled (the model raises `ValueError`): affix text containing `%` (it passes through
the engine's formatter `wstr_format` 0x19ea78), affix text of 128 characters or more, nouns
shorter than a tag, and a form number beyond the alternatives present (the original then
reads on past the end of the text).

## 10. What reaches the shared seed

One table of everything above that draws, for checking a rebuild's draw count:

| Function | Draws |
|---|---|
| parse with variant −1 | 1 if the definition has variants, else 0 |
| `item_randomizeVariant` | the same |
| §7.1 | 1 if category 1; then, if any row is eligible, 10 × (1 + parse) and the final variant draw if something was kept |
| §7.2 | 0–2 (cloth), 1 if category 0 or 1, 1 if `wantSuffix == −1` and category ≠ 2 (only when a row is eligible); per try 1 + (1 or more) + one parse per candidate; the final variant draw |
| §7.4 | 0, or 1 + parse + variant |
| §7.5 | 1 (third descriptor) or 2, plus the parse |
| §7.6 | 223 |
| §8 | as marked; plus what the object constructors take |

## 11. Floating point

- All arithmetic above must truncate (round toward zero) and saturate like the console's
  FPU; the constants must be the bit patterns given (0.6 is 0x3f199999, not the nearest
  float). `ref_items.py` does this in integer arithmetic with the same rules as `ee_emu`'s
  default model, and its results equal the original's bit for bit **under that model**.
- The two double-precision products at the top of §8 go through the library's software
  routines 0x3aef58 (float → double), 0x3af4d0 (multiply), 0x3afb90 (double → float). Those
  follow the console's float rules too: both the product and the conversion are truncated,
  so the result is the exact product truncated to 24 bits; exponent field 255 of a float is
  an ordinary exponent, a result of 2¹²⁹ or more becomes 0x7f800000, one below 2⁻¹²⁶
  becomes 0. [O] under emulation, 100,000 values
- What real hardware does in the last bit of a product or sum is not established
  (`docs/issues/dynamic-tests.md`). It matters here: `item_getValue` runs some forty
  operations inside `powf` and ends in `int(x + 0.5)`. Re-running the **original** under
  `ee_emu`'s other models, the value of 136 of 10,000 table items (as parsed) changed under
  the "ps2g1" adder, 0 under plain truncation, and 704 under the worst-case multiplier bias;
  the difference was never more than 1 gold. A generator compares values with a budget, so
  a 1-gold difference can occasionally change which item is generated, and with it the
  draw sequence. Two machines with the same FPU behaviour agree; whether an emulator setting
  or a rebuild with a slightly different multiplier agrees with a console is [U]. Recording
  the value of a few hundred shop items on a console (or on PCSX2 with its FPU options
  varied) and comparing with `ref_items.py` would settle it.
- Percentages: `x × 0.01` then a product, truncated, gives results one below the "obvious"
  integer whenever that integer is exact (§4).

## 12. What the differential test covers

`python3 -I -B tools/difftest_items.py [SLUS_209.73] [--quick | --full] [--iso disc.iso]`.
Default sample sizes are a fifth of the figures below (about 5 minutes on 12 cores; the table
rows are always all run); the figures are the `--full` run of this revision with `--iso`,
base seed 20973, 21 minutes on 14 cores: **26 properties, 26 PASS, 0 mismatches**. Without
the executable the script prints SKIP and exits 0.
"Record" means every byte the original defines (§2); for the parser it means all 0x48 bytes,
with the unwritten ones taken from a stack the test filled with random bytes.

| Property | Inputs | Compared |
|---|---|---|
| `powf` 0x3a7930 | 200,000 pairs, four fifths with the exponents used here, the rest random patterns | result, bit for bit. `y = 0.5` goes to the square-root routine, which is not modelled (not used by item code) |
| float × double | 100,000 | result, bit for bit |
| library `sscanf` | 30,100 (piece, format) pairs, all 43 formats | return value and the three integers |
| parser, table names | 607 base names; 835 presets as presets and again as plain descriptors | 0x48 bytes, seed (1,658 draws) |
| parser, random | 20,000 descriptors of 0–6 pieces: every word, cut words, bare words, signs, white space, numbers up to 2⁷⁰, garbage, empty pieces, unknown names, upper case, fixed variants −2³¹…2³¹−1, both tables | 0x48 bytes, seed |
| value | 200,000 random records (any code 0–0x2a incl. ones no descriptor can make, repeated codes, values −32768…32767, odd counts) | the value |
| weight, armour, attack rating, damage (both modes), model row | 100,000 random records | weight bit for bit, the integers |
| all of the above on real rows | all 1,442 rows as parsed | value and statistics |
| groups and record helpers | both group functions on all rows; 59,420 checks in all | results, bytes |
| preset generator | 600 calls with the library's own code, 7,500 with its string routines replaced | return value, record, seed |
| affix generator | 180 calls (library original), 2,000 (replaced); caps 1–120, budgets 0–10⁶, categories −1…2, suffix request −1…2, 1–4 players of random classes; 1.5 million draws | return value, record, seed |
| reagent, figurine, consumable | 30,000 calls, levels incl. out-of-range and 16-bit wrap, difficulties 1–5, with and without a picture filter | return value, record, seed |
| shop append | 198 lists of 1–4 appends (102 more not run: first try made nothing, §7.3) | list entries, seed |
| loot | 200 calls (library original), 7,500 (replaced): random seeds, levels 1–75, difficulties, player sets, both PvP flags, quality −1…36, with and without filter and forced preset; a quarter with seeds chosen so that the reagent or figurine roll succeeds; 3,215 gold, 1,024 consumable, 276 reagent, 92 figurine, 1,994 equipment drops; 1,064 early returns; 113 calls with a refused allocation | drops in order, their records, gold amounts, throw angle, prop position, seed |
| gold scatter | 20,000 calls, scripted terrain heights | queried points, final position, amount, seed |
| named drop | 3,000 descriptors | record handed to the constructor, seed |
| loader | 41 start seeds | seed after `item_loadResources` |
| requirement test | 200,000 random player records × items; every reason 0–9 occurred at least 4,843 times | the reason |
| names | 40,000 with an invented table; 20,000 with each of the disc's four text files; languages −1…5 | the wide string |

How the original was run, and the limits of that:

- Replaced in the tests that need a world: `pool_new` 0x14fdb8 (returns a buffer, or null on
  request), `PhProp_ctor` 0x155a0c (records its arguments, takes 0 or 1 value from the seed),
  `PhProp_initPhysics` 0x155110, `math_cos16` / `math_sin16`, `loot_spawnGold` (inside the
  loot test only; it has its own test), `Gold_ctor2` 0x157668, `terrain_height` 0x183820,
  `world_findFreeSpot` 0x14acf8, `res_find` 0x17365c, `text_lookup` 0x173c84. What those do
  in a game — including their draws — is **not** tested here.
- "Library replaced" rows run the item module's own machine code but substitute Python
  equivalents for `sscanf`, `strcmp`, `strcpy`, `strcat`, `strchr`, `strstr`, `memset`, to fit
  more cases in the time. The same properties also pass with the library's code, on the
  smaller samples shown, and `sscanf` is compared directly.
- Not covered: the picture cache and `item_buildPictureFilename`; `Creature_dropLoot` and
  every other caller (their arguments are taken as given); the shop's budget arithmetic;
  saving and loading; inventory code other than the requirement test; anything on a console.
- `tools/test_ref_items.py` (56 cases, no game files, invented tables) checks the model's own
  logic and runs in CI.

## 13. Corrections, a proposed ledger row, open points

Corrections to earlier documents (each [O] at the address given and confirmed by the test):

| Document | Says | Is |
|---|---|---|
| `docs/data-tables.md` §1.3 | "the first format that converts at least one value wins" | the first format for which `sscanf` returns non-zero; it returns −1 when the piece ends before the first value, so empty pieces, cut words and bare words match with value 0 (§3.1). 0x106ba4 |
| `docs/data-tables.md` §1.3, §10 | `requiredclass`: index or index plus one Unknown; who tests the `required…` codes Unknown | index plus one; all of them are tested by `inventory_checkEquipAllowed` 0x1c4948 (§6), which also applies class rules by weapon subtype, damage type and cloth |
| `docs/startup.md`, Item table | modifiers "+0x24, 4 × 8 bytes" in a 0x48-byte record, +0x22 "zeroed by copy" | the slots end at +0x44; +0x44…+0x47 is padding. +0x06, +0x22, the values of empty slots and the padding are never written at creation (§2) |
| `docs/startup.md`, `item_generateWithAffixes` | "the first try is the plain item, later tries build one candidate per eligible prefix" | the first try parses the plain item once per fitting prefix row (draws included); later tries cover only the first N prefix rows, N = number of fitting rows, so up to 10 fitting prefixes are out of reach at caps 1–18 (§7.2) |
| `docs/startup.md`, `item_generateFromSpecialTable` | "10 random picks" | the pick is off by one: first eligible row twice as likely, last never (§7.1) |
| `docs/startup.md`, loot step 6 | equipment "the caller's chance", ×2 with more than one player | the chance is also halved for everyone, and is a fixed 0.25 in PvP mode B; the preset branch multiplies the budget by 1.7 (by 7 when it is 3 or less); reagent and figurine generators get half the level (§8) |
| `docs/startup.md`, `item_getValue` | "by about 8 for the jewellery slots"; power "fixed" | × 8.009912 only for category 2 with slot 5, 6, 7, 14 or 15; the power is 1.95; for armour an `armorbonus` slot falls into the code-0x1a term (§5) |
| `docs/startup.md`, language codes | 4 German, 1 and 3 Romance: Inferred | supported by the tag shapes in the disc's text files (§9) |
| `docs/runtime.md` | 0x3aef58 / 0x3af4d0 / 0x3afb90 "Inferred from shape" | executed: float→double, double multiply, double→float, all truncating, no NaN/infinity handling (§11) |
| `symbols/ui.tsv` 0x1c4948 | "Inferred: class/race test" | the full requirement test of §6; returns a reason code 0–9 |

Proposed ledger row (not added to `FINDINGS.md` by this work):

| Id | Finding | Kind | Would matter when |
|---|---|---|---|
| I1 | Item records carry bytes the parser never writes (+0x06, +0x22, +0x44, values of empty slots); they come from its stack frame. `item_sameIdentityFields` 0x108924 compares the 32-bit word at +0x20, which includes +0x22, and `shop_openOrStock` 0x1c7af8 uses it as its duplicate test on freshly generated stock (calls at 0x1c7e28, 0x1c8070, 0x1c8428) to decide whether to generate again | [O] mechanism (parser and compare read in the disassembly, shop loop *(dec)*; byte origin seen under emulation) | the stack content under the first parse of a stocking pass differs between machines: then one machine retries a generation the other accepts, and the shared seed parts. Within a pass the bytes were seen to depend only on earlier candidates, which are lockstep. Whether the first one can differ is [U]; a dump of the three stock arrays (0x866e78, 0x868080, 0x869288) on two machines after entering a shop would show it |

No patch is proposed.

Open points:

1. §11: the last-bit behaviour of the console's multiplier against item values (up to 7 % of
   items move by 1 gold between `ee_emu`'s models).
2. Which of `lang` 1 and 3 is French and which Spanish; whether the US disc can select them.
3. What the callers of the requirement test do with each reason, and who sets flag bits 36,
   40, 41 and 43 on definitions (counts by `dump_tables.py`: 3, 11, 82 and 5 rows).
4. `item_appendGeneratedUnique` appending unwritten stack when its first generation makes
   nothing (§7.3): whether the shop's budgets ever let that happen.
5. Not reached: `item_buildPictureFilename` 0x107edc, the picture cache, the shop's budget
   arithmetic, `Creature_dropLoot`'s per-class additions (traced in
   `docs/issues/kill-loot-xp.md`, not modelled).
