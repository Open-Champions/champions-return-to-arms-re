# Native build by static recompilation

## Status for other agents

(Kept current by the runtime's author at every step. Last update: 2026-10-12, step 1 in
progress.)

**How far `rta_native` boots today.** From power-on: start-up, engine and display set-up,
then stops at the first I/O-processor module load (the binary of 2026-10-11). From a
resumed emulator image: runs the hub level. The I/O services that take it further (module
loads, disc, controller, memory card) are being written right now; this paragraph changes
when they work.

**The runtime is being split into several files today** (2026-10-12). Until this section
says "builds", `python3 tools/recomp/build.py run` may fail for a few minutes at a time.
The layout it is moving to, in `tools/recomp/rt/`:

| File | Holds |
|---|---|
| `runtime.cpp` | memory, clock, kernel, interrupts, DMA, hardware registers, `rta::run()` — **no `main` any more** |
| `main_headless.cpp` | `main()`: calls `rta::run(argc, argv, hooks)` with no hooks |
| `iop.cpp` | the services behind `sceSifBindRpc` / `sceSifCallRpc`: module loader, disc (`iso9660.h`), controller, multitap, memory card; owns `fn_00356510`, `fn_003566f0`, `fn_00355d68` |
| `sound_null.cpp` | the two sound servers, no output (replaceable, see below) |
| `script.cpp` | scripted input and conditions in the rig's script language, symbols, watch expressions |
| `host.h`, `host_posix.cpp` | the only host-specific code (threads with large stacks, 64-bit file offsets) |
| `iface.h` | the interfaces for picture, sound, network, controller (`rta::Hooks`) |
| `rt.h` | what those files share |

**Interfaces that will be kept stable** (a change is announced here first):

- **Sound** (`rt.h`): `bool sound_rpc(u32 server, u32 function, u32 send, u32 send_size,
  u32 recv, u32 recv_size); void sound_vblank(); void sound_report();` — `function` is
  the full number the game passed; `send`/`recv` are addresses in `g_ram` (already
  reduced to main memory). `iop_ram()` is 2 MB; whatever the game sends to I/O-processor
  memory (disc reads to IOP addresses, `SifSetDma`) is in that buffer before the RPC that
  refers to it is made. `rt_cycles()` is the virtual clock (294,912,000 per second).
  `build.py run --sound <file.cpp>` links another file in place of `sound_null.cpp`.
- **Picture** (`iface.h`, `rta::VideoSink`, null by default, set through `rta::Hooks` or by
  assigning `g_hooks.video` before `rta::run`): `vif1(words, count)` / `vif0` / `gif` once
  per DMA transfer with the chain flattened, `reg(address, value)` for every store to a GS
  privileged or GIF/VIF register, `vblank(field, number)` at every blank, `frame(number,
  buffer)` when the game hands a finished frame to its back end. Exact wording: section
  "Renderer interface" below (being written with step 5; the header is authoritative
  until then).
- **Network** (`iface.h`, `rta::NetDriver`): the libnet entries. Not wired yet.
- **Controller** (`iface.h`, `rta::PadSource`), or a script (`--script`).
- **Options for modules**: `--opt key=value` (repeatable) is accepted by `rta::run` and
  read with `const char* rt_option(const char* key)` (`rt.h`); unknown options are still
  refused.

**Build**: `python3 tools/recomp/recomp.py && python3 tools/recomp/build.py run`
(`--opt -O1|-O2`, `--jobs N`, `--gen DIR`, `--define NAME`, `--name NAME`, `--sound FILE`).

# Native build by static recompilation: feasibility spike

Started 2026-10-11. Question: if the executable's MIPS R5900 code is translated to C++ once
and compiled for the host, does the translated code compute the same game as the original,
tick for tick, and how much platform work stands between that and a playable native
Mac/Windows application?

This file is written as the work proceeds; every section says what was **Ran** (executed
here, with the numbers), what was only **Read**, and what was **Not reached**.

Related pages: [STATE-OF-PLAY.md](../STATE-OF-PLAY.md) sets this build beside the three
other routes to a game — PCSX2 with the patch file ([online-setup.md](../online-setup.md)),
the Play! emulator as a Mac application ([play-online.md](../play-online.md),
[tools/play-net](../../tools/play-net/README.md)) and the same emulator in a browser
([browser-build.md](browser-build.md)). The rig this build is compared with is
[live-rig.md](live-rig.md).

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
  input, memory card and sound are not in it.
- Step 4 compare with the rig: **done from a resumed session** — 2,005 consecutive frames
  in the hub level, every compared value identical, whole object pool and heap identical
  at the end. From power-on the translation gets through start-up, engine and display
  set-up to the first I/O-processor module load, and stops there.
- Step 5 verdict: at the end of this file.

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
| entries (`fn_<address>` symbols and slots in the call table) | 12,147 (124 of them added for step 4: the session-loop head and the return address of every `WaitSema`/`SleepThread` call, `tools/recomp/entries.txt`) |
| units with a computed jump | 240; units with a dispatch switch: 655 |
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

After the later changes to the translator (extra entries for step 4, `ERET` as a checked
return) the stub-mode sweep was run again with one seed: 46,392 cases, 36,382 identical
to the return, 247 identical up to a common stop, 0 different; 7,349 functions pass, 42
partly, 0 fail.

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
| **Kernel calls** | a complete wrapper table 0x3525c0–0x352e54 (every `SYSCALL` number 0x00–0x83 and the interrupt-context variants) plus 5 inline ones in the start-up code; by callers: semaphores (Create 56, Delete 109, Signal 166, iSignal 20, Wait 116, Poll 28), threads (Create 13, Start, Exit/Terminate 10, ChangePriority 12, GetThreadId 15, Sleep 9, Wakeup 5+2, Suspend/Resume), interrupt and DMA handlers (Add 9+11, Remove 13, Enable/Disable), `FlushCache` 52, `SetVSyncFlag`, `GsGetIMR/PutIMR`, SIF register and DMA calls, alarms, `SetSyscall` (the SDK installs four handlers of its own, 0x35c0c4–0x35e594) | threads, semaphores, sleep/wake, handler tables, a vertical-blank source, alarms. **Done** in `rt/runtime.cpp`, alarms and game-installed handlers included (see the boot section). Hit: `WaitSema` 4,008, `iSignalSema` 4,008, `PollSema` 2,004, `SleepThread`/`WakeupThread` 2,004 each, `FlushCache` 4,008, `Deci2Call` 4 (unhandled, harmless) | small; done |
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

Functions the runtime replaces (`tools/recomp/hle.txt`): `sceSifInitRpc`, `sceSifBindRpc`,
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
- The translation compiled at `-O1` and at `-O2` gives the same 25 columns and the same
  987 bytes.

What this shows: with the same memory to start from, the translated code computes the
same game as the original running in the emulator, tick for tick, including every draw of
the shared random generator, all object code that runs in the hub, the animation poses
(VU0), and the full draw pass. The floating-point model used is the emulator's (`host`
in `rt/fpu.h`), so this is agreement with the emulator, not with a console.

What it does not show: a level with fighting, a level change, input, or anything before
the hub (boot, front end, loading) — see below.

### Sensitivity of the comparison (Ran, by accident)

While extending the runtime for the boot path, the RPC stub was changed to answer every
call with zeroes. The resumed run then differed from the original: the controller-state
checksum from frame 9, the task table from frame 38, and from frame 39 the tick counter
stood still (112 on the rig, 111 here) with the seed and the object pool diverging — the
zero answer of the controller library says "unplugged", and the game pauses. Restoring the
previous behaviour for clients bound before the image was taken (they keep the last answer
the emulator's I/O processor gave) restored the identical run. So the comparison does
notice a divergence, within frames, and names the tick.

### Boot from power-on (Ran as far as it goes)

`rta_native boot --elf SLUS_209.73 --seconds 6` runs the translated game from its entry
point 0x14fa88. What happens, in order (from the runtime's trace):

1. Start-up code: `SetupThread`, `SetupHeap`, then the SDK's kernel patches. The SDK
   installs system calls of its own with `SetSyscall` and runs them: 0x83 and 0x5a are
   translated code (0x35c108, 0x35c0d0, 0x35c738, 0x35c318, 0x35e548) and run natively.
   Three times it then copies a block of kernel-mode code out of its **data** section
   (0x507da0, 0x5075d8, 0x508570) to kernel memory (0x80076000, 0x80074000, 0x80075000)
   and installs that as system calls 0xfc–0xff (alarms), 0x55–0x59, 0x8, 0x12c. Code that
   exists only as data has no translation. The runtime drops those registrations and
   implements alarms itself; the 0x55–0x59 group (TLB entry calls, 48 of them during
   start-up) returns 0.
2. A kernel-mode helper (0x35c858) writes a hardware register and returns with `ERET`.
   `ERET` is now translated as a checked return (the return register must equal `$ra`).
3. The timer thread (procedure 0x3536e0) is created and started; static constructors run;
   `main` runs `engine_init`: semaphores, `SetGsCrt`, the vertical-blank handler
   0x19b6e4, two GIF transfers (71,696 quadwords), waits on vertical blanks that the
   runtime delivers.
4. `sceSifInitRpc` (0x355d68) polls for the I/O processor's answer forever; replaced by
   "done" (`hle.txt`).
5. The game binds to the module loader (0x80000006) and the disc drive (0x80000592,
   0x80000593), sets the disc mode, and then stops itself with its own message "Can't
   load IOP modules!" and `Exit(0)`, 24 fields after power-on: nothing behind those calls
   loads a module or reads the disc.

That is the edge of the runtime, and it is where the list "the next piece of work" in
step 3 starts: module loads that answer "loaded", an ISO 9660 reader behind the disc and
file servers, the controller buffer, the memory card, then the logo films (skip) and the
front end. None of it is translation work.

### Speed (Ran)

Same machine (Apple silicon, one core used; other agents kept the machine at a load
average near 60 during the measurements, so processor time is the fair column), the hub
level, no input:

| | frames per second of wall time | frames per processor-second | × real time (59.94 fps) by processor time |
|---|---|---|---|
| original in the rig (Play! core, break-point build), 1,200 frames | 31 | 36 | 0.6 |
| original in the rig, build without break points, 1,200 frames | 29 | 62 | 1.04 |
| translation `-O2`, original renderer back end walking 4.8 MB of graphics data per frame, 6,000 frames | 476 | 650 | 10.8 |
| translation `-O2`, renderer back end replaced by the hand-over hook, 6,000 frames | 1,026 | 1,325 | 22 |
| translation `-O1` with the 26-value log (1 MB of checksums per frame), 2,004 frames | 233–388 | — | — |

A frame of the hub is about 37,600 calls and loop iterations of translated code. In the
fastest configuration a third of the processor time is the VU0 interpreter (173
microprogram runs per frame, each instruction copying the register file first); it has
not been optimised. Compile time: 213 processor-seconds at `-O2`, 38 s on 14 jobs.

## Step 5 — verdict

### Does the translated code compute the same game?

Yes, as far as it was tested, and it was tested three ways:

1. **Function by function against the project's interpreter** (the R5900's own
   floating-point rules, `ps2` model): 7,431 of 7,732 functions agree on every register,
   call and memory byte; 0 disagree; 301 could not be driven automatically. 124,284
   automatic cases and 40,991 calls from the reference-model tests are identical.
2. **Frame by frame against the original running in the emulator** (the emulator's
   floating-point rules, `host` model): 2,005 consecutive frames of a real session, every
   compared value identical including checksums of all object memory; at the end 0
   differing bytes in the object pool and the heap.
3. **A deliberate-in-effect perturbation is detected** within 9 frames (above).

Limits of that statement: one level (the hub), no input, no fighting, no level change, no
network session; equality with the emulator, not with a console (the console-accurate
float model exists and passes test 1, but nobody here has a console to check the
interpreter's model against, as `tools/ee_emu.py` says itself).

### What fraction is done

| Part | State |
|---|---|
| Translator: all instructions, all 757,702 instruction slots, jump tables, cross-function clusters, 128-bit registers, both float models | done |
| Proof of the translation | done at function level (96 % of functions) and for 2,005 frames of one level |
| Kernel: threads, semaphores, interrupt/DMA handlers, alarms, vertical blank, game-installed system calls | done for what the frame loop and start-up use |
| DMA controller, GS events, timers, scratchpad, mirrors, VU0 | done (headless) |
| I/O-processor services: module loader, disc, files, controller, memory card | **missing** — the boot stops here |
| Renderer | **missing** — the hand-over point exists (`gfx_dmaHandler(-1)`: 153 draw packets per frame at the hub; or the raw VIF1/GIF streams, 4.8 MB per frame) |
| Sound | **missing** — the game's driver is polled by RPC three to four times per frame |
| Network | **missing** — plus two ERX code modules that need translating ahead of time |
| Windows | not built; the runtime uses POSIX threads and Clang built-ins, the generated code is plain C++17 |

The part that could not have been bought with ordinary engineering — is a mechanical
translation of 3 MB of machine code faithful enough to be the simulation core — is
answered. What is left is ordinary, and large: it is the platform, not the game.

### What a playable native application still needs, in order

1. **I/O services** behind `sceSifBindRpc`/`sceSifCallRpc` (two functions, already the
   runtime's): module loads answer "loaded"; an ISO 9660 reader for the disc image behind
   the drive's search/read/stream calls and the file server; the controller library's
   buffer written from host input; the memory card as a host directory. This takes the
   boot to the front end and makes every level reachable — and with it, the same
   frame-for-frame comparison with the rig from power-on (the seeds the offline session
   takes from the cycle counter have to be forced equal on both sides) and in levels with
   fighting.
2. **A renderer.** Two ways in. (a) Emulate what is there: run the VU1 microprograms
   (15,680 bytes of microcode; 1,717 program starts and 8,135 unpacks per frame at the
   hub) and rasterise the GS primitives they emit — a small GS on the GPU; faithful,
   resolution-independent only with effort. (b) Take the frame at the hand-over point and
   draw the packets from their documented layout (`docs/spec/render-pipeline.md`), doing
   in shaders what the microprograms do; more work to start, but it is the route to
   higher resolution and wide screen. Texture uploads are in the GIF stream either way.
3. **Sound**: a replacement for the game's I/O-processor sound driver at its RPC
   interface (functions 0x50, 0x70, 0x80 are the per-frame ones), mixing the sample and
   stream formats of `docs/audio-save.md`.
4. **Films**: skip, or decode the MPEG streams with a host library in place of the IPU.
5. **Network**: host sockets under the libnet RPC interface (the rig's shim shows the
   shape) and the two ERX modules translated for a fixed load address, or replaced at
   their socket API.
6. Frame pacing against the host display, input mapping, a Windows build of the runtime.

### Measured speed

One core runs the hub at 10.8 times real time with the game's own renderer back end
feeding a null GS, 22 times with the back end replaced — against 0.6 to 1.04 for the
emulator core on the same machine by the same measure. A native renderer has the whole
frame time left to it.

### Risks

- **Floating point and online play.** The translation can do the emulator's arithmetic
  (fast) or the interpreter's console model (integer arithmetic, slower). Two native
  clients agree with each other under either. Agreement with consoles or with other
  emulators' settings is the question `docs/issues/float-divergence.md` already asks, and
  this work does not answer it.
- **Code that is not in `.text`.** Seen: the SDK's kernel patches (three blocks copied
  from data — handled by not running them) and the ERX modules (network only). Anything
  else of that kind stops the runtime with the address; none appeared in start-up or in
  2,005 frames. An interpreter for such code as a fallback was considered and not built.
- **Indirect jumps to an address without an entry**, and the rule that a return goes back
  to the caller whatever `$ra` holds. Both are checked or visible when they fail (the
  runtime stops and names the address); neither occurred. Coverage is one level.
- **Threads of a resumed image** continue only when they sleep in a kernel call made
  directly from their thread procedure (true for all four at the hub). A fresh boot does
  not have this limit.
- **Timing.** The runtime's clock counts calls and loop iterations, I/O is instantaneous,
  DMA completes at once. The frame loop is paced by vertical blanks and agreed with the
  emulator; code that depends on how long loading takes (the loading-screen thread, the
  half-rate display mode after 32 late frames, asynchronous lump loads) will see
  different timing than a console. In lockstep network play ticks are counted, not
  timed, so this is a per-machine matter.
- **The renderer back end reads DMA registers back** (TADR, ASR0) and waits for the GS
  `FINISH` interrupt. A native renderer replaces that code; until then the DMA model has
  to stay exact.
- **Distribution.** The generated C++ is a translation of the game's code. This project
  keeps it under `local/`; a release would ship the translator and runtime and build from
  the user's own executable, which puts a C++ compiler on the user's machine — the way
  the N64 recompilation projects handle it is the model to look at.

### Not reached

- Boot beyond the first module load; the title screen; any level entered natively.
- A comparison with fighting, input, a level change or a network session.
- `difftest_anim.py` in the replay (needs extracted `.anm` files); the 301 functions the
  sweep cannot drive.
- VU1, any drawing, any sound, the network, a Windows build.

## How to repeat

```
python3 tools/recomp/recomp.py                      # translate (1.5 s)
python3 tools/recomp/build.py test                  # test build
python3 tools/recomp/difftest.py sweep --seeds 2    # step 2, stub mode  (2 min)
python3 tools/recomp/difftest.py sweep --seeds 2 --mode follow
python3 tools/recomp/difftest.py replay tools/difftest_core.py --quick
python3 tools/recomp/build.py run                   # runtime build (-O2)
export RTA_DISC=/path/to/your/disc.iso
python3 tools/recomp/rigcompare.py snapshot         # needs the rig and its state 04-hub.zip
python3 tools/recomp/rigcompare.py run --frames 2000
python3 tools/recomp/rigcompare.py memdiff
local/recomp-out/bin/rta_native boot --elf SLUS_209.73 --seconds 6
```

Files: `tools/recomp/recomp.py` (translator), `build.py`, `difftest.py`, `replay.py`,
`rigcompare.py`, `hle.txt`, `entries.txt`, `rt/recomp.h`, `rt/fpu.h`, `rt/mmi.h`,
`rt/vu0.h`, `rt/test_driver.cpp`, `rt/runtime.cpp`. Everything generated or dumped is
under `local/recomp-out/`.
