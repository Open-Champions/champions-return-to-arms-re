# Audit of structure-field and flag-bit claims after the `fieldxref` / `flagxref` rewrite

Scope: statements in `FINDINGS.md`, `docs/*.md`, `docs/issues/*.md` and `docs/spec/*.md`
whose truth depends on a list of the readers or writers of a structure field, or of the
tests of a flag bit, being complete. `docs/issues/claims-audit.md` did this for globals
after `tools/gxref.py` was corrected; its section 6 showed that the two sibling tools had
comparable gaps and that the claims resting on them had not been re-checked. This document
fixes the two tools, measures the change and re-checks the claims.

Everything here was read from the executable (SLUS_209.73, v2.00), its disassembly and its
decompile; **nothing was run on a console or emulator.** (The project does run the game in
an emulator — Play!, not a PlayStation 2 and not PCSX2, `docs/issues/live-rig.md` — but this
audit used none of it.) Statements are **Observed** unless
marked otherwise. `FINDINGS.md`, the other documents, `names.tsv` and `patches/` were not
edited; corrections are listed in section 5 for whoever applies them. No patch is proposed
and no symbol was added.

## 1. Result in short

- **Both tools were rewritten** on one shared analysis (section 2). On 47 (offset,
  structure) pairs the documents use, narrowed to the structure's own functions, the old
  tool printed 1,284 accesses and the new one 1,831: 545 added, 307 of them certain, in 39
  of the 47 pairs. On 34 flag bits the old tool printed 1,235 hits, of which **342 were
  false** (the flag word never reaches the masked register); the new one prints 1,744
  certain hits, 904 of which the old tool did not have (section 3).
- **39 claims were examined one by one**, first the ledger rows the earlier audit named.
  **27 stand as written, 9 stand with a changed list, 3 are wrong** (section 4). A further
  27 statements in the area and specification documents were checked mechanically only
  (section 4.3).
- **No ledger row is overturned and no patch loses its safety argument.** D12–D15, G2, G12,
  G14, G24, D28, E11, K3, K4, B1, B9, MV6, D34/D40 and ST4–ST6 hold with the corrected
  scans. The two patches whose argument is a field list ("prediction copy starts without
  pending damage", "CloudGiant king conjure test uses a shared flag") hold.
- **The three wrong statements** are in issue and area documents, not in the ledger:
  `sync-breakers.md` says creature +0xf0 is read only in the counter-7 branch of
  `Creature_run` (it is also read in `Player_run`, where it times the creation of an
  object); `prediction-copy.md` says creature flag bit 63 is set only in the charm branch
  of `Creature_run` (it is the "active" bit, set for every active creature); and
  `creatures.md` says no code in its range writes a status counter except the clones
  (`Creature_draw` and `Creature_run` do). The conclusion drawn survives in the last two;
  the first adds a consequence that is confined to the old ability path of D16.
- **Step 4 found one new latent route and two extensions of known ones** (section 6): the
  inventory screen's model drawing contains code that zeroes the 17 equipped-item words of
  the player record, which the simulation reads and the lobby checksum covers — but its
  trigger needs a global (0x44f070) that nothing sets, so it is dead as shipped. The stats-page
  window of K3 has four more simulation readers than SB2 lists. No new candidate was found
  for code that runs for the prediction copy.

## 2. The two tools after the rewrite

`tools/flagxref.py` now imports `tools/fieldxref.py`; both use one analysis:

- **Function bodies from `ghidra_funcs.tsv`**, as `gxref.py` does. Code no function
  contains is grouped and marked "(outside any function)".
- **A forward data-flow pass over the function's real control flow** instead of a look-back
  window or the listing order: branch targets, delay slots, likely-branches (whose delay
  slot runs only when taken) and joins are modelled. Blocks reached only through a jump
  table are given the merged state at the function's indirect jumps. The listing this
  checkout has elides runs of zero words; they are put back as no-ops (without that, 567
  functions had unreachable blocks; with it, 3).
- **Each register holds "root + constant"**: the root is the function's incoming value of a
  register, a value loaded from memory, a call's result or a join. `addiu`, `move`,
  `addu`/`subu` with a constant, an index added to a pointer, and spills to the stack frame
  are followed. A pointer stepped round a loop becomes "start + n × step"; when the loop's
  exit test compares a constant-step counter or pointer with a constant (three shapes are
  recognised) the trip count is attached, so `Creature_draw`'s walk over the 16 status
  counters is listed for each counter, certain, and not beyond the sixteenth.
- **A loaded value is followed through moves, shifts and masks**, with every mask translated
  back to bit numbers of the bytes that were loaded. That removes the six-instruction
  window and lets one query match a word load, a byte or halfword load inside the word, an
  8-byte or unaligned load covering it, or a load through a formed pointer.
- **Certain and possible.** A hit without `?` touches that byte offset from the pointer the
  tool names on every path. `?` marks: a base kept across a call in a register a call may
  destroy, a pointer reloaded from the frame of a function that takes a local's address,
  two different offsets merged outside a loop, a later element of an indexed access or of
  a walk whose length is unknown, code outside every function, and run-time masks.
- The result for the whole executable (160,037 loads and stores with a non-stack base,
  31,102 address events, 7,634 bit operations) is cached in `disasm/text.fx.pickle` — about
  6 s to build, then a fraction of a second per query. The file is a derived cache like
  `disasm/text.ins.pickle` and is ignored by git; `--no-cache` avoids it.

The old command lines still work (`fieldxref.py ELF off[,off] [--stores]`,
`flagxref.py ELF MASK [off]`). New options: `--class`, `--func`, `--range`, `--this`,
`--loads`, `--array`, `--static`, `--adjust`, `--blocks`, `--roots`, `--certain`,
`--walk-limit`, `--no-follow`, `--no-cache`; `flagxref.py` adds `--stores`. Each docstring
lists the output marks and what the tool cannot see. `tools/test_fieldxref.py` has 48 unit
tests on hand-written listings (no game file).

### 2.1 What `fieldxref.py` gained

| Gap named in claims-audit 6.2 | Now | Size in this executable |
|---|---|---|
| unaligned loads and stores | the left/right pair is one access at the right half's displacement (`uld`, `usd`, `ulw`, `usw`) | 10,080 load halves and 9,306 store halves with a non-stack base |
| a wider access at a lower displacement | listed with `*` when its width reaches the offset; 128-bit loads and stores are decoded from the ELF (the listing shows them as unknown) | 321 128-bit accesses with a non-stack base; e.g. 1,278 covering accesses of +0xc |
| a pointer formed first | listed at the sum, with the base shown: `sw+0{a0+36c}` | 31,741 accesses go through a formed pointer |
| loops over an array inside the object | the walk and, where recognised, its trip count: `{a0+36c~4x16}` | 5,701 accesses through a walking pointer, 2,663 with a trip count |
| array elements other than element 0 | an index added to the base is marked `[i]`; `--array START,STRIDE,COUNT` lists indexed and walking accesses for any element | 17,050 indexed accesses |
| static instances | `--static BASE[,STRIDE[,COUNT]]` lists absolute accesses (constant addresses, with or without an index) to any instance | 30,068 absolute accesses |
| a shifted `this` | `--adjust N`. Only two virtual tables in the executable have a non-zero adjustment (library classes, −8 and −4), so game classes are not affected | — |
| whole-object copies and fills by a called routine | `&+K>callee` when the address of +K is handed to a call; the callee's own accesses through that pointer are listed (`sw+0<site&+K`, direct calls three deep); `--blocks` adds calls with a constant length | 9,035 calls pass object + K |
| cannot tell classes apart; heuristic function bounds | Ghidra bounds; `--class` (functions in the class's virtual table or named `Class_…`), `--this`, `--func`, `--range`, and `--roots` to see where each base pointer came from | — |

Checked against the old tool: on 15 offsets the old tool's own output is reproduced exactly
by filtering the new database for "aligned access, displacement equal, base not the stack
pointer", and every old hit is among the new ones.

### 2.2 What `flagxref.py` gained

| Gap named in claims-audit 6.3 | Now |
|---|---|
| the ±6-instruction window | none: the loaded value is followed to wherever it is used, also across calls in a saved register and through the stack frame |
| only the exact one-bit immediate | any mask that contains the bit; the whole mask is printed when it differs (`test:20008`) |
| tests by shifting | `test(sign)` (the bit moved to, or already in, the sign position and branched on) and `test(shift)` (shifted down so only bits including this one remain, then branched on, compared, stored or passed) |
| the mask in a register | constants built by `lui`, `ori`, `addiu`, shifts and `nor` are followed like any value, including out of loops. A mask that is the function's own argument is looked up one call higher (`addr:set>callee`); a `1 << n` mask or a variable shift is listed as possible for every bit (`set(var)?`) |
| byte, halfword and 8-byte access | handled by the bit translation; `flagxref 80000000 a8` now prints the tests, the set and the clears in `Creature_run` |
| toggle and whole-word writes | `toggle`; `--stores` lists stores over the word that are not the same word written back (`store=CONST`, `copy<+off`, `store?`) |
| clearing bit 15 | the two-instruction constant is followed like any other |
| formed pointer, fixed address | as for `fieldxref.py` |
| false hits (unrelated immediates, substring register match) | gone: a hit needs the flag word itself in the operand register |

### 2.3 What the pass still cannot see

Stated in both docstrings; in short:

1. **Which structure.** An offset alone does not name a type: every structure with something
   at that displacement is listed. The tool narrows by `--class`, `--this` (base is the
   function's first argument), `--func`, `--range`, and shows the base's origin with
   `--roots`. A base loaded from memory or returned by a call is the reader's job to
   identify by reading the function.
2. A base whose constant part was added out of reach: in memory other than the stack frame,
   behind a virtual or indirect call, more than three direct calls away, in a callee that
   keeps the pointer, or folded into an index register in a way that is not a constant.
3. Which element an indexed access or an uncounted walk reaches (possible for the whole
   array, within `--walk-limit` for a walk).
4. Whole-object copies and fills that start at the object's own address with a computed
   length; `--blocks` is crude (any constant in a later argument register counts as a
   length).
5. Flag values that reach the test through memory other than the stack frame, through a
   call, or that change inside a loop (one case in the soft-float library, 0x3ae84c);
   masks read from a table or passed through two calls; whole-word comparisons.
6. Values merged from different pointers at a join are forgotten (plain displacement only).
   Jump tables are not read.

## 3. Old output against new

Method: the old tools were kept and run unchanged. For fields, "in scope" means hits in the
functions of the named class (its virtual table plus `Class_…` symbols), or in all functions
where no class applies; a new hit counts as added when the old tool did not print that
instruction. "Certain" excludes `?` hits.

### 3.1 Fields: 50 (offset, structure) pairs

Totals for the 47 pairs that are narrowed to a structure or to the static record table:
old 1,284, new 1,831, added 545 (307 certain); 39 pairs gained an access, 30 a certain one.
The three unrestricted small offsets (+0x4, +0xc, record +0xd0 searched everywhere) go from
16,363 to 28,524.

| Offset | Structure | Scope | Old | New | Added (certain) | Mostly | Functions that gained most |
|---|---|---|---|---|---|---|---|
| +0x374, +0x37c, +0x388, +0x38c, +0x394, +0x398, +0x39c, +0x3a0 | Creature status counters 2, 4, 7, 8, 10, 11, 12, 13 (8 pairs) | Creature, Player | 13, 3, 7, 1, 1, 2, 2, 2 | 24, 14, 18, 12, 12, 13, 13, 13 | 11 (10) each | walking pointer | `Creature_draw` 4, `Creature_clone` 2, `Player_clone` 2, `Player_ctor` 1, `Player_draw` 1 |
| +0xc8 | Creature pending damage | Creature, Player | 37 | 49 | 12 (1) | walking pointer (possible: save and record code) | `player_packRecord`, `Creature_saveState` |
| +0x2dc | pending-damage data | Creature, Player | 50 | 54 | 4 (4) | wider access below | `Creature_processDamage` 3 |
| +0x2e0, +0x2e8 | pending-damage fields | Creature, Player | 17, 31 | 18, 32 | 1 (1) each | walking pointer | `player_importCharacter` (the record, not the creature) |
| +0x2e4 | attacker handle | Creature, Player | 9 | 24 | 15 (15) | address passed, inside a callee | `handle_link`, `Creature_takeDamage`, clones |
| +0x364 | attached-spell list | Creature, Player | 3 | 19 | 16 (16) | address passed, inside a callee | `handle_link`, `Creature_dtor`, clones |
| +0x360 | effect handle | Creature, Player | 4 | 18 | 14 (14) | address passed, inside a callee | `Creature_setEffectTimer`, clones |
| +0x234 | target handle | Creature, Player | 58 | 90 | 32 (31) | address passed, formed pointer | `Creature_pickTarget` 5, `Player_run` 3 |
| +0x238 | ally handle | Creature, Player | 12 | 32 | 20 (19) | address passed | `Creature_pickAlly` 5, `Creature_spawnScavenger` 3 |
| +0x4b8, +0x588 | Player handle lists | Player | 1, 3 | 15, 13 | 14 (14), 10 (10) | address passed, inside a callee | `Player_run` 3, `Player_clone` 2, `Player_dtor` |
| +0x2fc | slow byte | Creature, Player | 46 | 47 | 1 (1) | — | (record walk) |
| +0xf0 | creature +0xf0 | Creature, Player | 12 | 27 | 15 (0) | walking pointer (possible) | save and record code |
| +0x231, +0x232 | inert bits, AI state | Creature, Player | 42, 25 | 48, 29 | 4 (2) each | wider access below | `Creature_advanceWaypoint` |
| +0x58c | Player action state | Player | 87 | 92 | 5 (5) | formed pointer | `Player_processDamage` 2, Player slot 27 2 |
| +0x3c8, +0x540 | Player slot, vehicle pointer | Player | 393, 8 | 394, 9 | 1 (1) each | — | (record walk) |
| +0xa8 | creature flag word | Creature, Player | 127 | 141 | 14 (3) | formed pointer | `Creature_pickAlly` 2 |
| +0xa0 | tint byte | Creature, Player | 11 | 30 | 19 (8) | formed pointer | `Creature_pickTarget` 2 |
| +0x4a5c, +0x4a74, +0x4a78 | record selector and float fields | record table | 8, 11, 7 | 10, 12, 9 | 2, 1, 2 (0) | static instance | `player_initNewCharacter` |
| +0x4c20 | record speed multiplier | record table | 3 | 11 | 8 (0) | static instance | `Player_move`, `player_speedScale`, GiantGrowth, Resurrect; the arena store 0x307d04 is now listed |
| +0x4c1c | record character kind | record table | 0 | 9 | 9 (3) | static instance, wider access below | `player_initNewCharacter` 4, `player_importCharacter` 2 |
| +0x43d8 | record object pointer | record table | 152 | 278 | 126 (13) | static instance | 60 functions |
| +0x530, +0x508 | CloudGiant beam handle, bolt flag | CloudGiant | 11, 4 | 11, 4 | 0 | — | — |
| +0x610 | pose buffer owner | all functions | 8 | 76 | 68 (62) | other structures (animation-state copies, library) | none in the pose code |
| +0x104, +0xe4 | prop fields | Prop, ItemProp, PhProp | 12, 0 | 23, 10 | 11, 10 (0) | walking pointer (possible) | constructors, save and load |
| +0x84, +0xc4 | Savepoint effect state | Savepoint | 8, 8 | 8, 8 | 0 | — | — |
| +0x4d | JumpGate mark | JumpGate | 15 | 15 | 0 | — | — |
| +0x408 | Vehicle help latch | Vehicle | 6 | 11 | 5 (0) | walking pointer (possible) | seat loops |
| +0x4a8, +0x1c, +0x64 | StaticFire, SpellBlindingLight, HolyBolt pointers | own class | 7, 2, 8 | 7, 2, 8 | 0 | — | — |
| +0x34 | Camera mode word | Camera | 7 | 19 | 12 (0) | walking pointer (possible) | `Camera_saveState`, `Camera_loadState` |
| +0xd0 | record weapon damage, searched everywhere | all functions | 422 | 1,560 | 1,138 (160) | walking pointer (possible), unaligned | drawing code (other structures) |
| +0xc | object flag word | all functions | 5,363 | 8,651 | 3,288 (2,916) | wider access below 1,278, unaligned 715, formed pointer 617 | — |
| +0x4 | object list head | all functions | 10,578 | 18,313 | 7,727 (7,399) | unaligned 4,545, wider access below 2,091 | — |

### 3.2 Flags: 34 bits

Old 1,235 hits. 342 of them are not confirmed: for 340 the masked register was never
loaded from the flag displacement (an unrelated immediate near an unrelated access — for
example the constant that builds a 64-bit mask for +0xa8 next to a store at +0xc), one
(0x110968, `Creature_deadUpdate`) is reached by a branch taken before the load, and one
(0x3ae84c, soft-float library) is real and still missed (2.3, item 5). New: 1,744 certain
hits, 904 not in the old output, plus 3,595 possible hits (run-time masks, listed for every
bit).

| Mask | Word | Old | Old, false | New certain | New certain, not in old |
|---|---|---|---|---|---|
| 0x1 | +0xc | 225 | 99 | 258 | 136 |
| 0x2 | +0xc | 117 | 23 | 185 | 98 |
| 0x4 | +0xc | 28 | 27 | 48 | 47 |
| 0x8 | +0xc | 116 | 41 | 208 | 132 |
| 0x10 | +0xc | 23 | 11 | 40 | 31 |
| 0x20 | +0xc | 180 | 2 | 212 | 49 |
| 0x40 | +0xc | 185 | 13 | 203 | 47 |
| 0x80 | +0xc | 12 | 9 | 8 | 5 |
| 0x100 | +0xc | 22 | 6 | 26 | 10 |
| 0x200 | +0xc | 14 | 8 | 41 | 35 |
| 0x400 | +0xc | 7 | 7 | 13 | 13 |
| 0x800 | +0xc | 14 | 9 | 34 | 29 |
| 0x1000 | +0xc | 5 | 0 | 31 | 26 |
| 0x2000 | +0xc | 11 | 5 | 30 | 24 |
| 0x4000 | +0xc | 39 | 9 | 94 | 64 |
| 0x8000 | +0xc | 53 | 41 | 16 | 7 |
| 0x20000 | +0xc | 40 | 0 | 60 | 20 |
| 0x40000 | +0xc | 4 | 1 | 10 | 7 |
| 0x80000 | +0xc | 7 | 0 | 7 | 1 |
| 0x100000 | +0xc | 51 | 8 | 61 | 18 |
| 0x200000 | +0xc | 3 | 1 | 6 | 4 |
| 0x400000 | +0xc | 16 | 2 | 20 | 6 |
| 0x800000 | +0xc | 4 | 2 | 6 | 4 |
| 0x1000000 | +0xc | 29 | 5 | 26 | 8 |
| 0x2000000 | +0xc | 2 | 0 | 2 | 0 |
| 0x4000000 | +0xc | 8 | 4 | 4 | 0 |
| 0x8000000 | +0xc | 8 | 5 | 4 | 1 |
| 0x20000000 | +0xc | 8 | 3 | 3 | 0 |
| bit 31 | +0xa8 | 0 | 0 | 7 | 7 |
| bit 63 | +0xa8 | 0 | 0 | 27 | 27 |
| 0x1 | +0xa8 | 4 | 1 | 18 | 12 |
| 0x4000000 | +0xa8 | 0 | 0 | 19 | 19 |
| 0x8000000 | +0xa8 | 0 | 0 | 15 | 15 |
| 0x100 | +0xa8 | 0 | 0 | 2 | 2 |

The counts at +0xc include every structure with a word there (pads, items, tasks, library
streams), as before. For the two copy flags: 0x20000 has 60 certain hits against 40 before
(none of the 40 was false), one of them the set at 0x13b570; 0x200000 is set at 0x13b588
and cleared at 0x13b55c, and in game code is tested with a fixed mask only in
`Player_animStep` 0x1b9584 (the other users take the exclude mask in a register).

## 4. The claims

### 4.1 Method

1. A search of `FINDINGS.md` and the 60 documents for about forty phrasings ("only … writes",
   "nothing reads", "no reader", "read only by", "is set only", "no writer", `fieldxref`,
   `flagxref`) next to an offset, a flag or a counter gave 338 lines. The ledger rows the
   earlier audit named, the other rows and patches that rest on a field or flag list, and
   the statements those rows cite were taken first (4.2). What was left over was only
   swept mechanically (4.3) or not reached (section 8).
2. For each claim the new tool was run with the structure's class, with `--static` for the
   player record table (0x4d8af0, four records of 0x4c30 bytes), with `--array` for the
   status counters, and without a class filter where the claim is about "any code".
3. Every reader or writer that the document does not name was read in the decompile
   (`decomp/all/<entry>.c`) or the disassembly.

"Old" below means the old tool's output; "new" the corrected scan plus what the code does.

### 4.2 Claims examined one by one

| # | Claim | Field or flag | New evidence | Verdict | Consequence |
|---|---|---|---|---|---|
| 1 | D12: `Creature_draw` decrements the first non-zero status counter | creature +0x36c…+0x3a8 | the old tool printed nothing for the decrement: it is a load (0x10b8a8, 0x10b8cc) and a store (0x10b8d4) through a pointer walked over 16 entries. No other function stores into the array through a walk or an index | stands | none |
| 2 | D14: simulation readers of counters 2, 4, 7, 12 | +0x374, +0x37c, +0x388, +0x39c | same simulation readers. Added by the new forms: `Player_draw` reads counter 0 (0x1a4a8c) and walks the others (0x1a4ae4); `Creature_draw` has an indexed read (0x10b7e0). Not in the row though the old tool printed it: `UnholyAura_run` 0x2949bc reads its owner's counter 12 and starts fading when it is 0 | stands, list changed | none: counter 12 is the one drawing never decrements |
| 3 | D15: only four ability effects set counters 2, 7, 12, 13 | same | non-zero stores: 0x1a71c4 (counter 2), `Root_ctor` 0x293a1c (7), `UnholyAura_ctor` 0x294950 (12), 0x1abe90 (13) — as the row says. Zero stores it does not mention: `Player_run` 0x1a5b0c (counter 2 when mana runs out), 0x1ac068 (counter 12 toggled off), `Creature_run` 0x113744 and 0x113758 (counter 7). `Player_ctor` 0x1a229c zero-fills all 16; 34 clone functions copy all 16 (only `Player_clone` runs) | stands, list changed | none; "sets" means "sets to a non-zero value" |
| 4 | D15: counters 8, 10, 11 are read only by drawing | +0x38c, +0x394, +0x398 | no reader outside `Creature_draw` and `Player_draw`. Setters the row does not list: `Player_run` 0x1abda0 (counter 11 = 41), `OniBall_onTouch` 0x294800 (8) and 0x294844 (10) | stands, list changed | none |
| 5 | kill-loot-xp.md: counter 4 has no setter at all; counter 2's only setter is the old ability path | +0x37c, +0x374 | no store to creature +0x37c by any form outside constructors' zero-fill and clones (`SpellWizardBeam_ctor` 0x2f18fc writes the spell's own +0x37c) | stands | none |
| 6 | creatures.md: `Creature_run` reads only counter 7 | +0x388 | loads at 0x113614, 0x113728, 0x113734, 0x1137ac, nothing else in the array | stands | none |
| 7 | creatures.md: "No code in this range writes any counter except through whole-object copies (clone)" | +0x36c… | `Creature_draw` 0x10b8d4 and `Creature_run` 0x113744 / 0x113758 are in the range and write | **wrong as worded** | conclusion intact (no non-zero setter in the range); the two bullets above the sentence describe both writes |
| 8 | G2: the clone starts with every handle list empty (+0x364, +0x360, +0x234, +0x238, +0x2e4, +0x4b8, +0x588) | handle heads | `Player_clone` passes each of the seven to `handle_initEmpty` (0x11eb64, 0x11eb70, 0x11ec00, 0x11ed2c, 0x11ed38, 0x11ef90, 0x11f148). It does the same for five more the row does not list: the handles at +0x3d8 + 0x18·n, n = 0…4 (loop at 0x11ede0–0x11ee20; `Player_dtor` clears them from 0x1a1cc0), and for the object's own heads +4 and +8 (0x11e8c0, 0x11e8cc). Every head that `Creature_dtor` or `Player_dtor` clears is among those the clone empties | stands, list changed | none: the copy shares no handle |
| 9 | G8, player.md, prediction-copy.md: record +0x4a5c is written without a guard and nothing else reads it | record +0x4a5c | readers only in `Player_run` (0x1a6200, 0x1a6258, 0x1a8054). Writers also `player_importCharacter` 0x1bd904 and the zero store in `player_initNewCharacter` 0x1b2218, now listed (`--static`). The character checksum does not cover it (row 24) | stands | none |
| 10 | G12: `Player_clone` copies the pending-damage fields +0xc8, +0x2dc, +0x2e0, +0x2e8 | creature | loads and stores at 0x11ea84/0x11ea8c, 0x11ebfc/0x11ec04, 0x11ebe8/0x11ebf0, 0x11ec08/0x11ec14; no covering, unaligned or pointer-formed access to them in the clone | stands | none |
| 11 | G14: … and leaves the attacker handle empty | +0x2e4 | address formed at 0x11ebb0, `handle_initEmpty` at 0x11ec00 | stands | none |
| 12 | G24 and patch "prediction copy starts without pending damage": one store | +0xc8 in `Player_clone` | 0x11ea8c is the only store that reaches bytes +0xc8…+0xcb of the new object. No newly found writer of creature +0xc8 anywhere (the new hits are other structures: the record, save buffers, props) | stands | patch argument holds |
| 13 | D28: the king tests a visual beam handle | CloudGiant +0x530 | accesses only in `CloudGiant_ctor`, `CloudGiant_run`, `CloudGiant_setState`; nothing added | stands | none |
| 14 | patch "CloudGiant king conjure test uses a shared flag": +0x508 is the simulation's own | CloudGiant +0x508 | stores 0x251a00, 0x252280, 0x2522e8 and the read 0x251f84, all in `CloudGiant_run` | stands | patch argument holds |
| 15 | E11: bit 31 of the creature flag word is set from the local alive list; "nothing else reads the bit" | +0xa8, bit 31 | `Creature_run` tests it at 0x113a3c and 0x113ab0, sets it at 0x113a44, clears it at 0x113ad0. **The script flag helper 0x1445fc also tests it (0x14464c) and clears it (0x144670)** when a script clears creature flag 0: it then zeroes the two boss-meter globals. The helper's run-time bit number can only be 0 or 26. Clones copy the word; `cut_execKey` 0x196e68 copies it between creatures | stands, list changed | none: the extra reader writes only the bit itself and the per-machine boss-meter globals. `creatures.md` C3 already names it |
| 16 | creatures.md C3: `Creature_saveState` does not store bit 31 | same | it packs bits 22, 23, 24, 32 and 49 of the word (0x116874) | stands | none |
| 17 | "Ruled out": the hit-flash flag 0x100 is read only by drawing | object +0xc, 0x100 | tests: `Creature_draw` 0x10b150, `AutoObject_draw` 0x23aa9c and 0x23ac9c, and `net_frameLoop` 0x13af20 (which moves it to the copy: set 0x13af24, clear 0x13af30). Sets: `Creature_processDamage` 0x110de8 and, not in the documents' lists, `Player_processDamage` 0x1b336c; the three `…LP_draw` functions. No call site passes 0x100 as a constant mask to a function that takes one | stands, list changed | none |
| 18 | draw-sim-leaks.md: draw code writes only bit 0x100 of the flag word | same | clears at 0x10bac4 and 0x23acc8, sets in the three LP draws; no other store over +0xc from a draw slot that is not the same word written back | stands | none |
| 19 | D13 / G1: 0x200000 is set only on this machine's own player; the copy gets 0x20000 | +0xc | fixed-mask sets and clears of either bit exist only in `net_frameLoop` (0x13b570; 0x13b55c, 0x13b588) | stands | none |
| 20 | G6, objects.md: tests of 0x20000 | +0xc | 60 certain hits against 40 (3.2). The ones the old tool lacked are combined masks (`Creature_isEnemy` 0x119364 and `Creature_isAlly` 0x119468 test 0x20008), tests far from the load, and tests behind a join (`obj_moveWithCollision` 0x14d88c, `world_collectObjectsInBox` 0x14aa7c, `Gold_onTouch`, `Player_meleeHit`, `Player_usePotion`, `Player_regenMana`, `Player_regenHealth`, `Player_onTouch`, `OniBall_onTouch`, `SpellCyclone_ctor`, `arena_onPlayerKilled`, `arena_loseLife`) | stands, list changed | none: the documents found these guards by reading |
| 21 | K4, kill-loot-xp.md, draw-sim-leaks.md: `hud_spellSelect` writes record +0x4a74 / +0x4a78; no simulation reader | record | `hud_spellSelect`, the unreferenced 0x1de8c4, `player_importCharacter`, and the zero stores of `player_initNewCharacter` (0x1b2230, 0x1b2234) | stands | none |
| 22 | K3 and patch "stats page does not rewrite stored weapon damage" | record +0xcc, +0xd0, +0xd4 | writers: `Player_recalcDamage`, `Player_meleeHit` (0x1b6ef4–0x1b6fcc), import and creation. The checksum does not cover them | stands | patch argument holds |
| 23 | SB2: the hit handlers of FireArrow, ColdArrow and PoisonArrow read +0xd0 / +0xd4 inside the K3 window | same | also `MultiFireProjectile_onHit` 0x2da720 / 0x2da780, `SkillMultiFire_cast` 0x2d9d24 / 0x2d9d6c, `SkillFireAxe_cast` 0x319b58 / 0x319b6c, `SkillColdAxe_cast` 0x31a48c / 0x31a4a0 | stands, list changed | four more readers inside the window of K3 (section 6) |
| 24 | B1: kind 2 is given only by character creation in the lobby and by the launch code | record +0x4c18 (8 bytes; kind in +0x4c1c) | stores: `player_initNewCharacter` 0x1b1e5c, 0x1b1e90; `player_importCharacter` 0x1bdb14 (read back and rewritten); `game_restorePlayerRecord` writes +0x4c15…+0x4c19 only. `player_checksum` 0x1bdc98 covers record bytes 0x20–0x23, 0x58, 0x59, 0x5c–0x5f, 0x90… (indexed), 0xc0–0xcb, 0xe4–0xeb, 0x3748–0x41cf and 0x43f0–0x4433 | stands | none |
| 25 | B9: the save point's own effect state follows each machine's card state | Savepoint +0x84, +0xc4 | nothing added | stands | none |
| 26 | MV6 (as corrected): writers of the record speed multiplier | record +0x4c20 | GiantGrowth 0x3093c4, 0x309668; Resurrect 0x312a28, 0x312adc; import 0x1bdb0c; creation 0x1b23f0; arena set-up 0x307d04 — the store `gxref` misses is listed by `fieldxref` | stands | none |
| 27 | D14 / F4: the slow byte is read by movement and animation | creature +0x2fc | `Creature_turnToward`, `Creature_run`, `Creature_moveTo`, `Creature_moveToDirect`, `Creature_fleeFrom`, `Creature_stepAnim`, `Player_run` (0x1a81a0, 0x1aa178), `Player_move`, `Player_animStep`, `Ghoul_run`; nothing added | stands | none |
| 28 | D34 / D40: the pose buffer's owner field | buffer +0x610 (+0x614, +0x618, +0x61c) | accesses only in `anim_advance`, `anim_buildPose`, `anim_emitPose`, `anim_init`, `anim_jumpTopToEnd`, `anim_snapTopToEnd`, `AnimState_dtor`, `anim_releaseCaches`; the 68 added hits at +0x610 are other structures | stands | none |
| 29 | pose-cache.md: calls that detach | same | the five functions it lists are the ones that store 0 to the owner | stands | none |
| 30 | pose-cache.md: direct stores into track fields (`Player_move`, `SpellRaiseArmy_raiseInRing`, `cut_advance`) | creature +0x11c…+0x21b | also `Player_run` (0x1a6c08–0x1a6c1c; loops at 0x1a7298 / 0x1a72a0 and 0x1a7f08 / 0x1a7f10; indexed 0x1ab1a8, 0x1ab82c), `Player_updateCast` (0x1a423c, 0x1a4240, after its two skeleton queries: clamps a weight to 1 and sets a fade rate), `Player_idleFidget` (0x1bc388, 0x1bc390; called from `Player_run` 0x1a576c), `player_resetIdleAnim`, `AntQueen_fadeBankTracks` 0x238638 | stands, list changed | the player argument is unaffected: all of these run inside `Player_run` before the tail query, except the stores of `Player_updateCast` itself, which do not change the blended pose until the next step (**Inferred** from the clamp rule the document gives); `player_resetIdleAnim` releases the caches |
| 31 | ST4: none of the 17 `net_objOrGhost` call sites stores its result | call results | traced with the pass: one site, `minimap_draw` 0x1e4c1c, writes the result into a stack array of blip objects (draw code, already in prediction-copy.md); the others pass it to query helpers | stands | none |
| 32 | ST6, SA1–SA3, SB3: plain pointer fields and where they are cleared | Root +0xb0, ParticleMorphEffect +0x54 / +0x58, NPC +0x474, Player +0x540, FireBomblet +0xac, SpellBlindingLight +0x1c, HolyBolt +0x64, SpellShieldBash +0x24, SpellBash +0x24, StaticFire +0x4a8, FrostShard +0x78 | no access added in any of the classes | stands | none |
| 33 | sync-breakers.md §5: creature +0xf0 "is read only in the counter-7 branch of `Creature_run`" | creature +0xf0 | also read by `Creature_draw` 0x10b76c and by **`Player_run` 0x1a66f0**: in action state 0xc, when +0xf0 equals the frame counter minus 30, it allocates a pool block and constructs a `LightEffect` | **wrong** | `jumpgate_travelEffect` (a draw task) writes +0xf0 of every living player, so the object would be created on a per-machine frame. State 0xc is entered only by ability effect 0x0e (0x1a71c8), so this is one more consequence of D16, not a route of its own |
| 34 | sync-breakers.md §5: what `jumpgate_travelEffect` writes on players | player object | +0xf0 (0x27ead0), +0x394 (0x27eae8) and the colour words +0x90…+0x9e (0x27ea2c–0x27ea48); it also hands the player's animation state to `model_getSamplePoint` (0x27ee30) | stands | the skeleton query from a draw task was not followed (section 8) |
| 35 | prediction-copy.md §3.2: creature flag "bit 63 is set only in the charm branch of `Creature_run`" | +0xa8, bit 63 | bit 63 is the "active" bit: `Creature_updateActive` sets it at 0x10c204 and clears it at 0x10c210, eight constructors set it, `Creature_stepAnim` 0x116324 tests it. `Creature_spawnScavenger` 0x112660 requires bit 63 set and bit 62 clear | **wrong** | conclusion intact: the scavenger spawn also needs AI state 0x14 at +0x232, and in the Player table the only stores to +0x232 are `Creature_loadState` and the clone's copy |
| 36 | engine.md: the Torch, Lantern and Lamp run functions write only +0x68…+0x84 | own object | the stores go through a pointer formed at +0x4c (0x2b2660–0x2b267c and the two siblings); nothing else | stands | none |
| 37 | monsters.md §7: nothing links the UndeadKnight handle +0x3c8 except the unreferenced 0x2b5370 | +0x3c8 | `handle_clear` and `handle_link` at 0x2b5390 / 0x2b53a0 in that function only | stands | none |
| 38 | ui.md P4: the only writes to a player object's flag word from the UI range are in `hud_onMsg` | object reached through record +0x43d8 | no store through such a pointer by presentation-only code in the range; outside it, only `jumpgate_travelEffect` (row 34) | stands | none |
| 39 | arena-entry.md: the record bytes known to be per machine are +0xed, +0xee, +0x4a58, +0x4a5c | record table | presentation-only stores into the record during play: +0xed, +0xee (`menu_openInventory`, `stats_screen`), +0x4a58 (`inventory_drawPlayerModel` 0x1c0a48, `menu_openInventory`), and the dead wipe of +0x43f0…+0x4433 (section 6.1) | stands | see 6.1 |

### 4.3 Statements checked mechanically only

For every sentence in the area and specification documents that has an offset followed by
a "no reader / no writer / written only / read only by" phrase and stands under a heading
naming a class (27 sentences in 22 documents), the class's own functions were searched with
the new tool for a certain access of the opposite kind that the old tool lacked. 24 gave
none; 2 gave hits that reading showed to be another offset of the sentence
(monsters-2.md, the Mummy weapon holder; skills-35-68.md, an ability record); 1 had no
class. This checks only the class's own functions and only the 27 sentences the pattern
caught; it is not an audit of those documents.

## 5. Corrections for the documents

1. **sync-breakers.md §5 (jump gates)** — creature +0xf0 is also read by `Creature_draw`
   and by `Player_run` 0x1a66f0 (action state 0xc: a `LightEffect` is created when +0xf0
   is 30 frames old). Add to FINDINGS D15/D16: the old ability path also reads +0xf0.
2. **prediction-copy.md §3.2, scavenger row** — replace the reason: bit 63 is the "active"
   bit and is set on players; what keeps the copy out is AI state 0x14 at +0x232, which
   no Player code stores.
3. **creatures.md, status counters** — "no code in this range sets a counter to a non-zero
   value"; the range does write them (0x10b8d4, 0x113744, 0x113758).
4. **FINDINGS E11** — "nothing else reads the bit" → "its only other reader is the script
   creature-flag helper 0x1445fc, which resets the boss meter" (as `creatures.md` C3).
5. **FINDINGS G2** — add the five handles at +0x3d8 + 0x18·n and the object's own heads +4, +8.
6. **FINDINGS D14 / D15** — add the reader `UnholyAura_run` 0x2949bc (counter 12), the
   setters `Player_run` 0x1abda0 (counter 11) and `OniBall_onTouch` 0x294800 / 0x294844
   (counters 8, 10), and the zero stores 0x1a5b0c, 0x1ac068, 0x113744, 0x113758.
7. **FINDINGS SB2 / K3** — four more readers of record +0xd0 / +0xd4 (row 23).
8. **FINDINGS "Ruled out" and objects.md, flag 0x100** — also set by
   `Player_processDamage` 0x1b336c.
9. **pose-cache.md §2** — the list of direct track-field stores (row 30).
10. **FINDINGS "Tools added" and "Audit of reader and writer lists"** — the two tools are
    rewritten; `ghostreach.py`'s list of record writers is incomplete (6.3).

## 6. New desync candidates (step 4)

Method: (a) every store into the static player record table, with the function classified
by `tools/drawsim.py` (presentation only; reached by the prediction copy; simulation), and
the simulation readers of the same bytes; (b) every store through a pointer loaded from
record +0x43d8 (the player object) by presentation-only code; (c) the newly found accesses
of section 4. Not chased to the end.

### 6.1 Presentation code writes, simulation reads

| What | Where | Finding |
|---|---|---|
| **Record +0x43f0…+0x4433, the 17 equipped-item words** | `inventory_drawPlayerModel` 0x1c0920: counter 0x41b514 is incremented on each draw while non-zero (0x1c0d48); when it reaches 279 a loop zeroes the 17 words (0x1c0d54–0x1c0d80). The counter is started (0x1c0e00) only when record byte +0x4a86 is 5, record word +0x50 is 0, two bits (0x400, 0x200) of an entry of the table at 0x4028d8 are set (what the table is was not established) and **global 0x44f070 is non-zero** | The words are read by `Player_meleeHit`, `Player_regenHealth`, `Player_regenMana`, `Player_run`, `Player_weaponSwapInput`, `player_canBlock` and the axe and bash skills, and are exactly the range 0x43f0–0x4433 that `player_checksum` sums. **Dead as shipped**: 0x44f070 is 0 in the file, has this one reader, no store and no data word pointing at it. Latent: anything that sets that word on one machine (a cheat device, a debug build) strips that character's equipment on that machine only |
| Creature +0xf0 | `jumpgate_travelEffect` 0x27ead0 (draw task) writes; `Player_run` 0x1a66f0 reads | row 33: object creation on a per-machine frame, only in action state 0xc (D16) |
| Record +0xd0 / +0xd4 | `stats_screen` → `Player_recalcDamage` (K3) writes | four more simulation readers (row 23). K3's patch removes the cause |
| Record +0xe4 (gold) | `hud_tickGold` 0x1dcc54 and `hud_run` 0x1dbbbc, in the HUD run task | known (ui.md): timed by the frame counter only |
| Record +0xed, +0xee, +0x4a58 | `menu_openInventory`, `stats_screen`, `inventory_drawPlayerModel` | known per-machine bytes; no simulation reader found |
| Player object fields | `jumpgate_travelEffect` only (row 34) | known (sync-breakers.md), except the skeleton query |

### 6.2 Counter 12 and the aura object

`UnholyAura_run` 0x2949bc (a run function) reads its owner's status counter 12. Counter 12
is not decremented by drawing, and while it is the first non-zero counter drawing
decrements nothing after it either (D12), so no per-machine value reaches the read. Listed
because the row that names the readers of the counters does not have it.

### 6.3 Code that runs for the prediction copy

No new candidate. The sweep lists record stores by functions the copy can reach that
`tools/ghostreach.py` does not print, because they are indexed stores:
`Player_regenHealth` (+0xac, +0xb4), `Player_regenMana` (+0xc0, +0xc8), `Player_takeDamage`
(+0xc0), `Player_usePotion` (+0x2544), `OniBall_onTouch` (+0xb4, +0xc8),
`hud_addGoldFloater` (+0xe4), `inventory_giveItem` (+0x130…+0x152, +0x1330, +0x4c25),
`inventory_equipItem` (+0x43f0…+0x443c), and `Player_run`'s own +0x4bc8, +0x4bc9, +0x4bca
and +0x4c27. `Player_regenHealth`, `Player_regenMana`, `Player_usePotion` and
`OniBall_onTouch` contain a test of 0x20000 that the new `flagxref` lists (0x1b3bb8,
0x1b3928, 0x1b9d00, 0x29471c), and `Player_run` has one before each of its stores (0x1ac6b8,
0x1a5338). `Player_takeDamage`, `hud_addGoldFloater`, `inventory_giveItem` and
`inventory_equipItem` have none of their own and depend on their callers, which is how
`prediction-copy.md` argues (from call paths, not from that tool). Whether each test guards
each store, and each caller is guarded, was **not re-read here**. "The player-record writers in that set have been read"
in the ledger's tool paragraph should be read with this list in mind.

## 7. What the tools still cannot see

Section 2.3, and for this audit in particular:

- A verdict "stands" for a field of a heap object means: no access by the new forms in the
  class's own functions, and none in other functions that reading tied to that class. An
  access through a pointer the pass cannot type (loaded from a table, returned by a call)
  in a function of another class is listed by the tool but was read only where a row
  above names it.
- Virtual calls are not followed by the "inside a callee" step, and jump tables are not
  read.
- `--blocks` did not show any block copy or fill of a creature or player object with a
  constant length apart from the pool's own zero fill; a computed length would not show.

## 8. Not done

- The object-flag table of `objects.md` row by row (only 0x100, 0x20000 and 0x200000 were
  audited; the other bits are in the measurement of 3.2 only).
- FINDINGS D37 (weapon holder effect block), K7 (level bytes +0x58 / +0x59), the pad-field
  rows (G5's "+0x00–0x07 and +0x24", netcode.md row 1a, draw-sim-leaks.md on other
  pad-pointer users), ST5's equality keys (they rest on `tools/rawptr.py`), and
  prediction-copy.md's statement about the inert bits at +0x231 (its writers are listed by
  the tool: `Creature_ctor`, `Creature_loadState`, `Creature_setWaiting`, `Creature_show`,
  `Creature_hide`, `Creature_freeze`, and the two freeze helpers; not read).
- The per-class field tables of `monsters.md`, `monsters-2.md` and the three skill
  specifications beyond the mechanical sweep of 4.3.
- The skeleton query that `jumpgate_travelEffect` makes from a draw task (row 34) against
  the pose-cache rules.
- Whether each copy test guards each record store in the list of 6.3.
- `tools/ghostreach.py` and `tools/drawsim.py` were not changed; both still use their own
  trackers.
