Champions: Return to Arms - native build for Windows (experimental, third test build)
====================================================================================

This program was built on a Mac and has NEVER BEEN RUN on Windows. You are the first test.
Nothing is installed; everything it writes goes into the folder "rta-data" beside it.

In the second build: playing online through a lobby server, widescreen and the other
picture settings. New in this one (2026-10-13): the way the game is held to 60 pictures a
second (check 3, "How even is it"), a fix for threads that were left behind after every
online game, the fix set every build of this day has, and the camera views (the V key:
they were made and tried on the Mac this afternoon; on Windows not even the mouse code
has run - say what happens when you press V and move the mouse). None of it has been
seen on Windows either.

You need
  - Windows 10 (version 1903 or later) or Windows 11, 64-bit
  - a graphics driver from Intel, AMD or NVIDIA with OpenGL 4.1 or newer
  - your own disc image (.iso) of Champions: Return to Arms, US version SLUS-20973 v2.00
  - for the online test: the address of the lobby server, which you are given with this
    folder

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
  V          the next camera view: overhead (the game's own), action, chase, shoulder,
             first person (Shift+V: the one before). In chase, shoulder and first person
             the mouse looks (the pointer is hidden and kept in the window; Escape gives
             it back, a click takes it again), W A S D walk where you look, left mouse
             button attacks, right blocks, middle uses, the wheel swaps weapons, Tab is
             the map. With a controller the right stick looks.
  An Xbox controller (or any controller that Steam or DS4Windows presents as one) works
  as controller 1 as well.

Five checks, in this order
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
         @FRAMES_LINE@
         @VU0_LINE@
     boot-check-mac.txt is what the Mac printed; to compare the two yourself:
         fc boot-check.txt boot-check-mac.txt
     (delete the folder rta-data\card-headless before running the check a second time:
     the script expects a blank memory card.)

  3. The game: drag the .iso onto play.bat and play for a few minutes.
     How even is it. The game is now let go by a clock a few milliseconds ahead of the
     moment each picture is due, and that clock is set by your display: this was written
     for the Mac, measured there, and carried over to Windows by reading - you are the
     first to see it. Please look at three things and say what you saw:
       - walking through a level with the camera moving: does the picture move evenly,
         or does it hitch (a short stop every second or so, or now and then)?
       - drag the window by its title bar while the game runs, and make it larger and
         smaller: the game should go on (sound too), the picture may stop while you drag;
       - click another program so that it lies over the game's window, wait a few
         seconds, come back: the game should have gone on, with no burst of fast motion.
     Then close the game and look at the last lines of rta-data\rta_app-log.txt; they
     start with "rta_app: pacing:" and "rta_app: path:". Send the log in any case. What
     they should say on a PC that keeps up: nearly every picture "stood for" the same
     number of refreshes (1 on a 60 Hz display, 2 on 120 Hz, 4 on 240 Hz), "the swaps
     wait for the display", only a few pictures "more than half a refresh late" or
     "drawn and not shown".
     If the picture stutters, start once more with  --pacing queued  (the way the first
     two builds held the game) and say which of the two is better; send both logs.

  4. The picture. The first start writes rta-data\settings.txt; every line in it says what
     it is, and you can edit it with Notepad (close the game first).
       - Make the window wide by dragging its edge, or press F for full screen: the 3-D
         view should become wider (you see more to the sides, nothing is stretched), the
         health bars should stay at the left edge, menus and text in the middle.
       - Edges should look smooth (4 samples of multisampling are on by default) and the
         ground in the distance should not shimmer (mip maps, anisotropic filtering).
       - If anything looks wrong, start once with  --plain  (everything of this list off:
         the picture as the console makes it) and say whether it is still wrong.
     Press F12 on a normal and on a wide picture and send both.
     The reader of enlarged textures ("art packs") has a check of its own, without a pack:
         pnghash.exe pngtest > pnghash.txt
     Send pnghash.txt. Its line has to end in  figure @PNG_HASH@  - what the Mac prints
     for the same folder of test pictures (pngtest, beside this file).
     If you have a folder of enlarged textures made for the emulator build of this project
     (files named like 0123456789abcdef-0123456789abcdef-p19-256x128.png), try
         rta_app.exe --disc "C:\path\to\your.iso" --art-pack "C:\path\to\that folder"
     (or put the folder into settings.txt as art_pack). Without such a folder skip this.

  5. Online. You were given the address of a lobby server.
       a. Open server.txt (in this folder) with Notepad and put the address on a line of
          its own, save.
       b. Drag the .iso onto online.bat and type 1. The game should go by itself from the
          title screen through "Internet Game" to the lobby's list of games. The first
          time a small dialogue asks for a player name (3 to 15 letters and digits): type
          one, press Enter. You are not asked for a password: the program makes the
          account and keeps its login in rta-data\online-login (do not send that file).
          Windows may ask whether rta_app.exe may use the network: allow it (the game
          receives from the other players).
       c. The window's title should show the server and what the program is doing.
       d. With a second person (they can use this build, or the Mac or emulator build of
          the project, on the same server): one drags the .iso onto online.bat and types
          2 - the window's title then shows a code of four letters; the other types 3 and
          that code. Each of you chooses or makes a character when the game asks; when
          both are in the room the host presses Start (Enter). Play a few minutes
          together: walk, fight, change the level.
       e. Close the game with the window's X. Send rta-data\rta_app-log.txt of each PC.
     In that log, the lines starting with [net] say which server was used, this copy's
     "patch set" (it should read  @PATCH_SET@  on every copy of this build; if two players
     have different figures a warning box appears, and the games would not stay in step),
     and at the end how many connections and packets there were.
     A second player on the same PC:  rta_app.exe --disc "..." --player 2 --join CODE
     Without online.bat:  rta_app.exe --disc "..." --server ADDRESS --online | --host [CODE] | --join CODE

What to report
  - fpcheck.txt, boot-check.txt, pnghash.txt, and the file rta-data\rta_app-log.txt (written on every
    run; it starts again on each run, so copy it before you start the program again)
  - did a window open? did the memory card screen, the logo, the title screen appear?
  - is there sound? does it crackle or drop out?
  - do the keyboard and the controller work?
  - does it run at normal speed and smoothly?
  - widescreen: the two F12 pictures; does the picture follow when you resize the window?
  - online: did the name dialogue appear, could you type and confirm? did the game reach
    the list of games by itself? did host and join by code work? did the two games stay
    together (the same things happening on both screens), for how long? any message box?
  - anything that looks wrong: press F12 at that moment and send the picture
  - if it closes by itself: the last lines of rta-data\rta_app-log.txt say why

When something is wrong
  --pacing queued       the pacing of the earlier builds (see check 3)
  --no-sound            no sound device is opened
  --no-films            the films at the start are skipped
  --plain               the picture without widescreen, multisampling and mip maps
  --antialiasing off    only the multisampling off (a driver that shows a black 3-D scene)
  --window 640x480      a smaller window        --fullscreen   start full screen
  --scale 2             draw at twice the console's resolution instead of the window's size
  --no-settings         do not read rta-data\settings.txt
  set RTA_SOUND_API=waveout   (before starting, in the same Command Prompt) the older sound interface
  rta_app.exe --help    the whole list
  rta_app_gcc.exe (if it is in this folder): the same program built by a second compiler.
  Try it only if rta_app.exe does not start at all, and say which one you used.
  Online: "the game will not get online" or a network error after "Internet Game" in the
  log means the server's address could not be reached: check server.txt, your firewall,
  and that the server is running; the line with "TCP ->" names the address that was tried.
  Online, and no dialogue asks for your name (the game waits at the log-in screen):
         rta_app.exe --disc "C:\path\to\your.iso" --online --name YourName
  gives the name on the command line (3 to 15 letters and digits). Say so in the report.

The two films at the start (the developer's logo, the intro) are played by this build. If
one hangs, looks wrong or has no sound, say so and start again with  --no-films  (a film
then ends at its first picture).
