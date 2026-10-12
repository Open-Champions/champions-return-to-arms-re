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

(kept current; last update 2026-10-12 15:40)

| Part | State |
|---|---|
| 1. The two differences against the rig | both located to the byte, the writing code and the cause; neither is a translation error. One runtime gap found on the way (flush-to-zero, part 4) |
| 2. The 301 functions without a comparable case | method built and run on the first session: 49 of the 301 now identical to their return on real inputs, 0 different; the rest in progress |
| 3. Coverage of play | execution counter built; first sessions counted; tours of all classes and 90 levels running against the rig |
| 4. Arithmetic corner cases | FPU done on 244,400 operand sets per instruction (0 differences in both builds against their references) and against the rig itself; the full run (2 million sets per instruction), the integer/multimedia run and the vector-unit run are in progress |

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

**The cause.** Which slot a sound gets, and whether an earlier sound on the same object
still holds its handle, depends on when earlier sounds ended — and that is asked of the
sound driver (the voice-end flags, `native-recomp.md` step 1), which is `sound_null.cpp`
here and the emulator's sound processor on the rig. **Ran:** (to be filled in from the
run with `--emulator-timing`, which changes when sound calls are answered). **Inferred:**
the rest of the chain — that at tick 3885 the rig still had a sound playing on the player
that the native build's driver had already reported ended. The slots themselves were not
logged on the rig for this run; the tours of part 3 log a checksum of all 32 slots on
both machines.

**Can it reach the sync hash? (Read)** Not through this word: the handle list is a list
of back links, walked when the object is deleted and when a handle is cleared; no code
found orders anything by it. Two things were **not** audited: every caller's use of
`sound_playOnObject`'s return value (a handle, or −1 when no slot is free), and whether
a different order of handle-node allocation can change simulation state anywhere (node
addresses differ, the nodes' contents do not). On two consoles the sound hardware is the
same, so the question only arises between unlike machines.

## 2. The 301 functions without a comparable case

(Table of reasons, method, results: below, being filled in.)

## 3. Coverage of the comparison in play

(below, being filled in)

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

### 4c. Integer, multiply/divide and multimedia instructions

(in progress)

### 4d. Vector unit 0

(in progress)

## What remains unproven

(at the end)

## Proposed ledger rows

(at the end)

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
