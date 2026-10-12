Champions: Return to Arms - native build for Windows (experimental, first test build)
====================================================================================

This program was built on a Mac and has NEVER BEEN RUN on Windows. You are the first test.
Nothing is installed; everything it writes goes into the folder "rta-data" beside it.

You need
  - Windows 10 (version 1903 or later) or Windows 11, 64-bit
  - a graphics driver from Intel, AMD or NVIDIA with OpenGL 4.1 or newer
  - your own disc image (.iso) of Champions: Return to Arms, US version SLUS-20973 v2.00

Start
  Drag your .iso file onto play.bat (or onto rta_app.exe).
  Or, in a Command Prompt in this folder:   rta_app.exe --disc "C:\path\to\your.iso"

Keys
  W A S D    left stick            arrows     direction pad
  I J K L    triangle square cross circle
  Q E        L1 R1                 1 3        L2 R2
  X C        L3 R3 (stick buttons)
  Enter      Start                 Backspace  Select
  F, F11 or Alt+Enter  full screen (Escape leaves it)
  F12        writes a picture of the game to rta-data\picture-N.png
  An Xbox controller (or any controller that Steam or DS4Windows presents as one) works
  as controller 1 as well.

Three checks, in this order (each takes a minute)
  Open a Command Prompt in this folder first: type cmd in the address bar of the folder
  window and press Enter.

  1. The arithmetic of your processor:
         fpcheck.exe > fpcheck.txt
     Send fpcheck.txt. Its line "must agree everywhere" has to end in 2e77df4dc13ec9c5,
     the number the Mac prints. If it does not, stop here and report it: the game would
     not compute on your PC as it does on the Mac.

  2. The game without window or sound, from power-on into the first level by a script
     (it presses the buttons; about ten seconds):
         rta_native.exe boot --disc "C:\path\to\your.iso" --script boot-check.rig > boot-check.txt 2>&1
     Send boot-check.txt. Near its end it has to have these two lines, as on the Mac
     (the "wall=" time and the speed will be different, nothing else):
         frames=2309 wall=...: ... fields=2413 units=113069982
         VU0: 466083 microprogram calls, 26111361 instructions
     boot-check-mac.txt is what the Mac printed; to compare the two yourself:
         fc boot-check.txt boot-check-mac.txt
     (delete the folder rta-data\card-headless before running the check a second time:
     the script expects a blank memory card.)

  3. The game: drag the .iso onto play.bat and play for a few minutes.

What to report
  - fpcheck.txt, boot-check.txt, and the file rta-data\rta_app-log.txt (written on every
    run; it starts again on each run, so copy it before you start the program again)
  - did a window open? did the memory card screen, the logo, the title screen appear?
  - is there sound? does it crackle or drop out?
  - do the keyboard and the controller work?
  - does it run at normal speed and smoothly?
  - anything that looks wrong: press F12 at that moment and send the picture
  - if it closes by itself: the last lines of rta-data\rta_app-log.txt say why

When something is wrong
  --no-sound            no sound device is opened
  --window 640x480      a smaller window        --fullscreen   start full screen
  --scale 2             draw at twice the console's resolution instead of the window's size
  set RTA_SOUND_API=waveout   (before starting, in the same Command Prompt) the older sound interface
  rta_app.exe --help    the whole list
  rta_app_gcc.exe (if it is in this folder): the same program built by a second compiler.
  Try it only if rta_app.exe does not start at all, and say which one you used.

Known not to work yet (as on the Mac): the two films at the start are skipped.
