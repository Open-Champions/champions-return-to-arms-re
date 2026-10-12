# The native application for Windows

Started 2026-10-12. The native application (`docs/issues/native-app.md`: the game's own
code translated to C++, with our runtime, renderer, sound library and input) ran on macOS
only. This is its build for Windows x86-64, made on the Mac with a cross-compiler.

**Nothing here has been run on Windows.** There is no Windows machine, and nothing on this
Mac executes Windows programs (no Wine; `qemu-system-x86_64` and Docker are installed but
there is no Windows to start in them, and nothing may be downloaded). Every statement
below says **Built** (compiles and links), **Ran on the Mac** (the same sources as an
x86-64 macOS program under Rosetta, or as arm64), **Read** (seen in the linked program or
the source), or **Not run**. The test plan at the end is for a person with a Windows PC.

Nothing derived from the game is in the repository. The generated game code
(`local/recomp-out/gen-app`), the objects and the programs are under `local/recomp-out/`;
a Windows build is made by the builder from the builder's own disc.

STATE: see "Resume here" at the end (kept current while the work goes on).

## What is built

```
python3 tools/recomp/app/build_win.py            # everything, into local/recomp-out/win/
python3 tools/recomp/app/build_win.py --standin  # the x86-64 macOS stand-in and its arm64 control
```

| In `local/recomp-out/win/` | Is |
|---|---|
| `rta_app.exe` | the game in a window: Win32 window, OpenGL 4.1 core through WGL, keyboard, XInput, WASAPI |
| `rta_native.exe` | the machine with nothing attached (`rt/main_headless.cpp`): boots, runs scripts, prints its report |
| `fpcheck.exe` | the game's floating-point operations as a table of checksums (`app/win/fpcheck.cpp`) |
| `play.bat`, `README.txt` | for the tester (copies of `tools/recomp/app/win/`) |
| `standin/` | `rta_native_x64`, `recomp_test_x64`, `fpcheck_x64` (macOS x86-64, run under Rosetta) and `rta_native_arm64`, `fpcheck_arm64` (the controls, same sources, same moment) |

No DLL has to be shipped: the programs are linked with `-static` (libstdc++, libgcc,
winpthreads inside) and import only what Windows 10 and later has.

**Toolchain.** Installed with Homebrew, and nothing else: `mingw-w64` 14.0.0_3 (GCC
16.2.0, binutils, the MinGW-w64 headers and libraries for the UCRT). Homebrew upgraded
two of its dependencies on the way: `isl` 0.27 to 0.28, `libmpc` 1.3.1 to 1.4.1.
Qt for Windows cannot be had by cross-compiling without downloading it, so the Windows
program does not use Qt.

**Compiler.** The Mac's own `clang++` (Apple clang 21) with
`--target=x86_64-w64-mingw32 --sysroot=<brew>/mingw-w64/toolchain-x86_64 -femulated-tls`,
linked by `x86_64-w64-mingw32-g++ -static -s`. Reason: it is the same compiler, with the
same x86-64 code generator and the same flags, as the stand-in that is run under Rosetta
(below), so what was run and what is shipped differ in the calling convention and the
object format, not in how arithmetic is compiled. `--compiler gcc` compiles with
`x86_64-w64-mingw32-g++` instead (see "Resume here" for whether that was built). On
Windows itself the script takes `g++` or `clang++` from an MSYS2 shell; that path was
never run.

## The parts that are new

| File | Does | State |
|---|---|---|
| `rt/host_win32.cpp` | `host.h` for Windows: `_beginthreadex` with a 256 MB stack reservation, `TerminateProcess` after flushing, the disc image through a Win32 handle read at a 64-bit offset, a high-resolution waitable timer; sets the timer period to 1 ms; prints exception code and image offset when the program faults | Built, not run |
| `sound/audio_out_win.cpp` | the sound device: WASAPI shared mode, event driven, 48 kHz 16-bit stereo handed over as it is (Windows converts), 20 ms buffer; the device is opened again when it goes away; waveOut (4 x 10 ms) when WASAPI does not open or `RTA_SOUND_API=waveout` | Built, not run |
| `app/win_main.cpp` | the program: options, window, pacing, keyboard, F12 pictures (PNG written here), log file, the `app ...` script commands | Built, not run |
| `app/win/wgl.h`, `wgl.cpp`, `QOpenGLContext`, `QOpenGLExtraFunctions` | the OpenGL context (4.1 core, 3.3 core as second try) and the driver's functions, behind the two Qt class names `render/backend_gl.cpp` is written against - the backend compiles for Windows unchanged | Built, not run |
| `app/pad_win.cpp` | `pad_host.h` over XInput (looked up at run time), `pad_mac.mm`'s map and dead zones | Built, not run |
| `app/win/fpcheck.cpp` | every operation of `rt/fpu.h` and the arithmetic of `rt/vu0.h` over corner values and a fixed random set, as checksums | Ran on the Mac (both architectures); the `.exe` not run |
| `app/win/rta_app.manifest`, `rta_app.rc` | UTF-8 as the process code page (paths with any characters, Windows 10 1903+), per-monitor DPI | Built |
| `app/build_win.py` | the build | Ran |

**Changes to existing files** (three, all small; the macOS build compiles the same code as before):

1. `rt/fpu.h`, the default ("host") model, inside `#if defined(__x86_64__) || defined(_M_X64)`:
   `fp_max`, `fp_min` and `fp_rsqrt` (below, "Arithmetic").
2. `sound/audio_out.cpp`: `#elif defined(_WIN32)` / `#include "audio_out_win.cpp"` before
   the final `#else` (the Windows device uses the file's ring and counters, so it is part
   of the same translation unit).
3. `difftest.py`: the test driver's path can be given by `RECOMP_TEST_DRIVER` (to run the
   sweep with the x86-64 driver).

Not changed: `app_main.cpp`, `backend_gl.cpp`, `pipeline.h`, the runtime, the generated
code. The control socket of `app_main.cpp` (`control.h`, Unix sockets) is not in the
Windows program.

## Portability: what was looked for and what was found

| Looked for | Found |
|---|---|
| 128-bit integers | `unsigned __int128` only in the test model of `fpu.h` (`-DFPU_PS2`): shifts, compares, add, subtract - no division or multiplication, so no library call whose 128-bit calling convention could differ. The Windows programs use the default model: none at all |
| `long` (32 bits on Windows) | none in the runtime's arithmetic; one `(long)(s32)` for an `fseek` of a memory-card file (files far below 2 GB). The disc image (over 2 GB) goes through `host::big_read` |
| byte order, alignment | guest memory is read with `memcpy` as little-endian; x86-64 is little-endian. No aligned-load assumption found |
| POSIX calls | `pthread`, `usleep`, `fseeko`, `_exit` only in `host_posix.cpp`; `clock_gettime(CLOCK_THREAD_CPUTIME_ID)` in the renderer's timing aids compiles as it is (winpthreads has it). `app_main.cpp`, `control.h`, `pad_mac.mm` are not part of the Windows program |
| text and binary files | every binary file is opened with `"rb"`, `"wb"` or `"r+b"` (memory cards, dumps, streams, WAV); the files opened as text are scripts, symbol tables and logs |
| weak symbols | the 7 replaced game functions (`hle_weak.cpp`), `recomp_patches`, `rta_sound_figures`. A weak definition against a strong one, alone, and an undefined weak reference were each linked in a test program with both compilers and both link orders and read back from the disassembly: the strong one is called, a weak one alone is used, the missing one is null. In `rta_native.exe` the seven `fn_...` symbols are the runtime's (their addresses are not those of the `.weak.` defaults) |
| thread-local storage | clang's default for this target is native TLS, GCC's libraries use emulated TLS; `-femulated-tls` makes clang match |
| printf formats | `%llu`, `%zu` are the UCRT's own; no `%lu` of a 64-bit value in the runtime |
| case of include names | none wrong (the Mac's file system would not have shown it; the cross-compiler's headers are on the same file system, so this is **not proven** for a case-sensitive one) |
| paths | built with `\`; arguments and file names in the process code page, which the manifest makes UTF-8 |

Link: clang and GCC pad the name strings of C++ type information differently; `ld` reports
each one it merges with libstdc++'s copy ("duplicate section ... has different size") and
keeps one. The build prints their number instead of the lines.

## Arithmetic: how the game computes on x86-64

The translated game computes with `rt/fpu.h` (the main processor's FPU, on raw 32-bit
patterns) and `rt/vu0.h` (vector unit 0, one microprogram). Both use the host's
single-precision arithmetic in round-toward-zero, without fused multiply-add
(`-ffp-contract=off -frounding-math`).

**State on x86-64 (Read in `rta_native.exe` and its objects).**

- *SSE, not x87.* The objects of the game and the runtime contain no x87 instruction at
  all. Scalar single-precision SSE2: `mulss` 12,965, `addss` 8,460, `subss` 4,582,
  `divss` 495, `sqrtss` 300, `cvtsi2ss` 2,078, `cvttss2si` 1,442, compares; no
  `vfmadd` (no FMA: the build is for baseline x86-64, no `-march`), no `rsqrtss` /
  `rcpss` approximations. (The whole program has some x87 in the C library's `long
  double` formatting; none of it computes for the game.)
- *No library arithmetic.* The game's 49 objects have no undefined symbol other than the
  runtime's own (`g_ram`, `g_site`, the `rt_...` and `fn_...` functions): no `fmaxf`,
  `sqrtf` or other libm call whose result could depend on the C library.
- *Rounding.* Every guest thread calls `fesetround(FE_TOWARDZERO)` (`runtime.cpp`,
  `thread_main`). In the program this is MinGW-w64's `fesetround` -> `__mingw_controlfp(mode,
  _MCW_RC)` -> `__mingw_setfp` (x87 control word) and `__mingw_setfp_sse` (`ldmxcsr`): the
  MXCSR rounding field is set. Windows keeps MXCSR per thread.
- *Denormals.* MXCSR starts as 0x1F80 on every Windows thread: flush-to-zero and
  denormals-are-zero off, as on macOS (both architectures). Nothing in the tree sets
  them. Denormal results are IEEE's on every host.
- *Width.* `float` operations are single precision in SSE; there is no x87 extended
  intermediate to round twice.

**What differed between ARM64 and x86-64, and the fix (Ran on the Mac).** `fpcheck` runs
every operation over 48 corner patterns and 800 fixed random ones, all pairs (about
700,000 cases per two-operand operation), built from the same file for arm64 and for
x86-64 and run under Rosetta. Before any change three operations of `fpu.h` differed:

| Operation | Cases | Cause |
|---|---|---|
| `fp_max`, `fp_min` | 2 each: the pairs of +0 and -0 | `__builtin_fmaxf` is ARM64's `FMAXNM` (max(-0, +0) = +0) but on x86 a `MAXSS` sequence that returns an operand by its position (-0) |
| `fp_rsqrt` | every negative operand | the square root of a negative number is a NaN, and which one is the processor's choice: ARM64 makes 0x7fc00000, x86 0xffc00000; the next operation clamps them to +FLT_MAX and -FLT_MAX |

The x86-64 branch of `fpu.h` now spells both out as the ARM64 results (the model is "the
arithmetic of the reference emulator on an ARM64 host", so ARM64's answer is the
definition). After it every `fpu.h` operation agrees on **every** 32-bit pattern,
infinities and NaNs included (the operations clamp what they read), and the arm64
checksums are the ones from before the change. Add, subtract, multiply, divide, square
root, both conversions and the compares never differed.

**Left as it is: `vu0.h` with an infinity or NaN operand.** With ordinary numbers the
vector unit's operations agree (`fpcheck`, class "numbers"). With an infinity or NaN as an
operand, add / subtract / multiply give a NaN whose sign and payload differ (about 100 of
719,104 pairs each): x86 makes 0xffc00000 where ARM64 makes 0x7fc00000, and with two NaN
operands each processor has its own rule for which one is passed on. Rounding toward zero
never makes an infinity from numbers, so this needs an infinity or NaN bit pattern in the
animation data the pose program is fed. Whether the compared sessions ever differ: see the
comparison below. `MAX` / `MINI` and both conversions of `vu0.h` are written as C
comparisons and agree on every pattern.

`fpcheck`'s last line - one checksum over everything that must agree - is
`2e77df4dc13ec9c5` on arm64 and on x86-64 under Rosetta. **`fpcheck.exe` on a real PC must
print the same** (test plan, step 1); that is the check of real x86 hardware, which this
Mac cannot make.

**What "x86-64 under Rosetta" proves and what it does not.** It runs the x86-64 machine
code that clang generates from these sources - the instruction selection, the operand
orders, the x86-only source branches. Rosetta translates that code to ARM and is built to
give x86 results (the cases above - the sign of a made NaN, `MAXSS` on zeros - came out the
x86 way, which is how they were found). It is not an Intel or AMD processor; it cannot
show a processor's own behaviour that Rosetta does not model. `fpcheck.exe` on the PC
closes that gap for the operations; the game's own code paths are covered by the session
comparison only on the Mac.

## The x86-64 stand-in: differential test and session comparison (Ran on the Mac)

RESULTS PENDING - see "Resume here".

## Not run, and what could be wrong there

- `rta_app.exe`, `rta_native.exe`, `fpcheck.exe` themselves.
- The Win32 window, the message loop, full screen, DPI scaling.
- WGL: the pixel format, the core context, the function lookup; whether `backend_gl.cpp`'s
  shaders compile on a Windows driver (they are `#version 410 core` shaders that so far
  only Apple's OpenGL has compiled - a stricter or laxer GLSL compiler may object).
- Pacing against a Windows display (swap interval through `wglSwapIntervalEXT`, the
  clock otherwise).
- XInput; WASAPI and waveOut - nobody has heard a sample.
- Guest threads on 256 MB reserved stacks made by `_beginthreadex`; C++ threads, mutexes
  and condition variables of winpthreads under the game's scheduler.
- The UTF-8 manifest on Windows before 10 1903 (there: ASCII paths only).
- Building on Windows itself (MSYS2).

## Test plan for a person with a Windows PC

PENDING - see `tools/recomp/app/win/README.txt` for the tester's short version.

## Resume here

(2026-10-12 14:30) Done: toolchain; `rta_native.exe` + `fpcheck.exe` link (clang, 106 s for
57 files at 8 jobs under a load average of 200); all Windows sources written and each
compiles; `fpu.h` fix verified by `fpcheck` on both architectures; stand-in built
(`rta_native_x64`, `recomp_test_x64`).
Running / next: (1) full `build_win.py` (links `rta_app.exe`); (2) `difftest.py sweep
--seeds 2` with `RECOMP_TEST_DRIVER=local/recomp-out/win/standin/recomp_test_x64`, report
in `win/standin/sweep-stub-x64.txt`; (3) `build_win.py --standin` again for the arm64
control, then the rig comparison with both (`rigcompare.py boot-native --replay`, its
output directory pointed at `win/standin/rig-x64` and `rig-arm64`) and a byte comparison of
the two tick logs and memory dumps; (4) write the two pending sections; (5) optionally
`--compiler gcc`.
