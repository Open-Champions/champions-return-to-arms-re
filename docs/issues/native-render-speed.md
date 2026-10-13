# The renderer's processor side, made cheaper

Started 2026-10-12, 19:50. The native build's game logic costs about 10 million
instructions a frame; the renderer's processor side (VIF1 unpacking, the VU1 vertex
programs, the GS model: everything above `render/backend.h`) cost 185 million natively and
312 million as WebAssembly (`docs/issues/native-web.md`, section 5). This is the work to
make that part several times cheaper without changing the picture. Every statement says
**Ran** (with what was seen) or **Read**.

This file is kept current while the work goes on: a successor who has only this file
should be able to go on from the section "State and next step".

## Where things are

| What | Where | In the repository? |
|---|---|---|
| this file | `docs/issues/native-render-speed.md` | yes |
| the changes to shared sources | `tools/recomp/render/speed.patch` (merge notes at its head) | yes |
| new files (tools; nothing of the game in them) | `tools/recomp/render/` (listed in the patch's head) | yes |
| my working tree: a copy of `tools/recomp` taken 19:52 with the changes applied | `local/recomp-speed/root/tools/recomp/` | no |
| the copy as taken (what the patch is made against) | `local/recomp-speed/base/` | no |
| my build output (objects, programs, the generated VU1 code) | `local/recomp-speed/root/local/recomp-out/`, `local/recomp-speed/build/` | no - derived from the game |
| recorded streams, logs, results | `local/recomp-speed/streams/`, `local/recomp-speed/out/` | no - derived from the game |

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

VU1 by program entry (first level; instructions per instruction pair): entry 0x42 679,028
pairs a picture at 70; 0x44 495,625 at 76; 0x46 288,859 at 44; 0x48 27,536 at 62; 0x30
14,310 at 40; all others under 0.3 % together. fire3: 0x44 486,152 pairs at 75; 0x48
388,468 at 62; 0x42 380,000 at 76. Title: 0x46 567,784 at 43; 0x42 258,782 at 64. Over
all entries a pair costs 83 instructions in the old translation and about 165 interpreted.

Read from the table: the old measurement's 185 million is confirmed (187). The order of
work is VU1 (over half), then the GS model's handling of what VU1 kicks (a quarter), then
UNPACK (3,000 instructions per code: it is written field by field), then uploads. Draw
state and texture lookup are already small: "cheaper texture identification" is the
upload's copy and hash, 1 to 4 % of the instructions and 3 to 9 % of the cycles.

## State and next step

(21:05) **Step 1 works**: `vu1_translate.py` (+ `vu1_translate_gen.py`, `vu1_simd.h`,
`vu1_fast.h`, `vu1_fast_none.cpp`) translates the three programs; `decode_bench` built by
`speedbench.py build fast` gives the same checksums of vertices and draw commands as the
interpreter on title, hub and fire3-fight, every run in translated code. Whole process:
title 80.8 -> 46.9, hub 187 -> 103, fire3 249 -> 141 million instructions. Next: profile
again, then the GS vertex path, UNPACK, uploads; then the patch, the app, WebAssembly.

How to build and compare (from `local/recomp-speed/`, all at nice 10):

```
python3 -I root/tools/recomp/render/speedbench.py translate streams/fire3-fight.rtavs streams/hub.rtavs streams/title.rtavs
python3 -I root/tools/recomp/render/speedbench.py build fast [--prof]      # root/local/recomp-out/speed/fast/decode_bench
root/local/recomp-out/speed/fast/decode_bench streams/hub.rtavs --loops 5 [--interpret | --old-translation]
```

## Log

- 19:52 copy of `tools/recomp` (`local/recomp-speed/base`, `root/tools/recomp`).
- 19:55 baseline `decode_bench` runs on the existing streams. The machine is very busy
  (load average 340): times mean nothing, instructions and cycles are what is compared.
- 20:00 scenes recorded with my own build of the application (`out/record.py`).
- 20:10 profile of the three scenes before any change.
- 21:05 the ahead-of-time VU1 translation: identical lists on the three scenes at the first
  build; kicks of a translated run are taken out of VU1 memory at once and drawn after the
  run (`Gs::xgkick_take` / `xgkick_flush`), the interpreter still draws them at once.
