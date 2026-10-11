# play-net — the game in a window, with its network

Champions: Return to Arms (SLUS-20973 v2.00) in the desktop application of the
[Play!](https://github.com/jpd002/Play-) PlayStation 2 emulator, changed so that a person
can sit down and play it online on a Mac: video, sound, keyboard and controller, the
game's own network stack reaching a lobby server and the other players, the test patches
applied while it runs, and no set-up step.

Play! needs **no PlayStation 2 BIOS file** (it has its own). You need your own disc image.
Nothing of the game and nothing of Play! is in this directory: what is here is our own
source (`src/`), a patch against one Play! commit (`play-net.patch`) and scripts. What it
has been seen to do, and what not, is at the end; how to play is in
[docs/play-online.md](../../docs/play-online.md).

| File | What it is |
|---|---|
| `build.sh` | clones Play! at commit `83700b2c31e593bc94e845b4b31b797be84dda59` into `local/play-playable`, applies the patch, copies `src/` in, builds `local/play-playable-build/Source/ui_qt/Play.app` |
| `play.sh` | starts the application with the disc image, a data directory under `local/play-data/`, the patch file and the list of sections, and the lobby server's address |
| `play-net.patch` | the changes to Play! (18 files): the Ethernet chip, the graphics handler, the frame limiter, the front end's hooks |
| `src/RtaNet.h`, `RtaNet.cpp` | the network behind the emulated Ethernet adaptor (stand-alone C++, nothing of the emulator in it) |
| `src/Rta.h`, `Rta.cpp`, `RtaMac.mm` | what joins it to the application: patches, the memory card's network setting, display patches, settings, thread priority, the control socket |
| `sections-suggested.txt` | the patch sections `play.sh` applies by default (the suggested set of `docs/online-setup.md`) |
| `ctl.py` | sends commands to a running application over its control socket (buttons, memory reads, pictures) |
| `smoke.py` | test: power-on to the lobby server's first screen, with the network's log and the speed |

## Build

Apple silicon macOS; tested with Apple clang 21, CMake 4.4, Ninja 1.13 and Qt 6.11 from
Homebrew.

```
brew install cmake ninja qtbase
tools/play-net/build.sh
```

`qtbase` is the part of Qt the application needs (Widgets); `brew install qt` works too.
The first run clones Play! with its submodules (about 1 GB) and compiles about 560 files;
later runs only copy `src/` in and rebuild what changed. `local/` is ignored by the
repository.

## Start

```
tools/play-net/play.sh --disc "/path/to/your disc image.iso" [--server ADDRESS]
```

Without `--server` the lobby server is taken to run on this computer. `--player 2` starts
a second copy with its own settings and memory card. `play.sh --help` lists the rest;
anything after `--` goes to the application (`--help` there lists its `--rta-…` options).
Settings, the memory card and the log `rta.log` are in `local/play-data/player<N>/`.

## What was wrong in the emulator for this game, and what was changed

Measured on an M5 Pro, in the game's first level (`hub`) unless said. "Burst" is the
control socket's `burst` command: consecutive pictures as they are presented, compared
pixel by pixel. Processor time is each thread's own clock, so it does not depend on what
else the computer is doing.

| Fault a player sees | Cause | Change | Check |
|---|---|---|---|
| Slow motion in every level: 17–20 frames a second instead of 60, sound breaking up, everything late | Play!'s OpenGL handler set the framebuffer up again after every texture the game sends — about 790 times a frame — and each time bound it and attached the depth buffer anew. On macOS OpenGL runs on Metal on a tile-based graphics processor: every such change ends the render pass and writes out and reads back the whole colour and depth buffers | `SetupFramebuffer` binds and attaches only when something differs (`GSH_OpenGL.cpp`) | video thread 46–51 ms of processor time per frame before; with this and the two below 10–12 ms; 60.0 frames a second at resolution factor 1, 4 and 8 |
| the same | The game names a size of 1024 × 1024 in `TEX0` for most interface textures, whatever their real size (it addresses them by texel; the size only says where coordinates wrap). Play! took the megabyte behind the address as the texture and uploaded it again whenever anything in it changed: 103 such textures, about 103 MB, per frame | `GetUsedTextureSize`: the texture's size is bounded by what the game actually transferred to that address, and by the buffer width (`GSH_OpenGL_Texture.cpp`; only for plainly repeated textures) | trace of one frame: named 1024 × 1024, used 256 × 192, 256 × 128, 128 × 64 … |
| the same | The game keeps a ring of sixteen textures in the console's 4 MB of video memory and sends about 340 textures and palettes again in every frame. Play! knew a texture by its address, so every re-send was converted and uploaded again in the middle of drawing (on macOS each upload also ends the render pass and waits for the graphics processor) | `PrepareTextureByContent`: a 64-bit figure (XXH3) of the texels finds the texture already made from them; nothing is uploaded after the first frames of a scene. Large direct-colour pictures (film frames) are updated in place as before | per frame: 127 re-sent textures recognised, 0 created, 717 unchanged |
| the same, smaller | A picture the game renders its shadows into lives among its textures; Play! takes every framebuffer to be 1024 lines high, so textures landing "inside" it were uploaded into it (704 lines for 128 of use), through one texture that the driver had to wait for | the upload is cut to the lines about to be drawn, and uses a texture of its own each time (`CommitFramebufferDirtyPages`) | profile: 19 % of the video thread asleep in the driver before, under 4 % after |
| The whole picture jumps up and down by a line, sixty times a second | The game is made for an interlaced television: it draws every other picture half a line lower (`XYOFFSET` 1824.5 instead of 1824.0), and draws interface art from two stacked half-height pictures, one per field, a line apart. A television interleaves the two; the emulator showed them one after the other in the same place | two **display patches** built into the application (`Rta.cpp`, `g_displayPatches`; each applied only where the expected instruction is found; picture only, so not part of the shared patch set): `0x19C904` — the drawing offset is the same for both fields; `0x19D9EC` — the interface drawers are always told "first field". `--rta-interlaced` leaves the game as it is, and then the emulator moves the two fields half a line apart when it shows them (`renderer.fieldoffset`), which steadies the interface but not the 3-D picture | burst on the memory-card screen: consecutive pictures byte-identical (before: 12.8 % of samples differ, ±0.57 rows); title, network dialog, level: 0.00–0.01 rows of shift (before ±2.7 to ±3.6) |
| Everything is a staircase of blocks | the picture was computed at the console's 640 × 224 per field and stretched | resolution factor 4 by default (2560 × 896 per field; the 3-D target is 5120 × 1792) | pictures; speed unchanged, see above |
| The picture is 7 % too wide | "fit" took the 640 × 448 pixels as square (10:7); a television shows them as 4:3 | `GetPresentationViewport` uses 4:3 unless the widescreen setting is on | pictures: bars left and right |
| The game runs a little slow all the time on a busy computer (57.6 frames a second), sound runs dry | the frame limiter slept "what is left of the average frame" in 250 µs steps and never made up for a late wake-up | `FrameLimiter.cpp` rewritten: a deadline per frame, late frames are caught up | 60.0 where it was 57.6 |
| A press is answered later than it need be | the limiter's wait was at the end of the vertical blank, after the controller had been read | the wait is immediately before the controller is read (`PS2VM.cpp`) | see "Response" below |
| The application slows down when its window is covered, or when the computer is busy | macOS treats its threads as ordinary work | the machine and video threads ask for interactive priority; the application asks not to be napped (`Rta.cpp`, `RtaMac.mm`) | — |
| Sound comes a tenth of a second after the picture | sound was handed over in pieces of 100 ms | 30 ms (`audio.spublockcount`, in the settings dialog) | not measured by ear |
| The emulated Ethernet chip stops receiving after 64 frames, or after the game restarts into another program | receive index wrapped at 512 instead of 64, and was not reset when the driver starts again; reads past the end of the receive buffer | `Iop_Speed.cpp` (as the test rig corrects from outside, live-rig.md section 13.2), plus a poll hook and "ready for a frame" | the lobby path below |

Not changed, known:

- **Interface art at half its vertical resolution.** With the display patch the menus,
  text and bars are drawn from one of their two field pictures (224 lines stretched to
  448) — which is what each field showed before, alternating. Drawing both halves into
  one picture is what the game itself does in its half-rate mode, under the GS scanline
  mask (`SCANMSK`), which Play! does not emulate. That would be the way to full-height
  interface art: `SCANMSK` in the fragment shader, and the game's interface drawers
  forced onto that path (eleven places read the flag at `0x44fdb4`). Not done.
- **Films** are stored the same way and still alternate between their two halves.
- Only the title screens, the menus, character creation and the first level have been
  looked at, on pictures. See docs/play-online.md, "What is known not to work".

## The network

`RtaNet.cpp` is a port of the network in `tools/rig/rig.cpp` (the `Ether…` functions),
widened from "one server on this host" to real remote hosts. The emulated machine is
alone on a made-up network (198.18.0.0/15, the range set aside for test networks) with
this code as its gateway 198.18.0.1:

- **ARP** for every address but the machine's own; **DHCP** (the machine gets a random
  198.19.x.y, kept in the settings, so that two players do not report the same
  "own-network" address); **ping**;
- **DNS**: `con.soegames.net` gets the lobby server's address, every other name "does
  not exist" (which is also what keeps the game from waiting on Sony's sign-in servers);
- **TCP** is ended here and carried on a host TCP connection to the real destination
  (non-blocking; the machine's connection request is answered when the host's connection
  stands);
- **UDP**: one host socket per UDP port of the machine, for every destination — what a
  "full cone" router does, which is what the game's hole punching wants: the lobby
  server sees the same address and port for the game's socket as the other players must
  send to. The host socket takes the same port number as the machine's (4000–4004) when
  it is free, so that a router can be told to forward those ports.

Three things beyond the rig:

- **The server's other address.** The lobby's gateway tells the game where the lobby is
  (`public_ip` of the server's `config.ini`). A server at home hands out its public
  address, which a player on the server's own network often cannot reach; a server that
  hands out its private address cannot be reached there from outside. The first reply on
  a gateway connection is read, and when it names another address than the one the
  gateway was reached at — and they are not both public addresses — that address is
  treated as the server too (`--rta-server-public` sets it by hand).
- **Two emulators on one computer** (`--rta-loopback`, on by itself when the server is
  on this computer): the server sees both at one address and tells each to find the
  other there; a datagram for the server's address on a port that is not the server's
  goes to 127.0.0.1 on that port, and what arrives from there is shown to the machine as
  coming from the server's address.
- Datagrams for another machine's own-network address (the game tries that as well as
  the address the server saw) are dropped: they exist nowhere else.

**The memory card's network setting** is written directly (`WriteNetcnf` in `Rta.cpp`):
the four files Sony's set-up program saves for "Ethernet adaptor, automatic address".
Two are text scrambled with a key from the console's identification number, which is
the same for every Play! machine: each 16-bit word rotated left by 6, 3, 3, 6, 3, 3 …
bits and inverted. The files are byte for byte what the set-up program saved on Play!
(compared with the rig's), without its icon; the game lists the setting.

**Patches.** `--rta-patch-file` with `--rta-patch-sections` (names, `@file` or `*`), and
`--rta-extra-patch` for further files applied whole (the local sign-in patch). Only
applied when the executable is `SLUS_209.73` with PCSX2's checksum `4028A55F`. As PCSX2
does with its every-frame patches, a word that is not what the patch says is written
again at every vertical blank. The status bar and `rta.log` show a figure for the set
("set xxxxxxxx", from the addresses and values of the shared sections only): every
player in a game has to have the same.

## Control socket and tests

`--rta-control <path>` makes the application listen on a UNIX socket; `ctl.py` sends
commands (press and release buttons, wait frames, read the game's memory, pictures of
what is presented, consecutive pictures with their times, the display state, thread
processor times, settings). `smoke.py` uses it to go from power-on to the lobby server's
first screen and stops there. Pictures are game output: they stay under `local/`.
