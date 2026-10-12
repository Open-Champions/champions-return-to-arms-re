# Playing online, on a Mac, without a console

How to build the playable application, start it, and get from the title screen into a
game with a friend. **The short version: start it, type a player name once, and you are
in the lobby; *Online → Host a game* gives you a code of four letters, and your friend
types it under *Online → Join a game*** (section 4). It is the [Play!](https://github.com/jpd002/Play-) emulator's desktop
application with this project's changes (`tools/play-net/`): the game's own network stack
behind a built-in network, the test patches, and repairs to the emulator's picture and
speed for this game. It needs **no PlayStation 2 BIOS file**. You need your own disc image
of Champions: Return to Arms, SLUS-20973 version 2.00.

What has and has not been tried is at the end. Read "What is known not to work" before
you plan an evening around it.

## 1. Build (once)

Apple silicon Mac, Xcode command line tools, [Homebrew](https://brew.sh).

```
brew install cmake ninja qtbase
tools/play-net/build.sh
tools/play-net/package.sh
```

`build.sh` fetches Play! (one fixed commit), applies `tools/play-net/play-net.patch`,
adds the sources in `tools/play-net/src/` and builds
`local/play-playable-build/Source/ui_qt/Play.app`; about ten minutes the first time.
`package.sh` makes of it an application that needs no terminal:
`local/dist/Play-RTA.app`, with Qt and the patch list inside.

A copy for other people can be given its settings in advance, so that they have nothing
to set (`tools/play-net/package.sh --help` lists everything):

```
tools/play-net/package.sh --default-server ADDRESS --default-online on --zip
```

`--default-server` is the lobby server the copy uses and `--default-online` whether it
goes online by itself at the start; both hold only until the person sets something else
in the *Online* menu (they are kept inside the application, in
`Contents/Resources/rta/defaults.ini`, and the person's own `launch.ini` goes before
them). `--zip` also writes `Play-RTA.zip` beside the application, for sending; the
signature survives unpacking.

## 2. Start

### The application

Double-click `local/dist/Play-RTA.app` (or copy it anywhere, to another Mac too. There
the first opening is refused, because it is not notarised: click *Done*, then open
*System Settings → Privacy & Security*, scroll down to *Security* and click *Open
Anyway* beside "“Play-RTA” was blocked to protect your Mac."; once is enough. Before
macOS 15 a right-click and *Open* does the same.)

- **Keep the game image in the same folder as the app (or in Downloads).** Nobody is
  asked to choose a file: at the start the application looks for the image by itself,
  beside the application, in its data folder, then in Downloads, Desktop and Documents
  (and one level of their sub-folders), and remembers it. The file may have any name; it
  has to be Champions: Return to Arms, US release SLUS-20973, version 2.00, and anything
  else is passed over. Only when there is none, one window says where to put the file,
  with *Retry* and *Browse…*. *Online → Choose the disc image…* changes it later. For
  Downloads, Desktop and Documents macOS asks once whether "Play-RTA" may access that
  folder: allow it (a file beside the application needs no such question).
- ***Online → Server, player, patch set…***: the lobby server's address (empty: the
  server runs on this Mac; a copy made with `package.sh --default-server` comes with
  one), the player number (leave it at 1; another number is a second
  copy on the same Mac with its own settings and memory card), and the patch-set figure
  to compare with your friends (section 6). A change is taken up when the application
  starts again; the dialog offers to do that.
- **The sign-in patch** is not inside the application. Put
  `SLUS-20973_4028A55F_signin.pnach` into `~/Library/Application Support/Play-RTA/` or
  next to the application; the Online dialog says whether it was found. Without it the
  game stops with a network error after "Internet Game".
- **It goes online by itself** when it starts (section 4): the first time it asks for
  your player name, after that you arrive in the lobby without pressing anything.
  *Online → Go online at start* switches that off.
- Settings, memory card, the saved online login and the log `rta.log` are in
  `~/Library/Application Support/Play-RTA/player1/`. One folder up, `launch.ini` holds
  what the application was told: `server`, `player`, `online` (go online at start),
  `disc` (the remembered image) and, if you write it there, `textures` (a directory of
  replacement textures, what `--rta-textures` gives; section 5).
- A second copy on the same Mac: set player 2 in the Online dialog of a second start
  (`open -n local/dist/Play-RTA.app --args --rta-player 2` does both at once).
- *Help → About* says what this is: the Play! emulator (BSD licence) with this
  project's changes; the licences are inside the application
  (`Contents/Resources/licences`).

### From a terminal

```
tools/play-net/play.sh --disc "/path/to/your disc image.iso" --server ADDRESS
```

- `--server ADDRESS` is the lobby server: an IPv4 address or a host name. Leave it out
  when the server runs on this same Mac.
- `--online` goes online by itself after the start (section 4). Without it the
  application waits at the title screen, and *Online → Play Online* does the same later.
  `--host` goes on to open a game of your own (its code is in the window "Your game" and
  in the status bar); `--join CODE` goes on into the game with that code.
- A second copy on the same Mac (to try it alone): add `--player 2`. It has its own
  settings and memory card.
- Settings, the memory card and a log (`rta.log`, with every step of the network) are in
  `local/play-data/player1/`. The sign-in patch is looked for at
  `local/SLUS-20973_4028A55F_signin.pnach`.

Either way: the first start may bring up the macOS question whether the application may
accept incoming network connections: allow it (other players' game data arrives that
way). Nothing has to be set up in the game: the network setting it asks for is already on
the emulated memory card, the lobby's host name is answered by the application, and the
sign-in step that needs Sony's long-gone servers is skipped by the sign-in patch (not
part of this repository).

## 3. Controller and keys

**A game controller** works the moment it is attached — plugged in by USB or paired by
Bluetooth, before the start or in the middle of a game — with nothing to set up:
DualSense, DualShock 4, Xbox and Switch Pro controllers and the others macOS knows. The
sticks, the direction pad, the four face buttons and the shoulder buttons are where they
are on a PlayStation pad (on an Xbox pad A is ✕, B is ○, X is □, Y is △); Options or Menu
is Start; Create, Share or View is Select, and so is pressing a Sony pad's touchpad. L2
and R2 count as pressed from a third of the way. The status bar says "controller:
DualSense" (or what it is) while one is attached. The first controller attached is the
one that plays; it is listened to while the window is in front. A controller macOS does
not know can still be bound by hand in *Settings → Controller Manager*.

**The keyboard** works beside it:

| Controller | Key | Controller | Key |
|---|---|---|---|
| left stick (move) | W A S D | D-pad (menus) | arrow keys |
| ✕ cross | K | ○ circle | L |
| □ square | J | △ triangle | I |
| L1 / L2 / L3 | Q / 1 / X | R1 / R2 / R3 | E / 3 / C |
| right stick (camera) | T F G H (up, left, down, right) | Start / Select | Return / Backspace |

The four face buttons lie on I J K L as they lie on the pad: I on top, J left, K below,
L right. *Help → Controls…* shows this table and the attached controller; it opens by
itself on the first start. Keys can be changed in *Settings → Controller Manager* (click
a row, press the key). A data directory made by an earlier version of this build is given
this layout once (Play!'s own put the left stick on T G F H).

Double-click the picture (or *View*) for full screen; Escape leaves it.

## 4. From the title screen into a game with a friend

Everyone uses the same server address, the same disc version and the same patch list
(section 6).

### Into the lobby: the short way

**Start it, type a player name once, and you are in the lobby.**

- The packaged application does it at every start; from a terminal it is `play.sh
  --online`; at any time from the title screen it is *Online → Play Online*.
- The application then presses its own way through the game: the memory-card questions
  and the logos, *Start New Game*, *Internet Game*, the network setting, the server's
  terms (accepted), the log-in. It stops at the lobby's game list ("Game Selection and
  Chat") and the controls are yours. From a cold start that takes about half a minute;
  the status bar says where it is ("Going online: logging in...").
- **The first time** a window asks for your **player name**: what the others see in the
  lobby, in a game's room and in chat. 3 to 15 letters and digits, typed on the Mac's
  keyboard. That is all you are asked. If the name is taken on that server the window
  comes back for another one.
- You never see an account or a password. The application makes both for you in the
  game's own account screen: the name you chose, a random password, a placeholder e-mail
  address (`<name>@example.invalid`) and date of birth (01/01/1980), and your name again
  as the chat handle. Name and password are kept per server in the file `online-login`
  in the data directory, readable by you alone; every later start logs in with them.
  The player name is registered with the server you are connected to, and going online
  this way accepts that server's terms for you (the game shows them under *Internet
  Game* if you go by hand).
- *Online → Forget online login* deletes the saved pair for the server you are on; the
  next start asks for a name again. (The old name stays taken on the server.) A second
  copy (`--player 2`) has its own.
- While it is pressing, your own keys and controller are not passed to the game. When
  anything comes up that it does not know - an error box, another menu, the server not
  answering for twenty seconds - it stops, says why in the status bar and in `rta.log`
  ("Going online stopped: ..."), and you have the controls where the game is. *Online →
  Stop going online* does the same on request.

### Into a game with a friend: the short way, by code

One of you hosts, the others join; nobody looks for anybody in a list.

- **Host: *Online → Host a game*** (or start with `play.sh --host`). The application
  goes online as above if it is not there yet, opens the lobby's *Host Game*, and hands
  you the **character screens**: make a character, or press △ for one stored on the
  server or the memory card, ✕ to accept it. When you are through, it goes on by itself:
  it names the game with a **code of four letters**, takes the game form's own settings
  (a public mission game at the difficulty your character allows), and stops in your
  game's room. The code stands large in the window "Your game" and in the status bar:
  **tell it to your friends**. When they have appeared in the room, press ✕ *Start Game*.
- **Join: *Online → Join a game...***, type the code (or start with `play.sh --join
  CODE`). The application goes online, waits until a game of that name is in the lobby's
  list (the game asks the server for the list about every twelve seconds; it gives up
  after two minutes and says so), joins it, hands you the character screens as for the
  host, and stops in the room. The host starts the game.
- The code is the game's name in the lobby, nothing more: anybody on that server can see
  the game in the list and join it by hand too. A game somebody named by hand can be
  joined by typing its name as the code, if it has 4 to 8 letters and digits.
- The same rules as for going online: while the application presses, your keys are not
  passed on (except on the character screens, which are yours); anything unexpected
  stops it with a note in the status bar and `rta.log`, and you go on by hand from where
  the game is.

### Into the lobby: by hand

The way the game itself wants it; it always works, and it is the way to use an account
you made earlier.

1. **Start New Game → Internet Game** (down, ✕). The screen "Network Configuration and
   Selection" lists "1 Setting 1": ✕. The game connects and shows the server's terms: ✕.
2. **Log in.** The first time, △ *Create New Account*: login, password, password again,
   e-mail, date of birth, chat handle. Text is typed on the game's on-screen keyboard:
   □ opens it on the highlighted field, the D-pad moves, ✕ types, □ deletes, △ is a
   space, hold R2 for capitals and symbols, L2 finishes the field and goes to the next,
   ○ closes it. Then ✕. Later: □ on *login*, type, L2, type the password, L2, ✕ *Login*.
   ("Save Login/Password? Yes" keeps them on the memory card.) The account lives on the
   server you are connected to.

### In the lobby, by hand

3. **The lobby** ("Game Selection and Chat") lists the open games; it refreshes about
   every twelve seconds. L1/R1 move between the list and the chat panes.
4. **To host:** △ *Host/Search*, ✕ *Host Game*. The character screens come up: make a
   new character (class, looks, 20 ability points, name), or press △ there to import one
   that is stored on the server ("RTA Net") or on the memory card, ✕ to accept it, ✕
   again on its sheet. Then the game form: □ to type a name (L2 when done), left/right to
   change difficulty, game type and mission, ✕ *Submit*. You are in the game's room; wait
   for your friends to appear there, then ✕ *Start Game*.
5. **To join:** highlight the game in the list, ✕ *Join Game*. After a few seconds
   ("Attempting…") the character screens come up as for the host; accept a character and
   you are in the room. The host starts the game.
6. In the game, Start opens the pause menu; leaving the game is there. Characters are
   saved on the server every half minute or so while you play.

If a press seems to be ignored on the lobby and character screens, press again and hold
the key a little longer: the game itself drops short presses there.

## 5. Picture and response

The application starts with the settings below. They are in *Settings* and on the status
bar (right-click the "4x" to change the resolution).

| Setting | Value | Why |
|---|---|---|
| resolution factor | 4× (2560 × 896 per field; 8× also held 60 frames a second on an M5 Pro) | at 1× the console's 640 × 224 picture is stretched into blocks |
| presentation | fit, 4:3 | the game is 4:3; Play! used to show it 7 % too wide |
| steady picture | on (`--rta-interlaced` turns it off) | the game draws for an interlaced television: every other picture half a line lower, interface art split into two field pictures. Shown in a window that makes the whole picture jump up and down. The application changes six instructions of the game's drawing code (picture only, never the simulation, so they are not part of the shared patch set) and emulates the GS scanline mask, so that every picture is drawn at the same height and the interface is drawn from both of its field pictures |
| frame timing | by the display's refreshes (`--rta-timer` for a timer) | each picture stays on screen for exactly two refreshes of a 120 Hz display (one at 60 Hz) |
| sound | pieces of 30 ms, 40 ms held in reserve | about 55 ms behind the picture, and no gaps: Play!'s own way (100 ms pieces, no reserve) ran dry 20 times in five minutes of play |
| pause when the window is not in front | off | a paused machine loses the lobby after two minutes and stalls every other player at once |

**Speed.** In the first level the machine runs at 60 frames a second with about half a
processor core for the machine and 10 ms of a 16.7 ms frame for the video thread (M5 Pro).
Before the repairs in `tools/play-net/README.md` the same scene ran at 17–20 frames a
second: that slow motion, not the controller, was the "lag".

**Response — what is the emulator's and what is the game's.** Measured by injecting a
press where the emulator reads the controller and timing the pictures it presents
(`tools/play-net/latency.py`):

- The emulator reads the controller immediately before each frame is computed and shows
  the frame it produces before the next one starts. In a menu the first picture after a
  press already shows the change. It adds no queued frame. What remains outside the
  game: a key press waits for the next frame to begin (0–17 ms), and the finished picture
  for the display's refresh (with the display timing above it appears one frame time
  after the frame began).
- The game itself, in a level, shows the first movement of an attack in the fifth or sixth
  picture after the press (82–104 ms measured, offline). That is how it plays on a
  console too.
- **Online the game adds more of its own**: it delays every player's input by a few
  frames so that all machines can run the same frame (about five for two players; more
  after a stall, see the LAG-1 section in `docs/online-setup.md`), and it ramps the
  stick. That delay is part of the game's lockstep and cannot be removed here; it grows
  with the distance between the players.

Do not use Play!'s save states in an online session (the network adaptor is not part of
a state), and do not pause.

**Other art.** Every texture can be written out as a PNG file and replaced by a file of
any size with the same name (`tools/play-net/README.md`, "Texture dump and
replacement"); replaced textures change the picture only.

**Sharper art (optional).** The textures can be enlarged four times by a learned model
and drawn in place of the game's own: text, menus, bars, stone, leaves and characters
come out sharper, in the game's colours; grass stays about as it is. It needs the
`realesrgan-ncnn-vulkan` program, which is not part of this repository
(`tools/play-net/README.md`, "Upscaled art", has what is done and why):

```
tools/play-net/play.sh --disc IMAGE -- --rta-textures "$PWD/local/hd-pack" --rta-texture-dump
tools/play-net/upscale.py local/hd-pack/dump local/hd-pack/replace --upscaler PATH/realesrgan-ncnn-vulkan
tools/play-net/play.sh --disc IMAGE -- --rta-textures "$PWD/local/hd-pack"
```

The first line is playing with every texture written out as it is drawn; the second
enlarges what is new (about two thirds of a second a picture); the third plays with the
pack. Keep `--rta-texture-dump` on and repeat the second line to make the pack grow with
where you have been. The pack for the title, the menus and the first level takes 1.4 GB
of video memory at 60 frames a second on an M5 Pro; `--scale 2` on the second line makes
one of a quarter of that. A pack changes your picture only: the other players need not
have it.

## 6. What every player has to have the same

- The disc: SLUS-20973 v2.00. The application checks the executable and applies no patch
  to anything else.
- This build of the emulator — not PCSX2, not a console, not another Play! version. Play
  is lockstep: every machine computes the whole game itself.
- The patch list. `play.sh` applies the sections named in
  `tools/play-net/sections-suggested.txt` from `patches/SLUS-20973_4028A55F.pnach`. The
  status bar and `rta.log` show a figure for it ("patches: 19 sections, … set
  xxxxxxxx"): compare it with your friends' before you start. Resolution, keys and the
  other settings of section 5 may differ: they do not touch the game's simulation.

## 7. Two people on different networks

The game finds its lobby by one address and then talks player to player over UDP
(`docs/lobby-protocol.md` sections 9 and 11). What each side has to arrange:

**Whoever runs the lobby server at home**

- Forward on the router, to the Mac that runs the server: TCP 40810 and 40910, UDP 10101.
- In the server's `config.ini` set `public_ip` to the router's public IPv4 address and
  `report_public_ip_for_lan_consoles=1` (otherwise players outside are told your private
  address for the people at your place).
- If someone plays at the server's own place, also forward UDP 4000–4004 to the Mac they
  play on: the server cannot see which outside port the router gives the game, and the
  application takes the same port numbers on the Mac as the game uses.
- Start your own copy with no `--server` (server on the same Mac) or with the server's
  local address. The server will hand your game its public address; the application
  notices that and keeps talking to the server locally (it says so in `rta.log`), so the
  router does not have to send your own traffic back in.

**Everyone else**

- `--server <the public address or host name>`. Nothing to forward on an ordinary home
  router: the game's own hole punching does it, and the application gives the game one
  outside port for the server and for the other players, which is what that needs.
- A router that picks a new outside port for every destination ("symmetric" NAT, some
  mobile and company networks) will not work unless UDP 4000–4004 is forwarded to the
  Mac — or everybody joins one VPN and uses the server's VPN address.

**Two copies on one Mac, or two Macs in one home with the server**: nothing to arrange;
the server sees them at local addresses and they talk directly (two copies on one Mac
through the loop-back interface, which the application does by itself).

Two Macs in one home with the server **somewhere else** are both told the home's public
address for each other; that only works if the router sends such traffic back in.

## 8. What has been tried, and what is known not to work

Tried on one Mac (M5 Pro, macOS 27), with the control socket driving the game, not a
person at the controls:

- Power-on, title, menus, character creation, the lobby screens, the first level, one
  dungeon level (`fire1`) and the arena level, with video at 4×, at 60 frames a second
  (machine thread 6–9 ms and video thread 8–12 ms of a 16.7 ms frame).
- The packaged application, started by `open`: first start, a wrong disc refused, the
  right one remembered, the first level reached, a second start.
- The whole online path with two copies on this Mac against the lobby server on the same
  Mac: network setting found by the game, address, name lookup, gateway, lobby, terms,
  log in typed on the on-screen keyboard, stored characters imported, a game hosted and
  joined, the player-to-player handshake through real sockets, the launch, and 4,000
  lockstep frames of both characters walking and fighting with both machines agreeing on
  positions and hit points and no checksum failure.

- **One-step online and games by code** (section 4), with background test copies
  against the lobby server on the same Mac, player names made by the test: a first start
  that made its account and reached the lobby's game list by itself (30 s after launch);
  a second start that logged in with the saved pair (28 s); a first name that was taken,
  the second accepted; the server's gateway at a closed port (stopped after 20 s of the
  game's "Connecting", controls handed back); a saved login the server refused (stopped
  at the game's "Login Failed" box); *Play Online* from the title screen and from the
  Normal Game / Internet Game menu; *Forget online login* and a new name after it. Two copies: one hosted (`--host`), the other joined by the
  code (`--join CODE`), both reached the room, the host pressed *Start Game*, both were
  in the first level, at the same simulated frame when sampled together, with the same
  shared seed and hit points and no checksum failure, for 650 frames. A code that no
  game has: stopped after two minutes at the list, with the reason.

Not tried, or known not to work:

- **One-step online**: the windows for the player name, the code and *Join a game* were
  drawn to pictures and read, but no person has typed into them (a background test copy
  cannot show a window to anyone; the tests gave the name and the code by option). The
  packaged application's going online at every start was not run (a test copy never
  does it by itself). Nothing of it was ever run against a server that is not on this
  Mac. On the character screens the application waits for you: it does **not** pick the
  character you used last by itself, and it does not ask for difficulty or game type:
  the game form's own settings are taken. A character was made on those screens by the
  test's own presses, not by a person.

- **Controllers**: a DualSense by USB was seen to attach (log, status bar); every button,
  both sticks, the dead zone and the trigger threshold were exercised with a controller
  made by the program, which goes through the same code as a real one, and the game was
  driven from the title into the first level with it. No real button was pressed by the
  tests, and Bluetooth and other makes were not tried.
- **Sound was never listened to.** It was counted: five minutes in the first level and
  five at the title without the output running dry once, nothing thrown away, no
  silence inside sound (`tools/play-net/README.md`, "Sound"). While a level loads there
  are short gaps (the machine stops on disc reads).
- **Two different networks.** Section 7 follows from how the relay and the server work
  and from the lobby protocol; no session between two homes has been run.
- **More than two players**, private games, friends, chat typed by a player.
- **Looked at on pictures at 4×** besides the scenes above: the opening film, the pause
  menu, a dungeon and an underwater level, two cutscenes, the arena with a fight against
  five opponents. **Not looked at**: the inventory, shop, skill and map screens, spells,
  and most levels.
- Whether play **stays in step** between two different Macs is unknown; everything in
  `docs/online-setup.md` about that applies. Two copies on one Mac agree with each other.
- A machine that is paused, asleep or stopped for two minutes is dropped by the server;
  the others return to the lobby (`docs/issues/live-rig.md` section 20.4).
- Play!'s emulation is not a PlayStation 2: timing, sound and some graphics differ. What
  was found wrong for this game and repaired is listed in `tools/play-net/README.md`.
