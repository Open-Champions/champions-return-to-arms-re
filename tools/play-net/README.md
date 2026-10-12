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
| `latency.py` | test: time from a button press to the first changed picture, and the spacing of presented pictures |
| `src/RtaNet.h`, `RtaNet.cpp` | the network behind the emulated Ethernet adaptor (stand-alone C++, nothing of the emulator in it) |
| `src/Rta.h`, `Rta.cpp`, `RtaMac.mm` | what joins it to the application: patches, the memory card's network setting, display patches, settings, thread priority, the control socket |
| `src/RtaPad.mm` | game controllers through macOS's GameController framework: the first one attached is the pad in port 1, with nothing to bind |
| `src/RtaUi.cpp` | what is added to the application's windows: *Help → Controls…* |
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
later runs only copy `src/` in and rebuild what changed. When the patch itself has
changed, `build.sh --reset` puts Play!'s files back and applies it anew. `local/` is
ignored by the repository. (A build from nothing in another directory, with the
script, was done once to check it.)

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
| the same | The game names a size of 1024 × 1024 in `TEX0` for most interface textures, whatever their real size (it addresses them by texel; the size only says where coordinates wrap). Play! took the megabyte behind the address as the texture and uploaded it again whenever anything in it changed: 103 such textures, about 103 MB, per frame | `GetUsedTextureSize`: the texture is the rectangle the game actually transferred to that address — 8-bit textures are sent as 32-bit pictures of half the width and height, which share their block order — and failing that the pages it touched (`GSH_OpenGL_Texture.cpp`; only for plainly repeated textures) | trace of one frame: named 1024 × 1024, used 320 × 192, 256 × 112, 144 × 48, 112 × 32 … |
| the same | The game keeps a ring of sixteen textures in the console's 4 MB of video memory and sends about 340 textures and palettes again in every frame. Play! knew a texture by its address, so every re-send was converted and uploaded again in the middle of drawing (on macOS each upload also ends the render pass and waits for the graphics processor) | a texture is known by **what the game sent**: a 64-bit figure (XXH3) of the bytes of every piece sent to that address and of where each piece went, taken while they arrive (`RecordUpload`, `PrepareTextureByUpload` in `GSH_OpenGL_Texture.cpp`). A texture sent again is found by that figure without reading or converting anything. A table of which upload last wrote each 256-byte block of video memory tells whether a texture is still whole; one that is not (never seen in this game) is read back from memory and known by its texels, as a first version of this change did for all. Large direct-colour pictures (film frames) are updated in place as before | power-on to the first level and 40 s of walking, per frame: 595 draws found their texture by upload, 0 by reading memory, 0.000 textures made once the level had been seen (339 in all); 60.0 frames a second at 4× |
| Textures got a new name again and again; dumped pictures were full of blocks of other textures (7,516 dump files for the first level where a few hundred were expected, new ones for ever) | the first version of the change above read a texture back from video memory, as the rectangle bounding what had been sent. But the game does not send rectangles of texels: an 8-bit texture arrives as one or more rectangles **of 32-bit pixels** that cover only what its triangles use (an L shape, say), of any height — and one line of 32-bit pixels is two lines of 8-bit texels that are not next to each other. The rest of the bounding rectangle keeps whatever texture lay there before, different each time the ring puts the texture somewhere else | the figure of what was sent (above) names the texture; texels that were not sent are 0 in the texture made and transparent in a dump. Which texels were sent is not worked out but done: the pieces are written, all ones, into a second video memory in the format they were sent in and read back in the texture's format with the code that reads textures (`GetUploadCoverage`) | two runs, power-on to the first level and 40 s of walking: 339 dump files each, the same 339 names, the same bytes in every file; contact sheets of all of them looked at: no foreign blocks |
| A patch of streaky noise over the left quarter of the health and mana bars | the bars' fills are 4-bit textures 104 texels wide (33 of them: 11 frames of animation in 3 colours). Making a texture the size that was sent rather than the 128 that `TEX0` names (the row about 1024 × 1024 above) met Play!'s converters for 4- and 8-bit textures, which copy whole blocks of 32 or 16 texels and take the width to be a multiple of that: every row spilled its last 24 texels — never sent, leftovers — over the start of the next | `ConvertTexture`: conversion at the next multiple of the block width, rows moved together afterwards | found by switching, in one running game, each display patch and the way textures are known (`displaypatch`, `texmode` of the control socket): the noise stayed with all of them; pictures of the bars before and after |
| the same, smaller | A picture the game renders its shadows into lives among its textures; Play! takes every framebuffer to be 1024 lines high, so textures landing "inside" it were uploaded into it (704 lines for 128 of use), through one texture that the driver had to wait for | the upload is cut to the lines about to be drawn, and uses a texture of its own each time (`CommitFramebufferDirtyPages`) | profile: 19 % of the video thread asleep in the driver before, under 4 % after |
| The whole picture jumps up and down by a line, sixty times a second; menus and text tremble | The game is made for an interlaced television. It draws every other picture half a line lower (`XYOFFSET` 1824.5 instead of 1824.0), and it keeps interface art as two stacked half-height pictures, one per field, drawing the one for the current field a line higher or lower. A television interleaves the two fields; the emulator showed them one after the other in the same place | **display patches** built into the application (`Rta.cpp`, `g_displayPatches`; each applied only where the expected instruction is found; they change drawing only, so they are not part of the shared patch set or its figure): `0x19C904` — the drawing offset is the same for both fields; `0x19D9EC` — `gfx_displayField` always answers "first field". `--rta-interlaced` leaves the game as it is; the emulator then moves the two fields half a line apart when it shows them (`renderer.fieldoffset`), which steadies the interface but leaves the 3-D picture moving by a quarter line | burst on the memory-card screen: consecutive pictures byte-identical (before: 12.8 % of samples differ, ±0.57 rows); title, network dialog, level: 0.00–0.01 rows of shift (before ±2.7 to ±3.6) |
| Menus, text and the bars have half their height in detail (each line doubled) | with one field picture only, interface art is 224 lines stretched to 448. The game has a second way of drawing it, for its half-rate mode: both field pictures over the same place, one to the even lines and one to the odd, under the GS scanline mask (`SCANMSK`) — which Play! did not emulate (both passes covered all lines) | `SCANMSK` in the fragment shader (`GSH_OpenGL_Shader.cpp`: discard by the parity of the console's line, at any resolution factor; part of the render state), and four more display patches that put the game's two sprite drawers and two text drawers on that path (`0x17AB58`, `0x17BAE4`, `0x180D2C`, `0x180FEC`: each loads "1" instead of the rate flag at `0x44fdb4`; nothing else that reads the flag is touched, so the game stays at full rate) | pictures of title, character creation, lobby: glyphs with 448 lines of detail; still 0.00–0.01 rows of shift |
| (found on the way) | the handler compared its 64-bit shader capability word as 32 bits, so a change only in the upper bits (alpha-fail method, two depth flags) did not select another shader | compared as 64 bits (`GSH_OpenGL.cpp`) | read in the source |
| Everything is a staircase of blocks | the picture was computed at the console's 640 × 224 per field and stretched | resolution factor 4 by default (2560 × 896 per field; the 3-D target is 5120 × 1792) | pictures; speed unchanged, see above |
| The picture is 7 % too wide | "fit" took the 640 × 448 pixels as square (10:7); a television shows them as 4:3 | `GetPresentationViewport` uses 4:3 unless the widescreen setting is on | pictures: bars left and right |
| The game runs a little slow all the time on a busy computer (57.6 frames a second), sound runs dry | the frame limiter slept "what is left of the average frame" in 250 µs steps and never made up for a late wake-up | `FrameLimiter.cpp` rewritten: a deadline per frame, late frames are caught up | 60.0 where it was 57.6 |
| Movement stutters although nothing is slow | the machine was timed by its own timer and drifted against the display: a picture stayed for one refresh, the next for three | frames start on a refresh of the display (`RtaMac.mm`, a display link; two refreshes per frame at 120 Hz, one at 60, the timer when the display's rate is neither), and a finished picture is handed to the window after the refresh before the one it is meant for (`CGSHandler::PresentClock`). `--rta-timer` goes back to the timer | 240 consecutive pictures in the first level: 238 spaced two refreshes, 1 spaced one |
| A press is answered later than it need be | the limiter's wait was at the end of the vertical blank, after the controller had been read | the wait is immediately before the controller is read (`PS2VM.cpp`) | `latency.py`: in a menu the first picture after a press shows the change (6–7 ms after the press with the timer; one frame time with display timing). In the first level an attack shows in picture 5 or 6 (82–104 ms): the game's own |
| The application slows down when its window is covered, or when the computer is busy | macOS treats its threads as ordinary work | the machine and video threads ask for interactive priority; the application asks not to be napped (`Rta.cpp`, `RtaMac.mm`) | — |
| Sound comes a tenth of a second after the picture | sound was handed over in pieces of 100 ms | 30 ms (`audio.spublockcount`, in the settings dialog) | not measured by ear |
| The emulated Ethernet chip stops receiving after 64 frames, or after the game restarts into another program | receive index wrapped at 512 instead of 64, and was not reset when the driver starts again; reads past the end of the receive buffer | `Iop_Speed.cpp` (as the test rig corrects from outside, live-rig.md section 13.2), plus a poll hook and "ready for a frame" | the lobby path below |

Not changed, known:

- **A one-pixel line along the right and bottom edge of some interface panels** at 4×:
  where a sprite ends, the upscaled picture samples the texel just outside it. Not looked
  into further.
- **Films** are stored as two field pictures as well and probably still alternate between
  them (not looked at).
- Only the title screens, the menus, character creation, the lobby screens, the first
  level, one dungeon level and the arena level have been looked at, on pictures, standing
  or walking a few steps; all ran at 60 frames a second. See docs/play-online.md, "What is known not to work".

## Controller and keyboard

Play! reads controllers on macOS as raw HID devices (`InputProviderMacOsHid`): it has
report layouts for three Sony product numbers, takes every other device's elements by
their HID usage number, and leaves it to the player to bind each button in the
Controller Manager — nothing works until that is done, and what a button is called
differs from pad to pad. `RtaPad.mm` uses GameController.framework instead, which
presents every controller macOS supports (by USB or Bluetooth) as the same extended
gamepad. `CPadHandlerRta` asks for its state once a frame, on the machine's thread, at
the place where the machine reads its pad (immediately before the frame is computed),
and puts it on top of what Play!'s bindings and the keyboard gave: pressed buttons are
added, a stick that is not at rest replaces the keyboard's. Attaching and detaching come
as the framework's notifications; the controller object is kept in a list under a lock
until it is detached, so reading from the machine's thread is safe against unplugging.
Only the first controller is read, and only while the application is the active one
(two copies on one Mac would otherwise both move). `rta.log` gets a line for every
attach and detach and for the first press of each button and direction.

| Extended gamepad | PlayStation 2 pad |
|---|---|
| left / right thumbstick | left / right stick: nothing inside 15 % of the way, then evenly to the edge |
| direction pad | direction pad |
| A (bottom), B (right), X (left), Y (top) | ✕, ○, □, △ |
| left / right shoulder | L1 / R1 |
| left / right trigger | L2 / R2, pressed beyond 30 % |
| thumbstick buttons | L3 / R3 |
| Menu (Options on a DualSense) | Start |
| Options (Create, Share, View) and a Sony pad's touchpad button | Select |

Checked: a DualSense by USB attaches (log, `pads` of the control socket, status bar).
With a controller made by the program (`gcpad connect`, `gcpad set …`: the framework's
own settable controller object, attached through the same notification and read through
the same map) every button, three at once, each direction of both sticks, the dead zone
and the trigger threshold arrive as in the table, and the game was driven from the title
into the first level and walked with it. Not checked: a real button press, Bluetooth,
other makes of controller.

The keyboard's defaults (`AutoConfigureKeyboard`, in the patch) are W A S D for the left
stick, the arrow keys for the direction pad, I J K L for △ □ ✕ ○, Q and E for L1 and R1,
1 and 3 for L2 and R2, X and C for L3 and R3, T F G H for the right stick, Return and
Backspace for Start and Select; a data directory that has Play!'s own (left stick on
T G F H) is given them once (`rta.keys`).

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

## Texture dump and replacement

A texture's name does not change from run to run or with where the game puts it in video
memory: it is made of the figure of the bytes the game sent for it, the figure of the
palette it is drawn with (the same texels with another palette are another picture), its
format and its size.

- `--rta-texture-dump` (after `--` on `play.sh`) writes every texture the game draws with,
  once, to `<data>/textures/dump/<texels>-<palette>-p<format>-<width>x<height>.png`
  (`<format>` is the console's number: 19 is 8-bit, 20 is 4-bit, 0 is 32-bit).
  Power-on to the first level and 40 seconds of walking gives 339 files, the same 339 in
  every run. Dumping costs speed while new textures appear; afterwards nothing.
- A picture is written when it is still being drawn 30 frames after it was first drawn.
  Pictures that are made anew every frame (film frames that are small enough to be kept as
  textures at all) are therefore not written; `tex_short_lived` of the control socket's
  `info` counts them.
- A PNG file of the same name in `<data>/textures/replace/`, **of any size**, is drawn in
  its place (read when first needed; the directory is listed once at start).
  `--rta-textures DIR` puts both directories somewhere else. A replacement changes the
  picture only.
- A file whose name starts with `mem-` is a texture that could not be told by what was
  sent and was read back from video memory; its name may not come back. None appeared
  in the scenes listed at the end.

How a replacement has to be laid out (for a pipeline that takes a file and gives back a
file of 4 times the size):

- **Same name, same proportions, any whole multiple of the size.** The picture is
  stretched over the same rectangle of texture coordinates, so a 160 × 160 file becomes
  640 × 640. Nothing else has to be told to the application.
- **An ordinary rectangle is right, also for textures the game sent as an L shape.** The
  file is the smallest rectangle (from the top left corner) that holds everything that
  was sent. Texels that were not sent are written as red 0, green 0, blue 0, alpha 0. The
  game's triangles do not use them, so a replacement may hold anything there — but an
  enlarging filter reads across that border: fill the unsent part from its neighbours
  before enlarging (or enlarge colour and alpha separately), or the border of the used
  part comes out darkened.
- **Alpha is the console's: 128 is opaque**, 255 is not "more opaque", and many world
  textures have alpha 0 on purpose (the game's blend modes read it the other way round:
  `docs/spec/render-pipeline.md` section 6). A viewer shows such files half or fully
  transparent. Keep the alpha channel exactly as it is (enlarge it as a grey picture of
  its own, or with nearest-neighbour), and use tools that do not premultiply: one pass
  through `sips` turned every texture with alpha 0 black here. That alpha 0 also marks
  unsent texels does no harm: those are never drawn.
- **Interface art is two field pictures, one above the other**: the top half of the file
  is the picture's lines 0, 2, 4 …, the bottom half its lines 1, 3, 5 …
  (`docs/formats/model-texture.md`, "Interface pictures are two fields"). The game draws
  each half over the same place, to the even and to the odd lines. It has to stay that
  way: to enlarge such a picture, interleave the two halves into one picture, enlarge
  that, and take it apart again into even and odd lines, one above the other. Which
  files these are does not show in the name: everything the 2-D drawers draw (menus,
  the bars and their frame, inventory, text) except head portraits, map icons and effect
  sprites; a picture whose top and bottom halves look alike is one.
- Indexed (4- and 8-bit) and 32-bit textures only; a replacement is always 32-bit.
- Checked with 492 textures replaced by double-size copies with red and blue swapped:
  drawn in place, 60 frames a second (before the change of names; the mechanism is
  unchanged). Dumps are the game's art: they stay under `local/`.

## Control socket and tests

`--rta-control <path>` makes the application listen on a UNIX socket; `ctl.py` sends
commands (press and release buttons, wait frames, read the game's memory, pictures of
what is presented, consecutive pictures with their times, the display state, thread
processor times, settings; `ctl.py --help` lists them). `smoke.py` uses it to go from
power-on to the lobby server's first screen and stops there. Pictures are game output:
they stay under `local/`.

- `shot FILE` is the window's picture; `shotfb FILE` is the picture as the machine drew
  it — 640 × 224 console pixels per field times the resolution factor, 2560 × 892 at 4×,
  twice as wide as high for a 4:3 screen — whatever the size of the window.
- `--rta-test "TEXT"` is for test runs on a computer somebody is using: the window is
  titled "AGENT TEST - TEXT", is small, is put behind the other windows, has no Dock icon
  and never takes the keyboard. Say in TEXT what is switched off.
- For telling faults apart in a running game, a second at a time: `displaypatch all|N 0|1`
  takes a display patch out or puts it back; `texmode 0|1|2` makes textures known by
  what was sent (0, the default), by the texels read back from video memory (1), or by
  address as Play! itself does (2; not usable after a switch, only from the start).
- `info` counts, among other things: `tex_made` (textures made), `tex_by_upload` and
  `tex_by_memory` (draws that found their texture one way or the other),
  `tex_memory_read`, `tex_in_place`, `tex_short_lived`, `uploads`.
- `RTA_TEXLOG=FILE` in the environment writes a line for every texture made (frame,
  figure, format, size, address, pieces).
