# Get the game and play

Updated with each release. **Last update: 2026-10-20** (section 8: the native version from your own disc). Current release: fix set
`9ac29719` (31 sections), and in the Mac application the new **Room** menu (section 4).
How complete each part is: [PROGRESS.md](PROGRESS.md).

## 1. What you need

1. **The link.** One private link leads to both versions below. You get it from the person
   who invited you to play. (Not invited by anyone? See section 7.)
2. **Your own disc image** of *Champions: Return to Arms* - the US release, SLUS-20973,
   version 2.00 - as one file (`.iso`). Nothing of the game comes with the download.
3. **A computer**: a Mac with Apple silicon and macOS 14 or later, or any computer with
   the Chrome browser (Windows included). No PlayStation 2 BIOS is needed.

## 2. On a Mac: the application

1. Open the link and click **Download Play-RTA.zip**. Unzip it; you get one app, *Play-RTA*.
2. Open it. The first time macOS refuses ("Not Opened"): go to **System Settings →
   Privacy & Security**, scroll to *Security*, click **Open Anyway**, and confirm.
3. Put your disc image next to the app, in Downloads, or in
   `~/Library/Application Support/Play-RTA/`. The app finds it by itself.
4. To play with friends, use the **Room** menu (section 4, the new way) or the **Online**
   menu (section 5, the lobby - the way to play with browser players).

A controller that macOS knows (DualSense, DualShock 4, Xbox, Switch Pro) works when it is
plugged in or paired. The keyboard works too: the app shows the keys under *Controls*.

## 3. On Windows or any other computer: in the browser

1. Open the link **in Chrome** and click **Play in your browser**.
2. When the page asks, pick your disc image file. It is read on your own computer and is
   not uploaded anywhere.
3. Type a **player name**, click **Online...**, then **Host a game** or **Join a game**
   with a room code.
4. Keep the tab in front while you play online: a hidden tab slows down and drops out.

Brave works as well. Safari stalls for a few seconds when a level loads. Firefox and Edge
have not been tried.

## 4. Playing together on Macs: the Room menu (new)

A room is a game of two to four players on our own room service. There is no lobby, no
account and no password, and Mac-app players and players of the native program (section 7)
can be in the same room.

1. **Start from the game's title screen.** The app as sent goes to the lobby by itself when
   it opens. For a room, switch that off once: **Online → Go online at start** (so that it
   has no tick), quit the app and open it again. It now stops at the title screen. (Tick it
   again whenever you want the lobby back.)
2. **One player hosts:** **Room → Host a room**. The first time, the app asks for *the name
   the other players see* (3 to 24 characters); type it and click **Go to the room**. It is
   asked only once.
3. A window shows the **room code** - five letters and digits, such as `H4KQ7`. The host
   **reads it out** to the others (or sends it in a message). *Room → Show the room's code*
   brings it back.
4. **Everyone else joins:** **Room → Join a room...**, type the code, click OK (and the
   name, the first time). A player of the native program joins the same room with the same
   code.
5. On every computer the game's **own character screens come up by themselves**: make a new
   character, or *Import* one from the memory card.
6. When everybody has a character, **the host chooses Room → Start the game**. The game
   connects everyone and the first level loads.
7. The status bar at the bottom says where the room stands ("room H4KQ7: 3 players ...") and
   warns if someone's copy is different.
8. After the game, or to give up waiting: **Room → Leave the room**. For another game, host
   a new room.

Who you are in rooms is a file in the app's data folder (`net2-identity.key` in
`~/Library/Application Support/Play-RTA/player1/`), not an account. Copy that file to another Mac to
be the same player there; delete it and you are a new player.

## 5. Playing through the lobby: the Online menu (as before)

The **Online** menu is still there and works as before. Use it to play with **browser
players**, or if you prefer the old way.

1. Leave **Online → Go online at start** ticked (it is, as the app is sent), or choose
   **Online → Host a game** / **Join a game...** from the title screen.
2. Type a **player name** when the app asks. That is your name on the lobby server; there
   is no password to remember.
3. **Online → Host a game** gives you a room code of four letters to read out; the others
   choose **Online → Join a game...** and type it. Browser players do the same on their
   page (section 3).

## 6. Who can play with whom

| | Mac app | Native program | Browser |
|---|---|---|---|
| **Room menu** (our own room service) | yes | yes | not yet |
| **Online menu** (the lobby) | yes | yes | yes |

- Two to four players in every case. One player hosts and reads the code out; the others
  join with it.
- **Everyone needs the same fix set.** All versions behind the link always carry the same
  one (now `9ac29719`); if a friend's copy is older, the room says so before the game
  starts - they download again.
- More about what happens online, your account and your character:
  [play-online.md](play-online.md); about rooms:
  [issues/app-rendezvous.md](issues/app-rendezvous.md).

## 7. Why the link is not here, and how to build it yourself

The ready-made versions behind the link are set up for one private server and carry a
small sign-in file that is not part of this repository. So there is no public download
button. Everything else is here, and you can build each version yourself with your own disc:

| Version | State | Build it |
|---|---|---|
| Mac application | released | [tools/play-net](../tools/play-net/README.md): `build.sh`, then `package.sh` |
| Browser version | released; further work paused | [tools/play-web](../tools/play-web/README.md) |
| Lobby server (the Online menu, browser players) | running | [online-setup.md](online-setup.md) |
| Room service (the Room menu; no account) | running, encrypted | [tools/rendezvous](../tools/rendezvous), [issues/native-rendezvous-tls.md](issues/native-rendezvous-tls.md); in the Mac application: [issues/app-rendezvous.md](issues/app-rendezvous.md) |
| Native build for Mac (the game's code translated to C++, no emulator) | experimental; plays offline and online, joins rooms | section 8; [issues/native-recomp.md](issues/native-recomp.md), [issues/native-app.md](issues/native-app.md) |
| Native build for Windows | experimental; builds, never run on a Windows computer | section 8; [issues/native-windows.md](issues/native-windows.md) |
| Native build for Linux | experimental; runs in a container (x86-64, aarch64), plays in a room with the Mac | section 8; [issues/native-linux.md](issues/native-linux.md) |
| Native build in Godot (first person and other views, new interface, portal) | in development; nothing to download yet | [issues/native-godot.md](issues/native-godot.md), [issues/native-first-person.md](issues/native-first-person.md) |

## 8. Native version: build it from your own disc

The native version is the game's own code translated to C++ and built into a program for
your computer - no emulator, no BIOS. Because that code comes from the game, it can never be
handed out: **every player translates it from their own disc**. One script per system does
all of it: it checks (and, after you say yes, installs) the compiler, asks for your disc
image, copies the game's executable `SLUS_209.73` out of it, translates and builds, and puts
**Champions RTA Native** on your desktop. Your disc image is only read; nothing is uploaded
and nothing of the game is in this repository or comes with the script.

**First**, get this repository: on GitHub click **Code → Download ZIP** and unzip it (or
`git clone https://github.com/Open-Champions/champions-return-to-arms-re`). Keep the
folder: the program is built inside it, in `local/` - never share that folder, it holds
the translated game.

You need your disc image of the **US release, SLUS-20973, version 2.00** as an `.iso` file
(the script refuses any other: it checks the executable's checksum `4028A55F`).

| | Mac (Apple silicon; Intel not tried) | Windows 10 / 11 (x86-64 or ARM) | Linux (x86-64 or aarch64) |
|---|---|---|---|
| **Run** | double-click `tools/install/install-mac.command` | double-click `tools/install/install-windows.bat` | `sh tools/install/install-linux.sh` in a terminal |
| **Installs if missing (asks first)** | Apple's command line tools (Apple's own prompt), [Homebrew](https://brew.sh), Homebrew's Qt 6 (`qtbase`) | Python 3 (with `winget`, from python.org) and the portable compiler [llvm-mingw](https://github.com/mstorsjo/llvm-mingw/releases) (its official GitHub release, unpacked into `local\toolchain`; nothing installed into Windows) | your distribution's `clang`, C++ library, `python3`, SDL 2 and OpenSSL development packages (apt, dnf, pacman or zypper; `sudo` asks for your password) |
| **Disc image** | a file window | a file window | a file window (zenity / kdialog), else typed |
| **Time** | 1 to 30 minutes | 5 to 40 minutes | 1 to 40 minutes |
| **Then start** | **Champions RTA Native** on the desktop | **Champions RTA Native** on the desktop | **Champions RTA Native** in the applications menu and on the desktop, or `play.sh` |
| **State** | tested from a fresh folder ([issues/native-app.md](issues/native-app.md) 14) | **not yet run on Windows** | tested in a fresh Ubuntu 24.04 container |

- The first time on a Mac, Finder may say the script is from the Internet: right-click it,
  choose **Open**, then **Open** again. In a terminal: `bash tools/install/install-mac.command`.
- Running the script again rebuilds from the same folder (quick: only what changed).
  `--disc FILE` (Mac, Linux) or `-Disc FILE` (Windows) skips the file window.
- The keys, the views (V), the souls-style combat mode (`--combat souls`) and playing in a
  room with other native players are described in
  [issues/native-app.md](issues/native-app.md), [issues/native-souls-combat.md](issues/native-souls-combat.md)
  and section 4. Windows and Linux players start a room from the command line
  (`rta_app --play-host` / `--play-join CODE`, with the room service's address as
  `--service HOST:PORT` or a `service=` line in `server.txt` beside the program; `rta_app --help`).
- **Sharper textures (optional)** are a separate step: an art pack of *your own* textures,
  dumped from your copy of the game and enlarged. Nothing of it comes with the repository;
  how to make one and use it (`--art-pack FOLDER`) is in
  [issues/native-graphics.md](issues/native-graphics.md), section 3 "The art pack".
- What was run on each system, and what was not: [issues/native-app.md](issues/native-app.md)
  (Mac), [issues/native-windows.md](issues/native-windows.md),
  [issues/native-linux.md](issues/native-linux.md).

## 9. If something goes wrong

- **The Mac app shows a bar saying macOS is asking for permission**: answer the question
  macOS put on screen (Allow). The game goes on by itself.
- **"Different patch set" in the room**: someone has an older copy; they download again.
- **Room: the character screens do not come up**: the game is not at its title screen (it
  went to the lobby by itself). Choose **Room → Leave the room**, switch off **Online → Go
  online at start**, quit and open the app again, and host or join once more (section 4,
  step 1).
- **Nothing happens after Host a room or Join a room**: *Not now* was clicked at the name
  question; choose it again and type a name.
- **A game of three or four does not start**: everyone downloads again - older copies had
  a fault there that the current release fixes.
- **The browser version is slow**: use Chrome, keep the tab in front, close other heavy
  tabs.
- Anything else: open an issue in this repository and say which version, which step, and
  what the screen said.
