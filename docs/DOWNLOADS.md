# Get the game and play

Updated with each release. **Last update: 2026-10-21** (section 8: **Champions Setup**, one file to double-click on Mac, Windows and Linux, that builds the native version from your own disc). Current release: fix set
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
handed out: **every player translates it from their own disc**, on their own computer.

### 8.1 Champions Setup: one file, double-click it

**You need your own disc image of Champions: Return to Arms (US, v2.00). Download the setup
for your computer, double-click it, it finds your disc image and does the rest.**

The setups are on the same private page as the other downloads (section 1: the link comes
from the person who invited you), or you make them yourself from this repository (below).

| | Mac | Windows 10 / 11 | Linux |
|---|---|---|---|
| **Download** | `Champions-Setup-Mac.zip` (about 65 MB): the app **Champions Setup** | `Champions-Setup-Windows.exe` (about 7 MB) | `Champions-Setup-Linux.zip` (about 60 MB): `Champions-Setup-Linux.sh` |
| **First start** | macOS cannot check the app: **Done**, then **System Settings → Privacy & Security → Open Anyway** | "Windows protected your PC": **More info → Run anyway** (no administrator rights needed) | double-click the `.sh` (or `bash Champions-Setup-Linux.sh`) |
| **Fetches by itself** (official sources, pinned versions, size and SHA-256 checked) | Apple's command line tools (Apple's own window: one click on **Install**); Qt 6.11.3 from download.qt.io (30 MB) unless Homebrew's Qt is there | Python 3.13.9 ("embeddable", python.org, 10 MB) and the compiler llvm-mingw 20261006 (its GitHub release, 180 MB) into `%LOCALAPPDATA%\Champions\tools` - nothing is installed into Windows | the compiler and the SDL 2, OpenSSL and EGL development files from your distribution (apt, dnf, pacman, zypper; your system asks for your password) |
| **Then** | **Champions** and **Champions Godot** in `~/Applications` and on the desktop | **Champions** on the desktop and in the Start menu | **Champions** and **Champions Godot** in the applications menu and on the desktop |
| **Ran** (2026-10-21) | from a fresh home folder: found the image in Downloads, built native and Godot (with Homebrew's Qt, and again with the downloaded official Qt), both started; not yet: the first-start prompts of a downloaded copy, Apple's tools installed by it | from a fresh user folder with a space in its name, in a Windows 11 ARM virtual machine: found the image in Downloads, fetched Python and llvm-mingw, built in 4 minutes, made both shortcuts and started the game (the machine has no OpenGL driver: with Mesa beside it the game shows its first screen); not yet: an Intel or AMD PC | in a fresh Ubuntu 24.04 container (64-bit ARM, terminal, as root): installed the packages, found the image, built native and Godot's library in 7 minutes; the program shows its first screen headless; not yet: the zenity / kdialog window, pkexec, x86-64 |

What every setup does: it looks for your disc image (an `.iso` file) in Downloads, on the
Desktop, in Documents and on other drives - on a Mac also in
`~/Library/Application Support/Play-RTA/` - and takes the one whose `SLUS_209.73` is the US
v2.00 executable (checksum `4028A55F`), whatever the file is called; if there is none it opens
one file window. Then a progress bar while it copies the executable out of the image,
translates it and builds the program (15 to 45 minutes; the computer stays usable), puts the
launchers in place and starts **Champions**. Starting a setup again later updates the build
(quick). Everything it makes stays in your own folders:
`~/Library/Application Support/Champions` (Mac), `%LOCALAPPDATA%\Champions` (Windows),
`~/.local/share/champions` (Linux) - never share those folders, they hold the translated game.

**What is in a setup** - and what never is: the project's source code (this repository), the
setup's own small program, the Godot version as exported without any game library (Mac and
Linux; the Windows Godot version has no game library yet), and for the private page a
`setup.ini` with the room service's address. **Never** a disc image, the game's executable, a
translation of it, a program or library built from it, or any of the game's data.
`tools/install/setup/build_setups.py` checks every file of every setup, also inside the
archives in it, for disc images, PS2 executables, pieces of the game's executable, translated
code and the translation's function table, and writes the list of what is in it beside it.

**Make the setups yourself** (on a Mac with Apple's command line tools and Homebrew's
`mingw-w64`; nothing is downloaded):

```
python3 tools/install/setup/build_setups.py          # local/dist-setups/: the three setups and their contents lists
python3 tools/install/setup/build_setups.py --service HOST:PORT   # with your room service as their default
```

The Godot version comes from `tools/godot/build.py export` (macOS, Linux); without an export
the setups are made without it.

### 8.2 The scripts, in a copy of this repository

The scripts below do the same from a copy of this repository, in a terminal or with a double-click.
One script per system does
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
| **State** | tested from a fresh folder ([issues/native-app.md](issues/native-app.md) 14) | run from a fresh folder in a Windows 11 ARM virtual machine ([issues/native-windows.md](issues/native-windows.md)) | tested in a fresh Ubuntu 24.04 container |

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
- **Your own boss music (optional)**: put your own music files in `<data>/music/boss/`
  (`<data>` is the program's data folder, the one with its memory cards in `card/`; `.ogg`,
  `.mp3` or `.wav`). During a boss fight one of them fades in over the game's music, which
  comes back after the fight. Nothing comes with the program; `--boss-music off` or a
  `music.boss = off` line in `settings.txt` switches it off
  ([issues/native-hud.md](issues/native-hud.md) section 13).
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
