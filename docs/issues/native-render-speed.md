# The renderer's processor side, made cheaper

Started 2026-10-12, 19:50; this state 21:36. The native build's game logic costs about 10
million instructions a frame; the renderer's processor side (VIF1 unpacking, the VU1
vertex programs, the GS model: everything above `render/backend.h`) cost 185 million
natively and 312 million as WebAssembly (`docs/issues/native-web.md`, section 5). This is
the work to make that part several times cheaper without changing the picture. Every
statement says **Ran** (with what was seen) or **Read**.

## Result

**The renderer's processor side now costs a fifth of the instructions and under a third of
the cycles, and the lists it hands the graphics backend are the same bytes** (Ran):

| Per picture, millions (instructions / cycles) | title | first level, standing | fire3, a fight |
|---|---|---|---|
| `decode_bench` on the Mac, before (the older translation of the main program) | 76.6 / 13.7 to 14.8 | 176.3 / 30.4 to 32.4 | 232.7 / 38.2 to 41.6 |
| ... now | **16.9 / 3.5 to 4.3** | **34.1 / 8.3 to 9.2** | **42.8 / 10.3 to 10.4** |
| ... factor | 4.5 / 3.4 to 3.9 | 5.2 / 3.5 to 3.6 | 5.4 / 3.7 to 4.0 |
| ... the reference (VU1 interpreted, GS and UNPACK the long way) | 126.0 / 23.7 | 280.0 / 51.6 | 363.4 / 66.7 |
| as WebAssembly under node, to nearest: before (`native-web.md`: the older recording `hub12`, with the bench's checksum) | | 312 / 70.5 | |
| ... now, with WebAssembly SIMD (`hub12` the same way: 63.1 / 21.3) | **26.2 / 7.9** | **56.2 / 15.6** | **68.4 / 18.6** |
| the whole application (game, decoder, OpenGL), before | 89 / 26 | 216 / 44 to 51 | 269 to 280 / 55 to 60 |
| ... now | **31 / 9 to 11** | **73 / 22 to 23** | **88 to 103 / 31 to 33** |

(`decode_bench` rows: `speedbench.py count`, the whole process without the bench's own
checksum, difference of runs of 3 and 9 passes; measured twice, at load average 185 to
215 and at 35: the instructions agree to 0.3 %, the cycles are given as the two values.
With the checksum, as `native-web.md` measured, the first level is 184.4 -> 41.7.
"Before" is the same binary on the old paths, `--old-translation` with `RTA_GS_SLOW=1 RTA_VIF_SLOW=1`; the
binary built from the tree as copied gave 187.2 with the checksum. Application rows:
section "The application".)

- **The proof** (section "Proof"): the vertices and the draw commands of eleven recorded
  streams are the same bytes with the fast paths and with the reference, by checksum; 15
  pictures of `rta_replay` and 4 pictures of the running application at fixed simulation
  ticks are the same PNG files; the four-wide arithmetic gives the interpreter's bits over
  2 million random operand sets in each of four builds; in WebAssembly the translated
  programs give the lists of that build's interpreter, and with the software rounding
  the Mac's lists bit for bit.
- **What it is** (section "What was done"): the VU1 microprograms translated ahead of time
  to straight C++ with four-wide operations (`vu1_translate.py`); a whole run of triangles
  in one loop in the GS model; one loop per UNPACK format; cheaper bookkeeping of uploads.
- **Delivered as** `tools/recomp/render/speed.patch` (15 files of the shared tree; it
  applies to the tree as it is at 21:26) and eight new files in `tools/recomp/render/`;
  nothing in the shared `local/recomp-out/` was written. Section "The patch".
- **The reference stays**: the interpreter, the general vertex path and the general UNPACK
  are in the tree unchanged and are chosen at run time by environment variables.

## Where things are

| What | Where | In the repository? |
|---|---|---|
| this file | `docs/issues/native-render-speed.md` | yes |
| the changes to shared sources | `tools/recomp/render/speed.patch` (merge notes at its head) | yes |
| new files (tools and headers; nothing of the game in them) | `tools/recomp/render/`: `vu1_translate.py`, `vu1_translate_gen.py`, `vu1_fast.h`, `vu1_simd.h`, `vu1_fast_none.cpp`, `vu1_fast_test.cpp`, `prof.h`, `speedbench.py` | yes |
| my working tree: a copy of `tools/recomp` taken 19:52 with the changes applied | `local/recomp-speed/root/tools/recomp/` | no |
| the copy as taken (what the patch is made against) | `local/recomp-speed/base/` | no |
| my build output: the generated VU1 code (`gen-vu/vu1_fast.cpp`), objects, `bin/rta_app`, `bin/rta_replay`, `speed/*/decode_bench` | `local/recomp-speed/root/local/recomp-out/` | no - derived from the game |
| recorded streams; logs, pictures, helper scripts | `local/recomp-speed/streams/`; `local/recomp-speed/out/` | no - derived from the game |

`local/recomp-speed/root/` is a small stand-in for the repository's root (links to the
executable, the symbol files and `tools/play-net`), so that the build scripts, which find
everything relative to themselves, write into it and never into the shared
`local/recomp-out/` (whose `bin/rta_app` the user's launcher runs and another agent
rebuilds).

## The scenes

Recorded 20:00 from my own build of the application (`local/recomp-speed/out/record.py`:
power-on, the title, a new character, the first level, then levels asked for by name as
`tools/recomp/app/tour.py` does), 14 pictures each, with `--plain` (4:3, no multisampling).
A stream begins with the whole of main memory, so a replay has every texture.

| Scene | Stream (`local/recomp-speed/streams/`) | Per picture |
|---|---|---|
| title screen (backdrop level, logo, menu) | `title.rtavs` | 66,753 vertices, 70 draw commands, 690,757 VU1 pairs in 1,092 runs |
| first level, standing | `hub.rtavs` | 181,625 vertices, 854 commands, 1,226,192 pairs in 1,684 runs |
| fire3, fighting (an insect on the player, a golem beside, lava, sparks, heat haze) | `fire3-fight.rtavs` | 330,321 vertices, 1,454 commands, 1,463,888 pairs in 1,961 runs |
| also: `fire3-start`, `drunare-start`, `drunare-fight` (the arena's opening scene) | | |

fire3 is the heaviest level the application's own measurements found
(`local/recomp-out/app-test/perf/find.txt`). The microprogram memory holds the main
program (pairs 0 to 0x74b, loaded once) and, loaded again every frame, one of two small
programs behind it: at 0x79e (98 pairs; every scene) and at 0x79a (102 pairs; fire3).

## The profile before any change (Ran, 20:10)

`decode_bench` built with `-DRTA_PROF` (`render/prof.h`: the thread's own instruction and
cycle counters read at every change of part, the cost of reading taken off), 4 passes of
each stream after a first one, load average 213. Millions per picture; shares of the
renderer.

| Part | title: instr. | cycles | first level: instr. | cycles | fire3 fight: instr. | cycles |
|---|---|---|---|---|---|---|
| VU1 programs (old translation of the main program) | 41.9 (54 %) | 6.9 | 102.0 (57 %) | 16.0 | 132.9 (56 %) | 20.5 |
| GS model: the packets VU1 kicks (registers, vertices, primitives) | 16.2 (21 %) | 2.9 | 41.9 (23 %) | 7.6 | 70.5 (30 %) | 12.6 |
| VIF1 UNPACK | 14.4 (18 %) | 2.7 | 24.3 (13 %) | 5.1 | 23.3 (10 %) | 4.8 |
| GS: uploads (copy and hash of what was sent) | 2.9 (4 %) | 1.4 | 6.6 (4 %) | 3.3 | 2.8 (1 %) | 1.5 |
| XGKICK: the packet copied out of VU1 memory | 0.7 | 0.2 | 1.8 | 0.7 | 2.9 | 1.0 |
| VIF1 codes other than UNPACK | 1.1 | 0.4 | 1.8 | 1.3 | 1.9 | 1.1 |
| GS: draw state worked out (per primitive group) | 0.5 | 0.2 | 0.9 | 0.6 | 1.5 | 0.8 |
| GS: DIRECT and GIF-channel register data | 0.4 | 0.1 | 0.5 | 0.3 | 0.5 | 0.2 |
| GS: texture looked up | 0.1 | 0.1 | 0.3 | 0.3 | 0.5 | 0.4 |
| **the renderer** | **78.3** | **14.9** | **180.2** | **35.3** | **236.7** | **43.0** |
| the bench itself (reading the stream, 32 MB of memory copied per pass, the checksum) | 3.4 | 4.4 | 8.4 | 11.3 | 14.9 | 20.5 |
| whole process, without the profile's counters | 80.8 | 18.6 | 187.2 | 42.8 | 249.8 | 59.9 |
| whole process, VU1 interpreted (`--interpret`) | 130.3 | 27.3 | 290.9 | 62.2 | 380.7 | 84.3 |

VU1 by program entry (pairs a picture, instructions per pair): first level - entry 0x42
543,222 at 88; 0x44 396,500 at 95; 0x46 231,087 at 56; 0x48 22,029 at 78; all others
under 1 % together. fire3 - 0x44 388,922 at 94; 0x48 310,774 at 78; 0x42 304,000 at 95.
Title - 0x46 454,227 at 53; 0x42 207,025 at 80. Over all entries a pair costs 83
instructions in the old translation and about 165 interpreted. (The profile's first
print counted the first pass's pairs too and showed a quarter more pairs at a fifth less
each; corrected here and in `prof.h`.)

Read from the table: the old measurement's 185 million is confirmed (187). The order of
work is VU1 (over half), then the GS model's handling of what VU1 kicks (a quarter), then
UNPACK (3,000 instructions per code: it is written field by field), then uploads. Draw
state and texture lookup are already small: "cheaper texture identification" is the
upload's copy and hash, 1 to 4 % of the instructions and 3 to 9 % of the cycles.

## What was done

### 1. The VU1 microprograms translated ahead of time

`tools/recomp/render/vu1_translate.py` (decoder, the programs in a stream or in the
executable) and `vu1_translate_gen.py` (analysis, code writer) write
`local/recomp-out/gen-vu/vu1_fast.cpp`: one C++ function per microprogram - the main
program (pairs 0 to 0x74b) and the two small ones the game loads behind it (0x79a, 0x79e).
The older translation (`Vu1::write_translation`) calls the interpreter's step with every
pair a constant, 83 instructions a pair; this one is code per pair, 10.

- **Registers are local variables for the length of a run**: a float register is a
  vector of four (`vu1_simd.h`: NEON, SSE2, WebAssembly SIMD, or plain C++), integer
  registers are integers; they are loaded when the function is entered and stored when it
  is left. Blocks are C++ labels, branches with their delay slots are `goto`s.
- **A pair** is written as the interpreter executes it: the upper half's result into a
  temporary from the state before the pair, then the lower half, then the result written
  (so the upper half wins when both write a register, and a partly written register is
  merged with what it held before the pair). The I register is loaded after the upper half
  has read it.
- **The unit's numbers** (`vu_in`, `vu_out` of `vu1_step.h`: exponent 255 is the largest
  number, exponent 0 is zero, results too small are zero; `MAX` / `MINI` compare bit
  patterns): kept exactly. Two things make them cheap. (a) A forward analysis over the
  blocks finds, per register and field, where a value is certainly the result of an
  arithmetic instruction (or of `ITOF`, or `vf0`, or a copy of such): `vu_in` leaves such a
  value as it is and is not applied to it (`v4_in_clean`; not used in a WebAssembly build
  that computes to nearest, where a result can be an infinity). Only the fields an
  instruction writes have to be known. (b) On AArch64 the processor's flush-to-zero mode
  (FPCR.FZ) is switched on while a translated program runs: it reads an operand with
  exponent 0 as zero and gives zero for a result with exponent 0, which is `vu_out` and
  half of `vu_in` (the other half, exponent 255, is three vector operations). `Vu1::run`
  checks ten cases around the smallest normal number once before it trusts the mode, and
  `vu1_fast_test.cpp` compares everything over random operands (below). The interpreter
  does not use the mode. SSE does the masking itself: x86's bit of that name keeps a tiny
  result when it is exact.
- **Rounding** is toward zero as before: `Vu1::run` puts the thread in that mode, and NEON
  and SSE vector arithmetic follow it like scalar arithmetic. `XGKICK` puts the thread's
  own mode back while the GS model takes the packet (`vu1_fast_kick`), as the interpreter
  does.
- **MAC and status flags**: the interpreter records every arithmetic result with its
  cycle and looks back four cycles when a flag is read. The translator walks back from
  each of the 9 MAC / status readers and 23 clip readers over every path. Where all paths
  end at one instruction four or more pairs back, with no divide or `WAITQ` nearer (a
  wait adds cycles and makes nearer results visible), the reader takes that instruction's
  result from a variable: all 9 MAC readers and 14 of the clip readers. Otherwise the
  instructions found are recorded as the interpreter records them and the reader looks
  back in that history (`vu1_mac_seen`, `vu1_clip_seen`). The same walk is made from
  every way out of the translated code (an end bit, a place handed to the interpreter):
  whatever runs next - another program, the interpreter - may read flags, so the last
  results before a way out are recorded too (48 of the 620 arithmetic pairs in all). A
  record that nobody can read is the only thing left out; what a reader sees is the same.
- **The divider**: Q changes 7 (13) cycles after a divide. Kept as in the interpreter (Q,
  the result on its way, the cycle it arrives) but looked at only where Q is read, at a
  divide and at `WAITQ`; inside a block the translator knows whether a divide of the same
  block has arrived and writes no test. The cycle counter is one addition per block.
- **What is not followed is handed to the interpreter** at that pair with the machine in
  the same state: an instruction the interpreter does not know either, a branch in a
  delay slot, an end bit on a branch or on a delay slot, a jump outside the program, a
  computed jump to a place that is not an entry (the one `JR` of the main program is in
  code no entry reaches). Nothing in the three programs needs it: over all recorded
  streams every run stays in translated code. A program that never ends is handed over
  after 3 million pairs (the interpreter gives up after 4 million).
- **Entries**: the 76 pairs of the main program's jump table, the start of a program, and
  every entry seen in the streams given. An entry it was not made for returns at once and
  the run is interpreted.
- **At run time** (`vu1.cpp`): a translated program is used while the microprogram memory
  holds the bytes it was made from (a hash, checked again only for the programs a change
  touches: the game loads a small program every frame, the main one is 15 KB);
  `Vu1::use_fast = false`, or `RTA_VU1_INTERPRET=1` in the environment, interprets
  everything.

### 2. The GS model's vertex path

- `Gs::triangle_run`: a whole PACKED run of triangles, strips or fans (97 % of what VU1
  kicks is strips with UV, RGBAQ and XYZF2) is read in one loop instead of one call of
  `packed()` and `kick()` per quadword: no state comparison per vertex, no function call
  per vertex, vertices written three at a time into a piece of memory of the run and
  added to the list in one piece. Once the first triangle of a strip has settled the
  state, the queue is kept as the two vertices already made, copied as blocks from where
  they lie; the last two are put back into the queue when the run ends, so whatever
  follows finds the registers and the queue as `kick()` would have left them.
- A kicked packet is read where it lies in VU1 memory, not copied to a buffer first
  (unless it runs round the end of the memory).
- Everything else (sprites, lines, register lists, anything with other registers in the
  run, the 2-D layer of a wide picture primitive by primitive) goes the way it went.
  `RTA_GS_SLOW=1` sends everything that way.

### 3. UNPACK

`Vif1::unpack_fast`: one loop per format (S, V2, V3, V4 of 8, 16 and 32 bits, signed or
not, with the offset or the difference mode, with a write cycle that skips) instead of
one decision per field: every UNPACK the game sends. Masked ones and filling write
cycles go to the old function, and `RTA_VIF_SLOW=1` sends all there.

### 4. Uploads

"Which texture is this" was already cheap (0.2 % of the frame). What cost was
`Gs::start_transfer`: for every one of the 340 uploads of a frame it listed and sorted
the GS blocks the rectangle writes and searched that list for every other upload set in
the rectangle's span, to find the sets the upload replaces - as much work as hashing the
3.5 MB. Now the list is kept per kind of rectangle, and a table of the blocks sets start
at is asked block by block. The copy and the hash of what was sent are as they were.

## Proof (Ran)

"The same" below means the same bytes. The reference is everything on the old paths:
VU1 interpreted, every vertex through `packed()` and `kick()`, kicked packets copied
first, every UNPACK through the old function (`--interpret` with `RTA_GS_SLOW=1
RTA_VIF_SLOW=1`, or `rta_replay --reference`).

| What | Compared | Result |
|---|---|---|
| vertex lists and draw commands, `decode_bench` (a checksum over every vertex, another over every field of every draw command; first pass, and all of 3 passes) | 11 streams: my six (title, hub, fire3-start, fire3-fight, drunare-start, drunare-fight), the older `hub12`, `pole` (the fight whose joints held another drawer's data), `haze` (fire3 with heat haze), the graphics work's widescreen `fight169` and `hub169` (the 2-D layer's layout active) | all 11 the same (`local/recomp-speed/out/identity.sh`, `identity.txt`); every run in translated code, none finished by the interpreter |
| whole pictures, `rta_replay --png` at 1280 x 896, blanks 3, 8 and 13 | title, hub, fire3-fight, drunare-fight, fight169 | 15 PNG files the same (`out/pictures.sh`, `pictures.txt`) |
| whole pictures of the running application at four simulation ticks (the tick-keyed route of `app-test/pole-rec.rig`: title, first level, two in the fight in valor), 1280 x 896 | fast paths against `RTA_VU1_INTERPRET=1 RTA_GS_SLOW=1 RTA_VIF_SLOW=1` | 4 PNG files the same (`out/det.txt`) |
| the SSE2 form end to end: `decode_bench` built for x86-64 and run under Rosetta | title, hub, fire3-fight: translated, its own reference, and the ARM build | the same checksums all three ways |
| the four-wide operations of `vu1_simd.h` against `vu_in` / `vu_out` / `vu_add` ... of `vu1_step.h`: 22 kinds of operation, operands drawn so that exponent 0, exponent 255, results below and beyond the range and both zeros come up constantly (`vu1_fast_test.cpp`) | NEON with the processor's flush-to-zero mode; NEON masking itself; plain C++; SSE2 (x86-64 under Rosetta) | 2,000,000 sets of four operands each: 0 differences, and the same reference checksum (8f0d16669cbff80b) on ARM and x86 |
| WebAssembly under node, to nearest, SIMD: translated against that build's interpreter | title, hub, fire3-fight, fire3-start, drunare-fight, fight169 | the same (`out/identity-wasm.txt`). (Its lists differ from the Mac's, as `native-web.md` says: that build rounds to nearest) |
| WebAssembly with VU1 rounded toward zero in software (`-DRTA_SOFT_RZ_VU1`): translated | hub, fire3-fight | the Mac's checksums (f17b4f8de2deca9b, 503fb8869067848c): bit-identical lists, as before with the interpreter |
| the patched copy of the shared tree, built with no translation at all (`vu1_none.cpp`, `vu1_fast_none.cpp`) and with the generated file | hub; fire3-fight | the same checksums |

What the proof does not cover: streams are 14 pictures each of six places plus five older
ones; levels not recorded were not compared (a program path no stream runs is translated
by the same rules but was not executed). `fast_left` (runs the interpreter had to finish)
is printed by `decode_bench`, `rta_replay` and is 0 everywhere.

## Results in detail (Ran)

### Where the instructions are now

The profile again (`speedbench.py build fastprof --prof`, 6 passes, load 110 to 190).
Millions per picture, instructions (cycles); the table of "The profile before any change"
for comparison.

| Part | title | first level | fire3 fight | was (first level) |
|---|---|---|---|---|
| VU1 programs | 5.7 (1.5) | 11.4 (3.0) | 14.3 (3.7) | 102.0 (16.0) |
| GS model: the packets VU1 kicks | 3.9 (1.0) | 9.7 (2.6) | 17.4 (4.4) | 41.9 (7.6) |
| VIF1 UNPACK | 3.0 (0.8) | 5.3 (1.6) | 4.8 (1.3) | 24.3 (5.1) |
| GS: uploads | 1.9 (1.3) | 4.2 (3.2) | 1.7 (1.3) | 6.6 (3.3) |
| VIF1 codes other than UNPACK | 1.0 (0.4) | 1.8 (0.8) | 1.6 (0.5) | 1.8 (1.3) |
| GS: draw state | 0.5 (0.2) | 1.0 (0.5) | 1.4 (0.6) | 0.9 (0.6) |
| GS: DIRECT and GIF-channel register data | 0.4 (0.1) | 0.6 (0.3) | 0.5 (0.2) | 0.5 (0.3) |
| GS: texture looked up | 0.1 (0.1) | 0.3 (0.3) | 0.4 (0.4) | 0.3 (0.3) |
| XGKICK | 0.05 | 0.2 | 0.2 | 1.8 (0.7) |
| **the renderer** | **16.5 (5.4)** | **34.6 (12.6)** | **42.3 (12.4)** | **180.2 (35.3)** |
| the bench itself (the stream read, 32 MB copied per pass, the checksums) | 3.4 (4.5) | 8.7 (11.8) | 15.4 (21.1) | 8.4 (11.3) |

A VU1 pair costs 8.2 to 9.8 instructions (83 in the older translation, about 165
interpreted). Cycles moved by a fifth between runs with the machine's load (the first
level's 12.6 was 10.2 an hour earlier); instructions did not move.

### WebAssembly

`em++` 6.0.12 and node 26 are on the machine; nothing was downloaded.
`speedbench.py build wasm-fast --wasm --flag=-msimd128 --no-old` (under a minute: the
generated file is 336 KB of C++ and links in seconds), `speedbench.py count wasm-fast
STREAM --no-check`.

| Per picture, millions (instructions / cycles), whole node process without the checksum | title | first level | fire3 fight |
|---|---|---|---|
| to nearest, SIMD, translated ahead of time | 26.2 / 7.9 | 56.2 / 15.6 | 68.4 / 18.6 |
| the same build, VU1 interpreted | 134.8 / 24.6 | 288.9 / 51.1 | 368.6 / 67.7 |
| VU1 toward zero in software (`-DRTA_SOFT_RZ_VU1`; lists bit-identical to the Mac's), translated | | 151.9 / 30.8 | |
| ... the same build interpreted | | 404.5 / 67.4 | |

Against what was there before, on the stream and in the way `native-web.md` measured it
(`hub12.rtavs`, the bench's checksum included, which is 8 million instructions and 11
million cycles of each figure):

| `hub12`, per picture, millions (instructions / cycles) | before (`native-web.md`, section 3) | now |
|---|---|---|
| Mac | 185 / 43.3 | 42.7 / 21.4 |
| WebAssembly, to nearest | 312 / 70.5 (no SIMD, the older translation) | 63.1 / 21.3 (SIMD) |
| WebAssembly, VU1 toward zero in software | 406 / 97.9 | 162.7 / 44.5, list checksum 0b7cb8dbc0366a59 as on the Mac |

**Not measured: the old WebAssembly build on my three scenes.** I built it
(`speedbench.py build wasm-old --wasm --vu old`): Binaryen had not finished the older
translation's one function after 17 minutes and I stopped it.

So the WebAssembly renderer is 1.6 times the Mac's instructions (it was 1.7), and the
page's verdict in `native-web.md` ("what would change the verdict": a real translation
with SIMD and a cheaper vertex path) has what it asked for: the decoder is 56
million instructions a frame as WebAssembly, where the bench measured 312 for it and the
page's whole process was 297 (the emulator page: 227 to 287). **Not run: the page
itself** (`web/build.py page --vu-fast FILE --flag=-msimd128` is written, not built). The exact-arithmetic build gains less (2.7 times) because there
every add and multiply is the software family, field by field; a four-wide form of
`soft_rz.h` is not written.

### The application

My build of `rta_app` (the tree as copied plus the patch, linked against the copied game
objects), `--plain`, 1280 x 896, not paced, 600 pictures per place after the same route
(`local/recomp-speed/out/appperf.py`); the whole process - game, decoder, OpenGL - by
`proc_pid_rusage`; two runs, load 110 to 220. The fight is not the same fight twice (it
is played by script, not by tick), so its figures spread.

| | title | first level | fire3 fight |
|---|---|---|---|
| instructions / cycles per picture, now | 30.7, 30.8 M / 9.4, 10.7 M | 72.7, 73.5 M / 22.3, 22.9 M | 87.9, 103.4 M / 31.0, 33.2 M |
| the same binary on the paths as they were (`RTA_VU1_OLD=1 RTA_GS_SLOW=1 RTA_VIF_SLOW=1`) | 88.6, 89.8 M / 25.7, 27.2 M | 215.0, 216.0 M / 44.0, 51.0 M | 268.7, 280.2 M / 54.8, 59.5 M |
| on the reference paths | 137.3, 138.2 M / 28.5, 34.5 M | 318.1, 323.4 M / 66.3, 76.2 M | 394.0, 406.2 M / 85.4, 86.5 M |
| processor time per picture over all threads, now / as they were | 4.1, 4.4 / 10.8, 11.1 ms | 8.9, 9.4 / 14.3, 37.7 ms | 12.3, 12.8 / 20.1, 21.1 ms |
| pictures a second not paced, now / as they were (they follow the load: two runs) | 208, 499 / 22, 80 | 111, 199 / 33, 101 | 80, 139 / 53, 68 |

The application's own figures by stage, a run from power-on with 9,000 of its 11,800
pictures standing in the first level (`out/appstage.py`; whole-run averages):

| | decoder: its own processor time per picture | decoder: wall time | pictures a second | load |
|---|---|---|---|---|
| not paced, now | 3.86 ms | 4.90 ms | 187 (171 in the level) | 109 |
| not paced, as it was | 9.92 ms | 11.07 ms | 90 (81 in the level) | 44 |
| paced at 59.94, now | 4.13 ms | 7.03 ms | 46.2; 85 % of the pictures stood their two refreshes | 74 |
| paced at 59.94, as it was | 16.19 ms | 20.26 ms | 37.3; 59 % stood their two refreshes | 102 |

The machine was never free (other agents' builds, emulators and windows), so neither
paced run held 59.94: the pictures that were late waited in the main thread's swap
(15 to 18 ms "in OpenGL and the swap" a picture in both runs, stalls up to 0.4 s), which
this work does not touch. What it changed is the decoder's place in that: at load 100 the
old decoder needed 16 ms of processor time and 20 ms of wall time a picture - more than a
frame - and the new one 4 and 7. From the cycles, at this Mac's full clock the decoder is
about 2.0 ms a picture in the first level and 2.3 ms in the fire3 fight, where it was 7.2
and 9.2 (**inferred** from 9.2 / 10.3 and 32.4 / 41.6 million cycles at the 4.5 GHz
`native-web.md` reckons with, not measured as time).

Of the application's 73 million instructions in the first level the decoder is now 34,
the game side about 10, and the rest is the main thread's OpenGL work and the copies of
the picture path: the decoder is no longer three quarters of the frame but under a half.

## What is left on the table

In the order of what it would give (first level / fire3, of 34.6 / 42.3 million):

1. **The GS model's strips, 9.7 / 17.4 M.** A settled strip costs 75 instructions a
   vertex (conversion of five numbers, three 32-byte copies, the copy of the run into
   the list). Converting the fields four at a time and writing straight into the list
   (the vertex list would have to be sized before, which touches `rebuild_state` and the
   layout calls) could halve it. Sprites (particles), lines and everything DIRECT still go
   quadword by quadword (about 4 M in fire3): a sprite loop like the triangle one is not
   written - the field / weave decisions of `kick()` make it longer.
2. **VU1, 11.4 / 14.3 M, 9 instructions a pair.** Left in: one flag record per vertex in
   every loop whose last arithmetic instruction is within reach of the program's end (the
   record could be made once at the way out); `vu_in` of a matrix register on every use
   where the compiler does not hoist it (a shadow register made at the load would);
   the integer side (addresses masked to 10 bits and registers to 16 at every step).
3. **UNPACK, 5.3 / 4.8 M**: 32 instructions a vector; with the widening four at a time it
   would be a third.
4. **Uploads, 4.2 / 1.7 M and a quarter of the first level's cycles**: the hash (2.1 M,
   0.6 instructions a byte: a wider hash would be a third), the copy (1.3 M; upload sets
   that replace each other inside a frame are freed and made again, with their memory),
   0.8 M of bookkeeping. 3.5 MB a frame are sent again by the game whatever is done here.
5. **WebAssembly with exact VU1 arithmetic**: a four-wide `soft_rz.h`.
6. Outside this work: the picture path's copies and the OpenGL thread, now over half of
   the application's frame.

## Found on the way

- **`cur_path` after a texture is sent again.** When `rebuild_state()` asks for a texture
  the machine still has (`restore_texture`), the packet goes through `gif(3, ...)`, which
  sets `cur_path = 3`, and nothing puts it back: the rest of the VU1 packet being read is
  marked `made_by` 1 (built on the CPU) and, in a wide picture, treated as 2-D by the
  layout. One draw command of the hub recording shows it (the command checksum found it).
  `triangle_run` reads the path after the state is made and gives the same; not changed,
  it is `gs.cpp`'s owner's.
- **Upload sets that are never drawn with are never cleared** (`start_transfer` clears a
  set only when it was used since its last upload): a texture sent every frame and not
  drawn grows by its size every frame. Read, not seen to happen (memory is steady in the
  runs here); not changed.
- **A branch in a delay slot**: the interpreter takes it (after one instruction at the
  first branch's target), the older translation's comment says it is not taken. The game's
  programs have none; the new translation hands such a place to the interpreter.
- `python3 -I` does not put a script's directory on the path: `vu1_translate.py` adds it
  itself for its second half.

## The patch

`tools/recomp/render/speed.patch`, made against the tree as copied at 19:52; **Ran**
21:26: it applies to a fresh copy of the shared tree as it is now (of its 15 files only
`app/build_win.py` had changed since; its hunk applies with an offset), and the patched
copy builds `decode_bench` without a translation and with one and gives the same lists
(hub f17b4f8de2deca9b, fire3 503fb8869067848c). **Not built: the Windows program**
(`build_win.py` only gains the job; the SSE2 form it would compile was built for x86-64
macOS and run under Rosetta: translated, reference and the ARM build give the same
checksums on title, hub and fire3-fight).

| File | Change |
|---|---|
| `render/vu1.h`, `vu1.cpp` | the run-time side of the translation (`use_fast`, which programs match, `vu1_fast_kick`, the flush-to-zero check); `micro_changed(first, count)`; decoding and the older translation's hash only when the interpreter is needed |
| `render/vif1.h`, `vif1.cpp` | `unpack_fast`; MPG passes its range; profile scopes |
| `render/gs.h`, `gs.cpp` | `triangle_run` and five lines in `gif()`; `xgkick()` reads the packet where it lies; `start_transfer`'s kept block lists and `set_at`; profile scopes |
| `render/renderer.h`, `renderer.cpp` | the four environment switches; the renderer's own VU1 memories aligned |
| `render/replay_main.cpp` | `--reference`, `--old-translation`, the report line |
| `render/build.py`, `app/build.py`, `app/build_win.py`, `web/build.py` | one more job: `gen-vu/vu1_fast.cpp` or `vu1_fast_none.cpp` (`web`: `--vu-fast FILE`) |
| `web/decode_bench.cpp` | instruction and cycle counters, the checksum of draw commands, `--no-check`, `--list`, `--old-translation`, the profile |
| `web/web_main.cpp` | `--interpret-vu` also switches the new translation off |

After merging, once: `python3 tools/recomp/render/vu1_translate.py --elf SLUS_209.73
--stream local/recomp-speed/streams/fire3-fight.rtavs --stream
local/recomp-speed/streams/hub.rtavs --out local/recomp-out/gen-vu/vu1_fast.cpp --report`,
then `python3 tools/recomp/app/build.py`. Without that file everything builds and runs as
before, with the fast paths of the GS model and of UNPACK on. Run-time switches (environment, read once):
`RTA_VU1_INTERPRET=1`, `RTA_VU1_OLD=1`, `RTA_GS_SLOW=1`, `RTA_VIF_SLOW=1`.

## How to repeat

```
cd local/recomp-speed                                    # everything at nice 10
S=root/tools/recomp/render/speedbench.py
python3 -I $S translate streams/fire3-fight.rtavs streams/hub.rtavs streams/title.rtavs   # root/local/recomp-out/gen-vu/vu1_fast.cpp
python3 -I $S build fast                                 # root/local/recomp-out/speed/fast/decode_bench
python3 -I $S count fast streams/hub.rtavs --no-check                         # instructions and cycles per picture
RTA_GS_SLOW=1 RTA_VIF_SLOW=1 python3 -I $S count fast streams/hub.rtavs --no-check --old-translation   # ... as it was
python3 -I $S build fastprof --prof && root/local/recomp-out/speed/fastprof/decode_bench streams/hub.rtavs --loops 7   # by part
sh out/identity.sh                                       # eleven streams, fast against reference
sh out/pictures.sh                                       # rta_replay pictures, fast against --reference
python3 -I $S build wasm-fast --wasm --flag=-msimd128 --no-old && python3 -I $S count wasm-fast streams/hub.rtavs --no-check
sh out/identity-wasm.sh
clang++ -std=c++17 -O2 -ffp-contract=off -frounding-math -I root/tools/recomp/render root/tools/recomp/render/vu1_fast_test.cpp -o build/test/t && build/test/t 8
(cd root && python3 tools/recomp/app/build.py --no-game && python3 tools/recomp/render/build.py replay)   # my rta_app, rta_replay
RTA_DISC=IMAGE python3 -B out/appperf.py fast            # the application; out/record.py recorded the scenes
sh out/mkpatch.sh                                        # speed.patch from base and root; copies the new files into tools/recomp/render
```

## Log

- 19:52 copy of `tools/recomp` (`local/recomp-speed/base`, `root/tools/recomp`).
- 19:55 baseline `decode_bench` runs on the existing streams. The machine is very busy
  (load average 340): times mean nothing, instructions and cycles are what is compared.
- 20:00 scenes recorded with my own build of the application (`out/record.py`).
- 20:10 profile of the three scenes before any change.
- 20:25 the ahead-of-time VU1 translation: identical lists on the three scenes at the first
  build; kicks of a translated run are taken out of VU1 memory at once and drawn after the
  run (`Gs::xgkick_take` / `xgkick_flush`), the interpreter still draws them at once.
  (Taken out again at 20:33: reading the packet where it lies, at once, is cheaper than
  copying it, and it is one way for both.)
- 20:30 `Gs::triangle_run`, `Vif1::unpack_fast`. One difference found by the command
  checksum and kept as the reference has it: when making a draw's state sends a texture
  again (`restore_texture`, GIF data of "path 3"), `cur_path` stays 3 for the rest of the
  packet being read, so the triangles of that one VU1 packet are marked `made_by` 1
  (built on the CPU) in the reference. `triangle_run` reads the path after the state is
  made, as `kick()` does, and gives the same. It looks like a small fault of the model
  (the path should be put back after the restore); it is `gs.cpp`'s owner's to decide.
- 20:35 the shared tree's files that the patch touches are unchanged since my copy.
- 20:40 the settled strip in `triangle_run` (the compiler had kept the three vertices of
  a triangle as forty separate values in registers: copying them as blocks by address
  halved the loop); the processor's flush-to-zero mode for translated programs (hub VU1
  16.2 -> 12.0 million instructions); the written-blocks list of an upload kept.
- 20:48 `vu1_fast_test.cpp`: four kinds of `vu1_simd.h`, 0 differences each.
- 20:50 eleven streams identical (`out/identity.sh`).
- 20:52 `render/build.py`, `app/build.py`, `web/build.py` take the translation; my
  `rta_app` and `rta_replay` built with it.
- 20:55 to 21:16 the application measured twice in three configurations
  (`out/appperf.py`); its pictures at four simulation ticks the same with the fast paths
  and the reference (`out/det-fast.rig`).
- 21:05 the upload bookkeeping (`set_at`); cleanliness per written field in the
  translator; `--elf` (the main program from the executable: same hash as from a stream).
- 21:08 WebAssembly: `wasm-fast` built and measured; translated equal to interpreted in
  it; with the software rounding the Mac's lists. 21:22 the SSE2 form built for x86-64 and
  run under Rosetta: the ARM build's checksums.
- 21:20 to 21:31 the application's stage times, not paced and paced, now and as it was.
- 21:26 the patch applied to a fresh copy of the shared tree and built there (in the
  session's scratch directory; removed again). `app/build_win.py` added to the patch: it
  needs the new job too.
- 21:32 final sources: `decode_bench` rebuilt, eleven streams the same once more;
  `rta_app` and `rta_replay` rebuilt, the 15 replay pictures the same once more.
- 21:34 the old WebAssembly build's link stopped after 17 minutes in Binaryen (by its
  process number); the new build measured on `hub12` instead, as `native-web.md` did.
- 21:36 the patch made a last time and compared: the eight new files and `speed.patch`
  in `tools/recomp/render/` are the working tree's; the translator run from the shared
  tree with the command of the patch's head writes the same `vu1_fast.cpp` byte for byte
  as the one everything here was measured with (into `local/recomp-speed/out/check/`),
  and refuses to write outside `local/`. Nothing of mine is running; nothing was written
  into the shared `local/recomp-out/`.
