# The translated game inside Godot (spike)

Started 2026-10-13. Question: can the statically recompiled game (`native-recomp.md`,
`native-app.md`) run inside Godot as its game logic, with Godot doing window, input, sound
and - step by step - the drawing? Everything here says **Ran** (with what was seen) or
**Read**. Kept current as the work goes; a successor needs only this file.

Nothing derived from the game is in the repository. `tools/godot/` holds glue, build
scripts, the Godot project's scripts and shaders. The translated code, the libraries, the
staged project, exported applications, pictures and logs are under `local/godot-spike/`.

## STATE (kept current; newest first)

- **Stage 1, the game as a library: done (Ran).** `local/godot-spike/lib/librta_game.dylib`
  (fix set) and `librta_game_orig.dylib` (the game as on the disc), C interface
  `tools/godot/lib/rtag.h`. Proven with the test host `bin/rtag_host`: the tick-keyed
  picture route gives 11 of 11 pictures identical to `rta_app`'s pixel for pixel; the
  rig's session comparison gives the same result file as `rta_app_orig`'s, byte for byte.
- Stage 2 (in a Godot window): in work.
- Stages 3 to 5: not started.

## From nothing

```
export RTA_DISC="/path/to/your/disc image.iso"
python3 tools/recomp/app/build.py && python3 tools/recomp/app/build.py --original   # the translated game (objects)
python3 tools/godot/build.py all            # snapshot, library, extension, staged project
python3 tools/godot/build.py lib --original # the unpatched game as a library (for the rig comparison)
```

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
