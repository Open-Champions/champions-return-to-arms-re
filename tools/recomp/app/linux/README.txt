Champions: Return to Arms - native build for Linux (experimental, first test build)
==================================================================================

The game's own code translated to C++ and built for Linux (@ARCH@). It was built and run in
an Ubuntu 24.04 container on a Mac (under Xvfb, with Mesa's software OpenGL): it boots, plays,
and played one online game against the Mac build. Nobody has played it on a real Linux
desktop yet - you are the first. Nothing is installed; what it writes goes into the folder
"rta-data" beside it.

You need
  - Linux on @ARCH@ with glibc 2.39 or newer (Ubuntu 24.04, Debian 13, Fedora 40 or later)
  - SDL2 and OpenSSL 3:   Ubuntu/Debian: sudo apt install libsdl2-2.0-0 libssl3
                          Fedora:        sudo dnf install SDL2 openssl-libs
  - a graphics driver with OpenGL 4.1 core (Mesa 20 or newer: Intel, AMD; NVIDIA's own driver)
  - your own disc image (.iso) of Champions: Return to Arms, US version SLUS-20973 v2.00

Start
  ./play.sh "/path/to/your.iso"            (or  ./rta_app --disc "/path/to/your.iso")

Keys
  W A S D    left stick            arrows     direction pad
  I J K L    triangle square cross circle
  Q E        L1 R1                 1 3        L2 R2
  X C        L3 R3 (stick buttons)
  Enter      Start                 Backspace  Select
  F, F11 or Alt+Enter  full screen (Escape leaves it)
  F12        writes a picture of the game to rta-data/picture-N.png
  V          the next camera view: overhead (the game's own), action, chase, shoulder,
             first person (Shift+V: the one before). In the look views the mouse looks
             (Escape gives the pointer back, a click takes it again).
  A game controller SDL2 knows (Xbox, PlayStation, Switch and most others) is controller 1.

Four checks, in this order (in a terminal in this folder)

  1. The arithmetic of your processor:
         ./fpcheck > fpcheck.txt
     Its line "must agree everywhere" has to end in  @FPCHECK@  - the figure the Mac
     prints. If it does not, stop and report it: the game would not compute as on the Mac.

  2. The game without window or sound, from power-on into the first level by a script:
         ./rta_native boot --disc "/path/to/your.iso" --script boot-check.rig > boot-check.txt 2>&1
     Near its end it has to have these two lines (the "wall=" time will differ):
         @FRAMES_LINE@
         @VU0_LINE@
     (delete rta-data/card-headless before running it again: the script expects a blank card.)

  3. The game: ./play.sh "/path/to/your.iso" and play for a few minutes. Is there sound,
     do keyboard and controller work, is the picture even? Close it and send
     rta-data/rta_app-log.txt (its last lines, "rta_app: pacing:", say how even it was).
     If the picture stutters, try once with  --pacing queued  and say which is better.

  4. Online. Put the addresses you were given into server.txt (it says how). Then
         ./online.sh "/path/to/your.iso"                 the lobby (1, 2 or 3 as it asks)
         ./online.sh "/path/to/your.iso" room-host       a room of your own: its code is printed
         ./online.sh "/path/to/your.iso" room-join CODE  your friend's room
     The first time a player name is asked on the terminal (or: NAME=yourname ./online.sh ...).
     Each player makes or chooses a character on the game's own screens; the host starts.
     Every copy of this build says "patch set @PATCH_SET@" in its log; copies with another
     figure would not stay in step.

When something is wrong
  --no-sound            no sound device is opened (SDL_AUDIODRIVER=pulseaudio|pipewire|alsa chooses one)
  --plain               the picture without widescreen, multisampling and mip maps
  --antialiasing off    only the multisampling off
  --window 640x480      a smaller window      --fullscreen   start full screen
  SDL_VIDEODRIVER=x11 or wayland chooses the window system
