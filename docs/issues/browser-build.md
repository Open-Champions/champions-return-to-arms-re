# Browser build (Play! compiled to WebAssembly) — working notes

Status: IN PROGRESS (started 2026-10-11). Kept current while the work goes on; the
summary at the top is rewritten when figures change.

Question: does Champions: Return to Arms (SLUS-20973 v2.00) run at full speed in Chrome
on an Apple M5 Pro, at the title screen and standing in the first level, with the same
core changes as the native build (`tools/play-net/play-net.patch`) and the same patches?

## Summary

(no measurement yet)

## Where things are

| What | Where |
|---|---|
| sources of the web front end, build script, local test server | `tools/play-web/` |
| my copy of Play! (commit 83700b2c + `play-net.patch` + `play-web.patch`) | `local/play-web-src` (not in the repository) |
| pristine copies of every Play! file `play-web.patch` touches (as they are after `play-net.patch`) | `local/play-web-orig` |
| build directory | `local/play-web-build` |
| the page as served | `local/play-web-site` |

## Installed

`brew install emscripten` (6.0.12). Homebrew brought its dependencies with it: abseil,
simdutf, hdrhistogram_c, libffi, libnghttp2, libuv, llhttp, merve, simdjson, readline,
highway, python@3.14, openjdk, yuicompressor, and it upgraded node 26.5.0 to 26.11.1.
Nothing else was downloaded (no npm packages: the page is plain HTML and JavaScript, not
Play!'s React application under `js/play_browser`, which needs `npm install`).

## Log

- The tree: `local/play-playable` copied without `.git` to `local/play-web-src`, the 18
  files under `local/play-orig/Source` put back, `tools/play-net/play-net.patch` applied
  (no rejects).
- `emcmake cmake … -DBUILD_TESTS=OFF -DBUILD_PLAY=ON -DBUILD_PSFPLAYER=OFF -DUSE_QT=OFF`,
  `cmake --build . --target Play`: all 429 objects compile with the patch as it is (the
  Qt/macOS sources of `tools/play-net/src` are not part of this configuration). Only the
  link failed: Play!'s `-sUSE_ES6_IMPORT_META=0` is no longer accepted by Emscripten 6.

## How Play!'s browser port works (read in the source)

- The machine thread and the video thread are pthreads (web workers on a shared
  WebAssembly memory): the page must be served with `Cross-Origin-Opener-Policy:
  same-origin` and `Cross-Origin-Embedder-Policy: require-corp`.
- Translated code: every basic block of MIPS code becomes a WebAssembly module of its own
  (`CMemoryFunction`: `new WebAssembly.Module` + `Instance`, put into the function table).
  Blocks are not linked to each other in this configuration (`BasicBlock.cpp`,
  `__EMSCRIPTEN__`): every block returns to the dispatcher.
- No write protection of memory pages: translated code is not thrown away when the game
  overwrites it (`CEeExecutor::SetMemoryProtected` does nothing). Patches therefore have
  to be in place before the code is first run, or the range has to be cleared by hand.
- No control of the floating-point rounding mode (`fesetround(FE_TOWARDZERO)` has no
  effect in WebAssembly): results can differ in the last bit from the native build. This
  matters for online play between a browser and a native player (docs/issues/float-divergence.md).
- Upstream draws through a WebGL context made on the page's main thread and used from
  the video thread: Emscripten then sends every GL call to the main thread.
- Upstream reads the disc by asking the main thread for each piece and polling for it.
