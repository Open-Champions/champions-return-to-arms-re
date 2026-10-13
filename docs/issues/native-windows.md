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
python3 tools/recomp/app/build_win.py              # the Windows programs, into local/recomp-out/win/
python3 tools/recomp/app/build_win.py --standin    # the x86-64 macOS stand-in and its arm64 controls
export RTA_DISC="/path/to/your/disc image.iso"
python3 tools/recomp/app/build_win.py --reference  # what rta_native.exe should print (arm64 Mac build)
python3 tools/recomp/app/win/standin_compare.py    # x86-64 against arm64 and both against the rig
```

| In `local/recomp-out/win/` | Is |
|---|---|
| `rta_app.exe` (27.3 MB) | the game in a window: Win32 window, OpenGL 4.1 core through WGL, keyboard, XInput, WASAPI |
| `rta_app_gcc.exe`, `rta_native_gcc.exe`, `fpcheck_gcc.exe` | the same three built by GCC (`--compiler gcc`); see "Compiler" |
| `rta_native.exe` (26.5 MB) | the machine with nothing attached: boots, runs scripts, prints its report |
| `fpcheck.exe` (0.2 MB) | the game's floating-point operations as a table of checksums (`app/win/fpcheck.cpp`) |
| `rta-windows/` | **the folder a tester gets**: the three programs, `play.bat`, `README.txt`, `boot-check.rig` (the rig's boot script with addresses in place of names), `boot-check-mac.txt` (what the Mac printed for it) |
| `gen-app/`, `gen-orig/` | this build's own translation of the game (with the fix set / unpatched), made by `recomp.py` at every build; a file is replaced only when its content changed |
| `obj-clang/` | objects, and a linker map of each program (`rta_app.map`: the addresses a crash report names) |
| `standin/` | `rta_native_x64`, `recomp_test_x64`, `fpcheck_x64` (macOS x86-64, run under Rosetta); `rta_native_arm64`, `fpcheck_arm64` (the controls, same sources); `rta_native_fix_arm64` (the game as `rta_native.exe` has it, for the reference); the comparison's logs |

The build translates into its own directory because the other builds translate into
`local/recomp-out/gen-app` whenever they run: at 14:13 that changed `funcs.h` under a
running compile.

**Time and size.** The 51 generated files (31 MB of C++) and the runtime for Windows at
`-O2`: about 210 s of processor time; 106 s of wall time at 8 jobs and nice 10 under a load
average of 200, 8.6 minutes under a load average of 500. Everything (68 files, three
programs): 2 min 18 s when the machine was calmer. `rta_app.exe` is 27.3 MB stripped
(43.2 MB with its symbol table; the arm64 macOS `rta_app` is 23.4 MB).

No DLL has to be shipped: the programs are linked with `-static` (libstdc++, libgcc,
winpthreads inside) and import only `KERNEL32`, `USER32`, `GDI32`, `OPENGL32`, `WINMM`,
`AVRT`, `ole32` and the UCRT's `api-ms-win-crt-*` sets, all part of Windows 10 and later
(read from the import table). XInput is looked up at run time.

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
object format, not in how arithmetic is compiled.

`--compiler gcc` compiles everything with `x86_64-w64-mingw32-g++` (GCC 16.2) instead and
names its programs `rta_app_gcc.exe`, `rta_native_gcc.exe`, `fpcheck_gcc.exe`. **Built**:
all 70 files compile unchanged and link without a warning (about 570 to 740 s of processor
time, three times clang's; 24.96 MB). It is a second chance for the tester if the first program does
not start - one toolchain throughout instead of clang objects against GCC's libraries -
and nothing more: its arithmetic was not compared with anything (another compiler; the
x86 branch of `fpu.h` and the flags are the same, and `fpcheck_gcc.exe` checks its
operations on the PC).

On Windows itself the script takes `g++` or `clang++` from an MSYS2 shell; that path was
never run.

## The parts that are new

| File | Does | State |
|---|---|---|
| `rt/host_win32.cpp` | `host.h` for Windows: `_beginthreadex` with a 256 MB stack reservation, `TerminateProcess` after flushing, the disc image through a Win32 handle read at a 64-bit offset, a high-resolution waitable timer; sets the timer period to 1 ms; prints exception code and image offset when the program faults | Built, not run |
| `sound/audio_out_win.cpp` | the sound device: WASAPI shared mode, event driven, 48 kHz 16-bit stereo handed over as it is (Windows converts), 20 ms buffer; the device is opened again when it goes away; waveOut (4 x 10 ms) when WASAPI does not open or `RTA_SOUND_API=waveout` | Built, not run |
| `app/win_main.cpp` | the program: options, window, pacing, keyboard, F12 pictures (PNG written here), log file, the `app ...` script commands; a disc image dropped on the program is taken as `--disc` | Built, not run |
| `app/win/headless_main.cpp` | `rta_native.exe`: `rt/main_headless.cpp` with `native.py`'s defaults (the executable copied out of the disc image, a card directory) | Built, not run |
| `app/win/standin_compare.py` | runs the x86-64 and the arm64 Mac build as `rigcompare.py boot-native --replay` does, each into its own directory, and compares | Ran |
| `app/win/wgl.h`, `wgl.cpp`, `QOpenGLContext`, `QOpenGLExtraFunctions` | the OpenGL context (4.1 core, 3.3 core as second try) and the driver's functions, behind the two Qt class names `render/backend_gl.cpp` is written against - the backend compiles for Windows unchanged | Built, not run |
| `app/pad_win.cpp` | `pad_host.h` over XInput (looked up at run time), `pad_mac.mm`'s map and dead zones | Built, not run |
| `app/win/fpcheck.cpp` | every operation of `rt/fpu.h` and the arithmetic of `rt/vu0.h` over corner values and a fixed random set, as checksums | Ran on the Mac (both architectures); the `.exe` not run |
| `app/win/rta_app.manifest`, `rta_app.rc` | UTF-8 as the process code page (paths with any characters, Windows 10 1903+), per-monitor DPI | Built |
| `app/build_win.py` | the build; `--standin`, `--reference`; the tester's folder with `boot-check.rig` | Ran |

**Changes to existing files** (three, all small; the macOS build compiles the same code as before):

1. `rt/fpu.h`, the default ("host") model, inside `#if defined(__x86_64__) || defined(_M_X64)`:
   `fp_max`, `fp_min` and `fp_rsqrt` (below, "Arithmetic").
2. `sound/audio_out.cpp`: `#elif defined(_WIN32)` / `#include "audio_out_win.cpp"` before
   the final `#else` (the Windows device uses the file's ring and counters, so it is part
   of the same translation unit).
3. `difftest.py`: the test driver's path can be given by `RECOMP_TEST_DRIVER` (to run the
   sweep with the x86-64 driver).

Not changed: `app_main.cpp`, `backend_gl.cpp`, `pipeline.h`, the runtime, the generated
code.

**What the macOS application has and the Windows program has not:**

- the control socket for test drivers (`control.h`, Unix sockets);
- the network (`net/netdrv.cpp`, `online.cpp`, `RtaOnline.cpp`, `online_mac.mm`, added to
  `app/build.py` this afternoon): POSIX sockets and a macOS dialogue. The Windows program
  is translated without `net/hle-online.txt` and plays offline;
- rumble is counted, not sent (as on the Mac).

**Films.** `app/film.cpp` (the MPEG library's entry points, added to `app/build.py` this
afternoon and still being worked on by its author) is part of the Windows program when it
and `app/hle-app.txt` exist: the translation is made with `--hle-add app/hle-app.txt` as
on the Mac, `win_main.cpp` passes `films=original` when the decoder is linked, and
`--no-films` ends a film at its first picture as before. The file needs `<ctime>` for a
timing aid, which it gets on macOS through another header; the Windows build passes
`-include ctime` instead of touching it. Not run, like the rest.

## Portability: what was looked for and what was found

| Looked for | Found |
|---|---|
| 128-bit integers | `unsigned __int128` only in the test model of `fpu.h` (`-DFPU_PS2`): shifts, compares, add, subtract - no division or multiplication, so no library call whose 128-bit calling convention could differ. The Windows programs use the default model: none at all |
| `long` (32 bits on Windows) | none in the runtime's arithmetic; one `(long)(s32)` for an `fseek` of a memory-card file (files far below 2 GB). The disc image (over 2 GB) goes through `host::big_read` |
| byte order, alignment | guest memory is read with `memcpy` as little-endian; x86-64 is little-endian. No aligned-load assumption found |
| POSIX calls | `pthread`, `usleep`, `fseeko`, `_exit` only in `host_posix.cpp`; `clock_gettime(CLOCK_THREAD_CPUTIME_ID)` in the renderer's timing aids compiles as it is (winpthreads has it). `app_main.cpp`, `control.h`, `pad_mac.mm` are not part of the Windows program |
| text and binary files | every binary file is opened with `"rb"`, `"wb"` or `"r+b"` (memory cards, dumps, streams, WAV); the files opened as text are scripts, symbol tables and logs |
| weak symbols | the 7 replaced game functions (`hle_weak.cpp`), `recomp_patches`, `rta_sound_figures`. A weak definition against a strong one, alone, and an undefined weak reference were each linked in a test program with both compilers and both link orders and read back from the disassembly: the strong one is called, a weak one alone is used, the missing one is null. In `rta_native.exe` the seven `fn_...` symbols are the runtime's (their addresses are not those of the `.weak.` defaults); in an unstripped link of `rta_app.exe`'s objects the film player's library entries and `rta_films_linked` are `film.cpp`'s in the same way |
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

`build_win.py --standin` compiles the same sources with the same flags for macOS x86-64
(`clang++ -arch x86_64`; the programs run under Rosetta) and, as the control, for arm64 at
the same moment. Both use this build's own unpatched translation (`win/gen-orig`,
byte-identical to the shared `gen/`): the game that is compared with the rig.

**Function by function** (`RECOMP_TEST_DRIVER=.../recomp_test_x64 difftest.py sweep
--seeds 2`; the test model `-DFPU_PS2`, which also exercises the 128-bit integers):

| | functions | cases | pass | identical to a common stop | FAIL | cases different | not comparable |
|---|---|---|---|---|---|---|---|
| x86-64 under Rosetta (795 s) | 7,732 | 92,784 | 7,391 | 40 | 0 | 0 | 301 |
| arm64 (this morning's `sweep-stub.txt`) | 7,732 | 92,784 | 7,391 | 40 | 0 | 0 | 301 |

Every count of the two reports is the same (72,825 cases identical to the return, 501 to
a common stop, 19,458 stopped in the interpreter).

**A whole session** (`standin_compare.py`: script `fight3.rig` - power-on, front end,
character creation, the first level, the level change to `valor`, the fight - with the
rig's controller bytes replayed tick for tick and the rig's session seeds, exactly as
`rigcompare.py boot-native --replay`; each build into its own directory):

| | arm64 | x86-64 under Rosetta |
|---|---|---|
| frames / fields / units | 7,797 / 7,904 / 257,776,500 | 7,797 / 7,904 / 257,776,500 |
| wall time (load average about 450) | 83 s | 115 s |

- The two tick logs (27 watch columns - positions, hit points, the player record, the
  object pool, the task list, both seeds - at every one of 7,798 logged frames) are
  **byte-identical** (1,980,683 bytes).
- Main memory, all 32 MB, written at frame 7,304 (after the fight; the two `--dump-tick`
  conditions were both already true there, so it is one moment written twice): **byte-identical**.
- `rigcompare.py boot-compare` against the rig's log gives the same text for both, and it
  is the result `native-app.md` has: front end 1,383 ticks and `valor` 5,410 ticks identical
  in every simulation column; the first level 99 ticks identical but for the player record
  at tick 7; the object pool different in the same 27 ticks (3,886 to 3,912); the cosmetic
  seed different where it was.

So in this session nothing the game computed depended on the processor - which also means
the one known hardware-dependent case (`vu0.h` with an infinity or NaN operand) either did
not occur or left no trace in memory.

**The Windows objects against the stand-in's (Read).** One generated file, the one with
the most floating-point operations (`c_006.cpp`, 201 functions), compiled for
`x86_64-w64-mingw32` and compared with the stand-in's object: 2,631 floating-point
instructions in each; in all 201 functions the same instructions in the same numbers, in
199 in the same order (in two the compiler laid the blocks out in another order). The
other 45 files were not compared this way.

**What rta_native.exe should print.** `build_win.py --reference` runs the tester's check
script (`boot-check.rig`: the rig's `boot-to-hub.rig`, 2,413 fields from power-on into the
first level) in `rta_native_fix_arm64` - the sources and the translation of
`rta_native.exe`, as an arm64 Mac program. Two runs print the same 691 lines except the
wall time. The lines to look for:

```
frames=2309 wall=...: ... fields=2413 units=113069982
VU0: 466083 microprogram calls, 26111361 instructions
```

and the script's last `show` puts the character at 131.570755, -96.2327423, -48. These
figures belong to the sources of 2026-10-12 15:39; a later build gets its own
(`--reference` again).

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

**What to copy:** the folder `local/recomp-out/win/rta-windows` (54 MB; it contains
translated game code, so it is not in the repository and goes to the tester directly),
and the tester's own disc image of SLUS-20973 v2.00. Needs Windows 10 1903 or later, 64-bit,
and a graphics driver with OpenGL 4.1. Nothing is installed; everything written goes to
`rta-data` beside the programs. `README.txt` in the folder is this plan in the tester's words.

| Step | The tester does | Passes when | Tells us |
|---|---|---|---|
| 1 | `fpcheck.exe > fpcheck.txt` in a Command Prompt | the line "must agree everywhere" ends in `2e77df4dc13ec9c5` and the rounding mode reads "toward zero" | the processor, the C library's `fesetround` and the compiled operations give the Mac's results |
| 2 | `rta_native.exe boot --disc "C:\...\image.iso" --script boot-check.rig > boot-check.txt 2>&1` | the two lines above appear; `fc boot-check.txt boot-check-mac.txt` shows only the `wall=` line (and paths) | host file, threads, stacks, disc reading, memory card, the whole translated game from power-on into the first level, bit for bit as on the Mac |
| 3 | drags the image onto `play.bat`; plays a few minutes | a window with the memory-card screens, logo, title, a level; sound; keyboard and controller | window, WGL, shaders, pacing, WASAPI, XInput |

**What to send back:** `fpcheck.txt`, `boot-check.txt`, `rta-data\rta_app-log.txt` (the
log of the last run of `rta_app.exe`: Windows version, OpenGL version and renderer, missing
OpenGL functions, the pacing chosen, the sound device's line, and at the end the figures -
pictures per second, how long pictures stood, sound requests late), pictures made with F12
of anything that looks wrong, and the answers to: did a window open; which screens
appeared; is there sound, does it crackle; do keyboard and controller work; is the speed
right and even.

**If it fails:** a fault prints `host: the program failed: exception 0x... at offset 0x...`
as the last line of the log; the offset is looked up in `local/recomp-out/win/obj-clang/rta_app.map`
of the same build (keep that directory until the report is in). "The window or its OpenGL
4.1 context could not be made" names the step of `wgl.cpp` that failed. No sound:
`set RTA_SOUND_API=waveout` before starting, or `--no-sound`, and the `sound:` lines of
the log. `rta_app_gcc.exe`, when it is in the folder, is the same program built by GCC -
to be tried only if `rta_app.exe` does not start at all (its arithmetic was not compared
with anything; `fpcheck_gcc.exe` is its step 1).

## Resume here

**Second pass, started 2026-10-12 19:50 (in progress - this block is rewritten as it goes).**
Brief: (1) the network in `rta_app.exe` (Winsock behind one socket layer shared with the
Mac build, a Win32 name dialogue, server address from an option or `server.txt` beside the
program); (2) the merged graphics of `native-graphics.md` in the Windows program (settings,
widescreen, multisampling, mip maps, the art pack read without Qt); proofs on the Mac;
tester's folder and README. Plan and state:

| Step | Files | State |
|---|---|---|
| socket layer | `net/sock.h` (new), `net/netdrv.cpp` (its POSIX calls replaced by the layer) | not started |
| name dialogue, title note, set warning for Windows | `net/online_win.cpp` (new) | not started |
| PNG reader without Qt | `render/png_read.h` (new), `render/texpack.cpp` (`read_png`, `open`) | not started |
| settings, aspect, online options in the Windows program | `app/win_main.cpp` | not started |
| build: new files, network, sign-in patch, stand-ins with the network | `app/build_win.py` | not started |
| proofs: x86-64 stand-in lobby game, Mac `rta_app` lobby game, PNG reader against QImage over `local/hd-pack` | | not started |
| tester's folder, README, this file, `native-app.md` 8, `native-recomp.md` step 6 | | not started |

Rules of this pass: the local lobby only (never 167.99.183.124), builds into
`local/recomp-out/win/` only, no git, nothing derived from the game outside `local/`.

**State saved 2026-10-12 15:45 (first pass).** Nothing is half-done in the sources; the tree compiles
(last full `build_win.py` 15:37: 70 files, three programs linked; `--standin` and
`--reference` after it; `--compiler gcc` after those). Every file of this work is listed under "The parts that are new"
and "Changes to existing files".

What exists now, by the clock:

| Made | What |
|---|---|
| 15:37 | `rta_app.exe` (27.3 MB, with `film.cpp`), `rta_native.exe`, `fpcheck.exe`, clang; the folder `local/recomp-out/win/rta-windows` with them, `play.bat`, `README.txt`, `boot-check.rig` |
| 15:39 | `standin/rta_native_fix_arm64` and `rta-windows/boot-check-mac.txt` from the same translation: `frames=2309 ... fields=2413 units=113069982`, `VU0: 466083 microprogram calls, 26111361 instructions` (unchanged by the film entries) |
| 15:43 | `rta_app_gcc.exe` (24.96 MB, with `film.cpp`), `rta_native_gcc.exe`, `fpcheck_gcc.exe`: GCC, the same sources and translation as the 15:37 programs (rebuilt after them: 57 of 70 files, 568 s of processor time); copied into `rta-windows` |
| 14:38 - 15:00 | the stand-in comparison (`standin/rig-x64`, `rig-arm64`, `compare.log`) and the x86-64 sweep (`standin/sweep-stub-x64.txt`): made with the runtime sources of that time; `runtime.cpp` and the renderer were changed by others afterwards (15:03, 15:13). Repeat with `build_win.py --standin`, `standin_compare.py`, and the sweep line of the section above |

Everything of the brief is done except running on Windows, which needs a person with a
PC: the test plan above. Open ends, in the order they matter:

1. **The tester's report.** Steps 1 and 2 decide whether the arithmetic and the runtime
   hold on real hardware; step 3 is the first time anybody sees the window or hears the
   sound. Expect the first faults in `wgl.cpp` (context), the shaders on a non-Apple
   driver, or pacing.
2. **`vu0.h` with an infinity or NaN operand** is the one place where x86 and ARM64 can
   still differ (sign and payload of the NaN). Not seen in the compared session. Closing
   it means a check after each arithmetic result in the interpreter's x86 branch.
3. **The film decoder on x86-64** (`app/mpeg2.h`, added by its author while this was
   written): compiled for Windows, never compared between the two processors. It makes
   pictures, not simulation state.
4. **The network on Windows**: Winsock behind `net/netdrv.cpp` and a dialogue in place of
   `online_mac.mm`.
5. **Controllers that are not XInput** (a PlayStation controller without Steam or
   DS4Windows): Windows.Gaming.Input or raw HID.
6. **Building on Windows itself** (MSYS2): `build_win.py` has the branch, nobody ran it.
7. `native-app.md` section 8 and `native-recomp.md` "Step 6 - Windows" still describe
   Windows as not written; they are their author's and were left alone.

The builds of other agents change `tools/recomp` while this is written: a later
`build_win.py` picks their changes up (it follows `app/build.py` for the translation and
the film decoder), and `build_win.py --standin` + `--reference` + `standin_compare.py`
repeat every figure above.
