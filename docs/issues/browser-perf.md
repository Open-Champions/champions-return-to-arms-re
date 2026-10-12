# Browser build: making it cheaper to run — working notes

Status: in progress (2026-10-12). The summary is the state; the rest is the record.

Question: how much of the machine thread's 9 – 12 ms and the video thread's 5 – 7 ms per
frame (`docs/issues/browser-build.md`) can be taken out of the browser build, so that it
holds 60 frames a second on computers slower than the Apple M5 Pro it was measured on —
with the picture and the game's simulation unchanged?

## Summary

| Change | State | Machine thread, CPU ms/frame | Proof of unchanged behaviour |
|---|---|---|---|
| Blocks linked with tail calls (a block jumps to the next one instead of returning to the dispatcher); translated code calls the runtime through the program's own function table | in `perf.patch` | title 12.0 → 9.45 at load ~370 (back to back; **not a quiet reading**); dispatcher entries per frame 93,700 → 9,050 (title), 198,700 → 12,300 (first 10 s in the level) | replay pending (the Mac is at load 400) |
| C++ exceptions as WebAssembly exceptions (`-DRTA_WASM_EXCEPTIONS=ON`) | option added, not built yet | — | — |

Everything below "Where the time goes" was measured on the unchanged build.

## Where things are

| What | Where |
|---|---|
| the changes, as a patch against the tree `tools/play-web/build.sh` makes | `tools/play-web/perf.patch` |
| my Play! tree with the changes / the same tree without them (both with the test aid) | `local/play-web-perf-src`, `local/play-web-perf-base` |
| builds: changed, unchanged, changed + WebAssembly exceptions | `local/play-web-perf-build`, `-build-base`, `-build-eh` (all `--profiling-funcs`, Release) |
| the test site (one directory per build variant) and its server | `local/play-web-perf-site`, `serve.py --port 8974` started from `local/play-web-perf-out` |
| harness, helpers, results | `local/play-web-perf-out`: `perf.mjs` (measure / replay / calibrate in a Chrome of its own, profile `chrome-profile`, DevTools port 9334), `prof.mjs`, `prof2.mjs` (profile summaries), `cmptrace.py`, `stopgo.c` (the slow-computer stand-in), `aid/` (the test aid and `apply.sh`), `results.jsonl`, `profiles/`, `traces/` |

Nothing of the other browser work is touched: not `tools/play-web/web`, `src/RtaWeb*`,
`local/play-web-src`, `-build`, `-site`. The test aid adds two calls to my copies of
`RtaWeb.cpp` and one line to my copy of the page's script; neither is in `perf.patch`.

## How to measure (all on 127.0.0.1, the page titled "AGENT TEST - browser perf (…)")

```
cd local/play-web-perf-out
python3 -B serve.py --port 8974 --site ../play-web-perf-site --disc "<image>.iso" &
./publish.sh <variant> <build dir>                 # copies Play.js/.wasm and the page into the site
node perf.mjs measure <variant> --profile 8 --throttle 2,4,6 --blocks 12 --label <text>
node perf.mjs calibrate <variant>                  # how many presses the way to the title takes
node perf.mjs replay <variant> --taps 11 --shots 1000,3500,4100,4400,4700,4983 --label <text>
python3 cmptrace.py traces/A.trace traces/B.trace ; cmp traces/A.shot1000.rgba traces/B.shot1000.rgba
node prof.mjs profiles/<file>.cpuprofile 40 ; node prof2.mjs profiles/<file>.cpuprofile
```

`measure` reads: frames a second, wall time of both threads per frame (the page's own
counters), CPU time per frame of the three busiest threads of the page's process (`ps -M`
before and after: the machine's thread, the video thread, the next), dispatcher entries
per frame, the share of the emulated processor's ticks that were idle, and the load
average at both ends. `--profile` takes a sampling profile of every worker (200 µs);
`--blocks N` saves the WebAssembly bytes of the N hottest translated blocks.

## The replay (correctness)

Every press is queued before the machine is started (`rtaTap`, `rtaStick`: consumed one
step per vertical blank on the machine's thread), so the game reads the same pad at the
same frame in every run: power-on, 11 presses to the title, a new offline game into the
first level, then a walk in four directions and a diagonal, two strikes, a jump, another
walk — 4,984 frames. The test aid (`aid/RtaPerfTest.cpp`, compiled into both trees)
writes at every frame the game's three random seeds and the player's position as raw
bits, every 32 frames a checksum of the EE's memory (32 MB, scratchpad, VU1 data memory)
and one of the IOP's memory, and takes the canvas at six frames (title, level standing,
walking, striking, the end) — the request for a picture travels through the video
thread's queue, so it is the same picture in every run.

Two runs of the **unchanged** build (loads 119 and 127): seeds and position identical in
all 4,984 frames, the EE checksum identical in all 156 samples, the six pictures
identical byte for byte. The IOP's memory differs between two runs of the same build
from frame 64 on (154 of 156 samples) — a property of the build as it is, not looked
into; the IOP checksum is therefore not a criterion.

## Where the time goes (unchanged build, load 8, hub standing, limiter on, factor 2)

Speed: title 59.7 frames/s, machine 9.8 ms CPU/frame, video 4.9; hub 59.96, machine 9.1,
video 5.5; hub with the limiter off 110.6 frames/s. 193,000 dispatcher entries a frame.

Machine thread, sampling profile (10.7 ms busy per frame with the profiler on):

| What | ms/frame |
|---|---|
| translated blocks, own time | 5.96 (VU1 programs 2.5; EE 1.8; 1.4 the profiler could not attribute; half of it in 90 blocks, the five hottest — all VU1 — 1.75) |
| the EE's dispatcher loop (`CGenericMipsExecutor::Execute`) | 0.89 |
| GIF (`ProcessSinglePacket` 0.66 own; 1.58 with what it calls) | 1.58 |
| VIF unpack (all `CVif::Unpack<…>`) | ~0.9 |
| `CVpu::ExecuteMicroProgram` own | 0.27 |
| JavaScript wrappers of exception-aware calls (`invoke_*`, wasm-to-js, js-to-wasm, stack save) | ~0.6 |
| sound (`CSpuBase::Render`), IOP | 0.4 |

The DMA chain a register write of the game starts (VIF1 → VU1 → GIF) is 5.5 ms of the
8.3 ms spent under the EE's dispatcher. The emulated EE itself is idle 83 – 89 % of its
4,915,200 ticks a frame (title 89 %, level 83 %): Play!'s idle detection works, and the
~190,000 block starts execute only some 700,000 instructions — a handful per block, so
what happens between blocks costs about as much as the blocks.

Video thread (6.1 ms busy): `TransferWriteHandlerGeneric<PSMCT32>` 1.13, `CGSH_OpenGL::
WriteRegisterImpl` 1.03, the register-batch call 0.40, `bufferData` 0.40, `CGSHandler::
WriteRegisterImpl` 0.38, `Prim_Triangle` 0.37, `ProcessHostToLocalTransfer` 0.34,
JavaScript wrappers ~0.3.

## Chrome's CPU throttling and what is used instead

`Emulation.setCPUThrottlingRate` is accepted for the page and answers "Operation is only
supported …" for each of the workers the machine and the video thread run on: it slows
the page's main thread only. Stand-in: `stopgo <pid> <rate>` stops the page's renderer
process (SIGSTOP) for (rate − 1)/rate of every 4 ms, so all its threads get 1/rate of
the time; the browser's GPU process is not slowed.

## Log

1. Taken over from an agent that had copied the tree, built the baseline and written the
   first harness. Own server on 8974.
2. Baseline and profile at load 8. Test aid, replay, calibration (front end up at frame
   585 → 11 presses). Determinism of the unchanged build shown (above).
3. Block linking. First readings under load 200 – 400.
