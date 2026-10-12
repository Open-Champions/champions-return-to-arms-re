# State of play: four routes to a game

As of 2026-10-12, afternoon. One page on what can be done today with Champions: Return to
Arms (SLUS-20973 v2.00) through this project, route by route. Every figure names the
document it comes from; that document has the method and the conditions in full.

Read these three limits first. They hold for every line below.

- **Nothing has run on a PlayStation 2 or in PCSX2.** "Ran" on this page means: seen
  running in the [Play!](https://github.com/jpd002/Play-) emulator, or, for route 4, as
  translated code on the host compared with that emulator.
- **No two different computers have played together.** Every pair was on one
  Apple-silicon Mac: two copies of one build, or two of this project's builds side by
  side (the browser build and the Mac app; the native build and the emulator). Two copies
  of one build can show a difference in logic and none in arithmetic. Two builds on one
  processor show the difference in arithmetic between those two builds. Neither shows a
  difference in timing or hardware.
- **No session is on record as having crossed two networks or been played by a person.**
  The tests drove the game by script. No document reports anybody typing into the new
  windows, pressing a real controller button or listening to the sound.

Evidence words, as the project uses them: **Ran** (seen on the running game), **Executed**
(one function at a time in `tools/ee_emu.py`), **Observed** (read in the executable),
**Inferred**.

| Route | What it is | Plays today | Online today |
|---|---|---|---|
| 1. PCSX2 with the patch file | the stock emulator, this project's patch file, a community lobby server | not tried here | not tried here |
| 2. The Mac app | Play! with this project's changes, packaged; no BIOS file | yes, by test script | two copies on one Mac |
| 3. The browser build | the same core compiled to WebAssembly | first level, by test script | two pages on one Mac, through a relay; a private page is deployed |
| 4. The native build | the game's code translated to C++, in a window of its own | two levels, by test script, with picture, sound, input, save and load | without a lobby, on one Mac, with itself and with the emulator; through the lobby: in progress |

Every route needs your own disc image. No route puts anything from the game into this
repository.

## 1. PCSX2 with the patch file

**What it is.** The route this project started with: the game in PCSX2, a replacement
lobby server, and `patches/SLUS-20973_4028A55F.pnach` to remove known causes of "OUT OF
SYNC". The steps are in [online-setup.md](online-setup.md).

**What works.** Nothing has been run in PCSX2 by this project. What exists is the patch
file and the evidence for it from the other emulator:

- The patch file has 41 sections. The suggested set is 26 of them, 90 patched words
  ([online-setup.md](online-setup.md), "Suggested patch set";
  `tools/play-net/sections-suggested.txt`; the word count is from
  [issues/native-app.md](issues/native-app.md), "The fix set"). Each section's `author=`
  line says whether its fault and its fix were seen on a live game; none says PCSX2 or a
  console. A section that was only switched on in the soak below, without its fault being
  reproduced, still reads "untested on a running game" there.
- A simulated pair of clients passes 16 of 16 core steps and 40 of 40 extended steps
  against the fixed fork of the lobby server (`tools/lobby_e2e_test.py`;
  [lobby-protocol.md](lobby-protocol.md) section 1a), also after the server's hardening
  of 2026-10-12 ("The lobby server" below). That tests the server, not the game.
- The real game has been through the whole lobby path against that server — terms,
  account, log in, characters, host, join, launch, play — but in Play!: on the rig
  (FINDINGS V49; live-rig section 19) and in the Mac app (route 2).

**Measured, on the two-machine rig in Play!** ([issues/live-rig.md](issues/live-rig.md)):

| Figure | Conditions | Source |
|---|---|---|
| 7 of 12 arena fights diverged | no patch section; two real-character builds; 165,225 ticks | FINDINGS V17, V21; live-rig 9.3, 10.3 |
| 0 of 120 pairs differed in any shared value compared (seed, positions, hit points, bags, statistics, equipment and the rest listed in live-rig 22.1); 5,121,702 ticks; no out-of-sync flag | 24 fix sections on; six character builds; 27 levels; 30,000–60,000 frames a pair; 63 of the pairs with delay, jitter and loss or an outage between the machines | FINDINGS V62; live-rig 22.1, 22.2 |
| 24 pairs, 1,027,302 ticks: one differing tick, a kick from the pause menu | the same 24 sections plus the skeleton section | FINDINGS V62; live-rig 22.3 |
| 8 pairs, 195,331 ticks: no difference, no checksum failure, 712 saves accepted | launched through the real lobby path, 24 sections | FINDINGS V62; live-rig 22.6 |

The three arms together are 6,344,335 ticks. Five things to know about them:

- **The soak's 24 sections are not the suggested 26.** Eighteen of the 26 were in the
  soak (live-rig 22.1 lists the 24 by title). Eight were not, and none of the eight has
  been in a soak: "no touch handler runs for a prediction copy that walks into something",
  which has runs of its own (FINDINGS V61;
  [issues/touch-handlers.md](issues/touch-handlers.md) section 6), and seven that came
  from [issues/online-quality.md](issues/online-quality.md) on 2026-10-12, each with rig
  runs of its own there: the silence time-out (its section 1.7), the three lag sections
  LAG-2, LAG-3 and LAG-4 (section 2), and the three of sections 3.1, 3.2 and 4.2. The
  soak also had six sections that are not in the suggested set.
- **The set of 26 has no long run behind it as a set.** With it one existing pair script
  (`pair-arena.rig`) no longer reaches its cutscene, on an emulator pair and on a native
  pair alike; whether that comes from the newer sections or from the script is not
  established ([issues/native-net.md](issues/native-net.md), "The known desyncs").
- Two bytes of local effect state in the player record do differ between machines, in
  68 of the 120 pairs. The soak follows them but does not count them as a divergence; no
  reader in the simulation is known (FINDINGS V63; live-rig 22.4).
- Four pairs ended early: one machine dropped the other while its own pause menu was
  open (three pairs of the first arm, one of the second; live-rig 22.3). The three of the
  first arm were run again with break points: the random input had chosen the host's own
  "kick players" entry. It was not a time-out, and an open menu stops neither the network
  nor the simulation ([issues/online-quality.md](issues/online-quality.md) 1.1 to 1.3).
  A kick ends a session without the machines having disagreed before it. The one
  automatic drop is a silence time-out: a machine that stands completely still for 15
  seconds is dropped (1.4, 1.5); the suggested set now makes that 24 seconds (1.7).
- What the soak cannot see is listed in live-rig 22.8: state outside the player records
  unless it reaches the shared seed or a player, anything that needs longer than a pair
  lasts (17 minutes of play at most), and every difference between two real machines.

**Missing.** A run in PCSX2 or on a console of any of it: the emulator's DNS override,
the sign-in step, two clients finding each other, the patch set. The sign-in step cannot
succeed as shipped (Sony's servers are gone); online-setup.md says how it can be
answered or skipped. The developer LAN start (boot argument `--net`, FINDINGS V6) was not
tried in PCSX2. [VALIDATION.md](VALIDATION.md) is a test procedure for two PCSX2 clients;
it has not been executed.

## 2. The Mac app

**What it is.** The Play! emulator's desktop application with this project's changes:
the game's own network stack behind a built-in network, the suggested patch set applied
while it runs, and repairs to the emulator's picture, speed and sound for this game.
Apple-silicon Mac; no PlayStation 2 BIOS file. Source, patch and scripts are in
`tools/play-net/`; how to play is in [play-online.md](play-online.md); what was repaired
and how it was checked is in [tools/play-net/README.md](../tools/play-net/README.md).

**What works** (Ran, driven through the control socket by test scripts):

- Power-on, title, menus, character creation, the lobby screens, the first level, one
  dungeon level and the arena.
- A controller with nothing to set up, the keyboard beside it.
- Going online in one step: the application presses its own way from power-on to the
  lobby's game list and makes the account. Host and Join by a four-letter room code.
- Two copies on one Mac, with the lobby server on the same Mac: hosted, joined, launched
  and played in step.
- A warning when two players have different patch sets.
- A switch that makes the application compute as a browser copy does, which it sets by
  itself in the room when it hears such a copy ("Mixing routes" below).
- Textures written out and replaced by files of any size, and a pipeline that enlarges
  the game's art (`upscale.py`, `disctex.py`, `leveltour.py`).
- Packaging as an application that needs no terminal (`package.sh`).

The sign-in step that needs Sony's servers is skipped by a local sign-in patch, which is
not part of this repository (play-online.md section 2).

**Measured** (one M5 Pro Mac):

| Figure | Conditions | Source |
|---|---|---|
| 60 frames a second; machine thread 6–9 ms, video thread 8–12 ms of a 16.7 ms frame | resolution factor 4; first level, one dungeon level, the arena | play-online.md section 8 |
| 17–20 frames a second | the same scene before the repairs | tools/play-net/README.md, table of faults |
| 60.0 frames a second at factors 1, 4 and 8 | first level | tools/play-net/README.md, table of faults |
| consecutive pictures byte-identical | memory-card screen, steady picture on | tools/play-net/README.md, table of faults |
| 82–104 ms from a press to the first movement of an attack | first level, offline; the game's own delay, the emulator adds no queued frame | play-online.md section 5; `tools/play-net/latency.py` |
| sound ran dry 0 times in five minutes (20 times as Play! does it) | first level, walking and attacking; counted, not listened to | tools/play-net/README.md, "Sound" |
| lobby's game list reached 30.4 s after launch; 28.3 s with the saved login | background test copies, lobby server on the same Mac | tools/play-net/README.md, "One-step online" |
| host in its room 43 s after launch, joiner 53 s after its own, no press by anybody | two test copies on one Mac, remembered characters, load average 60–140 | play-online.md section 8 |
| 4,000 lockstep frames, both machines agreeing on positions and hit points, no checksum failure | two copies on one Mac, walking and fighting | play-online.md section 8 |
| 650 frames in step after Host and Join by code | two copies on one Mac | play-online.md section 8 |
| 339 texture files, the same 339 names and bytes in two runs | power-on to the first level and 40 s of walking | tools/play-net/README.md, "Texture dump and replacement" |
| 60.00 frames a second with a 4× art pack; 1.39 GB of video memory | first level | tools/play-net/README.md, "Upscaled art" |
| 120,039 pictures dumped for the whole game, 118,257 of them level pictures (the level files hold 132,280); 2,171 more from later tours of effects, skills and the level `fire3` | levels toured by script; about a sixth of `fire3`'s 3,655 pictures not drawn. The enlarged pack made from them was a third complete when it was last recorded (issues/visual-check.md) | tools/play-net/README.md, "Upscaled art" |

**Missing or not tried** (play-online.md section 8):

- A person at the controls: the windows for the player name and the room code, a real
  controller button, Bluetooth, the sound as heard.
- A lobby server that is not on the same Mac. Two different Macs. Two networks
  (play-online.md section 7 is from reading). More than two players.
- Looked at since, by one visual check (stable build at resolution factor 4 with the
  enlarged art, offline; [issues/visual-check.md](issues/visual-check.md)): the new-game
  menus, character creation, the HUD, the pause menu, the inventory pages, the skill and
  spell-book screens, the shop lists, dialogue, level-up, the save-point and memory-card
  screens showed no fault. Ten faults were confirmed elsewhere, one of them high: noise
  over fire and around the lava golems, an emulator fault that is fixed in the working
  build. Not reached by that check: death, a chest or a door opening, credits and end
  films, the player-against-player, medal and bonus levels, the spells of ten of the
  twelve class choices.
- Whether two different Macs stay in step is unknown. Two copies on one Mac agree.
- One known stop: a copy without the sign-in patch shows a network error after *Accept*,
  and cancelling it leaves the game stuck.
- Built and tried on an Apple-silicon Mac only.

## 3. The browser build

**What it is.** Play!'s browser version compiled to WebAssembly, with the same core
changes and the same patch set as the Mac app. A page reads the disc image from the
player's own computer; nothing is installed and the image does not leave the computer.
A page has no sockets of its own, so online it reaches the lobby server and the other
players through a relay program that runs on a server. Source in `tools/play-web/`
([README](../tools/play-web/README.md)); working notes with every figure in
[issues/browser-build.md](issues/browser-build.md) (the build and online play),
[issues/browser-perf.md](issues/browser-perf.md) (the speed patch) and
[issues/mixed-arithmetic.md](issues/mixed-arithmetic.md) (a game shared with the Mac
app).

**What works** (checked by test; browser-build, table "Checked" and "Online play from a
browser: built"): the build; boot from a disc image read in place; refusal of a wrong
disc; the patch set and the display patches; a steady picture; keyboard; sound at the
title; the memory card and settings kept in the browser; the title and the first level
reached by scripted presses. Online between browser players through the relay
(`tools/play-web/relay/`): going online in one step, Host and Join by code as in the Mac
app, two pages hosted, joined, launched and in step.

**Deployed.** As of this date the page stands at a private address with online play and
the speed patch below. That is the project coordinator's statement of 2026-10-12. No
document in this repository records the deployment or a test of the deployed page:
browser-build, "Putting it on a server", still describes the step as prepared and not
done, and every figure below was taken on one Mac.

**Measured** (Chrome 155, one M5 Pro Mac):

| Figure | Conditions | Source |
|---|---|---|
| 59.95–60.04 frames a second | title screen | browser-build, "Summary" |
| 59.98 frames a second; machine thread 9.9 ms, video thread 6.2 ms of processor time a frame; 93 with the limiter off | first level, standing, resolution factor 2, load average 9 | browser-build, "Summary" |
| 59.97 frames a second; 11.6 and 7.4 ms; 76 with the limiter off | the same at factor 1, load average 12 | browser-build, "Summary" |
| 28–53 frames a second | first level with the Mac busy (load average 80–170) | browser-build, "Summary" |
| 7–45 frames a second | page hidden or covered | browser-build, "Summary" |
| 28,700 WebGL calls a frame became 11,700 | first level, after redundant calls were left out | browser-build, "Summary" |
| With the speed patch (`perf.patch`): 226.9 million instructions a frame instead of 287.1 (21 % fewer); machine thread 7.85 ms instead of 9.23 and 10.19, video thread 5.08 ms instead of 5.64 and 6.18 | first level, standing, factor 2, load average 8–16; one run, the unchanged build twice; the patch as it was before it was moved onto a later change of the Mac app's patch | browser-perf, "Summary" |
| 60.04 frames a second with the speed patch where the unchanged build gave 53.2 and 48.2; 34.6 where it gave 27.2 and 24.7 | the same scene on a stand-in for a computer half as fast, and a quarter as fast; no real slower computer was tried | browser-perf, "Summary" |
| The speed patch changes neither picture nor simulation: three random seeds and the player's position identical at every one of 4,984 frames, 156 checksums each of three memories, six pictures byte for byte | a tick-exact replay: power-on, title, a new game, the first level with walking, two strikes and a jump | browser-perf, "Summary" |
| 1,387 consecutive lockstep frames with every sync hash equal on both pages (1,122 distinct values); host in its room 39 s after *Host a game* at power-on, joiner 43 s after *Join*, first level 14 s after *Start Game*, no press by anybody | two Chrome pages on one Mac, lobby server and relay on the same Mac, saved login and remembered character, load average 41 | browser-build, "Tried on one Mac" |
| 1,451 consecutive frames, all hashes equal | the same with the later build, load average 52 | browser-build, "Tried on one Mac" |
| a datagram from one session of the relay to another and one back: median 0.33 ms | the relay's own test on that Mac, load average 105 | browser-build, "The relay path, measured" |

**The rounding finding, and what was done about it.** WebAssembly always rounds
floating-point results to nearest and keeps tiny numbers. The Mac app sets the processor
to round toward zero and to take tiny numbers as zero, as the console does. With one
machine of each kind in a game the positions differ in the last bit on the first step
(mixed-arithmetic section 3.2: 3 rig pairs of 3 with input; before that FINDINGS V15,
live-rig 8.3). So a page and the Mac app cannot share a game as each computes by
default. The Mac app can now compute as a browser does ("browser arithmetic"), and that
half is proven (mixed-arithmetic, "Summary", section 3 and "Rig totals"):

| Figure | Conditions |
|---|---|
| 12,400 frames and 8,810 frames, 224 bytes of game state read in every frame: no byte differs | the browser build in Chrome 155 against a rig machine in browser arithmetic, the same recorded input from power-on; walking, fighting, 8 deaths, four level changes in the first session, another level and both sticks in the second; one player, offline |
| the same input with the rig machine in the Mac app's own arithmetic: differs from frame 2741 | the first of those sessions |
| 54 pairs, 312,989 lockstep ticks, no pair with a difference in a shared column | two rig machines both in browser arithmetic, 6,000 frames of random input each, four levels, part of the pairs with delay, jitter and loss between the machines |
| 506 and 436 lockstep frames in the first level and 500 after a level change, every sync hash equal | two copies of the Mac app in one room on one Mac: one fixed to browser arithmetic, the other changing to it by itself when it heard the first (section 5) |

A page and the Mac app in one game has **not been run**; "Mixing routes" below says what
is still missing. Browser players among themselves agree on one Mac (the two-page rows
of the first table); two different processors were not tried, and an x86 browser, where
one kind of result can differ, was not available (mixed-arithmetic section 6). (The
browser notes call the Mac app the "desktop" or "native" build; on this page "native
build" means route 4 only.)

**Missing** (browser-build, "Not tried, not built", unless another source is named).

- Any record of the deployed page in use: two players in different places, more than two
  players, a level beyond the first, a long session.
- A page and the Mac app in one game.
- A session that survives a lost connection to the relay. A browser closes a page's
  connections when the computer sleeps, and the online game is lost with them (seen three
  times on the test Mac; "What a lost connection does").
- Every datagram of a browser player goes through the relay and back out, on a WebSocket
  connection, so one lost packet holds back those behind it. WebTransport was not built.
- All browser players reach the lobby server from the relay's one address, so they share
  what the hardened server allows one address: 16 connections, and 20 new accounts and
  then one every three minutes (**Inferred** from `tools/play-web/relay/README.md` and
  the server's `SECURITY.md`; not run).
- A controller, the file dialog, full screen and the sound have not been tried by a
  person.
- Safari and Firefox are untested. The speed patch links translated blocks with tail
  calls; its fallback for a browser without them was not run (browser-perf, "Not shown").
- A build from an empty directory by the script was not run.

## 4. The native build

**What it is.** Static recompilation: the executable's MIPS code translated once to C++
and compiled for the host, with a runtime in place of the console. Since 2026-10-12 an
application puts the translated game, a renderer and a sound library into one window
(`tools/recomp/app/`). Translator, runtime and tests are in `tools/recomp/`; the
generated code is derived from the game and stays out of the repository. Notes:
[issues/native-recomp.md](issues/native-recomp.md) (translator and runtime),
[issues/native-app.md](issues/native-app.md) (the application),
[issues/native-net.md](issues/native-net.md) (the network).

**What works** (Ran by test script in the window program; native-app, "State" and
sections 1 to 6, unless another source is named).

- The translator covers all of the code: 757,702 instruction slots, none without a
  translation; all 46 generated files compile (native-recomp, step 1).
- From power-on with a picture: the memory-card screens, the publisher's logo, the title
  and its menus, character creation, the loading screen and the first level. Each was
  laid beside the emulator's picture of the same script and is the same, except the two
  films, which are not shown.
- Play in the first level and in a level with monsters: walking, striking, casting, a
  fight, the pause menu and its load screen, a level change.
- Input: the keyboard (power-on to the first level by key events alone) and a game
  controller, tested with one made by the program, not with a real one.
- Sound through the Mac's sound device.
- Save and load: a save made through the game's own request, loaded again from the
  title menu after a restart. The emulator build loads the same card.
- The network of the game's own lockstep code, in a headless program
  (native-net, "Status"): the developer LAN start (boot argument `--net`) from power-on,
  between two native instances and between a native instance and an emulator machine of
  the rig.

**Measured** (one Apple-silicon Mac shared with other work; the load average is given
where the source gives it):

| Figure | Conditions | Where |
|---|---|---|
| 7,431 of 7,732 functions compared, 0 differ, 301 could not be driven | one function at a time against `tools/ee_emu.py`, 12 inputs each | native-recomp, step 2 |
| 40,991 calls replayed, 0 differ | calls made by 16 of the project's 17 reference-model tests (the seventeenth needs extracted files) | native-recomp, step 2 |
| 2,005 consecutive frames identical in every compared value, the whole object pool included | translated code against the original in the rig; first level, resumed from a saved session, no input | native-recomp, step 4 |
| 987 of 33,554,432 bytes differ at the end; 0 in the object pool, the heap and the code | the same run | native-recomp, step 4 |
| 10.8 times real time on one core (22 with the renderer back end replaced); the emulator core 0.6 to 1.04 | first level, no input, by processor time | native-recomp, "Speed" |
| In step with the emulator with picture and sound attached: front end 1,383 ticks, every simulation column identical; first level 99 ticks, identical but for the player record at tick 7; a level with a fight 5,410 ticks, every simulation column identical, the object pool different in 27 consecutive ticks | the unpatched game in the application, picture drawn off screen, sound device silent, given the controller bytes of the rig's log; 7,904 fields, load average 50–110 | native-app, section 3 |
| 4,603 pictures in 83.6 s; 97.1 % of the intervals between them exactly 1/60 s | a play session in a window of 480 × 360 points on a 120 Hz display, load average 21–32 | native-app, section 3 |
| 2,413 fields (40.3 s of the machine's time) from power-on to the first level playable; 2,830 with the emulator's loading times | by the boot script | native-app, section 5 |
| native with native in one game: 296,778 lockstep ticks (83 minutes of play), no shared column differs; 296,691 with the fix set, the same | LAN start from power-on into the arena fight, random input, delay 3, jitter 4, loss 6 % between the machines; load average 9 and 7 | native-net, "Speed and soak" |
| native with the emulator in one game: 21,141 ticks, no shared column differs | the arena fight, delay 4, jitter 4, loss 8 % | native-net, "From power-on" |
| the known desyncs K2, K3, E9 and D26 appear at the documented ticks without fixes and are gone with the fix set built in | native pairs, D26 and K2 also native with emulator; the fix set as it stood that morning (its first 20 sections) | native-net, "The known desyncs" |
| 1,387 ticks a second (23 times real time) idle, 927 (15 times) in the arena fight | two native instances in a lockstep game, unthrottled; load average 13 and 16 | native-net, "Speed and soak" |

**Missing** (native-app, "State", sections 4, 8 and 10, unless another source is named).

- **Online through the lobby is in progress.** The network above runs in a headless
  program without a lobby; the application links none of it, and the lobby path (TCP,
  name look-up, network configuration, two relocatable modules) is not done in the notes
  (native-net, "Status" and "What the lobby path needs").
- Films are not shown: the developer's logo film and the intro film end at their first
  picture.
- Nobody listened to the sound. It drops out for tens of milliseconds at a time while a
  level loads (51 times, 301 ms in all, in an 84 s session).
- No real controller was connected, and no person pressed a key.
- Water, trails, heat haze and floor decals: no level that shows them was visited. One
  drawing fault seen in the fight, a pole from the player to the corner of the screen,
  was traced to the vector unit's arithmetic and is gone (section 10.1; the "State"
  paragraph of 13:15 was written before that).
- Two differences from the rig that nobody has explained: the player record at one tick
  of the first level, and the object pool in 27 consecutive ticks of the fight.
- A save made by the emulator build loaded here: not tried. A Windows build: not built.
  The application runs from its build directory.
- The agreement shown is with the emulator, not with a console (native-recomp, step 5).

The section "Status for other agents" at the top of native-recomp and the "State"
section of native-app are kept current by their authors and go before this page where
they differ.

## The lobby server

Routes 1 to 3 meet in one replacement lobby server, a fork with a repository of its own
([online-setup.md](online-setup.md)). On 2026-10-12 it was hardened for a server that
strangers can reach. What follows is from that repository's `SECURITY.md` and its
`FIXES.md`, sections 21 to 30.

- **Protected.** A malformed message does not stop the server. A request acts for the
  account its connection logged in as, and a connection that has not logged in can only
  connect, create an account, log in and ask for the rules and the statistics. A
  character can be written by its owner and by the consoles in a game with its owner.
  Passwords are stored as PBKDF2-HMAC-SHA256 with 50,000 rounds. One address may hold 16
  connections, has a request budget (50 units a second, 400 at once), 40 password checks
  and one more every 3 seconds, 20 new accounts and one more every 3 minutes; the server
  takes 512 connections in all and its database 1,024 MB.
- **How it was checked** (FIXES.md, "The checks of 21 to 30"; all against instances of
  its own on one machine): a fuzzer sent 2.28 million messages in four runs to a build
  with the address and undefined-behaviour sanitizers, without a report; ten abuse checks
  pass, seven of which fail on the tree before the hardening; five limit checks pass; the
  protocol test passes 16 of 16 and 40 of 40. Not compiled on Linux or with MSVC by those
  checks.
- **Not protected, and it cannot be from the server.** Nothing on the wire is secret:
  the protocol's one key is on every game disc, so anybody who can see a player's traffic
  can read the password. A player in your game can overwrite the character you are
  playing, because the game lets every console of a party save every member's character.
  Accounts are free, and a password cannot be changed or recovered. IPv4 only.

## Mixing routes

The game is lockstep: every machine computes the whole game itself, so every player in a
game needs the same arithmetic and the same patch set.

- Mac app with Mac app: agrees on one Mac. Not run between two Macs.
- Browser page with browser page: agrees on one Mac, through the relay (route 3). Not run
  between two computers.
- Mac app with browser build: not run, and in two halves. The arithmetic half is
  proven: the Mac app in browser arithmetic matches the browser build byte for byte over
  two recorded sessions, and it changes to that arithmetic by itself in the room (route
  3; [issues/mixed-arithmetic.md](issues/mixed-arithmetic.md)). The network half is in
  progress: the relay as first built carries nothing to or from a player outside it. A
  relay that opens a path to an outside player whom the lobby server named, or to one
  both sides have sent to, is written and passes its self-test (30 checks); the proof
  with one application copy and one page was still to do when the notes were written
  ([issues/browser-build.md](issues/browser-build.md), "Mixed games"). A game in browser
  arithmetic no longer rounds as a console does (mixed-arithmetic section 6).
- Native build with the emulator: in step in every run of the developer LAN start, up to
  21,141 ticks (route 4). Through the lobby, or with the Mac app or a page: not run.
- Any of these with PCSX2 or a console: not run. Expect drift until someone shows
  otherwise ([online-setup.md](online-setup.md), "Settings every player must match";
  [issues/float-divergence.md](issues/float-divergence.md)).

## Where to help

The open items of every route are collected in
[CONTRIBUTING.md](../CONTRIBUTING.md#what-to-work-on).
