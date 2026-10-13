# Native build by static recompilation

## Status for other agents

(Kept current by the runtime's author at every step. Last update: 2026-10-12 10:50 local,
**the tree builds**; steps 1 to 3 done as far as described under "Continuation", steps 4
to 6 written up, not built.)

**Changed 2026-10-12, 15:20: the game's threads flush denormals to zero.** `thread_main`
in `rt/runtime.cpp` now sets flush-to-zero besides rounding toward zero (FPCR bit 24 on
ARM64; `_MM_SET_FLUSH_ZERO_MODE` and `_MM_SET_DENORMALS_ZERO_MODE` on x86-64), as the
emulator the translation is compared with does: on the console a denormal is zero when it
is read and when it would be a result, and with rounding alone add, subtract, multiply,
divide, square root, multiply-add, MAX / MIN and some compares gave other bits whenever a
denormal was involved (found by another agent's directed operand sets against an exact
reference). Every host thread that runs translated code starts in `thread_main`
(interrupt handlers and alarms are delivered on those threads; `vu0.h` computes with the
host's floats), so the one place covers the main processor's FPU and the VU0 macro
instructions. `--opt arith=nearest` sets neither mode (the host's own arithmetic, for telling apart
what depends on it); a build that defines `RTA_SOFT_RZ` (WebAssembly: the float helpers
do it in software) leaves the processor's mode alone; one line at the start of a run
("arithmetic: ...") says which is in force. **Who builds against `rt/`:** nothing to
change in a build for ARM64 or
x86-64 with clang or GCC; a Windows build with MSVC needs `<xmmintrin.h>` /
`<pmmintrin.h>` (included under `_M_X64`) and, on ARM64, `_controlfp_s` or the intrinsic
for FPCR in place of the inline assembly; a WebAssembly build has no such mode and has to
flush in the float helpers (`fpu.h`) instead. Code of yours that runs on a game thread and
wants round-to-nearest or denormals (a decoder, a mixer) must not rely on the thread's
mode. **Checked:** the fight session against the rig's log (`rigcompare.py boot-native
--replay`, `rta_app_orig`, 7,904 fields): the result is the same line for line as before
the change - every simulation column identical, the player record still different at
tick 7 of the first level and the object pool in ticks 3,886 to 3,912 of `valor`. So
this session met no denormal that mattered, and the two unexplained differences are not
denormals.

**Changed 2026-10-12 afternoon, later** (the window program only; nothing in `rt/`):
`tools/recomp/app/build.py` translates with `--hle-add tools/recomp/app/hle-app.txt`
(Sony's MPEG library at the seven entry points the film player calls; supplied by
`app/film.cpp`), so `rta_app` plays the films; the shared translation and `hle.txt` are
unchanged, and the headless runtime still ends a film at its first picture.
`tools/recomp/sound/sound_rta.cpp` has a second way of keeping time, `--opt
sound-clock=real` (the sound side on the device's thread; `native-sound.md` section 8);
the default is as before.

**Changed 2026-10-12 afternoon** (the runtime is now kept by the author of
`docs/issues/native-app.md`; section 7 there has the reasons). Additions only: nothing in
`rt.h` / `iface.h` changed its shape.

- **Accesses where nothing is** no longer stop the run: a load answers 0xCC in every
  byte, a store is dropped, both are counted and the first 16 are listed in the report
  (`--opt strict-memory=1` for the old stop). A network build needs no memory wrapper.
- **`--arg <text>`** (repeatable): the arguments of the game's `main()`.
- **`hle.txt` gained two addresses**, supplied in `runtime.cpp`: 0x3205ec `movie_update`
  (a film ends at its first update; `--opt films=original` for the game's code) and
  0x322520 `mainloop_pollAmbientAudio` (the level-music countdown is held while the old
  music fades out; `--opt music-start=original`). Every translation has to be made again
  to link against this runtime (`recomp.py`, 1.5 s).
- **I/O processor**: SIF command 0x80000001 is answered (word 0x8ef2c4), headset driver
  function 1 answers 0x8000000A, module loader function 9 answers by the module's own
  name. Not exercised offline.
- **Script**: `app <text>` (for an application linked with the runtime; noted and ignored
  without one), `call <address> [a0 [a1]]` (a game function called at a blank; a test
  aid). `rt_at_finish` is called before the final report.
- **Translator**: `recomp.py --pnach FILE --sections FILE [--section NAME]` translates
  the patched game and writes `<out>/patches.cpp`, which the runtime applies to memory
  after loading the executable (compile it with the other generated files). An entangled
  cluster whose members lie far apart is merged member by member (a unit with several
  address ranges) instead of with everything between them; the unpatched translation is
  unchanged byte for byte.
- **The window program** is `tools/recomp/app/` (`rta_app`); `rta_render` in
  `tools/recomp/render/` is the renderer's old test program (it still builds against this
  runtime; it boots without the renderer changes' benefit of input or sound).

**Added 2026-10-12, network** (by the author of `docs/issues/native-online.md`; nothing in
`tools/recomp/rt/` was changed, `rt.h` / `iface.h` are as they were):

- **Translator**: `recomp.py --hle-add FILE` (repeatable: one more list of addresses whose
  `fn_` somebody else supplies, beside `--hle`) and `--extra-pnach FILE` (repeatable: a
  patch file from outside the repository, applied whole after `--pnach` — the local
  sign-in patch). `patches.cpp` gained `unsigned recomp_patch_set_words()`: how many of
  its words are the fix set's (the rest came from `--extra-pnach`).
- **The network** is `tools/recomp/net/netdrv.cpp` with `online.cpp`: it supplies the
  addresses of `tools/recomp/net/hle-online.txt` (Sony's libnet entries, the eznetcnf /
  eznetctl clients, `net_loadModules`, `net_linkCheck`, and hooks on `main` 0x323dcc and
  `tasks_run` 0x3226e4 in which the original runs). A program that does not link it gets
  the originals through `hle_weak.cpp`. It reads `--opt` keys (`net-*`, `online*`,
  `tick-*`; `netdrv.h`), stands in front of `g_hooks.pad`, and chains
  `script_app_command` ("app online …", "app net …") and `rt_at_finish`.
- **Programs**: `tools/recomp/net/build_online.py` builds `bin/rta_native_online`
  (headless, the suggested fix set, the network); `app/build.py` now translates with the
  network list and links the network into `rta_app`.

**How far `rta_native` boots today.** From power-on, headless, by a script: module loads,
disc reads, the memory-card check (a save directory is created on a blank card), logo
and intro, front end, character creation, **the first level (the hub) with a
controllable character**, a level change into a level with monsters (`valor`), a fight,
the pause menu and its load screen, and back to the hub. Nothing the game asks for goes
unanswered. Compared with the rig tick for tick from power-on: front end, hub, the fight
level and the hub again agree in every simulation value, the whole object pool included
(details and the exceptions: "Continuation", steps 2 and 3). From a resumed emulator
image the 2,005-frame comparison of the spike still passes unchanged.

```
export RTA_DISC="/path/to/your/disc image.iso"
python3 tools/recomp/recomp.py && python3 tools/recomp/build.py run     # 46 generated files + 6 of the runtime
python3 tools/recomp/native.py boot --card local/recomp-out/card-test --script tools/rig/examples/boot-to-hub.rig
```

`native.py` adds `--elf`, `--disc` (from `RTA_DISC`), `--card` and one `--sym` per symbol
file; `rta_native --help` lists every option. Build options: `--opt -O1|-O2`, `--jobs N`,
`--gen DIR`, `--define NAME`, `--name NAME` (objects in `obj-NAME`, program `bin/NAME`),
`--sound FILE.cpp` (in place of `rt/sound_null.cpp`), `--main FILE.cpp` (in place of
`rt/main_headless.cpp`), `--extra FILE.cpp` and `--lib NAME` (both repeatable).

**Files** (`tools/recomp/rt/`; every `.cpp` there except `test_driver.cpp` is the runtime):

| File | Holds |
|---|---|
| `runtime.cpp` | memory, clock, kernel, interrupts, timers, DMA, hardware registers, `rta::run()` — no `main` |
| `main_headless.cpp` | `main()`: calls `rta::run(argc, argv, hooks)` with no hooks |
| `iop.cpp` | the services behind `sceSifBindRpc` / `sceSifCallRpc`: module loader, I/O-processor heap, disc (`iso9660.h`), controller, multitap, memory card; owns `fn_00356510`, `fn_003566f0`, `fn_00355d68` |
| `sound_null.cpp` | the two sound servers, no output (replaceable) |
| `script.cpp` | scripted input and conditions in the rig's script language, symbols, watch expressions |
| `host.h`, `host_posix.cpp` | the only host-specific code (threads with large stacks, 64-bit file offsets) |
| `iface.h` | the interfaces for picture, sound, network, controller (`rta::Hooks`) |
| `rt.h` | what those files share |

**Services that exist**

- **Controller**: both ports report a DualShock 2. Input comes from `rta::PadSource`
  when an application sets one (`rta::Hooks::pad`), otherwise from the script
  (`--script FILE`, `--do "command"`; the rig's language: `wait`, `at`, `until`, `press`,
  `release`, `tap`, `tapuntil`, `stick`, `pad`, input-table lines, the `…2` forms for the
  second port, `poke`, `dump`, `show`, `echo`, `quit`), otherwise nothing is held. The
  runtime writes the library's controller buffers at every vertical blank; `pad_readPort`
  0x17421c is not replaced. In a resumed image the ports are already open: name the
  buffers with `--opt pad0=7cb140 --opt pad1=7cb640` to drive them.
- **Memory card**: `--card DIR` (default `./rta-card`; `native.py` passes
  `local/recomp-out/card`): `DIR/mc0` and `DIR/mc1`, one host directory per card, a save
  a sub-directory of plain files — the layout of the Play! emulator's `<data>/vfs`, so a
  card directory can be copied to and from the emulator build.
- **Disc**: `--disc IMAGE` or `RTA_DISC`, an ISO 9660 image read in place: search, sector
  reads to main memory and to I/O-processor memory, streaming reads.
- **Modules**: every load is answered "loaded" after the name is checked on the disc.
- **Sound**: `sound_null.cpp` answers both sound servers without output.
- **Time**: I/O answers arrive after short fixed times on the virtual clock (50 µs and
  up); `--emulator-timing` uses the delays the Play! emulator applies instead.
- The game's own console text (through the debugger link) is printed as `[game] …`.

**Interfaces kept stable** (a change is announced here first)

- **Sound** (`rt.h`): `bool sound_rpc(u32 server, u32 function, u32 send, u32 send_size,
  u32 recv, u32 recv_size); void sound_vblank(); void sound_report();` — `function` is
  the full number the game passed; `send`/`recv` are offsets into `g_ram` (already
  reduced to main memory; `~0u` when the game gave no usable buffer). `sound_rpc` returns
  false for a server that is not a sound server. `iop_ram()` is 2 MB; whatever the game
  sends to I/O-processor memory (disc reads to I/O-processor addresses, `sceSifSetDma`)
  is in that buffer before the call that made it returns, so before any RPC that refers
  to it. `rt_cycles()` is the virtual clock (`CYCLES_PER_SECOND` = 294,912,000).
  `sound_vblank()` is called at the start of every vertical blank, `sound_report()` once
  at the end of a run. `build.py run --sound <file.cpp>` links another file in place of
  `sound_null.cpp`.
- **Picture** (`iface.h`, `rta::VideoSink`, every member a no-op by default; set through
  `rta::Hooks::video`): `vif1(words, count)` / `vif0` / `gif` once per DMA transfer with
  the chain flattened, `reg(address, value)` for every store to a GS privileged or GIF/VIF
  register, `vblank(field, number)` at every blank, `frame(number, buffer)` when the game
  hands a finished frame to its back end. `rta::memory()`, `scratchpad()`, `vu1_micro()`,
  `vu1_data()` give guest memory. Exact wording: section "Renderer interface" under
  "Continuation", step 5.
- **Network** (`iface.h`, `rta::NetDriver`): a reserved shape, not wired; the libnet
  entries are the original code today (they reach RPC servers 0x80001101 / 0x80001201,
  which answer nothing). A build that replaces them does it with its own HLE list:
  `tools/recomp/net` does, for the lobby path as well (`docs/issues/native-online.md`).
  `rta::SoundSink` is reserved in the same way: nothing calls it.
- **Controller** (`iface.h`, `rta::PadSource`): asked once per port per blank, before the
  game's blank handler runs. **Changed 09:45**: what it returns reaches the game's
  controller buffer one blank later, as on the console and in the rig (the I/O
  processor's copy lands during the frame); `--opt pad-delay=0` hands it over at once,
  `--opt pad-delay=N` delays N blanks. Scripts behave like the rig's with the default.
- **Comparison aids**: `--count-at <site>=<v1>,<v2>…` gives the reads of the CPU cycle
  counter at one code address their values (the offline session seeds are read at
  0x3229f0 and 0x322a00); `--adopt` (resume only) lets this runtime's services answer the
  clients an emulator image had bound; `--script-offset N` starts the script's frame
  numbers at N; `--opt pad-replay=FILE` hands the game recorded controller bytes tick
  for tick (written by `rigcompare.py boot-native --replay` from the rig's log).
  `tools/recomp/examples/boot-to-hub-ticks.rig` is the boot route with every front-end
  press keyed on the simulation tick, for runs that are compared.
- **Options for modules**: `--opt key=value` (repeatable) is accepted by `rta::run` and
  read with `const char* rt_option(const char* key)` (`rt.h`); other unknown options are
  refused.
- `rt_after(cycles, fn)`, `rt_sleep(ctx, cycles)`, `rt_call_handler(address, a0, a1)`,
  `rt_signal_sema(id)`, `rt_note(text)`, `rt_fmt`, `rt_die`, `rt_finish(code)`,
  `rt_fields()`, `guest_addr(pointer, size)` (`rt.h`) are available to code linked with
  the runtime.

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
  input, memory card and sound are not in it. (State of the spike, 2026-10-11. The
  section "Continuation, 2026-10-12" adds them and boots from power-on.)
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

(The verdict of the spike, 2026-10-11, kept as written. The I/O services it lists as
missing, the boot from power-on and play are in "Continuation, 2026-10-12" below.)

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
| Windows | not built then (since: `docs/issues/native-windows.md`); the runtime uses POSIX threads and Clang built-ins, the generated code is plain C++17 |

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

# Continuation, 2026-10-12: boot from power-on, and play

The spike above ended at the first module load. This part takes the same translation
from power-on into play and compares it with the rig again. Same conventions: **Ran**,
**Read**, **Not reached**. Machine load is quoted beside speeds because other jobs shared
the Mac (load average between 35 and 420 during the day).

## Step 1 — the I/O processor's services (Ran)

`tools/recomp/rt/iop.cpp` replaces three library functions — `sceSifInitRpc` 0x355d68,
`sceSifBindRpc` 0x356510, `sceSifCallRpc` 0x3566f0 — and puts one native service behind
each server the game binds. What each answers was taken from two sources: the layouts of
the Play! emulator's own services (read, nothing copied), and a capture of every call and
reply of a boot of the original in the rig (break points at the call, at its return and
at the completion functions; `local/recomp-out/ref/boot2.log`, 24,770 lines).

| Server | Service here | Calls in a boot to the hub and 1,400 fields of standing there (3,908 fields) |
|---|---|---|
| 0x80000006 | module loader: 0xff answers the version text the library accepts, 0 (load and start) checks the name on the disc and answers a running id | 23 loads, all found |
| 0x80000003 | I/O-processor heap: allocate, free, largest and total free block; the heap begins at 0x11a400 and ends at 2 MB, as in the rig | 4 allocations (0x14800, 0x1000, 0x1000, 0x7a000), 21 size queries |
| 0x80000592 / 0x593 / 0x595 / 0x597 / 0x59a / 0x59c | the disc on an ISO 9660 image (`iso9660.h`): init, media mode, layer information, last error, clock, search (the game asks once, for a directory, and walks the directory sectors itself), read to main memory, read to I/O-processor memory, the streaming commands (init, start, read, stop, seek, status), drive-ready | 115 reads, 65 stream commands, 3 reads to I/O-processor memory, 118 ready polls; 15,277 sectors |
| 0x80000100 / 0x101 | controller ports: open, slots per port, main mode, actuator alignment, button information (pressures), version; the library's two 0x80-byte records per port and slot are rewritten every vertical blank | 478 |
| 0x80000900 | multitap: version, port open; none connected | 6 |
| 0x80000400 | memory card on a host directory: init, card information, open (and make directory), close, seek, read, write, flush, change directory, directory listing with wild cards, rename, delete, slot count | 53; 760 bytes read, 129,572 written |
| 0x61766973, 0x50494c42 | the USB keyboard and headset drivers: their version and packet-size answers; the keyboard read stays open for ever, as with no keyboard | 4 |
| 0x80000701, 0x163a5 | sound: `sound_rpc()` (below) | about 12,400 |

Two library details the replacement has to honour: a no-wait call is "in progress" for
`sceSifCheckStatRpc` 0x3568f0 while the packet the client points at carries the call's
number and a busy bit (64 small packets at 0xff000 serve as that), and a completion
function runs later, where an interrupt handler would (`rt_after`), not inside the call.

**Time.** A call takes time on the virtual clock: 50 µs and up by default (the calling
thread sleeps, other threads and interrupts run), or with `--emulator-timing` the delays
Play! applies (16.67 ms per stream read and per read to I/O-processor memory, 0.1 ms +
0.5 ms per sector for a plain read, 2.7 ms per card command). Loading is therefore much
faster here by default: the hub is reached at field 2,453 instead of 2,826.

**Controller.** Both ports report a DualShock 2; the mode sequence the game drives
(digital → analog → analog with pressures) is modelled with the busy states the library
polls. The record layout was taken from dumps of the original's buffer in the rig. The
state read at a vertical blank reaches the game one blank later (see the findings).

**Memory card.** `--card DIR`: `DIR/mc0`, `DIR/mc1`; a save is a sub-directory of plain
files, `:` and `\` in names written `%3A` and `%5C` — Play!'s layout. A boot on a blank
card creates the same three files with the same sizes as the rig's run (760, 127,848 and
964 bytes). Not yet exercised: a save of a character (see "Not reached").

**Sound, what the game asks** (`sound_null.cpp` answers it and makes no sound). Function
numbers as the game passes them; counts from the same 3,908 fields:

| Server | Function | Count | Answer here |
|---|---|---|---|
| 0x80000701 | 0x8000 init | 1 | 0 |
| | 0x8010 set parameter | 42 | 0 |
| | 0x8030 set switch | 108 | 0 |
| | 0x8040 get switch (the voice-end flags, twice every 8th frame) | 924 | every voice ended (0xffffff — what the rig's sound library answered throughout the capture) |
| | 0x8050 set address, 0x8070 set core attribute, 0x8190 / 0x81a1 / 0x81b1 effects | 13 each | 0 |
| | 0x80b0 batch | 114 | the number of commands |
| | 0x80d0 voice transfer (sample upload from I/O-processor memory) | 743 | the size; 2,082,176 bytes in all |
| | 0x80f0 transfer status | 756 | done |
| 0x163a5 | 0x20 init, 0x30 stream buffer (stream, address, size) ×3 | 4 | the status block |
| | 0x40 data written (stream, write position, sample rate, flags) | 3 | status block |
| | 0x50 status | 9,668 | 0x40 bytes: per stream write position, read position, current volume, bytes played |
| | 0x60 stop, 0x70 volume target, 0x80 volumes | 36 / 100 / 233 | status block |
| | 0xb0 / 0xc0 sample upload | 488 each | status block |

The stream model advances the read position on the virtual clock at the stream's byte
rate (16 bytes per 28 samples per channel) in 0x800-byte steps, never past the write
position, and ramps the volume word toward its target; the game feeds a stream as the
driver consumes it and treats "read = write" as finished, so without this model dialogue
and music logic would not move.

## Runtime changes the boot needed (Ran)

| What | Why |
|---|---|
| Timer compare and overflow interrupts (INTC 9–12), `timer_sync` / `next_timer` | Sony's `DelayThread` 0x353a58 and its alarms run on timer 2's compare interrupt; without it the first delay never ended |
| `Deci2Call` (system call 0x7c): open, send, poll, puts | the game's console output goes through the debugger link and waits for the "sent" flag; the text is printed as `[game] …` |
| Hardware status bits are raised whether or not the CPU accepts interrupts | code polls INTC_STAT with interrupts off |
| The vertical-blank interrupt is taken 4,800 cycles after its status bit | `sceGsSyncV` 0x34fde0 → 0x352e70 clears the bit and polls for it with interrupts on while the game has a blank handler installed; it only sees the bit if code runs between the hardware raising it and the kernel acknowledging it. Play! gives it that window (interrupts are looked at after the next slice of code); a kernel that acknowledges at once hangs the boot in `gfx_uploadMicrocode` 0x19be08 |
| `rt_after`, `rt_sleep`, `rt_call_handler` | answers that arrive later; completion functions in interrupt context |
| per-thread last call site, possible return addresses on the stack in the `--seconds` report | finding where a boot waits |

Not handled and harmless so far: system calls 0x5b (13 calls) and 0x6b (1), which the
SDK reaches after its own `SetSyscall` registrations of code copied out of the data
section were dropped; one bind to the file server 0x80000001 with one call 0xff after a
level change (answered with nothing).

## Step 2 — from power-on to the first level, against the rig (Ran)

`python3 tools/recomp/native.py boot --script tools/rig/examples/boot-to-hub.rig` runs the
rig's own boot script unchanged: card check and creation of the save directory, logo and
film skipped, front end, character creation, the hub — sim tick 60 with a controllable
character at field 2,453 (rig: 2,826 to 2,830). Nothing the game asked for went
unanswered.

**Method** (`tools/recomp/rigcompare.py boot-rig`, `boot-native`, `boot-compare`). Both
run the same script from a blank card and log the same watches once per displayed frame
at the entry of `gfx_beginFrame`. Frames cannot be matched: loading takes a different
number of them. Rows are matched on **game events**: an *episode* is a stretch in which
the simulation tick `g_simFrame` does not go back (one level from its start to the next
level start), and within an episode the first row of each tick is compared with the
other machine's first row of that tick. Two things have to be made equal first:

- **The session seeds.** `mainloop_runSession` takes `g_cosmeticSeed` and `g_randSeed`
  from the CPU cycle counter (0x3229f0, 0x322a00) when the front-end session starts. The
  rig's values are logged at the next block start (`game_addCoreTasks`, return address
  0x322a28: 0x0bade742 and 0x0bade743 in every run of this script) and given to the
  native run with `--count-at`.
- **The controller, tick for tick.** See findings 2, 3 and 4 below.

**Result** (2026-10-12; `tools/recomp/examples/boot-to-hub-ticks.rig`, the rig's boot
route with every front-end press keyed on the simulation tick):

| Episode | Ticks compared | Result |
|---|---|---|
| start-up and card screens (level name empty) | 662 + 22 | simulation columns identical; the cosmetic seed differs (it is seeded from the cycle counter at 0x19d1e0 in `engine_init`, which was not forced), and the controller bytes differ at 73 ticks while the two controller drivers bring the pad up |
| front end (`intro`) | 1,383 | **all 27 columns identical**, the object pool included |
| first level (`hub`) | 599 | all identical, the object pool included, except the whole-record checksum of the player at one tick (tick 7) |

The 27 columns: simulation tick, shared seed, cosmetic seed, displayed-frame counter
(different by design), the rig's marker, level name, player count, the player's position
(three raw floats), facing, action state, object seed, hit points, mana, gold, experience,
checksums of bag, statistics, equipment, abilities and skills, of the whole player record
(19,504 bytes), of **the whole object pool (947,968 bytes)**, of the task table and of
the controller state, and the 32 controller bytes of the tick.

At hub tick 300 the two memories were also diffed (`rigcompare.py memdiff --a … --b …`):
the heap's block list is identical (111 blocks, same addresses, sizes and callers); 0
bytes differ in code; the object pool differed in 5 pointer words when the rig's
frame-timed boot script was used (finding 4) and in none of the compared ticks with the
tick-keyed one.

## Step 3 — play (Ran)

Scripts are written by two tools, so that they play the same in the rig and here:

- `tools/recomp/playscript.py` — the boot route, then in the first level: walk a square,
  strike, open and close the pause menu, open the pause menu's load entry (the card is
  searched, no save is found) and leave it; a level change into a level with monsters
  (the request is written into `g_pendingLevel`, as the game's own code does), seeded
  random walking and striking; the level change back.
- `tools/recomp/pilot.py` — a script cannot look at the game; this tool does it for the
  script. It runs the native build to a memory dump, reads the player's and the
  creatures' positions from the object pool, and writes the next piece of script: the
  stick direction that walks the player toward a creature (turning aside when a trial
  run shows no headway), then strikes while it re-aims every 60 ticks. 56 native runs of
  about 6 s each wrote the fight below.

All runs: `boot-rig --script S`, then `boot-native --script S --replay`, then
`boot-compare`. Results of 2026-10-12, level `valor`:

| Scenario | Episode | Ticks | Result |
|---|---|---|---|
| **Walk, strike, level change, random play, return** (`playscript.py --no-menus --ticks 1800`), the player record also logged in 77 pieces | hub | 299 | all 104 columns identical except the record piece 0x4a00–0x4aff at tick 7 |
| | valor (opening cutscene to tick 1,171, then random play; a message box stops the ticks at 1,341 and is dismissed) | 1,909 | all simulation columns identical, the object pool included; controller bytes differ at tick 1 (a stick byte left over from the load); cosmetic seed differs at 47 ticks |
| | hub again | 419 | **all identical** |
| **The same with menus** (`playscript.py --ticks 2400`): pause menu opened and closed, load entry opened (two cards searched, "no save" shown), left with the back button | hub | 339 | all identical, pool included, except the player record at tick 7 |
| | valor | 2,509 | all simulation columns identical, pool and player record included; cosmetic seed differs at 617 ticks |
| | hub again | 319 | **all identical** |
| **Fight** (`pilot.py --hit-points 100000`, continued with `--weaken 6`): walk 1,100 units around obstacles to a creature, 1,900 ticks of blows exchanged (the creature from 228 to 118 hit points, 22 blows taken), the creature then weakened by a poke and killed, a walk over the place | valor | 5,010 | all simulation columns identical at every tick: tick, shared seed, position, facing, state, object seed, hit points (999,959.8 → 999,092.9 on both), mana, gold, experience, bag, stats, equipment, abilities, skills, whole player record, task table, controller; the object pool identical at 4,983 ticks and different in one window of 27 (finding 6); cosmetic seed different from tick 1,218 |

What the fight needed that a real player would not: a level-1 character dies of one blow
in that level (seen: hit points 32.8 to 0 at tick 2,482, the level restarts), so the
script pokes the character's hit points once before the first blow, on both machines,
and later the creature's.

### Findings

1. **Two driver replies shift the whole heap.** Without the USB keyboard driver's version
   word and the headset driver's packet size in their init replies, the two libraries
   take other paths: an allocation of 0x680 bytes at 0x36b3a0 is missing and every later
   heap block lies 0xd00 lower. Nothing in the simulation columns shows it; the object
   pool does, through every pointer it holds. Found with the block-list diff, fixed in
   `iop.cpp` (*runtime service*).
2. **The controller is one blank late on the console.** The first comparisons had every
   press one tick early here. The I/O processor reads the controller at the blank and
   its copy reaches main memory during the frame, after the game has read its buffer;
   the rig shows exactly one tick of lag. `iop.cpp` now delivers the state of the
   previous blank (`--opt pad-delay=0` for none) (*runtime service*).
3. **A scripted press cannot be put on the same tick on two machines.** A script acts at
   a vertical blank. When a frame of the game runs late on one machine, the press lands
   one tick earlier or later relative to the simulation there. The rig ran late at tick
   1,986 of the fight level (entering new scenery; the native clock does not charge CPU
   time per instruction, so nothing runs late here), a stick release moved by one tick,
   and from that tick on position, seed and pool differed. The same script agrees for
   the 1,985 ticks before. Leaving a menu has the same weakness: the frame in which the
   menu closes relative to the button differs, and a button still held counts as a new
   press on one machine only (seen: a spell cast at the first tick after the load
   screen). This is *timing*, not translation. The cure is the replay: the rig logs the
   32 bytes the controller delivered in every displayed frame (column `padraw`, the
   library's read buffer at 0x7cbc00), and the native run hands the game the same bytes
   for the same tick — and, while the tick stands still on both (menu, message box), for
   the same frame of that tick (`--opt pad-replay=FILE`, `iop.cpp`). All results above
   are with the replay.
4. **Frame-timed presses in the front end change draw-side state that later sits in the
   pool.** With the rig's `boot-to-hub.rig` (taps every 40 frames) the simulation columns
   agree for 659 hub ticks, but five pointers in creature objects (+0x98, +0x114) point
   at different 0x620-byte entries of a table near 0x795000: the entries were handed out
   in another order because the presses fell on other ticks. Hence the tick-keyed boot
   script (*timing*).
5. **The cosmetic generator follows sound.** `g_cosmeticSeed` (documented as outside
   the sync hash) is reseeded from the frame counter by a cutscene and then first drawn
   at tick 1,218 on the rig and later here; its draws come from sound and ambience code,
   and `sound_null.cpp`'s timing is not the emulator's. It differs for part of every
   level with sound events and agrees again after the next level start (*timing, per
   machine by the game's design*).
6. **One short-lived object.** In the fight the pool checksum differs in one window of
   27 consecutive ticks (3,886–3,912) and is identical before and after, with every
   other column identical throughout. Not dumped; an effect object that draws from the
   cosmetic generator is the likely cause (*not located*).
7. **One tick of the player record in the hub.** Record bytes 0x4a00–0x4aff (ability
   button and weapon-trail state, `docs/player.md`) differ at hub tick 7 and at no other
   tick; cause not determined (*not located*).

No divergence found was a translation error. The 301 functions the automatic sweep could
not drive were not re-tested function by function; what play adds for them is that the
code reached by a boot, three level loads, menus and a fight computes the same pool,
player record and seeds as the original.

## Step 4 — robustness of the translation at scale

- **Indirect jumps and calls outside the tables** (Ran): none. `rt_call` stops the run
  with the address when a target has no entry; in every run of this day (about 90 boots,
  three levels, menus, the fight) it never did.
- **Code that exists only as data** (Ran): the SDK's three kernel-mode blocks are still
  not run (their `SetSyscall` registrations are dropped; alarms and delays work through
  the timer interrupt instead). Nothing else of that kind appeared.
- **The ERX modules** (Not reached): `BG/0ERX` has `LIBINSCK.ERX` (23,769 bytes),
  `NG_INSCK.ERX` (3,341) and `DNAS_NET.ERX` (1,863,761). They are relocatable EE code the
  network set-up loads; offline play never loads them and they were not translated.
  What it takes: apply their relocations for a fixed load address, give `recomp.py` a
  second input with its own function list (the modules have no `ghidra_funcs.tsv`; entry
  points can come from their export tables and `jal` targets), and add their entries to
  the call table so that the game's calls through the modules' function pointers land
  in translated code. `tools/recomp/disc.py` extracts them (`extract --all '*.ERX'`).

## Step 5 — the boundary for what others add

### Renderer interface

`rta::VideoSink` (`rt/iface.h`), set in `rta::Hooks::video` by the application that calls
`rta::run()` (build it with `build.py run --main yourmain.cpp --extra … --lib …`). Every
member is a no-op by default. All calls are made under the runtime's one lock, on the
host thread that carries the running guest thread (it changes from call to call); a
pointer passed in is valid until the call returns.

| Call | When | What |
|---|---|---|
| `vif1(words, count)` | once per DMA transfer on channel 1 | the transfer flattened to the 32-bit words the VIF receives: the source chain is followed (call/return stack, tag interrupts); with CHCR.TTE set the upper two words of each tag come ahead of its data, as on the hardware. A transfer can stop at a tag with the interrupt bit and the next one continues the list, so a decoder keeps its state between calls |
| `vif0(words, count)` | the same for channel 0 | VU0 microprogram uploads (one at start-up) |
| `gif(words, count)` | once per DMA transfer on channel 2 (PATH3) | whole quadwords, DMA tags removed |
| `reg(address, value)` | every store to 0x12000000–0x12001fff (GS privileged, 64 bits) and 0x10003000–0x10003fff (GIF and VIF registers, 32 bits) | the raw value; CSR and IMR are also acted on by the runtime |
| `vblank(field, number)` | start of every vertical blank, after the controller buffers are written | `field` is CSR.FIELD after the flip. A windowed application presents here and may block here to pace the game |
| `frame(number, buffer)` → bool | the game calls `gfx_dmaHandler(-1)`: a finished frame's eight draw lists are about to be sent | list heads at 0x6f4070 + (buffer·8 + list)·4, each a chain of nodes linked through the word at +0xc. Return true to take the frame there: the runtime then reports it as sent and no `vif1`/`gif` calls are made for it. Return false and the game's own back end sends the lists through DMA |

A quadword stored by hand into a FIFO (0x10004000, 0x10005000, 0x10006000) arrives as a
four-word `vif0` / `vif1` / `gif` call. Guest memory for a sink: `rta::memory()` (32 MB),
`rta::scratchpad()`, `rta::vu1_micro()`, `rta::vu1_data()` (stores the game makes
straight into VU1 memory land there; data that arrives through VIF1 is the sink's to
apply). Headless, the runtime walks the same data only for what feeds back into the game:
VU0 microcode and the GS `SIGNAL` / `FINISH` / `LABEL` registers, whose interrupt the
game's back end waits for. Volume at the hub, per frame: 55 VIF1 transfers with 68,400
quadwords, 24 GIF transfers with 234,000 quadwords, 4 `FINISH`.

### Sound interface

Three functions in one source file (`rt.h`); `sound_null.cpp` is the silent one and
`build.py run --sound FILE.cpp` links another:

```
bool sound_rpc(u32 server, u32 function, u32 send, u32 send_size, u32 recv, u32 recv_size);
void sound_vblank();     // start of every vertical blank
void sound_report();     // once, at the end of a run
```

`sound_rpc` is offered every RPC whose server the I/O services do not know and returns
false for a server that is not a sound server (0x80000701, 0x000163a5 are). `function`
is the number the game passed; `send` and `recv` are offsets into `g_ram`, `~0u` when the
game gave no usable buffer. `iop_ram()` is the I/O processor's 2 MB: what the game puts
there (`sceSifSetDma`, disc reads to I/O-processor addresses) is in it when the call
that put it returns, so before any RPC that refers to it. `rt_cycles()` is the clock
(294,912,000 per second; one 48 kHz sample is 6,144 cycles). The answer is written
before `sound_rpc` returns; the caller then sleeps 50 µs of virtual time (500 µs with
`--emulator-timing`). The traffic is the table in step 1.

### Network interface

Not wired in this runtime. Offline play does not reach the network library; its ten
entry points used by the game's netcode are the original translated code here and would
reach RPC servers 0x80001101 / 0x80001201, which answer nothing. A network build
replaces those entries with its own list of supplied functions (`tools/recomp/net`,
`hle-net.txt`: `sceLibnetInitialize` 0x365ec0, `sceInetGetInterfaceList` 0x365a08,
`sceInetInterfaceControl` 0x365a90, `sceInetCreate` 0x3654a8, `sceInetOpen` 0x365518,
`sceInetClose` 0x365560, `sceInetSendTo` 0x365830, `sceInetRecvFrom` 0x365670,
`net_loadModules` 0x137a10, `net_linkCheck` 0x13e638). `rta::NetDriver` in `iface.h` is
a reserved shape for the same boundary; nothing calls it. Options for such a module:
`--opt key=value` and `rt_option()`.

### Controller interface

`rta::PadSource` in `rta::Hooks::pad`: `read(port, number, state)` once per port at the
start of every vertical blank (buttons in libpad's bit values with 1 = held, sticks
0–255 with 128 at rest), `rumble(port, small, large)` when the game sets the motors.
What `read` returns reaches the game one blank later. Without a source, the script
(`--script`, `--do`) supplies the state; `--opt pad-replay=FILE` overrides both with
recorded controller bytes. `pad_readPort` 0x17421c is the original code and reads the
library's buffer, which the runtime writes at 0x7cb140 (port 1) and 0x7cb640 (port 2).

## Step 6 — Windows (Read)

**Later the same day this was done**: `docs/issues/native-windows.md` has the Windows
x86-64 build (cross-compiled on the Mac with MinGW-w64, `rt/host_win32.cpp`,
`app/build_win.py`; compiles and links, not run on Windows). What follows is the reading
it started from, kept as it was written:

Not built; nothing was installed. What the sources need:

- `rt/host.h` is the whole host boundary: a thread with a 256 MB stack, a 64-bit file
  read, process exit, sleep. `host_posix.cpp` implements it; a `host_win32.cpp` of about
  the same 50 lines (`CreateThread` with a stack size, `_fseeki64` / `_ftelli64`,
  `ExitProcess`, `Sleep`) is the only new file.
- The rest is C++17 and the standard library (`<thread>`, `<mutex>`,
  `<condition_variable>`, `<filesystem>`, `<chrono>`). Compiler-specific constructs:
  `__builtin_ctz` and `__builtin_expect` (runtime and `recomp.h`), `__attribute__((weak))`
  in the generated `hle_weak.cpp`. clang-cl accepts all three; for MSVC the first two
  have intrinsics and the weak definitions have to become a generated list of the
  replaced functions that are actually supplied.
- Floating point: the build relies on `-ffp-contract=off -frounding-math` and sets the
  rounding mode to toward-zero per guest thread (`fesetround`); the MSVC equivalents are
  `/fp:strict` and the same `fesetround`. Guest memory is read with `memcpy` as
  little-endian, which holds on x86-64 and ARM64 Windows.
- `build.py` calls `clang++` and `nice`; a Windows branch is needed there.
- The memory-card directory uses `%3A` / `%5C` for `:` and `\`, so card paths are valid
  Windows names already.

## Not reached in the continuation

- A save of a character written to the card and loaded again. The load entry of the
  pause menu was exercised (card searched, no save found); the hub's pause menu has no
  save entry, a save point has to be walked to, and that was not scripted. The card
  service's write path is exercised only by the creation of the save directory at boot.
- An item picked up: the creature that was killed left nothing the walk over the place
  collected (gold and bag unchanged on both machines).
- The ERX modules, the function-by-function re-test of the 301 unproven functions.
  (The Windows build exists since: `docs/issues/native-windows.md`.)
- A comparison in which the native run uses its own scripted presses throughout
  (finding 3): it agrees up to the first late frame of the rig, not beyond.
- `--adopt` (a resumed image served by this runtime's services) with input, a level
  change or the card. Tested only at rest: the spike's 2,005-frame comparison still
  passes with the image's 14 clients adopted and the controller buffers written by the
  runtime (`--adopt --opt pad0=7cb140 --opt pad1=7cb640`).

## Speed (Ran)

| Run | Fields | Wall | × real time | Load average |
|---|---|---|---|---|
| native, boot to the hub + 600 ticks, 26 watches logged | 3,035 | 9.3 s | 5.2 | about 50 |
| native, boot + fight (27 watches, controller replay) | 7,608 | 20.2 s | 6.1 | about 35 |
| native, same boot under the heavy job | 3,908 | 972 s | 0.07 | about 400 |
| rig, boot to the hub + play | 9,800 | 161–178 s | 0.9–1.0 | about 35 |

The start-up to the hub is mostly loading and logging; the idle hub figure of the spike
(10.8× with the game's renderer back end feeding a null GS) still stands.

## How to repeat the continuation

```
export RTA_DISC="/path/to/your/disc image.iso"
python3 tools/recomp/recomp.py && python3 tools/recomp/build.py run
python3 tools/recomp/native.py boot --card local/recomp-out/card-test \
        --script tools/rig/examples/boot-to-hub.rig                       # boot alone

S=tools/recomp/examples/boot-to-hub-ticks.rig                             # boot compared
python3 tools/recomp/rigcompare.py boot-rig --script $S
python3 tools/recomp/rigcompare.py boot-native --script $S --replay
python3 tools/recomp/rigcompare.py boot-compare

python3 tools/recomp/playscript.py --out local/recomp-out/play.rig        # menus, level change, play
python3 tools/recomp/pilot.py --out local/recomp-out/fight.rig --legs 40 --hit-points 100000   # the fight
python3 tools/recomp/rigcompare.py boot-rig --script local/recomp-out/fight.rig --frames 10400
python3 tools/recomp/rigcompare.py boot-native --script local/recomp-out/fight.rig --replay
python3 tools/recomp/rigcompare.py boot-compare
python3 tools/recomp/rigcompare.py memdiff --a <rig image> --b <native image> [--words lo:hi]
```

New files of the continuation: `tools/recomp/rt/iop.cpp`, `script.cpp`, `sound_null.cpp`,
`host.h`, `host_posix.cpp`, `iso9660.h`, `iface.h`, `rt.h`, `main_headless.cpp`;
`tools/recomp/native.py`, `disc.py`, `playscript.py`, `pilot.py`,
`examples/boot-to-hub-ticks.rig`; `rigcompare.py` (boot-rig, boot-native, boot-compare,
memdiff over any two images) and `build.py` (source list, `--sound`, `--main`, `--extra`,
`--lib`) were extended.

## How to repeat (the spike)

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
