# The Mac application in our own rooms: one game with the native program

Started 2026-10-14. The owner: "Anybody should be able to play with anybody." This file is
the work that puts the Mac application (Play! with this project's changes, `tools/play-net`)
into the rendezvous service of `docs/issues/native-rendezvous.md`, so that application
players and native players sit in one room and play one lockstep game - no lobby, no
account, no password, and **without the sign-in patch**. Section 7 of
`native-rendezvous.md` was the design; what was found on the way changed one part of it
(section 2.4 here). Every claim says **Ran** (run on this Mac) or **Read** (read in the
game's code or in a source named).

## STATE (rewritten at every step; read this first after a stop)

**2026-10-14 04:20. Done and run.** The application hosts and joins rooms by code (menu
*Room*, beside *Online*; the name is asked once and kept with the device identity file),
carries the game's lockstep datagrams over net2's carrier (punched routes, relay
fallback), and starts the game's own launch handshake by memory writes at a vertical blank
and one press of cross on each of two of the game's own menus. One new pnach section was
needed (section 2.4): it is not in the fix set, so the figure stays `9ac29719`. Every room
below was in step through a level change, tick logs compared column by column:

| Run | Copies (host first) | Routes | Ticks in step (every pair) | Fix set |
|---|---|---|---|---|
| `lv-an` | app, native | punched (127.0.0.1) | 2,656 | 073064bb |
| `lv-na` | native, app | punched | 2,662 | 073064bb |
| `lv-aa` | app, app | punched | 3,155 | 073064bb |
| `lv-ann` | app, native, native | punched | 2,628; 2,629; 2,628 | 073064bb |
| `lv-aann` | app, native, app, native | punched | 2,614 - 2,619, all 6 pairs | 073064bb |
| `relay-an` | app, native | relay, forced on both | 2,659 | 073064bb |
| `cur-aw` | app, native window program | punched | 2,661 | **9ac29719** |
| `pub-ana` | app, native window program, app - **through the public service (TLS)** | two pairs punched (this Mac's LAN address), one relayed | 2,634; 2,641; 2,634 | **9ac29719** |

Not done: two computers in two homes; a person at the controls of the application in a
room; *Play again* (a second game in the same room) for the application; the arena modes.
Nothing of this work is running.

| Part | Where | State |
|---|---|---|
| the room in the application | `tools/play-net/src/RtaRoom.h`, `RtaRoom.cpp` | **Ran** |
| the carrier hook | `tools/play-net/src/RtaNet.h`, `RtaNet.cpp` (`NetCarrier`) | **Ran** |
| the menu *Room*, the name question, the code window | `tools/play-net/src/RtaUi.cpp`, `Rta.h` | name question and identity **Ran**; the menu entries compiled, not clicked (the tests use the same calls through `--rta-room` and the control socket) |
| options, control socket `room ...`, tick log hook, arithmetic from the room | `tools/play-net/src/Rta.cpp` | **Ran** |
| the executor's block hook (tick log, tick-keyed writes) | `tools/play-net/play-net.patch` (`Source/ee/EeExecutor.h/.cpp`) | **Ran**: the application's tick logs equal the native program's in every column |
| net2's client compiled in | `tools/play-net/build.sh` (copies `tools/recomp/net2` and `tools/recomp/net/sock.h`), `play-net.patch` (CMake: every `.cpp` of `rta/net2`, `-framework Network -framework Security`) | **Ran** with the TLS client of 97c60b5 |
| the room-launch section | `patches/SLUS-20973_4028A55F.pnach`, `[Room launch: the developer's network start uses the modules loaded at boot]` | **Ran**; not in `sections-suggested.txt` |
| the proof driver | `tools/play-net/roomparty.py` | **Ran** |
| packaging | `tools/play-net/package.sh --default-room-service HOST:PORT` (`room_service` in `defaults.ini`) | syntax-checked only |

## 1. What a player does

- *Room > Host a room*: the first time in this data folder a sheet asks "the name the other
  players see" (3 to 24 bytes, any text). There is no account and no password: the player
  is `net2-identity.key` in the application's data folder (mode 0600, made at that moment),
  exactly as the native program has it (`native-rendezvous.md` 3.1). A window shows the
  room code in large letters.
- The others choose *Room > Join a room...* and type the code - in the application or in
  the native program (`--play-join CODE`, or the portal).
- On every machine the game's own character screens come up by themselves (at the title
  screen; a room asked for at power-on presses cross through the card questions and logos
  first): make a character, or *Import* one from the memory card.
- When everybody has a character, the host chooses *Room > Start the game*. The game's own
  "Network Game Launch" handshake runs and the first level loads.
- The status bar says where the room is ("room H4KQ7: 3 players - ..."), and a warning when
  the copies differ (fix set, arithmetic).
- Where the service is: `--rta-room-service HOST:PORT`, else `room_service` in `launch.ini`
  (or the bundle's `defaults.ini`, `package.sh --default-room-service`), else
  `RTA_NET2_SERVICE`, else `net2-service.txt` in the data folder. A service named by a host
  name is reached inside TLS (net2's own rule, `tools/recomp/net2/tls.h`); one on this
  computer or a home network address in plain text. The built-in default stays empty.

**Ran**: the name question on a new data folder (sheet up, the name typed and accepted
through the control file `<control>.ui`: "I am Tester of rooms, friend code YATT-N68D (a
new identity, made now)"), then a second start of the same folder: no question, the same
friend code. Every room of the table above: hosted or joined by code, character screens,
start.

## 2. The start, without calling the game

The native program calls the game's functions from its main thread
(`tools/recomp/net2/launch.cpp`). The emulator cannot call into the emulated machine; what
the calls did is had by writing memory at a vertical blank and letting the game's own front
end (`frontend_run` 0x1e08f0, one pass per frame) do the rest. All addresses are the
executable's (**Read** from the game's code; the effect of every step **Ran**).

### 2.1 The character screens

The title menu's branch for a key that is neither of the retail two clears the net
settings block 0x402a30 (0x14c bytes), sets the net flag 0x4f70a0 and goes to front-end
state 6 with the menu pointer 0x4f6b7c on the developer's host / client menu 0x4f6db8
(`menu_net_client`, `menu_net_server`). The application does exactly that, and writes the
menu's selection (the word after its last entry, index in both bytes - what
`menuList_setSelection` 0x1a076c writes) on "client". Then it presses cross for five frames.
State 6's handler (0x1e1b6c) sets difficulty and mode, points 0x86ad54 at the "chosen" byte
0x4fbbe2, goes to state 7 and starts the character screens (`frontend_startPlayerSelect`).
At the first blank in state 7 the application parks the front end in state 10 ("waiting for
the lobby"; with lobby state 0 it does nothing), so that the end of the screens launches
nothing by itself. A character is chosen when the task `playerSelection` is gone from the
game's task table (0x840108, 16 bytes an entry, count 0x44fdb8 - what `task_isRunning`
0x19e5e8 reads) and 0x4fbbe2 is 1. **Ran**: in every room, five blanks after the press.

### 2.2 The launch

At the room's start (the routes stand, or four seconds have passed: the relay carries what
is not straight yet), the application writes what state 7 would leave - settings bits (host,
and 2 or 4 by the kind of character), 0x402a3a = 0xff - and the developer's address table
0x53d0e8: four records of eight words, two addresses a b c d each. Every player k is
10.77.0.(k+1) as on the native program; in this machine's own record the second address is
its real one (198.19.x.y, RtaNet's DHCP answer), because `frontend_startNetGame` 0x1e21e0
finds "my number" by comparing those second addresses with its interface's address (libnet
keeps the address as one machine word: bytes backwards). Then front-end state 3 with the menu
pointer on the difficulty menu 0x4f6e38 (selection: the host's difficulty), and cross. The
difficulty menu's handler (0x1e1a88) writes the difficulty and calls
`frontend_startNetGame`, whose branch for lobby state 0 calls `net_gameInit(0)`, copies the
table, sets the count to a fixed 4 and own number by the match, and ends in
`net_launchPrepare` 0x134c60.

### 2.3 The count of four

`net_launchPrepare` builds its launch records for the count it finds (4) and sends nothing;
its last write is -1 to 0x402b84, which the application sets to 0 before. At the first blank
that finds -1 there - always before the front end's next pass, the first that runs
`net_launchUpdate` - the count 0x402a37 is set to the room's and this machine's second
address back to 10.77.0.(k+1). The section 7 design called this "the delicate one". **Ran**:
in every launch the log says "count 4 -> N, I am player K" with K right; the handshake then
ran between the room's players only. From the press to the tables standing took 266 - 310
blanks (the network interface coming up, 2.4), to "launched" 455 - 490 blanks; the native
copies in the same rooms launched after 488 - 489 blanks (they wait for the application in
the handshake).

### 2.4 What section 7 did not foresee: the developer's network start

`net_gameInit(0)` calls `net_loadModules` 0x137a10 when the flag 0x402790 is clear. That
function was written for a development kit: it loads every network module (inet, inetctl,
ppp, pppoe, dev9, smap or spduart, msifrpc, libnet; eznetcnf and eznetctl from `host0:`),
reads the network setting from `mc0:/BWCONFIG/BWCONFIG`, sets the combination "Setting 1",
brings the interface up and waits for it. On the retail boot `iop_loadModules` 0x19ba98 has
loaded all of those modules already (eznetcnf and eznetctl too), and a lobby game never calls
`net_gameInit(0)` (the lobby brings the interface up with its own thread, `netcfg_thread`
0x34e068, and calls `net_gameInit(12)`). **Ran**: four starts without a patch (runs
`an1` - `an4`) ended the emulator with a fault in its IOP (`CIopBios::SetAlarm`, a thread
it could not make) 2 - 5 s after the press, during that second load.

There is no way to bring the interface up by writing memory (it is a request to an IOP
module), and the lobby's own way goes through the sign-in step. So, as section 7 allowed, a
minimal pnach section: `[Room launch: the developer's network start uses the modules loaded
at boot]`, 20 words:

| Words | What |
|---|---|
| 12 | the twelve module loads of `net_loadModules` (its calls of 0x35b9a8) become `nop` |
| 5 | the string `mc0:/BWCONFIG/BWCONFIG` (0x530528) becomes `mc0:/BWNETCNF/BWNETCNF`, the retail setting the application writes to the card |
| 3 | the string `Setting 1` (0x530600) becomes `Combination1`, the combination's name in that setting |

What the function then does - ezNetCnf, `ezNetCtlInit`, the interface up, the wait for it -
is the game's own. `net_loadModules` has one caller (`net_gameInit` with 0), so a lobby
game, an offline game and the native program (whose `net_loadModules` is the network
driver's own, `native-online.md`) are not touched.

**Effect on the fix set `9ac29719`: none.** The section is not in
`tools/play-net/sections-suggested.txt`; the application reads it by its name beside the
fix set and does not count it in the figure (**Ran**: "patches: 31 sections, 189 words, set
9ac29719" and, on the next line, "patches: 20 words for the start of a room ..., beside the
fix set (not in its figure)"; the native copies in the same rooms said "patch set 9ac29719
(189 words)" and the room showed no mismatch). No word of it overlaps another section (**Ran**: a
check over the patch file; `tools/touchfix_test.py` 20 of 20). Measured: with it every
start of the table worked; without it none did (above). With `play.sh --sections '*'`
(every section) it would be counted in that copy's figure.

## 3. The datagrams

`RtaNet.h` has a `NetCarrier` hook: a datagram of the machine to 10.77.0.0/24 while a room's
game is being carried goes to `CRoom::Send` and on to net2's carrier (`Carrier::send(slot)`:
straight when punched, else the service's relay); what the carrier receives is put to the
machine as a datagram from 10.77.0.(k+1):4000 to its port 4000. No address of the made-up
network needs a route of its own: the gateway (RtaNet) takes every address. The patch-set
and arithmetic keep-alives of the lobby path are not sent on this path; the room's member
lines carry the same (`copy fix= words= can= does=`). **Ran**: one other thing - a datagram
handed to the machine while its network modules were still starting (2.4) is thrown away
until `net_launchPrepare` has run ("6 datagram(s) of the others thrown away before the game's
socket was open"); the other players' handshake sends again until answered.

Relay, forced on both copies (`relay-an`): the application sent 1,600 and received 1,572
datagrams, all through the service; the service relayed 2,938 (150 kB) and dropped 259 - all
of them in the last 26 s, as the copies were ending (none at its report half a minute
before; that they belong to the leaving is Inferred). Public run: the two application copies and the native copy
punched to each other through this Mac's LAN address but for one pair (native and the
second application), which went through the relay (1,085 out, 1,070 in) - as designed.

**The arithmetic rule** (`mixed-arithmetic.md` section 5) is applied from the room's members:
in automatic mode the application changes to browser arithmetic when a member says it cannot
compute as the console does or already computes as a browser does (Read in code; not run -
no browser copy is in a room yet). The application tells the room "can both, does the
console's"; the native program says "the console's" (`launch.cpp`), so a room of the two
stays in the console's arithmetic. **Ran**: no room of the table showed a mismatch.

## 4. Tick logs of the application

The native program logs a lockstep tick at the return of the tick's task pass in
`net_frameLoop` (0x13aee8) and makes tick-keyed writes there; the rig does it with a break
point, which the application's build does not have. `play-net.patch` gives Play!'s EE
executor a block hook (`CEeExecutor::Execute`: a call before the block at one address is run
from the executor's loop - the return from `tasks_run` is a jump through a register, so it
always passes the loop; with no address set the loop is Play!'s own). `--rta-tick-log`,
`--rta-tick-watch`, `--rta-tick-do` write the native program's format (the same columns, the
same value formats, numbers instead of names) and do `poke` / `poke32` in a given tick.
**Ran**: the level change of every run is a `poke g_pendingLevel drunare` in tick 1600 on
every copy, the application's included, and every pair of logs had no shared column
differing (seed, level, player count, button maps, the previous tick's sync hash, every
player's position, state, hit points, gold, experience, out-of-step flags).

## 5. Proof

All on this Mac, 2026-10-14 03:26 - 03:51, load average 9 to 26. Application copies: my
build of the working tree (`local/app-rv`, a copy of the Play! tree and its build
directory), test windows behind the others (`--rta-test`), a control socket, data folders
of their own, no sign-in patch. Native copies: `n2_headless` (fix set 073064bb, the
29-section set the application then gets with `--drop-section` of the two newest) or the
window program `rta_app` off-screen (9ac29719, the 31 sections the application has by
default). A service of each run's own on 127.0.0.1 (`rendezvous.py`), but for `pub-ana`:
the public one (named by its host name, inside TLS). Each copy boots by itself, makes a new
character on the game's screens (the application's pressed through its control socket by
`roomparty.py`, the native ones by their scripts), the host starts when all are ready, 900
frames of drawn input, the level change, 900 more. Results: the STATE table (one launch
each, every copy reached both levels and finished its script). Commands:

```
export RTA_DISC="/path/to/your disc image.iso"
python3 -B tools/play-net/roomparty.py OUT --copies app,native --play 900 --level drunare --play2 900 \
    [--drop-section NAME]... [--relay force] [--native-window PATH/rta_app] \
    [--external --service-address HOST --port PORT]
```

Earlier, failing: `an1` - `an4` (section 2.4). `an5`: the first start that worked, 919 ticks
in step in `hub`.

## 6. What the owner must do

Nothing for the code. To give friends a packaged application that finds the public service
by itself: `tools/play-net/package.sh --default-room-service <the service's host name>:41900`
(the address stays out of the repository). `build.sh` needs `--reset` once on an existing
Play! tree (the patch changed).

## 7. Files

New: `tools/play-net/src/RtaRoom.h`, `RtaRoom.cpp`, `tools/play-net/roomparty.py`, this file.
Changed: `tools/play-net/src/Rta.cpp`, `Rta.h`, `RtaNet.cpp`, `RtaNet.h`, `RtaUi.cpp`,
`tools/play-net/play-net.patch`, `build.sh`, `package.sh`, `README.md`,
`patches/SLUS-20973_4028A55F.pnach` (the new section, at the end). Local, not in the
repository: `local/app-rv/` (the Play! tree and build, `runs/` with every run's logs and tick
logs, `sync.sh`). Nothing in `tools/recomp/net2/` was edited.
