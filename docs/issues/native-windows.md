# The native application for Windows

Started 2026-10-12. The native application (`docs/issues/native-app.md`: the game's own
code translated to C++, with our runtime, renderer, sound library and input) ran on macOS
only. This is its build for Windows x86-64, made on the Mac with a cross-compiler.

**First run on Windows: 2026-10-20, in a Windows 11 virtual machine on this Mac** (Windows 11
Pro for ARM, the x86-64 programs under Windows' own x86-64 emulation, no graphics chip):
section "First run on Windows" below. Until then nothing here had run on Windows, and the
sections written before it say so. Every statement says **Ran on Windows (VM)**, **Built**
(compiles and links), **Ran on the Mac** (the same sources as an x86-64 macOS program under
Rosetta, or as arm64), **Read** (seen in the linked program or the source), or **Not run**.
The test plan at the end is still for a person with a Windows PC: a real Intel or AMD
processor and a real OpenGL driver have not run it.

Nothing derived from the game is in the repository. The generated game code
(`local/recomp-out/gen-app`), the objects and the programs are under `local/recomp-out/`;
a Windows build is made by the builder from the builder's own disc.

STATE (2026-10-21): **aiming by looking** (`docs/issues/native-first-person-aim.md`) is in `win_main.cpp` where
`app_main.cpp` has it (`fpaim::blank` after the controls, `fpaim::drawn` in `fpview::on_drawn`, `--aim look|off`, the
`combat.aim` setting, `app aim ...`, the figures line), and `build_win.py` compiles `app/fpaim.cpp`. **Ran on Windows
(VM)**: a Mac `rta_app_next` host (`--aim look --view first`, a Ranger) and the VM's `rta_app.exe` joiner (`--offscreen
--plain --view first`, Mesa llvmpipe, a Wizard; it took the host's choice: "the host plays with aiming by looking on: so
does this copy now") in one room through a rendezvous service on this Mac: **2,254 ticks in step** hub > drunare, no
shared column differs (the aim block's columns included); 7 arrows at 7 pitches (-54.7 to +65.0 degrees) from the Mac,
4 Shock of Frost at 4 pitches (-17.4 to +16.3) from the Windows copy, which sent its own 34 aim messages (`local/aim/r8/win/w1`).
The Godot version for Windows now has its game library (`tools/godot/build_lib_win.py`, `docs/issues/native-godot.md`
round 8): its export ran in the VM.

Earlier STATE (2026-10-20, 17:05): the tester's folder and the installer were run in a Windows 11 ARM
virtual machine: floating-point table, boot check, a headless play run and the PNG check give
the Mac's figures; the window program draws (with a software OpenGL); a Windows copy and the
Mac's `rta_app` played in one room through a rendezvous service on this Mac, in step through a
level change, also with `--combat souls`; `install-windows.bat` built a working program from
nothing (one Windows-only fix). Details: "First run on Windows"; open ends: "Resume here".

## What is built

```
python3 tools/recomp/app/build_win.py              # the Windows programs, into local/recomp-out/win/
python3 tools/recomp/app/build_win.py --standin    # the x86-64 macOS stand-in and its arm64 controls
export RTA_DISC="/path/to/your/disc image.iso"
python3 tools/recomp/app/build_win.py --reference  # what rta_native.exe should print (arm64 Mac build)
python3 tools/recomp/app/win/standin_compare.py    # x86-64 against arm64 and both against the rig
python3 tools/recomp/app/build_win.py --mac        # after --standin: the macOS rta_app from the same translation, into win/mac/
python3 tools/recomp/app/build_win.py --pngcheck   # win/standin/pngcheck: the PNG reader against QImage
```

| In `local/recomp-out/win/` | Is |
|---|---|
| `rta_app.exe` (27.7 MB) | the game in a window: Win32 window, OpenGL 4.1 core through WGL, keyboard, XInput, WASAPI; since the second pass (below) the network and the picture options |
| `rta_app_gcc.exe`, `rta_native_gcc.exe`, `fpcheck_gcc.exe` | the same three built by GCC (`--compiler gcc`); see "Compiler" |
| `rta_native.exe` (26.5 MB) | the machine with nothing attached: boots, runs scripts, prints its report |
| `fpcheck.exe` (0.2 MB) | the game's floating-point operations as a table of checksums (`app/win/fpcheck.cpp`) |
| `rta-windows/` | **the folder a tester gets**: the three programs, `play.bat`, `online.bat`, `server.txt` (where the lobby server's address goes), `README.txt` (with this build's figures filled in), `boot-check.rig` (the rig's boot script with addresses in place of names), `boot-check-mac.txt` (what the Mac printed for it) |
| `gen-app/`, `gen-orig/` | this build's own translation of the game (with the fix set / unpatched), made by `recomp.py` at every build; a file is replaced only when its content changed |
| `obj-clang/` | objects, and a linker map of each program (`rta_app.map`: the addresses a crash report names) |
| `standin/` | `rta_native_x64`, `recomp_test_x64`, `fpcheck_x64` (macOS x86-64, run under Rosetta); `rta_native_arm64`, `fpcheck_arm64` (the controls, same sources); `rta_native_fix_arm64` (the game as `rta_native.exe` has it, for the reference); `rta_native_online_x64`, `rta_native_online_arm64` (headless with the network: the lobby games below); `pngcheck`; `online/` (the lobby games' logs); the comparisons' logs |
| `mac/` | `rta_app` (the macOS window program, arm64 with Qt, from this build's translation and the sources as they are: what `app/build.py` makes, without touching the shared `bin/`), `rta_app_pngread` (the same with the art pack read by `render/png_read.h`) |

The build translates into its own directory because the other builds translate into
`local/recomp-out/gen-app` whenever they run: at 14:13 that changed `funcs.h` under a
running compile.

**Time and size.** The 51 generated files (31 MB of C++) and the runtime for Windows at
`-O2`: about 210 s of processor time; 106 s of wall time at 8 jobs and nice 10 under a load
average of 200, 8.6 minutes under a load average of 500. Everything (68 files, three
programs): 2 min 18 s when the machine was calmer. `rta_app.exe` is 27.3 MB stripped
(43.2 MB with its symbol table; the arm64 macOS `rta_app` is 23.4 MB). Second pass: 76
files (the network's four, `texpack.cpp`, `gfx_rt.cpp`), 71 of them in 203 s at load
200; `rta_app.exe` 27.7 MB.

No DLL has to be shipped: the programs are linked with `-static` (libstdc++, libgcc,
winpthreads inside) and import only `KERNEL32`, `USER32`, `GDI32`, `OPENGL32`, `WINMM`,
`AVRT`, `ole32`, since the second pass `WS2_32` (24 functions), `IPHLPAPI`
(`GetAdaptersAddresses`) and `ADVAPI32` (five functions for the saved login's access
list), and the UCRT's `api-ms-win-crt-*` sets, all part of Windows 10 and later
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
| *second pass:* `net/sock.h` | the host's sockets as `netdrv.cpp` uses them, one header with two bodies: BSD sockets and Winsock 2 ("The network", below) | BSD body: Ran on the Mac (three lobby games); Winsock body: Built and Read, not run |
| `net/online_win.cpp`, `online_win.h` | the name question (a modeless Win32 dialogue made in memory), the note in the window's title, the set warning (a box); the two file calls of `posix_win.h` | Built and Read, not run |
| `net/posix_win.h` | `fchmod`, `fsync`, `rename` for `tools/play-net/src/RtaOnline.cpp`, given to that one file with `-include` (the file itself is unchanged) | Built and Read, not run |
| `render/png_read.h` | a PNG file as RGBA8 without a library (own inflate), for the art pack | Ran on the Mac: identical to QImage over 222,094 files; the same source is what the `.exe` contains |
| `app/win/pngcheck.cpp`, `pngtest.py` | the comparison of `png_read.h` with QImage over folders; made PNG files of every kind and damaged ones | Ran |
| `app/win/online.bat`, `server.txt` | the tester's way online: the address in a text file, a menu of three | not run (cmd.exe) |

**Changes to existing files** (first pass: three, all small; the macOS build compiles the same code as before):

1. `rt/fpu.h`, the default ("host") model, inside `#if defined(__x86_64__) || defined(_M_X64)`:
   `fp_max`, `fp_min` and `fp_rsqrt` (below, "Arithmetic").
2. `sound/audio_out.cpp`: `#elif defined(_WIN32)` / `#include "audio_out_win.cpp"` before
   the final `#else` (the Windows device uses the file's ring and counters, so it is part
   of the same translation unit).
3. `difftest.py`: the test driver's path can be given by `RECOMP_TEST_DRIVER` (to run the
   sweep with the x86-64 driver).

Second pass (the macOS build was made again from the changed files and played a lobby
game: "The network"):

4. `net/netdrv.cpp`: its socket calls (`socket`, `bind`, `connect`, `poll`, `fcntl`,
   `send`, `recv`, `sendto`, `recvfrom`, `getsockopt`, `getifaddrs`, `getaddrinfo`,
   `SIGPIPE`, `_NSGetExecutablePath`) are calls of `net/sock.h`; host sockets are
   `sock::Handle` instead of `int`; `setvbuf(..., _IOLBF, 0)` for the tick log is left out
   on Windows (its C library ends the program for a size of 0). Nothing else: the rules
   below the library entries are the same lines as before.
5. `render/texpack.cpp`: under `RTA_NO_QIMAGE` `read_png` calls `pngread::read_file`
   (it returned false), `open` lists the folder (it returned 0), and on Windows the reader
   threads run below normal priority. The Qt branch is untouched.
6. `net/lobbypair.py`: the window program can be another build (`RTA_NATIVE_APP`, as
   `play-native.sh` has it). One line.
7. `app/win_main.cpp`, `app/build_win.py`, `app/win/README.txt`: this work's own files.

Not changed: `app_main.cpp`, `backend_gl.cpp`, `pipeline.h`, the runtime, the generated
code, `net/online.cpp`, `tools/play-net/src/RtaOnline.cpp`, `app/build.py`,
`net/build_online.py` (the layer is a header: no build list changes).

**What the macOS application has and the Windows program has not:**

- the control socket for test drivers (`control.h`, Unix sockets) and with it
  `app latency`;
- rumble is counted, not sent (as on the Mac).

The network and the picture options were missing after the first pass and are in the
program now: the next two sections.

**Films.** `app/film.cpp` (the MPEG library's entry points, added to `app/build.py` this
afternoon and still being worked on by its author) is part of the Windows program when it
and `app/hle-app.txt` exist: the translation is made with `--hle-add app/hle-app.txt` as
on the Mac, `win_main.cpp` passes `films=original` when the decoder is linked, and
`--no-films` ends a film at its first picture as before. The file needs `<ctime>` for a
timing aid, which it gets on macOS through another header; the Windows build passes
`-include ctime` instead of touching it. Not run, like the rest.

## The network (second pass, 2026-10-12 evening)

`rta_app.exe` has the online path of the macOS `rta_app` (`docs/issues/native-online.md`):
the same driver source, the same one-step online, the same translation (`--hle-add
net/hle-online.txt`, and the local sign-in patch through `--extra-pnach` when the file is
in `local/`; nothing of that file is printed, copied or in the repository).
`build_win.py --no-net` leaves all of it out. `rta_native.exe` does not link the driver
and is offline as before (it gets the translated originals of the listed entries).

**One source for both systems: `net/sock.h`.** A header with two bodies and one small
interface in host byte order (`udp`, `tcp`, `bind_port`, `local_port`, `connect`,
`connect_check`, `send`, `recv`, `send_to`, `recv_from`, `readable`, `shut`,
`outside_address`, `own_addresses`, `resolve`, `program_dir`, `start`). `netdrv.cpp` has
no socket header and no `#ifdef` for the host any more (one, for `setvbuf`). The BSD body
is the calls `netdrv.cpp` made, moved; the Winsock body differs from it in more than names
in these places:

| | BSD body (Ran) | Winsock body (Built, Read) |
|---|---|---|
| start | `SIGPIPE` ignored | `WSAStartup(2.2)`, once |
| non-blocking | `fcntl(O_NONBLOCK)`, macOS `SO_NOSIGPIPE` | `ioctlsocket(FIONBIO)` |
| a connection under way | `connect` says `EINPROGRESS`; asked with `poll(POLLOUT)` and `SO_ERROR` | `connect` says `WSAEWOULDBLOCK`; asked with `select`: writable = up, in the "except" set = refused (`SO_ERROR` has the reason). `WSAPoll` is not used: before Windows 10 2004 it did not report a refused connection |
| nothing to read / cannot send now | `EAGAIN`, `EWOULDBLOCK`, `EINTR` | `WSAEWOULDBLOCK`, `WSAEINTR` (send also `WSAENOBUFS`) |
| a datagram sent to a port nobody listens on | nothing | the ICMP answer comes back as `WSAECONNRESET` of a later `recvfrom` on that socket. The driver sends to players who may not be there yet (the hole punching), so the report is switched off per socket (`SIO_UDP_CONNRESET`), and one that still arrives is skipped, not taken for "no datagram" |
| a datagram longer than the buffer | its first part | its first part and `WSAEMSGSIZE`: taken as the first part |
| "is something to read" | `poll(POLLIN)` | `select` with a zero time-out |
| this computer's addresses | `getifaddrs` | `GetAdaptersAddresses(AF_INET)` |
| error text in the log | `strerror` | `FormatMessage` and the number |
| close, both directions off | `close`, `shutdown(SHUT_RDWR)` | `closesocket`, `shutdown(SD_BOTH)` |

Read in the linked program: the import table has the 24 Winsock functions the body calls
and no others; in the link map `fn_003654a8` (`sceInetCreate`), `fn_00365780`
(`sceInetSend`), `fn_00323dcc` (`main`) lie inside `n_netdrv.o` and the `.weak. ... .default`
copies of the translation are separate symbols; `recomp_patch_set_words()` is
`g_patches.o`'s (90 words), not the driver's weak fallback.

**The player-name question, the title note, the set warning: `net/online_win.cpp`.**
The driver calls from the game's thread; the calls post a message to the game's window,
and the window's thread makes a small modeless dialogue from a template built in memory
(no resource file): the explanation, one text field limited to 15 characters, "Play
online" and "Not now". A name that does not fit the rule leaves the dialogue open with
the reason above the field. It is modeless for the reason the macOS sheet is one: the
game goes on running and being drawn behind it, and the lobby server drops a client it
does not hear from. The note of the one-step driver and the server go into the window's
title; the warning that another player's patch set (or arithmetic) differs is a box with
the text and OK. A test window, and a window that is never shown, are left alone as on
the Mac. `win_main.cpp` hands messages from `WM_APP` on to `onlinewin::window_message`
and offers every message of its loop to `onlinewin::dialog_message` first.

**The saved login on Windows: `net/posix_win.h`.** `RtaOnline.cpp` writes the login with
`open` / `fchmod(0600)` / `write` / `fsync` / `close` / `rename`. MinGW-w64 has no `fchmod`
and no `fsync`, and its `rename` does not replace an existing file - which would have
kept the first login and the first "character used last" for ever. The Windows build
compiles that file with `-include net/posix_win.h`: `fsync` is `_commit`; `rename` is
`MoveFileEx(MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)`; `fchmod(fd, 0600)` gives
the file, still empty, an access list of its own with one entry - full access for the user
the program runs as - and stops it inheriting its folder's (`ReOpenFile` with `WRITE_DAC`,
`SetSecurityInfo` with a protected DACL). If a step of that fails the file keeps its
inherited access and is saved all the same. `std::random_device` (the password, the game
code, the made-up address) is hardware random numbers or `rand_s` in this libstdc++
(Read: `rdseed`, `rdrand` and `__imp_rand_s` in the program), not a fixed sequence.

**Options** (`rta_app.exe --help`; `app/win_main.cpp`): `--server ADDRESS`, or the first
line of `server.txt` beside the program that is not a remark (a line `public = ADDRESS` is
`--server-public`), or neither: a server on this computer; `--online`, `--host [CODE]`,
`--join CODE`, `--choose-character`; `--player N` (data in `rta-data-player<N>`). They
become the driver's `--opt net-server=`, `net-server-public=`, `net-data=`, `net-card=`,
`online=`; what follows `--` on the command line comes later and wins. `online.bat` in
the tester's folder asks "list of games, host or join" and for the code.

**What was run on the Mac** (the lobby server on this computer, throw-away names made by
`net/lobbypair.py`, every copy with `net-local-only=1`; the only addresses in the logs
are this computer's own, 127.0.0.1 and the copies' made-up 198.19 ones). All four programs are
from this build's own translation and the sources with the socket layer:

| Run (`local/recomp-out/win/standin/online/`) | Load | Result |
|---|---|---|
| `x64pair`: `rta_native_online_x64` hosts, `rta_native_online_x64` joins (both x86-64 under Rosetta), `--play 1800 --level drunare --play2 1800` | 146 | 4,813 ticks compared, **no shared column differs**; the game's checksum exchange equal (6de5a610 on both); patch set 3f5b1e14 (90 words) told both ways; both ended by their script |
| `mixed`: `rta_native_online_x64` hosts, `rta_native_online_arm64` joins, `--play 3000 --level drunare --play2 3000` | 212 | 6,758 ticks compared, nothing differs; checksums equal (0b647cd6): an x86-64 copy and an ARM64 copy in one lockstep game |
| `macpair2`: the macOS window program `win/mac/rta_app` (arm64, Qt, test window) hosts, `rta_native_online_arm64` joins, `--play 1800` | 230 | 1,654 ticks compared, nothing differs; checksums equal (4eca3948) |

(`macpair`, the first try of the third run, ended at the launch with "unknown name
g_levelName": the window program looks for `names.tsv` three directories above itself,
which is right for `bin/` and wrong for `win/mac/`. The second try names the symbol files
with `--native-arg=--sym`. Nothing in the program.)

The shared `local/recomp-out/bin/rta_app` was **not** rebuilt by this work (other work
runs tests against it); it takes the layer at its owner's next `app/build.py`, which
compiles the same `netdrv.cpp` with the same flags as `build_win.py --mac`.

**What the stand-in proves here and what it does not.** The driver, the one-step online
and the translated game as x86-64 code hold a lobby game, against themselves and against
ARM64. The socket layer that ran is the BSD body. Of the Winsock body nothing ran: it is
about 150 lines that were compiled by clang and GCC and read against the table above.

## The picture options (second pass)

The merged graphics work (`docs/issues/native-graphics.md`) is in the Windows program:

- `build_win.py` translates with the current `hle.txt` (its 16 new addresses come with
  it) and compiles `app/gfx_rt.cpp` (the hooks on the game's view functions and the marks
  for the 2-D layer) and `render/texpack.cpp`. `render/backend_gl.cpp` with its
  multisampled surfaces, mip-mapped parts and samplers compiles against `app/win/wgl.h`
  unchanged: every OpenGL function it now calls was in the list already.
- `app/win_main.cpp` has what `app_main.cpp` got in the merge: `<data>\settings.txt`
  (written with its defaults at the first start somebody plays), `--settings`,
  `--no-settings`, `--aspect`, `--resolution`, `--antialiasing`, `--anisotropy`,
  `--mipmaps`, `--art-pack`, `--art-memory`, `--frame-cap`, `--plain`, `--no-layout`,
  `--art-whole`, `--art-wait`; the view's shape from the window's client area, followed
  when the window is resized or goes full screen; the picture sized for the shape each
  frame list was built for; every other picture at `frame_cap = 30`; the report lines
  `rta_app: picture:`; the script lines `app window W H`, `app fullscreen`, `app art
  off|on` (posted to the window's thread). It also takes `dead_targets` over with a
  frame, which the first pass's file did not know.

**The art pack without Qt: `render/png_read.h`.** A PNG reader written for this (its own
table-driven inflate, CRC-32, Adler-32, the five row filters, Adam7, every colour type
and bit depth, tRNS); no code of zlib, libpng or anything else, nothing downloaded. A
build without Qt (`-DRTA_NO_QIMAGE`) reads the pack with it. What is not 8-bit RGBA is
converted as Qt 6 converts it on the way to `Format_RGBA8888` - found by experiment, not
from Qt's source: 16 bits to 8 as (v x 255 + 32767) / 65535 (all 65,536 values checked),
a palette index beyond the palette shown as the palette's first entry (white in a 1-bit
picture), the transparent grey of a 2-, 4- or 8-bit grey picture as transparent black.

Compared with QImage, used exactly as `texpack.cpp` uses it (`app/win/pngcheck.cpp`;
**Ran**):

| Files | Result |
|---|---|
| all of `local/hd-pack` as it stood at 20:11 to 20:42: `replace` (the 4x pack) and `dump` (the game's own textures), 222,094 PNG files, 79.09 GB, 123,101 million pixels - every one 8-bit RGBA, not interlaced | **222,094 identical in every byte, 0 different**, 0 refused |
| 913 files made by `app/win/pngtest.py` (nothing of the game): every colour type and bit depth, interlaced and not, with tRNS, palettes of several sizes, every filter, streams of stored / fixed / dynamic blocks cut into IDAT chunks in several ways | 894 identical; 19 damaged ones refused by both (cut short, wrong CRC of a critical chunk, wrong Adler-32, wrong filter byte, rows missing, unknown critical chunk ...); 0 different |
| 48 more of those: 16-bit RGB with a transparent colour | differ, and stay so: Qt 6 reads such a file's rows of three samples as rows of four (checked: its output is that misreading, pixel for pixel). `png_read.h` follows the PNG specification. No pack file is of this kind |

**The reader alone, for the tester: `app/win/pnghash.cpp`.** It prints one figure (FNV-1a
over name, size and every pixel of every file) for a folder, with no Qt. `pnghash.exe` is
in the tester's folder beside `pngtest/`, the 961 made files; `--reference` runs the
arm64 Mac build over that folder and writes the figure into `README.txt`. On the Mac the
x86-64 build (under Rosetta) and the arm64 build print the same figure for it (942 read,
19 refused, b4ed3d8917871960) and for 3,000 files drawn from the 4x pack
(`standin/packsample.log`). This is the one part of the picture work that step 4 of the
test plan checks on Windows without a pack.

Reading took QImage 3,899 s and `png_read.h` 7,056 s summed over six threads at load 150
to 230: the reader is about 1.8 times slower than libpng. It runs on the pack's three
reader threads beside the game, not in it; a faster inflate is possible and was not
needed for a proof.

**The whole path on the Mac (Ran).** `win/mac/rta_app` (QImage) and
`win/mac/rta_app_pngread` (the same objects but `texpack.cpp` with `RTA_NO_QIMAGE`), each
from power-on by the tester's script into the first level, 16:9 at 1280 x 720, no window,
the 4x pack, every frame waiting for its pictures (`--art-wait`): the same report in both -
303 textures named, 289 found in the pack, 333 pictures read (229 as parts, 46 read again
for a larger part), 244 held, 575.0 MB; 2,629 frames built wide, 436,627 2-D primitives
moved - and the picture written at vertical blank 2,712 is **the same file, byte for
byte** (1,732,487 bytes; `win/mac/arttest/`).

**Not run:** all of this on Windows - whether a Windows OpenGL driver makes the
multisampled surface and resolves it, compiles the shaders with `centroid` and
`textureGrad`, has `GL_TEXTURE_MAX_ANISOTROPY`; the window's shape reaching the game
through `win_main.cpp` (the same arithmetic as `app_main.cpp`, typed again for Win32
client sizes); `settings.txt` through the Windows C library; the pack folder listed with
MinGW's `dirent`.

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

**Repeated at 21:13** with the stand-ins of the second pass (the current shared tree: the
16 new `hle.txt` addresses, the runtime as others left it at 16:11): the same figures to
the digit - 7,797 / 7,904 / 257,776,500 on both, tick logs identical (7,798 rows,
1,980,683 bytes), memory identical at both dump ticks, the same `boot-compare` text for
both (`standin/compare-pass2.log`). The function-by-function sweep was not repeated.

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
figures were made with the sources of 15:39 and again at 20:57 with the second pass's
translation (network entries, sign-in patch, 16 view and draw hooks, which a headless
program leaves to the originals): the same two lines. A later build gets its own
(`--reference` again; it also fills them, and the patch set a copy announces, into the
tester's `README.txt`).

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
- Second pass: every line of the Winsock body of `net/sock.h` (start-up, the connection
  under way, `WSAECONNRESET` on datagram sockets, the address list); Windows Firewall's
  question at the first start and what it does to the peer datagrams when declined; the
  name dialogue (its template, focus, Enter and Escape through `IsDialogMessage`), the
  title note, the warning box; the saved login's access list and the replace-on-rename;
  `server.txt` and `online.bat` (cmd.exe); a lobby game between a Windows copy and any
  other copy; the picture options on a Windows OpenGL driver ("The picture options").

## Test plan for a person with a Windows PC

**What to copy:** the folder `local/recomp-out/win/rta-windows` (85 MB with the GCC programs; it contains
translated game code, so it is not in the repository and goes to the tester directly),
and the tester's own disc image of SLUS-20973 v2.00. For step 5 the tester is told the
address of a lobby server and writes it into `server.txt` (the folder's copy has none; a
rebuild keeps a `server.txt` that is already there). Needs Windows 10 1903 or later, 64-bit,
and a graphics driver with OpenGL 4.1. Nothing is installed; everything written goes to
`rta-data` beside the programs. `README.txt` in the folder is this plan in the tester's words.

| Step | The tester does | Passes when | Tells us |
|---|---|---|---|
| 1 | `fpcheck.exe > fpcheck.txt` in a Command Prompt | the line "must agree everywhere" ends in `2e77df4dc13ec9c5` and the rounding mode reads "toward zero" | the processor, the C library's `fesetround` and the compiled operations give the Mac's results |
| 2 | `rta_native.exe boot --disc "C:\...\image.iso" --script boot-check.rig > boot-check.txt 2>&1` | the two lines above appear; `fc boot-check.txt boot-check-mac.txt` shows only the `wall=` line (and paths) | host file, threads, stacks, disc reading, memory card, the whole translated game from power-on into the first level, bit for bit as on the Mac |
| 3 | drags the image onto `play.bat`; plays a few minutes | a window with the memory-card screens, logo, title, a level; sound; keyboard and controller | window, WGL, shaders, pacing, WASAPI, XInput |
| 4 | makes the window wide, presses F; F12 on a normal and a wide picture; once with `--plain` if something looks wrong; `pnghash.exe pngtest > pnghash.txt`; `--art-pack FOLDER` if they have a pack | the 3-D view wider and not stretched, HUD at its edge, menus centred; smooth edges; `rta-data\settings.txt` written; `pnghash.txt` ends in `figure b4ed3d8917871960` | the multisampled surface, mip maps and samplers on a Windows driver; the view's shape from Win32; the settings file; the PNG reader on Windows |
| 5 | puts the server's address into `server.txt`; drags the image onto `online.bat`: 1 (list of games), then 2 (host) with a second person who types 3 and the code | the name dialogue appears once and takes a name; the game reaches the list by itself; the title shows server and code; the two play together; the log has `patch set 3f5b1e14 (90 words)` and no warning | Winsock: TCP to the lobby, the UDP path between players, the firewall; the dialogue; the saved login (a second start asks nothing) |

**What to send back:** `fpcheck.txt`, `boot-check.txt`, `pnghash.txt`, `rta-data\rta_app-log.txt` (the
log of the last run of `rta_app.exe`: Windows version, OpenGL version and renderer, missing
OpenGL functions, the pacing chosen, the sound device's line, the `picture:` lines, the
`[net]` lines - server, patch set, every TCP connection and the first datagram each way,
never a name or a password - and at the end the figures: pictures per second, how long
pictures stood, sound requests late, `net:` connections and datagrams), pictures made with
F12 of anything that looks wrong - never `rta-data\online-login`, which holds the saved
login - and the answers to: did a window open; which screens
appeared; is there sound, does it crackle; do keyboard and controller work; is the speed
right and even; does the picture follow the window's shape; did the name dialogue work,
did the game get to the list of games, did host and join by code work, did the two games
stay together.

**If it fails:** a fault prints `host: the program failed: exception 0x... at offset 0x...`
as the last line of the log; the offset is looked up in `local/recomp-out/win/obj-clang/rta_app.map`
of the same build (keep that directory until the report is in). "The window or its OpenGL
4.1 context could not be made" names the step of `wgl.cpp` that failed. No sound:
`set RTA_SOUND_API=waveout` before starting, or `--no-sound`, and the `sound:` lines of
the log. Online: the `[net]` lines say what was tried - `CANNOT find the lobby server`, `TCP
-> a.b.c.d:40800 could not connect (...)` with Winsock's reason, `UDP ... NOT SENT`; a
game that reaches the room but never starts points at the datagrams between the players
(firewall, router). `rta_app_gcc.exe`, when it is in the folder, is the same program built by GCC -
to be tried only if `rta_app.exe` does not start at all (its arithmetic was not compared
with anything; `fpcheck_gcc.exe` is its step 1).

## First run on Windows (2026-10-20, a virtual machine on this Mac)

**The machine.** UTM 5.0.8 on this Mac (Apple M5 Pro): Windows 11 Pro for ARM, version
10.0.26300.9457, 8 virtual processors (4 for the first checks), 8 GB, 64 GB disk, the shared
network of UTM (the virtual machine 192.168.64.2, the Mac 192.168.64.1). The programs are
x86-64: Windows runs them under its own x86-64 emulation, so - as with Rosetta - the
processor that computed is not an Intel or AMD one. There is no graphics chip: Windows has
its basic display adapter and OpenGL 1.1 (GDI). Everything of the virtual machine is under
`local/winvm/` (not in the repository); the disc image was copied into it and nowhere else.

**How it was set up, unattended** (the Mac's screen was locked: no click, no key): Microsoft's
Windows 11 ARM64 ISO rebuilt with `xorriso` (Homebrew) as a new ISO with the EFI boot image that
does not wait for a key (`efi/microsoft/boot/efisys_noprompt.bin`), `install.wim` split into two
`.swm` parts with `wimlib` (Homebrew; the ISO has no UDF, and a file over 4 GB cannot be in it),
an `autounattend.xml` (Windows 11 Pro chosen with Microsoft's generic installation key - the
"I don't have a product key" path, no activation; the licence accepted, as the owner had done
in the first try; disk 0 wiped; one local administrator `tester` without a password and with
automatic log-on; `BypassNRO`; no account or privacy pages), and, in the same ISO, the UTM guest
tools' drivers and installer and the Win32-OpenSSH MSI (its official GitHub release, ARM64,
10.0.0.0p2). `SetupComplete.cmd` installs the network driver (`pnputil`), OpenSSH with this
Mac's public key as the administrators' key, a firewall rule for port 22, and switches sleep
off; the first log-on installs the guest tools. The disk comes first in the boot order (UTM
gives the drives boot indexes in their order), so the CD without the key prompt starts only
while the disk is empty. A QEMU monitor on 127.0.0.1 gave screen dumps and keys
(`screendump`, `sendkey`) to see what Setup did. From the first boot to `ssh` working: 13
minutes, to the desktop 17. Two things that did not work at first: an `<InstallFrom><Path>` in the answer file
(Windows 11 24H2's new Setup: "Unable to find wim specified in unattend", 0x80070490 -
0x4002C; without the element it finds `install.swm` by itself), and the guest tools' own CD,
which carries an `Autounattend.xml` of its own (not attached; its files are in the new ISO).

**Ran on Windows (VM)**, the tester's folder as it is (`local/recomp-out/win/rta-windows`, the
cross build of 10:06) and the llvm-mingw build made on the Mac
(`local/recomp-out/win-llvm-mingw/rta-windows`), the README's checks over `ssh`:

| Check | Cross build (`rta-windows`) | llvm-mingw build | Against |
|---|---|---|---|
| 1. `fpcheck.exe` | "must agree everywhere" **2e77df4dc13ec9c5**; all 56 lines the same as the Mac's x86-64 stand-in under Rosetta except `sizeof(long) 4` (Windows' LLP64); against the arm64 table only the five `vu_* any` lines differ (the NaN sign and payload of "Arithmetic") | the same file, byte for byte | `standin/fpcheck_x64`, `fpcheck_arm64.txt` |
| 2. boot check (`rta_native.exe boot ... --script boot-check.rig`) | `frames=2309 ... fields=2413 units=113069252`, `VU0: 466083 microprogram calls, 26111361 instructions`; `fc` against `boot-check-mac.txt`: only the `wall=` line (9.7 s, 4 processors) | the same (15.1 s) | `boot-check-mac.txt` |
| headless play run: the boot check, then 3,600 vertical blanks of drawn input in the hub (`lobbypair.play_lines`, six seeds), the player's level, position, state, hit points, gold, experience shown every 600 | the same values as the arm64 Mac build; four of the seven lines print a position's ninth digit differently (-34.1419106 against -34.1419105 and three more: the same bit patterns, `c2089151` etc. - the GCC libraries' `printf` rounds the last digit differently); `units=256907238` | identical text apart from `wall=` | `standin/rta_native_fix_arm64`, same script |
| 4. `pnghash.exe pngtest` | 961 files, 942 read, 19 refused, **figure b4ed3d8917871960** | the same | `png-hash.txt` |

**The window program** (`rta_app.exe`). With Windows' own OpenGL it stops at once with its
message ("the OpenGL driver cannot make a core profile context (it says: 1.1.0) ...") - the
error path works and says what to do. With Mesa 26.2.4's `opengl32.dll` and
`libgallium_wgl.dll` (the mesa-dist-win release on GitHub, x64) put beside the program:

- the D3D12 driver over WARP (Mesa's default there): OpenGL 4.6, then the process ends after
  about 10 s with exit code 0x80070057 before its first picture, with and without `--plain`
  and `--no-films`, in the `ssh` session and on the desktop;
- llvmpipe (`GALLIUM_DRIVER=llvmpipe`): exit code 0xC000001D (illegal instruction): Mesa's JIT
  makes AVX code the emulation does not take; with `GALLIUM_OVERRIDE_CPU_CAPS=sse4.1` (128-bit
  code) it **works**: the memory-card screen and the hub's loading picture look as on the Mac
  (pictures looked at; kept under `local/`), the scripts walked the title and the character
  screens, and the boot script reaches the hub in the window; 36 pictures a second in a 320 x 240 window, 42 without a window
  (8 processors), about 5 at 960 x 720 with 4 samples (4 processors, the installer compiling beside it);
- softpipe: OpenGL 3.3 only; the shaders (`#version 410`) are refused with a clear log line and
  the program goes on to its end without a picture.

Neither crash printed the line `host: the program failed: exception ...` that
`rt/host_win32.cpp`'s exception filter writes; probably a DLL loaded later (LLVM inside the
OpenGL driver) installs a filter of its own over it (**not proven**). A tester whose driver
crashes would get no line either.

**A room of our own: a Windows copy and the Mac in one game (Ran).** `tools/rendezvous/rendezvous.py`
on this Mac, plain, bound to 127.0.0.1 and 192.168.64.1 (port 41977); the Mac's
`local/recomp-out/bin/rta_app` (arm64, no window) hosting with `--play-host`, the tester
folder's `rta_app.exe` (llvmpipe as above, `--plain --resolution 320x224`) joining with
`--play-join CODE --service 192.168.64.1:41977`; each driven by `n2party.py`'s own scripts (a
chat line, a new character on the game's screens, drawn play) with `tick-log` and the same
`tick-do` line; `tools/rig/compare.py ticks` over the two tick logs. Both copies said
`patch set 9ac29719 (189 words)`; the route was direct (punched; 31 to 53 ms), nothing relayed;
the launch handshake took 211 blanks on both, as between two Macs.

| Run | Ticks compared | What |
|---|---|---|
| `room2` | 1,338 | hub; no shared column differs (the level change was not reached before the host's script gave up) |
| `room5` | **1,359** | hub, the level changed to drunare at tick 1,000 in one lockstep tick on both, 360 ticks there; **no shared column differs on any tick**; the Windows copy ended by itself, exit code 0 |
| `room3`, `--combat souls` on both | **522** | "souls-style combat: on for this game" on both; hub; no shared column differs |

The games went at the Windows copy's pace: 1 to 2 lockstep ticks a second (the Mac copy
waited). Not the network: the Windows program's main thread was inside Mesa's LLVM in three of
four stack samples (`lldb` of the x86-64 llvm-mingw release attached to the process): llvmpipe
compiles shader variants on the drawing thread, under emulation, and a two-player game kept
it compiling. On a PC with an OpenGL driver of its graphics chip this does not apply; it is
the reason the runs are short.

**The installer** (`tools/install/install-windows.bat`) in a fresh folder: the repository at
HEAD (4c9a48f, `git archive`) unpacked into `C:\fresh\champions-re`, then
`install-windows.bat -Disc ... -Yes -Desktop C:\fresh\desk` on the desktop session. It
installed Python 3.12.10 for ARM64 with winget (from python.org, hash checked by winget; no
question was left open), downloaded llvm-mingw 20261006 `ucrt-aarch64` from its GitHub release
(177 MB, SHA-256 9A835D51...), copied `SLUS_209.73` out of the image (4028A55F), translated and
built (`x86_64-w64-mingw32-clang++` of the ARM64 toolchain: 91 of 91 files in 375 s at 4
jobs), made the desktop shortcut; 24 min 49 s, exit code 0. Its programs give the same
`fpcheck` file as the Mac's llvm-mingw build, the same boot check and headless play run as the
Mac (`units=113069252` and `256907238`) and the same PNG figure; they say `patched: 189 words`
where today's working-tree builds say 191 (HEAD's fix set).

One fault, Windows only, **fixed**: `render/vu1_translate.py` refused its output path
("what is made from the game's programs must be written under local/") because it looked for
`/local/` in a path with backslashes; the installer then went on with VU1 interpreted. The test
now turns `os.sep` into `/` first (one line; on macOS and Linux nothing changes). The installer
run again with the fix: "wrote ...\gen-vu\vu1_fast.cpp: 1 programs", one file compiled,
`rta_app.exe` 26,971,136 bytes instead of 26,845,184, 2.5 minutes.

On the way: started with its input from a pipe (`echo.| install-windows.bat`), Windows
PowerShell 5.1 waited before its first line and never went on; with the input from `nul` it
ran. Someone who double-clicks the file is not affected.

**Not run in the virtual machine:** sound (the machine has no sound device: `--no-sound`
throughout), a controller, the name dialogue and the lobby server (`online.bat`), the
`--pacing` comparison on a real display, the full-screen and wide-window checks by eye, the GCC
programs, a real OpenGL driver, a real x86-64 processor, TLS to the public service (never
pointed at).

## Resume here

**2026-10-20 17:05, the first run on Windows** (a virtual machine; "First run on Windows" above
has everything). Ran there: checks 1, 2 and 4 of the README with both builds, a headless play
run, the window program with Mesa's llvmpipe, three games in one room with the Mac's `rta_app`
(1,359 ticks in step through a level change; 522 with `--combat souls`), the installer from a
fresh folder. Changed in the sources: `render/vu1_translate.py`, one line (the path test with
backslashes). Open, in the order they matter:

1. A real PC: an Intel or AMD processor (the figures above came through Windows' emulation on
   ARM) and a real OpenGL driver; sound, controller, the pacing by eye, full screen.
2. The exception filter of `rt/host_win32.cpp` printed nothing when the program died inside
   the OpenGL driver: probably replaced by the driver's DLL. A vectored handler, or setting the
   filter again after the context is made, would keep the line.
3. Mesa's D3D12 driver over WARP ends the program with 0x80070057 before the first picture;
   not looked into (a driver of a virtual machine, but the same Mesa layer is what Windows on
   ARM laptops use for OpenGL through Microsoft's compatibility pack).
4. A long game with a Windows copy: these were short because llvmpipe under emulation made the
   lockstep slow, not because of the network.
5. `online.bat`, the name dialogue and the lobby server on Windows; TLS on Windows.

The virtual machine stays as it is (`ssh tester@192.168.64.2` with this Mac's key; the scripts
used are in `local/winvm/tools/`), with the folders, the installer's tree, Mesa and the disc
image inside it.

**2026-10-20, the combat mode, a room of our own, the installer** (nothing of it run on
Windows; a Windows 11 ARM virtual machine is being set up for that).

- `win_main.cpp` now has what `app_main.cpp` and `linux_main.cpp` have: the souls-style
  combat mode (`soulscombat::blank` after the controls' `translate`, `overlay` before
  `backend->execute`, the camera in `fpview::on_drawn`, `--combat souls|off`, `combat.*`
  settings, `app souls ...`, the figures in the final report; `docs/issues/native-souls-combat.md`)
  and the room options of net2 (`--play-host`, `--play-join CODE`, `--service HOST:PORT` or a
  `service=` line in `server.txt`, `--name` also as the room name), which only the macOS and
  Linux programs had. `build_win.py` compiles `app/soulscombat.cpp` (also for `--mac`). The
  first-person world work (`fpworld.cpp`, the shelf in `rt/runtime.cpp`) and the view and
  controls settings were shared files already. **Built**: `rta-windows/rta_app.exe` 28.46 MB,
  `rta_native.exe` 26.46 MB, `fpcheck.exe`, `pnghash.exe` (Homebrew mingw-w64 sysroot, the Mac's
  clang; 91 files in 37 s). The import table as before (no new DLL).
- **The installer `tools/install/install-windows.bat`** (it runs `install-windows.ps1`): Python 3
  (found as `py -3`, `python`; if missing, `winget install Python.Python.3.12` after asking),
  llvm-mingw from its official GitHub release (the `ucrt-x86_64` or, on Windows on ARM, the
  `ucrt-aarch64` archive of the latest release or of `-LlvmMingwTag`; size checked, SHA-256
  printed) unpacked into `local\toolchain`, a file window for the disc image, then
  `tools/install/fromdisc.py`: `SLUS_209.73` copied out of the ISO and checked (4028A55F), the
  main VU1 program translated, `build_win.py`, a desktop shortcut to `rta-windows\rta_app.exe
  --disc "<image>"`. On Windows `build_win.py` now takes `x86_64-w64-mingw32-clang++` first (so
  an ARM64 Windows also builds the x86-64 program, which runs under Windows' emulation) and
  `x86_64-w64-mingw32-windres`. **Not run** (no Windows here): the scripts themselves, PowerShell
  5.1's handling of them, winget, the download, the build on Windows.
- **What was run instead (on the Mac)**: the same build with llvm-mingw 20261006 (its macOS
  release, `x86_64-w64-mingw32-clang++` with libc++ and lld, what the installer fetches for
  Windows) through `build_win.py`'s own steps into `local/recomp-out/win-llvm-mingw/`. It found
  two faults, both fixed: `net2/session_mock.cpp` used `atof` without `<cstdlib>` (libc++ does not
  bring it in through another header), and `clock_gettime` (winpthreads) was not linked
  (`-lpthread` added to `WIN_LIBS`; GCC's libstdc++ had pulled it in). Then **Built**: all 91
  files, `rta_app.exe` 27.58 MB, `rta_native.exe` 25.61 MB, the same DLL imports as the
  Homebrew build (plus `api-ms-win-crt-multibyte`). The Homebrew build was linked again after the
  change: unchanged otherwise.
- For the virtual machine: `local/recomp-out/win/rta-windows/` (the cross build, as before) and
  `local/recomp-out/win-llvm-mingw/rta-windows/` (what the installer makes) are both there;
  the test plan above applies to either, plus: `rta_app.exe --combat souls`, and a room
  (`rta_app.exe --play-host --service HOST:PORT` on one machine, `--play-join CODE` on the
  other) against a Mac or Linux copy.


**2026-10-13 14:53, by the owner of `rt/`, `render/`, `app/`, `net/`** (`native-app.md`
12.5 and 12.10 have the detail): the folder `rta-windows` was rebuilt twice this afternoon
(13:35, and 14:46 with the camera views) - `rta_app.exe` 27.99 MB (clang),
`rta_app_gcc.exe` 25.67 MB, `rta_native.exe`, `fpcheck.exe`, `pnghash.exe`,
`fpcheck_gcc.exe`, README. New in `win_main.cpp`, all of it **compiled and linked, none of
it run**: the macOS program's pacing (the game let go by a clock ahead of each picture's
moment; a late picture drawn and not shown; the grid moved onto the display's refreshes
by the swaps' return times or, where swaps do not wait, by `DwmGetCompositionTimingInfo`;
`--pacing queued` is the old way), a high-resolution timer for the game's thread, the
above-normal priority class and no power throttling; the camera views (`--view`, V) and
their controls (raw mouse input, the pointer clipped). In shared files: the thread fix,
the new fix set, the link fix for `CNet::NoteGame`. The stand-in checks and `--reference`
were repeated after each build: tick logs and memory images of x86-64 and arm64 identical
(7,798 rows), the comparison with the rig the same text as before, `fpcheck`
2e77df4dc13ec9c5, `frames=2309 ... fields=2413 units=113069192` (the new fix set; it was
`units=113069982`), **patch set 073064bb (99 words)**, `pnghash` b4ed3d8917871960. The
README's check 3 now says what a tester must look at for the pacing ("How even is it")
and its key list has V and the mouse. In the test plan above, step 5's "patch set
3f5b1e14 (90 words)" is now 073064bb (99 words).

**2026-10-13 07:48, by the owner of `rt/`, `render/`, `app/` since last night** (the
passes below are as their author left them): the folder `rta-windows` was built again
from the tree as it is now - with the render speed work (`gen-vu/vu1_fast.cpp` is found
and compiled), the runtime's and the renderer's changes of `native-app.md` section 11,
and the network work's `netdrv.cpp` of this morning; the patch set is now 27f61e1d with
91 words. The stand-in checks and `--reference` were repeated: same results (tick logs
and memory images of x86-64 and arm64 identical, `fpcheck` 2e77df4dc13ec9c5,
`frames=2309 ... units=113069982`, `pnghash` b4ed3d8917871960). The Windows program does
not have the Mac program's new pacing (its own window thread paces as before). Details:
`native-app.md` 11.9. `build_win.py` now leaves out stray copies of generated and object
files (names with a space, as a file synchroniser makes them) and links `--mac` with
CoreVideo and CoreGraphics (the Mac program's display link).


**State saved 2026-10-12 21:22 (second pass). Nothing is half-done in the sources.** The
brief of this pass - the network in `rta_app.exe`, the merged graphics in it with the art
pack read without Qt, proofs on the Mac, the tester's folder - is done as far as a Mac can
take it. Every file is in "The parts that are new" and "Changes to existing files"; what
was run is in "The network" and "The picture options".

What exists now, by the clock:

| Made | What |
|---|---|
| 21:20 | by clang: `rta_app.exe` (27.7 MB: network, picture options, films), `rta_native.exe`, `fpcheck.exe`, `pnghash.exe`; the folder `rta-windows` (85 MB) with them, `play.bat`, `online.bat`, `server.txt` (no address in it), `README.txt` (five checks; this build's figures filled in), `boot-check.rig`, `pngtest/` (961 made PNG files) |
| 21:18 | by GCC (`--compiler gcc`, the same sources and translation): `rta_app_gcc.exe` (25.4 MB), `rta_native_gcc.exe`, `fpcheck_gcc.exe`; all 76 files compile unchanged, no link warning; the first and the third are in the folder. Their arithmetic was not compared with anything, as before |
| 21:20 | `--reference`: `rta-windows/boot-check-mac.txt` (`frames=2309 ... fields=2413 units=113069982`, `VU0: 466083 microprogram calls, 26111361 instructions`), `standin/patch-set.txt` (3f5b1e14, 90 words), `standin/png-hash.txt` (b4ed3d8917871960) |
| 20:21 - 20:29 | `--standin`: all six stand-ins from the tree of that time; 21:13 `standin_compare.py` (`standin/compare-pass2.log`); `fpcheck_x64` and `fpcheck_arm64` run again: 2e77df4dc13ec9c5 on both |
| 20:58 | `--mac`: `win/mac/rta_app`, `rta_app_pngread`; 21:01 `win/mac/arttest/` (the two runs with the pack) |
| 21:01 - 21:11 | the three lobby games (`standin/online/x64pair`, `macpair2`, `mixed`, each with its `.log`) |
| 20:11 - 20:42 | `standin/pngcheck-pack.log`: the reader against QImage over `local/hd-pack` |

To repeat everything from nothing (each line is independent of the session that wrote this;
`RTA_DISC` set; about 25 minutes of compiling at load 200):

```
python3 tools/recomp/app/build_win.py                  # the Windows programs and the tester's folder
python3 tools/recomp/app/build_win.py --standin        # stand-ins, with rta_native_online_x64 / _arm64
python3 tools/recomp/app/build_win.py --pngcheck       # pngcheck, pnghash_x64, pnghash_arm64
python3 tools/recomp/app/build_win.py --reference      # boot-check-mac.txt, the figures in README.txt
python3 tools/recomp/app/build_win.py --mac            # win/mac/rta_app, rta_app_pngread
python3 tools/recomp/app/build_win.py --compiler gcc   # the second-chance programs
O=local/recomp-out/win/standin; S=$PWD/$O
python3 tools/recomp/net/lobbypair.py run $O/online/x64pair --program $S/rta_native_online_x64 --play 1800 --level drunare --play2 1800
python3 tools/recomp/net/lobbypair.py run $O/online/mixed --program $S/rta_native_online_x64 --join-program $S/rta_native_online_arm64 --play 3000 --level drunare --play2 3000
RTA_NATIVE_APP=$PWD/local/recomp-out/win/mac/rta_app python3 tools/recomp/net/lobbypair.py run $O/online/macpair2 --host window --join native \
    --program $S/rta_native_online_arm64 --play 1800 --native-arg=--sym --native-arg=$PWD/names.tsv   # and one pair per symbols/*.tsv
python3 tools/recomp/app/win/pngtest.py && $O/pngcheck local/recomp-out/win/pngtest
$O/pngcheck --threads 6 local/hd-pack/replace.nosync local/hd-pack/dump.nosync          # half an hour
```

(The lobby games need the lobby server on this computer, which this work did not start and
did not touch; they send nothing beyond it. Never point a test at the public server.)

Open ends, in the order they matter:

1. **The tester's report** - now five steps. Steps 1 and 2 as before. Step 3 is the first
   time anybody sees the window. Step 4 is the first Windows OpenGL driver to meet the
   multisampled surface, `centroid` and `textureGrad`: if the 3-D scene is black or the
   shaders do not compile, `--plain` and `--antialiasing off` separate the causes, and
   the log has the driver's message. Step 5 is the first time the Winsock body runs:
   expect trouble first at the connection under way (`sock::connect_check`), at the
   firewall (the room is reached, the game never starts), and in the dialogue (there is
   `--name NAME` to go round it).
2. **The Winsock body has no test at all.** A person with a PC could also build a small
   console program over `net/sock.h` (connect to a port that refuses, to one that
   accepts; a datagram to a closed port and then a `recv_from`) before a whole game is
   tried; it was not written because it could not be run here.
3. **The shared `bin/rta_app`** has not been rebuilt with the socket layer by this work;
   its owner's next `app/build.py` does it (same file, same flags as `--mac`, which
   played a lobby game).
4. **`png_read.h` is 1.8 times slower than libpng.** Enough for three background
   threads; if a pack loads visibly slowly on a PC, the inflate's inner loop (one symbol
   at a time, a 10-bit table) is the place.
5. From the first pass, unchanged: `vu0.h` with an infinity or NaN operand; the film
   decoder on x86-64; controllers that are not XInput; building on Windows itself (MSYS2:
   `build_win.py` has the branch - now with the network and the new files in it - and
   nobody ran it).
6. Not done in the Windows program: the control socket (`control.h`) and `app latency`;
   settings are read, not written back (as on the Mac); `rta_native.exe` has no network
   (a headless online check for a tester would be `net/online.cpp` linked into it, as the
   stand-ins are built).

**State saved 2026-10-12 15:45 (first pass; kept as it was written - of its open ends, 4
"the network on Windows" and 7 "the two documents" are done by the second pass above, and
its table of what exists is superseded by the one above).** Nothing is half-done in the sources; the tree compiles
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
