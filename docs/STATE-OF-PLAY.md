# State of play: four routes to a game

As of 2026-10-12. One page on what can be done today with Champions: Return to Arms
(SLUS-20973 v2.00) through this project, route by route. Every figure names the document
it comes from; that document has the method and the conditions in full.

Read these three limits first. They hold for every line below.

- **Nothing has run on a PlayStation 2 or in PCSX2.** "Ran" on this page means: seen
  running in the [Play!](https://github.com/jpd002/Play-) emulator, or, for route 4, as
  translated code on the host compared with that emulator.
- **No two different computers have played together.** Every pair was two copies of one
  build on one Apple-silicon Mac. Such a pair can show a difference in logic. It cannot
  show a difference in arithmetic, timing or hardware.
- **No session has crossed two networks**, and **no person has played one.** The tests
  drove the game by script. Nobody typed into the new windows, pressed a real controller
  button or listened to the sound.

Evidence words, as the project uses them: **Ran** (seen on the running game), **Executed**
(one function at a time in `tools/ee_emu.py`), **Observed** (read in the executable),
**Inferred**.

| Route | What it is | Plays today | Online today |
|---|---|---|---|
| 1. PCSX2 with the patch file | the stock emulator, this project's patch file, a community lobby server | not tried here | not tried here |
| 2. The Mac app | Play! with this project's changes, packaged; no BIOS file | yes, by test script | two copies on one Mac |
| 3. The browser build | the same core compiled to WebAssembly | first level, offline, by test script | no |
| 4. The native build | the game's code translated to C++ | no: no picture, sound or input yet | no |

Every route needs your own disc image. No route puts anything from the game into this
repository.

## 1. PCSX2 with the patch file

**What it is.** The route this project started with: the game in PCSX2, a replacement
lobby server, and `patches/SLUS-20973_4028A55F.pnach` to remove known causes of "OUT OF
SYNC". The steps are in [online-setup.md](online-setup.md).

**What works.** Nothing has been run in PCSX2 by this project. What exists is the patch
file and the evidence for it from the other emulator:

- The patch file has 37 sections. The suggested set is 19 of them
  ([online-setup.md](online-setup.md), "Suggested patch set";
  `tools/play-net/sections-suggested.txt`). Every section's `author=` line says whether it
  ran on a live game; none says it ran in PCSX2 or on a console.
- A simulated pair of clients passes 16 of 16 core steps and 40 of 40 extended steps
  against the fixed fork of the lobby server (`tools/lobby_e2e_test.py`;
  [lobby-protocol.md](lobby-protocol.md) section 1a). That tests the server, not the game.
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

The three arms together are 6,344,335 ticks. Three things to know about them:

- **The soak's 24 sections are not the suggested 19.** Eighteen of the 19 were in the
  soak. The nineteenth, "no touch handler runs for a prediction copy that walks into
  something", was not (live-rig 22.1 lists the 24 by title); it has runs of its own and no
  soak (FINDINGS V61; [issues/touch-handlers.md](issues/touch-handlers.md) section 6).
  The soak also had six sections that are not in the suggested set.
- Two bytes of local effect state in the player record do differ between machines, in
  68 of the 120 pairs. The soak follows them but does not count them as a divergence; no
  reader in the simulation is known (FINDINGS V63; live-rig 22.4).
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
| 120,039 pictures dumped for the whole game; 118,257 of 132,280 level pictures reached by the tour | levels toured by script; three quarters of one level (`fire3`) not covered | tools/play-net/README.md, "Upscaled art" |

**Missing or not tried** (play-online.md section 8):

- A person at the controls: the windows for the player name and the room code, a real
  controller button, Bluetooth, the sound as heard.
- A lobby server that is not on the same Mac. Two different Macs. Two networks
  (play-online.md section 7 is from reading). More than two players.
- The inventory, shop, skill and map screens, spells, and most levels were not looked at.
- Whether two different Macs stay in step is unknown. Two copies on one Mac agree.
- One known stop: a copy without the sign-in patch shows a network error after *Accept*,
  and cancelling it leaves the game stuck.
- Built and tried on an Apple-silicon Mac only.

## 3. The browser build

**What it is.** Play!'s browser version compiled to WebAssembly, with the same core
changes and the same patch set as the Mac app. A page reads the disc image from the
player's own computer; nothing is installed and the image does not leave the computer.
Source in `tools/play-web/` ([README](../tools/play-web/README.md)); working notes with
every figure in [issues/browser-build.md](issues/browser-build.md).

**What works** (checked by test, table "Checked" in the notes): the build; boot from a
disc image read in place; refusal of a wrong disc; the patch set and the display patches;
a steady picture; keyboard; sound at the title; the memory card and settings kept in the
browser; the title and the first level reached by scripted presses. Offline only.

**Measured** (Chrome 155, one M5 Pro Mac; issues/browser-build.md, "Summary" and
"Measurements"):

| Figure | Conditions |
|---|---|
| 59.95–60.04 frames a second | title screen |
| 59.98 frames a second; machine thread 9.9 ms, video thread 6.2 ms of processor time a frame; 93 with the limiter off | first level, standing, resolution factor 2, load average 9 |
| 59.97 frames a second; 11.6 and 7.4 ms; 76 with the limiter off | the same at factor 1, load average 12 |
| 28–53 frames a second | first level with the Mac busy (load average 80–170) |
| 7–45 frames a second | page hidden or covered |
| 28,700 WebGL calls a frame became 11,700 | first level, after redundant calls were left out |

**The rounding finding.** WebAssembly always rounds floating-point results to nearest.
The Mac app sets the processor to round toward zero, as the console does. **Measured:**
on the same walk the two builds hold the player's height in bits that differ in the last
place (issues/browser-build.md, "Can a browser player and a desktop player share a
game?"). A shared game between the two was **not run**. What it would do is taken from
the rig, where one of two linked machines was forced to round to nearest: the game's own
out-of-sync check tripped 7 to 113 ticks after anyone moved (FINDINGS V15; live-rig 8.3).
So a browser player and a native player cannot share a game as the builds are. Browser
players among themselves should agree (Inferred from the WebAssembly specification; not
run).

**Missing.** Online play: a browser has no raw sockets, so a relay is needed; it is
designed in the notes and not built. A controller, the file dialog, full screen and the
sound have not been tried by a person. Nothing beyond the first level. Safari and Firefox
are untested. A build from an empty directory by the script was not run.

## 4. The native build

**What it is.** A feasibility test of static recompilation: the executable's MIPS code
translated once to C++ and compiled for the host, with a runtime in place of the console.
Translator, runtime and tests are in `tools/recomp/`; the generated code is derived from
the game and stays out of the repository. Notes:
[issues/native-recomp.md](issues/native-recomp.md).

**What works.**

- The translator covers all of the code: 757,702 instruction slots, none without a
  translation; all 46 generated files compile (native-recomp, step 1).
- A runtime runs the game's frame loop without picture or sound (step 3).

**Measured** (issues/native-recomp.md):

| Figure | Conditions | Where |
|---|---|---|
| 7,431 of 7,732 functions compared, 0 differ, 301 could not be driven | one function at a time against `tools/ee_emu.py`, 12 inputs each | step 2 |
| 40,991 calls replayed, 0 differ | calls made by 16 of the project's 17 reference-model tests (the seventeenth needs extracted files) | step 2 |
| 2,005 consecutive frames identical in every compared value, the whole object pool included | translated code against the original in the rig; first level, resumed from a saved session, no input | step 4 |
| 987 of 33,554,432 bytes differ at the end; 0 in the object pool, the heap and the code | the same run | step 4 |
| 10.8 times real time on one core (22 with the renderer back end replaced); the emulator core 0.6 to 1.04 | first level, no input, by processor time | "Speed" |

**Missing.** It is not playable. From power-on the translated game stops at the first
load of an I/O-processor module. Not built: disc, controller and memory-card services, a
renderer, sound, the network, a Windows build. Not compared: a level with fighting,
input, a level change, a network session. The agreement shown is with the emulator, not
with a console (native-recomp, step 5).

## Mixing routes

The game is lockstep: every machine computes the whole game itself, so every player in a
game needs the same arithmetic and the same patch set.

- Mac app with Mac app: agrees on one Mac. Not run between two Macs.
- Mac app with browser build: cannot share a game as built (the rounding finding).
- Any of these with PCSX2 or a console: not run. Expect drift until someone shows
  otherwise ([online-setup.md](online-setup.md), "Settings every player must match";
  [issues/float-divergence.md](issues/float-divergence.md)).

## Where to help

The open items of every route are collected in
[CONTRIBUTING.md](../CONTRIBUTING.md#what-to-work-on).
