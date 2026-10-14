# Get the game and play

Updated with each release. **Last update: 2026-10-14.** Current release: fix set
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
| Native build for Mac (the game's code translated to C++, no emulator) | experimental; plays offline and online, joins rooms | [issues/native-recomp.md](issues/native-recomp.md), [issues/native-app.md](issues/native-app.md) |
| Native build for Windows | experimental; builds, never run on a Windows computer | [issues/native-windows.md](issues/native-windows.md) |
| Native build in Godot (first person and other views, new interface, portal) | in development; nothing to download yet | [issues/native-godot.md](issues/native-godot.md), [issues/native-first-person.md](issues/native-first-person.md) |

## 8. If something goes wrong

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
