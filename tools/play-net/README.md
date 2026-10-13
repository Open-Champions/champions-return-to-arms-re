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

Related pages: [docs/STATE-OF-PLAY.md](../../docs/STATE-OF-PLAY.md) sets this build
beside the other routes to a game, with the measured figures. The patch set applied here
and what it rests on is in [docs/online-setup.md](../../docs/online-setup.md). The same
core changes compiled for a browser are in [tools/play-web](../play-web/README.md)
(notes: [docs/issues/browser-build.md](../../docs/issues/browser-build.md)); a browser
player and a player of this build cannot share a game as built, because the two round
floating-point results differently. The game's code translated to native C++, with no
emulator, is in `tools/recomp/`
([docs/issues/native-recomp.md](../../docs/issues/native-recomp.md)).

| File | What it is |
|---|---|
| `build.sh` | clones Play! at commit `83700b2c31e593bc94e845b4b31b797be84dda59` into `local/play-playable`, applies the patch, copies `src/` in, builds `local/play-playable-build/Source/ui_qt/Play.app` |
| `play.sh` | starts the application with the disc image, a data directory under `local/play-data/`, the patch file and the list of sections, and the lobby server's address |
| `play-net.patch` | the changes to Play! (21 files): the Ethernet chip, the graphics handler (textures, sprites, the scanline mask, frame copies), the frame limiter, the choice of arithmetic in the processor core (`FpUtils`, `PS2VM.cpp`), the keyboard's defaults, the front end's hooks |
| `latency.py` | test: time from a button press to the first changed picture, and the spacing of presented pictures |
| `src/RtaNet.h`, `RtaNet.cpp` | the network behind the emulated Ethernet adaptor (stand-alone C++, nothing of the emulator in it) |
| `src/Rta.h`, `Rta.cpp`, `RtaMac.mm` | what joins it to the application: patches, the memory card's network setting, display patches, settings, thread priority, the control socket |
| `src/RtaOnline.h`, `RtaOnline.cpp` | one-step online: the application presses its own way from power-on to the lobby by the game's state, makes and keeps the account ("One-step online" below; stand-alone C++) |
| `src/RtaPad.mm` | game controllers through macOS's GameController framework: the first one attached is the pad in port 1, with nothing to bind |
| `src/RtaSound.cpp` | the sound handler: a held reserve, counts of every fault, a WAV file on request |
| `src/RtaUi.cpp` | what is added to the application's windows: *Help → Controls…*, the *Online* menu (Play Online, the question for the player name, Forget online login), the disc image at the start (the remembered one, else the one found, else one window that says where to put it), the line across the window that says what is being waited for, and the `ui` commands that read and work these windows in tests |
| `package.sh` | makes `local/dist/Play-RTA.app` of the built application: Qt inside, the patch list inside, its own name, signed for this computer (ad hoc, or with an identity or a stable requirement: "Start-up" below); on request with a default server, "online at start" and the art pack's folder inside, and as a `.zip` (`--help`) |
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
`~/Library/Application Support/Play-RTA/player<N>/`, the disc image found and checked
(`Rta::CheckDisc`: `SYSTEM.CNF` names `SLUS_209.73` and the program's checksum is
`4028A55F`; `--rta-check-disc FILE` gives the verdict on a command line), server and
player number from the *Online* dialog (`launch.ini`), the sign-in patch looked for in
the data directories and beside the application (`package.sh` does not put it inside;
its `--help` names the one exception). Tested by starting
it with `open` and driving it through the control socket: an image of another game and
one of SLUS-20973 with another program are refused
with the reason; the right one is remembered; the first level was reached at 59.99
frames a second; a second start goes on from the remembered image. To macOS such an
application is a program of its own: a disc image or an art pack under Desktop, Documents
or Downloads that is opened from the remembered path (not picked in the file dialog)
makes macOS ask the person for access to that folder - once per build, because an
application signed without an identity is another program to macOS after every build
("Start-up, and the folders macOS guards" below).

**Nobody is asked to choose a file.** When no image is remembered, or the remembered
one is gone, `Rta::FindDisc` looks without any dialog, in this order: the folder the
application is in, `Contents/Resources/rta`, the data folders, then Downloads, Desktop
and Documents with one level of sub-folders each (hidden folders and application bundles
are not entered; a file kept in iCloud and not on the computer is not fetched). A
candidate is any regular file, whatever its name, of 1 to 9 GB that has the ISO 9660
mark at sector 16 (or a `.chd`, `.cso`, `.zso`, `.isz` file of 256 MB or more); the
first that passes `Rta::CheckDisc` is remembered and started. The application's own
places come first because they need nobody's permission: macOS asks once before it lets
a program read Downloads, Desktop or Documents, and a folder that was refused is logged
as "could not be read" and passed over. Only when nothing is found, one window says
"Put the game image in the same folder as this app, or in Downloads, then press Retry",
with *Retry*, *Browse…* (the file dialog, as a way out) and *Not now*. *Online → Choose
the disc image…* still opens the file dialog at once. Tested with labelled test starts
of an unpacked `.zip` in a scratch home: nothing anywhere (the search's list of places
and the window, in the log); a 4.3 GB image under another name beside the application,
with a 2 GB file of zeros beside it (found, accepted, the game's program checked, no
dialog); the remembered image gone and one a folder down in the home's Downloads (found
there); a wrong file named with `--disc` (refused with the reason).

**Defaults inside the bundle.** `package.sh --default-server ADDRESS` and
`--default-online on|off` write `Contents/Resources/rta/defaults.ini` (`server`,
`online`) before the bundle is signed. The application takes a value from there only
when its own `launch.ini` has no such key (`LaunchValue` in `Rta.cpp`): what the person
saves in the *Online* dialog or switches in the menu, an empty server address too, goes
before it, and nothing is ever written into the bundle, so the signature stays good.
The log says where the address came from ("lobby server: … (the default this
application was made with)"). `--zip` packs the signed bundle with `ditto` into
`Play-RTA.zip`; unpacked again, `codesign --verify --deep --strict` passes. `launch.ini`
also takes `textures=DIR`, the same as `--rta-textures DIR`. On another Mac the first
opening of such a copy has to be allowed once in *System Settings → Privacy & Security*
("Open Anyway"), as it is signed ad hoc and not notarised; the Qt frameworks from
Homebrew need macOS 14 or later.

## Start

```
tools/play-net/play.sh --disc "/path/to/your disc image.iso" [--server ADDRESS]
```

### Start-up, and the folders macOS guards

[docs/issues/mac-app-start.md](../../docs/issues/mac-app-start.md) has the whole account
(the release of 2026-10-13 morning showed no window for eleven minutes at its first
start) and the tests; in short:

- **macOS stops a program inside its first `open()` or `opendir()` of anything under
  Desktop, Documents or Downloads until the person has answered its question** about that
  folder. Nothing of that kind happens on the application's own thread any more. The art
  pack's folder is not touched before the game's program is loaded and is then listed by
  a thread of its own (`StartTextureList` in `Rta.cpp`; the game draws its own textures
  until the names are known, then every picture is looked for again). The disc image is
  opened for the first time, checked and - in the packaged application - searched for by
  a thread of its own while the window stays alive (`Rta::WaitReadable`, `RunAside` in
  `RtaUi.cpp`).
- **The window appears at once and says what it waits for**: a line across its top and
  the status bar - "macOS is asking for permission to read the Desktop folder - answer the
  question on screen. Your disc image is there (…). This goes on by itself as soon as you
  have answered (N s)." after one second of waiting; for a folder or file that may not be
  read, a sentence that says so and where to allow it. What could not be read is tried
  again every two seconds and goes on by itself. `rta.log`: "window: shown N s after the
  application started", "window says: …".
- **Places macOS asks nothing about**: the folder the application is in and
  `~/Library/Application Support/Play-RTA/`. The packaged application looks for the disc
  image there first, and takes `textures/` there (`textures/replace/*.png`, for every
  player number) as the art pack when neither `launch.ini` nor the bundle's
  `defaults.ini` (`package.sh --default-textures DIR`) names another folder. The log says
  when the image or the pack in use lies under a guarded folder.
- **Why the question comes back with every build, and what keeps the permission**: the
  designated requirement of an ad-hoc signature is the hash of that very build.
  `package.sh --sign IDENTITY` signs with a code-signing identity of the keychain (a
  self-signed one will do), `package.sh --stable-requirement` signs ad hoc with the
  requirement "the identifier is ours"; either makes every build the same program to
  macOS. The options, with the commands for making a certificate and for moving the image
  and the pack, are in the notes; the last line of `package.sh` prints the requirement
  the build got. (Neither option was run here: `package.sh` was only syntax-checked after
  the change, and the two `codesign` calls were tried on a scratch bundle.)
- Test aids: `--rta-test-folder-wait N` makes the first opening of the image and of the
  pack's folder take N seconds, as it does while the question is unanswered;
  `RTA_TEST_PACKAGED=DIR` in the environment makes the working build take the packaged
  application's paths (`DIR/rta` for what the bundle holds, `DIR/support` for its folder
  in Application Support).

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
| In the game's largest level (`fire3`) everything stops for good at certain places: nothing is presented any more, the level's clock `0x44fdcc` stands, with or without the frame limiter | The game sends a picture as eight layers. Each layer's draw packets go out by DMA from the interrupt of the packet before (`gfx_dmaHandler` 0x16b998), and a layer ends with a packet that writes the GS register `FINISH`; the main thread waits behind a semaphore (0x16c8e0) until the handler has counted that interrupt for all eight. Play! keeps the GS register writes between two vertical blanks in a buffer of 1,310,720 (`REGISTERWRITEBUFFER_SIZE`) and **threw away whatever came when it was full** — triangles and, here, the `FINISH`. Nothing in Play! accounts for the time DMA and VU1 take, so a whole layer of any size arrives between two blanks, and the widest views of this level are more than the buffer holds. The machine then idles for ever: main thread in `WaitSema`, the handler in state 2 with one `FINISH` asked for and none counted (`0x41b4e0` = 2, `0x41b4e6` = 1, `0x41b4e5` = 0), both DMA channels finished, `CSR` without the FINISH bit, no interrupt pending. A scripted event it is not, and it is none of our changes: the buffer is Play!'s own, and the stable build with textures known by address (`texmode 2`) and all display patches off stops at the same place | `CGSHandler::DrainWriteBuffer` (`GSHandler.cpp`, called from `WriteRegister`): a full buffer is processed (its `SIGNAL`, `FINISH`, `LABEL` events), handed to the video thread, waited for, and written from its start again. `info` counts it: `gs_buffer_drains`, and `gs_buffer_most` is the most register writes between two blanks | found with a labelled test instance, the new `hw` command (interrupt, DMA and GS registers of a machine that has stopped) and a temporary trace of DMA starts and ends, GS events and interrupt acknowledgements: the last `FINISH` packet (0x6f40b0) goes through VIF1 and the GIF, and no `FINISH` reaches the GS. Before: the tour's camera stopped the game at place 21–22 of the level's 342 in 4 runs of 4; after: all 342 places gone over without a stop (676 s at resolution factor 1, frame limiter off, 3,079 pictures dumped on the way); the buffer was full 15 times, and the most register writes between two vertical blanks were 2,147,619 (in `shame1`, the heaviest level for textures, 725,558) |
| Heat haze is a rectangle of multicolour noise and blue and white stripes: around every lava golem of `fire3`, over the catapult fire of the first level's opening, as speckle over torches | For the haze (`particle_drawHaze` 0x18fe18) the game copies a piece of its 16-bit draw buffer (56 × 28 to 96 × 48 pixels) into a 16-bit texture of 128 × 64 with a GS local-to-local transfer and draws it back displaced, about 22 times a frame beside one golem. Play!'s OpenGL handler read those pixels back from the graphics card, made them small and wrote them into GS memory **as 32-bit pixels whatever the format of the destination**: two pixels of noise for each. It also made a texture from memory for every one of them | the piece is kept as a texture of its own on the graphics card, at the frame buffer's resolution factor (`FRAME_COPY`, `MakeFrameCopy` in `GSH_OpenGL_Texture.cpp`: a blit, no read-back); the texture set-up finds it by the address, width and format `TEX0` names, and it is dropped when anything else is written there. Where that cannot be done (a piece not put at the start of its destination: not seen in this game) the read-back stays, written in the destination's format now. `info`: `frame_copies`, `frame_copy_uses` | `local/play-out/fx_haze.py` (stands beside the same objects of `fire3`, pauses, takes `shotfb`), frame limiter and pack off, load 21–24. Beside a golem at 4×: noise before, none after; 35.7 frames a second and 22.0 ms of the video thread per frame before, 71.7 and 15.0 after (the read-back was what cost); 1,995 pieces kept in 90 frames and 1,995 textures set up from them. Without a golem near: 68.0 → 104.9 frames a second |
| Along the top of the menu screens a line of another colour, half a console line high (Options, Controls, the title's other pages); one white pixel at the left edge of the skills page | Neither is the emulator's. Both are in the game's own picture, at its very edge, where a television does not look. `drawlog` of the controls screen: the draw buffer is cleared to the title scene's sky colour (0x59, 0x65, 0xa5, which the present pass shows times 0x99 / 0x80: 107, 121, 198, the colour of the line), and the backdrop is one sprite from line 1 to line 449 of the buffer's 448, so line 0 stays as cleared. As the game ships (display patches off) the sprite goes from line 2 on one field and from −0.5 on the other: on a console the top line of every second field is that colour. The white pixel is art: the skill-tree page of the wizard (both sexes; no other class has it) is a picture whose first three lines are a leftover, light grey and transparent but for their first texel (`905de2357a18325f…-p19-512x852`), and the page is drawn from the left edge of the screen. A console puts both into its signal and a television does not show them: the outermost lines and pixels of a picture are behind the rim of the tube (overscan), which games count on | the edge of the picture is not presented (`FlipImpl` in `GSH_OpenGL.cpp`): one line of a field's 224 at the top and at the bottom and the same share of the width, three pixels of 640, at either side, so that the picture keeps its shape and is 0.9 % larger. `edge 0` on the control socket presents everything; `shotfb` is still the whole picture, `shotview` the part presented | the same screen before and after at 4× and at 1× (`local/vq.nosync/shots/controls-*`): the line is there in the whole picture and not in the part presented; inside that part the two are the same pixel for pixel (largest difference 0) |
| At a resolution factor above 1: dust motes are small squares of dots, rain is a quarter as wide and as bright as it should be, the automap's outline is a staircase | Things the console reads unfiltered or draws a pixel wide. The game's interface drawers set point sampling (`TEX1` = 1) and nothing sets it back, so whatever is drawn after them in the same layers is read without filtering — not a choice made for each picture: particles (a mote is a cell of 32 × 32 texels holding eight specks, drawn 6 × 3 to 10 × 5 pixels of the draw buffer), the automap (a strip of tiles of 10 × 10 texels from a sheet of 120 × 160, turned 45°, 1.4 pixels to the texel), models shown in menus. On the console a texel is at most about a pixel and a mote is a glint of two or three pixels; with sixteen times the pixels each texel is a block and the inside of the mote's cell shows as a square of dots. Rain is GS lines (about 1,040 a frame in `strife`), one console pixel wide; OpenGL's lines are one pixel of the enlarged buffer wide and macOS draws no wider ones | `WantsSmoothTexture` (`GSH_OpenGL.cpp`): at a resolution factor above 1 a texture the game reads unfiltered is filtered — except by sprites drawn without a depth test: interface art and text, pixel for pixel, which stay exactly as they are. Where the console draws a texture smaller than it is, it is read at the console's density (the smaller copies of a replacement picture, chosen in the fragment shader from the texels per console pixel): what a console pixel cannot hold is not drawn. A sprite, and anything drawn flat over the picture, reads no texel outside those its own corners span (`texSmooth` 2: the box goes with each vertex), as reading the nearest texel guarantees: a sheet of tiles does not bleed from tile to tile. Points and lines are drawn as bands a console pixel wide (`Prim_Point`, `Prim_Line`). `upscale 0` on the control socket draws as before; `info` counts `smoothed_draws` and `scaled_points` | found with `drawlog`; one paused frame of `strife` before and after (`local/vq.nosync/shots/strife2-*`, crops `sheets/ba2-motes6.png`, `ba2-map-4x.png`): motes are soft glints of the size they have at 1×, the automap's edge is smooth with no lines between its tiles, rain has the weight it has at 1×. The controls screen at 4× is the same pixel for pixel; at 1× nothing of this is at work (the same frame differs by 0.015 of 255, from the row below). Without the art pack the particle sheet has no smaller copies: a mote is then filtered, its specks stay |
| (found on the way) the game's own level and model textures sit half a texel up and to the left of where they belong, and of where their enlarged replacements are drawn: the picture shifts when a replacement comes in | Play! filters indexed textures in the fragment shader (the graphics card cannot: a texel is an index into the palette) and took the texel at the place asked for and the three after it. A texel's colour belongs to its middle: the four are those round the place, the first half a texel before, as the GS has it and as the graphics card does for the textures it filters itself | `GenerateFragmentShader` (`GSH_OpenGL_Shader.cpp`); `texcentre 0` on the control socket reads as before | the same paused frame of `strife` with the pack on and off: mean difference 4.52 of 255 and 1.40 % of the pixels more than 24 apart before, 2.96 and 0.38 % after; with the pack on the change itself moves the frame by 0.05 |
| After the resolution factor is changed in the settings while a game runs, textures are told apart by reading video memory for the rest of the level (357 draws a frame in the first level) and every replacement picture is read from its file again | `NotifyPreferencesChangedImpl` forgot what the game had sent (`ForgetUploads`), the textures made of it and the pictures from outside. A change of settings makes the frame buffers anew and changes nothing in GS memory; a texture the game sends once, not again every frame, never had a known upload again | nothing of it is forgotten there any more (`GSH_OpenGL.cpp`); a reset of the machine still forgets all | the hub, factor 4 → 1 → 4 in the running game: 854 draws a frame find their texture by upload and 0.0 by memory before and after, no memory read, no replacement picture read again; the same after several changes in `strife` and on the controls screen (`tex_by_memory` 0) |
| With the art pack, enlarged pictures replace the game's own in view: during the first moments in a level (for seconds on a busy computer), again after a visit to a menu that was opened while they came in, and all of a level's at once after ten seconds in a menu where the level holds more than the memory allowed | The files were read in the order the game draws — the ground at the far end of the view first, the character and the interface last — by threads at "utility" priority, which a busy computer hardly runs. A picture whose texture was not drawn for two seconds was given up, so a menu threw away what was coming in. Beyond the memory allowed every picture not drawn for ten seconds went at once | read order by what covers the screen (`NotePictureArea`, `g_textureOrder`; `ReadTextureFiles` in `Rta.cpp`), on-screen pictures at "user-initiated" priority; pictures whose texture is not being drawn stay wanted, are read last and handed to the graphics card at the end of a frame (`TakeTexturePicture`, `ContentTextures_EndFrame`); beyond the memory allowed the longest unused go, as many as it takes ("Texture dump and replacement" below). `texorder 0` reads in the old order | `strife`, every picture asked for again (`texreplace reload`), load average about 400 from other work: half of the screen's pending area enlarged after 0.97–1.82 s and all of it after 2.2–3.8 s in the old order, 0.07 s and 0.22–0.26 s in the new (today's release: all after 6.8–7.2 s). A menu opened at once and left open ten seconds: the release gives up 44 pictures, has 52–63 to read on the return and is done 3.9–8.4 s later; this build gives up none, hands over 14–16 while the menu is up, has 3 to read on the return (0.3 s). On the final build at a load average of 180: all in view after 0.22 s against 0.82 s in the old order. The least-recently-used rule was not measured: with the limit at 60 % of what `shame1` held, what one view needs still fitted, on both builds |

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
- **Not reached** in that first look: the inventory, shop, skill and map screens (Start
  opens the pause menu offline; which button opens the others was not found in the
  time), and spells (the test character has none). The visual check and its second pass
  (`docs/issues/visual-check.md`) went through them since, and through what follows.
- **The second visual pass** (2026-10-12; two labelled test instances at 4× with the
  pack, pictures under `local/vq.nosync`): a death and the respawn at the save point; a
  chest and a door opening (the action button held ten frames); the mission menu, which
  opens at the hub's gateway when a mission is available and not complete; both end
  films, the save list after them, and the credits; the ten player-against-player
  levels (alone in an arena the character starts outside its ground: the arenas were
  looked at beside the things placed in them), the nine medal and eight bonus levels;
  `torment2`, `swamp1` and `arachna1` in play; all twelve class and sex choices with
  every skill at rank 10 — the bag's pages, the skill tree, 71 different skills cast in
  the arena. No fault was found in any of it beyond the ones in the table above.
- **After those changes** (the standing checks, final build, other work on the computer
  the whole time): still screens are the same from frame to frame (three consecutive
  pictures of the controls screen at 4× and 1×, of the hub's pause menu and of a paused
  frame of `blood1` and `innovat1`: largest difference 0; `shame1`: 3 of 255 in a few
  pixels). Today's release and this build side by side in the same level at a load
  average of 250 to 290: both 60.0 frames a second in `innovat1` and `blood1`, standing,
  with the pack on and off; the video thread's own time a frame 7.6–7.9 ms against
  7.6–8.0 ms with the pack, 7.6–7.9 against 8.0–8.4 without. One instance alone with
  the pack at a load average of 220 to 240: `blood1` 59.99 standing, 60.03 and 59.64
  walking; `shame1` 59.75 and 59.99 / 59.96; `innovat1` 57.4 and 57.7 / 56.5 in that
  run and 60.0 in the side-by-side run. Heat haze in `fire3`: no block of noise in six
  pictures beside its golems, 2,024 to 2,781 pieces of the frame kept as textures in 90
  frames; beside a golem both builds run at 37 to 41 frames a second under that load
  (video thread 21–25 ms a frame). The set figure in `rta.log` was 3f5b1e14 then, as before (27f61e1d since the flush
  section's third word, "Patches" below).

- **After the start-up work** (2026-10-13, `docs/issues/mac-app-start.md`; one test copy
  at 4× with the pack, load average 8 to 10): the pack's 122,205 names listed aside 0.7 s
  after the game was loaded; title 60.00 frames a second, first level 60.00 standing and
  60.00 walking (video thread 6.7 to 7.3 ms a frame, 259 to 323 replacements held); the
  hub's pause menu within 3 of 255 right after it opens and identical 10 s later, a
  paused frame identical; `fire3`: no block of noise in six pictures, 60.0 at all six
  places.

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

**A peer's disconnect, held back in a game's room** (`RtaNet.cpp`, the same in the
application and in the page; `docs/issues/mac-app-start.md`, "The launch hold"). The
game's launch can leave two joiners with a wrong address for each other, which its own
handshake cannot repair (`docs/issues/three-players.md` cause 1,
`docs/issues/native-online.md` "The disconnect hold"). A datagram that is the game's peer
library's disconnect (8 bytes, `00 05` …) and arrives while the game's lobby state word
says "in a game's room" is shown to the machine 30 vertical blanks late, or as soon as the
state has moved on: by then a joiner has filled its launch tables from connections that
were all still there. Nothing else is ever held, and nothing during a game. The state and
the count of vertical blanks reach the network through `CNet::NoteGame`, which
`COnline::Tick` calls once a frame. `--rta-no-disconnect-hold` switches it off; `info`
(`udp_held`) and `peers` (`held_disconnects`) count.

**One player, one entry.** The players heard from are kept by the address and port the
machine knows them by (not by where a datagram really came from: a relay on this
computer sends from two of its addresses in turn), and what this copy tells a player goes
the way the game's own datagrams to that player go. `peers` shows `from=` when the real
source differs.

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
player in a game has to have the same. For `sections-suggested.txt` as it is now the
line reads "patches: 29 sections, 99 words, set 073064bb" (26 sections, 91 words, set
27f61e1d before three sections were added on 2026-10-13; 90 words, set 3f5b1e14 until
the evening of 2026-10-12, before the flush section got its third word).

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
  changes the picture only. The directory is listed once, by a thread of its own, when
  the game's program is loaded (not on the application's own thread and not before: see
  "Start-up, and the folders macOS guards"); until then, and while the folder cannot be
  read, the game's own textures are drawn. A file is read when
  its texture is first drawn, by three threads of their own: until it is there the
  game's own texture is drawn, so reading never holds a frame up (unpacking a
  2688 × 640 picture takes longer than a frame lasts), and at most 24 MB a frame are
  handed to the GPU. A replacement gets mip maps and is drawn with them where the game
  filters (the game's textures have none: a picture four times the size glitters without
  on anything far away).
- **What is on the screen is read first.** While a picture is being read the renderer
  adds up how much of the frame its texture is drawn over (triangles by their area,
  sprites by their box, both cut to the scissor rectangle) and tells the readers at the
  end of every frame (`g_textureOrder`). They take the largest first — interface art
  counted fourfold: text is what the eye reads —, then what was asked for since the
  renderer last spoke, then pictures whose texture is not being drawn, the most recently
  drawn first; a picture that is on the screen is read as work the person is waiting for
  (`QOS_CLASS_USER_INITIATED`), the others as before as work that may wait. Before, the
  files were read in the order they were asked for, which is the order the game draws
  in: the ground at the far end of the view first, the character and the interface last.
  `texorder 0` on the control socket goes back to that order for comparing;
  `tex_pending_area` of `info` is the number of pixels of the last frame drawn with
  textures whose picture has not come yet.
- **Only the part of a replacement that is drawn with goes to the graphics card.** A level
  texture is a page of which the game draws with a corner (below); the rest of the page
  cost video memory and nothing else — 70 % of it in the heaviest level. From a picture's
  first draw on the application gathers the rectangle of texture coordinates its
  triangles use (the boxes the `.json` file gets), and when the file has been read it
  hands over that rectangle and 4 texels round it, mip maps of its own included, and
  maps the coordinates onto it (`GetTexturePictureCrop` in `GSH_OpenGL_Texture.cpp`; the
  texture matrix in `SetupTexture`; the part is clamped at its own border). Held whole
  as before: pictures drawn by sprites (interface art: other parts of them are drawn
  later, and two-field pictures are laid out their own way), pictures that repeat
  (coordinates beyond the size `TEX0` names), files that are not a whole multiple of the
  game's picture, and parts of nine tenths of the picture or more. A draw beyond the
  part held, or one that takes its texels from a region `CLAMP` names, makes the picture
  be read again for the larger part — the game's own texture is drawn for those frames
  — and after two such times it is held whole (`tex_regrown` of `info`; 4 of the 572 pictures held after a first crossing of the
  heaviest level).
  **The files are untouched**: every pack made so far works as it is and `upscale.py`
  need not know. The other way that was weighed — files cut to the `.json` file's
  `other_uv` with the rectangle in a small file beside them — would have meant writing
  120,000 pictures again or a second pass over them, would have tied a pack to the dump
  it was made from, and a draw beyond the rectangle could not have been served at all.
  `--rta-texture-whole`, or `texcrop 0` in a running game, hands over whole pictures as
  before; `tex_cropped` of `info` counts those held as parts.
- `--rta-texture-memory MB` (default 3072; `texmemory MB` in a running game) is the
  video memory replacements may take; beyond it those longest not drawn with go — not
  drawn with for ten seconds at least, and only as many as it takes to come back to nine
  tenths of it — and are read again when needed (`tex_dropped` of `info`). (At first
  every picture not drawn with for ten seconds went at once: ten seconds in a menu threw
  a whole level's pictures away where the level holds more than is allowed.) The first level with
  every replacement at 4× holds 1.4 GB. The heaviest level (`shame1`) with every
  replacement held is 3.4 GB as parts (11.0 GB whole), so the limit is hardly at work
  any more (figures under "Upscaled art").
- **A level's pictures stay warm through a visit to a menu.** A picture that was asked
  for and whose texture is then not drawn with (a menu is up, the camera has turned
  away) stays wanted: it is read after those that are on the screen and handed to the
  graphics card at the end of a frame, with the room that frame's own draws left
  (`tex_warmed` of `info`), so that it is there when its texture is drawn again. It is
  given up — taken out of the readers' queue, what was read of it let go, asked for
  again when the texture is next drawn (`tex_abandoned`) — only when it has not been
  drawn with for 30 seconds, when more than 768 such pictures wait (the longest unused
  go), or after two seconds while the pictures held are within a tenth of what they may
  take. (First such a picture stayed counted in `tex_pending` for ever and its unpacked
  pixels, 7 MB for a 4× level picture, stayed in memory for ever — 541 of them after
  five levels gone through fast — and a count that was not 0 made every frame start
  from an invalid render state. Then every one was given up after two seconds, which
  threw a level's pictures away whenever a menu was opened while they were coming in.)
  The two-second rule was checked with the camera at a new
  place every 20 frames through 40 places of `blood1`, `strife`, `islc1`, `fire1`,
  `shame1`): the count at the end of each level was 7, 12, 28, 34, 563 and stayed;
  it is now 1, 0, 0, 0, 3 and 0 five seconds later; in the first level afterwards 60.00
  frames a second with the pack on and off (15.1 and 15.5 ms of the video thread per
  frame, load 41–46).
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
| interface | sprites under the scanline mask, or blended sprites (`ALPHA` 0x44) | two-field pictures (those with `field0_uv`/`field1_uv`) are interleaved, enlarged as the one picture they are and laid out as described above; `realesrgan-x4plus` only where it shows what the game shows, the rest by a filter that draws nothing of its own ("Interface art keeps its shapes", below) |
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
- **A texel's colour is only replaced when no way of drawing shows it, and then only
  near the edge.** A texel counts as hidden only if *every* state in the `.json` file
  hides it; a file that does not come from seeing the picture drawn (`"source": "disc"`,
  written by `disctex.py`) or that has `states_overflow` hides nothing at all; and even
  where texels are hidden, colour is replaced only within 3 texels of visible ones (as
  far as an enlarging filter reaches) — further in they keep their own colour. So if a
  `.json` file is ever wrong or incomplete, a rim can be lost, never the thing itself;
  the price where nothing is known is a slightly darker edge on cut-outs.
- **Self-check.** Every finished picture is made small again and compared with the
  game's texels: where the colour, taken over about a texel either way, has moved by
  more than 16 of 255 among texels the game shows, the run prints `LOOK AT <name>`
  (sharpening does not count, a painted-over patch does: an eye of 12 × 14 texels
  painted over with skin gives 253 texels, largest move 153). It also says in how many
  pictures and texels colour was replaced on purpose. `upscale.py DUMP REPLACE --check`
  does the same for the files of a pack as they are, without enlarging anything (exit
  status 1 when something is to be looked at); `REPLACE/upscale-check.json` keeps the
  figures of every picture made.
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
  interface are 6 or 8 lines high; the model made a maze of their mottled fill). **So
  are model textures of fewer than 2,048 texels** (16 × 16 to 32 × 48: item pictures,
  small hair and ornament pieces — 220 of the disc's 1,447). Every feature in them is a
  texel or two wide; the model drew confident other shapes from them (a rune became a
  different rune, a mottled pouch a flat one) and moved their colour. From 48 × 48 on it
  follows what is there. **And so are interface pictures of fewer than 2,048 texels**
  (`FEWEST` in `upscale.py`: the 32 × 32 skill icons of the ability ring, the coin, the
  scales, the socket, the pointer, the corners of the notice box, the skill tree's
  pipes — 83 of the first 310 interface pictures enlarged). At full strength they came
  out redrawn, not sharper: the head on the coin became scribble, a hand got other
  fingers, masks other faces, a frame black bars, the pipes a dark blue rim; the
  self-check does not see that (colour averaged over a texel stays where it was: 0
  pictures named before and after). Enlarged plainly they are soft and keep every shape.
  A two-field picture is counted as the one picture its fields make (a 64 × 32 file with
  fields of 15 lines is 64 × 30), in the rule and in the manifest's note `plain`, so a
  pack made before the rule has exactly these pictures done again by the next run
  (pictures that were plain already for their short side are written again unchanged).
  Before and after, both packs: `local/hd-work/interface-redo/sheet-4x.png`,
  `sheet-2x.png`. Not every model result was wrong (the shield, the scales, the crossed
  swords, the gem and the pointer were faithful and crisper), so choosing per picture
  was tried: 37 figures of the model's result against the game's picture and the plain
  one — made small again and compared texel by texel, structure (local correlation),
  edges that do not run along the plain picture's, total variation, detail inside
  texels, colour and darkness of the rim, change of chroma, and how far the model's
  answers differ when the picture is given to it mirrored, upside down and turned.
  None tells the redrawn ones from the faithful ones: of 47 pictures judged by eye (30
  redrawn, 17 faithful) the best single figure sorts 13 wrongly (calling all of them
  redrawn: 17), and the best of 400 pairs of figures still puts a redrawn picture
  before a faithful one in a quarter of the cases. A coin's head turned into scribble agrees with the game's texels as well as a
  sharpened shield does. So the rule stays plain for all
  (`local/hd-work/interface-redo/sheet-measure.png`, `calib*.py`).
- **Interface art keeps its shapes.** The model redraws whatever is a texel or two wide,
  in large pictures too: on the 48 × 44 icons (2,112 texels, just over the rule above) a
  face became another face and an axe a blot; on the skill-tree pages a branch lost its
  tines and a skull its teeth; a brooch's knotwork turned into rune-like marks; the bars'
  frame and the bag's tab bar came out with thinner lines and a bright rim. So for
  interface pictures (`agree` in their recipe) the model's picture is taken only where,
  made small again, it is the game's texels — fully where the largest difference in a
  texel's surroundings is under 6 of 255, not at all over 18 — and everything else is
  enlarged by `edged`: the plain enlargement smoothed along its edges (the direction is
  that of the picture's own gradients) and made steeper across them inside the range of
  the texels around, so that no pixel can leave that range: no halo, no ringing, no
  stroke the game has not; noise stays plain. The interface pictures of fewer than 2,048
  texels, which never see the model, are enlarged by `edged` too instead of plainly
  (sharper, the same shapes); a side under 12 stays plain. Paintings (loading screens,
  the shop's niche), frames and item pictures keep the model nearly everywhere. **The
  two pages of letters are left out of this** (`LETTERS`, known by their texels): glyph
  by glyph the model's letters are the game's, heavier, without ringing on the sheet or
  in the game — it makes a thin grey stroke a solid one, which the rule takes for
  redrawing, and letters crisp in patches are worse than either. What was tried and
  dropped: the model at 0.3 and 0.5 (half-redrawn faces), fitting the result back to the
  texels (shows the texel grid), counting the difference against the local range (lets
  the redrawn faces through again). `VERSION` is unchanged: the recipe is part of each
  picture's signature, so a run does the 405 interface pictures again and nothing else.
- **Texels never sent are filled from their neighbours and stay filled**; a border of 8
  texels is given to the model around what it enlarges (the picture's own texels where
  the rectangle lies inside it; repeated edge otherwise; wrapped round where `other_uv`
  shows that the texture repeats and the dump is the whole of it — no such texture
  occurs from power-on to the first level, where every level texture is a page with a
  margin of its own, so that case is untested).

What was looked at to choose (same frame with and without, `texreplace` with the game
paused, pictures `local/play-out/hd2-*.png`; a screen that cannot be paused, like
character creation, is taken one whole turn of its idle animation apart, 240 frames —
the character there shuts its eyes three times in those 4 seconds, for up to 8 frames,
with the game's own textures as with any others, and a picture taken then shows it
without eyes): `realesrgan-x4plus-anime` flattens every
surface with grain (stone, parchment, the bars) into flat colour and was dropped;
`realesr-animevideov3` and Lanczos both ring on noise; blurring the texture before the
model turns grass into lichen; enlarging a Lanczos-doubled picture and halving the result
gave a checkered pattern. What came out better than the game's art by eye: the title's logo, all text, the
frames and icons of menus, bars and inventory, stone, leaves, the character's skin and
armour close up. Grass is about as before. Looked at for the whole game (pairs of the
game's texture and the enlarged one, 40 model textures and 100 level textures of 15
levels taken at random, and every picture the self-check named): rock, masonry, wood,
metal, cloth, faces and hair follow the game's art, the dither of its 8-bit palettes
goes. One thing is not right and not caught by the noise rule: a surface that is fine,
low-contrast grain all over (the sea floor of the `wat` levels) gets faint flowing lines
from the model; its figures (2.6 to 2.7 where rock has 2.4 to 2.9) do not tell it from
rock, so the cure would be a lower strength for all level textures.

Measured on an M5 Pro, other test runs going on beside (load average 10 to 16; for the
whole game 10 to 130):

| | |
|---|---|
| time to enlarge | 394 pictures 4 min 20 s; 25 new ones in a later run 20 s. The whole game: 1.5 to 2 pictures a second with four batches at a time, the graphics card shared with other work — 120,000 pictures take most of a day |
| the pack for title, menus, character creation and the first level | 418 files, 257 MB (4×); 72 MB (2×) |
| the pack for the whole game | 120,039 pictures dumped (118,257 level textures, 1,479 model textures — the disc's 1,447 and what the character is put together from —, 288 interface pictures, 15 others), 6.8 GB. A 4× picture is 0.8 MB on average, a 2× one 0.24 MB: about 95 GB and 29 GB |
| video memory in the first level | the game's own 335 textures 16 MB; 4× replacements 1.39 GB (310 pictures, mip maps included; 1.46 GB with the inventory's); 2× 350 MB |
| video memory in the heaviest level (`shame1`: 1,089 pictures, 606 of them in the nine texture cells round one place) at 4×, whole pictures handed to the graphics card (all there was before; `--rta-texture-whole` now) | with every replacement of the level kept (`--rta-texture-memory 40000`, the camera over every place once) 11.0 GB for 1,061 pictures (9.4 GB for the 992 there were when it was first measured). With the default 3,072 MB the application gives up what was not drawn for ten seconds and reads it again when needed: going through the level at a new place every second the most held at one time was 4.0 GB, 1,208 given up on the way |
| the same with only the part that is drawn with (the default now, see "Texture dump and replacement") | 70 % of the level's pages is texels nobody draws with: its 1,051 dumps hold 127.8 million texels, the rectangles the game draws with 37.9 million. Everything kept: **3.4 GB** for the same 1,061 pictures, 743 of them as parts. Default budget: the most held at one time 3.2 GB, 664 given up |
| speed and loading there, whole against part (the camera at a new place every second over the level's 109 places, 6,431 presented pictures a crossing; the enlarging paused, load average 16 to 33, one or two other test instances at 1× beside) | everything kept: 59.8 and 60.0 frames a second while it loads, 59.9 and 59.9 with all of it loaded; the video thread's own processor time 7.0–7.2 and 6.7–6.8 ms a frame; 99 % of the gaps between pictures under 26.4 and 22.8 ms, the longest 52 and 50 ms. Default budget: 59.8 and 59.9 frames a second; gaps over 25 ms 196 and 89, over 50 ms 6 and 1 (the longest 100 and 164 ms); places still reading a second after the camera came 48 and 6 of 109. Standing: 60.0 either way. The same paused frame drawn from parts and from whole pictures differs no more than two takes of one setting do (mean difference 0.33, 0.03 and 0.00 of 255 at three places, the same figures part against part) |
| speed with the pack, standing and walking through the level | 60.00 frames a second at 4× and at 2×, as without |
| speed with the 4× pack in three other levels (`blood1`, `innovat1`, `shame1`; load average 9 to 31) | standing and walking 60.00 frames a second, the same seconds later with the pack switched off (`texreplace 0`); with the camera at a new place of the level every second 59.84 to 60.00 (the game drew 56.6 to 59.2 pictures a second). An earlier run with the load average at 80 to 130 and the enlarging going on on the same graphics card gave 41 to 60, lowest where the load was highest; that one was not repeated with the pack off |

For a computer with little memory make the pack with `--scale 2` (a quarter of the
memory: the heaviest level was 2.4 GB with whole pictures, before only the part drawn
with was handed over; text and frames are still clean, see
`local/play-out/hd2-pack2x-vs-4x.png`), or lower `--rta-texture-memory`.

**Growing the pack.** A dump holds what a run has drawn. Three ways to more:

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
  pixel for pixel). Model textures get a `.json` file saying that they are model
  textures and are enlarged at once — with nothing in them treated as hidden, since
  nobody has seen them drawn; for the others (interface art, effects) the file does not say
  how they are drawn, and `upscale.py` leaves them until a run has drawn them. **Level
  textures cannot be named from the disc**: `<LEVEL>.TEX` holds them packed (header
  flags 0x010c, no upload packet, a table of offsets) and the game unpacks them before
  sending; the unpacker was not rewritten. Neither can the player's own character (put
  together from parts when the game starts) and the two font pages.
- **A tour of every level** for the level textures. They are the bulk of the game's art:
  the 111 `<LEVEL>.TEX` files hold 157,820 textures, one per piece of ground and wall;
  25,540 of them are one flat tile of 6 × 6 to 12 × 12 texels again and again, 132,280
  are pictures. A texture is dumped when it is drawn, so the camera has to pass over
  every piece. `tools/play-net/leveltour.py --disc IMAGE --out DIR` does it (and
  `--merge DUMP_DIR` afterwards):
  - the level is asked for as the game's own level changes do, by writing its name to
    `g_pendingLevel` (`poke 0x41b6d0 str <name>`, `docs/mainloop.md` section 7); a medal
    round's notice box is answered with the confirm button;
  - where to look comes from the level's `.world` (`docs/formats/world.md`): the bounds
    of its chunks, sorted into squares of 345 units, one stop per square that holds
    anything, in rows there and back;
  - the camera is the game's own free camera: mode 3 (camera object `[0x4f8450]` +0x34)
    stays where its position is written (`0x44f038`, three floats), so it is put above
    each stop as the following camera would be (98, −98, 370 from the place, 1.3 times
    that; yaw and pitch word +0x68 = 0x2efbe000) while the character stands at the
    level's start: no trigger, no dialog and no way out of the level is touched. (Moving
    the character instead — its position at object +0x10, held against falling — works
    too and was used for the first half; it walks into level exits and conversations.)
    Each stop is held until the application has written no new picture for 40 frames;
  - the instances run without the frame limiter (`throttle 0`) at resolution factor 1,
    three at a time, each with its own `--rta-textures` folder; the folders are joined
    into the pack's dump afterwards (`.json` files united: every way of drawing, the
    largest rectangles).
  A level of 2,000 pictures takes three to six minutes. How complete it is was checked
  on three levels by going over them again more densely (squares of 165 units instead
  of 414: 3 more pictures of 1,787), with the camera turned round (none) and with the
  other way of moving (1,925 against 1,918 of 2,014): what a level's file holds beyond
  what a tour finds — 2 to 6 % of the pictures in most levels, up to 40 % in arenas and
  island levels — are pieces that hold the same picture as another (107 sea-floor tiles
  of one size, 64 different ones) or are never drawn. 58 levels were gone over a second
  time with the free camera after the character: 0 to 5 new pictures each. In all:
  118,257 different level pictures of the 132,280.
- Also toured, once: every class and every position of every appearance slider of
  character creation (the character's own textures), the shop's lists, the pages of the
  bag, the pause menu and its options, the save screen, and the mission menu with every
  mission unlocked (the flags at player record +0x4bbf, `docs/player.md`).

`upscale.py --jobs N` works on N batches at a time, `--names FILE` on the pictures named
in a file (a level at a time, in the game's order, so that a run cut short leaves whole
levels), and a run that is stopped keeps what it has written. **What limits it is the
graphics card**: the model takes about a third of a second for a level picture (the 150 ×
150 texels the game draws with, with their margin) on an M5 Pro with nothing else on its
graphics card, so the game's 130,000 need half a day; the work around the model is
0.2 seconds of one core. **The 2× pack is made from the 4× pack**: `upscale.py DUMP
PACK2X/replace --scale 2 --from-pack PACK4X/replace` halves each picture (two-field
pictures come out right, their second copy being two lines up at 4×, one at 2×). Against
`--scale 2` done with the model: mean difference 0.37 of 255 on 15 model textures, 0.25 on
86 interface pictures; a plain `--scale 2` run takes such pictures as done.

**Effects, skills and what else is only drawn in play.** The game's effect art is small:
of the disc's 628 pictures that are not model textures (`disctex.py DISC --kinds other
--list` names them with their lumps) nine are in `FX.LMP` and five in `ENGINE.LMP` —
halos, one sheet of particles (512 × 160: sparks, bubbles, puffs, stars), a floor sprite,
the shadow blob, the trail, a spider web. Spells are particles from that sheet, halos,
trails and models (whose textures are all in the pack from the disc), so "12 effect
pictures were seen in all" was nearly all there is: 11 of the 14 have been drawn now
(ten were in the pack, `halo3` is new; a twelfth, the trail, is known by another name
because it is only drawn clamped; `halo5` and `bordersmall` were never drawn). What the first tours lacked is interface art that
only shows with a character who has the skills: 87 skill icons, a skill-tree page and
its pipes per class, the ring of abilities. Toured for it (local helpers, results in the
pack's notes): a character of each of the seven classes with every skill of its class
at rank 10 on the ability records (the rig's recipe: `tools/rig/sweep.py`), the bag's
pages, the level-up page (statistics and skill tree; it opens with a level gained and
not yet looked at: record +0x58 below +0x59), the shop, the ring all the way round,
and every skill cast among the arena's opponents (`drunare`) — 89 skills on the
buttons, 71 of them not passive, 45 cast for certain (the recast counter moved); bow
skills want a bow drawn, others a target or a weapon of their kind. Then a few blows
beside sixteen things each of twelve levels with the character unhurtable (what monsters
cast and throw, what dies), and `fire3` whole. In all 10,908 pictures drawn, 2,171 of
them new to the pack: 1,923 level pictures of `fire3`, about 150 of the other levels,
38 skill icons, 27 pictures of the skill-tree pages, the spell ring (6), one halo. The
tours add no way of drawing that changes what an effect picture is taken for (the
particle sheet is drawn blended and added: kind sprite; the halos added: glow).

**Light that is added stays dark where it was dark.** The effect pictures are white or
coloured all over and carry their shape in alpha (`ALPHA` 0x48 adds colour × alpha,
0x44 mixes by alpha), so "black" there is alpha 0. For the seven that are in the 4× pack
(`floorsprite`, `halo1`, `particletex`, `halo2`, `halo4`, `halo7`, `wisphalo`): where
the game's picture adds nothing — a texel and all its neighbours — the enlarged one adds
at most 0.4 of 255 (the floor decal 19, in 0.05 % of such texels, at the edge of its
blots), and the light a picture adds in all is the same to 0.3 of 255. Pairs were looked
at (what each adds to black, the game's beside the enlarged one): the same shapes,
smoother, no box, no rim. The recipe was left as it is.

Not tried: other models (none may be fetched here; `4x-UltraSharp` and
`4x_foolhardy_Remacri`, ESRGAN models of about 65 MB each listed on openmodeldb.info and
made for textures rather than photographs, would be the first to try on stone and
ground — from memory, not checked, and they need converting to ncnn's format);
anisotropic filtering. Not covered: about a sixth of `fire3`'s 3,655 pictures (3,079
were drawn, and part of the rest never is, as in other levels; it could not be toured
past its first quarter until the emulator fault in the table at the top was found); the medal and bonus entries of the mission
menu (the hub's script opens the menu from a detector the player walks into,
`warnDetect` in its script; neither standing on or using any of the hub's ten objects
nor standing on each of 55 pieces of its ground opened it, and where the detector is
was not read out of the level's data); 48 of the 87 pictures of `ICONS.LMP` (skill
icons) and 63 of the 131 of `INVENTRY.LMP` (skill-tree pages and pipes among them: an
icon shows when its skill is in the ring or on the page that is open, and the tour
went round both blindly); 26 of the 71 active skills not cast; the six
busts of things aimed at that the first act shows (`bust_catapult`, `bust_scout` …),
the twelve head pictures (two players), the map icons, the boss meter; items that are
not in the first shop; the films; of the title's level only what the title shows. The
pictures new since the first tours are not enlarged yet: they are handed to the
enlarging loop, which was paused when this was written.

## One-step online

`src/RtaOnline.{h,cpp}`; the user's side of it is `docs/play-online.md` section 4.

**What it does.** `--rta-online` (play.sh: `--online`; the packaged application: at every
start unless *Online → Go online at start* is off; at any time: *Online → Play Online*)
makes the application press its own way from power-on to the lobby's game list: the
memory-card questions and logos, *Start New Game*, *Internet Game*, the network setting,
the server's terms, the log-in. It runs on the machine's thread at every vertical blank,
before the pad is handed to the game.

**How it knows where the game is.** By the game's own state, read from its memory at
every frame; never by the clock alone. A press is made only when the screen it belongs to
has been identified and has stood still for some frames; it is held 8 to 10 frames (the
lobby screens drop shorter ones, `docs/issues/live-rig.md` 19.3), and the state is looked
at again before the next. What is read (addresses for SLUS-20973 v2.00; the application
does nothing unless the executable's checksum is that version's):

| What | Where | Values used |
|---|---|---|
| front end up | `g_inFrontend` 0x41b510, `g_levelName` 0x41b721 | 1 and `intro` |
| which menu | `g_frontendState` 0x4f6b78 | 0 main menu, 1 normal / internet game, 10 the lobby |
| the menu's entries and cursor | table at `g_frontendMenu` 0x4f6b7c: 16 bytes an entry, the name's address first (`menu_startnewgame`, `menu_netgame`); the entry after the last holds the cursor in its second word | found by name, not by position |
| menu takes input | float at 0x4d8a10 | 1.0 |
| which lobby screen | `g_lobbyState` 0x506160 | 2 network setting, 4 log-in, 3 account, 5 game list |
| network window (pointer at 0x506148) | +0xdb4 state, +0x4354 settings found, +0xd88 message box | state 3 the list of settings, 1 "already up", 7 signed in: each goes on with cross |
| log-in window (0x50614c) | +0x165c state, +0x115c terms box, +0x1148 message box | 1 with the terms box: cross accepts; 2 the form; 4 sent; 6 refused; 8 to the account form; 9 to the list |
| account window (0x506150) | +0x229c state, +0x2288 message box, +0x22b0 request under way | 0 the form; 2 sent; 3 refused (box); 4, 5 made |
| game list window (0x506144) | +0xc248 next state, +0xc244 request under way | both 0 for 30 frames: arrived |
| on-screen keyboard (0x5071f4) | +0x14 | 1 while open (then nothing is sent) |

**The two forms are filled by writing the game's text fields**, not by walking its
on-screen keyboard: a text field (class vtable 0x51cdd0 at +0x48) keeps what it shows at
+0x52 and its value at +0x2ca (16-bit characters), its limit at +0x2c9 and its "stars"
flag at +0x44c. Before anything is written the field's class, its limit and its flag are
checked against what is expected; after writing, at a later frame, every field is read
back, and only then is the form sent with cross. The log-in form's two fields take 15
characters each; the account form has six fields (name 15, password twice 15, e-mail 79,
date of birth 11, chat handle 15). "Save Login/Password?" on the game's log-in form is
set to "No": the pair is kept by the application instead.

**The account.** A player name is asked for once (`Rta::AskPlayerName`: a sheet on the
main window, so that no other window of ours can lie round it or behind it; it has no
time limit and ends only with *Go online*, *Not now* or the application - Escape does
not end it; the log says how it ended; `docs/issues/mac-app-start.md`, "The name
dialog"): 3 to
15 letters and digits - the game's name fields take 15, the server refuses a chat handle
longer than 15 and its own rule for a name is 3 to 20. The application makes the account
in the game's Create New Account form with: login = the name, a password of 14 random
characters from a-z and 0-9 (`std::random_device`), e-mail `<name>@example.invalid`,
date of birth 01/01/1980, chat handle = the name. When the server refuses (the game's
box; it gives no reason, a taken name is the usual one) the box is closed and another
name is asked for.

**The saved login**: `<data directory>/online-login`, mode 0600, one line per server
(the server's address as given; `this-computer` for a server on the same Mac): server,
name, password, `ok` or `pending`, separated by tabs. It is written, as `pending`,
before the account form is sent, so that an application that ends between the server's
making the account and its answer still has the pair; `pending` becomes `ok` when the
game list is reached. A `pending` pair that the server does not know is dropped at the
next start and a name is asked for. The password is never written to the log, the status
bar or the control socket, and neither is the name. *Online → Forget online login*
(control socket: `online forget`) deletes the line.

**When it stops.** A message box it does not expect, a menu it does not know, a screen
that was passed coming back (a lost connection), a saved login the server refuses, six
presses that a form does not answer, nothing changing for 20 seconds (90 for the start
up to the title screen): it lets go of the pad, writes "online: STOPPED - why" to
`rta.log`, shows "Going online stopped: why. The controls are yours." in the status bar,
and does nothing more. While it runs, and only then, the game is given its buttons alone
(`CPadHandlerRta::Override`): keyboard, controller and control-socket presses are left
out and the sticks are at rest.

**The Controls help** (*Help → Controls…*) comes by itself once per data directory - not
at the start, where it opened round the question for the name and dead under it, but when
the game has run some seconds, nothing of ours is asking and the one-step sign-in is over.

**Test aids.** `--rta-test-dialogs now|released` shows our own windows in a test run
(behind the others, never active; `released`: built and opened as the release of
2026-10-13 morning did), and the control socket's `ui` commands read and work them
("Control socket and tests"). Without it a background test run (`--rta-test`) can show a
dialog to nobody, so:
`--rta-online-name NAME[,NAME...]` gives the player names to use (the next one when the
server refuses one), and `online name NAME` on the control socket answers when the
application is waiting for one (it gives up after two minutes). `online` reports the
stage and the outcome; `online start [lobby|host[:CODE]|join:CODE]`, `online stop`, `online forget` do what
the menu entries do; `uishot playername|playername2|gamecode FILE` draws the new windows
to a picture. `--rta-gateway-port N` makes this computer look for the server's gateway at
TCP port N instead of 40810: a closed port stands for a server that is not there.
`--rta-no-online` keeps the packaged application from going online at one start.

**Measured** (M5 Pro, lobby server on the same Mac, background test instances, fresh
data directories, player names made by the test): first start, account made, game list
reached 30.4 s after launch (machine frame 1666: 11 s to the title screen's menu, 4 s
for the title to take input, 4 s of network set-up, 4 s for the lobby's first answer,
then terms, account and list in 4 s); second start with the saved pair 28.3 s; a first
start whose first name was taken, second name accepted, 32.0 s; with the gateway at a
closed port it stopped 20 s after the game began to say "Connecting" and left the game
there.

**Games by code** (`--rta-online host`, `--rta-online join:CODE`; play.sh `--host`,
`--join CODE`; *Online → Host a game*, *Join a game...*). The same machine, going on from
the game list:

| What | Where | Used for |
|---|---|---|
| the pane that has the pad | list window +0xc258 | must be the list of games (+0x31c), or the form's name field |
| "Host / Search" box | list window +0xc244 (a box), +0xc24c = 1 | cross there is *Host Game* |
| the form for a new game | +0xc24c = 2, name field at the pointer +0xc210 (an ordinary text field, 15 characters; the game refuses fewer than 4) | the code is written there, read back, sent with cross |
| the list of games | lobby client (pointer at list window +0x314): count at +0x60 (u16), array at +0x98, 0xb8 bytes a game, name at +0x22 (16-bit characters), highlighted game at list window +0xc249 | the code is looked for at every frame; the cursor is walked to it; cross joins |
| request out / let in | client +0x64, bits 0x10 and 0x20 | cross is pressed again until the first is seen |
| character screens | `g_lobbyState` 8 to 11; 0x4fbbe2 = 1 when a character was chosen | the character used last is taken by itself (below); otherwise the player's own: the pad is theirs while they are up, and there is no time limit |
| a game's room | `g_lobbyState` 6, window at 0x506140 | arrived |

A host: triangle, cross, the character screens (the character used last, or the player),
the form (name = the code, everything else as the form has it), the room. The code is four letters out of 24 (no I,
no O), made with `std::random_device`; it is the game's name on the server and no secret.
A joiner: the list is watched until a game of that name is in it (two minutes at most),
then cross on it, the character screens, the room. A box that stays after the form was
sent, the character screens left without a character, the pad in a chat pane: it stops
as above. *Not done*: asking for difficulty or game type (the form's own are taken).

**The character used last.** "Host" and "Join" always open the game's new-character
screens; stored characters are behind triangle ("Import") on the first of them, in one
list for those the server keeps ("RTA Net") and those on a memory card. What is read
(`playerSel_task` 0x225478, `memcard_importScreen` 0x21fa2c):

| What | Where | Values |
|---|---|---|
| page of the character screens | 0x8e2c02 (u8) | 1 race and class, 2 appearance, 3 ability points, 4 name, 5 done, 8 the sheet of an imported character |
| card screen | `g_memcardState` 0x88d3a0, its own state 0x88d3a8 | 9 is "Import Character"; there 1 the list takes the pad, 0xd to 0xf the entry is fetched, 0x13 / 0x14 an error |
| the list | pointer at 0x4f8ee4, 0xf4 bytes an entry, count 0x4f9230, cursor 0x8e1b43 (u8) | entry +2 kind (2: kept by the server), +0x48 the server's number, +0x4c name, +0x9c class, +0xa5 level |
| the character in use | `g_players` 0x4d8af0, record 0 while the lobby screens are up | name first, class at +0x50 |

When a character has been chosen (0x4fbbe2 = 1) its name, class and - if it came from the
list - the server's number are written to `<data directory>/online-character`, one line
per server (the key of `online-login`). The next Host or Join finds that line and does
the screens itself: triangle on page 1, waits for the list, looks for the entry (by the
server's number while it still has that name; else by name and class, the server's
before a memory card's; two that fit are left to the player), walks the cursor to it,
cross, waits for the sheet (page 8), cross. The player's own buttons are not passed on
meanwhile, and **any button the player holds** (keyboard, controller, a test script)
before the entry is taken hands the screens over, as do `+choose` after the mode
(`host+choose`, `join:CODE+choose`; the tick in the Host and Join windows; `play.sh
--choose-character`), an entry that is not there, a sheet or page that was not asked
for, an error or question of the game on the list, or 40 s without getting there. A
character's name appears in the status bar and, where it explains a hand-over, in
`rta.log`; unlike the login it is no secret. `uishot host|join FILE` draws the two
windows.

**Which patch set the other players have** (`RtaNet.cpp`, `CheckPatchSets` in
`Rta.cpp`). Looked at for a carrier: the chat line (a player's copy would have to drive
the chat keyboard, and the text lands in everybody's chat pane); the game's name (only
host to joiner, and it changes the code people type); what the server stores for a game
(the game sends an empty attribute list and blob with its create request: filling them
means changing a request the server parses). None is used. The copies tell each other
directly, on the path the game has opened between them: to every address another
player's datagram arrives from, the relay sends - from the same socket, four times in
nine seconds - a keep-alive of the game's own UDP library (bytes 0, 6) followed by the
mark `RTAset1`, the set's figure and its word count, 15 bytes in all. That library does
nothing with a type 6 packet of any length (dispatch 0x392354: types 4, 6, 0x1c and
0x1e share one empty case), so a copy that does not know the mark hands a keep-alive to
its game; a copy that does takes the datagram out before the machine sees it. Nothing
goes to the lobby server and nothing reaches the simulation. A different figure from a
player heard within the last 15 s: a line in `rta.log`, "WARNING: another player has a
DIFFERENT PATCH SET (…; yours …)" in the status bar, and once per player and figure a
window that does not stop the game. A player heard for 12 s that has said nothing: "does
not say which patch set". `peers` on the control socket lists them; `--rta-set-quiet`
(say nothing) and `--rta-set-raw` (hand the datagrams on to the game as well) stand for
an older copy in tests. Not done: a warning before joining (the figure is only known
once the two machines talk, that is in the room), more than two players, and anything
between two networks.

**Which arithmetic the other players compute with** (`RtaNet.cpp`, `CheckArithmetic` in
`Rta.cpp`; `docs/issues/mixed-arithmetic.md`). A browser copy's machine rounds
floating-point results to nearest, this application's toward zero; the application's core
can do either (`FpUtils::SetArithmetic`). The copies say what they can do and what they
do in a second datagram of the same kind, at the same times and again whenever it
changes: bytes 0, 6, the mark `RTAari1`, one byte "can do" (bit 0 Play!'s own, bit 1 the
browser's), one byte "does now", 11 bytes. In the game's front end the application
changes to browser arithmetic while a player is heard who cannot do Play!'s own or
already does the browser's, and back when nobody needs it - but not while it is in a
game's room: there it stays on browser arithmetic although the player it was needed for
is silent for the moment (a silence is not a departure), unless a copy heard there cannot
compute that way, and goes back when it has left the room. In a running level it changes
nothing and warns. The status bar says "browser arithmetic" while it is on and warns
about a copy that cannot follow (a copy that says nothing is taken for one that can only
do Play!'s own); `peers` lists each player's arithmetic; `--rta-arith browser|native|auto`
fixes it. Compiled for the application and for the browser build. Tried between two
copies of the application through the lobby server on the same Mac (2026-10-12; the
browser build itself was not part of it): the host started with `--rta-arith browser`,
the joiner left at `auto`. The joiner heard "computes with browser arithmetic (can do:
the browser's)", changed one second later in the room ("arithmetic: the machine now
computes as a browser copy's does", `rta.log`), `peers` said `arith=browser` for both
players on both copies, and the game ran in step: 506 and 436 lockstep frames in the
first level and 500 after a level change, every sync hash the same on both, hit points
`42033333` (the value to nearest) on both.

**Measured with remembered characters** (two background test copies on one Mac, load
average 60 to 140 from other work; each copy had used its character once before): host
in its room 43 s after launch, joiner 53 s after its own, no press by anybody; *Start
Game* by the test; 6 s later both in the first level, lockstep frames 247 / 250 / 256,
396 / 402 / 406, 552 / 557 / 565 (host, joiner, host again), shared seed and both
players' hit points the same on both, checksum flag 0. The room was reached this way
three times (host 43 s each time, joiner 50 to 61 s) and the game started twice, the
second time with the patch-set datagrams also handed to both games (`--rta-set-raw`):
in step again (259 / 260 / 270, 400 / 402 / 410, 534 / 545 / 552). With one
section taken out of the joiner's list: both copies had the other's figure 1 s after
the first datagram between them and showed the warning; the room stayed up.

**Measured, two background test copies on one Mac**: host started with `--host`: at the
character screens 28.6 s after launch, in its room 3 s after the test had made a
character there (the test's presses, each checked by the screens' page number at
0x8e2c02); joiner started with `--join CODE`: at the character screens 28.8 s after
launch (logged in, found the game in the list, joined it), in the room after its
character; the host's *Start Game* by the test; 4 to 6 s later both in the first level,
lobby state 12, at simulated frames 234 / 234, 433 / 447, 643 / 653 when sampled one
after the other, shared seed and both players' hit points the same on both, checksum
flag (`g_checksumFailed`) 0. Run twice. A code that no game has: stopped two minutes
after the list came up.

## The network screen's "Config", and a game that has stopped

**"Config" (triangle) on "Network Configuration and Selection".** The game stops its
network worker and restarts the machine into Sony's network settings program on the disc
(`LoadExecPS2` of `NTGUI2.ELF`, from `FUN_00332490`); leaving that program restarts the
game. In this build the program does run: it draws (a few letters of its text are
missing), takes the pad, its connection test succeeds against the built-in network, and
*Back → Quit* lands at the game's title again (55 to 57 machine frames a second with a
load average of 15 to 60, background test copies). But there is nothing to set in it -
the setting on the memory card is the application's own and the network behind the
adaptor is made up - and it throws a player out of the session. So the button is **not
passed on** while that screen lists a setting or is still reading the card (`WatchGame`
in `Rta.cpp`: front-end state 10, lobby state 2, network window state 0 or 3): the game
stays where it is and the status bar says "The network is already set up: press cross
(Accept)…". `--rta-netcnf-program` passes it on.

**A freeze on that screen that was found.** A copy without the sign-in patch gets
"Network Error (-611) … Please check your network configuration" after *Accept*.
Cancelling it (circle) leaves the game drawing nothing for ever, the machine still
running: the screen's shutdown calls the shutdown of Sony's ERX loader (`FUN_0039ccf0`),
whose module-stop call (`FUN_003a4710`) does not give back the driver's id on Play!; the
game prints "liberx: PANIC!! ELOADP driver unload failure" and stays in an endless loop
of its own (0x39ce18). With the sign-in patch the sign-in modules are never loaded and
that shutdown has nothing to do. (A freeze from "Config" itself was not reproduced.)

**What the application does about a stop of any kind.**

- It watches that the machine draws (the renderer's counts of transfers and textured
  draws). Nothing drawn for 600 frames - 180 while the game is leaving the lobby screens,
  where the case above sits - and the status bar says "The game is stuck: … Press Escape
  (or choose Reset in the menu) to start it again"; `rta.log` gets the front-end and lobby
  states and the processor's pc and ra. The longest stretch without drawing in ordinary
  use was 141 frames (power-on). On the error screen itself the status bar says that the
  sign-in step failed and whether this copy has a sign-in patch.
- **Escape** outside full screen starts the game again when it is known to be stuck (in
  full screen it leaves full screen, as before). **Reset** in the menu also drops the
  relayed TCP connections and ends the one-step automation.
- The machine's own thread (`MachineAnswers`): when no vertical blank comes for 2.5 s
  while the machine is running, Reset, Escape and closing do not call anything that would
  wait for that thread (Play!'s Pause and Reset do, for ever). The status bar says "The
  emulated machine has stopped answering" after 5 s; Reset asks whether to end the
  application and start it again, and does; closing ends it at once.

Tested with background test copies: "Config" pressed three times and left out, then
*Accept* to the server's terms; with `--rta-netcnf-program` the program, and Reset from
inside it back to the title; without the sign-in patch the error, circle, "stuck" after
3 s, Escape, the title again; the machine's thread stopped by `hang 60`, Reset asked
through the `.ui` file, the application ended 3.9 s later. Not tested: the question and
the restart after it (a test run ends without asking), closing with the thread stopped,
a real key or menu click, anything with the window in front.

## Control socket and tests

`--rta-control <path>` makes the application listen on a UNIX socket; `ctl.py` sends
commands (press and release buttons, wait frames, read the game's memory, pictures of
what is presented, consecutive pictures with their times, the display state, thread
processor times, settings; `ctl.py --help` lists them). `smoke.py` uses it to go from
power-on to the lobby server's first screen and stops there. Pictures are game output:
they stay under `local/`.

- `shot FILE` is the window's picture; `shotfb FILE` is the picture as the machine drew
  it — 640 × 224 console pixels per field times the resolution factor, 2560 × 892 at 4×,
  twice as wide as high for a 4:3 screen — whatever the size of the window. `shotview
  FILE` is the part of that picture that is presented: without its outermost line and
  column (the fault table, "the edge"), 2536 × 884 at 4×.
- `drawlog FILE [frames [x0 y0 x1 y1]]` writes how the game draws, for finding out what
  a thing on the screen is made of: one line for every draw of the next `frames`
  pictures (1) with the kind of primitive, the number of vertices, the box drawn to, the
  texels used, the GS registers (`PRIM`, `ALPHA`, `TEST`, `FRAME`, `ZBUF`, `SCISSOR`,
  `SCANMSK`, `XYOFFSET`, `TEX0`, `TEX1`, `CLAMP`), the texture's address and size, its
  filter, whether a replacement is drawn and the start of the picture's name; with a
  rectangle, in pixels of the buffer drawn to (the game's draw buffer is 1280 × 448),
  every primitive that touches it is listed vertex by vertex. A `FLIP` line ends each
  picture. The four faults of the second visual pass were found with it.
- `upscale 0|1`, `edge 0|1`, `texcentre 0|1`, `texorder 0|1` switch four of the changes
  in the fault table off and on in the running game: the same paused frame before and
  after.
- `--rta-test "TEXT"` is for test runs on a computer somebody is using: the window is
  titled "AGENT TEST - TEXT", is small, is put behind the other windows, has no Dock icon
  and never takes the keyboard. Say in TEXT what is switched off.
- For telling faults apart in a running game, a second at a time: `displaypatch all|N 0|1`
  takes a display patch out or puts it back; `texmode 0|1|2` makes textures known by
  what was sent (0, the default), by the texels read back from video memory (1), or by
  address as Play! itself does (2; not usable after a switch, only from the start).
- `texcrop 0|1` hands the whole of every replacement to the graphics card, or (1, the
  default) the part that is drawn with; `texmemory MB` sets the video memory they may
  take. Both for measuring in one running game.
- `texreplace 0|1` switches the replacement pictures off or on in the running game
  (three frames later the picture is drawn the other way): with the game paused that is
  the same frame with and without. `texreplace reload` lists the folder again and reads
  every picture again, for trying a changed file without a restart.
- `hw` gives the registers that say what a machine that has stopped waits for: the
  interrupt controller's status and mask, the DMA controller with the VIF1 and GIF
  channels (`CHCR`, `MADR`, `QWC`, `TADR`), `VIF1_STAT`, `GIF_STAT`, the GS's `CSR` and
  `IMR`, the processor's status and `EPC`. (`peek` reads main memory only.) With the
  threads and semaphores the emulated kernel keeps in main memory (threads at 0x11000,
  0x38 bytes each; semaphores at 0xe000, 0x18 each) that was enough to find the stop in
  `fire3` (the table above).
- `ui …` reads and works our own windows on the application's own thread, for tests
  without a picture of the screen: `ui windows` (Qt's shown windows with modality and
  place, then AppKit's own list front to back with level, key and sheet), `ui main
  info|raise` (the main window, its page and the line across its top), `ui notice`, `ui
  name info|type TEXT|press ok|notnow|escape|close` (the question for the player name),
  `ui controls info|show|close` (with whether the window system has it blocked). The same
  lines written to `<control path>.ui` are answered in `<control path>.ui.out` by the
  application's own thread, so also before the machine runs or when it has stopped.
  `notice` gives what the window says about a folder it waits for; `texlist` whether the
  pack's folder has been listed and how many names it has.
- `cpu` says where the main processor is (pc, ra, sp, idle), whether the game is taken
  to be stuck and the longest stretch without drawing; `note` gives the status bar's
  note about the game; `reset` does what Reset in the menu does; `hang N` stops the
  machine's own thread for N seconds (a stand-in for an emulator that is stuck). The
  socket is answered by that thread, so for a machine that has stopped there is a file:
  `<control path>.ui` holding `reset`, `escape` or `close` is taken up by the
  application's own thread within a quarter of a second (any other line is a `ui`
  command, above).
- `info` counts, among other things: `tex_made` (textures made), `tex_by_upload` and
  `tex_by_memory` (draws that found their texture one way or the other),
  `tex_memory_read`, `tex_in_place`, `tex_short_lived`, `uploads`; `tex_held` and
  `tex_bytes` (the game's own textures and their video memory), `tex_replacements` and
  `tex_replacement_bytes` (replacement pictures held, mip maps included), `tex_pending`
  (asked for and not read yet: 0 before a picture is taken for comparing),
  `tex_dropped`, `tex_cropped` (held as the part that is drawn with), `tex_regrown`,
  `tex_abandoned`, `frame_copies` and `frame_copy_uses` (the heat haze's pieces of the
  frame buffer), `gs_buffer_drains` and `gs_buffer_most` (GS register writes between
  two vertical blanks: how often there were more than Play!'s buffer holds, and the
  most there were), `tex_warmed` (replacement pictures handed to the graphics card
  while their texture was not being drawn), `tex_pending_area`, `smoothed_draws` (draws
  of the last frame whose point-sampled texture was filtered) and `scaled_points`
  (points and lines of the last frame drawn a console pixel wide).
- `RTA_TEXLOG=FILE` in the environment writes a line for every texture made (frame,
  figure, format, size, address, pieces).
