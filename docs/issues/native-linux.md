# The native application for Linux

Started 2026-10-19. The native application (`docs/issues/native-app.md`: the game's own
code translated to C++, with our runtime, renderer, sound library and input) for Linux on
x86-64 and aarch64, made from the same sources as the macOS (`app/app_main.cpp`, Qt) and
Windows (`app/win_main.cpp`, Win32) programs. Everything below was built and run in an
Ubuntu 24.04 container (Docker Hub's official `ubuntu:24.04` image, nothing else pulled) on
this Mac: colima profile `rta` (vz, 8 processors, 12 GB, Rosetta for x86-64), the tree
mounted read-write at its own path, the disc image's folder mounted read-only. Each claim
says **Ran** (in that container, unless it says the Mac) or **Read**.

Nothing derived from the game is in the repository: the translation
(`local/recomp-out/linux/gen-app`, `gen-orig`), objects, programs, logs and the tester's
folders are under `local/recomp-out/linux/`.

## STATE (2026-10-26): Hardcore mode with the attributes, Ran

The aarch64 `rta_app` (`build_linux.py --docker arm64 --no-game`) in the colima `rta` container joined a room hosted by the
Mac's `rta_app_next --combat hardcore`: boot, a new character on the game's screens, the host's Hardcore choice taken up,
level 6 by the test aid, the mode's character screen (points, spell slots), valor > drunare: **1,574 ticks in step, no
shared column differs** (`native-souls-combat.md` 4.13). A script needs `names.tsv` and `symbols/` beside the program.

## STATE (2026-10-21, evening): the tester's kit

`linux_main.cpp` has the tester's kit (`docs/issues/native-app.md` 15): F8 and the L3 + R3 chord (`testerkit::pad`), the
box's keys and its text by SDL_TEXTINPUT, F9, the overlay, the tick rows at each blank, the crash handler, an SDL box
about a crash report of the run before; `build_linux.py` compiles `app/testerkit.cpp` and gives the container the build
id made outside it (`RTA_BUILD_ID`; git there sees another owner). **Ran** in the aarch64 container (Xvfb, offscreen,
`RTA_TESTERKIT=1`): a report from the hub (zip with the picture, `local/tester/lin1/box.png`), a crash on purpose (signal
11, 14 frames as `rta_app(+offset)`), zipped and announced at the next start. The Godot library for Linux
(`tools/godot/build_lib_linux.py --arch arm64`) builds with the kit (`rtag_report_*` exported). (A note for the next
tester: the disc image's folder is given to the container with `--mount type=bind,...` - `-v` with that path found
nothing this time.)

## STATE (2026-10-21): aiming by looking

`linux_main.cpp` calls aiming by looking (`app/fpaim.h`, `docs/issues/native-first-person-aim.md`) where `app_main.cpp`
does: `fpaim::blank` after the controls' `translate`, `fpaim::drawn` in `fpview::on_drawn`, `--aim look|off`, the
`combat.aim` setting, `app aim ...`, the figures line; `build_linux.py` compiles `app/fpaim.cpp`. **Ran** (aarch64,
`build_linux.py --docker arm64 --no-game`: 16 of 91 files): a room hosted by the Linux `rta_app` in the container
(`--aim look --view first`, a Ranger, Xvfb) and joined by the Mac's `rta_app_next` (`--view first`, a Wizard, no
option: "the host plays with aiming by looking on: so does this copy now"), our own `rendezvous.py` on 127.0.0.1:41981
(container through 192.168.5.2), `local/aim/net/n2aim.py --external` with `local/aim/r8/as-linux-aim.py` (`lin1`):
**4,381 ticks in step** hub > drunare, one death, `compare.py ticks`: no shared column differs (the aim block's columns
included); mode on in every tick on both; 19 arrows at 17 pitches (-10.3 to +59.5 degrees) and 6 Shock of Frost at 6
pitches (-33.4 to -6.0); routes direct both ways (16 ms). The Godot library for Linux has the mode too
(`build_lib_linux.py`, built and dlopen-tested, 66 exports).

## STATE (2026-10-20, morning): the combat mode, the world work, the installer

**What changed.** `linux_main.cpp` (and `win_main.cpp`) now call the souls-style combat mode
exactly where `app_main.cpp` does (`docs/issues/native-souls-combat.md`): `soulscombat::blank`
after the controls' `translate`, `overlay` before `backend->execute`, the camera in
`fpview::on_drawn`, `--combat souls|off`, `combat.*` settings, `app souls ...`, the figures in
the final report; `build_linux.py` compiles `app/soulscombat.cpp`. The first-person world work
of 2026-10-20 (`fpworld.cpp`: the decoder-slot guard, the box margin, the texture shelf
`rt_shelf` in `rt/runtime.cpp`) and the view and controls settings were already shared files:
rebuilt, nothing to wire. **Ran** (both architectures, `build_linux.py --docker both --original`):
x86-64 and aarch64 88 + 71 files, exit 0 (47 s wall: only what changed was compiled).

| Check (all **Ran**, 2026-10-20 09:55 to 10:05) | Result |
|---|---|
| `fpcheck`, aarch64 / x86-64 | byte for byte the 54 lines of macOS arm64 / macOS x86-64; `2e77df4dc13ec9c5` |
| boot check (`boot-check.rig`), aarch64 and x86-64, against the Mac arm64 headless program rebuilt from the current sources | the same 692 lines apart from the `frames= wall=` line (frames 2309, fields 2413, units 113069252; VU0 466083 calls, 26111361 instructions); the rebuilt Mac program is itself the same as the 2026-10-19 reference |
| rig comparison, `rta_app_orig` (now with the combat mode linked in, off), aarch64 and x86-64 | **`rig-final-compare.txt` line for line** both: the mode off changes nothing |
| a room with the mode on: host the Linux aarch64 `rta_app --combat souls` in the container, joiner the Mac's `rta_app_combat` (no option: it took the host's choice, "the host plays with the souls-style combat mode on: so does this copy now"); our own `rendezvous.py` on 127.0.0.1:41979 (container through 192.168.5.2), `local/souls-combat/net/n2souls.py --external` (`online/souls1`) | room HV4B2, launched both, **5,016 ticks in step** hub > drunare, the arena fight there: 2 deaths and the reload after everybody died; `tools/rig/compare.py ticks`: **no shared column differs on any tick** (64 shared columns, the game's and the mode's; only `l_inp`, `l_drawframe` are per machine); the mode on in every row on both; player 0: 4 dodges, 35 light, 1,717 ticks blocking; player 1: 6 dodges, 1 heavy, 30 light, 5 presses refused with an empty bar, stamina at 0 in 148 ticks; 1 hit not landed (a dodge), 1 blocked hit paid; routes direct both ways (16 / 17 ms) |

**The installer: `tools/install/install-linux.sh`** (with `tools/install/fromdisc.py`, shared
with the Mac and Windows scripts): installs `clang g++ python3 libsdl2-dev libssl-dev` (apt;
dnf, pacman, zypper lines for Fedora, Arch, openSUSE - those three Read, not Ran) after asking,
takes the disc image (zenity / kdialog / typed), copies `SLUS_209.73` out of the ISO 9660 image
and checks its checksum 4028A55F, runs `build_linux.py`, writes `local/install.txt` and
`rta-native.desktop` into `~/.local/share/applications` and the desktop. **Ran** in a fresh
`ubuntu:24.04` container (Docker Hub's official image, arm64, as root; the repository's
tracked files copied into an empty folder): apt from the Ubuntu archive, the translation (51
files), 88 files compiled in 35 s, `rta_app`, `rta_native`, `fpcheck` linked, the launcher
written; then in the same container `fpcheck` byte for byte the Mac arm64 lines and the boot
check the same 692 lines as the Mac (189 words of the fix set: the sign-in patch is not in a
fresh folder, as for every player). 56 s from an empty container to the end. **Not run**: the
launcher by a person on a desktop, `zenity`/`kdialog`, `sudo`, x86-64 (the same script),
other distributions.

## STATE (2026-10-19, evening)

| | x86-64 | aarch64 |
|---|---|---|
| build (`build_linux.py --docker amd64\|arm64 --original`) | Ran: 70 + 66 files, exit 0 | Ran: 70 + 66 files, exit 0 |
| `fpcheck` against the Mac build of the same file | Ran: **the same 54 lines, byte for byte**, as `fpcheck` for macOS x86-64 (Rosetta); "must agree everywhere" `2e77df4dc13ec9c5` | Ran: **the same 54 lines, byte for byte**, as `fpcheck` for macOS arm64 |
| `rta_native` boot check (`boot-check.rig`: power-on, memory card, front end, character creation, into the first level) against the Mac arm64 headless build of the same translation | Ran: the same 692 lines apart from the one `frames= wall=` timing line (frames 2309, fields 2413, units 113069252; VU0 466083 calls, 26111361 instructions) | Ran: the same |
| rig comparison (`rta_app_orig --offscreen --unpaced --plain`, the rig's controller rows replayed, `fight3.rig`) | Ran: **`rig-final-compare.txt` byte for byte** | Ran: **`rig-final-compare.txt` byte for byte** (the file every Mac build since 2026-10-12 reproduces) |
| window, OpenGL | Ran under Xvfb: SDL 2 (x11), OpenGL 4.5 core, Mesa 25.2.8 llvmpipe | Ran: the same |
| room game against the Mac's `bin/rta_app` | Not run (the same sources; only aarch64 was played) | Ran: 1,163 ticks in step through `hub` into `drunare`, every shared column identical, direct routes ("Online") |
| TLS (`net2/tls_openssl.cpp`) | Read (the same source as aarch64) | Ran: against a TLS room service with test certificates, three ways (below) |
| a real Linux desktop, a GPU driver, a sound device, a controller | Not run | Not run |

## What is built

```
python3 tools/recomp/app/build_linux.py --docker both --original    # on the Mac: the container builds
python3 tools/recomp/app/build_linux.py --original                  # on Linux itself (apt install clang python3 libsdl2-dev libssl-dev)
```

`--docker` translates the game once on the Mac (`recomp.py` into `linux/gen-app` and, with
`--original`, `linux/gen-orig`), writes the Dockerfile into `local/recomp-out/linux/docker/`,
builds the image `rta-linux:<arch>` when it is missing (apt: clang 18, SDL2, OpenSSL 3,
Xvfb, Mesa) and runs the script inside it as the Mac's user. In `local/recomp-out/linux/<arch>/`:

| Program | Is |
|---|---|
| `rta_app` (aarch64 26.5 MB, x86-64 29.8 MB, not stripped) | the game in a window: `app/linux/linux_main.cpp`; the network (netdrv over `net/sock.h`'s BSD body, the one-step online, a room of our own: net2 with TLS) |
| `rta_app_orig` | the unpatched game without the network: the rig comparison's program |
| `rta_native` | the machine with nothing attached (`app/linux/headless_main.cpp`) |
| `fpcheck` | `app/win/fpcheck.cpp` |
| `../rta-linux-<arch>/` | the tester's folder: the three programs, `play.sh`, `online.sh`, `server.txt`, `README.txt` (the Mac's figures filled in), `boot-check.rig` |

Linked dynamically against the system's SDL2, libssl/libcrypto 3 and glibc (2.39 in
Ubuntu 24.04: the programs need that or newer); libstdc++ and libgcc are inside
(`-static-libstdc++ -static-libgcc`). Compiler: clang 18 with the flags of every other
build (`-O2 -fwrapv -fno-strict-aliasing -ffp-contract=off -frounding-math`).

Build time (Ran): aarch64 4,380 s of wall time for the first 70 files at a load average
of about 500 on the Mac (the VM's processors are shared with it); x86-64 under Rosetta
in about the same.

## The parts that are new

| File | Does |
|---|---|
| `app/build_linux.py` | the build (uses `build_win.py`'s translation, compile and link helpers); `--docker` |
| `app/linux/linux_main.cpp` | the program: `win_main.cpp`'s options, hand-over queue, pacing, reports and `app ...` script lines over SDL 2 (window, OpenGL context, keyboard, mouse with relative mode for the look views, events from other threads as SDL user events); `--play-host`, `--play-join`, `--service` as `app_main.cpp`; the driver's notes into the window's title; `--log FILE` (the output stays on the terminal otherwise; `play.sh` tees it into `rta-data/rta_app-log.txt`); data beside the program, else `$XDG_DATA_HOME/rta-native` |
| `app/linux/glsdl.h`, `glsdl.cpp`, `QOpenGLContext`, `QOpenGLExtraFunctions` | the OpenGL functions through `SDL_GL_GetProcAddress` behind Qt's two class names (as `app/win/wgl.h`): `render/backend_gl.cpp` compiles unchanged |
| `app/linux/pad_linux.cpp` | `pad_host.h` over SDL 2's game controllers (the map and dead zones of `pad_mac.mm` / `pad_win.cpp`); the window's thread copies the state, the game's thread reads the copy |
| `app/linux/headless_main.cpp` | `rta_native`: `main_headless.cpp` with `native.py`'s defaults |
| `sound/audio_out_linux.cpp` | the sound device: SDL 2 audio, 48 kHz 16-bit stereo, 512 frames; both `open_device_sink` and `open_device_puller`; gain applied to the samples; no device = the timer, as everywhere |
| `net2/tls_openssl.cpp` | `tls.h`'s link: OpenSSL over a non-blocking socket, TLS 1.2 minimum, SNI, `SSL_set1_host` (an address: `X509_VERIFY_PARAM_set1_ip_asc`), the system's store (`SSL_CTX_set_default_verify_paths`) or the anchors of one file only |
| `net2/hash_linux.h` | `hash.h`'s SHA-256 and HMAC from libcrypto, random bytes from `getrandom()` |
| `app/linux/play.sh`, `online.sh`, `server.txt`, `README.txt` | the tester's folder |

Changes to shared files (each an `#elif` for Linux; the other systems compile what they did):

1. `sound/audio_out.cpp`: `#elif defined(__linux__) && defined(RTA_SDL_AUDIO)` includes `audio_out_linux.cpp`.
2. `net2/tls.cpp`: `#elif defined(__linux__) && defined(RTA_OPENSSL)` includes `tls_openssl.cpp`; the header comment.
3. `net2/hash.h`: `#elif defined(__linux__)` includes `hash_linux.h`.
4. `net/sock.h`: `program_dir()` reads `/proc/self/exe` on Linux.

Not changed: the runtime (`rt/host_posix.cpp` was already for macOS and Linux), the
renderer, `backend_gl.cpp`, `pipeline.h`, `netdrv.cpp`, `fpu.h`, the generated code.

## Floating point

The guarantee is the other platforms': SSE2 scalar arithmetic on x86-64, the AArch64 FPU,
no fused multiply-add (`-ffp-contract=off`), rounding toward zero set at run time with
`-frounding-math` (the runtime's start-up line in every run: "arithmetic: toward zero,
denormals are zero - the processor's mode on every thread that runs the game's code").

**Ran**: `fpcheck` (every operation of `rt/fpu.h` and `rt/vu0.h` over corner values and
695,556 / 719,104 / 200,848 cases) prints on Linux aarch64 exactly the 54 lines of macOS
arm64, and on Linux x86-64 exactly the 54 lines of macOS x86-64. The two Mac builds differ
from each other only in five lines of the "any" class (vu add, sub, mul, madd, msub over
NaN patterns: the processor's NaN payload, as `native-windows.md` says); the line "must
agree everywhere" is `2e77df4dc13ec9c5` on all four.

**Ran**: the boot check (2,413 fields from power-on into the first level with the
translated game, the runtime, VU0) prints the same 691 lines on Linux aarch64, Linux
x86-64 and macOS arm64 (`local/recomp-out/linux/check/`, `reference/boot-check-mac.txt`).

One difference that is not arithmetic (Ran, in every window run): "vu1: this processor's
flush-to-zero mode is not what the translated programs count on - interpreting" - on Linux
the ahead-of-time translated VU1 programs (`gen-vu/vu1_fast.cpp`) are not used and VU1 is
interpreted. The picture is the same (the interpreter is the reference); it costs speed.
Not looked into further.

## The rig comparison (native-app.md 12, 13)

`local/recomp-out/linux/rig/rig.sh` is `app-test/s12/rig.sh` with the program in the
container: `rigcompare.py boot-native --replay` through `app-test/rigsnd/rc.py`, the
program `rta_app_orig --offscreen --unpaced --size 640x448 --plain -- ... --opt
sound-clock=machine` under Xvfb, then `boot-compare`.

- **aarch64 (Ran)**: `rig/a64-compare.txt` is **`app-test/merge/rig-final-compare.txt`
  line for line** (`cmp`): 5 episodes, 7,797 rows of the tick log, the same columns
  identical and the same timing and controller-byte notes as every Mac build.
- **x86-64 (Ran, under Rosetta)**: `rig/x64-compare.txt` is the same file, line for line.

## Online

The room service is the Mac's own (`tools/rendezvous/rendezvous.py`, plain text), the
game `tools/recomp/net2/n2party.py --external` (two copies, the host's room code, the
game's own character screens, start, drawn input, the level name written in one lockstep
tick, more play there, tick logs compared column by column). The host is the Linux
`rta_app` (aarch64, `--plain`, a 320 x 240 test window under Xvfb) in the container; the
joiner the Mac's `local/recomp-out/bin/rta_app` (Oct 17, as it is; same translation, fix
set 9ac29719, 189 words) as a test window (`app-test/s13/n2/as-app.py`). Wrappers in
`local/recomp-out/linux/online/` (`as-linux.py`, `linapp.sh`).

**Ran (2026-10-20, 09:38 to 09:40, `online/lan6`, load average about 100)**: room U4769
hosted by the Linux copy, joined by the Mac copy; both made a character on the game's own
screens; "launched: 2 players, first level hub"; the level name written in one lockstep tick;
**1,163 ticks in step through `hub` into `drunare`**, both scripts to their end, no death.
Column by column over all 1,163 common ticks: **every shared column identical** (seed, level,
player count, button maps, the previous tick's sync hash, both players' position, state, hit
points, gold, experience, out-of-step flags, dropped counts: 25 columns); only the two local
ones differ (`l_inp`, `l_drawframe`: each copy's own input and draw counters). Routes:
**direct** both ways (the Linux copy reached the Mac's UDP socket at its LAN address, 22 ms;
the Mac reached the container through the VM bridge, 33 ms), nothing relayed. Patch set
9ac29719 (189 words) on both. The Linux copy drew 37.0 pictures a second (`--plain`,
llvmpipe).

An earlier attempt (`online/lan5`, 2026-10-19 19:32) also launched (room 5Q45U, both in
`hub`, 1,058 ticks in step, routes through the service's relay) but never reached the level
change: the Linux copy ran at a few pictures a second at a load average of 200 to 500, the
Mac copy's script gave up waiting for `drunare` after its 12,000 frames, and the Mac then
slept until morning.

What it took (Ran): with `n2party.py` starting its own service the copies get
`net-local-only=1`, which makes net2 refuse a service that is not on the copy's own
computer - the container's copy never connected ("lan1", "lan2"). With `--external` and a
service of our own: on this Mac, at the time of the runs, TCP from anywhere but the loop-back
interface to a listening program on the Mac (its LAN address 10.x and the VM bridge's
192.168.64.1) was accepted but carried no data, even for a ten-line Python server (Tailscale's
network extension is active; not looked into, nothing changed). The container reaches the Mac's
loop-back through the VM's own gateway (lima's host address 192.168.5.2), so the service
listens on 127.0.0.1 and the Linux copy is given `192.168.5.2:41977`, the Mac copy
`127.0.0.1:41977` (both plain text: a private address).

**TLS (Ran, aarch64)**: `net2cli` (net2's terminal client, built in the container with
`tls_openssl.cpp`) against `rendezvous.py --tls-cert/--tls-key` on localhost inside the
container, certificates from `tools/rendezvous/check.py`'s test authority, trusting that
authority only (`RTA_NET2_TLS_CA`):

| Service's certificate | Result |
|---|---|
| for localhost, signed by the authority | link up, a player registered, a room hosted (code given) |
| for another name, same authority | refused: "The service's certificate is not accepted for localhost: hostname mismatch (trusted: only ca.pem)" |
| signed by another authority | refused: "... self-signed certificate in certificate chain (trusted: only ca.pem)" |

**The public room service (Not run to the end)**: a connection to the project's public
service by its host name, from the container and from the Mac's own Python `ssl`, both got
"wrong version number" in the handshake at the time of the run - the service did not answer
TLS on its port then. The server was not touched. The system-store path of
`tls_openssl.cpp` (`SSL_CTX_set_default_verify_paths`) is therefore Read, not Ran.

## Not run

- a real Linux desktop: a GPU driver (Mesa on hardware, NVIDIA's), Wayland, display-locked
  pacing (Xvfb has no vertical blank: "the driver cannot be told to wait for the display;
  the clock paces"), full screen, the mouse look, a game controller, a sound device (the
  container has none: "sound: no sound device; the sound side runs on a timer");
- speed: under Xvfb with llvmpipe at 4x multisampling, at a Mac load average of 200 to 500,
  a 320 x 240 window ran 14.9 pictures a second; meaningless for a real machine;
- the name question of the lobby path on a terminal (`ask_name_on_terminal`); the lobby
  server path (`--online`, `--host`, `--join`) of the old one-step online;
- `online.sh`, `play.sh` by a person.

## How to repeat

```
colima start rta --cpu 8 --memory 12 --vm-type vz --vz-rosetta --mount "$HOME/champions-re:w" --mount "<the disc image's folder>:r"
python3 tools/recomp/app/build_linux.py --docker both --original
L=local/recomp-out/linux        # lin.sh ARCH NAME PROGRAM ...: the program in the container under Xvfb
$L/lin.sh arm64 fp $L/aarch64/fpcheck                       # compare with the Mac's fpcheck
$L/rig/rig.sh a64 "$PWD/$L/lin.sh arm64 rig $PWD/$L/aarch64/rta_app_orig" --plain
```
