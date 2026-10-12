# Browser build: making it cheaper to run — working notes

Status: a first round is done and measured (2026-10-12). The summary is the state; the
rest is the record.

Question: how much of the machine thread's 9 – 12 ms and the video thread's 5 – 7 ms per
frame (`docs/issues/browser-build.md`) can be taken out of the browser build, so that it
holds 60 frames a second on computers slower than the Apple M5 Pro it was measured on —
with the picture and the game's simulation unchanged?

## Summary

**About a fifth of the work per frame is gone, with the picture and the simulation
unchanged.** `tools/play-web/perf.patch` (18 files of the Play! tree, applied after
`play-net.patch` and `play-web.patch`; it dry-runs clean against `local/play-web-src` as
it was on 2026-10-12 11:00). Measured in Chrome 155 on the M5 Pro, first level
standing, resolution factor 2, the Mac quiet (load 8 – 16), one run each, unchanged
build measured twice:

| | unchanged | with `perf.patch` | + `-DRTA_WASM_EXCEPTIONS=ON` |
|---|---|---|---|
| frames/s, limiter on | 59.98, 59.97 | 59.98 | 60.05 |
| machine thread, CPU ms/frame | 9.23, 10.19 | 7.85 | 7.55 |
| video thread, CPU ms/frame | 5.64, 6.18 | 5.08 | 4.88 |
| frames/s, limiter off | 111.5, 94.1 | 132.4 | 137.5 |
| instructions per frame, whole page process (millions) | 287.1, 287.1 | 226.9 (−21 %) | 218.8 (−24 %) |
| cycles per frame (millions) | 65.9, 68.5 | 57.8 | 55.8 |
| title screen: machine / video CPU ms/frame | 5.49 / 2.75, 5.57 / 2.76 | 4.94 / 2.33 | 4.58 / 2.13 |
| a computer **half** as fast (stand-in, below): frames/s limiter on / off | 53.2 / 56.6, 48.2 / 49.6 | **60.04** / 68.5 | **60.01** / 68.4 |
| a **quarter** as fast | 27.2 / 27.1, 24.7 / 27.0 | 34.6 / 34.5 | 34.7 / 33.9 |
| a **sixth** as fast | 18.2 / 18.9, 17.7 / 17.5 | 22.1 / 22.5 | 22.1 / 22.9 |

So the level, which this Mac ran at 60 with a third in reserve, is now held at 60 by a
stand-in for a computer half as fast, where the unchanged build gave 48 – 53. It is not
held at a quarter of the speed (35 frames a second instead of 27).

Times on this Mac move by 10 % between two runs of the same build even when it is quiet
(the two columns of the unchanged build), and by a factor of 1.8 when other work takes
the fast cores. Instructions retired repeat to 0.5 % and are what the changes were
judged by. The same frames in every run (the replay, below), millions per frame:

| Stretch of the replay | unchanged | with `perf.patch` | + WebAssembly exceptions |
|---|---|---|---|
| title screen coming up (frames 1150 – 1650) | 200.6 | 162.4 (−19.0 %) | 154.8 (−22.8 %) |
| first level, standing (3000 – 3900) | 287.9 | 231.8 (−19.5 %) | 222.0 (−22.9 %) |
| first level, walking and striking (3990 – 4900) | 289.7 | 234.3 (−19.1 %) | 224.0 (−22.7 %) |

What is in the patch, with what each part gave in the first level (instructions per
frame of the whole process; each measured against the build before it — the flags and
the linking in one pair of ordinary runs each, whose scene differs by up to 3 % from run
to run, the others on the replay's fixed frames):

| Change | Gain | Where |
|---|---|---|
| VU1's sign and zero flags computed only where VU1's program can read them | −10.3 % | `VuExecutor`, `VuBasicBlock`, `VUShared`, `Ee_SubSystem.cpp` |
| C++ exceptions as WebAssembly exceptions (**an option, off by default**: `-DRTA_WASM_EXCEPTIONS=ON`, needs a build from scratch) | −4.2 % | `Header.cmake` |
| pictures sent to the video memory: a loop per row instead of per pixel | about −4 % (half of the video thread's largest function) | `GSHandler.cpp` |
| VIF unpack straight from the source memory; register writes not looked at twice | −4.4 % | `Vif.h`, `GSHandler.h/.cpp` |
| blocks of translated code linked with tail calls; translated code calls the runtime through the program's own function table | −0.4 % (title −2.2 %) — 94 % fewer returns to the dispatcher, but each cost little | `BasicBlock.cpp`, `deps/CodeGen` |

**Proof of unchanged behaviour** (every build in the tables against the unchanged one):
a tick-exact replay of 4,984 frames — power-on, title, a new game into the first level,
walking in five directions, two strikes, a jump. Identical: the game's three random seeds
and the player's position at every frame; checksums of the EE's main memory, of the
scratchpad and of VU1's data memory every 32 frames (156 each); six pictures of the
canvas (title, level standing, walking, striking, the end) byte for byte. Two runs of
the unchanged build agree with each other in the same way.

**Not shown**: anything beyond the first level; a browser other than Chrome (the linking
needs tail calls — Chrome 112, Firefox 121, Safari 18.2; without them the build falls
back to unlinked blocks by itself, a path that was not run); a real slower computer.

**What is left, largest first**: translated code keeps every register of the emulated
processors in memory (an estimated 5 – 10 % of the whole); the video thread's handling of
register writes (about 16 % of all CPU time, no plan); GIF packet handling (4 – 5 %); the
checks at the start of every VU1 block. Details under "What is left".

## Where things are

| What | Where |
|---|---|
| the changes, as a patch for `patch -p1` in the Play! tree | `tools/play-web/perf.patch` |
| my Play! tree with the changes / the same tree without them (both with the test aid) | `local/play-web-perf-src`, `local/play-web-perf-base` |
| builds: changed, unchanged, changed + WebAssembly exceptions (all Release, `--profiling-funcs`) | `local/play-web-perf-build`, `-build-base`, `-build-eh` |
| the test site (one directory per variant: `base`, `all`, `eh`, earlier `link`, `flags`) | `local/play-web-perf-site` |
| harness, helpers, results | `local/play-web-perf-out`: `perf.mjs` (measure / replay / calibrate in a Chrome of its own: profile `chrome-profile`, DevTools port 9334), `publish.sh`, `mkpatch.sh`, `cmp.sh` + `cmptrace.py`, `prof.mjs`, `prof2.mjs`, `rusage.c`, `stopgo.c`, `aid/` (the test aid and `apply.sh`), `results.jsonl`, `run-*.txt`, `profiles/` (with the hottest blocks as `.wasm` and `.wat`), `traces/` |

Nothing of the other browser work was touched: not `tools/play-web/web`, `src/`,
`local/play-web-src`, `-build`, `-site`. The test aid adds two calls to my copies of
`RtaWeb.cpp`, a file `RtaPerfTest.cpp` and one line to my copy of the page's script;
both trees have them, so they are not in the patch.

## How to measure (all on 127.0.0.1; pages titled "AGENT TEST - browser perf (…)")

```
cd local/play-web-perf-out
python3 -B serve.py --port 8974 --site ../play-web-perf-site --disc "<image>.iso" &
cmake --build ../play-web-perf-build --target Play -j 8 && ./publish.sh all ../play-web-perf-build
node perf.mjs measure all --throttle 2,4,6 --profile 8 --blocks 14 --label <text>
node perf.mjs replay  all --taps 11 --shots 1000,3500,4100,4400,4700,4983 --label <text>
./cmp.sh base-ref all-<text>            # trace and pictures against the unchanged build's
node prof.mjs profiles/<file>.cpuprofile 30 ; node prof2.mjs profiles/<file>.cpuprofile
./mkpatch.sh                            # writes tools/play-web/perf.patch from the two trees
```

`measure` drives the page to the title and into the first level and reads at each: frames
a second, wall time of both threads per frame (the page's own counters), CPU time per
frame of the three busiest threads of the page's process (`ps -M`), **instructions
retired and cycles of the page's process per frame** (`rusage.c`: `proc_pid_rusage`),
returns to the dispatcher per frame, the share of the emulated EE's ticks that were
idle, the load average at both ends. `--profile` adds a sampling profile of every worker
(200 µs), `--blocks N` the WebAssembly bytes of the N hottest translated blocks (read
through the debugger domain after everything else), `--throttle` the slow-computer
stand-in.

`replay` queues every press before the machine is started and records (next section);
it also reads instructions and cycles over three fixed stretches of frames. `calibrate`
finds how many presses the way to the title takes (the front end is up at frame 585:
11 presses, 46 frames apart).

### Why instructions and not times

With other agents' work on the Mac (16 test rigs, three native emulators, an upscaler:
load 20 – 400 for most of the day) the same unchanged build cost 17 – 18 ms of machine
thread CPU per frame in the level instead of 9.2: CPU time itself grew by 1.8, not just
wall time. Cycles per frame stayed where they were (66 – 78 million), so the threads were
running at about 2.5 GHz instead of 4.5 — on slower cores or at a lower clock. Thread
CPU time is therefore no measure on a shared computer; instructions retired per frame
are (unchanged build, level: 282.2 – 289.4 million over six runs at loads 9 – 61, and
287.9 on the replay's fixed frames).

### The slow-computer stand-in

Chrome's CPU throttling (`Emulation.setCPUThrottlingRate`) is accepted for the page and
answers "Operation is only supported …" for each of the workers that the machine's and
the video thread run on: it slows the page's main thread only, which does nothing here.
Instead `stopgo <pid> <rate>` stops the page's renderer process (SIGSTOP) for
(rate − 1)/rate of every 20 ms, so that all its threads get 1/rate of the time; it says
what share the process really ran (quiet series: 50.4 – 51.1 %, 25.7 – 26.2 %,
16.9 – 17.7 %). The browser's GPU process is not slowed. On a loaded Mac the stand-in
still compares builds (same conditions: unchanged 27.6 / 14.1 frames a second at a half
and a quarter, patched 36.2 – 37.7 / 18.5 – 18.8) but its absolute figures are those of
the slowed cores. Its first version (4 ms periods, lost time taken out of the next
running phase) collapsed under load — 4.4 frames a second at "a quarter", the process
having run 8 – 11 % — and those rows are not used.

## The replay (correctness)

Every press is queued before the machine is started (`rtaTap`, `rtaStick`: one step per
vertical blank, on the machine's thread), so the game reads the same pad at the same
frame in every run. The test aid (`aid/RtaPerfTest.cpp`) writes at every frame the
game's three random seeds and the player's position as raw bits, every 32 frames a
checksum each of the EE's main memory (32 MB), the scratchpad, VU1's data memory and the
IOP's memory, and takes the canvas at six frames — the request for a picture travels
through the video thread's queue, so it is the same picture in every run.

| Compared with the unchanged build | Seeds, position (4,984 frames) | EE memory, scratchpad, VU1 data (156 checksums each) | Pictures (6) |
|---|---|---|---|
| unchanged build again (three runs with the aid's first version, two with the present one; loads 18 – 127) | identical | identical | identical |
| linking only | identical | identical | identical |
| + VU1 flags | identical | identical | identical |
| + picture transfer | identical | identical | identical |
| everything (`all-final`) | identical | identical | identical |
| everything + WebAssembly exceptions (`eh-final`) | identical | identical | identical |

Two things about the tool itself. The IOP's memory differs between two runs of the same
unchanged build from frame 64 on (154 of 156 checksums): a property of the build as it
is, not looked into, and not a criterion. And the aid's first version made one checksum
of three memories with xxHash's streaming calls; that value differed between two builds
at frame 0 while each memory by itself was identical (a state on the stack that is not
fully set, most likely). The aid now makes one-shot checksums of each memory; the rows
above were all taken (the first two: retaken) with it, except "linking only", which was
compared with the first version against an unchanged build of the same version.

## Where the time went (unchanged build, level standing, limiter on)

Machine thread, sampling profile at load 8 (10.7 ms busy per frame with the profiler on):

| What | ms/frame |
|---|---|
| translated blocks, own time | 5.96 — VU1 programs 2.5, EE 1.8, 1.4 the profiler could not attribute; half of it in 90 blocks, the five hottest (all VU1) 1.75 |
| the EE's dispatcher loop | 0.89 |
| GIF (`ProcessSinglePacket` 0.66 own; 1.58 with what it calls) | 1.58 |
| VIF unpack (all `CVif::Unpack<…>`) | ~0.9 |
| JavaScript wrappers of exception-aware calls (`invoke_*`, wasm-to-js, js-to-wasm, stack save) | ~0.6 |
| sound and IOP | 0.4 |

- The DMA chain a register write of the game starts (VIF1 → VU1 → GIF) is 5.5 ms of the
  8.3 ms under the EE's dispatcher.
- The emulated EE is idle 83 – 89 % of its 4,915,200 ticks a frame (Play!'s idle
  detection works): the 194,000 block starts run only some 800,000 instructions.
- Translating code is not where the first seconds in a level go: 1,650 – 1,890 blocks in
  the first 10 s cost 0.11 – 0.42 ms per frame, and those seconds need 2 – 3 % more
  instructions than what follows (290.7 – 295.9 against 282.7 – 289.4 million). They are
  slower in time (10.9 against 9.1 ms) because the browser runs each new block in its
  quick first translation until it has optimised it. Keeping compiled modules across
  visits would not change that (a page can no longer store compiled modules), and was
  not built.

Video thread (6.1 ms busy): `TransferWriteHandlerGeneric<PSMCT32>` 1.13, `CGSH_OpenGL::
WriteRegisterImpl` 1.03, the register-batch call 0.40, `bufferData` 0.40, `CGSHandler::
WriteRegisterImpl` 0.38, `Prim_Triangle` 0.37, `ProcessHostToLocalTransfer` 0.34,
JavaScript wrappers ~0.3.

## The changes

### 1. VU1's sign and zero flags (−10.3 %)

Read in the hottest blocks (`profiles/wat`): every float instruction of a vector unit
(ADD, MUL, MADD, …) also computed its sign and zero flags and queued them — always into
an eight-slot "sticky" pipeline (two SIMD loads, a shuffle and a bitmask, then six loads
and three stores for the ring), and into the MAC flag pipeline unless Play!'s analysis
of the block showed that nothing could read them. That analysis assumed that the code
after a block reads the flags of the block's last four cycles — and VU1 blocks are a
few instructions long. It was a third of the memory traffic of the hottest blocks.

VU1's flags can be read by nothing but VU1's own program: the main processor reads
VU0's (CFC2) and of VU1 only the program counter (`HandleVu1AreaRead`). So, for VU1 only
(`SetFlagsElision`, `#ifdef __EMSCRIPTEN__`):

- **Sticky flags** are not kept while VU1's program memory has no instruction that reads
  them: FSEQ, FSOR, or FSAND with one of the sticky bits in its immediate. This game's
  programs read the status with FSAND and immediates 1 and 2 only (four places) and the
  MAC flags with FMAND (five). The memory is looked at again whenever it changes.
- **MAC flags** of a block's last instructions are kept only if the code after the block
  can read them (`CVuBasicBlock::AreTrailingFlagsRead`): on every way on from the block
  (both sides of a branch, up to 48 instructions), is there a flag-reading instruction
  before a float instruction has been four instructions ago? Where the way on is not
  known — the program ends or stops, a jump through a register, the search runs out —
  the answer is "yes", which is what was done for every block before.
- Because a block's code now depends on code outside it, every VU1 block is made again
  when VU1's program memory changes, and a block's code is reused at another address
  only where the answer is the same.

With no flag kept at all, nothing is emitted. The hottest blocks went from about 3,000
lines of disassembly to 1,700.

A first version (no flags at all while the program memory has no reader) did nothing:
this game's programs do read flags. A first plan to judge it by "does the title cost
less" was wrong twice over: title CPU time moved between 7.9 and 10.5 ms for one build.

What it can change that the replay cannot show: across two runs of a VU1 program. Play!
starts every run with its pipeline clock at zero and leaves the queued flags of the run
before in the ring, so a flag-reading instruction that comes before any float
instruction of its own run sees old entries, and which old entries are still in the
ring is now different. Blocks that end a program keep their flags as before, so the
last flags of a run are there either way. Nothing in the first level does this (the
VU1 data memory and the pictures are identical); it is the one place where this change
is not provably the same as before.

### 2. WebAssembly exceptions (−4.2 %; an option, off)

The tree is compiled with `-fexceptions`: every call that an exception could pass
through a handler or a destructor leaves WebAssembly for a JavaScript `invoke_…`
wrapper and comes back. `-DRTA_WASM_EXCEPTIONS=ON` (in `Header.cmake`) compiles and
links with `-fwasm-exceptions` instead: no wrapper is left in `Play.js`, `Play.wasm` is
270 KB smaller. It is an option and off because it changes the flags of every file
(a build from scratch, and Emscripten builds its exception-aware system libraries once)
and needs a browser with WebAssembly exceptions (Chrome 95, Firefox 100, Safari 15.2).
The first build with it took over ten minutes to configure with the Mac at load 400.

### 3. Pictures sent to the video memory (−4 %)

`CGSHandler::TransferWriteHandlerGeneric` — the video thread's largest function, the
game sends its textures every frame — worked pixel by pixel with the position kept in
the object. It now takes a row of the rectangle at a time: the row of the page offset
table, the page number's share of the row and the position are outside the loop over
the pixels. The same pixels are compared and written in the same order; the old loop
stays for a position outside the rectangle's width. The function's share of the video
thread went from 20 % to 13 %.

### 4. VIF unpack and register writes (−4.4 %)

- `CVif::Unpack`, when there is no mask and no filling write (CL at least WL): the values are read from the source memory the
  FIFO stream stands on (`CDirectStream`) and the stream is moved on once at the end
  (`SkipDirect`, which leaves the state `Read` would have left), instead of through the
  stream's 16-byte buffer for every value. Not while a DMA tag is still to be skipped
  or the buffer holds the rest of an earlier transfer. The old loop follows and takes
  whatever is left (and reports "waiting for data" exactly as before).
- `CGSHandler::ProcessWriteBuffer` looked at every register write a second time for
  writes to SIGNAL, FINISH and LABEL; `WriteRegister` now notes whether there was one.

### 5. Linked blocks (−0.4 % in the level, −2.2 % at the title)

Play! links translated blocks on every other platform: a block jumps to the next one
through a patched address. In the browser it did not; every block returned to the
dispatcher. Now a block ends in `return_call_indirect` through the function table at an
index read from two words beside the function (`CMemoryFunction::SetWasmLink`), each
instance of a module with its own words (an imported global), and `LinkBlock` /
`UnlinkBlock` set them. For that, translated code imports the program's own function
table instead of a table of JavaScript wrappers: runtime functions are called by their
address. Whether the browser has tail calls is asked once (`WebAssembly.validate`);
without them the old code is emitted.

Returns to the dispatcher per frame: 93,700 → 9,050 at the title, 194,000 → 12,300 in
the level. The gain is small because a return and a dispatch cost about what the tail
call costs. The first figure I had for it (machine thread 12.0 → 9.45 ms at the title)
was load noise and was withdrawn; a paired run at load 40 – 58 showed 17.8 against
17.5 ms.

## What is left

Shares are of the patched build's CPU time in the level (profile `all-fin2`, load 38;
machine thread 61 % of the two, video thread 39 %).

| What | Share now | What could be done | Size |
|---|---|---|---|
| Translated code keeps every register in memory: each emulated instruction loads its operands from the processor's state and stores its result (an EE loop of 8 instructions: 45 loads and stores; 64-bit values as two halves) | blocks are 58 % of the machine thread (EE 23 %, VU1 20 %, 13 % unattributed) | Play!'s translator already allocates registers within a block for the other platforms; the WebAssembly back end reports "no registers". Giving it registers as WebAssembly locals: integer ones touch 3 matcher entries, the vector ones about 90 (`MATCH_MEMORY128` → `MATCH_VARIABLE128` and the emitters behind them) | estimate 5 – 10 % of the whole; days, not hours; the replay would check it |
| Video thread, register writes: `CGSH_OpenGL::WriteRegisterImpl`, `CGSHandler::WriteRegisterImpl`, the batch call, `Prim_Triangle`, the vertex vector | 43 % of the video thread | not looked at | unknown |
| GIF: `CGIF::ProcessSinglePacket` (one switch per register of every vertex, state in the object) | 8.8 % of the machine thread | a loop per packet format | 1 – 2 % of the whole |
| VU1 blocks begin with up to nine checks for a wait carried over from the block before (`pipeFmacWrite`) | ~7 % of a VU1 block | none found that keeps the timing | — |
| EE dispatcher, what is left of it | 3.4 % of the machine thread | translating whole functions (the project knows 7,732 boundaries) would remove the tail calls too | under 2 % by itself: not worth it before registers |
| Texture transfer | 13 % of the video thread | eight pixels at a time (SIMD) | ~2 % of the whole |
| The VU1 programs as hand-written code | — | would be derived from the game: not for `tools/` | not done |
| Compiled modules kept across visits | — | see above: nothing to gain | not done |

## Log

1. Taken over from an agent that had copied the tree, built the baseline and written
   the first harness. Own server on 8974; baseline and profiles at load 8.
2. Test aid, replay, calibration; the unchanged build shown to repeat.
3. Block linking. First readings at load 200 – 400: a gain reported that was noise, and
   withdrawn. The harness lost its browser twice without a word (it had attached to a
   Chrome that the run before was closing; it now waits for the port to go quiet and
   says so when the browser goes away).
4. Hot blocks read; VU1 flags, in three versions (none at all; sticky only; + the look
   ahead). Instructions retired taken as the measure.
5. WebAssembly exceptions; picture transfer; VIF unpack; register-write scan.
6. A quiet half hour (load 8 – 16): the table at the top, with the stand-in at a half, a
   quarter and a sixth.
7. One `git status` was run by mistake while listing the deliverables (it prints,
   changes nothing); no other git command was run.
