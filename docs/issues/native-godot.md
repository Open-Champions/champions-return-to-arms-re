# The translated game inside Godot (spike)

Started 2026-10-13. Question: can the statically recompiled game (`native-recomp.md`,
`native-app.md`) run inside Godot as its game logic, with Godot doing window, input, sound
and - step by step - the drawing? Everything here says **Ran** (with what was seen) or
**Read**. Kept current as the work goes; a successor needs only this file.

Nothing derived from the game is in the repository. `tools/godot/` holds glue, build
scripts, the Godot project's scripts and shaders. The translated code, the libraries, the
staged project, exported applications, pictures and logs are under `local/godot-spike/`.

## STATE (kept current; newest first)

- **Stage 3, Godot draws: runs (Ran).** `--mode draw`: every draw of the frame's list goes
  through Godot's RenderingServer (`extension/src/rta_drawer.cpp`, one shader:
  `project/shaders/gs_draw.gdshaderinc`). The 11 pictures of the tick-keyed route, drawn
  by Godot, differ from the library's own OpenGL pictures by at most 3 of 255 in a
  channel (mean 0.28 to 0.36), none by more than that. 15.6 ms of processor time a
  picture against `rta_app`'s 5.2 ms on the same route.
- **Stage 2, in a Godot window: done (Ran).** `--mode picture`. Boots from power-on in a
  Godot 4.5.2 window, keyboard through Godot's input (power-on to the first level and
  play by 110 key events), sound pulled by Godot's mixer, the rig's session comparison
  through Godot the same file as the native application's, 11 of 11 pictures identical.
- **Stage 1, the game as a library: done (Ran).** `local/godot-spike/lib/librta_game.dylib`
  (fix set) and `librta_game_orig.dylib` (the game as on the disc), C interface
  `tools/godot/lib/rtag.h`.
- Stage 4 (the scene in 3-D): in work. Stage 5 (export): not started.

## From nothing

```
export RTA_DISC="/path/to/your/disc image.iso"
python3 tools/recomp/app/build.py && python3 tools/recomp/app/build.py --original   # the translated game (objects)
python3 tools/godot/build.py all            # snapshot, library, extension, staged project
python3 tools/godot/build.py lib --original # the unpatched game as a library (for the rig comparison)
python3 tools/godot/run.py import           # once: Godot's import cache (bounded headless editor start)
python3 tools/godot/run.py -- --disc "$RTA_DISC"                 # the game in a Godot window (picture mode)
python3 tools/godot/run.py -- --disc "$RTA_DISC" --mode draw     # Godot draws the frame itself
```

`run.py` starts the Godot under `local/godot-spike/deps` on the staged project
`local/godot-spike/project` (a copy of `tools/godot/project` with `bin/` beside it:
Godot's import cache and `.uid` files stay out of the repository) and points Godot's own
directories at `local/godot-spike/godot-home` (`XDG_*_HOME`, which Godot honours on
macOS): nothing is written to `~/Library`. The options after `--` are at the head of
`tools/godot/project/main.gd`. **The first import**: Godot 4.5.2 can crash when it shuts
down after its first import (godotengine/godot#111645); `run.py import` is the bounded
editor start open-champions-godot uses (`--headless --editor --quit-after 120
--frame-delay 50`) and ended normally here (Ran).

Downloads the Godot side needs (the owner agreed to exactly these; each in its own
directory under `local/godot-spike/deps/`):

| What | From | Size | Check |
|---|---|---|---|
| `godot-editor/Godot_v4.5.2-stable_macos.universal.zip` (Godot 4.5.2 standard editor) | `github.com/godotengine/godot/releases/download/4.5.2-stable/` | 162,276,911 bytes | SHA-512 `0b309feb…2b5d7c0` = the release's `SHA512-SUMS.txt` = the pin in open-champions-godot's CI (checked before it was unpacked or run) |
| `godot-cpp/src` (godot-cpp, Godot 4.5 API) | `github.com/godotengine/godot-cpp`, commit `e83fd0904c13356ed1d4c3d09f8bb9132bdc6b77` fetched by its hash (`git fetch --depth 1 origin <hash>`) | 9.3 MB | `git rev-parse HEAD` = the pin; the extension's CMake refuses any other commit |

Same pins as `open-champions-godot/gdextension/dependencies.json` (copied as
`tools/godot/extension/dependencies.json`). No Homebrew install, nothing else fetched:
godot-cpp is built with the CMake (4.4.4) and Ninja already on the machine, SCons is not
needed.

## Stage 1: the game as a library (Ran)

`python3 tools/godot/build.py snapshot` copies `tools/recomp/{rt,render,sound,app}` and
the compiled translated game (`local/recomp-out/obj-rta_native_fix`, `obj-run`, the VU1
translations of `gen-vu`) into `local/godot-spike/src/` and applies
`tools/godot/recomp.patch`; `build.py lib` compiles that copy with the files of
`tools/godot/lib/` into a dynamic library. `tools/recomp/` itself is not touched (another
agent owns it and changes it meanwhile; `build.py snapshot --refresh` takes it again as
it is then).

What is in the library: the runtime (`rt/runtime.cpp`, `iop.cpp`, `script.cpp`), the
translated game, the renderer's processor side (VIF1, VU1 with both translations, the GS
model, `renderer.cpp`), the OpenGL backend (`backend_gl.cpp`, optional at run time), the
sound core (`sound_rta.cpp`), the game-side picture hooks (`app/gfx_rt.cpp`), the films
(`app/film.cpp`, fix-set library only), the picture path of the application
(`app/pipeline.h`: the sink that copies on the game's thread and the decoder thread).
**Not in it: the network** (`tools/recomp/net`). The translation leaves the network
library's entries open with weak defaults that are the original code, so the game links
and plays offline exactly as before, and nothing in the library can open a socket.

What `tools/godot/lib/` adds (all written for this spike, nothing derived from the game):

| File | Does |
|---|---|
| `rtag.h` | the C interface: `rtag_start` (disc path, data directory, picture and sound options, more runtime arguments), `rtag_step` / `rtag_poll` / `rtag_run` (one vertical blank at a time, or on the library's own clock), `rtag_set_pad`, `rtag_audio_pull` (48 kHz stereo), the frame (`rtag_frame`: draw list with every draw's complete state, new textures and surfaces, optionally the picture as RGBA, the pictures a script asked for), `rtag_memory`, `rtag_info`, `rtag_stop` |
| `rtag.cpp` | the hand-over: the game's thread stands at every blank until it is let go; finished lists wait in a queue of three for the host; the library's own renderer (when a picture size is given) runs on the decoder's thread in a context without a window and writes `app shot` pictures itself |
| `host_godot.cpp` | `rt/host.h` for a machine inside another program: `quit()` does not end the process - the library reports the end and the game's thread stands still for good |
| `audio_host.inc` | the "sound device": the host asks for the sound. Included by `sound/audio_out.cpp` (the one change of `recomp.patch`) |
| `gl_standin/QOpenGLContext`, `QOpenGLExtraFunctions` | Qt's two classes that `backend_gl.cpp` is written against, forwarding to macOS's OpenGL framework (the Windows build does the same over WGL: `app/win/wgl.h`). `backend_gl.cpp` is compiled unchanged, without Qt |
| `gl_offscreen.h`, `gl_offscreen_mac.cpp` | an OpenGL 4.1 core context with no window (CGL) |
| `png_write.h` | pictures as PNG with the system's zlib |
| `scene_tap.h/.cpp` | stage 4 |
| `host_main.cpp` | `rtag_host`: the smallest host - loads the library with `dlopen`, runs scripts, takes frames; exit code is the runtime's |

`recomp.patch` (16 lines): `sound/audio_out.cpp` includes the file named by
`RTA_AUDIO_HOST` in place of its own devices. Everything else needed no change:
`rt/host.h` already is the boundary for ending a run, the picture sink and the pad source
are `rta::Hooks`, `texpack.cpp` has `RTA_NO_QIMAGE`.

Limits of the library as it is: **one machine per process and one run per machine** (the
translated game keeps its state in globals; `rtag_start` after `rtag_stop` is refused);
arm64 macOS only (the Windows sources exist, see stage 5); exported symbols are the
fourteen `rtag_*` functions and nothing else.

### Proof (Ran, 2026-10-13 morning; machine shared, load average 6 to 23)

`local/godot-spike/test/` (scripts written for this; results beside them):

| Check | Result |
|---|---|
| power-on, 409 blanks, two pictures (`smoke/`) | card screens drawn; 0.33 s |
| **pictures at fixed ticks** (`det/`: the tick-keyed route of `app-test/s11/mkdet.py` - power-on, title, first level, change to `valor`, a fight; 5,309 blanks; 11 pictures at 1280 x 896, plain picture) through `rtag_host` and through `local/recomp-out/bin/rta_app --offscreen --unpaced --plain` | **11 of 11 identical, pixel for pixel** (`test/piccmp.py`, decoded pixels; the PNG files differ because the encoders do) |
| **the rig's session comparison** (`test/rig.sh lib`: `rigcompare.py boot-native --script fight3.rig --replay` with `rtag_host --lib librta_game_orig.dylib` standing in for the headless build, then `boot-compare`; 7,904 fields) | **the same file as `app-test/merge/rig-final-compare.txt`, byte for byte** (`cmp`): the result the native application has - front end, first level, 5,410 ticks of `valor` - reproduced through the library |
| speed of that route, not paced, 1280 x 896 | library: 317 pictures a second, 3.97 ms of processor time a picture over all threads (decoder with OpenGL 2.65 ms); `rta_app` in the same minutes: 337 a second, 5.16 ms |

## Stage 2: in a Godot window (Ran)

`tools/godot/extension/` is a GDExtension (CMake, the layout and options of
`open-champions-godot/gdextension`; built against the pinned godot-cpp with
`build.py extension`, about three minutes the first time for the bindings). **It holds no
game code and does not link the game library**: `RtaMachine.load_library(path)` loads it
at run time (`dlopen`; `LoadLibrary` is written for Windows) and takes the fourteen
functions by name.

| Class | Does |
|---|---|
| `RtaMachine` (`rta_machine.cpp`) | `load_library`, `start(config)`, `set_pad`, `step(wait_ms)` / `poll` / `run`, the frame last taken (`get_picture()` as an `Image`, `get_shots()`, `get_host_commands()`), `peek_*` into the machine's memory, `stop` |
| `RtaAudioStream`, `RtaAudioPlayback` (`rta_audio.cpp`) | an `AudioStream` whose playback (`AudioStreamPlaybackResampled`, 48 kHz) calls `rtag_audio_pull` when Godot's mixer asks: the game's sound side runs on Godot's audio thread and clock, by itself, as the console's sound processor does (`sound-clock=real`), and Godot's buses and volume apply |
| `RtaDrawer` (`rta_drawer.cpp`) | stage 3 |

`tools/godot/project/` (scripts only): `main.gd` is the host - options, window, pacing
(one step per 1/60 s, held to the display when its rate is a multiple of 60), keyboard
and controller polled through Godot's `Input` once per picture (the native application's
key map; first joypad Godot knows), the sound player, pictures; `view.gd` shows the
picture letterboxed to the frame's shape. Script lines `app key down|up NAME` and `app
gcpad ...` become `InputEventKey` / `InputEventJoypad*` sent through
`Input.parse_input_event`, so a script exercises Godot's own input path; `app windowshot
FILE` writes the root viewport (what is in the window).

Proof (Ran; test windows 480 x 360 points titled "AGENT TEST - ...", without focus, in the
screen's corner, sound muted):

| Check | Result |
|---|---|
| power-on in a Godot window, paced (`test/g-win`) | 429 pictures in 7.25 s (59.2 a second with start-up); the window's own picture (`g-win/b-window.png`, the root viewport) shows the card screen; Godot's mixer asked for 7.26 s of sound in 2,721 requests, longest time between two requests of the sound side 10.7 ms, none late |
| **keyboard through Godot's input** (`test/g-keys`: `app-test/keyboard-play.rig`, 110 key events and nothing else) | power-on, card screens, title, menus, character creation, first level; W for 60 frames moved the character by (-102.4, +116.0) (the native application's own run of this script: (-102.5, +116.0)), D and S+A moved it on, K put it into its strike state, Return opened and closed the pause menu; `g-keys/k2-pause-window.png` is the Godot window with the pause menu over the first level |
| **the rig's session comparison through Godot** (`test/rig.sh godot`: Godot headless, the extension, `librta_game_orig.dylib`, 7,904 fields) | the same file as `app-test/merge/rig-final-compare.txt`, byte for byte |
| **pictures at fixed ticks** in a Godot window (`test/det/godot-picture`, picture mode, 1280 x 896) against `rta_app`'s | 11 of 11 identical, pixel for pixel |

Found on the way: Godot buffers input events until its next frame
(`Input.use_accumulated_input`), so a script's key was pressed and released between two
of the machine's blanks without being seen; the host flushes after each
(`Input.flush_buffered_events()`). A real key press arrives with Godot's own event
processing before `_process` and needs nothing.

Not done in stage 2: a real controller was not attached (the mapping is exercised by
`app gcpad` only as far as Godot's `Input` goes; not run yet); rumble is counted, not
sent; nobody listened to the sound (tests are muted) - that it is pulled at the right
rate is what the figures say.

## Stage 3: Godot draws (Ran)

How (`rta_drawer.h` has the full account):

- **A surface is a viewport** with a scenario, a camera and an environment of its own
  (`ENV_BG_KEEP`, clear mode "never": the GS never clears, the game does). A small
  surface that is drawn, read and drawn again within one frame - the ground shadows: up
  to eight passes a frame in `valor` - gets one viewport per pass.
- **A draw is a mesh instance.** Meshes are rebuilt every frame from the list's vertices
  through `mesh_add_surface` with raw buffers (position; colour as four bytes; texture
  coordinates s, t, q and fog as a float custom channel - no conversion through Godot's
  packed arrays, the bytes are the GS's).
- **One shader** (`gs_draw.gdshaderinc`), a line-for-line port of the OpenGL backend's
  fragment shader: texture functions (modulate with 0x80 = 1.0, decal, highlight),
  `TEXA`, the weave of two-field interface art, region wraps, fog, the alpha test, the
  scissor (as a discard), and the blend. Its variants (defines): blend equation, depth
  test, depth write, texture filter, repeat. One material per distinct state, kept
  between frames (211 alive at a time in `valor`).
- **Blend**: `(A - B) x C + D` is `source x |sc F + sk| +/- destination x |dc F + dk|`;
  everything with a plus is Godot's `blend_premul_alpha` with `ALPHA = 1 - destination
  factor` (opaque draws included), destination minus source is `blend_sub`. The only form
  this cannot do is source minus destination (counted; none in the sessions run).
- **Order.** The GS draws in the order it is told. Every material is drawn in Godot's
  transparent pass, and each instance's sorting offset (`instance_set_pivot_data`) makes
  that pass keep the list's order; depth test and depth write are the draw's own
  (`depth_draw_always` / `never`, `depth_test_disabled`).
- **"Depth test always, and write"** (every 2-D draw of this game) is not a mode Godot
  has: such a draw is submitted twice, once with the default test and once with
  `depth_test_inverted` (new in 4.5) - exactly one of the two passes at every pixel.
- **Order of surfaces.** The viewports are children of the window's viewport (rendered
  before it) and are deactivated and activated again every frame in the order the list
  needs (a surface after what it reads; the present pass, which opens a list and reads
  the 3-D surface as the frame before left it, before that surface's new draws).
- **The picture**: the viewport of the surface the display circuit reads, drawn into the
  window by `view.gd`.

Three things about Godot 4.5.2's Compatibility renderer that were found by trying and
that the drawer depends on (`test/gamma/` is the probe for the third):

1. `RenderingServer.shader_set_code` does not run the shader preprocessor; a `Shader`
   resource's `set_code` does. `shader_type` must be the first statement, before defines.
2. A position a spatial shader writes itself (`POSITION`) has y down in the viewport's
   picture, as the list's positions have; a viewport's texture reads with v down.
3. **`ALBEDO` is taken for an sRGB colour**: the renderer converts it to linear light and
   back when it writes the pixel, each way with a fast approximation, and the round trip
   lowers dark values (10 of 255 comes back as 4, 42 as 40). The shader puts in the
   colour whose round trip is the wanted one (`to_linear`: one exact inverse, three
   Newton steps). Blending then happens on the stored values, as on the GS.

**Compared with stage 2** (`test/det/godot-draw`: the tick-keyed route, Godot's capture
of the shown surface's viewport at each of the 11 ticks, 1280 x 896, against the
library's own OpenGL picture of the same tick; `test/piccmp.py`):

| Picture | Pixels that differ at all | Largest difference (of 255) | Mean |
|---|---|---|---|
| title | 61 % | 2 | 0.28 |
| first level (hub) | 69 % | 2 | 0.33 |
| `valor`, nine pictures (cutscene, play, fight) | 71 to 73 % | 2 to 3 | 0.34 to 0.36 |

No picture has a pixel that differs by more than 3. What the differences are (Read, from
the way they are spread - nearly every pixel, by one): the rounding of the colour round
trip above (float to 8 bits twice), and the present pass, which reads the 3-D surface
with the game's bilinear filter from a viewport texture. Nothing is missing or misplaced:
ground shadows, alpha-tested foliage, the HUD and its bars, text.

Differences in kind, known and counted by the drawer (`figures()`), none of which showed
in these sessions:

- **A surface read in the middle of its own draws** (the heat haze of the fire levels:
  a piece of the 3-D surface is copied out and drawn back distorted) gets the picture of
  the frame before, HUD included: one viewport renders once a frame. 7 such reads in
  5,309 lists here (level changes). Not looked at in a fire level.
- The alpha the GS writes into a surface is not kept (Godot writes the blend's own); a
  draw that reads a surface's alpha (`TEXA` modes take theirs from the register) would
  differ. Depth test "greater" is drawn as "greater or equal".
- Multisampling, mip maps, anisotropy and the art pack of the native application are not
  wired here (`--samples` sets Godot's MSAA on the 3-D surface's viewport: not compared).

**Processor time** (the same route, not paced, 1280 x 896, plain picture, load average
about 10, Apple M5 Pro; all threads of the process):

| | Pictures a second | ms of processor time a picture | Where |
|---|---|---|---|
| `rta_app --offscreen --plain` | 337 | 5.16 | decoder 1.66, OpenGL thread 2.0 |
| the library with its own renderer (`rtag_host`) | 317 | 3.97 | decoder with OpenGL 2.65 |
| Godot, picture mode (window) | 259 | 5.50 | decoder with OpenGL 3.5; read-back and texture upload every picture |
| **Godot draws** (window) | **75** | **15.6** | decoder 1.73; `submit()` 5.4 ms on Godot's main thread (236 draws and 91,000 vertices a list: a mesh, an instance and a material lookup per draw, 43 draws a list doubled for the depth rule); the rest is Godot rendering 4 viewports a frame |

So Godot's own drawing of the unchanged list costs about three times the native
application's whole picture path, and still leaves room at 60 pictures a second on this
machine (13.4 ms a picture of wall time, not paced). Where it would be made cheaper
(not done): one mesh per frame with a surface per draw instead of one mesh per draw;
not doubling 2-D draws nothing tests depth against; keeping the instances' sort keys.
