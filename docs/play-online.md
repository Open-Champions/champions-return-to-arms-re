# Playing online, on a Mac, without a console

How to build the playable application, start it, and get from the title screen into a
game with a friend. It is the [Play!](https://github.com/jpd002/Play-) emulator's desktop
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
```

The script fetches Play! (one fixed commit), applies `tools/play-net/play-net.patch`,
adds the sources in `tools/play-net/src/` and builds
`local/play-playable-build/Source/ui_qt/Play.app`. About ten minutes the first time.

## 2. Start

```
tools/play-net/play.sh --disc "/path/to/your disc image.iso" --server ADDRESS
```

- `--server ADDRESS` is the lobby server: an IPv4 address or a host name. Leave it out
  when the server runs on this same Mac.
- A second copy on the same Mac (to try it alone): add `--player 2`. It has its own
  settings and memory card.
- The first start may bring up the macOS question whether "Play" may accept incoming
  network connections: allow it (other players' game data arrives that way).
- Settings, the memory card and a log (`rta.log`, with every step of the network) are in
  `local/play-data/player1/`.

Nothing has to be set up in the game: the network setting it asks for is already on the
emulated memory card, the lobby's host name is answered by the application, and the
sign-in step that needs Sony's long-gone servers is skipped if you have the sign-in patch
at `local/SLUS-20973_4028A55F_signin.pnach` (it is not part of this repository; without
it the game stops with a network error after "Internet Game").

## 3. Keys

The keyboard, as Play! sets it up (change it, or bind a controller, in
*Settings → Controller Manager*: click a row, press the key or the controller's button):

| Controller | Key | Controller | Key |
|---|---|---|---|
| D-pad | arrow keys | left stick | T G F H (up, down, left, right) |
| ✕ cross | Z | right stick | I K J L |
| ○ circle | X | L1 / L2 / L3 | 1 / 2 / 3 |
| □ square | A | R1 / R2 / R3 | 8 / 9 / 0 |
| △ triangle | S | Start / Select | Return / Backspace |

Double-click the picture (or *View*) for full screen; Escape leaves it. The game moves the
character with the left stick, so on a keyboard that is T G F H until you change it.

## 4. From the title screen into a game with a friend

Everyone uses the same server address, the same disc version and the same patch list
(section 6).

1. **Start New Game → Internet Game** (down, ✕). The screen "Network Configuration and
   Selection" lists "1 Setting 1": ✕. The game connects and shows the server's terms: ✕.
2. **Log in.** The first time, △ *Create New Account*: login, password, password again,
   e-mail, date of birth, chat handle. Text is typed on the game's on-screen keyboard:
   □ opens it on the highlighted field, the D-pad moves, ✕ types, □ deletes, △ is a
   space, hold R2 for capitals and symbols, L2 finishes the field and goes to the next,
   ○ closes it. Then ✕. Later: □ on *login*, type, L2, type the password, L2, ✕ *Login*.
   ("Save Login/Password? Yes" keeps them on the memory card.) The account lives on the
   server you are connected to.
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
| sound block | 30 ms | how far sound runs behind the picture; Play!'s 100 ms was audible |
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
  (machine thread 6–9 ms and video thread 8–12 ms of a 16.7 ms frame); pictures looked at
  for these scenes only, standing or walking a few steps.
- The whole online path with two copies on this Mac against the lobby server on the same
  Mac: network setting found by the game, address, name lookup, gateway, lobby, terms,
  log in typed on the on-screen keyboard, stored characters imported, a game hosted and
  joined, the player-to-player handshake through real sockets, the launch, and 4,000
  lockstep frames of both characters walking and fighting with both machines agreeing on
  positions and hit points and no checksum failure.

Not tried, or known not to work:

- **Sound was never listened to**, and **no controller was connected**: both go through
  Play!'s own code unchanged (OpenAL; HID controllers bound in the Controller Manager).
- **Two different networks.** Section 7 follows from how the relay and the server work
  and from the lobby protocol; no session between two homes has been run.
- **More than two players**, private games, friends, chat typed by a player.
- **Fights, spells, cutscenes, films and most levels** have not been looked at on screen.
  Films are stored as two field pictures and probably still alternate between them.
- At 4× some interface panels show a one-pixel line along their right and bottom edge.
- Whether play **stays in step** between two different Macs is unknown; everything in
  `docs/online-setup.md` about that applies. Two copies on one Mac agree with each other.
- A machine that is paused, asleep or stopped for two minutes is dropped by the server;
  the others return to the lobby (`docs/issues/live-rig.md` section 20.4).
- Play!'s emulation is not a PlayStation 2: timing, sound and some graphics differ. What
  was found wrong for this game and repaired is listed in `tools/play-net/README.md`.
