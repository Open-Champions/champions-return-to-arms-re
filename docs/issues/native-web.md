# The native build in a browser: feasibility spike

Started and written 2026-10-12. Question: compile the native build of Champions: Return to
Arms (SLUS-20973 v2.00) - the game's code translated ahead of time to C++ (`tools/recomp`)
with our runtime, renderer and sound - to WebAssembly, so that it runs in a browser tab in
place of the emulator page (`docs/issues/browser-build.md`), and say with numbers whether
that makes the browser version cheaper. Every statement says **Ran** (with what was seen)
or **Read**. Nothing derived from the game is in the repository: generated code, objects,
WebAssembly, logs and pictures are under `local/recomp-web/`.

The Mac was never quiet while this was done (load average 270 to 500 the whole time, other
agents' builds and rigs). Times are therefore inflated and are given with the load;
**instructions retired and cycles per frame** of the whole process (which do not depend on
the load the way times do, `docs/issues/browser-perf.md`) are what the comparison rests on.

## The night of 2026-10-12/13: the page with the cheaper renderer (IN PROGRESS - kept current)

(The sections below this one are the afternoon's and stand as they were written; this one
is being filled as the work goes.  Stopped once at 22:50 after a minute's work, taken up
again 07:53.)

**Done so far (Ran):**

- Snapshot `local/recomp-web/src4` = `tools/recomp` as of 2026-10-13 07:55 (the speed work
  merged and the morning's `rt/iop.cpp`, `render/gs.cpp`, `app/pipeline.h` changes), the
  translation `gen2` unchanged (`recomp.py`, `hle.txt`, `recomp.h`, `fpu.h`, `mmi.h` are
  the same files).  `host_web.cpp` got the new `host::interactive_threads` (empty).
  Builds in `local/recomp-web/build4/` (`out/build-night.sh`, `build-night2.sh`; 54 files
  in 31 - 62 s at 10 jobs, links 9 - 17 s now that the VU1 translation is 336 KB):
  `mac-host`, `node-nearest`, `node-zero`, and the pages `page-fast` (game and VU1 to
  nearest), `page-zero` (game toward zero in software, VU1 to nearest), `page-exact`
  (both toward zero in software); all pages with `--vu-fast` and `-msimd128`.
- **Tick for tick, both arithmetics** (`out/cmp4.sh n4 fight3.rig 600`: power-on, front
  end, first level, the fight in `valor`; 27 watches a row): node to nearest == Mac
  `--opt arith=nearest`, node toward zero in software == Mac default: 7,901 rows each,
  byte-identical logs (md5 1f3b8384..., 9f39323e...).
- **A fault in `soft_rz.h` found and corrected**: `add` took the error of the sum with
  the symmetric two-sum, whose intermediate `s - a` goes to infinity when the operands
  have opposite signs and one is the largest number (the value the FPU model clamps to):
  the sum was then not stepped back - one place too large.  The afternoon's test did not
  draw that case.  Now the fast two-sum with the larger operand first; `soft_rz_test.cpp`
  draws the case (the old header: 23,456 differences in `add` and `add, flush`; the new
  one: 0 of 11,202,304 sets in 16 kinds, and node prints the Mac's 16 checksums).  The
  7,901-row session never met it (same logs before and after).
- **The four-wide software family: `web/soft_rz4.h`** (add, subtract, multiply, integer
  conversion with a power-of-two scale; toward zero with flush-to-zero; written with the
  compiler's vector types, so one source is NEON on the Mac and WebAssembly SIMD).
  `soft_rz4_test.cpp` on the Mac against the processor's own toward-zero, flush-to-zero
  mode: **22,403,136 operand sets, 10 kinds, 0 differences**; the node build prints the
  same 10 checksums.  `render/vu1_fast_test.cpp` as WebAssembly with it: 2,000,000 sets
  of four, 22 kinds, 0 differences, reference checksum 8f0d16669cbff80b (the ARM and x86
  builds').  `decode_bench` with it: the Mac's list checksums (hub f17b4f8de2deca9b, fire3
  fight 503fb8869067848c).  It needs one change outside `web/`:
  `web/shared-sources-2.patch` (`render/vu1_simd.h`; applied in my snapshot only).
- What it costs (`out/count-decode.sh`, whole node process per picture, load 50 - 55):

  | decoder as WebAssembly, millions (instructions / cycles) | title | first level | fire3 fight |
  |---|---|---|---|
  | VU1 to nearest | 26.1 / 6.2 | 55.4 / 12.2 | 68.1 / 15.6 |
  | VU1 toward zero, field by field (as it was) | 64.7 / 13.7 | 150.2 / 27.7 | 179.7 / 32.1 |
  | VU1 toward zero, four at a time (`soft_rz4.h`) | 34.3 / 9.9 | 80.8 / 23.6 | 98.2 / 29.5 |
  | (Mac, processor's mode) | 16.6 / 3.8 | 33.8 / 8.0 | 42.8 / 9.6 |

  Honest reading: **46 % fewer instructions, but only 8 - 15 % fewer cycles** - the
  vector form has long chains (a sum is twenty vector operations where the scalar form's
  branches are predicted away), so exact vertices still cost about 11 - 14 million cycles
  a picture more than rounding to nearest.

**Measured in Chrome 155 (Ran, 08:10 - 08:50; `perf.mjs`, results in `out/results.jsonl`
labels n1, m1; the Mac at load 300 - 650, so the times are a floor and the instructions
are what counts).**  Pages built from the UNPATCHED translation (see the fault below);
instructions / cycles per frame of the whole page process, millions:

| | `page-zero` (game toward zero, VU1 to nearest) | `page-fast` (both to nearest) | `page-exact` (both toward zero) | afternoon's page | emulator page with `perf.patch` (quiet Mac) |
|---|---|---|---|---|---|
| title | 50.3 / 15.6 | 49.0 / 16.8 | 59.4 / 19.7 | 156 / 34 | 162 (replay stretch) |
| first level, standing | 90.2 / 26.6 | 87.8 / 25.6 | 114.3 / 36.5 | 297 / 57 | 227 / 57.8 |
| first level, walking and striking | 76.5 / 23.6 | 76.3 / 22.9 | 96.2 / 30.7 | - | 234 |
| the fight in `valor` (lighter scene: 320 draws) | 60.0 / 18.5 | 57.6 / 18.6 | 74.0 / 29.6 | - | - |
| frames a second paced, first level | 59.99 (load 410) | 59.93 (load 316) | 59.99 (load 600) | 49 (load 360) | 60 |
| stand-in 1/2, 1/4, 1/6 (first level, standing; run n1, load 55 - 90) | | 60.0, 46.8, 31.2 | | 30, 15, 10 | 60, 34.6, 22.1 |
| busiest thread, CPU ms per frame (decoder) | 5.1 (load 410) | 5.3 | 8.6 (load 600) | 15 - 18 | 7.85 machine + 5.1 video |

**A fault of this page found by comparing pictures (Ran, 08:55): it was built from the
translation of the UNPATCHED executable.**  The Mac application `rta_app` is translated
with the suggested fix set (`recomp.py --pnach patches/SLUS-20973_4028A55F.pnach
--sections tools/play-net/sections-suggested.txt`: 26 sections, 91 words, figure 27f61e1d -
"what every other build of the game here runs with"), `rta_app_orig` without; my `gen2`
is the unpatched one, as the afternoon's was.  Seen as: the page's pictures at seven
fixed ticks against `rta_app`'s differ in 98 % of the pixels from the first level on (the
character stands elsewhere: (131.6, -96.2) patched, (140.3, -122.5) unpatched, at tick 60
of the first level), and against `rta_app_orig`'s only by what the vertex rounding
explains (0.19 - 0.68 % of the pixels by more than 8 of 255).  **To do next: translate with
the fix set (no film and network entries: the page links neither), rebuild, repeat
identity, table and pictures with it.**

**Written and partly run** (all in `tools/recomp/web/`): the disc check with the emulator
page's sentences (`rta-native.js`, `checkDisc`; nine wrong files through the page's file
input all refused with the right sentence: `playtest.mjs discs`, `out/mkdisctests.py`);
pause (hidden tab, P key, button); a controller through the Gamepad interface with
rumble; the sound worklet gives up a burst of more than 200 ms above its 70 ms reserve;
the memory card is written to IndexedDB every 4 s and when the page is hidden or left;
`app shot NAME.png` script lines post that blank's picture to the test server
(`web_main.cpp`); `perf.mjs --route fight`, `--walk`; `playtest.mjs` (discs, play, card,
pictures).  **Not yet run**: `playtest.mjs play` (file input with the real image, sound
queue, controller, pause) and `card` (save, reload, load).

**Left over to clean when done**: `local/recomp-web/out/disc-tests/` (two files hold
pieces of the disc image).  One thing touched outside my directories, by mistake of the
script and not mine to keep: `local/recomp-out/fight3.rig` has `dump` lines, so the four
runs of 08:06 rewrote `local/recomp-out/pilot/c0.bin`, `c1.bin`, `c2.bin` (memory dumps of
that same script; the afternoon's runs did the same).  Later runs use a copy without them.

## Verdict

**No: this should not replace the emulator page now.** It works - the translated game
boots from power-on in a Chrome tab, draws through WebGL 2 on three threads, reads the
player's disc image in place and takes the keyboard - but it is **not cheaper**:

| First level, standing (Chrome 155, picture 1280 x 896) | native page | emulator page with `perf.patch` | emulator page unchanged |
|---|---|---|---|
| instructions per frame, whole page process | **297 million** | 227 million | 287 million |
| cycles per frame | **57 million** (load 350) | 57.8 million (quiet) | 66 - 68 million (quiet), 66 - 78 (loaded) |
| busiest thread, CPU ms per frame | **15.2 - 18.4** decoder (load 350) | 7.85 machine (quiet) | 9.2 - 10.2 (quiet), 17 - 18 (loaded) |
| the other threads | game 2.8 - 3.4, drawing 1.0 - 1.4 | video 5.1 | video 5.6 - 6.2 |
| frames a second, this Mac | 49 paced, 60 with the limiter off (load 360) | 60 (quiet) | 60 (quiet), 28 - 53 (loaded) |
| half speed (stand-in) | **30** (load 350) | 60 quiet, 36 - 38 loaded | 48 - 53 quiet, 28 loaded |
| a quarter | **15** | 35 quiet, 18.5 loaded | 25 - 27 quiet, 14 loaded |
| a sixth | **10** | 22 quiet | 18 quiet |
| title screen: instructions / cycles per frame | 156 million / 30 - 34 million | 162 million (replay stretch) | 201 million |

(Emulator columns: `docs/issues/browser-perf.md`. The native page could only be measured
on the loaded Mac; its place is between the two emulator columns' loaded figures.)

Why: the premise ("the game side needs 2 ms") is true and carries over - the translated
game plus runtime costs **14 million instructions a frame** as WebAssembly, against some
70 - 85 million for the emulator's EE - but the game side is a twentieth of the frame.
Three quarters of the native page's work is the renderer's CPU side (`tools/recomp/render`:
VIF1, the VU1 vertex programs run instruction by instruction, the GS model): 1.24 million
VU1 instruction pairs and 186,000 vertices a frame in the first level, 185 million
instructions a frame **on the Mac natively** (measured here, section 5) and 312 million as
WebAssembly. The Mac application holds 60 because that work has a thread to itself; so
does the page on a fast Mac, but one thread carries 75 % of the frame, where the emulator
page splits its frame 60 : 40, so the page falls below 60 sooner on a slower computer:
the stand-in gives 30, 15 and 10 frames a second at a half, a quarter and a sixth, which
is 1,000 / (15.5 ms x the factor) - the decoder thread alone.

It also lacks what the native application lacks (`docs/issues/native-app.md`: the
network; films are not linked into the page), and nothing beyond the first level was
looked at in it.

**What would change the verdict** (section 8): a real translation of the VU1 programs
(straight-line code per program path, without the per-instruction bookkeeping of flags,
pipeline and cycle counter that the interpreter-shaped translation keeps), with SIMD; and
a cheaper vertex path in the GS model. If the decoder came down to the cost of the game
side times three or four, the whole frame would be about 100 million instructions - less
than half the emulator page - and both arithmetic questions below are already answered.
That is renderer work, of use to the Mac application as well; none of it is specific to
the browser.

## 1. What there is

| File (`tools/recomp/web/`) | Does |
|---|---|
| `build.py` | `node` (translated game + runtime, headless), `page` (the site), `mac` (the same headless program with the Mac's compiler: the reference). `--src DIR` names the tree, `--arith nearest\|zero` the game's arithmetic, `--vu-arith nearest\|zero` the vertex programs'; the translated game's objects are shared between targets |
| `host_web.cpp` | `rt/host.h` for Emscripten: pthreads with a small stack, the disc image through node's file system or, on a page, through the page's reader (below) |
| `web_main.cpp` | the page's program: `app/app_main.cpp` without Qt (threads, pacing, input, figures) |
| `backend_webgl.cpp` | `render/backend.h` on WebGL 2 (the port of `render/backend_gl.cpp`) |
| `audio_out_web.h` | the sound device of a page: a ring in shared memory |
| `index.html`, `rta-native.js`, `rta-sound-worklet.js` | the page: disc picker, keyboard, memory card in IndexedDB, AudioWorklet, figures, `window.rta` for tests |
| `serve.py` | serves a site on 127.0.0.1 with the cross-origin isolation headers; `--disc` (developer tests) makes an image readable by range requests at `/dev/disc.iso` |
| `perf.mjs`, `stopgo.c`, `rusage.c` | the measuring harness: a Chrome of its own (profile `local/recomp-web/chrome-profile`), the slow-computer stand-in, instructions and cycles of the page's process |
| `soft_rz.h`, `soft_rz_test.cpp` | arithmetic rounded toward zero, with flush-to-zero, on a host that has neither; the test against the processor |
| `decode_bench.cpp` | the renderer's CPU side alone on a recorded stream, for the Mac and for node |
| `shared-sources.patch` | what had to change in `rt/`, `render/` and `sound/` (section 7); applies to the merged tree (16:00) |

My working tree is `local/recomp-web/`: `src2/` (a copy of `tools/recomp` as merged with
the graphics work, about 16:00, with the patch applied) and `gen2/` (its translation) -
what the last builds are made from; `src/`, `orig/`, `gen/` (the copy of 14:00, the
touched files as copied, its translation: everything before the merge); `gen-vu/` (the
VU1 translation, copied), `build/` (objects, programs, sites), `out/` (logs, scripts,
results). The merge changed nothing that was measured: the tick-for-tick logs of the
builds from the merged tree have the same md5 as before it, and `backend_webgl.cpp`
follows the new `backend.h` (fog, moved scissors, surfaces given back; multisampling,
mip maps, anisotropy and replacement pictures are not in the WebGL backend, and
widescreen was not tried).

## 2. Headless under node (Ran)

**It compiles as it is**: no source change was needed for the first build. 54 files (46
generated, 704,728 lines, 31 MB of C++), `em++ -O2 -pthread -fwasm-exceptions` at nice 10
with 10 jobs: **172 s of wall time, 1,663 s summed** (load 390; the Mac's own compiler on
the same files at the same time: 106 s, 970 s). Link 33 s. **25.4 MB of WebAssembly**,
92 KB of JavaScript (28 - 29 MB with the software arithmetic). Emscripten 6.0.12, node
26.11; nothing downloaded (Emscripten built two of its own system libraries into its cache).

**It boots from power-on by the rig's script** (`tools/rig/examples/boot-to-hub.rig`,
then `local/recomp-out/fight3.rig`): the disc image read in place through node's file
system (`-sNODERAWFS`), guest threads as pthreads (workers), C++ exceptions through the
translated frames as WebAssembly exceptions, the memory card as a host directory. Peak
memory 350 - 480 MB (512 MB linear memory is reserved; the Mac build: 60 MB).

**Tick for tick against the Mac build** (same sources, same script, `--watch-file` with
`rigcompare.py`'s 27 watches - seeds, the player, checksums of the 19,504-byte player
record, the 947,968-byte object pool, the task table - one row per displayed frame):

| Pair | Rows | Result |
|---|---|---|
| node to nearest == Mac `--opt arith=nearest` | 2,909 (boot) and 7,601 (front end, first level, 5,170 ticks of `valor` with the fight) | byte-identical logs (same md5) |
| node toward zero + flush in software == Mac default (processor) | the same two sessions; the 7,601-row one again with both builds made from the merged tree | byte-identical logs (and the same md5 before and after the merge) |
| Mac toward zero against Mac to nearest | | differ from row 887: tick 1 of the title's backdrop level, column `pool`; the player's position differs in 5,244 of 7,601 rows |
| Mac with flush-to-zero against Mac without (rounding mode only, as `runtime.cpp` was) | 7,601 | byte-identical: no tiny number reaches a watched value in this session |

**Speed, game side only** (difference of two runs of different length, so start-up and
compilation cancel; first level standing / `valor` after the fight):

| | instructions per frame | cycles per frame | frames per second of its own processor time |
|---|---|---|---|
| Mac native | 10.3 M / 8.6 M | 3.83 M / 3.59 M | 969 / 797 |
| node, to nearest | 14.2 M / 11.5 M | 4.71 M / 4.69 M | 826 / 624 |
| node, toward zero + flush in software | 16.3 M / 14.8 M | 6.49 M / 7.05 M | 555 / 423 |
| (node, toward zero without the flush, earlier build) | 15.6 M / 13.7 M | 5.99 M / 6.46 M | |

So WebAssembly costs 1.2 - 1.3 times the Mac's cycles for the translated game; the
software rounding adds 38 - 50 % to that (of which the flush is 8 - 9 points). Wall time
of the long runs at load 300: 235 - 286 frames a second to nearest, 183 - 203 in software.

## 3. Rounding: does the translated code depend on the host? (Read, then Ran)

**Yes, in exactly two headers.** The generated C++ has no float operation of its own:
every one of the game's 26,000 FPU operations is a call of `fp_add`, `fp_sub`, `fp_mul`,
`fp_div`, `fp_sqrt`, `fp_rsqrt`, `fp_from_int`, the compares and `fp_min` / `fp_max` in
`rt/fpu.h`, whose default ("host") model is the host's IEEE instruction on clamped
operands, in whatever state the host processor is in; and the VU0 interpreter `rt/vu0.h`
(one microprogram, `anim_buildPose`) uses the C operators. `rt/runtime.cpp` puts each guest
thread in round-toward-zero (and, since today, flush-to-zero), which is the Play!
emulator's state. (`-DFPU_PS2`, the integer model, depends on nothing but is another
arithmetic: the console's, not the emulator's.)

**WebAssembly has neither mode.** Emscripten's `fesetround(FE_TOWARDZERO)` returns 0
("done") and changes nothing - the runtime's report now asks the arithmetic, not the
library. So a WebAssembly build as it comes computes to nearest with tiny numbers kept:
exactly the emulator page's "browser arithmetic" (`docs/issues/mixed-arithmetic.md`).
For sync with other builds that leaves two ways, and both are built and proven above:

1. **Everybody computes as the browser does.** `--opt arith=nearest` makes the Mac runtime
   leave the processor alone (the counterpart of the emulator application's
   `--rta-arith browser`). Free on both sides.
2. **The browser computes as everybody else.** `soft_rz.h`: each operation is done to
   nearest, then it is decided *exactly* whether the result lies beyond the true one
   (add: the error of the sum by Knuth's two-sum; multiply, divide, square root: the
   exact product in a double), and if so it steps one place back; the `_fz` family adds
   flush-to-zero (tiny operands read as zero, tiny results zero, compares and min / max
   on flushed operands - FCMP, FMAXNM, FMINNM as FPCR.FZ makes them). `soft_rz_test.cpp`
   **against the ARM processor's own modes: 8,002,304 operand sets, 16 kinds of
   operation, 0 differences**, and the node build of the test prints the same 16
   checksums. Cost: the table above.

Not looked at: an x86 browser (the bits of a NaN that an operation creates differ there;
`mixed-arithmetic.md`, section 6 - the software family normalises nothing in that case).

**The vertex programs (VU1) are a separate question** - they make the picture, not the
simulation. The unit rounds toward zero and the renderer sets that mode around each run;
in WebAssembly it cannot. Measured with `decode_bench` on a recorded stream of the first
level (12 frames, 2.23 million vertices):

| VU1 arithmetic in WebAssembly | vertices against the Mac's | decoder cost |
|---|---|---|
| to nearest (the page's default) | positions differ by at most 0.19 pixel (none by half a pixel), colours by at most 1 of 255; same vertex counts | 312 M instructions, 70.5 M cycles a frame |
| toward zero in software (`--vu-arith zero`, `RTA_SOFT_RZ_VU1` in `render/vu1_step.h`) | **bit-identical lists** (same checksum as the Mac) | 406 M, 97.9 M (+39 %) |
| (Mac native, processor's mode) | reference | 185 M, 43.3 M |
| (Mac native, software) | bit-identical | 285 M, 70.7 M |

## 4. The page in Chrome (Ran)

`perf.mjs measure` drives it: page titled "AGENT TEST - native web (...)", Chrome 155 with
its own profile, window visible, closed afterwards; the server on 127.0.0.1 only.

- **Threads**: the page's main thread (page, disc reader, IndexedDB, sound device); a
  drawing thread that owns the canvas (OffscreenCanvas, every WebGL call direct) and runs
  one turn per task of its worker's event loop, through a message channel of its own; the
  game (runtime and guest threads, pthreads from a pool of 14); the decoder
  (`app/pipeline.h`, unchanged). Pacing by the clock at 59.94 on the drawing thread; the
  wait travels back through the two hand-overs as in the application.
- **Disc**: the image stays where it is. A read goes from the game's thread to the page's
  main thread, which asks its reader - `File.slice().arrayBuffer()` for a picked file, a
  range request for the developer's `/dev/disc.iso` - copies the bytes into the caller's
  buffer and wakes it. To the first level: 275 reads, 41 MB, 0.6 s in all (range
  requests). The executable is copied out of the image into memory. **Not run: the file
  picker** (it needs a person's click); the picked-file path is the same reader interface.
  There is no check that the image is the right disc.
- **WebGL 2 against OpenGL 4.1 core**, what was missing and what stands in
  (`backend_webgl.cpp`, head): (1) **dual-source blending** - the extension
  `WEBGL_blend_func_extended` is in this Chrome and is used, the same shader outputs as
  on the desktop; without it a second way is built in (constant blend colour where the
  destination's factor is a constant of the draw; the fragment's alpha as the factor,
  scaled back for storage by `GL_CONSTANT_ALPHA`, where it follows the source's alpha;
  loses stored alpha above 0x80 in such draws) - `--basic-blend` forces it, **not looked
  at on screen**; (2) GLSL ES 3.00 (precision statements, `gl_PointSize`); (3) a surface
  sampled while drawn into is refused by WebGL: such a draw samples a copy - **none
  occurred** to the first level; (4) nothing else: vertex arrays, samplers, blits, 32-bit
  float depth are there. Calls that would set what is set are left out: 7,900 WebGL
  calls a frame for 865 draws in the first level (drawing thread 0.9 - 1.6 ms).
- **Keyboard**: the application's map. A real key event through the browser (W held
  1.5 s) walked the character from (140.3, -122.5) to (17.1, 16.4).
- **Picture**: title and first level drawn and looked at
  (`local/recomp-web/out/shots/web-title-final1.png`, `web-hub-fix2.png`): the title's
  backdrop, logo and menu; in the first level the ground, the platform, both characters
  textured and lit with their ground shadows, the HUD and the talk prompt. Two faults of
  mine on the way, both fixed: float uniforms shadowed across frames (broken level
  geometry in the first pictures), and draws without a texture that left the last one
  bound (WebGL dropped them as feedback loops when it was the surface being drawn into:
  the characters came out as flat pale shapes). **Not compared side by side with the
  application's pictures**, and nothing beyond the first level was looked at.
- **Sound** (Ran, to the title; Chrome muted, nobody listened): the sound library
  renders into a ring in the shared memory and an AudioWorklet - the emulator page's -
  plays from it; the page's main thread is not on the path. After 25 s: playing, never
  ran dry, **428 ms queued** where 70 ms are asked for: the start-up burst is not given
  up as the desktop device's ring does it (the worklet only corrects its rate by 0.5 %),
  so the delay is too long as it is. The frame's cost with sound on is the same
  (154 M instructions a frame at the title).
- **Memory card** (Ran): the card directory is an IndexedDB mount (IDBFS), written back
  every 4 s. The boot script's card initialisation left 3 files, 129,572 bytes; the
  store held 6 entries (3 files, 3 directories) and still did after the page had been
  loaded again (read without starting the game). **Not run: a game booting from the kept
  card, a save and a load.**

### Figures

`page-nearest`: game to nearest, VU1 to nearest, VU1 main program translated, `-O2`,
Binaryen `-O2`, no SIMD; scale 2 (1280 x 896 on a 1195 x 896 canvas), no sound. Wall
milliseconds per frame are each thread's own counters; thread CPU from `ps -M`. Run
`final2`: the build from the merged tree with both picture faults fixed.

| | fields/s | game / decoder / drawing, wall ms | thread CPU ms | process: instructions, cycles | load |
|---|---|---|---|---|---|
| title | 54.4 (60.0 in three other runs) | 4.3 / 18.3 / 0.5 | 17.6, 4.3, 1.6 | 156 M, 34.1 M | 310 |
| first level | 49.0 | 3.9 / 20.1 / 1.0 | 18.4, 3.4, 1.4 | 297 M, 57.2 M | 360 |
| first level, limiter off | 60.1 | 3.6 / 16.7 / 1.3 | 15.2, 2.8, 1.0 | 300 M, 56.5 M | 356 |
| half speed (ran 50.4 %) | 29.6 / 30.4 off | 7.1 / 33.8 / 2.2 | 15.8, 3.0, 1.2 | 299 M, 56.8 M | 350 |
| a quarter (26.4 %) | 15.3 / 14.7 | 13.0 / 65.4 / 5.1 | 15.7, 2.9, 1.3 | 300 M, 58.2 M | 345 |
| a sixth (18.2 %) | 9.9 / 10.5 | 21.4 / 100 / 8.0 | 15.9, 2.9, 1.4 | 308 M, 57.4 M | 340 |

(The run before it, `final1` - the earlier tree, draws without a texture still being
dropped - at load 285: title 60.0; first level 49.5, 21.2, 8.3 and 5.0 with decoder
thread CPU of 18 - 35 ms and the same 292 - 297 M instructions: the times moved with
whatever else the Mac was doing, the instructions did not.)

A quiet Mac was not available. From the cycles: 57 M a frame is about 13 ms of processor
at this Mac's full clock, the decoder's share about 10 ms, so the first level should
hold 60 on this Mac when it is quiet with a third in reserve (**inferred, not run**; with
the limiter off it reached 60 at load 356), less than the emulator page's busiest thread
has with `perf.patch` (7.9 ms of 16.7). Other builds measured on the way (first
level, instructions per frame): linked without Binaryen 338 M; with `-msimd128` for the
renderer 298 M (-12 %); VU1 interpreted instead of translated 519 M.

Decoder, by its own clock in the first level (build with `--times`, load 380): VU1 runs
24 of 31 ms (1,700 runs a frame), of which the GS work of their kicks 8.5; the GIF
channel 2.2.

## 5. Where the frame goes

`decode_bench` (the renderer above `backend.h`, from `local/recomp-out/render/hub12.rtavs`,
20 passes after a first one): per frame 185,852 vertices, 871 draw commands, **1,235,049
VU1 instruction pairs in 1,717 runs**.

| | instructions per frame | cycles per frame |
|---|---|---|
| Mac native | 185 M | 43.3 M (9.6 ms at full clock: what `native-render.md` gives) |
| WebAssembly (node), same arithmetic to nearest | 312 M (1.7 x) | 70.5 M (1.6 x) |
| translated game + runtime, WebAssembly (section 2) | 14 M | 4.7 M |

The decoder is 150 instructions per VU1 pair natively and 250 as WebAssembly (the Mac's
compiler vectorises the four-wide loops; Emscripten without SIMD does not, and with
`-msimd128` gains 12 %). The "translation" of the main VU1 program is one function of
780 KB that calls the interpreter's step with every pair a constant: it keeps the cycle
counter, the flag rings and the Q pipeline per instruction. (Binaryen needs 2.5 - 5
minutes for that one function at link time, and did not finish it in 37 minutes when the
machine was at its busiest; `--link-opt=-O1` links in 15 s and costs 15 % speed.)

## 6. How to build and run

```
# once: Emscripten is installed (brew, 6.0.12); nothing else is needed
cp -R tools/recomp local/recomp-web/src2 && (cd local/recomp-web/src2 && patch -p1 < web/shared-sources.patch)
python3 local/recomp-web/src2/recomp.py --elf SLUS_209.73 --funcs ghidra_funcs.tsv --out local/recomp-web/gen2
#   (or apply the patch to tools/recomp itself and leave --src and --gen away.  Without the
#    patch `node --arith nearest` builds as the tree is; the page needs it for sound - or
#    --no-sound, not tried - and --arith zero / --vu-arith zero need it)
B="python3 tools/recomp/web/build.py"; S="--src local/recomp-web/src2 --gen local/recomp-web/gen2"
$B mac  $S --name mac-host                    # reference: local/recomp-web/build/mac-host/rta_native
$B node $S --arith nearest                    # local/recomp-web/build/node-nearest/rta_native.js
$B node $S --arith zero                       # the same with toward zero + flush in software
$B page $S --vu local/recomp-web/gen-vu/vu1_translated.cpp      # the site: local/recomp-web/build/page-nearest
#   --arith zero, --vu-arith zero, --flag=-msimd128, --link-opt=-O1, --no-sound, --name NAME

# headless, compared (scripts in local/recomp-web/out: run-mac.sh, run-node.sh, cmp3.sh, bench2.sh)
node --stack-size=3000 local/recomp-web/build/node-nearest/rta_native.js boot --elf SLUS_209.73 --disc IMAGE \
    --card DIR --sym names.tsv ... --script tools/rig/examples/boot-to-hub.rig --watch-file W --log out.tsv

# the page, by hand
python3 tools/recomp/web/serve.py --site local/recomp-web/build/page-nearest    # http://127.0.0.1:8975/
# the page, measured (test server with the developer's disc option, then the harness)
python3 tools/recomp/web/serve.py --site local/recomp-web/build --disc IMAGE --shots local/recomp-web/out/shots &
clang -O2 -o local/recomp-web/build/tools/stopgo tools/recomp/web/stopgo.c; clang -O2 -o local/recomp-web/build/tools/rusage tools/recomp/web/rusage.c
node tools/recomp/web/perf.mjs measure --site page-nearest --throttle 2,4,6 --shots --keys --label NAME
#   --sound, --keep-card, --blend basic, --args times,interpret-vu ; results: local/recomp-web/out/results.jsonl

# the arithmetic test and the decoder benchmark: heads of soft_rz_test.cpp and decode_bench.cpp
```

## 7. Changes needed in the shared sources (`shared-sources.patch`)

All additions that change nothing unless a new name is defined:

| File | Change |
|---|---|
| `rt/fpu.h` | the rounding-dependent operations of the host model go through `FP_ADD` ... `FP_FROM_INT`: the operators, or `soft_rz.h`'s `_fz` family under `RTA_SOFT_RZ`; compares and min / max likewise |
| `rt/vu0.h` | VU0's arithmetic through `vu_add`, `vu_sub`, `vu_mul`, `vu_itof`, `vu_gt` (same rule) |
| `render/vu1_step.h`, `render/vu1.cpp` | VU1's arithmetic through `vu_add` ... `vu_itof`; `RTA_SOFT_RZ_VU1` computes them toward zero in double precision; the `fesetround` calls behind two macros |
| `sound/audio_out.cpp` | three lines: under `__EMSCRIPTEN__` include `audio_out_web.h` |
| `rt/runtime.cpp` | **not in the patch**: its owner has put `--opt arith=nearest` and the `#ifndef RTA_SOFT_RZ` guard in (in the tree since the merge). One thing is still wrong there for a WebAssembly build *without* `RTA_SOFT_RZ`: the line at the start says "toward zero, denormals are zero - the processor's mode", because Emscripten's `fesetround` reports success; that build computes to nearest with tiny numbers kept (its log is byte-identical to the Mac's with `--opt arith=nearest`). The line should ask the arithmetic (1 + 0.75 of a place; half the smallest normal number) or say so under `__EMSCRIPTEN__` |

Found on the way: `rt/runtime.cpp` set the rounding mode but not flush-to-zero (being
fixed in the shared tree; invisible in the sessions compared here, section 2).

## 8. What is left

In the order in which it decides anything:

1. **The decoder's cost** - the verdict. A translation of VU1 that is code per program
   path instead of a constant-folded interpreter step; SIMD; the GS model's per-vertex
   work. Measure with `decode_bench` (it prints a checksum of the lists, so a faster
   decoder is checked against the Mac's bit for bit).
2. Pictures side by side with the application's, and levels beyond the first.
3. **Run what is only written or half run**: the file picker by a person; a game from a
   kept memory card; the sound's delay (428 ms queued) and a listening test;
   `--basic-blend` on screen; the page with the game's arithmetic in software
   (`build.py page --arith zero`: the headless build of it is proven, the page was not
   built again after the last fixes) and with exact vertex programs (`--vu-arith zero`:
   proven in `decode_bench`, not run as a page); `--no-sound`.
4. A quiet Mac, a real slower computer, another browser (the page needs
   cross-origin isolation, OffscreenCanvas with WebGL 2 in a worker, WebAssembly
   exceptions and threads).
5. Everything the application lacks: films, the network (`netshim` would need the
   emulator page's relay path), a disc check, settings, a controller.
6. Smaller: the 512 MB of linear memory reserved (350 - 480 MB used at the peak);
   start-up (the browser compiles 26 MB of WebAssembly: to the title 24 - 30 s of wall
   time on the loaded Mac, most of it the game's own boot script); pacing by the
   display's refresh.

## Log

- 14:00 copy of `tools/recomp`, translation made again (identical). First `em++` build
  of the headless program compiles and boots unchanged.
- 14:15 boot script tick for tick: node == Mac to nearest; Mac toward zero differs at
  row 887. `soft_rz.h` written and proven against the processor.
- 14:30 fight session tick for tick, both arithmetics. Per-frame cost of the game side.
- 14:40 first page: title at 60, first level at 32 (load 400), keyboard. Level geometry
  broken (my uniform shadow, fixed 15:30).
- 15:05 `decode_bench`: the decoder is 185 M instructions a frame natively - the frame's
  cost is the renderer's CPU side, not the game.
- 15:20 flush-to-zero added to the software family at the coordinator's word; proven
  against FPCR.FZ; fight session identical again; the flush changes nothing in it.
- 15:45 final page build measured with the stand-in (section 4).
- 15:55 the pale characters: draws dropped by WebGL's feedback-loop rule; fixed
  (`web-hub-fix2.png`). The shared tree was merged with the graphics work
  (`render/gfx.patch`): fresh copy `local/recomp-web/src2`, translation `gen2`,
  `backend_webgl.cpp` follows the new `backend.h` (fog, moved scissors, surfaces given
  back; not: multisampling, mip maps, replacement pictures). Rebuild and re-check in
  progress: `local/recomp-web/out/build-merged.sh`.
- 16:15 merged tree: Mac, node (both arithmetics) and the page rebuilt; the fight session
  tick for tick again, same md5 as before the merge in both arithmetics; the page
  measured again with the stand-in (`final2`); sound and the memory card run to the
  title. Test browser closed, test server stopped.
