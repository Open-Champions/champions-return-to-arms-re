# Native build: closing the gaps in the proof

What this file is about: `docs/issues/native-recomp.md` shows that the game's code,
translated to C++ (`tools/recomp/`), computes what the original computes — function by
function against the interpreter `tools/ee_emu.py`, and in play against the original in
the emulator rig. It left four gaps: two differences against the rig that were found and
not explained, 301 functions the function-by-function test could not drive, no count of
which code the compared play actually ran, and no test of the arithmetic helpers on
corner cases. This file closes them as far as stated below.

Conventions as in `native-recomp.md`: **Ran** = executed and measured here; **Read** =
taken from reading code; **Inferred** = a reading that fits the measurements and was not
itself measured; **Not reached** = not done. Everything was run headless on 2026-10-12 on
an Apple-silicon Mac that other jobs kept at a load average of 300–500, which is why the
rig figures are slow.

## Status

(kept current; last update 2026-10-12 16:35)

| Part | State |
|---|---|
| 1. The two differences against the rig | both located to the byte, the writing code and the cause: disc-read completion time, and which sound-sequence slot was free; both measured on both machines; neither is a translation error |
| 2. The 301 functions without a comparable case | method built; one session replayed: **49 of the 301 identical to their return on real inputs, 6 more identical up to a common stop, 0 different**, 25 entered but not comparable (they wait), 221 not entered by that session. The states of five tours are recorded (942 states) and not replayed yet |
| 3. Coverage of play | **2,660 of 7,732 functions (34.4 %)** reached by sessions that were compared with the rig tick for tick (the fight and five class tours of 13 levels each, 47,565 ticks). Two tours agree in every simulation column at every tick (18,872 ticks, 26 levels), a third in all but 122 ticks of the pool checksum in one level; two do not, for reasons located or being located (3c). Three more rig runs in progress. The set has not stopped growing |
| 4. Arithmetic corner cases | FPU: 24 instructions × 1,980,400 operand sets, **0 differences** in both builds; host model against the rig itself: 0 differences with flush-to-zero, and **one runtime gap found** (the runtime does not set flush-to-zero). Integer/multiply/divide/multimedia: 156 instruction words × 250,000 sets, **0 differences**. Vector unit 0: 225 instruction forms, 21,000,000 lane results in each of two modes, **0 differences** |

## Tools added (all in `tools/recomp/proof/`, outputs under `local/recomp-out/proof/`)

Nothing under `tools/recomp/rt`, `render`, `sound`, `app`, `net` and nothing in
`recomp.py`, `build.py`, `difftest.py` or `rigcompare.py` was changed.

| File | What it does |
|---|---|
| `cmp.py` | `rigcompare.py` with an output directory per run, a choice of native binary, extra watch columns and extra arguments for the native run |
| `instrument.py`, `proof.h.in` | a copy of the generated translation with one line added at every entry point: `PROOF_ENTER(n)` |
| `proof_rt.cpp` | what that line calls, linked into a build of the unchanged runtime (`bin/rta_proof`): a counter per entry point; the machine state at a function's entry (registers and all memory, pages stored once); a write-watch that reports the two points of execution between which watched bytes changed; memory dumps and memory writes keyed on level episode and tick |
| `build_proof.py` | translate, instrument, build `rta_proof` and `proof_driver` in directories of their own |
| `proof_driver.cpp` | `rt/test_driver.cpp` with recorded states as input |
| `realproof.py` | the function-by-function comparison on recorded states (part 2) |
| `tour.py`, `session.py` | scripted sessions: class, character, a list of levels, seeded play; rig run, native run on the rig's controller bytes and memory writes, comparison (part 3) |
| `coverage.py` | adds the counters of several runs up against the function table (part 3) |
| `arith.py`, `arith_main.cpp`, `softf.py`, `rigarith.py` | the arithmetic tests (part 4) |

The instrumented build was checked to be the same program: on the fight session it gives
the same 27 columns at every tick as the plain build, including the two differences below
at the same ticks (**Ran**).

## 1. The two differences against the rig

### 1a. One tick of the player record in the first level (hub tick 7)

**The bytes (Ran).** Both machines were run again with the 256 record bytes logged as a
column. Six bytes differ, in one row: the upper halves of three floats at record +0x4a88,
+0x4a98 and +0x4aa8, which are 0.0 on the rig and 1.0 in the native build at tick 7 and
1.0 on both from tick 8 on. They are the diagonal of a 3×4 matrix at the head of the main
weapon's trail state (`docs/player.md`, +0x4a88).

**The writer (Ran, native write-watch).** The three words change between the return of
the call at 0x1f6e00 (`mat34_setIdentity`) and the return to 0x1bc964: the store is in
`fx_modelStatusEffects` 0x1f6ac8, called from `Player_weaponTrails` 0x1bc768 with the
trail state as its third argument.

**The cause (Ran).** `fx_modelStatusEffects` returns at once while its model argument is
null (0x1f6b70). `Player_weaponTrails` gets that argument from `eqcache_lookupModel`
0x1a2d48, which answers null until the weapon's model has arrived from the disc. Logged
on both machines in one more run:

| Tick (hub) | Equipment-cache record of slot 0 (0x866388) holds the model | Trail matrix written |
|---|---|---|
| 6 | native: yes — rig: no | neither |
| 7 | both | native: yes — rig: no |
| 8 | both | both |

So the matrix is written one tick after the model is there, on both machines, and the
model is there one tick earlier in the native build. Moving the native build's disc
timing moves the write with it: default timing — written in tick 6; `--emulator-timing`
(the delays Play! applies) — in tick 8; the rig — in tick 7. It is the completion time of
an asynchronous disc read, counted in ticks.

**Can it reach the sync hash? (Read)** The sync hash covers the shared seed and the
player positions (`docs/netcode.md`, row 14). The 0x30 matrix bytes are read and written
only by `fx_modelStatusEffects` (`tools/fieldxref.py` over record +0x4a88–+0x4b07: the
other hits are `Player_meleeHit` storing the hit material and timer at +0x4ac5/+0x4ac6
and `player_importCharacter` copying the block), which emits particles and draws from the
cosmetic generator. The cosmetic seed was identical on both machines at every hub tick of
that run, so the first call drew nothing. Not sync-hash material; on two consoles the
same one-tick spread would exist whenever their drives differ.

### 1b. Twenty-seven ticks of the object pool in the fight (valor, ticks 3886–3912)

**The bytes (Ran).** The rig run was repeated twice: once with the pool logged as 232
checksums of 4 KB (one chunk differs, 0x6c88c0–0x6c98bf, at exactly the 27 ticks), once
with that chunk logged in full. One 32-bit word differs: **the player object's +0x00**,
the head of its "who refers to me" handle list (`docs/objects.md`). The two machines hold
different handle nodes there (0x84a404 and 0x84a4cc, nodes of `g_handleNodes`):

| Ticks | rig | native |
|---|---|---|
| 3830–3885 | 0x84a4cc | 0x84a4cc |
| 3886–3888 | 0x84a404 | 0x84a4cc |
| 3889–3912 | 0x84a4cc | 0x84a404 |
| 3913–3934 | 0x84a404 | 0x84a404 |

Position, facing, state, both seeds' simulation side, hit points and every other byte of
the 947,968-byte pool are identical through the window.

**The writer (Ran, native write-watch on the four bytes, ticks 3820–3940).** Every change
of the word lies between the entry of `handle_clear` 0x1a1698 and the return to 0x214324,
or between the entry of `handle_link` 0x1a1738 and the return to 0x214334: both calls are
in `sound_playOnObject` 0x214230, which picks one of the 32 sound-sequence slots
(`g_soundSeqs`), clears the slot's handle and links it to the object the sound is to
follow. Nothing else wrote the word in those 120 ticks.

**The cause (Ran).** The fight was run once more on both machines with the 32 slots
(2,432 bytes at `g_soundSeqs`) logged in full:

- The slots differ between the machines at 854 of the 3,978 ticks compared, first at tick
  1,522 — while every simulation column is identical. The bytes that differ are the
  slots' time counters (+8 to +10) and track flags (+32, +34): where each sound is in its
  life. That follows the sound driver, which is `sound_null.cpp` here and the emulator's
  sound processor on the rig.
- In the window: slot 30 holds a handle to the player on both machines throughout. Slot
  31 holds one from tick 3886 on the rig and from tick 3889 in the native build; and the
  native build re-links slot 30 at tick 3885, the rig at tick 3888. The same two sounds
  are started on the player on both machines, in the two slots the other way round,
  because the slots were in different states when the first was asked for. From tick 3889
  both machines hold the same two handles in opposite list order, and at tick 3912/3913
  the next re-link puts the same node at the head on both.

So the difference is the order of two back links, set by which sound-sequence slot was
free on each machine. With `--emulator-timing` (which changes when the I/O processor's
answers arrive, not what the sound driver answers) the window is the same 27 ticks.

**Can it reach the sync hash? (Read)** Not through this word: the handle list is a list
of back links, walked when the object is deleted and when a handle is cleared; no code
found orders anything by it. Two things were **not** audited: every caller's use of
`sound_playOnObject`'s return value (a handle, or −1 when no slot is free), and whether
a different order of handle-node allocation can change simulation state anywhere (node
addresses differ, the nodes' contents do not). On two consoles the sound hardware is the
same, so the question only arises between unlike machines.

## 2. The 301 functions without a comparable case

### Why the interpreter stops on them (Ran: read off the sweep's report)

`realproof.py want` reads `local/recomp-out/sweep-stub.txt` (the stub-mode sweep, twelve
synthetic inputs per function) and lists the functions with no run that reached the
return: 301, plus 40 whose only comparable runs end at an instruction both sides stop at.
By what stopped the interpreter in most of a function's twelve runs:

| Reason on synthetic inputs | Functions |
|---|---|
| step limit of 100,000: a loop that waits for something an interrupt or the I/O processor would do, or a long loop over made-up data (a string copy without an end, a list that points into itself) | 143 |
| wild pointer: an access outside the 32 MB through a made-up pointer | 109 |
| unaligned access through a made-up pointer (the interpreter refuses it, as the CPU would) | 40 |
| an instruction the interpreter does not implement (vector unit, some COP0) | 6 |
| a jump to address 0 or out of the code through a made-up function pointer | 3 |

No function of the 301 stops on a system call or `BREAK` alone; the 40 "partial" ones are
those (their runs end at a `BREAK`, a vector-unit instruction or a trap on both sides).

### Method: real inputs (Ran)

The instrumented runtime records, at a function's entry in the running game, the whole
register context and all of memory (`--opt proof-capture`; its 1st, 2nd and 5th call per
session; memory as 4 KB pages stored once, about 20,000 pages for 168 states).
`realproof.py replay` runs each recorded state to the function's return in the
interpreter and in the translation (`proof_driver`, the test build of the plain
translation) and compares what `difftest.py` compares — all general registers at 128
bits, HI/LO and the second pair, the shift amount, the FPU registers, accumulator and
compare bit, every call with its eight integer and eight float argument registers — and
**every byte of memory**: all 32 MB, the scratchpad and any other page touched (not only
the pages a write log names). Each state is tried with callees running (the whole call
tree is compared); when the interpreter does not reach the return within a million
instructions, again with every call replaced by "return 0" on both sides. On both sides a
system call returns 0, the mirrors of main memory fold as `rt/runtime.cpp` folds them,
and hardware registers are plain memory that starts at zero.

### Result so far (Ran: one session — boot, first level, the fight in valor)

168 states of 82 functions were recorded (80 of the 301, 2 of the 40).

| Of the 301 | Functions |
|---|---|
| identical to the return, callees running | 42 |
| identical to the return, calls replaced | 7 |
| identical up to an instruction both sides stop at (first vector-unit instruction, `BREAK`) | 6 |
| entered, not comparable: neither side returns (they wait for an interrupt or an I/O answer: `gfx_waitVsync`, `iop_loadModules`, `scePadInit`, `sceMtapInit`, `lgAudInit`, `engine_init`, the session loop …); the calls made up to the limit agree on both sides | 25 |
| not entered by this session | 221 |
| **different** | **0** |

Of the 40 partial ones: 2 entered (again identical up to the stop), 38 not entered.

A first run reported 6 differences; all six were the test driver folding the 0x30000000
mirror with the wrong mask (`proof_driver.cpp`, fixed), none was the translation.

Not yet done: the states of the tours (part 3) — each `session.py NAME native --capture`
records them, `realproof.py replay local/recomp-out/proof/real/NAME` compares them, and
`realproof.py report DIR... --hits FILE... --list` prints this table over all sessions
with, for every function still without a state, how many calls, jumps and data words of
the executable name it (20 of the 221 are named by none: candidates for dead code, the
list is printed by that command).

## 3. Coverage of the comparison in play

### The counter (Ran)

`instrument.py` adds one line at each of the 12,147 entry points of the generated code;
7,732 of them are the first instructions of the functions of `ghidra_funcs.tsv` (nine of
those are labels inside another function's body and are counted at the label). A run of
`bin/rta_proof` with `--opt proof-hits=FILE` writes how often each was reached;
`coverage.py` adds runs up.

### 3a. Sessions compared with the rig (Ran)

Each session: `session.py NAME rig`, `native`, then `summary.py NAME`. Rows are matched
on level episode and tick as in `rigcompare.py`; 29 columns (rigcompare's 27 and
checksums of the 32 sound slots and of the equipment cache).

| Session | Levels | Ticks compared | Result | Functions reached | New | Total |
|---|---|---|---|---|---|---|
| fight (class 6 as created) | start-up, front end, first level, valor | 5,010 in valor | identical but for 1a and 1b | 1,839 | 1,839 | 1,839 |
| `s6` class 6 | 13 + first level twice | 9,916 | **every simulation column identical at every tick** except: the pool at 122 ticks of the last level (not located), 1a | 2,048 | 259 | 2,098 |
| `s5` class 5 | 13 | 9,916 | positions, seeds, state, hit points, statistics, bag, equipment, abilities, skills identical at every tick; the whole-record checksum differs from the second level on (being located, 3c) | 2,175 | 243 | 2,341 |
| `s0` class 0 | 13 | 10,016 | **identical at every tick** (two ticks of 1a) | 1,906 | 36 | 2,377 |
| `s1` class 1 | 13 | 8,856 | **identical at every tick** (one tick of 1a) | 2,054 | 77 | 2,454 |
| `s3` class 3 | 13 | 8,861 | identical for the first level and the first tour level; then the game itself changed level in mid-play and the two runs part at the first tick of the new level (3c) | 2,255 | 206 | 2,660 |

"Identical" leaves out what is not expected to agree — the displayed-frame counter, the
cosmetic seed, the controller checksum, the sound-slot and equipment-cache checksums
(part 1) — and the "write rows" explained in 3b.

**2,660 of 7,732 functions (34.4 %)**, 2,682 of 12,147 entry points. Each tour still adds
functions (36 to 259), so the set has **not** stopped growing. Native-only runs of the
same tours with other seeds and of a 1,500-tick walk through the first level and its twin
reach 2,602 together with the fight; their union with the above was not taken.

The tours (`tour.py`): the class is chosen on the character-creation screen (the number
of presses per class was measured: the screen turns through twelve models); in the first
level the character is given level 25, large statistics and every active skill of its
class at rank 10 by memory writes; then, per level, the game's own level-change request,
seeded random walking, striking, blocking and casting, the two ability buttons moving on
to the next two skills every 96 ticks, and in one level per tour hit points written to
almost nothing (no tour character died of it: nothing hit it in time). Seven tours are
defined (`local/recomp-out/proof/sessions.json`: classes 0–6, 92 levels between them,
among them the two boss levels, the medal and bonus levels, the arenas and the three
cutscene levels); `s4`, `s2` and the walk `h6` are running in the rig.

### 3b. What it took to compare a session with memory writes and many levels (Ran)

1. **A scripted memory write lands at a vertical blank, and the blank falls anywhere in a
   frame.** The script announces each group of writes (`echo @P n`), the rig prints the
   frame it ran them in, and the native run applies the same bytes at that row of the tick
   log (`--opt proof-pokes`) instead of running them from the script. A write that ends a
   level is applied after the level's last row, so both machines leave after the same
   tick (all 70 level changes of the five tours did). Any other write is applied one row
   later than the rig's log first shows it: the columns it touches then differ for that
   one row ("write rows": 1 for the character, 5 per level for the ability buttons and
   mana, up to 3 for hit points) and nothing after it. Applied a row earlier they agree in
   that row, but the simulation step of that tick sees the write in the native run and
   not on the rig, and a hit-point write then leaves a constant offset for the rest of
   the session (seen, and the reason for the choice).
2. **The noise table.** `engine_init` 0x19d19c seeds the cosmetic generator from the CPU
   cycle counter (0x19d1e0) and `math_buildNoiseTable` 0x1646c8 fills `g_noiseTable` from
   it; `Torch_run` 0x2b2088 takes a torch's light radius and position from the table
   (`math_noise` 0x166b48) and stores them in the torch object (+0x68 to +0x84), which is
   in the pool. With different counter values the pool therefore differs at every tick of
   every level that has a torch (seen in three of the first tour's levels: 14 words in
   two objects in a memory image taken on both machines at the same tick; writer found
   with the write-watch). The rig's log shows the seed only after start-up has drawn from
   it, but each draw is a step of a linear generator, so the logged seed is
   a·counter + b mod 2³²: two short native runs with the counter forced to 0 and 1 give a
   and b, the rig's seed gives its counter (0x002a3038 in every run of these scripts), and
   the native run is given it (`--count-at 19d1e0=…`; `session.py` does all of it). After
   that the three levels are identical in every pool byte at every tick.
3. **Memory images at the same tick on both machines.** The rig dumps memory inside its
   tick hook when a script write arms it (`ontick 77 dump …`, `poke 0x4027ac:s32 77`);
   the native run dumps at the row of the same episode and tick (`--opt proof-dump`);
   `rigcompare.py memdiff --a … --b …` compares. This is what located the torches.

### 3c. Differences in the tours, and where they come from

| Where | What differs | Cause |
|---|---|---|
| every tour, first level, tick 7 (class 5 and 0: ticks 7–8) | player record | 1a |
| `s6`, last level (boss), ticks 453–578 | object pool, 122 ticks | **not located** (the pool differs, no other column does) |
| `s5`, from tick 2 of the first tour level to the end | whole-record checksum; from the twelfth level on also the pool | **being located** (a memory image pair of that level is being made); hit points, mana, statistics, bag, equipment, abilities and skills are identical, so it is a record byte outside those |
| `s3`, second tour level onward | position from tick 1 of a level the game itself entered (through an exit, in mid-play), seeds 430 ticks later, then record and pool for the rest of the session | **the controller replay, not the game** (Ran): at the first tick of a level the native run is handed the controller bytes of the rig's row before (native tick 1: the rig's tick-0 bytes; equal from tick 2). When a level starts with the stick neutral — all level changes the script makes — this cannot matter; here the stick was held and a button pressed, and the character moved differently in tick 1. The replay is `--opt pad-replay` in `rt/iop.cpp`; reported, not changed |

### Not reached, by area (Ran: the 2,602 against the symbol files' areas, after the first three sessions)

Largest unreached blocks: the libraries above 0x34e000 (SDK, network stack, lobby API:
1,328 of 1,551 functions never entered — offline play cannot reach most of them), the
C/C++ runtime and the virtual-table default slots above 0x3a7000 (1,349 of 1,553), the
lobby and network-session client at 0x322000 (418 of 437), monsters (734 of 891 after
three sessions) and skills and spells (637 of 983). `coverage.py … --areas --list FILE`
prints the table and the list for whatever runs it is given.

**Not reached at all:** shops, the workshop, saving at a save point, a level-up by
experience. Each needs the character walked to an object (as `pilot.py` does for a
creature), and a native run costs two minutes under today's load because it boots from
power-on every time.

## 4. Arithmetic corner cases

The translated code does its arithmetic through `rt/fpu.h` (two models: `-DFPU_PS2`, the
interpreter's, used by the function-by-function proof; and the default 'host' model, used
by the runtime because it is what the emulator computes), `rt/mmi.h`, the multiply/divide
helpers of `rt/recomp.h`, and `rt/vu0.h`. `tools/recomp/proof/arith.py` tests them one
instruction at a time. Every instruction is compiled from the C++ text `recomp.py` itself
emits for that instruction word (`arith_gen.cpp`, generated), so the translator's choice
of helper and operand order is tested with the helper.

### 4a. FPU instructions (Ran)

All 24 FPU instruction forms the executable contains, 1,980,400 operand sets each
(47.5 million in all): the product of 480 edge patterns with itself (zeroes; denormals;
exponents 1, 2, 23–25, 126–129, 150–159, 253, 254; exponent 255 with ten mantissas, i.e.
every infinity and NaN shape; mantissas 0, 1, 2, all ones, alternating), then seven seeded
sets of 250,000: uniform bit patterns; exponents within 30 of each other; pairs that
cancel to within three units of the last place; products and quotients within three
exponents of overflow and of underflow; denormal operands; infinity and NaN patterns;
whole numbers and integers read as floats.

| Comparison | Operand sets | Different |
|---|---|---|
| **A.** `-DFPU_PS2` build against the interpreter (`ee_emu.py`, model `ps2`): result register, accumulator, compare bit | 24 × 1,980,400 | **0** |
| **B.** runtime build ('host' model) against `softf.py`, denormals kept (how the runtime's threads run today) | 24 × 1,980,400 | **0** |
| **B′.** runtime build with the CPU's flush-to-zero mode set, against `softf.py` with flush-to-zero (how the emulator runs the game) | 24 × 1,980,400 | **0** |

`softf.py` is a description of the host model written for this test in integer
arithmetic only: operands clamped to ±FLT_MAX, the IEEE operation rounded toward zero
(overflow gives ±FLT_MAX, never infinity), divide and reciprocal square root by a zero
exponent give ±FLT_MAX, multiply-add as two rounded operations, conversion saturating with
NaN → 0. That B and B′ are zero means the compiler flags hold (no fused multiply-add, the
rounding mode honoured, nothing folded at compile time) and the special cases in `fpu.h`
are what the header says.

Where the two models differ from each other is not an error, it is the difference
between the emulator's arithmetic and the interpreter's console model; counted over the
same sets (host model without flush-to-zero against the interpreter):

| Cause | Results that differ |
|---|---|
| an operand with exponent 255 — the host model clamps it to FLT_MAX first, the console model computes with it | 4,704,020 |
| a denormal operand — zero in the console model, a number for a host that keeps denormals | 2,744,765 |
| last bit — the console model's adder keeps six guard bits, IEEE truncation the exact sum | 2,649,202 |
| overflow — 0x7fffffff in the console model, FLT_MAX on the host | 1,644,001 |
| underflow — zero below the smallest normal number, a denormal on the host | 258,522 |
| other (compositions of the above in `rsqrt` and multiply-add) | 84,650 |

No instruction differs in any other way: `abs`, `neg`, `mov`, `c.f` and `cvt.s.w` agree
on every set; `cvt.w.s` differs only on NaN patterns (exponent 255 with a non-zero
mantissa: the console model saturates, the host gives 0).

### 4b. The host model against the emulator itself (Ran) — and one gap in the runtime

`rigarith.py` writes a small routine and 128 edge patterns into unused memory of a saved
rig state and makes `gfx_beginFrame` jump to it once: the emulator's own translation of
each instruction then computes all 128 × 128 pairs in the game's thread. The dump is
compared with `fpu.h`'s host model built as the runtime builds it.

| Instruction | pairs | differ, flush-to-zero set | differ, denormals kept |
|---|---|---|---|
| add.s | 16,384 | 0 | 1,510 |
| sub.s | 16,384 | 0 | 1,510 |
| mul.s | 16,384 | 0 | 1,892 |
| div.s | 16,384 | 0 | 1,508 |
| sqrt.s | 16,384 | 0 | 1,280 |
| rsqrt.s | 16,384 | 0 | 596 |
| max.s | 16,384 | 0 | 1,240 |
| min.s | 16,384 | 0 | 1,320 |
| abs.s, neg.s, cvt.w.s, cvt.s.w | 4 × 16,384 | 0 | 0 |
| c.eq.s | 16,384 | 0 | 130 |
| c.lt.s | 16,384 | 0 | 65 |
| c.le.s | 16,384 | 0 | 65 |

So on these inputs `fpu.h`'s host model **is** the emulator's arithmetic, bit for bit,
including the clamping of exponent-255 operands, overflow and division by zero — provided
the thread runs with flush-to-zero. It does not today:

**Finding (runtime, not translation).** The Play! emulator starts its machine thread
with `fesetround(FE_TOWARDZERO)` and `FpUtils::SetDenormalHandlingMode()` (`PS2VM.cpp`,
`CPS2VM::EmuThread`; on ARM64 that sets FPCR.FZ, on x86 the DAZ and FTZ bits) (**Read**).
`rt/runtime.cpp` (`thread_main`) calls only `fesetround`. With denormals kept, a denormal
operand is a number instead of zero and a result below the smallest normal number is a
denormal instead of zero: `add.s` 0 + 0x00000001 gives 0 on the rig and 0x00000001 here;
`c.eq.s` 0, 0x00000001 is true on the rig and false here; and because rounding is toward
zero, adding a negative denormal to a positive number lowers its last bit
(0xb40531e5 + 0x004e3b21 gives 0xb40531e4 here and 0xb40531e5 with flush-to-zero)
(**Ran**). In the 47.5 million directed sets flush-to-zero changes 118,000–282,000
results per arithmetic instruction and 33,000–67,000 per compare (column "fz changes" of
`local/recomp-out/proof/arith/fpu.txt`).

None of the sessions compared so far shows it — no compared value met a denormal — but a
value that decays toward zero does reach the denormal range, and from there the two
machines would compute different numbers, positions included. The fix was sent to the
runtime's keeper and is not applied by this work: next to `fesetround` in `thread_main`,
set FPCR bit 24 on ARM64 (`mrs`/`orr`/`msr`) and `_MM_SET_DENORMALS_ZERO_MODE` +
`_MM_SET_FLUSH_ZERO_MODE` on x86-64; `vu0.h` uses host floats and is covered by the same
setting.

### 4c. Integer, multiply/divide and multimedia instructions (Ran)

156 instruction words against the interpreter, 250,000 operand sets each (39 million):
the 33 multimedia operations of `rt/mmi.h` (the parallel shifts at six shift amounts),
`MULT`/`MULTU`/`DIV`/`DIVU` and their second-pair forms, `MADD`/`MADDU`, `PLZCW`, the
HI/LO moves, the 32- and 64-bit shifts at four amounts and by register, the conditional
moves, set-on-less-than and the logical and wrapping arithmetic instructions. Operands:
128-bit values whose lanes (8, 16, 32 or 64 bits) are edge values (0, 1, −1, the largest
and smallest signed, the saturation boundaries) or random; for multiply and divide also
zero divisors, the most negative number by −1, and register contents that are not
sign-extended 32-bit values. Compared: the 128-bit destination, HI, LO, HI1, LO1.

**0 different in 39,000,000.**

### 4d. Vector unit 0 (Ran)

The interpreter has no vector unit, so `rt/vu0.h` is tested against `softf.py`: every
upper-instruction form the header implements — add, subtract, multiply, multiply-add and
multiply-subtract with a register, a broadcast field or the I register, to a register or
to the accumulator; maximum and minimum; the four fixed-point conversions each way;
absolute value — 225 forms with three destination masks, one instruction per run of the
header's own microprogram loop, on finite operands (a sixth of them denormal or zero, a
tenth at the largest exponents, a fifth cancelling to within two units of the last
place).

| Mode | Lane results | Different |
|---|---|---|
| denormals kept | 21,000,000 | **0** |
| flush-to-zero set | 21,000,000 | **0** |

Not covered: infinity and NaN operands (they cannot arise from finite operands under
rounding toward zero; they would have to come in as data), the lower instructions (moves,
loads, stores, one branch), and the vector unit against the rig itself. The game's one
vector-unit program runs in every session of part 3 (`anim_buildPose`), where its results
feed the compared state.

## Half-done, and how to resume

State at 16:35 on 2026-10-12. Everything below is under `local/recomp-out/proof/`.

| What | State | To finish |
|---|---|---|
| recorded entry states of the tours `s6`, `s5`, `s0`, `s1`, `s3` (942 states, `real/<name>/`) | recorded, not replayed | `realproof.py replay real/NAME` for each, then `realproof.py report real/* --hits cmp/*/hits.tsv --list` |
| rig runs of `s4`, `s2` (classes 4 and 2) and `h6` (walk in the first level) | running | `session.py NAME native --capture`, `summary.py NAME` |
| the record difference of `s5` | a memory image pair of its first tour level is being made (`cmp/d2/`) | native run with `--opt proof-dump=4:<tick>:FILE` at the tick of the rig's row whose `net` column is 77, then `rigcompare.py memdiff --a cmp/d2/rig-dump.bin --b FILE --words 4d8af0:4dd720` |
| the pool difference in the boss level of `s6` | not started | the same with a script that goes to that level |
| every function one tour reaches, replayed from its first real call (not only the 301) | queued (`chain-all.sh`, output `real/all-s1/`) | `realproof.py report real/all-s1` |

Repeat from nothing:

```
export RTA_DISC="/path/to/your/disc image.iso"
python3 tools/recomp/proof/build_proof.py translate     # recomp.py into gen-proof-src, hook into gen-proof
python3 tools/recomp/proof/build_proof.py runtime       # bin/rta_proof
python3 tools/recomp/proof/build_proof.py driver        # bin/proof_driver
python3 tools/recomp/proof/realproof.py want            # the 301 (+40) from sweep-stub.txt
python3 tools/recomp/proof/session.py s6 rig            # one tour in the rig ...
python3 tools/recomp/proof/session.py s6 native --capture
python3 tools/recomp/proof/session.py s6 compare
python3 tools/recomp/proof/realproof.py replay local/recomp-out/proof/real/s6
python3 tools/recomp/proof/realproof.py report local/recomp-out/proof/real/* --hits local/recomp-out/proof/cmp/s6/hits.tsv --list
python3 tools/recomp/proof/coverage.py --sessions s6,s5,s0 --areas
python3 tools/recomp/proof/arith.py build && python3 tools/recomp/proof/arith.py fpu && python3 tools/recomp/proof/arith.py int && python3 tools/recomp/proof/arith.py vu
python3 tools/recomp/proof/rigarith.py                  # needs local/rig-out/states/04-hub.zip
```

## What remains unproven

(as of 16:35; to be rewritten at the end)

- **252 of the 301 functions** have no identical comparable case yet: 221 were not
  entered by the one session replayed (the five tours' states are recorded and not yet
  replayed), 25 wait for an interrupt or an I/O answer and cannot return in isolation, 6
  are identical only up to their first vector-unit instruction or `BREAK`. None differs.
- **5,072 functions have not run in any compared session.** Most of them cannot run
  offline (network stack, lobby, most of the C++ runtime's default slots); the rest are
  monsters, skills, menus and the save path not visited yet.
- **Two differences in the tours are not explained**: 122 ticks of the pool in the boss
  level of `s6`, and the record checksum of `s5`. In both, every other column agrees.
- **A level the game enters by itself in mid-play** cannot be compared beyond its first
  tick with the controller replay as it is (3c).
- **Flush-to-zero** is missing in the runtime (4b); until it is set, a compared value
  that meets a denormal will differ from the rig.
- **Not reached:** shops, the workshop, saving at a save point, a level-up, a death.
- The function-by-function proof stops at the first vector-unit instruction of
  `anim_buildPose` (the interpreter has no vector unit); what stands for it is 4d and the
  play comparison.
- 1b: that the sound slots' time counters differ *because* the two sound drivers report
  voices ended at different times was not traced into the drivers; the slots and the
  handle order were measured.

## Proposed ledger rows

(as of the save point; counts will move)

| Id | Statement | Status | Where |
|---|---|---|---|
| NP1 | The one-tick difference of the player record at hub tick 7 is the identity matrix of the weapon-trail state, written by `fx_modelStatusEffects` one tick after `eqcache_lookupModel` first returns the weapon's model; the tick depends on when the disc read completes. Cosmetic state | Ran (bytes, writer, both machines' cache record, three timings) | 0x1f6ac8, 0x1bc964, 0x1a2d48, record +0x4a88 |
| NP2 | The 27-tick difference of the object pool in the fight is one word, the player object's handle-list head (+0x00), written by `sound_playOnObject` linking a sound-sequence slot's handle to the object: the same two sounds take the two slots the other way round on the two machines. The 32 slots differ between the machines at 854 of 3,978 ticks with the simulation identical | Ran (bytes, writer, slots on both machines) | 0x214230, 0x1a1698, 0x1a1738, `g_soundSeqs` |
| NP3 | The runtime's threads keep denormals; the emulator flushes them to zero. `rt/fpu.h`'s host model equals the emulator's FPU arithmetic on 15 instructions × 16,384 edge pairs with flush-to-zero set and differs on 65–1,892 pairs per instruction without | Ran | `rt/runtime.cpp` `thread_main`; `tools/recomp/proof/rigarith.py` |
| NP4 | `-DFPU_PS2` arithmetic equals the interpreter's on 24 FPU instructions × 1,980,400 directed operand sets; the host model equals its written reference with and without flush-to-zero on the same sets | Ran | `tools/recomp/proof/arith.py fpu` |
| NP5 | The translation of 156 integer, multiply/divide and multimedia instruction words equals the interpreter on 250,000 operand sets each | Ran | `tools/recomp/proof/arith.py int` |
| NP6 | Of the 301 functions without a comparable synthetic case, 49 are identical to their return on states recorded in the running game (registers, calls, all of memory), 6 more up to a common stop; none differs | Ran (one session) | `tools/recomp/proof/realproof.py` |
| NP7 | Sessions compared with the rig at every tick (a fight and five class tours of 13 levels, 47,565 ticks) reach 2,660 of the 7,732 functions; two tours (18,872 ticks, 26 levels) agree in every simulation column at every tick, a third (9,916 ticks) in all but 122 ticks of the pool checksum | Ran | `tools/recomp/proof/coverage.py`, `summary.py` |
| NP8 | The object pool of a level with a torch differs between two machines at every tick unless they read the same cycle-counter value in `engine_init`: `Torch_run` stores light radius and position taken from the per-boot noise table in the torch object (+0x68–+0x84). With the counter made equal the pools are identical | Ran | 0x19d1e0, 0x1646c8, 0x166b48, 0x2b2088 |
| NP9 | `rt/vu0.h` equals IEEE single precision rounded toward zero on 225 upper-instruction forms × 21,000,000 lane results, with and without flush-to-zero | Ran | `tools/recomp/proof/arith.py vu` |
| NP10 | The controller replay of `rt/iop.cpp` hands the game, at the first tick of a level, the bytes of the rig's row before; a level that starts with input held diverges from the rig at that tick | Ran (one case) | `--opt pad-replay` |

## Working notes

- `RTA_DISC` must be set. Rig runs: `nice -n 19`, at most three at a time here; a rig run
  with the whole-pool checksum column makes 3–9 displayed frames a second under this load
  (the checksum of 948 KB per frame is the larger part), a run resumed from a saved state
  with small columns 20.
- A rig state saved in mid-script (`save`) cannot continue the same run: the script's
  held buttons are not in the state. `cmp/pool/valor3800.state` was made that way and its
  resumed run is a different fight; the full run was repeated instead.
- `local/recomp-out/unproven.txt` (442 lines) is from an earlier sweep and is stale; the
  301 are derived from `sweep-stub.txt` by `realproof.py want`.
