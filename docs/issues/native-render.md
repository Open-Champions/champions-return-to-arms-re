# A picture for the native build

Started 2026-10-12. The native build (`docs/issues/native-recomp.md`) runs the game's own
code but drew nothing. This is the renderer for it: `tools/recomp/render/`. Every statement
here says whether it was **Ran** (with what was seen) or only **Read**; the last section
lists what was not reached.

## Where things are

| What | Where | In the repository? |
|---|---|---|
| renderer sources, build script | `tools/recomp/render/` | yes — ours |
| objects, programs (`rta_replay`, `rta_render`), the translated VU1 program, recorded streams, pictures | `local/recomp-out/` (`obj-render/`, `bin/`, `gen-vu/`, `render/`) | no — derived from the game |

## State (2026-10-12)

**Later the same day** (`docs/issues/native-app.md`): the renderer now runs in the window
program `tools/recomp/app` from power-on. The memory-card screens, the publisher's logo,
the title, the menus, character creation, the loading screen, the first level and a level
with a fight draw and were compared with the emulator's `shotfb` screen by screen. Two
things changed here for that: a display buffer takes the display's size instead of only
growing (`Gs::display_size`), and a texture made before its header was known has its
picture height asked for again (`Gs::texture_for`, `Renderer::set_memory`). Still open:
films, one fault in the fight (a pole of stray vertices), and everything no visited level
shows. `rta_replay` draws a stream recorded in the middle of a session wrongly (the
display registers and uploads from before the recording are missing); its `--list` is
still right.

- **Ran:** the first level (hub) from the resumed memory image draws completely: level
  geometry with textures and point lights, skinned and lit models (player, the woman on
  the platform, butterflies), their shadow surfaces and ground shadows, environment-mapped
  two-pass strips, particles, the present pass, and the HUD (name text, bars, frame, level
  badge). Pictures: `local/recomp-out/render/pic/` (`d-9.png` 2×, `live4x-100.png` 4×,
  `e4x-hud-9.png`, `e4x-mid-9.png` crops at 4×, `final-240.png` from the live program).
- **Ran:** `rta_render`, the translated game + runtime + renderer in a window, paced at
  59.94 pictures a second or free-running; about 105 pictures a second at 4× unpaced with
  other jobs loading the machine (section "Speed").
- **Not reached:** anything the hub does not show (water, trails, glow shells, heat haze,
  a fight), menus and the title (the runtime does not boot that far yet), a comparison
  with the emulator at the same instant, Windows.
- `tools/recomp/rt/` did not build while this was written (it is being split). The window
  program was built and run against a private copy of `runtime.cpp` with stand-ins for the
  three files not yet written (`local/recomp-out/render/rt-snap/`); nothing in `rt/` was
  changed. `python3 tools/recomp/render/build.py app` uses `rt/` itself as soon as it
  builds.

## Decision: interpret (then translate) VU1, draw GS primitives with the GPU

The brief offered (a) a GS-level rasteriser fed by the packets after running the game's
VU1 programs and (b) drawing from the hand-over point with the vertex programs rewritten
as shaders. Chosen: **the game's VU1 microcode is run on the CPU, and what it kicks to the
GS is drawn by the GPU through a model of the GS at the level of what a draw means**
(render targets, textures as the game sent them, blend and test state) — not a software
rasteriser and not an emulation of video memory.

Why:

- **Correct soonest.** One interpreter (60 instruction kinds) covers every 3-D path at
  once, including the ones `docs/spec/render-pipeline.md` marks as read but not verified
  (shadows, particles, two-pass strips all drew on the first complete run). Route (b) is
  one shader and one packet decoder per path. The 2-D layer and the effects built on the
  CPU reach the GS as plain register packets, so the same GS model draws them.
- **Any resolution all the same.** The vertex programs emit screen coordinates in 1/16
  pixel of a 1280 × 448 surface, colours and texel coordinates; those are drawn as
  triangles into a surface of any size. The 3-D scene never exists at 1280 × 448.
- **It leaves route (b) open**, and the first step that way is done: the main program is
  also translated to C++ (below), checked against the interpreter picture for picture.

What it costs: sub-pixel positions are quantised to 1/16 of an original pixel by the
programs' own number format (1/8 pixel horizontally and 1/4 vertically at 4×), and the
depth values are the game's 16-bit ones (interpolated in a 32-bit float buffer).

### What the GS model does instead of emulating video memory

The faults a generic GS emulation had with this game (`tools/play-net/README.md`) are
designed out:

| Fault there | Here |
|---|---|
| textures named 1024 × 1024 whatever their size | a texture is the rectangles the game transferred to an address; its size is what was sent. (Ran: level textures too are named 1024 × 1024 and are 160 × 160, 176 × 128, …) |
| textures re-sent every frame and converted again; foreign blocks in unsent parts | a texture is known by a hash of the bytes sent and where they went (340 uploads, 3.5 MB a frame; 137 distinct textures in the hub, each decoded once). It is decoded from a scratch memory holding only its own rectangles, so unsent texels are zero. Nothing is kept in a video memory between textures |
| 4/8-bit widths not multiples of a block | texel-by-texel addressing in GS memory order for any rectangle (8-bit textures arrive as 32-bit pixels, `docs/formats/model-texture.md`) |
| sprite texel centres (a line at panel edges at 4×) | a sprite's texture coordinates are moved back by half an original pixel: the GS samples at a pixel's corner, the GPU at its centre. For the present pass this makes the mapping exactly 1 : 1 at any output size |
| the picture jumping by a line (interlace offset) | the half line in `XYOFFSET` is dropped when positions are converted |
| interface art at half height, scanline mask | a sprite that draws half a texture row per line out of one half of a picture is drawn from the woven picture: the fragment shader takes line L from row `(L >> 1) + (L & 1) × half`. `half` is half the picture height in the game's own texture header (the size that was sent is rounded up: the HUD frame is sent as 160 × 48 and is 160 × 46) |

Also: a surface the game draws into is a render target known by its base pointer, as wide
as its buffer width and as high as its scissor; one as large as the picture is made at the
output size. A texture that starts inside a surface is that surface with an offset — the
present pass reads the 1280-wide 3-D surface as two 640-wide textures because the GS
cannot name a wider one (Ran: the second starts 320 blocks in).

## The parts

| File | Does |
|---|---|
| `vu1.h`, `vu1_step.h`, `vu1.cpp` | VU1: one instruction pair as an always-inlined function (`vu1_step`), the interpreter around it, and `write_translation`, which writes the main program as C++ calling the same function with every pair a constant |
| `vu1_none.cpp` | linked when there is no translation |
| `vif1.h/.cpp` | VIF1: every UNPACK format with masks, modes and write cycles, the double buffer, MPG, MSCAL/MSCNT, DIRECT |
| `gs.h/.cpp` | GIF packets on the three paths, GS registers, primitive assembly, transfers, textures by content, render targets; writes a `FrameList` |
| `texindex.h` | finds the game's texture headers in main memory (picture heights; the textures a level uploads only once) |
| `backend.h` | the boundary to a graphics API: `FrameList` (textures as RGBA, targets, draws with complete state, vertices) and `Backend` (four functions) |
| `backend_gl.h/.cpp` | the OpenGL backend; the only file with graphics calls |
| `renderer.h/.cpp` | the above as one object with the methods of `rta::VideoSink`; includes nothing of the runtime |
| `stream.h`, `recorder.h` | a file format for what the runtime hands its picture sink, and a sink that records it |
| `replay_main.cpp` | `rta_replay`: plays a recorded stream without the game: pictures, command lists, texture sheets, timings, the VU1 translation |
| `app_main.cpp` | `rta_render`: translated game + runtime + renderer + window |
| `build.py` | `python3 tools/recomp/render/build.py replay` / `app` |

### VU1 (Ran unless marked)

What the interpreter models, each because the programs rely on it:

- one pair per cycle, both halves reading the state from before the pair — **the I
  register too**: a pair with the I bit loads its constant *after* its own upper half has
  read the old one. The programs write `ADDi.x vf1, vf0, I | LOI 2^65` to store the
  previous constant (255) while loading the next; with the load first, the weight-sum test
  of every blended vertex failed and the skinning walked off its data.
- the divider: Q changes 7 cycles after DIV and 13 after RSQRT and the old value is read
  until then (the loops use Q one and two instructions after starting a divide);
- MAC, status and clip flags as seen 4 cycles after the instruction that made them (worked
  out when read: nine places);
- arithmetic rounded toward zero (the programs make GS integers by adding 2^23 and the
  like to a float).

Not modelled: FMAC data stalls, the EFU, integer-register branch hazards — the loop at
instruction 0x117 (`SQI (vi2++)` directly before `IBNE vi3, vi2`) ends after 63 slots only
if the branch sees the incremented register, so the programs do not expect one there.

**Translation.** `rta_replay <stream> --translate-vu local/recomp-out/gen-vu/vu1_translated.cpp`
writes the 1,868 pairs of the main program as one C++ function: every pair is a
`constexpr` record handed to `vu1_step`, branches with their delay slots and end bits are
`goto`s, a computed jump goes through a switch. The compiler folds the decoding away. It is
used only while the microprogram memory holds exactly the program it was made from (a hash
is compared); the floor-decal and trail programs, loaded behind it every frame, are
interpreted. Pictures with and without it are byte-identical (three frames of the recorded
stream compared by checksum); VU1 time went from about 9 ms to about 3.5 ms a frame
(1.24 million pairs).

### VIF1 findings (Ran)

- **The VIF runs ahead of VU1.** A mesh packet's texture coordinates follow its `MSCAL` and
  are unpacked into the strip the program is still building. So a started program does not
  run at its `MSCAL`: `STCYCL` and an `UNPACK` into the output part of the buffer half
  (+0x80 and up) are carried out first, any other code runs the program before it. (Letting
  every double-buffer `UNPACK` pass, as the reference emulator's "delayed microprogram"
  does between DMA tags, was wrong here, where the stream arrives flattened: the next
  packet's input overwrote what a set-up program had yet to read.)
- **Fields a format does not carry must read as zero** (V2: z, w; V3: w). The strip
  programs read the fourth field of three-element rows. With the next element there, as
  another emulator does it, copy loops ran through the constants at 0x3f6.

### The interface to the runtime

`rta::VideoSink` (`tools/recomp/rt/iface.h`) as the runtime's author defined it is enough:
`vif1`, `gif`, `reg`, `vblank`. `frame()` is not used (the game's own back end sends the
lists). What the renderer takes from the machine besides the calls:

- **VU1 memory.** The game stores constants straight into VU1 data memory (qwords 0x3f6,
  0x3fb–0x3fd). `rta::vu1_data()` / `vu1_micro()` must stay the one copy of those stores:
  the sink compares them at every transfer and sends what changed along.
- **Main memory**, read-only, for `texindex.h`: the picture size in a texture's header
  (found by the GS block in its +0x18; of several, the one used last by +0x1c), and —
  **only for a machine resumed from a memory image** — the VU1 program (upload packet at
  0x3e5ec0) and the two textures a level sends once, the environment map and the shadow
  blob, re-sent from their packets (found by the destination block the game patched into
  them). A run from power-on sees all of that arrive and needs none of it.

### The window program

Three stages, each handing a whole frame to the next: the game's threads (the sink only
copies), a decoder thread (VIF1, VU1, GS model, on memories of its own, exactly as when a
stream is played back), and the main thread (OpenGL, the window). Paced, the main thread
holds each picture to 1/59.94 s — not to the display's refresh, which is 120 Hz here —
and the wait travels back to the game. `--serial` decodes on the game's thread instead.

`--test "TEXT"` titles the window "AGENT TEST - TEXT", keeps it small, behind the others
and without keyboard focus or Dock icon; `--offscreen` opens none. Pictures are read from
the renderer's own surface (`--png`, `--at`), never from the screen.

## Compared with the emulator

**Ran**, with the limit that no picture of the *same instant* exists: the emulator build
cannot load the rig's saved state the native image comes from, and the native build cannot
boot to the hub yet. Compared instead with the emulator build's own 4× picture of the same
place a moment after loading (`local/play-out/web-hub-4x.png`; the camera stands 23
original pixels further left there).

| | Native | Emulator build |
|---|---|---|
| average colour, large stone circle | 157, 133, 143 | 160, 135, 145 |
| stone, left circle | 155, 131, 141 | 155, 131, 141 |
| grass left / top | 60, 58, 46 / 49, 50, 41 | 61, 59, 47 / 50, 50, 41 |
| stairs at the top | 165, 140, 148 | 167, 141, 148 |
| HUD: name, bars, frame, badge | same places and shapes, full vertical detail | same |
| characters, stairs, flowers, butterflies, ground shadows | present, same look | present |

Differences seen: none that could be told from the difference in camera and animation
phase. Not a pixel comparison; that needs the same state on both sides (a rig that can
write its GS output, or native boot).

## Speed (Ran)

Apple M5 Pro, hub level from the resumed image, no input, 871 draw commands and 186,000
vertices a picture. Other agents and an art job were using the machine; the load average
is given with each figure.

| Run | Pictures a second | Load |
|---|---|---|
| window, not paced, 4× (2560 × 1792) | 104 | 20 |
| window, not paced, display resolution (2619 × 1964 of 3024 × 1964) | 109 | 20 |
| no window, not paced, 4× / display resolution | 107 / 118 | 22 |
| window, paced, 4× | 59.0 over 360 blanks including start-up (target 59.94) | 20 |
| before the VU1 translation, pipelined, 4× | 64 | 32 |
| before the pipeline, one stage, 4× | 34–42 | 70–200 |

Per picture, pipelined with the translation: game side 1.6–1.9 ms of wall time (translated
game, runtime, the sink's copy), decoder 8–9 ms (of which VU1 about 3.5, the GS work of the
kicked packets 1.2–2.5, uploads 0.7, the rest unpacking and DIRECT packets), OpenGL 2–3 ms
on the main thread. The decoder is the slowest stage, so it sets the rate. Resolution
hardly matters (the GPU is not the limit at these sizes).

Where the next gains are: the GS model's per-vertex work, and VU1 again (the translation
still keeps a cycle counter and writes every register to memory; about 2.7 ns a pair).

## What Windows would need

- **Nothing in the renderer above `backend.h`**: `vu1`, `vif1`, `gs`, `texindex`,
  `renderer`, `stream` are C++17 with the standard library only (`clock_gettime` in two
  timing aids and `<sys/resource.h>`/`unistd.h` in the two `main` files need their Windows
  equivalents).
- **Graphics:** `backend_gl.cpp` uses OpenGL 3.3 functions plus dual-source blending,
  reached through Qt's `QOpenGLExtraFunctions`, so with Qt 6 for Windows and a desktop
  OpenGL driver it should compile as it is. A Direct3D 11 backend is the same four
  functions over the same `FrameList` (about the 330 lines of the OpenGL one): the state
  in a `DrawCmd` is already API-neutral.
- **Window:** `app_main.cpp` is Qt only.
- **The runtime** needs its `host_win32.cpp` (`tools/recomp/rt/host.h`), which is the
  runtime author's.
- The rounding mode is switched with `fesetround` around VU1 runs; MSVC needs
  `/fp:strict` (or `#pragma fenv_access`) for `vu1.cpp` and the translation, and no
  contraction of multiply-add.

## Approximations in the GS model (Read: none was seen to matter in the hub)

- Alpha test with a fail rule other than "keep": only "never passes" is exact (colour
  only / depth only / RGB only); otherwise failing pixels are dropped.
- Blend factor "destination alpha" is taken as 1; a source alpha above 1.0 (0x80) is
  clamped by the 8-bit target; destination-alpha test, `FBA`, `PABE`, fog, dither and
  `AA1` are not applied; `FBMSK` only per whole channel group.
- Region-repeat wrapping is approximate; lines are one output pixel wide.
- Local-to-local transfers are honoured only between surfaces (the heat-haze copy);
  nothing in the hub uses one.
- Textures are never freed (137 in the hub).
- No input: `rta_render` sets no `PadSource`.

## Not reached

- Water, trails and beams, weapon glow shells, heat haze, floor decals, a level with
  fighting: nothing in the hub draws them. The paths are the same interpreter and GS
  model, but no picture was looked at.
- The blend of the present pass with the previous picture (the game's value was neutral).
- Title, menus, loading screens, films (uploads straight into a displayed buffer are not
  handled): the runtime does not boot that far.
- A pixel comparison with the emulator at the same instant.
- A Windows build; a Metal or Direct3D backend.
- Freeing textures; keyboard or controller input in the window.

## How to repeat

```
python3 tools/recomp/render/build.py replay            # rta_replay
python3 tools/recomp/render/build.py app               # rta_render (needs tools/recomp/rt to build;
                                                       #  --rt DIR takes the runtime sources from elsewhere)
B=local/recomp-out
# the native game in a window, from the rig's hub image
$B/bin/rta_render --window 960x720 -- resume --ram $B/rig/image-ram.bin --spr $B/rig/image-spr.bin \
    --regs $B/rig/image-regs.txt --entry 322b48
# a test run: small background window, 4x, timings after 600 pictures
$B/bin/rta_render --test "native renderer" --window 400x300 --unpaced --size 2560x1792 --stop-after 600 -- resume ...
# record a stream while running (frames 2 to 13), then work without the game
$B/bin/rta_render --offscreen --record $B/render/hub12.rtavs --record-frames 2-13 --stop-after 20 -- resume ...
$B/bin/rta_replay $B/render/hub12.rtavs --size 2560x1792 --png $B/render/pic/x --at 9
$B/bin/rta_replay $B/render/hub12.rtavs --list 9            # every draw of that picture with its state
$B/bin/rta_replay $B/render/hub12.rtavs --sheet $B/render/pic/sheet.png 1   # the textures as decoded
# the VU1 main program as C++ (then build again); --interpret / --no-translation go without it
$B/bin/rta_replay $B/render/hub12.rtavs --translate-vu $B/gen-vu/vu1_translated.cpp
```
