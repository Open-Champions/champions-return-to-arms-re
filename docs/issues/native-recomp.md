# Native build by static recompilation: feasibility spike

Started 2026-10-11. Question: if the executable's MIPS R5900 code is translated to C++ once
and compiled for the host, does the translated code compute the same game as the original,
tick for tick, and how much platform work stands between that and a playable native
Mac/Windows application?

This file is written as the work proceeds; every section says what was **Ran** (executed
here, with the numbers), what was only **Read**, and what was **Not reached**.

Where things are:

| What | Where | In the repository? |
|---|---|---|
| translator (Python), runtime (C++), tests | `tools/recomp/` | yes — ours |
| generated C++, objects, binaries, logs, dumps | `local/recomp-out/` | no — derived from the game |

Prior art named because ideas were borrowed (nothing was downloaded, no code copied):
**N64Recomp** (one C function per game function, a context struct, a lookup table for
indirect calls, host threads for guest threads) and **PS2Recomp** by ran-j (the same shape
applied to the R5900: 128-bit registers, a runtime that answers syscalls).

## Status

(kept current; see the sections below for evidence)

- Step 1 translator: **done** — all of `.text` translates and compiles.
- Step 2 differential test: **done** — 7,431 of 7,732 functions compared by the automatic
  sweep, 0 failing; 40,991 calls of the reference-model tests replayed, 0 different.
- Step 3 platform boundary and runtime: **a runtime exists that runs the game's frame
  loop headless** (kernel, interrupts, DMA, GS events, VU0, RPC stubs); disc, controller
  input and memory card are not in it yet.
- Step 4 compare with the rig: **done from a resumed session** — 2,005 consecutive frames
  in the hub level, every compared value identical, whole object pool and heap identical
  at the end. Boot from power-on: not reached.
- Step 5 verdict: below.

## Facts about the input (Ran: opcode census over the function table)

- `.text` 0x100000–0x3e5c40; `ghidra_funcs.tsv` has 7,732 functions in 9,979 address
  ranges (814 functions have more than one range, separated by padding words). 329 regions
  of `.text` with non-zero words are in no function range; no `jal` targets them, so they
  are reached through pointers or by falling/branching in from a neighbour. The translator
  must cover them.
- A second loaded segment, `.loadScreenSection`, sits at 0x1800000 (0x118200 bytes).
- `.vutext` 0x3e5c40 (0x3d40 bytes) is vector-unit microcode, not MIPS code.
- Instruction mix inside the function ranges: 82 `SYSCALL`, 181 `BREAK`, 13 COP2
  instructions in all (two `VCALLMS` in `anim_buildPose` 0x16f594/0x16f5f4, the rest
  control-register moves and two `LQC2`), 5 reads of the COP0 cycle counter
  (0x19d1e0, 0x2177b8, 0x218d10, 0x3229f0, 0x322a00), no `CFC1` (so the FPU flag bits
  are never read; only the compare bit matters), FPU arithmetic limited to
  add/sub/mul/div/sqrt/rsqrt/abs/neg/mov/max/min/adda/cvt and three compares, and 33
  distinct multimedia (MMI) operations, all of which `tools/ee_emu.py` implements.
- The two ERX modules on the disc (`LIBINSCK.ERX`, `NG_INSCK.ERX`) are relocatable EE code
  loaded by the network set-up window only; offline play does not need them.

## Step 1 — the translator (Ran)

`tools/recomp/recomp.py` reads the executable and `ghidra_funcs.tsv` and writes C++ to
`local/recomp-out/gen/` (46 files of about 64 KB of game code each, `funcs.h`, `table.cpp`
and `units.tsv`); `tools/recomp/build.py` compiles them with the clang already on the
machine. The generated code is written against `tools/recomp/rt/recomp.h` (context,
memory access, unaligned loads and stores, multiply/divide), `rt/fpu.h` and `rt/mmi.h`.

```
python3 tools/recomp/recomp.py            # 1.5 s
python3 tools/recomp/build.py test        # 35-45 s on 14 jobs (232 s of processor time at -O1)
```

| | |
|---|---|
| instruction slots translated | 757,702 — every word of `.text` that is in a function range or is a non-zero word outside one |
| instructions with no translation | 0 |
| units (C++ function bodies) | 8,056: 7,751 from the 7,732 table rows, 329 "gap" units (55,588 bytes of `.text` in no table row), less 30 that were merged into 6 clusters |
| entries (`fn_<address>` symbols and slots in the call table) | 12,023 |
| units with a computed jump | 240; units with a dispatch switch: 559 |
| C++ files that fail to compile | 0 of 46 |

Design, in the order the task asked:

- **One C++ function per game function.** `void fn_<address>(Ctx*)`. A table row with
  several address ranges is one unit when only padding separates the ranges; a range that
  lies elsewhere becomes a unit of its own, reached by the branch that leads to it.
- **Memory** is one flat 32 MB array; an access outside it goes to the runtime
  (`rt_load`/`rt_store`: mirrors, scratchpad, hardware registers).
- **Registers.** `Ctx` holds the 32 general registers as 128 bits each (two 64-bit arrays:
  bits 0–63 and bits 64–127, the second touched only by the multimedia instructions and
  the 128-bit load/store), HI/LO and the second pair, the shift-amount register, 32 FPU
  registers as raw bit patterns, the accumulator and FCR31.
- **FPU.** Two models (`rt/fpu.h`). `-DFPU_PS2` is the interpreter's default `ps2` model
  in integer arithmetic, exact: no NaN/infinity/denormal, exponent 255 an ordinary number,
  overflow to ±0x7fffffff, underflow to zero, the six-guard-bit adder, truncating
  multiply/divide/square root. The default (`host`) model is what the Play! emulator does
  on an ARM64 host — operands clamped to ±FLT_MAX, the host's IEEE operation with rounding
  toward zero, ±FLT_MAX for division by a zero exponent — because that is the arithmetic
  the headless rig computes the original game with (read in Play!'s `COP_FPU.cpp` and its
  AArch64 code generator; nothing copied). Flag bits are not kept: the executable has no
  `CFC1`.
- **Delay slots** are emitted with their branch: after the condition is computed, before
  the jump; inside the taken arm for "likely" branches. A delay slot that is itself a
  branch target gets a second, labelled copy.
- **Calls.** `jal` is a direct C++ call; `jalr` goes through a table indexed by address
  (`rt_call`). Every address that can be reached from outside its unit is an entry: `jal`
  targets, branches and jumps that leave their unit, fall-through off the end of a unit,
  7,204 distinct data words that hold a `.text` address (function pointers, virtual
  tables, jump tables), 213 addresses formed by `lui`/`addiu` pairs, and the address after
  every return inside a gap unit.
- **Jump tables.** A `jr` through a register other than `$ra` goes to the unit's dispatch
  `switch`, which has a case for every label of the unit; the jump-table targets are
  labels because the tables are data words holding `.text` addresses. A target outside the
  unit is a tail call through the table; a target equal to the return address the unit was
  entered with is a return (the hand-written decompressor returns through `$a1`).
- **Fallback dispatch loop.** Six clusters of functions jump into the middle of one
  another: 0x1a3580–0x1a3f70, 0x255d3c–0x255f7c (a switch whose cases the function table
  puts outside the function), 0x372d48–0x372efc, the hand-written decompressor
  0x3a3620–0x3a404c (14 table rows with private calling conventions), 0x3ad9a8–0x3adb08
  and 0x3adb08–0x3adc30. Each cluster is one unit in which calls between members are
  jumps and every return goes through the dispatch switch.
- `SYSCALL`, `BREAK`, COP0 moves, `ERET` and all COP2 instructions call the runtime.
- An address list (`tools/recomp/hle.txt`, optional) names functions whose `fn_` the
  runtime supplies; the translation is still emitted as `orig_<address>`.

Known limits of the translation scheme (not bugs found, properties of the approach):

- A return does not consult `$ra`. Code that overwrites its own saved return address
  (a buffer overrun on the stack) returns to its caller here and jumps to the garbage
  address on the console; the sweep showed exactly that in 6 cases with random data.
- Code that is not in the executable at translation time cannot run: the two ERX network
  modules, and anything written into memory and jumped to. A call to an address without
  an entry stops the runtime with the address.
- A call through a pointer into the middle of a function that no data word, `lui` pair or
  branch names has no entry. None was met.

## Step 2 — differential test against the interpreter (Ran)

`tools/recomp/difftest.py` runs one function on one prepared input twice — in
`tools/ee_emu.py` and in the compiled translation (`local/recomp-out/bin/recomp_test`,
built with `-DRECOMP_TEST -DFPU_PS2`) — and compares all 31 general registers (both
halves), HI/LO and HI1/LO1, the shift-amount register, 32 FPU registers, the accumulator,
the compare bit, every call made (call site, target, eight integer and eight float
argument registers) and every byte of memory that changed, the stack included.

### Automatic sweep over the whole function table

Six kinds of input per function, two seeds each (12 cases per function): arguments
pointing at zero-filled areas; small integers and game-sized floats; a 16 KB arena filled
with pointers into itself, with floats, with a mix, and with random bytes (the last with
random 128-bit register contents). In **stub** mode every call the function makes is
replaced by "return 0" on both sides (the interpreter's stub-all), so one function's own
translation is compared, including the calls it makes and their arguments. In **follow**
mode callees run, so whole call trees are compared. `SYSCALL` returns 0 on both sides.

| | stub mode | follow mode |
|---|---|---|
| cases | 92,784 | 92,784 |
| interpreter instructions executed | 313,550,815 | 1,025,711,234 |
| cases run to the return and identical | 72,825 | 51,459 |
| cases identical up to an instruction both sides stop at (`BREAK`, COP2, trap) | 501 | 717 |
| cases that differ | **0** | **0** |
| cases the interpreter stops on (not comparable) | 19,458 | 40,608 |
| functions passing (at least one comparable case, all identical) | 7,391 | 5,992 |
| functions identical only up to a common stop | 40 | 58 |
| functions failing | **0** | **0** |
| functions with no comparable case | 301 | 1,682 |

So of the 7,732 functions: **7,732 translate, 7,732 compile, 7,431 were compared and
agree in at least one run (7,391 to their return), none disagrees, 301 are unproven** —
the interpreter stops in every one of their 12 cases, mostly on an unaligned access made
through a synthetic pointer (which the console would trap on too), a wild pointer, or its
step limit of 100,000. Unproven is not failing: the same instruction translations pass
elsewhere 124,284 times.

Not-comparable cases by cause (interpreter / translation), stub mode: unaligned access
11,313; wild pointer on both sides 5,158; step limit 2,846; other 141.

Bugs the sweep found in the translator, all fixed:

1. Functions that return through a register other than `$ra` (0x3a3998, 0x3a3a08).
2. Functions that branch into the middle of another function — the six clusters above.
3. A switch whose case bodies lie outside its function's range (0x255c5c): the merged
   unit must treat a `jr $ra` it cannot place as a plain return.

Two test artefacts were also removed: a jump to an address below 0xff0 slides down a page
of zeroes into the interpreter's return address and looks like a return.

```
python3 tools/recomp/difftest.py sweep --seeds 2 --report local/recomp-out/sweep-stub.txt
python3 tools/recomp/difftest.py sweep --mode follow --seeds 2 --report local/recomp-out/sweep-follow.txt
```

### Replay of the reference-model tests (Ran)

`python3 tools/recomp/difftest.py replay tools/difftest_<area>.py --quick` runs one of the
project's seventeen reference-model tests unchanged and wraps the interpreter's `call`:
for every call the test makes into the game's code, the state before (registers, every
memory page that differs from the executable's image, the stubs and the follow policy in
force) is given to the translation, which must arrive at the same registers, calls and
memory. These are the functions and inputs the reference models are checked on — the
maths library, the random generators, item values, damage formulas, the script machine,
message and wire codecs, object, creature, monster, player and skill code.

| Test | Calls it makes | Replayed | Identical | Different | Functions |
|---|---|---|---|---|---|
| `difftest_amx.py` | 100594 | 1267 | 1267 | 0 | 12 |
| `difftest_anim.py` | 0 | 0 | 0 | 0 | 0 |
| `difftest_arena_monsters.py` | 3975 | 710 | 710 | 0 | 21 |
| `difftest_combat.py` | 16569 | 2082 | 2082 | 0 | 30 |
| `difftest_core.py` | 272103 | 14366 | 14366 | 0 | 110 |
| `difftest_creature.py` | 7754 | 1373 | 1373 | 0 | 18 |
| `difftest_items.py` | 52089 | 3514 | 3514 | 0 | 27 |
| `difftest_messages.py` | 2195 | 572 | 572 | 0 | 12 |
| `difftest_monsters_1.py` | 1967 | 234 | 234 | 0 | 9 |
| `difftest_natives.py` | 5644 | 1377 | 1377 | 0 | 37 |
| `difftest_netwire.py` | 7055 | 852 | 852 | 0 | 8 |
| `difftest_objects.py` | 28625 | 2226 | 2226 | 0 | 35 |
| `difftest_player.py` | 3808 | 158 | 158 | 0 | 2 |
| `difftest_skills_a.py` | 138406 | 3657 | 3657 | 0 | 91 |
| `difftest_skills_b.py` | 76797 | 3197 | 3197 | 0 | 86 |
| `difftest_skills_c.py` | 131324 | 3741 | 3741 | 0 | 127 |
| `difftest_world.py` | 19122 | 1665 | 1665 | 0 | 17 |

**40991 calls replayed, 40991 identical, 0 different, 562 distinct functions** (entry points;
their callees run too). Not replayed: calls under the five other floating-point
configurations of those tests (the test build of the translation implements the default
`ps2` model only), calls beyond 150 per function per test, calls during which a
Python-implemented stub or hook fires (its effect cannot be handed to the translation),
and 800 calls in `difftest_core.py` that run instructions the test itself wrote into the
code area. `difftest_anim.py` was not run: it needs a directory of `.anm` files.

## Step 3 — the platform boundary

### What the game calls outside itself (Read: static; Ran: counted in the runtime)

Static counts are from the executable (`.text` scan); "hit" means the runtime saw it in
the 2,004 frames of step 4 (hub level, no input, numbers per 2,004 frames).

| Boundary | What the executable has | What a native runtime must supply | Effort |
|---|---|---|---|
| **Kernel calls** | a complete wrapper table 0x3525c0–0x352e54 (every `SYSCALL` number 0x00–0x83 and the interrupt-context variants) plus 5 inline ones in the start-up code; by callers: semaphores (Create 56, Delete 109, Signal 166, iSignal 20, Wait 116, Poll 28), threads (Create 13, Start, Exit/Terminate 10, ChangePriority 12, GetThreadId 15, Sleep 9, Wakeup 5+2, Suspend/Resume), interrupt and DMA handlers (Add 9+11, Remove 13, Enable/Disable), `FlushCache` 52, `SetVSyncFlag`, `GsGetIMR/PutIMR`, SIF register and DMA calls, alarms, `SetSyscall` (the SDK installs four handlers of its own, 0x35c0c4–0x35e594) | threads, semaphores, sleep/wake, handler tables, a vertical-blank source, alarms. **Done** in `rt/runtime.cpp` except alarms and the SDK's own syscall handlers (not hit). Hit: `WaitSema` 4,008, `iSignalSema` 4,008, `PollSema` 2,004, `SleepThread`/`WakeupThread` 2,004 each, `FlushCache` 4,008, `Deci2Call` 4 (unhandled, harmless) | small; done |
| **Threads** | 6 at the hub: main (priority 10), three library threads (procedures 0x3536e0, 0x31ed80, 0x36a988), the texture/terrain worker 0x17ca58, the loading-screen thread 0x32187c | each guest thread on a host thread, one running at a time, switched only at kernel calls, interrupts and a poll every 20,000 calls/loop iterations | done |
| **Interrupts** | handlers present at the hub: vertical blank start 0x19b6e4, GS 0x16c910, timers 0/2/3, DMA channels 0–2 `gfx_dmaHandler` 0x16b998, channel 5 (SIF) 0x355b70 | call the registered handler on an interrupt stack at the right moments. Hit: vblank 2,004, DMA ch1 ~110,000, ch2 ~48,000, GS ~8,000 | done |
| **DMA controller** 0x10008000–0x1000e050 | channels 0 (VIF0), 1 (VIF1), 2 (GIF), 3/4 (IPU), 5/6 (SIF), 8/9 (scratchpad) | the register semantics exactly: the game's renderer reads TADR and the call stack ASR0 to see how far a list got. Source-chain mode with call/return, tag interrupts and resumption is implemented; data to VIF1/GIF is walked and dropped | done for what the frame loop uses |
| **GS** 0x12000000–0x12001080 | privileged registers (PMODE, DISPFB, DISPLAY, BGCOLOR, CSR, IMR), and inside the GIF data the `FINISH` register, whose interrupt the renderer waits on (4 per frame) | headless: find `SIGNAL`/`FINISH`/`LABEL` in the GIF stream and raise the GS interrupt. **A renderer**: everything else in that stream | events done; drawing is the large missing piece |
| **VIF1 / VU1** | per frame at the hub: 55 VIF1 transfers, 68,400 quadwords, 8,135 `UNPACK`, 1,717 microprogram starts; `.vutext` holds the VU1 programs | headless: skip. A renderer: either run VU1 microcode (interpreter/translation, 0x3d40 bytes of it) or draw from the packets the way `docs/spec/render-pipeline.md` describes | not started |
| **GIF path 3** | 24 transfers and 234,000 quadwords per frame (texture uploads, set-up) | headless: walk for `FINISH`. A renderer: texture uploads | events done |
| **VU0** | 13 COP2 instructions; one microprogram (77 instructions) run 173 times per frame from `anim_buildPose` | register moves and a microprogram interpreter: `rt/vu0.h`, 23 instruction kinds. Hit: 346,692 calls, 19.3 million instructions | done |
| **Timers** 0x10000000–0x10001830 | timer 0 is the game's frame pacer; timers 2/3 belong to the SDK | counters derived from the virtual clock; no timer interrupts yet | done for pacing |
| **CPU cycle counter** | 5 reads (cosmetic and offline session seeds, profiling) | the virtual clock | done |
| **Scratchpad** 0x70000000, uncached mirrors 0x20000000 / 0x30000000 | used throughout the renderer (display lists are written through the 0x30000000 mirror) | address decoding in the slow path of every load/store | done |
| **I/O processor (SIF RPC)** | servers bound by id: file I/O 0x80000001, module loader 0x80000006, controller 0x80000100/101, multitap 0x80000900, memory card 0x80000400, disc drive 0x80000592–0x8000059c, sound 0x80000701 plus the game's sound driver (client `g_soundRpcClient` 0x877160), network 0x80001101/0x80001201, USB audio/keyboard | one native service per server behind `sceSifBindRpc` 0x356510 / `sceSifCallRpc` 0x3566f0 (both replaced in the runtime). Today every call returns "done" with no data. Hit: sound driver functions 0x50 / 0x70 / 0x80 (5,136 / 1,503 / 125), two library polls (68, 502) | **the next piece of work**: disc reads (ISO 9660 reader + the search/read/stream calls), controller, memory card (a directory of save files), module loads answering "ok" |
| **Controller** | `scePadRead` reads a buffer the I/O processor fills by DMA every blank | write the same buffer from host input | small |
| **Sound** | the game's own driver on the I/O processor (streams, samples, reverb) driven by RPC; position polled every frame | headless: stub. An application: a mixer for SPU2-format samples and the stream format in `docs/audio-save.md` | medium |
| **IPU / MPEG** 0x10002000, DMA 3/4 | the intro films | skip films, or decode with a host library | optional |
| **Network** | libnet/inet over RPC and the two ERX modules (relocatable EE code loaded at run time) | a socket shim at the RPC level (the rig already has one for the emulator), and the ERX code must be translated ahead of time as well | medium; only for online play |

### The runtime that exists (Ran)

`tools/recomp/rt/runtime.cpp` (about 1,200 lines) + `rt/vu0.h`; `python3
tools/recomp/build.py run` links it with the translation into
`local/recomp-out/bin/rta_native`. Guest memory is 32 MB plus scratchpad and vector-unit
memories. Time is a virtual clock: 4 CPU cycles per call or backward branch executed, and
a jump to the next vertical blank when every thread is blocked.

Its kernel keeps its tables **in guest memory, in the layout of the Play! emulator's
high-level kernel** (threads at 0x11000, semaphores at 0xe000, interrupt handlers at
0xa000, DMA handlers at 0xc000, state at 0x4000; structure layouts read in Play!'s
`PS2OS.h`, no code taken). The reason is `resume`: a memory image written by the rig
carries the kernel's state, so the translated game can be started in the middle of a
session the original was running — which is what step 4 uses.

Functions the runtime replaces (`tools/recomp/hle.txt`): `sceSifBindRpc`,
`sceSifCallRpc`, `gfx_beginFrame` (only to log the watches, then the original runs) and
`gfx_dmaHandler` (the original runs; `--hle-renderer` instead counts the frame's draw
packets and reports the frame as sent — the hook a native renderer would use: 153 draw
packets per frame at the hub).

Two findings from building it:

- The game's renderer is interrupt-driven and reads the DMA controller's registers back.
  A model that completes a transfer without leaving TADR/ASR0 as the hardware does stalls
  it; with the registers right, the original state machine runs unmodified.
- A decoding bug of mine (the 0x30000000 mirror mapped onto nothing) lost 14,750 stores
  per frame — every display list the game built — and the simulation still matched the
  original in every compared value for 2,005 frames. The simulation does not read back
  what the renderer writes there. (Fixed; the numbers below are from the fixed runtime.)

## Step 4 — the translated game against the original, frame for frame (Ran)

`tools/recomp/rigcompare.py` does this unattended.

1. `snapshot`: the rig loads its saved state `04-hub.zip` (offline, one player standing in
   the hub level) and, at the head of the session loop (0x322b48 in
   `mainloop_runSession`), writes out the 32 MB of main memory, the scratchpad and the
   main thread's registers.
2. `run`: the rig runs on for 2,000 frames with no input, logging 26 values at the entry
   of `gfx_beginFrame` (once per displayed frame), and writes out memory again at frame
   2,002. The translation is started from the image — the main thread at the loop head
   (an extra entry point of the translation), the four sleeping threads at the return
   address of the kernel call they sleep in — and logs the same values at the same
   address.
3. `compare`, `memdiff`.

Result, 2026-10-11, hub level, simulation ticks 73 to 2,077 (one tick per frame):

- **2,005 frames compared; identical in every frame:** the tick counter, the shared
  random seed `g_randSeed` (it changes every tick in the hub), the cosmetic seed, the draw
  frame counter, level name, player count, the player's position (three raw floats),
  facing, action state, object seed, hit points, mana, gold, experience, checksums of the
  bag, statistics, equipment, abilities and skills, a checksum of the whole player record
  (19,504 bytes), **a checksum of the whole object pool (947,968 bytes: every creature,
  item and effect object)**, the task table and the controller state.
- The one column that differs is `g_netFrame`, which the test itself pokes on the rig to
  arm the memory dump.
- **Memory at frame 2,002:** of 33,554,432 bytes the original changed 74,062 since the
  image; **987 bytes differ** between original and translation: 489 in dead stack space,
  149 in the kernel area (Play!'s own bookkeeping, thread contexts), 127 in the audio
  stream state `g_streams` (the sound driver's replies are stubs), about 220 in renderer
  and texture-cache bookkeeping and timer samples. **0 bytes differ in the object pool,
  0 in the 23 MB heap, 0 in the code.**
- The first version of the run, with the renderer back end replaced (`--hle-renderer`),
  gave the same 25 identical columns.

What this shows: with the same memory to start from, the translated code computes the
same game as the original running in the emulator, tick for tick, including every draw of
the shared random generator, all object code that runs in the hub, the animation poses
(VU0), and the full draw pass. The floating-point model used is the emulator's (`host`
in `rt/fpu.h`), so this is agreement with the emulator, not with a console.

What it does not show: a level with fighting, a level change, input, or anything before
the hub (boot, front end, loading) — see below.

### Boot from power-on (Not reached)

`rta_native boot --elf SLUS_209.73` enters the start-up code and has the kernel calls it
needs, but nothing behind the I/O processor calls: the first disc access cannot be
answered. Not attempted further; the list under "the next piece of work" above is what
it takes (disc, module loads, controller, memory card), then the film player has to be
skipped or stubbed.

### Speed (Ran)

Same machine (Apple silicon), same 2,004 frames of the hub:

| | frames per second | × real time (59.94) |
|---|---|---|
| original in the rig (Play! core, break-point build, logging) | 17–19 | 0.3 |
| original in the rig, 300 frames without the wide log | 36–45 | 0.6–0.76 |
| translation, `-O1`, with the 26-value log (1 MB of checksums per frame) and the original renderer back end walking 4.8 MB of graphics data per frame | 325 | 5.4 |
| translation, `-O1`, renderer back end replaced | 388 | 6.4 |
