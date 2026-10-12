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
| `play-net.patch` | the changes to Play! (19 files): the Ethernet chip, the graphics handler (textures, sprites, the scanline mask), the frame limiter, the keyboard's defaults, the front end's hooks |
| `latency.py` | test: time from a button press to the first changed picture, and the spacing of presented pictures |
| `src/RtaNet.h`, `RtaNet.cpp` | the network behind the emulated Ethernet adaptor (stand-alone C++, nothing of the emulator in it) |
| `src/Rta.h`, `Rta.cpp`, `RtaMac.mm` | what joins it to the application: patches, the memory card's network setting, display patches, settings, thread priority, the control socket |
| `src/RtaPad.mm` | game controllers through macOS's GameController framework: the first one attached is the pad in port 1, with nothing to bind |
| `src/RtaSound.cpp` | the sound handler: a held reserve, counts of every fault, a WAV file on request |
| `src/RtaUi.cpp` | what is added to the application's windows: *Help → Controls…*, the *Online* menu, the first start's question for the disc image |
| `package.sh` | makes `local/dist/Play-RTA.app` of the built application: Qt inside, the patch list inside, its own name, signed for this computer |
| `sections-suggested.txt` | the patch sections `play.sh` applies by default (the suggested set of `docs/online-setup.md`) |
| `ctl.py` | sends commands to a running application over its control socket (buttons, memory reads, pictures) |
| `smoke.py` | test: power-on to the lobby server's first screen, with the network's log and the speed |
| `upscale.py` | enlarges dumped textures for the replacement folder, each kind of picture in its own way ("Upscaled art" below) |
| `disctex.py` | names and writes out the textures kept in the disc's lumps without playing (model, monster and item textures, interface art) |

## Build

Apple silicon macOS; tested with Apple clang 21, CMake 4.4, Ninja 1.13 and Qt 6.11 from
Homebrew.

```
brew install cmake ninja qtbase
tools/play-net/build.sh
tools/play-net/package.sh      # optional: local/dist/Play-RTA.app, to double-click
```

`qtbase` is the part of Qt the application needs (Widgets); `brew install qt` works too.
The first run clones Play! with its submodules (about 1 GB) and compiles about 560 files;
later runs only copy `src/` in and rebuild what changed. When the patch itself has
changed, `build.sh --reset` puts Play!'s files back and applies it anew. `local/` is
ignored by the repository. (After the last change the script was run on a second copy
of the Play! checkout with an empty build directory: it put Play!'s own files back,
applied the patch, copied `src/` in and built everything; the patched files were the
same as the working tree's.)

`package.sh` copies the built application to `local/dist/Play-RTA.app`, puts the patch
file and the list of sections into `Contents/Resources/rta` and the licences of Play!,
of the libraries it is built with and of Qt into `Contents/Resources/licences`, gives it
its own name and identifier, lets `macdeployqt` (part of `qtbase`) copy the Qt frameworks
in, and signs it ad hoc. An application bundle that holds the patch file behaves as a
packaged application (`Rta::EarlyInit`): data in
`~/Library/Application Support/Play-RTA/player<N>/`, the disc image asked for and checked
(`Rta::CheckDisc`: `SYSTEM.CNF` names `SLUS_209.73` and the program's checksum is
`4028A55F`; `--rta-check-disc FILE` gives the verdict on a command line), server and
player number from the *Online* dialog (`launch.ini`), the sign-in patch looked for in
the data directories and beside the application and never inside it. Tested by starting
it with `open` and driving it through the control socket: the first start asks for the
image; an image of another game and one of SLUS-20973 with another program are refused
with the reason; the right one is remembered; the first level was reached at 59.99
frames a second; a second start goes on from the remembered image. To macOS such an
application is a program of its own: a disc image under Desktop, Documents or Downloads
that is opened from the remembered path (not picked in the file dialog) makes macOS ask
the person once for access to that folder.

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
| A dark line one pixel wide down the right edge of interface panels at 4× (and thin vertical lines over the picture behind the pause menu) | the GS takes a pixel's sample at the pixel's top left corner, OpenGL at its centre, half a pixel further along. The game draws its interface with half a texel to the pixel and a quarter of a texel added to the coordinates, so that a GS reads every texel at .25 and .75; read half a pixel later that is .5 and exactly on the border between two texels, and for the last pixel of a sprite 128.0 of a picture that ends at 128. At 1× the wrong column is half a console pixel and is blended away; at 4× it is a line | `Prim_Sprite` moves a sprite's texture coordinates back by half a pixel's worth: the texture is read where the GS reads it, and at higher factors evenly on both sides of that place. What a sprite covers is unchanged; triangles are untouched (`GSH_OpenGL.cpp`) | coordinates of every interface sprite of a frame logged (x 454…710, u 0.25…128.25, point sampled); pictures of the pause menu's corner at 4× and 1× before and after: the lines are gone; consecutive pictures of the menu still identical; 60.0 frames a second |
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
| Sound comes a tenth of a second after the picture | sound was handed over in pieces of 100 ms | 30 ms (`audio.spublockcount`, in the settings dialog) | see "Sound" below |
| Clicks and short gaps in the sound, four or five a minute, more while a level loads | Play!'s sound handler queues each piece as it comes and starts the source when it finds it stopped: no reserve is kept, so a frame that is a few milliseconds late leaves the output without sound; and nothing matches the machine's pace to the sound device's | a sound handler of our own (`src/RtaSound.cpp`): starts when one piece and 40 ms are queued, and holds that amount by making the sound up to half a per cent shorter or longer | five minutes in the first level: 20 times dry with 100 ms pieces and 27 with 30 ms as Play! does it, 0 with the new handler; see "Sound" below |
| The emulated Ethernet chip stops receiving after 64 frames, or after the game restarts into another program | receive index wrapped at 512 instead of 64, and was not reset when the driver starts again; reads past the end of the receive buffer | `Iop_Speed.cpp` (as the test rig corrects from outside, live-rig.md section 13.2), plus a poll hook and "ready for a frame" | the lobby path below |

Looked at, at 4× (pictures of the machine's own output, `shotfb`; 60.0 frames a second
in each): the publisher's logo and the opening film, title, menus, character creation,
the first level with the bars and the pause menu, a dungeon level (`fire1`: weapon
trails), an underwater level (`wat1`: its opening cutscene with the letterbox, bubbles),
the arena (`drunare`: the cutscene at its gate, a fight against five opponents with
weapon trails, torches); the same still scenes at 1× beside them. Levels were entered by
writing their name to the game's pending-level word (0x41b6d0), which is what a level
script does.

- **The opening film** plays as whole, steady pictures. The logo before it is shown as a
  448-line interlaced frame, the film itself in the game's usual 224-line mode; eight
  consecutive presented pictures in each part are at the same height (best vertical
  shift within 0.06 of a window row; a picture alternating between its two fields would
  show 1.4). Its pictures go through Play!'s own path for large direct-colour pictures
  (one texture updated in place: 410 draws for logo and film), are never kept as
  textures and so never dumped.
- **Not reached**: the inventory, shop, skill and map screens (Start opens the pause
  menu offline; which button opens the others was not found in the time), and spells
  (the test character has none). Nothing is known to be wrong there; nothing was seen.

## Sound

Nobody listened; this is what was counted. `RtaSound.cpp` counts every time the output
ran dry (and for how long, from the clock), every piece thrown away, how much sound was
queued, and samples at full scale; `--rta-sound-wav` writes what the machine hands over
to `sound-<time>.wav` in the data directory (game audio: looked at and deleted; never
in the repository). `sound` and `sound reset` of the control socket give the counts.
`--rta-sound-plain` makes the handler queue as Play!'s own does, `--rta-sound-block N`
sets the piece. Three copies ran at the same time for each row (load average 14 to 18),
five minutes each after the level or the title had come up, walking and attacking in the
level:

| Where | Handler, piece | Ran dry | In all | Longest | Queued after a piece, ms (least / mean / most) |
|---|---|---|---|---|---|
| first level | Play!'s way, 100 ms (as Play! is) | 20 times | 272 ms | 125 ms | 102 / 119 / 137 |
| first level | Play!'s way, 30 ms | 27 times (2 in a second run) | 171 ms | 27 ms | 31 / 60 / 90 |
| first level | held reserve, 30 ms | **0** | 0 | — | 37 / 71 / 91 |
| title | Play!'s way, 30 ms | 8 times | 11 ms | 8 ms | 31 / 46 / 65 |
| title | held reserve, 30 ms | **0** | 0 | — | 54 / 71 / 93 |

- **Going from 100 ms to 30 ms did not bring the gaps**: they were there with 100 ms (20
  in five minutes) and are a fifth as long with 30. Their cause is that nothing was kept
  in reserve: Play!'s way runs with whatever was queued when the source last started,
  and whether that is enough is luck — the two 30 ms runs in the level, 27 and 2, differ
  only in that the machine ran at 59.96 frames a second in one and 60.00 in the other
  (the display paces it; sound is made at 735 samples a frame, so at 59.96 a little less
  sound is made than is played).
- **The held reserve** is one piece and 40 ms after a piece has been added (71 ms; about
  55 ms on average over time, where 100 ms pieces gave about 70 to 120). The rate
  correction stayed between 0.9994 and 1.0014 (a fortieth of a semitone). The least that
  was left just before a piece arrived was 6 ms in the level, 24 ms at the title: there
  is no room to make the reserve smaller on a busy computer.
- **Power-on and loading** (the minute before each stretch): the machine stops for up to
  a third of a second at a time while it reads the disc, and no reserve of this size
  covers that: 9 to 19 times dry there with the held reserve (0.9 s in all), 46 to 89 with
  Play!'s way (1.2 to 1.6 s).
- **Sound against the emulated clock**: 735.07 samples a frame in every run — Play! makes
  sound for frames of 1/60 s. Sound and picture therefore cannot drift apart; against a
  console's 59.94 frames a second the sound is 0.09 % short for the same number of
  frames, and against the wall clock it runs at 1.00003 when the display paces the
  machine at 60.00.
- **Nothing was thrown away** in any run (no piece without a free buffer, none dropped for
  too much queued).
- **Silence and full scale**, from the WAV files: in the level no stretch of exact silence
  inside sound; 389 samples of 25 million at full scale, in 32 runs of three or more —
  loud hits reach the top of the scale in the machine's own mix (a console's mixer
  saturates the same way; nothing is added after it). At the title two stretches of
  exact silence of 40 and 50 ms (where the music loops), peak 9 dB under full scale.
- The first version of the reserve used the source's own pitch control, set anew for
  every piece; it did not hold the amount (71 ms queued where 56 was asked for, with the
  pitch at +0.3 %) and is gone: the sound is resampled before it is queued (four-point
  interpolation, in step from piece to piece).
- A test run started with `--rta-test` is silent (gain 0); everything else is the same.

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
- Beside each picture it writes `<same name>.json`: **how the game draws with it**, so
  that nobody has to guess from the picture. It is added to as long as the run goes on
  (every two seconds) and by later runs, never made poorer:

  | Field | Meaning |
  |---|---|
  | `width`, `height`, `named_width`, `named_height` | the picture's size and the size `TEX0` names |
  | `whole` | every texel of the picture was sent (false: the zero texels in whole blocks are unsent ones) |
  | `states` | each different way it was drawn, as fields of the GS registers: `prim` (6 sprite, 3–5 triangles), `abe` and `alpha` (blending on, `ALPHA`'s low byte) with `fix`, `test` (`TEST`: alpha test and its reference), `wms`/`wmt` (0 repeat, 1 clamp, 2 and 3 region), `mag` (0 nearest, 1 linear), `tfx`, `tcc`, `scanmsk` (0, 2, 3), `context`. At most 16; `states_overflow` when there were more |
  | `sprite_uv` | u0, v0, u1, v1: the texels sprites drawn to all lines used |
  | `field0_uv`, `field1_uv` | the same for sprites drawn under the scanline mask to their own even lines (counted from the sprite's top) and to their odd lines: the two halves of a two-field picture |
  | `other_uv` | the same for triangles (beyond 0 … named size: the texture repeats) |
- A picture is written when it is still being drawn 30 frames after it was first drawn.
  Pictures that are made anew every frame (film frames that are small enough to be kept as
  textures at all) are therefore not written; `tex_short_lived` of the control socket's
  `info` counts them.
- A PNG file of the same name in `<data>/textures/replace/`, **of any size**, is drawn in
  its place. `--rta-textures DIR` puts both directories somewhere else. A replacement
  changes the picture only. The directory is listed once at start. A file is read when
  its texture is first drawn, by three threads of their own at low priority: until it is
  there the game's own texture is drawn, so reading never holds a frame up (unpacking a
  2688 × 640 picture takes longer than a frame lasts), and at most 24 MB a frame are
  handed to the GPU. A replacement gets mip maps and is drawn with them where the game
  filters (the game's textures have none: a picture four times the size glitters without
  on anything far away).
- `--rta-texture-memory MB` (default 3072) is the video memory replacements may take;
  beyond it those not drawn with for ten seconds are given up and read again when needed
  (`tex_dropped` of `info`). The first level with every replacement at 4× holds 1.4 GB.
- A file whose name starts with `mem-` is a texture that could not be told by what was
  sent and was read back from video memory; its name may not come back. None appeared
  in the scenes listed at the end.

How a replacement has to be laid out (for a pipeline that takes a file and gives back a
file of 4 times the size):

- **Same name, any whole multiple of the size.** The picture is stretched over the same
  rectangle of texture coordinates, so a 160 × 160 file becomes 640 × 640. The factor
  may differ between width and height (two-field pictures below use that). Nothing else
  has to be told to the application.
- **An ordinary rectangle is right, also for textures the game sent as an L shape.** The
  file is the smallest rectangle (from the top left corner) that holds everything that
  was sent. Texels that were not sent are written as red 0, green 0, blue 0, alpha 0. The
  game's triangles do not use them, so a replacement may hold anything there — but an
  enlarging filter reads across that border, and so do bilinear filtering and the mip
  maps: fill the unsent part from its neighbours before enlarging **and leave it
  filled**, or the border of the used part comes out darkened. A level texture is a page
  of 1024 × 1024 of which the game sends and uses a corner (typically 144 × 144 texels
  with a 3-texel margin, of a 672 × 160 dump); `other_uv` says which.
- **Alpha is the console's: 128 is opaque**, 255 is not "more opaque", and many world
  textures have alpha 0 on purpose (the game's blend modes read it the other way round:
  `docs/spec/render-pipeline.md` section 6). A viewer shows such files half or fully
  transparent. Keep the alpha channel exactly as it is (enlarge it as a grey picture of
  its own, or with nearest-neighbour), and use tools that do not premultiply: one pass
  through `sips` turned every texture with alpha 0 black here. That alpha 0 also marks
  unsent texels does no harm: those are never drawn.
- **Interface art is two field pictures, one above the other**: the first field is the
  picture's lines 0, 2, 4 …, the second its lines 1, 3, 5 …
  (`docs/formats/model-texture.md`, "Interface pictures are two fields"). The game draws
  each field over the same place, one to the sprite's even lines and one to its odd
  lines, under the scanline mask. Which files these are and how high a field is does not
  show in the name or the size — the `.json` file says it: a picture with `field0_uv` and
  `field1_uv` is one, and a field has `field1_uv[1] − field0_uv[1] + 0.25` lines. That is
  **not** half the file's height as a rule: a font page of 256 × 180 has fields of 89
  lines, the bars' frame of 160 × 48 fields of 23. (The first pass of `upscale.py` cut
  at half the height and got combs.) And the game reads the first field a quarter texel
  into it and the second from its very first line: V runs `0.25 + line/2` and
  `rows + line/2`.
- **How to lay out the replacement of a two-field picture**: interleave the fields into
  the one picture they are (2 × rows lines), enlarge that by *s*, and write the enlarged
  picture **twice**, one above the other, into a file of *s* times the width and 2*s*
  times the height (the rest of the height, if the dump is higher than two fields, is
  not drawn); the second copy moved up by *s*/2 lines. Each of the game's two draws
  stretches its field over all the sprite's lines, so with twice the vertical factor it
  finds, behind every line of the screen, exactly that line of the enlarged picture —
  whichever of the two draws the mask lets through, at any resolution factor, with point
  sampling as with filtering; the half-line move makes up for the quarter texel. (Taking
  the enlarged picture apart into even and odd lines again, as this section said before,
  shows only every other line of it, the odd ones a line off.)
- Indexed (4- and 8-bit) and 32-bit textures only; a replacement is always 32-bit.
- Checked with 492 textures replaced by double-size copies with red and blue swapped:
  drawn in place, 60 frames a second (before the change of names; the mechanism is
  unchanged). Dumps are the game's art: they stay under `local/`.

## Upscaled art

The game's textures enlarged four times by a learned model (Real-ESRGAN), drawn in place
of the game's own. Three steps, each of which can be done again at any time; only what
is new or changed is worked on:

```
tools/play-net/play.sh --disc IMAGE -- --rta-textures "$PWD/local/hd-pack" --rta-texture-dump
        # play: every texture drawn is written to local/hd-pack/dump, with its .json file
tools/play-net/upscale.py local/hd-pack/dump local/hd-pack/replace \
        --upscaler local/upscaler/realesrgan/realesrgan-ncnn-vulkan      # --scale 2 for a 2x pack
tools/play-net/play.sh --disc IMAGE -- --rta-textures "$PWD/local/hd-pack"
        # play with the pack (add --rta-texture-dump again to keep growing it)
```

The enlarging program is not part of this repository
(https://github.com/xinntao/Real-ESRGAN, `realesrgan-ncnn-vulkan` with its models
`realesrgan-x4plus`, `realesrgan-x4plus-anime`, `realesr-animevideov3`). Dumps and packs
are the game's art: they stay under `local/`.

**Nothing is guessed from the picture.** `upscale.py` reads the `.json` file the
application wrote beside each dump (the section above) and sorts the pictures by how the
game draws them:

| Kind | Known by | What is done |
|---|---|---|
| interface | sprites under the scanline mask, or blended sprites (`ALPHA` 0x44) | two-field pictures (those with `field0_uv`/`field1_uv`) are interleaved, enlarged as the one picture they are and laid out as described above; `realesrgan-x4plus` at full strength |
| level | triangles, texture function 0 (ground, walls, stone, wood, foliage: one pre-lit picture per piece of the level) | `realesrgan-x4plus`; the distribution of brightness is matched as well; only the rectangle `other_uv` names (plus 6 texels) goes to the model, the rest of the page is enlarged plainly |
| model | triangles, texture function 3 (characters, monsters, weapons, props) | `realesrgan-x4plus` at full strength |
| glow | every draw adds to the picture (`ALPHA` 0x48, 0x68) | `realesr-animevideov3` at 0.6, and never brighter than the game's picture around it: what is black stays black |
| sprite | other effects drawn without writing depth, other sprites | `realesrgan-x4plus` at 0.8 |
| environment | only drawn in GS context 2 (the reflection picture, the shadow blob) | left alone |

For every kind:

- **Alpha means what the draws say.** From each state's blend mode and alpha test the
  script works out which alpha values put any of a texel's colour on the screen. Texels
  that cannot be seen (transparent interface art under 0x44; the rim of cut-out foliage,
  which fails the level's alpha test "less than 0x2f"; model texels the test "less than
  0x7f" drops) get the colour of their visible neighbours before enlarging, so no
  fringe of the hidden colour comes out of the enlarged edge. Where alpha 0 is opaque
  (`ALPHA` 1 and 2: level and model textures) nothing is touched. Alpha itself is
  enlarged plainly (bicubic) inside its range, and stays exactly what it is wherever a
  texel and its neighbours have one value. (Letting a model enlarge alpha turned the soft
  shadow round the menu's letters into a hard black outline.)
- **The result has the game's colours.** The model's picture is mixed with a plain
  enlargement and then everything coarser than a texel and a half is taken from the plain
  one; then each pixel is held inside the range of the texels around it (plus 6 of 255).
  A thin olive line stays an olive line: the model alone made the bars' frame a thinner,
  bright yellow one.
- **Where the picture is noise from texel to texel, most of the model is taken away.**
  A photo model draws worms where it finds noise (the grass: every texel differs from
  its neighbours). The script measures that — the energy of differences between
  neighbouring texels against that across two texels, about 4 for noise and 1.5 to 2.7
  for anything drawn with a brush — and lowers the strength there (`calm`: 0.6 of it for
  level textures, 0.8 for the rest). Grass therefore stays close to the game's own, a
  little finer; stone, wood, leaves and skins get the model.
- **Pictures with a side under 12 texels are enlarged plainly** (the bars of the
  interface are 6 or 8 lines high; the model made a maze of their mottled fill).
- **Texels never sent are filled from their neighbours and stay filled**; a border of 8
  texels is given to the model around what it enlarges (the picture's own texels where
  the rectangle lies inside it; repeated edge otherwise; wrapped round where `other_uv`
  shows that the texture repeats and the dump is the whole of it — no such texture
  occurs from power-on to the first level, where every level texture is a page with a
  margin of its own, so that case is untested).

What was looked at to choose (same frame with and without, `texreplace` with the game
paused, pictures `local/play-out/hd2-*.png`): `realesrgan-x4plus-anime` flattens every
surface with grain (stone, parchment, the bars) into flat colour and was dropped;
`realesr-animevideov3` and Lanczos both ring on noise; blurring the texture before the
model turns grass into lichen; enlarging a Lanczos-doubled picture and halving the result
gave a checkered pattern. What came out better than the game's art by eye: the title's logo, all text, the
frames and icons of menus, bars and inventory, stone, leaves, the character's skin and
armour close up. Grass is about as before.

Measured on an M5 Pro, other test runs going on beside (load average 10 to 16):

| | |
|---|---|
| time to enlarge | 394 pictures 4 min 20 s; 25 new ones in a later run 20 s |
| the pack for title, menus, character creation and the first level | 418 files, 257 MB (4×); 72 MB (2×) |
| video memory in the first level | the game's own 335 textures 16 MB; 4× replacements 1.39 GB (310 pictures, mip maps included; 1.46 GB with the inventory's); 2× 350 MB |
| speed with the pack, standing and walking through the level | 60.00 frames a second at 4× and at 2×, as without |

For a computer with little memory make the pack with `--scale 2` (a quarter of the
memory; text and frames are still clean, see `local/play-out/hd2-pack2x-vs-4x.png`), or
lower `--rta-texture-memory`.

**Growing the pack.** A dump holds what a run has drawn. Two ways to more:

- Play with `--rta-texture-dump` and run `upscale.py` again: it does the new pictures
  and those whose `.json` file has since learnt something that changes the work (a kind,
  a larger rectangle). `REPLACE_DIR/upscale-manifest.json` remembers what each file was
  made from; `--force` does everything again, `--list` says what each picture is taken
  for.
- `disctex.py DISC.iso DUMP_DIR` names and writes the textures kept in the disc's lumps
  without playing: they are stored as the packets the game sends, so the figure of the
  bytes, of the palette, the format and the size sent can all be worked out from the
  file (2,075 different pictures: 1,447 model textures, 628 others; checked against a
  dump made by playing, `--check`: all 112 names found in both hold the same picture,
  pixel for pixel). Model textures get a `.json` file saying how models are drawn and
  are enlarged at once; for the others (interface art, effects) the file does not say
  how they are drawn, and `upscale.py` leaves them until a run has drawn them. **Level
  textures cannot be named from the disc**: `<LEVEL>.TEX` holds them packed (header
  flags 0x010c, no upload packet, a table of offsets) and the game unpacks them before
  sending; the unpacker was not rewritten. Neither can the player's own character (put
  together from parts when the game starts) and the two font pages.

Not judged by eye: the glow and sprite kinds (two such pictures from power-on to the
first level), the 2× model (`--scale 2` reduces the 4× result). Not tried: other models (none may be fetched here; `4x-UltraSharp` and
`4x_foolhardy_Remacri`, ESRGAN models of about 65 MB each listed on openmodeldb.info and
made for textures rather than photographs, would be the first to try on stone and ground
— from memory, not checked, and they need converting to ncnn's format); anisotropic
filtering; giving only the used rectangle of a level page to the GPU (it would cut the
memory to about 40 %; the application stretches a replacement over the whole dump);
levels beyond the first; a second player's and monsters' textures in a fight.

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
- `texreplace 0|1` switches the replacement pictures off or on in the running game
  (three frames later the picture is drawn the other way): with the game paused that is
  the same frame with and without. `texreplace reload` lists the folder again and reads
  every picture again, for trying a changed file without a restart.
- `info` counts, among other things: `tex_made` (textures made), `tex_by_upload` and
  `tex_by_memory` (draws that found their texture one way or the other),
  `tex_memory_read`, `tex_in_place`, `tex_short_lived`, `uploads`; `tex_held` and
  `tex_bytes` (the game's own textures and their video memory), `tex_replacements` and
  `tex_replacement_bytes` (replacement pictures held, mip maps included), `tex_pending`
  (asked for and not read yet: 0 before a picture is taken for comparing),
  `tex_dropped`.
- `RTA_TEXLOG=FILE` in the environment writes a line for every texture made (frame,
  figure, format, size, address, pieces).
