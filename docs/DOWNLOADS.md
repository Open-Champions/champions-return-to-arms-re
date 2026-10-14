# Get the game and play

Updated with each release. **Last update: 2026-10-13.** Current release: fix set
`9ac29719` (31 sections). How complete each part is: [PROGRESS.md](PROGRESS.md).

## 1. What you need

1. **The link.** One private link leads to both versions below. You get it from the person
   who invited you to play. (Not invited by anyone? See section 5.)
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
4. Type a **player name** when the app asks. That is your name on the server; there is no
   password to remember.
5. In the menu bar: **Online → Host a game** (you get a room code to read out), or
   **Online → Join a game...** and type the code a friend gave you.

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

## 4. Playing together

- One player hosts and reads the room code out; the others join with it. Two to four
  players.
- Mac players and browser players can be in the same game.
- **Everyone needs the same fix set.** Both versions behind the link always carry the same
  one (now `9ac29719`); if a friend's copy is older, the room says so before the game
  starts - they download again.
- More about what happens online, your account and your character:
  [play-online.md](play-online.md).

## 5. Why the link is not here, and how to build it yourself

The ready-made versions behind the link are set up for one private server and carry a
small sign-in file that is not part of this repository. So there is no public download
button. Everything else is here, and you can build each version yourself with your own disc:

| Version | State | Build it |
|---|---|---|
| Mac application | released | [tools/play-net](../tools/play-net/README.md): `build.sh`, then `package.sh` |
| Browser version | released; further work paused | [tools/play-web](../tools/play-web/README.md) |
| Lobby server (needed for online play) | running | [online-setup.md](online-setup.md) |
| Native build for Mac (the game's code translated to C++, no emulator) | experimental; plays offline and online | [issues/native-recomp.md](issues/native-recomp.md), [issues/native-app.md](issues/native-app.md) |
| Native build for Windows | experimental; builds, never run on a Windows computer | [issues/native-windows.md](issues/native-windows.md) |
| Native build in Godot (first person and other views, new interface, portal) | in development; nothing to download yet | [issues/native-godot.md](issues/native-godot.md), [issues/native-first-person.md](issues/native-first-person.md) |

## 6. If something goes wrong

- **The Mac app shows a bar saying macOS is asking for permission**: answer the question
  macOS put on screen (Allow). The game goes on by itself.
- **"Different patch set" in the room**: someone has an older copy; they download again.
- **A game of three or four does not start**: everyone downloads again - older copies had
  a fault there that the current release fixes.
- **The browser version is slow**: use Chrome, keep the tab in front, close other heavy
  tabs.
- Anything else: open an issue in this repository and say which version, which step, and
  what the screen said.
