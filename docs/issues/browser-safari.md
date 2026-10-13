# Browser build in Safari's engine: the stall on arriving in a level — working notes

Status: **in progress** (2026-10-13). Where the time goes is measured in both engines and
two causes are found; the change for both is written and builds, **its measurements and
the identity proof are not done yet** (see "State" at the end). If this work was cut
off, "State" and "Log" say where.

Question: the page plays at 60 frames a second in Chrome and in Safari's engine, but in
Safari's engine arriving in a level gives up to five seconds without a frame
(`docs/issues/browser-build.md`, "What Safari's engine does differently"). Where does that
time go, and what removes it without changing what the emulated machine computes?

## Summary (so far)

Two things, both made by `perf.patch`'s changes, neither by the disc:

1. **In Safari's engine, giving a block of translated code its place in the program's
   function table costs milliseconds** — 1.3 ms a block on the way to the title, 2.6 ms
   on arriving in the first level, 3.1 ms later (it grows with the number of blocks
   there are), against 2 – 3 µs in Chrome. It is 80 % of everything translation costs
   there. Cause, shown outside the emulator (`local/play-web-safari/out/bench/tablegrow.js`,
   run in the system's JavaScriptCore and in V8): `WebAssembly.Table.grow(1)` costs
   JavaScriptCore time **for every instance that imports the table** — 0.1 µs with none,
   19 µs with 1,000, 530 µs with 5,000, 7.9 ms with 20,000 (V8: 2 – 6 µs throughout).
   Since `perf.patch` every block's instance imports the program's own table (that is
   how blocks call the runtime and each other), and Emscripten's `addFunction` grows
   that table by one place per block. Growing it by 4,096 places costs JavaScriptCore
   the same as growing it by one. **Cure: places for blocks are taken from a run of
   4,096 made by one growth** (`MemoryFunction.cpp`).
2. **In a level that alternates between VU1 programs, every VU1 block is translated
   again at every change of program** — in both engines. `perf.patch` made VU1's block
   code depend on program memory outside the block and therefore throws every VU1 block
   away when VU1's program memory changes. The first level changes program a few times
   in all; the game's largest level (`fire3`) does it many times a frame: of 32,567
   blocks translated in its first 600 frames, **30,505 were VU1 blocks that had been
   translated before with the same content at the same address** (150 distinct contents).
   Chrome ran those frames at 17 a second (load 320) and its page **ended** after about
   70,000 modules (twice, once as a stopped machine and once with the tab gone);
   Safari's engine ran them at 3 a second. **Cure: the blocks of a program are kept
   while another program is in memory** — one executor per content of the whole of
   VU1's program memory — and taken up again when that content comes back
   (`VuExecutor.cpp`).

The disc is not it: a piece of a picked file took 1.2 ms (median) in Safari's engine and
0.9 ms in Chrome in these runs, 124 pieces on arriving in the first level, 0.16 – 0.26 s
in all.

What is left after both, by the same measurements: the translator itself (Play!'s C++
code that turns a block into WebAssembly bytes) is 60 – 85 % of a block's cost in
Chrome and will be most of it in Safari's engine too; 3,660 new blocks of the main
processor's code on arriving in the first level, 2,266 in the largest.

## Measurements of the unchanged build (2026-10-13, 08:20 – 08:35; **load average 310 – 480**: other work on the Mac)

One scripted session, every press queued before the machine starts, so every run sees
the same frames: power-on, title, a new game into the first level (`hub`), a walk and
strikes (the speed work's replay, frame for frame), then at frame 5000 the game is asked
for `fire3` the way its own level changes ask. Per vertical blank the wall clock is
taken; a stretch of frames that takes longer than frames/60 s lost that time to the
host, and the longest time between two vertical blanks is "seconds without a frame".
(These figures are of a loaded Mac and of the tree before play-net.patch's change of
2026-10-13 10:52, which touches none of the files concerned. They are to be taken again
on the quiet Mac; the ratios and the counts are the finding.)

| Unchanged build | Chrome 155 (`c-base-3`) | WebKit 27.2 (`w-base-1`) |
|---|---|---|
| power-on to title (frames 0 – 1200): lost / longest without a frame | 3.7 s / 0.71 s | 30.0 s / 3.6 s |
| arriving in the first level (2486 – 3386): lost / longest without a frame | 1.5 s / 0.55 s | 14.5 s / **4.6 s** |
| first level, standing (600 frames) | 60.0 frames/s | 58.8 frames/s |
| first level, walking (998 frames): lost / longest | 0.27 s / 0.11 s | 4.1 s / 1.1 s |
| arriving in `fire3` (5000 – 5600): frames a second | 17 | 3 (the run was also cut by the display going to sleep) |
| load average | 313 – 360 | 396 – 481 |

Blocks, the same in both engines (the machine is the same): 13,766 modules to the title
(10,226 EE, 3,380 IOP, 154 VU1, 6 VU0) plus 1,753 further instances of an existing
module; 3,660 on arriving in the first level (3,650 EE, 10 VU1) plus 556 instances; 465
while walking; 32,567 in the first 600 frames of `fire3` (2,266 EE, 30,554 VU1 of which
30,505 again). Sizes: median 5 – 8 emulated instructions and 520 – 670 bytes of module, mean
7 – 9 instructions and 750 – 900 bytes (EE), 24 instructions and 1,540 bytes (VU1);
90 % under 1,500 bytes; largest 318 instructions, 45 KB. Translated more than once: no
EE block (the main processor's code is never thrown away in a browser, and the same
code at another address is a second instance of the module, not a second translation);
823 of 3,387 IOP blocks have a content translated before (the IOP has no store by
content); VU1 as above.

Per module, mean microseconds (first level's arrival; medians are about half the means
under this load):

| Stage | Chrome | WebKit |
|---|---|---|
| the translator (C++, block to module bytes) | 323 | 453 |
| `new WebAssembly.Module` (synchronous) | 75 | 157 |
| `new WebAssembly.Instance` (synchronous) | 9 | 30 |
| into the function table (`addFunction`) | 2 | **2,593** |
| first call from the dispatcher (with whatever linked blocks ran on from it) | 33 | 10 |

A sampling profile of the machine's thread in Chrome from power-on to the title
(`out/profiles/boot-base-w1.cpuprofile`): `CBasicBlock::Compile` 390 µs a block, of which
`Jitter::CJitter::End` (the translator's passes and the code generator) 59 %,
`CMemoryFunction` (module and instance) 24 %, the front end that reads the instructions
17 %. No one function stands out in the translator: it is spread over its containers.

## Where things are

| What | Where |
|---|---|
| the change, as a patch for the next release (applied after `play-net.patch`, `play-web.patch`, `perf.patch`) | `tools/play-web/safari.patch` (**not written yet**; until it is, the change is `local/play-web-safari/work-src` against `base-src`) |
| an untouched Play! tree at the commit `build.sh` names (copied from `local/rel.nosync/play-pristine`) | `local/play-web-safari/pristine` |
| the tree as `tools/play-web/build.sh` builds it (made by running that script with `RTA_PLAY_SOURCE`, `RTA_WEB_SOURCE`, `RTA_WEB_BUILD`, `RTA_WEB_SITE` pointing here; patches as of 2026-10-13 10:52), its build and site | `local/play-web-safari/base-src`, `base-build`, `site/release` |
| the tree with the change | `local/play-web-safari/work-src` |
| both with the test aids put in (never the trees the patch is made from), their builds and sites | `base-aid`, `work-aid`, `build-base-aid`, `build-work-aid`, `site/base`, `site/work` |
| harness and results | `local/play-web-safari/out`: `run.py` (one scripted session in a Chrome of its own — profile `chrome-profile`, DevTools 9337 — or in the WebKit window `wk/wk`), `analyze.py`, `serve.py` (port 8976, 127.0.0.1 only), `build.sh`, `aid/` (`apply.py`, `RtaStallAid.cpp/.h`, the speed work's `RtaPerfTest.cpp`), `profrun.mjs`, `bench/`, `data/` (recordings: `<label>.json`, `.frames`, `.recs`, `.disc`, `.trace`, pictures) |

Nothing of the released page is touched: not `tools/play-web/build.sh`, `play-web.patch`,
`perf.patch`, `src/`, `web/`, not `local/play-web-src`, `-build*`, `-site`.

## State (2026-10-13 12:20)

Done: measurements of the unchanged build in both engines (above, on a loaded Mac); both
changes written in `work-src`; the instrumented builds of both trees.

Next, in this order:
1. `run.py chrome work …` and `run.py webkit work …` (the first run of the changed build
   stopped at frame 136: a kept executor's table of blocks was never set up — fixed by
   calling `Reset()` on it, not yet run again).
2. The same sessions of the unchanged build on the quiet Mac, for the before/after table.
3. The identity proof: `data/<label>.trace` and the pictures of the changed build
   against the unchanged one, in both engines (`cmp` of the traces; the speed work's
   `cmptrace.py` reads them).
4. `tools/play-web/safari.patch` from `base-src` and `work-src`, with merge notes; a
   build from an untouched tree with all four patches.
5. Whether to go further at the translator's own cost (blocks translated ahead on
   another thread, or many to a module): by the numbers above it is what is left.

## Log

1. 2026-10-12 22:45: started, stopped a minute later by the coordinator (the usage window
   was kept for the release). Nothing had been built.
2. 2026-10-13 08:00 – 08:50: started again on the released tree. Untouched tree copied;
   the released build made in my own directories with `build.sh`; test aid, harness,
   server. Unchanged build measured in Chrome (three runs: the first two ended in
   `fire3` with the page gone) and in the WebKit window (one run, cut in `fire3` by the
   display sleeping). Table growth shown in JavaScriptCore by itself. Both changes
   written; first run of the changed build stopped at frame 136.
3. 08:50: paused by the coordinator. 12:05: carried on. `play-net.patch` had changed
   (commit 356add2: network and online files only); base tree made again with
   `build.sh`, my change carried over as a diff, both instrumented builds made again.
   My server (port 8976) had been closed by the coordinator and was started again.
